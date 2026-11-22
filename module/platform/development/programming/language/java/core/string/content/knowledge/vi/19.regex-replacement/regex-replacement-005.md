# Phân biệt escape của mẫu tìm và escape của phần thay thế trong Java

## 1. Tại sao có hai kiểu escape khác nhau?

Khi thay thế bằng regex trong Java, ví dụ `text.replaceAll(regex, replacement)`, hai tham số đi qua **hai bộ quy tắc riêng**:

1. **Mẫu tìm (regex/pattern)** được giải thích bởi `java.util.regex.Pattern`. Các ký tự như `.`, `*`, `+`, `?`, `[`, `(`, `|`, `$` và dấu `\` có thể mang ý nghĩa đặc biệt đối với việc **tìm vị trí khớp**.
2. **Chuỗi thay thế (replacement)** được giải thích bởi `java.util.regex.Matcher`. Ở đây, `$1`, `$2` hoặc `${name}` có nghĩa là **chèn nội dung nhóm bắt**, còn dấu `\` dùng để escape ký tự tiếp theo trong *replacement*. Các ký tự regex như `.` hay `*` trong replacement thông thường chỉ là văn bản.
3. **Nếu viết trong mã nguồn Java**, cả regex lẫn replacement còn phải đi qua cú pháp *Java string literal*: viết `\\` trong mã nguồn để tạo **một** dấu `\` ở chuỗi lúc chạy. Đây là lớp escape thứ ba, dễ bị nhầm với hai lớp ở trên.

Hình dung luồng xử lý:

```text
Mã nguồn Java
     |
     |  Java string literal (\\ trong source -> \ lúc chạy)
     v
regex -------------------> Pattern: quy tắc tìm kiếm
replacement -------------> Matcher: quy tắc chèn/đổi nhóm
                                        |
                                        v
                                   Chuỗi kết quả
