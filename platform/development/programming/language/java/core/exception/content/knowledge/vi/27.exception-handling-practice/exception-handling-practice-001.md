# Xây dựng quy trình đọc file có kiểm tra dữ liệu đầu vào — Java Core Exception

## 1. Mục tiêu và đầu ra thực hành

Bài này xây dựng một quy trình **nhận tên tệp từ người dùng, kiểm tra dữ liệu đầu vào, đọc nội dung văn bản UTF-8 và báo lỗi có ý nghĩa** bằng Java 17+. Trọng tâm là ranh giới giữa **lỗi validation** và **lỗi I/O thực tế**, cách bảo toàn <code>cause</code>, và cách tránh dùng những phép kiểm tra trước như lời bảo đảm sai lầm rằng thao tác đọc chắc chắn thành công.

Hoàn thành bài học, bạn có thể:

- Vẽ luồng từ **input thô → validation → xác định tài nguyên → mở file → đọc/giải mã → kết quả hoặc lỗi**.
- Kiểm tra <code>null</code>, chuỗi rỗng, ký tự không được phép, đuôi file và quy tắc đặt tên.
- Hạn chế tên file tương đối về một thư mục gốc được ứng dụng kiểm soát; hiểu vấn đề path traversal, symbolic link và TOCTOU.
- Phân biệt <code>IllegalArgumentException</code>, <code>InvalidPathException</code>, <code>NoSuchFileException</code>, <code>AccessDeniedException</code>, <code>CharacterCodingException</code>, <code>IOException</code> và lỗi nghiệp vụ đã được chuyển đổi.
- Dùng <code>try-with-resources</code> để đóng stream kể cả khi đọc hoặc giải mã thất bại.
- Áp dụng giới hạn byte được đọc thay vì tin một precheck kích thước file là đủ.
- Báo lỗi theo mã/loại ổn định, giữ cause để chẩn đoán và không gửi message kỹ thuật thô cho người dùng.
- Chạy một ví dụ Java 17 độc lập, có dữ liệu mẫu được tạo tự động, stdout xác định và không cần tệp chuẩn bị sẵn.
- Thiết kế các test cho nhánh thành công, dữ liệu đầu vào sai, lỗi encoding và lỗi I/O bị giả lập.

**Giới hạn bảo mật:** chương trình thực hành dùng một thư mục tạm do chính chương trình tạo và chỉ chấp nhận **tên file đơn**, không có thư mục con. Nó có kiểm tra ký tự và tránh đi theo symbolic link ở thành phần file cuối trên hệ thống file hỗ trợ. Đây là ví dụ học cơ chế exception và kiểm tra đầu vào; **không phải sandbox chống mọi thao tác đồng thời của kẻ tấn công có quyền sửa thư mục gốc**. Các trường hợp thư mục cha bị thay thế, mount point, file provider đặc biệt và đối tượng file bị thay đổi giữa các bước cần thiết kế bảo mật/đồng bộ hóa nâng cao riêng.

## 2. Yêu cầu của quy trình

Giả sử ứng dụng cho phép người dùng chọn tên một tệp ghi chú, chẳng hạn <code>notes.txt</code>, từ một thư mục do ứng dụng quản lý.

Quy tắc của bài thực hành:

1. Người dùng chỉ nhập **một tên file**, không phải đường dẫn đầy đủ và không được chuyển sang thư mục con.
2. Chỉ đọc file đuôi chính xác <code>.txt</code>, phân biệt chữ hoa/chữ thường theo hợp đồng ví dụ.
3. Tên file bắt đầu bằng ký tự chữ hoặc số ASCII; các ký tự tiếp theo trước phần mở rộng chỉ có chữ, số, dấu chấm, gạch dưới hoặc gạch ngang.
4. File phải là tệp thông thường, không phải thư mục hoặc symbolic link ở vị trí đích.
5. Mỗi file được đọc tối đa **1.024 byte** trong ví dụ để giới hạn bộ nhớ dành cho nội dung.
6. Nội dung là UTF-8 **hợp lệ**, không âm thầm thay byte sai bằng ký tự thay thế.
7. Khi có lỗi, caller nhận một exception có <code>code</code> rõ ràng; với lỗi từ hệ thống file/decoder, <code>cause</code> được giữ.
8. Tài nguyên stream phải đóng dù đọc thành công hay thất bại.
9. Phần trình bày public chỉ dùng mã lỗi và thông điệp an toàn, không lấy nguyên đường dẫn/exception message kỹ thuật.

Các quy tắc trên là **quyết định hợp đồng của bài học**, không phải luật chung của Java. Ứng dụng khác có thể cho phép nhiều thư mục con, tên Unicode, kích thước lớn hơn hoặc định dạng file khác, miễn là kiểm tra và chính sách truy cập tương ứng được thiết kế rõ ràng.

## 3. Luồng xử lý tổng thể

~~~text
Input String fileName
        |
        v
Kiểm tra null / blank / đuôi / ký tự được phép
        |
        +---- không hợp lệ ------> ReadFailure(INVALID_NAME / UNSUPPORTED_TYPE)
        |
        v
Xác định target = trustedBaseDir.resolve(fileName)
        |
        v
Kiểm tra sơ bộ loại tệp, không theo symlink của tệp cuối
        |
        +---- là thư mục/symlink -> ReadFailure(NOT_REGULAR_FILE)
        |
        v
Mở stream để đọc, try-with-resources
        |
        +---- không tồn tại -----> ReadFailure(NOT_FOUND, cause)
        +---- không đủ quyền ---> ReadFailure(ACCESS_DENIED, cause)
        +---- lỗi I/O khác -----> ReadFailure(READ_FAILED, cause)
        |
        v
Đọc tối đa MAX_BYTES + 1
        |
        +---- vượt giới hạn ----> ReadFailure(TOO_LARGE)
        |
        v
Giải mã UTF-8 ở chế độ REPORT
        |
        +---- byte sai ----------> ReadFailure(INVALID_UTF8, cause)
        |
        v
Trả về String thành công
~~~

**Vì sao cần tách các giai đoạn?** Lỗi nhập tên file là một tình huống mà code có thể phát hiện **trước I/O**, trong khi file không tồn tại, bị từ chối quyền truy cập hoặc biến mất do race chỉ được xác định đáng tin cậy bằng thao tác thực tế. Mỗi nhóm lỗi cần chính sách báo cáo khác nhau.

## 4. Phân loại lỗi trước khi viết code

| Mã lỗi ví dụ | Nguồn gốc | Ý nghĩa |
| --- | --- | --- |
| <code>INVALID_NAME</code> | Validation | Chuỗi tên file rỗng hoặc chứa đường dẫn/ký tự ngoài quy tắc |
| <code>UNSUPPORTED_TYPE</code> | Validation | Đuôi file không phải <code>.txt</code> |
| <code>NOT_REGULAR_FILE</code> | Chính sách tài nguyên | Đích được biết là thư mục, symbolic link hoặc loại không cho phép |
| <code>NOT_FOUND</code> | File system | Không mở được file vì đường dẫn không tồn tại |
| <code>ACCESS_DENIED</code> | File system | Hệ thống từ chối quyền truy cập |
| <code>TOO_LARGE</code> | Giới hạn đầu vào | Nội dung vượt số byte tối đa được phép đọc |
| <code>INVALID_UTF8</code> | Decoder | Byte trong file không tạo thành chuỗi UTF-8 hợp lệ |
| <code>READ_FAILED</code> | File system/stream | Lỗi I/O khác không nằm trong các trường hợp cụ thể trên |

