# Triển khai cuốn chiếu và tương thích giữa hai phiên bản ứng dụng

Triển khai cuốn chiếu (rolling deployment) thay từng nhóm instance của phiên bản cũ bằng instance phiên bản mới trong khi hệ thống vẫn nhận traffic. Trong một khoảng thời gian, nhiều client và server khác phiên bản cùng hoạt động. Với RSocket, điều này cần được tính đến ở cả hợp đồng payload, route, metadata, connection dài hạn và dữ liệu lưu trong database.

Một bản phát hành an toàn phải bảo đảm các phiên bản có thể giao tiếp trong suốt giai đoạn chuyển tiếp. Server mới thường cần tiếp tục phục vụ client cũ; client mới cần có khả năng gọi server cũ cho tới khi toàn bộ fleet đã được nâng cấp. Chỉ sau khi không còn thành phần cũ sử dụng hợp đồng cũ, nhóm phát triển mới nên loại bỏ route, field hoặc cấu trúc dữ liệu cũ.

## 1. Vì sao rolling deployment tạo ra bài toán tương thích?

Giả sử hệ thống Order có client C1 và server S1. Bản phát hành mới thêm trường deliveryWindow vào yêu cầu tạo đơn hàng và thay đổi cách tính trạng thái:

- C1 gửi payload theo schema cũ.
- C2 gửi payload theo schema mới.
- S1 chỉ hiểu schema cũ.
- S2 hiểu schema mới và vẫn hỗ trợ schema cũ trong giai đoạn chuyển tiếp.

Trong khi rollout diễn ra, có thể tồn tại đồng thời C1, C2, S1 và S2. Một request có thể đi từ C2 tới S1 nếu load balancer chọn instance cũ. Một event do S2 phát ra có thể tới consumer C1 chưa được nâng cấp.

Với RSocket, load balancer thường chọn backend khi thiết lập transport connection. Các interaction sau đó trên cùng connection tiếp tục tới instance đã nhận connection. Vì vậy, C2 có thể mở một connection mới tới S1 trong lúc rollout, hoặc có thể giữ connection tới S1 đã mở từ trước; không nên hình dung load balancer chọn Pod lại cho từng route trên cùng socket.

| Thành phần gửi | Thành phần nhận | Điều cần bảo đảm |
| --- | --- | --- |
| Client cũ | Server cũ | Hành vi hiện tại tiếp tục hoạt động. |
| Client cũ | Server mới | Server mới vẫn đọc route và payload cũ. |
| Client mới | Server cũ | Client mới còn dùng hợp đồng cũ hoặc biết fallback. |
| Client mới | Server mới | Có thể dùng hợp đồng mới sau khi xác nhận capability. |
| Producer cũ | Consumer mới | Consumer mới tiếp tục đọc event cũ. |
| Producer mới | Consumer cũ | Producer chưa phát schema mới cho tới khi consumer cũ không còn nhận traffic, hoặc payload vẫn tương thích. |

Không thể giả định mọi instance được nâng cấp cùng một thời điểm. Kubernetes tạo Pod mới, đợi readiness rồi mới giảm Pod cũ; trong giai đoạn đó cả hai phiên bản có thể nhận kết nối.

## 2. Phân biệt phiên bản RSocket protocol và phiên bản API ứng dụng

RSocket có version major/minor ở tầng protocol. Client truyền phiên bản protocol mà nó hỗ trợ trong SETUP; server quyết định có chấp nhận phiên bản client hay không. Theo protocol specification hiện tại, thay đổi major hoặc minor của RSocket protocol được coi là không tương thích ngược. Cơ chế này độc lập với phiên bản Java library, phiên bản Spring Boot và phiên bản API nghiệp vụ.

Ở tầng ứng dụng, các thành phần sau do hệ thống tự định nghĩa:

- Route, ví dụ orders.v1.create và orders.v2.create.
- Schema của data payload, ví dụ CreateOrderV1 và CreateOrderV2.
- Schema của metadata, ví dụ authentication, tenant context hoặc capability.
- Event type và event schema version.
- Quy tắc nghiệp vụ, quyền truy cập và ý nghĩa của từng field.

