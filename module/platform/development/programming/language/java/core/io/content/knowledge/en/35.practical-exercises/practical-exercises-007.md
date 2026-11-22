# So sánh RandomAccessFile với FileChannel trên bản ghi cố định

## 1. Bài toán thực hành và mục tiêu

Giả sử một chương trình Java lưu nhiều bản ghi tài khoản trong một tệp nhị phân. Mỗi bản ghi có đúng **16 byte**, nên ta biết ngay vị trí của bản ghi thứ `i` mà không phải đọc mọi bản ghi đứng trước. Chương trình cần:

- Tạo tệp chứa một số bản ghi theo cùng một layout.
- Đọc một bản ghi bất kỳ theo chỉ số.
- Sửa giá trị trong một bản ghi mà không phải viết lại toàn bộ tệp.
- Phát hiện chỉ số sai, EOF và bản ghi cuối bị thiếu byte.
- So sánh hai cách thao tác: **`RandomAccessFile`** và **`FileChannel`** với **`ByteBuffer`**.
- Hiểu khác biệt giữa **file pointer** của `RandomAccessFile`, **position** của channel, và **position/limit** của buffer.
- Không tự suy ra phương án nào nhanh hơn khi chưa đo trên workload thật.

**Kết luận trước khi viết code:** cả hai API đều có thể thực hiện random access tới bản ghi có độ dài cố định. `RandomAccessFile` tiện với các phương thức đọc/ghi primitive và `seek()`; `FileChannel` tiện với positional read/write và các thao tác NIO. **Cùng đọc đúng 16 byte ở cùng offset** mới là tiền đề của một phép so sánh hợp lệ.

Bài dùng **Java 17+**, chỉ sử dụng Java SE. Mọi ví dụ chạy độc lập sẽ có tên tệp/class tương ứng, lệnh `javac`/`java` và stdout không phụ thuộc đường dẫn tệp tạm.

## 2. Bản ghi cố định là gì?

Một **fixed-length record** là một bản ghi mà số byte và thứ tự trường được định nghĩa trước; mọi bản ghi của cùng phiên bản định dạng có cùng chiều dài.

Trong bài này, một bản ghi gồm:

| Offset trong bản ghi | Trường | Kiểu nhị phân | Số byte |
| --- | --- | --- | --- |
| 0–3 | `id` | `int` signed 32-bit | 4 |
| 4–11 | `balance` | `long` signed 64-bit | 8 |
| 12–15 | `status` | `int` signed 32-bit | 4 |
| **Tổng** | | | **16 byte** |

Cả hai cách ghi đều dùng **big-endian**: byte có trọng số cao nhất xuất hiện trước. `RandomAccessFile.writeInt/writeLong` dùng big-endian theo hợp đồng `DataOutput`; `ByteBuffer` có default order là `BIG_ENDIAN` nhưng nên thiết lập tường minh để tránh lỗi khi code được refactor.

Ví dụ bản ghi `id=1002`, `balance=7250`, `status=1` có các nhóm byte:

```text
Offset:     0          4                     12
            |          |                      |
Field:      id:int     balance:long           status:int
Bytes:      00 00 03 EA  00 00 00 00 00 00 1C 52  00 00 00 01
Size:       < 4 bytes > <      8 bytes      > < 4 bytes >
```

Vì `1002 = 0x000003EA` và `7250 = 0x0000000000001C52`, hai API phải diễn giải chính xác cùng byte nếu dùng cùng layout và byte order.

**Không phải Java object serialization:** một tệp fixed-record chứa các byte do ứng dụng quy định. Nó không dùng `ObjectOutputStream`, không mang class descriptor và không khôi phục object graph tự động. Chương trình tự chịu trách nhiệm về schema và tính tương thích phiên bản.

## 3. Công thức xác định offset

Gọi:

- `R`: số byte mỗi bản ghi (ở đây `R=16`).
- `i`: chỉ số bản ghi bắt đầu từ **0**.
- `base`: vị trí bắt đầu vùng dữ liệu, bằng 0 khi file không có header.
- `offset`: vị trí byte đầu tiên của bản ghi trong file.

Công thức:

\[
\text{offset}(i)=\text{base}+i\times R
\]

Với `base=0`:

| Record index | Byte offset | Vùng byte của bản ghi |
| --- | --- | --- |
| 0 | 0 | 0–15 |
| 1 | 16 | 16–31 |
| 2 | 32 | 32–47 |
| 3 | 48 | 48–63 |

Tệp gồm ba bản ghi chính xác phải dài `3 × 16 = 48` byte. Nếu tệp dài 50 byte, hai byte cuối không tạo thành bản ghi hợp lệ; đó là tình huống **partial/truncated/corrupt record**, không phải một bản ghi thứ tư.

### Tránh overflow khi tính offset

Không dùng:

```java
long offset = index * RECORD_BYTES;
```

nếu cả `index` và `RECORD_BYTES` là `int`: phép nhân được thực hiện trong `int` **trước khi gán sang `long`**, nên có thể overflow. Cũng phải kiểm tra chỉ số âm và phép nhân `long` quá lớn.

Dùng:

```java
static long offsetOf(long index, int recordBytes) {
    if (index < 0 || recordBytes <= 0) {
        throw new IllegalArgumentException("Invalid index/size");
    }
    return Math.multiplyExact(index, (long) recordBytes);
}
```

Đây là **đoạn helper minh họa**; `Math.multiplyExact` ném `ArithmeticException` nếu phép nhân không biểu diễn được trong `long`. Với file có header, cần thêm `base` bằng `Math.addExact(base, product)`.

Công thức offset chỉ hợp lệ nếu **mọi bản ghi thực sự có đúng R byte**. Không thể áp dụng trực tiếp nếu bạn chèn chuỗi UTF-8 độ dài thay đổi, metadata tùy ý hoặc marker không cố định vào giữa các record.

## 4. RandomAccessFile: con trỏ đọc/ghi duy nhất

`java.io.RandomAccessFile` cung cấp API đọc/ghi dữ liệu ở những vị trí tùy chọn trên file. Một số phương thức cốt lõi:

```java
RandomAccessFile file = new RandomAccessFile(path.toFile(), "rw");
file.seek(byteOffset);
long position = file.getFilePointer();
int id = file.readInt();
long amount = file.readLong();
file.writeInt(newStatus);
long size = file.length();
```

Đây là đoạn minh họa: cần khai báo `path` và `byteOffset`, xử lý `IOException` và đóng tài nguyên.

**`seek(long pos)`** đặt file pointer tới một byte offset **tuyệt đối tính từ đầu tệp**, không phải chỉ số bản ghi. Sau đó các phương thức đọc/ghi tiếp tục tại file pointer hiện tại:

- `readInt()` đọc đúng 4 byte, trả `int` và tăng file pointer 4.
- `readLong()` đọc đúng 8 byte, trả `long` và tăng file pointer 8.
- `writeInt(x)` ghi 4 byte và tăng file pointer 4.
- `writeLong(x)` ghi 8 byte và tăng file pointer 8.
- `readFully(byte[])` cố đọc đủ byte của mảng, ném `EOFException` nếu gặp EOF trước khi đủ.
- `length()` lấy kích thước tệp theo byte.
- `setLength(newLength)` thay đổi chiều dài tệp, cần xem xét truncate/extend.

