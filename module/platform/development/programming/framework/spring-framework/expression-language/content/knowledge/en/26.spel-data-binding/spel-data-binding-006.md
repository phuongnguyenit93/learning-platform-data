# Auto-Grow Nested Paths and Collections

In Spring Expression Language (SpEL), an expression can access nested properties or collection elements along a path, such as **customer.address.city** or **items[3].name**. If an intermediate object is null or the accessed index is beyond the current bounds, a normal operation may fail during evaluation.

SpEL provides two options in **SpelParserConfiguration** to handle these situations:

- **autoGrowNullReferences**: automatically instantiates an intermediate object when a property path encounters a null reference and SpEL has enough information to create an instance.
- **autoGrowCollections**: automatically grows a collection when accessing an index beyond its current size, within configured limits.

These two options help simplify data binding and updating object graphs. However, they can mutate data right during expression evaluation. You must clearly understand when objects or collections are created, conditions for successful growth, and resource limits before enabling them for flows handling untrusted data.

## 1. What Is Auto-Grow in SpEL?

### 1.1. The Problem with Null Nested Properties

Suppose we have a Person object containing an Address:

~~~java
public class Person {

    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}

public class Address {

    private String city;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
~~~

If address is null, the expression:

~~~java
address.city
~~~

cannot access city on an object that does not yet exist. When auto-grow null references is disabled, evaluating this path can fail because the intermediate receiver is null.

When auto-grow null references is enabled, SpEL can create a new Address at the address position and then continue processing the city property, if the target type and constructor allow it.

### 1.2. The Problem with Collection Indices

Suppose Person has a list of addresses:

~~~java
public class Person {

    private List<Address> addresses = new ArrayList<>();

    public List<Address> getAddresses() {
        return addresses;
    }

    public void setAddresses(List<Address> addresses) {
        this.addresses = addresses;
    }
}
~~~

If the list is empty, the expression:

~~~java
addresses[2].city
~~~

requests accessing the element at index 2, while the list does not yet have an element at that position.

When auto-grow collections is enabled, SpEL can expand the collection so the requested index falls within bounds. If the created element is still null and the path continues accessing its properties, auto-grow null references can participate in creating the intermediate object if SpEL can determine the element type and instantiate it.

Distinguish the two behaviors: growing a collection adds slots; auto-grow null references creates an object at a null slot when continuing along a property path. Enabling one option does not mean the other option is also enabled.

### 1.3. Auto-Grow Can Mutate the Object Graph

Auto-grow is not merely a safer way to read data. When SpEL automatically creates objects or grows collections, the state of the object graph can change during evaluation.

For example, an expression reading a deep path can cause intermediate properties to be initialized. A write expression can both create objects, grow a list, and then assign the final value.

Therefore, treat auto-grow as an intentional data-mutation behavior. Do not enable it merely to avoid seeing null or index errors without understanding the impact on the objects.

## 2. Configuring Auto-Grow with SpelParserConfiguration

### 2.1. The Two Main Options

SpelParserConfiguration allows configuring auto-grow behavior:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,   // autoGrowNullReferences
                true    // autoGrowCollections
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

The two Boolean values respectively control automatically initializing null references and automatically growing collections.

If auto-grow is not needed, use a disabled configuration or the default parser suited to the Spring version in use. Explicitly check the application's parser configuration rather than assuming every parser has the same behavior.

### 2.2. Limiting Auto-Grow Size

You can configure a maximum size limit for auto-grow operations:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,
                true,
                256
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);
~~~

The third parameter is **maximumAutoGrowSize**. It limits the expansion SpEL permits during supported auto-grow operations.

The number 256 is just an example. Choose a threshold based on data structure, memory capacity, and business requirements. Do not use an arbitrarily large limit, especially when indices or expressions may come from users.

This limit is not a global cap for all pre-built collections, all inline lists/maps, or all array constructions in SpEL. The application still needs to validate input data sizes separately.

### 2.3. Creating a Parser with Consistent Configuration

Complete example:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,
                true,
                256
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);

StandardEvaluationContext context =
        new StandardEvaluationContext(person);

Expression expression =
        parser.parseExpression("address.city");

expression.setValue(context, "Hanoi");
~~~

In the example, the parser enables both features and caps auto-grow at 256. When the path encounters a null address, SpEL can instantiate Address and then write city if instantiation and property-writing conditions are met.

The parser carries the configuration it was created with. If a group of expressions needs a different policy, create a parser with the configuration appropriate for that group rather than changing policy arbitrarily between requests.

