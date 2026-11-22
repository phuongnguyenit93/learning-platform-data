
# jpackage and How to Distribute Desktop Applications

A Java program that runs from an IDE or via the `java -jar` command is not yet synonymous with a **desktop application that can be distributed to end users**. They need a launcher, an icon, ways to install, update, and uninstall, data write permissions, multi-operating-system support, and a compatible Java runtime without having to configure it manually.

`jpackage` helps create an **application image** and **native installer packages** for Java desktop applications. In the problem of *Java Advance Compatibility Migration*, the *Packaging and Environment* section, this tool is especially important when the system moves from the “install a JRE on the client machine and then run a JAR” model to the model of **packaging the application together with its own runtime**, in order to control the JDK version and reduce environment errors.

However, successfully running `jpackage` only proves that the tool has created the artifact. **The ability to install and operate on real machines** still depends on Java modules, JavaFX, native libraries, CPU architecture, the operating system, signing, launcher configuration, and the update process. This lesson walks through each of those layers and how to verify them when upgrading the JDK.

The examples use the `jpackage` of a JDK that supports this tool. Option names, auxiliary tools, and native installer formats may differ depending on the JDK release or vendor. Always check `jpackage --help` and the documentation for the **exact target JDK and OS**. Illustrative package names, versions, and paths must be replaced with the actual data of the project.

## 1. What does a Java desktop application need besides a JAR?

A simple application can run as follows:

~~~bash
java -jar desktop-app.jar
~~~

But end users usually do not want to open a terminal and figure out the classpath or install a JDK manually. When distributing a desktop application, the development team needs to address:

- **Launcher:** users double-click an icon or select from the operating system menu.
- **Runtime:** Java version, modules, JVM options, and native dependencies.
- **Installer:** installation location, shortcuts, file associations, and install permissions.
- **Versioning:** package name, version, upgrade identity, and data compatibility.
- **Security:** digital signature of the package, download source, update authenticity.
- **Data:** where to store configuration, cache, logs, and user documents.
- **Operations:** startup error support, uninstallation, rollback, and security patches.
- **Cross-platform:** Windows, macOS, Linux, and CPU architectures.

A JAR that runs properly on a developer's machine can still fail when placed on a machine without a JDK or missing JavaFX native libraries.

### 1.1. Common distribution methods

| Model | User receives | Strengths | Limitations |
|---|---|---|---|
| Pure JAR | JAR, Java instruction documentation | Simple for developers | Depends on JRE/system setup |
| JAR with script | JAR, dependencies, shell/batch script | Easy to customize internally | Launcher and UX are still manual |
| `jpackage --type app-image` | Application directory, launcher, runtime | Test/copy before installer | Not itself a native installer |
| Installer created by jpackage | MSI/EXE, DMG/PKG, DEB/RPM depending on OS | Familiar installation experience | Depends on OS tools/metadata |
| Installer + custom update system | Installer package and update mechanism | Can control lifecycle | Must design verification, rollback |

**`jpackage` does not turn all Java bytecode into AOT machine code** like a native-image compiler. It mainly builds the launcher, runtime image, and platform-specific application structure/installer package.

## 2. What is jpackage?

`jpackage` is a command-line tool in the JDK whose job is to create an application image and native package for a Java application.

Important historical milestones:

- **JDK 14:** `jpackage` was introduced in incubating state under JEP 343.
- **JDK 16:** `jpackage` became a production tool under JEP 392.
- **Subsequent JDKs:** continued adjusting features, signing, installer options, and platform integration.

Therefore, a project running on **JDK 8 or JDK 11 cannot rely by default on the standard `jpackage` tool in that JDK**. You can use a newer JDK for the build/package step and choose a suitable runtime, but you must verify application compatibility and bytecode target separately.

### 2.1. Checking the toolchain

~~~bash
java -version
javac -version
jpackage --version
jpackage --help
~~~

On Windows PowerShell:

~~~powershell
java -version
jpackage --version
jpackage --help
~~~

If the machine has multiple JDKs, `java` and `jpackage` on PATH may come from two different installations. You should invoke them via explicit JDK paths in CI and record the version.

### 2.2. How does jpackage differ from jlink?

| Tool | Primary responsibility |
|---|---|
| `javac` | Compiles Java source |
| `jar` | Creates/reads JARs |
| `jdeps` | Analyzes module/dependency references at the bytecode level |
| `jlink` | Creates a custom Java runtime image containing the selected set of modules |
| `jpackage` | Creates an application image and installer with a launcher |
| Maven/Gradle | Manages dependencies, build pipeline, and invokes the tools |
| OS tools | MSI, signing, notarization, Linux package metadata |

`jlink` creates a runtime image; **it does not build the application's installer experience on its own**. `jpackage` can build a runtime for the package or use a runtime image that the team has already provided via `--runtime-image`.

## 3. What components does jpackage create?

General workflow:

~~~mermaid
flowchart TD
    A["Source / resources"] --> B["Compile + JAR/modules"]
    C["Third-party dependencies"] --> D["Application input"]
    B --> D
    E["JDK / custom runtime / JavaFX"] --> F["Runtime image"]
    D --> G["jpackage"]
    F --> G
    H["Icons, metadata, launcher flags"] --> G
    G --> I["Application image"]
    I --> J["Native installer by OS"]
    J --> K["Install, launch, upgrade, uninstall"]
