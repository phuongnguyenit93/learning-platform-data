# Khóa độc quyền, khóa chia sẻ và vùng byte với FileChannel (Java NIO.2)

Khi hai tiến trình cùng đọc/ghi một tệp, việc thao tác tại đúng offset **không tự bảo vệ nội dung trước cập nhật đồng thời**. Java NIO cung cấp `FileChannel.lock(...)`, `tryLock(...)` và `FileLock` để yêu cầu khóa một **vùng byte** của tệp, có thể ở chế độ **độc quyền (exclusive)** hoặc **chia sẻ (shared)**. Những khóa này chủ yếu dùng để **phối hợp giữa các tiến trình** thông qua cơ chế khóa tệp của hệ điều hành.

Điểm quan trọng nhất: **FileLock không phải khóa dùng để điều phối các thread trong cùng JVM; không phải transaction; không phải lời cam kết dữ liệu đã được ghi bền vững.** Muốn hệ thống đúng đắn, cần hiểu phạm vi vùng byte, cách hệ điều hành thực thi khóa, thời điểm giữ/thả khóa và mối quan hệ giữa khóa, nội dung file, `force` và giao thức ứng dụng.

Sau bài này, bạn có thể xác định lúc nào cần shared/exclusive lock, cách chia vùng byte, đọc hiểu các kết quả và exception của `lock/tryLock`, viết code Java 17+ có vòng đời khóa rõ ràng, và nhận diện những giới hạn của việc dùng file locking để bảo vệ dữ liệu.

## 1. Khóa tệp bảo vệ điều gì?

Giả sử hai ứng dụng cùng cập nhật file `counter.dat` có một số nguyên. Mỗi ứng dụng đều thực hiện “đọc số hiện tại → cộng một → ghi lại”. Nếu chúng đọc cùng giá trị `41`, cả hai có thể ghi `42` thay vì kết quả mong muốn `43`. Đó là **lost update**. Việc gọi `FileChannel.write` thành công không giải quyết tranh chấp nghiệp vụ này.

Một giao thức khóa phù hợp có thể yêu cầu:

1. Mỗi tiến trình xin **exclusive lock** trên vùng chứa counter.
2. Chỉ sau khi giữ được lock mới đọc giá trị hiện tại.
3. Tính toán và ghi giá trị mới trong lúc vẫn giữ lock.
4. Nếu yêu cầu độ bền, gọi `channel.force(...)` đúng điểm cam kết.
5. Giải phóng lock; tiến trình khác mới được vào vùng cập nhật theo cùng giao thức.

Với tác vụ chỉ đọc, nhiều tiến trình có thể cùng giữ **shared lock** trên cùng vùng nếu nền tảng hỗ trợ, với điều kiện writer xin exclusive lock và tất cả đều tôn trọng giao thức.

Tuy nhiên, mức độ hệ điều hành **thực sự ngăn truy cập** khác nhau: trên nền tảng có **advisory lock**, tiến trình không tham gia giao thức vẫn có thể mở hoặc thay đổi file; trên hệ thống có **mandatory lock**, một số thao tác trái khóa có thể bị ngăn. Java khuyến nghị **luôn thiết kế như khóa là advisory**, dù chạy trên OS nào.

## 2. Shared lock và exclusive lock

| Tính chất | Exclusive lock | Shared lock |
| --- | --- | --- |
| Mục đích phổ biến | Phối hợp writer hoặc thao tác đọc–sửa–ghi | Phối hợp các reader đồng thời |
| Đối tượng xung đột | Một exclusive lock ngăn các khóa shared/exclusive chồng vùng được cấp cho tiến trình khác theo cơ chế OS | Nhiều shared lock chồng vùng có thể cùng tồn tại; yêu cầu exclusive chồng vùng sẽ xung đột |
| Ký hiệu tham số | `shared=false` | `shared=true` |
| Điều kiện mở channel | Channel phải cho phép **WRITE** | Channel phải cho phép **READ** |
| Tính di động | Phụ thuộc OS/filesystem hỗ trợ khóa | Có nền tảng không hỗ trợ shared; Java có thể **chuyển yêu cầu sang exclusive** |
| Cách biết loại khóa thực nhận | `lock.isShared() == false` | Kiểm tra `lock.isShared()`, không giả định luôn `true` |

Ví dụ tưởng tượng ba tiến trình truy cập cùng vùng `[0, 100)`:

- P1 đang giữ shared. P2 xin shared trên cùng vùng: **có thể** cùng được cấp nếu OS/provider cho phép shared.
- P1 đang giữ shared. P3 xin exclusive vùng chồng lấn: phải chờ, thất bại ngay với `tryLock` hoặc gặp lỗi tùy điều kiện.
- P1 đang giữ exclusive. P2/P3 xin khóa chồng lấn, dù shared hay exclusive: không được đồng thời giữ cùng kiểu xung đột.

