# ForwardRoutingFilter và chuyển tiếp nội bộ bằng `forward:`

## 1. Chuyển tiếp nội bộ giải quyết vấn đề gì?

Khi xây dựng API Gateway với **Spring Cloud Gateway**, thông thường một route nhận request rồi proxy qua HTTP tới microservice khác, ví dụ `lb://catalog-service`. Nhưng có những trường hợp gateway cần đưa request tới **handler trong chính ứng dụng gateway**, chẳng hạn endpoint trả dữ liệu dự phòng, endpoint kiểm thử nội bộ hoặc một handler xử lý quy tắc phản hồi đặc biệt.

Với **Spring Cloud Gateway Server WebFlux**, một URI có scheme **`forward:`** biểu thị yêu cầu định tuyến vào cơ chế xử lý handler **nội bộ của Spring WebFlux**. Thành phần đảm nhận việc này là **ForwardRoutingFilter**, một bộ lọc định tuyến được framework cung cấp.

~~~mermaid
flowchart LR
    C[Client] --> G[Spring Cloud Gateway]
    G --> P{Route URI scheme}
    P -->|http / https / lb| U[Upstream HTTP service]
    P -->|forward| H[Local WebFlux handler]
    H --> R[HTTP response]
    U --> R
    R --> C
~~~

Khác biệt quan trọng nằm ở **đích xử lý**: đường `forward:` đưa request đến handler trong cùng ứng dụng, còn `http:`, `https:` và `lb:` là những cách hướng tới upstream qua kết nối mạng (trực tiếp hoặc qua cơ chế phân giải service).

Sau bài học, bạn có thể:

1. Giải thích **ForwardRoutingFilter** hoạt động ở đâu trong chuỗi xử lý request.
2. Phân biệt `forward:` với định tuyến qua HTTP, load balancing, rewrite đường dẫn và redirect.
3. Cấu hình một route `forward:` tới controller WebFlux trong cùng ứng dụng.
4. Hiểu vai trò của **GATEWAY_REQUEST_URL_ATTR**, **GATEWAY_ORIGINAL_REQUEST_URL_ATTR** và **DispatcherHandler**.
5. Thiết kế fallback cục bộ, kiểm tra hành vi định tuyến và phòng tránh route lặp, lộ endpoint nội bộ, blocking I/O và sai lệch quan sát.

> **Phạm vi:** Nội dung này nói về **Spring Cloud Gateway Server WebFlux**, tức biến thể dựa trên Spring WebFlux và Reactor. Spring Cloud Gateway Server Web MVC và Servlet forwarding có những thành phần xử lý khác; không nên áp dụng máy móc lớp `ForwardRoutingFilter` của WebFlux cho các biến thể đó.

## 2. Vị trí của ForwardRoutingFilter trong kiến trúc Gateway

Để hiểu `forward:`, trước tiên cần thấy luồng request thông thường trong Spring Cloud Gateway:

~~~mermaid
flowchart TB
    A[Incoming HTTP request] --> B[Spring WebFlux handler mappings]
    B --> C[RoutePredicateHandlerMapping]
    C -->|Khớp route| D[FilteringWebHandler]
    D --> E[Combined GatewayFilter chain]
    E --> F[RouteToRequestUrlFilter]
    F --> G{Target URL scheme}
    G -->|forward| H[ForwardRoutingFilter]
    H --> I[Spring WebFlux DispatcherHandler]
    I --> J[Local controller / handler]
    G -->|http / https| K[NettyRoutingFilter]
    K --> L[HTTP upstream]
    J --> M[Write response to client]
    L --> M
~~~

Các vai trò:

- **RoutePredicateHandlerMapping:** tìm route phù hợp với request qua predicate như `Path`, `Method`, `Host` hoặc `Header`.
- **FilteringWebHandler:** tạo và thực thi chuỗi gồm các `GlobalFilter` và `GatewayFilter` của route được chọn.
- **RouteToRequestUrlFilter:** chuẩn bị URL đích của route trong thuộc tính exchange dùng cho bước định tuyến.
- **ForwardRoutingFilter:** nhận ra **scheme `forward`** trong URL đích và chuyển việc xử lý tới **DispatcherHandler** của WebFlux.
- **NettyRoutingFilter:** xử lý đường đi proxy HTTP cho URL đích thích hợp; không phải thành phần tạo một HTTP request mới cho `forward:`.
- **DispatcherHandler:** bộ điều phối handler của Spring WebFlux, có thể chọn controller có `@RequestMapping` hoặc functional handler được khai báo trong cùng ứng dụng.

