# autoGrowNestedPaths and Conditions for Auto-Instantiating Objects in Spring

## 1. The problem: a property path crossing a null value

In Spring Framework, **data binding** maps input data onto Java objects using property names like `name`, `address.city`, `shippingAddress.postalCode`, or `items[1].sku`. Dots denote deep navigation into the object graph; bracketed syntax denotes collection/array elements or map keys accordingly.

Suppose a form contains:

~~~java
public class CustomerForm {
    private Address address;

    public Address getAddress() {
        return address;
    }

    public void setAddress(Address address) {
        this.address = address;
    }
}
~~~

And `Address` has a `city` property. When a request sends:

~~~text
address.city=Da Nang
~~~

Spring needs two steps: retrieve `customerForm.address`, then set `city`. But if `getAddress()` returns `null`, how can it set `address.city`?

`autoGrowNestedPaths` is a configuration option on `DataBinder` and related property accessors that allows **auto-creating null intermediate values when possible**, then continuing down the path. This mechanism also supports expanding collections/arrays when accessing an index beyond current bounds, within configured limits.

When enabled and `Address` can be instantiated properly:

~~~text
Before binding:
CustomerForm
└── address = null

Input:
"address.city" = "Da Nang"

After binding:
CustomerForm
└── address = Address
    └── city = "Da Nang"
~~~

When disabled, the intermediate `address` remains `null`. The system cannot set `city` via that path, and depending on the API and invalid-field flags, binding can raise a path access error or skip the field.

**Key takeaway:** auto-grow does not mean Spring can always create every object, is not a dependency-injection mechanism, and does not guarantee valid input. It handles property paths within a specific binding/property-access flow.

## 2. Placing autoGrowNestedPaths properly in Spring

Components to distinguish:

| Component | Role | Relationship to auto-grow |
| --- | --- | --- |
| `org.springframework.validation.DataBinder` | Accepts name–value pairs to apply to a target and manages binding errors | Has `setAutoGrowNestedPaths(boolean)`, defaulting to `true` on a standard binder |
| `org.springframework.web.bind.WebDataBinder` | Extends `DataBinder` for web flows | Inherits auto-grow configuration, normally created by Spring MVC per binding |
| `org.springframework.beans.BeanWrapper` / `BeanWrapperImpl` | Accesses JavaBeans properties via getters/setters | Supports the auto-grow flag; a directly instantiated `BeanWrapperImpl` defaults to `false` |
| `org.springframework.beans.ConfigurablePropertyAccessor` | Configuration contract for property accessors | Declares `setAutoGrowNestedPaths` along with access options |
| `org.springframework.beans.MutablePropertyValues` | Holds input values to bind | Only describes field/value pairs; does not auto-create nested objects itself |
| `org.springframework.validation.BindingResult` | Holds errors and target after binding | Allows inspecting results; does not control auto-grow behavior |
| `org.springframework.core.convert.ConversionService` | Converts source values to target Java types | Converts values once a valid access path exists; does not replace container/nested bean creation |

**Defaults to remember:** per the Spring Framework 6.2 Javadoc, a standard `DataBinder` sets `autoGrowNestedPaths=true`. Conversely, a directly instantiated `BeanWrapperImpl` defaults to `false`. Those two defaults belong to two different layers. Never treat "Spring always enables/disables auto-grow" as an accurate statement.

In Java:

~~~java
DataBinder binder = new DataBinder(new CustomerForm());
System.out.println(binder.isAutoGrowNestedPaths()); // true
binder.setAutoGrowNestedPaths(false);
~~~

This is an illustrative snippet assuming required Spring imports. Changing the flag should happen **before the binder is initialized to access properties/begin binding**. The `DataBinder` Javadoc requires early configuration; once the binding result has been initialized, changing the flag can be rejected due to binder state.

## 3. Under the hood: how is a path expanded?

For example, `customer.address.city` is interpreted as a sequence of operations:

1. Identify target `customer` and the active access mode: JavaBeans property access or direct field access.
2. Read the intermediate property `address`.
3. If `address` is non-`null`, continue into the existing object.
4. If `address == null` and auto-grow is **enabled**, attempt to create a default value for type `Address`.
5. Attach the newly created value onto the intermediate property if the access path permits.
6. Access `city`, convert the source value to the property type, and assign it.

Pseudo-flow example:

~~~text
setPropertyValue("address.city", "Da Nang")
    |
    v
address exists?
    |                         \
    | Yes                      \ No
    v                           v
use current address          autoGrowNestedPaths?
                                | Yes             | No
                                v                 v
                         Create Address?      Cannot proceed
                           | Yes | No         -> error/ignore per API
                           v        v
                         attach   object creation error
                           |
                           v
                   set address.city
~~~

