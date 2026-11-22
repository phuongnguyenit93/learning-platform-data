# Adding Automatic-Module-Name as a Transitional Step

When a Java library was released in the classpath era without **module-info.java**, an application using the Java Platform Module System (JPMS) can still place that library's JAR on the module path. A JAR without an explicit descriptor will be treated by the module system as an **automatic module**. The problem is that an automatic module's name can be derived from the JAR filename, so it can easily change when the artifact is renamed, packaging conventions change, or a version is upgraded.

The **Automatic-Module-Name** manifest attribute lets library authors assign a stable module name before converting the library into an explicit named module. This is a useful transitional step: consumers begin writing **requires** against an intentional name, while the artifact can still serve classpath applications and does not yet require **module-info.class**.

Key takeaway: **Automatic-Module-Name only stabilizes the name; it does not turn the JAR into an explicit modular JAR and does not automatically create encapsulation boundaries.** Use this attribute to reduce migration risk while preparing a plan to add a proper module descriptor.

## 1. The Problem Before Automatic-Module-Name

Suppose a library is released under the name:

~~~text
acme-codec-1.8.0.jar
~~~

This JAR does not contain a **module-info.class** file. When placed on the module path, Java can create an automatic module with a name derived from the JAR filename according to the module system's rules. The derived name typically strips the version suffix and normalizes separator characters, but it is not a module name contract explicitly published by the library author.

If the JAR is renamed due to an artifact policy change, for example:

~~~text
acme-codec-1.8.0.jar
acme-serialization-codec-2.0.0.jar
~~~

the derived automatic module name can change. An application with a module descriptor:

~~~java
module com.acme.application {
    requires acme.codec;
}
~~~

may no longer resolve the dependency on upgrade when the new module name differs from the previous one. The issue does not necessarily lie in the library's API classes: the same packages and classes may still exist, yet the module name used in **requires** no longer matches.

The **Automatic-Module-Name** attribute addresses part of this risk by decoupling the module name from the JAR filename.

## 2. What Is Automatic-Module-Name?

It is an attribute in the JAR's **META-INF/MANIFEST.MF** file. Example:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.codec
~~~

When a JAR has no explicit module descriptor and is placed on the module path in Java 9 or later, the module system prefers the **com.acme.codec** value as the automatic module name instead of deriving the name from the filename.

Example:

~~~text
mlib/
└── acme-codec-1.8.0.jar
    └── META-INF/
        └── MANIFEST.MF
~~~

If the manifest contains:

~~~text
Automatic-Module-Name: com.acme.codec
~~~

then another named module can declare:

~~~java
module com.acme.application {
    requires com.acme.codec;
}
~~~

The name **com.acme.codec** can be preserved across many artifact versions even if the JAR filename changes.

This value must be a valid module name according to JPMS rules. Use a package-like name following reverse-domain naming conventions, such as **com.acme.codec**, **org.example.csv**, or **io.example.transport**. Avoid generic names like **util**, **common**, or **core** because they easily collide with other dependencies.

## 3. What Automatic-Module-Name Changes and Does Not Change

When a library lacks module-info.class, the module name can come from the manifest. Other automatic module rules still apply.

| Aspect | After adding Automatic-Module-Name |
|---|---|
| Automatic module name | Uses the name declared in the manifest |
| Named consumer dependency | Can write **requires** with a stable module name |
| Explicit **module-info.class** | Not present yet |
| Exported packages | The automatic module still exports all of its packages |
| Deep reflection | The automatic module still opens packages according to automatic module rules |
| Library's explicit dependency graph | Not yet described by an author-written set of **requires** |
| Usability on the classpath | The JAR can still be used via the classpath mechanism |
| Maven/Gradle dependency version | Not managed by the manifest attribute |
| Ability to become an explicit module later | Yes, if a descriptor is released with the same name and matching API contract |

This means **Automatic-Module-Name** is not a replacement for **exports**, **opens**, **uses**, or **provides**. It only solves naming during the automatic module phase.

In an automatic module, readability and encapsulation rules are geared toward broader compatibility than in an explicit module. Legacy libraries can thus join the module path more easily, but consumers can still depend on implementation packages that the author never designated as a stable API.

