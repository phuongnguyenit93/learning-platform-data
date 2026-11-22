# Handling `null` in `switch` and Distinguishing It from `default` — Java 17+

**`default` is not a `null`-handling branch.** In standard Java 17 `switch` features, if the selector expression (*selector*) evaluates to `null`, the program throws `NullPointerException` **before entering any `case` or `default` label**.

~~~java
String status = null;

// This snippet will throw NullPointerException at runtime:
// switch (status) {
//     case "ON" -> System.out.println("enabled");
//     default -> System.out.println("unknown");
// }
~~~

Conversely, `default` runs when the selector is **non-null**, yet does not match any `case` label:

~~~java
String status = "PAUSE";
switch (status) {
    case "ON" -> System.out.println("enabled");
    case "OFF" -> System.out.println("disabled");
    default -> System.out.println("unknown"); // Runs this branch.
}
~~~

## 1. Distinguishing Non-Matching Cases from `null`

| `String` selector value | Matches `case "ON"`? | Does `default` run? | Behavior |
| --- | --- | --- | --- |
| `"ON"` | Yes | No | Runs `case "ON"` |
| `"OFF"` | No, but matches another case | No | Runs `case "OFF"` |
| `"PAUSE"` | No | Yes | Runs `default` |
| `""` (empty string) | No | Yes | Runs `default` |
| `null` | Does not check cases | **No** | Throws `NullPointerException` |

The empty string `""` is **a non-null `String` object**, so it can perfectly well be handled by `default`. `null` references no `String` object at all.

This applies to both **switch statements** and **switch expressions** in standard Java 17, even when `default` is declared.

## 2. The Safe Approach: Check `null` Before `switch`

### Return a separate result for missing data

~~~java
static String describe(String status) {
    if (status == null) {
        return "missing";
    }
    return switch (status) {
        case "ON" -> "enabled";
        case "OFF" -> "disabled";
        default -> "unknown";
    };
}
~~~

- `"missing"`: the input **does not exist**.
- `"unknown"`: the input **exists**, but is neither `"ON"` nor `"OFF"`.
- `case` branches: recognized valid values.

These are two distinct business states. Do not automatically merge `null` with `default` if the application needs to distinguish "not provided" from "provided but unrecognized".

### Reject with an error instead of substituting a value

If `null` violates the method's contract, reject it explicitly:

~~~java
static String requireStatus(String status) {
    if (status == null) {
        throw new IllegalArgumentException("status required");
    }
    return switch (status) {
        case "ON" -> "enabled";
        default -> "unknown";
    };
}
~~~

Here `IllegalArgumentException` expresses a policy **chosen by the program**. By contrast, an automatic `NullPointerException` from `switch(null)` often makes it harder for callers to understand the business meaning of the error.

## 3. Standalone Java 17+ Example, Runnable CLI

Create UTF-8 file **`SwitchNullDemo.java`**:

~~~java
public class SwitchNullDemo {
    enum Mode { START, STOP }

    static String statement(String code) {
        if (code == null) {
            return "missing";
        }
        String result;
        switch (code) {
            case "ON":
                result = "enabled";
                break;
            case "OFF":
                result = "disabled";
                break;
            default:
                result = "unknown";
        }
        return result;
    }

    static String expression(String code) {
        if (code == null) {
            return "missing";
        }
        return switch (code) {
            case "ON" -> "enabled";
            case "OFF" -> "disabled";
            default -> "unknown";
        };
    }

    static String number(Integer n) {
        if (n == null) {
            return "missing";
        }
        return switch (n) {
            case 0 -> "zero";
            case 1 -> "one";
            default -> "other";
        };
    }

    static String mode(Mode m) {
        if (m == null) {
            return "missing";
        }
        return switch (m) {
            case START -> "start";
            case STOP -> "stop";
        };
    }

    static String rawString(String code) {
        return switch (code) {
            case "ON" -> "enabled";
            default -> "default";
        };
    }

    static String rawNumber(Integer n) {
        return switch (n) {
            case 0 -> "zero";
            default -> "default";
        };
    }

    static String rawMode(Mode m) {
        return switch (m) {
            case START -> "start";
            case STOP -> "stop";
        };
    }

    static String requireCode(String code) {
        if (code == null) {
            throw new IllegalArgumentException("code required");
        }
        return rawString(code);
    }

