# Phân biệt dữ liệu chung với dữ liệu phụ thuộc từng yêu cầu

Trong Spring Cloud LoadBalancer, **chuỗi cung cấp bản sao** (`ServiceInstanceListSupplier` chain) thường cần xử lý hai loại thông tin:

1. **Dữ liệu dùng chung cho các yêu cầu đến cùng một dịch vụ:** danh sách bản sao được discovery cung cấp, địa chỉ mạng, trạng thái sức khỏe hoặc metadata của từng `ServiceInstance`.
2. **Dữ liệu riêng của một yêu cầu:** hint trong HTTP header, phiên bản API mà request mong muốn, cookie sticky session hoặc tiêu chí định tuyến được tạo từ ngữ cảnh request.

Hai loại dữ liệu này có vòng đời và cách cache khác nhau. Nếu lọc theo request rồi đưa kết quả vào cache dùng chung, yêu cầu tiếp theo có thể nhìn thấy danh sách ứng viên bị giới hạn bởi yêu cầu trước đó. Ngược lại, nếu chỉ cung cấp một danh sách cố định và bỏ qua ngữ cảnh request, các chính sách như canary routing hay sticky session có thể hoạt động sai.

Bài này giải thích cách xác định dữ liệu nào được chia sẻ, dữ liệu nào phải tính theo từng request và cách sắp xếp supplier để việc chọn `ServiceInstance` ổn định.

## 1. Một service ID, nhiều danh sách ứng viên có thể khác nhau

Giả sử dịch vụ `catalog-service` có ba bản sao:

| Instance ID | URI | Metadata `hint` |
|---|---|---|
| `catalog-stable-1` | `http://10.0.1.11:8080` | `stable` |
| `catalog-stable-2` | `http://10.0.1.12:8080` | `stable` |
| `catalog-canary-1` | `http://10.0.1.21:8080` | `canary` |

Nguồn discovery trả về danh sách chung:

~~~text
catalog-service:
  [catalog-stable-1, catalog-stable-2, catalog-canary-1]
~~~

Tuy nhiên, một yêu cầu có header `X-SC-LB-Hint: stable` có thể được lọc thành hai instance stable, còn yêu cầu có `X-SC-LB-Hint: canary` có thể chỉ thấy `catalog-canary-1`.

~~~mermaid
flowchart TD
    D["Discovery: catalog-service"]
    C["Danh sách chung: stable-1, stable-2, canary-1"]
    A["Request A: hint=stable"]
    B["Request B: hint=canary"]
    F1["Ứng viên A: stable-1, stable-2"]
    F2["Ứng viên B: canary-1"]
    L1["LoadBalancer chọn một bản sao cho A"]
    L2["LoadBalancer chọn một bản sao cho B"]
    D --> C
    C --> A
    C --> B
    A --> F1
    B --> F2
    F1 --> L1
    F2 --> L2
~~~

**Danh sách gốc** giống nhau cho cả hai request tại cùng một thời điểm; **danh sách sau lọc** có thể khác vì ngữ cảnh mỗi request khác nhau. Đây là ranh giới chính khi thiết kế supplier chain.

## 2. Dữ liệu chung là gì?

“Dữ liệu chung” không nhất thiết là dữ liệu bất biến hoặc toàn cục cho cả ứng dụng. Trong bài này, nó là dữ liệu có thể sử dụng lại cho **nhiều request đến cùng một service ID** trong một khoảng thời gian.

Các ví dụ điển hình:

| Dữ liệu | Vì sao có thể dùng chung? | Khi nào thay đổi? |
|---|---|---|
| Danh sách `ServiceInstance` của `catalog-service` | Nhiều request cần cùng tập instance đã đăng ký | Scale up/down, đăng ký/hủy đăng ký, đồng bộ discovery |
| Host, port, URI của instance | Mô tả endpoint cụ thể | Instance được thay thế hoặc cập nhật đăng ký |
| Metadata `zone`, `hint`, `weight` trên instance | Thuộc tính được công bố cùng instance | Thay đổi triển khai hoặc metadata discovery |
| Kết quả health check | Có thể dùng để lọc các instance không khỏe cho nhiều request | Khi chu kỳ kiểm tra cho kết quả mới |
| Danh sách được cache theo service ID | Tránh truy vấn discovery lặp lại cho từng request | Cache hết hạn hoặc được làm mới |

