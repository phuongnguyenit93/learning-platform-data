# Null-Safe Navigation with the ?. Operator in SpEL

In Spring Expression Language (SpEL), the null-safe navigation operator ?. allows accessing a property or calling a method when the receiving object may be null. If the receiver of the operation is null, SpEL returns null for that operation instead of throwing a NullPointerException at the access point.

This operator is useful when working with multi-layered object graphs, incomplete request data, query results that may be absent, or optional properties. However, ?. only protects the operation it immediately precedes. In a compound expression, subsequent steps are still evaluated; therefore, you must place the null-safe operator at every link that can be null.

## 1. Objectives and prerequisites

After this lesson, you can:

- Distinguish standard dot property access from null-safe navigation with ?.
- Use the null-safe operator for properties and methods.
- Protect every layer in a nested property path.
- Combine null-safe navigation with Elvis, comparisons, and conditional expressions.
- Recognize null-safe indexing, selection, and projection forms in Spring Framework 6.2 and later.
- Distinguish a null object from an empty collection, invalid index, and exceptions from methods.
- Test null behavior and choose default handling appropriate for business rules.

You should be familiar with Java objects, getters, methods, collections, SpEL variables with the # prefix, and evaluating an Expression using EvaluationContext.

## 2. The problem when accessing objects that may be null

Suppose there are the classes:

~~~java
class Person {
    private Address address;

    public Address getAddress() {
        return address;
    }
}

class Address {
    private String city;

    public String getCity() {
        return city;
    }
}
~~~

If person exists and address also exists, the expression accessing city works:

~~~text
#person.address.city
~~~

However, if person or address is null, a standard property access operation can raise an evaluation error. This is a common situation when data comes from forms, APIs, databases, or an object graph with many optional properties.

You can handle this with null checks, but expressions become verbose when paths have many layers. Null-safe navigation provides a shorter syntax and directly expresses that a branch may not exist.

## 3. Basic syntax of ?.

Standard dot:

~~~text
#person.address
~~~

Null-safe navigation:

~~~text
#person?.address
~~~

If person is null, the second expression returns null for the address access. If person exists, SpEL reads the address property normally.

It can be used with methods:

~~~text
#person?.getAddress()
~~~

If person is null, the getAddress() method is not called and the operation returns null. If person exists, the method is invoked via the EvaluationContext's method resolver mechanism.

Example in Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#person?.name");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("person", null);

Object result = expression.getValue(context);
~~~

The result is null. If person is replaced with an object that has a name property, the expression returns the value of that property.

Null-safe navigation does not create a replacement object and does not automatically assign a default value. It only makes the operation on a null receiver return null.

## 4. Protecting each layer of a property path

A very important point is that ?. does not automatically make the rest of a compound expression null-safe.

Example:

~~~text
#person?.address.city
~~~

The ?. operator protects reading address on person. If person is null, that operation returns null; the .city part afterward is still a step in the compound expression and can still be evaluated on the null result.

Therefore, when both person and address can be null, write:

~~~text
#person?.address?.city
~~~

How to read it:

1. If person is null, the result of the first step is null.
2. If person exists, read address.
3. If address is null, the second step returns null.
4. If address exists, read city.

You can apply the same principle across multiple layers:

~~~text
#order?.customer?.profile?.displayName
~~~

Each ?. protects the receiver of the next operation. Place it at every boundary where data may be null, instead of placing it only once at the start of the path.

### 4.1. Comparison with explicit null checks

Explicit form:

~~~text
#person != null and
#person.address != null and
#person.address.city != null
~~~

Safe navigation form:

~~~text
#person?.address?.city != null
~~~

The second form is shorter and focuses on the property path. However, if business rules need to distinguish person not existing, address not existing, and city not existing, explicit conditions may be clearer to express.

Do not shorten an expression merely to reduce character count if doing so loses the business meaning of each null state.

## 5. Null-safe navigation with methods

You can call a method on an object that may be null:

~~~text
#customer?.getDisplayName()
~~~

If customer is null, the method is not called and the result is null. If customer exists, SpEL invokes the method and receives the return value.

If the method exists but itself returns null, a subsequent operation still needs protection:

~~~text
#customer?.getProfile()?.getDisplayName()
~~~

Here there are two distinct cases:

- customer is null: getProfile() is not called.
- customer exists, but getProfile() returns null: the getDisplayName() operation is protected by the second ?.

The operator does not catch or hide exceptions thrown by the method. If the method is invoked and throws an exception, the error can still surface during evaluation. Null-safe navigation also does not check whether a method has side effects; prefer read-only methods with predictable results.

## 6. Combining with Elvis to supply default values

Null-safe navigation typically returns null when the receiver is null. If the application needs a fallback value, you can combine it with the Elvis operator ?:.

Example:

~~~text
#person?.name ?: 'Anonymous'
~~~

