# Distinguishing Final Features from Preview Syntax by Version — Java 17+

## 1. Goal and the Most Important Rule

In Java, a **final/stable feature** (*final, permanent language feature*) is syntax that has been incorporated into the language specification of a release. It can be used when compiling for that version **without** `--enable-preview`.

A **preview feature** is a language capability included in a JDK release for developers to try out, but **not yet stabilized syntax** in that version. When compiling and running preview code, you must enable the options matching the **JDK in use**; preview syntax and semantics may still change before becoming final.

Examples related to **type patterns**:

~~~java
// Stable in Java 17: pattern matching for instanceof.
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

However:

~~~java
// Java 21 or later: pattern matching for switch is stable.
switch (input) {
    case String text when text.length() >= 5 -> System.out.println("LONG");
    default -> System.out.println("OTHER");
}
~~~

**The second snippet DOES NOT compile in stable Java 17**. Java 17 had pattern matching for switch in **preview**, but the Java 17 preview guard used different syntax: `case String s && condition`, **not `when`**.

**Rule:** Whenever you encounter new syntax online, verify simultaneously **(1) the JDK version**, **(2) its final/preview status in that version**, **(3) compile/run flags**, and **(4) the exact syntax for that version**.

## 2. Version Milestone Table to Know

| Feature | Status by Relevant Milestone | Remember When Learning Java 17+ |
|---|---|---|
| **Switch expressions** with `case ->` and `yield` | Final since **Java 14** | Ready to use on JDK 17, no preview needed |
| **Pattern matching for `instanceof`** | Final since **Java 16** | `o instanceof String s` is valid on JDK 17 |
| **Record classes** | Final since **Java 16** | `record Point(int x, int y) {}` differs from record *patterns* |
| **Sealed classes** | Final since **Java 17** | `sealed`/`permits` can be used on JDK 17 |
| **Pattern matching for `switch`** | Preview across **Java 17–20**; final since **Java 21** | Do not use switch type patterns as a final feature of Java 17 |
| **`when` guard in pattern switch** | Appeared in preview releases after Java 17 (Java 19/20); final with pattern switch in **Java 21** | Java 17 preview uses `&&` in guarded pattern labels, not `when` |
| **Record patterns** | Preview before Java 21; final since **Java 21** | Do not confuse `record` (final in Java 17) with record destructuring patterns |

**Important warning:** A feature can be **preview in version A** and already **final in version B**. You cannot vaguely say "pattern switch is preview" without attaching a version number.

The examples in this lesson use **Java 17** (stable and preview separately) and **Java 21** (final syntax) for comparison. If you are using a different JDK, look up the feature status in that JDK before changing commands.

## 3. Stable Features Can Compile Without Enabling Preview

The `instanceof` pattern in Java 17:

~~~java
static String explain(Object value) {
    if (value instanceof String text) {
        return "TEXT:" + text;
    }
    return "NOT_STRING";
}
~~~

With `value = "Java"`, the expression `instanceof String text` checks the type and assigns the pattern variable `text` in the flow confirmed as matched. With null or a non-String object, the expression returns false; Java does not throw NPE merely from checking `instanceof` on null.

Similarly, **switch expressions** were already final before Java 17:

~~~java
static String status(int code) {
    return switch (code) {
        case 1 -> "NEW";
        case 2 -> "RUNNING";
        default -> "UNKNOWN";
    };
}
~~~

There are no type patterns in this example: the `case 1`/`case 2` labels are **ordinary constants**. Seeing the keywords `switch`, `->`, or `yield` **does not mean** the code is using a preview feature.

## 4. Compiling Preview for the Right Version

For a program containing **Java 17** preview syntax, on **JDK 17**, use:

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PreviewSwitch17.java
java --enable-preview -cp . PreviewSwitch17
~~~

**Explanation:**

- `--enable-preview`: enables preview features for the version being compiled/run.
- `--release 17`: compiles targeting the Java 17 API/language level.
- `java --enable-preview`: required to run a class that uses preview features.
- For preview, standard `javac` **only allows enabling preview for the compiler's own JDK version**. Do not use JDK 21 to try enabling Java 17 preview with `--release 17`.
- A class compiled with preview carries a corresponding class-file marker; **do not treat** it as a stable Java 17 class that can run arbitrarily on other JDKs.

