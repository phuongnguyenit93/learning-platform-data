# Indexers on Objects with Corresponding Accessors

## Objectives

SpEL uses the square-bracket index operator to access elements of many data structures. In addition to arrays, Lists, Collections, Strings, and Maps, SpEL also supports reading a property of an object by placing the property name inside square brackets. Starting from Spring Framework 6.2, applications can also register an IndexAccessor to define how a custom structure that does not implement java.util.Map is indexed.

This lesson focuses on how to choose the right accessor for an object, how to register an IndexAccessor, and how to read or write data using indexer syntax.

After this lesson, you will be able to:

- Use square-bracket syntax to access a property of an object.
- Distinguish object indexing from Map indexing and dot-notation property navigation.
- Understand the roles of IndexAccessor and PropertyAccessor.
- Register a ReflectiveIndexAccessor for a custom structure.
- Determine when to implement a custom IndexAccessor or CompilableIndexAccessor.
- Handle null values, incompatible index types, and read/write errors.

## 1. Overview of the Index Operator

General syntax:

~~~text
target[index]
~~~

The meaning of index depends on the target type:

| Target | Meaning of index | Example |
|---|---|---|
| Array | Element position, starting from 0 | **items[0]** |
| List or Collection | Element position, starting from 0 | **members[1]** |
| String | Character position, result is a String | **name[0]** |
| Map | Key used to retrieve the value | **settings['theme']** |
| Object | Name of the property to read | **#root['name']** |
| Custom structure | Index value handled by a registered IndexAccessor | **#fruitMap[T(example.Color).RED]** |

SpEL selects the indexing mechanism based on the target type and the corresponding accessors in the EvaluationContext. Therefore, the same square-bracket syntax does not always have the same meaning.

Numeric indices in arrays, Lists, Collections, and Strings are zero-based. The first element or first character has index 0.

## 2. Indexing into an Object's Property

For a regular object, you can retrieve a property by putting the property name inside square brackets:

~~~text
#root['name']
~~~

Java example:

~~~java
Inventor tesla = new Inventor("Nikola Tesla");

String name = parser.parseExpression("#root['name']")
    .getValue(context, tesla, String.class);
~~~

The result is the inventor's name. This syntax is similar to retrieving a value from a Map by key, but the target here is an object and the string inside square brackets is a property name.

If the property name is accessible through a PropertyAccessor of the EvaluationContext, SpEL can read it. Therefore, object indexing by property name still depends on the context's property-reading capability.

### Comparison with Dot Notation

The following two approaches usually access the same property:

~~~text
#root.name
#root['name']
~~~

Dot notation is suitable when the property name is known and fixed. Square brackets are useful when you want to express the property as an index or when the property name is computed dynamically from a variable:

~~~text
#root[#propertyName]
~~~

In this example, propertyName must evaluate to a String containing the name of the property to read. If the variable has not been provided, has an incompatible type, or the property name is not supported by the accessor, the expression can fail.

Do not confuse object indexing with Map indexing. If the target is actually a Map, the expression **settings['theme']** looks up the key theme in the Map. If the target is a Java object, the expression **#root['name']** asks the accessor to read the name property on that object.

## 3. PropertyAccessor and IndexAccessor

The two accessor types have different purposes:

| Component | Typical Syntax | Responsibility |
|---|---|---|
| PropertyAccessor | **customer.name** | Reads or writes a named property on an object |
| IndexAccessor | **customer[index]** | Reads or writes an element at an index on a structure |
| Map indexing | **settings['theme']** | Gets a value by Map key |
| Object indexing | **#root['name']** | Gets an object property by String name |

PropertyAccessor receives the property name as a String. IndexAccessor receives the index as an Object, because an index can be a number, an enum, or another custom type.

For object indexing where the index is a String property name, SpEL can use the corresponding PropertyAccessor mechanism to read the property. For a custom structure with its own indexing rules, the application needs to register an appropriate IndexAccessor.

You should not implement an IndexAccessor merely to replace a PropertyAccessor that can already read ordinary properties. Choose the accessor type according to the semantics of the data the expression needs to access.

## 4. Indexing into a Custom Structure

Some classes behave like a Map or lookup table without implementing java.util.Map. For example, a class might accept an enum as a key and return a corresponding value:

~~~java
public enum Color {
    RED, ORANGE, YELLOW
}

public class FruitMap {
    private final Map<Color, String> map = new HashMap<>();

    public FruitMap() {
        this.map.put(Color.RED, "cherry");
        this.map.put(Color.ORANGE, "orange");
        this.map.put(Color.YELLOW, "banana");
    }

    public String getFruit(Color color) {
        return this.map.get(color);
    }

    public void setFruit(Color color, String fruit) {
        this.map.put(color, fruit);
    }
}
~~~

FruitMap can look up by Color, but it does not implement Map. SpEL does not automatically infer that Color is the index and getFruit is the read method. Starting from Spring Framework 6.2, you can register an IndexAccessor to describe that indexing contract.

