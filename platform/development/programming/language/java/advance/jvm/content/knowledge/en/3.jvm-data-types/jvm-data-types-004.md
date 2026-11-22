# The null Value, Class Types, Interface Types, and Array Types in the JVM

## 1. Objective: Understanding Reference Values Accurately

In the JVM, data types serve to represent values, verify bytecode validity, and execute programs. A foundational distinction is between **primitive values** and **reference values**.

Example:

```java
int count = 3;                 // primitive int value
String title = "JVM";          // variable with a reference type to String
Runnable task = () -> {};     // reference via an interface type
int[] numbers = {1, 2, 3};    // an array is also an object and the variable value is a reference
String missing = null;        // special null reference value
```

In the **JVM Specification (JVMS §2.4)**, the three groups of reference types are:

1. **Class types**: describe objects belonging to a class, such as `java.lang.String`.
2. **Interface types**: allow referencing objects whose class implements the interface, such as `java.lang.Runnable`.
3. **Array types**: describe array objects, such as `int[]` or `String[][]`.

A reference value can be a reference to a corresponding object or the **special value `null`**. The JVM does not add a "fourth JVM type named null" to the three groups above. At the **Java language** level, the JLS specification mentions a special **null type** for the `null` expression; this type has no name for writing variable declarations and must be distinguished from the reference types classification in the JVMS.

Objective after this lesson: explain which objects can be held in class/interface/array variables, why `null` is valid in reference positions, which bytecodes are involved, when `NullPointerException`, `ClassCastException`, and `ArrayStoreException` appear, and why `int[]` is a reference type even though its elements are `int`.

## 2. From Java Source Types to the Values the JVM Manipulates

Consider:

```java
String message = "hello";
Object any = message;
CharSequence readable = message;
```

The string object is created/managed at runtime; three variables can simultaneously reference **one object** even though their declared types differ. A reference-type variable **does not contain a copy of the entire object**. When assigning `any = message`, the program copies the *reference value* according to the language model, without automatically copying the string's contents.

The word "reference" is not synonymous with "raw memory address that the programmer can read out and perform arithmetic on". The JVM specification does not force every implementation to represent a reference with the same form of physical pointer. Compilers/runtimes may also optimize internally, but observable semantics must obey the Java contract.

### Declared Type and Actual Type Differ

```java
Object value = "Java";
```

- The **static type** of the variable `value` is `Object`; the compiler checks the operations allowed on this variable based on its static type.
- The **runtime type** of the referenced object is `String`.
- It can be checked at runtime with `value instanceof String` or `value.getClass()` if the reference is not `null`.
- If `value = null` is assigned, there is no object behind that reference to query `getClass()`.

This distinction explains why the same object can be viewed through a superclass type, an interface, or `Object`, while an invalid cast is only detected at runtime.

### Where Do Objects Reside?

In the JVM model, objects and arrays are allocated on the **heap**. Locations that hold reference values can be local variables of a frame, object fields, `static` fields, or elements of a reference array. The actual machine layout, optimizations, and specific memory organization depend on the JVM implementation.

Conceptual diagram:

```text
Local variables          Heap (conceptual)
-------------------      -----------------------
String a -----------+---> String object "JVM"
Object b -----------+
String c = null ----X     (no object for c)
```

Assigning `null` to a variable only changes the reference at that location. It **does not directly destroy** the object that was previously referenced; the object may still be referenced from elsewhere, and eligibility for reclamation is determined by reachability/garbage collection mechanisms.

## 3. The `null` Value: Where Can It Appear and What Does It Mean?

### 3.1. `null` Is Not Zero, an Empty String, or a `Null` Object

`null` indicates **there is no object/array currently being referenced** at that location. It is completely different from:

| Expression | Meaning |
| --- | --- |
| `null` | References no object |
| `0` | Integer value equal to zero |
| `""` | Reference to a `String` object of length 0 |
| `new int[0]` | Reference to a valid `int` array with `length == 0` |
| `new Object()` | Reference to a newly created object |

A zero-length array is still **a real array object**, has a runtime type, and can have `getClass()` called on it. With `null`, you cannot access members or query the runtime class.

