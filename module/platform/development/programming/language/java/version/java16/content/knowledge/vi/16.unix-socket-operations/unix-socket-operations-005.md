# Giới hạn bộ đệm, kích thước thông điệp và kiểm tra dữ liệu nhận

**Module:** `JAVA_VERSION_JAVA16`  
**Chương:** Vận hành socket  
**Áp dụng:** Java 16 trở lên; ví dụ dùng Unix-domain `SocketChannel`, `ByteBuffer` và `Selector`.

Unix-domain socket trong Java truyền dữ liệu qua `SocketChannel`. Kênh này cung cấp luồng byte; nó không giữ ranh giới thông điệp của ứng dụng. Một lần `write()` có thể được đọc thành nhiều lần, và một lần `read()` có thể nhận một phần frame hoặc dữ liệu của nhiều frame. Vì vậy, ứng dụng phải tự định nghĩa framing, giới hạn kích thước, quản lý bộ đệm và xác thực nội dung nhận được.

Nếu tin vào độ dài do client gửi, cấp phát bộ nhớ trước khi kiểm tra hoặc để hàng đợi tăng không giới hạn, một client cục bộ cũng có thể làm service cạn bộ nhớ và tài nguyên. Unix-domain socket giới hạn nơi có thể kết nối; nó không làm dữ liệu trở nên đáng tin cậy.

Một thiết kế an toàn cần bốn lớp:

1. **Framing:** xác định chính xác điểm bắt đầu và kết thúc của mỗi message.
2. **Giới hạn tài nguyên:** giới hạn byte mỗi frame, bộ đệm mỗi connection, hàng đợi và số connection đồng thời.
3. **Validation:** kiểm tra encoding, cấu trúc, kiểu, miền giá trị và quyền nghiệp vụ trước khi xử lý.
4. **Backpressure:** làm chậm hoặc tạm ngừng đọc khi consumer chưa xử lý kịp, tránh tích lũy dữ liệu vô hạn.

## 1. SocketChannel truyền byte, không truyền message

Không được giả định một lần ghi tương ứng một lần đọc:

```java
// Client
channel.write(ByteBuffer.wrap("HELLO".getBytes(StandardCharsets.UTF_8)));

// Server: read() có thể chỉ nhận "HE", sau đó nhận "LLO".
int count = channel.read(buffer);
```

Các tình huống thường gặp:

- Một frame bị chia thành nhiều lần `read()`.
- Một lần `read()` chứa phần cuối frame trước và đầu frame kế tiếp.
- `write()` ở non-blocking mode chỉ ghi một phần buffer.
- `read()` trả về `0` khi hiện chưa có byte để đọc trong non-blocking mode.
- `read()` trả về `-1` khi peer đã đóng đầu ra và không còn byte nào để đọc.

Do đó, gọi `read()` một lần rồi parse toàn bộ kết quả là lỗi giao thức. Ứng dụng phải giữ trạng thái parser qua nhiều lần đọc.

## 2. Chọn framing phù hợp

Một giao thức stream cần quy tắc xác định message boundary. Các cách phổ biến:

| Cách framing | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Fixed length | Mọi message có độ dài cố định | Bản tin rất nhỏ, cấu trúc cố định |
| Delimiter | Kết thúc bằng ký tự phân cách như newline | Text protocol có quy tắc escaping rõ |
| Length-prefix | Header chứa độ dài payload, sau đó là payload | Binary protocol, payload có độ dài thay đổi |
| TLV / structured framing | Header mô tả type, length và value | Giao thức cần nhiều loại trường hoặc mở rộng |

Với request/response nội bộ, length-prefix thường dễ kiểm tra. Ví dụ dùng header 4 byte big-endian chứa số byte payload:

```text
+----------------------+--------------------------+
| Length: 4 bytes      | Payload: Length bytes    |
+----------------------+--------------------------+
```

Header chỉ là dữ liệu do peer gửi; không được xem độ dài đó là đáng tin. Phải kiểm tra giới hạn trước khi cấp phát hoặc đọc payload.

## 3. Đặt giới hạn frame trước khi cấp phát bộ nhớ

Giả sử giao thức cho phép tối đa 256 KiB mỗi message:

