# ByteBuffer chứa dữ liệu ứng dụng và dữ liệu mạng

## 1. SSLEngine không tự đọc hoặc ghi socket

`SSLEngine` xử lý giao thức TLS trên các buffer byte. Mã ứng dụng chịu trách nhiệm chuyển dữ liệu giữa engine và hệ thống I/O.

Có hai loại dữ liệu khác nhau:

- **Dữ liệu ứng dụng:** byte mà giao thức phía trên TLS gửi hoặc nhận, chẳng hạn nội dung HTTP.
- **Dữ liệu mạng:** byte bản ghi TLS được chuyển qua kết nối, gồm cả dữ liệu giao thức/bắt tay và dữ liệu được bảo vệ.

Luồng khái quát:

```text
Gửi:
Ứng dụng → appOut → wrap() → netOut → socket

Nhận:
Socket → netIn → unwrap() → appIn → ứng dụng
```

Không gửi trực tiếp appOut ra socket nếu đó là đường truyền phải qua TLS. Cũng không giải mã netIn thành chuỗi ứng dụng trước khi nó được engine xử lý thành dữ liệu ứng dụng.

Tính độc lập với transport là đặc điểm cốt lõi của [SSLEngine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html).

## 2. Bốn buffer và quyền đọc/ghi

Tên biến không bắt buộc, nhưng một quy ước dễ theo dõi là:

| Buffer | Nội dung | Bên ghi | Bên đọc |
| --- | --- | --- | --- |
| `appOut` | Byte ứng dụng đang chờ gửi | Ứng dụng | `wrap` |
| `netOut` | Byte TLS đang chờ chuyển đi | `wrap` | Socket/channel |
| `netIn` | Byte TLS đã nhận, chưa xử lý hết | Socket/channel | `unwrap` |
| `appIn` | Byte ứng dụng đã được engine tạo | `unwrap` | Ứng dụng |

“Mạng” không đồng nghĩa mỗi byte trong buffer đều là phần ứng dụng đã mã hóa. Trong lúc bắt tay, netOut có thể chứa thông điệp giao thức mà appOut chưa bị tiêu thụ.

Tương tự, unwrap có thể xử lý dữ liệu bắt tay nhưng chưa sinh byte ứng dụng nào. Đếm số byte ở hai phía không tạo một quan hệ một-một cho từng lời gọi.

## 3. Position, limit và remaining là trạng thái sống của buffer

ByteBuffer không có một trường riêng tên “read mode” hoặc “write mode”. Đây là quy ước mà chương trình duy trì qua position và limit:

```text
Chế độ ghi thông thường:
[0 ... position) chứa byte đã được ghi
[position ... limit) là chỗ còn ghi được

Chế độ đọc thông thường:
[position ... limit) chứa byte chưa được đọc/tiêu thụ
```

Các thao tác cần hiểu đúng:

| Thao tác | Tác dụng điển hình |
| --- | --- |
| `flip()` | Đặt limit bằng position hiện tại, rồi position về 0 để đọc phần vừa ghi |
| `compact()` | Dồn phần chưa đọc về đầu, đặt position sau phần đó để ghi thêm |
| `clear()` | Position về 0, limit về capacity; không giữ ranh giới dữ liệu chưa xử lý |
| `remaining()` | `limit - position`, ý nghĩa phụ thuộc quy ước đọc/ghi hiện tại |

`clear()` không xóa vật lý mọi byte trong bộ nhớ. Nhưng nó làm mất cách biểu diễn phần đang chờ nếu chương trình còn cần giữ các byte cũ.

`flip()` cũng không sao chép dữ liệu; nó đổi các mốc điều khiển. Xem [ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html).

Không gọi flip theo thói quen sau mọi lời gọi engine. Trước hết phải biết buffer đang được bên nào đọc hoặc ghi và những byte nào còn cần giữ.

## 4. Chiều gửi: appOut đọc, netOut ghi

Trước một lần wrap thông thường:

- appOut ở quy ước đọc, chỉ phần byte ứng dụng đang chờ xử lý.
- netOut có chỗ ghi, ở quy ước ghi.

```java
// Mã minh họa; không phải toàn bộ vòng xử lý TLS.
SSLEngineResult result = engine.wrap(appOut, netOut);
```