**Không suy diễn:** một file chưa từng tồn tại và một file vừa bị xóa trước lúc mở có thể cho cùng <code>NoSuchFileException</code>. Ngược lại, một phép kiểm tra tồn tại trước khi mở có thể trả kết quả lỗi thời hoặc không kết luận được. Code phải dựa trên **hợp đồng của thao tác thật**.

Nếu sản phẩm cần biết chính xác tình trạng tài nguyên tại một thời điểm đồng thời, có thể cần cơ chế quản lý phiên bản/file handle/transaction riêng; chỉ phân loại exception không giải quyết vấn đề đó.

## 5. Kiểm tra null, blank và tên file

### 5.1. Null không giống chuỗi rỗng

~~~java
if (fileName == null || fileName.isBlank()) {
    throw new IllegalArgumentException("Tên file không được trống");
}
~~~

Đây là **mã minh họa** trong phương thức có biến <code>fileName</code> kiểu <code>String</code>. Biểu thức <code>||</code> có đánh giá ngắn mạch nên không gọi <code>isBlank()</code> khi <code>fileName == null</code>.

Các đầu vào cần cân nhắc gồm:

- <code>null</code>.
- <code>""</code>, <code>"   "</code> hoặc chuỗi chỉ chứa ký tự whitespace.
- <code>"notes.txt"</code> hợp lệ.
- <code>"../secret.txt"</code> dùng thành phần thư mục cha.
- <code>"sub/notes.txt"</code> chứa đường dẫn tương đối nhiều thành phần.
- <code>"C:\\private\\notes.txt"</code> kiểu đường dẫn Windows.
- <code>"notes.csv"</code> sai loại file theo chính sách bài.
- Chuỗi rất dài, chứa ký tự điều khiển hoặc ký tự bất hợp lệ theo file system.

Ví dụ chọn **allowlist** tên file thay vì cố liệt kê mọi ký tự nguy hiểm. Điều này có thể loại trừ một số tên file hoàn toàn hợp lệ trên hệ điều hành; đó là hệ quả có chủ đích của quy tắc bài thực hành.

### 5.2. Validation không phải biến một đường dẫn bất kỳ thành “an toàn”

Một ý tưởng đơn giản nhưng nguy hiểm:

~~~java
Path target = baseDir.resolve(userInput);
~~~

Đây là **mã minh họa**, yêu cầu import <code>java.nio.file.Path</code>. Nếu <code>userInput</code> chứa <code>..</code> hoặc là đường dẫn tuyệt đối, kết quả có thể không còn nằm trong thư mục mong muốn. Chuẩn hóa và kiểm tra ranh giới đường dẫn cần được thiết kế ngay từ đầu.

Với bài chỉ cần **một tên file**, cho phép ký tự trong một pattern chặt thường đơn giản hơn việc xử lý tùy ý mọi thành phần đường dẫn:

~~~java
if (!fileName.matches("[A-Za-z0-9][A-Za-z0-9._-]*\\.txt")) {
    throw new IllegalArgumentException("Tên file không hợp lệ");
}
~~~

Đây là **mã minh họa**. Quy tắc trên chấp nhận <code>note_01.txt</code> và từ chối dấu gạch chéo, dấu gạch chéo ngược cùng các trường hợp có thành phần thư mục cha. Nếu cần tên file Unicode, hãy xác định rõ bộ ký tự và giới hạn mới, không đơn giản bỏ mọi kiểm tra.

### 5.3. Thứ tự kiểm tra ảnh hưởng mã lỗi

Nếu tên là <code>notes.csv</code>, ví dụ muốn trả <code>UNSUPPORTED_TYPE</code>. Nếu tên là <code>../secret.txt</code>, ví dụ muốn trả <code>INVALID_NAME</code>. Vì vậy, pipeline chọn:

1. Kiểm tra null/blank.
2. Nếu tên không kết thúc bằng <code>.txt</code>, báo unsupported type.
3. Nếu tên tuy có đuôi <code>.txt</code> nhưng sai allowlist, báo invalid name.

Cách phân loại được công bố này giúp test xác định; ứng dụng khác có thể quyết định báo chung <code>INVALID_NAME</code> cho mọi đầu vào không hợp lệ nhằm giảm rò rỉ về chính sách.

## 6. Xử lý Path và InvalidPathException

Java NIO cung cấp <code>Path.of(...)</code> hoặc <code>Paths.get(...)</code>. Với chuỗi có ký tự không hợp lệ theo file system, thao tác tạo đường dẫn có thể ném <code>InvalidPathException</code>, là unchecked exception.

~~~java
try {
    Path supplied = Path.of(rawInput);
} catch (InvalidPathException e) {
    throw new IllegalArgumentException("Đường dẫn không hợp lệ", e);
}
~~~

Đây là **mã minh họa** với import <code>java.nio.file.Path</code> và <code>java.nio.file.InvalidPathException</code>. Không cần catch loại này trong demo có allowlist tên file rất chặt, nhưng trong API cho phép chuỗi path tự do, nên phân loại nó như lỗi input theo hợp đồng thay vì trả nguyên thông báo nội bộ cho người dùng.

### normalize và startsWith

Với ứng dụng cho phép đường dẫn tương đối nhiều thành phần, ví dụ:

~~~java
Path root = baseDir.toAbsolutePath().normalize();
Path supplied = Path.of(rawInput);

if (supplied.isAbsolute()) {
    throw new IllegalArgumentException("Chỉ cho phép đường dẫn tương đối");
}

Path target = root.resolve(supplied).normalize();

if (!target.startsWith(root)) {
    throw new IllegalArgumentException("Đường dẫn vượt thư mục gốc");
}
~~~

Đây là **đoạn minh họa**, giả định <code>baseDir</code> và <code>rawInput</code> đã được cung cấp. <code>Path.startsWith(Path)</code> kiểm tra theo các thành phần đường dẫn, không phải phép so chuỗi ký tự đơn giản.

**Giới hạn quan trọng:** kiểm tra trên đường dẫn đã normalize chỉ xử lý một phần nguy cơ *lexical traversal*. Symbolic link có thể trỏ sang vị trí bên ngoài dù đường dẫn biểu kiến nằm trong root. Hơn nữa, file hoặc symlink có thể bị thay thế giữa thời điểm kiểm tra và lúc mở. Một dịch vụ nhận đường dẫn từ nguồn không tin cậy phải bổ sung cơ chế xử lý symbolic link và race phù hợp môi trường, chứ không tuyên bố <code>normalize()</code> là “sandbox”.

Trong demo bên dưới, filename chỉ có một thành phần nên không chứa slash hoặc <code>..</code> đứng thành phần riêng. Đây là **giảm bề mặt rủi ro nhờ hợp đồng đầu vào**, không phải bằng chứng chống được mọi tấn công trên file system.

## 7. Vì sao không chỉ dùng Files.exists trước khi đọc?

Một đoạn code tưởng như an toàn:

~~~java
if (Files.exists(path)) {
    return Files.readString(path);
}
return "";
~~~

Đây là **mã minh họa**, yêu cầu import <code>java.nio.file.Files</code> và một phương thức xử lý <code>IOException</code> thích hợp. Nó có nhiều vấn đề:

- File có thể bị xóa hoặc đổi tên giữa <code>exists</code> và <code>readString</code>.
- Quyền truy cập có thể thay đổi.
- <code>exists</code> trả false không nhất thiết chứng minh file vĩnh viễn không tồn tại: truy vấn metadata có thể không kết luận được trong một số điều kiện.
- <code>readString</code> có thể thất bại vì encoding, bộ nhớ, thiết bị, permission hoặc lỗi I/O khác ngay cả khi precheck vừa thành công.
- Trả chuỗi rỗng cho “không tồn tại” sẽ lẫn với file thực sự tồn tại và chứa nội dung rỗng.

Phương án phù hợp là xem **thao tác đọc** như nguồn sự thật về thành công/thất bại, bắt các exception cụ thể mà caller cần phân biệt. Precheck như <code>Files.isRegularFile</code> có thể phục vụ trải nghiệm người dùng/chính sách, nhưng **không thay thế** xử lý lỗi khi mở.

~~~java
try {
    return Files.readString(path, StandardCharsets.UTF_8);
} catch (NoSuchFileException e) {
    throw new DocumentNotFoundException("Không tìm thấy tài liệu", e);
} catch (IOException e) {
    throw new DocumentReadException("Không thể đọc tài liệu", e);
}
~~~

Đây là **mã minh họa**; hai loại exception custom cần được định nghĩa trong dự án. Dùng constructor nhận <code>Throwable cause</code> giúp giữ lỗi gốc.

## 8. Kiểm tra loại file và symbolic link

Java NIO có:

- <code>Files.isRegularFile(path)</code>: thông thường theo symbolic link.
- <code>Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)</code>: yêu cầu không theo symbolic link ở đích khi lấy thông tin loại file.
- <code>Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)</code>: phân biệt thư mục theo cách tương ứng.
- <code>Files.isSymbolicLink(path)</code>: kiểm tra entry là symbolic link.
- <code>Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS)</code>: trên file system provider hỗ trợ option, tránh đi theo symbolic link ở entry file được mở.

Mỗi phép metadata check ở trên **không phải lock**. Nếu bên khác có quyền sửa file system, entry có thể thay đổi sau lúc check. Ở môi trường chịu tấn công race/symlink, cần đánh giá API mở file một cách ràng buộc, quyền OS, tính an toàn của thư mục gốc và có thể dùng <code>SecureDirectoryStream</code> khi provider hỗ trợ.

Trong chương trình thực hành, thư mục là một temp directory được tạo riêng và không có tác nhân khác sửa, vì vậy kiểm tra loại file trước khi mở chủ yếu dùng để có **mã lỗi dễ hiểu** như <code>NOT_REGULAR_FILE</code>. Code vẫn phải bắt <code>IOException</code> của việc mở thật.

### Symlink không phải thư mục thường

Một symbolic link có thể trỏ đến file thực nằm ngoài root. Không nên gọi <code>Files.readString</code> mặc định trên tên do người dùng điều khiển rồi tin rằng việc check <code>target.startsWith(root)</code> bảo đảm dữ liệu chỉ nằm dưới root.

Trong ví dụ, với filename đơn không có parent do người dùng cung cấp, <code>NOFOLLOW_LINKS</code> được dùng khi mở. Trong dịch vụ cho phép đường dẫn con và thư mục gốc có thể bị thay thế, **chỉ ngăn follow ở entry cuối chưa đủ**: những thành phần đường dẫn cha cũng phải được bảo vệ.

## 9. Đọc UTF-8: mặc định thay thế byte sai hay báo lỗi?

Một tệp đuôi <code>.txt</code> **không bảo đảm** nội dung là UTF-8 hợp lệ. Nếu hệ thống công bố “mọi nội dung phải là UTF-8 hợp lệ”, việc gặp byte sai phải trở thành lỗi dữ liệu, không bị tự động chuyển thành ký tự thay thế và coi như thành công.

Với Java NIO Charset API:

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

String content = decoder.decode(ByteBuffer.wrap(bytes)).toString();
~~~

Đây là **mã minh họa**; cần các import từ <code>java.nio</code> và <code>java.nio.charset</code>, biến <code>bytes</code> kiểu <code>byte[]</code> đã được cấp. Chế độ <code>REPORT</code> khiến dữ liệu mã hóa sai phát sinh <code>CharacterCodingException</code> (ví dụ <code>MalformedInputException</code>) thay vì âm thầm thay bằng ký tự U+FFFD.

Một số API đọc text cấp cao như <code>Files.readString(path, StandardCharsets.UTF_8)</code> cũng có thể ném <code>IOException</code> khi gặp dữ liệu UTF-8 sai. Bài demo sử dụng decoder tường minh để **làm rõ hợp đồng** và kết hợp với giới hạn số byte đọc.

### Byte limit khác với character limit

UTF-8 dùng từ một đến nhiều byte cho mỗi Unicode code point. Vì vậy:

- File 1.024 byte không nhất thiết chứa 1.024 ký tự Java.
- Số ký tự Java (UTF-16 code unit) cũng không phải số code point.
- Nếu giới hạn theo **byte** để bảo vệ việc đọc/bộ nhớ, kiểm tra **byte**, không chỉ độ dài sau khi giải mã.
- Nếu sản phẩm cần thêm giới hạn ký tự, kiểm tra sau khi đã xác định chính sách ký tự/Unicode.

Demo đặt <code>MAX_BYTES = 1024</code> và đọc tối đa <code>MAX_BYTES + 1</code>. Khi nhận 1.025 byte, kết luận vượt giới hạn. Nó không dựa vào riêng <code>Files.size()</code>, vốn chỉ là snapshot metadata có thể thay đổi.

## 10. Try-with-resources: đóng stream ở mọi đường

Ví dụ:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    byte[] bytes = input.readNBytes(1025);
    return decoder.decode(ByteBuffer.wrap(bytes)).toString();
}
~~~

Đây là **mã minh họa** trong một phương thức có các biến và exception contract phù hợp. Cú pháp <code>try-with-resources</code> gọi <code>close()</code> khi rời khối, bao gồm khi:

- Đọc xong bình thường.
- <code>readNBytes</code> ném <code>IOException</code>.
- Decoder ném <code>CharacterCodingException</code>.
- Code tự ném exception do vượt giới hạn.
- Code xử lý bên trong trả về sớm.

Nếu cả thao tác chính và đóng stream cùng lỗi, Java giữ lỗi đóng ở danh sách <code>getSuppressed()</code> của exception chính theo hợp đồng try-with-resources. Khi chuyển sang exception tầng ứng dụng, nên giữ cause để không vô tình mất thông tin này.

**Không dùng <code>finally</code> có thể ném exception mới không kiểm soát** rồi làm lỗi gốc bị che. Try-with-resources giúp quản lý quan hệ lỗi chính/lỗi đóng đáng tin cậy hơn khi tài nguyên là <code>AutoCloseable</code>.

## 11. Chương trình Java 17+ hoàn chỉnh: ValidatedFileReadDemo

Chương trình này:

1. Tạo một thư mục tạm riêng.
2. Tạo một file UTF-8 hợp lệ, một file rỗng, một file chứa byte UTF-8 sai, một file vượt giới hạn và một thư mục mang tên đuôi <code>.txt</code>.
3. Thử đọc các đầu vào hợp lệ/sai và in mã lỗi rõ ràng.
4. Giữ nguyên cause khi lỗi đến từ hệ thống file hoặc decoder.
5. Xóa dữ liệu thử nghiệm sau khi chạy.

