# Testing Expressions with Mock Root Objects in SpEL

## 1. Goal of mocking the root object

Spring Expression Language (SpEL) typically evaluates properties and methods against a root object. In an application, the root object can be an entity, DTO, request model, or business object with multiple nested properties.

When testing expressions, it is not necessary to start the entire Spring context or hit a database to obtain a real object. You can create a small mock/fixture object with deterministic data and pass that object directly into Expression.getValue(...).

Example:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("customer.active");

Order order = new Order(new Customer("Lan", true), 150);

Boolean active = expression.getValue(order, Boolean.class);

assertTrue(active);
~~~

Order is the root object of the evaluation pass. SpEL reads the customer property, then reads active on the returned Customer object. The test only needs an object with the exact structure and data used by the expression.

Mocking the root object keeps tests focused on expression behavior: which properties are read, which conditions evaluate to true, which collection elements are selected, and whether the result type is correct.

## 2. Passing the root object directly to getValue

The getValue(rootObject, expectedResultType) overload is a simple way to evaluate an expression against a root object:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customer.name");

Order order = TestData.orderWithCustomer("Lan");

String name = expression.getValue(order, String.class);

assertEquals("Lan", name);
~~~

Property names in the expression are resolved from the root object. No `#` prefix is needed when reading properties directly on the root object. The `#` prefix is for variables in the evaluation context.

You can use the same Expression with multiple root objects:

~~~java
Expression expression =
        parser.parseExpression("customer.name");

Order firstOrder = TestData.orderWithCustomer("Lan");
Order secondOrder = TestData.orderWithCustomer("Minh");

assertEquals("Lan", expression.getValue(firstOrder, String.class));
assertEquals("Minh", expression.getValue(secondOrder, String.class));
~~~

This approach is useful when one expression is used for multiple objects of the same structure. The parser only needs to parse the source once; each getValue call receives the corresponding root object.

## 3. Creating small POJO fixtures with deterministic data

For most property-access tests, a simple POJO is the most readable and lowest-dependency choice. The fixture only needs to expose getters for the properties accessed by the expression.

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
    private final Customer customer;
    private final int total;

    public Order(Customer customer, int total) {
        this.customer = customer;
        this.total = total;
    }

    public Customer getCustomer() {
        return customer;
    }

    public int getTotal() {
        return total;
    }
}
~~~

Factory methods can be created so tests do not have to repeat long constructors:

~~~java
final class TestData {
    private TestData() {
    }

    static Order orderWithCustomer(String name) {
        return new Order(new Customer(name, true), 150);
    }

    static Order inactiveOrder() {
        return new Order(new Customer("Lan", false), 150);
    }
}
~~~

The fixture should have just enough data to represent the condition under test. There is no need to build the entire domain model if the expression only uses a few properties. If the expression accesses additional properties, add those properties to the fixture with the matching types and getters.

## 4. Testing nested properties

When an expression traverses multiple object levels, the fixture must mimic the exact path structure:

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
    private final Address address;

    public Customer(Address address) {
        this.address = address;
    }

    public Address getAddress() {
        return address;
    }
}

public class Order {
    private final Customer customer;

