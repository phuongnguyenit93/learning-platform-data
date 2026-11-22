# Retry-aware supplier và tránh chọn lại bản sao vừa lỗi

Khi `order-service` gọi `inventory-service` qua Spring Cloud LoadBalancer, client có thể chọn một `ServiceInstance` rồi gặp `connection refused`, timeout hoặc một HTTP response được chính sách đánh giá là có thể thử lại. Nếu lần thử tiếp theo vẫn được gửi đến đúng replica vừa gặp sự cố, retry có thể chỉ làm tăng độ trễ và tiếp tục tạo tải lên instance lỗi.

Spring Cloud LoadBalancer hỗ trợ một thành phần dành cho tình huống này: **`RetryAwareServiceInstanceListSupplier`**. Thay vì tự thực hiện retry, supplier dùng **ngữ cảnh của lần thử trước** để chuẩn bị danh sách ứng viên cho **lần lựa chọn tiếp theo**, ưu tiên loại instance vừa được chọn trước đó nếu còn bản sao khác.

Đây là bài học của chương **Gửi lại yêu cầu** trong module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Chúng ta sẽ phân biệt retry policy với việc chọn instance, giải thích vai trò của `ServiceInstanceListSupplier#get(Request)`, cấu hình tránh instance trước, xử lý trường hợp chỉ còn một replica và kiểm thử đường gọi bằng RestClient, WebClient hoặc OpenFeign. Mục tiêu là bảo vệ tính đúng đắn của nghiệp vụ khi dùng retry/timeout và giúp quan sát lỗi của từng replica chính xác hơn.

> Ý chính: **retry-aware supplier không phải circuit breaker, không tự tạo thêm HTTP request và không duy trì danh sách đen vĩnh viễn**. Nó chỉ giúp lựa chọn ứng viên cho một lần chọn lại khi integration retry truyền đúng ngữ cảnh và còn bản sao thay thế phù hợp.

## 1. Bài toán: lần thử tiếp theo lại rơi vào instance vừa lỗi

Giả sử `inventory-service` có ba replica:

| Instance | Địa chỉ | Tình trạng trong ví dụ |
| --- | --- | --- |
| A | `10.0.1.11:8080` | Đã dừng nhận kết nối nhưng thông tin discovery còn cũ |
| B | `10.0.1.12:8080` | Đang chạy |
| C | `10.0.1.13:8080` | Đang chạy |

`order-service` gọi:

```http
GET /api/stocks/BOOK-001 HTTP/1.1
Host: inventory-service
Accept: application/json
```

Discovery hoặc cache hiện vẫn trả danh sách `[A, B, C]`. Ở lần thử đầu, LoadBalancer chọn A:

```text
Attempt 1
  Service ID: inventory-service
  Danh sách ứng viên: [A, B, C]
  Instance được chọn: A (10.0.1.11:8080)
  HTTP outcome: Connection refused
```

Một chính sách retry cho phép thử lại request này. Nếu hệ thống chỉ chạy lại bước chọn trên cùng danh sách `[A, B, C]`, **không có bảo đảm** lần chọn mới sẽ khác A. Một thuật toán như Random hoàn toàn có thể chọn lại A; Round Robin có trạng thái lựa chọn riêng và cũng không nên được xem là cơ chế “nhớ instance lỗi” cho mọi đường gọi.

Với supplier nhận biết retry, lần chọn tiếp theo có thể bắt đầu từ `[B, C]`:

```text
Attempt 2
  Previous ServiceInstance: A
  Danh sách từ discovery: [A, B, C]
  Danh sách sau retry-aware filtering: [B, C]
  Instance được chọn: C (10.0.1.13:8080)
  HTTP outcome: 200 OK
```

Phần lọc không chữa được lỗi trên A, nhưng nó **giảm khả năng tái sử dụng ngay bản sao vừa thất bại trong lần thử tiếp theo**.

## 2. Tách ba quyết định: có retry, chọn ai và gửi như thế nào?

Để hiểu đúng `RetryAwareServiceInstanceListSupplier`, phải chia trách nhiệm thành ba bước:

1. **Retry policy:** quyết định một lỗi có đủ điều kiện thử lại hay không; giới hạn số lần, backoff và deadline.
2. **Instance supplier và LoadBalancer:** tạo danh sách ứng viên, tránh replica đã chọn ở attempt trước khi có thể và chọn một `ServiceInstance` cho lần thử mới.
3. **HTTP client/transport:** thực sự gửi request tới địa chỉ được chọn, chờ response, áp dụng connect/read timeout và trả lỗi nếu thất bại.

| Thành phần | Trách nhiệm chính | Không nên gán cho nó |
| --- | --- | --- |
| Retry engine / `LoadBalancerRetryPolicy` | Quyết định có thử tiếp sau lỗi; kiểm tra attempt và loại lỗi | Phát hiện registry thay đổi hoặc tạo metadata zone |
| `RetryAwareServiceInstanceListSupplier` | Điều chỉnh danh sách instance theo ngữ cảnh retry | Tự phát HTTP request hoặc quyết định nghiệp vụ có an toàn để gửi lại |
| `RoundRobinLoadBalancer` / thuật toán khác | Chọn một instance trong danh sách mà supplier cung cấp | Giữ danh sách “instance lỗi toàn cục” |
| `DiscoveryClient` | Cung cấp danh sách replica do nguồn discovery biết | Chọn instance thay thế cho một attempt cụ thể |
| RestClient / WebClient / OpenFeign | Thực hiện HTTP qua integration được cấu hình | Tự có retry/load balancing giống nhau ở mọi phiên bản |

