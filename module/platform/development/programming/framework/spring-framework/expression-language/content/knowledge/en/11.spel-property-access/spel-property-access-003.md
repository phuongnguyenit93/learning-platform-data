# Nested Properties via Dot Chaining

In Spring Expression Language (SpEL), the dot **.** is used to access an object's property. When an object contains another object, multiple property accesses can be chained into a path:

~~~text
#order.customer.address.city
~~~

The expression above sequentially retrieves the order variable, reads the customer property, reads address next, and then retrieves city. This is a common pattern when business data is organized into nested objects such as orders, customers, addresses, or configuration.

To read and write property paths properly, you need to understand where SpEL starts from, how each segment in the path is resolved, and what happens if an intermediate object is null.

## 1. Structure of a property path

A simple property path has the form:

~~~text
object.property
~~~

Multiple properties can be chained:

~~~text
order.customer.address.city
~~~

Each dot represents an access step:

1. Obtain the root object.
2. Read the first property on that object.
3. Use the read value as the target object for the next step.
4. Repeat until the final property.

Example with a Java model:

~~~java
public class Order {
    private Customer customer;

    public Customer getCustomer() {
        return customer;
    }
}

public class Customer {
    private Address address;

    public Address getAddress() {
        return address;
    }
}

public class Address {
    private String city;

    public String getCity() {
        return city;
    }
}
~~~

Given an Order object, the expression:

~~~text
customer.address.city
~~~

can be read as:

- order.getCustomer()
- calling getAddress() on that result
- calling getCity() on the next result

SpEL typically uses the property access mechanism to resolve properties. For a standard JavaBean, properties are read via getters. A property can be provided by another PropertyAccessor if the evaluation context is configured to support that object type.

The dot is the property access operator in expressions. It does not mean SpEL is looking up a key string containing dots in a Map. For a Map, use key-based indexer syntax as shown later.

## 2. Starting a property path from a root object or variable

SpEL can obtain the starting object from the EvaluationContext or receive the root object directly when calling getValue().

### 2.1. Using a root object

If you pass an Order as the root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

String city = parser
        .parseExpression("customer.address.city")
        .getValue(order, String.class);
~~~

In this expression, customer is a property of the root object order. Therefore, the #order prefix is not needed.

### 2.2. Using a variable in EvaluationContext

If you register Order as a variable:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);

String city = parser
        .parseExpression("#order.customer.address.city")
        .getValue(context, String.class);
~~~

The # symbol accesses a variable in EvaluationContext. After retrieving the order variable, the dots continue accessing properties of that object.

The two forms have different starting points:

| Syntax | Starting point | When to use |
| --- | --- | --- |
| **customer.address.city** | Root object | When getValue() receives the root object directly |
| **#order.customer.address.city** | Variable named order | When the object is registered in EvaluationContext |
| **@orderService.defaultAddress.city** | Spring bean named orderService | When the context allows bean references |

Do not confuse #order with @order. #order is a variable placed into EvaluationContext; @order is a bean reference resolved through the context's BeanResolver.

## 3. Nested properties in an object graph

### 3.1. Reading multiple property levels

Suppose Order has customer, Customer has address, and Address has city. You can read city with a single expression:

~~~text
#order.customer.address.city
~~~

There is no need to call getters manually in the Java expression. SpEL resolves each property in the chain.

Some similar examples:

~~~text
#employee.department.manager.name
#invoice.customer.billingAddress.postalCode
#product.category.parent.name
#applicationSettings.database.connectionTimeout
~~~

The longer a property path is, the more it depends on the object structure at each step. If a class renames a property or changes a getter's return type, the expression may need to be updated.

### 3.2. A property can be a getter, field, or custom accessor

A property name in SpEL is typically the logical JavaBean property name, not necessarily the field name:

~~~java
class Customer {
    private String fullName;

    public String getFullName() {
        return fullName;
    }
}
~~~

The expression uses:

~~~text
#customer.fullName
~~~

rather than needing to write getFullName(). With reflective property access, Spring can read properties via getters and, in supported cases, access fields. Actual access rights depend on the PropertyAccessor and EvaluationContext being used.

If a data type does not follow the JavaBean convention, you may need to register an appropriate PropertyAccessor. Do not assume every method automatically becomes a property; a regular method must be called using method-call syntax, for example:

~~~text
#customer.getDisplayName()
~~~

If a class has a getDisplayName() getter, property style is usually easier to read:

~~~text
#customer.displayName
~~~

### 3.3. Nested properties in Java records

With records:

~~~java
record Address(String city, String country) {}
record Customer(String name, Address address) {}
~~~

You can access record components by property name:

~~~text
#customer.address.city
~~~

