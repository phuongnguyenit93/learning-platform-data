# Nested collections and multi-level processing

## Objectives

In Spring Expression Language (SpEL), collection operations allow filtering or transforming elements directly within an expression. When an element itself contains another collection, selection and projection can be nested to process multiple levels of data. For example, a school has many classes, each class has many students; a store has many orders, each order has many product line items.

When handling nested collections, it is important to understand the scope of **#this**, the stable role of **#root**, the result type after each step, and how to handle null or empty collections. A multi-level expression can be short, but without tracking each step, maintenance and troubleshooting become difficult.

After this lesson, you can:

- Nest selection and projection across multi-level collections.
- Track #this when moving from an outer collection to an inner collection.
- Use #root and EvaluationContext variables to pass shared data across multiple processing levels.
- Combine filtering, transformation, and property access step by step.
- Predict the result type and structure of nested expressions.
- Handle null collections, empty collections, and invalid elements.
- Know when complex processing should be moved to Java.

## 1. Multi-level data model

Let us use an example of a school with multiple classes, each class having a list of students:

~~~java
public class Student {
    private String name;
    private int score;
    private boolean active;

    public String getName() { return name; }
    public int getScore() { return score; }
    public boolean isActive() { return active; }
}

public class SchoolClass {
    private String className;
    private List<Student> students;

    public String getClassName() { return className; }
    public List<Student> getStudents() { return students; }
}

public class School {
    private List<SchoolClass> classes;

    public List<SchoolClass> getClasses() { return classes; }
}
~~~

The data structure has three levels:

1. School is the root object.
2. School contains multiple SchoolClass instances.
3. Each SchoolClass contains multiple Student instances.

An expression can start from School, traverse classes, and then continue operating on students. Each level has its own element type, so you need to know what objects the current collection contains before writing conditions.

For example, to get the list of classes:

~~~text
#root.classes
~~~

To get the list of students in the first class:

~~~text
#root.classes[0].students
~~~

To filter students in the first class with a score of at least 80:

~~~text
#root.classes[0].students.?[score >= 80]
~~~

This is a selection at the student level. When you need to process all classes, you can nest the operation inside an outer-level projection or selection.

## 2. Scope of #this in nested collections

**#root** always represents the root object passed in when evaluating the expression. **#this** represents the current object in the context being evaluated.

When a collection operation iterates over elements, #this switches to the current element of that operation. If there is another collection operation inside the condition or projection, the inner operation creates a current scope for the elements of the inner collection.

For example:

~~~text
#root.classes.![students.?[active]]
~~~

You can read the expression step by step:

1. #root.classes retrieves the list of classes from School.
2. Outer projection .![...] runs once for each SchoolClass.
3. During each projection step, students is the list of students of the current class.
4. Selection .?[active] runs on that list of students; #this is now the Student being evaluated.
5. Selection returns the active students of the current class.

The result is a list of lists of students. Each inner list corresponds to one class.

You can write #this explicitly at both levels:

~~~text
#root.classes.![#this.students.?[#this.active]]
~~~

In the outer projection, #this is SchoolClass. Inside the selection on students, #this is Student. When the inner operation finishes, the expression continues in the scope of the outer projection.

### #root remains unchanged

Even when #this is a Student inside a nested selection, #root is still the original School:

~~~text
#root.classes.![students.?[score >= #root.minimumScore]]
~~~

This example assumes the root object provides a minimumScore property. Each student is compared against the same threshold on School.

If the threshold value comes from configuration, it can be passed through a variable:

~~~text
#root.classes.![students.?[score >= #minimumScore]]
~~~

The #minimumScore variable is provided in EvaluationContext and can be used at every level of the expression.

## 3. Nesting selection to filter the outer collection based on an inner collection

A common case is selecting an outer-level object if its child collection has at least one element satisfying a condition.

For example, retrieve classes that have at least one active student:

~~~text
#root.classes.?[students.?[active].size() > 0]
~~~

How to read it:

1. Outer selection iterates over each SchoolClass.
2. In each class, inner selection filters students whose active is true.
3. size() gets the number of selected students.
4. If the count is greater than 0, the current class is kept.

In the outer selection, #this is SchoolClass. In the inner selection, #this is Student. When the inner selection completes, the size result is used to decide whether to keep the current SchoolClass.

