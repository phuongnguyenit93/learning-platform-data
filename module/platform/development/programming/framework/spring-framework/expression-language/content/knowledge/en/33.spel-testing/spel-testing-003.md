# Testing Root Objects and Variables in SpEL

## 1. Two data sources in an expression

Spring Expression Language (SpEL) evaluates expressions within an EvaluationContext. The context provides a root object and variables that the expression can reference.

These two data sources have different syntax:

- Properties on the root object are accessed directly by name, such as customer.name or total.
- Variables are referenced with the # prefix, such as #minimumTotal or #currentUser.
- #root references the root object of the evaluation.
- #this references the current object; in a regular expression it is the root object, whereas inside collection selection/projection it is the element currently being processed.

A good test should clearly verify which source an expression reads data from. Confusing a root property with a variable can cause the expression to return null, use the wrong data, or fail during evaluation.

## 2. Preparing a small root object fixture

Use a POJO fixture with getters for the properties the expression needs to read. There is no need to start the entire Spring ApplicationContext if the goal is only to test the SpEL parser and evaluation.

~~~java
public class Customer {
    private final String name;
    private final boolean active;

    public Customer(String name, boolean active) {
        this.name = name;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }
}

public class Order {
    private final String code;
    private final Customer customer;
    private final int total;

    public Order(String code, Customer customer, int total) {
        this.code = code;
        this.customer = customer;
        this.total = total;
    }

    public String getCode() {
        return code;
    }

    public Customer getCustomer() {
        return customer;
    }

    public int getTotal() {
        return total;
    }
}
~~~

A fixture with deterministic data makes tests readable and repeatable. If the expression only reads code and total, there is no need to build the application's entire entity graph. If the expression reads customer.name, the fixture must have customer and the corresponding name getter.

## 3. Testing the root object directly

When only root object properties are needed, the object can be passed directly into the getValue(rootObject, resultType) overload:

~~~java
@Test
void readsPropertyFromRootObject() {
    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("customer.name");

    String name = expression.getValue(order, String.class);

    assertEquals("Lan", name);
}
~~~

Here, order is the root object. SpEL reads customer from order and then reads name from Customer. There is no need to create a separate StandardEvaluationContext when the expression only needs a root object and does not require variables or custom resolvers.

Multiple properties can be tested with separate expressions:

~~~java
Expression codeExpression = parser.parseExpression("code");
Expression totalExpression = parser.parseExpression("total");

assertEquals("ORD-1001",
        codeExpression.getValue(order, String.class));
assertEquals(Integer.valueOf(150),
        totalExpression.getValue(order, Integer.class));
~~~

Passing a result type to getValue explicitly expresses the type expected by the calling code. If the expression does not return a compatible value, SpEL may raise a conversion or evaluation error.

## 4. Creating a StandardEvaluationContext with a root object

When an expression needs both root object properties and variables, place the root object into StandardEvaluationContext:

~~~java
@Test
void evaluatesRootPropertiesAndVariablesTogether() {
    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", 100);

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "customer.active and total >= #minimumTotal");

    Boolean eligible = expression.getValue(context, Boolean.class);

    assertTrue(eligible);
}
~~~

In this expression:

- customer.active is read from the root object.
- total is read from the root object.
- #minimumTotal is read from a variable in the context.
- The final result is a Boolean.

This style allows the test to verify both data sources in a single evaluation. It also reflects how applications typically use SpEL when combining business objects with configuration parameters or supplemental data.

## 5. Distinguishing root properties from identically named variables

A root object property and a variable can have the same name, yet are referenced with different syntax. Properties use the direct name; variables use the # prefix.

~~~java
public class SearchRequest {
    private final String category;

    public SearchRequest(String category) {
        this.category = category;
    }

    public String getCategory() {
        return category;
    }
}
~~~

The test below sets the category variable differently from the root's category property:

~~~java
@Test
void distinguishesRootPropertyFromVariable() {
    SearchRequest request = new SearchRequest("books");

    StandardEvaluationContext context =
            new StandardEvaluationContext(request);
    context.setVariable("category", "music");

    Expression rootExpression =
            new SpelExpressionParser().parseExpression("category");
    Expression variableExpression =
            new SpelExpressionParser().parseExpression("#category");

    assertEquals("books",
            rootExpression.getValue(context, String.class));
    assertEquals("music",
            variableExpression.getValue(context, String.class));
}
~~~

This test ensures the expression does not accidentally read from the wrong source. When variable and property names can easily be confused, give variables distinct meaningful names, such as minimumTotal, currentUser, or allowedRegions.