Không dùng việc nâng version thư viện RSocket để thay thế cho versioning của payload nghiệp vụ. Một ứng dụng có thể giữ nguyên wire protocol RSocket nhưng thay đổi route hoặc DTO qua nhiều lần phát hành.

### MIME type trong SETUP có phạm vi connection

SETUP khai báo data MIME type và metadata MIME type cho connection. Các MIME type này áp dụng cho các request trên connection đó. Vì vậy, không nên giả định có thể thay data MIME type tùy ý cho từng request để giải quyết tương thích trong một connection dùng chung.

Với ứng dụng cần nhiều schema trong cùng connection, có thể:

- Giữ MIME type ổn định, chẳng hạn JSON, rồi đưa schema version vào route hoặc envelope của payload.
- Dùng metadata entry có MIME type riêng cho một extension đã được hai phía thống nhất.
- Mở connection riêng nếu hai nhóm client/server thực sự cần hợp đồng encoding khác nhau.

Composite Metadata cho phép route và các metadata entry cùng tồn tại. Tuy nhiên, nó không tự version hóa DTO hoặc kiểm tra rằng responder hiểu schema của data.

## 3. Nguyên tắc tương thích ngược và tương thích xuôi

Một thay đổi tương thích ngược cho phép phiên bản server mới tiếp tục phục vụ client cũ. Một thay đổi tương thích xuôi cho phép client mới giao tiếp với server cũ trong phạm vi hợp đồng mà server cũ hiểu.

Các thay đổi payload thường an toàn hơn khi:

- Thêm field optional có default rõ ràng.
- Giữ nguyên tên, kiểu và ý nghĩa của field đang dùng.
- Consumer bỏ qua field chưa biết nếu serializer được cấu hình cho phép.
- Producer chỉ gửi field mới khi đã biết consumer hỗ trợ.
- Giữ nguyên route cũ trong suốt thời gian chuyển đổi.

Các thay đổi có nguy cơ phá vỡ tương thích:

- Xóa hoặc đổi tên field đang được consumer sử dụng.
- Đổi kiểu dữ liệu, ví dụ số thành chuỗi.
- Thay đổi ý nghĩa của field mà không đổi schema version.
- Đổi field optional thành bắt buộc.
- Thêm enum value nhưng consumer cũ xử lý enum theo kiểu exhaustive và lỗi khi gặp giá trị lạ.
- Thay đổi thứ tự hoặc semantics của stream.
- Xóa route cũ ngay khi server mới được triển khai.

Ví dụ: thêm deliveryWindow dưới dạng optional thường ít rủi ro hơn việc đổi deliveryDate từ ngày giao dự kiến thành ngày giao thực tế. Thay đổi ý nghĩa của field là breaking change ngay cả khi kiểu Java không đổi.

## 4. Version hóa route và payload RSocket

Route là metadata theo từng request, do đó có thể dùng route version để giữ nhiều hợp đồng song song:

~~~java
public record CreateOrderV1(
    UUID customerId,
    List<OrderLine> lines
) {}

public record CreateOrderV2(
    UUID customerId,
    List<OrderLine> lines,
    String deliveryWindow,
    String salesChannel
) {}

public record OrderViewV1(UUID orderId, String status) {}

public record OrderViewV2(
    UUID orderId,
    String status,
    String deliveryWindow
) {}
~~~

Server giữ cả hai handler:

~~~java
@Controller
public class OrderRSocketController {

    private final OrderApplicationService orders;

    public OrderRSocketController(OrderApplicationService orders) {
        this.orders = orders;
    }

    @MessageMapping("orders.v1.create")
    Mono<OrderViewV1> createV1(CreateOrderV1 request) {
        return orders.create(
            request.customerId(),
            request.lines(),
            null,
            "legacy"
        ).map(order -> new OrderViewV1(
            order.id(),
            order.status()
        ));
    }

    @MessageMapping("orders.v2.create")
    Mono<OrderViewV2> createV2(CreateOrderV2 request) {
        return orders.create(
            request.customerId(),
            request.lines(),
            request.deliveryWindow(),
            request.salesChannel()
        ).map(order -> new OrderViewV2(
            order.id(),
            order.status(),
            order.deliveryWindow()
        ));
    }
}
~~~

