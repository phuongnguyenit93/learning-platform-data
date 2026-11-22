# Mô phỏng partial read, partial write và lỗi giữa chừng trong Java I/O

## 1. Vì sao phải kiểm thử I/O theo từng phần?

Trong Java NIO, `ReadableByteChannel.read(ByteBuffer)` và `WritableByteChannel.write(ByteBuffer)` trả về **số byte thật sự đã chuyển trong lời gọi hiện tại**, không hứa luôn xử lý hết `ByteBuffer.remaining()`. Với file nhỏ trên ổ cục bộ, một lần đọc/ghi có thể tình cờ đủ. Nhưng socket non-blocking, luồng bị giới hạn băng thông, bộ đệm gần đầy, I/O từ thiết bị hoặc một test double có thể khiến lệnh chỉ chuyển **một phần**, không chuyển byte nào, hoặc gặp `IOException` giữa chuỗi thao tác.

Nếu chỉ kiểm tra trường hợp “đọc hết một lần, ghi hết một lần”, code dễ chứa những lỗi:

- Bỏ quên phần `ByteBuffer` chưa ghi, gây **mất dữ liệu**.
- Coi `read() == 0` là EOF, nên dừng quá sớm.
- Coi `write() == 0` là thành công và loại bỏ bytes chưa chuyển.
- Quên gọi `flip()`/`clear()` hoặc `compact()`, khiến ghi sai vùng dữ liệu.
- Thử lại toàn bộ request/file sau lỗi và **ghi trùng** phần đã thực hiện.
- Coi `IOException` chỉ có thể xảy ra trước khi bất kỳ byte nào được chuyển.
- Dùng `Thread.sleep` trong test thay vì kiểm soát lịch lỗi một cách xác định.

Mục tiêu của bài này là **tạo tình huống lỗi một cách chủ động và tái lập được** bằng các channel giả lập, thay vì chờ mạng chậm hoặc làm hỏng file thật. Bạn sẽ biết cách kiểm thử vòng lặp đọc đủ/ghi đủ, phân biệt `0`/EOF/exception, quan sát trạng thái buffer và thiết kế retry có thể phục hồi.

## 2. Hợp đồng read và write cần thuộc lòng

Với `ReadableByteChannel.read(dst)`, gọi `dst.remaining()` trước khi đọc để biết số byte tối đa mà buffer nhận được.

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `n > 0` | Đã đưa `n` bytes vào `dst`, tăng `position` tương ứng. | Cập nhật số byte, tiếp tục nếu đang đọc một frame cố định. |
| `n == 0` | Chưa đọc được byte trong lời gọi này; có thể do I/O chưa sẵn sàng hoặc buffer không còn chỗ. | **Không** tự coi là EOF; xem blocking mode, readiness và deadline. |
| `n == -1` | Đã tới end-of-stream (EOF). | Nếu cần đúng N bytes mà chưa đủ thì báo truncated frame. |
| `IOException` | Đọc thất bại. | Không coi là EOF hay “chắc chắn chưa đọc byte nào”; áp dụng chính sách lỗi/recovery. |

Với `WritableByteChannel.write(src)`:

| Kết quả | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| `n > 0` | Đã lấy `n` bytes từ `src`, tăng `position` tương ứng. | Tiếp tục ghi phần `src.hasRemaining()`. |
| `n == 0` | Chưa chuyển byte trong lần gọi này. | Giữ buffer, chờ khả năng ghi/áp dụng deadline; tránh busy-loop. |
| `IOException` | Lời gọi thất bại. | Không ACK thành công và không retry mù nếu có thể đã ghi một phần. |

`write` **không dùng `-1` làm tín hiệu EOF** như `read`. Một số channel có hành vi blocking và có thể đợi tới khi tiến triển, nhưng những channel như `SocketChannel` ở non-blocking mode có thể thường xuyên trả `0`. Giao diện `ReadableByteChannel` cho phép trả ít hơn số byte còn chỗ trong buffer; một lần read không đồng nghĩa một message TCP.

### ByteBuffer.position, limit và remaining

Giả sử `ByteBuffer.allocate(8)`: lúc mới tạo, `position=0`, `limit=8`, `remaining=8`.

