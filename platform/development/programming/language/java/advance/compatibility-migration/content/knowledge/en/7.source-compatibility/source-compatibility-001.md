# Identifiers, Keywords, and New Type Names That Can Conflict

When upgrading Java versions, a project may stop compiling even though its business logic has not changed. Sometimes the cause comes from small language changes: a name previously allowed as a variable or type becomes a keyword, a restricted identifier gains new semantics, or the JDK adds a type to an automatically imported or wildcard-imported package. These conflicts typically surface at compile time and can affect source code, shared libraries, generated sources, or annotation-processor output.

This lesson belongs to **Java Advance Compatibility Migration**, in the **Source Compatibility** chapter. It explains the types of name collisions when changing the Java source level, how to recognize errors caused by keywords and new types, how to fix them safely, and the verification process to avoid altering application behavior.

## 1. Why Can a Name Valid in an Older Java Version Become a Problem?

The Java language evolves across releases. Each version can introduce:

- New keywords to represent language constructs.
- Restricted identifiers or contextual keywords carrying special meaning in specific contexts.
- New types in JDK packages.
- New methods, constructors, or overloads on existing types.
- New syntax that changes how the parser interprets a piece of code.

A previously valid identifier can fall into one of these cases:

1. Become a keyword and no longer be allowed as an identifier.
2. Become a restricted identifier, restricted only in certain syntactic positions.
3. Remain valid in most positions yet be interpreted differently in a new syntactic context.
4. Collide with a new type supplied by the JDK, making a simple type name ambiguous.
5. Collide with a newly inherited or imported API, causing an expression that previously resolved uniquely to have multiple resolutions.

For example, an older codebase might contain:

~~~java
public class Record {
    private String value;
}
~~~

The capitalized type name `Record` remains a valid Java identifier. However, since Java 16, the JDK added `java.lang.Record` as the base class for record classes. If other source code uses a wildcard import for the package containing the application's `Record` while also receiving types from `java.lang`, a simple reference to `Record` can become ambiguous.

Another example is a variable name:

~~~java
int yield = 10;
~~~

The name `yield` can appear as an identifier in certain positions, yet since Java 14, `yield` is used in the `yield` statement syntax of switch expressions. If source code uses this name in a syntax-sensitive context, check how the compiler parses the expression.

Therefore, during migration, distinguish a word that looks like a keyword from one that is genuinely forbidden everywhere. Java has true keywords, restricted identifiers, and contextual keywords.

## 2. Distinguishing Keywords, Restricted Identifiers, and Contextual Keywords

### 2.1. True Keywords

A keyword is a token reserved for Java syntax. You cannot use a keyword as the name of a variable, method, class, interface, package, or type parameter.

Examples:

~~~java
int class = 10;       // Invalid
class return { }      // Invalid
String package = "";  // Invalid
~~~

Several keywords were added across historical releases:

| Keyword | Relevant Java Version | Meaning |
|---|---:|---|
| assert | Java 1.4 | Runtime condition check when assertions are enabled |
| enum | Java 5 | Declares an enumeration type |
| _ | Java 9 | A single underscore becomes a keyword |
| const, goto | Since early versions | Reserved keywords without standard Java functionality |

Many words have long been keywords, such as `public`, `private`, `static`, `final`, `class`, `interface`, `extends`, `implements`, `return`, `throw`, `try`, and `catch`.

A notable migration point is an identifier consisting solely of a single underscore. Prior to Java 9, some codebases used it as a variable or lambda parameter name:

~~~java
String _ = readValue();
~~~

Since Java 9, a single underscore is a keyword and can no longer be used as an identifier. If you need a name representing an ignored value, use a meaningful name or another identifier:

~~~java
String ignoredValue = readValue();
~~~

Names starting with an underscore followed by other characters, such as `_value`, are not keywords just because they begin with an underscore.

### 2.2. Restricted Identifiers

A restricted identifier is not a general keyword in every position. The language restricts its use in certain syntactic positions to reserve room for new features.

Important examples:

| Restricted Identifier | Relevant Version | Context to Watch |
|---|---:|---|
| var | Java 10 | Restricted as a type name in type declaration contexts; supports local variable type inference |
| yield | Java 14 | Used in the `yield` statement of switch expressions; certain unqualified method invocations may be affected |
| record | Java 16 | Used to declare record classes; restricted when used as a type name |
| sealed | Java 17 | Modifier for sealed classes/interfaces |
| permits | Java 17 | Declares permitted subtypes of a sealed type |

For instance, `var` is not a universal keyword. A variable name like this can be valid:

~~~java
int var = 10;
System.out.println(var);
~~~

However, using `var` as a type name in a class or interface declaration can be invalid:

~~~java
class var { }  // Invalid in source levels supporting var
~~~

Meanwhile, local variable type inference uses `var` in the type position:

~~~java
var total = 100;
var names = List.of("An", "Binh");
~~~

Distinguish `var` in local variable declarations from field, parameter, or return-type declarations. Java does not permit `var` for type inference across all declaration kinds.

Similarly, `record` is reserved for record declaration syntax:

~~~java
public record CustomerId(String value) { }
~~~

The lowercase identifier `record` carries syntactic meaning in this declaration. A capitalized identifier `Record` is a distinct name because Java is case-sensitive.

For `yield`, consider a switch expression example:

~~~java
int result = switch (status) {
    case 1 -> 10;
    case 2 -> {
        yield 20;
    }
    default -> 0;
};
~~~

Inside a switch expression block, `yield` terminates the branch and supplies the value for the entire switch expression. When an older codebase has a method or identifier named `yield`, the newer compiler may require clearer syntax in that context. You can use a more descriptive method name, or invoke the method via an explicit receiver where syntax permits.

### 2.3. Contextual Keywords

A contextual keyword is treated as a keyword only in a specific syntactic context. In ordinary contexts, the word can still serve as an identifier.

Notable groups:

| Contextual Keyword or Token | Usage Context |
|---|---|
| module, open, opens, requires, transitive, exports, to, uses, provides, with | Module declarations and module directives |
| var | Local variable declarations with type inference |
| yield | `yield` statement syntax inside switch expressions |
| record | Record declarations |
| sealed, permits, non-sealed | Sealed class/interface declarations and permitted subclass clauses |
| when | Guards in pattern matching for switch |

For example, `module` has special meaning in `module-info.java`:

~~~java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
}
~~~

Yet the word `module` does not automatically become a keyword in every Java file. In a normal class, an identifier with the same name can still be used outside the reserved syntactic context.

Since Java 21, `when` is used as a guard in pattern matching for switch:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> "text";
        case String text -> "empty";
        default -> "other";
    };
}
~~~

The word `when` in a case label serves a syntactic role. In an ordinary variable declaration position, it is not necessarily forbidden.

**Do not handle every contextual keyword by mass renaming.** Identify whether the compiler is interpreting the token as new syntax or as a normal identifier.

## 3. Java Changes That Can Create Name Collisions

When changing source levels, pay attention to when a feature was standardized and which source version the compiler applies. The table below summarizes common milestones during migration.

| Version | Name-Related Change | Possible Impact |
|---|---|---|
| Java 1.4 | `assert` becomes a keyword | Old identifiers named `assert` become invalid |
| Java 5 | `enum` becomes a keyword | Old identifiers named `enum` become invalid |
| Java 9 | `_` becomes a keyword; module system adds contextual keywords | Single `_` names and module syntax need auditing |
| Java 10 | `var` supports local variable type inference | `var` in type positions can conflict |
| Java 14 | `yield` used in switch expressions | `yield` in certain contexts can cause errors |
| Java 16 | `record` standardized; `java.lang.Record` introduced | Type names `record` and imports can conflict |
| Java 17 | `sealed`, `permits`, and `non-sealed` standardized | Subtype declaration syntax can cause identifiers to be parsed differently |
| Java 21 | `when` used as guard in switch patterns | `when` needs attention inside case labels |

