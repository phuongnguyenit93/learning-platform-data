# Tạo lời gọi theo tên dịch vụ với retrieve và exchange

Trong một hệ thống microservices, ứng dụng thường không nên hardcode địa chỉ `http://10.0.1.25:8080` của một instance cụ thể. Với **Spring Cloud LoadBalancer**, một `RestClient` được cấu hình bằng `@LoadBalanced` có thể gọi URL dạng **`http://inventory-service/api/items/42`**. Phần host `inventory-service` được hiểu là **service ID**; LoadBalancer tìm tập `ServiceInstance` phù hợp, chọn một instance, rồi gửi HTTP request đến host/port thực của instance đó.

Bài học thuộc chương **RestClient** trong module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Trọng tâm là tạo lời gọi theo **tên dịch vụ**, sử dụng **`retrieve()`** để xử lý response thuận tiện và **`exchange()`** khi cần kiểm soát HTTP response chi tiết hơn. Các ví dụ cũng cho thấy mối quan hệ với discovery, health check, timeout, retry và observability; từ đó giúp giao tiếp liên dịch vụ ổn định và chẩn đoán lỗi chính xác.

> `RestClient` là HTTP client **đồng bộ (blocking)** trong Spring Framework 6.1 trở lên. Nó có API fluent tương tự `WebClient` nhưng không phải reactive client. Dùng `WebClient` nếu yêu cầu thực sự là chuỗi xử lý non-blocking.

## 1. Luồng request: URL theo service ID được xử lý ở đâu?

Khi service gọi:

~~~java
restClient.get()
    .uri("http://inventory-service/api/items/{id}", "42")
    .retrieve()
    .body(ItemDto.class);
~~~

Quy trình khái quát:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as order-service
    participant R as @LoadBalanced RestClient
    participant LB as Spring Cloud LoadBalancer
    participant S as ServiceInstanceListSupplier
    participant I as inventory-service instance

    C->>R: GET http://inventory-service/api/items/42
    R->>LB: Chọn instance theo inventory-service
    LB->>S: Lấy danh sách ServiceInstance
    S-->>LB: [inventory-a, inventory-b]
    LB-->>R: inventory-b (host:port)
    R->>I: GET /api/items/42
    I-->>R: HTTP status, headers, body
    R-->>C: DTO / ResponseEntity / exception
~~~

`RestClient` không tự tìm instance qua discovery chỉ vì URL trông giống tên dịch vụ. Cần có **bean `RestClient.Builder` được đánh dấu `@LoadBalanced`**, dependency Spring Cloud LoadBalancer tương thích và nguồn danh sách instance.

Ba giai đoạn phải phân biệt:

1. **Phân giải service ID**: từ `inventory-service` đến danh sách ứng viên.
2. **Lựa chọn instance**: Round Robin hoặc chính sách khác chọn một `ServiceInstance`.
3. **Thực hiện HTTP**: client gửi request; nhận HTTP response hoặc lỗi kết nối/timeout.

Nếu không chọn được instance, request không tới backend. Lỗi này khác HTTP `404` hay `503` do server đích gửi.

## 2. Điều kiện chuẩn bị dự án

Các ví dụ sử dụng Java 17+, Spring Boot hỗ trợ Spring Framework 6.1+ (ví dụ Spring Boot 3.2+) và **Spring Cloud release train tương thích**. Hãy để BOM/dependency management của dự án chọn version, không ghép tùy tiện các phiên bản không tương thích.

