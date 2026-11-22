# Đọc ghi văn bản với bảng mã đã chỉ rõ bằng `Files` trong Java

## 1. Vì sao phải nêu rõ charset?

Một tệp văn bản thực chất lưu **các byte**; nội dung khi chương trình đọc thành `String` phụ thuộc vào **bảng mã ký tự (charset)**. Chẳng hạn:

- UTF-8 biểu diễn ký tự ASCII bằng một byte, ký tự tiếng Việt thường bằng nhiều byte và emoji bằng nhiều byte.
- ISO-8859-1 biểu diễn được `é` (U+00E9) bằng một byte `E9`, nhưng không biểu diễn được emoji.
- Cùng các byte đầu vào, nếu chọn charset giải mã không phù hợp thì có thể xuất hiện ký tự sai, ký tự thay thế hoặc ngoại lệ.

Vì vậy, chương trình nên **xác định charset theo định dạng file/giao thức**, không “đoán đại” hoặc lệ thuộc cài đặt máy. API chính được học:

~~~java
Files.writeString(path, content, StandardCharsets.UTF_8);
String contentAgain = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa, cần import `java.nio.file.Files`, `java.nio.file.Path` và `java.nio.charset.StandardCharsets`, đồng thời đặt trong method xử lý `IOException`.

Bài nằm trong chủ đề **`Files`** (Java NIO.2) và tập trung vào **đọc, ghi văn bản với charset chỉ định**: `readString`, `writeString`, `newBufferedReader`, `newBufferedWriter`, `readAllLines` và `lines`.

**Sau bài học, bạn có thể:**

1. Chọn `Charset` rõ ràng khi biến đổi byte ↔ ký tự, kể cả UTF-8 và một charset hẹp hơn.
2. Dùng đúng các phương thức `Files` theo kích thước file và nhu cầu giữ nguyên dấu xuống dòng.
3. Phân biệt **giải mã sai charset**, **byte malformed** và **ký tự không thể mã hóa**.
4. Chọn `StandardOpenOption` để tạo, ghi đè hay nối thêm văn bản mà không làm mất dữ liệu ngoài ý muốn.
5. Quản lý `BufferedReader`, `BufferedWriter` và `Stream<String>` bằng `try-with-resources`.
6. Hiểu BOM, newline theo nền tảng, tính toàn vẹn dữ liệu và các lỗi thường gặp.

**Lưu ý phiên bản:** `Files.newBufferedReader` / `newBufferedWriter` với charset đã có từ Java 7; `Files.readString` / `writeString` được bổ sung từ Java 11. Chúng **vẫn là API chuẩn đang áp dụng** trên Java hiện đại. Ví dụ chạy trên **Java 21**, không khuyến nghị kỹ thuật đã lỗi thời hay API legacy.

## 2. `Charset` và `StandardCharsets`

Một `Charset` định nghĩa quy tắc biến đổi giữa **byte sequence** và **Unicode character sequence**. Với các charset chuẩn thường gặp, dùng hằng số trong `java.nio.charset.StandardCharsets` thay vì nhập tên chuỗi bằng tay:

| Hằng số | Đặc điểm | Tình huống |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode, đa số văn bản/giao thức hiện đại, chiều dài byte biến đổi | Lựa chọn thường ưu tiên cho file văn bản mới |
| `StandardCharsets.US_ASCII` | Chỉ mã hóa được các ký tự ASCII cơ bản | Khi đặc tả file thật sự yêu cầu ASCII |
| `StandardCharsets.ISO_8859_1` | Charset một byte, biểu diễn nhiều ký tự Tây Âu như `é`, nhưng không có emoji/đa số tiếng Việt | Đọc/ghi dữ liệu tương thích một giao thức quy định rõ ISO-8859-1 |
| `StandardCharsets.UTF_16` | UTF-16 với quy tắc BOM/byte order theo charset này | Chỉ khi định dạng yêu cầu |
| `StandardCharsets.UTF_16LE` / `UTF_16BE` | UTF-16 với thứ tự byte chỉ định | Khi nguồn dữ liệu quy định rõ endian |

**Không có charset duy nhất đúng cho mọi file cũ.** Nếu file đến từ hệ thống ngoài, thông tin charset phải được lấy từ **hợp đồng hoặc metadata đáng tin** (ví dụ định dạng file, HTTP `Content-Type` nếu áp dụng phù hợp). Đừng tự đổi mọi byte thành UTF-8 mà không biết nguồn được mã hóa như thế nào.

### 2.1. Đừng nhầm “charset mặc định của hệ thống” với overload của `Files`

Trong Java 21, các overload sau **dùng UTF-8 theo tài liệu API**, không phải tự lấy `Charset.defaultCharset()`:

~~~java
Files.readString(path);                 // UTF-8
Files.writeString(path, content);       // UTF-8
Files.newBufferedReader(path);          // UTF-8
Files.newBufferedWriter(path);          // UTF-8
Files.readAllLines(path);               // UTF-8
Files.lines(path);                      // UTF-8
~~~

