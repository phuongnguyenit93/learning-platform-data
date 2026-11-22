# Field and `static` Method Hiding by Declared Type in Java

When a subclass declares a **field with the same name** as a field inherited from its superclass, Java calls this **field hiding**. When a subclass declares a **static method** with a signature matching a static method of its superclass, this is **static method hiding**. Both mechanisms are easily confused with **method overriding**, but their member selection rules differ fundamentally.

~~~java
class Parent {
    static String category = "PARENT";

    static String kind() {
        return "Parent.kind";
    }

    String describe() {
        return "Parent.describe";
    }
}

class Child extends Parent {
    static String category = "CHILD"; // Field hiding.

    static String kind() {           // Static method hiding.
        return "Child.kind";
    }

    @Override
    String describe() {              // Instance method overriding.
        return "Child.describe";
    }
}
~~~

If a reference is declared as `Parent reference = new Child();`, the expressions:

~~~java
reference.category
reference.kind()
reference.describe()
~~~

**do not always select Child**. The field and static method are selected according to the **compile-time type of the `reference` expression** (Parent), whereas the overridden instance method is dispatched according to the **actual runtime object** (Child). This is the core distinction of this lesson.

This lesson belongs to Java Core — **Class & Object / Inheritance and Polymorphism**, using **Java 17+**. Each standalone runnable program has a specific filename, `javac`/`java` commands, and stdout. Snippets that are not standalone or intentionally fail to compile will be noted.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **field hiding**, **static method hiding**, and **instance method overriding**.
2. Understand the concepts of the **declared/compile-time type** of a reference and the **runtime class** of an object.
3. Predict which field and static method are selected when a `Parent` variable points to a `Child` object.
4. Understand why `@Override` cannot be used for static method hiding.
5. Explain the effect of `(Parent)` and `(Child)` casts on **member selection**.
6. Distinguish between **selecting a field by name and compile-time type** and how the actual object stores instance fields.
7. Know that a subclass declaring a field with the same name can create **two distinct fields**, rather than modifying a single field.
8. Know when a static field/method is inherited and when it is hidden.
9. Distinguish `Parent.staticMember` from `reference.staticMember`; recognize that syntax via an object is misleading.
10. Predict cases where a **null reference** can still be used as a qualifier to access a static member.
11. Understand that **the qualifier expression can still be evaluated**, even when the reference value is not needed for static access.
12. Distinguish **overloading** selected at compile time from **overriding** dispatched at runtime.
13. Know the compatibility requirements for access, return type, `throws`, `final`, and static/instance when hiding.
14. Know how static members in **interfaces** differ from class static methods regarding inheritance.
15. Understand class initialization when reading an inherited static field through a subclass name.
16. Avoid using field hiding as a “data polymorphism” mechanism.
17. Design alternative solutions using instance methods, constructor injection, or clearly named methods.
18. Write tests that distinguish compile-time member selection from runtime virtual dispatch.

## 2. Two Kinds of “Types” to Distinguish

Example:

~~~java
Parent ref = new Child();
~~~

Two pieces of information coexist:

- The **declared/compile-time type** of the expression `ref` is **Parent**.
- The **runtime class** of the object that `ref` points to is **Child**.

Diagram:

~~~text
  local variable
  ref : Parent
      |
      v
  +--------------------+
  | Child object       |
  | extends Parent     |
  +--------------------+

  ref.field       -> Look up field by compile-time type Parent.
  ref.staticCall() -> Select static method by compile-time type Parent.
  ref.virtualCall()-> Runtime dispatch to override in Child if valid.
~~~

Using `new Child()` **does not cause the compiler to change the declaration of `ref` to Child**. The compiler only knows that `ref` has type Parent; because Child is a subtype of Parent, the assignment is valid.

### Short Rule to Remember

> **Fields and static methods are not polymorphic based on the runtime receiver. Only validly overridden instance methods have dynamic dispatch.**

This is a foundational practical rule, though Java's details regarding overloads, method signatures, access, hiding, and inheritance still require considering the context.

## 3. Precise Terminology

| Concept | Member | What Happens |
| --- | --- | --- |
| **Field hiding** | Field with the same name in a subclass | The new declaration hides the inherited field when looked up by name in the appropriate context |
| **Static method hiding** | Static method with a matching signature in a subclass | The subclass method hides the superclass static method; selection does not rely on the actual receiver object |
| **Instance method overriding** | Instance method in a subclass overriding an inherited method | Dispatches to the appropriate implementation based on the runtime object |
| **Method overloading** | Methods with the same name but different parameter lists | Selects the matching overload primarily based on compile-time argument types |
| **Shadowing** | A local/parameter declaration hiding another declaration's name in scope | Name lookup can prioritize the local variable over the field |
| **Upcasting** | Assigning a Child reference to a Parent variable | The actual object is not sliced/transformed into a Parent object |
| **Downcasting** | Casting a Parent reference to Child when the runtime object is actually compatible | Allows accessing members according to type Child; may throw ClassCastException |

The word **hiding** does not mean Java removes Parent's field/method from runtime. It refers to **which declaration is chosen during name resolution** in a compile-time context.

## 4. Field Hiding with Two Static Fields of the Same Name

Example:

~~~java
class Parent {
    static int value = 10;
}

class Child extends Parent {
    static int value = 20;
}
~~~

There are **two separate static variables**:

- `Parent.value` is declared by Parent.
- `Child.value` is declared by Child.

They can hold different values. Changing `Child.value` does not automatically change `Parent.value`.

### Accessing via Class Name

~~~java
System.out.println(Parent.value); // 10.
System.out.println(Child.value);  // 20.
~~~

This is the clearest approach.

### Accessing via Object Reference

~~~java
Parent p = new Child();
Child c = new Child();

System.out.println(p.value); // Parent.value, not Child.value.
System.out.println(c.value); // Child.value.
~~~

Java allows the `p.value` syntax for a static field (when the field is accessible), but it is **discouraged** because it easily misleads readers into thinking the static field belongs specifically to object p. Use `Parent.value` or `Child.value`.

## 5. Runnable Program: Static Field Hiding

Save the file **`StaticFieldHidingDemo.java`**:

~~~java
public class StaticFieldHidingDemo {
    static class Parent {
        static int score = 10;
    }

    static final class Child extends Parent {
        static int score = 20;
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = new Child();

        System.out.println("Parent=" + Parent.score);
        System.out.println("Child=" + Child.score);
        System.out.println("parentView=" + parentView.score);
        System.out.println("childView=" + childView.score);

        Child.score = 99;

