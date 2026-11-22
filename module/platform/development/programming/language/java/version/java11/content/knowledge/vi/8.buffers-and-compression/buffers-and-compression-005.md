# Nén dữ liệu bằng `Deflater` với `ByteBuffer` đầu vào và đầu ra (Java 11+)

## 1. Mục tiêu và phạm vi

`java.util.zip.Deflater` dùng thuật toán **DEFLATE** để nén một chuỗi **byte**. Từ **Java 11**, API hỗ trợ trực tiếp `java.nio.ByteBuffer` ở cả hai phía:

```java
deflater.setInput(inputBuffer);
int bytesWritten = deflater.deflate(outputBuffer);
```

Điều này cho phép làm việc với buffer của NIO, bao gồm **heap buffer** tạo bằng `ByteBuffer.allocate(...)` hoặc `ByteBuffer.wrap(...)` và **direct buffer** tạo bằng `ByteBuffer.allocateDirect(...)`. Không cần người gọi chuyển mọi buffer thành `byte[]` chỉ để truyền cho `Deflater`.

Nội dung bài học tập trung vào các hợp đồng **còn áp dụng trong Java hiện đại**:

- Cách chuẩn bị `position` và `limit` của `ByteBuffer` đầu vào.
- Cách `setInput(ByteBuffer)` tiêu thụ byte và thay đổi `position`.
- Cách `deflate(ByteBuffer)` ghi byte nén và thay đổi `position` của đầu ra.
- Cách xử lý buffer đầu ra có dung lượng nhỏ, gọi `finish()` và lặp tới `finished()`.
- Cách thu hồi tài nguyên `end()`, kiểm tra bằng `Inflater` và phân biệt dữ liệu **zlib**, **raw DEFLATE**, **GZIP**.

`Deflater` nén **byte**, không nén trực tiếp `String` hay tự chọn UTF-8. Nếu dữ liệu gốc là văn bản, mã hóa thành byte bằng `StandardCharsets.UTF_8` trước, rồi giải mã đúng charset sau khi giải nén.

## 2. Các API cốt lõi của Java 11

| API | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `new Deflater()` | Tạo bộ nén với mức nén mặc định, đầu ra theo định dạng **zlib** | Cần gọi `end()` khi xong |
| `setInput(ByteBuffer input)` | Cung cấp các byte nằm trong `input.position()..input.limit()` | Có từ Java 11; vị trí input tiến khi byte được tiêu thụ trong các lượt `deflate` |
| `deflate(ByteBuffer output)` | Nén và ghi byte ra buffer, mặc định `NO_FLUSH` | Có từ Java 11; trả số byte đã ghi, đồng thời tiến vị trí output |
| `deflate(ByteBuffer output, int flush)` | Nén và điều khiển flush | Có từ Java 11; các chế độ `NO_FLUSH`, `SYNC_FLUSH`, `FULL_FLUSH` |
| `needsInput()` | Cho biết phần input đang cấp đã được tiêu thụ hết | Chủ yếu dùng trong luồng nén từng đợt |
| `finish()` | Thông báo **sẽ không cấp thêm input**; yêu cầu hoàn tất luồng nén | Không đồng nghĩa ngay lập tức đã xuất hết byte |
| `finished()` | Cho biết đã xuất tới cuối luồng nén | Dùng làm điều kiện kết thúc vòng lặp lấy output |
| `getBytesRead()` / `getBytesWritten()` | Tổng số byte đầu vào đã tiêu thụ / đầu ra đã tạo | Hữu ích khi đo lường, giám sát |
| `end()` | Giải phóng tài nguyên nén do native zlib sử dụng | Nên đặt trong `finally` |

Các overload nhận `byte[]` cũng vẫn hợp lệ. Tính năng ByteBuffer là bổ sung từ Java 11, không có nghĩa các phương thức dùng mảng đã lỗi thời.

## 3. Cơ chế `position`, `limit` và `remaining()`

Một `ByteBuffer` có:

- `capacity()`: dung lượng tối đa của buffer.
- `position()`: vị trí đọc/ghi tiếp theo.
- `limit()`: ranh giới không được vượt qua khi truy cập theo vị trí.
- `remaining()`: số byte từ vị trí hiện tại đến giới hạn, bằng `limit - position`.

Chỉ các byte **còn lại** của input tại thời điểm cấp cho `Deflater` mới được xem là vùng input. Với buffer đầu vào, `setInput` không tự chuyển buffer sang chế độ đọc hay tự lật `flip()`. Người gọi phải đặt `position`/`limit` đúng trước đó.

### 3.1. Chuẩn bị đầu vào: `put` rồi `flip`

```java
byte[] plain = "ABC".getBytes(java.nio.charset.StandardCharsets.UTF_8);
ByteBuffer input = ByteBuffer.allocateDirect(16);

input.put(plain); // position = 3, limit = 16
input.flip();     // position = 0, limit = 3: sẵn sàng đọc 3 byte
deflater.setInput(input);
```

Đoạn trên là mã minh họa: biến `deflater` cần được tạo và quản lý như ví dụ hoàn chỉnh ở mục 5. Sau khi các byte được nén tiêu thụ, `input.position()` tăng theo lượng byte đã dùng; `input.limit()` không tự thay đổi.

Khi buffer có phần **prefix** không cần nén, ví dụ hai byte đầu là header do ứng dụng quản lý, có thể đặt `input.position(2)` sau `flip()`. Lúc đó chỉ vùng từ vị trí 2 đến giới hạn được đưa vào máy nén. Ví dụ hoàn chỉnh bên dưới minh họa chính trường hợp này.

### 3.2. Thu thập đầu ra: `clear`, `deflate`, `flip`, `get`

```java
ByteBuffer output = ByteBuffer.allocateDirect(64);

output.clear(); // position = 0; limit = capacity
int written = deflater.deflate(output);
// Thành công: output.position() tăng đúng written byte.

output.flip();  // position = 0; limit = số byte vừa được ghi
byte[] chunk = new byte[output.remaining()];
output.get(chunk);
```

Lưu ý:

1. `clear()` **không xóa dữ liệu trong bộ nhớ**, chỉ thiết lập lại `position = 0` và `limit = capacity` để có thể ghi đè.
2. `deflate(output)` trả về số byte **đầu ra nén được ghi trong lượt đó**, không phải số byte input đã đọc. `output.position()` tiến thêm đúng số byte ghi.
3. `flip()` chuyển buffer đầu ra từ trạng thái **được ghi** sang **được đọc**. Nếu quên `flip()` và đọc toàn bộ capacity, có thể lấy cả dữ liệu cũ hoặc byte chưa hợp lệ.
4. Với **direct buffer**, `hasArray()` thường là `false`; gọi `output.array()` sẽ thất bại. Dùng `get(byte[])` hoặc một thao tác NIO tương thích để lấy dữ liệu.
5. Đầu ra `ByteBuffer` phải **có thể ghi**. Nếu truyền buffer chỉ đọc (`asReadOnlyBuffer()`), `deflate(ByteBuffer)` ném `ReadOnlyBufferException`.

Trong ví dụ đơn giản, sử dụng buffer đầu ra mới mỗi lượt có thể tránh `clear`, nhưng khi nén lượng dữ liệu lớn, **tái sử dụng** một buffer nhỏ giúp kiểm soát bộ nhớ.

## 4. Vì sao phải kết hợp `finish()` và `finished()`?

`Deflater` là bộ nén **có trạng thái**. Một lần `deflate(ByteBuffer)` không nhất thiết trả ra toàn bộ dữ liệu nén, ngay cả khi input đã được đọc hết. Nó có thể còn byte chờ trong bộ nén, và dữ liệu zlib còn có phần kết thúc/trailer.

Với input đã biết là hoàn chỉnh, trình tự đúng là:

1. Tạo `Deflater`.
2. Cấp input qua `setInput(ByteBuffer)` khi buffer đã sẵn sàng đọc.
3. Gọi `finish()` để báo **không còn input mới**.
4. Lặp `deflate(output)`, lấy **chính xác các byte đã ghi**, cho tới khi `finished() == true`.
5. Ghép các chunk theo đúng thứ tự.
6. Gọi `end()` trong `finally`, kể cả khi nén gặp lỗi.

