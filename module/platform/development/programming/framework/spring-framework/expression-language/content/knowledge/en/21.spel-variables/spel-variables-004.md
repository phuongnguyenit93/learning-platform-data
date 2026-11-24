# Variables Shared Across Multiple Parts of an Expression

In Spring Expression Language (SpEL), a **variable** is a value supplied to an expression through an **EvaluationContext**. An expression references a variable using the **#** symbol followed by the variable name, for example **#order**, **#minimumTotal**, or **#currentUser**.

A single variable can be used in multiple positions within the same expression: conditions, ternary branches, method arguments, selection expressions, or projection expressions. If multiple expressions are evaluated using the same EvaluationContext, they can also share the variables registered in that context.

This mechanism helps separate input data from the expression string. Instead of repeating a value or embedding data directly into the string, the application registers the variable once and references it wherever needed.

## 1. Variable Syntax

Reference syntax:

~~~text
#variableName
~~~

Examples:

~~~text
#order
#minimumTotal
#currentUser
#featureEnabled
~~~

The **#** symbol distinguishes a variable from a root object property and a bean reference:

- **#order**: variable named order in EvaluationContext.
- **order**: order property on the current root object.
- **@orderService**: bean named orderService in the Spring container, resolved via BeanResolver.

Variable names are case-sensitive according to the registered name. If a variable minimumTotal is registered, the expression must reference that exact name using #minimumTotal.

A variable can hold many kinds of values: String, numbers, boolean, domain objects, collections, Maps, or any object that EvaluationContext can provide. SpEL does not require every variable to be a simple type.

## 2. Registering Variables in EvaluationContext

A common approach is to use StandardEvaluationContext and call setVariable():

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("region", "APAC");
context.setVariable("enabled", true);

Boolean accepted = parser
        .parseExpression("#minimumTotal >= 100")
        .getValue(context, Boolean.class);
~~~

Here, three variables are registered in the context. The expression uses #minimumTotal to read the registered value. The remaining variables can be used in other expressions evaluated with the same context.

You can register a root object separately from variables:

~~~java
context.setRootObject(order);
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("taxRate", new BigDecimal("0.08"));
~~~

Then, the expression can combine properties of the root object and variables:

~~~text
total >= #minimumTotal and #taxRate > 0
~~~

In the example, total is read from the root object order, while minimumTotal and taxRate are retrieved from EvaluationContext.

### 2.1. Reading and Updating Variables from Java

StandardEvaluationContext supports reading a variable with lookupVariable() and updating it with setVariable():

~~~java
context.setVariable("region", "APAC");

Object currentRegion = context.lookupVariable("region");

context.setVariable("region", "EMEA");
~~~

An expression evaluated after the update reads the current value in the context:

~~~text
#region
~~~

Updating a variable affects the EvaluationContext. If multiple expressions share that context, subsequent evaluations will see the new value.

Name variables to reflect their meaning and data type. This helps readers see what data an expression depends on without tracing literal strings scattered across the expression.

## 3. Sharing Variables Across Multiple Parts of an Expression

An expression can contain multiple subexpressions, such as logical conditions, ternary operators, method calls, selection, or projection. A registered variable can be referenced in each of those parts.

Example:

~~~text
#order.total >= #minimumTotal
    and #currentUser.active
    and #region == 'APAC'
~~~

Three variables can be used in the same condition:

- #minimumTotal supplies the total amount threshold.
- #currentUser supplies the user performing the action.
- #region supplies the processing region.

There is no need to register a separate copy of a variable for each part. All parts of the expression read the same value from EvaluationContext.

### 3.1. Using One Variable Multiple Times in a Ternary

~~~text
#order.total >= #minimumTotal
    ? #order.total * #taxRate
    : #minimumTotal * #taxRate
~~~

The taxRate and minimumTotal variables are used in both the condition and the two result branches. This allows a configuration value to be reused without duplicating the actual value inside the expression.

### 3.2. Using Variables in Method Calls