~~~

An application image usually contains:

- **Application launcher**: executable file or entrypoint suitable for the OS.
- **Application files**: JARs/modules, resources, necessary native dependencies.
- **Java runtime**: the set of JVM/Java modules bundled with the application.
- **Launcher configuration**: main class/module and JVM arguments.
- **OS metadata**: name, version, icon, and other components.

You should not hardcode directory structures inside the image because the layout differs by OS and JDK. On macOS, the `.app` bundle has its own structure; on Windows/Linux, launcher and runtime placement differ.

### 3.1. A bundled runtime differs from a system JRE

When an application carries its own runtime, users **usually do not have to install Java system-wide** to run that application. This reduces risks:

- The client machine has no Java.
- The client machine has an old incompatible Java.
- Multiple applications compete over Java versions.
- Environment variables are misconfigured.
- Upgrading the system JDK causes regressions for the desktop app.

But in return, the release team must **update the Java runtime packaged inside the installer** when security patches are released. Having users update the system JDK does not necessarily affect the bundled runtime.

### 3.2. A packaged runtime is not the entire operating system

GUI, printers, font rendering, JNI, native drivers, the OpenGL/graphics stack, and OS APIs still depend on the platform. Having a bundled runtime does not guarantee that a Linux app image runs on every distro, or that a Windows DLL runs on macOS.

## 4. Output types by platform

| Build OS | Common `--type` | Result |
|---|---|---|
| Windows | `app-image` | Directory with launcher/runtime |
| Windows | `exe`, `msi` | Windows native installer package |
| macOS | `app-image` | Application bundle |
| macOS | `dmg`, `pkg` | Disk image or installer package |
| Linux | `app-image` | Application directory |
| Linux | `deb`, `rpm` | Linux package |

These are **common formats**; there is no guarantee every JDK/vendor has the exact same options. Check host support using `jpackage --help`.

### 4.1. Native packaging usually must be built on the target OS

You should not assume a Linux build can create standard MSI and DMG installers just by changing `--type`. `jpackage` is designed around a **native packaging platform**, so CI pipelines usually need separate Windows, macOS, and Linux workers/build hosts.

Similarly, the runtime image and native libraries must match the CPU architecture:

~~~text
Windows x64  != Windows ARM64
macOS x64    != macOS ARM64
Linux x64    != Linux ARM64
~~~

Java bytecode may be portable, but the launcher, runtime, JavaFX, and native libraries do not automatically become cross-platform.

### 4.2. App image and installer solve two different things

**App image** helps verify the application runtime and launcher. **Installer** adds the OS-specific installation process, metadata, shortcuts, and uninstallation.

The workflow should be:

1. Compile the application and prepare dependencies.
2. Create the app image.
3. Run the actual launcher on the target OS.
4. Check GUI, resources, network, JNI.
5. Only after the app image passes, create the native installer.
6. Test install, upgrade, and uninstall like an end user.

## 5. Self-contained example: small Swing application

The example uses Swing so there is no need to assume JavaFX is present in the JDK. Source:

~~~java
package com.example.desktop;

import java.awt.BorderLayout;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;

public final class DesktopMain {
    private DesktopMain() {
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("DeskDemo");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setLayout(new BorderLayout());

            JLabel label = new JLabel("Xin chào Java desktop");
            JButton button = new JButton("Nhấn");

            button.addActionListener(event ->
                    label.setText("Đã nhấn nút"));

            frame.add(label, BorderLayout.CENTER);
            frame.add(button, BorderLayout.SOUTH);
            frame.setSize(420, 230);
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }
}
~~~

Explanation:

- `SwingUtilities.invokeLater` initializes the GUI on the Event Dispatch Thread.
- `JFrame.EXIT_ON_CLOSE` allows the application to exit when the window is closed.
- `java.desktop` is the Java SE module related to Swing/AWT.
- The application main class is `com.example.desktop.DesktopMain`.
- The example has no dependencies outside Java SE.

### 5.1. Compiling and creating a JAR

In a Unix shell:

~~~bash
mkdir -p build/classes build/package-input
javac -d build/classes src/com/example/desktop/DesktopMain.java
jar --create --file build/package-input/desk-demo.jar \
    --main-class com.example.desktop.DesktopMain \
    -C build/classes .
~~~

Run before packaging:

~~~bash
java -jar build/package-input/desk-demo.jar
~~~

If the project uses Maven/Gradle, let the build tool create the JAR and copy runtime dependencies; do not maintain a separate build path manually that can easily drift from CI.

### 5.2. Preparing the input directory when there are multiple JARs

Conceptual example:

~~~text
build/package-input/
├── desktop-app.jar
├── dependency-a.jar
├── dependency-b.jar
└── resources/
~~~

`--input` specifies the input directory. `--main-jar` identifies the main JAR inside it. **Do not assume that jpackage will automatically resolve dependencies from a Maven repository** just because there is a main JAR; the build pipeline must prepare the application files that the launcher needs.

After packaging, you must test the launcher from the image to verify the actual classpath and resources.

## 6. Creating an app-image with jpackage

Example:

~~~bash
jpackage \
  --type app-image \
  --input build/package-input \
  --dest build/dist \
  --name DeskDemo \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --app-version 1.0.0 \
  --vendor "Example Team" \
  --add-modules java.desktop
~~~

The options:

| Option | Purpose |
|---|---|
| `--type app-image` | Creates a self-contained application directory |
| `--input` | Directory of application files |
| `--dest` | Output directory |
| `--name` | Application/launcher name |
| `--main-jar` | Main JAR, relative to input |
| `--main-class` | Main class of a non-modular application |
| `--app-version` | Application version |
| `--vendor` | Publisher name |
| `--add-modules` | Additional modules for runtime creation |

If the main JAR manifest already specifies the main class, the tool may infer the class depending on the model; specifying it explicitly makes the example easy to follow.

### 6.1. Inspecting the output

Illustrative structure:

~~~text
build/dist/
└── DeskDemo/
    ├── launcher
    ├── app/
    │   └── desk-demo.jar
    └── runtime/
        ├── bin/
        └── lib/
~~~

**This is not a mandatory standard layout.** Each OS/JDK may organize it differently; in particular, a macOS app bundle has its own structure.

Testing:

- Locate the actual launcher inside the image.
- Open the application window.
- Enter Vietnamese text and check fonts.
- Check images/resources.
- Close the application and confirm the process terminates.
- Test on a machine without system Java configured.
- Check the embedded source JDK/runtime version when needed for diagnostics.

### 6.2. App image is a useful technical checkpoint

If the launcher in the app image already fails to run, packaging it into an MSI/DMG usually will not solve runtime errors. Fix issues such as a missing class, missing module, wrong main class, or native libraries beforehand.

## 7. Non-modular and modular applications

`jpackage` supports two main models.

### 7.1. Non-modular application

Usually uses `--input`, `--main-jar`, `--main-class`:

~~~bash
jpackage --type app-image \
  --name DeskDemo \
  --input build/package-input \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain
~~~

Suitable for traditional applications running on the classpath. It is not mandatory to add `module-info.java` just to distribute with jpackage.

However, you need to check that runtime JARs, service metadata files, and dynamic class loading are not missing after packaging.

### 7.2. Modular application (JPMS)

Example module descriptor:

~~~java
module com.example.desktop {
    requires java.desktop;
    exports com.example.desktop;
}
~~~

If modular JARs have been created in `build/mods`:

~~~bash
jpackage \
  --type app-image \
  --name DeskDemo \
  --module-path build/mods \
  --module com.example.desktop/com.example.desktop.DesktopMain \
  --dest build/dist
~~~

Here `--module` specifies the main module and main class. Named modules require a proper module graph.

### 7.3. Do not mix the two ways of declaring the main application

A common mistake is using both main JAR configuration and module main from two different models and not knowing what the launcher will select. Choose one appropriate model and test the output.

### 7.4. Should you modularize just for packaging?

Not necessarily. JPMS brings explicit module boundaries, but can also expose:

- Split packages.
- Reflection without `opens`.
- Automatic module naming.
- Unresolved provider modules.
- Dependencies that do not yet support the module path.

If a legacy classpath application is working steadily, you can migrate packaging first and make JPMS migration an independently verified work item.

## 8. jlink and custom runtime images

`jlink` creates a Java runtime image containing only the selected modules.

Example of a simple Swing application:

~~~bash
jlink \
  --add-modules java.base,java.desktop \
  --output build/runtime \
  --strip-debug \
  --no-header-files \
  --no-man-pages
~~~

Then:

~~~bash
jpackage \
  --type app-image \
  --name DeskDemo \
  --input build/package-input \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --runtime-image build/runtime \
  --dest build/dist
~~~

`--runtime-image` accepts a prebuilt runtime. This allows the team to control modules, JDK updates, and custom jlink options.

### 8.1. Risks when a runtime image is too small

An app with only a main window may run, while rarely used features fail:

- Printing documents.
- Using JDBC.
- Loading a TLS/security provider.
- Opening a JavaFX/FXML controller.
- Loading classes by reflection string.
- Using ServiceLoader.
- Loading plugins dynamically.
- Calling a JNI library.

Do not infer from “successful startup” that the runtime image is complete.

### 8.2. jdeps helps identify modules

Example:

~~~bash
jdeps --print-module-deps \
  --class-path "build/package-input/*" \
  build/package-input/desk-demo.jar
~~~

`jdeps` finds static dependencies. It does not necessarily detect dynamically selected service providers, modules loaded via reflection, or optional features. Therefore `jdeps` results must be cross-checked against integration tests.

### 8.3. Service binding

When creating a modular runtime, some applications require provider modules. `jlink` has service binding capability and `jpackage` has related options to pass module selection/jlink options depending on the JDK.

If using `ServiceLoader`, crypto providers, or locale services, you need to check which providers are packaged in the image. Do not simply keep only `java.base` just because it is the minimal module.

## 9. Packaging JavaFX

JavaFX has different requirements from Swing:

- `javafx.controls`, `javafx.graphics`, `javafx.fxml` modules if used.
- OS/architecture-specific native libraries.
- FXML resources and CSS/images/fonts.
- Reflection access for FXML controllers.
- JavaFX version compatible with the toolchain and runtime.

In typical modern JDKs, **JavaFX is not bundled by default as part of the Java SE runtime**. Therefore, installing a JDK does not mean a JavaFX app has enough JavaFX libraries.

### 9.1. Module descriptor

Example:

~~~java
module com.example.viewer {
    requires javafx.controls;
    requires javafx.fxml;
    exports com.example.viewer;
    opens com.example.viewer.controller to javafx.fxml;
}
~~~

