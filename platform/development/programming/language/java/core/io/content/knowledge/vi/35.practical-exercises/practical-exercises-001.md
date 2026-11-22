# Sao chép tệp nhị phân với buffer giới hạn trong Java Core I/O

## 1. Mục tiêu bài thực hành

Bài thực hành này yêu cầu **sao chép chính xác từng byte của một tệp nhị phân** từ đường dẫn nguồn sang đường dẫn đích, nhưng **không đọc toàn bộ tệp vào bộ nhớ**. Tệp có thể nhỏ vài byte hoặc lớn nhiều gigabyte; chương trình chỉ sử dụng một buffer có kích thước cố định, tái sử dụng buffer đó cho đến khi gặp EOF.

Kỹ năng cần nắm:

1. Phân biệt sao chép byte với đọc/ghi văn bản và giải mã charset.
2. Sử dụng `FileChannel`, `ByteBuffer`, `clear()`, `flip()` và `hasRemaining()`.
3. Đọc dữ liệu theo từng khối, nhận đúng giá trị trả về của `read()` và không nhầm `0` với EOF `-1`.
4. **Xử lý partial write**: một lần `write()` không bắt buộc ghi hết vùng dữ liệu đang chờ.
5. Chỉ cần bộ nhớ **O(B)**, trong đó `B` là buffer capacity, không phụ thuộc tuyến tính vào kích thước file.
6. Đóng channel khi hoàn tất hoặc gặp lỗi; tránh ghi đè đích ngoài ý muốn.
7. Kiểm chứng cả **số byte** lẫn **nội dung** của hai tệp.
8. Biết khi nào nên dùng `Files.copy`, stream truyền thống, `FileChannel.transferTo()` hoặc thiết kế ghi file tạm để an toàn hơn.

Bối cảnh: **Java Core - io → Thực hành → Sao chép tệp nhị phân với buffer giới hạn**. Bài có chương trình **Java 17+ hoàn chỉnh**, có lệnh biên dịch/chạy và stdout xác định.

## 2. Vì sao không dùng `Files.readAllBytes()` cho file lớn?

Cách đơn giản sau phù hợp để thử với file nhỏ nhưng không phải giải pháp streaming bộ nhớ giới hạn:

```java
byte[] all = Files.readAllBytes(source);
Files.write(destination, all);
```

Đây là đoạn minh họa, cần import `java.nio.file.Files` và hai biến `Path` thích hợp.

Nhược điểm:

- `readAllBytes()` cố đưa **toàn bộ nội dung file** vào một mảng Java, khiến nhu cầu heap tăng theo kích thước tệp.
- Mảng Java có giới hạn chỉ số `int`, nên không thể là container tùy ý cho file nhiều GiB.
- Dễ gặp `OutOfMemoryError` khi tệp lớn hoặc nhiều thao tác sao chép chạy cùng lúc.
- Mỗi lần thực hiện có thể tạo một mảng rất lớn, tăng áp lực GC và cạnh tranh bộ nhớ với công việc khác.

**Buffer giới hạn** giải quyết vấn đề bằng một vòng lặp:

```text
Nguồn (có thể rất lớn)
  │
  │ đọc tối đa B byte/lượt
  ▼
┌──────────────────────────┐
│ ByteBuffer cố định: B    │
└──────────────────────────┘
  │
  │ ghi hết những byte thực nhận
  ▼
Đích

Lặp tới khi read() trả -1.
```

Ví dụ file 10.257 byte với buffer capacity 4.096 byte có thể cần nhiều lượt đọc. Buffer luôn chỉ có sức chứa 4.096 byte. Không được giả định số lượt thực tế bằng đúng 3, vì `read` có thể trả ít hơn capacity; chương trình phải xử lý mọi lượt đọc hợp lệ.

**Kết luận:** không cần tạo mảng bằng kích thước file, không cần giữ tất cả byte trong RAM, và không cần biết trước file size để hoàn thành bản sao tuần tự.

## 3. Sao chép nhị phân khác sao chép văn bản

**Sao chép nhị phân** phải giữ nguyên mọi byte, bao gồm:

- Byte `0x00` (NUL);
- Byte `0xFF` (Java `byte` biểu diễn là `-1` nếu xem như số có dấu);
- Byte xuống dòng `0x0A`, carriage return `0x0D`;
- Mọi chuỗi byte không phải UTF-8 hợp lệ;
- Header, compressed data, checksum, trailing zero hoặc binary metadata.

Không làm thế này cho dữ liệu nhị phân:

```java
String text = Files.readString(source);
Files.writeString(destination, text);
```

Lý do: việc **giải mã rồi mã hóa lại** dựa trên charset có thể không định nghĩa được đối với dữ liệu bất kỳ, chuyển đổi byte hoặc ném lỗi. Ngoài ra, các thao tác theo dòng có thể thay đổi newline/terminator. Tệp `.png`, `.zip`, `.pdf`, `.class`, `.dat`, file thực thi và tệp nhị phân tự định nghĩa không cần chuyển qua `String`.

**Quy tắc:** lấy byte từ nguồn rồi ghi đúng byte sang đích. Nếu yêu cầu là **biến đổi encoding**, đó là một bài toán khác và kết quả không còn là bản sao byte-đúng-byte.

## 4. Các thành phần Java NIO cần biết