For **stable Java 17 code**:

~~~bash
javac --release 17 -encoding UTF-8 StablePatterns17.java
java -cp . StablePatterns17
~~~

No preview needed. For **Java 21 code using finalized pattern switch**:

~~~bash
javac --release 21 -encoding UTF-8 FinalSwitch21.java
java -cp . FinalSwitch21
~~~

`--enable-preview` is not needed when using standard Java 21 pattern switch features.

**Avoid this misconception:** The preview flag **does not turn** Java 21 `when` syntax into valid syntax on Java 17. The flag only unlocks preview features **actually present in that version**.

## 5. Java 17 Preview: Guarded Patterns Use `&&`

Guarded pattern syntax in JEP 406 (Java 17 preview) can be written as:

~~~java
// Valid only when using JDK 17 with --enable-preview:
return switch (value) {
    case String text && text.length() >= 5 -> "LONG";
    case String text -> "SHORT";
    default -> "OTHER";
};
~~~

- The selector must have an appropriate type, here `Object`.
- The `String text` part is the **type pattern**.
- The guard `&& text.length() >= 5` is **Java 17 preview** syntax, evaluated after the `String` pattern matches.
- If the guard is false, the switch tries the next label.
- The unguarded String pattern is placed **after** the guarded label so it does not shadow the specific label.

Do not write `case String text when ...` in a Java 17 file and simply add `--enable-preview`: **`when` is not Java 17 preview syntax**.

## 6. Java 21 Final: Guarded Patterns Use `when`

On JDK 21, express the corresponding logic with:

~~~java
return switch (value) {
    case null -> "NULL";
    case String text when text.length() >= 5 -> "LONG";
    case String text -> "SHORT";
    default -> "OTHER";
};
~~~

For the same String value, the type branches and guards determine the result just like the Java 17 preview example. However, Java 21 uses `when` to separate the type pattern from the guard condition.

| Intent | Java 17 Preview | Java 21 Final |
|---|---|---|
| Select a String of length at least 5 | `case String s && s.length() >= 5 ->` | `case String s when s.length() >= 5 ->` |
| Select any remaining String | `case String s ->` | `case String s ->` |
| Handle null | Better guarded outside per Java 17 contract | Can use `case null ->` |

**Note:** Java 21 code may also require sufficient branches for a switch expression to produce a result. With an Object selector, `default` is one way to handle values that do not match the listed patterns.

## 7. What Does Not Change Across Versions?

Even though Java 17 preview writes guarded labels with `&&` and Java 21 final uses `when`, a guard is evaluated only **after** the type pattern matches. If the guard is false, the switch tries the next label; if multiple labels match, the earlier label is selected. Pattern variables are only valid in the branch and guard where the type has been confirmed.

Order also relates to **dominance**: placing `case CharSequence cs` before `case String s` makes the String label unreachable; similarly, an unguarded `String` label can shadow a guarded String label placed after it. Changing syntax versions does not fix wrong ordering. In stable Java 17, an `if (value instanceof String s && ...)` chain expresses guards without dominance checking between `if` branches.

## 8. When Should You Use Preview?

**Prefer stable code** if:

- The project must compile on Java 17 using a standard `javac --release 17` command.
- You are writing libraries or lessons for multiple different JDK environments.
- You want to avoid depending on syntax that might change.
- Your build system, CI, IDE, and runtime do not yet guarantee the exact same version and preview flags.

**Only consider preview** when genuinely exploring a new feature on the exact right version, accepting deployment constraints, and controlling the entire toolchain. For lessons on guarded pattern switches:

- **JDK 17:** using stable `instanceof` patterns + `if`/`&&` is the safe choice.
- **JDK 17 preview:** you can try guards with `&&`, but preview must be enabled for both compile and run.
- **JDK 21 or later:** you can use final `when` under JDK 21 semantics.

Do not change target language levels or upgrade the JDK merely because an example online looks shorter; consider the project's compatibility policy.

