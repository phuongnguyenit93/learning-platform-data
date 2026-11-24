# Giới hạn phạm vi bảo vệ của leasing trên từng kết nối

RSocket hỗ trợ **leasing** để responder kiểm soát số request mà một requester được phép khởi tạo trong một khoảng thời gian. Một lease grant mang hai thông tin: thời gian hiệu lực (TTL) và số request được cấp. Cơ chế này giúp server điều tiết việc tiếp nhận request trên từng kết nối khi tải tăng, hàng đợi đầy hoặc tài nguyên phía sau bị giới hạn.

Phạm vi của lease rất quan trọng. Một lease được gửi qua một RSocket connection và bảo vệ request được khởi tạo trên chính kết nối đó. Nếu cùng một người dùng mở nhiều kết nối, mỗi kết nối có thể nhận một grant riêng. Vì vậy, leasing theo kết nối không tự động trở thành quota toàn cục theo user, tenant hay service. Muốn bảo vệ các phạm vi đó, server cần phối hợp lease với bộ cấp quota dùng chung.

Bài học này giải thích vòng đời lease, phạm vi đếm request, khác biệt với backpressure và giới hạn concurrency, cùng cách thiết kế chính sách leasing trong Java và Spring RSocket.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích một lease grant gồm TTL và số request được phép.
- Xác định leasing bảo vệ request trên một connection như thế nào.
- Phân biệt request được khởi tạo với các payload tiếp theo của một stream.
- Hiểu giới hạn của leasing khi một client mở nhiều kết nối.
- Kết hợp lease theo connection với quota theo user, tenant và toàn service.
- Phân biệt leasing với Reactive Streams demand, byte rate limit và giới hạn request đồng thời.
- Thiết kế cấp phát, làm mới và giám sát lease theo tải thực tế.

## 1. Leasing là gì?

Leasing là cơ chế admission control ở tầng giao thức RSocket. Responder cấp cho requester một lượng quyền khởi tạo request trong một khoảng thời gian. Requester phải tôn trọng quyền được cấp và chỉ gửi request mới khi còn lease hợp lệ.

Một lease grant có hai thành phần:

- **TTL (time to live)**: khoảng thời gian grant còn hiệu lực.
- **Allowed requests**: số request requester được phép khởi tạo trong thời gian đó.

Ví dụ, responder cấp một lease có TTL 10 giây và 40 request. Requester có thể khởi tạo tối đa 40 request trong thời gian grant còn hiệu lực. Nếu đã dùng hết 40 quyền trước khi hết 10 giây, requester phải chờ grant tiếp theo. Nếu TTL hết trước khi dùng hết số quyền, phần quyền chưa dùng cũng hết hiệu lực.

~~~text
Lease grant:
    TTL              = 10 giây
    Allowed requests = 40

Requester:
    Khởi tạo request 1  -> còn 39
    Khởi tạo request 2  -> còn 38
    ...
    Khởi tạo request 40 -> còn 0

Không còn quyền khởi tạo request mới cho đến grant tiếp theo.
~~~

Leasing là chính sách cấp quyền gửi request trong một khoảng thời gian. Nó không phải một thông điệp xác thực và không chứng minh requester có quyền truy cập dữ liệu nghiệp vụ.

### 1.1. Lease frame

RSocket biểu diễn việc cấp lease bằng frame **LEASE**. Frame này mang TTL và số request được phép. Requester nhận grant và theo dõi quyền còn lại trong vòng đời kết nối.

Khi sử dụng leasing, requester báo hiệu khả năng hỗ trợ lease trong quá trình SETUP. Responder gửi các LEASE frame để cấp hoặc làm mới quyền. Cả hai phía cần bật và triển khai cơ chế leasing tương thích; ứng dụng không nên giả định server sẽ tự gửi lease nếu requester không tham gia cơ chế này.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    C->>S: SETUP (lease support)
    S-->>C: LEASE (TTL = 10s, requests = 40)
    C->>S: REQUEST_RESPONSE
    C->>S: REQUEST_STREAM
    C->>S: REQUEST_FNF
    Note over C: Quyền khởi tạo request giảm theo grant
    S-->>C: LEASE (grant tiếp theo)
    C->>S: REQUEST_CHANNEL
~~~

