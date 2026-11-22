# Giải phóng FileLock khi đóng tài nguyên trong Java NIO

Khi nhiều chương trình cùng thao tác trên một file, Java NIO cung cấp `FileChannel.lock()` và `tryLock()` để yêu cầu **khóa một vùng byte của file**. Đối tượng `java.nio.channels.FileLock` biểu diễn khóa đã nhận. Khóa cần có **vòng đời rõ ràng**: nhận khóa → thực hiện công việc trong phạm vi bảo vệ → giải phóng khóa → đóng channel. Nếu tài nguyên bị đóng sớm, khóa cũng mất hiệu lực; nếu không giải phóng đúng lúc, chương trình khác có thể phải chờ lâu hoặc không lấy được khóa.

Điểm cốt lõi: **một `FileLock` được giải phóng khi gọi `release()`/`close()`, hoặc khi đóng channel đã cấp khóa, hoặc khi JVM kết thúc — tùy sự kiện nào xảy ra trước.** Tuy nhiên, khi điều phối nhiều luồng/tiến trình và trên các filesystem khác nhau, phải hiểu thêm phạm vi khóa, quy tắc của hệ điều hành và cách xử lý ngoại lệ.

## 1. Vai trò của FileChannel và FileLock

Hai đối tượng có vai trò khác nhau:

- **`FileChannel`**: handle mở để đọc/ghi một file. Channel cung cấp `lock(...)` hoặc `tryLock(...)` để xin khóa và quản lý tài nguyên I/O.
- **`FileLock`**: token đại diện **một khóa đang được giữ**, có vùng byte `position()` và `size()`, chế độ `isShared()` và trạng thái `isValid()`.

Một `FileLock` hợp lệ chỉ khi khóa còn tồn tại và channel tương ứng vẫn mở; `isValid()` cho biết trạng thái khóa **ở thời điểm kiểm tra**, không phải cam kết nó sẽ vẫn hợp lệ mãi về sau.

```text
FileChannel.open(...)
        |
        v
    channel.lock() ------------> FileLock (valid)
        |                            |
        |                            | release() hoặc close()
        |                            v
        |                       FileLock (invalid)
        |
        +-- channel.close() -------> mọi lock cấp từ channel được giải phóng
                                     (invalid)

JVM kết thúc ---------------------> các khóa do JVM giữ được giải phóng
```

Khóa không làm file tự động được ghi bền vững xuống thiết bị, không sao lưu nội dung và không cung cấp transaction. Một khóa được giữ đúng vẫn có thể đi cùng dữ liệu chưa flush, chưa `force()`, hoặc mới chỉ được ghi một phần. **Quản lý khóa** và **quản lý độ bền dữ liệu** là hai trách nhiệm bổ sung cho nhau.

## 2. Ba con đường giải phóng khóa

Theo hợp đồng `FileLock`:

| Hành động | Tác động lên khóa | Tác động lên channel |
| --- | --- | --- |
| `lock.release()` | Giải phóng khóa hợp lệ; sau đó `isValid() == false`. | Channel vẫn mở nếu không bị đóng riêng. |
| `lock.close()` | Gọi `release()`; thích hợp với `try-with-resources`. | Channel vẫn mở. |
| `channel.close()` | Giải phóng các khóa nhận qua chính channel, khiến chúng không còn hợp lệ. | Channel đóng; không thể dùng để I/O tiếp. |
| JVM kết thúc | Các khóa đang giữ của JVM được hệ điều hành giải phóng. | Toàn bộ tài nguyên của tiến trình kết thúc. |

Thứ tự thực hành nên là **giải phóng `FileLock` trước, đóng `FileChannel` sau**. Dù đóng channel cũng giải phóng khóa, cách đóng tuần tự giúp giới hạn vùng được bảo vệ và làm chủ thời điểm giải phóng.

Sau khi `FileLock` mất hiệu lực, không sử dụng nó như một bằng chứng rằng tài nguyên vẫn bị khóa. Mở lại channel sau đó không làm token `FileLock` cũ hợp lệ trở lại: muốn có khóa mới phải **gọi `lock()`/`tryLock()` mới**.

**Đừng trông chờ chương trình tự giải phóng khi garbage collector chạy.** Sử dụng `try-with-resources` hoặc `finally`. JVM kết thúc là cơ chế thu hồi cuối cùng, không phải chiến lược quản lý lock cho ứng dụng chạy lâu.