This is not an exhaustive list of every Java source compatibility change. It focuses on names and syntax that can prevent an older codebase from compiling or require adjusting references.

## 4. Collisions with New Types in the JDK

Beyond keywords, the JDK also adds new classes and interfaces. New types can collide in name with types defined by applications or libraries.

### 4.1. Why Can New Types Make Simple Names Ambiguous?

Java automatically imports public types in the `java.lang` package. When a new JDK adds a type to `java.lang`, that type name enters the scope of source files without needing an explicit import.

For example, Java 16 added `java.lang.Record`. Suppose an application has a `Record` type in package `legacy.model` and a source file uses a wildcard import:

~~~java
import legacy.model.*;

public class ReportService {
    private Record current;
}
~~~

If `legacy.model` also contains a `Record` type, the reference `Record` can be ambiguous between the type in `legacy.model` and `java.lang.Record`, which is imported automatically on demand. The compiler may report an error demanding an explicit reference.

This can be fixed with a single-type import:

~~~java
import legacy.model.Record;

public class ReportService {
    private Record current;
}
~~~

Or by using the fully qualified name:

~~~java
private legacy.model.Record current;
~~~

If the code actually intends to use `java.lang.Record`, reference that type explicitly. Keep in mind that `java.lang.Record` is the base class for record classes, not a drop-in data type replacement for legacy `Record` classes.

### 4.2. Example: java.lang.Module

Java 9 added `java.lang.Module` to represent modules at runtime. An older library might already have a `Module` type in its own package.

~~~java
import legacy.runtime.*;

public class ModuleInspector {
    private Module currentModule;
}
~~~

If `legacy.runtime` contains a `Module` type, a simple reference can collide with `java.lang.Module`. Use an explicit import or a fully qualified name to specify the intended type.

~~~java
import legacy.runtime.Module;

public class ModuleInspector {
    private Module currentModule;
}
~~~

### 4.3. New Types in Wildcard-Imported Packages

The risk is not confined to `java.lang`. A new JDK can add types to packages that the application already wildcard-imports.

Java 21 added `SequencedCollection`, `SequencedSet`, and `SequencedMap` in `java.util`. Suppose a legacy library also defines a `SequencedCollection` type and a source file wildcard-imports both packages:

~~~java
import java.util.*;
import legacy.collections.*;

public class CollectionAdapter {
    private SequencedCollection<String> values;
}
~~~

If both packages provide a type with the same name, the simple reference can be ambiguous. The fix is to import the specific type or use its fully qualified name:

~~~java
private java.util.SequencedCollection<String> values;
~~~

This example illustrates the risk of wildcard imports. If the project explicitly imports only one type, or if a same-named type resides in the current package, name resolution rules may behave differently.

### 4.4. Same Name in Different Packages Does Not Always Cause Errors

Java follows precedence rules when resolving type names. Several cases:

- Types declared in the same compilation unit or same package follow distinct rules.
- Single-type imports have different precedence from wildcard imports.
- Two same-named types coming from two on-demand imports can cause ambiguity.
- Types in `java.lang` are imported automatically on demand.
- Fully qualified names always disambiguate package and type.

Therefore, you cannot conclude that merely having a new class with the same name will break the project. Inspect the actual imports and reference sites.

## 5. Name Collisions in Source, Packages, and Generated Code

### 5.1. Identifiers in Various Positions

Names can appear in many positions:

- Class, interface, enum, or record names.
- Field and local variable names.
- Method and constructor names.
- Parameter names.
- Generic type parameter names.
- Package names.
- Module names.
- Record component names.
- Pattern variable names.
- Lambda parameter names.
- Names generated by annotation processors or code generators.

A word may be valid in one position and invalid in another. Therefore, when the compiler reports an error, identify the exact identifier kind and context.

For instance, `var` can be a variable name:

~~~java
int var = 5;
~~~

Yet `var` cannot be used as the type of a field:

~~~java
class Config {
    var value = 5; // Invalid: var is not allowed for fields
}
~~~

