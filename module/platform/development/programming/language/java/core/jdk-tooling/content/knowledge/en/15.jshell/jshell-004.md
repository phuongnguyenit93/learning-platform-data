# Declaring Variables in JShell

## 1. What Is a Variable in JShell?

JShell is a REPL (Read-Eval-Print Loop) tool included with the JDK that lets you enter and evaluate Java code snippets directly within a session. Each piece of code entered is called a **snippet**. A snippet can be a variable declaration, method, class, statement, import, or expression.

**Declaring a variable in JShell** creates a typed name to store a value and reuse it in subsequent snippets. Unlike a standard Java program that typically starts from a §main§ method, JShell lets you declare variables directly at the §jshell>§ prompt.

Example:

§§§text
jshell> int quantity = 3
quantity ==> 3

jshell> quantity + 2
$2 ==> 5
§§§

After the first declaration, the variable §quantity§ exists in the JShell session. Subsequent snippets can use that variable without redeclaring it. The expression §quantity + 2§ creates a scratch variable managed by JShell to hold the result; it is not a named variable declared by the developer.

A variable declaration is a persistent snippet: it remains active in the session until it is replaced, dropped, or the session is reset. JShell is well suited for testing data types, checking expressions, trying out APIs, observing values after each assignment, and quickly prototyping without building a complete class.

## 2. Starting JShell

JShell is bundled with the JDK. Open Terminal, Command Prompt, or PowerShell and run:

§§§bash
jshell
§§§

Check the tool version:

§§§bash
jshell --version
§§§

If the system reports that the §jshell§ command is not recognized, check whether the JDK is installed and the JDK's §bin§ directory is in your PATH. JShell is not included in some minimal runtime distributions that contain only the JRE.

You can enable verbose feedback mode to observe snippets in detail:

§§§bash
jshell -v
§§§

In verbose mode, JShell notifies you when a variable is created, replaced, or updated. Other feedback modes may display less information; actual output may also vary slightly across JDK versions.

To end the session:

§§§text
jshell> /exit
§§§

## 3. Variable Declaration Syntax

Standard Java variable declaration syntax is used in JShell:

§§§java
type variableName = initialValue;
§§§

Where:

- §type§ is the data type of the variable.
- §variableName§ is a valid variable name following Java identifier rules.
- §initialValue§ is an initial value compatible with the declared type.

Example:

§§§java
int age = 25;
double price = 19.95;
boolean isActive = true;
String language = "Java";
§§§

You can enter each declaration at the JShell prompt:

§§§text
jshell> int age = 25
age ==> 25

jshell> double price = 19.95
price ==> 19.95

jshell> boolean isActive = true
isActive ==> true

jshell> String language = "Java"
language ==> "Java"
§§§

JShell usually appends a semicolon automatically to a complete snippet if you omit §;§. However, it is good practice to keep semicolons while practicing so you stay familiar with Java source code syntax and can easily copy snippets into a §.java§ file.

## 4. Declaring Variables by Data Type

JShell supports Java data types just like a regular Java program.

### 4.1. Primitive Type Variables

The primitive types include:

| Type | Example | Purpose |
|---|---|---|
| §byte§ | §byte level = 2;§ | Small integer, 8-bit |
| §short§ | §short year = 2026;§ | Integer, 16-bit |
| §int§ | §int quantity = 120;§ | Integer, 32-bit |
| §long§ | §long population = 8_000_000_000L;§ | Integer, 64-bit |
| §float§ | §float ratio = 0.75f;§ | Floating-point number, 32-bit |
| §double§ | §double average = 8.25;§ | Floating-point number, 64-bit |
| §char§ | §char grade = 'A';§ | A single UTF-16 code unit character |
| §boolean§ | §boolean enabled = false;§ | True or false value |

Example:

§§§java
int attempts = 3;
long distance = 15000000000L;
float temperature = 36.5f;
double taxRate = 0.08;
char initial = 'J';
boolean completed = false;
§§§

Literal suffix notes:

- Integer literals of type §long§ typically use the §L§ suffix, for example §100L§.
- Floating-point literals of type §float§ require the §f§ or §F§ suffix, for example §2.5f§.
- A floating-point literal without a suffix defaults to type §double§.

### 4.2. Reference Type Variables

Reference variables store references to objects or arrays. Some common types:

§§§java
String userName = "Lan";
Integer score = 95;
int[] marks = {8, 9, 10};
§§§

You can declare collection types after importing them:

§§§java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
§§§

JShell lets you enter imports and variable declarations as separate snippets. Imports are retained in the session for subsequent snippets to use.

### 4.3. Declaring Arrays

You can declare arrays using standard Java syntax:

§§§java
int[] scores = {80, 90, 95};
String[] tools = new String[] {"javac", "java", "jshell"};
§§§

Access elements using 0-based indexing:

§§§text
jshell> scores[0]
$4 ==> 80

jshell> scores.length
$5 ==> 3
§§§

Scratch variable IDs such as §$4§ and §$5§ depend on the snippets previously entered in the session.

## 5. Declaring Variables With or Without an Initial Value

It is good practice to initialize a variable when declaring it so its state is explicit:

§§§java
int retryCount = 0;
String status = "READY";
§§§

JShell also accepts variable declarations without an initializer:

§§§text
jshell> int pending;
pending ==> 0

jshell> String note;
note ==> null
§§§

In JShell, variables declared at the top level of a session have default initialization behavior similar to Java fields: numeric types default to §0§, booleans to §false§, characters to §'\u0000'§, and reference variables to §null§.

This differs from local variables inside a regular Java method. Inside a method, a local variable must be definitely assigned before it is read; reading it before assignment causes a compiler error. You should not rely on JShell's default values when writing method source code.

Example of explicit initialization:

§§§java
int pending = 0;
String note = "";
§§§

When a reference variable holds §null§, calling a method or accessing a field on it can throw a §NullPointerException§.

## 6. Using var for Type Inference

Starting in Java 10, you can use the §var§ keyword so the compiler infers the variable type from its initializer expression. JDK 17 and later support this declaration style in JShell.

Example:

§§§java
var count = 10;
var title = "Java Core";
var average = 8.5;
var names = java.util.List.of("Lan", "Minh");
§§§

The inferred types are:

- §count§: §int§.
- §title§: §String§.
- §average§: §double§.
- §names§: §List<String>§.

You can inspect types and values with the §/vars§ command.

§var§ does not mean a variable can change to any data type. The type inferred at declaration time is still the variable's static type. For example, §var count = 10;§ creates an §int§ variable; you cannot assign a string to it.

### 6.1. Cases Where var Cannot Be Used

§var§ requires an initializer expression with enough information to infer the type. The following declarations are invalid:

§§§java
var value;
var empty = null;
var first = 1, second = 2;
§§§

Reasons:

- Without an initializer, the compiler cannot determine the type to infer.
- The §null§ literal does not provide a specific type.
- A §var§ declaration cannot contain multiple variable declarators.

When you need to represent a null value, declare an explicit reference type:

§§§java
String empty = null;
§§§

For multiple variables, declare them separately so each type and purpose is clear:

§§§java
var first = 1;
var second = 2;
§§§

Avoid using §var§ when the inferred type makes the code harder to read. Use an explicit type when the data type is important information for the reader.

## 7. Naming Variables in JShell

Variable names follow Java's identifier rules:

- Can contain letters, digits, underscores, and the §$§ character.
- Cannot start with a digit.
- Cannot match a Java keyword.
- Are case-sensitive.
- Should use names that convey the meaning of the data.

Valid examples:

§§§java
int itemCount = 12;
double unitPrice = 4.5;
String customerName = "An";
boolean isReady = true;
§§§

Invalid examples:

§§§java
int 2items = 2;
int class = 1;
§§§

The standard naming convention for Java variables is §lowerCamelCase§, such as §totalPrice§, §maxRetries§, and §currentUser§.

JShell can generate scratch names such as §$1§ and §$2§ for the results of expressions not assigned to a named variable. You should not use these scratch names as business variable names in a program.

## 8. Using and Updating Declared Variables