**Gradle (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Maven:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-web` cung cấp phần MVC và các thành phần HTTP đồng bộ thường dùng; `spring-cloud-starter-loadbalancer` cung cấp tích hợp client-side load balancing. Cả hai ví dụ dependency chỉ là phần cần thiết cho bài học, không thay thế cấu hình build và quản lý phiên bản của dự án.

Trong môi trường thực tế, danh sách instance thường đến từ Eureka, Consul, Kubernetes hoặc nguồn discovery đã cấu hình. Để chạy một lab nhỏ **không cần registry**, có thể dùng `SimpleDiscoveryClient` với danh sách tĩnh.

## 3. Cấu hình hai instance dưới cùng service ID

Giả sử hai instance `inventory-a` và `inventory-b` đang phục vụ cùng API:

| Instance | Địa chỉ thật | Service ID logic |
|---|---|---|
| inventory-a | `http://localhost:18081` | `inventory-service` |
| inventory-b | `http://localhost:18082` | `inventory-service` |

Cấu hình trong `application.yml` của caller:

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
            inventory-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

`SimpleDiscoveryClient` là nguồn instance tĩnh dành cho môi trường nhỏ hoặc demo. Trong sản xuất, discovery động phù hợp hơn nếu instance được triển khai, gỡ bỏ hoặc scale thường xuyên.

Một backend mẫu cho hai tiến trình:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record ItemDto(String id, String name, int stock) {}

@RestController
@RequestMapping("/api/items")
class InventoryController {

    @Value("${instance.id:inventory-unknown}")
    private String instanceId;

    @GetMapping("/{id}")
    ResponseEntity<?> find(@PathVariable String id) {
        if ("missing".equals(id)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "ITEM_NOT_FOUND"));
        }

        if ("busy".equals(id)) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("code", "INVENTORY_BUSY"));
        }

        return ResponseEntity.ok()
            .header("X-Instance-Id", instanceId)
            .body(new ItemDto(id, "Notebook", 7));
    }
}
~~~

Chạy hai bản từ cùng một ứng dụng Spring Boot:

~~~bash
java -jar inventory-service.jar --server.port=18081 --instance.id=inventory-a
java -jar inventory-service.jar --server.port=18082 --instance.id=inventory-b
~~~

Các lệnh giả định bạn đã build artifact Spring Boot có chứa controller mẫu và ứng dụng có entry point `@SpringBootApplication`. Ví dụ `inventory-service.jar` là tên minh họa, không phải một artifact đã được tạo bởi bài học.

Thử backend trực tiếp trước khi kiểm tra LoadBalancer:

~~~bash
curl -i http://localhost:18081/api/items/42
curl -i http://localhost:18082/api/items/missing
~~~

Kỳ vọng lần đầu trả HTTP `200` và header `X-Instance-Id: inventory-a`; lần hai trả `404`.

## 4. Tạo @LoadBalanced RestClient.Builder đúng cách

Trong ứng dụng caller, khai báo bean builder:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @org.springframework.beans.factory.annotation.Qualifier(
                "loadBalancedRestClientBuilder"
            ) RestClient.Builder builder) {
        return builder.build();
    }
}
~~~

Spring Cloud tích hợp thành phần LoadBalancer vào **builder bean** được đánh dấu `@LoadBalanced`. Khi gọi `builder.build()`, `RestClient` được tạo mang cấu hình đó. Dependency discovery cung cấp tập instance, còn thuật toán LoadBalancer chọn đích.

Có thể rút gọn import `@Qualifier` trong dự án thật:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;

// Trong @Bean inventoryRestClient:
RestClient inventoryRestClient(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder) {
    return builder.build();
}
~~~

Đoạn thứ hai chỉ minh họa cách viết gọn **thay thế phần khai báo method tương ứng ở trên**, không phải một bean bổ sung cần đăng ký hai lần.

### Sai lầm: dùng RestClient.create() rồi mong nó tự load balance

~~~java
// Không tự sử dụng Spring Cloud LoadBalancer:
RestClient plain = RestClient.create();

plain.get()
    .uri("http://inventory-service/api/items/42")
    .retrieve()
    .body(String.class);
~~~

`RestClient.create()` trực tiếp không nhận interceptor/load-balancing configuration từ bean `@LoadBalanced RestClient.Builder`. Vì vậy host `inventory-service` có thể bị đưa cho DNS bình thường và gây lỗi phân giải tên, trừ khi môi trường có DNS hoặc routing riêng.

**Quy tắc:** đối với URL theo service ID dùng Spring Cloud LoadBalancer, tạo client từ **builder đã được Spring quản lý và đánh dấu `@LoadBalanced`**. Đối với URL Internet bên ngoài hoặc endpoint phải gọi trực tiếp theo DNS, có thể dùng một RestClient bình thường để tránh nhầm lẫn host với service ID.

## 5. retrieve(): thao tác phổ biến để nhận body