Hai handler gọi cùng application service và dùng chung mô hình domain nội bộ. Route version chỉ biểu diễn hợp đồng ở ranh giới mạng; không nhất thiết phải tạo hai bộ logic nghiệp vụ độc lập.

Ở client:

~~~java
Mono<OrderViewV1> createOrderV1(
        RSocketRequester requester,
        CreateOrderV1 command) {

    return requester
        .route("orders.v1.create")
        .data(command)
        .retrieveMono(OrderViewV1.class);
}
~~~

Khi phát hành V2, client mới có thể gọi route V2 sau khi xác nhận server hỗ trợ. Giữ route V1 trong S2 để C1 tiếp tục hoạt động trong thời gian rollout và trong cửa sổ rollback.

### Dùng schema version trong envelope

Nếu nhiều event dùng chung một route, có thể đặt version trong envelope:

~~~java
public record EventEnvelope(
    UUID eventId,
    String eventType,
    int schemaVersion,
    JsonNode payload
) {}
~~~

Consumer kiểm tra schemaVersion và chọn decoder/handler tương ứng:

~~~java
Mono<Void> consume(EventEnvelope event) {
    return switch (event.schemaVersion()) {
        case 1 -> handleV1(decodeV1(event.payload()));
        case 2 -> handleV2(decodeV2(event.payload()));
        default -> Mono.error(new UnsupportedSchemaVersionException(
            event.schemaVersion()
        ));
    };
}
~~~

Ví dụ này dùng JSON tree để minh họa việc chọn decoder theo version. Nếu dùng serializer khác, cần định nghĩa rõ schema registry hoặc decoder tương ứng. Không deserialize trực tiếp vào DTO mới rồi giả định mọi payload cũ đều tự tương thích.

## 5. Capability negotiation giữa client và server

Client mới không nên gửi route V2 tới server cũ chỉ dựa trên phiên bản client. Một cách rõ ràng là cung cấp route capability:

~~~java
public record ApiCapabilities(
    Set<Integer> orderCreateVersions,
    Set<Integer> eventSchemaVersions
) {}

@Controller
public class CapabilityController {

    @MessageMapping("system.capabilities")
    Mono<ApiCapabilities> capabilities() {
        return Mono.just(new ApiCapabilities(
            Set.of(1, 2),
            Set.of(1, 2)
        ));
    }
}
~~~

Client gọi system.capabilities, sau đó chọn version cao nhất nằm trong tập giao giữa version client hỗ trợ và server công bố:

~~~text
client supports: {1, 2}
server supports: {1}
intersection:    {1}
selected route: orders.v1.create
~~~

Capability negotiation là hợp đồng ứng dụng do hệ thống xây dựng; RSocket không tự thực hiện việc chọn phiên bản DTO hoặc route nghiệp vụ.

Trong rolling deployment, mỗi RSocket connection thường gắn với một backend instance đã nhận SETUP. Capability nhận được trên connection đó phản ánh server phía bên kia của connection. Không cache capability của một connection rồi dùng cho connection khác có thể được route tới instance khác.

Nếu server cũ chưa có route system.capabilities, client mới cần fallback về V1 theo chính sách rõ ràng. Một cách khác là client luôn dùng V1 cho tới khi feature flag bật V2 sau khi server fleet đã được nâng cấp.

## 6. Trình tự rollout server trước client

Với thay đổi cần thêm route hoặc field mới, trình tự an toàn thường là:

1. Chuẩn bị database schema theo expand-contract nếu thay đổi có liên quan.
2. Triển khai server mới hỗ trợ cả V1 và V2.
3. Xác minh tất cả server instance mới sẵn sàng và route V1 vẫn hoạt động.
4. Triển khai client mới nhưng tiếp tục gọi V1 mặc định.
5. Bật V2 cho một nhóm canary hoặc một tỷ lệ nhỏ client.
6. Quan sát lỗi decode, route not found, latency và tỷ lệ fallback.
7. Tăng dần traffic V2 khi các chỉ số ổn định.
8. Chờ client cũ, connection cũ và event cũ hết vòng đời.
9. Phát hành riêng một bản loại bỏ V1 sau khi xác nhận không còn consumer sử dụng.

