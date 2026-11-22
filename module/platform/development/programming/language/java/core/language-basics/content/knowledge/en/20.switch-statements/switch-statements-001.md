# Switch Statements and Supported Selector Types — Java 17+

## 1. What Is a Switch Statement Used For?

`switch` selects how to handle execution based on **a single value** (*selector*). It is useful when multiple branches compare against a command code, character, enum state, or discrete value.

~~~java
int option = 2;

switch (option) {
    case 1:
        System.out.println("Create");
        break;
    case 2:
        System.out.println("Update");
        break;
    default:
        System.out.println("Unknown");
}
~~~

**Exact output:**

~~~text
Update
~~~

In Java 17, it is important to distinguish:

- **Switch statement**: executes statements or blocks; **does not itself return a value** that can be assigned.
- **Switch expression**: produces a value using `switch` in an expression position; it has different rules regarding branch exhaustiveness and `yield`. This lesson focuses on the **switch statement**.

A switch statement can be written using the traditional `case ...:` syntax or the arrow branch syntax `case ... ->` (stabilized before Java 17).

## 2. Supported Selector Types in Java 17

In Java 17's standard, stable switch syntax, the `switch (selector)` expression can have the following types:

| Group | Valid selector types | Example |
|---|---|---|
| Primitive integers | `byte`, `short`, `char`, `int` | `switch (code)` with `int code` |
| Corresponding wrapper classes | `Byte`, `Short`, `Character`, `Integer` | `switch (boxedCode)` |
| Strings | `String` | `switch (command)` |
| Enumerations | A specific `enum` type | `switch (status)` with `Status status` |

**Cannot be used directly**: `long`/`Long`, `float`/`Float`, `double`/`Double`, `boolean`/`Boolean`, `Object`, arrays, or an arbitrary class.

~~~java
long bigId = 10L;
// switch (bigId) { case 10 -> System.out.println("ten"); }
// COMPILE ERROR in Java 17: long is not a valid selector type.

boolean enabled = true;
// switch (enabled) { case true -> System.out.println("enabled"); }
// COMPILE ERROR in Java 17: boolean is not supported.
~~~

A special case: if the selector has **static type `Object`**, the fact that the object happens to hold an `Integer` at runtime does not make `switch (object)` a valid switch. The compiler checks the **expression's type**, not inferred runtime values.

**Version scope:** Java 17 has *pattern matching for switch* as a preview feature, which requires enabling preview options and has different rules. Examples in this lesson use **stable Java 17 switch**, compiled with `--release 17` and **without preview enabled**.

## 3. Recognizing Colon Syntax and Fall-Through

In the traditional form, `case VALUE:` marks an execution entry point. Without `break`, `return`, or `throw`, Java can execute the statements after the next label without re-checking the selector. This is *fall-through*, not multiple values matching at once. The lesson on colon form and the lesson on `break` analyze this control flow in full.

## 4. Recognizing Arrow-Style `->` Switch Statements

Java 17 allows `case 2, 3 -> System.out.println("two or three");`. Once an arrow branch finishes executing, control does not fall through to the following branch. The right-hand side can be a statement expression, a `{ ... }` block, or `throw`.

The arrow does not automatically turn a switch into an **expression**: the example above is still a statement performing an action. The lesson on arrow branch blocks covers syntax and variable scoping separately.

## 5. Small Integer Selectors: `byte`, `short`, `char`, `int`

These primitive types are directly supported:

~~~java
byte byteCode = 1;
short shortCode = 300;
char letter = 'A';
int action = 2;

switch (byteCode) {
    case 1 -> System.out.println("byte one");
    default -> System.out.println("byte other");
}

switch (shortCode) {
    case 300 -> System.out.println("short 300");
    default -> System.out.println("short other");
}

switch (letter) {
    case 'A' -> System.out.println("letter A");
    default -> System.out.println("other letter");
}

switch (action) {
    case 2 -> System.out.println("action two");
    default -> System.out.println("other action");
}
~~~

Java checks that the **`case` label value is compatible with the selector type's range**:

~~~java
byte small = 10;
// switch (small) {
//     case 128 -> System.out.println("impossible");
// }
// COMPILE ERROR: 128 exceeds the byte range (-128..127).
~~~

For `char`, labels can use character literals like `'A'` or compatible integer constant expressions. `'A'` and `65` have the same value, so they cannot be placed as two duplicate case labels.

## 6. Integer `case` Labels Must Be Compile-Time Constants

In a switch using traditional constant labels, an integer `case` must be a compatible **constant expression**; an ordinary variable is invalid even if it currently holds the exact number.

