# Kiểm thử lỗi quyền, tệp biến mất và nội dung không hợp lệ trong Java 8+

## 1. Mục tiêu: kiểm thử các tình huống lỗi của I/O, không chỉ đường thành công

Phần lớn ví dụ đọc tệp Java đều bắt đầu bằng một tệp có sẵn, đúng định dạng và được phép truy cập. Trong ứng dụng thực, có ít nhất ba nhóm tình huống phải xử lý đúng:

1. **Lỗi quyền (permission denied):** ứng dụng không được phép mở/đọc tệp do quyền hệ thống, ACL, chính sách file system hoặc nguyên nhân liên quan.
2. **Tệp biến mất (missing/disappearing file):** đường dẫn không còn trỏ tới tệp khi thao tác mở bắt đầu, hoặc nội dung/tệp bị thay đổi trong quá trình xử lý.
3. **Nội dung không hợp lệ (invalid content):** byte không giải mã được theo charset, hoặc văn bản đã giải mã nhưng không đúng schema/giá trị nghiệp vụ.

Kiểm thử tốt phải xác nhận **đúng loại lỗi, thời điểm lỗi, thông tin phản hồi, cách đóng tài nguyên và không công bố kết quả sai**. Chỉ kiểm tra rằng "có exception nào đó" không đủ để phát hiện sai contract.

Bài thuộc nhóm **Tệp và I/O** của Java 8. Ta sử dụng **java.nio.file.Files**, **Path**, **BufferedReader**, **IOException**, **UncheckedIOException** cùng các API vẫn còn được hỗ trợ trong Java SE hiện hành. Các chương trình runnable gồm một bản Java 17+ và một bản tương thích Java 8, có dữ liệu tạm để tránh sửa file thật.

**Nguyên tắc cốt lõi:** kiểm thử lỗi theo *hợp đồng quan sát được*; không phụ thuộc message ngoại lệ, lời đoán từ Files.exists hay mẹo chỉnh quyền không chạy ổn định trên mọi OS.

## 2. Phân biệt bốn kiểu kết cục

| Kết cục | Ví dụ | Tầng gặp lỗi | Hướng xử lý |
| --- | --- | --- | --- |
| Đọc thành công | Tệp có 2 bản ghi hợp lệ | Reader + parser | Trả giá trị đầy đủ |
| Quyền bị từ chối | Mở tệp nhưng không có quyền | File system / bước mở | Phân loại I/O, không coi như tệp vắng |
| Không tìm thấy tệp | Tệp bị xóa trước khi mở | File system / bước mở | Phân loại missing, cho phép retry nếu nghiệp vụ quy định |
| Byte không hợp lệ | Tệp chứa chuỗi byte không hợp lệ với UTF-8 | Charset decoder khi đọc | Báo lỗi encoding, không âm thầm sửa nội dung |
| Bản ghi sai schema | "rice,zero" thay vì "rice,2" | Parser / validation | Báo dữ liệu không hợp lệ, chỉ rõ dòng nếu an toàn |
| Lỗi đọc giữa chừng | I/O lỗi sau khi đã đọc một vài dòng | Reader hoặc terminal Stream | Không tự công bố một phần dữ liệu như kết quả hoàn chỉnh |

**Tệp không tồn tại** và **không được phép truy cập** là hai trạng thái khác nhau. Đừng dựa vào một lần Files.exists(path) trả false để kết luận chính xác rằng tệp không có: API này có thể trả false khi không xác định được sự tồn tại hoặc do vấn đề quyền.

**Nội dung sai** có hai lớp riêng: byte không giải mã được và chuỗi giải mã thành công nhưng sai quy tắc nghiệp vụ. Thông thường hai lỗi này cần thông báo, metric và cách xử lý khác nhau.

## 3. Các kiểu ngoại lệ Java NIO hiện còn áp dụng

Các kiểu có từ Java 7/8 và tiếp tục được hỗ trợ:

| Kiểu | Quan hệ kế thừa | Ý nghĩa |
| --- | --- | --- |
| **IOException** | Exception checked | Lỗi I/O chung |
| **FileSystemException** | IOException | Lỗi liên quan một hoặc hai đường dẫn |
| **AccessDeniedException** | FileSystemException | Truy cập bị từ chối, thường do quyền hoặc kiểm tra truy cập |
| **NoSuchFileException** | FileSystemException | Thao tác với đường dẫn không còn tệp |
| **MalformedInputException** | CharacterCodingException → IOException | Chuỗi byte/ký tự không hợp lệ theo charset |
| **UncheckedIOException** | RuntimeException | Wrapper của IOException cho API không khai báo checked IOException |
| **NumberFormatException** | IllegalArgumentException → RuntimeException | Giá trị số trong bản ghi không hợp lệ |
| **InvalidRecordException tự định nghĩa** | Có thể là RuntimeException/Exception | Vi phạm schema hoặc quy tắc của ứng dụng |

**Đừng khẳng định mọi file system/provider đều bắt buộc ném chính xác subclass cụ thể.** Một số exception chuyên biệt của Files API là tùy chọn theo provider; có thể thấy một IOException/FileSystemException rộng hơn trên nền tảng khác.

Ví dụ thứ tự catch hợp lý khi thao tác trực tiếp có throws IOException:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String first = reader.readLine();
} catch (AccessDeniedException denied) {
    // Lỗi quyền được nhận diện cụ thể.
} catch (NoSuchFileException missing) {
    // File không tồn tại khi mở.
} catch (IOException otherIo) {
    // Lỗi mở, giải mã, đọc hoặc đóng còn lại.
}
~~~

Đây là **đoạn minh họa trong một method** có import java.io.*, java.nio.file.*, java.nio.charset.* và biến path; không phải chương trình độc lập. Các catch phải đặt lớp chuyên biệt trước IOException tổng quát để tránh unreachable catch.

## 4. Vì sao kiểm thử quyền thường thiếu ổn định?

Có thể thử **chmod** hoặc chỉnh ACL rồi gọi Files.newBufferedReader. Tuy nhiên:

- Windows, Linux, macOS và network file systems có mô hình quyền khác nhau.
- Trên POSIX, bit permission không phải yếu tố duy nhất; quyền truy cập thư mục cha, ACL hoặc mount option cũng quan trọng.
- Một tiến trình có đặc quyền cao vẫn có thể đọc tệp dù permission mode không cho user thông thường.
- File system có thể không hỗ trợ POSIX attribute view; thao tác setPosixFilePermissions có thể ném UnsupportedOperationException.
- Trên Windows, ACL, file sharing và các tiến trình khác giữ handle có thể tác động kết quả.
- Container, CI/CD runners và IDE có thể chạy dưới những danh tính khác nhau.
- Dựa vào nội dung message kiểu "Permission denied" cũng không portable: ngôn ngữ, path và provider thay đổi.

