# Creating an Abstract Class to Share Data Validation and Logging

When multiple data-processing classes share the same input workflow, they often repeat steps such as checking for empty data, normalizing strings, logging start/end, and handling errors. If each class rewrites these steps on its own, rules can easily diverge: one class forgets to check for `null`, another logs inconsistently, or the order of checking and processing differs.

An **abstract class** lets you consolidate the shared workflow into one place while letting subclasses define their specific processing. This practice exercise builds a text processor with shared validation and logging steps; subclasses only decide how to transform the validated data.

## 1. Identifying Shared and Varying Parts

Suppose an application has two requirements: converting text to uppercase and counting words. The two requirements differ in their processing operation, yet both need to:

1. Log when starting.
2. Reject `null` or whitespace-only data.
3. Strip leading and trailing whitespace before processing.
4. Run the processor's specialized logic.
5. Log success or record input errors.
6. Return the result to the caller.

These steps form a stable workflow. Only the specialized processing step needs to vary across classes. We will place the shared workflow in the `process` method of the abstract class and declare an abstract `transform` method for subclasses to implement.

This separation ensures that every processor follows the same sequence without duplicating validation and logging code.

## 2. Why Use an Abstract Class?

An abstract class is suitable when multiple subclasses need to share both **behavior** and **state**. The base class can hold the processor name, implement the validation logic, and provide the logging method. Subclasses only need to implement the extension point.

An interface typically describes a contract that implementing classes must fulfill; an interface can also have `default` and `static` methods, but it does not provide ordinary instance state through instance fields. An abstract class is suitable when you want to share fields, constructors, implemented methods, and abstract methods within the same hierarchy.

Do not create an abstract class just to avoid a few lines of duplication. Use it when classes genuinely belong to the same concept and have a stable common workflow. If you only need to pass a simple processing rule, a lambda expression or a functional interface may be more lightweight.

## 3. Designing the Base Class

The `AbstractTextProcessor` class has three responsibilities:

- `process(String input)` is the public entry point and orchestrates the shared workflow.
- `validate(String input)` validates the data and returns the string with leading/trailing whitespace removed.
- `transform(String input)` is the extension point for subclasses to perform their own work.

The `process` method is declared `final` so subclasses cannot override it and accidentally bypass validation or logging. The `validate` and `log` methods are `private` because only the base class needs to call them. `transform` is `protected abstract` so subclasses can implement it, while external callers cannot invoke it directly through the public API.

The workflow uses `try/catch` to log when validation or processing throws `IllegalArgumentException`, and then rethrows the exception so the caller still knows the operation failed. Logging must not silently turn an error into a valid result.

## 4. Complete Java 17+ Program

Save all the code below into a file named `SharedValidationLoggingDemo.java`. The example places the abstract class, two subclasses, and the runner class in the same file for easy compilation; only `SharedValidationLoggingDemo` is a `public` class.

~~~java
import java.util.Locale;

abstract class AbstractTextProcessor {
    private final String name;

    protected AbstractTextProcessor(String name) {
        this.name = name;
    }

    public final String process(String input) {
        log("Bắt đầu xử lý");
        try {
            String validated = validate(input);
            String result = transform(validated);
            log("Xử lý thành công");
            return result;
        } catch (IllegalArgumentException ex) {
            log("Xử lý thất bại: " + ex.getMessage());
            throw ex;
        }
    }

    private String validate(String input) {
        if (input == null || input.isBlank()) {
            throw new IllegalArgumentException(
                "Dữ liệu không được null hoặc chỉ chứa khoảng trắng"
            );
        }
        return input.strip();
    }

    protected abstract String transform(String input);

    private void log(String message) {
        System.out.println("[" + name + "] " + message);
    }
}

final class UppercaseProcessor extends AbstractTextProcessor {
    UppercaseProcessor() {
        super("UPPER");
    }

    @Override
    protected String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

final class WordCountProcessor extends AbstractTextProcessor {
    WordCountProcessor() {
        super("WORDS");
    }