Đây là mô hình giao thức giữa các tiến trình. **Không** dùng bảng trên để kết luận một JVM được phép tạo hai `FileLock` chồng vùng: Javadoc cấm các lock giữ trong **cùng JVM** chồng lấn nhau, kể cả hai yêu cầu đều shared. Khi có lock chồng lấn đã giữ hoặc request chồng vùng đang đợi trong cùng JVM, API ném `OverlappingFileLockException`.

Nếu dùng shared lock cho reader, nhớ rằng **không phải mọi reader đều tự động xin khóa**: `Files.readAllBytes(path)` hoặc `FileChannel.read(...)` không “đi xin shared lock” hộ bạn. Phối hợp chỉ đáng tin khi tất cả bên liên quan dùng và tuân thủ cùng một quy tắc.

## 3. Vùng khóa là khoảng byte, không phải toàn file mặc định

Chữ ký chính:

```java
FileLock lock(long position, long size, boolean shared) throws IOException;
FileLock tryLock(long position, long size, boolean shared) throws IOException;
```

- `position` là **byte offset bắt đầu**, từ `0`; phải không âm.
- `size` là số byte trong vùng; phải không âm và `position + size` không được tràn sang giá trị âm.
- Với `size > 0`, lock bảo vệ vùng nửa mở **`[position, position + size)`**. Byte ở điểm cuối **không thuộc** vùng.
- `size == 0` có ý nghĩa đặc biệt: yêu cầu khóa từ `position` đến hết không gian file theo hợp đồng API, kể cả khi tệp mở rộng hoặc thu ngắn sau đó. Khóa được trả về có kích thước `Long.MAX_VALUE - position`.
- Một vùng khóa **không bắt buộc nằm trong kích thước hiện tại của file**. Ví dụ file có 8 byte vẫn có thể xin khóa vùng `[100, 200)` trên filesystem hỗ trợ.
- Vùng có kích thước dương là **cố định** sau khi cấp. Nếu khóa `[0, 100)`, sau đó tệp được mở rộng từ 20 byte lên 500 byte, phần `[100, 500)` nằm ngoài vùng khóa đã lấy.

Ví dụ các vùng:

| Khóa đã giữ | Vùng muốn xin tiếp | Chồng lấn? | Giải thích |
| --- | --- | --- | --- |
| `[0, 10)` | `[5, 15)` | Có | Chung các byte `5..9` |
| `[0, 10)` | `[10, 20)` | Không | Hai vùng tiếp giáp; điểm cuối `10` nằm ngoài vùng đầu |
| `[100, 200)` | `[0, 100)` | Không | Điểm kết thúc vùng thứ hai đúng điểm đầu vùng thứ nhất |
| `[100, 200)` | `[199, 201)` | Có | Chung byte `199` |
| `[50, 60)` | `[55, 56)` | Có | Vùng nhỏ nằm trong vùng lớn |

`FileLock.overlaps(position, size)` kiểm tra hình học chồng lấn giữa vùng của một **đối tượng FileLock** và vùng được truyền vào. Nó **không cấp thêm lock**, không kiểm tra các process khác và cũng không nói rằng lock vẫn hợp lệ: muốn kiểm tra trạng thái của chính lock, dùng `isValid()`.

### Phân biệt byte offset và record

Nếu mỗi record có kích thước cố định 16 byte, record thứ `i` (đếm từ `0`) nằm ở `[i * 16, (i + 1) * 16)`. Khóa một record dùng:

```java
// Đoạn minh họa: channel phải mở đúng quyền.
long offset = Math.multiplyExact(recordIndex, 16L);
try (FileLock lock = channel.lock(offset, 16, false)) {
    // Đọc/sửa/ghi record tại offset trong khi lock còn hiệu lực.
}
```

`recordIndex` phải không âm và phép nhân không được tràn số. Kích thước record theo **byte**, không tính bằng số ký tự Unicode. Với record biến độ dài, phải có bảng offset/length hoặc framing rõ ràng; khóa 16 byte khi record thực chiếm 50 byte sẽ không bảo vệ toàn bộ record.

Với file có thể mở rộng không dự đoán trước, cần chọn chiến lược khóa bao phủ vùng sắp thêm hoặc dùng một khóa điều phối metadata/offset riêng. **Không nên tin rằng khóa cũ tự mở rộng khi file lớn lên**, trừ trường hợp xin vùng tới EOF bằng `size=0` theo hợp đồng.

## 4. `FileChannel.lock` và `tryLock` khác nhau thế nào?