Chẳng hạn, `catalog-stable-1` có metadata `hint=stable`. Giá trị này là **thuộc tính của instance**: nó mô tả instance thuộc nhóm nào. Nó không phải giá trị hint mà mọi request buộc phải sử dụng.

Dữ liệu dùng chung vẫn có thể trở nên cũ. Health check, registry và cache có thể nhìn thấy trạng thái instance ở các thời điểm khác nhau. Khi một instance đã dừng nhưng dữ liệu chưa được làm mới, danh sách chung vẫn có khả năng chứa endpoint không còn truy cập được.

### Định danh phạm vi chia sẻ

Trong Spring Cloud LoadBalancer, mỗi service ID thường có ngữ cảnh cấu hình LoadBalancer riêng. Vì vậy, danh sách instance của `catalog-service` không nên bị trộn với danh sách của `payment-service`. Ngay cả trong cùng một service ID, kết quả có thể khác giữa môi trường, namespace hoặc cấu hình discovery của các client.

Không nên hiểu “dùng chung” là “lưu trong một biến static cho mọi dịch vụ và mọi request”.

## 3. Dữ liệu phụ thuộc từng yêu cầu là gì?

Dữ liệu phụ thuộc request được xác định khi một lời gọi cụ thể được tạo ra và có thể khác giữa hai lời gọi liên tiếp tới cùng service ID.

| Tín hiệu theo request | Ví dụ | Cách dùng có thể có |
|---|---|---|
| Hint trong header | `X-SC-LB-Hint: canary` | Ưu tiên các instance có metadata `hint=canary` |
| API version được yêu cầu | `Accept-Version: 2` | Lọc instance phục vụ phiên bản tương ứng khi đã cấu hình tính năng |
| Cookie sticky session | Cookie chỉ instance trước đây | Cố gắng chọn lại instance phù hợp khi chính sách sticky được bật |
| Thông tin caller | Chính sách theo ứng dụng gọi hoặc mức ưu tiên | Chọn nhóm instance theo ngữ cảnh tin cậy của caller |
| Yêu cầu về vùng xử lý | Ví dụ một request cần xử lý trong khu vực nhất định | Lọc theo metadata phù hợp, nếu chính sách có hỗ trợ |

Những tín hiệu này **không tự động có hiệu lực** chỉ vì chúng xuất hiện trong HTTP request. Chúng cần được adapter tích hợp LoadBalancer chuyển vào ngữ cảnh thích hợp và cần supplier/chính sách đọc những giá trị đó.

Ví dụ: `catalog-service` vẫn là service ID, bất kể request có `hint=stable` hay `hint=canary`. Hint chỉ làm thay đổi các ứng viên phù hợp cho lần gọi đó.

### Phân biệt metadata instance với dữ liệu request

~~~text
ServiceInstance.getMetadata():
    hint = canary          <-- Thuộc tính đã đăng ký của instance

HTTP request:
    X-SC-LB-Hint: canary   <-- Mong muốn của một lần gọi cụ thể
~~~

Supplier so khớp hai phía để chọn các instance tương ứng. Không nên ghi hint của request hiện tại vào map metadata của `ServiceInstance` dùng chung, vì việc làm đó có thể ảnh hưởng các request khác.

## 4. Hai phương thức quan trọng của ServiceInstanceListSupplier

Trong Spring Cloud LoadBalancer, `ServiceInstanceListSupplier` cung cấp danh sách `ServiceInstance` dưới dạng reactive:

~~~java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

Đây là các chữ ký minh họa từ API; `Request` thuộc abstraction LoadBalancer, không phải một `HttpServletRequest` bắt buộc.

- `get()`: lấy danh sách theo nguồn và logic của supplier, không truyền ngữ cảnh request cụ thể.
- `get(Request request)`: cho phép supplier sử dụng ngữ cảnh của lời gọi để lọc hoặc điều chỉnh danh sách.

Một supplier chỉ cần dữ liệu discovery có thể trả kết quả tương tự cho cả hai cách gọi. Một supplier có chính sách theo hint có thể trả kết quả khác tùy `Request`.

Ví dụ biểu đạt bằng hàm thuần:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;

static List<ServiceInstance> byHint(
        List<ServiceInstance> candidates,
        String requestedHint
) {
    if (requestedHint == null || requestedHint.isBlank()) {
        return candidates;
    }

    List<ServiceInstance> matching = candidates.stream()
            .filter(instance -> requestedHint.equals(
                    instance.getMetadata().get("hint")))
            .toList();

    // Mô phỏng hành vi fallback của HintBasedServiceInstanceListSupplier.
    return matching.isEmpty() ? candidates : matching;
}
~~~