`needsInput() == true` chỉ nói rằng input hiện tại đã hết; **không chứng minh** bộ nén đã xuất xong mọi byte. Trong tình huống nén một lần, dùng `finished()` mới là điều kiện kết thúc đáng tin cậy.

Với nguồn vào **cấp từng chunk**, quy trình có thêm bước: chỉ gọi `setInput(nextInput)` khi `needsInput()` cho phép cấp thêm; sau khi cấp chunk cuối, gọi `finish()` và vẫn phải tiêu thụ hết output đến `finished()`. Không gọi `finish()` giữa chừng rồi hy vọng có thể tiếp tục cấp dữ liệu vào cùng luồng nén đã kết thúc.

Khi `deflate(...)` trả `0`, không được tự suy ra nén đã hoàn tất. Có thể không có tiến triển vì chưa có input mới, vì buffer output không còn chỗ hoặc vì trạng thái nén/flush. Kiểm tra `needsInput()`, `finished()` và dung lượng buffer. Trong mã một lần đã gọi `finish()`, buffer đầu ra có dung lượng dương và không có lỗi, việc không có tiến triển bất ngờ được xử lý thành lỗi để tránh vòng lặp vô hạn.

## 5. Ví dụ hoàn chỉnh: direct ByteBuffer ở cả hai phía và kiểm tra giải nén

Tạo tệp **`DeflaterByteBufferDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.DataFormatException;
import java.util.zip.Deflater;
import java.util.zip.Inflater;

public class DeflaterByteBufferDemo {
    static byte[] compress(ByteBuffer input) {
        Deflater deflater = new Deflater();
        try {
            deflater.setInput(input);
            deflater.finish();

            ByteBuffer output = ByteBuffer.allocateDirect(7);
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            int chunks = 0;

            while (!deflater.finished()) {
                output.clear();
                int written = deflater.deflate(output);
                if (written == 0) {
                    throw new IllegalStateException("No compression progress");
                }
                if (written != output.position()) {
                    throw new IllegalStateException("Unexpected output position");
                }
                output.flip();
                byte[] chunk = new byte[output.remaining()];
                output.get(chunk);
                result.write(chunk, 0, chunk.length);
                chunks++;
            }

            System.out.println("output chunks > 1: " + (chunks > 1));
            System.out.println("input fully consumed: " + !input.hasRemaining());
            return result.toByteArray();
        } finally {
            deflater.end();
        }
    }

    static byte[] decompress(byte[] compressed, int capacity)
            throws DataFormatException {
        Inflater inflater = new Inflater();
        try {
            inflater.setInput(ByteBuffer.wrap(compressed));
            ByteBuffer output = ByteBuffer.allocate(capacity);

            while (!inflater.finished()) {
                if (!output.hasRemaining()) {
                    throw new DataFormatException("Output limit reached");
                }
                int read = inflater.inflate(output);
                if (read == 0) {
                    if (inflater.needsInput()) {
                        throw new DataFormatException("Truncated compressed data");
                    }
                    if (inflater.needsDictionary()) {
                        throw new DataFormatException("Dictionary required");
                    }
                    throw new DataFormatException("No decompression progress");
                }
            }

            output.flip();
            byte[] restored = new byte[output.remaining()];
            output.get(restored);
            return restored;
        } finally {
            inflater.end();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] original = "Java 11 ByteBuffer | ".repeat(6)
                .getBytes(StandardCharsets.UTF_8);

        ByteBuffer input = ByteBuffer.allocateDirect(original.length + 4);
        input.position(2);
        input.put(original);
        input.flip();
        input.position(2);
        int sourceLimit = input.limit();

        byte[] compressed = compress(input);
        byte[] restored = decompress(compressed, original.length + 8);

        System.out.println("input position == limit: "
                + (input.position() == sourceLimit));
        System.out.println("compressed length > 0: " + (compressed.length > 0));
        System.out.println("round trip equals: " + Arrays.equals(original, restored));
        System.out.println("restored bytes: " + restored.length);
        System.out.println("direct hasArray: " + input.hasArray());

        Deflater readOnlyCheck = new Deflater();
        try {
            readOnlyCheck.setInput(ByteBuffer.wrap(original));
            readOnlyCheck.finish();
            try {
                readOnlyCheck.deflate(ByteBuffer.allocate(32).asReadOnlyBuffer());
            } catch (ReadOnlyBufferException expected) {
                System.out.println("read-only output: ReadOnlyBufferException");
            }
        } finally {
            readOnlyCheck.end();
        }
    }
}
```

