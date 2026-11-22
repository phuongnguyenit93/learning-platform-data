# FileChannel: đọc ghi theo vị trí hiện tại trong Java NIO

## 1. Bản chất của current file position

`java.nio.channels.FileChannel` là kênh đọc/ghi tệp trong Java NIO. Mỗi đối tượng channel có một **vị trí hiện tại** (`current file position`) kiểu `long`, đo bằng **byte** từ đầu tệp. Hai phương thức quan trọng:

- `position()`: trả offset hiện tại.
- `position(long newPosition)`: đặt offset cho các thao tác I/O tương đối tiếp theo.

Khi gọi `read(ByteBuffer)` hay `write(ByteBuffer)` **không truyền offset**, channel xử lý byte bắt đầu từ position hiện tại, rồi tự tiến theo **số byte thực tế** đã đọc/ghi. Đây chính là **đọc ghi theo vị trí hiện tại**.

Ngược lại, `read(ByteBuffer, long position)` và `write(ByteBuffer, long position)` làm việc ở offset chỉ định mà **không thay đổi current file position**. Hai cơ chế đều cho phép truy cập ngẫu nhiên; khác nhau ở việc có dùng/tiến con trỏ chung của channel hay không.

**Mục tiêu:** biết mở channel đúng quyền, điều khiển position, thực hiện vòng lặp đọc/ghi đủ byte, phân biệt position của channel và `ByteBuffer`, nhận biết EOF, ghi đè giữa tệp, đọc lại từ đầu, đồng thời tránh tranh chấp khi nhiều luồng sử dụng cùng channel.

## 2. Hình dung tệp và con trỏ

Giả sử tệp có sáu byte ASCII `ABCDEF`:

```text
Byte offset: 0 1 2 3 4 5 6
Nội dung:   A B C D E F |EOF|
            ^
          position=0
```

Sau khi `read(dst)` đọc thành công 2 byte từ offset 0:

```text
Byte offset: 0 1 2 3 4 5 6
Nội dung:   A B C D E F |EOF|
                ^
              position=2
```

Nếu position đang là 2, `write(ByteBuffer.wrap(new byte[]{'X','Y'}))` (ghi đủ hai byte) sẽ thay `CD` bằng `XY`, tạo nội dung `ABXYEF`, position tăng lên 4. Ghi giữa tệp là **ghi đè**, không tự chèn byte hay dịch các byte phía sau.

Đặc điểm cần nhớ:

1. Vị trí là **byte offset**, không phải chỉ số ký tự trong chuỗi UTF-8.
2. `size()` trả độ dài tệp; `position()` là nơi I/O tương đối tiếp theo bắt đầu. Chúng có thể khác nhau.
3. `position(newPosition)` không tự đọc, ghi, cắt ngắn hay mở rộng tệp.
4. Cho phép đặt position vượt kích thước tệp. Đọc ở nơi chưa có byte sẽ gặp EOF; ghi có thể mở rộng file và tạo khoảng trống phụ thuộc filesystem/provider.
5. Các `FileChannel` mở **riêng** vào cùng một tệp có con trỏ position riêng, dù dữ liệu tệp vẫn được chia sẻ.
6. Nhiều thành phần sử dụng **cùng một đối tượng FileChannel** chia sẻ cùng current position của đối tượng ấy.

## 3. Mở FileChannel đúng mục đích

Java 17+ thường dùng `FileChannel.open(Path, OpenOption...)`, kết hợp try-with-resources:

```java
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("data.bin");

try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    // channel.position(), channel.read(...), channel.write(...)
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập.

| OpenOption | Tác dụng |
|---|---|
| `READ` | Cho phép đọc tệp |
| `WRITE` | Cho phép ghi tệp |
| `CREATE` | Tạo tệp nếu chưa có khi mở để ghi |
| `CREATE_NEW` | Tạo mới, lỗi nếu đường dẫn đã tồn tại |
| `TRUNCATE_EXISTING` | Nếu mở để ghi, cắt rỗng nội dung tệp hiện hữu |
| `APPEND` | Các thao tác ghi tuân theo semantics nối cuối tệp; không dùng để sửa offset tùy ý |

Mở để đọc đơn thuần:

```java
try (FileChannel channel =
             FileChannel.open(path, StandardOpenOption.READ)) {
    // Chỉ đọc.
}
```

Đừng thêm `TRUNCATE_EXISTING` nếu mục tiêu là chỉnh sửa tệp đang chứa dữ liệu. Với `APPEND`, không kết hợp `READ`: tổ hợp không hợp lệ có thể ném `IllegalArgumentException`. Để đọc và ghi tại offset tùy ý, chọn `READ` + `WRITE` thay vì `APPEND`.

Khi mở channel theo cách thông thường, vị trí ban đầu là 0. Trong các tình huống cần rõ ràng, gọi `channel.position(0L)` để xác lập điểm bắt đầu. Luôn đóng channel bằng try-with-resources.

Ngoài `FileChannel.open`, có thể lấy channel từ `RandomAccessFile.getChannel()`. Nếu làm như vậy, **`RandomAccessFile` và channel liên kết dùng chung file position**: `raf.seek(...)` tác động tới `channel.position()` và ngược lại. Tránh phối hợp tùy tiện hai API trên cùng đối tượng.

## 4. Phân biệt hai loại position

`FileChannel.position()` và `ByteBuffer.position()` **không phải một biến**:

| Đối tượng | `position()` biểu thị | Đơn vị |
|---|---|---|
| FileChannel | Offset của thao tác I/O tương đối tiếp theo trong **tệp** | Byte của tệp |
| ByteBuffer | Vị trí đọc/ghi tiếp theo trong **vùng nhớ buffer** | Byte của buffer |

Giả sử channel position=100, buffer position=3 và remaining=5. Nếu `channel.read(buffer)` đọc thành công 4 byte:

- Channel position từ 100 thành **104**.
- Buffer position từ 3 thành **7**.
- Bốn byte của tệp được đặt trong buffer tại các index 3, 4, 5, 6.

Một lệnh relative I/O có thể làm **cả hai position tăng cùng lượng**, nhưng việc gọi `buffer.flip()`, `buffer.clear()` hay `buffer.rewind()` **không di chuyển position của channel**. Tương tự, `channel.position(0)` không đổi position của buffer.

Chu trình trạng thái buffer:

| Phương thức | Ý nghĩa |
|---|---|
| `put(...)` | Đưa byte vào buffer và tiến buffer position |
| `flip()` | Đặt limit = position cũ, position = 0; chuẩn bị đọc phần byte vừa ghi |
| `clear()` | Đặt position = 0 và limit = capacity; **không xóa nội dung bộ nhớ** |
| `rewind()` | Đưa position buffer về 0, giữ limit |
| `remaining()` | Số byte còn có thể đọc/ghi trong buffer (`limit - position`) |
| `hasRemaining()` | Kiểm tra còn byte chưa xử lý hay không |

Sai lầm thường gặp là sau khi `put` vào buffer lại `write(buffer)` ngay mà **quên `flip()`**, khiến buffer đang ở cuối phần dữ liệu hoặc ghi cả vùng không mong muốn.

## 5. Đọc theo vị trí hiện tại: `read(ByteBuffer)`

Chữ ký:

```java
int bytesRead = channel.read(destination);
```

Quy trình:

1. Bắt đầu từ `channel.position()`.
2. Đọc byte từ file, đưa vào `destination` từ `destination.position()`.
3. Xử lý tối đa `destination.remaining()` byte trong một lần gọi.
4. Trả số byte **thực tế** đọc, có thể ít hơn remaining hoặc bằng 0; nếu đã đến EOF và không đọc được byte, trả `-1`.
5. Với `n > 0`, channel position và destination position đều tăng `n`.

Ví dụ minh họa (giả định channel đã mở để đọc):

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
int n = channel.read(buffer);
if (n > 0) {
    buffer.flip();
    while (buffer.hasRemaining()) {
        byte b = buffer.get();
        // Xử lý byte b.
    }
}
```

