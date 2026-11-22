# FileChannel và zero-copy: khả năng tối ưu, không phải bảo đảm cho mọi tình huống

## 1. Zero-copy trong I/O nghĩa là gì?

Khi truyền nội dung một tệp sang một channel khác, cách thực hiện quen thuộc là đọc byte từ tệp vào một `ByteBuffer` trong tiến trình Java rồi ghi những byte đó sang đích. Với tệp lớn, quá trình chuyển dữ liệu có thể tạo thêm bước sao chép giữa các vùng nhớ và tiêu thụ CPU.

**Zero-copy** là tên gọi của một nhóm kỹ thuật giúp **tránh một số bước sao chép dữ liệu không cần thiết**, đặc biệt những lần phải chuyển toàn bộ nội dung qua bộ nhớ ứng dụng. Trên một số hệ điều hành, đường truyền từ tệp sang socket có thể dùng một cơ chế nhân hệ điều hành như `sendfile` để giảm lượng dữ liệu phải đi qua không gian người dùng.

Trong Java NIO, `java.nio.channels.FileChannel` có các phương thức có thể tạo điều kiện cho tối ưu này:

- `transferTo(long position, long count, WritableByteChannel target)`: chuyển byte từ một vùng của **FileChannel nguồn** sang channel đích.
- `transferFrom(ReadableByteChannel src, long position, long count)`: chuyển byte từ channel nguồn vào một vùng của **FileChannel đích**.

**Nhưng gọi `transferTo` hoặc `transferFrom` không chứng minh rằng hệ thống đã thực sự sử dụng zero-copy.** Java định nghĩa kết quả truyền dữ liệu ở cấp API; cách thực hiện phụ thuộc JDK, hệ điều hành, loại channel, hệ thống tệp và tình huống vận hành. Một triển khai có thể dùng đường truyền tối ưu trong nhân hệ điều hành, dùng một vùng đệm trung gian hoặc kết hợp nhiều cách.

> **Nguyên tắc học bài:** Zero-copy là *khả năng tối ưu của một đường dữ liệu cụ thể*, không phải lời hứa “không có bất kỳ bản sao byte nào”, “luôn nhanh hơn” hoặc “chỉ cần gọi một lần là truyền xong”.

## 2. Phân biệt sao chép qua ByteBuffer và cơ hội zero-copy

### Luồng sao chép qua bộ đệm ứng dụng

Một phương án thông thường:

```text
File nguồn
    |
    v
FileChannel.read(ByteBuffer)
    |
    v
ByteBuffer do ứng dụng quản lý
    |
    v
WritableByteChannel.write(ByteBuffer)
    |
    v
Đích (tệp, socket, ...)
```

Dữ liệu được đưa đến vùng lưu trữ mà Java có thể thao tác. Ứng dụng có thể kiểm tra, biến đổi, giải mã, mã hóa hoặc xử lý từng khối byte trước khi gửi tiếp.

### Đường truyền có thể tối ưu với FileChannel

Với `source.transferTo(offset, count, target)`:

```text
Ứng dụng Java:
  yêu cầu chuyển vùng byte [offset, offset + count)
           |
           v
  FileChannel.transferTo(...)
           |
           v
  Triển khai JDK / hệ điều hành
           |
           +-- Có khả năng: đường truyền tối ưu trong kernel
           |
           +-- Trường hợp khác: sao chép qua buffer trung gian
           |
           v
  WritableByteChannel đích
```

Sơ đồ chỉ mô tả **các khả năng triển khai**. Không được khẳng định rằng mọi đường truyền qua `transferTo` đều bỏ qua không gian người dùng, không cần bộ đệm hay không tiêu thụ tài nguyên CPU/bộ nhớ. Cache của hệ điều hành, đường DMA, lớp mạng, mã hóa TLS và driver có thể tạo các bước xử lý hoặc sao chép khác nhau.

Điểm được API bảo đảm là **ý nghĩa chuyển byte**, số byte báo đã chuyển và các quy tắc trạng thái liên quan; tối ưu vật lý nằm ngoài hợp đồng chức năng của chương trình.

## 3. Hợp đồng `FileChannel.transferTo`

Chữ ký:

```java
public abstract long transferTo(
    long position,
    long count,
    WritableByteChannel target
) throws IOException;
```

Ý nghĩa:

- **`position`**: offset byte tuyệt đối, bắt đầu từ 0, trong FileChannel nguồn.
- **`count`**: số byte tối đa yêu cầu chuyển, không phải số byte chắc chắn sẽ được chuyển.
- **`target`**: channel đích có khả năng ghi.
- **Giá trị trả về**: số byte **thực sự** chuyển, kiểu `long`, nằm trong phạm vi từ 0 đến `count` khi thao tác thành công.

Không chấp nhận `position` hoặc `count` âm. Thao tác có thể phát sinh `IOException`, bao gồm những ngoại lệ liên quan channel không được mở đúng mode hay bị đóng.

### Vị trí của FileChannel nguồn có thay đổi không?

**Không.** Tham số `position` là vị trí riêng của lần truyền. Theo hợp đồng của `transferTo`, **`source.position()` không đổi** sau lời gọi đó.

Nếu channel đích có một vị trí hiện tại (ví dụ `FileChannel` đích), dữ liệu thường được ghi từ vị trí của **đích**, và vị trí đích có thể tiến theo số byte ghi được. Với đích là socket, không có một file offset công khai để người dùng quan sát tương tự.

Ví dụ:

```text
Nguồn "ABCDEFGHIJ" (10 byte)
source.position() = 7

transferTo(2, 3, target)
          |
          +-- yêu cầu chuyển "CDE"

source.position() sau chuyển: vẫn 7
target: tiến theo lượng byte nhận được, nếu có position
```

Không sử dụng `source.position()` để tìm “offset tiếp theo” trong vòng lặp positional transfer; cần tự theo dõi offset bắt đầu và tổng số byte đã chuyển.

### Khi nào `transferTo` có thể trả về 0?

Có nhiều nguyên nhân tùy hoàn cảnh:

1. `count == 0`.
2. `position` đã ở cuối hoặc vượt quá kích thước nguồn.
3. Đích chưa thể nhận thêm dữ liệu, chẳng hạn socket non-blocking đang chịu backpressure.
4. Một đường truyền/giới hạn triển khai cụ thể chưa chuyển được byte trong lượt gọi đó.

**`0` không đồng nghĩa chắc chắn với EOF hoặc “đã xong”.** Cần phân biệt dựa trên số byte kỳ vọng, trạng thái nguồn, loại đích và cơ chế chờ sẵn sàng. Không viết vòng `while` gọi lại `transferTo` liên tục khi kết quả bằng 0 mà không có điều kiện tiến độ.

## 4. Vì sao một lần `transferTo` có thể chuyển ít hơn `count`?

Hợp đồng cho phép **partial transfer**. Dù file nguồn còn đủ dữ liệu và đích có khả năng nhận, một lời gọi vẫn có thể chuyển ít hơn số byte yêu cầu do giới hạn hệ thống, I/O, điều kiện đích hoặc quyết định của triển khai.

Giả sử muốn chuyển 10.000 byte từ offset 1.000:

| Lần gọi | Offset truyền vào | Count yêu cầu | Byte thực chuyển | Tổng byte đã chuyển |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1.000 | 10.000 | 4.096 | 4.096 |
| 2 | 5.096 | 5.904 | 4.096 | 8.192 |
| 3 | 9.192 | 1.808 | 1.808 | 10.000 |

Đây là **tình huống giả định** để học cách tính offset; không phải số lượng byte bảo đảm của một hệ điều hành.

Công thức đúng sau mỗi lượt có `n > 0`:

\[
nextPosition = startPosition + transferredSoFar
\]

\[
remaining = requestedCount - transferredSoFar
\]

Vòng lặp phải tăng vị trí **nguồn** một cách tường minh:

```java
long offset = startOffset;
long remaining = byteCount;

while (remaining > 0) {
    long n = source.transferTo(offset, remaining, target);
    if (n == 0) {
        // Không có tiến độ: kiểm tra điều kiện, chờ readiness
        // hoặc dùng fallback phù hợp; không spin vô hạn.
        break;
    }

    offset += n;
    remaining -= n;
}
```

