# Scattering read và gathering write trong Java NIO Channel

## 1. Mục tiêu và bài toán

Trong Java NIO, thông tin thường được vận chuyển qua **Channel** và đặt trong **Buffer**. Nếu một thông điệp gồm nhiều phần, chẳng hạn **header** và **payload**, ứng dụng có thể:

- **Scattering read:** đọc các byte liên tiếp từ một channel rồi **phân tán** chúng vào nhiều `ByteBuffer` theo thứ tự.
- **Gathering write:** lấy các byte còn lại trong nhiều `ByteBuffer` rồi **gom** thành một dãy byte liên tiếp để ghi ra channel.

Đây là cơ chế I/O theo **vector buffer**: một lời gọi xử lý một mảng buffer, giúp thể hiện rõ cấu trúc dữ liệu và có thể giảm số lời gọi I/O tùy hệ thống. Tuy nhiên, **một lời gọi không đảm bảo đọc/ghi đủ mọi byte**, không đại diện cho một thông điệp mạng hoàn chỉnh và cũng không tự tạo một transaction nguyên tử.

Hình dung một frame đơn giản có **4 byte header** chứa độ dài payload, sau đó là **3 byte payload** chứa ký tự ASCII `ABC`:

~~~text
Luồng byte trên file/socket:
  00 00 00 03  41 42 43
  └─ header ─┘  └ body ┘
  4 byte         3 byte

Scattering read:
  Channel ───────────────┬──> ByteBuffer header [00 00 00 03]
                         └──> ByteBuffer body   [41 42 43]
                             (theo thứ tự mảng, header trước body)

Gathering write:
  ByteBuffer header [00 00 00 03] ─┐
                                   ├──> Channel: 00 00 00 03 41 42 43
  ByteBuffer body   [41 42 43] ────┘
~~~

Điều kiện quan trọng: **kích thước vùng header và body phải được chuẩn bị đúng**. Khi độ dài body chưa biết cho đến lúc đọc xong header, chương trình thường cần **hai pha đọc** hoặc một parser lưu trạng thái, thay vì mặc định một lời gọi scattering có thể tự cấp đúng buffer cho payload.

## 2. API nào hỗ trợ?

Hai interface ở package `java.nio.channels`:

- `ScatteringByteChannel`: đọc tuần tự các byte từ channel vào **một mảng `ByteBuffer`**.
- `GatheringByteChannel`: ghi tuần tự dữ liệu từ **một mảng `ByteBuffer`** ra channel.

Các overload cơ bản:

~~~java
// Các chữ ký API (không phải chương trình độc lập):
long read(ByteBuffer[] dsts) throws IOException;
long read(ByteBuffer[] dsts, int offset, int length) throws IOException;

long write(ByteBuffer[] srcs) throws IOException;
long write(ByteBuffer[] srcs, int offset, int length) throws IOException;
~~~

Lưu ý: các phương thức `read` thuộc `ScatteringByteChannel`, các phương thức `write` thuộc `GatheringByteChannel`; không phải mọi kiểu `Channel` đều hỗ trợ cả hai. Những kiểu tiêu biểu hỗ trợ là:

| Channel | Scattering read | Gathering write | Bối cảnh điển hình |
|---|---|---|---|
| `FileChannel` | Có | Có | Đọc/ghi tệp có header, payload, record nhị phân |
| `SocketChannel` | Có | Có | Đọc/ghi byte stream TCP, frame giao thức |
| Một `ReadableByteChannel` / `WritableByteChannel` bất kỳ | Chưa chắc | Chưa chắc | Phải xem interface cụ thể mà object triển khai |

Các ví dụ dùng `FileChannel` vì dễ tái lập kết quả; quy tắc buffer vẫn áp dụng khi dùng `SocketChannel`, nhưng I/O mạng có thể trả về ít byte hơn mong đợi, đặc biệt khi non-blocking.