```

Ví dụ, `"\\."` dùng ở **regex** có nghĩa là tìm **dấu chấm thật**; `"\\$"` dùng ở **replacement** có nghĩa là ghi **ký tự đô la thật**. Hai cú pháp giống hình dạng (dấu `\` trong chuỗi Java) nhưng thuộc **hai bộ giải thích khác nhau**.

> Quy tắc cần nhớ: **`Pattern.quote(...)` bảo vệ mẫu tìm**; **`Matcher.quoteReplacement(...)` bảo vệ nội dung thay thế**. Dùng đúng hàm tại đúng đầu vào.

## 2. Escape của mẫu tìm: regex diễn giải các ký tự đặc biệt

### 2.1. Mẫu tìm là regex, không mặc định là văn bản thuần

Xét hai câu lệnh:

```java
System.out.println("a.b".replaceAll(".", "-"));    // ---
System.out.println("a.b".replaceAll("\\.", "-")); // a-b
```

- Regex `"."` khớp **bất kỳ một ký tự** thông thường (trừ một số ký tự xuống dòng tùy chế độ), nên cả `a`, `.` và `b` đều được thay.
- Regex ở runtime `\.` khớp **dấu chấm thật**; trong Java source phải viết `"\\."`, nên chỉ một dấu chấm được thay.

Bảng sau đọc từ **mã nguồn Java** sang ý nghĩa tìm kiếm:

| Muốn tìm | Java source cho regex | Regex ở runtime | Ý nghĩa |
| --- | --- | --- | --- |
| Dấu chấm `.` | `"\\."` | `\.` | Dấu chấm thông thường, không phải wildcard |
| Một hoặc nhiều chữ số | `"\\d+"` | `\d+` | Regex cho dãy chữ số |
| Ký tự `$` | `"\\$"` | `\$` | Dấu đô la thật, không phải mốc cuối |
| Một dấu gạch chéo ngược `\` | `"\\\\"` | `\\` | Regex escape dấu `\` |
| Từ "a" theo sau bởi chữ số | `"a\\d"` | `a\d` | Regex mô tả cấu trúc, không phải chuỗi cố định |

Viết `"\d+"` hoặc `"\."` trực tiếp trong Java source sẽ gây lỗi biên dịch *illegal escape character*: `\d` và `\.` không phải escape hợp lệ của Java string literal. Điều này xảy ra **trước khi** regex engine nhận đầu vào.

### 2.2. Khi mẫu tìm đến từ dữ liệu người dùng

Nếu mục tiêu là tìm **đúng một chuỗi ký tự** do người dùng nhập, dùng `Pattern.quote(...)`:

```java
String find = "$5.00";
String source = "Giá là $5.00";
String result = source.replaceAll(Pattern.quote(find), "10 USD");
System.out.println(result); // Giá là 10 USD
```

Nếu dùng trực tiếp `"$5.00"` làm regex, ký tự `$` sẽ được hiểu là mốc kết thúc input, còn dấu `.` là ký tự bất kỳ; kết quả không phù hợp mục tiêu tìm văn bản `$5.00`. `Pattern.quote(find)` khiến toàn bộ nội dung `find` được xử lý như **văn bản literal**, kể cả khi chứa `\`, `$`, dấu ngoặc hoặc dấu `.`.

Cách khác khi làm việc trực tiếp với `Pattern`:

```java
Pattern literal = Pattern.compile("$5.00", Pattern.LITERAL);
System.out.println(literal.matcher("Giá là $5.00").find()); // true
```

`Pattern.LITERAL` thay đổi **cách diễn giải pattern**, không thay đổi cú pháp replacement của `Matcher`. Nếu thật sự muốn tìm cấu trúc bằng regex (ví dụ `"\\d+"`), **không** quote toàn bộ regex, vì khi đó nó sẽ tìm ký tự `\`, `d`, `+` theo nghĩa đen.

## 3. Escape của phần thay thế: cú pháp riêng của Matcher

Với `String.replaceAll(regex, replacement)`, `String.replaceFirst(regex, replacement)` và `Matcher.replaceAll(replacement)`, replacement không được hiểu như regex; thay vào đó nó có cú pháp riêng:

- `$1`, `$2`, ... tham chiếu tới nhóm bắt tương ứng. `$0` là **toàn bộ lần khớp**.
- `${name}` tham chiếu đến **nhóm bắt có tên**, được định nghĩa bằng `(?<name>...)` trong pattern.
- `\` trong replacement escape ký tự tiếp theo; cần escape chính dấu `$` hoặc dấu `\` khi muốn chèn chúng theo nghĩa đen.
- Một ký tự `$` không có tham chiếu nhóm hợp lệ có thể làm replacement lỗi. Tham chiếu tới nhóm không tồn tại cũng gây lỗi.

### 3.1. Ví dụ thay thế bằng nhóm bắt

```java
Pattern p = Pattern.compile("(\\w+)-(\\d+)");
System.out.println(p.matcher("item-42").replaceAll("$2:$1"));
// 42:item
```

Regex có hai nhóm: `(\\w+)` bắt `item`; `(\\d+)` bắt `42`. Replacement `"$2:$1"` chèn nhóm hai, dấu hai chấm, rồi nhóm một. Ký tự `:` trong replacement là dấu hai chấm thông thường.

Với nhóm có tên:

```java
String result = "item-42".replaceAll(
        "(?<name>[A-Za-z]+)-(?<qty>\\d+)",
        "${qty}x${name}");
System.out.println(result); // 42xitem
```

Lưu ý: `${qty}` là cú pháp **replacement**; `(?<qty>...)` là cú pháp **regex pattern**. Không được hoán đổi hai dạng này.

### 3.2. Muốn xuất đúng ký tự đô la `$` hoặc backslash `\`

Ví dụ thay dấu chấm bằng dấu đô la thật:

```java
System.out.println("a.b".replaceAll("\\.", "\\$")); // a$b
```

Ở đây:
- Java source `"\\."` tạo regex `\.`, tìm dấu chấm.
- Java source `"\\$"` tạo replacement gồm **backslash + dollar** (`\$` ở runtime). Matcher bỏ dấu escape và chèn `$` thật vào kết quả.

Tương tự, muốn thay dấu chấm bằng **một dấu backslash thật**:

```java
System.out.println("a.b".replaceAll("\\.", "\\\\")); // a\b
```

Java source `"\\\\"` tạo **hai dấu backslash** lúc chạy; Matcher xử lý chúng để xuất **một dấu backslash**. Nếu replacement ở runtime chỉ có một dấu `\` đứng cuối, nó không escape được ký tự tiếp theo và sẽ gây lỗi.

| Muốn đưa vào kết quả | Replacement Java source | Điều Matcher nhận tại runtime | Ý nghĩa |
| --- | --- | --- | --- |
| Giá trị nhóm 1 | `"$1"` | `$1` | Thay bằng nội dung group 1 |
| Dấu `$` thật | `"\\$"` | `\$` | Escape `$` trong replacement |
| Dấu `\` thật | `"\\\\"` | `\\` | Escape `\` trong replacement |
| Văn bản `$1` thật | `Matcher.quoteReplacement("$1")` | `\$1` | Bảo vệ cả `$` để không đọc thành group |
| Văn bản `$HOME\path` | `Matcher.quoteReplacement("$HOME\\path")` | Các dấu `$` và `\` được escape | Chèn nguyên văn đúng dữ liệu |

Dùng `Matcher.quoteReplacement(replacement)` là lựa chọn ít lỗi hơn khi chuỗi thay thế là văn bản tự do, có thể chứa nhiều dấu `$` và `\`:

```java
String literal = "$1\\";
System.out.println("a.b".replaceAll(
        "\\.", Matcher.quoteReplacement(literal)));