Đoạn mã này **không phải chương trình độc lập**; giả định `source`, `target`, `startOffset` và `byteCount` đã có. Nó minh họa cơ chế lặp, nhưng sau vòng lặp người gọi vẫn phải kiểm tra `remaining` và quyết định xử lý thiếu byte. Khi phép cộng offset có nguy cơ tràn `long`, cần kiểm tra giới hạn trước.

**Sai lầm phổ biến:** lặp `source.transferTo(startOffset, byteCount, target)` với cùng offset ban đầu mà không tăng offset. Lần sau có thể chuyển lại cùng đoạn byte và khiến tệp hoặc luồng đích chứa dữ liệu trùng lặp.

## 5. Ví dụ Java 17+: `transferTo` với fallback qua ByteBuffer

Ví dụ tạo hai tệp tạm để không cần mạng hoặc tài nguyên ngoài. Chương trình trước tiên **đề nghị** triển khai sử dụng `transferTo`; nếu một lượt không đạt tiến độ trong khi vẫn còn byte cần chuyển, nó thực hiện một lượt sao chép bằng `ByteBuffer` và các lời gọi `read`/`write` thông thường. Do vậy, chương trình minh họa đúng thông điệp “zero-copy là lựa chọn tối ưu, còn tính đúng đắn của sao chép là yêu cầu bắt buộc”.

Vì một lần gọi `transferTo` không bảo đảm truyền hết, cả đường chính và đường fallback đều theo dõi số byte thực tế.

**Tệp `TransferToWithFallbackDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TransferToWithFallbackDemo {
    static long copy(FileChannel source, WritableByteChannel target)
            throws IOException {
        long offset = 0;
        long end = source.size();
        ByteBuffer fallback = ByteBuffer.allocate(8);

        while (offset < end) {
            long count = end - offset;
            long n = source.transferTo(offset, count, target);

            if (n > 0) {
                offset += n;
                continue;
            }

            // Không có tiến độ: dùng đường đọc/ghi thông thường
            // cho một khối nhỏ, giữ nguyên position của source.
            fallback.clear();
            fallback.limit((int) Math.min(
                    fallback.capacity(), end - offset));

            int bytesRead = source.read(fallback, offset);
            if (bytesRead <= 0) {
                throw new IOException(
                    "Source ended or read made no progress");
            }

            fallback.flip();

            while (fallback.hasRemaining()) {
                int bytesWritten = target.write(fallback);
                if (bytesWritten <= 0) {
                    throw new IOException(
                        "Target write made no progress");
                }
            }

            offset += bytesRead;
        }
        return offset;
    }

    public static void main(String[] args) throws IOException {
        Path sourcePath = Files.createTempFile("nio-source-", ".txt");
        Path targetPath = Files.createTempFile("nio-target-", ".txt");

        try {
            Files.writeString(sourcePath, "Hello NIO!",
                    StandardCharsets.US_ASCII);

            try (FileChannel source = FileChannel.open(
                        sourcePath, StandardOpenOption.READ);
                 FileChannel target = FileChannel.open(
                        targetPath, StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING)) {

                source.position(2); // Vị trí nguồn đang sử dụng.
                long copied = copy(source, target);

                System.out.println("So byte da chuyen: " + copied);
                System.out.println("Vi tri nguon: "
                        + source.position());
                System.out.println("Vi tri dich: "
                        + target.position());
            }

            System.out.println("Noi dung dich: "
                    + Files.readString(targetPath,
                            StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(sourcePath);
            Files.deleteIfExists(targetPath);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac TransferToWithFallbackDemo.java
java TransferToWithFallbackDemo
```

**Stdout chính xác trong điều kiện các thao tác I/O hoàn tất:**

```text
So byte da chuyen: 10
Vi tri nguon: 2
Vi tri dich: 10
Noi dung dich: Hello NIO!
```

Giải thích:

1. `"Hello NIO!"` gồm đúng **10 byte ASCII**.
2. `source.position(2)` thiết lập con trỏ nguồn trước khi sao chép.
3. `source.transferTo(offset, ..., target)` sử dụng offset truyền vào, **không di chuyển** con trỏ nguồn đang là 2.
4. Nếu `transferTo` báo không có tiến độ, `source.read(fallback, offset)` là một lệnh **positional read**, cũng không sửa `source.position()`. Phần vừa đọc được gửi qua `target.write(fallback)` với vòng lặp để không bỏ sót byte.
5. `target.position()` tăng theo các byte được ghi vào tệp đích, cuối cùng bằng 10.
6. Đường tối ưu hoặc fallback có thể được chọn tùy máy; **stdout không có dòng nào khẳng định zero-copy đã xảy ra**. Kết quả người học cần kiểm tra là nội dung và số byte đã chuyển.

Đây là ví dụ cho **FileChannel tệp thường với đích FileChannel có khả năng ghi**. Với một `SocketChannel` non-blocking, `transferTo == 0` hoặc `write == 0` có thể là trạng thái backpressure bình thường: chương trình phải giữ offset/remaining, đăng ký readiness phù hợp rồi tiếp tục ở lượt sau. Không nên dùng chính sách “ném ngoại lệ ngay khi write trả 0” của ví dụ blocking để xử lý non-blocking socket.

## 6. Hợp đồng `FileChannel.transferFrom`

Chữ ký:

```java
public abstract long transferFrom(
    ReadableByteChannel src,
    long position,
    long count
) throws IOException;
```

`transferFrom` lấy tối đa `count` byte từ channel `src` rồi đưa chúng vào **FileChannel đích** bắt đầu từ offset `position`.

Bảng so sánh trực tiếp:

| Tính chất | `sourceFile.transferTo(pos, count, target)` | `targetFile.transferFrom(src, pos, count)` |
| --- | --- | --- |
| FileChannel là | **Nguồn** | **Đích** |
| `position` là offset của | FileChannel nguồn | FileChannel đích |
| Vị trí của FileChannel gọi phương thức | **Không thay đổi** | **Không thay đổi** |
| Channel đối tác | `WritableByteChannel` | `ReadableByteChannel` |
| Vị trí của channel đối tác | Có thể tiến theo số byte ghi, nếu đối tác có position | Có thể tiến theo byte đã đọc, nếu nguồn có position |
| Giá trị trả về | Số byte thực chuyển | Số byte thực chuyển |
| Được bảo đảm dùng zero-copy? | **Không** | **Không** |

**Đừng lẫn vị trí của FileChannel gọi phương thức với vị trí của channel đối tác.** Trong `transferTo`, FileChannel nguồn giữ nguyên position; đích nhận byte có thể thay đổi position. Trong `transferFrom`, FileChannel đích giữ nguyên position; nguồn bị tiêu thụ dữ liệu có thể thay đổi position.

Một giới hạn đáng chú ý của `transferFrom`: nếu offset đích **lớn hơn kích thước hiện tại của tệp đích**, hợp đồng API không chuyển byte trong lần gọi đó. Nếu cần ghi vào một vùng sau EOF và tạo khoảng trống, phải thiết kế cách mở rộng tệp thích hợp, không mặc định rằng `transferFrom` tự tạo vùng trống xa EOF.

`transferFrom` cũng có thể chuyển ít hơn `count`, kể cả khi các điều kiện khác có vẻ thuận lợi; gọi lại với `position + bytesTransferred` khi còn cần chuyển tiếp. Vì nguồn là `ReadableByteChannel`, có thể gặp nguồn chưa sẵn sàng hoặc đã EOF; `0` cần được xử lý theo trạng thái cụ thể.

## 7. Ví dụ Java 17+: `transferFrom` không đổi vị trí FileChannel đích

Ví dụ nhận dữ liệu từ một `ReadableByteChannel` chuyển đổi từ `ByteArrayInputStream`. Chương trình đặt `destination.position(2)` nhưng truyền dữ liệu vào offset **0** bằng `transferFrom`.

