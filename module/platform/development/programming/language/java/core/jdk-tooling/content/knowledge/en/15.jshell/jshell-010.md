# Testing APIs with JShell

**JShell** is an interactive REPL environment included with the JDK that lets you enter and run Java expressions, statements, variables, classes, and methods directly in the Terminal. It is a fast way to explore APIs, check method signatures, test input values, observe results, and reproduce small issues before putting code into a project.

When testing an API, treat JShell as a stateful workbench: declare imports or variables once, then call multiple methods on the same object. You can test normal cases, boundary values, invalid inputs, and exceptions without creating a full project.

JShell is well suited for interactive exploration. For logic that requires automated testing, repeated runs in CI, or checking many cases, convert stabilized examples into unit tests using a framework such as JUnit.

## 1. Starting JShell

JShell has been included in the JDK since Java 9. Check the version and start it:

```sh
jshell --version
jshell
```

You will see the prompt:

```text
jshell>
```

Try an expression:

```java
jshell> 2 + 3
$1 ==> 5
```

JShell automatically stores the expression result in a temporary variable named something like `$1`. The sequence number depends on session history, so you should not rely on this number in documentation or scripts.

You can choose concise feedback mode at startup:

```sh
jshell --feedback concise
```

In a running session, change the mode with:

```text
jshell> /set feedback concise
```

View help and exit:

```text
jshell> /help
jshell> /help intro
jshell> /exit
```

## 2. Workflow for Testing an API

A simple workflow:

1. Identify the class or interface to explore and its package.
2. Import the required types or refer to them by their fully qualified names.
3. Create an object with small, easy-to-control data.
4. Call a method and observe the return value or side effects.
5. Try multiple argument types to understand overloads.
6. Check boundary cases and invalid inputs.
7. Observe exceptions and the conditions that trigger them.
8. Record the verified results and convert them into unit tests if needed.

Example exploring `String`:

```java
jshell> import java.util.Locale;
jshell> String message = "  Java API  ";
jshell> message.strip()
$1 ==> "Java API"

jshell> message.toUpperCase(Locale.ROOT)
$2 ==> "  JAVA API  "

jshell> message.substring(2, 6)
$3 ==> "Java"
```

`strip()` removes whitespace from both ends, `toUpperCase()` produces an uppercase string, and `substring(begin, end)` extracts the substring starting at index `begin` and ending before index `end`. String is immutable: these methods return a new string without modifying the original `message` object.

## 3. Importing Packages and Using Fully Qualified Names

Imports let you use short class names:

```java
jshell> import java.time.LocalDate;
jshell> import java.time.format.DateTimeFormatter;
jshell> LocalDate today = LocalDate.of(2026, 11, 10);
jshell> today.plusDays(7)
$1 ==> 2026-11-17
```

Without importing, you can use the fully qualified name:

```java
jshell> java.time.LocalDate.of(2026, 11, 10)
$2 ==> 2026-11-10
```

Some basic packages are pre-imported by JShell, but you should import explicitly in longer examples so readers understand where the types come from. View current imports:

```text
jshell> /imports
```

If two packages contain classes with the same name, import the specific class or use the fully qualified name to avoid ambiguity.

## 4. Exploring Methods and Overloads

An API can have multiple methods with the same name but different parameter lists. This is method overloading. When testing an API, check the name, parameter types, return type, and applicable conditions.

Example with `String.substring`:

```java
jshell> "OpenJDK".substring(4)
$1 ==> "JDK"

jshell> "OpenJDK".substring(0, 4)
$2 ==> "Open"
```

- `substring(int beginIndex)` extracts from the start index to the end of the string.
- `substring(int beginIndex, int endIndex)` extracts from `beginIndex` up to before `endIndex`.

You can use reflection to inspect the methods declared in a class:

```java
jshell> import java.lang.reflect.Method;
jshell> import java.util.Arrays;
jshell> Arrays.stream(String.class.getDeclaredMethods()).filter(m -> m.getName().equals("substring")).map(Method::toGenericString).sorted().forEach(System.out::println);
```