// a$1\b
```

Nếu truyền `"$1\\"` trực tiếp dưới dạng replacement mà chưa quote, Matcher sẽ cố diễn giải `$1` là tham chiếu nhóm, hoặc diễn giải `\` là escape. Việc quote giúp coi toàn bộ chuỗi thay thế là văn bản.

**Khác biệt quan trọng:** Khi muốn `$1` thực sự chèn **nhóm 1**, đừng gọi `Matcher.quoteReplacement("$1")`, vì lúc đó chuỗi `$1` chỉ được chèn theo nghĩa đen.

## 4. Ví dụ Java 17+ hoàn chỉnh

Tạo file **`RegexEscapingDemo.java`**:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class RegexEscapingDemo {
    public static void main(String[] args) {
        String source = "file.txt | price $5.00 | item-42";

        // 1. Pattern: tìm dấu chấm thật.
        System.out.println(source.replaceAll("\\.", "#"));

        // 2. Tìm một chuỗi literal và thay bằng một chuỗi literal.
        //    Cả dấu $ và backslash ở replacement đều được giữ nguyên.
        System.out.println(source.replaceAll(
                Pattern.quote("$5.00"),
                Matcher.quoteReplacement("$10\\new")));

        // 3. Replacement dùng nhóm bắt (không quoteReplacement).
        Pattern item = Pattern.compile("(\\w+)-(\\d+)");
        System.out.println(item.matcher(source).replaceAll("$2:$1"));

        // 4. Named capturing groups.
        System.out.println("item-42".replaceAll(
                "(?<name>[A-Za-z]+)-(?<qty>\\d+)",
                "${qty}x${name}"));

        // 5. Xuất $ và \ theo nghĩa đen.
        System.out.println("a.b".replaceAll("\\.", "\\$"));
        System.out.println("a.b".replaceAll("\\.", "\\\\"));

        // 6. Replacement chứa '$1' mà KHÔNG có ý nghĩa group 1.
        System.out.println("a.b".replaceAll(
                "\\.", Matcher.quoteReplacement("$1\\")));

        // 7. String.replace là phép thay thế literal ở cả hai phía.
        System.out.println("a.b".replace(".", "$1\\"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RegexEscapingDemo.java
java RegexEscapingDemo
```

Kết quả stdout:

```text
file#txt | price $5#00 | item-42
file.txt | price $10\new | item-42
file.txt | price $5.00 | 42:item
42xitem
a$b
a\b
a$1\b
a$1\b
```

Kết quả trên dùng dấu `\` **thật**; ví dụ `$10\new` không chứa xuống dòng, vì mã Java `"$10\\new"` tạo dấu backslash thật trước chữ `n`. Các biểu thức tương đương đã được kiểm tra qua JShell với JDK có hỗ trợ các API Java 17 này.

## 5. Kết hợp hai phía khi dữ liệu được nhập nguyên văn

Nếu hệ thống cung cấp **find** và **replacement** như hai chuỗi do người dùng nhập, trước hết xác định có cần tính năng regex hay không. Với tác vụ thay chuỗi literal thông thường, **String.replace(find, replacement)** giữ nguyên ký tự đặc biệt ở cả hai phía và là API dễ hiểu nhất.

Nếu vẫn phải dùng bộ máy regex, dùng **Pattern.quote(find)** cho tham số tìm và **Matcher.quoteReplacement(replacement)** cho tham số thay. Chỉ quote phía nào thực sự là dữ liệu literal; quote cả một biểu thức regex đang dùng chủ động sẽ thay đổi điều kiện tìm kiếm. Ví dụ, tìm đúng ký tự **$5.00** và thay bằng **$10\x** đòi hỏi bảo vệ cả hai phía để tránh đọc **$** thành anchor hoặc tham chiếu nhóm.

## 6. Khi vừa dùng nhóm bắt, vừa muốn thêm ký tự đặc biệt

Không thể quote **toàn bộ** replacement nếu trong đó có `$1` cần mở rộng thành nhóm bắt. Hãy xây dựng replacement có chủ đích.

Ví dụ muốn đổi `name=42` thành `[name: $42]`:

```java
String output = "name=42".replaceAll(
        "(\\w+)=(\\d+)",
        "[$1: \\$$2]");
