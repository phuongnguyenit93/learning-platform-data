# Auto-Grow Null References and Auto-Grow Collections in SpEL

SpEL can automatically initialize a property that is currently null and automatically expand a collection when an expression accesses an index beyond its current size. These two capabilities are commonly called **auto grow null references** and **auto grow collections**. They make updating an object graph possible with a short expression, yet they can also mutate data during expression evaluation.

This lesson explains how to enable both capabilities in SpelParserConfiguration, how they work together when accessing nested properties inside a List, how to cap growth size, and which cases to avoid.

## 1. Objectives and prerequisites

After this lesson, you will be able to:

- Distinguish auto-initializing null properties from auto-growing collections.
- Configure the two behaviors independently with SpelParserConfiguration.
- Use Expression.setValue(...) to update a property path whose intermediate object is null.
- Grow a List up to a target index and initialize the element if its type can be determined.
- Set a growth limit and anticipate errors when exceeding the limit or lacking type information.
- Recognize side effects, data impact, and risks when evaluating untrusted expressions.

You should be familiar with Java classes, getters/setters, constructors, List, and using SpelExpressionParser to parse an expression. This lesson focuses on parser configuration and evaluation behavior rather than covering all SpEL syntax.

## 2. Two mechanisms solving two different situations

Imagine an object with this structure:

~~~java
class Person {
    private Address address;
    // getters and setters
}

class Address {
    private String city;
    // getters and setters
}
~~~

If person.getAddress() is currently null, the expression address.city cannot proceed through normal property access. Auto grow null references allows SpEL to instantiate the intermediate object when the parser is configured to do so and the target type can be instantiated.

The second situation involves a list:

~~~java
class Order {
    private List<LineItem> items = new ArrayList<>();
    // getters and setters
}
~~~

If items is empty and the expression accesses items[2], index 2 does not exist yet. Auto grow collections allows SpEL to expand the collection so that index can be accessed.

The two behaviors can be enabled independently:

| Configuration | Effect |
|---|---|
| Auto grow null references | Instantiates a null intermediate property when SpEL has enough type information and can create an instance |
| Auto grow collections | Expands a collection accessed by an index beyond its current size, within configured limits |

If the expression is items[2].sku, both capabilities may be needed together: the collection must grow in size to have index 2, and then the element at index 2 must be initialized if it is null so SpEL can access sku.

## 3. Configuring with SpelParserConfiguration

Both behaviors are controlled when creating the parser:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true);

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

The two boolean parameters are, in order:

1. autoGrowNullReferences: enables auto-initializing null references along a property path.
2. autoGrowCollections: enables auto-growing collections when accessing an out-of-bounds index.

You can set a growth size limit using the constructor with a third parameter:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true, 64);

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

In this example, 64 is the auto-grow limit configured for the parser. When an application handles varying input data, set an explicit limit according to your needs rather than letting an expression request an arbitrary size.

The configuration is tied to the parser created from it. If you create another parser with default settings, do not assume that parser shares the same auto-grow behavior. Manage parsers and configurations in a controlled place, and avoid creating parsers with differing privileges arbitrarily.

## 4. Auto grow null references: initializing intermediate properties

### 4.1. How it works

When SpEL traverses a property path that has a null intermediate property, a parser with auto grow null references enabled can attempt to instantiate that property and continue traversing the path.

Example:

~~~java
Person person = new Person(); // address is initially null

ExpressionParser parser =
    new SpelExpressionParser(
        new SpelParserConfiguration(true, false));

Expression expression = parser.parseExpression("address.city");
expression.setValue(person, "Ha Noi");
~~~

After successful evaluation, the object graph can look like:

~~~text
person
  └── address
        └── city = "Ha Noi"
~~~

SpEL needs to determine the property's type in order to create an appropriate object. Therefore, classes and properties should provide sufficiently clear type metadata. Concrete types with an appropriate constructor are usually easier to instantiate than interfaces, abstract classes, or uninstantiable types. If the intermediate object cannot be created, the expression cannot complete the path on its own.

### 4.2. Conditions to check

- The property path must pass through a property that SpEL can recognize.
- The type of the null property must be determinable.
- That type must be instantiable in the runtime environment.
- The property accessor must have the required access rights; for regular JavaBeans, provide matching getters/setters.
- If there are multiple null levels, each level must be instantiable for SpEL to proceed.