The output contains signatures corresponding to `substring(int)` and `substring(int, int)`. The order of methods returned by reflection is not guaranteed; `sorted()` sorts the output text for readability.

Distinguish between:

- `getMethods()` returns public methods, including inherited ones.
- `getDeclaredMethods()` returns methods declared directly in the class, including non-public methods, but excluding inherited ones.

Reflection is useful for inspecting an API at runtime, but it does not replace Javadoc. It does not fully describe behavioral contracts, thread safety, performance, or usage conditions.

## 5. Tab Completion and Help

In JShell, press Tab to complete class names, variables, or methods, or to see suggestions at the cursor position. For example:

```java
jshell> var text = "Java";
```

Type `text.` and press Tab to view callable members. Name completion helps you explore APIs quickly, but it is not complete documentation. To understand exact parameters, return values, exceptions, and usage notes, read the Javadoc.

You can view help for JShell commands:

```text
jshell> /help /list
jshell> /help /save
```

JShell commands start with `/`; regular Java expressions, declarations, and statements do not.

## 6. Testing the Collection API

The Collection API is commonly used to test creating lists, adding elements, querying, filtering, and transforming data.

```java
jshell> import java.util.ArrayList;
jshell> import java.util.List;
jshell> var names = new ArrayList<String>();
jshell> names.add("An")
$1 ==> true

jshell> names.add("Binh")
$2 ==> true

jshell> names
names ==> [An, Binh]
```

Testing access and updates:

```java
jshell> names.get(0)
$3 ==> "An"

jshell> names.set(1, "Chi")
$4 ==> "Binh"

jshell> names
names ==> [An, Chi]
```

`set(index, value)` returns the previous element at that position. `get(index)` reads the element at a 0-based index.

Calling `names.get(10)` throws `IndexOutOfBoundsException` because the list has no element at index 10.

### 6.1. List.of and Immutability

`List.of(...)` creates an unmodifiable list:

```java
jshell> var fixedNames = List.of("An", "Binh");
jshell> fixedNames
fixedNames ==> [An, Binh]
```

If you call `fixedNames.add("Chi")`, the API throws `UnsupportedOperationException`. This list also does not accept `null` elements. When testing an API, distinguish between mutable lists like `ArrayList` and unmodifiable lists like those created by `List.of`.

## 7. Testing the Map API

Maps store key/value pairs. Use `HashMap` to test update and query operations:

```java
jshell> import java.util.HashMap;
jshell> var prices = new HashMap<String, Integer>();
jshell> prices.put("book", 120)
$1 ==> null

jshell> prices.put("pen", 15)
$2 ==> null

jshell> prices.get("book")
$3 ==> 120

jshell> prices.containsKey("pen")
$4 ==> true
```

Testing updating the same key:

```java
jshell> prices.put("book", 130)
$5 ==> 120

jshell> prices.get("book")
$6 ==> 130
```

`put` returns the previous value if the key already existed; otherwise, it returns `null`. When testing Map APIs, pay attention to the difference between a missing key and a key mapped to `null` if the Map implementation allows nulls.

Testing `getOrDefault`:

```java
jshell> prices.getOrDefault("not-found", 0)
$7 ==> 0
```

APIs such as `putIfAbsent`, `computeIfAbsent`, and `merge` can be tested in a similar way. Read each method's contract before using it with complex update logic.

## 8. Testing the Stream API

The Stream API supports processing data sequences through steps such as filtering, transforming, and aggregating:

```java
jshell> import java.util.stream.Stream;
jshell> var result = Stream.of("java", "", "jshell", "api").filter(s -> !s.isBlank()).map(String::toUpperCase).toList();
jshell> result
result ==> [JAVA, JSHELL, API]
```

- `Stream.of(...)` creates a stream from the given elements.
- `filter(...)` keeps elements matching the predicate.
- `map(...)` transforms each element.
- `toList()` collects the results into an unmodifiable list.

Testing numeric aggregation:

```java
jshell> var total = List.of(10, 20, 30).stream().mapToInt(Integer::intValue).sum();
jshell> total
total ==> 60
```

