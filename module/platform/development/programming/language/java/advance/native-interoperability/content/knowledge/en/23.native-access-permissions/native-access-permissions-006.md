# Checking or Granting Native Access to Dynamic Modules Within Permitted API Scope

## 1. Goal: Native Access Is Tied to Modules, Not Just Function Calls

When integrating Java with C/C++ using the **Foreign Function & Memory API (FFM)** or **Java Native Interface (JNI)**, certain operations cross the managed boundary of the JVM. For example: calling restricted FFM methods, opening a native library, performing downcalls/upcalls, or using JNI native methods. These operations can cause memory corruption or crashes if native code, layouts, pointers, or resource lifecycles are handled incorrectly.

Java manages **native access** per **module**. A module can be permitted by the runtime to perform restricted operations (*restricted operations*), and a program can query whether that module has the permission enabled:

```java
Module current = MyClass.class.getModule();
boolean enabled = current.isNativeAccessEnabled();
```

For modules created **dynamically** inside a `ModuleLayer`, the API also allows **an entity that already has native access** to grant permission to a target module within the layer it controls:

```java
ModuleLayer.Controller controller = ...; // returned by defineModules*
Module plugin = ...;                     // belongs to the controller's exact layer

controller.enableNativeAccess(plugin);   // restricted API
```

Two main methods in this lesson:

- `Module.isNativeAccessEnabled()`: **checks** whether a module has native access enabled; available since **JDK 22**; does not grant permission itself.
- `ModuleLayer.Controller.enableNativeAccess(Module)`: **grants permission** to a module in the controller's exact layer; **the grant operation itself is also restricted**; available since **JDK 22**.

**Key takeaway:** a dynamic plugin cannot arbitrarily grant native access to itself via a setter. This permission is only enabled by **the launcher/runtime configuring the module** or **controlled delegation** via `ModuleLayer.Controller`, from code that already has native access. A controller cannot arbitrarily modify any module in the JVM.

### Versions and Safety of the Examples

- The `Module.isNativeAccessEnabled` and `ModuleLayer.Controller.enableNativeAccess` APIs have existed since **Java 22**.
- The standalone runnable examples in this lesson use **JDK 24+**, because they use `--illegal-native-access=deny` to create a verifiable fail-closed scenario. The module code uses standard JDK 22+ APIs, but this flag was introduced in JDK 24 via JEP 472.
- Compiled and run on **JDK 24**. The outputs illustrate the initial state, the restricted operation being denied before granting permission, and succeeding after granting permission.
- Starting in JDK 24, the default mode for some unenabled native access is `warn`; therefore "missing permission" may **emit a warning and allow the operation to proceed** in warn mode. The test program **intentionally uses `deny`** to distinguish between valid and invalid states and to prepare for stricter enforcement modes in the future.

### After This Lesson, What Will You Be Able to Do?

1. Identify which module is calling a restricted API, without confusing class loaders with module identity.
2. Check permission using `getModule().isNativeAccessEnabled()`.
3. Create a named module in a **dynamic module layer** with a controller.
4. Ensure the host module has been granted native access by the launcher before delegating.
5. Enable permission for the right module in the layer via `controller.enableNativeAccess(target)`.
6. Handle `IllegalCallerException` and `IllegalArgumentException` in the proper context.
7. Distinguish native access from `exports`, `opens`, `reads`, and Java reflection permissions.
8. Design a plugin loader with a least-privilege trust policy, without handing the controller to untrusted plugins.

## 2. What Is Native Access and Why Do Modules Need It?

Native access protects **the safety boundary between the Java runtime and code outside the JVM**. Java cannot prove at all times that a native address is within bounds, a C callback has a valid lifetime, or a C ABI declaration is valid.

Examples of restricted FFM operations from the Java 24 documentation:

| API/Action | Why native access is required |
| --- | --- |
| `Linker.downcallHandle(...)` | Calling a native function may use an incorrect prototype or ABI |
| `Linker.upcallStub(...)` | Allows native code to hold/call a Java callback; lifecycle and signature risks |
| `MemorySegment.reinterpret(...)` | Can widen a view beyond the size or scope of the actual allocation |
| `AddressLayout.withTargetLayout(...)` | Declares the size of the region a native pointer points to, which may not actually exist |
| `SymbolLookup.libraryLookup(...)` | Loads and looks up native symbols from a library capable of executing machine code |
| `System.load(...)`/`System.loadLibrary(...)` | Loads native code into the JVM process |
| `ModuleLayer.Controller.enableNativeAccess(...)` | Transfers a restricted permission to another module |
| JNI native method declarations/calls under JDK 24 policy | Touches native runtime outside pure Java checks |

**Important:** not **every** method in `java.lang.foreign` is restricted. For instance, `MemorySegment.ofArray(...)` or `Arena.ofConfined().allocate(...)` can be used as normal Java APIs. However, if you want to call `withTargetLayout` or create a restricted downcall handle, the calling module needs native access according to the runtime policy.