Biên dịch và chạy với **JDK 11+**. Nếu đang dùng JDK mới, `--release 11` buộc trình biên dịch chỉ chấp nhận API và ngôn ngữ có trong Java 11:

```bash
javac --release 11 -encoding UTF-8 DeflaterByteBufferDemo.java
java DeflaterByteBufferDemo
```

**Đầu ra chính xác đã kiểm thử:**

```text
output chunks > 1: true
input fully consumed: true
input position == limit: true
compressed length > 0: true
round trip equals: true
restored bytes: 126
direct hasArray: false
read-only output: ReadOnlyBufferException
```

### Phân tích kết quả

1. Chuỗi `"Java 11 ByteBuffer | "` có **21 byte ASCII**; lặp lại 6 lần tạo **126 byte**. `StandardCharsets.UTF_8` mã hóa toàn bộ thành byte.
2. `input` là **direct buffer** chứa hai byte nằm ngoài phạm vi cần nén: sau `flip()`, `position(2)` bỏ qua hai byte prefix. `Deflater` chỉ đọc các byte từ vị trí này tới `limit`.
3. `deflater.setInput(input)` nhận đúng đoạn input còn lại; sau khi hoàn tất nén, `input.position() == sourceLimit` và `input.hasRemaining() == false`.
4. `output` là direct buffer có **capacity chỉ 7 byte**. Kết quả nén lớn hơn 7 byte nên phải đọc qua nhiều chunk. Mỗi vòng dùng `clear()` trước khi ghi, `flip()` trước khi đọc, rồi ghép chunk bằng `ByteArrayOutputStream`.
5. `Inflater` cùng định dạng zlib giải nén trở lại. `Arrays.equals(original, restored)` chứng minh dữ liệu đầu ra sau giải nén **trùng byte-for-byte** với đầu vào, không phụ thuộc vào việc các phiên bản zlib tạo mảng nén dài bao nhiêu.
6. `input.hasArray() == false` là tính chất của direct buffer; nếu dùng `input.array()` sẽ không được. `ByteBuffer.get(...)` là cách lấy dữ liệu hợp lệ.
7. Phần kiểm tra riêng dùng output `asReadOnlyBuffer()` cho thấy `Deflater.deflate(ByteBuffer)` ném `ReadOnlyBufferException`. Không nên dùng read-only output để nén.

Phương thức `decompress` trong ví dụ dùng buffer đầu ra được cấp phát với **giới hạn đã biết** (cao hơn 126 byte), và báo lỗi khi vượt giới hạn. Đây là lựa chọn cho phép kiểm thử round-trip an toàn với dữ liệu nhỏ. Với dữ liệu đầu vào không tin cậy, **đừng cấp phát theo kích thước chưa kiểm chứng**, và không giải nén vô hạn vào bộ nhớ vì nguy cơ dữ liệu nén mở rộng rất lớn.

## 6. Heap buffer, direct buffer và read-only buffer

| Loại buffer | Tạo bằng | Có thể làm input? | Có thể làm output? |
| --- | --- | --- | --- |
| Heap, ghi được | `ByteBuffer.allocate(...)`, `ByteBuffer.wrap(byte[])` | Có | Có |
| Direct, ghi được | `ByteBuffer.allocateDirect(...)` | Có | Có |
| Read-only | `asReadOnlyBuffer()` | Có, vì `Deflater` chỉ đọc dữ liệu từ input | **Không**: output phải có thể ghi |