Đây là các lệnh minh họa; `path` và `content` cần được khai báo. **Việc không truyền charset** ở các overload cụ thể này vẫn có nghĩa là UTF-8, không phải “phụ thuộc Windows/Linux”. Tuy nhiên, việc **ghi tường minh `StandardCharsets.UTF_8`** thường giúp code review nhìn thấy hợp đồng của file, và đặc biệt quan trọng khi dữ liệu không phải UTF-8.

### 2.2. Ghi và đọc phải đồng thuận về charset

Nếu file đã được ghi bằng `ISO_8859_1`, hãy đọc bằng `ISO_8859_1` hoặc chuyển mã có kiểm soát. Trường hợp `"Café"`:

~~~java
Files.writeString(path, "Café", StandardCharsets.ISO_8859_1);
String decoded = Files.readString(path, StandardCharsets.ISO_8859_1);
~~~

Đây là đoạn minh họa. Kết quả `decoded` bằng `"Café"`. Nếu đọc các byte của chữ `é` này bằng UTF-8, byte `E9` đứng đơn lẻ là byte không hợp lệ trong UTF-8; phương thức đọc có thể báo `MalformedInputException`. Không phải mọi trường hợp đọc sai charset đều tự phát hiện được: một số dữ liệu sai charset vẫn tạo ra text hợp lệ **nhưng sai nghĩa** (*mojibake*).

## 3. Đọc/ghi file nhỏ bằng `Files.readString` và `Files.writeString`

### 3.1. Ghi bằng charset đã chọn

~~~java
Path path = Path.of("notes.txt");
String text = "Xin chào, Java!";
Files.writeString(path, text, StandardCharsets.UTF_8);
~~~

Đây là đoạn minh họa trong method có thể ném `IOException`. `writeString` chuyển ký tự sang byte theo UTF-8 và ghi vào file.

**Khi không truyền `OpenOption`**, `Files.writeString(path, text, charset)` sử dụng hành vi tương đương `CREATE`, `TRUNCATE_EXISTING`, `WRITE`:

- Nếu file chưa tồn tại, tạo file rồi ghi.
- Nếu file đã tồn tại, **cắt về kích thước 0 trước khi ghi**.
- Không tự nối nội dung, không tự thêm newline và không tự tạo các thư mục cha còn thiếu.

Lệnh này **không phải một bản cập nhật nguyên tử**. Nếu bị lỗi I/O trong lúc ghi, không có bảo đảm file cũ được bảo toàn. Với dữ liệu quan trọng, nên thiết kế quy trình ghi file tạm/đồng bộ/đổi tên theo hỗ trợ của filesystem, thay vì giả định `writeString` là giao dịch.

### 3.2. Đọc bằng đúng charset

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

`readString` trả toàn bộ nội dung thành một `String`. Nó giữ **các ký tự xuống dòng** có trong file (như LF hoặc CRLF), không tự chia thành từng dòng hay chuẩn hóa tất cả line endings.

Theo Javadoc, phương thức này dành cho file có kích thước phù hợp để đưa hết vào bộ nhớ. Đối với log rất lớn, file nhiều gigabyte hoặc dữ liệu streaming, nên dùng `newBufferedReader` hoặc `Files.lines`, không dồn toàn bộ vào `String`.

### 3.3. Vì sao `Files.readString` và `writeString` không có `close()` ở mã gọi?

Hai phương thức trọn gói quản lý việc mở/đóng file bên trong. Không có `Reader` hay `Writer` nào được trả về để bạn tự đóng. Ngược lại, phương thức `newBufferedReader` / `newBufferedWriter` trả tài nguyên đang mở và bạn phải đóng.

Điểm này khác với xử lý lỗi: dù tự đóng tài nguyên, `readString` và `writeString` **vẫn có thể ném `IOException`**, nên caller phải catch hoặc khai báo `throws IOException`.

## 4. Một ví dụ Java 21 hoàn chỉnh, kiểm thử cả UTF-8 và ISO-8859-1

Chương trình sau:

- Ghi và đọc tiếng Việt/emoji bằng UTF-8 rồi so giá trị.
- So sánh overload UTF-8 mặc định với overload có `Charset`.
- Kiểm tra UTF-8 sinh bao nhiêu byte và có tự thêm BOM không.
- Ghi `"Café"` bằng ISO-8859-1 và kiểm tra byte thực tế `43 61 66 E9`.
- Cho thấy lỗi **đọc sai charset** và **ghi ký tự không biểu diễn được**.
- Dùng `BufferedWriter` để ghi và append từng dòng, `BufferedReader` để đọc dòng đầu, `readAllLines` và `Files.lines` để đọc nhiều dòng.
- Cho thấy BOM UTF-8 đầu file được đọc ra như ký tự `U+FEFF`.
- Dọn dẹp file/thư mục tạm chính nó tạo, không đụng đến file có sẵn của người học.