~~~java
static final int OPEN = 1; // valid constant variable

int option = 1;
switch (option) {
    case OPEN -> System.out.println("open");
    default -> System.out.println("unknown");
}
~~~

A common mistake:

~~~java
int dynamicCode = 1;
// switch (option) {
//     case dynamicCode -> System.out.println("open");
// }
// COMPILE ERROR: dynamicCode is not a constant expression.
~~~

A `final int` initialized with a compatible constant expression can be used as a label. However, `final` alone **does not turn any runtime-computed value into a compile-time constant**.

For example, `final int code = Integer.parseInt("1")` cannot be used as a `case code` label even though `code` is never reassigned.

**Duplicate label values** are a compile error:

~~~java
// case 1 -> ...;
// case 1 -> ...; // ERROR: duplicate case label.
~~~

## 7. `String` Selector: Content Comparison, Case-Sensitive

`switch` on `String` selects based on **string content**, without requiring the two `String` variables to reference the same object.

~~~java
String command = new String("start");

switch (command) {
    case "start" -> System.out.println("starting");
    case "stop" -> System.out.println("stopping");
    default -> System.out.println("unknown");
}
~~~

**Exact output:**

~~~text
starting
~~~

The `case "start"` label must be a compile-time `String` constant. Java compares content for case selection, corresponding to `String.equals` semantics, **not relying on `==` reference comparison**.

**Case sensitivity:** `"start"` and `"START"` do not match the same way. If you want case-insensitive matching, normalize the input **according to an explicit rule** before switching, such as `command.toLowerCase(Locale.ROOT)` for a case-insensitive ASCII command set.

Do not blindly call `toLowerCase()` on input that has not been null-checked.

## 8. `enum` Selector: Labels Are Enum Constant Names

~~~java
enum Status {
    NEW, RUNNING, DONE
}

Status status = Status.RUNNING;
switch (status) {
    case NEW -> System.out.println("created");
    case RUNNING -> System.out.println("working");
    case DONE -> System.out.println("finished");
}
~~~

**Exact output:**

~~~text
working
~~~

In a switch with a selector of type `Status`, enum labels are written as **`case RUNNING`**, not `case Status.RUNNING`, in standard Java 17 enum switch syntax. Enum labels must belong to the enum type being switched on.

**A switch statement is not always required to have `default`**. However, if you want to handle an unlisted enum value or keep code clear when the enum evolves, decide on an appropriate `default` policy. For switch expressions, branch exhaustiveness has separate requirements.

## 9. Wrapper Types: `Byte`, `Short`, `Character`, `Integer`

All four of the following wrapper classes can be used as selectors in stable Java 17:

~~~java
Byte boxedByte = 1;
Short boxedShort = 300;
Character boxedChar = 'A';
Integer boxedInt = 7;

switch (boxedByte) {
    case 1 -> System.out.println("Byte one");
    default -> System.out.println("Byte other");
}
switch (boxedShort) {
    case 300 -> System.out.println("Short 300");
    default -> System.out.println("Short other");
}
switch (boxedChar) {
    case 'A' -> System.out.println("Character A");
    default -> System.out.println("Character other");
}
switch (boxedInt) {
    case 7 -> System.out.println("Integer seven");
    default -> System.out.println("Integer other");
}
~~~

Wrappers are object references, but selectors of these types are handled according to their corresponding primitive values; watch out for **unboxing** when the selector is nullable.

Do not generalize this conclusion to "all wrappers are supported": **`Long`**, **`Float`**, **`Double`**, and **`Boolean`** are not valid selectors in standard Java 17 switch.

## 10. Reference-Type Selector Is `null`

For `String`, enum, or permitted wrapper selectors, standard Java 17 throws `NullPointerException` if the selector is `null`; `default` only handles **values that do not match a case**. Check for null before switching if the input can be missing:

~~~java
if (command == null) {
    System.out.println("missing command");
} else {
    switch (command) {
        case "start" -> System.out.println("start");
        default -> System.out.println("unknown");
    }
}
~~~

Policies for returning results or throwing errors on missing input are analyzed in the dedicated lesson on `null`.

## 11. When Should You Use `if` Instead of `switch`?

`switch` fits multiple discrete values of a valid selector. Thresholds (`age >= 18`), numeric ranges, combinations of multiple conditions, or priorities are usually clearer with `if/else if`. Do not cast `long` or `double` to `int` just to write a switch if doing so could lose information. The final lesson of this chapter provides a structure-selection workflow with business examples.

## 12. Complete, Standalone Java 17 Program