You can write the condition more explicitly:

~~~text
#root.classes.?[#this.students.?[#this.active].size() > 0]
~~~

### Filtering by minimum count

If at least two qualifying students are needed:

~~~text
#root.classes.?[students.?[active and score >= #minimumScore].size() >= 2]
~~~

The expression keeps only classes that have at least two students who are both active and meet minimumScore.

This approach works well for simple counting conditions. If you need multiple aggregations, grouping, sorting, or complex calculations per class, consider handling it in Java for easier testing and optimization.

## 4. Nesting projection for multi-level transformation

Projection uses **.![ ]** to transform each element into the result of the inner expression. If the inner result is itself a collection, the outer projection retains that collection as a result element.

For example, retrieve the names of active students in each class:

~~~text
#root.classes.![students.?[active].![name]]
~~~

The result has the form:

~~~text
[
  ["Lan", "An"],
  ["Minh"],
  ["Hoa", "Nam", "Mai"]
]
~~~

Each sublist contains the names of active students in one class. This is a nested structure; projection does not automatically merge all names into a flat list.

You can transform to scores instead of names:

~~~text
#root.classes.![students.?[active].![score]]
~~~

The result has structure List<List<Integer>> if score is an int boxed into Integer in the result collection.

### Retaining additional outer-level data

You can retrieve class names and student lists using separate projections, but note that each projection produces a distinct result structure. For example, retrieve the list of class names:

~~~text
#root.classes.![className]
~~~

And the list of student names per class:

~~~text
#root.classes.![students.![name]]
~~~

If you need to return a combined structure containing the class name along with its student list in one result object, it is usually better to create a DTO in Java rather than trying to combine two independent projections into a complex structure in SpEL.

## 5. Combining selection and projection across multiple levels

Selection and projection can be chained together. A common workflow is filtering the outer collection, filtering the inner collection, and then transforming the remaining elements into the needed values.

For example, retrieve the names of active students with scores at or above a threshold, per class:

~~~text
#root.classes.![students.?[active and score >= #minimumScore].![name]]
~~~

Steps:

1. Outer projection iterates over each class.
2. Inner selection keeps students who are active and meet the threshold.
3. Inner projection transforms each remaining Student into name.
4. Outer projection collects the lists of names per class.

The result is a List<List<String>>.

If you only want classes that have at least one qualifying student, you can filter classes first:

~~~text
#root.classes.?[students.?[active and score >= #minimumScore].size() > 0].![students.?[active and score >= #minimumScore].![name]]
~~~

This expression has two clear stages:

- Outer selection removes classes that have no qualifying students.
- Outer projection builds the list of qualifying student names for each remaining class.

The inner condition appears twice. If that logic becomes long or prone to diverging across locations when edited, move the rule into a clearly named Java method or prepare pre-filtered data before evaluation.

## 6. Nested collections in a Map

A Map can contain values that are collections. When selection runs on a Map, #this represents the current entry; key and value can be accessed through the entry.

Suppose the root object contains a Map from group name to list of students:

~~~java
Map<String, List<Student>> groups;
~~~

To keep entries that have at least one active student:

~~~text
#root.groups.?[#this.value.?[active].size() > 0]
~~~

In the outer selection, #this is Map.Entry. In the inner selection on value, #this is Student. The outer selection result remains a Map so keys and values of the selected groups are preserved.

Retrieve the list of active student names per entry:

~~~text
#root.groups.![value.?[active].![name]]
~~~

The result is a list of lists of names, in the Map's iteration order. Because projection on a Map builds results from the iterated values, if you need to keep the key alongside each sublist, build an explicit result structure in Java or use a testable expression convention.

With a Map that does not guarantee order, do not rely on element positions in the result. If order matters, choose a Map implementation with appropriate ordering rules.

## 7. Multiple collection levels and result types

When nesting multiple collection operations, predict the result type after each level. This helps avoid assuming the result is always a flat List.

| Expression | General result type |
|---|---|
| **#root.classes** | List<SchoolClass> |
| **#root.classes.?[condition]** | Filtered List<SchoolClass> |
| **#root.classes.![students]** | List<List<Student>> |
| **#root.classes.![students.?[active]]** | List<List<Student>> |
| **#root.classes.![students.?[active].![name]]** | List<List<String>> |
| **#root.classes.?[students.?[active].size() > 0]** | List<SchoolClass> |