### 3.2. `null` Is Compatible with Reference-Type Positions

```java
String text = null;
Runnable runnable = null;
Object object = null;
String[] strings = null;
int[] integers = null;
```

The declarations above are valid. `int[]` is an **array/reference type**, whereas `int` is a primitive; therefore `int[] a = null` is valid, but `int x = null` is a compile error.

Note the difference between `null` and an array whose elements have default values:

```java
String[] names = new String[2];
System.out.println(names == null); // false
System.out.println(names[0]);      // null
```

The variable `names` holds a reference to **a real array**. The two slots of the `String[]` array initially contain a **null reference**.

### 3.3. Default Values and Definite Assignment

**Object fields**, **static fields**, and **reference-type array elements** are initialized by default to `null` when the object/class/array is initialized according to the corresponding rules. Example:

```java
class Account {
    String owner;             // default value null
    static Object cache;      // default value null
}
```

Conversely, local variables must be definitely assigned before being read, according to the Java compiler's *definite assignment* rule:

```java
// Illustrating a compile error (not a standalone program):
String unassigned;
// System.out.println(unassigned); // error: variable might not have been initialized
```

One should not infer that "reference-type local variables always default to `null`"; the constraint in the Java language prevents reading an unassigned variable in the situation above. In addition, `var x = null;` does not have enough information to infer a valid local variable type; if you intentionally want to allow null, declare the type explicitly.

### 3.4. `null`, Comparison, and `instanceof`

```java
Object a = null;
Object b = null;
System.out.println(a == b);           // true
System.out.println(a instanceof Object); // false
```

The `==` operator on two reference values compares whether they have the same reference (or are both `null`). `null instanceof AnySuitableReferenceType` is always **false**: there is no object to check the runtime type of.

Casting `null` to a reference type is valid and returns `null`:

```java
String name = (String) null;
System.out.println(name == null); // true
```

This differs from casting a **non-null** object to an incompatible type, which can throw `ClassCastException`.

### 3.5. Dereferencing `null`

Operations that require a real object will fail if the target object is `null`. Example:

```java
String s = null;
// s.length(); // NullPointerException at runtime
```

Typical scenarios:

- Calling an instance method or accessing an instance field through a null reference.
- Reading/writing an element of a null array and reading `array.length` through a null array.
- Performing unboxing on a wrapper whose value is null, for example `Integer boxed = null; int n = boxed;`.
- Certain other operations that require a non-null reference.

**Not every operation involving `null` is an error.** Assigning `null`, comparing `== null`, `instanceof`, and reference casting on `null` have valid semantics. One must distinguish checking/moving a reference from an operation that actually requires an object.

### 3.6. `null` in Overloads and API Design

Two overloads that are unrelated in specificity can cause a call with `null` to become **ambiguous at compile time**:

```java
// Structural illustration: not meant as a standalone program.
void select(String value) {}
void select(Integer value) {}

// select(null); // compile error: reference to select is ambiguous
select((String) null); // selects the overload taking String
```

This is a **compile-time method selection** issue based on the type of the expression, not a `NullPointerException`.

When an API requires a non-null value, the contract should be clearly documented and checked at the appropriate boundary:

```java
import java.util.Objects;

static String normalize(String input) {
    Objects.requireNonNull(input, "input");
    return input.trim();
}
```

The snippet above is a **method illustration**, not a standalone program. `requireNonNull` throws a `NullPointerException` with a specific message if the caller passes null; this is an intentional failure that is easier to diagnose than a dereference deep inside the program.

## 4. Class Type

### 4.1. A Class-Type Variable References a Compatible Instance

When declaring:

```java
Number number = Integer.valueOf(42);
Object object = number;
```

`Number` and `Object` are both class types. The runtime object is an instance of `Integer`, which is a subclass of `Number` and `Object`. Assignments from a more specific type to a supertype are allowed when there is an appropriate type relationship (*widening reference conversion*).

A class type does not have to be a concrete class that can be used directly with `new`:

- An **abstract** class like `Number` is still a valid class type for variables, parameters, and return types.
- You cannot do `new Number()` because it is an abstract class.
- Values can still come from objects of concrete subclasses, such as `Integer`.

