# Verifying Observed Results Against the Exact Spring Javadoc and Documentation Version

## 1. Practical Problem: When Runtime Behavior Differs from Online Examples

In Spring Framework, seeing a method name in Javadoc is not enough to conclude how it behaves in your situation. You must know the **actual running version**, **the class/mechanism handling the request**, **the applicability conditions**, and **what the documentation guarantees**.

Examples in the Spring Framework – validation/data-binding module:

- You submit a form with `approved=true` and see the field ignored. Did `@Valid` block it?
- You call `DataBinder#setAllowedFields("name")`, see `"approved"` in `getSuppressedFields()`, yet `hasErrors()` remains false. Is that a bug?
- You enable `setDeclarativeBinding(true)` and call `bind(...)`, and setters are not invoked. Does this also apply to constructor binding?
- You change `setAutoGrowCollectionLimit(4)`, yet a List bound via constructor still grows larger than 4. Why?
- `@Valid @RequestBody` throws `MethodArgumentNotValidException`, whereas `@Min` directly on `@RequestParam` throws `HandlerMethodValidationException`. Why?
- A blog post says “that method doesn't exist yet,” while your project compiles fine. Was the blog targeting Spring Framework 5.3, 6.0, 6.1, 6.2, or 7.0?

The practical goal is generating **reproducible evidence**, then checking it against **the exact version's Javadoc and Reference Guide**. We do not trust a doc just because it ranks first in search results; nor do we declare an ad-hoc test observation to be a stable Spring contract.

After this lesson, you will be able to:
1. Determine Spring Boot and Spring Framework **resolved versions**, avoiding confusing the two version lines.
2. Read exact signatures, `Since`, defaults, preconditions, scope, warnings, and exceptions in Javadoc for the exact **patch**.
3. Use the Reference Guide for the **right major/minor series** and recognize when the displayed page has moved to a newer patch.
4. Write `DataBinder` unit tests verifying `allowedFields`, `suppressedFields`, `declarativeBinding`, and conversion errors.
5. Write MockMvc tests for `@ModelAttribute`, `@RequestBody`, Bean Validation, and handler method validation.
6. Distinguish **what Javadoc guarantees** from behavior dependent on version, configuration, or implementation details.
7. Build a traceability table: **claim → documentation → version → test → actual result → verdict**.
8. Write evidence reports suitable for pull requests or Spring upgrades.

**Scope:** Java 17+, Spring Boot **3.5.6** and Spring Framework **6.2.11** as the fixed baseline for the sample project; Spring MVC Servlet stack, Jakarta Validation, Spring Test. Never use Spring Framework 7 API snippets to draw conclusions for a project running Spring 6.

## 2. Rule Number One: Boot Version Differs from Framework Version

### 2.1. Two Distinct Version Numbers

A `pom.xml` containing:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
</parent>
```

does **not** mean `org.springframework.validation.DataBinder` comes from “Spring Framework 3.5.6”. Spring Boot manages a curated bill of dependencies, in which Spring Framework modules have their own version line.

For the root artifacts of **Spring Boot 3.5.6**, Maven Central records:
- `org.springframework:spring-core:6.2.11`.
- `org.springframework:spring-web:6.2.11`.
- `org.springframework:spring-webmvc:6.2.11`.

Verification sources:
- [Maven Central — spring-boot-starter-web 3.5.6](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-web/3.5.6).
- [Spring Framework 6.2.11 release announcement](https://spring.io/blog/2025/09/11/spring-framework-6-2-11-available%20now/), noting this version aligns with Boot 3.5.6.
- [Spring Boot 3.5.6 release announcement](https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now/).

This is the **official baseline**. Real applications may override `spring-framework.version`, import another BOM, apply custom dependency management, repackage jars, or suffer classpath conflicts. Therefore, you must always verify the **actually resolved and loaded** versions.

### 2.2. Checking Maven Resolved Versions

In the project directory:

```bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework
mvn help:evaluate -Dexpression=spring-framework.version -DforceStdout
mvn help:effective-pom -Doutput=target/effective-pom.xml
```

Checks:
- `mvn -version`: Maven and Java runtime versions.
- `dependency:tree`: which `org.springframework:*` jars resolved, their scopes, and the dependency paths pulling them in.
- `help:evaluate`: the `spring-framework.version` property in the effective Maven model if provided.
- `effective-pom`: actual dependency management and plugin configurations after inheritance/profiles.

**Never fabricate full `dependency:tree` output.** An **illustrative excerpt** to look for in the baseline project is:

```text
org.springframework:spring-core:jar:6.2.11
org.springframework:spring-web:jar:6.2.11
org.springframework:spring-webmvc:jar:6.2.11
```

A full dependency tree also shows scopes, parent paths, and differing order. When reporting an issue, attach the actual output from the project running the tests.

On Windows PowerShell, when the shell parses dots or property arguments unexpectedly, quote each `-D...` argument:

```powershell
mvn dependency:tree "-Dincludes=org.springframework"
mvn help:evaluate "-Dexpression=spring-framework.version" "-DforceStdout"
```

### 2.3. Gradle Uses Different Commands from Maven

For Gradle projects, run:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

On Windows you can use `gradlew.bat`. Never inspect a Maven POM and assume a Gradle project receives the exact same versions if platforms, `resolutionStrategy`, constraints, or dependency locking are present.

### 2.4. Checking the Runtime Version

Spring provides:

```java
import org.springframework.core.SpringVersion;

