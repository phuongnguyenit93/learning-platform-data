# Template Method in Java: Fixing an Algorithm Skeleton, Customizing Individual Steps

> **Learning path:** OOP → Design Patterns → Template Method and the algorithm skeleton.  
> **Objective:** Understand Template Method, identify fixed versus variable steps, implement a superclass and subclasses in Java, verify execution order, distinguish Strategy/Factory Method, and recognize when inheritance adds cost.

## 1. What Problem Does Template Method Solve?

Many programs perform tasks with **the same overall process** but different steps. Consider generating a sales report:

1. Receive and validate transaction data.
2. Calculate total revenue.
3. Generate the report heading.
4. Render each transaction.
5. Generate the summary line.
6. Optionally add a footer.

Plain-text and Markdown reports must perform these steps **in the correct order**; only the presentation of headings, transaction lines, and summaries differs.

If each report type independently implements the complete `generate()` process, data validation, total calculation, and step order may be duplicated. One variant might forget to reject negative amounts or omit a summary.

**Template Method** is a GoF *behavioral pattern*: define **an algorithm skeleton in a superclass method** while letting subclasses implement or override selected steps **without changing the overall algorithm structure**.

How to read a Template Method design:

| Component | Role |
|---|---|
| **Abstract Class** | Superclass owns the workflow and defines extension steps |
| **Template Method** | Coordinates step order; often marked `final` to prevent overrides |
| **Concrete Operation** | Fully implemented step in the superclass, shared by all variants |
| **Primitive Operation** | An `abstract` step that subclasses must provide |
| **Hook** | A step with default behavior that subclasses **may** override |
| **Concrete Class** | Subclass implementing differences specific to a variant |

The pattern name refers to a **“workflow template”**, not a C++ generic-type template or a UI template file.

## 2. From Duplicated Code to a Shared Skeleton

An initial design often has two independent classes:

~~~java
// Phác thảo để thấy chỗ trùng lặp, không phải chương trình hoàn chỉnh.
class TextReport {
    String generate(List<Sale> sales) {
        validate(sales);
        BigDecimal total = calculateTotal(sales);
        // Render tiêu đề văn bản, từng dòng, tổng kết...
        return "...";
    }
}

class MarkdownReport {
    String generate(List<Sale> sales) {
        validate(sales);
        BigDecimal total = calculateTotal(sales);
        // Render tiêu đề Markdown, từng dòng, tổng kết...
        return "...";
    }
}
~~~

Both classes must preserve the order `validate → calculateTotal → render`. If the business adds a shared step, such as checking transaction IDs, both may need modification.

Refactoring idea:

- **Keep in the superclass:** input-list validation, snapshotting, total calculation, step order, and result assembly.
- **Customize in subclasses:** heading content, transaction representation, and summary format.
- **Use a hook:** the optional report footer can default to empty or be customized by subclasses.

This mechanism is often expressed as the “**Hollywood Principle**”: *Do not call us; we will call you*. The superclass chooses when to invoke steps provided by subclasses, so subclasses need not reconstruct the entire workflow.

## 3. Complete Java 17 Example: Generating Sales Reports

The example uses only the JDK. Every transaction has a transaction code and an amount in VND with two decimal places **to simplify the lesson**; this is a demo convention, not a claim that VND always requires two decimal digits.

Input contract:

- Transaction codes contain only uppercase `A–Z`, digits, or `-` for safe plain-text/Markdown rendering.
- Amounts must be nonnegative, non-null, and exactly representable with two decimal places.
- The transaction list must not be null and may be empty; null elements are forbidden.
- Subclasses only **format** output; they must not modify amounts or silently drop transactions.

Create **`TemplateMethodDemo.java`** and copy the full example below:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

// Mỗi Sale là một value object bất biến.
// Compact constructor của record chuẩn hóa số tiền.
record Sale(String code, BigDecimal amount) {
    Sale {
        Objects.requireNonNull(code, "code");
        Objects.requireNonNull(amount, "amount");

        if (!code.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException(
                    "code must contain only A-Z, 0-9 or -");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must be nonnegative");
        }

        try {
            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "amount has fractions smaller than 0.01", ex);
        }
    }
}

