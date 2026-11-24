# SetPath: đặt đường dẫn bằng URI template

## 1. Bài toán: URL bên ngoài khác URL mà microservice cần

Trong chương **Đường dẫn và chuyển hướng** của **SPRING_CLOUD_GATEWAY**, ta đã biết gateway có thể nhận một URL công khai rồi chuyển tiếp request đến các microservice. Điều gì xảy ra khi đường dẫn client gọi khác với đường dẫn mà backend thực sự hỗ trợ?

Giả sử client cần API ổn định:

~~~http
GET /api/orders/42?include=items HTTP/1.1
Host: api.example.test
~~~

Nhưng dịch vụ đơn hàng chỉ triển khai endpoint `GET /internal/orders/42`. Ta muốn gateway đổi **đúng phần path** từ `/api/orders/42` thành `/internal/orders/42`, đồng thời giữ query `include=items` và chuyển tiếp request theo cơ chế proxy.

**`SetPath` GatewayFilter Factory** thực hiện chính xác việc này bằng **URI template**:

~~~yaml
predicates:
  - Path=/api/{resource}/{id}
filters:
  - SetPath=/internal/{resource}/{id}
~~~

Với request `/api/orders/42`, predicate trích xuất `resource=orders` và `id=42`; filter tạo path mới `/internal/orders/42`. Điểm quan trọng: đây là **thay đổi đường dẫn nội bộ trước khi forward đến backend**, không phải HTTP redirect yêu cầu trình duyệt gọi một URL mới.

Trong Spring Cloud Gateway, route predicate quyết định request có đi vào route hay không; filter chain xử lý path/header, khám phá dịch vụ, xác thực và chính sách như rate limiting, retry hoặc circuit breaker. Hiểu `SetPath` giúp bạn giữ hợp đồng API ổn định bên ngoài trong khi cấu trúc endpoint bên trong microservices thay đổi.

> **Phạm vi:** Bài tập trung vào **Spring Cloud Gateway Server WebFlux**, sử dụng `SetPath` trong cấu hình route. Tên property thay đổi giữa các phiên bản, nhưng ý nghĩa filter giữ nguyên. Server MVC có cơ chế tích hợp và cách viết Java DSL riêng.

## 2. SetPath hoạt động ở đâu trong luồng định tuyến?

Một route chứa `id`, `uri` đích, `predicates` và `filters`. Với WebFlux, `RoutePredicateHandlerMapping` tìm route phù hợp theo request, sau đó `FilteringWebHandler` chạy các gateway filter của route và các global filter liên quan. `SetPath` là **gateway filter**, nên được áp dụng **sau khi route đã khớp** và trước khi request được routing filter gửi đến backend.

~~~mermaid
flowchart TD
    C["Client<br/>GET /api/orders/42?include=items"] --> P{"Path predicate<br/>/api/{resource}/{id}"}
    P -->|"Khớp"| V["Biến template:<br/>resource=orders, id=42"]
    P -->|"Không khớp"| O["Gateway xét route khác"]
    V --> F["SetPath<br/>/internal/{resource}/{id}"]
    F --> R["Path mới:<br/>/internal/orders/42"]
    R --> U["Xác định URL đích<br/>theo uri của route"]
    U --> B["orders-service<br/>GET /internal/orders/42?include=items"]
    B --> S["Backend trả response"]
    S --> C
~~~

| Thời điểm | Giá trị của đường dẫn | Ý nghĩa |
| --- | --- | --- |
| Client gửi request | `/api/orders/42` | Giao diện API công khai |
| Predicate `Path` đánh giá | `/api/orders/42` | Route match và trích xuất biến `resource`, `id` |
| Filter `SetPath` chạy | `/internal/orders/42` | Đặt **toàn bộ path mới** bằng template đã mở rộng |
| Backend nhận request | `/internal/orders/42` | Endpoint thực tế của microservice |

Query string `?include=items` không phải một phần của path template và thông thường vẫn đi theo request sau khi `SetPath` đổi path. HTTP method, body và header cũng không bị `SetPath` chủ động thay đổi. Tuy nhiên, các filter khác hoặc HTTP proxy có thể tiếp tục sửa chúng; khi kiểm thử phải quan sát request tại backend thay vì chỉ suy luận từ YAML.

### Vì sao SetPath không đổi kết quả của Path predicate vừa dùng?