Exact types may depend on the source collection and the value type returned by the projection. Request an explicit result type in Java when calling getValue if the application needs a specific type.

### Selection does not flatten collections

Example:

~~~text
#root.classes.![students.?[active].![name]]
~~~

Does not return a single List<String>. It returns a list containing lists of names per class.

If the business requirement is a flat list of all active student names, SpEL collection projection does not perform flatMap automatically. You can perform a flatten step in Java after obtaining the nested result, or prepare a flat collection in a service before evaluating the expression.

Do not rely on type casting to flatten a structure. Casting only changes how Java views the result, not the inner subcollections themselves.

## 8. Null and empty collections at each level

Nested collections can be null in multiple places:

- Outer collection is null, for example classes is null.
- An outer element is null, for example a null SchoolClass in classes.
- Child collection is null, for example students is null in a class.
- Inner element is null, for example a null Student.
- Property used in the predicate is null.

Distinguish null collections from empty collections. An empty collection has no elements to filter and normally yields an empty selection result. A null collection cannot be iterated by normal selection.

Since Spring Framework 6.2, SpEL supports null-safe selection and projection. Example:

~~~text
#root.classes?.![students?.?[active]]
~~~

If classes is null, null-safe projection returns null. If a class has null students, null-safe selection on students returns null at that corresponding position.

A null-safe operation only handles a null target at the position where the operator is placed. It does not automatically handle null elements inside the collection or nonexistent properties. If a collection may contain null elements, check the element before accessing properties:

~~~text
#root.students.?[#this != null and #this.active]
~~~

For nested collections, place guard conditions at the appropriate level:

~~~text
#root.classes.?[#this != null and #this.students != null and #this.students.?[#this != null and #this.active].size() > 0]
~~~

The expression above keeps only classes that are non-null, have non-null students, and have at least one non-null active student. If the expression becomes too long, move basic validation and filtering to Java.

Verify the Spring Framework version before using null-safe collection operation syntax; null-safe selection/projection forms were added in Spring Framework 6.2.

## 9. Using shared variables across multiple processing levels

Variables in EvaluationContext can be referenced at any level of an expression. This is useful when multiple selections share a threshold or status code.

Example:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumScore", 80);
context.setVariable("requiredStatus", "ACTIVE");
~~~

Expression:

~~~text
#root.classes.![students.?[active and score >= #minimumScore].![name]]
~~~

Every selection on students uses the same minimumScore.

You can pass a variable for a status condition:

~~~text
#root.classes.![students.?[status == #requiredStatus].![name]]
~~~

Using variables avoids hardcoding configuration values into expression strings. It also makes it easier to test the same expression with different thresholds or policies.

Document the variable names and types that each expression expects. If a variable is missing or has an incompatible type, an error will occur when evaluating a level that uses that variable.

## 10. Breaking complex expressions into understandable steps

A deeply nested expression can be valid yet hard to read. When there are multiple levels of selection/projection, rewrite it step by step to determine intermediate results.

Example goal: retrieve names of active students scoring 80 or above across all classes.

Step 1 — retrieve the list of classes:

~~~text
#root.classes
~~~

Step 2 — retrieve qualifying students in one class:

~~~text
#root.classes[0].students.?[active and score >= 80]
~~~

Step 3 — retrieve names of qualifying students in that class:

~~~text
#root.classes[0].students.?[active and score >= 80].![name]
~~~

Step 4 — apply across all classes:

~~~text
#root.classes.![students.?[active and score >= 80].![name]]
~~~

Each step clarifies the data type and the scope of #this. If a step does not return the expected result, you can inspect the corresponding collection, predicate, or projection individually.

If many processing steps are needed that cannot be expressed concisely, consider:

- Creating a Java method whose name expresses the business intent.
- Splitting one large rule into small named expressions.
- Computing intermediate collections in a service and passing them to SpEL.
- Using a DTO to hold multi-level result structures.
- Writing unit tests for individual steps instead of one giant expression.

SpEL fits conditions and data transformations with a clear structure. Logic requiring grouping, sorting, multi-type aggregation, or detailed error handling is usually easier to maintain in Java.

## 11. Common errors and how to diagnose them