A stream can generally be consumed only once. Calling a second terminal operation on an already-used stream can throw `IllegalStateException`. When you need to rerun a pipeline, create a new stream from the data source.

## 9. Testing the Date and Time API

Classes in `java.time` are immutable and well suited for testing date and time logic without depending on the system clock.

```java
jshell> import java.time.LocalDate;
jshell> import java.time.format.DateTimeFormatter;
jshell> var start = LocalDate.of(2026, 11, 10);
jshell> start.plusDays(5)
$1 ==> 2026-11-15

jshell> start.withDayOfMonth(1)
$2 ==> 2026-11-01
```

Formatting dates:

```java
jshell> var formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu");
jshell> formatter.format(start)
$3 ==> "10/11/2026"
```

`uuuu` is generally preferred over `yyyy` when representing a proleptic year, especially in date-parsing operations. For standard UI formatting, choose the pattern according to business requirements.

Testing an invalid case:

```java
jshell> LocalDate.of(2026, 2, 30)
```

The call throws `DateTimeException` because February 2026 does not have 30 days. This is a way to check how the API validates input data.

## 10. Testing Optional

`Optional` represents a result that may or may not contain a value:

```java
jshell> import java.util.Optional;
jshell> var found = Optional.of("Java");
jshell> found.isPresent()
$1 ==> true

jshell> found.orElse("unknown")
$2 ==> "Java"
```

With an empty result:

```java
jshell> var missing = Optional.<String>empty();
jshell> missing.orElse("unknown")
$3 ==> "unknown"

jshell> missing.map(String::toUpperCase)
$4 ==> Optional.empty
```

When testing an API that returns `Optional`, test both the present branch and the empty branch. Do not call `get()` without checking its state; if the `Optional` is empty, `get()` throws `NoSuchElementException`.

## 11. Testing the Files API with Temporary Files

NIO.2 provides APIs for working with paths and files. You can use temporary files to test reading and writing without affecting existing project files.

```java
jshell> import java.nio.file.Files;
jshell> import java.nio.file.Path;
jshell> import java.io.IOException;
jshell> import java.io.UncheckedIOException;
```

Create, write, read, and delete a temporary file:

```java
jshell> try {
   ...>     Path file = Files.createTempFile("jshell-api-", ".txt");
   ...>     try {
   ...>         Files.writeString(file, "API test");
   ...>         System.out.println(Files.readString(file));
   ...>     } finally {
   ...>         Files.deleteIfExists(file);
   ...>     }
   ...> } catch (IOException e) {
   ...>     throw new UncheckedIOException(e);
   ...> }
API test
```

The example uses `Files.createTempFile`, `writeString`, `readString`, and `deleteIfExists`. The `finally` block ensures an attempt is made to delete the file even if reading or writing fails. The I/O exception is wrapped in `UncheckedIOException` so the error is displayed in the test session.

When testing APIs that work with resources, pay attention to resource lifecycles, access permissions, and cleaning up temporary data. For streams or readers/writers, use try-with-resources to close resources properly.

## 12. Testing HTTP Client Without Sending Requests

Java 11 and later include an HTTP Client in the `java.net.http` module. You can test how requests are constructed first without making a network connection.

```java
jshell> import java.net.URI;
jshell> import java.net.http.HttpRequest;
jshell> var request = HttpRequest.newBuilder(URI.create("https://api.example.test/items")).header("Accept", "application/json").GET().build();
jshell> request.method()
$1 ==> "GET"

jshell> request.uri()
$2 ==> https://api.example.test/items
```

This example checks how to construct a URI, add headers, choose the HTTP method, and inspect the values stored in the request. The domain `api.example.test` is an illustrative address; the code only builds the request object and does not send data over the network. A request is only sent when calling APIs such as `HttpClient.send(...)` or `sendAsync(...)`.

When you need to send real requests, use authorized endpoints, configure timeouts, and handle status codes and network errors. Never send secrets or personal data to untrusted test endpoints.

## 13. Checking Exceptions and Boundary Conditions

An API is not understood through successful results alone. Proactively test inputs that can fail.

Example with `Integer.parseInt`:

```java
jshell> Integer.parseInt("123")
$1 ==> 123

jshell> try {
   ...>     Integer.parseInt("12x");
   ...> } catch (NumberFormatException e) {
   ...>     System.out.println(e.getClass().getSimpleName());
   ...> }
NumberFormatException
```

A testing checklist:

| Test Category | Examples | What to Observe |
|---|---|---|
| Normal values | Valid strings, positive numbers | Result matches the contract |
| Empty values | Empty string, empty collection | Whether the API returns an empty result or throws an error |
| Boundary values | 0, negative numbers, last index | Whether boundary rules match expectations |
| Null | Passing `null` when allowed or rejected | NPE or documented behavior |
| Invalid type/format | Unparseable string | Exception type and when it is thrown |
| Side effects | Adding/removing elements, writing files | State before and after the call |
| Immutability | Calling mutators on immutable collections | Whether the API throws `UnsupportedOperationException` |
| Resources | Closing streams, deleting temp files | Whether resources are released |

Do not rely on a single successful call to conclude an API works for all cases. Cross-check results with the Javadoc, especially when a method can throw checked exceptions, mutate state, or depend on the environment.

## 14. Creating a Helper for Quick Result Checks

You can define a check method in JShell to reduce repetitive typing:

```java
jshell> import java.util.Objects;
jshell> void checkEquals(Object expected, Object actual) {
   ...>     if (!Objects.equals(expected, actual)) {
   ...>         throw new AssertionError("Expected " + expected + " but got " + actual);
   ...>     }
   ...> }
```

Test the API:

```java
jshell> checkEquals("JAVA", "java".toUpperCase(Locale.ROOT));
```

If the result matches, the method prints nothing and the session continues normally. If it differs, it throws `AssertionError` with the expected and actual values.

This helper is only a manual exploration utility. It does not provide test organization, setup/teardown, multi-case reporting, or automated execution like JUnit. For formal testing, move verified cases into separate tests.

## 15. Testing APIs from Third-Party Libraries

If the API resides in an external JAR, pass the JAR to JShell at startup:

```sh
jshell --class-path "lib/example-library.jar"
```

Then import classes from the library and test calling methods:

```java
jshell> import com.example.library.Client;
jshell> var client = new Client();
```

The package, class, and constructor names above are illustrative; replace them with the actual API of the library you are using.

If the library has other dependencies, include all required dependencies on the classpath as well. Path separator characters for multiple classpath entries:

| Operating System | Separator Character |
|---|---|
| Windows | `;` |
| Linux/macOS | `:` |

Example on Linux/macOS:

```sh
jshell --class-path "lib/client.jar:lib/common.jar"
```

Example on Windows PowerShell:

```powershell
jshell --class-path "lib/client.jar;lib/common.jar"
```

For modular libraries, you may need the module path and appropriate module options instead of only the classpath. See `jshell --help` for the options supported by your JDK.

When testing third-party libraries, check the JAR version, transitive dependencies, minimum Java requirement, and license. JShell only helps invoke the API; it does not resolve dependencies or guarantee library version compatibility.

## 16. Managing Snippets in a Session

Each declaration or statement is managed by JShell as a snippet. Useful commands:

| Command | Purpose |
|---|---|
| `/list` | List snippets in session history |
| `/list -all` | Show all snippets, including dropped ones |
| `/vars` | List declared variables |
| `/methods` | List active methods |
| `/types` | List declared types |
| `/imports` | List current imports |
| `/drop <id>` | Drop a snippet by ID |
| `/reset` | Reset JShell state |
| `/save <file>` | Save snippets to a file |
| `/open <file>` | Load and execute snippets from a file |
| `/exit` | Exit JShell |

Example:

```text
jshell> /methods
jshell> /vars
jshell> /list
```

If you need to remove a declaration, find its ID with `/list` and run `/drop <id>`, replacing `<id>` with the actual ID. `/reset` clears session state, including declared variables, methods, classes, and imports; use it when you want to start fresh.

Save tested snippets and reopen them in a later session:

```text
jshell> /save api-experiments.jsh
jshell> /open api-experiments.jsh
```