## 3. Mẫu try-with-resources chuẩn: đóng lock trước channel

Dạng ngắn và an toàn về vòng đời:

```java
// Snippet: file là java.nio.file.Path đã tồn tại hoặc được tạo.
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    // Chỉ làm việc cần được bảo vệ ở bên trong khối này.
    // Nếu cần ghi dữ liệu, channel phải có quyền WRITE.
}
```

Đoạn trên là **snippet**; cần import `FileChannel`, `FileLock` và `StandardOpenOption`. Không chạy độc lập vì biến `file` được định nghĩa ở ngữ cảnh bên ngoài.

**Tại sao thứ tự khai báo quan trọng?**

1. `try-with-resources` khởi tạo từ trái sang phải: mở `FileChannel` rồi xin `FileLock`.
2. Khi thoát khối, Java đóng **theo thứ tự ngược lại**: gọi `lock.close()` trước, rồi `channel.close()`.
3. Nếu code bên trong ném exception, Java **vẫn** thực hiện đóng cả hai tài nguyên. Ngoại lệ khi đóng được quản lý theo cơ chế suppressed exceptions; lỗi chính không bị tùy tiện thay thế bằng lỗi đóng.
4. Nếu `channel.lock()` ném exception trước khi tạo được `FileLock`, tài nguyên `channel` đã được khởi tạo thành công vẫn được đóng tự động.

Nếu chỉ mở channel rồi `channel.lock()` nhưng **quên giữ và giải phóng token**, khóa sẽ tồn tại đến khi channel đóng. Đối với một channel sống lâu (ví dụ gắn với một service), điều đó có thể làm các tiến trình hợp tác phải chờ quá thời gian mong muốn.

## 4. Ví dụ Java 17+ đầy đủ: release tường minh và giải phóng khi đóng channel

Ví dụ tạo file tạm riêng, nhận khóa trên một `FileChannel`, kiểm tra trạng thái trước/sau khi `FileLock` tự đóng; tiếp đó nhận một khóa khác và để việc đóng channel giải phóng khóa.

Lưu thành **`LockLifecycleDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class LockLifecycleDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lock-lifecycle-", ".bin");
        try {
            FileLock releasedExplicitly;
            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                try (FileLock lock = channel.lock()) {
                    releasedExplicitly = lock;
                    System.out.println("during lock: " + lock.isValid());
                    channel.write(ByteBuffer.wrap(new byte[] {65, 66, 67}));
                }
                System.out.println("after FileLock.close: "
                        + releasedExplicitly.isValid());
            }

            FileLock releasedByChannel;
            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                releasedByChannel = channel.lock();
                System.out.println("before channel.close: "
                        + releasedByChannel.isValid());
                // Khi channel đóng, lock của channel tự được giải phóng.
            }
            System.out.println("after channel.close: "
                    + releasedByChannel.isValid());
            System.out.println("bytes: " + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy trên JDK 17+ có filesystem hỗ trợ `FileLock`:

```bash
javac -encoding UTF-8 LockLifecycleDemo.java
java LockLifecycleDemo
```

Stdout (đã đối chiếu bằng chương trình Java chạy thực tế):

```text
during lock: true
after FileLock.close: false
before channel.close: true
after channel.close: false
bytes: 3
```

**Diễn giải:**

- Lần đầu, `channel.lock()` xin khóa **exclusive** cho toàn bộ vùng khóa mặc định; `isValid()` trả `true` trong khối. `ByteBuffer` chứa ba byte `A B C` và `channel.write(...)` ghi chúng vào file.
- Khi rời khối `try (FileLock lock = ...)`, `lock.close()` tự gọi `release()`. Token `releasedExplicitly` đã mất hiệu lực, dù `channel` vẫn đang mở.
- Lần hai mở một channel mới trên cùng file. Khóa mới `releasedByChannel` được giữ đến khi `try (FileChannel channel = ...)` kết thúc. Không gọi `release()` riêng trong đoạn này để minh họa cơ chế **đóng channel giải phóng lock**.
- Sau khi đóng channel, `releasedByChannel.isValid()` là `false`. File có đúng ba byte vì chương trình chỉ ghi ba byte ở phiên đầu.

Ví dụ dùng một tiến trình, chạy tuần tự và không có writer cạnh tranh. Nếu OS/filesystem không hỗ trợ loại khóa được yêu cầu, việc nhận lock có thể thất bại; chương trình khi đó sẽ ném exception thay vì in đủ stdout trên.

## 5. Dùng release() trong finally khi không dùng try-with-resources

Nếu cấu trúc ứng dụng bắt buộc quản lý thủ công, giữ token và giải phóng trong `finally`:

```java
// Snippet: channel là FileChannel đang mở với WRITE.
FileLock lock = null;
try {
    lock = channel.lock();
    // Thao tác được bảo vệ ở đây.
} finally {
    if (lock != null && lock.isValid()) {
        lock.release();
    }
}
```

Đây là đoạn minh họa, yêu cầu `IOException` được xử lý hoặc truyền ra ngoài. `finally` chạy dù logic trong khối `try` phát sinh exception, nhưng **không phải** bảo đảm tuyệt đối trước việc tiến trình bị kill hoặc JVM dừng đột ngột. Nếu `release()` tự ném `IOException`, cần xử lý lỗi một cách có chủ đích; code nghiệp vụ quan trọng không nên bị che khuất trong log.

Nếu cả channel do hàm này sở hữu, cũng phải đóng channel trong `finally` hoặc `try-with-resources`. Không nên gọi `release()` sau khi channel đã đóng rồi dựa vào đó để “giải phóng lần nữa”. Theo hợp đồng `FileLock`, `release()` trên token không hợp lệ không còn thao tác khóa thực sự, và API còn quy định ngoại lệ trong một số trường hợp channel đóng; cách rõ ràng nhất là đóng lock **trước** khi đóng channel.

Dùng `try-with-resources` thường giúp code gọn hơn và xử lý cả trường hợp nhận khóa thất bại trong quá trình khởi tạo tài nguyên.

## 6. Thời điểm khóa còn hiệu lực: phạm vi critical section

Ví dụ cập nhật một số đếm trong file:

```text
Đúng về phạm vi:
xin lock ──> đọc dữ liệu cũ ──> tính toán ──> ghi dữ liệu mới
                                               |
                                               v
                                           giải phóng lock

