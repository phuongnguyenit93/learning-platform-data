# Lỗi phụ thuộc ngoài

Application event thường kích hoạt công việc cần gọi tới một hệ thống nằm ngoài module hoặc ngoài ứng dụng: dịch vụ tồn kho, cổng thanh toán, hệ thống vận chuyển, API đối tác hay một dịch vụ nội bộ khác. Những hệ thống này có thể chậm, tạm ngừng, giới hạn lưu lượng hoặc trả về lỗi dữ liệu. Khi listener xử lý event gặp lỗi từ dependency ngoài, ứng dụng cần quyết định có thử lại, trì hoãn, chuyển sang quy trình phục hồi hay yêu cầu can thiệp vận hành.

Trong Spring Modulith, lỗi ở listener xảy ra sau khi transaction nghiệp vụ phát event đã commit. Vì vậy, lỗi gọi dịch vụ ngoài thường không thể rollback thay đổi ban đầu. Muốn giao sự kiện đáng tin cậy, cần kết hợp phân loại lỗi, timeout, retry có giới hạn, idempotency, khả năng cô lập dependency và theo dõi publication chưa hoàn tất.

## 1. Lỗi phụ thuộc ngoài là gì?

Lỗi phụ thuộc ngoài là lỗi phát sinh khi listener gọi một thành phần mà nó không kiểm soát trực tiếp. Ví dụ, Orders đã xác nhận đơn hàng và phát `OrderConfirmed`; listener Fulfillment gọi API của hãng vận chuyển để tạo yêu cầu giao hàng. API có thể timeout, trả HTTP 503 hoặc từ chối dữ liệu.

~~~mermaid
sequenceDiagram
    participant O as Orders
    participant DB as Orders DB
    participant R as Event Publication Registry
    participant L as Event listener
    participant X as External service
    O->>DB: Commit đơn hàng
    O->>R: Đăng ký publication
    R->>L: Giao OrderConfirmed
    L->>X: Gọi API tạo yêu cầu giao
    X-->>L: Timeout / 503
    L-->>R: Báo lỗi xử lý
    Note over R,L: Publication chưa hoàn tất
~~~

Dependency ngoài có thể lỗi dù code listener không thay đổi. Do đó, handler phải được thiết kế cho tình huống dependency chậm hoặc không sẵn sàng, thay vì giả định mọi lời gọi mạng đều thành công.

## 2. Phân loại lỗi trước khi retry

Không nên retry mọi exception giống nhau. Trước tiên hãy xác định lỗi có khả năng tự phục hồi hay không:

| Nhóm lỗi | Ví dụ | Hướng xử lý thường dùng |
| --- | --- | --- |
| Lỗi mạng tạm thời | Connection reset, DNS tạm thời không phân giải được, connect timeout | Retry có backoff và giới hạn số lần |
| Dependency quá tải | HTTP 429, 503, 502 hoặc 504 | Giảm tốc độ, tôn trọng `Retry-After`, retry có giới hạn |
| Lỗi dữ liệu/hợp đồng | HTTP 400, payload thiếu trường bắt buộc, schema không tương thích | Không retry nguyên trạng; sửa dữ liệu hoặc hợp đồng |
| Lỗi xác thực/phân quyền | HTTP 401 hoặc 403, credential hết hạn, ACL sai | Cảnh báo và sửa cấu hình; retry sau khi nguyên nhân được khắc phục |
| Từ chối nghiệp vụ | Không đủ tồn kho, đơn hàng không hợp lệ, trạng thái không cho phép | Áp dụng quy tắc nghiệp vụ hoặc chuyển quy trình xử lý; không retry vô hạn |
| Kết quả không xác định | Request timeout sau khi server có thể đã thực hiện side effect | Tra cứu trạng thái hoặc gửi lại bằng idempotency key ổn định |

Điểm khó là timeout không luôn có nghĩa thao tác thất bại. Server có thể đã tạo yêu cầu giao hàng nhưng phản hồi bị mất trên đường về. Nếu client gửi lại một request tạo mới mà không có idempotency, hệ thống có thể tạo hai yêu cầu giao hàng.

## 3. Đặt timeout cho mọi lời gọi mạng

Timeout giới hạn thời gian listener chờ dependency. Nếu không đặt timeout, một request có thể giữ thread, connection và tài nguyên giao dịch quá lâu khi hệ thống đích bị treo.

Nên xác định riêng:

- **Connect timeout:** thời gian tối đa để thiết lập kết nối.
- **Response/read timeout:** thời gian tối đa chờ dữ liệu phản hồi.
- **Call/deadline timeout:** giới hạn tổng thời gian cho toàn bộ lời gọi, gồm cả các lần retry nếu có.

Timeout phải phù hợp với SLA của dependency và ngân sách thời gian của listener. Nếu mỗi lần gọi chờ 30 giây, retry 5 lần, một event có thể chiếm worker trong nhiều phút. Hãy tính tổng thời gian tối đa, bao gồm backoff, và bảo đảm nó phù hợp với thread pool, thời gian xử lý và chính sách phục hồi.

Ví dụ, với HTTP client, cấu hình timeout nên được tập trung ở bean dùng chung thay vì để từng listener tự đặt một giá trị khác nhau. Giá trị cụ thể phụ thuộc client như `RestClient`, `WebClient` hoặc HTTP client đang được ứng dụng sử dụng.

## 4. Retry có giới hạn và backoff

Retry phù hợp khi lỗi có khả năng biến mất sau một khoảng thời gian ngắn. Dùng số lần thử hữu hạn và khoảng chờ tăng dần để tránh gửi liên tục vào dependency đang quá tải.

Ví dụ, một lời gọi có thể thử tối đa bốn lần, bắt đầu sau 500 ms, tăng theo hệ số 2 và không vượt quá 5 giây. Các giá trị chỉ mang tính minh họa; hãy điều chỉnh theo SLA, giới hạn API và thời gian phục hồi thực tế.

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;

import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
class ShippingGateway {

    private final ShippingClient client;

    ShippingGateway(ShippingClient client) {
        this.client = client;
    }

    @Retryable(
            retryFor = {
                    ConnectException.class,
                    SocketTimeoutException.class
            },
            maxAttempts = 4,
            backoff = @Backoff(
                    delay = 500,
                    multiplier = 2.0,
                    maxDelay = 5_000))
    public ShippingResult createShipment(
            CreateShipmentRequest request, String idempotencyKey) {
        return client.createShipment(request, idempotencyKey);
    }
}
~~~

Đây là ví dụ minh họa với Spring Retry; ứng dụng cần dependency và cấu hình retry phù hợp, chẳng hạn bật retry annotation processing bằng `@EnableRetry`. Phương thức cần được gọi qua Spring proxy; self-invocation trong cùng bean có thể bỏ qua interceptor. Hãy kiểm tra các loại exception thực tế do HTTP client ném ra và chỉ đưa lỗi có thể retry vào danh sách.

Không retry lỗi validation hoặc lỗi nghiệp vụ cố định. Với HTTP 429 hoặc 503, nếu dependency trả `Retry-After`, hãy cân nhắc tôn trọng thời gian đó. Trong môi trường có nhiều worker, thêm jitter vào backoff để tránh tất cả worker cùng retry tại một thời điểm.

## 5. Tránh retry chồng nhiều tầng

Spring Modulith Event Publication Registry có thể theo dõi listener chưa hoàn tất và hỗ trợ phục hồi publication theo cấu hình. Spring Retry hoặc Resilience4j có thể thử lại một lời gọi dependency bên trong listener. Đây là hai tầng khác nhau:

| Tầng | Phạm vi retry | Ví dụ lỗi |
| --- | --- | --- |
| Retry lời gọi dependency | Một thao tác HTTP hoặc RPC trong lần xử lý listener hiện tại | Timeout, 503, connection reset |
| Phục hồi publication | Giao lại application event cho listener khi publication chưa hoàn tất | Listener kết thúc bằng exception hoặc tiến trình dừng khi đang xử lý |
| Retry message broker | Consumer bên ngoài đã nhận message nhưng xử lý thất bại | Consumer Kafka lỗi khi ghi read model |

Nếu listener thử lại một lời gọi bốn lần, sau đó publication được giao lại ba lần, dependency có thể nhận tới mười hai request cho cùng một event. Cần tính tổng retry budget xuyên suốt các tầng, đặt giới hạn thời gian và ghi nhận attempt để tránh retry nhân lên ngoài dự kiến.

