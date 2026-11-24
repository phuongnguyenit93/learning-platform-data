# Testing Selection, Projection, and Null-Safe Navigation in SpEL

Spring Expression Language (SpEL) provides selection and projection operations to filter or transform elements in a collection. Null-safe navigation helps expressions handle objects or collections that may be null without raising null-access errors at the guarded location.

These features frequently appear together in expressions reading nested data. Therefore, tests need to confirm not only the return value, but also collection shape, element order, behavior with null elements, null collections, and null intermediate properties. This lesson presents how to construct tests with clear data to verify those behaviors.

## 1. Objectives and prerequisites

After this lesson, you will be able to:

- Test selection using the .?[], .^[], and .$[] operators.
- Test projection using the .![] operator.
- Confirm selection retains source elements while projection builds a result collection.
- Test selection and projection on List and Map.
- Test null-safe property navigation using the ?. operator.
- Test null-safe selection and projection on Spring Framework 6.2 and later.
- Distinguish null collections, empty collections, and collections containing null elements.
- Check nested properties that may be null at each level.
- Write unit tests for values, result types, order, and runtime errors.
- Use compatible guards when the application runs on a Spring version that does not support null-safe collection operators.

You should know how to create SpelExpressionParser, Expression, EvaluationContext, JavaBean properties, and collection operations in SpEL.

## 2. What do selection and projection need to test?

Selection filters collection elements by a predicate. Projection applies an expression to each element and collects the produced values into a result collection.

| Operation | Syntax | Typical result |
|---|---|---|
| Selection of all matching elements | .?[condition] | Collection containing the retained original elements |
| Selection of first matching element | .^[condition] | First element matching the condition |
| Selection of last matching element | .$[condition] | Last element matching the condition |
| Projection | .![expression] | Collection containing expression results for each element |

Example:

~~~text
#members.?[active]
~~~

filters members where active is true.

~~~text
#members.![name]
~~~

extracts the name of each member and builds a result collection.

With a source List, selection keeps the matching original objects and projection creates a List of values. With a Map, selection keeps matching entries and returns a Map; projection evaluates on each Map.Entry and returns a result List. Tests should verify this exact type and structure instead of checking only a display string.

## 3. Preparing test data

Use a small fixture with easily recognizable names and states. Example:

~~~java
public class Member {
    private final String name;
    private final boolean active;
    private final Address address;

    public Member(String name, boolean active, Address address) {
        this.name = name;
        this.active = active;
        this.address = address;
    }

    public String getName() {
        return name;
    }

    public boolean isActive() {
        return active;
    }

    public Address getAddress() {
        return address;
    }
}

public class Address {
    private final String city;

    public Address(String city) {
        this.city = city;
    }

    public String getCity() {
        return city;
    }
}

public class MemberInput {
    private final List<Member> members;

    public MemberInput(List<Member> members) {
        this.members = members;
    }

    public List<Member> getMembers() {
        return members;
    }
}
~~~

Creating data:

~~~java
Member an = new Member(
    "An", true, new Address("Hanoi"));

Member binh = new Member(
    "Binh", false, new Address("Da Nang"));

Member chi = new Member(
    "Chi", true, null);

MemberInput input =
    new MemberInput(List.of(an, binh, chi));
~~~

This fixture has:

- Two active members and one inactive member.
- The address property with both non-null and null cases.
- Data small enough to read the expected result clearly.
- Deterministic element order to test first/last selection and projection order.

For null-element tests, do not use List.of because this factory does not accept null elements. You can use Arrays.asList or an ArrayList that can hold null.

## 4. Creating the parser and evaluating expressions in tests

One parser can be used to parse expressions in each test:

~~~java
private final ExpressionParser parser =
    new SpelExpressionParser();
~~~

Example reading a collection from the root object:

~~~java
Expression expression =
    parser.parseExpression("members.?[active]");

List<?> result =
    expression.getValue(input, List.class);
~~~

The members property is read from the MemberInput root object. Inside the predicate, the active property is resolved on the current element.

If using a variable instead of a root property, register the variable in the context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("members", members);

List<?> result = parser
    .parseExpression("#members.?[active]")
    .getValue(context, List.class);
~~~

Use the same way of supplying data within each test group so results are easy to understand. When needing to test a null collection, use a root DTO whose property returns null or a nullable wrapper. With StandardEvaluationContext, setVariable(name, null) may remove the variable name from the context, so do not use that approach to simulate a registered variable with a null value.

## 5. Testing selection on a List

Expression example:

~~~text
members.?[active]
~~~

The test can confirm only active members are retained:

~~~java
@Test
void selectsOnlyActiveMembers() {
    List<?> result = parser
        .parseExpression("members.?[active]")
        .getValue(input, List.class);

    assertThat(result)
        .extracting("name")
        .containsExactly("An", "Chi");
}
~~~

Things to verify:

- The number of result elements is right.
- Elements are retained properly according to the predicate.
- Order matches the source collection order.
- Selection returns the source objects, rather than creating new objects for each element.

Also include the case where no elements satisfy the condition. With a non-empty List source where the predicate is always false, the result is an empty List, not null.

## 6. Testing first and last selection

SpEL has two useful selection variants:

~~~text
members.^[active]
~~~

~~~text
members.$[active]
~~~

The first expression picks the first element matching the predicate; the second picks the last element matching the predicate.

With the An, Binh, Chi fixture:

- First selection returns An.
- Last selection returns Chi.

Test:

~~~java
@Test
void selectsFirstAndLastMatchingMembers() {
    Member first = parser
        .parseExpression("members.^[active]")
        .getValue(input, Member.class);

    Member last = parser
        .parseExpression("members.$[active]")
        .getValue(input, Member.class);

    assertThat(first.getName()).isEqualTo("An");
    assertThat(last.getName()).isEqualTo("Chi");
}
~~~

Also test the case where no element matches. First/last selection can return null when no element is found; consuming code must handle that case.

Do not confuse first/last selection with sorting the collection. They are based on the iteration order of the source collection.

## 7. Testing projection on a List

Projection applies an expression to each element:

~~~text
members.![name]
~~~

Test:

~~~java
@Test
void projectsMemberNamesInSourceOrder() {
    List<?> names = parser
        .parseExpression("members.![name]")
        .getValue(input, List.class);

    assertThat(names)
        .containsExactly("An", "Binh", "Chi");
}
~~~

Verify:

- The number of results equals the number of source elements.
- Each result corresponds to the exact element.
- Order is preserved according to the source collection.
- The type of each value matches the expression.
- Projection does not automatically drop an element just because the returned value is null.

Example of projection on a nullable property:

~~~text
members.![address?.city]
~~~

For member Chi with a null address, the result at the corresponding position is null. Projection still produces a result element for that member.

If you want to exclude null results, combine an explicit selection condition followed by projection:

~~~text
members.?[address != null].![address.city]
~~~

Tests must accurately reflect business requirements: whether to keep null at the corresponding position or filter out source elements before projection.

## 8. Testing selection combined with projection

An expression can filter first and then transform:

~~~text
members.?[active].![name]
~~~

Selection keeps active members; projection extracts the name of the remaining members.

Test:

~~~java
@Test
void selectsThenProjectsNames() {
    List<?> names = parser
        .parseExpression("members.?[active].![name]")
        .getValue(input, List.class);

    assertThat(names)
        .containsExactly("An", "Chi");
}
~~~

Verify the order of operations. If projection runs first, the expression may no longer have the object or property needed for the subsequent predicate.

With nested properties, members having an address can be filtered before extracting city:

~~~text
members.?[address != null].![address.city]
~~~

Write a separate test for a member with a null address to confirm selection properly excludes the element before projection accesses city.

## 9. Testing selection and projection on a Map

With a Map, the selection predicate runs on Map.Entry. Both key and value can be accessed:

~~~text
#scores.?[value >= 70]
~~~

Selection keeps matching entries and returns a Map.

Projection:

~~~text
#scores.![key]
~~~

returns a List of keys. Projection on a Map does not return a Map because each entry is transformed into a single value.

Test example:

~~~java
@Test
void selectsMapEntriesAndProjectsKeys() {
    Map<String, Integer> scores = new LinkedHashMap<>();
    scores.put("An", 80);
    scores.put("Binh", 60);
    scores.put("Chi", 90);

    StandardEvaluationContext context =
        new StandardEvaluationContext();
    context.setVariable("scores", scores);

    Map<?, ?> selected = parser
        .parseExpression("#scores.?[value >= 70]")
        .getValue(context, Map.class);

    List<?> keys = parser
        .parseExpression("#scores.?[value >= 70].![key]")
        .getValue(context, List.class);

    assertThat(selected).containsKeys("An", "Chi");
    assertThat(keys).containsExactly("An", "Chi");
}
~~~

Use LinkedHashMap when order is part of the expected result. HashMap does not guarantee stable iteration order, so do not write tests requiring a specific order on a HashMap.

## 10. Null-safe navigation on properties

The ?. operator guards property access or method invocation when the receiver may be null.

Example:

~~~text
member.address?.city
~~~

If address is null, the expression returns null instead of attempting to read city on null. However, member must still exist; if member can also be null, guard that level too:

~~~text
#this?.address?.city
~~~

Tests should include fixtures for:

- Non-null member, non-null address, city has a value.
- Non-null member, null address.
- Null member.
- Non-null address, null city.

Null-safe navigation only guards the receiver immediately before the ?. operator. Do not assume a single ?. at the start of a path will guard every intermediate object after it.

## 11. Null-safe selection and projection since Spring Framework 6.2

Spring Framework 6.2 adds null-safe collection selection and projection. The syntax uses ?. immediately before the collection operator:

~~~text
members?.?[active]
~~~

~~~text
members?.![name]
~~~

If the collection receiver is null, the null-safe operation returns null instead of throwing an error from performing selection/projection on null.

This differs from an empty collection:

- Null collection: result is null when using a null-safe collection operator.
- Empty collection: selection/projection runs on the empty collection and returns an empty result collection.
- Populated collection: the operation runs on each element.

Tests should confirm these three distinct states. Do not assume null-safe selection turns null into an empty list.

### 11.1. Guarding elements and nested properties

A null-safe collection operator only guards the collection receiver. It does not automatically guard individual null elements or null intermediate properties.

Example:

~~~text
members?.![#this?.address?.city]
~~~

Here:

- members?. guards the source collection.
- #this?. guards the current element if the element is null.
- address?. guards the address property if null.
- city is read when address exists.

Similarly, selection can be written as:

~~~text
members?.?[#this?.active == true]
~~~

If member is null, the predicate expression yields null on the comparison side and does not select that element.

## 12. Distinguishing null, empty, and null-element collections

These are three different fixtures and need separate tests.

| Fixture | Meaning | Expected result |
|---|---|---|
| members = null | No collection | Null-safe selection/projection returns null |
| members = empty list | Collection exists with no elements | Selection/projection returns empty List |
| members contains null | Collection has a null element | Predicate/projection needs to guard the element if accessing properties |

Example creating a collection with a null element:

~~~java
List<Member> membersWithNull =
    Arrays.asList(an, null, chi);
~~~

Selection without guarding elements:

~~~text
members.?[active]
~~~

can fail when the predicate accesses active on a null element.

Selection guarding elements:

~~~text
members.?[#this?.active == true]
~~~

Projection guarding elements and nested properties:

~~~text
members.![#this?.address?.city]
~~~

Testing these cases clearly distinguishes a null-safe receiver from a null-safe element.

## 13. Spring versions prior to 6.2

If the application uses a Spring version that does not yet support null-safe selection/projection on collections, do not use the ?. syntax before these operators.

The collection can be guarded using the conditional operator:

~~~text
members == null ? null : members.![name]
~~~

Or return an empty collection if that is the desired contract:

~~~text
members == null ? {} : members.![name]
~~~

With this choice, tests must confirm the explicit null policy: returning null or returning an empty collection. The two results carry different meanings.

Property null-safe navigation with ?. existed before null-safe collection operations; do not equate a version supporting ?.property with a version supporting ?.![...] or ?.?[...]. Check the actual Spring version before using the new syntax.

## 14. Verifying result types and shapes

Selection/projection tests should also verify the collection type:

| Source | Operation | Result shape |
|---|---|---|
| List | Selection | List of matching source objects |
| List | Projection | List of computed values |
| Map | Selection | Map of matching entries |
| Map | Projection | List of values computed from entries |
| Null collection with null-safe operation | Selection/projection | Null |
| Empty List | Selection/projection | Empty List |

Do not cast a Map selection result to a List or vice versa. If the Java API expects a specific type, use getValue(context, ExpectedType.class) and assert that type in the test.

For projections returning multiple value types or nested maps, check individual elements and important keys. Do not just check the collection's toString() because string formatting can hide the actual types and structure.

## 15. JUnit examples for null-safe navigation

The example below uses a root object with a members property so it can represent a null collection:

~~~java
@Test
void nullSafeProjectionReturnsNullForNullCollection() {
    MemberInput nullInput = new MemberInput(null);

    Object result = parser
        .parseExpression("members?.![name]")
        .getValue(nullInput);

    assertThat(result).isNull();
}
~~~

Testing an empty collection:

~~~java
@Test
void projectionReturnsEmptyListForEmptyCollection() {
    MemberInput emptyInput =
        new MemberInput(Collections.emptyList());

    List<?> result = parser
        .parseExpression("members?.![name]")
        .getValue(emptyInput, List.class);

    assertThat(result).isEmpty();
}
~~~

Testing null elements and nested properties:

~~~java
@Test
void projectionHandlesNullElementsAndNestedProperties() {
    List<Member> values =
        Arrays.asList(an, null, chi);

    MemberInput input = new MemberInput(values);

    List<?> cities = parser
        .parseExpression(
            "members?.![#this?.address?.city]")
        .getValue(input, List.class);

    assertThat(cities).containsExactly("Hanoi", null, null);
}
~~~

These tests only use null-safe collection operators when the application runs Spring Framework 6.2 or later. For older versions, use an appropriate guard expression or handle null collections in Java before evaluating.

## 16. Testing errors and unexpected behavior

Not every error involving selection/projection is a syntax error. An expression can parse successfully yet fail during evaluation.

Cases to check:

- Source collection is null when using a non-null-safe operation.
- Element is null and predicate accesses a property directly.
- Intermediate property is null without safe navigation.
- Property does not exist or getter is inaccessible.
- Predicate calls a disallowed method or the method throws an exception.
- Heterogeneous element types.
- Map value is null when predicate compares it numerically.
- Projection produces results of a type different from what Java code expects.

Tests should distinguish parse errors, evaluation errors, and empty business results. Do not catch all exceptions and return an empty collection because that can hide model or configuration errors.

## 17. Organizing the test suite with parameterized tests

JUnit parameterized tests can be used to run multiple fixtures through the same expression.

Example cases:

- List with both active and inactive members.
- Empty list.
- Null collection.
- List containing null elements.
- Null nested property.
- All elements failing the predicate.

Each test case should declare:

1. Input fixture.
2. Expression source.
3. Expected result type.
4. Expected value or exception.
5. Required version/capability if using new syntax.

Parameterized tests help ensure boundary cases run repeatedly whenever the model or expression changes. However, keep test names and data clear enough so that when a failure occurs, the fixture causing the error can be identified.

## 18. Common errors and how to handle them

| Symptom | Common cause | How to handle |
|---|---|---|
| Selection fails when collection is null | Using .?[] on a null receiver | Use null-safe selection on Spring 6.2+ or guard beforehand |
| Projection fails when collection is null | Using .![] on a null receiver | Use null-safe projection or a guard |
| Null-safe collection still fails on null elements | Only guarding the collection receiver | Use #this?.property in predicate/projection |
| Nested property still fails | An intermediate null level is unguarded | Place ?. on each receiver that could be null |
| Test expects empty list but gets null | Null-safe operations preserve null semantics | Explicitly define null vs empty and use a default if needed |
| Selection returns objects instead of values | Selection preserves source elements | Use projection if transformation is needed |
| Projection returns List instead of Map | Projection produces one result per entry | Use selection if key-value pairs must be preserved |
| Unstable order test | Using HashMap or a collection without guaranteed order | Use List/LinkedHashMap when order is part of the contract |
| Expression parses but evaluation fails | Incompatible data, property, or method | Check context and fixture |
| Null-safe collection syntax unsupported | Spring version older than 6.2 | Use a compatible conditional guard |

## 19. Practice exercises

1. Create a List of Members with active true/false and test selection .?[active].
2. Test first and last selection using .^[...] and .$[...].
3. Test projection .![name] and verify order.
4. Combine selection then projection to get active member names.
5. Create a Map<String, Integer>, select by value and project to get keys.
6. Create an empty collection and verify selection/projection results.
7. Create a root DTO with a null collection and test null-safe selection/projection.
8. Create a List containing null elements; compare a direct predicate against a predicate using #this?.
9. Create an object with a null address and test the property path address?.city.
10. Test nested projection with a null sub-collection and null sub-elements.
11. Write parameterized tests for null, empty, populated, and mixed states.
12. Run tests on the exact Spring version the application deploys.

## 20. Checklist before using selection, projection, and null-safe navigation

- [ ] Does selection filter the right elements according to the predicate?
- [ ] Does projection produce the right value for each element?
- [ ] Have List and Map results been distinguished?
- [ ] Does result order match the source collection?
- [ ] Have first/last selections been tested if used?
- [ ] Have null collections and empty collections been tested separately?
- [ ] Have collections with null elements been tested?
- [ ] Is every nullable intermediate property guarded?
- [ ] Has null-safe collection been distinguished from null-safe element?
- [ ] Is null-safe collection syntax used appropriately for Spring 6.2+?
- [ ] For older Spring versions, is a compatible conditional guard in place?
- [ ] Do tests verify result types, values, and exceptions?
- [ ] Are catch-all handlers that silently return an empty collection avoided?

## 21. Conclusion

Selection .?[] filters elements, .^[] and .$[] pick the first/last matching element, and projection .![] transforms each element into a result collection. Null-safe property navigation guards the receiver at each ?., while null-safe selection/projection on collections is supported starting in Spring Framework 6.2. Test null collections, empty collections, null elements, and null nested properties separately; confirm types, order, and result shapes. When running on older versions, use explicit guards instead of the new null-safe collection syntax.