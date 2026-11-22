# File lock thuộc phạm vi JVM, không thay thế khóa giữa các luồng

## 1. Hai loại cạnh tranh khi truy cập tệp

Trong Java NIO, `FileLock` được dùng để phối hợp truy cập tệp hoặc vùng byte của tệp, đặc biệt khi **nhiều tiến trình** cùng quan tâm tới một tài nguyên. Nhưng ứng dụng Java còn có thể chạy **nhiều thread trong cùng JVM**. Hai bài toán cần cơ chế khác nhau:

- **Đồng bộ trong JVM:** tổ chức các thao tác đọc–sửa–ghi giữa thread, bảo vệ các object Java và tạo quan hệ happens-before về bộ nhớ. Dùng `synchronized`, `ReentrantLock` hoặc cơ chế đồng bộ phù hợp.
- **Phối hợp giữa các tiến trình:** dùng `FileChannel.lock(...)`/`tryLock(...)` để yêu cầu khóa vùng byte, theo khả năng filesystem/hệ điều hành. Mọi chương trình tham gia cần tuân thủ cùng giao thức khóa, nhất là khi khóa là advisory.

Một file lock được giữ **thay mặt cho toàn bộ JVM**. Nó không phải một monitor hay một mutex dành cho từng Java thread. Vì thế, theo hợp đồng `java.nio.channels.FileLock`, **file lock không phù hợp để kiểm soát truy cập tệp giữa các thread trong cùng JVM**.

~~~text
                  CÙNG JVM A                             JVM B
      +--------------------------------+             +----------+
      | Thread A       Thread B        |             | Process B|
      |    \              /            |             +-----+----+
      |     \            /             |                   |
      |   synchronized / ReentrantLock |                   |
      |       bảo vệ critical section  |                   |
      |                |               |                   |
      |         FileChannel.lock() ----+-------+-----------+
      +--------------------------------+       |
                                     Hệ điều hành / filesystem
                               file lock có khả năng phối hợp tiến trình
~~~

**File lock không tự khóa các biến, collection hay buffer Java.** File lock cũng không bảo đảm ứng dụng ngoài JVM phải tuân thủ nếu hệ điều hành triển khai advisory locking.

## 2. API FileChannel và FileLock

Các phương thức chính của `FileChannel`:

~~~java
FileLock lock() throws IOException;
FileLock lock(long position, long size, boolean shared) throws IOException;

FileLock tryLock() throws IOException;
FileLock tryLock(long position, long size, boolean shared)
        throws IOException;
~~~

Đây là các **chữ ký minh họa API**, chưa phải chương trình chạy độc lập.

`lock()` yêu cầu khóa độc quyền vùng byte bắt đầu từ offset 0, có độ dài `Long.MAX_VALUE`. `lock(position, size, shared)` yêu cầu một vùng chỉ định:

- `position` là byte offset bắt đầu, không âm.
- `size` là chiều dài vùng byte, không âm; offset và chiều dài phải hợp lệ.
- `shared = false` yêu cầu exclusive lock.
- `shared = true` yêu cầu shared lock, nếu nền tảng/provider hỗ trợ. Nếu shared lock không được hỗ trợ, provider có thể cấp exclusive lock; dùng `FileLock.isShared()` để biết loại đã nhận thực tế.

`FileLock` cung cấp `position()`, `size()`, `isShared()`, `isValid()`, `release()` và `channel()`. Không coi `FileLock.position()` là `FileChannel.position()`: cái thứ nhất nói về điểm bắt đầu của **vùng khóa**, cái thứ hai nói về vị trí **đọc/ghi tương đối hiện tại**.

### lock và tryLock khác nhau

| Trạng thái | `lock(...)` | `tryLock(...)` |
| --- | --- | --- |
| Có thể cấp khóa | Trả `FileLock` | Trả `FileLock` |
| Khóa xung đột đang do tiến trình khác giữ | Có thể chờ (hoặc thất bại khi bị gián đoạn/lỗi) | Trả `null` nếu không thể cấp ngay |
| Vùng khóa chồng lấn với khóa đã giữ hoặc đang chờ **trong cùng JVM** | `OverlappingFileLockException` | `OverlappingFileLockException` |
| Channel không có quyền hoặc có lỗi I/O | Ngoại lệ tương ứng | Ngoại lệ tương ứng |

