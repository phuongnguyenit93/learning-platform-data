# Biến đổi yêu cầu sau khi chọn đích với request transformer

Spring Cloud LoadBalancer giúp một HTTP client gọi địa chỉ **logic** theo service ID, ví dụ **http://inventory-service/api/stock/BOOK-01**. Sau khi lấy danh sách **ServiceInstance**, LoadBalancer chọn một bản sao như **inventory-a.internal:8080** và dùng địa chỉ vật lý để gửi HTTP request. Tuy nhiên, không ít hệ thống còn cần **bổ sung thông tin về bản sao đã được chọn** vào request: instance ID để chẩn đoán, zone để kiểm thử routing, một header kỹ thuật được chuẩn hóa hoặc một dấu hiệu cho upstream trusted gateway.

**Request transformer** là điểm mở rộng dành riêng cho việc đó. Nó nhận **HTTP request** và **ServiceInstance đã được chọn**, rồi trả về request được biến đổi để gửi tiếp. Khác với filter/interceptor thông thường, transformer có quyền truy cập trực tiếp instance đã được LoadBalancer chọn cho lần gọi hiện tại.

Bài học trong chương **Tùy biến LoadBalancer** làm rõ phạm vi transformer, API cho **RestTemplate/RestClient, WebClient và OpenFeign**, cách cấu hình nhiều transformer, ví dụ xử lý header/metadata, phân biệt với supplier/filter, tác động tới retry và bảo mật, kiểm thử ở cấp unit và HTTP integration. Mục tiêu tổng thể là giao tiếp giữa các dịch vụ ổn định khi kết hợp service discovery, health check, routing, timeout và retry.

> **Lưu ý phiên bản:** Những API được mô tả xuất hiện trong tài liệu Spring Cloud Commons/LoadBalancer và Spring Cloud OpenFeign hiện hành. Với repository cụ thể, cần dùng Spring Boot–Spring Cloud BOM tương thích. Chưa thực hiện build/test trên dự án ở bước viết Knowledge này; các ví dụ phải được biên dịch và kiểm thử trong dependency set thực tế.

## 1. Transformer nằm chính xác ở đâu?

~~~mermaid
flowchart TD
    A["Ứng dụng tạo GET http://inventory-service/api/stock/X"] --> B["LoadBalancer filter/interceptor"]
    B --> C["ServiceInstanceListSupplier: discovery, cache, health, zone, hint"]
    C --> D["Reactive/Blocking LoadBalancer: chọn ServiceInstance"]
    D --> E{"Có bản sao hợp lệ?"}
    E -->|Không| F["Không có đích: lỗi/response theo tích hợp"]
    E -->|Có| G["Tái dựng URI theo ServiceInstance"]
    G --> H["Request transformers nhận request và instance đã chọn"]
    H --> I["HTTP transport gửi request cuối"]
    I --> J["Backend trả HTTP response"]
~~~

Đây là **sơ đồ khái niệm**. Vị trí chi tiết của bước tái dựng URI, tạo request và gọi transformer phụ thuộc tích hợp blocking/reactive/Feign và phiên bản. Contract cốt lõi ổn định là **transformer được cung cấp ServiceInstance đã chọn**; không nên mặc định mọi transformer luôn nhìn URI ở cùng một trạng thái vật lý nếu chưa kiểm tra implementation.

Ví dụ trước/sau:

~~~text
Request logic:
    GET http://inventory-service/api/stock/BOOK-01
    X-Correlation-Id: trace-123

LoadBalancer chọn:
    ServiceInstance id=inventory-a
    host=10.20.1.11, port=8080, secure=false
    metadata={zone: zone-a, version: v2}

Request gửi đến backend (minh họa):
    GET http://10.20.1.11:8080/api/stock/BOOK-01
    X-Correlation-Id: trace-123
    X-LB-Selected-Instance: inventory-a
~~~

Chỉ định **X-LB-Selected-Instance** là header của ví dụ, **không phải header bắt buộc** của Spring Cloud. Không dựa vào header này làm thông tin xác thực danh tính; một client khác có thể tự giả mạo nó nếu backend nhận trực tiếp request không được bảo vệ.

### 1.1. Ba câu hỏi, ba điểm mở rộng

| Mục tiêu | Điểm mở rộng | Thời điểm |
| --- | --- | --- |
| Quyết định **instance nào đủ điều kiện** | ServiceInstanceListSupplier, zone/health/hint filtering | Trước khi chọn |
| Quyết định **chọn instance nào** | RoundRobinLoadBalancer, RandomLoadBalancer hoặc implementation tùy chỉnh | Khi chọn |
| Biến đổi **request cho instance đã chọn** | LoadBalancer request transformer | Sau khi có lựa chọn |
| Thêm trace/auth không phụ thuộc instance | RestClient/RestTemplate interceptor, WebClient filter, Feign RequestInterceptor | Theo pipeline của từng client |
| Kiểm soát số lần gửi lại | Retry policy/LoadBalancer retry | Khi gặp điều kiện retry |
| Giới hạn lỗi/thời gian chờ | Timeout, bulkhead, circuit breaker | Tại lớp giao tiếp hoặc application |

**Transformer không phải thuật toán LoadBalancer thứ hai.** Nếu muốn chỉ gửi traffic đến zone-a hoặc canary-v2, nên làm điều đó ở **supplier hoặc LoadBalancer policy**, không bằng cách tự thay hostname/header tùy tiện sau khi đã chọn một instance khác.

## 2. Contract của ba transformer chính

Theo tài liệu Spring Cloud:

| HTTP client | Interface transformer | Request đầu vào và đầu ra |
| --- | --- | --- |
| RestTemplate | **LoadBalancerRequestTransformer** | Spring HttpRequest → HttpRequest |
| RestClient | **LoadBalancerRequestTransformer** | Spring HttpRequest → HttpRequest |
| WebClient | **LoadBalancerClientRequestTransformer** | Spring WebFlux ClientRequest → ClientRequest |
| OpenFeign | **LoadBalancerFeignRequestTransformer** | Feign Request → Request |

Các method:

~~~java
// Spring Cloud Commons, blocking:
HttpRequest transformRequest(HttpRequest request, ServiceInstance instance);

// Spring Cloud Commons, reactive WebClient:
ClientRequest transformRequest(
        ClientRequest request, ServiceInstance instance);

// Spring Cloud OpenFeign:
Request transformRequest(Request request, ServiceInstance instance);
~~~

Không nhầm:

- **LoadBalancerRequestTransformer** với Spring Framework **ClientHttpRequestInterceptor**; interceptor thường không nhận ServiceInstance đã chọn.
- **LoadBalancerClientRequestTransformer** với **ExchangeFilterFunction** của WebClient; filter thông thường nhìn thấy request của pipeline, nhưng không được truyền ServiceInstance theo chữ ký như transformer.
- **LoadBalancerFeignRequestTransformer** với **feign.RequestInterceptor**; RequestInterceptor chủ yếu làm việc trên RequestTemplate, còn transformer nhận **Request** và instance.

Các API là **hàm biến đổi request**, không phải chỗ gọi HTTP thêm lần nữa. Không mở socket, không gọi registry, không đồng bộ refresh token và không tự thực hiện retry bên trong transformer.

### 2.1. Khi không có ServiceInstance

Nếu discovery/supplier không trả ứng viên, tích hợp LoadBalancer có thể tạo lỗi hoặc response lỗi trước bước gửi HTTP. **Không có bảo đảm mọi transformer sẽ được gọi với một instance hợp lệ**. Ở một số interface/phiên bản, tham số ServiceInstance được đánh dấu có thể null.

Vì vậy, code nên:

~~~java
if (instance == null) {
    return request;
}
~~~

Nếu hợp đồng ứng dụng cần coi không có instance là lỗi, hãy xử lý ở tầng **LoadBalancer error adapter/response handler**; đừng cố tạo một host hoặc instance giả trong transformer.

## 3. Khai báo dependency và client có LoadBalancer

Một ví dụ Gradle sử dụng dependency versions theo BOM Spring Boot–Spring Cloud của dự án:

~~~gradle
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.springframework.boot:spring-boot-starter-web")

    // Nếu dùng WebClient:
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    // Nếu dùng Spring Cloud OpenFeign:
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
    // MockWebServer hoặc WireMock cho integration testing
}
~~~

Không cần thêm **cả ba HTTP client starters** nếu ứng dụng chỉ sử dụng một kiểu. Ví dụ gom các lựa chọn lại để người học thấy các API liên quan.

Cấu hình RestTemplate:

~~~java
@Bean
@LoadBalanced
RestTemplate loadBalancedRestTemplate() {
    return new RestTemplate();
}
~~~

Cấu hình RestClient:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

Cấu hình WebClient:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
~~~

Lưu ý: **@LoadBalanced** được dùng để đánh dấu bean cần Spring Cloud LoadBalancer tùy biến. Nếu một WebClient đã được tạo bằng builder có filter LoadBalancer, không thêm **ReactorLoadBalancerExchangeFilterFunction** lần thứ hai. Trong production, nên giữ các Boot customizers cho observability, TLS và codec khi tạo custom builders.

### 3.1. Sử dụng service ID thay vì host vật lý

RestClient:

~~~java
StockResponse stock = restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

WebClient:

~~~java
Mono<StockResponse> stock = webClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

Nếu code gọi **http://localhost:8080/...** bằng một client không có tích hợp LoadBalancer, transformer không có ServiceInstance thực để nhận. Một request HTTP hợp lệ tự nó không phải bằng chứng đã đi qua transformer của Spring Cloud LoadBalancer.

## 4. RestTemplate và RestClient: LoadBalancerRequestTransformer

**LoadBalancerRequestTransformer** nhận Spring Framework **HttpRequest** và **ServiceInstance**. Tài liệu chính thức dùng **HttpRequestWrapper** để sao chép request gốc, rồi ghi đè **getHeaders()** nhằm thêm header dựa trên bản sao đã chọn.

Ví dụ bean hoàn chỉnh:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.support.HttpRequestWrapper;

@Configuration(proxyBeanMethods = false)
class InventoryBlockingTransformers {

    @Bean
    LoadBalancerRequestTransformer selectedInstanceHeader() {
        return new LoadBalancerRequestTransformer() {
            @Override
            public HttpRequest transformRequest(
                    HttpRequest request, ServiceInstance instance) {
                if (instance == null || instance.getInstanceId() == null) {
                    return request;
                }

                return new HttpRequestWrapper(request) {
                    @Override
                    public HttpHeaders getHeaders() {
                        HttpHeaders headers = new HttpHeaders();
                        headers.putAll(super.getHeaders());
                        headers.set("X-LB-Selected-Instance",
                                instance.getInstanceId());
                        return headers;
                    }
                };
            }
        };
    }
}
~~~

**Điểm cần quan sát:**

1. Transformer **không tự gọi ServiceInstanceListSupplier**. Nó nhận instance từ tích hợp LoadBalancer.
2. **HttpRequestWrapper** giữ các thành phần của request gốc và chỉ thay đổi phần được override.
3. Tạo một **HttpHeaders mới** thay vì sửa trực tiếp headers của request ban đầu.
4. Dùng **headers.set()** thay vì add() để tránh nhiều giá trị trùng khi các lớp filter/transformer khác xử lý cùng header.
5. Nếu không có ID, ví dụ không thêm header; không biến null thành chuỗi **null**.

**Lưu ý bảo mật:** interface cho phép nhận instance với metadata từ registry bên ngoài; hãy kiểm tra giá trị hợp lệ trước khi đưa vào HTTP header. Mục 11 sẽ minh họa validation theo allowlist.

### 4.1. Vì sao không sửa trực tiếp request.getHeaders()?

Những implementation HttpRequest có thể giữ headers mutable hoặc read-only, hoặc được một interceptor khác chia sẻ. Code kiểu:

~~~java
request.getHeaders().add(
        "X-LB-Selected-Instance", instance.getInstanceId());
return request;
~~~

có thể ném UnsupportedOperationException, tạo side effect không mong muốn hoặc làm header bị nhân sau nhiều lần transform. **Trả wrapper/request mới** là mẫu được tài liệu Spring Cloud minh họa và dễ kiểm thử hơn.

### 4.2. Chú ý bảo toàn request method và URI

Nếu chỉ cần thêm header, đừng thay:

- **getMethod()**: GET/POST/PUT/DELETE có ngữ nghĩa và idempotency khác nhau.
- **getURI()**: chứa đích đã được LoadBalancer xử lý theo phiên bản tích hợp.
- **Path, query và fragment**: có thể ảnh hưởng routing, chữ ký hoặc cache key.
- **Content-Length/Content-Type**: phải đồng bộ với body nếu có biến đổi payload.

Transformer không phải chỗ làm mới body bằng cách đọc lại InputStream của request. Body có thể không replayable, đặc biệt khi retry các upload lớn.

## 5. WebClient: LoadBalancerClientRequestTransformer

Với **WebClient**, Spring Cloud cung cấp **LoadBalancerClientRequestTransformer**. Kiểu request là **org.springframework.web.reactive.function.client.ClientRequest**, được xây dựng theo mô hình bất biến; ta thường tạo request mới từ request gốc bằng **ClientRequest.from(request)**.

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.reactive.LoadBalancerClientRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.ClientRequest;

@Configuration(proxyBeanMethods = false)
class InventoryReactiveTransformers {

    @Bean
    LoadBalancerClientRequestTransformer selectedInstanceHeader() {
        return new LoadBalancerClientRequestTransformer() {
            @Override
            public ClientRequest transformRequest(
                    ClientRequest request, ServiceInstance instance) {
                if (instance == null || instance.getInstanceId() == null) {
                    return request;
                }

                return ClientRequest.from(request)
                        .headers(headers -> headers.set(
                                "X-LB-Selected-Instance",
                                instance.getInstanceId()))
                        .build();
            }
        };
    }
}
~~~

**Điểm quan trọng:** WebClient là reactive nên request thường chỉ được gửi khi Publisher được subscribe. Đừng kết luận transformer đã chạy khi chỉ mới tạo Mono.