**Không nên đánh đồng “chọn instance khác” với “có quyền retry”.** Một request `POST` có tác dụng phụ có thể không an toàn để gửi lại, dù supplier có sẵn nhiều replica khỏe.

## 3. Luồng tổng quan của một lời gọi có retry

```mermaid
sequenceDiagram
    participant Caller as order-service
    participant Policy as Retry policy
    participant LB as Spring Cloud LoadBalancer
    participant Supplier as RetryAwareServiceInstanceListSupplier
    participant Discovery as Discovery supplier
    participant A as inventory-service A
    participant C as inventory-service C

    Caller->>Policy: GET /api/stocks/BOOK-001
    Policy->>LB: Chọn instance (attempt 1)
    LB->>Supplier: get(request chưa có previous instance)
    Supplier->>Discovery: Lấy danh sách ứng viên
    Discovery-->>Supplier: [A, B, C]
    Supplier-->>LB: [A, B, C]
    LB-->>Policy: Chọn A
    Policy->>A: HTTP request
    A--xPolicy: Connection refused
    Policy->>Policy: Kiểm tra retry policy + deadline
    Policy->>LB: Chọn instance (attempt 2; previous=A)
    LB->>Supplier: get(request có retry context)
    Supplier->>Discovery: Lấy danh sách ứng viên
    Discovery-->>Supplier: [A, B, C]
    Supplier-->>LB: [B, C] nếu còn lựa chọn khác
    LB-->>Policy: Chọn C
    Policy->>C: HTTP request
    C-->>Policy: HTTP 200
    Policy-->>Caller: Kết quả cuối cùng
```

Sơ đồ phản ánh **một đường gọi minh họa** khi integration retry thực sự tạo lần lựa chọn mới và truyền previous instance. Thứ tự callback, cách triển khai HTTP client và cách lưu context cụ thể có thể thay đổi theo phiên bản Spring Cloud. Khi không có retry hoặc request không đủ điều kiện retry, chỉ xảy ra lần thử đầu.

## 4. RetryAwareServiceInstanceListSupplier làm việc tại ranh giới nào?

Trong Spring Cloud LoadBalancer, `ServiceInstanceListSupplier` có hai đường lấy dữ liệu:

```java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
```

`get()` trả danh sách mà không cần thông tin về request hiện tại. `get(Request)` cho phép một lớp supplier phụ thuộc request: đọc hint, thông tin sticky session hoặc **ngữ cảnh retry**.

`RetryAwareServiceInstanceListSupplier` là một supplier dạng **decorator**: nó bọc một supplier khác, nhận danh sách ứng viên rồi áp dụng logic liên quan tới instance được chọn trước đó.

Một cấu trúc khái niệm:

```text
RoundRobinLoadBalancer
  |
  v
RetryAwareServiceInstanceListSupplier
  |
  v
Zone / health / hint suppliers (nếu cấu hình)
  |
  v
CachingServiceInstanceListSupplier (nếu cần)
  |
  v
DiscoveryClientServiceInstanceListSupplier
```

Thứ tự các lớp có thể khác tùy cấu hình. Đối với cache hoặc health-check, tài liệu Spring Cloud khuyến nghị đặt gần supplier lấy instance từ mạng, **trước các bộ lọc phụ thuộc request**, để tránh cache nhầm kết quả của request A cho request B.

Trong mỗi lần chọn, supplier nhận request **không phải HTTP response của server**. Dữ liệu đó là ngữ cảnh do LoadBalancer/retry integration tạo ra để lựa chọn replica. Nó cũng không nhất thiết là toàn bộ request body hoặc DTO nghiệp vụ.

## 5. Ngữ cảnh retry lưu điều gì?

Ở attempt đầu, chưa có instance được chọn trước đó, nên retry-aware supplier thường không có gì để loại.

Sau khi một attempt thất bại và retry engine quyết định thử tiếp, integration có thể truyền thông tin kiểu:

```text
serviceId = inventory-service
attemptIndex = 2                 // nhãn minh họa cho log của ứng dụng
previousServiceInstance = A       // ServiceInstance của attempt trước
```

**Mấu chốt là `previousServiceInstance`**, không phải chỉ thông báo “request đã retry”. Một supplier muốn tránh A cần biết A là instance nào trong danh sách ứng viên, chứ không thể suy từ việc nhận exception mà không có quan hệ với attempt trước.

Trong các phiên bản Spring Cloud, ngữ cảnh này được cung cấp qua các kiểu request/retry context tương ứng. Không nên phụ thuộc vào một class context cụ thể mà chưa kiểm tra phiên bản; về nguyên tắc, cơ chế retry phải truyền đủ thông tin cho `ServiceInstanceListSupplier#get(Request)`.

Điểm cần hiểu rõ:

- **Supplier không tự ghi nhận request HTTP nào đã thất bại.** Lỗi được retry engine và HTTP client quan sát.
- **Supplier không mặc định nhớ mọi instance đã từng lỗi trong suốt business request.** Cơ chế chuẩn chủ yếu tránh instance của **lần lựa chọn trước**, không phải lưu tập tất cả các instance lỗi xuyên nhiều attempt.
- **Nếu request context bị bỏ qua ở một decorator, retry-aware filtering có thể không nhận được previous instance** và không thể hoạt động theo ý định.

