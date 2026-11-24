# Nested Paths and PropertyAccessor in SpEL

Spring Expression Language (SpEL) can access nested properties by chaining property names with dots. A path like `customer.address.city` lets an expression move from the root object to customer, then to address, and then retrieve city. Each access step is performed through a **PropertyAccessor** suited to the current object.

Understanding nested paths and PropertyAccessor helps you read or update an object graph clearly, handle null cases properly, and choose the right EvaluationContext for data binding.

## 1. What Is a Nested Path?

A nested path is a path consisting of multiple consecutive properties separated by dots:

    customer.address.city

Suppose the root object is an Order, which has a `customer` property; Customer has an `address` property; Address has a `city` property. The expression above reads three levels of properties in sequence and returns the city name.

Nested paths can be used in many operations:

    customer.address.city
    customer.contact.email
    shippingAddress.postalCode
    items[0].product.name

Nested paths let expressions access required data directly without calling each getter in Java. Property names are usually JavaBean property names—for example, `name` corresponds to getter `getName()`, or `active` corresponds to Boolean getter `isActive()` or `getActive()`.

Property paths and method invocation are two different mechanisms. `customer.name` reads the `name` property; `customer.getName()` is an explicit method call.

## 2. How SpEL Evaluates Each Property Level

When evaluating `customer.address.city`, SpEL does not look up the entire string as a single property name. It proceeds step by step:

1. Start from the root object or current target.
2. Find a way to read the `customer` property on that object.
3. Use the customer value just read as the target for the next step.
4. Read the `address` property on customer.
5. Use address as the target to read the `city` property.

Each step can use a PropertyAccessor matching the current object's type. Therefore, a nested path can traverse multiple different object types, as long as the context has accessors capable of handling each type.

For example:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    ExpressionParser parser = new SpelExpressionParser();

    String city = parser.parseExpression(
            "customer.address.city"
    ).getValue(context, String.class);

The root object is order; the final result is the city of the customer attached to order.

If an intermediate property returns null, SpEL cannot continue accessing subsequent properties on null. You need to check for null or use safe navigation at the exact positions that can be null.

## 3. PropertyAccessor Is Responsible for Reading and Writing

EvaluationContext holds a list of PropertyAccessor instances. An accessor defines which targets it supports, which properties can be read/written, and how the operation is performed.

The main methods of the interface:

| Method | Role |
|---|---|
| `getSpecificTargetClasses()` | Declares target classes supported by the accessor |
| `canRead(context, target, name)` | Checks whether the property can be read |
| `read(context, target, name)` | Reads the property value |
| `canWrite(context, target, name)` | Checks whether the property can be written |
| `write(context, target, name, newValue)` | Writes a new value to the property |

When SpEL needs to read a property, it looks for an accessor that can read that target and property name. When assigning a value, it needs an accessor that supports writing. If no suitable accessor exists, or the property does not exist / cannot be accessed, evaluation fails.

Distinguish technical capability from business permission. `canWrite` indicates that the accessor can write the property according to its configuration; it does not prove that the caller is permitted to modify the data. Write permissions must be controlled at the application layer or inside the accessor's policy.

## 4. ReflectivePropertyAccessor and JavaBean Properties

StandardEvaluationContext includes ReflectivePropertyAccessor by default to access properties via reflection. For typical JavaBeans, the accessor can read properties through getters and write through matching setters.

