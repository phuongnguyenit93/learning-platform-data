# Thứ tự ưu tiên khi nhiều tuyến cùng khớp

## 1. Vấn đề: cùng một request có thể thỏa nhiều route

Trong **Spring Cloud Gateway**, một route thường gồm `id`, `uri`, danh sách **predicate** và các **filter** tùy chọn. Predicate kiểm tra request theo đường dẫn (`Path`), HTTP method (`Method`), host, header, query hoặc những điều kiện khác. Khi hệ thống microservices có nhiều API, các điều kiện này rất dễ chồng lấn:

~~~text
GET /api/orders/42
  ├─ Path=/api/orders/**  → khớp
  └─ Path=/api/**         → cũng khớp
~~~

Nếu cả hai route đều có thể nhận request, **Spring Cloud Gateway chọn route nào?** Câu trả lời nằm ở thuộc tính **`order` của route**: trong mô hình **Spring Cloud Gateway Server WebFlux**, route có giá trị `order` **nhỏ hơn** được xét **trước**. Gateway chọn **route đầu tiên có toàn bộ predicate khớp** theo thứ tự đó.

Đây là bài thuộc chương **Cấu hình tuyến** của module **SPRING_CLOUD_GATEWAY**. Nắm được ưu tiên route giúp tránh chuyển request nhầm dịch vụ, hiểu vì sao bộ lọc biến đổi đường dẫn/header không được thực thi, và giữ ranh giới rõ ràng khi sau này bổ sung service discovery, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request.

> **Điểm cần nhớ:** Độ cụ thể của `Path` (ví dụ `/api/orders/**` so với `/api/**`) **không mặc nhiên quyết định** route thắng. Hãy cấu hình `order` rõ ràng nếu các route có khả năng cùng khớp.

## 2. Gateway chọn route theo thứ tự nào?

Đối với WebFlux Gateway, `RoutePredicateHandlerMapping` tìm route phù hợp từ danh sách route do `RouteLocator` cung cấp. Các route được sắp xếp theo ưu tiên; gateway lần lượt kiểm tra predicate và lấy route khớp đầu tiên. Sau khi route được chọn, `FilteringWebHandler` mới tổ chức các `GlobalFilter` và `GatewayFilter` để xử lý request.

~~~mermaid
flowchart TD
    C["Request đến Gateway"] --> S["Lấy các route theo thứ tự ưu tiên"]
    S --> P1{"Route order thấp nhất<br/>có khớp mọi predicate?"}
    P1 -->|"Có"| R["Chọn route đó"]
    P1 -->|"Không"| P2{"Xét route kế tiếp"}
    P2 -->|"Khớp"| R
    P2 -->|"Không khớp, còn route"| P2
    P2 -->|"Hết route"| N["Không tìm được route"]
    R --> F["Chạy filter chain<br/>của route đã chọn"]
    F --> U["Xác định URL đích / chọn instance"]
    U --> B["Gửi request đến backend"]
    N --> E["Thường 404 nếu không có<br/>handler WebFlux khác"]
~~~

Trong cấu hình route:

- `order: -20`: ưu tiên cao hơn `order: -10`.
- `order: -10`: ưu tiên cao hơn `order: 0`.
- `order: 0`: ưu tiên cao hơn `order: 100`.
- **Không khai báo `order`:** giá trị mặc định thường là **`0`**.

Vì các giá trị nhỏ hơn được xét trước, một route tổng quát có `order: -100` có thể “nuốt” request của route cụ thể có `order: 0`. Ngược lại, route có ưu tiên cao **nhưng predicate không khớp** sẽ bị bỏ qua, và gateway tiếp tục xét route kế tiếp.

### 2.1. Điều kiện bên trong một route vẫn phải cùng thỏa

Xét route:

~~~yaml
predicates:
  - Path=/api/orders/special/**
  - Method=GET
~~~

Hai predicate được kết hợp theo nghĩa **AND**: `GET /api/orders/special/42` khớp, còn `POST /api/orders/special/42` không khớp route này dù đường dẫn giống hệt. Nếu phía sau có route tổng quát `Path=/api/orders/**` và không hạn chế method, request POST có thể rơi vào route tổng quát đó.

**Ưu tiên cao không ép một request khớp predicate.** `order` chỉ điều khiển thứ tự xét các route đủ điều kiện.

### 2.2. Chỉ một route được chọn cho lượt định tuyến

Khi hai route cùng thỏa `Path`:

1. Gateway chọn route có ưu tiên thích hợp.
2. Các **gateway filter riêng của route được chọn** được thực thi cùng những filter dùng chung phù hợp.
3. Gateway tạo URL đích và chuyển tiếp request theo `uri` của route đó.
4. Các filter gắn riêng vào route **không được chọn** không tự chạy và không được “gộp” vào route thắng.

Điều này đặc biệt quan trọng với `StripPrefix`, `RewritePath`, `SetRequestHeader` hoặc `CircuitBreaker`: nếu một filter được khai báo trên route thua, bạn không nên kỳ vọng nó tác động lên request.

## 3. Cấu hình minh họa ba route chồng lấn

Giả sử có một backend để thử nghiệm tại `http://localhost:9001`. Để chỉ quan sát **route được chọn**, ba route dưới đây cùng trỏ tới backend đó và mỗi route thêm một header khác nhau. Khi triển khai hệ thống thật, chúng có thể trỏ đến các microservice độc lập hoặc URI kiểu `lb://orders-service`.

Ví dụ cho **Spring Cloud Gateway Server WebFlux** sử dụng namespace cấu hình mới:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: route-priority-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: special-get
              order: -20
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/special/**
                - Method=GET
              filters:
                - SetRequestHeader=X-Lab-Route, special-get
                - AddResponseHeader=X-Lab-Route, special-get

            - id: orders-general
              order: -10
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - SetRequestHeader=X-Lab-Route, orders-general
                - AddResponseHeader=X-Lab-Route, orders-general

            - id: api-fallback
              order: 100
              uri: http://localhost:9001
              predicates:
                - Path=/api/**
              filters:
                - SetRequestHeader=X-Lab-Route, api-fallback
                - AddResponseHeader=X-Lab-Route, api-fallback
~~~

> **Phiên bản cấu hình:** Các phiên bản Spring Cloud Gateway WebFlux cũ dùng `spring.cloud.gateway.routes`. Trong trường hợp đó, đặt toàn bộ danh sách `routes` dưới `spring.cloud.gateway.routes` thay vì `spring.cloud.gateway.server.webflux.routes`. Chọn đúng cấu trúc cho phiên bản Spring Boot/Spring Cloud đang sử dụng; không định nghĩa trùng một route ở cả hai namespace.

| Route | `order` | Predicate | Vai trò |
| --- | ---: | --- | --- |
| `special-get` | **-20** | `Path=/api/orders/special/**` **và** `Method=GET` | Trường hợp GET đặc biệt, xét đầu tiên |
| `orders-general` | **-10** | `Path=/api/orders/**` | Xử lý các request orders còn lại |
| `api-fallback` | **100** | `Path=/api/**` | Bắt các request API không thuộc hai route phía trên |

Thuộc tính `order` nằm **ngang cấp** với `id`, `uri`, `predicates` và `filters` của route, không nằm bên trong `predicates` hoặc `filters`.

### Vì sao hai filter thêm header?

`SetRequestHeader=X-Lab-Route, ...` đặt header **trên request** đi xuống backend; backend có thể đọc nó để xác nhận tuyến thắng. `AddResponseHeader=X-Lab-Route, ...` đặt header **trên response** đi về client, giúp xem ngay kết quả bằng `curl -i`. Đây là dấu đánh dấu phục vụ bài lab, không phải cơ chế xác thực.

Ví dụ cố tình giữ nguyên path để việc kiểm chứng ưu tiên route dễ quan sát. Khi cần chuyển `/api/orders/42` thành `/orders/42`, có thể thêm `StripPrefix=1` vào route phù hợp; hành vi đó thuộc **giai đoạn filter**, sau khi route đã được chọn.

## 4. Bảng dự đoán route được chọn

Áp dụng cấu hình trên:

| Request | Các route có predicate khớp | Route được chọn | Lý do |
| --- | --- | --- | --- |
| `GET /api/orders/special/42` | `special-get`, `orders-general`, `api-fallback` | **`special-get`** | Cả ba khớp; `-20` nhỏ nhất |
| `POST /api/orders/special/42` | `orders-general`, `api-fallback` | **`orders-general`** | `special-get` không khớp `Method=GET` |
| `GET /api/orders/42` | `orders-general`, `api-fallback` | **`orders-general`** | `-10` ưu tiên hơn `100` |
| `DELETE /api/orders/42` | `orders-general`, `api-fallback` | **`orders-general`** | Route orders không có `Method` predicate |
| `GET /api/customers/42` | `api-fallback` | **`api-fallback`** | Hai route orders không khớp `Path` |
| `GET /health-check` | Không có | **Không chọn route** | Không đường dẫn nào khớp `/api/**` |

Trường hợp cuối thường trả `404 Not Found` nếu gateway không có handler WebFlux hoặc route khác cho `/health-check`. **Không phải cứ request không chọn route thì bắt buộc trả 404 trong mọi cấu hình**: ứng dụng có thể định nghĩa endpoint khác để xử lý.

Tương tự, route predicate `Method=GET` không tự sinh `405 Method Not Allowed` khi nhận POST. Nếu vẫn còn route khác khớp, POST được xét trên route đó; nếu không có route/handler nào xử lý, kết quả thường là 404. Backend vẫn có thể trả 405 khi request đã tới một endpoint chỉ cho phép method khác.

## 5. Thực hành: nhìn tận mắt route thắng

Để bài thử độc lập với nhiều microservice, chạy một backend echo tối giản có thể trả lời mọi path và method, ghi lại `X-Lab-Route` nhận từ gateway.

### 5.1. Tạo backend WebFlux đơn giản

Tạo ứng dụng Spring Boot với dependency `spring-boot-starter-webflux`, đặt `server.port=9001` trong `application.properties` và thêm mã sau. Hai lớp ở cùng package `demo.echo`.

~~~java
package demo.echo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EchoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EchoApplication.class, args);
    }
}
~~~

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EchoController {

    @RequestMapping("/**")
    public Map<String, Object> inspect(ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethod().name());
        result.put("path", request.getPath().value());
        result.put("query", request.getURI().getRawQuery());
        result.put("routeSeenByBackend",
                   request.getHeaders().getFirst("X-Lab-Route"));
        return result;
    }
}
~~~

Echo backend không tự gán response header `X-Lab-Route`, nên header đó xuất hiện trong phản hồi qua gateway sẽ đến từ `AddResponseHeader`. Khi gọi trực tiếp tới `localhost:9001`, giá trị `routeSeenByBackend` có thể là `null` vì không có filter gateway thêm header.

### 5.2. Khởi chạy Gateway WebFlux

Ứng dụng gateway cần starter **Spring Cloud Gateway Server WebFlux** và Spring Cloud BOM tương thích với Spring Boot. Với các phiên bản mới, tên starter thường là `spring-cloud-starter-gateway-server-webflux`; ở một số bản trước là `spring-cloud-starter-gateway`. Không dùng lẫn starter Servlet MVC nếu mục tiêu là Gateway WebFlux.

Lưu YAML ở mục 3 vào `application.yml` của gateway và khởi chạy cả hai ứng dụng trong **hai terminal khác nhau**:

~~~bash
# Trong thư mục dự án echo backend:
./mvnw spring-boot:run

# Trong thư mục dự án gateway:
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng `mvnw.cmd spring-boot:run`. Các lệnh chỉ là hướng dẫn thực hành; kết quả ở những mục sau là **kỳ vọng**, không phải thông số đã đo trên máy người đọc.

### 5.3. Gửi request và đối chiếu header

~~~bash
# Ba route cùng khớp; special-get thắng:
curl -i "http://localhost:8080/api/orders/special/42"

# special-get không khớp method POST; orders-general thắng:
curl -i -X POST "http://localhost:8080/api/orders/special/42"

# Route orders-general thắng api-fallback:
curl -i "http://localhost:8080/api/orders/42"

# Chỉ route api-fallback khớp:
curl -i "http://localhost:8080/api/customers/42"
~~~

Kết quả kỳ vọng cho request đầu tiên:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Lab-Route: special-get

{"method":"GET","path":"/api/orders/special/42","query":null,"routeSeenByBackend":"special-get"}
~~~

Ba request còn lại lần lượt có `X-Lab-Route: orders-general`, `X-Lab-Route: orders-general` và `X-Lab-Route: api-fallback`. Trong JSON, trường `routeSeenByBackend` có cùng giá trị với route đã được chọn. Với request POST, controller ở ví dụ chấp nhận mọi method và không đọc body nên vẫn có thể trả 200.

**Thử kiểm tra header giả mạo:** gửi `-H "X-Lab-Route: chosen-by-client"`; gateway dùng `SetRequestHeader` để đặt lại giá trị theo route. Backend phải nhìn thấy giá trị gateway chọn chứ không phải giá trị giả của client. Đừng vì thế mà dùng header đánh dấu này làm chứng cứ xác thực người dùng.

### 5.4. Thử đảo thứ tự để quan sát thay đổi

Trong bài lab, đổi **chỉ** `order` của `orders-general` từ `-10` sang `-30`, sau đó nạp lại cấu hình theo cách phiên bản/ứng dụng của bạn hỗ trợ (đối với YAML tĩnh, cách đơn giản là khởi động lại gateway):

~~~yaml
- id: orders-general
  order: -30
  uri: http://localhost:9001
  predicates:
    - Path=/api/orders/**
  filters:
    - SetRequestHeader=X-Lab-Route, orders-general
    - AddResponseHeader=X-Lab-Route, orders-general
~~~

Giờ `GET /api/orders/special/42` sẽ chọn **`orders-general`** vì `-30 < -20`, dù `Path=/api/orders/special/**` có vẻ “cụ thể hơn”. Đây là phép thử trực tiếp cho thấy độ cụ thể của path không tự áp đảo thứ tự route.

Đổi lại `order: -10` sau khi thử để khôi phục kịch bản ban đầu.

## 6. Cấu hình trùng `order` và các nguồn route khác nhau

Khi không đặt `order`, đa số route có giá trị mặc định `0`. Ví dụ:

~~~yaml
routes:
  - id: orders-route
    uri: http://localhost:9001
    predicates:
      - Path=/api/orders/**

  - id: catch-all
    uri: http://localhost:9001
    predicates:
      - Path=/api/**
~~~

Hai route đều có thể khớp `GET /api/orders/42` và cùng ưu tiên `0`. Một cấu hình cụ thể có thể biểu hiện thứ tự ổn định trong một lần chạy, nhưng **không nên dựa vào thứ tự khai báo YAML để đảm bảo quy tắc nghiệp vụ** khi nhiều route có `order` bằng nhau. Kết quả có thể bị ảnh hưởng bởi nguồn route, cơ chế kết hợp/sắp xếp, thay đổi phiên bản hoặc refresh route.

Các nguồn phổ biến gồm:

- Route khai báo trong cấu hình ứng dụng.
- Route tạo bằng Java DSL (ví dụ `RouteLocatorBuilder`).
- Route phát sinh từ discovery locator hoặc nguồn động nếu ứng dụng có cấu hình.

Khi nhiều nguồn cùng đóng góp route, hãy **đặt `order` nhất quán**, giữ `id` duy nhất và tránh predicate chồng lấn ngoài ý muốn. Nếu thứ tự có tính quyết định với nghiệp vụ hoặc bảo mật, thiết kế các route sao cho predicate loại trừ nhau càng nhiều càng tốt.

Ví dụ, thay vì để `GET /api/reports/public/**` và một catch-all đều nhận cùng đường dẫn rồi hy vọng filter bảo mật chạy đúng, có thể kết hợp predicate rõ ràng với chính sách authorization độc lập theo endpoint/tài nguyên.

## 7. Phân biệt `order` của route và `order` của filter

Đây là hai tầng **khác nhau** trong Spring Cloud Gateway:

| Khái niệm | Giai đoạn | Điều được sắp thứ tự | Tác dụng |
| --- | --- | --- | --- |
| **Route `order`** | **Trước** khi chạy gateway filter | Các route có khả năng được chọn | Route nào được xét trước khi predicate cùng khớp |
| **Filter `order`** | **Sau** khi đã chọn route | `GlobalFilter` và `GatewayFilter` trong chuỗi đã ghép | Filter nào chạy logic pre trước, logic post sau |
| **`WebFilter` / handler mapping order** | Tầng WebFlux bao quanh hoặc đứng trước gateway handler | Filter/handler của framework WebFlux | Điều phối xử lý HTTP tổng thể, không thay thế thứ tự route |

Ví dụ về filter toàn cục:

~~~java
@Component
public class RequestTimingFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             GatewayFilterChain chain) {
        long start = System.nanoTime();
        return chain.filter(exchange)
                .doFinally(signal ->
                        log.info("elapsedNanos={}",
                                System.nanoTime() - start));
    }
}
~~~

Đây là **đoạn minh họa phần thân filter**: cần khai báo các import tương ứng và biến logger trong lớp để biên dịch. Giá trị `-100` ở `getOrder()` chỉ ảnh hưởng thứ tự filter khi route đã được chọn; **không làm route chứa filter đó có ưu tiên `-100`**. Trong filter chain, filter order thấp thường chạy phần **pre** sớm hơn và phần **post** muộn hơn.

Khi cần thay đổi route được chọn, hãy điều chỉnh **predicate** và **route `order`**; khi cần thay đổi thời điểm đo log, sửa header hoặc áp dụng logic trong chuỗi, hãy xem **filter order**.

## 8. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| Route catch-all nhận cả API đặc biệt | `order` của catch-all thấp hơn route cụ thể | So sánh `order` của các route cùng khớp |
| Route có ưu tiên cao không được chọn | Một predicate khác (`Method`, `Host`, `Header`...) không khớp | Kiểm tra **toàn bộ** predicate, không chỉ `Path` |
| Filter riêng không chạy | Request được chọn vào route khác | Gắn header đánh dấu cho từng route hoặc xem route ID |
| Cấu hình giống đúng nhưng luôn 404 | YAML dùng sai namespace hoặc route không được nạp | Kiểm tra route runtime và log khởi động |
| Đã sửa YAML nhưng chưa thấy ưu tiên mới | Ứng dụng chưa nạp lại cấu hình/route cache | Khởi động lại hoặc refresh theo cơ chế được hỗ trợ |
| Backend trả 404 dù route đã khớp | URI/path sau `StripPrefix`, `RewritePath` không đúng endpoint backend | So sánh path đầu vào gateway với path backend nhận |
| Kết quả khác nhau giữa các lần chạy | Route trùng ưu tiên, nhiều nguồn route hoặc refresh thay đổi thứ tự | Đặt `order` tường minh và kiểm tra route đang hoạt động |

### Phân biệt 404 trước và sau định tuyến

Nếu client gọi `/not-api/orders/42`, không có route nào ở mục 3 khớp; gateway thường trả 404. Nếu client gọi `/api/orders/does-not-exist`, route `orders-general` vẫn khớp và gateway có thể chuyển tiếp request để backend trả 404. Hai trường hợp có cùng HTTP status nhưng vị trí lỗi khác nhau. Khi điều tra, cần đối chiếu **route ID, path mà backend nhận, status và trace ID**.

### Xem danh sách route thực tế

Trong môi trường phát triển, có thể bật Spring Boot Actuator và endpoint quản trị Gateway tương ứng với phiên bản đang chạy để kiểm tra route ID, predicates, filters, URI và `order`. Các endpoint quản trị phải được **giới hạn truy cập và bảo vệ**, không công khai Internet. Metrics (nếu bật gateway metrics và Micrometer) có thể gắn nhãn `routeId`, giúp theo dõi request nào đã đi vào từng route.

Với hệ thống dùng discovery/`lb://`, ghi nhận cả **service ID** và instance đích được chọn. Nhưng lưu ý: **lựa chọn route** và **lựa chọn instance** là hai quyết định khác nhau. `order` quyết định *route nào thắng*; LoadBalancer quyết định *instance nào nhận request* của route đó.

## 9. Những lưu ý quan trọng khi áp dụng trong production

### Ưu tiên route không phải cơ chế phân quyền

Trong ví dụ mục 4, `POST /api/orders/special/42` **không** khớp route `special-get` nhưng vẫn có thể đi qua `orders-general`. Nếu một route đặc biệt có filter xác thực mà route tổng quát không có, client có thể đi theo nhánh ngoài ý định. Hãy thiết kế authorization tại tầng phù hợp (chẳng hạn Spring Security và phân quyền ở backend), kiểm tra mọi method/path/host cần bảo vệ, và tránh phụ thuộc duy nhất vào việc “route đặc biệt sẽ thắng”.

### Tránh catch-all quá rộng

`Path=/**` hoặc `Path=/api/**` đặt ưu tiên cao có thể nuốt request dành cho các service khác hoặc endpoint quản trị. Ưu tiên rõ cho route chuyên biệt, ưu tiên thấp cho fallback, và giới hạn fallback theo host/method khi cần. Cũng cần nhớ fallback có thể khiến một path “lạ” được chuyển sang backend thay vì trả 404 sớm.

### Kết hợp với retry, circuit breaker và rate limiting

Chính sách retry, circuit breaker, giới hạn lưu lượng hoặc biến đổi header nằm trong filter chain hoặc tầng bảo mật tương ứng. Chúng chỉ áp dụng theo cách đã cấu hình. Nếu request chọn nhầm route, nó có thể gặp **chính sách resilience hoặc rate limit khác**. Khi thử nghiệm thay đổi `order`, hãy kiểm tra cả mã HTTP, số lần backend nhận request, header, latency và trace — đặc biệt với thao tác ghi dữ liệu không idempotent.

### TLS, forwarded headers và quan sát

TLS ở kết nối client → gateway và gateway → backend được cấu hình theo từng chặng; `order` không thay thế kiểm soát TLS. Nếu phía trước gateway có reverse proxy, xử lý `Host`, `Forwarded`, `X-Forwarded-*` theo chính sách tin cậy rõ ràng: thay đổi host có thể làm thay đổi kết quả của `Host` predicate. Khi vận hành, nên ghi **route ID được chọn**, method/path ban đầu, status, trace ID và thời gian xử lý, đồng thời tránh ghi access token hoặc dữ liệu nhạy cảm.

## 10. Bài tự luyện: tự dự đoán trước khi chạy

Với ba route đã khai báo ở mục 3, thử tự trả lời rồi kiểm chứng bằng `curl -i`:

1. Nếu đổi `order` của `api-fallback` từ `100` thành `-50`, `GET /api/orders/42` sẽ đi route nào? **Đáp án:** `api-fallback`, vì cả fallback và orders đều khớp nhưng `-50` được xét trước.
2. Nếu giữ `order` ban đầu nhưng gọi `PUT /api/orders/special/42`, route nào được chọn? **Đáp án:** `orders-general`; `Method=GET` của `special-get` không thỏa.
3. Nếu xóa `api-fallback` rồi gọi `GET /api/customers/42`, gateway sẽ ra sao? **Đáp án:** không route nào khớp; thường 404 nếu không có handler khác.
4. Nếu hai route đều có `order: 0`, có nên dựa vào thứ tự khai báo trong YAML để đảm bảo chọn đúng route hay không? **Đáp án:** không; hãy đặt thứ tự rõ ràng hoặc điều chỉnh predicate để các route không tranh cùng request.

**Ghi nhớ:** Trong Spring Cloud Gateway WebFlux, **route `order` thấp hơn được ưu tiên trước; route đầu tiên thỏa mọi predicate được chọn**. Sau đó gateway mới chạy filter chain của route ấy rồi xác định dịch vụ đích. Đặt ưu tiên tường minh cho các route chồng lấn, kiểm chứng bằng request thật và route ID, đồng thời thực thi bảo mật độc lập với quy tắc chọn tuyến.