Không bắt exception cuối cùng rồi trả về bình thường chỉ để registry đánh dấu publication hoàn tất. Nếu công việc nghiệp vụ chưa thành công, hãy để lỗi được truyền ra hoặc ghi nhận một trạng thái pending/deferred rõ ràng theo thiết kế. Ngược lại, nếu listener đã chuyển trách nhiệm sang một hàng đợi bền vững và việc enqueue đã commit thành công, publication có thể hoàn tất vì chặng bàn giao đã thành công; consumer xử lý hàng đợi sẽ có vòng đời retry riêng.

## 6. Idempotency khi dependency có thể đã thực hiện side effect

Đối với thao tác tạo hoặc thay đổi dữ liệu ở hệ thống ngoài, retry phải dùng một idempotency key ổn định. Có thể dùng `eventId` hoặc một ID nghiệp vụ được tạo trước và giữ nguyên qua mọi lần thử.

~~~java
import org.springframework.modulith.events.ApplicationModuleListener;

@ApplicationModuleListener
void on(OrderConfirmed event) {
    var request = new CreateShipmentRequest(
            event.orderId(),
            event.deliveryAddress());

    shippingGateway.createShipment(
            request,
            event.eventId().toString());
}
~~~

Ví dụ này giả định API vận chuyển hỗ trợ idempotency key và trả lại cùng kết quả cho những request trùng khóa. Nếu API ngoài không hỗ trợ, ứng dụng cần một cơ chế khác như tra cứu theo external reference, đối soát trước khi gửi lại hoặc quy trình xử lý thủ công khi kết quả không xác định.

Chỉ lưu `eventId` đã xử lý trong database của ứng dụng không đủ để ngăn side effect trùng ở hệ thống ngoài nếu server đã thực hiện thao tác nhưng client mất response. Khóa chống trùng phải được hệ thống đích hiểu hoặc phải có cách xác minh trạng thái thao tác từ xa.

## 7. Circuit breaker, bulkhead và rate limit

Retry hữu hạn vẫn có thể làm dependency quá tải hơn nếu tất cả listener cùng gửi request. Các cơ chế bảo vệ bổ sung giúp giới hạn tác động:

- **Circuit breaker:** khi tỷ lệ lỗi vượt ngưỡng, ngắt lời gọi trong một khoảng thời gian. Sau đó chuyển sang half-open để thử một số request trước khi đóng mạch lại.
- **Bulkhead:** giới hạn số request đồng thời tới một dependency để lỗi ở dependency đó không chiếm hết worker của ứng dụng.
- **Rate limiter:** giới hạn tốc độ request theo quota của dịch vụ ngoài.
- **Concurrency limit:** kiểm soát số listener hoặc worker xử lý song song.

Circuit breaker không thay thế retry. Khi mạch đang mở, request thường bị từ chối nhanh; retry liên tục trong trạng thái này chỉ tiêu tốn tài nguyên. Hãy phối hợp chính sách: retry lỗi tạm thời trong giới hạn, circuit breaker ngăn gọi khi dependency suy giảm kéo dài, và hàng đợi bền vững giữ công việc để xử lý sau.

Fallback chỉ nên dùng khi nghiệp vụ định nghĩa rõ kết quả thay thế. Ví dụ, có thể ghi trạng thái `SHIPMENT_PENDING` và để worker xử lý sau. Không nên giả vờ tạo vận đơn thành công hoặc đánh dấu event đã hoàn tất nếu hệ thống ngoài chưa xác nhận.

## 8. Giữ transaction ngắn và tách công việc dài

`@ApplicationModuleListener` xử lý event sau khi transaction phát event commit và listener có transaction riêng theo cấu hình Spring Modulith. Nếu listener gọi API chậm trong lúc transaction đang mở, transaction và connection database có thể bị giữ lâu hơn cần thiết.

Với dependency nhanh và timeout ngắn, lời gọi trực tiếp có thể đủ. Với dependency chậm hoặc không ổn định, cân nhắc tách thành hai bước:

1. Listener ghi một yêu cầu tích hợp bền vững vào database, có event ID và trạng thái PENDING, rồi commit.
2. Worker riêng lấy yêu cầu, gọi dependency ngoài với timeout, retry, idempotency và circuit breaker; sau đó ghi kết quả vào một transaction ngắn.

~~~mermaid
flowchart TD
    A[Application event] --> B[Listener ghi integration task]
    B --> C[(Task table / outbox)]
    C --> D[Worker lấy task]
    D --> E[Call external dependency]
    E -->|Thành công| F[Đánh dấu COMPLETED]
    E -->|Lỗi tạm thời| G[Đặt next_attempt_at]
    G --> D
    E -->|Lỗi không thể retry| H[Quarantine / cần xử lý]