Direct buffer có thể hữu ích khi kết nối với các thao tác I/O của NIO và giảm việc sao chép ở một số trường hợp. Tuy nhiên, **không nên khẳng định direct luôn nhanh hơn heap**: hiệu năng, chi phí cấp phát và sao chép phụ thuộc kiểu dữ liệu, JVM, thư viện native và workload. Khi hiệu năng quan trọng, đo bằng benchmark trên hệ thống thật.

Lưu ý `Deflater` có thể dùng input từ một buffer có dữ liệu được chia sẻ qua `slice()`/`duplicate()`. Với buffer này, hãy tách rõ vùng `position..limit` để không đưa nhầm prefix/suffix vào đầu ra nén. **Không sửa đồng thời nội dung, vị trí hoặc giới hạn của input** trong lúc `deflate` đang thực thi; hợp đồng API cảnh báo hành vi không xác định.

## 7. Vấn đề flush và kết thúc luồng

Overload:

```java
int n = deflater.deflate(output, Deflater.NO_FLUSH);
```

tương đương về flush mode với `deflater.deflate(output)`. Ba mode:

- **`NO_FLUSH`:** chế độ thường dùng. Bộ nén có thể giữ dữ liệu để nén hiệu quả; không ép xuất hết dữ liệu đang chờ sau mỗi lượt.
- **`SYNC_FLUSH`:** đẩy dữ liệu đang chờ theo một điểm đồng bộ để phía giải nén có thể xử lý dữ liệu đã nhận được; có thể giảm hiệu quả nén.
- **`FULL_FLUSH`:** ngoài việc flush, đặt lại trạng thái nén để cho phép phía giải nén bắt đầu lại từ điểm phù hợp; dùng nhiều có thể làm giảm tỷ lệ nén đáng kể.

Với chương trình nén **một lần** ở mục 5, dùng `finish()` rồi lấy hết output đến `finished()` là đủ; **không cần `SYNC_FLUSH` hoặc `FULL_FLUSH`**.

Nếu bắt buộc dùng `SYNC_FLUSH`/`FULL_FLUSH`, theo Javadoc phải bảo đảm buffer output có đủ chỗ cho marker flush (khuyến nghị **ít nhất 6 byte còn trống**). Nếu một lượt trả đúng bằng số byte còn trống, cần tiếp tục gọi với cùng flush mode và vùng output mới để hoàn tất flush. Với vòng lặp flush, đặc biệt tránh gọi lặp mù quáng khi không có tiến triển hoặc không cung cấp buffer mới.

`finish()` không tự đóng bộ nén; `finished()` không tự gọi `end()`. Phải giải phóng tài nguyên bằng `end()`, kể cả khi compression thất bại giữa chừng.

## 8. Phân biệt zlib, raw DEFLATE và GZIP

`Deflater` là bộ **nén theo thuật toán DEFLATE**, nhưng định dạng bao quanh các byte nén rất quan trọng:

| Định dạng | Cách nén trong Java | Cách giải nén tương ứng |
| --- | --- | --- |
| **zlib** (mặc định) | `new Deflater()` hoặc `new Deflater(level, false)` | `new Inflater()` hoặc `new Inflater(false)` |
| **Raw DEFLATE** (không có zlib header/trailer) | `new Deflater(level, true)` | `new Inflater(true)` |
| **GZIP** | Dùng `GZIPOutputStream` để tạo framing GZIP đúng | Dùng `GZIPInputStream` |

**Không gửi đầu ra mặc định của `Deflater` rồi gắn nhãn `.gz` và cho rằng đó là file GZIP đúng định dạng.** GZIP có header/trailer của riêng nó. Tương tự, một tập tin ZIP còn có metadata cho các entry; một buffer DEFLATE đơn lẻ chưa phải toàn bộ file ZIP.

Khi tích hợp API hoặc giao thức, phải thống nhất định dạng hai phía. Nếu phía nhận mong đợi raw DEFLATE nhưng phía gửi phát zlib wrapper, quá trình giải nén có thể thất bại dù thuật toán nén bên trong giống nhau.

