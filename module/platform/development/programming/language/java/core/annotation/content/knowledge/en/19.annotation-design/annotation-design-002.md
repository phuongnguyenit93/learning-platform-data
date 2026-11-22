# Designing Names That Accurately Convey Metadata Meaning in Java Annotations

## 1. Why Is an Annotation Name Part of the Design Contract?

Annotations in Java are **metadata** attached to declarations or type uses. When a reader sees `@MaintainedBy(team = "catalog")` on a class, they expect the annotation to answer the question **“who maintains this component?”**. When they encounter `@RequiresPermission("catalog.read")` on a method, they expect the annotation to indicate **“what permission does this method require?”**.

An annotation name does not merely exist so the code can compile. That name is part of the API that helps readers, inspection tools, frameworks, and project maintainers interpret the **declared meaning**. An ambiguous name can lead to incorrect processing logic even when both the Java structure and the element types are valid.

Example:

~~~java
@MaintainedBy(team = "catalog")
class CatalogRepository {}

@RequiresPermission("catalog.read")
void listCatalog() {}
~~~

This is **code illustrating naming**, not a standalone program. The two annotations have two different kinds of meaning:

- `MaintainedBy` describes an **existing property/relationship**: which team maintains the component.
- `RequiresPermission` describes a **desired condition/policy** for performing an action.

Both are merely **metadata**. Java does not automatically manage class ownership teams or block method access. Those behaviors require tools, frameworks, or application code that **consume the annotation**. A good name must help users recognize this distinction, rather than implying that merely attaching the annotation causes the JVM to enforce the policy.

**Lesson goal:** design annotation type names, internal element names, package names, and contract semantics so that readers do not have to guess what the metadata says about **which entity, which property, which condition, and how far its effect extends**.

## 2. Names Must Describe the Fact or Intent of Metadata, Not Promise Nonexistent Behavior

Compare these hypothetical names:

| Name | How readers typically interpret it | Design assessment |
| --- | --- | --- |
| `@MaintainedBy(team = "search")` | The component is maintained by the `search` team | Specific about the ownership/maintenance relationship |
| `@OwnedBy("search")` | The team or individual owning the component | Concise if “owner” is already defined in the project |
| `@RequiresPermission("orders.write")` | Calls require this permission | Good for declaring a policy; must have an enforcer |
| `@Audited` | The component is audit-tracked | Easy to understand at the intent level, but you need to know whether tools record audit logs or only mark it |
| `@AuditEvent("DELETE_ORDER")` | Metadata indicates an audit event | Clearer when tools read it as an event description |
| `@Info("...")` | Arbitrary information | Too broad if the API is used for a specific domain purpose |
| `@Data` | “Data” of an unknown kind | Very vague outside a framework with a known contract |
| `@RunFast` | The JVM will make the code run fast | Prone to creating false expectations if it is only a label without enforcement |
| `@Safe` | The component is always safe | Overly broad assertion, hard to verify, and lacks scope |
| `@Validated` | Already validated/checked | Appropriate only when truly describing a checked state, not suitable for requesting validation |
| `@RequiresValidation` | Needs to be checked | More suitable for a requirement not yet performed |

A question to ask before choosing a name: **is the annotation “describing a fact”, “requiring a policy”, “marking a process”, or “passing configuration to a tool”?** These categories require different vocabularies.

For example, if a tool will verify that a method has been reviewed, `@ReviewedBy("qa")` should only be used when the metadata represents a completed review result; if it is a request assigned to the QA team to carry out, `@ReviewRequired` or `@ReviewOwner("qa")` is more honest.

An annotation `@Immutable` carries a very strong meaning: readers may understand that the object cannot be modified. If the annotation is only attached manually by the development team without a proof/verification mechanism, the documentation must clearly state that this is an **author-declared design commitment**, not a property automatically enforced by Java.

## 3. Use Consistent Parts of Speech and Naming Structures

A Java annotation type is a special kind of interface, so it normally follows **UpperCamelCase** like Java type names. Java does not require an `Annotation` suffix.

You can choose a structure according to the kind of meaning:

| Metadata category | Suggested naming style | Examples |
| --- | --- | --- |
| Declared property/relationship | Noun, adjective, or participle phrase | `@Deprecated`, `@Documented`, `@MaintainedBy` |
| Precondition before execution | `Requires...`, `AllowedFor...`, `AccessPolicy...` | `@RequiresPermission`, `@RequiresReview` |
| Processing mode or option | Noun indicating configuration/policy | `@RetryPolicy`, `@CachePolicy` |
| Role of a component in the system | Noun or compound noun | `@Endpoint`, `@Handler` |
| Compile-time code generation/checking request | `Generate...`, `Check...`, `Enforce...` | `@GenerateMapper`, `@CheckNaming` |
| Data identifying source or owner | `...By`, `...Owner`, `...Source` | `@CreatedBy`, `@ModuleOwner` |

These are **semantic naming recommendations**, not a list of keywords required by Java. Public annotations that already have their own contracts—for example `@Override`, `@FunctionalInterface`, or library annotations—should follow their own contracts rather than being renamed to fit a mold.

### 3.1. Do Not Turn Every Name into a Verb Requesting JVM Execution

`@Validate`, `@Encrypt`, and `@Delete` sound like commands executed immediately. When an annotation merely describes metadata for a tool that will run later, names like `@RequiresValidation`, `@EncryptionPolicy`, or `@DeletionRule` usually distinguish **declared intent** from **implemented behavior**.

However, a framework with a clear definition of `@Transactional` or `@Cacheable` may use behavior-describing names because its documentation affirms that the framework will process these annotations when the proper conditions are met. **A name is not wrong in itself**; what is wrong is when the meaning the name promises does not match the actual mechanism or is not explained.

### 3.2. Distinguish Between State and Requirement

Example:

~~~java
@ReviewedBy("alice")
class ReleasedChange {}

@ReviewRequired
class PendingChange {}
~~~

The two declarations above carry **different meanings**: one states “who reviewed it”, while the other states “needs review”. If a project uses `@Reviewed` for both, readers or processors cannot tell whether the state is complete.

Similarly, `@Encrypted` describes the state of encrypted data; `@EncryptWith("AES-GCM")` sounds like a directive telling a tool to perform encryption. If the tool does not enforce the request, the name must be properly interpreted as a **metadata directive**, not a guaranteed execution result.

## 4. Element Names Inside an Annotation Must Also Clearly Convey Meaning

An annotation type contains **elements** in the form of parameterless methods. A design example:

~~~java
@interface RetryPolicy {
    int maxAttempts() default 3;
    long delayMillis() default 200;
}
~~~

- `maxAttempts` refers to the **maximum total number of attempts**; different from `maxRetries` (the number of *retries* after the first attempt).
- `delayMillis` includes the **millisecond unit**. If written only as `delay`, users have to look up the documentation to know whether it is seconds, milliseconds, or nanoseconds.
- Default values must be compatible with the element's meaning: `maxAttempts() default 3` and `delayMillis() default 200` do not imply that retry is automatically enabled by Java.
- The `int` and `long` types ensure the data has numeric types, but the compiler does not automatically validate business constraints such as `maxAttempts >= 1`. The tool using the metadata must check it if that is part of the contract.

Good element names generally follow **lowerCamelCase**, use nouns/noun phrases describing the value, include units when meaningful, and avoid overly broad names such as `data()`, `name()`, or `flag()` if a more specific option exists.

### 4.1. When to Use value()?

Java allows a shorthand syntax when an element is named exactly `value`:

~~~java
@interface RequiresPermission {
    String value();
}

@RequiresPermission("catalog.read")
class CatalogReader {}
~~~

`@RequiresPermission("catalog.read")` is shorthand for `@RequiresPermission(value = "catalog.read")`. This syntax is appropriate when the annotation has **one obvious primary value** and the annotation name is clear enough to understand what that value is.

You should not overuse `value()` if the annotation carries multiple metadata fields or the primary value could easily cause confusion. For example:

~~~java
@interface MaintainedBy {
    String team();
}

@MaintainedBy(team = "catalog")
class CatalogService {}
~~~

`team = "catalog"` is clearer than `value = "catalog"` when other concepts might exist, such as a person's name, a business unit, or an owning repository.

If there are multiple elements with closely related meanings, use transparent names:

~~~java
@interface ApiLifecycle {
    String introducedIn();
    String deprecatedSince() default "";
}
~~~

`introducedIn` and `deprecatedSince` avoid ambiguity better than two elements named `from`/`until` if the system needs to manage API lifecycles. The empty string here is simply a **data convention that must be documented**; Java annotations do not accept `null` as a default value.

### 4.2. Name Booleans to Reflect a Verifiable Statement

Example:

~~~java
@interface ExportPolicy {
    boolean publicApi() default false;
    boolean requiresApproval() default true;
}
~~~

These boolean names can be read as affirmative statements and clearly express the `true`/`false` values. A name like `flag()` or `state()` does not indicate what `true` means.

A boolean `secure()` is also usually too broad: “secure” with respect to transport, authentication, authorization, encryption, or data? Split it into specific conditions if business requirements permit.

### 4.3. Names and Types Must Be Consistent with Meaning

If the metadata represents an access level with a finite set of choices, using an enum instead of a free-form string can be clearer and safer:

~~~java
enum Exposure { INTERNAL, PARTNER, PUBLIC }

@interface ApiExposure {
    Exposure level() default Exposure.INTERNAL;
}
~~~

If the metadata is a list of classification tags, `String[] tags() default {}` properly expresses an array type; if it is a single tag, `String tag()` is more reasonable. Do not name it `tags()` while stating in the documentation that only one value is allowed without explaining why.

An annotation element may only use types permitted by Java: primitives, `String`, an appropriate `Class`, enums, annotation types, and **one-dimensional** arrays of those types. You cannot arbitrarily use `List<String>` or `Map<String, String>` as an element type; name and structure design must stay within this constraint.

## 5. Semantic Scope Must Match @Target

The annotation name conveys a message, but **`@Target` is what governs the valid locations to attach it**. The design must be consistent between the two.

| Intended name/meaning | Typically appropriate target | Why |
| --- | --- | --- |
| `@MaintainedBy` for an entire class | `ElementType.TYPE` | Describes the owner of the type declaration |
| `@RequiresPermission` for a method call | `ElementType.METHOD` | Policy attached to the operation |
| `@ColumnName` for a field | `ElementType.FIELD` | Describes field mapping |
| `@ParameterAlias` for a parameter | `ElementType.PARAMETER` | Describes each parameter declaration |
| `@NonNullValue` for a type use | `ElementType.TYPE_USE` | Metadata belongs to type-use; read via the corresponding API |
| `@ModuleOwner` for a JPMS module | `ElementType.MODULE` | Describes the entire module in `module-info.java` |

This table is a design guideline; an annotation can have **multiple targets** when the same semantics apply at multiple locations. However, do not broaden targets just so the annotation “can be used everywhere”. If `@RequiresPermission` is placed on both a class and a method, clearly define how the two levels combine: is the class policy a default? Does the method policy supplement or override it? Java provides no automatic business merging rules.

If `@Target` is not declared, an annotation can be used across many **declaration contexts** under Java rules; that does **not** mean it automatically supports all `TYPE_USE` positions. For metadata with a precise meaning, targets should be declared explicitly so the compiler prevents misplacement.

A confusing design is `@ParameterFormat` having only a `TYPE` target while the documentation requires using it on parameters. The compiler will reject it; renaming alone does not solve it—the target contract must be fixed.

## 6. Retention and the Meaning Promised by the Name

`@Retention` determines which stage an annotation survives to. The meaning of the name should match **where the metadata is actually consumed**.

| Retention | Use when | What to remember |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Compiler, annotation processor, compile-time lint/checks | Annotation usages are not stored in the target class file |
| `RetentionPolicy.CLASS` | Tools processing class files after compilation | Stored in bytecode, but invisible to standard Java reflection |
| `RetentionPolicy.RUNTIME` | Frameworks/reflection must read metadata while the program runs | Retrievable via the corresponding `AnnotatedElement`, without automatically triggering behavior |

For example, if `@RequiresPermission` is used by a runtime interceptor to block operations, the annotation should have `@Retention(RUNTIME)`. If `@GenerateAdapter` is only for an annotation processor to generate source in `javac`, `@Retention(SOURCE)` is usually sufficient.

