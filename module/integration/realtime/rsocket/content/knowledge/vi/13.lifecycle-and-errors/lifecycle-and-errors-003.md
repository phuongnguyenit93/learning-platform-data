# Phân loại lỗi thiết lập, lỗi kết nối và lỗi cấp luồng

RSocket cho phép nhiều tương tác độc lập cùng hoạt động trên một kết nối. Vì vậy, khi có lỗi, điều quan trọng đầu tiên là xác định lỗi thuộc phạm vi nào: quá trình thiết lập phiên chưa thành công, toàn bộ kết nối bị ảnh hưởng, hay chỉ một stream cụ thể gặp sự cố.

Ba phạm vi này có cách xử lý khác nhau. Lỗi thiết lập khiến peer không thể bắt đầu phiên RSocket. Lỗi kết nối ảnh hưởng đến phiên và các stream đang chạy trên kết nối đó. Lỗi cấp luồng chỉ kết thúc tương tác mang Stream ID tương ứng; những stream khác có thể tiếp tục. Phân loại đúng giúp ứng dụng Java/Spring Boot trả lỗi phù hợp, tránh retry sai tầng và giải phóng tài nguyên đúng lúc.

## 1. Ba phạm vi lỗi trong vòng đời RSocket

Một phiên RSocket thường đi qua các giai đoạn:

1. **Transport:** hai peer mở kênh TCP hoặc WebSocket; nếu dùng TLS, quá trình bắt tay TLS diễn ra ở tầng này.
2. **Setup:** peer khởi tạo gửi frame SETUP để thương lượng tham số phiên, MIME type và dữ liệu setup tùy chọn.
3. **Tương tác:** sau khi phiên được thiết lập, các peer mở request-response, fire-and-forget, request-stream hoặc request-channel.
4. **Kết thúc:** từng stream có thể hoàn tất, bị hủy hoặc lỗi; sau cùng kết nối có thể được đóng.

~~~mermaid
flowchart TD
    A[Transport mở] --> B[SETUP]
    B -->|Setup thành công| C[Phiên RSocket sẵn sàng]
    B -->|Setup bị từ chối hoặc không hợp lệ| D[Lỗi thiết lập]
    C --> E[Request / Stream]
    E -->|Một tương tác lỗi| F[Lỗi cấp luồng]
    E -->|Kết nối lỗi hoặc đóng| G[Lỗi cấp kết nối]
    F --> C
    G --> H[Đóng các tương tác trên kết nối]
~~~

| Phạm vi | Thời điểm | Ảnh hưởng | Ví dụ |
|---|---|---|---|
| Setup error | Trước khi phiên sẵn sàng | Không tạo được phiên RSocket | MIME type không hỗ trợ, setup payload không hợp lệ, chính sách xác thực từ chối |
| Connection error | Trong vòng đời kết nối | Ảnh hưởng toàn bộ phiên và stream đang chạy trên kết nối | Peer đóng kết nối, lỗi giao thức cấp kết nối, keepalive timeout |
| Stream error | Sau khi một tương tác được mở | Chỉ tương tác có Stream ID đó kết thúc | Request không hợp lệ, lỗi nghiệp vụ, downstream phục vụ riêng request bị lỗi |

Transport error là một nhóm sự cố ở lớp thấp hơn. Ví dụ TCP reset hoặc TLS handshake thất bại có thể xảy ra trước khi RSocket trao đổi được frame. Khi đó ứng dụng nhận lỗi từ transport thay vì một ERROR frame có mã RSocket.

## 2. Setup error: lỗi trước khi phiên được thiết lập

Setup bắt đầu khi initiator gửi frame SETUP. Frame này mang thông tin cần thiết để hai bên thống nhất phiên, chẳng hạn phiên bản giao thức, MIME type của data và metadata, cùng setup payload tùy chọn.

Nếu responder không thể chấp nhận setup, nó có thể gửi ERROR với Stream ID bằng 0 và đóng kết nối. Không có stream nghiệp vụ nào được mở thành công trên phiên đó.

Các nguyên nhân thường gặp:

- Phiên bản giao thức hoặc tham số SETUP không được hỗ trợ.
- MIME type data hoặc metadata không hợp lệ hoặc không được hỗ trợ.
- Setup payload không đúng định dạng mà server mong đợi.
- Thông tin xác thực trong setup bị thiếu, hết hạn hoặc không hợp lệ.
- Server từ chối peer theo chính sách truy cập, tenant hoặc giới hạn tài nguyên.
- Cấu hình client và server không tương thích.

### Một số mã lỗi thiết lập và resume

| Mã | Tên | Ý nghĩa khái quát |
|---:|---|---|
| 0x00000001 | INVALID_SETUP | Setup frame hoặc tham số setup không hợp lệ |
| 0x00000002 | UNSUPPORTED_SETUP | Setup chứa phiên bản hoặc khả năng không được hỗ trợ |
| 0x00000003 | REJECTED_SETUP | Responder chủ động từ chối thiết lập phiên |
| 0x00000004 | REJECTED_RESUME | Yêu cầu resume phiên cũ bị từ chối |

REJECTED_RESUME thuộc nhánh khôi phục phiên: client muốn tiếp tục một phiên đã gián đoạn nhưng responder không thể hoặc không chấp nhận khôi phục trạng thái đó. Khi resume bị từ chối, ứng dụng cần quyết định có tạo phiên mới và đăng ký lại stream từ cursor hay không.

### Xử lý setup error ở client

Trong Spring, thao tác kết nối trả về một publisher. Lỗi khi kết nối có thể được xử lý tại điểm tạo requester:

~~~java
Mono<RSocketRequester> requesterMono =
    RSocketRequester.builder()
        .connectTcp("localhost", 7000)
        .doOnError(error ->
            log.error("Cannot establish RSocket session", error));
~~~

Đây là nơi phù hợp để phân biệt lỗi không mở được phiên với lỗi của một request đã chạy trên phiên. Ứng dụng có thể phân loại lỗi cấu hình, lỗi xác thực và lỗi tạm thời của transport để quyết định có cần sửa cấu hình, làm mới thông tin xác thực hay thử kết nối lại.

Không nên retry liên tục một setup bị từ chối vì sai MIME type hoặc sai credentials. Những lỗi cấu hình và xác thực thường cần sửa nguyên nhân trước khi kết nối lại.

## 3. Connection error: lỗi ảnh hưởng toàn bộ phiên

Sau khi SETUP thành công, một kết nối RSocket có thể phục vụ nhiều stream đồng thời. Lỗi ở phạm vi kết nối có thể khiến mọi stream đang hoạt động trên kết nối đó bị gián đoạn.

Nguyên nhân có thể gồm:

- Peer gửi frame CONNECTION_ERROR hoặc CONNECTION_CLOSE.
- Transport TCP/WebSocket bị đóng hoặc reset.
- TLS session hoặc tầng mạng gặp lỗi.
- Keepalive không nhận được phản hồi trong thời gian cho phép.
- Lỗi giao thức khiến một peer không thể tiếp tục duy trì phiên.
- Server đóng kết nối khi shutdown hoặc bảo trì.

### Mã lỗi kết nối

| Mã | Tên | Ý nghĩa khái quát |
|---:|---|---|
| 0x00000101 | CONNECTION_ERROR | Kết nối đang bị kết thúc; peer có thể đóng ngay mà không chờ các stream đang chạy |
| 0x00000102 | CONNECTION_CLOSE | Kết nối đang được đóng có trật tự; peer phải chờ các stream đang chạy kết thúc trước khi đóng |

Các lỗi kết nối được biểu đạt bằng ERROR frame có Stream ID bằng 0. Nếu transport bị mất đột ngột, có thể không có ERROR frame nào được nhận; client chỉ quan sát thấy socket đóng hoặc lỗi transport.

Khi kết nối đóng, các stream đang chạy trên kết nối đó không thể tiếp tục truyền frame trên chính kết nối đã mất. Ứng dụng cần xử lý từng tương tác đang chờ và quyết định có khôi phục phiên hay tạo request mới.

### Keepalive giúp phát hiện kết nối không còn phản hồi

