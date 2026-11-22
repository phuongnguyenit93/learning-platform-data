# SSLEngine và TLS độc lập cơ chế vận chuyển dữ liệu

## 1. SSLEngine xử lý TLS, ứng dụng điều khiển I/O

Khi dùng một kết nối TLS, có hai việc liên quan nhưng khác nhau:

1. Thực hiện giao thức bảo mật: bắt tay, xác thực phía đối diện, bảo vệ tính toàn vẹn và mã hóa dữ liệu ứng dụng.
2. Vận chuyển byte: đọc/ghi socket, xử lý dữ liệu nhận từng phần, chờ khả năng đọc/ghi và đóng kết nối.

`SSLEngine` tách phần thứ nhất khỏi cơ chế vận chuyển. Nó nhận byte trong ByteBuffer, thực hiện bước TLS phù hợp rồi trả byte kết quả cùng trạng thái cần xử lý tiếp.

```text
Dữ liệu ứng dụng gửi
        |
       wrap
        |
Byte bản ghi TLS
        |
Tầng vận chuyển do ứng dụng quản lý
        |
Byte TLS nhận từ phía đối diện
        |
      unwrap
        |
Dữ liệu ứng dụng nhận
```

SSLEngine không tự tạo SocketChannel, không tự đăng ký Selector và không tự gửi các byte do wrap tạo ra.

API có tên SSL vì lịch sử JSSE, nhưng ví dụ hiện đại dùng TLS. Không cần bật các phiên bản giao thức cũ chỉ vì tên lớp chứa SSL.

Bài dùng Java 17+ và các khả năng còn phù hợp của JSSE. [SSLEngine](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngine.html) mô tả rõ ranh giới giữa xử lý giao thức và vận chuyển.

## 2. Độc lập vận chuyển không có nghĩa không cần hợp đồng vận chuyển

Ứng dụng có thể tích hợp engine với:

- Socket hoặc stream theo cách tự điều phối.
- SocketChannel và Selector.
- Một framework I/O bất đồng bộ.
- Các vùng đệm trong bộ nhớ để mô phỏng hai đầu kết nối.

Với TLS trên luồng byte, tầng dưới vẫn phải cung cấp đúng các đặc tính truyền cần thiết, như thứ tự và độ tin cậy của luồng mà giao thức dựa vào. Không thể tùy ý bỏ byte, đổi thứ tự rồi kỳ vọng engine tự sửa mọi lỗi vận chuyển.

DTLS là một cấu hình/giao thức riêng có khả năng liên quan datagram và trạng thái riêng. “SSLEngine độc lập I/O” không đồng nghĩa một engine TLS thông thường có thể được gắn lên UDP tùy ý như TCP.

Tách tầng là cách chia trách nhiệm. Nó không xóa yêu cầu giao thức của từng tầng.

## 3. So với SSLSocket và thư viện mức cao

| Lựa chọn | Ai quản lý việc đọc/ghi TLS qua kết nối? | Khi nào cân nhắc |
| --- | --- | --- |
| SSLSocket | Lớp socket TLS tích hợp cùng I/O của socket | Cần mô hình socket/stream thuận tiện |
| SSLEngine | Ứng dụng/framework điều phối buffer và transport | Cần tích hợp I/O tùy chọn hoặc máy trạng thái riêng |
| HTTP client/framework TLS | Thư viện quản lý thêm giao thức ứng dụng và vòng đời kết nối | Công việc chính là HTTP hoặc một giao thức đã có thư viện |

Chọn SSLEngine không tự làm chương trình nhanh hơn. Nó cho phép điều phối I/O theo cách khác, nhưng chuyển nhiều trách nhiệm sang phần tích hợp.

Nếu chỉ cần gọi HTTPS, thường không cần tự viết một vòng wrap/unwrap. Khi học framework hoặc xây tầng vận chuyển, hiểu engine giúp giải thích cách TLS được gắn vào một luồng I/O bất đồng bộ.

SSLEngine cũng không tự triển khai HTTP, framing thông điệp nghiệp vụ hay retry yêu cầu ứng dụng.

## 4. Bốn vùng đệm và hai hướng dữ liệu

Một mô hình tên thường dùng:

| Buffer | Nội dung | Người ghi chính | Người đọc chính |
| --- | --- | --- | --- |
| appOut | Dữ liệu ứng dụng muốn gửi | Ứng dụng | wrap |
| netOut | Byte TLS sẵn sàng chuyển đi | wrap | Tầng I/O ghi ra transport |
| netIn | Byte TLS nhận được | Tầng I/O | unwrap |
| appIn | Dữ liệu ứng dụng được giải bảo vệ | unwrap | Ứng dụng |

```text
Ứng dụng -> appOut -> wrap -> netOut -> transport
Ứng dụng <- appIn  <- unwrap <- netIn <- transport
```

Trong pha dữ liệu, appOut/appIn chứa plaintext của ứng dụng. netOut/netIn chứa dữ liệu giao thức TLS hoặc dữ liệu đã được bảo vệ theo pha hiện tại.

Không gọi mọi byte trong netOut là ciphertext ứng dụng. Trong bắt tay có các bản tin điều khiển, và một số thông tin giao thức như ClientHello không phải dữ liệu ứng dụng đã được mã hóa.

Tầng vận chuyển phải gửi **byte netOut**, không gửi nhầm appOut trực tiếp. Ở chiều nhận, byte từ mạng phải đi qua unwrap theo trạng thái engine trước khi ứng dụng dùng kết quả appIn.

## 5. wrap và unwrap không phải send và receive

### wrap

```java
SSLEngineResult result = engine.wrap(appOut, netOut);
```

Đây là đoạn minh họa, cần engine và ByteBuffer ở trạng thái phù hợp.

wrap có thể:

- Tiêu thụ một phần dữ liệu ứng dụng.
- Tạo một phần byte TLS.
- Tạo dữ liệu bắt tay/đóng kết nối dù chưa có dữ liệu ứng dụng.
- Báo thiếu chỗ trong buffer đích.
- Yêu cầu một bước khác trước khi tiếp tục.

Lời gọi hoàn tất không chứng minh byte đã ra mạng. Chúng còn nằm trong buffer cho tới khi tầng I/O gửi đi.

### unwrap

```java
SSLEngineResult result = engine.unwrap(netIn, appIn);
```

unwrap xử lý các byte TLS hiện có. Nó không tự đọc socket để lấy thêm phần còn thiếu.

Một lần unwrap có thể không tạo plaintext ứng dụng vì đang xử lý bản tin bắt tay. Một lần đọc transport cũng không nhất thiết đủ cho một bản ghi TLS.

Các ranh giới không đồng nhất:

```text
một lần read/write
    != một bản ghi TLS
    != một thông điệp nghiệp vụ
```

Ví dụ một thông điệp ứng dụng có thể được vận chuyển qua nhiều lần đọc. Tầng ứng dụng vẫn cần quy tắc xác định độ dài hoặc framing của chính nó.

## 6. SSLEngineResult là chỉ dẫn để tiến triển

Kết quả chứa hai nhóm trạng thái khác nhau:

### Status của thao tác

| Giá trị | Cách hiểu |
| --- | --- |
| OK | Thao tác đã xử lý theo khả năng hiện tại |
| BUFFER_OVERFLOW | Buffer đích chưa đủ chỗ cho kết quả cần tạo |
| BUFFER_UNDERFLOW | Khi unwrap, dữ liệu nguồn chưa đủ để xử lý một gói/bản ghi cần thiết |
| CLOSED | Phía tương ứng đã đóng hoặc thao tác gặp engine đã đóng theo trạng thái |

OK không có nghĩa “bắt tay xong”, “dữ liệu đã được gửi” hay “toàn bộ thông điệp đã đọc”.

### Số byte thực sự xử lý

- bytesConsumed: số byte đã tiêu thụ từ nguồn của lời gọi.
- bytesProduced: số byte đã ghi vào đích.

Không giả định wrap luôn tiêu thụ hết appOut. Cũng không giả định unwrap luôn tiêu thụ hết netIn hoặc tạo một thông điệp hoàn chỉnh.

Tham khảo [SSLEngineResult](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.html), [Status](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.Status.html).

## 7. Bắt tay là máy trạng thái do ứng dụng điều phối

Những HandshakeStatus quan trọng với TLS luồng:

| Trạng thái | Trách nhiệm điều phối |
| --- | --- |
| NEED_WRAP | Gọi wrap để tạo dữ liệu cần gửi và đưa nó tới tầng vận chuyển |
| NEED_UNWRAP | Cần dữ liệu từ phía đối diện để unwrap/tiến triển |
| NEED_TASK | Lấy và chạy các delegated task theo hợp đồng |
| FINISHED | Lời gọi wrap/unwrap vừa hoàn tất một lần bắt tay |
| NOT_HANDSHAKING | Hiện không ở trong một lần bắt tay |