System.out.println(SpringVersion.getVersion());
```

In the sample Maven build, the expected output is:

```text
6.2.11
```

`SpringVersion.getVersion()` can return null in some runtime environments lacking implementation version metadata. For the example's Maven application packaging standard jars, the test asserts exact **6.2.11**. If a project uses custom repackaging/shading that strips metadata, inspect `Package.getImplementationVersion()`, `CodeSource`, and the actual jar files as well.

**Principle:** the build-time resolved version and the runtime-loaded class version must match; if they diverge, investigate the classpath, plugins, container, or multiple classloaders.

## 3. Choosing the Right Documentation Sources — Order of Precedence

A review workflow can follow this order:

1. **Javadoc for the exact patch**: signature, parameters, return type, `Since`, defaults, preconditions, limitations.
2. **Reference Guide for the exact branch**: how APIs fit together in Spring MVC, Servlet/WebFlux, validation, and data binding.
3. **Release notes/changelog per release/tag**: API changes and bug fixes across patches.
4. **Source code at the exact tag**: when docs do not clarify an edge case, verify the exact implementation.
5. **Minimal reproduction tests** using verified dependency versions.
6. Blogs/Stack Overflow/videos: reference ideas and hypotheses only, **never** a substitute for versioned evidence.

Never reverse this order to “get a test passing and then hunt for a blog post that agrees”.

### 3.1. Exact Patch 6.2.11 Javadoc

Specific links:

- [DataBinder — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/DataBinder.html)
- [BindingResult — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/BindingResult.html)
- [FieldError — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/FieldError.html)
- [WebDataBinder — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/bind/WebDataBinder.html)
- [HandlerMethodValidationException — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [ResponseEntityExceptionHandler — Spring Framework 6.2.11 API](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)

On the Javadoc page, verify the banner says **Spring Framework 6.2.11 API**, not just the tail of the URL. For each method, read **Method Details**, not only Method Summary.

**Link accuracy:** If a specific Javadoc page is temporarily unindexed by search engines, open the Javadoc index for release [6.2.11](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/) directly and browse by package. Never switch to “current” and silently change patches.

### 3.2. The 6.2 Reference Guide Branch May Reflect a Newer Patch

Links:

- [Spring Framework — Data Binding, 6.2 branch](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html)
- [Spring Framework — @InitBinder, 6.2 branch](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework — @ModelAttribute, 6.2 branch](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC validation, 6.2 branch](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Spring MVC MockMvc](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html)

**Trap:** `/reference/6.2/...` pins the **minor series**, while the page header may display a **newer 6.2.x patch**. At the time of writing for this example, some 6.2 branch pages displayed 6.2.19 while the Maven baseline was **6.2.11**.

Therefore:
- Use the 6.2 Reference Guide to understand **architecture and recommendations**.
- Use Javadoc **6.2.11** to verify the API contract for the exact binary.
- When suspecting a discrepancy due to a fix between patches, check the `v6.2.11` source tag and release notes, then run baseline tests.
- Never claim “the 6.2 Reference Guide is an exact snapshot of 6.2.11” if the banner shows a different patch.

### 3.3. Source at the Exact Git Tag

- [Spring Framework source tag v6.2.11](https://github.com/spring-projects/spring-framework/tree/v6.2.11).
- [Spring Boot source tag v3.5.6](https://github.com/spring-projects/spring-boot/tree/v3.5.6).

Example inspecting `DataBinder`:
1. Switch to tag `v6.2.11`, never the default “main” branch.
2. Open module `spring-context` and package `org.springframework.validation`.
3. Read `DataBinder.java`, `setDeclarativeBinding`, and the flows of `bind(PropertyValues)`/`construct(ValueResolver)`.
4. If behavior depends on MVC, follow call sites in `spring-webmvc`.
5. When citing something as a **public contract**, anchor on Javadoc; source implementation merely clarifies the exact tag's behavior.

**When comparing patches** 6.2.11 vs 6.2.19, inspect the Git diff between tags and changelogs instead of guessing that different patches imply different semantics.

## 4. Checklist for Reading a Method's Javadoc

For any API, record:

| Field | Specific question |
| --- | --- |
| Class/package/module | Does the API belong to `spring-context`, `spring-web`, or `spring-webmvc`? |
| Declaration | Name, visibility, argument types, generics, annotations? |
| `Since` | Which Framework version introduced the method? |
| Defaults | Could default values differ from expectations? |
| Applies to | Setter/property, constructor, form, JSON, Servlet, or WebFlux? |
| Preconditions | Requires target object, conversion service, validator, model attribute name? |
| Return/side effects | Mutates state on binder, target, BindingResult, or throws exception? |
| Exceptions | Argument conversion, binding, method validation, or user-constructor exception? |
| Security | Warnings about exposed object graphs or mass assignment? |
| “See Also” | Which related APIs must be read for full context? |
| Version links | Exact patch Javadoc, matching minor Guide, matching release source tag? |
| Test evidence | Which test proves this statement and can be re-run? |

An insufficiently precise claim:

> “`setAutoGrowCollectionLimit(4)` guarantees every List received from a request has at most four elements.”

That statement is overly broad. Javadoc **6.2.11** states this limit governs collection auto-growth during **setter/field property binding**, and explicitly notes it **does not apply** to `construct(ValueResolver)`. Revise it to:

> “`setAutoGrowCollectionLimit(4)` limits array/collection auto-growth along the `bind(PropertyValues)` path; it must not be used as a general quota for constructor binding or request bodies.”

This is a classic example of **reading the full "Used for..." notes**, not only the summary line.

## 5. Specific Verification 1: `setAllowedFields` and Suppressed Fields

### 5.1. What Does Javadoc 6.2.11 Say?

`DataBinder#setAllowedFields(String... allowedFields)`:
- Registers patterns of fields permitted to be bound.
- Allows all fields by default.
- Intended to prevent unwanted modifications from client-supplied HTTP data.

`BindingResult#getSuppressedFields()`:
- Returns the list of fields suppressed during binding.

**There is no guarantee** that every suppressed field becomes a `FieldError`. If an application must **reject** requests carrying out-of-allowlist fields, it must inspect suppressed fields explicitly.

### 5.2. Test Model

A JavaBean:

```java
public class AuditForm {
    private String name;
    private Integer seats;
    private boolean approved;
    // getters and setters
}
```

A binder:

```java
AuditForm form = new AuditForm();
DataBinder binder = new DataBinder(form, "auditForm");
binder.setAllowedFields("name", "seats");

MutablePropertyValues values = new MutablePropertyValues();
values.add("name", "Mai");
values.add("seats", "2");
values.add("approved", "true");

binder.bind(values);
```

This excerpt comes from the complete project in section 12. Expectations:
- `form.getName()` is `Mai`.
- `form.getSeats()` is Integer 2.
- `form.isApproved()` remains false.
- `getSuppressedFields()` contains `approved`.
- `hasErrors()` can remain false if all bound values are valid.

**Right conclusion:** The allowlist works and leaves a suppression trace. **Wrong conclusion:** Bean Validation rejected `approved`; `@Valid`/`@NotBlank` alone are not a field allowlisting mechanism.

### 5.3. Mapping Javadoc → Test → Verdict

| Claim | 6.2.11 docs | Test to run | Expected conclusion |
| --- | --- | --- | --- |
| Default `DataBinder` can call unlisted setters | `setAllowedFields`: default all fields | Bind `approved=true` without allowlist | `approved=true` |
| Allowed-fields blocks unlisted properties | `setAllowedFields` + `bind` | Bind name, seats, approved with allowlist | Approved remains false |
| Blocked field recorded on result | `BindingResult#getSuppressedFields` | Assert suppressed array contains approved | Suppressed field recorded |
| Suppression is not necessarily a validation error | `BindingResult` and `FieldError` are separate structures | Assert `hasErrors()==false` when remaining inputs are valid | True with suppression and zero FieldErrors |
| Type conversion failure creates binding error | `DataBinder` `typeMismatch` error | Bind `seats=abc` | `FieldError.bindingFailure=true` |

Never cite these rows as **executed Maven results**. They are **expected assertions**; actual evidence exists only after running the test suite.

## 6. Specific Verification 2: `setDeclarativeBinding(true)`

### 6.1. Version and Scope

Javadoc `DataBinder#setDeclarativeBinding(boolean)` in **6.2.11**:
- `Since: 6.1`.
- Default is `false`.
- `true` restricts binding to constructor arguments via `construct(...)`, and to permitted properties when `allowedFields` is configured.

Meaning:
- Calling only `setDeclarativeBinding(true)` then `bind(PropertyValues)` on a mutable bean, **without** declaring `allowedFields`, generally **performs no property binding**.
- If `setAllowedFields("name")` is configured, property binding for `name` can proceed.
- When declaring a constructor argument named `approved`, `allowedFields` is **not** a general filter for that argument.

### 6.2. Two Tests That Must Be Kept Separate

