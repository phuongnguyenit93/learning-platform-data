# SimpleEvaluationContext as a Restricted-Privilege Option

Spring Expression Language (SpEL) can read properties, invoke methods, reference types, instantiate objects, and access beans depending on the EvaluationContext configuration. These capabilities are useful for application-controlled expressions, but can be overly broad when expressions are constructed from user-supplied data.

**SimpleEvaluationContext** is a more restricted option than StandardEvaluationContext. It lets the application choose how properties are accessed, optionally enable method invocation intentionally, and configure type conversion. This context does not provide capabilities such as Java type references, constructor calls, and bean references.

SimpleEvaluationContext helps reduce the expression's access surface, especially in data binding or simple rule scenarios. However, it is not a complete sandbox: allowed getters or methods can still consume resources or cause side effects. The application must still control the root object, input data, business permissions, and evaluation cost.

## 1. Why Is SimpleEvaluationContext Needed?

### 1.1. StandardEvaluationContext Has Broad Capabilities

StandardEvaluationContext is the full-featured context commonly used with SpEL. Depending on configuration, it can support:

- Reading and writing properties via PropertyAccessor.
- Invoking methods via MethodResolver.
- Resolving Java types with TypeLocator and `T(...)` syntax.
- Creating objects with constructor expressions `new`.
- Referencing Spring beans via BeanResolver.
- Using variables and type conversion services.
- Registering custom resolvers or accessors.

These features are appropriate when expressions are part of trusted configuration or when the application needs the full power of SpEL. If an expression is user-entered, each additional capability can open another path to access application objects or behaviors.

### 1.2. Purpose of SimpleEvaluationContext

SimpleEvaluationContext is designed for scenarios that need only a subset of SpEL, typically data binding and expression evaluation on data objects.

It allows the application to choose one of several ways to build the context, for example:

- Read-only property access via the data binding mechanism.
- Read-write property access via the data binding mechanism.
- Providing custom PropertyAccessors for a dedicated data model.

Method invocation is not enabled by default in common builder configurations. If calling instance methods is genuinely required, the application must enable it explicitly using the corresponding builder configuration or provide a controlled MethodResolver.

SimpleEvaluationContext does not support StandardEvaluationContext features such as Java type references, constructors, and bean references. Therefore, expressions cannot use syntax such as `T(java.lang.Runtime)`, `new java.util.Date()`, or `@someBean` the way they would in the full context.

### 1.3. When Should It Be Chosen?

SimpleEvaluationContext is usually appropriate when:

- The expression only needs to read properties of a DTO or view object.
- Data needs to be bound into an object with a controlled property scope.
- A simple Boolean rule is needed over prepared data.
- Object creation via constructor expressions is not needed.
- Looking up beans from ApplicationContext is not needed.
- You want to avoid accidentally letting expressions use type references or broader SpEL capabilities.

If an expression needs to access multiple services, call constructors, or reference types, revisit the design. Data can often be prepared in Java and the required values placed into a restricted context.

## 2. Creating a SimpleEvaluationContext

### 2.1. Read-Only Properties

Common construction for read-only expressions:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();
~~~

This builder configures the read-only data binding mechanism. Expressions can read properties supported by the provided accessor, but this context cannot be used to write properties.

Example:

~~~java
public class OrderView {

    private final String status;
    private final BigDecimal total;

