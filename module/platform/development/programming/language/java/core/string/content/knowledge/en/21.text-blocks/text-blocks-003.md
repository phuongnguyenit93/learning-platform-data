# Chuẩn hóa kết thúc dòng trong Java text block

## 1. Vấn đề: source code có CR, LF hoặc CRLF

**Text block** là cú pháp chuỗi nhiều dòng trong Java (chính thức từ Java 15), mở và đóng bằng ba dấu nháy kép `"""`. Nội dung của một file `.java` có thể sử dụng nhiều kiểu kết thúc dòng khác nhau:

| Tên | Ký hiệu | Mã Unicode | Escape trong chuỗi Java |
| --- | --- | --- | --- |
| Line Feed | LF | U+000A | `\n` |
| Carriage Return | CR | U+000D | `\r` |
| Carriage Return + Line Feed | CRLF | U+000D U+000A | `\r\n` |

Một số trình soạn thảo lưu code bằng CRLF, nơi khác lưu bằng LF. Khi dùng text block, bạn thường muốn giá trị chuỗi giống nhau dù file nguồn được định dạng trên Windows hay Linux.

**Quy tắc cốt lõi:** Java chuẩn hóa tất cả **dấu kết thúc dòng vật lý nằm trong nội dung text block của mã nguồn** thành **LF (`\n`)** khi biên dịch. Cụ thể:

- Một CRLF trong source được đổi thành **một** LF.
- Một CR đơn trong source được đổi thành LF.
- Một LF trong source được giữ nguyên.

Vì vậy, cùng một text block nếu chỉ thay định dạng dấu kết thúc dòng vật lý trong source sẽ cho cùng một giá trị chuỗi. Việc này **không có nghĩa mọi `String` trong Java tự động được chuẩn hóa**: chuỗi đọc từ file, socket hoặc database vẫn giữ dấu kết thúc dòng vốn có, trừ khi ứng dụng xử lý thêm.

## 2. Java xử lý text block theo thứ tự nào?

Theo *Java Language Specification* (JLS §3.10.6), nội dung text block được chuyển thành chuỗi qua ba giai đoạn, theo đúng thứ tự sau:

1. **Chuẩn hóa line terminators:** CRLF → LF, CR → LF; LF giữ nguyên.
2. **Loại bỏ khoảng trắng không chủ ý:** bỏ incidental indentation và khoảng trắng cuối dòng theo quy tắc tương đương `String.stripIndent()`.
3. **Giải mã escape:** xử lý `\n`, `\r`, `\t`, `\s`, `\\` và escape nối dòng bằng dấu `\`, theo quy tắc tương đương `String.translateEscapes()`.

```text
Text block trong source file
            |
            v
Chuẩn hóa CRLF và CR thành LF
            |
            v
Xử lý incidental whitespace
            |
            v
Giải mã các escape sequence
            |
            v
Giá trị String khi chương trình chạy
```

Tại sao thứ tự này quan trọng? Một CR xuất hiện **thực sự trong source file** thuộc bước 1 nên bị đổi thành LF. Nhưng khi bạn viết escape `\r` bằng hai ký tự dấu gạch chéo ngược và chữ `r`, ký tự CR chỉ được **tạo ra ở bước 3**. Khi đó bước chuẩn hóa đã kết thúc, nên CR này vẫn tồn tại trong giá trị `String`.

Hai khái niệm cần phân biệt rõ:

- **Physical line terminator:** ký tự xuống dòng thực tế giữa các dòng văn bản trong file mã nguồn.
- **Escape sequence:** cách viết `\n` hoặc `\r` dưới dạng mã Java; trình biên dịch chỉ diễn giải chúng thành ký tự điều khiển ở giai đoạn giải mã escape.

Không nên coi `\r\n` được viết bằng escape là dấu CRLF vật lý của source.

## 3. Giá trị text block với ba kiểu xuống dòng nguồn

Ví dụ Java:

```java
String colors = """
    red
    green
    blue
    """;
```

Dù file chứa ví dụ trên được lưu bằng LF, CRLF hay CR cho các dòng nằm trong text block, giá trị cuối cùng vẫn tương đương với:

```java
String colors = "red\n" + "green\n" + "blue\n";
```

Chuỗi `colors` có **15 ký tự**, gồm ba LF và không có CR.

Có thể hình dung cùng một source theo ba biểu diễn dưới đây. Ký hiệu `␍` chỉ CR và `␊` chỉ LF; đây là ký hiệu minh họa, không phải nội dung phải gõ vào chương trình:

```text
Source lưu bằng LF:
"""␊
    red␊
    blue␊
    """