Engine cập nhật position tương ứng với số byte đã tiêu thụ và tạo ra.

Sau đó netOut cần được chuyển sang quy ước đọc trước khi ghi ra socket:

```java
// Mã minh họa: netOut vừa được wrap ghi dữ liệu.
netOut.flip();
while (netOut.hasRemaining()) {
    int written = channel.write(netOut);
    if (written == 0) {
        // Giữ nguyên position/limit và tiếp tục khi kênh có thể ghi.
        return;
    }
}
netOut.clear();
```

Đoạn trên thể hiện một chính sách đơn giản: gửi hết netOut trước khi dùng nó để nhận thêm dữ liệu từ wrap.

Nếu channel chỉ ghi được một phần, không clear netOut. Byte còn lại vẫn thuộc bản ghi cần chuyển đi.

Cũng không flip lại buffer đang đọc dở, vì việc đó có thể đặt limit theo một position đã tiến qua một phần dữ liệu và làm sai phạm vi còn chờ.

### appOut có thể chưa được tiêu thụ hết

Một lần wrap không có nghĩa mọi dữ liệu ứng dụng đã được engine nhận. Byte còn lại trong appOut phải được giữ cho lần xử lý sau.

Đặc biệt, khi engine cần tiến triển bắt tay, nó có thể tạo byte mạng mà chưa nhận byte ứng dụng nào.

## 5. Chiều nhận: netIn đọc, appIn ghi

Một chu kỳ thường có dạng:

```text
netIn ở quy ước ghi
    ↓ socket đọc thêm byte vào netIn
netIn.flip()
    ↓
engine.unwrap(netIn, appIn)
    ↓
giữ byte mạng chưa tiêu thụ, xử lý dữ liệu ứng dụng vừa có
    ↓
netIn.compact() khi chuẩn bị nhận thêm byte mạng
```

Không giả định một lần đọc socket là một bản ghi TLS hoàn chỉnh. Nó có thể chỉ chứa một phần bản ghi hoặc chứa nhiều bản ghi.

Cũng không giả định một bản ghi TLS là một thông điệp hoàn chỉnh của giao thức ứng dụng. Sau unwrap, appIn vẫn là một luồng byte cần được giao thức phía trên phân khung.

Khi ứng dụng đọc appIn:

```java
// Mã minh họa: appIn đang ở quy ước ghi sau unwrap.
appIn.flip();
consumeAvailableApplicationBytes(appIn);
appIn.compact();
```

`consumeAvailableApplicationBytes` phải tiến position cho phần thực sự đã dùng. Nếu một thông điệp ứng dụng mới có một nửa, giữ phần đó lại khi compact thay vì bỏ đi.

## 6. Lấy kích thước ban đầu từ SSLSession

Session cung cấp hai kích thước theo tình trạng hiện tại:

```java
SSLSession session = engine.getSession();

int applicationSize = session.getApplicationBufferSize();
int packetSize = session.getPacketBufferSize();
```

- applicationSize gợi ý dung lượng cho dữ liệu ứng dụng lớn nhất được dự kiến.
- packetSize gợi ý dung lượng cho dữ liệu mạng/bản ghi TLS được dự kiến.

Xem [SSLSession](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLSession.html).

Không dùng applicationSize thay cho packetSize chỉ vì cả hai đều là số byte. Bản ghi TLS có cấu trúc và phần chi phí giao thức ngoài dữ liệu ứng dụng.

Cũng không đóng đinh một kích thước record vào mã rồi coi mọi phiên TLS, provider và giai đoạn kết nối giống nhau. Khi engine báo cần thêm dung lượng, đọc lại yêu cầu session hiện tại và xử lý trạng thái.

Dung lượng cần cho một kết quả engine còn khác với tổng lượng dữ liệu đang xếp hàng trong ứng dụng. Nếu nhiều request cùng chờ gửi, phải có chính sách hàng đợi và áp lực ngược riêng; không chỉ tăng một ByteBuffer vô hạn.

## 7. BUFFER_UNDERFLOW và BUFFER_OVERFLOW thuộc hai vấn đề khác nhau

