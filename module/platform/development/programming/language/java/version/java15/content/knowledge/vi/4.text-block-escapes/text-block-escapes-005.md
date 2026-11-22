# Escape \n, \r, \t và các ký tự điều khiển trong Java text block (Java 15+)

## 1. Hiểu đúng giá trị của escape

Text block (`"""`) là cú pháp viết một `String` trong Java, được hỗ trợ chính thức từ Java 15 và vẫn dùng trong các phiên bản hiện hành. Nội dung có thể trải nhiều dòng; các ký hiệu escape `\n`, `\r`, `\t`, `\b`, `\f` vẫn được giải mã giống như trong string literal thông thường.

Điều quan trọng nhất là phân biệt **mã nguồn** và **giá trị trong bộ nhớ**:

- Trong mã nguồn Java, `\n` gồm **dấu backslash và chữ n**, nhưng khi biên dịch nó tạo **một ký tự line feed (LF, U+000A)** trong `String`.
- Nếu muốn giá trị chứa nguyên **hai ký tự backslash và n**, phải viết `\\n` (hai dấu backslash liên tiếp rồi đến chữ n) trong mã Java.
- Một xuống dòng **vật lý** trong text block cũng thường tạo LF, dù không viết `\n`.
- Việc terminal hiển thị CR, TAB, BS hay FF **không làm thay đổi** các ký tự thực sự được lưu trong `String`.

Ví dụ ngắn:

```java
String bySourceLine = """
        first
        second""";

String byEscape = """
        first\nsecond""";

System.out.println(bySourceLine.equals(byEscape)); // true
```

Hai giá trị đều tương đương với Java string literal `"first\nsecond"`. Dấu xuống dòng ngay sau `"""` mở là bắt buộc về cú pháp nhưng **không tự thêm LF ở đầu** giá trị.

## 2. Các escape áp dụng trong text block

| Viết trong mã nguồn Java | Ký tự tạo ra trong `String` | Mã Unicode | Ghi chú |
|---|---|---|---|
| `\n` | LF, xuống dòng | U+000A | Có thể cùng tồn tại với LF sinh từ xuống dòng vật lý |
| `\r` | CR, carriage return | U+000D | Chỉ tạo CR; không tự thêm LF |
| `\t` | HT, horizontal tab | U+0009 | Ký tự TAB; độ rộng khi hiển thị tùy trình xem |
| `\b` | BS, backspace | U+0008 | Có thể ảnh hưởng con trỏ terminal; không xóa ký tự ra khỏi `String` |
| `\f` | FF, form feed | U+000C | Trình xem có thể dùng để ngắt trang hoặc bỏ qua |
| `\0` | NUL | U+0000 | Octal escape hợp lệ; Java `String` vẫn chứa ký tự sau NUL |
| `\s` | Dấu cách SP | U+0020 | Không phải control character; dùng để giữ dấu cách cuối dòng |
| `\\` (hai backslash trong mã Java) | Một backslash thật | U+005C | Cần khi muốn chữ `\\n` xuất hiện nguyên dạng |
| Backslash ngay trước xuống dòng **vật lý** | Không thêm ký tự tại chỗ xuống dòng | — | Line continuation: nối hai dòng nguồn |

Những escape `\"`, `'` cũng hợp lệ, nhưng dấu nháy kép/đơn riêng lẻ thường **không cần escape** bên trong text block. Khi cần giữ dãy ba dấu nháy kép liên tiếp, hãy escape ít nhất một dấu để không bị hiểu là dấu đóng.

Các octal escape khác cũng được Java chấp nhận, nhưng khi ký tự đã có escape dễ đọc như `\n` hoặc `\t`, nên ưu tiên ký hiệu có tên thay vì mã số.

## 3. Vì sao thứ tự xử lý text block quan trọng?

Sau khi Java nhận diện đúng dấu phân cách của text block, **nội dung** được xử lý theo trình tự:

1. **Chuẩn hóa kết thúc dòng:** Các line terminator vật lý LF, CR hay CRLF trong tệp nguồn đều thành LF.
2. **Loại incidental whitespace:** Phần thụt lề chung và khoảng trắng cuối dòng không được bảo vệ được bỏ đi.
3. **Giải mã escape sau cùng:** `\n`, `\r`, `\t`, `\s` và các escape khác mới chuyển thành ký tự tương ứng.

