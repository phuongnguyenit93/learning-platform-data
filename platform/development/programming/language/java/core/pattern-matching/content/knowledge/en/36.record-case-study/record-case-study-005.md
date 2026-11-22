# Handling null components in Java record patterns

**Topic:** Java Core Pattern Matching — Record case study. This article focuses on the differences between a **null record object**, a **null component**, and a **null nested record** when using record patterns in **Java 21 and later**. Record patterns (JEP 440) and pattern matching for switch (JEP 441) are standard features since Java 21, requiring no preview flags.

## 1. Why is a null component an easily overlooked bug?

Records make data declarations concise:

~~~java
record Address(String city) {}
record Profile(String name, Address address) {}
~~~

However, this syntax **does not forbid null by itself**. The following calls are all valid for a model without validation:

~~~java
new Address(null);
new Profile(null, new Address("Hue"));
new Profile("Lan", null);
~~~

Many people assume that once a record is created, every component has a value, or that a matching record pattern means the components are non-null. Neither assumption is sound.

In an application, this can cause three categories of bugs:

1. **NullPointerException:** the body invokes a method on a variable extracted from a component, but that variable is null.
2. **Missing branch:** a nested record pattern requires the child record to exist; when the child component is null, the pattern does not match, and the logic lacks a suitable handling branch.
3. **Domain logic error:** the software treats "missing profile", "missing address", and "empty name" as the same state even though they have different meanings.

A solid handling strategy must answer: **which components are allowed to be null, what does null mean, where is it checked, and how should the API respond?**

## 2. Distinguishing four null scenarios

Suppose we have:

~~~java
record Address(String city) {}
record Profile(String name, Address address) {}
record UserJoined(Profile profile) {}
~~~

The following four scenarios are distinct:

| Input | Where is the null value? | Consequence |
| --- | --- | --- |
| **null** | The entire selector or the record itself | There is no object to deconstruct |
| **new UserJoined(null)** | The profile component of UserJoined | UserJoined exists, Profile does not |
| **new UserJoined(new Profile("Lan", null))** | The address component in Profile | Profile exists, Address does not |
| **new UserJoined(new Profile("Lan", new Address(null)))** | The city component of Address | All three records exist, String city is null |

A switch's **case null** only addresses a **null selector**; it does not automatically catch a record with a null component. A null component must be handled at the right layer: using an appropriate pattern, a guard, checks in the body, or constructor invariants.

If a component has a primitive type such as **int**, **long**, or **double**, the component itself cannot hold null. However, **double** can still hold NaN or Infinity; numeric data validation is a separate concern and is not solved by a null check.

## 3. How do record patterns work?

A record pattern uses the shape of a record to extract its components:

~~~java
// Illustrative branch snippet in a switch over Event.
case UserJoined(Profile(var name, Address(var city))) ->
        "JOINED: " + name + " @ " + city;
~~~

Here:

1. **UserJoined(...)** requires the selector to be UserJoined.
2. **Profile(...)** requires the profile component to be a Profile to continue deconstructing.
3. **var name** binds the name component of Profile.
4. **Address(...)** requires the address component to be an Address.
5. **var city** binds the city component of Address.

If **profile is null** or **address is null**, the corresponding nested record pattern **does not match**. If both profile and address exist but **name or city is null**, the variables bound with **var** can still receive null.

Therefore, the example above is **unsafe** if the body goes on to call **name.trim()** or **city.trim()** without checking. Structural matching alone does not prove that a String component has valid content.

### 3.1. A var binding does not mean non-null

~~~java
record Box(String value) {}

// Illustrative snippet when box is indeed a Box:
Box box = new Box(null);
String value = box.value();  // null
~~~

The pattern **Box(var text)** can bind the variable text to null. Also, do not associate **var** with creating a copy; it is a pattern form that infers the component's type and stores the bound value in a variable.

### 3.2. A subtle case: a component's type pattern can also match null

You should not memorize a rule that "every type pattern rejects null" and apply it blindly to a **record component**. For a component declared with type String, an **unconditional** pattern for that component can bind null as well.