Source lưu bằng CRLF:
"""␍␊
    red␍␊
    blue␍␊
    """

Source có lẫn CR và LF:
"""␍
    red␍
    blue␊
    """
```

Ba biến thể đều biểu diễn `"red\nblue\n"` sau khi chuẩn hóa và xử lý thụt lề. CRLF không tạo hai ký tự LF vì cả cặp được xem là một dấu kết thúc dòng.

### Dấu xuống dòng đầu và cuối

Cú pháp mở text block yêu cầu có dấu kết thúc dòng ngay sau `"""`. Dấu xuống dòng bắt buộc sau dấu mở **không phải ký tự đầu tiên của chuỗi**. Nhưng dấu xuống dòng trước dấu đóng được giữ nếu dấu đóng đặt trên một dòng riêng:

```java
String hasFinal = """
    red
    green
    """;

String noFinal = """
    red
    green""";

// hasFinal.equals("red\ngreen\n") == true
// noFinal.equals("red\ngreen") == true
```

Nếu cần chuỗi không kết thúc bằng LF, cách đặt dấu đóng như `noFinal` là một lựa chọn rõ ràng. Không nên nhầm thay đổi này với thay đổi kiểu CRLF/LF trong file nguồn.

## 4. Escape tạo ra CR hoặc CRLF sau bước chuẩn hóa

Text block vẫn hỗ trợ escape của Java string. Vì chúng được diễn giải ở giai đoạn cuối, bạn có thể chủ động tạo CR hoặc CRLF:

```java
String withCr = """
    A\rB
    """;

String withCrLf = """
    A\r\nB
    """;

String withLf = """
    A\nB
    """;
```

Với dấu đóng trên dòng riêng, giá trị tương ứng là:

| Biến | Giá trị runtime, viết ở dạng Java literal | Giải thích |
| --- | --- | --- |
| `withCr` | `"A\rB\n"` | `\r` tạo CR; LF cuối đến từ dòng vật lý |
| `withCrLf` | `"A\r\nB\n"` | Hai escape tạo một CR và một LF; thêm LF cuối |
| `withLf` | `"A\nB\n"` | `\n` tạo LF; thêm LF cuối |

Ở đây, `withCrLf` chứa CRLF thực sự dù source code có thể được lưu bằng LF. Quy tắc chuẩn hóa dấu xuống dòng vật lý **không xóa CR do escape tạo ra**.

Một cú pháp khác dễ gây nhầm là dấu `\` ở cuối dòng vật lý, thường gọi là *line continuation escape*:

```java
String joined = """
    hello\
    world
    """;

// joined.equals("helloworld\n") == true
```

Dấu `\` ngay trước xuống dòng vật lý khiến newline đó **không xuất hiện** trong giá trị `String`. Ngược lại, `\n` được viết trên cùng dòng là escape **tạo** một LF. Quy tắc về khoảng trắng của text block vẫn có thể ảnh hưởng các dấu cách đặt cạnh dấu nối dòng.

## 5. Chương trình Java 17+ độc lập, kiểm tra được

Lưu đoạn sau vào tệp **`TextBlockLineEndingsDemo.java`**:

```java
public class TextBlockLineEndingsDemo {

    private static String visible(String value) {
        return value.replace("\\", "\\\\")
                    .replace("\r", "\\r")
                    .replace("\n", "\\n");
    }

    private static void show(String name, String value) {
        System.out.println(name + " = " + visible(value));
    }

    public static void main(String[] args) {
        String basic = """
            alpha
            beta
            """;

        String noFinal = """
            alpha
            beta""";

        String escapedCr = """
            A\rB
            """;

        String escapedCrLf = """
            A\r\nB
            """;

        String joined = """
            alpha\
            beta
            """;

        show("basic", basic);
        show("noFinal", noFinal);
        show("escapedCr", escapedCr);
        show("escapedCrLf", escapedCrLf);
        show("joined", joined);

        System.out.println("basic has CR = " + (basic.indexOf('\r') >= 0));
        System.out.println("basic equals literal = "
                + basic.equals("alpha\nbeta\n"));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 TextBlockLineEndingsDemo.java
java TextBlockLineEndingsDemo
```

Đầu ra chính xác:

```text
basic = alpha\nbeta\n
noFinal = alpha\nbeta
escapedCr = A\rB\n
escapedCrLf = A\r\nB\n
joined = alphabeta\n
basic has CR = false
basic equals literal = true
```

Trong output trên, `\r` và `\n` là **các ký tự hiển thị** do hàm `visible` thay thế; chúng giúp quan sát sự khác biệt vốn khó nhìn trong terminal. Hàm `visible` không sửa giá trị chuỗi gốc.

Để kiểm tra tính ổn định khi đổi nền tảng, hãy chạy chương trình, sau đó dùng editor thay kiểu kết thúc dòng của file nguồn từ LF thành CRLF (hoặc ngược lại), biên dịch và chạy lại. Nếu chỉ thay dấu xuống dòng vật lý của file, output sẽ không đổi.

### Vì sao không chỉ dùng println để quan sát?

Nếu in trực tiếp `basic` hoặc `escapedCrLf`, terminal thường thể hiện LF và CRLF gần giống nhau. Khi cần kết luận về **ký tự thực tế**, dùng một trong những cách sau:

- `equals("alpha\nbeta\n")` để so sánh chính xác.
- `indexOf('\r')` hoặc `indexOf('\n')` để tìm ký tự.
- `length()`, `charAt()` hoặc duyệt code point nếu cần kiểm tra cấu trúc.
- Biến dấu điều khiển thành ký hiệu hiển thị như hàm `visible` ở trên.

## 6. Khi nào nên chủ động đổi LF sang CRLF?

Text block tạo LF nhất quán. Phần mềm có thể cần chuyển đổi thành dạng khác **vì yêu cầu đầu ra**, chẳng hạn một giao thức hoặc định dạng file quy định CRLF. Đó là thao tác runtime riêng biệt:

```java
String content = """
    first
    second
    """;

String crlf = content.replace("\n", "\r\n");
System.out.println(crlf.equals("first\r\nsecond\r\n")); // true
```

Đoạn trên phù hợp khi **đầu vào chỉ chứa LF**. Nếu chuỗi ban đầu đã có CRLF do escape hoặc do ghép với dữ liệu khác, thay mọi LF như vậy sẽ biến `\r\n` thành `\r\r\n`. Đừng áp dụng chuyển đổi mù quáng cho chuỗi chưa biết trạng thái.

Nếu đích yêu cầu dấu xuống dòng theo **hệ điều hành đang chạy** thay vì một dạng cố định:

```java
String nativeText = content.replace("\n", System.lineSeparator());
```

`System.lineSeparator()` trên Windows thông thường là CRLF; trên nhiều hệ Unix là LF. Đây là lựa chọn theo runtime và không làm thay đổi quy tắc chuẩn hóa của text block. Nếu đặc tả giao thức yêu cầu CRLF bất kể máy chạy, dùng `"\r\n"` rõ ràng hơn `System.lineSeparator()`.

Khi ghi file, `Files.writeString(path, content, StandardCharsets.UTF_8)` ghi ra đúng các dấu kết thúc dòng **đã tồn tại trong `content`**. API ghi file không tự động đổi LF do text block sinh ra thành CRLF theo hệ điều hành.

## 7. Khác nhau giữa chuẩn hóa lúc biên dịch và lúc chạy

Đối tượng `String` có thể được tạo từ nhiều nguồn. Chỉ text block literal trong mã Java mới được compiler xử lý theo ba bước đã nêu.

| Nguồn/cơ chế | Thời điểm | Quy tắc với CR/LF |
| --- | --- | --- |
| Text block literal `"""..."""` | Biên dịch | Chuẩn hóa dấu kết thúc dòng **vật lý** thành LF |
| String literal thường `"a\r\nb"` | Biên dịch | Escape tạo CR và LF; không đi qua bước chuẩn hóa nội dung text block |
| `String.stripIndent()` | Runtime | Bỏ incidental indentation; không phải lệnh tự động chuyển mọi CRLF thành LF trong mọi đầu vào |
| `String.translateEscapes()` | Runtime | Giải mã escape; có thể tạo CR và LF |
| `String.lines()` | Runtime | Tách dòng theo CR, LF, CRLF; stream kết quả không giữ dấu kết thúc dòng |
| `System.lineSeparator()` | Runtime | Cung cấp dấu xuống dòng của nền tảng, không sửa text block |
| `String.replace(...)` | Runtime | Thay ký tự/chùm ký tự theo quy tắc được lập trình |

Ví dụ dữ liệu đến từ bên ngoài có thể chứa CRLF/CR dù text block của bạn toàn LF:

```java
String received = "a\r\nb\rc\n";
String lfOnly = received.replace("\r\n", "\n").replace("\r", "\n");

System.out.println(lfOnly.equals("a\nb\nc\n")); // true
```

Tại đây ứng dụng đang thực hiện **chuẩn hóa runtime**, độc lập với cơ chế của text block. Thứ tự thay `"\r\n"` trước rồi thay `"\r"` giúp xử lý cả CRLF lẫn CR đơn.

## 8. Lỗi thường gặp

1. **Cho rằng file Java lưu bằng CRLF sẽ tạo text block chứa CRLF.** Thực tế CRLF vật lý được chuyển thành LF trong bước đầu.
2. **Cho rằng text block không thể chứa CR.** Escape `\r` có thể tạo CR sau bước chuẩn hóa.
3. **Nhầm newline bắt buộc sau dấu mở với newline cuối chuỗi.** Newline sau dấu mở `"""` là cú pháp; newline cuối phụ thuộc dấu đóng đứng cùng dòng nội dung cuối hay dòng riêng.
4. **Nhầm `\n` với dấu `\` nối dòng.** `\n` thêm LF; dấu `\` ngay trước physical newline bỏ newline đó.
5. **Không tính đến incidental indentation.** Sau chuẩn hóa line terminator, Java còn xóa khoảng trắng đầu và cuối dòng theo quy tắc text block; kết quả không chỉ phụ thuộc newline.
6. **Dùng println để chứng minh giá trị newline.** Console có thể làm CRLF và LF nhìn giống nhau; hãy kiểm tra bằng `equals` hoặc mã hóa ký tự thành ký hiệu dễ đọc.
7. **Đổi LF thành CRLF khi chuỗi đã có CRLF.** Thay thế không kiểm soát có thể sinh `\r\r\n`.
8. **Phụ thuộc hệ điều hành mà không có yêu cầu rõ.** LF của text block được thiết kế để ổn định xuyên nền tảng; đầu ra có quy tắc riêng mới cần chuyển đổi.

## 9. Tự kiểm tra

**Câu 1:** File Java có text block sau và được lưu bằng CRLF. Giá trị `s` là gì?

```java
String s = """
    A
    B
    """;
