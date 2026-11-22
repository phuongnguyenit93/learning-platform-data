# Pattern.quote: tìm dữ liệu nguyên văn khi làm việc với regex trong Java

## 1. Vấn đề: dữ liệu cần tìm có thể bị hiểu thành biểu thức chính quy

Trong Java, các API như `Pattern.compile(regex)`, `String.matches(regex)`, `String.split(regex)` và `String.replaceAll(regex, replacement)` nhận **biểu thức chính quy** (regular expression). Nhưng chuỗi do người dùng nhập thường chỉ là **văn bản cần tìm nguyên văn**.

Ví dụ người dùng nhập `a.b` vì họ muốn tìm đúng ba ký tự: `a`, dấu chấm `.`, rồi `b`. Nếu viết:

```java
Pattern pattern = Pattern.compile("a.b");
System.out.println(pattern.matcher("a.b").matches()); // true
System.out.println(pattern.matcher("axb").matches()); // true
```

Cả hai lần kiểm tra đều trả về `true`. Lý do: trong regex, `.` mang nghĩa “một ký tự bất kỳ” (ngoại trừ một số ký tự kết thúc dòng theo chế độ mặc định). Nếu dữ liệu là `file[1].txt`, dấu ngoặc vuông và dấu chấm còn khiến biểu thức được hiểu khác hẳn chuỗi gốc.

