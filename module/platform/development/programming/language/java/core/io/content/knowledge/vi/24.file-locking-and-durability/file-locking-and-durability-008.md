# `ATOMIC_MOVE` và khả năng không được hỗ trợ trong Java NIO.2

## 1. Vấn đề cần giải quyết

Khi đổi tên, xuất bản hoặc thay thế một file, ứng dụng thường muốn những người đọc khác **không nhìn thấy trạng thái di chuyển dở dang**. Java NIO.2 cung cấp tùy chọn `StandardCopyOption.ATOMIC_MOVE` cho `Files.move(source, target, options...)` để yêu cầu hệ thống tệp thực hiện thao tác move như **một thao tác nguyên tử**.

Ví dụ: một công cụ tạo file cấu hình mới trong file tạm rồi chuyển nó thành `config.json`. Mục tiêu là tránh việc người đọc mở đúng thời điểm ứng dụng đang chuyển file và nhìn thấy file đích chỉ chứa một nửa nội dung.

Tuy nhiên, `ATOMIC_MOVE` **không phải cam kết luôn thành công**:

- Hệ điều hành, `FileSystemProvider`, file store, cách mount, quyền truy cập và loại đối tượng đều có thể ảnh hưởng.
- Nếu không thể thực hiện move nguyên tử, API ném `AtomicMoveNotSupportedException`.
- Nếu đường dẫn đích đã tồn tại, Java **không bảo đảm** một `ATOMIC_MOVE` sẽ thay thế đích: provider có thể thay thế hoặc ném `IOException`, tùy triển khai.
- Một move nguyên tử về mặt tên/khả năng quan sát **không đồng nghĩa** nội dung đã được ghi bền vững xuống thiết bị khi mất điện; đây là hai yêu cầu khác nhau.

Bài học thuộc nhóm **Java Core I/O → Khóa và dữ liệu bền**. Sau bài này, bạn sẽ hiểu chính xác hợp đồng `ATOMIC_MOVE`, các trường hợp bất khả thi, ý nghĩa của ngoại lệ, chiến lược xuất bản file theo quyền hạn và cách phân biệt **atomicity**, **visibility**, **durability** và **consistency**.

## 2. `Files.move` và `ATOMIC_MOVE` hoạt động thế nào?

Chữ ký API:

```java
Path result = Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

Đây là đoạn minh họa đặt trong một phương thức có thể ném `IOException`; `source` và `target` là các `Path` phù hợp.

`Files.move` di chuyển hoặc đổi tên một mục tệp. Với tùy chọn `ATOMIC_MOVE`, Java yêu cầu thao tác được thực hiện dưới dạng **atomic file-system operation**: quan sát của ứng dụng khác về việc đổi tên/di chuyển không thấy một chuỗi trạng thái trung gian của chính thao tác move đó.

Mô hình điển hình khi file đích chưa tồn tại:

```text
Trước:
  work/new.tmp    -> chứa toàn bộ dữ liệu hoàn chỉnh
  work/result.dat -> chưa có

Files.move(new.tmp, result.dat, ATOMIC_MOVE)

Sau khi thành công:
  work/new.tmp    -> không còn
  work/result.dat -> xuất hiện với dữ liệu hoàn chỉnh