Nếu client được triển khai trước server, client phải tiếp tục gọi V1 trong lúc server fleet còn instance cũ. Không bật V2 chỉ vì một vài Pod mới đã sẵn sàng.

### Ví dụ ma trận tương thích

Giả sử:

- C1 chỉ hỗ trợ V1.
- C2 hỗ trợ V1 và V2.
- S1 chỉ cung cấp V1.
- S2 cung cấp V1 và V2.

| Client / Server | S1 | S2 |
| --- | --- | --- |
| C1 | V1 | V1 |
| C2 khi chưa bật V2 | V1 | V1 |
| C2 sau capability negotiation | V1 | V1 hoặc V2 tùy capability |

Ma trận này cho phép C2 tồn tại trong fleet trước khi mọi server được nâng cấp. S2 không xóa V1 trong cùng release triển khai V2.

## 7. Triển khai cuốn chiếu trên Kubernetes

Kubernetes Deployment hỗ trợ chiến lược RollingUpdate. Hai thông số quan trọng:

- maxUnavailable: số Pod tối đa được phép không sẵn sàng trong quá trình cập nhật.
- maxSurge: số Pod bổ sung tối đa vượt quá replica mong muốn.

Ví dụ có bốn replica, cho phép tạo thêm một Pod mới và không giảm số Pod khả dụng trong quá trình rollout:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-rsocket
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: order-rsocket
  template:
    metadata:
      labels:
        app: order-rsocket
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: order-rsocket
          image: example/order-rsocket:2.0.0
          ports:
            - name: rsocket
              containerPort: 7000
            - name: management
              containerPort: 8081
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 5
            failureThreshold: 2
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: management
            periodSeconds: 5
            failureThreshold: 30
~~~

Để probe sử dụng cổng management riêng, cấu hình ứng dụng tương ứng:

~~~yaml
management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
~~~

Manifest là ví dụ minh họa; cần điều chỉnh image, port, probe và tài nguyên theo ứng dụng. maxUnavailable: 0 yêu cầu cluster có đủ capacity để tạo Pod surge. Nếu node không đủ tài nguyên hoặc quota không cho phép Pod bổ sung, rollout có thể chờ thay vì giảm Pod cũ.

Readiness probe giúp Kubernetes ngừng chọn Pod chưa sẵn sàng làm endpoint mới. Nó không tự đóng các TCP connection RSocket đã được thiết lập trước đó.

## 8. Connection RSocket dài hạn và quá trình drain Pod

HTTP request thường kết thúc sau một response. RSocket connection có thể tồn tại lâu và mang nhiều interaction trên cùng transport. Load balancer hoặc Kubernetes Service thường chọn backend khi connection được tạo; các request tiếp theo trên connection đó tiếp tục đi qua cùng socket.

Điều này tạo ra một tình huống đặc biệt khi rolling deployment:

1. Pod cũ bị đánh dấu không còn readiness.
2. Kubernetes ngừng đưa connection mới tới Pod đó sau khi endpoint cập nhật.
3. Các client đang giữ connection tới Pod cũ vẫn có thể tiếp tục gửi request trên connection đã mở.
4. Khi Pod cũ bị terminate, connection hiện hữu bị đóng.
5. Client cần reconnect hoặc resume theo cấu hình, sau đó tiếp tục interaction theo chính sách ứng dụng.

Vì vậy, readiness chỉ giải quyết việc chọn endpoint cho kết nối mới. Nó không phải cơ chế drain đầy đủ cho RSocket.

### Quy trình drain gợi ý

1. Đưa Pod vào trạng thái REFUSING_TRAFFIC để readiness thất bại.
2. Chờ endpoint controller và load balancer cập nhật.
3. Ngừng nhận connection RSocket mới ở listener hoặc gateway tương ứng.
4. Cho các interaction đang chạy một khoảng grace period để hoàn tất.
5. Thông báo hoặc đóng các connection còn lại theo chính sách client/server.
6. Đợi client reconnect sang instance còn sẵn sàng.
7. Đóng server transport và process trước khi hết termination grace period.