Similarly, the name `record` can be used as a variable name in some contexts, yet cannot be used as a type name in restricted declaration syntax.

### 5.2. New Type Names and Wildcard Imports

Wildcard imports shorten code, but make name scope depend on all public types in the imported packages. When the JDK or a dependency adds new types, a previously unambiguous reference can become ambiguous.

Example:

~~~java
import java.util.*;
import legacy.types.*;

public class Converter {
    private Date value;
}
~~~

If both `java.util` and `legacy.types` contain a `Date` type, the compiler cannot automatically pick which one the source file intends. This collision could already happen prior to migration, yet adding packages or new types to one of the imported sources can surface the error after upgrading a JDK or dependency.

A safer approach is explicit imports:

~~~java
import java.util.Date;
~~~

If both types are needed, use an explicit import for one and a fully qualified name at the other reference sites.

### 5.3. Generated Source and Annotation Processors

A project may not contain conflicting identifiers directly in handwritten source, while generated code introduces those names.

Common generated code sources include:

- Annotation processors.
- OpenAPI or Swagger generators.
- JAXB or XML schema generators.
- Query/metamodel generators.
- ORM static metamodels.
- Protobuf or gRPC generators.
- Client SDK generators.
- Tools generating sources from database schemas.

For example, a schema has a property named `record`. An older generator might emit fields or methods unsuitable for the new source level. Another generator might emit types named `Module`, `Record`, or a name colliding with a newly added JDK type.

During migration, inspect:

- Handwritten source code.
- Sources generated in the build directory.
- Generator configuration and plugin versions.
- Templates or renaming rules.
- Annotation processors running under the target JDK compiler.

Do not edit generated files directly if the next build overwrites them. Fix the schema, template, mapping, or upgrade the generator so output is produced cleanly.

## 6. Recognizing Errors from Keywords and Type-Name Collisions

Compiler diagnostics usually pinpoint the location and error shape. Common error patterns include:

| Message Pattern | Possible Cause |
|---|---|
| identifier expected | Token in identifier position is invalid |
| not a statement | Parser interpreted token under different syntax or invalid expression |
| class, interface, enum, or record expected | Declaration structure or token placement is invalid |
| reference to X is ambiguous | Multiple types with the same name are in import scope |
| cannot find symbol | Type or member cannot be resolved |
| package X does not exist | Dependency/import is missing from classpath |
| incompatible types | Resolved type differs from expected type |
| invalid method declaration | Invalid method/constructor name or declaration syntax |

A `cannot find symbol` error does not automatically mean an identifier became a keyword. It can also stem from a missing dependency, changed imports, ungenerated sources, or an incorrect profile/configuration.

During migration, classify errors in order:

1. Parser/syntax error.
2. Invalid identifier or restricted identifier.
3. Ambiguous type reference.
4. Missing import or missing dependency.
5. Type incompatibility.
6. Changed API/member resolution.

This classification prevents renaming a class when the actual root cause is classpath or imports.

## 7. Investigation Process for Name Collisions When Upgrading Java

### Step 1 — Identify the Actual Source Level

Do not look only at the JDK installed on the machine. Check:

- The JDK running Maven or Gradle.
- Compiler toolchain.
- Source/release target.
- IDE compiler settings.
- CI build parameters.
- Annotation processors and generated source tasks.

A project may use a new JDK while still compiling at an older source release. If the compiler runs with release 8, certain identifiers remain accepted under that source level's rules. Raising the release to 17 or 21 can trigger new errors.

### Step 2 — Read the First Error in Compiler Output

The initial parser error is often the root cause. Subsequent errors may be cascading consequences after the parser misread the rest of the file.

Record:

- File and line number of the error.
- Token the compiler points to.
- Active source release.
- Actual JDK compiler.
- Whether the file is handwritten or generated source.

### Step 3 — Find All Usages of the Identifier

Search for the reported name in:

- `src/main/java`.
- `src/test/java`.
- Other source sets.
- Generated source directories.
- Code generator templates.
- Schemas and code-generation configs.
- Module descriptors and package declarations.