RSocket sử dụng frame KEEPALIVE để peer kiểm tra trạng thái phiên. Nếu không nhận được keepalive hợp lệ trong khoảng thời gian đã cấu hình, peer có thể xem kết nối là đã mất và đóng phiên.

Keepalive chỉ phản ánh sức khỏe của kết nối. Nó không chứng minh một route cụ thể đang xử lý tốt; server vẫn có thể trả keepalive trong khi một truy vấn database hoặc một stream nghiệp vụ bị nghẽn.

### Theo dõi vòng đời kết nối

Ở tầng RSocket core, đối tượng kết nối cung cấp tín hiệu đóng phiên qua onClose() và có thể được đóng chủ động bằng dispose(). Với Spring abstraction, cần theo dõi lỗi từ publisher kết nối và quản lý vòng đời của requester theo phạm vi ứng dụng.

Ví dụ quản lý kết nối ở tầng core:

~~~java
RSocket socket = connector.connect(transport).block();

socket.onClose()
    .doFinally(signal ->
        log.info("RSocket connection closed: {}", signal))
    .subscribe();
~~~

Ví dụ trên minh họa việc quan sát vòng đời một RSocket đã kết nối; không nên gọi block() trên event-loop hoặc trong reactive request path. Ứng dụng Spring reactive nên giữ chuỗi kết nối dưới dạng Mono hoặc quản lý nó trong lifecycle component phù hợp.

## 4. Stream error: lỗi chỉ ảnh hưởng một tương tác

Mỗi tương tác RSocket có một Stream ID khác 0. Khi một stream gặp lỗi, peer có thể gửi ERROR frame với Stream ID của tương tác đó. Subscriber của stream nhận lỗi terminal; các stream khác trên cùng kết nối vẫn có thể tiếp tục.

Nguyên nhân phổ biến:

- Request payload không hợp lệ.
- Người dùng không có quyền thực hiện thao tác.
- Tài nguyên được yêu cầu không tồn tại.
- Quy tắc nghiệp vụ từ chối request.
- Một dịch vụ downstream phục vụ riêng request đó bị lỗi.
- Publisher phát onError.

### Một số mã lỗi cấp stream

| Mã | Tên | Ý nghĩa khái quát |
|---:|---|---|
| 0x00000201 | APPLICATION_ERROR | Lỗi ứng dụng khi xử lý tương tác |
| 0x00000202 | REJECTED | Responder từ chối một request hợp lệ và bảo đảm chưa xử lý request đó |
| 0x00000203 | CANCELED | Responder hủy request; có thể đã bắt đầu xử lý và phát sinh tác dụng phụ |
| 0x00000204 | INVALID | Request hoặc thao tác không hợp lệ |

Các mã trên có phạm vi stream; ERROR frame mang Stream ID tương ứng. Cần phân biệt mã lỗi CANCELED với frame CANCEL: CANCEL là frame requester gửi để hủy tương tác; CANCELED là mã trong ERROR cho biết responder đã hủy request và có thể đã bắt đầu xử lý. Ý nghĩa chi tiết và thông điệp lỗi cần được ứng dụng chuẩn hóa, không nên phụ thuộc vào chuỗi exception nội bộ.

### Lỗi handler trong Spring Boot

Một message handler trả về Mono hoặc Flux. Nếu publisher phát lỗi, lỗi được chuyển thành lỗi của tương tác RSocket đó:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<Order> find(String orderId) {
        return orderService.find(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)));
    }
}
~~~

Nếu OrderNotFoundException phát ra, request hiện tại kết thúc bằng lỗi. Các request khác trên cùng requester connection không vì thế mà tự động bị đóng.

Ứng dụng nên ánh xạ exception sang lỗi an toàn, có mã ổn định và không chứa stack trace, câu SQL hoặc dữ liệu nhạy cảm. Cách framework chuyển exception thành mã RSocket cụ thể phụ thuộc integration và phiên bản thư viện; hãy xác minh behavior thực tế khi cần một mã protocol cụ thể.

## 5. Nhìn Stream ID để xác định phạm vi lỗi

