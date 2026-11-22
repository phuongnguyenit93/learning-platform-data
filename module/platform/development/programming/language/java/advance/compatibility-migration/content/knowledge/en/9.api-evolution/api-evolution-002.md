# Adding a Replacement API Before Discontinuing Support for the Old API

When developing a Java library or a shared platform, the need to change APIs is unavoidable. Perhaps an old method returns a value that poorly expresses an error state, an interface no longer reflects the business logic, or an API relies on a library unsupported on a new JDK. Directly changing signatures or deleting the old API can prevent dependent applications from compiling, linking at runtime, or preserving their behavior.

An often effective API evolution strategy is to **introduce the replacement API first**, maintain the old API during a transition period, provide upgrade guidance, and discontinue support for the old API only after evaluating the impact. This approach allows vendors and consumers to migrate at different paces, while preserving the ability to release bug fixes during migration.

This lesson focuses on how to design replacement APIs, manage deprecation, and migrate consumers in the context of **Java Advance Compatibility Migration**. The principles can also apply to framework APIs, plugins, and external protocols, but the contract of each API type must be evaluated separately.

## 1. Why Add a Replacement API First?

Suppose version 1 of a library has the method:

~~~java
Customer findCustomer(String customerId)
        throws CustomerNotFoundException;
~~~

Application A uses this method in the admin UI, application B uses it in a batch job, and application C is deployed only once every few months. The vendor wants to introduce a new API returning Optional to represent the customer-not-found situation.

If the vendor directly replaces the old method with:

~~~java
Optional<Customer> findById(String customerId);
~~~

then source code calling findCustomer will no longer compile. Pre-compiled consumers may also encounter NoSuchMethodError when running with the new library version, because the old method has disappeared. In addition, users have to change how they handle the customer-not-found situation.

Instead, the vendor can publish a version containing **both methods**:

~~~java
Customer findCustomer(String customerId)
        throws CustomerNotFoundException;

Optional<Customer> findById(String customerId);
~~~

Existing consumers continue using the current contract. New consumers and upgrading consumers can choose findById. During the transition period, the library has the opportunity to collect feedback, test compatibility, and resolve cases that the new API does not yet satisfy.

This strategy is often called **additive evolution** or part of the **expand–migrate–contract** process:

1. **Expand:** add the new API while keeping the old API working.
2. **Migrate:** guide and gradually move consumers to the new API.
3. **Contract:** after meeting the support policy, remove the old API or end support commitments for it according to a published version.

The expand phase does not automatically guarantee full compatibility. Adding a method to an interface, adding an overload, or changing dependencies can still affect consumers. The specific form of the change must be evaluated before release.

## 2. Distinguishing Old APIs, New APIs, and Supported Contracts

Not every class or method existing in an artifact is guaranteed by the vendor to be stable. Before designing a replacement API, identify:

- **Supported API:** methods, classes, interfaces, SPIs, configurations, or behaviors that consumers are permitted to depend on according to the published contract.
- **Deprecated API:** an API that still exists, though the vendor recommends moving to another solution; during the support window, its contract still needs to be respected.
- **Internal API:** implementation details not published as a stable surface for consumers.
- **Experimental API:** an API provided for evaluation but having a different stability policy than official APIs.

Deprecation is a signal about **the future of the API**, not an announcement that the API has immediately stopped working. When a supported method is marked deprecated, consumers unable to upgrade yet still normally expect it to work properly during the published support period.

Beyond method signatures, an API contract can include input preconditions, null rules, exceptions, result ordering, transaction boundaries, thread-safety, serialization, configuration, and side effects. To safely add a replacement API, you must know these constraints precisely.

## 3. Pinning Down the Purpose of the Replacement API

Do not create a new API just to rename a method without clear benefit. First, identify the problem with the old API and the criteria for solving it.

