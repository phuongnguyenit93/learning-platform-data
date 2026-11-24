# First selection .^[] and last selection .$[] in SpEL

Spring Expression Language (SpEL) provides selection operators to find elements in a list, array, or map based on a Boolean condition. Standard selection `.?[condition]` returns all matching elements. When only the first or last result is needed, you can use **first selection** `.^[condition]` and **last selection** `.$[condition]`.

These two operators keep expressions concise when finding a single element by criteria. However, "first" and "last" depend on the iteration order of the collection; they do not automatically sort data by a property.

## 1. Three forms of selection to distinguish

| Operator | Meaning | Result |
|---|---|---|
| `.?[condition]` | Get all elements matching the condition | Collection containing matching elements |
| `.^[condition]` | Get the first matching element | A single element, or null if not found |
| `.$[condition]` | Get the last matching element | A single element, or null if not found |

Example with a list:

    #members.?[nationality == 'Serbian']
    #members.^[nationality == 'Serbian']
    #members.$[nationality == 'Serbian']

The first expression returns all members with Serbian nationality. The second expression returns the first member matching the condition, and the third expression returns the last member matching the condition.

The predicate syntax sits inside square brackets. The predicate must evaluate to a Boolean; if the inner expression returns another type, SpEL reports an evaluation error rather than guessing true/false.

## 2. First selection on List and Iterable

For a List or an object implementing `java.lang.Iterable`, SpEL evaluates the predicate sequentially on each element. First selection stops when it finds the first matching element and returns that element itself.

Example:

    List<Inventor> members = List.of(
            new Inventor("Nikola Tesla", "Serbian"),
            new Inventor("Thomas Edison", "American"),
            new Inventor("Mihajlo Pupin", "Serbian")
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("members", members);

    ExpressionParser parser = new SpelExpressionParser();

    Inventor firstSerbian = parser.parseExpression(
            "#members.^[nationality == 'Serbian']"
    ).getValue(context, Inventor.class);

The result is Nikola Tesla because that is the first element in the list with `nationality` equal to `'Serbian'`.

In the predicate, properties can be accessed directly on the current element:

    #members.^[nationality == 'Serbian']

Or use `#this` to make the object being examined explicit:

    #members.^[#this.nationality == 'Serbian']

Both ways express the same condition. When a predicate has multiple operations or is nested, `#this` helps readers see that the property belongs to the current element.

## 3. Last selection on List and Iterable

Last selection continues iterating through the collection to find the last matching element. The result is a single element, not a List containing only one element:

    Inventor lastSerbian = parser.parseExpression(
            "#members.$[nationality == 'Serbian']"
    ).getValue(context, Inventor.class);

With the list in the example above, the result is Mihajlo Pupin. If multiple elements satisfy the condition, only the last matching element is returned.

Difference in traversal:

- First selection can stop as soon as it encounters the first matching element.
- Last selection needs to traverse the entire collection to know which matching element appears last.

Therefore, if a collection is large and matching elements usually appear early, first selection can avoid scanning the remaining elements. Last selection has to keep checking until the end.

## 4. Selection on Array

SpEL also supports selection on arrays. The predicate is evaluated for each element in array index order:

    String[] roles = {"GUEST", "EDITOR", "ADMIN", "EDITOR"};

    context.setVariable("roles", roles);

    String firstEditor = parser.parseExpression(
            "#roles.^[#this == 'EDITOR']"
    ).getValue(context, String.class);

    String lastEditor = parser.parseExpression(
            "#roles.$[#this == 'EDITOR']"
    ).getValue(context, String.class);

Both results are the string `'EDITOR'`, but they correspond to two different positions in the array. If you need to determine the index of the found element, first/last selection does not return the index; use a loop or process the collection in Java when both position and value are needed.

## 5. Selection on Map

For a Map, the predicate is evaluated on each entry of type `Map.Entry`. Inside the predicate, two special properties can be accessed:

- `key`: the key of the current entry.
- `value`: the value of the current entry.

Example:

    #scores.?[value >= 80]
    #scores.^[value >= 80]
    #scores.$[value >= 80]

Standard selection returns a Map containing all matching entries. First selection and last selection return a Map containing only the first or last matching entry, rather than returning the entry's value directly.

Example with an ordered Map:

    Map<String, Integer> scores = new LinkedHashMap<>();
    scores.put("Lan", 75);
    scores.put("Minh", 92);
    scores.put("An", 88);

    context.setVariable("scores", scores);

    Map<?, ?> firstPassed = parser.parseExpression(
            "#scores.^[value >= 80]"
    ).getValue(context, Map.class);

The result is a single-entry Map: `{"Minh": 92}`. If you need to retrieve the value separately, you can access a known key or process the result Map in Java. With a single-entry Map, you should not assume ordering or how an element is extracted from an arbitrary Map implementation if the application requires general handling.

To search by key, the predicate can use:

    #scores.^[key == 'Minh']

To search by both key and value:

    #scores.$[key != 'Lan' and value >= 80]

## 6. "First" and "last" depend on iteration order

First/last selection does not mean finding the minimum/maximum value. It only selects the first or last element in the collection's iteration order after applying the predicate.

For common data structures:

| Collection type | Order used to determine first/last |
|---|---|
| List | Index order from start to end |
| Array | Index order from 0 to length - 1 |
| LinkedHashSet | Insertion order |
| TreeSet | Comparator order |
| LinkedHashMap | Iteration order by insertion |
| TreeMap | Order by key comparator |
| HashSet / HashMap | Should not rely on stable iteration order |

If you need the element with the earliest timestamp, highest score, or largest value, sort the collection by that criterion before using first/last selection, or compute the result in Java. For example, `members.$[score > 80]` does not find the person with the highest score; it only finds the person satisfying the condition who appears last in iteration order.

For HashMap or HashSet, iteration order is not guaranteed to follow insertion. Thus, first/last results may be unsuitable if business logic requires determinism. Use a collection with a clear order or prepare the data before evaluation.

## 7. No matching element found

With first selection and last selection, if no element satisfies the predicate, the result is null. This differs from all-match selection `.?[...]`, which returns an empty collection when no element matches.

Example:

    Inventor selected = parser.parseExpression(
            "#members.^[nationality == 'Martian']"
    ).getValue(context, Inventor.class);

If no member matches, `selected` is null. Check for null before accessing subsequent properties:

    #members.^[nationality == 'Serbian']?.name

Safe navigation on the selected result helps avoid errors when no matching element is found. You can use the Elvis operator to provide a default value:

    #members.^[nationality == 'Serbian']?.name ?: 'Unknown'

In the example above, if no member is found or the name is null, the expression returns `'Unknown'`.

Distinguish two cases: a collection with no matching elements and an initial collection that is null. Standard selection on a null target will cause an evaluation error. Null-safe selection operators such as `?.^` and `?.$` are supported starting in Spring Framework 6.1.6; they allow the expression to return null when the target collection is null:

    #members?.^[nationality == 'Serbian']
    #members?.$[nationality == 'Serbian']

If the Spring version in use does not yet support null-safe selection syntax, check the collection beforehand in Java or in the expression using an appropriate condition.

## 8. Combining first/last selection with properties and methods

The result of first/last selection can continue to be used to read properties or call methods:

    #members.^[nationality == 'Serbian']?.name
    #members.$[nationality == 'Serbian']?.getDisplayName()

You can continue accessing deeper if an object is found:

    #orders.^[status == 'PAID']?.customer?.email

This expression finds the first paid order, then retrieves the customer's email. Safe navigation handles the case where no order is found or customer is null. If the method being called has side effects, remember that each evaluation of the Expression may execute that call.

Selection can be combined with projection. For example, after finding the first matching element, get a property from the result:

    #members.^[active]?.department

Projection `.![...]` is typically used when each element in a collection needs to be transformed; first/last selection only picks a single matching element.

## 9. Checking predicates and performance

A selection predicate needs to return a Boolean. Common comparison expressions include `==`, `!=`, `>`, `>=`, `<`, and `<=`. Conditions can be combined with `and`, `or`, `not`, and parentheses:

    #orders.^[
        status == 'PAID' and
        total >= 100 and
        customer.active
    ]

