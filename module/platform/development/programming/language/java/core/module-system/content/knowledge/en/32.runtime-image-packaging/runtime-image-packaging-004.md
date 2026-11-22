# Launcher Scripts and Module Main

## Objectives

After this lesson, you will be able to:

- Explain the role of the module main class when launching a modular application.
- Create a launcher script that invokes `java -m` and forwards arguments to the application.
- Create a custom launcher in a custom runtime image using `jlink --launcher`.
- Package an application launcher using `jpackage`.
- Distinguish between the module main class, a main class specified on the command line, and a launcher script.
- Choose an appropriate packaging approach for applications that need their own runtime or multiple entry points.

## 1. Module Main and Launcher Scripts

A modular application can be launched by module name:

~~~bash
java --module-path app-modules \
     --module com.example.app
~~~

When the command line only has the module name, the Java launcher needs to know the module's main class. This information can be stored in the binary module descriptor as the `ModuleMainClass` attribute, typically set when packaging a modular JAR with `jar --main-class`.

If the module descriptor does not yet have a main class, specify the main class explicitly on the command line:

~~~bash
java --module-path app-modules \
     --module com.example.app/com.example.app.Main
~~~

In a deployment environment, end users generally do not want to memorize the module path, module name, main class, or runtime path. A launcher script solves this startup interface: it locates the installation directory, invokes the right Java runtime, passes the module entry point, and forwards arguments to the application.

A launcher script does not replace the module descriptor. It is an external launch layer, while the module main is still determined by the descriptor or the command line that the script invokes.

## 2. Preparing a Modular Application

Suppose an application has the structure:

~~~text
customer-app/
├── src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── build/
│   └── mods/
└── scripts/
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Main class:

~~~java
package com.example.app;

import java.util.Arrays;
import java.util.logging.Logger;

public class Main {

