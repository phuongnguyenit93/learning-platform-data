# The #this variable in SpEL projection

## 1. Projection and the role of #this

Spring Expression Language (SpEL) supports collection projection to apply a sub-expression to each element of a source collection and produce a new result collection.

Syntax:

```text
source.![projectionExpression]
```

During projection, SpEL evaluates `projectionExpression` sequentially on each element. The system variable `#this` always references the object currently being evaluated. Therefore, inside a projection, `#this` is the current element.

For example, converting a list of names to uppercase:

```java
List<String> names = List.of("Ada", "Grace", "Linus");
context.setVariable("names", names);

List<?> upperNames = parser.parseExpression(
        "#names.![#this.toUpperCase()]")
        .getValue(context, List.class);

// ["ADA", "GRACE", "LINUS"]
```

Each time the projection runs, `#this` points to a different element: `"Ada"`, `"Grace"`, and `"Linus"` in turn. The `toUpperCase()` method is called on the current element, and the result of each call is placed into the new collection.

You can omit `#this` when directly accessing a property or method of the element:

```text
#names.![toUpperCase()]
```

However, writing `#this` explicitly helps make it clear which object receives the call, especially when the expression has multiple object levels or nested projections.

## 2. Distinguishing #this and #root

SpEL always provides two system variables:

| Variable | Meaning | In projection |
|---|---|---|
| `#this` | The current object being evaluated; unprefixed names are also resolved against this object. | Changes for each element iterated by the projection. |
| `#root` | The initial root context object passed to EvaluationContext or `getValue()`. | Always remains the original object, unchanged across elements. |

For example, the root object is an Inventor with a name and a list of inventions. We want to build a description sentence for each invention:

```java
Inventor tesla = new Inventor("Nikola Tesla");
tesla.setInventions(
        "Telephone repeater",
        "Tesla coil transformer");

ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding().build();

String expression =
        "#root.inventions.![#root.name + ' invented the ' + #this + '.']";

List<?> descriptions = parser.parseExpression(expression)
        .getValue(context, tesla, List.class);

// [
//   "Nikola Tesla invented the Telephone repeater.",
//   "Nikola Tesla invented the Tesla coil transformer."
// ]
```

In the expression:

- `#root.inventions` accesses the list of inventions on the root Inventor.
- `#root.name` always retrieves the name of the root Inventor.
- `#this` inside the projection is each invention string in turn.
- Each evaluation produces a new description sentence.

If `#root.name` were replaced with `#this.name`, the expression would try to read the `name` property on the current element. However, the current element here is an invention String, not an Inventor, so the expression does not match the data model.

## 3. Accessing properties of the current element

Projection is commonly used to extract a property from each object:

```java
List<Inventor> members = loadMembers();
context.setVariable("members", members);

List<?> names = parser.parseExpression(
        "#members.![#this.name]")
        .getValue(context, List.class);
```

If each Inventor has a PlaceOfBirth, you can retrieve the birth cities of all members:

```text
#members.![#this.placeOfBirth.city]
```

Equivalent short form:

```text
#members.![placeOfBirth.city]
```

In projection, unprefixed property names are resolved against `#this`. Thus, `placeOfBirth.city` and `#this.placeOfBirth.city` have the same meaning when the expression is evaluating an Inventor.

Properties can be combined with methods and calculations:

```text
#products.![#this.code.toUpperCase()]
#products.![#this.price * 1.08]
#members.![#this.name + ' (' + #this.nationality + ')']
```

The result for each element is the value of the sub-expression, which does not have to be the same type as the source element. For example, projecting from List<Product> can return List<String> if the sub-expression retrieves product codes.

## 4. Projection on arrays, Iterable, and Map

Projection is supported on:

- Java arrays.
- Types implementing `java.lang.Iterable`, such as List and Set.
- Java Maps.

For an array or Iterable, `#this` is each element in turn. The result is a List containing the sub-expression value corresponding to each element.

Example with an integer array:

```java
int[] values = {2, 4, 6};
context.setVariable("values", values);

List<?> doubled = parser.parseExpression(
        "#values.![#this * 2]")
        .getValue(context, List.class);

// [4, 8, 12]
```

For a Map, SpEL evaluates the projection expression on each entry of type `java.util.Map.Entry`. In this case, `#this` is the current entry, from which `key` and `value` can be accessed.

```java
Map<String, Integer> scores = Map.of(
        "Ada", 95,
        "Grace", 91);

context.setVariable("scores", scores);

List<?> labels = parser.parseExpression(
        "#scores.![#this.key + ': ' + #this.value]")
        .getValue(context, List.class);

// ["Ada: 95", "Grace: 91"] (order depends on the Map)
```

A projection on a Map returns a List of values computed from each entry, not a new Map. If you need to keep key/value pairs, include the key in the result value or use selection when the goal is to filter entries while keeping the Map structure.