| Thành phần | Vai trò | Điều phải nhớ |
| --- | --- | --- |
| `Path` | Đường dẫn tệp | Phân biệt source và destination; kiểm tra chính sách ghi đè |
| `FileChannel` | Channel có thể đọc/ghi byte và quản lý vị trí trong tệp | `read`/`write` trả số byte thực sự chuyển |
| `ByteBuffer` | Vùng byte cố định cùng trạng thái `position/limit/capacity` | Không tự hiểu đâu là “byte mới” nếu dùng sai trạng thái |
| `buffer.clear()` | Chuẩn bị buffer cho lượt **ghi từ channel vào buffer** | Không xóa byte cũ trong storage |
| `buffer.flip()` | Chuẩn bị buffer cho lượt **đọc từ buffer ra channel đích** | Đặt `limit` bằng số byte đã nhận |
| `buffer.hasRemaining()` | Có byte chưa được channel đích lấy hay không | Bắt buộc xét partial write |
| `StandardOpenOption.READ` | Mở nguồn chỉ để đọc | Không cần quyền sửa nguồn |
| `StandardOpenOption.CREATE_NEW` | Tạo đích mới, thất bại nếu tên đã tồn tại | Tránh ghi đè ngoài ý muốn |
| `StandardOpenOption.WRITE` | Mở đích để ghi | Đi cùng chính sách tạo đích |

**Cảnh báo quan trọng:** `FileChannel.read(ByteBuffer)` có thể trả số byte dương nhỏ hơn `buffer.remaining()` ban đầu. `FileChannel.write(ByteBuffer)` cũng có thể lấy ít byte hơn số còn lại. Các vòng lặp phải dựa vào **kết quả thực** và trạng thái buffer, không dựa vào kỳ vọng một lần đọc/ghi sẽ hoàn tất cả khối.

## 5. Luồng trạng thái ByteBuffer trong một lượt

Giả sử buffer có capacity 8 và lần này chỉ đọc được 3 byte `A`, `B`, `C`.

```text
Mới cấp / sau clear():
  position=0, limit=8, capacity=8
  [ _ _ _ _ _ _ _ _ ]

Sau source.read(buffer) trả 3:
  position=3, limit=8
  [ A B C ? ? ? ? ? ]
        ^
        position

Sau buffer.flip():
  position=0, limit=3
  [ A B C | các byte ngoài limit không hợp lệ cho lượt này ]

Trong khi destination.write(buffer):
  Có thể ghi 1 byte, rồi 2 byte;
  hoặc ghi cả 3 byte trong một lần.
  Khi hết: position=3, limit=3, hasRemaining()=false.

Lượt kế:
  clear() → position=0, limit=8;
  buffer được tái sử dụng, không cấp lại.
```

Không gọi `clear()` khi buffer còn byte chưa được đích ghi. Nếu làm vậy, bạn **mất trạng thái phần dữ liệu còn lại**; ở lượt sau nguồn có thể ghi đè byte chưa chép xong.

Ngược lại, không quên `clear()` trước lượt đọc nguồn kế. Nếu buffer vẫn ở `position==limit`, nó có `remaining()==0`, làm việc đọc không tiến triển mặc dù nguồn có thể còn dữ liệu.

## 6. Thuật toán chuẩn: đọc → flip → ghi hết → lặp

```text
buffer = allocate(fixedCapacity)
totalCopied = 0

mở source READ
mở destination CREATE_NEW + WRITE

lặp:
    buffer.clear()
    n = source.read(buffer)

    nếu n == -1:
        break                  # EOF của file nguồn
    nếu n == 0:
        áp dụng chính sách no-progress
        không coi là EOF

    buffer.flip()              # Chỉ n byte mới là hợp lệ
    trong khi buffer.hasRemaining():
        written = destination.write(buffer)
        nếu written == 0:
            áp dụng chính sách no-progress
            không bỏ byte chưa ghi

    totalCopied += n

đóng cả hai channel
kiểm tra kích thước và nội dung khi cần
```

### 6.1. Vì sao phải lặp `hasRemaining()`?

`destination.write(buffer)` cập nhật `buffer.position()` bằng **đúng số byte đã ghi**. Nếu đích chỉ nhận một phần, phần dư vẫn nằm trong buffer và có thể ghi tiếp. Điều kiện `hasRemaining()` giữ cho vòng lặp chạy đến khi **toàn bộ khối đã được chuyển**.

Mã sai:

```java
buffer.flip();
destination.write(buffer); // Có thể ghi thiếu!
buffer.clear();            // Phần chưa ghi đã mất trạng thái.
```

Mã đúng:

```java
buffer.flip();
while (buffer.hasRemaining()) {
    int written = destination.write(buffer);
    if (written == 0) {
        throw new IOException("No progress while writing");
    }
}
```

Đây là đoạn minh họa trong một phương thức, giả định đã có `ByteBuffer buffer` và `FileChannel destination`, cùng import `java.io.IOException`. Với `FileChannel` ghi ra regular file trong tình huống phổ biến, `0` khi còn byte là bất thường; bản thực hành chọn **báo lỗi** thay vì busy-spin vô hạn. Với socket non-blocking, `write()==0` có thể bình thường, và phải dùng `Selector`/`OP_WRITE` hay cơ chế chờ phù hợp thay vì ném lỗi mặc định.

### 6.2. Vì sao `read()==0` khác EOF?

- `n > 0`: nguồn đã chuyển **n byte**, dù n nhỏ hơn capacity.
- `n == 0`: lượt gọi chưa chuyển byte, **không khẳng định nguồn đã hết**.
- `n == -1`: nguồn báo **end-of-stream**.
- Exception: lỗi I/O thực tế, không được ngầm coi là EOF.

Trong bản thực hành với `FileChannel` và buffer dung lượng dương luôn được `clear()`, `read()==0` sẽ được coi là **no-progress error** để tránh vòng lặp tiêu thụ CPU. Nếu triển khai trên `SocketChannel` non-blocking, chính sách này cần thay đổi: `0` có thể là tình huống chờ dữ liệu hoàn toàn hợp lệ.

## 7. Chương trình Java 17+ hoàn chỉnh: chép file nhị phân bằng 4 KiB

Ví dụ dưới đây:

1. Tạo một thư mục tạm.
2. Tạo file nguồn **10.257 byte** với mẫu nhị phân xác định, có nhiều giá trị bao gồm `0x00` và `0xFF`.
3. Sao chép bằng **một `ByteBuffer` 4.096 byte** được tái sử dụng.
4. Mở file đích bằng `CREATE_NEW`, để không âm thầm ghi đè một file có sẵn.
5. Xác minh `Files.size()` và `Files.mismatch()` sau khi copy xong.
6. In kết quả không phụ thuộc vào tên file tạm.
7. Đóng stream/channel bằng `try-with-resources` và dọn file tạm trong `finally`.

Tạo tệp **`BoundedBinaryCopyDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class BoundedBinaryCopyDemo {
    private static final int BUFFER_BYTES = 4096;
    private static final int FILE_BYTES = 10_257;
    private static final int MAX_BUFFER_BYTES = 1024 * 1024;

    static void createFixture(Path source) throws IOException {
        byte[] block = new byte[257];
        for (int i = 0; i < block.length; i++) {
            block[i] = (byte) ((i * 31 + 7) & 0xFF);
        }

        try (OutputStream out = Files.newOutputStream(
                source, StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            int remaining = FILE_BYTES;
            while (remaining > 0) {
                int n = Math.min(remaining, block.length);
                out.write(block, 0, n);
                remaining -= n;
            }
        }
    }

    static long copy(Path source, Path destination, int capacity)
            throws IOException {

        if (capacity <= 0 || capacity > MAX_BUFFER_BYTES) {
            throw new IllegalArgumentException(
                    "Buffer must be between 1 and " + MAX_BUFFER_BYTES);
        }
        if (!Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Source is not a regular file");
        }

        ByteBuffer buffer = ByteBuffer.allocate(capacity);
        long totalCopied = 0L;

        try (FileChannel in = FileChannel.open(
                     source, StandardOpenOption.READ);
             FileChannel out = FileChannel.open(
                     destination, StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {

            while (true) {
                buffer.clear();
                int n = in.read(buffer);

                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    throw new IOException(
                            "Read made no progress");
                }

                buffer.flip();
                while (buffer.hasRemaining()) {
                    int written = out.write(buffer);
                    if (written == 0) {
                        throw new IOException(
                                "Write made no progress");
                    }
                }
                totalCopied += n;
            }
        }
        return totalCopied;
    }

    public static void main(String[] args) throws IOException {
        Path directory =
                Files.createTempDirectory("bounded-binary-copy-");
        Path source = directory.resolve("source.bin");
        Path destination = directory.resolve("destination.bin");

        try {
            createFixture(source);

            long copied = copy(source, destination, BUFFER_BYTES);
            boolean identical =
                    Files.mismatch(source, destination) == -1L;

            System.out.println("Source bytes: " + Files.size(source));
            System.out.println("Copied bytes: " + copied);
            System.out.println("Target bytes: "
                    + Files.size(destination));
            System.out.println("Buffer capacity: " + BUFFER_BYTES);
            System.out.println("Content identical: " + identical);
        } finally {
            Files.deleteIfExists(destination);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac BoundedBinaryCopyDemo.java
java BoundedBinaryCopyDemo
```

Stdout dự kiến khi filesystem hỗ trợ tạo/đọc/ghi và xóa tệp tạm:

```text
Source bytes: 10257
Copied bytes: 10257
Target bytes: 10257
Buffer capacity: 4096
Content identical: true
```

### 7.1. Giải thích chương trình theo thứ tự

**A. Dữ liệu nguồn là nhị phân thực sự.** Vòng khởi tạo `block` tính `(i * 31 + 7) & 0xFF`, rồi ép sang `byte`. Với các giá trị khác nhau, block có thể chứa byte 0, byte 255 và nhiều giá trị không có nghĩa như ký tự văn bản. `createFixture()` ghi đủ 10.257 byte, chỉ dùng mảng 257 byte và không cấp mảng bằng toàn bộ file.

**B. Kích thước buffer được kiểm soát.** Hàm `copy` nhận `capacity`, kiểm tra giới hạn dương và tối đa 1 MiB, sau đó tạo **một** `ByteBuffer.allocate(capacity)` trước vòng đọc. Ở lời gọi demo, capacity đúng 4.096.

**C. Nguồn được mở chỉ đọc.** `FileChannel.open(source, READ)` không yêu cầu quyền sửa nội dung nguồn. Ví dụ kiểm tra `isRegularFile(..., NOFOLLOW_LINKS)` để từ chối source symbolic link ở giai đoạn kiểm tra ban đầu. Tuy vậy, đây **không phải một cơ chế chống TOCTOU tuyệt đối** nếu tác nhân khác có thể thay đổi path giữa lúc kiểm tra và lúc mở file.

**D. Đích được tạo mới.** `CREATE_NEW` từ chối tên file đích đã tồn tại (kể cả nếu đó là symbolic link theo quy tắc API). Demo không ghi đè một file cũ. Khi gặp lỗi sau khi tạo đích, **có thể đã tồn tại file đích sao chép dở**; khối `finally` trong demo chủ động xóa file tạm. Ứng dụng thật phải có chính sách cleanup riêng.

**E. `n` không phải giá trị byte.** `in.read(buffer)` trả số byte thực nhận. Nếu nhận byte `0xFF` hay `0x00`, kết quả `n` vẫn là **số lượng**, không phải `-1` hoặc `0` tương ứng nội dung.

**F. `flip()` rồi ghi hết.** `buffer.flip()` giới hạn vùng dữ liệu hợp lệ về đúng `n` byte. `while (buffer.hasRemaining())` xử lý mọi trường hợp đích chỉ ghi một phần. Nếu lần ghi đầu lấy 1 KiB của khối 4 KiB, ba KiB còn lại vẫn được giữ cho lượt tiếp theo.

**G. Dùng `long` cho tổng.** `totalCopied` là `long` nên không bị giới hạn ở 2 GiB như `int`; đây là cách đếm an toàn cho file lớn. `capacity` vẫn là `int` vì API `ByteBuffer` dùng capacity kiểu `int`.