Native access is **not** "operating system administrator privilege" and does not prove that native code is benign. It is **an explicit acknowledgment by the application owner** that the module is permitted to cross certain JVM integrity boundaries. The operating system still has its own ACLs, sandbox/process permissions, and dynamic loader rules.

## 3. Which Module Is Checked?

When code calls a restricted API, the permission is tied to **the module containing the caller**, not the module of a passed-in object, an arbitrary JAR name, or the JDK module containing the API.

```java
Module mine = Example.class.getModule();

System.out.println(mine.getName());              // module name, may be null
System.out.println(mine.isNamed());               // true/false
System.out.println(mine.isNativeAccessEnabled()); // true/false
```

Concepts to distinguish:

- **Named module:** has a module name, usually defined from `module-info.java` in the boot layer or a dynamic layer. For example `demo.host`, `demo.plugin`.
- **Unnamed module:** typically contains code on the **classpath**. Multiple class loaders have their own unnamed modules. Depending on the flag, `--enable-native-access=ALL-UNNAMED` enables permission for **all unnamed modules**.
- **ModuleLayer:** a set of named modules defined from a `Configuration` and one or more parent layers.
- **ModuleLayer.Controller:** a sensitive object that allows the creator of a layer to add read/export/open edges and has `enableNativeAccess` for modules of that layer.
- **ClassLoader:** loads classes; **not synonymous** with a module or a layer. One class loader can manage multiple named modules, while a module resides in exactly one layer (or special module kinds outside a layer).
- **Dynamic named module:** a module defined at runtime, for example a plugin read from a separate module path and created with `ModuleLayer.defineModulesWithOneLoader(...)`.

`Module.getLayer()` returns the layer for a named module if it has one; **an unnamed module does not reside in a module layer**, so you cannot obtain a controller and arbitrarily enable native access for an unnamed module that way.

There is no general public method like `myModule.enableNativeAccess()` that any code can call to elevate its own privileges. The real pattern in the JDK is `ModuleLayer.Controller.enableNativeAccess(target)` with the constraints below.

## 4. Two Ways to Grant Permission: Launcher and Controller

### 4.1. Granting Permission at Startup

For a **named module** named `demo.host`:

```bash
java --enable-native-access=demo.host \
     --module-path mods \
     -m demo.host/demo.host.LayerHost
```

Inside the host module:

```java
Module me = LayerHost.class.getModule();
System.out.println(me.isNativeAccessEnabled()); // true
```

For code on the classpath:

```bash
java --enable-native-access=ALL-UNNAMED -cp out MyMain
```

Every unnamed module gets permission enabled when using `ALL-UNNAMED`. This may be **broader than necessary**: an untrusted dependency on the classpath also gets native access if loaded into an unnamed module.

**Production recommendation:** if possible, move components requiring JNI/FFM into a named module and use `--enable-native-access=module.name` to limit scope; do not enable `ALL-UNNAMED` merely for convenience.

### 4.2. Modules Created After JVM Startup: Controller

If a plugin module is not defined in the boot layer when the JVM starts, but only appears when the plugin manager creates a new layer, the JVM launcher does not have a target module instance available to grant permission via the object API.

When creating a dynamic layer, you can retain the `ModuleLayer.Controller` returned by one of the static factory methods:

```java
ModuleLayer.Controller controller =
        ModuleLayer.defineModulesWithOneLoader(
                configuration,
                List.of(ModuleLayer.boot()),
                ClassLoader.getSystemClassLoader());

ModuleLayer layer = controller.layer();
Module target = layer.findModule("demo.plugin").orElseThrow();

controller.enableNativeAccess(target);
```

**Preconditions for `enableNativeAccess`:**

1. The caller is running in a module that **already has native access** (or is permitted by the runtime under the corresponding policy; with `deny`, missing permission throws `IllegalCallerException`).
2. `target` must be a module **in the exact layer managed by the controller**; otherwise, `IllegalArgumentException`.
3. `enableNativeAccess` is a **restricted method**, so behavior when the caller does not have permission enabled also depends on the JDK version and `--illegal-native-access` policy.
4. Host code should verify that the plugin is trusted, check artifact version/provenance, and confirm the need for native access before granting permission, rather than doing so immediately for every plugin.

A controller has the ability to **delegate** within its layer, not "root access to grant to every module" across the entire JVM.

## 5. Trust Flow of a Plugin Loader

Model:

```text
                  JVM startup
                      |
             --enable-native-access=demo.host
                      |
                      v
           module demo.host (trusted)
             native access = true
                      |
              create child ModuleLayer
                      |
                      v
           module demo.plugin (new)
             native access = false
                      |
       Check trusted release / allowlist / checksum
                      |
            policy allows plugin to use native?
             /                       \
           NO                         YES
           |                           |
     Do not grant             controller.enableNativeAccess(
     deny task                        target)
     requiring native                  |
                                       v
                               plugin native access = true
```