Ví dụ đọc bản ghi `i=1`:

```java
file.seek(1L * 16);
int id = file.readInt();       // Pointer: 20
long balance = file.readLong();// Pointer: 28
int status = file.readInt();   // Pointer: 32
```

**File pointer đã bị thay đổi.** Nếu method khác gọi `file.readInt()` ngay sau đó mà không `seek`, nó đọc từ offset 32, tức đầu bản ghi tiếp theo, không tự quay về offset 16.

Điểm mạnh là code đọc primitive ngắn gọn. Điểm cần quản lý là **trạng thái vị trí đọc/ghi chung trong cùng một `RandomAccessFile`**.

### Chế độ mở

| Mode | Ý nghĩa |
| --- | --- |
| `"r"` | Chỉ đọc, không cho phép ghi |
| `"rw"` | Đọc và ghi |
| `"rws"` | Đọc/ghi, yêu cầu đồng bộ dữ liệu và metadata theo hợp đồng |
| `"rwd"` | Đọc/ghi, yêu cầu đồng bộ nội dung file theo hợp đồng, có khác biệt so với `"rws"` về metadata |

Các mode có đồng bộ cao hơn có thể làm chi phí ghi khác đi đáng kể; **không dùng `"rws"` để benchmark đối đầu với FileChannel không force**, vì đó là hai mức bảo đảm dữ liệu không tương đương.

## 5. FileChannel: positional read/write với ByteBuffer

`java.nio.channels.FileChannel` cũng có thể đọc/ghi theo offset tùy ý:

```java
int read(ByteBuffer dst, long position) throws IOException;
int write(ByteBuffer src, long position) throws IOException;
```

Hai overload này có tính chất quan trọng:

1. `position` là **byte offset tuyệt đối** trên file, không phải index bản ghi.
2. `read(dst, position)` không làm thay đổi `channel.position()`.
3. `write(src, position)` không làm thay đổi `channel.position()`.
4. **`ByteBuffer.position()` vẫn thay đổi** theo số byte đọc/ghi thực tế.
5. Một lời gọi có thể trả **ít byte hơn yêu cầu**; phải loop cho đến khi đủ hoặc nhận EOF/lỗi.
6. `FileChannel` cho phép quản lý chiều dài bằng `size()`/`truncate(...)` và các thao tác NIO khác.

Ví dụ ý tưởng:

```java
ByteBuffer buffer = ByteBuffer.allocate(16);
buffer.order(ByteOrder.BIG_ENDIAN);

long offset = 1L * 16;
int received = channel.read(buffer, offset);

// channel.position() giữ nguyên;
// buffer.position() có thể tăng theo số byte received.
```

Đoạn này chỉ minh họa, chưa phải chương trình độc lập; `channel` cần được mở và `received` phải được kiểm tra. Không được gọi ngay `buffer.getInt()` khi buffer còn ở pha ghi sau `read` mà chưa `flip()`/quản lý vị trí phù hợp.

### Buffer position khác channel position

| Thành phần | `RandomAccessFile` | `FileChannel` positional overload |
| --- | --- | --- |
| Vị trí I/O | `getFilePointer()`; thay đổi qua `seek/read/write` | Offset truyền trực tiếp trong mỗi lời gọi |
| Position nội tại | File pointer thay đổi | `channel.position()` **không đổi** khi dùng overload offset |
| Buffer trung gian | Có thể dùng primitive methods | `ByteBuffer` với `position/limit/capacity` |
| Đọc primitive | `readInt()/readLong()` tự tiến con trỏ | `ByteBuffer.getInt()/getLong()` tiến buffer position |
| Partial read | `readInt`/`readLong` đòi đủ số byte, nếu thiếu ném EOFException | `read(ByteBuffer,offset)` có thể trả số byte nhỏ; ứng dụng tự loop |
| Byte order | Các primitive DataInput/DataOutput theo big-endian | Cấu hình `buffer.order(...)` tường minh |

**Sai lầm hay gặp:** nghe “positional I/O không đổi position” rồi tưởng cả `ByteBuffer.position()` cũng không đổi. Thực tế chỉ vị trí nội tại của **FileChannel** được giữ; buffer vẫn được tiêu thụ/điền dữ liệu.

## 6. Vòng đời ByteBuffer: clear, flip, get/put

Để mã hóa một bản ghi 16 byte:

```java
ByteBuffer bytes = ByteBuffer.allocate(16);
bytes.order(ByteOrder.BIG_ENDIAN);
bytes.putInt(1002);
bytes.putLong(7250L);
bytes.putInt(1);
bytes.flip();
```

Trước `flip()`, buffer đã có:

```text
position = 16
limit    = 16
capacity = 16
```

Sau `flip()`:

```text
position = 0
limit    = 16
capacity = 16
```

Lúc này `channel.write(bytes, offset)` lấy dữ liệu từ vùng `[position, limit)`. Sau mỗi lần ghi, `bytes.position` tăng tương ứng. Muốn gửi tiếp phần còn lại, **không gọi `clear()`**, vì `clear` có thể làm cho chương trình gửi lại byte cũ chưa đúng phạm vi.

Khi đọc:

```java
ByteBuffer bytes = ByteBuffer.allocate(16);
bytes.order(ByteOrder.BIG_ENDIAN);

// Lặp channel.read(bytes, ...) đến khi buffer đầy.
bytes.flip();
int id = bytes.getInt();
long balance = bytes.getLong();
int status = bytes.getInt();
```

Đoạn này chưa đủ độc lập vì thiếu phần đọc/lỗi và `channel`. `flip()` sau khi nhận đủ 16 byte chuẩn bị cho các phương thức `get`. Ba lần get tiêu thụ đúng 4+8+4=16 byte.

`ByteBuffer.clear()` **không xóa vật lý byte** trong backing array; nó chỉ thay position/limit. Nếu buffer được dùng lại cho dữ liệu nhạy cảm, cần chính sách làm sạch riêng, không coi `clear` là thao tác bảo mật.

## 7. Bảng so sánh trực tiếp

| Tiêu chí | `RandomAccessFile` | `FileChannel` |
| --- | --- | --- |
| Package | `java.io` | `java.nio.channels` |
| Mở tệp | `new RandomAccessFile(file, "r"/"rw")` | `FileChannel.open(path, StandardOpenOption...)` |
| Truy cập offset | `seek(offset)` | `read/write(buffer, offset)` |
| Thao tác I/O tiến vị trí đối tượng | Có, sau `seek/read/write` | Positional overload **không đổi** `channel.position` |
| Đọc/ghi số nguyên | `readInt/readLong/writeInt/writeLong` | `ByteBuffer.putInt/getInt` và `putLong/getLong` |
| Big-endian | Cố định cho primitive DataInput/Output | Cấu hình buffer, default BIG_ENDIAN |
| Khối lượng code cho record nhỏ | Thường ít | Nhiều thao tác buffer và vòng partial I/O |
| Buffer reuse/direct buffer | Không phải mô hình chính của API | Có thể tái sử dụng heap/direct `ByteBuffer` |
| Truy cập theo vị trí trong nhiều tác vụ | Phải quản lý file pointer, đồng bộ nếu dùng chung đối tượng | Có overload offset không dùng position chung; vẫn cần đồng bộ dữ liệu |
| Quản lý độ dài | `length/setLength` | `size/truncate` |
| File lock, transfer, mapping | Có `getChannel()` để dùng NIO | Cung cấp trực tiếp các phương thức NIO |
| Dữ liệu được cập nhật nguyên tử cả record? | Không bảo đảm | Không bảo đảm |
| Hiệu năng tuyệt đối | Phụ thuộc workload | Phụ thuộc workload |