Records provide accessors named after their components. Spring can resolve the corresponding properties via the access mechanisms supported in the framework version in use.

## 4. What happens when an intermediate property is null?

A standard property path assumes that the receiving object at each step exists:

~~~text
#order.customer.address.city
~~~

If order is null, SpEL cannot read customer. If customer is null, it cannot read address. If address is null, it cannot read city. These cases can cause an EvaluationException when the expression is evaluated.

### 4.1. Using the safe-navigation operator

SpEL provides the safe-navigation operator **?.** to access a property when the receiving object may be null:

~~~text
#order?.customer?.address?.city
~~~

If an intermediate object is null, the corresponding access returns null instead of throwing an error at that step.

You should place **?.** at every boundary where an object may be null. For example:

~~~text
#order?.customer?.address?.city
~~~

protects order, customer, and address in turn.

Do not protect only the first step and assume subsequent steps are automatically safe:

~~~text
#order?.customer.address.city
~~~

Safe navigation only protects the operation immediately following it. If customer can be null, the subsequent address access can still fail. Clearly identify nullable points and use safe navigation at each of those points.

### 4.2. Combining safe navigation with default values

When a default value is needed, you can combine safe navigation with Elvis:

~~~text
#order?.customer?.address?.city ?: 'Unknown'
~~~

The expression returns city when the path exists and city has a value. If a step returns null or city is an empty string, Elvis supplies Unknown.

You can use this approach to build display names:

~~~text
#employee?.department?.manager?.name ?: 'Unassigned'
~~~

Safe navigation handles intermediate objects that may be null; Elvis handles a final result that lacks a value.

### 4.3. Safe navigation does not auto-initialize objects

When customer or address is null, safe navigation simply returns null for the access. It does not create a Customer, Address, or any object to complete the path.

If you need to initialize nested objects, do so in a Java service or in intentional configuration logic. A property path only reads data and does not populate the object graph by itself.

## 5. Combining dots with Maps, Lists, and arrays

Property paths can be combined with indexers to access nested data structures. Dots and square brackets serve two distinct roles:

- Dots access object properties.
- Square brackets access collection or array elements, or values in a Map.

### 5.1. Accessing a Map by key

For a Map, use the key inside square brackets:

~~~text
#order.attributes['priority']
#settings['database']['url']
~~~

You can continue into properties of the object retrieved from the Map:

~~~text
#order.attributes['shippingAddress'].city
~~~

In the last example, attributes is a Map, shippingAddress is the key, and city is a property of the object stored under that key.

If the key does not exist, the result of the Map access may be null. When the path continues further, handle null at the next step or use safe navigation appropriate for the data type and SpEL version.

### 5.2. Accessing List or array elements

Use a 0-based index:

~~~text
#order.lines[0].product.name
~~~

The expression takes the first element in lines, reads product, and then retrieves name.

Property paths can be combined with multiple indexes:

~~~text
#matrix[0][1]
#departments[0].employees[2].name
~~~

The index must be within valid bounds. If the List is empty, the index is out of range, or the array lacks that element, evaluation may fail. Check the size before accessing if input data is not guaranteed.

### 5.3. Combining properties, Maps, and Lists

A real-world path can traverse multiple data types:

~~~text
#response.data['orders'][0].customer.address.city
~~~

Resolution order:

1. Retrieve the response variable.
2. Read the data property.
3. Look up the orders key in the Map.
4. Retrieve the element at index 0.
5. Read customer.
6. Read address.
7. Read city.

When an expression combines multiple structure types, read it left to right and determine the type of the value after each step. This helps locate the exact position causing an error when a key, index, or property does not exist.

## 6. Using nested property paths in Spring configuration

SpEL is integrated into many parts of Spring. When an annotation supplies objects or parameters into an EvaluationContext, you can use a property path to extract a deeply nested value.

### 6.1. Building a cache key from nested properties

Example caching by the customer's ID in an order:

~~~java
@Cacheable(
    cacheNames = "orders",
    key = "#order.customer.id"
)
public OrderSummary summarize(Order order) {
    // ...
}
~~~

The expression reads customer and then retrieves id. Make sure order and customer exist when the cache key is evaluated. If customer may be null, define an explicit fallback key:

~~~java
@Cacheable(
    cacheNames = "orders",
    key = "#order?.customer?.id ?: 'unknown'"
)
public OrderSummary summarize(Order order) {
    // ...
}
~~~

In multi-tenant or multi-customer systems, do not group missing-ID cases into a single shared key if that could cause cached data to be shared across improper scopes. Default values must align with the application's identification rules.

### 6.2. Using in Method Security

You can check access permissions based on nested properties of a parameter:

~~~java
@PreAuthorize(
    "#order.customer.id == authentication.principal.customerId"
)
public Order findOrder(Order order) {
    // ...
}
~~~

