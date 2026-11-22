# Defining Field, Property, or Accessor Policies in Java Reflection Tools

## 1. Why have a policy instead of scanning every member?

When building a tool using reflection (serializer, object inspector, mapper, validator, form generator, exporter...), the same value can appear in multiple forms:

- **Field**: a storage slot such as `private String name` or `public int count`, described by `java.lang.reflect.Field`.
- **JavaBeans property**: a logical attribute determined by convention-based method pairs, e.g. `getName()` / `setName(String)`, or `isActive()` for booleans; there may be **no field with the same name**. Metadata is typically read via `java.beans.Introspector` and `PropertyDescriptor`.
- **Record component**: a component declared in a record header, e.g. `record User(String name) {}`, with accessor `name()` and its own `RecordComponent`.
- **Custom accessor**: a method with data-retrieval semantics like `displayName()` or `fetchBalance()`; not every zero-parameter method should become a property.

If a tool scans both fields and getters, it may output `name` twice; if it forces calls to all getters, it can trigger database queries, business errors, or data leaks. If it arbitrarily uses `setAccessible(true)`, the tool can violate module boundaries or read unauthorized data.

An **access policy** is a rule set that clearly specifies *metadata sources*, *which members are selected*, *naming rules*, *read/write permissions*, *precedence on conflict*, *output order*, *error handling*, and *security boundaries*. The policy must be decided before scanning/reading an object; never let behavior accidentally depend on the return order of `getDeclaredFields()` or `getDeclaredMethods()`.

### Some scenarios

| Context | Potentially suitable policy | Points to control |
| --- | --- | --- |
| Simple inspector on DTOs with public fields | Public instance fields | Do not assume private fields are also allowed to be read |
| Framework using JavaBeans contract | Valid getters/setters from `Introspector` | Exclude broken getters and getters with side effects; check permissions |
| Exporting record data | Record components by header | Use `getRecordComponents()` and accessor `name()`, do not assume `getName()` |
| API serializer for sensitive data | Explicit allowlist + annotation/config | Only output approved fields; protect secrets |
| Framework with mixed domain objects | Explicit policy per type or annotation | Avoid automatically merging/overwriting colliding fields and properties |

## 2. Properly distinguishing fields, properties, and accessors

### Field: direct storage

Given:

```java
class Account {
    private String name;
    public String alias;
}
```

`Account.class.getDeclaredFields()` finds fields **declared directly on the class** (including private ones), whereas `Account.class.getFields()` finds accessible public fields, including inherited public fields. These two APIs have different scopes; `getDeclaredFields()` does not automatically fetch inherited fields.

Discovering a field via metadata does not mean the program has permission to read its value. `Field.get(target)` requires a valid receiver and appropriate access rights. For static fields, the target argument is ignored; for instance fields, target must be a compatible instance. Java reflection also provides `Field.getInt`, `getBoolean`, etc. for primitives.

**A field is not equivalent to a property**: a field may be internal data; a property may compute a value or delegate to another system. Do not automatically serialize every private field just because the tool has the technical capability to do so.

### JavaBeans property: method contract

`Introspector.getBeanInfo(type, Object.class).getPropertyDescriptors()` returns property metadata according to the JavaBeans convention, excluding parts inherited from `Object` via the stop class. A `PropertyDescriptor` can provide:

- `getName()`: logical name, such as `active`.
- `getReadMethod()`: getter if present.
- `getWriteMethod()`: setter if present.
- `getPropertyType()`: property type when determinable.

For example, `boolean isActive()` under the JavaBeans convention typically produces property `active`; `getBalance()` can be a read-only property if there is no setter. A setter-only property has `getReadMethod() == null` and **cannot be read** from that descriptor alone.

`Introspector.decapitalize` has its own naming rules; for instance, `getURL()` typically maps to property `URL`, not `uRL`. Do not convert names simply by lowercasing the first letter in all cases. JavaBeans descriptors coming from inheritance and custom `BeanInfo` may differ from naive inference from method names.

### Record component: record header contract

Example:

```java
public record Receipt(String code, int total) {}
```

`Receipt.class.isRecord()` is `true`. `Receipt.class.getRecordComponents()` returns `RecordComponent` objects in declaration order: `code`, `total`. The accessors are `code()`, `total()`, **not** `getCode()` or `getTotal()`. `getRecordComponents()` returns `null` for non-record classes, so you must check `isRecord()` first.

Record components are not automatically identical to JavaBeans properties in every tool: traditional JavaBeans introspection relies on `getX()/isX()`, whereas record accessors are named after the components. If a tool must support records, define a dedicated record branch.