**Tệp `TransferFromDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.channels.ReadableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TransferFromDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = "DATA".getBytes(StandardCharsets.US_ASCII);
        Path path = Files.createTempFile("transfer-from-", ".txt");

        try {
            try (ReadableByteChannel input = Channels.newChannel(
                        new ByteArrayInputStream(payload));
                 FileChannel destination = FileChannel.open(
                        path, StandardOpenOption.READ,
                        StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING)) {

                destination.position(2);

                long copied = 0;
                while (copied < payload.length) {
                    long n = destination.transferFrom(
                            input, copied, payload.length - copied);
                    if (n == 0) {
                        throw new IOException("No transfer progress");
                    }
                    copied += n;
                }

                System.out.println("So byte da chuyen: " + copied);
                System.out.println("Vi tri dich: "
                        + destination.position());
                System.out.println("Kich thuoc tep: "
                        + destination.size());
            }

            System.out.println("Noi dung tep: "
                    + Files.readString(path,
                            StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac TransferFromDemo.java
java TransferFromDemo
```

**Stdout chính xác nếu các thao tác I/O hoàn tất:**

```text
So byte da chuyen: 4
Vi tri dich: 2
Kich thuoc tep: 4
Noi dung tep: DATA
```

Bốn byte `DATA` được ghi bắt đầu tại offset 0. `destination.position()` vẫn bằng **2**, vì đối số `position` của `transferFrom` là offset riêng của lần chuyển. Số byte được chuyển được lấy từ **giá trị trả về thực tế**, không mặc định bằng `count`.

Ví dụ này có nguồn là stream trong bộ nhớ được bọc bằng channel. **Không thể dựa vào nó để tuyên bố có zero-copy**: đây là cách sử dụng đúng hợp đồng API, còn đường triển khai thực tế do JDK và hệ điều hành quyết định.

## 8. Các tình huống khiến zero-copy không được sử dụng hoặc kém hiệu quả

### 8.1. Loại nguồn và đích khác nhau

Đường truyền file → socket có những cơ hội tối ưu ở cấp hệ điều hành khác với file → file, socket → file hoặc channel tự tạo. Từng tổ hợp có thể đi qua các lớp adapter hoặc cơ chế đệm khác nhau.

Ví dụ `Channels.newChannel(OutputStream)` cho phép dùng `transferTo` với một `WritableByteChannel` được bọc từ `OutputStream`, nhưng không bảo đảm kernel có thể chuyển trực tiếp từ tệp sang stream bên dưới mà không có sao chép qua Java.

### 8.2. Mã hóa, nén hoặc biến đổi nội dung

Nếu ứng dụng cần **giải mã/mã hóa TLS**, nén gzip, thay đổi cấu trúc dữ liệu, kiểm tra và sửa byte hoặc chèn header giữa các đoạn, quá trình truyền có thể bắt buộc đi qua lớp xử lý trung gian. Một số nền tảng có offload hoặc tích hợp đặc biệt; nhưng không được mặc định cơ chế đơn giản của `transferTo` tự xử lý mọi biến đổi mà vẫn giữ tối ưu zero-copy.

Với giao thức HTTP, có thể ứng dụng gửi header theo cách riêng rồi dùng đường tối ưu cho phần thân tệp **nếu** đích và stack thực thi hỗ trợ. Cần phân biệt loại kênh và giao thức cụ thể.

### 8.3. Hạn chế hệ điều hành và JDK

Các giới hạn về số byte truyền mỗi lần, kích thước tệp, thiết bị, filesystem, kiểu handle, bộ nhớ kernel, cờ mở tệp hoặc tình trạng I/O có thể ảnh hưởng đến cách chuyển dữ liệu. Có thể xảy ra một số lần truyền thành công rồi lần tiếp theo trả 0, hoặc chỉ chuyển một phần số byte yêu cầu.

Không giả định một giá trị tối đa cố định, ví dụ “mỗi lần luôn truyền được 2 GB”, áp dụng trên tất cả JDK/hệ điều hành. Hãy dùng số byte trả về và viết vòng lặp tiến độ, đồng thời đo trên môi trường thực tế.

### 8.4. Backpressure ở mạng và non-blocking I/O

Nếu đích là socket non-blocking, bộ đệm gửi có thể đầy. Khi đó `transferTo` có thể trả về **0** do tạm thời không thể gửi; tiếp tục thử liên tục sẽ gây *busy spin*. Cách đúng là giữ offset và số byte còn lại, chờ sự kiện sẵn sàng ghi phù hợp, sau đó thử lại khi có tiến độ.

