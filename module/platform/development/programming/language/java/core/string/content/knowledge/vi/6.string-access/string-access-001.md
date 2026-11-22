# `String.length()` và `String.isEmpty()` trong Java

Một chương trình xử lý văn bản thường phải trả lời hai câu hỏi: **chuỗi dài bao nhiêu?** và **chuỗi có rỗng hay không?** Java cung cấp trực tiếp hai phương thức của lớp `java.lang.String`:

- `int length()`: trả về **số đơn vị mã UTF-16 (UTF-16 code units)** có trong chuỗi.
- `boolean isEmpty()`: trả về `true` khi và chỉ khi `length() == 0`.

Hai phương thức không sửa nội dung `String`, không nhận tham số và rất phù hợp cho các điều kiện kiểm tra thông thường. Điều quan trọng nhất là hiểu chính xác từ **“độ dài”** và **“rỗng”** ở đây, đặc biệt khi chuỗi chứa dấu cách, emoji hoặc dữ liệu có thể là `null`.

## 1. `length()` trả về gì?

Cú pháp:

```java
int count = text.length();
```

`length()` trả về một số nguyên không âm. Với chuỗi ASCII đơn giản, kết quả thường trùng với số ký tự người đọc nhìn thấy:

```java
"".length()       // 0
"A".length()      // 1
"Java".length()   // 4
"Java 17".length() // 7: dấu cách ở giữa cũng được tính
"  ".length()     // 2: hai dấu cách
"\n".length()     // 1: một ký tự xuống dòng
"\r\n".length()   // 2: hai đơn vị mã (CR và LF)
```

Đây là các biểu thức minh họa, không phải tệp Java độc lập. Kết quả `length()` bao gồm **mọi** đơn vị mã UTF-16 trong chuỗi, kể cả khoảng trắng và ký tự điều khiển; phương thức không tự loại bỏ, cắt tỉa hay bỏ qua ký tự nào.

### Vì sao không gọi đơn giản là “số ký tự”?

Java `String` sử dụng mô hình chỉ số UTF-16 cho `length()`, `charAt()` và `substring()`. Một ký tự Unicode có thể được biểu diễn bằng **một** hoặc **hai** đơn vị mã UTF-16:

- Phần lớn ký tự thường gặp trong BMP (Basic Multilingual Plane), ví dụ `A`, `á` hoặc chữ Hán phổ biến: **1** đơn vị mã UTF-16.
- Một ký tự Unicode ngoài BMP, ví dụ nhiều emoji: **2** đơn vị mã UTF-16, dưới dạng một *surrogate pair*.

Vì vậy, `length()` **không phải** phép đếm số Unicode code points, không phải số chữ/grapheme mà người dùng nhìn thấy, và cũng không phải số byte khi lưu UTF-8.

Có ba khái niệm khác nhau:

| Thước đo | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| UTF-16 code units | Đơn vị dùng làm chỉ số trong `String` | `s.length()` |
| Unicode code points | Các giá trị Unicode logic trong một dãy UTF-16 | `s.codePointCount(0, s.length())` |
| Bytes theo một encoding | Kích thước khi mã hóa chuỗi thành byte | `s.getBytes(StandardCharsets.UTF_8).length` cho UTF-8 |

Một **grapheme cluster** (ví dụ chữ cái kết hợp dấu hoặc emoji có nhiều thành phần) có thể gồm nhiều Unicode code points; do đó ngay cả `codePointCount()` cũng không bảo đảm đếm đúng số ký tự người dùng cảm nhận. Khi phải giới hạn “số ký tự hiển thị”, cần tiêu chuẩn phân đoạn grapheme phù hợp, thay vì chỉ dựa vào `length()`.

## 2. `isEmpty()` kiểm tra gì?

Cú pháp:

```java
boolean empty = text.isEmpty();
```

Với một đối tượng `String` khác `null`, hai điều kiện dưới đây **tương đương về kết quả**:

```java
text.isEmpty()
text.length() == 0
```

Có thể coi `isEmpty()` là cách diễn đạt trực tiếp ý định: **“Chuỗi có độ dài bằng 0 không?”**.

Ví dụ:

| Giá trị chuỗi | `length()` | `isEmpty()` | Giải thích |
| --- | ---: | --- | --- |
| `""` | 0 | `true` | Không có đơn vị mã nào. |
| `"Java"` | 4 | `false` | Bốn chữ cái ASCII. |
| `" "` | 1 | `false` | Có một dấu cách. |
| `"  "` | 2 | `false` | Có hai dấu cách. |
| `"\t"` | 1 | `false` | Có một tab. |
| `"\n"` | 1 | `false` | Có một ký tự xuống dòng. |
| `" \t\n"` | 3 | `false` | Chỉ có whitespace nhưng vẫn có nội dung theo nghĩa mã UTF-16. |

`isEmpty()` **không** tự động loại bỏ khoảng trắng, và **không** trả về `true` chỉ vì chuỗi “nhìn như không có chữ”. Nếu yêu cầu nghiệp vụ là “người dùng chỉ nhập dấu cách cũng bị xem như chưa nhập gì”, hãy xem `isBlank()` ở phần sau.

## 3. Chương trình Java 17+ đầu tiên: độ dài, rỗng và khoảng trắng

Tạo tệp `LengthAndEmptyDemo.java`:

```java
public class LengthAndEmptyDemo {
    public static void main(String[] args) {
        String empty = "";
        String spaces = " \t";
        String text = "Java";

        System.out.println("empty.length = " + empty.length());
        System.out.println("empty.isEmpty = " + empty.isEmpty());

        System.out.println("spaces.length = " + spaces.length());
        System.out.println("spaces.isEmpty = " + spaces.isEmpty());
        System.out.println("spaces.isBlank = " + spaces.isBlank());

        System.out.println("text.length = " + text.length());
        System.out.println("text.isEmpty = " + text.isEmpty());

        String maybeNull = null;
        System.out.println(
            "null-or-empty = " + (maybeNull == null || maybeNull.isEmpty())
        );
        System.out.println(
            "has-text = " + (text != null && !text.isEmpty())
        );
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac LengthAndEmptyDemo.java
java LengthAndEmptyDemo
```

Kết quả:

```text
empty.length = 0
empty.isEmpty = true
spaces.length = 2
spaces.isEmpty = false
spaces.isBlank = true
text.length = 4
text.isEmpty = false
null-or-empty = true
has-text = true
```

Điểm cần quan sát:

1. `""` không có đơn vị mã nào nên `length() == 0` và `isEmpty() == true`.
2. `" \t"` có hai đơn vị mã, vì vậy `isEmpty() == false` dù không có chữ cái nào. Nó là *blank* theo `isBlank()`.
3. Biểu thức `maybeNull == null || maybeNull.isEmpty()` an toàn nhờ **short-circuit evaluation**: nếu vế đầu `true`, Java không đánh giá vế sau, tránh gọi phương thức trên `null`.
4. `text != null && !text.isEmpty()` chỉ trả về `true` khi tham chiếu tồn tại và chuỗi có độ dài lớn hơn 0.

## 4. Phân biệt chuỗi rỗng, chuỗi trắng và `null`

Ba trường hợp thường gặp khi xử lý dữ liệu nhập:

**Chuỗi rỗng — empty:** `String s = "";`. Đây là một đối tượng `String` hợp lệ có độ dài 0; `s.isEmpty()` là `true`.

**Chuỗi chỉ gồm khoảng trắng — blank:** `String s = "  \t";`. Chuỗi có độ dài lớn hơn 0 nên `isEmpty()` là `false`; `isBlank()` là `true`.

**Tham chiếu `null`:** `String s = null;`. Không có đối tượng `String` được tham chiếu; gọi `s.length()` hoặc `s.isEmpty()` đều gây `NullPointerException`. Không thể nói “`null` có độ dài 0”: `null` không phải một chuỗi rỗng.

### `isEmpty()` và `isBlank()`

`String.isBlank()` có từ Java 11. Nó trả về `true` nếu chuỗi rỗng **hoặc** chỉ chứa các Unicode code points được `Character.isWhitespace(int)` coi là whitespace.

```java
String a = "";
String b = " \t\n";
String c = " Java ";

System.out.println(a.isEmpty()); // true
System.out.println(a.isBlank()); // true

System.out.println(b.isEmpty()); // false
System.out.println(b.isBlank()); // true

System.out.println(c.isEmpty()); // false
System.out.println(c.isBlank()); // false
```

Đoạn này là ví dụ đặt trong phương thức, và các chú thích chỉ rõ kết quả in tương ứng.

Chọn phương thức theo yêu cầu thực tế:

- Chỉ muốn biết **chuỗi có độ dài bằng 0**: dùng `isEmpty()`.
- Muốn coi **chuỗi toàn whitespace như không có nội dung**: dùng `isBlank()` khi phù hợp với quy tắc whitespace của Java.
- Muốn loại bỏ whitespace ở hai đầu trước khi kiểm tra: cân nhắc `strip().isEmpty()` (Java 11+) hoặc `trim().isEmpty()` tùy chuẩn mong muốn. `strip()` và `trim()` có cách nhận diện ký tự ở đầu/cuối khác nhau; đừng giả định chúng hoàn toàn đồng nghĩa với nhau hoặc với `isBlank()` trong mọi trường hợp Unicode.

Lưu ý: định nghĩa whitespace ở `Character.isWhitespace` **không bao gồm mọi dấu cách Unicode có thể nhìn giống khoảng trắng** (ví dụ một số non-breaking spaces). Nếu quy tắc nghiệp vụ cần xử lý các ký tự đó, hãy định nghĩa và kiểm thử quy tắc riêng.

### Mẫu kiểm tra `null` an toàn

```java
// true nếu biến không tham chiếu String nào hoặc trỏ tới String rỗng:
boolean missing = s == null || s.isEmpty();

// true nếu biến có String không rỗng:
boolean nonEmpty = s != null && !s.isEmpty();

// true nếu không null và có ít nhất một code point không phải whitespace:
boolean hasNonBlankText = s != null && !s.isBlank();
```

Đây là fragment trong một phương thức có biến `String s` đã được khai báo. Dùng thứ tự như trên để tránh `NullPointerException`. Nếu quy tắc cần phân biệt `null` (chưa có dữ liệu) và `""` (dữ liệu rỗng), hãy giữ chúng thành **hai trạng thái riêng**, đừng mặc định gộp lại.

## 5. UTF-16: `length()` có thể khác số Unicode code points

Tạo tệp `UnicodeLengthDemo.java`:

```java
import java.nio.charset.StandardCharsets;

public class UnicodeLengthDemo {
    public static void main(String[] args) {
        String ascii = "Java";
        String accented = "\u00E9";           // é, một code point trong BMP.
        String emoji = "\uD83D\uDE00";       // 😀, surrogate pair.
        String combining = "e\u0301";         // e + dấu sắc kết hợp.

        printLengths("ascii", ascii);
        printLengths("accented", accented);
        printLengths("emoji", emoji);
        printLengths("combining", combining);

        String mixed = "A" + emoji + "B";
        System.out.println("mixed.length = " + mixed.length());
        System.out.println(
            "mixed.codePoints = " +
            mixed.codePointCount(0, mixed.length())
        );
        System.out.println(
            "highSurrogateAt1 = " +
            Character.isHighSurrogate(mixed.charAt(1))
        );
        System.out.println(
            "emojiSubstringEquals = " + mixed.substring(1, 3).equals(emoji)
        );
    }

    private static void printLengths(String name, String value) {
        System.out.println(
            name + ": units=" + value.length()
            + ", codePoints=" + value.codePointCount(0, value.length())
            + ", utf8Bytes=" +
            value.getBytes(StandardCharsets.UTF_8).length
        );
    }
}
```

Chạy:

```bash
javac UnicodeLengthDemo.java
java UnicodeLengthDemo
```

Kết quả:

```text
ascii: units=4, codePoints=4, utf8Bytes=4
accented: units=1, codePoints=1, utf8Bytes=2
emoji: units=2, codePoints=1, utf8Bytes=4
combining: units=2, codePoints=2, utf8Bytes=3
mixed.length = 4
mixed.codePoints = 3
highSurrogateAt1 = true
emojiSubstringEquals = true
```

Giải thích:

- `"\u00E9"` biểu diễn ký tự `é` có một code point, một UTF-16 code unit, nhưng **hai byte** khi mã hóa UTF-8.
- `"\uD83D\uDE00"` biểu diễn emoji 😀 bằng một cặp surrogate gồm hai code units; nó là **một code point**, **bốn byte UTF-8**.
- `"e\u0301"` chứa chữ `e` và dấu sắc kết hợp. Nó thường **hiển thị tương tự** `é` nhưng có **hai code points**, **hai UTF-16 code units**, **ba byte UTF-8**. Vì vậy, các giá trị `length()` khác nhau không nhất thiết có nghĩa số “chữ” người dùng nhìn thấy khác nhau.
- `mixed` là `"A" + emoji + "B"`. Chỉ số UTF-16 tương ứng: `A` ở 0; hai nửa surrogate ở 1 và 2; `B` ở 3. Do đó `length() == 4` và `codePointCount(...) == 3`. `substring(1, 3)` lấy cả hai đơn vị mã của emoji nên tạo ra nội dung bằng `emoji`.