**H. Kiểm tra kết quả.** `Files.size()` phản ánh kích thước file, còn `Files.mismatch(source,destination)` trả `-1L` khi không tìm thấy byte khác nhau; nếu khác, nó trả vị trí byte đầu tiên không khớp. So sánh kích thước đơn thuần **không đủ** khẳng định nội dung giống nhau. `Files.mismatch()` có từ Java 12 và dùng được với Java 17.

**I. Đóng tài nguyên.** Hai `FileChannel` được đóng kể cả khi `read` hoặc `write` ném `IOException`. Sau khi đóng, demo mới thực hiện kiểm tra và xóa dữ liệu tạm. Lưu ý việc xóa cũng có thể ném `IOException` tùy quyền truy cập và trạng thái filesystem.

## 8. Bất biến để tự chứng minh thuật toán không mất byte

Trong một lượt đọc, gọi:

- `p`: tổng số byte nguồn đã đọc trước lượt;
- `n`: số byte trả về bởi `in.read(buffer)`;
- `w`: tổng số byte thực sự đích đã ghi từ buffer ở lượt này.

Trước khi gọi `flip()`, `buffer.position()` đã tăng `n`. Sau `flip()`, `limit=n`, `position=0`.

Khi vòng `while (hasRemaining())` kết thúc bình thường:

```text
w == n
buffer.position() == buffer.limit() == n
totalCopied_new == p + n
```

Do đó, mỗi byte của khối đọc được chuyển sang đích **đúng một lần** theo vị trí của buffer, miễn là không có tác nhân ngoài cùng can thiệp vào channel/file. Sau đó vòng lặp đặt lại buffer để nhận byte nguồn tiếp theo.

Khi EOF:

```text
in.read(buffer) == -1
→ không có byte mới
→ không cần flip/ghi thêm
→ kết thúc vòng đọc
```

Nếu file nguồn chứa `N` byte và không thay đổi trong lúc copy, khi thành công thì `totalCopied == N`, file đích chứa byte theo đúng thứ tự và `Files.mismatch(source,dest) == -1L`.

**Không được suy luận** rằng `n < capacity` là EOF. Ví dụ `n=1` khi capacity=4096 vẫn là một lượt đọc dữ liệu thành công; tiếp tục cho tới `-1`.

## 9. Tại sao `CREATE_NEW` quan trọng?

Mặc định nếu sử dụng một số API mở ghi với tùy chọn khác, ứng dụng có thể tạo/ghi đè/truncate file đích, gây mất dữ liệu.

So sánh chính sách:

| Tùy chọn mở đích | Hành vi có ý nghĩa |
| --- | --- |
| `CREATE_NEW, WRITE` | Chỉ tạo file mới; tên đã tồn tại thì lỗi, tránh ghi đè ngoài ý muốn |
| `CREATE, WRITE, TRUNCATE_EXISTING` | Có thể tạo hoặc xóa nội dung file cũ; chỉ dùng khi ứng dụng có quyền overwrite rõ ràng |
| `APPEND, WRITE` | Thêm dữ liệu vào cuối file; **không phù hợp** với yêu cầu sao chép thay thế toàn bộ |
| `READ` | Chỉ đọc, không dùng cho output |
| `SYNC`/`DSYNC` hoặc `force()` | Liên quan tới mức độ đồng bộ bền vững, không thay thế kiểm tra đúng nội dung |

**Không sao chép vào chính file nguồn.** Nếu mở nguồn trước rồi mở đích với `TRUNCATE_EXISTING` nhưng thực chất cùng file, việc truncate có thể phá dữ liệu nguồn. Trong demo, `CREATE_NEW` cùng đường dẫn đích mới giúp tránh trường hợp đơn giản này.

Ở ứng dụng thực, nếu nguồn và đích có thể trùng qua hard link, symbolic link hoặc đường dẫn tương đương, hãy dùng `Files.isSameFile()` khi cả hai đã tồn tại và thiết kế chính sách kiểm soát race. Kiểm tra trước thao tác không đủ mạnh nếu một tác nhân khác có thể thay đổi cây thư mục đồng thời.

## 10. Phiên bản `InputStream` / `OutputStream` dùng mảng `byte[]`

Không bắt buộc dùng NIO. Nếu mục tiêu chỉ là sao chép byte với buffer giới hạn, API stream có thể dễ đọc hơn:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

static long copyWithStreams(
        Path source, Path destination, int bufferBytes)
        throws IOException {

    if (bufferBytes <= 0 || bufferBytes > 1024 * 1024) {
        throw new IllegalArgumentException("Invalid buffer size");
    }

    byte[] buffer = new byte[bufferBytes];
    long total = 0L;

    try (InputStream in = Files.newInputStream(source);
         OutputStream out = Files.newOutputStream(
                 destination, StandardOpenOption.CREATE_NEW,
                 StandardOpenOption.WRITE)) {

        int n;
        while ((n = in.read(buffer)) != -1) {
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            out.write(buffer, 0, n);
            total += n;
        }
    }
    return total;
}
```

Đây là **phương thức để đặt trong một class**, không phải chương trình độc lập có `main`. Nó có cùng đặc tính cấp phát **một `byte[]` cố định**, dùng `long` để đếm byte, mở đích mới và tự đóng streams.

**Khác biệt quan trọng:** `OutputStream.write(byte[], 0, n)` có hợp đồng ghi đúng `n` byte hoặc ném exception; API không trả số lượng partial write như `FileChannel.write(ByteBuffer)`. Vì vậy không cần vòng `hasRemaining()` ở tầng `OutputStream`, nhưng vẫn cần xử lý `IOException`, hỏng dữ liệu đích một phần và flush/close đúng thời điểm.

Nếu chỉ cần chuyển byte, `InputStream`/`OutputStream` là lựa chọn hợp lý; dùng `FileChannel` để thực hành sâu cơ chế `ByteBuffer`/NIO, truy cập vị trí hoặc tối ưu đặc thù khi được đo.

## 11. `Files.copy()` và vì sao vẫn học cách copy có buffer

Java đã cung cấp:

```java
long copied = Files.copy(
        sourceInputStream, destinationPath);
