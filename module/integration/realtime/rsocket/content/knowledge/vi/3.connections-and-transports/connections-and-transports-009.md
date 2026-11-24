# Vòng đời kết nối, trạng thái sẵn sàng và đóng kết nối

RSocket duy trì một phiên giao tiếp hai chiều trên một kết nối transport. Trên cùng phiên đó, client và server có thể mở nhiều stream độc lập, trao đổi request-response, request-stream, request-channel hoặc fire-and-forget. Vì vậy, quản lý kết nối RSocket cần phân biệt ba vòng đời: kết nối mạng, phiên RSocket và từng stream ứng dụng.

Kết nối TCP hoặc WebSocket thành công mới chỉ cho biết hai đầu đã thiết lập được đường truyền. Ứng dụng chỉ nên xem phiên RSocket là sẵn sàng sau khi quá trình thiết lập giao thức hoàn tất. Khi phiên bị đóng, mọi stream còn phụ thuộc vào phiên đó có thể bị kết thúc hoặc báo lỗi. Nắm được các mốc này giúp ứng dụng khởi động đúng thời điểm, theo dõi sức khỏe phiên và phục hồi sau sự cố mạng.

## 1. Phân biệt transport, connection, session và stream

Các khái niệm sau có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Phạm vi vòng đời |
| --- | --- | --- |
| Transport | Đường truyền mang frame RSocket, ví dụ TCP hoặc WebSocket. | Từ lúc mở kết nối mạng đến khi transport đóng hoặc mất. |
| RSocket connection/session | Phiên giao thức được thiết lập trên transport, có trạng thái và các tham số giao tiếp chung. | Từ khi hoàn tất SETUP đến khi phiên bị đóng hoặc mất hiệu lực. |
| Stream | Một tương tác RSocket cụ thể, có stream ID và tín hiệu riêng. | Có thể kết thúc trong khi connection vẫn tiếp tục hoạt động. |
| Payload | Dữ liệu và metadata được gửi trong frame của một tương tác. | Gắn với frame hoặc stream mang payload đó. |

Ví dụ, một ứng dụng có thể mở một kết nối TCP từ client tới server rồi gửi hàng trăm request trên nhiều stream. Một request-response hoàn tất không làm đóng TCP connection. Tương tự, client hủy một request-stream chỉ tác động tới stream tương ứng; các stream khác vẫn có thể tiếp tục.

TCP và WebSocket chỉ khác nhau ở cách vận chuyển frame. Sau khi RSocket session được thiết lập, mô hình stream và các interaction model của RSocket vẫn giữ nguyên. Với WebSocket, quá trình mở đường truyền có thêm HTTP Upgrade; với TCP, hai bên thiết lập kết nối TCP trực tiếp.

## 2. Các giai đoạn trong vòng đời kết nối

Ở góc nhìn ứng dụng, có thể mô hình hóa vòng đời bằng các trạng thái sau:

~~~text
DISCONNECTED
     |
     v
 CONNECTING       Mở TCP hoặc WebSocket transport
     |
     v
  SETTING_UP      Trao đổi frame SETUP và kiểm tra phiên
     |
     v
    READY         Có thể gửi các interaction RSocket
     |
     v
   CLOSING        Ứng dụng chủ động đóng hoặc đang dừng
     |
     v
    CLOSED

CONNECTING / SETTING_UP / READY
     |
     +---- lỗi không thể phục hồi ----> FAILED
~~~

Đây là state machine ở tầng ứng dụng để tổ chức xử lý, không phải một enum trạng thái bắt buộc được mọi thư viện RSocket cung cấp. Một ứng dụng có thể gộp FAILED vào CLOSED hoặc thêm trạng thái RETRYING tùy nhu cầu.

**Giai đoạn 1 — DISCONNECTED.** Chưa có transport và chưa có phiên RSocket. Ứng dụng chưa thể gửi request qua connection đó.

**Giai đoạn 2 — CONNECTING.** Client yêu cầu transport mở kết nối tới địa chỉ server. Với TCP, quá trình này thiết lập socket TCP; với WebSocket, client thực hiện bắt tay HTTP Upgrade tới endpoint WebSocket. Ở giai đoạn này, đường truyền có thể thất bại do DNS, từ chối kết nối, timeout, TLS hoặc endpoint không khả dụng.