Ứng dụng cần tự quản lý bước drain cho RSocket TCP/WebSocket. Graceful shutdown của embedded HTTP server trong Spring Boot không nên được mặc định coi là đã drain mọi RSocket server transport độc lập.

### Spring Boot graceful shutdown

Spring Boot hỗ trợ graceful shutdown cho embedded web server:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Thiết lập này giúp web server từ chối request mới và cho request đang xử lý hoàn tất trong thời gian shutdown. Với RSocket TCP server riêng, cần bổ sung lifecycle quản lý listener, active connection và thời gian drain phù hợp.

Không đặt timeout drain dài hơn terminationGracePeriodSeconds. Nếu thời gian kết thúc Pod ngắn hơn grace period của ứng dụng, Kubernetes có thể gửi SIGKILL trước khi connection được đóng có kiểm soát.

## 9. Phục hồi client khi server instance bị thay thế

Client RSocket cần xác định rõ hành vi khi transport đóng:

- Nếu resume được bật và server còn session state, client có thể resume interaction cũ.
- Nếu resume bị từ chối hoặc server instance mới không có session state, client phải tạo SETUP mới.
- Với Request-Stream hoặc Request-Channel, client có thể tạo interaction mới từ cursor/sequence nghiệp vụ.
- Với command có side effect, client cần idempotency key trước khi retry.

Một reconnect strategy nên có:

- Exponential backoff và jitter.
- Giới hạn thời gian retry.
- Phân biệt lỗi tạm thời với lỗi authentication hoặc protocol không tương thích.
- Cập nhật metadata xác thực nếu token đã hết hạn.
- Resubscribe stream theo cursor sau khi tạo connection mới.
- Metric cho reconnect, resume, resume rejection và thời gian phục hồi.

Không retry vô hạn một route không tồn tại hoặc payload bị server từ chối do schema. Đây thường là lỗi tương thích cần xử lý bằng fallback hoặc rollback.

## 10. Expand-contract cho database schema

Rolling deployment không chỉ ảnh hưởng đến RSocket route. Nhiều thay đổi API đi kèm thay đổi database. Trong lúc rollout, code cũ và code mới có thể cùng truy cập một schema database.

Expand-contract chia một thay đổi phá vỡ tương thích thành các lần phát hành nhỏ:

### Giai đoạn 1 — Expand

Thêm cấu trúc mới nhưng chưa xóa cấu trúc cũ. Ví dụ thêm cột delivery_window nullable:

~~~sql
ALTER TABLE orders
ADD COLUMN delivery_window VARCHAR(80);
~~~

Code cũ vẫn đọc và ghi các cột hiện tại. Cột mới không bắt buộc trong giai đoạn đầu.

### Giai đoạn 2 — Migrate behavior

Triển khai code có thể ghi cả cột cũ và mới trong cùng transaction. Backfill dữ liệu lịch sử bằng batch có giới hạn. Sau khi dữ liệu đã được chuyển, code mới bắt đầu đọc từ cột mới và có thể fallback sang cột cũ khi cần.

Nếu code phải ghi đồng thời hai cột, hãy thực hiện hai thao tác trong cùng transaction database. Theo dõi số bản ghi chưa backfill và chênh lệch giữa hai cột trước khi chuyển read path.

~~~sql
UPDATE orders
SET delivery_window = legacy_delivery_slot
WHERE delivery_window IS NULL;
~~~

Lệnh backfill thực tế cần chia batch nếu bảng lớn, theo dõi lock, replication lag và tải database.

### Giai đoạn 3 — Contract

Chỉ sau khi tất cả instance cũ đã ngừng chạy, mọi consumer đã chuyển sang cấu trúc mới và rollback window đã kết thúc, mới xóa cột cũ:

~~~sql
ALTER TABLE orders
DROP COLUMN legacy_delivery_slot;
~~~

Không gộp expand và contract trong cùng release. Nếu rollback ứng dụng về phiên bản cũ, schema đã contract có thể khiến phiên bản cũ không khởi động hoặc không ghi được dữ liệu.

## 11. Tương thích event và consumer

RSocket có thể truyền event qua Request-Stream hoặc Request-Channel. Nếu producer và consumer được triển khai độc lập, thời gian tồn tại của event có thể dài hơn thời gian rollout.

