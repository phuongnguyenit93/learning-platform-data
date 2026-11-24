# Accessing size, empty, and collection properties

## 1. Why read collection size and state?

In SpEL, expressions often need to know how many elements a collection has or whether it is empty before proceeding with further processing.

For example:

    members.size()
    members.isEmpty()

These two expressions invoke familiar Java Collection methods. SpEL allows accessing properties and invoking methods on objects, so those APIs can be used directly inside an expression.

Three concepts need to be distinguished:

- **Size:** the number of elements currently in a Collection or the number of entries in a Map.
- **Empty state:** whether a collection or map has zero elements.
- **Object property:** a value accessed according to property accessor rules, usually through a getter or field.

Some syntaxes look similar but are handled differently by SpEL. In particular, for a regular List or Map, size() is a method; you should not write size as a property if the class does not have a corresponding getter.

## 2. Reading the size of List, Set, and Collection

Java Collection interfaces provide the size() method, which returns the current number of elements.

For example:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable(
        "members",
        List.of("Lan", "Minh", "An")
    );

    Integer count = parser
        .parseExpression("#members.size()")
        .getValue(context, Integer.class);

    // count = 3

The expression #members.size() performs these steps:

1. Look up the variable members in EvaluationContext.
2. Call the size() method on the List object.
3. Return the number of elements as an Integer.

The same syntax applies to Set or other Collection implementations:

    #members.size()
    #tags.size()
    #permissions.size()

The result is the number of elements present at the time the expression is evaluated.

Do not confuse the element count with the last index. A List with size equal to 3 has valid indices 0, 1, and 2; the last index is typically size() - 1.

## 3. Reading the size of a Map

Map also provides the size() method. The returned value is the number of key-value entries, not the sum of keys and values combined.

For example:

    Map<String, Object> settings = new HashMap<>();
    settings.put("theme", "dark");
    settings.put("language", "vi");

    context.setVariable("settings", settings);

    Integer count = parser
        .parseExpression("#settings.size()")
        .getValue(context, Integer.class);

    // count = 2

If a Map has two key-value pairs, size() returns 2.

You must distinguish calling the size() method from reading an entry whose key is size:

    #settings.size()

Calls the size() method to count the number of entries.

    #settings['size']

Reads the value stored under the string key size.

When accessing a Map entry, use an indexer with the key in square brackets to make the intent clear. Do not use dot notation as a substitute for key lookup unless an accessor specifically designed for that purpose is configured.

## 4. Checking an empty collection with isEmpty()

Collection and Map provide the isEmpty() method to check whether there are any elements.

For example:

    context.setVariable("members", List.of());

    Boolean empty = parser
        .parseExpression("#members.isEmpty()")
        .getValue(context, Boolean.class);

    // empty = true

If the collection has at least one element, isEmpty() returns false.

For example:

    context.setVariable("members", List.of("Lan"));

    Boolean empty = parser
        .parseExpression("#members.isEmpty()")
        .getValue(context, Boolean.class);

    // empty = false

isEmpty() returns a boolean, so it can be used directly in conditions:

    #members.isEmpty() ? 'No members' : 'Has members'

Or combined with logical operators:

    #members != null and !#members.isEmpty()

The null condition is checked first. Thanks to AND short-circuiting, SpEL does not call isEmpty() if members is null.

## 5. How do the empty property and the isEmpty() method differ?

SpEL supports property access through getters following JavaBean conventions.

For a boolean method named isEmpty(), the corresponding property is named empty. Therefore, when using the default reflective property access, you can write:

    #members.empty

This expression reads the empty property through the isEmpty() getter.

The explicit method call is:

    #members.isEmpty()

Both forms can produce the same result for standard Collections in StandardEvaluationContext:

| Syntax | How SpEL handles it |
| --- | --- |
| #members.isEmpty() | Directly invokes the isEmpty() method |
| #members.empty | Reads the empty property via the isEmpty() getter |
| #members.size() | Invokes the size() method |
| #members.size | Attempts to read the size property via a getSize() getter; standard List does not have this getter |

The last point is very error-prone. Standard List and Map have a size() method, but do not have a JavaBean getter getSize(). Therefore, the expression #members.size usually does not work as expected.

Use #members.size() to retrieve the size.

The empty property depends on the property accessors registered in EvaluationContext. If the application replaces accessors or uses a restricted context, verify that the accessor supports reading the corresponding getter. When you want to express intent clearly and avoid confusion with a custom property, calling isEmpty() directly is usually easier to understand.

## 6. Arrays use length, not size()

