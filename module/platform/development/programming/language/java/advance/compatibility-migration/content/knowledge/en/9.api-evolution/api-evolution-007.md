
# Changing enums, annotations, and metadata read by external tools

In a Java system, an API is not just classes and methods called directly from source code. Many elements are also **read as data**: enum constant names sent over JSON, annotations scanned by frameworks via reflection, generic information analyzed by code-generation tools, or class-file attributes used by plugins, serializers, and schema generators.

Therefore, a seemingly small change—renaming an enum constant, adding an annotation element, switching a retention policy, stripping metadata during JAR packaging—can cause consumers to fail even when the main project still compiles and passes ordinary unit tests. In the context of **Java Advance Compatibility Migration**, it is necessary to evaluate not only source and binary compatibility, but also **data, reflection, schema, and external tool compatibility**.

This lesson provides a classification of changes, concrete Java examples, and a verification process when evolving APIs containing enums, annotations, and metadata.

## 1. APIs used by invocation and APIs read as data

Consider four types of consumers:

1. **Source consumers**: a module imports classes, invokes methods, compares enum constants, and is recompiled when upgrading dependencies.
2. **Binary consumers**: a JAR compiled against an old version, running against the new library version without recompiling.
3. **Dynamic runtime consumers**: frameworks using reflection, classpath scanning, annotation processing, service loading, or class loaders to discover types and metadata.
4. **Consumers outside the JVM**: other systems receiving JSON, databases storing enum values, OpenAPI/JSON Schema generators, or a program reading class files.

These consumers do not share the same compatibility criteria.

| Contract type | Data the consumer depends on | Changes that can cause failures |
|---|---|---|
| Source API | Class names, enum constants, methods, and annotation elements | Renaming constants or changing signatures |
| Binary API | Symbolic references, descriptors, and fields in class files | Removing an enum constant still referenced by old bytecode |
| Runtime reflection | Annotations, retention, target, element names and values | Switching RUNTIME to CLASS or changing annotation elements |
| Stored data | Enum names, ordinals, or representative codes | Reordering enums when the database stores ordinals |
| Communication contract | JSON values, enum schemas, message payloads | Changing JSON values or adding enum values not yet supported by consumers |
| Tool metadata | Signature, MethodParameters, annotation attributes, service files | Shading/minification stripping required metadata |

**Key takeaway:** “A successful build” only proves a set of build-time constraints. It does not verify every runtime consumer, database, or integrated service.

~~~mermaid
flowchart TD
    A["Java API changes"] --> B["Source and binary consumers"]
    A --> C["Reflection / frameworks"]
    A --> D["Data and protocols"]
    A --> E["Class file / JAR metadata"]
    B --> F["Multi-layer compatibility evaluation"]
    C --> F
    D --> F
    E --> F
    F --> G["Appropriate migration and testing"]
~~~

## 2. Enums carry more contracts than a list of constants

A Java enum is a reference type with a predefined set of declared instances, and can have fields, constructors, methods, interfaces, and per-constant logic.

Example:

~~~java
public enum PaymentStatus {
    CREATED,
    AUTHORIZED,
    SETTLED,
    FAILED
}
~~~

Consumers can use enums in multiple ways:

~~~java
PaymentStatus status = PaymentStatus.AUTHORIZED;

String name = status.name();
int position = status.ordinal();

PaymentStatus parsed = PaymentStatus.valueOf("AUTHORIZED");

for (PaymentStatus candidate : PaymentStatus.values()) {
    System.out.println(candidate);
}
~~~

Each usage creates a different dependency point:

- **Direct access** `PaymentStatus.AUTHORIZED` depends on the enum constant field of the corresponding name.
- **`name()` and `valueOf()`** depend on the declared name, case-sensitively.
- **`ordinal()`** depends on the declaration position, starting from 0.
- **`values()`** returns constants in declaration order.
- **`toString()`** may be overridden and is therefore not necessarily equal to `name()`.
- **`switch`** depends on the set of cases and the strategy for handling unknown values.
- **Serializers, ORMs, code generators** may choose the name, position, or other metadata as the representation.

Therefore, when modifying an enum, you must ask: **who is reading this enum and which property are they reading?**

### 2.1. Constant names are a contract

For example, changing:

~~~java
enum PaymentStatus {
    CREATED, AUTHORIZED, SETTLED
}
~~~

to:

~~~java
enum PaymentStatus {
    CREATED, APPROVED, SETTLED
}
~~~

If an old consumer calls `PaymentStatus.AUTHORIZED`, it may fail to compile when rebuilt. If old bytecode still references the removed field, the JVM may throw `NoSuchFieldError`.

A system receiving the string `"AUTHORIZED"` and calling `PaymentStatus.valueOf(...)` will receive `IllegalArgumentException` once that constant no longer exists.