// Abstract Class: chứa quy trình chung và các extension points.
abstract class SalesReportTemplate {

    // TEMPLATE METHOD: luồng xử lý cuối cùng của mọi biến thể.
    public final String generate(List<Sale> source) {
        Objects.requireNonNull(source, "source");

        // Snapshot; List.copyOf cũng từ chối phần tử null.
        List<Sale> sales = List.copyOf(source);

        // Concrete operation: cùng công thức tổng cho mọi báo cáo.
        BigDecimal total = sales.stream()
                .map(Sale::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                .setScale(2, RoundingMode.UNNECESSARY);

        StringBuilder output = new StringBuilder();

        // Các primitive operations sẽ được dispatch tới subclass.
        output.append(Objects.requireNonNull(
                header(), "header returned null"));

        for (Sale sale : sales) {
            output.append(Objects.requireNonNull(
                    row(sale), "row returned null"));
        }

        output.append(Objects.requireNonNull(
                summary(sales.size(), total),
                "summary returned null"));

        // Hook tùy chọn: không yêu cầu mọi subclass tự viết lại.
        output.append(Objects.requireNonNull(
                footer(), "footer returned null"));

        return output.toString();
    }

    // Primitive operations: subclass bắt buộc cài đặt.
    protected abstract String header();
    protected abstract String row(Sale sale);
    protected abstract String summary(int count, BigDecimal total);

    // Hook: hành vi mặc định là không thêm phần cuối báo cáo.
    protected String footer() {
        return "";
    }
}

// Concrete Class A: định dạng văn bản thuần.
final class TextSalesReport extends SalesReportTemplate {
    @Override
    protected String header() {
        return "BÁO CÁO DOANH THU\n-----------------\n";
    }

    @Override
    protected String row(Sale sale) {
        return sale.code() + ": "
                + sale.amount().toPlainString() + " VND\n";
    }

    @Override
    protected String summary(int count, BigDecimal total) {
        return "Tổng " + count + " giao dịch: "
                + total.toPlainString() + " VND\n";
    }

    // Không ghi đè footer(): dùng hành vi mặc định của hook.
}

// Concrete Class B: định dạng bảng Markdown.
final class MarkdownSalesReport extends SalesReportTemplate {
    @Override
    protected String header() {
        return "| Mã giao dịch | Số tiền (VND) |\n"
                + "|---|---:|\n";
    }

    @Override
    protected String row(Sale sale) {
        return "| " + sale.code() + " | "
                + sale.amount().toPlainString() + " |\n";
    }

    @Override
    protected String summary(int count, BigDecimal total) {
        return "| **Tổng (" + count + ")** | **"
                + total.toPlainString() + "** |\n";
    }

    @Override
    protected String footer() {
        return "\n_Tự động tạo báo cáo._\n";
    }
}

public class TemplateMethodDemo {
    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("S-01", new BigDecimal("120.00")),
                new Sale("S-02", new BigDecimal("30.50"))
        );

        SalesReportTemplate textReport = new TextSalesReport();
        SalesReportTemplate markdownReport = new MarkdownSalesReport();

        System.out.println(textReport.generate(sales));
        System.out.println(markdownReport.generate(sales));
    }
}
~~~

Compile and run:

~~~bash
javac TemplateMethodDemo.java
java TemplateMethodDemo
~~~

Output:

~~~text
BÁO CÁO DOANH THU
-----------------
S-01: 120.00 VND
S-02: 30.50 VND
Tổng 2 giao dịch: 150.50 VND

| Mã giao dịch | Số tiền (VND) |
|---|---:|
| S-01 | 120.00 |
| S-02 | 30.50 |
| **Tổng (2)** | **150.50** |

_Tự động tạo báo cáo._
~~~

**Why Is This Template Method?**

1. `SalesReportTemplate.generate()` owns the **order** of the steps.
2. `generate()` is `final`, so subclasses cannot override it to skip total calculation, reorder steps, or forget shared processing.
3. `header()`, `row()`, and `summary()` are **primitive operations**: abstract methods invoked by the template and implemented by subclasses.
4. `footer()` is a **hook** defaulting to `""`. `TextSalesReport` need not override it; `MarkdownSalesReport` adds an optional note.
5. `TextSalesReport`/`MarkdownSalesReport` determine **how results are presented**, not how to orchestrate the algorithm.

