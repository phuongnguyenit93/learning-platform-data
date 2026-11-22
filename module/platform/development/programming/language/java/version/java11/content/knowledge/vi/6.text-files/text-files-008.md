# Java 11 — Xử lý lỗi encoding, quyền truy cập và tệp không tồn tại

**Chủ đề:** Java 11 → Tệp văn bản. Bài học giải thích cách chẩn đoán và xử lý đúng ba nhóm sự cố khi đọc/ghi text file: **byte không giải mã được theo charset đã chọn**, **hệ điều hành/tệp từ chối quyền truy cập**, và **đường dẫn không trỏ tới tệp tồn tại**. Những kiến thức được chọn vẫn áp dụng cho Java và hệ thống hiện nay; ví dụ sử dụng API có sẵn trong **Java 11**, không phụ thuộc thư viện ngoài.

**Sau bài học, bạn có thể:** chọn UTF-8 có chủ đích, bắt `NoSuchFileException` và `AccessDeniedException`, phân biệt lỗi charset với lỗi đường dẫn, viết mã không che giấu lỗi thật, xử lý file lớn bằng stream, bảo toàn dữ liệu khi ghi, và kiểm thử những trường hợp có thể tái hiện ổn định trên nhiều hệ điều hành.

## 1. Đọc tệp văn bản thực chất gồm những bước nào?

Dù dòng code trông rất ngắn:

~~~java
String content = Files.readString(path, StandardCharsets.UTF_8);
~~~

hệ thống phải thực hiện nhiều công việc:

1. **Đường dẫn (`Path`):** xác định file theo working directory, filesystem, symlink và tên tệp.
2. **Quyền mở tệp:** hệ điều hành/file provider xác nhận tiến trình được đọc file, thư mục cha có thể truy cập, file không bị chặn bởi cơ chế khác.
3. **Đọc byte:** dữ liệu phải được đọc từ thiết bị, bộ nhớ đệm, filesystem hoặc mạng.
4. **Giải mã:** chuỗi byte phải hợp lệ trong **charset** đã chọn, chẳng hạn UTF-8.
5. **Xử lý nội dung:** kiểm tra cấu trúc dữ liệu, giới hạn độ dài, schema và quy tắc nghiệp vụ.

Lỗi ở những bước trên không giống nhau. Ví dụ **file có tồn tại nhưng không đọc được**, **file đọc được thành byte nhưng không giải mã thành UTF-8**, và **file không tồn tại** cần cách khắc phục khác nhau. Không thể chỉ bắt mọi `Exception` rồi trả `""` mà vẫn biết chuyện gì đã xảy ra.

### 1.1. Chọn API Java 11 phù hợp

| Trường hợp | API Java 11 | Lưu ý |
| --- | --- | --- |
| Đọc file text nhỏ/vừa, giữ nguyên dấu xuống dòng | `Files.readString(path, StandardCharsets.UTF_8)` | Đọc toàn bộ vào RAM; có thể lỗi I/O hoặc decoding. |
| Đọc từng dòng không giữ toàn bộ file | `Files.newBufferedReader(path, StandardCharsets.UTF_8)` | `try-with-resources`; `readLine()` không trả về ký tự kết thúc dòng. |
| Xử lý dòng theo Stream | `Files.lines(path, StandardCharsets.UTF_8)` | Phải đóng stream; lỗi khi duyệt có thể được bọc thành `UncheckedIOException`. |
| Ghi text nhỏ/vừa | `Files.writeString(path, text, StandardCharsets.UTF_8)` | Mặc định có thể tạo mới hoặc **ghi đè nội dung** file cũ. |
| Cần giữ nguyên byte nguồn hoặc xử lý charset bằng tay | `Files.readAllBytes(path)` và `CharsetDecoder` | Chỉ tải toàn bộ byte nếu đã kiểm soát dung lượng. |

`Files.readString` và `Files.writeString` có từ **Java 11**. Các overload không truyền charset của hai hàm này dùng **UTF-8**, nhưng ghi rõ `StandardCharsets.UTF_8` vẫn có ích cho hợp đồng dữ liệu và code review. Đừng suy từ đó rằng mọi API I/O trong Java 11 hoặc mọi file trên máy đều mặc định UTF-8.

## 2. Lỗi encoding: byte và ký tự không phải một thứ

**Encoding/charset** là quy tắc chuyển các ký tự Unicode thành byte khi ghi và chuyển byte thành ký tự khi đọc. Java `String` lưu nội dung ký tự; file trên ổ đĩa là byte. Hai phía phải thống nhất charset, hoặc phải có quy trình chuyển đổi xác định.

Ví dụ “Tiếng Việt” được lưu theo UTF-8 sẽ có nhiều byte cho các ký tự có dấu. Nếu file thực sự là UTF-8 nhưng code đọc với charset khác, kết quả có thể thành **mojibake** (ký tự rác) dù **không ném exception**. Nếu byte không hợp lệ trong charset đã chọn, việc giải mã nghiêm ngặt có thể thất bại.

### 2.1. Những dấu hiệu cần kiểm tra

- Text tiếng Việt bị thành chuỗi ký tự lạ hoặc xuất hiện ký hiệu thay thế `�`: có thể đọc sai charset hoặc dữ liệu nguồn đã hỏng.
- `MalformedInputException`: byte sequence không hợp lệ với charset đang decode, thường gặp khi coi dữ liệu không phải UTF-8 là UTF-8.
- `UnmappableCharacterException`: dữ liệu có dạng mã hóa hợp lệ nhưng không ánh xạ được sang ký tự tương ứng, tùy charset/encoder.
- File có ký tự **BOM** đầu nội dung: BOM có thể là một phần quy ước định dạng; phải xử lý theo hợp đồng file, không xóa mọi ký tự đầu tiên một cách mù quáng.
- File có chuỗi `\r\n`, `\n`, `\r`: đây là khác biệt **line ending**, không nhất thiết là lỗi charset. Cần giữ nguyên nếu so sánh byte hoặc ký chữ ký số.

