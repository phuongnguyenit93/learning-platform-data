# Why Is the Number of `char`s Not Always Equal to User-Perceived Characters?

A “delete character” button, a counter inside a name input field, and a 30-character preview typically must work with **user-perceived character clusters**, whereas Java's `String.length()` only returns the number of **UTF-16 code units**. This lesson turns that difference into a testable text-handling policy for production.

## 1. One Limit, Multiple Interpretations

Consider three inputs:

- `😊`: 2 `char`s, yet 1 code point and typically 1 display cluster because non-BMP emojis are encoded in UTF-16 as a surrogate pair.
- `e\u0301`: 2 `char`s, 2 code points, yet typically 1 cluster because the combining mark attaches to the base letter.
- `👩‍💻`: 5 `char`s, 3 code points, yet 1 extended grapheme cluster thanks to a ZWJ sequence.

Therefore, replacing `length()` with `codePointCount()` only solves the surrogate pair case; you can still slice between components of the same emoji or between a letter and its accent. When operating on individual displayed characters, you need **grapheme boundaries**.

An extended grapheme cluster under Unicode Standard Annex #29 is the segmentation unit closest to user expectations. It is **not synonymous** with a glyph, a terminal cell, or a pixel width. A font may fail to join a ZWJ emoji into one icon, and complex scripts are also affected by shaping and text layout.

## 2. Specify Input Rules Before Writing Code

Suppose a form has two constraints: at most **6 grapheme clusters** for a short label and at most **18 UTF-8 bytes** for the payload. We need to answer separately:

| Question | Product rule |
| --- | --- |
| What is “one character”? | One extended grapheme cluster per Unicode segmentation |
| What is the server limit? | Both the grapheme count and UTF-8 byte count must be satisfied |
| Should Unicode be normalized before counting? | Whether to normalize or not must be decided by the API contract; the example below **keeps the input as-is** |
| How are unpaired surrogates handled? | Rejected because the input is not well-formed UTF-16 |
| When over the limit? | Keep the longest prefix containing complete clusters that does not exceed the byte limit |
| Cross-platform consistency? | Test client and server on a sample string suite, pinning/controlling the Unicode version when needed |

Note: **truncating for a preview** and **validating data for storage** can differ. For account names, silent truncation can cause data loss or name collisions; return an explicit error instead of silently truncating. For previews, taking a cluster-complete prefix is usually the right choice.

## 3. Finding Grapheme Boundaries in Java

Java 17+ supports `Pattern.compile("\\X")` to match each extended grapheme cluster. `Matcher.find()` steps through clusters in order; `Matcher.end()` returns the **UTF-16 offset** right after the matched cluster. You can use this offset in `substring(0, end)` without manually adding up emoji lengths.

When there is also a byte limit, each **well-formed** UTF-16 cluster can be encoded to UTF-8 and its bytes summed to decide whether to accept that cluster. Never slice at an arbitrary byte count, as that can cut inside a code point's UTF-8 byte sequence.

### Complete Example: Preview Satisfying Both Cluster Count and Byte Count

File `GraphemePreviewPolicy.java`, JDK 17+:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemePreviewPolicy {
    private static final Pattern CLUSTER = Pattern.compile("\\X");

    static String preview(String text, int maxClusters, int maxUtf8Bytes) {
        if (text == null) {
            throw new IllegalArgumentException("text is null");
        }
        if (maxClusters < 0 || maxUtf8Bytes < 0) {
            throw new IllegalArgumentException("negative limit");
        }

        // Java codePoints() can emit unpaired surrogates; reject before encoding.
        if (text.codePoints().anyMatch(
                cp -> cp >= 0xD800 && cp <= 0xDFFF)) {
            throw new IllegalArgumentException("unpaired surrogate");
        }

        Matcher matcher = CLUSTER.matcher(text);
        int usedBytes = 0;
        int endUtf16 = 0;
        int usedClusters = 0;

        while (usedClusters < maxClusters && matcher.find()) {
            int clusterBytes = matcher.group()
                    .getBytes(StandardCharsets.UTF_8).length;

            if (clusterBytes > maxUtf8Bytes - usedBytes) {
                break;
            }

            usedBytes += clusterBytes;
            usedClusters++;
            endUtf16 = matcher.end();
        }
        return text.substring(0, endUtf16);
    }

    public static void main(String[] args) {
        String text = "Vi\u1EC7t \uD83D\uDC69\u200D\uD83D\uDCBB!";

        System.out.println(preview(text, 6, 18)
                .equals("Vi\u1EC7t \uD83D\uDC69\u200D\uD83D\uDCBB"));
        System.out.println(preview(text, 6, 17).equals("Vi\u1EC7t "));
        System.out.println(preview(text, 5, 50).equals("Vi\u1EC7t "));
        System.out.println(preview(text, 0, 50).isEmpty());
        System.out.println(preview("\uD83D\uDC69\u200D\uD83D\uDCBB", 1, 10)
                .isEmpty());
    }
}
~~~