**Class vs. reference value:** the `String` type describes the group of matching objects; a variable `String s` only holds one reference value at a time, which may be `null`.

### 4.2. What Do the Declared Class and Runtime Class Determine?

```java
Object value = "hello";
```

The compiler only allows calling methods directly that are known through the static type `Object` (unless there is a cast or another language mechanism). For example, `value.toString()` is valid whereas `value.length()` is invalid without checking and converting the type.

Using pattern matching for `instanceof` (valid since Java 17):

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

The condition is true because the runtime object is `String`; the variable `text` is checked by the compiler as type `String` within the scope of the corresponding branch. If `value == null`, the condition is false.

Reference casting:

```java
Object value = "hello";
String ok = (String) value;         // valid at runtime
// Integer bad = (Integer) value;  // ClassCastException at runtime
```

The offending line has been commented out so the rest of the example remains valid. If the runtime detects that the object is incompatible with the target class/interface, the cast operation will fail.

### 4.3. `java.lang.Object` in the Hierarchy

`Object` is the root superclass of ordinary Java classes and is a type that can hold references to Java objects, including array objects:

```java
Object object = new Object();
Object text = "a";
Object array = new int[3];
```

However, one must not equate primitives with references: `int` is a primitive, whereas `Integer` is a wrapper class. `Object boxed = 5;` is valid thanks to **autoboxing** from `int` to the corresponding wrapper object; it does not mean `int` itself turns into a kind of JVM class.

## 5. Interface Type

### 5.1. An Interface Variable Holds a Reference to an Object Implementing the Contract

An interface defines a contract that a class can implement. Example:

```java
interface Named {
    String name();
}

final class Person implements Named {
    private final String value;

    Person(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }
}
```

The declarations above are **illustrative code with multiple top-level types**, which need to be placed in appropriate Java files when used in a real project. You can use them as:

```java
Named named = new Person("Lan");
System.out.println(named.name()); // Lan
```

`Named` is the **declared type** of the variable; the actual object is an instance of `Person`. The call `named.name()` is executed according to the implementation applicable to the runtime object. In a class file, a call through an interface usually corresponds to the `invokeinterface` opcode; an instance method call through a class usually uses `invokevirtual` when appropriate. This is a detail of the JVM model, not a promise that every Java call always produces the exact same opcode after all compiler/runtime optimizations.

### 5.2. Why Is an Interface a Reference Type Even Though It Cannot Instantiate Itself?

You cannot write `new Named()` when `Named` is a regular interface. Nevertheless, a `Named` variable can hold:

- A reference to an object of any class that implements `Named`.
- The `null` value.
- An object of a subclass that inherits the `Named` implementation if applicable.

An interface is not a copy of an object; it is a **way of representing the capability/type relationship** of an object. An object can be referenced through multiple different interfaces.

```java
Runnable r = () -> System.out.println("run");
Object sameObject = r;
```

Both `r` and `sameObject` can hold a reference to the same runtime object. `r.run()` invokes the implementation; `sameObject.run()` is invalid at compile-time because the static type `Object` does not declare `run()`.

### 5.3. Interfaces Do Not Eliminate Runtime Checks

```java
Object candidate = "text";
System.out.println(candidate instanceof Runnable); // false
```

A runtime reference to `String` does not become `Runnable` just because the programmer wants to cast it. Casting to an interface not supported by the object can throw `ClassCastException`. `null` can be cast to an interface, but interface methods cannot be called on it while it is still null.

The **interface** type in the JVM also appears in type checking, descriptors, assignability rules, and method linkage. Polymorphism only works when the actual object conforms to the contract.

## 6. Array Type: Elements Can Be Primitive or Reference

### 6.1. Every Java Array Is an Object

```java
int[] numbers = new int[3];
String[] words = new String[3];
```

Both `int[]` and `String[]` are **reference types** and both reference **array objects**. The difference is the **component type**:

- `int[]` has component type `int` (primitive). Each slot holds an `int` value.
- `String[]` has component type `String` (reference). Each slot holds a reference value to a `String` or `null`.
- `String[][]` has component type `String[]` (which is also an array type); the elements of the outer array are references to inner arrays.

