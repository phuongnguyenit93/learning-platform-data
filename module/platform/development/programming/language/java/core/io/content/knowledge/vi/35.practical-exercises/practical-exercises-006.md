# Cập nhật tệp bằng ghi tạm và thay thế trong Java NIO.2

## 1. Bài toán thực hành

Giả sử ứng dụng đang có `config.txt` chứa một bản cấu hình hoạt động ổn định. Muốn lưu cấu hình mới, cách đơn giản là ghi đè trực tiếp:

~~~java
Files.writeString(target, newContent, StandardCharsets.UTF_8);
~~~

Đây là **mảnh mã minh họa** có biến `target` và `newContent` được khai báo bên ngoài. Nếu ứng dụng bị ngắt sau khi truncate file cũ nhưng trước khi ghi đủ nội dung mới, file đích có thể rỗng hoặc chỉ chứa một phần bản mới. Nguy cơ tương tự xảy ra khi thiếu dung lượng, serialization lỗi giữa chừng hoặc quá trình bị dừng.

Mẫu **write-temp-then-replace** tách việc chuẩn bị dữ liệu với việc công bố dữ liệu:

~~~text
Ban đầu:
  config.txt = VERSION_1

Bước 1, tạo ứng viên:
  .update-xxxxx.tmp = (trống)
  config.txt        = VERSION_1

Bước 2, ghi/kiểm tra bản mới:
  .update-xxxxx.tmp = VERSION_2
  config.txt        = VERSION_1

Bước 3, thay tên bằng move nguyên tử khi provider hỗ trợ:
  config.txt        = VERSION_2
  .update-xxxxx.tmp = không còn tên cũ
~~~

**Nếu lỗi xảy ra trước bước publish và không có writer khác**, target cũ vẫn chưa bị thao tác thay thế ảnh hưởng. Nếu thao tác move được thực hiện nguyên tử theo hợp đồng và thành công, reader mở theo tên target sẽ không phải quan sát quá trình ghi bản mới từng byte dưới tên đó.

Nhưng cần hiểu bốn bảo đảm khác nhau:

1. **Hoàn tất serialize:** bản ứng viên có đủ byte và format hợp lệ.
2. **Atomic visibility:** việc công bố tên target diễn ra như một thao tác nguyên tử, nếu được filesystem hỗ trợ.
3. **Durability:** dữ liệu và thay đổi tên có tồn tại đúng sau crash/mất điện hay không.
4. **Concurrency control:** nhiều writer có được phép vô tình ghi đè cập nhật của nhau không.

Một lời gọi `Files.move` chỉ góp phần giải quyết mục tiêu thứ hai. Không mặc nhiên coi nó là transaction nhiều file, fsync toàn bộ metadata hoặc cơ chế khóa giữa các tiến trình.

## 2. Luồng cập nhật đúng thứ tự

Với một file đơn, quy trình nền tảng là:

1. Chọn `target` có parent đáng tin cậy và đã kiểm tra quyền của caller.
2. Tạo file tạm **cùng thư mục đích** bằng `Files.createTempFile(parent, prefix, suffix)`.
3. Ghi **toàn bộ** nội dung/serialized representation vào file tạm; nếu dùng `FileChannel` thì lặp theo số byte thực ghi.
4. Kiểm tra tính hợp lệ của bản ứng viên: cú pháp, kích thước, checksum/version nếu nghiệp vụ cần.
5. Yêu cầu đồng bộ nội dung temp theo mức durability mong muốn bằng `FileChannel.force(...)` và **đóng channel**.
6. Gọi `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE)` để yêu cầu publish nguyên tử.
7. Nếu move thành công, coi bản mới đã công bố theo semantics của filesystem. Nếu thất bại, không xóa target cũ để “giúp move chạy”; dọn temp trong `finally`.
8. Nếu `ATOMIC_MOVE` không được hỗ trợ, áp dụng **chính sách đã quyết định**: fail closed hoặc cố ý cho phép fallback non-atomic, không đánh đồng hai mức bảo đảm.

Không nên đặt `Files.delete(target)` giữa bước 5 và bước 6. Thao tác đó phá tính liên tục: ứng dụng chết sau delete sẽ để target biến mất dù temp đã chuẩn bị xong.

### 2.1. Chọn đúng vị trí cho temp

~~~java
Path absolute = target.toAbsolutePath().normalize();
Path parent = absolute.getParent();
Path temp = Files.createTempFile(parent, ".update-", ".tmp");
~~~