**Một lời gọi `read` không đảm bảo lấp đầy buffer.** Nếu định dạng yêu cầu đọc chính xác N byte, dùng vòng lặp kiểm tra số byte đã nhận và phát hiện EOF trước khi đủ N byte:

```java
static void readFully(FileChannel channel, ByteBuffer destination)
        throws IOException {
    while (destination.hasRemaining()) {
        int n = channel.read(destination);
        if (n == -1) {
            throw new EOFException("Tệp kết thúc trước số byte yêu cầu");
        }
        if (n == 0) {
            throw new IOException("Lần đọc không tiến thêm byte");
        }
    }
}
```

Đây là **phương thức minh họa**, cần các import `java.io.EOFException`, `java.io.IOException`, `java.nio.ByteBuffer` và `java.nio.channels.FileChannel`. Chính sách báo lỗi khi `n == 0` của ví dụ tránh lặp vô hạn. Ứng dụng có provider đặc biệt có thể chọn retry có giới hạn và quản lý liveness khác. Vẫn phải xử lý trường hợp tệp bị thu ngắn hay dữ liệu bị thay đổi bởi tiến trình khác trong lúc đọc.

Nếu muốn đọc toàn bộ đến EOF (không biết trước kích thước), thường dùng vòng lặp `read`, xử lý mỗi khối sau `flip` và chuẩn bị lại buffer. Khi `read` trả `-1` thì dừng; không coi buffer capacity là số byte dữ liệu hợp lệ.

## 6. Ghi theo vị trí hiện tại: `write(ByteBuffer)`

Chữ ký:

```java
int bytesWritten = channel.write(source);
```

Với `n > 0` byte thực sự ghi được:

- Tệp được ghi tại current position, có thể đè byte đã tồn tại.
- Channel position tăng `n`.
- `source.position()` tăng `n` vì `write` đã tiêu thụ byte từ buffer.
- Kích thước tệp có thể tăng nếu phần ghi vượt vị trí EOF cũ.

Ví dụ gửi ba byte ASCII (đoạn minh họa, channel phải có quyền ghi):

```java
ByteBuffer source = ByteBuffer.wrap(new byte[]{'A', 'B', 'C'});
while (source.hasRemaining()) {
    int n = channel.write(source);
    if (n == 0) {
        throw new IOException("Lần ghi không tiến thêm byte");
    }
}
```

Khi vòng lặp kết thúc thành công, buffer không còn remaining; position channel tăng đúng 3 byte so với lúc bắt đầu. Không dựa vào giả định một lần `write(source)` luôn ghi đủ toàn bộ nội dung.

Mẫu ghi nhiều primitive:

```java
ByteBuffer record = ByteBuffer.allocate(Integer.BYTES + Long.BYTES);
record.putInt(2026);
record.putLong(1000L);
record.flip();
while (record.hasRemaining()) {
    channel.write(record);
}
```

Ở đây buffer chứa 12 byte (4 + 8). Nếu file format cần little-endian, đặt `record.order(ByteOrder.LITTLE_ENDIAN)` **trước** khi put và dùng cùng byte order lúc giải mã. Offset channel vẫn đo bằng byte, không đo bằng số lượng giá trị `int`/`long`.

## 7. Ví dụ Java 17+ hoàn chỉnh

Chương trình tạo tệp tạm, ghi `ABCDEF`, di chuyển về đầu và đọc hai byte, đọc riêng byte ở offset 4 bằng positional I/O, sau đó ghi đè `CD` bằng `XY` từ **current position=2**.