Note that `final` only prevents overriding **the template method**; it cannot automatically prevent all subclass bugs. For example, a subclass implementation of `row()` could return an incorrect value or produce unexpected side effects. Contracts and tests still matter.

## 4. Class Diagram and Execution Sequence

### 4.1. Class Structure

~~~mermaid
classDiagram
    class SalesReportTemplate {
        <<abstract>>
        +generate(source) String
        #header() String*
        #row(sale) String*
        #summary(count,total) String*
        #footer() String
    }
    class TextSalesReport {
        #header() String
        #row(sale) String
        #summary(count,total) String
    }
    class MarkdownSalesReport {
        #header() String
        #row(sale) String
        #summary(count,total) String
        #footer() String
    }
    SalesReportTemplate <|-- TextSalesReport
    SalesReportTemplate <|-- MarkdownSalesReport
~~~

The `*` marker in the diagram indicates abstract steps. The example Java code declares `generate()` as `final`; the diagram merely summarizes method signatures.

### 4.2. Who Controls the Order?

~~~mermaid
sequenceDiagram
    actor Client
    participant Context as SalesReportTemplate
    participant Sub as Concrete Report
    Client->>Context: generate(sales)
    Note over Context: Snapshot danh sách + tính total
    Context->>Sub: header()
    Sub-->>Context: Văn bản tiêu đề
    loop Mỗi Sale
        Context->>Sub: row(sale)
        Sub-->>Context: Dòng đã format
    end
    Context->>Sub: summary(count, total)
    Sub-->>Context: Dòng tổng kết
    Context->>Sub: footer()
    Sub-->>Context: Nội dung hook hoặc chuỗi rỗng
    Context-->>Client: Chuỗi báo cáo hoàn chỉnh
~~~

When calling `new MarkdownSalesReport().generate(...)`, execution still starts in the method inherited from `SalesReportTemplate`. Only the individual virtual steps are dispatched by the JVM to the runtime implementation.

## 5. Three Groups of Steps in Template Method

A good design distinguishes **invariant steps**, **required variation steps**, and **optional steps**:

| Group | Java characteristic | Example | Usage |
|---|---|---|---|
| **Shared step** | `private` or `final` method with complete logic | Snapshot, total calculation, data validation | Keep in the superclass; do not create an override point unnecessarily |
| **Abstract step** | `protected abstract` | `header()`, `row(...)`, `summary(...)` | Subclasses must provide an implementation |
| **Hook** | `protected` method with a default | `footer() { return ""; }` | Subclasses override only when needed |
| **Template Method** | Often `public final` | `generate(...)` | Coordinates steps in a deliberate order |

The word “**often**” matters: GoF does not require every Template Method to be `final`. Java permits a template method that is not `final`, and some frameworks intentionally extend the entire process. When the goal is **preserving the algorithm skeleton**, marking it `final` protects the design intent.

### 5.1. What Is a Hook For?

A hook is an **optional** extension point. Most reports need no footer, but Markdown may add a note. A hook should have safe, understandable default behavior without requiring subclasses to implement empty methods.

A hook may also control a decision:

~~~java
// Ví dụ minh họa, giả sử đặt trong một abstract class khác.
protected boolean shouldAddTimestamp() {
    return false;
}
~~~

The Template Method may invoke `shouldAddTimestamp()` at a predetermined point. This works for one small option; numerous interdependent hooks can create unpredictable combinations of overrides.

### 5.2. Should Subclasses Modify Shared Data?

In the example, `row(Sale)` receives an immutable `record`. The subclass cannot modify `Sale` in place, protecting input data. If a hook receives a mutable `List`, one subclass might remove elements, reorder them, or affect the summary step.

Therefore:

- Pass immutable parameters, value objects, or appropriate copies.
- Distinguish **extending presentation** from **changing business rules**.
- Clearly specify which hooks can change which values and what must remain invariant.
- Do not expose the entire superclass internals as `protected` merely for subclass convenience; that increases coupling and complicates refactoring.

## 6. Common Design Mistakes

### Mistake 1: Every Subclass Overrides the Whole Template