## 6. Thuật toán tránh bản sao cũ: ví dụ đơn giản

Hình dung danh sách discovery là `[A, B, C]` và previous instance là A. Thuật toán khái niệm:

```text
function chooseCandidates(instances, previous):
    if previous is absent:
        return instances

    alternatives = instances excluding previous

    if alternatives is not empty:
        return alternatives

    return instances   # fallback nếu không có lựa chọn khác
```

Bảng hành vi:

| Danh sách trước lọc | Instance trước | Danh sách ứng viên kỳ vọng |
| --- | --- | --- |
| `[A, B, C]` | Chưa có | `[A, B, C]` |
| `[A, B, C]` | A | `[B, C]` |
| `[A, B, C]` | B | `[A, C]` |
| `[A]` | A | `[A]`, vì không có bản sao khác |
| `[B, C]` | A | `[B, C]`, vì A đã không còn trong danh sách |
| `[]` | A | `[]`, vì không có đích để lựa chọn |

**Fallback khi chỉ còn một instance** là chi tiết quan trọng: nếu A là replica duy nhất, việc loại A sẽ tạo danh sách rỗng. Cơ chế tránh previous instance thường chỉ ưu tiên một lựa chọn khác **khi có thể**, chứ không cam kết không bao giờ chọn lại A.

Bảng là mô hình hành vi để học. Việc so khớp danh tính instance trong implementation thực tế dựa trên cấu trúc và so sánh `ServiceInstance` mà thư viện sử dụng; khi tự viết supplier, cần đặc biệt cẩn thận với `instanceId`, `host`, `port` và cách implementation định nghĩa equality.

## 7. Trường hợp chỉ có một replica: tránh khác với cấm

Giả sử staging chỉ chạy một bản sao:

```text
inventory-service -> A (10.0.1.11:8080)
```

Attempt 1 tới A gặp timeout. Nếu policy cho phép retry, supplier không có instance B/C để thay thế. Có hai mục tiêu có thể xung đột:

1. **Khả năng phục hồi:** thử lại A nếu lỗi có thể là sự cố thoáng qua.
2. **Giảm tải/giới hạn lỗi:** không tiếp tục bắn request vào A nếu A đang quá tải hoặc lỗi kéo dài.

`RetryAwareServiceInstanceListSupplier` thiên về cung cấp lựa chọn khác **nếu danh sách có nhiều instance**. Nó không thay thế quyết định retry. Nếu retry A không mang lại lợi ích, retry policy, circuit breaker, health check hoặc deadline mới là nơi thích hợp để giới hạn số lần thử.

Do đó, “đã bật avoid previous” **không bảo đảm mọi attempt đi đến instance khác**, đặc biệt khi supplier chỉ thấy một ứng viên còn lại sau zone/health/hint filtering.

## 8. Khác nhau giữa tránh lần trước và chọn theo Round Robin

Round Robin là thuật toán lựa chọn theo vòng dựa trên danh sách nhận được. Khi danh sách ổn định `[A, B, C]`, một số lần chọn liên tiếp của cùng một LoadBalancer có thể tạo chuỗi `A → B → C → A`.

Tuy vậy:

- Round Robin **không biết** request trước đã lỗi hay thành công chỉ từ thuật toán.
- Nhiều caller có trạng thái cân bằng tải riêng; request và retry có thể xen kẽ với request khác.
- Thứ tự danh sách có thể đổi khi registry, cache, zone hoặc health filtering thay đổi.
- Nếu retry và non-retry cùng dùng chung LoadBalancer, “phần tử kế tiếp” không phải luôn “bản sao khác với attempt lỗi của business request hiện tại”.

Retry-aware filtering bổ sung thông tin **previous instance** vào quá trình chuẩn bị ứng viên, sau đó Round Robin mới chọn trên tập đã lọc. Vì vậy, nó hỗ trợ tính đúng mục tiêu “tránh A trong attempt kế” tốt hơn việc chỉ trông chờ vòng tròn tự nhiên của thuật toán.

## 9. Cấu hình tránh chọn instance trước trong Spring Cloud LoadBalancer

Thuộc tính liên quan đến hành vi này là:

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        avoid-previous-instance: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retry-on-all-operations: false
```

Ý nghĩa:

| Thuộc tính | Ý định cấu hình |
| --- | --- |
| `retry.enabled` | Cho phép tính năng retry của LoadBalancer khi integration/dependency hỗ trợ |
| `retry.avoid-previous-instance` | Cho phép bọc supplier bằng `RetryAwareServiceInstanceListSupplier` để ưu tiên không chọn lại instance trước nếu có thay thế |
| `retry.max-retries-on-same-service-instance` | Số lần retry trên cùng instance theo chính sách của integration |
| `retry.max-retries-on-next-service-instance` | Số lần retry với một lựa chọn instance khác |
| `retry.retry-on-all-operations` | Có cho phép xét retry với các HTTP operation ngoài những operation mặc định an toàn hay không |

Trong tài liệu cấu hình Spring Cloud Commons hiện hành, `retry.avoid-previous-instance` có **giá trị mặc định `true`**. Tuy nhiên, **mặc định của property không có nghĩa mọi HTTP client luôn retry**: việc tạo retry request còn phụ thuộc integration, classpath, error policy và các bean liên quan. Đặc biệt, với nhiều phiên bản, đường retry đồng bộ cần các thành phần Spring Retry thích hợp. Với reactive, cơ chế kích hoạt và hỗ trợ retry có điều kiện khác.

Ví dụ trên đặt `avoid-previous-instance: true` một cách tường minh nhằm thể hiện ý định; không nên hiểu là phải bật lại một property vốn có mặc định đã bật. Các tên property dùng dạng kebab-case; các phiên bản cũ có thể hiển thị dạng camelCase trong một số ví dụ tài liệu.

### 9.1. Khi nào tắt hành vi này?

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        avoid-previous-instance: false
```