Lưu thành **`FileChannelPositionDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelPositionDemo {

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("file-channel-position-", ".bin");

        try {
            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer initial = ByteBuffer.wrap(
                        "ABCDEF".getBytes(StandardCharsets.US_ASCII));

                writeFully(channel, initial);
                System.out.println("After write: position="
                        + channel.position() + ", size=" + channel.size());

                channel.position(0);
                ByteBuffer firstTwo = ByteBuffer.allocate(2);
                readFully(channel, firstTwo);
                firstTwo.flip();
                System.out.println("Read: "
                        + StandardCharsets.US_ASCII.decode(firstTwo)
                        + ", position=" + channel.position());

                ByteBuffer atFour = ByteBuffer.allocate(1);
                readFullyAt(channel, atFour, 4L);
                atFour.flip();
                System.out.println("Absolute read: "
                        + StandardCharsets.US_ASCII.decode(atFour)
                        + ", position=" + channel.position());

                ByteBuffer change = ByteBuffer.wrap(
                        "XY".getBytes(StandardCharsets.US_ASCII));
                writeFully(channel, change);
                System.out.println("After overwrite: position="
                        + channel.position());

                channel.position(0);
                ByteBuffer whole = ByteBuffer.allocate(6);
                readFully(channel, whole);
                whole.flip();
                System.out.println("Final: "
                        + StandardCharsets.US_ASCII.decode(whole)
                        + ", position=" + channel.position());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    // Relative I/O: channel position và buffer position cùng tiến.
    private static void readFully(FileChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            int n = channel.read(target);
            if (n < 0) {
                throw new EOFException("Not enough bytes");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
        }
    }

    private static void writeFully(FileChannel channel, ByteBuffer source)
            throws IOException {
        while (source.hasRemaining()) {
            int n = channel.write(source);
            if (n == 0) {
                throw new IOException("Write made no progress");
            }
        }
    }

    // Positional I/O không đổi channel.position().
    private static void readFullyAt(
            FileChannel channel, ByteBuffer target, long offset)
            throws IOException {
        long position = offset;
        while (target.hasRemaining()) {
            int n = channel.read(target, position);
            if (n < 0) {
                throw new EOFException("Not enough bytes at offset " + offset);
            }
            if (n == 0) {
                throw new IOException("Positional read made no progress");
            }
            position += n;
        }
    }
}
```

Biên dịch và chạy tại thư mục chứa mã nguồn:

```bash
javac FileChannelPositionDemo.java
java FileChannelPositionDemo
```

**Stdout chính xác khi có quyền tạo/đọc/ghi/xóa tệp tạm:**

```text
After write: position=6, size=6
Read: AB, position=2
Absolute read: E, position=2
After overwrite: position=4
Final: ABXYEF, position=6
```

Từng bước:

1. Ghi sáu byte bắt đầu tại vị trí 0, nên `channel.position() == 6` và `size() == 6`.
2. `position(0)` đưa con trỏ về đầu, không làm mất dữ liệu. Đọc `AB` làm con trỏ tăng lên 2.
3. `readFullyAt(...,4L)` đọc byte `E`, **giữ nguyên vị trí channel=2**.
4. Ghi `XY` bằng relative write từ vị trí 2, thay hai byte `CD`, khiến position=4.
5. Di chuyển về 0 rồi đọc sáu byte cho ra `ABXYEF`; sau đọc position=6.

Ví dụ dùng vòng lặp đầy đủ vì `read/write` có thể trả ít byte hơn kích thước buffer. Hàm positional tăng biến `position` cục bộ sau từng lượt để nếu đọc phân mảnh vẫn lấy tiếp các byte kế tiếp, thay vì đọc đi đọc lại cùng offset.

## 8. Relative và positional I/O: khác biệt về position

```java
int n1 = channel.read(dst);         // Dùng current position.
int n2 = channel.read(dst, 128L);   // Đọc từ offset 128.

int n3 = channel.write(src);        // Dùng current position.
int n4 = channel.write(src, 256L);  // Ghi từ offset 256.
```

Đây là đoạn minh họa; giả định các biến được khai báo và channel có quyền tương ứng.

| Phương thức, với n byte thành công | Điểm bắt đầu trong file | FileChannel.position sau gọi | ByteBuffer.position sau gọi |
|---|---|---|---|
| `read(dst)` | Current position trước gọi | Tăng n | Tăng n |
| `write(src)` | Current position trước gọi | Tăng n | Tăng n |
| `read(dst, offset)` | Offset truyền vào | **Không đổi** | Tăng n |
| `write(src, offset)` | Offset truyền vào | **Không đổi** | Tăng n |
| `position(offset)` | Không có I/O | Đặt bằng offset | Không đổi |

Với positional read/write, **buffer vẫn tiến position**, dù channel không tiến. Đây là nhầm lẫn thường gặp khi tái sử dụng một buffer qua nhiều offset.