There are two boundaries:

- **Caller permission boundary:** the host must have native access first. A plugin **must not use the host's controller to self-escalate** when untrusted.
- **Layer boundary:** the controller can only manage modules belonging to **the layer it created**. It cannot be used to modify `java.base` or an arbitrary module in the boot layer.

For a plugin requiring native code, granting permission is a **trust decision** equivalent to allowing a native library to run in the same process. Verify file signatures/hashes, provenance, version, and which libraries may be loaded; do not rely on a single flag to protect against malicious C/C++ code.

## 6. Complete JDK 24+ Example: Named Host Creates and Grants Permission to a Dynamic Plugin

This example uses **two named modules**:

- `demo.host`: the module that runs first, granted native access by the JVM via a launcher flag.
- `demo.plugin`: the module loaded by the host into a **dynamic layer**, initially without native access.
- The plugin calls the restricted method `ValueLayout.ADDRESS.withTargetLayout(JAVA_INT)` solely to **check permission**; it does not dereference a pointer, so no C library is needed and there is no risk of invalid native memory access.
- The host attempts to call the plugin before granting permission in `deny` mode, catches `IllegalCallerException` via `InvocationTargetException`, then grants permission and calls it again.

### 6.1. Directory Tree

```text
native-module-lab/
  src/
    demo.host/
      module-info.java
      demo/host/LayerHost.java
    demo.plugin/
      module-info.java
      demo/plugin/PluginNative.java
  mods/                        # generated by javac
```

No JNI C compiler or external library is required, only JDK 24+.

### 6.2. File `src/demo.host/module-info.java`

```java
module demo.host {
    // Host does not need to require demo.plugin at compile time.
    // Plugin is only resolved in the layer created at runtime.
}
```

Omitting `requires demo.plugin` is **intentional**. If the host required the plugin module at startup, the plugin could be resolved into the boot layer instead of the child layer as intended by this lesson.

### 6.3. File `src/demo.plugin/module-info.java`

```java
module demo.plugin {
    exports demo.plugin;
}
```

`exports demo.plugin` allows the host to call public methods of `demo.plugin.PluginNative` via normal reflection. Native access and Java module exports are **two independent mechanisms**; adding an export **does not** grant native access.

### 6.4. File `src/demo.plugin/demo/plugin/PluginNative.java`

```java
package demo.plugin;

import java.lang.foreign.ValueLayout;

public final class PluginNative {
    public static long safeProbe() {
        return ValueLayout.ADDRESS
                .withTargetLayout(ValueLayout.JAVA_INT)
                .targetLayout()
                .orElseThrow()
                .byteSize();
    }
}
```

`withTargetLayout` is a restricted FFM method; it attaches a layout to a pointer type. `targetLayout().orElseThrow().byteSize()` will be 4 because `JAVA_INT` represents a 4-byte value.

**There is no dereference** in this demo; it demonstrates the presence/absence of native access, not a lab on native pointer safety.

### 6.5. File `src/demo.host/demo/host/LayerHost.java`

```java
package demo.host;

import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

public class LayerHost {
    public static void main(String[] args) throws Exception {
        Module self = LayerHost.class.getModule();

        ModuleFinder finder = ModuleFinder.of(Path.of(args[0]));
        Configuration config = ModuleLayer.boot().configuration().resolve(
                finder,
                ModuleFinder.of(),
                Set.of("demo.plugin"));

        ModuleLayer.Controller ctrl =
                ModuleLayer.defineModulesWithOneLoader(
                        config,
                        List.of(ModuleLayer.boot()),
                        ClassLoader.getSystemClassLoader());

        Module target = ctrl.layer()
                .findModule("demo.plugin")
                .orElseThrow();

        Class<?> clazz = ctrl.layer()
                .findLoader("demo.plugin")
                .loadClass("demo.plugin.PluginNative");

        System.out.println("Host access: "
                + self.isNativeAccessEnabled());
        System.out.println("Plugin before: "
                + target.isNativeAccessEnabled());

        // Because the JVM runs with --illegal-native-access=deny,
        // the plugin is not yet allowed to perform the restricted operation.
        try {
            clazz.getMethod("safeProbe").invoke(null);
            throw new AssertionError(
                    "Plugin operation unexpectedly succeeded");
        } catch (InvocationTargetException expected) {
            if (!(expected.getCause() instanceof IllegalCallerException)) {
                throw expected;
            }
            System.out.println("Before grant: denied");
        }

        // Host trusted module already has native access.
        // target belongs to ctrl's exact layer.
        ctrl.enableNativeAccess(target);

        System.out.println("Plugin after: "
                + target.isNativeAccessEnabled());
        System.out.println("Probe target bytes: "
                + clazz.getMethod("safeProbe").invoke(null));
    }
}
```

This is a **complete program**. It uses `ModuleFinder.of(path)` to locate modular classes, `Configuration.resolve` to resolve the graph, `ModuleLayer.defineModulesWithOneLoader` to create a child layer and return the controller, and then finds **the actual module in the child layer**.