Renaming an enum constant is not a simple “label edit”; it can break both the **binary API** and the **wire/data contract**.

### 2.2. `ordinal()` is not a durable ID

With the enum:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}
~~~

the ordinals are 0, 1, and 2 respectively. If `URGENT` is added at the beginning:

~~~java
enum Priority {
    URGENT, LOW, MEDIUM, HIGH
}
~~~

all previous ordinals are shifted. A database storing `0` meaning LOW may be interpreted as URGENT when running the new version.

This is dangerous for:

- ORMs storing enums by ordinal.
- Caches or message payloads storing the numeric value of `ordinal()`.
- Arrays, bitmasks, mappings, or configuration files using indexes as business meaning.
- Schema generators treating declaration position as an identifier number.

**Do not use ordinal as a durable storage or communication code.** Ordinal is primarily for internal structures ordered by declaration.

### 2.3. `name()` is more stable than ordinal but is still a rename contract

When a serializer stores the constant name, adding or reordering constants does not change existing names. However, renaming still breaks previously stored data.

For example, a table contains `"AUTHORIZED"`. If the Java enum is renamed to `APPROVED`, a mapper knowing only the new name may fail to read old records.

Hence, using `EnumType.STRING` in an ORM is usually safer than storing ordinals when needing to insert or reorder enums, but still requires migration when **renaming** constants. “Using STRING” does not replace a data compatibility plan.

### 2.4. `toString()` can serve display purposes, not necessarily as a key

~~~java
enum PaymentStatus {
    CREATED, AUTHORIZED;

    @Override
    public String toString() {
        return this == CREATED ? "Chờ xử lý" : "Đã xác thực";
    }
}
~~~

`name()` always reflects the declared name; `toString()` here returns a display string that can change with language or UX requirements. If a system uses `toString()` to write durable data, changing display text becomes a breaking change.

Separate **machine-readable codes** from **user labels**.

## 3. Enum change and risk matrix

| Change | Source/binary consumers | External data or tools |
|---|---|---|
| Add new constant | Usually keeps old references; may break logic assuming a fixed enum set | Old consumers may not read the new value; schema needs updating |
| Remove constant | Old source fails; old bytecode may hit `NoSuchFieldError` | Old names in DB/JSON can no longer be parsed |
| Rename constant | Roughly equivalent to removing old name and adding new name | Requires aliases or data migration |
| Reorder constants | Name-based references usually remain intact | `ordinal()`, UI order, and index-based mappings change |
| Add field/method to enum | Usually does not remove old members | Reflection/scanners may observe new metadata |
| Change constant's custom wire code | Does not necessarily change binary API | Breaking change for consumers using that code |
| Change annotation on constant | Does not necessarily change enum descriptor | Serializers, ORMs, or schema generators may change output |
| Change `toString()` logic | Bytecode can still call the method | Logs, custom serialization, or UI may change |
| Change enum's internal constructor | External consumers usually do not call constructor directly | Bytecode/reflection tools may depend on implementation structure |

Assessment must be based on **usage paths** rather than only the type of change.

### 3.1. Adding an enum constant is not always a harmless change

Suppose the old version:

~~~java
enum JobState {
    NEW, RUNNING, DONE
}
~~~

A consumer has a `switch` covering all three constants. The new version adds `CANCELLED`.

A consumer using a `switch statement` with a `default` branch may handle the new value via the default branch. However, source code using a **switch expression** without `default` typically relies on exhaustiveness of the enum set at compile time; running old bytecode with a new constant can encounter a runtime error when no branch matches. The specific exception type may depend on the Java version and how the compiler generates bytecode (for example `IncompatibleClassChangeError` or `MatchException`).

Even without a technical error, logic can still be wrong:

~~~java
switch (state) {
    case NEW:
        enqueue();
        break;
    case RUNNING:
        monitor();
        break;
    case DONE:
        archive();
        break;
    default:
        archive(); // Should CANCELLED really be archived?
}
~~~

A `default` branch prevents certain errors but does not guarantee correct semantics. When expanding an enum that is a public API, check all consumers using `switch`, mappings, whitelists, and validation.

### 3.2. Changing enum constants that have their own class bodies

Enum constants can override methods:

~~~java
enum Transport {
    ROAD {
        @Override
        int capacity() { return 100; }
    },
    AIR {
        @Override
        int capacity() { return 1000; }
    };

    abstract int capacity();
}
~~~

The compiler may generate auxiliary classes for constants with their own bodies. Tools scanning class files can see these classes, but the names and structure of generated classes are implementation details. Consumers must not depend on synthetic subclass names or class ordering inside the JAR.

## 4. Designing stable enum codes for data and protocols

When an enum is stored in a DB, cache, event, or API response, declare a stable code controlled by the application.

~~~java
import java.util.Arrays;
import java.util.Optional;

