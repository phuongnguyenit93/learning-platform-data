# javac Warnings, -Xlint, and Grounded Warning Handling

## 1. Why pay attention to compiler warnings?

The Java compiler checks more than syntax and data types. During compilation, `javac` can also spot suspicious code patterns: using raw types, unchecked casts, calling deprecated APIs, omitting `serialVersionUID`, unsafe generic varargs, or declaring a resource without referencing it inside a `try` body.

Such code may still compile successfully, yet warnings signal risks to correctness, compatibility, maintainability, or operations. Handling warnings in a grounded way means:

1. Understanding the exact condition that triggers the compiler warning.
2. Assessing the actual risk in the context of the code.
3. Fixing the root cause whenever possible.
4. Suppressing only when a verifiable invariant or technical rationale exists.
5. Keeping the build strict enough that new warnings do not silently accumulate.

In Java 17, the primary tools are:

- `javac`: the JDK compiler.
- `-Xlint`: enables detailed warning categories.
- `-Xlint:<key>`: enables a specific warning category.
- `-Xlint:all`: enables all lint categories supported by the compiler.
- `-Werror`: treats warnings as compilation errors.
- `@SuppressWarnings`: suppresses warnings with a clear scope and rationale.
- `--release 17`: compiles against Java 17 language, bytecode, and platform APIs.

Compiler warnings are signals to investigate. Neither ignore all warnings nor suppress them wholesale just to get a green build.

## 2. How javac emits warnings

### 2.1. Warnings vs. errors

An **error** prevents the compiler from successfully producing class output for the affected compilation unit. A **warning** indicates the compiler found a notable issue while still being able to continue compiling.

Example:

```shell
javac Example.java
```

The compiler may display warnings and still generate `.class` files. Adding `-Werror` promotes warnings to errors and fails the build:

```shell
javac -Werror Example.java
```

`-Werror` does not automatically enable all lint categories. For strict builds with lint checks, typically combine:

```shell
javac -Xlint:all -Werror Example.java
```

### 2.2. Anatomy of a diagnostic

A warning typically looks like:

```text
Example.java:12: warning: [unchecked] unchecked conversion
    List<String> names = rawNames;
                         ^
  required: List<String>
  found:    List
1 warning
```

Read in order:

- File and line: where the compiler detected the issue.
- Diagnostic kind: `warning`.
- Lint key in brackets: `unchecked`.
- Message: what the compiler cannot verify.
- Source line and caret: the relevant expression.
- Required/found types: expected type and actual type if applicable.

The lint key is very helpful when enabling or suppressing selectively. Never chase away a warning line while ignoring the underlying type or API issue causing it.

### 2.3. Default warning level and -Xlint

Not all lint categories are enabled by default in all situations. `-Xlint` or `-Xlint:all` tells the compiler to report additional issues that default mode may hide.

Example:

```shell
# Compile with default warnings.
javac --release 17 -d out src/com/acme/*.java

# Enable all lint categories.
javac --release 17 -Xlint:all -d out src/com/acme/*.java
```

Exact names and details of some lint categories can depend on the javac version. When standardizing a project on Java 17, consult JDK 17's javac documentation and use the same toolchain in CI.

## 3. Selecting warning categories with -Xlint

### 3.1. Syntax

Common forms:

```shell
javac -Xlint:all Example.java
javac -Xlint:unchecked Example.java
javac -Xlint:deprecation Example.java
javac -Xlint:all,-serial Example.java
```

- `-Xlint:all`: enable all lint categories.
- `-Xlint:unchecked`: enable unchecked operation warnings.
- `-Xlint:deprecation`: warn when using deprecated APIs.
- `-Xlint:all,-serial`: enable all categories, then disable `serial`.

List syntax allows combining multiple keys separated by commas. Prefixing a key with `-` disables it.

### 3.2. Do not use broad disabling as a long-term policy

The following reduces issue detection:

```shell
javac -Xlint:none ...
```

If a project has a legacy category it cannot resolve immediately, you can temporarily exclude only that category:

```shell
javac -Xlint:all,-deprecation ...
```

However, record the reason, affected modules, and plan to remove the exception. Do not disable `all` merely because one specific warning remains unresolved.

### 3.3. Common lint keys

The table below describes categories commonly useful in Java 17 codebases. This list does not replace official documentation for the exact javac version in use.