## 4. When Should You Add This Attribute?

This is an appropriate step when one or more of the following conditions apply:

1. The library is not yet ready to publish **module-info.java** because it still supports older Java environments or has unmodularized dependencies.
2. Applications are gradually migrating to JPMS and need to declare **requires** on the library.
3. The JAR filename contains classifiers, version metadata, or suffixes that may change across releases.
4. Maintainers want to keep the module name stable so they can add an explicit descriptor later without forcing consumers to change **requires**.
5. The library already appears as an automatic module in the runtime graph and needs to reduce identity instability during migration.

If the library already has an explicit **module-info.class**, adding **Automatic-Module-Name** does not override the module name in the descriptor. When an explicit descriptor is present, the name in the descriptor is authoritative.

If the library does not yet have consumers using the module path, this attribute can still be added early as a way to publish the intended module name. However, it does not automatically bring encapsulation benefits to classpath applications.

## 5. Choosing a Stable Module Name from the Start

The name published in the manifest becomes part of the contract for using the library on the module path. Therefore, do not treat it as an easily changeable build detail.

Some principles:

- Use a clearly namespaced name, typically following reverse-domain naming.
- Choose a unique name for one logical module; avoid reusing the same name across different libraries.
- Do not include versions in the module name, e.g., avoid **com.acme.codec.v2** just because the artifact reaches 2.0.
- Do not name it after the current JAR filename if the filename is a temporary packaging detail.
- Determine the intended module name for the future explicit descriptor right when choosing the manifest name.
- Check that the name does not collide with system modules or other modules in the runtime dependency graph.
- Document the module name in release notes so consumers do not have to guess.
- Avoid renaming the module; if a rename is unavoidable, treat it as a migration impacting consumer source descriptors.

Example of a chosen name:

~~~text
Artifact: com.acme:codec-core:1.8.0
JAR: codec-core-1.8.0.jar
Automatic-Module-Name: com.acme.codec
Future module-info.java: module com.acme.codec { ... }
~~~

Maven coordinates and module names are two different identification systems. GroupId, artifactId, and version are used by build tools to select artifacts; JPMS uses the module name to resolve modules.

## 6. Adding the Manifest Attribute with Maven

If the project packages JARs using Maven, you can configure **maven-jar-plugin** to write the manifest attribute.

Example in **pom.xml**:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <configuration>
        <archive>
          <manifestEntries>
            <Automatic-Module-Name>com.acme.codec</Automatic-Module-Name>
          </manifestEntries>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

In real projects, pin the plugin version according to your build policy or manage the plugin version in a parent POM. This illustration focuses on where the manifest attribute goes.

Package the library:

~~~bash
mvn clean package
~~~

Read back the manifest of the generated artifact using JDK or ZIP/JAR tools to confirm the module name is actually present, rather than just looking at the POM configuration.

If the build pipeline also produces a **sources JAR**, **javadoc JAR**, or shaded JAR, identify which artifact consumers actually use on the module path. The attribute must be in the released runtime JAR, not only in secondary artifacts.

If the project uses another plugin to create an uber-JAR or repackage the artifact, verify whether the final packaging step preserves **META-INF/MANIFEST.MF** and the **Automatic-Module-Name** attribute.

## 7. Adding the Manifest Attribute with Gradle

With Gradle Groovy DSL, you can configure the **jar** task:

~~~groovy
tasks.named('jar', Jar) {
    manifest {
        attributes(
            'Automatic-Module-Name': 'com.acme.codec'
        )
    }
}
~~~

Then run:

~~~bash
./gradlew clean jar
~~~

With Gradle Kotlin DSL, the equivalent configuration is:

~~~kotlin
tasks.named<Jar>("jar") {
    manifest {
        attributes(
            "Automatic-Module-Name" to "com.acme.codec"
        )
    }
}
~~~

In a multi-project build, configure the specific subproject that produces the library. Do not assign the same module name to all subprojects via shared configuration if the subprojects produce different modules.

