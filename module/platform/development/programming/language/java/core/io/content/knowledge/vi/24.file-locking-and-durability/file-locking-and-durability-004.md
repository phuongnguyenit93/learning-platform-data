# OverlappingFileLockException và giới hạn hỗ trợ của hệ điều hành trong Java NIO

## 1. Vì sao khóa tệp không đơn giản là gọi lock()?

Khi nhiều luồng, nhiều `FileChannel` hoặc nhiều tiến trình cùng truy cập một tệp, ứng dụng đôi khi cần phối hợp để tránh ghi đè và đọc dữ liệu ở trạng thái đang thay đổi. Java NIO cung cấp `FileChannel.lock(...)` và `FileChannel.tryLock(...)` để yêu cầu **khóa một vùng byte của tệp** (*file-region lock*).

Một lỗi đặc biệt dễ gây nhầm lẫn là `java.nio.channels.OverlappingFileLockException`. Lỗi này liên quan đến **các vùng khóa chồng lấn trong cùng Java Virtual Machine (JVM)**. Nó khác với trường hợp một **tiến trình khác** đang giữ khóa khiến thao tác xin khóa không thành công hoặc phải chờ.

Ngoài ra, khóa tệp đi qua dịch vụ khóa của hệ điều hành và file system bên dưới. Tính chất *shared/exclusive*, phạm vi ảnh hưởng của khóa, cách các tiến trình khác thực sự tuân thủ khóa, và việc sử dụng trên network file system có thể khác nhau giữa các nền tảng. Một chương trình đúng phải phân biệt:

1. **Quy tắc API của Java:** kiểu khóa, phạm vi byte, vòng đời, ngoại lệ và các điều kiện trong cùng JVM.
2. **Quy tắc phối hợp của ứng dụng:** ai khóa, khóa phần nào, dùng chung channel hay không, thứ tự lấy/nhả khóa.
3. **Khả năng hệ điều hành/file system:** khóa có được hỗ trợ đầy đủ không, có mang tính bắt buộc hay chỉ khuyến nghị, có giới hạn trên network file system không.

Mục tiêu là hiểu được khi nào xảy ra `OverlappingFileLockException`, xử lý khác biệt với `tryLock() == null` ra sao, và tại sao chỉ có `FileLock` vẫn chưa đủ để khẳng định dữ liệu đã được ghi bền hoặc một chuỗi thao tác là transaction.

## 2. Mô hình FileChannel và FileLock

Một `FileChannel` có thể yêu cầu khóa một vùng tệp với ba tham số:

~~~java
FileLock lock = channel.lock(position, size, shared);
~~~

Đây là đoạn minh họa, không phải chương trình độc lập; `channel` phải được mở với quyền phù hợp.

- `position`: byte offset bắt đầu vùng khóa, là số `long` không âm.
- `size`: độ dài vùng khóa, cũng là số `long` không âm. Phạm vi được hiểu theo nửa khoảng **[position, position + size)**, nghĩa là byte đầu có trong vùng và điểm kết thúc không thuộc vùng.
- `shared`: `false` yêu cầu khóa độc quyền (*exclusive*); `true` yêu cầu khóa chia sẻ (*shared*), nếu hệ điều hành/file system hỗ trợ.

Ví dụ:

~~~text
Khóa A: [0, 100)      -> byte 0 tới 99
Khóa B: [100, 200)    -> byte 100 tới 199
Khóa C: [50, 150)     -> byte 50 tới 149

A và B không chồng lấn vì điểm 100 là cuối A, đầu B.
A và C chồng lấn ở [50, 100).
B và C chồng lấn ở [100, 150).
~~~

Mã Java có thể yêu cầu khóa bao trùm cả vùng nằm ngoài độ dài hiện tại của tệp; vùng khóa **không tự thay đổi** khi kích thước tệp sau đó thay đổi. Một vùng khóa không phải lời hứa rằng tệp sẽ giữ nguyên kích thước hoặc không thể bị thao tác ngoài giao thức khóa. Trong nhiều bài toán cần khóa “toàn tệp”, overload `channel.lock()` tương đương yêu cầu khóa độc quyền vùng bắt đầu ở 0 với kích thước `Long.MAX_VALUE`.