Các ký tự như `.`, `*`, `+`, `?`, `^`, `$`, `(`, `)`, `[`, `]`, `{`, `}`, `|` và `\` có vai trò đặc biệt trong cú pháp regex tùy ngữ cảnh. Một dữ liệu đầu vào như `[` còn có thể làm `Pattern.compile` ném `PatternSyntaxException` vì regex không hợp lệ.

**Giải pháp:** khi cần tìm hoặc khớp **nguyên văn** một chuỗi bên trong API regex, dùng `Pattern.quote(text)`:

```java
import java.util.regex.Pattern;

String keyword = "a.b";
Pattern literalPattern = Pattern.compile(Pattern.quote(keyword));

System.out.println(literalPattern.matcher("a.b").matches()); // true
System.out.println(literalPattern.matcher("axb").matches()); // false
```

Ở đây `Pattern.quote(keyword)` khiến toàn bộ `keyword` được hiểu là dữ liệu literal; dấu chấm không còn là toán tử regex.

## 2. Pattern.quote hoạt động như thế nào?

Khai báo API:

```text
java.util.regex.Pattern.quote(String s) → String
```

Đây là cách ghi chữ ký để giải thích: trong mã Java thực tế, gọi `Pattern.quote(s)`; không khai báo lại phương thức đó.

`Pattern.quote(s)` trả về một **chuỗi biểu thức chính quy** có thể khớp đúng các ký tự trong `s` theo nghĩa nguyên văn. Phương thức **không thay đổi `s`**, không tìm dữ liệu và không tự biên dịch `Pattern`. Bạn đưa chuỗi kết quả vào `Pattern.compile(...)` hoặc một API có nhận regex.

Với dữ liệu thông thường, chuỗi regex được tạo có dạng `\Q...\E`: trong cú pháp regex Java, `\Q` bắt đầu vùng được coi là literal, `\E` kết thúc vùng đó.

```java
String literal = "a.b";
String safeRegex = Pattern.quote(literal);
System.out.println(safeRegex); // \Qa.b\E
```

Không cần tự ghép `"\Q"` và `"\E"` vào dữ liệu. Nếu chuỗi gốc chứa chính dãy ký tự `\E`, `Pattern.quote` vẫn xử lý đúng để giữ nguyên ý nghĩa literal. Ví dụ:

```java
String input = "\\E"; // Hai ký tự thực tế: dấu \ và chữ E
boolean matches = Pattern.compile(Pattern.quote(input))
        .matcher(input)
        .matches();
System.out.println(matches); // true
```

Lưu ý hai tầng cú pháp:

- **Java string literal:** `"\\E"` biểu diễn chuỗi runtime `\E`; dấu `\` phải được escape khi viết mã Java.
- **Java regex:** `Pattern.quote` xử lý tiếp chuỗi runtime đó để regex engine không diễn giải nó như một lệnh điều khiển regex.

**Quy tắc cốt lõi:** `Pattern.quote` là công cụ **escape chuỗi tìm kiếm (pattern)**. Nó không phải công cụ escape chuỗi **thay thế (replacement)**.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Tạo tệp `PatternQuoteDemo.java` với toàn bộ mã dưới đây:

```java
import java.util.Arrays;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class PatternQuoteDemo {
    public static void main(String[] args) {
        String text = "a.b | axb | a.b";
        String keyword = "a.b";

        // Không quote: "." được hiểu là ký tự bất kỳ.
        System.out.println("raw matches axb: " +
                Pattern.compile(keyword).matcher("axb").matches());

        // Quote: chỉ khớp đúng chuỗi literal "a.b".
        Pattern literal = Pattern.compile(Pattern.quote(keyword));
        System.out.println("literal matches axb: " +
                literal.matcher("axb").matches());

        Matcher matcher = literal.matcher(text);
        int count = 0;
        while (matcher.find()) {
            System.out.println("found: " + matcher.group());
            count++;
        }
        System.out.println("count: " + count);

        // Dấu "|" là ký tự đặc biệt của regex; giữ trường rỗng cuối.
        String[] fields = "red|green||".split(Pattern.quote("|"), -1);
        System.out.println("fields: " + Arrays.toString(fields));
        System.out.println("fields count: " + fields.length);

        // Pattern.quote bảo vệ phần cần tìm;
        // Matcher.quoteReplacement bảo vệ phần thay thế.
        String replacement = "$5\\path";
        String changed = Pattern.compile(Pattern.quote("a.b"))
                .matcher("a.b and a.b")
                .replaceAll(Matcher.quoteReplacement(replacement));
        System.out.println("replaced: " + changed);

        // Trường hợp chuỗi gốc chứa chính dấu kết thúc vùng quote.
        String special = "\\E";
        System.out.println("embedded E: " +
                Pattern.compile(Pattern.quote(special))
                        .matcher(special).matches());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac PatternQuoteDemo.java
java PatternQuoteDemo
```

Kết quả:

```text
raw matches axb: true
literal matches axb: false
found: a.b
found: a.b
count: 2
fields: [red, green, , ]
fields count: 4
replaced: $5\path and $5\path
embedded E: true
```

Khi đọc kết quả:

1. Không quote, regex `a.b` nhận cả `axb`; có quote, `a.b` chỉ khớp đúng `a.b`.
2. `matcher.find()` quét lần lượt các vùng khớp bên trong chuỗi dài. Trong `"a.b | axb | a.b"` có đúng **hai** lần xuất hiện literal `a.b`.
3. `split(Pattern.quote("|"), -1)` tách theo đúng dấu `|`; `-1` là tham số riêng của `split` để giữ hai trường rỗng ở cuối.
4. Chuỗi thay thế chứa cả `$` và `\` vẫn được chèn nguyên văn nhờ `Matcher.quoteReplacement`.
5. Trường hợp `\E` cũng khớp nguyên văn, chứng tỏ không cần tự xử lý thủ công dấu kết thúc vùng quote.

## 4. Chọn phương thức tìm kiếm đúng mục đích

Sau khi tạo `Pattern` từ literal, việc nhận kết quả phụ thuộc cách kiểm tra:

| Mục đích | API | Hành vi |
| --- | --- | --- |
| Tìm xem chuỗi có chứa dữ liệu nguyên văn hay không | `text.contains(keyword)` | Tìm literal, không cần regex. |
| Tìm một hay nhiều vị trí xuất hiện literal bằng regex | `Pattern.compile(Pattern.quote(keyword)).matcher(text).find()` | `find()` tìm một vùng khớp bên trong chuỗi. |
| Yêu cầu **toàn bộ** chuỗi bằng literal | `Pattern.compile(Pattern.quote(keyword)).matcher(text).matches()` | `matches()` chỉ đúng khi khớp toàn bộ đầu vào. |
| Xác định phần đầu của chuỗi bằng regex | `matcher.lookingAt()` | Kiểm tra một vùng khớp bắt đầu tại đầu input. |
| Tách theo dấu phân cách literal | `text.split(Pattern.quote(separator), -1)` | Dấu phân cách được hiểu nguyên văn; `-1` giữ trường rỗng cuối. |
| Thay toàn bộ chuỗi con literal | `text.replace(oldText, newText)` | Cả hai đối số đều là literal; không cần quote. |

Ví dụ phân biệt `find()` với `matches()`:

```java
Pattern p = Pattern.compile(Pattern.quote("api.v1"));
Matcher m = p.matcher("prefix-api.v1-suffix");

System.out.println(m.find()); // true
System.out.println(p.matcher("prefix-api.v1-suffix").matches()); // false
System.out.println(p.matcher("api.v1").matches()); // true
```

Đoạn mã trên là một ví dụ đặt trong một phương thức có `import java.util.regex.Pattern;` và `import java.util.regex.Matcher;`.

Đặc biệt, **không bắt buộc phải dùng regex** để kiểm tra chuỗi con nguyên văn. `String.contains` hoặc `String.indexOf` thường rõ ràng hơn cho việc tìm đơn giản. Dùng `Pattern.quote` khi thật sự đang làm việc với regex, ví dụ cần `Matcher` để lấy vị trí, cần ghép regex với dữ liệu literal, hoặc API yêu cầu đối số regex.

## 5. Ghép phần literal vào regex có chủ đích

Không phải mọi bài toán đều muốn biến **toàn bộ** biểu thức thành literal. Đôi khi ta muốn giữ một số thành phần regex (anchor, khoảng trắng linh hoạt, nhóm bắt) nhưng tên hoặc nhãn do người dùng cung cấp phải được tìm đúng nguyên văn.

Giả sử một dòng cấu hình có dạng `"status[0]: ACTIVE"`, trong đó `status[0]` là nhãn đầu vào:

```java
String label = "status[0]";
String line = "status[0]: ACTIVE";

Pattern pattern = Pattern.compile(
        "^" + Pattern.quote(label) + "\\s*:\\s*(.+)$");

Matcher matcher = pattern.matcher(line);
if (matcher.matches()) {
    System.out.println(matcher.group(1)); // ACTIVE
}
```

Ý nghĩa của từng đoạn:

- `^` và `$`: các anchor do người lập trình chủ động đặt ở đầu/cuối regex.
- `Pattern.quote(label)`: nhãn `status[0]` được khớp nguyên văn; `[0]` không biến thành character class.
- `\\s*:\\s*` trong mã Java: regex cho phép 0 hoặc nhiều ký tự khoảng trắng ở hai bên dấu hai chấm.
- `(.+)`: nhóm bắt nội dung ở cuối; `group(1)` lấy giá trị `ACTIVE`.

Nếu quote **toàn bộ** biểu thức `"^" + label + "\\s*:\\s*(.+)$"` thì các dấu `^`, `$`, `\s*` và `(.+)` cũng biến thành ký tự literal và mất chức năng regex. Chỉ quote **đoạn dữ liệu cần khớp nguyên văn**, giữ nguyên các thành phần regex có chủ đích.

## 6. Pattern.quote và Matcher.quoteReplacement là hai việc khác nhau

Với các API như `Matcher.replaceAll(replacement)`, chuỗi thay thế có cú pháp riêng:

- `$1`, `$2`… có thể tham chiếu đến nhóm bắt.
- `\` được dùng làm ký tự escape trong replacement.

Nếu replacement do người dùng nhập là `"$5\path"`, đưa trực tiếp vào `Matcher.replaceAll` có thể gây lỗi khi `$5` bị diễn giải như một tham chiếu nhóm không tồn tại, hoặc khiến dấu `\` không được giữ nguyên như mong muốn.

Để thay một literal bằng một literal thông qua regex:

```java
String original = "key[0] and key[0]";
String fromUser = "key[0]";
String replacement = "$5\\path";

String result = Pattern.compile(Pattern.quote(fromUser))
        .matcher(original)
        .replaceAll(Matcher.quoteReplacement(replacement));

System.out.println(result);
// $5\path and $5\path
```

Sơ đồ trách nhiệm:

```text
Dữ liệu cần tìm      --Pattern.quote--------> regex pattern literal
Dữ liệu cần thay thế --Matcher.quoteReplacement--> replacement literal
                                      |
                     Matcher.replaceAll(replacement)
```

Nếu chỉ cần thay chuỗi con literal, dùng API ngắn hơn và tự nhiên hơn:

```java
String result = original.replace(fromUser, replacement);
```

`String.replace(CharSequence, CharSequence)` thay chuỗi literal; còn `String.replaceAll(String, String)` nhận regex và replacement có ngữ nghĩa đặc biệt. Đừng nhầm tên `replace` với `replaceAll`.

## 7. Pattern.LITERAL có thay được Pattern.quote không?

Java cung cấp cờ `Pattern.LITERAL`:

```java
String keyword = "file[1].txt";

Pattern byQuote = Pattern.compile(Pattern.quote(keyword));
Pattern byFlag = Pattern.compile(keyword, Pattern.LITERAL);

System.out.println(byQuote.matcher(keyword).matches()); // true
System.out.println(byFlag.matcher(keyword).matches());  // true
```

Cả hai cách đều khiến nội dung `keyword` được hiểu là literal trong ví dụ trên. Khác biệt trong cách dùng:

- `Pattern.quote(keyword)` trả về **một chuỗi regex**; phù hợp khi cần chèn dữ liệu literal vào một regex lớn hơn, như `"^" + Pattern.quote(keyword) + "$"`.
- `Pattern.compile(keyword, Pattern.LITERAL)` áp dụng cách hiểu literal cho **toàn bộ** chuỗi pattern được biên dịch. Nếu đưa cả `"^"` hoặc `".*"` vào chuỗi với cờ này, các ký tự đó cũng sẽ được tìm như ký tự thường.

Khi chỉ cần biên dịch một pattern hoàn toàn literal, cả hai là lựa chọn hợp lệ. Khi cần pha trộn literal và cú pháp regex, `Pattern.quote` cho từng phần dữ liệu thuận tiện hơn.

## 8. Lỗi phổ biến và trường hợp biên

### 8.1. Tự escape từng ký tự đặc biệt

Ví dụ thủ công thay mọi dấu chấm bằng `\\.` có thể giải quyết riêng dấu chấm, nhưng chưa giải quyết `[`, `|`, `\` và nhiều ký tự khác. Regex còn có quy tắc escape khác nhau tùy vị trí; càng nhiều lần biến đổi thủ công càng dễ dẫn đến escape thiếu hoặc thừa.

Hãy dùng `Pattern.quote` cho **nguyên một giá trị literal**. Nếu đầu vào có thể chứa `\E`, hàm này cũng xử lý được; không tự ghép `\Q`/`\E` rồi hy vọng đầu vào luôn “đơn giản”.

### 8.2. Nhầm giá trị literal với regex hợp lệ do người dùng cố ý nhập

Nếu chức năng sản phẩm là **“Tìm theo regex”**, việc áp dụng `Pattern.quote` lên toàn bộ mẫu đầu vào sẽ khiến các toán tử regex không còn hoạt động. Ví dụ người dùng cố ý nhập `a.*b` để khớp nhiều ký tự thì sau quote chương trình chỉ tìm văn bản `a.*b`.

Ngược lại, với chức năng **“Tìm nguyên văn”**, không quote dữ liệu rồi đưa trực tiếp cho regex engine sẽ tạo hành vi sai hoặc lỗi `PatternSyntaxException`. Phải xác định đúng chế độ tìm kiếm dựa trên yêu cầu.

### 8.3. Nhầm quote với kiểm soát phân biệt chữ hoa/thường

`Pattern.quote` chỉ xử lý cú pháp regex, không tự chuyển chữ hoa/thường. Mặc định, tìm `"Java"` không đồng nghĩa tìm `"java"`.

Nếu cần tìm không phân biệt chữ hoa/thường bằng regex, có thể dùng cờ thích hợp:

```java
Pattern pattern = Pattern.compile(
        Pattern.quote("Java"),
        Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);

System.out.println(pattern.matcher("java").matches()); // true
```

Các cờ này ảnh hưởng quy tắc khớp, còn `Pattern.quote` vẫn chịu trách nhiệm xem đầu vào là literal. Với yêu cầu Unicode phức tạp, cần kiểm tra rõ chính sách so sánh văn bản của ứng dụng.

### 8.4. Đầu vào `null` hoặc rỗng

`Pattern.quote(null)` không tạo ra regex hợp lệ để tìm, mà ném `NullPointerException`. Với chuỗi rỗng `""`, việc quote là hợp lệ, nhưng mẫu rỗng có thể khớp ở các vị trí độ dài 0; ví dụ `find()` có thể trả về `true` ngay cả khi người dùng chưa gõ từ khóa.

Nếu chức năng yêu cầu từ khóa có ít nhất một ký tự, hãy kiểm tra trước:

```java
if (keyword == null || keyword.isEmpty()) {
    throw new IllegalArgumentException("Từ khóa phải có nội dung");
}
Pattern pattern = Pattern.compile(Pattern.quote(keyword));
```

Không tùy tiện gọi `trim()` hoặc `strip()` nếu khoảng trắng đầu/cuối là một phần dữ liệu người dùng thực sự muốn tìm.

### 8.5. Quote pattern không điều khiển cách split giữ phần tử rỗng

`Pattern.quote("|")` quyết định **dấu `|` là dấu phân cách literal**; nó không quyết định mảng kết quả có giữ trường rỗng cuối hay không.

```java
String s = "a|b||";
System.out.println(Arrays.toString(s.split(Pattern.quote("|"))));
// [a, b]

System.out.println(Arrays.toString(s.split(Pattern.quote("|"), -1)));
// [a, b, , ]
```

Ở đây `-1` là lựa chọn của `String.split` để giữ mọi phần tử rỗng cuối. Ví dụ này cần đặt trong phương thức có `import java.util.Arrays;` và `import java.util.regex.Pattern;`.

### 8.6. Biên dịch Pattern nhiều lần không cần thiết

`Pattern` là đối tượng đã biên dịch regex và có thể được dùng lại cho nhiều lần so khớp. Nếu cùng một từ khóa được tìm nhiều lần, có thể biên dịch một lần rồi gọi `pattern.matcher(text)` cho từng chuỗi:

```java
Pattern pattern = Pattern.compile(Pattern.quote(keyword));

for (String line : lines) {
    if (pattern.matcher(line).find()) {
        System.out.println(line);
    }
}
```

Đây là đoạn mã minh họa giả sử `keyword` là `String` và `lines` là tập hợp dòng văn bản đã có. `Pattern` có thể tái sử dụng; không chia sẻ cùng một đối tượng `Matcher` đang thay đổi trạng thái giữa các luồng mà không đồng bộ.

## 9. Tự kiểm tra

Hãy xác định câu lệnh nào trả về `true`:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `Pattern.compile("a.b").matcher("axb").matches()` | `true` | Dấu chấm là toán tử regex. |
| `Pattern.compile(Pattern.quote("a.b")).matcher("axb").matches()` | `false` | Dấu chấm phải là ký tự thật. |
| `Pattern.compile(Pattern.quote("a.b")).matcher("x-a.b-y").find()` | `true` | `find()` tìm trong một phần của chuỗi. |
| `Pattern.compile(Pattern.quote("a.b")).matcher("x-a.b-y").matches()` | `false` | `matches()` yêu cầu toàn bộ chuỗi khớp. |
| `Pattern.compile(Pattern.quote("[0]")).matcher("[0]").matches()` | `true` | Dấu ngoặc vuông được hiểu literal. |
| `Pattern.compile(Pattern.quote("a|b")).matcher("a").matches()` | `false` | `|` không còn là toán tử lựa chọn. |

Một bài tập thực hành: xây dựng chức năng nhận một từ khóa bất kỳ từ người dùng, tìm mọi vị trí xuất hiện của từ khóa đó trong một câu rồi in `matcher.start()` và `matcher.end()`. Thử lần lượt với `a.b`, `[0]`, `C:\temp`, `.*` và `\E`. Nếu đây là chế độ tìm nguyên văn, cả năm chuỗi phải được xử lý như dữ liệu, không phải mã lệnh regex.

## 10. Ghi nhớ

- **`Pattern.quote(input)` biến dữ liệu thành regex literal**; dùng khi API đang yêu cầu regex nhưng người dùng muốn tìm nguyên văn.
- **`find()` tìm vùng khớp**, **`matches()` khớp toàn bộ đầu vào**; quote không thay đổi khác biệt này.
- Khi cần kết hợp dữ liệu nguyên văn với cú pháp regex, chỉ quote **phần dữ liệu**, ví dụ `"^" + Pattern.quote(label) + "$"`.
- Với chuỗi **thay thế**, dùng `Matcher.quoteReplacement(replacement)` nếu gọi `Matcher.replaceAll`; `Pattern.quote` không giải quyết vấn đề replacement.
- Với tìm hoặc thay thế literal đơn giản, ưu tiên `String.contains`, `String.indexOf` hoặc `String.replace` vì chúng diễn đạt trực tiếp ý định.
- `Pattern.LITERAL` là lựa chọn hợp lệ khi muốn coi **toàn bộ pattern** là văn bản nguyên văn.