A small standalone example in a Java 21 context:

~~~java
record Box(String value) {}

Object raw = new Box(null);

String result = switch (raw) {
    case Box(String text) -> "TYPED:" + text;
    default -> "OTHER";
};

System.out.println(result);
~~~

Output:

~~~text
TYPED:null
~~~

Here, the type pattern **String text** is **inside the record pattern of Box**, and can bind a null String component. This differs from a normal check:

~~~java
Object raw = null;
System.out.println(raw instanceof String text);
~~~

The output of **instanceof** on null is **false**. Record deconstruction has its own matching and unconditional pattern rules, so you need to understand the pattern context rather than extrapolating from a simple instanceof example.

**Specifically:** Placing **case Box(String text)** before **case Box(var text)** in the same switch can cause the latter branch to be **dominated**, because the first pattern already covers all Boxes with that String component structure. Do not try to use case Box(String text) to separate "nonnull" from "null"; use a **guard** or an explicit check when you need to distinguish values.

### 3.3. A nested record pattern differs from a String component pattern

Given:

~~~java
record Address(String city) {}
record Profile(String name, Address address) {}
~~~

**Profile(var name, var address)** can match a Profile with a null address. However, **Profile(var name, Address(var city))** requires an **Address record** to deconstruct; if address is null, the pattern does not match. If Address exists but city is null, **var city** can receive null.

This is the key boundary between a **null nested record** and a **null component inside a child record**.

## 4. Building the case study: user registration and delivery request

We build a domain model with three events:

~~~java
sealed interface Event permits UserJoined, DeliveryRequested, Ping {}

record Address(String city) {}
record Profile(String name, Address address) {}

record UserJoined(Profile profile) implements Event {}

record DeliveryRequested(String id, Address destination) implements Event {}

record Ping() implements Event {}
~~~

These records represent **raw data accepted for validation**, so they do not yet have constructors that reject null. In a real system, input coming from JSON, forms, message queues, or databases may be missing these fields. This article validates them at the consumer and then transitions to a validated domain model.

Requirements:

- **UserJoined** is valid when Profile exists, name is not blank, and Address exists with a non-blank city.
- **DeliveryRequested** is valid when id is not blank, destination is an Address, and city is not blank.
- **Ping** has no components, so it requires no component checks.
- **Null selector** means there is no event and must return a clear message.

Write a string-checking helper:

~~~java
static boolean present(String text) {
    return text != null && !text.isBlank();
}
~~~

**String.isBlank()** has been available since Java 11 and is only called after checking that text is non-null due to short-circuit evaluation of the **&&** operator. For a blank or null string, present returns false; for a string with valid content, present returns true.

### 4.1. Separating the valid case with a nested pattern and guard

~~~java
case UserJoined(Profile(var name, Address(var city)))
        when present(name) && present(city) ->
        "JOINED: " + name.trim() + " @ " + city.trim();
~~~

The conditions are evaluated in order:

1. UserJoined has a non-null Profile component.
2. Profile has a non-null Address.
3. The variables name and city are bound.
4. The guard confirms both have content.
5. Only when the guard is true is **trim()** called in the body.

A false guard does not throw an error if present is written properly; the switch moves on to evaluate subsequent matching cases. If the guard itself throws an exception, the exception propagates and is not treated as false.

### 4.2. Distinguishing three UserJoined errors

~~~java
case UserJoined(Profile(var name, var address))
        when !present(name) -> "INVALID JOIN: name";

case UserJoined(Profile(var name, var address))
        when address == null -> "INVALID JOIN: address";

case UserJoined(Profile(var name, Address(var city))) ->
        "INVALID JOIN: city";

case UserJoined(var profile) -> "INVALID JOIN: profile";
~~~

Place these branches **after the valid branch**, because a broad case appearing early can shadow a narrower branch and cause a dominance error.

The outcomes have distinct meanings:

- **INVALID JOIN: name:** Profile exists, but name is null/blank; here the name error takes priority if address is also missing at the same time.
- **INVALID JOIN: address:** Profile exists, name is valid, but address is null.
- **INVALID JOIN: city:** Address exists, name is valid, but city is null/blank.
- **INVALID JOIN: profile:** the Profile component of UserJoined is null.

This is **error prioritization by case order**. If a record has multiple invalid components, this design chooses to report the first meaningful error in the designed order. If an API needs to return **all errors at once**, using a validation result containing a list of issues is more appropriate than multiple cases producing a single String.

### 4.3. DeliveryRequested: same principle, different structure

~~~java
case DeliveryRequested(var id, Address(var city))
        when present(id) && present(city) ->
        "DELIVERY: " + id.trim() + " -> " + city.trim();

case DeliveryRequested(var id, var address)
        when !present(id) -> "INVALID DELIVERY: id";

case DeliveryRequested(var id, var address)
        when address == null -> "INVALID DELIVERY: address";

case DeliveryRequested(var id, Address(var city)) ->
        "INVALID DELIVERY: city";
~~~

In the valid DeliveryRequested branch, if destination is null, the nested **Address(...)** does not match. If id is null or city is null while Address exists, the guard is false, and then a specific error case handles it. If both id and address are missing, the example prioritizes reporting the **id** error.

### 4.4. Exhaustive switch without default

The entire Event hierarchy consists only of **UserJoined**, **DeliveryRequested**, and **Ping**, all of which are final records. The general cases at the end of each group cover the remainder of each subtype; Ping has its own branch, and the null selector has **case null**.

Therefore, the **switch expression** does not need a default branch. When a new subtype is later added to permits and recompiled, the compiler will remind the handler to add a branch. A broad default is usually unhelpful if the domain requires reviewing every event type.

**Note:** Compiler exhaustiveness does not by itself prove that name/city are valid. It only checks coverage of patterns and types; domain conditions still require guards, constructor invariants, and tests.

## 5. Complete runnable Java 21 program