**Distinction to keep in mind:** `LayerHost.class.getModule()` is the host module, granted permission at JVM startup; `target` is the dynamically created `demo.plugin` module. If you only set `--enable-native-access=demo.host` without calling the controller, **the plugin still does not automatically inherit** the host's native access.

### 6.6. Compilation

From the `native-module-lab` directory:

```bash
javac --module-source-path src -d mods -m demo.host,demo.plugin
```

If using PowerShell on Windows, the same `javac` command can be run directly in a configured Java/JDK terminal. The `src/demo.host` and `src/demo.plugin` structure must follow `--module-source-path` rules.

### 6.7. Running with Host Permission and Deny Policy

```bash
java \
  --enable-native-access=demo.host \
  --illegal-native-access=deny \
  --module-path mods \
  -m demo.host/demo.host.LayerHost \
  mods
```

Single line for PowerShell/Windows:

```powershell
java --enable-native-access=demo.host --illegal-native-access=deny --module-path mods -m demo.host/demo.host.LayerHost mods
```

**Stdout executed on JDK 24:**

```text
Host access: true
Plugin before: false
Before grant: denied
Plugin after: true
Probe target bytes: 4
```

### 6.8. Reading the Output in Order

1. `Host access: true` because module `demo.host` was specified at the launcher.
2. `Plugin before: false` because the plugin is in a new dynamic layer and has not yet been granted permission by the controller.
3. In `deny` mode, the restricted `withTargetLayout` call from a plugin without native access throws `IllegalCallerException`; reflection wraps it in `InvocationTargetException`, and the host catches **the exact cause**.
4. `ctrl.enableNativeAccess(target)` is called from a host module that already has permission; the `target` module is a member of this layer, so the grant succeeds.
5. `Plugin after: true` reflects the native access state just enabled for the plugin module.
6. The second call to `safeProbe` works, returning 4 bytes according to the `JAVA_INT` layout.

For real permission checks, you can place `isNativeAccessEnabled` logic **directly inside the plugin** for friendly diagnostics before calling FFM:

```java
Module me = PluginNative.class.getModule();
if (!me.isNativeAccessEnabled()) {
    throw new IllegalStateException("Native access is not enabled");
}
```

This snippet needs to be placed **inside the PluginNative class**, not run standalone. Such a check provides a clear message, but **does not grant permission itself**.

## 7. What Happens If the Host Does Not Have Native Access?

Omit the `--enable-native-access=demo.host` flag while keeping `--illegal-native-access=deny`:

```bash
java --illegal-native-access=deny \
  --module-path mods \
  -m demo.host/demo.host.LayerHost \
  mods
```

In that case:

- `LayerHost.class.getModule().isNativeAccessEnabled()` is `false`.
- `demo.plugin` is also not granted permission.
- The plugin's restricted probe is denied.
- When the host code calls `ctrl.enableNativeAccess(target)`, **the grant itself is restricted**, and the caller does not have native access enabled; under `deny` mode, it throws `IllegalCallerException`.

You cannot use the plugin's controller to create a "bypass" for granting permission when the host module is denied. This is how the delegation model is preserved: **an unauthorized entity cannot validly grant permission to another entity** in strict mode.

**Note on JDK 24 `warn` mode:** JEP 472 documentation states that unpermitted restricted operations may only emit a warning and still execute. In testing with JDK 24 `--illegal-native-access=warn`, an `enableNativeAccess` call from a host module without permission enabled **emitted a warning but still completed**. Therefore, **do not treat warn behavior as a safe permission-granting mechanism in production**. Use `deny` in CI to catch missing permissions and plan for stricter modes in future JDK releases.

### 7.1. Distinguishing Three Different States

| Condition | `isNativeAccessEnabled()` | Restricted operation in JDK 24 `deny` mode |
| --- | --- | --- |
| Host has permission via launcher | `true` | Can call `Controller.enableNativeAccess` for the right target |
| Plugin not yet granted | `false` | Throws `IllegalCallerException` when calling a restricted FFM method itself |
| Plugin granted via controller | `true` | Can perform restricted methods, but must still obey ABI/lifetime |

In `warn` mode, a module may still report `false` and the restricted operation may still execute with a warning. Therefore `isNativeAccessEnabled()` reflects **formal authorization**, not an absolute prediction of whether the next statement will fail under all warning policies.

## 8. Layer Boundary: Cannot Grant Permission to Modules Outside the Controller

According to the `ModuleLayer.Controller.enableNativeAccess(Module)` API:

- If `target` is not in the layer managed by the controller: `IllegalArgumentException`.
- If the caller does not have native access and the restricted operation is denied: `IllegalCallerException`.
- If `target == null`: `NullPointerException` per the controller's general contract.
- A plugin layer's controller is **not** the boot layer's controller and cannot grant permission to arbitrary boot modules, such as `java.base`.

