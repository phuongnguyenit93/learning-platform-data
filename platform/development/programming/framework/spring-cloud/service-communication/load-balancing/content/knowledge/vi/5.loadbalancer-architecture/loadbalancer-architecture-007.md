# Response và trường hợp không chọn được bản sao

Spring Cloud LoadBalancer chọn một **ServiceInstance** phù hợp cho mỗi lần gọi dịch vụ bằng service ID. Kết quả lựa chọn có thể chứa instance được chọn hoặc cho biết hiện không có instance nào khả dụng. Ứng dụng cần xử lý hai kết quả này rõ ràng để tránh lỗi khó hiểu, retry vô ích hoặc trả response sai cho caller.

Trong bài này, “bản sao” được hiểu là một instance đang cung cấp cùng một service, không phải bản sao dữ liệu của cơ sở dữ liệu.

Trong module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**, bài học này nối kiến trúc lựa chọn instance với hành vi thực tế của **RestClient**, **WebClient** và **OpenFeign**. Trọng tâm là phân biệt response của LoadBalancer với HTTP response từ dịch vụ đích, hiểu vì sao không chọn được instance và thiết kế cách phản hồi có thể quan sát, phục hồi an toàn.

## 1. Hai loại response trong một lần gọi dịch vụ

Khi ứng dụng gọi một URL dùng service ID, chẳng hạn `http://catalog-service/api/items/42`, có hai giai đoạn khác nhau:

1. **Chọn ServiceInstance**: Spring Cloud LoadBalancer tìm danh sách instance của `catalog-service` và áp dụng chính sách lựa chọn.
2. **Gửi HTTP request**: HTTP client gửi request đến địa chỉ host và port của instance đã chọn, sau đó nhận HTTP response hoặc lỗi giao tiếp.

Vì vậy, từ “response” trong ngữ cảnh này có thể chỉ hai đối tượng khác nhau:

- **LoadBalancer response** là kết quả nội bộ của bước chọn instance. Kết quả có thể chứa một `ServiceInstance`, hoặc không có server nào được chọn.
- **HTTP response** là phản hồi giao thức từ dịch vụ đích, ví dụ status `200`, `404` hoặc `503`, cùng header và body.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Ứng dụng
    participant LB as Spring Cloud LoadBalancer
    participant SD as Instance supplier / Discovery
    participant HTTP as HTTP client
    participant S as Service instance

    App->>LB: Chọn instance theo catalog-service
    LB->>SD: Lấy danh sách instance
    SD-->>LB: Danh sách ServiceInstance
    alt Có instance phù hợp
        LB-->>App: Response có ServiceInstance
        App->>HTTP: Gửi request đến host:port đã chọn
        HTTP->>S: HTTP request
        S-->>HTTP: HTTP response (2xx/4xx/5xx)
        HTTP-->>App: Kết quả HTTP hoặc lỗi
    else Không có instance phù hợp
        LB-->>App: EmptyResponse / không có server
        Note over App,HTTP: Request HTTP chưa được gửi đến dịch vụ đích
    end
~~~

Nếu không chọn được instance, ứng dụng chưa có địa chỉ đích để gửi request. Do đó, không tồn tại HTTP status do dịch vụ đích trả về cho lần gọi đó. Đây là lỗi ở bước phân giải hoặc lựa chọn instance, khác với trường hợp một instance đã nhận request nhưng trả về `503 Service Unavailable`.

## 2. Response của Spring Cloud LoadBalancer

API lựa chọn instance của Spring Cloud LoadBalancer biểu diễn kết quả bằng kiểu `Response<ServiceInstance>`. Hai kết quả phổ biến là:

| Kiểu kết quả | Ý nghĩa |
|---|---|
| `DefaultResponse<ServiceInstance>` | Có instance được chọn; có thể lấy instance qua `getServer()` |
| `EmptyResponse` | Không có instance được chọn; `hasServer()` trả về `false` |

Với bộ chọn vòng tròn `RoundRobinLoadBalancer`, khi danh sách instance rỗng, LoadBalancer trả về kết quả rỗng thay vì chọn một địa chỉ không tồn tại. Khi có instance, nó chọn một phần tử trong danh sách theo vị trí vòng tròn và trả về response chứa instance đó.