Hàm này mô tả **bước lọc sau khi đã có danh sách chung**. Nó không thực hiện discovery và cũng không tự chọn duy nhất một instance. Phần chọn instance (chẳng hạn round-robin) diễn ra sau bước lọc.

Ví dụ trên mô phỏng cơ chế fallback của supplier hint được Spring Cloud cung cấp: nếu không có instance khớp hint, nó trả lại danh sách gốc. **Không dùng hành vi fallback này như cơ chế bảo đảm cách ly tenant hoặc giới hạn truy cập**. Nếu chính sách yêu cầu bắt buộc đi đúng nhóm, cần lọc chặt chẽ và xử lý trường hợp không có instance, đồng thời thực thi kiểm soát quyền ở các tầng phù hợp.

## 5. Vì sao thứ tự trong supplier chain rất quan trọng?

Một chuỗi supplier có thể gồm nhiều lớp bọc nhau: truy vấn discovery, cache, health check, lọc zone, hint hoặc các bộ lọc tùy biến. Những bước này không thể hoán đổi tùy ý.

Với chính sách lọc theo request, cách tổ chức thường mong muốn là:

~~~text
Nguồn discovery
    ↓
Cache danh sách chung
    ↓
Lọc theo request (ví dụ hint)
    ↓
Danh sách ứng viên của request hiện tại
    ↓
LoadBalancer chọn một ServiceInstance
~~~

Trong mô hình này, cache giữ danh sách dùng chung, còn bộ lọc tạo ra danh sách riêng cho request **sau khi đọc cache**.

~~~mermaid
flowchart TD
    D["DiscoveryClientServiceInstanceListSupplier"]
    C["CachingServiceInstanceListSupplier"]
    H["HintBasedServiceInstanceListSupplier"]
    L["LoadBalancer"]
    D -->|"danh sách chung"| C
    C -->|"có thể dùng lại"| H
    H -->|"lọc bằng request hiện tại"| L
~~~

Tài liệu chính thức của Spring Cloud hướng dẫn đặt `CachingServiceInstanceListSupplier` ngay sau supplier lấy instance từ mạng, trước các supplier lọc khác. Với `HealthCheckServiceInstanceListSupplier`, cần lưu ý supplier này có cơ chế giữ kết quả riêng; việc phối hợp thêm cache phải cân nhắc để tránh hai lớp cache không cần thiết.

### Nguy cơ khi cache được đặt sau bộ lọc theo request

Giả sử chuỗi được thiết kế sai theo ý nghĩa dữ liệu như sau:

~~~text
Discovery -> lọc hint -> cache dùng chung -> LoadBalancer
~~~

Diễn biến có thể xảy ra khi cache lưu kết quả lọc mà không phân biệt request:

1. Request A mang `hint=canary`; bộ lọc trả danh sách `[catalog-canary-1]`.
2. Cache dùng chung lưu danh sách này cho `catalog-service`.
3. Request B mang `hint=stable`; cache có thể cung cấp lại danh sách `[catalog-canary-1]`.
4. Request B nhận ứng viên không đúng nhu cầu, dù danh sách discovery vẫn có hai instance stable.

Đây là mô hình lỗi **ô nhiễm cache giữa các request** (cross-request cache contamination). Hành vi thực tế còn tùy implementation và khóa cache, nhưng nguyên tắc an toàn là **không đưa kết quả lọc theo request vào cache chỉ khóa theo service ID**.

Nếu thực sự muốn cache kết quả theo request, khóa cache cần bao gồm đầy đủ mọi tiêu chí ảnh hưởng kết quả, có cơ chế hết hạn phù hợp và tránh cache dữ liệu nhạy cảm. Trong đa số bài toán LoadBalancer, dùng cache cho danh sách nguồn rồi lọc theo request đơn giản và dễ kiểm soát hơn.

## 6. Ví dụ cấu hình với HintBasedServiceInstanceListSupplier

Một cách thực hành dễ quan sát là dùng `SimpleDiscoveryClient` để cung cấp danh sách instance tĩnh.

### Khai báo instance và metadata

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  hint: stable
              - uri: http://127.0.0.1:8082
                metadata:
                  hint: stable
              - uri: http://127.0.0.1:8083
                metadata:
                  hint: canary