Example testing the wrong layer:

```java
Module javaBase = Object.class.getModule();

try {
    ctrl.enableNativeAccess(javaBase);
    throw new AssertionError("Unexpected grant");
} catch (IllegalArgumentException expected) {
    System.out.println("Other layer: rejected");
}
```

The snippet assumes `ctrl` is the controller of a **dynamic child layer** and the caller **already has** native access. If the caller also lacks permission, policy and check ordering may affect which exception is thrown first; do not use that code as a test when both conditions are false.

**Verified on JDK 24** with an authorized host: passing `Object.class.getModule()` (which belongs to `java.base` in the boot layer) to the child layer's controller was rejected and printed:

```text
Other layer: rejected
```

As a result, you can design a plugin manager with clear ownership: the controller for layer A cannot be used to update layer B just because of a similar module name.

## 9. Second Example: Host Running on the Classpath and Unauthorized Test Case

In the named host example, selective permission granting is optimal. To directly test the scenario where **the caller has not been granted permission by the launcher**, you can run a host belonging to an unnamed module and compare the two modes.

On the classpath, the host module has `getName() == null`. If you use:

```bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny ...
```

then the host has native access, while the dynamic named plugin can still **lack** permission. This is proof that native access **is not automatically inherited through classloaders or parent layers**.

On JDK 24, a classpath host test with a dynamic plugin module produced two results:

**With `--enable-native-access=ALL-UNNAMED`:**

```text
Host native access: true
Actual module matches: true
Dynamic before: false
Before grant: denied
Dynamic after: true
Restricted target bytes: 4
Other layer: rejected
```

**Without `--enable-native-access`, keeping `--illegal-native-access=deny`:**

```text
Host native access: false
Actual module matches: true
Dynamic before: false
Before grant: denied
Grant denied: caller has no native access
Other layer: rejected
```

The two transcripts above are Java 24 test results with host code using `ModuleLayer.defineModulesWithOneLoader` and the same restricted `withTargetLayout` in the plugin; they are **variants of the example**, not the stdout of the named-module `LayerHost` in section 6.

**Do not confuse:** `--enable-native-access=ALL-UNNAMED` opens access for all classpath code, and **does not** automatically enable native access for a named `demo.plugin` residing in a dynamic layer. For production with many dependencies, prefer a `demo.host` named module over `ALL-UNNAMED`.

## 10. Interaction with Native Restriction Modes Across JDK Versions

### 10.1. Java 22 and 23

`Module.isNativeAccessEnabled` and `Controller.enableNativeAccess` have been available since JDK 22. Standard FFM was finalized in the same JDK. However, the `--illegal-native-access` option and JNI warnings were developed in JDK 24 under JEP 472; do not run the JDK 24 example command with `--illegal-native-access=deny` verbatim on JDK 22/23 and mistake it for a Java source error.

On JDK 22/23, verify behavior against the policy documented for the version in use; granting native access via `--enable-native-access` remains the primary launcher mechanism.

### 10.2. Java 24: Explicit warn/deny

JEP 472 unifies restrictions on JNI and FFM:

- `--illegal-native-access=allow`: allows unpermitted restricted operations to proceed.
- `--illegal-native-access=warn`: allows execution with a warning; default in JDK 24.
- `--illegal-native-access=deny`: denies with `IllegalCallerException`, suitable for fail-closed testing and detecting modules lacking permission.

The documentation states that `deny` will become the default in a future release; **do not assume the default of all newer JDKs solely from JDK 24 behavior**. Check the documentation for the exact Java runtime being deployed.

### 10.3. Where Can It Be Configured?

Example with a named module:

```bash
java --enable-native-access=demo.host -m demo.host/demo.host.LayerHost
```

You can pass the option in launcher arguments, `JDK_JAVA_OPTIONS`, an argument file, or a `jlink` runtime image configuration. The `Enable-Native-Access: ALL-UNNAMED` manifest attribute exists for executable JAR scenarios, but has **broad scope**. Do not arbitrarily modify a customer's command line or runtime configuration just to silence warnings without evaluating the risk.

**Do not mix up with `--enable-preview`:** native access and preview language/API features are two different mechanisms.

## 11. Distinguishing Native Access from opens, exports, and reads

The module system has separate permissions:

| API/flag | Purpose | Grants restricted native access? |
| --- | --- | --- |
| `requires`/`Module.addReads` | Establishes a readability edge between modules | No |
| `exports`/`Module.addExports` | Allows other modules to access public types of a package | No |
| `opens`/`Module.addOpens` / `--add-opens` | Allows deep reflection on a package under certain conditions | No |
| `--add-exports` | Exports a specific package at the launcher | No |
| `--enable-native-access` | Enables native access for specified module(s) | Yes |
| `ModuleLayer.Controller.enableNativeAccess` | Enables native access for a target module in a dynamic layer within scope | Yes, but the method itself is restricted |
| `Module.isNativeAccessEnabled` | Reads native access status | Does not change permission |