```

Trong đó `sourceInputStream` là một `InputStream` đang mở và `destinationPath` là `Path`. Cách này thuận tiện cho nhiều use case. Với `Files.copy(Path,Path,CopyOption...)`, API còn hỗ trợ copy tệp trực tiếp, quy tắc xử lý symbolic link và lựa chọn sao chép thuộc tính tùy provider.

Nhưng trong **bài thực hành buffer giới hạn**, ta tự quản lý vòng đọc/ghi vì muốn:

- Chỉ định kích thước buffer của code ứng dụng;
- Đếm byte và giám sát tiến độ theo từng khối;
- Thêm checksum/hash trong lúc copy;
- Áp quota đọc/ghi, deadline, cancellation hoặc rate limit;
- Xử lý partial writes và hiểu `ByteBuffer` state;
- So sánh hiệu năng các capacity khác nhau có kiểm chứng.

Đừng hiểu `Files.copy()` là API tốn RAM theo kích thước file; các triển khai có thể dùng streaming hoặc tối ưu riêng. Khi **không cần kiểm soát loop**, thường ưu tiên API thư viện chuẩn thay vì tự viết một bản copy chưa được kiểm thử.

## 12. Tệp lớn trên 2 GiB: tránh giới hạn `int`

Một `ByteBuffer` có `capacity()` kiểu `int`, nhưng file position và `FileChannel.size()` dùng `long`. Không cần một buffer tương đương file size.

**Cách sai:**

```java
long size = Files.size(source);
ByteBuffer all = ByteBuffer.allocate((int) size);
```

Đây là snippet **cố ý sai**, vì `(int) size` có thể overflow và ngay cả một `int` dương rất lớn cũng có thể vượt ngân sách heap. File 5 GiB không thể nhét vào một `ByteBuffer` duy nhất có capacity 5 GiB.

**Cách đúng trong bài thực hành:**

```java
final int bufferBytes = 64 * 1024;
ByteBuffer buffer = ByteBuffer.allocate(bufferBytes);
long copied = 0L;

// Mỗi lượt đọc/ghi xử lý tối đa bufferBytes;
// copied tăng theo n thực tế và vẫn là long.
```

Tệp rỗng, tệp nhỏ hơn buffer, tệp không chia hết cho buffer hoặc tệp hàng chục GiB đều đi qua **cùng logic**. File lớn làm tăng số vòng lặp/thời gian, không khiến buffer phình theo file size.

Cũng đừng dùng `while (copied < Files.size(source))` làm điều kiện dừng duy nhất: kích thước file có thể thay đổi khi đang đọc, và `read()==-1` mới là dấu EOF của channel hiện tại. Nếu yêu cầu “snapshot byte tại thời điểm bắt đầu”, phải thiết kế chính sách đồng bộ/immutable file riêng.

## 13. Chọn buffer size theo mục tiêu và phép đo

Các ứng viên khởi đầu thường là **4, 16, 64, 256 KiB hoặc 1 MiB**; nhưng không có kích thước tối ưu cố định cho mọi file và hệ thống.

| Kích thước | Ưu điểm tiềm năng | Chi phí cần cân nhắc |
| --- | --- | --- |
| 4 KiB | Nhỏ, dễ thực hành, ít RAM per job | Nhiều lượt I/O hơn |
| 16–64 KiB | Thường là vùng thử hợp lý cho copy tuần tự | Cần benchmark workload thật |
| 256 KiB | Có thể giảm số lần gọi so với buffer nhỏ | Tăng bộ nhớ/connection |
| 1 MiB | Hữu ích nếu throughput còn tăng trong workload cụ thể | Không chắc nhanh hơn; tăng heap/direct memory |

Ví dụ 1.000 tác vụ cùng giữ buffer 64 KiB: tổng vùng buffer khoảng **62,5 MiB**. Nếu 1.000 buffer đều 1 MiB thì là khoảng **1.000 MiB** (gần 0,98 GiB), chưa tính object, socket, file descriptor và queue.

Đo:

1. Thời gian copy tệp thật (không chỉ thời gian đọc source);
2. MiB/s end-to-end;
3. Memory và GC khi nhiều tác vụ cùng chạy;
4. Heap `allocate` so với `allocateDirect`, nếu đang cân nhắc;
5. Warm-up, OS page cache, tải thiết bị, độ trễ p95/p99;
6. Kết quả đúng theo `Files.mismatch()` hay checksum phù hợp.

Nếu một buffer 64 KiB đạt gần bằng throughput buffer 1 MiB trong sai số, cấu hình nhỏ hơn có thể có lợi cho bộ nhớ. **Không tự kết luận 1 MiB tốt hơn chỉ vì nó lớn hơn.**

## 14. Heap và direct ByteBuffer có làm thay đổi tính đúng?

Dòng trong chương trình:

```java
ByteBuffer buffer = ByteBuffer.allocate(capacity);
```

có thể được thử thay bằng:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(capacity);
```

Cả hai vẫn hỗ trợ `clear()`, `flip()`, `hasRemaining()`, `get/put` và `FileChannel.read/write` theo giao thức buffer. Nếu thao tác đúng, **nội dung sao chép giống nhau**.

Điểm khác:

- Heap buffer có thể cấp phát nhanh hơn, dùng bộ nhớ heap.
- Direct buffer thường dùng vùng nhớ ngoài heap; JVM có thể tối ưu native I/O, nhưng không hứa nhanh hơn trong mọi workload.
- Direct allocation/deallocation thường tốn chi phí hơn, nên đặc biệt cần tái sử dụng và kiểm soát số buffer đồng thời.
- `buffer.clear()` **không xóa dữ liệu nhạy cảm trong vùng nhớ** và không giải phóng direct memory.
- Với direct buffer, không được giả định gọi được `buffer.array()`.

Chọn kiểu buffer bằng phép đo thực tế chứ không phải một nhận định “direct luôn nhanh hơn”.

## 15. Kiểm tra byte-đúng-byte bằng cách nào?

### 15.1. So sánh kích thước

```java
boolean sameSize = Files.size(source) == Files.size(destination);
```

Điều này hữu ích để phát hiện chép thiếu hoặc chép thừa, nhưng **chưa đủ**: hai file cùng số byte có thể khác nội dung.

### 15.2. `Files.mismatch()` (Java 12+)

```java
long firstMismatch = Files.mismatch(source, destination);

if (firstMismatch == -1L) {
    System.out.println("Identical bytes");
} else {
    System.out.println("Different at offset " + firstMismatch);
}
```

Theo hợp đồng API, `-1L` nghĩa là không có byte nào khác (và kích thước phù hợp). Nếu khác, hàm trả vị trí byte khác đầu tiên hoặc vị trí bằng kích thước file ngắn hơn khi một file là prefix của file kia.

Đây là **snippet để đặt trong phương thức** sau khi cả hai file đã đóng và ổn định. `Files.mismatch()` không phải một thao tác atomic trước thay đổi đồng thời: nếu có process khác sửa file giữa lúc so sánh, kết quả không đại diện cho một snapshot bất biến.

### 15.3. Hash để đối chiếu file lớn hoặc lưu kiểm toán

Có thể tính SHA-256 bằng `MessageDigest` khi đọc từng block. Hash giúp báo kết quả kiểm chứng độc lập với một lần so sánh byte đối byte, nhưng:

- Hash **không thay thế** một giao thức xác thực nguồn khi file đến từ bên không tin cậy, trừ khi giá trị hash kỳ vọng được cung cấp qua kênh tin cậy.
- Nếu tính digest lúc copy, hãy chú ý checksum nguồn vừa đọc và checksum đích sau ghi, hoặc đối chiếu kết quả bằng `Files.mismatch()` để phát hiện lỗi đường ghi.
- Không dùng CRC32 như chữ ký chống sửa đổi có chủ ý.

Để kiểm thử demo hoặc một file local ổn định, `Files.mismatch()` là công cụ dễ hiểu, trực tiếp và có trong JDK 17.

## 16. Xử lý lỗi: file đích đang sao chép dở

Nếu chương trình chép được 8 MiB rồi gặp hết dung lượng ổ đĩa, mất quyền ghi hoặc bị interrupt, **file đích có thể chứa 8 MiB dữ liệu chưa hoàn chỉnh**. `try-with-resources` đóng channel nhưng **không tự xóa file đích bị chép dở**.

Có ba chính sách phổ biến:

1. **Xóa file đích khi thất bại:** phù hợp khi ta vừa tạo file mới và chắc chắn ứng dụng sở hữu nó.
2. **Ghi vào tệp tạm trong cùng thư mục rồi chuyển tên sau khi thành công:** tránh công bố file đích dở dưới tên chính thức; cần lưu ý `ATOMIC_MOVE` có thể không được provider hỗ trợ.
3. **Giữ phần đã chép để resume:** phải có metadata tiến độ, kiểm tra source unchanged, offset, checksum và xử lý crash consistency. Không thể chỉ nhìn file đích đã có rồi mặc định resume an toàn.

### 16.1. Tại sao dùng file tạm để publish?

Sơ đồ:

```text
source.bin
   |
   | bounded-buffer copy
   v
destination.bin.part-<random>  (tệp tạm, cùng filesystem)
   |
   | verify bytes/size; close channels
   v
Files.move(temp, destination, ATOMIC_MOVE nếu hỗ trợ)
```

Nếu copy thất bại, ứng dụng xóa temp và tên đích chính thức chưa bị tạo do quy trình này. Nếu copy thành công, ứng dụng chỉ **công bố** file sau khi verify.

**Chú ý:** `ATOMIC_MOVE` có thể ném `AtomicMoveNotSupportedException`. Hành vi đối với target đã tồn tại khi dùng `ATOMIC_MOVE` có khác biệt theo provider; không dựa vào việc bỏ `REPLACE_EXISTING` như một bảo đảm tuyệt đối chống overwrite trong mọi tình huống. Cần quyết định policy đích tồn tại và kiểm tra/đồng bộ race phù hợp. Muốn bảo đảm dữ liệu đã bền trên thiết bị sau mất điện còn cần cân nhắc `force()`/đồng bộ thư mục theo filesystem/provider.

Cách copy vào temp nên có quota đĩa, cleanup, rollback và logging rõ ràng. Một thao tác `Files.move()` tự nó không biến mọi bước kiểm tra/copy thành giao dịch atomic toàn phần.

## 17. Tên file, symbolic link và các trường hợp đồng thời

Với đường dẫn do người dùng cung cấp:

- Không đưa source/destination tùy ý vào thư mục không được phép; giới hạn root, canonicalization và quyền truy cập theo threat model.
- `Files.isRegularFile(path, NOFOLLOW_LINKS)` chỉ kiểm tra ở một thời điểm. Nếu tác nhân khác thay đường dẫn thành symlink giữa check và open, đó là **TOCTOU**; cần cơ chế mở an toàn hơn trên nền tảng nếu dữ liệu không tin cậy.
- `CREATE_NEW` hữu ích để bảo vệ file đích đã tồn tại; vẫn cần chính sách dọn file mới tạo nếu thất bại.
- Tránh nguồn và đích chỉ là hai tên khác nhau của **cùng inode/file**; khi hai file đã tồn tại có thể dùng `Files.isSameFile()`.
- Nếu nguồn đang được tiến trình khác sửa/truncate trong khi copy, bản sao có thể không tương ứng một snapshot nhất quán. `Files.size()` ở một thời điểm không giải quyết được điều đó.
- `FileLock` có thể giúp phối hợp trong một hệ thống nhưng tính bắt buộc/advisory và hỗ trợ trên filesystem khác nhau. Không giả định nó thay thế toàn bộ cơ chế versioning hoặc quiescence.