| Symptom | Possible cause | Resolution |
|---|---|---|
| #this references the wrong object | Inside a nested selection/projection | Identify the nearest operation and current element type |
| #root does not point to the child collection | Confusing root object with current element | Use paths from #this for the current object, keep #root for the initial root |
| Result has multiple sublists | Nested projection preserves collection structure | Decide whether a nested result is needed or flatten in Java |
| Outer selection returns empty | Inner or outer predicate does not match | Test each predicate on representative data |
| Error reading a property at an inner level | Child element is null or wrong type | Check the child collection and element type |
| Error calling size() | Selection result is null or source collection is invalid | Verify null-safe behavior and check the collection |
| Unstable result order | Source collection does not guarantee order | Choose a List or Map with explicit ordering |
| Expression is hard to maintain | Too many levels or duplicated conditions | Split steps or move logic to Java |

When diagnosing, start from the outer collection and inspect each level in turn. Do not edit the entire expression at once before identifying which level produces the wrong result.

## 12. Testing nested collections

Tests should verify the result structure, not only the final element count.

Example testing the list of active student names per class:

~~~java
@Test
void selectsActiveStudentNamesByClass() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "#root.classes.![students.?[active].![name]]");

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    School school = sampleSchool();

    List<?> result = expression.getValue(context, school, List.class);

    assertEquals(2, result.size());
    assertEquals(List.of("Lan", "An"), result.get(0));
}
~~~

The test verifies there are two sublists and checks the content of the first sublist. In real tests, create fixtures with multiple classes having different numbers of students and states to test empty branches as well.

Cases to include:

| Case | What to verify |
|---|---|
| Multiple child collections | Each child collection is processed independently |
| Empty child collection | Result at that level is empty |
| Null child collection | Error or null-safe behavior matches contract |
| Null child element | Predicate does not accidentally dereference null |
| No elements match | Selection returns an empty collection |
| Multiple elements match | Correct count and order are preserved |
| Predicate uses external variable | Variable is present and has the right type |
| Selection nested in projection | #this switches properly per level |
| Selection nested in selection | Outer condition receives the right inner result |
| Map containing collections | Keys/values and result type are preserved properly |
| Multi-level projection | Nested List structure matches expectations |
| Flattening requirement | Java flattening step yields the right result |

Use the same EvaluationContext type and root object structure as production. If the application uses a custom PropertyAccessor, create the context from the same factory in tests.

## 13. Best practices

- Write expressions level by level from root to child collections.
- Use #this to make clear which element is being processed in the current operation.
- Use #root for shared data on the root object and context variables for configuration.
- Distinguish selection from projection at each level.
- Predict the result type after each projection; nested collections do not auto-flatten.
- Clearly define behavior for null collections, empty collections, and null elements.
- Use null-safe selection/projection when the Spring version supports it and null is an acceptable case.
- Avoid repeating a long predicate across levels; move it to a method or prepare data in Java when appropriate.
- Do not invoke methods with side effects inside selection/projection.
- Choose collections with stable order when results depend on position.
- Test intermediate steps and the final result structure.
- Move grouping, sorting, complex aggregation, or flattening to Java when expressions become hard to read.

## 14. Review checklist

Before accepting a multi-level collection expression, check:

- [ ] Root object and child collections have been identified.
- [ ] Element type at each level is clear.
- [ ] #this is understood according to the current collection operation.
- [ ] #root is used for root data, not confused with the current element.
- [ ] Each selection has a clear Boolean predicate.
- [ ] Each projection has an expected result type.
- [ ] Whether nested List/Map results should be kept or flattened has been decided.
- [ ] Null collections, empty collections, and null elements are distinguished.
- [ ] Null-safe operations match the running Spring version.
- [ ] Source order is guaranteed if business logic depends on order.
- [ ] Expression does not contain complex logic that belongs in Java.
- [ ] Tests exist for individual levels and the final result structure.

## Conclusion

Nested collections in SpEL are handled by combining selection and projection level by level. Each collection operation has its own #this scope for the element under evaluation, while #root continues to represent the original object. Nested projection preserves child collection structures and does not flatten results automatically. When writing multi-level expressions, determine data types and results after each step, handle null intentionally, use variables for shared conditions, and move overly complex logic to Java for easier testing and maintenance.