```java
// A: declarative binding without allowedFields
binder.setDeclarativeBinding(true);
binder.bind(values);
// Property setters are not invoked per documented mechanism.

// B: declarative binding + explicit property allowlist
binder.setDeclarativeBinding(true);
binder.setAllowedFields("name");
binder.bind(values);
// Only the name setter/property is permitted.
```

**Never run a constructor-binding experiment and conclude `bind(PropertyValues)` behaves the same way.** The methods have different inputs and scopes.

### 6.3. Differences from 5.3/6.0 Docs

`setDeclarativeBinding` has `Since 6.1`. A Spring 5.3 blog post omitting this API does not prove the API **does not exist** in 6.2.11. Conversely, if a real project runs 6.0.x, copying a method from 6.2 Javadoc will fail to compile.

When seeing `cannot find symbol: setDeclarativeBinding`:
1. Check imports for `org.springframework.validation.DataBinder`/`org.springframework.web.bind.WebDataBinder`.
2. Check the effective Framework version.
3. Compare IDE compile classpath against the Maven build classpath.
4. Open the **Javadoc for the exact resolved version** and check `Since`.
5. Never work around it by declaring a dummy method with the same name on the DTO.

## 7. Specific Verification 3: `setAutoGrowCollectionLimit`

### 7.1. What the Documentation Guarantees

In Javadoc 6.2.11:
- `DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` is **256**.
- `setAutoGrowCollectionLimit(int)` adjusts the auto-growing limit for arrays/collections.
- `setAutoGrowNestedPaths(boolean)` controls auto-initializing null nested paths.
- **Both** are documented in Javadoc for **setter/field injection via `bind(PropertyValues)`**, **not** constructor binding via `construct(ValueResolver)`.

This is an **official API scope boundary**, not just an observation from source implementation.

### 7.2. Simple Test

```java
DataBinder binder = new DataBinder(new AuditForm());

assertEquals(
        DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT,
        binder.getAutoGrowCollectionLimit());

assertEquals(256, binder.getAutoGrowCollectionLimit());
```

This test proves the default on the baseline version. It **does not** prove every HTTP body, Map, or List is capped at 256.

### 7.3. Why Distinguish “Default” from “Security”

An auto-grow limit:
- Is not a maximum size for all collections in Java objects.
- Is not a Servlet container maximum parameter count.
- Is not a JSON request body size limit.
- Is not a Map key count limit.
- Does not replace allowlists, quotas, input schemas, or authorization.
- Does not automatically bound collections created by constructor binding.

When experimenting with very large indices, use **small controlled values** rather than sending million-element requests in CI or shared machines. This lesson prioritizes proving **documented scope**, not running unprotected stress tests.

## 8. Specific Verification 4: Validation in MVC

### 8.1. Per the Spring MVC 6.2 Reference Guide

Two common paths:
- Bean Validation applied only to `@ModelAttribute`/`@RequestBody` with `@Valid` and **no direct method constraint** triggering method validation: typically raises `MethodArgumentNotValidException` when no `BindingResult` handles it.
- Constraints placed **directly** on handler parameters, e.g., `@RequestParam("page") @Min(1) int page`: Spring MVC 6.1+ uses built-in **method validation**, typically raising `HandlerMethodValidationException`.

Javadoc `HandlerMethodValidationException` 6.2.11 states status **400** when input validation fails, and status **500** when a **return value** is invalid.

**Note:** A controller with class-level `@Validated` may go through AOP method validation. To observe built-in MVC 6.1+ behavior as in this lesson, omit `@Validated` from the controller class. With handlers combining multiple constraints and argument resolvers, exception routing can vary; actual tests establish the expected contract.

### 8.2. Why Not Assert Only HTTP 400

A test asserting only 400 fails to distinguish:
- Missing query parameter.
- Query text failing Integer conversion.
- Direct `@Min(1)` violation.
- `@Valid @RequestBody` DTO constraint violation.
- Unreadable JSON body.
- Form property binding `FieldError`.

Combine:
1. `MockMvc` and resolved exception type when verifying the **framework path**.
2. HTTP status and JSON error code when verifying the **public API contract**.
3. Exact-version Javadoc/Reference Guide to explain why that path executed.

### 8.3. Validation Failures Differ from Binding Failures

In `DataBinder`, `BindingResult.FieldError.isBindingFailure()` distinguishes setter/conversion errors from constraint errors. Examples:
- `seats=abc`: String→Integer conversion fails; `typeMismatch` error.
- `seats=0`: parses to Integer 0, then `@Min(1)` fails during validation.
- `approved=true` outside `allowedFields`: suppressed; does not necessarily create a `FieldError`.

When writing READMEs or PRs, avoid labeling every 400 case “validation failed”; describe the exact stage accurately.

## 9. Reading `@ModelAttribute` and `@RequestBody` by Stack

### 9.1. Spring MVC Form/Query

`@ModelAttribute` in MVC can use constructor binding, property binding, or a combination. `@InitBinder` configures `WebDataBinder` for a named model attribute. Form/query values normally pass through `ConversionService`/formatters.

A negative suppression test uses:

```java
@InitBinder("auditForm")
void bindAuditForm(WebDataBinder binder) {
    binder.setAllowedFields("name", "seats");
}
```

This configures a **property-binding allowlist**, not a Jakarta Validation constraint and not a JSON deserializer schema.

### 9.2. `@RequestBody` JSON

`@RequestBody` is typically read by Jackson via `HttpMessageConverter`. `@Valid` can still run validation after deserialization, while `WebDataBinder#setAllowedFields` **does not** filter Jackson field deserialization the way form property binding does.

An example payload such as:

```java
public record AuditPayload(
        @NotBlank String title,
        @NotNull @Min(1) Integer quantity) {}
```

is constructed by Jackson from JSON:

```json
{"title":"Book","quantity":2}
```

An error on `{"quantity":{"not":"an integer"}}` occurs during **JSON decoding**, distinct from `@Min(1)` when quantity is 0. Before applying an “`@ModelAttribute` fix” to JSON, consult the `@RequestBody` documentation and test at the Jackson layer.

## 10. Designing an Auditable Verification Table

Sample result table for a team:

| ID | Claim | Actual version | Evidence link | Test & input | Expected | Observed | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DB-01 | Default property binder can populate approved setter | 6.2.11 | `DataBinder#setAllowedFields` | approved=true, no allowlist | approved true | Record after run | PENDING |
| DB-02 | Allowlist suppresses approved | 6.2.11 | `DataBinder#setAllowedFields` | approved=true, allowlist name,seats | approved false, suppressed | Record after run | PENDING |
| DB-03 | Suppression does not automatically create FieldError | 6.2.11 | `BindingResult#getSuppressedFields` | valid values + approved=true | hasErrors false | Record after run | PENDING |
| DB-04 | Declarative binding disables property binding outside allowedFields | 6.2.11 | `DataBinder#setDeclarativeBinding` | declarative=true, no allowlist | target unchanged | Record after run | PENDING |
| DB-05 | Auto-grow default is 256 | 6.2.11 | `DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` | new DataBinder | 256 | Record after run | PENDING |
| MV-01 | Invalid `@Valid @RequestBody` uses argument validation | 6.2.11 | MVC validation Guide | title="" | MethodArgumentNotValidException/400 | Record after run | PENDING |
| MV-02 | Direct `@Min` uses method validation | 6.2.11 | HandlerMethodValidationException Javadoc | page=0 | 400 | Record after run | PENDING |
| MV-03 | Invalid return value is a server error | 6.2.11 | HandlerMethodValidationException Javadoc | broken return null | 500 | Record after run | PENDING |
| JV-01 | Malformed JSON is not Bean Validation | 6.2.11 | `HttpMessageConverter`/Jackson path | malformed JSON | HttpMessageNotReadable/400 | Record after run | PENDING |