Stream ID là dấu hiệu quan trọng khi đọc trace hoặc log frame:

- **Stream ID = 0:** frame thuộc phạm vi kết nối hoặc thiết lập phiên, ví dụ SETUP error, CONNECTION_ERROR và CONNECTION_CLOSE.
- **Stream ID khác 0:** frame thuộc một tương tác cụ thể, ví dụ ERROR hoặc CANCEL của stream đó.

~~~mermaid
flowchart TD
    A[Nhận ERROR frame] --> B{Stream ID?}
    B -->|0| C[Lỗi setup hoặc connection]
    C --> D[Kiểm tra SETUP, transport, keepalive, shutdown]
    B -->|Khác 0| E[Lỗi của một stream]
    E --> F[Kiểm tra route, payload, quyền và downstream]
    F --> G[Chỉ kết thúc tương tác tương ứng]
~~~

Không nên kết luận chỉ dựa vào text của exception. Ví dụ Connection reset by peer thường là lỗi transport; APPLICATION_ERROR là lỗi cấp stream. Cần kết hợp Stream ID, ERROR code, Frame Type, log transport và thời điểm xảy ra.

## 6. Phân loại theo tình huống thực tế

| Triệu chứng | Phạm vi có khả năng | Hướng kiểm tra |
|---|---|---|
| Client không thể kết nối vì sai port | Transport/setup | Host, port, listener, firewall và transport |
| Server từ chối MIME type | Setup | MIME type data/metadata ở hai phía |
| Token setup hết hạn | Setup | Credentials, thời hạn token và chính sách xác thực |
| TCP reset làm nhiều request cùng lỗi | Connection/transport | Socket, proxy, mạng, server restart |
| Keepalive timeout | Connection | Khoảng keepalive, mạng có jitter, peer bị treo |
| Một route trả APPLICATION_ERROR | Stream | Handler, exception, dependency của request |
| Một request bị REJECTED | Stream | Chính sách route, quyền hoặc trạng thái nghiệp vụ |
| Một stream bị CANCEL | Stream | Subscriber đã hủy, timeout hoặc client không còn cần dữ liệu |
| Resume bị REJECTED_RESUME | Resume/setup | Resume state, token, thời gian lưu trạng thái và khả năng hỗ trợ |

Một dấu hiệu hữu ích là số lượng stream bị ảnh hưởng. Nếu nhiều stream trên cùng kết nối thất bại gần như đồng thời, hãy kiểm tra connection hoặc transport trước. Nếu chỉ một route hoặc một Stream ID lỗi, hãy bắt đầu từ request và handler tương ứng.

## 7. Chiến lược xử lý khác nhau theo phạm vi

### Với setup error

- Kiểm tra phiên bản giao thức, MIME type và setup metadata.
- Xác thực token và quyền kết nối trước khi retry.
- Phân biệt lỗi cấu hình cố định với lỗi tạm thời.
- Không tạo vòng lặp reconnect khi server chủ động từ chối setup.
- Ghi lại lý do từ chối an toàn để có thể chẩn đoán.

### Với connection error

- Đánh dấu phiên hiện tại không còn khả dụng.
- Dừng hoặc hủy các request phụ thuộc vào phiên đã đóng.
- Đóng tài nguyên liên quan và tránh để subscriber treo.
- Reconnect theo backoff có jitter nếu nguyên nhân có thể phục hồi.
- Nếu dùng RSocket Resumption, thử resume khi client và server hỗ trợ và trạng thái còn hiệu lực.
- Nếu resume thất bại, tạo phiên mới và đăng ký lại stream từ cursor nếu nghiệp vụ yêu cầu.

### Với stream error

- Chỉ xử lý lỗi của request/stream tương ứng.
- Trả mã lỗi nghiệp vụ ổn định, không làm lộ chi tiết nội bộ.
- Chỉ retry lỗi tạm thời và có giới hạn.
- Không retry validation, authorization hoặc lỗi request không hợp lệ.
- Với stream dài hạn, quyết định rõ lỗi có làm kết thúc toàn bộ stream hay có thể biểu diễn thành kết quả thất bại của một phần tử.

