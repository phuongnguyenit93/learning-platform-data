# Javadoc for Records, Sealed Types, and API Contracts in Java 17

**Topic:** Java 17 → Compilation and Documentation  
**Focus:** Writing Javadoc for record components, sealed classes/interfaces, and API contracts; understanding what the standard doclet generates automatically, how to document input/output preconditions, exceptions, and mutability, and how to configure extra tags when generating docs with JDK 17.

Javadoc is documentation attached directly to source declarations. The `javadoc` tool reads source code and documentation comments to produce HTML API documentation. In Java 17, the standard doclet understands records and sealed types: it generates a **Record Components** section for records and a **Permitted Subclasses** section for sealed classes or interfaces. Documentation authors are responsible for describing the business meaning of each component, the permitted subtypes, and the contracts API users can rely on.

Good Javadoc answers practical questions: what the object represents, which arguments are valid, whether results can be null, whether returned collections are modifiable, which exceptions are thrown and under what conditions, whether a method has side effects, whether ordering is guaranteed, and which behaviors are public commitments. Contract descriptions must state what callers can depend on; implementation details should be documented separately only when genuinely needed.

## 1. Javadoc in the API development workflow

A documentation comment is placed immediately before the declaration it documents:

~~~java
/**
 * Returns the current account balance.
 *
 * @return the balance in the account's currency
 */
public BigDecimal balance() {
    return balance;
}
~~~

Standard Javadoc typically has two parts:

1. **Main description:** the first sentence should be a concise, complete summary; subsequent paragraphs explain context and behavior.
2. **Block tags:** supply structured metadata such as `@param`, `@return`, `@throws`, `@since`, `@deprecated`, and `@see`.

The standard doclet generates HTML pages from source code. Generated documentation can include module, package, class, constructor, method, and record component pages, lists of permitted subtypes, cross-links, and a search index. Therefore, Javadoc should describe the API at the level a library consumer needs, rather than repeating method names or internal implementation notes.

### 1.1. Writing meaningful summary sentences

Good example:

~~~java
/**
 * Returns an immutable snapshot of the configured roles.
 */
public List<String> roles() {
    return roles;
}
~~~

Poor example:

~~~java
/**
 * Gets roles.
 */
public List<String> roles() {
    return roles;
}
~~~

"Gets" fails to clarify whether the return value is a snapshot or a live view, whether it is modifiable, or which roles it includes. A good summary sentence states behavior meaningful to callers.

In JDK 17, `{@summary ...}` can explicitly delimit the summary if you do not want the standard doclet to rely solely on the first sentence. Even so, a clear first sentence remains the most readable choice for most APIs.

## 2. Javadoc for records

A record is suited for representing a fixed-structure tuple of values. Each component is declared directly in the record header:

~~~java
public record CustomerId(String value) {
}
~~~

The compiler generates corresponding members:

- A `private final` field for each component.
- A public accessor with the same name as the component, e.g., `value()`.
- A canonical constructor accepting components in declaration order.
- Default implementations of `equals`, `hashCode`, and `toString`.

Record Javadoc must explain the purpose of the record and each component. In JDK 17's standard doclet, `@param` tags on the record's documentation comment render under the **Record Components** section. Those descriptions are also reused for parameters of the automatically generated canonical constructor.

### 2.1. Documenting each record component with @param

~~~java
import java.util.List;
import java.util.Objects;

/**
 * Represents a snapshot of a customer's public profile.
 *
 * <p>The role list is copied when the record is constructed, so changes
 * to the caller's original list are not reflected in this value.
 *
 * @param id the stable customer identifier; must not be blank
 * @param displayName the name shown to users; must not be null
 * @param roles the roles assigned to the customer; the list and its elements must not be null
 * @since 1.0
 */
public record CustomerProfile(
        String id,
        String displayName,
        List<String> roles) {

    public CustomerProfile {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(displayName, "displayName");
        Objects.requireNonNull(roles, "roles");

        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        roles = List.copyOf(roles);
    }
}
~~~