`retrieve()` phù hợp khi ứng dụng cần lấy body đã được Spring HTTP message converter ánh xạ về Java object:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryGateway {

    private final RestClient restClient;

    InventoryGateway(RestClient inventoryRestClient) {
        this.restClient = inventoryRestClient;
    }

    ItemDto getItem(String id) {
        return restClient.get()
            .uri("http://inventory-service/api/items/{id}", id)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

Trong ví dụ, `ItemDto` là kiểu dữ liệu trong caller có hình dạng JSON tương ứng, chẳng hạn `record ItemDto(String id, String name, int stock) {}`. Mã Java ở backend và caller có thể khai báo DTO trong các module riêng; không bắt buộc chia sẻ file nguồn.

Các bước:

1. `get()` chọn HTTP method GET.
2. `uri("http://inventory-service/...", id)` tạo URI; hostname là service ID.
3. LoadBalancer chọn instance; HTTP request được gửi tới instance đó.
4. `retrieve()` tạo `ResponseSpec` và áp dụng xử lý status mặc định.
5. `body(ItemDto.class)` giải mã JSON response thành DTO.

**Đặc điểm đồng bộ:** lời gọi `body(...)` chặn thread caller cho đến khi nhận kết quả hoặc lỗi. Nếu gọi nhiều dịch vụ nối tiếp trong một request web, tổng latency sẽ chịu ảnh hưởng của các lời gọi blocking.

### URI template giúp tránh ghép chuỗi thủ công

Thay vì:

~~~java
// Tránh tự ghép path bằng input chưa mã hóa:
String url = "http://inventory-service/api/items/" + id;
~~~

Dùng:

~~~java
ItemDto item = restClient.get()
    .uri("http://inventory-service/api/items/{id}", id)
    .retrieve()
    .body(ItemDto.class);
~~~

Có thể dùng URI builder cho query parameters:

~~~java
List<ItemDto> items = restClient.get()
    .uri(uriBuilder -> uriBuilder
        .scheme("http")
        .host("inventory-service")
        .path("/api/items")
        .queryParam("category", "paper")
        .queryParam("limit", 20)
        .build())
    .retrieve()
    .body(new org.springframework.core.ParameterizedTypeReference<List<ItemDto>>() {});
~~~

Ví dụ minh họa trả một JSON array phù hợp với `List<ItemDto>`; backend mẫu ở phần trước chỉ khai báo endpoint item đơn lẻ, nên muốn chạy ví dụ danh sách phải bổ sung endpoint `GET /api/items` tương ứng. `ParameterizedTypeReference` giữ thông tin generic cho converter.

Không hardcode `localhost:18081` trong client khi mục tiêu là kiểm chứng lựa chọn theo tên dịch vụ.

## 6. retrieve().toEntity(): cần status và headers

Khi chỉ đọc body, `body(ItemDto.class)` thường là đủ. Nếu nghiệp vụ cần HTTP status và header từ instance, dùng `toEntity(...)`:

~~~java
import org.springframework.http.ResponseEntity;

ResponseEntity<ItemDto> entity = restClient.get()
    .uri("http://inventory-service/api/items/{id}", "42")
    .retrieve()
    .toEntity(ItemDto.class);

int status = entity.getStatusCode().value();
String chosenInstance =
    entity.getHeaders().getFirst("X-Instance-Id");
ItemDto item = entity.getBody();
~~~

Đây là cách quan sát instance thực sự đã trả response trong lab. Header `X-Instance-Id` là header tự tạo ở backend; Spring Cloud LoadBalancer **không tự động gắn** nó vào mọi response.

Lưu ý:

- `toEntity(...)` vẫn chịu status handler mặc định của `retrieve()`; HTTP 4xx/5xx chưa được xử lý sẽ dẫn đến exception thay vì một `ResponseEntity` thành công.
- Response có `204 No Content` hoặc body trống có thể khiến `entity.getBody()` là `null`.
- Nếu chỉ cần status và headers mà không cần body, có thể dùng `retrieve().toBodilessEntity()`.

### Khi cần thêm header ở request

~~~java
ItemDto item = restClient.get()
    .uri("http://inventory-service/api/items/{id}", id)
    .header("X-Correlation-Id", correlationId)
    .accept(org.springframework.http.MediaType.APPLICATION_JSON)
    .retrieve()
    .body(ItemDto.class);
~~~

Correlation ID giúp nối log giữa caller và backend. Không đưa token xác thực, dữ liệu cá nhân hoặc thông tin nhạy cảm vào URL query và log một cách tùy tiện.

## 7. retrieve() xử lý HTTP 4xx/5xx mặc định ra sao?

Với `retrieve()`, các status HTTP `4xx` và `5xx` không được xử lý bởi handler tùy biến sẽ **mặc định tạo exception** thuộc nhóm `RestClientResponseException` (hoặc các lớp con tương ứng), thay vì trả DTO như status 2xx.

Ví dụ backend trả `404`:

~~~java
try {
    ItemDto item = restClient.get()
        .uri("http://inventory-service/api/items/missing")
        .retrieve()
        .body(ItemDto.class);
} catch (org.springframework.web.client.RestClientResponseException ex) {
    int status = ex.getStatusCode().value();
    String responseBody = ex.getResponseBodyAsString();
    // Phân loại 404, 429, 500, 503 theo hợp đồng nghiệp vụ.
}
~~~

`RestClientResponseException` biểu diễn **một HTTP response lỗi thực sự đã nhận được**. Đừng dùng catch này để bao trùm mọi trường hợp không có instance, lỗi DNS hoặc connect timeout.

Ví dụ phân loại với `onStatus(...)`:

~~~java
ItemDto item = restClient.get()
    .uri("http://inventory-service/api/items/{id}", id)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        (request, response) -> {
            throw new ItemNotFoundException(id);
        }
    )
    .onStatus(
        org.springframework.http.HttpStatusCode::is5xxServerError,
        (request, response) -> {
            throw new InventoryUnavailableException(
                "inventory-service returned " +
                response.getStatusCode().value());
        }
    )
    .body(ItemDto.class);
~~~

`ItemNotFoundException` và `InventoryUnavailableException` là **exception nghiệp vụ do ứng dụng tự định nghĩa**. Handler `onStatus(...)` nhận request và HTTP response; nó có thể đọc headers/body để quyết định lỗi, nhưng phải tránh đưa payload nhạy cảm vào exception hoặc log.

Không nên đổi mọi lỗi `404` thành “dịch vụ không khả dụng”: `404` thường có nghĩa resource không tồn tại, trong khi `503` thường biểu thị khả năng phục vụ tạm thời bị ảnh hưởng. Cách phân loại cuối cùng phụ thuộc hợp đồng API.

## 8. exchange(): kiểm soát response ở mức thấp hơn

`exchange(...)` cho phép caller truy cập `ClientHttpRequest` và `ClientHttpResponse` trực tiếp trong một callback. Điều này hữu ích khi cần xem status trước khi quyết định cách đọc body, xử lý nhiều dạng response, hoặc lấy headers cụ thể mà không muốn cơ chế status handler của `retrieve()` tự ném lỗi.

Ví dụ một response kiểm tra mang nguyên status, header và raw body:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.web.client.RestClient;

record RawInventoryResult(
    int httpStatus,
    String instanceId,
    String rawBody
) {}

RawInventoryResult inspect(RestClient restClient, String id) {
    return restClient.get()
        .uri("http://inventory-service/api/items/{id}", id)
        .exchange((request, response) -> {
            int code = response.getStatusCode().value();
            String instanceId =
                response.getHeaders().getFirst("X-Instance-Id");

            // Chỉ phù hợp với response nhỏ trong lab.
            String body = new String(
                response.getBody().readAllBytes(),
                StandardCharsets.UTF_8
            );

            return new RawInventoryResult(code, instanceId, body);
        });
}
~~~

Khi gọi `inspect(..., "42")`, đối tượng có thể chứa `httpStatus=200` và JSON item. Với `"missing"`, nó có thể chứa `httpStatus=404` và raw body dạng `{"code":"ITEM_NOT_FOUND"}` **mà không tự ném exception từ status handler của `retrieve()`**.

**Khác biệt cốt lõi: `exchange()` không áp dụng status handler mà `retrieve()` sử dụng.** Nếu một HTTP response có status lỗi, callback của `exchange()` cần tự quyết định trả dữ liệu, chuyển thành exception hay xử lý fallback.

Callback của `exchange()` được gọi sau khi request đã được gửi và response đã có mặt. Một lỗi xảy ra **trước khi nhận HTTP response**, ví dụ không chọn được instance hoặc không kết nối được, vẫn khiến lời gọi thất bại; `exchange()` không biến các lỗi này thành response giả định.

### Chỉ sử dụng readAllBytes cho response nhỏ và đáng tin cậy

Đoạn ví dụ đọc toàn bộ body vào memory để dễ quan sát. Với response lớn, streaming, file download hoặc dữ liệu không kiểm soát kích thước, nên dùng một parser/streaming strategy có giới hạn. Không log raw body chứa thông tin nhạy cảm.

## 9. exchange(): quyết định 404, 503 và response thành công theo hợp đồng

Một ví dụ khác sử dụng `exchange()` để ánh xạ HTTP status theo lựa chọn của ứng dụng:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.springframework.http.HttpStatusCode;

Optional<String> getRawItem(RestClient restClient, String id) {
    return restClient.get()
        .uri("http://inventory-service/api/items/{id}", id)
        .exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();

            if (status.value() == 404) {
                return Optional.empty();
            }

            if (!status.is2xxSuccessful()) {
                throw new InventoryUnavailableException(
                    "HTTP " + status.value() +
                    " from inventory-service");
            }

            String json = new String(
                response.getBody().readAllBytes(),
                StandardCharsets.UTF_8
            );
            return Optional.of(json);
        });
}
~~~

