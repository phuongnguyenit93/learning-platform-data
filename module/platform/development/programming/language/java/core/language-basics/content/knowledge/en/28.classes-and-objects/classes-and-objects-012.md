# Recognizing `@Override` and `@Deprecated` Annotations in Java

> **Java core — language-basics / Classes and Objects**  
> **Environment:** Java 17+, JDK only.  
> **Goal:** Know the purpose, placement, and effect of `@Override` and `@Deprecated`; distinguish overriding from overloading and method hiding; identify legacy APIs and how to migrate safely.

## 1. What Is an Annotation?

An *annotation* is supplemental metadata placed on a declaration (and certain other positions depending on the annotation type), usually starting with `@`. It helps the compiler, tools, or libraries recognize the code's intent:

~~~java
@Override
public String toString() {
    return "example";
}
~~~

An annotation is **not** a method call. Placing `@Override` before a method declaration does not execute its body automatically; the method still runs when called under Java's rules.

| Annotation | Primary meaning | Observable effect |
| --- | --- | --- |
| `@Override` | This declaration is intended to override/implement a valid method from a superclass/interface | The compiler reports an error if it does not actually override/implement properly |
| `@Deprecated` | The API is no longer recommended for use | Tools/compilers can warn when other code uses the legacy API |

Both annotations live in `java.lang`, so no `import` is needed. Do not confuse `@Deprecated` with a command that deletes code, and do not confuse `@Override` with a mandatory keyword required for Java polymorphism.

## 2. `@Override` on Methods Overridden from a Superclass

~~~java
class Animal {
    public String speak() {
        return "generic";
    }
}

class Dog extends Animal {
    @Override
    public String speak() {
        return "woof";
    }
}
~~~

`Dog.speak()` overrides `Animal.speak()`: same name and parameter type list, compatible return type, and satisfying access/exception rules. Calling through a superclass-typed reference still executes the version on the actual object:

~~~java
Animal pet = new Dog();
System.out.println(pet.speak()); // woof
~~~

`@Override` asks the compiler to verify this intent. If you accidentally write `speek()` instead of `speak()` while keeping `@Override`, the compiler reports an error rather than silently creating a **new** method.

**Without `@Override`, valid overriding still happens**, yet adding the annotation catches signature mistakes early and makes code clearer.

You can override appropriate instance methods of `Object`, such as `toString()`:

~~~java
@Override
public String toString() {
    return "Dog";
}
~~~

## 3. `@Override` When Implementing an Interface

A class implementing an interface typically writes `@Override` before the method fulfilling the contract:

~~~java
interface Audible {
    String sound();
}

class Bird implements Audible {
    @Override
    public String sound() {
        return "chirp";
    }
}
~~~

`Bird.sound()` must match the signature and return type of `Audible.sound()`. Because the interface method in this example is `public`, the implementing method must also be `public`; you cannot reduce visibility.

In Java 17, `@Override` is also used when overriding a matching `default method` of an interface. An annotation does not replace `implements`/`extends` keywords: the type relationship and method definition must already exist.

## 4. Cases Where `@Override` Is Invalid

| Situation | Is it a valid override for `@Override`? | Reason |
| --- | --- | --- |
| Misspelling `speek()` instead of `speak()` | No | Does not match superclass method |
| `speak(int n)` when superclass only has `speak()` | No | This is **overloading**, different parameter list |
| Defining a new method that only exists in the subclass | No | No matching method to override |
| Writing constructor `Dog()` | No | Constructors are not overridden methods |
| Declaring `static` matching a superclass static method | No | This is **method hiding**, not overriding |
| Trying to override a superclass `private` method | No | Private methods are not inherited to be overridden |
| Trying to override a superclass `final` method | No | `final` prevents overriding |

The example below **intentionally does not compile**, solely for identifying errors:

~~~java
class Parent {
    public void run() {}
}

class Child extends Parent {
    // @Override
    // public void run(int times) {} // Error: only overloads, does not override.

    // @Override
    // public void rnu() {} // Error: misspelled method name.
}
~~~