**Không phải hai thế giới tách rời:** `RandomAccessFile.getChannel()` trả về một `FileChannel` gắn với chính file đó. Theo hợp đồng API, file pointer của `RandomAccessFile` và **position của channel trả về từ `getChannel()` được liên kết**. Vì thế nếu trộn `raf.seek`, `raf.readInt` và các phương thức channel **không positional**, một thao tác có thể ảnh hưởng vị trí mà thao tác tiếp theo của bên kia nhìn thấy.

Overload `channel.read(buffer, absoluteOffset)` vẫn không đổi position nội tại của channel; tuy nhiên chia sẻ stream và update record cần hiểu rõ ownership và concurrency. Ví dụ chính dưới đây mở **hai file riêng biệt** bằng hai API để so sánh kết quả byte một cách công bằng và tránh can thiệp file pointer ngoài ý muốn.

## 8. Ví dụ hoàn chỉnh Java 17: cùng layout, cùng thao tác, kết quả byte giống nhau

Ví dụ tự tạo một thư mục tạm và hai file chứa cùng ba bản ghi 16 byte. File thứ nhất được tạo/đọc/cập nhật **chỉ bằng RandomAccessFile**; file thứ hai được tạo/đọc/cập nhật **chỉ bằng FileChannel positional I/O**.

Chuỗi thực hiện:

1. Ghi ba bản ghi:
   - `(1001, 5000, 1)`.
   - `(1002, 7250, 1)`.
   - `(1003, 9000, 0)`.
2. Đọc record `index=1` ở offset 16 bằng hai API.
3. Đặt `channel.position(7)` để chứng minh positional I/O không làm đổi giá trị ấy.
4. Thay balance của record `index=1` thành `7777` bằng cả hai API.
5. Quan sát `raf.getFilePointer()==32` và `channel.position()==7`.
6. Đọc lại bản ghi đã sửa, so sánh nội dung toàn file qua `Files.mismatch`.

