# Giới hạn xử lý Unicode escape của String.translateEscapes() trong Java 15+

## 1. Quy tắc cốt lõi

Phương thức **`String.translateEscapes()`** được đưa vào Java 15 như một API chính thức và vẫn tồn tại trong Java hiện đại. Nó nhận một `String` **đã có ở thời điểm chạy** và chuyển các chuỗi escape thông thường, ví dụ hai ký tự `\` và `n`, thành ký tự xuống dòng thực.

**Giới hạn quan trọng: `translateEscapes()` KHÔNG giải mã Unicode escape dạng `\uXXXX`**, kể cả khi `XXXX` là bốn chữ số thập lục phân hợp lệ. Trong Java, Unicode escape của *mã nguồn* được trình biên dịch xử lý ở giai đoạn đọc ký tự đầu vào, trước khi nhận diện chuỗi literal; nó không thuộc tập escape mà phương thức này xử lý ở thời điểm chạy.

~~~java
String ordinary = "\\n";
String lineFeed = ordinary.translateEscapes(); // một ký tự xuống dòng LF

String unicodeText = "\\u0041"; // sáu ký tự: \, u, 0, 0, 4, 1
// unicodeText.translateEscapes(); // ném IllegalArgumentException
~~~

Dấu `\u0041` biểu diễn ký tự `A` khi xuất hiện **như một Unicode escape hợp lệ trong mã nguồn Java được biên dịch**. Tuy nhiên, việc một `String` đang chứa ký tự backslash rồi đến `u0041` hoàn toàn **không kích hoạt lại** bước tiền xử lý của trình biên dịch.

Đây là hành vi được tài liệu `String.translateEscapes()` của Java SE quy định rõ, không phải lỗi của Java 15, IDE hay bảng mã UTF-8.

## 2. Phân biệt ba cơ chế dễ bị nhầm

| Cơ chế | Thời điểm xử lý | Ví dụ | Kết quả |
| --- | --- | --- | --- |
| **Unicode escape trong mã nguồn Java** | Khi `javac` đọc và phân tích mã nguồn, **trước khi nhận diện token/literal** | `String s = "\u0041";` | `s` chứa `"A"`. |
| **Escape thông thường trong Java string literal** | Trong quá trình xử lý literal khi biên dịch | `String s = "\n";` | `s` chứa một ký tự LF, có độ dài 1. |
| **`String.translateEscapes()`** | Khi chương trình chạy, trên chuỗi đã được tạo | `"\\n".translateEscapes()` | Chuỗi gồm hai ký tự `\` + `n` được chuyển thành một LF. |
| **`String.translateEscapes()` với Unicode escape dạng văn bản** | Khi chương trình chạy | `"\\u0041".translateEscapes()` | Ném `IllegalArgumentException`; không trả về `"A"`. |

**Hai đoạn mã gần giống nhau nhưng khác kết quả:**

~~~java
String processedByCompiler = "\u0041";  // trình biên dịch chuyển thành "A"
String keptAsText       = "\\u0041";    // tại runtime là sáu ký tự \u0041
~~~

`processedByCompiler` đã là `"A"` và không cần `translateEscapes()`. Trong `keptAsText`, hai dấu backslash liên tiếp trong mã nguồn biểu diễn một dấu backslash thực trong `String`. Điều đó ngăn chuỗi `\u0041` được coi là Unicode escape của mã nguồn, nhưng để lại văn bản mà `translateEscapes()` không biết giải mã.

Theo **Java Language Specification `3.2–`3.3**, Unicode escape được xử lý sớm, trước cả khi Java phân biệt đoạn nào là string, comment hay mã lệnh. Vì vậy không nên hình dung `\uXXXX` là một biến thể có thể dùng tùy ý của `\n` trong chuỗi runtime.

## 3. Những escape mà translateEscapes() thực sự hỗ trợ

API tuân theo danh sách escape thông thường của Java:

| Văn bản escape ở thời điểm chạy | Kết quả khi gọi `translateEscapes()` |
| --- | --- |
| `\b` | Backspace, U+0008 |
| `\t` | Horizontal tab, U+0009 |
| `\n` | Line feed, U+000A |
| `\f` | Form feed, U+000C |
| `\r` | Carriage return, U+000D |
| `\s` | Một dấu cách, U+0020 |
| `\"` | Dấu nháy kép `"` |
| `\'` | Dấu nháy đơn `'` |
| `\\` | Một dấu backslash `\` |
| Octal, ví dụ `\101` | Ký tự có mã bát phân tương ứng (`\101` → `A`); tuân theo cú pháp octal escape của Java |
| Backslash ngay trước dấu kết thúc dòng | Bỏ dấu backslash và dấu kết thúc dòng để nối dòng |

**Không hỗ trợ:** `\u0041`, `\u2022`, `\uD83D\uDE42`, `\U0001F642` và các cú pháp tương tự để biểu diễn Unicode bằng số trong dữ liệu runtime. `\x41` cũng không phải escape được API này công nhận.

Chú ý: `\uXXXX` **không được giữ nguyên một cách âm thầm**. Khi gặp backslash ngay trước `u` trong dữ liệu chưa giải mã, phương thức xem đó là escape không hợp lệ và ném `IllegalArgumentException`. Dù nhiều chữ số hex có vẻ hợp lệ, API không dùng chúng để quyết định giải mã Unicode.

Một ví dụ đối chiếu đơn giản:

~~~java
String a = "\\101".translateEscapes();  // "A", nhờ octal escape
String b = "\\n".translateEscapes();    // chứa ký tự xuống dòng
// String c = "\\u0041".translateEscapes(); // IllegalArgumentException
~~~

Đừng suy ra rằng vì API hiểu `\101` nên nó cũng hiểu `\u0041`; đây là **hai cú pháp khác nhau**, được xử lý ở các giai đoạn khác nhau.

## 4. Vì sao chỉ có \uXXXX trong file dữ liệu vẫn thất bại?

Giả sử một file, một dòng trong cơ sở dữ liệu hoặc một thông điệp mạng chứa đúng các ký tự:

~~~text
\u0041
~~~

Khi đọc chúng bằng một API như `Files.readString(...)`, chương trình nhận một `String` chứa **sáu ký tự**: một backslash, chữ `u` và bốn chữ số `0041`. Trình biên dịch đã hoàn tất từ trước; nó **không đọc lại** nội dung của giá trị runtime để tìm Unicode escape.

Do đó:

~~~java
String fromExternalInput = "\\u0041"; // mô phỏng dữ liệu vừa đọc
int length = fromExternalInput.length(); // 6

// SAI nếu mục tiêu là giải mã Unicode escape:
String decoded = fromExternalInput.translateEscapes();
// Lệnh trên ném IllegalArgumentException.
~~~

Đây là lỗi **ở runtime**, khác với lỗi biên dịch do viết escape không hợp lệ trực tiếp trong string literal Java. Chẳng hạn `String s = "\q";` là một literal không hợp lệ ngay từ khi biên dịch, còn `String s = "\\q";` là literal hợp lệ tạo ra một backslash và chữ `q`, rồi `s.translateEscapes()` mới ném lỗi lúc chạy.

Vì vậy, khi gặp dữ liệu có cấu trúc khác (chẳng hạn **JSON** với chuỗi Unicode escape), hãy dùng **bộ giải mã đúng của định dạng đó**. `translateEscapes()` không phải trình đọc JSON hay bộ giải mã Unicode tổng quát.

## 5. Unicode ngoài BMP: không thể dùng translateEscapes() để ghép surrogate

Unicode có các ký tự nằm ngoài Basic Multilingual Plane (BMP), ví dụ code point **U+1F642**. Java `String` lưu trữ bằng UTF-16, nên một code point như vậy chiếm **hai `char` (hai code unit)**, còn gọi là một cặp surrogate.

Văn bản giống Unicode escape theo kiểu Java:

~~~text
\uD83D\uDE42
~~~

gồm hai phần mã hóa các code unit UTF-16. Nếu `String` runtime chứa chính văn bản này, `translateEscapes()` sẽ lỗi ngay từ escape `\u` đầu tiên. Nó không giải mã `\uD83D` và `\uDE42` để ghép thành ký tự.

Khi **đã có một code point hợp lệ ở runtime**, hãy sử dụng API Unicode của Java thay vì ghép chuỗi escape:

~~~java
int codePoint = Integer.parseInt("1F642", 16);
String result = new String(Character.toChars(codePoint));
System.out.println(result.length());                           // 2 (UTF-16 code units)
System.out.println(result.codePointCount(0, result.length())); // 1 (Unicode code point)
~~~

`Character.toChars(int)` nhận code point, không nhận chuỗi `\uXXXX`. Nếu dữ liệu đầu vào thực sự theo định dạng chứa **nhiều** escape `\uXXXX`, bộ giải mã của định dạng phải xử lý đúng từng nhóm bốn chữ số và cặp surrogate. Đừng dùng `replace("\\u", "")` hoặc ép mỗi nhóm hex thành một ký tự một cách tùy tiện: cách đó dễ làm sai dữ liệu và không giải quyết được các trường hợp Unicode bổ sung.

## 6. Chương trình Java 17+ chạy độc lập

Tạo file **`TranslateEscapesUnicodeDemo.java`**. Ví dụ phân biệt dấu xuống dòng thường, chuỗi escape Unicode runtime, Unicode escape đã xử lý khi biên dịch, octal escape và một code point ngoài BMP.

~~~java
public class TranslateEscapesUnicodeDemo {
    public static void main(String[] args) {
        String rawNewline = "\\n";
        String newline = rawNewline.translateEscapes();
        System.out.println("newlineIsLF=" + (newline.length() == 1 && newline.charAt(0) == '\n'));

        String rawUnicode = "\\u0041";
        System.out.println("rawUnicode=" + rawUnicode);
        System.out.println("rawUnicodeLength=" + rawUnicode.length());
        try {
            rawUnicode.translateEscapes();
            System.out.println("rawUnicodeResult=unexpected");
        } catch (IllegalArgumentException ex) {
            System.out.println("rawUnicodeResult=" + ex.getClass().getSimpleName());
        }

        String atCompileTime = "\u0041";
        System.out.println("compileTime=" + atCompileTime);
        System.out.println("compileTimeLength=" + atCompileTime.length());

        String octal = "\\101".translateEscapes();
        System.out.println("octal=" + octal);
        System.out.println("tabIs9=" + (("\\t".translateEscapes().charAt(0)) == 9));

        int codePoint = Integer.parseInt("1F642", 16);
        String fromCodePoint = new String(Character.toChars(codePoint));
        System.out.println("supplementaryCodePoint="
                + Integer.toHexString(fromCodePoint.codePointAt(0)).toUpperCase());
        System.out.println("utf16Length=" + fromCodePoint.length());

        String emojiUnicodeEscapes = "\\uD83D\\uDE42";
        try {
            emojiUnicodeEscapes.translateEscapes();
            System.out.println("emojiSequence=unexpected");
        } catch (IllegalArgumentException ex) {
            System.out.println("emojiSequence=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên, lưu tệp bằng UTF-8:

~~~bash
javac --release 17 -encoding UTF-8 TranslateEscapesUnicodeDemo.java
java TranslateEscapesUnicodeDemo
~~~

**Stdout chính xác** khi chạy:

~~~text
newlineIsLF=true
rawUnicode=\u0041
rawUnicodeLength=6
rawUnicodeResult=IllegalArgumentException
compileTime=A
compileTimeLength=1
octal=A
tabIs9=true
supplementaryCodePoint=1F642
utf16Length=2
emojiSequence=IllegalArgumentException
~~~

Giải thích kết quả:

- `newlineIsLF=true` chứng minh `"\\n"` đã được chuyển thành đúng **một ký tự LF**.
- `rawUnicodeLength=6` xác nhận `"\\u0041"` còn nguyên văn bản sáu ký tự tại runtime; phương thức sau đó ném lỗi, không tạo `A`.
- `compileTime=A` chứng minh `"\u0041"` được **trình biên dịch** xử lý thành `A` trước khi chương trình chạy.
- `octal=A` cho thấy octal escape được hỗ trợ, khác với Unicode escape.
- `supplementaryCodePoint=1F642` và `utf16Length=2` cho thấy API `Character` làm việc với code point và UTF-16 đúng cách.
- `emojiSequence=IllegalArgumentException` xác nhận hai mã surrogate viết dưới dạng văn bản `\u...` vẫn không được `translateEscapes()` giải mã.

Để bài chạy ổn định trên nhiều môi trường, ví dụ in mã code point bằng hệ thập lục phân thay vì in ký tự emoji trực tiếp, tránh phụ thuộc font hiển thị của terminal.

## 7. Phân biệt lựa chọn xử lý theo nguồn dữ liệu

| Nguồn và nhu cầu | Cách làm phù hợp |
| --- | --- |
| Muốn ghi một ký tự Unicode cố định trực tiếp trong mã nguồn | Dùng ký tự Unicode trong file nguồn (với encoding đúng) hoặc Unicode escape của **mã nguồn** như `"\u0041"`. |
| Có chuỗi runtime chứa ký hiệu escape thông thường như `\n`, `\t` | Có thể dùng `String.translateEscapes()` khi dữ liệu tuân theo đúng cú pháp escape được hỗ trợ. |
| Có mã Unicode code point ở runtime, ví dụ giá trị hex `1F642` | Parse hex thành số nguyên hợp lệ rồi dùng `Character.toChars(...)` để tạo `String`. |
| Đọc JSON chứa Unicode escape `\uXXXX` | Dùng parser JSON có xử lý escape và surrogate theo chuẩn JSON. |
| Đọc một định dạng tùy biến dùng `\uXXXX` | Viết/chọn bộ phân tích phù hợp với định dạng, quy tắc kiểm tra chính xác bốn chữ số hex, xử lý code unit UTF-16 và cặp surrogate; không dùng `translateEscapes()`. |

Lưu ý về bảo toàn dữ liệu: không nên tự động gọi `translateEscapes()` cho mọi văn bản từ bên ngoài. Chuỗi chứa dấu backslash chưa chắc có chủ ý mã hóa escape; một escape không được hỗ trợ có thể gây `IllegalArgumentException`. Hãy xác định rõ dữ liệu đầu vào có sử dụng cú pháp escape nào và yêu cầu đầu ra là gì.

## 8. Những hiểu lầm thường gặp

| Hiểu lầm | Điều đúng |
| --- | --- |
| `translateEscapes()` có chữ “Escapes”, nên giải mã mọi `\uXXXX` | API chỉ giải mã danh sách escape thông thường mà `String` Javadoc công bố; **không giải mã Unicode escape**. |
| `"\\u0041"` và `"\u0041"` là cùng một chuỗi | Chuỗi thứ nhất chứa sáu ký tự, chuỗi thứ hai chứa `A`; khác ngay từ quá trình biên dịch. |
| `translateEscapes()` sẽ bỏ qua `\uXXXX` không hiểu | Nó **ném `IllegalArgumentException`** khi gặp escape không hợp lệ. |
| `\uD83D\uDE42` ở runtime sẽ tự ghép thành một emoji | Không; cần bộ giải mã đúng của định dạng hoặc code point API. |
| Unicode escape chỉ được xem xét bên trong dấu nháy kép | Trong mã nguồn Java, giai đoạn xử lý Unicode escape diễn ra **trước nhận diện literal và comment**. |
| Cứ thay `\u` bằng chuỗi rỗng rồi parse hex là đủ | Không; còn giới hạn bốn hex, cặp surrogate, escape backslash và quy tắc định dạng dữ liệu. |
| `translateEscapes()` chỉ là tính năng preview của text block đời cũ | Từ **Java 15**, đây là phương thức chính thức được hỗ trợ trong API hiện hành. |

## 9. Kết luận áp dụng

Một cách kiểm tra trước khi gọi API:

1. **Đây có phải Java source đang được `javac` biên dịch?** Nếu có, `\uXXXX` hợp lệ thuộc bước xử lý Unicode escape của **ngôn ngữ Java**.
2. **Đây là một `String` đã tồn tại khi chạy?** Nếu có, `translateEscapes()` chỉ xử lý những escape được Javadoc liệt kê.
3. **Chuỗi runtime có `\uXXXX`?** Nếu có, đừng dùng `translateEscapes()` để giải mã nó; hãy chọn parser theo định dạng đầu vào hoặc dùng Unicode code point API khi bạn đã có mã code point.

**Tài liệu chuẩn còn hiệu lực:**

- [Java SE 26 — `String.translateEscapes()`: danh sách escape, ngoại lệ và giới hạn Unicode](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html#translateEscapes())
- [Java Language Specification, `3.2 — Lexical Translations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.2)
- [Java Language Specification, `3.3 — Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.3)
- [Java Language Specification, `3.10.7 — Escape Sequences](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.10.7)