# Reading an Inherited Static Field: The Type That Actually Declares the Field

## 1. The problem: which class does `Child.value` initialize?

Consider two classes:

~~~java
class Parent {
    static int value = 42;
}

class Child extends Parent {
}
~~~

Java allows reading the variable in two ways: **Parent.value** and **Child.value**. In both cases, **the field actually belongs to Parent**: Child only inherits access to it and does not receive a copy of the static variable.

According to **JLS §12.4.1**, when a static field that is **not a constant variable** is used, only the class/interface **that actually declares the field** is initialized by that access. Therefore, **Child.value** can cause **Parent to be initialized**, but does not by itself cause **Child to be initialized**. That is the central point of this lesson.

This lesson helps you identify the declaring class in the presence of inheritance, distinguish between field hiding and constant fields inlined by the compiler, read initialization traces, inspect behavior with reflection, and avoid confusing referencing Child by name with actually using a member of Child.

## 2. Three names that can differ

To analyze **Child.value**, we need to separate three questions:

| Concept | Question | Value in the example |
| --- | --- | --- |
| **Qualifier** | Which type name is written before the dot? | Child |
| **Declaring class** | Which class/interface *declares* the field selected by lookup? | Parent |
| **Initialization target** | Which type requires initialization due to this runtime static field read? | Parent |

You should not conclude which type needs to be initialized simply by looking at the name to the left of the dot.

If **Child** does not declare value, member lookup finds the field inherited from **Parent**. There is no field-overriding mechanism like there is for instance methods. If Child later declares a field of its own with the same name, it **hides** Parent's field: at that point, **Child.value** and **Parent.value** are two different fields.

### 2.1 Static fields are state of the type declaration

A static field is not copied into a new storage slot for each subclass. If Parent declares **static int count**, then:

~~~java
long before = Child.count;
Child.count = 30;
long after = Parent.count;
~~~

Both the read and the assignment here target **Parent.count** (assuming Child does not declare count itself and the type of count is compatible). The value of **after** will be 30. No independent **Child.count** exists in this case.

### 2.2 Initialized does not mean loaded

Even when **Child** has not yet executed its static initializer, the JVM may already have **loaded** or **linked** Child. Loading finds/creates the class representation; linking verifies, prepares, and resolves references; initialization is what executes static logic. This lesson measures and explains **initialization conditions**, and does not use log line numbers to assert the exact timing of loading or linking.

## 3. Initialization rules from the Java Language Specification

For a type **T**, initialization occurs immediately before the notable active-use actions:

1. T is a class and an instance of T is created.
2. A static method **declared by T** is invoked.
3. A static field **declared by T** is assigned.
4. A static field **declared by T** is used, and the field is not a **constant variable**.

When class T is initialized, the JVM initializes any uninitialized superclasses of T first. Superinterfaces that declare default methods also have related rules. Interface initialization does not automatically initialize all superinterfaces.

For **Child.value**, where value is declared only by Parent, case 4 applies to **Parent**, not Child.

~~~text
Parent
  ├─ static int value = 42;
  └─ static { ... }    ← code that runs when Parent is initialized
       ▲
       │ extends
       │
Child
  └─ static { ... }    ← does not run just from reading Parent.value

        read Child.value
               │
               ▼
    lookup → Parent.value
               │
               ▼
    initialize Parent if needed
               │
               ▼
        read Parent.value
~~~

The reverse rule to remember: **new Child()** or an active use of **a field declared by Child itself** causes Child to initialize; in that case, Parent must be initialized before Child. This does not mean that reading an inherited field automatically initializes the entire inheritance branch.

## 4. Runnable example 1: reading an inherited field

Create the file **InheritedStaticFieldDemo.java**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int count = initializeCount();

        static int initializeCount() {
            System.out.println("Parent: initialize count");
            return 42;
        }

        static {
            System.out.println("Parent: static block");
        }
    }

    static class Child extends Parent {
        static int own = 7;

        static {
            System.out.println("Child: static block");
        }
    }

    public static void main(String[] args) {
        System.out.println("1. Before inherited field");
        System.out.println("2. Child.count = " + Child.count);
        System.out.println("3. After inherited field");
        System.out.println("4. Parent.count = " + Parent.count);
        System.out.println("5. Child.own = " + Child.own);
        System.out.println("6. Child.count again = " + Child.count);
    }
}
~~~

