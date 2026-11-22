# Phân biệt chuẩn hóa văn bản với chọn bảng mã khi ghi tệp trong Java

## 1. Hai câu hỏi khác nhau: String có nội dung gì và tệp chứa byte gì?

Khi tạo một tệp văn bản trong Java, có ít nhất **hai quyết định độc lập**:

1. **Chuẩn hóa văn bản (text normalization)**: Các ký tự trong `String` phải như thế nào? Có cần bỏ khoảng trắng thụt lề, thống nhất `\r\n` thành `\n`, giữ hay bỏ dòng mới cuối chuỗi, chuẩn hóa Unicode NFC/NFD hay không?
2. **Chọn bảng mã (charset/character encoding)**: Khi ghi `String` đó xuống tệp, dùng quy tắc chuyển **ký tự → byte** nào, ví dụ `StandardCharsets.UTF_8` hay `UTF_16LE`?

Một cách diễn đạt ngắn:

~~~text
Nguồn dữ liệu / text block / dữ liệu từ mạng
             |
             v
     String trong Java
             |
    (chuẩn hóa nội dung theo chính sách)
             v
      String mong muốn
             |
     (mã hóa bằng Charset)
             v
        Dãy byte
             |
       ghi xuống tệp
~~~

**Chuẩn hóa không tự chọn charset; chọn charset không tự chuẩn hóa whitespace.** Đây là điểm cần nắm khi làm việc với text blocks và dữ liệu tiếng Việt.

Ví dụ hai chuỗi:

~~~java
String a = "Hello\n";
String b = "Hello\r\n";
~~~

`a` và `b` khác nhau về **ký tự**: một bên có LF (U+000A), bên kia có CR (U+000D) rồi LF. Dù cùng ghi bằng UTF-8, chúng vẫn tạo **các dãy byte khác nhau**. Chuyển từ UTF-8 sang UTF-16LE cũng không tự làm `a.equals(b)` thành true.

Ngược lại, **cùng một String** được ghi bằng UTF-8 và UTF-16LE thường tạo **byte khác nhau** nhưng khi đọc lại **bằng đúng charset tương ứng** vẫn tái tạo cùng String.

## 2. Ba lớp cần tách trong tư duy

| Lớp | Dữ liệu đang xử lý | Công cụ Java điển hình | Điều công cụ làm |
| --- | --- | --- | --- |
| Nội dung ký tự | `String` gồm ký tự, khoảng trắng, dấu xuống dòng | `stripIndent()`, `strip()`, `replace()`, `Normalizer.normalize()` | Có thể thay đổi dãy ký tự của String |
| Mã hóa/giải mã | Quan hệ giữa ký tự và byte | `Charset`, `StandardCharsets.UTF_8`, `Files.writeString/readString` | Chuyển String thành byte hoặc byte thành String |
| Lưu trữ | Dãy byte thực tế trong tệp | `Path`, `Files.write`, `Files.readAllBytes` | Đọc/ghi byte; đường dẫn hoặc đuôi `.txt` không tự xác định charset |

**Ví dụ:** Nếu `text` chứa `"A\nB\n"`, UTF-8 mã hóa các ký tự ASCII này thành byte `41 0A 42 0A` (hệ thập lục phân). UTF-16LE mã hóa cùng String thành `41 00 0A 00 42 00 0A 00`. Cả hai đều giữ ý nghĩa xuống dòng LF; chỉ khác cách biểu diễn dưới dạng byte.

Không nên nói “chuẩn hóa sang UTF-8” để chỉ việc xóa khoảng trắng hoặc đổi CRLF thành LF. UTF-8 là **charset**, còn xóa khoảng trắng/đổi CRLF là **chính sách biến đổi nội dung**.

## 3. Chuẩn hóa whitespace: các thao tác thực sự đổi ký tự

### 3.1. Thụt lề vô tình trong text block

Với text block Java:

~~~java
String html = """
    <p>Hello</p>
      <p>World</p>
    """;
~~~

Giá trị String có dạng:

~~~java
String html = "<p>Hello</p>\n  <p>World</p>\n";
~~~

Trình biên dịch đã loại bỏ **incidental indentation** theo quy tắc text block, nhưng vẫn giữ hai dấu cách có chủ đích trước dòng thứ hai và giữ LF cuối vì dấu đóng `"""` ở dòng riêng.

Text block là tính năng ngôn ngữ chính thức từ **Java 15**, nên các ví dụ trong bài dùng **Java 17+**. Trong mã nguồn, line terminators của text block được chuẩn hóa thành LF, rồi loại bỏ incidental whitespace, rồi giải mã escape sequences. Những bước này diễn ra khi tạo **giá trị String**, trước khi chương trình chọn charset để ghi tệp.

Vì vậy **text block không tự “lưu dưới dạng UTF-8”**. Nó tạo ra String; bước xuất ra byte nằm ở API I/O.

### 3.2. Chuẩn hóa các dạng line ending