## 9. Lỗi thường gặp và cách khắc phục

| Hiện tượng hoặc giả định sai | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nén ra mảng rỗng | Input chưa `flip()`, `position == limit`, hoặc chưa gọi đủ các lượt `deflate` | Đảm bảo input có `remaining() > 0`; gọi `finish()` và lặp tới `finished()` |
| Đầu ra bị thiếu phần cuối | Dừng ngay khi `needsInput() == true` hoặc ngay sau một lần `deflate` | Tiếp tục đọc output cho tới `finished()` |
| Đọc ra toàn byte rác hoặc dư | Đọc `capacity` thay vì lượng byte thực ghi | Dùng `written` hoặc `flip()` + `remaining()` cho từng chunk |
| `UnsupportedOperationException` khi gọi `buffer.array()` | Buffer direct hoặc dạng không có backing array | Dùng `get(byte[])`, `ByteBuffer.put/get` hoặc API NIO khác |
| `ReadOnlyBufferException` | Truyền output chỉ đọc | Tạo buffer output ghi được |
| Vòng lặp nén không tiến triển | Buffer không còn chỗ, chưa cấp input hoặc trạng thái chưa đáp ứng | Kiểm tra `remaining()`, `needsInput()`, `finished()`; không loop vô hạn khi trả `0` |
| Kết quả giải nén không đúng | Ghép các chunk sai thứ tự, bỏ sót byte hoặc mismatch wrapper zlib/raw/GZIP | Ghép theo thứ tự và dùng giải nén cùng định dạng |
| `DataFormatException` trong `Inflater` | Dữ liệu nén không đúng định dạng, hỏng hoặc bị cắt cụt | Kiểm tra framing, độ dài và tính toàn vẹn nguồn |
| Dữ liệu tiếng Việt bị lỗi chữ | Đầu vào đã được mã hóa/giải mã bằng charset không khớp | Chọn charset rõ ràng, ví dụ UTF-8, và dùng cùng charset khi giải mã |
| Bộ nén giữ tài nguyên | Không gọi `end()` khi xong | Dùng `try/finally` để luôn `end()` |
| Tin direct buffer luôn tối ưu | Chi phí cấp phát/GC/native memory tùy workload | Đo benchmark và giữ buffer để tái sử dụng nếu phù hợp |

**Giới hạn của ví dụ:** `DeflaterByteBufferDemo` thu gom toàn bộ byte nén vào `ByteArrayOutputStream` và dữ liệu giải nén vào buffer trong bộ nhớ. Với stream lớn, nên **ghi từng output chunk trực tiếp vào nơi nhận** (file, channel hoặc output stream) và giới hạn kích thước dữ liệu; không tải mọi thứ vào bộ nhớ nếu dung lượng không biết trước.

## 10. Vận dụng cho luồng dữ liệu từng phần

Khi dữ liệu đến từ `SocketChannel` hoặc `FileChannel` thành từng `ByteBuffer` nhỏ, cách quản lý thường là:

1. **Nhận một chunk input**, đặt buffer đúng vùng đọc bằng `flip()` nếu vừa ghi byte vào nó.
2. Nếu `deflater.needsInput()`, cấp chunk bằng `setInput(buffer)`. Trong thời gian bộ nén chưa tiêu thụ hết, tránh sửa `position`, `limit` hoặc nội dung buffer từ thread khác.
3. **Tạo output chunk**, gọi `deflate(output)` và xử lý đúng số byte mới được tạo. Nếu buffer đã đầy, `flip()` rồi ghi chunk sang nơi đích, `clear()` để tiếp tục.
4. Khi hết chunk đầu vào và không còn byte phải cấp, gọi `finish()` đúng một lần và tiếp tục xuất dữ liệu đến `finished()`.
5. Đóng/giải phóng tài nguyên `end()` kể cả có lỗi I/O. Với nén tiếp một thông điệp mới, tạo `Deflater` mới hoặc dùng `reset()` có chủ đích khi bộ nén vẫn hợp lệ, và không nhầm trạng thái cũ với dữ liệu mới.