Run with JDK 17+:

~~~bash
javac InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

Exact stdout:

~~~text
1. Before inherited field
Parent: initialize count
Parent: static block
2. Child.count = 42
3. After inherited field
4. Parent.count = 42
Child: static block
5. Child.own = 7
6. Child.count again = 42
~~~

### Explanation of the checkpoints

- When line 1 is printed, there has not yet been any static field read from Parent or Child.
- To evaluate **Child.count** on line 2, the program needs the field **Parent.count**. The JVM initializes Parent: first executing **initializeCount()**, then the static block in the order they appear in Parent's declaration. The printed result is 42.
- After line 3, **Child: static block** has not appeared. Reading an inherited static field does not cause initialization of Child.
- Line 4 reads the same variable Parent.count again, so it does not initialize Parent a second time.
- Line 5 reads **Child.own**; because **own is declared by Child** and is not a constant variable, the JVM initializes Child. Parent is already initialized, so only Child's line is printed.
- Line 6 reads a field belonging to Parent that has already been initialized, so there are no more static messages.

**Key point to understand:** the output proves when the **static initializers** are executed. It does not claim that before line 5, Child had never been loaded or never been linked.

## 5. How Java selects a field: member lookup and declaring class

Suppose:

~~~java
class Base {
    public static long total = 100;
}

class Derived extends Base {
}
~~~

Both **Base.total** and **Derived.total** access the field declared by Base:

~~~java
long first = Base.total;
long second = Derived.total;
~~~

If **Derived** has not declared a field with the same name, there is no runtime decision based on whether an object belongs to Derived or Base. The field is **statically bound** according to Java's member lookup rules.

Writing the subclass name can lead a reader to think that a static initializer of Derived must run. In reality, the selected field is still **Base.total**.

You should not claim that the compiler must always emit the exact same constant pool reference for both expressions. Bytecode can contain symbolic references and be handled by JVM field resolution according to the specification rules. What matters is **which declaration the field actually resolves to**.

### 5.1 Reading and writing an inherited field

With Base.total above:

~~~java
Derived.total = 250;
System.out.println(Base.total); // 250
~~~

This is still an assignment to and read of **Base.total**. If Base is not yet initialized, assigning to Base's static field must trigger initialization of Base before updating it. No initialization of Derived is required merely because the syntax uses the name Derived.

### 5.2 Writing with the declaring class name is clearer

When you already know the field belongs to Base, you should write **Base.total**. This reveals where the variable is owned, makes initialization timing easier to spot during code review, and avoids misunderstandings if someone adds a field with the same name to a subclass.

## 6. Using a reference variable to access a static field

Java allows using a primary expression to the left of the dot when accessing a static field:

~~~java
Derived reference = null;
long value = reference.total;
~~~

This is valid syntax, although an IDE may warn about it. Because total is static, the value of **reference** is not dereferenced to obtain the field. If reference is null, the read **does not throw NullPointerException** simply because the reference is null.

According to **JLS §15.11.1**, the primary expression must still be **evaluated**, though its result is discarded when the field is static. This is especially important if the qualifier has a side effect.

Illustrative example:

~~~java
static Derived obtainReference() {
    System.out.println("qualifier evaluated");
    return null;
}

// Placed inside a method:
long result = obtainReference().total;
~~~

If this expression is executed, the line **qualifier evaluated** still appears. After evaluating the qualifier, the read still accesses the field **Base.total** and only requires initialization of Base if needed.

**Distinction:** if the field is non-static, accessing it through a null reference can throw NullPointerException; and with **new Derived().total**, the **new Derived()** operation itself causes Derived to be initialized before the static field is read, so that is an **unsuitable** example for testing the trigger of field access in isolation.

**Recommendation:** a static field should be accessed through its declaring type name such as **Base.total**, not through a reference or a subclass name if you want to avoid misunderstandings.

## 7. Important exception: compile-time constants do not trigger initialization

The active-use rule for **reading a static field** excludes a **constant variable**.

According to JLS §4.12.4, a constant variable is a **final** variable of **primitive** type or type **String** that is initialized with a **constant expression**. For such fields, javac normally embeds the constant value directly into the caller's bytecode (inlining) rather than emitting a runtime field read.