Sơ đồ mô tả luồng khái niệm. Cách cấu hình cụ thể phụ thuộc phiên bản rsocket-java hoặc Spring RSocket đang dùng.

### 1.2. Request nào tiêu thụ lease?

Lease giới hạn số interaction request được requester khởi tạo. Các loại request có thể gồm:

| Interaction | Có tiêu thụ một quyền khởi tạo? | Giải thích |
|---|---:|---|
| Request-response | Có | Một request tạo một interaction và chờ một response |
| Fire-and-forget | Có | Một request được gửi dù không có response stream |
| Request-stream | Có | Một request khởi tạo stream response |
| Request-channel | Có | Request đầu tiên khởi tạo channel hai chiều |

Các PAYLOAD tiếp theo trong một request-stream hoặc request-channel đang tồn tại không phải những request khởi tạo mới. Chúng thuộc interaction đã mở. Tương tự, REQUEST_N là tín hiệu cấp thêm demand cho phần tử của stream, không phải một request mới tiêu thụ lease.

Điểm này giúp phân biệt lease với flow control: lease đếm việc khởi tạo interaction, còn demand điều tiết số payload mà subscriber có thể nhận trong stream.

## 2. Phạm vi của lease là từng RSocket connection

RSocket có thể multiplex nhiều interaction trên cùng một connection. Lease được cấp qua connection đó và giới hạn tổng số request mà requester có thể khởi tạo trên chính connection đó trong grant còn hiệu lực.

Ví dụ, một client mở một TCP connection đến server và sử dụng nó cho nhiều route:

- orders.find dùng request-response.
- notifications.live dùng request-stream.
- audit.record dùng fire-and-forget.

Các request khởi tạo trên cùng connection cùng tiêu thụ ngân sách lease của connection. Lease không tự chia riêng 40 quyền cho mỗi route.

~~~mermaid
flowchart TD
    C["Một RSocket connection"]
    C --> L["Một lease grant: 40 request / 10 giây"]
    L --> A["orders.find"]
    L --> B["notifications.live"]
    L --> D["audit.record"]
    A --> R["Cùng tiêu thụ ngân sách connection"]
    B --> R
    D --> R
~~~

Điều này có nghĩa lease là một lớp bảo vệ ở ranh giới kết nối. Responder có thể giảm grant cho một connection mà không cần thay đổi payload hoặc logic của từng route.

### 2.1. Nhiều connection tạo ra nhiều ngân sách riêng

Giả sử một user mở ba RSocket connection đến cùng service. Nếu mỗi connection nhận 40 request trong 10 giây, tổng quyền khởi tạo có thể đạt:

**3 × 40 = 120 request trong 10 giây**

Nếu user mở thêm connection, tổng ngân sách theo connection cũng có thể tăng theo. Do đó, lease riêng lẻ không ngăn được một user tiêu thụ nhiều tài nguyên bằng cách mở nhiều connection.

| Phạm vi | Số connection | Grant mỗi connection | Tổng quyền tối đa theo grant |
|---|---:|---:|---:|
| Một client | 1 | 40 request/10 giây | 40 request/10 giây |
| Một client | 3 | 40 request/10 giây | 120 request/10 giây |
| Một client | 5 | 40 request/10 giây | 200 request/10 giây |

Các con số trên giả định mọi connection đều nhận cùng grant và chưa có quota ở phạm vi rộng hơn. Trong production, responder nên phân bổ grant theo danh tính và ngân sách tổng để nhiều connection không cộng dồn thành một lỗ hổng quá tải.

### 2.2. Kết nối mới có vòng đời lease mới

Khi client reconnect, nó tạo một RSocket connection mới. Connection mới cần tham gia lại quá trình leasing và nhận grant của chính nó. Không nên coi quyền chưa dùng trên connection cũ là tự động chuyển sang connection mới.

Tương tự, đóng connection làm kết thúc phạm vi của grant gắn với connection đó. Các request đang chạy phải được quản lý theo vòng đời interaction, timeout và cancellation; việc đóng connection không biến lease thành một kho quota có thể chuyển giữa các kết nối.

## 3. TTL và số request cùng giới hạn việc khởi tạo

Một grant có hai điều kiện dừng độc lập:

1. Số request được cấp đã dùng hết.
2. Thời gian TTL đã hết.

Điều kiện nào xảy ra trước sẽ ngăn requester khởi tạo request mới bằng grant đó.

~~~mermaid
flowchart TD
    A["Requester nhận lease"] --> B{"Còn request budget?"}
    B -- Không --> E["Chờ lease mới"]
    B -- Có --> C{"TTL còn hiệu lực?"}
    C -- Không --> E
    C -- Có --> D["Cho phép khởi tạo request"]
    D --> F["Giảm request budget"]
    F --> B
~~~

### 3.1. TTL không phải timeout của request

TTL của lease xác định thời gian requester còn được phép bắt đầu request mới bằng grant đó. Nó không phải thời gian tối đa để một request hoàn tất.

Ví dụ:

- Một request-stream được khởi tạo khi lease còn hiệu lực.
- Sau đó TTL của lease hết.
- Stream đã khởi tạo có thể tiếp tục chạy cho đến khi hoàn tất, bị cancel, timeout hoặc connection bị đóng.
- Requester không được dùng grant đã hết hạn để khởi tạo interaction mới.

Nếu cần giới hạn thời gian xử lý của từng request, hãy dùng timeout hoặc deadline ở tầng ứng dụng. Nếu cần giới hạn số stream đang hoạt động, hãy dùng concurrency/admission limit riêng.

### 3.2. Số request không phải số request đồng thời

Một lease cho phép 40 request trong 10 giây không có nghĩa chỉ có tối đa 40 request đang chạy, cũng không có nghĩa tối đa 4 request mỗi giây.

Requester có thể khởi tạo nhiều request gần nhau trong một burst, rồi dùng hết budget trước khi TTL kết thúc. Một request-stream dài hạn có thể vẫn đang hoạt động sau khi requester đã tiêu thụ hết quyền khởi tạo. Vì vậy, cần thêm giới hạn:

- Số request-response đang xử lý đồng thời.
- Số stream đang hoạt động trên một connection.
- Số channel đang mở.
- Số công việc đang chờ downstream.

Lease kiểm soát tốc độ chấp nhận request theo grant; concurrency limit kiểm soát số công việc cùng tồn tại.

## 4. Leasing khác gì các cơ chế điều tiết khác?

Nhiều cơ chế cùng bảo vệ server nhưng kiểm soát các đại lượng khác nhau:

| Cơ chế | Kiểm soát | Phạm vi thường gặp |
|---|---|---|
| Leasing | Số interaction request được khởi tạo trong TTL | Một RSocket connection |
| Reactive Streams demand / REQUEST_N | Số phần tử stream được phép phát | Một subscription/stream |
| Concurrency limit | Số công việc đang chạy đồng thời | Route, service, tenant hoặc instance |
| Rate limiter | Số request trong một cửa sổ thời gian hoặc tốc độ trung bình | User, tenant, route hoặc service |
| Byte rate limiter | Số byte truyền trong một đơn vị thời gian | Stream, connection, tenant hoặc service |
| Message size limit | Kích thước một payload hoặc frame | Message/connection |
| Circuit breaker | Ngăn gọi tiếp đến dependency đang lỗi | Dependency hoặc route |

### 4.1. Leasing và backpressure

Backpressure điều tiết tốc độ truyền phần tử sau khi một stream đã được tạo. Leasing điều tiết việc tạo interaction mới trước khi request được chấp nhận.

Ví dụ:

- Client đã có một request-stream và đang nhận dữ liệu chậm. REQUEST_N điều chỉnh lượng payload server được phép phát.
- Client muốn mở thêm một request-stream. Lease quyết định connection còn quyền khởi tạo request mới hay không.

Hai cơ chế bổ sung cho nhau. Không dùng leasing để thay thế flow control của stream.

### 4.2. Leasing và rate limiting

Một lease cấp N request trong TTL có thể tạo ra giới hạn số request trong khoảng thời gian đó, nhưng cách cấp grant cho phép burst. Nếu cần giới hạn đều theo thời gian, ví dụ tối đa 5 request mỗi giây với burst tối đa 2, hãy dùng rate limiter có thuật toán và cửa sổ phù hợp.

