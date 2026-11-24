# Read-Only Data Binding and Source Data in Spring Expression Language (SpEL)

Spring Expression Language (SpEL) can read properties from a data object provided during expression evaluation. In cases where only lookups or calculations from input data are needed, an application can use SimpleEvaluationContext with read-only data binding mode.

This configuration allows expressions to access properties through the data binding mechanism and restricts advanced SpEL capabilities. It is suitable for expressions that need to read data from DTOs, configuration objects, or reporting data models without modifying properties of the source object.

A key point to remember is that read-only property access only restricts property access operations through the context. It does not automatically turn the entire object graph into immutable data: if a getter returns a mutable List or object, other Java code can still modify that object. Therefore, source data and expression scope must be designed intentionally.

## 1. What Is Read-Only Data Binding?

Data binding is how property names in an expression are mapped to an object's data. For example, when the root object has getters getName() and getAge(), SpEL can evaluate the expressions:

~~~text
name
age >= 18
name + ' - ' + age
~~~

Read-only data binding allows reading properties supported by the accessor while not granting write access to properties through that binding mechanism.

A common use case is evaluating rules or generating display content from input data:

- Reading an account's status to decide whether to display a feature.
- Computing a label from name, status, and effective date.
- Filtering or projecting a collection to generate reporting data.
- Reading configuration fields prepared by the application.

If an expression only needs to read data, choosing a read-only context helps narrow the capabilities the expression can use.

## 2. Source Data and the Root Object

Source data is the object or data model that the application passes in when evaluating an expression. In SpEL, this object usually serves as the root object.

For example, the CustomerSource class only provides getters:

~~~java
public class CustomerSource {
    private final String name;
    private final int age;
    private final boolean active;