For example, `module demo.plugin { exports demo.plugin; }` allows the host to call `PluginNative.safeProbe()` via reflection, yet the first call still fails with `IllegalCallerException` on `withTargetLayout` when the policy is `deny`.

Conversely, enabling native access **does not automatically open** private fields or packages of the plugin to the host. If the host encounters `IllegalAccessException` during reflection, fix module exports/opens according to architectural policy instead of adding `--enable-native-access`.

Similarly, `controller.addReads` and `controller.addOpens` have their own purposes in a plugin loader, but **do not replace** `enableNativeAccess`.

## 12. Checking Permission in a Plugin Before Performing a Native Operation

A wrapper can proactively provide diagnostics:

```java
public static void requireNativeAccess(Class<?> owner) {
    Module module = owner.getModule();

    if (!module.isNativeAccessEnabled()) {
        String name = module.isNamed()
                ? module.getName()
                : "ALL-UNNAMED";

        throw new IllegalStateException(
                "Native access is not enabled for " + name);
    }
}
```

This is an **illustrative method** that needs to be placed in an application class. `owner` should be the class that actually contains the code calling the restricted FFM/JNI operation. Do not trust a user-supplied module name just because it resembles the module needing permission.

Correct workflow:

1. Check the exact module of the caller.
2. If not yet enabled, stop according to product policy or request formal permission from the host.
3. For a dynamic module verified as trusted, only a host that already has native access calls `controller.enableNativeAccess`.
4. After granting, you may call `isNativeAccessEnabled` again to confirm the state.
5. The actual native operation must still handle library loading, FFM descriptors, exceptions, ABI, memory lifetime, and ownership.

Do not call a restricted operation and ignore warnings/`IllegalCallerException` by retrying or using reflection hacks. The proper fix is **granting the right permission to the right module through official channels**.

### 12.1. isNativeAccessEnabled Does Not Prove Native Code Is Safe

A module with `isNativeAccessEnabled() == true` can still:

- Use `MemorySegment.reinterpret` with the wrong size and access freed memory.
- Create a `Linker.downcallHandle` with the wrong C calling convention.
- Load a DLL/so with the wrong architecture or version.
- Call JNI native code that corrupts the heap.
- Have insufficient OS permissions to open files, sockets, devices, or attach a debugger.

Native access is **authorization to perform risky operations**, not a certification of ABI, provenance, or lifecycle correctness.

## 13. Why Not Hand the Controller to Untrusted Code?

The `ModuleLayer.Controller` Javadoc includes an API note: exercise caution and **do not share the Controller with untrusted code**. Reasons include:

- `enableNativeAccess` can propagate restricted permission from an authorized caller.
- `addReads`/`addExports`/`addOpens` mutate the module graph and can inadvertently expose internal APIs.
- A plugin given the controller itself could ask the host to create/grant permissions to modules not approved by product policy.
- Native access is granted per **module**, not per method. Once enabled, any code in that module can potentially call restricted methods under runtime conditions, not just a single entrypoint.

Good architectural pattern:

```text
Trusted PluginManager
  - keeps controller private
  - verifies plugin identity / release manifest
  - approves native permissions allowlist
  - resolves target Module from controller.layer()
  - calls enableNativeAccess itself
  - only exposes restricted interface to plugin

Untrusted plugin
  - does not hold controller
  - does not decide native configuration of other modules
  - does not change loader policy itself
```

**Do not confuse with a strong sandbox:** a plugin granted native access can execute native code that breaks JVM memory safety. For truly untrusted plugins, module boundaries/Controllers do not replace **process isolation or OS sandboxing**. Run untrusted code in a separate process with restricted privileges if strict isolation is required.

### 13.1. Can Native Access Be Revoked After Being Enabled?

`ModuleLayer.Controller` has `enableNativeAccess(Module)` but **does not expose a reverse method to immediately revoke it** in the JDK 24 API. Do not build a plugin manager assuming you can "enable for a moment and then disable again" for the same module.

If native access is only needed for a short phase, consider a separate-process architecture and process lifecycle, or only load permanently approved plugins. Do not rely on `ModuleLayer` GC as a security/revocation mechanism.

### 13.2. Do Not Grant Permission to Multiple Modules Just Because They Share a Classloader

A controller can define multiple modules in the same loader. Calling `enableNativeAccess(pluginA)` is **not** a command that opens permission for the entire loader or module layer. Grant to the **specific** module after verification:

```java
Module selected = ctrl.layer().findModule("demo.plugin")
        .orElseThrow();

if (policyAllowsNative(selected)) { // application policy pseudocode
    ctrl.enableNativeAccess(selected);
}
```

`policyAllowsNative` is an application-defined function; the snippet above is **pseudocode**, not a runnable Java program. Every decision must be based on the real module identity and verified artifact, not merely a string name if the name could be spoofed by a plugin.