Leasing thường hữu ích khi responder muốn chủ động cấp hoặc thu hồi năng lực tiếp nhận theo từng connection. Rate limiter thường hữu ích khi cần áp dụng quota nghiệp vụ theo user, tenant hoặc route bất kể số connection.

### 4.3. Leasing và byte quota

Lease đếm request khởi tạo, không đếm byte. Một request-response nhỏ và một request-stream tạo payload lớn đều tiêu thụ quyền khởi tạo theo interaction, dù chi phí tài nguyên rất khác nhau.

Nếu cần bảo vệ băng thông hoặc bộ nhớ, kết hợp lease với max payload size, byte rate limiter và queue có giới hạn theo byte.

## 5. Thiết kế chính sách lease theo connection

Responder nên cấp lease dựa trên khả năng tiếp nhận hiện tại và danh tính đã xác thực của connection. Một chính sách có thể xét:

- CPU và memory pressure của instance.
- Độ dài hàng đợi xử lý.
- Số request và stream đang hoạt động.
- Tình trạng dependency như database hoặc message broker.
- Quota còn lại của user hoặc tenant.
- Loại client và mức dịch vụ đã được cấp.

Không nên cấp một grant cố định lớn cho mọi connection nếu tải hệ thống thay đổi. Một connection mới không nhất thiết có nghĩa service đang đủ tài nguyên để nhận thêm request.

### 5.1. Phân bổ ngân sách từ quota tổng

Một cách thiết kế là phân tầng ngân sách:

1. Global admission controller xác định tổng số request mới mà service có thể nhận trong một khoảng thời gian.
2. Quota manager chia ngân sách cho tenant hoặc user theo chính sách.
3. Lease allocator phân bổ một phần ngân sách tenant cho từng connection đang hoạt động.
4. RSocket responder gửi lease grant tương ứng trên từng connection.

~~~mermaid
flowchart TD
    G["Global capacity / quota"] --> T["Quota theo tenant"]
    T --> U["Quota theo user"]
    U --> C1["Lease allocator: connection A"]
    U --> C2["Lease allocator: connection B"]
    C1 --> L1["LEASE A"]
    C2 --> L2["LEASE B"]
~~~

Việc phân bổ phải bảo đảm tổng grant đang hiệu lực không vượt ngân sách đã dành cho phạm vi cha, hoặc phải chấp nhận rõ ràng mức overcommit được thiết kế. Nếu mỗi connection tự tính grant mà không chia sẻ trạng thái quota, nhiều connection có thể cùng cấp vượt ngân sách tenant.

### 5.2. Cân bằng giữa TTL và request budget

TTL ngắn giúp responder điều chỉnh grant thường xuyên khi tải thay đổi, nhưng tăng tần suất gửi lease và yêu cầu requester cập nhật quyền liên tục. TTL dài giảm overhead quản lý nhưng khiến grant đã cấp khó phản ánh nhanh tình trạng mới.

Request budget lớn cho phép burst cao hơn. Budget nhỏ làm admission chặt hơn nhưng có thể khiến client phải chờ grant thường xuyên.

Hãy chọn TTL và budget dựa trên:

- Độ biến động tải.
- Thời gian phản hồi của client.
- Mức burst mà server có thể chịu.
- Chi phí của một request trung bình và request tốn tài nguyên nhất.
- Độ trễ cập nhật quota giữa các instance.

Một request budget không thay thế đánh giá chi phí. Nếu một route tạo truy vấn rất nặng, có thể cần quota riêng cho route hoặc trọng số chi phí thay vì tính mọi request như nhau.

## 6. Ví dụ Java: tạo lease grant

Trong rsocket-java, lease được biểu diễn bằng đối tượng **Lease** với TTL và số request được phép. Ví dụ tạo một grant:

~~~java
import io.rsocket.lease.Lease;
import java.time.Duration;

Lease grant = Lease.create(
        Duration.ofSeconds(10),
        40
);
~~~

Grant trên cho phép tối đa 40 request trong 10 giây trên connection mà responder gửi grant đó.

### 6.1. Tách quyết định quota khỏi transport

Nên đặt logic tính ngân sách trong một thành phần riêng:

~~~java
public record LeaseBudget(
        Duration ttl,
        int allowedRequests) {
}