        System.out.println("after Parent=" + Parent.score);
        System.out.println("after Child=" + Child.score);
        System.out.println("after parentView=" + parentView.score);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFieldHidingDemo.java
java StaticFieldHidingDemo
~~~

Stdout:

~~~text
Parent=10
Child=20
parentView=10
childView=20
after Parent=10
after Child=99
after parentView=10
~~~

### Explanation

1. `Parent.parentView` is not a new object beyond what `new Child()` creates; the variable `parentView` is declared with type Parent but holds a reference to a Child object.
2. `parentView.score` is resolved to `Parent.score`.
3. `childView.score` is resolved to `Child.score`.
4. `Child.score = 99` only changes Child's field.
5. `Parent.score` remains 10; `parentView.score` continues to read Parent.score.

Even though both references point to **objects whose runtime class is Child**, static field lookup does not dispatch based on the runtime object.

## 6. What If Child Does Not Declare a Field with the Same Name?

~~~java
class Parent {
    static int count = 5;
}

class Child extends Parent {
    // Does not declare count.
}
~~~

In an allowed context, `Child.count` refers to **the same field declared in Parent**, without creating a new field in Child.

~~~java
Parent.count = 7;
System.out.println(Child.count); // 7.
Child.count++;
System.out.println(Parent.count); // 8.
~~~

Two situations must be distinguished:

| Does Child declare its own `static int count`? | What is `Child.count` actually? |
| --- | --- |
| No | Refers to the field inherited from Parent |
| Yes | Refers to Child's own field, hiding Parent's field |

**Do not say:** “Each subclass always gets a copy of its superclass's static fields.” Fields that are not redeclared belong to the superclass that originally declared them.

## 7. Runnable Example: An Inherited Static Field Is Only One Field

Save **`InheritedStaticFieldDemo.java`**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int counter = 1;
    }

    static final class Child extends Parent {
    }