**Phân biệt hai mục tiêu kiểm thử:**

1. **Unit test đường xử lý lỗi quyền:** chủ động đưa **AccessDeniedException** vào ranh giới mở tệp, bảo đảm logic phân loại/cảnh báo/cleanup chính xác; chạy độc lập OS.
2. **Integration test quyền thật:** chỉ chạy trong môi trường đã biết danh tính, ACL/mode, file system/provider, quyền của user và cách thiết lập sandbox; nếu môi trường không đáp ứng, ghi nhận skip rõ lý do thay vì giả định test thành công.

Cách thứ nhất thường phù hợp CI và unit tests. Cách thứ hai bổ sung bảo đảm về tích hợp hệ điều hành, chứ không thay thế kiểm thử deterministic.

## 5. Đặt ranh giới có thể giả lập ở thao tác mở Reader

Một thay đổi nhỏ giúp kiểm thử lỗi quyền mà không sửa permission thật:

~~~java
@FunctionalInterface
interface ReaderOpener {
    BufferedReader open(Path path) throws IOException;
}
~~~

Đây là **interface bên trong class demo**. Code production có thể dùng một interface hoặc dependency tương tự để tách việc mở tệp khỏi việc đọc, parse và xử lý lỗi.

Implementation thật:

~~~java
ReaderOpener real =
        path -> Files.newBufferedReader(path, StandardCharsets.UTF_8);
~~~

Implementation giả lập lỗi:

~~~java
ReaderOpener denied =
        path -> {
            throw new AccessDeniedException(path.toString());
        };
~~~

**Tác dụng:** ta kiểm tra được rằng một lỗi quyền từ bước open khiến ứng dụng phân loại thành ACCESS_DENIED, không đánh đồng với thiếu file, không nuốt lỗi và không tạo kết quả giả.

**Không nói rằng việc ném AccessDeniedException giả lập đã chứng minh ACL của OS đang hoạt động đúng.** Đó là một unit test cho *xử lý lỗi*, không phải bài integration test hệ điều hành.

Một ranh giới tốt có thể là factory nhận Path và trả BufferedReader, hoặc một abstraction cao hơn trả kết quả đọc; nên chọn mức dependency injection vừa đủ để test có ý nghĩa.

## 6. Không dùng Files.exists hoặc Files.isReadable làm nguồn sự thật vĩnh viễn

Ví dụ anti-pattern:

~~~java
if (Files.exists(path) && Files.isReadable(path)) {
    return Files.readAllLines(path, StandardCharsets.UTF_8);
}
return Collections.emptyList();
~~~

Đây là snippet minh họa, **không phải cách xử lý lỗi được khuyến nghị**.

Vấn đề:

- Files.exists(path) có thể trả false nếu không thể xác định có tồn tại hay không.
- Files.isReadable(path) có thể trả false nếu tệp vắng, quyền không cho phép, hoặc khả năng truy cập không xác định.
- Kết quả của hai phép kiểm tra có thể lỗi thời ngay lập tức.
- Giữa pre-check và open, file có thể được xóa, di chuyển, thay thế, đổi quyền.
- Trả **emptyList** cho cả thiếu file lẫn lỗi quyền làm mất thông tin nghiệp vụ, gây khó vận hành.

**Nên thử chính thao tác cần làm** và xử lý IOException từ thao tác đó. Chỉ sử dụng pre-check khi nó thực sự cung cấp UX/gợi ý bổ sung, không coi như cơ chế đồng bộ hay quyền truy cập đảm bảo.

Khi đầu vào path không đáng tin, cần thêm chính sách bảo mật đường dẫn/symlink phù hợp; một lần kiểm tra rồi dùng lại path vẫn có race.

## 7. Kiểm thử tệp biến mất trước thời điểm mở

Một test dễ tái lập, không cần thread race:

1. Tạo một **thư mục tạm riêng**.
2. Tạo tệp trong thư mục đó, ghi dữ liệu thử.
3. Xác nhận Files.exists(file) trả true trên fixture vừa tạo.
4. Gọi Files.delete(file) — tệp bị xóa trước bước mở.
5. Gọi Files.newBufferedReader(file, UTF_8).
6. Kiểm tra NoSuchFileException với provider mặc định hỗ trợ kiểu cụ thể này; ở helper tổng quát, vẫn cần xử lý IOException rộng hơn.

~~~java
Path directory = Files.createTempDirectory("missing-test-");
Path file = directory.resolve("input.csv");
try {
    Files.write(file, "A,1\n".getBytes(StandardCharsets.UTF_8));
    boolean existed = Files.exists(file);
    Files.delete(file);
    try (BufferedReader reader =
                 Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        reader.readLine();
        throw new AssertionError("Expected missing-file failure");
    } catch (NoSuchFileException expectedMissing) {
        // Trên provider mặc định đã được thử trong demo.
    }
} finally {
    Files.deleteIfExists(file);
    Files.deleteIfExists(directory);
}
~~~

Đây là đoạn **trong method có khai báo throws IOException**. Chương trình đầy đủ ở phần 17 có ca tương ứng.

**Không dùng một đường dẫn cố định trong máy người dùng**, chẳng hạn C:\data\report.csv, để xóa khi test. Luôn tạo fixture riêng và chỉ dọn những tệp do test vừa tạo.

## 8. Check-then-open race: file còn tại check nhưng mất ở open

Một đường xử lý:

~~~text
T0  Reader: Files.exists(path) => true
T1  Writer khác: Files.delete(path)
T2  Reader: Files.newBufferedReader(path, UTF_8)
T3  Reader: NoSuchFileException hoặc lỗi I/O tương ứng
~~~

Đây là **TOCTOU (time-of-check to time-of-use)**.

**Hai điều phải kiểm tra:**

- Logic có sẵn sàng đón lỗi khi open không, dù đã có exists/isReadable trước đó?
- Khi không mở được, ứng dụng có trả trạng thái lỗi đúng thay vì một List rỗng giả thành công?

Trong unit test, có thể chèn hành động xóa ngay giữa hai bước thông qua abstraction; trong integration test, có thể điều phối hai thread bằng CountDownLatch/Phaser để ép thứ tự **check → delete → open**.

**Không dùng Thread.sleep(50)** rồi mong race xảy ra đúng lúc. Sleep làm test không deterministic và có thể gây flaky theo tải CI.

Với yêu cầu an ninh nghiêm ngặt, kiểm tra rồi mở đường dẫn theo tên có thể gặp symlink substitution; cần thiết kế đúng file-system API, sandbox và trust boundary, không chỉ tăng số lần Files.exists.

## 9. Tệp bị xóa sau khi đã mở: không có kết quả portable duy nhất