## 14. Distinguishing Dynamic Modules, Dynamic Proxies, and Unnamed Modules

The phrase "dynamic module" is often misunderstood:

- **Dynamic module layer:** uses `ModuleFinder`/`Configuration`/`ModuleLayer.defineModules*` to create a **named module** at runtime. This is the case supported by `ModuleLayer.Controller.enableNativeAccess`.
- **Dynamic proxy class:** `Proxy.newProxyInstance` can generate a class in a dynamic module, but native access cannot be arbitrarily granted to a runtime-managed module that your controller does not own. Do not assume every "dynamic module" has an application-owned controller.
- **Unnamed classpath module:** has no name/layer like a named module. Permission is granted via launcher `ALL-UNNAMED`, not through a plugin layer controller.
- **Boot layer module:** resolved by the JVM launcher; native access is typically granted via launcher options. Do not take a child layer's controller to modify the boot layer.

A module named `demo.plugin` in a child layer and a module with the same name in another layer (if configuration permits) **are not the same Module object**. Do not look up by string on layer A and then use controller B.

## 15. Common Errors When Writing a Plugin Loader

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `Plugin before: false` even though host has native access | Permission is not automatically inherited by dynamic named modules | Host calls `enableNativeAccess` for the right target |
| `IllegalCallerException` on `enableNativeAccess` | Caller is not enabled and runtime is in deny mode | Grant permission to host via launcher, do not bypass |
| `IllegalCallerException` on FFM restricted method in plugin | Plugin has not been enabled | Grant to plugin via the right controller before calling |
| `IllegalArgumentException` on `enableNativeAccess` | Target does not belong to the layer managed by the controller | Obtain module from `controller.layer()` |
| `NoSuchElementException` on `findModule` | Plugin was not resolved into the layer or wrong name | Check `ModuleFinder`/`Configuration` |
| `FindException` / `ResolutionException` | Invalid module descriptor/dependencies | Fix module graph or module path |
| `LayerInstantiationException` | Error defining layer, loader/packages | Check `ModuleLayer` factory constraints |
| `ClassNotFoundException` when loading plugin class | Wrong class name/module path/class loader | `layer.findLoader(moduleName)` |
| `IllegalAccessException` when reflecting | Plugin package is not properly exported/opened | Fix `exports`/`opens`, do not confuse with native access |
| Enabled `--add-opens` but native is still denied | Deep reflection != native access | Use `--enable-native-access`/controller |
| Running JDK 22 and JVM does not recognize `--illegal-native-access` | This flag is JDK 24+ | Read docs for your JDK, use the right command line |
| JDK 24 defaults to only warning when permission is missing | `warn` mode can still execute | Test with `--illegal-native-access=deny` |
| Enabled `ALL-UNNAMED` but named plugin still lacks permission | `ALL-UNNAMED` only applies to unnamed modules | Use controller with dynamic named module |
| Module has native enabled but still gets `UnsatisfiedLinkError` | Library not found, wrong arch/deps | Check OS loader, native library path/ABI |
| Module has native enabled but C code crashes | Incorrect ABI, pointer, or lifetime | Check FFM/JNI and native code, not just flags |
| Controller leaked outside the host | Untrusted code can request module graph/permission changes | Keep controller private and enforce policy |
| Want to revoke after enabling | API does not expose revoke | Use process isolation/different lifecycle |

## 16. Checklist for Reviewing an enableNativeAccess Call

1. Which module is the caller in? Is `callerClass.getModule()` used to verify accurately?
2. Is the host's `isNativeAccessEnabled()` true in **deny** mode after launcher configuration?
3. Is the plugin module a **new named module** in the right dynamic layer? Are there name/class hierarchy collisions?
4. Is the controller kept by the trusted host, not returned to plugins or user code?
5. Was `target` retrieved from `controller.layer().findModule(...)` rather than a module object from another layer?
6. Do `ModuleFinder` and `Configuration` read the right plugin binary/JAR and dependency graph?
7. Does the plugin artifact have a verified signature/checksum or allowlist before granting permission?
8. Are you sure the plugin actually **needs** FFM/JNI native access, not just Java reflection/exports?
9. Is permission enabled only for approved modules, rather than automatically enabling every module in the layer?
10. Does CI run `--illegal-native-access=deny` to catch errors hidden by warning mode?
11. Are there negative tests for a host lacking permission, a target in the wrong layer, and an ungranted plugin?
12. Are native libraries also checked for provenance/ABI/ownership rather than being arbitrary DLL/so files?
13. Does deployment documentation clearly specify `--enable-native-access=host.module` and JDK versions?
14. Is there a plan if permission needs to be revoked? Do not confuse module-unload/GC with secure revocation.

## 17. Self-Check Exercises

**Question 1.** Does `Module::isNativeAccessEnabled` grant permission itself?

**Answer:** No. It only returns the native access status of the current module without changing permissions. Granting permission to a dynamic named module uses `ModuleLayer.Controller.enableNativeAccess` subject to the API's conditions.

