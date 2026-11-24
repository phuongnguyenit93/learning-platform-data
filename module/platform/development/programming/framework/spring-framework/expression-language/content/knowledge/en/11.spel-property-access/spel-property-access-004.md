# Properties of the Root Object and Intermediate Objects

In SpEL, an expression typically begins by reading a property of an input object. The default input object is called the root object. From the root object, the expression can traverse through multiple properties to reach nested objects inside. Those objects that appear along the middle of the path are called intermediate objects.

For example, with the path:

    customer.address.city

SpEL reads the customer property on the root object, obtains the Customer object, then reads address to obtain Address, and finally reads city on the Address object. Clearly understanding the root object and intermediate objects helps identify where an expression reads data from, why a path can fail when encountering null, and how to use #root or #this in collection operations.

## 1. What is the root object?

The root object is the starting object that SpEL uses when evaluating an expression. It is provided through an EvaluationContext or directly in the getValue call.

Suppose the application has an order model:

    public class Order {
        private Customer customer;
        private BigDecimal total;

        public Customer getCustomer() {
            return customer;
        }

        public BigDecimal getTotal() {
            return total;
        }
    }

    public class Customer {
        private Address address;
        private String name;

        public Address getAddress() {
            return address;
        }

        public String getName() {
            return name;
        }
    }

    public class Address {
        private String city;

        public String getCity() {
            return city;
        }
    }

If Order is the root object, the expression can directly read its properties:

    customer
    total
    customer.name

Property names do not need the # prefix when accessing from the root object. Thus, customer.name means reading the customer property of the root, then reading name on the resulting customer object.

You can explicitly write the starting point using the built-in variable #root:

    #root.customer.name
    #root.total

Both customer.name and #root.customer.name have the same starting point when the root object is Order. The explicit form is useful when an expression has many intermediate objects or when inside selection/projection and needing to distinguish the root from the current object.

## 2. Providing the root object to an expression

There are two common ways to provide a root object.

### Setting the root object in EvaluationContext

    Order order = orderService.findOrder(orderId);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("customer.address.city");

    String city = expression.getValue(context, String.class);

When creating StandardEvaluationContext with order, that object becomes the root object. The expression does not need to receive order again on every getValue call.

You can change the context's root object using setRootObject if needed, but you should control the context lifecycle so you do not accidentally evaluate multiple requests on the same context with mutable state.

### Passing the root object when calling getValue

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
            parser.parseExpression("customer.address.city");

    String city = expression.getValue(context, order, String.class);

In this approach, order is passed directly into the evaluation call. SimpleEvaluationContext is appropriate for examples that only need to read properties. Choosing the context depends on the capabilities the expression needs; if the expression needs type references, bean references, or broader features, you must configure the context accordingly.

Whichever approach you choose, the key is knowing exactly which object is serving as the root object at evaluation time. A syntactically valid expression can still fail if the root object does not have the property the expression requires.

## 3. Root object properties and intermediate object properties

A property path is a chain of consecutive property accesses separated by dots.

    customer.address.city

It can be broken down step by step:

1. customer is read on the root object Order.
2. The result of customer is a Customer object; this object becomes the target for the next step.
3. address is read on Customer.
4. The result of address is an Address object.
5. city is read on Address and becomes the final result.

Thus, only the first property customer is read directly on the root object. address and city belong to intermediate objects returned by the preceding step.

A longer path follows the same principle:

    customer.address.country.region.code

Each dot shifts access to the object returned by the property immediately before it. If a step returns a type that lacks the next property, SpEL cannot continue the path and will raise an evaluation error.

This distinction is helpful when reading error messages. If the message reports that the city property cannot be found, check the type of the object immediately preceding .city, rather than checking only the initial root object's type.

## 4. How does SpEL access JavaBean properties?

In expressions, a property name usually corresponds to a JavaBean getter. For example:

    order.customer
    order.total

are typically resolved via getCustomer() and getTotal(). For a Boolean property with an isActive() getter, the property name is active:

    customer.active