| Lint key | What the compiler warns about | Common resolution |
|---|---|---|
| `unchecked` | Generic operations not fully verified | Use type-safe generics, validate data at boundaries |
| `rawtypes` | Using a generic class without type arguments | Declare `List<String>`, `Map<K,V>` |
| `deprecation` | Using a deprecated API | Migrate to the replacement API, check docs |
| `removal` | Using an API marked for removal | Prioritize early migration |
| `serial` | Serializable class missing common serialization metadata | Define serialization contract and declare UID when appropriate |
| `cast` | Redundant or unnecessary cast | Remove cast or fix type at the source |
| `fallthrough` | Switch case may fall through to the next case | Add break/return or comment explaining intentional fall-through |
| `finally` | finally block cannot complete normally | Do not return/throw from finally to override control flow |
| `try` | Issues related to try-with-resources | Manage resources and lifecycle clearly |
| `static` | Accessing a static member through an instance expression | Qualify with class name |
| `varargs` | Risk of heap pollution with generic varargs | Use `@SafeVarargs` only when safety is truly proven |
| `overloads` | Overloads that may be confusing or ambiguous | Design clearly distinguishable signatures |
| `path` | Classpath/module path contains invalid or missing entry | Fix dependency/path configuration |
| `options` | Inappropriate or misused compiler options | Standardize JDK and compiler arguments |
| `processing` | Annotation processing issues | Inspect processor and build configuration |
| `auxiliaryclass` | Accessing an auxiliary class from another source file | Move top-level class to its own file |
| `preview` | Using preview features/APIs | Enable preview intentionally with matching JDK |
| `strictfp` | Unnecessary strictfp modifier in Java 17 context | Remove redundant modifier |

Other categories cover module declarations, exported APIs, class files, or annotations. When checking exact keys, consult `javac --help-lint` in JDK 17:

```shell
javac --help-lint
```

## 4. rawtypes and unchecked warnings

### 4.1. Raw types forfeit type checking

A raw type uses a generic class without specifying type arguments:

```java
import java.util.ArrayList;
import java.util.List;

List names = new ArrayList();
names.add("Alice");
names.add(42);
```

The compiler cannot guarantee the list holds only Strings. Errors surface later when reading and casting elements:

```java
String first = (String) names.get(1); // ClassCastException at runtime
```

### 4.2. Fix using generic types

```java
List<String> names = new ArrayList<>();
names.add("Alice");
names.add("Bob");

String first = names.get(0);
```

The compiler checks element types at compile time and eliminates casts when reading.

### 4.3. Unchecked conversion

Another example:

```java
List raw = obtainLegacyList();
List<String> names = raw; // unchecked conversion
```

The compiler does not know whether the actual elements are Strings. Adding a type argument to the target variable does not make the source data type-safe.

If a legacy boundary returns untyped data, convert and validate every element:

```java
static List<String> toStrings(List<?> source) {
    List<String> result = new ArrayList<>();
    for (Object item : source) {
        if (!(item instanceof String value)) {
            throw new IllegalArgumentException(
                    "Expected String but got: " +
                    (item == null ? "null" : item.getClass().getName())
            );
        }
        result.add(value);
    }
    return List.copyOf(result);
}
```

This code validates data at runtime instead of suppressing the warning. If null is allowed, adjust the contract and check null separately; the example intentionally rejects null.

### 4.4. Distinguishing rawtypes and unchecked

- `rawtypes`: warns about declaring or using a generic type without type arguments.
- `unchecked`: warns about an operation whose safety the compiler cannot verify, such as an unchecked conversion or cast.

A single line of code can trigger both warnings. Fixing it with proper generics usually eliminates both.

### 4.5. When is an unchecked cast acceptable?

Occasionally an older generic API cannot fully express a type contract. If a cast cannot be removed, you must establish an external invariant guaranteeing the type.

For example, an internal registry storing objects by class token:

```java
import java.util.HashMap;
import java.util.Map;

final class ServiceRegistry {
    private final Map<Class<?>, Object> services = new HashMap<>();

    <T> void register(Class<T> type, T instance) {
        services.put(type, type.cast(instance));
    }

    <T> T lookup(Class<T> type) {
        Object value = services.get(type);
        return value == null ? null : type.cast(value);
    }
}
```

In this example, `Class.cast` performs a runtime type check without an unchecked cast. This is usually preferable to suppressing warnings.

If using a data structure whose generic type cannot be checked with a class token, a cast guarded by a stronger invariant may be necessary. In that case:

- Enforce the invariant where data is written into the structure.
- Keep the structure encapsulated so external code cannot insert ill-typed values.
- Place `@SuppressWarnings("unchecked")` on the smallest possible variable or method.
- Write tests covering the invariant.
- Document the technical rationale rather than vague notes like "compiler warning".

## 5. deprecation and removal warnings

### 5.1. Deprecated means the API is no longer recommended

An API may be marked:

```java
@Deprecated
public void oldOperation() {
}
```

This tells callers the API is no longer recommended. It may still exist and function, yet users should consult documentation for replacements and compatibility plans.

Example:

```java
class LegacyClient {
    @Deprecated
    void connectOldWay() {
    }

    void connect() {
        connectOldWay(); // deprecation warning
    }
}
```

### 5.2. since and forRemoval

Java supports metadata:

```java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
}
```

- `since`: the version in which the API was deprecated.
- `forRemoval = true`: indicates the API is slated for future removal.

The compiler emits `deprecation` or `removal` warnings depending on the annotation/API. These signal different levels of migration urgency.

### 5.3. Checking the replacement API

When encountering the warning:

1. Open the API's Javadoc.
2. Read the `@Deprecated` and `@deprecated` descriptions.
3. Find the recommended replacement API.
4. Check differences in semantics, exceptions, threading, and resource lifecycle.
5. Migrate and run corresponding tests.

Never replace mechanically just because a new API has a similar name. The new API may change behavior or require additional configuration.

### 5.4. Do not suppress deprecation just for a green build

The following merely hides the warning:

```java
@SuppressWarnings("deprecation")
void load() {
    legacyApi();
}
```

If migration is blocked by a dependency or compatibility protocol, isolate legacy calls behind an adapter, document why, and track the dependency version. Suppression belongs at a small boundary, not across an entire package or application.

## 6. serial warnings

### 6.1. Serializable classes and serialVersionUID

A class implementing `Serializable` without declaring `serialVersionUID` can trigger a warning:

```java
import java.io.Serializable;

public class UserSession implements Serializable {
    private String userId;
}
```

The serialization runtime computes a default UID from the class structure. Modifying the class can alter the computed UID, breaking compatibility when deserializing data serialized by another version.

### 6.2. Declare UID when serialization is part of the contract

```java
import java.io.Serial;
import java.io.Serializable;

public class UserSession implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String userId;
}
```

`@Serial` was introduced in Java 14 and is present in Java 17. This annotation lets the compiler validate certain serialization-related declarations. The UID field is normally declared `private static final long`.

Do not blindly add an arbitrary UID to every class just to silence warnings. First decide whether the class truly needs Java native serialization. If it does not need a serialized form, remove `implements Serializable`; if compatibility is required, manage the UID and schema migration as part of the contract.

### 6.3. serialVersionUID is not an automatic schema version

The UID checks compatibility at the Java serialization level. It does not replace versioning of APIs, database schemas, or message formats. Field changes still require checking serialization behavior and legacy payloads.

## 7. cast warnings

### 7.1. Redundant casts

Example:

```java
String name = (String) "Alice";
```

The cast is unnecessary because the expression already has type String. It can be removed:

```java
String name = "Alice";
```

Redundant casts clutter code and sometimes obscure overly broad source variable types.

### 7.2. Fix the type at the source instead of casting at the destination

Avoid repeated casts when the source variable can be typed accurately:

```java
Object value = "Alice";
String name = (String) value;
```

If the data is always a String, declare:

```java
String name = "Alice";
Object value = name;
```

If the type is genuinely unknown, guard the cast with a runtime check:

```java
if (value instanceof String name) {
    use(name);
} else {
    handleUnexpectedType(value);
}
```

### 7.3. Do not confuse cast warnings with unchecked casts

A `cast` warning often indicates a redundant cast; an `unchecked` warning relates to generic type erasure where the compiler cannot verify cast safety. Read the specific lint key to fix the right issue.

## 8. fallthrough warnings in switch

### 8.1. Unintentional fallthrough

In traditional switch statements, omitting `break`, `return`, or an equivalent terminator allows control flow to fall through into the next case:

```java
switch (status) {
    case 1:
        start();
    case 2:
        notifyUser();
        break;
    default:
        logUnknown();
}
```

When status is 1, both `start()` and `notifyUser()` run. Unless intentional, this is a logic bug.

### 8.2. Terminate cases explicitly