An array object has a **fixed length** from the moment it is created. `array.length` returns the number of elements, while `array.length = 7` is a compile error. If you need flexible capacity growth, consider collections such as `ArrayList` when requirements fit.

### 6.2. Default Values of Elements

| Declaration | Element type | Default value |
| --- | --- | --- |
| `new int[2]` | `int` | `0` |
| `new boolean[2]` | `boolean` | `false` |
| `new double[2]` | `double` | `0.0` |
| `new String[2]` | `String` | `null` |
| `new Runnable[2]` | `Runnable` | `null` |
| `new int[2][]` | `int[]` (reference type) | `null` |

If `String[] array = null;`, then the variable itself does not point to any array. If `String[] array = new String[2];`, then there is a real array with two elements initially null. These are two different states.

### 6.3. One-Dimensional, Multi-Dimensional, and Jagged Arrays

```java
int[][] grid = new int[2][3];
```

`grid` references an outer array consisting of two elements of type `int[]`; each element points to an `int` array of length 3.

```text
grid ──> [ ref row 0 | ref row 1 ]
              |             |
              v             v
           [0,0,0]       [0,0,0]
```

Java multi-dimensional arrays are **arrays of arrays**. Rows can have different lengths:

```java
int[][] ragged = new int[2][];
ragged[0] = new int[] {1};
ragged[1] = new int[] {2, 3, 4};
```

At the point after `new int[2][]` but before assigning the two rows, each element `ragged[0]` and `ragged[1]` is `null`. Attempting to access `ragged[0].length` at this time will result in a `NullPointerException`.

### 6.4. Arrays Are Objects Belonging to a Special Hierarchy

Every Java array object has `Object` as its direct superclass according to Java's runtime model and implements two marker interfaces: `java.lang.Cloneable` and `java.io.Serializable`. Example:

```java
Object value = new int[] {1, 2};
Cloneable cloneable = (Cloneable) value;
java.io.Serializable serializable = (java.io.Serializable) value;
```

The casts in the example succeed because the runtime value is an array. However, `int[]` **is not** `Object[]`: the elements of `int[]` are primitive integers, not object references. The following code does not compile:

```java
// Illustrating a type error (line intentionally commented out):
// Object[] array = new int[3]; // incompatible types
```

Conversely, `String[]` can be assigned to `Object[]` because arrays **with reference elements** support a conditional covariance relationship (section below).

### 6.5. Arrays Retain Their Runtime Component Type

Reference arrays **remember their runtime component type** so that the JVM can check writes into elements. Therefore `Object[] view = new String[2]` is valid, but the actual object is still `String[]` and the JVM does not allow writing an `Integer` into that slot.

This can be observed:

```java
Object a = new String[2];
Object b = new int[2];
System.out.println(a.getClass().isArray()); // true
System.out.println(b.getClass().isArray()); // true
```

`a.getClass().getComponentType()` reflects `String.class`, while `b.getClass().getComponentType()` reflects `int.class`. Runtime checks can only be performed when the reference is not `null`.

## 7. Array Covariance and `ArrayStoreException`

The **covariance** relationship of reference arrays means: when `Sub` is a subtype of `Super`, `Sub[]` can be used where `Super[]` is accepted, according to the corresponding type rules.

```java
String[] actual = new String[2];
Object[] view = actual;    // valid at compile-time
view[0] = "hello";        // valid at runtime
// view[1] = 123;         // compiles, but throws ArrayStoreException
```

Reason:

1. The static type of `view` is `Object[]`, so the compiler allows storing an `Integer` (autoboxing from the number `123`).
2. The actual runtime array object is `String[]`.
3. When the instruction to store a reference element executes, the JVM checks whether the value is valid for the **actual component type** of the array.
4. `Integer` is not a `String` → `ArrayStoreException`.

**Important:** not all Java arrays have the same covariance. `int[]` does not have an assignment like `Object[]`; for **primitive** components, arrays of different primitive types do not form a subtype relationship via numeric widening. For example, `int[]` does not automatically convert to `long[]`.

Compared with generics:

```java
// Compile-time illustration (invalid line commented out):
// java.util.List<Object> objects = new java.util.ArrayList<String>();
```