### Custom accessor: accept only with a contract

A parameterless `public String displayName()` is **not necessarily** a property. If a tool selects non-JavaBeans accessors, there must be a transparent condition such as an `@Expose` annotation, user-declared metadata, or a standard application interface. Do not scan all zero-argument methods and speculatively invoke them: you may hit `close()`, `reset()`, `delete()`, or expensive operations, even if some have matching return types.

## 3. Policy decisions to lock down

Before writing the scanner, explicitly record answers to these questions:

| Decision | Common options | Implementation recommendation |
| --- | --- | --- |
| Member source | `PUBLIC_FIELD`, `BEAN_PROPERTY`, `RECORD_COMPONENT`, `ANNOTATED_ACCESSOR`, or combination | Pick a deterministic default; allow intentional overrides |
| Selected members | Public-only, allowlist, annotation, module-allowed visibility | Public + allowlist by default for externally exported data |
| Instance/static | Instance only or include static | Usually exclude static because it does not belong to an object's state |
| Synthetic/bridge | Include compiler-generated members or not | Exclude synthetic fields/methods and bridge methods when scanning raw methods |
| Mutable/read-only | Read, write, or both | Separate `readable` and `writable`; do not infer from field existence |
| Inheritance | Include inherited members or declared only | Document per API; handle override/hiding |
| Public name | Field name, bean property name, record component name, or annotation alias | Normalize output names and check for duplicates |
| Order | Record header order, by name, by `order` annotation | Specify explicitly; do not rely on reflection return order |
| Null & getter errors | Keep null, skip, record error by path | Do not silently convert null to the string `"null"` |
| Name collisions | Which takes priority? error? | Default to reporting ambiguity; prioritize only when policy explicitly declares it |
| Access rights | Public, `privateLookupIn`, conditional `setAccessible` | Respect module boundaries, minimize deep reflection |
| Performance | Introspect every time or cache metadata | Cache descriptors by `Class<?>`; do not arbitrarily cache object values |

**Policy must match the output goal:** a serializer serving a public API usually has different boundaries from an internal debugger; a read (export) policy also differs from a write (binding/deserialization) policy. Avoid an `includeAll=true` flag that merges all cases with unpredictable consequences.

## 4. Recommended policy model and traversal flow

A design can consist of three layers:

1. **Discovery**: from `Class<?>`, gather the list of fields, properties, record components, or registered accessors according to the policy.
2. **Selection & normalization**: apply allowlist/denylist/annotations, exclude static/synthetic, determine logical name, visibility, nullability, readable/writable, resolve collisions, and sort deterministically.
3. **Execution**: only when requested, invoke `Field.get` or the getter/record accessor; record results, classify exceptions, and avoid letting one property's error break the entire output if the contract permits partial results.

Example intermediate descriptor (fragment, not a complete program):

```java
enum SourceKind { FIELD, BEAN, RECORD, EXPLICIT_ACCESSOR }

record MemberDescriptor(
        String externalName,
        Class<?> valueType,
        SourceKind sourceKind,
        boolean readable,
        boolean writable
) {}
```

In a real system, the descriptor should hold a controlled execution strategy, such as a reader/writer function or `Field`/`Method`/`MethodHandle` reference, plus annotation/ownership metadata. **Do not choose how to read by string name** after receiving a descriptor: names may be aliased, overridden, or duplicated.

Recommended rule for `AUTO`: if target is a record, use record components; if it is an application-defined bean, use JavaBeans; if public fields are desired, explicitly choose `PUBLIC_FIELD`. This is simply **a tool-defined policy**, not automatic behavior of the JVM or reflection API. To combine multiple sources, design an explicit precedence, e.g., explicit annotation → record → JavaBeans → public field, and report a collision when two sources do not share the same semantics.

Decision flow:

```text
target + policy
    |
    +-- record && policy=AUTO ? RECORD_COMPONENT
    |
    +-- policy=AUTO ? BEAN_PROPERTY
    |
    +-- policy explicit ? corresponding source
    |
    v
metadata -> filter -> normalize names -> collision check
    -> stable order -> access check -> execute accessor -> result
```

## 5. Complete Java 17+ example: same object, three reading modes

The following program intentionally supports **three separate modes**:

- `PUBLIC_FIELD`: reads public, non-static, non-synthetic fields.
- `BEAN_PROPERTY`: reads getters discovered via JavaBeans `Introspector`; skips write-only properties, reading only when `getReadMethod() != null`.
- `RECORD_COMPONENT`: reads the record's components directly.
- `AUTO` is a program-chosen policy: records use record components; other objects use JavaBeans. It does not try to merge two sources.