Auto grow does not fix every kind of data error automatically. It cannot infer an arbitrary implementation for an interface, cannot construct an object whose constructor requires arguments without a mechanism to supply them, and does not replace business validation.

## 5. Auto grow collections: expanding by index

### 5.1. How it works

For index-accessed collections, auto grow collections lets SpEL expand the collection when the requested index lies outside the current size.

For example, if items is an empty List, accessing index 2 requires the collection to have enough slots up to that index. The newly added slots may contain null until another expression assigns a value or auto grow null references instantiates the accessed element.

~~~java
Order order = new Order(); // items is an empty List

ExpressionParser parser =
    new SpelExpressionParser(
        new SpelParserConfiguration(false, true, 64));

Expression expression = parser.parseExpression("items[2]");
expression.setValue(order, new LineItem());
~~~

After the operation, the List can hold three positions: index 0, index 1, and index 2. The new element is assigned at index 2; the preceding positions were added to satisfy the index.

### 5.2. Combining with auto grow null references

A more realistic example is updating a property of an element at an index that does not yet exist:

~~~java
class LineItem {
    private String sku;

    public LineItem() {
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }
}

class Order {
    private List<LineItem> items = new ArrayList<>();

    public List<LineItem> getItems() {
        return items;
    }

    public void setItems(List<LineItem> items) {
        this.items = items;
    }
}
~~~

Configuration and evaluation:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true, 64);

ExpressionParser parser =
    new SpelExpressionParser(configuration);

Order order = new Order();

Expression expression =
    parser.parseExpression("items[2].sku");

expression.setValue(order, "SKU-003");
~~~

For the expression to complete, SpEL needs to handle two steps: expand the List to have index 2, then instantiate the element at that index if it is null and its element type can be determined. Generic type metadata such as List<LineItem> helps SpEL know what element type to create. If a raw collection is used or the element is declared with an overly generic type, SpEL may lack sufficient information to auto-initialize nested elements.

### 5.3. Which collections are suitable?

Auto grow makes the most sense for index-accessed structures such as List. A Map is accessed by key and has no concept of a list end index to auto-expand; the absence of a key does not mean SpEL will auto-create a value of a desired type. A Set also provides no index to expand in this manner.

With arrays, a Java array's size is fixed. If a use case needs to add elements frequently, List is usually a clearer and more suitable choice. Do not assume every collection type can auto-grow in the same way; check your application's actual property types and accessors.

## 6. How the two options work together

The following table describes typical outcomes when an expression needs to access items[2].sku and the List is initially empty:

| Auto grow null references | Auto grow collections | Behavior |
|---|---|---|
| Off | Off | Does not auto-create slots or objects; out-of-bounds index access fails |
| On | Off | Cannot reach a nonexistent index; enabling null initialization does not replace growing the List |
| Off | On | The List can grow, but the null element at index 2 is not auto-initialized to access sku |
| On | On | The List can grow and the null element can be initialized if SpEL can determine the element type |

These are two independent flags. Enabling one flag does not automatically enable the other.

## 7. Size limits and memory impact

Auto grow collections can increase data size solely because an expression accesses a large index. If the index comes from external data, a very large value can cause the application to allocate many elements or consume unnecessary resources.

Set an appropriate maximumAutoGrowSize:

~~~java
int maximumSize = 64;

SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, true, maximumSize);
~~~

This limit helps block growth requests that exceed what the application permits. When the requested index or size exceeds the limit, evaluation may throw an exception. The application should handle that error as invalid input or a business limit violation, depending on the expression source.

Do not use the size limit as a substitute for validation. If business rules allow at most 10 order lines, validate the limit of 10 at the business layer; the parser cap is an additional safeguard for auto-grow behavior.

## 8. Auto grow can mutate object state

An important point is that auto grow is a behavior with side effects. When evaluating a property path, SpEL may instantiate objects or expand collections to continue traversing. Therefore, do not assume every getValue call only reads data and leaves the object graph unchanged when the parser has auto-grow enabled.

Consider the following:

- Use dedicated objects for binding or update operations rather than sharing mutable objects across multiple requests.
- Avoid evaluating expressions with auto-grow on singleton objects or objects concurrently used by multiple threads.
- Clearly define when an object is allowed to change and who is responsible for persisting those changes.
- If you only need to check conditions, use fully initialized data and keep auto-grow disabled if unnecessary.
- Test object state before and after evaluation to detect unexpected mutations.

## 9. Safety when evaluating expressions