Ví dụ event envelope:

~~~json
{
  "eventId": "8baf5f56-1dd8-4c9e-a5de-7c6b9f6d2a10",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "payload": {
    "orderId": "ORD-42",
    "customerId": "CUS-7",
    "deliveryWindow": "09:00-12:00"
  }
}
~~~

Consumer mới nên đọc được các schema version còn được phát trong thời gian chuyển đổi. Producer mới chỉ nên phát schema version mới khi mọi consumer nhận event đã hỗ trợ version đó hoặc có routing riêng theo capability.

Nếu event được lưu trong outbox hoặc broker, giữ decoder cũ ít nhất lâu hơn thời gian retention và replay. Một event cũ có thể được phát lại sau nhiều ngày khi vận hành khôi phục hoặc rebuild projection.

Quy tắc hữu ích:

- Thêm field optional trước khi producer bắt đầu ghi field đó.
- Consumer hỗ trợ schema mới trước khi producer phát schema mới.
- Không đổi ý nghĩa event type đang tồn tại.
- Dùng event type mới khi semantics nghiệp vụ thay đổi.
- Giữ event ID ổn định khi retry.
- Consumer idempotent để xử lý event replay.
- Theo dõi số consumer còn đọc schema cũ trước khi xóa decoder cũ.

## 12. Thay đổi metadata và authentication

Metadata cũng là hợp đồng. Một phiên bản server mới có thể cần thêm tenant context, correlation ID hoặc authentication claim. Trong thời gian rollout:

- Giữ các metadata entry cũ mà client cũ còn gửi.
- Server mới có thể chấp nhận cả metadata cũ và mới trong thời gian chuyển đổi.
- Không đổi MIME type hoặc cấu trúc entry đang dùng mà không có kế hoạch tương thích.
- Không yêu cầu một metadata entry mới trước khi tất cả client đã gửi nó.
- Không coi metadata thiếu là hợp lệ nếu nó liên quan đến authorization; hãy định nghĩa fallback an toàn.
- Không đưa credential vào data payload chỉ để tránh thay đổi metadata.

MIME type data và metadata được khai báo ở SETUP cho connection. Metadata entry theo request có thể bổ sung route, tracing hoặc authentication context nhưng cần được decoder phía nhận hỗ trợ. Hãy kiểm thử cả client cũ và client mới với server cũ và mới.

## 13. Canary và feature flag

Canary release triển khai phiên bản mới cho một nhóm traffic nhỏ trước khi mở rộng. Với RSocket, có thể chọn canary theo:

- Nhóm client hoặc tenant.
- Phiên bản ứng dụng client.
- Route V2 chỉ bật cho một nhóm caller.
- Connection được định tuyến tới một pool server canary.
- Feature flag tại gateway hoặc service client.

Không chỉ dựa vào tỷ lệ Pod mới để kết luận tỷ lệ traffic V2. Một connection RSocket có thể tồn tại lâu và tiếp tục gửi nhiều interaction tới cùng một Pod. Hãy đo số connection và số request thực tế theo phiên bản.

Feature flag nên có giá trị mặc định an toàn. Khi phát hiện lỗi decode hoặc latency tăng, có thể tắt V2 để client quay về V1 trong khi server vẫn giữ cả hai route.

## 14. Rollback và tương thích dữ liệu

Rollback ứng dụng không đồng nghĩa rollback mọi thay đổi dữ liệu. Nếu bản mới đã ghi payload V2 hoặc cột database mới, phiên bản cũ phải vẫn đọc được dữ liệu đó hoặc hệ thống cần có bước chuyển đổi an toàn.

Trước khi rollout, xác định:

1. Có thể quay lại image cũ trong bao lâu?
2. Phiên bản cũ có đọc được schema database sau expand không?
3. Server mới có giữ route cũ khi client rollback không?
4. Producer mới có phát event mà consumer cũ không hiểu không?
5. Có thể tắt V2 bằng feature flag không?
6. Cần replay hoặc backfill dữ liệu nào nếu rollback?

Không xóa route V1, cột cũ hoặc decoder cũ trong cùng lần phát hành đưa V2 vào production. Contract là một thay đổi riêng sau khi rollback window đóng và số liệu xác nhận không còn traffic cũ.

