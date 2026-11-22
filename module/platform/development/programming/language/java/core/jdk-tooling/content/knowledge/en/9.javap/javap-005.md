# Viewing Private Members with javap

In Java, class members can be declared with different access levels: `public`, `protected`, package-private (no modifier), and `private`. When inspecting a library or a `.class` file, it is sometimes necessary to view non-public fields and methods as well.

The JDK's **`javap`** tool supports this with the `-p` or `-private` option. This option instructs it to display all members declared in the class file, including private members.

## 1. Why View Private Members?

Following the principle of encapsulation, a class typically keeps its internal data and operations private, exposing only a public API to external code.

For example:

```java
public class User {
    private String password;
    private boolean active;

    public boolean isActive() {
        return active;
    }
}
```

Code outside the class can call `isActive()`, but cannot directly access `password` under standard Java access rules.

When analyzing a class file, viewing only the public API may not be enough. You may need to know:

- What private fields the class has.
- What private methods perform internal processing.
- How constructors and overloaded methods are declared.
- The data types, parameters, and return types of members.
- Whether members have `static`, `final`, `volatile`, `synchronized`, or other special flags.
- Whether the compiler generated additional bridge methods or synthetic members.

`javap -p` lets you inspect this metadata without needing the original source code.

## 2. The -p and -private Options

The following two forms serve the same purpose:

```bash
javap -p ClassName
javap -private ClassName
```

`-p` is the short form of `-private`. This option instructs `javap` to display every field and method declared in the class, regardless of access level.

Without `-p`, `javap` displays `public` and `protected` members by default. Private and package-private members are not shown in the default mode.

Related options:

| Option | Scope of members displayed |
| --- | --- |
| `-public` | Only public |
| `-protected` | Public and protected; this is the default mode |
| `-package` | Public, protected, and package-private |
| `-private` or `-p` | All members, including private |

Example:

```bash
javap -classpath out -p User
```

This command looks up the `User` class in the `out` directory and displays private members as well.

**Note:** `-p` controls how `javap` displays the contents of a class file. It does not change modifiers in the class file, modify bytecode, or grant private access to other Java programs.

## 3. Preparing an Example with Private Members

Create a file named **`PrivateMemberDemo.java`**:

```java
public class PrivateMemberDemo {
    private String name;
    private static final int MAX_RETRIES = 3;

    String state = "READY";
    protected int retryCount;

    public PrivateMemberDemo(String name) {
        this.name = normalize(name);
    }

    private String normalize(String value) {
        return value.trim().toUpperCase(java.util.Locale.ROOT);
    }

    private static boolean isValid(String value) {
        return value != null && !value.isEmpty();
    }

    public String getName() {
        return name;
    }

    void reset() {
        retryCount = 0;
        state = "READY";
    }

    protected void incrementRetry() {
        if (retryCount < MAX_RETRIES) {
            retryCount++;
        }
    }

    public static void main(String[] args) {
        PrivateMemberDemo demo = new PrivateMemberDemo("Java");
        System.out.println(demo.getName());
        System.out.println(isValid("Java"));
    }
}
```

The class contains several kinds of members:

| Member | Access level | Kind |
| --- | --- | --- |
| `name` | private | Instance field |
| `MAX_RETRIES` | private | Static final field |
| `state` | package-private | Instance field |
| `retryCount` | protected | Instance field |
| `normalize(String)` | private | Instance method |
| `isValid(String)` | private static | Static method |
| `getName()` | public | Instance method |
| `reset()` | package-private | Instance method |
| `incrementRetry()` | protected | Instance method |
| `main(String[])` | public static | Static method |

Compile the example using the JDK:

```bash
javac -g -parameters -d out PrivateMemberDemo.java
```

- `-g` includes debug information such as line numbers and local variables.
- `-parameters` stores method parameter names in the appropriate metadata.
- `-d out` sets the root directory for output class files.

After compilation, the file is created at:

```text
out/
  PrivateMemberDemo.class
```

## 4. Comparing Output Before and After Using -p

### Default Mode

Run:

```bash
javap -classpath out PrivateMemberDemo
```

Sample output:

```text
Compiled from "PrivateMemberDemo.java"
public class PrivateMemberDemo {
  protected int retryCount;
  public PrivateMemberDemo(java.lang.String);
  public java.lang.String getName();
  protected void incrementRetry();
  public static void main(java.lang.String[]);
}
```

Private members such as `name`, `MAX_RETRIES`, `normalize()`, and `isValid()` do not appear. Package-private members such as `state` and `reset()` also do not appear in the default mode.

### Displaying All Members

Run:

```bash
javap -classpath out -p PrivateMemberDemo
```

Sample output:

```text
Compiled from "PrivateMemberDemo.java"
public class PrivateMemberDemo {
  private java.lang.String name;
  private static final int MAX_RETRIES;
  java.lang.String state;
  protected int retryCount;
  public PrivateMemberDemo(java.lang.String);
  private java.lang.String normalize(java.lang.String);
  private static boolean isValid(java.lang.String);
  public java.lang.String getName();
  void reset();
  protected void incrementRetry();
  public static void main(java.lang.String[]);
}
```

Now both private fields, private methods, and package-private members are visible. The display order or some formatting details may vary across JDK versions; compare names, descriptors, and access flags rather than relying strictly on line order.

## 5. Viewing Descriptors of Private Members

To view type signatures in JVM format, combine `-p` with `-s`:

```bash
javap -classpath out -p -s PrivateMemberDemo
```

Options:

- `-p`: displays private members as well.
- `-s`: displays field and method descriptors.

For example, some descriptors in the class:

| Java member | Descriptor |
| --- | --- |
| `private String name;` | `Ljava/lang/String;` |
| `private static final int MAX_RETRIES;` | `I` |
| `private String normalize(String value)` | `(Ljava/lang/String;)Ljava/lang/String;` |
| `private static boolean isValid(String value)` | `(Ljava/lang/String;)Z` |
| `PrivateMemberDemo(String name)` (constructor) | `(Ljava/lang/String;)V` |

Parameter names are not part of a descriptor. A method descriptor consists of the parameter types in parentheses followed by the return type. The symbol `V` represents `void`.

When inspecting a compiled library, descriptors help distinguish overloaded methods and identify the exact types the JVM uses when linking methods.

## 6. Viewing Bytecode Inside Private Methods

Private methods have bytecode just like ordinary Java methods with a body. Use `-c` to view bytecode instructions:

```bash
javap -classpath out -p -c PrivateMemberDemo
```

In the output, locate the section:

```text
private java.lang.String normalize(java.lang.String);
  Code:
     ...
```

The `-p` option makes the private method appear; `-c` displays its bytecode.

For the `normalize` method, the bytecode performs operations corresponding to:

1. Receiving the `String` parameter.
2. Calling `trim()`.
3. Calling `toUpperCase(Locale.ROOT)`.
4. Returning the resulting string.

Specific instructions and offsets may differ across JDK versions. If you need to inspect method calls, local variables, and the operand stack, read the `Code` section of the method in the disassembly output.

## 7. Viewing Access Flags and Detailed Metadata

To view full access flags, descriptors, the constant pool, and attributes, run:

```bash
javap -classpath out -p -v PrivateMemberDemo
```

A private field may be displayed similarly to:

```text
private java.lang.String name;
  descriptor: Ljava/lang/String;
  flags: ACC_PRIVATE
```

A private instance method may have:

```text
private java.lang.String normalize(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  flags: ACC_PRIVATE
```

A private static method may have a combination of flags:

```text
private static boolean isValid(java.lang.String);
  descriptor: (Ljava/lang/String;)Z
  flags: ACC_PRIVATE, ACC_STATIC
```

Common flags:

| Access flag | Meaning |
| --- | --- |
| `ACC_PRIVATE` | Member has private access |
| `ACC_PROTECTED` | Member has protected access |
| `ACC_PUBLIC` | Member has public access |
| `ACC_STATIC` | Member belongs to the class |
| `ACC_FINAL` | Member has final semantics |
| `ACC_SYNCHRONIZED` | Method has synchronized semantics |
| `ACC_BRIDGE` | Bridge method generated by the compiler |
| `ACC_SYNTHETIC` | Member generated by the compiler |

For the `MAX_RETRIES` field, you can combine the `-constants` option to view eligible constant values:

```bash
javap -classpath out -p -constants PrivateMemberDemo
```

The output may display:

```text
private static final int MAX_RETRIES = 3;
```

Not every `final` field has a `ConstantValue` attribute in the class file. Values that must be computed at runtime may be set by initialization bytecode.

## 8. Inspecting Private Members in a JAR

You do not need to extract a JAR library just to view a class's declarations. You can specify the JAR as the classpath and pass the fully qualified class name.

For example, if the library contains `com.example.internal.TokenStore`:

```bash
javap -classpath lib/example.jar -p com.example.internal.TokenStore
```

To view descriptors and bytecode:

```bash
javap -classpath lib/example.jar -p -s -c com.example.internal.TokenStore
```

If there are multiple dependent JARs, pass the classpath list according to your operating system:

**Windows:**