## 6. Testing #root and #this

At the top level, #root and #this both refer to the root object:

~~~java
@Test
void rootAndThisReferToRootOutsideCollectionOperations() {
    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    ExpressionParser parser = new SpelExpressionParser();

    Expression rootExpression =
            parser.parseExpression("#root.customer.name");
    Expression thisExpression =
            parser.parseExpression("#this.customer.name");

    assertEquals("Lan",
            rootExpression.getValue(order, String.class));
    assertEquals("Lan",
            thisExpression.getValue(order, String.class));
}
~~~

Inside collection operations, #this changes to the current element. #root continues to refer to the original object of the evaluation.

~~~java
public class Item {
    private final String name;
    private final int price;

    public Item(String name, int price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public int getPrice() {
        return price;
    }
}

public class Catalog {
    private final String owner;
    private final List<Item> items;

    public Catalog(String owner, List<Item> items) {
        this.owner = owner;
        this.items = items;
    }

    public String getOwner() {
        return owner;
    }

    public List<Item> getItems() {
        return items;
    }
}
~~~

Example selection test using both scopes:

~~~java
@Test
void distinguishesRootAndCurrentItemInSelection() {
    Catalog catalog = new Catalog(
            "Lan",
            List.of(
                    new Item("A", 50),
                    new Item("B", 150),
                    new Item("C", 250)));

    StandardEvaluationContext context =
            new StandardEvaluationContext(catalog);
    context.setVariable("ownerFilter", "Lan");
    context.setVariable("minimumPrice", 100);

    Expression expression = new SpelExpressionParser()
            .parseExpression(
                    "items.?[#root.owner == #ownerFilter "
                    + "and #this.price >= #minimumPrice]");

    List<?> selected = expression.getValue(context, List.class);

    assertEquals(2, selected.size());
    assertEquals("B", ((Item) selected.get(0)).getName());
    assertEquals("C", ((Item) selected.get(1)).getName());
}
~~~

Inside the predicate, #root.owner always reads the owner of Catalog. #this.price reads the price of the Item currently being evaluated. #ownerFilter and #minimumPrice are context variables.

## 7. Using variables as selection conditions

Variables often represent search parameters, thresholds, or configuration flags. They can be used in selection to reuse the same expression with multiple inputs:

~~~java
Expression expression =
        new SpelExpressionParser()
                .parseExpression("items.?[price >= #minimumPrice]");

Catalog catalog = new Catalog(
        "Lan",
        List.of(
                new Item("A", 50),
                new Item("B", 150),
                new Item("C", 250)));

StandardEvaluationContext context =
        new StandardEvaluationContext(catalog);

context.setVariable("minimumPrice", 100);
List<?> firstResult = expression.getValue(context, List.class);

context.setVariable("minimumPrice", 200);
List<?> secondResult = expression.getValue(context, List.class);

assertEquals(2, firstResult.size());
assertEquals(1, secondResult.size());
assertEquals("C", ((Item) secondResult.get(0)).getName());
~~~

The expression source does not change. The minimumPrice value is fetched from the context at evaluation time. This makes it easy to test the same rule against multiple data sets without concatenating values into the expression string.

If you need to confirm the exact selected elements, assert both content and order instead of only checking size.

## 8. Variables can be objects or collections

A variable does not only hold a String or number. It can reference an object, a collection, or another business domain type.

~~~java
@Test
void readsPropertiesFromObjectVariable() {
    Customer customer = new Customer("Minh", true);

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("currentCustomer", customer);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("#currentCustomer.name");

    String name = expression.getValue(context, String.class);

    assertEquals("Minh", name);
}
~~~

A collection can be passed as a variable:

~~~java
@Test
void selectsFromCollectionVariable() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable(
            "items",
            List.of(
                    new Item("A", 50),
                    new Item("B", 150)));

    context.setVariable("minimumPrice", 100);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("#items.?[price >= #minimumPrice]");

    List<?> result = expression.getValue(context, List.class);

    assertEquals(1, result.size());
    assertEquals("B", ((Item) result.get(0)).getName());
}
~~~

In this case, #items is a collection variable. Inside the selection, #this is each Item; #minimumPrice remains a context variable.

## 9. Testing method arguments and variables

When an expression is invoked from Java code, input parameters can be placed into the context via setVariable. Use meaningful names rather than embedding values directly into the expression source.