Các thành phần này không phải một chuỗi cố định duy nhất cho mọi request. Route, bộ lọc được bật, thứ tự filter và cấu hình hạ tầng quyết định đường xử lý cụ thể. Sơ đồ chủ ý lược giản nhiều bước như kiểm tra bảo mật, metrics, lỗi, sửa URL và các filter trước/sau.

### ForwardRoutingFilter không phải một filter thêm vào YAML bằng tên

Một route đi tới `forward:` thường được xác định ở **`uri`**:

~~~yaml
uri: forward:///internal/ping
~~~

Bạn không cần thêm mục `ForwardRoutingFilter` vào `filters:`. Framework nhận diện URL có scheme `forward` trong exchange và dùng filter định tuyến tương ứng. Các filter khai báo ở `filters:` như `StripPrefix`, `RewritePath` hoặc filter tự viết vẫn có thể tác động đến request trước bước định tuyến.

## 3. ForwardRoutingFilter hoạt động như thế nào?

Các thành phần Gateway trao đổi dữ liệu qua **ServerWebExchange**. Khi một route đã được chọn, URL đích của nó được đặt vào thuộc tính:

```java
ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR
```

**ForwardRoutingFilter** kiểm tra giá trị URL này. Nếu URL mang scheme `forward`, filter dùng **DispatcherHandler** để xử lý request trong ứng dụng hiện tại. Path của request được thay bằng phần path trong URI `forward:`; URL gốc chưa thay đổi được đưa vào danh sách lưu tại:

```java
ServerWebExchangeUtils.GATEWAY_ORIGINAL_REQUEST_URL_ATTR
```

Luồng ý tưởng:

~~~mermaid
sequenceDiagram
    participant Client
    participant Mapping as RoutePredicateHandlerMapping
    participant Chain as Gateway filter chain
    participant Forward as ForwardRoutingFilter
    participant Dispatcher as DispatcherHandler
    participant Local as Local WebFlux controller

    Client->>Mapping: GET /api/ping
    Mapping->>Chain: Matched route: local-ping
    Chain->>Chain: Set target forward:///internal/ping
    Chain->>Forward: Continue routing
    Forward->>Forward: Change request path to /internal/ping
    Forward->>Dispatcher: Handle within same application
    Dispatcher->>Local: GET /internal/ping
    Local-->>Dispatcher: Mono response
    Dispatcher-->>Forward: Completion / error
    Forward-->>Chain: Completion / error
    Chain-->>Client: HTTP response
~~~

Điểm cần nhớ:

- **Không tạo chuyến HTTP mới tới localhost.** Việc gọi handler nội bộ xảy ra trong tiến trình hiện tại. `forward:` không phải tên host và không dùng DNS, service discovery hay Spring Cloud LoadBalancer để tìm ứng dụng khác.
- **Vẫn là cùng request đang được xử lý ở gateway.** Thông tin như method, header và exchange được sử dụng qua đường đi nội bộ; path được điều chỉnh để handler đích khớp. Nếu body đã bị một filter trước đó tiêu thụ hoặc sửa đổi, handler nội bộ phải làm việc với trạng thái body thực tế còn lại.
- **Có thể xảy ra lỗi như bình thường.** Handler đích không tồn tại có thể dẫn tới 404; method không được chấp nhận có thể dẫn tới 405; exception ở handler có thể chuyển tới cơ chế xử lý lỗi của WebFlux.
- **Forward không đồng nghĩa với redirect.** Client thường chỉ thấy một request/response và không phải tự gửi yêu cầu mới đến path nội bộ.
- **Một số filter chạy cả pha trước và sau.** Filter có phần xử lý sau `chain.filter(exchange)` vẫn có thể quan sát trạng thái kết thúc của quá trình xử lý nội bộ, tùy thứ tự và cách filter được viết.

### Ba thuộc tính exchange thường gặp

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `GATEWAY_ROUTE_ATTR` | Route mà Gateway chọn cho request |
| `GATEWAY_REQUEST_URL_ATTR` | URL đích hiện tại, được các routing filter sử dụng để quyết định nơi xử lý |
| `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` | Danh sách URL trước các lần sửa URL, phục vụ truy vết quá trình định tuyến |