```java
switch (status) {
    case 1:
        start();
        break;
    case 2:
        notifyUser();
        break;
    default:
        logUnknown();
}
```

Where Java 17 switch expressions fit, they also clarify each branch's result:

```java
String label = switch (status) {
    case 1 -> "STARTED";
    case 2 -> "NOTIFIED";
    default -> "UNKNOWN";
};
```

### 8.3. Intentional fallthrough

Some switch statements intentionally group multiple case labels:

```java
switch (day) {
    case SATURDAY:
    case SUNDAY:
        return "weekend";
    default:
        return "weekday";
}
```

This is multiple labels sharing one body, not falling through from a non-empty case body into another. If fallthrough between non-empty case bodies is genuinely required, add a comment explaining why and follow your project's compiler/tooling conventions.

## 9. finally warnings

### 9.1. Do not return from finally

```java
static int calculate() {
    try {
        return 10;
    } finally {
        return 0; // overrides the return value from try
    }
}
```

Returning inside `finally` overrides any earlier return value and discards thrown exceptions. This is a dangerous pattern that the compiler flags under the `finally` lint key.

### 9.2. Do not throw from finally to replace the original exception

If `finally` throws a new exception, the original exception can be lost in normal control flow. For resources, prefer try-with-resources so Java manages closing and suppressed exceptions.

### 9.3. Use finally for cleanup that does not alter control flow

```java
Lock lock = obtainLock();
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

`finally` is appropriate for cleanup such as unlocking or releasing state, provided cleanup neither returns nor throws unmanaged exceptions that mask the primary outcome.

## 10. try and try-with-resources warnings

### 10.1. Closing resources manually in finally is error-prone

Old pattern:

```java
InputStream input = openInput();
try {
    read(input);
} finally {
    input.close();
}
```

If both reading and closing throw exceptions, manual code can lose the original exception or create tangled cleanup branches.

### 10.2. Use try-with-resources

```java
try (InputStream input = openInput()) {
    read(input);
}
```

The JVM/compiler automatically closes the resource on block exit, even when exceptions occur. Exceptions during `close()` are recorded as suppressed exceptions.

### 10.3. Resource not referenced in the body

The `try` lint key can warn when a resource declared in try-with-resources is never referenced in the block body. This can indicate a resource was opened accidentally without being used.

Example:

```java
try (var lock = channel.lock()) {
    updateFile();
}
```

If the resource should be checked, use it meaningfully:

```java
try (var lock = channel.lock()) {
    if (!lock.isValid()) {
        throw new IllegalStateException("File lock is not valid");
    }
    updateFile();
}
```

Do not insert meaningless dummy calls merely to silence the compiler. If a resource is opened strictly for scoped close behavior, consider a more suitable API or document the reason and suppress narrowly if the compiler still warns.

### 10.4. AutoCloseable and close exceptions

When defining custom resource types, implement `AutoCloseable` and specify `close()` behavior clearly. Avoid designing `close()` to throw unexpected exceptions callers cannot handle. When used with try-with-resources, understand the rules for primary and suppressed exceptions.

## 11. static warnings

### 11.1. Do not invoke static members via an instance

```java
class Config {
    static String environment() {
        return "prod";
    }
}

Config config = new Config();
String env = config.environment();
```

`environment()` is static, yet called through an instance variable. This misleads readers into thinking the outcome depends on the object instance.

Fix:

```java
String env = Config.environment();
```

### 11.2. Use static imports selectively

Static imports can be handy for clear constants or helpers:

```java
import static java.lang.Math.max;