Dễ bị race:
xin lock ──> đọc ──> giải phóng lock ──> tính toán ──> ghi
                          ^                            ^
                          |                            |
                 Writer khác có thể thay đổi file giữa hai bước
```

Khóa phải được giữ cho **toàn bộ chuỗi read-modify-write** khi các writer cần thấy thao tác như một critical section. Việc chỉ khóa riêng lần đọc rồi đóng lock trước lần ghi vẫn để lại khoảng trống cạnh tranh.

Nhưng **khóa đúng phạm vi không đồng nghĩa transaction**. Nếu tiến trình chết giữa lần ghi, có thể tồn tại dữ liệu dở dang dù tại thời điểm ghi chỉ có một writer hợp tác. Với dữ liệu cần phục hồi, phải thêm record framing/checksum, file tạm và chiến lược commit/rollback phù hợp.

Hạn chế giữ khóa trong khi làm việc tốn thời gian không liên quan như gọi HTTP, chờ người dùng nhập liệu hoặc sleep dài. Tính toán trước phần có thể làm ngoài critical section, rồi chỉ giữ khóa cho đoạn cần đọc trạng thái mới nhất và cập nhật.

## 7. lock() và tryLock(): khác nhau về cách chờ, giống về trách nhiệm giải phóng

`FileChannel.lock()` là lệnh **chờ** cho đến khi vùng được khóa, channel bị đóng hoặc luồng đang đợi bị interrupt. `tryLock()` **không chờ**: hoặc nhận `FileLock`, hoặc trả `null` nếu chương trình/tiến trình khác đã giữ khóa xung đột; trong những tình huống lỗi khác nó có thể ném exception.

Mẫu `tryLock` an toàn:

```java
// Snippet: channel mở với WRITE và chưa có khóa trùng trong JVM.
FileLock lock = channel.tryLock();
if (lock == null) {
    System.out.println("File đang được tiến trình khác sử dụng");
} else {
    try (lock) {
        // Critical section: chỉ chạy khi có khóa.
    }
}
```

Biến resource `lock` trong `try(lock)` hỗ trợ từ Java 9 nếu biến cuối cùng hoặc effectively final; ở ví dụ này không đổi giá trị sau khi gán. Không dùng token `null` để đi vào critical section.

Các trường hợp cần phân biệt:

| Tình trạng | Hành vi thường gặp |
| --- | --- |
| Một process khác giữ khóa xung đột | `lock()` chờ; `tryLock()` trả `null`. |
| Chính JVM đang giữ lock trùng vùng trên cùng file | `OverlappingFileLockException`, kể cả khi dùng channel khác trong JVM. |
| Cố xin exclusive lock bằng channel không có quyền ghi | `NonWritableChannelException`. |
| Cố xin shared lock bằng channel không có quyền đọc | `NonReadableChannelException`. |
| Channel đã đóng | `ClosedChannelException`. |
| Đóng channel khi một thread đang chờ `lock()` | Có thể ném `AsynchronousCloseException`. |
| Interrupt thread trong lúc chờ `lock()` | Có thể ném `FileLockInterruptionException`; trạng thái interrupt được thiết lập. |

Không nên “sửa” `OverlappingFileLockException` bằng vòng lặp `tryLock` bận vô hạn. Vì `FileLock` được nắm giữ **ở cấp JVM**, nhiều thread trong cùng JVM phải có cơ chế đồng bộ cấp ứng dụng khác (`synchronized`, `ReentrantLock`, một hàng đợi writer). File lock chủ yếu là cơ chế phối hợp **giữa các process** có tôn trọng giao thức khóa.

## 8. Khóa toàn file và khóa vùng byte

`channel.lock()` có ý nghĩa tương đương:

```java
FileLock lock = channel.lock(0L, Long.MAX_VALUE, false);
```

Trong đó `position=0`, `size=Long.MAX_VALUE`, `shared=false`; đây là yêu cầu **exclusive**. Đoạn chỉ minh họa, cần đóng/release `lock` sau khi xử lý.

Khi cần khóa một phân vùng dữ liệu:

```java
// Snippet: khóa vùng [100, 200) bằng channel ghi được.
try (FileLock lock = channel.lock(100L, 100L, false)) {
    // Chỉ thao tác với phần file theo quy ước khóa vùng của ứng dụng.
}
```

Phạm vi là `[position, position + size)`, tức điểm cuối **không thuộc** vùng đã khóa. Vùng khóa có thể vượt qua EOF; nó không tự mở rộng nội dung file. Một lock có `size` xác định không tự mở rộng cùng file; nếu file lớn thêm vượt phạm vi, phần mới không được che phủ.

Các hàm hỗ trợ `FileLock`:

- `position()`: vị trí bắt đầu.
- `size()`: kích thước vùng bị khóa.
- `overlaps(start, length)`: kiểm tra hai vùng có giao nhau không; nó không xin lock mới.
- `isShared()`: xác nhận lock đã nhận thuộc chế độ shared/exclusive. Một số nền tảng có thể chuyển yêu cầu shared thành exclusive.
- `acquiredBy()`: trả channel đã cấp khóa; với `FileChannel` có thể dùng `channel()`.

Không nên mặc định có thể chia file thành nhiều vùng khóa độc lập trên mọi filesystem; giới hạn native locking khác nhau theo nền tảng, đặc biệt là network filesystem.

## 9. Cạm bẫy: đóng channel khác có thể làm mất lock

Đây là khác biệt nền tảng được **JDK cảnh báo rõ**: trên một số hệ thống, **đóng một channel tới cùng file** có thể giải phóng **mọi file lock do JVM đang giữ trên file đó**, kể cả khóa được xin bằng **channel khác**.

Tình huống khái niệm:

```text
channel A ── lock vùng [0, 100) ──> lockA còn được kỳ vọng là valid
channel B ── cùng underlying file ──> đóng channel B
                                    |
                                    v
                Trên một số OS, lockA cũng có thể bị giải phóng.
