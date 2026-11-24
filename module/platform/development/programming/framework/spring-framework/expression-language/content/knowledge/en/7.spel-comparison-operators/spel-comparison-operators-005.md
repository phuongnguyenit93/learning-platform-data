# Distinguishing Value Equality from Reference Identity

When using Spring Expression Language (SpEL), the **==** operator is often read as "equal". However, we must determine "equal" according to which rule. In Java, the **==** operator on two references checks whether they point to the same object (reference identity). Meanwhile, equality comparison in SpEL uses SpEL's equality rules; for ordinary objects, the comparison is based on **equals()**. These two checks can produce different results.

Clearly distinguishing these two concepts helps avoid bugs when writing authorization conditions, data filters, cache keys, event conditions, or other expressions containing objects.

## 1. What Are Value Equality and Reference Identity?

### Value equality — two objects whose values are considered equal

Value equality answers the question: do two values represent the same content or state as defined by the data type?

For example, two String objects created separately but containing the same content spring:

~~~java
String first = new String("spring");
String second = new String("spring");

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
~~~

equals() returns true because the two strings have the same content. The Java == operator returns false because the two variables reference two different objects.

### Reference identity — do two references point to the same object?

Reference identity answers the question: do two variables point to the exact same object in memory?

~~~java
String first = new String("spring");
String alias = first;

System.out.println(first.equals(alias)); // true
System.out.println(first == alias);      // true
~~~

Here both comparisons return true, because both references point to the same object and that object is also equal to itself according to equals().

In short, you can remember:

- **Value equality:** compares according to the equality rules of the data type.
- **Reference identity:** compares whether two references point to the same object.

## 2. The == and != Operators in SpEL

In SpEL, **==** and **!=** are equality and inequality operators. For ordinary objects, SpEL checks equality according to the object's equals() rules; this is not a reference identity check like Java's == operator.

Example:

~~~java
String first = new String("spring");
String second = new String("spring");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("first", first);
context.setVariable("second", second);

ExpressionParser parser = new SpelExpressionParser();

Boolean equal = parser
        .parseExpression("#first == #second")
        .getValue(context, Boolean.class);

Boolean notEqual = parser
        .parseExpression("#first != #second")
        .getValue(context, Boolean.class);

System.out.println(equal);    // true
System.out.println(notEqual); // false
~~~

Even though first and second are two different objects, the expression **#first == #second** returns true because the two strings are equal in content.

| Expression | Meaning | Result with two distinct String objects having the same content |
| --- | --- | --- |
| Java **first == second** | Reference identity | false |
| Java **first.equals(second)** | Value equality | true |
| SpEL **#first == #second** | Equality according to SpEL rules | true |
| SpEL **#first != #second** | Negation of equality | false |

Therefore, when reading an expression, do not automatically carry over the meaning of Java's == operator to SpEL.

## 3. Results Depend on How the Data Type Defines equals()

SpEL uses object equality, so the result depends on the equals() implementation of that class.

### 3.1. Types whose equals() compares content

Types such as String, BigInteger, BigDecimal, and many value object types implement equals() to compare values according to the type's own contract.

~~~java
String a = new String("order-100");
String b = new String("order-100");
~~~

The expression **#a == #b** returns true for these two strings, even though they are two different references.

For domain objects, equality can be intentionally defined based on business-meaningful fields:

~~~java
public final class CustomerKey {

    private final String value;

    public CustomerKey(String value) {
        this.value = value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CustomerKey that)) {
            return false;
        }
        return Objects.equals(this.value, that.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(value);
    }
}
~~~

Two separate CustomerKey instances with the same value will be considered equal according to the class's rules:

~~~java
context.setVariable("left", new CustomerKey("CUS-001"));
context.setVariable("right", new CustomerKey("CUS-001"));
~~~

The expression **#left == #right** returns true because equals() is defined to compare the customer key.

### 3.2. Types that do not override equals()

If a class does not override equals(), the implementation inherited from Object.equals() compares reference identity. In that case, two separate instances are generally not equal, even when their fields are identical.

~~~java
class Point {
    int x;
    int y;
}

Point p1 = new Point();
p1.x = 10;
p1.y = 20;

Point p2 = new Point();
p2.x = 10;
p2.y = 20;
~~~

With these two objects, the expression **#p1 == #p2** returns false because Point has not defined value-based equality. This is a case where SpEL equality matches the identity result, but the cause is Java's default equals() implementation.

If two points should be equal by coordinates, implement equals() and hashCode() appropriately, or use a data type that already defines value equality, such as a Java record:

~~~java
record Point(int x, int y) {}

Point p1 = new Point(10, 20);
Point p2 = new Point(10, 20);
~~~

A record automatically generates equals() and hashCode() based on its components. The two instances above are therefore considered equal by value, even though they remain two separate objects.

## 4. SpEL Does Not Provide a Dedicated Identity Operator

SpEL does not have a **===** operator equivalent to some other languages for checking whether two references point to the same object. Do not use **==** for identity checks when writing SpEL.

If the business logic truly needs an identity check, place the Java reference comparison inside an explicit method and call that method from the expression.

Helper example:

~~~java
public class ReferenceCheck {

    public boolean same(Object left, Object right) {
        return left == right;
    }
}
~~~

The helper can be registered as a Spring bean and referenced in the expression if the EvaluationContext has a BeanResolver:

~~~text
@referenceCheck.same(#left, #right)
~~~

Bean reference syntax requires the context to be connected to a Spring BeanFactory. If constructing a standalone StandardEvaluationContext, the helper can be registered as a context variable and the method called through that variable:

~~~java
context.setVariable("referenceCheck", new ReferenceCheck());

Boolean sameReference = parser
        .parseExpression("#referenceCheck.same(#left, #right)")
        .getValue(context, Boolean.class);
~~~

The expression above performs Java's == inside the same() method, so the result reflects reference identity.

Do not use System.identityHashCode() as a substitute for reference comparison. Identity hash codes can collide between two different objects, so comparing hash codes does not prove that two references have the same identity.

## 5. Points to Note When Equality Involves Multiple Data Types

### 5.1. SpEL may perform type conversion during comparison

When two operands do not have the same type, SpEL may use its type conversion mechanism to convert operands to compatible types before checking equality. Therefore, do not assume every comparison is equivalent to calling Java's equals() between two variables keeping their original types.

For numeric values of different numeric types, SpEL handles them according to the expression engine's numeric comparison and conversion rules. If business logic depends on the exact data type or representation, normalize types before comparing or call a Java method with a clear contract.

### 5.2. BigDecimal and scale

In Java, BigDecimal.equals() considers both numeric value and scale:

~~~java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

equals() distinguishes 10.0 from 10.00, whereas compareTo() considers them to have the same numeric value.

If the business logic wants to compare monetary or decimal values by numeric magnitude, express the intent clearly by normalizing scale or calling compareTo() in a helper:

~~~text
#left.compareTo(#right) == 0
~~~

This approach is appropriate when both operands are BigDecimal and non-null. If either can be null, check for null first or move the comparison into a null-safe Java method.

### 5.3. Null

SpEL supports comparing with null:

~~~text
#left == null
#left != null
#left == #right
~~~

Two null sides are considered equal; one null side and one non-null side are not equal. When needing to call methods like equals() or compareTo(), ensure the receiver object is non-null, or use appropriate safe navigation.

Example:

~~~text
#left != null and #left.equals(#right)
~~~

This condition checks that left is non-null before calling equals().

### 5.4. Collection and Map

Many collections and maps in Java define equals() by content. Therefore, two separate collections with the same elements in the appropriate order and equality rules can be considered equal by SpEL.

~~~java
context.setVariable("a", List.of("A", "B"));
context.setVariable("b", List.of("A", "B"));
~~~

The expression **#a == #b** returns true because List.equals() compares elements in order. Changing the element order to ["B", "A"] makes the result false.

Do not confuse two collections being equal by content with being the same instance. If identity is needed, use a Java helper as shown earlier.

## 6. Choosing the Comparison Matched to Your Purpose

| Need | Usage | Reason |
| --- | --- | --- |
| Compare string content | **#name == 'admin'** | String equality by content |
| Compare value objects | **#left == #right** | Uses equality defined by the class |
| Check inequality by equality rules | **#left != #right** | Negation of equality |
| Check for null object | **#value == null** | Comparison with null |
| Compare decimals by numeric value | **#left.compareTo(#right) == 0** | Explicitly expresses BigDecimal rule |
| Check for the same instance | **@referenceCheck.same(#left, #right)** | Helper using Java reference == |
| Compare collections by content | **#listA == #listB** | Relies on collection's equals() |

Choose the comparison based on business semantics:

- If you care about identifiers, names, statuses, or content, use value equality with a data type that has a proper equals().
- If you care about a specific object instance being shared or passed across multiple components, use reference identity via a Java method.
- If a data type has special comparison rules, such as BigDecimal, state the rule explicitly instead of relying on assumptions about the operator.

## 7. Applying in Spring Annotations

SpEL often appears in annotations, such as cache conditions or method security. Keep in mind that these annotations evaluate expressions in their own contexts, yet SpEL's equality rules must still be understood accurately.

### Cache

~~~java
@Cacheable(
    cacheNames = "customer",
    key = "#customerKey",
    condition = "#customerKey != null"
)
public Customer find(CustomerKey customerKey) {
    // ...
}
~~~

The condition above only checks that customerKey is not null. If using equality to compare one CustomerKey with another key, the result depends on CustomerKey's equals().

### Method Security

~~~java
@PreAuthorize("#requestedTenant == authentication.principal.tenantId")
public Invoice findInvoice(String requestedTenant) {
    // ...
}
~~~

In the example, the expression compares two tenant values using SpEL equality. This is a check of tenant content/value, not a requirement that the two String objects be the same instance.

If a more complex policy is needed, invoke a clearly named authorization bean rather than cramming logic into the expression. This also makes security reviews easier.

## 8. Common Misunderstandings

1. **Assuming SpEL == is always like Java ==:** false for objects with an overridden equals() that compares content.
2. **Assuming two objects with identical fields are automatically equal:** only true when the class defines equals() based on those fields.
3. **Using != to check whether objects are different instances:** != is inequality under SpEL rules, not an identity check.
4. **Using identity hash code to prove the same object:** hash codes can collide.
5. **Forgetting null when calling equals() or compareTo():** method calls on a null receiver can cause evaluation errors.
6. **Ignoring type conversion:** operands of different types may be converted by SpEL before comparison.
7. **Using default equality for domain objects without defining a contract:** clearly determine whether equality is based on ID, full state, or a business key.

## 9. Quick Takeaways

- Value equality answers whether two values are considered equal under the type's contract.
- Reference identity answers whether two references point to the same object.
- SpEL **==** and **!=** are equality/inequality operators; for ordinary objects, they rely on equals().
- If a class does not override equals(), Object.equals() compares identity by default.
- Java == on references checks identity; do not carry that meaning over to SpEL.
- SpEL has no dedicated === operator for reference identity.
- When identity is genuinely needed, call a Java helper performing left == right.
- For BigDecimal, distinguish equals() from compareTo() because scale can produce different results.
- Always consider null, type conversion, and the data type's equality contract before writing expressions.

## 10. Official References

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Operators in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Java Object.equals() Contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))
- [Java BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