With complex predicates, use parentheses and clear indentation. If a predicate calls a method, ensure the method has appropriate characteristics when invoked multiple times across elements.

First selection stops at the first matching element; last selection needs to traverse the entire source to determine the final result. Both evaluate the predicate element by element until a result is obtained or the collection ends. Do not use selection to replace a large database query if the filter condition can be pushed down to the repository layer.

## 10. Complete example in Java

The example below finds the first and last active members in a list:

    public class Member {
        private String name;
        private boolean active;

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

    List<Member> members = List.of(
            new Member("Lan", false),
            new Member("Minh", true),
            new Member("An", true)
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("members", members);

    ExpressionParser parser = new SpelExpressionParser();

    Member firstActive = parser.parseExpression(
            "#members.^[active]"
    ).getValue(context, Member.class);

    Member lastActive = parser.parseExpression(
            "#members.$[active]"
    ).getValue(context, Member.class);

The `firstActive` result is Minh, and `lastActive` is An. The example shows both operators using the same predicate while picking elements at two different positions in the list order.

In unit tests, cover at least these cases: first element matches, multiple elements match, only the last element matches, no element matches, empty collection, and null collection. For Maps, verify key, value, and the iteration order of the implementation used.

## 11. Key takeaways

Use `.^[condition]` to get the first matching element and `.$[condition]` to get the last matching element. For List, Iterable, and array, the result is the selected element; for Map, the result is a Map containing the selected entry. If no element matches, first/last selection returns null, whereas all-match selection returns an empty collection. The result depends on the source's iteration order and does not automatically find min/max. Check for null, choose a collection with deterministic order when stable results are required, and use selection in SpEL for collections already present in the context.
