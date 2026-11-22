# JavaFX and Separately Distributed Desktop Components

When upgrading a Java desktop application from an older JDK to a newer JDK, errors do not come only from syntax or deprecated APIs. Certain UI technologies previously bundled with some JDK distributions have now become **independently released components**. The most common situation is a JavaFX application that previously compiled and ran with Oracle JDK 8, yet after moving to JDK 17 or JDK 21 the compiler cannot find the `javafx.*` packages, or the application fails on startup with a message that JavaFX runtime components are missing.

This does not mean Java no longer supports desktop applications. AWT and Swing remain in Java SE's standard `java.desktop` module in modern JDKs. **JavaFX is a different case:** JavaFX/OpenJFX has been released and managed independently of the JDK since the JDK 11 generation. Legacy desktop deployment technologies such as Java Web Start/JNLP from the traditional Java Deployment stack are also no longer distributed as before in modern Oracle JDKs. These differences require the migration team to review **UI libraries, native runtimes, build tools, launchers, and installers**, rather than merely changing the `JAVA_HOME` variable.

This lesson explains the distribution history, how to identify dependencies to migrate, Maven/Gradle configuration, JPMS handling, packaging applications for Windows/macOS/Linux, common errors, and the compatibility verification workflow when upgrading the JDK.

## 1. Separating Three Concepts: JDK, UI Framework, and Application Distribution

A Java desktop application typically consists of multiple layers:

~~~text
Business application code
          |
          v
UI framework: JavaFX / Swing / SWT
          |
          v
Java SE APIs + Java runtime (JDK/JRE or runtime image)
          |
          v
Native libraries, graphics toolkit, font/media/web engine
          |
          v
Packaged application: launcher, installer, updater
          |
          v
Operating system, CPU architecture, display server
~~~

Each layer has its own lifecycle and release policy. Choosing JDK 21 as the runtime does not automatically determine the JavaFX version, and the selected JavaFX version does not determine how the application is installed on a user's machine.

- **JDK:** the Java toolkit and runtime, containing the `javac` compiler, `java` launcher, Java SE modules, and tools such as `jlink` and `jpackage` (depending on the JDK version).
- **JavaFX/OpenJFX:** a set of libraries for building graphical user interfaces including scene graph, controls, CSS, FXML, animation, media, WebView, and other integrations.
- **Java SE desktop APIs:** such as AWT, Swing, Java2D, Java Sound, and image I/O in `java.desktop`; these should not be conflated with JavaFX.
- **Desktop distribution:** how the runtime, JARs, native libraries, icons, launchers, update configuration, and installers are delivered to user machines.
- **Auxiliary tools:** such as JavaFX Scene Builder, IDE integrations, profilers, and launchers/updaters. They may be released independently or are no longer included in the JDK.

When surveying an existing system, identify exactly which layer is the source of dependency. A pure Swing application does not need to add JavaFX just because it is a desktop application. Conversely, an application using `JFXPanel` to embed JavaFX inside Swing still needs the JavaFX libraries even if most screens are written in Swing.

## 2. How JavaFX Distribution Changed Across JDK Generations

### 2.1. The Java 8 Application Era

Many JavaFX applications were built with Oracle JDK 8 because JavaFX was included in that distribution. Developers could import `javafx.application.Application`, run the application, and use IDE tools without managing JavaFX dependencies as a separate set of Maven libraries.

However, **not every OpenJDK 8 distribution included JavaFX the same way**. Some vendors packaged or supported JavaFX differently. Therefore, do not assume that "any JDK 8 has JavaFX"; you must check the exact vendor and build in use.

### 2.2. Java 9/10 and the Transition Period

In Java 9 and 10, moving to the module system introduced a module-based view of desktop components. Even so, JavaFX packaging history must be examined per vendor. Applications that used JavaFX internal packages or build tools relying on the old JDK directory layout could encounter risks even during this transition period.

### 2.3. Since JDK 11: JavaFX Is a Separate Dependency

The key turning point for migration is that **JavaFX is no longer bundled with Oracle JDK 11**. OpenJFX continues to be developed and released as separate modules/libraries. Applications wanting to use JavaFX on JDK 11 and later must add the appropriate artifacts or corresponding JavaFX SDK/runtime.

Example:

~~~java
import javafx.application.Application;
import javafx.scene.Scene;
import javafx.scene.control.Label;
import javafx.stage.Stage;
~~~

These imports do not reside in the Java SE modules of an ordinary JDK 21. If the project does not declare JavaFX dependencies or an appropriate module path, simply upgrading the compiler/JDK will lead to build errors.

When reading documentation, distinguish:

- **JDK version** that the application uses to compile/run.
- **OpenJFX/JavaFX version** compatible with that JDK.
- **JavaFX SDK, Maven artifacts, or JMODs** selected for compiling/packaging.
- **Operating system and CPU architecture** of the native JavaFX libraries.
- **Gradle/Maven plugin version** used to resolve and package the application.

Do not assume the JDK and JavaFX share the same version number or must upgrade on the same schedule. What matters is that the vendor confirms the specific combination is supported.

## 3. Desktop Components Still in the JDK and Components Requiring Separate Management