| Static declaration | Is it a constant variable? | Does reading it by itself trigger initialization? |
| --- | --- | --- |
| **static final int LIMIT = 100;** | Yes | No. |
| **static final String NAME = "Java";** | Yes | No. |
| **static final long MASK = 1L << 3;** | Yes | No. |
| **static int count = 100;** | No | Yes, if the class is not yet initialized. |
| **static final int SIZE = Integer.parseInt("100");** | No | Yes. |
| **static final Integer BOXED = 100;** | No | Yes. |
| **static final Object TOKEN = new Object();** | No | Yes. |

The **final** keyword does not by itself create a constant variable. A field whose value is computed only at runtime, or a field of type Object/Integer, does not fall under this exception.

### 7.1 Runnable example 2: inherited constants vs. runtime-computed field

Create **InheritedConstantDemo.java**:

~~~java
public class InheritedConstantDemo {
    static class Parent {
        static {
            System.out.println("Parent initialized");
        }

        static final int LIMIT = 64;
        static final String NAME = "core";
        static final int COMPUTED = compute();

        static int compute() {
            System.out.println("Parent.compute()");
            return 9;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("limit = " + Child.LIMIT);
        System.out.println("name = " + Child.NAME);
        System.out.println("computed = " + Child.COMPUTED);
    }
}
~~~

~~~bash
javac InheritedConstantDemo.java
java InheritedConstantDemo
~~~

Stdout:

~~~text
limit = 64
name = core
Parent initialized
Parent.compute()
computed = 9
~~~

Explanation:

1. Parent.LIMIT and Parent.NAME are **constant variables**. Reading them through the name **Child** does not on its own initialize Parent or Child.
2. **COMPUTED** is not a compile-time constant because its initializer calls a method. Reading **Child.COMPUTED** causes the JVM to initialize **Parent**.
3. In Parent, the static block appears before the declaration of COMPUTED; therefore, **Parent initialized** is printed first, followed by **Parent.compute()**.
4. Child does not declare any field being read, so **Child initialized** does not appear.

### 7.2 Consequences of inlining when upgrading a library

Suppose a library defines **public static final int LIMIT = 64**. A compiled client may carry the value 64 inside its bytecode. If the library changes LIMIT to 128 without recompiling the client, the client may still see 64. This differs from a static field that is not a constant variable, which is read from the runtime definition.

When designing an API, use a constant variable for constants that are immutable by contract; do not treat it as a configuration mechanism that can be changed independently at deployment time.

## 8. Field hiding: when Child declares the same name

If Child has its own declaration:

~~~java
class Parent {
    static int score = 10;
}

class Child extends Parent {
    static int score = 20;
}
~~~

At this point, **Parent.score** and **Child.score** are two independent fields. Field lookup selects based on the type appearing in the source code, not virtual overriding.

- **Parent.score** → reads Parent's field.
- **Child.score** → reads Child's field.
- **Parent ref = new Child(); ref.score** → reads Parent.score based on the **static type Parent**.
- **Child ref = new Child(); ref.score** → reads Child.score based on the **static type Child**.

When reading a field declared by Child, the JVM initializes Child if it is not yet initialized. Initializing Child also requires its superclass Parent to be initialized first if needed.

### 8.1 Runnable example 3: field hiding has two storage slots

Create **StaticFieldHidingDemo.java**:

~~~java
public class StaticFieldHidingDemo {
    static int initial(String owner, int value) {
        System.out.println(owner + " field initialized");
        return value;
    }

    static class Parent {
        static int score = initial("Parent", 10);
    }

    static class Child extends Parent {
        static int score = initial("Child", 20);
    }