Đây là mảnh mã, không chạy độc lập nếu chưa có biến `target`, import và xử lý lỗi. Tạo cùng parent thường giúp temp và target nằm cùng filesystem, cần thiết cho atomic rename trong nhiều hệ thống. Tạo temp bằng `Files.createTempFile("update-", ".tmp")` không có parent có thể đưa nó sang thư mục tạm mặc định trên **filesystem khác**, khiến atomic move không khả thi.

`createTempFile` tạo entry mới với tên không trùng, nhưng không loại bỏ mọi rủi ro nếu thư mục cho phép attacker xóa/đổi entry; thư mục staging phải thuộc quyền kiểm soát phù hợp.

### 2.2. Không đặt tên temp cố định

~~~java
// Anti-pattern khi nhiều tiến trình cập nhật đồng thời:
Path temp = target.resolveSibling("config.tmp");
~~~

Tên cố định dễ gây tranh chấp, bị chiếm sẵn hoặc bị hai lượt ghi đè lên nhau. Dùng `createTempFile` để mỗi lượt có ứng viên riêng và dọn đúng Path của lượt đó.

## 3. Ghi đầy đủ dữ liệu và xử lý short write

Một file tạm chỉ an toàn khi **không được publish trước lúc toàn bộ dữ liệu mới đã ghi xong**. Có thể dùng `Files.writeString` hoặc `Files.write` cho dữ liệu nhỏ. Với nội dung lớn hoặc cần đồng bộ trực tiếp, `FileChannel` cho quyền kiểm soát rõ:

~~~java
static void writeCandidate(Path temp, byte[] bytes) throws IOException {
    try (FileChannel file = FileChannel.open(
            temp,
            StandardOpenOption.WRITE,
            StandardOpenOption.TRUNCATE_EXISTING)) {

        ByteBuffer src = ByteBuffer.wrap(bytes);
        while (src.hasRemaining()) {
            int n = file.write(src);
            if (n == 0) {
                throw new IOException("Ghi file tạm không tiến triển");
            }
        }

        file.force(true);
    }
}
~~~

Đây là **phương thức minh họa**, cần import `IOException`, `Path`, `ByteBuffer`, `FileChannel` và `StandardOpenOption`.

- `FileChannel.write(src)` trả số byte thực chuyển và tăng `src.position()` tương ứng; không giả định mỗi lần luôn ghi hết.
- `src.hasRemaining()` xác định khi toàn bộ byte trong bản ứng viên đã được tiêu thụ.
- `force(true)` yêu cầu đồng bộ thay đổi file theo hợp đồng JDK; mục đích là chuẩn bị dữ liệu ứng viên trước khi publish.
- Đóng channel bằng `try-with-resources` đảm bảo không còn code serializer tiếp tục ghi vào temp sau bước chuẩn bị.

Nếu deserialize/serialize cần giữ byte liên tục rất lớn, hãy đưa dữ liệu qua `InputStream`/`OutputStream` để không giữ toàn bộ trong RAM, đồng thời xác định rõ bước nào flush, sync, verify và close.

### 3.1. Ghi vào temp khác với ghi vào target

