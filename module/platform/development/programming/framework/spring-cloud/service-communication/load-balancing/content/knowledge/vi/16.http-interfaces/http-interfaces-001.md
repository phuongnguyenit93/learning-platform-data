# HTTP Service Interface và các annotation mô tả lời gọi

Khi giao tiếp giữa các microservice bằng HTTP, cách quen thuộc là gọi trực tiếp `RestClient.get().uri(...).retrieve()` hoặc `WebClient.get().uri(...).retrieve()` ở từng service. Nếu một ứng dụng có nhiều endpoint như lấy sản phẩm, tìm kiếm, tạo và cập nhật dữ liệu, mã xây dựng HTTP request có thể lặp lại tại nhiều vị trí.

**HTTP Service Interface** trong Spring Framework cho phép khai báo **hợp đồng gọi HTTP dưới dạng một Java interface**. Bạn mô tả HTTP method, URL và các tham số bằng annotation như `@HttpExchange`, `@GetExchange`, `@PostExchange` và `@PathVariable`. Sau đó, `HttpServiceProxyFactory` tạo một proxy thực hiện HTTP request thông qua adapter của `RestClient` hoặc `WebClient`.

Bài học thuộc chương **HTTP Interface** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu không chỉ là biết cú pháp annotation, mà còn hiểu **cách interface được kết nối với Spring Cloud LoadBalancer** để gọi theo service ID, tận dụng discovery và health check, đồng thời xử lý timeout, retry và lỗi khi giao tiếp liên dịch vụ.

> Cần phân biệt: **HTTP Service Interface** là cơ chế khai báo **client gọi HTTP**, không phải một controller tự động công bố API phía server. Nó cũng không mặc nhiên bật cân bằng tải; phải tạo proxy từ HTTP client đã được tích hợp Spring Cloud LoadBalancer.

## 1. Từ HTTP client viết tay đến hợp đồng khai báo

Một đoạn sử dụng RestClient trực tiếp:

~~~java
ItemDto item = restClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);
~~~

Cách này phù hợp cho ít lời gọi. Nhưng khi có nhiều thao tác, ứng dụng có thể lặp URL, header, body conversion và logic cấu tạo request.

HTTP Service Interface chuyển phần mô tả lời gọi vào interface:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange("/api/items")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

Ở service sử dụng, mã nghiệp vụ trở nên ngắn:

~~~java
ItemDto item = catalogHttpApi.findById(itemId);
~~~

Proxy sinh ra từ interface sẽ chuyển method call thành HTTP request. Mã gọi vẫn có lỗi HTTP/mạng như trước: khai báo interface **không làm request trở thành local call**, không tự bổ sung transaction phân tán và không thay thế chính sách timeout hoặc retry.

~~~mermaid
flowchart LR
    A["order-service: catalogHttpApi.findById(id)"] --> I["HTTP Service Interface proxy"]
    I --> H["RestClient / WebClient adapter"]
    H --> LB["Spring Cloud LoadBalancer"]
    DISC["ServiceInstanceListSupplier / discovery"] --> LB
    LB --> X["catalog-a"]
    LB --> Y["catalog-b"]
~~~

## 2. Vai trò của từng thành phần

| Thành phần | Trách nhiệm | Không tự làm gì? |
|---|---|---|
| `@HttpExchange` | Khai báo thông tin HTTP chung ở interface hoặc một method | Không tạo bean hay gửi request |
| `@GetExchange`, `@PostExchange`, ... | Khai báo HTTP method, URL và metadata request | Không tự chọn instance |
| `@PathVariable`, `@RequestParam`, ... | Ánh xạ đối số Java vào URL/header/body | Không xác thực nghiệp vụ của server |
| `HttpServiceProxyFactory` | Tạo proxy từ interface | Không cung cấp discovery nếu adapter không có |
| `RestClientAdapter` | Thực hiện lời gọi qua RestClient đồng bộ | Không làm caller non-blocking |
| `WebClientAdapter` | Thực hiện lời gọi qua WebClient reactive | Không bảo đảm server trả dữ liệu hợp lệ |
| `@LoadBalanced RestClient.Builder` hoặc `WebClient.Builder` | Gắn tích hợp LoadBalancer cho HTTP client được tạo | Không tự tạo instance khi registry rỗng |
| `ServiceInstanceListSupplier` | Cung cấp các `ServiceInstance` ứng viên theo service ID | Không đảm bảo mỗi instance hiện còn khỏe |
| `RoundRobinLoadBalancer` hoặc bộ chọn khác | Chọn instance từ tập ứng viên | Không đo tải thực tế nếu không có dữ liệu bổ sung |

Ba bước độc lập nhưng phối hợp:

1. **Khai báo hợp đồng**: interface định nghĩa method Java tương ứng request HTTP nào.
2. **Chọn công cụ thực thi**: proxy được nối với RestClient hoặc WebClient.
3. **Chọn đích**: nếu client là load-balanced, hostname logic được giải thành một instance thực.