    public static void main(String[] args) {
        Parent parentRef = null;
        Child childRef = null;

        System.out.println("parentRef.score = " + parentRef.score);
        System.out.println("childRef.score = " + childRef.score);
        System.out.println("Parent.score = " + Parent.score);
        System.out.println("Child.score = " + Child.score);
    }
}
~~~

~~~bash
javac StaticFieldHidingDemo.java
java StaticFieldHidingDemo
~~~

Stdout:

~~~text
Parent field initialized
parentRef.score = 10
Child field initialized
childRef.score = 20
Parent.score = 10
Child.score = 20
~~~

When **parentRef.score** is read for the first time, Parent is initialized. When **childRef.score** is read, Child is initialized because score is declared by Child. Parent was already initialized earlier. Both references are null, yet valid static accesses do not dereference null.

This example illustrates field hiding. Real-world code should write **Parent.score** and **Child.score** for clarity.

### 8.2 Do not confuse field hiding with method overriding

| Syntax | Primary mechanism |
| --- | --- |
| **ref.field** | The field is selected by the **static type** of ref and member lookup. |
| **ref.instanceMethod()** | Methods can be overridden; **runtime dispatch** typically selects the implementation based on the actual object. |
| **Child.field** inherited from Parent | Still a field belonging to Parent. |
| **Child.field** declared by Child itself | A different field from Parent.field; Child is the owner. |

Do not apply the principle of **instance method polymorphism** to static fields.

## 9. Reflection: checking where a field is actually declared

In Java Reflection, there are three relevant APIs:

- **Class.getField(name)** searches **public fields**, including inherited public fields.
- **Class.getDeclaredField(name)** searches only fields **declared by the Class being inspected** (regardless of public/private), not inherited fields.
- **Field.getDeclaringClass()** returns the Class/interface **that actually contains the field declaration**.

That is how you verify the owner instead of guessing from the **Child.field** syntax.

### 9.1 Runnable example 4: reflection and initialization

Create **InheritedFieldReflectionDemo.java**:

~~~java
import java.lang.reflect.Field;

public class InheritedFieldReflectionDemo {
    static class Parent {
        public static int LEVEL = initialize();

        static int initialize() {
            System.out.println("Parent initialized");
            return 5;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        Field field = Child.class.getField("LEVEL");

        System.out.println("declaring class = "
                + field.getDeclaringClass().getSimpleName());
        System.out.println("declared by Child = "
                + (field.getDeclaringClass() == Child.class));

        try {
            Child.class.getDeclaredField("LEVEL");
            System.out.println("Child declares LEVEL");
        } catch (NoSuchFieldException expected) {
            System.out.println("Child does not declare LEVEL");
        }

        System.out.println("reflected value = " + field.get(null));
    }
}
~~~

~~~bash
javac InheritedFieldReflectionDemo.java
java InheritedFieldReflectionDemo
~~~

Stdout:

~~~text
declaring class = Parent
declared by Child = false
Child does not declare LEVEL
Parent initialized
reflected value = 5
~~~

**Child.class** and metadata lookup do not cause Child to be initialized. **getField("LEVEL")** returns the public field inherited from Parent; **getDeclaredField("LEVEL")** on Child does not find it because Child does not declare LEVEL itself. When **field.get(null)** reads the value of the static field, Parent is initialized before returning 5. There is no **Child initialized** line.

**Note:** other reflection operations such as reading a static field, invoking a static method, or instantiating an instance can trigger initialization. Do not generalize that "reflection never initializes a class"; you must check the specific API and operation.

## 10. Interface static fields also follow the owner

A field declared in an interface is implicitly **public static final**. However, it is not necessarily a constant variable: its initializer can be a method call.

Example:

~~~java
interface ParentFlags {
    int DYNAMIC = compute();

    static int compute() {
        System.out.println("ParentFlags initialized");
        return 8;
    }
}

interface ChildFlags extends ParentFlags {
    String LABEL = announce();