FINISHED chỉ xuất hiện trong kết quả wrap/unwrap vừa hoàn tất bắt tay; không được trả từ engine.getHandshakeStatus(). Không viết vòng chờ getHandshakeStatus()==FINISHED rồi chờ vô hạn.

Enum trên Java hiện đại còn có NEED_UNWRAP_AGAIN dành cho DTLS: có dữ liệu đã nhận trước đó cần được unwrap lại mà không cần nhận thêm. Bài tập trung TLS luồng, không trộn logic DTLS vào ví dụ.

Một lần bắt tay không phải một chuỗi cố định “wrap một lần rồi unwrap một lần”. Số bước và dữ liệu cụ thể phụ thuộc giao thức, cấu hình, provider và phía đối diện.

Delegated task có thể chứa công việc như xử lý liên quan xác thực/chứng chỉ. Tầng tích hợp phải bảo đảm chúng được hoàn tất đúng lúc trước khi thúc engine tiến theo bước yêu cầu tiếp theo; không bỏ qua NEED_TASK hoặc để event loop quay liên tục trong khi task chưa chạy.

Nguồn trạng thái: [HandshakeStatus](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html).

## 8. Buffer phải được giữ đúng trạng thái

ByteBuffer có position, limit và các thao tác chuyển giữa đọc/ghi:

- Tầng I/O ghi byte TLS nhận được vào netIn.
- Trước unwrap, netIn cần ở trạng thái đọc phần dữ liệu đã nhận.
- Sau unwrap, phần chưa tiêu thụ phải được giữ lại khi nhận thêm dữ liệu.
- netOut có dữ liệu được tạo, nhưng tầng I/O có thể chỉ ghi ra một phần.

Với dữ liệu nhận chưa đủ, thường cần bảo toàn phần dư bằng compact hoặc một cách tổ chức buffer tương đương. clear làm mất phạm vi dữ liệu chưa xử lý nếu dùng sai.

BUFFER_UNDERFLOW không phải lý do tự loại bỏ các byte đang có. Chúng có thể là đầu một bản ghi hợp lệ chưa nhận đủ.

BUFFER_OVERFLOW yêu cầu xem buffer đích:

- Với wrap, cần chỗ trong netOut.
- Với unwrap, cần chỗ trong appIn.

Có thể cần giải phóng dữ liệu đã xử lý, gửi/drain phần đang chờ hoặc tăng buffer theo giới hạn ứng dụng. Không tăng vô hạn chỉ vì lặp overflow.

SSLSession cung cấp getPacketBufferSize và getApplicationBufferSize để tham khảo kích thước cần thiết. Không mã hóa cứng một số “đủ cho mọi TLS”; kiểm tra theo trạng thái/session hiện tại và xử lý kết quả thực tế.

## 9. Ví dụ: tạo dữ liệu bắt tay mà không mở socket

Chương trình tạo client engine, cấu hình thông tin phía đối diện và sinh dữ liệu bắt tay đầu tiên vào ByteBuffer. Nó không có Socket, SocketChannel hay lời gọi gửi mạng.

Đây là **thí nghiệm bước khởi đầu**, chưa phải một kết nối TLS hoàn chỉnh. Không có server nên không thể xác thực chứng chỉ phía đối diện hay trao đổi dữ liệu ứng dụng thành công.

Lưu thành `TransportIndependentTlsDemo.java`:

```java
import java.nio.ByteBuffer;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLEngineResult;
import javax.net.ssl.SSLParameters;

public class TransportIndependentTlsDemo {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLEngine engine =
                context.createSSLEngine("service.example", 443);
        engine.setUseClientMode(true);

        SSLParameters parameters = engine.getSSLParameters();
        parameters.setProtocols(new String[]{"TLSv1.3", "TLSv1.2"});
        parameters.setEndpointIdentificationAlgorithm("HTTPS");
        engine.setSSLParameters(parameters);

        ByteBuffer emptyApplicationData = ByteBuffer.allocate(0);
        ByteBuffer tlsOutput = ByteBuffer.allocate(
                engine.getSession().getPacketBufferSize());

        try {
            engine.beginHandshake();

            SSLEngineResult result =
                    engine.wrap(emptyApplicationData, tlsOutput);

            System.out.println("Peer hint: " + engine.getPeerHost()
                    + ":" + engine.getPeerPort());
            System.out.println("Client mode: " + engine.getUseClientMode());
            System.out.println("Endpoint identification: "
                    + engine.getSSLParameters()
                            .getEndpointIdentificationAlgorithm());
            System.out.println("Operation status: " + result.getStatus());
            System.out.println("Handshake bytes produced: "
                    + (result.bytesProduced() > 0));
            System.out.println("Application bytes consumed: "
                    + result.bytesConsumed());
            System.out.println("TLS bytes waiting for transport: "
                    + (tlsOutput.position() > 0));
            System.out.println("Handshake finished in this call: "
                    + (result.getHandshakeStatus()
                        == SSLEngineResult.HandshakeStatus.FINISHED));
        } finally {
            engine.closeOutbound();
        }
    }
}
```

Chạy trên JDK 17+ với JSSE hỗ trợ những phiên bản đã chọn:

```shell
javac TransportIndependentTlsDemo.java
java TransportIndependentTlsDemo
```

Stdout của lần kiểm chứng trên JDK 17.0.15:

```text
Peer hint: service.example:443
Client mode: true
Endpoint identification: HTTPS
Operation status: OK
Handshake bytes produced: true
Application bytes consumed: 0
TLS bytes waiting for transport: true
Handshake finished in this call: false
```

Số byte thực tế của bản tin không được in như một hằng số vì cấu trúc bắt tay có thể thay đổi theo provider/cấu hình.

Những kết luận được phép rút ra từ thí nghiệm:

1. Một engine có thể tạo byte giao thức chỉ bằng thao tác bộ nhớ.
2. Không có dữ liệu ứng dụng vẫn có thể cần wrap trong bắt tay.
3. Byte đã được tạo nhưng còn chờ tầng vận chuyển.
4. Bắt tay chưa hoàn tất, nên chưa có bằng chứng về xác thực peer hay một kênh ứng dụng thành công.

Peer host/port là thông tin phục vụ engine; createSSLEngine không tự kết nối tới service.example. Tên miền trong ví dụ không được dùng làm đích mạng.

Khối finally đóng hướng outbound của engine thí nghiệm. Nó không minh họa đầy đủ một cuộc trao đổi close_notify với peer, vì thí nghiệm chưa thiết lập transport hay có peer.

## 10. Xác thực và cấu hình vẫn thuộc trách nhiệm tích hợp

Độc lập vận chuyển không có nghĩa được bỏ kiểm tra danh tính.

Một kết nối client cần phối hợp:

- SSLContext có trust/key material phù hợp với môi trường.
- Vai client/server được đặt trước bắt tay.
- Phiên bản/cipher suite và ràng buộc thuật toán theo chính sách triển khai.
- Thông tin peer và endpoint identification theo giao thức ứng dụng.
- SNI/ALPN khi bài toán cần.

Ví dụ dùng thuật toán endpoint identification tên HTTPS để thể hiện cấu hình kiểm tra danh tính host thường gặp. Việc đặt chuỗi ấy không tự tạo HTTP client và không chứng minh xác thực đã diễn ra khi mới sinh ClientHello.

SNI giúp phía server chọn cấu hình phù hợp với tên được yêu cầu; nó không thay cho xác minh chứng chỉ và tên peer. Cũng không dùng trust manager “chấp nhận mọi chứng chỉ” để làm ví dụ bắt tay thành công.

Giá trị getPeerHost không phải kết quả xác thực danh tính phía đối diện. Nó là thông tin được cung cấp/cấu hình cho engine.

Trong ứng dụng thực tế, chính sách TLS cần đối chiếu JDK/provider và yêu cầu hệ thống hiện hành. Không bật lại giao thức hoặc thuật toán đã bị chính sách vô hiệu hóa chỉ để vượt qua lỗi thương lượng.

Các lớp cấu hình và mô hình xác thực được trình bày trong [SSLParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLParameters.html), [JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html).

## 11. Tầng I/O cần bảo đảm tiến triển và giới hạn tải

Một vòng điều phối TLS đầy đủ cần xét:

1. Có byte TLS đang chờ gửi không?
2. Có byte nhận chưa unwrap không?
3. Engine đang yêu cầu wrap, unwrap hay task?
4. Buffer đích còn chỗ và ứng dụng có đang tiêu thụ dữ liệu không?
5. Transport đọc/ghi được bao nhiêu byte trong lần này?
6. Có thay đổi trạng thái hoặc tiêu thụ/sinh byte không?
7. Khi chưa thể tiến triển, sự kiện nào sẽ đánh thức lần xử lý tiếp theo?

Không gọi wrap/unwrap trong một vòng quay vô hạn chỉ vì “chưa xong”. Nếu không có dữ liệu mới, không có chỗ đích hoặc task chưa hoàn tất, vòng quay chỉ tiêu CPU.

Tầng tích hợp phải có giới hạn buffer, số kết nối, thời hạn bắt tay, thời hạn I/O và chính sách hủy. Engine không tự đặt toàn bộ deadline của yêu cầu ứng dụng.

Nếu transport chỉ ghi được một phần netOut, giữ phần còn lại cho lần ghi tiếp. Không wrap thêm vào một buffer đang có dữ liệu chưa gửi theo cách ghi đè nó.

Nếu ứng dụng chưa tiêu thụ appIn, cần quản lý áp lực ngược để việc nhận thêm không làm bộ nhớ tăng vô hạn.

## 12. Đóng TLS khác với đóng socket ngay lập tức

Khi kết thúc gửi, closeOutbound chuyển engine sang quy trình đóng hướng ra. Có thể cần tiếp tục wrap để tạo thông báo đóng TLS và gửi những byte còn lại qua transport.

Đóng socket ngay sau closeOutbound mà bỏ output còn chờ có thể không tạo được cuộc đóng TLS trật tự.

Ở chiều vào, cần xử lý thông báo đóng từ peer. EOF transport không tự tương đương một close_notify hợp lệ trong mọi tình huống. closeInbound có thể báo SSLException nếu kết thúc không đúng giao thức theo trạng thái engine.

Không nuốt mọi SSLException ở bước đóng rồi coi chúng đều là thành công. Thiết kế phải phân biệt kết thúc bình thường, mất kết nối, timeout và lỗi TLS, theo hợp đồng ứng dụng.

Một engine đã đóng không được reset để làm kết nối độc lập mới; tạo engine mới cho vòng đời kết nối mới.

## 13. Sở hữu engine và thứ tự byte

Mỗi kết nối TLS cần trạng thái engine riêng. Không dùng chung một engine cho hai luồng kết nối độc lập chỉ vì chúng cùng host.

Cũng không gọi wrap/unwrap tùy tiện từ nhiều tác vụ mà không có mô hình phối hợp. Các chiều có khả năng đồng thời theo hợp đồng API, nhưng ứng dụng phải giữ đúng thứ tự dữ liệu, không chồng các lời gọi cùng chiều và không phá các bước bắt tay/task/đóng.

Một mô hình event loop sở hữu trạng thái kết nối và buffer thường giúp lập luận rõ. Nếu dùng worker cho delegated task, cần bàn giao kết quả và tiếp tục engine đúng thứ tự.

Đừng giữ một khóa chặn event loop trong khi chờ chính event loop xử lý I/O giúp engine tiến triển. Tách xử lý giao thức không tự loại bỏ deadlock do cách điều phối của ứng dụng.

## 14. Tự kiểm tra

**wrap trả OK có nghĩa byte đã tới server không?**  
Không. Byte mới được tạo vào buffer đích; tầng I/O phải gửi chúng.

**unwrap có tự gọi read socket khi thiếu dữ liệu không?**  
Không. Nó báo trạng thái để tầng tích hợp nhận thêm hoặc xử lý phù hợp.

**netOut có luôn chứa ciphertext ứng dụng không?**  
Không. Nó còn có thể chứa dữ liệu bắt tay/điều khiển TLS.

**getHandshakeStatus có trả FINISHED để vòng lặp phát hiện không?**  
Không. FINISHED được báo từ kết quả wrap/unwrap vừa hoàn tất bắt tay.

**createSSLEngine(host, port) có mở kết nối không?**  
Không. Đó là tạo engine cùng thông tin peer, không tạo socket.

Điểm cốt lõi là một ranh giới hai chiều: SSLEngine thực hiện máy trạng thái và biến đổi byte của TLS, còn ứng dụng/framework chịu trách nhiệm đưa byte đúng nơi, đúng thứ tự, đúng vòng đời và theo giới hạn tài nguyên đã định.