| API | Cách xin khóa | Khi có tiến trình khác giữ khóa chồng lấn | Khi có khóa chồng lấn trong cùng JVM |
| --- | --- | --- | --- |
| `channel.lock()` | Chờ để xin **exclusive lock** cho cả miền file (`0` đến `Long.MAX_VALUE`) | Có thể **chờ** tới khi cấp được, channel đóng hoặc thread bị interrupt | `OverlappingFileLockException` |
| `channel.lock(p, n, shared)` | Chờ xin khóa đúng vùng/loại yêu cầu | Có thể chờ | `OverlappingFileLockException` |
| `channel.tryLock()` | Thử ngay exclusive lock toàn file | Trả **`null`** khi xung đột với khóa của tiến trình khác | `OverlappingFileLockException` |
| `channel.tryLock(p, n, shared)` | Thử ngay khóa vùng/loại được yêu cầu | Trả **`null`** khi xung đột với khóa của tiến trình khác | `OverlappingFileLockException` |

`tryLock` thường hữu ích khi ứng dụng muốn báo “tệp đang được sử dụng” hoặc lên lịch thử sau, tránh đợi vô hạn. Nó **không phải** lời hứa sẽ luôn trả trong thời gian xác định nếu chính hệ thống tệp/OS gặp trục trặc, và vẫn có thể ném exception cho những lỗi không phải xung đột bình thường.

`lock` có thể chờ khi process khác giữ khóa xung đột. Nếu luồng đang chờ bị interrupt, `FileLockInterruptionException` có thể được ném; nếu channel bị đóng bởi thread khác, có thể gặp `AsynchronousCloseException`. Khi thiết kế server, đừng giữ một worker thread chờ lock vô thời hạn nếu độ trễ có SLA; cân nhắc `tryLock` với deadline/backoff do ứng dụng quản lý hoặc một cơ chế quản lý tài nguyên phù hợp.

**Điều kiện quyền:**

- Xin shared lock với channel chỉ mở `WRITE` có thể ném `NonReadableChannelException`.
- Xin exclusive lock với channel chỉ mở `READ` có thể ném `NonWritableChannelException`.
- Cần thêm quyền truy cập và policy OS phù hợp; `AccessDeniedException`/`IOException` có thể phát sinh, kể cả khi mode Java đúng.
- Một số filesystem/provider không hỗ trợ cơ chế cần thiết hoặc có giới hạn về phạm vi. Tránh khẳng định “mọi hệ điều hành chắc chắn cho phép mọi vùng”.

## 5. Ví dụ Java 17+ kiểm chứng vùng byte và khóa chồng lấn trong một JVM

Chương trình tạo file tạm 8 byte, mở hai `FileChannel` riêng đến **cùng file**, yêu cầu exclusive lock trên `[0, 4)`, kiểm tra vùng chồng lấn, và thử thêm khóa tại `[4, 8)`.

Tạo file `RegionLockDemo.java`:

```java
import java.nio.channels.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

public class RegionLockDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("region-lock-", ".dat");
        try {
            Files.writeString(file, "abcdefgh", StandardCharsets.US_ASCII);
            try (FileChannel first = FileChannel.open(file,
                         StandardOpenOption.READ, StandardOpenOption.WRITE);
                 FileChannel second = FileChannel.open(file,
                         StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                try (FileLock exclusive = first.lock(0, 4, false)) {
                    System.out.println("exclusive=" + !exclusive.isShared());
                    System.out.println("overlaps-3-5=" + exclusive.overlaps(3, 2));
                    System.out.println("overlaps-4-8=" + exclusive.overlaps(4, 4));
                    try {
                        second.tryLock(2, 2, false);
                        throw new AssertionError("Unexpected overlapping lock");
                    } catch (OverlappingFileLockException expected) {
                        System.out.println("same-jvm-overlap=rejected");
                    }
                    try (FileLock adjacent = second.lock(4, 4, false)) {
                        System.out.println("adjacent-lock=" + adjacent.isValid());
                    }
                }
                try (FileLock shared = first.lock(0, 4, true)) {
                    System.out.println("shared-request-acquired=" + shared.isValid());
                    // shared.isShared() có thể false nếu OS chuyển thành exclusive.
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy trên Java 17+ với local filesystem cho phép khóa:

```bash
javac --release 17 RegionLockDemo.java
java RegionLockDemo
```

Kết quả đã kiểm chứng:

```text
exclusive=true
overlaps-3-5=true
overlaps-4-8=false
same-jvm-overlap=rejected
adjacent-lock=true
shared-request-acquired=true
```

Giải thích:

1. `first.lock(0, 4, false)` giữ exclusive lock vùng `[0, 4)`; `isShared() == false`.
2. `overlaps(3, 2)` thử vùng `[3, 5)`, giao vùng đầu ở byte `3` nên `true`. `overlaps(4, 4)` thử vùng `[4, 8)`, không chung byte nên `false`.
3. `second.tryLock(2, 2, false)` là yêu cầu chồng lên khóa của cùng JVM; ném `OverlappingFileLockException`, **không trả `null`**. Điều này đúng dù dùng hai channel riêng.
4. `second.lock(4, 4, false)` không chồng vùng nên trong môi trường đã kiểm chứng có thể được cấp. Khi rời khối `try-with-resources`, cả hai khóa được thả.
5. Sau khi thả exclusive lock, chương trình yêu cầu shared lock `[0, 4)`. Dòng `shared-request-acquired=true` chỉ xác nhận lock nhận được đang hợp lệ; **không khẳng định `isShared() == true`** trên mọi OS. Một số nền tảng có thể đổi shared thành exclusive.

Kết quả ví dụ được ghi nhận trên file system hỗ trợ các thao tác tương ứng. Ở file store không hỗ trợ hoặc có chính sách riêng, thao tác có thể thất bại với lỗi I/O/quyền; phần còn lại của bài giải thích cách xử lý. Chương trình cố ý không tạo hai shared lock chồng vùng trong cùng JVM, vì như vậy sẽ **vi phạm hợp đồng Java**.

## 6. Vòng đời FileLock: lấy, kiểm tra, thả và đóng

`FileLock` là một đối tượng đại diện cho khóa đã cấp, triển khai `AutoCloseable`. Nó có các phương thức:

- `position()`: vị trí byte bắt đầu.
- `size()`: kích thước phạm vi khóa đã cấp; với tham số `size=0`, đối tượng có thể biểu diễn phạm vi tới điểm kết thúc miền file theo hợp đồng.
- `isShared()`: loại khóa **thực tế**, không nhất thiết bằng tham số yêu cầu trên môi trường không hỗ trợ shared.
- `isValid()`: khóa còn hiệu lực theo đối tượng Java không.
- `overlaps(p, n)`: kiểm tra phạm vi chồng lấn về mặt hình học.
- `release()` / `close()`: nhả khóa; rời khối `try-with-resources` tự đóng lock.

Một lock lúc mới cấp là valid; nó mất hiệu lực khi `release`, channel sở hữu được đóng, hoặc JVM kết thúc. **Giữ reference `FileLock` trong collection không làm lock sống lâu hơn channel**. Nếu chương trình thoát quá sớm khỏi block khóa, writer khác có thể bắt đầu thao tác trước khi bạn hoàn tất logic.

Mẫu vận dụng:

```java
// Đoạn minh họa: channel mở READ + WRITE, start/length đã được kiểm tra.
try (FileLock lock = channel.lock(start, length, false)) {
    // Chỉ sau khi lock thành công mới được đọc/sửa/ghi record.
    updateRecord(channel, start);
    // Có thể gọi channel.force(true) tại điểm commit nếu ứng dụng cần durability.
} // close() / release() bảo đảm nhả lock kể cả khi thao tác ném exception.
```

Đoạn trên **không phải source độc lập**: `updateRecord` là hàm nghiệp vụ do ứng dụng định nghĩa. Khi dùng `tryLock`, phải xét kết quả `null` **trước** khi truyền vào `try-with-resources` hoặc dùng lock:

```java
// Đoạn minh họa cho channel và recordRange đã có.
FileLock lock = channel.tryLock(start, length, false);
if (lock == null) {
    // Tiến trình khác đang giữ khóa xung đột: trả retry/busy hợp lý.
} else {
    try (lock) {
        // Thực hiện đơn vị công việc cần khóa.
    }
}
```

Đóng **một channel đang sở hữu FileLock** sẽ làm các lock thuộc channel đó không còn hiệu lực. Đáng chú ý, Javadoc cảnh báo trên một số nền tảng, **đóng một channel có thể làm mất các khóa khác của JVM trên cùng file**, kể cả khóa lấy từ channel khác. Vì vậy, khi dùng khóa để phối hợp các process, nên dùng **một channel được quản lý rõ vòng đời để giữ lock** cho file đó, tránh mở/đóng các channel khác không kiểm soát trong lúc khóa vẫn cần hiệu lực. Cũng không nên trông cậy vào finalizer hoặc GC để nhả khóa đúng thời điểm; nhả rõ bằng `try-with-resources`.

### Cần giữ khóa trong bao lâu?

Khóa cần bao trùm **tất cả thao tác thuộc transaction nghiệp vụ** cần được phối hợp. Với read-modify-write, chỉ giữ lock lúc `write` là chưa đủ: hai tiến trình có thể đã cùng đọc giá trị cũ trước khi đến lượt ghi. Cách đúng là lấy exclusive lock **trước lần đọc đầu**, đọc giá trị hiện tại, tính toán, ghi đủ, xử lý yêu cầu độ bền, rồi thả.

Không giữ khóa lâu trong lúc thực hiện tác vụ không liên quan như gọi API mạng bên ngoài, chờ người dùng, render UI hoặc xử lý CPU không bắt buộc. Một thời gian giữ khóa dài làm các tiến trình khác chờ lâu và có thể dẫn đến kẹt công việc.

## 7. Ví dụ Java 17+: exclusive lock cho bộ đếm lưu trong tệp

Ví dụ thứ hai cho thấy cách biến chuỗi “đọc → cộng → ghi” thành một đơn vị cần exclusive lock. Mỗi lần chạy là một process Java. Chương trình dùng cùng đường dẫn do người dùng truyền vào, nên hai lần chạy liên tiếp tăng giá trị từ `0` lên `1` rồi `2`.

Tạo file `LockedCounterDemo.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.*;