In the generated Javadoc page, `id`, `displayName`, and `roles` appear in the Record Components section. Names in `@param` must match the component names in the record header exactly; misspelling a name triggers Javadoc warnings and prevents attaching the description to the right component.

Each component should be documented with its data meaning, valid range, and null policy. For example, "the roles assigned to the customer" is more helpful than "the roles list" because it explains what the data represents.

### 2.2. Records are shallowly immutable

Records have `final` component fields, which does not automatically make referenced objects immutable. Example:

~~~java
public record Settings(List<String> allowedHosts) {
}
~~~

A caller can still pass an `ArrayList` and mutate that list after constructing the record. The record continues holding a reference to the same list. If the API promises a structural snapshot, perform a defensive copy:

~~~java
public record Settings(List<String> allowedHosts) {
    public Settings {
        allowedHosts = List.copyOf(allowedHosts);
    }
}
~~~

Javadoc should state this policy explicitly. If the list is shallow-copied, mutable elements inside the list can still be shared. Never describe the result as "deeply immutable" when calling only `List.copyOf`.

Accurate description example:

~~~java
/**
 * Represents a set of runtime settings.
 *
 * <p>The constructor makes an unmodifiable shallow copy of
 * {@code allowedHosts}. The elements are not cloned.
 *
 * @param allowedHosts host names accepted by the application
 */
public record Settings(List<String> allowedHosts) {
    public Settings {
        allowedHosts = List.copyOf(allowedHosts);
    }
}
~~~

With `String`, sharing elements is safe because `String` is immutable. If a component is `List<MutableType>`, consider copying individual elements or explicitly documenting shared element references.

### 2.3. Documenting the canonical constructor

If a record defines a compact canonical constructor to validate or normalize values, you can write Javadoc directly on that constructor:

~~~java
/**
 * Creates a customer profile after validating and copying its values.
 *
 * @param id the stable customer identifier
 * @param displayName the display name
 * @param roles the roles to copy into the profile; the list and its elements must not be null
 * @throws NullPointerException if an argument or a role element is null
 * @throws IllegalArgumentException if {@code id} is blank
 */
public CustomerProfile {
    Objects.requireNonNull(id, "id");
    Objects.requireNonNull(displayName, "displayName");
    Objects.requireNonNull(roles, "roles");
    if (id.isBlank()) {
        throw new IllegalArgumentException("id must not be blank");
    }
    roles = List.copyOf(roles);
}
~~~

When documenting both the record type and its canonical constructor, avoid mechanically repeating text. The record comment should explain the overall concept and components; the constructor comment should focus on validation, normalization, defensive copying, and exceptions callers may encounter.

### 2.4. Default accessors and custom accessors

Javadoc for a compiler-generated accessor automatically states that it returns the value of the record component. If an accessor has custom behavior, such as returning a defensive copy or computing a derived view, declare it explicitly and write dedicated Javadoc:

~~~java
public record Report(List<String> lines) {
    public Report {
        lines = List.copyOf(lines);
    }

    /**
     * Returns the report lines in their original order.
     *
     * @return an unmodifiable list of report lines
     */
    public List<String> lines() {
        return lines;
    }
}
~~~

Add custom accessors only when changing or clarifying behavior. For simple default accessors, documenting the component on the record declaration is usually sufficient.

## 3. Javadoc for sealed classes and sealed interfaces

Sealed classes/interfaces restrict which types may directly extend or implement them. Starting in Java 17, sealed classes are a finalized language feature requiring no preview flags.

Example:

~~~java
/**
 * A geometric shape whose direct implementations are controlled by this API.
 *
 * <p>Use the permitted types to represent supported shape categories.
 */
public sealed interface Shape
        permits Circle, Rectangle, Polygon {

    double area();
}
~~~

Each permitted subtype must directly extend/implement the sealed type and continue the sealing policy with exactly one of three modifiers:

- `final`: prohibits further subclassing.
- `sealed`: further restricts permitted subtypes.
- `non-sealed`: reopens inheritance to other types.

A record is implicitly final, so it can serve as a permitted subtype without writing `final`.