### 2.2. Đọc UTF-8 và nhận lỗi giải mã

~~~java
Path path = Path.of("data", "input.txt");
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là **đoạn minh họa trong một phương thức**, yêu cầu import `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets` và xử lý `IOException`. `Path.of` có sẵn trên JDK 11.

`Files.readString` ném `IOException` khi đọc thất bại hoặc nội dung có byte malformed/unmappable theo charset. Có thể phân loại các lỗi giải mã thông qua lớp cha `CharacterCodingException`, rồi dùng lớp con cụ thể khi cần báo cáo rõ:

~~~java
try {
    String text = Files.readString(path, StandardCharsets.UTF_8);
    process(text);
} catch (MalformedInputException e) {
    reportInvalidEncoding(e);
} catch (UnmappableCharacterException e) {
    reportUnmappableCharacter(e);
}
~~~

Đây là **đoạn minh họa**, các hàm `process`, `reportInvalidEncoding`, `reportUnmappableCharacter` được ứng dụng định nghĩa; còn phải bắt/khai báo `IOException` cho các lỗi filesystem khác. Hai exception về decoding đều là subclass của `CharacterCodingException`, tiếp đến `IOException`.

**Không tự động thử hàng loạt charset rồi chọn kết quả “nhìn có vẻ đọc được”.** Nhiều charset một byte có thể giải mã gần như mọi byte nhưng tạo text sai mà không báo lỗi. Khi dữ liệu có hợp đồng nhập, ưu tiên lấy charset từ **đặc tả giao thức/nguồn, metadata đáng tin, cấu hình import được người dùng chọn**, hoặc chuyển toàn bộ pipeline sang UTF-8.

### 2.3. CharsetDecoder và chính sách dữ liệu hỏng

Khi cần kiểm soát cụ thể “dừng lỗi” hoặc “thay thế byte lỗi”, sử dụng `CharsetDecoder`:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
    .onMalformedInput(CodingErrorAction.REPORT)
    .onUnmappableCharacter(CodingErrorAction.REPORT);

CharBuffer chars = decoder.decode(ByteBuffer.wrap(bytes));
String result = chars.toString();
~~~

Đây là **đoạn minh họa** với `bytes` là `byte[]` đã có; cần import `java.nio.ByteBuffer`, `java.nio.CharBuffer`, `java.nio.charset.CharsetDecoder`, `java.nio.charset.CodingErrorAction`, `java.nio.charset.StandardCharsets` và xử lý `CharacterCodingException`. Cơ chế `REPORT` làm lỗi giải mã được phát hiện. `REPLACE` thay dữ liệu lỗi bằng ký tự thay thế, có thể làm **mất thông tin**; chỉ dùng khi nghiệp vụ cho phép và phải ghi nhận việc thay thế.

Ngược lại, một số constructor dạng `new String(bytes, charset)` có chính sách thay thế đầu vào malformed thay vì ném lỗi. Nếu cần import dữ liệu chính xác, đừng mặc định rằng “đọc thành String được” đồng nghĩa file hợp lệ. Với dữ liệu nhỏ, dùng `Files.readString` để nhận lỗi; với luồng lớn, `newBufferedReader` hoặc decoder cho stream để giữ giới hạn bộ nhớ.

### 2.4. Quy tắc giải quyết lỗi charset

1. Xác định **file đến từ đâu**, encoding đã được công bố hay chưa, có bị đổi charset giữa các bước không.
2. Giữ một mẫu byte gốc an toàn cho việc phân tích, tránh log/đăng tải dữ liệu nhạy cảm.
3. Đọc theo đúng charset nguồn, validate kết quả, sau đó **ghi lại UTF-8** nếu quy trình có bước chuẩn hóa.
4. Nếu byte hỏng, báo lỗi rõ hoặc đưa bản ghi vào luồng xử lý lỗi; không lặng lẽ gộp dữ liệu hỏng vào dữ liệu đúng.
5. Kiểm tra độ dài, BOM và line endings theo định dạng thực tế; test với tiếng Việt, emoji, file rỗng và input malformed.

**Không thể xác định chính xác mọi charset chỉ từ byte** khi không có metadata/đặc tả đáng tin cậy. Việc “sửa dấu tiếng Việt” phải dựa vào nguồn gốc dữ liệu, tránh làm hỏng file đã đúng.

## 3. Tệp không tồn tại: NoSuchFileException và ngữ nghĩa nghiệp vụ

Java NIO.2 có `java.nio.file.NoSuchFileException`, subclass của `FileSystemException` rồi `IOException`. Nó có thể xuất hiện khi cố mở đường dẫn không tồn tại. Ví dụ:

~~~java
Path path = Path.of("config", "settings.txt");
String settings = Files.readString(path, StandardCharsets.UTF_8);
~~~

Lệnh có thể ném `NoSuchFileException` nếu file/đường dẫn cần thiết chưa tồn tại, tên sai hoặc bị xóa trước khi mở. Khi điều tra, xem xét:

- **Working directory:** `Path.of("config/settings.txt")` là đường dẫn **tương đối** với working directory của tiến trình, không tự động tương đối với thư mục chứa file `.java` hoặc JAR. IDE, CLI, container, service và CI có thể có working directory khác nhau.
- **Tên file và chữ hoa/chữ thường:** hệ điều hành/filesystem khác nhau về case sensitivity; file `Config.txt` không luôn tương đương `config.txt`.
- **Đường dẫn cha:** thư mục `config/` có tồn tại không? Một thành phần cha không phải directory cũng có thể gây các lỗi filesystem khác như `NotDirectoryException`.
- **Symlink:** symbolic link có thể trỏ đến đích đã mất hoặc ra ngoài thư mục dự kiến.
- **Thời điểm:** file có thể bị di chuyển/xóa giữa lúc bạn kiểm tra và lúc bạn mở.

