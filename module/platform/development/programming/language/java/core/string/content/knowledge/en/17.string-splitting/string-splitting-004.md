# Leading, consecutive, and trailing delimiters

When a delimiter is treated as a **boundary between fields**, its position determines whether empty elements appear. `",a,b"` has a leading empty part; `"a,,b"` has a middle empty part; `"a,b,"` has a trailing empty part if you choose to keep it.

## 1. Observing every position

| Input | `split(",")` | `split(",", -1)` |
| --- | --- | --- |
| `",a,b"` | `["", "a", "b"]` | `["", "a", "b"]` |
| `"a,,b"` | `["a", "", "b"]` | `["a", "", "b"]` |
| `"a,b,,"` | `["a", "b"]` | `["a", "b", "", ""]` |
| `",,a,,"` | `["", "", "a"]` | `["", "", "a", "", ""]` |
| `",,"` | Array of length 0 | Three `""` elements |
| `""` | One `""` element | One `""` element |

**Start of string:** a regex matching a **positive-length** segment at index 0 produces an empty element before it. A regex with a **zero-width** match at index 0 does not produce a leading empty element; the next lesson explains this explicitly with lookahead/anchors.

**Middle of string:** each comma matches individually, so two adjacent commas create an empty gap `""` between them. Removing middle empty elements can shift data columns out of alignment.

**End of string:** the default `limit=0` drops all trailing empty elements; `limit=-1` preserves them. The **trailing** empty rule differs from the **leading** zero-width match rule.

## 2. Each delimiter individually or collapsed as a group?

To see the difference between `","` and `",+"`, save `SplitBoundariesDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class SplitBoundariesDemo {
    private static void show(String label, String[] parts) {
        String visible = Arrays.stream(parts)
                .map(s -> "'" + s + "'")
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " n=" + parts.length + " " + visible);
    }

    public static void main(String[] args) {
        String input = ",a,,b,";
        show("individual", input.split(",", -1));
        show("default", input.split(","));
        show("grouped", input.split(",+", -1));
        show("first only", input.split(",", 2));
        show("zero width", "abc".split("(?=a)", -1));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SplitBoundariesDemo.java
java SplitBoundariesDemo
```

```text
individual n=5 ['', 'a', '', 'b', '']
default n=4 ['', 'a', '', 'b']
grouped n=4 ['', 'a', 'b', '']
first only n=2 ['', 'a,,b,']
zero width n=1 ['abc']
```

`","` treats **each** comma as a delimiter; `",+"` treats a **run of consecutive commas** as one match. For `",a,,b,"`, collapsing the group loses the middle empty field. Only use `+` if multiple consecutive delimiters **truly represent a single separator**.

For example, `"  red   green  ".split("\\s+")` treats multiple consecutive whitespace characters as one boundary. Because leading spaces produce a positive-length match at the start, a leading empty string can still appear; `limit=0` only removes trailing empty strings. Calling `strip()` before splitting is appropriate if the business rules allow stripping outer whitespace, but not for formats that require preserving spaces.

## 3. When the regex boundary is not a single character

- `"[,;]"` matches each comma or semicolon; `"[,;]+"` collapses runs of either character.
- `"::"` matches exactly two colons; `":+"` matches one or more colons.
- `Pattern.quote(delimiter)` is used when the delimiter character, such as `"."` or `"|"`, must be interpreted literally.
- With the lookahead `"(?=:)"`, the regex only matches the **position** before `:` without consuming characters. Then `:` remains inside the token; you cannot apply the character-consuming comma table above directly.

A fixed-column format usually requires each individual delimiter; a list of words separated by varying whitespace usually requires collapsing runs. **The data specification** determines the regex choice.

## Self-check

1. How many leading empty elements does `",,x".split(",", -1)` have?
2. Why does `"x,,y".split(",+", -1)` have fewer parts than `split(",", -1)`?
3. Should you always call `strip()` before `split("\\s+")`?
4. Does calling `split(",")` and filtering out **all** empty strings accurately simulate `limit=0`?

**Answers:** (1) Two. (2) `,+` collapses the two commas into one boundary, producing no middle field. (3) Only when outer whitespace is not data. (4) No; `limit=0` only removes trailing empty strings, not leading or middle ones.

**Remember:** Determine whether **each delimiter is an independent boundary** or **multiple delimiters merge into a single boundary**.