    public OrderView(String status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Evaluation:

~~~java
ExpressionParser parser = new SpelExpressionParser();

OrderView order = new OrderView(
        "PAID",
        new BigDecimal("125.50")
);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

Boolean eligible = parser
        .parseExpression("status == 'PAID' && total >= 100")
        .getValue(context, order, Boolean.class);
~~~

The `getValue` overload accepts a root object specifically for that evaluation, so the object does not need to be set in the context beforehand. This is useful when reusing a read-only context configuration across multiple objects of the same data type.

### 2.2. Reading and Writing Properties

If the use case requires two-way data binding, you can use:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .build();
~~~

Property write example:

~~~java
Expression expression =
        parser.parseExpression("status");

expression.setValue(context, orderForm, "REVIEWED");
~~~

The operation only succeeds if the property is writable according to the accessor and the target object supports updating. A getter-only property or an immutable object cannot be written simply because the context was created in read-write mode.

Choose read-only when updates are not needed. Only use read-write for binding flows with a clear purpose and a restricted target object.

### 2.3. Providing Custom PropertyAccessors

If the data model is not an ordinary JavaBean, you can provide custom PropertyAccessors:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext
                .forPropertyAccessors(customPropertyAccessor)
                .build();
~~~

The builder uses the provided accessors for property access. This is useful when the application wants an expression to see only a specific set of properties on a type of object.

PropertyAccessor should declare the exact target class and support only the required properties. Do not create a general-purpose accessor for all objects if the expression only needs to read a few fields.

When multiple accessors are needed, they can be passed to the builder per the Spring version's API. Check the order and target support of each accessor to avoid conflicts.

## 3. Property Access Is Central to Restricted Contexts

### 3.1. DataBindingPropertyAccessor

The `forReadOnlyDataBinding()` and `forReadWriteDataBinding()` builders use a property access mechanism suited for data binding. This accessor enables reading or writing JavaBean properties according to the selected mode and has its own restrictions compared to a broad reflective accessor.

Example expressions:

~~~java
customer.active
customer.address.city
order.total
~~~

SpEL accesses properties through the accessor provided by the context. For nested paths, each step requires the corresponding property to be accessible.

### 3.2. Non-Existent Properties

SimpleEvaluationContext does not automatically turn misspelled properties into `null`. If an expression references a property that the accessor cannot resolve, evaluation can fail.

Example:

~~~java
customer.unknownField
~~~

If `customer` has no `unknownField` property or the accessor does not support it, the expression may throw an evaluation error.

Keep property names consistent with the DTO and test expressions against the exact permitted object types.

### 3.3. Null Properties and Nested Paths

If an intermediate property is null, deeper access can fail:

~~~java
customer.address.city
~~~

You can check for null first:

~~~java
customer.address != null && customer.address.city == 'Hanoi'
~~~

Or use safe navigation in supported Spring versions:

~~~java
customer.address?.city == 'Hanoi'
~~~

SimpleEvaluationContext does not automatically make all nested paths safe. Null handling remains the responsibility of the expression and the data model.

### 3.4. Writable Properties

Read-write mode allows writes via the accessor when the target property is mutable. Remember that `setValue` can update the object directly in memory.

If the root object is a shared object or shared across requests, a write expression can mutate state that another thread is using. Use a dedicated DTO for binding, validate the result, and only then transfer valid data to domain objects.

## 4. Method Invocation Is Not Enabled Automatically

### 4.1. No Method Resolver Needed by Default

An important advantage of SimpleEvaluationContext is that method invocation is not enabled by default in common builders.

For example, the expression:

~~~java
isEligible()
~~~

will not automatically have permission to call the method just because the root object has that method. If the application does not configure a method resolver, method calls are unsupported and evaluation will fail.

This keeps expressions strictly reading configured properties without accidentally exposing every public method on the root object.

### 4.2. Intentionally Enabling Instance Methods

If a use case needs to call instance methods, the builder can enable this capability:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

This configuration adds support for calling instance methods through Spring's reflective resolver. It does not mean expressions are allowed to call static methods, constructors, or bean references.

Enable it only when the provided methods have clear contracts, low cost, and no unexpected side effects.

### 4.3. Choosing a Custom Method Resolver

When a custom method invocation policy is required, the builder supports configuring an appropriate MethodResolver. A custom resolver can restrict target classes, method names, and permitted signatures.

Do not use a general-purpose resolver to allow calling every method on every object. If only a few behaviors are needed, create a facade or a rule-representation object with small, easily testable methods.

### 4.4. Getters Are Also Code Invocations

Property access typically goes through getters. Even though the expression does not use method-call syntax, a getter is still Java code and can perform work.

For example, a getter should not execute database queries or network calls:

~~~java
public List<Order> getOrders() {
    return orderRepository.findAll();
}
~~~

If an expression reads `orders` on every evaluation, the getter can trigger queries. SimpleEvaluationContext cannot automatically determine which getters are pure or inexpensive.

Use DTOs/views containing prepared data and keep getters lightweight and deterministic.

## 5. Capabilities Excluded from SimpleEvaluationContext

SimpleEvaluationContext does not provide the full capabilities of StandardEvaluationContext. Major excluded feature groups include:

| Capability | SimpleEvaluationContext | Meaning |
|---|---|---|
| Reading properties via configured accessor | Yes | Scope depends on the accessor |
| Writing properties | Conditional | Only with builders/accessors supporting writes |
| Instance method invocation | Off by default | Can be enabled explicitly |
| Java type references `T(...)` | No | Cannot be used to obtain arbitrary Classes |
| Constructor expressions `new` | No | Cannot instantiate arbitrary objects via constructors |
| Bean references `@beanName` | No | Cannot look up Spring beans via BeanResolver |
| Full TypeLocator | No | Does not provide type lookup like the full context |
| Custom PropertyAccessor | Yes | Must be actively provided |
| ConversionService/TypeConverter | Yes | Type conversion can be configured |

These restrictions narrow the supported expression language. If an expression uses excluded syntax, it will not evaluate successfully the way it would with StandardEvaluationContext.

Do not try to work around this by switching to a broadly privileged StandardEvaluationContext without identifying exactly which features are actually needed. Consider changing the expression or preparing data in Java.

## 6. Configuring Type Conversion

### 6.1. ConversionService

SimpleEvaluationContext can use a ConversionService to convert values when property binding or evaluation operations require a target type.

Example:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

ConversionService provides common converters and can be extended with application-specific converters.

### 6.2. Custom Converters

Suppose the application has a `CustomerCode` type:

~~~java
public record CustomerCode(String value) {
}
~~~

Register the converter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Use it in the context:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

When assigning a String value to a property of type `CustomerCode`, the converter can be used if the property accessor supports write operations and the conversion is applicable.

Converters must validate invalid data. Successful type conversion does not replace business validation.

### 6.3. Dedicated TypeConverter

If the application already has a specific TypeConverter, the builder can accept a TypeConverter instead of a ConversionService. Choose a single unified conversion configuration source to avoid differing behavior across contexts.

Test both successful and failed conversion cases. `canConvert` only checks type-level convertibility; runtime values can still be malformed.

## 7. Variables and the Root Object

### 7.1. Passing the Root Object

The root object can be supplied directly at evaluation time:

~~~java
Boolean result = parser
        .parseExpression("active && total >= 100")
        .getValue(context, orderView, Boolean.class);
~~~

The root object should be a small DTO or view object containing only the data the expression needs to read.

### 7.2. Using Context Variables

Variables can be registered and referenced with `#`:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

Expression:

~~~java
total >= #minimumTotal
~~~

Variables help separate data from the expression source. If data is user-supplied, validate its type and value domain before placing it into the context.

### 7.3. `#root` and `#this`

In an expression, `#root` references the root object of the evaluation. `#this` references the current object and can change during operations such as selection or projection.

Example:

~~~java
orders.?[#this.total >= #root.minimumTotal]
~~~

If the root object is a view containing `orders` and `minimumTotal`, `#this` inside the predicate is each order while `#root` remains the original view.

Test the scope of these two special variables when expressions nest multiple collection operations.

## 8. SimpleEvaluationContext vs. StandardEvaluationContext

The two contexts serve different levels of need:

| Criterion | SimpleEvaluationContext | StandardEvaluationContext |
|---|---|---|
| Goal | Restricted SpEL subset | Full-featured SpEL |
| Property access | Accessor chosen via builder | Has default accessors and customization |
| Property writes | Choose read-only or read-write | Depends on accessors |
| Method invocation | Disabled by default, enabled intentionally | Has default resolvers |
| Type references | Not supported like full context | Supported via TypeLocator |
| Constructors | Not supported | Supported via ConstructorResolver |
| Bean references | Not supported | Can be supported via BeanResolver |
| Control level | Selects a small feature set | Requires careful configuration of broad privileges |

Do not choose SimpleEvaluationContext solely because its name contains the word "simple". Base the choice on the syntax and behavior the application actually needs.

If an expression needs a feature absent from SimpleEvaluationContext, first check whether it can be replaced with prepared data or a Java method called at the application layer.

## 9. SimpleEvaluationContext Is Not a Complete Sandbox

### 9.1. Getters Can Consume Resources

Expressions can read properties whose getters execute queries or heavy processing. A restricted context cannot automatically assess the cost of a getter.

Use DTOs holding preloaded data, avoid getters with I/O, and bound collection sizes before passing them into the context.

### 9.2. Instance Methods Can Cause Side Effects

If `withInstanceMethods()` is enabled, expressions can invoke methods allowed by the resolver on the object. A method can mutate state, write to a database, or call external services.

Enable instance methods only for objects with small, clear APIs. Prefer pure methods without side effects or external data dependencies.

### 9.3. Does Not Automatically Bound Time or Memory

SimpleEvaluationContext does not enforce limits on CPU, heap, expression length, or collection element counts. An expression can still iterate over large collections or trigger resource-intensive getters.

The application needs separate limits:

- Expression source length before parsing.
- Input string and collection sizes.
- Nesting structure depth.
- Evaluation count per user or tenant.
- Cost and duration of callable methods.
- Result size before passing to the next step.

A timeout at the layer awaiting the result does not automatically stop a running Java method. Do not rely on a single timeout to isolate untrusted expressions.

### 9.4. Does Not Replace Authorization

A restricted context does not verify that a user has permission to access data. If the root object contains information from multiple tenants or users, the expression can read every property permitted by the accessor.

Scope the root data by principal and tenant at the service layer before creating the context. Authorization must still be enforced at the business layer.

### 9.5. Do Not Grant Broadly Privileged Objects

Do not set ApplicationContext, BeanFactory, general repositories, or administrative services as the root object. Even though the context does not support bean references, objects placed into the root can still expose properties or methods.

Provide only a narrow-scoped DTO/view and the necessary variables.

## 10. Example: Evaluating a Read-Only Rule

Suppose a rule only needs to know status and total amount:

~~~java
public record OrderRuleView(
        String status,
        BigDecimal total,
        boolean customerActive
) {
}
~~~

Create the context:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

context.setVariable(
        "minimumTotal",
        new BigDecimal("100")
);
~~~

Evaluate:

~~~java
OrderRuleView order = new OrderRuleView(
        "PAID",
        new BigDecimal("125.50"),
        true
);

ExpressionParser parser = new SpelExpressionParser();

Boolean eligible = parser
        .parseExpression(
                "status == 'PAID' " +
                "&& customerActive " +
                "&& total >= #minimumTotal"
        )
        .getValue(context, order, Boolean.class);
~~~

The expression reads only three properties and one variable. It needs no bean references, constructor expressions, or type references.

This is the kind of use case suited for SimpleEvaluationContext: data is already prepared in Java, while SpEL merely expresses a small condition.

## 11. Example: Enabling Instance Methods Under Control

Suppose a view object has a pure predicate:

~~~java
public class OrderRuleView {

    private final BigDecimal total;
    private final String status;

    public OrderRuleView(BigDecimal total, String status) {
        this.total = total;
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }

    public boolean isHighValue() {
        return total.compareTo(new BigDecimal("1000")) >= 0;
    }
}
~~~

Create a context with instance methods:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

Expression:

~~~java
isHighValue() && status == 'PAID'
~~~

Evaluate:

~~~java
Boolean eligible = parser
        .parseExpression("isHighValue() && status == 'PAID'")
        .getValue(context, orderView, Boolean.class);
~~~

The `isHighValue` method only computes from existing data and performs no I/O. This is a much more suitable kind of method to allow expressions to call.

Do not expose methods like `sendPayment()`, `deleteCustomer()`, or `executeQuery()` merely because the builder can enable instance method invocation.

## 12. Example: Read-Write Binding and Validation

Suppose a form has writable properties:

~~~java
public class SearchForm {

    private String keyword;
    private Integer pageSize;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
~~~

Create a read-write context:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

Assign values:

~~~java
SearchForm form = new SearchForm();

parser.parseExpression("keyword")
        .setValue(context, form, "spring");

parser.parseExpression("pageSize")
        .setValue(context, form, "20");
~~~

If the converter supports String to Integer and the accessor can write `pageSize`, the value `"20"` can be converted to an Integer before assignment.

After binding, you still need to validate:

- `keyword` has an appropriate length.
- `pageSize` is within the allowed range.
- Required fields have values.
- No fields outside the allowlist were updated.

SimpleEvaluationContext controls the SpEL feature set; it does not replace form validation or authorization.

## 13. Common Mistakes

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Cannot read property | Appropriate accessor not configured or property does not exist | Use the right builder/accessor and verify the model |
| Cannot write property | Read-only context or property does not support writing | Use read-write when needed and check setter |
| Method invocation fails | Instance methods not enabled or no matching resolver | Enable resolver only when the use case needs it |
| `T(...)` does not work | SimpleEvaluationContext does not support type references | Use data/logic prepared in Java |
| Constructor expression does not work | Context does not support constructor invocation | Instantiate objects in Java and pass into context |
| `@beanName` does not resolve | SimpleEvaluationContext does not provide bean references | Call the bean in Java or design a data facade |
| Conversion fails | No converter or malformed data | Configure ConversionService and validate input |
| Nested path hits null | Intermediate property is null | Check for null or prepare the object graph |
| Expression runs slowly | Resource-heavy getter/method or collection | Use small views, limit data and methods |
| Data access risk remains | Root object contains too much information | Narrow the data and verify authorization |

When an expression fails, distinguish syntax errors, property access errors, method resolution errors, and conversion errors. Do not catch all exceptions and return `false` or `null`, as that can mask configuration bugs.

## 14. Process for Selecting and Configuring a Context

Before implementing, answer these questions:

1. Does the expression only read properties or does it need to write data?
2. Does it need to invoke instance methods?
3. Does it need Java type references, constructors, or bean references?
4. Does the root object contain strictly the minimal data?
5. Is a custom converter needed for domain types?
6. Are permitted getters and methods pure, lightweight, and deterministic?
7. Are expression length, data sizes, and evaluation frequency bounded?
8. Is the result validated before use in business logic?

If only reading properties is needed, start with `forReadOnlyDataBinding()`. If write binding is needed, use `forReadWriteDataBinding()` with a narrowly scoped target object. If custom accessors are needed, provide specific `PropertyAccessor`s. Enable instance methods only with a clear reason and after controlling the callable APIs.

If constructors, type references, or bean references are needed, review whether that logic can be executed in Java before evaluating the expression. Only switch to StandardEvaluationContext when full capabilities are genuinely required and an appropriate permission policy has been established.

## 15. Testing SimpleEvaluationContext

Test both permitted capabilities and restricted syntax:

~~~java
ExpressionParser parser = new SpelExpressionParser();

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .build();

OrderRuleView order = new OrderRuleView(
        new BigDecimal("125.50"),
        "PAID"
);

assertEquals(
        "PAID",
        parser.parseExpression("status")
                .getValue(context, order, String.class)
);
~~~

Test that method invocation is not enabled by default:

~~~java
assertThrows(
        EvaluationException.class,
        () -> parser.parseExpression("isHighValue()")
                .getValue(context, order)
);
~~~

Then create a context with instance methods and confirm pure methods can be called:

~~~java
SimpleEvaluationContext methodContext =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("isHighValue()")
                .getValue(methodContext, order, Boolean.class)
);
~~~

Additional cases to test:

- Reading valid properties and non-existent properties.
- Null nested properties.
- Writing properties in read-write mode and failing in read-only mode.
- Type conversion with ConversionService.
- Method invocation when disabled and when enabled.
- Non-existent methods or mismatched arguments.
- Restricted type reference, constructor, and bean reference syntax.
- Root objects containing minimal data.
- Large collections near thresholds and long expressions near limits.
- Failing getters/methods to confirm exceptions are handled properly.

Test against the application's actual Spring version, as builder APIs and accessor details may vary between versions.

## 16. Summary

SimpleEvaluationContext provides a subset of SpEL so applications can control property access and additionally enabled capabilities.

- Use `forReadOnlyDataBinding()` for read-only expressions.
- Use `forReadWriteDataBinding()` when updating writable properties is needed.
- Use `forPropertyAccessors(...)` when a custom property access model is required.
- Method invocation is not enabled by default; `withInstanceMethods()` can enable instance method calls when genuinely needed.
- ConversionService or TypeConverter can be configured.
- Does not support type references, constructor expressions, and bean references like StandardEvaluationContext.
- Does not automatically bound CPU, memory, expression length, or business permissions.
- Getters and methods are still code that can consume resources or produce side effects.

Prefer small root objects, specific property accessors, read-only expressions, and validated data. SimpleEvaluationContext is a useful privilege-reduction layer for rules and data binding, while resource limits, authorization, and behavior control must still be enforced at the application layer.