Once declared, a variable can be used in expressions, statements, or subsequent declarations.

Example:

§§§text
jshell> int unitPrice = 12
unitPrice ==> 12

jshell> int quantity = 4
quantity ==> 4

jshell> int total = unitPrice * quantity
total ==> 48

jshell> total
total ==> 48
§§§

Reassigning values to variables:

§§§java
quantity = 5;
total = unitPrice * quantity;
§§§

Variables are statically typed, so the assigned value must be compatible with the declared type. Example:

§§§java
int quantity = 5;
quantity = 7;       // Valid
quantity = 2.5;     // Error: double cannot be assigned directly to int
§§§

If you need to convert from §double§ to §int§, choose an intentional conversion. Casting with §(int) 2.5§ truncates the fractional part and yields §2§; it does not round.

You can use update operators:

§§§java
quantity++;
quantity += 2;
quantity *= 3;
§§§

Each snippet is evaluated as soon as it is completed, so updated values are immediately available in the next snippet.

## 9. Using final to Declare Non-Reassignable Variables

The §final§ keyword prevents a variable from being reassigned after initialization:

§§§java
final int MAX_RETRIES = 3;
final String APPLICATION_NAME = "Inventory";
§§§

The following assignments are invalid:

§§§java
MAX_RETRIES = 5;
APPLICATION_NAME = "Billing";
§§§

For reference variables, §final§ locks reassignment of the reference itself; it does not make the referenced object immutable.

Example:

§§§java
final StringBuilder message = new StringBuilder("Hello");
message.append(" Java");       // Valid: modifies the object
// message = new StringBuilder("Other"); // Invalid: reassigning a final variable
§§§

Use §final§ for values that are not meant to change during an exploratory session, such as limits, configuration values, or calculation constants.

## 10. Primitive Variables vs. Reference Variables

When declaring variables, it is important to understand the difference between primitive types and reference types.

| Characteristic | Primitive | Reference |
|---|---|---|
| Examples | §int§, §double§, §boolean§ | §String§, array, object |
| Stored value | Primitive value | Reference to an object or §null§ |
| Comparison with §==§ | Compares values | Compares identity/reference |
| Can be §null§ | No | Yes |
| Declaration example | §int score = 90;§ | §String name = "An";§ |

Example:

§§§java
int first = 10;
int second = 10;
first == second;                 // true

String a = new String("Java");
String b = new String("Java");
a == b;                          // false
a.equals(b);                     // true
§§§

Two separately created §String§ objects have equal content, but they are not necessarily the same object. Use §equals§ to compare the contents of objects that define equality semantics.

## 11. Multi-Line Variable Declarations and Using Variables in Expressions

JShell supports entering multi-line snippets. The continuation prompt §...>§ appears when a declaration or block is not yet complete.

Example of declaring a variable from a multi-line expression:

§§§text
jshell> int finalPrice =
   ...>     100
   ...>     + 20;
finalPrice ==> 120
§§§

You can declare a variable and then use it in a lambda or stream:

§§§java
var numbers = java.util.List.of(2, 4, 6, 8);
var doubled = numbers.stream()
                     .map(n -> n * 2)
                     .toList();
§§§

Then inspect the result:

§§§text
jshell> doubled
doubled ==> [4, 8, 12, 16]
§§§

The §Stream.toList()§ method was introduced in Java 16, so this example runs on JDK 17 and later.

## 12. Managing Variables with JShell Commands

JShell provides commands starting with §/§. These are session-control commands, distinct from Java snippets.

| Command | Purpose |
|---|---|
| §/vars§ | List active variables with their types and values |
| §/vars name§ | View information for the specified variable |
| §/list§ | List entered snippets and their IDs |
| §/list -all§ | Show all snippets, including replaced, dropped, or erroneous ones |
| §/drop name§ | Remove the named variable snippet from the active state |
| §/save file.jsh§ | Save currently active snippets to a file |
| §/open file.jsh§ | Load and execute snippets from a file |
| §/history§ | View command and snippet history |
| §/reset§ | Clear snippet state and restart the session |
| §/exit§ | Exit JShell |

