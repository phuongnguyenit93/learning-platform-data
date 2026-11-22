# Applet, Java Web Start, and Desktop Application Distribution Approaches

In many long-lived Java systems, the user interface was not limited to standard web applications or desktop programs. Some products were deployed as **Java Applets** running inside a browser, while others used **Java Web Start** to download and launch a Java application from a JNLP link. These technologies once helped distribute Java clients to many machines, yet relied on a Java browser plugin, the Java Deployment stack, and security assumptions that no longer fit modern platforms.

When migrating from Java 8 to JDKs such as 11, 17, or 21, simply bumping the source/target version is not enough. Applets may no longer be executed by browsers; `javaws` is no longer a standard tool bundled with newer JDKs; JavaFX is no longer bundled in the JDK starting with Java 11. The development team must re-select **how the application is launched, packaged, updated, and distributed**.

This lesson distinguishes Applets from Java Web Start, describes key version milestones affecting compatibility, analyzes suitable migration paths for desktop clients, and presents a migration workflow, Java Swing, `jlink`, and `jpackage` examples, and a deployment checklist.

## 1. Distinguishing Applets, Java Web Start, and Desktop Applications

These are three distinct models, even though all three can use Java SE and AWT/Swing UIs.

| Model | Historical Launch Mechanism | Relationship to Browser | Distribution Mechanism |
|---|---|---|---|
| Java Applet | Browser loads the Applet via Java Plugin | Runs inside or attached to a web page; has an Applet lifecycle | Browser/Java Plugin downloads classes/JARs and manages the runtime |
| Java Web Start | User opens a JNLP file with `javaws` | Browser typically provides only a link to download/open the JNLP; application runs separately | JNLP declares resources, runtime, permissions, and entrypoint |
| Standalone Java Desktop | Runs `java -jar`, a launcher, or a native executable | No browser plugin required | JAR + runtime, `jlink` image, `jpackage` app image/installer, or other tools |

Common points of confusion:

- **An Applet is not Java Web Start.** Applets rely on browser integration; Java Web Start launches a standalone desktop application using a JNLP file.
- **JNLP does not mean `javaws` is built into every JDK.** JNLP is the launch descriptor format/protocol, whereas `javaws` is a launcher provided by a specific implementation.
- **Swing/AWT did not disappear merely because Applet or Java Web Start was removed from the deployment stack.** Many Swing/AWT interfaces can be migrated to standard desktop applications.
- **Packaging as an executable does not automatically provide a network update mechanism.** That is a separate design responsibility.

## 2. Key Change Milestones by JDK

These milestones help distinguish technologies removed from the deployment stack from APIs that remained in the JDK for a period of time.

| Milestone | Related Changes | Migration Impact |
|---|---|---|
| JDK 8 | Applet and Java Web Start still supported in some Java 8 distributions, notably Oracle's deployment stack | Legacy systems may depend on `javaws`, Java Plugin, and Java Control Panel |
| JDK 9 | Applet API marked deprecated; Java Plugin enters deprecation/removal path | Do not build new Applets; prepare an alternative approach |
| JDK 11 | Oracle JDK removes Java Deployment technologies including Java Plugin, Java Web Start, and Java Control Panel; JavaFX no longer bundled with the JDK | Cannot assume `javaws`/browser plugin/JavaFX are present simply by installing JDK 11 |
| JDK 14 | `jpackage` introduced as incubating | Adds a path to create native app images/installers in newer JDKs |
| JDK 16 | `jpackage` becomes a standard tool (JEP 392) | Official desktop packaging solution bundled with the JDK |
| JDK 17 | Applet API deprecated for removal (JEP 398); `jpackage` available | Applet API remains legacy and is not a recommended distribution method; migrate the model |
| JDK 21 and beyond | Desktop Java still has supported tools and libraries depending on the distribution; applications must verify APIs and runtime separately | Separate upgrading the JDK from choosing the launcher, UI toolkit, and distribution channel |

Java distributions can differ in included tools or standalone deployment products. When saying “the JDK no longer includes Java Web Start,” understand that **the classic launcher is no longer part of the standard deployment stack as before**, not that every third-party JNLP implementation has vanished.

In particular, **retaining the Applet API in a release does not mean modern browsers still support running Applets**. The core issue is that browser plugins have been removed from mainstream browsers and the old Java Deployment architecture is no longer a viable deployment platform.

## 3. How Does a Java Applet Work?

An Applet is a Java object designed to be loaded and managed by a host (typically a browser with Java Plugin, and previously also an applet viewer).