Uncommenting `@Override` in a broken example causes the error to be caught immediately at compile time. Do not remove the annotation just to hide an error: check the name, parameter types, return type, and inheritance/implementation relationship.

`@Override` also does not make static calls polymorphic. **Overload** resolution is based on expression types at compile time, whereas instance method **overriding** supports dynamic dispatch based on the actual object at runtime.

## 5. `@Deprecated`: Marking an Old API, Not Deleting It

~~~java
class LabelService {
    /**
     * @deprecated Use modernLabel(String) instead.
     */
    @Deprecated(since = "17", forRemoval = false)
    public String oldLabel(String value) {
        return "old:" + value;
    }

    public String modernLabel(String value) {
        return "new:" + value;
    }
}
~~~

Even though `oldLabel` is annotated with `@Deprecated`, calls still compile and run while that API exists:

~~~java
LabelService service = new LabelService();
System.out.println(service.modernLabel("Java")); // new:Java
System.out.println(service.oldLabel("Java"));    // old:Java
~~~

The compiler/tools may emit warnings about using deprecated APIs; a warning **is not a compile error**, and the annotation does not automatically remove the method from the class.

You can mark **classes**, **constructors**, **methods**, **fields**, and other declaration kinds permitted by the annotation as deprecated. Because API users need to know the replacement path, write clear migration documentation.

**Two different parts:**

- `@Deprecated` is an **annotation** recognized by the compiler and tools.
- Lowercase `@deprecated` inside `/** ... */` is a **Javadoc tag**, explaining the reason and suggesting the replacement API for documentation readers.

Use **both** when publishing a legacy API. Writing only the `@deprecated` Javadoc tag without the annotation will not provide the standard deprecation signal to tools.

## 6. `since`, `forRemoval`, and Handling Warnings

Since Java 9, `@Deprecated` has two optional elements, both usable on Java 17:

| Syntax | Interpretation |
| --- | --- |
| `@Deprecated` | Marks deprecated, without providing extra metadata |
| `@Deprecated(since = "17")` | Indicates the author-recorded version `17`; this string does not automatically verify the version |
| `@Deprecated(forRemoval = true)` | The API is marked as **intended for removal** in the future |
| `@Deprecated(since = "17", forRemoval = false)` | Deprecated since descriptive version `17`, not yet marked for removal |

`forRemoval = true` **does not** promise the API will disappear on a fixed date. If an application uses this API, consult the provider's documentation and migration plan; avoid inferring a removal timeline on your own.

To view deprecation warnings when compiling a project yourself:

~~~bash
javac -Xlint:deprecation -encoding UTF-8 AnnotationBasicsDemo.java
~~~

`javac` warnings belong to the compiler diagnostic output stream, **not** the running program's stdout, and wording may vary by file path/JDK. `@SuppressWarnings("deprecation")` can suppress the corresponding warning within the annotated scope, but should be reserved for well-justified cases rather than used to hide reliance on legacy APIs. `forRemoval=true` can produce warnings under the separate `removal` category.

## 7. Self-Contained, Runnable Java 17+ Example

Create file **AnnotationBasicsDemo.java**. All declarations in this single file compile cleanly:

~~~java
public final class AnnotationBasicsDemo {
    private interface Audible {
        String sound();
    }

    private static class Animal {
        public String speak() {
            return "generic";
        }

        public String kind() {
            return "ANIMAL";
        }
    }

    private static final class Dog extends Animal {
        private final String name;

        Dog(String name) {
            this.name = name;
        }

        @Override
        public String speak() {
            return "woof";
        }

        @Override
        public String kind() {
            return "DOG";
        }

        @Override
        public String toString() {
            return "Dog(" + name + ")";
        }

        // Same name, different parameter: overload, not override.
        public String speak(int times) {
            return "woof x" + times;
        }
    }

    private static final class Bird implements Audible {
        @Override
        public String sound() {
            return "chirp";
        }
    }

    private static final class LegacyApi {
        /**
         * @deprecated Use modernLabel(String) instead.
         */
        @Deprecated(since = "17", forRemoval = false)
        public String oldLabel(String value) {
            return "old:" + value;
        }

        public String modernLabel(String value) {
            return "new:" + value;
        }
    }