### `offset` và `length` là vị trí trong **mảng buffer**

Với `ByteBuffer[] buffers = {a, b, c, d};`, lời gọi `read(buffers, 1, 2)` chỉ xem xét **b** rồi **c**:

- `offset = 1`: bắt đầu tại phần tử index 1 của **mảng**.
- `length = 2`: xử lý đúng hai phần tử của **mảng**; index kết thúc (exclusive) là 3.
- Không phải offset byte của file, không phải position của buffer và không phải số byte muốn đọc.

Nếu `offset < 0`, `length < 0` hoặc `offset + length` vượt kích thước mảng theo cách không hợp lệ, Java ném `IndexOutOfBoundsException`. Truyền `length=0` nghĩa là không chọn buffer nào và kết quả thao tác là 0. Khi cần truyền toàn bộ mảng, overload không có `offset,length` thuận tiện hơn.

## 3. Nhắc lại trạng thái ByteBuffer

Một `ByteBuffer` có ba chỉ số chính:

- `capacity`: tổng số byte có thể chứa, không đổi.
- `limit`: ranh giới cuối (exclusive) của miền hiện hành.
- `position`: index của thao tác tương đối tiếp theo.

Luôn có: `0 <= position <= limit <= capacity`. Số phần tử còn lại là `remaining() = limit - position`.

Hai trạng thái sử dụng phổ biến:

| Thời điểm | Buffer đích để **channel đọc vào** | Buffer nguồn để **channel ghi ra** |
|---|---|---|
| Chuẩn bị | Thường dùng `clear()` hoặc `compact()` để còn chỗ nhận dữ liệu | Đã `put(...)` rồi `flip()` để chỉ còn payload cần gửi |
| Trong lời gọi I/O | Channel đặt byte vào vùng `[position, limit)` và tăng `position` | Channel lấy byte từ vùng `[position, limit)` và tăng `position` |
| Sau lời gọi | Dùng `flip()` để đọc dữ liệu vừa nhận (khi phù hợp) | Nếu `hasRemaining()` thì vẫn còn dữ liệu chưa ghi |

Ví dụ:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);   // p=0, l=4, c=4
ByteBuffer body = ByteBuffer.allocate(8);     // p=0, l=8, c=8

// Cả hai có thể được dùng làm buffer đích cho scattering read.

ByteBuffer outgoing = ByteBuffer.allocate(4);
outgoing.putInt(3);                            // p=4, l=4
outgoing.flip();                               // p=0, l=4
// outgoing sẵn sàng làm buffer nguồn cho gathering write.
~~~

**Cẩn thận:** `flip()` đưa `limit` bằng `position` cũ và `position=0`. Nếu gọi `flip()` quá sớm trên buffer rỗng vừa cấp phát, `limit` thành 0 và channel sẽ không thể nạp/đọc byte nào vào buffer đích bằng thao tác tương đối.

## 4. Scattering read: phân tán dữ liệu vào nhiều buffer

Lời gọi:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
ByteBuffer payload = ByteBuffer.allocate(3);

long bytesRead = channel.read(new ByteBuffer[] {header, payload});
~~~

Đây là **đoạn minh họa** giả định `channel` là một `ScatteringByteChannel` đang mở. Một chương trình Java 17 hoàn chỉnh nằm ở mục 7.

Cơ chế:

1. Channel bắt đầu lấy byte từ vị trí đọc hiện tại của nó.
2. Đặt các byte nhận được vào buffer đầu tiên, từ `header.position()` đến trước `header.limit()`.
3. Chỉ khi buffer đầu tiên đã đầy vùng `remaining()` thì mới chuyển sang buffer tiếp theo.
4. Kết quả `long bytesRead` là **tổng số byte thực sự đã chuyển vào các buffer**.
5. `position` của từng buffer nhận byte tăng tương ứng; `limit` không tự đổi.

Giả sử channel chứa 7 byte, việc đọc thực tế trả 5 byte:

~~~text
Trước read:
  header: p=0, l=4, còn 4 byte
  body:   p=0, l=3, còn 3 byte

Đã nhận 5 byte:
  header = [00 00 00 03], p=4, l=4
  body   = [41 .. ..],    p=1, l=3
  return = 5L

Còn thiếu 2 byte payload:
  header.remaining() = 0
  body.remaining()   = 2
~~~

Nếu gọi lại `channel.read(new ByteBuffer[]{header, body})` và 2 byte `42 43` còn trong nguồn, channel sẽ **bỏ qua header không còn chỗ** và tiếp tục nạp vào body. Chỉ khi đã nhận đủ mới `flip()` các buffer để cho parser đọc.

### Một lần read không đảm bảo “đọc đủ”

- Có thể trả về **số dương nhỏ hơn tổng remaining**; đây là hành vi bình thường.
- Có thể trả về **0** nếu không đọc được byte nào ngay lúc đó, đặc biệt với channel non-blocking.
- Có thể trả về **-1** khi gặp cuối luồng (EOF) trước khi nhận byte trong lời gọi đó.
- Với buffer đích chỉ đọc (read-only), việc truyền vào scattering read có thể gây `ReadOnlyBufferException`; buffer đích phải writable.
- Nếu đã chạm `limit` của buffer đầu tiên nhưng frame còn cần một lượng header lớn hơn kích thước của nó, dữ liệu có thể chảy vào buffer thứ hai dù về **ý nghĩa giao thức** đó vẫn là header. Scattering chỉ tuân theo **dung lượng buffer**, không tự hiểu header/payload.

Vì vậy, nếu giao thức nói header đúng 4 byte, hãy chuẩn bị buffer đầu tiên có **remaining đúng 4**, không phải 8, rồi tin rằng parser sẽ tự dừng sau 4 byte.

### Vòng đọc đến khi đủ các vùng bắt buộc

Với **FileChannel đọc blocking** và một file đã biết là có đủ nội dung, có thể lặp đến khi tất cả buffer đầy:

~~~java
static long readExactly(FileChannel channel, ByteBuffer[] dsts)
        throws IOException {
    long total = 0;

    while (hasRemaining(dsts)) {
        long count = channel.read(dsts);
        if (count < 0) {
            throw new EOFException("Tep ket thuc truoc khi doc du");
        }
        if (count == 0) {
            throw new IOException("Khong co tien trien khi doc tep");
        }
        total += count;
    }
    return total;
}

static boolean hasRemaining(ByteBuffer[] buffers) {
    for (ByteBuffer b : buffers) {
        if (b.hasRemaining()) return true;
    }
    return false;
}
~~~

Đây là đoạn phương thức minh họa, cần imports `java.io.*`, `java.nio.*` và `java.nio.channels.*`; mục 7 cung cấp chương trình độc lập.

Đối với **SocketChannel non-blocking**, **không** dùng vòng lặp chạy liên tục khi `read(...) == 0`. Phải tích hợp cơ chế readiness/`Selector` hoặc điều phối khi có dữ liệu, rồi tiếp tục đọc tại `position` đã lưu. Để hạn chế tiêu thụ bộ nhớ, luôn giới hạn kích thước frame/buffer nhận từ nguồn bên ngoài.

### Buffer không nhận byte vẫn giữ position

Nếu source hết dữ liệu trước khi ghi vào một buffer phía sau, `position` của buffer đó giữ nguyên. Khi một buffer đã `remaining() == 0`, nó không nhận thêm byte dù vẫn nằm trong mảng. Nếu tổng `remaining()` bằng 0, đọc scattering không có vùng đích nào để nhận dữ liệu; cần chuẩn bị lại buffer khi muốn tiếp tục.

## 5. Gathering write: gom nhiều buffer thành một luồng ghi

Lời gọi:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
header.putInt(3);
header.flip(); // Header: 4 byte hợp lệ.