Tạo file `src/main/java/demo/ExplicitCharsetFilesExample.java`:

~~~java
package demo;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;
import java.util.List;
import java.util.stream.Stream;

public final class ExplicitCharsetFilesExample {
    private ExplicitCharsetFilesExample() {}

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("charset-files-");
        Path utf8 = folder.resolve("utf8.txt");
        Path latin1 = folder.resolve("latin1.txt");
        Path lines = folder.resolve("lines.txt");
        Path rejected = folder.resolve("rejected.txt");
        Path bom = folder.resolve("bom.txt");

        try {
            String message = "Xin chào Java 👋\nDòng thứ hai";
            Files.writeString(utf8, message, StandardCharsets.UTF_8);
            System.out.println("utf8-roundtrip="
                    + message.equals(Files.readString(utf8, StandardCharsets.UTF_8)));
            System.out.println("utf8-no-charset="
                    + message.equals(Files.readString(utf8)));
            System.out.println("utf8-byte-count=" + Files.size(utf8));
            byte[] encoded = Files.readAllBytes(utf8);
            boolean hasBom = encoded.length >= 3
                    && (encoded[0] & 0xFF) == 0xEF
                    && (encoded[1] & 0xFF) == 0xBB
                    && (encoded[2] & 0xFF) == 0xBF;
            System.out.println("utf8-written-bom=" + hasBom);

            Files.writeString(latin1, "Café", StandardCharsets.ISO_8859_1);
            System.out.println("latin1-roundtrip="
                    + "Café".equals(Files.readString(latin1, StandardCharsets.ISO_8859_1)));
            System.out.println("latin1-hex=" + HexFormat.ofDelimiter(" ")
                    .withUpperCase().formatHex(Files.readAllBytes(latin1)));
            try {
                Files.readString(latin1, StandardCharsets.UTF_8);
            } catch (MalformedInputException ex) {
                System.out.println("latin1-as-utf8=MalformedInputException");
            }

            try {
                Files.writeString(rejected, "👋", StandardCharsets.ISO_8859_1);
            } catch (UnmappableCharacterException ex) {
                System.out.println("latin1-emoji=UnmappableCharacterException");
            }

            try (BufferedWriter writer = Files.newBufferedWriter(lines,
                    StandardCharsets.UTF_8)) {
                writer.write("Một");
                writer.newLine();
                writer.write("Hai");
            }
            try (BufferedWriter writer = Files.newBufferedWriter(lines,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.APPEND)) {
                writer.newLine();
                writer.write("Ba");
            }
            try (BufferedReader reader = Files.newBufferedReader(lines,
                    StandardCharsets.UTF_8)) {
                System.out.println("first-line-match=" + "Một".equals(reader.readLine()));
            }
            System.out.println("all-lines-match="
                    + Files.readAllLines(lines, StandardCharsets.UTF_8)
                            .equals(List.of("Một", "Hai", "Ba")));
            try (Stream<String> stream = Files.lines(lines, StandardCharsets.UTF_8)) {
                System.out.println("line-count=" + stream.count());
            }

            Files.write(bom, new byte[] {(byte) 0xEF, (byte) 0xBB,
                    (byte) 0xBF, 0x41});
            String withBom = Files.readString(bom, StandardCharsets.UTF_8);
            System.out.println("bom-is-char="
                    + (withBom.length() == 2 && withBom.charAt(0) == (char) 0xFEFF));
        } finally {
            Files.deleteIfExists(utf8);
            Files.deleteIfExists(latin1);
            Files.deleteIfExists(lines);
            Files.deleteIfExists(rejected);
            Files.deleteIfExists(bom);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Từ thư mục chứa `src/`, dùng JDK hỗ trợ `--release 21`:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/ExplicitCharsetFilesExample.java
java -cp out demo.ExplicitCharsetFilesExample
~~~

**Stdout chính xác của chương trình** (đã kiểm thử trên JDK 21, mặc định filesystem trong môi trường thử nghiệm):

~~~text
utf8-roundtrip=true
utf8-no-charset=true
utf8-byte-count=35
utf8-written-bom=false
latin1-roundtrip=true
latin1-hex=43 61 66 E9
latin1-as-utf8=MalformedInputException
latin1-emoji=UnmappableCharacterException
first-line-match=true
all-lines-match=true
line-count=3
bom-is-char=true
~~~

### 4.1. Vì sao 35 byte, không phải số ký tự Java?

`message` có chữ tiếng Việt, emoji và `\n` giữa hai dòng. Mỗi ký tự Unicode có thể có số byte UTF-8 khác nhau. Bài thử đo bằng `Files.size(utf8)` và được **35 byte**; kích thước này không phải số `char` trong Java và cũng không nhất thiết là số Unicode code point.

Nếu cần biết số code point trong Java `String`:

~~~java
int count = message.codePointCount(0, message.length());
~~~

Đây là đoạn minh họa trong ngữ cảnh có `message`. Không nên dùng `String.length()` để đo số byte của file UTF-8 hoặc số ký tự hiển thị trên màn hình.

### 4.2. Vì sao `latin1-hex=43 61 66 E9`?

ISO-8859-1 mã hóa `C` = `43`, `a` = `61`, `f` = `66` và `é` = `E9`. UTF-8 sẽ có các byte khác cho `é`. Bởi vậy, dữ liệu byte **không mang sẵn nhãn charset**; cần biết charset đúng từ metadata/hợp đồng.

Khi `Files.readString(latin1, UTF_8)` gặp `E9` không phải UTF-8 hợp lệ trong ngữ cảnh này, nó ném `MalformedInputException`. Ngoại lệ xảy ra tại **giải mã**, không phải do file “không phải văn bản”.

### 4.3. Vì sao ghi emoji sang ISO-8859-1 bị từ chối?

Emoji `👋` là ký tự Unicode hợp lệ nhưng không có mã biểu diễn trong ISO-8859-1. `Files.writeString(..., ISO_8859_1)` dùng encoder nghiêm ngặt theo hợp đồng và gặp `UnmappableCharacterException`. Đây **không** phải một `MalformedInputException` vì bản thân emoji hợp lệ.

Ví dụ dùng file riêng `rejected.txt` cho phép minh họa lỗi mà không ghi đè dữ liệu đã mã hóa đúng trong `latin1.txt`. Một lần ghi thất bại có thể vẫn tạo hoặc làm thay đổi file đích; **không giả định lỗi ghi sẽ rollback dữ liệu**.

## 5. Đọc file lớn bằng `Files.newBufferedReader`

Đối với văn bản lớn, có thể đọc từng dòng mà không phải tạo một `String` chứa toàn bộ file:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        consume(line);
    }
}
~~~