A saved file can contain both expressions and declarations. Before sharing it, review the file to ensure it contains no sensitive data or unintended commands.

## 17. From API Exploration to Unit Tests

JShell helps you learn quickly, but exploration results should be converted into repeatable tests if the API is an important part of your application.

For example, after verifying that `String.strip()` removes leading and trailing whitespace, you can write a unit test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class StringApiTest {
    @Test
    void stripRemovesLeadingAndTrailingWhitespace() {
        assertEquals("Java", "  Java  ".strip());
    }
}
```

This example uses JUnit Jupiter; you need to configure the JUnit dependency in your build tool to run it. JShell does not provide a test framework or runner for the `@Test` annotation.

Convert the following cases into automated tests: behavior that must be guaranteed across builds; important boundary values and exceptions; compatibility with a specific library version; behavior that could change when upgrading the JDK or dependencies; and logic involving data integrity, security, time, or concurrency.

## 18. Common Errors When Testing APIs

| Symptom | Common Cause | How to Fix |
|---|---|---|
| `cannot find symbol` | Class not imported, wrong method name, or missing dependency | Check package, imports, and classpath |
| `package ... does not exist` | JAR missing from classpath or wrong package name | Add the right JAR and inspect library contents |
| `method ... cannot be applied to given types` | Argument types or count do not match | Check the method signature and pass the right argument types |
| Ambiguous overload call | Multiple overloads match equally well | Declare explicit variable types or cast intentionally |
| `NullPointerException` | API rejects null or code uses a null value | Check the contract and validate inputs |
| `IndexOutOfBoundsException` | Index out of collection/string bounds | Check size and 0-based indexing rules |
| `UnsupportedOperationException` | Calling a mutating operation on an unmodifiable collection | Use a mutable implementation if modification is needed |
| `NoSuchMethodError` | Runtime loads a different library version than compile time | Check the dependency tree and actual classpath |
| JShell cannot find classes from a JAR | Missing JAR or transitive dependency | Add dependencies to classpath/module path |
| Different results between runs | Different data, locale, timezone, or session state | Use fixed inputs and set environment configuration explicitly |
| Snippet fails after changing a declaration | Snippet depends on a declaration that was replaced or dropped | Use `/list`, `/methods`, and redeclare needed dependencies |

When encountering an error, separate snippet compilation errors from runtime exceptions. Compilation errors usually involve class names, imports, parameter types, or method signatures. Runtime exceptions occur after the call has compiled and stem from data, state, or execution conditions.

## 19. Principles for Safe and Repeatable API Testing

- Use mock or small data, never sensitive production data.
- Start with side-effect-free APIs before testing writes, deletes, or sending requests.
- For network APIs, send requests only to authorized endpoints and know what data is transmitted.
- For files/databases, use dedicated test resources and clean up afterward.
- Set timeouts when testing operations that may wait on network or I/O.
- Check exceptions and close resources properly.
- Record the JDK, library version, classpath, and inputs when results depend on the environment.
- Do not treat a single REPL result as sufficient proof of performance, thread safety, or stability.
- Convert important checks into unit/integration tests in your project.

## 20. Checklist

- [ ] Started JShell with a compatible JDK.
- [ ] Imported the right packages or used fully qualified names.
- [ ] Created objects with controllable test data.
- [ ] Called methods and identified return types.
- [ ] Checked overloads and signatures when needed.
- [ ] Tested normal, empty, boundary, and invalid cases.
- [ ] Observed exceptions and side effects.
- [ ] Checked mutability and resource lifecycles.
- [ ] Added dependencies to the right classpath/module path when using external libraries.
- [ ] Used `/list`, `/vars`, `/methods`, or `/imports` to inspect session state.
- [ ] Saved snippets if reuse is needed.
- [ ] Converted critical behavior into automated unit tests.

JShell turns reading API documentation into a hands-on testing process: create data, call methods, observe results, and check errors right at the prompt. By combining interactive exploration with Javadoc and unit tests, you can understand API contracts faster and bring verified results into your Java applications in a controlled way.