```text
Sau khi read được 3 bytes:
  position=3, limit=8
  [A B C _ _ _ _ _]
   ^ dữ liệu nhận     ^ vùng còn chỗ

Sau flip():
  position=0, limit=3
  [A B C] -> vùng chuẩn bị truyền/đọc

Sau write được 2 bytes:
  position=2, limit=3
  [A B | C] -> còn byte C chưa gửi

Sau write hết byte C:
  position=3, limit=3; remaining=0
```

`flip()` chuyển buffer từ chế độ lấp dữ liệu sang chế độ tiêu thụ. `clear()` đưa position về 0 và limit về capacity nhưng **không xóa vật lý bytes**. `compact()` giữ các bytes chưa tiêu thụ rồi chuyển chúng về đầu để tiếp tục đọc thêm; hữu ích cho parser TCP nhận dữ liệu không trọn frame.

Nếu gọi `clear()` ngay sau một lần `write` ngắn, phần bytes chưa ghi sẽ bị coi như không còn trong buffer và có nguy cơ mất. Nếu luôn gọi `flip()` sau mỗi lệnh `read` mà chưa cân nhắc state, bạn có thể gửi lặp một đoạn hoặc phá trạng thái parser.

## 3. Thiết kế test double cho partial I/O

Một unit test tốt không cần socket Internet hoặc ghi lên ổ thật. Có thể triển khai hai interface Java NIO:

- `ReadableByteChannel` nhận dữ liệu từ byte array và mỗi lần chỉ đưa tối đa 2 bytes vào buffer.
- `WritableByteChannel` nhận dữ liệu vào `ByteArrayOutputStream` và mỗi lần chỉ lấy tối đa 3 bytes từ buffer.
- Ở lần gọi đầu tiên, mỗi channel trả `0` để kiểm tra code không nhầm “chưa sẵn sàng” với EOF hay thành công.
- Thống kê số lần gọi để xác nhận code đã đi qua nhánh partial I/O thực sự.

Với test double, các số 2/3 là **ràng buộc cố ý của test**, không phải dự đoán filesystem hoặc số byte do hệ điều hành quyết định. Lợi ích lớn nhất là kiểm thử hoàn toàn xác định: chạy một trăm lần vẫn đi qua cùng lịch sự kiện.

### Ví dụ Java 17 chạy được: ShortIoDemo

Tạo file `ShortIoDemo.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class ShortIoDemo {
    static final class ShortReader implements ReadableByteChannel {
        private final byte[] data = "ABCDEFG".getBytes(StandardCharsets.US_ASCII);
        int pos, calls;
        boolean firstZero, open = true;
        @Override public int read(ByteBuffer dst) throws IOException {
            if (!open) throw new ClosedChannelException();
            calls++;
            if (!firstZero) { firstZero = true; return 0; }
            if (pos == data.length) return -1;
            int n = Math.min(2, Math.min(dst.remaining(), data.length - pos));
            dst.put(data, pos, n);
            pos += n;
            return n;
        }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    static final class ShortWriter implements WritableByteChannel {
        private final ByteArrayOutputStream saved = new ByteArrayOutputStream();
        int calls;
        boolean firstZero, open = true;
        @Override public int write(ByteBuffer src) throws IOException {
            if (!open) throw new ClosedChannelException();
            calls++;
            if (!firstZero) { firstZero = true; return 0; }
            int n = Math.min(3, src.remaining());
            byte[] chunk = new byte[n];
            src.get(chunk);
            saved.write(chunk);
            return n;
        }
        String content() { return saved.toString(StandardCharsets.US_ASCII); }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    public static void main(String[] args) throws Exception {
        try (ShortReader source = new ShortReader();
             ShortWriter target = new ShortWriter()) {
            ByteBuffer buffer = ByteBuffer.allocate(4);
            int total = 0;
            while (true) {
                int n = source.read(buffer);
                if (n < 0) break;
                if (n == 0) continue; // Fixture chỉ trả 0 đúng một lần.
                buffer.flip();
                while (buffer.hasRemaining()) {
                    int written = target.write(buffer);
                    if (written == 0) continue; // Fixture chỉ trả 0 đúng một lần.
                    total += written;
                }
                buffer.clear();
            }
            System.out.println("content=" + target.content());
            System.out.println("copied=" + total);
            System.out.println("read-zero=" + source.firstZero);
            System.out.println("write-zero=" + target.firstZero);
            System.out.println("read-calls=" + source.calls);
            System.out.println("write-calls=" + target.calls);
        }
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac --release 17 ShortIoDemo.java
java ShortIoDemo
```