Đoạn trên là **mẫu minh họa**, cần khai báo `Path path`, `consume(...)` và xử lý `IOException`; không phải chương trình độc lập.

- `newBufferedReader(path, charset)` mở file và decoder theo charset đã chọn.
- `readLine()` trả một dòng **không gồm ký tự kết thúc dòng**; trả `null` sau khi hết dữ liệu.
- Cú pháp `try-with-resources` bảo đảm reader được đóng khi rời block, kể cả xảy ra exception.
- `BufferedReader` hữu ích khi cần xử lý dòng theo thời gian, ví dụ validate từng record, lọc dữ liệu hoặc tổng hợp.
- Nếu format yêu cầu giữ nguyên vị trí newline (CRLF hay LF), **`readLine()` không giữ dấu kết thúc**, nên dùng `readString`/reader đọc char theo cách phù hợp.

**Nếu byte không hợp lệ theo charset**, `newBufferedReader` có thể ném `IOException` trong quá trình đọc chứ không nhất thiết tại lời gọi mở file. Bắt lỗi **bao quanh cả vòng lặp**, không chỉ lúc khởi tạo reader.

## 6. Ghi văn bản theo dòng bằng `Files.newBufferedWriter`

~~~java
try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Dòng thứ nhất");
    writer.newLine();
    writer.write("Dòng thứ hai");
}
~~~

Đây là mẫu minh họa. `BufferedWriter.newLine()` dùng separator theo môi trường chạy, trong khi `Files.writeString(path, "A\nB", charset)` sẽ ghi chính ký tự LF trong chuỗi đầu vào mà không tự đổi thành CRLF.

`BufferedWriter` có **buffer**, nên lỗi mã hóa hoặc I/O có thể xuất hiện khi `write`, `flush` hoặc `close`. `try-with-resources` là cách quản lý vòng đời tốt hơn việc quên đóng và hy vọng chương trình tự flush.

### 6.1. Ghi đè và nối thêm: ý nghĩa của `StandardOpenOption`

| Cách mở file | Hành vi thường dùng |
| --- | --- |
| Không truyền option cho `writeString` hoặc `newBufferedWriter` | `CREATE` + `TRUNCATE_EXISTING` + `WRITE`: tạo hoặc ghi đè file |
| `StandardOpenOption.CREATE_NEW` | Tạo mới, báo lỗi nếu file đã tồn tại; hữu ích khi không được phép ghi đè |
| `StandardOpenOption.CREATE` + `WRITE` + `APPEND` | Tạo nếu chưa có, hoặc **nối byte vào cuối** file đã có |
| `StandardOpenOption.WRITE` + `APPEND` | Nối vào cuối một file **đã tồn tại**; nếu file thiếu có thể lỗi |
| `StandardOpenOption.TRUNCATE_EXISTING` + `WRITE` | Nếu file tồn tại thì xóa nội dung cũ trước khi ghi, không tự tạo khi thiếu `CREATE` |

**Đừng trộn `APPEND` và `TRUNCATE_EXISTING` như một chế độ ghi hợp lý.** Nhiều provider từ chối tổ hợp không tương thích; nếu cần nối, đừng đồng thời bảo file xóa toàn bộ nội dung.