Chỉ cân nhắc tắt khi có lý do vận hành rõ ràng, chẳng hạn chính sách đặc biệt yêu cầu chọn lại cùng instance hoặc integration tùy biến tự thực hiện việc lựa chọn. **Tắt avoidance không đồng nghĩa tắt retry**; cũng không đồng nghĩa mọi attempt chắc chắn vào cùng instance.

Nếu muốn **tắt retry của LoadBalancer**, đó là quyết định khác với tắt previous-instance avoidance; cần kiểm tra `retry.enabled` và mọi retry ở các tầng khác của ứng dụng.

### 9.2. Cấu hình riêng theo service

Một ứng dụng có thể gọi nhiều downstream với mức chịu lỗi khác nhau. Spring Cloud LoadBalancer hỗ trợ cấu hình theo từng client/service ID qua nhóm property dành cho client ở những phiên bản tương ứng. Cần kiểm tra namespace có hiệu lực, ví dụ `spring.cloud.loadbalancer.clients.<clientId>...`, trước khi áp dụng.

Không nên bật cùng một mức retry cho toàn bộ dịch vụ chỉ vì phần `inventory-service` có nhiều replica. Một API báo cáo chậm hoặc một API `POST` thay đổi trạng thái có thể cần chính sách khác với `GET` đọc tồn kho.

## 10. Auto-configuration và supplier tự định nghĩa

Spring Cloud LoadBalancer có thể **tự động bọc** `ServiceInstanceListSupplier` hiện có bằng `RetryAwareServiceInstanceListSupplier` khi đường retry phù hợp được bật. Các điều kiện cụ thể phụ thuộc blocking/reactive integration, dependency và phiên bản framework.

Vì vậy, trong phần lớn ứng dụng:

1. Bật và cấu hình retry đúng cho HTTP client/integration.
2. Cho phép hành vi `avoid-previous-instance`.
3. Kiểm tra supplier chain thực tế có lớp retry-aware.
4. Quan sát lần retry có nhận context previous instance hay không.

**Không nên tự bọc thêm một tầng retry-aware vào custom chain khi auto-configuration đã bọc sẵn**, vì sẽ khiến cấu trúc khó hiểu và dễ nhầm rằng có hai bộ máy retry. Việc supplier bị bọc không quyết định số attempt; nhưng lặp decorator vẫn có thể làm phức tạp debug và cấu hình.

### 10.1. Ví dụ tạo nguồn danh sách instance tùy chỉnh

Nếu ứng dụng cần custom chain, nên bắt đầu từ supplier lấy danh sách và cấu hình các filter đúng chỗ. Ví dụ dưới đây **chỉ minh họa nguồn instance**, không tự bật retry:

```java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class InventoryInstancesConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
```

Để dùng bean này riêng cho service ID `inventory-service`, cần gắn lớp cấu hình với `@LoadBalancerClient(name = "inventory-service", configuration = InventoryInstancesConfiguration.class)` theo cách phù hợp, đồng thời tránh để lớp cấu hình riêng bị component scan toàn cục làm áp dụng nhầm.

Khi discovery client đã cache (chẳng hạn một số cách triển khai Eureka), không nên tự động thêm `.withCaching()` nếu không cần; việc double caching có thể giữ replica lỗi trong danh sách lâu hơn. Đặc biệt, **cache danh sách gốc nên nằm trước filter phụ thuộc request** để tránh chia sẻ kết quả lọc attempt A cho attempt B.

Nếu đặt cấu hình custom, phải kiểm tra **retry-aware decorator có còn được auto-configuration áp dụng hay không**. Không giả định mọi chain tùy biến sẽ tự động nhận những lớp bọc giống chain mặc định.

## 11. Giữ context qua các lớp supplier

Điểm nối quan trọng là lời gọi:

```java
delegate.get(request);
```

Một decorator không phụ thuộc request có thể cần chuyển tiếp context này để những lớp bên trong nhận được thông tin retry. Ví dụ cách chuyển tiếp đúng:

```java
@Override
public Flux<List<ServiceInstance>> get(Request request) {
    return delegate.get(request);
}
```

Nếu viết nhầm:

```java
@Override
public Flux<List<ServiceInstance>> get(Request request) {
    return delegate.get(); // Bỏ context, có thể làm mất dữ liệu retry
}
```

thì supplier cần `previousServiceInstance` có thể không nhận được thông tin đó. Kết quả nguy hiểm là danh sách trả về vẫn hợp lệ nhưng bước avoid-previous hoạt động khác mong đợi.