If the release pipeline turns a regular JAR into a fat JAR, shadow JAR, or another packaged artifact, inspect the final artifact's manifest. A stable module name only helps consumers if the exact artifact used at runtime carries that attribute.

## 8. Verifying the Artifact Has Automatic-Module-Name

Build configuration is not proof that the released JAR contains the manifest attribute. Verify on the output file.

First, check that the JAR does not accidentally contain an explicit descriptor:

~~~bash
jar --list --file build/libs/codec-core.jar
~~~

If the listing has **module-info.class** at the root, it may already be an explicit modular JAR rather than just an automatic module. If there is no descriptor, proceed to inspect the manifest and how the JDK recognizes the module.

Use:

~~~bash
jar --describe-module --file build/libs/codec-core.jar
~~~

The output describes the module the JDK recognizes from the JAR. For a JAR without a descriptor, the tool may describe the automatic module and its derived or manifest-supplied name. Exact output formatting depends on the JDK; what matters is whether the module name and automatic status are right.

You can verify directly in Java using **ModuleFinder**:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

public class InspectModule {
    public static void main(String[] args) {
        ModuleFinder finder = ModuleFinder.of(
            Path.of("build/libs/codec-core.jar")
        );

        ModuleReference reference = finder
            .find("com.acme.codec")
            .orElseThrow();

        System.out.println(reference.descriptor().name());
        System.out.println(reference.descriptor().isAutomatic());
    }
}
~~~

For a legacy JAR with only the manifest attribute, the expected name is **com.acme.codec** and **isAutomatic()** is **true**. Later, if the artifact gains an explicit descriptor, the name can stay the same while **isAutomatic()** must be **false**.

This is an important verification distinguishing **name stabilization** from **explicit modularization**.

## 9. Using the Library from a Named Module Consumer

Suppose the library JAR is located at:

~~~text
mlib/
└── codec-core-1.8.0.jar
~~~

The JAR contains:

~~~text
Automatic-Module-Name: com.acme.codec
~~~

The consumer application has a descriptor:

~~~java
module com.acme.application {
    requires com.acme.codec;
}
~~~

The application can import the library's public classes by their actual packages:

~~~java
package com.acme.application;

import com.acme.codec.api.Codec;

public class Main {
    public static void main(String[] args) {
        System.out.println(new Codec().encode("hello"));
    }
}
~~~

To compile and run, both the application module and the automatic module must be on the module path, for example once the appropriate artifacts exist:

~~~bash
javac --module-path mlib -d out \
  src/com.acme.application/module-info.java \
  src/com.acme.application/com/acme/application/Main.java
~~~

~~~bash
java --module-path "mlib:out" \
  -m com.acme.application/com.acme.application.Main
~~~

These two commands illustrate POSIX syntax, where module path entries are separated by colons. On Windows, use semicolons between entries, e.g., **"mlib;out"**. Source/output layout may differ when building multi-module systems; adjust for your actual exploded module directories or modular JARs.

If the application cannot find **com.acme.codec**, verify the manifest name and module path before editing **requires**. Adding a JAR to the classpath does not allow a named consumer to read it via **requires com.acme.codec**.

## 10. Compatibility with Java 8 and Classpath Applications

One advantage of **Automatic-Module-Name** is that it is purely manifest metadata. For applications running on Java 8 and using the JAR on the classpath, this attribute does not turn the library into a named module and does not make Java 8 read a JPMS descriptor.

Consequently, a JAR without module-info.class can:

- Continue running on Java 8 as long as its bytecode and APIs remain Java 8–compatible.
- Have a stable automatic module name when placed on the module path of Java 9 or later.
- Serve both classpath and module-path consumers during the transition period.

However, merely adding the manifest attribute **does not guarantee** Java 8 compatibility. If the library was compiled to newer bytecode or uses APIs only available in newer Java releases, it still will not run on Java 8. The build must still configure compiler release/target settings and run tests against the supported version.

The manifest attribute reduces migration friction, but does not replace the library's JDK support policy.

## 11. Remaining Limitations of Automatic Modules

### 11.1. No Explicitly Designed Exports

An automatic module exports its packages under compatibility rules. Consumers can import public classes in implementation packages even though the author never considered them stable APIs.