`List<String>` is not a subtype of `List<Object>` (invariance of generic type arguments), whereas `String[]` is a subtype of `Object[]`. This design allows generics to catch many invalid writes **at compile time**; arrays may have to check **at runtime** as well.

**Practical risk:** passing a `String[]` to an API that takes `Object[]` and having the API write a non-`String` value can cause an `ArrayStoreException` deep in the program. When design changes are permitted, the API should declare the exact component type or use a generic collection with an appropriate contract.

## 8. Type Conversions, Comparisons, and Runtime Errors

| Operation | Example | Result / note |
| --- | --- | --- |
| Widening reference | `Object o = "A";` | Valid: `String` is compatible with `Object` |
| Interface reference | `CharSequence c = "A";` | Valid: `String` implements `CharSequence` |
| Null assignment | `String s = null;` | Valid: reference variable holds null |
| Null cast | `String s = (String) null;` | Valid, result is still null |
| Null `instanceof` | `null instanceof String` | `false` |
| Null dereference | `((String) null).length()` | `NullPointerException` |
| Checked downcast | `(String) someObject` | Succeeds if runtime object matches or is null; otherwise may throw `ClassCastException` |
| Reference array upcast | `Object[] a = new String[1];` | Compiles |
| Wrong reference array store | `a[0] = Integer.valueOf(3);` | `ArrayStoreException` if a is actually `String[]` |
| Primitive array as object | `Object o = new int[1];` | Valid because arrays are objects |
| Primitive array as object array | `Object[] o = new int[1];` | Does not compile |
| Read beyond array bounds | `new int[1][1]` (accessing index 1 on outer array) | `ArrayIndexOutOfBoundsException` |
| Negative array size | `new String[-1]` | `NegativeArraySizeException` at runtime |

**Note:** whether an error occurs also depends on **the expression actually executed**. The table describes the semantics of the corresponding cases; one should not assume the compiler allows every example as a standalone program.

## 9. Complete Java 17+ Example and Exact stdout

Create a single file **`ReferenceTypesDemo.java`** in the current directory:

```java
import java.io.Serializable;
import java.util.Arrays;

public class ReferenceTypesDemo {
    interface Named {
        String name();
    }

    static final class Student implements Named {
        private final String value;

        Student(String value) {
            this.value = value;
        }

        @Override
        public String name() {
            return value;
        }
    }

    static void report(Named candidate) {
        System.out.println("is null: " + (candidate == null));
        System.out.println("instanceof Named: " + (candidate instanceof Named));
    }

    public static void main(String[] args) {
        Student student = new Student("Lan");
        Object byClass = student;
        Named byInterface = student;

        System.out.println("class: " + (byClass instanceof Student));
        System.out.println("interface call: " + byInterface.name());

        Named missing = null;
        report(missing);

        String[] names = new String[2];
        System.out.println("reference default: " + names[0]);
        names[0] = "Java";
        names[1] = "JVM";
        System.out.println("array: " + Arrays.toString(names));
        System.out.println("length: " + names.length);
        System.out.println("array as Object: " + (names instanceof Object));
        System.out.println("array as Cloneable: " + (names instanceof Cloneable));
        System.out.println("array as Serializable: " + (names instanceof Serializable));

        Object[] wider = names;
        try {
            wider[0] = Integer.valueOf(42);
        } catch (ArrayStoreException exception) {
            System.out.println("array store rejected");
        }
        System.out.println("array after check: " + Arrays.toString(names));

        int[] numbers = new int[2];
        System.out.println("primitive default: " + numbers[0]);
        System.out.println("primitive array as Object: " + (numbers instanceof Object));

        int[][] grid = new int[2][];
        System.out.println("nested row null: " + (grid[0] == null));
        grid[0] = new int[] {1, 2};
        grid[1] = new int[] {3};
        System.out.println("jagged row lengths: "
                + grid[0].length + ", " + grid[1].length);

        String absent = (String) null;
        System.out.println("cast null: " + (absent == null));
        System.out.println("null instanceof Object: " + (absent instanceof Object));

        try {
            absent.length();
        } catch (NullPointerException exception) {
            System.out.println("dereference null rejected");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ReferenceTypesDemo.java
java ReferenceTypesDemo
```