Auto grow is not a sandboxing mechanism. It only controls certain object creation and collection expansion behaviors. Other capabilities such as calling methods, referencing types, invoking constructors, or accessing beans depend on EvaluationContext and the configured resolvers.

Do not accept an arbitrary SpEL string from a request and evaluate it with a broadly privileged context. If users can define conditions, restrict the grammar, root object, properties, data types, expression length, and collection sizes. Prefer read-only contexts, small DTOs, and an allowlist of usable fields.

When enabling auto grow:

1. Allow updates only on objects with known structures and types.
2. Set a growth limit suited to business data.
3. Avoid passing services or large entity graphs as the root object.
4. Do not register powerful bean resolvers, type locators, or method resolvers unless required by the use case.
5. Check results and handle exceptions at application boundaries.
6. Do not log sensitive data or full untrusted inputs.

## 10. Testing auto grow behavior

There should be independent tests for each flag and an integration test for the combined case:

| Case | What to verify |
|---|---|
| Intermediate property is null, auto grow null on | The property path can instantiate the object when the target type is instantiable |
| Intermediate property is null, auto grow null off | No object is auto-created; access fails according to context |
| Index exceeds size, auto grow collection on | The collection grows enough to access the index within limits |
| Index exceeds configured limit | Evaluation is rejected with an exception |
| Element at new index is null, only auto grow collection on | The slot may exist, yet accessing a property on the element still fails |
| Both flags on with concrete generic element type | The collection expands and the element can be initialized to update the property |
| Element type cannot be instantiated | Auto grow null reference cannot instantiate an appropriate element |
| Repeated evaluation on the same object | Verify no unexpected additional mutations are produced |

A test should verify both the expression result and the object state after evaluation. For example, after assigning items[2].sku, confirm that the List has size 3, the element at index 2 exists, and the sku value is correct. For error tests, confirm the expected exception and that the object was not mutated unexpectedly.

## 11. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Path still fails when property is null | Auto grow null references is not enabled or target type cannot be instantiated | Check parser configuration, type metadata, and constructor |
| Out-of-bounds index still fails | Auto grow collections is not enabled or exceeds limit | Check the second flag and maximum auto grow size |
| List grew, yet accessing .property fails | Element at index is still null | Enable auto grow null references and ensure element type can be determined |
| Cannot instantiate generic element | Collection is declared raw or element type is unclear | Declare a concrete generic type such as List<LineItem> |
| Expression mutates object unexpectedly | Auto grow produces side effects during evaluation | Disable auto grow on read-only paths or use a dedicated object |
| Configuration has no effect | Using a different parser than the configured one | Check where the parser is created and where the expression is parsed |

When investigating, check in order the actual parser instance, the two configuration flags, the accessed index, the size limit, the property type, and the element type. Do not simply raise limits or add permissions before identifying the cause.

## 12. Practice roadmap

1. Create a Person class with an Address property that starts as null. Use a parser with only auto grow null references enabled and assign address.city.
2. Create an Order class with an empty List<LineItem>. Enable only auto grow collections and assign an element at index 2.
3. Combine both flags to assign items[2].sku, observing the created object and List size.
4. Try disabling each flag individually to see at which step errors appear.
5. Set a small limit and test indices both within and beyond the limit.
6. Write tests for non-instantiable properties, raw-type collections, nulls, and repeated evaluation.
7. Create a read-only context for a condition-checking use case and compare it with an update flow that uses auto-grow.

## 13. Application usage checklist

- [ ] Have you clearly identified which property paths need auto-initialization?
- [ ] Have you identified which collections are allowed to auto-expand?
- [ ] Are the two auto grow flags enabled strictly according to need?
- [ ] Do property types and generic element types provide enough information?
- [ ] Can the classes needing instantiation be instantiated at runtime?
- [ ] Is an appropriate maximum auto grow size set?
- [ ] Have side effects on the object graph been identified?
- [ ] Are untrusted expressions prevented from being evaluated with a high-privilege context?
- [ ] Have both the result and the object state after evaluation been tested?
- [ ] Are exceptions and business limits handled at the application layer?

## 14. Conclusion

Auto grow null references and auto grow collections solve two separate problems: creating null intermediate objects and expanding collections to satisfy an index. When an expression traverses deeply like items[2].sku, the two capabilities may need to work together. Configure them explicitly on the parser, ensure instantiable data types, set growth limits, and treat every auto-grow operation as a state mutation that must be controlled.