~~~

Trong mô hình này, publication của application event hoàn tất khi task đã được ghi bền vững. Việc gọi dịch vụ ngoài có trạng thái, retry và quan sát riêng. Nếu dùng outbox, cần bảo đảm việc ghi task và thay đổi dữ liệu nghiệp vụ nằm trong cùng transaction thích hợp; worker phải có khóa hoặc cơ chế claim để tránh nhiều instance xử lý cùng task ngoài ý muốn.

Không cần tách mọi lời gọi thành worker riêng. Hãy chọn dựa trên thời gian phản hồi, SLA, mức độ quan trọng và khả năng chịu lỗi của dependency.

## 9. Xử lý lỗi cuối cùng và quarantine

Khi đã hết retry mà dependency vẫn lỗi, không nên để event biến mất hoặc retry vô hạn. Cần quyết định trạng thái nghiệp vụ tiếp theo:

- **Pending:** công việc vẫn cần hoàn thành và sẽ được thử lại sau một khoảng thời gian dài hơn.
- **Quarantined:** message hoặc task được cô lập để điều tra vì dữ liệu hoặc hợp đồng không hợp lệ.
- **Rejected:** nghiệp vụ từ chối rõ ràng và cần thông báo tới module sở hữu quy trình.
- **Compensation required:** một bước trước đó đã hoàn thành và cần hành động bù trừ.

Quarantine record nên giữ event ID, event type, dependency, request reference, số lần thử, thời điểm lỗi cuối, loại exception và correlation ID. Chỉ lưu payload khi thực sự cần, có kiểm soát quyền truy cập và che dữ liệu nhạy cảm.

Quy trình phục hồi cần xác định ai xử lý, cách sửa nguyên nhân, cách replay và cách tránh side effect trùng. Không tự động replay toàn bộ quarantine khi dependency vừa hoạt động lại; lỗi dữ liệu hoặc lỗi nghiệp vụ có thể vẫn còn nguyên.

## 10. Phối hợp với Event Publication Registry

Event Publication Registry theo dõi publication tới listener. Khi listener hoàn tất thành công, publication được đánh dấu hoàn tất; nếu listener ném lỗi, publication có thể còn chưa hoàn tất để được phát hiện và phục hồi theo cấu hình.

Để phục hồi sau khi ứng dụng dừng, cần cấu hình persistence bền vững cho registry. Theo dõi publication chưa hoàn tất và tuổi của publication lâu nhất. Cần có quy trình retry hoặc resubmit publication phù hợp với phiên bản Spring Modulith và chính sách vận hành của ứng dụng.

Registry ghi nhận listener đã hoàn tất, không tự chứng minh một hệ thống ngoài đã hoàn tất nghiệp vụ. Nếu listener chỉ enqueue công việc, sự kiện hoàn tất có nghĩa task đã được bàn giao bền vững. Nếu listener gọi API trực tiếp, chỉ đánh dấu hoàn tất sau khi kết quả được xác nhận theo hợp đồng của dependency.

Registry cũng không phải kho lưu lịch sử nghiệp vụ vô thời hạn. Publication hoàn tất có thể được dọn theo retention. Nếu cần audit hoặc đối soát lâu dài, lưu kết quả tích hợp và dấu vết nghiệp vụ trong mô hình riêng.

## 11. Ví dụ thiết kế listener và gateway

Listener nên điều phối công việc; gateway chịu trách nhiệm giao tiếp với dependency và ánh xạ lỗi kỹ thuật thành loại lỗi mà ứng dụng hiểu:

~~~java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Component
class ShipmentRequestedListener {

    private final ShipmentApplicationService shipments;

    ShipmentRequestedListener(ShipmentApplicationService shipments) {
        this.shipments = shipments;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        shipments.requestShipment(event);
    }
}

@Service
class ShipmentApplicationService {

    private final ShippingGateway gateway;

    ShipmentApplicationService(ShippingGateway gateway) {
        this.gateway = gateway;
    }

    public void requestShipment(OrderConfirmed event) {
        var request = CreateShipmentRequest.from(event);
        gateway.createShipment(request, event.eventId().toString());
    }
}
~~~