## 3. @HttpExchange: annotation gốc

`@HttpExchange` thuộc package `org.springframework.web.service.annotation`. Có thể dùng ở **mức interface** để khai báo thuộc tính chung, hoặc dùng trực tiếp trên method.

Ví dụ:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(
    url = "/api/items",
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {
    // Các phương thức HTTP được khai báo bên trong
}
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| `url` / giá trị rút gọn | Đường dẫn chung hoặc đường dẫn method | `"/api/items"` |
| `method` | HTTP method khi dùng `@HttpExchange` trực tiếp ở method | `"GET"`, `"POST"` |
| `contentType` | Giá trị Content-Type dự kiến của request | `"application/json"` |
| `accept` | Giá trị Accept mà client mong nhận | `"application/json"` |
| `headers` | Các request headers tĩnh được khai báo | `"X-Caller=order-service"` |

`Content-Type` nói về **định dạng dữ liệu được gửi đi**, trong khi `Accept` nói về **định dạng response mong muốn nhận**. Với GET không có body, việc đặt Content-Type thường không cần thiết. Không xem hai header này là tương đương.

### Kết hợp annotation mức interface và method

~~~java
@HttpExchange(url = "/api/items", accept = "application/json")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

Khi gọi `findById("42")` và client có base URL `http://catalog-service`, request logic là:

~~~http
GET /api/items/42 HTTP/1.1
Host: catalog-service
Accept: application/json
~~~

Base URL xác định service logic hoặc host. `url` của interface tạo prefix, đường dẫn của method bổ sung phần cụ thể. Các thuộc tính được khai báo ở method có thể ghi đè giá trị tương ứng từ mức interface theo quy tắc của Spring Framework.

Không nên khai báo nhiều annotation HTTP method xung đột trên cùng một method, ví dụ vừa `@GetExchange` vừa `@PostExchange`. Chọn một hợp đồng HTTP rõ ràng.

## 4. Nhóm annotation theo HTTP method

Spring Framework có các annotation chuyên biệt được xây trên `@HttpExchange`:

| Annotation | HTTP method | Dùng khi nào? |
|---|---|---|
| `@GetExchange` | GET | Đọc một resource hoặc danh sách |
| `@PostExchange` | POST | Tạo resource hoặc gửi thao tác |
| `@PutExchange` | PUT | Thay thế/cập nhật resource theo contract |
| `@PatchExchange` | PATCH | Cập nhật một phần |
| `@DeleteExchange` | DELETE | Xóa resource hoặc gửi yêu cầu xóa |

Ví dụ trọn bộ khai báo:

~~~java
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.DeleteExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PatchExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.service.annotation.PutExchange;

@HttpExchange(
    url = "/api/items",
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);

    @GetExchange
    List<ItemDto> search(
        @RequestParam("category") String category,
        @RequestParam("limit") int limit
    );

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<ItemDto> create(@RequestBody CreateItemRequest request);

    @PutExchange(
        url = "/{id}",
        contentType = MediaType.APPLICATION_JSON_VALUE
    )
    ItemDto replace(
        @PathVariable("id") String id,
        @RequestBody UpdateItemRequest request
    );

    @PatchExchange(
        url = "/{id}",
        contentType = MediaType.APPLICATION_JSON_VALUE
    )
    ItemDto updatePartially(
        @PathVariable("id") String id,
        @RequestBody PatchItemRequest request
    );

    @DeleteExchange("/{id}")
    ResponseEntity<Void> delete(@PathVariable("id") String id);
}
~~~

Các kiểu DTO minh họa:

~~~java
record ItemDto(String id, String name, int stock) {}

record CreateItemRequest(String name, int stock) {}

record UpdateItemRequest(String name, int stock) {}

record PatchItemRequest(Integer stock) {}
~~~

Các đoạn trên có thể đặt thành file Java tương ứng trong dự án mẫu. Để gọi chạy được, server phải cung cấp các endpoint phù hợp và JSON schema tương ứng. Khai báo client **không tự sinh API server** cho POST/PUT/PATCH/DELETE.

### Khi nào dùng @HttpExchange(method = "...") trực tiếp?

Có thể dùng:

~~~java
@HttpExchange(method = "GET", url = "/{id}")
ItemDto findById(@PathVariable("id") String id);
~~~

Nó diễn đạt tương tự `@GetExchange("/{id}")` khi không cần cấu hình riêng. Trong bài toán phổ biến, annotation chuyên biệt dễ đọc và giảm nguy cơ ghi nhầm HTTP method.

## 5. Annotation mô tả tham số: URL, query, header và body

Thông tin trong chữ ký Java được ánh xạ sang các phần của HTTP request:

~~~mermaid
flowchart TD
    M["Một lời gọi Java method"] --> P["@PathVariable → URI path"]
    M --> Q["@RequestParam → query hoặc parameter"]
    M --> H["@RequestHeader → request header"]
    M --> C["@CookieValue → Cookie"]
    M --> B["@RequestBody → request body"]
    M --> F["@RequestPart → phần multipart"]