**Exact stdout** of the program (independent of PID or JVM exception message strings):

```text
class: true
interface call: Lan
is null: true
instanceof Named: false
reference default: null
array: [Java, JVM]
length: 2
array as Object: true
array as Cloneable: true
array as Serializable: true
array store rejected
array after check: [Java, JVM]
primitive default: 0
primitive array as Object: true
nested row null: true
jagged row lengths: 2, 1
cast null: true
null instanceof Object: false
dereference null rejected
```

### Explanation of Key Lines

**`class: true`:** the variable `byClass` has declared type `Object` but references a `Student` object. `instanceof Student` checks the runtime object.

**`interface call: Lan`:** the variable `byInterface` has declared type `Named`; at runtime it calls `Student`'s implementation of `name()`.

**`is null: true` and `instanceof Named: false`:** an interface declared type allows null, but null does not represent an object implementing the interface.

**`reference default: null`:** the slots of a newly created `String[]` array start with null references.

**`array as Object/Cloneable/Serializable: true`:** array objects participate in a special type hierarchy.

**`array store rejected`:** the runtime check detects that an `Integer` value cannot be stored into an actual `String[]` array, even when the variable used for writing has type `Object[]`. The old element is preserved because the operation is rejected.

**`primitive array as Object: true`:** `int[]` itself is an object, even though each element's value is a primitive `int`.

**`nested row null: true`:** the outer array `new int[2][]` is created, but the row arrays have not been created yet. The two rows created afterward have different lengths.

**`cast null: true` and `null instanceof Object: false`:** casting null is valid, but null is not an instance of `Object`.

**`dereference null rejected`:** the call `absent.length()` requires a `String` object and causes a `NullPointerException`; the example intentionally catches the exception to continue and keep stdout clear.

The lesson uses nested classes to ensure **a single standalone source file**, with the filename matching the public class name and simple run commands. Other examples in the lesson are isolated illustrations; only the complete example in this section is used to verify continuous stdout.

## 10. How Does Bytecode/JVM View Reference Types?

Java source code provides expressive syntax; class files represent many types as **descriptors** and instructions that manipulate references.

### 10.1. Descriptors for Class, Interface, and Array Types

Examples of some **field descriptors** at the class file level:

| Type in Java | JVM Descriptor | Explanation |
| --- | --- | --- |
| `int` | `I` | Primitive `int` value |
| `java.lang.String` | `Ljava/lang/String;` | A class type |
| `java.lang.Runnable` | `Ljava/lang/Runnable;` | An interface type |
| `int[]` | `[I` | One-dimensional array of primitive `int` |
| `String[]` | `[Ljava/lang/String;` | One-dimensional array of `String` |
| `int[][]` | `[[I` | Two-dimensional array in the sense of an array of `int` arrays |
| `Object[][]` | `[[Ljava/lang/Object;` | Array of arrays holding `Object` references |

Main rules:

- `L<internal-name>;` represents a class or interface type; the internal name in a descriptor uses `/`.
- Each `[` character adds one array dimension.
- Primitives have their own descriptor codes such as `I` for `int`, `J` for `long`, `Z` for `boolean`.

In bytecode, **there is no "field descriptor of null"** as an independent reference type. `null` is a **special reference value**, which can be pushed onto the operand stack by the `aconst_null` instruction. During bytecode verification, the JVM has dedicated verification type concepts for null to check data-flow validity; these should not be equated with type names that can be declared in Java.

### 10.2. Important Opcodes

| Opcode / group | Conceptual role |
| --- | --- |
| `aconst_null` | Pushes a null reference onto the operand stack |
| `aload` / `astore` | Loads/stores a reference value in a local variable |
| `new` | Creates an object of the appropriate class type |
| `newarray` | Creates an array with primitive elements |
| `anewarray` | Creates an array with reference elements |
| `multianewarray` | Creates a multi-dimensional array with the specified number of dimensions |
| `aaload` / `aastore` | Reads/writes a reference element of an array |
| `iaload` / `iastore` | Reads/writes an `int` element of an array |
| `arraylength` | Gets the length of an array |
| `checkcast` | Checks a reference cast at runtime |
| `instanceof` | Checks whether an object is compatible with a reference type |
| `ifnull` / `ifnonnull` | Branches based on whether a reference is null/non-null |
| `if_acmpeq` / `if_acmpne` | Compares equality/inequality of two reference values |
| `invokevirtual` / `invokeinterface` | Performs forms of instance method calls via the appropriate mechanism |

