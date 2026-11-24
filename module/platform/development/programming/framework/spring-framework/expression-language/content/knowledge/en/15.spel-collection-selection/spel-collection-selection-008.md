# Null-safe selection in Spring Expression Language

Spring Expression Language (SpEL) supports selection to filter elements of a collection according to a condition. For example, you can retrieve all members with Serbian nationality using the expression:

~~~spel
#members.?[nationality == 'Serbian']
~~~

If the source collection may be null, standard selection cannot be performed on a null object. Starting with Spring Framework 6.2, SpEL supports **null-safe selection** by placing the null-safe operator immediately before the selection operator:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

Two very similar-looking syntaxes need to be distinguished accurately:

- **Null-safe selection:** ?.?[...]
- **Null-safe indexing:** ?.[]

Therefore, ?.[] is the safe indexer syntax when retrieving an element by index or key; selection with condition brackets needs an extra ? after the null-safe operator. This lesson focuses on null-safe selection and how it handles potentially null collections.

## 1. How does standard selection work?

Selection is the operation of filtering a collection. SpEL evaluates a predicate for each element and then retains the elements that satisfy the condition.

General selection syntax:

~~~spel
collection.?[condition]
~~~

For example, suppose there is a list of members:

~~~java
public class Member {
    private final String name;
    private final String nationality;

    public Member(String name, String nationality) {
        this.name = name;
        this.nationality = nationality;
    }

    public String getName() {
        return name;
    }

    public String getNationality() {
        return nationality;
    }
}
~~~

Create the collection and register it in EvaluationContext:

~~~java
List<Member> members = Arrays.asList(
    new Member("Ana", "Serbian"),
    new Member("Mark", "American"),
    new Member("Mila", "Serbian")
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);
~~~

Selection:

~~~spel
#members.?[nationality == 'Serbian']
~~~

The result is a collection containing Ana and Mila.

Inside the predicate:

- SpEL iterates over each element of the collection.
- nationality is read on the element being examined.
- #this references the current element.
- The condition returns a Boolean to decide whether the element is retained.

It can be written more explicitly:

~~~spel
#members.?[#this.nationality == 'Serbian']
~~~

Both ways express filtering by nationality of the current element.

## 2. The problem when the source collection is null

In real applications, a collection may come from an API, database, configuration, or an uninitialized property. Therefore, the variable or property representing the collection may hold a null value.

Example:

~~~java
List<Member> members = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);
~~~

If evaluating standard selection:

~~~spel
#members.?[nationality == 'Serbian']
~~~

SpEL needs to iterate over the elements of the collection, yet the value of #members is null. With no collection to iterate over, evaluation can raise an error.

This differs from an empty collection:

~~~java
List<Member> members = Collections.emptyList();
~~~

An empty collection is still a valid object. Selection can run and return an empty collection because no element satisfies the predicate.

## 3. Null-safe selection syntax ?.?

Null-safe selection uses the null-safe operator ?. immediately before the selection operator ?[]:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

If #members is null, SpEL returns null and skips iterating over the collection. If the collection exists, SpEL performs selection as usual.

Example:

~~~java
List<Member> members = null;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#members?.?[nationality == 'Serbian']"
);

Object result = expression.getValue(context);
System.out.println(result);
~~~

Output:

~~~text
null
~~~

Processing flow:

1. SpEL reads the #members variable from EvaluationContext.
2. The variable's value is null.
3. The ?. operator recognizes the target collection is null.
4. Selection is not executed.
5. The Expression returns null.

This syntax is useful when the source data is optional and the application wants to avoid errors simply because the collection has not been initialized.

## 4. Distinguishing null-safe selection from null-safe indexing

The two syntaxes look similar but perform two different operations.

| Purpose | Syntax | Example |
|---|---|---|
| Get element by index or key | ?.[] | #members?.[0] |
| Filter all elements satisfying condition | ?.?[] | #members?.?[active] |
| Get first element satisfying condition | ?.^[] | #members?.^[active] |
| Get last element satisfying condition | ?.$[] | #members?.$[active] |