    private static final Logger LOGGER =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOGGER.info("Customer application started");
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
~~~

Compile the module:

~~~bash
javac --module-source-path src \
      -d build/mods \
      -m com.example.app
~~~

The output is an exploded module at `build/mods/com.example.app`. You can run it directly by specifying the module and main class:

~~~bash
java --module-path build/mods \
     --module com.example.app/com.example.app.Main \
     --config conf/app.properties
~~~

Arguments after the module entry point are passed into `main(String[] args)`.

## 3. Storing the Module Main Class in a Modular JAR

If you want the launcher to only need the module name, package the application into a modular JAR and store the main class:

~~~bash
jar --create \
    --file build/mods/com.example.app.jar \
    --main-class com.example.app.Main \
    -C build/mods/com.example.app .
~~~

`--main-class` (or `-e`) writes the main class name into the binary module descriptor. You can inspect it with:

~~~bash
jar --describe-module \
    --file build/mods/com.example.app.jar
~~~

The output may display:

~~~text
com.example.app
requires java.base mandated
requires java.logging
main-class com.example.app.Main
~~~

Now you can run the module without typing the class name:

~~~bash
java --module-path build/mods \
     --module com.example.app \
     --config conf/app.properties
~~~

If the command line specifies `com.example.app/com.example.app.AdminMain`, that class will be used instead of the stored default main class. This is useful when a module provides multiple entry points.

## 4. Creating a Launcher Script on Linux and macOS

Suppose the deployment directory has the structure:

~~~text
customer-app/
├── app/
│   └── com.example.app.jar
├── runtime/
│   └── bin/java
└── bin/
    └── customer-app
~~~

Script `bin/customer-app`:

~~~bash
#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_HOME=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)

JAVA="$APP_HOME/runtime/bin/java"
APP_MODULE_PATH="$APP_HOME/app"

exec "$JAVA" \
    --module-path "$APP_MODULE_PATH" \
    --module com.example.app \
    "$@"
~~~

Grant execute permission to the script:

~~~bash
chmod +x bin/customer-app
~~~

Run the application:

~~~bash
bin/customer-app --config "conf/customer settings.properties" --verbose
~~~

The script works as follows:

1. Determines the directory containing the script.
2. Finds the root installation directory from the script's location, independent of the caller's current working directory.
3. Uses the Java runtime packaged with the application.
4. Sets the module path to the directory containing modular JARs.
5. Launches the module using the stored module main class.
6. Forwards each argument via `"$@"`, preserving argument boundaries even when spaces are present.
7. `exec` replaces the shell process with the Java process so the application's exit code is returned directly.

If the JAR does not store a module main class, the script can specify the entry point explicitly:

~~~bash
exec "$JAVA" \
    --module-path "$APP_MODULE_PATH" \
    --module com.example.app/com.example.app.Main \
    "$@"
~~~

When deploying a bundled runtime, verify that `runtime/bin/java` exists and has execute permission. Do not assume the user's machine has the right JDK version installed just because the build environment has a JDK.

## 5. Creating a Launcher Script on Windows

With the same deployment structure, create the file `bin/customer-app.bat`:

~~~bat
@echo off
setlocal

for %%I in ("%~dp0..") do set "APP_HOME=%%~fI"

set "JAVA=%APP_HOME%\runtime\bin\java.exe"
set "APP_MODULE_PATH=%APP_HOME%\app"

"%JAVA%" --module-path "%APP_MODULE_PATH%" --module com.example.app %*

set "APP_EXIT=%ERRORLEVEL%"
endlocal & exit /b %APP_EXIT%
~~~

Explanation:

- `%~dp0` is the directory containing the batch file.
- `for %%I ... %%~fI` normalizes the installation directory path.
- Runtime and module path strings are enclosed in double quotes to handle spaces.
- `%*` forwards the command-line arguments passed by the user.
- The exit code is saved before `endlocal`, then returned to the calling process.

Run:

~~~bat
bin\customer-app.bat --config "conf\customer settings.properties" --verbose
~~~

If using an explicit main class, replace the module argument with:

~~~bat
--module com.example.app/com.example.app.Main
~~~

When writing a batch launcher, test actual invocations with arguments containing spaces, double quotes, and special characters. Argument parsing syntax in `cmd.exe` differs from Unix shells.

## 6. Using jlink to Create a Runtime Image with a Custom Launcher

If you want to distribute a runtime containing only the necessary modules, you can use `jlink`.

First, package the application into a modular JAR as in the previous section. Then create the runtime image:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:build/mods" \
    --add-modules com.example.app \
    --launcher customer-app=com.example.app \
    --output build/customer-runtime
~~~

In this example:

- `--module-path` supplies JDK modules and application modules.
- `--add-modules com.example.app` selects the root module to include in the image; its dependencies are also resolved.
- `--launcher customer-app=com.example.app` creates a launcher named `customer-app`.
- `--output` specifies the runtime image directory.

If the module descriptor has `ModuleMainClass`, you may only need the module name in the launcher declaration. If the descriptor does not store a main class, specify it explicitly:

~~~bash
--launcher customer-app=com.example.app/com.example.app.Main
~~~

After successful creation, the runtime image has the general form:

~~~text
build/customer-runtime/
├── bin/
│   ├── java
│   ├── keytool
│   └── customer-app
├── conf/
├── legal/
└── lib/
~~~

Launch the application using the created launcher:

~~~bash
build/customer-runtime/bin/customer-app --config conf/app.properties
~~~

The launcher generated by `jlink` is a platform-appropriate executable, not a `.sh` shell script or `.bat` batch file that you wrote yourself. It uses the bundled runtime image and the configured entry point.

### 6.1. Module Path When Running a Runtime Image

When the application module has already been linked into the image, the launcher does not need to specify the external JAR module path again:

~~~bash
build/customer-runtime/bin/java \
    --module com.example.app \
    --config conf/app.properties
~~~

If the application module is linked with the runtime image and its descriptor already stores the main class, the module name alone is sufficient. If you need a different entry point, specify `module/mainclass` on the command line or create a separate launcher for that entry point.

### 6.2. Provider Modules and Service Binding

If the application uses service providers and you want `jlink` to automatically include matching provider modules in the image, consider the option:

~~~bash
--bind-services
~~~

Providers must still be present in the input module path and discovered via service declarations. `--bind-services` assists service binding when creating the image; it does not automatically load provider JARs from an arbitrary directory outside the module path.

## 7. Packaging an Application Launcher with jpackage

`jpackage` creates a platform-appropriate application image or installer. It can create a launcher for a modular application directly:

~~~bash
jpackage \
    --type app-image \
    --name CustomerApp \
    --dest build/package \
    --module-path build/mods \
    --module com.example.app
~~~

If the module descriptor already stores the module main class, `--module` only needs the module name. If not, specify both the module and main class:

~~~bash
--module com.example.app/com.example.app.Main
~~~

The result is an application image with a launcher for users to run. Depending on the operating system and package type, the launcher may be an executable or an app bundle. If you want to use a runtime image already created with `jlink`, you can pass `--runtime-image` to `jpackage`:

~~~bash
jpackage \
    --type app-image \
    --name CustomerApp \
    --dest build/package \
    --runtime-image build/customer-runtime \
    --module com.example.app
~~~

Do not simultaneously pass runtime-creation options that are incompatible with `--runtime-image`; let the created image supply the runtime for the package.

### 7.1. Multiple Launchers for Multiple Module Mains

An application can provide multiple different launch commands, such as a main launcher and an administration launcher. With `jpackage`, use `--add-launcher` along with a properties file for the additional launcher.

Example `admin-launcher.properties`:

~~~properties
module=com.example.app/com.example.app.AdminMain
arguments=--mode,admin
java-options=--add-opens=com.example.app/com.example.app.internal=ALL-UNNAMED
win-console=true
~~~

Package the additional launcher:

~~~bash
jpackage \
    --type app-image \
    --name CustomerApp \
    --dest build/package \
    --module-path build/mods \
    --module com.example.app \
    --add-launcher admin=admin-launcher.properties
~~~

In the example, the primary launcher uses the default module main class; the `admin` launcher specifies a different main class and adds custom arguments/options. The properties file should be adjusted to match the actual modules and access requirements of the application.

## 8. Choosing Launcher Script, jlink, or jpackage

| Deployment Approach | Best Suited When | Result |
|---|---|---|
| Custom `.sh` / `.bat` script | You want control over how the runtime, config, and arguments are located | Thin script file invoking `java -m` |
| `jlink --launcher` | You want a small custom runtime image and a dedicated launcher | Runtime image with executable launcher |
| `jpackage` | You want an application image or installer for end users | Platform-specific app image/installer |

Approaches can be combined. For example, use `jlink` to create a runtime image, then use `jpackage --runtime-image` to package the application. A custom script can also invoke a runtime image created by `jlink`.

Choose based on deployment needs:

- If the target environment already has a suitable Java installation and the application is simple, a script calling `java -m` may suffice.
- If you need to ship a dedicated runtime and control which modules are packaged, use `jlink`.
- If you need an easy-to-install app image or installer, use `jpackage`.
- If there are multiple entry points, use `jlink --launcher` or `jpackage --add-launcher` to assign a distinct name to each command.

## 9. Common Errors

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Module ... not found` | Module path or module image is missing the application module | Check `--module-path`, `--add-modules`, and the module name |
| Main class not found when passing only module name | Module descriptor does not store `ModuleMainClass` | Use `jar --main-class` or explicitly specify `module/mainclass` |
| Launcher runs an unexpected class | Script or launcher specifies a main class different from the descriptor | Check the module argument part after `/` |
| Script works inside project directory but fails elsewhere | Script relies on current working directory | Compute `APP_HOME` from the script file's location |
| Java runtime not found | Bundled runtime path is wrong or image is incomplete | Check `runtime/bin/java` or `image/bin/java` |
| `jlink` reports missing module | Dependency or provider module is not on the module path | Add the module to the input path and check the module graph |
| Windows launcher does not receive arguments properly | Batch file handles quoting/spaces improperly | Test `%*` with arguments containing spaces and quotes |
| Installer is missing runtime | `jpackage` was not given a runtime image and did not build one per desired config | Check `--runtime-image` or input module path |

When debugging, print or inspect the actual command line used by the script/launcher. Module path, module name, and main class are the first three values to verify.

## 10. Summary

The module main class defines the default entry point of a modular application. A launcher script wraps the parameters needed to invoke `java -m`, find the right runtime, and forward arguments. If a dedicated runtime image is needed, `jlink` can create an image with a launcher via `--launcher`; if an application image or installer is needed, `jpackage` creates launchers and can add multiple entry points with `--add-launcher`.

Keep the module name and main class clear in your packaging configuration. If the descriptor stores `ModuleMainClass`, the launcher may only need the module name; if a separate entry point is needed, explicitly specify `module/mainclass`.

References:

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [The jlink Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [The jpackage Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [ModuleDescriptor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