| Trạng thái | Ý nghĩa cần kiểm tra |
| --- | --- |
| `BUFFER_UNDERFLOW` từ unwrap | Chưa đủ dữ liệu mạng để xử lý phần cần thiết |
| `BUFFER_OVERFLOW` | Buffer đích không đủ chỗ cho kết quả của thao tác |
| `OK` | Thao tác hoàn tất theo trạng thái đó; vẫn cần xem byte và trạng thái bắt tay |
| `CLOSED` | Một phía hoạt động của engine đã đóng theo kết quả; vẫn phải xử lý byte đã tạo nếu có |

Với overflow:

- Trong wrap, đích thường là netOut.
- Trong unwrap, đích thường là appIn.

Không thấy overflow rồi tăng netIn một cách máy móc.

Với underflow, tăng appIn cũng không tạo ra các byte TLS còn thiếu. Cần giữ phần netIn chưa tiêu thụ rồi nhận thêm dữ liệu, hoặc tăng khả năng chứa của netIn nếu yêu cầu packet hiện tại lớn hơn dung lượng đang có.

Nếu buffer đã đầy mà trạng thái không tiến triển, phải xét giới hạn và lỗi giao thức. Không phản ứng bằng việc cấp phát tăng mãi với mọi dữ liệu đầu vào.

## 8. Giữ đúng phần dữ liệu khi tăng buffer

Một helper cho buffer **đang ở quy ước ghi** có thể:

1. Tạo buffer mới đủ lớn.
2. Flip buffer cũ để đọc phần đã ghi.
3. Chép phần đó sang buffer mới.
4. Để buffer mới tiếp tục ở quy ước ghi.

```java
// Mã minh họa cho heap buffer đang ở write mode.
ByteBuffer replacement = ByteBuffer.allocate(newCapacity);
old.flip();
replacement.put(old);
// replacement.position() ở sau phần dữ liệu đã giữ.
```

Nếu buffer cũ đang ở quy ước đọc, phần cần giữ thường là `[position, limit)`. Không flip nó theo cùng helper phía trên, vì sẽ đổi phạm vi sang phần đã đi qua thay vì phần đang chờ.

Cần viết và đặt tên helper theo trạng thái đầu vào/đầu ra, không chỉ gọi chung là resize.

Khi tăng buffer thật, còn cần giữ chính sách heap/direct, giới hạn capacity, cách xử lý tràn số khi tính kích thước và yêu cầu vòng đời của ứng dụng.

## 9. Ví dụ đầy đủ: byte bắt tay, fragment và compact

Ví dụ sau không mở socket và không thực hiện một phiên TLS hoàn chỉnh:

- Engine client tạo thông điệp bắt tay đầu tiên.
- Dữ liệu HELLO đang chờ gửi vẫn chưa bị tiêu thụ.
- Chỉ ba byte đầu của dữ liệu bắt tay được đưa vào engine server.
- Server báo underflow; compact giữ lại ba byte còn chờ.
- Một buffer khác minh họa tăng dung lượng mà không mất byte đã ghi.

Tệp `EngineBufferDemo.java`, chạy trên JDK 17 trở lên với JSSE mặc định:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLSession;

public class EngineBufferDemo {
    private static ByteBuffer growWriteBuffer(ByteBuffer old, int required) {
        int newCapacity = Math.max(Math.multiplyExact(old.capacity(), 2), required);
        ByteBuffer replacement = ByteBuffer.allocate(newCapacity);
        old.flip();
        replacement.put(old);
        return replacement;
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);

        SSLEngine client = context.createSSLEngine("example.test", 443);
        client.setUseClientMode(true);
        SSLSession session = client.getSession();

        ByteBuffer appOut = ByteBuffer.wrap(
                "HELLO".getBytes(StandardCharsets.UTF_8));
        ByteBuffer netOut = ByteBuffer.allocate(session.getPacketBufferSize());

        client.beginHandshake();
        SSLEngineResult sent = client.wrap(appOut, netOut);
        if (sent.getStatus() != SSLEngineResult.Status.OK || netOut.position() < 3) {
            throw new IllegalStateException("Expected initial handshake output");
        }

        System.out.println("handshakeOutput=true");
        System.out.println("applicationBytesConsumed=" + sent.bytesConsumed());
        System.out.println("plaintextRemaining=" + appOut.remaining());