**PENDING** is an illustrative label **inside the hands-on document**, not a worker progress status or spreadsheet cell. When learners run Maven, record actual output in a separate report—never alter Javadoc to match a hypothesis.

### 10.1. Every Claim Needs Complete Preconditions

Never write: “`HandlerMethodValidationException` is always thrown when `@Valid` is present.”

Instead write:
- “In Spring MVC 6.2.11, inside a controller **without class-level `@Validated`**, direct `@Min` on a handler parameter uses built-in method validation; test `/audit/page?page=0` confirms the exception path.”
- “With `@Valid @RequestBody` and no other direct method constraint, the JSON request is decoded into the DTO and then validated; test `/audit/json` with a blank title confirms the argument validation path.”

Including **scope + version + setup + input** makes conclusions reproducible.

### 10.2. Distinguishing Three Kinds of Conclusions

1. **Documented contract:** Explicitly stated in Javadoc, e.g., `Since: 6.1` or auto-grow applying to property binding.
2. **Verified behavior under setup:** Your test passes on Boot 3.5.6 + Spring 6.2.11 under a specific configuration.
3. **Implementation detail:** Observed in current source/call stacks without a public guarantee across all patches.

Never elevate level (3) into a public API promise just because a test passed.

## 11. Workflow When “Docs Say One Thing, Tests Do Another”

### Step 1 — State the Hypothesis as a Verifiable Sentence

Example:

> “In Framework 6.2.11, with `setDeclarativeBinding(true)` and no `allowedFields`, calling `DataBinder.bind(...)` on a JavaBean does not write to setters.”

Never write “Spring binding is broken”.

### Step 2 — Lock Down Environment and Inputs

Record:
- Java vendor and version, Maven/Gradle version.
- Boot parent/BOM version.
- `dependency:tree` resolved Framework modules.
- `SpringVersion.getVersion()` at runtime.
- Test context: MVC Servlet, WebFlux, no context, or full `ApplicationContext`.
- DTO types/annotations, input field paths, locale, charset, and timezone if relevant.

### Step 3 — Open Javadoc for the Exact Patch

For `DataBinder`, link `.../docs/6.2.11/javadoc-api/...`. Read Method Details of `setDeclarativeBinding`, `bind`, `setAllowedFields`, and `getBindingResult`; never stop at a single method signature.

### Step 4 — Check the Reference Guide for the Right Generation

Select Spring 6.2 Reference and check the displayed patch banner. If it currently displays 6.2.19, note “6.2 series reference; exact Javadoc/source checked against 6.2.11”.

### Step 5 — Build a Minimal Reproduction

Separate:
- **Pure DataBinder test**: no `ApplicationContext`, testing API behavior independently of MVC.
- **MockMvc integration**: verifying actual argument resolvers/validators/advice.
- **Build/runtime evidence**: verifying dependency metadata.

Running only MockMvc makes it hard to tell whether a bug lies in the binder or MVC configuration. Calling only `DataBinder` does not prove which binding path Spring MVC actually selects.

### Step 6 — Record Actuals Instead of Tweaking Expectations to Pass

If a test fails:
1. Capture assertion failure, resolved exception type, and sanitized debug data.
2. Check runtime version, dependency conflicts, and annotation imports.
3. Trace the source call path at the tag.
4. If behavior contradicts the documented contract, build a minimal reproducible issue/test and contact maintainers.
5. If the patch's Javadoc explicitly contradicts your hypothesis, **fix your hypothesis and code**, not the framework.

### Step 7 — Record a Scoped Verdict

- **PASS:** behavior and docs align under recorded conditions.
- **EXPECTED DIFFERENCE:** doc scope differs from setup (e.g., constructor vs property).
- **VERSION MISMATCH:** reading the wrong major/minor/patch.
- **BLOCKED:** missing dependency tree, unable to run tests, or missing logs.
- **POSSIBLE FRAMEWORK DEFECT:** minimized repro, verified exact patch, and still contradicts documented contract.

A single failure is never enough to conclude Spring has a defect.

## 12. Reproducible Java 17 + Spring Boot 3.5.6 Project

The sample project is intentionally small and focused on verifying Javadoc claims. It requires no database, login, or external API. Production/demo code includes:
- A mutable input bean to observe property binding and suppression.
- A JSON request record to observe Bean Validation through Jackson.
- A controller using `@InitBinder`, `@ModelAttribute`, `@RequestParam @Min`, and `@RequestBody`.
- A `ResponseEntityExceptionHandler` to stabilize the error envelope.
- Three JUnit test classes covering version/Javadoc APIs, raw `DataBinder`, and `MockMvc`.

**There is no such thing as “Spring Framework 6.2.11 = Spring Boot 6.2.11”.** The Maven parent is Boot 3.5.6, and the resolved Spring Framework jars are 6.2.11 per that release's dependency management.

### 12.1. Structure

```text
spring-version-evidence/
├── pom.xml
├── src/main/java/demo/verify/
│   ├── VersionEvidenceApplication.java
│   ├── AuditForm.java
│   ├── AuditPayload.java
│   ├── AuditError.java
│   ├── AuditController.java
│   └── AuditAdvice.java
└── src/test/java/demo/verify/
    ├── VersionEvidenceTest.java
    ├── DataBinderEvidenceTest.java
    └── MvcEvidenceTest.java
```

### 12.2. `pom.xml` — Intact, Without Overriding Spring Framework

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>spring-version-evidence</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-validation` is essential for `@Valid` and `@Min` to run via a Jakarta Validation provider. Never add `spring-webmvc:7.x` directly to the project. When upgrading, change the Boot parent/BOM in one place and re-run both the dependency tree and the test suite.

### 12.3. `VersionEvidenceApplication.java`

```java
package demo.verify;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VersionEvidenceApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionEvidenceApplication.class, args);
    }
}
```

### 12.4. `AuditForm.java` — Mutable Bean to Observe Data Binding

```java
package demo.verify;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class AuditForm {

    @NotBlank
    private String name;

    @NotNull
    @Min(1)
    private Integer seats;

    // Intentionally exposed so tests can prove the over-posting risk.
    private boolean approved;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public boolean isApproved() {
        return approved;
    }

    public void setApproved(boolean approved) {
        this.approved = approved;
    }
}
```

**Production note:** A real input DTO should not have an `approved` setter. This file keeps it **intentionally** to compare default property binding against allowlisted binding. Real applications should separate server-owned state from request inputs at the class design level.

### 12.5. `AuditPayload.java` — JSON DTO

```java
package demo.verify;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AuditPayload(
        @NotBlank String title,
        @NotNull @Min(1) Integer quantity) {
}
```

The record is constructed by Jackson from JSON. `@Valid` on the handler argument triggers Bean Validation after reading the body. This **differs** from `DataBinder#setAllowedFields` for forms.