**Question 2.** The host is granted `--enable-native-access=demo.host` and creates module `demo.plugin` in a child layer. Is the plugin enabled by default?

**Answer:** No. A new module does not automatically inherit the host's native access; in the executed example, `Plugin before: false`.

**Question 3.** A caller without native access calls `enableNativeAccess` in JDK 24 `deny` mode. What happens?

**Answer:** `IllegalCallerException`. Permission must be granted by the launcher first; a controller is not a valid path for self-escalation.

**Question 4.** Can a plugin layer's controller grant native access to `java.base` in the boot layer?

**Answer:** No. `target` is not in the layer, resulting in `IllegalArgumentException` when the caller already has permission.

**Question 5.** Does `--enable-native-access=ALL-UNNAMED` enable a named plugin in a dynamic layer?

**Answer:** Not automatically. That flag applies to unnamed modules, whereas a named plugin must be granted permission separately through the appropriate mechanism.

**Question 6.** Can JDK 24 in `warn` mode execute a restricted operation even when `isNativeAccessEnabled()==false`?

**Answer:** Yes. That mode allows illegal native access with a warning. Do not use warn mode to conclude that a plugin is formally authorized; CI should use `deny`.

**Question 7.** Why does the `safeProbe` plugin only use `withTargetLayout` without calling a native C function?

**Answer:** Because `withTargetLayout` is already a restricted API, sufficient to test native access; there is no need to load a C library or dereference a dangerous pointer. The result of 4 target bytes is a valid layout result.

**Question 8.** Does allowing `--add-opens=demo.plugin/demo.plugin=demo.host` grant native access to the plugin?

**Answer:** No. `opens` only adjusts reflection access to a package; native access is a separate mechanism.

**Question 9.** Should `ModuleLayer.Controller` be passed to an untrusted plugin to configure itself?

**Answer:** No. The controller allows modifying the module graph and granting native access. Keep it in the host and apply an allowlist/provenance check before granting.

**Question 10.** If native access is enabled, does the JVM guarantee that a `MemorySegment.reinterpret` with an incorrect lifetime is safe?

**Answer:** No. Native access only permits the restricted operation; the author remains responsible for memory safety, alignment, size, and lifetime.

**Question 11.** After granting native access to a plugin module, is there a corresponding `disableNativeAccess` API to revoke it immediately?

**Answer:** There is no corresponding revoke in JDK 24's `ModuleLayer.Controller`. If strong isolation or revocation is required, use process boundaries and appropriate lifecycle management.

**Question 12.** If `java -m demo.host/...` fails because a plugin class cannot be found, should you add a native access flag to fix it?

**Answer:** No. Check the module path, resolver, class loader, and `exports`/`opens`. Only grant native access if the error is actually related to a restricted JNI/FFM operation.

## 18. Summary

- `Module.isNativeAccessEnabled()` **checks** the native access status of a module; available since JDK 22.
- `ModuleLayer.Controller.enableNativeAccess(target)` **grants permission** to a module **in the controller's exact layer**, but **it is itself restricted**.
- **The caller must have native access** to validly grant permission in fail-closed mode; use launcher `--enable-native-access=demo.host` for the trusted host, then have the controller grant into the child layer.
- A new plugin module **does not automatically inherit native access** from the host, even when using a related class loader. `ALL-UNNAMED` also does not automatically open access for a named plugin.
- In **JDK 24**, the default `warn` mode may allow illegal operations to run with a warning; set `--illegal-native-access=deny` to detect errors and properly test delegation boundaries.
- Native access **differs** from `reads/exports/opens` and does not replace verifying native libraries, ABI, memory lifetime, or sandboxing.
- The controller is a sensitive object; only the trusted host retains grant authority, **do not share it with untrusted plugins**. There is no corresponding revoke in the JDK 24 controller API.

## Official References

- [Java SE 24 — Module.isNativeAccessEnabled](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Module.html#isNativeAccessEnabled())
- [Java SE 24 — ModuleLayer.Controller.enableNativeAccess](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.Controller.html#enableNativeAccess(java.lang.Module))
- [Java SE 24 — ModuleLayer and layer-defining factories](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ModuleLayer.html)
- [Java SE 24 — Restricted Methods and native-access configuration](https://docs.oracle.com/en/java/javase/24/core/restricted-methods.html)
- [Java SE 24 — List of restricted methods](https://docs.oracle.com/en/java/javase/24/docs/api/restricted-list.html)
- [JEP 472 — Prepare to Restrict the Use of JNI (JDK 24)](https://openjdk.org/jeps/472)
- [JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454)
- [Java SE 24 — java launcher options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)

**Remember:** native access for a dynamic module is **checked via Module**, and when needed is **granted using the layer's own Controller** from an **authorized caller**. Do not mistake warnings in JDK 24 for formal authorization, do not abuse `ALL-UNNAMED`, and do not treat native access as proof that C/JNI/FFM code is safe.