## 9. Checking Your Environment and Common Errors

First open a terminal:

~~~bash
java -version
javac -version
~~~

These two commands show the **runtime** and **compiler** being invoked from PATH. On a machine with multiple JDKs, they can accidentally point to different versions; select the right JDK via `JAVA_HOME`, PATH, or IDE/build tool settings.

| Symptom | Common Cause | Resolution |
|---|---|---|
| `case String s when ...` syntax error on Java 17 | `when` is not valid syntax in this version | Use Java 17 `instanceof` or JDK 21 |
| Java 17 pattern switch reports preview disabled | `--enable-preview` was not enabled | Enable preview for both compile and run on JDK 17 |
| Java says `--enable-preview` is needed when running a preview class | Runtime does not allow preview | Run `java --enable-preview ...` on the matching JDK |
| Using JDK 21 with `--enable-preview --release 17` | Preview applies only to the compiler's own release | Use JDK 17 to test preview 17; or switch to final 21 syntax |
| Compiling Java 21 source with `--release 17` | Target Java 17 does not know Java 21 features | Write 17-compatible code or intentionally update the target |
| Treating `record` and record patterns as the same feature | `record` became final before record patterns | Separate feature milestones by JEP/version |
| Mistaking `instanceof String s` for Java 17 preview | Pattern instanceof has been final since 16 | Remove unnecessary preview flags |
| Mistaking `switch (int)` with `case ->` for preview | Switch expressions/rules became final before Java 17 | Distinguish constant cases from type patterns |
| Using `case null` casually on stable Java 17 switch | Differs from JDK 21 capabilities and semantics | Guard null with `if` beforehand |
| Broad String pattern placed before guarded pattern | Later label is dominated | Specific/guarded labels before general labels |
| IDE reports an error while CLI succeeds, or vice versa | Mismatched language level/JDK/preview flags | Align project SDK, compiler, runtime, and flags |

**Compatibility note:** `--release 17` asks the compiler to target Java 17 and its standard APIs; it is **not** a promise that newer preview syntax will be "backported" to Java 17.

## 10. Program 1 — Stable Java 17, No Preview

Create a file **`StablePatterns17.java`**:

~~~java
import java.util.Locale;