Đây là các thuộc tính nội bộ của `ServerWebExchange`, **không phải HTTP header** mà client tự gửi. Nếu ghi log, hãy chọn dữ liệu cần thiết, tránh ghi token, cookie hoặc query parameter chứa thông tin nhạy cảm.

## 4. Ví dụ hoàn chỉnh: route từ /api/ping tới controller nội bộ

Giả sử ứng dụng gateway có controller trả một phản hồi ngắn nhằm kiểm tra đường đi. Client gọi:

```http
GET /api/ping HTTP/1.1
Host: localhost:8080
```

Ta muốn **Spring Cloud Gateway** chọn route `local-ping`, sau đó **ForwardRoutingFilter** chuyển đến local handler ở **/internal/ping**.

### 4.1. Cấu hình route

Ví dụ dưới đây dùng cấu trúc cấu hình **Gateway Server WebFlux** thuộc các phiên bản mới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: local-ping
              uri: forward:///internal/ping
              predicates:
                - Path=/api/ping
                - Method=GET
~~~

Ở một số phiên bản Spring Cloud Gateway Server WebFlux trước đó, danh sách route dùng cấu trúc **`spring.cloud.gateway.routes`**:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: local-ping
          uri: forward:///internal/ping
          predicates:
            - Path=/api/ping
            - Method=GET
~~~

**Chọn một namespace tương thích với phiên bản thực tế**, không đồng thời sao chép cả hai khối. Tên `forward:///internal/ping` biểu diễn scheme `forward` và path đích `/internal/ping`. Cách viết `forward:/internal/ping` cũng có thể xuất hiện trong ví dụ fallback; điều quan trọng là URI được phân tích ra đúng scheme và path.

### 4.2. Tạo local handler

Controller WebFlux nằm **trong cùng ứng dụng** với Gateway:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class InternalPingController {

    @GetMapping("/internal/ping")
    Mono<Map<String, String>> ping() {
        return Mono.just(Map.of(
                "status", "ok",
                "handledBy", "gateway-local-handler"
        ));
    }
}
~~~

Controller phải được Spring phát hiện bằng component scanning hoặc cấu hình bean tương ứng. Đường dẫn `@GetMapping` phải khớp với **path được forward đến**, thay vì đường dẫn công khai `/api/ping`.

### 4.3. Gửi yêu cầu kiểm tra

~~~bash
curl -i http://localhost:8080/api/ping
~~~

Phản hồi kỳ vọng khi ứng dụng hoạt động đúng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok","handledBy":"gateway-local-handler"}
~~~

Đây là **phản hồi minh họa**, không phải output đã chạy thử trong bài. Header và định dạng JSON thực tế có thể khác tùy cấu hình.

### 4.4. Điều gì xảy ra tại mỗi chặng?

| Bước | Đối tượng | Kết quả |
| --- | --- | --- |
| 1 | Client | Gửi `GET /api/ping` |
| 2 | Route predicate | `Path=/api/ping` và `Method=GET` khớp route `local-ping` |
| 3 | Route URL | Đích có scheme `forward` và path `/internal/ping` |
| 4 | ForwardRoutingFilter | Điều chỉnh path để DispatcherHandler xử lý |
| 5 | DispatcherHandler | Tìm handler cục bộ tại `/internal/ping` |
| 6 | InternalPingController | Tạo phản hồi reactive `Mono<Map<...>>` |
| 7 | HTTP response | Client nhận kết quả từ request ban đầu |

Trong mô hình này, controller cục bộ có thể trả JSON, text, SSE hoặc nội dung reactive khác nếu WebFlux và codec hỗ trợ. ForwardRoutingFilter bản thân nó không yêu cầu body phải là kiểu JSON và cũng không tự tổng hợp dữ liệu thành một phản hồi mới.

## 5. So sánh forward, HTTP proxy, path rewrite và redirect

Những cơ chế này dễ bị nhầm do đều có thể khiến một URL bên ngoài dẫn đến một tài nguyên khác.

