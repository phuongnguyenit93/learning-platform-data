# Phương thức biến đổi trả kết quả thay vì sửa chuỗi nguồn trong Java

## 1. Mục tiêu và ý tưởng cốt lõi

Trong Java, `String` là **immutable** (*bất biến*): nội dung của một đối tượng `String` không thể bị sửa sau khi tạo. Khi cần viết hoa, viết thường, bỏ khoảng trắng, thay văn bản, nối hoặc cắt chuỗi, các phương thức tương ứng **trả về giá trị kết quả** để người gọi sử dụng; chúng không sửa nội dung đối tượng nguồn.

Sau bài này, bạn cần giải thích và thực hành được:

1. Phân biệt **biến tham chiếu**, **đối tượng String** và **giá trị trả về** của phương thức.
2. Phát hiện lỗi gọi `strip()`, `replace()`, `toUpperCase()`… nhưng bỏ kết quả.
3. Biết khi nào **gán lại biến**, khi nào **giữ bản gốc và tạo biến kết quả**, khi nào **trả kết quả** từ phương thức của mình.
4. Áp dụng *method chaining* đúng thứ tự.
5. Đối chiếu `String` với `StringBuilder` và xử lý các trường hợp `null`, regex, Unicode, `Locale`, hiệu năng.

Ví dụ trong bài dùng Java 17+; cần biết biến, phép gán, đối tượng, lời gọi phương thức và kiểu giá trị trả về.

## 2. Bất biến không có nghĩa biến không thể gán lại

Xem đoạn mã:

~~~java
String source = "java";
String upper = source.toUpperCase();

System.out.println(source); // java
System.out.println(upper);  // JAVA
~~~

Đối tượng biểu diễn `"java"` **không đổi**. `toUpperCase()` trả kết quả `"JAVA"` và biến `upper` nhận kết quả này. Hai biến chứa các **giá trị** khác nhau, trong khi việc đọc lại `source` vẫn nhận `"java"`.

Ba khái niệm dễ nhầm:

- **Đối tượng String:** mang nội dung bất biến.
- **Biến tham chiếu:** có thể trỏ sang một đối tượng chuỗi khác bằng phép gán, trừ khi biến được khai báo `final`.
- **Giá trị trả về:** kết quả của thao tác. Nếu bỏ qua, hiệu ứng biến đổi mong đợi thường không xuất hiện ở biến nguồn.

Ví dụ minh họa:

~~~text
Ban đầu:
source ───────► "java"

source.toUpperCase() trả về:
                 "JAVA"

Không gán kết quả:
source ───────► "java"

Gán source = source.toUpperCase():
source ───────► "JAVA"
               (đối tượng "java" gốc không bị sửa)
~~~

**Điểm tinh tế:** trả kết quả `String` **không đồng nghĩa luôn tạo đối tượng mới**. Khi giá trị không cần thay đổi, một số phương thức có thể trả lại cùng tham chiếu. Tính bất biến bảo đảm **nội dung nguồn không đổi**; không bảo đảm số lần cấp phát. Vì thế, dùng `equals()` khi cần kiểm tra hai chuỗi có cùng nội dung; `==` dùng để so sánh danh tính tham chiếu, không phù hợp với phần lớn phép so sánh văn bản.

## 3. Lỗi điển hình: gọi phương thức rồi bỏ giá trị trả về

~~~java
String text = "  java string  ";
text.strip();
text.toUpperCase();
text.replace("java", "JAVA");

System.out.println("[" + text + "]");
// [  java string  ]
~~~

Đoạn mã biên dịch bình thường, không ném lỗi, nhưng `text` không đổi. Mỗi phép biến đổi đã trả về kết quả **không được sử dụng**.

Sửa bằng cách nhận kết quả:

~~~java
String text = "  java string  ";
text = text.strip();
text = text.toUpperCase();
text = text.replace("JAVA", "Java");

System.out.println("[" + text + "]");
// [Java STRING]
~~~

