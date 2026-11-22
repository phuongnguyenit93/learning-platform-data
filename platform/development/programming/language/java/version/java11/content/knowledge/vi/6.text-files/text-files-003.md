# Java 11+ — `Files.readString` với UTF-8 hoặc `Charset` tường minh

## 1. Mục đích và hai cách gọi

Từ **Java 11**, `java.nio.file.Files` cung cấp `readString` để đọc **toàn bộ nội dung một tệp văn bản** thành một `String`. Nội dung trên đĩa tồn tại dưới dạng **byte**; phương thức cần một *charset* để giải mã byte thành ký tự Unicode trong Java.

Có hai overload đang được dùng trong Java hiện đại:

```java
public static String readString(Path path) throws IOException;
public static String readString(Path path, Charset cs) throws IOException;
```

| Cách gọi | Charset giải mã | Khi sử dụng |
| --- | --- | --- |
| `Files.readString(path)` | **UTF-8**, được quy định cố định bởi API. | Khi biết tệp được mã hóa UTF-8, trường hợp thường gặp nhất. |
| `Files.readString(path, StandardCharsets.UTF_8)` | **UTF-8** tường minh. | Khi muốn nêu rõ hợp đồng mã hóa trong code, hoặc giữ nhất quán với các lệnh đọc/ghi khác. |
| `Files.readString(path, StandardCharsets.UTF_16LE)` | UTF-16 little-endian. | Chỉ khi **đã biết** byte của tệp được ghi bằng UTF-16LE. |
| `Files.readString(path, StandardCharsets.ISO_8859_1)` | ISO-8859-1. | Khi phải đọc đầu vào được cung cấp thực sự ở charset này. |

Hai lệnh đầu **tương đương về cách giải mã**. Không có chuyện overload một tham số tự chọn bảng mã theo hệ điều hành, ngôn ngữ máy, biến môi trường hoặc `Charset.defaultCharset()`. Sự bảo đảm UTF-8 thuộc chính API `Files.readString(Path)` từ Java 11 và vẫn còn hiệu lực.

`Charset` ở đây là đối tượng thuộc `java.nio.charset.Charset`; các hằng như `StandardCharsets.UTF_8` đến từ `java.nio.charset.StandardCharsets`. Các chuẩn phổ biến được cung cấp sẵn, giúp tránh lỗi đánh máy tên bảng mã.

## 2. Đọc tệp UTF-8: cách dùng thực tế

Giả sử tệp `data/notes.txt` tồn tại và được mã hóa UTF-8:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

// Đoạn mã minh họa, đặt trong phương thức có throws IOException hoặc try/catch.
Path path = Path.of("data", "notes.txt");

String implicitUtf8 = Files.readString(path);
String explicitUtf8 = Files.readString(path, StandardCharsets.UTF_8);

// Với cùng tệp không đổi, hai chuỗi nhận được có cùng nội dung.
System.out.println(implicitUtf8.equals(explicitUtf8));
```

Trong một chương trình thực tế, cần xác định rõ `Path`:

- `Path.of("data", "notes.txt")` tạo **đường dẫn tương đối** đến thư mục làm việc hiện tại của tiến trình Java; nó không mặc nhiên tìm trong thư mục nguồn `src` hoặc trong classpath.
- `Path.of("/absolute/path/to/notes.txt")` minh họa đường dẫn tuyệt đối kiểu Unix; trên Windows cách viết đường dẫn tuyệt đối khác. Ưu tiên cấu hình đường dẫn phù hợp môi trường triển khai.
- `Path.of(...)` chỉ tạo đối tượng đường dẫn; nó **không** đảm bảo tệp đã tồn tại hoặc có quyền đọc. Lỗi sẽ được phát hiện khi thao tác I/O.

Phương thức trả về toàn bộ văn bản trong một `String` duy nhất. Nó **không tự thêm dấu xuống dòng**, không tự tách dòng, không bỏ dòng trống và không cắt khoảng trắng đầu/cuối. Tệp rỗng hợp lệ cho kết quả `""`.

## 3. Chọn đúng `Charset`: phụ thuộc byte thật của tệp

UTF-8 là lựa chọn phù hợp cho nội dung mới khi hệ thống có quyền quyết định định dạng. Tuy nhiên, nếu dữ liệu bên ngoài **đã được ghi bằng charset khác**, chương trình phải dùng chính charset đó khi đọc. Việc chọn charset là hợp đồng của định dạng/tệp/dịch vụ cung cấp; tên tệp `.txt` tự nó không nói lên bảng mã.

Ví dụ tệp được tạo với UTF-16LE:

```java
Files.writeString(path, "Xin chào", StandardCharsets.UTF_16LE);
String text = Files.readString(path, StandardCharsets.UTF_16LE);
```

Ở ví dụ trên, cả chiều **ghi byte** và **đọc byte** đều thống nhất UTF-16LE. Nếu đọc các byte này bằng UTF-8 thì kết quả có thể sai hoặc quá trình giải mã có thể thất bại. Ngược lại, đọc một tệp UTF-8 bằng ISO-8859-1 có thể tạo ra ký tự sai mà **không ném ngoại lệ** vì bộ giải mã vẫn tìm được ánh xạ cho các byte. Sai bảng mã không phải lúc nào cũng được phát hiện bằng exception.

Điều cần tránh:

```java
// Sai ý nghĩa nếu tệp không thực sự dùng bảng mã tương ứng:
String text = Files.readString(path, StandardCharsets.ISO_8859_1);