Auto-grow is a mechanism to **populate intermediate objects**; it does not convert `"Da Nang"` directly into an `Address`. If a request sends only key `address` instead of `address.city`, converting an entire string into `Address` involves a suitable `Converter`/`PropertyEditor`. Those two cases are different.

For longer paths such as `customer.address.country.name`, multiple intermediates may need instantiation. If any step lacks instantiation or write capability, the entire path can fail; succeeding at one level does not guarantee remaining levels will succeed.

## 4. Conditions for auto-creating a nested object

Auto-grow can succeed only when all technical conditions are met simultaneously.

### 4.1. The intermediate property must have a resolvable type

Spring needs to know the target type of `address` to instantiate a value. Clear example:

~~~java
private Address address;

public Address getAddress() { return address; }
public void setAddress(Address address) { this.address = address; }
~~~

With a field declared as `Object` or interface `Location`, there is not enough information to know which implementation to instantiate. Spring does not guess between `HomeAddress` and `OfficeAddress`. When needed, the application can **pre-initialize a concrete implementation** or use a DTO with concrete field types.

A nested bean typed as an abstract class or interface usually cannot be instantiated directly from just a property name. If the intermediate value already exists and is a valid implementation, no new creation is needed and binding can continue along the existing object's access path.

### 4.2. The intermediate class needs a suitable way to instantiate

For a typical JavaBean, Spring can attempt to invoke a no-arg constructor to instantiate the object when the property is null. Example class with a no-arg constructor and writable property:

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
~~~

A case that normally cannot auto-create:

~~~java
public class AddressWithoutNoArg {
    private final String city;

    public AddressWithoutNoArg(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}
~~~

With an uninitialized `AddressWithoutNoArg` bean, there is no no-arg constructor for Spring to auto-instantiate under nested property auto-grow. There is no guarantee Spring will guess an argument for `city`. A record or immutable type with parameterized constructors calls for a dedicated binding design rather than relying on JavaBean setter/property auto-grow.

Even when a class has a no-arg constructor, instantiation can still fail if the constructor is private or inaccessible at runtime, throws an exception, or cannot create a compatible target type. The result can be `NullValueInNestedPathException` or a related property access exception, depending on which step failed. Do not assume every auto-grow failure is a standard `typeMismatch`.

### 4.3. The newly created object must be attachable to the graph

Once Spring creates an `Address` for `customer.address`, it must store that object back through an appropriate setter/field accessor.

For default bean property access, proper JavaBeans getters/setters matter. For instance, if there is a getter and no setter at all for `address`, and the field is null, attaching the new object can be blocked. Direct field access takes a different access path, yet must be explicitly enabled and obeys Spring version rules/constraints.

If the property already holds a non-null value, Spring **does not need to create a new instance**. Thus an object with a complex constructor can still have child properties bound if the intermediate object itself was pre-initialized by the application and permits writing the leaf field.

### 4.4. Leaf fields must be writable and values must be convertible

Auto-grow solves `address == null`, but does not solve an `Integer` leaf field receiving `"abc"`. Once `address.zipCode` is reached cleanly, the converter can still fail on invalid input.

For example:

~~~text
address == null
address.zipCode = "abc"
zipCode type = Integer
~~~

Two distinct outcomes can occur:

- `Address` is created, yet `zipCode` is not assigned due to conversion failure.
- `BindingResult` records a `FieldError` such as `typeMismatch` on path `address.zipCode`.

Never treat `address != null` as proof that all input is valid. Business validation (`@Valid`, `@NotBlank`, `@Min`, etc.) is a separate step that runs only when properly configured/triggered by the application.

### 4.5. The path must be allowed for binding

Even with auto-grow enabled, `DataBinder.setAllowedFields(...)` or declarative binding mode can restrict which fields may be assigned.

For example:

~~~java
binder.setAllowedFields("address.city", "address.postalCode");
~~~

This permits the specified property paths in **property binding**. Fields outside the list are suppressed and cannot rely on auto-grow to be assigned. In Spring 6.1+, `setDeclarativeBinding(true)` is an additional option under DataBinder's contract, though it should not be seen as replacing DTO design, constructor binding, or security controls.

## 5. Standalone Java 17+ example with Spring Core/Context

This example requires neither Spring Boot nor a servlet container. It demonstrates two points:

- `DataBinder` can auto-create a null `Address` to handle `address.city`.
- The binder can expand `List<Line>` up to a valid index and instantiate elements of a concrete type when handling `lines[1].sku`.

Prerequisites: **JDK 17+**, Gradle, and access to download dependencies from Maven Central.

Create `settings.gradle`:

~~~groovy
rootProject.name = 'nested-path-autogrow'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.6'
}

application {
    mainClass = 'NestedPathAutoGrowDemo'
}
~~~

Create `src/main/java/NestedPathAutoGrowDemo.java`:

~~~java
import java.util.List;