~~~java
Mono<StockResponse> call = webClient.get()
        .uri("http://inventory-service/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class);

// Đến đây có thể chưa có request, nên cũng chưa có instance được chọn.

StepVerifier.create(call)
        .expectNextMatches(stock -> stock.available() >= 0)
        .verifyComplete();
~~~

Một lần subscription có thể kích hoạt một lần chọn instance; khi operator **retryWhen** resubscribe, đường LoadBalancer/transformer có thể chạy lại cho attempt mới. Cần test thay vì giả định instance ID đã được chọn từ thời điểm Mono được tạo.

### 5.1. Đặt chỗ cho trace/auth trong pipeline

WebClient có thể có:

~~~text
Client code
  -> Authentication ExchangeFilterFunction
  -> Observability/trace filters
  -> Spring Cloud LoadBalancer filter
  -> selected-instance request transformers
  -> ClientHttpConnector
~~~

Thứ tự thực tế phụ thuộc cách builder và filter được cấu hình. **Các filter WebClient có thể chạy trước hoặc sau LoadBalancer filter**, còn transformer chuyên dụng luôn được gọi trong tích hợp LoadBalancer với ServiceInstance của lần chọn. Nếu trace filter thêm header sau transformer hoặc ngược lại, một header trùng tên có thể bị thay đổi theo thứ tự.

Không thêm LoadBalancer filter hai lần; không gắn một global WebClient filter mang credential của Inventory vào request của Payment/Catalog. Nếu cần scope theo service, thiết kế **dedicated WebClient** hoặc kiểm soát service ID đáng tin cậy.

### 5.2. Khi nào cần biến đổi URI trong WebClient?

**ClientRequest.from(request).url(URI)** cho phép thay URI theo API của Spring Framework, nhưng không nên sử dụng để tự chọn lại một host sau khi LoadBalancer đã chọn ServiceInstance. Điều đó có thể:

- Bypass discovery/health/zone policy đã áp dụng.
- Khiến trace/metrics ghi selectedInstance=A nhưng HTTP thực tới B.
- Làm lệch TLS hostname verification/SNI hoặc Host header.
- Chuyển Authorization header sang host không đáng tin cậy.
- Gây sai đường retry và observability.

Nếu yêu cầu là **đổi path theo API version, rewrite base path hoặc gateway routing**, nên xem xét nơi cấu hình request URI trước khi chọn đích, gateway rewrite policy hoặc cơ chế version routing có hỗ trợ riêng. Chỉ biến đổi URI hậu lựa chọn khi có một contract được xác định rõ và integration test cho URI/TLS/auth.

## 6. OpenFeign: LoadBalancerFeignRequestTransformer

Spring Cloud OpenFeign có một transformer riêng, **LoadBalancerFeignRequestTransformer**, vì Feign dùng **feign.Request** chứ không phải HttpRequest/ClientRequest của Spring Framework.

Ví dụ từ nguyên tắc chính thức: sao chép headers, bổ sung service ID và instance ID, tạo Request mới mà vẫn giữ method, URL, body, charset và request template:

~~~java
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import feign.Request;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.openfeign.loadbalancer.LoadBalancerFeignRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class InventoryFeignTransformers {

    @Bean
    LoadBalancerFeignRequestTransformer selectedInstanceHeader() {
        return new LoadBalancerFeignRequestTransformer() {
            @Override
            public Request transformRequest(
                    Request request, ServiceInstance instance) {
                if (instance == null) {
                    return request;
                }

                Map<String, Collection<String>> headers =
                        new HashMap<>(request.headers());
                headers.put("X-LB-Service",
                        Collections.singletonList(instance.getServiceId()));

                if (instance.getInstanceId() != null) {
                    headers.put("X-LB-Selected-Instance",
                            Collections.singletonList(instance.getInstanceId()));
                }

                return Request.create(
                        request.httpMethod(),
                        request.url(),
                        headers,
                        request.body(),
                        request.charset(),
                        request.requestTemplate());
            }
        };
    }
}
~~~

Ở đây **Request.create(...)** là overload được tài liệu Spring Cloud OpenFeign minh họa. Với một phiên bản Feign khác, hãy kiểm tra overload của Request.create theo dependency thực tế trước khi biên dịch.

### 6.1. Feign client phải thật sự đi qua LoadBalancer

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

Khi starter OpenFeign và LoadBalancer có mặt, **name** là service ID dùng cho discovery. Ngược lại, khi khai báo URL cố định bằng thuộc tính **url** trên @FeignClient hoặc **spring.cloud.openfeign.client.config.<name>.url**, Feign có thể gọi URL trực tiếp **không qua LoadBalancer**, và transformer dành cho load-balanced request không nhất thiết được thực thi.

**Feign RequestInterceptor** chỉ làm việc trên template trước/sát lúc tạo request; nó không được truyền selected ServiceInstance qua method signature. Nếu muốn header phản ánh bản sao thực sự được chọn, dùng **LoadBalancerFeignRequestTransformer**, không chỉ đọc một service ID cố định trong RequestInterceptor.

### 6.2. Giữ body và charset khi tạo Feign Request mới

Một lỗi thường gặp khi tùy biến Feign:

~~~java
// Ý tưởng sai: tạo lại Request nhưng bỏ mất body, charset hoặc template.
// Cần dùng overload phù hợp và giữ các trường từ request gốc.
~~~

Đặc biệt với POST/PUT, nếu làm mất body hoặc thay Content-Type/Content-Length sai, backend có thể trả 400/415 hoặc thực hiện nghiệp vụ sai. Transformer nên **sửa đúng phần cần sửa** và bảo toàn các thuộc tính còn lại.

## 7. Bảng chọn đúng API theo client

| Trường hợp | Interface | Tạo request mới |
| --- | --- | --- |
| Blocking RestTemplate GET | LoadBalancerRequestTransformer | HttpRequestWrapper; override getHeaders() |
| Blocking RestClient POST | LoadBalancerRequestTransformer | HttpRequestWrapper; giữ method, URI, body do transport quản lý |
| Reactive WebClient GET/POST | LoadBalancerClientRequestTransformer | ClientRequest.from(original).headers(...).build() |
| Feign declarative client | LoadBalancerFeignRequestTransformer | Copy headers và Request.create(...) giữ fields gốc |

Một **Spring bean của interface này không tự gắn LoadBalancer vào HTTP client**. Phải có integration tương ứng và URI logic theo service ID. Cũng không thể lấy LoadBalancerRequestTransformer rồi đăng ký thay cho LoadBalancerClientRequestTransformer vì các kiểu request và pipeline khác nhau.

## 8. Nhiều transformer: thứ tự là một phần của contract

Spring Cloud cho phép khai báo **nhiều transformer**. Tài liệu LoadBalancer nêu thứ tự áp dụng theo thứ tự bean đã định nghĩa và có thể xác định thứ tự rõ ràng bằng cơ chế **@Order** / hằng **DEFAULT_ORDER** của interface.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderedTransformers {

    @Bean
    @Order(-100)
    LoadBalancerClientRequestTransformer ensureInstanceHeader() {
        return (request, instance) -> {
            if (instance == null || instance.getInstanceId() == null) {
                return request;
            }
            return ClientRequest.from(request)
                    .headers(h -> h.set("X-LB-Selected-Instance",
                            instance.getInstanceId()))
                    .build();
        };
    }

    @Bean
    @Order(100)
    LoadBalancerClientRequestTransformer markDiagnostics() {
        return (request, instance) ->
                ClientRequest.from(request)
                        .headers(h -> h.set("X-LB-Transform-Version", "1"))
                        .build();
    }
}
~~~

Trong ví dụ, bean -100 được ưu tiên trước bean 100 **nếu pipeline biến đổi dùng danh sách bean được sắp thứ tự như mong đợi theo phiên bản**. Tránh dựa vào thứ tự quét component hoặc tên method bean để tạo contract khi thay đổi thứ tự sẽ thay header.

Nếu hai transformer đều ghi **X-LB-Selected-Instance**:

~~~text
Transformer A: set X-LB-Selected-Instance = inventory-a
Transformer B: set X-LB-Selected-Instance = override

Kết quả: phụ thuộc transformer chạy sau.
~~~

Nếu sử dụng **add** thay vì **set**, kết quả còn có thể thành hai header values, gây ambiguity ở backend hoặc proxy. Đây là lý do mỗi trường nên có **một chủ sở hữu**, với thứ tự đã kiểm thử.

### 8.1. DEFAULT_ORDER và thứ tự bằng nhau

Các interface có **DEFAULT_ORDER**; ví dụ LoadBalancerRequestTransformer.DEFAULT_ORDER và LoadBalancerClientRequestTransformer.DEFAULT_ORDER đều là lựa chọn order mặc định. Với nhiều bean cùng order, không nên phụ thuộc vào một thứ tự ngầm để bảo đảm business contract.

Nếu cần một transformer xử lý trước tất cả transformer còn lại, đặt thứ tự rõ và xác minh qua unit/integration test. Không coi thứ tự này đồng nghĩa **vị trí tương đối với mọi ClientHttpRequestInterceptor, WebClient filter hoặc Feign RequestInterceptor**; đó là những pipeline khác nhau.

### 8.2. Đừng dùng transformer để tạo vòng gọi thứ hai

Transformer nên thực hiện **biến đổi thuần/lẹ**:

- Không gọi REST API để xin token mới bên trong method transformRequest.
- Không truy vấn database hoặc registry qua mạng ở mỗi attempt.
- Không sửa mutable shared state không an toàn.
- Không thực hiện blocking I/O trên WebClient reactive pipeline.

Nếu cần token OAuth2, ưu tiên **OAuth2AuthorizedClientManager** và filter/interceptor chuyên trách; nếu cần metadata chọn instance, lấy từ **ServiceInstance** đã được truyền vào.

## 9. Scope transformer cho đúng service ID

Một bean transformer trong **parent ApplicationContext** có thể áp dụng cho nhiều HTTP clients của cùng loại. Nếu chỉ Inventory được phép nhận header tùy chỉnh, **đừng mặc định bean toàn cục sẽ tự scope theo @LoadBalancerClient(name = "inventory-service")**.

Ví dụ điều kiện:

~~~java
@Bean
LoadBalancerClientRequestTransformer inventoryOnlyHeader() {
    return (request, instance) -> {
        if (instance == null
                || !"inventory-service".equals(instance.getServiceId())
                || instance.getInstanceId() == null) {
            return request;
        }

        return ClientRequest.from(request)
                .headers(h -> h.set("X-LB-Selected-Instance",
                        instance.getInstanceId()))
                .build();
    };
}
~~~

Đây là **giới hạn ở tầng transformer**, không phải một security boundary. Nếu service discovery metadata bị sai hoặc instance được ánh xạ đến host không được phép, header guard không thay thế mTLS, DNS policy hay allowlist endpoints.

Nếu cần cấu hình hoàn toàn khác nhau theo service ID, Spring Cloud còn có **@LoadBalancerClient(name, configuration)** để tùy chỉnh supplier/algorithm trong child context. **Không suy diễn** mọi transformer bean khai báo trong child config đều được tích hợp cùng cách ở mọi client/version; kiểm chứng điểm đăng ký và scope thực tế trên dependency của dự án.

## 10. Dùng metadata của ServiceInstance một cách có kiểm soát

ServiceInstance có thể chứa:

~~~java
instance.getInstanceId();
instance.getServiceId();
instance.getHost();
instance.getPort();
instance.isSecure();
instance.getMetadata();
~~~

Ví dụ registry cho Inventory:

| Instance ID | zone | release | weight |
| --- | --- | --- | ---: |
| inventory-a | zone-a | stable | 90 |
| inventory-b | zone-a | canary | 10 |
| inventory-c | zone-b | stable | 90 |

Các metadata **zone, release, weight** có thể được dùng ở bước **lọc/chọn instance**, nhưng sau khi đã chọn, transformer cũng có thể bổ sung thông tin đã được kiểm soát vào header gửi tới backend:

~~~java
@Bean
LoadBalancerClientRequestTransformer selectedZoneHeader() {
    return (request, instance) -> {
        if (instance == null) {
            return request;
        }

        String zone = instance.getMetadata().get("zone");
        if (!Set.of("zone-a", "zone-b").contains(zone)) {
            return request;
        }

        return ClientRequest.from(request)
                .headers(h -> h.set("X-Selected-Zone", zone))
                .build();
    };
}
~~~

Điều kiện **allowlist** ngăn một metadata tùy ý được đưa thẳng vào header. **X-Selected-Zone** là ví dụ kỹ thuật, không được backend dùng như bằng chứng vùng địa lý, tenant identity hoặc authorization.

### 10.1. Không tin metadata từ discovery như dữ liệu tuyệt đối

Một số registry cho phép ứng dụng tự đăng ký metadata. Nếu một instance có metadata chứa:

~~~text
zone = zone-a
header-value = dữ liệu không hợp lệ hoặc quá dài
~~~

việc copy thẳng header-value vào request có thể gây:

- HTTP header validation exception.
- Header injection hoặc xung đột proxy policy.
- High-cardinality logs/metrics.
- Bỏ sót security scope.

Sử dụng **allowlist, length limits, schema validation, normalization**. Không cho metadata tự quyết định gửi Bearer token, private key hoặc tenant header sang một host ngoài vùng tin cậy.

### 10.2. Bổ sung instance ID an toàn hơn

Một helper kiểm tra ID trước khi gắn header:

~~~java
final class InstanceHeaderPolicy {

    private static final Pattern SAFE =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    static Optional<String> validId(ServiceInstance instance) {
        if (instance == null || instance.getInstanceId() == null) {
            return Optional.empty();
        }
        String id = instance.getInstanceId();
        return SAFE.matcher(id).matches()
                ? Optional.of(id)
                : Optional.empty();
    }
}
~~~

Ví dụ này yêu cầu imports **java.util.Optional**, **java.util.regex.Pattern** và **ServiceInstance**. Nó chỉ minh họa chính sách ký tự an toàn cho một header kỹ thuật. Nếu hệ thống dùng Kubernetes pod UID, UUID hay instance ID định dạng khác, hãy chọn regex theo **contract thực tế**, không cắt bỏ dữ liệu ngẫu nhiên hoặc tự tạo giá trị không thể truy vết.

Khi ID không hợp lệ, có thể bỏ header và ghi log cảnh báo an toàn. Không đưa raw ID không kiểm soát vào logs nếu nó có thể do bên ngoài cung cấp.

## 11. Header dành cho chẩn đoán khác với header xác thực

Một request transformer thường hữu ích để thêm thông tin:

~~~text
X-LB-Service: inventory-service
X-LB-Selected-Instance: inventory-a
X-Selected-Zone: zone-a
~~~

Các header này chỉ là **thông tin quan sát**. Backend không nên suy ra:

- Request đã được xác thực.
- Người dùng thuộc tenant nào.
- Request đi qua đúng network policy.
- Token có audience đúng.
- Server được phép bỏ qua rate limit hoặc authorization.

Bất kỳ HTTP client nào có thể gửi header tự đặt tên nếu không có gateway/server-side stripping policy. **Instance header không thay thế mTLS/JWT/OAuth2**.

### 11.1. Không để caller giả mạo header được cấp bởi transformer

Giả sử một API gateway nhận từ internet:

~~~http
X-LB-Selected-Instance: inventory-admin
~~~

Nếu gateway chuyển nguyên header tới Order, rồi transformer dùng **headers.add()**, backend có thể thấy hai giá trị và chọn sai một giá trị theo parser. Dùng:

~~~java
headers.set("X-LB-Selected-Instance", safeInstanceId);
~~~

để **ghi đè giá trị từ phía caller** trong phạm vi HTTP client của bạn. Đồng thời, gateway phải **xóa hoặc chuẩn hóa** những header được coi là nội bộ, còn backend chỉ tin identity đến từ kênh đã xác thực.

### 11.2. Authorization header cần quyết định đúng nơi

**Authorization: Bearer ...** nên được đặt bởi OAuth2 authorized client/filter hoặc interceptor bảo mật đã được cấu hình cho audience/downstream cụ thể. Transformer chỉ dùng được ServiceInstance để bổ sung thông tin cuối cùng; nếu gắn token dựa trên metadata/host không được xác minh, có nguy cơ **token exfiltration**.

Khi thực sự cần token có audience theo instance, hãy thiết kế **credential provider có trust policy, audience mapping và cache** riêng, không yêu cầu transformer gọi Token Endpoint đồng bộ ở mỗi attempt.

**Không thay Authorization, Cookie, Host, Content-Length hoặc hop-by-hop headers** nếu mục tiêu đơn thuần là thêm instance ID. Trong HTTP/2, một số header hop-by-hop còn bị cấm hoặc có cách biểu diễn khác.

## 12. Host header, TLS SNI và X-Forwarded-* không nên sửa tùy tiện

Trong HTTP, request logic có thể dùng host service ID, nhưng request vật lý sẽ tới host/port của selected ServiceInstance. **Host header** và **TLS Server Name Indication (SNI)** có liên hệ nhưng không phải cùng một thứ: sửa HTTP Host header **không tự sửa TLS certificate validation**.

Ví dụ:

~~~text
URI logic:   https://inventory-service/stock
Instance:    inventory-a.internal:8443
TLS peer:    certificate SAN inventory-a.internal
~~~

Nếu transformer tự đặt:

~~~text
Host: inventory-service
~~~

trong khi TLS handshake diễn ra với inventory-a.internal, bạn phải đánh giá **certificate SAN, SNI, virtual host routing và policy proxy**. Đừng cố chữa SSLHandshakeException bằng cách tắt hostname verification.

### 12.1. X-Forwarded Headers Support của OpenFeign

Spring Cloud OpenFeign có hỗ trợ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      x-forwarded:
        enabled: true
~~~

Tài liệu OpenFeign mô tả tính năng để thêm **X-Forwarded-Host** và **X-Forwarded-Proto** qua transformer tương ứng. Không cần tự viết một transformer thứ hai để ghi đè các header này trừ khi có một yêu cầu cụ thể đã được kiểm thử.

X-Forwarded-Host/Proto là các thông tin có thể ảnh hưởng URL generation, redirect hoặc security policy phía server. Chỉ tin chúng khi nằm sau một proxy/gateway đã biết và có quy trình lọc header từ caller ngoài; **không coi X-Forwarded-* là danh tính được chứng thực**.

### 12.2. Không viết lại URL để chuyển sang host chưa được phê duyệt

Transformer có quyền sửa request theo API client, nhưng nếu dùng thông tin từ metadata để chọn host khác, request có thể vượt khỏi tập instance đã qua health/discovery và mang theo credentials nhạy cảm.

Nếu mục tiêu là **chỉ định canary hoặc zone**, áp dụng:

~~~text
Client hint / API version / zone
        |
        v
ServiceInstanceListSupplier lọc ứng viên
        |
        v
LoadBalancer chọn
        |
        v
Transformer chỉ ghi metadata quan sát
~~~

Không áp dụng:

~~~text
LoadBalancer chọn A
        |
        v
Transformer đọc metadata của A rồi tự đổi URL tới B
        |
        v
Metrics ghi A, request thực tới B
~~~

## 13. Transformer và hint-based routing phải được hiểu theo hai chiều

**HintBasedServiceInstanceListSupplier** có thể chọn tập ứng viên dựa trên hint trong request, ví dụ một header được Spring Cloud hỗ trợ hoặc cấu hình hints tương ứng. Đó là dữ liệu **đi vào** bước chọn instance.

Transformer nhận selected ServiceInstance sau lựa chọn, nên header do transformer thêm **không thể tác động ngược trở lại quyết định vừa được thực hiện**.

~~~text
Request header X-SC-LB-Hint: canary
         |
         v
HintBasedServiceInstanceListSupplier
         |
         v
Chọn inventory-b (metadata hint=canary)
         |
         v
Transformer thêm X-LB-Selected-Instance: inventory-b
~~~

Nếu muốn thuật toán chọn instance dựa trên **tenant, API version hoặc sticky session**, cần truyền dữ liệu vào context/supplier **trước khi lựa chọn**. Đừng viết transformer mong rằng header thêm sau sẽ làm LoadBalancer đổi đích ngay trong lần gọi đó.

### 13.1. Ghi nhận dữ liệu selected instance để kiểm tra policy

Ví dụ một request vào với hint **canary**, nhưng backend nhận header:

~~~text
X-LB-Selected-Instance: inventory-a
~~~

Điều này có thể cho thấy:

- Hint không match instance nào nên supplier fallback.
- Header hint không được đưa vào request context đúng cách.
- Metadata của instance chưa đúng.
- Supplier ordering khiến danh sách bị filter ngoài ý muốn.

Transformer giúp **quan sát kết quả** nhưng không tự sửa được nguyên nhân. Hãy kiểm tra chuỗi supplier và request-context propagation.

## 14. Retry và transformer: mỗi attempt có thể chọn đích khác

Giả sử Spring Cloud LoadBalancer/HTTP client có chính sách retry:

~~~text
Logical GET /stock/X

Attempt 1:
  selectedInstance = inventory-a
  transformer -> X-LB-Selected-Instance: inventory-a
  backend A -> 503

Attempt 2:
  selectedInstance = inventory-b
  transformer -> X-LB-Selected-Instance: inventory-b
  backend B -> 200
~~~

Nếu transformer lấy instance **từ constructor hoặc singleton field** thay vì tham số method, nó có thể ghi sai header ở attempt thứ hai. **Chỉ dùng ServiceInstance được truyền cho attempt hiện tại**.

### 14.1. Không khẳng định mỗi retry luôn chọn instance khác

Retry có thể:

- Thử lại trên **cùng ServiceInstance**.
- Chọn instance mới nhưng policy lại cho ra instance trước đó.
- Tránh previous instance khi còn ứng viên và retry-aware supplier hoạt động.
- Không chạy lại transformer khi lỗi xảy ra ở giai đoạn quá sớm hoặc tích hợp client khác.

Số transformer invocations và số HTTP attempts cần được **đếm trong integration test**. Không mặc định một logical request chỉ gọi transformer đúng một lần hoặc mọi lần retry đều chạy lại toàn bộ chuỗi giống nhau.

### 14.2. Không ghi số attempt bằng mutable shared counter trong transformer

Transformer bean thường là singleton. Nếu giữ:

~~~java
private int attemptNumber = 0;
~~~

rồi tăng số trên mỗi request, con số đó trộn lẫn **mọi concurrent requests** của service, không phải attempts của một logical call. Muốn phân biệt retries, dùng tracing/RetryContext hoặc request context có định danh phù hợp; chỉ thêm một header attempt khi dữ liệu đã được framework hoặc application tính **đúng phạm vi**.

### 14.3. HTTP method và idempotency không đổi vì transformer

Transformer không thể làm một POST non-idempotent trở nên an toàn chỉ bằng cách thêm header instance ID. Khi retry POST đặt hàng/thanh toán, cần **idempotency key có server-side deduplication** và deadline/attempt budget rõ ràng.

Một request có body stream cũng có thể không replayable. Không triển khai retry bên trong transformer để tránh phát sinh gửi lại body ngoài kiểm soát của HTTP client.

## 15. Unit test trực tiếp LoadBalancerRequestTransformer

Trước khi tạo Spring ApplicationContext, có thể test một transformer như **hàm biến đổi từ request + instance sang request mới**. Khi đó ta chủ động đặt instance ID và headers, không phụ thuộc thuật toán Round Robin.

Ví dụ JUnit Jupiter với Spring Test:

~~~java
import java.net.URI;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerRequestTransformer;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpRequest;
import org.springframework.mock.http.client.MockClientHttpRequest;

import static org.junit.jupiter.api.Assertions.*;

class BlockingTransformerTest {

    private final LoadBalancerRequestTransformer transformer =
            new InventoryBlockingTransformers().selectedInstanceHeader();

    @Test
    void addsSelectedInstanceWithoutMutatingOriginal() {
        URI originalUri =
                URI.create("http://inventory-service/api/stock/BOOK-01");
        MockClientHttpRequest original =
                new MockClientHttpRequest(HttpMethod.GET, originalUri);
        original.getHeaders().set("X-Correlation-Id", "trace-123");

        ServiceInstance selected = new DefaultServiceInstance(
                "inventory-a", "inventory-service",
                "localhost", 8081, false);

        HttpRequest transformed =
                transformer.transformRequest(original, selected);

        assertEquals(HttpMethod.GET, transformed.getMethod());
        assertEquals(originalUri, transformed.getURI());
        assertEquals("trace-123",
                transformed.getHeaders().getFirst("X-Correlation-Id"));
        assertEquals("inventory-a",
                transformed.getHeaders().getFirst("X-LB-Selected-Instance"));

        // Header gốc chưa bị sửa bởi transformer.
        assertNull(original.getHeaders().getFirst("X-LB-Selected-Instance"));
    }

    @Test
    void noInstanceDoesNotInventTarget() {
        MockClientHttpRequest original = new MockClientHttpRequest(
                HttpMethod.GET, URI.create("http://inventory-service/test"));

        HttpRequest result =
                transformer.transformRequest(original, null);

        assertSame(original, result);
    }
}
~~~

Đoạn test dùng implementation **InventoryBlockingTransformers** ở mục 4, Spring Test **MockClientHttpRequest** và một ServiceInstance cố định. Nếu dự án bật nullable type checks hoặc API khác theo phiên bản, điều chỉnh annotation/import tương ứng.

**Điều test này chứng minh:** transformer trả wrapper có header đúng, giữ URI/method/header cũ và xử lý instance null. Nó **chưa chứng minh** một RestTemplate/RestClient thật đã đăng ký transformer và chạy qua LoadBalancer.

### 15.1. Test trường hợp header đã tồn tại

Một trường hợp bảo mật nên có:

~~~java
original.getHeaders().set(
        "X-LB-Selected-Instance", "attacker-supplied");

HttpRequest result = transformer.transformRequest(original, selected);

assertEquals("inventory-a",
        result.getHeaders().getFirst("X-LB-Selected-Instance"));
assertEquals(1,
        result.getHeaders().get("X-LB-Selected-Instance").size());
~~~

Đây là ví dụ assertion đặt thêm trong **cùng test fixture** ở trên. Nó xác minh **set thay vì add**, không để header giả mạo lẫn vào nhiều giá trị.

## 16. Unit test WebClient transformer: request bất biến

Với ClientRequest:

~~~java
@Test
void webClientTransformerPreservesRequestAndAddsHeader() {
    URI uri =
            URI.create("http://inventory-service/api/stock/BOOK-01?q=1");

    ClientRequest original =
            ClientRequest.create(HttpMethod.GET, uri)
                    .header("X-Correlation-Id", "trace-456")
                    .build();

    ServiceInstance instance = new DefaultServiceInstance(
            "inventory-b", "inventory-service",
            "localhost", 8082, false);

    LoadBalancerClientRequestTransformer transformer =
            new InventoryReactiveTransformers().selectedInstanceHeader();

    ClientRequest changed =
            transformer.transformRequest(original, instance);

    assertEquals(original.url(), changed.url());
    assertEquals(original.method(), changed.method());
    assertEquals("trace-456",
            changed.headers().getFirst("X-Correlation-Id"));
    assertEquals("inventory-b",
            changed.headers().getFirst("X-LB-Selected-Instance"));
    assertNull(
            original.headers().getFirst("X-LB-Selected-Instance"));
}
~~~

Các imports chính gồm **java.net.URI**, **HttpMethod**, **ClientRequest**, **DefaultServiceInstance**, **ServiceInstance**, **LoadBalancerClientRequestTransformer**, JUnit assertions. Không cần mở socket hay subscribe Mono vì đang gọi trực tiếp method transformer.

Đây là unit test **thuần request transformation**. Muốn chứng minh transformer được **Spring Cloud WebClient filter** gọi đúng lúc, phải dùng integration test hoặc test filter đã cấu hình với ReactiveLoadBalancer.

### 16.1. Kiểm tra nhiều transformer có thứ tự

Có thể tạo hai transformers:

~~~java
LoadBalancerClientRequestTransformer first =
        (request, instance) ->
                ClientRequest.from(request)
                        .headers(h -> h.set("X-Phase", "first"))
                        .build();

LoadBalancerClientRequestTransformer second =
        (request, instance) ->
                ClientRequest.from(request)
                        .headers(h -> h.set("X-Phase", "second"))
                        .build();

ClientRequest afterFirst =
        first.transformRequest(original, instance);
ClientRequest afterSecond =
        second.transformRequest(afterFirst, instance);

assertEquals("second",
        afterSecond.headers().getFirst("X-Phase"));
~~~

Đoạn này chỉ kiểm tra **composition**, không phải Spring bean ordering. Trong integration test, nếu thứ tự là yêu cầu cứng, xác minh thứ tự thực khi beans được framework sắp xếp bằng @Order và khi cấu hình được auto-injected.

## 17. Unit test Feign transformer: giữ method, URL và body

Một biến đổi đúng kiểu Feign phải không làm mất dữ liệu của request gốc:

~~~java
@Test
void feignTransformerPreservesMethodUrlAndBody() {
    byte[] body = "{\"sku\":\"BOOK-01\"}"
            .getBytes(StandardCharsets.UTF_8);

    Request original = Request.create(
            Request.HttpMethod.POST,
            "http://inventory-service/api/reservations",
            Map.of("Content-Type", List.of("application/json")),
            body,
            StandardCharsets.UTF_8,
            new RequestTemplate());

    ServiceInstance selected = new DefaultServiceInstance(
            "inventory-c", "inventory-service",
            "localhost", 8083, false);

    LoadBalancerFeignRequestTransformer transformer =
            new InventoryFeignTransformers().selectedInstanceHeader();

    Request changed = transformer.transformRequest(original, selected);

    assertEquals(original.httpMethod(), changed.httpMethod());
    assertEquals(original.url(), changed.url());
    assertArrayEquals(body, changed.body());
    assertEquals(
            List.of("inventory-c"),
            List.copyOf(changed.headers().get("X-LB-Selected-Instance")));
}
~~~

Các imports gồm **feign.Request**, **feign.RequestTemplate**, **StandardCharsets**, **Map**, **List**, **DefaultServiceInstance** và interface transformer của Spring Cloud OpenFeign. Cần kiểm tra overload **Request.create** được cung cấp bởi phiên bản OpenFeign đang dùng.

**Đây không phải test retry POST**: test chỉ xác minh transformer không làm mất body. Việc gửi lại POST có side effect phải tuân theo idempotency policy của nghiệp vụ.

## 18. Integration test: xác minh header tại backend HTTP thật

Một unit test gọi transformer trực tiếp có thể pass ngay cả khi **client không hề dùng @LoadBalanced**. Integration test cần tạo request theo **service ID**, cho LoadBalancer chọn instance, rồi xem backend **thật sự nhận header nào**.

Fixture:

~~~text
        GET http://inventory-service/api/stock/X
                         |
                         v
                  Spring LoadBalancer
                       /     \
                      /       \
             A localhost:portA  B localhost:portB
                  |                 |
             MockWebServer A   MockWebServer B
                  |                 |
              observe:         observe:
              method, URI,     method, URI,
              X-LB-Selected-Port
~~~

### 18.1. Một ví dụ Spring Boot + MockWebServer cho WebClient

Để tránh phụ thuộc **getInstanceId()** của SimpleDiscoveryClient, fixture này dùng header **X-LB-Selected-Port**; port luôn được lấy trực tiếp từ ServiceInstance đã chọn. Ví dụ rút gọn nhưng có cấu trúc test hoàn chỉnh:

~~~java
@SpringBootTest(
        classes = RequestTransformerIT.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class RequestTransformerIT {

    static final MockWebServer A = new MockWebServer();
    static final MockWebServer B = new MockWebServer();

    static {
        try {
            A.start();
            B.start();
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @DynamicPropertySource
    static void instances(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri",
            () -> A.url("/").toString());
        registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[1].uri",
            () -> B.url("/").toString());
        registry.add(
            "spring.cloud.loadbalancer.retry.enabled",
            () -> "false");
    }

    @Autowired
    @LoadBalanced
    WebClient.Builder builder;

    @Test
    void transformerRunsAfterSelectionAndReachesBackend() throws Exception {
        for (int i = 0; i < 6; i++) {
            A.enqueue(new MockResponse().setBody("A"));
            B.enqueue(new MockResponse().setBody("B"));
        }

        WebClient webClient = builder
                .baseUrl("http://inventory-service")
                .build();

        for (int i = 0; i < 6; i++) {
            StepVerifier.create(webClient.get()
                    .uri("/api/stock/{sku}?wh={wh}", "BOOK-01", "HCM")
                    .retrieve()
                    .bodyToMono(String.class))
                    .expectNextMatches(body -> Set.of("A", "B").contains(body))
                    .verifyComplete();
        }

        int countA = A.getRequestCount();
        int countB = B.getRequestCount();
        assertEquals(6, countA + countB);
        assertTrue(countA > 0);
        assertTrue(countB > 0);

        for (int i = 0; i < countA; i++) {
            RecordedRequest request = A.takeRequest(1, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("/api/stock/BOOK-01?wh=HCM", request.getPath());
            assertEquals(Integer.toString(A.getPort()),
                    request.getHeader("X-LB-Selected-Port"));
        }

        for (int i = 0; i < countB; i++) {
            RecordedRequest request = B.takeRequest(1, TimeUnit.SECONDS);
            assertNotNull(request);
            assertEquals("/api/stock/BOOK-01?wh=HCM", request.getPath());
            assertEquals(Integer.toString(B.getPort()),
                    request.getHeader("X-LB-Selected-Port"));
        }
    }

    @AfterAll
    static void shutdown() throws IOException {
        A.shutdown();
        B.shutdown();
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        @LoadBalanced
        WebClient.Builder builder() {
            return WebClient.builder();
        }

        @Bean
        LoadBalancerClientRequestTransformer selectedPort() {
            return (request, instance) ->
                    ClientRequest.from(request)
                            .headers(h -> h.set(
                                    "X-LB-Selected-Port",
                                    Integer.toString(instance.getPort())))
                            .build();
        }
    }
}
~~~

**Thư viện/test imports:** Spring Boot Test, Spring Context/Test, JUnit Jupiter, Reactor Test, Spring Cloud LoadBalancer và **OkHttp MockWebServer 4.x** (package okhttp3.mockwebserver); cần import các class nêu trong đoạn test, **java.io.IOException**, **java.util.Set**, **java.util.concurrent.TimeUnit**, **org.springframework.web.reactive.function.client.WebClient**.

Fixture giả định:

- SimpleDiscoveryClient được Spring tạo và trả đúng hai service instances từ properties.
- Chính sách chọn đang dùng Round Robin với danh sách hai bản sao, không bị zone/health/hint filter làm mất ứng viên.
- Không có request đồng thời từ test khác dùng chung Spring ApplicationContext/MockWebServer.
- HTTP client đã thực sự nhận LoadBalancer filter từ bean **@LoadBalanced WebClient.Builder**.

**Không assert request đầu luôn đến A.** Round Robin có thể bắt đầu ở vị trí khác; điều cần xác minh là **mỗi request thực đến host/port được chọn** và tổng requests đúng.

### 18.2. Kiểm thử blocking RestClient/RestTemplate

Với RestClient, cùng fixture có thể đăng ký:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}

@Bean
LoadBalancerRequestTransformer selectedPort() {
    return (request, instance) -> {
        if (instance == null) {
            return request;
        }
        return new HttpRequestWrapper(request) {
            @Override
            public HttpHeaders getHeaders() {
                HttpHeaders copy = new HttpHeaders();
                copy.putAll(super.getHeaders());
                copy.set("X-LB-Selected-Port",
                        Integer.toString(instance.getPort()));
                return copy;
            }
        };
    };
}
~~~

Sau đó gọi **http://inventory-service/...** bằng RestClient được build từ builder đó, và đọc **RecordedRequest** tương tự. Đừng gửi thẳng localhost rồi kết luận blocking LoadBalancer interceptor đã hoạt động.

### 18.3. Kiểm thử OpenFeign

Tạo **@FeignClient(name = "inventory-service")** không khai báo **url**, thêm **LoadBalancerFeignRequestTransformer** ghi header **X-LB-Selected-Port** và kiểm tra MockWebServer nhận header tương ứng port đã chọn. Kiểm tra cả GET và POST test payload để bảo đảm URL/method/body được giữ nguyên.

OpenFeign có thể dùng client/retry khác với RestClient, vì vậy **không tái sử dụng số attempts mong đợi** từ một bài test WebClient nếu chưa đồng nhất retry config.

## 19. Test các tình huống biên và lỗi

Nhiều lỗi của transformer chỉ xuất hiện khi discovery metadata bị thiếu, có retries hoặc một filter khác chạm cùng header. Một bộ kiểm thử tốt không chỉ chứa **happy path**.

| Case | Đầu vào/test setup | Kỳ vọng |
| --- | --- | --- |
| Có một instance | [A] | Transformer nhận A; header phản ánh A |
| Có hai instances | [A, B] | Header phù hợp instance thực tế của mỗi HTTP attempt |
| Không có instance | [] | LoadBalancer báo lỗi/no-instance; không gửi request tới backend |
| instance.getInstanceId() null | ID null | Bỏ header hoặc xử lý theo contract, không ném NPE |
| Metadata thiếu key zone | metadata={} | Không thêm X-Selected-Zone |
| Metadata zone ngoài allowlist | zone=unknown | Không đưa giá trị vào header |
| Caller tự gửi X-LB-Selected-Instance | header giả mạo | Transformer set giá trị mới, không tạo hai values |
| Hai transformers cùng ghi header | @Order khác nhau | Giá trị cuối xác định đúng thứ tự |
| GET có query/encoding | URI có ký tự encode | Method, path, query vẫn nguyên |
| POST có JSON body | body, Content-Type | Body/method/charset không bị mất |
| Retry cùng instance | A → A | Header ở mỗi attempt vẫn phản ánh A |
| Retry chọn instance khác | A → B | Header lần sau phản ánh B, không dùng cached ID cũ |
| TLS/scheme HTTPS | Instance secure, cert/SAN hợp lệ | Không sửa Host/SNI làm lỗi handshake |
| Service khác Payment | Không phải inventory-service | Không rò header/credential chỉ dành Inventory |
| WebClient cancellation | Mono bị cancel | Transformer không giữ tài nguyên hoặc block |

### 19.1. Không có ServiceInstance

Khi supplier rỗng, bạn có thể thấy lỗi hoặc response lỗi từ lớp LoadBalancer. Tùy bản Spring Cloud và cấu hình, WebClient có thể nhận một phản hồi **503 Service Unavailable** (một số adapter có tùy chọn 404), nhưng đây **không phải** backend thật trả 503.

Test cần xác minh:

~~~text
source instance list = []
selected instance    = none
backend request count = 0
caller result         = error/no-instance theo contract
~~~

**Không bắt buộc transformer phải được invoke với instance=null** trong mọi tích hợp. Unit test null guard là một bài test phòng vệ; integration test không nên đòi transformer tạo header instance cho một request không có đích.

### 19.2. Timeout trước/sau transformer

Nếu timeout xảy ra:

- **Trước khi chọn instance** (discovery chậm, publisher cancellation): có thể chưa từng gọi transformer.
- **Sau khi chọn nhưng trước HTTP send** (pool acquire/connect): có thể transformer đã chạy nhưng backend chưa nhận request.
- **Sau khi backend nhận request** (response/read timeout): backend có thể đã xử lý; transformer thường không liên quan đến timeout.

Vì vậy, số **transformer invocation** không phải số request **backend đã xử lý**, càng không phải số logical successes. Hãy đo HTTP client attempts, backend recorded requests và trace state riêng biệt.

### 19.3. Thứ tự filter và thuộc tính security

Một test nên tạo:

~~~text
Authorization từ auth filter
X-Correlation-Id từ tracing
X-LB-Selected-Instance từ transformer
~~~

Rồi kiểm tra cả ba ở MockWebServer. Sau đó thêm một request tới **payment-service** và chắc chắn credential/header chỉ dành Inventory không bị phát sang Payment. Nếu filter/proxy rewrite header, test sẽ phát hiện before/after selection integration không đúng kỳ vọng.

## 20. Observability và performance của transformer

Một transformer tốt là một phép biến đổi ngắn, không truy cập I/O và không giữ state thay đổi giữa concurrent requests. Nếu mọi request đều phải gọi registry hoặc backend từ transformer, throughput sẽ chịu một **hop mạng bổ sung** ngoài LoadBalancer.

### 20.1. Log/metric gì là đủ?

| Trường | Mục đích | Lưu ý |
| --- | --- | --- |
| logical service ID | Inventory/Payment/Catalog | Có cardinality thấp |
| selected instance ID | Đối chiếu host/instance đã chọn | Tránh nhãn metric high-cardinality nếu instance churn nhanh |
| selected zone | Chẩn đoán zone routing | Chỉ nhận từ metadata đã kiểm soát |
| operation/URI template | Nhóm GET stock, reserve, etc. | Không log SKU/customer ID thật vào metric tag |
| retry attempt | Phân biệt logical call với HTTP attempt | Lấy từ retry context đúng scope |
| transform outcome | Header added/skipped/invalid metadata | Không ghi nội dung credential |
| request status/duration | Thành công, 4xx/5xx, timeout | Tách lỗi transport với backend status |
| correlation/trace ID | Nối log của caller và backend | Không dùng làm metric tag cardinality cao |

Spring Cloud LoadBalancer hỗ trợ các meter như:

~~~text
loadbalancer.requests.success
loadbalancer.requests.failed
loadbalancer.requests.discard
~~~

Các tên trên được tài liệu Spring Cloud LoadBalancer nêu cho thống kê request trong tích hợp hỗ trợ; chúng **không mặc định đo riêng số lần transformer chạy**, và availability phụ thuộc dependency/auto-configuration.

Nếu cần metric riêng, đặt:

~~~text
lb_transformer_applied_total{client="webclient",service="inventory-service"}
lb_transformer_skipped_total{reason="missing-instance-id"}
lb_transformer_invalid_metadata_total{key="zone"}
~~~

Đây là **tên metric gợi ý**, không phải meter Spring tạo sẵn. Không dùng **instanceId, trace ID, SKU, user ID** làm tag không giới hạn; ghi những giá trị đó vào traces/logs với sampling và masking phù hợp.

### 20.2. Không ghi log payload hoặc token trong transformer

Transformer có thể nhìn thấy headers request và selected ServiceInstance. Đừng log:

- Authorization/Bearer token.
- Cookie, Set-Cookie hoặc API key.
- Raw URL chứa secret/query parameter nhạy cảm.
- Full request body chứa dữ liệu khách hàng.
- ServiceInstance metadata chứa internal secrets.

Chỉ ghi các trường kỹ thuật được allowlist. Nếu có một lỗi header validation, log tên key, loại lỗi và service ID; tránh in raw giá trị header không đáng tin cậy.

### 20.3. Transformer không phải nơi làm health check

Không viết:

~~~java
if (!httpPing(instance.getHost(), instance.getPort())) {
    // Chọn instance khác bằng cách gọi REST trong transformer.
}
~~~

Việc đó gây:

- I/O nhân đôi trên mỗi attempt.
- Chậm đường request và gây backpressure trên WebClient.
- Race condition giữa ping và HTTP request thật.
- Bypass retry/deadline và metrics chính thức.

Nếu cần health-aware selection, dùng **HealthCheckServiceInstanceListSupplier** hoặc discovery/provider health semantics. Nếu cần circuit breaker, triển khai theo operation và policy đã chọn.

## 21. Hướng dẫn chẩn đoán theo từng biểu hiện

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không có header selected instance | Client không @LoadBalanced hoặc transformer bean không nằm trong context được tích hợp | Xác minh bean, starter, filter/interceptor |
| Không thấy transformer chạy trong unit test WebClient | Mono chưa subscribe | StepVerifier.verify hoặc subscriber phù hợp |
| Header xuất hiện nhưng ID sai | Singleton cache instance hoặc logic dùng metadata ngoài request | Luôn dùng tham số ServiceInstance hiện tại |
| Header có hai instance IDs | Dùng add() thay vì set() hoặc nhiều transformers | Xác định owner/thứ tự, dùng set() |
| Header đổi sai sau retry | Retry nằm ở tầng khác, transformer không được gọi như kỳ vọng | Test HTTP attempts với selected instance |
| Backend nhận header của service khác | Transformer quá global, không guard service ID | Dedicated client/per-service guard |
| 401/403 sau khi thêm transformer | Đụng Authorization/Host/forwarded security headers | Tách auth provider và transformer |
| SSLHandshakeException sau rewrite | URI host/SNI/cert SAN không tương thích | Kiểm tra physical URI và certificate |
| Request thực tới B nhưng metric ghi A | Transformer tự rewrite URL hoặc tracing sai hook | Không đổi host hậu selection, so sánh recorded request |
| Không có instance và backend không nhận request | Discovery/health/supplier trả rỗng | Chẩn đoán provider/cache/filter |
| HTTP 503 mà tưởng transformer lỗi | Backend hoặc LoadBalancer trả 503 | Phân biệt backend request count |
| WebClient event loop bị chặn | Transformer thực hiện blocking I/O | Loại I/O ra khỏi transformer |
| CPU/GC tăng sau thêm transformer | Copy/serialize metadata quá lớn mỗi request | Chỉ thêm headers nhỏ, avoid heavy allocations |
| Feign Request bị mất body | Request.create không giữ body/charset/template | Copy các trường từ original Request |
| RestClient hoạt động nhưng RestTemplate không | Hai beans/client integration khác nhau | Kiểm tra @LoadBalanced và request factories |
| Round Robin không luân phiên đúng A/B | Snapshot/seed/concurrency/filter/retry khác giả định | Test membership/selected port, không cứng lượt đầu |

### 21.1. Quy trình debug mười bước

~~~text
1. Code gọi client nào? RestTemplate, RestClient, WebClient, Feign?
2. Client có @LoadBalanced hoặc filter/interceptor LoadBalancer?
3. URI logic có host đúng service ID không?
4. ServiceInstanceListSupplier trả những instance nào?
5. LB chọn ServiceInstance ID/host/port nào?
6. Transformer bean thuộc đúng interface và Spring context?
7. Transformer có được gọi trên attempt cụ thể không?
8. Header/URI request sau biến đổi là gì (đã mask)?
9. MockWebServer/backend nào thực sự nhận HTTP request?
10. Retry, timeout, auth, proxy hoặc filter nào sửa/thay kết quả?
~~~

Nếu thiếu bước 9, bạn mới xác minh **ý định của client**, chưa chứng minh HTTP request đã đến đúng đích với header cuối cùng.

## 22. Case study: header chẩn đoán có kiểm soát cho Inventory

### Bối cảnh

Order Service gọi Inventory bằng **RestClient** và **WebClient**. Cùng lúc, Inventory có ba bản sao A/B/C ở hai zone. Đội vận hành muốn biết **request nào đã được gửi tới instance nào**, nhất là khi retry đổi đích.

Yêu cầu:

- Giữ request method, body, path, query và authentication như cũ.
- Bổ sung **X-LB-Selected-Instance** sau khi có quyết định chọn instance.
- Chỉ áp dụng với **inventory-service**.
- Bỏ header nếu instance ID không hợp lệ.
- Không cho caller giả mạo giá trị nội bộ.
- Có test chứng minh retry A→B ghi đúng header mỗi attempt.

### Thiết kế

~~~mermaid
flowchart TD
    A["Order HTTP adapter"] --> B["LoadBalanced client"]
    B --> C["Supplier lấy instance list"]
    C --> D["LB chọn A/B/C"]
    D --> E{"serviceId = inventory-service?"}
    E -->|Không| F["Giữ request gốc"]
    E -->|Có| G{"instanceId hợp lệ?"}
    G -->|Không| H["Bỏ header + metric invalid"]
    G -->|Có| I["Set X-LB-Selected-Instance"]
    I --> J["HTTP connector"]
    F --> J
    H --> J
    J --> K["Backend ghi trace với identity đã xác thực"]
~~~

**Quyết định kỹ thuật:** một transformer cho blocking clients, một transformer cho WebClient; cùng một helper **InstanceHeaderPolicy.validId** để tránh quy tắc khác nhau. Nếu Feign cũng dùng trong cùng dự án, thêm một transformer Feign tương ứng.

### Kịch bản chấp nhận

| Điều kiện | Assertion |
| --- | --- |
| A được chọn | A nhận header inventory-a |
| B được chọn | B nhận header inventory-b |
| Caller có header giả | Giá trị tại backend khớp instance thật, một value |
| Retry A→B | Request ở A và B có header khác nhau đúng đích |
| Payment được gọi | Không có header của Inventory |
| Registry trả null ID | Không NPE, header bị bỏ có kiểm soát |
| Header vượt allowlist | Không chuyển giá trị thô vào backend |

**Không yêu cầu transformer làm thay LoadBalancer**: A/B/C được chọn bởi supplier/algorithm; header chỉ phản ánh quyết định đã có. Khi backend thật cần xác thực identity caller, tiếp tục dùng **mTLS/JWT** thay vì tin request header.

## 23. Bài tập tự đánh giá có lời giải

### 23.1. Bài tập A: nên dùng Supplier hay Transformer?

Yêu cầu: request có header **X-SC-LB-Hint: canary** phải đi tới những ServiceInstance được đánh dấu canary, không gửi tới stable nếu còn canary hợp lệ.

**Câu hỏi:** Có nên viết LoadBalancerClientRequestTransformer để thay URL sang instance canary sau khi chọn không?

**Đáp án:** Không. Đây là bài toán **lọc/chọn instance** trước khi có lựa chọn. Dùng **HintBasedServiceInstanceListSupplier** hoặc policy tương đương; transformer có thể thêm header quan sát **instance đã chọn**, không dùng để đảo ngược quyết định chọn.

### 23.2. Bài tập B: hai transformer cùng thay header

~~~text
Transformer #1: set X-Environment = prod
Transformer #2: add X-Environment = test
~~~

**Câu hỏi:** Backend có thể thấy gì? Cách sửa?

**Đáp án:** Header có thể có **nhiều giá trị**, phụ thuộc builder/HTTP transport. Phải xác định **một chủ sở hữu**, sử dụng **set** thay cho add nếu muốn một giá trị, đặt thứ tự rõ bằng @Order và test kết quả sau toàn bộ chuỗi.

### 23.3. Bài tập C: retry đổi instance

~~~text
GET Inventory
Attempt 1: A -> 503
Attempt 2: B -> 200
Transformer giữ inventory-a trong một field singleton.
~~~

**Câu hỏi:** Điều gì sai?

**Đáp án:** Header lần thứ hai có thể vẫn ghi **inventory-a** dù request đến B. Không cache selected instance trong singleton field; dùng tham số **ServiceInstance của mỗi invocation**. Muốn xác minh, đếm requests ở A/B và assert header tương ứng.

### 23.4. Bài tập D: transformer trả request có URL khác

LoadBalancer chọn **inventory-a.internal**, transformer đọc một metadata tự đăng ký và thay URL tới **unknown-host.example**.

**Câu hỏi:** Rủi ro chính?

**Đáp án:** Bypass tập ứng viên đã được chọn, nguy cơ **SSRF/token leakage**, mismatch metric, TLS hostname/SNI và sai retry policy. Dữ liệu metadata không phải authorization. Nếu thực sự cần định tuyến tới host khác, thay thiết kế discovery/supplier hoặc gateway có trust boundary rõ, không rewrite mù sau selection.

### 23.5. Bài tập E: dùng WebClient nhưng transformer không chạy

~~~java
Mono<String> result = webClient.get()
        .uri("http://inventory-service/ping")
        .retrieve()
        .bodyToMono(String.class);
~~~

**Câu hỏi:** Vì sao unit test chưa thấy transformer invocation?

**Đáp án:** Mono thường **chưa được subscribe**, và WebClient có thể **chưa được gắn LoadBalancer** nếu builder không @LoadBalanced. Dùng StepVerifier/subscription và kiểm tra bean/filter. Đừng gọi đơn thuần **result.toString()** rồi kết luận HTTP đã thực thi.

### 23.6. Bài tập F: dùng transformer như cơ chế xác thực

Backend bỏ qua JWT nếu có:

~~~http
X-LB-Selected-Instance: inventory-a
~~~

**Câu hỏi:** Thiết kế đó có an toàn không?

**Đáp án:** Không. Header do HTTP client tự gửi có thể bị giả mạo nếu trust boundary không được bảo vệ; hơn nữa instance ID không chứng minh danh tính caller. Backend vẫn cần **mTLS/JWT hoặc cơ chế authn/authz đáng tin cậy** và giới hạn traffic theo network policy.

## 24. Checklist trước khi dùng request transformer trong production

- [ ] Hiểu đúng **Transformer chạy sau khi chọn ServiceInstance**, không thay supplier/algorithm.
- [ ] Chọn đúng interface: LoadBalancerRequestTransformer, LoadBalancerClientRequestTransformer hoặc LoadBalancerFeignRequestTransformer.
- [ ] HTTP client thật sự được tích hợp Spring Cloud LoadBalancer và gọi bằng **service ID**.
- [ ] Không gắn ReactorLoadBalancerExchangeFilterFunction hai lần vào WebClient.
- [ ] Transformer được Spring đăng ký đúng ApplicationContext/bean scope.
- [ ] Nếu chỉ áp dụng cho Inventory, có điều kiện service ID/dedicated client rõ.
- [ ] Không thực hiện I/O blocking, registry lookup, token fetch hoặc recursive HTTP call trong transformer.
- [ ] Bảo toàn method, URI, query, path, body, charset và Content-Type/Length.
- [ ] Với blocking clients, ưu tiên HttpRequestWrapper thay vì mutate request gốc.
- [ ] Với WebClient, ưu tiên ClientRequest.from(request) và tạo request mới.
- [ ] Với Feign, sao chép headers và giữ đầy đủ fields trong Request.create.
- [ ] Dùng **set** khi cần một header duy nhất; tránh add nhiều lần ở retry/filters.
- [ ] Có @Order rõ ràng nếu nhiều transformers cùng có thể tác động tới một header.
- [ ] Header mới có tên nội bộ cố định, không bị caller điều khiển.
- [ ] Instance ID/metadata đã được allowlist và kiểm tra độ dài/ký tự.
- [ ] Không coi selected instance header là authentication/authorization.
- [ ] Không ghi đè Authorization, Cookie, Host, Content-Length và hop-by-hop headers khi không có lý do.
- [ ] Không rewrite tới host nằm ngoài ServiceInstance selection/trust policy.
- [ ] TLS SAN/SNI/hostname verification vẫn đúng với URI vật lý.
- [ ] Phân biệt hint/zone/API version **trước lựa chọn** với header **sau lựa chọn**.
- [ ] Retry không dựa trên instance ID cached từ attempt cũ.
- [ ] Không dùng mutable singleton counter để tính logical retry attempt.
- [ ] Có unit test request/header immutability và null/invalid metadata.
- [ ] Có integration test thông qua service ID với MockWebServer/WireMock.
- [ ] Kiểm tra selected-instance header tại server nhận HTTP thật.
- [ ] Test no-instance, 404/503, timeout, retry A→B và cancellation (nếu reactive).
- [ ] Tracing/metrics ghi đúng layer và không lộ credential hoặc high-cardinality tags.
- [ ] Giữ các Spring Boot customizers cho observability/TLS khi tạo custom HTTP client builders.
- [ ] Đối chiếu interface và Request.create overload theo BOM/release train đang dùng.

## 25. Kết luận

**Request transformer là điểm mở rộng nhỏ nhưng hữu ích của Spring Cloud LoadBalancer**, cho phép biến đổi request bằng thông tin **ServiceInstance đã được chọn**. Nó đặc biệt phù hợp với các trường hợp cần thêm header kỹ thuật như selected instance/zone để debug giao tiếp giữa dịch vụ, kiểm chứng retry/routing hoặc truyền metadata đã được kiểm soát đến backend tin cậy.

Ba nguyên tắc cần ghi nhớ:

1. **Chọn đích trước, biến đổi request sau:** Supplier/LoadBalancer quyết định instance. Transformer không nên tự chọn lại host.
2. **Mỗi HTTP client có interface riêng:** RestTemplate/RestClient dùng LoadBalancerRequestTransformer; WebClient dùng LoadBalancerClientRequestTransformer; OpenFeign dùng LoadBalancerFeignRequestTransformer.
3. **Không đánh đổi bảo mật và tính đúng đắn:** Bảo toàn request gốc, validate metadata, quản lý thứ tự nhiều transformer, tránh rò Authorization và kiểm thử HTTP request thật ở backend.

Khi hệ thống có retry, timeout, health check và nhiều bản sao, hãy kiểm tra **mỗi attempt có header tương ứng với instance thực sự nhận request**, không chỉ nhìn một lần gọi method Java hoặc một unit test transformer riêng lẻ. Thiết kế đúng sẽ tăng khả năng quan sát mà không phá vỡ quyết định cân bằng tải.

## 26. Tài liệu tham khảo

- [Spring Cloud LoadBalancer – Transform the load-balanced HTTP request](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#transform-the-load-balanced-http-request): ví dụ chính thức cho LoadBalancerRequestTransformer và LoadBalancerClientRequestTransformer, multiple transformers và ordering.
- [Spring Cloud Commons – LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, discovery, health, hint, zone, request context, retry-aware selection và metrics.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): cấu hình @LoadBalanced RestTemplate, RestClient.Builder và WebClient.Builder.
- [Spring Cloud Commons – LoadBalancerRequestTransformer source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerRequestTransformer.java): chữ ký blocking transformRequest và DEFAULT_ORDER.
- [Spring Cloud Commons – LoadBalancerClientRequestTransformer Javadoc](https://www.javadoc.io/static/org.springframework.cloud/spring-cloud-commons/3.1.9/org/springframework/cloud/client/loadbalancer/reactive/LoadBalancerClientRequestTransformer.html): kiểu ClientRequest, ServiceInstance và DEFAULT_ORDER.
- [Spring Cloud OpenFeign – Transform the load-balanced HTTP request](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html#transform-the-load-balanced-http-request): LoadBalancerFeignRequestTransformer, Request.create, header copies và X-Forwarded support.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): @FeignClient name vs URL, LoadBalancer integration, RequestInterceptor và retry.
- [Spring Framework – ClientRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientRequest.html): ClientRequest.from, headers, url, method và build.
- [Spring Framework – HttpRequestWrapper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/support/HttpRequestWrapper.html): cơ chế bọc HttpRequest.
- [Spring Framework – WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): ExchangeFilterFunction, thứ tự filter và request processing.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient/RestTemplate và ClientHttpRequestInterceptor.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): HTTP mock server integration testing.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, subscription và kiểm thử Mono/Flux.
- [Spring Security – OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): token acquisition và authorization qua interceptor/filter chuyên dụng.