Create a file named **`SwitchStatementTypesDemo.java`**:

~~~java
public final class SwitchStatementTypesDemo {
    private SwitchStatementTypesDemo() {}

    enum Status {
        NEW, RUNNING, DONE
    }

    static final int OPEN = 1;

    static void showInt(int value) {
        switch (value) {
            case OPEN:
                System.out.println("int=open");
                break;
            case 2:
            case 3:
                System.out.println("int=two-or-three");
                break;
            default:
                System.out.println("int=other");
        }
    }

    static void showByte(byte value) {
        switch (value) {
            case -1 -> System.out.println("byte=negative-one");
            case 127 -> System.out.println("byte=max");
            default -> System.out.println("byte=other");
        }
    }

    static void showShort(short value) {
        switch (value) {
            case 300 -> System.out.println("short=300");
            default -> System.out.println("short=other");
        }
    }

    static void showChar(char value) {
        switch (value) {
            case 'A' -> System.out.println("char=A");
            default -> System.out.println("char=other");
        }
    }

    static void showString(String command) {
        switch (command) {
            case "start" -> System.out.println("string=start");
            case "stop" -> System.out.println("string=stop");
            default -> System.out.println("string=other");
        }
    }

    static void showStatus(Status status) {
        switch (status) {
            case NEW -> System.out.println("enum=new");
            case RUNNING -> System.out.println("enum=running");
            case DONE -> System.out.println("enum=done");
        }
    }

    static void showInteger(Integer value) {
        switch (value) {
            case 7 -> System.out.println("Integer=seven");
            default -> System.out.println("Integer=other");
        }
    }

    static void showWrappers() {
        Byte b = 1;
        Short s = 300;
        Character c = 'A';

        switch (b) {
            case 1 -> System.out.println("Byte=one");
            default -> System.out.println("Byte=other");
        }
        switch (s) {
            case 300 -> System.out.println("Short=300");
            default -> System.out.println("Short=other");
        }
        switch (c) {
            case 'A' -> System.out.println("Character=A");
            default -> System.out.println("Character=other");
        }
    }

    static void showFallThrough(int value) {
        switch (value) {
            case 1:
                System.out.println("fall=one");
                break;
            case 2:
                System.out.println("fall=two");
            case 3:
                System.out.println("fall=three");
                break;
            default:
                System.out.println("fall=other");
        }
    }

    public static void main(String[] args) {
        showInt(1);
        showInt(2);
        showInt(9);

        showByte((byte) -1);
        showByte((byte) 127);
        showShort((short) 300);
        showChar('A');

        showString(new String("start"));
        showString("START");
        showStatus(Status.RUNNING);

        showWrappers();
        showInteger(Integer.valueOf(7));

        showFallThrough(2);

        String missing = null;
        try {
            showString(missing);
        } catch (NullPointerException ex) {
            System.out.println("null String=NullPointerException");
        }

        Integer missingNumber = null;
        try {
            showInteger(missingNumber);
        } catch (NullPointerException ex) {
            System.out.println("null Integer=NullPointerException");
        }
    }
}
~~~

**Requirements:** JDK 17 or higher; terminal in the directory containing `SwitchStatementTypesDemo.java`. The program uses no external libraries beyond the JDK or preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SwitchStatementTypesDemo.java
java -cp . SwitchStatementTypesDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SwitchStatementTypesDemo.java
java -cp . SwitchStatementTypesDemo
~~~

### Exact expected stdout

~~~text
int=open
int=two-or-three
int=other
byte=negative-one
byte=max
short=300
char=A
string=start
string=other
enum=running
Byte=one
Short=300
Character=A
Integer=seven
fall=two
fall=three
null String=NullPointerException
null Integer=NullPointerException
~~~

**Reading the output:**

1. `int=open` proves `case OPEN` is a compile-time constant and can be used as a label.
2. `int=two-or-three` illustrates multiple labels sharing one action.
3. `byte`, `short`, `char`, `int`, and the four corresponding wrappers can all be used as selectors.
4. `new String("start")` still matches `case "start"`: switch compares **String content**; `"START"` falls into default because of case sensitivity.
5. Enum selects constant `RUNNING` by name without a type prefix.
6. `fall=two` and `fall=three` show that the `:` form can fall through when `break` is missing.
7. A null `String` or `Integer` selector throws NPE; `default` does not catch null in stable Java 17 switch.

## 13. Common Mistakes