`FileLock` là đối tượng đại diện cho khóa đã được cấp thành công. Có thể hỏi:

~~~java
lock.position();  // vị trí vùng khóa
lock.size();      // độ dài vùng khóa
lock.isShared();  // loại khóa thực tế
lock.isValid();   // khóa còn hợp lệ hay không
lock.release();   // giải phóng khóa
~~~

Từ `FileLock` cũng có thể lấy channel gắn với khóa. Cần nhớ rằng **khóa tệp thuộc JVM đang chạy**, dù API cho phép xin khóa qua nhiều đối tượng `FileChannel` khác nhau. Vì vậy hai channel mở cùng tệp ở một JVM không tạo ra hai không gian khóa độc lập.

## 3. Khi nào ném OverlappingFileLockException?

`OverlappingFileLockException` là ngoại lệ **không kiểm tra lúc biên dịch** (subclass của `IllegalStateException`). Các phương thức `lock(...)` và `tryLock(...)` có thể ném ngoại lệ này khi vùng được xin khóa **chồng lấn với vùng đang được khóa bởi JVM hiện tại**, hoặc có một thread trong JVM đã chờ khóa một vùng chồng lấn.

Các trường hợp phổ biến:

- Thread A trong cùng JVM đã có khóa `[0, 100)` trên một tệp; thread B gọi `lock(50, 25, false)` cho cùng tệp.
- Một `FileChannel` thứ hai mở cùng tệp, dù tạo từ lệnh `FileChannel.open(...)` riêng, lại xin khóa chồng lên khóa còn hiệu lực của channel thứ nhất.
- Một thread đang chờ yêu cầu khóa vùng A; thread khác trong cùng JVM xin vùng chồng lấn trước khi yêu cầu chờ đó kết thúc.

Điều quan trọng: **quy tắc kiểm tra chồng lấn trong cùng JVM áp dụng cả khi cả hai yêu cầu đều là shared lock**. Không được suy luận rằng hai thread cùng JVM có thể mỗi thread giữ một `FileLock` chia sẻ riêng trên vùng byte trùng nhau. Khóa chia sẻ có ý nghĩa khi phối hợp với **tiến trình khác** theo khả năng của hệ điều hành; nếu JVM đã giữ lock chồng lấn, một yêu cầu `FileLock` mới từ JVM đó vẫn có thể bị ném ngoại lệ.

Bảng nhận biết:

| Tình huống | Kết quả thường gặp tại API Java | Ý nghĩa |
| --- | --- | --- |
| Trong JVM đã giữ khóa chồng lấn, gọi `tryLock(...)` | `OverlappingFileLockException` | Xung đột quản lý lock **nội bộ JVM**, không phải `null` |
| Trong JVM đã giữ hoặc đang đợi khóa chồng lấn, gọi `lock(...)` | `OverlappingFileLockException` | Không nên giả định call sẽ “xếp hàng chờ” chính JVM mình |
| Tiến trình **khác** đang giữ khóa xung đột, gọi `tryLock(...)` | Thường trả `null` | Không lấy được khóa ngay, có thể thử lại theo lịch do ứng dụng quyết định |
| Tiến trình **khác** đang giữ khóa xung đột, gọi `lock(...)` | Có thể chờ đến khi được cấp hoặc bị lỗi/gián đoạn | Lời gọi blocking không đồng nghĩa sẽ thành công vô điều kiện |
| Vùng không chồng lấn, được hệ điều hành hỗ trợ | Có thể nhận `FileLock` | Vẫn phải xử lý lỗi I/O, quyền truy cập và giới hạn hệ thống |

Đừng dùng `tryLock() == null` làm điều kiện duy nhất để nhận biết mọi kiểu xung đột. `OverlappingFileLockException` được **ném** chứ không chuyển thành `null`. Và đừng gọi mã có khả năng ném ngoại lệ nội bộ JVM là dấu hiệu chắc chắn “tiến trình khác đang chiếm tệp”.