Ví dụ nối thêm bằng charset tường minh:

~~~java
Files.writeString(path, "\nThêm một dòng", StandardCharsets.UTF_8,
        StandardOpenOption.CREATE, StandardOpenOption.APPEND);
~~~

Đây là đoạn minh họa trong method xử lý `IOException`. Chương trình phần 4 dùng `newBufferedWriter` với `WRITE` + `APPEND` để thêm `"Ba"`. Nếu file đã có newline ở cuối, cần tránh ghi thêm hai newline liên tiếp theo yêu cầu định dạng.

**Đặc biệt quan trọng:** Append chỉ là cơ chế đặt vị trí ghi, không tự tạo “một record logic nguyên tử” khi nhiều writer hoặc nhiều luồng ghi đồng thời. Khi cần tránh các dòng bị trộn, phải có chính sách đồng bộ/transaction ở tầng ứng dụng hoặc thiết kế logging phù hợp.

## 7. `Files.readAllLines` và `Files.lines` với charset tường minh

Đây là hai phương thức khác nhau, dù cùng trả dữ liệu theo dòng.

### 7.1. `readAllLines` trả `List<String>`

~~~java
List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

- Đọc tất cả các dòng vào bộ nhớ.
- Dấu xuống dòng **không còn trong từng `String`** của list.
- Chỉ phù hợp khi dữ liệu đủ nhỏ.
- File được đóng bên trong phương thức, không cần `close()` trên kết quả `List`.
- Theo hợp đồng API, tính modifiable của list trả về **không được bảo đảm**; đừng xây logic phụ thuộc việc có thể `add` hoặc `remove` trên list đó.

### 7.2. `lines` tạo `Stream<String>` đọc lười