    @Override
    protected String transform(String input) {
        return "Số từ: " + input.split("\\s+").length;
    }
}

public class SharedValidationLoggingDemo {
    public static void main(String[] args) {
        AbstractTextProcessor uppercase = new UppercaseProcessor();
        AbstractTextProcessor wordCount = new WordCountProcessor();

        System.out.println("Kết quả: " + uppercase.process("  hello Java  "));
        System.out.println("Kết quả: " + wordCount.process("learn abstract class"));

        try {
            uppercase.process("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Đã bắt lỗi: " + ex.getMessage());
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~text
javac SharedValidationLoggingDemo.java
java SharedValidationLoggingDemo
~~~

Exact stdout output:

~~~text
[UPPER] Bắt đầu xử lý
[UPPER] Xử lý thành công
Kết quả: HELLO JAVA
[WORDS] Bắt đầu xử lý
[WORDS] Xử lý thành công
Kết quả: Số từ: 3
[UPPER] Bắt đầu xử lý
[UPPER] Xử lý thất bại: Dữ liệu không được null hoặc chỉ chứa khoảng trắng
Đã bắt lỗi: Dữ liệu không được null hoặc chỉ chứa khoảng trắng
~~~

The output shows that the two subclasses have different behavior yet follow the same processing sequence. `UppercaseProcessor` converts the string to uppercase; `WordCountProcessor` counts words. Both automatically use the same validation step and the same log format because they inherit `process` from the base class.

The final call passes a string containing only whitespace. The `validate` method throws `IllegalArgumentException`; the base class logs the failure and then rethrows the exception. The `catch` block in `main` handles that exception and prints the final message.

## 5. Understanding the Execution Flow and Template Method

The design above is an example of the **Template Method** pattern. The `process` method defines the algorithm skeleton: log start → validate → transform → log success. The `transform` step is delegated to subclasses.

Successful execution flow:

~~~text
process(input)
    |
    v
log("Bắt đầu xử lý")
    |
    v
validate(input)
    |
    v
transform(validated)
    |
    v
log("Xử lý thành công")
    |
    v
return result
~~~

If validation or `transform` throws `IllegalArgumentException`, the flow switches to the failure-logging branch and then rethrows the exception. Exceptions of other types are not caught in this example, so they propagate to the caller. This is an intentional choice: only errors defined in the processing contract are logged through the expected error branch.

The `final` keyword on `process` protects the algorithm skeleton. Without it, a subclass could override the method and forget to call `validate` or skip logging. Use `final` when adhering to the shared order is a design invariant; if a subclass truly needs to change the entire workflow, a different architecture may be needed.

## 6. Role of Constructors, Access Levels, and Overriding

The `AbstractTextProcessor(String name)` constructor is declared `protected` so subclasses can invoke it via `super(...)`. An abstract class cannot be instantiated directly with `new AbstractTextProcessor(...)`; you must create a concrete class that implements the abstract method.

The `name` field is `private final`, so only the base class accesses it and assigns its value in the constructor. This keeps the logger name consistent throughout the object's lifetime. In a real application, the constructor should also validate whether the name is valid, for example by rejecting `null` or an empty string.

Subclasses annotate `transform` with `@Override` so the compiler verifies the overriding signature. If the method name is misspelled or parameter types are wrong, the error is caught at compile time. An abstract method has no body; a concrete class must provide the implementation.

`UppercaseProcessor` uses `Locale.ROOT` when converting to uppercase to avoid results depending on the machine's default locale, which is helpful for technical normalization. The word-count example splits the normalized string using the regular expression `\\s+`; this is a simple word-counting approach for whitespace-separated text, not a natural language analyzer for all languages.

## 7. Adapting the Design for Real Applications

The example uses `System.out.println` so learners can see the output immediately. In a real application, use a logging framework such as SLF4J with Logback or your project's appropriate logging API to get log levels, timestamps, correlation information, and output routing capabilities. Avoid logging sensitive user data in full.

Validation rules should reflect business domain requirements. For example, an order-code processor might validate the code format; an email processor might check conditions required by the application. Do not place rules specific to a single subclass into the base class if other classes do not share those same conditions.

It is also important to distinguish input validation from result validation. The base class currently validates the input string before calling `transform`. If all results must adhere to a common contract, a result-validation step can be added after `transform`; do this only when there is a clear shared rule.

If duration logging is needed, you can measure start and end times inside `process`. If you also want to log exceptions other than `IllegalArgumentException`, you must explicitly decide whether the method catches `RuntimeException`, checked exceptions, or logs only at the calling layer. Catching too broadly and swallowing errors hides failures and misleads the caller into thinking processing succeeded.

## 8. Common Mistakes

- **Repeating validation in every subclass:** creates the risk of diverging rules. Place rules that are truly shared in the base class.
- **Letting subclasses override the orchestrating method:** can break the validation and logging order. Consider declaring the template method as `final`.
- **Calling `transform` before checking input:** empty data can cause confusing errors inside subclasses. Validate before the processing step.
- **Logging and then swallowing the exception:** leaves the caller unaware that the operation failed. Log and rethrow the error, or translate it into a domain exception under a clear contract.
- **Catching all exceptions indiscriminately:** can mask programming bugs or system failures. Only catch error types that the class can handle meaningfully.
- **Putting everything into the base class:** the parent class becomes hard to maintain if it holds too many rules that apply only to one subclass. Share only what is genuinely common.
- **Using inheritance just to reuse a small method:** can create rigid class relationships. If objects do not have an “is-a” relationship, consider composition or passing a processing interface into the constructor.

## 9. Checklist When Building a Shared Abstract Class

Before applying this pattern to a project, check the following:

1. Do the subclasses share the same core business workflow?
2. Which steps must always run and should reside in the template method?
3. Which steps truly differ and should become abstract methods or hooks?
4. Does the access level of each field/method restrict access appropriately?
5. Should `final` be used to protect workflow invariants?
6. When an error occurs, which exceptions will the base class log, translate, or rethrow?
7. Can the example compile, run, and produce predictable output?

If the answers regarding the shared steps and varying steps are clear, an abstract class can make the design easier to understand, reduce duplication, and keep behavior consistent. If the boundaries are not yet clear, start with two concrete classes and extract the base class only after the shared workflow has been identified.

## 10. Key Takeaways

An abstract class is useful when multiple subclasses need to share state and part of a workflow while still having their own processing steps. In this exercise, `process` is the Template Method that orchestrates validation, transformation, and logging; `transform` is the extension point for each subclass. Protect mandatory steps, validate data before processing, log meaningfully, and let exceptions propagate to where they can be handled.