    public CustomerSource(String name, int age, boolean active) {
        this.name = name;
        this.age = age;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Creating source data:

~~~java
CustomerSource source =
        new CustomerSource("Lan", 25, true);
~~~

When evaluating the expression name, SpEL looks up the name property on the root object source. The expression does not need a variable prefix:

~~~text
name
age >= 18
active and age >= 18
~~~

You can explicitly reference the root object using #root:

~~~text
#root.name
#root.age >= 18
~~~

The root object is the data provided for the evaluation. It is neither an EvaluationContext nor an ExpressionParser.

## 3. Creating SimpleEvaluationContext in Read-Only Mode

Spring provides SimpleEvaluationContext to evaluate expressions with a restricted feature set. When you only need to read properties following data binding rules, you can use the forReadOnlyDataBinding() builder:

~~~java
import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("name");

CustomerSource source =
        new CustomerSource("Lan", 25, true);

String name = expression.getValue(
        context,
        source,
        String.class
);
~~~

In this example:

1. forReadOnlyDataBinding() creates a builder for read-only property access.
2. build() creates the SimpleEvaluationContext.
3. parseExpression("name") parses the expression.
4. getValue(context, source, String.class) evaluates the expression with source as the root object and requests a String result.

SimpleEvaluationContext is designed for situations that do not require all the features of StandardEvaluationContext. The read-only data binding configuration provides a property accessor suitable for reading data.

## 4. Why Use SimpleEvaluationContext?

StandardEvaluationContext provides broad evaluation capabilities, which can include property access, method invocation, variables, functions, bean resolvers, and type locators. These capabilities are useful for internal expressions with full requirements, but may be broader than necessary when only reading data.

SimpleEvaluationContext allows the application to choose a smaller set of features. Read-only data binding mode is suitable when:

- The expression only needs to read JavaBean properties.
- There is no need to write data back into the source object.
- There is no need for bean or type references.
- There is no need to create objects from expressions.
- You want to restrict evaluation capabilities in a data binding flow.

A restricted context is not an absolute sandbox. The application still needs to control the root object, the data returned by getters, and any additional capabilities if configuring the builder itself.

## 5. Reading Nested Properties from Source Data

Source data often contains nested objects. SpEL can read properties across multiple levels if the accessor supports those properties.

For example:

~~~java
public class AddressSource {
    private final String city;
    private final String country;

    public AddressSource(String city, String country) {
        this.city = city;
        this.country = country;
    }

    public String getCity() {
        return city;
    }

    public String getCountry() {
        return country;
    }
}

public class CustomerProfile {
    private final String name;
    private final AddressSource address;

    public CustomerProfile(String name, AddressSource address) {
        this.name = name;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public AddressSource getAddress() {
        return address;
    }
}
~~~

Evaluating a nested property:

~~~java
CustomerProfile source = new CustomerProfile(
        "An",
        new AddressSource("Da Nang", "VN")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression cityExpression =
        parser.parseExpression("address.city");

String city = cityExpression.getValue(
        context,
        source,
        String.class
);
~~~

The expression address.city reads the address property from the root object and then reads city from the returned AddressSource object.

Read-only applies to property access operations provided by the context. If a nested object has setters or mutable collections, you should not assume the entire object graph has become immutable. Provide DTOs or view objects containing only the necessary data.

## 6. Using Collections as Source Data

Source data can contain a List or Map. SpEL supports element access, selection, and projection when the required properties can be read.

Example OrderSource class:

~~~java
public class OrderSource {
    private final String code;
    private final String status;
    private final BigDecimal total;

    public OrderSource(String code, String status, BigDecimal total) {
        this.code = code;
        this.status = status;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

public class OrderReportSource {
    private final List<OrderSource> orders;

    public OrderReportSource(List<OrderSource> orders) {
        this.orders = Collections.unmodifiableList(
                new ArrayList<>(orders)
        );
    }

    public List<OrderSource> getOrders() {
        return orders;
    }
}
~~~

Creating a context and filtering data:

~~~java
OrderReportSource source = new OrderReportSource(
        Arrays.asList(
                new OrderSource("A-100", "PAID", new BigDecimal("120.00")),
                new OrderSource("A-101", "PENDING", new BigDecimal("80.00")),
                new OrderSource("A-102", "PAID", new BigDecimal("250.00"))
        )
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Expression expression = parser.parseExpression(
        "orders.?[status == 'PAID'].![total]"
);

List<?> paidTotals = expression.getValue(
        context,
        source,
        List.class
);
~~~

The selection expression keeps orders whose status is PAID. Projection creates a list of total values for the selected orders.

Collections returned from getters are also part of the source data. Using defensive copies and unmodifiable wrappers such as Collections.unmodifiableList can help avoid unintended modification from other Java code. However, wrappers do not make the objects inside immutable; collection elements must also be designed appropriately if stable source data is desired.

## 7. Read-Only Property Access and Write Operations

In read-only data binding mode, the property accessor is configured to read properties. An assignment expression like the following is not the intended purpose of the context:

~~~text
name = 'New name'
~~~

Similarly, Java code calling setValue() to write a property will not have write permission through the read-only accessor. Depending on the location and evaluation method, a write operation may throw a SpEL error because the property is not writable.

Example illustrating read-only intent:

~~~java
Expression expression = parser.parseExpression("name");

String currentName = expression.getValue(
        context,
        source,
        String.class
);

// Do not use a read-only context to write:
// expression.setValue(context, source, "New name");
~~~

If the application genuinely needs to update data, use a separate write flow with appropriate validation and permissions. Do not switch to a writable context just to make a data-reading expression work.

Read-only binding also does not prevent a getter itself from having side effects. Getters should return data and avoid performing write operations, calling external services, or mutating state.

## 8. Read-Only Does Not Mean Immutable

This is an important point when designing source data.

A read-only property accessor restricts property assignment through SpEL. It does not guarantee that:

- Fields inside the object cannot be modified by other Java code.
- Getters only return immutable values.
- A returned List or Map cannot be modified.
- Elements inside a collection cannot be modified.
- Getters do not have side effects.

For example, the following getter directly returns a mutable List:

~~~java
public List<String> getRoles() {
    return roles;
}
~~~

An expression may only read the roles property, yet the returned List object can still be mutable if other Java code holds a reference and modifies it.

Risk can be reduced by creating an unmodifiable copy:

~~~java
public List<String> getRoles() {
    return Collections.unmodifiableList(new ArrayList<>(roles));
}
~~~

For nested objects, use read-only DTOs or return appropriate immutable values. The goal is to control the data visible to expressions, not just configure property write permissions at the SpEL layer.

## 9. Using Variables with Source Data

EvaluationContext can provide variables so expressions combine data from the root object with an additional value. With SimpleEvaluationContext, only use capabilities supported by the context's API and builder; do not assume the context has every feature of StandardEvaluationContext.

When you need to pass a threshold or parameter into an expression, you can include it in the source data as a property:

~~~java
public class EligibilitySource {
    private final int age;
    private final int minimumAge;

    public EligibilitySource(int age, int minimumAge) {
        this.age = age;
        this.minimumAge = minimumAge;
    }

    public int getAge() {
        return age;
    }

    public int getMinimumAge() {
        return minimumAge;
    }
}
~~~

Expression:

~~~text
age >= minimumAge
~~~

This approach makes inputs explicitly visible in the source object. If the application needs EvaluationContext variables, configure variables using the appropriate API and verify that the type of SimpleEvaluationContext being used supports that operation.

For configuration expressions with multiple inputs, a source DTO with clear property names is often easier to understand and test.

## 10. Null and Incomplete Source Data

Source data may contain null in the root object, properties, or nested objects. Behavior when data is missing must be clearly defined.

For example, if address can be null, the expression:

~~~text
address.city
~~~

may throw an error when address is null. Safe navigation can be used:

~~~text
address?.city
~~~

Safe navigation returns null when the left side is null, instead of continuing property access.

On the Java side, check the root object before evaluation if it can be null:

~~~java
if (source == null) {
    throw new IllegalArgumentException("Source data is required");
}

String city = parser.parseExpression("address?.city")
        .getValue(context, source, String.class);
~~~

When the result can be null, the receiving type and downstream logic must allow null. Do not assume null is equivalent to an empty string, zero, or false.

For collections that can be null, use safe navigation appropriately and handle a null result separately from an empty collection. These two states have different meanings: null may indicate data has not been provided, whereas an empty collection indicates a collection exists but has no elements.

## 11. Controlling Source Data Before Evaluation

Source data determines which properties an expression can read. Therefore, you should prepare an object with a small, clear structure suited to the expression's purpose.

Some principles:

1. Include only the properties needed by the expression.
2. Prefer DTOs or read models rather than passing entities with many relationships directly.
3. Use simple getters with no side effects.
4. Return unmodifiable collections or copies when appropriate.
5. Clearly define which properties can be null.
6. Validate and normalize input data before evaluation.
7. Do not include sensitive information or unnecessary behavior in the source object.
8. Use a SimpleEvaluationContext with the minimal configuration suited to the expression.

If expressions are user-configurable, treat both property names and the source object structure as part of the configuration interface. Changing the DTO may break older expressions, so schemas should be managed and critical expressions tested.

## 12. Distinguishing SimpleEvaluationContext and StandardEvaluationContext

| Criterion | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Goal | Evaluate with a restricted feature set | Provide a fuller evaluation environment |
| Property access | Select appropriate accessors via builder | Has default accessors and is extensible |
| Read-only binding | Has forReadOnlyDataBinding() builder | Requires configuring appropriate accessors and write permissions |
| Method invocation | Not enabled by default in minimal configuration | Has method resolvers in default configuration |
| Bean reference and type access | Does not provide these full capabilities | Can configure BeanResolver and TypeLocator |
| Use case | Data binding, restricted data-reading expressions | Internal expressions needing resolvers and advanced capabilities |

Choose SimpleEvaluationContext when expressions only need to read data and the restricted feature set meets requirements. Choose StandardEvaluationContext when you need to configure resolvers, functions, bean references, or other advanced capabilities.

Do not choose a context based solely on its name. Identify the exact properties, methods, functions, and data sources that the expression needs to access.

## 13. Common Errors

| Error | Cause | Resolution |
|---|---|---|
| Cannot read property | Root object lacks getter or accessor does not support the property. | Check the source DTO, property name, and accessor. |
| Assigning property in read-only context | Accessor is configured as read-only. | Use a separate update flow or a writable context when the business logic genuinely needs it. |
| Assuming source data is already immutable | Read-only access does not make nested objects immutable. | Use read-only DTOs, defensive copies, and unmodifiable collections. |
| Getter has side effects | Reading the property can execute code inside the getter. | Keep getters simple and only return data. |
| Accessing nested property when object is null | A level in the property path does not exist. | Check for null or use safe navigation. |
| Confusing null with empty collection | The two states represent different data meanings. | Define the data contract and handle them separately. |
| Passing an entire entity as source object | Expressions can see too much data and too many relationships. | Create a minimal DTO or read model. |
| Expecting SimpleEvaluationContext to support all SpEL features | This context intentionally restricts features. | Check the builder and choose the context based on required capabilities. |
| Returned collection can still be modified | Getter returns a reference to a mutable collection. | Return a copy or unmodifiable wrapper; also consider element mutability. |
| Using read-only as the sole security mechanism | The context does not automatically control every access source outside the object graph. | Restrict the root object, property accessors, and enabled features. |

## 14. Complete Example: Evaluating Rules on Read-Only Source Data

The example below creates a small source object and evaluates multiple expressions without modifying the source data.

~~~java
public class AccountSource {
    private final String status;
    private final int age;
    private final BigDecimal balance;

    public AccountSource(
            String status,
            int age,
            BigDecimal balance) {
        this.status = status;
        this.age = age;
        this.balance = balance;
    }

    public String getStatus() {
        return status;
    }

    public int getAge() {
        return age;
    }

    public BigDecimal getBalance() {
        return balance;
    }
}

AccountSource source = new AccountSource(
        "ACTIVE",
        25,
        new BigDecimal("1500.00")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

ExpressionParser parser = new SpelExpressionParser();

Boolean activeAdult = parser.parseExpression(
        "status == 'ACTIVE' and age >= 18"
).getValue(context, source, Boolean.class);

BigDecimal balance = parser.parseExpression(
        "balance"
).getValue(context, source, BigDecimal.class);
~~~

The first expression returns a Boolean indicating whether the account is active and the account holder meets the age condition in the example. The second expression reads balance from the source object.

Values are read from the passed-in object. There are no property assignment operations in these expressions.

## 15. Takeaways

- Source data is the object or data model passed in when SpEL evaluates an expression.
- The root object provides properties that the expression accesses directly.
- SimpleEvaluationContext.forReadOnlyDataBinding() creates a context for reading properties via data binding.
- The source object can be passed via getValue(context, source, resultType).
- Read-only property access does not grant property write permission through that accessor.
- Read-only does not mean immutable: nested objects and returned collections can still be mutable.
- Prefer small source DTOs, simple getters, and unmodifiable collections when appropriate.
- Use safe navigation and handle null according to the data contract.
- SimpleEvaluationContext restricts features; do not assume it supports all capabilities of StandardEvaluationContext.
- Choose the minimal context that meets requirements and provide only the data the expression needs to read.