**Không cắt ở giữa surrogate pair:** `mixed.substring(1, 2)` chỉ lấy một surrogate, không phải emoji nguyên vẹn. Khi xử lý dữ liệu theo Unicode code point, cân nhắc `codePointAt()`, `codePoints()` và cách chuyển từ chỉ số code point sang chỉ số UTF-16 như `offsetByCodePoints()`. Với chuỗi người dùng nhập chứa emoji ghép, còn cần thêm phân đoạn grapheme nếu thao tác được mô tả bằng “ký tự hiển thị”.

## 6. Dùng `length()` làm cận khi truy cập chuỗi

`charAt(index)` nhận chỉ số **UTF-16 code unit**, bắt đầu từ 0. Một chỉ số chỉ hợp lệ khi `0 <= index < s.length()`; giá trị `length()` chính là ranh giới **sau** đơn vị cuối cùng.

```java
String s = "Java";
if (!s.isEmpty()) {
    System.out.println(s.charAt(s.length() - 1)); // a
}
```

Với chuỗi rỗng, `length() - 1 == -1`, nên không thể đọc `charAt(-1)`. Nếu `s` có thể là `null`, hãy kiểm tra `s != null && !s.isEmpty()` trước khi gọi. Phần kiểm tra chỉ số âm, vòng lặp và xử lý lỗi được luyện kỹ ở bài **charAt và điều kiện chỉ số hợp lệ**; ở đây cần nhớ rằng `length()` đo *code unit*, nên `charAt(length() - 1)` có thể lấy **low surrogate** thay vì toàn bộ code point khi emoji nằm cuối chuỗi.
## 7. Các tình huống ứng dụng

### Kiểm tra tham số tùy chọn

Nếu chuỗi trống nghĩa là người dùng không cung cấp giá trị, có thể dùng:

```java
static boolean isProvided(String value) {
    return value != null && !value.isEmpty();
}
```

Nếu dấu cách đơn thuần không được chấp nhận, hãy dùng `!value.isBlank()` thay vì `!value.isEmpty()`. Cần đặt quy tắc theo yêu cầu của dữ liệu: có trường hợp một dấu cách thực sự là dữ liệu hợp lệ.

### Giới hạn độ dài dữ liệu nhập

```java
static boolean fitsUtf16Limit(String input, int maxUnits) {
    return input != null
        && maxUnits >= 0
        && input.length() <= maxUnits;
}
```

Hàm này áp dụng **giới hạn số UTF-16 code units**. Nó phù hợp nếu hợp đồng dữ liệu quy định chính xác thước đo đó. Nếu hệ thống yêu cầu tối đa một số Unicode code points, nên đếm với `input.codePointCount(0, input.length())`; nếu giới hạn payload là byte UTF-8, nên kiểm tra độ dài byte sau khi mã hóa. Không được dùng `length()` để khẳng định kích thước byte của dữ liệu.

### Duyệt nội dung chuỗi

```java
String s = "ABC";
for (int index = 0; index < s.length(); index++) {
    System.out.print(s.charAt(index));
}
System.out.println(); // ABC
```

Đây là một cách duyệt **UTF-16 code units**. Nó phù hợp khi thao tác theo chỉ số `char`, nhưng cần cách khác nếu mỗi bước phải xử lý trọn vẹn Unicode code point hoặc grapheme. `String` là immutable nên các thao tác `length()`, `isEmpty()` và `charAt()` không biến đổi chính đối tượng chuỗi.

### Hiệu năng

Trong các JDK Java hiện đại, `length()` và `isEmpty()` kiểm tra thông tin độ dài đã có và không cần duyệt toàn bộ nội dung chuỗi. Hãy ưu tiên **cú pháp diễn đạt đúng mục đích**: `isEmpty()` khi hỏi có rỗng không; `length()` khi thật sự cần số đơn vị mã hoặc làm việc với chỉ số. Ngược lại, `codePointCount()` phải xét các code units trong phạm vi để xác định surrogate pairs; kiểm tra độ dài byte theo một encoding cần thực hiện mã hóa.