| Problem with the Old API | Potentially Suitable Replacement Approach | What to Evaluate |
|---|---|---|
| Returns null to represent not found | Use Optional or a meaningful domain result | Distinguish non-existence from system errors |
| Accepts multiple parameters of the same type, easy to pass wrongly | Use a parameter object or domain type | Object creation cost and impact on callers |
| Leaks implementation exceptions | Define stable exceptions at the module boundary | Preserve cause and error classification capability |
| Method has too many responsibilities | Split into operations with clear semantics | Avoid breaking transactions or atomicity |
| Depends on JDK internal APIs | Use appropriate public Java SE APIs | Behavior, performance, and Java baseline |
| Uses confusing configuration names | Add a new name and alias mechanism | Precedence order when both old and new names are declared |
| API returns mutable types without ownership rules | Provide stable result types or abstractions | Data compatibility and copying cost |

The result of this step should be a concise description: which consumers benefit, how the new behavior differs, and which parts of the old contract must be kept during the transition period.

## 4. Java Example: Adding a New API and Keeping the Old API

Suppose CustomerService previously returned Customer or threw CustomerNotFoundException. The new API wants to return Optional when a customer is not found. One possible design is:

~~~java
import java.util.Objects;
import java.util.Optional;

public final class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    /**
     * Returns a customer when one exists for the identifier.
     *
     * @param customerId the identifier to look up
     * @return a customer, or an empty Optional when not found
     */
    public Optional<Customer> findById(String customerId) {
        Objects.requireNonNull(customerId, "customerId");
        return repository.findById(customerId);
    }

    /**
     * Looks up a customer using the legacy exception contract.
     *
     * @deprecated Since 2.1, use {@link #findById(String)} and
     *             handle the empty Optional explicitly.
     */
    @Deprecated(since = "2.1", forRemoval = false)
    public Customer findCustomer(String customerId)
            throws CustomerNotFoundException {
        return findById(customerId)
                .orElseThrow(
                    () -> new CustomerNotFoundException(customerId));
    }
}
~~~

In this example, CustomerRepository has a findById method returning Optional<Customer>, while CustomerNotFoundException is a checked exception belonging to the old API. These types are illustrative components of the library.

The important point is that **both APIs share a single lookup flow**. When changing repository logic, caching, or search policy, the team does not have to maintain two independent business implementations. The old API converts the Optional result into an exception to preserve the original contract.

Example using the old API:

~~~java
try {
    Customer customer = service.findCustomer("C-42");
    render(customer);
} catch (CustomerNotFoundException exception) {
    showNotFound();
}
~~~

Example of a consumer migrating to the new API:

~~~java
Optional<Customer> result = service.findById("C-42");

if (result.isPresent()) {
    render(result.get());
} else {
    showNotFound();
}
~~~

Because Optional does not propagate a checked exception for the “not found” case, the new caller needs to handle an empty result explicitly. Genuine I/O errors or backend errors must still have a separate contract; you should not turn every exception into Optional.empty(), as doing so hides incidents.

### 4.1. Conditions for an Adapter to Preserve Compatibility

In the example, the old method should only call the new API if the adapter maintains the committed behavior:

- Preserve the rules for handling invalid customerId.
- Preserve the exception type and required information when the customer does not exist.
- Do not add extra queries or unexpected side effects.
- Preserve synchronization conditions, thread-safety, and transactions if committed.
- Maintain backend error cause information; do not convert backend errors into “not found”.
- Do not change permissions, logging behavior, or observable data outside the published scope.

If the old contract used null instead of an exception, the adapter must reproduce the exact null rules during the transition period. You must not arbitrarily change “not found returns null” to “throws an exception” just because the new API was designed differently.

### 4.2. The Reverse Delegation Direction Can Also Be Suitable

In some systems, the old implementation is already stable and complex. The new API can temporarily call the old API and convert the result:

~~~java
public Optional<Customer> findById(String customerId) {
    try {
        return Optional.of(findCustomer(customerId));
    } catch (CustomerNotFoundException exception) {
        return Optional.empty();
    }
}
~~~

This approach is useful when wanting to release the new API with low risk. However, if findCustomer could previously return null, Optional.of will throw NullPointerException; in that case, handle it according to the actual contract. Additionally, when planning to remove the old API, the development team may want to move the implementation into a shared internal function to avoid the new API having a long-term dependency on a method about to be deleted.