public interface LeaseBudgetAllocator {
    Mono<LeaseBudget> allocate(ConnectionIdentity connection);
}
~~~

**ConnectionIdentity** là context nội bộ do ứng dụng tạo sau khi xác thực connection. Allocator có thể hỏi quota manager về ngân sách tenant, kiểm tra tải instance và quyết định số request được cấp cho connection.

Một publisher grant có thể được tạo từ kết quả allocator:

~~~java
Flux<Lease> grantsFor(ConnectionIdentity connection) {
    return leaseBudgetAllocator.allocate(connection)
            .flux()
            .map(budget -> Lease.create(
                    budget.ttl(),
                    budget.allowedRequests()));
}
~~~

Đây là lớp logic minh họa. Cách nối publisher lease vào RSocketServer phụ thuộc phiên bản rsocket-java: hãy cấu hình lease supplier/lease publisher tại server và bảo đảm publisher được gắn với đúng connection. Không dùng một publisher hoặc counter dùng chung nếu mục tiêu là quản lý ngân sách riêng từng connection mà không có cơ chế phân bổ rõ ràng.

### 6.2. Cấp grant dựa trên tải

Ví dụ allocator có thể giảm số request khi hàng đợi tăng:

~~~java
Mono<LeaseBudget> allocate(ConnectionIdentity connection) {
    return loadMonitor.currentSnapshot()
            .flatMap(load -> {
                int base = connectionQuota(connection);

                int allowed;
                if (load.queueDepth() > 5_000
                        || load.cpuPercent() > 90) {
                    allowed = 0;
                } else if (load.queueDepth() > 2_000
                        || load.cpuPercent() > 75) {
                    allowed = Math.max(1, base / 4);
                } else {
                    allowed = base;
                }

                if (allowed == 0) {
                    return Mono.empty();
                }

                return Mono.just(new LeaseBudget(
                        Duration.ofSeconds(5),
                        allowed));
            });
}
~~~

Các ngưỡng trong ví dụ chỉ là giá trị minh họa, cần hiệu chỉnh bằng kiểm thử tải và SLO của hệ thống. Khi allocator không cấp grant mới, requester không có quyền khởi tạo request mới cho đến khi nhận được lease hợp lệ tiếp theo. Ứng dụng nên có cơ chế phục hồi và cấp lease mới khi tải giảm.

### 6.3. Bật leasing ở requester

Requester phải tham gia cơ chế leasing và tuân thủ grant do responder gửi. Với rsocket-java, cấu hình leasing trên RSocketConnector theo API của phiên bản đang dùng. Sau khi leasing được bật, không tự gửi request vượt số quyền còn lại hoặc sau khi TTL hết.

Trình tự cấu hình ở client có dạng:

~~~text
RSocketConnector builder
    -> bật lease handling
    -> kết nối transport
    -> nhận và theo dõi LEASE frame
    -> chỉ khởi tạo request khi còn grant hợp lệ
~~~

Tên method và overload để bật lease handling có thể khác giữa các phiên bản rsocket-java. Hãy kiểm tra API đúng với dependency đang sử dụng; không thay bằng một bộ đếm client tự viết rồi giả định nó đồng bộ với lease của protocol.

## 7. Giới hạn bảo vệ trên từng connection trong Spring RSocket

Spring RSocket cung cấp handler như **@MessageMapping**, nhưng lease là cơ chế của RSocket protocol layer. Việc một handler trả về **Mono** hoặc **Flux** không tự bật leasing. Cần cấu hình RSocket server/connector để trao đổi lease frame ở tầng giao thức.

Trong ứng dụng Spring Boot, có thể tổ chức trách nhiệm như sau:

| Thành phần | Trách nhiệm |
|---|---|
| Authentication/security | Xác minh credential và tạo danh tính connection |
| Connection registry | Theo dõi connection ID, Principal và tenant |
| Global quota manager | Giữ ngân sách tổng theo service, tenant hoặc user |
| Per-connection lease allocator | Chia ngân sách thành TTL và request count cho connection |
| RSocket server lease configuration | Phát LEASE frame trên connection tương ứng |
| Request handler | Xác minh quyền nghiệp vụ và xử lý request |
| Concurrency limiter | Giới hạn số công việc đang chạy |
| Stream flow control | Điều tiết payload trong request-stream/channel |

