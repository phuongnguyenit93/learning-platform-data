# Using `this` or the Class Name to Disambiguate Shadowed Fields in Java

## 1. Why is it necessary to specify the field?

In a constructor or method, a local/parameter can have the same name as a field. In that case, the short name normally selects the local/parameter. For example:

~~~java
class Account {
    private int balance;
    Account(int balance) {
        this.balance = balance; // The field receives the value from the parameter.
    }
}
~~~

If you only write `balance = balance;`, the code is valid but self-assigns the parameter, ignoring the field. This is a case of *shadowing*; explanations of constructor/setter bugs were practiced in the previous lesson. This lesson focuses on **field selection syntaxes**, especially when inheritance or an enclosing class is involved.

## 2. Distinguishing `this.field`, `ClassName.field`, and `super.field`

| Syntax | Should be used to access | Valid context | Meaning |
| --- | --- | --- | --- |
| `field` | Nearest variable/parameter with that name; if none exists, possibly a field | Depends on scope | The short name may be shadowed |
| `this.field` | **Instance** field of the current object | Instance constructor/method/block | Bypasses shadowing of the short name by a parameter/local |
| `ClassName.field` | **Static** field declared or suitably inherited on the class | Including `static` methods | Explicitly specifies a class field, not belonging to individual instances |
| `super.field` | Instance field looked up starting from the superclass | Instance context of a subclass | Distinguishes a superclass field from a field with the same name in the subclass |
| `object.field` | Field accessible through an object reference variable | When an object and access permission exist | Specifies an instance, subject to access control checks |

**Note:** `ClassName.instanceField` is **invalid**, because an instance field must be accessed through an object (`this` or a specific reference). Conversely, Java allows some ways of accessing a `static` field through an object reference, but you should use `ClassName.staticField` to avoid misunderstandings and warnings from code analysis tools.

A `private` field can still be accessed with `this.field` from **inside the same class**. `this` does not bypass access control rules: another class cannot read a `private` field merely by writing `someObject.field`.

## 3. Selecting the right instance field with `this.field`

`this` refers to the current object of an instance constructor/method. It allows selecting the field even when the short name points to a parameter or local:

~~~java
class Student {
    private String name;
    Student(String name) { this.name = name; }
    String display() {
        String name = "LOCAL";
        return name + "/" + this.name;
    }
}
~~~

With `new Student("Mai").display()`, the result is `LOCAL/Mai`. In a `static` method there is no `this`. When no local/parameter shadows the field, using the short field name can still be valid; `this.` helps make instance state explicit.

## 4. Selecting the right `static` field with `ClassName.field`

For shared class state, write the class name before the field to avoid confusing it with a local/parameter:

~~~java
class Settings {
    private static int timeout = 30;
    static void configure(int timeout) {
        Settings.timeout = timeout;
    }
}
~~~

`Settings.timeout` updates the field, whereas the bare `timeout` on the right-hand side is the parameter. `ClassName.instanceField` is invalid because an instance field requires an object; accessing a `static` field through an object, though legal in Java, makes code harder to understand. Inheriting a field with the same name raises a different question: should you use `this.field` or `super.field`?

## 5. When a subclass hides a superclass field: `this` and `super`

Two classes in an inheritance relationship can declare **two separate fields with the same name**. This is a case of *field hiding*. Unlike overridden instance methods, **field access does not use dynamic dispatch** based on the object's runtime type; the field is chosen based on the reference type and compile-time lookup rules.

```java
class Base {
    int level = 10;
}

class Derived extends Base {
    int level = 20;

    void inspect(int level) {
        System.out.println(level);       // Parameter
        System.out.println(this.level);  // Derived field
        System.out.println(super.level); // Base field
    }
}
```

In `Derived.inspect(int level)`:

- `level` is the **parameter**.
- `this.level` points to `Derived`'s field.
- `super.level` selects the field inherited from `Base`.

Both `Base.level` and `Derived.level` reside in the same `Derived` object; the JVM does not merge them into a single field.

```java
Base baseView = new Derived();
Derived derivedView = (Derived) baseView;
// baseView.level == 10
// derivedView.level == 20
```

The difference occurs because the expression `baseView` has type `Base` while `derivedView` has type `Derived`. This is not dynamic method polymorphism. `super.field` can only be used in an appropriate instance context of the subclass and remains subject to the superclass field's access restrictions.

If a **static** field with the same name exists in both the superclass and subclass, prefer writing `Base.field` or `Derived.field` explicitly (given valid access permissions), rather than relying on the short name.