All permitted subtypes must belong to the same named module as the sealed type. If the sealed type resides in the unnamed module, all permitted subtypes must be in the same package. When all subtypes are declared in the same compilation unit, the `permits` clause may be omitted for compiler inference; Javadoc can still display the permitted subtype list.

### 3.1. Javadoc automatically generates Permitted Subclasses

JDK 17's standard doclet recognizes sealed types and generates a **Permitted Subclasses** section in the documentation page. The list is derived from the sealed type's source/class metadata.

`permits` is a **Java syntax clause**, not a Javadoc block tag. JDK 17's standard doclet does not define a standard `@permits` tag. Do not write `@permits` assuming it behaves like `@param` or `@throws`.

Recommended style:

~~~java
/**
 * Describes a supported payment method.
 *
 * <p>The API currently supports card payments and bank transfers.
 * Each permitted subtype defines its own payment data and validation rules.
 *
 * @see CardPayment
 * @see BankTransfer
 * @since 1.0
 */
public sealed interface PaymentMethod
        permits CardPayment, BankTransfer {
}
~~~

The doclet-generated Permitted Subclasses section lists `CardPayment` and `BankTransfer`; the main description explains the domain meaning of the hierarchy. Use `@see` or `{@link ...}` to link to subtypes with detailed documentation.

### 3.2. Each permitted subtype also needs its own documentation

~~~java
/**
 * Represents a payment made with a card token.
 *
 * <p>The token is an opaque reference managed by the payment provider.
 *
 * @param token the provider-issued token; must not be blank
 * @param amount the amount to charge; must be positive
 * @see PaymentMethod
 */