Các ký tự kết thúc dòng thường gặp:

- `\n` (LF, U+000A): thường dùng trong giao thức và tệp trên Unix/Linux, cũng là kết quả chuẩn hóa line terminator trong text block.
- `\r\n` (CRLF, U+000D U+000A): thường xuất hiện trong văn bản từ Windows hoặc một số định dạng/giao thức.
- `\r` (CR): một dạng line ending cũ, vẫn có thể gặp trong dữ liệu.

Nếu hợp đồng dữ liệu yêu cầu **mọi line ending là LF**, có thể dùng:

~~~java
static String toLf(String text) {
    return text.replace("\r\n", "\n").replace('\r', '\n');
}
~~~

Phải thay `\r\n` **trước** `\r` để không biến một CRLF thành hai LF. Hàm chỉ thực hiện quy tắc đã định nghĩa; không tự xóa dòng trống hay khoảng trắng khác.

Đổi nội dung String bằng `toLf` là công việc **khác** với `Files.writeString(..., StandardCharsets.UTF_8)`. API ghi tệp sẽ mã hóa **những line endings đã có trong String**, không tự đổi `\r\n` thành `\n` chỉ vì charset được chọn là UTF-8.

**Cảnh báo:** đừng chuyển tất cả `\r` một cách máy móc nếu ký tự CR riêng có ý nghĩa đặc thù trong dữ liệu đầu vào. Trước khi chuẩn hóa, xác nhận định dạng và hợp đồng của tệp.

### 3.3. Bỏ thụt lề và khoảng trắng

Các API dễ bị nhầm:

| API | Mục đích chính | Hệ quả cần chú ý |
| --- | --- | --- |
| `stripIndent()` (Java 15+) | Bỏ incidental indentation ở nhiều dòng, giữ thụt lề tương đối | Có thể loại trailing whitespace của từng dòng và chuẩn hóa line endings thành LF |
| `indent(int)` (Java 12+) | Thêm hoặc bỏ thụt lề từng dòng | Chuẩn hóa line endings; có thể tác động tới dấu xuống dòng cuối |
| `strip()` (Java 11+) | Bỏ Unicode whitespace ở **đầu và cuối toàn bộ String** | Có thể xóa LF cuối, dòng trống có chủ đích |
| `stripLeading()`, `stripTrailing()` | Bỏ whitespace ở đầu hoặc cuối toàn bộ String | Không tương đương việc bỏ lề **từng dòng** |
| `trim()` | Bỏ các ký tự ở hai đầu theo ngưỡng lịch sử của phương thức | Khác với tiêu chí Unicode whitespace của `strip()`; không phải cách chuẩn hóa Unicode tổng quát |
| `replace("\r\n", "\n")` | Đổi một loại line ending sang loại khác | Không tự bỏ indentation hoặc chọn encoding |
| `String.lines()` | Tách thành stream dòng **không gồm line terminators** | Nếu nối lại, phải xác định delimiter và trailing newline theo chính sách |

**Không lạm dụng `strip()` để “làm sạch” mọi payload:** với SQL, Markdown, JSON có chữ ký số, cấu trúc định dạng cố định hoặc snapshot test, khoảng trắng đầu/cuối có thể là dữ liệu hợp lệ. Nếu cần giữ đúng một LF cuối, hãy xử lý theo quy tắc rõ ràng, không trông đợi `strip()` tự làm điều đó.

`stripIndent()` có cách tính thụt lề riêng (kể cả ảnh hưởng của dòng cuối nếu trống), nên không phải lúc nào cũng có cùng kết quả với trình biên dịch khi tạo text block có closing delimiter trên dòng riêng. Hãy **kiểm tra kết quả thực tế** với dữ liệu nguồn, không khẳng định hai cơ chế luôn tương đương với mọi bố cục.

## 4. Chọn charset: String được mã hóa thành byte như thế nào?

Java `String` biểu diễn nội dung ký tự; API `Charset` quyết định cách biểu diễn các ký tự ấy bằng byte khi xuất ra tệp:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("output.txt");
String content = "Xin chào\n";

Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Đoạn trên là ví dụ **tích hợp**, không phải class hoàn chỉnh. Nó ghi String với UTF-8. Nếu tệp đã tồn tại, mặc định `Files.writeString` tạo/truncate rồi ghi (theo tùy chọn mở tệp mặc định); cần lưu ý khi thao tác với dữ liệu thật.

**UTF-8 là lựa chọn nên dùng trong phần lớn hệ thống mới**, trừ khi hợp đồng bên nhận yêu cầu encoding khác. `StandardCharsets.UTF_8` có sẵn trong Java và không phụ thuộc máy cài thêm charset.

Một vài charset chuẩn khác:

- `StandardCharsets.UTF_16LE`: mã hóa UTF-16 little-endian; thường cần khi định dạng/giao thức quy định rõ, không phải lựa chọn mặc định của tệp text hiện đại.
- `StandardCharsets.UTF_16BE`: UTF-16 big-endian.
- `StandardCharsets.UTF_16`: UTF-16 với quy tắc xử lý byte-order mark; khi cần byte chính xác và không muốn BOM, chọn dạng LE/BE theo hợp đồng.
- `StandardCharsets.ISO_8859_1`, `US_ASCII`: chỉ dùng khi định dạng yêu cầu; **không** thể biểu diễn đầy đủ mọi ký tự tiếng Việt.

Đổi charset **không** giải quyết việc String chứa LF không mong muốn, indentation thừa hoặc tổ hợp Unicode chưa thống nhất. Và ngược lại, chuẩn hóa whitespace **không** giúp một charset hạn chế có thể biểu diễn những ký tự nằm ngoài tập mã của nó.

## 5. Files.writeString mặc định đã dùng UTF-8 từ Java 11

Hai lệnh sau tương đương về charset khi không có cấu hình mở tệp đặc biệt:

~~~java
Files.writeString(path, content);

Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

`Files.writeString(Path, CharSequence, OpenOption...)` **quy định UTF-8 mặc định trong chính API này** từ khi ra đời ở Java 11. Điều này đúng cả khi chạy trên **Java 17** mà charset mặc định chung của hệ điều hành có thể là một code page khác.

Tuy nhiên, không nên suy ra rằng **mọi API Java 17 đều mặc định UTF-8**.

### Khác biệt lịch sử cần hiểu chính xác

- Trước **Java 18**, các API **dựa vào charset mặc định của runtime** có thể khác nhau theo hệ điều hành, locale hoặc cấu hình. Ví dụ một số constructor của `FileWriter`, `InputStreamReader` hoặc `String.getBytes()` không tham số.
- Từ **Java 18**, **JEP 400** quy định UTF-8 làm charset mặc định cho các API Java SE phụ thuộc default charset, trừ khi môi trường cấu hình chế độ tương thích/ngoại lệ được tài liệu cho phép.
- **`Files.writeString` là trường hợp cần phân biệt:** đã sử dụng UTF-8 trước Java 18, độc lập với thay đổi JEP 400.

Dù chạy JDK 17, 21 hay mới hơn, với dữ liệu trao đổi nên viết **charset tường minh** để người đọc code và hệ thống kiểm thử hiểu chính xác hợp đồng:

~~~java
Files.writeString(path, content, StandardCharsets.UTF_8);
String readBack = Files.readString(path, StandardCharsets.UTF_8);
~~~

**Đừng phụ thuộc vào `Charset.defaultCharset()`** cho tệp có yêu cầu cố định, ngay cả khi máy hiện tại đang trả UTF-8.

## 6. Chương trình Java 17+ hoàn chỉnh: cùng nội dung, khác encoding

Ví dụ dưới đây kiểm tra **ba ý tưởng độc lập**:

1. Một text block và một chuỗi bên ngoài sau chuẩn hóa có nội dung bằng nhau.
2. Cùng String được ghi bằng UTF-8 và UTF-16LE cho byte-size khác nhau, nhưng đọc đúng charset vẫn khôi phục cùng nội dung.
3. Chuẩn hóa Unicode NFC là **một phép biến đổi ký tự khác nữa**, không tự xảy ra khi ghi UTF-8.

Lưu tệp **`TextNormalizationVsCharsetDemo.java`**, mã hóa nguồn UTF-8:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.Normalizer;
import java.util.Arrays;

public class TextNormalizationVsCharsetDemo {

    static String normalizeLf(String text) {
        return text.replace("\r\n", "\n")
                   .replace('\r', '\n');
    }