Ở đây `text = ...` cập nhật **tham chiếu lưu trong biến**, không làm sửa một đối tượng `String` tại chỗ.

Nếu muốn giữ dữ liệu nhập nguyên bản:

~~~java
String raw = "  java string  ";
String display = raw.strip().toUpperCase();

System.out.println("raw=[" + raw + "]");
// raw=[  java string  ]
System.out.println("display=[" + display + "]");
// display=[JAVA STRING]
~~~

Đặt tên `raw`/`display` giúp phân biệt bản gốc và bản xử lý. Việc giữ nguồn đặc biệt hữu ích khi cần giải thích, đối chiếu hoặc kiểm thử quy tắc biến đổi.

## 4. Các phương thức biến đổi trả về String

| Phương thức | Mục đích | Ví dụ kết quả |
| --- | --- | --- |
| `toUpperCase()`, `toLowerCase()` | Đổi chữ hoa/thường | `"Java".toUpperCase()` → `"JAVA"` |
| `strip()`, `stripLeading()`, `stripTrailing()` | Bỏ whitespace ở hai đầu / đầu / cuối | `" a ".strip()` → `"a"` |
| `trim()` | Bỏ ký tự đầu/cuối có mã `<= U+0020` theo đặc tả | `" a ".trim()` → `"a"` |
| `replace(old, new)` | Thay **literal** | `"a-b".replace("-", ":")` → `"a:b"` |
| `replaceAll(regex, replacement)` | Thay tất cả đoạn khớp **regex** | `"a1b2".replaceAll("\\d", "#")` → `"a#b#"` |
| `replaceFirst(regex, replacement)` | Thay phần khớp regex đầu tiên | `"a1b2".replaceFirst("\\d", "#")` → `"a#b2"` |
| `substring(begin, end)` | Trích đoạn, cận cuối không lấy | `"Java".substring(1, 3)` → `"av"` |
| `concat(other)` và phép `+` | Nối chuỗi | `"Java".concat(" 17")` → `"Java 17"` |
| `repeat(count)` | Lặp nội dung | `"ab".repeat(2)` → `"abab"` |
| `formatted(args...)`, `String.format(...)` | Dựng chuỗi từ định dạng | `"%s-%d".formatted("A", 2)` → `"A-2"` |
| `indent(n)`, `stripIndent()` | Biến đổi cách thụt lề của văn bản đa dòng | Kết quả có thể khác cả khoảng trắng lẫn dấu xuống dòng |

**Không phải mọi phương thức được gọi trên String đều trả String.** Ví dụ:

~~~java
String data = "a,b,c";
int length = data.length();
boolean exists = data.contains("a");
String[] pieces = data.split(",");
~~~

`length()` trả `int`, `contains()` trả `boolean` và `split()` trả `String[]`. Tất cả đều **không sửa** `data` nhưng có kiểu trả về khác nhau. Các phương thức như `indexOf()`, `isBlank()`, `matches()` hoặc `codePoints()` cũng có kiểu trả về riêng. Hãy đọc chữ ký trong Javadoc trước khi viết code.

## 5. Ba cách nhận kết quả đúng

### 5.1. Gán lại khi không còn cần biến chứa bản cũ

~~~java
String name = "  alice  ";
name = name.strip();
name = name.replace("alice", "Alice");
// name giờ chứa "Alice"
~~~

Giá trị chuỗi ban đầu không bị sửa. Điều thay đổi là **giá trị tham chiếu của biến** `name`.

### 5.2. Dùng biến mới để giữ cả dữ liệu thô và đã xử lý

~~~java
String input = "  alice  ";
String normalized = input.strip().replace("alice", "Alice");

// input: "  alice  "
// normalized: "Alice"
~~~

Cách này hữu ích khi mỗi phiên bản có vai trò khác nhau. Không tự động bỏ dấu, đổi case hoặc cắt chuỗi nếu nghiệp vụ chưa quy định vì có thể mất thông tin.

### 5.3. Trả kết quả khi viết phương thức của mình