// Không nên đọc đúng rồi mới "sửa" bằng cách chuyển qua byte theo charset đoán:
String guessed = new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
```

Câu lệnh `new String(...)` thứ hai có thể giải mã UTF-8 nhưng đọc gián tiếp qua `readAllBytes` không mang lại lợi ích nếu mục tiêu chỉ là một `String`. Hãy dùng `Files.readString` và charset đúng ngay từ đầu. Khi định dạng cần bảng mã không có hằng trong `StandardCharsets`, có thể dùng `Charset.forName("ten-charset-duoc-ho-tro")`, nhưng phải biết chính xác tên và môi trường có hỗ trợ.

**Không có tự động dò charset** trong hai overload `readString`. Nếu không biết bảng mã đầu vào, cần xác định từ đặc tả, header hoặc nguồn tạo tệp trước khi giải mã; đừng coi UTF-8 là kết quả của một thuật toán “đoán”.

## 4. Dấu xuống dòng và Unicode có được giữ nguyên không?

`Files.readString` đọc mọi ký tự, **bao gồm dấu kết thúc dòng giữa các dòng và ở cuối tệp**, rồi giữ chúng trong `String` theo kết quả giải mã. Ví dụ tệp chứa chuỗi:

```text
Dòng 1\r\nDòng 2\n
```

Trong đoạn biểu diễn trên, `\r\n` và `\n` là **ký hiệu escape để giải thích byte/ký tự điều khiển**: hai dòng có kiểu xuống dòng khác nhau. Sau khi đọc với charset đúng, chuỗi vẫn có `\r\n` tại chỗ cũ và `\n` cuối tệp. `readString` không thay chúng bằng `System.lineSeparator()`.

Cần phân biệt với `Files.readAllLines`, `Files.lines` hoặc `BufferedReader.readLine()`: các API đọc theo dòng đó trả về **nội dung từng dòng mà không giữ nguyên ký tự kết thúc dòng**. Nếu yêu cầu là so sánh nguyên văn, tính checksum trên dữ liệu văn bản, hoặc bảo tồn định dạng newline thì `readString` thường thuận tiện hơn (miễn tệp đủ nhỏ).

Đối với Unicode, Java `String` dùng các đơn vị mã UTF-16. Một biểu tượng 🌍 được đọc đúng từ UTF-8 vẫn là một Unicode code point, nhưng trong Java `String.length()` nó chiếm hai đơn vị UTF-16. Điều này **không** có nghĩa charset UTF-8 đã giải mã sai:

```java
String earth = "\uD83C\uDF0D"; // 🌍
earth.length();                           // 2 đơn vị UTF-16
earth.codePointCount(0, earth.length()); // 1 Unicode code point
```

Khi đọc Unicode từ tệp, hãy kiểm tra **giá trị chuỗi** và dùng `codePointCount` khi thực sự cần đếm code point, thay vì mặc định một ký tự hiển thị luôn tương đương một đơn vị của `length()`.

## 5. UTF-8 BOM: tình huống cần nhận biết

Một số tệp UTF-8 có ba byte đầu `EF BB BF` (*byte order mark*, BOM). Khi sử dụng `StandardCharsets.UTF_8` của Java, chuỗi nhận được có thể bắt đầu bằng ký tự `U+FEFF`; **`Files.readString` không tự ý bỏ ký tự đầu đó**.

Ví dụ, nếu tệp có byte `EF BB BF 41` (BOM UTF-8 rồi đến chữ `A`), kết quả có thể là chuỗi gồm `U+FEFF` theo sau bởi `A`. Kiểm tra:

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
boolean hasLeadingBom =
        !text.isEmpty() && text.charAt(0) == '\uFEFF';
```