Once the accessor is registered, expressions can use the syntax:

~~~text
#fruitMap[T(example.Color).RED]
~~~

The expression uses the RED enum as the index and retrieves the corresponding value from FruitMap.

## 5. Using ReflectiveIndexAccessor

Spring provides ReflectiveIndexAccessor to handle common custom structures without having to write a custom IndexAccessor class yourself.

The three-argument constructor creates a read-only accessor:

~~~java
new ReflectiveIndexAccessor(
    FruitMap.class,
    Color.class,
    "getFruit"
)
~~~

The parameters are, in order:

1. **targetType:** the type of the object being indexed, here FruitMap.
2. **indexType:** the type of the index, here Color.
3. **readMethodName:** the name of the public method used for reading, here getFruit.

To support writing as well, use the constructor that takes an additional write method name:

~~~java
new ReflectiveIndexAccessor(
    FruitMap.class,
    Color.class,
    "getFruit",
    "setFruit"
)
~~~

The read method takes one argument of type Color and returns a String. The write method takes the same Color index along with a String value. The value type of the write method must match the return type of the read method according to ReflectiveIndexAccessor's convention.

The read/write methods must be public. If SpEL compilation is enabled for read expressions, the configured method also needs to be invocable through a public class or public interface.

### Registering the Accessor and Reading an Index

Full example:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();

IndexAccessor fruitMapAccessor = new ReflectiveIndexAccessor(
    FruitMap.class,
    Color.class,
    "getFruit",
    "setFruit"
);

context.addIndexAccessor(fruitMapAccessor);
context.setVariable("fruitMap", new FruitMap());

String fruit = parser
    .parseExpression("#fruitMap[T(example.Color).RED]")
    .getValue(context, String.class);
~~~

The result is **cherry**.

The crucial point is that the accessor must be registered on the exact EvaluationContext used during evaluation. Simply creating a ReflectiveIndexAccessor instance without adding it to the context means SpEL cannot use that accessor.

### Writing an Index

Because the example registered a read-write accessor, you can assign a value through an expression:

~~~java
parser.parseExpression(
    "#fruitMap[T(example.Color).RED] = 'strawberry'"
).getValue(context);

String updatedFruit = parser
    .parseExpression("#fruitMap[T(example.Color).RED]")
    .getValue(context, String.class);
~~~

After the assignment, the value read back for Color.RED is strawberry.

If only reading is needed, use the three-argument constructor. Do not expose a write method if the business logic does not need to modify the data structure.

## 6. Implementing a Custom IndexAccessor

When a structure does not have read/write methods following the convention required by ReflectiveIndexAccessor, you can implement the IndexAccessor interface yourself.

This interface defines four main operations:

| Method | Responsibility |
|---|---|
| **canRead(context, target, index)** | Determines whether the accessor can read this index on this target |
| **read(context, target, index)** | Reads the value and returns a TypedValue |
| **canWrite(context, target, index)** | Determines whether the accessor can write this index |
| **write(context, target, index, newValue)** | Writes a new value to the index |

IndexAccessor also extends TargetedAccessor. The getSpecificTargetClasses() method allows declaring the target types supported by the accessor. Accessors that specify explicit target classes are tried before generic accessors.

Execution flow:

1. SpEL supplies the EvaluationContext, target object, and index.
2. The accessor is queried via canRead or canWrite.
3. If the accessor confirms it can perform the operation, SpEL calls read or write with the same arguments.
4. read returns a TypedValue to preserve both the value and type information.
5. If no accessor supports the operation, SpEL reports the corresponding indexing error.

A very important contract: read should only be called after canRead returns true for the same target and index. Likewise, write should only be called after canWrite returns true.

When implementing a custom accessor, clearly define:

- Supported target types.
- Accepted index types.
- Behavior when the index does not exist.
- Type of value returned.
- Read and write behavior when data is null.
- How errors are reported when the structure does not allow the operation.
- Whether write access is supported.

If the accessor only supports certain classes, declare specific target classes. Avoid a generic accessor that accepts every object and then checks too many cases on every evaluation.

## 7. IndexAccessor and Compilation Capability

SpEL can compile certain expressions into bytecode to optimize evaluation. A custom IndexAccessor that only implements the IndexAccessor interface does not automatically provide the information needed for compilation.

If compilation support is desired, the accessor must additionally implement CompilableIndexAccessor and provide bytecode generation according to that SPI.

ReflectiveIndexAccessor already implements CompilableIndexAccessor and supports compilation for read access when eligible. However, the configured read method must be invocable through a public class or public interface for compilation to succeed.

Do not enable compilation just because an accessor supports it. Benchmark performance with real expressions and models, and test both interpreted mode and compiled mode if the application uses both.

## 8. Safe Indexing and Null Objects

Starting from Spring Framework 6.2, SpEL supports null-safe indexing with the **?.[ ]** syntax:

~~~text
#fruitMap?.[T(example.Color).RED]
~~~

If fruitMap is null, the expression returns null instead of attempting to perform an indexing operation on null. If fruitMap has a value, SpEL proceeds to find a matching IndexAccessor and read the index normally.

