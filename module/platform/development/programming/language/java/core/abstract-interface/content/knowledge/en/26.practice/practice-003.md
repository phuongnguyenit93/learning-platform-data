# Implementing Template Method for a Data Import Workflow

Template Method is a behavioral design pattern in which a superclass defines the **fixed skeleton of an algorithm**, while subclasses customize specific steps. For a data import workflow, the superclass can determine the order of checking the source, reading data, parsing each line, validating records, persisting results, and reporting completion. Each format, such as CSV or TSV, only needs to provide the appropriate way to parse lines and persist data.

This pattern is useful when multiple data import workflows have the same steps and order, but differ in a few details. It prevents each class from rewriting the entire workflow on its own and accidentally omitting an important step.

## 1. Template Method Structure in the Data Import Problem

In this example, `DataImporter` is the abstract superclass. The `importFile()` method is the **Template Method** and is declared `final`, so subclasses cannot change the sequence of steps.

The workflow is kept consistent as follows:

1. Check whether the source path points to a regular file.
2. Read lines from the file using UTF-8.
3. Skip blank lines; parse each line into a record.
4. Validate the record's fields.
5. Invoke the data persistence step implemented by the subclass.
6. Report the number of successfully imported records.

`parseLine()` and `persist()` are abstract steps that subclasses are required to implement. `validateSource()`, `readSource()`, `validateRecord()`, and `afterImport()` are hooks with default implementations that subclasses can override when needed. Not every hook needs to be overridden.

## 2. Standalone Java 17+ Example

The example includes `CsvImporter` and `TsvImporter`. Both share the `importFile()` algorithm, but parse data by comma or tab character and implement their own persistence step. The program automatically creates temporary sample files and deletes them after running.

Save the code below to `TemplateMethodImportDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class TemplateMethodImportDemo {
    private record ImportRecord(String name, String email) {}

    private abstract static class DataImporter {
        public final void importFile(Path file) throws IOException {
            Objects.requireNonNull(file, "file");
            validateSource(file);
            System.out.println("Start import: " + file.getFileName());
            List<String> lines = readSource(file);
            List<ImportRecord> records = new ArrayList<>();
            for (int i = 0; i < lines.size(); i++) {
                String line = lines.get(i);
                if (line.isBlank()) continue;
                ImportRecord record = parseLine(line, i + 1);
                validateRecord(record, i + 1);
                records.add(record);
            }
            persist(List.copyOf(records));
            afterImport(records.size());
        }

        protected void validateSource(Path file) {
            if (!Files.isRegularFile(file)) {
                throw new IllegalArgumentException("Input file not found: " + file);
            }
        }
        protected List<String> readSource(Path file) throws IOException {
            return Files.readAllLines(file, StandardCharsets.UTF_8);
        }
        protected abstract ImportRecord parseLine(String line, int lineNumber);
        protected void validateRecord(ImportRecord record, int lineNumber) {
            if (record.name().isBlank() || !record.email().contains("@")) {
                throw new IllegalArgumentException("Invalid record at line " + lineNumber);
            }
        }
        protected abstract void persist(List<ImportRecord> records);
        protected void afterImport(int count) {
            System.out.println("Import complete: " + count + " records");
        }
    }

    private static final class CsvImporter extends DataImporter {
        @Override protected ImportRecord parseLine(String line, int lineNumber) {
            String[] fields = line.split(",", -1);
            if (fields.length != 2) {
                throw new IllegalArgumentException("Expected 2 CSV fields at line " + lineNumber);
            }
            return new ImportRecord(fields[0].trim(), fields[1].trim());
        }
        @Override protected void persist(List<ImportRecord> records) {
            System.out.println("Persisting CSV records:");
            for (ImportRecord record : records) {
                System.out.println("  " + record.name() + " -> " + record.email());
            }
        }
    }

    private static final class TsvImporter extends DataImporter {
        @Override protected ImportRecord parseLine(String line, int lineNumber) {
            String[] fields = line.split("\\t", -1);
            if (fields.length != 2) {
                throw new IllegalArgumentException("Expected 2 TSV fields at line " + lineNumber);
            }
            return new ImportRecord(fields[0].trim(), fields[1].trim());
        }
        @Override protected void persist(List<ImportRecord> records) {
            System.out.println("Persisting TSV records:");
            for (ImportRecord record : records) {
                System.out.println("  " + record.name() + " -> " + record.email());
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("template-method-import-");
        Path csv = directory.resolve("people.csv");
        Path tsv = directory.resolve("people.tsv");
        try {
            Files.write(csv, List.of(
                "Alice,alice@example.com",
                "Bob,bob@example.com"
            ), StandardCharsets.UTF_8);
            Files.write(tsv, List.of(
                "Carol\tcarol@example.com"
            ), StandardCharsets.UTF_8);
            new CsvImporter().importFile(csv);
            new TsvImporter().importFile(tsv);
        } finally {
            Files.deleteIfExists(csv);
            Files.deleteIfExists(tsv);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run in the directory containing the file:

```text
javac TemplateMethodImportDemo.java
java TemplateMethodImportDemo
```

Exact output:

```text
Start import: people.csv
Persisting CSV records:
  Alice -> alice@example.com
  Bob -> bob@example.com