Lưu ý: hai đoạn mã trên là **minh họa phần method trong decorator** có sẵn biến `delegate`, không phải class độc lập có thể biên dịch ngay. Một số supplier nguồn như cache/discovery không cần context để hoạt động; nhưng nếu chuỗi được kỳ vọng truyền request đến các filter phụ thuộc request, hãy kiểm tra chiều và vị trí các lớp để context không bị mất.

## 12. Không biến retry-aware supplier thành global blacklist

Khi A vừa timeout, có thể xuất hiện ý tưởng “đánh dấu A lỗi và xóa A vĩnh viễn khỏi danh sách”. Đây không phải trách nhiệm mặc định của `RetryAwareServiceInstanceListSupplier`.

**Previous-instance avoidance** có phạm vi hẹp:

- Liên quan đến **lượt retry cụ thể** và instance vừa được chọn trước đó.
- Không mặc nhiên lưu trữ lịch sử mọi lỗi theo host, port, zone hoặc service ID.
- Không thực hiện probe health check hay kết nối TCP để xác định A đã chết.
- Không loại A khỏi lựa chọn của **mọi request khác** nếu A vẫn có mặt trong nguồn instance.

Nếu cần giảm traffic tới replica lỗi trên diện rộng, nên dùng kết hợp:

| Cơ chế | Mục tiêu |
| --- | --- |
| Discovery deregistration / lease | Cập nhật topology khi instance đã rời hệ thống |
| Health-check supplier | Lọc instance không khỏe theo probe được cấu hình |
| Cache TTL/refresh hợp lý | Không giữ topology đã lỗi quá lâu |
| Circuit breaker | Chặn lời gọi tới dependency khi chính sách phát hiện nhiều lỗi |
| Bulkhead / concurrency limit | Hạn chế tác động lan truyền khi downstream quá tải |
| Retry-aware supplier | Hạn chế chọn lại instance của attempt vừa thất bại |

Các cơ chế này bổ sung cho nhau, không thể dùng một cơ chế thay thế hoàn toàn các cơ chế còn lại.

## 13. Quan hệ với zone, sticky session và các filter khác

Giả sử `inventory-service` có:

| Instance | Zone | Trạng thái |
| --- | --- | --- |
| A | `zone-a` | Vừa lỗi |
| B | `zone-a` | Khỏe |
| C | `zone-b` | Khỏe |

Caller chạy tại `zone-a` và có `ZonePreferenceServiceInstanceListSupplier` được cấu hình. Sau bước zone preference, danh sách có thể là `[A, B]`. Nếu retry-aware filter nhận previous=A, danh sách còn `[B]`.

Nhưng giả sử **chỉ A ở zone-a** và C ở zone-b. Nếu zone preference đã lọc thành `[A]` trước khi retry-aware lọc, supplier có thể chỉ thấy một ứng viên và fallback về A. Nếu muốn failover sang C, cần thiết kế chain và chính sách zone cho phù hợp thay vì mặc định retry-aware có thể tìm instance ngoài danh sách mà delegate cung cấp.

Tương tự, với **sticky session**, hệ thống có thể ưu tiên instance trước vì dữ liệu phiên nằm cục bộ. Chính sách “giữ cùng instance” và “tránh instance vừa lỗi” có thể xung đột. Phải xác định thứ tự và ưu tiên của các lớp: availability hay affinity quan trọng hơn, và ứng dụng có chịu được chuyển phiên sang replica khác không?

**Retry-aware supplier chỉ được chọn trong danh sách do delegate cung cấp.** Nó không thể tự khôi phục replica bị một filter khác loại bỏ, và cũng không tự mở rộng zone sang region khác nếu logic cấu hình không cho phép.

## 14. Retry sau nhiều lần lỗi: không phải danh sách tất cả instance đã thử

Xét danh sách `[A, B, C]`:

```text
Attempt 1: chọn A -> timeout
Attempt 2: previous=A -> có thể chọn B -> timeout
Attempt 3: previous=B -> có thể chọn A hoặc C
```

Nếu cơ chế chỉ tránh **immediate previous instance**, ở attempt 3, A có thể quay trở lại danh sách ứng viên. **Không nên mặc định thứ tự sẽ là A → B → C** hay tất cả các instance sẽ được thử đúng một lần.

Khi yêu cầu phải thử qua các replica khác nhau không lặp lại trong cùng một business request, đó là một chính sách nâng cao:

- Theo dõi tập instance đã thử trong context theo request.
- Truyền context đúng cho mọi lần chọn.
- Xác định cách xử lý khi mọi instance đều đã được thử.
- Giới hạn số attempt và deadline.
- Kiểm tra tương tác với zone, sticky, health và chính sách lựa chọn.

Spring Cloud LoadBalancer mặc định chỉ hỗ trợ cơ chế tránh previous instance như mô tả; không nên tự suy ra có sẵn một lịch sử blacklist cho toàn bộ chuỗi retry.

## 15. Cùng instance và instance tiếp theo: hiểu các giới hạn

Hai nhóm cấu hình phải được đọc cùng nhau:

```yaml
spring:
  cloud:
    loadbalancer:
      retry:
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
```

Theo ý định, giá trị này hạn chế retry trên cùng instance và cho phép một lần thử với instance được chọn tiếp theo trong đường integration hỗ trợ.

Tuy nhiên, **“next service instance” không phải một địa chỉ cố định**. Bộ chọn vẫn hoạt động trên danh sách do supplier trả về. Khi không có instance thay thế, thuật toán có thể trả lại instance cũ, tùy tập ứng viên và fallback. Cần kiểm thử số attempt và selected instance thực tế thay vì suy đoán từ tên property.

