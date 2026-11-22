# NEED_WRAP, NEED_UNWRAP và NEED_TASK trong SSLEngine

## 1. Ba trạng thái trả lời câu hỏi nào?

Khi tích hợp TLS với vòng lặp sự kiện, ứng dụng cần biết bước tiếp theo là tạo dữ liệu gửi đi, xử lý dữ liệu nhận vào hay chạy công việc tính toán. `SSLEngineResult.HandshakeStatus` biểu diễn nhu cầu đó. Ba giá trị chính của bài này là `NEED_WRAP`, `NEED_UNWRAP` và `NEED_TASK`.

`SSLEngine` không tự đọc hoặc ghi socket. Hãy hình dung engine là bộ xử lý TLS; ứng dụng giữ bộ đệm và vận chuyển byte. Vì vậy, một trạng thái yêu cầu hành động của ứng dụng, không có nghĩa hành động mạng đã xảy ra. Mô hình này vẫn áp dụng trên JDK hiện đại; tên chủ đề Java 5 nói đến nguồn gốc API, không yêu cầu chạy Java 5 hay bật giao thức cũ. Xem [API SSLEngine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html).

| Trạng thái | Việc ứng dụng cần tổ chức |
| --- | --- |
| `NEED_WRAP` | Gọi `wrap()` để engine tạo dữ liệu TLS, rồi chuyển số byte tạo ra đến đối tác |
| `NEED_UNWRAP` | Đưa dữ liệu TLS nhận được vào `unwrap()`; nếu dữ liệu chưa đủ thì nhận thêm |
| `NEED_TASK` | Lấy tác vụ bằng `getDelegatedTask()`, thực thi và đợi chúng hoàn tất trước khi tiếp tục engine |

Các trạng thái được hiểu từ phía engine cục bộ. Nếu máy khách cần gửi thì máy chủ có thể đang chờ nhận. Không được suy ra trạng thái của máy này từ trạng thái của máy kia, hoặc gắn cứng một chuỗi chuyển trạng thái cho mọi phiên TLS.

## 2. Phân biệt kết quả thao tác với nhu cầu bắt tay

Một lần `wrap()` hoặc `unwrap()` trả về `SSLEngineResult`. Đọc đủ các thành phần sau:

```java
SSLEngineResult result = engine.unwrap(netIn, appIn);
SSLEngineResult.Status operation = result.getStatus();
SSLEngineResult.HandshakeStatus next = result.getHandshakeStatus();
int consumed = result.bytesConsumed();
int produced = result.bytesProduced();
```

Đây là đoạn minh họa trong một kết nối đã có engine và bộ đệm. `netIn` phải ở chế độ đọc; `appIn` phải còn chỗ để ghi.

- `getStatus()` cho biết thao tác vừa rồi có thành công, thiếu dữ liệu, thiếu chỗ chứa hay gặp chiều kết nối đã đóng.
- `getHandshakeStatus()` cho biết hướng tiến triển của bắt tay.
- `bytesConsumed()` và `bytesProduced()` giúp kiểm tra tiến triển và cập nhật luồng xử lý.

Chẳng hạn, `OK` không đồng nghĩa bắt tay hoàn tất. Một thao tác thành công vẫn có thể trả `NEED_TASK`. Ngược lại, khi thiếu dữ liệu đầu vào, gọi lại liên tục với đúng bộ đệm cũ không làm dữ liệu tự xuất hiện. Các trường kết quả có ý nghĩa độc lập và phải được phối hợp; xem [SSLEngineResult](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngineResult.html).

## 3. NEED_WRAP: tạo bản ghi rồi mới gửi

Trong giai đoạn bắt tay, engine có thể cần phát thông điệp điều khiển dù ứng dụng chưa có dữ liệu nghiệp vụ. Vì vậy, không được đợi hàng đợi dữ liệu ứng dụng có phần tử mới xử lý `NEED_WRAP`.