Đây là bẫy trong nhiều bài hướng dẫn kiểm thử "file biến mất".

Giả sử một Reader đã mở handle tới tệp, sau đó thread khác gọi Files.delete(path):

- Trên một số hệ thống kiểu POSIX, tên file có thể bị xóa nhưng handle đang mở vẫn đọc được các byte còn lại.
- Trên một số trường hợp Windows, việc xóa file đang mở có thể bị từ chối do quy tắc chia sẻ handle.
- File system mạng/provider khác có thể có semantics riêng.
- Nếu file bị truncate/modify trong lúc đang stream, nội dung đọc có thể thay đổi hoặc hành vi không phù hợp kỳ vọng snapshot.

**Vì vậy không nên viết assert rằng "đã delete khi reader mở thì readLine bắt buộc ném NoSuchFileException".** Đó không phải hợp đồng chung.

Các ca test nên tách:

1. **Disappearing before open**: chắc chắn không còn path khi yêu cầu mở, kiểm tra missing theo provider.
2. **Read failure after open**: giả lập IOException ở readLine lần thứ N bằng Reader có thể inject lỗi; kiểm tra partial read, cleanup, exception propagation.
3. **OS-specific delete-while-open integration**: kiểm tra chính sách của môi trường mục tiêu, không áp expected outcome từ Unix lên Windows hoặc ngược lại.

Bài này có riêng một test ném IOException ở **lần readLine thứ hai** và xác nhận BufferedReader được đóng trong nhánh lỗi.

## 10. Kiểm thử nội dung không hợp lệ có hai tầng

**Tầng A — encoding/decoder:** byte không hợp lệ với charset được dùng.

Ví dụ byte sequence **0xC3, 0x28** không phải UTF-8 hợp lệ vì 0xC3 đòi một continuation byte, nhưng 0x28 không phải continuation. Ghi chính xác hai byte này vào file tạm:

~~~java
Files.write(badUtf8, new byte[] {(byte) 0xC3, (byte) 0x28});
~~~

Khi đọc bằng UTF-8, decoder có thể ném **MalformedInputException** (một IOException checked). Nếu dùng **BufferedReader.lines()**, lỗi I/O phát sinh khi terminal operation lấy dòng sẽ được bọc **UncheckedIOException**.

**Tầng B — dữ liệu logic:** bytes decode hợp lệ nhưng bản ghi không đúng schema:

~~~text
milk,3
rice,zero
~~~

Chuỗi "rice,zero" vẫn là văn bản UTF-8 hợp lệ. Lỗi nằm ở việc parser cần một số nguyên dương nhưng nhận từ "zero" không parse được.

**Không dùng một catch duy nhất rồi báo "File unreadable" cho cả hai.** Mỗi tầng có thể dẫn tới hành động hỗ trợ người dùng khác: sửa encoding hoặc sửa dữ liệu/schema.

## 11. Chọn charset tường minh và không tự thay byte lỗi bằng dữ liệu giả

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý dòng khi decode thành công.
    }
}
~~~

**Files.newBufferedReader(Path, Charset)** giải mã byte bằng charset đã nêu và thông báo IOException khi gặp byte malformed/unmappable. Với UTF-8 sai, thường có thể bắt **MalformedInputException**, nhưng nếu môi trường/provider trả IOException khác, code vẫn phải có fallback IOException.

**Không lấy new String(bytes, UTF_8) rồi giả định mọi byte đều đã decode nghiêm ngặt**: một số API decode có chế độ thay byte lỗi bằng ký tự replacement. Nếu nghiệp vụ bắt buộc từ chối byte lỗi, dùng API/hợp đồng decoder có error reporting thích hợp.

**Không dựa vào charset mặc định của OS** cho dữ liệu trao đổi. Java hiện đại có quy tắc charset mặc định khác các nền tảng/phiên bản trước; định dạng file cần chỉ rõ UTF-8 (hoặc charset đúng của định dạng).

**BOM, newline và Unicode normalization** có thể ảnh hưởng parser. Nếu file xuất từ hệ thống có BOM hoặc dấu phân cách đặc thù, định nghĩa rõ cách xử lý. Không tự cho rằng một tệp decode được thì chắc chắn hợp lệ theo nghiệp vụ.

## 12. Validation bản ghi: kiểm tra cấu trúc trước rồi mới chuyển kiểu

Giả sử định dạng đào tạo là một dòng **sku,quantity**, trong đó:

- Có đúng **hai trường**.
- SKU không được rỗng sau trim.
- Quantity là **số nguyên dương**.
- Không cho phép trường thừa hoặc quantity không parse được.
- Dòng nào sai làm cả file bị từ chối, không âm thầm trả kết quả một phần.

Một parser có thể thực hiện:

~~~java
String[] fields = line.split(",", -1);
if (fields.length != 2 || fields[0].trim().isEmpty()) {
    throw new InvalidRecordException("line " + lineNumber);
}
try {
    int quantity = Integer.parseInt(fields[1].trim());
    if (quantity <= 0) {
        throw new InvalidRecordException("line " + lineNumber);
    }
    return new Order(fields[0].trim(), quantity);
} catch (NumberFormatException ex) {
    throw new InvalidRecordException("line " + lineNumber);
}
~~~

Đây là **snippet thuộc method** có biến line/lineNumber, kiểu Order và InvalidRecordException được định nghĩa ở chương trình phần 17.

**split(",", -1) giữ cả các trường rỗng cuối**, giúp phát hiện "milk," thay vì âm thầm mất field. Với đầu vào "milk,3,extra", số phần tử là 3 nên bị từ chối.

**Đừng coi split bằng dấu phẩy là CSV parser đầy đủ**. CSV thật có thể có dấu phẩy trong field được quote, escaping, multiline fields và schema riêng. Khi cần xử lý CSV theo chuẩn, dùng parser được thiết kế cho định dạng đó và kiểm tra giới hạn kích thước/độ dài.

**Không chỉ test các dòng điển hình.** Nên thử tệp rỗng, dòng trống, trường thiếu, giá trị âm/0, số quá lớn, ký tự Unicode, ký tự xuống dòng bất thường và tệp nhiều dòng.

## 13. Không công bố partial result như thể cả file đã hợp lệ

Nếu chương trình đã đọc và ghi 100 dòng vào database, rồi lỗi ở dòng 101, side effect trước đó **không tự rollback**.

Trong các bài test ở đây, phương thức đọc tạo một **List local** và chỉ trả List khi đọc và validate toàn bộ tệp thành công. Nếu có exception trước khi trả, caller không nhận danh sách được quảng cáo là kết quả hoàn chỉnh.