Even though both are **references**, the JVM retains enough type information and performs checks so that an `int[]` array cannot arbitrarily be treated as `Object[]`. When `aastore` runs, the stored value must be compatible with the **actual** component type of the array, otherwise `ArrayStoreException` is thrown.

`checkcast` has an easy-to-forget detail: for a null reference, it still **succeeds** and preserves null. Meanwhile `instanceof` returns false for null. Thus both opcodes handle null differently from attempting to dereference null.

### 10.3. Observing Bytecode Yourself with JDK Tools

After compiling the complete program:

```bash
javap -c -p ReferenceTypesDemo
```

`javap` prints the bytecode of methods, including `main`. You can look for opcode names such as `instanceof`, `anewarray`, `aastore`, `newarray`, and `arraylength` corresponding to each operation in the source code. With nested classes, the class implementing the interface will be generated as a separate class file, for example `ReferenceTypesDemo$Student.class` depending on the environment and how filenames are listed.

**Do not rely on bytecode offsets or the order of every instruction as a fixed API.** The compiler may change compilation across versions; JIT execution optimizations are also not the bytecode text that `javap -c` displays.

### 10.4. How Do the Three Reference Type Groups Relate to Type Checking?

- **Class type:** subclass/superclass relationships and the runtime object govern assignability, casting, and method dispatch.
- **Interface type:** the runtime checks whether the object implements the appropriate interface; calls can bind to the runtime class's implementation.
- **Array type:** is both an object and carries a component type and dimensionality; the JVM must check assignments and element writes according to the appropriate runtime rules.

Because **`null` has no runtime object**, it can pass through many reference assignments/casts without producing specific runtime class information.

## 11. Common Design and Debugging Mistakes

### 11.1. Confusing `null` with a Business Default Value

A `User` object with a field `String email = null` does not mean the email is an empty string; nor does it automatically prove "never assigned", because a program may assign null intentionally. The business contract must define the meaning of a missing value itself.

### 11.2. Calling `equals` on an Unchecked Reference

```java
String input = null;
// input.equals("yes"); // NullPointerException
System.out.println("yes".equals(input)); // false
```

Flipping the literal to the left side can be useful in simple cases; for other APIs, `Objects.equals(a, b)` should be used when null-safe comparison is needed. Do not confuse `==` (checks **same reference**) with `equals` (comparison contract defined by the class).

### 11.3. Using `instanceof` Thinking Null Has a Specific Runtime Type

`String s = null` states the **declared type** of variable `s`; there is no String object existing from the value of `s`. `s instanceof String` is false, and `s.getClass()` throws `NullPointerException`.

### 11.4. Casting Without Checking the Object Kind

`Object payload` can reference a `String`, `Integer`, array, or another kind of object. Casting `(String) payload` is only valid at runtime if payload is null or a `String`-compatible object. You can use `instanceof` when branching is truly needed; in API design, prefer declaring exact types to reduce unnecessary casts.

### 11.5. Assuming Every Array Is `Object[]`

`int[]` is also an Object, but it is not `Object[]`. `Object[]` uses reference elements. For primitive arrays, choose the right array type and corresponding API overloads (for example `Arrays.toString(int[])` differs from the `Arrays.toString(Object[])` overload).

### 11.6. Forgetting Type Checks When Writing Through a Supertype Array Variable

`Object[] arr = new String[1]` still points to a String array. A variable of type `Object[]` **does not change the runtime component type**. Array write checks can throw `ArrayStoreException`.

### 11.7. Confusing Multi-Dimensional Arrays with a Fixed Two-Dimensional Data Block