```java
import java.net.ProtocolException;
import java.nio.ByteBuffer;

final class FrameEncoder {
    static final int MAX_FRAME_BYTES = 256 * 1024;

    static ByteBuffer encode(byte[] payload) throws ProtocolException {
        if (payload.length > MAX_FRAME_BYTES) {
            throw new ProtocolException("Frame exceeds configured limit");
        }

        ByteBuffer frame = ByteBuffer.allocate(
            Integer.BYTES + payload.length
        );
        frame.putInt(payload.length);
        frame.put(payload);
        frame.flip();
        return frame;
    }
}
```

Trình tự đúng:

1. Đọc đủ header cố định.
2. Parse length.
3. Từ chối length âm hoặc lớn hơn giới hạn.
4. Chỉ sau đó mới nhận/cấp phát vùng chứa payload.
5. Đọc đủ payload theo trạng thái hiện tại của connection.

Không làm theo thứ tự ngược lại, ví dụ `ByteBuffer.allocate(peerLength)` rồi mới kiểm tra `peerLength`. Giá trị lớn có thể gây `OutOfMemoryError`; giá trị âm có thể gây lỗi cấp phát; phép cộng header và length cũng có thể overflow nếu không kiểm tra.

Khi tính tổng kích thước, dùng kiểu đủ rộng hoặc kiểm tra trước phép cộng:

```java
long totalBytes = (long) Integer.BYTES + payloadLength;
if (payloadLength < 0 || payloadLength > MAX_FRAME_BYTES
        || totalBytes > MAX_FRAME_BYTES + (long) Integer.BYTES) {
    throw new ProtocolException("Invalid frame length");
}
```

Giới hạn cần được định nghĩa trong protocol và áp dụng nhất quán ở cả client lẫn server. Giới hạn phía client giúp phát hiện lỗi sớm; server vẫn phải tự kiểm tra vì client có thể không tuân thủ.

## 4. Bộ giải mã incremental cho length-prefix frame

Parser cần giữ các byte chưa đủ thành frame để ghép với lần đọc tiếp theo. Ví dụ sau minh họa decoder cho header 4 byte và payload tối đa 256 KiB:

```java
import java.net.ProtocolException;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

final class LengthPrefixedFrameDecoder {
    private static final int HEADER_BYTES = Integer.BYTES;
    private static final int MAX_FRAME_BYTES = 256 * 1024;

    private final ByteBuffer pending =
        ByteBuffer.allocate(HEADER_BYTES + MAX_FRAME_BYTES);

    List<byte[]> feed(ByteBuffer incoming) throws ProtocolException {
        List<byte[]> frames = new ArrayList<>();

        while (incoming.hasRemaining()) {
            if (!pending.hasRemaining()) {
                throw new ProtocolException("Frame buffer limit exceeded");
            }

            int count = Math.min(incoming.remaining(), pending.remaining());
            int oldLimit = incoming.limit();
            incoming.limit(incoming.position() + count);
            pending.put(incoming);
            incoming.limit(oldLimit);

            pending.flip();
            while (true) {
                if (pending.remaining() < HEADER_BYTES) {
                    break;
                }

                pending.mark();
                int length = pending.getInt();
                if (length < 0 || length > MAX_FRAME_BYTES) {
                    throw new ProtocolException("Invalid frame length: " + length);
                }

                if (pending.remaining() < length) {
                    pending.reset();
                    break;
                }

                byte[] payload = new byte[length];
                pending.get(payload);
                frames.add(payload);
            }
            pending.compact();
        }

        return frames;
    }

    boolean hasIncompleteFrame() {
        return pending.position() != 0;
    }
}
```

Các thao tác buffer quan trọng:

- `flip()` chuyển từ chế độ ghi byte sang đọc byte đã nhận.
- `mark()` lưu vị trí đầu header để có thể quay lại nếu payload chưa đủ.
- `reset()` trở về đầu header khi cần đợi thêm byte.
- `compact()` giữ lại phần byte chưa xử lý và đưa buffer về chế độ ghi tiếp.

Decoder không giả định một lần `feed()` chỉ có một frame. Nó có thể trả về không frame nào, một frame hoặc nhiều frame. Trong ứng dụng thật, khi decoder ném `ProtocolException`, hãy xem connection là vi phạm protocol và đóng nó; không tiếp tục parse từ trạng thái lỗi.