You can use ripgrep:

~~~bash
rg -n -w "record|yield|var|sealed|permits|when" src
~~~

This command is only a word-based text search. It may return comments, string literals, and valid usages. Interpret matches in Java context; do not apply a global find-and-replace across all matches.

For new type names, search by simple name and inspect imports as well:

~~~bash
rg -n "import .*Record|\\bRecord\\b|import .*Module|\\bModule\\b" src
~~~

If the name comes from generated sources, search inside the build tool's generated output directory.

### Step 4 — Inspect Imports and Type Resolution Rules

When the error is an ambiguous reference:

- List all relevant imports.
- Check the current package.
- Determine whether the type is auto-imported from `java.lang`.
- Determine which wildcard imports provide the colliding name.
- Check single-type imports.
- Use a fully qualified name to confirm the intended type.

Example:

~~~java
import legacy.model.*;
import java.util.*;

class Report {
    Record record;
}
~~~

If `legacy.model` defines a `Record` type, `Record` can collide with `java.lang.Record` on the applicable source level. Change it to:

~~~java
import legacy.model.Record;

class Report {
    Record record;
}
~~~

or:

~~~java
class Report {
    legacy.model.Record record;
}
~~~

### Step 5 — Verify with the Target Compiler

After fixing a small site, rebuild with the exact target compiler and release used for migration. Do not rely solely on the IDE, as the IDE may use a different JDK or source level from CI.

### Step 6 — Check Generated Code

If the error occurs in generated source, identify the generator and version. Update the template/schema/configuration or upgrade the generator. Then clean and regenerate the output via the project's official task; do not manually edit generated output as a permanent fix.

### Step 7 — Run Tests and Check APIs

Renaming identifiers can affect:

- Reflection by field/method name.
- JSON property or XML element names.
- Serialization.
- ORM mapping.
- Spring bean names or property bindings.
- Expression languages.
- Public APIs and consumers.
- Native image reflection configuration.
- Code generators and client SDKs.

A rename may compile cleanly yet break an external contract. Verify places referencing names as strings or by convention.

## 8. Fixes by Collision Type

### 8.1. Identifier Became a Keyword

If the old name genuinely became a keyword, rename the identifier to a meaningful name.

Example:

~~~java
// Previously: valid on source levels prior to Java 9
String _ = readValue();

// After upgrading source level
String ignoredValue = readValue();
~~~

Avoid generic names like `value` when clearer semantics exist. If the identifier is part of a public API, evaluate consumer source and binary compatibility.

### 8.2. Restricted Identifier Conflicts Only in One Position

If the identifier remains valid at its current site, renaming may not be required. However, if new syntax harms readability or confuses parsing, renaming often clarifies the code.

Example:

~~~java
int yield = 5;
int result = yield + 10;
~~~

This can remain intact if the source context is valid. Yet if the code has methods or expressions easily mistaken for a `yield` statement, rename it to `resultValue` or `computedValue`, or qualify the receiver/invocation explicitly.

### 8.3. Two Types Share the Same Simple Name

Use a single-type import or a fully qualified name:

~~~java
import legacy.model.Record;

class Exporter {
    private Record model;
    private java.lang.Record baseRecord;
}
~~~

Note that `java.lang.Record` is the abstract base class for record classes. It does not represent the `legacy.model.Record` type.

### 8.4. Wildcard Imports Cause Ambiguity

Replace wildcard imports with explicit imports for the types used:

~~~java
import java.util.List;
import java.util.Map;
import legacy.collections.CustomSequence;
~~~

You do not necessarily need to remove every wildcard import across the entire project. Address files with ambiguous type names or collision risks when upgrading JDKs/dependencies.

### 8.5. Generated Code Contains Conflicting Names

Prioritize fixing at the generation source:

- Update the generator to a version supporting the target source level.
- Configure reserved words or name mappings if supported by the generator.
- Rename schema properties according to compatibility rules.
- Update code-generation templates.
- Ensure generated sources regenerate deterministically.