```

**Đáp án:** `"A\nB\n"`; dấu kết thúc dòng vật lý CRLF được chuẩn hóa thành LF. Giá trị không có CR.

**Câu 2:** Text block sau chứa bao nhiêu CR và LF?

```java
String s = """
    A\r\nB
    """;
```

**Đáp án:** **Một CR và hai LF**. Cặp escape `\r\n` tạo CRLF, còn newline vật lý cuối text block tạo thêm LF. `s.equals("A\r\nB\n")` là `true`.

**Câu 3:** Vì sao không dùng `System.lineSeparator()` một cách vô điều kiện để ghi giao thức yêu cầu CRLF?

**Đáp án:** Vì ký hiệu từ `System.lineSeparator()` phụ thuộc môi trường chạy. Giao thức yêu cầu CRLF cố định thì phải tạo chính xác `"\r\n"` bất kể hệ điều hành.

**Câu 4:** Tại sao đổi source code từ CRLF sang LF không làm thay đổi `String` text block, nhưng đổi `"\r\n"` thành `"\n"` trong một escape lại có thể làm thay đổi?

**Đáp án:** Trường hợp đầu là thay đổi dấu xuống dòng **vật lý** được chuẩn hóa khi biên dịch. Trường hợp sau là thay đổi **escape sequence** được dịch ở giai đoạn cuối, nên làm đổi các ký tự thực của chuỗi.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 21 — §3.10.6 Text Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.6): thứ tự chuẩn hóa line terminators, xử lý incidental whitespace và dịch escape.
- [Oracle Programmer's Guide to Text Blocks, Java SE 21](https://docs.oracle.com/en/java/javase/21/text-blocks/index.html): hướng dẫn thực tế, ví dụ CR/LF/CRLF, newline cuối và thay đổi dấu xuống dòng theo nền tảng.

Các ví dụ áp dụng cho Java 17 trở lên; text block là tính năng ngôn ngữ chính thức từ Java 15.