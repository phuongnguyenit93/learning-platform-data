# Không chia sẻ file pointer giữa nhiều thao tác mà thiếu phối hợp

Trong **truy cập ngẫu nhiên (random access)**, một file có thể được đọc hoặc ghi tại vị trí bất kỳ thay vì chỉ đi tuần tự từ đầu đến cuối. Java cung cấp `RandomAccessFile`, `FileChannel` và `SeekableByteChannel` để làm việc này. Điểm dễ sai nhất khi nhiều thao tác hoặc nhiều thread cùng dùng một đối tượng I/O là **file pointer (vị trí hiện tại) thuộc về đối tượng truy cập đang được chia sẻ**, nên một thao tác có thể làm thay đổi vị trí mà thao tác khác dự định sử dụng.

Quy tắc thực hành:

> Nếu các thao tác cần những offset riêng, hãy dùng API đọc/ghi theo **vị trí tuyệt đối** khi có thể. Nếu buộc phải dùng chuỗi `seek/position → read/write` dựa trên con trỏ chung, phải phối hợp **toàn bộ chuỗi thao tác** qua một cơ chế đồng bộ chung. Và ngay cả khi không còn tranh chấp con trỏ, các thao tác chồng lấn cùng byte hoặc cùng metadata vẫn cần quy tắc phối hợp dữ liệu.

Bài này tập trung vào **tính đúng đắn khi sử dụng file pointer**, các giới hạn thread-safety của API và cách thiết kế thao tác đọc/ghi có thể kiểm chứng. Không cần giả định rằng dữ liệu “đang nằm ở vị trí đúng” chỉ vì lệnh `seek` trước đó đã trả về thành công.

## 1. File pointer là gì và khác với offset nào?

**File pointer / current file position** là vị trí byte mà thao tác I/O *tương đối* tiếp theo sẽ sử dụng. Thông thường, sau khi đọc/ghi thành công `n` byte, vị trí tăng thêm `n`. Offset được tính từ đầu file, bắt đầu tại `0`, và đo bằng **byte**, không phải chỉ số ký tự Unicode.

Ví dụ file ASCII chứa `ABCDEFGH` có 8 byte:

- Vị trí `0`: byte `A`; vị trí `3`: byte `D`; vị trí `8`: ngay sau cuối file (EOF).
- `seek(3)` hoặc `position(3)` chỉ đặt vị trí đọc/ghi tiếp theo, không tự đọc hay ghi dữ liệu.
- `read` sau đó trả về một hay nhiều byte và thường dịch vị trí hiện tại theo số byte đã thực sự đọc.
- Với UTF-8, một ký tự tiếng Việt có thể chiếm nhiều byte. `position(3)` không có nghĩa “ký tự thứ tư”; đặt sai ranh giới mã hóa có thể cắt ngang ký tự.

Đừng nhầm các loại vị trí sau:

| Loại vị trí | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `RandomAccessFile.getFilePointer()` | Trạng thái của đối tượng `RandomAccessFile` / handle liên quan | Offset cho thao tác đọc/ghi kế tiếp qua `RandomAccessFile`. |
| `FileChannel.position()` | Trạng thái của channel | Offset cho các lệnh `read(ByteBuffer)` hoặc `write(ByteBuffer)` không truyền offset riêng. |
| `FileChannel.read(dst, long position)` / `write(src, long position)` | Tham số của **một lệnh** | Offset tuyệt đối của lệnh đó; không thay đổi `channel.position()`. |
| `ByteBuffer.position()` | Trạng thái trong bộ đệm của caller | Chỉ số trong `ByteBuffer` nơi dữ liệu được nhận/lấy tiếp theo; **không phải** offset trong file. |

`ByteBuffer` cũng là trạng thái mutable: một lần `read` có thể thay đổi `buffer.position()` dù thao tác với file là positional. Mỗi tác vụ nên dùng buffer riêng hoặc bảo đảm quy tắc sở hữu buffer, không chỉ phối hợp file pointer.

## 2. Các API thay đổi hoặc chia sẻ vị trí

### `RandomAccessFile`

`RandomAccessFile` cung cấp:

- `seek(long pos)`: đặt file pointer trước một lần đọc/ghi; `pos` phải không âm.
- `getFilePointer()`: trả vị trí byte hiện tại.
- `read(...)`, `readFully(...)`, `write(...)` và các phương thức đọc/ghi kiểu nguyên thủy: sử dụng rồi cập nhật pointer.
- `length()` / `setLength(...)`: xem/thay kích thước file; thao tác thay kích thước có thể ảnh hưởng vị trí hoặc dữ liệu các luồng khác đang dùng.

**Điểm đặc biệt:** `raf.getChannel()` trả về channel gắn với cùng `RandomAccessFile`. Javadoc quy định vị trí của channel này luôn bằng file pointer của `raf`; gọi `raf.seek` hoặc đọc/ghi qua `raf` ảnh hưởng `channel.position()`, và thao tác tương đối qua channel ảnh hưởng `raf.getFilePointer()`. Đừng xem chúng như hai con trỏ độc lập.

### `FileChannel`

Có hai nhóm API cần phân biệt:

```java
channel.position(100);     // đặt shared current position của channel
channel.read(buffer);      // đọc từ current position; tăng position
channel.write(buffer);     // ghi tại current position; tăng position

channel.read(buffer, 100); // đọc tại offset 100; KHÔNG đổi channel.position()
channel.write(buffer, 200);// ghi tại offset 200; KHÔNG đổi channel.position()
```

Đoạn trên là **minh họa API**, giả định `channel` và `buffer` đã được khai báo, có quyền và mode phù hợp. Phương thức đọc/ghi có thể truyền ít byte hơn `buffer.remaining()`; khi cần đọc/ghi đủ, phải lặp và cập nhật offset theo số byte *thực sự* xử lý.

Theo Javadoc `FileChannel` của Java 21, channel **có thể được dùng từ nhiều thread**. Hệ thống chỉ cho phép một thao tác có liên quan đến vị trí của channel hoặc có thể thay đổi kích thước file đang thực hiện tại một thời điểm; các thao tác cùng loại đến sau sẽ chờ thao tác trước hoàn tất. Các thao tác có offset tường minh có thể chạy đồng thời, nhưng việc chúng có thật sự song song hay không phụ thuộc implementation.

Điều trên **không** có nghĩa chuỗi `position(x); write(data)` được bảo vệ như một transaction, cũng **không** có nghĩa hai tác vụ cập nhật cùng đoạn file sẽ giữ được logic của ứng dụng. “Thread-safe API” nói về hợp đồng trạng thái nội tại của một lần gọi, còn **tính đúng đắn của thao tác nhiều bước** là trách nhiệm của chương trình.

### `SeekableByteChannel` và các nguồn khác

`SeekableByteChannel` định nghĩa `position()`, `position(long)`, `read`, `write`, `size`, `truncate`, nhưng không cung cấp overload đọc/ghi offset tuyệt đối trong chính interface. Khi chỉ có `SeekableByteChannel`, không mặc nhiên áp hợp đồng thread-safety chuyên biệt của `FileChannel` cho mọi provider. Nếu cần thay đổi pointer trước I/O, bảo vệ nguyên cụm thao tác bằng một cơ chế chung hoặc cấp channel độc lập cho từng tác vụ khi phù hợp.

## 3. Cách race condition xảy ra dù mỗi lời gọi riêng lẻ hợp lệ

Giả sử một `FileChannel` mở file 10 byte ban đầu: `abcdefghij`. Hai thao tác nghiệp vụ cần ghi:

- **A** muốn ghi `XX` tại byte `0..1`.
- **B** muốn ghi `YY` tại byte `4..5`.

Nếu cùng dùng lệnh tương đối, lịch xen kẽ hợp lệ có thể là:

| Thứ tự | Thao tác | Current position sau thao tác |
| --- | --- | --- |
| 1 | A: `channel.position(0)` | `0` |
| 2 | B: `channel.position(4)` | `4` |
| 3 | A: `channel.write(XX)` | `6` nếu ghi đủ 2 byte |
| 4 | B: `channel.write(YY)` | `8` nếu ghi đủ 2 byte |