A name like `@RuntimeValidated` that has `SOURCE` retention and no step generating a runtime validator will set false expectations. Conversely, merely changing retention from `SOURCE` to `RUNTIME` does not make validation execute automatically.

**The name–target–retention–consumer relationship forms a coherent contract.** A name cannot be evaluated independently of the mechanism reading the annotation.

## 7. Complete Java 17+ Example: Metadata with Clear Meaning and an Explicit Consumer

The example includes two annotations:

- `@MaintainedBy(team = ...)` describes **the team maintaining a class** and does not alter the class's behavior.
- `@RequiresPermission("...")` describes **the permission required to invoke a method**. The demo program actively reads the metadata and invokes the method only if the granted permission matches the requirement.

Save **the entire snippet below** to the file `MetadataNamingDemo.java`:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface MaintainedBy {
    String team();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequiresPermission {
    String value();
}

@MaintainedBy(team = "catalog")
final class CatalogApi {
    @RequiresPermission("catalog.read")
    public String list() {
        return "books";
    }

    @RequiresPermission("catalog.write")
    public String update() {
        return "updated";
    }
}

public class MetadataNamingDemo {
    private static void attempt(String methodName, String grantedPermission)
            throws ReflectiveOperationException {
        Method method = CatalogApi.class.getDeclaredMethod(methodName);
        RequiresPermission requirement =
                method.getAnnotation(RequiresPermission.class);
        boolean allowed = requirement != null
                && grantedPermission.equals(requirement.value());

        System.out.println(methodName + ": " + (allowed ? "allowed" : "denied"));
        if (allowed) {
            System.out.println(method.invoke(new CatalogApi()));
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MaintainedBy owner = CatalogApi.class.getAnnotation(MaintainedBy.class);
        System.out.println("owner=" + owner.team());
        attempt("list", "catalog.read");
        attempt("update", "catalog.read");
    }
}
~~~

Compile and run from the directory containing the file, with JDK 17 or later:

~~~bash
javac --release 17 MetadataNamingDemo.java
java MetadataNamingDemo
~~~

**Exact stdout:**

~~~text
owner=catalog
list: allowed
books
update: denied
~~~

The output was verified by compiling with `javac --release 17` and running the program on a Java 17-compatible JDK.

### 7.1. Explaining the Name Design Through the Output

1. `CatalogApi` is annotated with `@MaintainedBy(team = "catalog")`. Reflection reads the annotation on the **class** and prints `owner=catalog`. Java does not automatically notify this team or check whether the owner is valid.
2. The `list()` method is annotated with `@RequiresPermission("catalog.read")`. The `attempt` code obtains the `Method` and calls `getAnnotation(RequiresPermission.class)`. Because the granted permission is `catalog.read`, the comparison succeeds and the program invokes the method, printing `books`.
3. The `update()` method requires `catalog.write`, whereas the granted permission is only `catalog.read`; the `attempt` method **does not invoke** that method and prints `update: denied`.
4. The denial occurs because **the Java logic in `attempt` explicitly reads and processes the metadata**, not because `@RequiresPermission` can block a direct call on its own. If a user calls `new CatalogApi().update()` directly, the annotation does not intervene automatically.
5. `@Target(TYPE)` and `@Target(METHOD)` prevent using these two annotations in locations that are inappropriate according to the design.
6. `@Retention(RUNTIME)` is a necessary condition for reflection to read the metadata. Using `SOURCE` for `RequiresPermission` in the demo would make `getAnnotation(...)` unable to see the annotation at runtime.

**Security note:** this example is intended to demonstrate **annotation naming semantics and an explicit consumption step**, **not a production authorization mechanism**. Real-world authorization requires user identity, authentication, a trusted permission source, a mechanism covering all call paths, and a deny-by-default policy. Do not treat annotations alone as a firewall protecting methods. The demo denies access when the annotation is absent (`requirement == null`) to illustrate a specific policy; a real system must clearly specify how unannotated methods are handled.

## 8. Naming Appropriate to the Conceptual Level

### 8.1. Property-Indicating Names Must Not Mislead About Guarantees

`@ThreadSafe` can be a design commitment that the type is designated by its author as thread-safe; attaching the annotation **does not add synchronization to the class**. `@NotNull` or `@NonNull` can be a convention for a static/runtime checker in a framework; core Java does not automatically block null assignments simply because the annotation is present.

If a team does not yet have any system consuming the annotation, clearly document whether it is meant for **documentation** or for a **planned tool**. You should not use a strong affirmative name like `@Validated` if it is merely a “should be validated” label.

### 8.2. Names Need to Identify the Semantic Subject

An annotation named `@Sensitive` on a field easily makes readers ask: sensitive with respect to security, privacy, or priority level? In the personal data domain, `@ContainsPersonalData` may express the meaning more accurately if the contract is to mark personal data. If the goal is to require log masking, `@RedactInLogs` (accompanied by a processor) is a different policy.

Do not use the same name `@Sensitive` for all of “data containing personal information”, “requires encryption”, and “must not be logged” and leave every consumer to interpret it differently. Separate concepts whose lifecycles and processing tools differ.

### 8.3. Behavior-Indicating Names Must Clarify Who Executes Them

`@Cacheable` is commonly used by frameworks to decide whether to cache results. However, in an application without a caching interceptor, an annotation with that name is purely metadata. When designing your API, the documentation should clearly state **which processor/interceptor/tool reads it**, when it is processed, which targets are supported, and when the annotation may be ignored.

A good name makes writing documentation shorter; **it does not replace documentation of execution behavior**.

## 9. Packages, Public Names, and Discoverability

An annotation type is a Java type, so it follows normal naming and package rules.

- **Type names:** use `UpperCamelCase`; for example `RequiresPermission`, `MaintainedBy`, `ApiExposure`. The name is not required to start with `@` in the declaration: the `@` sign only appears when applying the annotation; the declaration uses `@interface`.
- **Element names:** use `lowerCamelCase`, for example `team()`, `expiresAt()`, `maxAttempts()`.
- **Packages:** typically lowercase and hierarchically organized by owning domain, for example `com.example.catalog.annotation` or `com.example.security.policy`. Avoid an overly broad `com.example.annotations` when there are many independent kinds of metadata, if the project structure is large enough to split them sensibly.
- **Discoverable names:** distinct enough from common annotations in other frameworks. Two annotations `com.alpha.Policy` and `com.beta.Policy` sharing the same simple name but having different contracts will cause confusion on import; names like `AccessPolicy` and `RetentionPolicy` express their domains more clearly.
- **Public API:** place the annotation in a package accessible from the appropriate modules/consumers, publish JavaDoc, and consider long-term name/element compatibility.

With JPMS, an annotation type declared `public` is not necessarily importable by another module if its containing module **does not export the package** or the consumer **cannot read the module**. Accessibility of metadata names is also part of the API, and `@Target` and `@Retention` do not substitute for `requires`/`exports`.

### 9.1. Should You Add the Annotation Suffix?

No Java rule requires `@AuditAnnotation` or `@PermissionAnnotation`. A name like `@RequiresPermission` usually makes its metadata role self-evident when placed before a method, whereas an `Annotation` suffix can lengthen the name without adding semantics.

If a project already has a public class `Policy` and needs to avoid colliding with an annotation type of the same name, choose a specifically meaningful name such as `AccessPolicy` or `PolicyMarker` based on the actual contract, rather than automatically appending the `Annotation` suffix across the entire API.

## 10. Naming Repeatable and Container Annotations

A **repeatable** annotation can be attached multiple times to a single declaration. The component annotation's name should represent **a single unit of metadata**, while the container typically uses an appropriate collective name.

Illustrative example (without `main`):

~~~java
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Repeatable(RequiredPermissions.class)
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequiresPermission {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface RequiredPermissions {
    RequiresPermission[] value();
}

class AdminApi {
    @RequiresPermission("orders.read")
    @RequiresPermission("orders.write")
    public void reconcile() {}
}
~~~

`RequiresPermission` represents a single permission requirement; `RequiredPermissions` is the container holding multiple elements. Java requires the container's `value()` structure to be an array of the component annotation. Choose a container name so readers understand it is a **collection**, though the **combination semantics** must still be defined by the tool.

For example, do two `@RequiresPermission` annotations mean **all permissions are required** or **only one permission is required**? `@Repeatable` does not automatically determine AND/OR logic. If the product needs a policy requiring only one of several permissions, you can design separate metadata such as `@RequiresAnyPermission` with an array element; if all permissions are wanted, `@RequiresAllPermissions` makes the meaning clearer. The two choices have different implementation requirements.

**Naming lesson:** simply pluralizing `RequiredPermissions` is not enough to answer how the processor combines conditions. Higher-level names and documentation must clearly state the **combination rule** if a tool consumes the metadata.

## 11. Designing Defaults and Valid Values Aligned with the Name

Suppose:

~~~java
@interface RateLimit {
    int requestsPerMinute() default 60;
    boolean enabled() default true;
}
~~~

This snippet only illustrates the declaration and has no `main`.

- `requestsPerMinute` includes the **time unit**, helping avoid misinterpreting 60 as per second.
- `enabled` is a configuration state: it defaults to `true`. However, no logic counts requests automatically unless the application implements it.
- If the goal is to limit total requests in a dynamic window, the term `PerMinute` may be too rigid; in that case, design dedicated data types/elements for the unit and time window.
- Use `default` when there is a meaningful common value. If **no safe default exists** for a property (for example, a required owner or permission), leave the element **without a `default`** so the compiler forces the annotation site to supply it.
- Constraints are not checked merely because of the name: `@RateLimit(requestsPerMinute = -5)` is still a valid `int` value; the consuming tool must validate it according to business rules.

Do not use sentinel strings like `"none"` or `""` if their meaning could be confused with an actual value. Annotations do not support the `null` literal as an element/default value. If a “none” state is needed, design a sentinel/enum with a clear contract.

## 12. Annotation Names Must Be Resilient to Change and API-Compatible

When an annotation type is part of a public API, renaming `@Owner` to `@MaintainedBy` is not merely changing wording. Every source file importing or using the annotation, or any processor scanning for the old name, may need to be updated; metadata in already-compiled class files may still reference the old type. Therefore:

1. **Choose sufficiently stable semantics before release.** Do not name things after a project nickname or a short-term implementation detail if the contract will be reused.
2. **Avoid silently expanding an old name into a new meaning.** If `@ReviewedBy` previously meant a completed review, do not modify the consumer to interpret it as a review to be done without a transition policy.
3. **Renaming or changing elements can break source compatibility.** Consumers writing `@MaintainedBy(team = "...")` are incompatible with a new definition that only has `ownerTeam()`.
4. **Adding a new required element** can prevent existing usages from recompiling. If you add an element with a default value, consider the behavioral impact on existing usages that do not pass a value.
5. **Changing a default can alter the observed value** for usages that do not specify it explicitly, because defaults are tied to the annotation type definition and applied when reading metadata. This is a contract change even though the source code does not change.
6. **Changing `@Target` or `@Retention`** alters where the annotation is valid or how processors/reflection see the metadata; it is not just a name change.
7. When introducing a new name, have a migration plan and test with the relevant compiler, annotation processors, runtime frameworks, or public documentation.

Some annotation names already carry well-known meanings in Java, such as `@Override` (compile-time override checking) or `@Deprecated` (marking an API as discouraged from use). When designing your own metadata, you should **learn from how these names clearly express their role**, and avoid redefining the same name with a completely different meaning in your own package if doing so would cause confusion.

## 13. Annotation Documentation Quality Is Part of the Name

Even the clearest name still needs JavaDoc when the annotation carries business rules. Example:

~~~java
/**
 * Declares the permission required to invoke the annotated method.
 *
 * <p>This annotation has no effect unless an authorization
 * component explicitly reads and enforces it.
 */
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface RequiresPermission {
    /** Permission identifier understood by the authorization component. */
    String value();
}
~~~

This is an **API illustration snippet**. To compile it standalone, you need the imports `java.lang.annotation.Retention`, `RetentionPolicy`, `Target`, and `ElementType`, and you must place the public annotation in a matching `RequiresPermission.java` file.

A good contract should answer:

- **Who/what** does the annotation describe and at **which level** does it apply?
- Which elements are required, and what are the data type and unit of each element?
- Which values are valid, and what do their defaults mean?
- Is the metadata read at **compile time, class file level, or runtime**?
- Which component/processor/framework consumes it? If that component is not enabled, what effect does the annotation have?
- If multiple annotations of the same or different types appear, what are the ordering and combination rules?
- Is metadata inherited from a superclass? `@Inherited` only has special meaning for certain annotation lookups **on classes**, and does not automatically make method/field annotations inherited.
- Does the metadata have any security or performance requirements? Does it contain sensitive data?

Do not put real passwords, tokens, or secrets into annotation elements under the excuse that they are “only metadata”; with `CLASS` or `RUNTIME` retention, values can persist in bytecode and be observed by analysis tools.

## 14. Counterexamples: Improving Names Based on Semantics

### Scenario A — Processing Limits

**Ambiguous:**

~~~java
@Fast(5)
void fetch() {}
~~~

Does the number `5` mean milliseconds, priority level, thread count, or retry count? Is `Fast` a promise of speed or a request to apply a policy?

**Clearer:**

~~~java
@RetryPolicy(maxAttempts = 5, delayMillis = 200)
void fetch() {}
~~~

The second example describes a **retry policy** and units without promising that the method will always run fast. This is illustrative code and will only compile if the corresponding annotation types are declared with appropriate targets.

### Scenario B — Logging Rules

**Ambiguous:**

~~~java
@Sensitive
String secret;
~~~

If the goal is not to write the field's value to logs, you can use `@RedactInLogs` accompanied by documentation stating that a specific logger/serializer must consume the annotation. However, if the goal is to identify personal data, the name `@ContainsPersonalData` expresses a different **data property**. There is no single name that is right for both meanings.

### Scenario C — Review Status

**Ambiguous:**

~~~java
@Review
class PaymentChange {}
~~~

If the annotation states that the review process is complete, `@ReviewedBy(team = "risk")` is more specific. If the annotation requests a review, `@RequiresReview(team = "risk")` is more specific. The two names lead to two different kinds of checks, avoiding confusion between a **completed event** and a **policy to be fulfilled**.

### Scenario D — Access Permissions

**Ambiguous:**

~~~java
@Security("admin")
void deleteOrder() {}
~~~

The name `Security` does not make clear whether the value `admin` is a username, role, permission, group, or protection level. If the contract requires a role, use `@RequiresRole("admin")`; if it requires a specific permission, use `@RequiresPermission("orders.delete")`. These are two different authorization models; choose the name according to the actual data being verified.

## 15. Annotation Naming Checklist in Code Review

Before releasing a new annotation, evaluate:

1. **One-sentence definition:** can you clearly describe the annotation in a single sentence without using its own name to explain it?
2. **Fact or requirement:** does the name accurately indicate whether the annotation records **state**, **policy**, **capability**, or **configuration input**?
3. **No overpromising:** might readers mistakenly think Java automatically executes a behavior that has no implementation?
4. **Semantically valid target:** does the annotation type declare `@Target` accurately for class, method, field, parameter, type-use, package, or module?
5. **Consumer-aligned retention:** can the compile-time checker/bytecode tool/runtime framework read the annotation under its `@Retention`?
6. **Clear elements:** do element names use lowerCamelCase, specify units, use clear propositions for booleans, and provide justified default values?
7. **Is value() warranted:** does the annotation have only one obvious central value, or does it need an explicit element name?
8. **Domain-appropriate package:** is the annotation placed in a package owned by the right domain, easy to import, and free of conflicts/ambiguity with other annotations?
9. **Inheritance and repetition:** is `@Inherited` or `@Repeatable` needed, and if so, have the inheritance/combination semantics been defined?
10. **Stability:** do public consumers depend on the name/type/elements; if renamed, how will migration be handled?
11. **Verifiability:** which elements can be type-checked by the compiler, and which require a framework/processor to verify business rules?
12. **Demonstrating examples:** are there both valid usage examples and a case where the annotation is not consumed to confirm what actually happens?

**Conclusion:** A good annotation name must express the **meaning of the metadata** rather than merely looking like a method call. Choose names according to the **fact, relationship, condition, or configuration** that the annotation declares; name elements with clear units and roles; and keep `@Target`, `@Retention`, the package, and the processor consistent with that promise. In Java, **metadata does not generate behavior on its own**: accurate names help humans and tools understand the contract, while the consumption logic determines what the system actually does.
