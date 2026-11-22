# Explicit Contract Implementation Using Methods with @Override

In Java, **@Override** is an annotation placed on a method declaration so that the compiler verifies that the method actually overrides an inherited method or implements a method declared in an interface. It expresses intent and helps detect signature mismatches at compile time.

Java does not have dedicated syntax to create a separate interface implementation by interface name as some other languages do. Here, "explicit" means writing out the implementing method clearly and marking it with **@Override**.

## 1. Complete Example

The following program demonstrates both implementing an interface and overriding a method that already has a body in the superclass. Save it as **OverrideDemo.java**:

~~~java
public class OverrideDemo {
    interface Formatter {
        String format(String value);
    }

    static class BasicFormatter implements Formatter {
        @Override
        public String format(String value) {
            return value.trim();
        }
    }

    static final class BracketFormatter extends BasicFormatter {
        @Override
        public String format(String value) {
            return "[" + super.format(value) + "]";
        }
    }

    public static void main(String[] args) {
        Formatter formatter = new BracketFormatter();
        System.out.println(formatter.format(" Java "));
    }
}
~~~

Compile and run:

~~~bash
javac OverrideDemo.java
java OverrideDemo
~~~

Output:

~~~text
[Java]
~~~

**BasicFormatter.format()** satisfies the interface contract. **BracketFormatter.format()** overrides the superclass method that has a body and uses **super.format(value)** to reuse the trim processing. Even though the **formatter** variable has the interface as its static type, at runtime Java invokes the **BracketFormatter** implementation based on the actual object.

## 2. What Does the Annotation Check?

| What @Override helps the compiler check | What @Override does not do |
| --- | --- |
| The method has a valid override/implement relationship with a supertype or interface | Does not automatically generate the method body |
| Detects a misspelled name, wrong parameter types, or an overload mistaken for an override | Does not change the access level to public |
| Detects an intent to override a method that cannot be overridden | Does not automatically call the superclass method |
| Clearly expresses intent to readers and analysis tools | Does not prove that the logic fully satisfies the business semantics |

Syntactically, the annotation is not mandatory for every valid overriding method. However, it should be used regularly: if a signature changes in the interface or superclass, the compiler can point out the methods that no longer override as intended.

## 3. Distinguishing Override and Overload

The following snippet is intentionally written incorrectly:

~~~java
interface Printer {
    void print(String value);
}

class ConsolePrinter implements Printer {
    @Override
    public void print(Object value) {
        System.out.println(value);
    }
}
~~~

The contract requires **print(String)**, but the class declares **print(Object)**. The two methods have different parameter types, so they do not have an override relationship. **@Override** causes the compiler to report an error right at the declaration; if the annotation is removed, the concrete class still has not implemented **print(String)**, so it remains invalid.

Parameter variable names do not affect the signature: **print(String text)** can implement **print(String value)**. Changing parameter types, the number of parameters, or the order of parameter types can create a different overload. The return type also cannot be used alone to distinguish two overloads; the return type of an overriding method must follow Java's compatibility rules.

## 4. Using @Override with Different Kinds of Methods

- **Implementing an abstract interface method:** declare a method with a body and keep the exact signature, return type, and public access level required by the contract.
- **Completing an abstract method from a superclass:** mark the concrete method so the compiler confirms that it properly fulfills the abstract declaration.
- **Changing the behavior of a concrete method in a superclass:** it can be overridden if the method is not final, private, or static in a way that makes the override relationship invalid.
- **Overriding a default method:** the annotation can be used when you want to replace the interface's default behavior. If multiple default methods conflict, the class must resolve the conflict according to Java's rules.
- **A method that is only inherited without being redeclared:** there is no place to attach the annotation. There is no need to rewrite the method just to add @Override.

The annotation does not turn a static method into an instance method, does not allow overriding a final method, and does not make a superclass private method overridable. When you want to invoke superclass logic, you must write an explicit **super.method(...)** call.

## 5. Safe Implementation Workflow

1. Read the interface or superclass declaration to know the exact method that needs to be implemented.
2. Write the exact name and parameter types, a compatible return type, and the required access level.
3. Place **@Override** before the method and compile. If the compiler reports that it cannot override, check the signature instead of removing the annotation to hide the error.
4. Write the body that performs the behavior required by the contract. The annotation only checks the type relationship; it does not verify business results.
5. Test both calls through interface/superclass-typed variables and edge cases of the concrete behavior.

## 6. Self-Check

**Question 1.** The **Converter** interface declares **String convert(String value)**. Can the method **public String convert(String input)** implement it?

**Answer:** yes; parameter names are not part of the signature.

**Question 2.** Can the method **public Object convert(String value)** override the declaration above?

**Answer:** no; the Object return type is broader than String, so it does not satisfy the return-type compatibility rule.

**Question 3.** If @Override is omitted from a method with incorrect parameter types, will the compiler automatically treat it as an override?

**Answer:** no. The annotation does not create an override relationship; omitting the annotation also does not fix the missing method.

**Takeaway:** write the concrete method to satisfy the contract, then use @Override so the compiler checks your intent. The annotation catches method-relationship errors early, while behavioral correctness must still be evaluated separately.