Ví dụ tách trách nhiệm để dễ kiểm thử. Trong triển khai thật, cần bảo đảm các exception sau retry vẫn được truyền lên listener nếu công việc chưa hoàn thành. Nếu ứng dụng chuyển sang mô hình task bền vững, service sẽ tạo task và worker thực hiện lời gọi mạng ở bước riêng.

## 12. Kiểm thử lỗi dependency

Kiểm thử cần bao phủ cả phản hồi bình thường và các tình huống lỗi:

1. Dependency trả thành công; listener hoàn tất và publication được đánh dấu hoàn tất.
2. Dependency timeout hoặc trả 503; số lần retry và backoff tuân theo cấu hình.
3. Dependency trả lỗi 400 hoặc 403; listener không retry vô ích.
4. Dependency thực hiện side effect nhưng response bị mất; retry cùng idempotency key không tạo bản ghi trùng.
5. Circuit breaker mở; request mới bị chặn nhanh và không làm cạn worker.
6. Hết retry; publication vẫn có thể được phục hồi hoặc task được đưa vào quarantine theo chính sách.
7. Ứng dụng dừng giữa quá trình xử lý; sau restart, registry hoặc task store cho phép tiếp tục.
8. Dependency hoạt động trở lại; công việc pending được xử lý và projection/trạng thái nghiệp vụ hội tụ.

Dùng HTTP mock server hoặc fake gateway để mô phỏng timeout, status code và response chậm. Kiểm tra số request, idempotency key và trạng thái cuối cùng; tránh dùng `Thread.sleep` cố định để chờ retry nếu có thể đồng bộ bằng điều kiện và timeout.

## 13. Quan sát và vận hành

Theo dõi theo từng dependency và từng loại event:

| Chỉ số | Mục đích |
| --- | --- |
| Request latency p50/p95/p99 | Nhận biết dependency chậm |
| Timeout và error rate | Phân biệt lỗi mạng, lỗi server và lỗi nghiệp vụ |
| Retry attempts | Biết retry có đang tăng bất thường hay không |
| Circuit breaker state | Biết dependency đang đóng, mở hay half-open |
| Pending publication count/age | Phát hiện listener chưa hoàn tất trong registry |
| Pending task age | Theo dõi công việc đã bàn giao nhưng chưa xử lý xong |
| Quarantine/DLT count | Theo dõi message cần điều tra |

Log nên có `eventId`, `eventType`, `correlationId`, tên dependency, attempt, timeout, HTTP status hoặc exception class và thời điểm xử lý. Không ghi token, credential hay toàn bộ payload nhạy cảm.

Runbook khi dependency lỗi nên trả lời: dependency nào đang suy giảm, circuit breaker đang ở trạng thái nào, backlog có tăng không, lỗi nào được retry, lỗi nào cần xử lý thủ công, và cách replay an toàn sau khi phục hồi. Khi dependency đã hoạt động lại, tăng tải xử lý từ từ để tránh tạo đợt request dồn.

## 14. Những sai lầm cần tránh

- Không đặt timeout cho HTTP/RPC call.
- Retry lỗi validation, xác thực hoặc lỗi nghiệp vụ cố định.
- Retry vô hạn hoặc dùng backoff quá ngắn khi dependency đang quá tải.
- Không dùng idempotency key khi request có thể đã tạo side effect nhưng response bị mất.
- Bắt exception rồi trả về bình thường dù công việc chưa hoàn thành.
- Để retry của gateway, listener và broker nhân lên mà không có retry budget tổng.
- Giữ transaction hoặc database connection trong lúc chờ một lời gọi mạng dài.
- Coi publication hoàn tất là bằng chứng hệ thống ngoài đã hoàn thành nghiệp vụ.
- Xóa publication pending hoặc quarantine để làm sạch dashboard mà chưa xử lý nguyên nhân.

## Kết luận

Lỗi phụ thuộc ngoài là tình huống bình thường trong hệ thống bất đồng bộ. Với Spring Modulith, hãy phân loại lỗi trước khi retry, đặt timeout và retry budget rõ ràng, dùng idempotency key cho side effect từ xa, bảo vệ dependency bằng circuit breaker/bulkhead và tách công việc dài thành task bền vững khi cần. Event Publication Registry giúp theo dõi listener chưa hoàn tất; trạng thái xử lý ở hệ thống ngoài cần được quản lý và quan sát riêng. Cách tổ chức này giúp event không bị mất dấu, tránh side effect trùng và cho phép phục hồi có kiểm soát khi dependency gặp sự cố.
