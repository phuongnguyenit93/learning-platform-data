# Comparing anonymous classes and lambdas on this and name scope

An anonymous class and a lambda can both provide behavior for a functional interface, such as Runnable. The key difference lies in the context that the expression creates: an anonymous class creates an object of a new class, whereas a lambda retains the context from its declaration site. This determines the meaning of this, how names are looked up, and which members can be declared.

## 1. Quick comparison table

| Aspect | Anonymous class | Lambda |
|---|---|---|
| Meaning of this | this refers to the anonymous class object | this retains its meaning from the enclosing context |
| Accessing the enclosing object | Use Outer.this when you need to specify the outer instance | this already refers to the enclosing instance; Outer.this can be used to make the intent explicit |
| Own members | Can declare fields, methods, and initializers in the class body | Cannot declare its own fields or methods in the lambda body |
| Name scope | Has class member scope; own members can shadow names from outside | Uses the lexical scope of the declaration site and the lambda's parameter/local scope |
| Local variables from the enclosing method | Can only capture final or effectively final variables | Can also only capture final or effectively final variables |
| Target type | Can subclass a class or implement an interface | Requires a functional interface as the target type, meaning one abstract method to implement |
| When appropriate | Need separate state, multiple methods, or this of the callback object | Need to pass concise behavior focused on a single method |

## 2. this in an anonymous class

An anonymous class has its own object. Therefore, inside its methods, this is the executing anonymous class object. If that class is declared inside an instance method of the class ThisAndScopeDemo, the expression ThisAndScopeDemo.this refers to the enclosing instance.

When field names are the same, use a prefix that clearly indicates the object to access:

- this.name: the name field of the anonymous class if that class declares this field.
- ThisAndScopeDemo.this.name: the name field of the enclosing ThisAndScopeDemo instance.
- A method call without a prefix inside an anonymous class is looked up in that class's context first; use ThisAndScopeDemo.this.someMethod() when you need to explicitly call a method of the outer instance.

An anonymous class can also declare methods, fields, and initializers. It does not declare a constructor with its own name, because the class itself has no name; an initializer can be used if you need to initialize its own state.

## 3. this in a lambda

A lambda does not create a new this binding. If a lambda is written inside an instance method of ThisAndScopeDemo, this inside the lambda is still the ThisAndScopeDemo instance. Therefore, this.name reads the field of the enclosing class.

A lambda also does not create a new class context for super. References to this and super are interpreted according to the lexical context where the lambda is declared. If a lambda is inside a static method, there is no enclosing instance for this to refer to, so writing this there is still a compile-time error.

Do not confuse this with the lambda object itself. A lambda is still an object that can be assigned to a variable, passed as an argument, or compared by reference. However, from inside the lambda body, this means the enclosing instance. The class information generated for a lambda object is an implementation detail; you should not rely on the auto-generated class name or the identity behavior of a lambda when designing business logic.

## 4. Runnable Java example

Save the following content in the file ThisAndScopeDemo.java. The example illustrates this, a shadowed field, and a captured local variable.

~~~java
public class ThisAndScopeDemo {
    private final String name = "outer field";

    private void demonstrate() {
        String text = "captured local";

        Runnable anonymous = new Runnable() {
            private final String name = "anonymous field";

            @Override
            public void run() {
                System.out.println("anonymous this == outer: "
                        + (this == (Object) ThisAndScopeDemo.this));
                System.out.println("anonymous this.name = " + this.name);
                System.out.println("anonymous outer name = "
                        + ThisAndScopeDemo.this.name);
                System.out.println("anonymous captured text = " + text);
            }
        };

        Runnable lambda = () -> {
            System.out.println("lambda this == outer: "
                    + (this == ThisAndScopeDemo.this));
            System.out.println("lambda this.name = " + this.name);
            System.out.println("lambda captured text = " + text);
        };

        anonymous.run();
        lambda.run();
    }