Vì escape được xử lý **cuối cùng**, `\r` tường minh vẫn tạo CR dù Java đã chuẩn hóa xuống dòng vật lý thành LF. Tương tự, `\t` không bị xóa như dấu thụt lề vô tình: nó chỉ trở thành TAB sau bước xử lý lề.

Do đó, **không thể suy luận giá trị text block chỉ bằng cách nhìn bố cục mã nguồn**. Khi nghi ngờ, hãy kiểm tra mã Unicode của từng ký tự hoặc dùng hàm hiển thị escape ở mục 8.

## 4. Escape \n và xuống dòng vật lý

### 4.1. Một LF hay hai LF?

```java
String one = """
        A\nB""";

String two = """
        A\n
        B""";
```

`one` tương đương `"A\nB"`: giữa `A` và `B` có **một** LF do `\n`.

`two` tương đương `"A\n\nB"`: LF đầu do `\n`, LF thứ hai do xuống dòng thật giữa hai dòng mã nguồn. Đây là nguyên nhân gây ra “dòng trống thừa” khi thêm `\n` vào một dòng vốn đã kết thúc bằng xuống dòng vật lý.

### 4.2. Dấu đóng ảnh hưởng LF cuối

```java
String withFinalLf = """
        A
        """;

String withoutFinalLf = """
        A""";
```

Giá trị của `withFinalLf` là `"A\n"`, còn `withoutFinalLf` là `"A"`. Để giữ dấu đóng trên dòng riêng mà **không** có LF cuối, đặt một backslash ngay trước xuống dòng vật lý:

```java
String alsoWithoutFinalLf = """
        A\
        """;
```

Escape **backslash + line terminator vật lý** loại bỏ chính xuống dòng đó. Nó không tạo LF như `\n`; cũng không tạo hai ký tự backslash và chữ n như `\\n`.

## 5. Escape \r và \r\n: CR khác LF

```java
String onlyLf = """
        row1\nrow2""";

String onlyCr = """
        row1\rrow2""";

String windowsLine = """
        row1\r\nrow2""";
```

Giá trị lần lượt tương đương với `"row1\nrow2"`, `"row1\rrow2"` và `"row1\r\nrow2"`. Trường hợp cuối chứa **hai ký tự điều khiển liên tiếp**, CR rồi LF.

Dù tệp `.java` được lưu với CRLF trên Windows, các dòng vật lý của text block vẫn được chuẩn hóa thành **LF**, không tự động trở thành CRLF trong `String`. Chỉ tạo `\r\n` rõ ràng khi định dạng hoặc giao thức tiêu thụ dữ liệu **yêu cầu** cặp CRLF; đừng thay mọi LF bằng CRLF theo thói quen.

Khi `\r` được in ra terminal, một số terminal đưa con trỏ về đầu dòng, số khác thể hiện khác nhau. `System.out.println` cũng tự thêm line terminator sau nội dung. Vì vậy, nhìn ảnh terminal không đủ để kết luận chuỗi có CR hay LF; hãy kiểm tra `charAt`, `length()` hoặc chuỗi đã được escape để quan sát.

**Lưu ý Unicode escape:** Cú pháp nguồn `\u000A` và `\u000D` được Java xử lý rất sớm, trước bước nhận diện token/text block. Đừng thay escape `\n`, `\r` bằng chúng trong mã Java với mong muốn giữ nguyên hành vi: chúng có thể bị biến thành xuống dòng ngay trong lúc phân tích mã nguồn và dẫn đến lỗi cú pháp.

## 6. Escape \t, \b, \f, \0 và \s

### Tab ngang \t

```java
String table = """
        name\tage
        Lan\t20""";
```

Giá trị chứa TAB giữa `name` và `age`, một LF, rồi TAB giữa `Lan` và `20`. TAB là **một ký tự U+0009**, không phải bốn hoặc tám dấu cách cố định. Cách căn cột phụ thuộc tab stop của trình xem; khi xuất dữ liệu có cấu trúc, dùng serializer/định dạng phù hợp thay vì giả định TAB sẽ căn đều trên mọi thiết bị.

### Backspace, form feed và NUL

```java
String special = """
        X\bY\fZ\0""";
```

Chuỗi gồm sáu ký tự: `X`, BS (U+0008), `Y`, FF (U+000C), `Z`, NUL (U+0000). Java không xóa `X` khi lưu BS vào `String`, cũng không cắt chuỗi tại NUL như một số giao diện kiểu C. Tác động của các ký tự này chỉ xuất hiện khi một hệ thống tiêu thụ/hiển thị chúng.