ByteBuffer payload =
        ByteBuffer.wrap(new byte[] {65, 66, 67}); // "ABC"

long bytesWritten = channel.write(
        new ByteBuffer[] {header, payload});
~~~

Đây là đoạn minh họa giả định `channel` là `GatheringByteChannel` có quyền ghi.

Cơ chế:

1. Đọc byte từ vùng `[position, limit)` của buffer đầu tiên.
2. Khi buffer đầu tiên hết byte còn lại, chuyển sang buffer thứ hai rồi tiếp tục.
3. Nối các byte theo **đúng thứ tự mảng** để ghi ra channel.
4. Kết quả `long bytesWritten` là số byte **đã thực sự được channel chấp nhận ghi trong lần gọi**.
5. `position` của những buffer đã tiêu thụ dữ liệu tăng; `limit` không đổi.

Giả sử buffer header có 4 byte và body có 3 byte, nhưng channel chỉ chấp nhận 5 byte:

~~~text
Trước write:
  header: p=0, l=4, remaining=4
  body:   p=0, l=3, remaining=3

Sau write trả 5:
  header: p=4, l=4, remaining=0
  body:   p=1, l=3, remaining=2
  bytes written: 00 00 00 03 41

Lần write tiếp theo bắt đầu:
  header không còn byte -> bỏ qua
  body tiếp tục ở 42, 43
~~~

Đây là đặc tính rất hữu ích: **giữ nguyên các buffer** sau một lần ghi dở rồi gọi lại, các `position` đã ghi nhớ chính xác phần chưa gửi. **Không `rewind()` buffer sau một lần partial write**, vì nó có thể dẫn đến ghi/gửi **lặp dữ liệu**.

### Vòng ghi cho FileChannel

~~~java
static long writeAll(FileChannel channel, ByteBuffer[] srcs)
        throws IOException {
    long total = 0;

    while (hasRemaining(srcs)) {
        long count = channel.write(srcs);
        if (count == 0) {
            throw new IOException("Khong co tien trien khi ghi tep");
        }
        total += count;
    }
    return total;
}
~~~

Với `FileChannel` dùng trong ví dụ, vòng này minh họa việc ghi đủ dữ liệu trước khi hoàn thành. Nếu dùng `SocketChannel` non-blocking, `write(...) == 0` là một tình huống bình thường; **đợi kênh có thể ghi** (ví dụ với `Selector.OP_WRITE`), giữ các buffer/position qua các sự kiện rồi gọi lại. Không đóng hoặc tái sử dụng buffer khi còn `hasRemaining()`.

### Không tự đảm bảo tính nguyên tử

Một lời gọi gathering write không tự tạo ranh giới thông điệp trên TCP. Dữ liệu có thể được truyền thành nhiều phần, và phía nhận có thể đọc theo bất kỳ cách chia nào. Hai bản ghi do hai tác nhân khác nhau ghi không mặc nhiên tạo nên một giao dịch được bảo vệ; nếu cần tránh xen kẽ, cần phối hợp quyền ghi/cấu trúc protocol phù hợp.

Không nên khẳng định một lời gọi gathering luôn tương ứng **đúng một system call** `writev`: Java đưa ra **hợp đồng dữ liệu và buffer**, còn triển khai và OS quyết định cách thực hiện thực tế.

## 6. Hành vi của `position`, `limit`, `mark` và kết quả trả về