Kết quả đã kiểm thử:

```text
content=ABCDEFG
copied=7
read-zero=true
write-zero=true
read-calls=6
write-calls=5
```

**Diễn giải lịch I/O:**

1. `read` đầu trả `0`; vòng lặp chưa chuyển byte nào và chỉ tiếp tục vì fixture được thiết kế chắc chắn có tiến triển.
2. Bốn lệnh `read` tiếp theo trả `2, 2, 2, 1` byte. Mỗi lệnh sử dụng phần `dst.remaining()` và tăng `position` đúng số byte.
3. Lệnh `read` cuối trả `-1` để báo EOF. Tổng cộng **6** lần gọi.
4. `write` đầu tiên trả `0`. Bốn lần ghi có tiến triển sau đó tiêu thụ `2, 2, 2, 1` byte. Tổng **5** lần gọi write.
5. `flip()` chuyển 2 hoặc 1 byte vừa nhận sang chế độ đọc để writer tiêu thụ; `while (buffer.hasRemaining())` bảo đảm chưa mất byte nào trước `clear()`.
6. `copied=7` và `content=ABCDEFG` chứng minh toàn bộ bytes được đưa qua fixture đúng thứ tự.

**Cảnh báo quan trọng:** hai nhánh `if (n == 0) continue` ở đây chỉ có thể dùng an toàn vì fixture cố ý trả `0` đúng **một lần**. Không sao chép nguyên vòng này vào channel non-blocking production: một channel có thể trả `0` liên tục, gây CPU spin. Dùng `Selector`/readiness, hàng đợi/đợi có giới hạn và timeout đúng kiến trúc.

### Một lỗi test dễ bỏ qua

Nếu fixture luôn trả “đủ các bytes được hỏi” thì code sai sau vẫn vượt qua:

```java
// Anti-pattern: lỗi vì không xử lý short write.
ByteBuffer src = ByteBuffer.wrap(payload);
channel.write(src);               // Có thể chỉ ghi một phần.
System.out.println("finished");   // Báo thành công quá sớm.
```

Đây là đoạn minh họa có `payload`, `channel` giả định. Test dùng `ShortWriter` sẽ làm rõ ngay lỗi này: `src.hasRemaining()` vẫn true sau lời gọi đầu có tiến triển, hoặc thậm chí lần đầu trả `0` mà chưa có byte nào được ghi.

## 4. Mô phỏng lỗi giữa chừng: đã chuyển một phần rồi IOException

Mục tiêu tiếp theo là kiểm tra không chỉ short I/O, mà cả **lỗi đến sau một số lời gọi thành công**:

- Reader cung cấp đúng 2 bytes `HE`, rồi ném `IOException` khi ứng dụng còn cần 3 bytes.
- Writer nhận đúng 2 bytes `HE`, rồi ném `IOException` ở lần ghi kế tiếp; 3 bytes `LLO` vẫn còn trong buffer của ví dụ.
- Ứng dụng phải ghi nhận dữ liệu **chưa hoàn chỉnh**, không trả thành công.
- Không thể suy từ lỗi rằng bên nhận hoặc storage **chưa từng nhận byte nào**.

### Ví dụ Java 17: MidStreamFailureDemo

Tạo file `MidStreamFailureDemo.java`:

```java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.StandardCharsets;

public class MidStreamFailureDemo {
    static final class FaultyReader implements ReadableByteChannel {
        boolean open = true;
        int calls;
        @Override public int read(ByteBuffer dst) throws IOException {
            if (!open) throw new ClosedChannelException();
            if (++calls == 1) {
                dst.put((byte) 'H').put((byte) 'E');
                return 2;
            }
            throw new IOException("injected read failure");
        }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    static final class FaultyWriter implements WritableByteChannel {
        boolean open = true;
        int calls;
        final ByteArrayOutputStream saved = new ByteArrayOutputStream();
        @Override public int write(ByteBuffer src) throws IOException {
            if (!open) throw new ClosedChannelException();
            if (++calls == 1) {
                int n = Math.min(2, src.remaining());
                byte[] chunk = new byte[n];
                src.get(chunk);
                saved.write(chunk);
                return n;
            }
            throw new IOException("injected write failure");
        }
        @Override public boolean isOpen() { return open; }
        @Override public void close() { open = false; }
    }
    public static void main(String[] args) throws Exception {
        ByteBuffer received = ByteBuffer.allocate(5);
        try (FaultyReader source = new FaultyReader()) {
            try {
                while (received.hasRemaining()) {
                    int n = source.read(received);
                    if (n < 0) throw new EOFException("truncated frame");
                }
            } catch (IOException e) {
                System.out.println("read-error=" + e.getMessage());
            }
        }
        System.out.println("read-before-error=" + received.position());

        ByteBuffer pending = ByteBuffer.wrap(
                "HELLO".getBytes(StandardCharsets.US_ASCII));
        try (FaultyWriter target = new FaultyWriter()) {
            try {
                while (pending.hasRemaining()) {
                    int n = target.write(pending);
                    if (n == 0) throw new IOException("write stalled");
                }
            } catch (IOException e) {
                System.out.println("write-error=" + e.getMessage());
            }
            System.out.println("written-prefix=" +
                    target.saved.toString(StandardCharsets.US_ASCII));
            System.out.println("remaining=" + pending.remaining());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 MidStreamFailureDemo.java
java MidStreamFailureDemo
```