## 6. Standalone Java 17+ program

Create the file **`FieldShadowDemo.java`**:

```java
public class FieldShadowDemo {
    private String title = "Mac dinh";
    private int level;
    private static int created = 0;

    FieldShadowDemo(String title, int level) {
        this.title = title;
        this.level = level;
        created++;
    }

    void setLevel(int level) {
        this.level = level;
    }

    void showLocalShadowing() {
        String title = "Bien cuc bo";
        System.out.println("local title: " + title);
        System.out.println("this.title: " + this.title);
    }

    static void increaseCreated(int created) {
        FieldShadowDemo.created += created;
    }

    static class Parent {
        int code = 1;
    }

    static class Child extends Parent {
        int code = 2;

        void show(int code) {
            System.out.println("parameter code: " + code);
            System.out.println("this.code: " + this.code);
            System.out.println("super.code: " + super.code);
        }
    }

    public static void main(String[] args) {
        FieldShadowDemo example = new FieldShadowDemo("Java", 1);
        System.out.println("level before: " + example.level);
        example.setLevel(4);
        System.out.println("level after: " + example.level);
        example.showLocalShadowing();

        System.out.println("created before: " + FieldShadowDemo.created);
        increaseCreated(2);
        System.out.println("created after: " + FieldShadowDemo.created);

        Child child = new Child();
        child.show(3);
        Parent asParent = child;
        System.out.println("parent view: " + asParent.code);
        System.out.println("child view: " + child.code);
    }
}
```

In the directory containing the file, using JDK 17 or later (PowerShell, CMD, bash):

```bash
javac -encoding UTF-8 FieldShadowDemo.java
java FieldShadowDemo
```

Exact expected stdout (successful `javac` prints nothing):

```text
level before: 1
level after: 4
local title: Bien cuc bo
this.title: Java
created before: 1
created after: 3
parameter code: 3
this.code: 2
super.code: 1
parent view: 1
child view: 2
```

Explanation:

1. The constructor and setter use `this.level` to affect the right instance field. The local variable `title` only shadows the field name inside the method; it does not delete `this.title`.
2. The parameter `created` of method `increaseCreated` is not the `static` field `created`. The statement `FieldShadowDemo.created += created` updates the field from `1` to `3`.
3. `Child.show` has three different interpretations for the name `code` as in the example: parameter `3`, subclass field `2`, and superclass field `1`.
4. `asParent.code` reads the field from type `Parent`, whereas `child.code` reads the field from type `Child` even though both variables reference the same object.

## 7. Fields in an enclosing class

In a **non-`static` inner class**, to access a field of the enclosing class object when the name is shadowed, use `Outer.this.field`:

```java
class Outer {
    int size = 10;

    class Inner {
        int size = 20;

        void print(int size) {
            System.out.println(size);            // Parameter
            System.out.println(this.size);       // Inner field
            System.out.println(Outer.this.size); // Outer field
        }
    }
}
```

This snippet illustrates the syntax inside a class (it is not a standalone program). `Outer.this` is a reference to the `Outer` instance enclosing the `Inner` instance. This **does not apply in the same way** to a nested class declared `static`, because a static nested class does not automatically hold an enclosing outer instance reference.

## 8. Common errors and how to choose the syntax

| Error / misconception | How to understand or fix |
| --- | --- |
| Constructor writes `name = name;` and assumes the field is assigned | Both names usually point to the parameter; use `this.name = name;` |
| Writing `this.field` in a `static` method | There is no `this` in a static context; write `ClassName.field` for static fields, and an object is needed for instance fields |
| Calling `ClassName.instanceField` | Instance fields cannot be accessed like static fields |
| Using `this.field` to select a superclass field when the subclass has a field of the same name | Use `super.field` if the superclass field is accessible |
| Thinking two fields with the same name in an inheritance hierarchy are one field | Field hiding creates two distinct fields; the expression type determines which field is selected |
| Thinking `this` bypasses all access restrictions | `this` is just the current reference; it does not alter Java access permissions |
| Using `object.staticField` as if it were an instance field | Write `ClassName.staticField` to express clearly that the field belongs to the class |

**Key Takeaway:** use `this.field` to explicitly refer to an **instance field of the current object**, use `ClassName.field` to explicitly refer to a **static field of the class**, and use `super.field` when you need a **superclass field** hidden by a subclass field. When names do not collide, qualifiers can still make code easier to read, but they should be chosen consistently with the field kind.