Nếu ứng dụng đang quét một tệp bằng relative read nhưng cần cập nhật header ở offset 0, positional write có thể phù hợp để không làm mất điểm đang quét. Vẫn cần xử lý ghi đè đúng cấu trúc tệp, quyền truy cập và độ dài dữ liệu.

## 9. EOF, short I/O và số byte thực tế

### EOF khi đọc

Khi file position đã ở cuối tệp và buffer còn sức chứa, `read(buffer)` thường trả `-1`. Nó **không tự cuộn position về đầu**. Muốn đọc lại, phải `channel.position(0)` và chuẩn bị trạng thái buffer đúng.

Nếu `read` trả `0`, không nên vội coi đó là EOF: đây là “chưa chuyển byte nào trong lời gọi đó”, có thể xảy ra khi buffer không còn remaining hoặc tình huống provider cụ thể. Khi `remaining()==0`, không cần gọi read.

### Short read / short write

Ví dụ cần đọc 4096 byte nhưng chỉ nhận 1024 trong lượt đầu. Đó **không nhất thiết là lỗi**. Hàm tiếp tục khi buffer còn remaining, sử dụng position đã tự tiến. Tương tự khi ghi: `write` trả về số byte thực ghi, nên luôn kiểm tra `hasRemaining()` nếu giao thức yêu cầu đủ khối.

Với positional I/O cần tự cập nhật offset:

```java
long offset = 1000L;
while (buffer.hasRemaining()) {
    int n = channel.read(buffer, offset);
    if (n == -1) {
        throw new EOFException("Unexpected EOF");
    }
    if (n == 0) {
        throw new IOException("No progress");
    }
    offset += n;  // Bắt buộc: current file position không tự tiến.
}
```

Đây là đoạn minh họa, yêu cầu buffer đã được chuẩn bị với đúng remaining. **Không** dùng nguyên offset 1000 cho mọi vòng lặp; nếu vậy sẽ lặp lại dữ liệu đầu đoạn khi lần đọc đầu chỉ xử lý một phần.

## 10. Ghi đè, nối cuối và thay đổi kích thước

### Ghi đè ở giữa tệp

Nếu tệp là `ABCDE`, gọi `channel.position(1)` rồi ghi đủ `XY`:

```text
Trước: A B C D E
Offset 0 1 2 3 4

Sau:   A X Y D E
             ^
        position = 3
```

Kích thước vẫn là 5. `FileChannel.write` không tự chèn hai byte và đẩy `BCDE` sang phải. Khi định dạng yêu cầu chèn thật sự, ứng dụng phải tự di chuyển/viết lại phần đuôi.

### Ghi ở cuối

Trong trường hợp một writer đơn giản:

```java
channel.position(channel.size());
ByteBuffer tail = ByteBuffer.wrap(new byte[]{'F', 'G'});
while (tail.hasRemaining()) {
    channel.write(tail);
}
```

Đoạn này không bảo đảm **append nguyên tử** với nhiều writer khác vì `size()`, `position(...)` và `write(...)` là các thao tác riêng. Nếu cần semantics append, cân nhắc mở channel với `StandardOpenOption.APPEND` và ràng buộc môi trường; APPEND không thích hợp cho sửa tệp tại offset tùy ý và không kết hợp với READ.

### Position vượt EOF

Giả sử size=10, `channel.position(100)` là hợp lệ và **không** làm size thành 100. Đọc từ đó có thể trả `-1`; ghi ở vị trí đó có thể làm tệp dài ra, tạo khoảng trống từ EOF cũ tới vùng vừa ghi. Nội dung khoảng trống phụ thuộc hệ thống và không nên dựa vào nó như phần dữ liệu được khởi tạo bởi ứng dụng.

### `truncate`, `size` và `force`