## 15. Kiểm thử tương thích trước khi rollout

Test suite nên kiểm tra ma trận phiên bản thay vì chỉ test phiên bản mới nhất:

| Client | Server | Payload | Kết quả |
| --- | --- | --- | --- |
| C1 | S1 | V1 | Thành công. |
| C1 | S2 | V1 | Thành công. |
| C2 | S1 | V1 fallback | Thành công. |
| C2 | S2 | V1 | Thành công. |
| C2 | S2 | V2 | Thành công khi capability cho phép. |
| C1 consumer | Producer mới | Event cũ | Consumer tiếp tục xử lý. |
| Consumer mới | Producer cũ | Event cũ | Consumer mới đọc được schema cũ. |
| Consumer cũ | Producer mới | Event mới | Chỉ cho phép nếu schema mới đã được chứng minh tương thích; nếu không, producer phải giữ V1. |

Các test quan trọng:

- Contract test route và DTO cho từng version.
- Serialization/deserialization test với payload lưu từ bản phát hành trước.
- Test enum value không biết trước và field optional bị thiếu.
- Test server mới nhận client cũ.
- Test client mới fallback khi server chưa hỗ trợ route V2.
- Test nhiều Pod cũ/mới sau khi load balancer tạo connection.
- Test reconnect khi Pod bị drain.
- Test stream resubscribe bằng cursor sau khi connection bị đóng.
- Test database rollback sau giai đoạn expand.
- Test event replay sau khi consumer được nâng cấp.

Lưu fixture payload của các phiên bản đã phát hành để kiểm tra tương thích theo thời gian. Chỉ kiểm tra DTO mới serialize rồi deserialize lại chính DTO đó là chưa đủ.

## 16. Theo dõi rollout

Trong rollout, theo dõi các chỉ số theo application version, route version và instance:

| Metric / log field | Mục đích |
| --- | --- |
| active_connections | Số connection RSocket theo Pod và phiên bản. |
| active_interactions | Số request/stream/channel đang hoạt động. |
| requests_by_route_version | Traffic V1 và V2. |
| decode_errors | Payload không tương thích hoặc schema không hợp lệ. |
| route_not_found | Client gọi route chưa được server hỗ trợ. |
| reconnect_total | Số lần client tạo lại connection. |
| resume_success / resume_rejected | Kết quả phục hồi connection. |
| stream_resubscribe_total | Số lần tạo lại stream ở tầng ứng dụng. |
| event_schema_version | Số event theo schema version. |
| pod_ready_duration | Thời gian Pod mới trở thành Ready. |

Không dùng customer ID, connection token hoặc request ID làm metric label có cardinality cao. Những giá trị này phù hợp hơn với log hoặc trace.

Đặt ngưỡng dừng rollout trước khi phát hành, ví dụ tỷ lệ decode error, route not found, request failure và p95 latency. Nếu vượt ngưỡng, pause rollout hoặc tắt feature flag V2 để điều tra.

## 17. Ví dụ trình tự phát hành V1 sang V2

Giả sử V2 thêm deliveryWindow và thay đổi response:

~~~text
Thời gian  | Server fleet        | Client fleet        | Database
-----------|---------------------|---------------------|----------------
T0         | S1 (V1)             | C1 (V1)             | schema cũ
T1         | S1 + S2 (V1,V2)     | C1 (V1)             | expand
T2         | S2 (V1,V2)          | C1 + C2 (V1)        | dual write
T3         | S2 (V1,V2)          | C2 canary (V2)      | backfill
T4         | S2 (V1,V2)          | C2 (V2)             | read new
T5         | S2 (V2, V1 retained)| C2 (V2)             | contract sau rollback window
T6         | S3 (V2 only)        | C2 (V2)             | schema mới
~~~