Save as **`AccessPolicyDemo.java`**:

```java
import java.beans.IntrospectionException;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class AccessPolicyDemo {
    enum Strategy { PUBLIC_FIELD, BEAN_PROPERTY, RECORD_COMPONENT, AUTO }

    public static final class Account {
        public String alias = "alpha";
        private int credits = 7;

        public int getCredits() { return credits; }
        public void setCredits(int credits) { this.credits = credits; }
        public boolean isActive() { return true; }
    }

    public record Receipt(String code, int total) {}

    record Entry(String name, Object value) {}

    static List<Entry> read(Object target, Strategy requested)
            throws ReflectiveOperationException, IntrospectionException {
        Objects.requireNonNull(target, "target");
        Class<?> type = target.getClass();

        Strategy mode = requested == Strategy.AUTO
                ? (type.isRecord()
                        ? Strategy.RECORD_COMPONENT
                        : Strategy.BEAN_PROPERTY)
                : requested;

        List<Entry> entries = new ArrayList<>();
        switch (mode) {
            case PUBLIC_FIELD -> {
                for (Field field : type.getFields()) {
                    if (field.isSynthetic()
                            || Modifier.isStatic(field.getModifiers())) {
                        continue;
                    }
                    entries.add(new Entry(field.getName(), field.get(target)));
                }
            }
            case BEAN_PROPERTY -> {
                for (PropertyDescriptor p :
                        Introspector.getBeanInfo(type, Object.class)
                                .getPropertyDescriptors()) {
                    Method getter = p.getReadMethod();
                    if (getter == null
                            || Modifier.isStatic(getter.getModifiers())) {
                        continue;
                    }
                    entries.add(new Entry(p.getName(), getter.invoke(target)));
                }
            }
            case RECORD_COMPONENT -> {
                if (!type.isRecord()) {
                    throw new IllegalArgumentException(
                            "RECORD_COMPONENT requires a record");
                }
                for (RecordComponent component : type.getRecordComponents()) {
                    entries.add(new Entry(
                            component.getName(),
                            component.getAccessor().invoke(target)));
                }
            }
            default -> throw new IllegalStateException(
                    "Unsupported mode: " + mode);
        }

        entries.sort(Comparator.comparing(Entry::name));
        return entries;
    }

    static String describe(Object target, Strategy strategy)
            throws ReflectiveOperationException, IntrospectionException {
        return read(target, strategy).stream()
                .map(entry -> entry.name() + "=" + entry.value())
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) throws Exception {
        Account account = new Account();
        Receipt receipt = new Receipt("R1", 45);

        System.out.println("FIELD(Account): "
                + describe(account, Strategy.PUBLIC_FIELD));
        System.out.println("BEAN(Account): "
                + describe(account, Strategy.BEAN_PROPERTY));
        System.out.println("AUTO(Account): "
                + describe(account, Strategy.AUTO));
        System.out.println("RECORD(Receipt): "
                + describe(receipt, Strategy.RECORD_COMPONENT));
        System.out.println("AUTO(Receipt): "
                + describe(receipt, Strategy.AUTO));
    }
}
```

Compile and run with JDK 17+:

```bash
javac --release 17 AccessPolicyDemo.java
java AccessPolicyDemo
```

Exact stdout:

```text
FIELD(Account): alias=alpha
BEAN(Account): active=true, credits=7
AUTO(Account): active=true, credits=7
RECORD(Receipt): code=R1, total=45
AUTO(Receipt): code=R1, total=45
```

Output explanation:

- `Account.alias` is a public field so it is selected by `PUBLIC_FIELD`. `credits` is a private field and does not appear in `getFields()`.
- JavaBeans sees `getCredits()` and `isActive()`, so it reads `credits=7` and `active=true`. It does not infer a JavaBeans property from the `alias` field alone.
- `Receipt` is a record: `getRecordComponents()` gets `code` and `total`; the corresponding accessors are `code()` and `total()`. The `AUTO` policy uses the record branch.
- The output order is deterministic because the program **explicitly sorts by name**. The order in which reflection APIs return items in general should not be treated as a sorting contract.
- The example uses nested types controlled by the program, so `setAccessible(true)` is not needed. Objects owned by third parties may impose different permission/module requirements.

This is a **read-only** example and does not yet handle aliases, annotations, deep reflection, duplicate names, or per-getter errors. In a real tool, the rules below should be additionally configured before processing user data.

## 6. Filtering, naming, and conflict-resolution policies

### 6.1. Intentional whitelisting