Không cần thay thế `isEmpty()` bằng `length() == 0` chỉ để “tối ưu” nếu không có số liệu chứng minh, vì hai cách có ý nghĩa giống nhau và thường không tạo khác biệt đáng kể.

## 8. Sai lầm thường gặp

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| “`" ".isEmpty()` là `true`.” | Dấu cách vẫn là một code unit. | Dùng `isBlank()` nếu muốn coi whitespace là rỗng về mặt nghiệp vụ. |
| “`null.isEmpty()` trả về `true`.” | Không có đối tượng để gọi phương thức; ném NPE. | Kiểm tra `s == null` trước khi gọi. |
| “`length()` là số byte UTF-8.” | `length()` đếm UTF-16 code units. | Dùng `getBytes(StandardCharsets.UTF_8).length` nếu cần byte UTF-8. |
| “`length()` luôn bằng số Unicode code points.” | Ký tự ngoài BMP cần hai code units. | Dùng `codePointCount(0, s.length())` cho code points. |
| “Số code points luôn là số ký tự hiển thị.” | Dấu ghép và emoji nhiều thành phần có thể gồm nhiều code points. | Dùng thuật toán phân đoạn grapheme khi cần. |
| “`s.charAt(s.length() - 1)` luôn an toàn.” | Chuỗi rỗng tạo chỉ số `-1`, chuỗi `null` ném NPE. | Kiểm tra `s != null && !s.isEmpty()` trước. |
| “`isEmpty()` loại bỏ khoảng trắng trước khi kiểm tra.” | Nó chỉ tương đương `length() == 0`. | Áp dụng rõ ràng chính sách whitespace mong muốn. |
| “`isBlank()` tồn tại trong mọi bản Java.” | `String.isBlank()` được bổ sung trong Java 11. | Với Java 17+ dùng được; khi dùng JDK cũ cần phương án khác. |

## 9. Tự kiểm tra

**Bài 1.** Cho:

```java
String s = "  ";
System.out.println(s.length());
System.out.println(s.isEmpty());
System.out.println(s.isBlank());
```

Kết quả:

```text
2
false
true
```

Giải thích: hai dấu cách là hai UTF-16 code units; chuỗi không rỗng nhưng chỉ gồm whitespace.

**Bài 2.** Cho:

```java
String s = "";
boolean result = s == null || s.isEmpty();
System.out.println(result);
```

Kết quả: `true`. Nếu đổi `s` thành `null`, kết quả vẫn là `true` nhờ toán tử `||` đánh giá ngắn mạch.

**Bài 3.** Cho `String s = "\uD83D\uDE00";`. `s.length()` là bao nhiêu, và `s.codePointCount(0, s.length())` là bao nhiêu?

Đáp án lần lượt là **2** và **1**: một Unicode code point ngoài BMP được biểu diễn bằng hai UTF-16 code units.

**Bài 4.** Một biểu mẫu quy định mật khẩu dài tối đa 20 **byte UTF-8**. Dùng `password.length() <= 20` đã đúng chưa?

Chưa. `length()` đo UTF-16 code units, không đo UTF-8 bytes. Phải mã hóa theo UTF-8 rồi kiểm tra số byte, hoặc để tầng xử lý nhận dữ liệu kiểm tra đúng chuẩn đã quy định.

## Tổng kết

- `length()` cho biết **số UTF-16 code units** trong `String`.
- `isEmpty()` chỉ kiểm tra **`length() == 0`**.
- Chuỗi chỉ chứa khoảng trắng không rỗng theo `isEmpty()`; `isBlank()` giải quyết nhu cầu khác.
- `null` không phải chuỗi rỗng; cần kiểm tra tham chiếu trước khi gọi phương thức.
- Khi yêu cầu dùng “độ dài”, phải xác định rõ đang tính **UTF-16 units**, **Unicode code points**, **grapheme clusters**, hay **bytes theo encoding**.

## Tài liệu tham khảo

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): hợp đồng `length()`, `isEmpty()`, `isBlank()`, `codePointCount()`, `charAt()` và `substring()`.
- [Java SE 21 API — `java.lang.Character`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html): định nghĩa code point, surrogate pair và whitespace.
- [Java Language Specification §3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.5): cú pháp chuỗi và escape sequences.