**Đừng nhầm `tryLock() == null` với mọi dạng tranh chấp.** Khi chính JVM hiện tại có một lock trùng vùng, `tryLock` sẽ ném `OverlappingFileLockException`, thay vì trả `null` để thread có thể âm thầm chờ.

## 3. Phạm vi JVM thể hiện ở đâu?

Giả sử JVM mở hai `FileChannel` riêng biệt tới cùng tệp:

~~~text
FileChannel A ── lock [0, 100) ── đã lấy
FileChannel B ── tryLock [0,100) ── trùng vùng, cùng JVM
~~~

Một lần thử khóa trùng vùng trên B sẽ bị phát hiện và ném `OverlappingFileLockException`. Điều này có thể xảy ra dù A và B thuộc hai thread khác nhau. JVM **không** xem mỗi channel hoặc mỗi thread là một chủ khóa độc lập cho mục đích chồng lấn file lock.

Phạm vi khóa byte được biểu diễn theo khoảng nửa mở:

~~~text
A: [0,100)       gồm offset 0 đến 99
B: [100,200)     không chồng lấn A
C: [50,150)      chồng lấn cả A và B
~~~

Hai vùng không chồng lấn có thể được khóa riêng theo khả năng provider. Khóa không nhất thiết phải chỉ nằm trong kích thước tệp hiện hữu. Ví dụ khóa `[0, Long.MAX_VALUE)` có thể được lấy ngay cả khi file đang rỗng.

Khả năng phát hiện lock trong cùng JVM **không** biến `FileLock` thành mutex nội bộ, vì:

1. Một thread khác trong cùng JVM **không tự bị monitor chặn** khi đọc/ghi dữ liệu hoặc sửa state của chương trình.
2. Nếu thread đó yêu cầu lock trùng vùng, nó có thể **nhận ngoại lệ ngay**, không xếp hàng chờ như khi dùng `ReentrantLock.lock()`.
3. File lock không cung cấp đầy đủ quan hệ happens-before cho mọi biến Java đang được thread thao tác.
4. Thread khác có thể sử dụng một channel khác mà không tuân thủ giao thức khóa; mức ngăn cản truy cập trực tiếp phụ thuộc hệ điều hành/provider.

## 4. Ví dụ Java 17+: hai channel trong một JVM

Chương trình dùng tệp tạm, có hai channel trong **cùng một tiến trình Java**. Nó lấy khóa bằng channel thứ nhất, thử khóa vùng trùng bằng channel thứ hai, rồi giải phóng khóa thứ nhất để chứng minh vùng đó có thể được cấp lại.