## 4. Ví dụ Java 17+ hoàn chỉnh: khóa chồng lấn, nhả và khóa lại

Ví dụ tạo một tệp tạm riêng, mở hai channel trên cùng tệp trong cùng JVM, dùng channel thứ nhất giữ `[0, 16)` rồi yêu cầu channel thứ hai khóa `[8, 16)`. Hai vùng chồng lấn nên `tryLock` sẽ ném `OverlappingFileLockException`. Khi khóa đầu đã được giải phóng, việc xin khóa lại có thể thành công.

Tạo tệp `LockOverlapDemo.java`:

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class LockOverlapDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lock-overlap-", ".bin");
        try {
            try (FileChannel first = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE);
                 FileChannel second = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {

                try (FileLock held = first.lock(0, 16, false)) {
                    System.out.println("First lock valid: " + held.isValid());
                    try {
                        FileLock unexpected = second.tryLock(8, 8, false);
                        if (unexpected != null) unexpected.close();
                        System.out.println("Unexpected: no overlap exception");
                    } catch (OverlappingFileLockException expected) {
                        System.out.println("Overlap detected in the same JVM");
                    }
                }

                try (FileLock afterRelease = second.tryLock(8, 8, false)) {
                    if (afterRelease == null) {
                        System.out.println("Other process holds the range");
                    } else {
                        System.out.println("Reacquired after release: " + afterRelease.isValid());
                    }
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy với **Java 17 trở lên**:

~~~bash
javac LockOverlapDemo.java
java LockOverlapDemo
~~~

Kết quả đã chạy trên môi trường kiểm thử với hệ thống tệp cục bộ:

~~~text
First lock valid: true
Overlap detected in the same JVM
Reacquired after release: true
~~~

Kết quả dòng cuối giả định **không có tiến trình khác giữ khóa [8,16)** và nền tảng hỗ trợ các khóa cần thiết. Nếu có một tiến trình ngoài JVM lấy khóa trong khoảng giữa hai thao tác, lời gọi `tryLock` thứ hai có thể trả `null` (hoặc gặp lỗi tùy tình huống).

Các bước đáng chú ý:

1. `Files.createTempFile(...)` tạo tệp mới, tránh làm thay đổi một tệp nghiệp vụ đang được sử dụng.
2. Hai `FileChannel` đều mở cùng tệp và có quyền đọc/ghi. Khóa được yêu cầu là exclusive vì đối số `shared=false`.
3. `first.lock(0, 16, false)` lấy vùng [0,16). `second.tryLock(8, 8, false)` xin vùng [8,16), nên bị xem là chồng lấn mặc dù hai channel khác object.
4. `try-with-resources` trên `FileLock held` tự gọi `close()`/`release()` khi ra khỏi khối. Điều này giải phóng khóa.
5. Lần thứ hai `second.tryLock(8, 8, false)` có thể lấy được khóa vì không còn xung đột nội bộ JVM.
6. Hai channel được đóng trước khi xóa tệp tạm; `finally` vẫn thử xóa nếu quá trình khóa gặp exception.

Ví dụ này cố ý có thứ tự tuần tự rõ ràng nên không cần chạy hai thread mới chứng minh được quy tắc **cùng JVM**. Nếu muốn mô phỏng nhiều JVM thực sự cạnh tranh, cần chạy **hai process Java riêng**, chứ không chỉ tạo hai thread. Tránh viết bài kiểm thử phụ thuộc vào thời điểm ngẫu nhiên vì sẽ cho kết quả không ổn định.

## 5. lock() và tryLock(): blocking, null và exception

Có hai nhóm phương thức quan trọng:

~~~java
FileLock blocking = channel.lock();                   // exclusive, cả vùng lớn
FileLock region = channel.lock(0, 1024, false);       // blocking cho vùng [0,1024)
FileLock quick = channel.tryLock(0, 1024, false);      // non-blocking
~~~

Đây là **các lời gọi minh họa**, không nên chạy đồng thời cả ba trên cùng channel vì chúng đang yêu cầu các vùng chồng lấn; mã thực tế chỉ chọn cách phù hợp.

- `lock()` và `lock(position, size, shared)` có thể **chặn thread** khi một tiến trình khác giữ khóa xung đột, cho đến lúc nhận được khóa hoặc thao tác bị hủy/lỗi.
- `tryLock(...)` yêu cầu khóa **không chờ**. Khi không nhận được ngay vì một tiến trình khác, API có thể trả `null`. Khi khóa chồng lấn đang được giữ hoặc chờ trong cùng JVM, nó ném `OverlappingFileLockException`.
- `tryLock()` không có đối số yêu cầu exclusive lock trên vùng bắt đầu ở byte 0 và kéo dài tới `Long.MAX_VALUE`.
- Các lời gọi vẫn có thể ném `IOException` vì lỗi file system, không tương thích khóa, quyền truy cập, tài nguyên hoặc kết nối với network FS. Việc `tryLock` “không chặn” chỉ mô tả cách chờ cấp khóa; không nên suy ra mọi I/O liên quan đều luôn không có độ trễ.

Khi `lock(...)` đang chờ, `Thread.interrupt()` có thể khiến nó kết thúc bằng `FileLockInterruptionException`; đóng channel từ thread khác khi nó đang chờ có thể gây `AsynchronousCloseException`. Đây là các trường hợp khác với `OverlappingFileLockException` và cần xử lý theo chính sách hủy tác vụ, retry hoặc đóng tài nguyên của ứng dụng.

Một nhánh xử lý `tryLock` minh họa:

~~~java
try (FileLock acquired = channel.tryLock(0, 1024, false)) {
    if (acquired == null) {
        // Tiến trình khác có thể đang giữ vùng khóa: thử lại có giới hạn hoặc báo bận.
        return;
    }
    // Chỉ thực hiện thao tác cần khóa trong khối này.
} catch (OverlappingFileLockException e) {
    // Xung đột khóa nội bộ JVM: sửa giao thức sở hữu thay vì retry vô hạn.
}
~~~

Đây là **mã minh họa đặt trong method trả về void**, nơi `channel` đã được tạo/mở với quyền thích hợp. `try-with-resources` chấp nhận tham chiếu null, nên nếu `tryLock` trả null, nhánh kiểm tra giúp tránh dereference null; mã trên vẫn nên được tổ chức để không để nhánh return qua nhiều lớp làm khó việc giám sát. Trong ứng dụng production, bắt và xử lý riêng các lỗi I/O có ý nghĩa nghiệp vụ.

Nếu nhiều thread trong cùng JVM cùng xử lý một file, tốt hơn nên dùng một nơi quản lý lock theo file/region để điều phối nội bộ trước khi xin OS lock. Bắt ngoại lệ rồi ngủ và retry liên tục không giải quyết được vấn đề khi một component quên nhả khóa.

## 6. Vùng khóa, shared và exclusive: đừng suy diễn quá mức

**Exclusive lock** yêu cầu độc quyền vùng byte với các khóa xung đột do những tiến trình có phối hợp áp đặt. **Shared lock** dành cho các reader có thể cùng giữ khóa đọc, với điều kiện hệ điều hành/file system thực sự hỗ trợ shared file locks.

Trên một số nền tảng, một yêu cầu shared lock có thể được **nâng thành exclusive**. Khi đó hãy kiểm tra `FileLock.isShared()` trên kết quả để biết trạng thái khóa thực tế; không giả định đối số `shared=true` được thực thi nguyên trạng.

Quyền mở channel cũng quan trọng:

- Để yêu cầu **shared lock**, channel phải được mở cho đọc; nếu không có quyền tương ứng, có thể gặp `NonReadableChannelException`.
- Để yêu cầu **exclusive lock**, channel phải được mở cho ghi; nếu không, có thể gặp `NonWritableChannelException`.
- Tùy nền tảng, file system có thể yêu cầu khả năng ghi ngay cả khi xin shared lock, hoặc không hỗ trợ khóa theo vùng như mong muốn. Có thể phải mở thêm quyền đọc/ghi cho một số kiểu khóa theo hợp đồng API/nền tảng.

Khóa vùng [0,100) **không tự động mở rộng** sang vùng [100,200) nếu file lớn lên; hai vùng kề nhau không overlap. Để bảo vệ cả append mới, cần chọn vùng khóa bao trùm dữ liệu có thể được thêm hoặc xây giao thức khóa thống nhất cho append. Khóa tối thiểu một byte theo key/record chỉ an toàn khi mọi tiến trình tham gia đều biết và tuân thủ cùng quy ước byte-offset.

Tài liệu `FileLock` khuyến nghị chỉ dùng file locking khi thực sự cần phối hợp với chương trình khác vì khác biệt giữa các hệ điều hành; còn **nhiều thread trong một JVM** nên phối hợp bằng `synchronized`, `Lock` hoặc cấu trúc đồng bộ chuyên dụng, kết hợp với khóa file khi còn có nhiều process.

## 7. Giới hạn phụ thuộc hệ điều hành và file system

### 7.1. Advisory và mandatory locking

Ở một số hệ điều hành, file locks mang tính **advisory**: chỉ các tiến trình chủ động yêu cầu/kiểm tra khóa mới phối hợp; một tiến trình khác có thể bỏ qua cơ chế khóa và tiếp tục đọc/ghi. Ở nền tảng khác, một số kiểu khóa có thể được **cưỡng chế** (*mandatory*) ở tầng hệ điều hành.

Vì vậy, `lock()` trả về `FileLock` **không chứng minh** rằng mọi chương trình trên máy sẽ bị chặn khi truy cập vùng đó. Đặc biệt nếu có mã native, ứng dụng khác, thư viện bên thứ ba hoặc môi trường network file system, cần xác minh chính sách thực tế thay vì coi khóa là cơ chế phân quyền/bảo mật.

Khóa file **không phải ACL** hay cơ chế xác thực. Chương trình có quyền mở/ghi dữ liệu có thể không tôn trọng giao thức khóa ở một số nền tảng.

### 7.2. Khóa là tài nguyên của JVM nhưng có hiệu ứng liên tiến trình

Theo hợp đồng Java, khóa giữ thay mặt cho **toàn JVM**, không phải riêng thread hoặc object `FileChannel`. Nếu code tạo hai channel đến cùng file và xin vùng chồng lấn, điều kiện xung đột JVM vẫn áp dụng.

Ở một số hệ điều hành, khóa có thể gắn với *process* theo cách mà việc đóng một descriptor/channel **khác** đến cùng file cũng ảnh hưởng đến khóa. Vì thế, khi dùng file locks trong Java, tránh thiết kế dựa vào việc mở/đóng nhiều channel trên cùng file hoàn toàn độc lập, nhất là trong mã phức tạp hoặc khi ứng dụng có thư viện khác cùng mở file.

Hợp đồng `FileLock` còn lưu ý không nên dùng nhiều kênh đến cùng tệp trong JVM khi cần bảo đảm portable; dùng một channel duy nhất cho các khóa nếu có thể, và tránh đóng channel trong lúc có vùng khóa cần giữ.

### 7.3. Khóa theo vùng có thể chỉ được hỗ trợ một phần

Một số nền tảng/file system không hỗ trợ vùng khóa bất kỳ hoặc giới hạn chúng theo những ranh giới nhất định; một số trường hợp yêu cầu shared bị chuyển thành exclusive. Network file systems có thể có thêm giới hạn, độ trễ, trạng thái mất kết nối, lease hết hạn hoặc chính sách máy chủ khác với file system cục bộ.

Tài liệu API không bảo đảm mọi đặc điểm khóa đều giống nhau trên NTFS, ext4, NFS, SMB hoặc nhà cung cấp file system ảo. Nếu chương trình phải chạy đa nền tảng, hãy thử đúng tình huống có **hai JVM riêng**, các kiểu open/lock thực tế và network share thực tế của sản phẩm.

### 7.4. File mapping và thao tác trên file còn khóa

Một số hệ điều hành không cho phép ánh xạ một vùng đang khóa hoặc khóa một vùng đã được memory-map theo một số chế độ nhất định. Tương tác giữa file locking, `MappedByteBuffer`, truncate, rename hay delete không thể mặc định giống nhau trên mọi nền tảng.

Nếu nhiệm vụ sử dụng `FileChannel.map(...)`, hãy xem xét vòng đời mapping và file lock riêng. Đừng coi việc đóng channel đồng nghĩa với việc mọi mapping của file chắc chắn đã được hủy tức thời.

### 7.5. Thử nghiệm thực tế thay vì phụ thuộc kết quả một máy

Các ví dụ học thuật trên file system cục bộ chứng minh các quy tắc API có thể quan sát trong môi trường đang thử. Chúng **không xác nhận** rằng OS/network FS mục tiêu sản phẩm sẽ cung cấp mandatory locking, shared lock thật, hay bảo vệ file khi process/crash/mạng đứt. Những yêu cầu này phải được kiểm chứng trên nền tảng đích.

## 8. Vòng đời FileLock và vấn đề giải phóng

Sau khi cấp khóa thành công, vùng khóa vẫn tồn tại cho tới khi gọi `release()`, đóng channel liên quan hoặc JVM kết thúc (theo cơ chế hệ điều hành). `FileLock` triển khai `AutoCloseable`; cách tự nhiên nhất để quản lý là `try-with-resources`.

~~~java
try (FileChannel channel = FileChannel.open(path,
        StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock(0, 4096, false)) {
    // Thao tác đọc/ghi vùng có khóa khi lock còn hiệu lực.
}
~~~

Đây là **mã minh họa**, giả sử `path` hợp lệ và file đã tồn tại; cần import `FileChannel`, `FileLock` và `StandardOpenOption`. Tài nguyên được đóng theo thứ tự ngược: nhả lock trước, rồi đóng channel.

- `lock.isValid()` trả false sau khi khóa được giải phóng hoặc không còn hiệu lực, chẳng hạn khi channel đóng.
- Đóng channel gắn với khóa làm các khóa được giữ qua channel đó không còn hiệu lực; thao tác đóng có thể có các tác động ngoài mong muốn khác tùy OS như đã nêu.
- Nếu một hàm chỉ **mượn** `FileChannel` hay `FileLock` do nơi khác quản lý, không tự đóng chúng nếu giao thức sở hữu chưa trao quyền.
- Thứ tự đóng quan trọng: hoàn tất dữ liệu cần bảo vệ trước khi nhả lock; kiểm tra và xử lý lỗi ghi/flush trước khi cho bên khác vào critical section.

Đừng giữ file lock qua lời gọi mạng dài hoặc tác vụ có thể treo nếu không cần: sẽ kéo dài thời gian tiến trình khác bị chặn. Với blocking `lock()`, cần có chiến lược hủy/giới hạn thời gian phù hợp, hoặc dùng `tryLock()` kết hợp retry có giới hạn và backoff tùy chính sách hệ thống.

## 9. File lock không đồng nghĩa dữ liệu đã bền hoặc thao tác đã nguyên tử

Một khóa file giúp phối hợp truy cập **giữa các bên tuân thủ giao thức**, nhưng không cung cấp:

- **Giao dịch nhiều bước:** viết record A, sửa index B rồi crash không được tự rollback chỉ nhờ file lock.
- **Tính nguyên tử của ghi dữ liệu:** một thao tác lớn có thể được hệ điều hành chia thành nhiều lần cập nhật, không phải transaction.
- **Durability:** nhả lock hoặc đóng đối tượng khóa không tự khẳng định dữ liệu đã được ghi bền xuống phương tiện lưu trữ theo yêu cầu nghiệp vụ.
- **Chống xóa/đổi tên bởi mọi chương trình:** hành vi phụ thuộc OS, quyền và kiểu khóa.

Khi cần yêu cầu lưu dữ liệu rõ ràng, có thể dùng `FileChannel.force(true)` để yêu cầu đồng bộ thay đổi nội dung và metadata ra thiết bị lưu trữ theo hợp đồng API và giới hạn thiết bị/file system. `force(true)` và `force(false)` khác nhau về yêu cầu đồng bộ metadata; cả hai **không biến nhiều lần ghi thành giao dịch nguyên tử**. Một cách tổ chức có thể là:

~~~java
try (FileLock lock = channel.lock(0, Long.MAX_VALUE, false)) {
    // Ghi dữ liệu/metadata theo giao thức ứng dụng đã xác định.
    channel.force(true);
} // Chỉ sau đó mới nhả khóa.
~~~

Đây là đoạn **minh họa**, giả sử `channel` là channel ghi, còn `try` này sở hữu riêng `FileLock`. Nếu cần recovery sau crash, phải bổ sung kiểm tra tính toàn vẹn, write-ahead log, copy-on-write hoặc hệ quản trị cơ sở dữ liệu có transaction phù hợp.

Trong ứng dụng nhiều process, mọi process phải nhất quán về **vùng khóa, thứ tự ghi dữ liệu, việc flush và lúc nhả khóa**; nếu một process ghi mà không xin lock, thuộc tính an toàn của giao thức tổng thể không còn được bảo đảm.

## 10. Phân biệt các ngoại lệ và hướng xử lý

| Hiện tượng/ngoại lệ | Diễn giải | Hướng xử lý |
| --- | --- | --- |
| `OverlappingFileLockException` | Khóa cùng JVM đã giữ hoặc đang chờ trên vùng chồng lấn | Sửa quản lý khóa nội bộ JVM, không retry vô hạn |
| `tryLock(...) == null` | Không cấp khóa ngay, thường do tiến trình khác có khóa xung đột | Báo bận, backoff/retry có giới hạn theo yêu cầu |
| `NonReadableChannelException` | Yêu cầu shared nhưng channel thiếu quyền đọc | Mở channel với quyền phù hợp |
| `NonWritableChannelException` | Yêu cầu exclusive nhưng channel thiếu quyền ghi | Mở channel với quyền phù hợp |
| `ClosedChannelException` | Channel đóng trước khi xin khóa | Sửa vòng đời resource |
| `FileLockInterruptionException` | Thread bị interrupt trong khi đang chờ khóa blocking | Tuân thủ chính sách hủy, không nuốt tín hiệu |
| `AsynchronousCloseException` | Channel bị đóng từ thread khác khi blocking operation diễn ra | Điều phối đóng và tác vụ |
| `IOException` | Lỗi OS/file system, unsupported operation hoặc lỗi I/O khác | Báo chi tiết, xử lý/retry có điều kiện |
| `IllegalArgumentException` | `position`/`size` âm hoặc vùng yêu cầu tràn `long` | Kiểm tra phép tính offset và size trước khi gọi |

Không bắt `Exception` rộng rồi tự cho rằng mọi lỗi đều là “file đang bị process khác lock”. Điều đó che mất lỗi cấu hình, quyền truy cập, lifecycle và những vấn đề lập trình nghiêm trọng.

Nếu hai vùng byte rời nhau nhưng vẫn liên quan cùng một invariant nghiệp vụ (ví dụ record dữ liệu và bảng chỉ mục), đặt khóa rời nhau có thể chưa đủ để bảo vệ thao tác cập nhật toàn vẹn. Hãy chọn phạm vi khóa bao trùm toàn bộ critical section cần tính nhất quán.

## 11. Mẫu thiết kế phối hợp an toàn hơn

Một thiết kế thực tế có nhiều thread và nhiều tiến trình có thể gồm hai lớp:

1. **Trong cùng JVM:** dùng `ReentrantLock`, `synchronized` hoặc lock manager theo file/region để chỉ một luồng được thực hiện thao tác xung đột tại một thời điểm. Các thread chờ ở lớp này trước khi gọi `FileChannel.lock`. Cách làm này tránh nhiều thread cùng JVM tự ném `OverlappingFileLockException` khi đồng thời xin khóa giống nhau.
2. **Giữa các JVM/process:** giữ `FileLock` trên vùng đã thống nhất, nếu môi trường hỗ trợ; ghi/đọc dữ liệu, đồng bộ khi cần, rồi nhả khóa. Có chiến lược khi không lấy được khóa trong thời gian cho phép.

Với ứng dụng hoạt động trên nhiều máy hoặc network FS mà cơ chế file lock không bảo đảm chính sách mong muốn, cân nhắc hệ quản trị dữ liệu/giao thức phối hợp chuyên dụng. Không nên tự xem file lock cục bộ là distributed lock mạnh.

### Checklist khi thiết kế

- Đã định nghĩa tệp và vùng byte khóa chính xác chưa?
- Có thread nào khác trong JVM đang giữ/đợi vùng chồng lấn không?
- Các channel và quyền mở có phù hợp shared/exclusive không?
- Ai có quyền đóng `FileLock` và `FileChannel`?
- Tất cả tiến trình liên quan có thực sự tuân thủ giao thức khóa không?
- Mục tiêu file system có hỗ trợ loại khóa/vùng khóa này không?
- Có đóng channel khác đến cùng tệp trong lúc cần giữ lock không?
- Việc ghi/đọc có giữ lock đủ lâu để bảo vệ invariant không?
- Đã kiểm soát crash, partial writes và durability ngoài lock chưa?
- Có kiểm thử riêng trên hệ điều hành và file system triển khai thật không?

## 12. Câu hỏi tự kiểm tra

1. Hai `FileChannel` mở cùng tệp trong một JVM, channel A đã khóa [0,20), channel B gọi `tryLock(10,5,false)`. Điều gì xảy ra? **`OverlappingFileLockException`**, vì [10,15) chồng lấn vùng đang được JVM giữ.
2. Nếu thay bằng `tryLock(20,5,false)` thì có chồng lấn không? **Không**, hai vùng [0,20) và [20,25) chỉ tiếp xúc ở biên, nhưng việc lấy khóa vẫn có thể gặp các giới hạn của file system/tiến trình khác.
3. Shared lock của cùng JVM có được xin thêm trên vùng đã có shared lock không? **Không thể mặc định**, vì API vẫn xét chồng lấn nội bộ JVM; có thể ném `OverlappingFileLockException`.
4. `tryLock()` trả `null` chứng minh gì? Chỉ rằng thao tác không được cấp khóa ngay; thường do xung đột với khóa từ process khác. **Không** phải dấu hiệu bắt buộc cho mọi kiểu xung đột.
5. `lock()` có luôn phải chờ khi JVM hiện tại đã có khóa vùng tương ứng? **Không**, có thể ném `OverlappingFileLockException` ngay.
6. `lock(..., true)` có chắc chắn tạo shared lock trên mọi nền tảng không? **Không**; một số hệ thống có thể nâng thành exclusive. Kiểm tra `isShared()`.
7. File lock có làm mọi chương trình khác không được đọc/ghi vùng dữ liệu không? **Không bảo đảm trên mọi hệ điều hành/file system**, nhất là môi trường advisory locking.
8. `channel.force(true)` có đồng nghĩa một chuỗi ghi dưới lock trở thành transaction nguyên tử không? **Không**; nó phục vụ yêu cầu đồng bộ dữ liệu/metadata, không tự tạo atomic transaction.
9. Khi hai luồng cùng JVM cần truy cập cùng một file, có nên xem file lock là primitive đồng bộ nội bộ chính không? **Không nên**; dùng đồng bộ trong JVM và quản lý file lock ở biên liên tiến trình.

## Tài liệu API tham khảo

- [Java SE 17 — FileLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): phạm vi vùng khóa, vòng đời, shared/exclusive, giới hạn hệ điều hành.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): các overload `lock`/`tryLock`, exceptions, `force`.
- [Java SE 17 — OverlappingFileLockException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/OverlappingFileLockException.html): ý nghĩa ngoại lệ cùng JVM.
- [Java SE 17 — StandardOpenOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html): các quyền mở file ảnh hưởng đến loại khóa.