~~~java
List<Order> load(Path path, ReaderOpener opener) throws IOException {
    try (BufferedReader reader = opener.open(path)) {
        AtomicInteger lineNumber = new AtomicInteger();
        return reader.lines()
                .map(line -> parse(line, lineNumber.incrementAndGet()))
                .toList();
    }
}
~~~

Đây là method của **chương trình Java 17**, dùng List.toList (Java 16+) và parse/Order đã định nghĩa.

**Lưu ý memory:** cách collect toàn bộ vào List phù hợp với fixture test nhỏ và trường hợp file vừa bộ nhớ. Trong production với file lớn, có thể xử lý streaming theo batch; nhưng muốn bảo đảm tính nguyên tử nghiệp vụ thì phải phối hợp transaction, staging, idempotency hoặc cơ chế commit thích hợp. Lazy Stream không tự biến I/O hoặc ghi database thành transaction.

**Không swallow exception sau vài dòng rồi return partial List** trừ khi API có trạng thái partial result rõ ràng, kèm số dòng thành công, số dòng lỗi và quy tắc phục hồi.

## 14. BufferedReader.lines(): IOException xảy ra muộn

Một nguồn dữ liệu lười:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    Stream<String> lines = reader.lines();
    long count = lines.count();
}
~~~

Khi gọi **reader.lines()**, Stream chỉ được dựng. Việc đọc thật xảy ra trong terminal operation **count()**.

Nếu **readLine()** ném IOException trong lúc terminal operation tiêu thụ, **BufferedReader.lines() bọc nó thành UncheckedIOException**. Đây là một RuntimeException nên không xuất hiện trong chữ ký throws của Stream.count.

Ví dụ xử lý tại ranh giới gọi:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    long count = reader.lines().count();
    System.out.println(count);
} catch (UncheckedIOException ex) {
    IOException cause = ex.getCause();
    // Phân loại lỗi đọc dựa trên cause.
} catch (IOException ex) {
    // Lỗi mở reader, hoặc lỗi đóng từ try-with-resources.
}
~~~

**Cẩn thận:** lỗi parser của ứng dụng phát sinh trong map(...), chẳng hạn InvalidRecordException, không tự được bọc trong UncheckedIOException chỉ vì nó nằm trong Stream pipeline. Phải phân biệt lỗi logic với lỗi I/O, đồng thời không để một exception wrapper che mất cause khi logging.

## 15. Phân loại lỗi mà không lệ thuộc vào text của exception

Một classifier đơn giản:

~~~java
static String classify(Throwable error) {
    if (error instanceof UncheckedIOException) {
        error = ((UncheckedIOException) error).getCause();
    }
    if (error instanceof AccessDeniedException) return "ACCESS_DENIED";
    if (error instanceof NoSuchFileException) return "MISSING";
    if (error instanceof MalformedInputException) return "BAD_UTF8";
    if (error instanceof InvalidRecordException) return "INVALID_RECORD";
    if (error instanceof IOException) return "READ_IO";
    return "UNEXPECTED";
}
~~~

Đây là **snippet minh họa**, class InvalidRecordException được định nghĩa trong ví dụ đầy đủ. Tại ranh giới API thực, nên dùng một enum/exception type ứng dụng thay vì chuỗi nếu cần kiểm soát compile-time.

**Ưu tiên loại ngoại lệ và cause, không so sánh ex.getMessage()** vì message thay đổi giữa Windows/Linux, locale, filesystem provider và chi tiết đường dẫn.

**Không tự chuyển mọi IOException thành MISSING**. Lỗi quyền, lỗi mạng, decoder, file system, disk hoặc close có thể cần cách xử lý khác. MISSING là một kết cục cụ thể; READ_IO là một fallback chung khi không có loại chuyên biệt.

**Không công bố path đầy đủ hoặc nội dung tệp nhạy cảm trong thông báo lỗi cho client.** Có thể ghi thông tin chẩn đoán vào log được bảo vệ, trả mã lỗi ổn định ra API bên ngoài.

## 16. Đóng tài nguyên khi thành công và khi thất bại

**Try-with-resources** là cách hiện hành để đóng BufferedReader dù parse, decode hoặc readLine ném lỗi:

~~~java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    return parseAll(reader);
}
~~~

Đây là method minh họa có parseAll do ứng dụng định nghĩa và throws phù hợp.

Khi lỗi đọc xảy ra, **reader.close() vẫn được gọi**. Nếu chính close cũng thất bại trong lúc một exception khác đang lan ra, Java có cơ chế **suppressed exceptions** để không đơn giản xóa mất lỗi chính; có thể kiểm tra Throwable.getSuppressed khi debug.

**Không cố close bằng tay ở mọi nhánh catch** nếu try-with-resources đã sở hữu tài nguyên. Điều đó dễ dẫn tới duplicate cleanup hoặc vô tình che lỗi chính.

Trong chương trình phần 17, một BufferedReader giả lập cố ý ném IOException ở lần readLine thứ hai. Method close được override để cập nhật AtomicBoolean; sau lỗi, kết quả **reader closed on failure: true** chứng minh nhánh cleanup hoạt động.

**Quy tắc ownership:** hàm tạo/mở nguồn và sở hữu Reader thường chịu trách nhiệm đóng nó. Nếu trả Stream ra caller, phải đặc tả ai quản lý lifetime; không trả reader.lines() từ try-with-resources rồi mong caller tiêu thụ khi reader đã đóng.
## 17. Chương trình Java 17+ đầy đủ: kiểm thử 6 trường hợp có xác nhận

Chương trình sau được biên dịch và thực thi với **javac --release 17**. Mã thử cả đường thành công, quyền bị từ chối được inject, file đã xóa trước open, schema sai, byte UTF-8 sai và IOException ở lần đọc thứ hai; cuối cùng kiểm tra Reader đã đóng.

**Đây là test console độc lập**, không cần thư viện test ngoài. Sử dụng **record Order** và **Stream.toList()** nên yêu cầu Java 17+; các API Files, Path, BufferedReader và ngoại lệ căn bản đã có từ Java 8.

Tạo tệp **FileFailureTestsDemo.java**:

~~~java
import java.io.*;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class FileFailureTestsDemo {
    record Order(String sku, int quantity) {}

    @FunctionalInterface
    interface ReaderOpener {
        BufferedReader open(Path path) throws IOException;
    }
    @FunctionalInterface
    interface CheckedAction {
        Object run() throws IOException;
    }
    static final class InvalidRecordException extends RuntimeException {
        InvalidRecordException(String message) {
            super(message);
        }
    }
    static Order parse(String line, int number) {
        String[] fields = line.split(",", -1);
        if (fields.length != 2 || fields[0].trim().isEmpty()) {
            throw new InvalidRecordException("line " + number);
        }
        try {
            int quantity = Integer.parseInt(fields[1].trim());
            if (quantity <= 0) {
                throw new InvalidRecordException("line " + number);
            }
            return new Order(fields[0].trim(), quantity);
        } catch (NumberFormatException ex) {
            throw new InvalidRecordException("line " + number);
        }
    }
    static List<Order> load(Path path, ReaderOpener opener) throws IOException {
        try (BufferedReader reader = opener.open(path)) {
            AtomicInteger lineNumber = new AtomicInteger();
            return reader.lines()
                    .map(line -> parse(line, lineNumber.incrementAndGet()))
                    .toList();
        }
    }
    static BufferedReader utf8(Path path) throws IOException {
        return Files.newBufferedReader(path, StandardCharsets.UTF_8);
    }
    static String type(Throwable error) {
        if (error instanceof UncheckedIOException) {
            error = ((UncheckedIOException) error).getCause();
        }
        if (error instanceof AccessDeniedException) return "ACCESS_DENIED";
        if (error instanceof NoSuchFileException) return "MISSING";
        if (error instanceof MalformedInputException) return "BAD_UTF8";
        if (error instanceof InvalidRecordException) return "INVALID_RECORD";
        if (error instanceof IOException) return "READ_IO";
        throw new AssertionError("unexpected exception: " + error);
    }
    static void expect(String label, String expected, CheckedAction action)
            throws IOException {
        try {
            Object value = action.run();
            if (!"OK".equals(expected)) {
                throw new AssertionError(label + ": expected failure but got " + value);
            }
            System.out.println(label + ": " + value);
        } catch (IOException | UncheckedIOException | InvalidRecordException ex) {
            String actual = type(ex);
            if (!expected.equals(actual)) {
                throw new AssertionError(label + ": " + actual + " != " + expected, ex);
            }
            System.out.println(label + ": " + actual);
        }
    }
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("file-failure-tests-");
        Path good = dir.resolve("good.csv");
        Path missing = dir.resolve("removed.csv");
        Path wrongFormat = dir.resolve("wrong-format.csv");
        Path wrongUtf8 = dir.resolve("wrong-utf8.csv");
        try {
            Files.writeString(good, "milk,3\nrice,2\n", StandardCharsets.UTF_8);
            Files.writeString(missing, "before-delete,1\n", StandardCharsets.UTF_8);
            Files.writeString(wrongFormat, "milk,3\nrice,zero\n",
                    StandardCharsets.UTF_8);
            Files.write(wrongUtf8, new byte[] {(byte) 0xC3, (byte) 0x28});

            expect("valid", "OK", () -> load(good, FileFailureTestsDemo::utf8));

            expect("denied (injected)", "ACCESS_DENIED", () ->
                    load(good, path -> {
                        throw new AccessDeniedException(path.toString());
                    }));

            System.out.println("exists before deletion: " + Files.exists(missing));
            Files.delete(missing);
            expect("removed before open", "MISSING",
                    () -> load(missing, FileFailureTestsDemo::utf8));

            expect("invalid record", "INVALID_RECORD",
                    () -> load(wrongFormat, FileFailureTestsDemo::utf8));

            expect("invalid UTF-8", "BAD_UTF8",
                    () -> load(wrongUtf8, FileFailureTestsDemo::utf8));

            AtomicBoolean readerClosed = new AtomicBoolean();
            expect("read fails after first line", "READ_IO", () ->
                    load(good, path -> new BufferedReader(
                            new StringReader("sku,1\nsku,2\n")) {
                        int readCalls;
                        @Override
                        public String readLine() throws IOException {
                            if (++readCalls == 2) {
                                throw new IOException("injected read failure");
                            }
                            return super.readLine();
                        }
                        @Override
                        public void close() throws IOException {
                            readerClosed.set(true);
                            super.close();
                        }
                    }));
            System.out.println("reader closed on failure: " + readerClosed.get());
        } finally {
            Files.deleteIfExists(good);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(wrongFormat);
            Files.deleteIfExists(wrongUtf8);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FileFailureTestsDemo.java
java FileFailureTestsDemo
~~~

**Stdout của chương trình đã kiểm chứng:**

~~~text
valid: [Order[sku=milk, quantity=3], Order[sku=rice, quantity=2]]
denied (injected): ACCESS_DENIED
exists before deletion: true
removed before open: MISSING
invalid record: INVALID_RECORD
invalid UTF-8: BAD_UTF8
read fails after first line: READ_IO
reader closed on failure: true
~~~

**Không nhầm lẫn loại kiểm thử:**

- **denied (injected)** kiểm tra nhánh xử lý AccessDeniedException, **không chứng minh tệp good.csv thực sự thiếu quyền**.
- **removed before open** thật sự tạo rồi xóa file trong thư mục tạm trước khi Files.newBufferedReader được gọi, do đó kiểm tra đường dẫn mất ở thời điểm mở.
- **invalid UTF-8** tạo byte sai thật và dùng decoder UTF-8, không inject giả lỗi encoding.
- **invalid record** là lỗi schema từ parser, không phải IOException.
- **read fails after first line** inject IOException ở readLine thứ hai, mô hình hóa sự cố đọc giữa chừng mà không dựa vào chi tiết OS về xóa một file đang mở.
- **reader closed on failure** kiểm tra try-with-resources hoạt động trong nhánh đọc thất bại.

Program cố ý dùng **List.toList()** vì fixture nhỏ và dễ assert; không khẳng định đây là thiết kế streaming production cho file khổng lồ. Mọi file thử được tạo dưới một thư mục tạm riêng và xóa trong finally.

## 18. Java 8 thuần: cùng các lỗi nhưng đọc trực tiếp readLine

Nếu dự án đặt baseline ở Java 8, vẫn có thể kiểm thử AccessDeniedException, NoSuchFileException, MalformedInputException, BufferedReader và try-with-resources.

Tạo tệp **FileErrorsJava8Demo.java**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class FileErrorsJava8Demo {
    @FunctionalInterface
    interface ReaderFactory {
        BufferedReader open(Path path) throws IOException;
    }
    static final class BadRow extends IllegalArgumentException {
        BadRow(int number) {
            super("line " + number);
        }
    }
    static List<String> readAndValidate(Path path, ReaderFactory factory)
            throws IOException {
        try (BufferedReader reader = factory.open(path)) {
            List<String> result = new ArrayList<String>();
            String line;
            int row = 0;
            while ((line = reader.readLine()) != null) {
                ++row;
                String[] parts = line.split(",", -1);
                if (parts.length != 2 || parts[0].trim().isEmpty()) {
                    throw new BadRow(row);
                }
                try {
                    if (Integer.parseInt(parts[1].trim()) <= 0) {
                        throw new BadRow(row);
                    }
                } catch (NumberFormatException ex) {
                    throw new BadRow(row);
                }
                result.add(parts[0].trim());
            }
            return result;
        }
    }
    static String classify(Exception ex) {
        if (ex instanceof AccessDeniedException) return "DENIED";
        if (ex instanceof NoSuchFileException) return "MISSING";
        if (ex instanceof MalformedInputException) return "BAD_UTF8";
        if (ex instanceof BadRow) return "BAD_ROW";
        if (ex instanceof IOException) return "OTHER_IO";
        throw new AssertionError("Unexpected: " + ex);
    }
    static void expect(String label, String expected, Path file, ReaderFactory factory)
            throws IOException {
        try {
            List<String> result = readAndValidate(file, factory);
            if (!"OK".equals(expected)) throw new AssertionError(label + " unexpectedly passed");
            System.out.println(label + ": " + result);
        } catch (IOException | BadRow ex) {
            String actual = classify(ex);
            if (!expected.equals(actual)) throw new AssertionError(label + " wrong " + actual);
            System.out.println(label + ": " + actual);
        }
    }
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("file-java8-");
        Path good = dir.resolve("good.csv");
        Path missing = dir.resolve("missing.csv");
        Path badData = dir.resolve("bad-data.csv");
        Path badBytes = dir.resolve("bad-utf8.csv");
        ReaderFactory normal =
                path -> Files.newBufferedReader(path, StandardCharsets.UTF_8);
        try {
            Files.write(good, "A,2\nB,4\n".getBytes(StandardCharsets.UTF_8));
            Files.write(missing, "X,1\n".getBytes(StandardCharsets.UTF_8));
            Files.write(badData, "A,2\nB,nope\n".getBytes(StandardCharsets.UTF_8));
            Files.write(badBytes, new byte[] {(byte) 0xC3, (byte) 0x28});

            expect("valid", "OK", good, normal);
            expect("denial injected", "DENIED", good,
                    path -> { throw new AccessDeniedException(path.toString()); });
            Files.delete(missing);
            expect("missing", "MISSING", missing, normal);
            expect("invalid data", "BAD_ROW", badData, normal);
            expect("invalid encoding", "BAD_UTF8", badBytes, normal);
            System.out.println("missing exists: " + Files.exists(missing));
        } finally {
            Files.deleteIfExists(good);
            Files.deleteIfExists(missing);
            Files.deleteIfExists(badData);
            Files.deleteIfExists(badBytes);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Nếu dùng **JDK 17+** để biên dịch mã tương thích Java 8:

~~~bash
javac --release 8 FileErrorsJava8Demo.java
java FileErrorsJava8Demo
~~~

Nếu dùng chính JDK 8, chỉ cần **javac FileErrorsJava8Demo.java** (tùy chọn --release được thêm ở các JDK sau). Một JDK rất mới có thể cảnh báo về việc chọn target quá cũ; đó là cảnh báo của compiler, **không phải lời khuyên chuyển từ API hiện hành sang API lỗi thời**.

**Stdout đã kiểm chứng với target Java 8:**

~~~text
valid: [A, B]
denial injected: DENIED
missing: MISSING
invalid data: BAD_ROW
invalid encoding: BAD_UTF8
missing exists: false
~~~

**Đối chiếu hai phiên bản:**

- Bản Java 8 sử dụng vòng **readLine()** trực tiếp, vì thế lỗi decoder là checked IOException/MalformedInputException.
- Bản Java 17 sử dụng **reader.lines()** rồi **Stream.toList()**, nên IOException trong khi stream tiêu thụ có thể được gói thành UncheckedIOException.
- Cả hai dùng injection ở bước mở tệp cho lỗi quyền và tạo/xóa fixture tạm để kiểm tra đường dẫn mất.
- Cả hai phân biệt bad encoding với bad record schema và dọn file bằng finally.

**Lưu ý:** target Java 8 ở đây nhằm minh họa tính tương thích của API còn áp dụng, không đề xuất dùng bản runtime đã hết hỗ trợ bảo mật trong dự án production. Nên triển khai trên phiên bản JDK còn được nhà cung cấp hỗ trợ theo chính sách tổ chức.

## 19. Permission integration test thực tế, tránh dựa vào root/ACL tình cờ

Một integration test thực sự phải chạy **dưới danh tính user mục tiêu**, trên file system mục tiêu. Ví dụ:

- Linux/macOS: kiểm tra file store có hỗ trợ **PosixFileAttributeView**; tạo fixture riêng, đặt quyền đọc phù hợp, nhưng phải nhớ user đặc quyền/root và ACL khác có thể thay đổi kết quả.
- Windows: kiểm soát ACL thực bằng test account có quyền hạn xác định; không giả định rằng thay đổi thuộc tính read-only sẽ chặn **read access**.
- Container CI: quyền của container user có thể khác host; mount read-only không tương đương cấm tất cả thao tác đọc.
- Network file system: quyền và message phụ thuộc server/provider, cần fixture và các điều kiện đo/ghi nhận riêng.

**Không buộc unit test phải set permission thật để "đáng tin"**. Unit test injection giúp xác minh logic ổn định; integration test giúp xác minh hành vi của môi trường triển khai.

Khi viết test chmod/ACL, phải **khôi phục quyền ban đầu trong finally** trên chính file fixture, rồi mới xóa. Nếu test chạy bằng tài khoản quá mạnh và vẫn đọc được, hãy ghi rõ rằng **môi trường không đủ điều kiện để assert deny**, không đánh dấu mã xử lý lỗi là thất bại.

Không chạy những bài test thay đổi permission trên thư mục dự án, file người dùng hay thư mục hệ thống.

## 20. Test "file biến mất" có cần nhiều thread?

**Không nhất thiết.** Để kiểm tra xử lý NoSuchFileException khi open, việc tạo rồi xóa file trước khi mở là test deterministic và đúng mục tiêu.

Nếu muốn kiểm tra một race cụ thể giữa check và open:

1. Dùng một **thư mục tạm riêng**.
2. Thread A làm pre-check xong thì signal latch.
3. Thread B đợi latch rồi xóa file, signal lại.
4. Thread A đợi tín hiệu đã xóa, sau đó gọi open và assert kết cục tương ứng.
5. Dùng Future.get(timeout) hoặc timeout có chủ đích để tránh test kẹt.
6. Cleanup mọi executor, file và latch liên quan trong finally.

**Không dùng sleep để "canh" race**; timing không tạo ra happens-before cần thiết.

**Đừng ép tình huống delete sau khi handle đã mở** rồi yêu cầu kết quả giống nhau ở mọi OS. Nếu cần đảm bảo dữ liệu không đổi trong lúc đọc, phải thiết kế immutable file, write-then-atomic-move, version check, file lock hoặc protocol phù hợp theo nghiệp vụ và file system provider.

## 21. Bộ test đầu vào bất lợi nên có

| Fixture | Kỳ vọng kiểm thử |
| --- | --- |
| File hợp lệ, 2 dòng | Trả 2 bản ghi đầy đủ |
| File rỗng | Theo schema: List rỗng hợp lệ hay lỗi explicit |
| File chỉ có newline | Parser có coi dòng trống sai không |
| Trường thiếu "A," | Báo schema/value lỗi |
| Không có dấu phân cách "A" | Báo schema lỗi |
| Dư trường "A,2,X" | Báo schema lỗi |
| Số không parse được "A,abc" | Báo lỗi dữ liệu |
| Số 0 hoặc âm | Báo lỗi nếu yêu cầu số dương |
| Số quá lớn | NumberFormatException hoặc kết quả validation lỗi |
| Byte UTF-8 sai | Decoder báo lỗi, không tự thay byte |
| File mất trước open | NoSuchFileException (provider mặc định) hoặc IOException tương ứng |
| Quyền bị từ chối tại open | Nhánh AccessDeniedException được inject; integration kiểm tra OS thật |
| Lỗi đọc tại dòng thứ N | Không trả kết quả partial như kết quả hoàn chỉnh; reader đóng |
| Close cũng thất bại | Lỗi chính không bị che; suppressed exception được xem xét |
| Hai thread thay đổi file | Không dựa vào kết quả nondeterministic của delete-while-open |
| File cực lớn | Tránh readAllLines và collect toàn file nếu không phù hợp memory |
| Đường dẫn là thư mục/symlink | Phản hồi đúng policy và file-system provider |
| Đường dẫn không đáng tin | Ngăn traversal/truy cập ngoài phạm vi được phép |

**Các dữ liệu lỗi phải có nguồn gốc từ fixture test**, không phải một file người dùng có nội dung bí mật. Test không nên log toàn bộ payload hoặc đường dẫn có thể nhạy cảm.

Khi kiểm thử I/O trong pipeline, cần phân biệt lỗi xảy ra **khi mở** với lỗi xảy ra **khi terminal operation bắt đầu đọc**.

## 22. Các sai lầm cần tránh

1. **Dựa vào Files.exists rồi giả định open chắc chắn thành công.**
2. **Coi Files.isReadable=false đồng nghĩa chỉ có lỗi quyền** — nó còn bao gồm trường hợp khác.
3. **Dùng chmod để unit test chạy trên mọi OS** — không portable và có thể bị quyền cao bỏ qua.
4. **Coi test inject AccessDeniedException là test ACL thật** — hai mục tiêu khác nhau.
5. **Assert message ngoại lệ bằng chuỗi tiếng Anh cố định** — locale/provider có thể khác.
6. **Coi NoSuchFileException bắt buộc cho mọi provider** — subtype chuyên biệt có thể tùy chọn.
7. **Xóa file khi reader đang mở rồi yêu cầu đọc nhất định ném exception** — hành vi OS-dependent.
8. **Dùng sleep để tái hiện race** — flaky; dùng latch hoặc injection.
9. **Nhầm UTF-8 malformed với bản ghi sai schema** — khác tầng, khác chính sách.
10. **Dùng String.split đơn giản rồi tuyên bố hỗ trợ CSV phức tạp** — sai với quoted fields.
11. **Bỏ dấu -1 trong split nếu cần phát hiện trường rỗng cuối** — có thể bỏ sót input sai.
12. **Catch IOException nhưng quên UncheckedIOException từ BufferedReader.lines()**.
13. **Nuốt exception parse thành empty List** — có thể báo thành công giả.
14. **Trả partial result mà không có contract partial** — làm mất tính toàn vẹn.
15. **Quên try-with-resources hoặc quên kiểm tra close khi lỗi giữa chừng**.
16. **Thử lỗi trên file thật rồi cleanup sai** — có thể xóa nhầm dữ liệu.
17. **Dùng Files.readAllLines với file không giới hạn kích thước** — dễ dùng quá nhiều heap.
18. **Ghi log nguyên exception message/path ra client** — có thể lộ thông tin nội bộ.
19. **Bỏ qua cleanup của thư mục tạm khi test thất bại** — tích lũy file CI.
20. **Coi tệp đang tồn tại có nghĩa nội dung bất biến suốt phiên đọc** — writer khác có thể đổi dữ liệu.
21. **Không kiểm thử lỗi từ giai đoạn open, read, decode, parse và close riêng** — bỏ sót các điểm thất bại.
22. **Dùng kết quả "test pass" từ tài khoản root để chứng minh app user không thể đọc** — sai điều kiện giả định.

## 23. Bài tập thực hành kèm lời giải

**Bài 1 — Lỗi quyền:** Unit test nào nên dùng để xác minh logic của service trả trạng thái ACCESS_DENIED?

**Đáp án:** Inject một ReaderOpener ném AccessDeniedException. Assert service phân loại đúng và không trả dữ liệu giả. Integration quyền thật là bài riêng.

**Bài 2 — Missing file:** Tạo file tạm rồi delete trước newBufferedReader; expected exception thuộc nhóm nào?

**Đáp án:** Một IOException cho mở path không tồn tại, thường là **NoSuchFileException** trên provider mặc định. Không assert mọi provider luôn cùng subclass.

**Bài 3 — TOCTOU:** Files.exists(path) trả true, liệu open tiếp theo chắc chắn thành công?

**Đáp án:** Không. File có thể bị xóa/đổi quyền ngay sau check; phải bắt lỗi tại open.

**Bài 4 — Delete after open:** Xóa path khi stream đã mở có chắc khiến lần đọc kế tiếp thất bại?

**Đáp án:** Không. Unix/Windows/provider có hành vi handle và delete khác nhau; test không nên phụ thuộc một kết quả chung.

**Bài 5 — Encoding:** Byte 0xC3 0x28 được giải mã với UTF-8 có phải dữ liệu hợp lệ không?

**Đáp án:** Không. Decoder theo hợp đồng báo lỗi malformed input, thường là MalformedInputException ở direct Reader read.

**Bài 6 — Stream wrapper:** Với reader.lines().count(), IOException phát sinh ở readLine được bọc thành gì?

**Đáp án:** **UncheckedIOException**, cần inspect getCause() để phân loại lỗi I/O gốc.

**Bài 7 — Schema:** "rice,zero" được decode UTF-8 thành công nhưng parser cần int. Đây là I/O error không?

**Đáp án:** Không. Đây là **lỗi nội dung/validation**, ví dụ BadRow hoặc InvalidRecordException.

**Bài 8 — Partial result:** Đã đọc ba dòng, dòng bốn lỗi. Có nên return List của ba dòng và gọi là thành công?

**Đáp án:** Không nếu API không có partial-result contract. Giữ result local, propagate lỗi hoặc có transactional design.

**Bài 9 — Resource:** Khi callback Stream ném lỗi, Reader trong try-with-resources có được đóng không?

**Đáp án:** Có, try-with-resources gọi close; test bằng tracking reader để xác minh.

**Bài 10 — Cross platform:** chmod 000 trên tệp tạm rồi Files.isReadable vẫn true. Có nên coi Java bị lỗi?

**Đáp án:** Không vội. Process có thể có đặc quyền hoặc ACL khác; cần kiểm tra chính xác môi trường/identity và ghi nhận test không đủ điều kiện.

**Bài 11 — Test fixture:** Vì sao dùng Files.createTempDirectory thay vì path cứng?

**Đáp án:** Giảm va chạm, tránh xóa file thật, cô lập các test. Cleanup chỉ đúng file/dir tự tạo.

**Bài 12 — Retry:** Có nên retry vô hạn khi gặp AccessDeniedException?

**Đáp án:** Không. Lỗi quyền có thể không tự hết; retry cần phân loại nguyên nhân, deadline, số lần và chính sách bảo mật cụ thể.

**Bài 13 — Invalid UTF-8:** Dùng String constructor có chế độ thay thế byte lỗi để test encoder strict có đủ không?

**Đáp án:** Không. Cần decoder/API có reporting mode, như Files.newBufferedReader với charset phù hợp, và assert lỗi decode trên byte fixture thật.

**Bài 14 — Race:** Có thể dùng CountDownLatch để ép thứ tự check→delete→open không?

**Đáp án:** Có. Đồng bộ rõ quan hệ giữa các bước; test kết quả open-time missing, không suy ra mọi thứ về việc xóa file đang mở.

## 24. Checklist trước khi đưa vào production

**Contract lỗi:** phân biệt ACCESS_DENIED, MISSING, BAD_ENCODING, INVALID_DATA và OTHER_IO; có status cho caller, không chỉ một message chung.

**Testability:** thao tác open có ranh giới để inject, parse là logic riêng, test unit không phụ thuộc quyền OS.

**I/O:** dùng Path/Files, chọn UTF-8 tường minh; trong Stream, unwrap UncheckedIOException khi cần phân loại.

**Laziness:** nếu dùng Files.lines hoặc reader.lines, nhớ rằng lỗi có thể đến từ terminal operation chứ không chỉ lúc tạo Stream.

**Cleanup:** mọi Reader/Stream có ownership rõ; try-with-resources; cleanup file tạm trong finally; không tác động file thật.

**Disappearing file:** logic chịu được TOCTOU, không chờ Files.exists/isReadable bảo đảm, không giả định delete-while-open portable.

**Invalid input:** tách malformed bytes và invalid record; strict validation, kiểm tra tràn số/trường rỗng/schema, không tự dùng kết quả một phần.

**Cross-platform:** test permission thật cần môi trường có danh tính và file system xác định; skip có lý do khi không đáp ứng; kiểm tra Windows/Linux nếu sản phẩm hỗ trợ cả hai.

**Security:** không tiết lộ path/bytes riêng tư ra client; nếu user cung cấp path, kiểm soát phạm vi truy cập/symlink; không dùng một pre-check dễ race làm biện pháp bảo vệ duy nhất.

**Operational readiness:** có metric theo loại lỗi, thông điệp hỗ trợ sửa lỗi dữ liệu, cảnh báo lỗi I/O bất thường, chính sách retry/timeout/idempotency khi phù hợp.

## 25. Tổng kết và tham khảo chính thức

**12 điều cần nhớ:**

1. Kiểm thử lỗi I/O phải phủ **open, read, decode, parse và close**.
2. **AccessDeniedException** là một IOException chuyên biệt về truy cập bị từ chối; unit test có thể inject.
3. **NoSuchFileException** mô tả tệp không tồn tại; trên nhiều provider đây là lỗi thường gặp khi open path vừa bị xóa.
4. **Files.exists/isReadable** không khóa tệp và không bảo đảm hành động tiếp theo thành công.
5. Tệp **biến mất trước open** khác với việc **xóa tên file sau khi đã mở handle**.
6. Test quyền bằng ACL/chmod phụ thuộc OS và danh tính process; không nên dùng làm unit test portable duy nhất.
7. **MalformedInputException** liên quan charset/byte; bản ghi "rice,zero" sai schema là lỗi khác.
8. **BufferedReader.lines** có thể bọc IOException trong **UncheckedIOException** tại terminal operation.
9. **Không dựa vào text của exception message** để phân loại lỗi.
10. **Không công bố partial results như kết quả đầy đủ** khi parse/read thất bại giữa chừng.
11. **Try-with-resources** giúp đóng Reader khi callback ném lỗi; fixture tạm phải được dọn đúng scope.
12. **Dùng các API Java NIO hiện hành** và kiểm thử với phiên bản JDK được hỗ trợ.

**Tài liệu Oracle Java SE 26 (API hiện hành, không dùng kỹ thuật legacy):**

- **Files** — newBufferedReader, write, delete, exists, isReadable, Files.lines, permission checks và TOCTOU: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html
- **AccessDeniedException** — exception khi quyền truy cập không cho phép: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/AccessDeniedException.html
- **NoSuchFileException** — truy cập đường dẫn không có tệp: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/NoSuchFileException.html
- **FileSystemException** — cơ sở cho các lỗi file-system cụ thể: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/FileSystemException.html
- **MalformedInputException** — byte hoặc ký tự không hợp lệ theo charset: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/MalformedInputException.html
- **BufferedReader** — readLine, lines, đóng tài nguyên và UncheckedIOException: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/BufferedReader.html
- **UncheckedIOException** — unchecked wrapper của IOException: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/UncheckedIOException.html
- **Java NIO file attribute views** — kiểm thử permission tùy platform: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/attribute/package-summary.html

**Phạm vi phiên bản:** Các lớp Path, Files và exception chuyên biệt còn áp dụng từ Java 7/8 đến các JDK hiện đại. Chương trình Java 17 dùng record, List.toList và Files.writeString nên cần Java 17+. Chương trình Java 8 dùng readLine trực tiếp, Files.write(byte[]) và các API có từ Java 8; đã biên dịch ở mức target Java 8.

**Kết luận:** kiểm thử mạnh về file I/O không tạo các race ngẫu nhiên rồi hy vọng gặp lỗi. Hãy kiểm thử có kiểm soát từng failure mode, giữ ranh giới dễ inject, xác nhận đúng loại lỗi và cleanup, đồng thời bổ sung các bài integration test quyền thật trên môi trường mục tiêu.