    public static void main(String[] args) {
        System.out.println("start=" + Parent.counter);
        Child.counter += 4;
        System.out.println("Parent=" + Parent.counter);
        System.out.println("Child=" + Child.counter);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

Stdout:

~~~text
start=1
Parent=5
Child=5
~~~

In this program, Child does not declare its own counter. `Parent.counter` and `Child.counter` are the same static field in Parent.

As a matter of style, use the name of the **class that declares the field**: `Parent.counter`. The syntax `Child.counter` can mislead readers into thinking counter belongs to Child.

## 8. How `static method hiding` Differs from `override`

Given:

~~~java
class Parent {
    static String identify() {
        return "Parent";
    }
}

class Child extends Parent {
    static String identify() {
        return "Child";
    }
}
~~~

`Child.identify()` **hides** `Parent.identify()`. A static call does not use dynamic dispatch based on the receiver object.

~~~java
Parent p = new Child();
Child c = new Child();

System.out.println(p.identify());      // Parent.
System.out.println(c.identify());      // Child.
System.out.println(Parent.identify()); // Parent.
System.out.println(Child.identify());  // Child.
~~~

Like static fields, the syntax `p.identify()` is semantically valid in these situations, yet misleading. You should call `Parent.identify()` and `Child.identify()`.

**Do not use `@Override` for static method hiding**: a static method does not override a superclass static method. Placing that annotation on a static method causes the compiler to report an error because there is no appropriate instance method to override.

## 9. Runnable Example: Static Hiding Contrasted with Instance Overriding

Save **`StaticVsInstanceDispatchDemo.java`**:

~~~java
public class StaticVsInstanceDispatchDemo {
    static class Parent {
        static String category() {
            return "Parent.static";
        }

        String describe() {
            return "Parent.instance";
        }
    }

    static final class Child extends Parent {
        static String category() {
            return "Child.static";
        }

        @Override
        String describe() {
            return "Child.instance";
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        System.out.println("p.static=" + parentView.category());
        System.out.println("c.static=" + childView.category());
        System.out.println("p.instance=" + parentView.describe());
        System.out.println("c.instance=" + childView.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticVsInstanceDispatchDemo.java
java StaticVsInstanceDispatchDemo
~~~

Stdout:

~~~text
p.static=Parent.static
c.static=Child.static
p.instance=Child.instance
c.instance=Child.instance
~~~

### What Does Each Call Select?

- `parentView.category()`: the compiler sees a Parent reference → selects `Parent.category()`.
- `childView.category()`: the compiler sees a Child reference → selects `Child.category()`.
- `parentView.describe()`: overridden instance method → runtime object Child → executes `Child.describe()`.
- `childView.describe()`: still executes Child.describe().

This is a program you need to master: **two references to the same object**, yet the static calls produce two different results due to compile-time types; the instance calls produce the same result due to runtime dispatch.

## 10. The Most Important Comparison Table

Suppose:

~~~java
Parent ref = new Child();
~~~

and Child declares corresponding members with the same names as Parent.

| Expression | Selection Mechanism | Typical Result |
| --- | --- | --- |
| `ref.staticField` | Field lookup by compile-time Parent | Parent.staticField |
| `ref.instanceField` | Field lookup by compile-time Parent | Parent.instanceField on the Child object |
| `ref.staticMethod()` | Static method resolution by compile-time Parent | Parent.staticMethod |
| `ref.instanceMethod()` | Dispatch by runtime Child if validly overridden | Child.instanceMethod |
| `Parent.staticMethod()` | Qualified name Parent | Parent.staticMethod |
| `Child.staticMethod()` | Qualified name Child | Child.staticMethod |
| `((Child) ref).staticField` | Compile-time qualifier after cast is Child | Child.staticField |
| `((Parent) ref).instanceMethod()` | Compile-time Parent, but virtual call | Child override still executes |

**Remember:** Casting only changes how the compiler interprets the expression; it does not automatically change the actual object. There is no “object slicing” when upcasting a Java reference, unlike some mechanisms in other languages.

## 11. Field Hiding Also Applies to Instance Fields

A learner might think only `static` fields are subject to hiding. In reality, **instance fields with the same name** can also be hidden.

~~~java
class Parent {
    String label = "parent field";
}

class Child extends Parent {
    String label = "child field";
}
~~~

A Child object can contain **two distinct instance fields**: the Parent.label part inherited in terms of state and Child.label declared by Child.

~~~java
Parent view = new Child();
System.out.println(view.label);          // parent field.
System.out.println(((Child) view).label); // child field.
~~~

The runtime object is still Child in both expressions. Field lookup is resolved **not by dynamic dispatch**.

### How Does This Differ from Static Fields?

- With **instance field hiding**, each Child object has its own corresponding instance fields; reading Parent.label vs. Child.label on **the same object** yields two different values.
- With **static field hiding**, the fields belong to **two runtime classes**, not per object.
- Both select the declaration according to the **compile-time qualifier type**.

## 12. Runnable Example: Instance Field Hiding Is Not Polymorphic

Create **`InstanceFieldHidingDemo.java`**:

~~~java
public class InstanceFieldHidingDemo {
    static class Parent {
        String name = "parent";

        String readName() {
            return name;
        }
    }

    static final class Child extends Parent {
        String name = "child";

        @Override
        String readName() {
            return name;
        }
    }

    public static void main(String[] args) {
        Parent p = new Child();
        Child c = (Child) p;

        System.out.println("p.field=" + p.name);
        System.out.println("c.field=" + c.name);
        System.out.println("p.method=" + p.readName());

        p.name = "P2";
        c.name = "C2";

        System.out.println("after p.field=" + p.name);
        System.out.println("after c.field=" + c.name);
        System.out.println("after p.method=" + p.readName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceFieldHidingDemo.java
java InstanceFieldHidingDemo
~~~

Stdout:

~~~text
p.field=parent
c.field=child
p.method=child
after p.field=P2
after c.field=C2
after p.method=C2
~~~

### Why Are There Two Field Values?

`p.name` accesses the `Parent.name` field inside the Child object. `c.name` accesses `Child.name` inside the same Child object. When `p.readName()` is called, virtual dispatch selects `Child.readName()`, and the body in Child reads `Child.name`.

**Do not conclude:** “since the field is inside Child, p.name will automatically use Child.name.” Fields are not overridden. If you need polymorphism to retrieve data, provide a **method such as `name()` and override that method**.

## 13. Casting Changes Compile-Time Member Lookup Without Creating a Different Object

~~~java
Parent p = new Child();
System.out.println(p.category());
System.out.println(((Child) p).category());
~~~

If Parent.category and Child.category are static methods with the same signature:

- `p.category()` selects Parent.category.
- `((Child) p).category()` selects Child.category.
- Both statements use the **same runtime object** of p (after the cast).

### Downcasting Can Fail

~~~java
Parent parentOnly = new Parent();
// Child invalid = (Child) parentOnly; // Compiles, but throws ClassCastException.
~~~

A cast performs a runtime check when needed. Do not use a downcast just to control which static method is selected: if you actually want to call Child's static method, write **`Child.category()`**, which is clearer and does not depend on a reference.

### Upcasting Does Not Remove Overriding

~~~java
Parent view = (Parent) new Child();
view.describe();
~~~

If Child overrides `describe`, the virtual call still executes Child.describe. Casting to Parent does not “freeze” dispatch at the Parent implementation.

## 14. `super.field` and `super.method()`

In Child's instance code, `super.field` can be used to access a **field declared in the superclass** when that field is accessible.

~~~java
class Parent {
    protected int points = 10;
}

class Child extends Parent {
    private int points = 20;

    int sum() {
        return super.points + this.points;
    }
}
~~~

`super.points` and `this.points` select two different fields. For static fields, in valid contexts, `super.staticField` may be syntactically accepted by Java, but **you should use `Parent.staticField`** to express its class-level nature.

### `super.instanceMethod()` Differs from Static Hiding

If Child overrides an instance method, `super.method()` in Child's body can invoke the specific superclass implementation instead of virtual dispatch landing back on Child's own override.

For hidden static methods, use `Parent.method()` to explicitly call the superclass static method. No receiver object or cast is needed.

### Runnable Example: Selecting Two Fields Using `super`

Save **`SuperFieldAccessDemo.java`**:

~~~java
public class SuperFieldAccessDemo {
    static class Parent {
        protected int points = 10;
    }

    static final class Child extends Parent {
        private int points = 20;

        int sum() {
            return super.points + this.points;
        }

        String report() {
            return "Parent=" + super.points
                    + ", Child=" + this.points;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        System.out.println(child.report());
        System.out.println("sum=" + child.sum());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuperFieldAccessDemo.java
java SuperFieldAccessDemo
~~~

Stdout:

~~~text
Parent=10, Child=20
sum=30
~~~

Inside the same Child object, both Parent.points and Child.points exist. The `super` and `this` qualifiers clarify which declaration should be accessed.

## 15. When Is a Static Method Considered Hiding?

Within a class hierarchy, a static method in a subclass can **hide** a corresponding accessible static method in a superclass if it satisfies Java's rules regarding signatures, name clashes, return types, access, and checked exceptions.

Example:

~~~java
class Parent {
    public static Number sample() {
        return 1;
    }
}

class Child extends Parent {
    public static Integer sample() {
        return 2;
    }
}
~~~

`Child.sample()` hides `Parent.sample()` with a **covariant return type** Integer compatible with Number. There is no instance method override.

However, you should not assume that merely having **two methods with the same name** constitutes hiding:

- `sample()` and `sample(int)` are **overloads**, not the same signature.
- If one method is an instance method and the other is static, and their signatures clash as an override/hide, the compiler can reject it.
- Two private or inaccessible methods follow different inheritance rules and should not be assumed to have the same meaning of hiding.
- A static `final` method of Parent cannot be hidden by a method with the same signature in Child under the applicable rules.

## 16. Static and Instance Methods Cannot Replace Each Other Like Overrides

Intentionally incorrect:

~~~java
class Parent {
    static void ping() {}
}

class Child extends Parent {
    // void ping() {} // Error: an instance method cannot override/hide static ping.
}
~~~

The reverse direction:

~~~java
class Parent {
    void ping() {}
}

class Child extends Parent {
    // static void ping() {} // Error: a static method cannot override instance ping.
}
~~~

Java does not allow using the `static` keyword as a way to change the dispatch mechanism of an inherited method with the same signature without changing the contract.

### Placing `@Override` on a Static Method?

~~~java
class Parent {
    static void ping() {}
}

class Child extends Parent {
    // @Override // Error if attached to static ping.
    static void ping() {}
}
~~~

Static `ping` in Child **hides** static ping in Parent. The `@Override` annotation cannot be used because Child.ping does not override an instance method.

**Convention:** Use the class name as the qualifier; do not use a static method as a mechanism for runtime polymorphism.

## 17. Static Method Hiding, `final`, and Access

A method declared `final static` cannot be hidden by a subclass with a matching signature under Java rules:

~~~java
class Parent {
    public static final void stable() {}
}

class Child extends Parent {
    // public static void stable() {} // Invalid.
}
~~~

When Child validly hides an inherited static method, the new method must not **narrow access** in violation of Java rules:

~~~java
class Parent {
    public static void show() {}
}

class Child extends Parent {
    // static void show() {} // Error: weaker than public.
    public static void show() {}
}
~~~

In addition, the return type must be compatible, and checked exception declarations are constrained similarly to the compatibility rules for hiding/overriding. Do not simply change a modifier to bypass the compiler.

### Should You Hide a Superclass's Public Static Method?

Usually **no**, especially when the method represents a “variant” of behavior based on the object type. Use clear names (for example `createCsvFormatter`, `createJsonFormatter`) or a polymorphic instance method.

## 18. Runnable Example: Covariant Return in Static Hiding

Create the file **`StaticCovariantReturnDemo.java`**:

~~~java
public class StaticCovariantReturnDemo {
    static class Parent {
        public static Number example() {
            return 10;
        }
    }

    static final class Child extends Parent {
        public static Integer example() {
            return 20;
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        Number a = parentView.example();
        Integer b = childView.example();

        System.out.println("Parent result=" + a);
        System.out.println("Child result=" + b);
        System.out.println("names=" + Parent.example()
                + "/" + Child.example());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticCovariantReturnDemo.java
java StaticCovariantReturnDemo
~~~

Stdout:

~~~text
Parent result=10
Child result=20
names=10/20
~~~

`Parent.example()` returns Number, and Child.example returns the compatible subtype Integer. However, **static calls are still selected by the declared reference type**, with no runtime polymorphism.

An API designed for runtime polymorphism should use an instance method with a covariant return type and `@Override`, rather than relying on static hiding.

## 19. Checked Exception Constraints When Hiding

Suppose:

~~~java
class Parent {
    public static String read() throws java.io.IOException {
        return "parent";
    }
}

class Child extends Parent {
    public static String read()
            throws java.io.FileNotFoundException {
        return "child";
    }
}
~~~

The subtype `FileNotFoundException` is a checked exception subclass of `IOException`, so it can be compatible with the method in Parent.

However, Child cannot arbitrarily declare a broader checked exception such as `throws Exception` when hiding the corresponding method of Parent.

**Why?** The caller is compiled against the signature of the selected method. The checked exception contract must preserve the caller's ability to handle it, even though a static method does not undergo virtual dispatch.

If the method is called through a reference `Parent p`, the compile-time method chosen is Parent.read, and the caller handles `IOException` according to that declaration, even if the actual object is Child.

## 20. Static Field Hiding Is Not Limited to Primitive Fields

You can hide a reference field:

~~~java
class Parent {
    static String SOURCE = "parent";
}

class Child extends Parent {
    static String SOURCE = "child";
}
~~~

The two fields hold two separate reference values. Both String objects are immutable, but the **field references** are not final and can therefore be reassigned.

~~~java
Parent.SOURCE = "P2";
Child.SOURCE = "C2";
~~~

Each assignment updates the corresponding field. There is no mechanism to synchronize the two values just because they share the same field name.

### `static final` Can Also Undergo Field Hiding

~~~java
class Parent {
    static final int LIMIT = 10;
}

class Child extends Parent {
    static final int LIMIT = 20;
}
~~~

`Parent.LIMIT` and `Child.LIMIT` are two distinct declarations. Field hiding is not itself prohibited by `final` on a field. **`final` forbids reassigning the field itself**, not a subclass declaring **another field with the same name** under Java's language rules when valid.

This contrasts with a **final static method**: a `final` method is subject to the corresponding rule forbidding hiding/overriding.

## 21. Runnable Example: Static Final Constants with the Same Name

Create the file **`StaticFinalFieldHidingDemo.java`**:

~~~java
public class StaticFinalFieldHidingDemo {
    static class Parent {
        static final int LIMIT = 10;
    }

    static final class Child extends Parent {
        static final int LIMIT = 20;
    }

    public static void main(String[] args) {
        Parent p = new Child();
        Child c = (Child) p;

        System.out.println("Parent=" + Parent.LIMIT);
        System.out.println("Child=" + Child.LIMIT);
        System.out.println("p=" + p.LIMIT);
        System.out.println("c=" + c.LIMIT);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFinalFieldHidingDemo.java
java StaticFinalFieldHidingDemo
~~~

Stdout:

~~~text
Parent=10
Child=20
p=10
c=20
~~~

Both `LIMIT` fields are **compile-time constant variables** of type int in this example, so some uses may be replaced by the compiler with their constant values. That further emphasizes that **there is no runtime polymorphic value lookup** when reading a static field.

Do not treat declaring multiple constants with the same name in a hierarchy as a recommended API pattern; qualifying with the declaring class is clearer.

## 22. When a Static Method Exists, but the Subclass Just Wants a Method with a Different Name

In many projects, it is better to avoid collisions:

~~~java
class ParentTools {
    static String genericName() {
        return "general";
    }
}

class ChildTools extends ParentTools {
    static String specificName() {
        return "specific";
    }
}
~~~

Because the two methods have different names, there is no hiding of the same signature. It is clear which tool the caller is requesting.

However, using `extends` just to gain the superclass's utility static methods is usually poor design from an is-a modeling perspective. If a class only needs to use helpers, call the helper by class name or use composition; do not create an artificial inheritance hierarchy.

## 23. Accessing a Static Member Through a `null` Reference

A surprising property of Java:

~~~java
Parent p = null;
System.out.println(p.staticField);
p.staticMethod();
~~~

For an accessible static field/method, Java **does not dereference object p like an instance member access**, because the static member is selected by type. Therefore, a null `p` reference in this simple case **does not automatically cause a `NullPointerException` merely for being null**.

However, writing code like this is **discouraged**: it is hard to read and can cause learners to misunderstand.

### When the Qualifier Expression Has a Side Effect

~~~java
factory().staticMethod();
~~~

Java still evaluates the expression `factory()` according to language rules before the static call is performed, even though the returned **object value** is not needed to select the static method.

If `factory()` prints a log, updates a counter, or throws an exception, those things can still happen. Do not say “Java completely ignores everything before the dot” in a static access through an expression.

## 24. Runnable Example: `null` and Qualifier Side Effects

Create **`NullStaticAccessDemo.java`**:

~~~java
public class NullStaticAccessDemo {
    static class Parent {
        static String label = "PARENT";

        static String describe() {
            return "STATIC";
        }
    }

    static Parent returnNull() {
        System.out.println("qualifier evaluated");
        return null;
    }

    public static void main(String[] args) {
        Parent nothing = null;

        System.out.println("field=" + nothing.label);
        System.out.println("method=" + nothing.describe());

        System.out.println("via call=" + returnNull().label);
        System.out.println("via method=" + returnNull().describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullStaticAccessDemo.java
java NullStaticAccessDemo
~~~

Stdout:

~~~text
field=PARENT
method=STATIC
qualifier evaluated
via call=PARENT
qualifier evaluated
via method=STATIC
~~~

The call to `returnNull()` still executes and prints the log each time. However, accessing the static member **does not need to dereference null** the way an instance method or instance field does.

### Compared to Instance Access

If Parent has an instance method `instanceDescribe()`, `nothing.instanceDescribe()` will throw a `NullPointerException` when called in the normal case. This is the difference between **static access via an expression qualifier** and **instance access that truly requires a receiver object**.

### Best Practice

Write:

~~~java
System.out.println(Parent.label);
System.out.println(Parent.describe());
~~~

Do not write it through a nullable reference; when code shows `Parent.`, readers immediately know the member belongs to the class.

## 25. Static Method Hiding and Class Initialization

Static fields/methods are tied to the runtime class that declares them. When reading an inherited static field or calling an inherited static method through a **subclass name**, you must consider **which class actually declares the member**, not just the qualifier.

Example:

~~~java
class Parent {
    static int value = 10;
}

class Child extends Parent {
    static int ownValue = 20;
}
~~~

`Child.value` refers to `Parent.value` if Child does not hide it. Reading an inherited field can trigger initialization of **Parent** without necessarily initializing Child.

Conversely, `Child.ownValue` is declared in Child, so using it triggers Child's initialization if it has not yet been initialized, according to class initialization rules.

### Compile-Time Constants Are a Special Case

`static final int LIMIT = 10` with a constant expression is a **constant variable**. Reading a constant value in the normal way may not trigger class initialization. Do not use just any constant value access to prove that static blocks have run.

## 26. Runnable Example: The Class Declaring the Static Member Determines Initialization

Create **`StaticOwnerInitializationDemo.java`**:

~~~java
public class StaticOwnerInitializationDemo {
    static class Parent {
        static final int COMPILE_TIME_LIMIT = 7;

        static int inherited = 10;

        static {
            System.out.println("Parent initialized");
        }
    }

    static final class Child extends Parent {
        static int own = 20;

        static {
            System.out.println("Child initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("constant=" + Child.COMPILE_TIME_LIMIT);
        System.out.println("inherited=" + Child.inherited);
        System.out.println("own=" + Child.own);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticOwnerInitializationDemo.java
java StaticOwnerInitializationDemo
~~~

Stdout:

~~~text
constant=7
Parent initialized
inherited=10
Child initialized
own=20
~~~

Explanation:

1. `COMPILE_TIME_LIMIT` is a constant variable of Parent, so reading it via `Child.COMPILE_TIME_LIMIT` in the example does not cause Parent/Child static blocks to run.
2. `Child.inherited` is actually the non-constant static field **Parent.inherited**. The read causes Parent initialization to run, printing `Parent initialized`; Child does not need to be initialized yet.
3. `Child.own` is a static field declared by Child, causing Child to initialize and print `Child initialized`. Parent is already initialized, so it does not run again.

**Takeaway:** Across inheritance, the syntax `Child.member` is not enough to determine the initialization owner; you must know **where the member is declared**.

## 27. Class Loaders and Static State: Limits of “Sharing”

In a simple program, `Parent.counter` is a shared static field for all code using **the same Parent runtime class**. However, class identity in the JVM can depend on the class loader; two different class loaders can define two runtime classes with the same name and separate static states.

That does not change the rules of field hiding. It simply reminds us that “there is only a single static field across the entire JVM regardless of how many class loaders exist” is an overstatement.

In systems with plugins, app servers, or isolated test loaders, you must consider **runtime class identity** and loading context before comparing “this Parent.staticField” with “that Parent.staticField”.

You do not need a custom class loader to study this lesson; this is an important boundary when applying this knowledge to large systems.

## 28. Do Not Confuse Hiding with Overloading

**Static method overloading**:

~~~java
class Printer {
    static void print(int value) {
        System.out.println("int: " + value);
    }

    static void print(String value) {
        System.out.println("String: " + value);
    }
}
~~~

Two static methods have the same name but **different parameter lists**, so they are overloads within a class.

**Static method hiding**:

~~~java
class Parent {
    static String identify() {
        return "Parent";
    }
}

class Child extends Parent {
    static String identify() {
        return "Child";
    }
}
~~~

Two methods in the class hierarchy have **the same signature**. The Child declaration hides the Parent declaration according to Java rules.

### Overload Selection Is Based on Compile-Time Argument Types

~~~java
static String show(Object value) {
    return "Object";
}

static String show(String value) {
    return "String";
}
~~~

If a variable is `Object value = "text";`, the call `show(value)` normally selects the `show(Object)` overload; the runtime String value does not automatically switch the overload to `show(String)`.

This is also selected at compile time, but it is **overload resolution**, not **field/static hiding**. Do not merge the two terms.

## 29. Runnable Example: Overloading Combined with Instance Overriding

Save **`OverloadVsOverrideDemo.java`**:

~~~java
public class OverloadVsOverrideDemo {
    static class Parent {
        String accept(Object value) {
            return "Parent Object";
        }

        String accept(String value) {
            return "Parent String";
        }
    }

    static final class Child extends Parent {
        @Override
        String accept(Object value) {
            return "Child Object";
        }

        @Override
        String accept(String value) {
            return "Child String";
        }
    }

    public static void main(String[] args) {
        Parent receiver = new Child();

        Object asObject = "java";
        String asString = "java";

        System.out.println(receiver.accept(asObject));
        System.out.println(receiver.accept(asString));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverloadVsOverrideDemo.java
java OverloadVsOverrideDemo
~~~

Stdout:

~~~text
Child Object
Child String
~~~

Two steps:

1. The compiler selects **`accept(Object)` or `accept(String)`** based on the compile-time argument type.
2. Runtime dispatch selects the **Child implementation** of the exact selected method signature, because the actual receiver is Child.

When contrasting this with static method hiding, remember: **runtime dispatch only applies after an appropriate instance method invocation has been determined**; it is not used to select an overload based on the runtime argument class.

## 30. Static Overloads in a Class Hierarchy

Suppose:

~~~java
class Parent {
    static String format(Object value) {
        return "Parent Object";
    }
}

class Child extends Parent {
    static String format(String value) {
        return "Child String";
    }
}
~~~

`Child.format(String)` does not hide `Parent.format(Object)` because their signatures differ; this is a different overload. With `Child.format(...)`, both candidates can participate in overload resolution depending on context/access.

If the caller references via type Parent, the Child-only static overload is not automatically present in Parent's compile-time method set.

### Runnable Program

Save **`StaticOverloadHierarchyDemo.java`**:

~~~java
public class StaticOverloadHierarchyDemo {
    static class Parent {
        static String format(Object value) {
            return "Parent Object";
        }
    }

    static final class Child extends Parent {
        static String format(String value) {
            return "Child String";
        }
    }

    public static void main(String[] args) {
        Object textAsObject = "java";

        System.out.println(Parent.format("java"));
        System.out.println(Child.format("java"));
        System.out.println(Child.format(textAsObject));
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticOverloadHierarchyDemo.java
java StaticOverloadHierarchyDemo
~~~

Stdout:

~~~text
Parent Object
Child String
Parent Object
~~~

`Child.format("java")` selects the more specific overload for String. `Child.format(textAsObject)` selects Parent.format(Object), because the compile-time argument type is Object. There is no runtime “retry” of the overload using String.

## 31. Instance Methods Are the Right Choice When Polymorphism Is Needed

If the requirement is: “The same method `label()` on a Parent reference must return a label based on the actual object type,” use an **instance method**.

~~~java
class Animal {
    String label() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String label() {
        return "dog";
    }
}
~~~

~~~java
Animal a = new Dog();
System.out.println(a.label()); // dog.
~~~

These are illustrative snippets.

Conversely, if you write `static String label()` in both classes, `a.label()` will select Animal.label, not Dog.label. Static methods are not suitable for describing state or behavior based on a **runtime subtype**.

### Runnable Program: The Proper Polymorphic Design

Create **`PolymorphicLabelDemo.java`**:

~~~java
public class PolymorphicLabelDemo {
    static class Animal {
        String label() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String label() {
            return "dog";
        }
    }

    static final class Cat extends Animal {
        @Override
        String label() {
            return "cat";
        }
    }

    static void print(Animal animal) {
        System.out.println("label=" + animal.label());
    }

    public static void main(String[] args) {
        print(new Dog());
        print(new Cat());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PolymorphicLabelDemo.java
java PolymorphicLabelDemo
~~~

Stdout:

~~~text
label=dog
label=cat
~~~

`print(Animal)` does not depend on the concrete classes Dog/Cat. This is true **runtime subtype polymorphism**. No same-named static fields or casts are needed.

## 32. Static Factories: Hiding Is Possible, but Clear Names Are Usually Better

Java has many **static factory methods** such as `of(...)`, `from(...)`, and `valueOf(...)`. A superclass and subclass can declare static factories with the same signature, yet static methods do not dispatch polymorphically based on a receiver object.

Example:

~~~java
class Parent {
    static Parent create() {
        return new Parent();
    }
}

class Child extends Parent {
    static Child create() {
        return new Child();
    }
}
~~~

Calling `Parent.create()` creates a Parent, and `Child.create()` creates a Child according to each method body. A Parent variable referencing a Child **does not cause** `ref.create()` to select Child.create.

If an API needs to create a subtype from configuration, consider:

- A factory interface/strategy instance and dynamic dispatch.
- A registry with an explicit type key.
- A clearly named factory method and class qualifier.
- Constructor injection or dependency injection.

Do not force a design to use inheritance just to create a “polymorphic static factory” that the language does not support.

## 33. Runnable Example: Static Factory Hiding

Create **`StaticFactoryHidingDemo.java`**:

~~~java
public class StaticFactoryHidingDemo {
    static class Parent {
        static Parent create() {
            return new Parent();
        }

        String name() {
            return "Parent instance";
        }
    }

    static final class Child extends Parent {
        static Child create() {
            return new Child();
        }

        @Override
        String name() {
            return "Child instance";
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();

        Parent createdViaView = parentView.create();
        Parent createdViaChildClass = Child.create();

        System.out.println("via view=" + createdViaView.name());
        System.out.println("via class=" + createdViaChildClass.name());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFactoryHidingDemo.java
java StaticFactoryHidingDemo
~~~

Stdout:

~~~text
via view=Parent instance
via class=Child instance
~~~

When `parentView.create()` is resolved by compile-time Parent, it calls Parent.create and creates a new Parent instance. `Child.create()` creates a new Child instance. Then `name()` is called as an **instance virtual method**, so it returns according to the class of each respective new object.

### Two Mechanisms in the Same Program

- **Static factory selection:** compile-time.
- **Virtual `name()` dispatch:** runtime.

Do not equate the two decision points.

## 34. Interface Constants Can Be Hidden by a Class Field

An interface field is implicitly **`public static final`**:

~~~java
interface Flags {
    String LABEL = "interface";
}
~~~

A class implementing the interface can declare a field with the same name:

~~~java
class Item implements Flags {
    static String LABEL = "class";
}
~~~

Qualified syntax:

~~~java
System.out.println(Flags.LABEL); // interface.
System.out.println(Item.LABEL);  // class.
~~~

If a variable is declared with type `Flags`:

~~~java
Flags asInterface = new Item();
System.out.println(asInterface.LABEL); // interface.
~~~

Static field access continues to follow the **compile-time type**.

It is **discouraged** to read interface constants through object references. Use `Flags.LABEL` to avoid misleading readers into thinking the field belongs to each Item instance.

## 35. Runnable Example: Interface Constant and Class Field Hiding

Save **`InterfaceFieldHidingDemo.java`**:

~~~java
public class InterfaceFieldHidingDemo {
    interface HasLabel {
        String LABEL = "interface";
    }

    static final class Item implements HasLabel {
        static final String LABEL = "class";
    }

    public static void main(String[] args) {
        HasLabel asInterface = new Item();
        Item asClass = (Item) asInterface;

        System.out.println("interface=" + HasLabel.LABEL);
        System.out.println("class=" + Item.LABEL);
        System.out.println("via interface=" + asInterface.LABEL);
        System.out.println("via class=" + asClass.LABEL);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceFieldHidingDemo.java
java InterfaceFieldHidingDemo
~~~

Stdout:

~~~text
interface=interface
class=class
via interface=interface
via class=class
~~~

An Item object does not turn an interface field into an instance field. The two constant declarations exist on the two types, and the syntax via the interface/class determines which field is selected.

## 36. Interface Static Methods Are Not Inherited Like Class Static Methods

Java allows interfaces to declare static methods:

~~~java
interface Tools {
    static String format() {
        return "Tools";
    }
}
~~~

A class:

~~~java
class Service implements Tools {
}
~~~

**does not inherit** `Tools.format()` in the way a static method declared in a superclass can be accessed through a subclass. Call:

~~~java
Tools.format();
~~~

Do not write `Service.format()` unless Service **declares its own static method** with that name. If Service declares its own, that is Service's method, not a runtime override of the interface static method.

### Runnable Example

Create **`InterfaceStaticMethodsDemo.java`**:

~~~java
public class InterfaceStaticMethodsDemo {
    interface Tools {
        static String format() {
            return "interface Tools";
        }
    }

    static final class Service implements Tools {
        static String format() {
            return "class Service";
        }
    }

    public static void main(String[] args) {
        System.out.println(Tools.format());
        System.out.println(Service.format());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceStaticMethodsDemo.java
java InterfaceStaticMethodsDemo
~~~

Stdout:

~~~text
interface Tools
class Service
~~~

Do not refer to `Service.format()` as “overriding `Tools.format()`”. Interface static methods are declared for the interface itself and are not inherited into Service; the two methods in the example are distinct declarations.

### Default Methods Are Different

Interface `default` methods are instance methods with a body. A class implementing the interface can override them, and runtime dispatch is based on the actual object. Do not conflate default method overriding with static method hiding just because both are declared in an interface.

## 37. Field Name Conflicts from Two Interfaces

If a class implements two interfaces that have the same constant name:

~~~java
interface Left {
    int VALUE = 1;
}

interface Right {
    int VALUE = 2;
}

class Both implements Left, Right {
}
~~~

A simple reference to `VALUE` inside class Both can be **ambiguous** because both Left.VALUE and Right.VALUE are candidates. Use qualified names:

~~~java
int sum = Left.VALUE + Right.VALUE;
~~~

A class can declare its own `VALUE` field to hide those corresponding declarations according to the rules, though doing so usually makes the API harder to understand.

Do not treat interface constants as a polymorphic configuration mechanism. If you want to obtain different values depending on the implementing object, declare an **instance method such as `int value()`** and implement/override it.

## 38. Visibility: A Private Field Is Not Like Protected/Public Hiding

A private field of Parent cannot be accessed by name in a subclass like an inherited public/protected field. The subclass can declare its own field with the same name without “overriding” the private field.

~~~java
class Parent {
    private int id = 1;

    public int parentId() {
        return id;
    }
}

class Child extends Parent {
    private int id = 2;

    public int childId() {
        return id;
    }
}
~~~

`Parent.parentId()` reads private Parent.id; `Child.childId()` reads private Child.id. It is not a single polymorphic mutable field.

### Runnable Example

Save **`PrivateFieldNamesDemo.java`**:

~~~java
public class PrivateFieldNamesDemo {
    static class Parent {
        private final int id = 1;

        public int parentId() {
            return id;
        }
    }

    static final class Child extends Parent {
        private final int id = 2;

        public int childId() {
            return id;
        }
    }

    public static void main(String[] args) {
        Child c = new Child();
        System.out.println("parentId=" + c.parentId());
        System.out.println("childId=" + c.childId());
    }
}
~~~

~~~bash
javac -encoding UTF-8 PrivateFieldNamesDemo.java
java PrivateFieldNamesDemo
~~~

Stdout:

~~~text
parentId=1
childId=2
~~~

Because the methods establish the access context of their respective declaring classes, the two getters read two separate fields. This is also an example of why you should keep state private and provide meaningful behavior rather than expecting polymorphic fields.

## 39. Shadowing by a Local Variable Differs from Field Hiding

Example:

~~~java
class Counter {
    private int value;

    void update(int value) {
        this.value = value;
    }
}
~~~

In the `update` method, the parameter `value` **shadows** the instance field `value`. `this.value` is used to access the object's field, while `value` on the right-hand side is the parameter.

Do not call this “static method hiding” or “subclass field hiding,” because no class hierarchy is involved in this name lookup. The term **shadowing** is broader and relates to a different scope.

### When a Subclass Declares a Field with the Same Name as a Parameter?

You must examine the scope in each expression. A parameter/local variable can shadow the field name, `this` can select the current field, and `super` can select the superclass field. It is not a single rule of “whichever name is closest” for every case; clearly identify the **declaration kind and access context**.

## 40. Static Hiding Does Not Depend on Whether a Variable Is Actually Created

You can call:

~~~java
Parent.identify();
Child.identify();
~~~

before creating **any Parent/Child instance**, if the methods are accessible and class initialization allows it. Static members belong to the class and do not need a receiver object.

For dynamic polymorphism:

~~~java
Parent parent = new Child();
parent.describe();
~~~

a reference pointing to an actual object is needed to perform an instance method invocation. `new Child()` creates the object, and instance fields/constructors are executed according to the rules.

This difference explains why a static method cannot “guess which runtime subtype you want to call” without an explicit argument/type key.

## 41. Design Smell: “Defining Polymorphism” Using Static Fields

Counterexample:

~~~java
class Animal {
    static String TYPE = "animal";
}

class Dog extends Animal {
    static String TYPE = "dog";
}

class Cat extends Animal {
    static String TYPE = "cat";
}
~~~

If code receives `Animal animal`, `animal.TYPE` is always resolved according to Animal, regardless of whether the object is a Dog/Cat. This is usually not what is desired.

### Improving with Instance Behavior

~~~java
abstract class Animal {
    abstract String type();
}

class Dog extends Animal {
    @Override
    String type() {
        return "dog";
    }
}

class Cat extends Animal {
    @Override
    String type() {
        return "cat";
    }
}
~~~

Then `Animal a = new Dog(); a.type()` returns `"dog"`. The code behaves according to the runtime subtype, true to the contract.

Another solution is to store the type value in an instance field with constructor validation if a subtype hierarchy is unnecessary. The key is to **choose the data model based on the use case**, rather than using static fields to simulate per-object polymorphism.

## 42. Design Smell: Static Service Method “Overridden” in a Subclass

A codebase might write:

~~~java
class BaseFormatter {
    static String format(Object input) {
        return "base";
    }
}

class JsonFormatter extends BaseFormatter {
    static String format(Object input) {
        return "json";
    }
}
~~~

And then expect `BaseFormatter f = new JsonFormatter(); f.format(data)` to call JsonFormatter. That is **wrong**: the compiler selects BaseFormatter.format.

If the service must swap implementations at runtime, use an interface:

~~~java
interface Formatter {
    String format(Object input);
}

class JsonFormatter implements Formatter {
    @Override
    public String format(Object input) {
        return "json";
    }
}
~~~

These are illustrative snippets. The caller can receive a `Formatter` in its constructor and call the instance method. There is no need to subclass a utility class just to “inherit” static helpers.

## 43. Runnable Example: Refactoring Static Hiding into an Instance Strategy

Save the file **`StrategyInsteadOfStaticHidingDemo.java`**:

~~~java
public class StrategyInsteadOfStaticHidingDemo {
    interface Formatter {
        String format(String value);
    }

    static final class PlainFormatter implements Formatter {
        @Override
        public String format(String value) {
            return value;
        }
    }

    static final class BracketFormatter implements Formatter {
        @Override
        public String format(String value) {
            return "[" + value + "]";
        }
    }

    static void show(Formatter formatter) {
        System.out.println(formatter.format("Java"));
    }

    public static void main(String[] args) {
        show(new PlainFormatter());
        show(new BracketFormatter());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StrategyInsteadOfStaticHidingDemo.java
java StrategyInsteadOfStaticHidingDemo
~~~

Stdout:

~~~text
Java
[Java]
~~~

The call to `show(Formatter)` depends on the interface contract, and the runtime object determines the implementation. This is true polymorphism, unlike selecting a static member by class name/declared reference type.

## 44. Generic Classes Still Do Not Duplicate Static Fields per Type Argument

Consider:

~~~java
class Box<T> {
    static int created;

    Box() {
        created++;
    }
}
~~~

`Box<String>` and `Box<Integer>` do not have **two separate static counters** just because their type arguments differ. Generic type arguments in Java undergo type erasure; the static field belongs to the Box runtime class.

### Runnable Example

Save **`GenericStaticFieldDemo.java`**:

~~~java
public class GenericStaticFieldDemo {
    static final class Box<T> {
        private static int created;

        Box(T value) {
            created++;
        }

        static int created() {
            return created;
        }
    }

    public static void main(String[] args) {
        Box<String> word = new Box<>("Java");
        Box<Integer> number = new Box<>(17);

        System.out.println("word type=" + word.getClass().getSimpleName());
        System.out.println("number type=" + number.getClass().getSimpleName());
        System.out.println("created=" + Box.created());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GenericStaticFieldDemo.java
java GenericStaticFieldDemo
~~~

Stdout:

~~~text
word type=Box
number type=Box
created=2
~~~

There is no hiding in this snippet; it explains the **scope of a static field** when a generic class is used with multiple type arguments. In fact, the compiler does not allow a static field of a generic class to directly use the type parameter `T` as its type: `static T value;` is invalid because a static context is not tied specifically to each type instantiation.

## 45. Reflection: Field Declarations Differ from Convenience Lookup

If using reflection, a class can have a field declared in itself and a field with the same name declared in its superclass. You may need to distinguish `getDeclaredField` on each Class object instead of assuming “reading a field by name always refers to a single field”.

Example:

~~~java
java.lang.reflect.Field parentField =
        Parent.class.getDeclaredField("value");
java.lang.reflect.Field childField =
        Child.class.getDeclaredField("value");
~~~

The lines above are illustrative code; if classes Parent/Child actually declare `value`, the two Field objects represent two different member declarations. `getDeclaredField` has a checked exception `NoSuchFieldException` that must be handled or declared with throws.

### Why Not Use Reflection as a Shortcut for Learning Static Hiding?

Reflection also involves visibility/access checks, lookup APIs, and invocation mechanisms that differ from normal Java syntax. To learn hiding rules, **using `Parent.value`, `Child.value`, and declared reference types directly** is clearer. Reflection is only useful when developing frameworks or tooling that need to inspect member declarations.

## 46. Tests Should Verify Both Compile-Time and Runtime Paths

When designing tests for a hierarchy:

1. Assign a Child object to a variable of type Parent.
2. Access the static field via Parent and Child qualifiers.
3. Call static methods via Parent/Child qualifiers.
4. Call overridden instance methods via a Parent reference.
5. Perform a valid downcast and then access the field/static method again.
6. Test the case where an inherited member is not hidden.
7. Test a hidden field having a different value.
8. Check static owner initialization if the code has side effects.
9. Check semantics that require true polymorphism to ensure static was not used accidentally.
10. Do not rely on the order of test methods or mutable global static state.

**You do not necessarily need to run an external test framework** to verify basic semantics: the `main` programs with stdout in the README already illustrate them. For real applications, you can put expectations into JUnit assertions.

## 47. Exercise 1 — Predict Static and Instance Output

Given:

~~~java
class A {
    static String s() {
        return "A static";
    }

    String i() {
        return "A instance";
    }
}

class B extends A {
    static String s() {
        return "B static";
    }

    @Override
    String i() {
        return "B instance";
    }
}
~~~

Caller:

~~~java
A x = new B();
System.out.println(x.s());
System.out.println(x.i());
System.out.println(B.s());
~~~

**Answer:**

~~~text
A static
B instance
B static
~~~

`x.s()` selects A.s based on compile-time type A. `x.i()` dispatches to B.i because the runtime receiver is B. `B.s()` explicitly calls B's method.

## 48. Exercise 2 — Two Separate Static Fields

~~~java
class A {
    static int n = 1;
}

class B extends A {
    static int n = 2;
}
~~~

After:

~~~java
A.n += 5;
B.n += 10;
System.out.println(A.n);
System.out.println(B.n);
~~~

**Answer:**

~~~text
6
12
~~~

They are two different fields. Do not confuse using the same name `n` with sharing storage.

## 49. Exercise 3 — Not Declaring a New Field

~~~java
class A {
    static int n = 1;
}

class B extends A {
}
~~~

After:

~~~java
B.n = 8;
System.out.println(A.n);
~~~

**Answer:** `8`, because `B.n` is the inherited field **A.n**, not a new field in B.

## 50. Exercise 4 — Casting Parent ↔ Child

~~~java
A a = new B();
System.out.println(a.n);
System.out.println(((B) a).n);
~~~

Assume A.n=3 and B.n=9.

**Answer:**

~~~text
3
9
~~~

The cast changes the compile-time type of the field access expression. The runtime object is already B, and no new object is created. If the actual object is not B, casting to B can throw ClassCastException.

## 51. Exercise 5 — Is an Interface Static Method Inherited?

~~~java
interface I {
    static void work() {
        System.out.println("I");
    }
}

class C implements I {
}
~~~

**Answer:** `I.work()` is valid. `C.work()` is not inherited merely by implementing I. If C declares its own `static void work()`, it is C's method, not an instance overriding of I.work.

## 52. Exercise 6 — Combining Field Hiding and Method Overriding

~~~java
class Parent {
    int value = 1;

    int getValue() {
        return value;
    }
}

class Child extends Parent {
    int value = 2;

    @Override
    int getValue() {
        return value;
    }
}
~~~

If `Parent p = new Child();`:

**Answer:** `p.value == 1`, while `p.getValue() == 2`. Field lookup relies on the Parent compile-time type; the virtual method calls the Child override.

## 53. Exercise 7 — What Is Wrong with `@Override`?

~~~java
class Parent {
    static void ping() {}
}

class Child extends Parent {
    // @Override
    static void ping() {}
}
~~~

If the annotation is enabled, the compiler rejects it because the static method Child.ping **hides**, rather than overrides. Do not change it into an instance method with the same signature: a static/instance clash still causes an error. If polymorphism is needed, create an instance method in Parent and override it properly.

## 54. Exercise 8 — Two Static Final Constants

~~~java
class P {
    static final String KIND = "P";
}
class C extends P {
    static final String KIND = "C";
}
~~~

With `P ref = new C();`, `ref.KIND` is `"P"`. If cast as `((C) ref).KIND`, it is `"C"`. These are two independent constant variables, with no object-level polymorphism.

## 55. Exercise 9 — Static Access via Null

Given:

~~~java
class Tool {
    static String name() {
        return "utility";
    }
}

Tool ref = null;
System.out.println(ref.name());
~~~

**Answer:** Prints `utility` in a valid Java context. There is no instance dereference in that static call. However, writing `Tool.name()` is the proper style and avoids confusion.

If the qualifier is a method call with side effects such as `getNull().name()`, Java still evaluates `getNull()` before performing the static method invocation.

## 56. Exercise 10 — Choosing a Design According to Purpose

A library has `Animal` and `Dog`; the requirement is for `displayName(Animal a)` to return a name depending on the runtime subtype. Two proposals:

- Place `static String TYPE` in each subclass.
- Declare a `String type()` instance method in Animal and override it in subclasses.

**Answer:** Use an instance method if the goal is runtime polymorphism. Static fields are selected by the compile-time type of the reference and do not produce results depending on the runtime subtype.

## 57. Common Mistakes

| Misconception | What Is Correct |
| --- | --- |
| “A static method in a subclass overrides Parent.” | It **hides** it when the signature matches appropriately. |
| “`@Override` is used for any method with the same name.” | Do not use the annotation for static hiding. |
| “For a Child object, `Parent ref` always reads Child fields.” | Fields are selected by the declared reference type. |
| “Field hiding has dynamic dispatch.” | No; field lookup differs from instance method dispatch. |
| “Creating Child creates a new copy of Parent's static field.” | No; if not redeclared, the static field still belongs to Parent. |
| “The same field name means the same storage.” | Two declarations can be two separate fields. |
| “A `final static field` cannot have a field with the same name declared by a subclass.” | A final field and field hiding are two separate matters; hiding can be valid. |
| “A static `final` method can be hidden arbitrarily.” | A final method cannot be hidden/overridden under the relevant rules. |
| “A static method is selected by the runtime object.” | No; it is selected at compile time. |
| “Casting to Parent turns Child into a Parent object.” | No; a cast does not create/slice an object. |
| “`null.staticMethod()` always throws NPE.” | Not if it is a valid static member access, though the qualifier expression is still evaluated. |
| “Everything after the dot is ignored during static access.” | The qualifier expression can cause side effects. |
| “Accessing `Child.parentField` always initializes Child.” | An inherited static member may initialize only the declaring class Parent. |
| “Reading a compile-time constant definitely runs the static block.” | Not necessarily; constant variables have special rules. |
| “A static interface method is inherited into the implementing class.” | Interface static methods are not inherited like class static methods. |
| “`List<Child>` is a `List<Parent>` because Child extends Parent.” | Java generics are invariant and do not infer that automatically. |
| “Overloading and hiding are both decided by the runtime subclass.” | Overloading/static hiding depend on compile-time contexts. |
| “`super.field` and `this.field` are always the same field.” | When hiding occurs, they can be two different declarations. |
| “Fields with the same name are the standard way to configure subtypes.” | Use polymorphic instance behavior or explicit config. |
| “A static factory called via a Parent ref creates Child because ref holds a Child.” | Static factory selection does not use dynamic dispatch. |

## 58. End-of-Lesson Checklist

- [ ] I know that declared type and runtime class can differ.
- [ ] I understand that a Child object can be held by a Parent reference.
- [ ] I can distinguish field hiding from instance method overriding.
- [ ] I know how static method hiding differs from overriding.
- [ ] I call static members using `ClassName.member` instead of an object qualifier.
- [ ] I understand that `Parent ref = new Child(); ref.staticField` selects Parent's field.
- [ ] I understand that `ref.staticMethod()` selects Parent's static method.
- [ ] I understand that `ref.instanceMethod()` dispatches to the actual Child if overridden.
- [ ] I know a cast can change compile-time field/static lookup.
- [ ] I do not think upcasting creates/slices an object.
- [ ] I understand that two static fields with the same name can store two independent values.
- [ ] I know an inherited static field does not create a new copy in the subclass.
- [ ] I know instance fields can also be hidden.
- [ ] I use `super.field` and `this.field` to distinguish declarations when appropriate.
- [ ] I know `@Override` is invalid for static method hiding.
- [ ] I recognize the error of a static/instance method clash with the same signature.
- [ ] I know a static final method differs from a static final field in hiding capability.
- [ ] I know access level, return type, and checked exceptions must be compatible.
- [ ] I understand static member access through a null qualifier can be valid.
- [ ] I understand a qualifier expression can still execute side effects.
- [ ] I distinguish static hiding from overload resolution.
- [ ] I know instance overrides undergo dynamic dispatch after overload selection.
- [ ] I understand an inherited static member is tied to its declaring class during initialization.
- [ ] I recognize that compile-time constant access might not initialize a class.
- [ ] I know interface constants are selected by compile-time type.
- [ ] I know interface static methods are not inherited into classes.
- [ ] I know generic type arguments do not create separate static field copies.
- [ ] I can refactor from static hiding to a polymorphic instance method.
- [ ] I can test both member lookup and runtime dispatch.
- [ ] I can explain the stdout of the Java 17+ programs in this lesson.

**Conclusion:** **Hiding** is not **overriding**. When a subclass declares a field with the same name, Java can have **two field declarations**, and access selects the field according to the **compile-time type**. When a subclass declares a matching static method, it **hides** the superclass's static method, so calls are also selected by type at compile time, not by the actual receiver. Conversely, an **overridden instance method** is dispatched according to the runtime class of the object. Understanding these three member-selection paths helps predict output, accurately explain upcasting behavior, and avoid fake “polymorphism” designs using static fields/static methods. If the goal is to vary behavior based on the actual object, use **instance methods/interfaces/strategies** instead of static hiding.