    public Order(Customer customer) {
        this.customer = customer;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

The expression customer.address.city requires the root object to have a customer property, Customer to have an address property, and Address to have a city property.

~~~java
@Test
void readsNestedPropertyFromRootObject() {
    Order order = new Order(
            new Customer(new Address("Da Nang")));

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer.address.city");

    String city = expression.getValue(order, String.class);

    assertEquals("Da Nang", city);
}
~~~

If a getter is missing or a property name does not match, SpEL cannot resolve the path. Fixtures should reflect the actual property API exposed by real objects rather than adding fake properties just to make the expression run.

## 5. Using StandardEvaluationContext when variables are needed

Some expressions combine root object properties with variables. In that case, create a StandardEvaluationContext and put the root object in the context:

~~~java
Order order = TestData.orderWithCustomer("Lan");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("minimumTotal", 100);

Expression expression =
        new SpelExpressionParser().parseExpression(
                "customer.active and total >= #minimumTotal");

Boolean eligible =
        expression.getValue(context, Boolean.class);

assertTrue(eligible);
~~~

In this expression:

- customer.active and total are read from the root object.
- #minimumTotal is read from the variable in the context.
- The result is a Boolean.

You can swap the root object without changing the expression source by creating a new context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(inactiveOrder);

context.setVariable("minimumTotal", 100);

Boolean eligible = expression.getValue(context, Boolean.class);

assertFalse(eligible);
~~~

When testing, pass variable data via setVariable instead of concatenating values directly into the expression source. This keeps clear which part is syntax and which part is input data.

## 6. Distinguishing #root and #this

In a top-level expression, #root references the root object of the evaluation pass and #this references the current object. Before entering a collection operation, the current object is the root object itself.

~~~java
Order order = TestData.orderWithCustomer("Lan");

Expression rootExpression =
        parser.parseExpression("#root.customer.name");

Expression thisExpression =
        parser.parseExpression("#this.customer.name");

assertEquals("Lan", rootExpression.getValue(order, String.class));
assertEquals("Lan", thisExpression.getValue(order, String.class));
~~~

In collection selection or projection, #this changes with the element being processed, while #root remains the initial root object.

~~~java
public class Item {
    private final String name;
    private final boolean enabled;

    public Item(String name, boolean enabled) {
        this.name = name;
        this.enabled = enabled;
    }

    public String getName() {
        return name;
    }

    public boolean isEnabled() {
        return enabled;
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

You can check both root and the current element in the same predicate:

~~~java
Catalog catalog = new Catalog(
        "Lan",
        List.of(new Item("A", true), new Item("B", false)));

Expression expression = parser.parseExpression(
        "items.?[#root.owner == 'Lan' and #this.enabled]");

List<?> enabledItems = expression.getValue(catalog, List.class);

assertEquals(1, enabledItems.size());
assertEquals("A", ((Item) enabledItems.get(0)).getName());
~~~

This example clarifies both scopes: #root.owner always reads Catalog's owner; #this.enabled reads the enabled property of the current Item.

## 7. Testing selection with a mock root object

Selection filters a collection exposed by the root object. The fixture should include both matching and non-matching elements so the result clearly demonstrates the predicate:

~~~java
@Test
void selectsEnabledItemsFromRootObject() {
    Catalog catalog = new Catalog(
            "Lan",
            List.of(
                    new Item("A", true),
                    new Item("B", false),
                    new Item("C", true)));

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("items.?[enabled]");

    List<?> result = expression.getValue(catalog, List.class);

    assertEquals(2, result.size());
    assertEquals("A", ((Item) result.get(0)).getName());
    assertEquals("C", ((Item) result.get(1)).getName());
}
~~~

The predicate can be written explicitly using #this:

~~~java
Expression expression =
        parser.parseExpression("items.?[#this.enabled]");
~~~

Both ways of writing it evaluate the enabled property of the current element. Use the short form when there is no chance of confusion; use #this when it clarifies the context or when the predicate also references #root.

## 8. Testing projection with a mock root object

Projection creates a new collection from the results of an expression applied to each element:

~~~java
@Test
void projectsItemNamesFromRootObject() {
    Catalog catalog = new Catalog(
            "Lan",
            List.of(
                    new Item("A", true),
                    new Item("B", false)));

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("items.![name]");

    List<?> names = expression.getValue(catalog, List.class);

    assertEquals(List.of("A", "B"), names);
}
~~~

Projection does not filter elements. It produces one result value for each element of the input collection. If you need both filtering and transformation, you can chain selection with projection:

~~~java
Expression expression =
        parser.parseExpression("items.?[enabled].![name]");
~~~

In tests, verify both content and element order if order is part of the collection contract. Using a small fixture makes it immediately clear which elements are retained and which properties are projected.

## 9. Using Mockito when collaborators need mocking

POJO fixtures fit simple data. Mockito is useful when the root object is an interface or collaborator whose behavior needs to be controlled, or when constructing a real object requires many dependencies unrelated to the expression.

Example with interfaces:

~~~java
public interface OrderView {
    CustomerView getCustomer();
    int getTotal();
}

public interface CustomerView {
    String getName();
    boolean isActive();
}
~~~

You can create mocks and stub getters:

~~~java
@Test
void evaluatesExpressionAgainstMockRoot() {
    OrderView order = mock(OrderView.class);
    CustomerView customer = mock(CustomerView.class);

    when(order.getCustomer()).thenReturn(customer);
    when(order.getTotal()).thenReturn(150);
    when(customer.getName()).thenReturn("Lan");
    when(customer.isActive()).thenReturn(true);

    Expression expression = new SpelExpressionParser()
            .parseExpression("customer.active and total >= 100");

    Boolean result = expression.getValue(order, Boolean.class);

    assertTrue(result);
}
~~~

SpEL reads properties via accessors; for a mocked Java interface, stubbed getters supply the values for the corresponding properties. Stub the exact getters that the expression needs to read.

There is no need to use Mockito merely to replace a simple DTO with a straightforward constructor. Real objects or small fixtures usually make tests easier to read because property behavior matches the objects used by the application.

## 10. Testing null and optional properties

Mock root objects should include cases where nested properties can be null if the expression needs to support them.

~~~java
@Test
void returnsDefaultWhenNestedPropertyIsNull() {
    Order order = new Order(null);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer?.name ?: 'Guest'");

    String name = expression.getValue(order, String.class);

    assertEquals("Guest", name);
}
~~~

Here customer?.name returns null when customer is null; the Elvis operator supplies Guest. If the application needs to distinguish a null object from an empty property, create separate fixtures for each state.

Example testing both cases:

~~~java
@Test
void distinguishesNullAndEmptyName() {
    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer?.name ?: 'Guest'");

    Order missingCustomer = new Order(null);
    Order emptyName = new Order(new Customer("", true));

    assertEquals("Guest",
            expression.getValue(missingCustomer, String.class));
    assertEquals("Guest",
            expression.getValue(emptyName, String.class));
}
~~~

Elvis in SpEL handles null and empty strings. If business rules require preserving empty strings or replacing only null, use a `== null` condition instead of Elvis.

## 11. Testing result types and evaluation errors

Whenever possible, request an explicit result type using the getValue(rootObject, TargetType.class) overload:

~~~java
Expression expression =
        new SpelExpressionParser().parseExpression("total >= 100");

Boolean result = expression.getValue(order, Boolean.class);
~~~

This expresses the contract expected by application code. If the expression cannot produce a value convertible to the target type, SpEL will raise an evaluation error.

Parsing an expression and evaluating an expression are two separate operations:

~~~java
ExpressionParser parser = new SpelExpressionParser();

// Parse: check syntax and create Expression.
Expression expression = parser.parseExpression("customer.active");

// Evaluate: read property from root object.
Boolean active = expression.getValue(order, Boolean.class);
~~~

You can test parse errors separately with invalid expression source:

~~~java
assertThrows(
        ParseException.class,
        () -> parser.parseExpression("customer."));
~~~

And test evaluation errors with a root object that does not provide a property required by the expression:

~~~java
Expression expression = parser.parseExpression("unknownProperty");

assertThrows(
        EvaluationException.class,
        () -> expression.getValue(order));
~~~

In real tests, use the exception type appropriate to the Spring API and version in use. The goal is to clearly identify whether an error occurs during parsing or when accessing data at evaluation time.

## 12. Testing the same expression with multiple root objects

If an expression is reused across multiple objects, test multiple different root objects instead of testing only a single case:

~~~java
@ParameterizedTest
@MethodSource("orders")
void evaluatesEachOrder(Order order, boolean expected) {
    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("customer.active and total >= 100");

    Boolean actual = expression.getValue(order, Boolean.class);

    assertEquals(expected, actual);
}

static Stream<Arguments> orders() {
    return Stream.of(
            Arguments.of(
                    new Order(new Customer("Lan", true), 150),
                    true),
            Arguments.of(
                    new Order(new Customer("Minh", false), 150),
                    false),
            Arguments.of(
                    new Order(new Customer("An", true), 50),
                    false));
}
~~~

Each case demonstrates a different reason why the condition evaluates to true or false. When the expression source is the same, it can be parsed once in a field or test setup and then evaluated on each root object.

Testing multiple root objects verifies that the expression does not accidentally depend on one specific fixture and that results vary with input data.

## 13. Common mistakes when mocking root objects

**Missing getter or wrong property name**

The expression customer.name requires the root object to expose customer and the Customer object to expose name. Having a field without allowing an accessor to read it does not guarantee the expression can access it.

**Confusing root properties with variables**

customer.name is a property path from the root object. #customer.name is a customer variable in the evaluation context. If a test only passes a root object without creating a variable, the second expression will not read the root property as intended.

**Confusing #this with #root in collection operations**

In selection/projection, #this is the current element; #root remains the initial root object. Using the wrong one can cause the predicate to read from the wrong object level.

**Mock does not stub required getters**

A mock usually returns default values if a getter has not been stubbed. That can cause the expression to return null, false, or zero, making the test fail to reflect the intended data.

**Overly large fixtures**

Constructing the application's entire object graph makes tests hard to read and maintain. Create only the properties the expression actually uses.

**Checking only collection size**

If selection returns the right number of elements but the wrong elements, an assertion checking only size() can miss the bug. When order and content matter, assert specific values.

**Mixing parse errors with evaluation errors**

Parse the expression once in a separate step and evaluate it on the root object afterward. This shows whether an error stems from syntax or from a fixture failing to satisfy the property path.

## 14. Combined example with JUnit 5

The following example creates a mock root object, evaluates properties, uses #root in selection, and verifies the results:

~~~java
class SpelRootObjectTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void readsRootPropertiesAndFiltersNestedItems() {
        Catalog catalog = new Catalog(
                "Lan",
                List.of(
                        new Item("A", true),
                        new Item("B", false),
                        new Item("C", true)));

        Expression ownerExpression =
                parser.parseExpression("#root.owner");

        Expression enabledExpression =
                parser.parseExpression(
                        "items.?[#root.owner == 'Lan' and #this.enabled]");

        String owner =
                ownerExpression.getValue(catalog, String.class);

        List<?> enabledItems =
                enabledExpression.getValue(catalog, List.class);

        assertEquals("Lan", owner);
        assertEquals(2, enabledItems.size());
        assertEquals("A", ((Item) enabledItems.get(0)).getName());
        assertEquals("C", ((Item) enabledItems.get(1)).getName());
    }
}
~~~

The Catalog and Item fixtures are simple classes with getters for the properties used by the expressions. The test does not need a Spring application context because the parser and root object are enough to evaluate the expressions.

If the expression needs variables, create a StandardEvaluationContext from Catalog, set variables with setVariable, and then call getValue(context, ResultType.class). This tests both data sources without altering the expression source.

## 15. Takeaways

- Pass the root object directly with expression.getValue(rootObject, ResultType.class) when only root properties are needed.
- Use StandardEvaluationContext(rootObject) when the expression also needs variables or evaluation context configuration.
- Create small POJO fixtures with getters and deterministic data for the properties used by the expression.
- Use Mockito when interfaces/collaborators need to be mocked; avoid mocking simple DTOs when real objects are easy to instantiate.
- #root references the initial root object; #this is the current object and changes inside collection operations.
- Test nested properties, collection selection/projection, null cases, and result types according to the contract.
- Separate parsing and evaluation to distinguish syntax errors from runtime data errors.
- Use the same Expression with multiple root objects to test different data branches.
- Assertions should verify content and order when they are part of the expected result, not just count.