Trong phương án này:

- `404` được biến thành `Optional.empty()`, phù hợp khi “không tìm thấy” là kết quả hợp lệ.
- `5xx` và các status không thuộc 2xx khác, trừ 404, được chuyển thành exception riêng.
- `2xx` được trả về dạng raw JSON để ví dụ tập trung vào status; nếu cần DTO, dùng converter hoặc JSON mapper thích hợp.
- Nếu status `204 No Content` là hợp lệ, cần xử lý body rỗng rõ ràng thay vì mặc định luôn có JSON.

Không phải mọi API đều nên trả `Optional.empty()` cho 404. Với một số API, 404 mang thông tin cấu hình sai route, path sai hoặc endpoint không tồn tại. Quyết định của callback phải dựa trên contract đã thống nhất giữa hai dịch vụ.

## 10. So sánh retrieve và exchange

| Tiêu chí | `retrieve()` | `exchange(...)` |
|---|---|---|
| Mức trừu tượng | Cao, thuận tiện với DTO | Thấp, truy cập request/response trực tiếp |
| Cách lấy JSON body | `body(MyDto.class)` | Tự đọc/chuyển đổi body trong callback |
| Lấy status/header | `toEntity(...)` hoặc `toBodilessEntity()` | `response.getStatusCode()`, `response.getHeaders()` |
| HTTP 4xx/5xx mặc định | Ném exception qua default status handler | Callback tự xử lý; không áp dụng default status handlers của retrieve |
| Tùy biến lỗi HTTP | `onStatus(...)` | `if`/`switch` trong callback |
| Không chọn được instance | Lỗi trước khi nhận HTTP response | Cũng là lỗi trước callback response |
| Độ phức tạp | Thấp với API thông thường | Cao hơn, cần xử lý status/body cẩn thận |
| Phù hợp | CRUD, DTO, contract HTTP rõ ràng | Response đặc biệt, phân nhánh status, raw body/header |