Một đoạn mã minh họa cách kiểm tra kết quả:

~~~java
Mono<Response<ServiceInstance>> selection =
    loadBalancer.choose(new DefaultRequest<>());

return selection.flatMap(response -> {
    if (!response.hasServer()) {
        return Mono.error(new IllegalStateException(
            "No instances available for catalog-service"
        ));
    }

    ServiceInstance instance = response.getServer();
    return Mono.just(instance);
});
~~~

Đây là ví dụ ở mức API để làm rõ cách kiểm tra kết quả; trong ứng dụng thông thường, các tích hợp `@LoadBalanced` của HTTP client sẽ gọi LoadBalancer thay cho code nghiệp vụ. Nếu tự viết bộ chọn hoặc adapter, luôn kiểm tra `hasServer()` trước khi sử dụng `getServer()`.

Không nên giả định `getServer()` luôn khác `null`. Một bộ chọn tùy biến phải tuân thủ hợp đồng response và biểu diễn trường hợp không có instance theo cách mà lớp gọi có thể nhận biết.

## 3. Khi nào LoadBalancer không chọn được instance?

Kết quả rỗng thường xuất hiện khi danh sách instance đầu vào rỗng hoặc các bộ lọc không để lại instance nào. Có nhiều nguyên nhân khác nhau.

### Dịch vụ chưa đăng ký hoặc chưa được phát hiện

Service discovery có thể chưa nhận được đăng ký của dịch vụ đích. Tình huống này thường gặp khi:

- Dịch vụ đích chưa khởi động hoặc chưa đăng ký vào registry.
- Instance vừa khởi động và chưa xuất hiện trong lần truy vấn discovery tiếp theo.
- Instance đã dừng nhưng registry chưa kịp xóa đăng ký cũ.
- Ứng dụng gọi sai service ID, khác tên đăng ký hoặc khác quy ước viết hoa/thường của registry.
- Các ứng dụng đang dùng namespace, partition hoặc môi trường discovery khác nhau.

Cần xác minh service ID trong URL hoặc annotation client trùng với tên dịch vụ được đăng ký, sau đó kiểm tra danh sách instance mà discovery client trả về.

### Danh sách có instance nhưng bộ lọc loại bỏ tất cả

Nguồn discovery có thể trả về nhiều instance, nhưng chuỗi `ServiceInstanceListSupplier` có thể lọc chúng trước khi bộ chọn nhận danh sách.

Ví dụ:

- Bộ lọc theo zone chỉ giữ instance ở một vùng nhất định.
- Bộ lọc theo hint hoặc metadata không tìm thấy instance có thuộc tính phù hợp.
- Bộ lọc theo request chỉ giữ instance đáp ứng điều kiện định tuyến.
- Health check đánh dấu tất cả instance là không khỏe mạnh.
- Chính sách ưu tiên instance hoặc cùng instance không có ứng viên hợp lệ trong ngữ cảnh hiện tại.

Cần quan sát danh sách trước và sau từng bước lọc để xác định nơi số lượng instance giảm về không. Không nên chỉ nhìn vào registry rồi kết luận LoadBalancer chắc chắn có ứng viên, vì danh sách cuối cùng mà bộ chọn nhận có thể đã khác.

### Health check chưa thành công

Nếu cấu hình `HealthCheckServiceInstanceListSupplier`, LoadBalancer có thể dựa vào kết quả health check để chỉ cung cấp các instance đang khỏe mạnh. Khi tất cả endpoint health check thất bại, timeout hoặc trả trạng thái không được chấp nhận, danh sách sau lọc có thể rỗng.

Cần kiểm tra:

- Đường dẫn health endpoint có đúng với ứng dụng đích không.
- Endpoint có được truy cập từ mạng của ứng dụng gọi không.
- Health check có timeout quá ngắn hoặc chu kỳ kiểm tra chưa đủ để cập nhật trạng thái không.
- Ứng dụng đích có thật sự sẵn sàng nhận traffic khi health endpoint trả trạng thái khỏe mạnh không.

Health check là một tín hiệu vận hành, không phải bảo đảm tuyệt đối rằng request nghiệp vụ tiếp theo sẽ thành công. Instance có thể chuyển trạng thái sau lần kiểm tra gần nhất.