**Sai:**

~~~java
static String normalizeWrong(String input) {
    input.strip();
    input.toLowerCase(java.util.Locale.ROOT);
    return input; // Trả về nguồn, không phải kết quả đã xử lý
}
~~~

**Đúng:**

~~~java
static String normalizeCorrect(String input) {
    return input.strip().toLowerCase(java.util.Locale.ROOT);
}
~~~

Ở ví dụ đúng, tham số `input` phải khác `null`. Quy tắc xử lý `null` nên được viết rõ trong hợp đồng hàm.

## 6. Method chaining: kết quả trước là đầu vào của bước sau

~~~java
String result = "  java core  "
        .strip()
        .replace("java", "Java")
        .toUpperCase();

System.out.println(result); // JAVA CORE
~~~

Quá trình:

~~~text
"  java core  "
       │ strip()
       ▼
"java core"
       │ replace("java", "Java")
       ▼
"Java core"
       │ toUpperCase()
       ▼
"JAVA CORE"
~~~

**Thứ tự của phép biến đổi có thể làm thay đổi kết quả**:

~~~java
String text = "Java";

String first = text.toLowerCase().replace("java", "core");
String second = text.replace("java", "core").toLowerCase();

System.out.println(first);  // core
System.out.println(second); // java
~~~

`replace("java", "core")` phân biệt chữ hoa/chữ thường; khi áp dụng trực tiếp trên `"Java"` nó không thay gì. Khi đổi thành chữ thường trước rồi thay mới tìm thấy đoạn cần thay.

**Quy tắc chaining:**

- Lời gọi kế tiếp phải tương thích **kiểu trả về** của lời gọi trước: `text.strip().replace(...)` đúng, nhưng `text.length().strip()` sai vì `length()` trả `int`.
- Dùng biến trung gian khi cần debug từng bước hoặc pipeline quá dài.
- Lệnh cuối phải được sử dụng (gán, `return`, truyền làm đối số…) nếu kết quả xử lý là mục tiêu của chương trình.
- Chaining là cách diễn đạt xử lý tuần tự, **không phải** cách làm cho đối tượng `String` trở nên mutable.

## 7. Đối chiếu với StringBuilder: mutable thật sự

`StringBuilder` khác `String` ở chỗ nó **thay đổi trạng thái bên trong** khi gọi `append()`, `insert()`, `delete()` hoặc `replace()`.

~~~java
String text = "A";
text.concat("B");                // Giá trị trả về bị bỏ
System.out.println(text);        // A

StringBuilder builder = new StringBuilder("A");
builder.append("B");             // Chính builder thay đổi
System.out.println(builder);     // AB
~~~

Với `StringBuilder`, `append()` vừa thay builder, vừa trả lại tham chiếu đến builder để gọi tiếp. Với `String`, `concat()` trả về kết quả nối, còn giá trị nguồn giữ nguyên.

Hai cách sau đều tạo ra giá trị `"ab"`, nhưng cơ chế khác nhau:

~~~java
String s = "a";
s = s + "b"; // Gán lại biến s bằng kết quả String

StringBuilder b = new StringBuilder("a");
b.append("b"); // Sửa nội dung đối tượng b
~~~

**`final` khác immutable:**

~~~java
final String fixed = "a";
String changed = fixed.replace("a", "b"); // Hợp lệ
// fixed = changed; // Lỗi biên dịch: không được gán lại fixed

final StringBuilder editable = new StringBuilder("a");
editable.append("b"); // Hợp lệ: đối tượng builder vẫn mutable
~~~

`final` ngăn **gán lại một biến tham chiếu**; không tự làm cho đối tượng mà biến trỏ tới trở thành bất biến.

## 8. Trường hợp biên và lỗi thực tế

### 8.1. Rỗng, trắng và null

~~~java
String empty = "";
String blank = "   ";

System.out.println(empty.isEmpty()); // true
System.out.println(blank.isEmpty()); // false
System.out.println(blank.isBlank()); // true
System.out.println(blank.strip().isEmpty()); // true
~~~