public enum OrderState {
    CREATED("created"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderState(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static Optional<OrderState> fromCode(String input) {
        if (input == null) {
            return Optional.empty();
        }
        return Arrays.stream(values())
                .filter(value -> value.code.equals(input))
                .findFirst();
    }
}
~~~

Design points:

- `code` does not depend on declaration order.
- The code is guaranteed to remain preserved when the constant name changes for internal reasons.
- `fromCode` enables handling unrecognized values instead of throwing blindly.
- Aliases can be added during a migration period, provided there are clear rules on writing the new code and reading the old code.
- Codes must follow uniqueness rules and be documented in the schema/API documentation.

Do not automatically map every unfamiliar value to `UNKNOWN` if business logic needs to distinguish data corruption from a valid new case. You can use `Optional.empty()`, a result type distinguishing known/unknown, or a separate handling flow.

### 4.1. Read-old, write-new strategy

Suppose old data stores `"authorized"` while the new code wants to use `"approved"`. A transition strategy is:

1. In the transition version, **read both codes**.
2. When writing new records, always write `"approved"`.
3. Track statistics of data and requests still using the old code.
4. Migrate data in the DB and backlog messages if needed.
5. Remove the alias only after verifying all consumers and legacy data have been converted.

Example:

~~~java
public static Optional<OrderState> fromCode(String input) {
    if ("authorized".equals(input) || "approved".equals(input)) {
        return Optional.of(PAID);
    }
    return Arrays.stream(values())
            .filter(value -> value.code.equals(input))
            .findFirst();
}
~~~

This is an illustrative example; state names must accurately reflect real business semantics. Do not merge two states with different meanings just to avoid parse errors.

### 4.2. JSON, ORM, and schemas

For JSON, serializers may output enum names by default, but different libraries and configurations can use `toString()`, annotations, custom serializers, or numeric codes. Identify the exact **representation being published**.

For JPA/Hibernate, inspect how the enum is mapped:

- `EnumType.STRING`: usually stores the enum name.
- `EnumType.ORDINAL`: stores the numeric position.
- `AttributeConverter` or custom mapping: can store a stable code.

For OpenAPI/JSON Schema, adding an enum value may make the new schema valid while clients generated from the old schema fail to recognize it. Check each client's unknown-enum handling strategy. For protocols using numeric codes (such as protobuf), the numeric code is a separate contract, not the Java ordinal.

### 4.3. Java serialization

Java's standard serialization mechanism processes enums by constant name and does not treat ordinal order as the stored identifier. Therefore, adding or reordering constants differs from removing/renaming constants in the context of standard serialization.

However, many applications do not use Java Object Serialization and instead use JSON, databases, or custom binary protocols. Do not mechanically apply Java Serialization rules to those other formats.

## 5. Annotations are also APIs with their own consumers

Java annotations can provide metadata to frameworks, compilers, and external tools.

Example of a public annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface EndpointRole {
    String value();
    boolean audited() default true;
}
~~~

Consumers may:

- Read `EndpointRole` via reflection.
- Scan class files with ASM without loading the class.
- Use an annotation processor to generate source.
- Use a build plugin to generate documentation or code.
- Use a runtime framework to register routes, permissions, or dependencies.
- Use a schema generator to export an API contract.

If you change an annotation and only run business-logic unit tests, it is very easy to miss impacts on the consumers above.

### 5.1. Annotation elements are special methods

The declaration:

~~~java
public @interface EndpointRole {
    String value();
    boolean audited() default true;
}
~~~

defines elements `value` and `audited`. At the class-file level, they correspond to methods of the annotation interface.

Default values are stored as metadata on the annotation declaration, not necessarily written at each usage site.

Example:

~~~java
@EndpointRole("admin")
public class AdminEndpoint {
}
~~~

This annotation does not explicitly specify `audited`. When reading metadata, consumers typically receive the default value `true` from the annotation definition.

If the library changes the default to `false`, source code using the annotation does not change, but runtime behavior or tool output may change. That is a **behavioral change** even though no annotation usage site needs editing.

### 5.2. Annotations on enum constants reside on the corresponding fields

Example:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface ExternalCode {
    String value();
}

enum DeliveryState {
    @ExternalCode("queued")
    QUEUED,

    @ExternalCode("dispatched")
    DISPATCHED
}
~~~

A Java Reflection tool reads the constant's annotation via its field:

~~~java
import java.lang.reflect.Field;

public class DeliveryMetadata {
    public static String externalCode(DeliveryState state)
            throws NoSuchFieldException {
        Field field = DeliveryState.class.getField(state.name());
        ExternalCode annotation = field.getAnnotation(ExternalCode.class);
        return annotation != null ? annotation.value() : state.name();
    }
}
~~~

Do not confuse metadata on the **enum constant field** with annotations at the **enum class** level. Changing `@Target` or removing `@ExternalCode` from a constant can cause serializers/schema generators to change output even though the enum constant still exists and code referencing the constant name still runs.

## 6. Retention, target, and important meta-annotations

### 6.1. Retention determines who can read the annotation

The three values of `RetentionPolicy`:

| Retention | Where does metadata exist? | Typical consumers |
|---|---|---|
| SOURCE | Source; not retained in the class file | Compiler plugins, annotation processors reading source |
| CLASS | Stored in the class file but not exposed by Java Reflection as a runtime annotation | ASM, class-file scanners, build tools |
| RUNTIME | Stored in the class file and readable via reflection at runtime | DI frameworks, ORMs, web/security frameworks |

If `@Retention` is omitted, an annotation defaults to `RetentionPolicy.CLASS`.

Example:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Audit {
    String action();
}
~~~

If retention is changed from RUNTIME to CLASS:

- The class file may still contain the annotation as runtime-invisible.
- `Method.getAnnotation(Audit.class)` will no longer see that annotation.
- Frameworks relying on reflection may stop registering or applying audit logic.
- A tool scanning class files directly may still see the annotation, depending on how it reads metadata.

If changed from CLASS to SOURCE, the annotation is no longer in the class file; class-file scanners cannot find it in the compiled artifact either.

**Do not judge retention merely by whether the build succeeds.** Verify the exact reading mechanism that consumers use.

### 6.2. Target changes valid usage locations

`@Target` specifies where an annotation may be applied:

~~~java
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface ExportedApi {
}
~~~

For example, changing TARGET from `TYPE` to `METHOD` can cause old source attaching the annotation to a class to fail compilation. Consumer source has not changed, but the annotation definition has changed its contract.

Notable targets include `TYPE`, `FIELD`, `METHOD`, `PARAMETER`, `CONSTRUCTOR`, `TYPE_USE`, `TYPE_PARAMETER`, `RECORD_COMPONENT`, and `ANNOTATION_TYPE`, depending on the Java version.

For annotations on type uses, metadata may reside in `RuntimeVisibleTypeAnnotations` or `RuntimeInvisibleTypeAnnotations`. Tools that only read standard annotations may miss type-use annotations.

### 6.3. Inherited does not mean inherited everywhere

`@Inherited` primarily affects annotation lookup on **classes** via `Class.getAnnotation` when the annotation type carries this meta-annotation. It does not automatically cause annotations on methods, fields, or interfaces to be inherited in the same way.

Example:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Tracked {
}
~~~

Frameworks that traverse hierarchies or interfaces themselves may scan differently from default reflection. When changing `@Inherited`, inspect the framework's actual lookup mechanism.

### 6.4. Repeatable annotations and containers

With `@Repeatable`, an annotation can appear multiple times:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
~~~

Consumers using `getAnnotationsByType(Role.class)` can receive repeated annotations, whereas code calling only `getAnnotation(Role.class)` behaves differently when annotations are wrapped in a container. When converting an annotation from non-repeatable to repeatable, check:

- The container annotation type and the `value` element name.
- Retention and target of both the annotation and the container.
- How the framework reads directly, reads the container, or calls `getAnnotationsByType`.
- Data already compiled from the old version.
- Whether class-file scanning tools properly recognize the container.

### 6.5. Documented and documentation metadata

`@Documented` affects how an annotation is included in Javadoc documentation, rather than directly providing runtime functionality. Even so, documentation/API catalog generators may rely on that output, so changes still need review when documentation is an externally integrated output.

## 7. Evolving annotation elements and compatibility

Annotation elements have permitted value types such as primitives, String, Class, enums, other annotations, or one-dimensional arrays of those types. They can have default values.

### 7.1. Adding an element with a default is usually smoother

Version 1:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Route {
    String path();
}
~~~

Version 2 adds an element:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Route {
    String path();
    boolean secure() default true;
}
~~~

Old usages lacking `secure` can continue to be read thanks to the default. However, the new default also affects runtime behavior—for example, all existing routes become secure—so business review is still necessary.

### 7.2. Adding an element without a default can leave old annotations missing a value

Version 2:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Route {
    String path();
    String owner(); // No default
}
~~~

Source consumers using `@Route(path = "/users")` must provide `owner` when recompiling. Class files compiled with the old annotation version may still contain annotation instances missing this element; when a framework reads `owner()`, `IncompleteAnnotationException` may be thrown.

A usually safer transition approach:

1. Add the element with an appropriate default.
2. Update annotation usages to explicit values.
3. Check old artifacts and annotation-reading tools.
4. Only consider removing the default or making it newly required in an announced breaking release.

### 7.3. Renaming or removing an element

For example, changing `path()` to `value()`:

~~~java
// Old
String path();

// New
String value();
~~~

Old source annotation usages need updating. Compiled consumer bytecode calling the `path()` accessor may hit linkage errors if that method no longer exists. Previously compiled annotation metadata may also contain an element named `path` that the new annotation type no longer defines.

If you want a transition, keep the old element (possibly deprecated), add the new element, and clearly define which field takes precedence. Do not remove it in a minor release if binary compatibility has been promised.

### 7.4. Changing an element's type

Example:

~~~java
// Old
String timeout();

// New
long timeout();
~~~

This is not just changing how metadata is written. The annotation's method descriptor changes, old usages have a different value form, and old reader code may fail to link or interpret it.

When the value type stored in the annotation differs from the type expected by the new definition, `AnnotationTypeMismatchException` may occur when reading the element. Other errors depend precisely on the change and the reading mechanism.

For an enum-valued annotation:

~~~java
public @interface Retry {
    RetryMode mode() default RetryMode.NORMAL;
}
~~~

if a constant `RetryMode.NORMAL` is removed while old metadata still refers to it, reading the element may encounter `EnumConstantNotPresentException`. If a class referenced in metadata no longer exists, `TypeNotPresentException` may occur.

**Do not predict only a single exception for every annotation change.** Inspect the actual bytecode and the exact points where readers access metadata.

### 7.5. Changing a default is a behavioral change

Example:

~~~java
public @interface Retry {
    int attempts() default 3;
}
~~~

changed to:

~~~java
public @interface Retry {
    int attempts() default 5;
}
~~~

Usages explicitly specifying `attempts = 3` do not change value, but usages omitting the element may receive the new value when the reader uses the new annotation definition. There is no forced compilation error, yet the system may execute more retries, altering latency or load.

For annotation APIs used in production, the default value is also a **public contract**.

## 8. Class-file metadata read by external tools

Some tools do not run the application, but instead read `.class` files, `.jar` files, or bytecode. Therefore, metadata can be affected right at the compilation, shading, obfuscation, or packaging steps.

| Metadata/attribute | Information | Typical consumers |
|---|---|---|
| `RuntimeVisibleAnnotations` | Runtime annotations on class/member | Reflection, runtime frameworks |
| `RuntimeInvisibleAnnotations` | Annotations present in the class file but not visible via core reflection | ASM scanners, plugins |
| `RuntimeVisibleTypeAnnotations` | Annotations on type-use positions | Nullability analysis, static/runtime tooling |
| `Signature` | Generic type information | Java Reflection generic API, IDEs, serializers |
| `MethodParameters` | Parameter names and flags | DI, binding, reflection |
| `AnnotationDefault` | Default value of annotation element | Annotation readers |
| `Record` | Record components | Reflection, serializers, schema generators |
| `PermittedSubclasses` | Permitted subclasses of a sealed class | Compiler, runtime/tooling |
| `InnerClasses` and `EnclosingMethod` | Nested class relationships | Reflection/tooling |
| `NestHost` and `NestMembers` | Nest membership | JVM and bytecode tools |
| `Module` in `module-info.class` | JPMS module information | Module resolvers and analyzers |

This list does not cover every attribute. Meaning and presence depend on JDK version, class kind, and compiler flags.

### 8.1. Generic Signature differs from method descriptor

Example:

~~~java
public List<String> names() {
    return List.of();
}
~~~

The JVM method descriptor may be:

~~~text
()Ljava/util/List;
~~~

The generic argument `String` is not in the descriptor, but can be stored in the `Signature` attribute. If a packaging tool strips `Signature`, the JVM can still invoke the method, but frameworks using `getGenericReturnType()` or schema generators may lose the `List<String>` information.

Thus, “the bytecode still runs” is not enough to prove that metadata consumers are unaffected.

### 8.2. Parameter names can be input data for frameworks

Example:

~~~java
public User findUser(long userId) {
    return repository.find(userId);
}
~~~

A web framework may use the parameter name `userId` during request binding, yet the class file is not guaranteed to always contain that name. When parameter names need to be reflected via `java.lang.reflect.Parameter`, the Java compiler typically needs `-parameters` enabled to emit the appropriate metadata.

Example:

~~~bash
javac -parameters -d out src/com/example/UserController.java
~~~

If a build refactor removes the `-parameters` flag, the method descriptor still remains `(J)Lcom/example/User;`, but frameworks relying on parameter names may no longer bind properly.

Note: some frameworks have alternative mechanisms such as explicit annotations, Kotlin metadata, or debug information; do not assume all frameworks require the exact same flag.

### 8.3. Record, sealed, and class-file versions

Records and sealed classes have appropriate metadata/attributes so the JVM, reflection, and compiler understand the type structure. Old bytecode-reading tools may not understand the new class-file version or new attributes. A JDK migration may require upgrading ASM/Byte Buddy or similar tools, even when business code does not change.

This is **tool compatibility**, distinct from source and runtime compatibility.

### 8.4. Metadata outside class files

A Java artifact also contains JAR-level and build-level metadata:

- `META-INF/MANIFEST.MF`: Main-Class, Multi-Release, and other entries.
- `META-INF/services/...`: `ServiceLoader` configuration.
- `module-info.class`: JPMS requires/exports/opens/provides information.
- Reflection/resource/proxy configuration files for native-image, if used by the project.
- Library-specific or language-specific metadata, such as Kotlin metadata annotations.
- Packaging metadata, schemas, framework descriptors, or annotation processor outputs.

Renaming an implementation class without updating `META-INF/services` can prevent `ServiceLoader` from loading the provider. Shading that renames class packages while forgetting service files is a common mistake; compilation succeeding does not guarantee plugin discovery works.

### 8.5. Obfuscation, shading, and minimization

Build steps can:

- Rename classes, methods, or fields.
- Strip annotations or class-file attributes.
- Merge or drop service files.
- Remove classes that are only dynamically loaded because tools assume they are unreferenced.
- Modify manifests or module descriptors.
- Package multiple inconsistent versions of metadata.

Configure keep rules and transformation rules based on actual consumers, and verify the **final artifact**, not just pre-packaging outputs.

## 9. The same change can differ across compatibility types

### 9.1. Example: reordering an enum

~~~java
// Before
enum Phase { START, PROCESS, FINISH }

// After
enum Phase { FINISH, START, PROCESS }
~~~

Calls to `Phase.START` and `Phase.name()` may still work. However:

- Ordinals change.
- The order of `values()` changes.
- UI selecting values by declaration order may differ.
- Data persisted by ordinal is misinterpreted.
- Order-dependent tests/snapshots may fail.

This is an example of a change that **does not necessarily break binary linkage**, yet still breaks **data/behavioral compatibility**.

### 9.2. Example: changing retention

~~~java
// Old
@Retention(RetentionPolicy.RUNTIME)
@interface Track {}

// New
@Retention(RetentionPolicy.CLASS)
@interface Track {}
~~~

Compiled code may still reference the annotation type. However, `getAnnotation(Track.class)` can return `null`; frameworks registering handlers via reflection may stop working. Specialized class-file scanners may still see the metadata.

This is an example of changing the **metadata visibility contract**.

### 9.3. Example: changing an annotation element default

~~~java
@interface Export {
    boolean enabled() default true;
}
~~~

Changing the default to `false` may cause classes using `@Export` without specifying the element to stop being exported, even with no compiler or linker error.

This is an example of changing the **behavioral contract**.

### 9.4. Example: removing an enum constant still referenced by an annotation

~~~java
enum RetryMode { FAST, NORMAL, SAFE }

@interface RetryPolicy {
    RetryMode value();
}

@RetryPolicy(RetryMode.SAFE)
class Task {}
~~~

If the new version removes `SAFE` while an old annotation artifact still exists, frameworks may encounter errors when reading metadata. Meanwhile, code that does not directly call `RetryMode.SAFE` may compile yet still fail during class scanning.

This is why you must test **old compiled artifacts** and the entire classpath, not just current source.

## 10. Surveying actual consumers

To evaluate changes, map out the points where enums/annotations/metadata are used.

### 10.1. Searching in source

Search suggestions:

~~~bash
rg -n "enum |@interface |@Retention|@Target|@Repeatable|@Inherited" src
rg -n "name\(\)|ordinal\(\)|valueOf\(|values\(\)" src
rg -n "EnumType\.ORDINAL|EnumType\.STRING|AttributeConverter" src
rg -n "getAnnotation|getAnnotationsByType|getDeclaredAnnotations" src
rg -n "getGenericType|getGenericReturnType|getParameters" src
rg -n "ServiceLoader|META-INF/services|module-info" .
~~~

The commands above are just samples; adjust paths to match the project structure. When reading results, distinguish production code, tests, build logic, and generated source.

String search does not detect all behaviors because a library can read metadata internally. Therefore, check the dependencies and framework documentation the application uses.

### 10.2. Inspecting published class files

Useful commands:

~~~bash
jar tf library.jar
javap -classpath library.jar -v -p com.example.OrderState
javap -classpath library.jar -v -p com.example.EndpointRole
~~~

`javap -v` output can show:

- Enum constants as fields, metadata, and flags.
- Methods of the annotation type.
- `AnnotationDefault`.
- Runtime-visible/runtime-invisible annotations.
- `Signature` and `MethodParameters`.
- Record or module metadata when present.

If the application uses an executable JAR containing nested JARs, tools may need to extract dependencies or specify the proper classpath. Do not conclude “no annotations” if the tool has not scanned the right artifact.

### 10.3. Verifying from the framework/tool side

List the tools that actually read metadata:

| Consumer | Verification question |
|---|---|
| Spring or DI framework | Does it scan annotations at runtime or build time? |
| Hibernate/JPA | Are enums stored by name, ordinal, or converter? |
| Jackson or other serializer | Are JSON values emitted from name, toString, annotations, or custom codecs? |
| OpenAPI/JSON Schema generator | How are enum values and annotation defaults emitted? |
| Annotation processor | Does it read source, classpath, or generated metadata? |
| ASM/Byte Buddy/plugin | Does it support the new class-file version? |
| ServiceLoader | Do service files and provider classes still exist after shading? |
| Client generated from schema | Does it handle unknown enum values? |

Do not assert that a framework always has a single default behavior without checking its **actual version and configuration**.

## 11. Safe change workflow

### Step 1. Define the contract before editing

Record the published parts of the API:

- Enum names and codes.
- JSON, DB, or message values.
- Annotation types, elements, defaults, retention, target.
- Metadata attributes read by tools.
- Classpath/module path and service registrations.

Clearly mark what is an implementation detail, what is part of the public contract, and what is long-lived data.

### Step 2. Collect old-version evidence

Save the old-version artifact along with its checksum. Export outputs:

- `javap -v` of public enums and annotations.
- OpenAPI/JSON Schema snapshot if applicable.
- Sample data from the DB or messages.
- List of service files and manifest.
- Scan outputs from key frameworks.

From there, you have a baseline to compare against the new artifact.

### Step 3. Classify the change

Assign each change to one or more categories:

| Category | Example |
|---|---|
| Source-breaking | Removing a constant, renaming an annotation element |
| Binary-breaking | Removing a static enum field referenced by old consumers |
| Metadata-breaking | RUNTIME to CLASS, stripping Signature or MethodParameters |
| Data-breaking | Changing wire codes, reordering an enum stored by ordinal |
| Behavioral-breaking | Changing an annotation element default or enum meaning |
| Tool-breaking | New bytecode exceeding capabilities of old scanners/transformers |

One change can belong to multiple categories simultaneously.

### Step 4. Choose a migration with a fallback path

Prefer techniques such as:

- Adding a new API while keeping the old API for a period.
- Deprecating old names/elements before removal.
- Reading both old and new data, while writing only the new format.
- Using stable enum codes instead of ordinals.
- Adding annotation elements with explicit defaults.
- Preserving retention/target while consumers still depend on them.
- Updating schemas and code generation by version.
- Upgrading bytecode tools and preserving proper class-file attributes.
- Performing controlled data migrations with rollback capability.

### Step 5. Test the old and new consumer matrix

A reference matrix:

| Producer/Library | Consumer/Reader | Goal |
|---|---|---|
| Old | Old | Known baseline |
| New | New | New functionality works |
| New | Old | Can old consumers read the new schema/enum values or fall back? |
| Old | New | Can new consumers still read old data/metadata? |

Depending on the system, the producer is a service emitting JSON, a library containing enums, or an artifact carrying annotations; the consumer is a client, framework, compiler, or program reading class files.

Verify both **old binary consumers without recompilation** and **recompiled source consumers** when evaluating a public Java API.

### Step 6. Test on the actual release artifact

After building:

1. Identify the artifact by SHA-256.
2. Use the exact JDK and runtime configuration from the support matrix.
3. Read metadata from the packaged JAR, not only from the output directory.
4. Boot the framework and trigger features using the enums/annotations.
5. Run actual schema generation or code generation.
6. Test old data, new data, and unknown values.
7. Verify consumers already compiled against the old library.

### Step 7. Publish and deploy in order

If a new producer can emit an enum value that old consumers do not understand, upgrade consumers or deploy the ability to ignore/route unknown values **before** the producer starts emitting the new value.

For databases, migrating from ordinals to stable codes may require a dual-read/dual-write phase or migration script; rollout ordering must depend on data type and rollback requirements. Avoid switching format at a single point if multiple application versions are simultaneously reading and writing the same data store.

## 12. Common errors and how to diagnose them

| Symptom | Likely cause | What to check |
|---|---|---|
| `NoSuchFieldError` | Old bytecode references a removed/renamed enum constant | `javap` on consumer, actual loaded JAR, field names |
| `IllegalArgumentException: No enum constant ...` | `valueOf()` receives a nonexistent name | JSON/DB/config data, spelling, and aliases |
| `EnumConstantNotPresentException` | Annotation element references an enum constant that no longer exists | Old annotation metadata, new enum definition |
| `IncompleteAnnotationException` | Old annotation usage lacks a new element without a default | `AnnotationDefault` and metadata of old classes |
| `AnnotationTypeMismatchException` | Annotation element value type does not match definition | Element descriptor and class-file annotation values |
| `TypeNotPresentException` | Metadata references a type that can no longer be resolved | Classpath/module path and annotation values |
| Reflection returns `null` | Retention/target/scan path changed | RuntimeVisibleAnnotations and how scanner works |
| DI or routes not registered | Annotation/parameter metadata stripped during build | Retention, `-parameters`, shading, and framework logs |
| JSON parsing error on new status | Client enum does not support unknown values | JSON payload, schema, and decoder version |
| DB displays wrong status | Ordinal mapping shifted | Raw data, enum order, and ORM mapping |
| Service not found | Lost `META-INF/services` or provider renamed | JAR contents, service file, and class loader |
| Bytecode tool reports class version error | Scanner does not understand new class file | ASM/Byte Buddy version and JDK target |

One symptom can have multiple causes. For example, `NoSuchFieldError` is not always caused by an enum; it can also result from a regular field being removed or a wrong JAR version on the classpath.

## 13. Checklist when reviewing enum changes

- [ ] Is the enum used in public APIs, JSON, DB, events, config, or schemas?
- [ ] Do any consumers use `ordinal()` or `values()` position as an identifier?
- [ ] Does adding a constant affect `switch`, validation, mappings, or default logic?
- [ ] Are there old binary consumers referencing a removed/renamed constant?
- [ ] Do wire values have stable codes independent of `name()` and `toString()`?
- [ ] Can previously stored data still be read after the upgrade?
- [ ] Can old consumers handle new enum values or is there a clear rollout policy?
- [ ] Were annotations on constants added/removed/changed in value?
- [ ] Have schemas/documentation and generated clients been updated?
- [ ] Have unknown-value scenarios and historical data been tested?

## 14. Checklist when reviewing annotation and metadata changes

- [ ] Does `@Retention` preserve the proper reading mechanism (source, class file, or reflection)?
- [ ] Does `@Target` still permit previous usage locations?
- [ ] Do new elements have appropriate defaults?
- [ ] Were any elements removed, renamed, changed in type, or changed in default?
- [ ] Are `@Repeatable` and container annotations supported by readers?
- [ ] Does `@Inherited` alter lookup results across the class hierarchy?
- [ ] Are annotations on enum constants properly read from fields?
- [ ] Are `Signature`, `MethodParameters`, annotation, and record metadata attributes still in the JAR?
- [ ] Do shading, obfuscation, and minimization have the necessary keep rules?
- [ ] Have `META-INF/services`, manifest, and `module-info.class` been verified?
- [ ] Do bytecode scanners and plugins support the new class-file version?
- [ ] Has the actual framework/tool version been tested against the new artifact?

## 15. Combined example: changing an annotation-driven enum

Suppose a public library:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.FIELD)
@interface WireName {
    String value();
}

public enum ShipmentState {
    @WireName("queued")
    QUEUED,