### 12.6. `AuditError.java` — Minimal Response Contract

```java
package demo.verify;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

import java.util.List;

public record AuditError(
        String code,
        List<String> fields) {

    public static AuditError simple(String code) {
        return new AuditError(code, List.of());
    }

    public static AuditError fromBindingResult(BindingResult errors) {

        boolean bindingFailure = errors.getFieldErrors()
                .stream()
                .anyMatch(FieldError::isBindingFailure);

        List<String> fields = errors.getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new AuditError(
                bindingFailure
                        ? "BINDING_ERROR"
                        : "VALIDATION_ERROR",
                fields);
    }
}
```

The demo contract never reflects raw rejected values, exception messages, or stack traces. If object-level errors exist in a real application, map `getGlobalErrors()` as well; this example declares only field-level Jakarta constraints.

### 12.7. `AuditController.java` — Distinct MVC Paths

```java
package demo.verify;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.core.SpringVersion;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;
import java.util.Objects;

@RestController
@RequestMapping("/audit")
public class AuditController {

    @InitBinder("auditForm")
    void restrictForm(WebDataBinder binder) {
        binder.setAllowedFields("name", "seats");
    }

    @GetMapping("/version")
    public Map<String, String> version() {
        return Map.of(
                "springFramework",
                Objects.toString(
                        SpringVersion.getVersion(), "unknown"));
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("auditForm") AuditForm form,
            BindingResult errors) {

        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(AuditError.simple("SUPPRESSED_FIELDS"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(AuditError.fromBindingResult(errors));
        }

        return ResponseEntity.ok(Map.of(
                "name", form.getName(),
                "seats", form.getSeats(),
                "approved", form.isApproved()));
    }

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<?> json(
            @Valid @RequestBody AuditPayload payload) {

        return ResponseEntity.ok(Map.of(
                "title", payload.title(),
                "quantity", payload.quantity()));
    }

    @GetMapping("/limit")
    public Map<String, Integer> limit(
            @RequestParam("limit") Integer limit) {

        return Map.of("limit", limit);
    }

    @GetMapping("/page")
    public Map<String, Integer> page(
            @RequestParam("page") @Min(1) int page) {

        return Map.of("page", page);
    }

    @NotNull
    @GetMapping("/broken-return")
    public String brokenReturn() {
        // Fixture intentionally violating the return-value contract.
        return null;
    }
}
```

**Testability notes:**
- `@InitBinder("auditForm")` targets only the form's model attribute name.
- `BindingResult` sits **immediately after** `AuditForm`.
- `getSuppressedFields()` is checked separately before `hasErrors()`.
- `/json` uses `@Valid @RequestBody` with no direct method constraint on parameters.
- `/page` uses direct `@Min(1)` and omits class-level `@Validated`.
- `/broken-return` is an **intentionally invalid** test fixture, never for production use. `HandlerMethodValidationException` Javadoc maps return-value errors to HTTP 500.

When Spring Security is present, supply proper authenticated test requests instead of disabling security merely to turn 401/403 into 400. The demo project declares no Spring Security dependency.

### 12.8. `AuditAdvice.java` — Matching Exact `ResponseEntityExceptionHandler` Signatures

```java
package demo.verify;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.List;

@RestControllerAdvice
public class AuditAdvice extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> reply(
            HttpHeaders headers,
            HttpStatusCode status,
            AuditError body) {

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                AuditError.fromBindingResult(ex.getBindingResult()));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                AuditError.simple("BODY_UNREADABLE"));
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                new AuditError(
                        "MISSING_PARAMETER",
                        List.of(ex.getParameterName())));
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (status.is5xxServerError()) {
            return reply(headers, status,
                    AuditError.simple("SERVER_CONVERSION_ERROR"));
        }

        String field =
                ex instanceof MethodArgumentTypeMismatchException mismatch
                        ? mismatch.getName()
                        : "parameter";

        return reply(headers, status,
                new AuditError("TYPE_MISMATCH", List.of(field)));
    }

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                AuditError.simple(
                        ex.isForReturnValue()
                                ? "RETURN_VALIDATION_ERROR"
                                : "METHOD_VALIDATION_ERROR"));
    }
}
```

Exact for Spring Framework 6.2.11, the overrides above take `HttpStatusCode` and `WebRequest`. If copying a signature from another major version causes the IDE to report “method does not override or implement a method from a supertype”, verify:
1. Exceptions are imported from the right package.
2. `ResponseEntityExceptionHandler` Javadoc for the **resolved Spring Framework patch**.
3. `@Override` matches exact signature, parameter order, and visibility.
4. Do not add an `@ExceptionHandler` colliding with a mapping already present on the superclass.

**Why not force everything to 400?** `HandlerMethodValidationException` distinguishes input vs return value. The demo preserves the `status` passed in by Spring, avoiding turning server errors into client errors.

## 13. JUnit Evidence: Versions and API Signatures

### 13.1. `VersionEvidenceTest.java`

```java
package demo.verify;

import org.junit.jupiter.api.Test;
import org.springframework.core.SpringVersion;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class VersionEvidenceTest {

    @Test
    void runtimeSpringFrameworkVersionMatchesManagedBaseline() {
        assertEquals("6.2.11", SpringVersion.getVersion());
    }

    @Test
    void dataBinderApisExistWithDocumentedSignatures()
            throws Exception {

        assertNotNull(DataBinder.class.getMethod(
                "setDeclarativeBinding", boolean.class));
        assertNotNull(DataBinder.class.getMethod(
                "setAllowedFields", String[].class));
        assertNotNull(DataBinder.class.getMethod(
                "setAutoGrowCollectionLimit", int.class));
        assertNotNull(BindingResult.class.getMethod(
                "getSuppressedFields"));
    }

    @Test
    void exceptionHandlerOverrideSignatureMatchesExactPatch()
            throws Exception {

        assertNotNull(
                ResponseEntityExceptionHandler.class
                        .getDeclaredMethod(
                                "handleHandlerMethodValidationException",
                                HandlerMethodValidationException.class,
                                HttpHeaders.class,
                                HttpStatusCode.class,
                                WebRequest.class));
    }
}
```

**Limitations of reflection tests:** They prove the methods exist with exact signatures on loaded classes. They **do not** prove the implementation works in every case, prove no bugs exist, or guarantee how source docs were published. Those require the subsequent unit/MockMvc tests.

### 13.2. Should Every Project Assert an Exact Runtime Version?

For a **fixed-baseline hands-on exercise**, yes—the test fails early if the BOM is bumped/overridden, forcing you to update Javadoc evidence. For continuously upgraded production systems, you can:
- Print the runtime version into test reports.
- Compare major/minor per organization policy.
- Use dependency locking or an SBOM to pin resolved artifacts.
- Update version-specific tests inside deliberate upgrade PRs.

Do not keep `"6.2.11"` hardcoded forever when intentionally upgrading Boot and Framework. That is the lesson's baseline, not a security recommendation to stay on an old patch indefinitely.