Cần phân biệt:

| Khía cạnh | Same-instance retry | Next-instance retry |
| --- | --- | --- |
| Có lần chọn instance mới? | Có thể không cần | Thường cần lần lựa chọn mới |
| Có thể chuyển khỏi replica vừa lỗi? | Không, vì chủ đích giữ nguyên | Có, nếu supplier/LoadBalancer có ứng viên khác |
| Có tránh được lỗi server quá tải? | Có thể làm tải tăng ngay trên replica lỗi | Có thể phân tán sang replica khác nhưng cũng tăng tổng tải |
| Còn cần timeout? | Có | Có |
| Còn cần idempotency khi ghi dữ liệu? | Có | Có |

Từ “retry” không chứng minh request sẽ được gửi lại chính xác một lần. Một client tích hợp Spring Cloud LoadBalancer, HTTP transport và tầng ứng dụng có thể có các retry policy khác nhau, dẫn đến **nhân số attempt** nếu cấu hình không phối hợp.

## 16. Chỉ retry lỗi có thể phục hồi và request an toàn

Tránh A sau một lỗi chỉ có ích khi việc gửi lại request **được phép** và có cơ hội thành công ở replica khác.

| Kết quả attempt trước | Khả năng retry | Lý do |
| --- | --- | --- |
| `GET` gặp connection refused | Có thể retry có giới hạn | Replica có thể đã ngừng lắng nghe; thử instance khác hữu ích |
| `GET` nhận `503` tạm thời | Có thể retry với backoff | Downstream có thể quá tải; cần tránh retry storm |
| `GET` nhận `429` | Theo `Retry-After` và deadline | Hạn mức có thể áp dụng toàn bộ dịch vụ, không riêng một replica |
| `GET` nhận `404` vì không có SKU | Thường không retry | Đổi instance không tạo ra tài nguyên không tồn tại |
| `POST` giữ hàng bị read timeout | Không retry mù quáng | Server có thể đã thực thi thao tác |
| `POST` có idempotency key được server bảo đảm | Có thể retry giới hạn | Server phải bảo vệ khỏi duplicate xuyên replica |
| `400` do dữ liệu đầu vào sai | Không retry | Việc đổi replica không sửa payload |

**Retry policy quyết định lỗi nào được thử lại; retry-aware supplier chỉ quyết định danh sách instance cho lượt thử đã được phép.** Nên phối hợp với deadline tổng và exponential backoff có jitter, nhất là khi nhiều caller có thể gặp cùng sự cố.

## 17. Ví dụ ứng dụng: WebClient gọi theo service ID

Một `WebClient.Builder` có `@LoadBalanced` là điểm tích hợp phổ biến:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Client tạo từ builder này có thể gọi URL logic:

```java
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

class InventoryGateway {

    private final WebClient client;

    InventoryGateway(@LoadBalanced WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    Mono<StockResponse> findStock(String sku) {
        return client.get()
                .uri("/api/stocks/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);
    }
}
```

Ở đây `StockResponse` là DTO do ứng dụng định nghĩa. **Chỉ với code này chưa khẳng định có retry**: nó khởi tạo client có khả năng chọn instance khi Spring Cloud LoadBalancer và nguồn discovery được cấu hình. Chính sách retry phải được kích hoạt phù hợp với version/integration và kiểm thử bằng các attempt thực.

Nếu cần đặt deadline tổng cho pipeline, có thể áp dụng `.timeout(Duration.ofSeconds(...))` ở tầng gọi thích hợp. Không tự thêm `retryWhen(...)` và đồng thời bật LoadBalancer retry mà chưa tính lại số attempt tối đa, vì hai tầng retry có thể chồng lên nhau.

## 18. RestClient và OpenFeign có gì khác?

Với `RestClient`, thường cấu hình `@LoadBalanced RestClient.Builder` để chọn instance theo service ID. Đường xử lý là **blocking**; hỗ trợ retry phụ thuộc các thành phần Spring Retry và tích hợp đang sử dụng.

Với OpenFeign, `@FeignClient(name = "inventory-service")` có thể sử dụng Spring Cloud LoadBalancer khi không có URL vật lý ghi đè. Tuy nhiên, **Retryer của OpenFeign và retry của Spring Cloud LoadBalancer không phải cùng một cơ chế**. Ở nhiều bản Spring Cloud OpenFeign, `Retryer.NEVER_RETRY` là mặc định cho Feign; không nên suy diễn rằng cấu hình LoadBalancer tự tạo mọi lần Feign retry theo cách mong muốn.

| Client | Cách chỉ định service ID | Điểm cần xác minh khi retry |
| --- | --- | --- |
| RestClient | HTTP URL qua builder `@LoadBalanced` | Retry integration, Spring Retry nếu cần, bean/transport, policy |
| WebClient | HTTP URL qua builder `@LoadBalanced` | Reactor retry/filter, request context, tránh double retry |
| OpenFeign | `@FeignClient(name = "...")`, không có URL vật lý | Feign Retryer, LoadBalancer integration, exception/status policy |