~~~

Các annotation tham số thường dùng thuộc `org.springframework.web.bind.annotation`. Chúng cũng xuất hiện trong Spring MVC controllers, nhưng tại đây đang được dùng ở **phía client** thông qua HTTP Service Interface.

### @PathVariable: giá trị động trong đường dẫn

~~~java
@GetExchange("/{id}")
ItemDto findById(@PathVariable("id") String id);
~~~

Gọi `findById("42")` tạo request tới path `/api/items/42`. Tên `id` trong template và annotation phải khớp. Nên chỉ định tên tham số rõ ràng thay vì lệ thuộc cấu hình compiler lưu parameter names.

Không tự ghép URI bằng phép cộng chuỗi từ input người dùng nếu có thể dùng template. Cơ chế dựng URI giúp xử lý encoding theo quy tắc của client; tuy nhiên, ứng dụng vẫn phải kiểm tra định dạng ID hợp lệ và không coi URL encoding là cơ chế kiểm soát quyền truy cập.

### @RequestParam: query parameters

~~~java
@GetExchange
List<ItemDto> search(
    @RequestParam("category") String category,
    @RequestParam("limit") int limit
);
~~~

Gọi `search("paper", 20)` tương ứng:

~~~http
GET /api/items?category=paper&limit=20 HTTP/1.1
~~~

Với filter phức tạp, có thể truyền nhiều tham số hoặc một kiểu chứa query parameters tùy API và hỗ trợ của adapter. Khi có giá trị optional, cần thống nhất cách biểu diễn tham số vắng mặt, không tự suy rằng mọi endpoint coi chuỗi rỗng tương đương thiếu tham số.

### @RequestHeader: header động

~~~java
@GetExchange("/{id}")
ItemDto findWithTrace(
    @PathVariable("id") String id,
    @RequestHeader("X-Correlation-Id") String correlationId
);
~~~

Header giúp truyền correlation ID, tenant context hoặc thông tin kiểm soát phiên làm việc theo contract. Không tự đưa access token, cookie nhạy cảm hoặc user ID vào log khi debug request.

### @RequestBody: payload gửi đi

~~~java
@PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
ItemDto create(@RequestBody CreateItemRequest request);
~~~

Nếu request object là `new CreateItemRequest("Notebook", 7)`, JSON body có thể là:

~~~json
{
  "name": "Notebook",
  "stock": 7
}
~~~

Mã hóa thực tế phụ thuộc HTTP message converter hoặc codec tương ứng với adapter. DTO ở client và server phải tương thích schema; không nhất thiết dùng chung một Java module.

### @CookieValue: dữ liệu từ cookie

~~~java
@GetExchange("/session")
String readSession(@CookieValue("session-id") String sessionId);
~~~

Dùng khi API đích có contract xác thực hoặc nhận diện phiên bằng cookie. Trong giao tiếp service-to-service, token hoặc identity context thường được kiểm soát tập trung; không biến cookie của người dùng thành request tới service khác mà không có mô hình bảo mật rõ ràng.

### @RequestPart: multipart request

~~~java
import org.springframework.core.io.Resource;
import org.springframework.web.bind.annotation.RequestPart;

@PostExchange(
    url = "/import",
    contentType = MediaType.MULTIPART_FORM_DATA_VALUE
)
String importFile(@RequestPart("file") Resource file);
~~~

Mục tiêu là gửi một phần có tên `file` trong multipart body. Cách biểu diễn filename, content type và kích thước thực tế phụ thuộc resource/codec của HTTP adapter. Với file lớn, cần xét streaming và giới hạn bộ nhớ thay vì nạp cả file vào RAM. Đây là endpoint minh họa riêng, không bắt buộc thuộc một inventory API cụ thể.

### @RequestAttribute và các tham số nâng cao

Spring Framework còn có cơ chế truyền request attributes và một số kiểu tham số đặc biệt tùy HTTP adapter. Chỉ sử dụng khi kiểm tra adapter hỗ trợ; **request attribute là dữ liệu cục bộ gắn với request của client**, không giống HTTP header được truyền qua mạng. Khi cần gửi thông tin cho server, dùng header, query hoặc body theo API contract.

## 6. HTTP Interface là client, không phải controller server

Hai vai trò thường dễ bị nhầm vì cùng dùng `@PathVariable` và `@RequestBody`.

**Client contract:**

~~~java
@HttpExchange("/api/items")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

**Server implementation:**

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/items")
class CatalogController {

    @GetMapping("/{id}")
    ItemDto findById(@PathVariable String id) {
        return new ItemDto(id, "Notebook", 7);
    }
}
~~~

Trong ứng dụng server, Spring MVC/WebFlux đăng ký HTTP handler dựa vào `@RestController`/mapping. Trong ứng dụng caller, `HttpServiceProxyFactory` tạo client proxy từ `@HttpExchange`. Hai phần có thể cùng mô tả một HTTP API nhưng **không mặc nhiên tự đồng bộ version**, không tự cung cấp validation, auth hay OpenAPI.