## 3. Auto-Grow Null References on Nested Paths

### 3.1. Automatically Creating Intermediate Objects

Suppose an object graph has multiple levels:

~~~java
public class Employee {

    private Profile profile;

    public Profile getProfile() {
        return profile;
    }

    public void setProfile(Profile profile) {
        this.profile = profile;
    }
}

public class Profile {

    private Contact contact;

    public Profile() {
    }

    public Contact getContact() {
        return contact;
    }

    public void setContact(Contact contact) {
        this.contact = contact;
    }
}

public class Contact {

    private String email;

    public Contact() {
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

If both profile and contact are null, the expression:

~~~java
profile.contact.email
~~~

may require creating two intermediate objects when auto-grow null references is enabled and SpEL can determine the type of each property.

When assigning:

~~~java
parser.parseExpression("profile.contact.email")
        .setValue(context, "employee@example.com");
~~~

SpEL can instantiate Profile, then instantiate Contact, and finally assign email.

### 3.2. Conditions for Successful Instantiation

Auto-grow null references needs enough information to create an instance for the null property. In typical cases, the property type must be determinable and have a suitable default constructor for SpEL to invoke.

Instantiation can fail if:

- The property type cannot be determined.
- There is no suitable default constructor.
- The constructor is not accessible in the current runtime.
- The type is an interface or abstract class with no way to instantiate a concrete implementation.
- The constructor throws an exception.
- The property cannot be written back with the newly created instance using the current accessor.

For example, a property declared with an interface type:

~~~java
private AddressProvider addressProvider;
~~~

SpEL cannot infer a concrete implementation from the interface alone without an appropriate instantiation mechanism. Initialize the implementation in Java or supply a pre-created object.

### 3.3. Default Constructors and Side Effects

Do not put heavy logic or side effects in the constructors of types that can be auto-grown. An expression read or write operation might unintentionally trigger the constructor when a path encounters null.

Intermediate object constructors should be lightweight, deterministic, and perform no I/O. If initialization needs dependencies, complex configuration, or service access, create the object in Java and attach it to the graph before evaluating SpEL.

### 3.4. Auto-Grow Does Not Replace Validation

Creating intermediate objects only gives the path objects to continue traversal. It does not guarantee that the new objects hold valid business data.

For example, creating a new Address may leave city, district, and postalCode all null. The application still needs to validate required fields before saving or using the object in business logic.

Do not treat successful auto-grow as proof that a request is valid.

## 4. Auto-Grow Collections

### 4.1. Expanding a List When Index Exceeds Size

Suppose a list initially has one element:

~~~java
List<String> tags =
        new ArrayList<>(List.of("spring"));
~~~

When accessing an index larger than the current last index, auto-grow collections can expand the list so that position exists within configured bounds.

Example expression:

~~~java
tags[3]
~~~

With auto-grow collections enabled, the list can be expanded up to index 3. New slots are initialized according to collection and element-type rules; for reference elements, they may remain null until assigned or further auto-grown as a nested reference.

Do not assume new elements automatically carry valid business values. If specific default data is needed, create and assign it explicitly.

### 4.2. Assigning to an Expanded Index

Example root object with a list:

~~~java
public class FormData {

    private List<String> tags = new ArrayList<>();

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

With a parser that enables auto-grow collections:

~~~java
parser.parseExpression("tags[2]")
        .setValue(context, "spel");
~~~

If the list is mutable and the index is within the auto-grow limit, SpEL can expand the list and assign the value at index 2.

As a result, the list has slots from index 0 through index 2. Earlier elements are preserved; newly added slots may hold null depending on the type and growth mechanism.

### 4.3. Immutable Lists or Lists That Do Not Support Growth

Auto-grow requires a collection that can be modified in the way SpEL uses. Immutable collections or collections that do not support adding elements can cause the operation to fail.

For example:

~~~java
List<String> tags = List.of("spring");
~~~

A list created by List.of does not support add. If SpEL needs to grow it, the operation cannot complete normally.

When auto-grow is needed, use a mutable implementation such as ArrayList or prepare a suitably modifiable collection. If the data must be immutable, create a mutable copy during binding and convert it to an immutable structure after validation.

### 4.4. Negative Indices and Overly Large Indices

Auto-grow does not make negative indices valid. A negative index is still an out-of-bounds access and can cause errors during evaluation.

Overly large indices also need limits. If an index exceeds maximumAutoGrowSize, SpEL rejects the corresponding auto-grow operation instead of expanding unboundedly.

Validate indices from user data before evaluation. The parser limit is an additional safeguard, not a replacement for validation at the API or service layer.

## 5. Distinguishing Collection Indices from Map Keys

Lists and arrays use positional indices; Maps use keys to look up entries.

For example:

~~~java
items[2]
settings['theme']
~~~

Auto-grow collections relates to growing collections by index. You should not infer that a nonexistent key in a Map will automatically create a new entry merely because auto-grow collections is enabled.

With a Map, if a key needs to be added, use an appropriate write operation and ensure the Map is mutable:

~~~java
parser.parseExpression("settings['theme']")
        .setValue(context, "dark");
~~~

Writability depends on the PropertyAccessor/indexer and Map implementation. An immutable Map or one that prohibits adding keys can cause the operation to fail.

If a Map or nested value needs to be initialized, explicitly determine where the Map is created and which value types are allowed to be created. Auto-grow null references does not mean SpEL can automatically infer every value type from a nonexistent Map key.

## 6. Auto-Grow and Arrays

Java arrays have a fixed size per instance. Therefore, arrays must be distinguished from Lists when designing data binding.

Collections like ArrayList can grow by adding elements. Arrays have no add operation to grow their length; if an operation needs to grow an array, SpEL must be able to create a replacement array and update the property holding the array. This depends on the target, whether the property is writable, and support in the Spring version being used.

Do not rely on assuming every array grows just like an ArrayList. For important input data, test arrays and collections separately on the exact Spring version. If dynamic sizing is needed, List is usually a clearer choice.

## 7. Combining Auto-Grow with Data Binding

### 7.1. Binding Nested Property Paths

A form field can map to a nested property:

~~~java
address.city
~~~

If address is null, auto-grow null references can instantiate the intermediate object when the parser is configured appropriately. This helps a binder or expression update an object graph without manually initializing every prior level.

However, whether the binder uses the same parser and SpEL configuration depends on the integration component. Do not assume every Spring MVC binding operation automatically uses a custom parser configuration created by the application.

Check the exact integration point: the SpEL parser, DataBinder, WebDataBinder, or framework component performing the binding.

### 7.2. Preparing the Object Graph Before Binding

In many cases, a more controllable approach is to initialize nested objects in a constructor or factory:

~~~java
public class RegistrationForm {

    private Address address = new Address();

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

When the object graph is already present, the expression does not need to create address automatically. This reduces reliance on auto-grow and makes the form's initial state explicit.

Use auto-grow when it genuinely simplifies the data structure, not as a way to mask an object graph that has not been clearly designed.

### 7.3. Checking After Binding

After binding completes, check:

- Whether intermediate objects were created with the right types.
- Whether the collection element count is within bounds.
- Whether added elements have proper default values.
- Whether required fields already have values.
- Whether there is extra data caused by user-submitted indices.
- Whether any binding errors or conversion errors were recorded.

Auto-grow only solves path structure; validation remains a separate step.

## 8. Resource Limits and Safety

### 8.1. Risk of Excessive Allocation

A short expression can request a very large index:

~~~java
items[100000000]
~~~

If auto-grow is enabled without an appropriate limit, the operation can consume large amounts of memory or cause the request to fail.

Always configure a suitable maximumAutoGrowSize and validate indices before evaluation. Do not use the maximum value of int or an overly large threshold just to avoid errors.

### 8.2. Controlling Nested Path Depth

A multi-level path can instantiate many intermediate objects. Limit the input structure and the number of levels expressions are allowed to access.

For user-supplied expressions, do not allow arbitrary access into a large object graph. Provide only small DTOs or root objects containing the required properties.

### 8.3. Auto-Grow Can Create Side Effects When Reading

If auto-grow null references or collections is enabled, an expression that appears read-only can mutate the object graph when accessing a path that requires growth.

Therefore:

- Do not use an auto-grow parser for read-only expressions unless there is a clear need.
- Separate read contexts and write contexts if the application has both types of use cases.
- Do not share an object undergoing auto-grow across concurrent requests without synchronization.
- Evaluate only on objects with appropriate lifecycles and mutation permissions.
- Test state both before and after evaluation.

### 8.4. Do Not Grant Broad Permissions to Untrusted Expressions

Auto-grow is a data-manipulation capability, not a sandbox mechanism. If an untrusted expression can also invoke methods, access beans, or instantiate arbitrary objects, the risk is far greater than expanding a list.

Restrict the root object, property accessors, method resolvers, bean resolvers, and type locators as needed. Do not let users control arbitrary expression sources in a broadly privileged context.

## 9. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Nested path still fails when property is null | autoGrowNullReferences is disabled | Enable the option if business logic allows or initialize the object in Java |
| Cannot create intermediate object | Missing suitable constructor or unknown type | Use a concrete type, accessible default constructor, or pre-initialize |
| List does not grow | autoGrowCollections is disabled | Configure the parser appropriately |
| List growth fails | Collection is immutable or does not support add | Use a mutable collection or create a copy |
| Negative index causes error | Invalid index; auto-grow does not handle negative indices | Validate index before evaluation |
| Very large index is rejected | Exceeds maximumAutoGrowSize | Check input data and choose a suitable limit |
| Nonexistent Map key does not auto-create value | Map key lookup differs from collection index growth | Write the key explicitly or prepare the value in Java |
| New object has null fields | Auto-grow only creates structure, not business data | Validate and assign needed values |
| Reading modifies the object | Auto-grow instantiated an object or grew a collection | Use a non-auto-grow parser for read flows |
| Array behavior differs from List | Arrays have fixed size and replacement depends on target | Test separately or use List for dynamic data |

## 10. Complete Example

The example below illustrates creating a nested object and growing a list inside a form:

~~~java
public class Address {

    private String city;

    public Address() {
    }

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}

public class RegistrationForm {

    private Address address;
    private List<String> tags = new ArrayList<>();

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }

    public List<String> getTags() {
        return tags;
    }

    public void setTags(List<String> tags) {
        this.tags = tags;
    }
}
~~~

Configuring the parser:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(
                true,
                true,
                32
        );

ExpressionParser parser =
        new SpelExpressionParser(configuration);

RegistrationForm form = new RegistrationForm();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);
~~~

Assigning a nested property:

~~~java
parser.parseExpression("address.city")
        .setValue(context, "Hanoi");
~~~

Assigning an element at index 2:

~~~java
parser.parseExpression("tags[2]")
        .setValue(context, "spring");
~~~

After these operations, address can be created and contain city Hanoi; tags is expanded to include index 2 and contain the value spring. Slots before index 2 are preserved or added according to the collection's growth rules.

In a real application, validate the form after binding, check size limits, and do not rely on auto-grow to automatically produce valid domain data.

## 11. Testing Auto-Grow

Both options and their limits should be tested separately:

~~~java
SpelParserConfiguration configuration =
        new SpelParserConfiguration(true, true, 16);

ExpressionParser parser =
        new SpelExpressionParser(configuration);

RegistrationForm form = new RegistrationForm();

StandardEvaluationContext context =
        new StandardEvaluationContext(form);

parser.parseExpression("address.city")
        .setValue(context, "Hanoi");

assertNotNull(form.getAddress());
assertEquals("Hanoi", form.getAddress().getCity());

parser.parseExpression("tags[2]")
        .setValue(context, "spring");

assertEquals("spring", form.getTags().get(2));
~~~

Cases that should be included in the test suite:

- Auto-grow null references enabled and disabled.
- Auto-grow collections enabled and disabled.
- Nested paths with one or multiple null levels.
- Intermediate types with and without a default constructor.
- Properties of interface or abstract types.
- Empty collections and collections that already have elements.
- Index equal to next position, index exceeding limit, and negative index.
- Mutable and immutable collections.
- Nonexistent Map keys.
- Read-only evaluation and setValue.
- Object graph before/after evaluation.
- Two requests evaluating on two separate objects.

For auto-grow limits, test both near-threshold and over-threshold cases. Do not depend on internal error messages if the message is not part of the application contract; assert the behavior and exception type appropriate to the Spring version in use.

## 12. Summary

SpEL supports auto-growing data paths via two options in SpelParserConfiguration:

- **autoGrowNullReferences** creates intermediate objects when a property path encounters null and the type can be instantiated.
- **autoGrowCollections** expands collections when accessing an index beyond the current size.
- **maximumAutoGrowSize** caps the permitted amount of auto-grow.

Auto-grow is useful for data binding and updating nested object graphs, yet it can mutate data even in expressions that seem read-only. Use appropriate constructors, mutable collections, size limits, post-binding validation, and test List, Map, array, and nested paths separately.

If the object graph has complex initialization rules, requires dependency injection, or has side effects, prepare objects in Java instead of letting SpEL create them automatically. Enable auto-grow only in flows that truly need it, and strictly control the data and permissions expressions are allowed to use.