### Cache hoặc trạng thái discovery chưa được cập nhật

Nếu danh sách instance được cache, thay đổi đăng ký có thể chưa xuất hiện ngay trong lần lựa chọn tiếp theo. Cache giúp giảm số lần truy vấn discovery nhưng cũng tạo độ trễ cập nhật.

Cần xem xét chu kỳ refresh, thời gian sống của cache, cơ chế cập nhật registry và thời điểm instance mới đăng ký hoặc bị gỡ. Tránh giảm thời gian cache một cách tùy tiện vì có thể làm tăng tải lên discovery server.

## 4. Phân biệt không có instance với lỗi HTTP

Các tình huống sau xảy ra ở những giai đoạn khác nhau và cần cách xử lý khác nhau:

| Tình huống | Giai đoạn | Có HTTP response từ dịch vụ đích? | Hướng điều tra |
|---|---|---|---|
| Không có ServiceInstance | Chọn instance | Không | Discovery, service ID, supplier và filter |
| Không kết nối được host/port | Thiết lập kết nối | Không | Mạng, DNS, port, instance đã dừng |
| Connect/response timeout | Giao tiếp HTTP | Có thể không có response hoàn chỉnh | Timeout, tải server, mạng và connection pool |
| HTTP `404` | Dịch vụ đã nhận request | Có | Path, resource và hợp đồng API |
| HTTP `503` | Dịch vụ đã nhận request hoặc gateway trả lỗi | Có | Sức khỏe dịch vụ, quá tải, dependency |
| HTTP `500` | Xử lý phía server | Có | Exception và log của dịch vụ đích |

Một HTTP `503` có thể được trả bởi gateway hoặc bởi chính dịch vụ đích. Nó cũng có thể được ứng dụng tạo ra khi chuyển lỗi “không có instance” thành phản hồi HTTP cho caller. Khi điều tra, cần xác định thành phần nào thực sự tạo ra status đó.

Điểm cần nhớ: `EmptyResponse` là kết quả của bước chọn instance, còn `503` là HTTP status. Không nên ghi log hai trường hợp này bằng cùng một thông điệp kiểu “service trả 503” nếu request thực tế chưa từng đến service.

## 5. Hành vi của các HTTP client khi không có instance

Các client được gắn `@LoadBalanced` sử dụng tích hợp của Spring Cloud để phân giải service ID. Khi không có instance, lỗi thường xuất hiện trước khi HTTP request đến dịch vụ đích. Kiểu exception cụ thể có thể khác nhau theo client, bộ lọc, retry và phiên bản Spring Cloud.

### RestClient

Ví dụ cấu hình builder:

~~~java
@Configuration
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Lời gọi dùng service ID:

~~~java
ItemDto item = restClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);
~~~

Khi có instance, request được gửi đến instance đã chọn. Khi không có instance, bước load balancing có thể phát sinh lỗi trước khi nhận được HTTP response. Vì vậy, xử lý `onStatus(...)` của `retrieve()` chỉ xử lý status từ một HTTP response; nó không thay thế việc xử lý lỗi chọn instance hoặc lỗi kết nối.

Có thể bắt lỗi ở ranh giới gọi dịch vụ và chuyển thành exception nghiệp vụ rõ nghĩa:

~~~java
public ItemDto getItem(String itemId) {
    try {
        return restClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .body(ItemDto.class);
    }
    catch (RestClientException | IllegalStateException ex) {
        throw new CatalogUnavailableException(
            "Cannot retrieve item from catalog-service", ex
        );
    }
}
~~~

Ví dụ trên minh họa việc xử lý các lỗi client phổ biến và lỗi không có instance thường được báo bằng `IllegalStateException` trong luồng blocking. Kiểu exception cụ thể còn phụ thuộc phiên bản và cấu hình retry; trong hệ thống thực tế, nên phân loại chi tiết hơn nếu caller cần phân biệt lỗi HTTP 4xx, 5xx, timeout và không có instance.

### WebClient

WebClient biểu diễn quá trình gọi bằng publisher:

~~~java
Mono<ItemDto> item = webClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class);
~~~