System.out.println(output); // [name: $42]
```

Đọc replacement Java source `"[$1: \\$$2]"` từ trái sang phải:

- `$1`: chèn nhóm 1 `name`.
- `: `: văn bản thông thường.
- `\\$` trong Java source: tạo `\$` ở runtime, để Matcher xuất dấu `$` thật.
- `$2`: chèn nhóm 2 `42`.
- `]`: văn bản thông thường.

Với logic replacement động phức tạp, `Matcher.appendReplacement` kết hợp `appendTail` cho phép tạo giá trị từ nội dung từng lần khớp. Giá trị được tạo ra **vẫn phải quote** nếu muốn chèn nguyên văn:

```java
Matcher matcher = Pattern.compile("(\\w+)=([0-9]+)")
        .matcher("a=1;b=2");
StringBuffer out = new StringBuffer();

while (matcher.find()) {
    String literalPart = "[" + matcher.group(1)
            + " -> $" + matcher.group(2) + "]";
    matcher.appendReplacement(
            out, Matcher.quoteReplacement(literalPart));
}
matcher.appendTail(out);

System.out.println(out); // [a -> $1];[b -> $2]
```

Cơ chế: `appendReplacement` chèn phần chưa khớp trước đó, sau đó chèn replacement cho lần khớp; `appendTail` chép nốt phần cuối còn lại. Vì `literalPart` chứa ký tự `$` với mục đích literal, dùng `quoteReplacement` là bắt buộc để tránh bị thay bằng group. `StringBuffer` là kiểu đối số của overload `appendReplacement(StringBuffer, String)` (Java cũng có overload với `StringBuilder` trong phiên bản hiện đại).

## 7. Các lỗi thường gặp và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `replaceAll(".", "-")` thay mọi ký tự | `.` là wildcard regex | Dùng `"\\."` hoặc `Pattern.quote(".")` |
| `replaceAll("$5", "...")` không tìm được dấu `$` thật | `$` trong regex là mốc cuối input | Dùng `Pattern.quote("$5")` |
| `replaceAll("\\.", "$1")` lỗi khi không có nhóm 1 | `$1` trong replacement tham chiếu tới group 1 | Nếu muốn literal `$1`, dùng `Matcher.quoteReplacement("$1")` |
| Replacement chứa dấu `$` do người dùng nhập gây lỗi tham chiếu nhóm | Chưa escape cú pháp replacement | Dùng `Matcher.quoteReplacement(userReplacement)` |
| Dấu `\` biến mất hoặc replacement lỗi | Backslash được Matcher dùng để escape ký tự tiếp theo | Dùng `Matcher.quoteReplacement(...)`; hoặc đặt đủ backslash trong source |
| Dùng `Pattern.quote(...)` cho replacement | Quote nhầm cú pháp regex thay vì replacement | Dùng `Matcher.quoteReplacement(...)` |
| Dùng `Matcher.quoteReplacement(...)` cho mẫu tìm | Quote nhầm phía và có thể tạo regex sai nghĩa | Dùng `Pattern.quote(...)` |
| Muốn chèn group `$1` nhưng toàn bộ replacement bị quote | `quoteReplacement` biến `$` thành literal | Giữ cú pháp `$1` trực tiếp và escape riêng các ký tự literal |
| `"\d+"` hoặc `"\."` không biên dịch | Java string literal không nhận escape `\d` hay `\.` | Viết `"\\d+"` hoặc `"\\."` |

Một số ngoại lệ thường gặp:

- `PatternSyntaxException`: cú pháp regex không hợp lệ, chẳng hạn dấu `[` chưa đóng.
- `IllegalArgumentException`: một số dạng replacement có tham chiếu nhóm sai cú pháp (chẳng hạn `$` đứng một mình).
- `IndexOutOfBoundsException`: tham chiếu đến nhóm đánh số không tồn tại, ví dụ `$1` khi pattern không khai báo nhóm bắt nào.

Đừng dựa vào việc bắt rồi bỏ qua ngoại lệ để xử lý dữ liệu đầu vào; hãy phân biệt ngay từ đầu trường hợp người dùng cung cấp **văn bản literal** hay **regex/replacement template**.

## 8. Bài tập áp dụng

**Bài 1.** Tìm dấu `$` thật trong `"Total: $12"` rồi đổi thành `"USD "`.

```java
System.out.println("Total: $12".replaceAll("\\$", "USD "));
// Total: USD 12
```

Đây là escape của **mẫu tìm**. Dấu `$` ở replacement `"USD "` không có mặt nên không cần quote.

**Bài 2.** Thay dấu chấm trong `"a.b"` bằng đúng văn bản `"$2\path"`.

```java
String replacement = "$2\\path";
System.out.println("a.b".replaceAll(
        "\\.", Matcher.quoteReplacement(replacement)));
// a$2\pathb
```

Ở đây `$2` là văn bản literal, **không** tham chiếu nhóm 2. Dấu `\` cũng phải giữ nguyên.

**Bài 3.** Đổi `"code-7"` thành `"7/code"` thông qua nhóm bắt:

```java
System.out.println("code-7".replaceAll(
        "([A-Za-z]+)-(\\d+)", "$2/$1"));
// 7/code
```

Trường hợp này `$2` và `$1` **phải** mang ý nghĩa nhóm bắt, nên không quote replacement.

**Bài 4.** Vì sao đoạn này không nhất thiết cho đúng kết quả mong muốn?

```java
String find = "a.b";
String replacement = "$1";
String output = "a.b".replaceAll(find, replacement);
```

Đáp án: `find` được xử lý như regex, trong đó dấu chấm khớp bất kỳ ký tự; `replacement` chứa `$1` nhưng pattern không định nghĩa group 1 nên gây lỗi. Nếu mục tiêu là thay một chuỗi literal bằng chính `$1`, viết:

```java
String output = "a.b".replaceAll(
        Pattern.quote(find),
        Matcher.quoteReplacement(replacement));
System.out.println(output); // $1
```

Hoặc chỉ cần `"a.b".replace("a.b", "$1")` nếu không có yêu cầu dùng regex.

## 9. Checklist trước khi thay thế

1. **Mẫu tìm là regex thực sự hay văn bản literal?** Regex thực sự thì viết/kiểm tra escape theo `Pattern`; văn bản literal thì dùng `Pattern.quote` hoặc `String.replace`.
2. **Replacement là mẫu có group `$1`/`${name}` hay văn bản literal?** Mẫu group thì giữ đúng cú pháp tham chiếu; văn bản literal thì dùng `Matcher.quoteReplacement`.
3. **Các dấu `\` trong Java source đã được viết đúng chưa?** Nên kiểm tra riêng chuỗi **sau khi Java phân tích string literal** và cách regex/Matcher phân tích chuỗi đó.
4. **Có group phù hợp với replacement không?** `$1` đòi hỏi group 1; `${name}` đòi hỏi group có tên `name`.
5. **Có dữ liệu động chứa `$`, `\`, `.`, `[`...?** Quote đúng từng phía; nếu không cần regex, chọn `String.replace` để giảm khả năng nhầm lẫn.

**Kết luận:** `Pattern.quote` và `Matcher.quoteReplacement` giải quyết **hai vấn đề độc lập**. Escape regex quyết định **khớp cái gì**; escape replacement quyết định **chèn cái gì**. Trong Java source còn có lớp escape thứ ba cho dấu backslash. Xác định rõ ba lớp này giúp xử lý chính xác ký tự đặc biệt và nhóm bắt khi gọi `replaceAll`, `replaceFirst` hoặc `Matcher`.

**Tham khảo chính thức:** [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html), [Java SE 17 — Matcher.appendReplacement / quoteReplacement / replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html), [Java SE 17 — String.replaceAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#replaceAll(java.lang.String,java.lang.String)).