Arrays in Java do not implement Collection and do not have size() or isEmpty() methods.

SpEL supports the special property length for arrays:

    int[] scores = {80, 90, 75};

    context.setVariable("scores", scores);

    Integer count = parser
        .parseExpression("#scores.length")
        .getValue(context, Integer.class);

    // count = 3

Checking an empty array:

    #scores.length == 0

Do not write:

    #scores.size()
    #scores.isEmpty()

because arrays do not have those methods.

Quick comparison:

| Data type | Get element count | Check empty |
| --- | --- | --- |
| List | list.size() | list.isEmpty() or list.empty |
| Set | set.size() | set.isEmpty() or set.empty |
| Collection | collection.size() | collection.isEmpty() or collection.empty |
| Map | map.size() | map.isEmpty() or map.empty |
| Array | array.length | array.length == 0 |
| String | string.length() | string.isEmpty() or string.empty |

For arrays, length is a special property supported by SpEL's reflective property accessor. It is not a length() method on the array.

## 7. String also has length and isEmpty

String is not a Collection, but it has useful methods for checking content:

    #name.length()
    #name.isEmpty()

For example:

    context.setVariable("name", "Spring");

    Integer length = parser
        .parseExpression("#name.length()")
        .getValue(context, Integer.class);

    // length = 6

Checking an empty string:

    #name.isEmpty()

The empty property can also be read via the isEmpty() getter if the property accessor allows it:

    #name.empty

Distinguish an empty string from a whitespace-only string:

    ''.isEmpty()       // true
    '   '.isEmpty()    // false

If business logic treats whitespace-only strings as having no content, use trim() or isBlank() with the appropriate Java version:

    #name == null or #name.isBlank()

Do not use size() for String. String has length(), not size().

## 8. Collection properties vs element properties

A collection can contain objects that have their own properties. You must distinguish properties of the collection from properties of each element.

For example:

    members.size()

Gets the number of elements in the members collection.

    members[0].name

Gets the name property of the first element.

    members.?[active == true].size()

Filters active members, then gets the number of elements in the selection result.

In selection, the active property is evaluated on each element. After selection returns the result collection, size() is called on that collection.

Full example:

    List<Member> members = List.of(
        new Member("Lan", true),
        new Member("Minh", false),
        new Member("An", true)
    );

    context.setVariable("members", members);

    Integer activeCount = parser
        .parseExpression(
            "#members.?[active == true].size()"
        )
        .getValue(context, Integer.class);

    // activeCount = 2

This form is easy to read, but selection creates a result collection before calling size(). If you only need a count on a very large collection, consider handling it in Java or at the query layer to avoid creating unnecessary intermediate collections.

## 9. Accessing properties on objects wrapping a collection

Many applications do not pass a List or Map directly as the root object. Instead, the collection resides inside a business object.

For example:

    public class Department {
        private List<Employee> employees;

        public List<Employee> getEmployees() {
            return employees;
        }
    }

If Department is the root object, you can write:

    employees.size()
    employees.isEmpty()
    employees.empty

If the object is placed in a variable:

    #department.employees.size()
    #department.employees.isEmpty()

The employees property is read first, and then the size() or isEmpty() method is called on the returned collection.

If Department or employees can be null, use null-safe navigation at each step:

    #department?.employees?.size()

    #department?.employees?.isEmpty()

If department is null, the employees access step returns null. The subsequent ?. guards the method call on employees.

Do not place the null-safe operator only at the beginning of a path and assume every subsequent step is automatically safe.

## 10. Handling null and empty collections

Null and an empty collection are two different states:

- Null: there is no collection object to access yet.
- Empty collection: the object exists, but contains no elements.
- Non-empty collection: the object exists and size is greater than 0.

For example:

    #members == null
    #members.isEmpty()
    #members.size() == 0

The three expressions check three different conditions. If members is null, calling isEmpty() or size() directly can cause an evaluation error.

You can use safe navigation:

    #members?.isEmpty()
    #members?.size()

When members is null, null-safe expressions return null.

If you want a default count of 0:

    #members?.size() ?: 0

Elvis chooses 0 when the left-hand result is null. If members exists and is empty, size() already returns 0. If it has elements, the actual size is preserved.

If you want to treat null the same as an empty collection when checking status:

    #members == null or #members.isEmpty()

Or use safe navigation with a default value:

    #members?.empty ?: true

When members is null or empty, the result is true. When the collection has elements, empty is false and Elvis preserves false.

## 11. Reading other properties on Map and Collection

In addition to size and empty, Map or Collection objects also provide many useful methods.