Nếu LoadBalancer không tìm được instance, pipeline kết thúc bằng tín hiệu lỗi. Lỗi đó có thể được xử lý bằng các toán tử Reactor:

~~~java
public Mono<ItemDto> getItem(String itemId) {
    return webClient.get()
        .uri("http://catalog-service/api/items/{id}", itemId)
        .retrieve()
        .bodyToMono(ItemDto.class)
        .onErrorMap(
            ex -> isCatalogUnavailable(ex),
            ex -> new CatalogUnavailableException(
                "catalog-service has no available instance", ex
            )
        );
}
~~~

Hàm `isCatalogUnavailable` là hàm phân loại lỗi do ứng dụng định nghĩa; cần kiểm tra chuỗi cause và loại exception thực tế của phiên bản đang dùng. Không nên biến mọi lỗi thành “không có instance”, vì lỗi giải mã, lỗi HTTP hoặc lỗi lập trình cần được giữ đúng bản chất.

Nếu dùng `retrieve().onStatus(...)`, phần `onStatus` xử lý status HTTP như `404` hoặc `503`. Lỗi phát sinh trước khi có response HTTP vẫn đi theo nhánh lỗi của publisher.

### OpenFeign

OpenFeign khai báo client qua interface:

~~~java
@FeignClient(name = "catalog-service")
public interface CatalogClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String itemId);
}
~~~

Khi có instance, Spring Cloud LoadBalancer chọn đích cho lời gọi Feign. Nếu không có instance, lời gọi có thể thất bại trong lớp tích hợp LoadBalancer trước khi Feign nhận được HTTP response. Nếu dịch vụ đích đã trả lỗi HTTP, Feign thường biểu diễn status lỗi bằng exception thuộc hệ sinh thái Feign, chẳng hạn `FeignException`.

Có thể dùng một lớp service để chuyển lỗi kỹ thuật thành lỗi nghiệp vụ mà controller hiểu được:

~~~java
@Service
class CatalogService {

    private final CatalogClient client;

    CatalogService(CatalogClient client) {
        this.client = client;
    }

    ItemDto getItem(String itemId) {
        try {
            return client.getItem(itemId);
        }
        catch (RuntimeException ex) {
            throw new CatalogUnavailableException(
                "Catalog service call failed", ex
            );
        }
    }
}
~~~

Đoạn mã chỉ minh họa ranh giới chuyển đổi lỗi. Trong ứng dụng thật, hãy bắt các loại exception đã xác định và giữ nguyên lỗi nghiệp vụ như `404` nếu caller cần biết item không tồn tại.

## 6. Thiết kế phản hồi khi không chọn được instance

Cách phản hồi phụ thuộc vai trò của dịch vụ trong nghiệp vụ.

### Dịch vụ bắt buộc để hoàn tất nghiệp vụ

Nếu không có catalog service thì không thể xác nhận đơn hàng, ứng dụng nên dừng luồng nghiệp vụ và trả lỗi phù hợp. Có thể ánh xạ lỗi nội bộ sang `503 Service Unavailable` ở API gateway hoặc controller vì hệ thống tạm thời không thể hoàn thành yêu cầu.

Response nên có cấu trúc ổn định, ví dụ:

~~~json
{
  "type": "https://api.example.com/problems/dependency-unavailable",
  "title": "Dịch vụ phụ thuộc tạm thời không khả dụng",
  "status": 503,
  "detail": "Không thể xử lý yêu cầu vì catalog-service hiện không có instance khả dụng.",
  "service": "catalog-service"
}
~~~

Không nên đưa hostname nội bộ, stack trace, thông tin registry hoặc chi tiết hạ tầng nhạy cảm vào response công khai. Có thể đưa mã lỗi ổn định để caller và hệ thống giám sát phân loại.

### Dịch vụ tùy chọn hoặc có dữ liệu thay thế

Nếu một dependency chỉ cung cấp dữ liệu bổ sung, ứng dụng có thể chọn phương án suy giảm chức năng:

- Trả dữ liệu đã cache với thông tin thời điểm cập nhật nếu nghiệp vụ cho phép dữ liệu cũ.
- Bỏ phần thông tin tùy chọn và trả kết quả chính.
- Trả trạng thái “đang cập nhật” nếu nghiệp vụ có thể hoàn tất bất đồng bộ.
- Dùng một nguồn dự phòng đã được thiết kế và kiểm soát trước.

