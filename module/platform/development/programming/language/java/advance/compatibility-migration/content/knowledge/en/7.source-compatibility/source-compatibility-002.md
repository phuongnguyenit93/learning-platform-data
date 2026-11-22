# Wildcard Imports and Class Names Colliding with New APIs

## 1. Why Can Imports Become an Issue When Upgrading the JDK?

In Java, `import` statements allow source code to use short type names instead of always writing full package names. Many projects use wildcard imports such as:

~~~java
import java.util.*;
import com.example.model.*;
~~~

This style is concise when a package has many types in use. However, when upgrading the JDK, the platform may add a new class or interface sharing the same simple name as an existing type in a third-party library or another project package.

Source code that previously compiled cleanly because only one type had that name in active imports can become ambiguous after switching to a new JDK, as the new JDK type enters name-lookup scope. The compiler may report an error because it cannot determine which type is intended.

Classic examples include:

- Java 9 added `java.lang.Module`.
- Java 16 added `java.lang.Record`.
- Java 21 added `java.util.SequencedCollection`, `SequencedSet`, and `SequencedMap`.

Types in `java.lang` are implicitly imported into every compilation unit. Therefore, conflicts can appear even when source code never writes `import java.lang.*;`.

During migration, audit wildcard imports alongside class names matching new APIs, determine which type each usage intends to reference, and fix imports explicitly. Do not rename wholesale based solely on class names because the same name can represent APIs with different purposes and contracts.

## 2. Import Forms in Java

Java has several main import forms:

| Syntax | Meaning |
|---|---|
| `import package.Type;` | Explicitly imports a single specific type. |
| `import package.*;` | Wildcard-imports accessible types declared directly in the package. |
| `import static package.Type.member;` | Explicitly imports a single static member. |
| `import static package.Type.*;` | Wildcard-imports accessible static members of a type. |

Example:

~~~java
import java.util.List;
import java.util.Map;
import java.util.*;

import static java.util.Collections.emptyList;
import static java.util.Collections.*;
~~~

You do not need to declare all these illustrative imports together in the same file; they are shown side by side to illustrate the different forms.

### 2.1. Explicit Single-Type Import

An explicit import specifies the exact package and type:

~~~java
import java.util.List;

public class Catalog {
    private List<String> names;
}
~~~

When reading the source, developers immediately know which package `List` comes from. If another library also defines a `List` type, an explicit import avoids having to deduce it from wildcard imports.

This is the right choice when:

- The type appears in public APIs or method signatures.
- The type name easily collides with JDK or popular library types.
- The project is upgrading the JDK and needs clear control over referenced types.
- One file uses two types from different packages sharing the same simple name.

### 2.2. Wildcard Import

A wildcard import uses `*`:

~~~java
import java.util.*;
~~~

This allows using simple names for accessible types declared directly in `java.util`. It does not recursively import subpackages. For example, `import java.util.*;` does not automatically import types in `java.util.concurrent`.

Wildcard imports:

- Do not enlarge the runtime classpath and do not load all classes in the package into memory.
- Do not create a new runtime dependency.
- Affect only compiler name lookup in source code.
- Can make a simple name ambiguous if multiple wildcard imports provide same-named types.

Thus, wildcard imports do not directly slow down the application or bundle the whole package. Their primary risk lies in readability and name resolution when packages or the JDK change.

### 2.3. Implicit Import from java.lang

Accessible types in `java.lang` are imported implicitly. Hence, source code can use `String`, `Object`, `Thread`, or `Record` without declaring `import java.lang.*;`.

When the JDK adds a new type to `java.lang`, that name participates in name resolution across existing sources. This is why a wildcard import from a third-party package can collide with a new platform API even though the file never declared a wildcard import for `java.lang`.

## 3. How the Compiler Resolves Type Names

To handle conflicts properly, understand the difference between explicit imports and wildcard imports.

### 3.1. Two Wildcard Imports Containing the Same Type Name

Suppose two packages both have a type named `Record`:

~~~java
import com.legacy.model.*;
import com.reporting.model.*;

public class ReportService {
    private Record record;
}
~~~