### 7.1. Không đặt quota toàn tenant chỉ trong handler của một connection

Giả sử một tenant có 10 connection đến cùng service. Nếu mỗi handler hoặc connection tự giữ một counter 100 request, tenant có thể tạo tổng cộng 1.000 request trong cùng phạm vi thời gian.

Quota theo tenant phải nằm trong một thành phần chia sẻ trạng thái giữa các connection, hoặc được phân bổ trước thành các phần không vượt tổng ngân sách. Lease allocator chỉ phát grant trong phần ngân sách mà connection được cấp.

### 7.2. Request-stream dài hạn

Một request-stream tiêu thụ một quyền khởi tạo khi được mở. Sau đó stream có thể phát nhiều payload và tồn tại lâu hơn TTL của lease ban đầu.

Vì vậy, nếu server muốn giới hạn số stream đồng thời, cần một stream registry hoặc concurrency limiter. Ví dụ:

~~~java
return streamConcurrencyLimiter.acquire(principal.getName())
        .flatMapMany(permit ->
                telemetryService.streamFor(principal.getName())
                        .doFinally(signal -> permit.release()));
~~~

Đây là mã minh họa cho admission permit ở tầng ứng dụng. Permit phải được giải phóng khi stream hoàn tất, lỗi hoặc bị cancel. Không dùng request budget của lease như số lượng stream đang mở.

## 8. Xử lý khi hết lease hoặc lease hết hạn

Requester có thể gặp các tình huống:

- Chưa nhận lease đầu tiên.
- Đã dùng hết allowed requests.
- TTL của grant hiện tại đã hết.
- Connection bị ngắt trước khi nhận grant tiếp theo.
- Responder tạm thời không cấp grant mới do quá tải.

Ứng dụng cần xác định hành vi phù hợp:

1. Không khởi tạo request mới khi không có quyền lease hợp lệ.
2. Chờ grant mới hoặc báo trạng thái tạm thời cho tầng gọi.
3. Dùng timeout cho thời gian chờ lease để caller không đợi vô hạn.
4. Áp dụng retry có backoff và jitter khi nghiệp vụ cho phép.
5. Không tạo vòng lặp reconnect liên tục chỉ để lấy lease mới.

Việc hết lease không tự động có nghĩa request đang chạy bị hủy. Các interaction đã được khởi tạo vẫn cần timeout, cancellation và quản lý tài nguyên riêng.

### 8.1. Retry và idempotency

Nếu client không thể gửi request vì hết lease, request chưa được khởi tạo trên connection đó. Khi nhận grant mới, client có thể thử lại theo chính sách.

Nếu connection mất sau khi request đã được gửi, client có thể không biết server đã xử lý hay chưa. Đây là tình huống retry có nguy cơ lặp thao tác. Với lệnh tạo dữ liệu hoặc thanh toán, hãy dùng idempotency key và xử lý deduplication ở server.

Không retry liên tục ngay khi nhận tín hiệu hết lease. Backoff giúp tránh tạo thêm áp lực vào thời điểm server đang giảm admission.

## 9. Các lỗi thiết kế thường gặp

### Nghĩ lease là quota toàn user

Lease chỉ bảo vệ connection được cấp grant. Một user mở nhiều connection có thể có nhiều grant. Hãy phối hợp với quota theo danh tính.

### Coi allowed requests là số request đồng thời

Đây là số request được khởi tạo trong grant, không phải giới hạn số request đang chạy. Dùng concurrency limiter riêng.

### Coi TTL là timeout của stream

TTL hết chỉ ngăn request mới dùng grant cũ. Stream đã mở cần timeout và cancellation riêng.

### Dùng lease thay cho REQUEST_N

Lease không điều tiết số payload trong stream. Dùng Reactive Streams demand và RSocket flow control.

### Dùng lease thay cho byte quota

Một request có thể truyền ít hoặc rất nhiều byte. Đặt max message size và byte rate limiter nếu cần bảo vệ băng thông.

### Cấp cùng grant lớn cho mọi connection

Nhiều connection sẽ cộng dồn ngân sách và có thể vượt năng lực service. Cấp grant từ global/tenant quota manager.

### Không gắn grant với danh tính đã xác thực