Do not create a direct call cycle between the two methods. If findById calls findCustomer and findCustomer calls findById, the application will fall into infinite recursion.

## 5. Ensuring Compatibility When Adding an API

Adding something new seems less risky than removing or modifying an existing API, but three compatibility dimensions must be distinguished.

**Source compatibility** means old consumer source code still compiles when using the new library version. **Binary compatibility** means compiled consumer bytecode still links with the new artifact. **Behavioral compatibility** means consumers still observe results and operational rules conforming to the previous contract.

| Change | Risks to Check |
|---|---|
| Adding a new method to a public class | Name/overload collision, ambiguity when calling with null or lambdas, impact on subclasses |
| Adding an abstract method to an interface | Implementor classes may fail to recompile; invocation on old implementations may cause AbstractMethodError |
| Adding a default method to an interface | May create conflicts between inherited interfaces, or change method resolution |
| Adding an overload with the same name | The compiler may select a different overload or report ambiguity for existing calls |
| Adding a new return type on a differently named method | Relatively independent, but check dependency exposure and JDK baseline |
| Adding a new API while modifying shared logic | The old API may change behavior even though the signature stays unchanged |
| Adding a method with a matching name in a superclass | May affect dispatch, inheritance, or overrides in consumers |

For example, if accept(String) previously existed and accept(Integer) is added, the call accept(null) can become ambiguous. This is a source incompatibility even without changing the old method.

~~~java
public void accept(String value) { /* legacy */ }
public void accept(Integer value) { /* new */ }

// With both overloads, the following statement can cause an ambiguous error:
accept(null);
~~~

Therefore, choosing a clearly meaningful new method name is sometimes less risky than adding an overload that only differs in parameter type.

## 6. Adding New Methods to an Interface Requires Extra Caution

An interface is a contract for both **callers** and **implementors**. A library may know every place calling the API, yet not know all the projects implementing that interface themselves.

Suppose:

~~~java
public interface DocumentStore {
    Document load(String id);
}
~~~

Adding an abstract method:

~~~java
public interface DocumentStore {
    Document load(String id);

    Optional<Document> findById(String id);
}
~~~

will require recompiled implementations to add findById, unless the class is abstract or there is another suitable mechanism. Old implementation bytecode may load in some situations, but when the new method is called via the interface without an implementation, AbstractMethodError can occur.

A default method can reduce the requirement to modify implementations:

~~~java
public interface DocumentStore {
    Document load(String id);

    default Optional<Document> findById(String id) {
        return Optional.ofNullable(load(id));
    }
}
~~~

Even so, a default method is not automatically safe for every situation. If an existing implementation has a method with the same name but an incompatible return type, or a class inherits multiple interfaces providing conflicting default methods, consumers can still encounter compile errors. In particular, the default implementation must preserve the right semantics when load throws an exception or returns null.

When the vendor does not control all implementors, consider:

- Adding a new interface to extend capabilities instead of adding abstract methods to the old interface.
- Providing an adapter or abstract base class with a default implementation.
- Using a default method when semantics and compatibility have been verified.
- Exposing the new API on a separate service/facade.
- Publishing clear instructions for teams implementing the SPI themselves.

You must test consumers that implement the interface directly, anonymous classes, mocks, and proxies, not just consumers calling the method.

## 7. Deprecation in Java: Announcing Replacement Intent

Java provides the Deprecated annotation and the deprecated Javadoc tag to help IDEs, compilers, and users recognize old APIs.

~~~java
/**
 * @deprecated Since 2.1, use {@link #findById(String)}.
 *             The legacy method will be supported during the migration window.
 */
@Deprecated(since = "2.1", forRemoval = false)
public Customer findCustomer(String id)
        throws CustomerNotFoundException {
    // Legacy behavior remains supported.
}
~~~

The two mechanisms play complementary roles:

- **@Deprecated:** metadata in Java, allowing the compiler and tools to warn when code uses a deprecated API.
- **Javadoc @deprecated:** guidance content, explaining why the old API is discouraged and where consumers should migrate.