Lưu **toàn bộ** vào file <code>ValidatedFileReadDemo.java</code>:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;

public class ValidatedFileReadDemo {
    private static final int MAX_BYTES = 1024;

    enum Code {
        INVALID_NAME,
        UNSUPPORTED_TYPE,
        NOT_REGULAR_FILE,
        NOT_FOUND,
        ACCESS_DENIED,
        TOO_LARGE,
        INVALID_UTF8,
        READ_FAILED
    }

    static final class ReadFailure extends Exception {
        private final Code code;

        ReadFailure(Code code, String message) {
            super(message);
            this.code = code;
        }

        ReadFailure(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        Code code() {
            return code;
        }
    }

    static String readText(Path trustedRoot, String name)
            throws ReadFailure {
        if (name == null || name.isBlank()) {
            throw new ReadFailure(
                    Code.INVALID_NAME, "Tên file không được trống");
        }
        if (!name.endsWith(".txt")) {
            throw new ReadFailure(
                    Code.UNSUPPORTED_TYPE, "Chỉ hỗ trợ .txt");
        }
        if (!name.matches("[A-Za-z0-9][A-Za-z0-9._-]*\\.txt")) {
            throw new ReadFailure(
                    Code.INVALID_NAME, "Tên file có ký tự không hợp lệ");
        }

        Path target = trustedRoot.resolve(name);

        // Chỉ là kiểm tra phân loại tiện lợi, không thay cho open().
        if (Files.exists(target, LinkOption.NOFOLLOW_LINKS)
                && !Files.isRegularFile(
                        target, LinkOption.NOFOLLOW_LINKS)) {
            throw new ReadFailure(
                    Code.NOT_REGULAR_FILE, "Đích không phải file thường");
        }

        try (InputStream input =
                Files.newInputStream(target, LinkOption.NOFOLLOW_LINKS)) {
            byte[] bytes = input.readNBytes(MAX_BYTES + 1);
            if (bytes.length > MAX_BYTES) {
                throw new ReadFailure(
                        Code.TOO_LARGE, "File vượt giới hạn byte");
            }

            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new ReadFailure(
                    Code.INVALID_UTF8, "File không phải UTF-8 hợp lệ", e);
        } catch (NoSuchFileException e) {
            throw new ReadFailure(
                    Code.NOT_FOUND, "Không tìm thấy file", e);
        } catch (AccessDeniedException e) {
            throw new ReadFailure(
                    Code.ACCESS_DENIED, "Không có quyền đọc file", e);
        } catch (IOException e) {
            throw new ReadFailure(
                    Code.READ_FAILED, "Không thể đọc file", e);
        }
    }

    static void show(Path root, String name) {
        String label = name == null ? "<null>" : "\"" + name + "\"";

        try {
            String content = readText(root, name);
            System.out.println(label + " -> OK ["
                    + content.strip() + "]");
        } catch (ReadFailure error) {
            System.out.println(label + " -> " + error.code());
        }
    }

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("file-read-practice-");

        try {
            Files.writeString(
                    root.resolve("ok.txt"),
                    "Xin chào\n",
                    StandardCharsets.UTF_8);
            Files.writeString(
                    root.resolve("empty.txt"),
                    "",
                    StandardCharsets.UTF_8);
            Files.write(
                    root.resolve("invalid.txt"),
                    new byte[] {(byte) 0xC3, (byte) 0x28});
            Files.write(
                    root.resolve("big.txt"),
                    new byte[MAX_BYTES + 1]);
            Files.createDirectory(root.resolve("folder.txt"));

            show(root, "ok.txt");
            show(root, "empty.txt");
            show(root, "missing.txt");
            show(root, "folder.txt");
            show(root, "invalid.txt");
            show(root, "big.txt");
            show(root, "note.csv");
            show(root, "../secret.txt");
            show(root, null);
        } finally {
            Files.deleteIfExists(root.resolve("ok.txt"));
            Files.deleteIfExists(root.resolve("empty.txt"));
            Files.deleteIfExists(root.resolve("invalid.txt"));
            Files.deleteIfExists(root.resolve("big.txt"));
            Files.deleteIfExists(root.resolve("folder.txt"));
            Files.deleteIfExists(root);
        }
    }
}
~~~

Biên dịch/chạy với Java 17+:

~~~bash
javac -encoding UTF-8 ValidatedFileReadDemo.java
java ValidatedFileReadDemo
~~~

**Stdout kỳ vọng trên file system thông thường có hỗ trợ các thao tác thử nghiệm:**

~~~text
"ok.txt" -> OK [Xin chào]
"empty.txt" -> OK []
"missing.txt" -> NOT_FOUND
"folder.txt" -> NOT_REGULAR_FILE
"invalid.txt" -> INVALID_UTF8
"big.txt" -> TOO_LARGE
"note.csv" -> UNSUPPORTED_TYPE
"../secret.txt" -> INVALID_NAME
<null> -> INVALID_NAME
~~~

### 11.1. Vì sao output có thứ tự xác định?

Mọi lời gọi <code>show(...)</code> được thực hiện tuần tự từ <code>main</code>, không dùng thread pool hoặc bất đồng bộ. Không có file đầu vào nào phụ thuộc vào thư mục làm việc của người chạy, vì tất cả dữ liệu thử đều được tạo trong temp directory trước khi test.

Với file system thông thường có thể tạo/xóa file, cho phép mở file tạm và hỗ trợ <code>NOFOLLOW_LINKS</code>, các kết quả trên có thể dự đoán được. **Không khẳng định** đây là output khi hệ điều hành từ chối tạo thư mục tạm, ổ đĩa hết dung lượng, provider không hỗ trợ option, hoặc một tiến trình khác cố ý thay đổi thư mục trong lúc chương trình chạy. Những tình huống đó là lỗi hạ tầng ngoài kịch bản kiểm thử thường.

### 11.2. Từng dòng thể hiện điều gì?

- <code>"ok.txt"</code>: tên hợp lệ, file có thể mở, kích thước nhỏ, UTF-8 hợp lệ. <code>strip()</code> ở <code>show</code> chỉ loại whitespace đầu/cuối **khi hiển thị demo**; hàm <code>readText</code> vẫn trả nội dung gốc gồm ký tự newline.
- <code>"empty.txt"</code>: file tồn tại và rỗng vẫn là **đọc thành công**, không bị nhầm với <code>NOT_FOUND</code>.
- <code>"missing.txt"</code>: tên được phép nhưng file không có; mở stream ném <code>NoSuchFileException</code>, được chuyển sang <code>NOT_FOUND</code>.
- <code>"folder.txt"</code>: entry tồn tại nhưng là thư mục; kiểm tra <code>isRegularFile(..., NOFOLLOW_LINKS)</code> dẫn tới <code>NOT_REGULAR_FILE</code>.
- <code>"invalid.txt"</code>: chuỗi byte <code>C3 28</code> không hợp lệ theo UTF-8; decoder ở chế độ REPORT tạo <code>CharacterCodingException</code>, được chuyển sang <code>INVALID_UTF8</code>.
- <code>"big.txt"</code>: có 1.025 byte trong khi giới hạn cho phép là 1.024, nên trả <code>TOO_LARGE</code> trước giải mã.
- <code>"note.csv"</code>: thất bại ở validation loại file, không thử đọc.
- <code>"../secret.txt"</code>: có đuôi .txt nhưng không khớp allowlist, nên thất bại trước khi tạo target.
- <code>null</code>: thất bại ở validation null, không truy cập file system.