```

Đây là minh họa thao tác thay đổi một tên file, **không phải giao dịch nhiều file**. Nếu yêu cầu cập nhật đồng thời `data.bin` và `index.json`, một lần `ATOMIC_MOVE` không biến hai thay đổi đó thành một transaction thống nhất.

### 2.1. Hợp đồng chính xác của `ATOMIC_MOVE`

Theo tài liệu Java SE 17/21 về `Files.move`:

1. `ATOMIC_MOVE` yêu cầu move dưới dạng thao tác nguyên tử của file system.
2. **Mọi tùy chọn move khác đều bị bỏ qua** khi có `ATOMIC_MOVE`.
3. Nếu đích đang tồn tại, provider **tự quyết định** có thay thế đích hay ném `IOException`. Không có lời hứa đa nền tảng cho việc replace.
4. Nếu không thể thực hiện move nguyên tử, ném `AtomicMoveNotSupportedException`, ví dụ khi buộc phải copy giữa hai file store khác nhau hoặc khi đường dẫn thuộc provider khác nhau.
5. Ngay cả khi hai đường dẫn cùng file store, thao tác vẫn có thể thất bại vì chính sách/cơ chế của provider hoặc lỗi I/O khác.

Từ khóa cần nhớ: `ATOMIC_MOVE` là **yêu cầu phải có tính nguyên tử**, không phải “cố gắng nguyên tử, không được thì Java sẽ tự hạ xuống copy rồi delete”.

## 3. So sánh move thường, replace và atomic move

| Cách gọi | Ý định | Khi target đã tồn tại | Có bảo đảm atomic không? |
| --- | --- | --- | --- |
| `Files.move(src, dst)` | Di chuyển/đổi tên theo mặc định | Thường thất bại, trừ trường hợp cùng file hoặc quy tắc provider | Không |
| `Files.move(src, dst, REPLACE_EXISTING)` | Cho phép thay thế đích nếu được hỗ trợ | Thay thế trong giới hạn API; thư mục không rỗng không thể bị thay thế theo cách này | Không |
| `Files.move(src, dst, ATOMIC_MOVE)` | Yêu cầu move nguyên tử | Có thể thay thế hoặc thất bại tùy provider | Có nếu **hoàn tất thành công với hợp đồng của provider** |
| `Files.move(src, dst, ATOMIC_MOVE, REPLACE_EXISTING)` | Vẫn là yêu cầu atomic move | **`REPLACE_EXISTING` bị bỏ qua**; như dòng trên | Có nếu hoàn tất đúng thao tác nguyên tử |

Các giá trị trên là `StandardCopyOption.ATOMIC_MOVE` và `StandardCopyOption.REPLACE_EXISTING`. Trong các bảng/ví dụ rút gọn, hai enum được viết không kèm tên lớp khi ngữ cảnh đã rõ.

Điểm dễ sai nhất:

```java
Files.move(staging, finalPath,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
```

Không được chú thích dòng này là “chắc chắn atomic overwrite”. Hợp đồng Java nói `ATOMIC_MOVE` khiến **tất cả tùy chọn khác bị bỏ qua**, còn đích tồn tại thì hành vi replace tùy implementation. Cách viết trên không thể biến một nền tảng không hỗ trợ thay thế nguyên tử thành nền tảng có hỗ trợ.

## 4. `AtomicMoveNotSupportedException` là ngoại lệ gì?

Ngoại lệ đầy đủ:

```java
java.nio.file.AtomicMoveNotSupportedException
```

Nó kế thừa `FileSystemException`, mà `FileSystemException` kế thừa `IOException`. Đây là **checked exception**. Khi gọi `Files.move`, chương trình cần xử lý/khai báo `IOException` hoặc các lớp con liên quan.

Ví dụ:

```java
try {
    Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException e) {
    // Tính nguyên tử không được hỗ trợ cho lần move này.
    // Quyết định theo nghiệp vụ: thất bại hoặc dùng phương án không nguyên tử.
}
```

Đoạn trên cần được đặt trong phương thức xử lý các `IOException` còn lại và có import `java.nio.file.*` thích hợp. Không nên bắt mọi `IOException` rồi kết luận “ATOMIC_MOVE không được hỗ trợ”.

| Ngoại lệ | Ý nghĩa có thể gặp | Cách phản ứng |
| --- | --- | --- |
| `AtomicMoveNotSupportedException` | Move nguyên tử không thể được thực hiện trong ngữ cảnh này | Không giả định đã thực hiện move; chọn chính sách fallback hoặc báo lỗi |
| `FileAlreadyExistsException` | Target đã tồn tại và provider không thể/không cho thay thế trong tình huống đó | Kiểm tra chính sách conflict, không tự ghi đè |
| `AccessDeniedException` | Thiếu quyền sửa đổi mục/thư mục hoặc có hạn chế truy cập | Kiểm tra quyền và tình trạng file đang sử dụng |
| `NoSuchFileException` | Source hoặc một phần đường dẫn cần thiết không có | Xem lại đường dẫn/đồng thời thay đổi |
| `DirectoryNotEmptyException` | Không thể thay thế thư mục đích không rỗng trong điều kiện API | Không biến thao tác này thành recursive delete ngoài ý muốn |
| `IOException` khác | Lỗi I/O, file system, khóa, mạng hoặc provider | Xem loại và nguyên nhân; không giả định trạng thái hậu lỗi |

Với non-atomic move, Javadoc nêu rõ nếu `IOException` xuất hiện **trạng thái source/target không được xác định hoàn toàn**: cả hai có thể tồn tại hoặc target có thể mới được copy một phần. Vì thế, một fallback không nguyên tử cần cả **chính sách khôi phục**, không chỉ một dòng gọi API.

## 5. Tại sao atomic move có thể không được hỗ trợ?

### 5.1. Chuyển giữa hai file store

Đổi tên file trong cùng một file store thường có thể được provider thực hiện bằng primitive rename của hệ điều hành. Nhưng khi source và target thuộc các file store khác nhau, di chuyển có thể cần:

```text
Source filesystem A                  Destination filesystem B
          |                                     ^
          +---- copy byte / metadata -----------+
          |
          +---- delete old file khi hoàn tất
```

Quy trình copy rồi delete gồm nhiều bước; một bên quan sát có thể thấy target đang được copy, hoặc hệ thống gặp lỗi giữa chừng. Java không thể hứa toàn bộ quy trình này là một file-system atomic operation phổ quát.

Ví dụ Windows chuyển từ một volume sang volume khác; Unix/Linux chuyển qua hai mount khác nhau; dữ liệu đang ở file-system provider ZIP rồi muốn đổi sang file system mặc định.

**Lưu ý:** “cùng ổ đĩa vật lý” không tương đương “cùng `FileStore`”. Các mount point, partition, network FS và provider có thể có quy tắc riêng. Và **cùng `FileStore` chỉ là điều kiện thuận lợi**, không phải chứng chỉ atomic move chắc chắn sẽ thành công.

### 5.2. Provider và hệ thống tệp khác nhau

`Path` trong Java thuộc một `FileSystem`; `FileSystem` được tạo bởi `FileSystemProvider`. Những file system như ZIP/JAR hoặc provider ảo có thể không hỗ trợ atomic rename giống filesystem mặc định.

`Files.move` có thể làm việc giữa các provider theo cách của API, nhưng khi được yêu cầu `ATOMIC_MOVE` thì việc chuyển dữ liệu liên-provider có thể không có primitive nguyên tử chung.

### 5.3. Giới hạn thực tế khác

Ngay trong cùng file store, thao tác có thể thất bại bởi quyền, file lock, khả năng provider, loại mục (thư mục/file/symlink), quy tắc chia sẻ trên Windows, giới hạn network FS, hoặc race với tiến trình khác. Không suy đoán tất cả lỗi đều là `AtomicMoveNotSupportedException`: nhiều lỗi xuất hiện dưới các lớp `IOException` khác.

## 6. Ví dụ Java 17+ chạy được: yêu cầu atomic, fallback có nhãn rõ

Ví dụ này tạo một file staging trong cùng thư mục với target, ghi nội dung đầy đủ, rồi thử `ATOMIC_MOVE`. Target cố tình **chưa tồn tại** để tránh phụ thuộc vào quy tắc replace-target của provider. Nếu không hỗ trợ atomic move, bản demo chọn fallback thường để minh họa nhánh lỗi; điều này được in ra rõ ràng.

Tạo file `AtomicMoveDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public class AtomicMoveDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("atomic-move-");
        Path staging = Files.createTempFile(directory, "stage-", ".tmp");
        Path target = directory.resolve("published.txt");

        try {
            Files.writeString(staging, "version-2", StandardCharsets.UTF_8);

            try {
                Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
                System.out.println("mode: atomic");
            } catch (AtomicMoveNotSupportedException ex) {
                // Chỉ bản demo chấp nhận giảm bảo đảm để vẫn có output.
                // Ứng dụng thật phải chọn chính sách này một cách chủ động.
                Files.move(staging, target);
                System.out.println("mode: non-atomic fallback");
            }

            System.out.println("content: "
                    + Files.readString(target, StandardCharsets.UTF_8));
            System.out.println("staging exists: " + Files.exists(staging));
        } finally {
            Files.deleteIfExists(staging);
            Files.deleteIfExists(target);
            Files.deleteIfExists(directory);
        }
    }
}
```

Lệnh thực thi:

```bash
javac AtomicMoveDemo.java
java AtomicMoveDemo
```

Khi provider hỗ trợ `ATOMIC_MOVE`, stdout:

```text
mode: atomic
content: version-2
staging exists: false
```

Nếu provider từ chối move nguyên tử nhưng cho phép move thường, stdout thay thế:

```text
mode: non-atomic fallback
content: version-2
staging exists: false
```

Hai trường hợp đều đúng với điều kiện tương ứng. Nếu gặp lỗi khác (quyền, file đang bị sử dụng, lỗi I/O), chương trình có thể kết thúc bằng exception thay vì các dòng trên. Đây không phải demo chứng minh máy nào cũng hỗ trợ atomic move.

**Giải thích:** `Files.createTempFile(directory,...)` đặt staging trong cùng thư mục cha với target, làm tăng khả năng được phép rename nguyên tử; chương trình không hứa điều đó. Khi move thành công, tên staging biến mất và target mang nội dung `version-2`. Trong nhánh fallback, tính nguyên tử **không được bảo đảm**, dù quan sát sau khi hoàn tất vẫn có vẻ giống nhau. Kết quả một lần chạy chỉ nói về môi trường và thao tác ấy, không chứng minh một provider luôn hỗ trợ mọi tình huống atomic move.

Lưu ý đường dẫn tạm phụ thuộc OS; demo không in đường dẫn ngẫu nhiên để stdout có thể so sánh.

## 7. Thiết kế publish file: staging hoàn chỉnh rồi mới move

Một ứng dụng cập nhật cấu hình hoặc dữ liệu thường dùng quy trình:

```text
[1] Tạo staging trong thư mục đích
          |