Nếu **đặc tả đầu vào** coi BOM là marker cần loại bỏ, có thể dùng `text = text.substring(1)` khi `hasLeadingBom` là `true`. Không nên xóa ký tự `U+FEFF` ở mọi nơi hoặc tự động xóa ký tự đầu nếu chưa biết cấu trúc đầu vào. Việc chọn `UTF_16`, `UTF_16LE` hay `UTF_16BE` có quy tắc riêng về thứ tự byte và BOM; chọn đúng charset theo định dạng cụ thể thay vì suy đoán.

## 6. Ví dụ Java 11+ đầy đủ, chạy độc lập

Chương trình tự tạo một thư mục tạm, ghi các tệp có bảng mã **đã biết**, đọc lại, đối chiếu kết quả và xóa dữ liệu thử nghiệm. Vì kết quả stdout chỉ in boolean/tên ngoại lệ nên nhất quán giữa nhiều hệ điều hành và encoding console.

Lưu vào tệp **`ReadStringCharsetsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadStringCharsetsDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("read-string-");
        Path utf8 = dir.resolve("utf8.txt");
        Path latin1 = dir.resolve("latin1.txt");
        Path empty = dir.resolve("empty.txt");
        Path bom = dir.resolve("bom.txt");

        try {
            String expected = "Xin ch\u00E0o \uD83C\uDF0D\r\nD\u00F2ng 2\n";
            Files.writeString(utf8, expected, StandardCharsets.UTF_8);
            Files.writeString(latin1, "Caf\u00E9", StandardCharsets.ISO_8859_1);
            Files.writeString(empty, "", StandardCharsets.UTF_8);
            Files.write(bom, new byte[] {
                    (byte) 0xEF, (byte) 0xBB, (byte) 0xBF, (byte) 'A'
            });

            String fromDefault = Files.readString(utf8);
            String fromExplicit = Files.readString(utf8, StandardCharsets.UTF_8);

            System.out.println("utf8-default=" + fromDefault.equals(expected));
            System.out.println("utf8-explicit=" + fromExplicit.equals(expected));
            System.out.println("line-endings-kept=" +
                    (fromDefault.contains("\r\n") && fromDefault.endsWith("\n")));
            System.out.println("latin1-correct=" +
                    Files.readString(latin1, StandardCharsets.ISO_8859_1)
                            .equals("Caf\u00E9"));

            try {
                Files.readString(latin1, StandardCharsets.UTF_8);
                System.out.println("wrong-utf8=unexpected-success");
            } catch (MalformedInputException ex) {
                System.out.println("wrong-utf8=MalformedInputException");
            }

            System.out.println("empty-is-empty=" + Files.readString(empty).isEmpty());

            String fromBom = Files.readString(bom, StandardCharsets.UTF_8);
            System.out.println("utf8-bom-retained=" +
                    (fromBom.length() == 2 && fromBom.charAt(0) == '\uFEFF'));
        } finally {
            Files.deleteIfExists(utf8);
            Files.deleteIfExists(latin1);
            Files.deleteIfExists(empty);
            Files.deleteIfExists(bom);
            Files.deleteIfExists(dir);
        }
    }
}
```

Biên dịch và chạy bằng **JDK 11 trở lên**:

```bash
javac -encoding UTF-8 --release 11 ReadStringCharsetsDemo.java
java ReadStringCharsetsDemo
```

Stdout:

```text
utf8-default=true
utf8-explicit=true
line-endings-kept=true
latin1-correct=true
wrong-utf8=MalformedInputException
empty-is-empty=true
utf8-bom-retained=true
```

Giải thích kết quả:

- Hai dòng đầu cho thấy overload mặc định và overload `StandardCharsets.UTF_8` đọc đúng cùng dữ liệu Unicode.
- `line-endings-kept=true` xác minh tổ hợp `\r\n` giữa tệp và `\n` ở cuối không bị thay đổi.
- `latin1-correct=true` cho thấy phải dùng charset phù hợp với byte đã ghi.
- Tệp `latin1` chứa byte `E9` cho chữ `é`. Khi thử giải mã bằng UTF-8, byte này tạo chuỗi UTF-8 không hợp lệ và dẫn đến `MalformedInputException`. Đây là một trường hợp **cố ý thử lỗi**, không có nghĩa mọi trường hợp chọn sai charset đều ném exception.
- Tệp rỗng trả về `String` rỗng, không phải `null`.
- Bộ byte BOM UTF-8 ở đầu được giải mã thành `U+FEFF`, vì vậy `fromBom.length() == 2` khi theo sau là `A`.
- `finally` xóa các tệp tạm để ví dụ có thể chạy độc lập mà không để dữ liệu học tập trong thư mục dự án. Các lệnh `Files.writeString` chỉ dùng để **tạo input kiểm chứng**; nhiệm vụ chính là minh họa cách `readString` giải mã chúng.

## 7. Những ngoại lệ cần xử lý

`Files.readString` có chữ ký `throws IOException`. Các vấn đề thường gặp:

| Tình huống | Điều xảy ra / hướng xử lý |
| --- | --- |
| Tệp không tồn tại | Có thể nhận `NoSuchFileException` (thuộc `IOException`); kiểm tra đường dẫn, nơi chạy, cấu hình và tên tệp. |
| Không có quyền đọc | Có thể nhận `AccessDeniedException` hoặc một lỗi `IOException` liên quan đến provider/hệ điều hành. |
| Byte không giải mã được theo charset đã chọn | `IOException`, thường là `MalformedInputException` hoặc ngoại lệ mã hóa ký tự phù hợp; kiểm tra charset từ nguồn dữ liệu. |
| Tệp rỗng | `readString` trả `""`; đây là kết quả bình thường, không phải ngoại lệ. |
| Tệp cực lớn | Có thể gặp `OutOfMemoryError`; `readString` không dành cho đầu vào quá lớn. |
| Đường dẫn là thư mục hoặc tài nguyên không phù hợp | Thao tác có thể thất bại bằng `IOException`; không được giả định mọi `Path` là tệp văn bản thông thường. |

Ví dụ xử lý lỗi ở ranh giới I/O:

```java
// Đoạn minh họa trong một phương thức; import java.io.IOException.
try {
    String content = Files.readString(path, StandardCharsets.UTF_8);
    // Xử lý content...
} catch (IOException ex) {
    // Ghi nhận đường dẫn/nguyên nhân phù hợp và thông báo thất bại cho caller.
    // Không coi lỗi đọc/giải mã là một tệp rỗng hợp lệ.
    throw ex;
}
```

`MalformedInputException` là một nhánh của `IOException`; có thể bắt riêng khi cần báo người dùng rằng charset đầu vào không hợp lệ. Chỉ bắt `IOException` để xử lý thống nhất nếu không cần phân loại sâu.

**Quản lý tài nguyên:** `Files.readString` **tự đóng tệp** sau khi đọc xong hoặc khi xảy ra lỗi đọc, nên không cần tự mở `Reader` hay đặt `String` trong try-with-resources. Khi dùng `Files.newBufferedReader`/`Files.lines`, trách nhiệm đóng tài nguyên lại thuộc về code của bạn.

## 8. Đọc toàn bộ hay đọc theo luồng?

`Files.readString` tiện lợi cho tệp văn bản có kích thước hợp lý: cấu hình nhỏ, Markdown, JSON, văn bản đầu vào được kiểm soát. Nó tạo cả chuỗi trong bộ nhớ; với tệp có kích thước lớn hoặc không đáng tin cậy, cần đặt giới hạn trước khi dùng, vì tệp cực lớn có thể gây lỗi cấp phát.

Nếu mục tiêu là **xử lý từng dòng mà không giữ toàn bộ tệp** trong `String`, dùng `Files.newBufferedReader` cùng charset tường minh và đóng bằng try-with-resources:

```java
// Đoạn minh họa, cần import java.io.BufferedReader và IOException.
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng, không lưu tất cả dòng vào bộ nhớ.
        System.out.println(line);
    }
}
```

Lưu ý `readLine()` không trả lại các dấu xuống dòng. Nếu nghiệp vụ cần giữ **nguyên thứ tự và ký tự xuống dòng**, hãy đọc theo khối ký tự bằng `Reader.read(char[])` hoặc dùng `readString` khi tệp đủ nhỏ. Với `Files.lines`, cần đóng `Stream<String>` sau sử dụng. Chuyển sang cách đọc theo luồng không tự bỏ qua yêu cầu kiểm soát kích thước dữ liệu và xử lý lỗi I/O.

## 9. Những nhầm lẫn thường gặp và cách sửa

| Nhầm lẫn | Cách đúng |
| --- | --- |
| “`readString(path)` dùng charset mặc định của máy.” | Overload này **luôn UTF-8**, theo hợp đồng API. |
| “`readString` tự nhận biết bảng mã của tệp.” | Không; charset phải có trong thông số kỹ thuật hoặc do ứng dụng xác định. |
| “Đọc sai charset chắc chắn ném exception.” | Có thể trả văn bản hỏng dấu; chỉ một số chuỗi byte không hợp lệ mới gây lỗi giải mã. |
| “Dùng `ISO_8859_1` cho mọi lỗi hiển thị tiếng Việt.” | Không. Phải biết encoding thực tế; với nội dung mới ưu tiên UTF-8 theo hợp đồng hệ thống. |
| “`readString` chỉ lấy dòng đầu / tự xóa newline.” | Nó đọc **toàn bộ tệp**, bao gồm các dấu xuống dòng. |
| “`readString` mở file nhưng người gọi phải `close()`.” | Phương thức xử lý đóng tài nguyên nội bộ; kết quả là `String`, không phải một handle tệp. |
| “Tệp rỗng gây lỗi hoặc trả `null`.” | Tệp rỗng hợp lệ trả `""`. |
| “Có thể dùng `readString` an toàn cho mọi tệp nhiều GB.” | Đọc toàn bộ có thể thiếu bộ nhớ; dùng đọc theo luồng khi dữ liệu lớn. |
| “`Path.of("notes.txt")` tự tìm tài nguyên trong `src/main/resources`.” | Đây là đường dẫn hệ thống tệp, được giải quyết theo thư mục làm việc hiện tại. |
| “BOM UTF-8 luôn bị tự động xóa.” | Byte BOM có thể xuất hiện như `U+FEFF` ở đầu chuỗi, cần xử lý theo hợp đồng tệp. |

## 10. Checklist khi viết code

1. **Biết đường dẫn:** xác định `Path` tương đối/tuyệt đối và môi trường chạy.
2. **Biết bảng mã:** nếu tệp là UTF-8, chọn `Files.readString(path)` hoặc ghi rõ `StandardCharsets.UTF_8`. Nếu định dạng khác, dùng charset **đúng với byte nguồn**.
3. **Giữ nguyên văn bản khi cần:** `readString` bảo tồn ký tự xuống dòng đã được giải mã; tránh vô tình `trim()`/`strip()` hoặc chuyển dòng nếu không có yêu cầu.
4. **Phân biệt lỗi và nội dung rỗng:** xử lý `IOException`, không nuốt lỗi rồi trả `""` cho mọi trường hợp.
5. **Quan tâm Unicode và BOM:** kiểm tra chuỗi kết quả, đặc biệt ở đầu tệp và với ký tự đa đơn vị UTF-16.
6. **Giới hạn quy mô:** dùng `readString` cho tệp hợp lý; với nguồn dữ liệu lớn hãy đọc theo luồng và quản lý tài nguyên.
7. **Test bằng tệp có charset đã biết:** tạo fixture bằng `Files.writeString(path, value, charset)` rồi so sánh chuỗi sau khi đọc. Thêm ca sai charset, tệp rỗng và line ending nếu chúng quan trọng cho ứng dụng.

### Tài liệu tham khảo chính thức

- [Java SE 11 — `Files.readString(Path)` và `Files.readString(Path, Charset)`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 25 — tài liệu `Files` hiện hành](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html)
- [Java SE 11 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/StandardCharsets.html)