Fallback phải thể hiện rõ giới hạn dữ liệu. Ví dụ, dữ liệu giá sản phẩm cũ có thể không an toàn để dùng cho thanh toán; một ảnh đại diện cũ có thể vẫn chấp nhận được. Không nên dùng cùng một chính sách fallback cho mọi dependency.

### Không trả dữ liệu giả để che lỗi

Không nên trả một DTO rỗng hoặc giá trị mặc định trông như thành công nếu nghiệp vụ cần dữ liệu thật. Caller có thể tiếp tục xử lý dựa trên thông tin sai, dẫn đến lỗi khó truy vết hơn lỗi ban đầu.

Fallback cần có hợp đồng rõ ràng, chẳng hạn một trạng thái degraded, nguồn dữ liệu và thời điểm cập nhật. Nếu không thể bảo đảm tính đúng đắn của kết quả, hãy trả lỗi có thể nhận biết.

## 7. Retry khi không có instance

Retry có thể giúp khi instance vừa đăng ký, discovery vừa cập nhật hoặc một instance tạm thời mất kết nối. Tuy nhiên, retry không phải giải pháp cho mọi trường hợp không có instance.

Cần phân biệt:

- **Danh sách rỗng**: retry ngay thường vẫn nhận danh sách rỗng nếu registry hoặc supplier chưa thay đổi.
- **Một instance vừa lỗi**: lần thử sau có thể chọn instance khác nếu danh sách còn ứng viên và retry strategy được cấu hình phù hợp.
- **Lỗi HTTP có thể phục hồi**: chỉ retry khi status và thao tác nghiệp vụ cho phép.
- **Lỗi request không idempotent**: retry có thể tạo tác dụng phụ lặp lại nếu server đã xử lý request nhưng response bị mất.

Spring Cloud LoadBalancer có hỗ trợ retry cho các tích hợp client. Cấu hình và hành vi cụ thể phụ thuộc phiên bản, loại client và retry policy đang dùng. Một số cấu hình có thể sử dụng supplier nhận biết instance đã thử để tránh chọn lại cùng instance trong lần retry tiếp theo. Cần xác minh chính sách này trong ứng dụng thay vì giả định mọi retry tự động chuyển sang một instance khác.

Một chính sách retry nên có:

1. Số lần thử tối đa nhỏ và được giới hạn.
2. Tổng deadline không vượt quá thời gian caller cho phép.
3. Backoff và jitter để tránh nhiều client retry cùng lúc.
4. Phân loại lỗi được retry; không retry tùy tiện lỗi 4xx hoặc lỗi nghiệp vụ.
5. Bảo đảm idempotency hoặc dùng idempotency key cho thao tác ghi.
6. Giới hạn retry ở các lớp để tránh retry lồng nhau giữa HTTP client, LoadBalancer và gateway.

Nếu tất cả instance đều vắng mặt hoặc không khỏe mạnh, retry chỉ kéo dài thời gian thất bại và tăng tải. Trong trường hợp đó, fail fast có kiểm soát thường giúp hệ thống bảo vệ thread, connection và tài nguyên của caller tốt hơn.

## 8. Quan sát và chẩn đoán lỗi lựa chọn instance

Khi một lần gọi thất bại, log và metric cần giúp trả lời bốn câu hỏi: ứng dụng định gọi service ID nào, supplier cung cấp bao nhiêu instance, LoadBalancer có chọn được instance không, và lỗi xảy ra trước hay sau khi gửi HTTP request.

Nên ghi nhận các trường thông tin sau:

| Trường | Mục đích |
|---|---|
| `serviceId` | Xác định dịch vụ logic được gọi |
| `traceId` / `correlationId` | Nối log giữa các dịch vụ |
| Số lượng instance trước/sau filter | Tìm bước làm danh sách trở thành rỗng |
| Instance được chọn | Xác định host/port hoặc metadata đã chọn |
| Loại kết quả LoadBalancer | Có instance hay EmptyResponse |
| Thời gian chọn instance | Phát hiện discovery hoặc supplier chậm |
| HTTP status | Phân biệt response từ server với lỗi trước HTTP |
| Exception class và cause | Phân loại lỗi chính xác |
| Retry attempt | Biết số lần thử và instance đã thử |