The since and forRemoval attributes were added to the Deprecated annotation in Java 9. If the project must compile source with JDK 8, use the annotation form compatible with that JDK, while expressing version information and plans in Javadoc or separate documentation.

**since** indicates from which version the deprecation label applies according to the library's versioning scheme. **forRemoval = true** expresses the intent to remove the API in the future; it does not automatically delete the API and does not specify a concrete removal date. Therefore, a separately published versioning policy, release notes, or end-of-support schedule is needed.

### 7.1. What a Useful Deprecation Notice Should Clarify

A good notice should answer:

1. What is wrong with the old API or why is it no longer suitable?
2. Which API is the official replacement path?
3. Does the migration require changing data types, exceptions, or behavior?
4. Is it necessary to upgrade the Java, Gradle, framework, or dependency baseline?
5. Which version began deprecation and what is the remaining support scope?
6. Is there an expected milestone for end of support or removal, if already decided?
7. Are there before/after examples, migration documentation, and tests for consumers to verify themselves?

Simply writing “Deprecated, use new API” is usually not enough if return types, errors, or semantics differ.

## 8. Transition Period and Versioning Policy

There is no single deprecation period suitable for every library. The transition period depends on the number of consumers, deployment schedules, API criticality, security requirements, and support commitments.

Example of an illustrative roadmap:

| Phase | Hypothetical Version | Vendor Actions | Consumer Actions |
|---|---|---|---|
| Preparation | 2.0 | Record old contract, design and test new API | Provide use cases and real-world constraints |
| Expand | 2.1 | Release new API, keep old API, start deprecation | Can upgrade library without changing source yet |
| Migrate | 2.2–2.x | Add guides, address feedback, report progress | Migrate module by module and retest |
| Removal decision | Before breaking release | Inventory consumers, confirm policy and warnings | Complete migration or request exceptions |
| Contract | A major version or announced milestone | Remove old API per support policy | Use new API, update dependencies and builds |

The version numbers above are for illustration only. Removing old APIs in a major version usually aligns with Semantic Versioning, but not every project uses SemVer, and incrementing the major version does not automatically make a breaking change safe. Decisions must be based on the published versioning policy, consumer upgrade capability, and support contracts.

It may be necessary to maintain a maintenance branch for consumers unable to upgrade yet, but doing so creates additional bug-fixing and security costs. The maintenance scope must be clear on duration, responsible owner, and types of patches provided.

## 9. Migration Guides Need to Provide Concrete Substitutions

The best migration documentation for users is guidance that can be applied directly to existing code.

Example with the old API:

~~~java
Customer customer = service.findCustomer(id);
process(customer);
~~~

In a method that can throw CustomerNotFoundException, the consumer might be handling the exception at a higher calling layer.

How to switch to using the new API:

~~~java
Optional<Customer> customer = service.findById(id);
if (customer.isEmpty()) {
    handleMissingCustomer(id);
    return;
}

process(customer.get());
~~~

When migrating, clearly state that the “not found” case has moved from a checked exception to Optional.empty. This changes the consumer's error handling responsibility. If the consumer previously caught the exception in a shared exception handler, switching to Optional may require updating control flow in the service or controller layer.

A mapping table can be helpful:

| Old API Behavior | New API Behavior | What Consumers Need to Do |
|---|---|---|
| Returns Customer when found | Optional containing Customer | Extract value after checking state |
| Throws CustomerNotFoundException when missing | Optional.empty | Handle the not-found branch |
| Throws other backend errors | Preserved or uses documented domain errors | Check catch, retry, and logging mechanisms |
| Accepts customerId per published rules | Preserved or has clearer rules | Check null/blank cases and special characters |

If the new API changes measurement units, element ordering, transactions, or asynchronicity, add examples for each of those changes. Do not imply a 1:1 replacement if the two APIs have different behavioral contracts.

### 9.1. Migration Support Tools

Depending on project scale, you can use:

- IDE quick fixes or refactoring to change methods and imports.
- Static analysis to list call sites of the old API.
- OpenRewrite or similar rewrite tools for changes with clear rules across many modules.
- Consumer compile tests to confirm new code compiles.
- Integration tests and contract tests to check new semantics.

Automated refactoring usually handles simple renames or signature changes well. For changes from exceptions to Optional, from callbacks to CompletableFuture, or retry logic changes, business processing flows must be inspected instead of applying mechanical rewrites.

## 10. Coordinating Consumer Migration

Vendors need to know who is using the old API. For internal libraries, you can rely on dependency graphs, source search, build reports, and lists of deployed artifacts. For externally released libraries, the consumer list may be incomplete.

A consumer list should record:

| Field | Meaning |
|---|---|
| Consumer | Repository, module, or application using it |
| Library version | Which artifact is using the old API |
| Old API | Method, class, or configuration needing migration |
| Owner | Team with authority to modify the consumer |
| Constraints | JDK, framework, deployment window, or dependencies |
| Status | Not started, in progress, tested, deployed |
| Evidence | Confirming commit, build, test, or release |
| Exceptions | Reason for not upgrading yet and resolution deadline |

During the transition period, prioritize critical consumers, consumers with slow release schedules, and consumers implementing SPIs themselves. Migrating all internal consumers before deleting the old API helps reduce risk, but external consumers that the team cannot directly observe must still be accounted for.

If measuring old API usage, choose an appropriate method: static usage analysis, build warnings, controlled telemetry, or version info from consumers. Do not inject logging into every API call on hot paths that degrades performance or collects unnecessary data. Runtime invocation counts also do not prove all consumers have been found, because many code paths only execute on rare events.

## 11. Creating Signals for Consumers to Self-Identify Old APIs

After marking Deprecated, IDEs and compilers can display warnings when consumers use the API. In Java projects, you can instruct javac to display additional deprecation details:

~~~bash
javac -Xlint:deprecation -cp library.jar Consumer.java
~~~

With Gradle JavaCompile, you can add the configuration:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Xlint:deprecation")
}
~~~

This is a Kotlin DSL example. The compiler can emit warnings at locations calling deprecated APIs. If the team wants to use warnings as a quality gate, clearly define the scope and enforcement timeline. Do not enable treating all warnings as errors immediately upon deprecating an API if consumers cannot yet migrate under the published support policy.

Some temporary exceptions may require @SuppressWarnings("deprecation") in adapters or transition code. If using suppression, limit its scope, accompanied by a reason, owner, and review date so it does not mask newly introduced calls to old APIs elsewhere.

## 12. Testing While Both APIs Coexist

When two APIs exist, the vendor needs to protect both contracts until support for the old API ends. Testing only the new API is not enough.

### 12.1. Testing Behavior of the Old API

Tests should verify the published behaviors:

- Valid data still returns the correct result.
- The not-found case still returns null or throws the same exception type as before.
- Null, blank, or invalid inputs still follow the contract.
- Backend errors are still propagated or wrapped as committed.
- Side effects, transactions, and concurrency do not change unexpectedly.

### 12.2. Testing Behavior of the New API

Tests need to cover both present and absent results, backend errors, boundary conditions, and newly published processing rules.

### 12.3. Testing Equivalence Between Both APIs

For behavioral aspects expected to be equivalent, use the same dataset to confirm:

~~~java
@Test
void bothApisReturnSameExistingCustomer() throws Exception {
    Customer legacy = service.findCustomer("C-42");
    Customer current = service.findById("C-42").orElseThrow();

    assertEquals(legacy.getId(), current.getId());
}
~~~

The example above assumes the test environment uses JUnit and Optional.orElseThrow() is supported on the project's Java baseline. Classes and fixtures are illustrative. When not found, separate tests need to verify that the old API throws CustomerNotFoundException and the new API returns Optional.empty.

Do not require both APIs to be identical in every respect if the new API was designed to change semantics; instead, clearly describe which parts are equivalent and which parts change intentionally.

### 12.4. Testing Old Consumers