~~~

Ba instance đều thuộc cùng `catalog-service`. Giá trị metadata `hint` là thuộc tính từng instance, không phải request.

### Cấu hình chuỗi supplier

Với phiên bản Spring Cloud hỗ trợ các builder tương ứng, cấu hình danh sách supplier cho service có thể theo mẫu:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogLoadBalancerConfiguration.class
)
class CatalogLoadBalancerRegistration {
}

// Đặt lớp này ngoài phạm vi component scan mặc định hoặc cấu hình
// sao cho chỉ được sử dụng trong child context của catalog-service.
class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogServiceInstanceListSupplier(
            ConfigurableApplicationContext context
    ) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withHints()
                .build(context);
    }
}
~~~

Các phương thức builder thể hiện chuỗi **nguồn discovery → caching → lọc theo hint**. `@LoadBalancerClient` giới hạn cấu hình cho service ID được chỉ định. Khi đưa cấu hình này vào dự án, cần đặt `CatalogLoadBalancerConfiguration` bên ngoài phạm vi component scan của application context chính để tránh bean cấu hình riêng bị áp dụng ngoài ý muốn.

Nếu discovery client bên dưới đã cache dữ liệu (ví dụ một số integration registry), cân nhắc tắt lớp LoadBalancer cache để tránh cache chồng nhau. Với ứng dụng thử nghiệm, có thể giữ cấu hình trên để thấy rõ các vai trò.

### Gửi hai request có ngữ cảnh khác nhau

~~~http
GET http://catalog-service/products/42
X-SC-LB-Hint: stable
~~~

~~~http
GET http://catalog-service/products/42
X-SC-LB-Hint: canary
~~~

Khi HTTP client được tích hợp LoadBalancer và request header được chuyển qua adapter thích hợp, `HintBasedServiceInstanceListSupplier` đọc header `X-SC-LB-Hint`, so khớp với metadata key `hint`, rồi cung cấp danh sách ứng viên khác nhau.

| Request | Danh sách discovery/cache | Danh sách sau lọc hint |
|---|---|---|
| A: `stable` | `[8081, 8082, 8083]` | `[8081, 8082]` |
| B: `canary` | `[8081, 8082, 8083]` | `[8083]` |
| C: không có hint | `[8081, 8082, 8083]` | `[8081, 8082, 8083]` |
| D: `preview` không khớp | `[8081, 8082, 8083]` | `[8081, 8082, 8083]` (fallback mặc định) |

Đây là kết quả kỳ vọng của **supplier hint** theo hành vi thông thường; chưa phản ánh lựa chọn cuối cùng của thuật toán LoadBalancer. Ví dụ với request A, round-robin sẽ tiếp tục chọn một trong hai instance stable tùy trạng thái của nó.

Lưu ý: ví dụ localhost chỉ dùng được khi caller và các instance cùng chia sẻ môi trường mạng có thể truy cập địa chỉ `127.0.0.1`.

## 7. Ngữ cảnh request đi vào supplier qua đâu?

Dữ liệu request được HTTP client tích hợp đưa vào abstraction `Request` của LoadBalancer. Phụ thuộc adapter và phiên bản Spring Cloud, context có thể chứa `RequestDataContext`, headers hoặc một đối tượng request context khác.

Luồng ở mức khái niệm:

~~~mermaid
sequenceDiagram
    participant Client as HTTP client
    participant Adapter as LoadBalancer adapter
    participant Supplier as Supplier chain
    participant LB as LoadBalancer
    participant Target as Target instance
    Client->>Adapter: HTTP request + header hint
    Adapter->>LB: choose(Request context)
    LB->>Supplier: get(Request)
    Supplier-->>LB: Danh sách đã lọc theo request
    LB-->>Adapter: ServiceInstance được chọn
    Adapter->>Target: Gửi HTTP đến host:port
    Target-->>Adapter: HTTP response
    Adapter-->>Client: Response
~~~

Điều này giải thích một lỗi hay gặp: bộ lọc `get(Request)` hoạt động khi đi qua HTTP client tích hợp, nhưng kết quả có thể khác khi mã kiểm thử chỉ gọi `get()` hoặc gọi bộ chọn trực tiếp mà không cung cấp context. Trường hợp đó, supplier không có dữ liệu hint của request để lọc.

### Phân biệt ba nhóm thông tin