Với một bộ đệm nguồn rỗng, engine vẫn có thể tạo dữ liệu bắt tay:

```java
ByteBuffer empty = ByteBuffer.allocate(0);
SSLEngineResult result = engine.wrap(empty, netOut);
```

Đoạn trên chỉ minh họa thao tác TLS. Trước lời gọi, `netOut` phải sẵn sàng nhận byte; không được `clear()` nếu nó còn giữ byte chưa gửi. Sau lời gọi, đưa phần dữ liệu tạo ra vào hàng đợi ghi mạng theo đúng thứ tự.

### Hai bước không được gộp nhầm

1. `wrap()` tạo byte trong bộ nhớ.
2. `SocketChannel.write()` hoặc cơ chế vận chuyển khác gửi byte đến đối tác.

Nếu kênh không chặn chỉ ghi được một phần, giữ lại phần dư. Nếu lần ghi trả `0`, chờ khả năng ghi rồi thử lại; không quay vòng liên tục. Với `Selector`, thường chỉ đăng ký `OP_WRITE` khi còn dữ liệu chờ gửi, và bỏ đăng ký khi hàng đợi đã hết.

Ví dụ tự thiết kế: `wrap()` tạo 1.200 byte nhưng kênh mới nhận 700 byte. Kết nối vẫn còn nghĩa vụ gửi 500 byte. Ngay cả khi engine đã chuyển sang `NEED_UNWRAP`, phần dư ấy phải tiếp tục được chuyển đi; nếu bỏ quên nó để chỉ chờ đọc, đối tác có thể cũng đang chờ phần thông điệp bị thiếu.

`BUFFER_OVERFLOW` yêu cầu giải phóng hoặc tăng dung lượng đích một cách có giới hạn, bảo toàn dữ liệu hiện có, rồi mới thử lại. Không khắc phục bằng cách lặp cùng lời gọi với cùng vùng đích đã đầy.

## 4. NEED_UNWRAP: dùng byte đã có trước khi chờ thêm

`NEED_UNWRAP` cho biết engine cần xử lý thông tin từ đối tác để tiếp tục. Hãy kiểm tra bộ đệm nhận hiện tại trước. Một lần đọc mạng có thể đã chứa nhiều bản ghi; xử lý phần còn lại mà không nhất thiết phải chờ sự kiện đọc mới.

Ngược lại, một lần đọc cũng có thể chỉ chứa một phần bản ghi. Khi `unwrap()` trả `BUFFER_UNDERFLOW`, giữ phần chưa tiêu thụ, tạo chỗ nhận thêm và chờ dữ liệu mới. Với bộ đệm đang ở chế độ đọc, trình tự thông thường là:

```java
netIn.compact();       // Giữ byte chưa xử lý, chuyển sang chế độ ghi.
int count = channel.read(netIn);
netIn.flip();          // Chuyển sang chế độ đọc trước lần unwrap tiếp theo.
```

Đây là đoạn tích hợp minh họa, chưa bao gồm xử lý tăng dung lượng và đóng kết nối. `channel` là kênh của kết nối. Chỉ `compact()` tại ranh giới nhận thêm dữ liệu, không gọi tùy tiện giữa các thao tác sử dụng cùng bộ đệm.

- `count == 0`: chưa có byte mới; trả quyền điều khiển cho vòng lặp sự kiện.
- `count > 0`: có dữ liệu để thử xử lý tiếp.
- `count == -1`: đối tác đã kết thúc luồng truyền; chuyển sang xử lý kết thúc kết nối và đánh giá việc đóng TLS, không coi đây là bắt tay thành công.