Ví dụ dùng một buffer tối đa 256 KiB cho mỗi connection. Đây là giới hạn dễ hiểu nhưng có chi phí bộ nhớ cố định cho mỗi decoder. Nếu có rất nhiều connection, hãy chọn giới hạn nhỏ hơn hoặc triển khai buffer tăng dần có trần cứng; tuyệt đối không cho buffer phát triển không giới hạn.

## 5. Đọc non-blocking và xử lý partial read

Với `SocketChannel` non-blocking, một vòng đọc thường có dạng:

```java
ByteBuffer readBuffer = ByteBuffer.allocate(16 * 1024);
LengthPrefixedFrameDecoder decoder = new LengthPrefixedFrameDecoder();

int count = channel.read(readBuffer);
if (count == -1) {
    if (decoder.hasIncompleteFrame()) {
        // Peer đóng giữa header/payload: protocol frame bị cắt cụt.
    }
    // Đóng connection sau khi xử lý trạng thái EOF.
} else if (count > 0) {
    readBuffer.flip();
    List<byte[]> frames = decoder.feed(readBuffer);
    readBuffer.clear();

    for (byte[] frame : frames) {
        validateAndHandle(frame);
    }
}
```

Trong selector loop, chỉ đọc khi key báo `OP_READ`. Khi `read()` trả `0`, chờ sự kiện tiếp theo thay vì quay vòng liên tục. Khi trả `-1`, đóng connection và kiểm tra xem parser có dữ liệu dang dở hay không; EOF giữa một frame phải được xem là message bị cắt cụt.

Không giữ nguyên buffer ở trạng thái đọc rồi tiếp tục gọi `channel.read()` vào nó. Sau khi decoder đã lấy dữ liệu, cần `clear()` hoặc `compact()` theo chiến lược buffer của ứng dụng để chuẩn bị vùng ghi tiếp theo.

## 6. Ghi message đầy đủ và giới hạn hàng đợi outbound

Non-blocking `write()` có thể chỉ ghi một phần buffer. Giữ lại buffer cho đến khi mọi byte được ghi:

```java
ByteBuffer frame = FrameEncoder.encode(payload);

int written = channel.write(frame);
if (frame.hasRemaining()) {
    // Lưu frame vào outbound queue của connection.
    // Bật OP_WRITE để selector báo khi channel sẵn sàng ghi tiếp.
    key.interestOps(key.interestOps() | SelectionKey.OP_WRITE);
}
```

Khi nhận `OP_WRITE`, tiếp tục ghi buffer đầu hàng đợi cho đến khi:

- Buffer được ghi hết: bỏ buffer khỏi queue.
- `write()` trả `0`: dừng và đợi readiness tiếp theo.
- Connection lỗi/đóng: giải phóng queue và đóng channel.

Chỉ đăng ký `OP_WRITE` khi thực sự có dữ liệu chờ ghi. Socket thường xuyên sẵn sàng ghi; giữ `OP_WRITE` liên tục có thể làm selector thức dậy liên tục và gây busy loop.

Đặt giới hạn tổng byte outbound đang chờ cho mỗi connection và cho toàn service. Khi vượt ngưỡng, từ chối message mới, tạm ngừng nhận thêm request hoặc đóng client chậm theo chính sách. Không để một client đọc chậm khiến queue phản hồi tăng vô hạn.

## 7. Phân biệt buffer ứng dụng với socket buffer của hệ điều hành

Có nhiều lớp buffer khác nhau:

| Loại buffer | Nơi quản lý | Vai trò |
| --- | --- | --- |
| `ByteBuffer` đọc/ghi | Ứng dụng Java | Lưu byte ứng dụng đang xử lý |
| Decoder/frame buffer | Ứng dụng Java | Ghép header và payload, giữ frame chưa hoàn chỉnh |
| Outbound queue | Ứng dụng Java | Giữ dữ liệu chưa ghi hết |
| Kernel receive/send buffer | Hệ điều hành | Đệm byte giữa tiến trình và socket endpoint |

`SO_RCVBUF` và `SO_SNDBUF`, khi provider và hệ điều hành hỗ trợ cho channel, điều chỉnh buffer ở tầng socket/kernel. Chúng không định nghĩa message boundary, không thay thế giới hạn frame và không xác thực dữ liệu. Tăng socket buffer cũng không giải quyết được một ứng dụng để queue vô hạn.

