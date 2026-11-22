# Giới hạn cắt hoặc đảo chuỗi theo chỉ số char trong Java

## 1. Vấn đề: một ký tự người dùng nhìn thấy không nhất thiết bằng một `char`

Trong ứng dụng đa ngôn ngữ, thao tác cắt chuỗi để tạo preview, giới hạn tên hiển thị, đảo chuỗi hoặc lấy "n ký tự đầu tiên" rất dễ tạo lỗi nếu giả định **một ký tự = một `char` Java**.

Ví dụ chuỗi:

```text
A🌍B
```

Trông như ba ký tự: `A`, biểu tượng Trái Đất `🌍` và `B`. Nhưng Java sử dụng **UTF-16** trong API `String`; ký tự `🌍` (U+1F30D) cần **hai UTF-16 code units**, nên:

```text
String.length()              = 4
String.codePointCount(...)   = 3
Số cụm ký tự hiển thị ở ví dụ = 3
```

Nếu gọi `substring(0, 2)`, phép cắt sẽ giữ `A` và **một nửa cặp surrogate** của emoji, sinh chuỗi UTF-16 không hợp lệ theo nghĩa không còn ghép cặp đầy đủ. Nếu gọi một vòng lặp đổi chỗ từng `char` khi đảo chuỗi, có thể hoán đổi high/low surrogate và làm hỏng ký tự ngoài BMP.

Tuy nhiên, **chuyển từ `char` sang Unicode code point vẫn chưa đủ cho mọi thao tác giao diện**: chữ `é` có thể gồm `e` + dấu sắc kết hợp, còn một emoji như `👩‍💻` gồm nhiều code point ghép bởi ZERO WIDTH JOINER (ZWJ). Người dùng thường coi toàn bộ cụm đó là **một ký tự hiển thị (grapheme cluster)**.

### Mục tiêu

Sau bài học, bạn sẽ:

- Phân biệt rõ **UTF-16 code unit**, **Unicode code point** và **extended grapheme cluster**.
- Hiểu tại sao `String.length()`, `charAt()`, `substring()` và `StringBuilder.reverse()` có các giới hạn khác nhau.
- Cắt theo **số code point** bằng `offsetByCodePoints` mà không tách cặp surrogate hợp lệ.
- Cắt hoặc đảo theo **cụm ký tự hiển thị** bằng `java.util.regex.Pattern` với `\X` trên Java 17+.
- Biết giới hạn phụ thuộc JDK của `java.text.BreakIterator` và các trường hợp emoji, dấu tổ hợp, lá cờ, skin tone.
- Tách việc **xử lý chuỗi Unicode** khỏi việc **đảo thứ tự hiển thị của ngôn ngữ viết từ phải sang trái**.
- Thiết kế kiểm thử và chính sách lưu trữ/validation rõ ràng cho ứng dụng localization.

## 2. Ba đơn vị đếm khác nhau

| Đơn vị | Định nghĩa | API liên quan | Dùng cho |
| --- | --- | --- | --- |
| **UTF-16 code unit** | Một đơn vị 16 bit, kiểu `char` Java | `length()`, `charAt(i)`, `substring(begin,end)` | Chỉ số bộ nhớ/vị trí trong `String`, API Java |
| **Unicode code point** | Giá trị ký tự Unicode từ U+0000 đến U+10FFFF | `codePointAt(i)`, `codePoints()`, `codePointCount(...)`, `offsetByCodePoints(...)` | Duyệt ký tự Unicode, phân loại code point, cắt không tách surrogate |
| **Extended grapheme cluster (EGC)** | Một chuỗi code point được coi là đơn vị ký tự gần với nhận thức của người dùng theo quy tắc Unicode UAX #29 | Regex `\X`, grapheme boundary; `BreakIterator` ở các JDK mới | UI cursor, truncate theo ký tự hiển thị, đảo các cụm không xé emoji |

Ví dụ:

| Chuỗi | UTF-16 units | Code points | Grapheme clusters điển hình |
| --- | ---: | ---: | ---: |
| `ABC` | 3 | 3 | 3 |
| `🌍` | 2 | 1 | 1 |
| `e◌́` (ký tự `e` + dấu sắc U+0301) | 2 | 2 | 1 |
| `👩‍💻` (woman technologist) | 5 | 3 | 1 |
| `🇻🇳` (cặp regional indicators) | 4 | 2 | 1 |
| `👍🏽` (emoji + skin tone) | 4 | 2 | 1 |

Các cụm emoji trong bảng là minh họa các quy tắc Unicode grapheme hiện đại; font/renderer có thể vẽ một cụm thành một hình, một ô hoặc nhiều glyph. **Grapheme count không phải số pixel, không phải độ rộng terminal và không phải số glyph luôn đúng trên mọi thiết bị.**

### Vì sao Java có `char` 16 bit?

`char` Java biểu diễn **một UTF-16 code unit**. Với code point trong Basic Multilingual Plane (BMP) ngoài dải surrogate, thường một `char` đủ biểu diễn một code point. Nhưng với code point ngoài BMP, như emoji `🌍` U+1F30D, UTF-16 cần:

```text
U+1F30D
   ↓
high surrogate = U+D83C
low surrogate  = U+DF0D
```

