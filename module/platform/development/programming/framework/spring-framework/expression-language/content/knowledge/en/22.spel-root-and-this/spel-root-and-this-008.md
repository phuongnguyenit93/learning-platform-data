# Designing Small Goal-Focused Root Objects in Spring Expression Language

In Spring Expression Language (SpEL), the root object is the default object on which an expression reads properties and invokes methods when names are written without a variable prefix. Therefore, the object chosen as root determines what data and behavior an expression can see from the outset.

When designing an application that uses SpEL, create a root object scoped just right for the expression's goal. If an expression only needs to filter orders by total amount and status, the root object should provide the list of orders along with the comparison threshold. There is no need to put the entire ApplicationContext, repositories, entity graphs, or unrelated services into the evaluation environment.

A small root object makes expressions easier to read, clarifies input data, reduces coupling to the application's internal structure, and limits which properties or methods an expression can access.

## 1. The root object is the starting point of an expression

When creating a StandardEvaluationContext with an object, that object becomes the root object:

~~~java
Order order = new Order(
    "ORD-100",
    new BigDecimal("750000"),
    "PAID"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

With this context, an expression can read properties directly:

~~~spel
total
status
orderNumber
~~~

Property names without the `#` prefix are looked up on the current object. At the outermost level, the initial current object is the root object itself.

You can explicitly reference the root object with `#root`:

~~~spel
#root.total
#root.status
~~~

Thus, if the root object is Order, both `total` and `#root.total` refer to the root object's `total` property in this simple context.

## 2. Root object differs from variables in EvaluationContext

The root object is the primary object of the evaluation pass. Variables are supplementary data registered separately in EvaluationContext.

Example:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

Expression:

~~~spel
total >= #minimum
~~~

reads total from the root object and minimum from a variable in the context.

You can use `#root` to clarify the data source:

~~~spel
#root.total >= #minimum
~~~

This separation is useful when designing inputs for expressions:

- The root object holds the primary data the expression operates on.
- Variables hold auxiliary values, parameters, or thresholds supplied separately.
- There is no need to turn every property into a variable if it already belongs to the primary object.

If an expression has several closely related values that are always passed together, consider grouping them into a dedicated root object instead of registering too many scattered variables.

## 3. Why design a small root object?

A large root object can make expressions depend on many parts of the application model. When an entity or service changes, expressions may also have to change accordingly.

A small root object provides these benefits:

1. **Clarifies inputs:** looking at the root class reveals which data the expression is allowed to use.
2. **Reduces coupling:** expressions do not need to know the entire domain or service layer structure.
3. **Easy to test:** small input objects can be constructed with deterministic data for each test case.
4. **Reduces unintended side effects:** expressions have fewer opportunities to access state-mutating methods or invoke unrelated components.
5. **Stabilizes the contract:** internal changes to an entity do not necessarily change the input class dedicated to SpEL.
6. **Easy to reuse:** the same input type can serve multiple expressions with similar goals.

The goal is not to create one class per expression. Group data that genuinely belongs to the same evaluation goal into a clear input type.

## 4. Designing a root object for a specific goal

Suppose an application needs to select orders whose total meets a minimum threshold. The expression needs:

- The list of orders.
- The total amount of each order.
- The minimum threshold.

Small input classes can be created:

~~~java
public class OrderSummary {
    private final String orderNumber;
    private final BigDecimal total;

    public OrderSummary(
            String orderNumber,
            BigDecimal total) {
        this.orderNumber = orderNumber;
        this.total = total;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

public class OrderSelectionInput {
    private final List<OrderSummary> orders;
    private final BigDecimal minimum;

    public OrderSelectionInput(
            List<OrderSummary> orders,
            BigDecimal minimum) {
        this.orders = orders;
        this.minimum = minimum;
    }

    public List<OrderSummary> getOrders() {
        return orders;
    }

    public BigDecimal getMinimum() {
        return minimum;
    }
}
~~~

The root object contains only the data needed for the order-filtering goal. It does not need to hold the entire Order entity, Customer, PaymentService, or Repository if the expression does not use them.

Create data and evaluate:

~~~java
List<OrderSummary> orders = Arrays.asList(
    new OrderSummary("ORD-100", new BigDecimal("750000")),
    new OrderSummary("ORD-101", new BigDecimal("250000")),
    new OrderSummary("ORD-102", new BigDecimal("1200000"))
);

OrderSelectionInput input =
    new OrderSelectionInput(
        orders,
        new BigDecimal("500000")
    );

StandardEvaluationContext context =
    new StandardEvaluationContext(input);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "orders.?[#this.total >= #root.minimum]"
);

Object result = expression.getValue(context);
~~~

The result is a collection containing ORD-100 and ORD-102.

In this example:

- orders is read on the root object.
- #root.minimum retrieves the threshold from the initial root object.
- #this.total retrieves the total of the element currently being checked by selection.
- The result is the orders meeting the condition.

## 5. Distinguishing #root and #this when processing collections

These two references are especially important when an expression enters selection or projection.

- **#root:** always references the root object of the entire evaluation pass.
- **#this:** references the object currently being evaluated at the current position; in selection or projection, it is usually the collection element currently being processed.

With the expression:

~~~spel
orders.?[#this.total >= #root.minimum]
~~~

you can picture it as:

~~~text
Root: OrderSelectionInput
  |
  +-- minimum = 500000
  |
  +-- orders
        |
        +-- OrderSummary 1  <-- #this on iteration 1
        +-- OrderSummary 2  <-- #this on iteration 2
        +-- OrderSummary 3  <-- #this on iteration 3
~~~

On each iteration:

- #this changes with the OrderSummary currently being examined.
- #root remains the initial OrderSelectionInput.
- #root.minimum always reads the same minimum threshold.

If you mistakenly write #this.minimum in the predicate, SpEL will look for minimum on the current OrderSummary. If OrderSummary lacks that property, the expression will not behave as expected.

## 6. Putting primary data in root and auxiliary data in variables

You do not always need to create a new class to hold every value. If an expression has one primary object and only a few independent parameters, you can keep that object as root and register the rest as variables.

~~~java
Order order = new Order(
    "ORD-100",
    new BigDecimal("750000"),
    "PAID"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

context.setVariable("requiredStatus", "PAID");
~~~

Expression:

~~~spel
total >= #minimum && status == #requiredStatus
~~~

This design fits when:

- Order is the primary object of the rule.
- minimum and requiredStatus are parameters of the evaluation pass.
- The parameters do not need to become part of the Order model.

If a group of parameters always travels together and carries its own business meaning, consider grouping them into an input object so the expression has a clearer contract.

## 7. Using a dedicated root object instead of passing the entire entity

An entity in an application can contain many associations and behaviors:

~~~text
Order
  |
  +-- Customer
  |     +-- Address
  |     +-- Preferences
  |     +-- Contacts
  |
  +-- Payments
  +-- Shipments
  +-- Audit history
  +-- Internal operations
~~~

If an expression only needs order number, total amount, and status, supplying the entire entity graph as the root object can expose many unnecessary access paths.

Instead, create a projection/input object:

~~~java
public class OrderRuleInput {
    private final String orderNumber;
    private final BigDecimal total;
    private final String status;

    public OrderRuleInput(
            String orderNumber,
            BigDecimal total,
            String status) {
        this.orderNumber = orderNumber;
        this.total = total;
        this.status = status;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }
}
~~~

The application transfers the required data from the entity into the input object before evaluation.

The expression sees only the three supplied properties. Changes in Customer, Payments, or Audit history do not affect the expression as long as the input properties stay intact.

## 8. Keeping the root object's access surface stable

Expressions typically access properties via getters and can call methods if EvaluationContext permits. Therefore, the root class should have a predictable access surface.

Prefer:

- Meaningful getters with stable names.
- Properties with well-defined types.
- Child objects containing only needed properties.
- Pure read methods if the expression needs to call methods.
- Immutable input data throughout an evaluation pass if possible.

Avoid putting methods with side effects on the root, such as mutating state, writing to the database, sending notifications, or changing configuration. If the expression only needs data, a read-only DTO is usually the right choice.

Getters should also avoid mutating state. Technically a getter can execute arbitrary logic, but getters with side effects make expression results harder to predict when evaluated multiple times.

## 9. The root object does not need to hold services or ApplicationContext

A design pattern that easily creates coupling is passing an object that can access nearly the entire application as the root, such as a large facade or ApplicationContext.

When that happens, an expression can accidentally depend on:

- Services unrelated to the goal.
- Repositories and persistence data.
- Beans capable of mutating state.
- Configuration or infrastructure components.
- Child objects with broad API surfaces.

If an expression needs a specific calculation, consider computing it beforehand in Java and passing the result in the root or a variable. If a behavior is genuinely needed, supply a small helper with only the needed methods and configure an appropriate MethodResolver.

Bean references via `@` are also a separate mechanism. Do not put ApplicationContext into the root just so expressions can look up arbitrary beans.

## 10. Root object and EvaluationContext can be configured separately

The root object can be set right when creating the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(input);
~~~

Or updated afterward:

~~~java
context.setRootObject(input);
~~~

In addition, some Expression overloads let you pass the root object directly during evaluation:

~~~java
String result =
    expression.getValue(
        context,
        input,
        String.class
    );
~~~

Passing the root directly is useful when the same Expression is used with multiple input objects.

Choose one consistent approach within each processing flow. If the context already contains a root object but a getValue call passes a different root object, the root passed into that overload is the object used for that evaluation pass.

## 11. Reusing an Expression with multiple root objects

A parsed Expression can be reused with different root objects as long as they satisfy the same property contract required by the expression.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

Order firstOrder = new Order(
    "ORD-100",
    new BigDecimal("750000"),
    "PAID"
);

Order secondOrder = new Order(
    "ORD-101",
    new BigDecimal("250000"),
    "PENDING"
);

Boolean firstResult =
    expression.getValue(
        context,
        firstOrder,
        Boolean.class
    );

Boolean secondResult =
    expression.getValue(
        context,
        secondOrder,
        Boolean.class
    );
~~~

The results are true and false, respectively.

Both root objects must provide the total property. If an object fails to satisfy this contract, evaluation may fail.

In concurrent processing, avoid sharing a context with mutable variables across independent requests. Expressions can be reused, whereas contexts and input data should be managed according to the appropriate unit of work.

## 12. Designing root objects by expression type

Some examples to help determine what data should live in the root:

| Expression goal | Root object should provide | Variables that can be used |
|---|---|---|
| Checking a single order | total, status, orderNumber | minimum, requiredStatus |
| Filtering an order list | orders and filter parameters | time range or threshold |
| Calculating shipping fee | weight, destination, serviceLevel | rate or applicable configuration |
| Building a product label | name, price, availability | locale or currency |
| Checking membership eligibility | membershipLevel, points, active | requiredLevel, minimumPoints |

There is no single root object structure right for every application. Start from the properties the expression actually needs, then create an input object whose name and type express that goal directly.

## 13. Controlling access scope during expression evaluation

The root object is part of the access surface visible to the expression. Therefore, designing a small root also helps restrict what an expression can operate on.

Some options:

- Pass only a DTO containing the data that needs to be read.
- Avoid supplying entities with broad associations if the expression does not need them.
- Avoid passing services or containers as root.
- Register variables with clear types and scopes.
- Use a restricted context if only data binding is needed.
- Configure PropertyAccessor and MethodResolver according to required capabilities.
- Do not let untrusted expressions arbitrarily call side-effecting methods.

A small root object does not by itself create a security sandbox. Expressions can still access other variables, beans, or methods if the context provides those mechanisms. The safety boundary depends on the entire EvaluationContext and all objects supplied to it.

## 14. Complete example: small root object for a selection rule

Suppose an application needs to check whether a product is eligible for display. The rule only needs name, price, stock availability status, and a price threshold.

~~~java
public class ProductRuleInput {
    private final String name;
    private final BigDecimal price;
    private final boolean available;

    public ProductRuleInput(
            String name,
            BigDecimal price,
            boolean available) {
        this.name = name;
        this.price = price;
        this.available = available;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isAvailable() {
        return available;
    }
}
~~~

Create the root object and evaluate:

~~~java
ProductRuleInput input =
    new ProductRuleInput(
        "Keyboard",
        new BigDecimal("750000"),
        true
    );

StandardEvaluationContext context =
    new StandardEvaluationContext(input);

context.setVariable(
    "maximumPrice",
    new BigDecimal("1000000")
);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "available && price <= #maximumPrice"
);

Boolean visible =
    expression.getValue(context, Boolean.class);

Expression labelExpression =
    parser.parseExpression("name.toUpperCase()");

String label =
    labelExpression.getValue(context, String.class);
~~~

Result:

~~~text
visible = true
label = KEYBOARD
~~~

The root object provides only the three properties needed for the rule. The maximumPrice threshold is passed separately as a variable. The expression does not need to access the Product entity, repository, or service.

## 15. Common misconceptions

**Misconception 1: The root object must be the application's main entity.**  
The root object only needs to be an object suited to the expression's goal. A small DTO or input object is often sufficient.

**Misconception 2: Every piece of data must be registered as a variable.**  
Properties of the root object can be accessed directly. Variables fit supplementary parameters or independent values.

**Misconception 3: #this is always the same as #root.**  
At the outermost level they usually point to the same root object. In selection and projection, #this switches to the element being processed, while #root keeps the initial object.

**Misconception 4: Passing a large object makes expressions more flexible at no cost.**  
Large objects can make expressions depend on many unrelated properties and methods, making the contract hard to understand and widening the access scope.

**Misconception 5: A small root object automatically guarantees safety.**  
Variables, BeanResolver, MethodResolver, and PropertyAccessor still affect what an expression can access.

**Misconception 6: Each evaluation requires re-parsing the expression.**  
A parsed Expression can be reused with multiple root objects that satisfy the same data contract.

## 16. Takeaways

- The root object is the default object for SpEL to look up properties and invoke methods without a variable prefix.
- Root can be set via the StandardEvaluationContext constructor, setRootObject, or a getValue overload that accepts a root object.
- #root retains a reference to the root object of the evaluation pass.
- #this is the current object and can change in selection or projection.
- Root object properties are usually written directly; variables are registered with setVariable and referenced with #name.
- Design a small input object with clear properties and data types tailored to the expression's goal.
- DTOs or projection objects help decouple expressions from unnecessary entity graphs and service layers.
- Keep getters simple and stable, and prefer read-only data when expressions only query values.
- A small root object limits the data surface, but the entire EvaluationContext must be configured to control access.
- An Expression can be reused with multiple root objects that satisfy the same property contract.

When designing a root object for SpEL, start by asking what the expression needs to read or compute. Then put only the relevant properties and data into the input object, place supplementary parameters in variables where appropriate, and keep #root and #this clear in expressions that process collections.