Với Unix-domain socket, khả năng hỗ trợ và ý nghĩa của từng socket option có thể phụ thuộc provider/hệ điều hành. Chỉ cấu hình option sau khi kiểm tra hỗ trợ trong môi trường đích; không dùng nó như một cam kết portable về kích thước message.

## 8. Kiểm tra encoding trước khi xử lý text

Nếu payload là UTF-8, không giả định mọi dãy byte đều là UTF-8 hợp lệ. Dùng decoder với chính sách báo lỗi cho chuỗi malformed/unmappable:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

static String decodeUtf8(byte[] payload)
        throws CharacterCodingException {
    return StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(ByteBuffer.wrap(payload))
        .toString();
}
```

Chính sách mặc định thay thế byte lỗi bằng ký tự thay thế có thể làm hai dữ liệu khác nhau trở thành cùng chuỗi sau decode. Với protocol yêu cầu dữ liệu chính xác, nên từ chối encoding không hợp lệ.

Đối với binary payload, không decode thành String. Dùng parser theo định dạng nhị phân và kiểm tra length/type trước khi đọc field.

## 9. Validate cấu trúc và miền giá trị của dữ liệu

Sau framing và decoding, dữ liệu vẫn chưa đáng tin. Kiểm tra theo nhiều lớp:

1. **Cấu trúc:** header, version, field bắt buộc, số field và thứ tự field.
2. **Kiểu:** integer có parse được không, boolean/enum có đúng biểu diễn không.
3. **Miền giá trị:** số lượng, thời gian, độ dài tên và trạng thái có nằm trong range cho phép không.
4. **Ngữ nghĩa:** các field có nhất quán với nhau và với trạng thái nghiệp vụ không.
5. **Danh tính/quyền:** client đã được xác thực và có quyền thực hiện thao tác này không.

Ví dụ, một request `TRANSFER` có thể cần:

| Field | Validation |
| --- | --- |
| `requestId` | Bắt buộc, giới hạn độ dài và định dạng |
| `operation` | Chỉ nhận enum trong allowlist |
| `amount` | Số dương, không vượt giới hạn nghiệp vụ |
| `currency` | Chỉ nhận mã tiền tệ được hỗ trợ |
| `accountId` | Định dạng hợp lệ và caller có quyền truy cập |

Không chỉ kiểm tra JSON/XML/binary parse thành công rồi tin mọi giá trị. Dữ liệu có cấu trúc đúng vẫn có thể vi phạm giới hạn nghiệp vụ hoặc cố truy cập tài nguyên không được phép.

## 10. Chống cấp phát và xử lý quá mức

Một số quy tắc bảo vệ quan trọng:

- Đặt `MAX_FRAME_BYTES` và từ chối length vượt ngưỡng trước khi allocate.
- Giới hạn số frame và tổng byte có thể chờ xử lý trên mỗi connection.
- Giới hạn số connection đồng thời và tổng memory budget toàn service.
- Giới hạn độ sâu cấu trúc lồng nhau, số phần tử collection và kích thước string.
- Giới hạn thời gian nhận đủ frame; không để client gửi từng byte rất chậm vô hạn.
- Đóng connection vi phạm protocol thay vì cố phục hồi một parser đã mất đồng bộ.
- Tránh log toàn bộ payload không tin cậy; log request ID, loại lỗi và số byte cần thiết.

Ví dụ, nếu decoder giữ tối đa 256 KiB mỗi connection, 2.000 connection có thể cần khoảng 500 MiB chỉ cho vùng frame buffer, chưa tính read buffer, outbound queue, object và heap khác. Giới hạn từng connection phải được nhân với concurrency thực tế để xác định ngân sách tổng.

Nếu cần hỗ trợ frame lớn, cân nhắc streaming payload theo chunk vào file hoặc consumer có giới hạn thay vì giữ toàn bộ frame trong heap. Vẫn phải có giới hạn tổng byte, quota lưu trữ và timeout.

## 11. Backpressure khi producer nhanh hơn consumer

Giới hạn frame riêng lẻ không đủ nếu client gửi hàng nghìn frame hợp lệ trong khi server xử lý chậm. Cần giới hạn lượng công việc đang chờ:

- Giới hạn số message pending trên mỗi connection.
- Giới hạn tổng byte đang chờ trong hàng đợi xử lý.
- Tạm ngừng đăng ký `OP_READ` khi queue đạt high-water mark.
- Đăng ký lại `OP_READ` khi consumer xử lý xuống dưới low-water mark.
- Giới hạn outbound queue và xử lý client không đọc response.
- Có chính sách từ chối, giảm tải hoặc đóng connection khi vượt hard limit.

High-water/low-water mark giúp tránh bật/tắt đọc liên tục quanh một ngưỡng duy nhất. Với hệ thống dùng executor, queue của executor cũng phải bounded; thread pool có kích thước cố định nhưng queue vô hạn vẫn có thể làm cạn heap.

## 12. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Một lần `write()` luôn tương ứng một lần `read()`. | **Sai** | SocketChannel truyền stream byte, không giữ ranh giới message. |
| `read()` trả về `0` nghĩa là peer đã đóng connection. | **Sai** | Trong non-blocking mode, hiện chưa có dữ liệu để đọc. |
| Có thể allocate buffer theo length từ peer rồi kiểm tra sau. | **Sai** | Phải validate length trước khi cấp phát. |
| `ByteBuffer` capacity là giới hạn message của protocol. | **Sai** | Capacity chỉ là giới hạn buffer cụ thể; protocol phải định nghĩa giới hạn riêng. |
| `SO_RCVBUF` thay thế max frame. | **Sai** | Kernel socket buffer không định nghĩa message size hoặc schema. |
| Decoder có thể trả nhiều frame cho một lần feed. | **Đúng** | Một lần đọc có thể chứa nhiều message. |
| UTF-8 decode mặc định luôn từ chối byte lỗi. | **Sai** | Cần cấu hình `CodingErrorAction.REPORT` nếu muốn từ chối. |
| Giới hạn mỗi frame là đủ chống memory exhaustion. | **Sai** | Còn phải giới hạn connection, queue và tổng byte pending. |
| Backpressure có thể tạm ngừng `OP_READ`. | **Đúng** | Điều này làm giảm tốc độ nhận khi consumer chưa xử lý kịp. |

## 13. Checklist giới hạn buffer và kiểm tra input

1. Protocol có framing rõ ràng và được version hóa không?
2. Length header có được kiểm tra âm, quá lớn và overflow trước allocate không?
3. Có giới hạn kích thước frame ở cả client và server không?
4. Parser có giữ trạng thái qua partial read và xử lý nhiều frame trong một lần đọc không?
5. EOF giữa header/payload có được xem là frame không hoàn chỉnh không?
6. Outbound code có xử lý partial write và giữ buffer cho đến khi ghi hết không?
7. `OP_WRITE` chỉ được bật khi queue còn dữ liệu không?
8. Có giới hạn decoder buffer, read buffer, outbound queue và executor queue không?
9. Có ngân sách tổng theo số connection đồng thời không?
10. Text payload có kiểm tra encoding nghiêm ngặt không?
11. Field có được kiểm tra kiểu, range, schema và quyền nghiệp vụ không?
12. Có backpressure và timeout cho client gửi chậm/đọc chậm không?
13. Có phân biệt kernel socket buffer với application frame limit không?
14. Log có tránh ghi toàn bộ payload nhạy cảm hoặc không tin cậy không?

**Ghi nhớ:** `SocketChannel` cung cấp luồng byte, vì vậy ứng dụng phải tự định nghĩa framing và xử lý partial I/O. Đọc length header, kiểm tra giới hạn trước khi allocate, giữ parser state qua nhiều lần đọc, xác thực encoding/schema/domain và giới hạn cả queue lẫn tổng tài nguyên. Kernel socket buffer không thay thế max frame; backpressure giúp service giữ mức sử dụng bộ nhớ trong ngân sách khi client gửi nhanh hơn khả năng xử lý.

## Tài liệu chính thức

- [JEP 380 — Unix-Domain Socket Channels, Java 16](https://openjdk.org/jeps/380).
- [Java SE 26 API — `SocketChannel`, stream I/O và partial read/write](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/SocketChannel.html).
- [Java SE 26 API — `ByteBuffer`, flip/compact/mark/reset](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html).
- [Java SE 26 API — `Selector` và `SelectionKey`, readiness operations](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/channels/Selector.html).
- [Java SE 26 API — `CharsetDecoder` và `CodingErrorAction`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
- [Java SE 26 API — `StandardSocketOptions`, SO_RCVBUF và SO_SNDBUF](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/StandardSocketOptions.html).