### Tệp `FixedRecordComparisonDemo.java`

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FixedRecordComparisonDemo {
    static final int RECORD_BYTES = Integer.BYTES
            + Long.BYTES + Integer.BYTES; // 16

    record Entry(int id, long balance, int status) { }

    static long offset(long index) {
        if (index < 0) {
            throw new IllegalArgumentException("Negative record index");
        }
        return Math.multiplyExact(index, (long) RECORD_BYTES);
    }

    static void requireReadable(long offset, long size)
            throws IOException {
        if (size % RECORD_BYTES != 0) {
            throw new IOException("Misaligned record file");
        }
        if (offset > size - RECORD_BYTES) {
            throw new EOFException("Record is outside the file");
        }
    }

    static void requireWritable(long offset, long size)
            throws IOException {
        if (size % RECORD_BYTES != 0 || offset > size) {
            throw new IOException("Invalid write position");
        }
    }

    static void writeRaf(RandomAccessFile file, long index, Entry e)
            throws IOException {
        long pos = offset(index);
        requireWritable(pos, file.length());
        file.seek(pos);
        file.writeInt(e.id());
        file.writeLong(e.balance());
        file.writeInt(e.status());
    }

    static Entry readRaf(RandomAccessFile file, long index)
            throws IOException {
        long pos = offset(index);
        requireReadable(pos, file.length());
        file.seek(pos);
        int id = file.readInt();
        long balance = file.readLong();
        int status = file.readInt();
        return new Entry(id, balance, status);
    }

    static void writeChannel(FileChannel channel, long index, Entry e)
            throws IOException {
        long pos = offset(index);
        requireWritable(pos, channel.size());

        ByteBuffer bytes = ByteBuffer.allocate(RECORD_BYTES);
        bytes.order(ByteOrder.BIG_ENDIAN);
        bytes.putInt(e.id());
        bytes.putLong(e.balance());
        bytes.putInt(e.status());
        bytes.flip();

        int written = 0;
        while (bytes.hasRemaining()) {
            int n = channel.write(bytes, pos + written);
            if (n <= 0) {
                throw new IOException("Channel write made no progress");
            }
            written += n;
        }
    }

    static Entry readChannel(FileChannel channel, long index)
            throws IOException {
        long pos = offset(index);
        requireReadable(pos, channel.size());

        ByteBuffer bytes = ByteBuffer.allocate(RECORD_BYTES);
        bytes.order(ByteOrder.BIG_ENDIAN);

        int received = 0;
        while (bytes.hasRemaining()) {
            int n = channel.read(bytes, pos + received);
            if (n == -1) {
                throw new EOFException("Incomplete record");
            }
            if (n == 0) {
                throw new IOException("Channel read made no progress");
            }
            received += n;
        }

        bytes.flip();
        return new Entry(
                bytes.getInt(), bytes.getLong(), bytes.getInt());
    }

    static String describe(Entry e) {
        return "id=" + e.id() + ", balance=" + e.balance()
                + ", status=" + e.status();
    }

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("records-");
        Path rafPath = folder.resolve("raf.bin");
        Path channelPath = folder.resolve("channel.bin");

        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(rafPath.toFile(), "rw");
                 FileChannel channel = FileChannel.open(
                         channelPath,
                         StandardOpenOption.CREATE,
                         StandardOpenOption.READ,
                         StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {

                Entry[] initial = {
                        new Entry(1001, 5000L, 1),
                        new Entry(1002, 7250L, 1),
                        new Entry(1003, 9000L, 0)
                };

                for (int i = 0; i < initial.length; i++) {
                    writeRaf(raf, i, initial[i]);
                    writeChannel(channel, i, initial[i]);
                }

                System.out.println("Record bytes: " + RECORD_BYTES);
                System.out.println("Before RAF: "
                        + describe(readRaf(raf, 1)));

                channel.position(7);
                System.out.println("Before FileChannel: "
                        + describe(readChannel(channel, 1)));

                Entry updated = new Entry(1002, 7777L, 1);
                writeRaf(raf, 1, updated);
                writeChannel(channel, 1, updated);

                System.out.println("RAF pointer after update: "
                        + raf.getFilePointer());
                System.out.println("FileChannel position after update: "
                        + channel.position());

                System.out.println("After RAF: "
                        + describe(readRaf(raf, 1)));
                System.out.println("After FileChannel: "
                        + describe(readChannel(channel, 1)));
            }

            System.out.println("Byte identical: "
                    + (Files.mismatch(rafPath, channelPath) == -1));
            System.out.println("File bytes: " + Files.size(rafPath));
        } finally {
            Files.deleteIfExists(channelPath);
            Files.deleteIfExists(rafPath);
            Files.deleteIfExists(folder);
        }
    }
}
```

### Biên dịch và chạy

```bash
javac FixedRecordComparisonDemo.java
java FixedRecordComparisonDemo
```

**Stdout khi các thao tác file hoàn tất thành công:**

```text
Record bytes: 16
Before RAF: id=1002, balance=7250, status=1
Before FileChannel: id=1002, balance=7250, status=1
RAF pointer after update: 32
FileChannel position after update: 7
After RAF: id=1002, balance=7777, status=1
After FileChannel: id=1002, balance=7777, status=1
Byte identical: true
File bytes: 48
```

### Phân tích những điểm cần nắm

**Thứ nhất — layout giống nhau.** `RandomAccessFile.writeInt/writeLong` và `ByteBuffer.putInt/putLong` với `BIG_ENDIAN` tạo cùng thứ tự 16 byte, nên `Files.mismatch(...) == -1` khi hai file có cùng trạng thái cuối.

**Thứ hai — offset tính theo byte.** Record 1 bắt đầu ở offset `1*16=16`. Đọc bản ghi index 1 không có nghĩa gọi `seek(1)` hoặc `read(buffer,1)`.

**Thứ ba — pointer khác nhau.** `writeRaf(raf,1,...)` gọi `seek(16)` rồi ghi 16 byte, nên `raf.getFilePointer()==32`. Ngược lại, `writeChannel(channel,1,...)` chỉ dùng overload có offset, nên `channel.position()` giữ nguyên **7**.

**Thứ tư — partial I/O.** `FileChannel.read/write` trả về số byte thực truyền. Ví dụ theo dõi `received`/`written` để tự tăng file offset và không bỏ mất phần còn lại. Nếu channel trả 0 khi cần tiến triển, ví dụ báo lỗi thay vì quay CPU vô hạn.

**Thứ năm — kiểm tra kích thước trước khi truy cập.** `requireReadable` kiểm tra file có số byte chia hết cho 16 và index còn trong vùng. `requireWritable` chỉ cho phép ghi đè record có sẵn hoặc append đúng cuối file, không vô tình tạo khoảng trống nếu offset nằm ngoài file.

**Thứ sáu — kiểm chứng chức năng khác benchmark.** Ví dụ kiểm tra ba cách phản ánh cùng nội dung, **không đo thời gian** và không chứng minh cách nào nhanh hơn.

### Vì sao FileChannel dùng positional overload?

Nếu dùng `channel.position(offset); channel.read(buffer);`, code vẫn có thể đúng nhưng nó thay đổi channel position chung. Trong ví dụ này, positional overload thể hiện rõ hợp đồng **đọc/ghi ở offset chỉ định mà không thay đổi vị trí hiện tại của channel**. Nó tiện khi các thao tác cần nhảy giữa các record bất kỳ, đặc biệt nếu không muốn thao tác này làm lệch vị trí tuần tự của thao tác khác.

Vẫn cần chú ý đồng bộ hóa cập nhật dữ liệu, vì “không đổi channel position” **không có nghĩa** đọc và sửa nhiều field của một record trở thành transaction nguyên tử.

## 9. Một chương trình khác: phát hiện file chứa bản ghi dở dang

Một lỗi thường gặp là file kết thúc **giữa** bản ghi. Ví dụ đã định nghĩa record 16 byte nhưng file dài 31 byte: có một record hoàn chỉnh và 15 byte của record thứ hai, không phải hai record đầy đủ.

Chương trình dưới đây tạo file 32 byte, xác nhận đọc được record index 1, từ chối index 2 và một index quá lớn, sau đó thu ngắn file còn 31 byte. Nó dùng cả `RandomAccessFile.length()` lẫn `FileChannel.size()` để chỉ ra hai API cùng nhìn thấy kích thước file thực.

### Tệp `FixedRecordValidationDemo.java`

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FixedRecordValidationDemo {
    private static final int RECORD_BYTES = 16;

    static long checkedOffset(long index, long fileSize)
            throws IOException {
        if (fileSize < 0 || fileSize % RECORD_BYTES != 0) {
            throw new IOException("Misaligned file");
        }
        if (index < 0) {
            throw new IOException("Negative record index");
        }

        long offset;
        try {
            offset = Math.multiplyExact(index, (long) RECORD_BYTES);
        } catch (ArithmeticException ex) {
            throw new IOException("Record offset overflow", ex);
        }

        if (offset > fileSize - RECORD_BYTES) {
            throw new EOFException("Record out of range");
        }
        return offset;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("validate-records-", ".bin");

        try {
            Files.write(file, new byte[32]);

            try (RandomAccessFile raf =
                         new RandomAccessFile(file.toFile(), "rw");
                 FileChannel channel = FileChannel.open(
                         file, StandardOpenOption.READ)) {

                System.out.println("RAF length: " + raf.length());
                System.out.println("Channel size: " + channel.size());

                System.out.println("Record 1 offset: "
                        + checkedOffset(1, raf.length()));

                try {
                    checkedOffset(2, channel.size());
                } catch (EOFException ex) {
                    System.out.println("Out of range: "
                            + ex.getClass().getSimpleName());
                }

                try {
                    checkedOffset(Long.MAX_VALUE, channel.size());
                } catch (IOException ex) {
                    System.out.println("Huge index: " + ex.getMessage());
                }

                raf.setLength(31);
                System.out.println("Aligned after truncate: "
                        + (channel.size() % RECORD_BYTES == 0));

                try {
                    checkedOffset(0, channel.size());
                } catch (IOException ex) {
                    System.out.println("Truncated record: "
                            + ex.getMessage());
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac FixedRecordValidationDemo.java
java FixedRecordValidationDemo
```

**Stdout khi I/O thành công:**

```text
RAF length: 32
Channel size: 32
Record 1 offset: 16
Out of range: EOFException
Huge index: Record offset overflow
Aligned after truncate: false
Truncated record: Misaligned file
```

**Vì sao thứ tự kiểm tra quan trọng?** Với `index=Long.MAX_VALUE`, phép nhân `index*16` không thể biểu diễn bằng `long`. `Math.multiplyExact` phát hiện lỗi trước khi chương trình đưa offset âm hoặc tràn vào `seek`/`read`. Với file 31 byte, phép `size % 16 != 0` phát hiện layout hỏng trước khi đọc, thay vì diễn giải 15 byte dở dang như dữ liệu hợp lệ.

Bài học: **fixed-length** không tự làm file luôn hợp lệ. File có thể bị cắt do crash, ghi dở, thao tác truncate, format không tương thích hoặc hỏng dữ liệu. Phải kiểm tra cấu trúc trước khi truy cập và có chiến lược phục hồi/chặn sử dụng file bất thường.

## 10. Đọc một record: EOF và partial read

**`RandomAccessFile.readInt/readLong`** cố lấy đủ số byte cho primitive tương ứng. Nếu không đủ do EOF, nó ném `EOFException`. Tuy nhiên, thành công sau khi đọc một trường **không chứng minh toàn bộ record hợp lệ**: có thể đọc được `id` nhưng thiếu vài byte của `balance` hoặc `status`.

Với **`FileChannel.read(ByteBuffer,long)`**, kết quả có thể là:

| Kết quả | Ý nghĩa |
| --- | --- |
| `n > 0` | Đã đọc `n` byte, buffer position tăng `n` |
| `n == 0` | Lời gọi hiện tại không đọc được byte; có thể liên quan buffer, trạng thái I/O hoặc điều kiện tiến triển |
| `n == -1` | Gặp EOF |