- **Nguồn instance:** trả lời “dịch vụ này có những bản sao nào?”.
- **Request context:** trả lời “yêu cầu này cần bản sao loại nào?”.
- **Chính sách chọn đích:** trả lời “trong các ứng viên hợp lệ, chọn bản sao nào?”.

Cả ba bước cần chính xác thì HTTP client mới nhận được đích phù hợp. Việc chọn đích thành công cũng chưa đảm bảo transport HTTP và server xử lý thành công.

## 8. Dữ liệu chung cũng có thể được xử lý theo chính sách

Không phải mọi supplier không đọc `Request` đều giống nguồn discovery thô. Có những bước biến đổi dựa trên cấu hình chung hoặc metadata của instance, chẳng hạn:

- **Ưu tiên zone:** chọn những instance có metadata zone phù hợp với zone của client. Nếu zone của caller là cấu hình cố định, kết quả có thể dùng lại cho nhiều request của caller đó.
- **Lọc theo sức khỏe:** dựa vào các lần kiểm tra endpoint, tạo danh sách instance đang đáp ứng tiêu chí.
- **Trọng số:** lấy metadata `weight` hoặc hàm trọng số được cấu hình để tác động đến lựa chọn instance.
- **Giới hạn tập instance:** một cấu hình có thể định nghĩa subset cố định cho một client nhằm giảm phạm vi truy cập.

Do đó, tiêu chí quan trọng không phải “có lọc hay không”, mà là **kết quả có phụ thuộc thông tin khác nhau giữa các request hay không**.

Ví dụ, nếu zone của client được cấu hình cố định là `zone-a`, ưu tiên zone có thể được tính từ dữ liệu chung. Nếu mỗi request tự khai báo zone của nó, quyết định lọc theo zone trở thành yêu cầu riêng và không nên bị cache dùng chung khi cache key không chứa zone.

## 9. Health check, cache và request filtering khác nhau ở điểm nào?

Ba cơ chế này dễ bị nhầm là cùng một việc vì đều ảnh hưởng đến danh sách instance.

| Cơ chế | Dữ liệu đầu vào chính | Mục tiêu | Rủi ro nếu cấu hình sai |
|---|---|---|---|
| Cache | Danh sách lấy từ discovery hoặc supplier nền | Giảm chi phí truy vấn lặp lại | Danh sách cũ, cache sai phạm vi |
| Health check | Endpoint và kết quả kiểm tra sức khỏe | Loại hoặc hạn chế instance không khỏe | Bỏ nhầm instance khỏe, probe quá nhiều, thiếu cập nhật |
| Request filtering | Request context cộng metadata instance | Trả ứng viên phù hợp request cụ thể | Trộn điều kiện của các request, fallback ngoài ý muốn |

`HealthCheckServiceInstanceListSupplier` có cơ chế phát lại/kết quả riêng, vì vậy Spring Cloud khuyến nghị đặt nó ngay sau supplier lấy dữ liệu từ mạng và cân nhắc **không** bọc thêm `CachingServiceInstanceListSupplier` khi không cần thiết. Không nên sao chép một thứ tự supplier cho mọi tổ hợp mà không xét loại dữ liệu và cách mỗi supplier giữ trạng thái.

Trong khi đó, `HintBasedServiceInstanceListSupplier` là ví dụ rõ về request filtering: nó cần danh sách candidate trước khi so khớp metadata với hint được chuyển đến.

## 10. Những lỗi có thể gặp khi trộn dữ liệu chung và theo request

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách chẩn đoán |
|---|---|---|
| Request `stable` đôi lúc tới canary | Hint không được chuyển tiếp, fallback khi không khớp hoặc supplier sai thứ tự | Ghi service ID, hint được nhận và candidate list trước/sau lọc |
| Hai request có hint khác nhau nhận cùng danh sách đã lọc | Cache kết quả theo request ở phạm vi chỉ theo service ID | Kiểm tra vị trí cache, key cache và delegate chain |
| Gọi trực tiếp supplier luôn trả mọi instance | Chỉ gọi `get()`, không dùng `get(Request)` hoặc request thiếu context | Kiểm tra cách tạo và truyền `Request` |
| Sau scale down vẫn chọn instance đã dừng | Cache/discovery/health check chưa cập nhật | Kiểm tra TTL, heartbeat và thời điểm làm mới |
| Lọc hint trả mọi instance dù hint không có bản sao nào | Hành vi fallback mặc định của `HintBasedServiceInstanceListSupplier` | Đối chiếu metadata `hint`, xác định yêu cầu có cần strict filtering |
| Kết quả lọc đúng nhưng HTTP thất bại | Host/port, TLS, mạng hoặc backend không sẵn sàng | Phân biệt lỗi lựa chọn với lỗi vận chuyển HTTP |
| Một request có thể gọi sang nhóm instance không được phép | Dùng hint do client tự cung cấp làm cơ chế phân quyền | Xác minh quyền truy cập độc lập với dữ liệu định tuyến |