[2] Ghi toàn bộ nội dung, kiểm tra dữ liệu
          |
[3] Nếu yêu cầu độ bền: force dữ liệu staging
          |
[4] Đóng handle ghi
          |
[5] Files.move(staging, target, ATOMIC_MOVE)
          |
[6] Nếu thành công: target được xuất bản
    Nếu unsupported/lỗi: làm theo chính sách, ghi nhận và dọn staging có kiểm soát
```

Đây là mô hình **staging + publish**:

- Người đọc không sử dụng staging làm nguồn dữ liệu chính.
- Chỉ khi nội dung đã chuẩn bị đầy đủ mới đổi tên sang đường dẫn chính thức.
- Mục tiêu của move nguyên tử là không quan sát thấy trạng thái trung gian của bản thân thao tác đổi tên.
- Cần định nghĩa rõ điều gì xảy ra nếu target đã tồn tại; Java không hứa atomic replacement trên mọi provider.
- Nếu ứng dụng lưu nhiều file liên quan nhau, cần cơ chế phiên bản/manifest hoặc giao thức công bố khác thay vì giả định từng lần move độc lập tạo ra toàn bộ transaction.

### 7.1. Mẫu nghiêm ngặt: yêu cầu atomic, thiếu là thất bại

Khi tính nguyên tử là một điều kiện **bắt buộc**, hãy giữ `ATOMIC_MOVE` là precondition:

```java
import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

