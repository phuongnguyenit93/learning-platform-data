# Evaluating Root Object Properties and Null-Safe Handling in Spring Expression Language

In Spring Expression Language (SpEL), the root object is the default object that an expression uses when reading a property or calling a method without a variable prefix. For example, if the root object is Customer, the expression name or address.city is evaluated on Customer.

In real-world applications, nested properties can return null. If the expression continues accessing a property on a null value, evaluation fails. SpEL provides null-safe navigation using the ?. operator to skip the access operation when the receiver immediately before the operator is null.

When writing an expression, you need to clearly identify which property belongs to the root object, which intermediate object may be null, and place the null-safe operator at each risky segment. You can combine it with null checks, the Elvis operator, or the conditional operator to produce an appropriate default result.

## 1. The root object is the starting point of property access

When creating a StandardEvaluationContext with an object, that object becomes the root object:

~~~java
Customer customer =
    new Customer("Linh", "GOLD");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

ExpressionParser parser =
    new SpelExpressionParser();

Expression expression =
    parser.parseExpression("name");

String name =
    expression.getValue(context, String.class);
~~~

With Customer as the root object, the expression name reads the name property on Customer. SpEL typically uses JavaBean getters such as getName() or isActive() through the context's default PropertyAccessor.

You can reference the root object explicitly using #root:

~~~spel
#root.name
#root.membershipLevel
~~~

At the outermost level, name and #root.name both refer to the name property of the root object. Writing #root is useful when an expression is complex and you need to distinguish the root data from the current object in a nested operation.

## 2. Distinguishing root properties from variables

A property name without the # prefix is normally looked up on the current object. A name with the # prefix is looked up in the variable space of the EvaluationContext.

For example:

~~~java
Customer customer =
    new Customer("Linh", "GOLD");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("minimumLevel", "SILVER");
~~~

Expression:

~~~spel
membershipLevel == #minimumLevel
~~~

Where:

- membershipLevel is a property on the root object Customer.
- #minimumLevel is a variable registered with setVariable.
- #root.membershipLevel is the explicit way to read the property from root.

Do not confuse #customer with the root object just because a variable has the same name as a type or property. #customer only exists if the application registers a variable named customer in the EvaluationContext.

## 3. Multi-level property paths

SpEL allows chaining properties with dots:

~~~spel
customer.address.city
~~~

Each subsequent segment is read on the object returned by the previous segment. If the root object is Order, the process can be:

| Expression segment | Object receiving the operation |
|---|---|
| customer | Order |
| address | Customer |
| city | Address |

Therefore, the receiver of city is not Order, but Address. When an expression fails at the final segment, check the actual intermediate object instead of only looking at the root object.

Example with JavaBeans:

~~~java
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
~~~

With Order as the root object, the expression can read:

~~~spel
customer.address.city
~~~

As long as both customer and address are non-null and the property is accessible.

## 4. What happens when an intermediate property is null?

Suppose Order has a customer, but customer does not yet have an address:

~~~java
Customer customer = new Customer();
customer.setAddress(null);

Order order = new Order();
order.setCustomer(customer);
~~~

The expression:

~~~spel
customer.address.city
~~~

reads customer, then address returns null. SpEL cannot read city on a null receiver, so evaluation raises an error.

This is a runtime error during property access, not a syntax error. The expression can parse successfully but fail when getValue is called with data that has a null intermediate object.

Null at the final property also needs to be distinguished from null at the receiver. If address exists but getCity() returns null, the expression customer.address.city can evaluate successfully and the result is simply null. An error occurs when a subsequent operation tries to access a property or call a method on that null value.

## 5. Null-safe navigation with the ?. operator

The ?. operator checks the receiver immediately to its left. If the receiver is null, the corresponding property or method operation is skipped and the result of that segment is null.

For example:

~~~spel
customer?.address
~~~

If customer is null, the expression returns null instead of attempting to read address on null. If customer exists, SpEL reads the address property normally.

It can be used with the root object:

~~~spel
#root?.customer
~~~

If the root object is null, the expression returns null. If the root object exists, SpEL continues reading customer.

Null-safe navigation is useful when data comes from an API, database, form, or conditionally constructed object, where some nested properties may not be initialized.

## 6. Placing ?. at each level that may be null

An important point is that the null-safe operator only protects the operation immediately following it. In a compound expression, the remaining segments are still evaluated. Therefore, if multiple intermediate objects can be null, you must place ?. at each corresponding segment.

For example:

~~~spel
customer?.address.city
~~~

This expression protects against customer being null when reading address. However, if customer exists and address is null, the subsequent .city part can still fail.