Không ghi body nhạy cảm, token, thông tin xác thực hoặc dữ liệu cá nhân vào log. Nếu log địa chỉ instance, cần tuân thủ chính sách bảo mật và quyền truy cập log của hệ thống.

Có thể tổ chức quy trình điều tra như sau:

~~~mermaid
flowchart TD
    A["HTTP client call thất bại"] --> B{"Có instance được chọn?"}
    B -->|Không| C["Kiểm tra service ID và discovery"]
    C --> D["Kiểm tra supplier, cache và filter"]
    D --> E["Kiểm tra health check / metadata / zone"]
    E --> F["Xác định vì sao danh sách rỗng"]
    B -->|Có| G{"Đã nhận HTTP response?"}
    G -->|Không| H["Kiểm tra DNS, kết nối, timeout và pool"]
    G -->|Có| I["Kiểm tra status, body và log server"]
    F --> J["Khôi phục đăng ký hoặc điều chỉnh cấu hình"]
    H --> K["Khắc phục mạng hoặc tài nguyên"]
    I --> L["Khắc phục lỗi endpoint hoặc nghiệp vụ"]
~~~

Khi cần theo dõi sâu hơn, có thể sử dụng hook vòng đời của LoadBalancer như `LoadBalancerLifecycle` để quan sát lúc bắt đầu chọn instance, lúc bắt đầu gửi request và lúc hoàn tất. Kết hợp log có correlation ID với metric về số lần chọn thành công, không có instance, retry, timeout và phân bố request sẽ giúp nhận biết sớm một dịch vụ đang mất khả năng phục vụ.

## 9. Checklist cấu hình và kiểm thử

Trước khi đưa tích hợp vào môi trường chạy thật, hãy kiểm tra:

- Service ID trong URL hoặc `@FeignClient(name = ...)` trùng với tên đăng ký trong discovery.
- Discovery trả về đúng danh sách instance cho ứng dụng gọi.
- Supplier và các filter không loại bỏ toàn bộ ứng viên ngoài ý muốn.
- Health endpoint có thể truy cập và phản ánh trạng thái sẵn sàng thực tế.
- Cache và chu kỳ refresh phù hợp với tốc độ thay đổi instance.
- Client xử lý được trường hợp không có instance và phân biệt với lỗi HTTP.
- Timeout, retry, backoff và deadline được giới hạn.
- Fallback phù hợp với yêu cầu đúng đắn của dữ liệu nghiệp vụ.
- Log và metric phân biệt lỗi chọn instance, lỗi kết nối và lỗi HTTP.

Có thể kiểm thử ít nhất các tình huống sau:

| Kịch bản | Kết quả cần quan sát |
|---|---|
| Discovery trả danh sách rỗng | LoadBalancer không chọn instance; ứng dụng trả lỗi phụ thuộc có kiểm soát |
| Một instance đang chạy | Request được gửi đến instance đó |
| Nhiều instance đang chạy | Request được phân phối theo chính sách lựa chọn đã cấu hình |
| Tất cả health check thất bại | Danh sách sau health filter rỗng và lỗi được phân loại đúng |
| Instance dừng ngay sau khi được chọn | Ghi nhận lỗi kết nối; retry chỉ diễn ra theo policy |
| Server trả `404` | Ứng dụng giữ đúng ý nghĩa resource không tồn tại |
| Server trả `503` | Phân biệt status do server/gateway trả với lỗi không có instance |
| Discovery cập nhật sau khi instance khởi động | Lần gọi sau có thể chọn instance mới khi supplier refresh |

Không nên chỉ kiểm thử đường đi thành công. Trường hợp danh sách rỗng là một phần bình thường của vòng đời hệ thống phân tán: dịch vụ có thể khởi động chậm, bị gỡ khỏi registry, bị đánh dấu unhealthy hoặc tạm thời mất kết nối. Khi các trạng thái đó được biểu diễn và xử lý rõ ràng, ứng dụng có thể trả lỗi đúng nghĩa, retry có giới hạn và phục hồi khi instance khả dụng trở lại.