If both packages contain an accessible type named `Record`, the compiler cannot pick one automatically. The reference `Record` is ambiguous and the source fails to compile.

Classpath ordering does not solve this conflict. Swapping the order of the two import lines does not give either package priority either.

### 3.2. Explicit Import and Wildcard Import

An explicit single-type import clarifies the intended type:

~~~java
import com.legacy.model.Record;
import com.reporting.model.*;

public class ReportService {
    private Record record;
}
~~~

Here, the simple name `Record` resolves via the explicit import. The remaining wildcard import can still serve other types in that package.

If both same-named types are needed in one file, Java has no import alias syntax like some other languages. You can import one type and use the fully qualified name for the other:

~~~java
import com.legacy.model.Record;

public class ReportService {
    private Record sourceRecord;
    private com.reporting.model.Record outputRecord;
}
~~~

If both types appear only a few times, writing the fully qualified name at usage sites can clarify intent better than adding multiple wildcard imports.

### 3.3. Two Explicit Imports Sharing the Same Simple Name

If you declare two explicit imports for two distinct types with the same simple name:

~~~java
import java.util.Date;
import java.sql.Date;
~~~

This is a conflict within the same compilation unit. Remove one import and use the fully qualified name for the other type:

~~~java
import java.util.Date;

public class DateConverter {
    private Date instantDate;
    private java.sql.Date databaseDate;
}
~~~

Java has no import alias to rename a type upon import. Fully qualified names are the direct way to distinguish two types with the same simple name.

### 3.4. Types in the Same Package

Types declared in the same package can be used without an import. A wildcard import cannot override a same-named type already declared in the current package. When a project has an internal type matching a JDK API name, define scope clearly and use fully qualified names if both must be referenced.

## 4. New JDK APIs That Can Cause Name Collisions

New type names can appear in `java.lang` or in packages that projects wildcard-import. Common milestones when upgrading Java:

| Java Version | Added API | Namespace | Common Risk |
|---|---|---|---|
| Java 9 | Module | java.lang | Collides with `Module` types in libraries or wildcard-imported packages. |
| Java 16 | Record | java.lang | Collides with `Record` types in data models or legacy libraries. |
| Java 21 | SequencedCollection | java.util | Collides with same-named types in third-party collection libraries. |
| Java 21 | SequencedSet | java.util | Collides with same-named types in other collection packages. |
| Java 21 | SequencedMap | java.util | Collides with same-named types in other map packages or libraries. |

The list above shows representative examples, not an exhaustive catalog of every API added across Java versions. During migration, cross-check release notes and API documentation of the target JDK against actual type names in your project's dependency graph.

### 4.1. Example: Record After Java 16

Suppose an application has its own type:

~~~java
package com.legacy.model;

public class Record {
    private String id;
}
~~~

Another file uses a wildcard import:

~~~java
import com.legacy.model.*;

public class RecordService {
    private Record current;
}
~~~

Since Java 16, `java.lang.Record` exists and is implicitly imported. At the same time, the name `Record` can be supplied by the wildcard import `com.legacy.model.*`. When both types participate in lookup, the compiler can report an ambiguous type name.

If the intent is to use the legacy data type, import it explicitly:

~~~java
import com.legacy.model.Record;

public class RecordService {
    private Record current;
}
~~~

If referencing the platform base class `java.lang.Record` is also needed, use fully qualified names:

~~~java
private com.legacy.model.Record legacyRecord;
private java.lang.Record javaRecord;
~~~

`java.lang.Record` is the base class for Java record classes. It does not share the same business meaning as an application-defined `Record` class. Do not swap one type for the other merely to silence the compiler error.

### 4.2. Example: Module After Java 9

Java 9 added `java.lang.Module` to represent runtime modules. If a legacy library also provides `com.legacy.runtime.Module` and source uses a wildcard import:

~~~java
import com.legacy.runtime.*;

public class RuntimeInspector {
    private Module current;
}
~~~

The name `Module` can collide with the implicitly imported `java.lang.Module`. Clarify the variable's intent:

~~~java
import com.legacy.runtime.Module;