`opens` allows the FXML loader to perform reflection into the controller package by design.

### 9.2. Target-specific JavaFX JMODs

If building a custom runtime with jlink, you must use JavaFX JMODs matching the target OS/CPU. A set of JavaFX native libraries for Linux cannot be assumed to run on Windows.

In CI, you should create separate packaging jobs and verify input artifacts per platform.

### 9.3. Important tests for JavaFX

- Stage/scene opens.
- FXML controllers are created.
- CSS/fonts/images load properly.
- Keyboard, Vietnamese input, and Unicode.
- Rendering/DPI/multiple displays.
- Media/WebView if the application uses them.
- Native libraries do not fail on startup.
- Application image runs without using an external JavaFX SDK.

If `javafx.graphics` or native libraries are missing, errors may appear at launch or only when invoking a specific feature.

## 10. Distribution on Windows

Windows usually supports creating `msi` or `exe` with `jpackage`.

Single-line PowerShell example (assuming the input folder is prepared):

~~~powershell
jpackage --type msi --input build\package-input --dest build\dist --name DeskDemo --main-jar desk-demo.jar --main-class com.example.desktop.DesktopMain --app-version 1.0.0 --vendor "Example Team" --win-menu --win-shortcut
~~~

### 10.1. Installer support tools

On some JDKs, Windows MSI/EXE packaging requires the **WiX Toolset**. The supported WiX version changes by JDK, so you must consult the guide for the exact `jpackage` version being run.

If you encounter a toolchain error stating WiX was not found or its version is incompatible, this is a **native packaging toolchain** error, not a Java source error.

### 10.2. Windows icons

Windows native icons usually use `.ico`:

~~~powershell
jpackage --type app-image --input build\package-input --name DeskDemo --main-jar desk-demo.jar --icon assets\desk-demo.ico
~~~

Do not assume a PNG is a suitable icon format for every installer.

### 10.3. Installation scope and permissions

You may need to decide whether to install:

- Per user.
- Machine-wide.
- Into a fixed install directory.
- With/without shortcuts.
- Whether choosing a directory is allowed if supported.
- Whether admin rights are required.

The application should not require admin rights to write routine config. Store mutable data in a per-user application data directory.

### 10.4. Upgrade identity on Windows

An MSI installer has metadata identifying the product and upgrades. Windows-specific options (such as upgrade identifier, when supported by the JDK) need to be managed consistently across releases if in-place upgrades are desired.

If each release changes the identity randomly, it may create side-by-side installations or fail to replace the old version.

## 11. Distribution on macOS

macOS usually has `app-image` as an app bundle, `dmg`, and `pkg`.

Example:

~~~bash
jpackage \
  --type dmg \
  --input build/package-input \
  --dest build/dist \
  --name DeskDemo \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --app-version 1.0.0 \
  --vendor "Example Team" \
  --icon assets/desk-demo.icns
~~~

### 11.1. Icons and app bundle

macOS icons usually use `.icns`. The bundle has its own internal structure to hold the launcher, runtime, and resources. Do not hardcode project-root paths in the application.

### 11.2. Code signing

To distribute through channels that require it, the app bundle and installer must be signed according to macOS policy. Signing the JAR does not mean the native app bundle is also signed.

Signing certificates/keys need to be protected in the release system; do not put passwords or private keys in Git or terminal logs.

### 11.3. Notarization and Gatekeeper

An outside-App-Store release workflow may require:

1. Creating the app bundle or installer.
2. Signing all components properly.
3. Performing notarization according to Apple's process if the distribution channel requires it.
4. Checking the result and handling errors.
5. Stapling the ticket when appropriate.
6. Testing opening the application on a clean machine with default security policies.

`jpackage` **is not an automated publishing/notarization service**; these steps require the corresponding tools and credentials.

### 11.4. Intel and Apple Silicon

macOS has different CPU architectures. The runtime image, JavaFX modules, and JNI libraries must match. If releasing for multiple architectures, corresponding builds and tests—or a packaging strategy explicitly supported by the platform—are needed.

## 12. Distribution on Linux

Common formats:

~~~bash
jpackage \
  --type deb \
  --input build/package-input \
  --dest build/dist \
  --name desk-demo \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --app-version 1.0.0 \
  --vendor "Example Team" \
  --linux-shortcut
~~~

Or select `--type rpm` with an appropriate build environment.

### 12.1. OS toolchain

DEB/RPM packaging requires the operating system's package-building tools as required by the JDK. There is no guarantee that every distro has the same tools or compatible versions.

You need to check:

- Package builder toolchain.
- Package metadata and naming.
- OS distribution/architecture.
- Shared library dependencies.
- Permissions of the launcher and install directory.
- Desktop environment integration.

### 12.2. Linux is not a single environment

A package that runs on a new Ubuntu is not guaranteed to run on an older Debian or a different Linux distribution. JNI/GUI may depend on libc, X11/Wayland, graphics, fonts, and system libraries.

Publish **supported Linux distributions and versions**, then test on those exact target images.

### 12.3. Package repository

Creating a DEB/RPM file does not automatically provide a package repository, signed repository metadata, or an update channel. If distributing via a repository, additional infrastructure and corresponding security policies are needed.

## 13. Metadata, version, and package identity

Options to manage:

| Metadata | Role |
|---|---|
| `--name` | Application and launcher name |
| `--app-version` | Product version |
| `--vendor` | Publisher |
| `--description` | Description |
| `--copyright` | Copyright notice |
| `--icon` | Native icon |
| OS-specific identifier/package-name | Identifies the application and upgrades |

### 13.1. App version differs from Java runtime version

Example:

~~~text
Application: DeskDemo 2.4.1
Bundled Java runtime: JDK 21, specific update
JavaFX runtime: selected version
jpackage tool: specific version of the JDK
Installer: corresponding Windows MSI build
~~~

You can release a new app version without changing the JDK, or you may need to rebuild alongside the application version policy when updating a Java security patch.

Therefore, a release should record the **app version, Java runtime update, and package checksum**.

### 13.2. Stable identity affects upgrades

Changing the application name, package name, or OS-specific identifier can make the installer treat the new release as a different product. When rebranding or changing channels (stable/beta), you need to intentionally design the identity, install path, and user data handling.

## 14. Launcher options and arguments

`jpackage` allows passing JVM options to the launcher, for example:

~~~bash
jpackage \
  --type app-image \
  --input build/package-input \
  --name DeskDemo \
  --main-jar desk-demo.jar \
  --java-options "-Dapp.environment=desktop"
~~~

The options must be distinguished:

- **`--java-options`:** parameters for the JVM such as `-D...`, GC, or module access flags.
- **`--arguments`:** arguments the application receives via `main(String[] args)`.
- **`--main-class`:** class the launcher needs to invoke.
- **`--module`:** main module/main class if modular.

### 14.1. Do not copy old JVM flags into the new launcher

A Java 8 application may carry GC flags or internal-API options that have been removed on newer JDKs, for example certain CMS flags. When putting that exact string into the launcher, the app image may **fail to start** even though the JAR builds successfully.

You must check JVM flags on the bundled JDK, especially:

- GC selection and GC logging.
- Module opens/exports.
- Encoding/locale.
- Heap limits.
- Native library path.
- Java agents.

Only keep flags with a proven purpose.

### 14.2. Additional launchers

An application may have secondary launchers such as an import tool or diagnostics. Some `jpackage` releases support the `--add-launcher` option pointing to a properties file to declare an additional launcher.

This is a way to organize multiple entrypoints, but you must check the supported syntax/options for the specific JDK. Do not treat an additional launcher as an authorization mechanism: users still need an authorization policy inside the application.

## 15. File associations

A file viewer application can register an extension so users can open documents by double-clicking. `jpackage` supports file associations on suitable OSes/JDKs.

Example conceptual properties file:

~~~properties
extension=demo
mime-type=application/x-desk-demo
description=DeskDemo document
~~~

The properties format, additional fields, and icon of the association must be verified on the target JDK/OS.

### 15.1. Testing associations like a user

- Double-click a file with the registered extension.
- File paths with spaces and Unicode.
- Corrupted files or files not permitted to be opened.
- Multiple opens while the application is already running.
- User changing the default app.
- Does uninstallation remove the association/shortcut appropriately?
- Does the app actually receive the correct path/open event?

Creating an association does not automatically implement file-opening logic in Java; the application needs to handle input appropriately for the launcher/OS.

### 15.2. Do not unreasonably claim common extensions

Registering a file association affects the user's environment. Prefer intentional extensions/MIME types and avoid altering default handlers outside the approved scope.

## 16. The install directory is not the place to write user data

A common migration error is an old application placing the JAR and `settings.properties` file in the same directory, then continuing to write to that directory after using an installer.

This can fail because:

- The install directory only allows administrators to write.
- The installer overwrites application-owned files during upgrade.
- Uninstallation may delete files alongside the package.
- A macOS app bundle has integrity/signing policies.
- Multiple users share one installation but need separate configs.

### 16.1. Categorizing data

| Category | Principled suitable location |
|---|---|
| Read-only JAR/runtime/resources | Install directory |
| User preferences | Per-user config directory |
| User-owned local database | Per-user application data directory |
| Cache | Per-user cache location |
| Logs | Policy-compliant writable directory |
| User-created documents | User-chosen directory |
| Credentials | Appropriate OS credential store/secret manager |
| Shared settings | Organization-managed path with clear permissions |

### 16.2. Conventions by OS

- Windows: per-user AppData area, via an appropriate API/path policy.
- macOS: Application Support area inside the user Library.
- Linux: XDG Base Directory conventions where applicable.

Do not hardcode paths containing usernames or write files into the temp directory without a lifecycle policy.

### 16.3. Resources packaged inside the JAR

If it is a read-only default resource:

~~~java
try (var stream = DesktopMain.class
        .getResourceAsStream("/config/defaults.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Missing defaults");
    }
    // Read data from the stream.
}
~~~

Do not assume the launcher's current working directory is the project root. Mutable files should have a separate data path; do not modify the JAR or install bundle.

## 17. Native dependencies and CPU architecture

A Java desktop application may use:

- JNI/JNA DLL/SO/DYLIB.
- JavaFX graphics native libraries.
- Database native clients.
- Printer/scanner drivers.
- Multimedia codecs.
- Browser embedding engines.
- PKCS#11/HSM clients.
- OS integration bridges.

`jpackage` does not automatically make these libraries portable.

Example:

~~~text
Java bytecode: platform-independent
Windows x64 DLL: architecture-specific
Target runtime: Linux ARM64
~~~