static void publishStrict(Path staging, Path target) throws IOException {
    try {
        Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
    } catch (AtomicMoveNotSupportedException e) {
        throw new IOException(
                "Cannot publish atomically: " + staging + " -> " + target, e);
    }
}
```

Đây là **phương thức minh họa**, đặt trong một lớp Java với các import tương ứng. Nó chỉ xử lý nhánh ngoại lệ cụ thể; các `IOException` khác truyền lên. Caller chịu trách nhiệm quản lý staging, lỗi và mục tiêu tồn tại. Không chuyển sang `Files.move` thường sau khi yêu cầu nguyên tử thất bại, vì điều đó làm yếu hợp đồng của chức năng xuất bản.

### 7.2. Mẫu cho phép giảm bảo đảm: fallback có chủ đích

Khi nghiệp vụ chấp nhận một giai đoạn di chuyển không nguyên tử, có thể bắt đúng `AtomicMoveNotSupportedException` rồi sử dụng `Files.move(source,target)` hoặc `REPLACE_EXISTING` theo chính sách.

Nhưng cần ghi rõ:

1. Fallback làm **mất bảo đảm atomicity**.
2. Trong nhánh non-atomic, nếu có `IOException`, tình trạng source/target **có thể chưa hoàn chỉnh hoặc không xác định**.
3. Chính sách có cho phép target đang tồn tại bị thay thế không? Nếu có, có được mất bản cũ nếu chương trình bị ngắt ở giữa không?
4. Có cần khôi phục từ bản sao staging/back-up, kiểm tra hash, marker trạng thái hoặc chạy reconcile lần sau không?
5. Nếu hệ thống dùng nhiều writer song song, ai có quyền publish phiên bản cuối cùng?

Không nên bắt tất cả `IOException` rồi luôn retry non-atomic: những lỗi như permission hoặc disk full sẽ không được giải quyết bằng cách đổi option, có thể còn làm hỏng trạng thái.

## 8. `ATOMIC_MOVE` với target đã tồn tại: bẫy quan trọng

Giả sử source chứa phiên bản mới và target chứa phiên bản cũ:

```text
source: new.tmp     = "version-2"
target: config.txt  = "version-1"
```

Với code:

```java
Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
```

Kết quả có thể tùy provider:

- Provider hỗ trợ atomic replace, thao tác thành công và đường dẫn target chuyển sang file mới.
- Provider từ chối vì target đã tồn tại và ném `IOException`.
- Nếu không hỗ trợ atomic move trong ngữ cảnh này, `AtomicMoveNotSupportedException` có thể được ném.

Thêm `REPLACE_EXISTING` **không sửa hợp đồng** của `ATOMIC_MOVE` vì các option khác bị bỏ qua. Kể cả khi bạn đã kiểm thử trên hệ điều hành A, không được suy luận hệ điều hành B hoặc ZIP/SMB/NFS sẽ xử lý target đã tồn tại giống hệt.

**Một điều không nên làm để né conflict:** xóa `target` trước, sau đó atomic move source vào. Hai thao tác `delete` và `move` không được hợp nhất thành một giao dịch nguyên tử. Trong khoảng giữa, target không tồn tại, phá vỡ mục tiêu cập nhật không gián đoạn.

Nếu yêu cầu “replace existing atomically” là bắt buộc, hãy ghi rành mạch trong hợp đồng ứng dụng và kiểm thử provider/file store/OS của môi trường triển khai. Khi không đáp ứng, thất bại rõ ràng hoặc dùng kiến trúc snapshot/versioned file; không lén giảm bảo đảm.

## 9. Atomicity khác durability: move thành công chưa chắc an toàn khi mất điện

Hai khái niệm thường bị trộn lẫn:

| Khái niệm | Câu hỏi | `ATOMIC_MOVE` có giải quyết hoàn toàn không? |
| --- | --- | --- |
| **Atomicity/visibility** | Một người đọc quan sát move như một thao tác duy nhất hay trạng thái trung gian? | Hướng tới điều này nếu move nguyên tử thành công |
| **Durability** | Khi hệ thống mất điện, nội dung và tên file đã tồn tại bền vững trên lưu trữ chưa? | **Không** được bảo đảm chỉ bởi `ATOMIC_MOVE` |
| **Consistency** | File có đúng định dạng, checksum, liên kết logic với dữ liệu khác không? | Không; ứng dụng phải kiểm tra |
| **Isolation** | Nhiều writer có tranh chấp phiên bản hoặc đọc/ghi đồng thời không? | Không tạo transaction nhiều thao tác |
| **Crash recovery** | Sau crash, chương trình biết dữ liệu nào là hợp lệ và phục hồi ra sao? | Cần thiết kế riêng |

Trước khi publish dữ liệu quan trọng, thường cần buộc nội dung staging được đẩy xuống thiết bị:

```java
try (FileChannel channel = FileChannel.open(
        staging, StandardOpenOption.WRITE)) {
    channel.force(true);
}
Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
```

Đây là đoạn minh họa trong phương thức khai báo `throws IOException`, với `staging`/`target` đã tồn tại, và cần import `java.nio.channels.FileChannel`, `java.nio.file.StandardOpenOption`, `java.nio.file.Files`, `java.nio.file.StandardCopyOption`. `force(true)` trên `FileChannel` yêu cầu đẩy cập nhật nội dung **và metadata của file** xuống thiết bị trong phạm vi cam kết API, nhưng **không tự bảo đảm** metadata của **thư mục chứa tên file sau rename** đã durable.

Để hướng tới crash consistency cao trên một số OS, thường còn cần flush/fsync **thư mục** sau thao tác rename. Java NIO không cung cấp một hợp đồng di động chung đảm bảo cách mở và `force` thư mục sẽ hoạt động trên mọi hệ điều hành/provider; không viết code Java chung rồi tuyên bố “100% crash safe trên mọi filesystem”. Một số hệ thống dùng transaction/journal ở tầng khác hoặc giao thức versioned publish + checkpoint.

Cũng cần phân biệt: `Files.move` không làm cho nội dung file mới hợp lệ một cách tự động. Nếu file staging được ghi thiếu, JSON sai cấu trúc hoặc checksum lỗi, một atomic move thành công vẫn sẽ xuất bản **nội dung sai đó một cách nguyên tử**.

## 10. Tạo staging cùng thư mục đích và những giới hạn còn lại

Lựa chọn thường tốt:

```java
Path dir = target.toAbsolutePath().getParent();
Path staging = Files.createTempFile(dir, ".publish-", ".tmp");
```

Đây là đoạn minh họa trong phương thức `throws IOException`; cần xác thực `target` có thư mục cha, quyền tạo tệp và mục tiêu hợp lệ. Tạo staging trong thư mục cha của target làm tăng xác suất hai đường dẫn cùng file store và được rename nguyên tử.

Nhưng vẫn có các giới hạn:

- `Files.getFileStore(staging)` hoặc `Files.getFileStore(dir)` có thể cho biết file store tại thời điểm kiểm tra, **không chứng minh atomic move chắc chắn hỗ trợ**.
- Nếu target là một symlink, replace-target và chính sách tương tác với symlink có thể ảnh hưởng đường đi. `Files.move` di chuyển **chính symlink** nếu source là symlink, không di chuyển nội dung đích.
- Đường dẫn cha có thể được thay bằng link hoặc đổi quyền bởi tiến trình khác giữa hai thao tác; với môi trường không tin cậy phải có chính sách bảo mật đường dẫn/thư mục phù hợp.
- Nếu staging chứa quyền/ownership/attributes không đúng, atomic rename không tự biến nó thành file có thuộc tính đúng. Cần chuẩn bị thuộc tính trước publish nếu bắt buộc.
- Một thao tác atomically **đổi tên** không có nghĩa mọi process đang giữ file descriptor tới file cũ lập tức thấy nội dung mới. Reader đã mở handle có thể tiếp tục nhìn file cũ theo ngữ nghĩa OS; nên mở lại đường dẫn hoặc dùng protocol version theo ứng dụng.

## 11. Không dùng `ATOMIC_MOVE` như một phép thử "an toàn tuyệt đối"

Những ngộ nhận thường gặp:

| Ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `ATOMIC_MOVE` luôn được hỗ trợ trên Java 17+ | Khả năng phụ thuộc provider, file store, OS và thao tác | Bắt `AtomicMoveNotSupportedException`; kiểm tra môi trường |
| Có `ATOMIC_MOVE` thì Java tự fallback copy/delete | API yêu cầu move nguyên tử hoặc báo lỗi phù hợp | Chọn chính sách fallback rõ ràng |
| `ATOMIC_MOVE, REPLACE_EXISTING` buộc phải atomic overwrite | Các option khác bị bỏ qua; target tồn tại implementation-specific | Thiết kế và kiểm thử replacement theo provider |
| Hai đường dẫn cùng ổ đĩa thì chắc chắn atomic | Một file store/OS vẫn có thể có ràng buộc khác | Dùng thao tác thực và xử lý lỗi |
| `FileAlreadyExistsException` nghĩa là không hỗ trợ atomic move | Có thể là vấn đề conflict với target hiện tại | Phân biệt lỗi |
| Atomic rename đảm bảo dữ liệu durable sau mất điện | Visibility và durability khác nhau | Chuẩn bị flush file, có chiến lược flush metadata/recovery |
| Xóa target trước rồi atomic move staging thì vẫn atomic replace | Hai bước có khoảng target thiếu | Giữ target đến bước publish nếu cần |
| `Files.copy` rồi `Files.delete` là atomic | Copy/delete là chuỗi nhiều thao tác | Dùng atomic move trong phạm vi hỗ trợ hoặc thừa nhận giảm bảo đảm |
| `Files.exists(target)` trước là đủ để chống race | Check-then-act có TOCTOU | Dùng quyền truy cập, ownership và chiến lược đồng thời phù hợp |
| Catch mọi `IOException` rồi thử thường sẽ sửa lỗi | Lỗi quyền/thiết bị/đĩa không liên quan thiếu atomicity | Phân loại exception, giữ ngữ cảnh lỗi |
| Atomic move là transaction gồm nhiều file | API áp dụng cho một thao tác move | Dùng manifest/version/checkpoint hoặc transaction cấp khác |

## 12. Đồng thời: nếu có hai writer cùng publish thì sao?

Giả sử writer A và B cùng chuẩn bị staging riêng cho `config.json`. Kể cả khi mỗi lần rename là nguyên tử, **không có đảm bảo** writer nào sẽ chiến thắng hoặc dữ liệu mới hơn là dữ liệu cuối cùng. `ATOMIC_MOVE` không cung cấp compare-and-swap theo phiên bản, lock phân tán hay đảm bảo thứ tự giao dịch.

Biện pháp phụ thuộc nghiệp vụ:

1. Chỉ một tiến trình có quyền publish trong mỗi thời điểm.
2. Sử dụng file lock hoặc hệ thống khóa phù hợp khi môi trường hỗ trợ, nhưng hiểu phạm vi khóa và sự hợp tác giữa tiến trình.
3. Gán version tăng dần, kiểm tra điều kiện cập nhật tại tầng điều phối, hoặc xuất bản file theo tên phiên bản bất biến.
4. Khi có nhiều file cần được đọc nhất quán, chỉ đổi một con trỏ manifest/current version cuối cùng sau khi tất cả file dữ liệu của phiên bản đã chuẩn bị xong.
5. Thiết kế recovery khi tiến trình chết ở bất kỳ thời điểm nào, bao gồm dọn staging tồn đọng có kiểm tra.

Một atomic move đảm bảo thuộc tính của **bản thân move đó nếu provider thực hiện thành công**; không thay thế giao thức quản lý phiên bản hay đồng thời.

## 13. Test tính hỗ trợ đúng cách

Một test có ý nghĩa nên thực hiện trong **môi trường thật** với:

- File source nằm trên đúng file store dự kiến.
- Target nằm ở đúng đường dẫn và điều kiện thực tế.
- Nếu cần thay thế, target **đã tồn tại**, để kiểm tra nhánh khó hơn.
- Quyền và ownership tương đương process chạy thật.
- Các tình huống lỗi (disk full, permission, concurrent reader/writer, target là directory/symlink) được kiểm tra có kiểm soát khi liên quan.

Ví dụ từ demo ở mục 6 chứng minh trường hợp **đích chưa tồn tại** trên đúng file store của máy chạy demo. Nó **không chứng minh** hỗ trợ replace-existing và không đo được crash durability.

Nếu muốn kiểm tra runtime:

```java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
    // Đã thành công cho source/target tại thời điểm này.
} catch (AtomicMoveNotSupportedException ex) {
    // Atomicity thiếu trong ngữ cảnh hiện tại.
} catch (IOException ex) {
    // Lỗi I/O khác; giữ thông tin để phân tích.
}
```

Mã này là đoạn minh họa trong phương thức; chưa xử lý chính sách file đích hay dọn source. Một phương thức `Files.move` thành công không thể khái quát rằng các file store khác, thư mục khác và target-existing cũng sẽ thành công.

## 14. Kịch bản thực tế và lựa chọn phù hợp

### A. Ghi cấu hình cần luôn thấy phiên bản hoàn chỉnh

Ghi vào file staging nằm cùng thư mục, xác thực nội dung, flush dữ liệu nếu yêu cầu độ bền, và thử `ATOMIC_MOVE`. Nếu replace-target là điều kiện bắt buộc nhưng provider không hỗ trợ, **báo lỗi và giữ phiên bản cũ** theo chính sách. Không chủ động `delete(target)` trước publish.

### B. Di chuyển file sang đĩa khác

Khi source ở volume A và destination ở volume B, atomic move có thể không khả thi. Nếu nhu cầu là chuyển dữ liệu, có thể chấp nhận copy vào một **staging ở đích**, xác minh checksum/độ dài, sau đó atomic rename từ staging đến tên cuối **trong file store đích**, và chỉ sau khi publish thành công mới cân nhắc xóa source. Đây là quy trình nhiều bước, **không bảo đảm atomic cho cả việc di chuyển xuyên volume**, nhưng có thể tránh xuất bản nội dung đích đang copy dở.

### C. Triển khai tập tin dung lượng lớn

Một chương trình tạo artifact `download.part`/file staging. Tới khi download + checksum hoàn tất, nó publish qua atomic rename nếu hỗ trợ. Dù rename có thể nguyên tử, vẫn phải thiết kế cách xử lý file chưa hoàn tất, timeouts và lỗi flush.

### D. Khóa tệp và tính bền

Nếu hệ thống đang dùng `FileLock`, đừng mặc định rằng lock của inode/file cũ bảo vệ tên target sau rename hoặc mọi provider tôn trọng lock theo cùng quy tắc. `FileLock` và `ATOMIC_MOVE` giải quyết vấn đề khác nhau: khóa kiểm soát truy cập đồng thời trong phạm vi OS/provider, còn atomic move kiểm soát tính nguyên tử của một thao tác di chuyển. Khả năng bền qua crash lại cần chính sách khác.

## 15. Câu hỏi tự kiểm tra

**1.** `Files.move(a,b,ATOMIC_MOVE)` có thể trả về thành công nếu target `b` đã tồn tại không?

**Đáp án:** Có thể, nhưng phụ thuộc provider; Java không bảo đảm cho mọi file system.

**2.** Thêm `REPLACE_EXISTING` vào `ATOMIC_MOVE` có bảo đảm thay thế target đang tồn tại không?

**Đáp án:** Không. Khi có `ATOMIC_MOVE`, tất cả option move khác bị bỏ qua; việc replace target vẫn implementation-specific.

**3.** Nếu source/target nằm trên hai file store khác nhau, Java có nhất định tự copy rồi delete để đảm bảo atomic không?

**Đáp án:** Không. Move nguyên tử có thể không khả thi; Java ném `AtomicMoveNotSupportedException` cho trường hợp không thể thực hiện atomic file-system move.

**4.** Khi `AtomicMoveNotSupportedException` xảy ra, có nên luôn fallback sang `Files.move` thường không?

**Đáp án:** Chỉ khi nghiệp vụ **chấp nhận mất bảo đảm atomicity** và có phương án khôi phục khi fallback bị lỗi giữa chừng. Nếu bảo đảm atomic là bắt buộc, phải báo lỗi.

**5.** Atomic move thành công có nghĩa đã chắc chắn durable sau mất điện không?

**Đáp án:** Không. Đó là bảo đảm về tính nguyên tử của thao tác move; độ bền của nội dung và metadata thư mục cần xử lý riêng, phụ thuộc OS/provider.

**6.** Có thể dùng `Files.delete(target)` rồi `Files.move(staging,target,ATOMIC_MOVE)` để tự tạo atomic replace không?

**Đáp án:** Không. Hai thao tác có khoảng thời gian target đã bị xóa nhưng staging chưa publish.

**7.** Hai writer cùng atomic move tới `config.json` có tự được sắp theo version mới nhất không?

**Đáp án:** Không. Atomic rename không cung cấp version ordering, CAS hay isolation cho một hệ thống nhiều writer.

**8.** Tại sao staging nên tạo tại thư mục cha của target?

**Đáp án:** Tăng khả năng source và target ở cùng file store và cùng provider, giảm nhu cầu copy qua volume. Tuy vậy vẫn cần xử lý ngoại lệ khi provider không hỗ trợ hoặc khi có lỗi khác.

## 16. Ghi nhớ và checklist khi triển khai

```text
ATOMIC_MOVE:
  - Yêu cầu move nguyên tử
  - Nếu không thể -> AtomicMoveNotSupportedException
  - Các tùy chọn move khác bị bỏ qua
  - Target tồn tại -> replace hay IOException phụ thuộc provider
  - Không mặc nhiên = durable / crash-safe / multi-file transaction
