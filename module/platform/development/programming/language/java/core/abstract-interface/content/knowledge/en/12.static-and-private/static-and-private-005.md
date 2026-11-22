# Sharing Code Between Default Methods Using Private Instance Methods in Java

## 1. Why Are Private Methods Needed in Interfaces?

Since Java 8, an interface can define **default methods** with a body, providing default behavior for implementing classes. When multiple default methods need the same processing step, copying the logic into each method duplicates code and makes implementations prone to drifting out of sync during maintenance.

Since **Java 9**, an interface can declare `private` methods to keep shared implementation inside the interface. A **private instance method** has a body, does not have the `static` keyword, and operates in the context of the current object. It allows methods in the interface to share logic without exposing the helper as part of the API.

Usage pattern:

1. Keep default methods as the public entry points.
2. Move the repeated logic into a private instance method.
3. Call that helper from each default method with the appropriate arguments.
4. Keep the helper private so callers and implementing classes do not depend on internal details.

## 2. Java 17+ Example: Two Default Methods Sharing a Helper

Save the following code in **PrivateInterfaceMethodDemo.java**:

~~~java
interface ReportFormatter {
    String serviceName();

    default String success(String user) {
        return format("SUCCESS", user);
    }

    default String failure(String user) {
        return format("FAILURE", user);
    }

    private String format(String status, String user) {
        return "[" + serviceName() + "] " + status + ": "
                + clean(user);
    }

    private String clean(String user) {
        if (user == null || user.isBlank()) {
            return "guest";
        }
        return user.trim();
    }
}

final class BillingFormatter implements ReportFormatter {
    @Override
    public String serviceName() {
        return "Billing";
    }
}

public class PrivateInterfaceMethodDemo {
    public static void main(String[] args) {
        ReportFormatter formatter = new BillingFormatter();
        System.out.println(formatter.success(" Mia "));
        System.out.println(formatter.failure(" "));
        System.out.println(formatter.success(null));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac PrivateInterfaceMethodDemo.java
java PrivateInterfaceMethodDemo
~~~

Exact output:

~~~text
[Billing] SUCCESS: Mia
[Billing] FAILURE: guest
[Billing] SUCCESS: guest
~~~

`success()` and `failure()` are default methods that can be called through a variable of type `ReportFormatter`. Both use `format()`, and `format()` calls `clean()` to process the name. As a result, how the message is assembled is defined only once.

The `format()` helper calls `serviceName()` on the current object. The call is dispatched to `BillingFormatter.serviceName()`, so the result contains `[Billing]`. This is why the example uses a private **instance** method: the helper relies on the behavior of the actual object. `clean()` turns `null`, an empty string, or a whitespace-only string into `guest`; other names have leading and trailing whitespace removed.

## 3. Differences Between Default Methods and Private Instance Methods

| Feature | Default method | Private instance method |
| --- | --- | --- |
| Has a method body | Yes | Yes |
| Callable through an interface-typed variable from a caller | Yes | No |
| Inherited by implementing classes for direct calls | Yes, unless overridden or there is a conflict | No |
| Overridable by implementing classes as an inherited method | Yes | No; private helpers are not inherited |
| Purpose | Default behavior in the API | Sharing internal implementation details |

A caller can call `formatter.success("Mia")` but cannot call `formatter.format("SUCCESS", "Mia")` because `format()` is private. An implementing class also cannot call the helper via `this` or via an interface-typed variable.

If an implementing class declares its own method with the same name `format`, that is not an override of the interface's private helper: the two methods have no inheritance relationship. Calls from default methods still use the helper in the interface. A private method must have a body; do not declare it as an abstract method, and do not combine `private` with `default` in the same declaration.

## 4. When Should You Use a Private Instance Method?

Use it when multiple default methods need the same logic, the logic is an implementation detail, and it requires the context of the current object. A private instance method can call other instance methods in the interface, including abstract methods such as `serviceName()`. Calls to an abstract method are dispatched according to the actual object.

If behavior must be provided by every implementing class, declare a public contract method instead of hiding that behavior in a private helper. If the logic is used only once and extracting a helper makes the processing flow harder to read, there is no need to create an extra method just to extract a single line of code.

## 5. Usage Boundaries

A **private instance method** is suitable when the helper needs object context, such as the `serviceName()` call in the example. If processing relies only on parameters, a `private static` helper may be simpler; a static helper does not have `this` and can only call instance behavior when it has a specific receiver. Both kinds of helpers in an interface require **Java 9 or later**.

You should not create a helper if extracting a method makes a single-use processing flow harder to read. If multiple **unrelated** interfaces need the same algorithm, one interface's private helper cannot be called by another interface; consider a utility class or a shared component.

**Self-check:** Why does `format()` need to be a private *instance* method? Because it calls `serviceName()` on the actual `BillingFormatter` object; a private static helper does not have that object available.