    @WireName("in_transit")
    IN_TRANSIT,

    @WireName("delivered")
    DELIVERED
}
~~~

A schema generation tool reads enum constants and the `@WireName` annotation to produce the value set:

~~~json
{
  "type": "string",
  "enum": ["queued", "in_transit", "delivered"]
}
~~~

The team decides to rename the Java constant `IN_TRANSIT` to `SHIPPING` and add `RETURNED`.

Separate impacts:

1. **Java source**: modules calling `ShipmentState.IN_TRANSIT` must migrate or be provided a compatibility mechanism.
2. **Binary consumers**: old bytecode referencing the constant field may hit `NoSuchFieldError` if the old name is removed.
3. **Schema**: if `SHIPPING` retains `@WireName("in_transit")`, the old wire value can be preserved; `RETURNED` needs a new wire name.
4. **Old consumers**: must know how to handle `"returned"` before producers start emitting this value.
5. **Reflection tools**: must read annotations on fields; if retention changes to CLASS, readers using reflection will no longer see it.
6. **Database**: if Java names or ordinals were previously stored, migration is needed independently of the JSON schema.
7. **Generated code**: clients/schemas must be regenerated and bidirectional compatibility tests run.

A safe rollout could be: deploy readers supporting the new value, update data/schemas, and only then allow producers to emit the new value. If the old Java constant is part of the public binary API, keep a compatibility layer or announce a breaking release according to library policy.

## Conclusion

Enums, annotations, and metadata in class files are part of the Java contract whenever external frameworks or tools read them. Adding an enum constant might not break old field references yet still cause logic, schema, and data errors. Changing retention or annotation defaults can cause frameworks to alter behavior without any compilation error appearing. Stripping `Signature`, `MethodParameters`, or service metadata can leave an artifact runnable while breaking reflection, binding, or discovery.

To evolve an API safely, you must **identify actual consumers**, distinguish source/binary/metadata/data compatibility, record artifact baselines, test both old and new consumers, and publish a migration strategy. Verification must be performed on the final artifact with the runtime configuration and tools the system actually uses.