Kết quả đã kiểm thử:

```text
read-error=injected read failure
read-before-error=2
write-error=injected write failure
written-prefix=HE
remaining=3
```

Kết quả được kiểm soát hoàn toàn bởi fixture: lần đọc đầu tăng `received.position()` lên `2`; lần ghi đầu tăng `pending.position()` lên `2`. Sau đó lỗi xảy ra ở **lời gọi kế tiếp** trước khi fixture thay đổi buffer thêm lần nữa, nên bản ghi đã nhận đúng prefix `HE` và còn `3` byte chưa ghi.

**Không suy diễn ra mọi channel thật:** nếu một lời gọi I/O **tự nó** ném `IOException` giữa khi truy cập OS/thiết bị, mức tiến triển đã được lưu bền hoặc peer đã xử lý có thể **không xác định** ở tầng ứng dụng. Vị trí `ByteBuffer` của fixture là đo được vì ta tự viết nó; API không có một “số byte chắc chắn đã commit đến peer/database” sau mọi exception. Tránh báo retry an toàn chỉ dựa trên `position()` sau lỗi.

## 5. EOF giữa frame khác IOException giữa frame

Khi một protocol quy định frame dài **N bytes**, reader phải phân biệt:

- Đọc được đúng N bytes: hoàn thành frame.
- Nhận `-1` khi mới có ít hơn N bytes: **truncated frame**, dù EOF tự nó là kết thúc stream bình thường.
- Nhận `IOException`: lỗi đọc, không được tự diễn dịch là EOF.
- Nhận `0`: chưa tiến triển; không thể tự kết luận frame hỏng hoặc hoàn thành.

Một hàm đọc đủ trong **blocking context** (mã minh họa, không phải chương trình độc lập):

```java
static void readFully(ReadableByteChannel input, ByteBuffer dst)
        throws IOException {
    while (dst.hasRemaining()) {
        int n = input.read(dst);
        if (n < 0) {
            throw new EOFException("Unexpected EOF: missing "
                    + dst.remaining() + " bytes");
        }
        if (n == 0) {
            throw new IOException("No progress; use readiness/deadline policy");
        }
    }
}
```

Hàm cố tình **fail fast trên `0`** khi dùng trong test được kiểm soát, để tránh vòng lặp vô hạn. Với non-blocking `SocketChannel`, `0` là trạng thái hợp lệ; handler production nên giữ `dst` và đăng ký `OP_READ`, không coi nó là lỗi ngay. Với blocking channel thông thường, nếu buffer còn chỗ, read thường chờ có tiến triển hoặc EOF; vẫn cần xử lý trạng thái và timeout theo loại channel.

Khi một frame có **length-prefix**, phải giới hạn length trước khi cấp phát buffer để tránh lỗi bảo mật/tài nguyên:

```text
[4-byte length][payload length bytes][optional checksum]
```

Test lần lượt “header thiếu 1 byte”, “payload thiếu 1 byte”, “length âm/quá lớn”, “truyền nhiều frame chung một read”, “một frame trải qua nhiều read”, “đọc 0 nhiều lần”. Đây là kiểm thử parser/protocol, bổ sung cho test API Channel.

## 6. Ghi đủ không đồng nghĩa transaction nguyên tử

Vòng lặp ghi dữ liệu có tiến triển thường được diễn đạt:

```java
// Snippet minh họa dành cho channel có progress theo chính sách.
static void writeAll(WritableByteChannel output, ByteBuffer src)
        throws IOException {
    while (src.hasRemaining()) {
        int n = output.write(src);
        if (n == 0) {
            throw new IOException("No write progress");
        }
    }
}
```

Cách này hữu ích cho **fixture hoặc blocking path** được kỳ vọng có tiến triển. Với non-blocking socket, phải chờ `OP_WRITE` thay vì ném lỗi ngay; không bật `OP_WRITE` liên tục nếu không có bytes pending, vì socket thường writable khiến vòng xử lý thức liên tục.

Ngay cả khi `writeAll` hoàn tất:

- Với socket, điều đó **không chứng minh remote application đã parse/commit dữ liệu**; cần acknowledgement ở protocol.
- Với file, điều đó **không chứng minh bytes đã bền vững sau mất điện**; xem `FileChannel.force` và filesystem contract.
- Với record lớn, thao tác có thể gồm nhiều ghi nhỏ; nếu crash ở giữa, file có thể chứa prefix dở. Cần checksum/version/journal/atomic replace hoặc storage engine.
- Với network request không idempotent, lỗi kết nối sau partial write có thể tạo **trạng thái chưa rõ bên nhận xử lý tới đâu**. Retry mù có thể gây gửi trùng hoặc double charge.

## 7. Chiến lược retry an toàn sau lỗi

Một điểm dễ nhầm là tách ba cấp độ:

| Cấp độ | Có thể biết gì sau một lời gọi thành công? | Không thể kết luận gì? |
| --- | --- | --- |
| `ByteBuffer` | `position` tăng theo byte được channel báo đã chuyển. | Peer đã xử lý, disk đã commit. |
| Kết nối TCP | `write` chấp nhận một phần byte stream ở local stack. | Remote app đã nhận toàn bộ logical message. |
| Ứng dụng nghiệp vụ | Chỉ có response/ACK theo protocol của ứng dụng. | Nếu mất ACK, không chắc server chưa làm việc. |

Khi IOException xảy ra:

1. Ghi log **tác vụ, offset/frame ID, kích thước mong đợi, số bytes đã báo tiến triển từ các lời gọi thành công trước đó**, loại exception và trạng thái kênh.
2. Đánh dấu request/file ở trạng thái **incomplete hoặc uncertain**, đừng báo thành công.
3. Kiểm tra loại dữ liệu: file tạm mới có thể xóa rồi dựng lại; log append cần record framing/checksum; network request cần idempotency key hoặc hỏi transaction status.
4. Quy định retry budget, backoff và deadline; tránh retry vô hạn khi thiết bị/mạng đang hỏng.
5. Khi không chứng minh được offset đã commit, **không** tùy tiện chỉ gửi phần còn lại hoặc gửi từ đầu nếu giao thức không hỗ trợ resume/dedup.

Ví dụ một file import có thể ghi vào `incoming.tmp` rồi publish bằng `ATOMIC_MOVE` sau khi kiểm tra checksum; consumer không bao giờ đọc file tạm. Với log cần lưu mọi record, dùng length/checksum/commit marker và quét bỏ record cuối dở khi recovery. Đây là vấn đề durability/transaction, **không được giải quyết chỉ bằng vòng lặp write**.

## 8. Test matrix tối thiểu cần chạy

| Test case | Lịch mô phỏng | Kết quả phải kiểm tra |
| --- | --- | --- |
| Read đủ ngay | `read -> N` | Byte contents và count đúng. |
| Partial read | `read -> 2, 2, 1` | Tích lũy đủ N, không bỏ/mất thứ tự. |
| Read tạm 0 | `read -> 0, N` | Không coi `0` là EOF; không CPU-spin trong production. |
| EOF trước đủ N | `read -> 2, -1` | Báo truncated frame, không parse dữ liệu dở. |
| Read lỗi sau prefix | `read -> 2, IOException` | Báo lỗi, giữ context số bytes, không ACK. |
| Write đủ ngay | `write -> N` | `hasRemaining == false`, bytes đúng. |
| Partial write | `write -> 1, 2, ...` | Lặp cho tới khi hết buffer, không gọi `clear` sớm. |
| Write tạm 0 | `write -> 0, N` | Giữ pending bytes, chờ readiness/deadline. |
| Write lỗi giữa chừng | `write -> 2, IOException` | Prefix có thể đã được chuyển; xử lý uncertain state. |
| Lỗi ở lời gọi đầu | `read/write -> IOException` | Không suy diễn là EOF, không retry vô hạn. |
| Buffer rất nhỏ | Capacity 1, 2, 3 | Không phá trạng thái flip/clear, giữ đúng thứ tự. |
| Payload rỗng / boundary | 0, 1, N-1, N, N+1 | Không truy cập buffer quá limit. |
| Nhiều message | Frame bị tách hoặc gộp | Parser giữ state, không dựa vào một read = một message. |
| Client hủy / timeout | Thời hạn hết giữa I/O | Cleanup, close, không double-complete. |
| Retry sau lỗi | Thử lại cùng ID | Idempotency/khả năng khôi phục, không tạo side effect trùng. |