import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.DataBinder;

public class NestedPathAutoGrowDemo {

    public static class Address {
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

    public static class CustomerForm {
        private Address address;

        public CustomerForm() {
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public static class Line {
        private String sku;

        public Line() {
        }

        public String getSku() {
            return sku;
        }

        public void setSku(String sku) {
            this.sku = sku;
        }
    }

    public static class OrderForm {
        private List<Line> lines;

        public OrderForm() {
        }

        public List<Line> getLines() {
            return lines;
        }

        public void setLines(List<Line> lines) {
            this.lines = lines;
        }
    }

    public static void main(String[] args) {
        CustomerForm customer = new CustomerForm();
        DataBinder customerBinder = new DataBinder(customer, "customerForm");

        System.out.println("autoGrow=" + customerBinder.isAutoGrowNestedPaths());
        System.out.println("addressBefore=" + customer.getAddress());

        customerBinder.setAllowedFields("address.city");

        MutablePropertyValues customerValues = new MutablePropertyValues();
        customerValues.add("address.city", "Da Nang");
        customerBinder.bind(customerValues);

        System.out.println("city=" + customer.getAddress().getCity());
        System.out.println("customerErrors=" +
                customerBinder.getBindingResult().getErrorCount());

        OrderForm order = new OrderForm();
        DataBinder orderBinder = new DataBinder(order, "orderForm");
        orderBinder.setAutoGrowCollectionLimit(3);
        orderBinder.setAllowedFields("lines[1].sku");

        MutablePropertyValues orderValues = new MutablePropertyValues();
        orderValues.add("lines[1].sku", "KB-02");
        orderBinder.bind(orderValues);

        System.out.println("lineCount=" + order.getLines().size());
        System.out.println("secondSku=" + order.getLines().get(1).getSku());
        System.out.println("orderErrors=" +
                orderBinder.getBindingResult().getErrorCount());
    }
}
~~~

Run:

~~~bash
gradle -q run
~~~

If the repository has a Gradle Wrapper, use `./gradlew -q run` on Linux/macOS or `gradlew.bat -q run` on Windows.

**Expected output of the program above with Spring 6.2.6**:

~~~text
autoGrow=true
addressBefore=null
city=Da Nang
customerErrors=0
lineCount=2
secondSku=KB-02
orderErrors=0
~~~

Explanation of the values:

1. `autoGrow=true` indicates a standard binder enables the feature by default; `addressBefore=null` confirms there is no nested object yet.
2. After `bind`, Spring instantiates `Address` and sets `city`, because the concrete type has a no-arg constructor and matching properties.
3. `lineCount=2` is not because the input declared two lines. Spring expanded the collection to reach index 1; Java indices are 0-based.
4. `secondSku=KB-02` confirms the element at index 1 exists and its `sku` field was set.
5. `customerErrors=0` and `orderErrors=0` only state that no binding errors were recorded in this test; they are **not** business validation results.

Note: this example uses a `List<Line>` with a concrete generic element type and an instantiable `Line`. Changing it to `List<?>` or an interface element without a known implementation prevents element creation from being inferred like this. Setting `lines[200].sku` with limit 3 prevents Spring from auto-expanding to element 200.

## 6. When autoGrowNestedPaths=false

Three scenarios must be separated:

### 6.1. Nested object is null

If a new `CustomerForm` has `address == null`, and you configure:

~~~java
DataBinder binder = new DataBinder(customer, "customerForm");
binder.setAutoGrowNestedPaths(false);
binder.bind(values);
~~~

This snippet assumes `customer` and `values` already exist, with `values` containing `address.city`. The binder will not auto-create `Address`. Depending on the accessor and invalid-property option, the assignment can raise `NullValueInNestedPathException` (common in the bean-property accessor) or be ignored if configured to ignore invalid paths. Do not hardcode an assumption that every case produces a `FieldError` or is silently skipped.

To test clearly without relying on MVC exception resolvers, use `BeanWrapperImpl` directly:

~~~java
CustomerForm customer = new CustomerForm();
BeanWrapperImpl wrapper = new BeanWrapperImpl(customer);
wrapper.setAutoGrowNestedPaths(false);
wrapper.setPropertyValue("address.city", "Hue");
~~~

This snippet assumes `org.springframework.beans.BeanWrapperImpl` and `CustomerForm` imports. Because `customer.address` is null, the path cannot continue and typically throws `NullValueInNestedPathException`. This is **error-scenario illustration code**, not a standalone example meant to succeed.

### 6.2. Nested object is already initialized

If you do not want auto-grow, create the nested object intentionally:

~~~java
CustomerForm customer = new CustomerForm();
customer.setAddress(new Address());

DataBinder binder = new DataBinder(customer, "customerForm");
binder.setAutoGrowNestedPaths(false);

MutablePropertyValues values = new MutablePropertyValues();
values.add("address.city", "Hue");
binder.bind(values);
~~~

This snippet belongs in a project with `Address`, `CustomerForm`, and matching imports; it shows that **`false` does not forbid binding nested fields**. It merely avoids auto-populating null intermediates. Because `address` is already allocated, property binding reaches `city` normally.

### 6.3. Collection already has enough elements

If the target already holds a `List<Line>` with two valid `Line` elements, `lines[1].sku` can still be assigned even when auto-grow is off; no new element allocation is needed. Conversely, a list containing only index 0 will not auto-expand to index 1 when the feature is disabled.

Hence the claim "disabling auto-grow makes nested path binding impossible" is false. The outcome depends on **how much of the graph is already initialized** before binding.

## 7. When auto-grow is enabled yet Spring still cannot instantiate

This is the most critical part when troubleshooting real failures.

### 7.1. Missing no-arg constructor

~~~java
public class ImmutableAddress {
    private final String city;