You do not need to call the getter as a method:

    customer.getName()

That is property access syntax, whereas method call syntax is a different operation:

    customer.getName()

Both may yield the same value in a standard JavaBean, but when the goal is to read a property, use the concise property name:

    customer.name

Actual access depends on the EvaluationContext's PropertyAccessor. Spring's default contexts provide accessors for common object types. If an application has specialized data types, a custom PropertyAccessor may be required.

A getter can execute Java code. Therefore, property access is not necessarily a simple memory field read. When placing objects into a context, consider getters with side effects, data queries, high cost, or exposure of sensitive information.

## 5. The root object is not the same as a context variable

Besides the root object, an EvaluationContext can also hold named variables. Variables are referenced with the # prefix.

Example:

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", new BigDecimal("500000"));

    Expression expression = parser.parseExpression(
            "total >= #minimumTotal");

In the expression:

- total is a property of the root object order.
- #minimumTotal is a variable registered in the context.

You can reference the root object explicitly:

    #root.total >= #minimumTotal

This clarifies the two different data sources: properties belonging to the input object and variables passed separately to the expression. Do not confuse #root with an application-defined variable; it is SpEL's built-in variable representing the root object.

## 6. #this and changes to the current object

#root always represents the root object of the evaluation. #this represents the object currently serving as the target of the expression at the position being evaluated.

At the beginning of a regular expression, #this usually points to the root object as well. However, in collection operations such as selection and projection, #this is set to the element currently being processed.

Suppose the root object is Order and has a lines collection:

    lines.?[quantity > 0]