Cả hai phương thức **dùng cùng cơ chế LoadBalancer** khi được gọi từ cùng `RestClient` đã tích hợp. `retrieve()` và `exchange()` khác nhau ở **xử lý response**, không phải thuật toán chọn instance.

### Quy tắc lựa chọn

- Dùng **`retrieve()`** trong đa số trường hợp đọc JSON DTO, và `onStatus(...)` khi cần tùy biến lỗi.
- Dùng **`retrieve().toEntity(...)`** nếu cần status/header của response thành công.
- Dùng **`exchange(...)`** nếu phải tự phân nhánh nhiều status, đọc response khác nhau theo status hoặc làm việc gần HTTP transport.
- Đừng dùng `exchange()` chỉ để né việc xử lý exception 4xx/5xx: nếu bỏ quên các nhánh lỗi, ứng dụng dễ diễn giải HTTP 503 như thành công.

## 11. Phân biệt lỗi trước HTTP và lỗi từ server

Khi gọi theo service ID, không phải thất bại nào cũng có `ClientHttpResponse`:

~~~mermaid
flowchart TD
    A["RestClient gọi inventory-service"] --> B{"LoadBalancer chọn được instance?"}
    B -->|Không| C["Không có server: xử lý lỗi lựa chọn"]
    B -->|Có| D{"Kết nối và nhận được HTTP response?"}
    D -->|Không| E["Lỗi mạng / timeout / TLS"]
    D -->|Có| F{"HTTP status?"}
    F -->|2xx| G["Giải mã body hoặc xử lý response"]
    F -->|4xx| H["Lỗi hợp đồng / tài nguyên / quyền"]
    F -->|5xx| I["Lỗi server hoặc dependency"]