public final class StablePatterns17 {
    private StablePatterns17() {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "TEXT:" + text.strip().toUpperCase(Locale.ROOT);
        }
        if (value instanceof String) {
            return "BLANK_TEXT";
        }
        if (value instanceof Integer number) {
            return "INTEGER:" + number;
        }
        if (value == null) {
            return "NULL";
        }
        return "OTHER";
    }

    static String status(int code) {
        return switch (code) {
            case 1 -> "NEW";
            case 2 -> "RUNNING";
            default -> "UNKNOWN";
        };
    }

    public static void main(String[] args) {
        System.out.println("stable17 text=" + describe(" Java "));
        System.out.println("stable17 blank=" + describe("   "));
        System.out.println("stable17 int=" + describe(Integer.valueOf(7)));
        System.out.println("stable17 null=" + describe(null));
        System.out.println("stable17 other=" + describe(Boolean.TRUE));
        System.out.println("stable17 switch=" + status(2));
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 StablePatterns17.java
java -cp . StablePatterns17
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\StablePatterns17.java
java -cp . StablePatterns17
~~~

**Exact expected stdout:**

~~~text
stable17 text=TEXT:JAVA
stable17 blank=BLANK_TEXT
stable17 int=INTEGER:7
stable17 null=NULL
stable17 other=OTHER
stable17 switch=RUNNING
~~~

Here both `instanceof` patterns and switch expressions are **stable in Java 17**, so preview is not enabled.

## 11. Program 2 — Preview Switch Patterns on Exact JDK 17

Create a file **`PreviewSwitch17.java`**, using JEP 406 preview without `when`:

~~~java
public final class PreviewSwitch17 {
    private PreviewSwitch17() {}

    static String classify(Object value) {
        return switch (value) {
            case String text && text.isBlank() -> "BLANK";
            case String text && text.length() >= 5 -> "LONG";
            case String text -> "SHORT";
            case Integer number -> "INTEGER:" + number;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("preview17 blank=" + classify("  "));
        System.out.println("preview17 long=" + classify("World"));
        System.out.println("preview17 short=" + classify("Go"));
        System.out.println("preview17 int=" + classify(7));
        System.out.println("preview17 other=" + classify(Boolean.TRUE));
    }
}
~~~

**Bash (Linux/macOS), JDK 17 required:**

~~~bash
javac --enable-preview --release 17 -encoding UTF-8 PreviewSwitch17.java
java --enable-preview -cp . PreviewSwitch17
~~~

**PowerShell (Windows), JDK 17 required:**

~~~powershell
javac --enable-preview --release 17 -encoding UTF-8 .\PreviewSwitch17.java
java --enable-preview -cp . PreviewSwitch17
~~~

**Exact expected stdout of the program:**

~~~text
preview17 blank=BLANK
preview17 long=LONG
preview17 short=SHORT
preview17 int=INTEGER:7
preview17 other=OTHER
~~~

**Note on compiler output:** JDK 17 may print additional **preview notices** to stderr during compilation; the expected stdout above is **only the program's output**. Do not alter the commands to suppress those notices.

Because `classify(null)` is not called, there is no null-handling branch in this demo program. If null needs to be accepted, check it **before the switch** per the API contract, rather than assuming `default` catches every value.

## 12. Program 3 — Final `when` Syntax on JDK 21+

Create a file **`FinalSwitch21.java`**:

~~~java
public final class FinalSwitch21 {
    private FinalSwitch21() {}

    static String classify(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String text when text.isBlank() -> "BLANK";
            case String text when text.length() >= 5 -> "LONG";
            case String text -> "SHORT";
            case Integer number -> "INTEGER:" + number;
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println("final21 null=" + classify(null));
        System.out.println("final21 blank=" + classify("  "));
        System.out.println("final21 long=" + classify("World"));
        System.out.println("final21 short=" + classify("Go"));
        System.out.println("final21 int=" + classify(7));
        System.out.println("final21 other=" + classify(Boolean.TRUE));
    }
}
~~~

**Bash (Linux/macOS), JDK 21+:**

~~~bash
javac --release 21 -encoding UTF-8 FinalSwitch21.java
java -cp . FinalSwitch21
~~~

**PowerShell (Windows), JDK 21+:**

~~~powershell
javac --release 21 -encoding UTF-8 .\FinalSwitch21.java
java -cp . FinalSwitch21
~~~

**Exact expected stdout:**

~~~text
final21 null=NULL
final21 blank=BLANK
final21 long=LONG
final21 short=SHORT
final21 int=INTEGER:7
final21 other=OTHER
~~~

This is a **final feature since Java 21**, so **do not use** `--enable-preview` for pattern matching for switch in this program.

## 13. How to Read the Differences Among the Three Examples

| Criterion | `StablePatterns17.java` | `PreviewSwitch17.java` | `FinalSwitch21.java` |
|---|---|---|---|
| JDK to compile | 17+ with target 17 | **Exact JDK 17** | 21+ with target 21 |
| `--enable-preview` | No | **Yes: compile and run** | No |
| Pattern matching for `instanceof` | Yes | Not needed separately | Not needed separately |
| Pattern matching for `switch` | No | **Preview** | **Final** |
| Guard syntax | `instanceof T t && ...` in `if` | `case T t && ...` | `case T t when ...` |
| `null` handling | `if (value == null)` | Guard before switch if needed | `case null` can be used |
| Purpose | Compatible Java 17 code | Experimenting with 2021 preview syntax | Stable modern switch pattern code |

The same type-classification requirement can be written in multiple ways; **no form may be "copied" across JDK versions while ignoring the version**.

## 14. Traps to Remember

1. **Final does not mean the feature already existed in older JDKs:** Java 21 final syntax is still invalid when targeting Java 17.
2. **Preview is not immutable syntax:** Java 17 preview's `&&` guard differs from Java 21's `when`.
3. **A file using preview can produce a class that does not run normally:** it requires the runtime flag and matching JDK.
4. **`case ->` is not automatically preview:** switch rules and switch expressions became final before Java 17.
5. **A valid Java 17 `record` does not imply record patterns are also final in Java 17.**
6. **Do not confuse warnings with program errors:** the compiler may warn about preview while the program still runs with the right flags.
7. **Do not assume `default` always catches null** in pattern switch: handle null explicitly according to version and syntax.
8. **Label order is semantics:** a false guard tries other cases, whereas an unguarded broad pattern before a narrower pattern can trigger a compiler dominance error.
9. **Do not force preview in production code** just to save a few lines when the stable release already offers a clear solution.
10. **Align IDE, build, and CLI:** differing language level options can cause the same file to compile in one place and fail in another.

## 15. Exercises with Answers

### Exercise A — Which syntax runs stably on Java 17?

~~~java
Object obj = "Java";
if (obj instanceof String s) {
    System.out.println(s.length());
}
~~~

**Answer:** Runs stably on JDK 17 and prints `4`. `instanceof` patterns have been final since Java 16; no preview needed.

### Exercise B — Fixing a version mismatch

~~~java
// Learner using JDK 17:
// case String s when s.isBlank() -> "BLANK"
~~~

**Answer:** Java 17 **does not support `when`**. You can use `if (obj instanceof String s && s.isBlank())` without preview. If intentionally studying Java 17 preview, use `case String s && s.isBlank() -> ...` and enable `--enable-preview` on JDK 17. If you want final `when`, JDK 21+ and target 21 or higher are required.

### Exercise C — Which command enables Java 17 preview?

~~~text
A. javac --release 17 PreviewSwitch17.java
B. javac --enable-preview --release 17 PreviewSwitch17.java
C. javac --enable-preview --release 21 PreviewSwitch17.java
~~~

**Answer:** **B**, when using **JDK 17**. After compiling, run `java --enable-preview -cp . PreviewSwitch17` on JDK 17. Option C is not how you request "Java 17 preview".

### Exercise D — Dominance and label order

~~~java
// JDK 21, WRONG order snippet:
switch (obj) {
    case CharSequence sequence -> System.out.println("SEQUENCE");
    case String text -> System.out.println("STRING");
    default -> System.out.println("OTHER");
}
~~~

**Answer:** `String` is a `CharSequence`, so the later String label is completely shadowed; fix by **placing `case String text` before `case CharSequence sequence`**.

### Exercise E — Does a finalized feature need preview?

A JDK 21 file uses only `case String s when s.length() > 3 -> ...` in finalized pattern switch. Is `--enable-preview` needed?

**Answer:** **No**. Use `javac --release 21 ...` and `java ...` on JDK 21. Preview is needed only when using a **different feature** that is not yet stable in that specific JDK.

## 16. Checklist and Conclusion

- [ ] Always tie final/preview statements to a **Java version number**.
- [ ] Know that `instanceof` patterns became final in Java 16 and are stable in Java 17.
- [ ] Know that switch expressions `->`/`yield` became final in Java 14.
- [ ] Know that pattern matching for switch was preview in Java 17–20 and final since Java 21.
- [ ] Know that Java 17 switch preview uses the `&&` guard; Java 21 final uses `when`.
- [ ] Know that `--enable-preview` must be enabled at **compile and run** if a class uses Java 17 preview.
- [ ] Do not try asking a newer JDK to enable an older release's preview.
- [ ] Know how to check `java -version`, `javac -version`, and the `--release` flag.
- [ ] Distinguish already-final record classes from record patterns finalized later.
- [ ] Understand that a guard runs only when the type pattern matches and case order can change results.
- [ ] Understand dominance and null handling in switch patterns by version.
- [ ] Run `StablePatterns17.java`, `PreviewSwitch17.java`, and `FinalSwitch21.java` on the corresponding JDKs and verify expected stdout.

**Conclusion:** A syntax feature in Java can be **preview in an earlier release and stable in a later one**, while **changing syntax** as it matures. For type patterns, Java 17 uses stable `instanceof` patterns; Java 17's pattern switch is preview with `&&` guards, whereas Java 21 finalized pattern switch with `when` guards. To learn or deploy properly, always check **version, syntax, status, and compile/run flags** before use.