        netOut.flip();
        byte[] firstThree = new byte[3];
        netOut.duplicate().get(firstThree);

        SSLEngine server = context.createSSLEngine();
        server.setUseClientMode(false);
        server.beginHandshake();
        ByteBuffer appIn = ByteBuffer.allocate(
                server.getSession().getApplicationBufferSize());
        ByteBuffer netIn = ByteBuffer.allocate(
                server.getSession().getPacketBufferSize());
        netIn.put(firstThree);
        netIn.flip();
        SSLEngineResult received = server.unwrap(netIn, appIn);
        System.out.println("underflow="
                + (received.getStatus() == SSLEngineResult.Status.BUFFER_UNDERFLOW));
        netIn.compact();
        System.out.println("preservedNetworkBytes=" + netIn.position());

        ByteBuffer pending = ByteBuffer.allocate(4);
        pending.put(new byte[]{1, 2, 3});
        pending = growWriteBuffer(pending, 8);
        System.out.println("grownPosition=" + pending.position());
        pending.flip();
        System.out.println("grownData="
                + pending.get() + "," + pending.get() + "," + pending.get());

        client.closeOutbound();
        server.closeOutbound();
    }
}
```

Biên dịch và chạy:

```shell
javac EngineBufferDemo.java
java EngineBufferDemo
```

Kết quả:

```text
handshakeOutput=true
applicationBytesConsumed=0
plaintextRemaining=5
underflow=true
preservedNetworkBytes=3
grownPosition=3
grownData=1,2,3
```

Giải thích:

- Client có dữ liệu bắt tay để gửi, dù HELLO chưa được nhận vào phần dữ liệu ứng dụng của TLS.
- `bytesConsumed=0` không có nghĩa thao tác không tạo đầu ra mạng.
- Ba byte đầu không đủ cho một bản ghi cần được unwrap.
- Engine chưa tiêu thụ fragment đó; compact giữ lại nó ở đầu netIn và position trở thành 3.
- Helper tăng buffer trong quy ước ghi giữ đúng dãy 1,2,3 và position tương ứng.

Hostname `example.test` chỉ là thông tin peer truyền cho engine trong minh họa; không có thao tác kết nối mạng đến tên đó.

Do không hoàn tất bắt tay, ví dụ không xác thực chứng chỉ đối tác và không chứng minh đã có một kênh TLS để gửi HELLO. Cấu hình danh tính, độ tin cậy, trạng thái bắt tay và truyền close_notify thuộc vòng đời kết nối thực tế.

Hai lời gọi closeOutbound ở cuối chỉ thay đổi trạng thái cục bộ của các engine trong minh họa. Trong một kết nối thật, dữ liệu đóng do engine tạo còn phải được wrap và chuyển đi đúng giao thức.

## 10. SSLEngineResult và position phải được đọc cùng nhau

Sau mỗi wrap/unwrap, xem:

```java
result.getStatus();
result.getHandshakeStatus();
result.bytesConsumed();
result.bytesProduced();
```

Xem [SSLEngineResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.html).

Thông thường position nguồn tăng theo bytesConsumed và position đích tăng theo bytesProduced. Nhưng hai số này không tự nói byte đã đến peer hoặc đã được ứng dụng xử lý.

```text
wrap đã tiêu thụ appOut
    ≠ netOut đã được socket gửi hết

socket đã đọc vào netIn
    ≠ unwrap đã nhận được một bản ghi đầy đủ

unwrap đã tạo appIn
    ≠ giao thức ứng dụng đã nhận một thông điệp hoàn chỉnh