    public ImmutableAddress(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}
~~~

When `customer.immutableAddress == null`, the binder cannot guess what argument to pass to create `ImmutableAddress` via property auto-grow. Do not "fix" this by adding a no-arg constructor that creates an invalid object just to make requests pass.

Appropriate solutions:

- **Intentional initialization** in the form DTO's constructor or factory.
- Use a mutable form DTO with a suitable no-arg constructor solely for property binding, then map it to an immutable domain object.
- Use **constructor binding** per your Spring/MVC version's contract for immutable types when inputs and constructor arguments map cleanly.
- If a polymorphic type is needed, design explicit implementation selection rather than making the binder guess.

Do not equate auto-grow with Spring IoC: `@Component`, `@Autowired`, or a bean with the same name in ApplicationContext does not mean the property accessor pulls that bean to fill a null field.

### 7.2. Abstract/interface types

~~~java
public interface ShippingAddress {
    String getCity();
}
~~~

If `private ShippingAddress address;` is null, there is not enough information to know which class to instantiate. If a concrete implementation object already sits in the field, Spring can read/write properties supported by the accessor depending on the implementation class. Adding an implementation onto the classpath does not automatically select it.

### 7.3. Read-only, final, or non-JavaBeans properties

For example:

~~~java
public class ReadOnlyCustomer {
    private Address address;