Minimal legacy AWT Applet example:

```java
import java.applet.Applet;
import java.awt.Button;
import java.awt.FlowLayout;

public class LegacyApplet extends Applet {

    @Override
    public void init() {
        setLayout(new FlowLayout());
        add(new Button("Gửi yêu cầu"));
    }

    @Override
    public void start() {
        // Host may call this when the Applet is activated.
    }

    @Override
    public void stop() {
        // Host may call this when the Applet is paused.
    }

    @Override
    public void destroy() {
        // Clean up resources when the host destroys the Applet.
    }
}
```

Common lifecycle methods:

1. `init()`: initializes data or UI components.
2. `start()`: starts or resumes work when the host activates the Applet.
3. `stop()`: pauses work when the host stops displaying/activating it.
4. `destroy()`: releases resources when the Applet terminates.

A host may invoke `start()` and `stop()` multiple times. When migrating to desktop, do not copy this lifecycle verbatim into a `main()` method and assume they are equivalent.

### 3.1. What Applets Used to Depend On

An Applet application typically included one or more of the following:

- Legacy HTML tags to embed the Applet in a page and pass parameters.
- Java Plugin/NPAPI or the corresponding browser integration mechanism.
- Sandbox rules and permission grants under the Java Plugin trust model.
- Resources loaded from the web page's codebase.
- Applet context, browser scripting bridge, or JavaScript integration.
- Applet/JAR signing, deployment descriptors, and deployment security settings.
- Assumptions about networking, cookies, proxies, sessions, and host origin.
- An AWT/Swing UI rendered inside a page region instead of an independent window.

Once browser plugins no longer operate, upgrading class files to Java 17 **will not make an old Applet tag run again**. The functionality must be moved to a browser-suitable model or a standalone desktop application.

### 3.2. Separating UI Code from Host Integration

In legacy Applets, business logic was sometimes browser-independent, whereas the entrypoint and resource access depended on the host.

For example, in a data-entry application:

```text
Applet host / HTML parameters
          |
          v
AWT/Swing UI
          |
          v
Domain validation + business rules
          |
          v
HTTP/SOAP client + file access
```

Domain validation or business rules may be reusable. However, host integration, endpoint configuration, permissions, and browser mechanisms must be replaced.

## 4. Limitations of Continuing to Use Applets

### 4.1. Browsers Are No Longer a Viable Launch Environment

Modern browsers no longer widely provide the Java Plugin as before. This makes the browser-embedded Applet model an unreliable option for end-user distribution.

This cannot be fixed by running:

```text
javac --release 17 LegacyApplet.java
```

or adding JVM flags. The compiler target does not control browser capabilities.

### 4.2. Security Compatibility Constraints

Traditional Applets had their own permission/sandbox system; many applications also requested permission to open files, print, or open network connections. A modern desktop environment does not automatically recreate the Applet permission policy.

When migrating, you must redesign:

- Will users approve opening files, saving files, or printing?
- Where are credentials and tokens issued and stored?
- Is the UI permitted to call legacy endpoints from the new environment?
- How are proxies, TLS, and truststores configured?
- Which directory stores files or temporary data?
- How are sensitive operations privilege-restricted?

### 4.3. Browser Scripting Bridges Do Not Automatically Become Desktop APIs

An Applet may have called JavaScript or been invoked by JavaScript via the Java Plugin integration mechanism. When moving to a standalone desktop app, this communication channel no longer exists automatically.

If two-way interaction between the browser and the desktop application is needed, consider solutions with explicit contracts such as:

- Backend API: both the browser app and desktop app communicate with the server.
- Controlled URI scheme/protocol handler: the browser asks the OS to launch the application.
- A separately deployed/controlled browser extension and native messaging host.
- A local loopback endpoint in certain products, accompanied by authentication, origin checks, and proper CORS/CSRF restrictions.

Do not expose an unprotected local HTTP endpoint and assume it is equivalent to the Applet sandbox.

## 5. Java Web Start and JNLP

Java Web Start once provided a way to launch a Java desktop app from a web link. The application is described by a **JNLP (Java Network Launch Protocol)** file containing artifact information, entrypoint, runtime, and deployment metadata.

An illustrative simple JNLP structure example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jnlp spec="1.0+"
      codebase="https://download.example.invalid/desktop">
    <information>
        <title>Inventory Desktop</title>
        <vendor>Example Organization</vendor>
        <description>Ứng dụng quản lý kho</description>
    </information>

    <resources>
        <j2se version="1.8+"/>
        <jar href="inventory-client.jar" main="true"/>
    </resources>

    <application-desc main-class="com.example.inventory.Main"/>