```

Đây là hành vi **phụ thuộc hệ điều hành**; không đưa ra output cố định cho thí nghiệm này. Không suy rằng việc `lockA.isValid() == true` luôn tiếp tục đúng sau khi mọi channel khác đóng.

Hướng thiết kế được khuyến nghị:

1. Trong mỗi chương trình, ưu tiên **một channel do một thành phần sở hữu việc xin tất cả lock trên cùng file**.
2. Xác định rõ người sở hữu channel và người sở hữu khóa; tránh hàm phụ bất ngờ mở và đóng channel thứ hai lên cùng file đang khóa.
3. Khi cần nhiều thread truy cập, điều phối qua service quản lý channel hoặc đồng bộ trong JVM thay vì mỗi thread mở channel và tranh cùng vùng lock.
4. Không dựa vào một bài test nhỏ trên một OS để cam kết tính tương thích trên mọi platform.

Lưu ý rằng đóng channel **đã cấp lock** luôn giải phóng lock đó theo hợp đồng. Còn đóng **channel khác** có ảnh hưởng tới lock kia hay không mới là điểm không portable.

## 10. Shared lock, exclusive lock và giới hạn của OS

Hai chế độ:

- **Exclusive lock:** yêu cầu khóa độc quyền, không cho các process hợp tác lấy shared/exclusive lock trùng vùng trong thời gian nó còn hiệu lực.
- **Shared lock:** nhiều chương trình có thể cùng xin shared lock trên một vùng, nhưng xung đột với yêu cầu exclusive.

Để xin shared lock:

```java
// Snippet: channel cần được mở với READ.
try (FileLock lock = channel.lock(0L, Long.MAX_VALUE, true)) {
    System.out.println("shared actually: " + lock.isShared());
}
```

Một số platform không hỗ trợ shared lock: yêu cầu shared có thể bị chuyển thành exclusive. Vì thế kiểm tra `lock.isShared()` nếu chế độ thực tế có ý nghĩa đối với ứng dụng. Exclusive lock đòi channel có quyền ghi; shared lock đòi channel có quyền đọc.

**Không coi FileLock là hàng rào bảo mật tuyệt đối.** Trên một số OS, khóa là *advisory*: process không hợp tác vẫn có thể đọc/ghi file. Trên OS khác, khóa có thể ảnh hưởng bắt buộc tới các thao tác file; một số cấu hình/file system có thể có hạn chế mapping và locking đồng thời. Khi cần bảo vệ dữ liệu khỏi truy cập trái phép, dùng permission/ACL, kiểm soát danh tính và ranh giới hệ thống; file locking không thay thế chúng.

Đặc biệt trên NFS/SMB/network share, việc cấp/thu hồi lock có thể chịu ảnh hưởng giao thức và cấu hình máy chủ. Đưa việc kiểm thử lock timeout, reconnect, crash và quyền truy cập vào môi trường triển khai thực tế.

## 11. Đóng tài nguyên an toàn khi xảy ra exception

Một chương trình ghi file cần xử lý cả **lỗi công việc** và **lỗi dọn tài nguyên**. Nếu dùng `try-with-resources`, Java đóng tài nguyên theo thứ tự ngược với lúc khai báo. Nếu thân `try` ném exception và `close()` cũng ném exception, lỗi đóng thường được gắn vào lỗi chính dưới dạng **suppressed**.

Ví dụ mẫu:

```java
try (FileChannel channel = FileChannel.open(
        file, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    writeRecord(channel);  // Có thể ném IOException.
} // FileLock.close() rồi FileChannel.close().
```

Đây là snippet; `file` và `writeRecord` phải được cung cấp bởi chương trình. Chương trình không cần viết `catch` để đảm bảo khóa được giải phóng. Nếu muốn ghi log lỗi kỹ lưỡng, có thể log `ex.getSuppressed()` bên cạnh exception chính.

**Lưu ý tránh deadlock nghiệp vụ:**

- Không giữ lock trong khi chờ một tác vụ khác cũng đang cần lock vùng trùng nhau.
- Không nhận nhiều khóa trên nhiều file theo thứ tự tùy ý giữa các process; quy định **thứ tự cố định** để giảm deadlock.
- Không chờ vô hạn khi ứng dụng có deadline: `lock()` có thể đợi. Thiết kế retry/backoff theo deadline với `tryLock()`, nhưng không polling quá nhanh.
- Nếu yêu cầu dừng tác vụ, xử lý interrupt và việc đóng channel với hiểu biết rằng thao tác `lock()` đang chờ có thể bị gián đoạn và ném exception.

Đóng lock sớm giúp giảm thời gian chiếm tài nguyên của hệ thống, nhưng phải đảm bảo tất cả công việc được bảo vệ đã hoàn thành.

## 12. Khóa và độ bền dữ liệu: release không đồng nghĩa commit

Giả sử chương trình chỉ có một writer được khóa hợp lệ. Khi thực hiện:

```java
try (FileLock lock = channel.lock()) {
    while (buffer.hasRemaining()) {
        channel.write(buffer);
    }
    channel.force(true);
}
```

đây là snippet dùng `channel` và `buffer` đã khai báo. `force(true)` yêu cầu các cập nhật nội dung và metadata phù hợp được đẩy xuống thiết bị lưu trữ theo hợp đồng `FileChannel`, với bảo đảm cụ thể phụ thuộc việc thiết bị là **cục bộ** hay **không cục bộ**.

Phân biệt rõ:

| Sự kiện | Nó làm gì | Nó không làm gì |
| --- | --- | --- |
| `lock.release()` / `lock.close()` | Giải phóng quyền giữ vùng lock. | Không bắt buộc dữ liệu đã được flush/sync xuống ổ đĩa. |
| `channel.close()` | Đóng handle, giải phóng các lock của channel. | Không tạo ra transaction có rollback. |
| `channel.force(false)` | Yêu cầu ghi các thay đổi nội dung thích hợp xuống thiết bị. | Không làm nhiều lần ghi trở thành atomic. |
| `channel.force(true)` | Yêu cầu cả content và metadata thích hợp. | Không xác nhận record có schema hợp lệ hoặc checksum đúng. |
| `SYNC` / `DSYNC` | Tùy chọn mở file yêu cầu đồng bộ dữ liệu khi cập nhật. | Không thay thế lock, record framing hay cơ chế commit. |

Nếu file chứa nhiều record, dùng thêm length-prefix, checksum, version, journal hoặc chiến lược thay file tạm tùy yêu cầu. Trong hệ thống yêu cầu crash consistency mạnh, một thao tác `write` thành công không có nghĩa toàn bộ chuỗi read-modify-write đã commit nguyên tử.

Việc sắp xếp `force` **trước khi** rời critical section có thể hợp lý khi writer khác chỉ được phép tiếp tục sau khi dữ liệu được yêu cầu đồng bộ, nhưng chi phí có thể cao. Phải chọn đúng yêu cầu nghiệp vụ; không nhất thiết force mỗi record nếu độ bền định kỳ là đủ.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Process khác chờ khóa mãi | Quên `release` và channel vẫn sống lâu, hoặc critical section quá lớn. | Dùng `try-with-resources`, thu hẹp phạm vi, chọn deadline. |
| `isValid() == false` dù không tự gọi `release()` | Channel cấp khóa đã đóng, JVM kết thúc hoặc hệ thống thu hồi lock. | Rà soát vòng đời channel; nhận lock mới nếu cần. |
| Có lock nhưng process khác vẫn sửa file | Hệ điều hành dùng advisory locking hoặc process không hợp tác. | Yêu cầu mọi writer tuân thủ giao thức, kết hợp quyền truy cập. |
| `OverlappingFileLockException` | JVM đã có lock trùng vùng hoặc thread khác đang chờ lock trùng. | Dùng đồng bộ cấp JVM; tránh tranh cùng file trong một JVM. |
| `tryLock() == null` | Lock xung đột do process khác giữ. | Bỏ qua tác vụ, báo bận hoặc retry theo deadline/backoff. |
| `NonWritableChannelException` | Xin exclusive lock trên channel không có quyền ghi. | Mở channel với WRITE. |
| `NonReadableChannelException` | Xin shared lock trên channel không có quyền đọc. | Mở channel với READ. |
| `ClosedChannelException` | Channel đóng trong khi xin hoặc dùng lock. | Quản lý sở hữu tài nguyên, không sử dụng channel sau close. |
| Lock khác bị mất khi đóng channel phụ | Một số OS gắn lock theo file và có chính sách release rộng hơn. | Dùng channel quản lý lock duy nhất mỗi file trong chương trình. |
| Dữ liệu vẫn hỏng dù có lock | Ghi dở dang, crash, thiếu framing/transaction. | Dùng định dạng và khôi phục phù hợp, `force` theo chính sách. |

Một lỗi review phổ biến là đặt `FileChannel` trong `try-with-resources` quá **ngắn** so với khối logic cần được bảo vệ, rồi đưa việc ghi/cập nhật quan trọng ra ngoài sau khi channel đã đóng. Việc có dòng `channel.lock()` trong code chưa đủ: **thời điểm giải phóng lock quyết định chính xác đoạn mã nào có thể được bảo vệ**.

## 14. Bài tập thực hành

**Bài tập 1 — Quan sát trạng thái khóa.** Chạy ví dụ `LockLifecycleDemo` và ghi lại các điểm `isValid()` chuyển `true → false`. Thử chuyển chương trình sang một dạng `try (FileChannel channel = ...; FileLock lock = channel.lock())` và xác nhận thứ tự đóng ngược với thứ tự khai báo.

**Bài tập 2 — Chạy hai process.** Viết process A xin exclusive lock, chờ tín hiệu người dùng rồi thoát khỏi `try`. Process B dùng `tryLock()` kiểm tra trước, trong và sau lúc A giữ lock. Trên filesystem hỗ trợ, B sẽ nhận `null` khi A giữ khóa và có thể xin được sau khi A giải phóng. Không cần dùng sleep cố định để giả lập thời điểm giao nhau; dùng tín hiệu/sự kiện thử nghiệm.

**Bài tập 3 — Bảo vệ read-modify-write.** Lưu một số `long` tại offset 0 của file; cho hai process cùng đọc, cộng một, ghi lại. Yêu cầu giữ lock xuyên suốt việc đọc + ghi, sau đó so sánh với tình huống giải phóng lock trước khi ghi. Vì sao một lần đọc hoặc ghi riêng lẻ có thể vẫn thành công nhưng kết quả cuối sai?

**Bài tập 4 — Khóa vùng.** Chia file thành hai vùng byte không chồng lấn, xin lock riêng cho từng vùng và quan sát behavior theo OS. Kiểm tra `FileLock.overlaps` trên các khoảng `[0, 100)`, `[100, 200)`, `[50, 150)`. Giải thích vì sao hai vùng chạm ở biên nhưng không overlap.

**Bài tập 5 — Lỗi giữa critical section.** Sau khi nhận lock, chủ động ném một `IOException` thử nghiệm. Đảm bảo `try-with-resources` giải phóng tài nguyên và một process hợp tác có thể xin lock về sau. Bổ sung log cho suppressed exceptions khi dọn tài nguyên.

**Bài tập 6 — Durability.** Tạo một chương trình ghi đầy đủ record có checksum và gọi `channel.force(true)` trước khi `lock.close()`. Phân biệt được điều gì nếu chỉ giải phóng lock mà không force, và vì sao ngay cả force cũng không làm chuỗi ghi thành transaction.

## 15. Checklist khi đưa vào ứng dụng

- File/channel được mở với quyền phù hợp loại lock (exclusive cần WRITE, shared cần READ).
- Ai sở hữu và đóng `FileChannel`? Ai sở hữu và đóng `FileLock`? Có mở một channel thứ hai cùng file ngoài dự kiến không?
- Toàn bộ phần cần đồng bộ đã nằm **bên trong** critical section chưa? Có giữ lock qua gọi mạng hoặc chờ lâu không?
- Có dùng `try-with-resources`/`finally` và xử lý tốt các exception khi nhận/đóng lock không?
- Nhiều thread cùng JVM đã có đồng bộ riêng chưa? Các process không cùng JVM đã cùng tuân thủ protocol lock chưa?
- Nền tảng chạy thật có hỗ trợ loại lock/vùng lock theo yêu cầu không? Tác vụ có deadline hoặc kế hoạch timeout/retry không?
- Đã phân biệt **giải phóng lock**, **đóng channel**, **đồng bộ dữ liệu** và **transaction** chưa?
- Có kiểm tra quy trình recovery nếu tiến trình chết sau khi ghi một phần nhưng trước khi `release()`/`force()` không?

## 16. Tài liệu tham khảo chính thức

- [Java SE 21 — FileLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): điều kiện khóa hợp lệ, `release()`, `close()`, trạng thái và các giới hạn phụ thuộc nền tảng.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): `lock()`, `tryLock()`, `force()`, khóa vùng, lỗi và lifecycle.
- [Java SE 21 — try-with-resources](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): thứ tự và cách Java tự đóng tài nguyên.

**Ghi nhớ:** `FileLock` là tài nguyên `AutoCloseable`. Dùng `try-with-resources` để giải phóng khóa **trước khi** đóng channel; đóng channel cấp khóa cũng làm khóa mất hiệu lực. Tổ chức ownership rõ ràng, không trộn nhiều channel xin khóa cùng file tùy tiện, và đừng đánh đồng lock release với durable commit.