Hai code unit riêng lẻ **không phải hai ký tự emoji hợp lệ**. Nếu chỉ giữ high surrogate và bỏ low surrogate, đầu ra có thể thành ký tự thay thế `�` hoặc bị encoder từ chối tùy cách xử lý lỗi.

## 3. Chỉ số `char` có thể nằm giữa một emoji

Với chuỗi `A🌍B`:

| UTF-16 index | `charAt(index)` | Vai trò |
| ---: | --- | --- |
| 0 | U+0041 | `A` |
| 1 | U+D83C | High surrogate của `🌍` |
| 2 | U+DF0D | Low surrogate của `🌍` |
| 3 | U+0042 | `B` |

`substring(beginIndex, endIndex)` nhận chỉ số theo **UTF-16 code unit**, `endIndex` không bao gồm. Vì vậy:

```java
String value = "A🌍B";
String broken = value.substring(0, 2);
```

`broken` gồm `A` và high surrogate; nó **không** chứa nguyên vẹn emoji. `String` Java có thể giữ unpaired surrogate, nên không chắc lệnh `substring` sẽ ném exception. Vấn đề chỉ bộc lộ về sau khi encode, hiển thị, so sánh hoặc truyền sang hệ khác.

### Ví dụ Java 17+ kiểm chứng bằng code point

Tạo file `Utf16IndexDemo.java`:

```java
import java.util.Locale;

public class Utf16IndexDemo {
    static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String s = "A" + new String(Character.toChars(0x1F30D))
                + "B";

        System.out.println("utf16 length: " + s.length());
        System.out.println("code points: "
                + s.codePointCount(0, s.length()));

        for (int i = 0; i < s.length(); i++) {
            System.out.printf(Locale.ROOT,
                    "char[%d]=U+%04X%n", i, (int) s.charAt(i));
        }

        String broken = s.substring(0, 2);
        System.out.println("broken length: " + broken.length());
        System.out.println("dangling high: "
                + Character.isHighSurrogate(broken.charAt(1)));

        int safeEnd = s.offsetByCodePoints(0, 2);
        System.out.println("safe points: "
                + points(s.substring(0, safeEnd)));
        System.out.println("reverse points: "
                + points(new StringBuilder(s).reverse().toString()));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 Utf16IndexDemo.java
java Utf16IndexDemo
```

Stdout (dùng mã Unicode để không phụ thuộc console có font emoji):

```text
utf16 length: 4
code points: 3
char[0]=U+0041
char[1]=U+D83C
char[2]=U+DF0D
char[3]=U+0042
broken length: 2
dangling high: true
safe points: [U+0041, U+1F30D]
reverse points: [U+0042, U+1F30D, U+0041]
```

Hai bài học khác nhau ở đây:

1. **Cắt bằng chỉ số `char` có thể xé surrogate pair**; `offsetByCodePoints` giúp chọn ranh giới sau số code point.
2. **`StringBuilder.reverse()` thực sự bảo toàn surrogate pair hợp lệ** (đảo `B🌍A` đúng ở mức code point). Không nên tuyên bố mọi việc đảo chuỗi bằng `StringBuilder.reverse()` đều phá emoji; lỗi quan trọng hơn là nó không bảo toàn **cụm grapheme gồm nhiều code point**.

## 4. Dùng `offsetByCodePoints` để cắt theo code point

Khi yêu cầu nghiệp vụ là "lấy n Unicode code point", hãy biến **số code point** thành **offset UTF-16** rồi gọi `substring`:

```java
public static String prefixCodePoints(String s, int count) {
    if (s == null) {
        throw new NullPointerException("s");
    }
    int total = s.codePointCount(0, s.length());
    if (count < 0 || count > total) {
        throw new IllegalArgumentException("Invalid count");
    }
    int end = s.offsetByCodePoints(0, count);
    return s.substring(0, end);
}
```

Đây là **phương thức minh họa**, đặt bên trong một lớp Java. Với `"A🌍B"`, `prefixCodePoints(s, 2)` trả `"A🌍"` mà không cắt giữa hai surrogate.

Các API cần phân biệt:

- `s.length()` trả **số UTF-16 code units**, không phải số ký tự Unicode.
- `s.charAt(index)` trả **một `char`**, có thể là một nửa surrogate pair.
- `s.codePointAt(charIndex)` trả code point bắt đầu tại **chỉ số UTF-16** đã cho; chỉ số vẫn tính theo `char`.
- `s.codePointBefore(charIndex)` trả code point nằm trước vị trí UTF-16.
- `s.codePointCount(startChar, endChar)` đếm code point trong đoạn xác định bằng **hai chỉ số UTF-16**.
- `s.offsetByCodePoints(startChar, delta)` chuyển độ lệch code point thành chỉ số UTF-16 hợp lệ từ một ranh giới phù hợp.
- `s.codePoints()` trả `IntStream` các code point (`int`); `s.chars()` trả các code unit (`int` mở rộng từ `char`).
- `Character.charCount(codePoint)` cho biết code point hợp lệ được biểu diễn bằng 1 hay 2 code units UTF-16.
- `StringBuilder.appendCodePoint(int)` thêm nguyên vẹn một code point.