~~~java
@Test
void usesVariablesAsExpressionInputs() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("subtotal", 120);
    context.setVariable("discountRate", 0.10);

    Expression expression = new SpelExpressionParser()
            .parseExpression("#subtotal * (1 - #discountRate)");

    Double finalAmount = expression.getValue(context, Double.class);

    assertEquals(108.0, finalAmount);
}
~~~

Inside a service method, a context can be created for each processing call:

~~~java
public boolean isAllowed(Order order, int minimumTotal) {
    StandardEvaluationContext context =
            new StandardEvaluationContext(order);

    context.setVariable("minimumTotal", minimumTotal);

    Expression expression =
            parser.parseExpression("total >= #minimumTotal");

    return Boolean.TRUE.equals(
            expression.getValue(context, Boolean.class));
}
~~~

Tests should confirm that variables are passed properly and that results change according to input values. For simple logic, a Java condition may be easier to read than SpEL; this example is appropriate when the expression is part of configuration or stored for repeated evaluation.

## 10. Testing multiple variable sets

Parameterized tests can be used to confirm the same expression works with multiple variable sets:

~~~java
@ParameterizedTest
@CsvSource({
        "100, true",
        "150, true",
        "151, false"
})
void checksOrderTotalAgainstVariable(
        int minimumTotal,
        boolean expected) {

    Order order = new Order(
            "ORD-1001",
            new Customer("Lan", true),
            150);

    StandardEvaluationContext context =
            new StandardEvaluationContext(order);
    context.setVariable("minimumTotal", minimumTotal);

    Expression expression = new SpelExpressionParser()
            .parseExpression("total >= #minimumTotal");

    Boolean actual = expression.getValue(context, Boolean.class);

    assertEquals(expected, actual);
}
~~~

Each test case creates its own context and sets the corresponding variable value. This ensures results do not depend on previous runs and clarifies the boundary between the expression source and input data.

If a test has many variables, use MethodSource with a test case object having clear field names instead of a long, hard-to-read parameter list.

## 11. Testing null or unprovided variables

A variable may have no value at evaluation time. If an expression uses that variable, explicitly verify the expected behavior: returning null, picking a default, or raising an error when the subsequent operation cannot be performed.

Example using Elvis to choose a default value:

~~~java
@Test
void usesDefaultWhenVariableHasNoValue() {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Expression expression = new SpelExpressionParser()
            .parseExpression("#displayName ?: 'Guest'");

    String result = expression.getValue(context, String.class);

    assertEquals("Guest", result);
}
~~~

A variable with a normal value can also be tested:

~~~java
context.setVariable("displayName", "Lan");

assertEquals(
        "Lan",
        expression.getValue(context, String.class));
~~~

Elvis in SpEL uses the default value when the left-hand side is null or an empty string. If the business rule only wants to replace null, use an explicit condition. For required variables, it may be better for the test to confirm a configuration error rather than silently using a default.

Do not infer the origin of null solely from the expression result. If you need to distinguish "variable not passed" from "caller actively passed a no-data state", add a presence variable or use a request object with an explicit state.

## 12. Testing nested properties and null-safe access

A root object can contain null intermediate objects. When the expression needs to support this case, use null-safe navigation and test both complete data and missing data:

~~~java
@Test
void handlesNullableNestedRootProperty() {
    Expression expression = new SpelExpressionParser()
            .parseExpression("customer?.name ?: 'Guest'");

    Order withoutCustomer =
            new Order("ORD-1", null, 100);

    Order withCustomer =
            new Order("ORD-2", new Customer("Lan", true), 100);

    assertEquals(
            "Guest",
            expression.getValue(withoutCustomer, String.class));

    assertEquals(
            "Lan",
            expression.getValue(withCustomer, String.class));
}
~~~

If the expression traverses multiple object levels, guard each step that could be null:

~~~text
customer?.address?.city ?: 'Unknown'
~~~

The null-safe operator only guards the operation immediately following it. Tests should create fixtures with null at every nullable level to confirm the expression works according to contract.

## 13. Distinguishing parse errors from evaluation errors

The parser creates an Expression from source. Evaluation uses the root object and variables to execute the expression. The two stages can fail for different reasons.

A parse error occurs when the source is syntactically invalid:

~~~java
@Test
void rejectsInvalidExpressionSyntax() {
    ExpressionParser parser = new SpelExpressionParser();

    assertThrows(
            ParseException.class,
            () -> parser.parseExpression("customer."));
}
~~~

An evaluation error occurs when the expression is valid, but the root object or context does not provide the required property, method, or data type:

~~~java
@Test
void reportsMissingRootPropertyDuringEvaluation() {
    Order order = new Order(
            "ORD-1",
            new Customer("Lan", true),
            100);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("unknownProperty");

    assertThrows(
            EvaluationException.class,
            () -> expression.getValue(order));
}
~~~

In real tests, more specific exceptions can be checked if the application depends on the error type. Avoid depending on the full message text because message content may change across versions or locales.

## 14. Verifying the result type

If an expression is expected to return Boolean, String, or a specific type, use the getValue overload with a result type so the contract is clearly expressed:

~~~java
Expression expression =
        new SpelExpressionParser()
                .parseExpression("total >= #minimumTotal");

Boolean result = expression.getValue(context, Boolean.class);
~~~

Tests should not only check true/false outcomes but also confirm the return type matches the code consuming the expression. If an expression can return null, do not directly unbox Boolean to boolean without handling null.

For expressions returning collections, List.class can be requested and elements checked afterward:

~~~java
List<?> selected = expression.getValue(context, List.class);
~~~

If the application needs a specific generic element type, check the element contents and types in the test because Class<List> does not fully represent the generic type of the elements.

## 15. Reusing Expression while creating an appropriate context

An expression can be parsed once and evaluated with multiple different contexts:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("total >= #minimumTotal");

Order smallOrder = new Order(
        "ORD-1",
        new Customer("Lan", true),
        80);

Order largeOrder = new Order(
        "ORD-2",
        new Customer("Minh", true),
        180);

StandardEvaluationContext firstContext =
        new StandardEvaluationContext(smallOrder);
firstContext.setVariable("minimumTotal", 100);

StandardEvaluationContext secondContext =
        new StandardEvaluationContext(largeOrder);
secondContext.setVariable("minimumTotal", 100);

assertFalse(expression.getValue(firstContext, Boolean.class));
assertTrue(expression.getValue(secondContext, Boolean.class));
~~~

The expression source does not change, while each context has its own root object and variables. This keeps tests independent and prevents a test case from accidentally using the previous case's data.

If replacing the root object within the same context via setRootObject, update it explicitly before evaluating. In test suites, creating a new context for each case is usually easier to understand.

## 16. Avoiding shared mutable EvaluationContext across tests or requests

StandardEvaluationContext contains a mutable root object and variables. If multiple tests or requests modify one context, data can cross-contaminate.

Practical rules:

- Create a new context for each test case when the root object or variables differ.
- Do not retain variables reflecting the state of a previous request.
- Do not share a mutable context across concurrent requests without appropriate synchronization design.
- A parsed Expression can be reused if the source does not change, while passing an appropriate context for each evaluation.
- Use meaningful variable names and set all required inputs before evaluating.

Separating Expression from EvaluationContext keeps tests clear: the expression describes the rule, and the context holds the data for a single evaluation.

## 17. When to use POJOs and when to use Mockito?

POJO fixtures are usually appropriate when the root object is just a DTO or domain object with simple constructors. They provide real getters and keep tests close to how SpEL reads properties in the application.

Mockito is useful when the root object is an interface or collaborator with many dependencies, and the test needs to control getter values:

~~~java
OrderView order = mock(OrderView.class);
CustomerView customer = mock(CustomerView.class);

when(order.getCustomer()).thenReturn(customer);
when(customer.getName()).thenReturn("Lan");

Expression expression =
        new SpelExpressionParser()
                .parseExpression("customer.name");

assertEquals("Lan", expression.getValue(order, String.class));
~~~

Stub every getter that the expression accesses. Unstubbed getters typically return mock default values and can cause tests to reflect incorrect data.

There is no need to mock simple DTOs just to test property access. Real objects are usually easier to read and avoid depending on default mock behavior.

## 18. Testing custom contexts when needed

If the application uses a custom PropertyAccessor, BeanResolver, or TypeConverter, tests must configure those exact components. Merely creating a StandardEvaluationContext with a root object and variables will not automatically supply the application's custom resolvers.

Example attaching a TypeConverter:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

If the expression references a bean using @beanName syntax, the context needs an appropriate BeanResolver. If the expression accesses properties using custom rules, the context needs the corresponding PropertyAccessor.

Test the context with the exact configuration the application uses. A unit test checking only the root object and variables does not prove that custom resolvers or the conversion service are wired properly.

## 19. Comprehensive example with JUnit 5

The following example tests root properties, variables, #root, and #this in collection selection:

~~~java
class SpelRootAndVariablesTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void evaluatesRootAndVariablesTogether() {
        Catalog catalog = new Catalog(
                "Lan",
                List.of(
                        new Item("A", 50),
                        new Item("B", 150),
                        new Item("C", 250)));