| Component | Architectural Location | What to Check When Upgrading the JDK |
|---|---|---|
| AWT | Java SE, module `java.desktop` | Desktop environment, fonts, rendering, headless mode |
| Swing | Java SE, module `java.desktop` | Look and feel, EDT, HiDPI, Java2D, integration |
| Java Sound and image APIs | Primarily Java SE desktop APIs | Supported codecs/formats, resource sources, and native environment |
| JavaFX Controls / Graphics | Separate OpenJFX | JavaFX version, module path, native runtime |
| JavaFX FXML | Separate OpenJFX | `javafx.fxml`, controller reflection, and `opens` |
| JavaFX Media / WebView | Separate OpenJFX | Native libraries, codecs/WebKit, and platform support |
| JavaFX ↔ Swing bridge | OpenJFX `javafx.swing` | JDK `java.desktop`, UI threads, event delivery |
| SWT | Separate Eclipse library | OS/architecture artifacts and native bindings |
| JavaFX Scene Builder | Independently released UI design tool | Compatible Scene Builder and FXML versions |
| Traditional Java Web Start/JNLP | Legacy Java Deployment technology | Replacement launcher/updater option; do not expect modern JDKs to include `javaws` |
| `jlink` / `jpackage` | Tools in supporting JDKs | Module graph and how runtime images/installers are built |

The table describes management responsibility; it does not assert that every feature of each framework is available on every OS or vendor. For example, JavaFX Media and JavaFX Web may have limitations or native differences on individual platforms.

### 3.1. AWT/Swing Were Not Removed Along with JavaFX

A common misconception is that "Java 11 dropped Java desktop". That is false. Packages such as `javax.swing.*` and `java.awt.*` remain part of Java SE in the `java.desktop` module.

Swing application:

~~~java
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;

public class SwingExample {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Desktop");
            frame.add(new JLabel("Swing vẫn thuộc java.desktop"));
            frame.setSize(400, 160);
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setVisible(true);
        });
    }
}
~~~

For a named module, declare:

~~~java
module com.acme.swingapp {
    requires java.desktop;
}
~~~

There is no need to add `javafx.controls` if the application does not actually use JavaFX.

### 3.2. JavaFX Is a Separate Library, Not a Java SE API

JavaFX uses the `javafx.*` namespace, yet that namespace does not mean it is provided by a newer JDK. Some desktop distributions may pre-package JavaFX or provide custom runtimes, but you must not rely on that when building portable artifacts.

The project should declare an explicit JavaFX version and manage it as a true dependency.

## 4. Important OpenJFX Modules

JavaFX is split into multiple modules so you can select the functionality you need:

| JavaFX Module | Typical Role |
|---|---|
| `javafx.base` | Properties, bindings, collections, foundational utilities |
| `javafx.graphics` | Application, Stage, Scene, scene graph, animation, rendering |
| `javafx.controls` | Button, TableView, TreeView, Menu, built-in controls |
| `javafx.fxml` | Loading FXML interfaces and controller binding |
| `javafx.media` | Audio/video via the supported media stack |
| `javafx.web` | WebView/WebEngine and web rendering |
| `javafx.swing` | Integrating JavaFX with Swing, such as `JFXPanel` and `SwingNode` |
| `javafx.swt` | Integrating with SWT when supported by the distribution |

An application using only `Button` and `Scene` may declare just `javafx.controls` with transitive dependencies resolved by the module graph. An application using FXML needs `javafx.fxml`. If media or WebView is not used, do not add `javafx.media` / `javafx.web` just for "completeness", as they can add native components and increase distribution size.

The required module scope must be based on source code and actual flows. Frameworks may use a module indirectly; for example, a UI wrapper library might read FXML or embed WebView even if the main source does not directly import `javafx.fxml`.

### 4.1. Native Libraries Bundled with JavaFX

Some JavaFX features use native code to interact with the operating system, GPU, media, and web engine. Therefore, JavaFX artifacts can have platform/architecture-specific parts.

Points to verify:

- Windows, macOS, Linux, and the JavaFX platforms supported by the vendor.
- CPU architecture, for example x86-64 versus AArch64.
- Native artifacts accompanying the corresponding JavaFX version.
- Required system libraries, graphics stack, and media codecs.
- Native binaries actually packaged into the final installer or runtime image.
- Code signing constraints, notarization, and OS security policies.

A build that runs on a Windows developer machine does not prove that native libraries exist for macOS or Linux. Cross-platform releases must be verified on the exact OS/CPU combinations or via corresponding pipelines.

## 5. Inventorying the Desktop Application Before Upgrading the JDK

Before selecting a JavaFX version, create a complete inventory:

1. **Legacy runtime:** JDK/JRE vendor, version, update, OS/architecture.
2. **UI framework:** JavaFX, Swing, AWT, SWT, or a combination.
3. **JavaFX modules used:** controls, fxml, media, web, swing...
4. **Internal JavaFX packages:** `com.sun.javafx.*` or non-public implementation APIs.
5. **Third-party libraries:** controls libraries, chart libraries, FXML utilities, CSS themes, testing libraries.
6. **Build:** Maven/Gradle/Ant, JavaFX plugins, compiler release, annotation processors.
7. **Launch:** `java` command, IDE run configuration, `javaws`, shortcuts, updaters, or native launchers.
8. **Packaging:** JAR, fat JAR, runtime image, EXE/MSI/DMG/PKG/DEB/RPM depending on the system.
9. **Native dependencies:** JavaFX native libraries, JNI, codecs, fonts, WebKit, media.
10. **Resources:** FXML, CSS, fonts, images, icons, localization files, and configuration files.
11. **Thread model:** JavaFX Application Thread, Swing EDT, executors, background services.
12. **Deployment:** auto-update, code signing, certificates, OS policies, data write permissions.
13. **Test matrix:** physical machines, HiDPI, GPU, multiple monitors, locale, dark mode, accessibility.

