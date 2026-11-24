# Preserving Service Registration Files When Merging or Relocating Packages in JARs

## 1. Why Can Plugins Disappear After Packaging?

Java SPI (Service Provider Interface) allows an application to discover implementations at runtime via `java.util.ServiceLoader`, without hardcoding implementations in application code. With traditional JAR registration on the classpath/module path, a library declares providers using a text file:

```text
META-INF/services/<fully qualified binary name of the service interface>
```

Each effective line in the file is the **fully qualified binary name of a provider class**; blank lines and anything after `#` are comments. For example:

```text
# META-INF/services/com.example.spi.GreetingProvider
com.example.plugin.EnGreetingProvider
com.example.plugin.ViGreetingProvider
```

In a standard JAR build, resource copying preserves this file as-is. Risk arises during **fat/uber JAR** assembly, **shading**, package **relocation**, or **minimization**: the classes may still exist inside the JAR while the provider goes undiscovered; conversely, metadata may exist yet point to a class that was renamed or stripped from the artifact. This is a bug in the **relationship between bytecode, class names, and registration resources**, and cannot be fixed merely by editing `MANIFEST.MF`.

## 2. Rules That Must Stay Intact

Three elements must remain consistent:

1. **Service type:** the name after `META-INF/services/` must match the fully qualified binary name of the interface/abstract class passed to `ServiceLoader.load(ServiceType.class)`. If relocation renames the service interface's package, the registration **filename** must also be updated.
2. **Provider type:** every class name listed in the file contents must point to a provider actually present in the JAR after relocation. If an implementation changes from `com.example.plugin.Foo` to `shaded.com.example.plugin.Foo`, the name inside the file must change accordingly.
3. **Loadability:** the provider must conform to the SPI contract (compatible with the service type, instantiable by ServiceLoader via the appropriate mechanism), and the active classloader/module layer must see both the metadata and the class.

On the classpath, a provider is typically a public concrete class with a public no-argument constructor. In named Java modules, `provides ... with ...` is the standard declaration mechanism; rules regarding constructors/provider methods differ, so do not extrapolate classpath rules to all modules.

### When Merging Multiple JARs

Two libraries may contain the **exact same path** `META-INF/services/com.example.spi.GreetingProvider`, yet have different contents. If the packaging tool takes one file and overwrites the other, one or more providers will be dropped from the list. The resulting file must preserve the **union** of valid providers, typically by concatenating lines and handling duplicates/comments via the build tool:

```text
# plugin-a.jar
com.example.plugins.EnglishGreeting

# plugin-b.jar
com.example.plugins.VietnameseGreeting

# correct in uber.jar, after merge
com.example.plugins.EnglishGreeting
com.example.plugins.VietnameseGreeting
```

Do not apply a merge strategy that overwrites or arbitrarily concatenates bytes for other configuration resources: `META-INF/services/` has its own semantics. Check framework-specific resources separately if they use different formats.

### When Relocating Packages

Distinguish these cases:

| Change | Registration Filename | File Contents |
| --- | --- | --- |
| Only provider package relocated | Keep service interface name | Update provider name accordingly |
| Service interface package relocated | Update to the new service interface name | Update provider if provider is also relocated |
| JARs merged without relocation | Keep unchanged | Merge provider lists across JARs |
| Provider stripped by minimizer | File may still remain | Must keep declared classes or intentionally remove registration |

Do not rename the file if the application still calls the original service API: `ServiceLoader` looks up the exact service type name it receives.

## 3. Minimal Example Structure

Suppose we have an API and two plugins:

```text
src/
  com/example/spi/GreetingProvider.java
  com/example/plugin/EnglishGreeting.java
  com/example/plugin/VietnameseGreeting.java
  Demo.java
resources/
  META-INF/services/com.example.spi.GreetingProvider
```

`src/com/example/spi/GreetingProvider.java`:

```java
package com.example.spi;

public interface GreetingProvider {
    String greeting();
}
```

`src/com/example/plugin/EnglishGreeting.java`:

```java
package com.example.plugin;

import com.example.spi.GreetingProvider;

public final class EnglishGreeting implements GreetingProvider {
    public EnglishGreeting() {}
    @Override public String greeting() { return "Hello"; }
}
```