- `size()`: lấy số byte hiện có, không thay position.
- `truncate(newSize)`: cắt phần đuôi nếu size cũ lớn hơn newSize; nếu position hiện tại lớn hơn newSize thì position được giảm xuống newSize. Nếu size cũ đã nhỏ hơn newSize, `truncate` **không mở rộng** tệp.
- `force(metaData)`: yêu cầu đồng bộ nội dung tệp (và metadata nếu `true`) xuống hệ lưu trữ theo ngữ nghĩa API; không phải thao tác thay position và không tự biến nhiều cập nhật thành một giao dịch nguyên tử.

```java
channel.position(18);
channel.truncate(10);
// Khi file trước truncate lớn hơn 10:
// channel.position() trở thành 10 nếu trước đó là 18.
```

Đoạn này mang tính minh họa; channel cần quyền ghi và filesystem phải cho phép thao tác.

## 11. An toàn khi nhiều luồng cùng dùng một channel

Một `FileChannel` có một current position chung đối với các thành phần cầm **cùng instance**. Ví dụ hai tác vụ:

```text
Tác vụ A: channel.position(100)
Tác vụ B: channel.position(500)
Tác vụ A: channel.read(bufferA)  ← có thể đọc từ offset 500.
```

Dù các thao tác I/O trên FileChannel có các quy tắc phối hợp nội bộ, **chuỗi nhiều lời gọi** `position(offset)` rồi `read/write(buffer)` của ứng dụng **không tự động nguyên tử** trước luồng khác.

Các cách giải quyết phụ thuộc nhu cầu:

- Chỉ có **một owner** thực hiện các thao tác relative I/O tuần tự.
- Khóa cả cụm `position + read/write` khi buộc chia sẻ cùng channel.
- Dùng `read(buffer, offset)` / `write(buffer, offset)` cho các tác vụ có offset riêng, để không tranh chấp current position.
- Có thể mở channel riêng nếu kiến trúc phù hợp; mỗi channel có position riêng, nhưng vẫn chia sẻ tệp và không bảo đảm chống ghi trùng hay truncate đồng thời.

Ngay cả positional I/O cũng cần đồng bộ khi các tác vụ cùng sửa một vùng, thay đổi độ dài file, hoặc đọc dữ liệu phải nhất quán trong nhiều bước. Dùng offset rõ ràng giảm rủi ro về con trỏ; nó không thay thế thiết kế đồng thời.

## 12. Các lỗi thường gặp

1. **Quên đưa channel về đầu trước khi đọc lại.** Sau khi ghi, current position thường ở cuối; gọi `position(0)` khi cần đọc từ đầu.
2. **Cho rằng read/write luôn xử lý đủ buffer.** Kiểm tra return value, `hasRemaining()` và lặp khi cần.
3. **Không xử lý EOF.** `-1` khác `0`; với bản ghi cố định, thiếu byte là điều kiện lỗi hoặc recovery rõ ràng.
4. **Quên `flip()` trước khi đưa buffer vừa put ra channel.** Buffer.position/limit sai dẫn tới ghi sai lượng byte.
5. **Gọi `clear()` rồi tưởng dữ liệu cũ bị xóa.** `clear()` chỉ thay trạng thái buffer.
6. **Nhầm position channel với position buffer.** Chúng độc lập dù một lần relative I/O có thể tăng cả hai.
7. **Nhầm hai overload read/write.** Overload có offset không thay current position, nhưng vẫn tiến buffer position.
8. **Dùng một offset cố định khi lặp positional read/write.** Phải tăng offset bằng số byte đã xử lý.
9. **Tưởng ghi giữa file là chèn.** Nó ghi đè byte hiện hữu.
10. **Nhầm position và size.** `position(size)` không thể bảo đảm append nguyên tử với writer khác.
11. **Tưởng `truncate` có thể mở rộng file.** Nó chỉ cắt nếu size cũ lớn hơn tham số.
12. **Mở với `TRUNCATE_EXISTING` khi muốn giữ dữ liệu.** Chế độ mở này có thể làm rỗng tệp.
13. **Dùng APPEND khi cần random overwrite.** Append có semantics riêng, không phù hợp đặt offset ghi tùy ý.
14. **Coi offset bằng chỉ số ký tự UTF-8.** Offset tính bằng byte, một ký tự có thể nhiều byte.
15. **Cho nhiều thread tự `position + read/write` trên cùng channel.** Cặp thao tác không nguyên tử; cần owner, khóa hoặc positional I/O.
16. **Quên đóng channel.** Dùng try-with-resources và xử lý `IOException`, `ClosedChannelException` theo tình huống.