| Mistake or misconception | Consequence | Correct approach |
|---|---|---|
| `switch(longValue)` in Java 17 | Does not compile | `if/else` or explicit int code design |
| `switch(booleanFlag)` | Does not compile | `if (flag) ... else ...` |
| `switch(doubleValue)` | Does not compile | Floating-point conditions with appropriate tolerance policy |
| `switch(object)` with `Object` holding an Integer | Static type Object is invalid | Use a selector with a concrete supported type |
| `case variable:` with a runtime variable | Label is not a compile-time constant | `static final` constant or constant expression |
| Two case labels with the same value | Duplicate case compile error | Remove duplicates |
| `case 128` with a byte selector | Outside byte range | Choose a representable label |
| Missing `break` in a `case:` branch | Unintended fall-through | Add `break` or use `->` |
| Expecting `default` to handle a null selector | Null causes NPE | Guard for null before switch |
| Expecting `switch(String)` to compare references | Actually compares content | Understand case-sensitive content matching |
| Writing `case Status.RUNNING` in a regular enum switch | Invalid Java 17 enum label form | Write `case RUNNING` |
| Thinking `->` form is always a switch expression | Switch statements also use `->` | Distinguish context and purpose |
| Reading `case null` docs from another version and applying directly | Differs from non-preview Java 17 | Check version/preview flags |

## 14. Exercises and Solutions

### Exercise A — Which selectors are valid?

Consider `byte`, `long`, `Character`, `String`, `boolean`, `Status enum`, `Double`, `Integer`.

**Solution:** `byte`, `Character`, `String`, `Status`, and `Integer` are valid; `long`, `boolean`, and `Double` are invalid for standard stable switch in Java 17.

### Exercise B — Fall-through

~~~java
int x = 1;
switch (x) {
    case 1:
        System.out.println("A");
    case 2:
        System.out.println("B");
        break;
    default:
        System.out.println("C");
}
~~~

**Solution:**

~~~text
A
B
~~~

Missing `break` after branch 1 causes execution to continue into branch 2.

### Exercise C — Avoiding fall-through

Rewrite so that `x = 1` prints only `A` using Java 17 syntax:

~~~java
switch (x) {
    case 1 -> System.out.println("A");
    case 2 -> System.out.println("B");
    default -> System.out.println("C");
}
~~~

**Solution:** Prints only `A`. The `->` form does not fall through.

### Exercise D — String with a different reference

~~~java
String command = new String("stop");
switch (command) {
    case "stop" -> System.out.println("matched");
    default -> System.out.println("other");
}
~~~

**Solution:** `matched`, because String switch compares **content**, not object identity.

### Exercise E — Null wrapper

~~~java
Integer code = null;
// switch (code) {
//     case 1 -> System.out.println("one");
//     default -> System.out.println("other");
// }
~~~

**Solution:** When executing switch on null `code`, it throws `NullPointerException` and does not run default. You must check for null beforehand.

### Exercise F — Choosing switch or if?

Requirement: classify age `age >= 18 && age < 65`, or handle commands `"start"`/`"stop"`.

**Solution:** Use `if` for the **age range** condition, and use `switch(String)` for **discrete command values**.

## 15. Checklist and Conclusion

- [ ] Know that a switch statement selects a branch based on a selector of a **supported type**.
- [ ] Remember the four supported primitives: `byte`, `short`, `char`, `int`.
- [ ] Remember the four corresponding wrappers: `Byte`, `Short`, `Character`, `Integer`.
- [ ] Know that `String` and specific `enum` types can also be used as selectors.
- [ ] Know that `long`, `float`, `double`, `boolean`, and their corresponding wrappers cannot be used directly in stable Java 17.
- [ ] Constant `case` labels must be valid in type, value, and non-duplicate.
- [ ] Know that String switch compares content and is case-sensitive.
- [ ] Know that regular enum labels are written `case RUNNING`, not `case Status.RUNNING`.
- [ ] Understand that `case:` needs `break` when fall-through is not wanted.
- [ ] Understand that `case ->` does not fall through and **can still be a statement**.
- [ ] Guard null selectors before switch; `default` does not catch null in non-preview Java 17.
- [ ] Use `if/else` for range/constraint conditions that cannot be expressed with case constants.
- [ ] Run `SwitchStatementTypesDemo.java` on Java 17+ with `javac`/`java` and verify stdout.

**Conclusion:** For stable Java 17 switch statements, the supported selectors are **`byte`/`short`/`char`/`int`**, **the four corresponding wrappers**, **`String`**, and **`enum`**. `case` labels must follow type and constant rules; the `:` form can fall through, whereas the `->` form avoids that. In particular, check for **null** before switching on reference types and choose `if/else` when relational or complex conditions are needed.