Đừng gọi một lần `read(buffer,offset)` rồi giả định buffer 16 byte đã đầy. Vòng lặp đúng:

```java
int total = 0;

while (buffer.hasRemaining()) {
    int n = channel.read(buffer, recordOffset + total);

    if (n == -1) {
        throw new EOFException("Incomplete fixed record");
    }
    if (n == 0) {
        throw new IOException("No progress");
    }
    total += n;
}

buffer.flip();
// Giải mã từ buffer.
```

Đoạn mã minh họa này cần `channel`, `recordOffset`, `buffer`, import và cơ chế đóng. Khi I/O xảy ra trên file **đang bị ghi/truncate đồng thời**, kiểm tra size ban đầu không loại bỏ race — vẫn cần xử lý EOF hoặc lỗi khác khi đọc.

**Không dùng `available()` để tính số byte còn lại của một RandomAccessFile:** `RandomAccessFile` không dùng API `InputStream.available()` cho hợp đồng này. Dùng `length` và `getFilePointer` hoặc kiểm tra theo frame/layout, nhưng vẫn có thể gặp thay đổi do tiến trình khác.

## 11. Ghi một record: partial write, append và holes

### Với RandomAccessFile

`seek(offset)` sau đó `writeInt/writeLong/writeInt` ghi các primitive theo thứ tự. Nếu ghi thất bại giữa chừng, file có thể bị **cập nhật một phần**, ví dụ `id` đã đổi nhưng `balance` chưa đổi. Cần xử lý kết quả nghiệp vụ như thất bại, không mặc định toàn record đã được cập nhật.

### Với FileChannel

`write(buffer,offset)` có thể ghi ít hơn số byte `remaining`. Vì vậy cần:

```java
int sent = 0;
while (buffer.hasRemaining()) {
    int n = channel.write(buffer, recordOffset + sent);
    if (n <= 0) {
        throw new IOException("Partial write made no progress");
    }
    sent += n;
}
```

Hai cách đều có thể viết tới offset lớn hơn kích thước file. **Ghi vượt EOF có thể mở rộng file và tạo một khoảng trống**; nội dung khoảng trống phụ thuộc file system/API và không nên được coi là một vùng record hợp lệ tự động. Nếu ứng dụng chỉ cho append hoặc update, cần quy tắc:

- **Update:** `0 <= index < recordCount` và size phải chia hết `RECORD_BYTES`.
- **Append:** `index == recordCount` và chỉ ghi một record hoàn chỉnh.
- **Không cho phép:** `index > recordCount` nếu không có quy trình cấp phát/khởi tạo các record trung gian.

Ví dụ chính chọn `offset <= fileSize` cho write; nếu file size là bội số 16, điều đó cho phép update hoặc append mà không tạo hole.

**Chú ý:** hai thao tác đồng thời có thể cùng thấy kích thước ban đầu rồi đều cố append tại cùng offset. Cần đồng bộ hóa/lock hoặc một cơ chế cấp offset nguyên tử theo kiến trúc ứng dụng. Một hàm kiểm tra size đơn lẻ **không** bảo đảm tính an toàn concurrent.

## 12. Vị trí chia sẻ khi dùng `RandomAccessFile.getChannel()`

`RandomAccessFile.getChannel()` tạo/trả channel liên kết với cùng file. Theo hợp đồng:

- `raf.getFilePointer()` và `raf.getChannel().position()` biểu diễn vị trí chung cho thao tác tuần tự.
- `raf.seek(100)` ảnh hưởng position của channel liên kết.
- `channel.position(200)` ảnh hưởng file pointer của RAF.
- `raf.readInt()` sẽ tiến con trỏ tương ứng, channel thấy vị trí mới.
- `channel.read(buffer, absoluteOffset)` là positional operation, nên không làm đổi channel position; vì vậy không làm đổi shared pointer do chính positional call.
- Thay chiều dài tệp qua một interface cũng được phản ánh qua interface khác.

Ví dụ minh họa:

```java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    FileChannel linked = raf.getChannel();

    raf.seek(8);
    System.out.println(linked.position()); // 8

    linked.position(16);
    System.out.println(raf.getFilePointer()); // 16
}
```

Đây là đoạn minh họa chứ không phải chương trình độc lập, vì `file` chưa được khai báo và thiếu import. Không đồng thời đóng `linked` và tiếp tục dùng `raf` rồi kỳ vọng file vẫn mở: channel/RAF liên kết cùng tài nguyên. Khi một bên bị đóng, các thao tác còn lại có thể không dùng được.

**Điểm dễ sai trong multithreading:** thread A gọi `raf.seek(offsetA)`, thread B gọi `raf.seek(offsetB)`, rồi thread A `raf.readInt()` có thể đọc nhầm offset nếu không đồng bộ toàn bộ chuỗi seek+read. Positional FileChannel giúp **tránh cạnh tranh về position** của channel, nhưng **không** tự ngăn nhiều thread cập nhật chồng lên cùng 16 byte hoặc đảm bảo snapshot nhất quán.

## 13. Vấn đề byte order và tính tương thích định dạng

### Primitive methods của RAF

`RandomAccessFile` triển khai `DataInput` và `DataOutput`, theo đó `writeInt`, `writeLong`, `readInt` và `readLong` dùng big-endian cho byte nhiều byte. Nó không có một `order(LITTLE_ENDIAN)` tương đương trực tiếp với `ByteBuffer.order`.

### ByteBuffer của FileChannel

`ByteBuffer` dùng big-endian mặc định khi mới tạo, nhưng có thể cấu hình:

```java
ByteBuffer buffer = ByteBuffer.allocate(16)
        .order(ByteOrder.LITTLE_ENDIAN);
```

Nếu viết file little-endian bằng `ByteBuffer` rồi đọc primitive bằng RAF big-endian, số nguyên sẽ bị diễn giải sai. Phải **định nghĩa endian trong schema của file**, không để mặc định ngầm.

Với file dùng nhiều kiểu, đừng suy rằng có thể gọi `ByteBuffer.order(LITTLE_ENDIAN)` mà `RandomAccessFile.readInt()` tự thay đổi. Nếu muốn dùng RAF đọc little-endian, cần tự kết hợp byte hoặc dùng lớp hỗ trợ phù hợp.

### File format nên có version

Bản ghi cố định 16 byte trong ví dụ không có file header. Đối với ứng dụng thật, nên cân nhắc:

```text
Header:
  magic            4 bytes
  version          2 bytes
  record size      2 bytes
  record count     8 bytes (nếu cần)
Records:
  16 bytes * count
```

Khi thêm header, offset là `headerSize + index * recordSize`, phải tính bằng `long` và kiểm tra tràn. Những thông số trong header do file không tin cậy cung cấp cần được xác thực trước khi cấp phát buffer hoặc tính offset.

Nếu bản schema thay đổi từ 16 sang 24 byte, code cũ không thể đọc file mới bằng phép `i*16` và mong đúng. Tên API không tự bảo vệ bạn khỏi sai phiên bản định dạng.

## 14. Thêm tên hoặc chuỗi vào bản ghi cố định

Với `int/long`, chiều dài trường là hằng số. Với `String`, **số ký tự không phải số byte**:

- Chuỗi `"ABC"` trong UTF-8 dài 3 byte.
- Chuỗi tiếng Việt có dấu có thể dài nhiều byte hơn số ký tự hiển thị.
- Emoji có thể chiếm 4 byte UTF-8 nhưng 2 UTF-16 code units.

Nếu muốn mỗi tên chiếm chính xác 20 byte, phải xác định:

1. Charset, thường là UTF-8.
2. Chính sách nếu tên vượt 20 byte (từ chối hoặc cắt tại ranh giới ký tự, không tự cắt byte gây chuỗi sai).
3. Cách padding phần còn thiếu (ví dụ byte 0).
4. Cách xác định độ dài thực khi đọc (prefix length hoặc cắt trailing padding có kiểm soát).
5. Chính sách với NUL byte trong nội dung nếu dùng NUL làm marker.
6. Cách chuẩn hóa Unicode nếu hệ thống so sánh tên theo ký tự.

`RandomAccessFile.writeUTF()` **không phù hợp để tự động tạo field 20 byte cố định**, vì nó dùng *modified UTF-8* với prefix độ dài và số byte biến thiên. `ByteBuffer.put(text.getBytes(UTF_8))` cũng không tự làm trường cố định.

Trong bài này, record chỉ dùng số nguyên để cô lập phần quan trọng: **cùng 16 byte, cùng endian, cùng offset**.

## 15. Atomicity, lock và tính nhất quán

Một bản ghi 16 byte bao gồm nhiều field. Việc gọi ba `raf.write...` hoặc nhiều `FileChannel.write` không tạo transaction nguyên tử. Nếu chương trình crash giữa update, file có thể mang trạng thái hỗn hợp.

Các tình huống cần kiểm soát:

- Hai thread cập nhật cùng record.
- Một thread đọc record trong lúc thread khác đang ghi.
- Hai tiến trình cùng append vào cuối file.
- Tiến trình bị tắt đột ngột sau khi ghi một phần.
- File bị truncate hoặc đổi format bởi tiến trình khác.

**`FileLock`** (qua channel) có thể hỗ trợ phối hợp quyền truy cập, nhưng giới hạn/phạm vi và việc tuân thủ lock phụ thuộc hệ điều hành/file system/tiến trình; lock không biến nhiều lời ghi thành transaction chống crash. Không dùng “có khóa file” như lời hứa độ bền dữ liệu sau mất điện.

Các giải pháp tùy yêu cầu:

- Với một process đơn giản, đồng bộ hóa toàn bộ cập nhật record trong cùng critical section.
- Với nhiều process, dùng file locking và protocol nhất quán.
- Với update cần crash consistency, dùng write-ahead log/journal, hai bản sao record kèm version/checksum, hoặc transactional database.
- Với read cần snapshot, dùng version number và xác minh lại trước/sau đọc (kèm giao thức phù hợp).
- Với công việc thực tế mang tính giao dịch, cân nhắc dùng database thay vì tự xây engine record nhị phân.

**Positional I/O chỉ tránh thay đổi channel position. Nó không tự bảo đảm atomicity của record, isolation hay durability.**

## 16. Tính bền vững dữ liệu: khác biệt sync/force

Khi `write...` hoàn tất, dữ liệu đã được chuyển qua API theo hợp đồng I/O, nhưng **không mặc định đã nằm bền vững trên thiết bị lưu trữ** nếu ứng dụng/OS có cache.

Với RandomAccessFile:

- `"rw"` không giống `"rwd"`/`"rws"` về chính sách đồng bộ.
- `raf.getFD().sync()` hoặc chính sách cụ thể có thể dùng khi cần yêu cầu đồng bộ.
- `raf.getChannel().force(true)` là cách tương ứng ở NIO.

Với FileChannel:

```java
channel.force(true);
```

Đoạn này giả sử channel được mở có quyền phù hợp. `force(boolean metaData)` yêu cầu đẩy các cập nhật theo hợp đồng; `true` quan tâm cả metadata liên quan, còn `false` có thể chỉ tập trung nội dung tùy API. Các giới hạn với filesystem từ xa/thiết bị đặc biệt vẫn phải được xét.

**Không so benchmark `RandomAccessFile("rws")` với `FileChannel.open(..., WRITE)` không gọi `force` rồi tuyên bố FileChannel nhanh hơn.** Hai phương án đang yêu cầu mức đồng bộ khác nhau. Hãy định nghĩa cùng yêu cầu durability trước khi đo.

## 17. Hiệu năng: bản ghi nhỏ, random access và nhiều lượt truy cập

So sánh hai API về performance nên xét workload:

| Workload | RAF có thể có ưu thế | FileChannel có thể có ưu thế |
| --- | --- | --- |
| Đọc vài primitive từ một record | `readInt/readLong` ngắn gọn, ít lớp buffer do ứng dụng quản lý | Positional read giúp điều phối offset tường minh |
| Nhiều record liên tiếp | Đọc tuần tự bằng pointer, code đơn giản | Buffer reuse hoặc đọc theo block để giảm số lời gọi |
| Random read theo index | `seek` rồi đọc primitive | `read(buffer, absoluteOffset)` không cần thay channel position |
| Nhiều thread đọc vùng khác nhau | RAF dùng chung cần kiểm soát seek+read | Positional read không đụng position chung, nhưng vẫn bị giới hạn I/O thật |
| Cập nhật record cùng file | `seek + write...` dễ hiểu | `write(buffer, offset)` với buffer encode và retry partial |
| Ghi số lượng lớn | Có thể dùng API nhị phân trực tiếp | Buffer reuse, batching, scattering/gathering khi thích hợp |
| File cực lớn | Offset `long` cho phép seek rộng | `long` offset, size, transfer/mapping và nhiều lựa chọn |
| Dễ đọc/dễ kiểm chứng code | Primitive read/write rõ ràng | Có thêm position/limit/flip/order cần đúng |

**Không có kết luận tổng quát ai nhanh hơn.** FileChannel có thể cần nhiều mã ứng dụng hơn cho record 16 byte vì phải đóng gói primitive vào buffer. Ngược lại, nếu đọc nhiều record trong một block, `FileChannel` có thể giảm chi phí lời gọi cấp thấp so với từng lượt `RAF.readInt()`, tùy cách thiết kế.

Cả hai đều chịu ảnh hưởng bởi OS page cache, SSD/HDD, filesystem, JDK, độ dài file, pattern truy cập và concurrency. Với truy cập random nhiều record nhỏ, chi phí seek vật lý trên HDD có thể chi phối; với file trong page cache, overhead CPU và cách cấp phát buffer có thể nổi bật hơn.

## 18. Benchmark công bằng cho bài thực hành

Để đo tốc độ một cách có ý nghĩa, cần:

1. Tạo **cùng tập record**, cùng layout, cùng endianness và cùng kích thước file.
2. Có cùng số lượng thao tác và cùng mẫu index (sequential, uniform random, Zipf/hotspot...).
3. Với RAF, **không** so từng `readInt` trên mỗi field với FileChannel đọc một block 1 MiB rồi suy ra API nhanh hơn; đó là hai chiến lược batching khác nhau.
4. Với FileChannel, tránh cấp `ByteBuffer.allocate(16)` mỗi lần nếu mục đích đo throughput steady state; thử thêm buffer reuse.
5. Kiểm tra kết quả mỗi phương án giống nhau, không bỏ sót partial read/write.
6. Warmup JVM và chạy nhiều lượt, đảo thứ tự thử nghiệm.
7. Phân biệt **cold vs warm page cache**; thuật toán chạy sau có thể hưởng file đã được thuật toán trước làm nóng.
8. Báo môi trường: JDK, OS, filesystem, thiết bị, heap, buffer size, số records và threads.
9. Tách chi phí mở file, tạo buffer, encode/decode, thao tác I/O và kiểm tra kết quả nếu cần phân tích bottleneck.
10. Đo cả throughput, p50/p95 latency, allocation/GC và áp lực bộ nhớ thay vì chỉ milliseconds một lượt.

Một bộ benchmark mini có thể kiểm tra:
- 1.000 bản ghi và 1 triệu random reads lặp lại.
- 1 triệu bản ghi và random read không đều.
- 1 triệu bản ghi và scan tuần tự.
- 100.000 cập nhật record phân tán.
- 1 thread so với 4/16 thread; từng thread có handle/buffer riêng hoặc dùng shared channel với hợp đồng rõ.

**Đó chỉ là workload ví dụ, không phải số liệu đo có sẵn.** Nếu chạy trên SSD với file đã nằm trong cache, kết quả có thể khác hẳn mạng/NFS/HDD. Không công bố “NIO nhanh hơn 2 lần” chỉ từ một ví dụ 48 byte.

## 19. Nếu cần đọc nhiều record cùng lúc

Thiết kế ở ví dụ chính tạo một `ByteBuffer` 16 byte cho mỗi lần đọc. Đối với bài học, nó giúp phân tách rõ thao tác. Nhưng nếu ứng dụng scan hàng triệu records, nên cân nhắc **batching**:

- Một buffer chứa, chẳng hạn, `4096` record 16 byte = 65.536 byte.
- Đọc một khối lớn rồi lặp `getInt/getLong/getInt` để giải mã record trong RAM.
- Đặt lại buffer theo `clear/flip` khi chuyển block.
- Xử lý cuối file nếu khối trả về không tròn record.
- Giữ cùng byte order và ranh giới schema.
- Benchmark buffer heap/direct, kích thước block và số lượng record.

`RandomAccessFile` cũng có thể `readFully(byte[])` một khối lớn, rồi giải mã bằng `ByteBuffer.wrap(array).order(BIG_ENDIAN)` hoặc parser riêng. Vì vậy **batching không độc quyền của FileChannel**.

Một ví dụ tính toán:

```text
16 bytes/record * 4096 records = 65536 bytes
65536 bytes = 64 KiB
```

Với workload tuần tự, số lần đọc khối có thể ít hơn rất nhiều so với đọc một record/lần. Nhưng nếu ứng dụng thường chỉ cần một record ở offset ngẫu nhiên, đọc nguyên block 64 KiB mỗi lần có thể lãng phí I/O và băng thông cache.

## 20. Khi nào chọn RandomAccessFile?

`RandomAccessFile` là lựa chọn dễ hiểu khi:

- Bạn cần ví dụ nhập môn về file pointer/`seek`/primitive read/write.
- Schema chứa các giá trị nhị phân cố định, big-endian.
- Ứng dụng ít luồng, ít tranh chấp, cập nhật theo index đơn giản.
- Không cần thao tác NIO đặc biệt như `transferTo` hoặc mapped buffer.
- Muốn code ngắn, ít chi tiết `ByteBuffer.position/limit`.

Nhược điểm cần nhớ:

- `seek` và read/write sau nó tạo **một chuỗi thao tác phụ thuộc shared pointer**.
- Primitive big-endian cố định, không có `ByteOrder` của buffer.
- Một record gồm nhiều lệnh ghi có thể bị ghi dở.
- Khi cần song song hóa hoặc tích hợp pipeline buffer NIO, có thể phải quản lý thêm `getChannel` hoặc chuyển sang API khác.

Không nên loại bỏ RAF chỉ vì nó nằm trong package `java.io`. Trong một bài toán record đơn giản, nó có thể **dễ kiểm tra và bảo trì hơn**.

## 21. Khi nào chọn FileChannel?

`FileChannel` thường phù hợp khi:

- Cần positional I/O theo offset một cách rõ ràng, độc lập với channel position.
- Cần đọc/ghi theo `ByteBuffer` và điều phối với NIO API.
- Muốn tái sử dụng buffer để quét các record theo khối lớn.
- Cần `FileLock`, `force`, `transferTo/transferFrom` hoặc `map`.
- Thiết kế chia nhiều tác vụ theo offset mà không muốn từng tác vụ thay shared file position.

Nhược điểm cần nhớ:

- Phải quản lý `ByteBuffer.order` và trạng thái `position/limit/flip`.
- Đọc/ghi có thể partial; phải dùng vòng lặp theo `remaining`.
- Nếu tạo buffer mỗi record, có thể làm tăng allocation pressure.
- Nếu dùng `FileChannel.map`, lại có thêm chi phí và vấn đề vòng đời mapping; mapping **không tự mặc định nhanh hơn**.
- Positional read/write không giải quyết race khi nhiều thread cập nhật cùng record.

**Chọn FileChannel vì semantics/capabilities phù hợp, rồi tối ưu bằng đo đạc**, thay vì chọn chỉ vì tưởng NIO được bảo đảm nhanh.

## 22. Lỗi thường gặp trong bài tập

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `seek(index)` thay vì `seek(index*16)` | Đọc giữa record | Dùng byte offset có công thức |
| Dùng `int index*recordSize` rồi ép sang long | Integer overflow | `Math.multiplyExact(index, (long) recordSize)` |
| Không kiểm tra index âm | Offset không hợp lệ | Validate trước |
| Tưởng `getFilePointer()` luôn là index record | Sai đơn vị | Pointer tính bằng **byte** |
| Dùng `raf.readInt()` sau seek và tưởng pointer không đổi | Đọc sai lần kế tiếp | Rõ ràng vị trí trước mỗi record |
| Tưởng `FileChannel.read(buffer, offset)` luôn lấy đủ 16 byte | Record decode thiếu dữ liệu | Retry partial read đến đủ/EOF |
| Tưởng positional I/O không đổi `ByteBuffer.position()` | Buffer state bị xử lý sai | Phân biệt channel position và buffer position |
| Quên `flip()` trước khi write buffer sau `putInt` | Không còn `remaining` để ghi | `flip` sau encode |
| Quên `flip()` trước `getInt` sau read | Đọc sai pha | `flip` sau nhận đủ |
| RAF big-endian, channel little-endian | Giá trị số khác nhau | Cố định byte order |
| Dùng `writeUTF` làm trường chuỗi fixed-size | Trường có độ dài biến thiên | Tự định nghĩa field theo byte |
| Tệp dài không chia hết cho 16 | Record cuối bị cắt | Validate `size % 16` |
| Ghi offset ngoài EOF và tin record gap tự hợp lệ | Hole hoặc dữ liệu không xác định | Chỉ update/append ở offset hợp lệ |
| Cập nhật 16 byte và tin atomically | Torn record khi crash/race | Lock/protocol/journal tùy yêu cầu |
| Dùng chung RAF và channel rồi không hiểu shared position | Seek/read ảnh hưởng nhau | Ownership rõ hoặc positional overload |
| Quên đóng file | Rò rỉ descriptor | `try-with-resources` |
| So tốc độ khi cách ghi khác mức durability | Benchmark không tương đương | Cùng mode sync/force |
| Dùng `FileChannel.map` và tin sẽ luôn nhanh hơn | Page faults và cleanup có chi phí | Benchmark theo workload |
| Không kiểm tra checksum/kết quả khi benchmark | Đo phương án thiếu dữ liệu | Verify byte/record count |
| Đổi schema mà không version file | Mã cũ giải mã sai offset | Header/magic/version/record size |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Record dài 16 byte, chỉ số bắt đầu từ 0. Record số 25 bắt đầu ở offset bao nhiêu?