## 14. JUnit Evidence: Direct `DataBinder`, Without MVC

### 14.1. `DataBinderEvidenceTest.java`

```java
package demo.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DataBinderEvidenceTest {

    private static MutablePropertyValues values() {
        MutablePropertyValues data = new MutablePropertyValues();
        data.add("name", "Mai");
        data.add("seats", "2");
        data.add("approved", "true");
        return data;
    }

    @Test
    void defaultPropertyBindingCanSetASetter() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");

        binder.bind(values());

        assertEquals("Mai", form.getName());
        assertEquals(Integer.valueOf(2), form.getSeats());
        assertTrue(form.isApproved());
    }

    @Test
    void allowlistPreventsUnexpectedSetterMutation() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setAllowedFields("name", "seats");

        binder.bind(values());

        assertEquals("Mai", form.getName());
        assertEquals(Integer.valueOf(2), form.getSeats());
        assertFalse(form.isApproved());
        assertEquals("approved",
                binder.getBindingResult()
                        .getSuppressedFields()[0]);
    }

    @Test
    void suppressedFieldDoesNotAutomaticallyRegisterError() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setAllowedFields("name", "seats");

        binder.bind(values());

        assertEquals(1,
                binder.getBindingResult()
                        .getSuppressedFields().length);
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void declarativeModeWithoutAllowedFieldsSkipsSetters() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setDeclarativeBinding(true);

        binder.bind(values());

        assertNull(form.getName());
        assertNull(form.getSeats());
        assertFalse(form.isApproved());
    }

    @Test
    void declarativeModeWithAllowlistPermitsOnlySelectedProperties() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setDeclarativeBinding(true);
        binder.setAllowedFields("name", "seats");

        binder.bind(values());

        assertEquals("Mai", form.getName());
        assertEquals(Integer.valueOf(2), form.getSeats());
        assertFalse(form.isApproved());
        assertEquals(1,
                binder.getBindingResult()
                        .getSuppressedFields().length);
    }

    @Test
    void autoGrowDefaultMatchesExactJavadoc() {
        DataBinder binder = new DataBinder(new AuditForm());

        assertEquals(256, binder.getAutoGrowCollectionLimit());
        assertEquals(
                DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT,
                binder.getAutoGrowCollectionLimit());
    }

    @Test
    void wrongIntegerValueProducesBindingFieldError() {
        AuditForm form = new AuditForm();
        DataBinder binder = new DataBinder(form, "auditForm");
        binder.setAllowedFields("name", "seats");

        MutablePropertyValues data = new MutablePropertyValues();
        data.add("name", "Mai");
        data.add("seats", "abc");

        binder.bind(data);

        assertTrue(binder.getBindingResult()
                .hasFieldErrors("seats"));
        assertNotNull(binder.getBindingResult()
                .getFieldError("seats"));
        assertTrue(binder.getBindingResult()
                .getFieldError("seats").isBindingFailure());
        assertEquals("typeMismatch",
                binder.getBindingResult()
                        .getFieldError("seats").getCode());
    }
}
```

These unit tests **do not spin up a Spring `ApplicationContext`**. They provide evidence for `DataBinder`, not for the full Jackson pipeline, argument resolvers, or Servlet container.

The sample does not call `binder.validate()` or register a Bean Validation provider on the binder manually. Thus `suppressedFieldDoesNotAutomaticallyRegisterError` does not test `@NotBlank`/`@Min`: it shows only that suppression **does not automatically produce an error** on an otherwise valid bind. Validation is tested via MockMvc.

## 15. MockMvc Evidence: What Actually Happens in Spring MVC?

### 15.1. `MvcEvidenceTest.java`

```java
package demo.verify;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import static org.hamcrest.Matchers.hasItem;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcEvidenceTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequestBuilder form() {
        return post("/audit/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Mai")
                .param("seats", "2");
    }

    @Test
    void versionEndpointShowsRuntimeFrameworkVersion()
            throws Exception {

        mvc.perform(get("/audit/version"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.springFramework")
                        .value("6.2.11"));
    }

    @Test
    void validFormIsBoundThroughWebDataBinder() throws Exception {
        mvc.perform(form())
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Mai"))
                .andExpect(jsonPath("$.seats").value(2))
                .andExpect(jsonPath("$.approved").value(false));
    }

    @Test
    void nonAllowlistedPropertyIsSuppressed()
            throws Exception {

        mvc.perform(form().param("approved", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("SUPPRESSED_FIELDS"));
    }

    @Test
    void wrongFormTypeIsBindingErrorNotConstraintError()
            throws Exception {

        mvc.perform(form().param("seats", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.fields[*]",
                        hasItem("seats")));
    }

    @Test
    void zeroSeatsIsValidationError() throws Exception {
        mvc.perform(form().param("seats", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.fields[*]",
                        hasItem("seats")));
    }

    @Test
    void blankNameIsValidationError() throws Exception {
        mvc.perform(form().param("name", "  "))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.fields[*]",
                        hasItem("name")));
    }

    @Test
    void validJsonDtoIsDeserializedThenUsed() throws Exception {
        mvc.perform(post("/audit/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"Book","quantity":2}
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("Book"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void invalidJsonDtoUsesArgumentValidation() throws Exception {
        mvc.perform(post("/audit/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"title":"","quantity":2}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void malformedJsonUsesMessageReadingError() throws Exception {
        mvc.perform(post("/audit/json")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"))
                .andExpect(result -> assertInstanceOf(
                        HttpMessageNotReadableException.class,
                        result.getResolvedException()));
    }

    @Test
    void missingQueryParameterUsesPresenceError()
            throws Exception {

        mvc.perform(get("/audit/limit"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(result -> assertInstanceOf(
                        MissingServletRequestParameterException.class,
                        result.getResolvedException()));
    }

    @Test
    void wrongQueryTypeUsesConversionError() throws Exception {
        mvc.perform(get("/audit/limit")
                        .param("limit", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentTypeMismatchException.class,
                        result.getResolvedException()));
    }

    @Test
    void validDirectMethodConstraintPasses() throws Exception {
        mvc.perform(get("/audit/page").param("page", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1));
    }

    @Test
    void directMinTriggersHandlerMethodValidation()
            throws Exception {

        mvc.perform(get("/audit/page").param("page", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }

    @Test
    void returnConstraintFailureIsServerError()
            throws Exception {

        mvc.perform(get("/audit/broken-return"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("RETURN_VALIDATION_ERROR"))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }
}
```

When `/audit/page?page=0` passes, you have evidence that **MVC 6.2.11** uses `HandlerMethodValidationException` in a setup without class-level `@Validated`. It **does not** prove service method validation via AOP throws that exact same exception.

When `/audit/json` with a blank title passes, you have evidence that `@Valid @RequestBody` and the validation provider work in the project. It does not prove `@InitBinder#setAllowedFields` restricted JSON fields.

When `/audit/form` sending `approved=true` passes with code `SUPPRESSED_FIELDS`, you have evidence that the controller **chose to reject** after reading `getSuppressedFields()`. Spring `DataBinder` supplies only suppression metadata; returning HTTP 400 is the application's policy.

## 16. Running, Saving Evidence, and Reporting Versions

### 16.1. Commands