### Không dùng cache để lưu trạng thái tạm của request

Các giá trị như trace ID, user ID, access token hoặc cookie của một request không nên được đưa vào danh sách instance dùng chung. Hơn nữa, không cần lưu toàn bộ dữ liệu này trong log để debug: thông thường chỉ nên ghi các thuộc tính định tuyến không nhạy cảm, chẳng hạn service ID, nhóm hint và instance được chọn.

### Không nhầm danh sách sau lọc với kết quả LoadBalancer

Supplier trả về **nhiều ứng viên**; LoadBalancer mới chọn một instance cụ thể. Nếu có hai instance stable, cùng một hint stable ở hai request không có nghĩa cả hai phải tới cùng instance.

## 11. Thực hành kiểm tra tính độc lập giữa các request

Có thể xác nhận cấu hình bằng một tình huống gồm ba endpoint và bốn loại request:

1. Khai báo hai instance `hint=stable`, một instance `hint=canary`.
2. Dùng `ServiceInstanceListSupplier.builder().withDiscoveryClient().withCaching().withHints()` trong cấu hình của `catalog-service`.
3. Gửi lần lượt các request có `X-SC-LB-Hint: stable`, `canary`, không có hint và hint không khớp.
4. So sánh danh sách từ discovery với danh sách ứng viên của từng request; chúng phải phản ánh các điều kiện ở bảng mục 6.
5. Lặp lại thứ tự request ngược lại. Kết quả lọc của A không được phụ thuộc vào việc B vừa gọi trước đó.
6. Dừng một instance, chờ dữ liệu discovery/cache cập nhật rồi gửi lại. Quan sát sự khác biệt giữa thay đổi **nguồn chung** và thay đổi **lọc theo request**.

Một bộ quan sát có ích sẽ phân biệt:

~~~text
serviceId=catalog-service sourceCandidates=3
requestHint=stable filteredCandidates=2
selectedInstance=catalog-stable-2
httpStatus=200
~~~

Những dòng trên là ví dụ định dạng log mong muốn, không phải tên log được framework tự động phát ra. Kết hợp trace ID với số lượng ứng viên trước/sau lọc giúp tìm ra lỗi nằm ở nguồn discovery, request context, bộ lọc hay bước HTTP.

## 12. Các quy tắc thiết kế nên nhớ

1. Xác định **phạm vi dữ liệu** trước khi quyết định có thể cache hay không: theo service ID, theo client, hay theo từng request.
2. Cache danh sách instance chung gần nguồn retrieval; áp dụng bộ lọc phụ thuộc request sau đó.
3. Truyền ngữ cảnh đến supplier bằng `get(Request)` khi chính sách cần header, cookie hoặc thông tin request.
4. Giữ metadata của `ServiceInstance` như dữ liệu mô tả instance; không sửa metadata dùng chung để chứa tiêu chí của caller hiện tại.
5. Kiểm tra hành vi khi không có instance khớp: một số supplier trả danh sách gốc, còn chính sách strict có thể cần trả danh sách rỗng hoặc lỗi.
6. Phân biệt danh sách **được cung cấp**, instance **được chọn** và request HTTP **được thực thi**; chúng là ba giai đoạn có thể quan sát riêng.
7. Khi kết hợp cache, health check, zone preference và hint, kiểm tra thứ tự delegate và semantics của từng supplier theo phiên bản Spring Cloud đang dùng.

Cốt lõi của chuỗi cung cấp bản sao là: **discovery và metadata cung cấp dữ liệu nền cho service ID; request context chỉ giới hạn các ứng viên của lần gọi hiện tại; LoadBalancer chọn một instance từ kết quả đó**. Phân định đúng hai loại dữ liệu giúp hệ thống dùng cache hiệu quả mà vẫn định tuyến chính xác khi các request có yêu cầu khác nhau.

**Tham khảo chính thức:** [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).