**Đáp án:** `25 × 16 = 400` byte. `seek(25)` là sai vì offset không phải record index.

**Câu 2.** `RandomAccessFile.seek(16)`, tiếp theo `readInt()`, `readLong()` và `readInt()`. Pointer ở đâu?

**Đáp án:** `16 + 4 + 8 + 4 = 32`. Đọc một record đủ 16 byte làm pointer chuyển tới đầu record kế tiếp.

**Câu 3.** `FileChannel.position()==7`. Gọi `channel.read(buffer, 16)` và đọc được 16 byte. `channel.position()` có thành 23 không?

**Đáp án:** **Không.** Với overload positional, channel position vẫn là 7; **buffer position** tăng theo 16 byte nhận được.

**Câu 4.** File dài 48 byte, record size 16. Đọc index 3 có hợp lệ không?

**Đáp án:** **Không.** File có 3 records, index hợp lệ là 0,1,2. Offset 48 là vị trí ngay sau EOF, không chứa 16 byte record mới.

**Câu 5.** Để append một record mới vào file hợp lệ dài 48 byte, bắt đầu ghi ở offset nào?

**Đáp án:** **48**. Khi ghi đủ 16 byte, kích thước file sẽ thành 64 byte. Nếu index là 4 (offset 64) khi file đang dài 48, ứng dụng có thể tạo hole; bài này từ chối thao tác ấy.

**Câu 6.** RAF ghi balance bằng `writeLong(7250L)`; ByteBuffer đặt `LITTLE_ENDIAN` để đọc bằng `getLong()`. Có được cùng số không?

**Đáp án:** Không được bảo đảm; thông thường sẽ **khác**. RAF ghi big-endian. Muốn cùng kết quả phải đọc với big-endian hoặc chủ động chuyển đổi.

**Câu 7.** Hai thread gọi `raf.seek` và `raf.readInt` trên cùng một RAF. Không có đồng bộ thì có nguy cơ gì?

**Đáp án:** Thread khác có thể thay đổi shared file pointer ở giữa các bước, làm đọc nhầm offset. Cần đồng bộ cả chuỗi hoặc thiết kế I/O theo offset không dùng chung con trỏ, đồng thời kiểm soát cập nhật dữ liệu.

**Câu 8.** Một file 32 byte bị truncate còn 31 byte. Có thể dùng `file.length()/16` rồi âm thầm bỏ 15 byte cuối không?

**Đáp án:** Đó là **cách làm mất dấu hiệu hỏng dữ liệu**. Với format fixed 16 byte, `length % 16 != 0` là tín hiệu bất thường cần báo/khôi phục theo chính sách, không tự coi file hợp lệ.

**Câu 9.** Tại sao chương trình so sánh hai file trả “Byte identical: true” nhưng không kết luận được hiệu năng?

**Đáp án:** Vì đây là **kiểm chứng correctness**. Không có phép đo latency/throughput, warmup, kiểm soát page cache hoặc số lượt chạy. Kết quả bằng byte chỉ chứng minh hai API đã thực hiện cùng thay đổi.

## 24. Checklist áp dụng cho hệ thống thực tế

Trước khi đọc/ghi:

- Định nghĩa record schema và version, mỗi field có offset/byte order/độ dài rõ.
- Xác thực index, phép tính offset và giới hạn `long`.
- Kiểm tra file size và `size % recordBytes == 0`.
- Xác định policy cho update, append và file corrupt.
- Chọn API theo nhu cầu: primitive `seek` hay positional buffer I/O.

Khi thực hiện:

- Với RAF: `seek` đúng offset, đọc/ghi đúng thứ tự, kiểm soát shared pointer.
- Với FileChannel: cấu hình ByteBuffer order, loop partial I/O, `flip` đúng pha, không nhầm buffer/channel position.
- Khi append hoặc update đồng thời: thiết kế khóa, thứ tự thao tác, retry và consistency.
- Nếu cần durability: xác định chính sách sync/force phù hợp trước khi benchmark.
- Khi file rất lớn: dùng buffer reuse/batching nếu workload cho phép, nhưng không giả định luôn nhanh.

Sau khi thực hiện:

- Kiểm tra kích thước, byte count, decoded fields và trường hợp EOF.
- Đóng stream/channel bằng `try-with-resources`.
- Có kế hoạch khôi phục torn record do crash hoặc ghi dở.
- Đo benchmark với input và điều kiện giống nhau trước khi quyết định tối ưu.
- Test ranh giới: file trống, một record, record cuối, index âm, index == recordCount, chỉ số tràn, record bị cắt, byte order sai, update đồng thời.

## 25. Tổng kết

**`RandomAccessFile` và `FileChannel` đều phù hợp để đọc/ghi bản ghi cố định theo offset.**

- `RandomAccessFile` dùng `seek(byteOffset)` và primitive `readInt/readLong/writeInt/writeLong`. Nó có **file pointer chung** và pointer tăng theo số byte I/O.
- `FileChannel` dùng `read/write(ByteBuffer, absoluteOffset)`. Positional overload giữ nguyên `channel.position()`, nhưng vẫn tiến `ByteBuffer.position()`; cần xử lý partial I/O, `flip` và byte order.
- Công thức offset `base + index * recordSize` phải dùng số học an toàn; phải kiểm tra EOF và kích thước file chia hết cho record size.
- Fixed-length record không tự cung cấp transaction, chống crash, concurrency safety hay khả năng tương thích schema.
- Kết quả byte giống nhau là điều kiện đúng để so sánh; **benchmark mới quyết định hiệu năng với workload cụ thể**.

Với record chỉ gồm primitive đơn giản và ít concurrency, **RAF thường là code dễ hiểu**. Với nhu cầu offset rõ ràng, buffer batching và tích hợp NIO, **FileChannel thường thuận tiện hơn**. Đánh giá sự phù hợp theo semantics, độ đúng đắn và đặc tính vận hành trước khi tối ưu.

**Tài liệu chính thức — Java SE 17:**

1. [RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html) — `seek`, `getFilePointer`, `readInt`, `writeLong`, `getChannel`.
2. [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html) — positional `read/write`, `size`, `position`, `force` và lock.
3. [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — `putInt/getInt`, `putLong/getLong`, `flip`, `position/limit`.
4. [ByteOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html) — `BIG_ENDIAN` và `LITTLE_ENDIAN`.
5. [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `mismatch`, tệp tạm và truy cập đường dẫn.