## 5. #this in nested projection

A projection can contain another projection. Each time evaluation enters an inner projection, `#this` switches to the current element of the inner collection.

Suppose a Company has multiple Departments, and each Department has a list of Employees. To build a list of employee names grouped by department:

```text
#root.departments.![#this.name + ': ' + #this.employees.![#this.name]]
```

Evaluation steps:

1. The outer projection iterates over each Department. At that point, `#this` is the current Department.
2. `#this.name` reads the department name before processing the inner projection.
3. `#this.employees` retrieves the list of employees for that Department.
4. The inner projection iterates over the employee list; inside this projection, `#this` is the current Employee.
5. `#this.name` inside the inner projection reads the Employee's name.

The result is a nested List: each outer element corresponds to one Department and contains the department name along with the list of employee names in that department.

Key point: `#this` is not a fixed variable pointing to the outermost element. It represents the current context object at the point where the expression is being evaluated. When entering a nested projection, `#this` changes to the inner collection's element.

If you need to access the root object from inside a nested projection, use `#root`. If you need to reuse a non-root parent object after entering an inner projection, structure the expression to capture the parent value before switching context, or place the needed value into a named variable in EvaluationContext. Do not assume `#this` still holds the outer parent object.

## 6. Combining #this with registered variables

Variables in EvaluationContext use the `#variableName` syntax. They are useful when a projection needs to compare the current element against a value outside the collection.

For example, getting only the names of members whose nationality matches the `#targetNationality` variable:

```java
context.setVariable("members", loadMembers());
context.setVariable("targetNationality", "Serbian");

List<?> matchingNames = parser.parseExpression(
        "#members.?[#this.nationality == #targetNationality].![#this.name]")
        .getValue(context, List.class);
```

In this expression:

- `#members` is the source collection.
- Inside the selection, `#this` is each Inventor being checked.
- `#targetNationality` is a fixed variable retrieved from EvaluationContext.
- Inside the projection after selection, `#this` is each retained Inventor.
- `#this.name` produces the name value for each Inventor.

Named variables help avoid confusion between the root object, the current element, and external reference data. Variable names and function names in EvaluationContext share the same namespace, so avoid naming collisions.

## 7. Projection vs. Selection

Projection and selection both iterate over a collection, but they perform two different tasks:

| Feature | Projection | Selection |
|---|---|---|
| Syntax | `.![expression]` | `.?[predicate]` |
| Goal | Transform each element into a value. | Filter and retain elements matching a condition. |
| Sub-expression | Can return String, number, object, null, or other types. | Must return a Boolean. |
| Result type | List of sub-expression values. | Sub-collection; for Map, retains the selected entries. |

Example projection retrieving names:

```text
#members.![#this.name]
```

Example selection retrieving those with Serbian nationality:

```text
#members.?[#this.nationality == 'Serbian']
```

Selection and projection can be combined:

```text
#members.?[#this.nationality == 'Serbian'].![#this.name]
```

The first expression filters members; the second transforms each retained member into a name. The final result is a List<String> in the order of the selected elements.

Projection does not remove elements just because the sub-expression returns null. If the source has three elements and the sub-expression returns `"A"`, null, and `"C"` respectively, the result still has three positions. If you want to exclude elements, use selection beforehand or filter the results in Java.

## 8. Null-safe projection and null properties

If the source collection can be null, you can use null-safe projection:

```text
#members?.![#this.name]
```

When `members` is null, the result of null-safe projection is null. When `members` is an empty collection, the result is an empty collection. These are two different situations, so callers need to handle them properly.

Null-safe projection only protects the source collection. If an element can be null or a nested property can be null, use safe navigation at the appropriate segment:

```text
#members?.![#this?.placeOfBirth?.city]
```

In the example:

- `#members?.!` protects the source collection.
- `#this?.placeOfBirth` protects against a null current element.
- `?.city` protects against a null placeOfBirth.

Safe navigation does not automatically make all remaining parts of a compound expression safe. Place `?.` at each segment where an intermediate object may be null.

If the projection expression returns null for an element, that null value remains an element in the result collection. Null-safe projection does not mean filtering out null values.

## 9. Testing #this in projection with Java