Với bài thực hành tại chỗ, dùng **thư mục tạm riêng** như demo. Trong dịch vụ thực cần quyết định rõ ai được phép tạo/xóa nguồn và đích, và khi nào dữ liệu được coi là immutable.

## 18. Các trường hợp biên cần kiểm thử

| Tình huống | Hành vi mong đợi |
| --- | --- |
| File nguồn rỗng | `read` trả `-1`; tạo file đích rỗng; `copied=0` |
| File 1 byte | Chép đúng một byte |
| File nhỏ hơn buffer | Đọc một hoặc nhiều lượt hợp lệ rồi EOF, không chép byte rác |
| File có kích thước đúng bội của buffer | Không thêm khối rỗng; dừng ở EOF |
| File kích thước không chia hết cho buffer | Khối cuối ngắn hơn, vẫn ghi đúng số byte |
| File có `0x00`, `0xFF`, dữ liệu UTF-8 không hợp lệ | Chép nguyên byte không decode |
| Tệp lớn hơn 2 GiB | `long totalCopied`; không allocate theo file size |
| Đích đã tồn tại | `CREATE_NEW` báo lỗi thay vì ghi đè |
| Nguồn không tồn tại | Lỗi I/O/kiểm tra nguồn, không tạo bản sao thành công |
| Hết đĩa giữa chừng | Lỗi ghi; cần cleanup file đích dở |
| Một lần write ghi ít hơn buffer | Vòng `hasRemaining()` hoàn tất phần dư |
| Source bị thay đổi trong lúc copy | Không có snapshot guarantee; cần chính sách ứng dụng |
| Thiếu quyền đọc/ghi | `IOException` hoặc lỗi quyền, đóng tài nguyên |
| Direct vs heap | Copy cùng nội dung nếu code đúng, hiệu năng cần đo |

### 18.1. Tự thêm bài test đổi một byte

Sau khi copy xong, nếu cố tình sửa byte đầu ở file đích:

```java
try (FileChannel out = FileChannel.open(
        destination, StandardOpenOption.WRITE)) {
    ByteBuffer one = ByteBuffer.wrap(new byte[] {(byte) 123});
    out.write(one, 0L);
}

long mismatch = Files.mismatch(source, destination);
```

Đây là **snippet thử lỗi**, không nằm trong chương trình demo chính; giả sử byte đầu của nguồn không phải 123, và đã import API tương ứng. Kết quả `mismatch` sẽ là vị trí byte khác đầu tiên (với fixture trong demo, byte đầu nguồn là `7`, nên `mismatch==0L`). Sau test này hai file **không còn giống nhau**; không dùng kết quả sau sửa để phủ nhận chức năng copy gốc.

## 19. Những lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| `readAllBytes()` cho file nhiều GiB | Tốn heap hoặc vượt giới hạn mảng | Buffer cố định, streaming |
| `new String(bytes)` cho file nhị phân | Sai/không biểu diễn được dữ liệu | Copy byte trực tiếp |
| `new byte[(int) Files.size(path)]` | Tràn `int`, OOM | Capacity nhỏ và tổng kiểu `long` |
| `buffer.flip()` bị quên | Ghi 0 byte hoặc đọc phạm vi sai | `clear` → `read` → `flip` → `write` |
| Chỉ gọi `write` một lần | Có thể mất phần chưa ghi | `while (buffer.hasRemaining())` |
| `buffer.clear()` khi đích chưa ghi hết | Mất trạng thái byte còn tồn | Chỉ clear ở lượt source read kế |
| Coi `read()==0` là EOF | Dừng quá sớm trên channel nonblocking | `-1` mới là EOF |
| Coi `read() < capacity` là EOF | Bỏ sót dữ liệu | Lặp tới `-1` |
| Chỉ kiểm tra kích thước đích | Nội dung sai vẫn có thể cùng size | `Files.mismatch` hoặc hash |
| Đích mở với `TRUNCATE_EXISTING` ngoài ý muốn | Mất nội dung file cũ | `CREATE_NEW`/chính sách overwrite rõ |
| Không đóng channel khi lỗi | Rò file descriptors, dữ liệu chưa flush | `try-with-resources` |
| Không dọn file copy dở | File đích hỏng bị dùng nhầm | Temp/publish hoặc cleanup |
| Nguồn/đích là cùng file | Có thể tự phá nội dung | Kiểm tra path/identity và ownership |
| Tạo buffer mới trong mỗi vòng đọc | Allocation, GC/native overhead | Tái sử dụng một buffer |
| Khẳng định buffer 1 MiB luôn nhanh nhất | Không dựa trên phép đo | Benchmark trên workload thực |
| Sao chép file đang bị writer khác thay đổi | Kết quả không phải snapshot chắc chắn | Lock/version/immutable input theo policy |

## 20. Bài tập thực hành và lời giải

**Câu 1.** Tại sao không thể dùng `BufferedReader.readLine()` để sao chép `.png` hoặc `.zip`?

**Đáp án:** Nó thao tác văn bản và charset, đồng thời tách dòng; dữ liệu nhị phân tùy ý không bảo toàn byte khi decode/encode. Dùng byte stream hoặc byte channel.

**Câu 2.** Source 10.257 byte, buffer capacity 4.096. Khối cuối nếu các lần trước đều lấp đầy là bao nhiêu byte?