public class RuntimeInspector {
    private Module legacyModule;
    private java.lang.Module platformModule;
}
~~~

Variable names should also reflect their roles so readers do not confuse a business module with a Java Platform Module System module.

### 4.3. Example: SequencedCollection After Java 21

Java 21 added `SequencedCollection`, `SequencedSet`, and `SequencedMap` in `java.util`. These types represent collections with a defined encounter order of first and last elements, providing uniform first/last operations.

Suppose a third-party collection library also supplies a `SequencedCollection` type:

~~~java
import java.util.*;
import com.vendor.collections.*;

public class SequenceService {
    private SequencedCollection<String> values;
}
~~~

On a JDK earlier than Java 21, `java.util` lacked `SequencedCollection`, so the simple name could resolve to the library's type. When compiling against Java 21 APIs, both wildcard imports can provide same-named types, making the reference ambiguous.

If the application wants the JDK standard type:

~~~java
import java.util.SequencedCollection;
import com.vendor.collections.*;

public class SequenceService {
    private SequencedCollection<String> values;
}
~~~

If the application needs the library's type:

~~~java
import com.vendor.collections.SequencedCollection;

public class SequenceService {
    private SequencedCollection<String> values;
}
~~~

If both are needed:

~~~java
public class SequenceService {
    private java.util.SequencedCollection<String> platformValues;
    private com.vendor.collections.SequencedCollection<String> vendorValues;
}
~~~

The `com.vendor.collections` package is a hypothetical example illustrating a name collision. In a real project, substitute the actual package and type present in your dependencies.

## 5. Wildcard Imports and API Changes by Release

A file can compile on an old JDK yet fail on a new JDK because the set of accessible standard library types has changed. Distinguish the JDK running the compiler from the release API level source code is permitted to use.

### 5.1. Using --release When Preserving an Older API Level

The `--release` option of `javac` selects the target Java version for compilation, covering language level, bytecode, and the permitted standard API set.

For example, if the JDK 21 compiler is used while the application must remain compatible with Java 17:

~~~bash
javac --release 17 -d out -cp "lib/vendor.jar" src/main/java/example/SequenceService.java
~~~

Under this configuration, Java 21's `java.util.SequencedCollection` API is not part of the permitted Java 17 API set. This prevents source code from accidentally depending on APIs newer than the committed support baseline.

If the target is Java 21:

~~~bash
javac --release 21 -d out -cp "lib/vendor.jar" src/main/java/example/SequenceService.java
~~~

Now Java 21 APIs enter compilation scope and name collisions can surface. Using `--release` does not automatically resolve collisions between two same-named types; it only determines which standard APIs may be referenced.

### 5.2. Gradle

With Gradle, configure the toolchain and release according to the project's baseline/target:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

This example uses the JDK 21 compiler while generating a Java 17 bytecode/API target. If the project has decided to raise the API target to Java 21, update `release` accordingly and inspect new type names appearing in source.

### 5.3. Maven

With the Maven Compiler Plugin, declare the target release in project configuration:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

When upgrading the API target to Java 21, update `release` to match the agreed target. Also verify the JDK running Maven and toolchain configuration if Maven uses a separate compiler JDK.

### 5.4. Do Not Use --release to Hide Collisions in a New Target

If the project truly needs Java 21, leaving `release` at Java 17 just to avoid import errors does not fulfill the migration requirement. Decide which type is intended, fix the imports, and test behavior. The `release` level should reflect the lowest Java version the artifact commits to supporting, not serve as a temporary way to suppress compile errors.

## 6. Wildcard Static Imports

Wildcard imports also appear in `import static`:

~~~java
import static java.util.Collections.*;
import static com.example.CollectionHelpers.*;
~~~

These statements bring accessible static members of both types into name-lookup scope. If both provide a method with the same name, an unqualified call can become hard to resolve or ambiguous depending on signatures and overload resolution rules.

Example:

~~~java
import static java.lang.Math.*;
import static com.example.NumericHelpers.*;

public class Calculation {
    double result = max(10.0, 20.0);
}
~~~

If both sources provide a `max` method matching the call, the compiler cannot choose a unique method. The fix is to explicitly import the desired member or qualify the call with the class name:

~~~java
double platformMax = java.lang.Math.max(10.0, 20.0);
double customMax = com.example.NumericHelpers.max(10.0, 20.0);
~~~

During migration, audit static wildcard imports whenever a new JDK adds static members or when upgrading utility libraries. The general rule remains making the source of the invoked member clear.

## 7. How to Resolve Import Conflicts During Migration

When the compiler reports an ambiguous type name after upgrading the JDK, follow a verifiable sequence:

1. Read the exact compiler message and identify the ambiguous simple name.
2. List every package or type capable of supplying that name, including implicitly imported `java.lang`.
3. Determine which type the source code intends to use based on signatures, behavior, dependencies, and business purpose.
4. Replace the relevant wildcard import with an explicit import where the conflict occurs.
5. If the same file requires both types, use a fully qualified name for at least one of them.
6. Inspect generic types, method parameter/return types, constructors, annotations, casts, static members, and test fixtures using the same name.
7. Recompile under the target release and run relevant tests.

Do not fix only the single field line flagged by the error. The same simple name can appear in many places:

~~~java
Record createRecord(Record input) {
    Record copy = new Record();
    return copy;
}
~~~

Ensure parameter types, return types, local variables, and constructors all point to the same intended API.

### 7.1. Choose Explicit Imports for Important Types

A maintainable convention is to explicitly import:

- Types appearing in public method signatures.
- Types with common names like `Date`, `List`, `Set`, `Map`, `Module`, `Record`, `Path`, `Process`, or new types likely to collide.
- Types coming from multiple libraries in the same domain.
- Types appearing in code shared across multiple modules.

Wildcard imports can still be used if allowed by the project style guide and the package creates no conflicts. What matters is not letting import resolution depend on classpath order or assuming a package will never gain new types.

### 7.2. Use Fully Qualified Names When Both Same-Named Types Are Needed

Java does not support import aliases. If a file frequently uses two types with the same name, you can:

- Import the more frequently used type and write the fully qualified name for the other.
- Write fully qualified names for both at critical sites.
- Create domain-named adapters or facades to limit propagation of the legacy type, if that is an intentional architectural change.

Do not rename a public class or change packages solely to work around an import error if doing so breaks other modules' APIs. Resolve it at the compilation-unit level first.

### 7.3. Check IDE Auto-Import and Optimize Imports

IDEs may automatically add, remove, or collapse imports based on import optimization settings. When upgrading the JDK or changing Project SDK:

- Check which type the IDE auto-selects during code completion.
- Inspect the import list after running Optimize Imports.
- Check the wildcard import threshold in code style settings.
- Ensure the IDE Project SDK and compiler/build tool use the same target release.
- Review diffs after organize-imports operations to catch unintended changes.

Do not let the IDE auto-pick a type when two APIs share a name without inspecting the package. Auto-import is a source-editing convenience, not proof of the type's business meaning.

## 8. Searching for Risky Imports in Source Code

At the start of migration, search for wildcard imports across the repository to identify areas for review. For example, with ripgrep:

~~~bash
rg -n '^\s*import\s+[\w.]+\.\*;' --glob '*.java'
rg -n '^\s*import\s+static\s+[\w.]+\.\*;' --glob '*.java'
~~~

Search output is a list to investigate, not a list of bugs. Not every wildcard import causes a conflict. Cross-reference used type names against new APIs and real dependencies.

You can search for key new names in source:

~~~bash
rg -n '\b(Module|Record|SequencedCollection|SequencedSet|SequencedMap)\b' --glob '*.java'
~~~

Searching by simple name can match comments, strings, variable names, or unrelated classes. Inspect each match to determine whether it is a type reference.

In multi-module repositories, search Java source sets per module and track which module owns each file. Do not automatically replace all wildcard imports across the repository merely because one module hit a conflict.

## 9. Verifying After Fixing Imports

After fixing imports, prove that the source compiles with the intended API release and type:

### 9.1. Compile with the Target JDK

Run the project's standard build with the chosen JDK/toolchain. With Gradle:

~~~bash
./gradlew clean compileJava
~~~

