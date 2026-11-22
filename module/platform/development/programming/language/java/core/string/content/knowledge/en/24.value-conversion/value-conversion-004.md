# toString() of String and Other Objects in Java

In Java, **toString()** is the method used to obtain a **String** representation of an object. Every class inherits this method from **java.lang.Object**, though each type can redefine its own representation. What makes **String** special is that it **is already a text string**, so **String.toString() returns the current String object itself**, whereas many other objects must construct or return an appropriate string representation.

Understanding this difference helps you read `println` output, string concatenation, logs, and debug info; avoid misinterpreting the `@` symbol in default representations; handle `null` properly; and recognize why an array's `toString()` does not print its elements as expected.

## 1. Where is toString() Declared and What Does It Mean?

The **Object** class defines the method `public String toString()`. Because every Java class inherits from `Object` (directly or indirectly), classes such as `String`, `Integer`, `ArrayList`, custom domain classes, and even array objects can all be converted to a `String` representation via `toString()`.

The specific behavior depends on the actual runtime class of the object:

- **Object not overriding toString():** the default method returns a string consisting of the class name, the `@` symbol, and the hash code value in hexadecimal.
- **Class overriding toString():** the method may return a name, properties, state, or human-readable information, depending on the class definition.
- **String:** overrides `toString()` to **return this**, i.e., returning the exact reference to the original string; it does not create another string with equivalent content.
- **Primitive types** such as `int`, `long`, and `boolean` are not `Object`s and **do not have an instance method `intVariable.toString()`**; to create a string, you can use `String.valueOf(value)` or `Integer.toString(value)` for the appropriate type.

`toString()` is used to present or inspect an object. It is **not an automatic serialization method** to convert data into JSON, XML, or a format sufficient to reconstruct the object. Nor does a `toString()` result guarantee uniqueness, format immutability, or suitability for machine parsing.

## 2. String.toString(): Returning the String Itself

In Java, `String` is a `final` class, so no subclass can alter the behavior of `toString()`. The method **String.toString() returns `this`**; therefore, if variable `s` references a non-null `String`, the expression `s.toString()` has the same reference and the same content as `s`.

Example file **StringToStringDemo.java** (runs on Java 17+):