**Giai đoạn 3 — SETTING_UP.** Sau khi transport mở, client gửi frame SETUP đầu tiên để bắt đầu một phiên RSocket mới. Frame này mang thông tin thiết lập như phiên bản giao thức, tham số keepalive, MIME type cho metadata và data, cùng metadata hoặc payload thiết lập nếu ứng dụng sử dụng. Server kiểm tra yêu cầu và khởi tạo phía RSocket tương ứng. Nếu server từ chối thiết lập, nó có thể trả về lỗi ở cấp connection và đóng phiên.

**Giai đoạn 4 — READY.** Khi thiết lập RSocket thành công, client có thể sử dụng RSocket để gửi request và nhận phản hồi. Phía server cũng có thể gửi dữ liệu chủ động trên các tương tác được tạo từ phiên. Đây là thời điểm thích hợp để đánh dấu client là sẵn sàng nhận công việc phụ thuộc vào RSocket.

**Giai đoạn 5 — CLOSING.** Ứng dụng bắt đầu dừng phiên, ví dụ khi service shutdown, thay đổi endpoint hoặc chủ động thay thế connection. Ứng dụng nên ngừng nhận công việc mới và quyết định cách xử lý các stream đang chạy.

**Giai đoạn 6 — CLOSED hoặc FAILED.** Transport đã đóng hoặc phiên không thể tiếp tục. Connection cũ không còn được dùng cho request mới; muốn giao tiếp lại, client cần thiết lập một phiên khác hoặc thực hiện cơ chế resume nếu đã cấu hình và còn đủ điều kiện.

## 3. Khi nào connection thực sự READY?

Không nên đánh dấu RSocket là READY chỉ vì socket TCP đã kết nối hoặc WebSocket đã hoàn tất HTTP Upgrade. Những bước đó xác nhận transport, chưa xác nhận rằng hai đầu đã hoàn tất thỏa thuận ở tầng RSocket.

Một phiên có thể được xem là sẵn sàng khi:

1. Transport đã được thiết lập thành công.
2. Frame SETUP được gửi và chấp nhận.
3. Thư viện đã tạo RSocket session và trả quyền sử dụng session cho ứng dụng.
4. Các cấu hình cần thiết của ứng dụng, chẳng hạn xác thực hoặc khởi tạo dữ liệu phiên ở tầng ứng dụng, đã hoàn tất nếu hệ thống yêu cầu chúng trước khi nhận traffic.

Điều kiện thứ tư là chính sách của ứng dụng. RSocket SETUP thành công không tự chứng minh rằng mọi quyền truy cập nghiệp vụ đã hợp lệ, mọi dependency downstream đang khỏe hoặc mọi route đều sẵn sàng.

Trong RSocket Java, thao tác kết nối thường trả về một Publisher chỉ phát ra RSocket sau khi quá trình kết nối và thiết lập phiên thành công. Với Reactor, kết quả đó thường có kiểu <code>Mono&lt;RSocket&gt;</code>. Nếu Publisher kết thúc bằng lỗi, ứng dụng không được đưa connection vào trạng thái READY.

Ví dụ tạo client dùng TCP:

~~~java
Mono<RSocket> connection = RSocketConnector.create()
    .keepAlive(Duration.ofSeconds(20), Duration.ofSeconds(90))
    .connect(TcpClientTransport.create("localhost", 7000));

connection.subscribe(
    rsocket -> {
        log.info("RSocket session is READY");

        rsocket.onClose()
            .doFinally(signal ->
                log.info("RSocket session đã đóng: {}", signal))
            .subscribe();
    },
    error -> log.error("Không thể thiết lập RSocket session", error)
);
~~~

Khi callback nhận được đối tượng <code>RSocket</code>, thao tác connect đã hoàn tất và ứng dụng có thể sử dụng session. <code>onClose()</code> cung cấp một tín hiệu để theo dõi thời điểm phiên đóng. Trong ứng dụng Spring, nên quản lý việc subscribe và lưu giữ đối tượng connection ở một thành phần có vòng đời rõ ràng, chẳng hạn bean quản lý kết nối; tránh tạo connection rời rạc trong từng request nghiệp vụ.