        StandardEvaluationContext context =
                new StandardEvaluationContext(catalog);
        context.setVariable("ownerFilter", "Lan");
        context.setVariable("minimumPrice", 100);

        Expression expression = parser.parseExpression(
                "items.?[#root.owner == #ownerFilter "
                + "and #this.price >= #minimumPrice].![name]");

        List<?> names = expression.getValue(context, List.class);

        assertEquals(List.of("B", "C"), names);
    }

    @Test
    void evaluatesSameExpressionWithDifferentVariableValues() {
        Catalog catalog = new Catalog(
                "Lan",
                List.of(
                        new Item("A", 50),
                        new Item("B", 150),
                        new Item("C", 250)));

        Expression expression =
                parser.parseExpression("items.?[price >= #minimumPrice]");

        StandardEvaluationContext firstContext =
                new StandardEvaluationContext(catalog);
        firstContext.setVariable("minimumPrice", 100);

        StandardEvaluationContext secondContext =
                new StandardEvaluationContext(catalog);
        secondContext.setVariable("minimumPrice", 200);

        assertEquals(
                2,
                expression.getValue(firstContext, List.class).size());
        assertEquals(
                1,
                expression.getValue(secondContext, List.class).size());
    }
}
~~~

The Catalog and Item fixtures must have owner, items, name, and price getters as in previous examples. The two tests confirm that the context supplies data to the expression and the same expression can be evaluated with different variables.

## 20. Recommended test matrix

| Case | Root object | Variables | What to verify |
|---|---|---|---|
| Root property | Yes | No | Property is read from the right root |
| Single variable | Optional | Yes | #name returns the right value |
| Root and variable | Yes | Yes | The two data sources are distinguished |
| Identical property/variable name | Yes | Yes | Direct name and #name are not confused |
| #root and #this | Has collection | Optional | Object scope is correct at each level |
| Object variable | Optional | Object variable | Variable properties are read properly |
| Collection variable | Optional | Collection variable | Selection/projection uses the right elements |
| Missing or null variable | Optional | Missing/null | Default or error per contract |
| Null nested root property | Yes | Optional | Null-safe navigation works properly |
| Different root objects | Multiple objects | May differ | Expression does not depend on a specific fixture |
| Different contexts | Yes | Multiple variable sets | No data leaks between tests |
| Context with custom resolver | Yes | Optional | Accessor, resolver, and converter are configured properly |

Not every expression needs the full matrix. Choose cases matching the properties, variables, and context capabilities that the application actually uses.

## 21. Common mistakes

**Using # for a root object property**

customer.name is a property path from the root. #customer.name is the customer variable in the context.

**Forgetting to put the root object in the context**

If using getValue(context), create the context with the root object or call setRootObject before evaluating.

**Not setting required variables**

The expression references #minimumTotal, but the test did not call setVariable. Provide the variable or explicitly test the behavior when it is missing.

**Confusing #root with #this**

Inside collection operations, #this is the current element; #root remains the original root object.

**Sharing a context across test cases**

Mutable variables and root objects can make results depend on execution order. Create a separate context for each case.

**Only checking selection size**

A collection with the right count but wrong elements can still make the test pass. Check content and order when they are part of the contract.

**Unstubbed mock getters**

Unstubbed properties may return null, false, or zero. Stub all getters used by the expression.

**Assuming parser tests prove the annotation context**

Parser tests verify basic SpEL expressions. If the expression is used in @Value, cache, security, or other modules, integration tests at the exact integration point are needed to verify the root object and variables provided by that module.

## 22. Key takeaways

- The root object provides properties accessed directly by name.
- Variables are referenced with the # prefix and set in the EvaluationContext.
- Use getValue(rootObject, resultType) for expressions needing only a root object.
- Use StandardEvaluationContext(rootObject) when an expression needs both a root object and variables.
- #root keeps a reference to the root object; #this is the current object and changes inside collection operations.
- Test root properties and variables separately, even when they have identical names.
- Use small POJO fixtures for simple objects; use Mockito when interfaces/collaborators need to be mocked.
- Parsing and evaluation are two separate steps; test syntax errors and runtime data errors separately.
- Create a separate context for each test case or evaluation with different data.
- Reuse parsed Expressions, but do not share mutable contexts without control.
- Configure PropertyAccessor, BeanResolver, and TypeConverter when the expression depends on them.
- Test through real annotations/modules if you need to verify the context provided by Spring integration.
