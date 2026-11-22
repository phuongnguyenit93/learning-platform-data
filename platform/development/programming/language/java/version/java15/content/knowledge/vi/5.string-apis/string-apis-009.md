# Escape hợp lệ, sai định dạng và IllegalArgumentException trong API chuỗi Java 15+

## Mục tiêu

Khi đọc cấu hình, tạo ví dụ, xử lý một đoạn text chứa ký tự `\` hoặc thử nghiệm text block, bạn có thể gặp chuỗi hai ký tự `\n`, `\t` hay `\s` nhưng muốn chuyển chúng thành **ký tự điều khiển hoặc ký tự trắng thực sự**. Từ **Java 15**, `String.translateEscapes()` là API chính thức để làm việc này. Phương thức vẫn tồn tại và có ích trong các JDK hiện đại; không cần bật preview hoặc dùng API đã lỗi thời.

Bài học tập trung vào ba câu hỏi:

1. Những **escape hợp lệ** nào được `translateEscapes()` nhận diện, và giá trị String sau chuyển đổi là gì?
2. Một escape **sai định dạng** gây lỗi **lúc biên dịch** hay ném `IllegalArgumentException` **lúc chương trình chạy**?
3. Khi nào nên gọi phương thức, cách xử lý lỗi có ngữ cảnh, và khi nào **không nên** sử dụng nó như parser của các định dạng khác?

Sau bài này, bạn có thể viết ví dụ chạy trên Java 15+, dự đoán đúng kết quả, và xử lý dữ liệu đầu vào có backslash mà không đánh đồng các tầng escape.

## 1. Trước hết phân biệt escape của mã Java với escape trong String dữ liệu

Java có hai giai đoạn dễ bị nhầm:

- **Lúc biên dịch:** compiler đọc source `.java` và xử lý escape ngay trong **string literal** hoặc text block. Ví dụ `"A\nB"` tạo String chứa ký tự `A`, một **LF** (xuống dòng), rồi `B`; khi chương trình chạy, ký tự `\` và chữ `n` *không còn đứng cạnh nhau* trong giá trị ấy.
- **Lúc chạy:** một String có thể chứa hai ký tự **backslash thật + chữ n**, do đọc từ file, HTTP, người dùng, hoặc do source Java biểu diễn bằng `"A\\nB"`. Gọi `translateEscapes()` sẽ biến cặp `\n` thành LF. Phương thức làm việc trên **giá trị String đang có ở runtime**, không viết lại mã nguồn Java.

Ví dụ phân biệt:

```java
String alreadyDecoded = "A\nB";           // A, LF, B
String rawSequence = "A\\nB";             // A, backslash, n, B
String decoded = rawSequence.translateEscapes();

