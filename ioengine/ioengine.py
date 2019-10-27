"""The IOEngine class."""
import inspect
import sys
import yaml
import os
import threading
import uuid
from types import ModuleType

from ioengine.utils import dotdict
from ioengine.exceptions import UnsupportedAPI


class IOEngine:
    """The IOEngine class."""

    def __init__(self):
        """Set up engine."""
        self.services = []
        self.packages = {}
        self.engine_api = dotdict(showMessage=print, register=self.register_service)
        self._service_lock = threading.Lock()

    def register_service(self, **api):
        """Set interface."""
        if isinstance(api, dict):
            api = {a: value for a, value in api.items() if not a.startswith("_")}
        elif inspect.isclass(type(api)):
            api = {a: getattr(api, a) for a in dir(api) if not a.startswith("_")}
        else:
            raise UnsupportedAPI
        self.services.append(dotdict(**api))

    def register(self, **kwarg):
        """Register api resources."""
        if kwarg["type"] == "service":
            self.register_service(**kwarg)
        else:
            raise NotImplementedError

    def execute(self, script):
        """Execute a script via the api."""
        # make a fake module with api
        mod = ModuleType("bioimage")
        sys.modules[mod.__name__] = mod  # pylint: disable=no-member
        mod.__file__ = mod.__name__ + ".py"  # pylint: disable=no-member
        mod.api = dotdict(**self.engine_api)
        exec(script, self.engine_api)  # pylint: disable=exec-used

    def load_package(self, package_dir):
        """load a service package."""
        with open(os.path.join(package_dir, "config.yaml"), "r") as f:
            package_info = yaml.load(f, Loader=yaml.FullLoader)
            package_info["id"] = str(uuid.uuid4())
            package_info["_locals"] = {}
            package_info["package_dir"] = package_dir
            try:
                self._service_lock.acquire()

                entry_point = os.path.join(package_dir, package_info["entrypoint"])
                model_script = open(entry_point).read()
                sys.path.insert(0, package_dir)

                # make a fake module with api
                mod = ModuleType("bioimage")
                sys.modules[mod.__name__] = mod  # pylint: disable=no-member
                mod.__file__ = mod.__name__ + ".py"  # pylint: disable=no-member
                mod.api = dotdict(**self.engine_api)
                mod.api.getServiceInfo = lambda: package_info
                mod.api.getConfig = lambda: package_info.get("config")

                exec(model_script, package_info["_locals"])
                self.packages[package_info["id"]] = package_info
            except Exception as e:
                if package_dir in sys.path:
                    sys.path.remove(package_dir)
                raise e
            finally:
                self._service_lock.release()

    def unload_package(self, package_id):
        if package_id in self.packages:
            package_info = self.packages[package_id]
            package_dir = package_info["package_dir"]
            if package_dir in sys.path:
                sys.path.remove(package_dir)
            del self.packages[package_id]
        else:
            raise Exception(f"Package {package_id} not found")


def main():
    """Run main."""
    ioe = IOEngine()
    # execute a model script directly
    ioe.execute(
        """
from bioimage import api
def run():
    api.showMessage('hello')
api.register(type='service', name='test', run=run)
"""
    )
    print(f"Service registered: {ioe.services}")
    ioe.services[0].run()

    ioe = IOEngine()
    # load a service package
    ioe.load_package("../example_packages/unet2d")
    print(f"Service registered: {ioe.services}")
    # use the registered service
    ioe.services[0].train()
    ret = ioe.services[0].predict(1)
    print(ret)


if __name__ == "__main__":
    main()