~~~java
abstract class ImportTask {
    // Không final; mọi subclass đều có thể thay đổi thứ tự.
    public void execute() {
        validate();
        parse();
        save();
    }

    protected abstract void validate();
    protected abstract void parse();
    protected abstract void save();
}
~~~

If the required order is `validate → parse → save`, consider `public final void execute()`. If a subclass legitimately needs a different order, **the algorithm skeleton may not actually be stable**; reconsider the abstraction instead of arbitrarily changing subclass code.

### Mistake 2: Calling Overridable Methods from a Superclass Constructor

~~~java
abstract class UnsafeBase {
    UnsafeBase() {
        configure(); // Nguy hiểm: dispatch tới subclass khi chưa khởi tạo xong.
    }
    protected abstract void configure();
}

final class UnsafeChild extends UnsafeBase {
    private final String prefix = "ready";

    @Override
    protected void configure() {
        System.out.println(prefix.length());
    }
}
~~~

In Java, the superclass constructor runs **before** subclass field initialization completes. `configure()` may execute while `prefix == null`, causing `NullPointerException`. Avoid calling hooks/abstract methods from constructors; invoke the template after full object initialization or use a factory that constructs objects before starting work.

### Mistake 3: Forcing Subclasses to Support Nonsensical Steps

If an `ImportTask` defines `decrypt()` but many sources are never encrypted, requiring every subclass to implement `decrypt() { throw new UnsupportedOperationException(); }` suggests a poorly designed contract.

Depending on requirements, use a safe default hook, split abstractions by capability, or inject a decoding Strategy. Do not use empty hooks mechanically when skipping decryption could create security risks.

### Mistake 4: Too Many Order-Dependent Hooks

A custom framework with dozens of methods such as `beforeValidate`, `afterValidate`, `beforeParse`, `afterParse`, `onError`, and `finally...` becomes hard to understand when subclasses override many steps. Template Method helps most when **the skeleton is genuinely stable** and only a few steps require replacement.

### Mistake 5: Using Inheritance for Every Variation Axis

Suppose there are two output formats (Text/Markdown), two languages (VI/EN), and three delivery approaches (file/email/API). Encoding every combination as a subclass produces `2 × 2 × 3 = 12` possible variants and can lead to class explosion.

With **multiple independent axes of variation**, consider composition: inject `ReportFormatter`, `Translator`, and `ReportPublisher` separately. Template Method may still orchestrate a stable outer workflow while collaborator objects provide particular variants.

## 7. Comparing Template Method with Strategy, Factory Method, and Other Techniques

| Criterion | Template Method | Strategy | Factory Method |
|---|---|---|---|
| Purpose | Preserve **an algorithm skeleton** while subclasses vary selected steps | Replace **a complete algorithm/behavior** using a collaborator object | Let subclasses choose **the class to instantiate** |
| Primary mechanism | **Inheritance + dynamic dispatch** of overridden steps | **Composition + delegation** through an interface | **Inheritance + overriding** a creation method |
| Variation point | Steps inside the superclass workflow | Strategy implementation supplied to Context | Method that creates a Product |
| Changing variants at runtime | Can select a **different subclass object**, but cannot dynamically alter the process structure within one object | Usually easy to select/swap Strategy through DI or parameters | Select a Creator subclass or use a factory supplied by the Creator |
| Benefit | Avoid duplicated workflow steps while maintaining order | Decouple algorithms and flexibly choose behaviors | Isolate product creation from business processing |
| Risk | Subclass coupling to superclass; excessive hooks | Too many small Strategies, plus selection mechanisms | Too many Creator subclasses solely to choose product types |

**Recognize the patterns through examples:**

- `SalesReportTemplate.generate()` fixes `header → rows → summary → footer`: **Template Method**.
- `PricingService` receives `PricingStrategy` and calls `calculate(...)`: **Strategy**.
- `DocumentCreator` calls `createDocument()`, overridden by subclasses to create `PdfDocument` or `HtmlDocument`: **Factory Method**.

A Template Method **may invoke a Factory Method** at a step, such as document export calling `createRenderer()`; it may also accept a Strategy for part of its calculations. Patterns are composable tools, not mutually exclusive categories.