Nếu bộ đệm nguồn không thể chứa bản ghi cần thiết, chỉ chờ thêm mạng cũng không đủ: phải kiểm tra kích thước bộ đệm gói do phiên cung cấp và tăng bộ đệm trong giới hạn tài nguyên. Nếu bộ đệm ứng dụng đích đầy và nhận `BUFFER_OVERFLOW`, cần chuyển dữ liệu đã giải mã cho bộ phận tiêu thụ hoặc tạo thêm chỗ trước khi thử lại. Không nhầm thiếu dữ liệu nguồn với thiếu dung lượng đích. Cách xử lý các tình huống bộ đệm được mô tả trong [API SSLEngine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html).

## 5. NEED_TASK: chạy tác vụ, không chờ socket

Một số công việc của bắt tay được engine trao cho ứng dụng dưới dạng `Runnable`. Khi gặp `NEED_TASK`, chờ sự kiện đọc hay ghi mạng sẽ không thay cho việc chạy những tác vụ này. Một mô hình đơn giản là lấy đến khi `getDelegatedTask()` trả `null`:

```java
static void runTasksInline(SSLEngine engine) {
    Runnable task;
    while ((task = engine.getDelegatedTask()) != null) {
        task.run();
    }
}
```

Đây là hàm hỗ trợ, cần import `javax.net.ssl.SSLEngine`. Mô hình chạy trực tiếp thích hợp để học luồng điều khiển hoặc khi ứng dụng chấp nhận thời gian thực thi ấy trên luồng hiện tại. Không coi nó là lựa chọn mặc định cho vòng lặp xử lý nhiều kết nối: tác vụ có thể tốn thời gian hoặc chặn, chẳng hạn khi chính sách kiểm tra chứng chỉ cần truy cập dịch vụ bên ngoài. Xem [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).

### Khi chuyển tác vụ sang bộ thực thi

Một thiết kế thực tế có thể lấy danh sách tác vụ trên luồng sở hữu kết nối, thực hiện chúng tuần tự trong một công việc nền, rồi báo hoàn tất về chính luồng sở hữu đó. Quy tắc cho thiết kế này:

1. Đánh dấu kết nối đang đợi tác vụ để ngăn tái nhập bộ điều khiển engine.
2. Trong lúc tác vụ chạy, không cho cùng bộ điều khiển gọi tiếp `wrap()`/`unwrap()` trên engine đó. Dữ liệu mạng mới có thể được xếp hàng trong giới hạn cho phép.
3. Chỉ đánh thức bộ điều khiển sau khi tất cả tác vụ của đợt đã hoàn tất; việc đưa công việc vào executor chưa phải hoàn tất.
4. Chuyển lỗi và tình huống executor từ chối công việc về luồng quản lý kết nối; không để cờ đang đợi bị treo vĩnh viễn.
5. Đọc lại `engine.getHandshakeStatus()` rồi quyết định bước kế tiếp; không mặc định sau `NEED_TASK` luôn là `NEED_WRAP`.

Không dùng `Future.get()` trên chính luồng sự kiện để giả lập bất đồng bộ: nó vẫn khiến luồng ấy phải chờ. Cũng không chạy lại cùng một `Runnable` nhiều lần. Nếu đã lấy hết tác vụ nhưng engine vẫn liên tục yêu cầu tác vụ và không có tiến triển, ghi nhận trạng thái và xử lý theo chính sách lỗi/thời hạn; không lặp vô hạn.

## 6. Ghép ba trạng thái thành bộ điều khiển có thể nhường quyền

Sơ đồ sau là thuật toán định hướng, không phải một vòng lặp TLS hoàn chỉnh:

```text
Có byte chưa gửi?
  -> tiếp tục xả hàng đợi khi kênh ghi được
  -> giữ nguyên phần dư khi kênh chưa ghi được

Có tác vụ nền đang chạy?
  -> nhường quyền; chờ thông báo hoàn tất

Đọc HandshakeStatus hiện tại:
  NEED_WRAP
    -> chuẩn bị vùng đích đủ chỗ
    -> wrap nguồn rỗng cho nhu cầu bắt tay
    -> giữ mọi byte tạo ra trong hàng đợi gửi
    -> xử lý Status và đọc trạng thái kế tiếp

  NEED_UNWRAP
    -> thử unwrap phần nhận hiện có
    -> thiếu dữ liệu: giữ phần dư và chờ đọc thêm
    -> thiếu chỗ: giải phóng/tăng bộ đệm đích có giới hạn
    -> xử lý Status và đọc trạng thái kế tiếp

  NEED_TASK
    -> lấy và chạy các tác vụ được giao
    -> khi hoàn tất: quay lại đọc trạng thái

  NOT_HANDSHAKING
    -> tiếp tục luồng dữ liệu/đóng kết nối tùy vòng đời
```

Một bộ điều khiển nên đặt giới hạn số bước xử lý trong mỗi lượt để một kết nối không chiếm hết thời gian của vòng lặp. Khi không tiêu thụ byte, không tạo byte, không đổi trạng thái và không hoàn thành tác vụ, phải xác định điều kiện cần chờ: dữ liệu nhận, khả năng ghi, chỗ chứa, kết quả tác vụ hoặc hết hạn. Không dùng một vòng `while` chỉ kiểm tra trạng thái mà thiếu điều kiện nhường quyền.

## 7. Hai trạng thái liên quan cần phân biệt

`FINISHED` là tín hiệu từ kết quả của lần `wrap()`/`unwrap()` vừa hoàn thành bắt tay; `engine.getHandshakeStatus()` không trả giá trị này. Vì thế, nếu cần đánh dấu thời điểm bắt tay hoàn tất, hãy kiểm tra kết quả thao tác ngay khi nhận được. `NOT_HANDSHAKING` chỉ mô tả engine hiện không bắt tay; engine mới tạo, chưa bắt đầu, cũng không phải một kết nối đã xác thực thành công. Xem [HandshakeStatus](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html).

Trong phạm vi bài này, luồng vận chuyển là TLS trên TCP. `NEED_UNWRAP_AGAIN` thuộc DTLS, yêu cầu gọi `unwrap()` tiếp trên dữ liệu đã được tiếp nhận thay vì mặc định chờ gói mới. Không ghép quy tắc DTLS này vào nhánh chờ đọc TCP. Bài này không hướng dẫn triển khai DTLS. [HandshakeStatus mô tả riêng phạm vi này](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html).

## 8. Chương trình chạy: quan sát NEED_WRAP sang NEED_UNWRAP

Chương trình sau chạy độc lập trên Java 17+, dùng bộ cung cấp SunJSSE của OpenJDK. Nó tạo thông điệp đầu tiên của máy khách TLS 1.3 trong bộ nhớ, không mở socket và không hoàn tất bắt tay. Vì chưa có máy chủ, nó không thực hiện xác thực chứng chỉ và không trao đổi dữ liệu ứng dụng.

Lưu thành `ClientHelloDemo.java`:

```java
import java.nio.ByteBuffer;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;

public class ClientHelloDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);

        SSLEngine engine = context.createSSLEngine("example.com", 443);
        engine.setUseClientMode(true);
        engine.setEnabledProtocols(new String[] {"TLSv1.3"});
        engine.beginHandshake();
        System.out.println("before=" + engine.getHandshakeStatus());

        ByteBuffer empty = ByteBuffer.allocate(0);
        ByteBuffer netOut = ByteBuffer.allocate(
                engine.getSession().getPacketBufferSize());
        SSLEngineResult result = engine.wrap(empty, netOut);
        netOut.flip();

        System.out.println("status=" + result.getStatus());
        System.out.println("after=" + result.getHandshakeStatus());
        System.out.println("applicationBytesConsumed=" + result.bytesConsumed());
        System.out.println("hasNetworkBytes=" + (result.bytesProduced() > 0));
        System.out.println("bufferMatchesResult="
                + (netOut.remaining() == result.bytesProduced()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ClientHelloDemo.java
java ClientHelloDemo
```