```

Trước khi đưa vào sản phẩm:

1. Xác định rõ mục tiêu: rename nguyên tử, atomic replacement, hay crash durability.
2. Tạo staging ở thư mục đích, ghi dữ liệu hoàn chỉnh và xác minh payload.
3. Nếu yêu cầu độ bền, cân nhắc `FileChannel.force(true)` và cơ chế flush metadata phù hợp hệ điều hành.
4. Chỉ publish sau khi hoàn tất chuẩn bị; không xóa bản đích cũ trước khi move.
5. Dùng `Files.move(..., ATOMIC_MOVE)` và phân biệt `AtomicMoveNotSupportedException` với các lỗi I/O khác.
6. Nếu nghiệp vụ đòi atomicity, **fail rõ ràng** khi không được hỗ trợ.
7. Nếu chấp nhận fallback, ghi rõ giảm bảo đảm và có cách xử lý source/target sau lỗi.
8. Kiểm thử trên file store, provider, OS, quyền và target-existing đúng môi trường triển khai.
9. Điều phối các writer và thêm cơ chế version/manifest nếu hệ thống cập nhật nhiều file.
10. Ghi nhận metadata và tình trạng staging để hỗ trợ recovery, tránh dọn nhầm dữ liệu hợp lệ.

## Tài liệu tham khảo

- Oracle Java SE 17 — `Files.move(Path,Path,CopyOption...)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Oracle Java SE 21 — `StandardCopyOption`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardCopyOption.html
- Oracle Java SE 21 — `AtomicMoveNotSupportedException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/AtomicMoveNotSupportedException.html
- Oracle Java SE 21 — `FileChannel.force(boolean)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