~~~text
@pricingService.calculate(#order, #customerTier, #currency)
~~~

All arguments come from variables or data provided by the context. If the same customerTier is also used in another condition in the expression, it is still referenced with #customerTier.

### 3.3. Using Variables Inside Selection and Projection

Example of filtering orders by a threshold and then transforming each order into its tax-included amount:

~~~text
#orders.?[total >= #minimumTotal]
       .![total * (1 + #taxRate)]
~~~

In selection, #minimumTotal is a shared variable used to filter each Order. In projection, #taxRate is used to calculate the value for each remaining Order.

Variables are read from the same EvaluationContext, even while the expression is evaluating a collection element. Changing the current evaluation object does not remove registered variables.

## 4. Complete Example: Reusing Variables Across Multiple Steps

Suppose an application needs to filter orders meeting a threshold, then obtain the total amount after tax:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("orders", orders);
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("taxRate", new BigDecimal("0.08"));

Expression expression = parser.parseExpression(
        "#orders.?[total >= #minimumTotal].![total * (1 + #taxRate)]"
);

List<?> totals = expression.getValue(context, List.class);
~~~

Process:

1. #orders retrieves the source collection.
2. Selection .?[total >= #minimumTotal] retains Orders whose total meets the threshold.
3. Projection .![total * (1 + #taxRate)] calculates the after-tax total for each remaining Order.
4. The result is a List of values computed from the selected orders.

minimumTotal and taxRate are registered just once. They are used in different parts of the same expression and retain their meaning throughout evaluation.

## 5. Sharing Variables Across Multiple Expression Objects

Not only subexpressions within the same string can share variables. Multiple separately parsed Expression objects can also read the same variables if they are evaluated using the same EvaluationContext.

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("currency", "VND");

Expression checkMinimum =
        parser.parseExpression("#amount >= #minimumTotal");

Expression formatLabel =
        parser.parseExpression(
            "#currency + ' ' + #amount"
        );

context.setVariable("amount", new BigDecimal("250.00"));

Boolean accepted = checkMinimum.getValue(context, Boolean.class);
String label = formatLabel.getValue(context, String.class);
~~~

The two Expressions are parsed independently, yet share the same context so both can read minimumTotal, currency, and amount.

If a new EvaluationContext is created, variables registered in the old context do not automatically appear in the new context. You must re-register the required values or create new contexts from a shared initializer.

### 5.1. Updating Values Between Two Evaluations

You can change a variable and then re-evaluate the same Expression:

~~~java
Expression checkMinimum =
        parser.parseExpression("#amount >= #minimumTotal");

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("amount", new BigDecimal("120.00"));

Boolean first = checkMinimum.getValue(context, Boolean.class);

context.setVariable("minimumTotal", new BigDecimal("150.00"));

Boolean second = checkMinimum.getValue(context, Boolean.class);
~~~

The first evaluation reads the 100.00 threshold; the next reads the 150.00 threshold. The parsed Expression does not need to be recreated just because a variable value changed.

This is helpful when an expression template is reused across multiple input datasets. However, you must ensure the context holds the right data for each evaluation.

## 6. Distinguishing Variables from #root and #this

SpEL has two special variables that frequently appear in expressions:

- **#root** represents the root object of EvaluationContext.
- **#this** represents the current evaluation object and can change when SpEL enters another part of an expression, such as selection or projection.

Application-registered variables like #minimumTotal or #currentUser are separate values in the context. They do not replace the root object and do not change with the current element.

Suppose the root object is a ReportRequest containing an orders collection and a report name:

~~~java
context.setRootObject(reportRequest);
context.setVariable("minimumTotal", new BigDecimal("100.00"));
~~~

Expression:

~~~text
#orders.?[
    total >= #minimumTotal
    and #this.customer.active
]
~~~

In selection:

- #this is the Order being checked.
- #minimumTotal is a variable registered in the context and keeps the same value during each check.
- #root remains the original ReportRequest if report-level data needs to be referenced.

You can use root and variables in the same expression:

~~~text
#root.reportName + ': ' + #minimumTotal
~~~

When entering selection or projection, #this may change, but #root and registered variables still refer to their respective context targets.

## 7. Variables in Spring Integration Points

Some Spring modules create an EvaluationContext themselves and supply variables according to the context of the annotation or operation being performed. These variables can be shared across multiple parts of the expression within that same integration point.

The available variable set depends on the module. Do not assume a variable name present in Spring Cache is also present in Spring Security or in @Value.

### 7.1. Spring Cache

In method-based cache annotations, SpEL can access method parameters by name if Spring can discover parameter names. Positional aliases such as #p0 or #a0 can be used when needed.

Example:

~~~java
@Cacheable(
    cacheNames = "customer",
    key = "#tenantId + ':' + #customerId",
    condition = "#customerId != null and #tenantId != null"
)
public Customer find(String tenantId, String customerId) {
    // ...
}
~~~

tenantId and customerId are used in both key and condition. Both expression parts retrieve data from the context created by Spring Cache for the method invocation.

If parameter names are not discovered, use positional aliases or appropriate compiler/metadata configuration. Do not assume Java parameter names are always available across every build configuration.

### 7.2. Spring Method Security

Method Security also supplies method parameters into EvaluationContext. Example:

~~~java
@PreAuthorize(
    "#request.tenantId == authentication.principal.tenantId"
    + " and #request.ownerId == authentication.principal.id"
)
public Document read(DocumentRequest request) {
    // ...
}
~~~

In the expression, request is used in two conditions. It is method parameter data supplied by Spring Security's context.

The ability to reference parameters by name depends on how Spring obtains parameter names, such as compiler metadata or supported parameter annotations. If names are unavailable, you can use the positional aliases provided by the module.

### 7.3. Creating EvaluationContext Manually

If the application parses and evaluates expressions itself, the application is responsible for registering the required variables:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("currentUser", currentUser);
context.setVariable("tenantId", tenantId);
context.setVariable("permissions", permissions);
~~~

Expression:

~~~text
#currentUser.active
    and #tenantId == #currentUser.tenantId
    and #permissions.contains('document:read')
~~~

There is no automatic list of variables shared across every application. The context is where you define the exact data exposed to the expression.

## 8. Are Variables Retained by Reference or Copied?

EvaluationContext stores the value registered for a variable. When the value is an object, the context keeps a reference to that object; SpEL does not automatically deep-copy the object upon setVariable().

Example:

~~~java
Customer customer = new Customer("CUS-001");

context.setVariable("customer", customer);

customer.setName("CUS-002");
~~~

An expression evaluated after mutating the object can read the new state via #customer:

~~~text
#customer.name
~~~

Similarly, if a variable holds a List or Map, modifying the collection's contents can also affect the results of subsequent evaluations.

This is useful when an expression needs to read the latest state of an object, but requires care if the context is reused. If you want the expression to use a data snapshot, pass an immutable object or an explicit copy created on the Java side.

## 9. Variable Lifecycle and Sharing Scope

A variable belongs to the EvaluationContext in which it was registered. It does not automatically become a global, static variable or shared data for every expression across the entire application.

The cases can be distinguished as follows:

| Case | Is Variable Available? |
| --- | --- |
| Multiple subexpressions in the same evaluation | Yes, if using the same EvaluationContext |
| Multiple Expression objects evaluated with the same context | Yes |
| Expression evaluated with a new context | Not automatically; must be re-registered |
| Expression running in another Spring integration point | Depends on the context provided by that integration point |
| A context reused after setVariable() | The current value is used for the next evaluation |

If an application reuses a StandardEvaluationContext, explicitly manage when input data is updated and cleared. Do not share a mutable context across multiple concurrent requests when each request needs different variables; doing so can cause one evaluation to accidentally read another's data.

A straightforward approach is to create a dedicated context for each processing pass or unit of work:

~~~java
StandardEvaluationContext createContext(
        Order order,
        BigDecimal minimumTotal,
        User currentUser) {

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);
    context.setVariable("currentUser", currentUser);

    return context;
}
~~~

Parsed Expressions can be reused, while each processing pass receives its own EvaluationContext with the appropriate variables.

## 10. Variables and Functions in SpEL

Variables typically hold data: objects, numbers, strings, collections, or booleans. SpEL can also register a Java method as a function in EvaluationContext. A function is invoked with syntax using # and parentheses:

~~~text
#normalizeCode(#rawCode)
~~~

A function is not the same as an ordinary data variable, even though the function name is also registered in the context. When a reusable transformation is needed, a function may fit better than storing a value.

For example, with StandardEvaluationContext you can register a Method:

~~~java
Method normalizeMethod =
        CodeFunctions.class.getDeclaredMethod("normalize", String.class);

context.registerFunction("normalizeCode", normalizeMethod);
~~~

The CodeFunctions class can define a static method:

~~~java
public class CodeFunctions {

    public static String normalize(String code) {
        return code == null ? null : code.trim().toUpperCase();
    }
}
~~~

Then the expression can invoke:

~~~text
#normalizeCode(#rawCode)
~~~

The registered method must have a signature compatible with the call and be accessible via reflection. Check the API for the Spring version in use if the application relies on function registration.

If logic has many dependencies or needs to access a Spring service, a bean method invoked via @beanName usually conveys intent more clearly than a static function.

## 11. Testing Shared Variables

You can write unit tests to verify that multiple parts of an expression read the same variable:

~~~java
class SharedExpressionVariableTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void reusesVariablesInSelectionAndProjection() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("orders", List.of(
                new Order("A-1", new BigDecimal("120.00")),
                new Order("A-2", new BigDecimal("80.00")),
                new Order("A-3", new BigDecimal("200.00"))
        ));
        context.setVariable("minimumTotal", new BigDecimal("100.00"));
        context.setVariable("taxRate", new BigDecimal("0.10"));

        List<?> totals = parser
                .parseExpression(
                    "#orders.?[total >= #minimumTotal]"
                    + ".![total * (1 + #taxRate)]"
                )
                .getValue(context, List.class);

        assertEquals(
                List.of(
                    new BigDecimal("132.0000"),
                    new BigDecimal("220.0000")
                ),
                totals
        );
    }

    @Test
    void separateExpressionsCanShareOneContext() {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        context.setVariable("limit", 10);
        context.setVariable("value", 15);

        Expression condition =
                parser.parseExpression("#value >= #limit");

        Expression message =
                parser.parseExpression(
                    "'value=' + #value + ', limit=' + #limit"
                );

        assertEquals(Boolean.TRUE,
                condition.getValue(context, Boolean.class));

        assertEquals("value=15, limit=10",
                message.getValue(context, String.class));
    }
}
~~~

The first test uses minimumTotal in selection and taxRate in projection. The second test parses two separate Expressions but passes the same EvaluationContext when evaluating.

When testing, also verify updating a variable between two evaluations and creating a new context. That helps catch bugs caused by stale data remaining in the context or forgetting to register a variable for a new processing pass.

## 12. Common Mistakes When Using Variables

1. **Forgetting the # symbol:** writing minimumTotal instead of #minimumTotal when intending to read a variable.
2. **Not registering the variable:** the expression references #currentUser, but the context was not supplied with that value.
3. **Registering under the wrong name:** the name in setVariable() does not match the name referenced in the expression.
4. **Confusing variables with beans:** #pricingService is a variable; @pricingService is a bean reference requiring a BeanResolver.
5. **Confusing variables with root properties:** order is a property of the root object; #order is a variable.
6. **Assuming a new context inherits old variables:** each EvaluationContext has its own data, unless the application registers them again.
7. **Reusing a context with different request data:** old variables may remain or be updated at the wrong time.
8. **Assuming variables are copies:** if a variable holds a mutable object, changes to the object may be visible in subsequent evaluations.
9. **Assuming every annotation has the same variables:** each Spring integration point defines its own EvaluationContext and variable set.
10. **Exposing untrusted data in an overly broad expression context:** provide only the objects and access permissions needed.

## 13. Quick Takeaways

- Variables in SpEL are referenced using the **#variableName** syntax.
- Register variables using **EvaluationContext.setVariable(name, value)**.
- Values can be read from Java using **lookupVariable(name)** on StandardEvaluationContext.
- Multiple parts of the same expression can share variables from EvaluationContext.
- Multiple Expression objects can also share variables if evaluated with the same context.
- Variables can be used in conditions, ternaries, method arguments, selection, and projection.
- In collection operations, **#this** can change per element; variables like #minimumTotal remain the value supplied in the context.
- **#root** is the root object; **#this** is the current evaluation object; application-registered variables are separate data.
- A new context does not automatically inherit variables from an old context.
- Registered objects or collections are generally kept by reference, not deep-copied.
- Create a separate context per processing unit when evaluations require different sets of variables.
- Spring Cache, Method Security, and other integration points can provide their own variables; check the specific module's context.

## 14. Official References

- [Spring Framework — Variables in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — Collection Selection and Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework — Cache Annotation SpEL Context](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Security — Method Security Expressions](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