For Map:

    #settings.keySet()
    #settings.values()
    #settings.entrySet()
    #settings.containsKey('theme')
    #settings.containsValue('dark')

For Collection:

    #members.contains('Lan')
    #members.iterator()
    #members.toArray()

These methods are invoked using method invocation syntax. Invocation capability depends on the MethodResolver and EvaluationContext configuration.

Do not confuse method names with properties. For example, keySet() is a method returning the Map's key set; keySet is not a general property guaranteed to exist on every object.

For a Map, if you need to retrieve a value by key, use:

    #settings['theme']

If you need to count entries, use:

    #settings.size()

The two expressions serve different purposes.

## 12. JavaBean properties on custom collections

A custom-written class can define its own getters to provide convenient properties for SpEL.

For example:

    public class MemberGroup {
        private List<Member> members;

        public List<Member> getMembers() {
            return members;
        }

        public int getSize() {
            return members == null ? 0 : members.size();
        }

        public boolean isEmpty() {
            return members == null || members.isEmpty();
        }
    }

With a MemberGroup object, the following properties can be accessed:

    #group.size
    #group.empty

Here size is a valid property because the class has getSize(). empty is a valid property because the class has isEmpty().

This differs from a standard List:

    #members.size

List does not have getSize(), so SpEL cannot infer a size property solely from the size() method.

If a custom class has both a property getter and a method with the same meaning, choose one consistent access style so expressions remain easy to understand.

## 13. Cost of calling size and empty

For common implementations such as ArrayList, HashSet, and HashMap, size() and isEmpty() typically read an internal counter or pre-existing state, so they are very fast.

However, do not assume every Collection implementation has O(1) cost. A custom collection might compute its size by traversing data or performing additional work.

Some notes:

- Calling size() multiple times on the same collection is usually unnecessary if the data does not change.
- isEmpty() usually expresses intent more clearly when you only need to know whether the collection has elements.
- Do not use size() to check emptiness when isEmpty() already expresses the condition directly.
- Accessing size after selection may require creating an intermediate collection.
- If a collection is loaded from an ORM, accessing or iterating over it may trigger data loading depending on mapping and persistence context state.
- Do not invoke methods with I/O or side effects in an expression just to check collection state.

For example:

    #members.size() > 0

can be written more clearly as:

    !#members.isEmpty()

The two expressions express the same condition when members is non-null, but isEmpty() states the goal directly.

## 14. Common mistakes

| Expression or situation | Problem | Solution |
| --- | --- | --- |
| #members.size | List does not have a getSize() getter | Use #members.size() |
| #members.isEmpty | Missing method call parentheses or incorrect property name | Use #members.isEmpty() or #members.empty |
| #array.size() | Array does not have a size() method | Use #array.length |
| #string.size() | String does not have a size() method | Use #string.length() |
| #members.isEmpty() when members is null | Calling a method on null | Check for null or use #members?.isEmpty() |
| #settings.size when wanting to count entries | Accessing the size property | Use #settings.size() |
| #settings['size'] when wanting to count entries | Reading the key size | Use #settings.size() |
| SimpleEvaluationContext disallows method calls | Method resolution is not enabled | Use an appropriate property accessor or configure a method resolver as needed |

When encountering an error, check the actual object type, whether the method exists, whether the property accessor supports it, and whether the EvaluationContext allows method resolution.

## 15. Key points to remember

- Collection and Map use size() to get the number of elements or entries.
- Collection and Map use isEmpty() to check for emptiness.
- In JavaBean-style reflective property access, empty can be read via the isEmpty() getter.
- Standard List does not have a size property; use size() instead of size.
- Array uses the length property and does not have size() or isEmpty().
- String uses length() and isEmpty().
- Map keys are accessed with an indexer, for example map['size']; the size() method counts entries.
- Property and method access depend on the accessors/resolvers of EvaluationContext.
- Null differs from an empty collection; use safe navigation or null checks before calling methods.
- When you only need to check whether elements exist, isEmpty() expresses intent better than size() > 0.
- For selection on large collections, consider the cost of creating the result collection before calling size().

When writing an expression, identify the data type first: Collection, Map, array, or String. Then choose the right API: size(), isEmpty(), length, or a property getter. Clearly distinguishing method invocation from property access helps prevent evaluation errors and makes expressions easier to read.

## References

- Spring Framework Reference — Properties, Arrays, Lists, Maps, and Indexers: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/properties-arrays.html
- Spring Framework Reference — Evaluation and EvaluationContext: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
- Spring Framework source — ReflectivePropertyAccessor: https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/support/ReflectivePropertyAccessor.java