This can cause consumers to build dependencies on internal details. When converting to an explicit module and exporting only true API packages, those consumers will fail to compile or run if they still use internal classes.

Therefore, as soon as you use Automatic-Module-Name, clearly document which packages are considered stable APIs and test that consumers use only those packages.

### 11.2. Dependencies Are Not Declared with Explicit requires

Automatic modules use special readability rules to support legacy JARs. They do not contain a set of **requires** reviewed by the library author like an explicit module descriptor.

When converting to an explicit module, the author must determine the actually required dependencies, distinguish **requires**, **requires transitive**, and **requires static**, and verify the module graph.

A working runtime with an automatic module is not enough to conclude the new descriptor will be valid.

### 11.3. Reflection and Frameworks May Break When Modularizing

Automatic modules open packages broadly for compatibility with legacy code and reflection. Once an explicit descriptor is added, unopened packages are subject to strong encapsulation of named modules.

ORM, JSON serialization, or dependency injection frameworks may require **opens** or appropriate public APIs. Do not change module status without integration tests covering code paths that use reflection.

### 11.4. Service Metadata May Need Migration

Legacy JARs may declare service providers via **META-INF/services/** files. The module system has a mechanism to interpret service metadata for automatic modules, whereas explicit modules need **provides ... with ...** matching the contract, and named consumers need **uses** when calling ServiceLoader.

When migrating to an explicit descriptor, verify service discovery with real runtime tests. Do not assume keeping META-INF/services guarantees identical behavior across every layer.

### 11.5. Does Not Solve Split Packages

If two JARs both contain classes belonging to the same package, adding Automatic-Module-Name does not turn them into one valid module. When both are placed on the module path, the split package can still cause conflicts around readability, exports, or class-loader mapping.

Separate namespaces, merge artifacts when appropriate, or replace dependencies; do not use the manifest attribute as a workaround for split packages.

## 12. Choosing When to Move to module-info.java

Once the library and its dependencies are ready for real module boundaries, move from an automatic module to an explicit module.

A future descriptor might look like:

~~~java
module com.acme.codec {
    requires java.logging;

    exports com.acme.codec.api;
    opens com.acme.codec.model to com.acme.serializer;

    uses com.acme.codec.spi.CodecExtension;
    provides com.acme.codec.spi.CodecExtension
        with com.acme.codec.internal.DefaultCodecExtension;
}
~~~

This is an illustrative example only. The actual descriptor must match the real packages, dependencies, and service types in the library. Do not copy sample directives into a project if the corresponding module does not exist or a package does not need reflection.

Migration principles:

1. **Keep the module name stable:** the name in **module-info.java** should match the name already published via **Automatic-Module-Name** unless there is a compelling reason to change.
2. **Define the public API:** export only the packages consumers are truly supported to use.
3. **Declare dependencies:** write requires for actual dependencies and review transitivity when public APIs expose types from other modules.
4. **Handle reflection:** open only the required packages to the necessary frameworks, avoiding opening the entire module.
5. **Handle services:** declare uses/provides per the contract and test provider discovery.
6. **Resolve structural issues:** resolve split packages, cycles, or classpath dependencies before publishing the descriptor.
7. **Test consumers:** run compilation, unit tests, integration tests, and launch on the target JDK/module path.
8. **Release in a controlled manner:** update release notes so consumers know the module transitioned from automatic to explicit.

Moving to an explicit module can expose dependencies on internal packages that were previously exported by the automatic module. This is a consumer-impacting change; provide migration guidance rather than treating it as a user error.

## 13. If You Still Need Java 8 Support Once You Have module-info.class

The **module-info.class** file is a JPMS component introduced in Java 9. A library wanting an explicit descriptor on Java 9+ while still supporting Java 8 execution can consider a **multi-release JAR**.

One packaging strategy is keeping Java 8–compatible classes at the root and placing the module descriptor in the Java 9 area:

~~~text
codec-core.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       └── 9/
│           └── module-info.class
└── com/acme/codec/...
~~~

The manifest must declare the corresponding multi-release attribute:

~~~text
Multi-Release: true
~~~

When using a multi-release JAR, JDK 9+ can see the version-appropriate descriptor according to packaging rules, while a Java 8 runtime uses the compatible contents at the root. This workflow is more complex than just adding Automatic-Module-Name: it requires building multiple bytecode targets, packaging entries accurately, and testing on both Java 8 and newer JDKs.

If the team does not need an explicit module immediately, using Automatic-Module-Name first is a simpler transitional choice. However, do not prolong it indefinitely if the end goal is strong encapsulation and a complete module descriptor.

## 14. Risks of Renaming a Module Across Versions

Adding Automatic-Module-Name for the first time can itself be a breaking change.

For example, an older version lacked the manifest attribute and Java automatically derived the name **acme.codec.core**. An application declared:

~~~java
module com.acme.application {
    requires acme.codec.core;
}
~~~

A new version adds:

~~~text
Automatic-Module-Name: com.acme.codec
~~~

The module name then changes from **acme.codec.core** to **com.acme.codec**. Consumers must update **requires**. Even though the library's Java code did not change, changing the module name is a JPMS contract change.

To minimize impact:

- Inventory consumers using the module path and the old automatic module name.
- Pick the new name with a long-term strategy so it will not change again across releases.
- Clearly document both the old and new names in release notes.
- Give consumers time to update **module-info.java** and launcher configurations.
- Verify the module path does not simultaneously contain two JARs with the same module name or two conflicting library versions.
- When appropriate, keep the name consumers already use reliably instead of picking a prettier name that forces widespread changes.

There is no general module name aliasing mechanism in JPMS equivalent to a symlink between two module names. If a rename is necessary, you must coordinate consumers and actual artifacts.

## 15. Common Errors and How to Resolve Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| JAR is on classpath but named consumer reports module not found | Classpath does not provide named modules for requires | Place the JAR on the proper runtime module path |
| Module name differs from expected | Manifest attribute was not packaged, or name was derived from filename | Inspect the final artifact with jar --describe-module |
| isAutomatic() still returns true | The manifest attribute does not create an explicit descriptor | This is the expected state during the transition phase |
| Added manifest but program fails to run on Java 8 | Bytecode/APIs are incompatible with Java 8 | Adjust compiler target/release and test on Java 8 |
| Consumer fails after module rename | requires still uses the old automatic module name | Update consumer descriptors and launcher flags |
| Build produces correct JAR but shadow/fat JAR has wrong manifest | Final packaging step overwrites or drops metadata | Configure the manifest for the final artifact |
| Runtime reports duplicate module names | Two artifacts are recognized with the same module name | Remove duplicate artifacts and unify dependency resolution |
| Runtime reports conflicting packages | Split package between dependencies | Fix package/artifact layout; do not rely on module names |
| Consumer uses an implementation class that the explicit module will hide | Previous automatic module exported broadly | Replace with supported API or design a migration path |
| ServiceLoader loses provider after switching to explicit module | Descriptor missing provides/uses or provider is unresolved | Check service metadata, configuration, and layers |

A helpful rule is to keep three separate pieces of evidence: **the manifest has the right attribute**, **the JDK reads the right module name**, and **the actual application resolves that module**. Any single condition alone is not enough to claim the transition works.

## 16. Controlling via CI and Release Documentation

For libraries shared across many projects, you can add automated checks after JAR creation:

1. Build the exact runtime artifact as it will be published.
2. Verify the manifest contains **Automatic-Module-Name** with the committed name.
3. Verify the JAR does not accidentally contain an explicit descriptor if the current release is still intended to be automatic.
4. Use **ModuleFinder** or **jar --describe-module** to confirm the module name recognized by the JDK.
5. Compile a simple named consumer with **requires** matching the name to verify integration.
6. Run a smoke test with the artifact on the module path.
7. For libraries still supporting Java 8, run compatibility tests on Java 8.
8. Include the module name in release notes and library API documentation.

Example small CI check in Java:

~~~java
ModuleReference ref = ModuleFinder
    .of(Path.of("dist/codec-core.jar"))
    .find("com.acme.codec")
    .orElseThrow(() -> new AssertionError("Wrong module name"));

if (!ref.descriptor().isAutomatic()) {
    throw new AssertionError("Unexpected explicit descriptor");
}
~~~

This snippet is only suitable during the phase when the JAR is expected to remain an automatic module. When releasing an explicit modular JAR, invert the check: the module name stays the same, while **isAutomatic()** must be **false**.

For large projects, maintain a migration table tracking artifact, current module name, planned explicit module name, owner, deadline, and migration status. Having CI checks and owners prevents Automatic-Module-Name from becoming a permanent stopping point.

## 17. Practical Migration Roadmap

You can execute along these steps:

| Phase | Key tasks | Completion criteria |
|---|---|---|
| 1. Inventory | Identify legacy JARs, derived module names, and module-path consumers | Know which dependencies rely on derived names |
| 2. Choose name | Design a stable module name, avoiding collisions | Name has an owner and is documented |
| 3. Manifest | Add Automatic-Module-Name to the runtime JAR | Final artifact contains the correct manifest attribute |
| 4. Verify | Use ModuleFinder, jar --describe-module, and named consumer tests | JDK recognizes the right name; still an automatic module |
| 5. Migrate consumers | Update requires and launcher configs as needed | Consumers compile and run on the module path |
| 6. Prepare explicit descriptor | Analyze dependencies, exports, opens, services, and split packages | Have a testable module-info.java design |
| 7. Release explicit module | Package module-info.class and keep module name stable | ModuleFinder reports isAutomatic() = false |
| 8. Pay down tech debt | Remove temporary flags/adapters no longer needed | Tests pass, module boundaries are clear |

You do not have to force all dependencies into explicit modules at the same time. However, clearly distinguish which components remain automatic and which already have descriptors, rather than treating both as equivalent simply because both have module names.

## 18. Practice Exercises

1. Create a Java library without **module-info.java**, and build it into a JAR containing **com.acme.codec.api.Codec**.
2. Place the JAR on the module path and run **jar --describe-module** to observe the derived automatic module name.
3. Add **Automatic-Module-Name: com.acme.codec** to the manifest using Maven or Gradle.
4. Rebuild and inspect the module name with **ModuleFinder**; confirm **isAutomatic()** is **true**.
5. Create module **com.acme.application** with **requires com.acme.codec**, compile, and run on the module path.
6. Rename the JAR file while keeping the manifest attribute, and confirm the module name remains **com.acme.codec**.
7. Remove the manifest attribute and rename the JAR file to observe the risk of derived automatic module names.
8. Try placing the same JAR on the classpath, and verify that its classes belong to the unnamed module rather than a named module.
9. Create an explicit **module-info.java** using the name **com.acme.codec**, exporting only the API package, and compare access rules with the automatic module.
10. If the library uses reflection or service providers, re-verify opens and provides after moving to explicit.
11. Write a CI test confirming the module name does not change across two builds.
12. Discuss the conditions required to eliminate the automatic module state completely from the runtime graph.

## 19. Key Takeaways

- **Automatic-Module-Name** is a manifest attribute inside a JAR's **META-INF/MANIFEST.MF**.
- It assigns the automatic module name when a JAR without module-info.class is placed on the module path.
- It does not create **module-info.class**, declare **requires**, restrict **exports**, or replace a module descriptor.
- An automatic module is still a named module, but has broader compatibility rules than an explicit named module.
- On the classpath, this attribute does not turn a JAR into a named module.
- The manifest attribute alone does not guarantee Java 8 bytecode compatibility; build and test separately.
- Keep the name from Automatic-Module-Name when publishing an explicit module-info.java later.
- Renaming an automatic module can break consumer **requires** clauses.
- Maven/Gradle must write the attribute into the final runtime artifact; always inspect the JAR after packaging.
- Achieving strong encapsulation requires an explicit descriptor with intentionally designed exports/opens and dependencies.
- A good roadmap includes transitional steps, completion criteria, assigned owners, and automated checks.

**Automatic-Module-Name is a promise about a name, not a promise that the library has finished modularizing.** Use it to stabilize **requires** relationships during migration; then gradually transition to module-info.class, controlling API packages, reflection, and services to build genuine module boundaries.