`null` không phải chuỗi rỗng: `null.strip()` ném `NullPointerException`. Hai chính sách ví dụ:

~~~java
static String normalizeNullable(String text) {
    return text == null ? null : text.strip();
}

static String normalizeRequired(String text) {
    java.util.Objects.requireNonNull(text, "text");
    return text.strip();
}
~~~

Chọn một hợp đồng theo nhu cầu: trả `null`, chuyển dữ liệu thiếu thành `""` hoặc từ chối `null`. Đừng thay đổi ý nghĩa dữ liệu một cách ngầm định.

### 8.2. Không thay được thì kết quả vẫn bằng nội dung cũ

~~~java
String original = "Hello";
String after = original.replace("x", "y");
System.out.println(original.equals(after)); // true
~~~

Không tìm thấy `"x"` nên nội dung kết quả bằng nguồn. Điều này không chứng tỏ hai biến chắc chắn cùng một tham chiếu; quy tắc ổn định là **nguồn không đổi**, không phải **mỗi lần luôn có đối tượng mới**.

### 8.3. Replace literal khác replaceAll regex

~~~java
String path = "a.b.c";

String a = path.replace(".", "-");        // a-b-c
String b = path.replaceAll("\\.", "-");   // a-b-c
~~~

`replace(".", "-")` tìm dấu chấm literal. `replaceAll` nhận biểu thức chính quy; ký hiệu `.` trong regex đại diện cho hầu hết ký tự, nên muốn khớp dấu chấm thật phải dùng `\.`, được viết trong mã nguồn Java là `"\\."`.