Đặc biệt, bên trong JSON string hợp lệ, các ký tự điều khiển U+0000–U+001F phải được **escape theo cú pháp JSON**; không được chèn thẳng như dữ liệu thô.

### Giữ dấu cách cuối dòng bằng \s

Java có bước loại dấu cách cuối dòng trong text block. Dùng `\s` nếu một dấu cách ở cuối dòng là dữ liệu có ý nghĩa:

```java
String trailingSpace = """
        A\s
        """;
```

Giá trị tương đương `"A \n"`: chữ `A`, một dấu cách U+0020, sau đó LF. `\s` tạo dấu cách **sau** khi Java đã thực hiện bước loại trailing whitespace.

## 7. Giữ nguyên backslash: khi nào dùng \\n?

```java
String control = """
        A\nB""";

String literalText = """
        A\\nB""";
```

Trong `control`, `\n` được giải mã thành **một LF**. Trong `literalText`, ký hiệu `\\n` ở mã nguồn có **hai dấu backslash**, nên giá trị thực chứa **một dấu backslash và chữ n**, không xuống dòng. Cách làm tương tự khi cần hiện chữ `\\r` hoặc `\\t` thay vì CR/TAB.

Đây là khác biệt quan trọng khi text block chứa nội dung của một ngôn ngữ khác. Ví dụ JSON:

```java
String json = """
        {"message":"line1\\nline2"}
        """;
```

Java tạo một `String` chứa văn bản JSON, trong đó đoạn `\\n` của JSON được giữ ở dạng backslash + n. **JSON parser** khi đọc mới giải mã đoạn đó thành xuống dòng bên trong giá trị `message`. Nếu mã Java ở trên chỉ viết `\n`, Java sẽ chèn một LF thật vào giữa JSON string; ký tự xuống dòng thô ấy làm JSON **không hợp lệ**. Với dữ liệu động, ưu tiên thư viện tạo JSON để xử lý escaping thay vì nối chuỗi thủ công.

Tương tự, khi viết đường dẫn có backslash như `C:\temp\files`, Java sẽ hiểu `\t` là TAB và `\f` là FF. Trong text block Java, viết `C:\\temp\\files` nếu muốn giá trị giữ nguyên từng dấu backslash của đường dẫn.

## 8. Chương trình có thể chạy và stdout xác định

Lưu toàn bộ mã dưới đây thành tệp **`TextBlockEscapeDemo.java`**. Mục tiêu của hàm `visible` là biến CR/LF/TAB/BS/FF/NUL thành các ký hiệu có thể nhìn thấy; nó cũng nhân đôi backslash thật để phân biệt “chữ `\\n`” với một LF.

```java
public class TextBlockEscapeDemo {
    private static String visible(String value) {
        return value.replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
                .replace("\b", "\\b")
                .replace("\f", "\\f")
                .replace("\0", "\\0");
    }

    public static void main(String[] args) {
        String natural = """
                one
                two""";

        String explicit = """
                one\ntwo""";

        String crlf = """
                one\r\ntwo""";

        String tabbed = """
                key\tvalue""";

        String controls = """
                X\bY\fZ\0""";

        String literalSlashN = """
                \\n""";

        String joined = """
                Hello\
                World""";

        String trailingSpace = """
                A\s
                """;

        System.out.println("naturalEqualsExplicit=" + natural.equals(explicit));
        System.out.println("natural=" + visible(natural));
        System.out.println("explicit=" + visible(explicit));
        System.out.println("crlf=" + visible(crlf));
        System.out.println("tabbed=" + visible(tabbed));
        System.out.println("controls=" + visible(controls));
        System.out.println("literalSlashN=" + visible(literalSlashN));
        System.out.println("joined=" + visible(joined));
        System.out.println("trailingSpace=" + visible(trailingSpace));
    }
}
```

Chạy với JDK 17 trở lên (không cần preview):

```bash
javac TextBlockEscapeDemo.java
java TextBlockEscapeDemo
```

**Stdout chính xác** (dấu `\\` trong phần hiển thị dưới đây là ký tự được in ra, không phải xuống dòng ẩn):