System.out.println(alreadyDecoded.length()); // 3
System.out.println(rawSequence.length());    // 4
System.out.println(decoded.length());        // 3
System.out.println(alreadyDecoded.equals(decoded)); // true
```

Đây là **đoạn minh họa** cần đặt trong một phương thức khi chạy. Dùng `"\\n"` trong source để **giữ lại** cặp `\n` cho `translateEscapes()` xử lý sau. Viết `"\n"` là đã giải mã ngay khi compiler đọc literal: gọi lại phương thức không tạo thêm newline.

Không gọi `translateEscapes()` theo thói quen trên mọi String. Phương thức dùng khi **quy ước dữ liệu đầu vào thật sự cho phép escape kiểu Java**.

## 2. Các escape hợp lệ còn được hỗ trợ

`String.translateEscapes()` nhận diện những escape thuộc quy tắc string literal/text block của Java. Bảng sau mô tả **đầu vào runtime**: cột trái là ký tự backslash `\` theo sau bởi ký hiệu tương ứng, không phải cách gõ một literal Java hoàn chỉnh.

| Chuỗi escape trong **dữ liệu đầu vào** | Kết quả sau `translateEscapes()` | Diễn giải |
| --- | --- | --- |
| `\b` | U+0008 | Backspace |
| `\t` | U+0009 | Tab ngang |
| `\n` | U+000A | Line feed (LF) |
| `\f` | U+000C | Form feed |
| `\r` | U+000D | Carriage return (CR) |
| `\s` | U+0020 | **Một space** thông thường |
| `\"` | U+0022 | Dấu nháy kép `"` |
| `\'` | U+0027 | Dấu nháy đơn `'` |
| `\\` | U+005C | Một dấu backslash thật |
| `\0` đến `\377` | U+0000 đến U+00FF | Ký tự theo **giá trị bát phân (octal)** hợp lệ |
| Backslash + **line terminator thật** | Không giữ lại hai ký tự đó | **Line continuation**: bỏ dấu `\` và ký tự kết thúc dòng (LF hoặc CRLF/CR) |

**Phân biệt rõ ký hiệu và ký tự thực:** `\n` trong bảng là cặp ký tự backslash + `n` trước khi dịch; kết quả là **một LF**. `\s` tạo **space U+0020**, không phải “mọi loại whitespace”. `\"` tạo dấu `"` ngay cả khi trong dữ liệu runtime không thật sự cần escape dấu nháy.

**Octal còn được API nhận diện** để tương thích với cú pháp escape Java. Dạng ngắn có 1 hoặc 2 chữ số `0…7`; dạng 3 chữ số phải bắt đầu bằng `0…3` để nằm trong khoảng `\000`–`\377`. Ví dụ `\101` là `A` (octal 101 = decimal 65), `\377` là U+00FF. Với mã mới, thường nên dùng escape có tên như `\n`, `\t` hoặc ký tự Unicode rõ nghĩa thay vì lạm dụng mã octal khó đọc.

Có một trường hợp dễ hiểu sai: dữ liệu `\400` **không buộc phải ném lỗi** chỉ vì trông như octal 400 lớn hơn 377. Parser có thể nhận `\40` là space, rồi để ký tự `0` còn lại. Vì vậy, nếu đầu vào phải có quy tắc chính xác hơn một escape Java hợp lệ, hãy **validate toàn bộ định dạng của dữ liệu**, đừng chỉ dựa vào `translateEscapes()`.

### Escape tiếp dòng

Nếu một String đang chứa **backslash thật ngay trước một ký tự xuống dòng thật**, `translateEscapes()` bỏ cả hai, tức nối hai phần văn bản. Với CRLF, hai ký tự CR và LF được loại cùng với backslash. Escape `\` + line terminator khác với hai ký tự `\` + chữ `n`: trường hợp thứ hai sẽ tạo ra **một LF**, không làm hai dòng nhập thành một dòng.

Trong source Java, có thể tạo đầu vào runtime “backslash + LF” bằng cách ghép `"A\\" + "\n" + "B"`. Sau `translateEscapes()`, kết quả là `"AB"`.

## 3. Khi nào xảy ra IllegalArgumentException?

Javadoc của `String.translateEscapes()` quy định **`IllegalArgumentException` khi escape sequence bị malformed**. Những ví dụ điển hình:

| Dữ liệu runtime trước khi dịch | Vấn đề | Kết quả |
| --- | --- | --- |
| `\q` | `q` không thuộc danh sách escape Java hợp lệ | Ném `IllegalArgumentException` |
| `\x41` | Không hỗ trợ escape hệ hex dạng `\x...` | Ném `IllegalArgumentException` |
| `\u0041` | **Không chuyển Unicode escape kiểu `\u...`** ở runtime | Ném `IllegalArgumentException` |
| `abc\` | Dấu backslash cuối chuỗi không có ký tự theo sau | Ném `IllegalArgumentException` |
| `\8` hoặc `\9` | `8` và `9` không phải ký tự mở đầu escape octal hợp lệ | Ném `IllegalArgumentException` |

Ngược lại, các ký tự bình thường không có `\` đứng trước (như `a`, `z`, dấu `%`, hoặc một chữ `u` đơn lẻ) **không phải escape**, nên phương thức giữ nguyên.

### Lỗi biên dịch khác với lỗi runtime

Đây là **mã Java không hợp lệ**:

```java
// Chỉ minh họa lỗi; đừng thêm dòng này vào ví dụ chạy:
String wrong = "\q"; // javac: illegal escape character
```

Compiler đã từ chối literal `"\q"`, nên chưa thể chạy `translateEscapes()`.

Đây là **mã Java hợp lệ** nhưng phát sinh lỗi **khi gọi phương thức**:

```java
String encoded = "\\q"; // String chứa hai ký tự: \ và q
encoded.translateEscapes(); // ném IllegalArgumentException lúc chạy
```

`IllegalArgumentException` là một **unchecked exception** (kế thừa `RuntimeException`), không bắt buộc khai báo `throws`. Khi xử lý dữ liệu bên ngoài, nên bắt **đúng phạm vi** để báo input nào có lỗi, giữ được nguyên nhân và tránh làm sập toàn bộ luồng xử lý nếu đó là yêu cầu của ứng dụng.

Thông điệp `getMessage()` của exception không phải một định dạng lỗi ổn định để parse; nếu cần output/tự động hóa ổn định, ghi tên loại exception hoặc tự tạo thông báo nghiệp vụ có ngữ cảnh.

## 4. Ví dụ Java hoàn chỉnh: escape hợp lệ, sai định dạng, và kết quả chính xác

Tạo file **`TranslateEscapesDemo.java`** (tên file phải trùng tên `public class`):

```java
public class TranslateEscapesDemo {
    private static String visible(String value) {
        return value.replace("\\", "\\\\")
                .replace("\b", "<BS>")
                .replace("\t", "<TAB>")
                .replace("\n", "<LF>")
                .replace("\f", "<FF>")
                .replace("\r", "<CR>")
                .replace(" ", "<SP>");
    }