Nếu dùng Spring Boot với RSocket server qua TCP, cấu hình cơ bản có thể là:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Với WebSocket, server cần được cấu hình transport và mapping path tương ứng. Client phải kết nối tới đúng endpoint WebSocket mà server công bố. Việc transport mở thành công vẫn cần theo sau bởi quá trình SETUP trước khi ứng dụng coi RSocket session là READY.

## 4. Theo dõi trạng thái sẵn sàng trong ứng dụng

Một client thường cần biết connection hiện tại có dùng được hay không để điều phối request. Có thể xây dựng một thành phần quản lý connection với các trách nhiệm:

- Lưu session hiện tại sau khi kết nối và SETUP thành công.
- Chuyển trạng thái sang READY khi nhận được session hợp lệ.
- Theo dõi <code>onClose()</code> để biết phiên đã kết thúc.
- Chuyển sang FAILED hoặc DISCONNECTED khi kết nối thất bại hay bị đóng.
- Chỉ cho phép thành phần nghiệp vụ gửi request khi session đang READY.
- Khởi tạo lại connection theo chính sách retry khi được phép.

Trạng thái READY nên được xem là một thông tin tại một thời điểm. Ngay sau khi kiểm tra READY, mạng vẫn có thể đứt trước khi request được gửi hoặc hoàn tất. Vì thế, mỗi thao tác gửi vẫn phải xử lý lỗi bất đồng bộ; kiểm tra trạng thái không thay thế cho xử lý lỗi.

Không nên dùng một biến boolean đơn lẻ nếu ứng dụng có nhiều lần reconnect đồng thời. Một connection cũ có thể phát tín hiệu đóng sau khi connection mới đã READY. Nếu callback cũ ghi đè trạng thái chung thành DISCONNECTED, ứng dụng sẽ hiểu nhầm rằng connection mới cũng đã đóng. Có thể gắn generation ID hoặc định danh session vào callback để chỉ cập nhật trạng thái nếu callback thuộc connection hiện tại.

Ví dụ logic quản lý trạng thái ở mức khái niệm:

~~~java
void onConnected(long generation, RSocket session) {
    if (generation != currentGeneration) {
        session.dispose();
        return;
    }

    currentSession = session;
    state = ConnectionState.READY;

    session.onClose()
        .doFinally(signal -> markClosedIfCurrent(generation, signal))
        .subscribe();
}
~~~

Đây là phác thảo để minh họa việc bảo vệ trạng thái trước callback đến muộn. Hàm <code>markClosedIfCurrent</code> cần kiểm tra generation ID trước khi cập nhật trạng thái, đồng thời có thể dùng <code>SignalType</code> để phân biệt phiên hoàn tất, lỗi hoặc bị hủy. Khi triển khai thật, cần dùng cơ chế đồng bộ phù hợp và đóng session cũ đúng cách. Một cách đơn giản hơn là đóng gói toàn bộ thao tác cập nhật vào một state manager có kiểm soát thứ tự sự kiện.

## 5. Keepalive và phát hiện connection không còn hoạt động

Một kết nối TCP có thể còn tồn tại ở cấp hệ điều hành trong khi ứng dụng bên kia đã dừng hoặc đường truyền trung gian không còn chuyển tiếp dữ liệu. RSocket có cơ chế KEEPALIVE ở tầng giao thức để hai peer kiểm tra sự sống của phiên.

Khi thiết lập session, hai bên trao đổi các tham số keepalive, gồm khoảng thời gian gửi keepalive và thời gian tối đa chấp nhận không nhận được frame từ peer. Peer có thể yêu cầu bên kia phản hồi keepalive. Nếu vượt quá thời gian sống đã thỏa thuận mà không nhận được traffic phù hợp, thư viện có thể xem connection là mất và kết thúc session.

Ví dụ cấu hình trong RSocket Java:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .keepAlive(
        Duration.ofSeconds(20),
        Duration.ofSeconds(90)
    );
~~~