~~~java
try (Stream<String> stream =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long count = stream.filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
~~~

Đây là đoạn minh họa có `Path path` và import `java.util.stream.Stream`. Điểm quan trọng:

- `Files.lines` **chưa đọc sẵn toàn bộ file**; dữ liệu được đưa vào stream khi gọi operation.
- Stream vẫn giữ một file đang mở, do đó **phải đóng bằng try-with-resources**.
- Khi đọc diễn ra sau lúc tạo stream, lỗi I/O hoặc malformed/unmappable có thể được gói trong `UncheckedIOException` từ terminal/intermediate stream operation.
- Không sửa file đồng thời trong khi terminal operation đang duyệt vì hợp đồng không xác định rõ kết quả trong tình huống này.
- Dù stream xử lý từng dòng, nếu bạn gọi `stream.toList()` để thu toàn bộ nội dung thì vẫn tạo collection giữ nhiều dữ liệu trong bộ nhớ.

**Chọn API theo công việc, không chỉ theo cú pháp ngắn:**

| Nhu cầu | Chọn |
| --- | --- |
| Đọc cả file văn bản nhỏ thành một chuỗi, giữ newline | `Files.readString(path, charset)` |
| Ghi một chuỗi ngắn, toàn bộ nội dung file | `Files.writeString(path, text, charset)` |
| Đọc file lớn theo dòng và xử lý tuần tự | `Files.newBufferedReader(path, charset)` |
| Ghi file lớn, sinh nội dung tăng dần | `Files.newBufferedWriter(path, charset, ...)` |
| File nhỏ, muốn list dòng | `Files.readAllLines(path, charset)` |
| Muốn dùng stream pipeline có nguồn là file | `Files.lines(path, charset)` + try-with-resources |

## 8. Malformed bytes và unmappable characters

**Lỗi giải mã (decode)** và **lỗi mã hóa (encode)** có ý nghĩa khác nhau:

| Lỗi | Ví dụ | Exception khi dùng overload strict |
| --- | --- | --- |
| Byte sequence sai cấu trúc theo charset | Byte `E9` đơn lẻ dưới UTF-8 | `MalformedInputException` |
| Một chuỗi Unicode hợp lệ không thể biểu diễn ở charset đầu ra | Emoji `👋` dưới ISO-8859-1 | `UnmappableCharacterException` |
| File không có hoặc quyền truy cập/đĩa lỗi | `path` chưa tồn tại, không được đọc | `IOException` hoặc subtype theo tình huống |
| Chuỗi UTF-16 input không hợp lệ | Một *high surrogate* đứng đơn lẻ khi mã hóa UTF-8 | Thường là `MalformedInputException` |

`MalformedInputException` và `UnmappableCharacterException` đều kế thừa `CharacterCodingException`, rồi `IOException`. Bạn có thể catch ở tầng tổng quát bằng `IOException` cho code production; trong bài học, bắt subtype để chứng minh hai nguyên nhân khác nhau.

### 8.1. Không giả định Java luôn thay byte lỗi bằng ký tự `�`

Nhiều API tiện dụng chuyển byte thành `String` có thể dùng chính sách thay thế (*replacement*) khi gặp lỗi, nhưng **`Files.readString(path, charset)` được tài liệu xác định sẽ ném `IOException` khi gặp malformed/unmappable byte sequence**.

Tương tự, `Files.writeString(path, csq, charset)` báo lỗi nếu có ký tự không mã hóa được. Không âm thầm biến `👋` thành dấu `?` chỉ để hoàn thành ghi file.

Nếu nghiệp vụ thực sự cho phép thay thế hoặc bỏ qua lỗi, hãy dùng `CharsetDecoder` / `CharsetEncoder` với chính sách `CodingErrorAction.REPLACE` / `IGNORE`, hoặc một pipeline giải mã tùy chỉnh. **Đây là quyết định chấp nhận mất dữ liệu**, không phải một bước sửa lỗi vô hại.

### 8.2. Đọc sai charset không phải lúc nào cũng có exception

Giả sử các byte của một văn bản UTF-8 tình cờ cũng là một chuỗi hợp lệ trong một charset khác; decoder có thể tạo ra chuỗi kí tự **khác nghĩa** mà không ném lỗi. Do đó, chỉ việc “đọc được” không chứng minh đã chọn charset đúng. Muốn kiểm tra độ tin cậy, cần metadata/định dạng, kiểm tra cấu trúc, round-trip và các yêu cầu nghiệp vụ riêng.

Đối với dữ liệu ký số/hash, xác định rõ bạn đang ký **byte thô** hay text đã được giải mã/chuẩn hóa; việc chọn sai charset hoặc thay byte lỗi có thể làm hỏng tính toàn vẹn dữ liệu.

## 9. Byte Order Mark (BOM) và các dấu xuống dòng

### 9.1. UTF-8 BOM không được tự động thêm

Trong ví dụ phần 4, `Files.writeString(utf8, message, UTF_8)` tạo file **không có BOM UTF-8**: `utf8-written-bom=false`.

UTF-8 BOM nếu có là các byte `EF BB BF` ở **đầu file**. File từ công cụ khác có thể chứa BOM theo quy ước xuất dữ liệu, nên không được giả định mọi file UTF-8 đều không có BOM.

### 9.2. UTF-8 BOM khi đọc bằng `Files.readString`

Ví dụ ghi trực tiếp các byte `EF BB BF 41` rồi gọi `Files.readString(bom, UTF_8)`. Kết quả có **hai ký tự Unicode**: ký tự `U+FEFF` và chữ `A`, như stdout `bom-is-char=true`.

Nói cách khác, không nên ngầm giả định `Files.readString(..., UTF_8)` sẽ tự xóa BOM. Nếu format dữ liệu quy định bỏ một BOM đầu, hãy xử lý **có điều kiện ngay đầu chuỗi** hoặc dùng một reader/parser tuân thủ đặc tả đó. Không loại bỏ tất cả ký tự `U+FEFF` ở mọi vị trí nếu chưa biết hợp đồng dữ liệu.

### 9.3. Dấu xuống dòng có ý nghĩa

| API | Cách xử lý line terminator |
| --- | --- |
| `Files.writeString(path, "A\nB", charset)` | Ghi ký tự LF đúng như trong chuỗi, không tự tạo `CRLF` |
| `BufferedWriter.newLine()` | Chèn dấu xuống dòng theo `System.lineSeparator()` |
| `Files.readString(path, charset)` | Giữ newline đã có trong file |
| `BufferedReader.readLine()` | Trả nội dung dòng nhưng **bỏ ký tự kết thúc dòng** |
| `Files.readAllLines` / `Files.lines` | Tách thành dòng, không giữ terminator trong phần tử trả về |

Vì vậy, nếu yêu cầu xử lý file theo một format cần **LF** (ví dụ giao thức văn bản quy định byte `0A`), viết rõ `"\n"` là cách dễ kiểm soát. Nếu muốn newline theo hệ điều hành, `newLine()` thể hiện chủ đích đó.

Đừng lấy việc `Files.readAllLines` trả ra đúng các dòng làm bằng chứng rằng byte newline ban đầu được giữ nguyên. `CRLF` và `LF` có thể cho cùng các phần tử trong list.

## 10. Lưu ý về tính toàn vẹn và an toàn khi ghi tệp

### 10.1. Không ghi đè ngoài ý muốn

Nếu không có option, `writeString` thường **truncates existing file**. Khi file chứa cấu hình quan trọng, người dùng có thể cần tạo mới độc quyền:

~~~java
Files.writeString(path, content, StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW);
~~~

Đây là đoạn minh họa; nếu file đã tồn tại, phương thức có thể ném `FileAlreadyExistsException`, thay vì ghi đè. Cần xử lý `IOException` phù hợp.

### 10.2. Không nhầm append với transactional write

Nhiều lần gọi `writeString`/`BufferedWriter.write` không tự tạo một giao dịch nguyên tử cho toàn bộ file. Khi có nhiều writer, có thể cần khóa hay một cơ chế ghi record đủ mạnh. Khi cần tránh file bị hỏng do lỗi giữa chừng, thiết kế ghi vào file tạm **cùng file system**, hoàn tất I/O, rồi chuyển/đổi tên với option thích hợp (ví dụ `ATOMIC_MOVE` nếu provider hỗ trợ). Không ngầm khẳng định mọi file system đều hỗ trợ atomic move hoặc bảo đảm độ bền qua mất điện.

### 10.3. Không tự nối đường dẫn người dùng mà thiếu bảo vệ

Việc xác định charset **không** ngăn path traversal, ghi nhầm file, symlink hoặc vi phạm quyền. Với path từ bên ngoài, cần kiểm tra quyền, phạm vi thư mục và quy tắc mở file riêng. Không coi `normalize()` hoặc charset rõ ràng là biện pháp bảo mật hoàn chỉnh.

### 10.4. Encoding trong nguồn Java khác encoding của file dữ liệu

`javac -encoding UTF-8` chỉ quy định **charset của file mã nguồn .java** trong lệnh biên dịch. Nó **không** tự thay thế `StandardCharsets.UTF_8` được truyền cho `Files.writeString` hoặc `readString`.

Ví dụ code chứa chuỗi `"Café"`: mã nguồn được lưu UTF-8 để compiler hiểu đúng ký tự `é`; sau khi chạy, code có thể cố tình ghi chính chuỗi này thành ISO-8859-1. Hai charset thuộc **hai bước khác nhau**.

## 11. Những lỗi dễ gặp và cách sửa

| Hiểu nhầm hoặc lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| “`readString(path)` dùng charset của hệ điều hành” | Kết luận sai về overload | Theo Javadoc hiện đại, overload đó dùng UTF-8 |
| Ghi ISO-8859-1 nhưng đọc UTF-8 | Lỗi malformed hoặc mojibake | Lưu/passing charset theo format thực tế |
| Ghi ISO-8859-1 cho emoji | Không biểu diễn được | Dùng UTF-8 nếu đặc tả cho phép, hoặc báo lỗi |
| Dùng `readString` cho file cực lớn | Tốn nhiều bộ nhớ, có thể thất bại | Dùng `BufferedReader`/`Files.lines` |
| Gọi `Files.lines` mà không đóng stream | File handle giữ mở | Bọc stream trong try-with-resources |
| Gọi `newBufferedWriter` mà không đóng | Dữ liệu có thể còn trong buffer | Đóng bằng try-with-resources |
| Dùng `readLine` rồi mong giữ nguyên CRLF | Mất terminator gốc | Dùng `readString` nếu cần giữ nguyên newline |
| Dùng `newLine` nhưng format yêu cầu LF | Kết quả theo OS có thể khác | Ghi `"\n"` theo protocol |
| Quên default ghi đè của `writeString` | File cũ bị truncate | Chọn `CREATE_NEW` / `APPEND` và kiểm tra tồn tại |
| Cho rằng `writeString` luôn rollback nếu mã hóa lỗi | File có thể đã bị tạo hay thay một phần | Dùng file tạm/transactional workflow phù hợp |
| Cho rằng UTF-8 luôn không có BOM | Đọc file khác tool có thể gặp `U+FEFF` | Xử lý BOM theo format, không tự gỡ mọi nơi |
| Lẫn `javac -encoding` với charset `Files` | Test chạy sai kết quả khi đổi môi trường | Quy định rõ cả charset mã nguồn và charset dữ liệu |
| Bật replacement để che mọi lỗi | Mất thông tin và có thể sai định danh | Strict decode/encode cho dữ liệu cần toàn vẹn |

## 12. Bài tập thực hành

**Bài 1.** Một file chứa byte `43 61 66 E9` theo ISO-8859-1. Muốn đọc thành `"Café"`, nên dùng lệnh nào?

**Đáp án:** `Files.readString(path, StandardCharsets.ISO_8859_1)`. Dùng UTF-8 cho byte `E9` đơn lẻ sẽ báo malformed trong tình huống này.

**Bài 2.** `Files.writeString(path, "Hello", UTF_8)` được gọi hai lần cho cùng file, lần thứ hai ghi `"World"`. File sẽ có nội dung nào?

**Đáp án:** `"World"` nếu hai lần ghi thành công. Không truyền option sẽ truncate file trước khi ghi lại; **không** tự append `"HelloWorld"`.

**Bài 3.** Khi muốn append một dòng bằng UTF-8 vào file đã tồn tại, cần làm gì?

**Đáp án:** Dùng option `APPEND` và quyền ghi phù hợp, ví dụ `Files.newBufferedWriter(path, StandardCharsets.UTF_8, WRITE, APPEND)`; nếu muốn tạo khi chưa có, thêm `CREATE`. Chủ động quản lý newline giữa các dòng.

**Bài 4.** Vì sao `Files.readAllLines` không thích hợp với file 20 GB?

**Đáp án:** Nó đưa toàn bộ các dòng vào bộ nhớ. Thích hợp hơn là `newBufferedReader` đọc tuần tự hoặc `Files.lines` trong try-with-resources, tùy cách xử lý.

**Bài 5.** Đọc file UTF-8 có BOM `EF BB BF` qua `Files.readString` có tự xóa BOM không?

**Đáp án:** Không được giả định. Ví dụ chạy được cho thấy BOM được đọc thành `U+FEFF` ở đầu chuỗi. Chỉ xử lý loại bỏ nếu đặc tả file yêu cầu.

**Bài 6.** Một chuỗi UTF-8 hợp lệ chứa emoji; viết nó bằng `ISO_8859_1` có được không?

**Đáp án:** Không thể biểu diễn emoji trong ISO-8859-1. `Files.writeString` trong ví dụ báo `UnmappableCharacterException`; chọn UTF-8 nếu hợp đồng cho phép hoặc xử lý lỗi có chủ đích.

**Bài 7.** `reader.readLine()` và `Files.readString` có giữ nguyên newline của file giống nhau không?

**Đáp án:** Không. `readLine()` bỏ terminator của từng dòng; `readString` giữ các ký tự newline có trong file.

**Bài 8.** Nếu `Files.lines` trả một `Stream`, có cần đóng không?

**Đáp án:** Có. Stream giữ tài nguyên file đang mở; dùng try-with-resources. Nếu lỗi I/O xảy ra khi terminal operation đang chạy, nó có thể được gói trong `UncheckedIOException`.

**Bài 9.** Charset của file `.java` dùng để compile có quyết định charset file dữ liệu mà chương trình sẽ ghi không?

**Đáp án:** Không. `javac -encoding UTF-8` chỉ xử lý source; chương trình chọn charset đầu ra bằng tham số `StandardCharsets.UTF_8`, `ISO_8859_1` hoặc charset khác.

## 13. Checklist cuối bài

- [ ] Xác định và ghi rõ charset thực sự của file/giao thức, ưu tiên `StandardCharsets` khi thích hợp.
- [ ] Dùng `Files.readString/writeString(path, ..., charset)` cho file nhỏ, không cần giữ reader/writer mở.
- [ ] Dùng `newBufferedReader/newBufferedWriter` hoặc `Files.lines` cho file lớn/streaming.
- [ ] Nhớ các overload không truyền charset của `Files` được tài liệu xác định là UTF-8, không suy diễn từ default charset của OS.
- [ ] Chọn `CREATE_NEW`, `CREATE`, `TRUNCATE_EXISTING`, `WRITE`, `APPEND` theo hợp đồng, tránh ghi đè ngoài ý muốn.
- [ ] Đóng reader/writer/stream bằng try-with-resources.
- [ ] Biết phân biệt lỗi `MalformedInputException` (byte không hợp lệ) và `UnmappableCharacterException` (không mã hóa được ký tự).
- [ ] Không giả định write thất bại là rollback, hoặc append là atomic transaction.
- [ ] Hiểu `writeString` giữ ký tự newline trong chuỗi; `newLine` dùng line separator của môi trường.
- [ ] Nếu format có BOM UTF-8, xử lý chính sách BOM một cách tường minh.
- [ ] Kiểm thử round-trip với tiếng Việt, emoji, charset hẹp, BOM, file thiếu và lỗi I/O.
- [ ] Kiểm tra việc mã hóa file và bảo vệ path là hai trách nhiệm khác nhau.
- [ ] Ưu tiên API đang được hỗ trợ trên JDK hiện đại, không dựa vào kiến thức legacy.

## 14. Tài liệu tham khảo chính thức

- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `newBufferedReader`, `newBufferedWriter`, `readAllLines`, `lines`, cấu hình charset và xử lý I/O.
- [Java SE 21 — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8, US-ASCII, ISO-8859-1, UTF-16 và biến thể endian.
- [Java SE 21 — StandardOpenOption](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardOpenOption.html): `CREATE`, `CREATE_NEW`, `WRITE`, `TRUNCATE_EXISTING`, `APPEND`.
- [Java SE 21 — BufferedReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html): `readLine()` và cơ chế đọc theo buffer.
- [Java SE 21 — BufferedWriter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedWriter.html): `write`, `newLine` và `flush`.
- [Java SE 21 — MalformedInputException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/MalformedInputException.html) và [UnmappableCharacterException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/UnmappableCharacterException.html): phân biệt hai loại lỗi chuyển mã.
- [Java SE 21 — CodingErrorAction](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html): khi cần chính sách decode/encode custom thay vì strict mặc định của các overload `Files`.

**Kết luận:** Đọc ghi văn bản đúng không chỉ là gọi `Files.readString` / `Files.writeString`, mà phải **biết file được mã hóa theo charset nào**, biết giới hạn của API đọc toàn file, chính sách lỗi, cách quản lý tài nguyên và option ghi. Với chương trình hiện đại, dùng `StandardCharsets.UTF_8` hoặc charset được đặc tả tường minh; không đánh đồng việc “đọc ra được String” với việc “đã hiểu dữ liệu đúng”.