Khi nghi ngờ retry-aware supplier không được dùng, cần xác nhận **HTTP client thực tế có đi qua Spring Cloud LoadBalancer**. Một Feign client được cấu hình `url = "http://10.0.1.11:8080"` chẳng hạn sẽ không dùng việc lựa chọn replica theo service ID như trường hợp khai báo name và không có URL cố định.

## 19. Quan sát retry-aware filtering qua từng attempt

Để xác nhận cấu hình hoạt động, nên ghi log với trace ID và attempt index, nhưng phải phân biệt nguồn dữ liệu:

```text
traceId=f31a... serviceId=inventory-service attempt=1
discoveryCandidates=[A,B,C] selected=A
httpResult=CONNECT_REFUSED

traceId=f31a... retryAllowed=true remainingBudgetMs=1450
traceId=f31a... serviceId=inventory-service attempt=2 previous=A
discoveryCandidates=[A,B,C] retryEligibleCandidates=[B,C]
selected=C httpStatus=200
businessOutcome=SUCCESS
```

Các tên log trong ví dụ là **đề xuất tự thiết kế**, không phải log format mặc định Spring Cloud phát ra. Muốn có những trường này, ứng dụng có thể dùng kết hợp instrumentation của supplier chain, các callback của `LoadBalancerLifecycle`, HTTP client và tracing.

Những thông tin quan trọng:

1. **Trước lọc:** discovery/supplier nguồn nhìn thấy những replica nào?
2. **Sau lọc:** retry-aware supplier đã loại previous instance hay chưa?
3. **Selected:** LoadBalancer đã chọn địa chỉ nào cho attempt hiện tại?
4. **Outcome:** exception/HTTP status là gì; request có thực sự được gửi hay không?
5. **Retry:** vì sao được phép thử lại và còn bao nhiêu lần/thời gian?
6. **Kết quả cuối:** business request thành công sau mấy attempt, latency end-to-end là bao nhiêu?

Không log token, cookie, request body chứa dữ liệu nhạy cảm hoặc các ID riêng tư. Khi tạo metric, tránh dùng danh sách instance hoặc URL động làm label có cardinality cao; nên tách service ID, outcome và số attempt thành những trường được kiểm soát.

## 20. Ma trận kiểm thử một supplier nhận biết retry

Để kiểm tra có thể dùng danh sách instance giả từ `SimpleDiscoveryClient`, dựng nhiều HTTP server nhỏ hoặc một harness mock HTTP có khả năng làm một replica trả lỗi.

| Tình huống | Kỳ vọng cần kiểm tra |
| --- | --- |
| Attempt đầu, không có previous | Supplier không loại instance vì chưa có previous context |
| Previous=A, candidates `[A,B,C]` | Khi policy tránh previous áp dụng, danh sách cho lần chọn mới không chứa A |
| Previous=A, candidates `[A]` | Fallback có thể giữ A; không tự coi đó là lỗi cấu hình |
| Previous=A, candidates `[B,C]` | Danh sách giữ B,C; A đã vắng từ nguồn |
| Candidates rỗng | Không có đích hợp lệ, retry không tự tạo instance |
| Retry chưa bật hoặc lỗi không cho retry | Không có attempt thứ hai dù có retry-aware supplier bean |
| Một decorator làm mất `Request` context | Phát hiện previous không tới được filter, có thể chọn lại A |
| Zone filter chỉ giữ A | Kiểm tra tương tác zone với retry-aware; không mặc định failover sang C |
| Attempt 1=A lỗi, attempt 2=B lỗi | Attempt 3 không mặc định nhớ A; quan sát tất cả selected instance |
| Lời gọi `POST` bị timeout sau khi server ghi | Chứng minh server xử lý idempotency; retry không tạo tác dụng phụ lần hai |

Không nên kiểm thử bằng cách chỉ gửi hai request bình thường rồi đếm số lần A xuất hiện. Request mới **khác** retry của cùng một business request; yêu cầu thử nghiệm phải kích hoạt đường retry với context previous instance thực sự.

### 20.1. Các bước thực hành cụ thể

1. Chạy 3 mock instance trả response có field `instanceId`.
2. Đăng ký các instance dưới service ID `inventory-service`.
3. Cấu hình Spring Cloud LoadBalancer và chính sách retry phù hợp client.
4. Làm A trả lỗi kết nối hoặc `503` được policy cho retry.
5. Gửi một request `GET` từ caller, ghi trace ID và attempt index.
6. Xác minh attempt đầu chọn A (có thể cần điều khiển bộ chọn trong test).
7. Xác minh retry chọn B hoặc C nếu còn đủ điều kiện.
8. Đổi thành chỉ có A và xác nhận fallback/giới hạn retry.
9. Tắt `avoid-previous-instance` để so sánh hành vi, **không giả định** lần nào cũng chọn lại A.
10. Kiểm tra tổng deadline, retry count và tải phát sinh do retry.

Kiểm thử cần cô lập giá trị ngẫu nhiên, thứ tự Round Robin, số request đồng thời và độ mới của cache để kết quả không phụ thuộc vào may rủi.

## 21. Quy trình chẩn đoán khi retry cứ quay lại bản sao lỗi

Nếu log cho thấy attempt đầu chọn A, retry vẫn chọn A nhiều lần, hãy kiểm tra theo thứ tự:

1. **Có phải là retry không?** Hai request độc lập có trace khác nhau có thể chọn cùng A một cách bình thường.
2. **Retry được thực hiện ở đâu?** Spring Cloud LoadBalancer, Feign Retryer, Reactor `retryWhen`, gateway hay một lớp nghiệp vụ riêng?
3. **Có lần lựa chọn mới hay không?** Same-instance retry theo chủ đích không đòi chọn lại; next-instance retry mới cần xét supplier.
4. **Client có dùng LoadBalancer không?** URL vật lý cố định hoặc builder không có `@LoadBalanced` có thể bỏ qua tầng lựa chọn.
5. **Supplier chain có retry-aware decorator không?** Kiểm tra auto-configuration, dependency và property tránh previous.
6. **Context có được truyền đúng?** Lớp nào gọi `delegate.get()` thay vì `delegate.get(request)` khi cần?
7. **Còn replica thay thế không?** Zone, health, hint, sticky hoặc cache có lọc danh sách chỉ còn A?
8. **Instance identity có ổn định không?** Instance ID/metadata bất thường có ảnh hưởng phép so khớp?
9. **Không có double retry chứ?** Nhiều policy có thể trộn attempt khác ngữ cảnh và làm khó hiểu kết quả.
10. **Deadline/idempotency đã đúng chưa?** Đừng tăng retry chỉ để che lỗi một replica chưa được loại khỏi topology.

Nếu discovery còn A dù A chết, điều tra deregistration/lease và độ trễ cache. Nếu retry-aware filter hoạt động nhưng tất cả request vẫn thất bại, cần nhìn tải, kết nối và sức khỏe của các replica khác. Nếu chỉ có một instance, retry-aware supplier không thể biến một topology đơn replica thành đa replica.

## 22. Các giới hạn cần nhớ và thực hành vận hành an toàn

- **Không phải bảo đảm tránh 100%:** nếu chỉ có một ứng viên, previous instance có thể được giữ.
- **Không phải lịch sử toàn bộ instance lỗi:** nó chủ yếu xét instance được chọn ngay trước, không mặc định lưu tất cả các attempt đã lỗi.
- **Không tự phát retry:** việc thử lại còn phụ thuộc retry policy, exception/status và HTTP method.
- **Không tự lọc replica lỗi khỏi registry:** supplier không thay discovery/health check.
- **Không tự chữa lỗi dữ liệu stale:** cache và registry cũ vẫn có thể tiếp tục đưa A vào danh sách các request khác.
- **Không bảo đảm retry an toàn cho POST:** phải thiết kế idempotency nếu muốn gửi lại thao tác ghi.
- **Không thay thế backoff/deadline:** tránh A nhưng dồn request vào B/C liên tục vẫn có thể gây quá tải.
- **Không nhất thiết hành vi giống nhau giữa RestClient, WebClient, OpenFeign:** cần xác minh integration được sử dụng và chính sách đang bật.
- **Không nhầm log của lựa chọn với response:** `ServiceInstance` được chọn không có nghĩa server đã nhận HTTP request.

### 22.1. Nguồn tham khảo chính thức

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): mô tả load-balanced retry và `RetryAwareServiceInstanceListSupplier`.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): nhóm property `spring.cloud.loadbalancer.retry.*`.
- [Spring Cloud Commons – LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): cơ chế supplier, cache, health check và các filter.
  
Khi triển khai, nên đối chiếu tài liệu với **phiên bản Spring Cloud thực sự được quản lý bởi BOM**, vì auto-configuration và điều kiện kích hoạt retry có thể thay đổi giữa các release train.

## 23. Câu hỏi tự kiểm tra

1. `RetryAwareServiceInstanceListSupplier` khác retry policy ở trách nhiệm nào?
2. Tại sao Round Robin không tự bảo đảm retry sẽ tránh instance vừa lỗi?
3. Dữ liệu quan trọng nào của attempt trước cần được chuyển qua `ServiceInstanceListSupplier#get(Request)`?
4. Khi previous=A và candidates là `[A,B,C]`, danh sách mới dự kiến có gì?
5. Nếu chỉ có A, vì sao supplier có thể tiếp tục cung cấp A?
6. `avoid-previous-instance: false` có đồng nghĩa tắt retry không?
7. Tại sao attempt 3 sau khi A và B lần lượt lỗi vẫn có thể nhìn thấy A?
8. Vì sao caching danh sách đã lọc theo request có thể khiến retry hoặc sticky session hoạt động sai?
9. Trong ví dụ caller ở `zone-a` nhưng chỉ còn A trong zone đó, tại sao retry-aware không chắc chọn C ở `zone-b`?
10. Vì sao retry từ `POST` read timeout sang một instance khỏe khác vẫn có thể gây duplicate?
11. Làm sao phân biệt hai business request đều chọn A với một business request retry chọn lại A?
12. Khi debug retry không đổi instance, nên kiểm tra những tầng nào trước khi thay thuật toán LoadBalancer?

**Kết luận:** Spring Cloud LoadBalancer dùng `RetryAwareServiceInstanceListSupplier` để **giảm khả năng chọn lại replica vừa được chọn ở attempt trước khi có phương án khác**. Cơ chế này chỉ hoạt động đúng khi integration retry tạo lượt lựa chọn mới, chuyển được request context và danh sách ứng viên còn lựa chọn thay thế. Hãy phối hợp nó với discovery/health check, timeout, backoff, deadline, giới hạn attempt và idempotency để retry góp phần phục hồi thay vì khuếch đại lỗi của hệ thống.