Không dùng mẫu `while (remaining > 0) { transferTo(...); }` không có xử lý `0`, vì vòng lặp có thể không bao giờ kết thúc.

### 8.5. Bản sao trong hệ thống vẫn có thể tồn tại

Ngay cả khi một đường truyền tránh sao chép qua buffer ứng dụng, dữ liệu vẫn có thể được đặt trong page cache, socket buffer, vùng DMA hoặc các lớp I/O khác. **Zero-copy không đồng nghĩa tổng số bản sao vật lý bằng 0** trong toàn bộ vòng đời dữ liệu. “Zero” thường nói đến một lớp bước sao chép cụ thể được tối ưu.

### 8.6. Tệp nhỏ có thể không hưởng lợi rõ rệt

Với tệp rất nhỏ, thời gian mở tệp, tạo tài nguyên, syscall, dispatch, thiết lập kết nối và xử lý giao thức có thể chi phối tổng thời gian. Giảm số lần sao chép chưa chắc giảm độ trễ đầu cuối một cách đáng kể. Hiệu năng cần được đo theo trường hợp sử dụng, không suy ra từ tên API.

## 9. Bảo toàn tính đúng đắn quan trọng hơn chọn đường tối ưu

Một hàm truyền file đáng tin cậy cần xác định **điều kiện hoàn tất** và **trạng thái khi chưa hoàn tất** trước khi quan tâm đến zero-copy.

Các điểm phải làm rõ:

1. **Nguồn dữ liệu có kích thước cố định trong suốt thao tác không?** Nếu tệp bị sửa, cắt ngắn hoặc mở rộng giữa chừng, `size()` ban đầu có thể không phản ánh dữ liệu đang có. Với dữ liệu cần nhất quán, cần thiết kế snapshot/khóa/phiên bản hoặc quy trình tái thử và xác minh phù hợp.
2. **Đang muốn chuyển bao nhiêu byte?** Dùng `long` cho offset, count và tổng chuyển; đảm bảo không âm, không tràn khi cộng.
3. **Khi `n>0`:** tăng offset và giảm remaining dựa trên `n` thực tế.
4. **Khi `n==0`:** không tự coi là đã xong; xác định EOF, backpressure, giới hạn triển khai hay chuyển đường fallback.
5. **Khi lỗi I/O:** báo lỗi/đóng tài nguyên; không công bố thành công khi file đích mới được ghi một phần.
6. **Khi cần bảo đảm dữ liệu bền vững:** việc sao chép hoàn tất không đồng nghĩa dữ liệu đã được đồng bộ xuống thiết bị lưu trữ. `FileChannel.force(boolean)` hoặc quy trình lưu an toàn khác có thể cần thiết tùy yêu cầu, nhưng cũng có giới hạn theo thiết bị và filesystem.

Trong một hệ thống tạo file đầu ra chính thức, có thể ghi vào file tạm, kiểm tra kích thước/hash rồi đổi tên theo chiến lược phù hợp thay vì để người khác nhìn thấy file đang được ghi dở. Chi tiết đổi tên nguyên tử phụ thuộc khả năng hỗ trợ của file system và option được dùng; không mặc định mọi thao tác move là atomic.

## 10. So sánh `transferTo`, `transferFrom` với sao chép thủ công

| Đặc điểm | `transferTo` | `transferFrom` | `read` + `write` với `ByteBuffer` |
| --- | --- | --- | --- |
| Hướng sử dụng | FileChannel → WritableByteChannel | ReadableByteChannel → FileChannel | Channel nguồn → buffer → channel đích |
| Offset tệp tuyệt đối | Offset nguồn | Offset đích | Tùy API đọc/ghi lựa chọn |
| Position FileChannel gọi phương thức | Giữ nguyên | Giữ nguyên | Phụ thuộc dạng read/write |
| Partial transfer | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra |
| Zero-copy | Có thể được tối ưu | Có thể được tối ưu | Thường có byte đi qua buffer ứng dụng |
| Thích hợp khi cần biến đổi từng byte | Không trực tiếp | Không trực tiếp | Phù hợp hơn |
| Có bảo đảm nhanh hơn? | Không | Không | Không |
| Có bảo đảm atomic hay durable? | Không | Không | Không |