```text
naturalEqualsExplicit=true
natural=one\ntwo
explicit=one\ntwo
crlf=one\r\ntwo
tabbed=key\tvalue
controls=X\bY\fZ\0
literalSlashN=\\n
joined=HelloWorld
trailingSpace=A \n
```

Lưu ý dòng `literalSlashN=\\n` có **hai dấu backslash được in ra** bởi `visible`, vì `String` gốc chứa một backslash thật. Dòng `trailingSpace=A \n` có **một dấu cách sau chữ A**, được giữ bằng `\s`. Mỗi dòng log lại được `println` kết thúc bằng line terminator của môi trường, độc lập với các LF/CR nằm trong giá trị đầu vào.

## 9. Bảng chẩn đoán và quy trình áp dụng

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
|---|---|---|
| Xuất hiện dòng trống thừa | Viết `\n` ngay trước xuống dòng vật lý | So sánh với `"A\n\nB"`; bỏ một lần xuống dòng |
| Thiếu LF ở cuối chuỗi | Đặt `"""` đóng ngay cuối dòng nội dung hoặc có backslash nối dòng | Kiểm tra `endsWith("\n")`; đặt dấu đóng ở dòng mới nếu cần LF |
| Terminal in `\r` không như mong đợi | CR có thể điều khiển con trỏ thay vì hiển thị ký hiệu | Dùng `visible` hoặc kiểm tra `charAt` |
| Text block dùng LF dù tệp Java là CRLF | Java chuẩn hóa xuống dòng vật lý thành LF | Chỉ viết `\r\n` tường minh khi hợp đồng dữ liệu cần CRLF |
| TAB làm cột lệch | Tab stop tùy trình hiển thị | Kiểm tra ký tự U+0009; định dạng bảng ở tầng xuất |
| BS/FF/NUL hiển thị lạ | Ký tự điều khiển được consumer diễn giải | In dạng escape; kiểm tra nơi nhận có hỗ trợ không |
| Dấu cách cuối dòng bị mất | Incidental/trailing whitespace bị loại | Dùng `\s` để giữ một dấu cách đúng vị trí |
| Muốn hiển thị `\\n` nhưng bị xuống dòng | Backslash chưa được escape ở Java source | Dùng `\\n` (hai backslash trong mã nguồn) |
| Báo `illegal escape character` | Ví dụ `\d` không phải Java escape hợp lệ | Viết `\\d` để giữ backslash + d |
| Hai dòng nguồn bị dính nhau | Dấu backslash ngay trước xuống dòng vật lý | Xóa dấu nối dòng nếu cần LF |

Quy trình xử lý lỗi thực tế:

1. **Đọc đúng mã nguồn:** xác định đó là escape như `\n`, hai dấu backslash như `\\n`, hay xuống dòng vật lý giữa hai dòng.
2. **Kiểm tra LF cuối/đầu:** vị trí dấu đóng `"""` và dòng trống sau dấu mở quyết định những LF không nhìn thấy ngay.
3. **Kiểm tra từng ký tự runtime:** dùng `visible`, `length()`, `charAt(i)`, `codePoints()`; không đoán từ cách console trình bày ký tự điều khiển.
4. **Xác định hợp đồng đầu ra:** LF, CRLF, TAB hoặc điều khiển trang chỉ nên xuất hiện khi định dạng đích cần chúng.
5. **Phân biệt các tầng escape:** Java source, JSON/regex và trình hiển thị có thể giải mã ở các thời điểm khác nhau. Với JSON hoặc giao thức có serializer, để thư viện phụ trách escaping theo đúng chuẩn.
6. **Tạo kiểm thử rõ ràng:** với chuỗi cố định, dùng `equals` và so sánh ký tự. Ví dụ `assert natural.equals(explicit);` có thể dùng trong kiểm thử để khóa kỳ vọng.

**Ghi nhớ:** `\n` tạo LF, `\r` tạo CR, `\t` tạo TAB; các escape này được dịch **sau** chuẩn hóa xuống dòng/thụt lề của text block. Backslash + xuống dòng vật lý lại **bỏ** LF. Muốn giữ backslash nguyên dạng thì phải escape backslash ở Java source.

**Tham khảo (đặc tả hiện hành):** [Java SE 26 — Text Blocks](https://docs.oracle.com/en/java/javase/26/language/text-blocks.html) và [Java Language Specification 26, §3.10.6 Text Blocks, §3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se26/html/jls-3.html#jls-3.10.6).