    private static void show(String label, String encoded) {
        try {
            String decoded = encoded.translateEscapes();
            System.out.println(label + " -> " + visible(decoded));
        } catch (IllegalArgumentException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        show("LF", "A\\nB");
        show("TAB", "A\\tB");
        show("SPACE", "A\\sB");
        show("QUOTE", "\\\"");
        show("BACKSLASH", "\\\\");
        show("OCTAL", "\\101");

        // Dau \ that + newline that: phep noi dong.
        show("CONTINUATION", "A\\" + "\n" + "B");

        show("BAD_Q", "\\q");
        show("BAD_X", "\\x41");
        show("BAD_U", "\\u0041");
        show("BAD_END", "A\\");

        String raw = "\\\\n";
        String once = raw.translateEscapes();
        String twice = once.translateEscapes();
        System.out.println("DOUBLE_TRANSLATION -> "
                + raw.length() + "/" + once.length() + "/" + twice.length());

        System.out.println("SOURCE_VS_RUNTIME -> "
                + "A\nB".equals("A\\nB".translateEscapes()));
    }
}
```

Lệnh thực hiện trên JDK có `javac` hỗ trợ `--release 15` (ví dụ JDK 21 hoặc JDK LTS được hỗ trợ có target này):

```bash
javac --release 15 -encoding UTF-8 -d out TranslateEscapesDemo.java
java -cp out TranslateEscapesDemo
```

**stdout chính xác:**

```text
LF -> A<LF>B
TAB -> A<TAB>B
SPACE -> A<SP>B
QUOTE -> "
BACKSLASH -> \\
OCTAL -> A
CONTINUATION -> AB
BAD_Q -> IllegalArgumentException
BAD_X -> IllegalArgumentException
BAD_U -> IllegalArgumentException
BAD_END -> IllegalArgumentException
DOUBLE_TRANSLATION -> 3/2/1
SOURCE_VS_RUNTIME -> true
```

Hàm `visible` biểu diễn ký tự điều khiển bằng ký hiệu `<LF>`, `<TAB>`, `<SP>` để output **không phụ thuộc** cách terminal hiển thị tab, xuống dòng hoặc khoảng trắng. Mỗi dòng `show` thử chuyển đổi rồi bắt `IllegalArgumentException` tại đúng thao tác có thể thất bại.

Giải thích những kết quả đáng chú ý:

- `"A\\nB"` là **4 ký tự** ở runtime. Sau giải mã còn 3 ký tự `A`, LF, `B`.
- `"\\s"` chuyển thành một space U+0020, được `visible` ghi là `<SP>`.
- `"\\101"` dùng octal escape tạo chữ `A`.
- `"A\\" + "\n" + "B"` có backslash thật theo sau LF thật; sau dịch là `"AB"`.
- `"\\\\n"` là **hai backslash + `n`** (độ dài 3). Sau lần dịch thứ nhất, còn một backslash + `n` (độ dài 2); sau lần dịch thứ hai, thành **một LF** (độ dài 1). Do đó `translateEscapes()` **không idempotent** trong mọi trường hợp: gọi lặp lại có thể đổi dữ liệu thêm một lần.
- `"A\nB".equals("A\\nB".translateEscapes())` là `true` vì hai biểu thức tạo **cùng một** giá trị String.

**Không mở đầu chương trình bằng cách cố chạy literal `"\q"`.** Literal ấy không vượt qua giai đoạn compile. Muốn kiểm tra lỗi runtime, phải đưa vào giá trị String có backslash thật, như `"\\q"`, rồi gọi phương thức.

## 5. Những escape không được phép hiểu nhầm

### 5.1. Không dịch `\uXXXX` của chuỗi dữ liệu

Dù JLS có **Unicode escapes** như `\u0041` trong mã nguồn, `String.translateEscapes()` **không** có chức năng giải mã Unicode escape kiểu đó. Java compiler xử lý Unicode escape ở một bước **sớm hơn** khi đọc file `.java`; đó là cơ chế khác với parser runtime.

Ví dụ, chuỗi runtime gồm sáu ký tự `\`, `u`, `0`, `0`, `4`, `1` có thể được tạo bằng source Java `"\\u0041"`. Gọi `translateEscapes()` lên chuỗi ấy ném `IllegalArgumentException` vì `\u` không thuộc danh sách runtime escape của phương thức. Nó không trả về chữ `A`.

Nếu đầu vào thực sự là **JSON**, `\uXXXX` là một trong những escape của **JSON**, hãy để **JSON parser** của ứng dụng xử lý. Không dùng `translateEscapes()` để giả lập JSON parser.

### 5.2. Không phải bộ giải mã JSON, regex, URL hay HTML

Nhiều định dạng cũng dùng dấu `\` nhưng **quy tắc khác nhau**:

- JSON nhận `\uXXXX`, `\/` và có cách escape riêng, trong khi `translateEscapes()` không chấp nhận `\u` hay `\/` theo quy tắc Java. Ngược lại, `\s` là escape Java hợp lệ nhưng không phải JSON escape hợp lệ.
- Regular expression có `\d`, `\w`, `\p{...}` với nghĩa thuộc **regex engine**; đưa chúng trực tiếp vào `translateEscapes()` sẽ bị từ chối. Nếu tạo regex trong mã Java, giữ nguyên backslash đúng số tầng rồi dùng `Pattern.compile` hoặc `String.matches`.
- URL có **percent encoding** như `%20`, không thuộc nhiệm vụ của `translateEscapes()`.
- HTML/XML có **entities** như `&amp;` hoặc `&lt;`, không phải escape Java.
- Chuỗi định dạng `String.format` và `String.formatted` dùng ký hiệu `%s`, `%d`; nếu format sai, nó có thể ném các ngoại lệ con của `IllegalFormatException` (thuộc họ `IllegalArgumentException`), nhưng đó là **cơ chế khác** với malformed backslash escape của `translateEscapes()`.

**Quy tắc:** chọn parser đúng **định dạng dữ liệu gốc**, không coi dấu `\` là cú pháp chung cho mọi kiểu văn bản.

### 5.3. Không tự động “làm sạch” input ngoài

Phương thức **không kiểm tra dữ liệu có an toàn cho SQL, HTML, log, shell hoặc JSON hay không**. Nó có thể chuyển cặp `\n` thành newline thật và `\t` thành tab thật: điều này thay đổi cấu trúc log, dòng CSV/TSV hoặc payload gửi đi. Nếu dữ liệu người dùng cần được lưu **nguyên văn**, không giải mã.

Nếu giá trị String đến từ hệ thống ngoài mà quy ước escape chưa được thỏa thuận, nên giữ nguyên và hỏi rõ format; không âm thầm thử `translateEscapes()` rồi bỏ qua `IllegalArgumentException`.

## 6. Text block Java 15 liên quan thế nào?

**Text blocks** cũng chính thức từ Java 15 và nhận cùng họ escape Java trong quá trình biên dịch, ví dụ `\s` để giữ một space ở cuối dòng hay `\` + line terminator để tiếp dòng. Nhưng **compiler đã giải mã** những escape nằm trực tiếp trong text block source. Vì vậy `translateEscapes()` chỉ cần thiết khi **giá trị String tại runtime vẫn còn các cặp backslash + ký tự mã**.

Ví dụ độc lập trong một phương thức:

```java
String text = """
        first\\nsecond
        """;

String decoded = text.translateEscapes();
System.out.println(decoded.equals("first\nsecond\n")); // true
```

Trong source text block, `\\` tạo một backslash thật nên giá trị `text` tại runtime chứa `first\nsecond` (cặp `\` + `n`) và một LF cuối text block. `translateEscapes()` biến cặp ấy thành LF thứ nhất; LF cuối ban đầu vẫn được giữ. Không cần tạo chuỗi này theo cách phức tạp nếu chỉ muốn viết dữ liệu cố định: có thể gõ newline thật trong text block.

**Các bước của text block**: Java chuẩn hóa line terminator, loại incidental indentation, **sau đó** giải mã escape khi biên dịch. Không nhầm việc xử lý compile-time này với một lần gọi `translateEscapes()` ở runtime; dùng cả hai không có chủ đích có thể dẫn đến giải mã hai lần.

## 7. Xử lý lỗi đầu vào trong ứng dụng một cách rõ ràng

Nếu ứng dụng thật sự có giao thức lưu “Java-style escaped text”, nên **quy định và kiểm tra phạm vi** rồi chuyển đổi một lần. Ví dụ một hàm có ngữ cảnh lỗi:

```java
public static String decodeConfigValue(String key, String encoded) {
    if (encoded == null) {
        throw new IllegalArgumentException("Missing value for key: " + key);
    }

    try {
        return encoded.translateEscapes();
    } catch (IllegalArgumentException cause) {
        throw new IllegalArgumentException(
                "Invalid Java-style escape in config key: " + key, cause);
    }
}
```

Đây là **hàm minh họa**, phải đặt trong class thích hợp; `key` là tên cấu hình hoặc mã mục, **không** nên đưa nguyên giá trị có thể nhạy cảm vào log exception.

Cách xử lý thích hợp tùy hệ thống:

1. **Dữ liệu cấu hình do nhóm quản lý:** fail-fast, báo đúng tên khóa và giữ exception gốc làm `cause`; tránh tự ý thay `\q` thành `q` vì có thể che giấu lỗi gõ.
2. **Nhập liệu tương tác:** bắt `IllegalArgumentException` ở ranh giới nhập liệu và hiển thị lỗi để người dùng sửa; giữ nguyên giá trị gốc khi retry, không decode nhiều lần.
3. **Dữ liệu nhiều bản ghi:** quyết định rõ “loại bản ghi lỗi”, “đưa vào hàng chờ xử lý” hoặc “dừng cả batch”; kiểm soát và đo số lỗi.
4. **Dữ liệu lưu chính xác/đã được escape bởi format khác:** không gọi `translateEscapes()`; dùng parser tương ứng và giữ đúng round-trip.

Tránh bắt chung `Exception` rồi trả chuỗi rỗng: như vậy các lỗi escape bị biến thành dữ liệu hợp lệ giả, rất khó debug và có thể gây mất thông tin.

### Gỡ lỗi mà không bị đánh lừa bởi output console

Tab, LF, CR và backspace có thể làm terminal hiển thị khác nhau. Để kiểm tra **ký tự thật**, hãy dùng `length()`, `charAt(i)`, `codePoints()` hoặc chuyển ký tự điều khiển thành ký hiệu như `visible` trong ví dụ. Với text Unicode, nhớ `String.length()` đếm UTF-16 code units, không phải số Unicode code points; khác biệt này không ảnh hưởng ví dụ escape ASCII bên trên nhưng có thể quan trọng với dữ liệu tổng quát.

Không dùng lời hứa “cứ escape hai lần là an toàn”: hai tầng escape phải có **mục đích rõ ràng** (source Java → String runtime → parser của định dạng cụ thể). Kiểm tra cả đầu vào, đầu ra và số lần chuyển đổi trong test.

## 8. Checklist thực hành

- Xác định chuỗi đang chứa **ký tự xuống dòng thật** hay cặp `\` + `n`: dùng `length()` và ký hiệu hóa output.
- Dùng `translateEscapes()` chỉ khi đầu vào tuân theo **quy ước escape kiểu Java** và bạn thật sự muốn chuyển đổi.
- Phân biệt **lỗi biên dịch** (`"\q"` trong source) với **lỗi runtime** (`"\\q".translateEscapes()`).
- Ghi nhớ các nhóm escape hợp lệ: control (`\b`, `\t`, `\n`, `\f`, `\r`), space (`\s`), quote, backslash, octal và continuation.
- Không giả định `\uXXXX`, `\xNN`, `\d`, `\/` luôn hợp lệ: chọn đúng parser theo nguồn dữ liệu.
- Bắt `IllegalArgumentException` ở ranh giới xử lý input, báo ngữ cảnh và không nuốt lỗi.
- Không decode lặp lại khi không có chủ đích; hai lần chuyển đổi có thể khác một lần.
- Trong Java 15+, API này là **ổn định**, không yêu cầu preview; khi build dự án mới, dùng JDK được hỗ trợ và cấu hình `--release` theo phiên bản Java tối thiểu của ứng dụng.

## Tài liệu chính thức

- Oracle Java SE 15 `String.translateEscapes()`, bảng escape và `IllegalArgumentException`: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html
- Oracle Java SE 25 `String.translateEscapes()`, xác nhận API vẫn còn được hỗ trợ: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html
- Java Language Specification Java SE 15, `3.3 Unicode Escapes`, `3.10.6 Text Blocks` và `3.10.7 Escape Sequences`: https://docs.oracle.com/javase/specs/jls/se15/html/jls-3.html
- Oracle Java `IllegalArgumentException`, hệ phân cấp unchecked exception: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/IllegalArgumentException.html

Nội dung tập trung vào API Java 15 **đã chính thức và vẫn đúng trong Java hiện đại**, tránh các cơ chế preview hoặc cách làm lỗi thời.