`src/com/example/plugin/VietnameseGreeting.java`:

```java
package com.example.plugin;

import com.example.spi.GreetingProvider;

public final class VietnameseGreeting implements GreetingProvider {
    public VietnameseGreeting() {}
    @Override public String greeting() { return "Xin chào"; }
}
```

`resources/META-INF/services/com.example.spi.GreetingProvider` (UTF-8):

```text
com.example.plugin.EnglishGreeting
com.example.plugin.VietnameseGreeting
```

`src/Demo.java`:

```java
import com.example.spi.GreetingProvider;
import java.util.ServiceLoader;

public class Demo {
    public static void main(String[] args) {
        for (GreetingProvider provider : ServiceLoader.load(GreetingProvider.class)) {
            System.out.println(provider.greeting());
        }
    }
}
```

Compile and run the example above with Java 17+ in the directory containing `src` and `resources`:

```bash
javac -d out src/com/example/spi/GreetingProvider.java src/com/example/plugin/EnglishGreeting.java src/com/example/plugin/VietnameseGreeting.java src/Demo.java
jar --create --file greetings.jar -C out . -C resources .
java -cp greetings.jar Demo
```

Output (in the order of providers in this example's registration file):

```text
Hello
Xin chào
```

`jar -C resources .` is the essential step: the registration file must be packaged alongside the `.class` files. A JAR containing only classes while omitting `META-INF/services` can still execute the `java` command cleanly, yet the `ServiceLoader` loop prints nothing.

## 4. Build Configuration for Fat/Shaded JARs

### Gradle Shadow

With Gradle and a Shadow plugin compatible with your Gradle version, instruct it to merge SPI files using the dedicated transformer:

```groovy
// build.gradle: example configuration snippet when the Shadow plugin is already applied
tasks.named('shadowJar') {
    mergeServiceFiles()
}
```

`mergeServiceFiles()` merges files under `META-INF/services` from dependencies included in the Shadow JAR. If relocation is enabled, verify in the final artifact that **both the filename and provider names** were updated correctly. Do not assume every transformer or plugin version handles every kind of metadata identically.

An illustrative relocation configuration (when isolating a dependency package):

```groovy
tasks.named('shadowJar') {
    mergeServiceFiles()
    relocate 'com.vendor.impl', 'internal.shaded.com.vendor.impl'
}
```

After building, open the Shadow JAR itself to inspect the `META-INF/services` paths and every line inside. If the service interface belongs to an unrelocated public API, that API's descriptor filename must remain unchanged.

### Maven Shade

With `maven-shade-plugin`, the `ServicesResourceTransformer` transformer merges service descriptors and updates names according to relocations:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-shade-plugin</artifactId>
  <version>3.6.1</version>
  <executions>
    <execution>
      <phase>package</phase>
      <goals><goal>shade</goal></goals>
      <configuration>
        <transformers>
          <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
        </transformers>
        <relocations>
          <relocation>
            <pattern>com.vendor.impl</pattern>
            <shadedPattern>internal.shaded.com.vendor.impl</shadedPattern>
          </relocation>
        </relocations>
      </configuration>
    </execution>
  </executions>
</plugin>
```

This is a configuration snippet to place inside `<plugins>` in `pom.xml`, not a complete POM. When changing plugin versions, check the documentation and build output of the exact version in use.

### Manually Assembled JARs

If using a custom script to unpack dependencies into a directory and re-pack them, unpacking can overwrite SPI files that share the same path. You must collect all service descriptors prior to unpacking, merge the lists by service type, update names upon relocation, and then write the consolidated file into the artifact. Using Shadow/Shade is generally safer and easier to maintain because they have specialized SPI resource handling.

## 5. How to Verify the Final Artifact

Looking at the source tree or running unit tests on the IDE's classpath is not enough: errors can occur **only after packaging**. Inspect the actual JAR file that will be distributed.

List metadata:

```bash
jar --list --file build/libs/app-all.jar
```

Look for entries starting with `META-INF/services/`. Inspect a descriptor's contents (`unzip -p` if the unzip tool is available):

```bash
unzip -p build/libs/app-all.jar META-INF/services/com.example.spi.GreetingProvider
```

Cross-check with `jar --list` to verify that provider classes are present at paths matching their binary names (`com.example.plugin.EnglishGreeting` → `com/example/plugin/EnglishGreeting.class`). With relocation, verify every name **after** transformation.

Run a smoke test against the **packaged JAR** using a classpath/module path matching the deployment environment, enumerating providers rather than merely checking that no exception is thrown:

```java
long count = ServiceLoader.load(GreetingProvider.class).stream().count();
if (count != 2) {
    throw new AssertionError("Expected 2 providers, found " + count);
}
```

This is a **Java snippet placed inside a method or test**, not a command runnable directly in a shell. With the `ServiceLoader.stream()` API, iterating can trigger provider/configuration checks; also verify instantiation and actual behavior by iterating instances as in `Demo`.

A useful CI check: build the artifact → read all service descriptors → verify every provider references an existing class → run a `ServiceLoader` test against that artifact. For optional plugins, verify the exact **expected provider set for each distribution configuration**, avoiding hardcoding a single count across all environments.

## 6. Common Errors and Fixes

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| `ServiceLoader` returns 0 providers | Descriptor not packaged, wrong filename, or classloader cannot see the JAR | Check `META-INF/services/<service FQCN>`, resources in the artifact, and the classloader |
| Some plugins missing after fat JAR | One descriptor overwrote another | Use a service-file merging transformer; check all providers after merge |
| `ServiceConfigurationError: Provider ... not found` | Descriptor points to old name after relocation or class was stripped by minimizer | Update provider names and keep rules; cross-check JAR contents |
| `ServiceConfigurationError: ... not a subtype` | Mismatch between provider/service API; possibly duplicate API class in another classloader | Ensure provider implements the exact loaded service type |
| Works in IDE, fails in fat JAR | Build packages resources differently from development classpath | Inspect the final JAR directly and run smoke tests against it |
| Plugin loaded on module path does not appear | Classpath descriptor does not replace a named module's declaration | Use valid `uses` and `provides ... with ...` in `module-info.java`, check the module layer |

Additional note: `ServiceLoader` uses lazy discovery and caching; when changing classpath/plugins at runtime, you may need to create a new loader or call `reload()` on the appropriate loader instance. However, `reload()` **cannot fix missing or broken metadata inside the JAR**.

## 7. The Java Module System (JPMS) Case

In a statically declared **named module**, providers are published via the module descriptor:

```java
module com.example.plugin {
    requires com.example.spi;
    provides com.example.spi.GreetingProvider
        with com.example.plugin.EnglishGreeting;
}
```

The consumer module typically declares:

```java
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.GreetingProvider;
}
```

When shading/relocating a module that has `module-info.class`, changing packages or classes can break `requires`, `exports`, `opens`, `uses`, `provides`, and module signatures/identity. Do not assume merging `META-INF/services` files is sufficient to combine multiple named modules into one valid named module. When using **automatic modules** or running JARs on the classpath, provider discovery behaves differently from named modules with `module-info.class`; always test in the exact deployment mode.

## 8. Plugin Release Checklist

- Identify the exact public service interfaces and provider classes that must be preserved.
- Inspect every dependency JAR containing `META-INF/services/<service>`; record the provider list before merging.
- Configure service descriptor merging when building fat/uber JARs and update metadata names when relocating.
- Verify that minimizers/obfuscators do not strip or rename providers without synchronizing metadata; use keep rules or disable minimization for required SPIs.
- Read descriptors and class lists **from the final artifact**, rather than inferring from source.
- Test `ServiceLoader` on the packaged artifact inside the target classloader/module layer.
- Run an integration test with at least two providers from two dependencies when proving a merge preserves both.
- If the library is packaged in multiple variants, test each variant; do not assume a regular `jar` and `shadowJar` have identical contents.

**Operational principle:** preserving SPI registration means keeping the **descriptor path**, the **provider name contents**, and the **corresponding class bytecode** aligned after every merge, relocation, or optimization step. Only by verifying all three on the final artifact can you be sure plugins will be discovered properly at runtime.