~~~

Các lỗi thường gặp:

| Lỗi | Có HTTP response từ inventory-service? | Hướng xử lý |
|---|---|---|
| Không có instance nào cho service ID | Không | Kiểm tra tên dịch vụ, discovery và supplier |
| Connect refused hoặc connect timeout | Không | Kiểm tra instance đang chạy, port, mạng |
| Read/response timeout | Có thể không nhận được response hoàn chỉnh | Kiểm tra tải, deadline, connection pool |
| HTTP `404` | Có | Xác minh resource/path và contract |
| HTTP `429` | Có | Xem rate limit và retry policy nếu an toàn |
| HTTP `503` | Có từ backend hoặc gateway nếu thực sự nhận được | Điều tra quá tải, health và dependency |
| Lỗi deserialization JSON | Có thể đã nhận status 2xx | Kiểm tra schema, media type và converter |

Ở một số tích hợp/phiên bản, trường hợp không có `ServiceInstance` có thể được báo bằng một exception như `IllegalStateException`. Kiểu exception cụ thể có thể thay đổi theo client, retry và phiên bản Spring Cloud. Đừng suy rằng mọi lỗi đều là `RestClientResponseException`; loại này dành cho trường hợp đã nhận HTTP response với status lỗi.

Cũng có thể gateway hoặc chính caller chủ động tạo HTTP `503` khi không tìm thấy instance, nhưng phải phân biệt **HTTP response gửi về cho caller** với **HTTP response từ inventory-service**.

## 12. Timeout cho RestClient có LoadBalancer

Cần cấu hình timeout ở lớp HTTP client. Ví dụ dùng `SimpleClientHttpRequestFactory` trong lab:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryTimeoutConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(2000);  // 2 giây
        factory.setReadTimeout(3000);     // 3 giây

        return RestClient.builder().requestFactory(factory);
    }
}
~~~

Đây là **phương án thay thế** cho bean `loadBalancedRestClientBuilder` ở phần 4, không được đăng ký song song hai bean cùng tên trong một context. Trong hệ thống có tải lớn, có thể chọn HTTP request factory với connection pooling và cấu hình timeout riêng phù hợp phiên bản thư viện sử dụng.

Cần phân biệt:

- **Connect timeout** giới hạn thời gian thiết lập kết nối theo transport được dùng.
- **Read timeout** giới hạn thời gian chờ đọc dữ liệu theo HTTP request factory.
- **Tổng deadline** của một thao tác nghiệp vụ có thể bao gồm discovery, chọn instance, kết nối, đọc body và nhiều lần retry; chỉ đặt hai timeout trên không bảo đảm một deadline tuyệt đối.

Nếu backend B tạm thời chậm, `RestClient` vẫn giữ thread caller trong thời gian đợi. Chọn timeout quá dài có thể làm cạn thread; quá ngắn có thể tạo lỗi giả trên đường truyền bình thường. Phải điều chỉnh theo SLO và phân bố latency thực tế.

## 13. Retry: không phải mọi lỗi đều nên thử lại