Example:

§§§text
jshell> int score = 90
score ==> 90

jshell> String student = "An"
student ==> "An"

jshell> /vars
|    int score = 90
|    String student = "An"

jshell> /list
   1 : int score = 90;
   2 : String student = "An";
§§§

Actual snippet IDs in output depend on session history. Startup snippets may have their own IDs and do not necessarily appear in the default §/list§ output.

To remove an experimental variable:

§§§text
jshell> /drop score
§§§

After dropping it, §score§ is no longer an active declaration. Snippets that depend on that variable may become invalid until fixed or redeclared.

## 13. Scratch Variables vs. User-Declared Variables

When you enter an expression that produces a value without assigning it to a variable name, JShell automatically creates a scratch variable to hold the result.

Example:

§§§text
jshell> 10 * 5
$1 ==> 50

jshell> "Java".toUpperCase()
$2 ==> "JAVA"
§§§

Scratch names take the form §$§ followed by an ID. The ID changes depending on the snippets entered in the session.

Comparison:

§§§java
int total = 10 * 5;   // Named variable declared by the user
10 * 5;               // Expression; JShell creates a scratch variable
§§§

Use a named variable when you need to reference the data in later steps. Scratch variables are useful for quickly inspecting the result of a calculation or method call.

The §/vars§ command can also display active scratch variables. Avoid relying on specific scratch variable ID numbers in documentation or scripts, because IDs can change when snippet order changes.

## 14. Redeclaring Variables in the Same JShell Session

A distinctive feature of JShell is that you can enter a new definition for an already declared variable. The new definition replaces the old snippet with the same name.

Example:

§§§text
jshell> int level = 3
level ==> 3

jshell> String level = "Advanced"
level ==> "Advanced"
§§§

On the second entry, JShell replaces the §int§ variable §level§ with a §String§ variable §level§. In verbose mode, JShell reports that the variable was replaced and the previous snippet was overwritten.

This is helpful when experimenting with different data types or quickly fixing a declaration. However, if other methods or variables depend on the old type, they may no longer compile or execute. Read JShell's update messages and recheck dependent snippets.

This behavior is specific to the REPL environment. Inside a normal Java block or method, you cannot declare two variables with the same name in the same scope as shown above.

If you want to remove the old definition before trying again, use §/drop level§ and then declare the new variable. When you need a completely clean slate, use §/reset§.

## 15. Saving and Reloading Variable Declarations

Variables and object state in a JShell session exist within the current session. When you exit, runtime state is not automatically saved like a running application.

You can save snippets to replay them later:

§§§text
jshell> int basePrice = 100
basePrice ==> 100

jshell> int tax = 10
tax ==> 10

jshell> int finalPrice = basePrice + tax
finalPrice ==> 110

jshell> /save pricing.jsh
§§§

In another session, reload the snippets:

§§§text
jshell> /open pricing.jsh
§§§

The §/save§ command saves snippet source code; §/open§ reads and re-evaluates the snippets in the file. It does not save a snapshot of the heap, live objects, or arbitrary runtime state. If snippets depend on external files, libraries, or configuration, the new environment still needs those resources available.

## 16. Common Errors When Declaring Variables

| Symptom | Cause | Resolution |
|---|---|---|
| §cannot find symbol§ | Using a variable before declaring it or misspelling its name | Declare the variable first and check spelling |
| §incompatible types§ | Assigned value is not compatible with the variable's type | Choose an appropriate type or perform an intentional conversion |
| §variable might not have been initialized§ in Java code | Reading a local variable before assigning it | Assign a value before using it |
| §cannot infer type for local variable§ | Using §var§ without an initializer or with an initializer that lacks type information | Declare an explicit type or use an initializer with a definite type |
| §null§ causes §NullPointerException§ | Reference variable has not been assigned an object | Check for null or initialize the object before calling methods |
| Cannot reassign variable | Variable is declared §final§ | Use another variable or remove §final§ if reassignment is needed |
| Existing method fails after changing a variable's type | Dependent snippet is affected when the variable is replaced | Review update messages and fix or redeclare dependent snippets |
| Variables missing after opening a new JShell session | Previous session state ended | Save snippets with §/save§ and reload with §/open§ |
| Unfamiliar names §$1§, §$2§ | Scratch variables created by JShell for expressions | Use §/vars§ or declare a named variable if needed longer-term |