```

Nếu cả hai số bằng 0, đừng lặp lại vô hạn mà không đổi điều kiện. Engine có thể cần thêm byte mạng, thêm chỗ đích, một thao tác bắt tay khác hoặc delegated task.

BUFFER_OVERFLOW/UNDERFLOW và HandshakeStatus là hai trục trạng thái khác nhau. Xử lý dung lượng buffer đúng chưa đủ để hoàn tất vòng điều khiển TLS. Hướng dẫn vòng đời này nằm trong [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html).

## 11. Partial write và áp lực ngược phải được giữ qua các lượt sự kiện

Với kênh không chặn, một lần write có thể ghi ít hơn số byte còn trong netOut, hoặc trả 0.

Khi đó:

- Giữ position và limit hiện tại.
- Đăng ký/chờ khả năng ghi theo mô hình I/O đang dùng.
- Không sinh quá nhiều đầu ra mới khi đầu ra cũ chưa thoát.
- Không dùng clear để “làm trống” chỉ nhằm tiếp tục wrap.

Tương tự, nếu appIn đầy vì ứng dụng chưa xử lý dữ liệu, phải cho phía ứng dụng tiêu thụ hoặc áp dụng áp lực ngược. Cứ cấp phát thêm mà không có giới hạn có thể làm bộ nhớ tăng theo tốc độ peer gửi.

Một byte đã nằm trong netOut còn là dữ liệu đang thuộc trách nhiệm gửi của kết nối. Một byte đã nằm trong appIn còn là dữ liệu ứng dụng chưa được tiêu thụ. Chương trình phải quản lý các nghĩa vụ đó khi chuyển giữa các sự kiện đọc/ghi.

## 12. Buffer mạng không phải nơi giải mã văn bản

TLS cung cấp dữ liệu ứng dụng dạng byte. Nếu ứng dụng dùng UTF-8 hoặc một charset khác, việc giải mã diễn ra sau unwrap trên dữ liệu appIn.

Một ký tự UTF-8 có thể bị chia giữa hai lần tạo dữ liệu ứng dụng. Không chuyển độc lập từng mảnh bằng một constructor String rồi giả định ranh giới mảnh trùng ranh giới ký tự.

Dùng bộ giải mã theo luồng và giữ byte chưa đủ để tạo ký tự theo giao thức giải mã. Đó là một tầng trạng thái khác với việc giữ fragment bản ghi TLS trong netIn.

Tương tự, một thông điệp JSON, HTTP hoặc giao thức nhị phân có thể bị chia qua nhiều bản ghi TLS. Không dựa vào số lần unwrap để phân tách thông điệp ứng dụng.

## 13. Heap, direct và chia sẻ đối tượng

ByteBuffer heap và direct đều có thể dùng theo hợp đồng của engine khi phù hợp, nhưng không có quy tắc mọi buffer direct đều nhanh hơn.

Chọn theo provider, mô hình I/O và phép đo. Buffer direct còn có chi phí cấp phát/vòng đời và ngân sách bộ nhớ khác heap.

Cũng không coi `duplicate()` là bản sao byte độc lập. Nó tạo một view có các mốc vị trí riêng nhưng chia sẻ nội dung nền. Trong ví dụ, duplicate chỉ đọc ba byte mà không làm netOut gốc tiến position.

Nếu hai luồng sửa nội dung hoặc position của cùng buffer ngoài một giao thức sở hữu rõ, có thể làm hỏng luồng dữ liệu. Ngay cả khi tách công việc đọc mạng và xử lý ứng dụng, phải xác định ai được truy cập từng buffer ở từng giai đoạn.

## 14. Tự kiểm tra trước khi gọi engine

Với mỗi buffer, hãy trả lời:

1. Nó đang chứa byte ứng dụng hay byte mạng?
2. Đang ở quy ước đọc hay ghi?
3. Phần nào đã tiêu thụ, phần nào còn phải giữ?
4. Thao tác sắp gọi sẽ đọc hay ghi buffer đó?
5. Khi thiếu đầu vào hoặc thiếu chỗ, điều kiện nào cần thay đổi?
6. Có giới hạn bộ nhớ và chính sách áp lực ngược không?

Bài tập:

- Thay compact của netIn bằng clear sau underflow: ba byte fragment không còn được giữ đúng trong vùng chờ xử lý.
- Gọi flip thêm lần nữa lên netOut đang gửi dở: theo dõi position/limit để thấy phạm vi dữ liệu bị thay đổi sai.
- Giảm dung lượng đích của wrap hoặc unwrap: xác định buffer nào cần thêm chỗ khi có overflow.
- Đưa một mảnh thông điệp ứng dụng chưa đầy đủ vào appIn: vì sao bên ứng dụng cũng phải giữ phần dư sau khi đọc?

Nguyên tắc là **giữ rõ loại byte, chiều chuyển dữ liệu và trạng thái position/limit ở mọi ranh giới giữa ứng dụng, SSLEngine và transport**.