Kết quả quan sát với SunJSSE trên OpenJDK 21:

```text
before=NEED_WRAP
status=OK
after=NEED_UNWRAP
applicationBytesConsumed=0
hasNetworkBytes=true
bufferMatchesResult=true
```

Không in toàn bộ dữ liệu ClientHello hoặc gắn cứng kích thước của nó: nội dung và kích thước có thể thay đổi theo cấu hình, phiên bản JDK và thông tin ngẫu nhiên. Ví dụ cho thấy nguồn ứng dụng rỗng vẫn tạo dữ liệu TLS. `after=NEED_UNWRAP` yêu cầu phản hồi của máy chủ; muốn có phản hồi, ứng dụng trước hết phải gửi số byte trong `netOut`. Không truyền buffer này trực tiếp cho `unwrap()` của chính engine máy khách: đó là dữ liệu gửi đi, dành cho engine phía máy chủ.

Đây là thí nghiệm một bước với cấu hình đã nêu, không phải giả định rằng mọi provider và mọi lần `wrap()` đều trả cùng chuỗi trạng thái. Bộ điều khiển thật vẫn xử lý tất cả kết quả và lỗi. Với một máy khách HTTPS kết nối thật, cấu hình kiểm tra tên máy chủ qua `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` trước bắt tay, dùng nguồn tin cậy phù hợp và giữ kiểm tra chứng chỉ; truyền tên vào `createSSLEngine()` không tự thay thế việc kiểm tra danh tính đầu cuối. [JSSE giải thích yêu cầu kiểm tra đối tác](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).

## 9. Lỗi thường gặp và thực hành suy luận

| Hiện tượng | Sai sót cần kiểm tra |
| --- | --- |
| Hai đầu đều chờ mãi | Bỏ qua `NEED_WRAP` khi không có dữ liệu ứng dụng, hoặc còn byte TLS chưa xả hết |
| CPU tăng nhưng không có lưu lượng | Lặp `unwrap()` khi thiếu dữ liệu hoặc lặp ghi khi kênh trả `0` |
| Bắt tay dừng ở `NEED_TASK` | Chỉ lấy tác vụ mà không chạy, hoặc không đánh thức kết nối sau khi chạy xong |
| Dữ liệu TLS hỏng | `clear()` bộ đệm còn phần chưa gửi, dùng sai chế độ bộ đệm hoặc đảo thứ tự gửi |
| Báo thành công quá sớm | Coi `OK` hay `NOT_HANDSHAKING` của engine chưa khởi động là xác thực hoàn tất |
| Một kết nối làm chậm nhiều kết nối | Tác vụ mất thời gian chạy trực tiếp trên luồng sự kiện, hoặc vòng xử lý không nhường quyền |

Tự kiểm tra bằng ba tình huống:

1. `wrap()` tạo 900 byte; lần ghi đầu gửi 400 byte rồi kênh chưa ghi được nữa. Cần giữ 500 byte và tiếp tục khi ghi được, kể cả engine đang yêu cầu nhận dữ liệu.
2. `unwrap()` trả `BUFFER_UNDERFLOW` với 7 byte chưa tiêu thụ. Giữ 7 byte ấy khi nhận thêm; không xóa chúng và không lặp vô hạn với cùng đầu vào.
3. Engine trả `NEED_TASK`, executor đã nhận công việc nhưng chưa chạy xong. Chưa tiếp tục bộ điều khiển engine; đợi kết quả tác vụ, chuyển quyền về luồng quản lý kết nối rồi đọc trạng thái mới.

Khi chẩn đoán, ghi tên thao tác, `Status`, `HandshakeStatus`, số byte tiêu thụ/tạo ra và lượng dữ liệu còn chờ gửi. Những dữ kiện này giúp phân biệt đang chờ mạng với đang chờ công việc nội bộ mà không cần ghi nội dung dữ liệu ứng dụng hay bí mật của phiên TLS.