Ở T5, route V1 chỉ được loại bỏ khi không còn client cũ và event cũ trong thời hạn replay. Database contract có thể diễn ra muộn hơn thời điểm client chuyển V2 để bảo đảm rollback an toàn.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client mới thỉnh thoảng gặp route not found | Một số Pod server cũ chưa có route V2. | Giữ client ở V1 cho tới khi fleet hỗ trợ V2 hoặc capability negotiation/fallback. |
| Server mới lỗi khi nhận payload cũ | Handler mới chỉ deserialize DTO mới. | Giữ decoder và handler V1. |
| Consumer cũ lỗi khi nhận event mới | Producer chuyển schema trước consumer. | Triển khai consumer trước và chỉ bật producer sau. |
| Rollback ứng dụng thất bại | Bản mới đã xóa field/route hoặc contract database quá sớm. | Tách expand và contract thành các release riêng. |
| Readiness thành công nhưng request vẫn tới Pod cũ | Connection RSocket hiện hữu vẫn mở. | Drain connection, không chỉ đánh dấu Pod unready. |
| Rollout xong nhưng traffic V1 vẫn còn | Client hoặc connection cũ tồn tại lâu. | Đo active connection và thời gian sống client; giữ V1 cho tới khi hết traffic. |
| Capability negotiation chọn sai version | Capability được cache giữa các connection hoặc không phản ánh instance thực tế. | Đọc capability theo connection và fallback an toàn. |
| Event replay thất bại | Decoder cũ bị xóa trước khi hết retention. | Giữ decoder theo thời hạn replay và lịch sử event. |

## 19. Checklist triển khai cuốn chiếu

- [ ] Tách version RSocket wire protocol khỏi version API/payload ứng dụng.
- [ ] Giữ MIME type SETUP ổn định trong giai đoạn rollout.
- [ ] Định nghĩa rõ route version hoặc schema version cho payload.
- [ ] Bảo đảm server mới hỗ trợ hợp đồng cũ.
- [ ] Bảo đảm client mới fallback khi server chưa hỗ trợ hợp đồng mới.
- [ ] Triển khai consumer trước producer khi thay đổi event schema.
- [ ] Dùng expand-contract cho database migration.
- [ ] Triển khai server mới trước, sau đó mới bật client V2.
- [ ] Canary V2 và theo dõi route, decode error, latency, reconnect.
- [ ] Dùng readiness và maxSurge/maxUnavailable để điều tiết Pod rollout.
- [ ] Drain connection RSocket dài hạn trước khi terminate Pod.
- [ ] Cấu hình reconnect/resume và application-level cursor/idempotency.
- [ ] Giữ route, decoder và cột cũ trong rollback window.
- [ ] Chỉ contract sau khi không còn client, consumer hoặc event cũ.
- [ ] Lưu payload fixture và chạy contract test giữa các version.

## 20. Ghi nhớ

- Rolling deployment tạo giai đoạn mixed-version; client và server khác phiên bản phải cùng tồn tại an toàn.
- RSocket protocol version trong SETUP khác với version route và schema payload do ứng dụng định nghĩa.
- Data MIME type và metadata MIME type được khai báo ở SETUP và áp dụng cho connection; không dùng chúng như version DTO theo từng request.
- Route V1/V2 hoặc schema version trong envelope giúp duy trì nhiều hợp đồng trong giai đoạn chuyển đổi.
- Triển khai server hỗ trợ cả V1 và V2 trước khi client bắt đầu gửi V2.
- Capability negotiation là hợp đồng ứng dụng; RSocket không tự chọn version payload nghiệp vụ.
- Expand-contract giữ schema database tương thích khi code cũ và mới cùng chạy.
- Readiness ngăn kết nối mới tới Pod không sẵn sàng nhưng không tự đóng connection RSocket đã tồn tại.
- RSocket connection dài hạn cần drain và reconnect/resume hoặc resubscribe theo cursor.
- Chỉ xóa route, field và decoder cũ sau khi hết client cũ, event cũ và rollback window.

## Tài liệu tham khảo

- [RSocket Protocol — Versioning, SETUP, Data and Metadata](https://rsocket.io/about/protocol/)
- [Kubernetes — Deployments and Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Update a Deployment Without Downtime](https://kubernetes.io/docs/tutorials/kubernetes-basics/update/update-intro/)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Boot — Actuator Readiness and Liveness Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Flyway — Expand and Contract Database Changes](https://documentation.red-gate.com/flyway/deploying-database-changes-using-flyway/rolling-out-updates-from-a-single-schema-to-multiple-production-databases)