Trong ví dụ, client gửi keepalive theo chu kỳ 20 giây và cấu hình thời gian tối đa 90 giây không nhận được dữ liệu từ peer trước khi xem connection là không còn khỏe. Giá trị thực tế cần dựa vào độ trễ mạng, proxy/load balancer, thời gian idle của hạ tầng và yêu cầu phát hiện sự cố của ứng dụng. Cấu hình quá ngắn có thể tạo reconnect giả khi mạng chập chờn; cấu hình quá dài làm ứng dụng phát hiện sự cố chậm.

Cần phân biệt ba cơ chế:

| Cơ chế | Phạm vi | Mục đích |
| --- | --- | --- |
| RSocket KEEPALIVE | Phiên RSocket | Phát hiện peer hoặc đường truyền không còn trao đổi frame trong thời gian cho phép. |
| TCP keepalive | Socket TCP và hệ điều hành | Kiểm tra kết nối TCP ở tầng transport theo cấu hình hệ điều hành. |
| Application heartbeat | Logic nghiệp vụ | Xác nhận một thành phần ứng dụng hoặc một chức năng cụ thể vẫn xử lý được yêu cầu. |

RSocket KEEPALIVE không phải là kiểm tra sức khỏe nghiệp vụ. Peer có thể trả lời keepalive trong khi cơ sở dữ liệu hoặc service downstream của nó đang lỗi. Nếu cần biết một chức năng nghiệp vụ có hoạt động hay không, hãy xây dựng health check hoặc heartbeat ở tầng ứng dụng.

## 6. Đóng một stream và đóng toàn bộ connection

Đóng stream và đóng connection có phạm vi ảnh hưởng khác nhau:

| Thao tác | Phạm vi ảnh hưởng | Hệ quả |
| --- | --- | --- |
| <code>CANCEL</code> | Một stream | Bên nhận dừng xử lý hoặc gửi dữ liệu trên stream tương ứng theo quy tắc giao thức. |
| <code>COMPLETE</code> | Một stream | Báo phía gửi đã hoàn tất chiều dữ liệu của tương tác tương ứng. |
| <code>ERROR</code> ở cấp stream | Một stream | Kết thúc tương tác do lỗi; connection có thể tiếp tục phục vụ stream khác. |
| Đóng RSocket connection | Toàn bộ phiên | Các stream còn hoạt động trên phiên đó bị ảnh hưởng và không thể tiếp tục qua connection cũ. |

Ví dụ, client đang theo dõi giá của ba mã cổ phiếu trên ba request-stream. Khi client hủy stream của một mã, hai stream còn lại vẫn có thể nhận dữ liệu. Nếu client đóng toàn bộ RSocket session, cả ba stream đều mất connection và cần được xử lý theo chính sách của ứng dụng.

Điểm này rất quan trọng khi thiết kế service realtime: không nên đóng connection dùng chung chỉ vì một stream gặp lỗi hoặc một người dùng ngừng theo dõi một chủ đề. Hãy hủy đúng subscription hoặc stream tương ứng.

## 7. Đóng connection có chủ đích

Khi ứng dụng cần dừng connection, nên thực hiện theo thứ tự để hạn chế mất dữ liệu:

1. Chuyển connection manager sang trạng thái CLOSING để chặn request mới.
2. Nếu nghiệp vụ cho phép, chờ các request đang xử lý hoàn tất trong một khoảng thời gian giới hạn.
3. Hủy các stream dài hạn hoặc tác vụ nền theo chính sách shutdown.
4. Đóng RSocket session và transport.
5. Ghi nhận thời điểm đóng, nguyên nhân và số stream còn hoạt động để phục vụ quan sát.

Trong RSocket Java, <code>RSocket.dispose()</code> cho phép ứng dụng chủ động đóng session ở phía đang quản lý đối tượng đó. <code>onClose()</code> là tín hiệu để quan sát việc đóng. Ở tầng giao thức, một peer có thể thông báo đóng connection bằng frame ERROR mang mã CONNECTION_CLOSE; transport sau đó được đóng. Nếu tiến trình bị kill hoặc mạng bị ngắt đột ngột, peer còn lại có thể chỉ phát hiện sự cố sau timeout hoặc khi thao tác I/O thất bại.

Ví dụ đóng session khi thành phần quản lý kết nối dừng:

~~~java
public final class RSocketSessionManager {
    private volatile RSocket current;