    public static void main(String[] args) {
        System.out.println("== String guard ==");
        for (String s : new String[] {null, "ON", "OFF", "PAUSE", ""}) {
            System.out.println("input=" + String.valueOf(s)
                    + ",statement=" + statement(s)
                    + ",expression=" + expression(s));
        }

        System.out.println("== wrapper and enum ==");
        System.out.println("numberNull=" + number(null));
        System.out.println("number0=" + number(0));
        System.out.println("number9=" + number(9));
        System.out.println("modeNull=" + mode(null));
        System.out.println("modeStart=" + mode(Mode.START));
        System.out.println("modeStop=" + mode(Mode.STOP));

        System.out.println("== default versus null ==");
        System.out.println("unmatched=" + rawString("PAUSE"));
        System.out.println("empty=" + rawString(""));
        System.out.println("unmatchedNumber=" + rawNumber(7));

        try {
            System.out.println("unexpected=" + rawString(null));
        } catch (NullPointerException ex) {
            System.out.println("nullString=NullPointerException");
        }
        try {
            System.out.println("unexpected=" + rawNumber(null));
        } catch (NullPointerException ex) {
            System.out.println("nullNumber=NullPointerException");
        }
        try {
            System.out.println("unexpected=" + rawMode(null));
        } catch (NullPointerException ex) {
            System.out.println("nullMode=NullPointerException");
        }

        System.out.println("== explicit contract ==");
        try {
            requireCode(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
        System.out.println("required=" + requireCode("ON"));

        String maybeNull = null;
        String safe = maybeNull == null
                ? "missing"
                : rawString(maybeNull);
        System.out.println("ternary=" + safe);
    }
}
~~~

Using **JDK 17 or higher**, open PowerShell or Bash in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SwitchNullDemo.java
java SwitchNullDemo
~~~

**Exact expected stdout** from `java SwitchNullDemo` alone:

~~~text
== String guard ==
input=null,statement=missing,expression=missing
input=ON,statement=enabled,expression=enabled
input=OFF,statement=disabled,expression=disabled
input=PAUSE,statement=unknown,expression=unknown
input=,statement=unknown,expression=unknown
== wrapper and enum ==
numberNull=missing
number0=zero
number9=other
modeNull=missing
modeStart=start
modeStop=stop
== default versus null ==
unmatched=default
empty=default
unmatchedNumber=default
nullString=NullPointerException
nullNumber=NullPointerException
nullMode=NullPointerException
== explicit contract ==
invalid=code required
required=enabled
ternary=missing
~~~

The output of the two `-version` commands depends on the JDK installed on the machine; they are not part of the fixed stdout block.

## 4. `String`, Wrappers, and `enum` All Require Attention to `null`

| Selector type in Java 17 | Non-null selector | Null selector |
| --- | --- | --- |
| `String` | Matches by **content** against string labels | Throws `NullPointerException` |
| `Integer`, `Byte`, `Short`, `Character` | Wrapper value is handled per integer `switch` rules | Throws `NullPointerException` |
| `enum` | Matches enum constant name | Throws `NullPointerException` |
| `int`, `byte`, `short`, `char` | Uses primitive value | **Cannot** be null |

In the demo, `rawNumber(null)` fails because the wrapper selector has no value to unbox; `rawMode(null)` is also not "caught on its behalf" by `default`.

**Do not confuse `default` with `case null`.** In Java 17 compiled normally (without preview enabled), do not write `case null -> ...` for switch under standard syntax. Examples of `case null` in newer Java documentation belong to **pattern matching for switch**, standardized in Java 21; Java 17 only has related features in preview requiring special configuration, **not applicable to this standard CLI exercise**.

## 5. When Is `default` Needed?

`default` is for **type-valid values that do not match any case**:

~~~java
String code = "MAYBE";
String result = switch (code) {
    case "YES" -> "accepted";
    case "NO" -> "rejected";
    default -> "unrecognized";
};
~~~

With `"MAYBE"`, the result is `"unrecognized"`.

For a **switch expression**, the compiler requires cases to be covered completely (*exhaustive*). For `String` or `int`, this typically requires `default`. For an `enum`, listing all constants can avoid `default`, as in `switch(Mode)` in the program.

That exhaustiveness **does not mean accepting null**. A switch expression over an enum listing all constants still throws an error if the selector is `null`.

## 6. Choosing an Explicit Handling Policy

Three common policies:

| Policy | When `null` | When no case matches |
| --- | --- | --- |
| Return a separate result | `"missing"` | `"unknown"` |
| Reject the input | `throw IllegalArgumentException` | `throw` or `default` reports another error |
| Map to a fallback value | Only when there is a clear business convention | `default` per convention |

A short check can be written with the `?:` operator:

~~~java
String result = code == null
        ? "missing"
        : switch (code) {
            case "ON" -> "enabled";
            default -> "unknown";
        };
~~~

Because `?:` evaluates only the selected branch, if `code == null`, `switch` **is not evaluated**. However, if checking multiple conditions or needing multiple statements, a method with an `if (code == null)` guard is usually easier to read.

Do not use a "dummy value" like `""` to replace null without considering collisions with valid data: an empty string may carry its own meaning.

## 7. Common Mistakes

| Misconception | Correct understanding |
| --- | --- |
| "`default` runs when the selector is null." | False in standard Java 17 switch; throws NPE |
| "`case "ON"` compares by reference `==`." | `String` switch matches by string content |
| "A null wrapper automatically becomes 0." | Null has no value to unbox |
| "If an `enum` lists all cases, null is handled automatically." | No; a guard is still needed if it can be null |
| "`""` is the same as null." | The empty string is a non-null `String` |
| "Standard Java 17 can use `case null` like Java 21." | Not when compiled normally without preview enabled |
| "Using `default` already validates the input." | It only covers unmatched labels, not full business validation |

## 8. Self-Check Exercises

1. What happens with `switch("UNKNOWN")` that has `default`?  
   *Answer:* Runs `default` if no other case matches.
2. What happens with `switch((String) null)` that has `default` in standard Java 17?  
   *Answer:* `NullPointerException` before running default.
3. Is `String s = "";` handled by default?  
   *Answer:* Yes, if no label matches the empty string.
4. Does `Integer n = null; switch(n) {...}` treat `n` as 0?  
   *Answer:* No; throws NPE.
5. Does a switch expression listing all enum constants without default handle null?  
   *Answer:* No.
6. When missing data and unrecognized data are two distinct states, what should you do?  
   *Answer:* Check for null before switching and return separate results for the two situations.

## Checklist

- [ ] `default` handles **unmatched cases**, not `null`.
- [ ] Check for `null` before a Java 17 switch for nullable `String`, wrapper, and enum selectors.
- [ ] Distinguish switch statements from switch expressions, while remembering both require guarding against null selectors.
- [ ] Choose an explicit policy for returning results or throwing exceptions.
- [ ] Do not use `case null` in standard non-preview Java 17 examples.
- [ ] Use `default` to cover remaining values, not as a substitute for full input validation.

**Conclusion:** In standard Java 17, `default` means **"no case matched a valid, non-null selector"**, not **"all remaining cases including null"**. Check for `null` first, then use `case` and `default` to handle present values.