An important case is taking a consumer already compiled against the old library and running it with the new library version. This helps detect linkage errors, bytecode changes, dependency changes, or behavioral changes that only compiling new tests cannot see.

At the same time, recompile several old consumers against the new library to detect source incompatibilities due to overloads, default methods, interfaces, or generic types.

## 13. Factors That Can Make the New API Unusable

A new API is only useful when target consumers can reach and run it. Before publishing, identify:

**Java baseline:** Optional exists since Java 8; the @Deprecated(since=..., forRemoval=...) form exists since Java 9. If the library supports Java 8, the syntax and APIs used in the implementation must be compatible with that compilation environment or have an appropriate --release configuration.

**Dependency exposure:** if the new method returns a type from an external library, consumers may have to receive that dependency on the compile classpath. This increases coupling and can create version conflicts.

**Module boundary:** if using JPMS, the types and packages of the new API must be properly exported. A public method in a non-exported package is not necessarily an API usable from another module.

**Serialization and protocols:** if the new API changes DTOs, enums, records, JSON fields, or configuration names, verify data exchange compatibility with old consumers. Java source compatibility does not guarantee wire format compatibility.

**Reflection and code generation:** frameworks, mappers, dependency injection, annotation processors, or proxies may depend on old constructors, annotations, or method names. Such consumers do not necessarily appear as direct calls in source code.

**Naming and overloading:** the new API name must be meaningful; avoid ambiguous overloads or names colliding with methods that consumer subclasses have already declared.

**State-dependent APIs:** if the new version only works when data has been migrated, coordinate schema and rollout. You cannot just add a method and assume consumers can upgrade independently.

## 14. Extending the Rule to Configuration and Service APIs

The add-first, remove-later principle does not apply only to Java methods.

### 14.1. Configuration

Suppose the application currently uses the property:

~~~yaml
client:
  timeout-ms: 3000
~~~

The team wants to use an explicit duration format:

~~~yaml
client:
  timeout: 3s
~~~

During the transition period, both names can be supported, defining a precedence order when both coexist, and warning when the old configuration is used. Without defining precedence, deployments having both timeout-ms and timeout may exhibit unpredictable behavior.

When discontinuing support for timeout-ms, update documentation, sample configurations, and consumers before removing the parser alias.

### 14.2. REST API

A new endpoint can be deployed alongside the old endpoint. For example, replacing /v1/customers/{id} with /v2/customers/{id} when schemas and semantics change significantly. Keep the old route according to the support policy, publish client migration guidance, and test both versions.

Do not simply create a new path and reuse an internal controller to return data different from the old endpoint's contract. Even if both APIs rely on the same service, the adapter at each endpoint must still guarantee its own status codes, headers, schema, and error responses.

### 14.3. Events and Data Schemas

With asynchronous producers/consumers, adding new fields typically requires evaluating schema compatibility rules and consumer acceptance. Producers and both old and new consumers may run concurrently. Depending on the system, dual-read, dual-write, or a new event version may be needed; do not remove old fields before consumers are ready.

These examples show that “adding a new API” is effectively managing two contracts during a transition period.

## 15. When Can Support for the Old API Be Discontinued?

An old API should only be taken out of support scope once a decision aligned with the release policy and consumer risk has been made.

Questions that need to be answered:

1. Does the replacement API have sufficient features and documentation for the supported use cases?
2. Have consumers under direct control upgraded and deployed successfully?
3. Are there external consumers or downstream libraries still using the old API?
4. Has the deprecation milestone been published and has the transition window met commitments?
5. Is there a rollback plan or maintenance branch if consumers cannot upgrade yet?
6. How will the removal release change source, binary, behavior, configuration, or data?
7. Do compatibility tests cover critical consumers and error cases?

Discontinuing support can take several forms: stopping new feature development for the old API, providing only security fixes, declaring end of support, or removing the API from the artifact. Clarify each milestone, because **deprecated**, **unsupported**, and **removed** are different states.

When actually deleting a public method or class, unmigrated consumers may fail to compile or encounter NoSuchMethodError/NoClassDefFoundError at runtime. The removal milestone must be reflected in the release notes and migration guide of the corresponding release version.