Đây là **quy trình khái niệm** cho streaming, không phải chương trình hoàn chỉnh. Một triển khai sản xuất còn cần xử lý backpressure, partial write của channel, luồng dữ liệu chưa kết thúc, giới hạn kích thước input/output và chính sách retry. `deflate(...)` không tự truyền các byte đã sinh sang socket hoặc file.

**Khi nào dùng Deflater trực tiếp?** Khi bạn cần điều khiển rõ ràng input/output `ByteBuffer`, xử lý pipeline NIO hoặc kiểm soát flushing. Nếu chỉ nén vào một `OutputStream` và không cần trực tiếp quản lý buffer, `DeflaterOutputStream` hoặc `GZIPOutputStream` có thể đơn giản hơn tùy định dạng đầu ra cần tạo.

## 11. Tự kiểm tra kiến thức

**Câu 1:** `setInput(ByteBuffer)` có tự gọi `flip()` cho buffer không?  
**Trả lời:** Không. Người gọi phải chuẩn bị vùng byte hợp lệ trong `position..limit`.

**Câu 2:** Sau `int n = deflater.deflate(out)`, `n` là số byte nào?  
**Trả lời:** Số **byte nén đã ghi vào `out`**, đồng thời `out.position()` tăng `n` byte.

**Câu 3:** `needsInput() == true` có đồng nghĩa nén hoàn tất không?  
**Trả lời:** Không. Còn có thể có output đang chờ; `finished()` mới xác nhận đã xuất tới cuối sau `finish()`.

**Câu 4:** Có thể gọi `deflate` với một output `ByteBuffer.allocateDirect(...).asReadOnlyBuffer()` không?  
**Trả lời:** Không. `ReadOnlyBufferException` sẽ được ném.

**Câu 5:** Kết quả của `new Deflater()` có tương đương file GZIP không?  
**Trả lời:** Không. Mặc định là dữ liệu nén có wrapper **zlib**. Muốn GZIP thì dùng API GZIP tương ứng.

**Câu 6:** Vì sao không nên dùng `output.array()` với direct buffer?  
**Trả lời:** Direct buffer không phơi bày mảng `byte[]` qua `array()`. Đọc những byte hợp lệ bằng `get(...)` hoặc API làm việc trực tiếp với ByteBuffer.

**Câu 7:** Khi nào có thể gọi `end()`?  
**Trả lời:** Khi không dùng bộ nén nữa; đặt trong `finally` và đảm bảo các byte cần thiết đã được xử lý trước khi kết thúc bình thường.

## 12. Ghi nhớ

- **Java 11+** cung cấp `Deflater.setInput(ByteBuffer)` và `Deflater.deflate(ByteBuffer)` để nén dữ liệu với buffer của NIO.
- **Input:** `position..limit` xác định byte còn lại; vị trí tăng khi `Deflater` tiêu thụ byte. **Output:** vị trí tăng đúng số byte nén đã ghi; dùng `flip()` để đọc chunk.
- Với dữ liệu đầu vào đã hoàn chỉnh, **`setInput` → `finish` → lặp `deflate` tới `finished` → `end`** là quy trình cần nhớ.
- `needsInput()` chỉ phản ánh input còn hay hết; **không dùng thay `finished()`**.
- Direct buffer **không đòi hỏi phải đổi thành mảng trước khi nén**, nhưng vẫn cần buffer output ghi được; không gọi `array()` trên buffer không có mảng backing.
- Mặc định `Deflater` phát định dạng **zlib**; raw DEFLATE và GZIP cần cấu hình/API tương ứng.
- Với dữ liệu lớn hoặc không đáng tin, kiểm soát tài nguyên native, số byte, buffer và giới hạn giải nén.

**Tài liệu chính thức:** [Oracle JDK 11 — Deflater](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/Deflater.html), [Oracle JDK 11 — Inflater](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/zip/Inflater.html), [Oracle Java API hiện hành — Deflater](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/zip/Deflater.html), [Oracle Java API — ByteBuffer](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/ByteBuffer.html).