In `spring-version-evidence`:

```bash
java -version
mvn -version
mvn dependency:tree -Dincludes=org.springframework
mvn test
```

Run a single class:

```bash
mvn -Dtest=VersionEvidenceTest test
mvn -Dtest=DataBinderEvidenceTest test
mvn -Dtest=MvcEvidenceTest test
```

Start the server:

```bash
mvn spring-boot:run
```

**This Markdown document has not executed Maven.** Assertions in the code are **sample expectations against the pinned dependency baseline**. Treat them as “PASSED” only after running `mvn test` and checking actual reports, never projecting console output as evidence.

JUnit tests per listing:
- `VersionEvidenceTest`: 3 `@Test` methods.
- `DataBinderEvidenceTest`: 7 `@Test` methods.
- `MvcEvidenceTest`: 14 `@Test` methods.
- **Total: 24 test methods**.

When running Maven Surefire, check `target/surefire-reports` for total discovered tests, failures, errors, and skips. If the project adds tests, the total changes; never treat the count in an article as a fixed KPI.

### 16.2. Testing with curl

```bash
curl -i 'http://localhost:8080/audit/version'
curl -i 'http://localhost:8080/audit/limit?limit=abc'
curl -i 'http://localhost:8080/audit/page?page=0'
```

With the baseline version, the first route returns JSON:

```json
{"springFramework":"6.2.11"}
```

Valid form:

```bash
curl -i -X POST \
  'http://localhost:8080/audit/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Mai' \
  --data-urlencode 'seats=2'
```

Expect 200 with data:

```json
{"name":"Mai","seats":2,"approved":false}
```

Form with blocked field:

```bash
curl -i -X POST \
  'http://localhost:8080/audit/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Mai' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'approved=true'
```

Expect 400:

```json
{"code":"SUPPRESSED_FIELDS","fields":[]}
```

JSON violating constraint:

```bash
curl -i -X POST \
  'http://localhost:8080/audit/json' \
  -H 'Content-Type: application/json' \
  -d '{"title":"","quantity":2}'
```

Expect 400 with `code="VALIDATION_ERROR"` and `fields` containing `title`. Malformed JSON returns `BODY_UNREADABLE`, not an `@NotBlank` error.

### 16.3. Suggested Evidence Log After Running

```text
Project: spring-version-evidence
Java: <record java -version output>
Boot parent: 3.5.6
Resolved Spring Framework: <record dependency:tree output>
Runtime SpringVersion: <record GET /audit/version>
Javadoc exact patch: Spring Framework 6.2.11
Reference Guide series: 6.2 (banner patch: <record at review time>)
Test command: mvn test
Surefire result: <actual tests/failures/errors/skips>
Verdict: <PASS/FAILED/INVESTIGATE>
Source tag: v6.2.11
```

The `<...>` placeholders are a **template to fill in during hands-on practice**, not program output, not other spreadsheet cells, and not a claim that tests ran. When producing a real report, never store source IPs, passwords, or credentials from CI machines.

## 17. When Results Do Not Match Docs: Case-by-Case Handling

### 17.1. `NoSuchMethodError` Even Though the IDE Compiles

Compilation may use the Spring 6.2 API while runtime loads an older jar. Check:
- `mvn dependency:tree` and effective POM.
- Fat jar contents and container classpath if deployed.
- `SpringVersion.getVersion()` at actual runtime.
- `CodeSource` of the class, e.g., `DataBinder.class.getProtectionDomain().getCodeSource().getLocation()` (if security policy allows).
- Runtime startup scripts, plugin loaders, tests, and shading.

`NoSuchMethodError` is usually a linkage/classpath mismatch; never jump to concluding the method was removed from the framework.

### 17.2. `@Override` Fails to Compile

You may have copied a signature from another patch's Javadoc or mistakenly imported `HttpStatus` instead of `HttpStatusCode`. For `ResponseEntityExceptionHandler`, check **every parameter of the method signature**, especially variations across major/minor releases. The demo's 6.2.11 Javadoc for `handleHandlerMethodValidationException` takes:
- `HandlerMethodValidationException`.
- `HttpHeaders`.
- `HttpStatusCode`.
- `WebRequest`.

Never delete `@Override` to “make the error go away”: doing so can turn an intended override into an overload that the framework never calls.

### 17.3. `getSuppressedFields()` Is Empty Despite an Unknown Request Field

Possible reasons:
- Constructor binding is active instead of property field allowlisting.
- `@InitBinder` does not match the model attribute name.
- `@RequestBody` JSON via Jackson is being used.
- The client sent a field without a setter and the binder ignored unknown fields.
- Declarative binding is enabled so property binding did not run.
- Field path canonicalization/casing differs from expectations.

Run a pure `DataBinder` test first, then compare the controller binding setup. Never use `getSuppressedFields` as a “universal unknown-key detector” for all input paths.

### 17.4. `@Valid` Has No Effect

Check:
- `spring-boot-starter-validation` and actual provider.
- Annotation imports `jakarta.validation.Valid` (Spring Boot 3/Spring Framework 6).
- Constraint annotations placed properly on fields/record components.
- Is `BindingResult` immediately after the argument and the controller ignoring errors?
- Is a direct method constraint shifting the handling path?
- Does the test context auto-configure the validator?

Never copy `javax.validation.*` from Spring Boot 2 examples into Boot 3 when code needs `jakarta.validation.*`.

### 17.5. `@Min` Throws a Different Exception Than Expected

If `@Validated` is on the controller class, AOP proxy-based validation can alter the path. If the Spring Framework version is below 6.1, built-in method validation does not match the baseline. Cross-check the 6.2 Guide, Javadoc `HandlerMethodValidationException` 6.2.11, and test with the smallest possible controller signature.

### 17.6. Reflection Tests Pass, but HTTP Tests Fail

A method signature existing does not guarantee:
- The bean is registered with Spring MVC.
- A validation provider is on the classpath.
- Filters/security did not reject the request before the controller.
- Formatters/converters are ready.
- Global advice was component-scanned.
- Error status/schema matches expectations.

Reflection is **API presence evidence**; MockMvc is **runtime integration evidence**.

### 17.7. Newer Patch Explains Different Behavior

If Spring Boot is upgraded to a newer 3.5.x patch, the resolved version may be a newer Spring 6.2.x patch. You should:
1. Record old and new versions.
2. Check release notes/bug fixes instead of assuming “same minor guarantees identical behavior”.
3. Open Javadoc and source tag for the new patch.
4. Run the regression suite on both old and new baselines if feasible.
5. Update statements/tests if a change is proven intentional.
6. Never change the compiler target merely to silence a Java API import error from copying Spring 7 snippets.