    public Address getAddress() {
        return address;
    }
}
~~~

If `address` is null and bean property access is active, Spring can determine the type yet lacks a setter to attach a new object. Having a matching field name does not grant Spring permission to write it. `initDirectFieldAccess()` uses a different mechanism, though it is not a universal fix, especially with final fields or immutable objects.

### 7.4. Constructor throws an exception

A class with a no-arg constructor that throws an error or executes dangerous side effects will cause auto-grow to fail. Constructors on DTOs used for binding should be lightweight, clean, and free of database/network dependencies or external request state.

### 7.5. Intermediate created, yet leaf field cannot be set

Spring might create `address` and still fail to assign `address.zipCode` because:

- missing setter/writable property;
- string-to-field-type conversion failed;
- setter checks invariants and throws an exception;
- field is absent from the allowlist or blocked by declarative binding rules;
- nested collection/map has mismatched element types.

Do not conclude "autoGrowNestedPaths is not working" merely because the leaf field lacks a value. Inspect the post-bind object graph and actual `BindingResult` or exceptions.

## 8. Collection auto-expansion and autoGrowCollectionLimit

### 8.1. Common path forms

| Path | Meaning | When auto-grow is needed |
| --- | --- | --- |
| `address.city` | `address` object with `city` field | When `address` is null |
| `items[0].sku` | `sku` field of the first list/array element | When container or element at index 0 does not exist yet |
| `items[3].quantity` | Field on element at index 3 | When list/array does not yet have enough elements |
| `settings[theme]` | Value under a map key | When map/container must be created; maps do not behave identically to list indices |
| `items[1].address.city` | Multiple levels across list and bean | Whenever any intermediate is still null |
| `matrix[0][1]` | Element in nested containers | When type metadata and instantiation across levels permit |

Spring supports common path forms, though auto-creation capability depends on collection type, generic element type, setter/accessor, and version. Do not assume every `Set` or complex map structure supports indexed access semantics like `List`.

### 8.2. Default limit of 256

`DataBinder.DEFAULT_AUTO_GROW_COLLECTION_LIMIT` equals **256** in Spring 6.2. Its goal is to prevent inputs like `items[999999].name` from requesting an excessively large element allocation, wasting memory.

~~~java
DataBinder binder = new DataBinder(orderForm);
binder.setAutoGrowCollectionLimit(16);
~~~

This is a snippet; call it before the binder is initialized/bound. A limit of 16 means array/collection auto-grow rules will not auto-expand past the allowed index range (typically indices 0–15). It is **not** a limit on total HTTP request fields or business validation of item counts.

For example:

~~~text
Initial collection: []
autoGrowCollectionLimit = 3

items[0].sku = "A"  -> can create element at index 0
items[1].sku = "B"  -> can expand to size 2
items[2].sku = "C"  -> can expand to size 3
items[3].sku = "D"  -> exceeds chosen growth limit
~~~

This illustrates a list with an instantiable element type. For an index out of bounds, the exact failure depends on the property accessor and call path; avoid guaranteeing a specific HTTP status or MVC exception class from this setting alone.

Per the `DataBinder` 6.2 Javadoc, this limit applies to property/field injection via `bind(PropertyValues)`, **does not apply to constructor binding** via `construct(...)`, and is not a general limit on map keys. Check documentation for your exact version if running a newer release, as field injection behavior can evolve. Never raise the limit arbitrarily to "fix" abnormal inputs.

### 8.3. Why is List<T> easier to auto-grow than List<?>?

When processing `lines[1].sku`, Spring must know which class the second element has so it can invoke its constructor and reach `sku`. With `List<Line>`, the generic element type identifies the element class. With a raw `List`, `List<?>`, insufficient wildcard info, interface/abstract element types, or non-instantiable elements, success is not guaranteed.

This is another reason DTOs should declare concrete element types:

~~~java
private List<Line> lines;
~~~

Instead of overusing:

~~~java
private List<Object> lines;
~~~

If design requires different subtypes, initialize them intentionally or convert input in a controlled way rather than letting clients pick classes to instantiate via property names.

### 8.4. Map cases

With `Map<String, Line> linesByCode`, Spring can create a suitable map container when the map is null and metadata provides enough information. However, key `"ABC"` differs from a numeric list index: adding a key to a map does not require creating intermediate keys. `autoGrowCollectionLimit` is not a mechanism to limit the number of Map keys.

This matters for security: you cannot rely on the collection limit to throttle a form sending thousands of map keys. Enforce request limits, entry counts, and allowed fields per use case.

## 9. autoGrowNestedPaths and constructor binding

Spring 6.1+ provides `DataBinder.construct(DataBinder.ValueResolver)` to construct objects from constructors/constructor parameters. This is a different path from `bind(PropertyValues)`, which sets properties on an existing target.

Spring 6.2 Javadoc explicitly states `setAutoGrowNestedPaths` and `setAutoGrowCollectionLimit` apply to setter/field injection via `bind(PropertyValues)`; **they do not apply to constructor binding** via `construct(...)`.

Comparison:

| Aspect | Property binding + auto-grow | Constructor binding |
| --- | --- | --- |
| Target | Typically already has a root object | Can create a new target via constructor |
| Assignment path | Getters/setters or field accessor | Resolved constructor parameters |
| Nested null | Can auto-create intermediate beans if conditions are met | Object graph built via constructor/nested constructor binding per its own rules |
| Mutable DTO | Usually a good fit | Can be used but not required |
| Immutable record/class | Not easily handled via setter auto-grow without a mutable target | Often a better fit when constructor binding is configured properly |
| autoGrowNestedPaths | Applies | Does not govern this mechanism |
| autoGrowCollectionLimit | Caps collection growth in property binding | Not a general cap applied here |

Example:

~~~java
public record AddressInput(String city) {
}

public record CustomerInput(AddressInput address) {
}
~~~

That is an immutable model. Do not treat `setAutoGrowNestedPaths(true)` as a way to ask Spring to build `AddressInput` via constructors in all situations. To bind onto records, verify constructor binding flow and parameter names supported in your MVC version. Likewise, validation annotations on records are checked separately after the object is constructed under proper conditions.

## 10. Interaction with WebDataBinder and Spring MVC

### 10.1. @InitBinder scoped at the controller level

In Spring MVC, `WebDataBinder` configures the binder per request/attribute. The snippet below is **integration** code in a controller, not a standalone Java program:

~~~java
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;

@InitBinder("customerForm")
public void initCustomerBinder(WebDataBinder binder) {
    binder.setAutoGrowNestedPaths(true);
    binder.setAutoGrowCollectionLimit(16);
    binder.setAllowedFields("name", "address.city", "address.postalCode");
}
~~~

Here:

- `@InitBinder("customerForm")` targets binders with the matching object name.
- `setAutoGrowNestedPaths(true)` enables auto-creating intermediate properties when conditions are met.
- `setAutoGrowCollectionLimit(16)` caps array/list/collection auto-expansion as described.
- `setAllowedFields(...)` restricts bindable property paths.

Place these settings in `@InitBinder` so they execute **before Spring performs binding**. Do not change settings after a controller has already received a `BindingResult` for the current request and expect bound data to be recomputed.

### 10.2. @ModelAttribute and field paths from forms

Suppose the DTO has `CustomerForm.address` initially null. In an HTML form:

~~~html
<form method="post" action="/customers">
    <input name="name" value="Lan">
    <input name="address.city" value="Da Nang">
    <input name="address.postalCode" value="550000">
    <button type="submit">Save</button>
</form>
~~~

With controller:

~~~java
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/customers")
public String save(
        @ModelAttribute("customerForm") CustomerForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return "customer/form";
    }
    return "redirect:/customers/success";
}
~~~

This is a snippet inside a `@Controller` class and requires the DTO, view engine, target route, and matching MVC configuration. Spring uses dotted field names to bind nested properties. If auto-grow is enabled and `Address` is instantiable, the controller can receive `form.getAddress().getCity() == "Da Nang"`.

`BindingResult` must be placed **immediately after** the corresponding `@ModelAttribute` parameter if the controller reads errors for that object. Failures due to non-existent nested paths can occur before reaching the controller or be handled per binder configuration; not every failure is guaranteed to land in `BindingResult`.

### 10.3. Global enable/disable

Some applications configure `WebBindingInitializer`/`ConfigurableWebBindingInitializer` to apply global policies across created binders. This impacts many endpoints, so regression-test after changes.

Never create a singleton `DataBinder` bean and share it across requests; binder/result instances are tied to a **specific target and binding invocation**. Put global policies in the proper MVC config while keeping per-request state on per-request binders.

### 10.4. @RequestBody JSON is a separate flow

When a controller accepts:

~~~java
@PostMapping("/customers/json")
public void create(@RequestBody CustomerForm input) {
    // ...
}
~~~

JSON is read via `HttpMessageConverter` and a JSON deserializer, usually Jackson. Jackson has its own rules for building nested objects; enabling `WebDataBinder.setAutoGrowNestedPaths(true)` **does not control how Jackson deserializes nested JSON objects**. If nested JSON objects fail, check serializers/deserializers, constructors, record support, and mapper settings for your version.

This is a common reason developers toggle auto-grow and see no change in JSON APIs. Separate *form/query binding* from *body deserialization* before making changes.

## 11. Safety, performance, and data design limits

### 11.1. Never let clients build unbounded object graphs

A request sending field names like:

~~~text
orders[99999].items[99999].sku=ATTACK
customer.internalRole=ADMIN
shippingAddress.owner.permissions[1]=WRITE
~~~

can force the binder to traverse deeply or expand the graph unexpectedly if those paths are allowed. The default collection limit mitigates one class of risk, yet **does not cover all risks**: deep graphs can allocate many objects; maps do not share the same index limit semantics; CPU/memory and field-name lengths also feel request load.

Practical safeguards:

1. **Use dedicated form DTOs** containing only fields users are permitted to enter, instead of binding directly onto domain entities with role flags, payment states, or internal fields.
2. **Restrict allowed fields** or use scoped declarative binding, avoiding overly broad wildcards in nested structures.
3. **Keep collection limits aligned with business rules**; if a screen allows at most 10 items, do not raise the limit to tens of thousands.
4. **Limit request size/field count** at the HTTP layer and validate collection/map sizes after binding against business rules.
5. **Review nested path depth** controllable from outside; if your framework/version offers depth limits, consult that version's exact API rather than guessing.
6. **Do not treat auto-grow as validation**. After binding, still enforce data constraints and authorization checks.
7. **Separate domain invariants from form initialization** so you never instantiate invalid immutable entities solely for binding.

### 11.2. Auto-grow limit is not a business limit

Suppose a form allows at most 5 order lines:

~~~java
binder.setAutoGrowCollectionLimit(5);
~~~

That alone does not verify the user submitted 5 or fewer order lines, does not limit map keys, does not guarantee all lines are valid, and does not replace `@Size(max = 5)` or business logic. If data already contains more than 5 elements, the auto-grow limit will not trim them down.

### 11.3. Constructor cost and side effects

Nested DTOs should have simple constructors. If a constructor registers events, hits a database, or allocates heavy resources, a request with many nested paths can trigger cascading side effects when the binder instantiates objects. That is a design smell: separate data-transfer classes from domain services.

## 12. Diagnosing when a nested property is not created

Check in a repeatable sequence:

**Step 1: Confirm the input type.** Is the request form/query via `@ModelAttribute`, a manually invoked binder, or `@RequestBody` JSON? Debug the right layer.

**Step 2: Record the exact path.** For example, `address.city` differs from `customer.address.city`. With a binder rooted at `customer`, data keys are normally `address.city`, without repeating the root object name at the start.

**Step 3: Check the flag and configuration timing.** What is `binder.isAutoGrowNestedPaths()`? Did `@InitBinder` or an initializer call `setAutoGrowNestedPaths(false)`? Was the flag set before binding started?

**Step 4: Inspect the pre-bind graph.** Is `getAddress()` null or already holding an instance? If already present, auto-grow is not the primary cause of a leaf-write failure.

**Step 5: Inspect classes and property descriptors.** Is the field type concrete? Does it have an accessible no-arg constructor? Are getters/setters or field access available for intermediates and the leaf? Is it a record/immutable type needing constructor binding?

**Step 6: If indexed, inspect the collection.** Does the index exceed `autoGrowCollectionLimit`? Is the list element type known? Is it a List/array or a Map? Never apply List limits to Maps.

**Step 7: Check allowlist and binding mode.** Are `setAllowedFields`, `setDisallowedFields`, or `setDeclarativeBinding` blocking the path? With `BindingResult.getSuppressedFields()`, inspect rejected fields, keeping in mind suppressed fields **do not automatically become FieldErrors**.

**Step 8: Distinguish exceptions from errors.** `NullValueInNestedPathException`, `NotWritablePropertyException`, conversion errors, and `FieldError` signal different causes; check the root cause and actual field path before applying a fix.

**Step 9: Minimal reproduction.** Build a DTO with exact field types and a standalone `DataBinder`; bind a single path. If that works, the cause likely lies in MVC/controller configuration or the real DTO.

**Step 10: Confirm version.** Spring 6.2 Javadoc clarifies the flag's scope across property/field injection and constructor binding. Older or newer versions may differ in accessor details; check your resolved dependency rather than only reading "current" docs.

Symptom table:

| Symptom | Common cause | How to verify/fix |
| --- | --- | --- |
| `address` stays null after bind | Auto-grow off, field suppressed, wrong path, or binder did not receive input | Check flag, `getSuppressedFields()`, and request keys |
| `NullValueInNestedPathException` | A path segment is null and cannot/may not auto-grow | Check null intermediate, constructor, setter |
| Cannot instantiate nested class | Missing suitable no-arg constructor, abstract/interface type, constructor throws | Pre-initialize explicitly, use mutable DTO, or proper constructor binding |
| `lines[1].sku` does not bind | Collection limit, unclear list element type, uncreatable element | Check generic type, limit, and index |
| `address.zipCode` gets typeMismatch | Path reached, yet parsing value failed | Check converters/formatters and `BindingResult` |
| Nested field missing on object | Missing getter/setter or wrong property name | Check JavaBeans descriptors, field names |
| DTO created yet validation fails | Successful binding does not mean valid data | Read constraint violations/`FieldError` |
| Changing flag has no effect on JSON | Jackson, not `WebDataBinder`, builds nested objects | Check JSON deserializer and request type |
| Raising collection limit still fails | Constructor, path, security, type, nested depth, or field allowlist error | Analyze each intermediate rather than raising limit further |

## 13. Regression tests to include

A good test distinguishes "Spring created the nested object" from "data was assigned accurately" and "input was accepted."

| Case | Initial state | Auto-grow | Expected outcome to verify |
| --- | --- | --- | --- |
| Mutable bean with no-arg constructor | `address=null` | On | `address` is created, `city` is set |
| Same bean | `address=null` | Off | `address` is not created; error or ignore per config |
| Pre-built nested object | `address=new Address()` | Off | Can still bind `address.city` |
| Immutable nested lacking no-arg | `address=null` | On | Do not assume creation succeeds; assert exception |
| Read-only intermediate field | `address=null` | On | Cannot automatically attach new instance |
| List with generic element class | `lines=null`, bind index 1 | On | Verify container, size 2, and target element |
| Index above limit | Empty list, bind index 200 with limit 3 | On | Does not auto-expand to index 200 |
| List with two elements ready | Bind index 1 | Off | Still binds if element and field are writable |
| Path outside allowlist | `role.permissions[0]` | On | Unauthorized field is not written |
| Mistyped nested field | `address.zipCode="abc"`, target is `Integer` | On | Intermediate object may be created, yet conversion error exists |
| `@RequestBody` JSON | JSON with nested object | WebDataBinder on/off | Do not attribute JSON deserialization to this flag |
| Immutable DTO | Constructor binding | Flag on/off | Test constructor object-creation path separately |

### 13.1. Suggested DataBinder test

With JUnit 5 in an app having Spring and test dependencies, core assertions:

~~~java
@Test
void growsNullAddress() {
    CustomerForm form = new CustomerForm();
    DataBinder binder = new DataBinder(form);

    MutablePropertyValues values = new MutablePropertyValues();
    values.add("address.city", "Hue");

    binder.bind(values);

    assertNotNull(form.getAddress());
    assertEquals("Hue", form.getAddress().getCity());
    assertFalse(binder.getBindingResult().hasErrors());
}
~~~

This is an **integration test method**, requiring imports for `org.junit.jupiter.api.Test`, static `Assertions.*`, `DataBinder`, `MutablePropertyValues`, and the example DTOs. It is not a standalone Java file. This test proves auto-grow works for a concrete type; if the DTO becomes a record or class lacking a no-arg constructor, results must be re-evaluated.

### 13.2. A test to prove boundaries

Beyond the default test, add a test with the flag off and `Address` null, then a test with `Address` pre-initialized. Use `assertThrows` only after checking the exact exception type thrown by your API/version; never copy exception assertions from `BeanWrapperImpl` into an MVC test assuming every exception resolver behaves identically.

For collections, test an index near the limit and an index above the limit. Avoid testing huge requests in live environments before configuring resource caps; use a small limit like 3 to reproduce safely.

## 14. Common misconceptions

**"Enabling auto-grow lets Spring instantiate any class."** False. It needs a resolvable type, a valid instantiation path, a place to attach the instance, and a writable leaf field.

**"Having a parameterized constructor is enough."** Not for standard JavaBean property auto-grow. Spring does not invent constructor arguments for a null nested property on this path.

**"Disabling auto-grow forbids nested binding."** False. An existing nested object can still be navigated and have its inner fields set.

**"BeanWrapper and DataBinder share the same default."** False. Direct `BeanWrapperImpl` defaults to false; standard `DataBinder` defaults to true per their Javadocs.

**"Collection limit is the maximum number of form items."** False. It only caps auto-expansion of eligible collections/arrays during binding; business validation must enforce valid item counts.

**"Failing to create a nested bean must mean a missing Converter."** Not necessarily. Distinguish a missing intermediate instance from a missing converter on the leaf field.

**"Auto-grow handles nested JSON objects in @RequestBody."** False. JSON deserialization belongs to the message converter/JSON mapper.

**"Changing auto-grow after bind fixes previous results."** False. Configuration must be applied before binding; changing settings does not replay requests and may be rejected by the binder.

**"If a field is allowed, every field nested inside it is safe."** False. Explicitly control exact accepted property paths and run separate validation/authorization checks.

**"Spring creating an object means it is valid."** False. Auto-grow only resolves graph structure; Bean Validation and business logic must verify resulting state.

**"Just set autoGrowCollectionLimit very high to stop errors."** False. That risks large memory allocations and does not solve constructor/property errors or map keys.

**"Nested path errors always go into BindingResult."** False. Depending on cause and setters/accessors, some errors surface as exceptions; inspect stack traces and `ignoreInvalidFields` when relevant.

## 15. Checklist for real projects

Before relying on `autoGrowNestedPaths` for a form with deep paths, answer:

1. Is the input `@ModelAttribute`/form/query or `@RequestBody` JSON?
2. What exact property paths are submitted? Does any mistakenly include the root object name at the front?
3. Was auto-grow configured on `DataBinder`/`WebDataBinder` before binding?
4. Is the nested type an instantiable concrete class with a suitable no-arg constructor, or an interface/abstract/record?
5. Are getters/setters or field access available to attach intermediate objects?
6. If the target already holds objects, why is auto-grow still needed?
7. For `List<T>`, is the generic element type clear and instantiable?
8. Is the input index within the chosen `autoGrowCollectionLimit`?
9. Are a field allowlist, dedicated DTO, request limits, and business validation in place?
10. Are `BindingResult`, suppressed fields, post-bind object graph, and exception root causes all checked?
11. Have you tested null nested, pre-initialized nested, flag on/off, conversion failure, and index over limit?
12. Have you checked the Javadoc for the exact Spring Framework version your application runs?

## 16. Primary references

- [Spring Framework 6.2 – DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html) — `setAutoGrowNestedPaths`, `setAutoGrowCollectionLimit`, defaults, and scope.
- [Spring Framework 6.2 – BeanWrapper Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapper.html) — property access API and nested property paths.
- [Spring Framework 6.2 – BeanWrapperImpl Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/BeanWrapperImpl.html) — JavaBeans accessor and configuration.
- [Spring Framework – BeanWrapper and property editors](https://docs.spring.io/spring-framework/reference/core/validation/beans-beans.html) — property access and type conversion mechanism.
- [Spring Framework – Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html) — binding property paths.
- [Spring Framework – Spring MVC @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html) — configuring binders in controllers.
- [Spring Framework – Spring MVC @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html) — argument binding model.
- [Spring Framework – Validation, Data Binding and Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation.html) — overview.

**Key takeaway:** `autoGrowNestedPaths=true` allows the binder to instantiate **null intermediate objects** and expand collections when Spring can resolve, construct, and attach those objects. When a suitable constructor is missing, a property is non-writable, a type is abstract, generics are unclear, or an index exceeds the limit, auto-grow cannot "fix" the structure on its own. Use dedicated DTOs, configure early, restrict fields and collections, and inspect both the object graph and binding errors to diagnose accurately.