Nếu quota theo tenant hoặc user, server cần xác thực connection trước và ánh xạ Principal vào quota policy. Không tin tenant ID do client tự khai.

### Không giám sát lease grant và request bị từ chối

Nếu không đo số grant, số quyền còn lại, số request bị chặn và tải tại thời điểm cấp, khó biết leasing đang bảo vệ service hay làm giảm throughput không cần thiết.

## 10. Quan sát và kiểm thử leasing

Nên thu thập metric theo connection và theo phạm vi quota rộng hơn:

| Metric | Ý nghĩa |
|---|---|
| Active RSocket connections | Số connection đang hoạt động |
| Lease grants issued | Số grant đã cấp |
| Allowed requests per grant | Ngân sách request của từng grant |
| Lease TTL | Thời gian hiệu lực grant |
| Lease budget remaining | Số quyền còn lại nếu thư viện cung cấp |
| Requests admitted | Số request được khởi tạo thành công |
| Requests blocked by lease | Số request bị chặn hoặc phải chờ do lease |
| Active streams/channels | Số interaction dài hạn đang mở |
| Per-tenant aggregate grants | Tổng grant đã phân bổ cho tenant |
| Queue depth and CPU | Tín hiệu tải dùng để quyết định grant |

Không gắn connection ID hoặc user ID có độ phân biệt cao làm label metric không giới hạn vì có thể tạo cardinality lớn. Dùng log có kiểm soát hoặc trace để điều tra từng connection.

### 10.1. Các kịch bản kiểm thử

1. Kết nối requester có bật leasing và xác minh responder gửi grant.
2. Gửi request đến khi dùng hết allowed requests; xác minh request mới phải chờ grant mới.
3. Để TTL hết khi vẫn còn request budget; xác minh grant cũ không được dùng để khởi tạo request mới.
4. Mở nhiều request-stream trên một connection; xác minh chúng dùng chung request budget của connection.
5. Mở nhiều connection cho cùng một Principal; xác minh global/tenant quota không bị nhân lên ngoài chính sách.
6. Giữ một stream đang hoạt động qua thời điểm TTL hết; xác minh lease expiry không bị nhầm thành timeout stream.
7. Đóng connection và reconnect; xác minh connection mới nhận grant theo chính sách mới.
8. Tạm dừng cấp grant khi service quá tải; xác minh requester chờ hoặc báo lỗi có kiểm soát.
9. Kiểm tra retry của thao tác có side effect với idempotency key.

## 11. Checklist triển khai

Trước khi bật leasing trong production, hãy xác nhận:

1. Cả requester và responder đều hỗ trợ leasing và thương lượng đúng trong SETUP.
2. Lease grant được gửi trên đúng RSocket connection.
3. TTL và allowed requests được chọn theo năng lực thực tế.
4. Các request type khởi tạo đều tuân thủ lease.
5. Nhiều route multiplex trên cùng connection cùng chịu ngân sách lease của connection.
6. Nhiều connection được điều tiết bằng quota theo user/tenant/service khi cần.
7. Có concurrency limit cho request đang chạy và stream dài hạn.
8. Có flow control riêng cho payload của request-stream và request-channel.
9. Có max message size và byte quota nếu cần bảo vệ bộ nhớ/băng thông.
10. Lease expiry không bị dùng nhầm làm request timeout.
11. Retry có backoff và idempotency khi thao tác có side effect.
12. Có metric cho grant, request bị chặn, connection và tải hệ thống.

## 12. Tổng kết

Leasing cho phép responder cấp số request được khởi tạo trong một TTL cho requester trên một RSocket connection. Các interaction request-response, fire-and-forget, request-stream và request-channel tiêu thụ quyền khi được khởi tạo; các payload tiếp theo của stream và REQUEST_N không phải request khởi tạo mới.

Phạm vi connection là giới hạn cốt lõi của leasing. Nhiều connection của cùng user hoặc tenant có thể nhận nhiều grant, nên quota rộng hơn phải được quản lý bởi thành phần dùng chung và phân bổ xuống từng connection. Kết hợp leasing với concurrency limit, Reactive Streams demand, byte quota, timeout và observability sẽ bảo vệ cả khả năng tiếp nhận request lẫn tài nguyên xử lý thực tế của hệ thống.