~~~java
// Nguy hiểm với mục tiêu bảo toàn file cũ nếu serialize lỗi:
try (OutputStream out = Files.newOutputStream(
        target, StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {
    serializer.writeTo(out);
}
~~~

Đây là pseudocode, `serializer` do ứng dụng cung cấp. `TRUNCATE_EXISTING` đã thay đổi file đích ngay khi bắt đầu. Nếu `serializer` ném lỗi giữa chừng, file cũ không còn nguyên vẹn.

Cách đúng trong mô hình này là thực hiện toàn bộ thao tác ghi trên `temp`, sau đó dùng move để thay tên vào cuối.

## 4. ATOMIC_MOVE không đồng nghĩa REPLACE_EXISTING

API `Files.move(source, target, options...)` hỗ trợ các option phổ biến:

| Option | Ý nghĩa | Giới hạn cần nhớ |
| --- | --- | --- |
| `StandardCopyOption.ATOMIC_MOVE` | Yêu cầu move được thực hiện như thao tác filesystem nguyên tử. | Có thể ném `AtomicMoveNotSupportedException`. |
| `StandardCopyOption.REPLACE_EXISTING` | Cho phép thay target đã tồn tại trong move thông thường. | Không tự làm thao tác thành nguyên tử. |
| `StandardCopyOption.COPY_ATTRIBUTES` | Chủ yếu dùng với `Files.copy` cho metadata. | Không phải lời giải cho atomic publication. |

Ví dụ:

~~~java
Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
~~~

Điều rất dễ bỏ qua trong **Javadoc Java 17**: khi có `ATOMIC_MOVE`, **các option khác bị bỏ qua**; nếu target đã tồn tại, việc nó được thay thế hay thao tác thất bại là **implementation-specific**. Do đó:

~~~java
Files.move(
        temp, target,
        StandardCopyOption.ATOMIC_MOVE,
        StandardCopyOption.REPLACE_EXISTING);
~~~

không chứng minh mọi provider đều hỗ trợ **atomic replacement của target đã tồn tại**, dù source và target cùng thư mục. Lệnh trên thường được dùng trên filesystem có atomic rename replacement, nhưng production phải kiểm tra hành vi thực tế và có chính sách xử lý khi provider từ chối.

**Không dùng `Files.deleteIfExists(target)` trước move** để giải quyết `FileAlreadyExistsException`. Điều đó tạo một khoảng trống mà reader có thể thấy target không tồn tại; nếu tiến trình chết sau delete, bản cũ cũng mất.

### 4.1. Khi không hỗ trợ ATOMIC_MOVE

~~~java
try {
    Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException unsupported) {
    if (!allowNonAtomicFallback) {
        throw unsupported;
    }

    Files.move(temp, target, StandardCopyOption.REPLACE_EXISTING);
}
~~~

Đây là mảnh code, cần `Path`, `AtomicMoveNotSupportedException`, `StandardCopyOption` và biến `allowNonAtomicFallback`.

Hai lựa chọn có ý nghĩa khác nhau:

- **Fail closed:** nếu nguyên tử là yêu cầu bắt buộc (cấu hình quan trọng, file trạng thái), báo lỗi và không publish. Target cũ được giữ theo giả định không có writer khác.
- **Fallback có chủ đích:** chỉ với tài nguyên cho phép mức bảo đảm thấp hơn (ví dụ cache tái tạo được), mới move thông thường với `REPLACE_EXISTING`. Thao tác fallback **không được bảo đảm nguyên tử**, có thể thất bại giữa các bước do provider.

Không catch **mọi IOException** rồi fallback vào `Files.copy(temp, target, REPLACE_EXISTING)`. Một lỗi permission/storage/target đang mở không đồng nghĩa thiếu atomic support; copy thẳng có thể làm target bị cập nhật dở dang.

## 5. Phân biệt atomic visibility và crash durability

**Atomic visibility**: thao tác publish thay entry target một cách nguyên tử khi filesystem đáp ứng yêu cầu.

**Durability**: thay đổi dữ liệu và tên còn đúng sau khi máy mất điện, kernel crash hoặc thiết bị gặp sự cố.

~~~text
write temp
    |
    v
file.force(true)    <- yêu cầu đồng bộ dữ liệu/metadata của TEMP
    |
    v
Files.move(temp, target, ATOMIC_MOVE)
    |
    v
Metadata entry trong THƯ MỤC có durable sau crash không?
    |
    v
Phụ thuộc OS, filesystem, storage và protocol đồng bộ.
~~~

`FileChannel.force(boolean metaData)` trên file tạm:

- `force(false)` yêu cầu đồng bộ nội dung file (không nhất thiết mọi metadata).
- `force(true)` yêu cầu đồng bộ nội dung và metadata theo hợp đồng.
- Bảo đảm API mạnh nhất áp dụng cho file trên thiết bị lưu trữ **cục bộ**; remote filesystem/provider có giới hạn riêng.

Nhưng **`force(true)` trên file tạm không tự đảm bảo rename của directory entry đã durable**. Trong Java 17 không có một thủ tục portable chung buộc mọi directory provider đồng bộ metadata tên sau rename. Nếu cần crash-safety nghiêm ngặt, phải thiết kế và kiểm chứng trên OS/filesystem mục tiêu hoặc chọn tầng lưu trữ transactional.

`OutputStream.flush()` chỉ đẩy bộ đệm Java đến downstream, không phải cam kết dữ liệu đã xuống thiết bị. `close()` cũng không thay thế một giao thức crash-consistency hoàn chỉnh.

## 6. Chương trình hoàn chỉnh Java 17+: thử lỗi trước publish, rồi cập nhật thành công

Chương trình sử dụng **thư mục tạm thuộc sở hữu ứng dụng**. Nó tạo file `config.txt` chứa `OLD`, cố tình gây lỗi **trước move** để xác minh target chưa bị thay, rồi ghi `NEW` và kiểm tra cleanup.

Để ví dụ có thể chạy trên nhiều provider, phương thức nhận cờ `allowNonAtomicFallback`. Trong demo đặt `true` nhằm cho phép fallback nếu `ATOMIC_MOVE` không được hỗ trợ; **đây là lựa chọn cho bài thực hành, không phải khuyến nghị mặc định cho file quan trọng**. Khi sản phẩm bắt buộc atomicity, truyền `false`.

Lưu thành `AtomicFileUpdateDemo.java`:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.stream.Stream;

public class AtomicFileUpdateDemo {

    static void updateFile(
            Path target,
            byte[] newBytes,
            boolean allowNonAtomicFallback,
            boolean failBeforeMove) throws IOException {

        Path absolute = target.toAbsolutePath().normalize();
        Path directory = absolute.getParent();
        if (directory == null) {
            throw new IOException("Target không có thư mục cha");
        }

        Path temp = Files.createTempFile(
                directory, ".update-", ".tmp");

        try {
            try (FileChannel file = FileChannel.open(
                    temp,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer bytes = ByteBuffer.wrap(newBytes);
                while (bytes.hasRemaining()) {
                    int n = file.write(bytes);
                    if (n == 0) {
                        throw new IOException("Ghi file tạm không tiến triển");
                    }
                }

                file.force(true);
            }

            if (failBeforeMove) {
                throw new IOException("Injected failure before move");
            }

            try {
                Files.move(
                        temp, absolute,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException unsupported) {
                if (!allowNonAtomicFallback) {
                    throw unsupported;
                }

                Files.move(
                        temp, absolute,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("file-update-");
        Path target = dir.resolve("config.txt");

        try {
            Files.writeString(
                    target, "OLD", StandardCharsets.UTF_8);

            boolean injected = false;
            try {
                updateFile(
                        target,
                        "IGNORED".getBytes(StandardCharsets.UTF_8),
                        true,
                        true);
            } catch (IOException expected) {
                injected = true;
            }

            System.out.println("failureInjected=" + injected);
            System.out.println("afterFailure=" +
                    Files.readString(target, StandardCharsets.UTF_8));

            updateFile(
                    target,
                    "NEW".getBytes(StandardCharsets.UTF_8),
                    true,
                    false);

            System.out.println("afterSuccess=" +
                    Files.readString(target, StandardCharsets.UTF_8));

            long leftovers;
            try (Stream<Path> entries = Files.list(dir)) {
                leftovers = entries.filter(p ->
                        p.getFileName().toString().endsWith(".tmp"))
                        .count();
            }
            System.out.println("tempFiles=" + leftovers);
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 AtomicFileUpdateDemo.java
java AtomicFileUpdateDemo
~~~

**Stdout dự kiến trên filesystem cho phép thay thế target đã tồn tại bằng atomic move hoặc nhánh fallback đã bật:**

~~~text
failureInjected=true
afterFailure=OLD
afterSuccess=NEW
tempFiles=0
~~~

Nếu provider không cho phép thay thế target đang tồn tại bằng `ATOMIC_MOVE` và ném ngoại lệ khác `AtomicMoveNotSupportedException`, hoặc filesystem/permission không cho move, chương trình có thể ném `IOException` thay vì in bốn dòng trên. Không hứa hẹn behavior như nhau trên mọi nền tảng.

### 6.1. Vì sao sau injected failure, target vẫn là OLD?

Lỗi được tạo ra **sau khi đã ghi và đóng temp, nhưng trước move**. Quy trình chưa hề mở target để truncate hay ghi, vì vậy trong bài demo không có tác nhân khác, `config.txt` vẫn chứa `OLD`. `finally` dọn temp đã ghi dở hoặc ghi đủ mà chưa được publish.

Đây là phép thử **lỗi xử lý khi tiến trình còn chạy**, không phải phép mô phỏng mất điện; không suy ra file chắc chắn còn tồn tại với đúng nội dung sau mọi crash OS.

### 6.2. Vì sao có thể chạy mà không in phương án move?

Chương trình không in `atomic=true/false` để stdout không gắn với một provider cụ thể. Nếu `ATOMIC_MOVE` được hỗ trợ thì nhánh đó chạy; nếu chỉ ném `AtomicMoveNotSupportedException` và cho phép fallback thì dùng `REPLACE_EXISTING`. Hai nhánh có **mức bảo đảm khác nhau** dù kết quả kiểm tra file trong một lượt chạy đơn giản giống nhau.

Ứng dụng production nên log/metric sự kiện hạ cấp này và thường không cho fallback với dữ liệu quan trọng.

### 6.3. Cleanup trong finally

`Files.deleteIfExists(temp)` sau move thành công thường không tìm thấy đường dẫn temp vì entry đã được chuyển. Nếu bước ghi/move thất bại, nó cố dọn file ứng viên.

**Điểm cần cải thiện trong production:** nếu cleanup ném IOException trong `finally`, nó có thể che lỗi gốc. Một implementation cứng cáp nên thu lỗi cleanup, gắn như **suppressed exception** vào lỗi chính khi có thể, và không để cleanup làm chương trình báo nhầm trạng thái publish. Cũng cần xử lý trường hợp tiến trình chết trước khi chạy finally: nên có quy trình dọn temp mồ côi theo tuổi/version một cách an toàn.

## 7. Reader quan sát gì khi replace?

Khi provider có atomic rename replacement:

~~~text
Trước publish: target -> bản A
Đang ghi temp: target -> bản A, temp -> bản B
Sau publish:   target -> bản B
~~~

Reader mở `target` **sau khi** publish thành công có thể đọc bản B. Reader đã mở một handle tới bản A trước đó **không tự chuyển** handle sang bản B. Trên nhiều filesystem kiểu POSIX, reader cũ có thể đọc tiếp inode cũ; trên Windows, quyền sharing của open handles còn có thể làm move thất bại.

Không dùng giả định “mọi reader trên mọi hệ điều hành luôn thấy bản A hoặc B theo cùng cách”; behavior cụ thể phụ thuộc provider, phương thức reader mở file và lifetime file handle.

Nếu client đọc nửa file, đóng handle, rồi mở lại và đọc tiếp theo offset, hai nửa có thể thuộc hai phiên bản khác nhau. Hãy đọc toàn bộ một phiên bản qua **một handle** hoặc sử dụng version ID/giao thức nhất quán.

## 8. Hai writer vẫn có thể gây lost update

~~~text
target đang là A
Writer 1: đọc A -> tính B1 -> ghi temp1
Writer 2: đọc A -> tính B2 -> ghi temp2
Writer 1: atomic move temp1 -> target = B1
Writer 2: atomic move temp2 -> target = B2

B1 bị thay bởi B2, dù từng move có thể atomic.
~~~

`ATOMIC_MOVE` không có semantics “chỉ thay nếu target vẫn là bản mà tôi vừa đọc”. Vì vậy nó **không tự giải quyết concurrency control**.

Có thể chọn:

- **Single writer**: một process/thread sở hữu file và tuần tự hóa mọi cập nhật.
- **File lock hợp tác**: tất cả writer tuân thủ cùng giao thức khóa trong toàn bộ đoạn read → compute → publish. Tính bắt buộc/khả dụng tùy OS/filesystem.
- **Versioned files + manifest**: ghi các file bất biến theo version, rồi publish một pointer/manifest; vẫn cần giải quyết việc hai writer cùng cập nhật manifest.
- **Transactional storage/CAS**: khi cần ngăn lost update một cách chắc chắn ở cấp hệ thống, sử dụng kho dữ liệu hỗ trợ compare-and-swap hoặc transaction thực sự.

`Files.size()`, `getLastModifiedTime()` hoặc checksum kiểm tra trước move chỉ mô tả trạng thái tại thời điểm đọc. Writer khác vẫn có thể đổi file **sau check nhưng trước move** (*TOCTOU*). Không biến check-then-move thành CAS chỉ bằng một câu lệnh if.

## 9. Giữ nguyên metadata, quyền và ownership

Một bản update bằng rename thường đưa một **object file mới** vào tên target. Vì thế thông tin của file cũ có thể không còn được giữ nguyên tự động:

- Quyền POSIX (rwx), owner, group.
- ACL của filesystem/provider.
- Modified time, creation time, extended attributes, security labels.
- Hard links: các tên khác trỏ inode cũ có thể vẫn giữ bản cũ.

Ví dụ chỉ sao chép permission khi provider thực sự hỗ trợ POSIX:

~~~java
Set<PosixFilePermission> permissions =
        Files.getPosixFilePermissions(target);

Files.setPosixFilePermissions(temp, permissions);
~~~

Đây là **mảnh mã minh họa**, cần `PosixFilePermission` và import `Files`/`Set`. API có thể ném `UnsupportedOperationException` trên provider không có POSIX view. Sao chép mode bit **không đủ** bảo toàn ACL, owner, xattrs và chính sách bảo mật. Nếu file thuộc dữ liệu nhạy cảm, lựa chọn tốt có thể là đặt permission theo cấu hình đáng tin **khi tạo temp**, thay vì mù quáng thừa kế từ target không tin cậy.

Đọc metadata của target rồi áp vào temp cũng có TOCTOU nếu actor khác có thể đổi target giữa hai bước. Đảm bảo parent directory tin cậy và authorization theo quy trình của hệ thống.

## 10. Symlink, hard link và vùng thư mục không tin cậy

Mẫu ghi tạm không tự tạo sandbox đường dẫn:

1. Nếu user nhập `../../config.txt`, `Path.normalize()` đơn độc không đủ chứng minh thao tác bị giữ trong vùng cho phép.
2. Nếu attacker có thể sửa parent directory, họ có thể thay thế entry, symlink hoặc temp giữa hai lời gọi API.
3. Khi target có symbolic link hoặc hard link, ngữ nghĩa thay entry với ngữ nghĩa sửa nội dung inode không giống nhau. Cần xác định chính sách của ứng dụng, không suy diễn tất cả provider như nhau.
4. `Files.exists(...)`/`isRegularFile(...)` rồi `Files.move(...)` không phải một giao dịch kiểm tra-và-thay thế nguyên tử.
5. Nếu cần chống path-race trong thư mục chia sẻ không tin cậy, kiểm tra `SecureDirectoryStream`, quyền thư mục, directory-handle-relative API và khả năng provider; nếu không đáp ứng bảo đảm cần thiết phải fail closed hoặc đổi kiến trúc.

**Phạm vi bảo vệ chính của mẫu này là không công bố output mới khi còn đang ghi**, không tự chặn mọi actor có quyền sửa tên tệp.

## 11. Cập nhật file rất lớn hoặc định dạng phức tạp

Khi file có thể lớn hơn RAM:

~~~text
Ứng dụng cung cấp dữ liệu mới
     |
     v
Stream serializer -> temporary file
     |
     v
Parse/validate lại temp khi cần
     |
     v
Sync temp theo hợp đồng
     |
     v
Đóng writer -> atomic move -> target
~~~

Ví dụ serializer streaming:

~~~java
try (OutputStream out = Files.newOutputStream(
        temp,
        StandardOpenOption.WRITE,
        StandardOpenOption.TRUNCATE_EXISTING)) {

    // serializer.writeTo(out) là API của ứng dụng.
    serializer.writeTo(out);
}
~~~

Đây là **pseudocode** vì `serializer` chưa được khai báo. Sau khi đóng output, cần có bước đồng bộ file temp phù hợp nếu yêu cầu durability, rồi mới công bố; không được xem việc đóng stream là bằng chứng mọi dữ liệu đã nằm bền vững trên đĩa.

Lưu ý phương án có temp phải giữ đồng thời **bản cũ và bản mới**, gây chi phí dung lượng lớn. `Files.getFileStore(path).getUsableSpace()` chỉ cung cấp thông tin tại thời điểm gọi và không đặt chỗ độc quyền; vẫn phải bắt `IOException` nếu disk-full.

## 12. Ma trận sự cố

| Lỗi xảy ra ở đâu? | Ảnh hưởng trong tiến trình còn chạy, nếu không có writer khác | Cách xử lý |
| --- | --- | --- |
| Trước tạo temp | Target cũ chưa bị thay. | Báo lỗi. |
| Đang ghi temp | Target cũ chưa publish thay đổi; temp có thể dở dang. | Không move, dọn temp. |
| Kiểm tra candidate thất bại | Target cũ chưa publish. | Bỏ candidate, dọn temp. |
| `force(temp)` ném lỗi | Chưa đi tới publish theo flow đúng. | Không move, giữ target cũ. |
| Fault injection trước move | Target cũ còn nguyên trong demo. | Bắt lỗi, kiểm tra cleanup. |
| `ATOMIC_MOVE` không được hỗ trợ | Bảo đảm yêu cầu chưa được đáp ứng. | Fail closed hoặc fallback được cho phép trước. |
| Move thành công nhưng caller chưa nhận response | Target có thể đã publish bản mới. | Retry cần idempotency/version. |
| Mất điện/cra​​sh | Không thể suy luận đầy đủ chỉ từ Java API. | Thử nghiệm recovery và durability theo filesystem. |

Nếu response cho caller bị mất **sau khi commit**, caller có thể retry cùng yêu cầu. Thiết kế cần cân nhắc request ID, version token hoặc cơ chế xử lý lặp thay vì giả định lần trước chắc chắn thất bại.

### 12.1. Atomic move không phải transaction nhiều file

Muốn cập nhật `users.json` và `permissions.json` cùng một phiên bản, hai lệnh atomic rename **không tạo giao dịch nguyên tử cho cả hai file**. Reader có thể quan sát một file đã đổi, file kia chưa đổi.

Có thể giải quyết bằng file phiên bản hóa và một manifest/pointer tới phiên bản hoàn chỉnh, hoặc lưu dữ liệu trong một transaction store. Bản thân manifest cũng cần quy trình publish và recovery phù hợp.

## 13. Kiểm thử đúng bảo đảm

### 13.1. Unit test serialization bằng stream bộ nhớ

Tách core serializer khỏi phần mở file:

~~~java
void writeRepresentation(OutputStream out, Config config)
        throws IOException {
    // API của ứng dụng: ghi theo thứ tự định dạng đã định.
}
~~~

Đây là **pseudocode**, chưa đủ để biên dịch vì `Config` và phần thân chưa có. Kiểm thử serializer bằng `ByteArrayOutputStream` hoặc `StringWriter` cho trường hợp dữ liệu rỗng, Unicode, bản ghi lớn, lỗi encode và invalid input.

### 13.2. Integration test file tạm

Với `Files.move`, phải chạy trên filesystem thật. Các tình huống quan trọng:

- Target ban đầu chứa `OLD`, lỗi trước move: vẫn là `OLD`.
- Update bình thường: target là `NEW` và không có temp mồ côi.
- Atomic move unsupported: với flag fail-closed phải ném lỗi, không thay target.
- Fallback được cho phép: ghi nhận chất lượng bảo đảm thấp hơn, không gọi nó atomic.
- Metadata permissions/ACL sau replace đúng chính sách.
- Writer đồng thời: test quy tắc chống last-writer-wins.
- Reader mở trước và sau publish: hành vi thực tế theo OS.
- Không đủ dung lượng, không có quyền, target đang mở, directory read-only, lỗi cleanup.

JUnit Jupiter có `@TempDir` để tạo thư mục test riêng. Test unit stream bộ nhớ không đủ kiểm chứng OS-specific rename, ACL, lock và crash recovery.

### 13.3. Kiểm tra crash durability cần hạ tầng riêng

Một phép thử Java thành công không chứng minh điều gì xảy ra khi thiết bị mất điện ở microsecond giữa các bước. Với yêu cầu độ bền mạnh, cần protocol đã kiểm chứng cho filesystem/OS mục tiêu hoặc hệ thống có giao dịch, cùng test recovery và fault injection cô lập. Không xem `ATOMIC_MOVE` + `force(true)` là bằng chứng tuyệt đối cho mọi storage.

## 14. Các lỗi phổ biến

### Lỗi 1: ghi trực tiếp vào file gốc

`TRUNCATE_EXISTING` làm target mất nội dung cũ trước khi ghi đủ. **Sửa:** ghi candidate trong temp, validate, sync rồi mới publish.

### Lỗi 2: tạo temp ở ổ khác

Temp nằm trên `java.io.tmpdir` có thể khác filesystem. **Sửa:** dùng `Files.createTempFile(parent,...)`.

### Lỗi 3: dùng filename tạm cố định

Tạo `config.tmp` cố định dễ va chạm/race. **Sửa:** createTempFile tạo entry mới và luôn cleanup.

### Lỗi 4: xóa target rồi mới ATOMIC_MOVE

Tạo khoảng trống và có thể mất bản cũ. **Sửa:** không xóa target trước, dùng semantics replace được provider hỗ trợ.

### Lỗi 5: cho rằng REPLACE_EXISTING đảm bảo atomic replace khi đi kèm ATOMIC_MOVE

Khi có `ATOMIC_MOVE`, option khác bị bỏ qua; target đã có hành vi implementation-specific. **Sửa:** xử lý exception, xác minh provider thực tế.

### Lỗi 6: catch mọi IOException rồi copy vào target

Có thể làm target dở dang và che mất lỗi chính. **Sửa:** fallback chỉ theo chính sách rõ ràng, không được tự động hạ bảo đảm.

### Lỗi 7: không xử lý short write

`FileChannel.write` không hứa luôn ghi đủ buffer trong một lần. **Sửa:** lặp theo `remaining()`.

### Lỗi 8: tưởng force trước move đảm bảo crash durability

Sync temp không mặc định sync directory rename. **Sửa:** có chiến lược crash-consistency riêng nếu cần.

### Lỗi 9: không xét permission của file mới

Temp có metadata riêng; replace không nhất thiết giữ ACL/owner của target cũ. **Sửa:** áp policy metadata lên temp trước publish và kiểm tra.

### Lỗi 10: hai writer cùng ghi mà không phối hợp

Atomic rename không ngăn lost update. **Sửa:** single-writer, lock hoặc version/CAS/transaction.

### Lỗi 11: bỏ qua symlink và path traversal

Ghi tạm cùng directory không tự chặn attacker thay directory entry. **Sửa:** root tin cậy, validate tên, kiểm soát quyền và cơ chế secure directory handle khi cần.

### Lỗi 12: dọn temp sau khi ghi thất bại nhưng che lỗi gốc

`finally` có thể ném lỗi dọn. **Sửa:** giữ ngoại lệ gốc và thêm ngoại lệ cleanup vào `addSuppressed(...)` khi thích hợp; log temp mồ côi.

### Lỗi 13: không giới hạn dung lượng temp

Cần chỗ cho cả bản cũ và bản mới. **Sửa:** hạn mức dung lượng/size và xử lý disk-full.

### Lỗi 14: báo success trước khi publish

Nếu move thất bại sau khi server gửi ACK, caller có thông tin sai. **Sửa:** chỉ báo sau khi đạt điều kiện commit theo nghiệp vụ, có idempotency khi retry.

## 15. Bài tập tự kiểm tra

1. **Tại sao không nên dùng `Files.writeString(target, text)` trực tiếp với cấu hình quan trọng?** Có thể truncate/ghi dở nếu lỗi.
2. **Tại sao temp nên ở cùng parent?** Tăng cơ hội cùng filesystem để atomic move.
3. **`Files.createTempFile` tốt hơn filename cố định như thế nào?** Tạo entry mới không trùng, tránh nhiều lượt ghi vào cùng temp.
4. **`ATOMIC_MOVE` có luôn được hỗ trợ không?** Không; có thể ném `AtomicMoveNotSupportedException`.
5. **`ATOMIC_MOVE` đi cùng `REPLACE_EXISTING` có chắc thay target đã có?** Không; các option khác bị bỏ qua theo Java 17, việc thay target là implementation-specific.
6. **Có nên xóa target trước khi move?** Không, vì tạo khoảng không có target.
7. **Nếu atomicity là yêu cầu bắt buộc, xử lý unsupported thế nào?** Fail closed, không hạ xuống non-atomic.
8. **Vì sao cần vòng lặp ghi FileChannel?** `write` trả số byte thực ghi, có thể ít hơn remaining.
9. **`force(true)` trước rename có chứng minh rename durable khi mất điện không?** Không.
10. **Hai writer có thể gây lost update dù mỗi move atomic không?** Có.
11. **File mới có chắc kế thừa ACL/owner của target cũ không?** Không.
12. **Reader đã mở bản cũ có tự đổi sang bản mới sau rename không?** Không nên giả định.
13. **Fallback bằng Files.copy có bảo đảm tránh file dở không?** Không, có thể cập nhật từng phần.
14. **Nếu update ba file, ba atomic move có tạo transaction không?** Không.
15. **Nếu serializer thất bại, target phải ở trạng thái nào trước publish?** Vẫn là bản cũ theo giả định không có writer khác.
16. **Vì sao cần xác thực đường dẫn user nhập?** Temp strategy không ngăn path traversal/symlink race.
17. **Muốn kiểm thử lỗi trước publish nên làm thế nào?** Fault injection ở điểm sau khi ghi temp, trước move; đối chiếu file target và cleanup.
18. **Tại sao mất điện sau move nhưng trước response khó xử lý?** Caller có thể không biết commit đã xảy ra; cần version/idempotency.
19. **Khi nào nên chọn database?** Khi cần transaction nhiều đối tượng, optimistic locking/CAS hoặc durability mạnh.
20. **Việc file mới lớn gấp đôi gây vấn đề gì?** Cần thêm dung lượng tạm thời để giữ cả bản cũ và bản mới.

## 16. Tài liệu Java 17 tham khảo

- [Files.move](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#move(java.nio.file.Path,java.nio.file.Path,java.nio.file.CopyOption...)): hợp đồng move và ATOMIC_MOVE.
- [StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html): ATOMIC_MOVE, REPLACE_EXISTING.
- [Files.createTempFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#createTempFile(java.nio.file.Path,java.lang.String,java.lang.String,java.nio.file.attribute.FileAttribute...)): tạo temp trong directory chỉ định.
- [FileChannel.force](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#force(boolean)): yêu cầu đồng bộ dữ liệu và metadata file.
- [FileChannel.write](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html#write(java.nio.ByteBuffer)): số byte thực ghi.
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): thao tác theo directory handle khi provider hỗ trợ.

**Ghi nhớ:** Để cập nhật một file mà không đưa bản đang ghi dở tới reader, hãy **tạo temp cùng thư mục → ghi/verify/force phù hợp → đóng → move nguyên tử nếu được hỗ trợ → dọn temp**. Không tự xóa target trước, không tự hạ bảo đảm sang copy/non-atomic và không đồng nhất atomic visibility với crash durability, transaction hay kiểm soát multi-writer.