**Đáp án:** `10257 - 2 * 4096 = 2065` byte. Nhưng thực tế các lượt trước **không được bảo đảm** luôn đầy buffer, nên thuật toán dựa vào `read()` trả số byte thực, không dựa vào số khối dự kiến.

**Câu 3.** Sau `read` trả 3 vào buffer capacity 8, `flip()` cho giá trị `position`, `limit` bao nhiêu?

**Đáp án:** `position=0`, `limit=3`, nên chỉ ba byte mới được dùng cho lượt ghi.

**Câu 4.** Sau `write()` lần đầu, `buffer.hasRemaining()==true`. Có thể `clear()` luôn không?

**Đáp án:** Không. Cần tiếp tục ghi phần còn lại; `clear()` sẽ xóa ranh giới dữ liệu chưa ghi.

**Câu 5.** Byte `0xFF` có làm `FileChannel.read(ByteBuffer)` trả `-1` không?

**Đáp án:** Không. `read` trả số byte đã chuyển; `-1` là EOF chứ không phải một byte dữ liệu.

**Câu 6.** Vì sao `Files.size(src)==Files.size(dst)` chưa đủ chứng minh copy đúng?

**Đáp án:** Hai file cùng độ dài có thể có byte khác nhau. Kiểm tra bằng `Files.mismatch(src,dst)` (trả `-1L` nếu trùng) hoặc so hash khi phù hợp.

**Câu 7.** Với file 5 GiB, `long totalCopied` và `ByteBuffer.allocate(65536)` có dùng được không?

**Đáp án:** Có, nếu hệ thống tệp/tài nguyên cho phép. Mỗi vòng xử lý 64 KiB tối đa; tổng byte đếm bằng `long`, không phải `int`.

**Câu 8.** `CREATE_NEW` giúp giải quyết gì?

**Đáp án:** Không âm thầm mở/truncate tệp đích đã tồn tại. Nếu đích đã có tên, thao tác tạo mới thất bại.

**Câu 9.** Vì sao cần cleanup đích nếu lỗi xảy ra giữa chừng?

**Đáp án:** File đích có thể mới chứa một phần dữ liệu. Nếu coi đó là kết quả hoàn chỉnh sẽ làm người dùng hoặc tác vụ sau đọc dữ liệu bị cắt.

**Câu 10.** Nếu chuyển từ heap `ByteBuffer` sang direct `ByteBuffer`, copy có nhất thiết nhanh hơn không?

**Đáp án:** Không. Phải benchmark trong môi trường thực; direct memory vẫn tốn tài nguyên và có chi phí allocation/lifecycle riêng.

**Câu 11.** `Files.copy()` có luôn đọc nguyên tệp vào RAM không?

**Đáp án:** Không. Đây là API thư viện chuẩn có thể dùng chiến lược streaming/triển khai tối ưu. Tự viết vòng buffer chủ yếu để học cơ chế hoặc tùy biến tiến độ, giới hạn, hash, transform.

**Câu 12.** File nguồn đang thay đổi trong khi copy. `Files.mismatch` sau đó có bảo đảm bản sao của một snapshot tại thời điểm bắt đầu không?

**Đáp án:** Không. Việc copy và so sánh không atomic với writer ngoài. Cần bảo vệ hoặc đóng băng version dữ liệu theo yêu cầu nghiệp vụ.

## 21. Checklist trước khi dùng trong ứng dụng

1. Dùng API truyền byte (`FileChannel`, `InputStream`, `OutputStream`), không qua `Reader`/`Writer` với binary.
2. Đặt giới hạn buffer dương, phù hợp memory budget; cấp đúng **một lần** rồi tái sử dụng.
3. Khi đọc, kiểm tra `-1` cho EOF; không coi short read hoặc `0` là EOF.
4. `clear()` trước source read, `flip()` trước destination write, `hasRemaining()` để ghi hết khối.
5. Dùng `long` cho số byte tổng và offset của file lớn.
6. Mở source chỉ để đọc; xác định chính sách destination (CREATE_NEW, overwrite, staging temp).
7. Dùng `try-with-resources` và xử lý `IOException`, no-progress, hết đĩa, bị ngắt.
8. Xử lý file output một phần khi thất bại; chỉ publish sau khi hoàn tất và verify nếu cần.
9. Kiểm tra size và nội dung bằng `Files.mismatch` hoặc checksum phù hợp; không tin size một mình.
10. Đảm bảo source/destination khác nhau, xem xét symlink/hardlink và nguồn bị thay đổi đồng thời.
11. Thử file rỗng, một byte, khối cuối ngắn, binary có 0x00/0xFF, file lớn và lỗi ghi.
12. Đo throughput/latency/memory theo workload thật trước khi tăng buffer tùy tiện.

## Kết luận

Sao chép file nhị phân an toàn về **nội dung và bộ nhớ** đòi hỏi ba nguyên tắc:

- **Chuyển byte nguyên vẹn**, không decode hoặc chuyển đổi text.
- **Dùng buffer có giới hạn và quản lý trạng thái đúng**: `clear → read → flip → write until !hasRemaining`.
- **Kiểm chứng và xử lý lỗi có chủ đích**: EOF, partial write, đích đã tồn tại, file đích dở, nguồn thay đổi và kiểm tra byte-đúng-byte.

Một buffer cố định vài KiB đến vài trăm KiB, được tái sử dụng đúng cách, có thể xử lý file nhiều GiB mà không cần mảng bằng kích thước file. Kích cỡ cụ thể phải được chọn bằng phép đo và hạn mức bộ nhớ của ứng dụng.

## Tài liệu tham khảo chính thức

- Java SE 17 — `FileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `ReadableByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 17 — `WritableByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritableByteChannel.html
- Java SE 17 — `Files` (`mismatch`, `copy`, `size`, `newInputStream`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 — `StandardOpenOption`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html
- Java SE 17 — `InputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- Java SE 17 — `OutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html