You should not export every discovered field/getter by default. For example, an entity might have `getPasswordHash()`, `getApiToken()`, or `getInternalAuditTrail()`. Even if a method is public, that does not automatically make the information appropriate for an API or export file.

A safer policy:

- Have a property-name allowlist or a tool-specific annotation (such as `@Exportable`) evaluated within valid declaration scopes and placement targets.
- Have a denylist for sensitive data like secrets, though **an allowlist is the primary control mechanism** when data crosses a trust boundary.
- If a property is not on the allowlist, skip it **before invoking the getter**, avoiding unnecessary code execution.
- Define whether annotations are placed on fields, getters, record components, or parameters, and how inheritance/overrides are handled. Do not assume an annotation on a field automatically transfers to its getter or vice versa.

Example pseudocode for a read policy (not a built-in JDK API):

```java
// Algorithm illustration; selected and policy are defined by your tool.
for (MemberDescriptor member : selected) {
    if (!policy.isAllowed(member.externalName())) continue;
    if (!member.readable()) continue;
    // Only at this point is the accessor executed and added to the result.
}
```

### 6.2. Duplicate names and source precedence

Suppose a class has `private String name`, `getName()`, and a record component `name`. If multiple sources are scanned, these three items might represent the same logical property or have different semantics (e.g., a getter returning a computed value). If merged arbitrarily with `Map.put`, traversal order decides which value wins, easily causing hard-to-reproduce bugs.

Lock down one of two contracts:

1. **Only one source per class** per policy, as in `AccessPolicyDemo`: avoids most conflicts.
2. **Combine multiple sources with clear precedence**, e.g. explicit annotation takes priority, then record component, JavaBeans property, public field. If two distinct candidates appear at the same level or aliases collide, report `AMBIGUOUS_PROPERTY` with the name, declaring class, and source.

Do not rely on `getDeclaredMethods()` or `getDeclaredFields()` to determine precedence. Check field hiding between parent/child classes, getter overrides, and inheritance to avoid picking an obsolete member. If aliases are supported, check for duplicates **after aliases have been applied**, not just on the original Java identifiers.

### 6.3. Deterministic ordering

Serializers or schema generators may require deterministic output so snapshot tests, hashes, and diffs do not change randomly. Specify an ordering rule: alphabetical by external name; or by explicit `order`; or by record component declaration order in the header when schema compatibility is needed. The example sorts alphabetically for everything for consistency.

## 7. Read policy differs from write policy

A readable property is not necessarily writable:

| Source | Read | Write | Notes |
| --- | --- | --- | --- |
| Public non-final field | Usually possible via `Field.get` | Possible via `Field.set` if permissions and types match | Does not imply atomicity/thread safety |
| Private field | Depends on reflection/module permissions | Depends on permissions, may be restricted | Do not deep-reflect just for convenience |
| JavaBeans getter-only | Yes | No setter in descriptor | Getter may compute values or have side effects |
| JavaBeans setter-only | No getter | Has matching setter | Do not guess the current value |
| Record component | Has accessor | Cannot be written as a mutable property | Construct a new record via constructor when values must change |
| Static field | Not part of instance state under typical policy | Needs separate policy | Should be excluded from instance serializers |

For JavaBeans, check `getReadMethod()` and `getWriteMethod()` separately. For fields, inspect `Modifier.isFinal` and access rights. A record has `private final` component fields, and more importantly, the public record API represents a value structure that does not support mutating components after creation; mutation of referenced objects inside can still occur (shallow immutability).

**Type validation** must follow the contract of the assignment API: `Field.set` and `Method.invoke` have their own type/primitive conversion rules; do not automatically convert the string `"42"` to `int` without a defined conversion policy. When binding user data, validation, coercion, and access policy are separate decisions.

## 8. Access rights and runtime errors

### Java Platform Module System limitations

Finding `getDeclaredField("secret")` does not prove that the field can be read. `setAccessible(true)` is not always valid under strong encapsulation; it can throw `InaccessibleObjectException`. `trySetAccessible()` can return false when disallowed. `MethodHandles.privateLookupIn` also requires the caller to have appropriate privileges and module conditions; it is not a bypass around Java access control.

For production tools, prefer explicit public contracts/annotations, and open specific packages only if strictly necessary and permitted by the module owner. Do not scatter `--add-opens ALL-UNNAMED` broadly just to bypass data-reading restrictions.

### Handling getter, field, and record accessor errors