    public void close() {
        RSocket session = current;
        current = null;

        if (session != null) {
            session.dispose();
        }
    }
}
~~~

Đây là ví dụ tối giản. Trong hệ thống thật, nên phối hợp <code>close()</code> với state manager để chặn request mới trước khi lấy session, xử lý race condition giữa reconnect và shutdown, đồng thời đặt timeout cho giai đoạn chờ stream hoàn tất. Nếu dùng Spring, hãy gắn việc đóng session vào vòng đời bean hoặc hook shutdown của ứng dụng.

Đóng một connection không đảm bảo mọi request đang chạy đều hoàn tất. Nếu cần bảo toàn một thao tác quan trọng, ứng dụng phải có timeout, xác nhận nghiệp vụ, idempotency hoặc cơ chế lưu trạng thái độc lập với vòng đời socket.

## 8. Mất kết nối và reconnect

Connection có thể mất do server restart, client restart, network partition, proxy đóng idle connection, lỗi TLS hoặc timeout keepalive. Khi điều đó xảy ra, request đang chạy có thể nhận lỗi; stream dài hạn không còn tiếp tục trên session cũ.

Reconnect là quá trình tạo một transport và RSocket session mới. Một chiến lược thông dụng gồm:

- Phát hiện lỗi qua kết quả connect, lỗi request hoặc tín hiệu <code>onClose()</code>.
- Đưa connection manager về trạng thái DISCONNECTED hoặc FAILED.
- Chờ theo exponential backoff, thêm jitter để nhiều client không đồng loạt kết nối lại.
- Thử thiết lập transport và SETUP mới.
- Chỉ chuyển sang READY khi session mới thực sự được tạo thành công.
- Khôi phục các subscription hoặc stream nghiệp vụ cần thiết.

Không nên retry vô hạn với chu kỳ cố định rất ngắn. Điều đó có thể làm server quá tải đúng lúc đang phục hồi. Cần giới hạn thời gian retry, phân loại lỗi có thể thử lại và có cách đưa hệ thống về trạng thái cần can thiệp khi endpoint hoặc thông tin xác thực sai kéo dài.

Đặc biệt, không nên mặc định rằng một request bị ngắt giữa chừng chắc chắn chưa được server xử lý. Server có thể đã thực hiện side effect nhưng phản hồi chưa tới client. Nếu client gửi lại request tạo đơn hàng hoặc trừ tiền, thao tác có thể bị thực hiện hai lần. Các lệnh có side effect cần idempotency key, mã giao dịch hoặc cơ chế deduplication ở tầng nghiệp vụ.

## 9. Resume và giới hạn phục hồi phiên

RSocket có extension Resume để hỗ trợ tiếp tục một phiên sau khi transport bị gián đoạn tạm thời. Khi hai bên cấu hình và hỗ trợ Resume, client có thể kết nối lại và cung cấp thông tin phiên để peer xác định có thể tiếp tục từ vị trí frame đã xác nhận hay không.

Resume có các điều kiện và giới hạn:

- Phải được bật và cấu hình ở cả hai phía theo cách tương thích.
- Hai phía cần giữ trạng thái phiên và dữ liệu frame cần thiết trong giới hạn buffer.
- Khoảng gián đoạn phải nằm trong khả năng lưu giữ trạng thái của phiên.
- Nếu trạng thái hoặc frame cần thiết đã bị loại bỏ, phiên không thể resume và ứng dụng phải tạo session mới.

Resume không đồng nghĩa với việc mọi thao tác nghiệp vụ được thực thi chính xác một lần. Nó phục hồi việc truyền frame trong phạm vi giao thức; tính đúng đắn của side effect, transaction và trạng thái nghiệp vụ vẫn cần được bảo vệ ở tầng ứng dụng. Với nhiều hệ thống, reconnect rồi đăng ký lại stream có thể đơn giản và phù hợp hơn resume.

## 10. Quan sát và kiểm thử vòng đời kết nối

Một connection manager nên ghi nhận các mốc có ý nghĩa:

| Sự kiện | Thông tin nên quan sát |
| --- | --- |
| Bắt đầu connect | Địa chỉ đích, transport, thời điểm bắt đầu, generation ID. |
| Transport mở | Thời gian mở transport, loại endpoint, TLS nếu có. |
| SETUP thành công | Thời gian thiết lập session, phiên bản và cấu hình giao thức phù hợp để chẩn đoán. |
| READY | Số connection sẵn sàng, thời điểm sẵn sàng, thời gian từ lúc bắt đầu connect. |
| Keepalive timeout | Thời gian không nhận frame, peer và nguyên nhân kết thúc nếu biết. |
| Connection đóng | Đóng chủ động hay do lỗi, thời gian sống của session, số stream đang hoạt động. |
| Reconnect | Số lần thử, thời gian backoff, kết quả và thời gian phục hồi. |

Không ghi payload nhạy cảm hoặc metadata xác thực vào log. Có thể dùng connection ID hoặc generation ID để liên kết log của cùng một phiên mà không làm lộ thông tin bảo mật.

Các tình huống kiểm thử nên bao gồm:

1. Server đang chạy: client connect thành công, SETUP hoàn tất và chuyển sang READY.
2. Server không lắng nghe: connect thất bại và client không đánh dấu READY.
3. Server từ chối SETUP: phiên không được đưa vào sử dụng.
4. Đang có nhiều stream: hủy một stream nhưng các stream còn lại vẫn hoạt động.
5. Đóng session có chủ đích: request mới bị chặn và callback đóng được quan sát.
6. Ngắt mạng đột ngột: client phát hiện lỗi hoặc timeout, sau đó reconnect theo chính sách.
7. Callback đóng của session cũ đến sau khi session mới READY: trạng thái session mới vẫn được giữ chính xác.
8. Resume được bật: kiểm thử cả trường hợp có thể resume và trường hợp phải tạo session mới.

Nên kiểm thử với cả TCP và WebSocket nếu ứng dụng hỗ trợ hai transport, bởi quá trình thiết lập đường truyền và các lỗi hạ tầng có thể khác nhau dù tầng RSocket giữ cùng mô hình tương tác.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đánh dấu READY ngay sau khi TCP connect | Request có thể được gửi trước khi SETUP hoàn tất. | Chỉ đánh dấu READY khi Publisher connect phát ra RSocket session. |
| Xem một stream hoàn tất là connection đã đóng | Ứng dụng đóng nhầm phiên dùng chung. | Theo dõi tín hiệu stream và connection riêng biệt. |
| Không theo dõi <code>onClose()</code> | Ứng dụng giữ tham chiếu tới session đã mất. | Gắn listener đóng vào connection manager. |
| Retry mọi lỗi ngay lập tức | Tạo vòng lặp reconnect và tăng tải lên server. | Dùng backoff, jitter, giới hạn retry và phân loại lỗi. |
| Gửi lại command không idempotent | Side effect có thể bị thực hiện hai lần. | Dùng idempotency key hoặc deduplication. |
| Dùng keepalive như health check nghiệp vụ | Connection có thể khỏe trong khi dependency ứng dụng lỗi. | Bổ sung health check hoặc heartbeat nghiệp vụ riêng. |
| Không bảo vệ callback của session cũ | Callback muộn ghi đè trạng thái connection mới. | Dùng generation ID hoặc đồng bộ trạng thái theo session. |

## 12. Ghi nhớ

- Transport mở thành công chưa có nghĩa RSocket session đã READY; cần hoàn tất SETUP.
- Một RSocket connection có thể mang nhiều stream độc lập; kết thúc một stream không đóng connection.
- <code>onClose()</code> giúp quan sát thời điểm session kết thúc; <code>dispose()</code> cho phép ứng dụng chủ động đóng session.
- KEEPALIVE phát hiện peer hoặc đường truyền im lặng quá thời gian cho phép, nhưng không xác nhận sức khỏe nghiệp vụ.
- Reconnect tạo session mới; các stream cần thiết phải được khôi phục theo chính sách của ứng dụng.
- Resume là extension cần cấu hình và có giới hạn lưu giữ trạng thái; không thay thế idempotency hay đảm bảo thực thi nghiệp vụ đúng một lần.
- Quản lý trạng thái READY, CLOSING và CLOSED ở một connection manager giúp ứng dụng xử lý shutdown, lỗi mạng và reconnect nhất quán.