If person is null or name is null, the result is Anonymous. If name has a non-null value, the result is that name.

A multi-layer property path:

~~~text
#order?.customer?.profile?.displayName ?: 'Guest'
~~~

Elvis helps handle null at the end of the expression and provides a concise default value.

Choose a default that matches the business meaning. For example, replacing null with 0 can cause undetermined data to be mistaken for a value of 0. For critical data, you may need to report a validation error instead of silently substituting.

### 6.1. Distinguishing ?. and ?:

The two operators serve different purposes:

| Operator | Role |
|---|---|
| ?. | Protects a property access or method call when the receiver is null |
| ?: | Chooses a fallback value when the left-hand expression is null |

You can combine them:

~~~text
#customer?.address?.city ?: 'Unknown'
~~~

The ?. handles null receivers along the path; Elvis supplies the default value if the final result is null.

## 7. Combining with comparisons and logical operators

Null-safe results can be used in conditions. Example:

~~~text
#customer?.status == 'ACTIVE'
~~~

If customer is null, the property expression returns null and comparing with the string ACTIVE does not evaluate to true. However, if you need to clearly distinguish null from an invalid status, check explicitly.

Example checking status and permissions:

~~~text
#customer?.status == 'ACTIVE' and #user?.enabled == true
~~~

Both sides must be true. You can use Elvis to provide a default boolean value:

~~~text
(#user?.enabled ?: false) and (#customer?.verified ?: false)
~~~

This treats null as false. Only use it when that is the desired business rule.

### 7.1. Combining with short-circuiting

AND and OR can stop evaluating once the result is determined. You can use a guard on the left-hand side:

~~~text
#person != null and #person.address?.city == 'Hanoi'
~~~

If person is null, the right-hand side is skipped. If person exists, address?.city protects the case where address is null.

When using safe navigation, there is no need to add a guard for the same receiver if the operator already protects the operation. However, keep an explicit condition if it carries business meaning beyond null safety.

## 8. Null-safe indexing, selection, and projection

Spring Framework 6.2 adds null-safe forms for collection and index operations. These syntaxes require the right version; if the project is running Spring Framework prior to 6.2, the parser may not support them.

### 8.1. Null-safe indexing

Syntax:

~~~text
#members?.[0]
~~~

If members is null, the result is null instead of attempting index access. If members exists, SpEL performs index 0 access normally.

It can be combined with null-safe navigation on the element:

~~~text
#members?.[0]?.name
~~~

Here there are two separate null boundaries:

- The members collection may be null.
- The element at index 0 may be null.

Null-safe indexing only protects the collection receiver. It does not turn an out-of-range index into a valid index; if the collection exists but is empty, accessing index 0 can still fail. If you need to handle empty collections, check size or use appropriate logic before fetching an element.

For a Map, you can use null-safe indexing to protect the map receiver when accessing a key:

~~~text
#settings?.['theme']
~~~

A nonexistent key and a null map are two different situations. How a missing key is handled depends on the Map/accessor and the application's default policy.

### 8.2. Null-safe selection

Selection filters elements satisfying a condition. Null-safe form in Spring Framework 6.2 and later:

~~~text
#members?.?[active == true]
~~~

If members is null, the selection operation returns null. If the collection exists, SpEL filters elements according to the predicate.

You can combine with Elvis if you want the resulting collection to default to an empty collection, but choose the right default type and value. Do not treat a null collection as equivalent to an empty collection by default if the two states carry different meanings.

### 8.3. Null-safe projection

Projection creates a result collection by applying an expression to each element. Null-safe form:

~~~text
#members?.![displayName]
~~~

If members is null, the projection operation returns null. If the collection exists, SpEL builds the result from each element's displayName.

If elements inside the collection can be null, protect the element's property inside the projection when needed:

~~~text
#members?.![#this?.displayName]
~~~

Null-safe projection protects the collection receiver; safe navigation inside the projection expression protects the current element.

## 9. Distinguishing null from empty collections and invalid indexes

Null-safe navigation is not a mechanism for handling every case of missing data.

| Situation | Meaning | How to handle |
|---|---|---|
| Receiver is null | No object to perform the operation on | Use ?. or check for null |
| Empty collection | Collection exists but has no elements | Check size/isEmpty before accessing an index |
| Index out of range | Collection has elements, but requested index is invalid | Check size or use appropriate control flow |
| Map missing key | Map exists but has no entry for that key | Check containsKey or use an explicit default |
| Method throws exception | Method was invoked but execution failed | Handle exception per the method contract |
| Property does not exist | Object structure or property name is wrong | Check model and accessor |

For example, the expression:

~~~text
#items?.[0]
~~~

protects the case where items is null. It does not protect the case where items is an empty List. To safely get the first element, check that the collection has elements before reading the index.

## 10. Null-safe navigation is not auto grow

These two mechanisms have opposite purposes:

- Null-safe navigation returns null when the receiver is null, allowing the expression to continue per evaluation rules.
- Auto grow null references can create intermediate objects when the parser is configured appropriately and the object type can be instantiated.

Safe navigation example:

~~~text
#person?.address?.city
~~~

If person is null, the expression does not create a new Person or Address.

Auto grow is a separate parser configuration:

~~~java
SpelParserConfiguration configuration =
    new SpelParserConfiguration(true, false);

ExpressionParser parser =
    new SpelExpressionParser(configuration);
~~~

If the use case needs to update an object graph, examine auto grow and property write conditions. If only reading optional data, safe navigation is usually more appropriate. Do not use the null-safe operator expecting it to auto-create objects for writing.

## 11. Evaluating with Java and EvaluationContext

Complete example with a variable:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#person?.address?.city ?: 'Unknown'");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("person", null);

String city = expression.getValue(context, String.class);
~~~

The result is Unknown.

If person has an address and city, the expression returns the city name. If person exists but address is null, the expression also returns Unknown because every layer is protected.

When passing data from requests or users, pass it via strongly typed variables or root objects. Avoid concatenating input into SpEL strings to construct arbitrary property paths or syntax.

## 12. Testing and debugging

Test at least the following cases:

| Case | Data | Result to verify |
|---|---|---|
| Receiver exists | person has name | Returns name |
| Receiver is null | person = null | Null-safe property returns null |
| Middle layer is null | person exists, address = null | address?.city returns null |
| Final value is null | address exists, city = null | Result is null |
| Elvis default | person = null | Returns default value |
| Method receiver is null | service/object = null | Method is not called |
| Collection is null | members = null | Null-safe index/selection/projection returns null on supported versions |
| Empty collection | members = [] | Index 0 is still invalid; handle separately |
| Null element | members has null at index 0 | Requires null-safe navigation on element |
| Method throws exception | receiver exists | Exception still propagates per evaluate behavior |

When debugging, break the expression down step by step:

1. Confirm whether the variable or root object exists.
2. Check each property path and positions that may be null.
3. Add ?. properly at receivers that can be null.
4. Check empty collections and indexes separately.
5. Add Elvis or default conditions if business logic requires them.
6. Re-verify results with a complete object, a null object, and objects missing each layer.

If null-safe indexing/selection/projection syntax fails to parse, check the running Spring Framework version before altering the expression.

## 13. Common mistakes

| Symptom | Common cause | Resolution |
|---|---|---|
| Still fails on a later property | ?. only on the first layer, later layer can still be null | Use ?. at every nullable link |
| Result is null instead of default string | Missing Elvis or default logic | Combine ?: when appropriate |
| Index still fails despite null-safe index | Collection exists but is empty or index is out of range | Check size before accessing |
| Element property still fails | Collection contains null elements | Use safe navigation on #this or the element |
| Method still throws exception | Method was invoked and threw exception itself | Handle exception per method contract |
| Parser rejects ?.[] or ?.?[...] syntax | Using Spring Framework prior to 6.2 | Check dependency version or use compatible guards |
| Object not created when receiver is null | Safe navigation only returns null, does not auto grow | Use auto grow parser configuration for appropriate write use cases |

## 14. Practice exercises

1. Create Person with Address and City; evaluate #person?.address?.city when person exists, is null, and has a null address.
2. Write an expression that returns Anonymous if name is null using Elvis.
3. Call a method via null-safe navigation and verify the method does not run when the receiver is null.
4. Compare #person?.address.city with #person?.address?.city when person is null and address is null.
5. On Spring Framework 6.2+, test null-safe indexing with a null List and an empty List.
6. Test null-safe selection and projection; distinguish a null collection from an empty collection.
7. Create a collection with a null element and protect the element's property in a projection.
8. Compare safe navigation with auto grow null references in a read use case and an update use case.

## 15. Checklist before using in an application

- [ ] Identified which receivers can be null?
- [ ] Placed ?. at every nullable layer in compound expressions?
- [ ] Distinguished null from empty collections and out-of-range indexes?
- [ ] Protected collection elements if elements can be null?
- [ ] Chosen defaults with Elvis according to business rules?
- [ ] Understood that methods can still throw exceptions when the receiver exists?
- [ ] Checked Spring version if using null-safe indexing/selection/projection?
- [ ] Distinguished safe navigation from auto grow?
- [ ] Tested null layers and boundary data?
- [ ] Passed data through strongly typed contexts?

## 16. Conclusion

The ?. operator helps SpEL access properties or invoke methods safely when the receiver may be null. In compound expressions, protect every nullable layer because subsequent steps are still evaluated. Elvis ?: can supply default values, while null-safe indexing, selection, and projection require Spring Framework 6.2 or later. Always distinguish null objects from empty collections, invalid indexes, and exceptions from methods. Use safe navigation for optional data-reading flows; if you need to create objects for updates, consider the separate auto grow mechanism.