</jnlp>
```

This is a historical example for Java Web Start, **not a file guaranteed to run on every modern JNLP launcher**. Runtime attributes, permissions, resources, and vendor features must be checked against the chosen implementation.

### 5.1. What Problems Did JNLP Files Solve?

- Providing metadata for the launcher to identify the application entrypoint.
- Describing JARs, native libraries, and resources to be downloaded.
- Supporting caching and certain resource update mechanisms.
- Allowing declaration of Java runtime requirements.
- Allowing configuration of desktop shortcuts, offline availability, and deployment behavior depending on the implementation.
- Supporting Java Web Start security policies and APIs in the historical environment.

Many systems relied on JNLP for the flow: “user clicks a link on the portal, launcher checks for a new version, downloads JARs, and opens the application.”

### 5.2. Why Does JDK 11 Not Launch JNLP Like JDK 8?

Java Web Start (`javaws`) was part of the historical Java Deployment stack, not a mandatory feature present in every JDK. When this stack was removed from Oracle JDK 11, upgrading user machines from Java 8 to Java 11 could cause `javaws` to disappear.

Consequence:

```bash
javaws inventory.jnlp
```

can no longer be assumed to work on a machine with only a standard JDK 11/17 installed. `java -jar inventory.jnlp` is not a replacement either: JNLP is an XML descriptor, not an executable JAR.

### 5.3. JNLP Is Not an Applet

Classify the legacy system accurately:

- If users launch the program via a `.jnlp` file using `javaws` and see a standalone window, it is usually a Java Web Start application.
- If the Java UI sits directly inside a web page and requires Java Plugin, it is an Applet.
- If there is only a shortcut running `java -jar`, it is a traditional Java desktop application, even if the JAR file was downloaded from a website.

Converting an Applet into Java Web Start is not just changing a file extension. You must create an entrypoint and rework the lifecycle, browser integration, and security model.

## 6. Transitional Option: Standalone JNLP Launchers

An organization may need to keep supporting JNLP during migration, especially when many desktop clients are already deployed alongside a long-standing JNLP update mechanism.

Solutions in the standalone Java Web Start ecosystem, such as **OpenWebStart** or IcedTea-Web-based implementations, can serve as a transitional option for **supported JNLP applications**.

Key points to emphasize:

- This is not a feature automatically restored by installing JDK 17.
- Support for JNLP features, JNLP services, JVM management, signing, and security varies by implementation and version.
- A standalone JNLP launcher **is not equivalent to a browser Java Plugin** and does not restore embedded Applets.
- Components tightly coupled to a JDK 8 vendor or proprietary deployment APIs must be verified.
- Review licensing/distribution terms, launcher update policies, and operability on the target OS.

### 6.1. When Should You Consider a Standalone JNLP Launcher?

This approach may be suitable if:

- The application is genuinely a **standalone** Java Web Start app rather than a browser Applet.
- Business logic and UI remain compatible with the target Java runtime.
- The server-based JAR download/update model must be retained.
- The organization can manage the launcher on workstations.
- The JNLP features in use are supported by the replacement implementation or can be adapted.

If the application depends heavily on legacy Java Deployment APIs, browser integration, or legacy security prompts, testing costs may be high. In that case, native packaging or rewriting the UI may be more sustainable.

### 6.2. Components to Inventory Before Testing

Inspect the JNLP file and active code:

- `<application-desc>`, `<applet-desc>`, `<component-desc>`, and launch type.
- `<resources>`, `<jar>`, `<nativelib>`, and required runtime.
- `<security>` such as `<all-permissions/>`, if present.
- `<extension>`, `<property>`, offline/caching, and additional arguments.
- `javax.jnlp.*` APIs such as BasicService, FileOpenService, DownloadService, or PersistenceService if used.
- Code signing, certificate chains, and trust requirements.
- Resource URLs, authentication, proxies, and server headers.
- Shortcut creation and custom application update mechanisms.

Do not conclude JNLP compatibility merely because the XML file parses cleanly. Launch the app, create shortcuts, download updates, and test key workflows on a clean machine.

## 7. Choosing a Migration Direction: Web or Desktop Application?

Before selecting a packaging tool, determine the user experience model.

### 7.1. Migrating to a Web Application

Suitable when most functionality can run in a browser:

- Data-entry forms and data lookup.
- Dashboards, reports, and approval workflows.
- Calling APIs over HTTP and managing state server-side.
- Using a browser across multiple operating systems without needing a Java runtime installed on the client.

A common architecture:

```text
Browser UI (HTML/CSS/JavaScript)
             |
             v
     Backend API (Java)
             |
             v
    Database / Services