## 18. Common Mistakes When Consulting Documentation

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| Searching “Spring DataBinder Javadoc” and opening `latest` | `latest` may differ from the running binary | Use only `docs/6.2.11/javadoc-api` for the baseline |
| Seeing Boot 3.5.6 and looking up Framework 3.5.6 | Two distinct release lines | Get resolved version from dependency tree |
| Using `/reference/6.2` and claiming it is 6.2.11 | Series docs can show a newer 6.2.x patch | Note banner patch and use exact Javadoc |
| Copying `setDeclarativeBinding` from 6.2 into a 6.0 app | API is `Since 6.1` | Check `Since` |
| Ignoring “used for setter/field injection” | Applying auto-grow limit to constructor binding out of scope | Read 6.2.11 Method Details |
| Seeing `hasErrors()==false` and claiming no unknown input | Suppression is reported separately | Read `getSuppressedFields` |
| Seeing 400 and labeling it “`@Valid` failed” | 400 can be conversion/JSON/method validation | Check resolved exception and `FieldError` |
| Using Spring WebFlux docs for Servlet MockMvc | Both stacks have distinct exception/validation paths | Pick MVC section, not Reactive |
| Removing `@Override` to silence compile error | May silently lose handler override | Check exact signature |
| Running only unit tests and skipping MockMvc | Fails to test MVC pipeline | Add web-layer tests |
| Running only MockMvc and skipping `DataBinder` unit tests | Hard to isolate root cause | Keep both layers |
| Seeing immutable Java record and thinking binder cannot over-post | Constructor args are still client-supplied | Keep only public input fields in DTO |
| Copying `javax.validation.` from Boot 2 | Spring 6/Boot 3 use Jakarta | Switch to `jakarta.validation` |
| Overriding `spring-framework.version` just to compile | Can break Boot-managed compatibility | Avoid overriding without strong reason/tests |
| Guessing compiler/plugin versions | Effective build has inheritance/overrides | Inspect effective POM |
| Running tests without recording environment | Cannot reproduce on CI | Record Java/Maven/Boot/Framework |
| Calling observed behavior a public guarantee | May be an implementation detail | Classify claims by evidence level |
| Exposing raw exception messages in API | Can leak request values, internal details | Use stable machine error codes |

## 19. End-of-Lesson Practice Checklist

1. Identified Maven vs Gradle?
2. Recorded the exact Boot parent/BOM version?
3. Obtained resolved Spring Framework version from the dependency tree?
4. Compared runtime `SpringVersion.getVersion()`?
5. Opened Javadoc for the exact **major.minor.patch**?
6. Recorded `Since` for every API under discussion?
7. Verified exact signatures and package imports?
8. Read defaults and “applies to/used for” in Method Details?
9. Separated property binding from constructor binding?
10. Separated form/query binder from JSON/Jackson?
11. Separated Bean Validation from conversion errors?
12. Checked `BindingResult.getSuppressedFields()` separately?
13. Verified `@InitBinder` attribute name matches the model?
14. Noted presence/absence of class-level `@Validated`?
15. Checked the right MVC stack instead of WebFlux?
16. Verified input 400 vs return 500 exception statuses?
17. Wrote pure `DataBinder` unit tests for method scope?
18. Wrote MockMvc tests for HTTP behavior?
19. Asserted error codes/fields, not just HTTP status?
20. Recorded build/runtime versions when tests ran?
21. Checked the Reference Guide series banner patch?
22. Checked release notes if Javadoc/test differed?
23. Read source at the **exact tag** when deep analysis was needed?
24. Avoided overriding the BOM just to “make an example run”?
25. Recorded actual results rather than claiming unexecuted tests passed?
26. Scoped conclusions clearly and noted unproven points?
27. Kept an upgrade test to catch API signature drift?
28. Prevented example-only vulnerable DTOs from leaking into production?

## 20. Extension Exercises

1. Upgrade Spring Boot **on a separate test branch only**, run `dependency:tree`, and record the new version without guessing.
2. Update the `DataBinder` Javadoc link from 6.2.11 to the newly resolved version; compare `Since` and scope of three methods.
3. Write another test for `setAutoGrowNestedPaths(false)` in property binding; state the null nested input and expectation.
4. Create a constructor-binding record containing a List, verifying why `setAutoGrowCollectionLimit` is not a quota for constructor binding.
5. Add `@BindParam` to a constructor argument on Spring 6.2, check `Since`, and test form aliases without confusing Jackson.
6. Switch `@Valid @RequestBody` to a handler with a direct `@Min` constraint and observe the validation exception path.
7. Add `@Validated` to a controller class **in a dedicated test configuration** and compare AOP vs built-in MVC validation.
8. Write a Bean Validation test for a nested object with `@NotNull @Valid` and record the exact error path.
9. Change `setAllowedFields` from `"name"` to an overly broad wildcard and find an input that can over-post.
10. Add a strict HTTP form parameter allowlist and compare it against `getSuppressedFields`; do not treat them as equivalent.
11. Write a `ResponseEntityExceptionHandler` test returning RFC 9457 `ProblemDetail` instead of custom `AuditError`.
12. Compare `@RequestBody` unknown JSON properties against `@ModelAttribute` unknown form fields, reading docs for both stacks carefully.
13. Add a Gradle build using `dependencyInsight` and compare resolved dependencies with the Maven build.
14. Build an API signature diff table when upgrading Framework 6.x to 7.x to locate compile fixes needed.
15. Test against a real HTTP server alongside MockMvc when a bug reproduces only with a proxy/container.
16. Run `javap` on the actual dependency jar to verify bytecode signatures when Javadoc, IDE, and runtime disagree.
17. Compare `DataBinder#setIgnoreUnknownFields(false)` Javadoc with constructor binding; prove the documented boundary.
18. Use the source tag to find the body of `shouldNotBindPropertyValues()` and classify it as an internal implementation detail vs public contract.
19. Add SBOM/dependency locking to the pipeline and report version drift periodically.
20. Set up a CI job running tests on both the old baseline and upgrade candidate, outputting a PASS/FAIL table with commit/tag.

**Conclusion:** A Spring observation is only reliably explained once you can answer **“Which version is running, which stack owns the API, what does the exact-patch Javadoc say, which Reference Guide branch applies, and how do tests reproduce it?”** The hands-on baseline Spring Boot 3.5.6 resolves Spring Framework 6.2.11; verify via the dependency tree and at runtime. Then read **Method Details** (defaults, `Since`, constructor vs property scope), write `DataBinder` unit tests and `MockMvc` integration tests, and record evidence instead of guessing. This workflow is reusable for any binding or validation issue during Spring upgrades.

## 21. Official and Versioned Reference Sources

1. [Maven Central — Spring Boot starter-web 3.5.6 dependencies](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-web/3.5.6).
2. [Spring Framework 6.2.11 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/DataBinder.html).
3. [Spring Framework 6.2.11 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/validation/BindingResult.html).
4. [Spring Framework 6.2.11 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html).
5. [Spring Framework 6.2.11 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.11/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html).
6. [Spring Framework 6.2 Reference — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beans-beans.html).
7. [Spring Framework 6.2 Reference — @InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html).
8. [Spring Framework 6.2 Reference — @ModelAttribute](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html).
9. [Spring Framework 6.2 Reference — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html).
10. [Spring Framework 6.2.11 official release](https://spring.io/blog/2025/09/11/spring-framework-6-2-11-available%20now/).
11. [Spring Framework source v6.2.11](https://github.com/spring-projects/spring-framework/tree/v6.2.11).
12. [Spring Boot source v3.5.6](https://github.com/spring-projects/spring-boot/tree/v3.5.6).
13. [Spring Boot 3.5 — Build Systems](https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html).
14. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
15. [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html).