Chú ý giá trị `replacement` của `replaceAll` còn có cú pháp cho `$` và `\`; khi muốn sử dụng chuỗi thay thế literal đến từ dữ liệu bên ngoài, dùng `java.util.regex.Matcher.quoteReplacement(replacement)` phù hợp.

### 8.4. Locale và chuyển chữ hoa/thường

`toLowerCase()` và `toUpperCase()` không có tham số sử dụng **locale mặc định**. Khi xử lý mã kỹ thuật cố định, truyền `Locale.ROOT` để không phụ thuộc locale người dùng:

~~~java
String key = "CONTENT-TYPE";
String lower = key.toLowerCase(java.util.Locale.ROOT);
System.out.println(lower); // content-type
~~~

Với ngôn ngữ tự nhiên, dùng locale phù hợp quy tắc nghiệp vụ. Một số chuyển đổi case có thể **thay đổi độ dài**, vì vậy không giả định một ký tự đầu vào luôn cho một `char` đầu ra.

### 8.5. Unicode khi cắt chuỗi

`length()` đếm **đơn vị UTF-16**, không phải số ký tự người dùng nhìn thấy:

~~~java
String value = "A😀B";
System.out.println(value.length()); // 4
System.out.println(value.codePointCount(0, value.length())); // 3
~~~

Một emoji có thể chiếm hai `char`. `substring()` cắt theo chỉ số UTF-16; nếu cắt giữa một surrogate pair, kết quả có thể không biểu diễn một ký tự Unicode hoàn chỉnh. Khi cần xử lý code points, sử dụng API như `codePoints()` và `offsetByCodePoints()`. Ký tự *grapheme* người dùng nhìn thấy còn có thể gồm nhiều code point. Bất biến **không** thay cho xử lý Unicode đúng.

### 8.6. Phương thức có thể ném ngoại lệ

`substring(begin, end)` có thể ném `StringIndexOutOfBoundsException` khi chỉ số sai; `repeat(n)` với `n < 0` ném `IllegalArgumentException`. Một phép biến đổi thất bại không làm sửa chuỗi nguồn, nhưng bạn vẫn phải xác minh đầu vào.

## 9. Chương trình hoàn chỉnh có thể biên dịch và chạy (Java 17+)

Tạo file **`ImmutableStringDemo.java`**:

~~~java
import java.util.Locale;

public class ImmutableStringDemo {
    public static void main(String[] args) {
        String raw = "  java-core  ";

        raw.strip();
        raw.toUpperCase(Locale.ROOT);
        System.out.println("raw=[" + raw + "]");

        String output = raw.strip()
                .replace("-", " ")
                .toUpperCase(Locale.ROOT);
        System.out.println("output=[" + output + "]");
        System.out.println("raw again=[" + raw + "]");

        String title = " hello ";
        title = title.strip();
        title = title.replace("hello", "Hello");
        System.out.println("title=[" + title + "]");

        String token = "a1b2";
        String redacted = token.replaceAll("\\d", "#");
        System.out.println("redacted=[" + redacted + "]");
        System.out.println("token=[" + token + "]");

        StringBuilder builder = new StringBuilder("A");
        builder.append("B");
        System.out.println("builder=" + builder);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac ImmutableStringDemo.java
java ImmutableStringDemo
~~~

**Stdout chính xác:**

~~~text
raw=[  java-core  ]
output=[JAVA CORE]
raw again=[  java-core  ]
title=[Hello]
redacted=[a#b#]
token=[a1b2]
builder=AB
~~~

Giải thích output:

1. Hai lời gọi trên `raw` không gán kết quả nên chuỗi nguồn giữ khoảng trắng đầu/cuối và chữ thường.
2. `output` nhận kết quả của `strip()` → `replace("-", " ")` → `toUpperCase(Locale.ROOT)`, thành `"JAVA CORE"`. Lời in `raw again` chứng minh nguồn vẫn giữ nguyên.
3. `title` được **gán lại** hai lần nên biến giữ bản cuối là `"Hello"`.
4. `replaceAll("\\d", "#")` thay các chữ số trong kết quả `redacted`, trong khi `token` vẫn `"a1b2"`.
5. `append("B")` thay nội dung `builder`, chứng minh đối tượng mutable hoạt động khác `String`.

Hãy tự thay đầu vào, dự đoán toàn bộ stdout rồi chạy để kiểm chứng. Sự nhất quán giữa dự đoán và chạy thật quan trọng hơn thuộc tên phương thức.

## 10. Ảnh hưởng đến hiệu năng và thiết kế

Bất biến có thể khiến việc xây dựng chuỗi qua nhiều thao tác tạo ra các giá trị trung gian; cấp phát và tối ưu cụ thể phụ thuộc phương thức và compiler/JVM. Không suy luận rằng **mọi** lời gọi trả về một đối tượng mới, hoặc rằng dùng `String` luôn chậm.

Ví dụ nối chuỗi trong vòng lặp:

~~~java
String result = "";
for (int i = 0; i < 1000; i++) {
    result += i;
}
~~~

Mã chạy đúng về logic nhưng phép nối tích lũy có thể tạo nhiều giá trị trung gian. Thay vào đó, thường thích hợp dùng:

~~~java
StringBuilder builder = new StringBuilder();
for (int i = 0; i < 1000; i++) {
    builder.append(i);
}
String result = builder.toString();
~~~

Nguyên tắc chọn công cụ: dùng `String` để **lưu và trao đổi giá trị văn bản**, dùng `StringBuilder` khi **xây dựng văn bản qua nhiều lần bổ sung**, rồi chuyển về `String` bằng `toString()`. Đo hiệu năng nếu đây là điểm nghẽn thực tế; phép nối `+` ngắn không cần chuyển sang builder một cách máy móc.

Vì một đối tượng `String` không thể bị sửa nội dung, việc cùng đọc một chuỗi qua nhiều tham chiếu trở nên an toàn về mặt nội dung. Nhưng **biến tham chiếu có thể gán lại** dùng chung giữa các luồng vẫn cần quy tắc công bố và đồng bộ thích hợp; immutable không tự giải quyết mọi vấn đề concurrency.

## 11. Bài tập và cách tự kiểm tra

### Bài tập 1 — Dự đoán rồi chạy

~~~java
String a = "Hello";
a.replace("H", "J");
String b = a.toLowerCase();
System.out.println(a);
System.out.println(b);
~~~

Kết quả: `Hello` và `hello`. Chữ `H` không thay vì kết quả `replace()` bị bỏ. `b` nhận kết quả viết thường nên có nội dung khác `a`.

### Bài tập 2 — Sửa lỗi

Viết hàm trả `"java core"` từ `"  Java CORE  "` bằng `strip()` và `toLowerCase(Locale.ROOT)`. Viết thử phiên bản **sai do bỏ giá trị trả về**, sau đó sửa bằng `return input.strip().toLowerCase(Locale.ROOT);`.

### Bài tập 3 — Thứ tự khác, kết quả khác

Cho `String x = "JAVA";`. So sánh:

~~~java
x.toLowerCase(java.util.Locale.ROOT).replace("java", "core");
x.replace("java", "core").toLowerCase(java.util.Locale.ROOT);
~~~

Kết quả lần lượt là `"core"` và `"java"`. Giải thích việc `replace()` phân biệt chữ hoa/chữ thường.

### Bài tập 4 — Hợp đồng null

Tạo hàm `normalize(String s)` nhận chuỗi có thể `null`. Chọn **một** quy tắc được công bố rõ: trả `null`, trả `""` hoặc ném ngoại lệ. Thử `null`, `""`, `" "`, `" A "`.

### Bài tập 5 — Giữ đầu vào nguyên bản

Với `String raw = "  Cà phê Đắk Lắk  ";`, tạo biến `display` bằng `strip()`. Chứng minh `raw` vẫn chứa khoảng trắng. Không tự ý xóa dấu hay chuyển chữ thường vì đó là thay đổi ý nghĩa văn bản ngoài yêu cầu.

### Bài tập 6 — Mutable và immutable

Dùng `StringBuilder` ghép các số `1`, `2`, `3` với dấu phẩy; gọi `toString()` để giữ bản hoàn chỉnh. Sau đó thêm `4` vào builder, in cả hai để chứng minh bản `String` vừa tạo vẫn không thay đổi.

### Checklist khi review code

- Lời gọi trên `String` trả về kiểu gì: `String`, mảng, số, boolean hay stream?
- Giá trị kết quả đã được **gán, return, truyền tiếp hoặc sử dụng** chưa?
- Có muốn giữ bản gốc không? Nếu có, đặt tên riêng cho bản xử lý.
- Có điều kiện nào phụ thuộc thứ tự các bước hoặc phân biệt chữ hoa/thường?
- Có yêu cầu xử lý `null`, chuỗi trắng, Unicode hay `Locale` đặc biệt?
- Phương thức `replaceAll()` đang nhận **regex** hay người viết nhầm với chuỗi literal?
- Biến `final` có bị hiểu sai là làm cho mọi đối tượng mutable trở nên bất biến?
- Khi nối nhiều lần, có cần `StringBuilder` không?

**Quy tắc nhớ lâu:**

> Phương thức biến đổi trên `String` không sửa chuỗi nguồn. Hãy sử dụng giá trị trả về. Gán lại biến là thay **tham chiếu** mà biến giữ; không phải thay nội dung của đối tượng `String` gốc.

Hoàn thành bài khi bạn dự đoán được giá trị biến trước/sau lời gọi, phát hiện được thao tác bị bỏ kết quả, viết được hàm biến đổi giữ nguồn và phân biệt rõ `String` với `StringBuilder`.

## 12. Tài liệu chuẩn để tra cứu

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): chữ ký và hợp đồng `strip()`, `replace()`, `substring()`, `toLowerCase()`, `concat()`, `repeat()`, `formatted()`…
- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): các thao tác thay đổi nội dung builder và `toString()`.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): ý nghĩa locale khi xử lý văn bản.
- [Java SE 17 — Matcher](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html): quy tắc replacement của regex và `quoteReplacement()`.