```

The advantage is not having to distribute a Java runtime to workstations. However, capabilities like reading USB devices, smart cards, specialized printing, deep filesystem access, or working offline require custom design.

### 7.2. Keeping a Java Desktop Application

Suitable if the product needs:

- Existing Swing/AWT/JavaFX UI that can be substantially reused.
- OS integration, printing, peripherals, clipboard, or local files.
- Offline operation or data synchronization when network connectivity returns.
- Bundling a dedicated runtime without depending on a pre-installed JDK.
- Release and rollback workflows tailored to desktop software.

You can choose `jpackage` to produce a launcher/app image/installer, or distribute a runtime image and script if operational needs dictate.

### 7.3. Hybrid Model

Some systems adopt a web UI for primary functionality combined with a small desktop utility for specialized hardware:

```text
Browser / Web App  <---- HTTPS API ----> Backend Services
       |
       | custom-designed integration protocol
       v
 Local Desktop Agent -----> Printer / Scanner / Smart Card
```

This design requires controlling authentication, authorization, agent updates, and restricting the communication channel between the browser and the local application.

### 7.4. Option Comparison Table

| Requirement | Web App | Desktop + `jpackage` | Standalone JNLP Launcher |
|---|---|---|---|
| No software installation required on user machine | Usually suitable | No | Requires launcher/runtime |
| Reuse existing Swing/AWT | Limited | Good | Potentially good |
| Peripherals / advanced local filesystem access | Needs a separate integration mechanism | Better suited | Depends on permissions/implementation |
| Offline-first | Needs custom offline web design | Suitable | Depends on cache and application |
| Automatic update channel | Easy to update on the server | Must build/adopt an updater | Can use launcher-provided caching/updates |
| Long-term investment in a Java desktop product | Not directly | Suitable | Usually a transitional option |
| Restore Applet inside a modern browser | Not via the Applet model | No; moves to a separate window | Does not restore Java Plugin |

There is no single optimal choice for every application. Balance code reuse, installation cost, workstation operations, security, offline needs, and hardware access requirements.

## 8. Converting an Applet into a Standalone Swing Application

Suppose a legacy Applet displays a button and handles an action. When migrating to desktop, you can often keep the domain/controller logic and replace the entrypoint with a JFrame, JDialog, or an appropriate JavaFX window.

Standalone Swing application example:

```java
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import java.awt.BorderLayout;

public final class InventoryDesktopApp {
    private InventoryDesktopApp() {
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(InventoryDesktopApp::showWindow);
    }

    private static void showWindow() {
        JFrame frame = new JFrame("Inventory Desktop");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        JLabel status = new JLabel("Chưa gửi yêu cầu");
        JButton button = new JButton("Gửi yêu cầu");
        button.addActionListener(event -> status.setText("Đã nhận thao tác"));

        JPanel panel = new JPanel(new BorderLayout(12, 12));
        panel.add(status, BorderLayout.CENTER);
        panel.add(button, BorderLayout.SOUTH);

        frame.setContentPane(panel);
        frame.setSize(420, 180);
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }
}
```

This is an example of desktop code that does not use the Applet API. It can be compiled with JDK 17:

```bash
javac InventoryDesktopApp.java
java InventoryDesktopApp
```

The application requires a desktop environment; in a server/headless environment, creating a JFrame may fail.

### 8.1. Parts That Can Be Reused

- Validation, domain services, and UI-independent business logic.
- Compatible data access and HTTP clients.
- Event-handling logic that can be extracted into controllers.
- Portions of Swing/AWT components, provided they do not rely on Applet context.
- Icon resources, localization bundles, and configuration files, after adjusting how they are loaded.

### 8.2. Parts That Must Be Redesigned

- `Applet.init/start/stop/destroy` into desktop app startup, foreground/background lifecycle, and shutdown.
- HTML parameters into config files, environment variables, or CLI arguments.
- Browser plugin/JavaScript bridge mechanisms into explicit APIs or protocols.
- Deployment-sandbox-managed file selection/printing into proper OS permissions and UI dialogs.
- Resources from the JNLP codebase into bundled app resources, API URLs, or a dedicated cache.
- Updates from Java Deployment into a managed installer/updater.

### 8.3. Event Dispatch Thread and Background Work

In Swing, UI updates should execute on the Event Dispatch Thread (EDT). Long-running network or file operations should not run directly inside an action listener, as they freeze the UI.

Use `SwingWorker` or an executor to offload heavy work to background threads and then update the UI safely. A migration is a good opportunity to separate UI from I/O rather than carrying over an unclear Applet threading model to desktop.

## 9. JavaFX When Moving from Java 8 to 11/17+

If a legacy desktop application uses JavaFX, remember that JavaFX is no longer bundled in standard JDK 11. The JavaFX libraries are distributed separately via OpenJFX or compatible distributions.

Consequences:

- A project that built and ran JavaFX on JDK 8 may fail to compile/run if you only switch `JAVA_HOME` to JDK 17.
- You must add JavaFX dependencies with the version and classifier/native artifacts matching the target OS and architecture.
- For modular applications, you may need `requires javafx.controls;`, `javafx.fxml`, or the corresponding JavaFX modules.
- When packaging with `jlink`/`jpackage`, include the appropriate JavaFX modules and native resources in the runtime/application image.
- FXML, reflection, and controller packages may require `opens ... to javafx.fxml;` in the module descriptor.

Modular JavaFX application descriptor example:

```java
module com.example.inventory.desktop {
    requires javafx.controls;
    requires javafx.fxml;