Null-safe indexing supports arrays, collections, strings, maps, objects, and custom structures.

Two conditions must be distinguished:

- **Null target:** safe indexing can return null.
- **Invalid index or accessor:** safe indexing cannot fix a wrong index type, an accessor that does not support the target, or an error inside the read method.

For example, if FruitMap exists but the passed index is not a Color as required by the accessor, the operation can still fail. Safe indexing only protects against a null target; it does not bypass the accessor's contract.

For Spring Framework versions prior to 6.2, this null-safe indexing syntax is not yet supported. Verify the framework version before using it in expressions.

## 9. Common Errors

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Indexing not supported on target | No matching IndexAccessor or target is not of a supported type | Check the target class and register the accessor |
| Accessor does not accept index | Index has a different type from indexType | Check the index expression and data type |
| Error reading index | Read method or accessor logic throws an error | Check the public read method, data, and exception message |
| Error writing index | No write method or incompatible write method | Use a read-write accessor and check the method signature |
| Accessor works in one context but not another | Accessor is not registered in the context being used | Check the factory creating the EvaluationContext |
| Expression returns null | Target is null and safe indexing is used, or the indexed entry has no value | Distinguish a null target from a non-existent index |
| Compilation fails | Accessor is not compilable or read method is not callable via a public type | Use CompilableIndexAccessor and check visibility |
| Indexer handles the wrong structure | Generic accessor accepts too many targets | Declare specific target classes and narrow canRead |

When diagnosing, record the expression, target class, index class, read/write operation type, and the accessor used. There is no need to log the entire object content if it contains sensitive data.

## 10. Testing an IndexAccessor

For custom indexing, tests should verify both that the accessor is selected and the returned value.

Cases to include:

- Target of a supported type and a valid index.
- Target of the right type but index of the wrong type.
- Valid index with no corresponding value.
- Null target with regular expression and null-safe expression.
- Read-only accessor and an attempt to write.
- Read-write accessor and value after updating.
- Multiple accessors coexisting in one context.
- Expression evaluated in an equivalent production context.
- Compilation if the application enables the SpEL compiler.

Example test for reading and writing with FruitMap:

~~~java
@Test
void indexesCustomFruitMap() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context = new StandardEvaluationContext();

    context.addIndexAccessor(new ReflectiveIndexAccessor(
        FruitMap.class, Color.class, "getFruit", "setFruit"));

    context.setVariable("fruitMap", new FruitMap());

    Expression read = parser.parseExpression(
        "#fruitMap[T(example.Color).RED]");

    assertEquals("cherry", read.getValue(context, String.class));

    parser.parseExpression(
        "#fruitMap[T(example.Color).RED] = 'strawberry'")
        .getValue(context);

    assertEquals("strawberry", read.getValue(context, String.class));
}
~~~

Tests should use the exact accessor factory deployed by the application, avoiding constructing a context different from production.

## 11. Best Practices

- Use object indexing with a String name when the purpose is to read an object property.
- Use IndexAccessor when a structure has custom indexing rules and is not a standard Map/array/collection.
- Register the accessor on the right EvaluationContext before evaluation.
- Choose ReflectiveIndexAccessor when the structure has public read/write methods following a suitable convention.
- Only expose a write method when the expression genuinely needs to mutate data.
- Declare specific target classes and index types to prevent the accessor from accepting unintended objects.
- Return a TypedValue with accurate type information when implementing a custom IndexAccessor.
- Implement CompilableIndexAccessor if compilation is needed for custom indexing.
- Use null-safe indexing only when a null target is an acceptable situation.
- Test valid indices, wrong index types, null targets, read/write errors, and context configuration.
- Do not allow untrusted expressions to access structures or write data outside the permitted scope.

## 12. Review Checklist

Before putting a custom indexing expression into use, verify:

- [ ] Target type and index type have been identified.
- [ ] Square-bracket syntax matches the target kind.
- [ ] Object indexing uses a readable property name.
- [ ] Custom structure has a corresponding IndexAccessor.
- [ ] Accessor is registered in the EvaluationContext performing evaluation.
- [ ] canRead/read and canWrite/write follow the same target/index contract.
- [ ] Read/write methods are public if using ReflectiveIndexAccessor.
- [ ] Write access is enabled only when necessary.
- [ ] Null-safe indexing is used only to handle a null target.
- [ ] Tests cover read values, updates, wrong index types, and accessor errors.
- [ ] Compilation is tested if the application uses the SpEL compiler.

## Conclusion

SpEL supports indexing into objects by property name in square brackets and supports custom structures via IndexAccessor. Object indexing still requires a PropertyAccessor capable of reading the corresponding property; custom indexing requires an accessor registered in the EvaluationContext. Starting from Spring Framework 6.2, ReflectiveIndexAccessor connects square-bracket syntax to the public read/write methods of a custom structure. Clearly define the target, index, read/write permissions, and null behavior, then test within the application's actual context.