### Template Method or Strategy for a Given Problem?

Ask:

1. Is there a **mandatory step sequence** with many shared steps and only a few differences? → Consider **Template Method**.
2. Are there multiple **complete algorithms** to interchange, especially at runtime or per request? → **Strategy** is usually more flexible.
3. Are there several independent dimensions (format, language, output)? → Prefer **composition** or combine Strategy with a common workflow.
4. Can subclasses violate processing order or the contract? → Limit extension points, specify preconditions/postconditions, and test every subclass.

Template Method inheritance tightly couples subclasses to the superclass. Changing step order or hook semantics may affect many subclasses; Strategy instead requires a clear interface and object-selection/creation mechanism.

## 8. How Template Method Differs from an Ordinary Interface

An interface only declares operations:

~~~java
interface Exporter {
    String export(List<Sale> sales);
}
~~~

If each implementation of `Exporter` independently decides the entire process, there is no **shared algorithm skeleton** in a superclass. That is interface-based polymorphism but **does not suffice** to identify Template Method.

An `abstract class` containing a `final generate()` that invokes `protected abstract` steps/hooks is characteristic. Java interfaces can use `default` methods, but have different extension/state mechanisms from abstract classes; examine **who actually owns the skeleton**, not merely the keywords.

## 9. Testing the Actual Properties of Template Method

Production tests should verify more than the final result:

- **Step order** is preserved.
- **Shared steps** execute for every subclass.
- Subclasses produce correctly formatted results under the contract.
- The default hook works when a subclass does not override it.
- Boundary data (empty list, null values, invalid amounts) is handled correctly.

The following tests use JUnit Jupiter 5; place `TemplateMethodDemo.java` under the main source set and `SalesReportTemplateTest.java` under the test source set in the same package, with a `junit-jupiter` dependency and suitable test runner.

### 9.1. Test Data, Summaries, and Hooks

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class SalesReportTemplateTest {
    @Test
    void textAndMarkdownUseSameTotal() {
        List<Sale> sales = List.of(
                new Sale("S-01", new BigDecimal("120.00")),
                new Sale("S-02", new BigDecimal("30.50"))
        );

        String text = new TextSalesReport().generate(sales);
        String markdown = new MarkdownSalesReport().generate(sales);

        assertTrue(text.contains(
                "Tổng 2 giao dịch: 150.50 VND"));
        assertTrue(markdown.contains(
                "| **Tổng (2)** | **150.50** |"));

        // Hook mặc định không thêm chú thích; Markdown có override.
        assertFalse(text.contains("_Tự động tạo báo cáo._"));
        assertTrue(markdown.endsWith(
                "_Tự động tạo báo cáo._\n"));
    }

    @Test
    void emptyListStillGetsASummary() {
        String result = new TextSalesReport()
                .generate(List.of());

        assertTrue(result.contains(
                "Tổng 0 giao dịch: 0.00 VND"));
    }

    @Test
    void invalidSalesAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new Sale("BAD|ID", new BigDecimal("10.00")));
        assertThrows(IllegalArgumentException.class,
                () -> new Sale("S-01", new BigDecimal("-1.00")));
        assertThrows(IllegalArgumentException.class,
                () -> new Sale("S-01", new BigDecimal("1.005")));
        assertThrows(NullPointerException.class,
                () -> new TextSalesReport().generate(null));
    }
}
~~~

### 9.2. Test Step Order with a Subclass That Records Calls

This test catches accidental reordering when someone later changes the template:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SalesReportOrderTest {
    static final class TracingReport extends SalesReportTemplate {
        final List<String> calls = new ArrayList<>();

        @Override
        protected String header() {
            calls.add("header");
            return "";
        }

        @Override
        protected String row(Sale sale) {
            calls.add("row:" + sale.code());
            return "";
        }

        @Override
        protected String summary(int count, BigDecimal total) {
            calls.add("summary:" + count);
            return "";
        }

        @Override
        protected String footer() {
            calls.add("footer");
            return "";
        }
    }

    @Test
    void templateControlsTheStepOrder() {
        TracingReport report = new TracingReport();

        report.generate(List.of(
                new Sale("S-01", new BigDecimal("20.00")),
                new Sale("S-02", new BigDecimal("15.00"))
        ));

        assertEquals(List.of(
                "header",
                "row:S-01",
                "row:S-02",
                "summary:2",
                "footer"
        ), report.calls);
    }
}
~~~