Không dùng “ít dòng code hơn” hay “API có tên transfer” làm bằng chứng về số lần sao chép và tốc độ. Đường truyền kernel phù hợp có thể giảm CPU đáng kể với tệp lớn, nhưng mức lợi ích là kết quả đo đạc và điều kiện triển khai cụ thể.

## 11. Đo và xác minh tối ưu một cách có ý nghĩa

Để kết luận zero-copy có lợi trong một ứng dụng, nên phân biệt hai câu hỏi:

### A. Truyền dữ liệu đúng chưa?

Kiểm tra các thuộc tính chức năng:

- Tổng số byte thực chuyển bằng lượng dữ liệu cần chuyển, hoặc có lý do dừng rõ ràng.
- Byte đầu ra giống byte đầu vào ở đúng phạm vi, bằng so sánh byte hoặc hash nếu phù hợp.
- Position của các channel và buffer đúng như hợp đồng.
- Không mất dữ liệu khi partial transfer; không nhân đôi đoạn byte khi thử lại.
- Xử lý được EOF, thiếu byte, đóng sớm và lỗi giữa chừng.

### B. Đường truyền có thực sự được tối ưu không?

Sau khi chức năng đúng, dùng đo đạc trên môi trường thực tế: thời gian xử lý, thông lượng, CPU, số byte cấp phát trong tiến trình, số lần syscall hoặc số liệu profiler/tracing nếu có. Hệ điều hành có thể cung cấp công cụ quan sát syscall/kernel (ví dụ theo dõi đường `sendfile` trên hệ thống có hỗ trợ). Tuy nhiên, **nhìn thấy một lời gọi syscall chưa đủ để chứng minh không có sao chép ở mọi tầng**.

Khi benchmark:

1. Dùng cùng loại nguồn/đích, cùng dữ liệu, chế độ blocking, kích thước buffer và chính sách đóng/flush.
2. Chạy nhiều lần, tách giai đoạn warmup khỏi số liệu đo, xem phân phối thời gian chứ không chỉ một lần chạy.
3. Chú ý tác động của OS page cache: lần đọc đầu và lần đọc lại có thể khác nhau đáng kể.
4. Với truyền mạng, phân biệt thông lượng đo từ ứng dụng, tải CPU và tốc độ bên nhận; áp lực mạng/backpressure có thể che hiệu quả sao chép.
5. Không so sánh đường truyền có xác minh/mã hóa với đường không làm công việc tương đương rồi kết luận nguyên nhân nằm hoàn toàn ở zero-copy.

**Không có API tiêu chuẩn `FileChannel` nào trả về cờ “lần vừa rồi đã sử dụng zero-copy”.** Muốn xác định đường đi của dữ liệu cần quan sát và hiểu triển khai thực tế.

## 12. Các lỗi thường gặp

| Giả định hoặc cách làm sai | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “Gọi `transferTo` là chắc chắn zero-copy” | Triển khai có thể dùng copy fallback | Xem đó là cơ hội tối ưu và đo trên nền tảng thực |
| “Zero-copy là zero byte được sao chép ở mọi tầng” | Còn page cache, driver, mạng, thiết bị | Nêu chính xác bước sao chép nào được giảm |
| “Một `transferTo` sẽ gửi hết `count`” | Partial transfer làm thiếu dữ liệu | Kiểm tra `long n`, tăng offset và lặp có kiểm soát |
| Lặp lại offset nguồn cũ sau partial transfer | Gửi trùng đoạn | Dùng `offset + transferredSoFar` |
| `n == 0` nghĩa là đã gửi xong | Có thể do backpressure hoặc giới hạn | Phân biệt còn dữ liệu/EOF và cơ chế chờ |
| Gọi lại liên tục khi `n == 0` | Busy spin | Chờ readiness hoặc chuyển fallback phù hợp |
| Giả định `source.position()` sẽ tăng sau `transferTo` | Đọc sai vị trí tiếp theo | Tự duy trì offset; position nguồn vẫn nguyên |
| Giả định `destination.position()` tăng sau `transferFrom` | Dữ liệu kế tiếp đặt sai vị trí | Tự cập nhật offset đích khi lặp |
| `transferFrom` ghi vào offset xa quá EOF | Có thể chuyển 0 byte theo hợp đồng | Định nghĩa và chuẩn bị kích thước/offset phù hợp |
| Ghi một phần rồi công bố file đã hoàn tất | Người đọc thấy nội dung thiếu | Kiểm tra tổng byte và công bố sau khi xác minh |
| Dùng zero-copy để tự động mã hóa/biến đổi dữ liệu | Transfer không thay thế pipeline xử lý | Chọn đường xử lý phù hợp với định dạng/giao thức |
| Kết luận “NIO luôn nhanh hơn stream” | Phụ thuộc kích thước, cache, I/O và nền tảng | Benchmark công bằng theo workload |
| Tin `transferTo` bảo đảm atomic và durability | Không có cam kết giao dịch/lưu bền | Thiết kế phối hợp/flush/khôi phục riêng |