`Path=/api/{resource}/{id}` đã được dùng để **chọn route** trước khi filter chạy. Sau đó `SetPath` biến đổi request dành cho phần xử lý tiếp theo. Gateway không tự quay lại đánh giá toàn bộ predicate vì path đã thay đổi. Do vậy:

- Route khớp ở `/api/orders/42` dù backend sẽ thấy `/internal/orders/42`.
- Route chỉ có `Path=/internal/**` **không tự khớp** request ban đầu `/api/orders/42` chỉ nhờ `SetPath` ở route khác.
- Nếu không route nào khớp, `SetPath` của route ấy không chạy; gateway có thể trả 404 nếu không có handler khác.

## 3. Cú pháp URI template và các biến từ predicate

URI template là chuỗi có **placeholder trong dấu ngoặc nhọn**. Trong bài này:

~~~text
Đường dẫn khớp:  /api/{resource}/{id}
Đường dẫn mới:   /internal/{resource}/{id}

GET /api/orders/42
       resource = orders
                     id = 42

SetPath → /internal/orders/42
~~~

Các biến `resource` và `id` được lấy từ thông tin match của predicate như `Path`. WebFlux Gateway lưu các URI template variables trong `ServerWebExchange` để những filter như `SetPath` sử dụng. Bạn cũng có thể dùng nhiều phân đoạn template trong một route; **tên biến trong `SetPath` phải tương ứng với biến có sẵn từ predicate**.

| Request đầu vào | `Path` predicate | `SetPath` | Path backend |
| --- | --- | --- | --- |
| `/api/orders/42` | `/api/{resource}/{id}` | `/internal/{resource}/{id}` | `/internal/orders/42` |
| `/api/products/SKU-7` | `/api/{resource}/{id}` | `/internal/{resource}/{id}` | `/internal/products/SKU-7` |
| `/v1/users/17/profile` | `/v1/{domain}/{id}/profile` | `/private/{domain}/{id}/profile` | `/private/users/17/profile` |
| `/public/report/daily` | `/public/{kind}/{name}` | `/documents/{kind}/{name}` | `/documents/report/daily` |

### 3.1. Biến không tự sinh ra từ tên placeholder

Nếu cấu hình:

~~~yaml
predicates:
  - Path=/api/orders/**
filters:
  - SetPath=/internal/orders/{id}
~~~

thì `**` là wildcard dùng để match path, nhưng nó **không tự tạo biến tên `id`**. Filter không có giá trị `id` được ràng buộc hợp lệ để mở rộng template; tùy phiên bản và đường xử lý lỗi, request có thể thất bại khi filter chạy. Cách sửa là khai báo predicate thực sự trích xuất ID:

~~~yaml
predicates:
  - Path=/api/orders/{id}
filters:
  - SetPath=/internal/orders/{id}
~~~

Nếu cần chấp nhận một số cấu trúc path khác nhau, hãy thiết kế nhiều route, hoặc dùng `RewritePath` khi một biểu thức chính quy phù hợp với nhu cầu. Tránh giả định `SetPath` có thể tự đoán ID từ wildcard.

### 3.2. Giữ nguyên, đổi vị trí hoặc bỏ biến

Template đích không bắt buộc phải lặp lại cấu trúc đường dẫn ban đầu:

~~~yaml
# Client: /legacy/orders/42
# Backend: /v2/42/orders
predicates:
  - Path=/legacy/{type}/{id}
filters:
  - SetPath=/v2/{id}/{type}
~~~

`SetPath` có thể chèn phần path cố định (`/v2`), đổi thứ tự các biến (`{id}` trước `{type}`), hoặc bỏ một biến không cần thiết. Nó **đặt path bằng kết quả mở rộng template**, thay vì chỉ xóa prefix. Các quy tắc chi tiết về ký tự đặc biệt, encode/decode path và dấu gạch chéo cần được kiểm chứng với phiên bản Spring Framework, gateway, proxy phía trước và backend đang sử dụng.

### 3.3. Template không phải JSON, regex hay chuỗi tùy ý

- `{id}` là biến URI template; `SetPath` không tự parse body JSON để tìm `id`.
- `SetPath=/internal/{id}` **không phải regex** có nhóm bắt `(?<id>...)`.
- `SetPath` chỉ nhắm vào **path của request**; không đặt scheme/host/port như `uri: http://localhost:9091` và không tạo response redirect.
- Nếu cần thay cả query parameter, hãy dùng filter/query manipulation tương ứng. Đừng đặt `?foo=bar` trong đường dẫn rồi coi đó là một phần của path template.
- Với đường dẫn có dấu cách, `%2F`, Unicode hoặc dấu `;`, phải thử đầu-cuối; đừng tự nối chuỗi từ input thiếu kiểm soát để làm hệ thống định tuyến hoặc phân quyền nhạy cảm.

## 4. Cấu hình route hoàn chỉnh với SetPath

Giả sử gateway lắng nghe ở `localhost:8080` và microservice ở `localhost:9091`. Để thấy rõ filter, ta thêm header đánh dấu request/response; hai header này chỉ phục vụ kiểm tra.

### 4.1. Cấu hình cho Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: gateway-setpath-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: setpath-demo
              order: -10
              uri: http://localhost:9091
              predicates:
                - Path=/api/{resource}/{id}
                - Method=GET,POST
              filters:
                - SetPath=/internal/{resource}/{id}
                - SetRequestHeader=X-Gateway-Route, setpath-demo
                - AddResponseHeader=X-Path-Rule, setpath-demo
~~~

Với đường dẫn `/api/orders/42?include=items`, gateway chọn route `setpath-demo`, tạo path `/internal/orders/42`, thêm header `X-Gateway-Route` rồi forward theo URI backend đã khai báo. Khi backend trả response, gateway thêm response header `X-Path-Rule`.

**Thứ tự khai báo filter:** Ở bài lab, `SetPath` không xung đột với hai filter đặt header. Khi nhiều filter cùng sửa path như `StripPrefix`, `PrefixPath`, `RewritePath`, `SetPath`, kết quả phụ thuộc trình tự thực thi thực tế. Nên giữ một quy tắc biến đổi path rõ ràng trên mỗi route và kiểm tra bằng request thật.

### 4.2. Cấu hình cho Gateway Server WebFlux 4.2.x và 4.3.x

Tài liệu chính thức của WebFlux Gateway **4.2.x và 4.3.x** sử dụng `spring.cloud.gateway.routes`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: setpath-demo
          order: -10
          uri: http://localhost:9091
          predicates:
            - Path=/api/{resource}/{id}
            - Method=GET,POST
          filters:
            - SetPath=/internal/{resource}/{id}
            - SetRequestHeader=X-Gateway-Route, setpath-demo
            - AddResponseHeader=X-Path-Rule, setpath-demo
~~~

Chọn **một namespace** phù hợp với dependency/version dự án. Nếu dùng nhầm namespace, ứng dụng có thể khởi động nhưng route không được nạp, dẫn đến 404 dù YAML nhìn có vẻ hợp lý.

### 4.3. Dạng tham số đầy đủ của SetPath

Ngoài dạng rút gọn `SetPath=/internal/{resource}/{id}`, bạn có thể sử dụng tên filter và tham số rõ ràng:

~~~yaml
filters:
  - name: SetPath
    args:
      template: /internal/{resource}/{id}
~~~

Hai cách cùng biểu diễn filter có một tham số `template`. Dạng đầy đủ phù hợp khi cấu hình muốn thể hiện rõ cấu trúc hoặc thuận tiện cho công cụ sinh YAML. Mặc định, template được mở rộng bằng URI variables đã có trong exchange.

## 5. Thực hành: backend echo để thấy path sau SetPath

Một phép thử tốt là để backend trả lại **method, path, query, header và body** mà nó nhận được. Nhờ đó, ta xác minh kết quả `SetPath` tại đích thật, không chỉ quan sát response cuối cùng từ gateway.

Tạo một ứng dụng Spring Boot độc lập với dependency `spring-boot-starter-webflux`, có package `demo.echo`. Cấu hình `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: echo-service

server:
  port: 9091
~~~

Lớp khởi động `EchoApplication.java`:

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

Controller kiểm thử `EchoController.java`:

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    private Map<String, Object> describe(ServerHttpRequest request,
                                          String resource,
                                          String id) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethod().name());
        result.put("path", request.getPath().value());
        result.put("query", request.getURI().getRawQuery());
        result.put("resource", resource);
        result.put("id", id);
        result.put("gatewayRoute",
                request.getHeaders().getFirst("X-Gateway-Route"));
        return result;
    }

    @GetMapping("/internal/{resource}/{id}")
    public Map<String, Object> inspectGet(
            @PathVariable String resource,
            @PathVariable String id,
            ServerHttpRequest request) {
        return describe(request, resource, id);
    }

    @PostMapping("/internal/{resource}/{id}")
    public Mono<Map<String, Object>> inspectPost(
            @PathVariable String resource,
            @PathVariable String id,
            @RequestBody Mono<Map<String, Object>> payload,
            ServerHttpRequest request) {
        return payload.map(body -> {
            Map<String, Object> result = describe(request, resource, id);
            result.put("body", body);
            return result;
        });
    }
}
~~~

Ứng dụng backend này chấp nhận `GET` và `POST` ở path `/internal/{resource}/{id}`. Route ở gateway trích xuất hai biến từ đường dẫn **bên ngoài**, còn controller Spring trích xuất biến từ đường dẫn **đã được thay đổi**. Chúng có thể cùng giá trị nhưng ở hai tiến trình và hai request context riêng biệt.

Với dự án gateway sử dụng Spring Cloud Gateway **Server WebFlux starter** và Spring Cloud BOM tương thích với Spring Boot, thêm cấu hình mục 4 vào `application.yml`. Các release mới dùng starter thường tên `spring-cloud-starter-gateway-server-webflux`; ở bản trước là `spring-cloud-starter-gateway`. Tránh thêm Servlet MVC starter vào ứng dụng định xây Gateway WebFlux.

Khởi động hai ứng dụng trong các terminal riêng:

~~~bash
# Terminal 1: ở thư mục dự án echo backend
./mvnw spring-boot:run

# Terminal 2: ở thư mục dự án gateway
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng `mvnw.cmd spring-boot:run` hoặc Maven đã cài bằng `mvn spring-boot:run`. Các lệnh trên chỉ chạy được sau khi bạn đã tạo hai dự án Maven với dependencies phù hợp.

### 5.1. Kiểm chứng GET qua gateway

~~~bash
curl -i "http://localhost:8080/api/orders/42?include=items"
~~~

Kết quả **minh họa**, không phải response được đo từ hệ thống thật:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Path-Rule: setpath-demo

{"method":"GET","path":"/internal/orders/42","query":"include=items","resource":"orders","id":"42","gatewayRoute":"setpath-demo"}
~~~

Nếu thấy path là `/internal/orders/42` và header `gatewayRoute=setpath-demo`, ta có hai tín hiệu độc lập: route đã được chọn và biến đổi path đã đến backend. Trường `query` cho thấy `SetPath` không chủ ý xóa query.

### 5.2. Kiểm chứng POST body có được chuyển tiếp

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/42" \
  -H "Content-Type: application/json" \
  --data-binary '{"operation":"confirm","quantity":2}'
~~~

Response kỳ vọng có phần dữ liệu:

~~~json
{
  "method": "POST",
  "path": "/internal/orders/42",
  "query": null,
  "resource": "orders",
  "id": "42",
  "gatewayRoute": "setpath-demo",
  "body": {
    "operation": "confirm",
    "quantity": 2
  }
}
~~~

Trong bài lab này, filter `SetPath` chỉ đổi path; nó không tự đọc hay viết lại body. Response JSON do backend giải mã rồi tạo lại có thể khác khoảng trắng/thứ tự trường của payload ban đầu. Muốn đối chiếu **từng byte**, cần dùng backend checksum hoặc echo raw bytes riêng.

Nếu dùng Windows PowerShell, ưu tiên `curl.exe`; với JSON dài, có thể lưu file UTF-8 và gửi `--data-binary "@payload.json"` để tránh lỗi quoting.

### 5.3. So sánh với gọi backend trực tiếp

~~~bash
# Đường dẫn backend thực sự hỗ trợ
curl -i "http://localhost:9091/internal/orders/42?include=items"

# Đường dẫn công khai không tồn tại trên backend của lab
curl -i "http://localhost:9091/api/orders/42?include=items"
~~~

Lệnh đầu thường trả 200; lệnh sau thường trả 404. Qua gateway, client vẫn gọi `/api/orders/42` mà backend nhận `/internal/orders/42`. Tính chất này là điểm khác biệt cốt lõi của **path rewriting**.

### 5.4. Bảng smoke test

| Yêu cầu gọi gateway | Có khớp route? | Path được chuyển tiếp | Kết quả mong đợi |
| --- | --- | --- | --- |
| `GET /api/orders/42` | Có | `/internal/orders/42` | 200, JSON resource `orders`, id `42` |
| `GET /api/products/SKU-7?lang=vi` | Có | `/internal/products/SKU-7` | 200, query giữ `lang=vi` |
| `POST /api/orders/42` với JSON hợp lệ | Có | `/internal/orders/42` | 200 và JSON echo body |
| `GET /api/orders/42/extra` | Không, vì thừa phân đoạn | Không forward qua route lab | Thường 404 nếu không có route khác |
| `GET /api/orders` | Không, thiếu `{id}` | Không forward qua route lab | Thường 404 nếu không có route khác |
| `DELETE /api/orders/42` | Không, do `Method=GET,POST` | Không forward qua route lab | Thường 404 nếu không có handler khác |

Không nên mặc định request DELETE trong hàng cuối trả **405** ở gateway: predicate Method không khớp nên route này không được chọn. HTTP 405 có thể xuất hiện ở **backend** hoặc từ một handler khác đã được chọn nhưng không hỗ trợ method.

## 6. So sánh SetPath, StripPrefix, RewritePath và redirect

| Cơ chế | Cách hoạt động | Ví dụ | Khi nên dùng |
| --- | --- | --- | --- |
| **`SetPath`** | Thay toàn bộ path bằng **URI template** được mở rộng từ biến | `/api/{resource}/{id} → /internal/{resource}/{id}` | Đường dẫn mới có cấu trúc rõ ràng, dùng biến của predicate |
| **`StripPrefix`** | Bỏ một số phân đoạn đầu đường dẫn | `/api/orders/42 → /orders/42` với `StripPrefix=1` | Chỉ muốn xóa prefix cố định |
| **`PrefixPath`** | Thêm tiền tố vào path | `/orders/42 → /internal/orders/42` | Chỉ muốn thêm prefix cố định |
| **`RewritePath`** | Biến đổi path dựa trên **regular expression** và replacement | Bắt nhóm tên theo regex để thay phần linh hoạt | Quy tắc khó biểu diễn bằng URI template đơn giản |
| **`RedirectTo`** | Gateway trả response **3xx** và `Location` cho client | Chuyển client tới URL khác | Cần client thực hiện request mới, chẳng hạn đổi URL công khai |

**Ví dụ phân biệt:** nếu client gọi `GET /api/orders/42`:

- `SetPath=/internal/orders/42`: gateway tự gọi backend theo path mới. Client nhìn thấy response backend và thường **không thấy HTTP 3xx** chỉ vì SetPath.
- `RedirectTo=302, https://new.example.test/orders/42`: gateway trả **302** với `Location`; client có quyền tự quyết có đi theo redirect hay không. Lệnh `curl -i` thông thường chỉ hiển thị response 302, còn `curl -L` sẽ cố đi tiếp.

Vì vậy, **SetPath không phải cơ chế redirect** dù thuộc cùng nhóm học về biến đổi đường dẫn và chuyển hướng.

### Khi nào SetPath không phù hợp?

- Bạn chỉ muốn bỏ `/api` trên mọi URL nhưng không biết trước số phân đoạn còn lại: `StripPrefix=1` thường đơn giản hơn.
- Bạn cần thay path theo regex có nhóm bắt phức tạp: dùng `RewritePath` và kiểm tra cú pháp escape của YAML.
- Bạn muốn chuyển người dùng tới domain hoặc trang công khai mới: dùng HTTP redirect thích hợp.
- Bạn muốn thay host, scheme, query hoặc body: cần cấu hình riêng cho các thành phần ấy.

## 7. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Client luôn nhận 404, không có log backend | Không route nào khớp hoặc cấu hình route chưa được nạp | Kiểm tra `Path`, `Method` và namespace cấu hình |
| `SetPath` thất bại với placeholder | Biến không có trong URI template variables, ví dụ dùng `{id}` nhưng predicate chỉ có `**` | Đảm bảo tên biến trong `SetPath` khớp `Path`/predicate có capture |
| Backend nhận path ban đầu | Filter chưa chạy hoặc một route khác được chọn | Xác minh route ID, header `X-Path-Rule` và request backend |
| Backend nhận path bị sửa hai lần | Có thêm `StripPrefix`, `PrefixPath`, `RewritePath` hoặc filter tự viết | Rà soát filter chain và order; đơn giản hóa biến đổi path |
| Client nhận 404 nhưng backend có log | Route khớp, `SetPath` tạo path mà backend không hỗ trợ | Đối chiếu URI sau SetPath với mapping của controller |
| Query thiếu hoặc thay đổi | Filter khác thay query hoặc reverse proxy phía trước | So sánh request đầu vào, URL định tuyến và request backend |
| POST body rỗng sau khi đổi path | Custom filter hoặc xử lý body khác đã tiêu thụ `Flux<DataBuffer>` | Kiểm tra body modifier/decorator; SetPath tự nó không cần đọc body |
| Response có 401/403/429 | Security hoặc rate limiter chặn request | Kiểm tra policy và vị trí filter; đây không phải status SetPath mặc định |
| Cấu hình `lb://service-id` trả 503 | LoadBalancer không tìm được instance cho service | Kiểm tra registry, discovery, service ID và instance |

### 7.1. Cẩn thận với biến path và bảo mật

Không nên mặc định URI template variable là dữ liệu đã được xác thực. Client kiểm soát đường dẫn đầu vào; nếu backend có endpoint quản trị hoặc đường dẫn đặc quyền, việc thay path bằng một template quá rộng có thể khiến request tới nơi ngoài dự kiến.

Ví dụ, nếu chỉ kiểm tra `Path=/api/{resource}/{id}` mà cho phép mọi `resource`, client có thể chọn nhiều giá trị khác nhau. Đối với hệ thống thật, cần giới hạn tập `resource` hợp lệ, tách route theo API cụ thể khi cần, và giữ **authorization ở gateway/backend** theo tài nguyên thực tế. Không để một route tổng quát vô tình bypass filter security của route cụ thể.

Với các path chứa `%2F` (slash đã encode), `..`, Unicode hoặc ký tự đặc biệt, hãy kiểm tra hành vi decode/normalize ở **ingress, WebFlux/Gateway và backend**. Sự khác nhau giữa các lớp có thể khiến path dùng để phân quyền khác với path backend cuối cùng xử lý. SetPath không thay thế validation hay normalization an toàn.

### 7.2. Order của route và filter là hai khái niệm riêng

Khi có hai route cùng khớp, route `order` **nhỏ hơn** thường được xét trước và route khớp đầu tiên được chọn. `SetPath` chỉ chạy nếu route chứa nó được chọn. Sau đó, filter order quyết định thứ tự thực thi các filter trên route đó.

Ví dụ `GET /api/orders/42` vừa khớp route cụ thể `Path=/api/orders/{id}`, vừa khớp route rộng `Path=/api/**`. Nếu route rộng thắng, `SetPath` gắn với route cụ thể không chạy. Dùng route ID, metrics hoặc header đánh dấu trong môi trường lab để xác minh route thực tế.

### 7.3. Path đổi nhưng query, header, body thì sao?

**Chỉ có `SetPath`** thì mục đích của filter là đặt đường dẫn request. Tuy nhiên, Spring Cloud Gateway hoạt động như HTTP proxy với nhiều filter khác; do đó:

- Header như `Host`, `Connection`, `Transfer-Encoding` có thể được xử lý theo từng hop; không nên giả định mọi header từ client đều được giữ nguyên byte-for-byte.
- `Forwarded` và `X-Forwarded-*` cần được xác minh ở proxy tin cậy, nhất là khi TLS kết thúc trước gateway.
- `Query parameter` vẫn có thể được các filter query rewrite/add/remove thay đổi.
- `Body` có thể bị can thiệp bởi filter thay request body hoặc retry; cần cân nhắc tính idempotent, dung lượng, backpressure và lưu trữ body.

Các trường hợp này không phải do SetPath mặc định gây ra, nhưng thường xuất hiện cùng lúc trong hệ thống microservices.

## 8. Ứng dụng SetPath với discovery và khả năng vận hành

Để thay URI tĩnh bằng service discovery:

~~~yaml
routes:
  - id: orders-service-api
    uri: lb://orders-service
    predicates:
      - Path=/api/orders/{id}
    filters:
      - SetPath=/internal/orders/{id}
~~~

Đoạn trên là **phần danh sách `routes`**; đặt nó dưới đúng namespace của phiên bản Gateway WebFlux. URI `lb://orders-service` yêu cầu Spring Cloud LoadBalancer và một nguồn cung cấp danh sách instance phù hợp. `SetPath` vẫn đổi request path; LoadBalancer chọn instance backend, còn routing filter mới gửi HTTP request.

Khi đi vào production, kết hợp biến đổi path với:

1. **Xác thực và phân quyền:** kiểm tra route công khai, endpoint nội bộ và quyền truy cập tài nguyên. SetPath không tự xác thực token hay cấp quyền.
2. **Giới hạn lưu lượng:** xem khóa rate limit theo người dùng/API key/IP đáng tin, tránh để route chồng lấn gây áp sai chính sách.
3. **Circuit breaker, retry và timeout:** theo dõi số lần backend nhận một request; retry trên POST tạo đơn hoặc thanh toán cần xem xét idempotency và khả năng đọc lại body.
4. **TLS:** xác minh kết nối HTTPS client → gateway và gateway → service theo thiết kế; SetPath không bật HTTPS hoặc xác minh certificate.
5. **Observability:** log/metric/trace nên phân biệt **path client gọi**, **route ID**, **path/URL đã biến đổi**, **instance đích**, status và latency. Tránh log access token hoặc body có thông tin nhạy cảm.

### Đoạn kiểm tra nhanh khi triển khai

~~~bash
# Route dự kiến và query giữ nguyên
curl -i "http://localhost:8080/api/orders/42?include=items"

# Một resource khác cùng URI template
curl -i "http://localhost:8080/api/products/SKU-7?lang=vi"

# Path thiếu biến: cần thấy route không khớp
curl -i "http://localhost:8080/api/orders"

# Method không được route hỗ trợ
curl -i -X DELETE "http://localhost:8080/api/orders/42"
~~~

Với hệ thống thử nghiệm ở mục 4–5, hai request đầu đến backend theo `/internal/...`; hai request sau không khớp route lab. Khi deployment có các route khác, status và đích cuối cùng phụ thuộc những route/handler còn lại.

## 9. Câu hỏi tự kiểm tra

**1. Client gọi `/api/customers/7`, `Path=/api/{resource}/{id}` và `SetPath=/v2/{id}/{resource}`. Backend nhận path nào?**

Đáp án: `/v2/7/customers`. Thứ tự placeholder trong template đích quyết định cấu trúc mới.

**2. Nếu predicate là `Path=/api/orders/**`, filter `SetPath=/orders/{id}` có lấy được `id` không?**

Không thể dựa vào wildcard `**` để có biến mang tên `id`. Cần một predicate trích xuất `{id}` hoặc thiết kế lại filter phù hợp.

**3. Vì sao SetPath không tự làm client nhận 301/302?**

Vì SetPath sửa request được gateway chuyển tiếp xuống backend trong cùng một lượt HTTP. Redirect là response 3xx với `Location` do gateway hoặc backend trả để client quyết định có thực hiện một request mới hay không.

**4. Nếu backend trả 404 sau SetPath, đó có phải chắc chắn lỗi chọn route?**

Không. Route có thể đã khớp nhưng path mới không có controller tương ứng. Kiểm tra log backend, route ID và path sau biến đổi để xác định vị trí lỗi.

**5. Khi chuyển từ URI tĩnh sang `lb://orders-service`, SetPath có còn tác dụng không?**

Có. SetPath vẫn xác định path gửi xuống service; discovery/LoadBalancer là bước chọn instance đích. Chúng giải quyết hai vấn đề độc lập.

## 10. Tài liệu đối chiếu phiên bản

- [Spring Cloud Gateway Server WebFlux — SetPath GatewayFilter Factory (5.x)](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setpath-factory.html)
- [Spring Cloud Gateway Server WebFlux — SetPath GatewayFilter Factory (4.3.x)](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setpath-factory.html)
- [Spring Cloud Gateway — SetPath GatewayFilter Factory (4.2.x)](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/gatewayfilter-factories/setpath-factory.html)

**Ghi nhớ:** `SetPath` đặt **toàn bộ request path** theo URI template sau khi route predicate đã khớp. Biến trong template phải được predicate cung cấp; query, method, header và body không phải mục tiêu trực tiếp của filter. Khi triển khai Spring Cloud Gateway, hãy kiểm tra path **thực tế tại backend**, giữ ranh giới bảo mật ở cả gateway và service, và phân biệt rõ path rewriting nội bộ với HTTP redirect.