    public static void main(String[] args)
            throws NoSuchMethodException {
        Animal base = new Animal();
        Animal pet = new Dog("Rex");
        Dog dog = new Dog("Rex");
        Audible bird = new Bird();
        LegacyApi labels = new LegacyApi();

        System.out.println("parent=" + base.speak());
        System.out.println("override=" + dog.speak());
        System.out.println("dynamic=" + pet.speak());
        System.out.println("kind=" + pet.kind());
        System.out.println("interface=" + bird.sound());
        System.out.println("toString=" + dog.toString());
        System.out.println("overload=" + dog.speak(2));

        System.out.println("modern=" + labels.modernLabel("Java"));
        System.out.println("legacy=" + labels.oldLabel("Java"));

        // Illustrates that the Deprecated annotation can be read via reflection.
        Deprecated info = LegacyApi.class
                .getDeclaredMethod("oldLabel", String.class)
                .getAnnotation(Deprecated.class);
        System.out.println("hasDeprecated=" + (info != null));
        System.out.println("since=" + info.since());
        System.out.println("forRemoval=" + info.forRemoval());
    }
}
~~~

Compile/run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 AnnotationBasicsDemo.java
java AnnotationBasicsDemo
~~~

**Exact expected stdout when running `java AnnotationBasicsDemo`:**

~~~text
parent=generic
override=woof
dynamic=woof
kind=DOG
interface=chirp
toString=Dog(Rex)
overload=woof x2
modern=new:Java
legacy=old:Java
hasDeprecated=true
since=17
forRemoval=false
~~~

Explanation: `dynamic=woof` and `kind=DOG` show dynamic overriding through an `Animal`-typed variable; `interface=chirp` illustrates interface implementation; `overload=woof x2` calls a method with a different parameter list, not an override. `legacy` still works even though the old API is marked deprecated.

The last three lines use JDK **reflection** to read `@Deprecated`; this is supplemental observation, not required for understanding the API. `@Override` mainly supports compile-time checking and is not used for this reflection inspection.

## 8. Common Mistakes, Checklist, and Exercises

| Misconception | Correct understanding |
| --- | --- |
| Must write `@Override` for polymorphism to work | No: the annotation helps verify override intent |
| `@Override` can be placed on any overload | Wrong: an overload with a different parameter list is not an override |
| Overriding a static method like an instance method | Wrong: static methods can be hidden, not overridden |
| Can place `@Override` on a constructor | No: constructors are not overridden methods |
| `@Deprecated` stops code from running | No: it still runs if the API exists and the call is valid |
| `@Deprecated` automatically provides the replacement API | No: check Javadoc/changelog for migration |
| Javadoc `@deprecated` and annotation `@Deprecated` are the same | Different: documentation explanation vs. compiler/tool signal |
| `forRemoval=true` means already removed | Only an intent to remove; not immediate deletion |
| Suppressing all deprecation warnings to keep code "clean" | Identify replacement APIs and a migration path instead |

**Exercise 1.** Create class `Vehicle` with `move()`, and class `Bike` overriding it with `@Override`; call it via a `Vehicle` variable to observe dispatch based on the actual object.

**Exercise 2.** Intentionally misspell `move` as `mvoe` while keeping `@Override`. Record the compile error; fix the name to make it a valid override.

**Exercise 3.** Create interface `Greeting` with `hello()`, and an implementing class using `@Override`. Why must the implementing method have appropriate access visibility?

**Exercise 4.** Mark method `oldSum(int,int)` with `@Deprecated(since = "17", forRemoval = false)`, write `sum(int,int)` as its replacement, and add Javadoc guiding the migration.

**Exercise 5.** Try `javac -Xlint:deprecation` and identify the warning source. Explain why, despite the warning, `java` can still invoke the old method.

### Takeaways

**`@Override` states "I intend to override a valid method" and asks the compiler to catch signature mismatches. `@Deprecated` states "this API is no longer recommended" without deleting it or stopping runtime calls.** Use Javadoc `@deprecated` to guide replacement; distinguish overriding, overloading, and static hiding; address warnings by understanding the API instead of merely hiding them.