public record CardPayment(String token, BigDecimal amount)
        implements PaymentMethod {

    public CardPayment {
        Objects.requireNonNull(token, "token");
        Objects.requireNonNull(amount, "amount");
        if (token.isBlank()) {
            throw new IllegalArgumentException("token must not be blank");
        }
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
~~~

~~~java
/**
 * Represents a payment collected from a bank account.
 *
 * @param iban the account identifier accepted by the payment provider
 * @param amount the amount to collect; must be positive
 * @see PaymentMethod
 */
public record BankTransfer(String iban, BigDecimal amount)
        implements PaymentMethod {
}
~~~

Each subtype should state:

- Which domain variant it represents.
- Its own invariants or constraints.
- Additional data beyond the sealed parent.
- Which behaviors are inherited versus variant-specific.

Do not rely solely on the permitted subclasses list on the parent page. Readers often jump directly to a subtype page from an IDE or API browser.

### 3.3. Multi-level sealed hierarchies

A permitted subtype can itself be sealed:

~~~java
/**
 * Represents a polygonal shape.
 *
 * <p>Only triangle and quadrilateral shapes are supported by this branch.
 */
public sealed interface Polygon extends Shape
        permits Triangle, Quadrilateral {
}
~~~

Leaf subtypes can be `final` records:

~~~java
/**
 * A triangle defined by its three side lengths.
 *
 * @param a the first side length; must be positive
 * @param b the second side length; must be positive
 * @param c the third side length; must be positive
 */
public record Triangle(double a, double b, double c)
        implements Polygon {
}
~~~

`Shape`'s Javadoc page lists direct subtypes; `Polygon`'s page lists `Triangle` and `Quadrilateral`. Documenting the hierarchy level by level clarifies extension boundaries and each branch's responsibilities.

### 3.4. Why is a sealed hierarchy part of the API contract?

The list of permitted subtypes governs API extensibility. Changing this list impacts:

- Client code assuming the existing set of variants.
- Serialization or subtype-based data mapping.
- Plugin and integration libraries.
- Exhaustive handling logic in applications.
- Source/binary compatibility when changing the hierarchy.

In Java 17, pattern matching for `switch` is still a preview feature. When writing documentation for Java 17, do not present pattern switches as finalized features. You can explain that a sealed hierarchy informs callers of the closed subtype set and enables exhaustiveness analysis in supporting tools/languages, while explicitly noting if an example relies on a preview feature.

## 4. Writing clear API contracts

An API contract defines what callers may expect and what implementations must uphold. Public methods should never say merely "Processes data" or "Gets value"; describe observable behavior.

Aspects commonly requiring clarity:

| Aspect | Questions to answer |
| --- | --- |
| Input | Which arguments are required? What is the valid range? Is null accepted? |
| Output | What does the result represent? Can it be null or empty? |
| Mutation | Does the method mutate input objects or receiver state? |
| Ownership | Is a returned collection/array a copy, a view, or an internal reference? Who may modify it? |
| Ordering | Is order guaranteed? |
| Exceptions | What exact conditions trigger exceptions? |
| Side effects | Does it write files, make network calls, update a database, or emit events? |
| Concurrency | Is it thread-safe? How must callers synchronize? |
| Lifecycle | Must resources be closed or methods called in a specific order? |
| Compatibility | Since which version has the API existed? Is it deprecated or scheduled for removal? |

Not every method needs every aspect documented. Document what influences how callers use the API, and avoid turning an accidental implementation detail into a long-term guarantee unless intended.

### 4.1. @param

`@param` documents each parameter by declared name:

~~~java
/**
 * Finds an active customer by its identifier.
 *
 * @param customerId the stable identifier to search for; must not be blank
 */
public Optional<Customer> findActiveCustomer(String customerId) {
    // ...
}
~~~

For generic types, document type parameters enclosed in angle brackets:

~~~java
/**
 * Stores values under unique keys.
 *
 * @param <K> the key type
 * @param <V> the value type
 */
public interface Store<K, V> {
}
~~~

Parameter descriptions should clarify:

- Domain meaning.
- Units for counts, durations, or monetary values.
- Valid value ranges.
- Nullability rules.
- Whether passed collections are read immediately or retained for later use.

Do not repeat the data type already visible in the signature. Instead of `@param count an int`, write `@param count the maximum number of records to return; must be positive`.

### 4.2. @return

`@return` describes the meaning and conditions of the return value:

~~~java
/**
 * Finds an active customer by its identifier.
 *
 * @param customerId the stable identifier to search for
 * @return the matching customer, or an empty result if no active customer exists
 */
public Optional<Customer> findActiveCustomer(String customerId) {
    // ...
}
~~~

Do not write `@return the customer` when the method returns `Optional<Customer>` and callers need to know what happens when nothing matches. When returning a collection, state whether it can be empty, whether order is preserved, and whether callers may mutate it.

### 4.3. @throws

`@throws` must state the conditions triggering the error:

~~~java
/**
 * Parses an ISO date.
 *
 * @param text the date in ISO-8601 format
 * @return the parsed date
 * @throws NullPointerException if {@code text} is null
 * @throws DateTimeParseException if {@code text} is not a valid ISO date
 */
public LocalDate parseDate(String text) {
    return LocalDate.parse(text);
}
~~~

Never list exception names alone. Callers need to know which conditions cause failures so they can validate inputs or handle errors properly. Document unchecked exceptions too when they are a significant part of the contract.

### 4.4. @since

`@since` records the version in which the API appeared:

~~~java
/**
 * Returns the immutable customer snapshot.
 *
 * @since 2.1
 */
public CustomerSnapshot snapshot() {
    // ...
}
~~~

For libraries with their own versioning, use the library version, e.g., `2.1`. Do not automatically write `@since 17` simply because code compiles with Java 17; record the Java version number only when the API genuinely corresponds to that platform version.

### 4.5. @deprecated and the Deprecated annotation

When an API should no longer be used, pair the annotation with Javadoc:

~~~java
/**
 * Loads a customer using the legacy identifier format.
 *
 * @deprecated since 2.0; use {@link #findCustomer(CustomerId)} instead
 */
@Deprecated(since = "2.0", forRemoval = false)
public Customer findCustomer(String legacyId) {
    // ...
}
~~~

`@deprecated` explains why and points to the replacement; `@Deprecated` marks the metadata so compilers and IDEs issue warnings. Set `forRemoval = true` once removal in a future release has been announced.

## 5. Other useful Javadoc tags

| Tag | Purpose | Example |
| --- | --- | --- |
| `@see` | Adds a See Also entry to related APIs. | `@see CustomerId` |
| `{@link ...}` | Inserts an inline link, typically formatted as code. | `Use {@link #close()} before shutdown.` |
| `{@linkplain ...}` | Inserts a link with plain text styling. | `See {@linkplain #close() the close operation}.` |
| `{@code ...}` | Renders code without parsing inner HTML/Javadoc. | `{@code null}` |
| `{@literal ...}` | Renders literal text without interpreting markup. | `{@literal <T>}` |
| `{@inheritDoc}` | Inherits method docs from an overridden/implemented method. | `{@inheritDoc}` |
| `{@summary ...}` | Explicitly defines the summary sentence. | `{@summary Returns a stable identifier.}` |
| `@hidden` | Hides an element from generated API docs. | Use intentionally for non-public APIs. |
| `@author` | Records author when the corresponding option is enabled. | `@author API Team` |

`@param`, `@return`, and `@throws` give documentation structure so IDEs and tools display each section cleanly. `{@link}` is better than plain class names because readers can jump directly to related APIs.

### 5.1. Using @inheritDoc for overridden methods

When implementing an interface or overriding a superclass method, you can inherit the parent contract:

~~~java
public interface CustomerRepository {
    /**
     * Finds a customer by identifier.
     *
     * @param id the stable customer identifier
     * @return the customer, or empty if no matching customer exists
     */
    Optional<Customer> find(CustomerId id);
}

public final class SqlCustomerRepository implements CustomerRepository {
    /**
     * {@inheritDoc}
     */
    @Override
    public Optional<Customer> find(CustomerId id) {
        // ...
    }
}
~~~

The standard doclet can inherit the main description, `@param`, `@return`, and `@throws` of the overridden or implemented method. If the implementation adds extra preconditions, side effects, or restrictions, append them after `{@inheritDoc}`. Do not use `{@inheritDoc}` on constructors or fields because those declarations do not inherit Javadoc via method inheritance.

## 6. @apiNote, @implSpec, and @implNote in JDK 17

Java SE Javadoc often features headings such as:

- **API Note:** notes, examples, or rationale helpful to API callers.
- **Implementation Requirements:** requirements imposed on default or overridable implementations.
- **Implementation Note:** implementation details of a concrete implementation.

The tag names `@apiNote`, `@implSpec`, and `@implNote` appear frequently in JDK documentation. However, in JDK 17 they are **not standard block tags** built into the standard doclet. The OpenJDK docs build registers them as custom tags using `-tag`.

To use these headings in your own project, configure Javadoc accordingly:

~~~shell
javadoc ^
  -tag 'apiNote:a:API Note:' ^
  -tag 'implSpec:a:Implementation Requirements:' ^
  -tag 'implNote:a:Implementation Note:' ^
  -d docs ^
  -sourcepath src ^
  com.example.api
~~~

On Windows Command Prompt, `^` continues lines. In PowerShell, use backticks or write the command on one line. The `-tag name:locations:heading` syntax specifies applicable locations and the rendered heading; `a` means all valid locations.

Without registering these tags, Javadoc reports unknown tags. A custom `Taglet` can also be written and passed via `-taglet`/`-tagletpath` for advanced handling.

### 6.1. Separating contracts from implementation notes

Example:

~~~java
/**
 * Returns an unmodifiable view of the configured endpoints.
 *
 * @apiNote Callers should retain the returned view only while this
 *          configuration remains active.
 * @implSpec The default implementation delegates to the configuration
 *           object and does not make a defensive copy.
 * @implNote This implementation stores endpoints in a LinkedHashMap.
 */
public Map<String, URI> endpoints() {
    // ...
}
~~~

This illustrates how to categorize content once the project registers custom tags. For public APIs, keep mandatory commitments in the main description. Never relegate a critical constraint like "callers must not modify the map" solely to an implementation note.

`@implNote` describes details that can vary by implementation or release. Callers should not treat it as a universal guarantee. `@implSpec` fits when specifying requirements for default implementations or overriding subclasses. `@apiNote` supplies additional guidance for callers without replacing contract text.

## 7. Writing contracts for collections and mutable data

Methods returning `List`, `Set`, `Map`, or arrays should state whether callers may mutate the result and whether it reflects subsequent changes in the source.

Clear contract example:

~~~java
/**
 * Returns an unmodifiable snapshot of the configured roles.
 *
 * <p>The returned list preserves the configured order and does not reflect
 * later changes to this configuration.
 *
 * @return an unmodifiable list containing the roles at the time of the call
 */
public List<String> roles() {
    return List.copyOf(roles);
}
~~~

Example when returning a view:

~~~java
/**
 * Returns an unmodifiable view of the current role mapping.
 *
 * <p>Changes made through this object's update methods are visible in the
 * returned view. The caller cannot modify the mapping through the view.
 *
 * @return an unmodifiable view backed by this configuration
 */
public Map<String, Role> roleView() {
    return Collections.unmodifiableMap(roles);
}
~~~

These two contracts differ distinctly:

| Return strategy | Caller mutates via result | Source mutates after call |
| --- | --- | --- |
| Unmodifiable snapshot | No | Does not reflect later structural changes of mutable source. |
| Unmodifiable view | No | View reflects updates from the backing collection. |
| Mutable copy | Yes | Mutating the result does not affect the source if structure was copied. |
| Direct reference to mutable collection | Possibly | Both caller and owner observe mutations. |

If an API returns a mutable object, document ownership, when data is read, and synchronization rules. Writing "returns a list of roles" does not tell callers whether keeping the list across updates is safe.

## 8. Contracts for thread safety and side effects

An API can be type-safe yet misleading if documentation omits concurrency and side effects.

Thread-safe method example:

~~~java
/**
 * Adds a role to this account.
 *
 * <p>This operation is thread-safe. Concurrent calls are serialized by
 * the account implementation.
 *
 * @param role the role to add; must not be null
 * @return {@code true} if the role was added, or {@code false} if it
 *         was already present
 * @throws NullPointerException if {@code role} is null
 */
public boolean addRole(Role role) {
    // ...
}
~~~

Document "thread-safe" only when truly guaranteed. If callers must synchronize externally, state the lock scope or concurrency rules clearly.

For side effects:

~~~java
/**
 * Persists the account and commits the current transaction.
 *
 * @throws SQLException if the database operation fails
 */
public void save() throws SQLException {
    // ...
}
~~~

If a method performs I/O, mutates state, emits events, consumes a stream, or closes a resource, document every effect callers need to know about. Never hide side effects behind vague names like `process()`.

## 9. Documenting a sealed hierarchy and records together

A domain API might use a sealed interface as its root and records as data variants. Example:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

/**
 * Represents a command that can be submitted to the billing service.
 *
 * <p>The supported command variants are listed in the permitted
 * subclasses section.
 *
 * @see Charge
 * @see Refund
 * @since 1.0
 */
public sealed interface BillingCommand permits Charge, Refund {
    BigDecimal amount();
}

/**
 * Requests a new charge.
 *
 * @param amount the amount to charge; must be positive
 * @param reference the external reference; must not be blank
 */
public record Charge(BigDecimal amount, String reference)
        implements BillingCommand {

    public Charge {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(reference, "reference");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (reference.isBlank()) {
            throw new IllegalArgumentException("reference must not be blank");
        }
    }
}

/**
 * Requests a refund for a previous charge.
 *
 * @param amount the amount to refund; must be positive
 * @param originalReference the reference of the original charge
 */
public record Refund(BigDecimal amount, String originalReference)
        implements BillingCommand {
}
~~~

This example illustrates division of responsibility:

- `BillingCommand` explains the overarching concept and links to variants.
- Generated Javadoc lists permitted subclasses.
- `Charge` and `Refund` explain variant-specific semantics and document record components via `@param`.
- Constructors document validation and exceptions where callers rely on them.

In real projects, each public top-level type normally resides in its own file. These snippets are grouped together for readability; split them into separate files per Java rules when compiling.

## 10. Package and module documentation

Javadoc is not restricted to classes and methods. You can also write:

### 10.1. package-info.java

`package-info.java` describes a package's purpose and shared conventions:

~~~java
/**
 * Provides public billing commands and result types.
 *
 * <p>All monetary values use {@link java.math.BigDecimal}. Public command
 * records validate their required fields during construction.
 *
 * @since 1.0
 */
package com.example.billing.api;
~~~

Package documentation is useful for explaining:

- The package's scope of responsibility.
- Shared naming or validation conventions.
- Nullability and ownership conventions.
- Relationships among key types.
- Typical usage workflows for the package.

### 10.2. module-info.java

In modular applications, place Javadoc before the module declaration:

~~~java
/**
 * Defines the public billing API.
 *
 * <p>The module exports the API package and uses the configured payment
 * provider service.
 *
 * @uses com.example.billing.spi.PaymentProvider
 */
module com.example.billing.api {
    exports com.example.billing.api;
    uses com.example.billing.spi.PaymentProvider;
}
~~~

The `@uses` and `@provides` tags are supported by the standard doclet for module documentation, describing services a module consumes or supplies. Module docs should clarify the module's role, exported packages, and service boundaries integrators must know.

## 11. Running Javadoc with JDK 17

Suppose the source tree is:

~~~text
src/
  com/example/billing/api/
    package-info.java
    BillingCommand.java
    Charge.java
    Refund.java
~~~

Generate documentation:

~~~shell
javadoc --release 17 ^
  -encoding UTF-8 ^
  -Xdoclint:all ^
  -Werror ^
  -d build/docs ^
  -sourcepath src ^
  -tag 'apiNote:a:API Note:' ^
  -tag 'implSpec:a:Implementation Requirements:' ^
  -tag 'implNote:a:Implementation Note:' ^
  -subpackages com.example.billing.api
~~~

The command above uses Windows Command Prompt line continuation with `^`. In PowerShell, use backticks or place it on a single line.

Option meanings:

| Option | Purpose |
| --- | --- |
| `--release 17` | Use Java 17 API/platform release when analyzing sources. |
| `-encoding UTF-8` | Read documentation sources as UTF-8. |
| `-Xdoclint:all` | Enable doc comment and HTML checks across all categories. |
| `-Werror` | Fail with an error if any warnings occur. |
| `-d build/docs` | Output directory for generated HTML. |
| `-sourcepath src` | Root path of source packages. |
| `-tag ...` | Register custom tags such as API Note/Implementation Requirements. |
| `-subpackages ...` | Generate documentation for specified packages and subpackages. |

For modular projects, use `--module-source-path` and `--module` matching the module layout:

~~~shell
javadoc --release 17 ^
  --module-source-path src ^
  --module com.example.billing.api ^
  -d build/docs ^
  -Xdoclint:all
~~~

Depending on project layout, supply additional module paths or source modules as needed. Check `javadoc --help` and `javadoc --help-extra` on your JDK 17 installation to confirm options.

## 12. Doclint and common errors

Doclint catches errors in documentation comments before publication. Common pitfalls:

| Issue | Consequence | Fix |
| --- | --- | --- |
| Missing `@param` on public method | Readers do not know parameter meaning; doclint may warn. | Document every parameter using its exact signature name. |
| Missing `@return` on non-void method | Unclear what the result represents. | State content, null/empty semantics, and mutability. |
| `@throws` omits conditions | Callers do not know when to expect exceptions. | State exact failure conditions. |
| Misspelled `@param` name | Tag fails to bind to parameter/component. | Match tag name to source declaration. |
| Using `@permits` as a standard tag | JDK 17 standard doclet defines no such tag. | Use `permits` in source; describe subtypes in main text and `@see`. |
| Using `@apiNote` without configuring it | Javadoc may report an unknown tag. | Register via `-tag` or supply a Taglet. |
| Invalid HTML | Generated pages render poorly or doclint warns. | Write valid HTML5 and close tags properly. |
| Overly long or vague first sentence | Summary/index entries are hard to scan and search. | Write a short first sentence stating core behavior. |
| Copying superclass Javadoc instead of `{@inheritDoc}` | Docs drift when parent contract changes. | Inherit shared text and append actual differences. |
| Putting implementation details in main contract | Callers accidentally rely on unguaranteed behavior. | Separate public contracts from implementation notes. |

## 13. Javadoc checklist for public APIs

Before publishing an API, verify:

1. Does the summary sentence accurately state the purpose of the type/method?
2. Does every record document all components with `@param`?
3. Do records specify null policy, validation, and defensive copying?
4. Do sealed types explain the general concept and roles of permitted subtypes?
5. Does each permitted subtype have its own Javadoc page linking back to the parent?
6. Do methods document inputs, returns, exceptions, and side effects?
7. Do collections/arrays specify ordering, mutability, and snapshot/view semantics?
8. Are thread-safety and concurrency assumptions documented where callers need them?
9. Are `@since`, `@deprecated`, `@see`, and `{@link}` used appropriately?
10. Are custom tags registered in the project's Javadoc command?
11. Does `javadoc -Xdoclint:all -Werror` pass cleanly in the build?
12. Have generated HTML pages been reviewed for types, components, constructors, and methods?

This checklist helps ensure documentation defines contracts callers can trust while accurately reflecting Java 17 constructs.

## 14. Frequently asked questions

**Which tag documents record components?**  
Use `@param` in the Javadoc on the record declaration. The standard doclet generates the Record Components section from those tags.

**Can I write @param on a compact constructor?**  
Yes. A compact canonical constructor has parameters corresponding to the record components. Document constructor validation and exceptions there; record-wide component meanings belong on the record declaration.

**Does Javadoc automatically create entries for record accessors?**  
Yes. Accessors are record methods and appear as methods. For default accessors, the doclet notes that they return the component value; if an accessor has custom behavior, write dedicated Javadoc.

**Does a sealed class need @permits?**  
No. `permits` is a Java language clause, not a standard JDK 17 Javadoc tag. The standard doclet automatically generates the Permitted Subclasses section.

**How should I explain each permitted subtype's meaning?**  
Write dedicated Javadoc on each subtype, use `@see` or `{@link ...}` on the parent, and describe business roles in the main description.

**Are @apiNote, @implSpec, and @implNote available by default?**  
Do not assume so. In JDK 17 they are custom tags registered by the JDK build; project builds must declare them via `-tag` or provide a Taglet.

**Should null constraints go in @param or @throws?**  
Document both sides: `@param` states whether null is permitted; `@throws` states which exception occurs if the caller violates that precondition.

**Must every private method have Javadoc?**  
Not necessarily. Prioritize public/protected APIs and private helpers with complex algorithms or subtle invariants. Javadoc primarily serves as a contract and guide for API users.

**Does Javadoc verify that implementation matches the contract?**  
No. Javadoc generates docs and doclint checks comment/HTML structure; unit tests, integration tests, and code review verify runtime behavior.

## 15. Official references

- [Java SE 17 — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): comment syntax, block tags, inline tags, inheritance, and tags supported by the standard doclet.
- [Java SE 17 — The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): doc generation options, `-tag`, `-taglet`, `-Xdoclint`, `-Werror`, module path, and source path.
- [Java SE 17 API — Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): record semantics, components, canonical constructors, and generated methods.
- [Java SE 17 Language Guide — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): syntax, restrictions, and usage of records.
- [Java SE 17 Language Guide — Sealed Classes and Interfaces](https://docs.oracle.com/en/java/javase/17/language/sealed-classes-and-interfaces.html): `sealed`, `permits`, `final`, `sealed`, `non-sealed`, and subtype constraints.
- [Java SE 17 API — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): runtime metadata of permitted subclasses.
- [Java SE 17 API — jdk.javadoc.doclet.Taglet](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.javadoc/jdk/javadoc/doclet/Taglet.html): API for creating custom Javadoc taglets.
- [Oracle — How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html): practical guide to writing documentation comments and basic tags.

**Guiding rule:** Use `@param` to document record components; describe sealed hierarchies through clear explanations and subtype links while leveraging the doclet-generated Permitted Subclasses section; express API contracts using the main description alongside `@param`, `@return`, `@throws`, `@since`, and `@deprecated`. Use `@apiNote`, `@implSpec`, and `@implNote` only when the build registers those custom tags.