Inside the selection condition, quantity is read on each element of lines. You can write it explicitly:

    lines.?[#this.quantity > 0]

If you need to compare an item's property with a property of the root object, use both:

    lines.?[#this.quantity > #root.minimumQuantity]

Here:

- #this.quantity is the quantity of the current order line.
- #root.minimumQuantity is the minimumQuantity of the original Order.

This distinction is very important. If you mistakenly write #this.minimumQuantity, SpEL will look for that property on each order line. If LineItem does not have this property, the expression will fail even though Order has the minimumQuantity property.

## 7. Accessing intermediate objects that may be null

A standard property path assumes that the object at every step exists. For example:

    customer.address.city

will run into trouble if customer or address is null. When SpEL tries to access the next property on a null value, evaluation can raise an error.

You can use the null-safe navigation operator ?. at each segment that could be null:

    customer?.address?.city

If customer is null, the result of the safe access is null. If customer has a value but address is null, the safe operator on the address?.city segment prevents an error when reading city.

Placing ?. only at the first step is not enough if subsequent intermediate objects can also be null:

    customer?.address.city

In this expression, the address.city segment is still a normal access. If address is null, reading city can fail. Place ?. at every boundary where the preceding object may be null:

    customer?.address?.city

Null-safe navigation only returns null for the protected operation. It does not make the entire object graph safe automatically. When the expression continues accessing other properties, examine every link in the chain.

## 8. Combining null-safe navigation with Elvis

After safely accessing a property, you can use Elvis to supply a default value:

    customer?.address?.city ?: 'Not updated'

If customer or address is null, the result of the property path is null and Elvis returns Not updated. If city is an empty string, Elvis also uses the default value. If city has content, that value is kept.

The two operators have distinct responsibilities:

- ?. protects a property or method access when the object may be null.
- ?: chooses a default value when the result is null or an empty string.

If you omit null-safe navigation, Elvis cannot catch errors raised while accessing an intermediate property. For example:

    customer.address.city ?: 'Unknown'

can still fail before Elvis is evaluated if customer or address is null.

You can combine with a ternary condition when default rules are more complex:

    customer?.address?.city != null
        ? customer.address.city
        : 'Unknown'

However, when the goal is simply to provide a fallback, null-safe navigation with Elvis is usually shorter and repeats the path less.

## 9. Accessing Maps, Lists, and arrays in an object graph

Not every intermediate object is a JavaBean. If a property returns a Map, List, or array, the expression can continue using element access syntax.

Examples with Map:

    metadata['region']
    metadata['owner']['name']

With List or array:

    lines[0]
    lines[0].product.name

You can combine multiple object types in the same path:

    order.attributes['shipping'].address.city

In this example, attributes is a Map; the shipping key returns an object that has an address property; address in turn has a city property.

If a collection may be empty or an index may be out of range, check conditions before accessing elements. Null-safe navigation handles null objects, but does not by itself guarantee an index exists or a Map key is present.

## 10. Complete example: retrieving the shipping city

Suppose the application receives an OrderView that has customer and shippingAddress. The goal is to retrieve the shipping city; if the address or city is missing, return a default label.

Simplified model:

    public class OrderView {
        private CustomerView customer;
        private AddressView shippingAddress;

        public CustomerView getCustomer() {
            return customer;
        }

        public AddressView getShippingAddress() {
            return shippingAddress;
        }
    }

    public class AddressView {
        private String city;

        public String getCity() {
            return city;
        }
    }

The expression can be written:

    shippingAddress?.city ?: 'No city'

Evaluating in Java:

    OrderView order = orderService.getOrder(orderId);

    EvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding().build();

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "shippingAddress?.city ?: 'No city'");

    String city = expression.getValue(context, order, String.class);

In this expression, shippingAddress is a property on the root object OrderView. city is a property on the intermediate object AddressView. If shippingAddress is null, null-safe navigation returns null and Elvis picks the default label.

If the rule needs to read the customer's city when there is no separate shipping address, you can write:

    shippingAddress?.city
        ?: customer?.address?.city
        ?: 'No city'

SpEL evaluates the Elvis expressions sequentially from left to right. The first value that is neither null nor an empty string is selected. Therefore, the shipping city is preferred; if missing, the customer's address is used; if both are missing, the default label is used.

## 11. Common errors when reading property paths

| Syntax or situation | Cause | Resolution |
|---|---|---|
| customer.name but root lacks customer | Starting from the wrong root object | Check the root passed into getValue or context |
| customer.address.city fails when address is null | Intermediate object does not exist | Use customer?.address?.city if steps can be null |
| #this.minimumQuantity in selection | #this is the current collection element | Use #root.minimumQuantity if the property belongs to the root |
| metadata.region when metadata is a Map | Accessing as a JavaBean property instead of a key | Use metadata['region'] |
| lines[0] fails | Empty collection or invalid index | Check size before accessing |
| Property not found | Property accessor does not support the data type or property name is wrong | Check getter, runtime type, and PropertyAccessor |

When an error occurs, break the path down at each dot. Identify the value and runtime type after each step. This usually pinpoints exactly which intermediate object is null or lacks the expected property.

## 12. Restricting access and designing input data

An expression can read any property allowed by the configured PropertyAccessor. Therefore, the object supplied as the root should be chosen intentionally.

Some practical principles:

- Use a DTO or object view that contains only the data the rule needs to read.
- Avoid passing entities with many lazy relationships or getters that may trigger unintended queries.
- Do not supply an object graph containing confidential information if the expression does not need it.
- Use a read-only context when the rule's only job is evaluation.
- If the expression comes from an external source, restrict property accessors and other context capabilities; do not grant broad access arbitrarily.
- Test the path with null intermediate objects, empty collections, and nonexistent properties.

Separating the root object and intermediate objects clearly also keeps the rule contract more stable. If the entity structure changes, a dedicated DTO can preserve the property path the rule is using.

## Conclusion

The root object is the starting point of a SpEL evaluation. The first property is read on the root; each subsequent property is read on the intermediate object returned by the previous step. You can use #root to explicitly reference the root object, while #this represents the current object and changes inside selection/projection.

When a property path passes through objects that may be null, use null-safe navigation at every link that needs protection. For Maps, Lists, or arrays, use the corresponding element access syntax and check keys/indexes before reading. Providing an appropriate root object and object graph, with restricted access permissions, will make expressions easier to understand, more stable, and safer when running in a Spring application.