    exports com.example.inventory.desktop;
    opens com.example.inventory.desktop.ui to javafx.fxml;
}
```

This is only a descriptor example; an actual build also needs compatible JavaFX dependencies and module path settings. Do not confuse **JavaFX leaving the JDK** with **JavaFX no longer being viable for application development**.

## 10. `jpackage`: A Modern Desktop Packaging Approach

`jpackage` creates a native **application image** or installer for a Java application, optionally bundling a dedicated Java runtime image. It is a standard solution in modern JDKs for Java desktop distribution without relying on Java Plugin or `javaws`.

### 10.1. App Images and Installers Differ

- **App image:** a directory containing the launcher and required runtime components. It can be used to verify packaging or serve as input for an installer.
- **Native installer:** an OS-specific installation package, such as `msi`/`exe` on Windows, `dmg`/`pkg` on macOS, or `deb`/`rpm` on Linux.

An app image is not automatically an installer with an install/uninstall UI or an update mechanism.

### 10.2. Example: Creating a JAR for the Swing Application

Assuming `InventoryDesktopApp.java` is compiled:

```bash
javac -d build/classes InventoryDesktopApp.java

jar --create \
  --file build/inventory-desktop.jar \
  --main-class InventoryDesktopApp \
  -C build/classes .
```

If the application has multiple dependencies, prepare all required runtime JARs. The commands above illustrate only a simple single-class case with no external dependencies.

### 10.3. Packaging with `jpackage`

Example creating an app image:

```bash
jpackage \
  --type app-image \
  --name InventoryDesktop \
  --input build \
  --main-jar inventory-desktop.jar \
  --main-class InventoryDesktopApp \
  --dest dist
```

Key options:

| Option | Role |
|---|---|
| `--type app-image` | Creates an application image directory instead of an installer |
| `--name` | Name of the application/launcher |
| `--input` | Directory containing input JARs and resources |
| `--main-jar` | JAR containing the entrypoint |
| `--main-class` | Main class when it needs to be specified |
| `--dest` | Destination directory where generated artifacts are written |
| `--runtime-image` | Uses a pre-built runtime image |
| `--java-options` | Adds JVM arguments needed for the launcher |

When using `--input build`, avoid accidentally bundling extraneous JARs or unnecessary resources into the package. For real applications, prepare a staging directory containing only approved release dependencies and runtime resources.

### 10.4. Choosing a Format by Platform

Installer formats and native dependencies vary by OS:

| Build Platform | Common Outputs | Notes |
|---|---|---|
| Windows | `app-image`, `exe`, `msi` | Requires suitable Windows environment and packaging toolchain; handle signing/installer policies |
| macOS | `app-image`, `dmg`, `pkg` | Must consider code signing, notarization, and OS permissions |
| Linux | `app-image`, `deb`, `rpm` | OS package-building tools must be properly installed |

Normally, **you cannot run `jpackage` once on Linux to produce full native Windows/macOS installers**. Build and test artifacts on each target OS/architecture; if Windows x64 and Windows ARM64, or macOS Intel and Apple Silicon, are needed, manage each variant accordingly.

### 10.5. Bundled Runtime Image

A major advantage is that the application can ship with an appropriate runtime. Users do not have to choose and install a JDK on their workstations just to run the client.

However, bundling a runtime brings update obligations:

- When JDK security patches arrive, the runtime/app image must be repackaged and re-released.
- The installer must support upgrade paths, repairs, rollback, and version metadata.
- Native libraries must match the target architecture and operating system.
- Track the provenance and license of the runtime distribution in use.

Do not treat a runtime bundle as “install once and never maintain.”

## 11. `jlink`: Creating a Custom Runtime Image

`jlink` appeared in Java 9 and is used to assemble a runtime image containing only the needed modules. It differs from `jpackage`:

- `jlink` creates a **runtime image**.
- `jpackage` creates an **application image or installer** and can consume that runtime image.

### 11.1. Analyzing Dependencies with `jdeps`

With the application JAR and libraries in `lib`, you can inspect dependencies using:

```bash
jdeps --print-module-deps \
  --class-path "lib/*" \
  build/inventory-desktop.jar