### 11.3. Byte giới hạn được kiểm tra sau khi mở

Hàm dùng:

~~~java
byte[] bytes = input.readNBytes(MAX_BYTES + 1);
if (bytes.length > MAX_BYTES) {
    throw new ReadFailure(Code.TOO_LARGE, "File vượt giới hạn byte");
}
~~~

Đây là **đoạn minh họa được trích từ chương trình**. Nó không chỉ đọc metadata <code>Files.size()</code> rồi giả định kích thước sẽ không đổi. Với mục tiêu giới hạn lượng dữ liệu **được tích lũy vào mảng**, việc đọc tối đa thêm một byte cho phép nhận biết trường hợp vượt ngưỡng.

Giới hạn này không phải quota toàn bộ tài nguyên hệ thống: việc mở file, allocation khác, các bộ đệm nội bộ và tải song song vẫn tiêu thụ tài nguyên. Khi xử lý tệp lớn, streaming, timeout, cancellation, quota theo request và quản lý concurrent requests cần được thiết kế bổ sung.

### 11.4. Việc loại symbolic link trong ví dụ có giới hạn

- Allowlist không cho người dùng nhập thư mục con hoặc path traversal bằng dấu gạch chéo.
- Kiểm tra <code>isRegularFile(..., NOFOLLOW_LINKS)</code> có thể từ chối symbolic link ở đích khi check nhìn thấy nó.
- <code>newInputStream(target, NOFOLLOW_LINKS)</code> được dùng để yêu cầu không theo symlink ở đích khi mở, theo mức hỗ trợ của provider.
- Nhưng <code>trustedRoot</code> phải thật sự là thư mục do ứng dụng kiểm soát. Nếu một bên khác có thể thay root hoặc namespace file system, chính sách chống race/symlink phải chặt hơn.

**Không dùng code demo như một sandbox bảo mật hoàn chỉnh** cho dịch vụ có người dùng không tin cậy được phép tạo/sửa symlink trong cấu trúc thư mục.

## 12. Bảo toàn cause và không đưa lỗi kỹ thuật thô ra client

Trong chương trình, khi mở không thấy file:

~~~java
} catch (NoSuchFileException e) {
    throw new ReadFailure(
            Code.NOT_FOUND, "Không tìm thấy file", e);
}
~~~

Đây là **đoạn minh họa trong chuỗi catch**. Vì constructor <code>ReadFailure(..., Throwable cause)</code> gọi <code>super(message, cause)</code>, tầng trên có thể dùng:

~~~java
ReadFailure error = ...;
Throwable cause = error.getCause();
~~~

Đây là **mã minh họa**, biến <code>error</code> phải được lấy từ một khối catch hoặc kết quả test phù hợp. <code>getCause()</code> có thể là null với lỗi validation, và khác null với lỗi đọc được chuyển từ exception của Java NIO.

### Ba nhóm dữ liệu cần phân biệt

| Thành phần | Mục đích | Có thể gửi thẳng tới người dùng? |
| --- | --- | --- |
| <code>ReadFailure.code()</code> | Phân loại ổn định cho caller | Có thể, nếu thuộc hợp đồng public |
| <code>ReadFailure.getMessage()</code> | Diễn đạt lỗi ở tầng ứng dụng | Chỉ khi nội dung đã được duyệt là an toàn |
| <code>ReadFailure.getCause()</code> | Chẩn đoán lỗi kỹ thuật, stack trace | Thường không; phải theo chính sách truy cập/log |
| <code>target Path</code> | File thực trên hệ thống | Không tự động; có thể lộ cấu trúc thư mục |
| <code>requestId</code> | Tra cứu sự cố từ phía hỗ trợ | Có thể nếu định dạng không chứa secret/PII |

Một API thực tế có thể ánh xạ:

~~~json
{
  "code": "FILE_UNAVAILABLE",
  "message": "Không thể đọc tệp lúc này. Vui lòng thử lại sau.",
  "requestId": "RQ-1234"
}
~~~

Đây là **JSON minh họa**, không phải server HTTP có thể chạy từ ví dụ. Thông báo public không đưa đường dẫn OS, hostname, stack trace hoặc token lấy từ exception message gốc.

### Không gộp mọi lỗi vào “Không tìm thấy”

Nếu đọc file bị từ chối quyền truy cập hoặc encoding sai, trả <code>NOT_FOUND</code> có thể khiến người dùng/ứng dụng đưa ra quyết định sai. Việc phân loại chi tiết ở tầng nội bộ không bắt buộc công bố mọi thông tin kỹ thuật, nhưng giúp log và chương trình xử lý đúng.

Có hệ thống cố tình không phân biệt <code>NOT_FOUND</code> và <code>ACCESS_DENIED</code> trong **public response** nhằm tránh tiết lộ thông tin tài nguyên. Đây là quyết định security boundary; trong nội bộ vẫn cần phân biệt nguyên nhân khi phù hợp.

## 13. Kiểm thử không dựa vào file system thật để mô phỏng IOException

Ví dụ ở mục 11 phù hợp cho **smoke test tích hợp** với file system. Nhưng khi cần kiểm tra đúng logic chuyển exception, việc cố thay quyền của một file thật trên máy chạy CI có thể thiếu ổn định:

- Windows, Linux và file system khác nhau về quyền.
- Process test có thể chạy với quyền quản trị và không bị chặn như dự đoán.
- Antivirus, agent backup, race hoặc mount lạ có thể ảnh hưởng kết quả.
- Không nên thao tác lên file thực của người dùng chỉ để làm test.

Thay vào đó, tách thao tác I/O qua một interface có thể giả lập để kiểm tra việc giữ cause và phân loại lỗi.

### Ví dụ Java 17 độc lập: fake reader ném IOException xác định

Lưu tệp **ReadFailureCauseDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.NoSuchFileException;

public class ReadFailureCauseDemo {
    interface Reader {
        String read(String name) throws IOException;
    }

    enum Code {
        NOT_FOUND,
        READ_FAILED
    }

    static final class LoadFailure extends Exception {
        private final Code code;

        LoadFailure(Code code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        Code code() {
            return code;
        }
    }

    static String load(Reader reader, String name) throws LoadFailure {
        try {
            return reader.read(name);
        } catch (NoSuchFileException e) {
            throw new LoadFailure(
                    Code.NOT_FOUND, "Không tìm thấy tài liệu", e);
        } catch (IOException e) {
            throw new LoadFailure(
                    Code.READ_FAILED, "Không thể đọc tài liệu", e);
        }
    }