## 13. Tình huống thực hành: gửi một vùng tệp 8 KiB

Giả sử nguồn dài 100 KiB, cần chuyển chính xác vùng 8 KiB bắt đầu ở offset 20 KiB đến một `WritableByteChannel`.

Các giá trị:

```text
startOffset     = 20 * 1024 = 20480
requestedCount  =  8 * 1024 = 8192
currentOffset   = 20480
remaining       = 8192
```

Nếu lần đầu `transferTo` trả về 3.000:

```text
nextOffset = 20480 + 3000 = 23480
remaining  = 8192 - 3000 = 5192
```

Nếu lần hai trả 2.000:

```text
nextOffset = 23480 + 2000 = 25480
remaining  = 5192 - 2000 = 3192
```

Nếu lần ba trả về **0**, dù `remaining = 3192`, **không được công bố hoàn tất**. Với socket non-blocking, lưu trạng thái `(nextOffset=25480, remaining=3192)` để tiếp tục khi socket sẵn sàng; với một kênh blocking trong môi trường phù hợp, có thể dùng fallback/diagnostics hoặc xử lý tình trạng thiếu tiến độ.

Để hoàn tất vùng truyền, tổng byte **phải bằng 8192**, và byte đích phải trùng với đoạn nguồn `[20480, 28672)`. FileChannel nguồn có thể vẫn giữ nguyên `source.position()` trong toàn bộ các lần `transferTo`.

**Không suy ra** có bao nhiêu copy nội bộ chỉ từ ba giá trị `3000, 2000, 0`. Chúng nói về lượng dữ liệu đã chuyển, không phải cơ chế truyền byte của kernel.

## 14. Ghi nhớ

1. **`FileChannel.transferTo` và `transferFrom` có thể tạo điều kiện cho đường truyền zero-copy**, nhưng hợp đồng Java **không bảo đảm cơ chế đó được sử dụng**.
2. **`transferTo` giữ nguyên position của FileChannel nguồn**; **`transferFrom` giữ nguyên position của FileChannel đích**. Channel đối tác có thể thay đổi trạng thái/position tương ứng với byte đã tiêu thụ hoặc tiếp nhận.
3. **Kết quả là số byte thực chuyển**, không phải số yêu cầu. Phải xử lý partial transfer bằng cách tăng offset và giảm remaining theo số byte trả về.
4. **Kết quả 0 chưa chắc là EOF hay thành công**; cần xét độ dài, trạng thái channel, readiness hoặc fallback.
5. **Zero-copy không có nghĩa là tuyệt đối không còn bản sao dữ liệu**, và không thay thế kiểm tra byte, bền vững lưu trữ, tính nhất quán hay bảo mật.
6. **Tính đúng đắn trước, hiệu năng sau**: xác minh dữ liệu đích, xử lý lỗi, rồi benchmark/trace trên nền tảng mục tiêu để đánh giá lợi ích.

**Tài liệu tham khảo:** Java SE 17 API: `java.nio.channels.FileChannel#transferTo`, `FileChannel#transferFrom`, `java.nio.channels.ReadableByteChannel`, `WritableByteChannel`, `java.nio.ByteBuffer` và `java.nio.file.StandardOpenOption`.