You cannot run a Windows x64 DLL on Linux ARM64 just because the JVM can load Java bytecode.

### 17.1. Checking library paths

If the application uses `System.loadLibrary(...)` or `System.load(...)`, you need to check launcher config, paths, execute permissions, and packaging layout.

Do not rely on a developer having placed the native library in system directories or PATH. A clean user machine may not have those.

### 17.2. JavaFX and media files

A JavaFX application can start up and only fail when opening WebView/media or a scene containing resources. That is why rarely used features must be tested, not just the first screen.

## 18. Installer signing, trust, and security

A native installer downloaded from the Internet may be subject to:

- Code signing policy.
- macOS Gatekeeper/notarization.
- Windows SmartScreen/reputation.
- Enterprise endpoint protection.
- Linux package repository signing.
- Browser download warnings.

**Checksum, code signing, and notarization are different layers.**

| Mechanism | Main question |
|---|---|
| SHA-256 checksum | Has the file changed? |
| Code signing | Is the file tied to a trusted publisher/signing key? |
| Notarization / platform validation | Does the artifact meet the platform verification process? |
| Update signatures | Did the update come from an authorized source? |
| SBOM/provenance | What components are in the artifact, and how was it built? |

Do not put private keys/passwords in the source repository or logging. Signing needs to be integrated into a release pipeline with access control.

### 18.1. Do not fix warnings by disabling OS protections

If users are blocked by Gatekeeper/SmartScreen, the sustainable release solution is verifying signing, notarization, publisher reputation, and the distribution channel. You should not instruct users to turn off all protection mechanisms to make the app run.

## 19. jpackage is not an auto-update system

A generated MSI/DMG/DEB package does not mean the application automatically detects and installs new versions.

If you want auto-update or managed rollout, you need to design:

- Release metadata and version channels.
- Source authentication and update signatures.
- Download, checksum/signature validation.
- OS/CPU compatibility.
- Installer upgrade mechanism.
- User/admin permissions.
- Handling of a running application.
- Rollback plan.
- Data schema migration.
- Update failure logging/telemetry.

For enterprises, you can use device management tools/package repositories appropriate to the OS. For general consumers, a supported updater can be used, but it must undergo a separate security assessment.

### 19.1. Stable upgrade identity

Windows MSI, macOS bundle identifiers, and Linux package names/versions all have semantics that affect upgrades. Do not randomly change product identifiers on every release.

### 19.2. Do not lose data when upgrading

An installer can replace application files without deleting user documents. However, if the local data format/schema changes, the old version may not be able to read it after a rollback.

You need a plan for **data migration, backup, and backward compatibility** beyond just managing installer files.

## 20. Runtime updates and maintenance responsibility

When bundling the Java runtime, the product team is responsible for delivering Java patches to users via application releases.

A JDK patch may fix:

- Security/TLS bugs.
- Certificate validation.
- Runtime/GC defects.
- Charset/locale handling.
- Graphics/font behavior.
- Native library issues.
- HotSpot crashes.

Simply replacing `-jar` or updating system Java is not enough.

### 20.1. Recording release inventory

~~~yaml
product:
  name: DeskDemo
  version: "2.4.1"
target:
  os: "windows"
  arch: "x64"
runtime:
  distribution: "Approved JDK vendor"
  version: "Exact Java update version"
tooling:
  jpackage_version: "Recorded build JDK"
dependencies:
  sbom: "release-sbom.json"
security:
  signed: true
integrity:
  sha256: "Artifact checksum"
~~~

The values are illustrative. Real releases need exact checksums/versions; do not record secrets.

### 20.2. Licensing and redistribution

Rights to distribute the JDK runtime, JavaFX modules, and third-party libraries depend on the licenses of the specific components and vendor. Before releasing:

- Check licenses and redistribution terms.
- Retain required license notices.
- Check native dependencies.
- Generate an SBOM.
- Track CVEs and JDK security updates.

Running the `jpackage` tool does not mean license obligations are automatically handled.

## 21. Multi-OS build pipeline

A typical pipeline:

~~~mermaid
flowchart TD
    A["Tag release and lock dependencies"] --> B["Build + unit/integration tests"]
    B --> C["Prepare JARs, resources, icons"]
    C --> D{"Platform target"}
    D --> E["Windows build agent"]
    D --> F["macOS build agent"]
    D --> G["Linux build agent"]
    E --> H["App image + MSI/EXE"]
    F --> I["App bundle + DMG/PKG"]
    G --> J["App image + DEB/RPM"]
    H --> K["Test + code sign/validate"]
    I --> K
    J --> K
    K --> L["Checksums, SBOM, release manifest"]
    L --> M["Staged release/rollout"]
~~~

### 21.1. Shared parts

- Java code.
- Unit tests.
- Dependency versions/locks.
- Business integration tests.
- Default app metadata.
- Release notes.
- Security scanning.
- Test data.

### 21.2. OS-specific parts

- Installer creation tools.
- Icon formats.
- Native libraries/JavaFX JMODs.
- Signing/notarization.
- Linux package dependencies.
- File associations/shortcuts.
- Target architecture.
- GUI end-user tests.

You should not test only on Linux and declare Windows/macOS supported.

### 21.3. Build reproducibility