    public static void main(String[] args) throws IOException {
        String fromTextBlock = """
                Alpha
                  Beta
                """;

        // Dữ liệu đầu vào có CRLF và bốn dấu cách thụt lề.
        String external = "    Alpha\r\n      Beta";

        // Quy tắc của ví dụ:
        // CRLF/CR -> LF; bỏ lề chung; thêm đúng một LF cuối.
        String normalized = normalizeLf(external)
                .stripIndent() + "\n";

        // Chuỗi có chữ có dấu để minh họa kích thước UTF-8.
        String payload = normalized + "Caf\u00E9\n";

        System.out.println(
                "same-text=" + fromTextBlock.equals(normalized)
        );
        System.out.println(
                "source-has-cr=" + external.contains("\r")
        );
        System.out.println(
                "normalized-has-cr=" + normalized.contains("\r")
        );
        System.out.println(
                "normalized-final-lf=" + normalized.endsWith("\n")
        );
        System.out.println("payload-chars=" + payload.length());

        Path utf8File = Files.createTempFile("lesson-utf8-", ".txt");
        Path utf16File = Files.createTempFile("lesson-utf16-", ".txt");

        try {
            Files.writeString(
                    utf8File, payload, StandardCharsets.UTF_8
            );
            Files.writeString(
                    utf16File, payload, StandardCharsets.UTF_16LE
            );

            byte[] utf8Bytes = Files.readAllBytes(utf8File);
            byte[] utf16Bytes = Files.readAllBytes(utf16File);

            System.out.println("utf8-bytes=" + utf8Bytes.length);
            System.out.println("utf16le-bytes=" + utf16Bytes.length);
            System.out.println(
                    "same-file-bytes="
                        + Arrays.equals(utf8Bytes, utf16Bytes)
            );
            System.out.println(
                    "utf8-roundtrip="
                        + payload.equals(Files.readString(
                                utf8File, StandardCharsets.UTF_8))
            );
            System.out.println(
                    "utf16le-roundtrip="
                        + payload.equals(Files.readString(
                                utf16File, StandardCharsets.UTF_16LE))
            );
        } finally {
            Files.deleteIfExists(utf8File);
            Files.deleteIfExists(utf16File);
        }

        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println(
                "unicode-raw-equal=" + composed.equals(decomposed)
        );
        System.out.println(
                "unicode-utf8-bytes-equal="
                    + Arrays.equals(
                            composed.getBytes(StandardCharsets.UTF_8),
                            decomposed.getBytes(StandardCharsets.UTF_8))
        );
        System.out.println(
                "unicode-nfc-equal="
                    + composed.equals(Normalizer.normalize(
                            decomposed, Normalizer.Form.NFC))
        );
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 TextNormalizationVsCharsetDemo.java
java TextNormalizationVsCharsetDemo
~~~

**Kết quả chuẩn, không phụ thuộc đường dẫn tạm do hệ điều hành tạo:**

~~~text
same-text=true
source-has-cr=true
normalized-has-cr=false
normalized-final-lf=true
payload-chars=18
utf8-bytes=19
utf16le-bytes=36
same-file-bytes=false
utf8-roundtrip=true
utf16le-roundtrip=true
unicode-raw-equal=false
unicode-utf8-bytes-equal=false
unicode-nfc-equal=true
~~~

**Giải thích quan trọng:**

- `fromTextBlock` là `"Alpha\n  Beta\n"`, sau khi xử lý indentation của text block và giữ LF cuối. `external` chứa `"    Alpha\r\n      Beta"` (không có LF cuối). Hàm `normalizeLf`, `stripIndent()` và việc thêm một LF cuối theo **chính sách của ví dụ** tạo ra đúng String giống text block.
- `payload` là `"Alpha\n  Beta\nCafé\n"`. Nó có **18 code units UTF-16**: 13 cho `"Alpha\n  Beta\n"`, thêm 5 cho `"Café\n"`. Không có ký tự bổ sung nào nằm ngoài Basic Multilingual Plane trong payload này.
- UTF-8 cần **19 byte**: các ký tự ASCII và LF mỗi ký tự một byte; `é` (U+00E9) cần hai byte. UTF-16LE cần **36 byte** cho 18 code units, hai byte mỗi code unit. `UTF_16LE` không tự thêm BOM.
- Hai tệp **khác byte** nhưng đọc lại bằng charset **đúng với tệp** sẽ cho cùng String. Điều đó chứng minh encoder/decoder không làm nhiệm vụ chuẩn hóa whitespace.
- `"\u00E9"` và `"e\u0301"` thường hiển thị cùng chữ `é` nhưng là hai dãy ký tự Unicode khác nhau. Ghi cả hai bằng UTF-8 **không** tự làm chúng giống nhau. `Normalizer.normalize(..., NFC)` mới là bước chuẩn hóa Unicode có chủ đích.
- Hai tệp được tạo trong thư mục tạm để minh họa và được xóa trong `finally`. Không nên dùng ví dụ này để viết đè tệp người dùng ngoài môi trường thực hành.

**Ghi chú riêng về `javac -encoding UTF-8`:** tham số này chỉ yêu cầu trình biên dịch **đọc tệp mã nguồn `.java` bằng UTF-8**. Nó **không** chọn charset của các tệp `.txt` do chương trình tạo ra; thao tác đó nằm ở `Files.writeString(..., Charset)`.

## 7. Ba quyết định không nên trộn trong một biến

Một thiết kế rõ ràng tách các bước:

~~~java
String original = loadIncomingText();

String normalized = normalizeLf(original);

Files.writeString(
        targetPath,
        normalized,
        StandardCharsets.UTF_8
);
~~~

Đây là **mảnh mã minh họa**, cần có định nghĩa `loadIncomingText()` và biến `targetPath` trong chương trình thực.

Hãy đọc đoạn code theo thứ tự:

1. **Nhận dữ liệu:** String đầu vào có thể còn CRLF, khoảng trắng và Unicode ở dạng kết hợp khác nhau.
2. **Áp dụng chính sách chuẩn hóa:** trong ví dụ chỉ thống nhất line endings sang LF; các phép biến đổi khác phải có yêu cầu cụ thể.
3. **Chọn charset ghi tệp:** chọn UTF-8 để chuyển **String đã chốt** thành byte.
4. **Ghi tệp:** lựa chọn hành vi tạo/truncate/append tệp là vấn đề I/O riêng, không phải nội dung String hoặc charset.

Nếu cần **bảo toàn tuyệt đối** nội dung đầu vào, không chuẩn hóa chỉ để “cho sạch”. Dùng chính String đầu vào và charset chính xác theo hợp đồng; nếu dữ liệu đầu vào vốn là **byte**, có thể cần giữ nguyên byte mà không đi qua String để tránh thay đổi ngoài ý muốn.

## 8. Phân biệt các API ghi tệp

| API | Charset/line ending | Trường hợp phù hợp |
| --- | --- | --- |
| `Files.writeString(path, text)` | UTF-8 theo đặc tả API; giữ line separators trong text, không thêm ký tự | Ghi toàn bộ String ngắn/vừa, chính xác nội dung |
| `Files.writeString(path, text, UTF_8)` | UTF-8 tường minh; giữ ký tự trong String | Nên ưu tiên cho hợp đồng rõ ràng |
| `Files.writeString(path, text, UTF_16LE)` | UTF-16LE, không tự đổi CRLF/LF | Hệ thống bên nhận yêu cầu UTF-16LE |
| `Files.newBufferedWriter(path, UTF_8)` + `writer.write(text)` | UTF-8, ghi đúng các ký tự bạn yêu cầu | Ghi theo dòng/stream, dữ liệu lớn hơn |
| `writer.newLine()` | Thêm **line separator phụ thuộc hệ thống** | Chỉ dùng nếu hợp đồng thật sự yêu cầu separator của host |
| `Files.write(path, lines, UTF_8)` | Ghi các dòng và thêm line separator theo cơ chế của API | Không phải lựa chọn đầu tiên khi cần bảo toàn chính xác line terminators ban đầu |
| `Files.write(path, bytes)` | Ghi byte đã chuẩn bị; không chọn charset | Khi đã tự mã hóa hoặc muốn giữ byte nguyên trạng |
| `new FileWriter(path)` trên JDK 17 | Có thể dùng charset mặc định hệ thống | Tránh nếu hợp đồng cần charset cố định; dùng overload có `Charset` hoặc API NIO |

Lưu ý: `Files.writeString` **không thêm newline cuối**. Nếu muốn LF cuối, nó phải có trong String. Nếu muốn CRLF cuối, String phải chứa `\r\n` hoặc bạn phải chuẩn hóa theo quy tắc thích hợp trước khi ghi.

Ví dụ buffer với LF cố định:

~~~java
try (var writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("first");
    writer.write("\n");
    writer.write("second");
    writer.write("\n");
}
~~~

Đây là mảnh mã nằm trong phương thức có xử lý/khai báo `IOException`; nó **không** phụ thuộc `System.lineSeparator()`. Nếu dùng `writer.newLine()`, line separator có thể thay đổi theo môi trường chạy.

## 9. UTF-8 không sửa được vấn đề mất dấu khi giải mã sai

Một tệp gồm các byte **đã được mã hóa bằng UTF-8** cần được đọc bằng UTF-8:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Nếu hệ thống khác ghi tệp bằng charset khác nhưng bạn cố đọc như UTF-8, có thể xảy ra lỗi giải mã hoặc ký tự hiển thị không đúng. Đổi `strip()`, `stripIndent()` hay `Normalizer.normalize()` trên một chuỗi **đã giải mã sai** thường không thể khôi phục dữ liệu gốc.

**Lỗi encoding cần xử lý ở ranh giới byte → ký tự**, tức là chọn đúng decoder/charset khi đọc tệp. **Lỗi whitespace cần xử lý ở ranh giới ký tự → ký tự**, sau khi đã có String hợp lệ.

Ví dụ tư duy:

~~~text
UTF-8 bytes -> decode với UTF-8 -> String đúng -> (tùy chọn) normalize -> write UTF-8
UTF-8 bytes -> decode sai       -> String hỏng -> stripIndent() không sửa encoding
~~~

Nói cách khác, trước khi “sửa lỗi tiếng Việt”, hãy kiểm tra **charset của tệp nguồn** và cách đọc. Không mặc định mọi tệp cũ đều là UTF-8, đặc biệt ở hệ thống tích hợp với phần mềm lâu đời.

### Charset không biểu diễn đủ ký tự

Một số charset như US-ASCII không thể biểu diễn đầy đủ Unicode. Đổi từ Unicode sang charset không hỗ trợ có thể thất bại hoặc dùng ký tự thay thế, tùy API và chính sách encoder. Với `Files.writeString(path, text, charset)`, việc ký tự không được biểu diễn hợp lệ có thể dẫn đến `IOException`. Không nên coi việc ghi “thành công không exception” qua mọi API là bằng chứng dữ liệu đã được bảo toàn; nếu quan trọng, **đọc lại bằng đúng charset và so sánh String**.

Nếu cần chủ động điều khiển lỗi mã hóa, dùng `CharsetEncoder` với `CodingErrorAction.REPORT` thay vì tùy tiện thay các ký tự không hỗ trợ bằng dấu hỏi.

## 10. Unicode normalization khác cả whitespace lẫn charset

Có **ba thao tác** rất dễ bị gộp nhầm dưới chữ “chuẩn hóa”:

1. **Whitespace normalization:** đổi `\r\n` thành `\n`, bỏ lề thụt, quyết định LF cuối.
2. **Unicode normalization:** thống nhất những cách biểu diễn Unicode tương đương như ký tự ghép sẵn và ký tự cơ sở + dấu kết hợp, thường theo NFC hoặc NFD.
3. **Encoding:** biến các code point/code units trong String thành byte theo UTF-8, UTF-16LE…

Ví dụ:

~~~java
import java.text.Normalizer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String precomposed = "\u00E9";       // é, một code point.
String decomposed = "e\u0301";       // e + combining acute.

System.out.println(precomposed.equals(decomposed)); // false

String canonical = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC
);
System.out.println(precomposed.equals(canonical));  // true

System.out.println(
        Arrays.equals(
                precomposed.getBytes(StandardCharsets.UTF_8),
                decomposed.getBytes(StandardCharsets.UTF_8))
); // false
~~~

Đây là ví dụ trong thân phương thức; chương trình đầy đủ ở mục 6 đã triển khai và in kết quả tương đương.

**Ghi UTF-8 không tự chuẩn hóa Unicode NFC.** Cả hai chuỗi đều hợp lệ trong UTF-8, nhưng byte sẽ khác nhau. Nếu hệ thống yêu cầu so khớp tên, chuẩn hóa khóa hoặc tạo định danh theo một dạng Unicode, phải chọn **chính sách riêng**, đồng thời cân nhắc bảo mật, ngôn ngữ và khả năng tương thích dữ liệu cũ.

Đặc biệt với **chữ ký số, hash hoặc so sánh tệp byte-for-byte**, phải xác định rõ có chuẩn hóa Unicode/whitespace trước khi ký hay không; mỗi bên phải áp dụng cùng chính sách. Không nên sửa chuỗi sau khi đã tính hash rồi mong kết quả không thay đổi.

## 11. BOM, đuôi tệp và ký tự cuối dòng

### 11.1. BOM không phải là whitespace normalization

Một số định dạng UTF-16 sử dụng BOM để biểu thị thứ tự byte, trong khi UTF-8 thường không cần BOM. `StandardCharsets.UTF_8` được dùng với `Files.writeString` không cần tự thêm BOM để tệp hợp lệ. `UTF_16LE` là charset chỉ rõ little-endian và không tự thêm BOM; với `UTF_16`, hành vi BOM thuộc quy tắc charset đó.

**Đừng thêm hoặc xóa BOM như một bước “trim whitespace”**. BOM là vấn đề định dạng byte/encoding và tương thích bên nhận, không phải dấu cách đầu dòng.

### 11.2. Tên file không chọn charset

Tệp tên `report.txt`, `output.csv` hoặc `config.json` không tự mang thông tin bắt buộc mọi trình đọc phải sử dụng UTF-8. Format, giao thức, metadata hoặc hợp đồng giữa các hệ thống mới quyết định điều đó. Một tệp mang đuôi `.txt` có thể chứa UTF-8 hoặc UTF-16LE.

### 11.3. Dấu xuống dòng vẫn là ký tự trong String

`Files.writeString(path, "A\n", UTF_8)` ghi một byte `41` và một byte `0A`. Nếu thay bằng `"A\r\n"`, nội dung UTF-8 là `41 0D 0A`. Bảng mã không chuyển `0D 0A` thành `0A`.

Việc xuất file theo quy định CRLF nên là bước **chuẩn hóa line ending có chủ đích** trước khi gọi encoder. Ví dụ, nếu String đã dùng LF thống nhất:

~~~java
String withCrLf = normalized.replace("\n", "\r\n");
Files.writeString(path, withCrLf, StandardCharsets.UTF_8);
~~~

Đây là mảnh mã; `normalized` phải **thật sự chỉ có LF** để không vô tình sinh `\r\r\n` khi dữ liệu ban đầu đã chứa CRLF. Có thể cần xử lý chính sách đặc thù cho các hệ thống yêu cầu line endings cố định.

## 12. Ghi tệp an toàn: các điểm ngoài charset và whitespace

- **Không ghi đè vô ý:** `Files.writeString` không có options sẽ tạo/truncate tệp như quy tắc API. Khi cần từ chối ghi đè, chọn option phù hợp như `StandardOpenOption.CREATE_NEW`. Đây là quyết định về **I/O**, không phải encoding.
- **Không giả định thao tác ghi là atomic:** nếu ghi vào tệp quan trọng, cân nhắc tạo tệp tạm, ghi hoàn tất, rồi đổi tên/move theo khả năng của file system và quy tắc ứng dụng; không suy rằng `Files.writeString` tự đảm bảo transaction.
- **Dữ liệu lớn:** với nội dung lớn, dùng `BufferedWriter` hoặc xử lý stream thay vì giữ toàn bộ tệp trong RAM; charset vẫn phải xác định rõ.
- **Ghi rồi đọc lại:** so sánh String bằng đúng charset (kiểm tra **ký tự**) và/hoặc so sánh byte/hash (kiểm tra **byte**). Hai phép thử phục vụ hai mục đích khác nhau.
- **Thông báo lỗi:** `IOException` có thể phát sinh vì không có quyền truy cập, hết dung lượng, đường dẫn sai hoặc lỗi encoding; không nên quy tất cả thành lỗi “Unicode”.
- **Console không phải tệp:** encoding của `System.out`/terminal có chính sách riêng. Nếu console hiển thị tiếng Việt sai, điều đó chưa đủ chứng minh tệp UTF-8 tạo ra có byte sai; hãy kiểm tra byte hoặc đọc lại tệp bằng charset đúng.
- **Nguồn mã Java không phải tệp đầu ra:** `javac -encoding UTF-8` điều khiển cách compiler đọc source; nó không thay thế `StandardCharsets.UTF_8` ở API ghi tệp.

## 13. Quy trình quyết định nên chuẩn hóa gì trước khi ghi tệp

**Bước 1 — Xác định hợp đồng đầu ra.** Bên nhận yêu cầu UTF-8 hay encoding nào? LF, CRLF hay giữ nguyên? Có cần LF cuối, số dấu cách cố định, NFC hay bảo toàn byte gốc không?

**Bước 2 — Kiểm tra nguồn dữ liệu.** Nếu nhận từ byte/tệp khác, phải **giải mã bằng đúng charset nguồn** trước. Nếu nhận từ Java text block, cần biết compiler đã chuẩn hóa line terminators và incidental indentation.

**Bước 3 — Chỉ thực hiện những biến đổi ký tự cần thiết.** Ví dụ:
- Quy định LF: `replace("\r\n","\n").replace('\r','\n')`.
- Quy định indentation: `stripIndent()` hoặc thuật toán domain-specific đã được kiểm thử.
- Quy định NFC: `Normalizer.normalize(text, Normalizer.Form.NFC)`.
- Quy định trailing newline: kiểm tra `endsWith("\n")` và áp dụng chính sách chính xác, không `strip()` vô điều kiện.

**Bước 4 — Chọn charset bằng API I/O.** Ưu tiên `Files.writeString(path, text, StandardCharsets.UTF_8)` cho tệp text hiện đại; chỉ dùng encoding khác khi có yêu cầu rõ.

**Bước 5 — Kiểm thử cả hai cấp:** giá trị String sau chuẩn hóa có đúng không? Sau khi ghi và đọc bằng charset đã chọn, String có trở lại đúng không? Nếu tệp phải byte-for-byte tương thích, bytes có đúng theo golden fixture không?

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Ghi UTF-8 sẽ tự đổi CRLF thành LF.” | Không. Đó là biến đổi nội dung String riêng. |
| “Đã stripIndent thì tệp chắc chắn UTF-8.” | Không. `stripIndent` chỉ xử lý ký tự, không chọn charset. |
| “Text block lưu trực tiếp UTF-8 xuống tệp.” | Không. Text block tạo String; API I/O mới mã hóa và ghi. |
| “Mọi API ở Java 17 đều mặc định UTF-8.” | Không. `Files.writeString` mặc định UTF-8 từ Java 11; các API phụ thuộc charset hệ thống ở Java 17 có thể khác. |
| “Từ Java 18 mọi vấn đề encoding đã hết.” | Không. Dữ liệu ngoài có thể dùng charset khác; default charset có ngoại lệ cấu hình và giao thức cần hợp đồng rõ. |
| “Có thể dùng strip để xóa khoảng trắng mà không mất dữ liệu.” | `strip` có thể xóa newline hợp lệ ở đầu/cuối. |
| “Chỉ cần FileWriter(path) sẽ luôn portable.” | Trên JDK 17 có thể phụ thuộc default charset; dùng API/overload khai báo Charset. |
| “Một glyph giống nhau chắc chắn là cùng String.” | Unicode có thể dùng nhiều chuỗi code point tương đương; muốn so sánh theo NFC phải normalize riêng. |
| “Tên .txt hoặc .csv quyết định encoding.” | Không. Cần hợp đồng/metadata và charset tương ứng. |
| “Ký tự bị sai chỉ cần đổi encoding lúc ghi.” | Nếu đã decode sai khi đọc, dữ liệu String có thể đã hỏng; phải sửa ở ranh giới đọc byte. |
| “Files.writeString tự thêm newline cuối.” | API ghi đúng các ký tự cung cấp, không tự thêm newline. |
| “BOM là dấu cách đầu tệp và nên trim.” | BOM là quy ước encoding/byte order; không xử lý bằng strip tùy tiện. |
| “Hiển thị ở console đúng nghĩa là bytes trong file đúng.” | Console và tệp có thể dùng quy tắc charset khác; hãy kiểm tra chính tệp. |

## 15. Checklist khi review mã Java xử lý văn bản

1. `String` đã có **nội dung** đúng chưa, bao gồm dấu cách, tab, dòng trống, CR/LF và dòng mới cuối?
2. Nếu dùng text block, bạn đã hiểu ba bước **normalize line terminators → strip indentation → translate escapes** chưa?
3. Có đang gọi `strip()` hoặc `stripIndent()` với dữ liệu mà khoảng trắng mang ý nghĩa không?
4. Nếu dữ liệu đi vào từ byte, bước đọc có khai báo đúng charset nguồn không?
5. Khi ghi, bạn đã chọn `StandardCharsets.UTF_8` hoặc charset mà bên nhận thực sự yêu cầu chưa?
6. Có nhầm `Files.writeString` (UTF-8 mặc định từ Java 11) với các API default charset trước Java 18 không?
7. Có cần kiểm soát `LF/CRLF`, `BOM` và Unicode normalization NFC riêng không?
8. Tệp có thể bị truncate/ghi đè vô ý không? Có cần `CREATE_NEW` hay phương án ghi an toàn?
9. Kiểm thử có phân biệt **character equality** và **byte equality** không?
10. Khi có tiếng Việt, test có thực sự chứa ký tự có dấu và xác thực readback bằng charset đúng không?

## 16. Bài tập thực hành

**Bài 1 — Đổi nội dung, không đổi charset.** Cho `String text = "A\r\nB\r\n";`. Chuẩn hóa về `"A\nB\n"` rồi ghi cả bản gốc và bản chuẩn hóa bằng UTF-8. Dự đoán: hai tệp **khác byte** dù charset giống nhau. Đếm byte của `"A\r\nB\r\n"` là **6** và `"A\nB\n"` là **4**.

**Bài 2 — Đổi charset, giữ nguyên String.** Ghi `"A\n"` vào hai tệp bằng `UTF_8` và `UTF_16LE`. Đáp án: UTF-8 có **2 byte** (`41 0A`), UTF-16LE có **4 byte** (`41 00 0A 00`). Đọc lại bằng đúng charset đều cho `"A\n"`.

**Bài 3 — Text block và dấu đóng.** Viết hai text blocks cùng nội dung `"one"`: bản có closing delimiter dòng riêng và bản có delimiter ngay sau `one`. Dùng `endsWith("\n")` để kiểm tra. Kỳ vọng: bản đóng riêng thường có LF cuối; bản inline không có LF cuối, nếu không dùng escape khác.

**Bài 4 — Unicode normalization.** So sánh `"\u00E9"` với `"e\u0301"` bằng `equals` và bytes UTF-8. Sau đó chuyển cả hai về NFC bằng `Normalizer` và thử lại. Giải thích vì sao **chỉ chọn UTF-8** không làm các String bằng nhau.

**Bài 5 — Xác định nguồn lỗi.** Một tệp tiếng Việt được viết bằng `Files.writeString(path, text, UTF_8)` nhưng ứng dụng bên nhận đọc bằng một charset cũ. Người dùng thấy ký tự không đúng. Cần sửa **decoder ở phía đọc** hoặc đổi hợp đồng charset giữa hai hệ thống, không phải tùy ý gọi `stripIndent`.

**Bài 6 — Ghi tệp không có LF cuối.** Cho `String s = "A\nB\n";` và hợp đồng yêu cầu đúng `"A\nB"`. Hãy bỏ **đúng một LF cuối** khi hiện diện, thay vì dùng `strip()` (có thể bỏ nhiều whitespace hợp lệ khác). Ví dụ:

~~~java
String result = s.endsWith("\n")
        ? s.substring(0, s.length() - 1)
        : s;
~~~

Đáp án: `"A\nB"`. Nếu dữ liệu có CRLF cuối hoặc nhiều LF, phải làm rõ chính sách trước khi triển khai.

## 17. Tài liệu chính thức

- [Oracle — Programmer's Guide to Text Blocks (Java 17)](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): thứ tự chuẩn hóa line terminators, bỏ incidental whitespace, escape và dòng mới cuối.
- [Oracle — String API (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `stripIndent()`, `strip()`, `indent()`, `lines()`.
- [Oracle — Files API (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `writeString/readString`, charset UTF-8 mặc định của API và việc giữ nguyên line separators trong String.
- [Oracle — StandardCharsets (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset chuẩn, đặc biệt UTF-8 và UTF-16LE.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text block là tính năng chính thức từ Java 15.
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định của các Java SE API phụ thuộc mặc định từ Java 18, phân biệt với `Files.writeString`.
- [Oracle — Normalizer API (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): chuẩn hóa Unicode NFC/NFD.
