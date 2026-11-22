# `String.split(regex, limit)`: positive, zero, and negative

The `limit` parameter answers two questions: **how the number of resulting parts is bounded** and **whether trailing empty elements are discarded**. For example, the first `=` sign may separate a key from a value that contains additional `=` signs; tabular data, on the other hand, needs to preserve trailing empty fields.

## 1. Three splitting modes

| `limit` | Rule | Trailing empty elements |
| --- | --- | --- |
| Positive `n` | Applies the regex at most `n-1` times; result has **at most `n` elements** | Kept if already produced |
| `0` | Splits as many times as possible | Discards **all** trailing empty elements |
| Negative (usually `-1`) | Splits as many times as possible | Keeps trailing empty elements |

`split(regex)` is synonymous with `split(regex, 0)`. Negative values `-1` and `-5` follow the same rule; a negative number does not mean splitting right-to-left. `limit=1` performs no splits and returns the entire string in a single element.

Consider `String s = "a:b::";`:

| Call | Result contents | `length` |
| --- | --- | --- |
| `s.split(":", 1)` | `["a:b::"]` | 1 |
| `s.split(":", 2)` | `["a", "b::"]` | 2 |
| `s.split(":", 3)` | `["a", "b", ":"]` | 3 |
| `s.split(":", 4)` | `["a", "b", "", ""]` | 4 |
| `s.split(":", 10)` | `["a", "b", "", ""]` | 4 |
| `s.split(":", 0)` | `["a", "b"]` | 2 |
| `s.split(":", -1)` | `["a", "b", "", ""]` | 4 |

With `limit=3`, there are only two cuts. The trailing `":"` is the **unsplit remainder**, not a delimiter character that was overlooked. `limit=10` only sets an upper cap; it does not insert six extra empty parts.

## 2. Java 17+ program verifying every branch

Save as `SplitLimitDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class SplitLimitDemo {
    static void show(String label, String[] parts) {
        String visible = Arrays.stream(parts)
                .map(s -> "\"" + s + "\"")
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " len=" + parts.length + " " + visible);
    }

    public static void main(String[] args) {
        String text = "a:b::";
        show("limit=1", text.split(":", 1));
        show("limit=2", text.split(":", 2));
        show("limit=3", text.split(":", 3));
        show("limit=4", text.split(":", 4));
        show("limit=0", text.split(":", 0));
        show("limit=-1", text.split(":", -1));

        show("empty", "".split(":", 0));
        show("delimiter only", ":".split(":", 0));
        show("key/value", "host=a=b".split("=", 2));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SplitLimitDemo.java
java SplitLimitDemo
```

```text
limit=1 len=1 ["a:b::"]
limit=2 len=2 ["a", "b::"]
limit=3 len=3 ["a", "b", ":"]
limit=4 len=4 ["a", "b", "", ""]
limit=0 len=2 ["a", "b"]
limit=-1 len=4 ["a", "b", "", ""]
empty len=1 [""]
delimiter only len=0 []
key/value len=2 ["host", "a=b"]
```

The `show` method intentionally prints `length` and wraps tokens in quotes. By default, `Arrays.toString` makes it hard to distinguish a zero-element array from an array containing a single empty string.

Two edge cases: `"".split(":", 0)` has **one** element `""` because the regex finds no `:` at all; `":".split(":", 0)` produces only empty segments and they are all stripped at the end, so it has **0** elements.

## 3. Application: splitting key/value only once

`limit=2` is usually the right choice when the delimiter is only meaningful at its first occurrence:

```java
String line = "endpoint=https://example.org?q=a=b";
String[] pair = line.split("=", 2);
// ["endpoint", "https://example.org?q=a=b"]
```

If you use `split("=")`, the value gets broken up at the `=` signs inside it. For `"enabled="`, `split("=", 2)` returns `["enabled", ""]`, whereas the default only returns `["enabled"]` because it drops the trailing empty field. Check `pair.length == 2` before accessing `pair[1]`: an input without `=` yields a single-element array.

`limit=2` also applies to config entries like `"level:WARN:retry-later"` where the first `:` separates the key from the entire remaining message.

## 4. Keeping trailing empty parts and `limit` limitations

`"A,B,,".split(",")` only yields `["A", "B"]`; `split(",", -1)` returns all `["A", "B", "", ""]`. Even with `limit=0`, **middle** empty elements in `"A,,B"` and **leading** empty elements in `",A,B"` are still kept if the delimiter matches positive length. The lesson on trailing empty fields uses these cases for schema validation and data reconstruction.

Additional distinctions to note:

- A **zero-width** regex match right at the start of the string does not create a leading empty element; this rule is different from discarding **trailing** empty elements under `limit=0`.
- `limit` does not turn a regex into a literal delimiter. A dot still needs `"\\."` or `Pattern.quote(".")`.
- `stream.limit(n)` after `Pattern.splitAsStream` only takes at most `n` tokens, whereas `split(input, n)` puts **the entire remainder** into the last element.
- No `limit` value replaces a CSV parser that handles quotes.

## 5. Self-check

1. Does `"user=hello=world".split("=", 2)` keep the second `=` sign?
2. What is the third element of `"x:y::".split(":", 3)`?
3. How do `"x:y::".split(":", 0)` and `split(":", -1)` differ?
4. Does `"a:b".split(":", 10)` have exactly ten elements?
5. Does `"a,b".split(":", 0)` return an empty array when there is no `:`?

**Answers:** (1) Yes, inside `"hello=world"`. (2) `":"`. (3) A two-element array versus a four-element array with two trailing empty strings. (4) No, two elements. (5) No, one element `"a,b"`.

**Remember:** `limit>0` is a cap on **the number of parts**, `0` removes trailing empty strings, and negative values keep them.