    static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Exception contract failed");
        }
    }

    public static void main(String[] args) {
        NoSuchFileException original =
                new NoSuchFileException("missing.txt");
        Reader missing = name -> {
            throw original;
        };
        Reader working = name -> "CONTENT";

        try {
            load(missing, "missing.txt");
            throw new AssertionError("Expected LoadFailure");
        } catch (LoadFailure e) {
            require(e.code() == Code.NOT_FOUND);
            require(e.getCause() == original);
            System.out.println("Missing code: " + e.code());
            System.out.println("Same original cause: "
                    + (e.getCause() == original));
        }

        try {
            System.out.println("Working result: "
                    + load(working, "ok.txt"));
        } catch (LoadFailure e) {
            throw new AssertionError("Unexpected failure", e);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ReadFailureCauseDemo.java
java ReadFailureCauseDemo
~~~

**Stdout chính xác:**

~~~text
Missing code: NOT_FOUND
Same original cause: true
Working result: CONTENT
~~~

Giải thích:

- <code>Reader</code> mô tả thao tác đọc có thể ném <code>IOException</code>.
- Fake <code>missing</code> ném **chính đối tượng** <code>NoSuchFileException</code> được tạo sẵn.
- <code>load</code> chuyển nó thành <code>LoadFailure</code> nhưng giữ cause nguyên bản.
- Test dùng <code>==</code> để xác nhận identity; trong JUnit 5, assertion tương ứng là <code>assertSame(original, e.getCause())</code>.
- Fake <code>working</code> minh họa nhánh thành công mà không cần tạo file thực.
- Đây là ví dụ để học **exception translation**, không phải bản thay thế cho bộ kiểm tra tên file và byte/encoding của demo chính.

## 14. Test cases cần có

| Input/tình huống | Kỳ vọng | Mục tiêu test |
| --- | --- | --- |
| <code>null</code> | <code>INVALID_NAME</code> | Guard null chạy trước các thao tác khác |
| Chuỗi rỗng hoặc blank | <code>INVALID_NAME</code> | Không mở I/O với tên vô nghĩa |
| Tên có <code>../</code> | <code>INVALID_NAME</code> | Không chấp nhận traversal qua tên file |
| Tên có slash/backslash | <code>INVALID_NAME</code> nếu đúng đuôi .txt | Không chấp nhận thư mục con theo policy |
| <code>note.csv</code> | <code>UNSUPPORTED_TYPE</code> | Phân biệt đuôi file sai |
| File <code>.txt</code> không tồn tại | <code>NOT_FOUND</code> | Phân loại NoSuchFileException |
| File rỗng | Chuỗi <code>""</code> thành công | Không đánh đồng rỗng với không tồn tại |
| File UTF-8 hợp lệ | Chuỗi đúng, không làm mất newline | Đọc và giải mã đúng |
| File chứa byte UTF-8 sai | <code>INVALID_UTF8</code> | Decoder dùng chế độ REPORT |
| File vượt 1.024 byte | <code>TOO_LARGE</code> | Không tích lũy không giới hạn |
| Một thư mục có tên đuôi .txt | <code>NOT_REGULAR_FILE</code> trong môi trường demo | Không coi directory là text file |
| Symlink ở file đích | Bị từ chối theo policy và provider tương ứng | Không vô tình theo symlink |
| Không đủ quyền | <code>ACCESS_DENIED</code> khi API ném AccessDeniedException | Không báo sai thành NOT_FOUND |
| Lỗi I/O khác | <code>READ_FAILED</code> | Có nhánh fallback giữ cause |
| Lỗi chuyển tầng | Cause identity được giữ | Không chỉ sao chép message |
| Close stream gặp lỗi | Lỗi đóng không bị im lặng mất | Tác dụng của try-with-resources |

### JUnit 5 minh họa

Trong một lớp test JUnit 5 với import và dữ liệu fixture phù hợp:

~~~java
ReadFailureCauseDemo.Reader failing = name -> {
    throw original;
};

ReadFailureCauseDemo.LoadFailure error =
        assertThrows(ReadFailureCauseDemo.LoadFailure.class,
                () -> ReadFailureCauseDemo.load(failing, "missing.txt"));

assertEquals(ReadFailureCauseDemo.Code.NOT_FOUND, error.code());
assertSame(original, error.getCause());
~~~

Đây là **mã minh họa không độc lập**, cần biến <code>original</code> là một <code>NoSuchFileException</code> được tạo trong test. Dùng các assertion JUnit Jupiter tương ứng. Không dựa vào message hệ điều hành hay số dòng stack trace khi chỉ cần kiểm tra code và cause.

Một test validation có thể dùng fake ghi lại số lần đọc để khẳng định input sai **không làm phát sinh I/O**. Nhưng hãy đặt assertion theo hợp đồng của tầng validate, không phụ thuộc chi tiết implementation mà caller không cần.

## 15. Tách logic validation và logic đọc để dễ mở rộng

Khi code lớn hơn, có thể tổ chức:

~~~text
FileNameValidator
    -> ValidatedName
    -> FileRepository (đọc nội dung)
    -> FileReadService (chuyển lỗi/áp hợp đồng)
    -> API hoặc CLI response mapper
~~~

Đây là **sơ đồ thành phần gợi ý**, không bắt buộc tạo đúng các lớp đó cho bài tập nhỏ.

Một cấu trúc rõ trách nhiệm:

1. **Validation:** chỉ biết quy tắc tên/loại file, không biết lỗi disk.
2. **Repository:** nhận tên hợp lệ/Path nội bộ và thực hiện open/read/close, báo exception kỹ thuật.
3. **Service:** áp chính sách kích thước/encoding và chuyển exception theo contract của tính năng.
4. **Adapter/API:** biến mã lỗi thành response an toàn, ghi correlation ID hoặc log có kiểm soát.

Không nhất thiết luôn cần bốn lớp: có thể gộp trong chương trình nhỏ nhưng giữ **ranh giới trách nhiệm trong tư duy**.

### Phân biệt validation lỗi trước I/O và lỗi phát hiện khi đọc

Ví dụ “tên file rỗng” có thể được xác định chỉ từ chuỗi đầu vào. Nhưng “file tồn tại và có quyền đọc” cần thao tác trên file system. API muốn công bố một trạng thái cụ thể khi file được thay đổi đồng thời phải xử lý điều đó như tình huống thực, không ỷ lại các check lúc trước.

## 16. Các quyết định về charset và nội dung

UTF-8 là lựa chọn phổ biến, nhưng phải được **công bố**. Nếu nội dung thực tế do một hệ thống khác ghi bằng charset khác, việc đọc UTF-8 có thể lỗi hoặc cho text sai.

Các tình huống cần xem xét:

- File có hoặc không có BOM.
- Newline kiểu <code>\n</code>, <code>\r\n</code> hoặc <code>\r</code>.
- Chuỗi có dấu tiếng Việt và ký tự Unicode ngoài ASCII.
- Byte invalid theo UTF-8.
- Giới hạn số byte so với giới hạn số ký tự.
- File rất lớn phải đọc theo streaming thay vì một mảng.
- Dữ liệu nhị phân được ngụy trang bằng đuôi <code>.txt</code>.
- Chuỗi có ký tự điều khiển mà domain không chấp nhận dù UTF-8 hợp lệ.

**Ví dụ chính chỉ kiểm tra UTF-8 well-formed**, không xác định một ngữ pháp nội dung cụ thể. Một chuỗi UTF-8 hợp lệ vẫn có thể sai nghiệp vụ, chẳng hạn một file cấu hình thiếu trường bắt buộc. Nếu cần parse CSV/JSON hoặc định dạng dòng, hãy có bước **validation nội dung sau decode** với exception/error code riêng.

### Không tự động trim nội dung gốc

Trong demo, <code>show</code> gọi <code>strip()</code> để in gọn, nhưng <code>readText</code> trả nguyên chuỗi đã decode. Nếu service tự ý trim, có thể làm mất whitespace hoặc newline mang ý nghĩa. Chỉ chuẩn hóa line endings, dấu cách hoặc BOM nếu hợp đồng dữ liệu yêu cầu.

## 17. Khi nào nên dùng Files.readString và khi nào nên streaming?

### Dữ liệu nhỏ, tin cậy và không cần hạn mức byte chặt

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Đây là **mã minh họa**, có thể đơn giản và dễ đọc nếu size được kiểm soát ở cấp kiến trúc/nguồn tin cậy. Nhưng nó có thể cần phân bổ bộ nhớ tương ứng kích thước file, không phù hợp nếu người dùng có thể đưa một file cực lớn vào đường đọc.

### Dữ liệu có giới hạn tài nguyên rõ

Trong demo, <code>InputStream.readNBytes(MAX_BYTES+1)</code> bảo đảm không tích lũy nội dung vượt ngưỡng bằng thao tác đọc này. Nó phù hợp với file nhỏ cần load toàn bộ vào bộ nhớ.

### File lớn hoặc dữ liệu cần xử lý từng dòng

Có thể dùng <code>BufferedReader</code> hoặc streaming:

~~~java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

Đây là **mã minh họa**, cần import <code>java.io.BufferedReader</code>, <code>Files</code>, <code>StandardCharsets</code> và định nghĩa <code>process</code>. Nếu có giới hạn số byte, số dòng hoặc độ dài một dòng, vẫn phải **chủ động triển khai hạn mức**; chỉ dùng <code>BufferedReader</code> không tự áp mọi quota.

Nếu cần chặn symlink, chọn API mở có hỗ trợ chính sách đó hoặc quản lý file descriptor/đường dẫn bằng cơ chế phù hợp. Không đơn giản chuyển từ <code>newInputStream</code> sang <code>newBufferedReader</code> rồi mặc định mọi quyền/symlink option vẫn y nguyên.

## 18. Logging và thông báo lỗi an toàn

Một quy trình đọc file không nên dùng:

~~~java
catch (IOException e) {
    System.out.println("Lỗi: " + e);
    return "";
}
~~~

Đây là **mã minh họa cố ý không khuyến nghị**:

- Trả <code>""</code> gây nhầm với file thực sự rỗng.
- In exception kỹ thuật trực tiếp có thể làm lộ đường dẫn nội bộ nếu stdout được đưa tới người dùng.
- Caller không còn biết có thao tác thất bại.
- Message từ hệ thống file có thể không ổn định giữa OS/JDK và có thể chứa thông tin nhạy cảm.

Tốt hơn là giữ <code>ReadFailure</code> với code ổn định và cause, rồi một lớp presentation quyết định:

~~~java
String publicMessage(Code code) {
    return switch (code) {
        case INVALID_NAME -> "Tên tệp không hợp lệ.";
        case UNSUPPORTED_TYPE -> "Chỉ hỗ trợ tệp .txt.";
        case TOO_LARGE -> "Tệp vượt dung lượng được phép.";
        case INVALID_UTF8 -> "Tệp không đúng định dạng UTF-8.";
        case NOT_FOUND -> "Không tìm thấy tệp.";
        case NOT_REGULAR_FILE -> "Tài nguyên không phải tệp hợp lệ.";
        case ACCESS_DENIED, READ_FAILED ->
                "Không thể đọc tệp lúc này.";
    };
}
~~~

Đây là **mã minh họa** với enum <code>Code</code> của ví dụ chính. Hệ thống thật có thể cố ý gom một số loại lỗi vào thông báo chung để bảo vệ thông tin tài nguyên. Nếu người dùng sửa được input, một thông báo hữu ích sẽ tốt hơn việc trả một stack trace kỹ thuật.

### Trường nào nên đi vào log?

- Mã lỗi và tên thao tác ổn định.
- Request ID/correlation ID an toàn.
- Thời gian, thành phần, thời lượng.
- Loại Throwable/cause cho kỹ sư có quyền.
- Tên tài nguyên nếu được phép ghi theo chính sách dữ liệu.

Không ghi token, password, dữ liệu riêng tư hoặc raw file content vào log chỉ vì exception đang xảy ra. Đừng lặp cùng stack trace ở mọi tầng nếu không thêm thông tin mới.

## 19. Xử lý input và security boundary thực tế

Các thành phần thường cần xem xét khi xây dựng dịch vụ production:

**Giới hạn đường dẫn.** Tốt nhất, người dùng cung cấp một **file ID** hoặc tên theo allowlist; server ánh xạ ID sang vị trí mà nó quản lý. Không cho client tự truyền đường dẫn tuyệt đối tới những vùng hệ thống nhạy cảm.

**Quyền truy cập.** Một tên file hợp lệ vẫn có thể trỏ tới tài nguyên mà người dùng không được quyền đọc. Validation cú pháp không thay authorization.

**Symlink.** Lexical normalize/startsWith không chặn symlink escape. <code>NOFOLLOW_LINKS</code> ở entry cuối không bảo vệ mọi parent nếu người dùng được phép thao tác trên parent. Môi trường chịu tấn công cần mở file bằng cơ chế chặt hơn, ví dụ kiểm soát descriptor/thư mục và <code>SecureDirectoryStream</code> khi khả dụng.

**TOCTOU.** Metadata check và open là các thao tác khác nhau; attacker có thể thay entry giữa hai thời điểm. Tùy yêu cầu cần chiến lược kiểm tra sau khi mở hoặc cơ chế API/OS hỗ trợ atomicity tương ứng.

**Tài nguyên.** Hạn chế byte, số request đồng thời, tốc độ đọc, thời hạn, memory và không log file vô hạn. File có kích thước nhỏ không nhất thiết là nội dung an toàn để parse, render hoặc thực thi.

**Định dạng.** Đuôi <code>.txt</code> chỉ là chính sách filename. Nếu ứng dụng yêu cầu đúng một nội dung cụ thể, phải kiểm tra nội dung; không dùng đuôi file làm bằng chứng tuyệt đối.

**Lỗi trên file system.** Mã lỗi cụ thể phụ thuộc OS/provider; cùng nguyên nhân nghiệp vụ có thể được biểu diễn khác nhau bởi provider. Một đường xử lý chung <code>READ_FAILED</code> vẫn cần thiết, không chỉ catch một exception con.

**Thông báo cho người dùng.** Không công khai đường dẫn tuyệt đối, exception class, stack trace hoặc file bytes nếu không có quyền. Khi debug, dùng mã tham chiếu an toàn để đối chiếu log.

## 20. Các lỗi thường gặp

1. **Chỉ check <code>fileName != null</code>:** chuỗi blank và path traversal vẫn lọt.
2. **Nối chuỗi đường dẫn trực tiếp:** dễ sai separator và vô tình cho phép truy cập ngoài root.
3. **Tin rằng <code>normalize()</code> chặn mọi symlink:** chỉ xử lý hình thức đường dẫn, không tự bảo đảm file thực.
4. **Dùng <code>Files.exists</code> như bảo đảm open sẽ thành công:** gặp race, permission và lỗi I/O khác.
5. **Trả chuỗi rỗng cho mọi lỗi:** không phân biệt file rỗng, không tồn tại, invalid UTF-8 hoặc access denied.
6. **Bắt <code>Exception</code> rồi trả mặc định:** nuốt bug và có thể che cả các lỗi không nên coi là validation.
7. **Bắt <code>IOException</code> trước mọi subtype cần phân loại:** trong Java, catch subtype phía sau superclass sẽ không hợp lệ/không tới được.
8. **Bỏ cause khi chuyển lỗi:** không thể đối chiếu exception gốc hay chẩn đoán nguồn.
9. **Quên đóng stream nếu decoder ném lỗi:** dùng try-with-resources.
10. **Chỉ dựa vào <code>Files.size()</code>:** metadata có thể thay đổi và không tự giới hạn số byte đã đọc.
11. **Cho rằng UTF-8 luôn hợp lệ vì đuôi .txt:** phải decode theo charset được công bố.
12. **Âm thầm thay byte sai bằng ký tự thay thế:** có thể che dữ liệu hỏng nếu yêu cầu strict UTF-8.
13. **Dùng <code>String.length()</code> làm hạn mức byte:** UTF-8 và UTF-16 có cách đếm khác nhau.
14. **Đọc toàn bộ file không giới hạn vào bộ nhớ:** có nguy cơ làm cạn tài nguyên.
15. **Trim nội dung không theo hợp đồng:** có thể làm mất khoảng trắng/newline quan trọng.
16. **Không phân biệt lỗi input với lỗi hạ tầng:** client có thể retry sai hoặc quy lỗi cho người dùng.
17. **Gửi <code>IOException.getMessage()</code> cho client:** có thể rò đường dẫn, tên máy chủ và chi tiết OS.
18. **Dùng file thật/quyền truy cập thật để unit test mapper:** dễ flaky giữa môi trường.
19. **Không kiểm thử file rỗng:** dễ biến kết quả thành lỗi “not found”.
20. **Không kiểm thử race/symlink trong mô hình threat phù hợp:** validation tên file không thay thế thiết kế bảo mật.
21. **Chỉ test mã lỗi mà không test cause identity:** wrapper có thể sao chép message nhưng mất exception gốc.
22. **Cho rằng mọi FileSystemProvider hỗ trợ option y hệt nhau:** cần kiểm thử trên runtime/file system mục tiêu.
23. **Dùng đường dẫn tương đối theo working directory không kiểm soát:** chương trình có thể đọc nhầm file theo nơi chạy.
24. **Xóa tệp thử nghiệm bên ngoài vùng được tạo:** phải giới hạn cleanup vào temp directory mà chương trình sở hữu.

## 21. Checklist review quy trình đọc file

- Input đã được mô tả là **file ID, filename đơn hay relative path** chưa?
- Có kiểm tra null/blank/ký tự/loại file theo hợp đồng không?
- Nếu cho phép path tương đối nhiều thành phần, có biện pháp kiểm soát root, traversal và symlink phù hợp không?
- Đã phân biệt validation với authorization chưa?
- Có tránh coi metadata precheck là đảm bảo open thành công không?
- Khi mở file, đã bắt các subtype <code>IOException</code> quan trọng trước catch tổng quát chưa?
- Có đóng stream trong mọi nhánh thành công, decode fail hoặc quá lớn không?
- Có giới hạn **byte thực sự đọc** thay vì chỉ đọc kích thước trước không?
- Charset có rõ ràng và hành vi malformed input có được công bố không?
- Có phân biệt file rỗng với file không tồn tại không?
- Lỗi đã có code thích hợp và bảo toàn cause của I/O/decoder chưa?
- Public response có bỏ thông tin nhạy cảm nhưng vẫn có hướng xử lý không?
- Test đã bao phủ tên sai, file rỗng, file missing, directory, oversized, malformed UTF-8 và success chưa?
- Test cause đã dùng fake để bảo đảm cùng đối tượng exception mà không phụ thuộc OS chưa?
- Nếu file system có bên không tin cậy sửa đồng thời, giải pháp có xử lý TOCTOU và symlink theo threat model thực tế không?

## 22. Bài tập mở rộng

### Bài tập A — giới hạn số ký tự sau khi decode

Bổ sung quy tắc “nội dung không vượt 500 ký tự” và xác định “ký tự” ở đây là UTF-16 code unit hay Unicode code point. Kiểm thử với emoji, tiếng Việt và chuỗi chứa ký tự kết hợp. Không thay thế giới hạn byte bằng giới hạn ký tự nếu mục tiêu vẫn là kiểm soát dung lượng đọc.

### Bài tập B — file nhiều dòng

Dùng <code>BufferedReader</code> và xử lý tối đa một số dòng cụ thể. Xác định hành vi với dòng rất dài, newline Windows/Unix, dòng rỗng và file rỗng. Đảm bảo đóng reader nếu parser ném exception.

### Bài tập C — cấu trúc kết quả không dùng checked exception

Thiết kế <code>sealed interface ReadResult</code> với <code>Success(content)</code> và <code>Failure(code, message)</code>, rồi so sánh với kiểu checked exception trong demo. Hãy xác định nơi nào cần giữ Throwable nội bộ, nơi nào chỉ cần mã lỗi để hiển thị.

### Bài tập D — kiểm tra file ID thay vì filename

Cho phép người dùng nhập <code>documentId</code> và ánh xạ nó sang một file do server quản lý. Không để caller quyết định path OS. Viết test chứng minh ID không hợp lệ không mở file và ID hợp lệ chỉ đọc file được cấp quyền.

### Bài tập E — race giữa kiểm tra và open

Vẽ một tình huống bên khác xóa file sau <code>Files.isRegularFile()</code> nhưng trước <code>Files.newInputStream()</code>. Giải thích tại sao <code>NoSuchFileException</code> vẫn là tình huống hợp lệ phải bắt. Đề xuất cách kiểm soát nếu hệ thống yêu cầu trạng thái file nhất quán hơn.

## 23. Tóm tắt

Một quy trình đọc file đáng tin cần kiểm tra **đúng điều kiện ở đúng tầng**:

- **Validation** kiểm tra tên và loại đầu vào mà không phụ thuộc I/O.
- **Path/resource policy** quyết định dữ liệu nào được phép truy cập; allowlist giúp đơn giản hóa nhưng không thay thế bảo mật file system.
- **Open/read** là thao tác có thể thất bại, phải xử lý exception thực tế thay vì dựa vào precheck.
- **Giới hạn byte** bảo vệ tài nguyên trong phạm vi đã định.
- **Giải mã UTF-8 rõ ràng** giúp không âm thầm chấp nhận byte sai.
- **Try-with-resources** bảo đảm đóng stream và giữ lỗi phụ phù hợp.
- **Exception translation** tạo mã lỗi có ý nghĩa và giữ cause gốc để chẩn đoán.
- **Testing** phải bao phủ cả dữ liệu sai, file thực rỗng, file hỏng, file quá lớn và các lỗi hệ thống được giả lập.
- **Security boundary** cần xét path traversal, symlink, TOCTOU, quyền truy cập và giới hạn dữ liệu được công bố.

**Điều quan trọng nhất:** kiểm tra input làm giảm lỗi có thể dự đoán, nhưng không thể “chứng minh” thao tác đọc file sẽ thành công. File system là môi trường có thể thay đổi; chương trình phải vừa **kiểm tra những gì mình kiểm soát**, vừa **xử lý đúng những lỗi xảy ra khi thực hiện I/O**, và giữ ranh giới rõ ràng giữa thông tin chẩn đoán nội bộ với thông báo dành cho người dùng.