With Maven:

~~~bash
./mvnw clean compile
~~~

Do not rely solely on the IDE showing no errors. Building via the wrapper exercises the real configuration CI will run.

### 9.2. Check Signatures and Behavior

If the chosen type has a different API from the old one, review:

- Generic bounds and type inference.
- Method signatures, constructors, and overload resolution.
- Serialization/deserialization.
- Data mapping, persistence, and framework bindings.
- Public APIs of dependent modules or services.

For instance, replacing a third-party collection type with the JDK's `SequencedCollection` can alter interfaces visible to other modules. Despite similar names, never assume two types share identical contracts, iteration ordering, mutability, serialization, or binary compatibility.

### 9.3. Run Tests and Inspect Diffs

Run unit tests and integration tests covering the modified component. Especially verify places where the type crosses module boundaries or is serialized into data. Afterward, inspect the diff to ensure only necessary imports and references were changed.

## 10. Project Conventions to Prevent Collisions

To reduce errors in future JDK upgrades, a project can adopt conventions such as:

- Prefer explicit imports for types used in public APIs and commonly named types.
- Limit wildcard imports in packages with many domain-overlapping types or frequent additions.
- Avoid naming business classes after common platform types like `Record`, `Module`, `Thread`, `Process`, or standard collection types when clearer domain names exist.
- When forced to keep a legacy name, explicitly import the package and use fully qualified names where referencing the JDK API.
- Keep compiler release synchronized with the lowest Java version the product commits to supporting.
- When upgrading the JDK, audit release notes/API additions and run compilation on the target JDK.
- Track import ambiguity errors in the source compatibility migration list alongside other compile failures.

These conventions are not meant to ban wildcard imports outright. They keep source code less vulnerable to packages or the JDK adding new types in the future.

## 11. End-to-End Example: Resolving a Conflict When Upgrading Java 17 to Java 21

Suppose an application has an internal collection library and previously used:

~~~java
import java.util.*;
import com.company.collections.*;

public class OrderedCatalog {
    private SequencedCollection<String> entries;
}
~~~

On Java 17, `java.util` did not yet provide `SequencedCollection`. Because the internal library defined that type, source compiled and the simple name resolved via the library import.

When raising the compiler/API target to Java 21, `java.util` now includes `SequencedCollection`. Two wildcard imports now supply two types with the same name, causing the compiler to report an ambiguous reference.

The migration team must decide:

1. Does the application want to use the Java 21 standard API or keep using the internal type?
2. If choosing the standard API, is the internal library still needed?
3. Do other modules depend on the internal type in public APIs?
4. Does switching to the standard type alter ordering, first/last operations, mutability, or serialization behavior?
5. Can the change be rolled out module by module while maintaining cross-module compatibility during the transition?

If choosing the JDK API:

~~~java
import java.util.SequencedCollection;

public class OrderedCatalog {
    private SequencedCollection<String> entries;
}
~~~

If choosing the internal type:

~~~java
import com.company.collections.SequencedCollection;

public class OrderedCatalog {
    private SequencedCollection<String> entries;
}
~~~

If both must be used:

~~~java
public class OrderedCatalog {
    private java.util.SequencedCollection<String> platformEntries;
    private com.company.collections.SequencedCollection<String> legacyEntries;
}
~~~

After selecting, update imports and related signatures, compile with Java 21, run tests, check consuming modules, and review API compatibility. Do not merely swap an import and consider the migration finished.

## 12. Expected Outcomes After Auditing Imports

For each conflict or risky import area, document:

- File and owning module.
- Colliding simple name.
- Packages/types providing that name.
- JDK release before and after migration.
- Selected type and rationale.
- Import or fully qualified name changes applied.
- Impact on public APIs, other modules, and serialization if any.
- Builds/tests executed and results.
- Remaining exceptions, owner, and next handling criteria.

This inventory helps the team distinguish import syntax errors from genuine API changes. An ambiguous reference error may require only an explicit import, whereas switching a type from a library to a JDK API can be a larger compatibility decision. Document the rationale so the next upgrade does not have to re-investigate from scratch.