## 7. Tạo HTTP Interface proxy với RestClientAdapter

Spring Framework 6.1+ hỗ trợ HTTP Service Interface trên `RestClient`. Đây là cách phù hợp nếu caller sử dụng mô hình đồng bộ/blocking.

### Bước 1: khai báo dependencies

Trong project dùng Spring Boot + Spring Cloud BOM phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Hai dependency là ví dụ phần lõi; project vẫn cần plugin và dependency management tương thích. `RestClient` xuất hiện từ Spring Framework 6.1; các dự án cũ hơn không thể áp dụng nguyên đoạn cấu hình này mà không nâng cấp framework.

### Bước 2: định nghĩa LoadBalanced builder và proxy

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
class CatalogHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    CatalogHttpApi catalogHttpApi(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder
    ) {
        RestClient client = builder
            .baseUrl("http://catalog-service")
            .build();

        RestClientAdapter adapter = RestClientAdapter.create(client);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter)
                .build();

        return factory.createClient(CatalogHttpApi.class);
    }
}
~~~

Khi gọi `catalogHttpApi.findById("42")`:

1. Proxy đọc metadata `@HttpExchange` và `@GetExchange`.
2. Adapter biến lời gọi method thành request của RestClient.
3. Vì RestClient được tạo từ builder `@LoadBalanced`, host `catalog-service` được xử lý như service ID.
4. `ServiceInstanceListSupplier` cung cấp instance; LoadBalancer chọn một instance.
5. Request được gửi đến host/port thật; response được đọc và ánh xạ về `ItemDto`.

Chính `@LoadBalanced` và tích hợp Spring Cloud mới kết nối HTTP Interface với LoadBalancer. **Chỉ tạo proxy qua `RestClientAdapter` không tự bật discovery** nếu RestClient nền được tạo bình thường.

### Ví dụ sử dụng từ service nghiệp vụ

~~~java
import org.springframework.stereotype.Service;

@Service
class ItemQueryService {

    private final CatalogHttpApi catalog;

    ItemQueryService(CatalogHttpApi catalog) {
        this.catalog = catalog;
    }

    ItemDto loadItem(String id) {
        return catalog.findById(id);
    }
}
~~~

`CatalogHttpApi` là dependency type-safe mà service nghiệp vụ sử dụng. Proxy vẫn thực hiện I/O HTTP đồng bộ; không coi method gọi là hoàn thành tức thời chỉ vì giao diện Java trông như lời gọi local.

## 8. Cấu hình discovery cho lời gọi theo service ID

Để chạy một lab không cần Eureka hoặc Consul, khai báo hai instance:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Chạy hai bản server `catalog-service` với cùng endpoint GET `/api/items/{id}` ở hai cổng:

~~~bash
java -jar catalog-service.jar --server.port=18081
java -jar catalog-service.jar --server.port=18082
~~~

Hai lệnh giả định ứng dụng server đã được build thành `catalog-service.jar`. Nếu server trả mã instance trong header thử nghiệm, có thể quan sát instance nào đã nhận request. `@HttpExchange` không làm phát sinh service ID; service ID phải khớp tên dùng trong `baseUrl("http://catalog-service")` và discovery.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as order-service
    participant Proxy as CatalogHttpApi proxy
    participant RC as @LoadBalanced RestClient
    participant LB as LoadBalancer
    participant Disc as Discovery / supplier
    participant B as catalog-b:18082

    App->>Proxy: findById("42")
    Proxy->>RC: GET http://catalog-service/api/items/42
    RC->>LB: catalog-service
    LB->>Disc: Lấy instance
    Disc-->>LB: [A, B]
    LB-->>RC: B
    RC->>B: GET /api/items/42
    B-->>RC: 200 JSON
    RC-->>Proxy: ItemDto
    Proxy-->>App: ItemDto
~~~

Nếu gọi hostname chưa có trong discovery, không thể chọn instance; cần kiểm tra service ID, nguồn discovery, cache, health check và các filter trước khi kết luận URL annotation sai.

## 9. Tạo HTTP Interface proxy với WebClientAdapter

Khi cần xử lý reactive hoặc streaming, sử dụng `WebClientAdapter` thay vì ép mọi lời gọi trả về DTO đồng bộ.

**Dependencies:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Interface reactive riêng:**

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record StockEvent(String sku, int quantity) {}

@HttpExchange(url = "/api/items", accept = MediaType.APPLICATION_JSON_VALUE)
interface ReactiveCatalogHttpApi {

    @GetExchange("/{id}")
    Mono<ItemDto> findById(@PathVariable("id") String id);