Khi request thất bại, retry có thể có ích nếu một instance vừa chết trong khi discovery chưa cập nhật hoặc có lỗi kết nối tạm thời. Nhưng retry tạo thêm tải và có thể lặp tác dụng phụ.

Các nguyên tắc:

1. Giới hạn **tổng số lần thử**, tổng thời gian và backoff; thêm jitter khi cần tránh retry đồng loạt.
2. Không tự retry mọi HTTP `4xx`; `404` thường không trở thành `200` chỉ vì gọi lại.
3. Với HTTP `429` hoặc `503`, xét hợp đồng API, chỉ dẫn `Retry-After` nếu có, và ngân sách thời gian.
4. Với thao tác ghi như trừ tồn kho, tạo đơn, thanh toán, cần **idempotency** hoặc idempotency key trước khi thử lại.
5. Không mặc định retry chọn một instance khác. Spring Cloud LoadBalancer có các tích hợp retry riêng tùy phiên bản; phải xác minh policy và kết quả lựa chọn thực tế.
6. Tránh retry chồng nhau giữa RestClient, LoadBalancer, gateway và service mesh, vì số lần thử có thể bị nhân lên.

Ví dụ đơn giản: 100 request/giây, mỗi request được thử tối đa ba lần **tổng cộng** khi thất bại, có thể gây đến khoảng 300 attempts/giây nếu phần lớn lần gọi vẫn lỗi. Nếu nguyên nhân là quá tải backend, retry không kiểm soát sẽ khiến vấn đề nặng thêm.

**`exchange()` không tự bật retry và `retrieve()` cũng không bảo đảm retry.** Chính sách retry thuộc cấu hình client/integration và các thư viện resilience mà ứng dụng chủ động sử dụng.

## 14. Quan sát instance được chọn và response

Để xác minh request đến instance nào, lab sử dụng header `X-Instance-Id` do backend tự trả. Có thể gọi lặp lại:

~~~bash
for i in $(seq 1 8); do
  curl -i http://localhost:18090/demo/item/42
done
~~~

Caller có thể cung cấp một controller thử nghiệm:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class DemoController {

    private final RestClient restClient;

    DemoController(RestClient inventoryRestClient) {
        this.restClient = inventoryRestClient;
    }

    @GetMapping("/demo/item/{id}")
    ResponseEntity<ItemDto> item(@PathVariable String id) {
        return restClient.get()
            .uri("http://inventory-service/api/items/{id}", id)
            .retrieve()
            .toEntity(ItemDto.class);
    }
}
~~~

Vì controller trả lại `ResponseEntity` của backend, header `X-Instance-Id` từ backend có thể quan sát được trên response của caller trong lab. Trong ứng dụng production, không nên mặc nhiên phản chiếu tất cả header từ backend ra public API vì có thể lộ thông tin hạ tầng hoặc vi phạm contract.

Với thuật toán Round Robin và danh sách instance ổn định, nhiều lượt gọi thường cho thấy cả inventory-a lẫn inventory-b; tỷ lệ chọn thực tế còn phụ thuộc số caller, trạng thái health/discovery và cấu hình retry.

Nên log/đo:

| Trường hoặc metric | Mục đích |
|---|---|
| `serviceId` | Phân biệt dịch vụ logic |
| Instance được chọn | Xác định host/port đích khi xử lý lỗi |
| `traceId` / `correlationId` | Nối log giữa caller và backend |
| HTTP method và operation | Phân loại lời gọi mà không tăng cardinality quá cao |
| HTTP status từ backend | Phân biệt 4xx/5xx có response |
| Exception class/cause | Nhận ra lỗi trước HTTP |
| Connect/read latency | Định vị timeout và nghẽn |
| Retry attempts | Đo số lần thử và độ khuếch đại tải |
| Supplier/discovery instance count | Kiểm tra có ứng viên hay không |

Có thể kết hợp observability của Spring Boot/Micrometer với các hook như `LoadBalancerLifecycle` để quan sát thời điểm lựa chọn và kết thúc lời gọi. Không giả định một metric từ LoadBalancer tự bao gồm thời gian xử lý bên trong server.

## 15. Kiểm thử retrieve và exchange trên các response khác nhau