### 3.1. Vì sao không chỉ kiểm tra exists trước khi đọc?

~~~java
if (Files.exists(path)) {
    String text = Files.readString(path, StandardCharsets.UTF_8);
}
~~~

Đây là **đoạn minh họa dễ gây lỗi**: file có thể biến mất sau `Files.exists`, nên `readString` vẫn có thể ném exception. `Files.exists`/`Files.notExists` cũng có thể cùng trả `false` nếu trạng thái không xác định do lỗi truy cập hoặc I/O; chúng không phải cơ chế bảo đảm kết quả.

**Cách thực tế:** thực hiện thao tác đọc thật trong `try` rồi xử lý `NoSuchFileException` khi nó phát sinh. Có thể dùng `exists` để hiển thị thông tin giao diện, nhưng nó không thay thế exception handling ở lúc truy cập.

### 3.2. File tùy chọn hay file bắt buộc?

Cách phản ứng phụ thuộc hợp đồng:

| Tình huống | Hướng xử lý |
| --- | --- |
| File cấu hình tùy chọn không có | Sử dụng default được định nghĩa rõ, ghi sự kiện ở mức phù hợp. |
| File cấu hình bắt buộc không có | Fail fast với thông báo đường dẫn tương đối/tuyệt đối đã kiểm soát, hướng dẫn cung cấp file. |
| File dữ liệu người dùng không tồn tại | Trả lỗi “không tìm thấy” hoặc yêu cầu chọn file khác; không giả định một file trống. |
| File log/output chưa có | Có thể được tạo khi ghi **nếu hợp đồng cho phép**; không tạo file đầu vào đang thiếu khi chỉ định đọc. |
| File bị xóa trong khi xử lý | Xử lý như lỗi I/O tại thao tác thực tế; cân nhắc thử lại khi kịch bản cho phép. |

Không nên bắt `NoSuchFileException` rồi tự `Files.writeString(path, "")` cho mọi trường hợp: có thể che giấu lỗi cấu hình hoặc phá hủy luồng xử lý dữ liệu.

## 4. Quyền truy cập: AccessDeniedException và hành vi hệ điều hành

`java.nio.file.AccessDeniedException` là checked exception cho thao tác filesystem bị từ chối, thường vì kiểm tra quyền hoặc cơ chế truy cập khác. Nó không phải là lời khẳng định rằng nguyên nhân **chắc chắn** chỉ là một bit “read-only”.

Những yếu tố hay gặp:

- Tiến trình chạy dưới user/service account không có quyền đọc file, ghi thư mục hoặc đi qua thư mục cha.
- Quy tắc **ACL** (access control list), permission của container/volume mount hoặc chính sách bảo mật hệ thống hạn chế truy cập.
- File/directory hoặc đường dẫn đích đang chịu giới hạn ghi; một số nền tảng có cơ chế khóa/chia sẻ file riêng.
- Đường dẫn đã được ánh xạ tới tài nguyên mạng hoặc filesystem provider trả về lỗi riêng.
- Ứng dụng tưởng dùng quyền của người chạy IDE nhưng khi deploy lại dùng identity của service khác.

**AccessDeniedException không bảo đảm là dạng exception duy nhất khi bị từ chối.** Java NIO giao tiếp với nhiều filesystem provider/OS; các lỗi cụ thể khác vẫn có thể là `FileSystemException` hoặc `IOException`. Thông báo từ `getReason()` là thông tin provider cung cấp, có thể rỗng và không ổn định giữa máy.

### 4.1. Không dùng Files.isReadable như cơ chế cấp quyền

~~~java
boolean apparentlyReadable = Files.isReadable(path);
~~~

`Files.isReadable` là phép kiểm tra khả năng đọc **ở thời điểm đó** và có thể không phản ánh đầy đủ việc mở/đọc thực tế, nhất là khi filesystem hoặc ACL thay đổi. Giá trị `false` không đủ để kết luận “file không tồn tại”; có thể do không đọc được hoặc trạng thái không xác định.

**Hãy thử mở/đọc file và bắt lỗi thao tác thực tế.** Không có API kiểm tra nào đảm bảo một quyền truy cập sẽ còn hợp lệ mãi về sau.

### 4.2. Khắc phục đúng nơi có thẩm quyền

Khi truy cập bị từ chối, kiểm tra path, service account và quyền thực tế trên **file lẫn thư mục cha**; với container, kiểm tra user, volume mount và cách mount read-only. Không tự động nâng quyền tiến trình, đổi toàn bộ thư mục thành world-writable hoặc tắt kiểm soát bảo mật để “làm cho chạy được”.

Nếu tệp thuộc về một user khác, hành động phù hợp là **yêu cầu cấp quyền hoặc chọn đường dẫn được phép**. Ứng dụng nên trả mã lỗi/hướng dẫn rõ, không in token hoặc file content trong log. Nếu hệ thống hỗ trợ cấu hình lại quyền, thao tác đó thuộc **quy trình vận hành có thẩm quyền**, không nên được thực thi âm thầm từ exception handler.

### 4.3. Phân biệt quyền đọc và quyền ghi

Một tiến trình có thể đọc file nhưng không ghi được; hoặc tạo file mới trong thư mục nhưng không sửa được file cụ thể. Các thao tác có yêu cầu khác nhau:

| Thao tác | Điều kiện thường cần |
| --- | --- |
| `Files.readString(file)` | Quyền đọc file và quyền truy cập đường dẫn cha. |
| `Files.writeString(existingFile, ...)` | Quyền ghi file; còn phụ thuộc chính sách filesystem. |
| Tạo file mới | Quyền ghi/tạo trong thư mục cha; tên chưa bị dùng nếu dùng `CREATE_NEW`. |
| Xóa/di chuyển file | Quyền sửa directory entry hoặc quyền liên quan theo OS/provider. |
| Đọc directory listing | Quyền đọc/liệt kê thư mục, khác quyền đọc nội dung từng file. |

Không hard-code giả định POSIX chmod sẽ hoạt động trên Windows. Để test quyền bị từ chối, dùng môi trường integration test có quyền/ACL kiểm soát được và xác định nền tảng; không dựa vào test `setReadable(false)` rồi kết luận chắc chắn rằng mọi OS sẽ ném `AccessDeniedException` (nhất là khi test chạy với quyền đặc biệt).

## 5. Cây exception Java 11 và cách đặt catch

Những kiểu lỗi cần nhớ:

| Exception | Dạng lỗi | Hành động thường phù hợp |
| --- | --- | --- |
| `NoSuchFileException` | File hoặc thành phần đường dẫn cần thiết không tồn tại | Kiểm tra path, phân biệt file tùy chọn và bắt buộc. |
| `AccessDeniedException` | Thao tác bị từ chối | Kiểm tra identity, ACL, thư mục cha, mount; trả lỗi truy cập. |
| `MalformedInputException` | Byte không hợp lệ cho charset đọc | Sửa hợp đồng encoding/nguồn, từ chối dữ liệu hỏng. |
| `UnmappableCharacterException` | Dữ liệu không ánh xạ được theo charset/encoder | Đổi charset theo đặc tả hoặc xử lý lỗi chuyển mã. |
| `FileSystemException` | Một lỗi filesystem có ngữ cảnh file/reason | Đọc thông tin provider và phân loại thêm. |
| `IOException` | Lỗi I/O còn lại | Không bỏ qua; giữ cause khi báo lên tầng gọi. |
| `InvalidPathException` | Chuỗi path sai cú pháp ở bước tạo `Path` | Kiểm tra đầu vào; đây là runtime exception, không phải subclass của IOException. |

`NoSuchFileException` và `AccessDeniedException` đều là `FileSystemException`. `MalformedInputException` và `UnmappableCharacterException` đều thuộc `CharacterCodingException`, tiếp đến `IOException`. **Đặt catch cụ thể trước catch tổng quát**.

~~~java
try {
    String text = Files.readString(path, StandardCharsets.UTF_8);
    consume(text);
} catch (NoSuchFileException e) {
    handleMissingFile(e);
} catch (AccessDeniedException e) {
    handlePermissionFailure(e);
} catch (CharacterCodingException e) {
    handleDecodeFailure(e);
} catch (IOException e) {
    handleOtherIoFailure(e);
}
~~~

Đây là **đoạn minh họa**: `path` và các hàm `consume`/`handle...` thuộc ứng dụng. Cần các import `java.io.IOException`, `java.nio.charset.CharacterCodingException`, `java.nio.charset.StandardCharsets` và các class trong `java.nio.file`.

Khi lỗi ở tầng thấp không thể xử lý, có thể **ném lại** exception hoặc bọc bằng một exception nghiệp vụ với **cause** và ngữ cảnh không nhạy cảm:

~~~java
throw new IOException("Cannot load required settings", e);
~~~

Đây là đoạn minh họa bên trong `catch (IOException e)`; không nên mất stack trace bằng cách `throw new IOException(e.getMessage())` không giữ cause, hoặc chỉ `printStackTrace()` rồi tiếp tục như thể đọc thành công.

## 6. Chương trình Java 11 chạy độc lập để kiểm chứng ba tình huống

Ví dụ dưới đây tạo file tạm trong thư mục do JDK cấp, viết một file UTF-8 hợp lệ, một file có byte không hợp lệ trong UTF-8 và cố đọc một đường dẫn không tồn tại. Chương trình **không cần Internet hay dependency bên ngoài**, có mã hoàn chỉnh và output ổn định. Nhánh `AccessDeniedException` có trong trình phân loại, nhưng **không giả lập quyền bị từ chối** vì cách đó không portable giữa Windows, Linux, macOS và các filesystem khác.