    static String announce() {
        System.out.println("ChildFlags initialized");
        return "child";
    }
}
~~~

When the program reads **ChildFlags.DYNAMIC**, the field is declared by **ParentFlags** and is not a constant variable. The JVM initializes **ParentFlags**, and does not initialize ChildFlags on its own simply because the qualifier name is ChildFlags.

If **ChildFlags.LABEL** is read afterward, that field is declared by ChildFlags and is not a constant variable, so ChildFlags is initialized. Initializing an interface **does not automatically** initialize all of its superinterfaces, unlike a class and its superclasses.

Also be careful when a class implements multiple interfaces that declare a field with the same name: **member lookup can be ambiguous**, causing a compile-time error. Access it through the declaring interface name to make the intent clear.

## 11. Diagnostic workflow for accessing Sub.FIELD

When you need to predict which static block runs, ask in order:

1. **Which member does FIELD belong to as selected by Java?** Check whether Child declares it itself or inherits it. If there is field hiding, determine the exact field through the static type and member lookup.
2. **Is FIELD actually static?** Instance fields have different access rules.
3. **What is the declaring type of the field?** It may be a superclass or interface, even though the code writes **Sub.FIELD**.
4. **Is FIELD a constant variable?** If it is final + primitive/String + constant expression, reading it does not trigger initialization on its own.
5. **Has the declaring type already been initialized?** If not, and the field requires runtime access, the JVM will initialize that type.
6. **Has another action triggered Sub beforehand?** For example, new Sub(), calling a static method declared by Sub, or reading Sub's own field.
7. **If Sub is initialized, have its superclasses already been initialized?** The JVM ensures that relevant superclasses are initialized before Sub.
8. **Do multiple class loaders define classes with the same name?** Initialized state is tied to each runtime Class definition, not just the class name string.

A diagram:

~~~text
    Encounter Sub.FIELD
         │
         ▼
  Lookup FIELD
         │
         ├── declared by Sub ──────→ owner = Sub
         │
         └── inherited from Parent → owner = Parent
                                     │
                                     ▼
                         static? constant variable?
                             │               │
                            No              Yes
                             │               │
                    other rules      reading a constant
                                     does not require init on its own
                             │
                             ▼
                   static, non-constant
                             │
                             ▼
                     initialize owner
                      if not yet init
                             │
                             ▼
                    read or assign field
~~~

Here, "owner" refers to the class/interface that declares the field, not the object used as the qualifier.

## 12. Comparing easily confused operations

Suppose **Parent** declares **static int X**, **static final int LIMIT = 7**; **Child extends Parent** and declares **static int OWN**:

| First operation | Type requiring initialization due to the operation | Why |
| --- | --- | --- |
| **int a = Child.X;** | Parent | X is declared by Parent and is not a constant. |
| **Child.X = 9;** | Parent | Assigns a static field declared by Parent. |
| **int a = Parent.X;** | Parent | Same field Parent.X. |
| **int n = Child.LIMIT;** | None from reading the constant | LIMIT is a constant variable. |
| **int a = Child.OWN;** | Parent then Child if both are not yet initialized | OWN belongs to Child; initializing Child must initialize its superclass. |
| **new Child()** | Parent then Child if not yet initialized | Active use from creating a Child instance. |
| **Class<?> c = Child.class;** | Does not initialize Child on its own | A class literal is not an initialization trigger. |
| **Class.forName(binaryNameChild)** | Child and superclass prerequisites | The single-argument form requires initialization. |
| **Class.forName(binaryNameChild, false, loader)** | Does not actively initialize Child | Overload with boolean false. |

If Child is a nested class, its binary name usually contains **$**; you cannot use the simple name **"Child"** regardless of package/nesting in Class.forName. The goal of the table is to compare **initialization causes**, not to replace binary naming rules.

## 13. Inspecting bytecode with javap

After compiling the examples:

~~~bash
javap -c -p InheritedStaticFieldDemo
javap -c -p InheritedConstantDemo
~~~

A runtime static field read typically uses the **getstatic** bytecode instruction, and an assignment typically uses **putstatic**. The compiler can inline **constant variables** using constant-loading instructions, so there is no corresponding getstatic at the caller.

However, you should not infer from a name seen in bytecode that that class **is definitely initialized**: the JVM performs field resolution to determine the actual declaration. Nor should you assume that every compiler emits identical constant pool references even when the Java semantics are the same.

When you want to observe loading on HotSpot/a JVM supporting Unified Logging, you can try:

~~~bash
java -Xlog:class+load=info InheritedStaticFieldDemo
java -Xlog:help
~~~

**class+load** can show loaded classes and their sources. Evidence that a **static initializer ran** still needs to be observed separately from the program. The logging format and level of detail depend on the JVM/JDK; avoid treating a class-loading log line as proof of initialization.

## 14. Common errors and misconceptions

### "Reading Child.counter does not show Child's static block."

Look up where **counter** is declared. If Parent declares it, Java is accessing **Parent.counter**, and the initialization rules require only Parent. If Child declares a field with the same name itself, that is field hiding and the conclusion differs.

### "static final is definitely initialized when read."

Incorrect for **constant variables**; reading **static final int X = 5** does not on its own initialize the class. By contrast, **static final int X = Integer.parseInt("5")** is computed at runtime and can still trigger initialization. Types like Integer/Object are also not compile-time constant variables.

### "I saw both Parent and Child initialized after reading an inherited field."

There may have been **another active use** of Child beforehand, such as **new Child()** or **Child.OWN**. To verify, create a new simple program and only read **Child.inheritedField** before any other action. Once static initialization has succeeded once, subsequent reads do not run the static blocks again.

### "reference.field is static, so a null reference must throw NullPointerException."

Incorrect. When the field is static, the qualifier's value is discarded after the expression is evaluated. If the qualifier has a side effect or throws an error during evaluation, the side effect/error still occurs. For instance fields, the null-dereference rule is different.

### "The class loaded in this run, so its static block must have run."

No. Loading and initialization are distinct phases. A class may have been loaded/linked without being initialized yet. Do not collapse all three concepts into the single phrase "load class".

### "A JAR changed a constant, yet the client still sees the old value."

If the constant variable was inlined by the compiler, the client must be recompiled. This is a consequence of binary compatibility and how constants are encoded, not a subclass initialization bug.

### "NoSuchFieldError occurs when using Sub.FIELD."

That may be an issue with mismatched binary versions, class loaders, or field resolution (for example, the runtime library no longer contains the field the compiled caller references). Check the classpath/module path and artifact versions; do not automatically blame the initialization rules.

## 15. Knowledge self-check

**1.** Parent declares **static int cache = 1**, Child extends Parent and has a static block. Which class is initialized the first time **Child.cache** is printed?

**Answer:** Parent. cache actually belongs to Parent. Child is not initialized solely because of this read.

**2.** If Child declares **static int cache = 2** itself, what happens the first time Child.cache is read?

**Answer:** This is a new field belonging to Child. If neither class is initialized yet, the superclass Parent is initialized first, followed by Child.

**3.** Parent declares **static final String VERSION = "v1"**. Why does Child.VERSION not initialize Parent on its own?

**Answer:** VERSION is a constant variable (final, type String, constant expression). Reading a constant is not an active use that triggers initialization.

**4.** Does **Parent p = new Child(); System.out.println(p.score);** select score by static type or runtime type?

**Answer:** By the static type Parent and field lookup rules. However, **new Child()** already initializes Child and its superclass beforehand; you need to separate that effect when analyzing output.

**5.** Why does **Child.class.getField("LEVEL").getDeclaringClass()** return Parent.class?

**Answer:** getField can find inherited public fields, while getDeclaringClass returns where the field is actually defined.

**6.** Parent declares **static final Object TOKEN = new Object()**. Does reading **Child.TOKEN** trigger Parent if it is not yet initialized?

**Answer:** Yes. Object is not a primitive or String constant variable; final is not enough to exclude initialization.

**7.** Interface A declares **int N = compute()**, and interface B extends A. Which interface is initialized when B.N is read for the first time?

**Answer:** A, because N is declared by A and is not a constant variable. B is not initialized on its own merely because B appears in the syntax.

**8.** If both Parent.field and Child.field have the same name and are each declared by their respective class, will changing the reference variable from type Parent to Child change which field is read?

**Answer:** It can change: field lookup follows the static type, so the two different declarations can be selected. It is not dynamic overriding.

## 16. Key takeaways

**Core rule:** When accessing an inherited static field, identify the **class/interface that actually declares the field**, rather than relying on the subclass name before the dot.

- An inherited field still belongs to its declaring type; there is no automatic static copy in the subclass.
- Reading or assigning a static field at runtime requires initializing the **declaring type** if needed.
- If a subclass declares a field with the same name itself, that is **field hiding** and it is a separate field.
- Compile-time constant variables are an exception: reading a constant does not trigger initialization on its own.
- Java field access is statically bound by type, unlike instance method overriding.
- Reflection's **getDeclaringClass()** helps find the owner; **getField** can find inherited fields, whereas **getDeclaredField** only finds fields declared by the type itself.
- Using the declaring class name when writing code helps avoid confusion about initialization state and order.

### References

- **JLS §12.4.1, When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4.1
- **JLS §4.12.4, final Variables / Constant Variables:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.12.4
- **JLS §15.11.1, Field Access Using a Primary:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.11.1
- **JLS §8.3.1.1, static Fields:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.3.1.1
- **Java SE 21 reflection Field API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html