int largest = max(a, b);
```

Avoid static importing too many generically named methods that obscure where methods originate. The `static` warning points out static member access via an expression; fix it using the class name for clarity.

## 12. varargs warnings and heap pollution

### 12.1. Generic varargs carry risks

Varargs are implemented via arrays. For non-reifiable generic types, the compiler cannot guarantee the runtime array holds elements of the right type parameter.

Example:

```java
static void addToFirst(List<String>... lists) {
    Object[] array = lists;
    array[0] = List.of(42); // can cause heap pollution
    String value = lists[0].get(0);
}
```

Generic types are erased at runtime; manipulating the array through an `Object[]` reference can inject improperly typed data.

### 12.2. @SafeVarargs only when the method is genuinely safe

`@SafeVarargs` suppresses warnings on varargs methods/constructors with generic element types when the author proves the body causes no heap pollution. In Java 17, this annotation applies to static methods, final instance methods, private instance methods, and constructors.

Example method that only reads the lists and never stores into or exposes the varargs array:

```java
@SafeVarargs
static int totalSizes(List<?>... lists) {
    int total = 0;
    for (List<?> list : lists) {
        total += list.size();
    }
    return total;
}
```

Here the method only reads each list, never mutates array slots, and never lets the array escape. The annotation reflects a verifiable invariant.

Never add `@SafeVarargs` to silence warnings if the method writes into the array, returns the array, or passes it to code that could mutate elements. The annotation does not make unsafe code safe.

### 12.3. Prefer collection APIs when appropriate

If generic varargs add complexity, accept `List<T>` or `Collection<T>` instead of an array:

```java
static int totalSizes(List<? extends List<?>> lists) {
    return lists.stream().mapToInt(List::size).sum();
}
```

Collection APIs explicitly model a group of items and avoid risks specific to generic arrays.

## 13. overloads warnings and ambiguous APIs

Overloads make APIs convenient, yet signatures that are too close together can create confusing calls, especially with lambdas or functional interfaces.

Example:

```java
static void process(Runnable action) {
}

static void process(java.util.concurrent.Callable<?> action) {
}

// A void-returning lambda can match Runnable;
// a value-returning lambda can match Callable.
process(() -> System.out.println("run"));
```

In complex cases, overloads can make calls ambiguous or shift overload resolution when new APIs are added.

Design guidelines:

- Choose distinct method names when semantics differ.
- Avoid overloads differing only in functional interfaces that callers struggle to distinguish.
- Provide descriptively named factories or builders.
- Check source compatibility when adding overloads to public library APIs.

Not every overload is wrong. The warning prompts you to check for potential confusion and compatibility impact.

## 14. strictfp warnings in Java 17

Starting in Java 17, floating-point expressions are always evaluated under Java's strict floating-point semantics. The `strictfp` modifier on classes, interfaces, or methods therefore no longer makes a difference as it did in older Java releases; the compiler warns that the modifier is unnecessary.

Example:

```java
public strictfp class Calculator {
    public strictfp double calculate(double a, double b) {
        return a / b;
    }
}
```

In Java 17 code, remove the redundant modifier:

```java
public class Calculator {
    public double calculate(double a, double b) {
        return a / b;
    }
}
```

Do not carry the old modifier into Java 17 code merely because it was once recommended for consistent floating-point results across older architectures.

## 15. path, options, and processing warnings

Not every warning comes from source code. Some warnings reflect build configuration:

### 15.1. path

`-Xlint:path` detects nonexistent classpath/module path entries or misconfigured paths.

Example:

```shell
javac -Xlint:path -cp "lib/missing.jar" Example.java
```

If a dependency is missing, fix dependency resolution or the path. Do not create an empty dummy JAR or suppress the warning to turn the build green.

### 15.2. options

`-Xlint:options` catches issues with compiler options, such as options incompatible with the chosen release/source/target. Standardize the JDK and use `--release 17` to prevent drift between developer machines and CI.

### 15.3. processing

`-Xlint:processing` relates to annotation processing. If a project uses processors to generate source or metadata, check:

- Is the processor discovered properly?
- Does the processor support JDK 17?
- Does the processor emit diagnostics or leave annotations unclaimed?
- Does the build explicitly configure processor path and version?

Do not disable annotation processing if code relies on generated sources. If the project uses no processors, inspect compiler settings to remove unnecessary dependencies or options.

## 16. module and exported API warnings

In modular projects, the compiler can warn about module descriptors or exported APIs. These warnings usually concern how other modules consume the API and declared dependencies.

Key principles:

- Export only packages that are truly public API.
- Do not export internal packages merely to work around reflection access errors.
- Distinguish `exports` and `opens`: exports exposes compile-time API; opens permits deep runtime reflection.
- Declare `requires` and `requires transitive` according to the API contract, rather than adding transitive dependencies arbitrarily.
- Inspect a dependency's module name with `jar --describe-module`.

If a warning mentions automatic modules or unstable dependencies in the module graph, identify the actual dependency and review its module descriptor or automatic module name. Do not invent module names assumed from artifact filenames.

## 17. @SuppressWarnings: when and how to use it responsibly

### 17.1. Suppression is an annotation, not a fix

`@SuppressWarnings` tells the compiler or tool not to emit a category of warnings within the annotated scope:

```java
@SuppressWarnings("unchecked")
void adaptLegacyApi() {
    // ...
}
```

The annotation does not alter runtime behavior, validate invariants, or make an unsafe cast safe. Suppressing incorrectly removes the warning while leaving the risk intact.

### 17.2. Use the narrowest scope

Never suppress an entire class if only one line needs handling. Prefer:

1. Local variable.
2. Small method.
3. Specific constructor or field.
4. Class only when multiple operations in the class share a single proven invariant.

Example:

```java
Object legacyValue = legacyApi.read();