    public static void main(String[] args) {
        new ThisAndScopeDemo().demonstrate();
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac ThisAndScopeDemo.java
java ThisAndScopeDemo
~~~

Stdout output:

~~~text
anonymous this == outer: false
anonymous this.name = anonymous field
anonymous outer name = outer field
anonymous captured text = captured local
lambda this == outer: true
lambda this.name = outer field
lambda captured text = captured local
~~~

In the first line, the cast to Object makes it possible to compare two references with different static types. The false result shows that this in the anonymous class is the callback object; the corresponding line for the lambda is true because this in the lambda is the enclosing instance itself. The anonymous class declares its own name field, so this.name reads that field, whereas ThisAndScopeDemo.this.name reads the field of the enclosing instance.

## 5. Name scope and name shadowing

### Fields with the same name

In the example above, both the enclosing class and the anonymous class have a name field. The unqualified name this.name in the anonymous class's method refers to the field of the anonymous class object. To access the enclosing class's field, you must explicitly write ThisAndScopeDemo.this.name.

In a lambda, there are no separate fields belonging to the lambda body. Therefore, the expression this.name refers to the name field of the enclosing instance. This rule helps lambdas generally keep name lookup close to code written directly in the enclosing method.

### Parameters and local variables

A lambda parameter is scoped to the lambda. A lambda's parameter name or local variable name cannot collide with an existing local variable or parameter in the enclosing scope. The following example intentionally fails to compile:

~~~java
String value = "outer";
java.util.function.Consumer<String> consumer =
        value -> System.out.println(value); // Error: the name value is already declared in the enclosing scope
~~~

Rename the parameter, for example to item, to avoid the conflict. This rule applies even when the lambda parameter is in a multi-line expression.

An anonymous class has its own class scope, so it can declare members with names matching members of the enclosing class. When names might cause confusion, use this.field for the anonymous class's member and Outer.this.field for the enclosing instance's member. Methods inside an anonymous class also have their own parameter and local variable scope.

### Capturing local variables

Both anonymous classes and lambdas can only capture local variables or parameters declared final or effectively final. Effectively final means that after being assigned an initial value, the variable is not reassigned. For example, text in the sample program is read from both callbacks without being reassigned, so it is valid.

Capturing does not turn a local variable into a variable that can be reassigned from the callback. If you need to change state, choose an appropriate data model, such as an object with well-designed mutable state, or move the state into a field of an object with an appropriate lifecycle. You should not use a mutable wrapper just to work around the rule when a simpler design can solve the problem.

## 6. How to choose

Choose a lambda when you need to implement a single behavior for a functional interface, such as a predicate, comparator, callback, or stream operation. The syntax is shorter and this continues to refer to the enclosing instance, which causes fewer surprises when the callback needs to call methods or read fields of the class being written.

Choose an anonymous class when you need separate fields per callback, need multiple methods in the class body, need to subclass an abstract class, or intentionally need this to refer to the callback object. For an interface with only one abstract method, either approach may be appropriate; choose the one that clearly expresses intent and makes the name scope easy to understand.

Do not convert an anonymous class to a lambda just to reduce line count if that change alters the meaning of this, super, or how names are looked up. Before refactoring, check all uses of this, super, fields with the same name, unqualified methods, and captured local variables.

## 7. Common mistakes

- Using this in a lambda as if it referred to the callback object. In a lambda, this retains the enclosing context.
- Using this.name in an anonymous class and assuming it always reads the enclosing class's field. If the anonymous class has a name field, the expression reads the anonymous class's field; use Outer.this.name to specify it explicitly.
- Reassigning a local variable after it has been captured. Both types of callbacks require captured local variables to be final or effectively final.
- Declaring a lambda parameter with the same name as a local variable in the enclosing method. Choose a different name to avoid a compile-time error.
- Relying on the auto-generated class name or the identity of a lambda. That is not a stable contract for business logic.
- Assuming a lambda can declare fields or methods like a class. If a callback needs state or multiple methods, consider an anonymous class or a named class.

## 8. Self-check

1. In a method of an anonymous class, what does this.name refer to if the anonymous class declares a name field? Answer: the name field of the anonymous class.
2. In a lambda written inside an instance method, what does this.name refer to? Answer: the name field of the enclosing instance.
3. Can both callbacks capture a local variable that is not explicitly declared final? Yes, if that variable is effectively final.
4. When you need to explicitly call a method on the enclosing instance from an anonymous class, how should you write it? Use Outer.this.methodName() with the appropriate enclosing class name.