Record the JDK/jpackage version, OS build image, target architecture, dependency checksums, build commit, and signing stage. Native installers often contain timestamps/metadata, so **byte-for-byte reproducibility** may require extra configuration beyond locking Java dependencies.

The minimum goal is to be able to reproduce a release from a list of inputs and approved tools.

## 22. UI regressions when changing the bundled JDK

GUI code still compiles, but desktop behavior can change due to the new runtime:

- Font fallback and shaping for Vietnamese.
- High-DPI scaling.
- Multiple monitors.
- Input Method Editor.
- Theme/look-and-feel.
- File dialogs.
- Printing.
- Clipboard/drag-and-drop.
- JavaFX rendering.
- Default charset and locale.
- Timezone/TZDB.
- TLS/truststore when connecting to the backend.
- Native integration.

Therefore, a `main()` check that does not throw an exception is not enough.

### 22.1. Legacy files and charsets

An old Java application might write config/CSV using the default charset on Windows. When the new bundled runtime uses a different charset rule, reading old files can produce garbled characters.

You must determine the **actual charset of historical data**, convert it in a verified way, and use an explicit charset for new data.

### 22.2. TLS and backend APIs

Upgrading the JDK runtime can change the truststore and restricted TLS algorithms. If the desktop app loses backend connectivity, you need to distinguish among network/proxy errors, server certificates, TLS policy, and app packaging. Do not disable certificate verification as a quick fix.

## 23. Migration scenario from Java 8 and scripts to jpackage

Suppose an internal point-of-sale application:

- Is compiled with Java 8.
- Runs via `run.bat`.
- Requires users to install a JRE themselves.
- Uses Swing, JDBC, and a PDF library.
- Stores `settings.properties` next to the JAR file.
- Distributes new versions by overwriting the JAR.

Goal: use a newer JDK, have an OS-specific installer, and include a bundled runtime.

### Step 1 — Capture a baseline

Record the current JDK, runtime dependencies, native libraries, startup options, user data storage, and list of supported OS/CPUs.

### Step 2 — Upgrade code/dependencies

Check drivers, TLS, logging, the PDF library, charsets, and UI behavior on the target JDK. Do not combine this with replacing the entire UI framework if the goal is only packaging.

### Step 3 — Standardize application input

Create a main JAR with an entrypoint, copy runtime dependencies/resources, and manage versions via the build tool.

### Step 4 — Create an app image

Run `jpackage --type app-image` and test the launcher on a clean machine. If the runtime image is minimized, also test JDBC, PDF printing, and features that use reflection.

### Step 5 — Move mutable config

Move data out of the install directory to a per-user location; provide migration/backup for old user data.

### Step 6 — Create the installer

Build Windows/macOS/Linux on the appropriate hosts, prepare icons, package identifiers, and sign according to policy.

### Step 7 — Test upgrading

Install the old version, create data, upgrade to the new version, and verify config and documents remain intact. If rollback is possible, check data backward compatibility.

### Step 8 — Release

Include checksums, release manifest, Java runtime version, supported OS matrix, and support/uninstall instructions.

## 24. Diagnosing common errors

| Symptom | Possibility | How to handle |
|---|---|---|
| `jpackage: command not found` | Tool is missing from JDK/PATH | Confirm JDK version and path |
| `Unsupported package type` | Selected installer format wrong for OS/build | `jpackage --help` on the host |
| Windows installer build fails | WiX/toolchain missing or mismatched | Read exact JDK requirements |
| Launcher cannot find main class | Wrong JAR/module/entrypoint | Check `--main-jar`, `--module`, manifest |
| `NoClassDefFoundError` | Missing runtime dependency/module | Input dir, classpath, jlink runtime |
| `ServiceConfigurationError` | Missing provider/SPI | Service descriptors, module resolution |
| `InaccessibleObjectException` | JPMS reflection | `opens` and framework support |
| JavaFX native error | OS/architecture dependency mismatch | Platform-specific JavaFX libs |
| App runs in IDE but not app image | Hidden environment dependency | Test on clean machine, inspect output |
| Cannot write config | App writes to install directory | Use per-user writable dir |
| Broken Unicode | Charset/font | Inspect raw bytes and font fallback |
| Windows warning | Signing/reputation | Check code-signing policy |
| macOS blocks | Signing/notarization | Check Gatekeeper and release process |
| Upgrade creates a second installation | Identity/version mismatch | Check installer metadata |
| Linux fails to load library | Missing ABI/system deps | Test distro/architecture and native libs |
| Uninstall loses user data | Data stored in install directory | Fix data location and migration |

### 24.1. Layering errors to avoid misdirected fixes

- **Build/compile:** source, classpath, JDK toolchain errors.
- **Packaging:** missing installer tools, icons, version metadata.
- **Launcher:** wrong main class/module or JVM options.
- **Runtime:** missing module, JAR, provider, native lib.
- **OS trust:** signing, notarization, permissions.
- **Upgrade:** package identity, data migration, update process.

Do not randomly add JVM flags or copy JARs when the actual error is WiX or OS signing.

## 25. Release testing matrix