// legacyApi's contract guarantees the returned value is List<String>
// when requested with key "display-names"; the producer validates every element.
@SuppressWarnings("unchecked")
List<String> displayNames = (List<String>) legacyValue;
```

This is justified only if the contract genuinely guarantees the type and enforces it at the boundary. Without that guarantee, perform runtime type checks instead of suppressing.

### 17.3. Suppress specific categories

Write:

```java
@SuppressWarnings("unchecked")
```

rather than:

```java
@SuppressWarnings("all")
```

Specific categories tell reviewers exactly which issue is accepted while keeping other warning categories active.

### 17.4. Document a verifiable rationale

A responsible suppression should explain:

- Why the warning cannot be eliminated at the source.
- Which invariant guarantees safety.
- Where that invariant is enforced.
- Which tests protect the invariant.

Example:

```java
@SuppressWarnings("unchecked") // Legacy registry stores values only after checking via type token.
private <T> T readLegacyEntry(Class<T> type, Object value) {
    // ...
}
```

This comment is valid only if the code genuinely checks and maintains the type token. Otherwise, update the code to perform type checking.

### 17.5. Suppress deprecation inside a bounded adapter

When forced to call a deprecated API because a dependency has no compatible replacement yet, isolate the call:

```java
final class LegacyAdapter {

    @SuppressWarnings("deprecation")
    void invokeLegacyEndpoint() {
        // Keep the deprecated call confined to this boundary.
        legacyClient.oldEndpoint();
    }
}
```

Attach an issue/target version for migration. Never suppress deprecation across an entire module just to avoid seeing warnings.

## 18. Using -Werror in the build pipeline

### 18.1. Why promote warnings to errors?

If CI prints warnings yet still succeeds, new warnings are easily overlooked. Over multiple merges, warning counts climb and distinguishing new issues from old debt becomes difficult.

`-Werror` causes the build to fail when the compiler emits a warning. Once a codebase is clean or has a controlled baseline of exceptions, this keeps compiler diagnostics stable.

### 18.2. Adoption roadmap

For an existing codebase, roll out in phases:

1. Run `-Xlint:all` and collect current warnings.
2. Group warnings by lint key and module.
3. Fix issues that can be resolved directly.
4. Schedule migration for deprecated/removal APIs.
5. Add grounded suppressions for boundaries that cannot be removed immediately.
6. Enable `-Werror` in CI.
7. Keep JDK/compiler options identical between developers and CI.

Do not turn on `-Werror` immediately on a codebase with hundreds of unclassified warnings and no remediation plan; that blocks unrelated changes. Bring the warning baseline under control first.

### 18.3. Full javac command

Assuming sources live in `src`:

```shell
javac --release 17 \
  -Xlint:all \
  -Werror \
  -d out \
  src/com/acme/Main.java