| Đặc điểm | Scattering read | Gathering write |
|---|---|---|
| Hướng dữ liệu | Channel → nhiều buffer đích | Nhiều buffer nguồn → Channel |
| Byte hợp lệ được chuyển | Vào vùng `[position, limit)` của từng buffer | Ra từ vùng `[position, limit)` của từng buffer |
| Thứ tự | Buffer index thấp đến cao | Buffer index thấp đến cao |
| `position` | Tăng theo byte được nạp | Tăng theo byte đã gửi |
| `limit`, `capacity` | Không được điều chỉnh tự động | Không được điều chỉnh tự động |
| Mark | Có thể bị mất hiệu lực nếu vị trí thay đổi vượt qua quy tắc mark; I/O không đặt mark mới | Tương tự |
| Kết quả | `long` số byte nhận; 0 khi chưa có byte; -1 khi EOF | `long` số byte chấp nhận ghi; có thể 0 |
| Buffer read-only | Không thể dùng làm vùng đích để nạp byte | Có thể làm nguồn vì channel chỉ đọc nội dung buffer |
| Khi xong | Thường `flip()` các buffer cần parser đọc | Kiểm tra `hasRemaining()`; khi hết có thể `clear()`/nạp tiếp |

Các phương thức `read/write` không tự `flip()` hoặc `clear()` hộ ứng dụng.

**Chi tiết về mark:** vị trí sau I/O thường tiến về phía trước nên một mark cũ (nếu hợp lệ) thường vẫn có thể sử dụng. Tuy nhiên, đừng giả định một mark là điểm rollback cho dữ liệu đã tiêu thụ trên channel: `reset()` chỉ thay đổi vị trí của **buffer**, không tua ngược byte của socket hoặc channel nguồn. Việc quay lại buffer cũng không lấy lại các byte đã được hệ điều hành chấp nhận ghi ra ngoài.

## 7. Chương trình Java 17+ hoàn chỉnh

Chương trình thực hiện các bước:

1. Tạo file tạm.
2. Tạo buffer header bốn byte ghi số nguyên `3` (big-endian) và buffer payload ba byte chứa `ABC`.
3. Ghi bằng **gathering write** cho đến khi cả hai buffer hết `remaining()`.
4. Mở file để đọc; tạo hai buffer đích có dung lượng 4 và 3 byte.
5. Đọc bằng **scattering read** cho đến khi đủ 7 byte.
6. `flip()` các buffer đích rồi giải mã header và payload, kiểm tra kết quả.