Create an illustrative table:

| Item | Current | Target | Action |
|---|---|---|---|
| JDK | Oracle JDK 8 | Organization-approved JDK | Verify compatibility |
| JavaFX | Previously bundled with old JDK | Separate OpenJFX dependency | Choose version/platform |
| FXML | Resource in JAR | Remains in new artifact | Check `opens` and resource paths |
| Installer | Old script or Web Start | Native installer/runtime image | Design deployment |
| Libraries | Old controls library | Version supporting target JDK/JavaFX | Upgrade dependencies/test |
| Media/Web | Present or absent | Depends on actual features | Check native support |

Version numbers in a real project must come from deployed artifacts and configurations. Do not use a "Java 8 to 21" milestone as automatic proof that every component needs replacement.

## 6. Accurately Identifying JavaFX Dependencies

### 6.1. Inspecting Imports and Resources

Some common indicators in source code:

~~~text
javafx.application.Application
javafx.stage.Stage
javafx.scene.Scene
javafx.scene.control.*
javafx.fxml.FXML
javafx.fxml.FXMLLoader
javafx.scene.web.WebView
javafx.scene.media.MediaPlayer
javafx.embed.swing.JFXPanel
javafx.embed.swing.SwingNode
~~~

Also check:

~~~text
*.fxml
*.css
*.png / *.svg / fonts
META-INF/services/*
native binaries
launcher scripts
~~~

Do not search only for imports: a screen may be declared entirely in FXML or loaded dynamically by resource name. In some cases JavaFX is loaded via reflection by a framework, so direct import searches do not reflect the full picture.

### 6.2. Distinguishing Public APIs from Internal APIs

Documented public packages are the preferred choice. If the application uses:

~~~java
import com.sun.javafx.some.internal.Type;
~~~

then the code depends on implementation details; newer JDK/JavaFX versions may change, encapsulate, or remove those classes. Do not simply add `--add-exports` or `--add-opens` and consider the migration finished.

Remediation approaches:

- Find an equivalent public JavaFX API.
- Upgrade libraries that depended on internal APIs to versions supporting the newer JavaFX.
- If no replacement API exists, consider changing the component/design.
- If a temporary workaround is unavoidable, restrict its scope and clearly document the reason and removal deadline.
- Check binary compatibility of third-party JavaFX dependencies, especially custom skins, controls, or renderers.

## 7. Choosing the Right Combination of JDK, JavaFX, and Build Tools

No single matrix applies to every project. At a minimum, record:

| Dimension | What to Confirm |
|---|---|
| JDK feature release | Planned compiler and runtime versions |
| JDK vendor/update | Build, support schedule, and patches |
| JavaFX version | Minimum/supported JDK, release notes |
| JavaFX modules | Features actually needed |
| Build tool | Maven/Gradle and version supporting target JDK |
| JavaFX build plugin | Plugin version compatible with build tool/JavaFX |
| OS and CPU | Native artifacts and platform compatibility |
| Installer | `jpackage`/`jlink`/launcher supporting the distribution format |

### 7.1. Do Not Equate JavaFX Version with JDK Version

JavaFX release names typically reflect their own release cycle. A JavaFX version may support a suitable set of JDKs, but you should not infer that:

- JDK 21 must use JavaFX 21.
- The latest JavaFX always runs on an older JDK.
- JavaFX with the same release number as the JDK will work on every operating system.
- A JavaFX dependency that compiles is sufficient for native startup to succeed.

Read the release notes and runtime requirements for the exact OpenJFX/vendor release. Pay special attention to security patch updates and the support status of long-term support releases if offered by the vendor.

### 7.2. Choose a Clear JavaFX Provisioning Approach

Common approaches:

- **Maven Central/Gradle dependencies:** use `org.openjfx` modules and plugins to resolve platform-appropriate artifacts.
- **Separate JavaFX SDK:** specify the path to the JavaFX SDK `lib` directory in the launch command or IDE.
- **JavaFX JMODs/runtime image:** use appropriate modules to build a runtime image with `jlink` and packaging tools.
- **Commercially supported or custom JavaFX distributions:** follow the corresponding documentation and licensing terms.

Do not arbitrarily mix JARs from Maven with native libraries from a different SDK version. This can lead to linking failures, `UnsatisfiedLinkError`, or hard-to-reproduce rendering bugs.

## 8. Minimal JavaFX Application Example

Suppose the application has the class:

~~~java
package com.acme.desktop;

import javafx.application.Application;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.layout.StackPane;
import javafx.stage.Stage;

public final class DesktopApp extends Application {
    @Override
    public void start(Stage stage) {
        Button button = new Button("Mở báo cáo");
        button.setOnAction(event ->
                System.out.println("Đã nhấn"));

        stage.setScene(new Scene(new StackPane(button), 420, 240));
        stage.setTitle("Desktop Migration");
        stage.show();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
~~~

The goal of the snippet is to show the library path and minimal lifecycle. It uses `javafx.application.Application` and `javafx.scene.control.Button`, meaning it requires the corresponding JavaFX modules. On a JDK without bundled JavaFX, running `javac` without JavaFX dependencies will fail.

### 8.1. Running with the JavaFX SDK for a Classpath Application

With a JavaFX SDK downloaded for the right OS/CPU and a version supporting the JDK:

~~~bash
java --module-path /path/to/javafx-sdk/lib \
     --add-modules javafx.controls \
     -cp build/classes \
     com.acme.desktop.DesktopApp
~~~

The command illustrates Linux/macOS; on Windows adjust paths and shell syntax. The paths must point to the directory containing the actual JavaFX JARs. For large projects, let Maven/Gradle or a launcher manage the classpath/module path instead of hardcoding an SDK directory on a developer's machine.

A message like "JavaFX runtime components are missing" typically indicates a launch/configuration issue, yet you should check the stack trace and actual launch command before concluding the sole cause is a missing JAR.

## 9. Gradle Configuration for OpenJFX

With Gradle and the Java plugin, a common approach is to use the JavaFX Gradle plugin selected and version-pinned by the project. Structural example:

~~~groovy
plugins {
    id 'application'
    id 'org.openjfx.javafxplugin' version 'PLUGIN_VERSION'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

javafx {
    version = 'COMPATIBLE_JAVAFX_VERSION'
    modules = ['javafx.controls', 'javafx.fxml']
}

application {
    mainClass = 'com.acme.desktop.DesktopApp'
}
~~~

`PLUGIN_VERSION` and `COMPATIBLE_JAVAFX_VERSION` are placeholders to replace with verified versions, not real values to copy into production. The configuration above describes an application **without a module descriptor**. For modular applications, declare the corresponding main module and verify support across the plugin version, Gradle, and toolchain.

Key points:

- `application` manages the entrypoint and run/distribution tasks.
- Java toolchain determines the JDK used for compilation.
- The JavaFX plugin helps manage the selected JavaFX modules.
- `javafx.controls` and `javafx.fxml` are declared according to features.
- Build output must be tested on an OS with appropriate native dependencies.

### 9.1. Separating Toolchain and Target Release

A project may run Gradle on one JDK, compile with a different toolchain, and set Java `--release` to match the minimum runtime. However, JavaFX APIs are not Java SE APIs automatically provided by `--release`. Setting `options.release = 17` does not make JavaFX available; you still need the dependency for the right JavaFX version.

If you compile the application on JDK 21 but need to run on JDK 17, verify that the selected JavaFX version supports the JDK 17 runtime, rather than checking only the application's class file target. JavaFX JARs themselves also have Java/classfile version requirements and native compatibility constraints.

## 10. Maven Configuration for OpenJFX

With Maven, `org.openjfx` dependencies and an appropriate plugin are commonly used to run the application. Example of the main section of `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-controls</artifactId>
        <version>COMPATIBLE_JAVAFX_VERSION</version>
    </dependency>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-fxml</artifactId>
        <version>COMPATIBLE_JAVAFX_VERSION</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.openjfx</groupId>
            <artifactId>javafx-maven-plugin</artifactId>
            <version>COMPATIBLE_PLUGIN_VERSION</version>
            <configuration>
                <mainClass>com.acme.desktop.DesktopApp</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The snippet above is an illustrative structure, not a complete POM. JavaFX/Maven plugin versions must be chosen from compatibility documentation. For modular applications, adjust `mainClass`, the module descriptor, and how the Maven plugin constructs the launch command accordingly.

Some projects do not use the JavaFX Maven plugin, instead declaring dependencies and manually configuring Surefire, packaging, and launchers. That can work, provided you check compile classpath, runtime module path, native artifacts, and the final distribution thoroughly.

### 10.1. Avoiding Misconfigured Fat JARs

A common mistake is bundling all JavaFX JARs together with native binaries into a fat JAR using arbitrary shading rules. If module descriptors, service metadata, native libraries, or platform-specific artifacts are handled improperly, the application may build successfully yet fail at runtime.

Do not assume that "a single JAR containing everything" is the best distribution method for a JavaFX application. A runtime image or application distribution with platform-appropriate native libraries, a launcher, and complete metadata is usually required.

## 11. JavaFX with JPMS: module-info.java, exports, and opens

When the application becomes an explicit named module, declare module dependencies:

~~~java
module com.acme.desktop {
    requires javafx.controls;
    requires javafx.fxml;

    exports com.acme.desktop;

    opens com.acme.desktop.ui to javafx.fxml;
}
~~~

Meaning:

- `requires javafx.controls`: the application uses public APIs of JavaFX Controls and its accompanying module dependencies.
- `requires javafx.fxml`: the application uses the FXML loader.
- `exports com.acme.desktop`: exposes necessary APIs of that package to modules that read the application.
- `opens com.acme.desktop.ui to javafx.fxml`: allows the FXML loader to access controller fields/methods in the UI package via reflection at runtime.

The module descriptor must match the packages in source and how the framework initializes the application. Do not blindly export every package just to avoid errors; in many cases conditional `opens` to FXML is needed, not `exports`.

### 11.1. Why Does FXML Often Fail When Modularizing?

FXML can declare a controller and bind fields/methods annotated with `@FXML`:

~~~java
package com.acme.desktop.ui;

import javafx.fxml.FXML;
import javafx.scene.control.Label;

public final class DashboardController {
    @FXML
    private Label statusLabel;

    @FXML
    private void onRefresh() {
        statusLabel.setText("Đã cập nhật");
    }
}
~~~

The FXML loader uses reflection to instantiate controllers, inject fields, and invoke handlers. When a class belongs to a named module, reflective access rights are no longer the same as in an unnamed module. If the package is not opened (`opens`) to `javafx.fxml`, loading can fail with a `LoadException` or an underlying access error.

The preferred solution is to open **the exact controller package**:

~~~java
opens com.acme.desktop.ui to javafx.fxml;
~~~

Do not use `open module ...` merely because one controller needs injection. Nor should you simply change `private` fields to `public` if doing so unnecessarily breaks encapsulation.

### 11.2. JavaFX Web, Media, and Swing Bridge in the Module Graph

If the application uses these components, add the corresponding modules:

~~~java
module com.acme.desktop {
    requires javafx.controls;
    requires javafx.fxml;
    requires javafx.web;
    requires javafx.media;
    requires javafx.swing;
    requires java.desktop;
}
~~~

This is an example for an application using all those feature groups, **not a configuration to apply to every application**. With the Swing bridge, `java.desktop` still belongs to the JDK while `javafx.swing` belongs to separate OpenJFX. Verify transitive dependencies and native requirements according to the selected distribution.

### 11.3. Do Not Arbitrarily Mix Classpath and Module Path

A non-modular application can sit on the classpath and load JavaFX named modules via `--module-path` / `--add-modules`. When the application becomes a named module, properly configure `requires`, root modules, class loaders, and unmodularized libraries.

If a third-party JavaFX library still remains only on the classpath, a named module cannot declare `requires` directly to the unnamed module. A temporary bridge or automatic module may be needed, provided you check module names, split packages, reflection, and runtime behavior.

## 12. Resource Loading: FXML, CSS, Fonts, Images

Many failures when moving to a newer JavaFX/JDK involve resource files rather than Java code.

Common layout:

~~~text
src/main/java/com/acme/desktop/DesktopApp.java
src/main/java/com/acme/desktop/ui/DashboardController.java
src/main/resources/com/acme/desktop/ui/dashboard.fxml
src/main/resources/com/acme/desktop/styles/main.css
src/main/resources/com/acme/desktop/images/logo.png
~~~

Use `Class.getResource` with the appropriate path:

~~~java
URL fxml = DesktopApp.class.getResource(
        "/com/acme/desktop/ui/dashboard.fxml");

if (fxml == null) {
    throw new IllegalStateException("Thiếu dashboard.fxml trong artifact");
}

Parent root = FXMLLoader.load(fxml);
~~~

For CSS:

~~~java
URL css = DesktopApp.class.getResource(
        "/com/acme/desktop/styles/main.css");

if (css != null) {
    scene.getStylesheets().add(css.toExternalForm());
}
~~~

Points to check:

- Files are actually copied from `src/main/resources` into the JAR or runtime image.
- Whether the path in `getResource` is accurate; `Class.getResource("/...")` differs from `ClassLoader.getResource("...")` in how `/` is interpreted.
- Whether a named module has resource packages that are encapsulated.
- Whether FXML contains `fx:controller` referencing the right class/package.
- Whether CSS `@import`, image URLs, and fonts use valid relative paths.
- Whether case-sensitive filenames match across Windows and Linux.
- When using `jlink`/`jpackage`, whether resources are present in the final image.

Do not convert a resource `URL` directly into a `File`. Resources inside a JAR or runtime image do not necessarily have an ordinary filesystem path. Use streams or resource APIs to read data.

## 13. JavaFX Application Lifecycle and UI Thread

Upgrading the JDK/JavaFX can surface latent threading bugs. JavaFX has the **JavaFX Application Thread** dedicated to handling the scene graph and related UI interactions. It differs from the **Swing Event Dispatch Thread (EDT)**.

Key `Application` lifecycle milestones:

1. `init()`: prepares the application before the UI runs.
2. `start(Stage)`: entrypoint that creates the scene and displays the stage on the JavaFX Application Thread.
3. `stop()`: cleanup when the application shuts down according to its lifecycle.

Updating the UI from a background thread requires dispatching work back to the JavaFX Application Thread:

~~~java
CompletableFuture.supplyAsync(() -> loadReport())
        .thenAccept(report ->
                Platform.runLater(() -> statusLabel.setText(report)));
~~~

This is a conceptual example. `loadReport`, `statusLabel`, and imports are omitted in the abbreviated snippet. In a real application, also handle errors, cancellation, and cases where the Stage closes before the callback executes.

Do not perform slow I/O or CPU-intensive work directly inside `start`, event handlers, or `Platform.runLater`, as that freezes the UI. Use `Task`, `Service`, executors, or appropriate concurrency mechanisms.

### 13.1. Combining JavaFX and Swing

JavaFX supports bridging with Swing through components such as `JFXPanel` and `SwingNode`. However, the two frameworks have different event threads.

Example update pattern:

- Swing UI: operate on the EDT using `SwingUtilities.invokeLater`.
- JavaFX UI: operate on the JavaFX Application Thread using `Platform.runLater`.
- When passing data between the two UI toolkits, avoid holding locks simultaneously or synchronously waiting across both event threads.

Do not treat `javafx.swing` as a way to merge event threads. Migrating dependencies to a new JavaFX version requires checking deadlocks, focus, keyboard input, window ownership, HiDPI, and popup behavior in hybrid screens.

## 14. JavaFX Media, WebView, and Codecs

`javafx.media` and `javafx.web` are two areas especially sensitive to the runtime environment because they contain native components or complex engines.

### 14.1. Media

Issues that can appear:

- Codec or container format unsupported on a given OS.
- Native media library missing from packaging.
- Audio/video device unavailable in a test runner or container.
- Media source using an unsupported protocol/path.
- Changes in the native pipeline, drivers, or system dependencies.

Do not assume JavaFX Media supports all popular codecs; check the list of formats/codecs supported by the specific JavaFX/vendor build and test real files.

### 14.2. WebView

`WebView` embeds a web engine. This feature can be affected by HTML/CSS/JavaScript support, TLS/certificates, cookies/sessions, CORS, and security changes in the engine shipped with JavaFX.

When upgrading JavaFX:

- Test real internal web pages, especially login, redirects, upload/download, and JavaScript bridges.
- Check the WebView version/engine in JavaFX release notes.
- Restrict exposing sensitive Java objects to untrusted web content.
- Test compatibility with proxies, CAs, and network policies.
- Confirm native WebView components are included in the distribution.

WebView is not an external browser updated independently of the JavaFX JARs under normal setups. To receive patches for the embedded engine, track and upgrade to appropriate JavaFX releases.

## 15. Legacy Desktop Tooling: Java Web Start and Java Deployment

Some Java 8 applications previously launched using Java Web Start, via JNLP files and the `javaws` command. Legacy Java Deployment technologies (including Java Web Start/Applet deployment) are no longer distributed in Oracle JDK 11 as before. Therefore, when migrating to a modern JDK, you cannot simply keep `javaws application.jnlp` and expect the launcher to still exist.

Options to evaluate:

- **Native installer/runtime image** built using appropriate packaging tools.
- **Standalone launcher/updater** managed by the organization or vendor.
- **OpenWebStart or an equivalent JNLP solution** if the system requires keeping the Web Start model and that solution supports the application/target JDK.
- **Change deployment architecture** if the legacy application depended on security sandboxes, signed JARs, or Java Web Start permissions that have changed.

Do not assume a replacement supports 100% of every JNLP extension, sandbox/security policy, and caching behavior of the old Java Web Start. Read vendor documentation and test with the actual release package.

### 15.1. Requirements Beyond Application Code

The launcher migration plan needs to answer:

- How do users install the application?
- Is the Java runtime pre-installed or bundled with the app?
- Who ships JDK and JavaFX security patches?
- Through which channel do automatic updates run?
- How are code signing and certificates managed?
- Are shortcuts, desktop integration, file associations, and protocol handlers needed?
- In which directories are local data, configuration, and caches stored?
- Does offline installation need to be supported?
- How to roll back if the new application fails to start?

These questions belong to compatibility migration, not solely to the release team. If the app cannot install or self-update after changing the JDK, the migration is not complete.

## 16. Packaging with jlink and jpackage

### 16.1. jlink Builds a Runtime Image from the Module Graph

`jlink` can create a runtime image containing selected modules. For a modular JavaFX application, a typical workflow includes:

1. Compile application modules.
2. Prepare JDK modules and JavaFX JMODs matching the OS/CPU.
3. Provide required application modules and module dependencies.
4. Run `jlink` with the defined module path and root modules.
5. Verify the application launcher, JavaFX native libraries, and resources in the final image.

Illustrative command:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:/path/to/javafx-jmods:build/mods" \
  --add-modules com.acme.desktop \
  --output build/runtime-image
~~~

The example uses Unix-style variables/paths and must be adapted for Windows and the JDK version. `build/mods` must contain properly compiled application modules, not arbitrary JARs dropped into a folder.

**Important limitation:** `jlink` operates on a graph of explicit modules; automatic modules cannot simply be linked like explicit modules. If dependencies are not yet modularized, consider replacing artifacts, modularizing them, or choosing a different packaging workflow. Do not assume that placing every JAR onto the module path means `jlink` will accept them.

### 16.2. jpackage Creates Installers or Application Images

`jpackage` is a tool for packaging Java applications for supported platforms. It can package a modular or non-modular application according to appropriate options, generating native launchers and app image/installer formats depending on the OS.

High-level workflow:

~~~text
Build application JAR/modules
              |
              v
Resolve JavaFX libraries + native artifacts
              |
              v
Build/choose suitable runtime image
              |
              v
Package launcher, icons, app files, metadata
              |
              v
Sign/notarize (if required by OS)
              |
              v
Test on a clean machine without JDK installed
~~~

With JavaFX, ensure the runtime image or app distribution **actually contains the required JavaFX modules and native components**. If JavaFX is not bundled, the installer might run on a developer machine that has the SDK yet fail on a new user's machine.

Depending on the artifact type, you can use `jpackage --module ...` or `--input`, `--main-jar`, `--main-class`, and `--runtime-image`. No single verbatim command fits every application type and OS. Choose the appropriate modular/non-modular mechanism based on the actual artifact and check `jpackage --help` on the JDK used for packaging.

### 16.3. Packaging per Operating System and Architecture

Desktop installers typically need to be built and tested for the exact target platform. Note:

- Windows: native launcher, MSI/EXE depending on tooling, DPI, file associations, and code signing.
- macOS: app bundle, architecture, code signing, notarization, and entitlements when needed.
- Linux: distribution-appropriate package or app image, graphics toolkit dependencies, and native media stack.
- Multiple CPU architectures: require matching JavaFX native libraries and runtime binaries.
- Offline distribution: the installer contains the full runtime and resources rather than relying on an already installed JDK.

Do not ship the same set of native libraries for every OS and expect Java to pick the right one when packaging is already wrong. Separate the build matrix by OS/architecture if artifacts are not truly portable.

## 17. Common Errors and Investigation Approaches

| Symptom | Possible Cause | First Check |
|---|---|---|
| `package javafx.application does not exist` | JavaFX not declared in compile dependencies | Maven/Gradle and compiler classpath/module path |
| `module not found: javafx.controls` | JavaFX module not on module path or wrong name | JavaFX artifacts, launch command, module descriptor |
| Missing JavaFX runtime components message | Launcher/runtime does not supply suitable JavaFX | Launch method, JavaFX SDK/dependencies |
| `UnsatisfiedLinkError` | Wrong or missing native artifact | OS/architecture, JavaFX native libraries |
| `NoClassDefFoundError` related to JavaFX | Missing module/JAR, classloader, or linking | Root stack trace, version, and runtime path |
| FXML `LoadException` | Wrong resource/controller path, reflection permissions, or controller error | FXML URL, `fx:controller`, `opens`, underlying cause |
| `InaccessibleObjectException` | Named module has not opened package to framework | `module-info.java` and the module performing reflection |
| `Not on FX application thread` | Updating scene graph from another thread | `Platform.runLater`, Task/Service, and event handlers |
| `Toolkit not initialized` | JavaFX toolkit not initialized or wrong lifecycle | `Application.launch` and UI creation order |
| CSS/images do not appear | Wrong resource path or packaging | JAR entries, `getResource`, resource URLs |
| WebView/Media fails only on another OS | Incompatible native engine/codec | Release notes and testing on the real platform |
| `jlink` rejects automatic module | Module graph contains a JAR not yet explicitly modularized | Module descriptors, packaging choice |
| Installer runs on build machine but not on a clean machine | Missing bundled runtime/native resource | Clean machine/VM testing |

This is a classification guide table, not a one-to-one mapping. For instance, `NoClassDefFoundError` can also appear after an earlier class initialization failure. Always read the root cause of the stack trace and record the exact launch command before changing configuration.

### 17.1. Standard Investigation Workflow

1. Record `java -version`, JDK vendor, and update release.
2. Record the JavaFX version and list of resolved JavaFX modules/artifacts.
3. Capture the exact launch command, classpath, module path, and working directory.
4. Identify the OS/CPU/display environment and whether the application runs headless or with a desktop session.
5. Verify that the JAR/runtime image actually contains classes, FXML/CSS/media, and native dependencies.
6. Determine whether the failure belongs to compilation, class/module resolution, native loading, FXML reflection, UI threading, or packaging.
7. Reproduce the error with a minimal screen on the exact OS/runtime.
8. Test a fix at the right layer: dependency, version, module descriptor, resource path, native package, or launcher.
9. Rerun business flows and the actual installer.
10. Document the root cause, evidence, rollback, and incident closure criteria.

## 18. Testing a JavaFX Application After Migration

Desktop applications are hard to prove compatible through unit tests alone. Multiple testing layers are needed:

### 18.1. Build and Startup

- Clean build with the target JDK and JavaFX version.
- Ensure the compiler does not use legacy internal JavaFX APIs.
- Build and run the application on the exact production classpath/module path.
- Verify startup on a machine without separately installed JavaFX/JDK if the application bundles its own runtime.
- Ensure error messages/logs can be collected if the launcher exits prematurely.

### 18.2. UI and User Interactions

- Open/close Stages, dialogs, popups, and secondary windows.
- Focus, keyboard navigation, clipboard, drag/drop, IME, and accessibility.
- Forms, TableView, TreeView, sorting/filtering, and custom controls.
- CSS themes, font fallback, scale factors, HiDPI, and multiple monitors.
- Application execution when changing locale and timezone.
- UI does not freeze when loading data or on slow networks.

### 18.3. FXML, Data, and Integration

- Load every FXML file in the final artifact.
- Inject controller fields and invoke event handlers.
- Load images, fonts, CSS, localization bundles, and templates.
- Connect to databases/HTTP/TLS/identity providers if used by the application.
- Check file choosers, printers, system tray, and required desktop integrations.
- If using the Swing bridge, verify operations across both the JavaFX thread and EDT.

### 18.4. Media, WebView, and Native Integration

- Open real media formats supported by the organization.
- Test WebView login, scripting, navigation, and certificate behavior.
- Check fonts/rendering/video on each OS/architecture.
- Test alerts/recovery when GPU or media backends are unavailable.

### 18.5. Packaging, Updates, and Rollback

- Verify installer, uninstaller, update, and relaunch.
- Confirm user data is not deleted during upgrades.
- Check application signing mechanisms, certificates, and OS permissions.
- Test rollback using the exact old installer/artifact if supported by the process.
- Verify the app does not depend on `JAVA_HOME` or an SDK pre-existing on a developer machine unless that is a documented deployment requirement.

The test suite must follow the actual version matrix instead of trying one configuration successfully and generalizing to all.

## 19. JDK – JavaFX – OS – Package Matrix

A minimal table for release readiness:

| Component | Fields to Fill | Illustrative Example |
|---|---|---|
| JDK | Vendor, feature/update, architecture | JDK 21 x64 |
| JavaFX | Version, modules, and native classifier | Verified version for target JDK |
| Build | Maven/Gradle version, plugin version | Plugin compatible with JDK/JavaFX |
| OS | Version and CPU architecture | Windows x64, macOS AArch64 |
| UI | Swing, JavaFX, FXML, WebView | JavaFX Controls + FXML |
| Launch | Module path or classpath | Named module or non-modular |
| Distribution | Runtime image, installer | OS-specific application image |
| Validation | Test result and artifact hash | Passed/failed + log path |

Example combinations to manage:

| Scenario | Build/Runtime | JavaFX Configuration | Objective |
|---|---|---|---|
| Baseline | Legacy JDK | JavaFX bundled with legacy JDK (if present) | Record current behavior |
| Development | New JDK | Separate OpenJFX dependencies | Validate source and UI |
| Modular | New JDK + JPMS | JavaFX named modules | Verify `requires`/`opens` |
| Packaged | Custom runtime image | Bundled JavaFX/natives | Run on a clean machine |
| Other OS | OS-matching JDK/runtime | Platform-matching JavaFX artifacts | Display and media/WebView |
| Rollback | Previously released artifact | Corresponding legacy libraries | Restore operations |

You do not need to test every imaginable combination. Test the combinations that the release and support policies actually commit to.

## 20. Phased Migration Roadmap

### Phase 1 — Lock Down the Baseline

Freeze the JDK/JavaFX version the application currently uses; list screens, resources, frameworks, native code, launchers, and update channels. Preserve a working installer along with how to reproduce it.

### Phase 2 — Replace Implicit JavaFX with Explicit Dependencies

Select an OpenJFX release suitable for the target JDK and OS. Add dependencies/plugins to Maven/Gradle; avoid mixing SDKs or artifacts of different versions. Run a minimal application before upgrading all third-party UI libraries.

### Phase 3 — Fix APIs and Module Boundaries

Audit internal `com.sun.javafx.*` imports and update custom libraries. If using JPMS, add `module-info.java` with the necessary `requires` and `opens` only controller packages needing FXML reflection. Verify resource loading over the module path.

### Phase 4 — Update Packaging/Launcher

Create a runtime image or distribution containing platform-appropriate JavaFX/natives. If relying on Web Start/JNLP, design a replacement launcher/update channel. Do not switch to a new installer before knowing how to update and roll back.

### Phase 5 — Platform-by-Platform Testing

Run on committed Windows/macOS/Linux and CPU architectures. Test clean machines, HiDPI, fonts, keyboard, FXML, media, WebView, external connections, and stability when opening/closing the application.

### Phase 6 — Staged Rollout and Monitoring

Release as a pilot to a small group, collecting startup, native loading, UI, data, and update errors. Keep the prior release intact enough to roll back if needed, without mixing the new runtime with old native libraries in the same installer.

## 21. Misleading Conclusions

**"Java 11 and later no longer support desktop applications."** False. AWT/Swing and `java.desktop` still exist; JavaFX is simply distributed separately.

**"Just downloading the JavaFX SDK and copying libraries into the JDK is enough."** Do not use this as a default migration workflow. Dependencies, module paths, native artifacts, and packaging must be managed reproducibly.

**"If JavaFX and the JDK have the same version, compatibility is guaranteed."** There is no such universal rule. Verify release notes and runtime requirements.

**"If the Gradle/Maven build is green, users can run it."** Not enough. Native libraries and the launcher may be missing or wrong for the OS/CPU; FXML resources may be encapsulated when running modularly.

**"FXML is just XML, unrelated to module access."** Incorrect. Controller injection uses reflection and may require `opens package to javafx.fxml`.

**"All Swing libraries were removed along with JavaFX."** False. Swing belongs to Java SE; only applications using JavaFX or the JavaFX-Swing bridge require the corresponding OpenJFX modules.

**"A fat JAR containing all of JavaFX is the safest distribution method."** Not guaranteed. Native dependencies, module metadata, service resources, and platform-specific components can be packaged incorrectly.

**"You can keep Java Web Start by reusing `javaws` from a new JDK."** False for modern Oracle JDKs. If JNLP is needed, you must select and test a separately provided solution or change the distribution model.

**"Testing the UI on one developer machine is sufficient."** Insufficient for desktop apps. OS, CPU, display server, fonts, DPI, codecs, certificates, and installers can differ significantly.

## 22. Checklist Before Marking Migration Complete

- [ ] Identified the legacy JDK/JRE and JavaFX builds, including vendor and artifacts.
- [ ] Distinguished Java SE Swing/AWT APIs from separately distributed JavaFX.
- [ ] Selected a JavaFX version supported on the target JDK.
- [ ] Identified all needed JavaFX modules: controls, fxml, media, web, swing...
- [ ] Checked native libraries by OS and CPU architecture.
- [ ] Managed JavaFX via dependencies/plugins or an explicit, reproducible SDK/runtime.
- [ ] Audited code depending on `com.sun.javafx.*` internal APIs.
- [ ] Checked `module-info.java`, `requires`, and `opens` if the application uses JPMS.
- [ ] Checked all FXML, CSS, image, font, and localization files in the final artifact.
- [ ] Checked controller injection and reflection errors.
- [ ] Tested the JavaFX Application Thread and Swing EDT if the application is hybrid.
- [ ] Tested WebView and media formats on supported platforms.
- [ ] Confirmed launcher, installer, updates, and code signing work.
- [ ] Ran the application on a clean machine independent of the developer SDK.
- [ ] Created a JDK/JavaFX/OS/CPU test matrix with clear results.
- [ ] Prepared a rollback plan covering the app, runtime, and native artifacts.
- [ ] Documented responsibility for updating both JDK and JavaFX security patches.

## 23. Conclusion

In Java Advance Compatibility Migration, **JavaFX is a prime example of a technology that continues to be developed yet is no longer bundled with the JDK as in some older releases**. Since JDK 11, JavaFX applications must actively manage OpenJFX modules and their corresponding native parts. Meanwhile, AWT/Swing remain in Java SE, whereas legacy desktop deployment technologies like Java Web Start require a replacement roadmap or separate distribution solution.

Compatibility evaluation must examine the full chain **source code → JavaFX dependency → module graph → native runtime → launcher/installer → actual operating system**. Only once the application compiles, launches, renders properly, locates resources, runs on a clean machine, and has a tested update/rollback channel is the desktop migration truly complete.