Đừng gọi `codePointAt(index)` với `index` là "số thứ tự code point" mà không chuyển đổi: tham số này vẫn là **UTF-16 index**. Cũng đừng giả định `offsetByCodePoints` tự xác thực mọi chuỗi UTF-16 có surrogate hợp lệ; **unpaired surrogate** trong String có thể được đếm như một đơn vị, vì API làm việc cả trên chuỗi UTF-16 có dữ liệu lỗi.

### Cắt theo code point vẫn chưa tương đương cắt theo ký tự hiển thị

Với chuỗi `e` + U+0301 (combining acute accent), cắt **một code point** có thể chỉ giữ `e` và bỏ dấu. Với `👩‍💻`, cắt một hoặc hai code point có thể tạo một emoji không còn nghĩa gốc. Đó là lý do cần cấp độ grapheme cho UI.

## 5. Vấn đề ngược chuỗi: `char[]` và `StringBuilder.reverse()` khác nhau

Một thuật toán tự viết thường thấy:

```java
static String reverseChars(String s) {
    char[] chars = s.toCharArray();
    for (int i = 0, j = chars.length - 1; i < j; i++, j--) {
        char tmp = chars[i];
        chars[i] = chars[j];
        chars[j] = tmp;
    }
    return new String(chars);
}
```

Với `🌍` có UTF-16 pair `D83C DF0D`, đảo từng `char` có thể biến chúng thành `DF0D D83C`, một cặp **low-high** không hợp lệ. Nếu chuỗi có dữ liệu text quốc tế, đừng dùng kiểu đảo `char[]` này để đảo Unicode.

`new StringBuilder(s).reverse().toString()` là giải pháp tốt hơn **ở mức code point** vì JDK đặc biệt xử lý surrogate pair hợp lệ như một đơn vị khi reverse. Tuy nhiên, nó **không** đảm bảo giữ những chuỗi nhiều code point đại diện cho **một grapheme**.

Ví dụ: `e\u0301` (e + combining acute) có hai code point:

```text
Trước:  [U+0065, U+0301]
Sau khi reverse(): [U+0301, U+0065]
```

Combining mark đã đứng trước chữ cơ sở. Với emoji `👩‍💻` gồm ba code point:

```text
Trước: [U+1F469, U+200D, U+1F4BB]
Sau:   [U+1F4BB, U+200D, U+1F469]
```

Surrogate pair vẫn hợp lệ, nhưng **thứ tự thành phần trong cụm bị đảo**, làm thay đổi hình/ý nghĩa emoji.

### Ví dụ Java 17+: đảo được code point nhưng không giữ grapheme

File `ReverseLimitsDemo.java`:

```java
import java.util.Locale;

public class ReverseLimitsDemo {
    static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String accent = "e\u0301";
        String technologist = new String(
                new int[] {0x1F469, 0x200D, 0x1F4BB}, 0, 3);

        System.out.println("accent: " + points(accent));
        System.out.println("accent reversed: "
                + points(new StringBuilder(accent).reverse().toString()));
        System.out.println("emoji: " + points(technologist));
        System.out.println("emoji reversed: "
                + points(new StringBuilder(technologist).reverse().toString()));
    }
}
```

```bash
javac -encoding UTF-8 ReverseLimitsDemo.java
java ReverseLimitsDemo
```

```text
accent: [U+0065, U+0301]
accent reversed: [U+0301, U+0065]
emoji: [U+1F469, U+200D, U+1F4BB]
emoji reversed: [U+1F4BB, U+200D, U+1F469]
```

**Phân biệt rõ:** `StringBuilder.reverse()` không phá cấu trúc high-low surrogate pair hợp lệ, nhưng nó đảo **thứ tự code point của một cụm nhiều code point**, vì thế không phải phép đảo "ký tự người dùng nhìn thấy" cho văn bản tổng quát.

## 6. Extended grapheme cluster: đơn vị phù hợp hơn cho UI

Quy tắc **Unicode Standard Annex #29 (UAX #29)** xác định ranh giới **extended grapheme cluster** nhằm xấp xỉ đơn vị chữ viết mà con người nhận thấy. Những cụm này có thể bao gồm:

1. **Chữ cơ sở + dấu tổ hợp**: `e` + U+0301 được coi như một cụm.
2. **Cặp regional indicator**: hai code point tạo một lá cờ quốc gia, ví dụ `🇻🇳`.
3. **Emoji + modifier**: `👍🏽` gồm emoji cơ sở và bộ điều chỉnh màu da.
4. **Emoji ZWJ sequence**: `👩‍💻` gồm `U+1F469` + `U+200D` + `U+1F4BB`.
5. **Một số chuỗi variation selector**: `U+FE0F` yêu cầu kiểu emoji ở những ký tự phù hợp.
6. **Một số chuỗi chữ viết phức tạp**: ký tự và dấu hoặc dấu nối của nhiều hệ chữ có thể tạo thành một cụm.
7. **CRLF**: cặp `\r\n` được xem là một cluster trong thuật toán grapheme.

Do đó, **đếm code point** không đủ để quyết định số "ký tự" trong một ô nhập liệu Unicode. Đồng thời, grapheme cluster vẫn không phải là *từ*, *âm tiết*, *glyph* hoặc *độ rộng giao diện*.