Lưu thành `JvmFileLockDemo.java`:

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class JvmFileLockDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lock-demo-", ".bin");

        try {
            try (FileChannel first = FileChannel.open(
                        file, StandardOpenOption.READ, StandardOpenOption.WRITE);
                 FileChannel second = FileChannel.open(
                        file, StandardOpenOption.READ, StandardOpenOption.WRITE)) {

                try (FileLock held = first.lock()) {
                    System.out.println("first lock valid: " + held.isValid());

                    boolean rejected = false;
                    try {
                        FileLock unexpected = second.tryLock();
                        if (unexpected != null) {
                            unexpected.release();
                        }
                    } catch (OverlappingFileLockException ex) {
                        rejected = true;
                    }
                    System.out.println("same JVM overlap rejected: " + rejected);
                }

                try (FileLock after = second.tryLock()) {
                    System.out.println("lock after release: "
                            + (after != null && after.isValid()));
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac JvmFileLockDemo.java
java JvmFileLockDemo
~~~

Stdout trên hệ thống tệp mặc định hỗ trợ exclusive file lock, khi không có tiến trình khác tranh chấp tệp tạm:

~~~text
first lock valid: true
same JVM overlap rejected: true
lock after release: true
~~~

Diễn giải:

1. Hai channel cùng trỏ tới một tệp tạm, cùng tồn tại trong một JVM.
2. `first.lock()` lấy exclusive lock trên toàn vùng mặc định và `held.isValid()` là `true`.
3. `second.tryLock()` yêu cầu khóa trùng vùng, JVM phát hiện khóa chồng lấn và ném `OverlappingFileLockException`.
4. `try-with-resources` đóng `held` (tức giải phóng khóa). Sau đó `second.tryLock()` lấy được khóa mới.
5. Tệp tạm được dọn trong `finally`; channel và lock được đóng đúng thứ tự.

Ví dụ chủ động **không** tạo thread thứ hai: hai channel trong cùng JVM đủ để quan sát tính chất chồng lấn. Để hiểu bài toán thực tế có nhiều thread, cần xét thêm khóa nội bộ ở các phần sau. Nếu filesystem không hỗ trợ lock hoặc quyền của tiến trình không đủ, kết quả có thể là ngoại lệ I/O thay cho stdout trên.

## 5. Vì sao FileLock không thay thế đồng bộ giữa các thread?

Ví dụ hai thread cùng ghi thêm dữ liệu:

~~~text
Tệp đang có 100 byte

Thread A: size() trả 100
Thread B: size() trả 100
Thread A: position(100), write(10 byte)
Thread B: position(100), write(20 byte)

Hai lần ghi có thể chồng lấn và làm mất bản ghi.
~~~

Với một channel dùng chung, các thao tác `position(...)` và `write(...)` còn có thể bị xen kẽ. Với hai channel riêng, việc cả hai cùng nhìn thấy size=100 cũng không tạo ra chỗ ghi riêng. Nếu cả hai cố lấy file lock trùng vùng trong cùng JVM, một thread có thể nhận `OverlappingFileLockException` thay vì được tự động xếp hàng.

Đồng bộ đúng ở đây là bảo vệ **toàn bộ thao tác logic** bằng cùng mutex mà mọi thread liên quan phải sử dụng:

~~~java
private final java.util.concurrent.locks.ReentrantLock mutex =
        new java.util.concurrent.locks.ReentrantLock();

void performUpdate() {
    mutex.lock();
    try {
        // Đọc dữ liệu đang có, tính offset, sửa và ghi.
        // Mọi thread cùng JVM cần đi qua cùng mutex này.
    } finally {
        mutex.unlock();
    }
}
~~~

Đây là mảnh code trong một class, chưa có `main`.

`synchronized` trên một object dùng chung cũng có thể bảo vệ một vùng tương tự. `ReentrantLock` phù hợp khi cần `tryLock`, timeout, cơ chế lấy lock có thể bị ngắt, hoặc chính sách chờ tùy biến. Quan trọng nhất là **các thread phải chia sẻ cùng đối tượng khóa**. Mỗi lần gọi lại tạo một `new ReentrantLock()` thì các thread sẽ không phối hợp.

Nếu state Java như `HashMap`, cache, counter, buffer hoặc danh sách record cũng được sửa, file lock không thay thế các quy tắc thread safety của những đối tượng đó.

## 6. Khi cần phối hợp cả trong JVM lẫn giữa các tiến trình

Một mẫu thường dùng là phối hợp **hai tầng**:

1. Lấy mutex chung của các thread trong JVM.
2. Mở channel theo đúng chế độ, rồi lấy file lock theo vùng/giao thức mà các tiến trình ngoài cũng chấp nhận.
3. Khi đang nắm cả hai, thực hiện trọn vẹn chuỗi đọc–sửa–ghi.
4. Giải phóng file lock, đóng channel, sau đó nhả mutex trong `finally`.

Ví dụ class sử dụng chung một instance cho mọi thread ghi cùng file:

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.locks.ReentrantLock;

final class CoordinatedAppender {
    private final Path file;
    private final ReentrantLock inProcess = new ReentrantLock();

    CoordinatedAppender(Path file) {
        this.file = file;
    }

    void append(byte[] record) throws IOException {
        inProcess.lock();
        try {
            try (FileChannel channel = FileChannel.open(
                    file, StandardOpenOption.CREATE, StandardOpenOption.WRITE)) {
                try (FileLock ignored = channel.lock()) {
                    channel.position(channel.size());
                    ByteBuffer bytes = ByteBuffer.wrap(record);
                    while (bytes.hasRemaining()) {
                        if (channel.write(bytes) == 0) {
                            throw new IOException("No write progress");
                        }
                    }
                }
            }
        } finally {
            inProcess.unlock();
        }
    }
}
~~~

Đây là **class minh họa**, không phải chương trình có `main`. Một số giới hạn phải được hiểu rõ:

- Trong cùng JVM, **các thread phải chia sẻ cùng `CoordinatedAppender` hoặc cùng mutex cho đúng tệp**. Tạo nhiều instance với mutex khác nhau sẽ mất bảo đảm phối hợp.
- Mọi tiến trình khác muốn phối hợp phải **tự sử dụng file lock tương thích**; trên hệ thống advisory, một tiến trình không tuân thủ vẫn có thể thao tác.
- Không dùng `APPEND` trong mẫu này: vị trí ghi được chọn sau `size()` khi đang giữ khóa.
- Mẫu này không tự tạo transaction khôi phục khi ghi nửa bản ghi rồi lỗi; ứng dụng thực tế có thể cần length-prefix, checksum, commit marker và `FileChannel.force(...)` khi yêu cầu durability.
- Nếu nhiều thread đang giữ các khóa khác nhau, cần nhất quán thứ tự lấy khóa để giảm nguy cơ deadlock.

Hai tầng đáp ứng hai mục tiêu khác nhau. Mutex bảo vệ critical section và trạng thái trong một JVM; file lock giúp phối hợp với tiến trình ngoài khi provider và những chương trình liên quan hỗ trợ.

## 7. Giới hạn hệ điều hành và filesystem

### Advisory và mandatory

Trên một số hệ điều hành/filesystem, file lock là **advisory**: chỉ các tiến trình chủ động tham gia giao thức mới tôn trọng nhau. Trên nền tảng khác, một số thao tác được OS enforce theo ngữ nghĩa mandatory. **Java không hứa rằng bất kỳ tiến trình ngoài nào cũng bị chặn mọi thao tác đọc/ghi**.

Do đó, file lock không phải hệ thống phân quyền truy cập hay giải pháp bảo mật tổng quát. Nếu file chứa dữ liệu nhạy cảm, phải dùng permission và cơ chế bảo mật riêng.

### Khóa chia sẻ và độc quyền

Exclusive lock thường phục vụ cập nhật tệp. Shared lock thường phục vụ nhiều bên đọc cùng lúc, nhưng support thực tế phụ thuộc provider/hệ điều hành. Một yêu cầu shared có thể được đáp ứng bằng exclusive; `FileLock.isShared()` xác định kiểu được cấp.

### Khóa và đóng channel

`FileLock` triển khai `AutoCloseable`, có thể dùng `try (FileLock lock = channel.lock())` để tự giải phóng. Nếu channel bị đóng, lock được giải phóng và `lock.isValid()` trả `false`.

**Lưu ý quan trọng:** trên một số nền tảng, đóng bất kỳ channel nào đến cùng file trong cùng JVM có thể giải phóng mọi file lock JVM đang giữ trên file đó, kể cả lock tạo từ channel khác. Vì vậy, tránh mở rồi đóng channel bất kỳ tới cùng file trong khi còn dựa vào một lock; quản lý vòng đời của các channel tập trung.

### Filesystem mạng, provider khác nhau

NFS/SMB, filesystem ảo, các provider đặc biệt và từng OS có thể có ngữ nghĩa khóa, granularity và lỗi khác nhau. Trường hợp provider không hỗ trợ, có thể có `IOException` hoặc ngoại lệ thích hợp. Kiểm thử bằng hệ thống tệp triển khai thực tế trước khi phụ thuộc vào file lock để bảo vệ dữ liệu quan trọng.

## 8. Các lỗi và phản ứng phù hợp

| Trường hợp | Kết quả có thể gặp |
| --- | --- |
| Vùng khóa chồng lấn trong cùng JVM (đã giữ hoặc đang chờ) | `OverlappingFileLockException` |
| `tryLock` xung đột với khóa từ tiến trình khác | `null` |
| Yêu cầu exclusive lock nhưng channel không có quyền ghi | `NonWritableChannelException` |
| Yêu cầu shared lock nhưng channel không có quyền đọc | `NonReadableChannelException` |
| Channel đã đóng | `ClosedChannelException` |
| Đang chờ `lock` thì thread bị interrupt | `FileLockInterruptionException` |
| Đã release hoặc channel bị đóng | `FileLock.isValid() == false` |

Phải bắt và xử lý ngoại lệ theo mục đích. Ví dụ nếu một thread nhận `OverlappingFileLockException` do thao tác khác của chính JVM, việc lặp `tryLock` liên tục sẽ không tự giải quyết vấn đề thiết kế: cần điều phối bằng mutex nội bộ.

Một mẫu thử không chặn:

~~~java
try {
    FileLock lock = channel.tryLock();
    if (lock == null) {
        // Tiến trình khác đang nắm khóa xung đột.
    } else {
        try (lock) {
            // Đã lấy được khóa.
        }
    }
} catch (OverlappingFileLockException ex) {
    // Chính JVM này có vùng khóa chồng lấn hoặc đang chờ khóa.
}
~~~

Đoạn code minh họa trong một phương thức với `channel` đang mở và import phù hợp.

## 9. Lỗi phổ biến

**Lỗi 1:** dùng `FileLock` để thay `ReentrantLock` trong hai thread. Một yêu cầu trùng vùng có thể ném `OverlappingFileLockException` thay vì chờ.

**Lỗi 2:** cho rằng `tryLock()` luôn trả `null` khi khóa chưa sẵn sàng. Cần phân biệt xung đột từ tiến trình khác và xung đột trong JVM.

**Lỗi 3:** tạo mutex mới mỗi lần gọi; hai thread thực tế không có cùng đối tượng khóa để phối hợp.

**Lỗi 4:** cho rằng file lock tạo memory visibility cho mọi biến Java. Cần `synchronized` hoặc công cụ Java concurrency phù hợp.

**Lỗi 5:** giữ file lock mà code khác tùy tiện mở/đóng channel tới cùng file. Trên một số OS, thao tác đóng này có thể ảnh hưởng khóa đang giữ.

**Lỗi 6:** giả định file lock chặn mọi tiến trình. Advisory lock cần các bên cùng tuân thủ.

**Lỗi 7:** khóa những vùng byte không tương thích giữa các tiến trình. Nếu A khóa [0,100) còn B chỉ khóa [100,200), chưa bảo vệ chung một vùng.

**Lỗi 8:** không release trong `finally` hoặc `try-with-resources`; để ngoại lệ làm mutex không được giải phóng.

**Lỗi 9:** tin rằng file lock là giao dịch. Khóa không tự rollback ghi dở, kiểm tra checksum hay bảo đảm dữ liệu đã durable trên thiết bị.

## 10. Câu hỏi tự kiểm tra

1. Hai thread trong cùng JVM muốn khóa cùng vùng byte. Thread đến sau có luôn chờ? **Không.** Nó có thể nhận `OverlappingFileLockException`.
2. `tryLock()` trả `null` có nghĩa là gì? **Không thể lấy khóa ngay do xung đột với tiến trình khác.** Xung đột ngay trong JVM có ngoại lệ riêng.
3. File lock có tự đồng bộ một `HashMap` mà hai thread đang sửa không? **Không.** Cần quy tắc thread safety của Java.
4. Hai `FileChannel` trỏ cùng tệp trong cùng JVM có phạm vi khóa riêng không? **Không** đối với cơ chế chồng lấn JVM.
5. Một tiến trình khác không tham gia cơ chế khóa có chắc bị chặn ghi không? **Không thể bảo đảm trên mọi OS/filesystem**, đặc biệt với advisory lock.
6. Mẫu hai tầng nên lấy khóa theo thứ tự nào? **Mutex trong JVM, rồi file lock**; nhả theo thứ tự ngược và thống nhất với mọi đường code.
7. Shared lock có luôn thực sự được cấp dạng shared? **Không.** Xem `FileLock.isShared()`.
8. Vì sao nên dùng `try-with-resources` cho FileLock? **Để release khóa đúng lúc kể cả khi thao tác gây lỗi**.

**Ghi nhớ:** `FileLock` có phạm vi **JVM** đối với việc nắm giữ và phát hiện vùng khóa chồng lấn, hữu ích trong giao thức phối hợp tệp giữa các tiến trình. Nó **không** thay thế `synchronized` hay `ReentrantLock` để điều phối nhiều thread, bảo vệ trạng thái chương trình và làm cho một chuỗi đọc–sửa–ghi trở thành critical section trong Java.