~~~java
public class StringToStringDemo {
    public static void main(String[] args) {
        String text = new String("Java");
        String converted = text.toString();

        System.out.println("content: " + converted);
        System.out.println("same reference: " + (text == converted));
        System.out.println("same content: " + text.equals(converted));

        Object objectRef = text;
        System.out.println("via Object: " + objectRef.toString());
        System.out.println("same via Object: " + (objectRef.toString() == text));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StringToStringDemo.java
java StringToStringDemo
~~~

Result:

~~~text
content: Java
same reference: true
same content: true
via Object: Java
same via Object: true
~~~

**Why are they all true?**

1. **new String("Java")** intentionally creates a new `String` object so the example does not rely on the String pool mechanism.
2. **text.toString()** returns `text` itself; therefore the **==** operator evaluates to `true` between the two references.
3. **equals()** compares string content and also yields `true`, though this is a different check from `==`.
4. Even though variable **objectRef** is declared with type `Object`, the actual object is still a `String`. Java uses **dynamic dispatch** to call the overridden `String.toString()`, returning the exact string `"Java"`.

There is no need to call `toString()` whenever you already have a `String`. For example, writing **String result = text;** usually expresses intent more clearly than **String result = text.toString();**. Calling `toString()` on a `String` does not sanitize it, change encoding, normalize Unicode, trim whitespace, or create a copy.

**Null warning:** the conclusion that it returns `this` applies only when the `String` reference is **non-null**. If **String s = null**, calling **s.toString()** throws a `NullPointerException` before any string can be returned.

## 3. Default Object.toString(): Class Name, @, and Hash

If a class does not override `toString()`, it uses the implementation inherited from **Object**. The conceptual result pattern is:

~~~text
package.name.ClassName@hexHash
~~~

By the contract of `Object.toString()`, the value is produced as if by concatenating:

~~~java
getClass().getName() + "@" + Integer.toHexString(hashCode())
~~~

For example, a run might display **java.lang.Object@5acf9800**. The part after the `@` depends on the object's `hashCode`, so **do not hardcode this string in expected output assertions**.

File **ObjectToStringDemo.java**:

~~~java
public class ObjectToStringDemo {
    public static void main(String[] args) {
        Object obj = new Object();
        String result = obj.toString();

        System.out.println(result.startsWith("java.lang.Object@"));
        System.out.println(result.equals(
                obj.getClass().getName() + "@"
                        + Integer.toHexString(obj.hashCode())
        ));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ObjectToStringDemo.java
java ObjectToStringDemo
~~~

Exact output:

~~~text
true
true
~~~

Here we avoid printing the hash code directly since it changes across objects/runs; instead, we verify the two properties guaranteed by the default implementation.

**Hash codes are not reliable memory addresses.** The `@` and hex segment of `Object.toString()` do not prove where an object resides in RAM; the `hashCode` value is not designed as a unique business ID. Two distinct objects can also share the same hash code.

Additionally, a class might override **hashCode()** without overriding **toString()**; in that case `Object.toString()` uses that class's `hashCode` result, so you should not infer that the hex segment is necessarily a JVM default identifier.

## 4. Custom Classes: Overriding toString() for Readable Content

Most domain classes need a more meaningful display than class name and hash code. We can override `toString()` with **@Override** and return a `String` describing useful properties.

Create file **OrderToStringDemo.java**:

~~~java
public class OrderToStringDemo {
    static final class Order {
        private final int id;
        private final String status;

        Order(int id, String status) {
            this.id = id;
            this.status = status;
        }

        @Override
        public String toString() {
            return "Order{id=" + id + ", status='" + status + "'}";
        }
    }

    public static void main(String[] args) {
        Order order = new Order(42, "PAID");

        System.out.println(order.toString());
        System.out.println(order);
        System.out.println("Current: " + order);
    }
}
~~~

~~~bash
javac -encoding UTF-8 OrderToStringDemo.java
java OrderToStringDemo
~~~

~~~text
Order{id=42, status='PAID'}
Order{id=42, status='PAID'}
Current: Order{id=42, status='PAID'}
~~~

In the example:

- **@Override** helps the compiler verify that the method signature overrides a superclass method.
- The overridden method is **public String toString()**, taking no parameters and returning a `String`.
- **System.out.println(order)** can use `order`'s string representation; the concatenation in **"Current: " + order** also uses this representation.
- `toString()` here **produces a textual representation** of `Order`. Do not rely on it always creating a new `String` object or always keeping this exact format if the class is updated in another version.

If a class holds sensitive information such as passwords, tokens, API keys, or private identifiers, **do not include those values in `toString()`**, because the method is easily invoked implicitly during logging or error handling. For complex objects, prefer concise, readable content and avoid external service calls or expensive computations inside `toString()`.

### Method selection by actual runtime class

If a variable declared with type `Object` points to an `Order`, calling `variable.toString()` still executes **Order.toString()**. This mechanism is called **polymorphism**, independent of whether the variable is declared as `Object` or `Order`. Java does not require casting to `Order` to find the appropriate overridden method.

**Note on records:** in Java 17, a `record` that does not define its own `toString()` is given a compiler-generated representation based on the record name and its components. For example, **record Point(int x, int y)** may print **Point[x=2, y=3]**. This is convenient for debugging, though it still does not turn `toString()` into a stable data interchange format.

## 5. String.valueOf(Object), Objects.toString, and Null Handling

It is easy to confuse **x.toString()** with **String.valueOf(x)**. Both can produce a string representation, but they differ significantly when the reference is **null**:

| Form | When `x` is non-null | When `x` is null |
| --- | --- | --- |
| `x.toString()` | Calls `toString()` of the actual class. | **NullPointerException**. |
| `String.valueOf((Object) x)` | Calls `x.toString()`. | Returns the string **"null"**. |
| `Objects.toString(x)` | Calls `x.toString()`. | Returns the string **"null"**. |
| `Objects.toString(x, "none")` | Calls `x.toString()`. | Returns the fallback string **"none"**. |

Why **(Object)** is written in the table: `String.valueOf` has multiple overloads accepting `Object`, `char[]`, and primitive types; casting to `Object` makes it clear we are referring to **String.valueOf(Object)**.

File **NullToStringDemo.java**:

~~~java
import java.util.Objects;

public class NullToStringDemo {
    public static void main(String[] args) {
        Object present = Integer.valueOf(25);
        Object missing = null;

        System.out.println(String.valueOf(present));
        System.out.println(String.valueOf(missing));
        System.out.println(Objects.toString(missing, "(empty)"));

        try {
            System.out.println(missing.toString());
        } catch (NullPointerException ex) {
            System.out.println("toString on null: NullPointerException");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullToStringDemo.java
java NullToStringDemo
~~~

~~~text
25
null
(empty)
toString on null: NullPointerException
~~~

This output has **four lines**. The second line has the text content `"null"`, which does not mean the variable `missing` turned into a `String`.

**Beware of uncast `String.valueOf(null)` calls:** because Java selects the most specific overload, an expression with a `null` literal may select the **char[]** overload instead of `Object`, leading to a runtime error. When you want the exact behavior of producing the string `"null"`, specify **String.valueOf((Object) null)** or use **Objects.toString(null)**.

`String.valueOf` also has dedicated overloads for `boolean`, `char`, `int`, `long`, `float`, `double`, etc.; for primitives, it produces the representation of the primitive value without explicitly creating a wrapper object first. For objects, behavior depends on the actual class's `toString()`.

## 6. Array toString() vs. Printing Element Contents

In Java, **arrays are objects**, yet array classes do not provide an element-listing `toString()` as beginners often expect. Calling **numbers.toString()** on an `int[]` uses the default representation, typically starting with **[I@** (the JVM class name for an `int` array) followed by a hash code.

To inspect array contents, use the utilities in **java.util.Arrays**:

- **Arrays.toString(array)** for one-dimensional arrays.
- **Arrays.deepToString(objectArray)** for multidimensional arrays or arrays containing nested arrays, such as `int[][]`.
- For **char[]** arrays, the special **String.valueOf(char[])** overload creates a `String` from the characters; it differs from `String.valueOf((Object) charArray)`.

Example file **ArrayToStringDemo.java**:

~~~java
import java.util.Arrays;

public class ArrayToStringDemo {
    public static void main(String[] args) {
        int[] numbers = {2, 4, 6};
        int[][] matrix = {{1, 2}, {3, 4}};
        char[] letters = {'J', 'a', 'v', 'a'};

        System.out.println(numbers.toString().startsWith("[I@"));
        System.out.println(Arrays.toString(numbers));
        System.out.println(Arrays.deepToString(matrix));
        System.out.println(String.valueOf(letters));
        System.out.println(String.valueOf((Object) letters)
                .startsWith("[C@"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayToStringDemo.java
java ArrayToStringDemo
~~~

~~~text
true
[2, 4, 6]
[[1, 2], [3, 4]]
Java
true
~~~

The first line verifies the `int` array type name without guessing the hash code. The last line demonstrates the difference between two overloads of `String.valueOf`: passing `char[]` directly creates a `String` from the characters, whereas casting to `Object` forces a call to the array object's `toString()`.

If you have an **Object[]** containing nested arrays, `Arrays.toString` may still show the class-name-and-hash representation of the inner arrays; `Arrays.deepToString` is needed to display nested elements properly. For self-referential arrays, `deepToString` has handling to prevent infinite recursion per the API contract.

## 7. How Does toString() of Mutable Objects Differ from String?

Objects can be **mutable**, such as `StringBuilder`. Calling `StringBuilder.toString()` creates a `String` representing **the content at the time of the call**; the resulting string is immutable, so subsequent edits to the `StringBuilder` do not alter the captured snapshot.

File **BuilderToStringDemo.java**:

~~~java
public class BuilderToStringDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("v1");
        String snapshot = builder.toString();

        builder.append("-updated");

        System.out.println("builder: " + builder);
        System.out.println("snapshot: " + snapshot);
        System.out.println("snapshot type: " + snapshot.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BuilderToStringDemo.java
java BuilderToStringDemo
~~~

~~~text
builder: v1-updated
snapshot: v1
snapshot type: String
~~~

**Comparing the two cases:** `String.toString()` returns **the exact same `String` object**, because `String` is already immutable and is already the desired string form. `StringBuilder.toString()` returns a **`String` containing the current content** of the builder; the snapshot does not continue updating when the builder changes. Do not write logic that assumes the `String` object returned by `StringBuilder` always has a fresh reference in every circumstance; what matters by the API contract is that **the string value is preserved after the builder changes**.

Many other library classes also provide readable `toString()` implementations, such as numeric wrapper classes like `Integer` and collections. However, the exact format depends on each class; a collection may use the `toString()` of its elements, so how elements appear is still determined by their own classes.

## 8. Where is toString() Called Implicitly?

Java and libraries often convert objects to text without us calling the `toString()` method directly:

- **System.out.println(object)**: print overloads have mechanisms to convert objects to text. If `object` is `null`, `println(Object)` prints **null** instead of calling a method on a null reference.
- **"value = " + object**: the string concatenation operator converts the object operand to a `String` representation; `null` becomes the text **"null"**.
- **String.valueOf(object)** and **Objects.toString(object)**: call `toString()` if the object is non-null.
- **StringBuilder.append(Object)**: typically uses `String.valueOf(Object)` and appends the text to the builder.
- Some formatters or loggers may use `toString()`, though each library's specific mechanism can differ; do not assume every logger always calls `toString()` in the exact same way.

Consequently, a sensible `toString()` override aids debugging, yet can also make printing objects **expensive**, raise exceptions, or inadvertently leak data. Avoid putting passwords, access tokens, personal data, and overly large text blocks into the default `toString()` of domain models.

If you need **user-facing formatting**, **persisted data**, or **API payload data**, write a dedicated method or serializer for that purpose. `toString()` is primarily a textual representation of an object, not a guaranteed stable serialization contract.

## 9. Common Confusions

| Misconception | Accurate explanation |
| --- | --- |
| `String.toString()` creates a new `String` copy. | `String.toString()` returns **`this`**, i.e., the same object. |
| Every object uses the default `Object.toString()`. | A class may override `toString()`; Java dispatches based on the **actual runtime type**. |
| The hex part in `ClassName@hex` is a memory address. | It is the hex representation of **`hashCode()`**, not a guaranteed RAM address. |
| Calling `toString()` on a null reference returns `"null"`. | Calling a method on null throws **NullPointerException**; for null-safety use `String.valueOf((Object) x)` or `Objects.toString(x)`. |
| `String.valueOf(null)` is always equivalent to `String.valueOf((Object) null)`. | There is a `char[]` overload; casting is needed to avoid choosing the wrong overload when passing a `null` literal. |
| `array.toString()` prints all elements. | Arrays normally use a type-and-hash representation; use `Arrays.toString`/`deepToString`. |
| Concatenating an object to a `String` only calls `Object.toString()`. | The method is selected by the **actual class**, which may be a subclass override. |
| `toString()` must always return the class name and fields. | That is a class **design** choice; the API only requires returning a `String`, whose content may differ. |
| `toString()` is a standard format for JSON or storage. | There is no such guarantee; use a serializer or a dedicated format. |
| An overridden `toString()` can print secrets for easier debugging. | Implicit calls are very common; avoid leaking sensitive information in logs. |

## 10. Checklist When Designing and Using toString()

1. **Already have a `String`?** You can use it directly, because calling `toString()` does not change the reference or content.
2. **Custom object needs to be readable?** Consider overriding `public String toString()`, adding `@Override`, and choosing concise, non-sensitive fields.
3. **Variable might be `null`?** Use `String.valueOf((Object) value)`, `Objects.toString(value)`, or `Objects.toString(value, fallback)` as appropriate.
4. **Working with an array?** Look at `Arrays.toString`, `Arrays.deepToString`, or `String.valueOf(char[])` depending on the array type.
5. **Converting `StringBuilder` or a mutable object?** Treat the returned `String` as a representation/snapshot at the moment of the call.
6. **Need data for comparison, identification, or storage?** Do not rely on `toString()` as a data contract; use `equals`/`hashCode`, identifier keys, or a dedicated serializer depending on the goal.

Quick rule of thumb: **String.toString() preserves the String itself; default Object.toString() describes the class and hash; other classes may override it to provide a meaningful representation.** When Java needs to display an object, the behavior depends on the actual runtime class and the null-handling policy of the calling API.