Nên dùng một test double **đặt sẵn lịch trả về** (`0, 2, 1, -1, exception`), chứ không phụ thuộc `Thread.sleep` hoặc traffic thật để đạt nhánh logic. Integration test sau đó nên chạy trên local file, loopback TCP, volume/OS mục tiêu, với network delay và restart simulation phù hợp.

### Cách viết assertions

Không chỉ kiểm tra “không ném exception”. Một bộ test tốt xác nhận:

- **Nội dung chính xác**: so sánh byte arrays (`Arrays.equals`), không chỉ số bytes.
- **Không mất/không nhân đôi bytes**: tổng số bytes ghi đúng bằng payload length khi hoàn tất.
- **Vòng lặp không treo**: số lần gọi hoặc deadline giới hạn; test phải thất bại rõ nếu channel cứ trả `0`.
- **Buffer state**: `position, limit, remaining` ở từng bước đúng ý nghĩa.
- **Nhánh lỗi**: ghi nhận exception, không thực hiện commit/ACK sau lỗi.
- **Tài nguyên**: cả hai channel được đóng trong `try-with-resources` khi thành công và khi ném lỗi.
- **Tái thực thi**: với retry, business state không bị nhân đôi và có thể phân biệt uncommitted/committed.

## 9. Quan sát và chẩn đoán khi chạy thực tế

Khi sự cố chỉ xảy ra dưới tải, log nên giúp tách **short I/O bình thường** khỏi **lỗi I/O**:

- Operation ID, channel type, local/remote endpoint hoặc path đã được bảo vệ thông tin nhạy cảm.
- Offset và total expected bytes của file/record/frame.
- Bytes returned bởi từng call; số lần trả `0` và số lần short read/write.
- `ByteBuffer.position/limit/remaining` **trước và sau lời gọi thành công**, chú ý rằng buffer có thể không an toàn để suy luận trạng thái commit sau exception tùy API.
- Thời gian chờ readiness, deadline, số lượng pending bytes, queue length và retry count.
- Exception class, cause và socket/file lifecycle; không nuốt stack trace khi cần chẩn đoán.

Tránh log toàn bộ payload chứa token, PII hoặc binary khổng lồ. Dùng sample hoặc metadata đủ để tái dựng vấn đề; khi cần xác minh toàn vẹn có thể dùng checksum ở mức record.

Một ví dụ ngắn về log định hướng:

```text
op=send-order-142 expected=1024 written=512 remaining=512 result=SHORT_WRITE
op=send-order-142 expected=1024 written=768 remaining=256 result=SHORT_WRITE
op=send-order-142 result=IO_ERROR error=IOException commit=UNKNOWN
```

Đây là **log giả định để minh họa**, không phải stdout của chương trình trên. Trường `commit=UNKNOWN` nhắc rằng không thể suy từ byte count local rằng nghiệp vụ bên kia chưa làm gì.

## 10. Lỗi thường gặp và sửa chữa