The ordering test uses only one tracing subclass. When variants proliferate, shared contract tests should cover all product subclasses too. If a hook performs real side effects (database writes, emails), inject fake dependencies to avoid unwanted effects in unit tests.

## 10. Using Template Method in Real Systems

Examples with relatively stable algorithm skeletons:

| Use case | Shared steps | Customized steps |
|---|---|---|
| ETL data import | Validate → read → transform → persist → summarize | Parse CSV/XML; normalize each record type |
| Report generation | Fetch data → aggregate → present → export | Header, row format, footer |
| Batch jobs | Initialize → process each item → update state → finish | Per-item processing, pre/post-batch hooks |
| Document processing | Check permission → read content → transform → write | Transformation/renderer implementation |
| Base test workflows | Shared setup → run scenario → assert invariants → clean up | Fixture data and scenario-specific steps |

For **ETL**, clarify that a template fixing step order **does not guarantee atomic transactions**. If a failure occurs midway through storing records, partial writes may remain; transactions, rollbacks, or idempotency must be designed according to requirements. Do not attribute framework transaction capabilities to the pattern.

### Algorithm-Skeleton Design Checklist

1. Write down **step names and order** before defining an abstract class. Put only truly invariant parts in the template.
2. Document **each extension-point contract**: inputs, outputs, errors, and permitted side effects.
3. Mark the template method `final` if subclasses must not alter the skeleton.
4. Use `protected abstract` for required steps and hooks with safe defaults for optional steps.
5. Keep validation, state protection, and shared rules in the superclass.
6. Avoid overridable calls in constructors, and do not give subclasses unrestricted access to mutable data.
7. Test **call order, shared steps, results, and variants**, including boundaries.
8. If variants grow along multiple independent axes, reconsider inheritance and move some variation into Strategy/composition.

## 11. Exercise: Product Import File Workflow

A system accepts partner product files in two illustrative formats: `CSV-SIMPLE` and `PIPE-SIMPLE`. Every line contains a product ID and quantity, but fields are separated differently.

Design the following:

~~~java
abstract class ProductImportTemplate {
    public final int importText(String raw) {
        // 1. validate raw
        // 2. parseRecords(raw) - abstract
        // 3. validate từng Product
        // 4. persistAll(records) - bước chung
        // 5. afterImport(count) - hook tùy chọn
        // 6. return count
        throw new UnsupportedOperationException("Exercise");
    }

    protected abstract List<Product> parseRecords(String raw);

    protected void afterImport(int count) {
        // mặc định không làm gì
    }
}
~~~

This is only an **exercise skeleton**, not a complete implementation; learners must define `Product`, `persistAll`, and correct error handling.

Exercise requirements:

- Implement two subclasses, `CsvProductImport` and `PipeProductImport`.
- The superclass checks that quantity is greater than 0 before persisting.
- Subclasses must not override `importText` to bypass validation.
- Write tests confirming that parsing/validation failures occur **before the persistence step is called**.
- If the entire file must either be committed or rolled back, specify where transactions begin/end in your design.
- Discuss when introducing a `RecordParser` interface and using Strategy would be clearer than format-based subclasses.

### Self-Check Questions

1. Which method in the report example is the **Template Method**? Why is it `final`?
2. Is `header()` a primitive operation or hook? What is `footer()`?
3. If Text and Markdown need **different formulas for revenue totals**, is changing only formatting enough? Which abstraction would need to change?
4. Why can invoking an overridable method from an abstract-class constructor cause a `NullPointerException`?
5. Should you use Strategy or create a Template Method subclass per HTTP request to switch pricing algorithms? Why?
6. Does an abstract class containing shared validation automatically qualify as Template Method without a method orchestrating an algorithm skeleton?

**Remember:** Template Method gives **the superclass control over a stable workflow**, while subclasses only **implement approved variation points**. Clear boundaries between fixed operations, abstract steps, and hooks provide its value; an `abstract class` alone does not constitute Template Method.