```powershell
javap -classpath "lib\example.jar;lib\common.jar" -p com.example.internal.TokenStore
```

**macOS/Linux:**

```bash
javap -classpath "lib/example.jar:lib/common.jar" -p com.example.internal.TokenStore
```

The classpath must point to the JAR containing the class you want to inspect. If the class is in a package, use its dot-separated fully qualified name, such as `com.example.internal.TokenStore`.

## 9. Inspecting Private Members of Inner Classes

A nested class has its own class file. For example:

```java
public class Outer {
    private static class Secret {
        private String value = "hidden";

        private String read() {
            return value;
        }
    }
}
```

The compiler generates class files with binary names similar to:

```text
Outer.class
Outer$Secret.class
```

You can inspect private members of the nested class with:

```bash
javap -classpath out -p 'Outer$Secret'
```

The quotes prevent the shell from interpreting the `$` character as an environment or shell variable. Binary class names use `$` to separate the nested class from the outer class.

If you need to view private members of both the outer class and the nested class, run `javap -p` separately on each class file.

## 10. javap -p Does Not Change Access Permissions

It is important to distinguish between **inspecting metadata** and **accessing members at runtime**.

`javap -p` only reads information from the class file and displays members that are already declared. It does not:

- Turn private members into public ones.
- Modify access flags or bytecode.
- Allow other source code to call private methods directly.
- Bypass compiler or JVM access checks.
- Automatically read the current value of a field in a running object.

For example, the following code remains invalid if placed in a class not permitted to access `normalize()`:

```java
PrivateMemberDemo demo = new PrivateMemberDemo("Java");
demo.normalize("text"); // Access error: normalize() is private
```

The fact that a tool displays a method name does not mean external code is allowed to call that method.

Reflection is a separate mechanism for inspecting and interacting with members at runtime. Reflection is subject to Java's access rules and module restrictions; knowing a private member's name from `javap` does not automatically grant access via reflection.

## 11. Private Members, Inheritance, and Class File Scope

Private members belong to the declaring class. When inspecting a subclass, `javap -p` displays the members declared in the subclass's class file; it does not turn the superclass's private members into members of the subclass.

For example:

```java
class Base {
    private String secret;
    protected int count;
}

public class Child extends Base {
    private boolean enabled;
}
```

When inspecting:

```bash
javap -p Base
javap -p Child
```

The first command displays `secret` and `count`. The second command displays `enabled` along with any members declared in `Child`. To view the superclass's private members, inspect the superclass's class file separately.

## 12. Common Issues

| Symptom | Common cause | Solution |
| --- | --- | --- |
| Private fields/methods not shown | Using `javap`'s default mode | Add `-p` or `-private` |
| Expected member still not shown | Inspecting the wrong class file or wrong classpath | Check class name, package, and JAR/directory location |
| Descriptors are hard to understand | Confusing JVM notation with Java types | Use `-s` and refer to the descriptor table |
| Private method bytecode not shown | Missing `-c` or method has no bytecode body | Use `-p -c`; `abstract`/`native` methods have no regular `Code` |
| Constant values not shown | Missing `-constants` or field is not an eligible constant variable | Check `-p -constants` and the class initializer |
| Cannot call method even though `javap` shows it | `-p` only changes display, not access permissions | Follow access control; use public APIs or appropriate access design |
| Inner class name not recognized | Wrong binary name or shell interpreting `$` | Use `Outer$Inner` format and wrap in quotes |

## 13. Recommended Inspection Workflow

When you need to analyze non-public members of a class:

1. Identify the correct class file or JAR and the fully qualified class name.
2. Run `javap -p` to list all declared fields and methods.
3. Use `-s` to view descriptors and distinguish overloads.
4. Use `-c` to read the bytecode of private methods that have a body.
5. Use `-v` to inspect access flags, attributes, and metadata.
6. Use `-constants` when you need to view eligible constant values.
7. If inspecting inherited classes or inner classes, inspect each relevant class file separately.
8. Distinguish class file analysis results from actual access permissions in Java code.

## 14. Key Takeaways

- `javap -p` and `javap -private` display all declared members, including private and package-private ones.
- `javap`'s default mode displays `public` and `protected` members.
- Combine `-s` to view descriptors, `-c` to view bytecode, and `-v` to view detailed metadata.
- Use `-constants` to view values of eligible constants.
- Class files of nested classes and superclasses must be inspected separately to see the members declared in each class.
- `javap -p` only displays class file information; it does not change private access permissions or read the runtime state of objects.

Once you know how to use `javap -p`, you can thoroughly analyze the internal structure of a Java class, inspect library APIs, and understand how the compiler represents non-public members in class files.