Save all the code below in a file named **NullRecordComponentDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NullRecordComponentDemo {
    sealed interface Event permits UserJoined, DeliveryRequested, Ping {}

    record Address(String city) {}
    record Profile(String name, Address address) {}
    record UserJoined(Profile profile) implements Event {}
    record DeliveryRequested(String id, Address destination) implements Event {}
    record Ping() implements Event {}

    static boolean present(String text) {
        return text != null && !text.isBlank();
    }

    static String describe(Event event) {
        return switch (event) {
            case null -> "NO EVENT";

            case UserJoined(Profile(var name, Address(var city)))
                    when present(name) && present(city) ->
                    "JOINED: " + name.trim() + " @ " + city.trim();

            case UserJoined(Profile(var name, var address))
                    when !present(name) -> "INVALID JOIN: name";

            case UserJoined(Profile(var name, var address))
                    when address == null -> "INVALID JOIN: address";

            case UserJoined(Profile(var name, Address(var city))) ->
                    "INVALID JOIN: city";

            case UserJoined(var profile) -> "INVALID JOIN: profile";

            case DeliveryRequested(var id, Address(var city))
                    when present(id) && present(city) ->
                    "DELIVERY: " + id.trim() + " -> " + city.trim();

            case DeliveryRequested(var id, var address)
                    when !present(id) -> "INVALID DELIVERY: id";

            case DeliveryRequested(var id, var address)
                    when address == null -> "INVALID DELIVERY: address";

            case DeliveryRequested(var id, Address(var city)) ->
                    "INVALID DELIVERY: city";

            case Ping() -> "PING";
        };
    }

    static String requireText(String text, String field) {
        if (!present(text)) throw new IllegalArgumentException(field);
        return text.trim();
    }

    record ValidatedAddress(String city) {
        ValidatedAddress {
            city = requireText(city, "city");
        }
    }

    record ValidatedUser(String name, ValidatedAddress address) {
        ValidatedUser {
            name = requireText(name, "name");
            Objects.requireNonNull(address, "address");
        }
    }

    record TaggedUser(String name, List<String> tags) {
        TaggedUser {
            name = requireText(name, "name");
            tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
        }
    }

    public static void main(String[] args) {
        Event[] events = {
            new UserJoined(new Profile(" An ", new Address(" Ha Noi "))),
            new UserJoined(new Profile(" ", new Address("Hue"))),
            new UserJoined(new Profile("Lan", null)),
            new UserJoined(null),
            new UserJoined(new Profile("Lan", new Address(null))),
            new DeliveryRequested("PK-1", new Address("Da Nang")),
            new DeliveryRequested(null, new Address("Hue")),
            new DeliveryRequested("PK-2", new Address(" ")),
            new DeliveryRequested("PK-3", null),
            new Ping(),
            null
        };

        for (Event event : events) {
            System.out.println(describe(event));
        }

        var user = new ValidatedUser(
                " Linh ", new ValidatedAddress(" Hue "));
        System.out.println("VALID: "
                + user.name() + " @ " + user.address().city());

        try {
            new ValidatedUser(" ", new ValidatedAddress("Hue"));
        } catch (IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        try {
            new ValidatedUser("Linh", null);
        } catch (NullPointerException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        var tags = new ArrayList<>(List.of("vip"));
        var tagged = new TaggedUser("Bao", tags);
        tags.add("new");
        System.out.println("TAGS: " + tagged.tags());

        try {
            tagged.tags().add("other");
        } catch (UnsupportedOperationException ex) {
            System.out.println("TAGS: unmodifiable");
        }

        try {
            new TaggedUser("Bao",
                    java.util.Arrays.asList("vip", null));
        } catch (NullPointerException ex) {
            System.out.println("REJECTED: null tag");
        }
    }
}
~~~

### 5.1. Compiling and running

Use **JDK 21 or later**:

~~~bash
javac NullRecordComponentDemo.java
java NullRecordComponentDemo
~~~

**Exact output:**

~~~text
JOINED: An @ Ha Noi
INVALID JOIN: name
INVALID JOIN: address
INVALID JOIN: profile
INVALID JOIN: city
DELIVERY: PK-1 -> Da Nang
INVALID DELIVERY: id
INVALID DELIVERY: city
INVALID DELIVERY: address
PING
NO EVENT
VALID: Linh @ Hue
REJECTED: name
REJECTED: address
TAGS: [vip]
TAGS: unmodifiable
REJECTED: null tag
~~~

### 5.2. Reading the output lines

1. **JOINED: An @ Ha Noi:** all required nested records exist; name and city are trimmed.
2. **INVALID JOIN: name:** Profile exists, but name contains only whitespace.
3. **INVALID JOIN: address:** Profile exists and name is valid, but Address is null.
4. **INVALID JOIN: profile:** UserJoined exists while Profile is null.
5. **INVALID JOIN: city:** Address exists, but city is null.
6. **DELIVERY: PK-1 -> Da Nang:** both ID and city have content.
7. **INVALID DELIVERY: id:** id is null, even though Address exists.
8. **INVALID DELIVERY: city:** Address is present, but city is blank.
9. **INVALID DELIVERY: address:** Address itself is missing.
10. **PING:** the componentless variant is handled independently.
11. **NO EVENT:** null is the **selector**, not a component of an event.
12. **VALID: Linh @ Hue:** the compact constructors normalized name/city using trim.
13. **REJECTED: name:** the domain record rejects a blank name at creation time.
14. **REJECTED: address:** the domain record rejects a null Address via Objects.requireNonNull.
15. **TAGS: [vip]:** TaggedUser created a copy of the list; adding an element to the original list does not change the list inside the record.
16. **TAGS: unmodifiable:** the list stored by TaggedUser does not allow adding elements through the accessor.
17. **REJECTED: null tag:** List.copyOf rejects a collection containing a null element.

The program uses an **Event[] array** to also test a null selector. **List.of(...)** does not allow null elements, so it is unsuitable if you want to intentionally include null in a test sample list.

**Demo limitations:** The article demonstrates processing an event into a String to observe the flow; there is no database, network, or external framework. Returning error messages instead of throwing exceptions is a **policy specific to the describe method**, not mandatory behavior for every Java API.

## 6. Using compact constructors to turn raw data into valid domain values

The **Profile** and **Address** models at the beginning of the article allow null to simulate data received from external sources. In the domain layer, however, many situations require stronger invariants: if a user is considered valid, then name and address must have values.

~~~java
record ValidatedAddress(String city) {
    ValidatedAddress {
        city = requireText(city, "city");
    }
}

record ValidatedUser(String name, ValidatedAddress address) {
    ValidatedUser {
        name = requireText(name, "name");
        Objects.requireNonNull(address, "address");
    }
}
~~~

This code is extracted from the complete class. In a **compact constructor**, we can validate or normalize component parameters before Java automatically assigns them to the record fields.

**requireText** throws IllegalArgumentException if the string is null or blank, and otherwise trims the valid string. **Objects.requireNonNull(address, "address")** throws NullPointerException if the address record is missing.

Comparison:

| Raw record | Validated record |
| --- | --- |
| Allows **new Address(null)** | **new ValidatedAddress(null)** is rejected |
| Allows **new Profile(null, ...)** | **new ValidatedUser(null, ...)** is rejected |
| Allows **new Profile("Lan", null)** | **new ValidatedUser("Lan", null)** is rejected |
| Consumers must check for null | Validly constructed instances uphold clear invariants |
| Suitable for unvalidated input | Suitable for domain logic after validation |

**No single option is always better.** When receiving untrusted JSON or form data, a raw DTO can record all missing fields and report multiple errors at once. Domain records should generally protect invariants that truly cannot be violated in the system.

A practical architecture is **parse → validate → build validated record → process business logic**. This reduces repetitive guards in domain logic, though it does not eliminate the need for null checks at the **selector API** if callers can still pass null.

### 6.1. Keeping the exception contract consistent

In the example, a blank/null name or city triggers **IllegalArgumentException**, while a null address object triggers **NullPointerException**. This is an illustrative contract, not the only choice.

If a public API wants all validation errors to share a common type such as **ValidationException**, you can design a factory that returns a result or throws that exception type. What matters is that **Javadoc, implementation, and tests match**.

## 7. Records containing collections: null is not only at the component level

A record has final reference components, but **it does not guarantee deep immutability**. A **List<String> tags** component can fail in three ways:

1. The entire List is null.
2. The List exists, but contains a null element.
3. The List is mutable and continues to be modified by the caller after the record is created.

In the example, **TaggedUser** handles this with:

~~~java
record TaggedUser(String name, List<String> tags) {
    TaggedUser {
        name = requireText(name, "name");
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }
}
~~~

Meaning:

- **Objects.requireNonNull(tags, "tags")** rejects a null list.
- **List.copyOf(tags)** creates an unmodifiable list that disallows operations like add/remove and does not allow null elements.
- When the source is a mutable ArrayList, the copy's contents are unaffected by **tags.add(...)** on the original ArrayList.
- For elements that are mutable objects, **List.copyOf** only copies the collection structure and **does not deep-copy** the internal state of each element.

An unsafe data example:

~~~java
// Illustrative snippet; List.copyOf does not accept null elements.
new TaggedUser("Bao", java.util.Arrays.asList("vip", null));
~~~

This call throws NullPointerException inside the TaggedUser constructor. If a null element is valid according to business rules, you should **not** automatically use List.copyOf and treat that error as proper validation; instead, define an explicit strategy for null elements, such as filtering them out, reporting an indexed error, or representing them with a different type.

**Key takeaway:** For collection components, document nullability for both the **collection reference** and **individual elements**; they are two distinct contracts.

## 8. Record patterns and accessors: do not assume deconstruction is completely harmless

When a record pattern extracts components, the JVM must retrieve the component values from the record according to deconstruction rules. For a typical record, the auto-generated accessor simply returns the component value. Java also allows records to have user-defined accessors, so access behavior can be more complex.

If a custom accessor throws an exception during record pattern matching, the error occurs **before the case body**. In specified cases, an error from an accessor may be wrapped in a **MatchException**, with the original throwable as its cause. Therefore, a **try/catch inside the case body** will not automatically catch an error that occurred before the case was even selected.

Avoid writing accessors with unnecessary side effects just to serve record deconstruction. Keep records representing clear value data; if data requires lazy loading or network queries on every access, a dedicated class or service usually expresses that better.

**Separate validation from matching exceptions:** checking null in a constructor or guard is a predictable domain decision; an exception from a faulty accessor is a different problem and should be handled at the appropriate boundary.

## 9. Where to place guards and avoiding ordering mistakes

A case's **when** guard is evaluated after the pattern has matched, before the body runs:

~~~java
case UserJoined(Profile(var name, Address(var city)))
        when present(name) && present(city) ->
        "JOINED: " + name.trim() + " @ " + city.trim();
~~~

If **present(name) && present(city)** is false, the case is not selected. In a switch with proper fallback branches, matching continues and selects another case. Without a fallback, however, a switch expression may not be exhaustive or may lack an appropriate handling path.

### 9.1. Short-circuiting is how to avoid NPE in guards

~~~java
static boolean present(String text) {
    return text != null && !text.isBlank();
}
~~~

Because **&&** only evaluates the right-hand side if the left-hand side is true, null never reaches **isBlank()**.

A common mistake:

~~~java
// Wrong: if text is null, the text.isBlank() branch will be called.
return text != null || !text.isBlank();
~~~

When text is null, the first operand is false, so **||** evaluates the second operand and throws NullPointerException. This condition is also semantically wrong: a non-null but blank string would make the expression return true.

### 9.2. Broad branches must come after narrow branches

~~~java
// Sketch: do not place a general case before a specific case.
case UserJoined(var profile) -> "any joined event";
case UserJoined(Profile(var name, Address(var city))) ->
        "special joined event";
~~~

With this order, the general case can dominate the later case. The compiler may reject the unreachable branch. Place specific cases with guards first, followed by the remaining cases for the same subtype.

### 9.3. Do not use default to hide null components

With a sealed Event, a **default -> "UNKNOWN"** branch can cause new subtypes to be lumped into UNKNOWN without requiring a domain review. It also fails to explain which component is missing.

Instead, provide cases that handle **raw records with missing components** with distinct results or exceptions. For strictly validated domain models, unnecessary component fallbacks can be omitted if the compiler and invariants genuinely allow it.

## 10. Strategies for handling null components

Not every consumer should return a message like describe. The right choice depends on what the data means.

| Strategy | Example | When appropriate |
| --- | --- | --- |
| **Reject immediately upon record construction** | Compact constructor checks name, address | Domain objects must never hold missing state |
| **Explicit validation result** | Result with a list of field errors | Forms/imports need to report multiple errors |
| **Guards and fallbacks in switch** | INVALID JOIN: address branch | Classifying raw records for UI/logging |
| **Null as a meaningful value** | Optional notes section omitted | Component is truly optional |
| **Optional or alternative result type** | Optional<Address> or AddressAbsent/AddressPresent | API wants to model absence explicitly |
| **Domain-based default** | Use a valid default configuration when missing | Only when allowed by contract, never guess data |
| **Fail-fast at the API boundary** | Objects.requireNonNull(input, "input") | A null selector is a caller bug |

A **valid null component** is different from a **null component that makes a record invalid**. For example, an order's additional notes may be null without causing an error; conversely, an identifier ID or required address cannot be null.

If using **Optional<T>** as a field in a model, choose a consistent convention and avoid returning null instead of Optional.empty(). Many codebases prefer Optional primarily for **return types**, while using invariants and dedicated models for fields; this is a design decision, not a Java requirement.

## 11. Javadoc for null components, not just null selectors

An API that processes raw records should clearly state its behavior at each level:

~~~java
/**
 * Builds an event description for display purposes.
 *
 * @param event may be null; null returns "NO EVENT".
 *              For UserJoined, Profile, name, Address, or city
 *              may be null/blank and are classified as INVALID.
 *              For DeliveryRequested, id or destination/city
 *              may be null/blank and are also classified.
 * @return a non-null String: JOINED, DELIVERY, INVALID, PING,
 *         or NO EVENT depending on the data structure
 */
static String describe(Event event) {
    // Full implementation is in section 5.
    throw new UnsupportedOperationException("illustrative signature");
}
~~~

This is only an **illustrative signature with Javadoc**, not a method to merge into the section 5 demo. Real code must guarantee there are no return paths yielding null and no unexpected exceptions for allowed inputs.

For **ValidatedUser**, the Javadoc should state that a blank/null name is rejected, a null address is rejected, and city is already validated by the ValidatedAddress constructor. These details cannot be inferred from the signature **ValidatedUser(String, ValidatedAddress)** alone.

If a project uses **@Nullable**, **@NonNull**, **@NullMarked**, or a static checker, pick a specific annotation system and keep it consistent with the implementation. Java SE does not provide a standard @Nullable annotation in java.lang understood with identical semantics by all tools; annotations also do not enforce runtime validation by themselves.

### Note on error messages

Callers are discouraged from parsing strings like **"INVALID JOIN: name"** to make business decisions. For a public API, consider a structured result: **ValidationResult**, a field path like **profile.address.city**, and stable error codes. The strings in this article are only for reading output and verifying pattern logic.

## 12. Test matrix for null components

Do not just test **describe(null)** and conclude that null handling is sufficient. Cover every component level:

| Input | Expected | Why |
| --- | --- | --- |
| **null** | NO EVENT | Null selector |
| **UserJoined(Profile("An", Address("Hue")))** | JOINED: An @ Hue | All components valid |
| **UserJoined(null)** | INVALID JOIN: profile | Nested Profile is null |
| **UserJoined(Profile(null, Address("Hue")))** | INVALID JOIN: name | String component is null |
| **UserJoined(Profile(" ", Address("Hue")))** | INVALID JOIN: name | Component is blank |
| **UserJoined(Profile("Lan", null))** | INVALID JOIN: address | Nested Address is null |
| **UserJoined(Profile("Lan", Address(null)))** | INVALID JOIN: city | Address has null city |
| **DeliveryRequested(null, Address("Hue"))** | INVALID DELIVERY: id | id is null |
| **DeliveryRequested("PK", null)** | INVALID DELIVERY: address | destination is null |
| **DeliveryRequested("PK", Address(" "))** | INVALID DELIVERY: city | city is blank |
| **Ping()** | PING | Componentless record |
| **ValidatedUser(" ", ValidatedAddress("Hue"))** | IllegalArgumentException | Constructor rejects blank name |
| **ValidatedUser("Linh", null)** | NullPointerException | Constructor rejects null address |
| **TaggedUser("Bao", null)** | NullPointerException | Null list reference |
| **TaggedUser("Bao", list with a null element)** | NullPointerException | List.copyOf disallows null elements |

If using JUnit, use **assertEquals** for return values and **assertThrows** for error cases. For framework-free testing, the program in section 5 already covers many representative cases and prints observable outcomes.

For complex raw data, add tests where **multiple components are null simultaneously** to verify error prioritization order. If validation returns a list of errors, check the set of field paths rather than just a single message.

## 13. Process for applying this in a project

1. **Classify models:** which records are raw input, and which are validated domain values?
2. **Write a nullability table:** for each component, mark it as required, optional, or untrusted.
3. **Choose the validation boundary:** in the constructor, factory, mapper, or service, depending on who owns the contract.
4. **Design record patterns:** write readable valid branches, guards for String/content, and fallbacks for null nested records.
5. **Order branches:** narrow cases first, broad cases later; avoid dominance and avoid defaults that hide new subtypes.
6. **Specify null selector behavior separately:** case null, Objects.requireNonNull, or a Missing result type—do not infer selector policy from component policy.
7. **Handle collections:** check for null collections, null elements, and mutable aliases, and protect with defensive copies when needed.
8. **Document the API:** Javadoc, error/result types, nullability annotations, and stability guarantees of error messages.
9. **Test intentionally:** null at every level, blank values, multiple invalid fields, exceptions, and valid cases.
10. **Recompile when the hierarchy changes:** sealed + exhaustive switch helps detect new subtypes, but does not replace reviewing record invariants.

## 14. Common mistakes and how to avoid them

**Mistake 1 — Thinking a final record means components cannot be null.** Final only prevents reassigning the field after initialization; it does not prevent the reference from holding null. If nonnull is required, validate in the constructor.

**Mistake 2 — Assuming deconstruction automatically validates strings.** A record pattern only extracts components; if a String component is null/blank, an appropriate guard or invariant is needed.

**Mistake 3 — Thinking every type pattern inside a record excludes null.** With an unconditional pattern matching the component's type, such as **Box(String text)** on a Box with a String value, text can be null. Do not use it as a substitute for **text != null**.

**Mistake 4 — Forgetting null nested records.** **Profile(var name, Address(var city))** does not match if address is null. Use a fallback or forbid null address from the start.

**Mistake 5 — Using case null for null components.** Case null only checks the selector. For **UserJoined(null)**, the selector is not null, so it will not enter case null.

**Mistake 6 — Placing broad cases before narrow cases.** Later branches may be dominated, or detailed logic may never run. Place specific guards/record patterns before fallbacks.

**Mistake 7 — Using the wrong operator in guards.** **text != null || !text.isBlank()** can cause an NPE; use short-circuiting &&.

**Mistake 8 — Having a default for everything.** A broad default can hide new subtypes in a sealed hierarchy and cause null components to be treated as a generic, hard-to-trace error.

**Mistake 9 — Confusing shallow immutability with deep immutability.** A record holds a final reference to a List, but the List's contents can be mutable if not copied. **List.copyOf** does not deep-copy individual elements.

**Mistake 10 — Catching NullPointerException and treating it as "missing data".** An NPE can also come from a bug or a custom accessor, so broad catching can mask the real cause.

**Mistake 11 — Conflating null errors with other business errors.** A null id, a null address, and a record of an unsupported subtype may require different error codes.

**Mistake 12 — Only testing a null selector.** A record can contain multiple component levels; test every level and the error prioritization order.

## 15. Code review checklist

- [ ] Which record models are allowed to contain null components, and which have nonnull invariants?
- [ ] Is a null selector handled independently from null components?
- [ ] Do nested record patterns have fallbacks for null child records when raw input allows them?
- [ ] Are variables from **var** or type patterns checked before calling methods when they might be null?
- [ ] Are guards null-safe and in the right error priority order?
- [ ] Do broad cases appear after narrow cases without causing dominance?
- [ ] Is the switch exhaustive over the sealed hierarchy without a default that masks new subtype signals?
- [ ] Do constructors/factories validate name, city, id, and required domain components?
- [ ] Do List components check for null references, null elements, and mutable aliases?
- [ ] Do Javadoc/annotations accurately describe null, blank, exception, and return cases?
- [ ] Do tests cover a null selector, null components at every level, multiple invalid fields simultaneously, and valid inputs?
- [ ] Are raw DTOs separated from validated domain records to avoid repeating defensive logic across the system?

**Conclusion:** **Records do not guarantee non-null components on their own.** In Java 21, record patterns can bind null components with unconditional patterns, whereas a **nested record pattern** does not match when the child record is null. Proper handling requires distinguishing a **null selector**, a **null component**, a **null child record**, **blank values**, and **collections containing null**. Using short-circuiting guards, per-subtype fallback cases, compact constructors to uphold invariants, and testing at API boundaries will help your system avoid silent NPEs without masking invalid data.