Another common mistake is confusing JShell commands with Java code. For example, §/vars§ is a JShell control command; do not put it in a §.java§ file or inside a method.

## 17. Practice Exercise: Declaring and Updating Invoice Variables

Open JShell and enter the following snippets in order:

Step 1 — Declare product data:

§§§java
String productName = "Keyboard";
int unitPrice = 450000;
int quantity = 2;
§§§

Step 2 — Calculate subtotal and tax:

§§§java
long subtotal = (long) unitPrice * quantity;
double taxRate = 0.08;
double taxAmount = subtotal * taxRate;
double total = subtotal + taxAmount;
§§§

Step 3 — Print the results:

§§§java
System.out.println("Product: " + productName);
System.out.println("Subtotal: " + subtotal);
System.out.println("Tax: " + taxAmount);
System.out.println("Total: " + total);
§§§

Stdout of the print statements:

§§§text
Product: Keyboard
Subtotal: 900000
Tax: 72000.0
Total: 972000.0
§§§

Step 4 — Change quantity and recalculate:

§§§java
quantity = 3;
subtotal = (long) unitPrice * quantity;
taxAmount = subtotal * taxRate;
total = subtotal + taxAmount;
§§§

Verify:

§§§text
jshell> total
total ==> 1458000.0
§§§

Step 5 — Inspect variable state:

§§§text
jshell> /vars
§§§

Confirm that §productName§, §unitPrice§, §quantity§, §subtotal§, §taxRate§, §taxAmount§, and §total§ exist with the expected types and values.

This exercise demonstrates that variables persist across the session and can be updated and reused across consecutive snippets without creating a complete Java class.

## 18. Best Practices for Declaring Variables in JShell

When experimenting with a piece of logic:

1. Start JShell using the JDK version that matches your project.
2. Declare variables with explicit types when the data type matters; use §var§ when the initializer makes the inferred type obvious.
3. Initialize variables upon declaration whenever the initial value is known.
4. Name variables using §lowerCamelCase§ and reflect their meaning clearly.
5. Enter small snippets in dependency order so errors are easy to isolate.
6. Use §/vars§ to inspect current variable names, types, and values.
7. Use §/list§ to review declarations and snippet IDs.
8. When changing a variable's type or name, check any dependent methods and snippets.
9. Use §/save§ if you need to keep experimental code; reload it with §/open§ when needed.
10. Move stabilized code into a §.java§ file with proper classes, methods, tests, and project structure.

## 19. Summary

Declaring variables in JShell uses familiar Java syntax directly inside a REPL session. Valid declarations are retained for use by subsequent snippets.

Key takeaways:

- Use §type name = value;§ to declare a variable with an explicit type.
- Use §var name = expression;§ to infer the type from the initializer on Java 10 and later.
- Primitive and reference types differ in how they store values, compare equality, and handle null.
- Prefer initializing variables when declaring them; JShell provides default values for top-level variables without initializers, whereas local variables in Java methods must be assigned before being read.
- Reassigning a value does not change a variable's static type.
- §final§ prevents reassignment; for reference types, it does not make the object immutable.
- Redeclaring the same name in JShell replaces the previous snippet, which is REPL-specific behavior.
- §/vars§, §/list§, §/drop§, §/save§, §/open§, §/reset§, and §/exit§ help manage the session.
- Expressions without a variable name can create scratch variables in the form §$<id>§.

Practicing variable declarations in JShell helps you quickly verify Java types, values, and expressions before moving stabilized logic into production code.

**Official references:**

- [The jshell Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jshell.html)
- [Java Shell User's Guide — Snippets](https://docs.oracle.com/en/java/javase/25/jshell/snippets.html)
- [JShell API — Snippet.Kind](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jshell/jdk/jshell/Snippet.Kind.html)