Example class:

    public class Customer {
        private String name;
        private Address address;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

An expression can read:

    name
    address.city

And it can write properties if the accessor supports writing, the property has a matching setter, and intermediate objects already exist:

    name = 'Lan'
    address.city = 'Ho Chi Minh City'

Not every property can be written. A property with only a getter can usually be read but cannot be assigned through the accessor. A property with a private or inaccessible setter may also fail write requirements depending on the accessor and configuration.

For fields or special object types, accessibility depends on the PropertyAccessor used. Do not assume every field in Java automatically becomes a property that SpEL can access.

## 5. Reading Nested Paths with SimpleEvaluationContext

When the use case is mainly data binding and reading properties, SimpleEvaluationContext can restrict the enabled feature set. The read-only data binding builder provides a PropertyAccessor suited for reading:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    String city = parser.parseExpression(
            "customer.address.city"
    ).getValue(context, String.class);

This approach suits expressions that only need to read data from an object graph. SimpleEvaluationContext does not provide all the features of StandardEvaluationContext; it is designed for use cases needing a narrower access scope.

If you need to write properties via data binding, you can use the read-write builder:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

Choosing read-write only opens write capability for properties supported by the accessor. The application still needs to verify the caller, the target, and which properties are allowed to be updated.

## 6. Writing Values to a Nested Path

You can use the assignment operator in an expression or the `Expression.setValue` API to update a property.

Example with a read-write context:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    parser.parseExpression("customer.address.city")
            .setValue(context, "Da Nang");

SpEL follows the nested path to locate the final property, then uses the accessor to write the value into `city`. If the target property type differs from the source value type, EvaluationContext's TypeConverter can help perform conversion.

An assignment expression can also be evaluated:

    parser.parseExpression(
            "customer.address.city = 'Da Nang'"
    ).getValue(context);

Both approaches can mutate the object. Use them only when the context is configured with appropriate write permissions and the application has verified that the update operation is permitted.

## 7. Null Intermediate Objects in Nested Paths

A normal nested path requires each intermediate object to exist. For example:

    customer.address.city

If `customer` is null, SpEL cannot read `address`. If customer exists but `address` is null, SpEL cannot read `city`.

Safe navigation can be used to handle steps that may be null:

    customer?.address?.city

If customer is null or address is null, the result of the safe access chain is null instead of continuing to access properties on null.

If a default value is needed, the Elvis operator can be used:

    customer?.address?.city ?: 'Unknown'

Safe navigation only protects the step where the operator is placed. If a potentially null level is skipped, an error can still occur at that level. Place `?.` at every object boundary that can be null.

For assignment, safe navigation does not automatically create intermediate objects. If customer or address does not exist yet, initialize them in Java or a business service before writing the final property.

## 8. Combining Nested Paths with Indices and Map Keys

Nested paths can be combined with index operators to traverse lists, arrays, or maps:

    items[0].product.name
    orders[1].customer.email
    attributes['shipping'].city

In the first example, SpEL gets the first element of the `items` list, then reads product and name. In the last example, SpEL retrieves the value by key `shipping` from the `attributes` map, then reads city.

List and array indices start at 0; maps are accessed by key. If an index is out of bounds, a key does not exist, or an intermediate value is null, the expression may return null or throw an error depending on the operation and data structure.

For dynamic data, ensure the collection is non-null, the index is within range, and intermediate objects exist before reading or writing deeper properties.

## 9. Custom PropertyAccessor

If the model is not a standard JavaBean or needs a custom policy, you can implement a custom PropertyAccessor. For example, an accessor can read properties from a dynamic record-like object or restrict which properties are allowed to be accessed.

Illustrative structure:

    public final class CustomerPropertyAccessor
            implements PropertyAccessor {

        @Override
        public Class<?>[] getSpecificTargetClasses() {
            return new Class<?>[] { Customer.class };
        }

        @Override
        public boolean canRead(
                EvaluationContext context,
                Object target,
                String name) {
            return target instanceof Customer
                    && isAllowedProperty(name);
        }

        @Override
        public TypedValue read(
                EvaluationContext context,
                Object target,
                String name) throws AccessException {
            Customer customer = (Customer) target;
            return readCustomerProperty(customer, name);
        }

        @Override
        public boolean canWrite(
                EvaluationContext context,
                Object target,
                String name) {
            return target instanceof Customer
                    && isWritableProperty(name);
        }

        @Override
        public void write(
                EvaluationContext context,
                Object target,
                String name,
                Object newValue) throws AccessException {
            Customer customer = (Customer) target;
            writeCustomerProperty(customer, name, newValue);
        }
    }

The helper methods `isAllowedProperty`, `readCustomerProperty`, `isWritableProperty`, and `writeCustomerProperty` are application-implemented logic, not built-in Spring APIs. A real accessor must check the target, property name, data type, new value, and policy before writing.

The accessor can be registered on StandardEvaluationContext:

    StandardEvaluationContext context =
            new StandardEvaluationContext(customer);

    context.addPropertyAccessor(
            new CustomerPropertyAccessor()
    );

For a nested path traversing multiple classes, accessors must support the right target type at each level. If it only supports Customer while the path continues into Address, another accessor or suitable mechanism is needed to handle Address.

## 10. Order and Scope of Multiple PropertyAccessors

An EvaluationContext can contain multiple PropertyAccessors. This is useful when an expression needs to access multiple object types, such as JavaBeans, Maps, or application-specific models.

When adding a custom accessor, clearly define the classes and properties it supports. Avoid overly broad accessors that always return true for every target/property, because they can take over handling properties meant for another accessor.

If multiple accessors can handle the same target and property, search order can affect which accessor is used. Configure the accessor list intentionally and test overlapping scopes. Do not rely on implicit ordering if two accessors behave differently.

For sensitive or writable properties, an accessor should explicitly reject names not in an allowlist. The fact that a property exists on an object does not mean an expression in the current use case is permitted to access or update it.

## 11. Type Conversion When Writing Properties

When writing to a property with a specific target type, the source value may need to be converted. EvaluationContext's TypeConverter supports conversion in appropriate cases.

For example, the `quantity` property is Integer, while the passed value is a string:

    parser.parseExpression("quantity")
            .setValue(context, "12");

If the converter supports String to Integer, the property can receive the value 12. If it cannot be converted, the write operation fails.

Type conversion does not replace business validation. A string may convert to a valid number yet still exceed quantity limits. Validate data before updating and handle conversion errors explicitly.

With a nested path, conversion applies to the final property being written. Intermediate objects must still resolve successfully before SpEL can reach the target property.

## 12. Complete Example in Java

The following example reads and updates the shipping address city:

    public class Address {
        private String city;

        public String getCity() {
            return city;
        }

        public void setCity(String city) {
            this.city = city;
        }
    }

    public class Customer {
        private Address address;

        public Address getAddress() {
            return address;
        }

        public void setAddress(Address address) {
            this.address = address;
        }
    }

    public class Order {
        private Customer customer;

        public Customer getCustomer() {
            return customer;
        }

        public void setCustomer(Customer customer) {
            this.customer = customer;
        }
    }

    Order order = loadOrder();

    SimpleEvaluationContext readContext =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    String city = parser.parseExpression(
            "customer.address.city"
    ).getValue(readContext, String.class);

    SimpleEvaluationContext writeContext =
            SimpleEvaluationContext.forReadWriteDataBinding()
                    .withRootObject(order)
                    .build();

    parser.parseExpression("customer.address.city")
            .setValue(writeContext, "Can Tho");

The example assumes order, customer, and address are already initialized. If an intermediate object is null, handle it before reading or writing the nested path. In a real application, use a business service to load the object, check permissions, and ensure valid state before updating.

## 13. Common Errors

- **Property does not exist:** check the JavaBean property name and matching getter/setter.
- **Null intermediate object:** check each level or use safe navigation when reading.
- **Writing to a read-only property:** confirm the accessor supports write and the property has a matching setter.
- **Confusing properties with methods:** `customer.name` reads a property; `customer.getName()` invokes a method.
- **Using the wrong context:** read-only SimpleEvaluationContext does not permit writing properties.
- **Invalid index or map key:** check bounds and keys before continuing a nested path.
- **Converter does not support target type:** normalize data or configure an appropriate converter.
- **Overly broad custom accessor:** restrict the target classes and properties allowed to be handled.
- **Assuming assignment auto-creates intermediate objects:** initialize customer/address in Java before assigning deep properties.

## 14. Takeaways

Nested paths let SpEL traverse multiple properties using dots, such as `customer.address.city`. SpEL resolves each level on the current object using a PropertyAccessor; ReflectivePropertyAccessor usually handles JavaBean properties in StandardEvaluationContext. SimpleEvaluationContext provides read-only or read/write data binding modes with a narrower feature scope. When reading nested paths, handle null at each level; when writing, every intermediate object must exist and the accessor must support writing the target property. If the model or policy is specialized, use a custom PropertyAccessor with clear target and property scopes.