Với backend mẫu đã trả được `200`, `404` và `503`, hãy kiểm tra bảng sau:

| Request | Với `retrieve()` chưa có `onStatus` | Với `exchange()` trả RawInventoryResult |
|---|---|---|
| `GET /api/items/42` | DTO `ItemDto` | `httpStatus=200`, body JSON |
| `GET /api/items/missing` | Exception HTTP 404 | `httpStatus=404`, body lỗi |
| `GET /api/items/busy` | Exception HTTP 503 | `httpStatus=503`, body lỗi |
| Backend trả 204 | `body(...)` có thể là `null` | `httpStatus=204`, body rỗng |
| Không có instance trong discovery | Lỗi chọn đích trước HTTP | Lỗi trước khi callback được gọi |
| Instance dừng sau khi được chọn | Exception kết nối/timeout | Lỗi trước khi có response |
| JSON sai schema | Lỗi decode khi chuyển DTO | Raw body vẫn có thể được trả nếu callback không decode |

Lưu ý `GET /api/items/busy` là đường dẫn kịch bản của backend lab: gọi `/api/items/{id}` với `id=busy`. Với HTTP `204`, backend phải được bổ sung một nhánh trả `204` nếu muốn chạy thử; bảng trình bày **hành vi cần kiểm chứng**, không khẳng định backend mẫu hiện có sẵn nhánh đó.

### Checklist lỗi thường gặp

- Chỉ tạo `RestClient.create()` hoặc `RestClient.builder()` thủ công, không dùng builder `@LoadBalanced` nên service ID bị DNS phân giải trực tiếp.
- Tên service ID trong URI không khớp discovery; ví dụ gọi `inventory` trong khi đăng ký `inventory-service`.
- Gọi đúng service ID nhưng tất cả instance bị loại bởi health check, zone hoặc filter.
- Nhầm `toEntity()` với `exchange()`: `toEntity` vẫn dùng status handlers của `retrieve()`.
- Cho rằng `exchange()` sẽ tự ném exception khi HTTP `404` hoặc `503`.
- Dùng `onStatus` để bắt lỗi “không chọn được instance”; lúc đó có thể chưa có HTTP response.
- Đọc body trong `exchange()` mà không giới hạn kích thước hoặc xử lý status.
- Đặt timeout quá dài hoặc retry không giới hạn, làm chậm toàn bộ luồng blocking.
- Trả header nội bộ hoặc raw body lỗi trực tiếp ra public API mà không kiểm tra dữ liệu nhạy cảm.
- Test chỉ với một instance nên không chứng minh được lựa chọn theo service ID.

## 16. Kết luận và nguyên tắc vận dụng

- **`@LoadBalanced RestClient.Builder`** là mắt xích giúp biến host trong URL thành service ID và để Spring Cloud LoadBalancer chọn `ServiceInstance`.
- **`retrieve()`** là cách phổ biến để lấy DTO, headers và status thành công; nó xử lý HTTP 4xx/5xx theo status handlers mặc định hoặc `onStatus` mà ứng dụng khai báo.
- **`exchange()`** cho quyền điều khiển trực tiếp HTTP response trong callback và không áp dụng status handlers của `retrieve()`; ứng dụng phải tự xử lý status, body và lỗi một cách có chủ đích.
- **Không chọn được instance, lỗi kết nối và HTTP status lỗi là những giai đoạn khác nhau**. Phân biệt chúng để cấu hình discovery, health check, timeout, retry và observability chính xác.
- **RestClient là blocking**; cân nhắc worker threads và deadline khi gọi chuỗi nhiều dịch vụ. Nếu cần pipeline reactive không chặn, sử dụng WebClient thay vì chèn `block()` tùy tiện vào reactive event-loop.

Điểm cần nhớ: `retrieve()` và `exchange()` **không quyết định thuật toán load balancing**. Chúng quyết định cách ứng dụng xử lý response sau khi Spring Cloud LoadBalancer đã lựa chọn instance và HTTP client đã cố gắng thực hiện lời gọi. Để hệ thống giao tiếp ổn định, cần phối hợp service discovery, lọc instance, health check, deadline, retry có giới hạn và khả năng quan sát rõ ràng.