### Regex `\X` của Java 17+

`java.util.regex.Pattern` hỗ trợ regex **`\X`** (extended grapheme cluster), kể cả trong JDK 17. Trong **Java string literal**, viết `"\\X"` để regex engine nhận được dấu `\` theo cú pháp regex.

Ví dụ:

```java
Pattern pattern = Pattern.compile("\\X");
Matcher matcher = pattern.matcher(text);
while (matcher.find()) {
    String cluster = matcher.group();
    // cluster là một extended grapheme cluster theo dữ liệu Unicode của JDK.
}
```

Đây là **đoạn minh họa**, cần `import java.util.regex.Pattern;` và `Matcher`, cùng biến `text` đã khai báo. Mặc dù `Pattern` nhận diện theo định nghĩa Unicode, cách phân nhóm của các emoji mới có thể thay đổi khi JDK cập nhật phiên bản dữ liệu Unicode; test quan trọng nên chạy trên runtime mục tiêu.

### `BreakIterator` cũng có thể dùng, nhưng chú ý phiên bản

`java.text.BreakIterator.getCharacterInstance(locale)` là API phân tích ranh giới ký tự. Tuy nhiên, **hành vi không giống nhau giữa các thế hệ JDK**:

- **JDK 17**: không nên giả định mọi chuỗi emoji ZWJ/cờ sẽ luôn được tách theo extended grapheme cluster hiện đại; việc phân đoạn phụ thuộc triển khai và Unicode data.
- **JDK 20 trở lên**: triển khai mặc định `BreakIterator` được cập nhật để tuân theo quy tắc **extended grapheme cluster của Unicode UAX #29**, theo thay đổi **JDK-8291660**.

Vì bài hướng đến **Java 17+**, ví dụ cắt theo grapheme dùng `Pattern.compile("\\X")`, vốn được tài liệu Java 17 mô tả. Nếu dùng `BreakIterator`, hãy kiểm thử trên đúng JDK/provider, nhất là đối với emoji gia đình, cờ, skin tone và ZWJ.

## 7. Java 17+: đếm và định vị ranh giới grapheme bằng `\X`

Tạo file `GraphemeCountDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class GraphemeCountDemo {
    static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String text = new String(new int[] {
                0x0065, 0x0301, 0x0020,
                0x1F469, 0x200D, 0x1F4BB, 0x0020,
                0x1F1FB, 0x1F1F3
        }, 0, 9);

        Matcher matcher = Pattern.compile("\\X").matcher(text);
        List<String> graphemes = new ArrayList<>();
        List<Integer> endOffsets = new ArrayList<>();

        while (matcher.find()) {
            graphemes.add(codePoints(matcher.group()));
            endOffsets.add(matcher.end());
        }

        System.out.println("UTF-16 units: " + text.length());
        System.out.println("code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("graphemes: " + graphemes.size());
        System.out.println("clusters: " + graphemes);
        System.out.println("end offsets: " + endOffsets);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 GraphemeCountDemo.java
java GraphemeCountDemo
```

Đầu ra trên JDK có các quy tắc grapheme đã đối chiếu:

```text
UTF-16 units: 13
code points: 9
graphemes: 5
clusters: [[U+0065, U+0301], [U+0020], [U+1F469, U+200D, U+1F4BB], [U+0020], [U+1F1FB, U+1F1F3]]
end offsets: [2, 3, 8, 9, 13]
```

Năm cụm lần lượt là:

- `e` + dấu sắc (một grapheme).
- Dấu cách.
- Emoji người làm việc với máy tính gồm ba code point.
- Dấu cách.
- Cặp regional indicators đại diện cờ Việt Nam.

Đặc biệt, `matcher.start()` và `matcher.end()` vẫn là **UTF-16 offsets** để dùng với `substring`. Ưu điểm là ranh giới được chọn **sau cả grapheme**, không ở giữa surrogate hoặc chuỗi dấu tổ hợp. Không biến các offset này thành code point indices rồi truyền trực tiếp vào `substring`; đó là hai hệ đơn vị khác nhau.

## 8. Cắt chuỗi theo mục đích: code point hay grapheme?

Cùng câu "lấy tối đa N ký tự" có nhiều nghĩa:

| Yêu cầu | Đơn vị nên xét | Ví dụ |
| --- | --- | --- |
| Giới hạn dung lượng của một API Java theo UTF-16 units | UTF-16 code units, **nhưng phải tránh chia surrogate** | Phân mảnh chuỗi cho giao thức lưu trữ |
| Xử lý danh sách Unicode code points | Code point | Thuật toán phân loại Unicode |
| Tạo preview tối đa N ký tự người dùng nhìn thấy | Grapheme cluster | Tên người dùng, tiêu đề |
| Giới hạn tối đa số byte trên mạng hoặc DB | Byte sau encoding, ví dụ UTF-8 | Trường giới hạn 255 bytes |
| Giới hạn chiều ngang bằng pixel/ô terminal | Đo lường font/layout theo renderer | Cắt dòng màn hình, giao diện terminal |
| Giới hạn N từ | Word boundaries, không phải grapheme | Preview theo từ |

**Đừng dùng `String.length()` để suy số byte UTF-8**. Một code point ngoài BMP có thể dài bốn byte UTF-8 và hai code units UTF-16; một grapheme nhiều code point còn có thể chiếm nhiều byte hơn nữa.

### Cắt an toàn ở mức grapheme

Tạo `SafeTruncateDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SafeTruncateDemo {
    static String firstGraphemes(String text, int max) {
        if (text == null) {
            throw new NullPointerException("text");
        }
        if (max < 0) {
            throw new IllegalArgumentException("max must be >= 0");
        }

        Matcher matcher = Pattern.compile("\\X").matcher(text);
        int end = 0;
        int matched = 0;

        while (matched < max && matcher.find()) {
            end = matcher.end();
            matched++;
        }
        return text.substring(0, end);
    }

    public static void main(String[] args) {
        String text = "e\u0301" + new String(
                new int[] {0x1F469, 0x200D, 0x1F4BB}, 0, 3)
                + "!";
        for (int n = 0; n <= 3; n++) {
            String prefix = firstGraphemes(text, n);
            System.out.println(n + ": utf16=" + prefix.length()
                    + ", codePoints="
                    + prefix.codePointCount(0, prefix.length()));
        }
    }
}
```

```bash
javac -encoding UTF-8 SafeTruncateDemo.java
java SafeTruncateDemo
```

```text
0: utf16=0, codePoints=0
1: utf16=2, codePoints=2
2: utf16=7, codePoints=5
3: utf16=8, codePoints=6
```

Tại `n=1`, code không cắt giữa `e` và dấu sắc. Tại `n=2`, nó giữ trọn emoji ZWJ gồm ba code point (năm UTF-16 units). Kết quả về mặt ký tự hiển thị phù hợp hơn so với `substring(0, n)` hoặc prefix chỉ theo code point.

**Lưu ý triển khai:** `firstGraphemes` trả chuỗi nguyên vẹn nếu số cụm ít hơn `max`. Nếu cần thêm ký hiệu `…` khi bị rút ngắn, phải tách logic **phát hiện còn nội dung** và **chèn dấu ba chấm**; cũng nên xác định ellipsis có tính vào giới hạn N hay không. Dấu `…` tự nó cũng là một code point/grapheme trong ngữ cảnh thông thường.

## 9. Đảo theo grapheme thay vì đảo từng `char` hoặc từng code point

Nếu yêu cầu nghiệp vụ thật sự là "đảo thứ tự các cụm ký tự" (không phải xử lý văn bản RTL), có thể tách cụm bằng `\X`, đảo danh sách rồi ghép lại:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class ReverseGraphemeDemo {
    static String reverseGraphemes(String input) {
        Matcher matcher = Pattern.compile("\\X").matcher(input);
        List<String> graphemes = new ArrayList<>();

        while (matcher.find()) {
            graphemes.add(matcher.group());
        }
        Collections.reverse(graphemes);
        return String.join("", graphemes);
    }

    static String points(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(
                        Locale.ROOT, "U+%04X", cp))
                .toList().toString();
    }

    public static void main(String[] args) {
        String emoji = new String(
                new int[] {0x1F469, 0x200D, 0x1F4BB}, 0, 3);
        String input = "A" + emoji + "B";

        String byCodePoint = new StringBuilder(input)
                .reverse().toString();
        String byGrapheme = reverseGraphemes(input);

        System.out.println("input: " + points(input));
        System.out.println("code-point-like reverse: "
                + points(byCodePoint));
        System.out.println("grapheme reverse: " + points(byGrapheme));
    }
}
```

```bash
javac -encoding UTF-8 ReverseGraphemeDemo.java
java ReverseGraphemeDemo
```

```text
input: [U+0041, U+1F469, U+200D, U+1F4BB, U+0042]
code-point-like reverse: [U+0042, U+1F4BB, U+200D, U+1F469, U+0041]
grapheme reverse: [U+0042, U+1F469, U+200D, U+1F4BB, U+0041]
```

Kết quả grapheme reverse vẫn giữ **thứ tự nội bộ** của emoji `👩‍💻`; chỉ đổi thứ tự các cụm `A`, emoji, `B`. Đây là điều `StringBuilder.reverse()` không đảm bảo đối với cụm nhiều code point.

Tuy nhiên, **đảo grapheme không phải cách đúng để làm giao diện RTL (Arabic/Hebrew)**. Thứ tự hiển thị của văn bản hai chiều được Unicode Bidirectional Algorithm và layout engine quyết định, không phải bằng việc reverse `String`. Đối với RTL, dùng API văn bản/renderer phù hợp và đặt hướng văn bản đúng cách; không sửa thứ tự dữ liệu Unicode một cách thủ công.

## 10. Unicode normalization: hai chuỗi trông như nhau chưa chắc `equals`

Ký tự `é` có hai cách biểu diễn điển hình:

- **Precomposed:** U+00E9, một code point và một UTF-16 unit.
- **Decomposed:** U+0065 (`e`) + U+0301 (combining acute), hai code point và hai UTF-16 units.

Hai chuỗi có thể hiển thị giống nhau nhưng `String.equals` trả `false`. Cắt theo `char` hoặc code point dễ khiến trường hợp decomposed bị mất dấu; cắt theo grapheme ít làm hỏng trực quan hơn, nhưng **không tự chuẩn hóa** cách lưu ký tự.

Java có `java.text.Normalizer`:

```java
import java.text.Normalizer;

String composed = "\u00E9";
String decomposed = "e\u0301";
boolean same = composed.equals(decomposed); // false

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
boolean equivalent = composed.equals(normalized); // true
```

Đây là đoạn code **bên trong phương thức**. `NFC` là canonical composition; `NFD` là canonical decomposition; `NFKC`/`NFKD` còn có tương đương compatibility và có thể làm biến đổi ý nghĩa hiển thị trong một số trường hợp. Không áp dụng normalize tùy tiện lên identifier, mật khẩu, chữ ký số hoặc dữ liệu pháp lý mà chưa định nghĩa hợp đồng bảo toàn.

**Normalization không thay thế grapheme segmentation.** Ngay cả sau NFC, nhiều emoji ZWJ, chuỗi modifier và các trường hợp chữ viết vẫn gồm nhiều code point trong một grapheme. Một chuỗi đã normalize vẫn có thể bị cắt sai nếu dựa vào chỉ số `char`.

### Ví dụ Java 17+ về normalization

File `NormalizationDemo.java`:

```java
import java.text.Normalizer;

public class NormalizationDemo {
    public static void main(String[] args) {
        String a = "\u00E9";
        String b = "e\u0301";

        System.out.println("a utf16: " + a.length());
        System.out.println("b utf16: " + b.length());
        System.out.println("raw equal: " + a.equals(b));
        System.out.println("NFC equal: "
                + a.equals(Normalizer.normalize(
                        b, Normalizer.Form.NFC)));
    }
}
```

```bash
javac -encoding UTF-8 NormalizationDemo.java
java NormalizationDemo
```

```text
a utf16: 1
b utf16: 2
raw equal: false
NFC equal: true
```

## 11. Chuỗi UTF-16 sai: unpaired surrogate và encoding

`String` Java có thể chứa một **high surrogate không có low surrogate** hoặc ngược lại. Các API như `substring` không nhất thiết ném exception khi tạo chuỗi như vậy. Nhưng chuyển sang UTF-8 (hoặc các hệ Unicode chuẩn khác) là lúc cần xử lý **malformed input**.

Ví dụ, `StandardCharsets.UTF_8.newEncoder()` được cấu hình `CodingErrorAction.REPORT` có thể **từ chối** unpaired surrogate thay vì âm thầm thay ký tự:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class SurrogateValidationDemo {
    public static void main(String[] args) {
        String text = "A"
                + new String(Character.toChars(0x1F30D)) + "B";
        String broken = text.substring(0, 2);

        try {
            StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap(broken));
            System.out.println("encoded");
        } catch (CharacterCodingException ex) {
            System.out.println("unpaired surrogate rejected");
        }
    }
}
```

```bash
javac SurrogateValidationDemo.java
java SurrogateValidationDemo
```

```text
unpaired surrogate rejected
```

Một vài con đường encode khác có thể **thay** phần ký tự sai bằng replacement hoặc dấu `?` tùy chính sách encoder, dẫn đến mất dữ liệu hoặc khó lần nguồn lỗi. Đừng dựa vào chuyện thiết bị hiển thị được dấu `�` là bằng chứng chuỗi vẫn hợp lệ. Với dữ liệu API, log hoặc persistence cần toàn vẹn, nên validate/encode theo chính sách cụ thể thay vì tự cắt chuỗi bằng index có thể xé surrogate.

Ngoài ra, **số byte** sau `UTF-8` không bằng `String.length()`. Khi hệ thống giới hạn số byte (ví dụ field protocol), phải đo trên **encoded bytes** và cắt tại ranh giới phù hợp, không cắt mù quáng vào byte sequence UTF-8 hoặc UTF-16. Việc đếm grapheme cho UI và giới hạn byte cho storage là hai bài toán độc lập.

## 12. Chú ý các bẫy khó quan sát khác

### 12.1. CRLF là hai code point nhưng thường một ranh giới dòng

Một dòng kết thúc bằng CRLF có sequence `\r\n` (U+000D U+000A). Nếu đảo code point, thứ tự có thể thành `\n\r`; các hệ thống xử lý line break có thể hiểu khác. UAX #29 xem CRLF như một grapheme cluster. Nhưng đối với thao tác **đảo các dòng**, cách thích hợp là phân tích dòng/line terminator theo đúng mục đích, không phải đảo từng grapheme toàn chuỗi.

### 12.2. Variation selector và emoji modifier

Một số emoji dùng U+FE0F (variation selector-16) để yêu cầu biểu diễn emoji; nhiều emoji khác dùng modifier như U+1F3FD. `StringBuilder.reverse()` giữ surrogate pair của các code point ngoài BMP nhưng vẫn có thể đẩy selector/modifier đứng trước ký tự cơ sở. Regex grapheme cluster giúp cắt tại ranh giới phù hợp hơn. Khi kiểm thử, dùng danh sách code point để thấy rõ ký tự vô hình.

### 12.3. Đảo văn bản không đồng nghĩa với đổi hướng viết

Ngôn ngữ như tiếng Ả Rập, Do Thái và câu trộn Latin với chữ RTL có **quy tắc bidi**. Đảo `char`, code point hoặc grapheme để "sửa thứ tự hiển thị" thường làm sai dữ liệu. Hãy giữ thứ tự logic của nội dung và giao trách nhiệm hiển thị cho renderer hỗ trợ bidi; trong Java có `java.text.Bidi` và tùy nền tảng có UI text engine thích hợp.

### 12.4. Code point không nhất thiết là ký tự hợp lệ ở mọi ngữ cảnh

`Character.isValidCodePoint(cp)` kiểm tra phạm vi code point Unicode, nhưng một giá trị nằm trong phạm vi code point **không nhất thiết** là ký tự đã được gán hoặc hợp lệ trong mọi loại dữ liệu. Các Unicode noncharacters, control codes và unpaired surrogates cần được xem theo schema và giao thức sử dụng. Đừng hiểu "một code point" là "một chữ cái đọc được" hoặc "một ký tự có thể hiển thị".

### 12.5. Khác biệt giữa phiên bản Unicode

Các quy tắc phân đoạn grapheme và tập emoji được cập nhật theo Unicode. Nếu ứng dụng cần giới hạn số grapheme nhất quán giữa backend và frontend, nên cố định/ghi nhận phiên bản dữ liệu Unicode và kiểm thử theo ví dụ thực của sản phẩm. JDK, trình duyệt và thư viện có thể không hoàn toàn dùng cùng phiên bản dữ liệu.

## 13. Bảng lựa chọn API

| Tình huống | Nên dùng | Tránh |
| --- | --- | --- |
| Duyệt UTF-16 để tích hợp API legacy | `charAt` theo contract rõ ràng | Gọi mỗi `char` là một ký tự hiển thị |
| Cắt N code points đầu | `codePointCount` + `offsetByCodePoints` | `substring(0, N)` |
| Phân tích từng code point | `codePoints()` hoặc `codePointAt` + `Character.charCount` | Đếm `char` thành số code point |
| Đảo chuỗi ở mức code point | `StringBuilder.reverse()` cho cặp surrogate hợp lệ hoặc dựng lại bằng code point | Tự swap từng `char` |
| Cắt N grapheme clusters | `Pattern.compile("\\X")` và `Matcher.end()` | Cắt mỗi code point rồi giả định còn nguyên emoji |
| Đảo các cụm ký tự | Tách `\X`, đảo **các cụm**, nối lại | `StringBuilder.reverse()` nếu cần giữ cụm |
| Phân tích ranh giới ký tự với `BreakIterator` | Kiểm tra JDK/provider; EGC đầy đủ mặc định từ JDK 20 | Giả định JDK 17 luôn xử lý mọi emoji ZWJ đúng |
| So sánh văn bản tương đương Unicode | `Normalizer` phù hợp + quy tắc so sánh/collation theo nghiệp vụ | Tự strip dấu hoặc bỏ code point |
| Giới hạn bytes UTF-8 | Encode và tính bytes, bảo toàn sequence hợp lệ | Dùng `String.length()` làm độ dài bytes |
| Hiển thị RTL | UI/layout hỗ trợ Unicode bidi | `reverse()` để đảo ký tự |
| Tìm vị trí con trỏ trên text người dùng | Grapheme boundary + engine bố trí văn bản | `char` index bất kỳ |

## 14. Checklist kiểm thử cho ứng dụng đa ngôn ngữ

Hãy lập ít nhất các nhóm input sau:

1. **ASCII đơn giản:** `ABC`; là trường hợp `UTF-16 units = code points = graphemes`.
2. **Một code point supplementary:** `A🌍B`; test `length=4`, `codePointCount=3`, tránh ranh giới giữa U+D83C và U+DF0D.
3. **Dấu kết hợp:** `e\u0301`; test cắt một code point và một grapheme, khác nhau rõ.
4. **NFC/NFD:** `é` precomposed so với `e + U+0301`; test so sánh theo normalization policy.
5. **ZWJ emoji:** `👩‍💻`; test giữ nguyên toàn cụm khi cắt/đảo.
6. **Regional indicators:** `🇻🇳`; test không tách đôi cờ.
7. **Emoji modifier:** `👍🏽`; test giữ skin tone với emoji cơ sở.
8. **Variation selector:** chuỗi có U+FE0F; test không tách selector khỏi ký tự trước.
9. **CRLF:** `\r\n`; test không làm sai cấu trúc dòng.
10. **Unpaired surrogate:** test encoder `CodingErrorAction.REPORT` hoặc policy thay thế có kiểm soát.
11. **Chuỗi rỗng / giới hạn 0 / giới hạn vượt số cụm:** xác nhận API không crash và không tạo fragment sai.
12. **Các ngôn ngữ viết từ phải sang trái và chữ viết phức tạp:** kiểm tra với renderer thực tế, không chỉ kết quả `String`.
13. **Khác biệt JDK 17, 20+ và phiên bản Unicode:** test các sequence emoji sản phẩm sử dụng thực tế.

**Câu hỏi nên viết thành test:** nghiệp vụ giới hạn *N UTF-16 units*, *N code points*, *N grapheme clusters*, *N bytes* hay *N pixels*? Nếu không chọn đơn vị, không thể nói thuật toán "cắt N ký tự" là đúng.

## 15. Những lỗi phổ biến

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `substring(0, n)` với n do người dùng nhập là số ký tự | Có thể cắt giữa surrogate hoặc grapheme | Chọn đơn vị và tính ranh giới |
| `length()` bằng số emoji hiển thị | Một emoji có thể cần nhiều code units/code points | Dùng `codePointCount` hoặc grapheme segmentation |
| Đảo `char[]` bằng swap | Có thể tạo low-high surrogate sai | Dùng ít nhất `StringBuilder.reverse()` |
| Nghĩ `StringBuilder.reverse()` luôn đảo đúng "ký tự" | Dấu kết hợp và ZWJ emoji có thể đổi thứ tự bên trong | Đảo grapheme clusters |
| Nghĩ `codePoints()` là danh sách grapheme | Một grapheme có thể có nhiều code points | Dùng `\X` hoặc grapheme boundary engine |
| Dùng `BreakIterator` trên JDK 17 và giả định mọi emoji là một cụm | Hành vi phụ thuộc JDK, chưa có nâng cấp JDK20 | Kiểm thử; chọn `\X`/thư viện phù hợp |
| Chỉ thử ASCII | Không phát hiện lỗi Unicode | Test emoji, combining mark, cờ |
| Không phân biệt chữ precomposed/decomposed | `equals` khác dù giống mắt thường | Dùng normalization có chủ đích |
| Cắt byte UTF-8 theo số byte mà không giữ code point | Tạo byte sequence sai | Encode/segment ở ranh giới hợp lệ |
| Đảo chuỗi để hỗ trợ RTL | Sai thứ tự logic và hiển thị | Dùng bidi renderer |
| Coi EGC là chiều rộng màn hình | Layout không tương ứng số grapheme | Dùng đo text trong UI renderer |
| Thay unpaired surrogate một cách im lặng | Mất dữ liệu, log khó chẩn đoán | Encoder REPORT hoặc replacement policy rõ ràng |

## 16. Tự kiểm tra

1. **Với `"A🌍B"`, `String.length()` trả bao nhiêu?** 4, vì `🌍` dùng hai UTF-16 code units.
2. **`codePointCount` trả bao nhiêu?** 3, vì có `A`, `🌍`, `B`.
3. **`substring(0,2)` có an toàn không?** Không; có thể để lại high surrogate không có low surrogate.
4. **Muốn lấy hai code points đầu tiên bằng Java API nào?** `offsetByCodePoints(0,2)` rồi dùng chỉ số UTF-16 trả về với `substring`.
5. **`StringBuilder.reverse()` có luôn làm sai cặp surrogate hợp lệ không?** Không; nó bảo toàn cặp surrogate khi reverse.
6. **Vì sao `StringBuilder.reverse()` vẫn có thể sai với `e\u0301`?** Nó đảo dấu kết hợp ra trước chữ cơ sở.
7. **`👩‍💻` có bao nhiêu UTF-16 units, code points, graphemes điển hình?** 5 units, 3 code points, 1 grapheme.
8. **Regex nào chọn một extended grapheme cluster trong Java 17?** `\X`, viết trong Java string literal là `"\\X"`.
9. **`Matcher.end()` tính theo code points hay UTF-16?** UTF-16 offsets, phù hợp trực tiếp với `substring`.
10. **`BreakIterator` đã hỗ trợ EGC đầy đủ từ JDK nào theo thay đổi JDK-8291660?** JDK 20, với triển khai mặc định.
11. **NFC có thay thế grapheme segmentation không?** Không; normalization không tự biến mọi emoji ZWJ thành một code point.
12. **Văn bản RTL có nên reverse `String` để hiển thị đúng không?** Không; dùng thuật toán bidi và renderer phù hợp.
13. **Nếu server giới hạn 255 byte UTF-8, có thể dùng `s.length() <= 255` không?** Không; phải đo số byte sau encode theo encoding đã chọn.
14. **Vì sao đoạn text hiển thị "giống nhau" vẫn có thể `equals=false`?** Có thể khác dạng chuẩn hóa Unicode, ví dụ `é` precomposed so với `e + U+0301`.
15. **Muốn đảo "ký tự hiển thị" mà giữ emoji ZWJ, nên làm gì?** Tách thành grapheme clusters rồi đảo các cluster, không đảo code points bên trong cluster.

## Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length`, `charAt`, `substring`, `codePoints`, `codePointCount` và `offsetByCodePoints`.
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): `reverse` xử lý surrogate pairs hợp lệ như một đơn vị.
- [Java SE 17 — Character](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pairs và Unicode code points.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): regex `\X` cho extended grapheme cluster.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): các API phân tích ranh giới ký tự/từ/câu.
- [JDK 20 Release Notes — Grapheme Support in BreakIterator (JDK-8291660)](https://www.oracle.com/java/technologies/javase/20-relnote-issues.html): triển khai mặc định được cập nhật theo extended grapheme clusters.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): NFC/NFD/NFKC/NFKD.
- [Unicode Standard Annex #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): quy tắc extended grapheme cluster, ZWJ emoji, combining marks, regional indicators.
- [Unicode Standard Annex #15 — Unicode Normalization Forms](https://www.unicode.org/reports/tr15/): canonical và compatibility normalization.