public class LockedCounterDemo {
    private static long readCounter(FileChannel channel) throws IOException {
        if (channel.size() == 0) return 0;
        if (channel.size() != Long.BYTES) {
            throw new IOException("Invalid counter file size");
        }
        ByteBuffer buf = ByteBuffer.allocate(Long.BYTES);
        long offset = 0;
        while (buf.hasRemaining()) {
            int n = channel.read(buf, offset);
            if (n <= 0) throw new IOException("Incomplete counter");
            offset += n;
        }
        buf.flip();
        return buf.getLong();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java LockedCounterDemo counter.dat");
        }
        Path file = Path.of(args[0]);
        try (FileChannel channel = FileChannel.open(file,
                StandardOpenOption.CREATE, StandardOpenOption.READ,
                StandardOpenOption.WRITE);
             FileLock ignored = channel.lock()) {
            long updated = Math.addExact(readCounter(channel), 1);
            ByteBuffer buf = ByteBuffer.allocate(Long.BYTES).putLong(updated);
            buf.flip();
            long offset = 0;
            while (buf.hasRemaining()) {
                int n = channel.write(buf, offset);
                if (n <= 0) throw new IOException("Write made no progress");
                offset += n;
            }
            channel.force(true);
            System.out.println("counter=" + updated);
        }
    }
}
```

Biên dịch và chạy tại thư mục chưa có file `counter.dat`:

```bash
javac --release 17 LockedCounterDemo.java
java LockedCounterDemo counter.dat
java LockedCounterDemo counter.dat
```

Kết quả đã kiểm chứng khi file ban đầu chưa tồn tại:

```text
counter=1
counter=2
```

Điều cần quan sát:

1. `FileChannel.open` với `CREATE`, `READ`, `WRITE` cho phép đọc/ghi cùng file; `channel.lock()` xin **exclusive lock toàn file**.
2. Chương trình **chỉ đọc counter sau khi lấy lock**, tránh hai process hợp tác cùng đọc một giá trị cũ.
3. Lần đầu file rỗng nên giá trị được hiểu là `0`; những lần sau file phải có đúng `Long.BYTES` (8) byte. File hỏng/ghi dở ở kích thước khác 0/8 khiến chương trình báo lỗi.
4. `ByteBuffer.putLong` lưu số theo byte order mặc định của buffer (big-endian); reader trong cùng chương trình dùng `getLong` tương ứng. Không được nhầm layout này với chuỗi chữ số text trong file.
5. `channel.write(buf, offset)` dùng offset tuyệt đối và lặp đến khi hết buffer. `force(true)` được gọi **trước khi giải phóng khóa và in thành công**, để yêu cầu đồng bộ nội dung/metadata của file theo hợp đồng Java.
6. `try-with-resources` nhả khóa và đóng channel nếu thành công hoặc ném exception.

**Giới hạn quan trọng:** Đây là ví dụ về **phối hợp process hợp tác**, không phải cơ chế transaction crash-safe đầy đủ. Nếu chương trình hoặc OS lỗi giữa lúc ghi 8 byte, giá trị có thể bị cập nhật một phần; `force` không biến lần ghi 8 byte thành transaction. Khi triển khai thực tế cần checksum, journal/WAL, bản ghi phiên bản, recovery hoặc database nếu mất điện không được phép làm hỏng counter. Đồng thời tất cả process phải cùng tuân thủ file lock; process bỏ qua advisory lock có thể phá dữ liệu. Nếu chạy hai bản chương trình đồng thời, thứ tự kết quả console không được bảo đảm, nhưng mỗi process dùng cùng giao thức khóa ở môi trường hỗ trợ.

## 8. Tại sao FileLock không dành cho đồng bộ nhiều thread trong cùng JVM?

Các `FileLock` được **giữ thay mặt toàn JVM**. Theo Javadoc, vùng lock đã giữ trong một JVM không được chồng lấn; điều này áp dụng cả khi chúng được lấy trên hai `FileChannel` khác nhau của cùng file. Vì vậy:

```java
// Minh họa lỗi logic, channelA/channelB cùng trỏ một file.
FileLock first = channelA.lock(0, 100, true);
FileLock second = channelB.lock(0, 100, true); // OverlappingFileLockException
```

Đoạn trên là ví dụ **không nên chạy như giải pháp đồng bộ** (cũng chưa khai báo biến và không đóng khóa); dùng để minh họa lý do hai thread Java không thể dựa vào “shared file locks” như nhiều process.

Đối với **thread trong một JVM**:

- Dùng `synchronized`, `ReentrantLock`, `ReadWriteLock` hoặc một worker owner duy nhất để bảo vệ đơn vị nghiệp vụ trên record.
- Nếu muốn nhiều reader đồng thời, có thể dùng `ReadWriteLock` ứng dụng: nhiều thread giữ read lock, writer giữ write lock; không cần lấy thêm nhiều `FileLock` chồng vùng trong JVM.
- Đối với các process ngoài JVM, giữ **một FileLock cấp OS** đại diện cho giao thức liên tiến trình; bên trong JVM vẫn phải có lock theo thread/record khi cần.
- `FileChannel` có hợp đồng đồng bộ một số lời gọi I/O liên quan position, nhưng điều đó **không** biến chuỗi `read → tính toán → write` thành transaction an toàn.

Ví dụ nếu hai thread cùng tăng counter và một JVM đã giữ exclusive FileLock, **cả hai thread vẫn có thể race với nhau bên trong JVM** nếu không có mutex hoặc quản lý owner. FileLock chỉ giải quyết phần phối hợp với **bên ngoài** JVM.

## 9. Advisory vs mandatory: khác biệt theo hệ điều hành và filesystem

File locking của Java ánh xạ tới hệ thống khóa native. Hành vi truy cập bị chặn thực sự phụ thuộc OS, filesystem, network mount và cấu hình.

| Bối cảnh | Điều cần dự kiến |
| --- | --- |
| Linux / Unix với filesystem cục bộ hỗ trợ | Khóa vùng có thể mang tính **advisory**: chương trình không hợp tác có thể vẫn mở/đọc/ghi vùng file. Không mặc định một khóa do JVM A giữ sẽ chặn mọi lời gọi `write` của JVM B nếu JVM B bỏ qua giao thức. |
| Windows với filesystem phù hợp | Một số cơ chế khóa vùng có thể cưỡng chế các thao tác đọc/ghi xung đột ở OS; chính sách mở file, sharing và quyền có thể khiến hành vi khác Unix. Không xây dựng logic dựa trên assumption “mandatory ở mọi Windows volume”. |
| NFS/SMB, ổ mạng | Semantics locking có thể liên quan server, network partition, lease/reconnect và mount options. Các tình huống mất kết nối/khóa hết hiệu lực cần kiểm thử riêng. |
| Docker/container / volume chia sẻ | Container có thể dùng host FS, overlay, mount mạng hoặc quyền user khác. Hai container chỉ phối hợp được nếu backend/file system thực sự hỗ trợ cùng cơ chế khóa. |
| Filesystem ảo/in-memory/provider tùy chỉnh | Khả năng khóa có thể thiếu hoặc khác biệt; cần thử trên đúng provider. |

Vì tính di động, **hãy coi FileLock là advisory** và yêu cầu mọi reader/writer tuân thủ hợp đồng khóa ứng dụng. Đừng khẳng định rằng khóa vùng byte tự cấp quyền đọc/ghi hoặc chống được mọi truy cập từ một chương trình không hợp tác.

Một số OS có hạn chế với file mapping: lấy lock mandatory trên vùng file được memory-map có thể thất bại, hoặc mapping sau khi có lock có thể bị từ chối. Khi phối hợp `MappedByteBuffer` và `FileLock`, cần kiểm thử trực tiếp trên filesystem mục tiêu; không coi hai API luôn tương thích.

### Không coi khóa là “phát hiện đầy đủ process đang mở file”

`tryLock()` thành công chỉ nói JVM xin được một vùng khóa theo cơ chế OS. Nó **không** chứng minh không có process nào đang mở tệp, không có reader nào đang xem nội dung hoặc không có writer ngoài giao thức. Ngược lại, việc thất bại với exception có thể do quyền, khả năng OS, trạng thái channel chứ không nhất thiết “có ai đó đang giữ khóa”.

## 10. Độ bền dữ liệu: khóa không thay thế FileChannel.force

Hai mục tiêu khác nhau:

- **Khóa:** điều phối quyền thực hiện thao tác đồng thời giữa các bên hợp tác trong khoảng thời gian giữ khóa.
- **Độ bền:** khi ứng dụng đã báo giao dịch hoàn tất, dữ liệu có còn sau sự cố theo hợp đồng lưu trữ hay không.

`channel.force(true)` yêu cầu đồng bộ nội dung và metadata file trong phạm vi hợp đồng `FileChannel`, nhưng **không khóa dữ liệu**. `FileLock` giúp giảm tranh chấp khi các process hợp tác nhưng **không buộc dữ liệu xuống đĩa**.

Quy trình thường dùng cho read-modify-write trên file local:

```text
Xin exclusive lock trên vùng record phù hợp
          |
          v
