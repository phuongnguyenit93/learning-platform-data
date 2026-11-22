# Unchecked exceptions and calling code responsibilities when overriding methods in Java

Unchecked exceptions include RuntimeException and its subclasses, as well as Error and its subclasses. The compiler does not force the caller to catch or declare them. An override can throw a new unchecked exception even if the parent method does not have a throws clause; that can still change the behavior observed by API users.

## 1. Not declaring throws does not mean it cannot fail

~~~java
interface TextProcessor {
    String process(String input);
}

final class UpperProcessor implements TextProcessor {
    @Override
    public String process(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        if (input.isBlank()) {
            throw new IllegalArgumentException("input must not be blank");
        }
        return input.strip().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

IllegalArgumentException is unchecked, so the signature does not need to include throws. However, a call with null or a blank string can still throw an exception at runtime. throws X is a declaration; throw new X(...) is the statement that actually throws the object.

## 2. Example of a caller handling input errors

~~~java
public class UncheckedDemo {
    public static void main(String[] args) {
        TextProcessor processor = new UpperProcessor();
        show(processor, "  Java  ");
        show(processor, "   ");
        show(processor, null);
    }

    private static void show(TextProcessor processor, String input) {
        try {
            System.out.println("Result: " + processor.process(input));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

When combined with the interface and implementation in section 1, the program prints:

~~~text
Result: JAVA
Rejected: input must not be blank
Rejected: input must not be null
~~~

The caller catches the specific input error where it can display a message and continue processing. Without a catch, an unchecked exception can propagate up the stack and terminate the thread when there is no suitable handler.

## 3. The compiler does not check the entire behavioral contract

Java allows an override to add unchecked exceptions, but type substitutability still matters. If the parent class promises that an operation succeeds for all valid inputs, a subclass arbitrarily throwing IllegalStateException for those inputs can break the contract even though it still compiles.

Implementation authors should:

- Clearly state preconditions such as non-null, positive values, or required state.
- Use meaningful exception types: IllegalArgumentException for invalid arguments, IllegalStateException for an inappropriate state, or a custom exception when genuinely needed.
- Avoid making partial state changes before reporting an error if possible; Java does not automatically roll back all changes when a RuntimeException occurs.
- Preserve the cause when translating an exception so diagnostic information is not lost.

## 4. Caller responsibilities

The caller does not need to wrap every call in a catch for RuntimeException. Instead:

- Validate user-supplied data when a better message can be provided.
- Catch expected exception types at boundaries where there is a specific way to handle them.
- Let unexpected errors propagate to an appropriate handling mechanism instead of silently swallowing them.
- Clean up resources with try-with-resources or finally when needed; do not assume that an exception automatically closes all resources or rolls back a transaction.

Throwable or Error should not be caught as ordinary input errors. The fact that an exception has been caught also does not guarantee that the operation has not produced side effects.

## 5. Distinguishing from checked exceptions

The rule for declaring checked exceptions when overriding was presented in the previous lesson: a subclass must not broaden checked exceptions that the parent contract does not permit. For unchecked exceptions, the compiler does not apply a similar throws restriction, so JavaDoc and the behavioral contract are even more important.

**Remember:** the compiler verifies type rules and checked exceptions; it does not prove that every implementation adheres to the business semantics of the parent type. API authors must describe predictable errors, while the caller needs to handle failure scenarios at the right boundary.