If both customer and address can be null, write:

~~~spel
customer?.address?.city
~~~

Similarly, with the root object:

~~~spel
#root?.customer?.address?.city
~~~

The chain of operations is protected at each level:

1. If the root object is null, the result is null.
2. If root exists but customer is null, the result is null.
3. If customer exists but address is null, the result is null.
4. If the entire path exists, SpEL returns city.

Do not place only one null-safe operator at the beginning of a path and assume every subsequent property is protected.

## 7. Using null-safe navigation with method calls

The ?. operator can also protect method calls:

~~~spel
customer?.getName()
customer?.calculateDiscount(#amount)
~~~

If customer is null, SpEL does not call the method and returns null. If customer exists, the method is looked up and called normally.

If the method returns another object that may be null, you need to continue protecting subsequent operations:

~~~spel
customer?.getAddress()?.getCity()
~~~

In this expression:

- customer?.getAddress() protects the receiver customer.
- ?.getCity() protects the result of getAddress() if it is null.

Null-safe navigation does not handle missing methods, incompatible overloads, or exceptions thrown inside a method. It only handles the case where the receiver of the operation is null.

## 8. Using #root explicitly in expressions with multiple objects

When an expression has multiple levels or collections, writing #root helps make it clear which data always belongs to the root object.

For example, the root object is OrderInput, which has properties customer and minimumTotal:

~~~spel
#root.customer?.address?.city
#root.minimumTotal
~~~

In selection:

~~~spel
orders.?[#this.total >= #root.minimumTotal]
~~~

#root is still OrderInput, while #this is the Order being checked. If you need to read each order's customer, you can write:

~~~spel
orders.?[#this.customer?.address?.city == #root.requiredCity]
~~~

If the order element itself can also be null:

~~~spel
orders.?[#this?.customer?.address?.city == #root.requiredCity]
~~~

This condition protects the current element before reading customer. The subsequent segments are also protected when customer or address can be null.

## 9. Using the Elvis operator to provide a default value

If a property result can be null and the application needs a replacement value, you can use the Elvis operator ?:.

For example:

~~~spel
customer?.address?.city ?: 'Unknown'
~~~

If the path returns null, the result is Unknown. If city has a value, the expression returns city. According to SpEL's Elvis semantics, an empty string is also treated as a missing value and can lead to the default branch.

It can be used with a root property:

~~~spel
#root?.customer?.name ?: 'Guest'
~~~

Elvis is suitable when only a simple fallback is needed. It does not catch exceptions from non-existent properties, incompatible methods, out-of-range indices, or errors inside getters.

If you want to distinguish null from an empty string, use an explicit condition instead of relying on Elvis.

## 10. Using the conditional operator when explicit rules are needed

The ternary operator allows choosing a result based on a condition:

~~~spel
customer != null ? customer.name : 'Guest'
~~~

If the root object can be null:

~~~spel
#root != null ? #root.customer?.name : 'Guest'
~~~

Additional properties can be checked:

~~~spel
customer != null && customer.address != null
    ? customer.address.city
    : 'Unknown'
~~~

The && operator evaluates short-circuit: if customer is null, the address check side is not evaluated. If customer exists but address is null, the branch accessing city is not chosen.

Ternary is suitable when the fallback depends on multiple conditions or when you need to distinguish different states. For a path that only needs to return a default value when null, null-safe navigation combined with Elvis is usually more concise.

## 11. Distinguishing null from empty values

Null-safe navigation handles null objects. It does not automatically treat every value "without content" as null.

Cases to distinguish:

| Property value | Meaning | Behavior when read |
|---|---|---|
| null | No object/value | Result is null if the property is read successfully |
| Empty string | String exists but has no characters | Returns empty string |
| Empty collection | Collection exists but has no elements | Returns empty collection |
| Number 0 | Valid numeric value | Returns 0 |
| Boolean false | Valid Boolean value | Returns false |

For example:

~~~spel
customer?.name
~~~

If customer exists and name is an empty string, the result is an empty string. The null-safe operator does not replace an empty string with null.

If a fallback is also needed for an empty string, SpEL's Elvis operator may be suitable:

~~~spel
customer?.name ?: 'Anonymous'
~~~

If you need to handle an empty collection, you must check its size or isEmpty() separately; null-safe navigation does not turn an empty collection into null.

## 12. Combining null-safe with indexers

When a property returns an array, List, or Map, you may need to protect both the collection and the retrieved element.

With Spring Framework 6.2 and later, the null-safe indexer has the syntax ?.[]:

~~~spel
#root?.addresses?.[0]?.city
~~~

In this example:

- #root?.addresses protects the root object and the addresses property.
- ?. [0] (written together as ?.[0]) is the null-safe indexer protecting the collection when it is null.
- ?.city protects the element if the retrieved element is null.

The actual syntax must be written together, without spaces:

~~~spel
#root?.addresses?.[0]?.city
~~~

The null-safe indexer does not handle an empty collection or an out-of-range index. If addresses exists but has no element at index 0, the index operation can still raise an error.

With Spring versions earlier than 6.2, you can check for null and size before indexing:

~~~spel
#root.addresses != null && !#root.addresses.isEmpty()
    ? #root.addresses[0].city
    : null
~~~

An additional null element check is needed if the first element can also be null.

## 13. Using null-safe in selection and projection

Selection and projection change the current object for each element. In a predicate or projection expression, #this represents the element currently being processed.

Example filtering orders that have valid customer and address:

~~~spel
#root.orders.?[
    #this?.customer?.address?.city == #root.requiredCity
]
~~~

If order is null, the element is not selected because the left side returns null and does not equal requiredCity. If customer or address is null, the null-safe chain also returns null.

Projection can create a list of city names:

~~~spel
#root.orders.![#this?.customer?.address?.city]
~~~

If an order or nested object is null, the corresponding position in the result can be null. Projection does not automatically remove null results.

If you need to exclude elements without a city, you can combine selection before projection:

~~~spel
#root.orders.?[
    #this?.customer?.address?.city != null
].![customer.address.city]
~~~

Selection ensures that only orders with a non-null city path are kept before projection reads the value.

## 14. Null root object and how to handle it

The root object can be null if the application creates a context without providing an object or passes a null root. In this case, a direct property access expression:

~~~spel
name
~~~

has no valid receiver and evaluation can fail.

If you want the expression to return null when root is null, you can reference it explicitly:

~~~spel
#root?.name
~~~

Or use a default value:

~~~spel
#root?.name ?: 'Unknown'
~~~

In Java, you should decide clearly whether the root object is required. If the expression always requires a valid root object, validate the input before calling getValue. If root is optional, use a null-safe expression and define the null result according to the application contract.

Do not use null-safe navigation to hide a required root object that is missing due to a data initialization bug.

## 15. Property accessors determine how properties are read

SpEL does not access every property using a single fixed rule. EvaluationContext provides PropertyAccessors to locate and read properties on the current object.

StandardEvaluationContext has a default reflection accessor, supporting property access according to common Java conventions such as getters and accessible fields. Applications can also register custom PropertyAccessors for domain types or proprietary data structures.

If a property exists in the source code but the expression cannot read it, check:

- Does the root object or current receiver have the right runtime type?
- Is the getter or field accessible?
- Is the property name correct?
- Which PropertyAccessors are registered?
- Is an intermediate object null?

Null-safe navigation only skips the operation when the receiver is null. It does not fix an incorrect property name and does not make an unsupported accessor support the property.

## 16. Distinguishing null-safe access from property errors

There are three different situations:

**Null receiver:**

~~~spel
customer?.name
~~~

If customer is null, the result is null.

**Non-existent property:**

~~~spel
customer?.unknownProperty
~~~

If customer exists but has no corresponding property or accessor, evaluation can still fail. The null-safe operator does not ignore property errors on a non-null object.

**Getter throws an exception:**

~~~spel
customer?.displayName
~~~

If customer exists but the displayName getter throws an exception, that exception can still propagate out. The null-safe operator does not catch exceptions inside a getter.

Distinguishing these three cases helps avoid using ?. as a general-purpose error-catching mechanism.

## 17. Evaluating segment by segment to find a null property

When a nested path fails, you can split the expression into segments to see which object returns null.

For example:

~~~spel
customer
customer.address
customer.address.city
~~~

In Java:

~~~java
Object customerValue =
    parser.parseExpression("customer")
          .getValue(context);

Object addressValue =
    parser.parseExpression("customer.address")
          .getValue(context);

Object cityValue =
    parser.parseExpression("customer.address.city")
          .getValue(context);
~~~

You can inspect intermediate values:

~~~java
private static String describe(Object value) {
    return value == null
        ? "null"
        : value.getClass().getName();
}
~~~

If customerValue has type Customer but addressValue is null, the point to address is the data or the address getter. If addressValue exists but city fails, check the accessor and the city property on the runtime type of Address.

Using the same EvaluationContext keeps the root object, variables, and accessors intact while isolating the error.

## 18. Choosing how to handle null based on requirements

Not every null property needs to be replaced with a default value. Define the desired result contract:

| Requirement | Suggested syntax |
|---|---|
| Return null if receiver is null | customer?.name |
| Read multiple levels that may be null | customer?.address?.city |
| Return default value when null | customer?.name ?: 'Guest' |
| Choose between two explicit branches | customer != null ? customer.name : 'Guest' |
| Check multiple conditions | customer != null && customer.active |
| Root object may be null | #root?.customer?.name |
| Exclude collection elements missing a property | Selection checking null before projection |

Avoid using default values arbitrarily if null carries a distinct business meaning. For example, null may indicate unverified data, whereas the string "Unknown" might be interpreted as an actual value.

## 19. Complete example: evaluating a nullable root property

Suppose an application creates a notification from customer information:

~~~java
public class Address {
    private final String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class Customer {
    private final String name;
    private final Address address;

    public Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public Address getAddress() {
        return address;
    }
}

public class CustomerInput {
    private final Customer customer;

    public CustomerInput(Customer customer) {
        this.customer = customer;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Create a root object with a null address:

~~~java
Customer customer =
    new Customer("Linh", null);

CustomerInput input =
    new CustomerInput(customer);

StandardEvaluationContext context =
    new StandardEvaluationContext(input);

ExpressionParser parser =
    new SpelExpressionParser();
~~~

Read the city safely:

~~~java
Expression cityExpression =
    parser.parseExpression(
        "#root?.customer?.address?.city"
    );

String city =
    cityExpression.getValue(context, String.class);
~~~

The result is null, without raising an error just because address is null.

A default message can be created:

~~~java
Expression messageExpression =
    parser.parseExpression(
        "Customer #{#root?.customer?.name ?: 'Guest'} lives in #{#root?.customer?.address?.city ?: 'Unknown'}.",
        new TemplateParserContext()
    );

String message =
    messageExpression.getValue(
        context,
        String.class
    );
~~~

Result:

~~~text
Customer Linh lives in Unknown.
~~~

The example shows the root object referenced explicitly, each nullable property protected, and Elvis providing fallbacks where needed.

## 20. Common misconceptions

**Misconception 1: A property without the # prefix is always a variable.**  
At the outermost level, a name without # is normally looked up on the root object or active object. A variable is referenced with #name.

**Misconception 2: #root and #this are always the same.**  
At the outermost level they usually coincide. In selection and projection, #this is the current element while #root keeps the original root object.

**Misconception 3: One ?. at the start of a property path protects all subsequent levels.**  
Each receiver that may be null needs to be protected at the exact segment, for example customer?.address?.city.

**Misconception 4: Null-safe navigation catches all property errors.**  
It only handles a null receiver. Non-existent properties, unsupported accessors, or getters throwing exceptions can still cause errors.

**Misconception 5: An empty collection is the same as a null collection.**  
An empty collection is a valid object. Null-safe property access does not automatically turn an empty collection into null.

**Misconception 6: Elvis catches exceptions.**  
Elvis chooses a fallback for null or empty string values according to SpEL semantics; it does not catch property, method, or index errors.

**Misconception 7: Null-safe indexer and property navigation use the same syntax.**  
Property/method access uses ?.; null-safe indexer ?.[] is supported starting from Spring Framework 6.2.

**Misconception 8: Using a fallback is always a good choice.**  
Null can carry business meaning. Only replace it with Unknown or a default value when the application contract requires it.

## 21. Key takeaways

- The root object is the default object for SpEL to read properties and call methods.
- StandardEvaluationContext can receive the root object via constructor or setRootObject; getValue overloads can also receive a root for a single evaluation.
- A property path is evaluated level by level; the receiver of the final property is the object returned by the previous level.
- Property names without # are normally read on the root/active object; #name reads a variable in the EvaluationContext.
- #root always keeps the original root object; #this can change inside selection and projection.
- Null-safe navigation ?. skips the property or method call when the receiver immediately before it is null.
- Place ?. at each level that may be null, for example #root?.customer?.address?.city.
- Null-safe navigation does not handle wrong properties, unsupported accessors, or exceptions from getters/methods.
- Elvis ?: and ternary can create fallbacks; choose the approach that matches the meaning of null and empty strings.
- Null-safe indexer ?.[] is a separate feature from Spring Framework 6.2; it does not make out-of-range indices valid.
- In selection/projection, protect both null elements and nested properties when needed.
- When debugging, evaluate the property path segment by segment, inspect values and runtime types, then identify the PropertyAccessor and receiver at the point of failure.

When evaluating a root object's properties, start from root, trace each receiver along the property path, and identify which segments may return null. Use null-safe navigation at each risky level, then clearly choose between a null result or a default value according to business requirements.