## 8. Retry cần dựa trên loại lỗi và tính idempotent

Retry setup, retry kết nối và retry stream là ba hành động khác nhau:

- **Reconnect:** mở một phiên RSocket mới sau khi connection mất.
- **Resume:** tiếp tục phiên cũ nếu cơ chế resumption được hỗ trợ và trạng thái còn hợp lệ.
- **Retry request:** tạo một tương tác mới sau khi request trước lỗi.
- **Replay từ cursor:** mở stream mới từ vị trí sự kiện do ứng dụng quản lý.

Không phải lỗi nào cũng nên retry. Lỗi cấu hình setup hoặc authorization cần sửa nguyên nhân. Lỗi transport tạm thời có thể reconnect. Lỗi ứng dụng chỉ nên retry nếu được phân loại là tạm thời.

Với thao tác ghi, timeout hoặc connection error không chứng minh server chưa thực hiện nghiệp vụ. Server có thể đã commit dữ liệu nhưng response chưa đến client. Dùng idempotency key hoặc request ID để request lặp không tạo tác dụng phụ trùng.

Một chính sách retry nên có:

- Danh sách lỗi được phép retry.
- Số lần thử tối đa.
- Exponential backoff và jitter.
- Tổng deadline cho toàn bộ lần thử.
- Cơ chế idempotency hoặc deduplication cho thao tác có tác dụng phụ.
- Metrics về số lần retry, reconnect, resume và kết quả cuối.

## 9. Ví dụ phân loại lỗi ở client với Reactor

Có thể đặt logic phân loại tại biên gọi dịch vụ. Ví dụ sau minh họa ý tưởng: chỉ chuyển sang fallback cho lỗi được nhận diện là tạm thời; lỗi nghiệp vụ được giữ nguyên để caller xử lý.

~~~java
Mono<Order> findOrder(RSocketRequester requester, String id) {
    return requester
        .route("orders.find")
        .data(id)
        .retrieveMono(Order.class)
        .onErrorResume(error -> {
            if (isTransientTransportFailure(error)) {
                return loadOrderFromCache(id);
            }
            return Mono.error(error);
        });
}
~~~

Trong code thực tế, isTransientTransportFailure phải dựa trên exception type của transport/driver đang dùng và nguyên nhân gốc, không chỉ dựa trên nội dung message. Cache fallback chỉ phù hợp nếu nghiệp vụ cho phép dữ liệu cũ.

Nếu lỗi xuất hiện khi connectTcp hoặc connectWebSocket, đó là lỗi mở phiên và cần xử lý ở publisher kết nối. Nếu lỗi xuất hiện trong retrieveMono hoặc retrieveFlux, đó là lỗi của tương tác hoặc lỗi kết nối làm gián đoạn tương tác; cần kiểm tra nguyên nhân gốc và trạng thái phiên.

## 10. Quan sát và log lỗi

Để phân loại nhanh, mỗi log hoặc trace nên có:

- Connection ID hoặc session correlation ID.
- Stream ID nếu sự cố thuộc một tương tác.
- Route và interaction model.
- Frame type và ERROR code nếu có.
- Transport type TCP/WebSocket và trạng thái TLS nếu có.
- Thời điểm SETUP, disconnect, reconnect, resume và close.
- Exception class, root cause và mã lỗi ứng dụng.
- Số stream đang hoạt động và số stream bị ảnh hưởng.

Không ghi access token, password, payload nhạy cảm hoặc metadata xác thực vào log. Nếu cần debug payload, dùng dữ liệu đã ẩn danh hoặc chỉ ghi kích thước và schema.

Một số metric hữu ích:

| Metric | Mục đích |
|---|---|
| Setup success/failure count | Phát hiện lỗi cấu hình hoặc xác thực |
| Connection open/close count | Theo dõi vòng đời phiên |
| Transport disconnect count | Phát hiện mạng hoặc server restart |
| Stream error count theo route/code | Tìm handler hoặc dependency lỗi |
| Active stream count | Theo dõi tải và rò rỉ tương tác |
| Reconnect/resume success rate | Đánh giá khả năng phục hồi |
| Error rate và latency p95/p99 | Phân biệt lỗi tăng do tải hoặc độ trễ |