A getter may throw exceptions due to business logic, side effects, or I/O. `Method.invoke` wraps exceptions from target code in `InvocationTargetException`; `Field.get` can throw `IllegalAccessException` or `IllegalArgumentException` when the receiver is invalid. `RecordComponent.getAccessor().invoke` is also a `Method` invocation, so exceptions must be handled similarly. Never swallow exceptions and write an indistinguishable `null` value.

Example result design (fragment):

```java
record ReadIssue(
        String propertyName,
        String sourceKind,
        String errorCode,
        String message
) {}
```

Error policies can be fail-fast for transactional systems, or collect-errors for internal object inspectors. If returning partial results, clearly mark which item failed and do not treat it as an actual `null` value. Avoid logging full values/stack traces to API responses because getters may touch personal data or secrets.

## 9. Performance, stability, and extensibility

The expensive part of a reflection tool is typically discovery, normalization, and permission checks, so **metadata descriptors** can be cached by `Class<?>` and policy version; do not cache per-instance values under the same key since values vary by object.

- **Caching by class/policy**: `ClassValue<T>` is worth considering when you want caching tied to the lifecycle of `Class`; for `Introspector`, the JDK already has its own `BeanInfo` cache. If the tool uses dynamic classloaders or hot reload, evaluate the risk of retaining classloader references.
- **Caching decisions**: store filtered members and normalized order to avoid repeating the work per object; invalidate when policy or annotation mappings change.
- **MethodHandle**: worth considering when invocations are frequent enough and signatures are known; switching from `Method` to a handle does not replace the discovery policy. Do not claim `MethodHandle` is always faster than `Method.invoke`, because JDK version, warm-up, and workload affect results.
- **Thread-safety**: cache immutable metadata using appropriate concurrent structures; do not mix metadata caching with synchronizing mutable bean values.
- **Cycle detection**: if a serializer traverses an object graph, separate the property selection policy from cycle handling and depth limits. Not every property is allowed to be recursively expanded.

Write tests covering cases such as getter-only, setter-only, record, inherited getter, field hiding, private field, static/synthetic, annotation allowlist, duplicate alias, getter throwing, JPMS, and classloader. Deterministic ordering makes results easy to compare across test runs.

## 10. Decision checklist and common mistakes

Before finalizing your tool's policy, answer:

1. What goal does this tool serve: serialization, binding, diagnostics, schema generation, or test introspection?
2. Is the default source public fields, JavaBeans properties, record components, or separately registered accessors?
3. Who is allowed to participate: all public members or only an approved allowlist?
4. Is private access allowed, and does the owning module permit it?
5. How are static, synthetic, bridge, transient, final, and inherited members handled?
6. How are getter-only/setter-only, aliases, nulls, duplicate names, and exceptions represented?
7. Does output require deterministic ordering and schema backward compatibility?
8. Is metadata cached by class/policy and is classloader unload/reload handled?

Mistakes to avoid:

- **"If there is a field, there is a property"**: JavaBeans may have no backing field; getters may compute values.
- **"Record accessors are always named `getX`"**: actual default accessors match the component name, such as `code()`.
- **"Any public method with no parameters is safe to call"**: getters can have side effects, and many methods are not accessors.
- **"Scanning `getDeclaredFields` captures the entire inheritance hierarchy"**: it only retrieves directly declared fields.
- **"`setAccessible(true)` always unlocks access"**: access checks and module boundaries still apply.
- **"Using both fields and getters is always more complete"**: can produce duplicates, internal data, and conflicting values; requires precedence and policy.
- **"Having a getter guarantees writability"**: the write contract is separate; record components are inherently not mutable properties.
- **"Reflection output has a fixed order"**: you must define/sort explicitly if stability is needed.

Self-check:

- A class has `private int age` and `getAge()`: do both `PUBLIC_FIELD` and `BEAN_PROPERTY` select `age`? **No**; a public-field policy does not select private fields, while a bean policy can select the getter.
- For `record Point(int x, int y)`, does using default `Introspector` alone guarantee retrieving `x`/`y`? **No**; use `getRecordComponents()` when intentionally supporting records.
- A getter `getSecret()` is public; should secrets be exported automatically? **No**; a public API does not automatically mean it should be exposed externally.
- When two accessors share the alias `userId`, is picking the later-visited one safe? **No**; deterministic precedence or collision reporting is required.
- An inspector needs to display 100 beans repeatedly: which step should be optimized first? **Cache metadata/selection policy**, then measure execution performance if actually needed.

Original references: [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html), [`Introspector`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html), [`PropertyDescriptor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyDescriptor.html), [`RecordComponent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html), and [JavaBeans Specification](https://www.oracle.com/java/technologies/javase/javabeans-spec.html).