| Sai lầm | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| Một `read` bằng cả message | TCP và channel có thể đọc ngắn | Parser tích lũy, length framing. |
| Một `write` gửi hết buffer | Channel có thể ghi ngắn hoặc 0 | Kiểm tra `hasRemaining` và ghi tiếp theo readiness. |
| Coi `read == 0` là EOF | EOF là `-1` | Xử lý 0 như chưa tiến triển. |
| Busy-loop `while(write==0)` | CPU 100% khi output buffer chưa sẵn sàng | `Selector`/backpressure/deadline. |
| Gọi `clear` khi còn bytes chưa write | Mất phần bytes chưa gửi | Chỉ clear sau khi tiêu thụ hết; dùng compact nếu cần. |
| Coi `IOException` như EOF | Lỗi và kết thúc bình thường khác semantics | Phân biệt exception, EOF, timeout. |
| Sau lỗi retry payload từ đầu | Có thể gây trùng side effect | Idempotency/resume/protocol ACK. |
| Sau lỗi giả định đã ghi đúng `position()` bytes bên remote | Local buffer không đo commit của peer | Theo dõi trạng thái ở protocol. |
| Test dựa vào sleep/network bất định | Flaky, khó tái hiện | Scripted fake channels/fault injection. |
| Chỉ test happy path | Không bắt được partial/truncation | Ma trận `0`/short/EOF/error/boundaries. |
| Giữ object buffer cho nhiều operation concurrent | Data race và trạng thái buffer sai | Một owner cho buffer tới completion. |
| Gọi `force` rồi coi file transaction nguyên tử | Durability khác atomicity | WAL/checksum/atomic publication/recovery. |

## 11. Checklist thực hành

1. Đã biết loại channel đang **blocking hay non-blocking** chưa?
2. Đã ghi đủ điều kiện dừng: `N bytes`, `EOF`, deadline hay protocol marker?
3. Đã phân biệt `0` với `-1` và `IOException`?
4. Có lưu phần `ByteBuffer.remaining()` sau short write không?
5. Sau `read` có `flip` đúng lúc và sau write có `clear/compact` đúng lúc không?
6. Có limit số bytes/frames để chống input bất hợp lệ và OOM không?
7. Vòng thử lại có bounded deadline/readiness, không busy-loop không?
8. Fixture có tạo được lịch partial + `0` + EOF + IOException deterministically không?
9. Test có assert **nội dung byte** và số lần tiến triển thay vì chỉ output console không?
10. Sau lỗi, ứng dụng có trạng thái uncertain/recovery/idempotency thay vì ACK sai không?
11. Đã log offset/bytes/exception an toàn, có đóng tài nguyên đúng vòng đời không?
12. Nếu dùng file thật hoặc network, đã có integration test trên provider/OS mục tiêu chưa?

## 12. Câu hỏi tự kiểm tra

**1. `read(dst)` trả `2` khi buffer còn chỗ cho 8 bytes có phải lỗi không?** Không; short read là hành vi hợp lệ.

**2. `read(dst)` trả `0` có nghĩa EOF?** Không. EOF của readable channel được báo bằng `-1`.

**3. `write(src)` trả `0` thì có được `src.clear()` không?** Không, vì bytes vẫn pending trong buffer.

**4. Đang đọc frame 5 bytes, mới được 2 bytes rồi `-1`: kết quả gì?** Truncated frame, thường báo `EOFException`.

**5. Sau `IOException` từ network write, có chắc server chưa xử lý request?** Không; cần acknowledgement/idempotency ở tầng ứng dụng.

**6. Vì sao test fake channel hữu ích hơn chỉ giới hạn băng thông mạng thật?** Vì fake channel kiểm soát thứ tự trả `0`, partial counts, EOF và exception, dễ lặp lại nhánh lỗi.

**7. Có nên dùng vòng `while (channel.write(buf) == 0)` liên tục trên non-blocking socket?** Không; nên chờ readiness và giới hạn thời gian để tránh CPU spin.

**8. Khi một lệnh `write` ném IOException, `ByteBuffer.position` có phải số byte chắc chắn đã tới disk/peer?** Không. Buffer state không phải application commit evidence.

## Tài liệu chính thức

- [Java SE 21 — ReadableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html): `read` có thể trả ít bytes hơn yêu cầu, 0 hoặc -1.
- [Java SE 21 — WritableByteChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html): `write` có thể ghi ngắn hoặc 0.
- [Java SE 21 — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `flip`, `clear`, `compact`, position/limit.
- [Java SE 21 — SocketChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking network read/write.
- [Java SE 21 — FileChannel](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): positional file I/O, IOException, `force`.
- [Java SE 21 — Selector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Selector.html): readiness-based non-blocking I/O.

**Tổng kết:** Đừng kiểm thử I/O bằng giả định mọi lần đọc/ghi đều đủ. Hãy chủ động mô phỏng **short read**, **short write**, `0`, EOF và lỗi giữa chừng; quan sát `ByteBuffer` đúng ranh giới và thiết kế recovery/idempotency khi đã chuyển một phần dữ liệu.