```

The output is a starting point for selecting required JDK modules, though static analysis can miss modules/providers used via reflection or service loading.

### 11.2. Creating a Runtime for a Swing Application

Example for a runtime requiring `java.desktop`:

```bash
jlink \
  --add-modules java.desktop \
  --output build/inventory-runtime
```

Depending on the application, you may also need `java.net.http`, `java.sql`, `java.logging`, security/service providers, or other modules.

Then point `jpackage` to that image:

```bash
jpackage \
  --type app-image \
  --name InventoryDesktop \
  --input build/staging \
  --main-jar inventory-desktop.jar \
  --runtime-image build/inventory-runtime \
  --dest dist
```

For applications using `ServiceLoader`, JDBC drivers, locales, or JavaFX modules, verify that the runtime image includes all required modules and providers. `jlink` does not automatically resolve every classpath library or native dependency.

### 11.3. Testing the Final Runtime

A custom image might launch the initial screen yet fail on features triggered later, such as:

- File-chooser or print dialogs.
- HTTPS connections with an incorrect truststore.
- Localized text, charsets, or timezones.
- JDBC drivers or serialization providers.
- Smart cards or native DLL/.so/.dylib libraries.
- Reflection and dynamic loading.

Therefore, testing must run on the **actual app image/installer**, not only on a full JDK on a development machine.

## 12. The JAR + Runtime + Script Approach

Not every environment needs a native installer. For internal systems, you can distribute an archive containing an appropriate runtime, JARs, and a launcher script:

```text
inventory-desktop/
├── runtime/
│   └── bin/java
├── app/
│   ├── inventory-desktop.jar
│   └── lib/
└── bin/
    └── start.sh
```

Linux/macOS launcher example using relative paths:

```bash
#!/usr/bin/env sh
APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec "$APP_HOME/runtime/bin/java" \
  -jar "$APP_HOME/app/inventory-desktop.jar" "$@"
```

This example requires an executable JAR with a valid classpath/manifest configuration or a corresponding dependency-loading mechanism. If the JAR does not bundle dependencies, the script must set the classpath or module path properly.

The advantage is high control and straightforward deployment via internal administration tools. The downside is having to handle shortcuts, install/uninstall, desktop integration, code signing, updates, and runtime maintenance yourself.

## 13. Distribution, Updates, and Rollback

Java Web Start tied launch directly to resource downloading and updates. When moving to an installer or app image, those capabilities do not appear automatically.

### 13.1. Choosing an Update Policy

Common choices:

1. **Manual updates:** users download and install new releases.
2. **Centralized management:** IT/MDM/software distribution pushes installers to device groups.
3. **Application-owned updater:** the application checks versions, downloads a signed package, and applies the upgrade.
4. **External auto-update framework:** used if it meets OS, security, and integration requirements.

For business-critical applications, choose an explicit mechanism rather than expecting users to swap JARs manually.

### 13.2. Safe Releases

A desktop release process should manage:

- Application version and JDK runtime version.
- Artifact hashes/checksums and code/installer signatures.
- Release channels (test, pilot, production).
- Rules for verifying downloads from the server.
- HTTPS/TLS download sources and certificate policies.
- Rollback capability if schemas/local data remain compatible.
- Storage locations for configs, logs, caches, and user data so new installations do not overwrite them.
- Per-user versus per-machine installation modes and admin privilege requirements.
- Monitoring of startup errors, crashes, and connectivity issues.

Do not embed tokens, passwords, or private keys in the installer. If the app requires sign-in, use modern authentication and OS-appropriate secure storage.

### 13.3. Version Compatibility Between Client and Server

Desktop clients may not update simultaneously on all machines. When backend APIs change, support mixed rollouts:

```text
Client 1.7  ──API v1──┐
                    ├── Server during the transition period