The following example verifies that #this receives each element and produces the expected results in order:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class ProjectionThisTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void usesThisForEachCurrentElement() {
        var context = new StandardEvaluationContext();
        context.setVariable("names", List.of("Ada", "Grace", "Linus"));

        List<?> result = parser.parseExpression(
                "#names.![#this.toUpperCase()]")
                .getValue(context, List.class);

        assertEquals(List.of("ADA", "GRACE", "LINUS"), result);
    }

    @Test
    void keepsNullProjectionResultsAsElements() {
        var context = new StandardEvaluationContext();
        context.setVariable("names", List.of("Ada", "", "Linus"));

        List<?> result = parser.parseExpression(
                "#names.![#this == '' ? null : #this.toUpperCase()]")
                .getValue(context, List.class);

        assertEquals(3, result.size());
        assertEquals("ADA", result.get(0));
        assertEquals(null, result.get(1));
        assertEquals("LINUS", result.get(2));
    }
}
```

The first test confirms that projection invokes the method on each current String. The second test confirms that projection keeps the position of an element whose expression returns null.

You can test both root and current object at the same time:

```java
@Test
void keepsRootWhileThisChanges() {
    Inventor tesla = new Inventor("Nikola Tesla");
    tesla.setInventions("Telephone repeater", "Tesla coil transformer");

    var context = new StandardEvaluationContext();

    List<?> result = parser.parseExpression(
            "#root.inventions.![#root.name + ' invented ' + #this]")
            .getValue(context, tesla, List.class);

    assertEquals(
            List.of(
                    "Nikola Tesla invented Telephone repeater",
                    "Nikola Tesla invented Tesla coil transformer"),
            result);
}
```

Here, #root keeps the Inventor while #this changes for each invention. This is a direct way to test the difference between the two system variables.

## 10. Order and result type

Projection creates a List containing the result of the sub-expression for each source element:

- For arrays and Lists, the result follows the order of the source elements.
- For other Iterables, order depends on the collection's iterator.
- For Maps, projection iterates over entries and produces a List; result order depends on the Map's iteration order.
- If the sub-expression returns null, null is retained in the result List.
- The result element type is determined by the sub-expression; projection does not declare a generic type by itself.

Example from List<Product> to List<String>:

```text
#products.![#this.code]
```

Example from List<Product> to List<BigDecimal>:

```text
#products.![#this.price]
```

Example from Map to List<String>:

```text
#scores.![#this.key + '=' + #this.value]
```

When retrieving the result in Java, `List.class` only describes the outermost collection type. If the caller needs a specific generic type, control the sub-expression's type and validate the returned data.

## 11. Common errors and how to handle them

| Symptom | Common cause | How to handle |
|---|---|---|
| `#this.name` cannot find property | The current element is not a type that has a name property. | Check the source element type and where the expression is running. |
| Mistakenly using #root instead of #this | #root is always the root context object, not the current element. | Use #this for the element being projected. |
| Mistakenly using #this to access root | #this has already switched to the current element. | Use #root for the original object. |
| Nested projection reads the wrong name | #this changes at each projection level. | Clearly identify the outer and inner projections; use #root for the root and evaluate parent values before entering the inner projection. |
| Projection returns a List instead of a Map | Projection on a Map creates a List from the entries. | Include the key in the projected value or use selection if a Map must be kept. |
| Result contains null even when wanting to drop elements | Projection keeps null results from the sub-expression. | Select/filter before projection or filter the result afterward. |
| Null-safe projection still throws an error | Properties inside a null element or intermediate objects are null. | Use safe navigation at each segment that can be null. |
| Results in wrong order | The source is a collection that does not guarantee iteration order. | Use an ordered source or sort before projection. |
| Expression cannot access variable | setVariable was not called or the variable name is wrong. | Register the variable in EvaluationContext and use the exact #name syntax. |
| Result does not have the expected type | The sub-expression returns another type or data is inconsistent. | Check the type of each value and apply explicit conversion in Java when needed. |

## 12. Process for reading and testing #this

1. Identify the source collection and its element type.
2. Identify the root context object passed into evaluation.
3. In projection, identify which element #this will be at each level.
4. Use #root when accessing the original object regardless of the current projection level.
5. For nested projections, note clearly when #this switches to the element of the inner collection.
6. Verify that the properties and methods accessed by the sub-expression exist on the current element type.
7. Test empty collections, null elements, and null nested properties.
8. Verify that results keep the same number of positions when the sub-expression returns null.
9. Verify the order and type of the resulting List, especially when the source is a Set or Map.
10. Use tests with distinct output values to prove #this points to the right element.

## 13. Key takeaways

- Projection uses the syntax `.![projectionExpression]` and creates a result List by evaluating the sub-expression on each element.
- `#this` is the current evaluation object; inside projection, it is the element currently being processed.
- `#root` is always the initial root context object and does not change across projections.
- #root and #this can be used together to combine root data with the current element.
- In nested projections, #this switches to the element of the inner collection.
- Projection on a Map evaluates each Map.Entry and returns a List; key/value are accessed through their corresponding properties.
- Projection preserves null if the sub-expression returns null; it is not a filter operation.
- Null-safe projection uses `?.!`; safe navigation is still needed for properties or intermediate objects that may be null.
- Result order depends on the source's iteration order.
- Test root, current element, nested projection, null handling, and result types separately.

## References

- [Spring Framework Reference — Variables, #this and #root](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-projection.html)
- [Spring Framework Reference — Safe Navigation and Safe Collection Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Projection AST Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/ast/Projection.html)