The expression compares the customer ID in order with the customer ID of the logged-in principal. This is a SpEL equality comparison.

Parameter names such as order must be properly discovered by Spring. Depending on how code is compiled, you may need to enable the Java -parameters option or use annotations that provide parameter names per Spring Security's mechanism.

If order or customer may be null, write a safe and explicit condition:

~~~java
@PreAuthorize(
    "#order != null and #order.customer != null and " +
    "#order.customer.id == authentication.principal.customerId"
)
~~~

SpEL uses short-circuit AND, so the right-hand side is evaluated only when earlier conditions hold. Even so, ensure the security context provides a principal with the structure expected by the expression.

### 6.3. Reading nested properties from a Spring bean

You can reference a bean and then read its nested properties:

~~~java
@Value("#{ @appSettings.database.region }")
private String databaseRegion;
~~~

Here **@appSettings** is a bean reference; **database** and **region** are properties accessed next. This requires an EvaluationContext with a BeanResolver, such as the context Spring sets up for the corresponding integration point.

If you only need to read a simple configuration value, a property placeholder is usually more appropriate. Use nested SpEL when the value resides inside an object provided by a bean or when multiple access operations must be combined.

## 7. Testing property paths with the SpEL parser

You can write a small test to verify nested paths:

~~~java
class NestedPropertyExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void readsNestedCityFromRootObject() {
        Address address = new Address("Da Nang");
        Customer customer = new Customer(address);
        Order order = new Order(customer);

        String city = parser
                .parseExpression("customer.address.city")
                .getValue(order, String.class);

        assertEquals("Da Nang", city);
    }

    @Test
    void readsNestedCityFromVariable() {
        Address address = new Address("Ha Noi");
        Customer customer = new Customer(address);
        Order order = new Order(customer);

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("order", order);

        String city = parser
                .parseExpression("#order.customer.address.city")
                .getValue(context, String.class);

        assertEquals("Ha Noi", city);
    }
}
~~~

The first test passes Order as the root object. The second test places Order into the context under the name order and accesses it via #order. Both verify that the property path resolves to the expected final value.

You should add tests for cases where customer or address is null if real data allows those states. You can test expressions using safe navigation:

~~~java
context.setVariable("order", orderWithMissingAddress);

String city = parser
        .parseExpression("#order?.customer?.address?.city ?: 'Unknown'")
        .getValue(context, String.class);

assertEquals("Unknown", city);
~~~

When testing an expression in an annotation, besides parser tests you also need integration-point tests to confirm the module supplies the right parameters, root object, bean resolver, and property access permissions.

## 8. Common mistakes when using nested property paths

1. **Forgetting the variable prefix:** using order.customer.city when order is only registered as a variable. In that case, you must write #order.customer.city.
2. **Confusing variables with beans:** #order is a variable; @order is a bean reference and requires a BeanResolver.
3. **Null intermediate properties:** if customer or address is null, further access can cause an EvaluationException.
4. **Using safe navigation only at the first step:** #order?.customer.address.city does not protect customer and address if they can be null.
5. **Confusing Map keys with properties:** use #settings['region'] to access a key in a Map; dots are for object properties.
6. **Invalid indexes:** #items[0] can fail if the collection is empty or the index is out of bounds.
7. **Incorrect property names:** SpEL resolves property names via accessors; use the exact JavaBean/record component name or custom accessor.
8. **Getters causing side effects or throwing exceptions:** reading a property may invoke a getter; getters should be stable and avoid unexpected business operations.
9. **Assuming all contexts have identical access permissions:** StandardEvaluationContext and SimpleEvaluationContext have different access capabilities. SimpleEvaluationContext may restrict property accessors, method resolvers, and bean references depending on how it is built.

## 9. Quick reference

- The dot **.** chains property accesses in an object graph.
- **customer.address.city** starts from the root object; **#order.customer.address.city** starts from a variable.
- **@beanName.property** starts from a bean reference when the context supports BeanResolver.
- SpEL resolves each property from left to right; a property in a later step is read on the object returned by the previous step.
- JavaBean properties are usually read via getters; accessors can be extended with PropertyAccessor.
- Use **['key']** for Maps and **[index]** for Lists/arrays.
- Null intermediate objects can cause a property path to fail; use **?.** at every step that may be null.
- Safe navigation does not initialize objects and does not automatically protect subsequent steps unless placed at the right positions.
- Property paths in caches, security, and other annotations use the EvaluationContext of their respective integration point.
- Test happy paths, intermediate nulls, missing keys, and out-of-range indexes.

## 10. Official references

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Properties, Arrays, Lists, Maps and Indexers](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html)
- [Spring Framework — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