A vô tình ghi tại `4..5` và B ghi tại `6..7`. Kết quả theo lịch trên là `abcdXXYYij`, khác với `XXcdYYghij` mà hai thao tác dự định. Hai thao tác đặt vị trí và hai thao tác ghi đều có thể hoàn tất thành công, không cần ném exception.

Lịch này là **mô hình minh họa một interleaving**, không phải khẳng định thread nào chắc chắn được scheduler chạy trước. Vấn đề cốt lõi là việc đặt vị trí và thực hiện I/O là **hai lời gọi riêng**. Đồng bộ từng lời gọi độc lập không tạo ra tính nguyên tử cho chuỗi.

Các biến thể phổ biến:

1. Một thread gọi `seek(start)`, thread khác gọi `seek(otherStart)`, rồi thread đầu đọc nhầm khối.
2. Một luồng đọc header bằng `readInt()`, luồng khác ghi dữ liệu và dịch pointer, khiến lần đọc payload tiếp theo lấy nhầm vị trí.
3. Một method tiện ích dùng `RandomAccessFile` còn method khác dùng `raf.getChannel()`, tưởng là hai cursor riêng nhưng thực tế cùng dùng một.
4. Hai thread cùng chia sẻ một `ByteBuffer` nên `flip`, `clear` hoặc `position` của buffer xen vào nhau, dù vị trí file của mỗi lệnh đã là tuyệt đối.
5. Chương trình tính `long end = channel.size()` rồi cho nhiều thread ghi tại `end`, dẫn đến việc các thread tính cùng offset và ghi đè nhau.

Việc thêm `Thread.sleep(...)`, tăng/giảm số thread hoặc thấy “chạy ổn” nhiều lần không chứng minh code không có race. Thread scheduling, OS caching, file system và tải máy đều có thể làm lỗi lúc xuất hiện lúc biến mất.

## 4. Ví dụ chạy được: `RandomAccessFile` và `getChannel()` dùng chung pointer

Tạo file `PointerCoupling.java`:

```java
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class PointerCoupling {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("raf-position-", ".dat");
        try {
            Files.writeString(file, "ABCDE", StandardCharsets.US_ASCII);
            try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "rw")) {
                FileChannel channel = raf.getChannel();
                raf.seek(1);
                System.out.println("channel-after-seek=" + channel.position());

                ByteBuffer next = ByteBuffer.allocate(1);
                channel.read(next);
                next.flip();
                System.out.println("relative-byte=" + (char) next.get());
                System.out.println("raf-after-relative=" + raf.getFilePointer());

                ByteBuffer atFour = ByteBuffer.allocate(1);
                channel.read(atFour, 4);
                atFour.flip();
                System.out.println("absolute-byte=" + (char) atFour.get());
                System.out.println("raf-after-absolute=" + raf.getFilePointer());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch/chạy với Java 17+:

```bash
javac --release 17 PointerCoupling.java
java PointerCoupling
```

Output trên hệ thống file thông thường:

```text
channel-after-seek=1
relative-byte=B
raf-after-relative=2
absolute-byte=E
raf-after-absolute=2
```

Giải thích từng mốc:

- `raf.seek(1)` làm `channel.position()` thành `1`.
- `channel.read(next)` đọc `B` ở vị trí `1` rồi đưa pointer chung đến `2`.
- `channel.read(atFour, 4)` đọc `E` theo offset tuyệt đối `4` nên pointer chung **vẫn là `2`**.
- `next.flip()` và `atFour.flip()` điều chỉnh vị trí của từng buffer để đọc byte vừa nạp; chúng không điều chỉnh file pointer.

Để chương trình ngắn gọn, ví dụ thao tác trên tệp tạm 5 byte không có writer khác và đọc 1 byte. Trong ứng dụng xử lý file có thể đổi kích thước hoặc nhiều source bất định, hãy kiểm tra kết quả `read` và EOF (`-1`), xử lý việc đọc ít byte hơn yêu cầu.

**Lưu ý vòng đời:** `RandomAccessFile` và channel lấy từ `getChannel()` gắn với nhau; đóng `raf` cũng đóng channel liên quan và ngược lại. Không phát channel này cho một tác vụ cần dùng lâu hơn vòng đời chủ sở hữu. Nếu một thread đóng channel khi thread khác đang I/O, xử lý ngoại lệ đóng/hủy thao tác theo hợp đồng thay vì quy lỗi cho pointer.

## 5. Cách ưu tiên: offset riêng với `FileChannel.read/write(ByteBuffer, long)`

Khi tác vụ đã biết offset cần xử lý, overload positional là cách đơn giản để loại bỏ tranh chấp **current position**:

```java
int count = channel.read(targetBuffer, offset);  // không đổi channel.position()
int sent  = channel.write(sourceBuffer, offset); // không đổi channel.position()
```

Ở đây:

- `offset` do nghiệp vụ xác định cho từng vùng dữ liệu, thường truyền qua tham số task.
- Buffer thuộc quyền sử dụng của một tác vụ trong suốt thời gian I/O; `ByteBuffer` không tự an toàn khi nhiều thread cùng thay đổi state.
- Sau mỗi lần `read`/`write`, kiểm tra số byte thực tế, cập nhật offset và tiếp tục nếu còn dữ liệu.
- Offset không âm; cộng offset với số byte đã xử lý phải tránh tràn `long`.
- Không mở channel với `StandardOpenOption.APPEND` nếu logic dựa vào offset ghi tuyệt đối: Javadoc quy định hành vi `write` tại vị trí cho trước khi channel đang mở ở chế độ APPEND là **không xác định**.

Phương pháp này tránh việc A thay đổi pointer của B, **nhưng không tự giải quyết** hai tác vụ cùng ghi byte `100..199`, đọc một record trong lúc record khác bị sửa, append chồng lấn, hoặc cùng gọi `truncate`. Với yêu cầu giữ tính nhất quán, vẫn phải cấp phát vùng không chồng lấn hoặc khóa ở mức dữ liệu/record.

### Ví dụ chạy được: hai thread ghi hai vùng độc lập

Tạo file `IndependentOffsets.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public class IndependentOffsets {
    static int writeAllAt(FileChannel channel, ByteBuffer source, long offset)
            throws IOException {
        int written = 0;
        while (source.hasRemaining()) {
            int n = channel.write(source, Math.addExact(offset, written));
            if (n == 0) throw new IOException("Write made no progress");
            written += n;
        }
        return written;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-slots-", ".dat");
        try {
            Files.writeString(file, "........", StandardCharsets.US_ASCII);
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                ExecutorService pool = Executors.newFixedThreadPool(2);
                try {
                    Future<Integer> a = pool.submit(() -> writeAllAt(channel,
                        ByteBuffer.wrap("ABCD".getBytes(StandardCharsets.US_ASCII)), 0));
                    Future<Integer> b = pool.submit(() -> writeAllAt(channel,
                        ByteBuffer.wrap("WXYZ".getBytes(StandardCharsets.US_ASCII)), 4));
                    System.out.println("bytes=" + a.get() + "," + b.get());
                    System.out.println("file=" + Files.readString(file, StandardCharsets.US_ASCII));
                    System.out.println("channel-position=" + channel.position());
                } finally {
                    pool.shutdown();
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 IndependentOffsets.java
java IndependentOffsets
```

Output đã kiểm chứng với Java 17 bytecode trên filesystem thông thường:

```text
bytes=4,4
file=ABCDWXYZ
channel-position=0
```

Vì hai task có **offset tuyệt đối không chồng lấn** (`0..3` và `4..7`), kết quả file nhất quán dù task nào chạy trước. Mỗi task sở hữu một `ByteBuffer` riêng và được `Future.get()` xác nhận đã hoàn tất trước khi đọc kết quả. Channel không bị dịch current position; nó vẫn ở `0`. Hàm `writeAllAt` lặp khi ghi ngắn, tự tăng offset bằng số byte đã ghi, và cố ý báo lỗi nếu không tiến triển để không lặp vô hạn. Việc phải phối hợp khi có ghi chồng lấn hoặc thay kích thước file vẫn áp dụng.

Ví dụ cố ý tạo tệp có đúng 8 byte trước khi hai task bắt đầu. Với tệp có thể mở rộng, thao tác positional ghi vượt cuối tệp vẫn có thể thay đổi kích thước; hợp đồng `FileChannel` có thêm quy tắc tuần tự hóa thao tác có thể thay đổi kích thước. **Điều đó không thay cho cấp phát offset chính xác**.

## 6. Khi phải dùng shared cursor: khóa toàn bộ thao tác nhiều bước

Một số thư viện hoặc interface chỉ cung cấp `seek` / `position` rồi `read` / `write`. Khi đó, hãy định nghĩa *một* lock chung cho mọi nơi truy cập cùng pointer:

```java
final Object cursorLock = new Object(); // field dùng chung của owner

byte[] readBlock(RandomAccessFile raf, long offset, int length)
        throws java.io.IOException {
    byte[] bytes = new byte[length];
    synchronized (cursorLock) {
        raf.seek(offset);
        raf.readFully(bytes);
    }
    return bytes;
}
```

Đây là **đoạn minh họa nằm trong class quản lý `cursorLock`**, không phải Java source độc lập. `readFully` có thể ném `EOFException` nếu không đủ bytes. Phải dùng **cùng một lock** cho toàn bộ code gọi `seek`, `read`, `write`, `getChannel().position` hay các thao tác tương đối trên chính handle đó. Khóa chỉ riêng `seek` hoặc chỉ `readFully` là chưa đủ:

```java
// SAI: hai khối synchronized rời nhau, thread khác có thể xen giữa.
synchronized (cursorLock) { raf.seek(offset); }
synchronized (cursorLock) { raf.readFully(bytes); }
```

Khối đồng bộ một lần phía trên bảo đảm các thread cùng tuân thủ lock không xen kẽ **giữa seek và readFully**. Tránh giữ lock trong các thao tác lâu không liên quan đến cursor; thực hiện xử lý dữ liệu phức tạp sau khi đọc xong nếu khả thi. Khóa này chỉ có hiệu lực trong JVM; một tiến trình khác dùng file riêng vẫn có thể sửa nội dung.

Có thể dùng `ReentrantLock` thay `synchronized` để hỗ trợ timeout hoặc interruptible acquisition; nguyên tắc không đổi: lock phải bao trùm toàn bộ đơn vị nghiệp vụ đang dựa vào pointer và mọi tác vụ dùng pointer phải tham gia.

**Không dựa vào `volatile long lastOffset` để bảo vệ chuỗi `seek + read`.** `volatile` chỉ tạo quy tắc visibility/order cho biến Java đó; nó không khóa trạng thái file pointer bên trong I/O handle. `AtomicLong.getAndAdd(length)` có thể dùng để **cấp phát offset không trùng nhau** cho các tác vụ nếu vùng file được quản lý đúng, nhưng bản thân nó cũng không biến các lần ghi nhiều bước thành một transaction.

## 7. Chọn kiến trúc phối hợp theo tình huống

| Tình huống | Thiết kế phù hợp | Giới hạn cần kiểm tra |
| --- | --- | --- |
| Nhiều task đọc các đoạn khác nhau của một file ít thay đổi | Dùng `FileChannel.read(buffer, offset)`, buffer riêng từng task. | Mỗi task xử lý short read / EOF; file vẫn có thể bị writer ngoài chương trình thay đổi. |
| Nhiều task ghi các ô/record có offset đã được cấp phát và không chồng lấn | `FileChannel.write(buffer, offset)`, loop khi ghi ngắn; cấp phát offset tập trung. | Chống tràn offset, tránh `truncate` đồng thời, tránh APPEND, đảm bảo layout record. |
| Cùng một `RandomAccessFile` và cần chuỗi `seek → read/write` | Một khóa chung cho toàn bộ chuỗi; có thể gom thao tác trong một owner/service. | Mọi caller phải tuân thủ; các tác vụ có thể chờ lâu vì I/O. |
| Mỗi worker có thể mở một channel riêng tới cùng file | Một channel riêng cho mỗi worker, mỗi channel có position riêng. | Nội dung file vẫn chung; các writer overlap phải phối hợp; không suy ra atomicity của record. |
| Nhiều worker append record có độ dài biến đổi | Một writer duy nhất nhận record qua queue, hoặc bộ cấp phát offset/độ dài chính xác rồi positional writes. | Cần định nghĩa record framing, thứ tự, lỗi ghi dở và recovery; APPEND không bảo đảm tính nguyên tử trên mọi hệ. |
| Nhiều tiến trình cùng thao tác file | Thiết kế giao thức phối hợp liên tiến trình; cân nhắc file lock và kiểm tra semantics trên OS/filesystem. | File lock phụ thuộc OS; không giải quyết logic giữa thread trong cùng JVM. |
| Yêu cầu đọc snapshot nhất quán trong khi có writer | Khóa dữ liệu/record, snapshot riêng, copy-on-write hoặc versioning phù hợp. | Positional API không tự tạo snapshot hay bảo đảm nhóm nhiều lệnh là transaction. |

Nếu nhiều tác vụ dùng queue tới một owner duy nhất, owner có thể thực hiện các thao tác tương đối theo thứ tự xác định. Mẫu này thường dễ lý giải với log có record thay đổi độ dài hoặc binary format nhiều trường. Tuy nhiên, quản lý một worker ghi duy nhất vẫn phải xử lý partial write, lỗi I/O và quá trình shutdown hợp lý.

Một **channel riêng cho mỗi thread** giúp tách cursor nhưng không có nghĩa file riêng. Nếu hai channel cùng mở cùng path, cả hai vẫn có thể ghi lên cùng byte; thiếu phối hợp dữ liệu có thể gây lost update. Nếu một channel lấy từ `raf.getChannel()`, đó **không phải** channel độc lập với chính `raf`.

## 8. Lock nào bảo vệ cái gì?

Phân biệt ba tầng đồng bộ:

1. **Cursor lock trong JVM:** `synchronized` hoặc `ReentrantLock` bảo vệ state `position`/`seek` và các thao tác nhiều bước thông qua đúng owner I/O. Đây là lựa chọn khi cần phối hợp các thread chung pointer.
2. **Khóa dữ liệu/record trong ứng dụng:** đảm bảo hai tác vụ không sửa cùng bản ghi một cách mâu thuẫn. Có thể là lock theo record/range, phân vùng offset hoặc một writer. Cần bảo vệ cả chuỗi “đọc → tính toán → ghi” nếu logic là read-modify-write.
3. **File lock cấp OS qua `FileChannel.lock` / `tryLock`:** dùng để phối hợp với các tiến trình khác khi môi trường hỗ trợ đúng semantics. Javadoc nêu rõ file lock được giữ thay mặt **cả JVM**, không phù hợp để điều phối nhiều thread trong cùng JVM; hành vi advisory/mandatory và khả năng shared lock tùy OS.

Ví dụ, `channel.lock(0, 100, false)` có thể xin khóa riêng trên phạm vi file, nhưng **không** nên thay thế `synchronized(cursorLock)` bằng lệnh này để bảo vệ hai thread trong một tiến trình. Trong JVM, yêu cầu lock chồng lấn còn có thể ném `OverlappingFileLockException`. Tùy hệ thống, tiến trình khác có thể bỏ qua khóa advisory, và filesystem mạng có thể có ràng buộc riêng. Giải pháp cần xác định cụ thể “không được xen kẽ cursor”, “không được ghi đè record” hay “phải phối hợp với process khác” trước khi chọn loại lock.

### Atomicity khác thread-safety và durability

- **Thread-safe**: API có thể được gọi đồng thời trong phạm vi bảo đảm của nó mà không làm hỏng trạng thái nội bộ.
- **Atomic theo nghiệp vụ**: một nhóm thao tác (ví dụ đọc số dư, cộng 1, ghi lại) xuất hiện như một đơn vị không bị chen ngang theo quy tắc ứng dụng. `FileChannel` không tự cung cấp transaction cho nhóm thao tác này.
- **Durable**: dữ liệu tồn tại sau lỗi máy/mất điện theo cơ chế lưu trữ; `FileChannel.force(...)` liên quan việc đẩy cập nhật xuống storage nhưng không tạo ra lock hay bảo đảm transaction logic giữa nhiều writer.

Không dùng `force(true)` để sửa race, và cũng không xem một mutex trong JVM là đủ để bảo đảm durability sau crash.

## 9. Các lỗi thường gặp và cách phát hiện

**Sai 1 — Đặt vị trí rồi thực hiện việc khác trước khi đọc/ghi.**

```java
channel.position(offset);
doSomethingThatMayUseTheSameChannel();
channel.read(buffer); // offset không còn chắc chắn như dự định
```

Đây là đoạn minh họa. Cách sửa tốt nhất khi có `FileChannel`: `channel.read(buffer, offset)`. Nếu không thể dùng positional API, đặt cả chuỗi dưới cùng lock và không gọi callback tùy ý khi đang giữ lock.

**Sai 2 — Coi thread-safe của `FileChannel` là transaction.**

```java
long old = channel.position();
channel.position(recordOffset);
channel.write(record);
channel.position(old);
```

Đây là đoạn minh họa. Giữa từng lời gọi, task khác vẫn có thể thay đổi position; việc khôi phục `old` còn có thể ghi đè vị trí mà task khác vừa thiết lập. Dùng write positional hoặc một lock bao trùm toàn bộ chuỗi khi thật sự cần lưu/khôi phục position.

**Sai 3 — Giả định một lần `read`/`write` xử lý đủ buffer.**

```java
// Kết quả có thể nhỏ hơn buffer.remaining() trước lời gọi.
int n = channel.write(buffer, offset);
```

Cần cập nhật `offset += n` và lặp nếu còn dữ liệu; với đọc, xử lý `-1` khi EOF, và chính sách xử lý `0` nếu không có tiến triển. Mỗi task phải sở hữu buffer cho đến khi lệnh I/O hoàn tất. Nếu file chứa record nhị phân, ghi dở có thể tạo record không hợp lệ; cần chiến lược lỗi và recovery.

**Sai 4 — Nhiều thread tự tính vị trí cuối file.**

```java
long offset = channel.size();
channel.write(buffer, offset);
```

Đây là đoạn minh họa. Hai task có thể cùng lấy một giá trị `size` trước khi bắt đầu ghi. Giải pháp là writer tập trung hoặc một cơ chế cấp phát vùng có tính nguyên tử ở tầng ứng dụng, đồng thời bảo vệ các thao tác resize/truncate liên quan. `StandardOpenOption.APPEND` cũng không nên được hiểu là mọi nền tảng đều bảo đảm một record nguyên tử.

**Sai 5 — Hiểu nhầm thread-safe của `ByteBuffer`.**

Dùng một buffer chung giữa hai task có thể khiến byte ghi sai hoặc `BufferUnderflowException` / `BufferOverflowException` do `position/limit` thay đổi bất ngờ. `FileChannel.write(src, absoluteOffset)` không khóa buffer cho caller. Tạo buffer riêng, hoặc truyền quyền sở hữu độc quyền cho worker tới khi hoàn tất.

**Sai 6 — Cố sửa race bằng file lock trong cùng JVM.**

`FileLock` là cơ chế phối hợp cấp file/OS với semantics hệ thống; không bảo vệ từng luồng khỏi thay đổi pointer qua cùng `RandomAccessFile`. Dùng mutex/owner trong JVM cho cursor, và thêm file lock nếu có yêu cầu phối hợp liên tiến trình được kiểm chứng.

**Sai 7 — Không xét việc đóng hoặc truncate từ thread khác.**

Khi channel bị đóng giữa I/O, có thể gặp `ClosedChannelException`/`AsynchronousCloseException` hoặc exception liên quan. Khi một worker gọi `truncate` hoặc thay độ dài, offset do worker khác dự định có thể không còn phù hợp. Quản lý vòng đời và phân quyền thao tác metadata, tránh cho worker đọc/ghi độc lập tùy ý đóng shared channel.

## 10. Checklist thiết kế và kiểm thử

Trước khi triển khai:

1. **Xác định sở hữu pointer:** object nào đang giữ pointer? Có `RandomAccessFile` và `getChannel()` dùng chung không? Có callback/helper nào cũng sử dụng nó?
2. **Xác định offset nghiệp vụ:** byte offset đến từ đâu, ai cấp phát, có bị trùng hoặc tràn số không? Có lẫn byte offset và character index không?
3. **Ưu tiên positional I/O:** khi có offset xác định, dùng `read/write(ByteBuffer, long)` với buffer riêng; bảo đảm lặp đủ bytes.
4. **Nếu bắt buộc dùng cursor:** lock nguyên khối `seek/position → read/write`; mọi caller dùng cùng lock; đừng dựa vào việc scheduler có vẻ tuần tự.
5. **Xác định vùng dữ liệu giao nhau:** hai task có thể ghi cùng byte, cùng record, cùng EOF hoặc gọi `truncate` không? Cần một giao thức cho phép/không cho phép overlap.
6. **Quy định ownership/vòng đời:** chỉ chủ sở hữu quyết định đóng channel; công việc bất đồng bộ hoàn tất trước khi close.
7. **Thử interleaving có kiểm soát:** dùng `CountDownLatch`/barrier hoặc trình tự giả lập để tái hiện A đặt pointer → B đổi pointer → A thao tác; không dùng `sleep` như chứng cứ correctness.
8. **Kiểm chứng file thật:** so sánh chính xác bytes ở từng offset, kiểm tra record framing, short I/O, EOF, chạy nhiều worker, và lỗi khi một thao tác thất bại giữa chừng.
9. **Đo độ đúng trước hiệu năng:** dùng positional API hay mutex theo yêu cầu nhất quán; tối ưu số channel/IOPS sau khi xác định correctness trên filesystem triển khai.

### Câu hỏi tự kiểm tra

**Câu 1.** Hai thread cùng dùng một `FileChannel`, mỗi thread gọi `position(...)` rồi `write(...)`. API thread-safe có bảo đảm cả hai ghi đúng offset không?

**Không.** Từng lời gọi hợp lệ, nhưng thread khác có thể xen vào giữa `position` và `write`. Dùng positional write hoặc khóa cả chuỗi.

**Câu 2.** Nếu dùng `channel.write(buffer, offset)` thì đã an toàn hoàn toàn với nhiều thread chưa?

**Chưa.** Nó loại bỏ tranh chấp con trỏ của channel, nhưng hai thread ghi chồng vùng byte, chia sẻ một `ByteBuffer`, thay kích thước file hay cùng cập nhật record vẫn cần phối hợp.

**Câu 3.** `raf.seek(10)` có làm đổi `raf.getChannel().position()` không?

**Có.** `RandomAccessFile` và channel của chính nó dùng chung vị trí. Ngược lại, `channel.read(dst, 20)` là đọc theo vị trí tuyệt đối nên không làm đổi pointer chung.

**Câu 4.** `FileChannel.lock()` có thay được `synchronized` để bảo vệ file pointer giữa hai thread trong một JVM không?

**Không.** `FileLock` không được thiết kế cho đồng bộ thread trong cùng JVM; dùng lock ứng dụng trên toàn bộ thao tác nhiều bước.

**Câu 5.** Vì sao chương trình ghi hai vùng độc lập ở ví dụ `IndependentOffsets` trả `ABCDWXYZ` bất kể task nào xong trước?

Vì mỗi task dùng một offset tuyệt đối khác nhau, mỗi buffer độc lập, hai phạm vi byte không chồng lấn và chương trình chờ cả hai `Future` hoàn tất trước khi đọc file. Không tác vụ nào cần sửa `channel.position()`.

## Tài liệu chính thức

- [Java SE 21 — `FileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): hợp đồng đa luồng, current position, positional read/write, giới hạn `APPEND`, file lock.
- [Java SE 21 — `RandomAccessFile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/RandomAccessFile.html): `seek`, `getFilePointer` và quan hệ vị trí với `getChannel()`.
- [Java SE 21 — `FileLock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): file locking theo OS, không phù hợp để đồng bộ các thread cùng JVM.
- [Java SE 21 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): vị trí, giới hạn và cách dùng buffer cho I/O.

Điểm cần nhớ xuyên suốt: **quản lý pointer là quản lý trạng thái chia sẻ**. Chọn offset tuyệt đối nếu tác vụ độc lập; nếu workflow bắt buộc dựa vào pointer chung, hãy đồng bộ toàn bộ hành động có ý nghĩa nghiệp vụ, đồng thời bảo vệ dữ liệu khi nhiều thao tác có thể chồng vùng.