| Cơ chế | Đích xử lý | Client có gửi request mới không? | Tác động chính |
| --- | --- | --- | --- |
| `uri: forward:///internal/ping` | WebFlux handler trong cùng ứng dụng Gateway | Không | DispatcherHandler xử lý nội bộ ở path được forward |
| `uri: http://localhost:9000` | HTTP server ở địa chỉ đích | Không đối với lần proxy này | Gateway gọi backend qua HTTP |
| `uri: lb://catalog-service` | Instance service phân giải qua load balancing | Không đối với lần proxy này | Gateway tìm instance và gọi service |
| `RewritePath` / `StripPrefix` | Phụ thuộc `uri` route | Không | Đổi path mà route chuyển tiếp sử dụng |
| `RedirectTo` | URL đích do client truy cập sau redirect | **Có**, nếu client theo redirect | Trả HTTP 3xx và `Location` |

Ví dụ:

~~~yaml
# Chuyển path tới local handler trong cùng ứng dụng:
uri: forward:///internal/ping

# Proxy HTTP tới một service đang lắng nghe trên cổng khác:
uri: http://localhost:9000

# Proxy qua tên service và load balancer:
uri: lb://catalog-service
~~~

**`RewritePath` không tự định nghĩa một đích xử lý**. Nó biến đổi path của request; Gateway vẫn cần route `uri` để biết phải gửi đi đâu. **`RedirectTo`** trả chỉ dẫn cho client, do đó client có thể thấy URL mới và phát sinh chuyến đi mạng mới.

**`forward:` cũng không phải một cách “gọi nhanh” microservice khác bằng cách bỏ qua HTTP.** Muốn forward tới một handler thì handler đó phải nằm trong cùng ứng dụng WebFlux. Nếu business logic nằm ở process/container khác, hãy dùng một cơ chế giao tiếp liên dịch vụ thực sự như HTTP, gRPC hoặc messaging phù hợp.

### Có nên dùng StripPrefix kèm forward?

Có thể, nhưng cần nắm rõ đường dẫn cuối cùng. Trong ví dụ trên, URI đã xác định cụ thể `/internal/ping`, nên không cần thêm `StripPrefix` chỉ để bỏ `/api`. Nếu đồng thời có các filter biến đổi path, kết quả tùy thứ tự filter và cách URL đích được hình thành. Hãy ghi rõ **path đầu vào**, **path sau filter** và **path nhận tại handler**, sau đó kiểm chứng bằng request thật.

## 6. Ứng dụng thực tế: CircuitBreaker fallback tới local handler

Một trường hợp sử dụng phổ biến của `forward:` là **fallback**. Giả sử request cần tới Pricing service, nhưng service tạm thời không khả dụng. Ta có thể dùng filter **CircuitBreaker** và chỉ khi điều kiện fallback xảy ra, xử lý request ở controller trong Gateway:

~~~mermaid
flowchart TB
    Client[GET /api/prices/P42] --> Edge[Gateway route: pricing]
    Edge --> CB{CircuitBreaker}
    CB -->|Upstream healthy| Service[Pricing service]
    Service --> Result[Actual price response]
    CB -->|Failure / open circuit| Forward[forward:/internal/fallback/pricing]
    Forward --> Local[Local fallback handler]
    Local --> Error[Controlled error response]
~~~