~~~bash
javac -encoding UTF-8 GraphemePreviewPolicy.java
java GraphemePreviewPolicy
~~~

Stdout:

~~~text
true
true
true
true
true
~~~

“Việt ” contains **5 clusters and 7 UTF-8 bytes**; `👩‍💻` is the sixth cluster, adding **11 bytes**, fitting the 18-byte limit exactly. With a 17-byte budget, the program must stop **before the entire emoji**. You must not take only the woman emoji and drop the ZWJ and laptop to fit the byte limit, as that changes the icon's meaning.

This example encodes each cluster into a temporary byte array; for short labels, this approach is simple and easy to verify. When processing very long texts or running at high frequency, you can optimize with an incremental encoder and measure performance. The algorithm preserves graphemes only according to **the rules supported by the current JDK**; it does not guarantee identical rendering across every platform.

## 4. Practical Testing Across Diverse Text Types

| Sample input | Easy-to-miss trap | Test to include |
| --- | --- | --- |
| `A😀B` | UTF-16 offset of B is 3 | Do not split between high and low surrogates |
| `e\u0301` and `\u00E9` | Two different code point sequences | Same cluster, yet `equals()` is not necessarily true |
| `Vi\u1EC7t` and NFD form | Vietnamese diacritics are decomposed | Count clusters per rules, bytes per actual representation |
| `🇻🇳` | Two regional indicators form a flag | Do not slice only the first regional indicator |
| `👍🏽` | Base emoji + skin tone | Do not split off the modifier |
| `👩‍💻` | Emoji + ZWJ + emoji | Do not split the joined sequence into separate icons |
| Standalone high surrogate | `String` can still be constructed, yet UTF-16 is invalid | Report an error instead of silently replacing bytes |
| Text with control characters | Grapheme count is not an allowlist rule for content | Additionally check allowed-character policy |

Add tests right at **exact boundaries**: limit 0, exact fit, 1 byte short, 1 cluster fewer, and empty strings. If the client uses JavaScript and the server uses Java, test with concrete Unicode strings instead of assuming both runtimes always segment identically. For Vietnamese input methods (IMEs), consider **in-progress composition state** before enforcing immediate limits, so users are not blocked from finishing diacritics.

## 5. Normalization, Cursors, and Text Editing

`Normalizer.normalize(text, Normalizer.Form.NFC)` can make canonically equivalent sequences consistent when comparing or searching, yet **changes code units and offsets**. If you save a cursor position before normalization and reuse the old offset after normalization, the position can be wrong. Therefore, define the order clearly: receive input, normalize (if the contract requires it), compute limits, store data, and update cursor position.

Interactive text editors also need to account for selections, Backspace/Delete keys, bidirectional text, IMEs, and shaping rules. `\\X` provides **cluster boundaries**, not a complete text editor on its own. Nor is a grapheme cluster a terminal column-count unit; text alignment still requires an appropriate width-measuring tool.

## 6. Decision Checklist

Before using `length()` as “character count”, identify the goal: UTF-16 `String` indexing, per-code-point processing, grapheme-based limits, byte limits, or UI width. Then select the corresponding API and test at least three case classes: **surrogate pairs**, **combining marks**, and **multi-code-point emojis**. If strict Unicode storage is required, check for unpaired surrogates before encoding.

### Self-Check

1. What is `"👩‍💻".length()`? **5**, even though it is one cluster under rules supporting that sequence.
2. What is `"e\u0301".codePointCount(0, 2)`? **2**, while the grapheme count is typically **1**.
3. An emoji cluster needs 11 UTF-8 bytes, but only 10 bytes remain in the budget: can you take half of the cluster? **No**, under the defined preview policy.
4. Does counting by graphemes automatically limit byte count or measure pixel width? **No**; these are three independent measurements.
5. Why should you test the same sample suite on both client and server? Because Unicode rules and segmentation data versions can differ across runtimes.

Technical references: [Unicode Text Segmentation — UAX #29](https://www.unicode.org/reports/tr29/), [Java `Pattern`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).