## 13. Tình huống áp dụng

**Đọc tuần tự tệp log:** relative `read(buffer)` phù hợp vì mỗi lần đọc tự tiến qua phần đã xử lý. Chuẩn bị buffer đúng cách và phân tích ranh giới bản ghi/charset riêng.

**Ghi lần lượt header và payload:** ghi đủ buffer header rồi buffer payload bằng relative `write`. Position tự tiến đúng số byte thực ghi; không cần tính offset cộng tay nếu chỉ ghi nối theo thứ tự trong một writer.

**Sửa header khi đang đọc payload:** dùng positional `write(src, headerOffset)` để không làm đổi con trỏ đọc payload. Nhưng vẫn cần quản lý tính nhất quán của format nếu thao tác đọc/ghi xen kẽ.

**Đọc nhiều trang tệp theo offset độc lập:** positional I/O giúp mỗi tác vụ có offset tường minh, tránh `position + read` trên một con trỏ chung; chú ý việc tăng offset khi read ngắn.

**Tạo file record fixed-size:** có thể dùng `channel.position(headerSize + index * recordSize)` rồi relative `read/write` trong logic một owner. Nếu có nhiều tác vụ truy cập các record song song, positional I/O thường làm quan hệ offset rõ hơn. Tính toán offset bằng `long` và tránh tràn số khi index đến từ input không tin cậy.

## 14. Câu hỏi tự kiểm tra

**1.** Tệp dài 10 byte, channel position=3, buffer còn chỗ cho 4 byte. Nếu relative `read` thực sự đọc đủ 4 byte, position mới là bao nhiêu?  
**Đáp án:** 7; buffer position cũng tăng 4 so với trước gọi.

**2.** Sau đó `channel.read(dst, 1L)` đọc 2 byte. Current position channel có đổi không?  
**Đáp án:** Không. Vẫn 7. Chỉ buffer position tăng 2.

**3.** Tệp `ABCDE`, position=1, ghi tương đối đủ `XY`. Kết quả là gì?  
**Đáp án:** `AXYDE`, position=3, kích thước vẫn 5.

**4.** `buffer.flip()` có đưa current file position về 0 không?  
**Đáp án:** Không. Nó chỉ chuyển chế độ của buffer. Muốn channel về 0, gọi `channel.position(0L)`.

**5.** Đã ghi đến cuối và `read(dst)` trả `-1`. `dst.capacity()` có cho biết số byte đọc thành công không?  
**Đáp án:** Không. Kích thước buffer không phải số byte dữ liệu hợp lệ. Phải dựa vào return value và position/limit trước–sau.

**6.** Vì sao không nên để hai thread tự gọi `position(offset)` rồi `read(buffer)` trên cùng channel?  
**Đáp án:** Thread khác có thể đổi position giữa hai lời gọi; cụm lệnh không nguyên tử. Sử dụng positional read hoặc đồng bộ phù hợp.

## 15. Tóm tắt

- **`FileChannel.read(ByteBuffer)` / `write(ByteBuffer)` đọc ghi tại current position và tiến con trỏ theo byte xử lý thực tế.**
- **`position(long)` chỉ di chuyển nơi thao tác tiếp theo bắt đầu; `size()` là kích thước tệp.**
- **FileChannel và ByteBuffer có position riêng.** `flip/clear` tác động buffer, không tác động con trỏ file.
- **`read/write(buffer, offset)` không đổi channel position** nhưng vẫn làm buffer position tiến theo số byte xử lý.
- **Short I/O và EOF phải được xử lý tường minh**; các vòng lặp đọc/ghi theo đúng độ dài là nền tảng của xử lý nhị phân đáng tin.
- **Tránh tranh chấp con trỏ chung khi đa luồng** bằng mô hình một owner, đồng bộ phù hợp hoặc positional I/O.

### Tham khảo

- Java SE 17 `FileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `StandardOpenOption`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html