`int[][]` in Java is an array containing references to `int[]` arrays. The number of columns between rows can differ, and a row can be null. When iterating, you need to check for null rows if the data can be in this state.

### 11.8. Confusing Null with a Missing Value in Generic Collections

`List<String>` is a reference collection; many implementations allow null elements, but not every collection allows them. Each API's contract decides. Do not use `null` as a "not found" marker if doing so causes ambiguity between "no result" and "a result with value null"; you can consider an explicit result type such as `Optional` in appropriate APIs.

### 11.9. Assuming All Null Errors Are Caught by the Compiler

The Java compiler checks many type issues and definite assignment, but it does not guarantee every reference is non-null. Java 17 does not automatically infer non-null for every path in a program. Testing, API constraints, and static analysis can help reduce bugs.

## 12. Self-Check Exercises with Answers

**Question 1.** Is `int[] a = null;` valid? What about `int a = null;`?

**Answer:** The first declaration is valid because `int[]` is an array/reference type. The second declaration is invalid because `int` is a primitive.

**Question 2.** Why is `new String[3]` not equal to `null` even though all its initial elements are null?

**Answer:** The expression creates **a real array object** of length 3; the reference value pointing to the array is non-null. Only the **three elements** of the reference array start out as null.

**Question 3.** Does the variable `Runnable task = null;` mean an instance of a class implementing `Runnable` exists?

**Answer:** No. `Runnable` is the declared type; the null value references no instance. `task instanceof Runnable` returns false.

**Question 4.** Does `Object[] items = new String[1]; items[0] = 7;` compile? How does it run?

**Answer:** It compiles thanks to boxing `7` into `Integer` and the ability to use `String[]` as `Object[]`. At runtime, the operation of writing `Integer` into the actual `String[]` array throws `ArrayStoreException`.

**Question 5.** Do `Object data = new int[2];` and `Object[] data = new int[2];` have the same validity?

**Answer:** No. The first line is valid because an array is an object; the second line has a type error because `int[]` is not `Object[]`.

**Question 6.** Why is `(String) null` valid while `((String) null).length()` fails?

**Answer:** `checkcast` with a null reference yields null; `length()` is an instance call that requires a non-null object, so it throws `NullPointerException`.

**Question 7.** How many new array objects exist right after `String[][] values = new String[2][];`?

**Answer:** There is **one outer array object** with two elements of type `String[]`, both initially null. No row arrays have been created yet.

**Question 8.** Among the three JVM reference type categories, which category does `String[]` belong to, and which does `Runnable` belong to?

**Answer:** `String[]` is an **array type**; `Runnable` is an **interface type**. `String` is a **class type**.

## 13. Key Takeaways

- The JVM distinguishes **primitive** and **reference**; the three reference type groups according to the JVMS are **class**, **interface**, and **array**.
- A reference variable can hold null, meaning **it does not point to an object**. The JLS has the concept of a **null type** for the `null` expression, but that is not an additional class/interface/array group of the JVM.
- The **static type** governs valid operations at compile time; the **runtime type** of the object determines the result of cast/`instanceof` checks and corresponding dispatch.
- An **interface reference** can point to an instance of a class implementing the interface; a regular interface itself cannot be instantiated directly with `new`.
- **Arrays are objects** regardless of whether their elements are primitive or reference. Reference arrays have null default slots, primitive arrays have their own default values; multi-dimensional arrays are arrays of arrays.
- **Array covariance** allows `String[]` to be used as `Object[]`, but the runtime checks writes and can throw `ArrayStoreException`.
- `null` can be assigned, compared, and cast; only operations requiring a real object risk `NullPointerException`.

### Specification References

- [Java Virtual Machine Specification §2.4: Reference Types and Values (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.4) — classification of reference types and null reference.
- [JVM Specification §4.3: Descriptors (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3) — descriptors of class, interface, and array.
- [JVM Specification §6: JVM Instruction Set (Java SE 21)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html) — related opcodes such as `aastore`, `checkcast`, `instanceof`.
- [Java Language Specification §4: Types, Values, and Variables (Java SE 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html) — reference types, null type, variables, and types.
- [Java Language Specification §10: Arrays (Java SE 21)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html) — array rules, element types, and array store checks.