    @GetExchange(value = "/events", accept = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<StockEvent>> watchEvents();
}
~~~

Ở ví dụ này, `/api/items/events` phải thực sự là endpoint SSE trên server; backend lab GET theo ID ở trên chưa cung cấp endpoint đó. `Mono<ItemDto>` biểu diễn tối đa một response DTO, còn `Flux<ServerSentEvent<StockEvent>>` biểu diễn luồng sự kiện có thể kéo dài.

**Tạo proxy:**

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
class ReactiveCatalogHttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    ReactiveCatalogHttpApi reactiveCatalogHttpApi(
        @Qualifier("loadBalancedWebClientBuilder")
        WebClient.Builder builder
    ) {
        WebClient client = builder
            .baseUrl("http://catalog-service")
            .build();

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(
                WebClientAdapter.create(client))
                .build();

        return factory.createClient(ReactiveCatalogHttpApi.class);
    }
}
~~~

Lưu ý đây là **một phương án thực thi khác** cho cùng loại hợp đồng, không nhất thiết phải đăng ký cả RestClient và WebClient trong một ứng dụng. Nếu muốn cả hai, cần đặt tên bean và injection rõ ràng.

### Blocking và reactive là hai mô hình khác nhau

| Nội dung | RestClientAdapter | WebClientAdapter |
|---|---|---|
| Client nền | RestClient | WebClient |
| Mô hình thường dùng | Đồng bộ, blocking | Reactive, non-blocking |
| Return type điển hình | DTO, `ResponseEntity<T>`, `void` | `Mono<T>`, `Flux<T>` và các kiểu phù hợp |
| Xử lý lỗi | Exception trong lời gọi đồng bộ | Error signal của publisher |
| Streaming response | Không phải lựa chọn mặc định tốt cho SSE dài | Thích hợp hơn cho SSE/streaming |
| Kết nối LoadBalancer | RestClient builder `@LoadBalanced` | WebClient builder `@LoadBalanced` |

Không dùng `block()` trên reactor event-loop để chuyển một HTTP interface reactive thành lời gọi đồng bộ. Nếu dùng WebClient trong pipeline reactive, trả tiếp `Mono`/`Flux` để framework quản lý subscription và cancellation.

## 10. Annotation mô tả kiểu dữ liệu trả về như thế nào?

Method return type của interface quyết định cách adapter chuyển response sang kiểu Java:

~~~java
@HttpExchange("/api/items")
interface CatalogResponses {

    @GetExchange("/{id}")
    ItemDto getBody(@PathVariable("id") String id);

    @GetExchange("/{id}")
    ResponseEntity<ItemDto> getEntity(@PathVariable("id") String id);

    @DeleteExchange("/{id}")
    void delete(@PathVariable("id") String id);
}
~~~

- `ItemDto`: cần nội dung body phù hợp để chuyển thành DTO.
- `ResponseEntity<ItemDto>`: ứng dụng nhận được status/header/body khi HTTP response được xử lý thành công.
- `void`: bỏ qua body khi contract không yêu cầu dữ liệu trả về.
- Với WebClientAdapter, có thể dùng `Mono<ItemDto>`, `Mono<ResponseEntity<ItemDto>>` và `Flux<T>` theo kiểu response.

**`ResponseEntity<T>` không mặc nhiên biến mọi 4xx/5xx thành giá trị trả về bình thường.** Với adapter và chính sách mặc định, HTTP error status có thể được chuyển thành exception hoặc error signal trước khi method trả được một entity thành công.

Nếu API trả `204 No Content`, không nên yêu cầu deserialize thành DTO bắt buộc. Hãy thiết kế return type/contract phù hợp, ví dụ `void` hoặc response chỉ có status.

### Các kiểu generic

Với danh sách hoặc wrapper generic:

~~~java
@GetExchange
List<ItemDto> list(@RequestParam("category") String category);
~~~

HTTP Service Proxy có thể nắm kiểu return type từ chữ ký method, khác với trường hợp dùng RestClient trực tiếp và phải cung cấp `ParameterizedTypeReference<List<ItemDto>>` trong nhiều lời gọi. Khả năng giải mã cuối cùng vẫn phụ thuộc media type và converter/codec của adapter.

## 11. Header chung, header động và bảo mật

Có thể định nghĩa header tĩnh bằng `@HttpExchange`:

~~~java
@HttpExchange(
    url = "/api/items",
    headers = {"X-Caller=order-service"},
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {
    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

Dùng header tĩnh cho thông tin không nhạy cảm, không thay đổi. Với thông tin liên quan từng request, dùng `@RequestHeader`:

~~~java
@GetExchange("/{id}")
ItemDto findById(
    @PathVariable("id") String id,
    @RequestHeader("X-Correlation-Id") String correlationId
);
~~~

**Không hardcode Bearer token hoặc API key vào annotation** rồi đưa vào source code. Authentication nên được quản lý bằng thành phần cấu hình client phù hợp (interceptor/filter hoặc cơ chế credentials) và phạm vi tin cậy cụ thể.

HTTP Interface đơn giản hóa mô tả request; nó không tự kiểm soát việc chuyển tiếp credentials giữa các service. Cần xác định token dành cho người dùng hay service account, quyền truy cập và quy tắc che log.

## 12. Phân biệt HTTP Service Interface với OpenFeign

Cả HTTP Interface và OpenFeign đều cho phép viết Java interface biểu diễn remote HTTP API. Nhưng chúng **khác framework thực thi và cách đăng ký**:

| Tiêu chí | Spring HTTP Service Interface | Spring Cloud OpenFeign |
|---|---|---|
| Khai báo interface | `@HttpExchange`, `@GetExchange`, `@PostExchange`... | `@FeignClient` và các mapping/contract tương ứng |
| Tạo client | `HttpServiceProxyFactory` + adapter | Feign client factory do OpenFeign quản lý |
| HTTP stack | RestClient, WebClient hoặc adapter tương thích | Feign client và HTTP transport cấu hình |
| LoadBalancer | Cần nền HTTP client được tích hợp `@LoadBalanced` | Tích hợp Spring Cloud LoadBalancer theo cấu hình/dependency |
| Reactive return | Có thể dùng `Mono`/`Flux` với WebClientAdapter | Không mặc định giống WebClient reactive |
| Status/exception | Theo adapter và cấu hình response handling | Theo error decoder/response handling của Feign |

**Không đặt `@FeignClient` lên một HTTP Service Interface rồi mặc định `HttpServiceProxyFactory` sẽ sử dụng Feign**, hoặc đổi `@GetMapping` của Feign sang `@GetExchange` mà không chỉnh lại cơ chế tạo proxy. Đây là hai cơ chế cần được cấu hình riêng.

Chọn theo kiến trúc dự án: RestClientAdapter thích hợp khi dùng stack Spring đồng bộ; WebClientAdapter thuận tiện với reactive/streaming; OpenFeign phù hợp nếu dự án đã dùng Feign và quy trình cấu hình của nó.

## 13. Xử lý HTTP status, không có instance và lỗi kết nối

Một method Java khai báo `ItemDto findById(...)` che bớt phần gọi HTTP, nhưng **không che được các tình huống lỗi**:

~~~mermaid
flowchart TD
    A["Gọi catalog.findById(id)"] --> B["HTTP proxy tạo request"]
    B --> C{"LoadBalancer chọn được instance?"}
    C -->|Không| D["Lỗi không có ServiceInstance"]
    C -->|Có| E{"Gửi request / nhận response?"}
    E -->|Lỗi I/O| F["Connect timeout / reset / TLS"]
    E -->|Có response| G{"HTTP status"}
    G -->|2xx| H["Giải mã body"]
    G -->|4xx| I["Client error theo contract"]
    G -->|5xx| J["Server / dependency error"]
~~~

| Tình huống | Có response từ service đích không? | Ví dụ xử lý |
|---|---|---|
| Service ID không tồn tại hoặc supplier không có instance | Không | Kiểm tra discovery, name, filter và health |
| Connect refused, connect timeout | Không | Kiểm tra mạng, instance, port và retry có giới hạn |
| HTTP 404 | Có | Resource không có hoặc route sai |
| HTTP 429 | Có | Throttle/rate limit theo contract |
| HTTP 503 | Có thể từ backend/gateway khi thật sự nhận response | Điều tra overload, health, dependency |
| Response JSON sai schema | Có thể nhận 2xx nhưng decode lỗi | Đối chiếu DTO và API version |

Với `RestClientAdapter`, lỗi HTTP status thường đi qua cơ chế xử lý của RestClient và có thể ném `RestClientResponseException` hoặc subclass. Với `WebClientAdapter`, lỗi status thường xuất hiện trong error signal, ví dụ `WebClientResponseException`. Ngoài ra còn lỗi kết nối, codec và tình huống không chọn được instance; **không bắt tất cả bằng một kiểu exception HTTP status**.

Nếu dùng `ResponseEntity` làm return type, vẫn phải kiểm tra chính sách status của client nền. HTTP Service Interface không tự có một “error decoder chung” độc lập hoàn toàn khỏi adapter.

### Ví dụ catch có phân loại ở caller đồng bộ

~~~java
try {
    ItemDto item = catalogHttpApi.findById("42");
    // Xử lý item
} catch (org.springframework.web.client.RestClientResponseException ex) {
    int code = ex.getStatusCode().value();
    // Đã nhận HTTP response lỗi; phân loại 404 / 429 / 5xx.
} catch (org.springframework.web.client.RestClientException ex) {
    // Lỗi I/O hoặc decode có thể thuộc nhóm này;
    // kiểm tra nguyên nhân trước khi retry.
}
~~~

Một số lỗi chọn instance trước HTTP có thể đi qua loại exception khác tùy tích hợp/phiên bản. Vì vậy, ví dụ catch này **không khẳng định bao phủ mọi lỗi**. Nên thiết kế xử lý ở biên gọi dịch vụ, log class/cause và tách lỗi discovery khỏi lỗi HTTP server.

## 14. Timeout và retry phải cấu hình ở client nền

Annotation `@GetExchange` không nói gì về connect timeout, read timeout hoặc số lần retry. Chúng thuộc **HTTP client/connector và các lớp resilience**.

Ví dụ cho RestClient dùng `SimpleClientHttpRequestFactory`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();

    factory.setConnectTimeout(2000);
    factory.setReadTimeout(3000);

    return RestClient.builder().requestFactory(factory);
}
~~~

Đây là **phương án thay thế** cho bean builder ở phần 7, không phải bean thứ hai cần đăng ký song song. Đơn vị của hai giá trị số nguyên là mili giây trong API ví dụ; cần kiểm tra timeout thực tế theo HTTP request factory và phiên bản sử dụng.

Khi dùng WebClient với Reactor Netty, cấu hình connector/response timeout tương ứng. Với các luồng SSE dài, timeout không thể được suy từ request JSON ngắn: có thể cần heartbeat và kiểm soát idle riêng.

Retry có thể làm phương thức `catalogHttpApi.create(...)` thực thi nhiều lần nếu backend đã xử lý request nhưng response bị mất. Vì vậy:

- Chỉ retry loại lỗi có khả năng phục hồi; giới hạn số lần và tổng deadline.
- Với POST hoặc các thao tác có tác dụng phụ, dùng **idempotency key** cùng cơ chế deduplicate thực sự ở server nếu cần.
- Không tự giả định retry sau lỗi sẽ chọn instance khác; điều đó còn phụ thuộc cấu hình retry/LoadBalancer.
- Tránh retry chồng nhau giữa HTTP client, gateway và service mesh khiến traffic khuếch đại.
- Không xử lý HTTP 404 như một lỗi tạm thời trừ khi hợp đồng nghiệp vụ nói khác.

Có thể khai báo idempotency key như một header động trong interface:

~~~java
@PostExchange(
    contentType = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<ItemDto> create(
    @RequestBody CreateItemRequest request,
    @RequestHeader("X-Idempotency-Key") String key
);
~~~

Đây là ví dụ method nằm trong interface đã có prefix `@HttpExchange("/api/items")`; không lặp thêm `/api/items` trong `@PostExchange` để tránh tạo đường dẫn hai lần. Header đơn thuần không đủ bảo đảm idempotency nếu server không triển khai xử lý key.

## 15. Bài thực hành nhỏ: hai instance, một interface

**Mục tiêu:** xác nhận method `findById` đi tới các instance khác nhau qua service ID, và hiểu vì sao khi một instance dừng hoặc discovery rỗng thì method proxy vẫn có thể thất bại.

### Thiết lập

1. Dựng service server có `@GetMapping("/api/items/{id}")` và trả cùng kiểu `ItemDto` trên cổng 18081 và 18082.
2. Cấu hình `SimpleDiscoveryClient` trong caller như phần 8.
3. Tạo bean `CatalogHttpApi` với `HttpServiceProxyFactory` và RestClient builder `@LoadBalanced`.
4. Viết một endpoint trong caller gọi proxy:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CallerDemoController {

    private final CatalogHttpApi catalog;

    CallerDemoController(CatalogHttpApi catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/demo/items/{id}")
    ItemDto item(@PathVariable String id) {
        return catalog.findById(id);
    }
}
~~~

5. Gửi nhiều request:

~~~bash
curl -i http://localhost:18090/demo/items/42
curl -i http://localhost:18090/demo/items/42
curl -i http://localhost:18090/demo/items/42
~~~

Để biết instance thực sự được chọn, có thể bổ sung một trường/response header `instanceId` tại server trong lab, hoặc sử dụng log/tracing của backend. Vì hai server trả DTO giống nhau, **chỉ dựa vào body JSON giống nhau không chứng minh có load balancing**.

### Kiểm chứng khi một instance lỗi

Dừng instance ở cổng 18082 rồi tiếp tục gọi caller. Có thể tồn tại một khoảng thời gian lỗi kết nối nếu nguồn discovery tĩnh vẫn liệt kê 18082 hoặc health check chưa cập nhật. LoadBalancer không mặc nhiên tự phát hiện và gỡ mọi địa chỉ chết ngay lập tức.

Nếu bật health-check supplier, quan sát danh sách candidate trước/sau khi probe cập nhật. Khi instance phục hồi, kiểm tra nó được đưa lại vào danh sách theo chính sách; đừng suy từ một response thành công rằng mọi thứ đã hội tụ.

### Các trường hợp cần kiểm thử

| Kịch bản | Kỳ vọng kiểm chứng |
|---|---|
| Chỉ một instance được đăng ký | Proxy vẫn gọi thành công nếu instance đó khỏe và endpoint tồn tại |
| Hai instance đăng ký | Có thể quan sát cả hai instance được chọn theo chính sách |
| Service ID trong baseUrl sai | Không có instance phù hợp hoặc lỗi phân giải đích |
| URL annotation sai path | Backend trả HTTP 404 nếu server vẫn nhận request |
| Backend trả 500 | Proxy/adapter biểu diễn HTTP lỗi theo cấu hình |
| Instance đã chết vẫn có trong list | Có thể lỗi kết nối hoặc timeout trước khi danh sách cập nhật |
| DTO thay đổi schema | Có thể phát sinh lỗi decode dù HTTP status thành công |
| Client dùng RestClient builder không `@LoadBalanced` | Host logic có thể bị xử lý bởi DNS thường |
| POST retry khi response bị mất | Cần chứng minh backend tránh tạo resource trùng |
| WebClient SSE stream | Một HTTP request gắn với instance đã chọn; event không tự Round Robin |

Không giả định output/exception cố định giữa mọi phiên bản Spring Cloud. Kiểm thử phải dựa vào HTTP request thật, cấu hình client thực, tình trạng registry và kết quả từ server.

## 16. Các lỗi thiết kế thường gặp

1. **Nhầm client interface với REST controller:** chỉ khai báo `@HttpExchange` không tự tạo endpoint server.
2. **Quên tạo proxy:** Spring không mặc nhiên đăng ký mọi interface `@HttpExchange` thành bean khi chưa có cơ chế cấu hình phù hợp.
3. **Quên @LoadBalanced:** proxy qua RestClientAdapter/WebClientAdapter vẫn cần client nền đã được tích hợp LoadBalancer để phân giải service ID.
4. **Lặp path prefix:** interface dùng `@HttpExchange("/api/items")`, method lại dùng `@PostExchange("/api/items")` khiến đường dẫn sai.
5. **Dùng @GetMapping/@PostMapping thay vì @GetExchange/@PostExchange tùy tiện:** annotation MVC dành cho mapping server hoặc contract khác, không mặc nhiên là metadata mong đợi của HTTP Service Proxy.
6. **Không đặt tên tham số rõ ràng:** placeholder `{id}` không khớp `@PathVariable("itemId")`.
7. **Dùng @RequestParam thay @RequestBody:** query string và JSON body là hai hình thức truyền dữ liệu khác nhau.
8. **Nhầm Content-Type và Accept:** yêu cầu response JSON không có nghĩa request luôn gửi JSON.
9. **Hardcode credentials trong annotation hoặc log request:** làm rò khóa và token.
10. **Coi ResponseEntity là cơ chế bỏ qua mọi HTTP lỗi:** default status handling có thể ném exception trước.
11. **Dùng kiểu reactive trên RestClientAdapter mà không kiểm tra hỗ trợ:** cần chọn đúng adapter và return type tương ứng.
12. **Thiếu timeout và retry budget:** proxy nhìn đơn giản nhưng vẫn dùng mạng và có thể chặn thread lâu.
13. **Retry POST không có idempotency:** request trước có thể đã được server xử lý.
14. **Bỏ qua discovery/health khi lỗi:** “method Java ném lỗi” có thể do không có ServiceInstance trước khi HTTP request được gửi.
15. **Không kiểm chứng phiên bản Framework/Cloud:** API factory và adapter phải tương thích dependency thực tế.

## 17. Checklist triển khai và kết luận

Trước khi dùng HTTP Service Interface trong sản phẩm, hãy xác nhận:

- Interface khai báo đúng `@HttpExchange` ở mức chung và một HTTP method annotation cho mỗi method.
- Đường dẫn mức interface + mức method tạo URL mong muốn, không bị trùng prefix.
- `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` và `@RequestPart` được dùng theo HTTP contract.
- DTO và generic return types khớp schema/content type của server.
- `HttpServiceProxyFactory` được tạo từ đúng adapter của HTTP client đang dùng.
- Nếu URL host là service ID, HTTP client được tạo từ builder `@LoadBalanced` và discovery có instance tương ứng.
- RestClientAdapter đi với mô hình đồng bộ; WebClientAdapter đi với publisher reactive khi cần.
- Lỗi không có instance, lỗi kết nối, HTTP 4xx/5xx và lỗi decode được phân loại riêng.
- Timeout, retry/backoff, idempotency và deadline tổng phù hợp SLO.
- Log/trace thể hiện service ID, instance được chọn, HTTP status và exception cause mà không tiết lộ thông tin nhạy cảm.
- Có integration test cho ít nhất một response thành công, lỗi HTTP và tình huống instance không có sẵn.

**Kết luận:** HTTP Service Interface giúp định nghĩa hợp đồng gọi HTTP theo kiểu **declarative, type-safe và dễ tái sử dụng**. `@HttpExchange` đặt cấu hình chung, các annotation `@GetExchange`/`@PostExchange`/`@PutExchange`/`@PatchExchange`/`@DeleteExchange` mô tả HTTP method, còn `@PathVariable`/`@RequestParam`/`@RequestHeader`/`@RequestBody`/`@RequestPart` định vị dữ liệu request. Để gọi **theo tên dịch vụ**, hãy tạo proxy từ `RestClientAdapter` hoặc `WebClientAdapter` với client được tích hợp **Spring Cloud LoadBalancer**, rồi phối hợp discovery, health check, timeout, retry và observability. Chính những thành phần vận hành này — không phải riêng annotation — giúp giao tiếp liên dịch vụ ổn định khi instance thay đổi hoặc xảy ra lỗi.