## 16. Common Mistakes

**Deleting the old API as soon as the new API is added.** Gives consumers no time to migrate, especially when multiple applications have different release schedules.

**Keeping the old API while changing its behavior.** An adapter returning different results, changing exceptions, dropping transactions, or altering null handling breaks the old contract even though the method still exists.

**Simply adding an abstract method to an interface.** Those implementing the interface themselves may be forced to edit source code or hit runtime errors; choose an appropriate extension point.

**Marking Deprecated without guidance.** Compiler warnings do not explain migration logic or behavioral differences to consumers.

**Using forRemoval=true as a deletion schedule.** The annotation expresses intent, not a specific version or date; announcements must have a separate release policy.

**Maintaining two independent business implementations.** Two logic branches can diverge over time. Use a shared implementation when both contracts allow it.

**Turning exceptions into Optional.empty for all cases.** Infrastructure errors and “not found” have different semantics; merging them loses operational signals.

**Testing only the new API.** During the transition period, existing consumers still need protection.

**Assuming a major version is enough to delete arbitrarily.** Support policies, downstreams, and practical consumer capabilities must still be evaluated.

## 17. Execution Process in a Java Compatibility Migration

Work can be organized according to the following steps:

### Step 1: Inventory Contracts and Consumers

Identify the old API, actual usage patterns, and the Java/Gradle/framework versions consumers are using. Distinguish callers, implementors, and consumers using reflection or configuration.

### Step 2: Design the Replacement API

Describe goals, data types, inputs, outputs, exceptions, immutability, side effects, and semantic differences. Choose clear new names, avoiding ambiguous overloads and unnecessary dependencies.

### Step 3: Add the New API in a Compatible Way

Publish the new API, keep the old API, and design shared adapters/implementations. For interfaces or SPIs, evaluate source and binary compatibility separately for implementors.

### Step 4: Announce Deprecation with Guidance

Use annotations and Javadoc compatible with the Java baseline; state the version deprecation started, the replacement API, before/after examples, and support duration if decided.

### Step 5: Verify Both Contracts

Compile both new and old consumers, run tests on the minimum supported JDK, check old consumer bytecode against the new artifact, and test error/edge-case behavior.

### Step 6: Migrate Consumers According to the Roadmap

Prioritize critical consumers, update dependencies and source code, and track deployment status. Record exceptions, owners, and action steps when migration is not yet possible.

### Step 7: Evaluate End-of-Support Criteria

Confirm versioning policy, maintenance commitments, and consumer migration evidence. Announce the final version supporting the old API and the planned removal version if decided.

### Step 8: Controlled Removal and Monitoring

Perform API removal only at the appropriate release milestone; run tests and verify migration guides, dependencies, and release notes. Monitor compile/runtime errors from consumers after release and maintain an appropriate incident handling channel.

## 18. Checklist for Library Publishers

- [ ] Described the problem with the old API and the benefits of the replacement API.
- [ ] Distinguished supported contracts from implementation details.
- [ ] Preserved the behavior of the old API during the committed support window.
- [ ] Considered source, binary, and behavioral compatibility when adding the API.
- [ ] Checked interface implementors, overloads, generic types, subclasses, and reflection.
- [ ] Selected the Java baseline and ensured the new API is usable on supported JDKs.
- [ ] Added deprecated Javadoc, annotations, and a migration guide.
- [ ] Tested the new API, old API, and previously compiled consumers.
- [ ] Communicated the migration roadmap, owners, and versioning policy.
- [ ] Defined practical conditions before discontinuing support or removing the old API.

## Conclusion

Adding a replacement API before discontinuing support for the old API is a controlled way to evolve contracts. Vendors open a path for consumers to use the new design, still keep the old contract during the transition period, then guide upgrades and verify readiness before removal. The core of the strategy does not lie in the Deprecated annotation, but in understanding consumers, maintaining committed compatibility, building behaviorally accurate adapters, testing both old and new versions, and publishing a roadmap aligned with the library's support lifecycle.