Đọc dữ liệu bên trong lock
          |
          v
Tính toán và ghi đủ bytes
          |
          v
force(true) nếu yêu cầu dữ liệu bền vững
          |
          v
Chỉ lúc hoàn tất hợp đồng commit mới báo thành công
          |
          v
Giải phóng khóa
```

Ngay cả với quy trình này, **độ bền và khả năng phục hồi không tuyệt đối**: Java không bảo đảm giống nhau với remote storage, directory entry có hợp đồng riêng, và crash ở giữa record nhiều bước có thể tạo trạng thái dở dang. Với WAL/database, cơ chế commit phức tạp hơn một khóa và một `force`.

Điều cần nhớ: việc gọi `force` trong lúc đang giữ FileLock là lựa chọn hữu ích khi muốn bảo vệ ranh giới commit giữa các **process hợp tác**; không có quy định rằng `FileLock` tự force hoặc `force` tự lock.

## 11. Các lỗi và exception cần xử lý

| Exception / kết quả | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `tryLock(...) == null` | Khóa chồng lấn đang được **process khác** giữ. | Trả trạng thái busy, thử lại với backoff/deadline hoặc chuyển sang queue theo yêu cầu. |
| `OverlappingFileLockException` | JVM hiện tại đã giữ hoặc đang chờ xin khóa chồng lấn trên cùng file. | Kiểm tra ownership/khóa vùng trong JVM; không retry theo vòng vô hạn như với `null`. |
| `NonReadableChannelException` | Yêu cầu shared lock trên channel không đọc được. | Mở channel với `READ`, kiểm tra quyền file/OS. |
| `NonWritableChannelException` | Yêu cầu exclusive lock trên channel không ghi được. | Mở channel với `WRITE`, kiểm tra quyền file/OS. |
| `IllegalArgumentException` | `position` hoặc `size` âm, hoặc tổng vùng tràn số không hợp lệ. | Kiểm tra offset và length, dùng `Math.addExact` / `Math.multiplyExact` khi tính vùng. |
| `ClosedChannelException` | Channel đã đóng khi gọi lock/tryLock. | Quản lý vòng đời channel một nơi, tránh sử dụng sau close. |
| `FileLockInterruptionException` | Thread đang xin lock blocking bị interrupt. | Tuân thủ chính sách cancel/shutdown, không nuốt lỗi rồi báo đã có lock. |
| `AsynchronousCloseException` | Channel bị thread khác đóng trong lúc chờ/tác vụ I/O. | Dừng/khôi phục đúng vòng đời, không coi đã giữ được lock. |
| `IOException` / lỗi file store | Lỗi native I/O, quyền, mount, mạng, thiết bị hoặc hỗ trợ platform. | Ghi log path, vùng khóa, thao tác và chính sách retry phù hợp; không phá dữ liệu hiện có. |

Đừng bắt mọi exception rồi tiếp tục đọc/ghi như thể lock đã được cấp. Với `tryLock`, `null` có ý nghĩa cụ thể là **không lấy được khóa do xung đột bên ngoài JVM**; exception là trạng thái cần phân tích khác. Khi `lock` bị interrupt hoặc channel đóng, không được giả định đã lấy khóa.

### Vấn đề deadlock khi nhiều vùng

Giả sử một giao dịch cần khóa record A và B:

- Process 1 giữ A rồi chờ B.
- Process 2 giữ B rồi chờ A.

Nếu cả hai dùng `lock` chờ blocking, có thể bị kẹt theo hình thức deadlock giữa các process. Để tránh:

1. Chuẩn hóa thứ tự xin lock (ví dụ theo byte offset tăng dần).
2. Không giữ một khóa rồi chờ vô hạn một khóa khác không có thời hạn.
3. Nếu dùng `tryLock` và không lấy được toàn bộ khóa, hãy giải phóng những khóa đã lấy và retry theo policy phù hợp.
4. Tránh gọi dịch vụ ngoài hoặc chờ input của user trong khi đang giữ nhiều file lock.

Một số OS có cơ chế deadlock detection ở mức native nhưng **Java FileLock không hứa giải quyết deadlock nghiệp vụ cho bạn**.

## 12. Checklist thiết kế đúng

Trước khi triển khai hệ thống chia sẻ tệp:

1. **Ai tham gia?** Nhiều thread trong một JVM, nhiều JVM/process hay cả hai? Thread dùng mutex/lock ứng dụng; process dùng FileLock nếu mọi bên cùng hợp tác và OS hỗ trợ.
2. **Vùng khóa là gì?** Byte offset và length đến từ đâu? Record cố định hay biến độ dài? Có chồng lấn hoặc mở rộng file không?
3. **Cần shared hay exclusive?** Reader cần nhiều process đọc cùng lúc; writer/read-modify-write cần exclusive. Shared có thể bị hệ thống chuyển sang exclusive.
4. **Channel có đúng quyền không?** `READ` cho shared, `WRITE` cho exclusive; policy OS có cho phép tạo lock không?
5. **Có xử lý `null` và exception riêng không?** `tryLock` gặp xung đột process khác trả `null`, cùng JVM chồng lấn ném `OverlappingFileLockException`.
6. **Vòng đời khóa rõ chưa?** Lấy trước lần đọc cần bảo vệ, giữ đến khi kết thúc ghi/force theo contract, thả trong `try-with-resources`.
7. **Có channel khác bị đóng không?** Trên một số OS, đóng một channel cùng file có thể làm mất các lock của JVM; quản lý duy nhất owner file/lock.
8. **Có process không hợp tác không?** Advisory lock đòi hỏi tất cả reader/writer tuân thủ giao thức; một `tryLock` thành công không chứng minh tệp không bị ai truy cập.
9. **Có yêu cầu durability không?** Nếu có, dùng `force`/giao thức recovery đúng loại lưu trữ; lock không phải flush.
10. **Thử trên đúng môi trường:** filesystem local/network, Windows/Linux/macOS, container/VM, quyền user, trạng thái process crash, timeout và network disconnect.
11. **Đo chi phí chờ khóa:** lock granularity quá rộng làm throughput giảm; vùng quá hẹp làm mất bảo vệ. Thử với nhiều process thật thay vì chỉ thread.
12. **Có cách khôi phục khi crash giữa write?** Cần record format kiểm chứng, WAL, atomic replace hoặc storage engine khi dữ liệu không được phép hỏng.

### Câu hỏi tự kiểm tra

**1. Nếu hai process đều chỉ đọc vùng `[0, 10)`, có thể xin shared lock đồng thời không?**

Theo semantics shared lock, các request chồng vùng từ nhiều process có thể cùng tồn tại nếu platform hỗ trợ và tất cả tuân thủ giao thức. Một số OS có thể nâng shared thành exclusive nên khả năng đồng thời thực tế thay đổi.

**2. Hai channel trong cùng một JVM xin shared lock cùng vùng có luôn được không?**

**Không.** Javadoc cấm FileLock cùng JVM chồng lấn, kể cả đều xin shared; `OverlappingFileLockException` được ném. Dùng `ReadWriteLock`/mutex trong JVM.

**3. Đã khóa `[0, 100)`, xin thêm `[100, 200)` có chồng lấn không?**

**Không.** Các vùng là nửa mở: byte `100` không thuộc khóa đầu.

**4. `tryLock` trả `null` khác `OverlappingFileLockException` thế nào?**

`null` thể hiện xung đột khóa từ **process khác**; `OverlappingFileLockException` thể hiện lock chồng lấn đã giữ hoặc yêu cầu chồng vùng đang đợi trong cùng JVM.

**5. Nếu file 8 byte mà chương trình khóa `[100, 200)` thì khóa có bắt buộc thất bại không?**

**Không.** Hợp đồng cho phép xin khóa vùng ngoài phạm vi kích thước file hiện tại, miễn hệ thống hỗ trợ. Nếu sau đó file mở rộng, khóa vùng cố định vẫn chỉ bao phủ các byte đã xác định.

**6. Tại sao lấy FileLock và ghi dữ liệu chưa đủ để cam kết chống mất điện?**

Vì FileLock quản lý phối hợp truy cập, không yêu cầu dữ liệu được flush xuống thiết bị. Cần `force` và giao thức recovery phù hợp OS/filesystem, đồng thời xét partial write.

**7. Có thể coi `FileLock` như bảo mật chặn mọi tiến trình đọc file không?**

**Không.** Đây là cơ chế phối hợp file I/O, có thể advisory. Quyền truy cập thuộc filesystem ACL/mode và OS policy; process không hợp tác có thể bỏ qua khóa trên một số platform.

## Tài liệu chính thức

- [Java SE 21 — FileLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): shared/exclusive lock, vòng đời, isShared/isValid/overlaps, advisory/mandatory và giới hạn JVM.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): lock/tryLock, vùng byte, tham số size=0, ngoại lệ và force.
- [Java SE 21 — OverlappingFileLockException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/OverlappingFileLockException.html): khóa chồng vùng trong cùng JVM.
- [Java SE 21 — AsynchronousFileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): API khóa trong I/O bất đồng bộ với callback/Future và giới hạn theo platform.

Điểm mấu chốt: **exclusive/shared lock quyết định yêu cầu phối hợp đọc/ghi giữa các process; `position` và `size` quyết định chính xác vùng byte; khóa không dùng thay mutex cho thread trong JVM; và muốn dữ liệu bền sau crash thì cần thêm force cùng giao thức cập nhật/khôi phục đúng đắn.**