Client 2.0  ──API v2──┘
```

Define the support window for older clients, request/response contracts, forced-upgrade policies, and rollback handling when clients have already migrated local data to a new format.

## 14. Security: From the Applet/JNLP Sandbox to an OS Application

One of the biggest shifts lies not in Java syntax but in the **trust model**.

### 14.1. No Automatic Inheritance of the Legacy Sandbox

The Applet sandbox and JNLP security model previously governed how network-downloaded applications accessed workstation resources. Once installed as a desktop application, the program typically runs with the user account's privileges and OS-level restrictions.

Re-evaluate:

- File and device system access.
- Network connections to external hosts and localhost.
- Credential storage.
- Code signing and artifact provenance.
- Privileges of the updater/installer.
- Scope of data the application reads and writes.
- Endpoints that can be called from the UI or browser integration.

### 14.2. Do Not Replace Warnings with Full Permissions

Some legacy JNLP files declared:

```xml
<security>
    <all-permissions/>
</security>
```

During migration, do not treat “grant all permissions” as the goal for the new application. Analyze exactly which permissions each feature requires and restrict according to least privilege.

### 14.3. Code Signing Differs from TLS

- **TLS/HTTPS** protects the download channel and authenticates the endpoint when configured properly.
- **Code signing** verifies the publisher and artifact integrity within the platform's signing ecosystem.
- **Checksums** help verify integrity, though by themselves they do not authenticate the publisher if distributed from an untrusted source.

When releasing an installer, combine these mechanisms; do not treat them as complete substitutes for one another.

## 15. Inventorying Legacy Systems Before Deciding on Migration

A legacy desktop application often has many dependencies beyond its JARs. Create an inventory to avoid missing requirements when replacing the launcher.

| Item | Questions to Answer |
|---|---|
| Application type | Browser Applet, standalone JNLP, or `java -jar`? |
| UI toolkit | AWT, Swing, JavaFX, or another UI library? |
| Lifecycle | `Applet.init/start/stop/destroy`, `main`, or JNLP entrypoint? |
| Browser integration | Are there JS bridges, cookies, sessions, or HTML parameters? |
| Java runtime | Current and minimum target vendor/version/architecture? |
| Dependencies | Which JARs, native libraries, JavaFX, `javax.jnlp.*`, or Java Deployment APIs? |
| Security | JAR signing, certificates, sandbox, `all-permissions`, secrets/tokens? |
| Filesystem | Local files, data directories, import/export, printing? |
| Network | Proxies, DNS, TLS, SOAP/REST endpoints, offline cache? |
| Deployment | JNLP resource cache, portal links, shortcuts, installer, or centralized management? |
| Updates | Who upgrades clients, using which channel, and how is rollback handled? |
| Operating system | Windows/macOS/Linux, x64/ARM64, account permissions? |

The inventory separates reusable components (domain logic, API clients, UI components) from components requiring replacement (host, launcher, updater, security policies).

## 16. Recommended Migration Process

### Step 1: Lock Down a Working Baseline

Record the legacy Java 8/JDK version, JNLP/HTML descriptors, signed artifacts, dependencies, browser or launcher environment, and tested business workflows.

### Step 2: Identify the Legacy Technology Accurately

Do not apply the same migration path to Applets and Java Web Start. Determine whether it is a browser-plugin-dependent Applet or a desktop app launched via `javaws`. If both exist, split them into two separate tracks.

### Step 3: Decouple Code from Host Mechanisms

Extract domain services, validation, data access, and HTTP clients from the Applet/JNLP lifecycle. Define an appropriate desktop entrypoint or backend API.

### Step 4: Choose the Distribution Target

Evaluate a web app, a `jpackage`-packaged desktop app, a standalone JNLP launcher bridge, or a hybrid model. Document the rationale based on features, OS, offline needs, and peripherals.

### Step 5: Upgrade the JDK and Dependencies

Select the target JDK, compiler/toolchain settings, and modern dependencies. If using JavaFX, declare OpenJFX separately. If `javax.jnlp.*` remains, replace the API or verify that the new launcher supports it before releasing.

### Step 6: Create the Entrypoint and Package

For desktop apps, create a `main()`/launcher, configure the manifest, and choose `jpackage` or an appropriate runtime image model. If using `jlink`, identify all required JDK modules and service providers.

### Step 7: Design Deployment and Updates

Define the app version, runtime version, download channel, code signing, install/uninstall behavior, updates, and rollback. Store user configs/data outside directories replaced during upgrades.

### Step 8: Functional Testing on a Clean Machine

Do not test only inside an IDE. Install the real artifact on the target OS/architecture under a standard user account, and test sign-in, file operations, printing, offline mode, proxies, TLS, and native integrations.

### Step 9: Pilot with a Small User Group

Roll out in stages, monitoring crashes, logs, performance, update success rates, and server API compatibility. Prepare support for machines that fail prerequisites or lack installer permissions.

### Step 10: Controlled Decommissioning of Legacy Mechanisms

Once the new client is stable, drop reliance on the legacy browser plugin/JNLP launcher, retire outdated distribution channels, and update operational documentation. Do not remove server/API endpoints still serving un-upgraded clients before their support window expires.

## 17. Common Risks and How to Avoid Them

### “The Applet compiles on a new JDK, so it will run in Chrome/Edge”

False. Browser plugins belong to the browser and deployment stack, not a capability restored by compiling an Applet class.

### “Replacing `javaws` with `java -jar` is enough”

False. `javaws` parses JNLP and handles resources, runtime selection, security, updates, and the entrypoint. `java -jar` runs an executable JAR; previous deployment features must be built or replaced separately.

### “Using OpenWebStart will make Applets run inside the browser again”

False. A standalone JNLP launcher does not restore Java Plugin for embedded Applets. Verify whether the application is genuinely standalone JNLP.

### “With `jpackage`, the application updates itself automatically”

False. `jpackage` builds an app image/installer. Update, rollback, and release-channel mechanisms still need to be designed and operated.

### “Just copying the JAR moves an Applet straight to desktop”

False. The Applet lifecycle, browser integration, sandbox, and resource loading must all be reworked. Business logic can be reused, but the host abstraction changes.

### “JavaFX is still bundled by default in JDK 17”

False for standard JDKs: JavaFX has been distributed separately since Java 11. You must manage OpenJFX dependencies, modules, and native assets or use an appropriate distribution.

### “If the app runs on a dev machine, the installer is guaranteed to work”

False. Developer machines often have JDKs, drivers, native libraries, certificates, or admin rights that user machines lack. Always test on a clean machine using the final artifact.

### “A bundled runtime needs no security patches”

False. When bundling a runtime with the app, responsibility for updating the runtime shifts to the application's release pipeline. Maintain a patch cadence and the ability to roll out new releases.

## 18. Completion Checklist

- [ ] Correctly distinguished Applet, Java Web Start/JNLP, and traditional desktop JAR models.
- [ ] Recorded browser plugin, `javaws`, JNLP API, and launcher dependencies.
- [ ] Identified the target JDK runtime and features no longer present in the JDK.
- [ ] Evaluated how to reuse AWT/Swing/JavaFX UI and business logic.
- [ ] If choosing a web app, redesigned browser integration and local features.
- [ ] If choosing desktop, implemented a `main()`/launcher independent of an Applet host.
- [ ] If choosing a JNLP bridge, tested the standalone launcher against actual JNLP features.
- [ ] If using JavaFX, declared and packaged OpenJFX for the target OS/architecture.
- [ ] If using `jlink`, verified the runtime image has all modules/providers and tested it in practice.
- [ ] If using `jpackage`, tested the app image/installer on a clean machine.
- [ ] Defined code signing, TLS, authentication, and filesystem/device permissions.
- [ ] Designed update channels, versioning, rollback, and bundled runtime maintenance.
- [ ] Tested offline mode, proxies, certificates, printing, and native devices where applicable.
- [ ] Established a client/server compatibility plan for the mixed-version rollout period.
- [ ] Established a plan to retire legacy Applet/`javaws` distribution once migration is complete.

## 19. Conclusion

Applet and Java Web Start represent two distinct Java client deployment models, yet both depended on historical deployment components that are no longer provided as before in newer JDKs and modern browsers. Therefore, migration cannot be accomplished merely by changing the compiler target or bumping the Java runtime version.

For systems still using Applets, the focus is separating business logic from the browser host and moving the UI to web or desktop. For standalone Java Web Start, you can evaluate a standalone JNLP launcher as a transitional measure, or transition to desktop distribution with a bundled runtime via `jlink` and `jpackage`. Whichever path is chosen, simultaneously manage the entrypoint, security, updates, code signing, client/server compatibility, and installer testing in the final target environment.