```

With multiple source files:

```shell
javac --release 17 -Xlint:all -Werror -d out \
  src/com/acme/*.java
```

In modular projects, use `--module-source-path` and `-m` according to the module layout instead of compiling a standalone file.

### 18.4. Using --release 17

`--release 17` configures the compiler for Java 17:

- Java 17 language level.
- Java 17 bytecode target.
- Java SE 17 platform APIs that code is permitted to reference.

Using only `-source 17 -target 17` does not ensure the compiler restricts platform APIs the way `--release` does. When building on a newer JDK for an application targeting Java 17, `--release 17` is the proper choice.

## 19. Configuration in Maven and Gradle

### 19.1. Maven Compiler Plugin

Example compiler configuration:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <release>17</release>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:all</arg>
            <arg>-Werror</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Set the plugin version according to your project's dependency/plugin management standards. In multi-module Maven builds, parent configuration applies according to plugin/module inheritance rules; inspect the effective POM to confirm which modules actually receive the arguments.

### 19.2. Gradle Groovy DSL

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.compilerArgs += ['-Xlint:all', '-Werror']
}
```

This configures `JavaCompile` tasks in the project. In multi-project builds, place it in a convention plugin or shared configuration so subprojects enforce the same policy.

### 19.3. Avoiding drift between local and CI

A developer on JDK 17 and CI on JDK 21 with mismatched source releases can see different diagnostics. Always:

- Pin the JDK toolchain.
- Use `--release 17`.
- Use identical compiler arguments.
- Log the JDK vendor/version in CI output.
- Ensure IDEs do not silently use a different compiler from the main build.

## 20. Reading and triaging warnings in CI

A practical review workflow:

**1. Group by lint key.**  
For instance `unchecked`, `deprecation`, `serial`, or `try` to organize work items.

**2. Determine whether a warning is new or pre-existing.**  
If the codebase carries legacy debt, track counts per module/package and disallow new warnings.

**3. Locate the source cause.**  
Inspect the warning line, generic types, module descriptor, or compiler option involved.

**4. Choose the remediation.**  
Fix the source, migrate APIs, update dependencies, adjust build config, or suppress with justification.

**5. Re-run the compiler with the same flags.**  
Confirm the specific warning disappears because the cause was fixed, not because lint was turned off.

**6. Verify behavior.**  
Run relevant tests because fixing generics, serialization, or deprecated APIs can affect runtime behavior.

**7. Enforce -Werror.**  
Once the warning baseline is clean, keep `-Werror` enabled so new warnings fail the build.

## 21. Common pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Ignoring all warnings | Generic, legacy API, or resource bugs accumulate | Enable lint and triage |
| Using `-Werror` without enabling lint | Promotes only default-enabled warnings to errors | Combine with `-Xlint:all` where appropriate |
| Using raw types to avoid complex generics | Loses type checks and risks ClassCastException | Use generic types or validate at boundaries |
| Writing unchecked casts and immediately suppressing | Masks broken type contracts | Check types at runtime or prove the invariant |
| Suppressing `all` on large classes | Hides future unrelated warnings | Suppress specific keys with narrow scope |
| Suppressing deprecation without a plan | Legacy APIs/dependencies linger indefinitely | Isolate behind an adapter with a migration target |
| Adding serialVersionUID to every class | Creates unintended serialization contracts | Implement Serializable only when domain requires it |
| Adding break to every case blindly | May break intentional fallthrough logic | Confirm semantics before editing |
| Returning from finally | Masks prior exceptions or return values | Use finally strictly for cleanup |
| Closing resources across multiple manual branches | Easy to miss close or drop exceptions | Use try-with-resources |
| Calling static methods via instances | Misleads readers about dispatch | Qualify with class name |
| Adding @SafeVarargs casually to silence warnings | Heap pollution can still happen | Prove the method neither writes nor leaks the array |
| Using -source/-target instead of --release for API compatibility | May reference APIs newer than target runtime | Use `--release 17` |
| Running lint only on developer machines | CI may use different flags/JDKs | Standardize toolchain and compiler args |
| Disabling lint due to an old dependency | Loses diagnostic signals across application source | Scope exceptions to the category or upgrade dependency |

## 22. Putting it together: compile warnings and fixes

Save **LintDemo.java**:

```java
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

class LegacyApi {
    @Deprecated(since = "17", forRemoval = true)
    static void oldApi() {
    }
}

class LintDemo {

    static void helper() {
    }

    static void rawTypes() {
        List values = new ArrayList();
        values.add("Alice");
        values.add(42);
        List<String> names = values;
    }

    static class Session implements Serializable {
        private String userId;
    }

    static void staticCall() {
        LintDemo demo = new LintDemo();
        demo.helper();
        LegacyApi.oldApi();
    }

    public static void main(String[] args) {
        rawTypes();
        staticCall();
    }
}
```

Compile:

```shell
javac --release 17 -Xlint:all LintDemo.java
```

The compiler can warn about deprecation/removal, rawtypes, unchecked, and static access (exact warnings depend on code/compiler). This example intentionally contains patterns requiring remediation.

Fixed version:

```java
import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

class LintDemo {

    static class Session implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String userId;

        Session(String userId) {
            this.userId = userId;
        }
    }

    static List<String> names() {
        List<String> values = new ArrayList<>();
        values.add("Alice");
        values.add("Bob");
        return List.copyOf(values);
    }

    public static void main(String[] args) {
        System.out.println(names());
    }
}
```

In the fixed version, raw types are replaced with generic types and serialization metadata is declared because the class retains its Serializable contract. The deprecated API is no longer called; in a real project, replace it with the new API per the dependency's documentation.

Strict compilation:

```shell
javac --release 17 -Xlint:all -Werror LintDemo.java
```

If any warnings remain in enabled categories, compilation fails. This illustrative example does not imply all dependency warnings vanish automatically; read the output of your actual compiler and source build.

## 23. Practice exercises

### Exercise 1 — Enable all lint checks

Create a Java file containing raw types, a redundant cast, a deprecated API, and a Serializable class without a UID. Compile with:

```shell
javac --release 17 -Xlint:all Example.java
```

Record each lint key and its corresponding source line.

### Exercise 2 — Fix rawtypes and unchecked

Replace raw `List`/`Map` with generic types. When data comes from a legacy API, convert it by checking every element. Verify no unchecked suppression is needed.

### Exercise 3 — Handle deprecation and removal

Create an API marked `@Deprecated(since = "17", forRemoval = true)`, call it from a client class, and observe the warning. Write an adapter using a replacement API; explain when temporary suppression is acceptable.

### Exercise 4 — Check serial

Create a Serializable class and inspect lint output. Add `@Serial` and `serialVersionUID`. Explain why adding a UID alone does not make every class change serialization-compatible.

### Exercise 5 — Spot fallthrough

Write a switch statement with accidental fallthrough. Enable `-Xlint:fallthrough`, fix it using break/return or a switch expression, and verify each case's result.

### Exercise 6 — Check finally and try-with-resources

Write a method returning from finally and another closing a stream manually. Observe the warnings, then rewrite using proper cleanup and try-with-resources.

### Exercise 7 — Generic varargs

Write a method accepting `List<String>...` and try mutating an element via `Object[]`. Observe the warning. Then rewrite it to only read, apply `@SafeVarargs` if provably safe, or switch to a Collection API.

### Exercise 8 — Enable -Werror in the build

Run `-Xlint:all` on an existing project. Categorize warnings, resolve or add grounded suppressions, then enable `-Werror`. Confirm a new warning fails CI.

### Exercise 9 — Verify the Java 17 API boundary

Compile on a newer JDK with `--release 17`. Attempt to reference an API available only in the newer JDK and observe the compiler error. Explain why `--release` is better than setting only source/target.

## 24. Self-check questions

1. How does a compiler warning differ from a compile error?
2. What roles do `-Xlint` and `-Xlint:all` serve?
3. Does `-Werror` automatically enable every lint category?
4. Which benefits of generics are lost when using raw types?
5. What is the difference between `rawtypes` and `unchecked` warnings?
6. Why can an unchecked cast cause a runtime error?
7. When should you prefer `Class.cast` over a direct cast?
8. How does `@Deprecated` differ from `forRemoval = true`?
9. Why might a Serializable class need `serialVersionUID`?
10. What does `@Serial` allow the compiler to verify?
11. What is fallthrough and when might it be intentional?
12. Why is returning from finally dangerous?
13. How does try-with-resources handle exceptions thrown during close?
14. How can heap pollution arise with generic varargs?
15. What conditions must be proven before applying `@SafeVarargs`?
16. Why should static members be qualified by class name?
17. How does `--release 17` differ from `-source 17 -target 17`?
18. When should `-Werror` be enabled in CI?
19. Why must warning suppressions have narrow scope and a verifiable rationale?
20. When compiler warnings come from an annotation processor or build path, what should you inspect?

## 25. References

- [Java SE 17 javac Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-Xlint`, `-Werror`, `--release`, and compiler options.
- [Java SE 17 javac — lint options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html#lint): warning categories and syntax for enabling/disabling lint keys.
- [Java Language Specification, Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/): language rules, generics, switch, and serialization details.
- [Java SE 17 API — Deprecated](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Deprecated.html): `since` and `forRemoval` metadata.
- [Java SE 17 API — Serial](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html): annotation for serialization declarations.
- [Java SE 17 API — SuppressWarnings](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SuppressWarnings.html): suppression scope and meaning.
- [Java SE 17 API — SafeVarargs](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SafeVarargs.html): safety contract for generic varargs.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): floating-point semantics in Java 17.

Compiler warnings highlight risks in source code and build configuration. Enable `-Xlint` to expose issues clearly, eliminate root causes using type-safe APIs and proper resource management, migrate away from deprecated/removal APIs, and enforce `-Werror` so new warnings fail CI. Suppress only when a technical invariant is proven, keep suppression scope minimal, and document the rationale so future maintainers can verify it.