Example:

~~~spel
#members?.[0]
~~~

reads the element at position 0 if the collection exists.

Meanwhile:

~~~spel
#members?.?[active]
~~~

filters the collection and returns elements whose active is true.

Therefore, when referring to null-safe selection, the exact syntax is ?.?[...], not ?.[].

## 5. Forms of null-safe selection

SpEL has different selection forms. The null-safe operator can be combined with each form.

### 5.1. Selecting all matching elements

Use ?[] to get all elements satisfying the predicate:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

If the collection is null, the result is null. If the collection exists, the result is a collection containing all matching elements.

### 5.2. Selecting the first matching element

Use ^[] to get the first element satisfying the condition:

~~~spel
#members?.^[nationality == 'Serbian']
~~~

If the collection is null, the expression returns null. If the collection exists, SpEL finds the first matching element in iteration order.

### 5.3. Selecting the last matching element

Use $[] to get the last element satisfying the condition:

~~~spel
#members?.$[nationality == 'Serbian']
~~~

If the collection is null, the expression returns null. If the collection exists, SpEL finds the last matching element.

The first and last selection forms typically return a single element, whereas ?[] selection returns a collection of matching elements.

## 6. Null-safe selection with List

Example with a populated list:

~~~java
List<Member> members = Arrays.asList(
    new Member("Ana", "Serbian"),
    new Member("Mark", "American"),
    new Member("Mila", "Serbian")
);

context.setVariable("members", members);

Expression selection = parser.parseExpression(
    "#members?.?[nationality == 'Serbian']"
);

Object result = selection.getValue(context);
~~~

The result is a collection containing two elements, Ana and Mila.

You can reuse the same Expression when the variable's value changes:

~~~java
context.setVariable("members", null);
Object whenNull = selection.getValue(context);

context.setVariable(
    "members",
    Collections.emptyList()
);
Object whenEmpty = selection.getValue(context);
~~~

The two cases produce different results:

- When members is null, null-safe selection returns null.
- When members is an empty list, selection returns an empty collection.

The Expression does not need to be re-parsed simply because the input data changes.

## 7. Null-safe selection with Map

SpEL also supports selection on map. With a map, the predicate can access the key and value properties of the current entry.

Example:

~~~java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("Ana", 90);
scores.put("Mark", 65);
scores.put("Mila", 95);

context.setVariable("scores", scores);
~~~

Filter entries with a value of 80 or higher:

~~~spel
#scores?.?[value >= 80]
~~~

Selection on a map creates a new map consisting of the matching entries. Inside the predicate, value is the current entry's value; key is the corresponding key.

It can be written explicitly via #this:

~~~spel
#scores?.?[#this.value >= 80]
~~~

If #scores is null, null-safe selection returns null without iterating over the map.

If the map exists but is empty, selection returns an empty map. If the map has data but no entry matches, the result is also an empty map.

## 8. Collection elements may be null

Null-safe selection protects the source collection when the collection itself is null. It does not automatically protect individual elements inside the collection.

Example:

~~~java
List<Member> members = new ArrayList<>();
members.add(null);
members.add(new Member("Ana", "Serbian"));

context.setVariable("members", members);
~~~

Predicate:

~~~spel
#members?.?[nationality == 'Serbian']
~~~

can fail when the current element is null and SpEL tries to read the nationality property on that element.

If elements may also be null, guard the access inside the predicate:

~~~spel
#members?.?[#this != null && #this.nationality == 'Serbian']
~~~

The && operator uses short-circuit evaluation. When #this is null, the right-hand side is not evaluated.

Null-safe navigation can be used inside the predicate:

~~~spel
#members?.?[#this?.nationality == 'Serbian']
~~~

Thus, two levels need to be distinguished:

- Null-safe selection protects the source collection.
- Null-safe property access inside the predicate protects potentially null elements or properties.

## 9. Empty collection, no matching elements, and null result

These three situations need to be distinguished:

| Source state | Selection | Result |
|---|---|---|
| Collection is null | #members?.?[condition] | null |
| Collection exists but is empty | #members?.?[condition] | Empty collection |
| Collection has elements but none match | #members?.?[condition] | Empty collection |
| Collection has matching elements | #members?.?[condition] | Collection of matching elements |

Null-safe selection does not convert null into an empty collection. If downstream code must always receive a collection, the application must normalize a null result to an empty collection or handle null in the next step.

With first selection or last selection, the result is the selected element; if no element matches, there is no element to return. Therefore, code consuming the result should handle the null case accordingly.

## 10. Null-safe selection in compound expressions

An expression can continue operating on the selection result:

~~~spel
#members?.?[active].size()
~~~

If #members is null, selection returns null. The subsequent .size() call can still try to invoke a method on null and cause an error.

If the selection result may be null, guard the next step as well:

~~~spel
#members?.?[active]?.size()
~~~

Here:

1. #members?.?[active] guards the source collection.
2. ?.size() guards the size call on the selection result if the result is null.

Elvis can be used to replace a null result with a default value:

~~~spel
#members?.?[active]?.size() ?: 0
~~~

If the collection is null, the expression returns 0. If the collection exists, the result is the count of active elements. If selection returns an empty collection, size is 0.

This notation shows that the null-safe operator needs to be placed at each point where a null value could be dereferenced.

## 11. Spring Framework version

Null-safe selection and projection are supported starting in Spring Framework 6.2. If the application uses an older version, the parser may not recognize null-safe selection syntax.

For versions without support, you can check for null before performing selection:

~~~spel
#members != null ? #members.?[active] : null
~~~

If you want the result to be an empty collection instead of null, you can normalize in Java code or use an alternative branch matching the application's collection type.

When sharing expressions across multiple services, check the Spring Framework version of each service to avoid using incompatible syntax.

## 12. Complete example in Java

The following example filters active members, where the collection may be null and some elements may also be null:

~~~java
public class Member {
    private final String name;
    private final boolean active;

    public Member(String name, boolean active) {
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
~~~

Prepare the data and context:

~~~java
List<Member> members = new ArrayList<>();
members.add(null);
members.add(new Member("Ana", true));
members.add(new Member("Mark", false));
members.add(new Member("Mila", true));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#members?.?[#this != null && #this.active]"
);

Object result = expression.getValue(context);
~~~

The result is a collection containing Ana and Mila.

If members is changed to null and the same expression is re-evaluated, the result is null. If replaced with an empty list, the result is an empty collection.

## 13. Common misconceptions

**Misconception 1: Null-safe selection uses the syntax ?.[]**  
?.[] is null-safe indexing. Null-safe selection uses ?.?[condition].

**Misconception 2: Null-safe selection also protects null elements.**  
It protects the source collection. If elements may be null, the predicate must guard property access on the element.

**Misconception 3: A null collection and an empty collection produce the same result.**  
A null collection causes null-safe selection to return null; an empty collection returns an empty collection.

**Misconception 4: Elvis catches selection errors.**  
Elvis handles a null value, not exceptions raised when a predicate or element access fails.

**Misconception 5: After selection, you can call a method immediately without checking null.**  
If the source is null, the selection result is null. Subsequent steps in a compound expression still need null-safe navigation if they may receive null.

## 14. Key takeaways

- Selection filters collection elements according to a predicate.
- Standard selection uses ?[condition].
- Null-safe selection uses ?.?[condition] and is supported starting in Spring Framework 6.2.
- ?.[] is the null-safe indexer for reading an element by index or key, not null-safe selection.
- Selection on a map creates a new map consisting of matching entries; the predicate can use key and value.
- Null-safe selection protects the source collection, not automatically null elements inside the collection.
- A null collection yields null; an empty collection or no matching elements yields an empty collection for full selection.
- First/last selection returns the selected element, so the case where no element is found must be handled.
- When chaining property or method calls, use null-safe navigation at each position that may be null.

When writing null-safe selection, determine whether the source collection may be null, whether elements may be null, which properties the predicate needs to read, and how the rest of the expression will handle a null result.