| Axis | Scenario | Verification |
|---|---|---|
| OS | Published Windows/macOS/Linux targets | Install and launcher |
| CPU | Supported x64/ARM64 | Correct runtime and native libs |
| Runtime | Target bundled JDK version | Startup, sufficient modules |
| UI | Swing/JavaFX | Rendering, keyboard, DPI |
| Permissions | Standard user | Config/logs writable |
| Charset | Vietnamese/Unicode | No corrupted data |
| Network | Online/offline, TLS | Connection and error handling |
| Local data | Existing data from old version | Upgrade preserves data |
| File association | Double-click file | App opens the correct document |
| Signing | Artifact downloaded from real channel | OS trust policy |
| Native integration | Printing/device/JNI | Real functionality |
| Uninstall | Complete removal | Per policy, no loss of user documents |
| Clean machine | No system JDK | Bundled runtime works |

### 25.1. Testing through the user lifecycle

1. Download the installer from the distribution channel.
2. Verify the file according to policy.
3. Install with real user permissions.
4. Open from the OS launcher/menu.
5. Use key features.
6. Close/reopen.
7. Upgrade from an older version.
8. Check data.
9. Uninstall.
10. Check file associations/shortcuts.

Running an application from a developer's terminal cannot replace this lifecycle.

## 26. Common misconceptions

### 26.1. “jpackage turns an application into JVM-independent machine code”

Not true. The Java runtime is usually packaged together with the application.

### 26.2. “Bundled Java means zero OS dependencies”

False. Native libraries, system graphics/fonts, and OS ABI still matter.

### 26.3. “Having jpackage means every JDK automatically includes JavaFX”

False. JavaFX requires matching dependencies and native runtime.

### 26.4. “Use one build host to create all installers”

Not the normal native packaging model. OS-specific builds are required.

### 26.5. “If the app image runs, the installer is definitely fine”

Not enough. Signing, permissions, shortcuts, file associations, and upgrades need separate testing.

### 26.6. “A desktop app writing config in the install directory is normal”

This easily breaks permissions and data during upgrade/uninstall.

### 26.7. “Having MSI/DMG means it can auto-update”

No. `jpackage` does not provide a complete cross-platform auto-update system.

### 26.8. “Only changing the app version is enough for an in-place upgrade”

Valid package identity and installer upgrade metadata are needed.

### 26.9. “A Java update on the user's machine automatically patches the app's runtime”

Not reliably when the app carries its own bundled runtime.

### 26.10. “The smaller the JDK runtime image, the better”

An image that is too small may miss dynamic modules/providers.

### 26.11. “Only testing Windows/macOS in the IDE is enough”

Not enough; the artifact must be run on a clean machine and tested via installation.

### 26.12. “Disabling Gatekeeper/SmartScreen is the way to handle signing errors”

Not a safe distribution approach.

### 26.13. “Every OS shares the same icon file”

False. Icon formats/conventions differ.

### 26.14. “Copy Java 8 GC flags to the new bundled JDK”

May prevent the launcher from starting due to deprecated/removed options.

### 26.15. “jpackage automatically manages licenses/SBOM”

No. That is a separate responsibility of the release process.

## 27. Pre-publish checklist

### Application

- [ ] Main class or module is clearly identified.
- [ ] Runtime JARs/resources are fully gathered.
- [ ] App runs outside the IDE.
- [ ] Platform-appropriate JavaFX modules/native libs if used.
- [ ] No paths relative to the project root used at runtime.
- [ ] Appropriate startup logging with no secrets.

### Runtime

- [ ] `jpackage` JDK version is recorded.
- [ ] Runtime image/JDK update is approved.
- [ ] Custom modules/providers are sufficient for workflows.
- [ ] JVM options are compatible with the new JDK.
- [ ] Licenses and redistribution conditions have been reviewed.
- [ ] Bundled runtime tested when the machine has no system JDK.

### Installer

- [ ] Created app image and launched it successfully.
- [ ] Created native package for the right OS/architecture.
- [ ] Icons in the right format.
- [ ] Stable metadata/identifier/version.
- [ ] WiX/OS packaging tools at the right version if needed.
- [ ] Signing/notarization per release channel.
- [ ] Shortcuts/menus/file associations tested.
- [ ] Install and uninstall with policy-compliant permissions.

### Data and updates

- [ ] Config/logs/user documents are not stored in the install dir.
- [ ] Upgrades retain data.
- [ ] Old data has migration/backup when format changes.
- [ ] Update source is authenticated and integrity-checked.
- [ ] Rollback compatible with data and installer.
- [ ] Record runtime version, checksum, and SBOM when needed.

### Desktop QA

- [ ] Tested actual OS/CPU matrix.
- [ ] Tested Unicode, Vietnamese, fonts/DPI.
- [ ] Tested offline/network/TLS.
- [ ] Tested printing/JNI/device integration when used.
- [ ] Tested startup on a standard user account.
- [ ] Tested clean install and upgrade.
- [ ] Tested uninstall and leftover files per policy.
- [ ] Release notes and support diagnostics available.

## Conclusion

`jpackage` helps move Java desktop applications from a system-JRE-dependent JAR distribution model to **an application image and native installer carrying its own Java runtime**. It supports launchers and packaging on Windows, macOS, and Linux; however, a successful build does not yet guarantee the application runs properly on every client machine.

A reliable migration strategy is: **identify the main application and dependencies → create an app image → verify runtime modules/JavaFX/native libraries → create installers on the right OS/CPU → sign and verify → test install, upgrade, uninstall, and user-data preservation → release with runtime version, checksum, and update plan**. When packaging is treated as part of environment compatibility, the development team can upgrade the JDK while keeping the desktop experience stable, secure, and supportable.