Lưu tệp **`TextFileErrorsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public final class TextFileErrorsDemo {
    private TextFileErrorsDemo() {
    }

    static String readResult(Path path) {
        try {
            String text = Files.readString(path, StandardCharsets.UTF_8);
            return "OK:" + text.replace("\n", " | ");
        } catch (NoSuchFileException e) {
            return "NOT_FOUND";
        } catch (AccessDeniedException e) {
            return "ACCESS_DENIED";
        } catch (CharacterCodingException e) {
            return "BAD_ENCODING";
        } catch (IOException e) {
            return "IO_ERROR";
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("java11-text-");
        Path valid = dir.resolve("valid.txt");
        Path invalid = dir.resolve("invalid.txt");
        Path missing = dir.resolve("missing.txt");

        try {
            Files.writeString(
                valid, "Xin chào\nJava 11", StandardCharsets.UTF_8);
            Files.write(
                invalid, new byte[] {(byte) 0xC3, (byte) 0x28});

            System.out.println("valid=" + readResult(valid));
            System.out.println("missing=" + readResult(missing));
            System.out.println("invalid=" + readResult(invalid));
        } finally {
            Files.deleteIfExists(valid);
            Files.deleteIfExists(invalid);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 11 trở lên:

~~~bash
javac -encoding UTF-8 TextFileErrorsDemo.java
java TextFileErrorsDemo
~~~

**Stdout chính xác trong điều kiện file tạm có thể được tạo/đọc/ghi bình thường:**

~~~text
valid=OK:Xin chào | Java 11
missing=NOT_FOUND
invalid=BAD_ENCODING
~~~

**Tại sao?**

1. `Files.createTempDirectory` tạo thư mục riêng; chương trình không phụ thuộc file đã có trước khi chạy.
2. File `valid.txt` chứa UTF-8 hợp lệ, bao gồm một ký tự xuống dòng `\n`. `replace("\n", " | ")` chỉ dùng để tạo output gọn trong ví dụ, không phải bước xử lý charset.
3. `missing.txt` chưa hề được tạo nên `Files.readString` thông thường ném `NoSuchFileException`. Nhánh này trả `NOT_FOUND`.
4. Hai byte `0xC3 0x28` **không tạo thành UTF-8 hợp lệ**: `0xC3` đòi byte tiếp diễn, còn `0x28` không phải byte tiếp diễn; decoder nghiêm ngặt ném lỗi coding, được bắt bằng `CharacterCodingException`.
5. `finally` dọn file tạm. Nếu môi trường không cho phép tạo/xóa file, thao tác quản lý tài nguyên vẫn có thể ném `IOException` — chương trình không cố ngụy trang đó thành một lỗi encoding.
6. `AccessDeniedException` được xử lý như một kết quả phân loại nhưng không có case stdout cho nó: hệ điều hành và quyền chạy quyết định khi nào xảy ra.

**Trong sản phẩm:** mẫu trả chuỗi trạng thái là cách dễ minh họa. Không nên “nuốt” mọi `IOException` thành `IO_ERROR` mà không log/giữ cause trong hệ thống thật; thay bằng result type có error category, exception cause, đường dẫn đã kiểm soát, hoặc ném exception lên tầng xử lý. Chỉ cho phép fallback khi nghiệp vụ chấp nhận mất file.

## 7. File lớn, streaming và lỗi xuất hiện sau khi mở

`Files.readString` thích hợp với file nhỏ/vừa; toàn bộ dữ liệu được giữ trong một `String`. Với log hoặc dữ liệu lớn, dùng `BufferedReader` để đọc theo dòng và đóng tài nguyên đúng cách:

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
~~~

Đây là **đoạn minh họa**, `path` là `Path` đã có, `processLine` là hàm ứng dụng; cần import `java.io.BufferedReader`, `java.nio.file.Files`, `java.nio.charset.StandardCharsets`, xử lý `IOException`. `readLine` bỏ dấu xuống dòng khỏi phần nội dung trả về; nếu cần giữ nguyên mọi byte/line ending, đọc theo buffer/byte stream thích hợp.

Với `Files.lines`:

~~~java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlank = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

Đây là đoạn minh họa cần import `java.util.stream.Stream` và các lớp `Files/Path/StandardCharsets`. `isBlank()` có từ Java 11. **Đặc biệt:** `Files.lines` có thể mở file thành công nhưng lỗi I/O/decoding phát sinh **trong lúc Stream đang duyệt**; khi đó exception thường được bọc thành `UncheckedIOException`. Vì vậy chỉ catch `IOException` quanh lúc tạo stream có thể bỏ sót lỗi khi chạy terminal operation.

~~~java
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(line -> processLine(line));
} catch (UncheckedIOException e) {
    IOException cause = e.getCause();
    reportIoFailure(cause);
}
~~~

Đây là đoạn minh họa, cần import `java.io.UncheckedIOException` cùng các import tương ứng và vẫn xử lý/khai báo checked `IOException` từ `Files.lines` lúc mở. Với pipeline nhiều bước, hãy ghi nhận **dòng/record nào** lỗi nếu có thể, nhưng không đưa dữ liệu nhạy cảm vào log. Không xử lý parser lẫn I/O trong một catch chung để rồi báo sai nguyên nhân.

**Chú ý encoding trong luồng:** với `newBufferedReader`, lỗi malformed có thể chỉ xuất hiện ở dòng thứ N, sau khi đã xử lý N-1 dòng. Nếu nghiệp vụ đòi tính **atomic**, đừng commit dữ liệu từng dòng trước khi toàn file được xác thực; cân nhắc staging/transaction, hoặc cách import từng phần có rollback/compensation rõ ràng.

## 8. Ghi tệp: quyền, file mới và tránh mất dữ liệu

Ghi file cũng có thể thất bại do quyền, thư mục cha thiếu, hết dung lượng, đường dẫn sai, filesystem chỉ đọc hoặc lỗi encoding đầu ra. Với `Files.writeString(path, text, UTF_8)` **không có option**, Java 11 mặc định tương đương `CREATE` + `TRUNCATE_EXISTING` + `WRITE`: nếu file tồn tại, nội dung cũ sẽ bị xóa trước khi ghi mới. Đây là hành vi phải xét kỹ khi file chứa dữ liệu quan trọng.

### 8.1. Chỉ tạo nếu chưa tồn tại

~~~java
Files.writeString(
    target,
    text,
    StandardCharsets.UTF_8,
    StandardOpenOption.CREATE_NEW,
    StandardOpenOption.WRITE);
~~~

Đây là **đoạn minh họa** với `target` kiểu `Path` và `text` kiểu `String`, cần import `java.nio.file.StandardOpenOption`. `CREATE_NEW` kết hợp kiểm tra không tồn tại và tạo file như một thao tác nguyên tử của filesystem provider; nếu tên đã được sử dụng có thể ném `FileAlreadyExistsException`, giúp tránh ghi đè vô ý. Không dùng riêng `Files.exists` rồi ghi theo chế độ mặc định vì sẽ có race giữa check và write.

### 8.2. Thư mục cha phải tồn tại khi ghi

~~~java
Path parent = target.getParent();
if (parent != null) {
    Files.createDirectories(parent);
}
Files.writeString(
    target, text, StandardCharsets.UTF_8,
    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

Đây là đoạn minh họa; `createDirectories` có thể ném `IOException` khi không đủ quyền hoặc đường dẫn không hợp lệ theo provider. Chỉ tự tạo thư mục nếu hợp đồng cho phép và path nằm trong khu vực ứng dụng được phép ghi; không tạo tùy ý theo input chưa kiểm soát.

### 8.3. Ghi bản mới trước khi thay bản cũ

Với file cấu hình quan trọng, không nên làm mất bản cũ nếu ghi lỗi giữa chừng. Một kỹ thuật là **ghi vào file tạm cùng thư mục → đóng/flush → thay đích bằng move**, kiểm tra chính sách ghi đè và hỗ trợ atomic move:

~~~java
Path temp = Files.createTempFile(target.getParent(),
                                ".settings-", ".tmp");
try {
    Files.writeString(temp, text, StandardCharsets.UTF_8);
    Files.move(temp, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temp);
}
~~~

Đây là **đoạn minh họa** cho file đích `target` có thư mục cha tồn tại và `text` đã được xác thực; cần import `StandardCopyOption`, các lớp `Files/Path` và xử lý `IOException`. `ATOMIC_MOVE` có thể không được filesystem/provider hỗ trợ và ném `AtomicMoveNotSupportedException`; việc thay thế đích đã tồn tại cùng `ATOMIC_MOVE` có khác biệt phụ thuộc provider. Thiết kế fallback có chủ đích, kiểm soát quyền/ACL, quyền ownership và độ bền dữ liệu (fsync) theo yêu cầu thực tế. Không hiểu lệnh trên là bảo đảm tuyệt đối về transaction/durability của mọi OS.

### 8.4. Khi nào cần append?

~~~java
Files.writeString(
    logPath,
    record + System.lineSeparator(),
    StandardCharsets.UTF_8,
    StandardOpenOption.CREATE,
    StandardOpenOption.APPEND);
~~~

Đây là đoạn minh họa. `APPEND` không đồng nghĩa một bản ghi text của nhiều thread/process luôn được ghi atomically; khi cần log đồng thời, hãy dùng logging framework và sink phù hợp. Không dùng append để cập nhật cấu hình JSON hoặc dữ liệu đòi schema nguyên khối.

## 9. Đường dẫn từ người dùng: bảo mật và khả năng di chuyển

File path lấy từ user/config cần được **giới hạn trong thư mục cho phép** và chuẩn hóa trước khi dùng. Ví dụ ý tưởng:

~~~java
Path root = Path.of("data").toAbsolutePath().normalize();
Path candidate = root.resolve(userSuppliedName).normalize();
if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Path outside allowed directory");
}
~~~

Đây là **đoạn minh họa**, `userSuppliedName` là dữ liệu chưa tin cậy. Phép `normalize` và `startsWith` chỉ là **bộ lọc cơ bản** chống `..` theo đường dẫn từ vựng, **không phải bảo vệ hoàn chỉnh trước symlink/race**. Với yêu cầu bảo mật cao, cần giải quyết liên kết tượng trưng, actual file identity, truy cập thư mục có thẩm quyền và các kỹ thuật tránh time-of-check/time-of-use theo filesystem. Không cho path từ API quyết định tùy ý nơi đọc/ghi file nhạy cảm.

- Tránh giả định separator của Windows và Linux giống nhau: dùng `Path.of(...)`, `resolve(...)` và API `Path`.
- Không hard-code absolute path của máy nhà phát triển; dùng cấu hình, resource đã đóng gói hoặc thư mục dữ liệu ứng dụng đúng ngữ cảnh.
- Đừng đưa filename chứa PII, đường dẫn home đầy đủ, token hoặc raw file content vào logs/metrics ngoài yêu cầu vận hành được phê duyệt.
- Kiểm tra file có giới hạn kích thước, tên file, loại dữ liệu và thời gian xử lý; một tệp cực lớn có thể làm `readString` cạn bộ nhớ dù encoding hợp lệ.
- Không coi `Files.probeContentType` là cách xác định chắc chắn charset; MIME type và charset là hai thuộc tính khác nhau.

## 10. Hợp đồng lỗi ở tầng ứng dụng

Một tầng xử lý file hữu ích nên tách **phân loại lỗi** khỏi **quyết định nghiệp vụ**:

~~~text
Đọc file
  ├─ Thành công: decode → validate → xử lý
  ├─ NoSuchFileException: tệp tùy chọn? default : báo thiếu đầu vào
  ├─ AccessDeniedException: báo hạn chế truy cập, kiểm tra identity/ACL
  ├─ CharacterCodingException: báo encoding không hợp lệ, giữ nguyên dữ liệu nguồn
  └─ IOException khác: giữ cause và báo lỗi I/O phù hợp
~~~

Sơ đồ trên là **flow minh họa**, không phải mã Java. Quyết định có retry hay không phụ thuộc lỗi:

| Lỗi | Retry ngay có hợp lý? |
| --- | --- |
| File bị thiếu theo đúng hợp đồng | Thường không; yêu cầu cung cấp đúng path hoặc dùng default đã quy định. |
| File chưa xuất hiện do producer bất đồng bộ | Có thể chờ/retry **hữu hạn, có deadline** nếu thiết kế yêu cầu file sẽ đến. |
| Quyền bị từ chối ổn định | Thường không; cần sửa quyền/identity/config. |
| Encoding không hợp lệ | Không; byte sai sẽ vẫn sai khi đọc lại không đổi. |
| Lỗi I/O mạng/thiết bị thoáng qua | Có thể retry có giới hạn, log attempt và deadline. |

Đối với dịch vụ, phân loại lỗi rõ trong log/metrics: `operation=read_text`, `result=not_found/access_denied/bad_encoding/io_error`, charset mong đợi, thời lượng và tên file **đã chuẩn hóa/an toàn để lộ**; không dùng raw filename tùy ý làm nhãn metrics vì cardinality cao và có thể rò rỉ dữ liệu. Với lỗi có thể trả cho người dùng, dùng thông điệp thân thiện và mã lỗi ổn định; chi tiết stack trace nằm ở logging nội bộ có quyền truy cập phù hợp.

**Không tự động suy diễn:** `NoSuchFileException` không đồng nghĩa “user có lỗi”; `AccessDeniedException` không chắc là “file đang bị khóa”; `CharacterCodingException` không chứng minh file chắc chắn dùng charset nào khác. Chỉ ghi nhận điều Java thực sự phát hiện.

## 11. Kiểm thử và tái hiện lỗi

Các bài test nên tạo tài nguyên dưới thư mục tạm, tránh phụ thuộc path ở máy lập trình. Bằng **JUnit Jupiter** bản tương thích JDK 11, `@TempDir` cấp một thư mục test được quản lý tự động:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TextFileErrorsDemoTest {
    @TempDir
    Path tempDir;

    @Test
    void missingFileIsReported() {
        Path missing = tempDir.resolve("absent.txt");
        assertEquals("NOT_FOUND",
            TextFileErrorsDemo.readResult(missing));
    }

    @Test
    void invalidUtf8IsReported() throws IOException {
        Path broken = tempDir.resolve("bad.txt");
        Files.write(broken, new byte[] {(byte) 0xC3, (byte) 0x28});
        assertEquals("BAD_ENCODING",
            TextFileErrorsDemo.readResult(broken));
    }

    @Test
    void utf8VietnameseIsPreserved() throws IOException {
        Path good = tempDir.resolve("good.txt");
        Files.writeString(good, "Tiếng Việt", StandardCharsets.UTF_8);
        assertEquals("OK:Tiếng Việt",
            TextFileErrorsDemo.readResult(good));
    }
}
~~~

Đây là **một lớp unit test hoàn chỉnh khi đặt cùng package với `TextFileErrorsDemo` và đã cấu hình dependency JUnit Jupiter/JUnit Platform**; nó không chạy trực tiếp chỉ với `javac` của JDK 11 vì JUnit không nằm trong Java SE. Cả ba test tạo file/đường dẫn tạm độc lập, có thể chạy trên máy phù hợp. Cấu hình JUnit Jupiter tương thích Java 11 trong Maven/Gradle và chạy bằng test task của build tool; không tuyên bố các test đã thực sự chạy trong tài liệu này.

**Không kiểm thử quyền bằng chmod trên mọi máy và chờ cùng exception:** Windows dùng ACL, POSIX permission có hành vi riêng, một số tiến trình có quyền bypass. Thay vì unit test flaky, dùng integration test với user/volume permission đã được thiết lập và kiểm tra lỗi I/O theo từng môi trường. Với unit test của code phân loại, có thể tách giao diện đọc tệp để inject một nguồn ném `AccessDeniedException`, tránh phụ thuộc quyền OS thực tế.

**Checklist test theo tình huống:**

1. UTF-8 hợp lệ: tiếng Việt, emoji, file rỗng, file có nhiều dòng.
2. UTF-8 sai: chuỗi byte malformed; xác nhận không bị đọc thành dữ liệu “đúng” im lặng.
3. File thiếu: tệp bắt buộc phải báo lỗi, tệp tùy chọn mới dùng default.
4. Tên/đường dẫn sai: relative path, working directory khác nhau, directory thay vì file.
5. Permission: chỉ chạy trong môi trường đã cấu hình quyền; xác nhận nguyên nhân và thông điệp không lộ dữ liệu.
6. Ghi file: file đã tồn tại và chế độ `CREATE_NEW`, thư mục cha thiếu, full disk/readonly filesystem khi có fixture phù hợp.
7. File lớn/giải mã lỗi giữa luồng: tài nguyên được đóng, rollback/partial import được xử lý theo hợp đồng.

## 12. Các lỗi lập trình phổ biến

| Cách làm sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| `catch (Exception e) { return ""; }` | Không phân biệt file rỗng hợp lệ với đọc thất bại. | Bắt loại lỗi cụ thể, giữ cause; chỉ default khi hợp đồng cho phép. |
| `new String(bytes, UTF_8)` và coi mọi text trả về là hợp lệ | Byte không hợp lệ có thể bị thay thế bằng ký tự khác. | Dùng `Files.readString` hoặc decoder `REPORT`, validate nội dung. |
| Đọc mọi file theo charset mặc định của máy | Hành vi khác giữa máy và môi trường. | Chọn charset theo đặc tả; ưu tiên UTF-8 cho dữ liệu mới. |
| `Files.exists` rồi giả định `readString` không còn lỗi | File/quyền có thể thay đổi giữa kiểm tra và mở. | Xử lý exception tại lúc thao tác thực tế. |
| `Files.isReadable(path) == false` → báo “file không tồn tại” | Sai phân loại access failure. | Phân tích lỗi khi mở/đọc, không dùng một phép check cho mọi kết luận. |
| Ghi đè bằng `Files.writeString` mặc định | Có thể mất nội dung trước khi ghi xong. | Chọn option rõ ràng; tạo mới bằng `CREATE_NEW` hoặc ghi file tạm rồi move khi phù hợp. |
| Dùng `Files.readString` cho file rất lớn | Áp lực bộ nhớ, thậm chí OOM. | Streaming theo dòng/khối và giới hạn dữ liệu. |
| Đóng file chậm hoặc quên đóng stream | Rò rỉ descriptor/lock, lỗi khi rename/xóa. | `try-with-resources` cho reader, writer, stream. |
| Giải mã lỗi nhưng vẫn commit dữ liệu đã import một phần | Trạng thái không nhất quán. | Transaction/staging hoặc chiến lược partial import được quy định. |
| Tự đổi permission quá rộng để chữa AccessDenied | Rủi ro bảo mật, che lỗi cấu hình. | Sửa identity/ACL theo quyền tối thiểu và quy trình có thẩm quyền. |
| Tự động retry lỗi encoding hoặc permission | Tốn thời gian, tải hệ thống không cần thiết. | Retry chỉ lỗi thực sự tạm thời, có giới hạn và deadline. |
| Bỏ qua symlink/`..` từ tên file người dùng | Có thể đọc/ghi ngoài thư mục cho phép. | Bảo vệ path và kiểm soát filesystem theo mô hình tin cậy. |

## 13. Quy trình chẩn đoán thực tế

Khi người dùng báo “Không đọc được file”:

1. **Xác định thao tác:** đọc, ghi, append, di chuyển hay xóa? File nào theo cấu hình? Đường dẫn có tương đối không?
2. **Lấy exception cụ thể:** `NoSuchFileException`, `AccessDeniedException`, `CharacterCodingException` hay `IOException` khác? Ghi nhận cause mà không lộ nội dung nhạy cảm.
3. **Đọc path và quyền đúng môi trường:** process chạy dưới user nào, working directory nào, quyền file/thư mục/mount nào? Không suy từ quyền tài khoản đang đăng nhập IDE.
4. **Nếu file mở được nhưng nội dung lỗi:** xác định charset theo nguồn; kiểm tra byte/BOM/line ending theo schema; dùng decoder nghiêm ngặt.
5. **Kiểm tra dung lượng và luồng xử lý:** file quá lớn hay lỗi xuất hiện giữa lúc stream? Có cleanup và chính sách xử lý một phần không?
6. **Sửa đúng lớp:** cập nhật cấu hình path, quyền hệ thống, đặc tả encoding hoặc logic validate; không sửa bằng default trống cho mọi lỗi.
7. **Viết test tái hiện:** file thiếu, byte malformed, UTF-8 tiếng Việt và test permission trong môi trường kiểm soát được.
8. **Đo lại:** khi sửa, xác nhận output, số lỗi theo nhóm, không gây mất nội dung file cũ.

## 14. Bài tự luyện

**Bài 1 — Encoding:** chạy `TextFileErrorsDemo`, giải thích vì sao `0xC3 0x28` không phải UTF-8 hợp lệ. Thử bỏ một byte và quan sát lỗi. Nếu đổi decoder sang `REPLACE`, giải thích vì sao kết quả không còn nguyên vẹn và khi nào chính sách đó bị cấm.

**Bài 2 — Đường dẫn:** giải thích tại sao `Path.of("data/input.txt")` chạy được trong IDE nhưng lỗi khi chạy `java -jar` từ thư mục khác. Đề xuất cách truyền thư mục dữ liệu bằng cấu hình mà không hard-code path cá nhân.

**Bài 3 — Permission:** giả sử ứng dụng chạy trong container với volume chỉ đọc. Xác định thao tác nào có thể thành công, thao tác nào có thể bị từ chối và những thông tin cần kiểm tra trong log/config; không giả định exception luôn giống nhau trên mọi OS.

**Bài 4 — Ghi an toàn:** tạo file `result.txt` bằng `CREATE_NEW`. Ghi lần thứ hai phải thất bại nếu file đã có; giải thích tại sao `Files.exists` + `writeString` mặc định không bảo vệ chống race và mất dữ liệu.

**Bài 5 — Streaming:** chuyển đọc file text lớn từ `Files.readString` sang `BufferedReader`, thêm giới hạn số dòng/kích thước và phân biệt lỗi lúc mở với lỗi ở dòng N. Chọn hành vi rollback hoặc partial import phù hợp nghiệp vụ.

**Bài 6 — Kịch bản tổng hợp:** API nhận một file UTF-8 ở đường dẫn do người dùng cung cấp. Hãy vẽ ba tầng bảo vệ gồm **path được phép → quyền mở file → charset/schema hợp lệ**, phân loại lỗi thành mã trả về có nghĩa và liệt kê những thông tin không được đưa vào log.

## 15. Tài liệu chuẩn và ghi nhớ

- [Java SE 11 — Files](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html): `readString`, `writeString`, `newBufferedReader`, `lines`, `exists`, `isReadable`, các option đọc/ghi.
- [Java SE 11 — NoSuchFileException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/NoSuchFileException.html): file không tồn tại.
- [Java SE 11 — AccessDeniedException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/AccessDeniedException.html): thao tác filesystem bị từ chối.
- [Java SE 11 — CharsetDecoder](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/charset/CharsetDecoder.html): điều khiển hành vi đối với input malformed/unmappable.

**Ghi nhớ:** Khi text file có lỗi, hãy tách vấn đề **đường dẫn**, **quyền**, **I/O** và **giải mã**. Với Java 11, dùng `Path` và `Files` cùng charset tường minh; bắt exception ở thao tác thực tế, giữ nguyên nguyên nhân, kiểm thử lỗi có thể tái hiện và chỉ fallback khi hợp đồng nghiệp vụ cho phép. Đây là cách xử lý vẫn phù hợp cho ứng dụng Java hiện nay.