Ví dụ cấu hình cho **Gateway Server WebFlux**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: pricing
              uri: lb://pricing-service
              predicates:
                - Path=/api/prices/**
                - Method=GET
              filters:
                - name: CircuitBreaker
                  args:
                    name: pricingCircuitBreaker
                    fallbackUri: forward:/internal/fallback/pricing
~~~

Để sử dụng được filter CircuitBreaker, dự án cần các dependency/tích hợp Spring Cloud CircuitBreaker thích hợp với phiên bản đang chạy, chẳng hạn biến thể Reactor Resilience4j, cùng cấu hình breaker cần thiết. Cấu hình ví dụ **chỉ nhằm minh họa đường đi fallback**, chưa bao gồm toàn bộ policy production về timeout, ngưỡng lỗi, hay giới hạn đồng thời.

Local handler:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class PricingFallbackController {

    @GetMapping("/internal/fallback/pricing")
    Mono<ResponseEntity<Map<String, String>>> fallback() {
        return Mono.just(
                ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                        .body(Map.of(
                                "code", "PRICE_SERVICE_UNAVAILABLE",
                                "message", "Không thể lấy giá tại thời điểm này"
                        ))
        );
    }
}
~~~

**Vì sao trả 503?** Giá có thể là thông tin thiết yếu để quyết định mua hàng. Trả một “giá dự phòng” không đáng tin hoặc mã 200 có thể đánh lừa client. Với dữ liệu phụ trợ như gợi ý sản phẩm, fallback trả kết quả rỗng hoặc dữ liệu cache có nhãn phù hợp có thể được chấp nhận **nếu hợp đồng nghiệp vụ cho phép**.

Điểm dễ nhầm: **CircuitBreaker filter không forward mọi request ngay lập tức**. Bình thường, request vẫn được gửi tới Pricing service. `fallbackUri` là đường đi thay thế khi filter kích hoạt fallback theo điều kiện và lỗi mà nó quan sát. Một phản hồi 4xx/5xx từ backend không nhất thiết tự động kích hoạt fallback nếu chưa cấu hình điều kiện cần thiết. Các filter khác như rate limiter có thể trả 429 độc lập với CircuitBreaker.

### Lỗi phát sinh trước và sau khi response được gửi

Nếu upstream lỗi **trước khi response được commit**, Gateway thường còn khả năng trả phản hồi fallback phù hợp. Nếu upstream đang gửi một stream rồi lỗi **sau khi header và một phần body đã được gửi cho client**, không thể giả định gateway sẽ thay toàn bộ response bằng mã HTTP khác. Vì vậy fallback với SSE, NDJSON hay download lớn cần hợp đồng reconnect/retry/range phù hợp với ứng dụng.

### Không dùng local fallback để che một sự cố cần phát hiện

Hãy quan sát riêng:

- Tổng request vào route `pricing`.
- Tỷ lệ CircuitBreaker mở và số lượt kích hoạt fallback.
- Thời gian phản hồi ở upstream và local handler.
- Mã HTTP trả cho client và phân loại lỗi.

Một fallback luôn trả 200 có thể khiến dashboard HTTP cấp gateway tưởng rằng mọi thứ bình thường, trong khi Pricing service đã không đáp ứng được. Trạng thái suy giảm phải được phản ánh trong metrics và tracing theo thiết kế.

## 7. Bảo mật và ranh giới tin cậy của handler nội bộ

Đây là một điểm rủi ro lớn khi dùng `forward:`: **đường dẫn “/internal/...” không tự trở thành private chỉ vì được đặt tên internal**.

Nếu controller có `@GetMapping("/internal/ping")` trên cùng HTTP server và không bị chặn, một client bên ngoài có thể thử truy cập trực tiếp:

~~~bash
curl -i http://localhost:8080/internal/ping
~~~

Request này có thể được xử lý trực tiếp bởi WebFlux controller, tùy route mapping, security và hạ tầng. Không nên chỉ bảo vệ `/api/ping` rồi cho rằng `/internal/ping` không tồn tại đối với người dùng bên ngoài.

**Các nguyên tắc bảo vệ:**

1. **Bảo vệ path gốc và path handler:** cấu hình Spring Security WebFlux, network policy, hoặc cơ chế kiểm soát truy cập phù hợp để client không gọi trực tiếp được endpoint nội bộ nhạy cảm.
2. **Không giả định xác thực sẽ tự chạy lần thứ hai theo path đã forward.** Việc xử lý handler qua DispatcherHandler không đồng nghĩa mọi WebFilter/security filter của request HTTP đầu vào sẽ được chạy lại như một request mới. Nếu rule Spring Security chỉ match `/internal/**`, hãy kiểm tra cách nó hoạt động khi client gọi path công khai `/api/**`.
3. **Service hoặc handler vẫn phải kiểm tra quyền nghiệp vụ.** Gateway xác thực token không chứng minh người dùng được truy cập mọi tài nguyên.
4. **Không tin header nội bộ do client tự đưa vào.** Các header như `X-User-Id`, `X-Role` hoặc danh tính đã ủy quyền cần được tạo từ ngữ cảnh đáng tin cậy, không lấy thẳng từ request.
5. **Không để fallback tiết lộ dữ liệu nhạy cảm:** tên host nội bộ, stack trace, URL service thực hoặc thông điệp lỗi có chứa token.
6. **Giữ bộ nhớ và thời gian xử lý có giới hạn:** local handler chạy trong chính ứng dụng gateway, nên công việc CPU nặng hay blocking I/O có thể ảnh hưởng mọi request đi qua gateway.

Ví dụ bảo vệ bằng WebFlux Security cần thiết kế theo chính sách của ứng dụng; một matcher chỉ chặn `/internal/**` ở vòng HTTP đầu tiên có thể **không đủ** để bảo vệ luồng forward từ `/api/**`. Hãy kiểm thử cả yêu cầu trực tiếp lẫn yêu cầu được forward với người dùng không xác thực và người dùng thiếu quyền.

## 8. Khi nào forwarding có thể dẫn tới vòng lặp?

Hãy xét một route quá rộng:

~~~yaml
predicates:
  - Path=/**
uri: forward:///internal/ping
~~~

Nếu đường `/internal/ping` lại được chọn bởi một route Gateway hoặc một handler có logic forward quay về Gateway, hệ thống có nguy cơ **lặp xử lý**. Tùy cấu hình handler mapping, kết quả có thể là request được xử lý sai handler, đệ quy sâu, lỗi 5xx hoặc quá tải. Bài học là không dùng route catch-all mà không tính đến đường dẫn nội bộ và thứ tự ưu tiên handler.

**Biện pháp phòng tránh:**

- Chọn path nội bộ có namespace rõ ràng, không trùng path public hoặc path sẽ được Gateway bắt và forward lại.
- Đặt predicate chính xác và kiểm tra mức độ phủ của các route `Path=/**`, regex hoặc Host.
- Tránh cho fallback route gọi ngược lại chính endpoint đã hỏng mà không có điều kiện dừng.
- Viết test cho các tình huống path đích bị bắt lại, không có handler, sai method, và fallback thất bại.
- Không dùng request header từ client để quyết định đường `forward:` tùy ý nếu chưa kiểm tra/giới hạn cho phép; tránh biến Gateway thành bộ định tuyến nội bộ không kiểm soát.

Lưu ý: có vòng lặp hay không phụ thuộc cách ứng dụng cấu hình handler mappings và filter; một route `Path=/**` **không tự động chứng minh** mọi forward đều lặp. Điều cần xác minh là handler thực tế được chọn **sau khi path bị đổi**.

## 9. Forward và vòng đời request/response reactive

Vì `forward:` hoạt động qua **Spring WebFlux**, các nguyên tắc Reactor vẫn áp dụng:

- **Không gọi `block()` trên event loop** trong controller/fallback. Một fallback tưởng là nhỏ nhưng dùng truy vấn JDBC blocking có thể làm nghẽn gateway khi sự cố upstream đồng thời diễn ra.
- **Không tự `subscribe()` body để log hoặc kiểm tra**, vì request body reactive có thể chỉ được tiêu thụ một lần. Handler forward có thể không còn dữ liệu để đọc.
- **Không mặc định forward sao chép body.** Nếu cần đọc body ở filter rồi cho controller đọc tiếp, phải sử dụng cơ chế caching/decorating body thích hợp, với giới hạn kích thước và vòng đời `DataBuffer` chính xác.
- **Tôn trọng cancellation và timeout**. Nếu client ngắt kết nối trong khi local handler đang chạy, các publisher có thể nhận tín hiệu hủy; công việc ngoài Reactor không nhất thiết tự dừng nếu không được tích hợp đúng.
- **Không để lỗi fallback chạy vòng vô hạn.** Nếu fallback cũng bị lỗi, cần error handler có thể đưa ra phản hồi an toàn hoặc ghi nhận việc không thể hoàn tất response.

### Ví dụ handler reactive không blocking

~~~java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
class LocalEventController {

    @GetMapping(value = "/internal/events",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<String> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .take(3)
                .map(i -> "event-" + i);
    }
}
~~~

Nếu có route `uri: forward:///internal/events`, local handler có thể trả SSE qua cùng kết nối HTTP đang mở. Tuy nhiên **forward không tự bảo đảm streaming xuyên suốt**: codec, các gateway filter, proxy phía trước và client có thể ảnh hưởng đến buffering và flush. Khi ứng dụng cần đảm bảo sự kiện không mất hoặc phát lại sau ngắt kết nối, phải thiết kế riêng event ID và lưu trữ/broker phù hợp.

## 10. Logging, metrics và tracing

Khi request được forward, việc chỉ nhìn URL bên ngoài hoặc chỉ nhìn path handler có thể gây khó hiểu. Một log có ích nên thể hiện các dữ liệu như:

| Thuộc tính | Ví dụ | Mục đích |
| --- | --- | --- |
| Path public | `/api/ping` | Biết client đã gọi gì |
| Route ID | `local-ping` | Xác định route được chọn |
| Forward target | `/internal/ping` | Xác định handler nội bộ nhận request |
| Method và status | `GET`, `200` | Đánh giá kết quả |
| Trace/correlation ID | ID được tạo hoặc truyền hợp lệ | Ghép log xuyên suốt các bước |
| Duration | 12 ms | Phân tích độ trễ |

Trong ứng dụng thật, log có thể được tạo từ Spring Cloud Gateway metrics, tracing và các hook hỗ trợ. Nếu phải viết custom filter, đọc thuộc tính exchange theo hợp đồng của framework; không ghi body, password, token hoặc cookie nhạy cảm.

Một điểm khác biệt để hiểu trace: **forward đến controller trong cùng tiến trình không phải một HTTP client call tới upstream**, nên không mặc định có một span outbound HTTP mới giống đường đi qua `NettyRoutingFilter`. Muốn phân biệt thời gian Gateway routing và thời gian local handler, cần instrument đúng các vùng xử lý. Với CircuitBreaker fallback, tách được **request được phục vụ bằng fallback** khỏi request upstream thành công rất quan trọng.

### Theo dõi khi troubleshoot

Nếu `GET /api/ping` trả 404, kiểm tra tuần tự:

1. Predicate có khớp method/path/host thực tế không?
2. Route có được nạp trong đúng namespace cấu hình của phiên bản Gateway không?
3. `uri` có scheme `forward` và path đích đúng không?
4. Controller nội bộ đã được component scan và khai báo đúng `@GetMapping` chưa?
5. Có filter nào thay đổi path hoặc request body trước khi tới ForwardRoutingFilter không?
6. Spring Security, handler mapping hoặc error handler có chặn/thay đổi kết quả không?

Nếu `GET /api/ping` trả 500 hoặc timeout, kiểm tra exception ở local handler, vòng lặp route, blocking I/O và giới hạn timeout. Nếu phản hồi trả 200 nhưng sai nội dung, kiểm tra route đã chọn và handler thực nhận request.

## 11. Thực hành: thiết kế một local fallback có kiểm soát

**Bài toán:** Gateway có route tới Inventory service. Khi service đang lỗi, hệ thống cần thông báo tạm không thể kiểm tra tồn kho. Không được tự khẳng định sản phẩm còn hàng.

### Bước 1 — Thiết kế route

Tạo route cho `GET /api/inventory/**` tới `lb://inventory-service`. Sử dụng `CircuitBreaker` với `fallbackUri: forward:/internal/fallback/inventory` và cấu hình điều kiện breaker phù hợp cho môi trường thử nghiệm.

### Bước 2 — Tạo handler

Tạo controller WebFlux nhận `GET /internal/fallback/inventory`, trả `503 Service Unavailable` cùng JSON:

~~~json
{
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Chưa thể xác nhận tồn kho",
  "retryable": true
}
~~~

`retryable` chỉ là gợi ý cho client nếu hợp đồng API định nghĩa rõ cách retry; không thay thế backoff, idempotency và deadline ở client. Với GET đọc dữ liệu, retry có thể phù hợp hơn một thao tác POST không idempotent, nhưng vẫn phải kiểm soát tần suất khi service gặp sự cố.

### Bước 3 — Kiểm chứng hai đường xử lý

| Thao tác kiểm tra | Kết quả mong đợi |
| --- | --- |
| Inventory service khỏe | Gateway trả dữ liệu Inventory thực, không vào fallback |
| Inventory service lỗi theo điều kiện breaker | Request tới local handler, trả 503 và mã lỗi đã định nghĩa |
| Gọi trực tiếp `/internal/fallback/inventory` từ bên ngoài | Bị chặn/kiểm soát theo chính sách bảo mật |
| Gọi `POST /api/inventory/... ` nếu chỉ cho phép GET | Không được đi qua route GET hoặc tạo side effect ngoài dự kiến |
| Handler fallback không tồn tại | Đường fallback thất bại; phát hiện qua log/metric và test |
| Nhiều request đồng thời khi upstream lỗi | Gateway còn đáp ứng được; handler không blocking hoặc tạo tải tăng không giới hạn |
| Fallback bị lỗi hoặc client ngắt kết nối | Có quan sát lỗi/cancel, không tạo vòng lặp hoặc rò rỉ tài nguyên |

### Bước 4 — Quan sát

Ghi nhận route ID, URL gốc, target forward, số lần fallback, HTTP status và độ trễ. Kiểm tra trường hợp `CircuitBreaker` đã mở: số lời gọi bị từ chối hoặc chuyển fallback phải được phân biệt với lỗi 503 do chính backend trả.

### Bước 5 — Đặt câu hỏi kiến trúc

- Fallback này có đủ đơn giản để chạy trong chính tiến trình Gateway không?
- Dữ liệu dự phòng có thể tin cậy không, hay phải trả lỗi rõ ràng?
- Nếu Gateway phải kết nối cơ sở dữ liệu và xử lý nghiệp vụ phức tạp để tạo fallback, có nên chuyển sang một service/facade riêng không?
- Có route `Path=/**` hoặc rule bảo mật nào vô tình khiến path `/internal/fallback/**` bị bắt hoặc lộ ra ngoài không?
- Timeout và tracing có giúp biết response lỗi đến từ upstream, CircuitBreaker hay local handler không?

## 12. Những nhầm lẫn cần tránh

**“ForwardRoutingFilter là cách gọi service khác không tốn network.”** Sai. Nó đưa request tới handler **trong cùng ứng dụng WebFlux**. Service khác process vẫn cần một kênh giao tiếp phù hợp.

**“`forward:` giống `redirect:`.”** Sai. Forward là xử lý nội bộ, còn redirect thường gửi phản hồi 3xx để client tự truy cập URL mới.

**“Chỉ cần `RewritePath` là thành forward.”** Sai. Rewrite sửa path; route URI quyết định hướng xử lý. Forward sử dụng scheme `forward`.

**“Controller có path `/internal/**` thì tự động private.”** Sai. Path là tên; tính bảo mật đến từ cấu hình xác thực, phân quyền và ranh giới mạng, cần kiểm thử cả truy cập trực tiếp lẫn forward.

**“Mọi filter và Spring Security được chạy lại đầy đủ khi forward.”** Không nên giả định. ForwardRoutingFilter điều phối xử lý qua DispatcherHandler, không tạo một request HTTP hoàn toàn mới.

**“Fallback luôn trả 200 sẽ làm hệ thống ổn định.”** Có thể che giấu sự cố và vi phạm tính đúng đắn của dữ liệu. Chọn status, payload, quan sát và chiến lược phục hồi theo ngữ nghĩa nghiệp vụ.

**“Do Gateway dùng WebFlux nên local handler có thể gọi hàm blocking tùy ý.”** Sai. Công việc blocking trên event loop ảnh hưởng độ trễ của nhiều request. Cần dùng API reactive hoặc cô lập tác vụ blocking có kiểm soát.

## 13. Tóm tắt

- **ForwardRoutingFilter** thuộc pipeline định tuyến của **Spring Cloud Gateway Server WebFlux** và nhận diện URI đích có scheme **`forward`**.
- Với `forward:`, Gateway giao request cho **DispatcherHandler** để tìm và gọi WebFlux handler **trong chính ứng dụng**, đồng thời điều chỉnh path và lưu thông tin URL trước khi thay đổi trong exchange.
- `forward:` phù hợp cho một số local endpoint và **CircuitBreaker fallback**, không thay thế HTTP routing, load balancing hoặc các cơ chế liên dịch vụ.
- **Forward, rewrite và redirect là ba thao tác khác nhau.** Hãy xác định route predicate, URL đích, path cuối cùng và handler thực tế để tránh cấu hình sai.
- **Handler nội bộ không tự động an toàn chỉ vì tên path**. Cần ngăn truy cập trực tiếp trái phép và kiểm tra chính sách xác thực/phân quyền áp dụng cho cả đường public lẫn local.
- Quan sát **route ID, original URL, forward target, status, latency và số lần fallback**; phòng tránh vòng lặp, blocking I/O và xử lý body sai cách để Gateway giữ được vai trò cổng vào microservices an toàn, ổn định.