Import complete: 2 records
Start import: people.tsv
Persisting TSV records:
  Carol -> carol@example.com
Import complete: 1 records
```

## 3. Why Is This Template Method?

The deciding factor is that `importFile()` orchestrates the entire algorithm and prevents subclasses from overriding it. Both importers must go through source checking, file reading, parsing, validation, persistence, and completion in the same order. Subclasses only alter the pre-designed extension points.

`parseLine()` is a required extension point because each format has its own syntax. `persist()` allows each importer to change how data is persisted; in the example, they print the records to the screen so they can be observed. In a real application, this part could write to a database or send data to a service.

`validateRecord()` has shared default logic, so both CSV and TSV must have a non-blank name and an email containing an `@` character. `afterImport()` also has a shared default. Subclasses can extend a hook if they need to add a step such as recording metrics, though they should call the superclass behavior if that behavior is still needed.

## 4. How to Apply This in Real-World Systems

- Place in the superclass the steps that are genuinely identical and the order every workflow must follow, such as source verification, reading, normalization, validation, and persistence.
- Create hooks for the parts that differ across formats, such as parsing lines for CSV, TSV, or an internal format.
- Pass configuration via constructor or parameters when the difference is only configuration data, such as a table name or mapping rules. There is no need to create a subclass for every configuration value.
- Define error handling clearly: stop everything when a line is invalid, skip invalid lines, or collect errors to report at the end. That is a business decision and should not be left to accidental behavior.
- If the persistence step requires a transaction, define transaction boundaries at the workflow level to avoid unintended partial data imports.

This example uses a simple `split()` and therefore only illustrates the design principle. It does not yet handle commas inside quoted CSV fields, column headers, encoding errors, or full email validation rules. For production CSV, you should use a dedicated CSV parsing library and add appropriate transaction, logging, and error-reporting strategies.

## 5. Template Method vs. Duplicated Code

Without this pattern, each importer might write its own separate import method. Over time, one class might forget validation, another might persist before finishing checks, and error reporting becomes inconsistent. Template Method centralizes the sequencing in one place so implementations share common rules.

However, you should not turn the superclass into a framework with too many hooks. If the workflows differ almost completely, or if steps need to be combined across many configurations, composition with strategy objects can be easier to change. Use Template Method when the overall sequence is relatively stable and only certain steps require specialization.

## 6. Common Mistakes

1. **Allowing subclasses to override the main algorithm.** If the step order is a design invariant, declare the Template Method as `final` so subclasses do not accidentally skip validation or cleanup.
2. **Putting everything into the superclass.** Keep only shared logic in the superclass; format-specific behavior belongs in hooks or the appropriate subclasses.
3. **Using hooks without defining a contract.** Clearly document when the hook runs, what data it receives, what exceptions it may throw, and whether the hook may be skipped.
4. **Inconsistent error handling.** Decide explicitly whether to stop, continue, or roll back when a record fails. This example throws an exception and halts the workflow when a line is invalid.
5. **Confusing Template Method with Strategy.** Template Method relies on inheritance and an algorithm skeleton in the superclass; Strategy encapsulates an interchangeable algorithm or policy through composition.

## 7. Design Checklist

- Does the algorithm have a stable common sequence across importers?
- Which parts must remain identical, and which parts genuinely need customization?
- Should the Template Method be `final` to preserve the order?
- Do hooks have clear names, clear contracts, and a small scope of responsibility?
- Have validation, error, transaction, and persistence rules been defined?
- Has the example tested at least one valid format and an invalid input case?

When the answers show that the workflow has a common skeleton while differing in certain steps, Template Method helps consolidate control flow in one place and keeps specialized parts at the proper extension points.