Lưu file là **`ScatteringGatheringDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ScatteringGatheringDemo {

    private static boolean hasRemaining(ByteBuffer[] buffers) {
        for (ByteBuffer b : buffers) {
            if (b.hasRemaining()) {
                return true;
            }
        }
        return false;
    }

    private static long writeAll(
            FileChannel channel, ByteBuffer[] sources)
            throws IOException {
        long total = 0;
        while (hasRemaining(sources)) {
            long count = channel.write(sources);
            if (count == 0) {
                throw new IOException("No progress while writing");
            }
            total += count;
        }
        return total;
    }

    private static long readExactly(
            FileChannel channel, ByteBuffer[] destinations)
            throws IOException {
        long total = 0;
        while (hasRemaining(destinations)) {
            long count = channel.read(destinations);
            if (count < 0) {
                throw new EOFException("Incomplete record");
            }
            if (count == 0) {
                throw new IOException("No progress while reading");
            }
            total += count;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("gather-scatter-", ".bin");
        try {
            ByteBuffer header = ByteBuffer.allocate(Integer.BYTES);
            header.putInt(3);
            header.flip();

            ByteBuffer body = ByteBuffer.wrap(
                    "ABC".getBytes(StandardCharsets.UTF_8));

            try (FileChannel out = FileChannel.open(
                    file,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {
                long count = writeAll(
                        out, new ByteBuffer[] {header, body});
                System.out.println("gathered=" + count);
            }

            System.out.println(
                    "source positions="
                    + header.position() + "/" + header.limit()
                    + "," + body.position() + "/" + body.limit());

            ByteBuffer readHeader =
                    ByteBuffer.allocate(Integer.BYTES);
            ByteBuffer readBody = ByteBuffer.allocate(3);

            try (FileChannel in = FileChannel.open(
                    file, StandardOpenOption.READ)) {
                long count = readExactly(
                        in, new ByteBuffer[] {readHeader, readBody});
                System.out.println("scattered=" + count);
            }

            System.out.println(
                    "target positions="
                    + readHeader.position() + "/" + readHeader.limit()
                    + "," + readBody.position() + "/" + readBody.limit());

            readHeader.flip();
            readBody.flip();

            int bodyLength = readHeader.getInt();
            byte[] bytes = new byte[readBody.remaining()];
            readBody.get(bytes);

            System.out.println("header length=" + bodyLength);
            System.out.println(
                    "payload=" + new String(bytes, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa source:

~~~bash
javac ScatteringGatheringDemo.java
java ScatteringGatheringDemo
~~~

**Stdout khi chương trình thành công:**

~~~text
gathered=7
source positions=4/4,3/3
scattered=7
target positions=4/4,3/3
header length=3
payload=ABC
~~~

**Giải thích:**

- Header là `00 00 00 03`; payload là `41 42 43` (UTF-8 cho ASCII `ABC`). Tổng số byte là `4 + 3 = 7`.
- `gathered=7` vì helper lặp đến khi ghi đủ; sau đó cả hai buffer nguồn có `position == limit`.
- Hai buffer đích bắt đầu ở `position=0`; `scattered=7` vì helper lặp đến khi nhận đủ 4 và 3 byte.
- Trước `flip()` các buffer đích có `position=4` và `position=3`. `flip()` đặt `position=0` để đọc chính xác phần vừa nạp.
- `getInt()` giải mã header theo big-endian mặc định của `ByteBuffer`, nhận giá trị 3; ba byte tiếp theo tạo chuỗi `ABC`.

Bài demo biết trước body dài 3 nên tạo `ByteBuffer.allocate(3)`. **Một parser giao thức thực tế không nên cấp phát dung lượng body chỉ từ dữ liệu không tin cậy mà chưa xác thực**, và cần xử lý EOF/timeout/thiếu dữ liệu.

## 8. Frame có độ dài động: khi nào không dùng một lần scattering?

Giả sử protocol gửi:

~~~text
[4 byte unsigned/signed length] [payload có N byte]
~~~

Kích thước payload chỉ biết **sau khi đọc header**. Nếu cố đoán `ByteBuffer.allocate(4096)` làm body trong một lần scattering, có ba vấn đề:

1. Body thực tế có thể **ngắn hơn 4096**; buffer không tự nhận diện ranh giới thông điệp. Nó có thể chứa cả byte của thông điệp kế tiếp.
2. Body thực tế có thể **dài hơn 4096**; bộ nhớ đích không đủ và cần bổ sung buffer.
3. Dữ liệu có thể đến thành nhiều phần, bất kể bên gửi dùng gathering write. Đây là **byte stream** (đặc biệt với TCP), không phải chuỗi “một `write` ↔ một `read`”.

Phương án phổ biến:

1. Tạo `ByteBuffer.allocate(4)` cho header, đọc **đến khi đủ 4 byte** bằng read bình thường hoặc scattering trong một state machine.
2. `flip()`, giải mã chiều dài (ví dụ `getInt()`) và **xác minh** `0 <= n <= MAX_FRAME_SIZE`.
3. Cấp buffer body theo `n` hoặc nhận theo từng phần có giới hạn; đọc body đến khi đủ.
4. Giải mã xong một frame mới bắt đầu frame kế tiếp, giữ phần byte chưa tiêu thụ nếu đã đọc vượt ranh giới.

Đoạn kiểm tra đơn giản:

~~~java
// Minh họa; header đã đọc đủ 4 byte và flip() để đọc.
int size = header.getInt();
int maxFrame = 1024 * 1024;
if (size < 0 || size > maxFrame) {
    throw new IOException("Invalid frame length: " + size);
}
ByteBuffer payload = ByteBuffer.allocate(size);
~~~

Nếu phải xử lý nhiều frame trong một luồng, có thể dùng một buffer tổng và parser riêng hoặc một state machine `READ_HEADER → READ_BODY → PROCESS_FRAME`. Scattering read rất có ích khi **biết trước các phần cố định** hoặc đã xác định dung lượng tương ứng; nó **không thay thế framing logic**.

### Xử lý trường hợp non-blocking bằng state machine

Với `SocketChannel.configureBlocking(false)`:

- `read(buffers) == 0`: chưa nhận thêm byte; **giữ `position`**, chờ `OP_READ` và thử lại sau.
- `read(buffers) > 0`: cập nhật số byte đã nhận, kiểm tra đủ header/body và chuyển trạng thái parser tương ứng.
- `read(buffers) == -1`: phía bên kia đã đóng luồng đầu vào; xử lý frame đang dở theo protocol.
- `write(buffers) == 0`: hệ điều hành chưa nhận thêm byte; lưu lại buffer trong hàng đợi outbound, đăng ký `OP_WRITE` khi cần, rồi tiếp tục từ `position` hiện tại.

Tránh giữ `OP_WRITE` được đăng ký liên tục khi không có pending outbound data, vì socket thường sẵn sàng ghi và selector có thể đánh thức liên tục gây lãng phí CPU.

## 9. Scattering/gathering so với nhiều lời gọi read/write

Hai cách có thể sinh cùng chuỗi byte:

~~~java
// A. Nhiều lệnh, sử dụng ByteBuffer riêng.
channel.write(header);
channel.write(body);

// B. Gathering write.
channel.write(new ByteBuffer[] {header, body});
~~~

**Đoạn minh họa** trên giả định buffer nguồn đã `flip()` đúng. Không chạy hai phương án liên tiếp trên **cùng buffer** nếu muốn so sánh, vì phương án A đã dịch `position` đến cuối, khiến B còn 0 byte.

Một API theo mảng buffer thường giúp:

- Tránh bước **tự ghép/copy** header và body thành một mảng lớn trước khi ghi.
- Giữ các thành phần trong buffer riêng, thuận tiện sửa từng thành phần khi tạo thông điệp.
- Có khả năng dùng cơ chế scatter/gather I/O được OS hỗ trợ, giảm overhead trong một số điều kiện.

Nhưng không nên kết luận:

- Mỗi lời gọi scattering/gathering luôn tạo một syscall duy nhất.
- Hiệu năng luôn cao hơn nhiều lời gọi đơn lẻ. Kích thước payload, số buffer, loại channel, OS, kernel, bộ đệm và trạng thái mạng đều ảnh hưởng kết quả.
- Có bảo đảm “all-or-nothing”: các buffer có thể chỉ được đọc/ghi một phần.
- Chỉ dùng gathering write là bên nhận tự tách được header/body. **Receiver phải áp dụng cùng giao thức và quy tắc framing**.

Đo benchmark trên dữ liệu thực tế nếu đang tối ưu hiệu năng; ưu tiên code chính xác và xử lý partial I/O trước.

## 10. Lỗi thường gặp và cách tránh

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Gọi `write(srcs)` rồi mặc định tất cả đã gửi | Mất phần dữ liệu chưa ghi khi đóng/tái sử dụng buffer | Kiểm tra tổng remaining; tiếp tục khi channel sẵn sàng |
| Gọi `read(dsts)` một lần và parse ngay | Header/body thiếu byte, `BufferUnderflowException` hoặc dữ liệu sai | Duy trì state và đọc đủ theo giao thức |
| Quên `flip()` buffer nguồn sau `put(...)` | Gathering write lấy cả phần chưa ghi hợp lệ của buffer | `flip()` trước write |
| Quên `flip()` buffer đích sau read hoàn tất | Parser đọc từ cuối vùng mới nhận | `flip()` buffer đích trước parse |
| Gọi `rewind()` sau partial write | Gửi lặp các byte đã được channel tiêu thụ | Giữ `position`; chỉ viết tiếp phần remaining |
| Kích thước header buffer lớn hơn header thật | Header “ăn” sang body theo quy tắc lấp đầy | Đặt remaining đúng số byte header mong đợi |
| Nhầm `offset,length` với offset/byte-count | Đọc/ghi nhầm buffer trong mảng | Nhớ đó là **chỉ số mảng và số phần tử mảng** |
| Cho phép body size từ mạng quá lớn/âm | Cấp phát khổng lồ, lỗi bộ nhớ, parser sai | Giới hạn frame size trước `allocate` |
| Spin khi non-blocking read/write trả 0 | CPU tăng cao dù không có tiến triển | Dùng readiness/`Selector` và lưu buffer state |
| Gửi dữ liệu qua TCP rồi mong một read nhận đúng một frame | Đọc dở hoặc gộp nhiều frame | Dùng length-prefix/delimiter và state machine |
| Truyền buffer read-only làm đích | Lỗi khi cố nạp byte vào buffer | Dùng buffer có thể ghi cho scattering read |
| Dùng chung mảng buffer cho nhiều luồng không đồng bộ | `position` của mỗi buffer và thứ tự message bị cạnh tranh | Một owner cho session/buffer hoặc đồng bộ/queue rõ ràng |

## 11. Câu hỏi tự kiểm tra

1. Hai buffer đích có `remaining()` lần lượt 4 và 3. Scattering read nhận đúng 5 byte. `position` tăng bao nhiêu? **4 ở buffer đầu, 1 ở buffer sau**; còn 2 byte chờ đọc.
2. Gathering write với hai buffer nguồn có remaining 4 và 3, nhưng `write` trả 2. Byte nào sẽ được ghi lần sau? **Phần còn lại của buffer thứ nhất trước**, rồi đến buffer thứ hai.
3. Dùng `read(buffers, 1, 2)` với mảng bốn buffer, thao tác xét buffer nào? **Index 1 và index 2**, không xét 0 hay 3.
4. `write(new ByteBuffer[]{header, payload})` có đảm bảo một lời gọi truyền đủ frame qua TCP không? **Không.** Vẫn phải xử lý partial write và framing.
5. Khi `channel.read(dsts) == 0` ở non-blocking mode, có nên gọi lặp không chờ? **Không.** Giữ state và chờ readiness.
6. Scattering read tự tách header 4 byte và payload động dài N mà không cần biết N không? **Không.** Buffer chỉ quyết định dựa trên remaining; ứng dụng phải đọc header, giải mã và xác thực N.
7. Sau scattering read vào hai buffer đầy, cần làm gì trước khi `getInt()` từ header? **`header.flip()`** (và `body.flip()` nếu muốn đọc body).
8. Một lần gathering ghi dở; cần gọi `rewind()` vào tất cả source buffer để thử lại không? **Không.** Làm thế sẽ gửi trùng dữ liệu.
9. Gathering write có tự động xóa, đóng hay thay đổi `limit` của buffer không? **Không.** Nó chủ yếu dịch `position` theo số byte thực sự được chuyển.
10. Vì sao scattering/gathering có thể hữu ích mà vẫn cần benchmark? **Có thể giảm bước copy và overhead I/O**, nhưng chi phí và số syscall cụ thể phụ thuộc cách triển khai và môi trường.

## 12. Tham khảo API chính thức

- [Java SE 17 — ScatteringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ScatteringByteChannel.html): contract về thứ tự buffer, kết quả `long` và partial read.
- [Java SE 17 — GatheringByteChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/GatheringByteChannel.html): contract về thứ tự ghi, `position` và partial write.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): API I/O tệp hỗ trợ read/write qua mảng buffer.
- [Java SE 17 — SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): I/O socket, blocking/non-blocking và các thao tác trên buffer.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `flip`, `remaining`, đọc/ghi binary.