## 11. Kiểm thử từng phạm vi lỗi

Nên có kiểm thử riêng cho setup, connection và stream vì chúng có hậu quả khác nhau.

### Kiểm thử setup error

- Khởi tạo client với MIME type không được server hỗ trợ.
- Gửi setup metadata không hợp lệ hoặc thiếu thông tin bắt buộc.
- Dùng credentials không hợp lệ.
- Xác nhận phiên không được tạo và lỗi được phân loại ở bước kết nối.

### Kiểm thử connection error

- Đóng server hoặc transport khi có nhiều stream đang chạy.
- Mô phỏng TCP reset hoặc WebSocket close.
- Làm peer không phản hồi keepalive.
- Xác nhận mọi stream trên connection được thông báo kết thúc và tài nguyên được dọn dẹp.
- Kiểm tra reconnect hoặc resume theo cấu hình.

### Kiểm thử stream error

- Một route phát lỗi nghiệp vụ trong khi route khác vẫn hoạt động trên cùng kết nối.
- Gửi request sai cấu trúc hoặc không có quyền.
- Hủy một stream và xác nhận stream khác không bị ảnh hưởng.
- Xác nhận lỗi được chuyển đến đúng subscriber, không làm đóng connection.

Ví dụ kiểm tra một publisher phát lỗi bằng Reactor Test:

~~~java
StepVerifier.create(
        service.findOrder("missing-id"))
    .expectError(OrderNotFoundException.class)
    .verify();
~~~

Đây là unit test cho lỗi ở tầng publisher. Cần bổ sung integration test qua RSocket client/server để xác nhận mã ERROR, Stream ID và phạm vi ảnh hưởng đúng như mong đợi.

## 12. Checklist chẩn đoán

Khi gặp lỗi RSocket, hãy đi theo trình tự:

1. **Phiên đã SETUP thành công chưa?** Nếu chưa, kiểm tra transport, SETUP parameters, MIME type và xác thực.
2. **Stream ID của lỗi là gì?** ID bằng 0 hướng tới setup/connection; ID khác 0 hướng tới tương tác cụ thể.
3. **Có bao nhiêu stream bị ảnh hưởng?** Nhiều stream cùng lỗi thường gợi ý vấn đề kết nối; một stream lỗi thường gợi ý vấn đề route hoặc request.
4. **ERROR code hoặc root cause là gì?** Phân biệt lỗi giao thức, lỗi ứng dụng và lỗi transport.
5. **Có nên retry không?** Kiểm tra tính tạm thời, deadline và idempotency.
6. **Cần phục hồi theo cách nào?** Reconnect, resume hay tạo stream mới từ cursor.
7. **Tài nguyên đã được dọn chưa?** Kiểm tra subscription, buffer, connection pool và tác vụ nền.

## 13. Kết luận

Setup error xảy ra trước khi phiên RSocket sẵn sàng; connection error ảnh hưởng toàn bộ phiên và các stream đang chạy; stream error chỉ kết thúc tương tác có Stream ID tương ứng. Stream ID bằng 0 thường biểu thị lỗi ở phạm vi thiết lập hoặc kết nối, còn Stream ID khác 0 gắn lỗi với một tương tác cụ thể. Transport failure có thể không mang ERROR frame vì kết nối thấp hơn đã mất trước khi giao thức gửi được thông báo.

Trong ứng dụng Java/Spring Boot, hãy xử lý lỗi tại đúng ranh giới: lỗi connect/setup ở publisher tạo requester, lỗi handler ở stream tương ứng, và lỗi transport ở lifecycle của phiên. Kết hợp mã lỗi ổn định, log có correlation ID, retry có giới hạn, idempotency và kiểm thử riêng cho từng phạm vi để hệ thống realtime có thể chẩn đoán và phục hồi mà không làm gián đoạn những tương tác không liên quan.

Tài liệu tham khảo: [RSocket Protocol – Error Handling](https://rsocket.io/about/protocol/) và [RSocket Implementations](https://rsocket.io/about/implementations/).