If a schema name is part of a public contract, renaming it directly can alter JSON fields, endpoints, database columns, or consumer-facing method names. Use mappings to preserve the contract when needed.

## 9. Preserving Contracts When Renaming

Renaming an identifier in source code is not always purely an internal refactoring.

### 9.1. Public Java API

If a class or method is `public`/`protected` in a library compiled separately by consumers, renaming can break source or binary compatibility.

For example, a library has:

~~~java
public class LegacyOptions {
    public String record;
}
~~~

Renaming the field to `recordName` causes consumers accessing `options.record` to fail compilation or linkage depending on the API change.

You can preserve the old API using compatibility methods or adapters over a transition period if API policy permits. Clearly define the deprecation period and removal version.

### 9.2. JSON and Serialization

Field names can become JSON property names by convention:

~~~java
public class Event {
    private String record;
}
~~~

Renaming to `recordName` can change JSON output from:

~~~json
{"record":"created"}
~~~

to:

~~~json
{"recordName":"created"}
~~~

If older clients must continue working, use annotation mapping to preserve the old property name while renaming the Java field, depending on the serialization library.

Example with Jackson:

~~~java
public class Event {
    @JsonProperty("record")
    private String recordName;
}
~~~

Test both serialization and deserialization, getters/setters, constructor bindings, and published schemas.

### 9.3. ORM and Database Mapping

Field names can affect naming strategies or default mappings. If renaming a field, verify:

- Whether mapped column names change.
- Whether JPQL/HQL queries reference the old property name.
- Whether Criteria API or generated metamodels are affected.
- Whether a database migration is required.

Use explicit mapping annotations if you want the Java name to change while keeping the database name unchanged.

### 9.4. Reflection, Framework Scanning, and Name-Based Configuration

Some frameworks or plugin systems look up classes/methods/fields by string name. Static search can miss names constructed from properties or runtime configs. Check:

- Annotations.
- XML configurations.
- Application properties/YAML.
- Expression languages.
- `ServiceLoader`.
- Reflection utilities.
- Native image reflection metadata.
- External integration contracts.

Safe renaming must account for name-based lookup paths, not just compiler-checked references.

## 10. Testing Source Compatibility Across Multiple Java Releases

A library project may need to support multiple releases. In that case, compile and test across every committed release.

For example, build with JDK 21 while keeping release 17:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

In Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

In Gradle:

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

Configuring release restricts syntax and platform APIs accordingly, yet does not automatically ensure third-party dependencies share the same baseline. Verify the dependency graph and real runtime.

If the application supports Java 17 and Java 21, run a test matrix across both runtimes when feasible. Some bugs appear only on the newer runtime due to behavioral or API changes; others appear on the older runtime because a dependency was compiled for too new a release.

## 11. End-to-End Example: Upgrading Source Level from Java 8 to Java 21

Suppose an older codebase contains the following cases in two separate source files:

~~~java
// Record.java
public class Record {
    private String value;
}
~~~

~~~java
// LegacyParser.java
public class LegacyParser {
    public String parse(String _) {
        return _;
    }
}
~~~

When upgrading the source level, the following categories of issues can arise:

- A single underscore is no longer allowed as an identifier since Java 9. This is a concrete example of an identifier valid in an older source level that became a keyword.
- The capitalized type `Record` remains a valid identifier, yet can collide with `java.lang.Record` when imported via wildcard.
- Generated code or annotation processors may emit identifiers colliding with newly restricted identifiers.

A clearer revised version:

~~~java
// LegacyRecord.java
package com.example.legacy;

public class LegacyRecord {
    private String value;
}
~~~

~~~java
// LegacyParser.java
package com.example.legacy;

public class LegacyParser {
    public String parse(String input) {
        return input;
    }
}
~~~

If the public class `Record` must remain unchanged due to an existing contract, you do not necessarily have to rename that class immediately. You can use explicit imports or fully qualified names at ambiguous sites, then plan a separate API change if genuinely needed.

The example above illustrates the error classes; when working on a real codebase, rely on actual compiler output and specific source locations.

## 12. Migration Workflow for Identifier and Type-Name Collisions

A workflow applicable per module:

1. Record the compiler JDK, source/release target, and module being built.
2. Compile at the target source level to collect actual errors.
3. Classify errors: keyword, restricted identifier, contextual keyword, ambiguous type, missing import, or generated code.
4. Locate declaration and reference sites of affected identifiers.
5. Check imports, packages, and new JDK types.
6. Check source generators and annotation processors.
7. Choose the minimal fix: rename, explicit import, qualified name, or generator update.
8. Evaluate public API, JSON/XML, database mapping, and reflection impacts.
9. Recompile with the target compiler.
10. Run unit, integration, and contract tests.
11. Record source compatibility changes and rationales in the migration record.

Do not perform bulk renaming via search-and-replace without distinguishing identifiers, string literals, comments, JSON properties, SQL columns, and reflection-invoked method names.

## 13. Tools for Search and Verification

### 13.1. Ripgrep

Quickly search for words often tied to new syntax:

~~~bash
rg -n -w "assert|enum|var|yield|record|sealed|permits|when" src
~~~

Search for potentially colliding type names:

~~~bash
rg -n "Record|Module|SequencedCollection|SequencedMap|SequencedSet" src
~~~

Matches must be triaged manually. Ripgrep searches text without fully understanding Java semantics.

### 13.2. Target JDK Compiler

The compiler is the strongest evidence of whether source compiles under the chosen release.

~~~bash
javac --release 21 -d out src/com/example/Main.java
~~~

In Maven or Gradle projects, run the actual compile task so plugins, annotation processors, and source sets are all exercised.

### 13.3. IDE Inspections and Static Analysis

IDEs can warn about:

- Restricted identifiers under the new source level.
- Unclear imports.
- Ambiguous type references.
- Deprecated or unavailable APIs.
- Compiler configuration differing from the intended JDK.

Static analysis can uncover additional patterns, provided it runs with the exact target source level and JDK. The IDE does not replace the CI build.

### 13.4. Generated Source Inspection

If the build generates source code, check output directories such as:

~~~text
target/generated-sources/
target/generated-test-sources/
build/generated/
build/generated/sources/
~~~

Exact directory names depend on plugins. Inspect the generating task or plugin to map outputs to generators.

Never treat manual edits to generated files as a lasting fix. Update the generation source and re-run the generator.

## 14. Recording Collision Resolution Results

A migration record should capture:

~~~text
MODULE
  Module:
  Source release before:
  Source release target:
  Compiler JDK:
  Build tool:

COLLISION
  Identifier/type:
  Source location:
  Collision category:
  New Java feature or JDK type:
  Compiler diagnostic:

RESOLUTION
  Rename / explicit import / qualified name / generator update:
  Files changed:
  Public API impact:
  Serialization/database/reflection impact:

VALIDATION
  Compile command:
  Compile result:
  Unit test result:
  Integration/contract test result:
  Generated source check:

FOLLOW-UP
  Consumer compatibility:
  Deprecation or migration note:
  Remaining risk:
~~~

Also record sites that required no changes yet were verified. This helps reviewers see the inspection scope and avoids repeating investigations in later migrations.

## 15. Summary Notes

When upgrading the Java source level, evaluate identifiers in context:

- **Keywords:** cannot be used as identifiers.
- **Restricted identifiers:** restricted only in specific syntactic positions.
- **Contextual keywords:** carry special meaning within a specific context.
- **New type names:** can collide with existing types via imports, especially wildcard imports and automatically imported `java.lang` types.
- **Generated identifiers:** should be addressed at the schema, template, or generator rather than manually editing generated output.

When the compiler reports an error, identify the source level, read the first error, check imports and packages, search both handwritten and generated sources, and select a fix that preserves application contracts.

Migration is complete when code compiles under the target compiler and release, types resolve unambiguously, generated code regenerates deterministically, and external contracts remain verified.
