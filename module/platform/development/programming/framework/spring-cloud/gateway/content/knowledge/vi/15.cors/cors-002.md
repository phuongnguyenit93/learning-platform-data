# Yêu cầu đơn giản so với preflight OPTIONS

## 1. CORS giải quyết vấn đề gì tại API Gateway?

Giả sử một trang web chạy tại `http://localhost:5173` gọi API qua **Spring Cloud Gateway Server WebFlux** tại `http://localhost:8080`:

~~~javascript
const response = await fetch("http://localhost:8080/api/orders/42");
const order = await response.json();
~~~

Hai địa chỉ có cùng hostname nhưng **khác cổng** nên là **khác origin**. Trình duyệt áp dụng **Cross-Origin Resource Sharing (CORS)** để quyết định mã JavaScript từ origin trang web có được **đọc response** của origin API hay không. Gateway là điểm vào của microservices, vì thế nó thường là nơi phù hợp để công bố chính sách CORS cho các API công khai.

Bài thuộc chương **CORS** của module **SPRING_CLOUD_GATEWAY**. Sau khi phân biệt request không cần preflight với request phải gửi `OPTIONS` trước, bạn sẽ hiểu tại sao một API có route predicate, filter chain, path rewriting, header transformation và service discovery đúng nhưng frontend vẫn báo “blocked by CORS policy”. Chủ đề cũng liên hệ đến xác thực, rate limiting, circuit breaker, retry, TLS và observability: những chính sách này phải phối hợp với CORS, không để preflight bị xử lý nhầm như một request nghiệp vụ.

Mục tiêu của bài:

1. Hiểu **origin** và ranh giới thực thi CORS.
2. Biết chính xác điều kiện để một request cross-origin **không cần preflight** (thường gọi là *simple request*).
3. Đọc được luồng `OPTIONS` với `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
4. Cấu hình Global CORS trong Spring Cloud Gateway **Server WebFlux** 4.2/4.3 và 5.x.
5. Kiểm thử GET đơn giản, POST JSON, request có header tùy biến, origin bị từ chối và lỗi OPTIONS không khớp route.
6. Tránh những lỗi CORS thường gặp khi kết hợp Spring Security, cookie/session, proxy và cache.

> **Phạm vi:** Đây là bài về **CORS trong trình duyệt và Gateway Server WebFlux**. Gateway Server MVC có namespace và cơ chế tích hợp khác. Các đoạn cấu hình cần dùng cùng Spring Boot/Spring Cloud BOM tương thích với phiên bản đang chạy.

## 2. Origin là gì và CORS có áp dụng cho mọi HTTP client không?

Một origin được xác định bởi bộ ba **scheme + hostname + port**. Ví dụ, với trang web `https://app.example.test`:

| URL API | So với origin trang web | Lý do |
| --- | --- | --- |
| `https://app.example.test/api/orders` | Cùng origin | Scheme, host và port mặc định đều khớp |
| `https://api.example.test/orders` | Khác origin | Host khác |
| `http://app.example.test/orders` | Khác origin | Scheme khác |
| `https://app.example.test:8443/orders` | Khác origin | Port khác |
| `https://app.example.test:443/orders` | Cùng origin | Cổng 443 là cổng HTTPS mặc định |

**CORS là cơ chế do trình duyệt thực thi.** Gateway và backend phản hồi các header CORS; trình duyệt đánh giá chúng trước khi cho mã JavaScript truy cập response. Các client như `curl`, Postman hoặc service-to-service HTTP client thường **không tự chặn** response theo CORS. Một lệnh `curl` trả 200 không chứng minh trình duyệt sẽ cho frontend đọc response.

**CORS không phải xác thực hay phân quyền.** Bất kỳ HTTP client ngoài trình duyệt vẫn có thể gọi API nếu mạng và cơ chế security cho phép. Không được dùng `Access-Control-Allow-Origin` làm danh sách người dùng được phép truy cập dữ liệu. Với request “simple”, trình duyệt có thể **gửi request thật tới server trước** rồi mới chặn JavaScript đọc response; vì thế CORS cũng không thay thế CSRF protection.

### Site khác origin

`https://app.example.test` và `https://api.example.test` khác origin, nhưng có thể cùng *site* theo quy tắc cookie SameSite. CORS kiểm soát **truy cập response xuyên origin**; SameSite kiểm soát **ngữ cảnh gửi cookie**. Hai khái niệm liên quan nhưng không hoán đổi cho nhau.

## 3. Thế nào là một simple request?

Tên “simple request” là thuật ngữ lịch sử thường dùng cho một **CORS request không cần preflight**. Request phải thỏa **tất cả** những điều kiện liên quan của chuẩn Fetch/CORS, chứ không chỉ có method GET hay POST.

### 3.1. Method thuộc danh sách được phép

Chỉ các method sau thuộc nhóm CORS-safelisted:

- `GET`
- `HEAD`
- `POST`

`PUT`, `PATCH`, `DELETE` và nhiều method khác **không** thuộc nhóm này nên một lời gọi cross-origin của browser thường cần preflight.

### 3.2. Header do mã ứng dụng đặt phải safelisted

Những request header thường có thể được mã ứng dụng đặt mà không tự gây preflight, **nếu giá trị cũng thỏa các giới hạn của chuẩn**, gồm:

| Header | Lưu ý |
| --- | --- |
| `Accept` | Giá trị phải đáp ứng giới hạn ký tự và độ dài |
| `Accept-Language` | Giá trị phải đáp ứng bộ ký tự cho phép |
| `Content-Language` | Cùng hạn chế như `Accept-Language` |
| `Content-Type` | Chỉ một số media type safelisted, xem dưới |
| `Range` | Chỉ một single byte range có định dạng hợp lệ |

Các header do browser tự điều khiển, ví dụ `Origin` và một số header kết nối, không được hiểu là “bạn đã thêm custom header” để suy ra preflight. Ngược lại, việc mã ứng dụng đặt `Authorization: Bearer ...`, `X-Request-Id` hoặc `X-Api-Key` thường khiến browser **phải preflight**.

Một số điều kiện giá trị như ký tự bị cấm, giới hạn độ dài header, quy tắc `Range` và hành vi riêng của Safari có thể làm request không còn safelisted dù **tên header** nằm trong danh sách. Vì vậy, bảng trên là quy tắc cơ bản, không phải giấy phép cho mọi giá trị.

### 3.3. POST chỉ được dùng những Content-Type nào?

Khi `Content-Type` do request sử dụng thuộc nhóm safelisted, media type phải là một trong:

~~~text
application/x-www-form-urlencoded
multipart/form-data
text/plain
~~~

Tham số media type (ví dụ `charset=utf-8`, boundary trong form) không tự làm media type đổi nhóm, nhưng các giới hạn về giá trị header vẫn áp dụng.

**`Content-Type: application/json` không safelisted.** Do đó một `POST` JSON cross-origin từ `fetch` thường gây preflight, dù POST là method safelisted.

### 3.4. Các điều kiện khác

Đối với `XMLHttpRequest`, listener trên `xhr.upload` có thể làm request không thuộc nhóm simple. Sử dụng `ReadableStream` như body cũng có thể kích hoạt preflight. Để xét chính xác ở những trường hợp hiếm, tham khảo tài liệu Fetch/CORS của trình duyệt đang sử dụng; không chỉ dùng mẹo “POST + text/plain chắc chắn simple”.

### Bảng phân loại nhanh

| Request cross-origin do browser tạo | Có cần preflight? | Vì sao |
| --- | --- | --- |
| `GET /api/orders/42` chỉ có header safelisted | **Thường không** | Method và headers safelisted |
| `HEAD /api/orders/42` | **Thường không** | HEAD safelisted |
| `POST` với `Content-Type: application/x-www-form-urlencoded`, không custom header | **Thường không** | POST và media type safelisted |
| `POST` với `Content-Type: text/plain` | **Thường không** | Media type safelisted, nếu các điều kiện khác cũng đạt |
| `POST` với `Content-Type: application/json` | **Có** | JSON không thuộc nhóm safelisted |
| `GET` có `Authorization: Bearer ...` | **Có** | Header Authorization không safelisted |
| `GET` có `X-Request-Id` tự đặt | **Có** | Header tùy biến |
| `PUT`, `PATCH` hoặc `DELETE` | **Có** | Method không safelisted |

> **Không nhầm:** Một POST dùng JSON **cùng origin** không cần CORS preflight vì không phải yêu cầu CORS cross-origin. Các quy tắc trên áp dụng khi trình duyệt thực hiện request thuộc phạm vi CORS, không áp dụng đồng loạt cho mọi HTTP request.

## 4. Luồng simple request: gửi thật rồi mới kiểm tra response

Một request cross-origin đơn giản có thể diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant P as Browser (http://localhost:5173)
    participant G as Gateway (http://localhost:8080)
    participant B as orders-service
    P->>G: GET /api/orders/42<br/>Origin: http://localhost:5173
    G->>B: GET /orders/42
    B-->>G: 200 + JSON
    G-->>P: 200 + JSON<br/>Access-Control-Allow-Origin: http://localhost:5173
    Note over P: CORS hợp lệ → JavaScript đọc response
~~~

Đặc điểm:

1. Browser gửi **request thật ngay**, không gửi `OPTIONS` trước.
2. Browser kèm `Origin` để server/Gateway có thể đánh giá.
3. Gateway có thể xử lý định tuyến/filter bình thường, backend thực sự nhận request.
4. Browser kiểm tra response, đặc biệt `Access-Control-Allow-Origin`. Nếu không được phép, mã JavaScript **không đọc được response**, nhưng request có thể **đã gây tác dụng phụ tại backend**.

Ví dụ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Accept: application/json
~~~

Response minh họa hợp lệ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Vary: Origin
Content-Type: application/json

{"id":"42","state":"READY"}
~~~

Nếu response thiếu header CORS cần thiết hoặc trả origin khác, browser vẫn có thể nhận **HTTP 200 ở tầng mạng** nhưng từ chối cho JavaScript đọc body. Điều này giải thích trường hợp DevTools thấy request 200 trong Network trong khi console báo CORS error.

## 5. Luồng preflight: browser hỏi trước bằng OPTIONS

Đối với request không simple (chẳng hạn POST JSON hoặc có custom header), browser gửi một HTTP **`OPTIONS` preflight** tới URL đích để hỏi server có cho phép **method và headers của request thật** hay không.

~~~mermaid
sequenceDiagram
    participant P as Browser
    participant G as Gateway WebFlux
    participant B as orders-service
    P->>G: OPTIONS /api/orders/42<br/>Origin: http://localhost:5173<br/>Access-Control-Request-Method: POST<br/>Access-Control-Request-Headers: content-type,x-request-id
    G-->>P: 200/204 + CORS allow headers
    Note over P: Preflight hợp lệ → mới gửi request thật
    P->>G: POST /api/orders/42<br/>Content-Type: application/json<br/>X-Request-Id: lab-42
    G->>B: POST /orders/42 + JSON
    B-->>G: 200 + JSON
    G-->>P: 200 + Access-Control-Allow-Origin
    Note over P: Kiểm tra CORS response thật trước khi cho JS đọc
~~~

### 5.1. Request OPTIONS trông như thế nào?

~~~http
OPTIONS /api/orders/42 HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

Ba trường cốt lõi:

- `Origin`: origin của trang đang gọi.
- `Access-Control-Request-Method`: method của **request thật** mà browser muốn gửi, ở đây `POST`; method của **preflight** vẫn là `OPTIONS`.
- `Access-Control-Request-Headers`: danh sách tên request header không safelisted mà browser dự kiến gửi trong request thật; có thể không có nếu preflight chỉ do method.

**Preflight không mang body nghiệp vụ** và theo chuẩn **không gửi credentials như cookie phiên**. Vì vậy, không được buộc preflight phải có session cookie/token giống request thật.

### 5.2. Response preflight hợp lệ cần gì?

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Status có thể là **200** hoặc **204**, tùy framework và cấu hình. Quan trọng là thành công theo giao thức và các header CORS cho phép origin, method và headers tương ứng. Preflight thành công **chưa phải** thành công của POST thật: browser sau đó còn phải gửi request thật, rồi kiểm tra CORS trên response thật.

`Access-Control-Max-Age` cho browser biết có thể **cache kết quả preflight** trong bao lâu (giây). Browser có thể giới hạn giá trị này bằng chính sách nội bộ; preflight cache **khác** HTTP response cache thông thường. Vì thế, không có OPTIONS trước **mọi lần** POST JSON là điều bình thường: browser có thể dùng lại kết quả preflight còn hạn.

### 5.3. Phân biệt một OPTIONS bất kỳ với CORS preflight

HTTP `OPTIONS` không tự động có nghĩa là CORS preflight. Một preflight hợp lệ thường được nhận diện nhờ `Origin` **và** `Access-Control-Request-Method`. Nếu gọi:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42"
~~~

thì đây là một OPTIONS thông thường, **không phải** phép mô phỏng preflight đầy đủ. Phải gửi đủ header mới kiểm tra được chính sách CORS.

## 6. Các header CORS quan trọng phải đọc đúng

| Header | Xuất hiện ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `Origin` | Request thật và preflight | Origin mà browser đang truy cập |
| `Access-Control-Request-Method` | Preflight request | Method của request thật |
| `Access-Control-Request-Headers` | Preflight request | Tên header mà request thật muốn sử dụng |
| `Access-Control-Allow-Origin` | Response preflight **và** response thật | Origin được phép đọc response |
| `Access-Control-Allow-Methods` | Chủ yếu response preflight | Các method server cho phép trong CORS |
| `Access-Control-Allow-Headers` | Chủ yếu response preflight | Các header request được chấp nhận |
| `Access-Control-Allow-Credentials` | Response khi hỗ trợ credentials | Cho phép browser chia sẻ response có credentials theo quy tắc CORS |
| `Access-Control-Expose-Headers` | Response thật | Những response header ngoài safelist mà JavaScript được đọc |
| `Access-Control-Max-Age` | Response preflight | Thời gian cache kết quả preflight |
| `Vary` | Response được cache | Phân biệt response theo origin/method/headers yêu cầu khi cần |

### 6.1. Access-Control-Expose-Headers không cấp quyền gửi header

`Access-Control-Allow-Headers` cho phép **request headers** mà frontend muốn gửi, ví dụ `Authorization` hoặc `X-Request-Id`. Trong khi đó, `Access-Control-Expose-Headers` cho phép JavaScript **đọc response headers** như `X-Gateway-Route` hay `X-Trace-Id`. Hai header không thể thay nhau.

Ví dụ browser thường không đọc được header `X-Gateway-Route` từ `response.headers.get("X-Gateway-Route")` nếu response không khai báo expose tương ứng; dù header đó có thể thấy trong DevTools Network.

### 6.2. Credentials và wildcard

Với cookie/session hoặc request dùng chế độ credentials:

- Frontend có thể cần `fetch(..., { credentials: "include" })`.
- CORS response cần `Access-Control-Allow-Credentials: true` nếu muốn browser cho truy cập response credentialed.
- **Không được** dùng `Access-Control-Allow-Origin: *` cho response credentialed; cần phản hồi **origin cụ thể** thuộc allowlist.
- Chính sách cookie `SameSite`/`Secure`, third-party cookie restriction và CSRF vẫn áp dụng độc lập với CORS.

Không nên bật `allowCredentials: true` cho tất cả API chỉ để “hết lỗi CORS”. Với API dùng bearer token hoặc API key, xác định cách cấp/đính kèm credentials và policy thực tế trước khi chọn allowCredentials.

### 6.3. Origin null và cấu hình wildcard

Một số ngữ cảnh như `file://` hoặc tài liệu sandbox có thể tạo `Origin: null`. Không tùy tiện thêm `null` vào allowlist cho API nhạy cảm. Wildcard `*` chỉ phù hợp một số API công khai không dùng credentials và không có dữ liệu truy cập riêng; nó **không phải** phương án mặc định an toàn cho mọi Gateway.

## 7. Global CORS của Spring Cloud Gateway Server WebFlux

Spring Cloud Gateway hỗ trợ **global CORS configuration** và **CORS metadata theo route**, dựa trên `CorsConfiguration` của Spring Framework. Với Gateway đứng trước nhiều microservice, nên thiết kế **một nguồn chính sách CORS rõ ràng** để tránh Gateway và backend cùng ghi header xung đột.

### 7.1. Ví dụ cấu hình Gateway Server WebFlux 5.x

Giả sử frontend chạy ở `http://localhost:5173`, Gateway tại `localhost:8080`, backend tại `localhost:9091`. Cấu hình `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: cors-gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          globalcors:
            add-to-simple-url-handler-mapping: true
            cors-configurations:
              '[/api/orders/**]':
                allowedOrigins:
                  - http://localhost:5173
                allowedMethods:
                  - GET
                  - POST
                allowedHeaders:
                  - Content-Type
                  - X-Request-Id
                  - Authorization
                exposedHeaders:
                  - X-Gateway-Route
                allowCredentials: false
                maxAge: 600

          routes:
            - id: orders-route
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Gateway-Route, orders-route
~~~

Ý nghĩa:

- `globalcors.cors-configurations` định nghĩa chính sách CORS theo **path công khai** mà browser gọi, ở đây `/api/orders/**`.
- `allowedOrigins` cho phép **chính xác** `http://localhost:5173`. `https://localhost:5173` hay `http://localhost:3000` là origin **khác**.
- `allowedMethods` cho phép browser xin gửi GET/POST; **không cần thêm `OPTIONS` vào danh sách chỉ để preflight kiểm tra POST**.
- `allowedHeaders` cho phép `Content-Type`, `X-Request-Id` và `Authorization` được yêu cầu qua preflight; đó không phải là cấp quyền truy cập backend.
- `exposedHeaders` cho phép JavaScript đọc `X-Gateway-Route` từ response thật.
- `allowCredentials: false` phù hợp lab này vì không dùng cookie/session; có thể cần thiết kế khác với ứng dụng đăng nhập.
- `maxAge: 600` đề xuất browser cache preflight trong 600 giây, tùy browser.
- `StripPrefix=1` khiến backend nhận `/orders/42`; CORS vẫn được đánh giá trên request bên ngoài `/api/orders/42`.

### 7.2. Tại sao cần add-to-simple-url-handler-mapping?

Route trên có predicate:

~~~yaml
predicates:
  - Path=/api/orders/**
  - Method=GET,POST
~~~

Một browser preflight sẽ gửi method HTTP **`OPTIONS`**, không phải GET/POST. Vì `Method=GET,POST` **không khớp**, request preflight có thể không đi vào route handler thông thường và không tìm được CORS config của route đó.

Spring Cloud Gateway cung cấp:

~~~yaml
globalcors:
  add-to-simple-url-handler-mapping: true
~~~

để cùng global CORS configuration cũng được cung cấp cho một **simple URL handler mapping** khác trong WebFlux, hữu ích khi preflight **không khớp route predicate**. Đây là tên thành phần `SimpleUrlHandlerMapping` trong framework, **không liên quan khái niệm “simple request”** của CORS dù có chữ “simple” giống nhau.

Property này mặc định là `false` trong các bản được tham khảo. Khi bật, preflight phù hợp có thể được xử lý ở tầng Gateway/WebFlux mà **không cần gửi một OPTIONS nghiệp vụ xuống backend**.

> **Không phải mẹo mở toàn bộ OPTIONS:** Vẫn phải giới hạn allowed origins/methods/headers và path. Khi dùng Spring Security, cần xác nhận lớp security không chặn preflight trước CORS handler.

### 7.3. Tương đương Gateway WebFlux 4.2.x / 4.3.x

Tài liệu chính thức WebFlux 4.2 và 4.3 dùng namespace `spring.cloud.gateway.globalcors` và `spring.cloud.gateway.routes`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/api/orders/**]':
            allowedOrigins:
              - http://localhost:5173
            allowedMethods:
              - GET
              - POST
            allowedHeaders:
              - Content-Type
              - X-Request-Id
              - Authorization
            exposedHeaders:
              - X-Gateway-Route
            allowCredentials: false
            maxAge: 600
      routes:
        - id: orders-route
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
            - Method=GET,POST
          filters:
            - StripPrefix=1
            - AddResponseHeader=X-Gateway-Route, orders-route
~~~

Không định nghĩa trùng routes hoặc globalcors ở cả hai namespace. **Chọn đúng phiên bản** và xác minh cấu hình thực tế đã được Gateway nạp. Nếu dùng Gateway Server MVC, không sao chép cấu hình WebFlux sang MVC.

## 8. CORS theo từng route và cách tránh cấu hình xung đột

Nếu API có nhiều nhóm frontend hoặc policy khác nhau, Gateway hỗ trợ CORS qua metadata của route:

~~~yaml
# Đoạn này đặt bên trong một phần tử của routes:
id: public-report
uri: http://localhost:9091
predicates:
  - Path=/api/reports/**
metadata:
  cors:
    allowedOrigins:
      - https://reports.example.test
    allowedMethods:
      - GET
    allowedHeaders:
      - Accept
    maxAge: 300
~~~

Đặt đoạn route trên dưới namespace `routes` phù hợp version. Metadata CORS gắn với route được chọn. Với route có predicate method quá hẹp khiến OPTIONS không chọn route, **global CORS với add-to-simple-url-handler-mapping** thường là phương án dễ kiểm tra cho preflight.

Nên quyết định rõ policy nào do **Gateway** quản lý và policy nào do **backend** quản lý. Nếu cả hai cùng ghi `Access-Control-Allow-Origin` hoặc `Access-Control-Allow-Credentials`, response có thể chứa **header trùng lặp/xung đột** khiến browser từ chối, dù backend trả 200.

Spring Cloud Gateway có `DedupeResponseHeader`, có thể xử lý một số header CORS bị thêm trùng. Tuy nhiên, **dedupe không giải quyết bất đồng chính sách**: nếu Gateway cho origin A còn backend cho origin B, hãy sửa cấu hình hai bên; không chỉ dựa vào loại trùng lặp để bỏ qua sự khác biệt.

## 9. Bài lab: backend WebFlux có endpoint GET và POST

Tạo một Spring Boot ứng dụng backend ở `localhost:9091` với dependency `spring-boot-starter-webflux`. Backend chỉ trả JSON để giúp bạn biết **request thật** đã tới nơi. Không thêm CORS config vào backend trong lab này để Gateway là nơi duy nhất phát chính sách CORS.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091
~~~

`src/main/java/demo/orders/OrdersApplication.java`:

~~~java
package demo.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`src/main/java/demo/orders/OrdersController.java`:

~~~java
package demo.orders;

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
public class OrdersController {

    @GetMapping("/orders/{id}")
    public Map<String, Object> getOrder(
            @PathVariable String id,
            ServerHttpRequest request) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", "GET");
        result.put("id", id);
        result.put("path", request.getPath().value());
        return result;
    }

    @PostMapping("/orders/{id}")
    public Mono<Map<String, Object>> updateOrder(
            @PathVariable String id,
            @RequestBody Mono<Map<String, Object>> body,
            ServerHttpRequest request) {
        return body.map(payload -> {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("method", "POST");
            result.put("id", id);
            result.put("path", request.getPath().value());
            result.put("requestId",
                    request.getHeaders().getFirst("X-Request-Id"));
            result.put("body", payload);
            return result;
        });
    }
}
~~~

Đây là **endpoint echo**, không lưu dữ liệu; trong production không công khai endpoint phản chiếu body/header nhạy cảm. Vì bài tập chỉ kiểm chứng CORS, nó không yêu cầu service discovery, load balancing hay session.

Chạy backend và Gateway trong **hai terminal riêng**:

~~~bash
# Trong project backend WebFlux
./mvnw spring-boot:run

# Trong project Gateway WebFlux
./mvnw spring-boot:run
~~~

Ở Windows, dùng `mvnw.cmd spring-boot:run` hoặc Maven đã cài. Gateway cần starter WebFlux và BOM tương thích; ở bản mới tên starter thường là `spring-cloud-starter-gateway-server-webflux`, các bản trước thường dùng `spring-cloud-starter-gateway`.

### 9.1. Kiểm tra GET simple bằng curl

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Accept: application/json"
~~~

Kỳ vọng response có status 200, body mô tả order và header:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
X-Gateway-Route: orders-route
~~~

Không có `OPTIONS` riêng trong thao tác `curl` này; khi browser gửi cùng một GET thỏa simple conditions, thông thường cũng không preflight. Để JavaScript đọc `X-Gateway-Route`, response có thể kèm:

~~~http
Access-Control-Expose-Headers: X-Gateway-Route
~~~

### 9.2. Mô phỏng preflight cho POST JSON có X-Request-Id

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-request-id"
~~~

Kỳ vọng response **2xx** (thường 200 với Spring/WebFlux) và các header cho phép:

~~~http
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: content-type,x-request-id
Access-Control-Max-Age: 600
~~~

Thứ tự/viết hoa trong danh sách method và header có thể khác. Preflight nên được Gateway/WebFlux xử lý; **backend không cần nhận request OPTIONS** để POST sau đó được gửi. Hãy đối chiếu backend access log nếu muốn xác minh điểm này.

Sau preflight, gửi request thật:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: lab-42" \
  --data-binary '{"quantity":2,"confirmed":true}'
~~~

Kỳ vọng response có `Access-Control-Allow-Origin: http://localhost:5173` và JSON đại loại:

~~~json
{
  "method": "POST",
  "id": "42",
  "path": "/orders/42",
  "requestId": "lab-42",
  "body": {
    "quantity": 2,
    "confirmed": true
  }
}
~~~

**Giới hạn của curl:** Các lệnh này chỉ mô phỏng **hai HTTP request riêng biệt** và giúp bạn đọc headers. `curl` không áp chính sách CORS như browser, cũng không tự động gửi POST sau khi OPTIONS thành công. Để xác nhận trình duyệt thực thi preflight, cần dùng một trang thực sự ở origin khác.

### 9.3. Dùng browser để xem đúng hai lượt

Trong một trang web chạy trên `http://localhost:5173`, mở DevTools → Network và chạy:

~~~javascript
// GET simple: thường chỉ có request GET.
const a = await fetch("http://localhost:8080/api/orders/42");
console.log(await a.json());

// POST JSON + custom header: thường có OPTIONS trước POST.
const b = await fetch("http://localhost:8080/api/orders/42", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-Id": "lab-42"
  },
  body: JSON.stringify({ quantity: 2, confirmed: true })
});
console.log(await b.json());
~~~

Quan sát dòng `OPTIONS` ở Network, các `Access-Control-Request-*` của preflight và các `Access-Control-Allow-*` response. Nếu không thấy OPTIONS ở lần gọi thứ hai, có thể browser đang dùng **preflight cache**. Thử URL/combination headers khác, ngữ cảnh browser mới hoặc chờ cache hết hạn để kiểm chứng mà không vô hiệu hóa biện pháp bảo mật.

### 9.4. Test origin và header không được phép

~~~bash
# Origin khác danh sách allowedOrigins
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:9999" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"

# Header X-Admin-Flag không thuộc allowedHeaders
curl -i -X OPTIONS "http://localhost:8080/api/orders/42" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-admin-flag"
~~~

Spring có thể từ chối preflight bằng **403 Invalid CORS request** tùy phiên bản/cấu hình; không nên cố dự đoán một status duy nhất trong mọi setup. **Điều cần xác nhận** là response không cấp quyền CORS sai, và browser không gửi request POST thật sau khi preflight không hợp lệ.

Một GET simple từ origin bị từ chối **vẫn có thể đến backend và trả 200 ở mạng** nhưng JavaScript bị chặn đọc response. Đây là khác biệt quan trọng giữa **chặn preflight trước request thật** và **chặn truy cập response của simple request**.

## 10. Vì sao OPTIONS hay trả 401/403/404 trong Gateway?

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `OPTIONS` 404 nhưng GET vẫn 200 | Route có `Method=GET,POST` nên OPTIONS không khớp; CORS config không ở handler nhận OPTIONS | Bật đúng `globalcors.add-to-simple-url-handler-mapping=true` theo version và path pattern phù hợp |
| `OPTIONS` 401 | Spring Security yêu cầu auth cho preflight vốn không mang cookie/session | Đảm bảo CORS được xử lý **trước** authentication, cấu hình Security/CorsWebFilter phù hợp |
| `OPTIONS` 403 | Origin, requested method hoặc headers không được phép; cũng có thể do security filter | So sánh Origin, Access-Control-Request-Method/Headers với allowlist và log |
| GET 200 nhưng browser báo CORS | Response thật thiếu `Access-Control-Allow-Origin`, bị duplicate hoặc origin không khớp | Xem response headers của GET và policy ở Gateway/backend |
| Có header CORS nhưng browser vẫn từ chối cookie | `Access-Control-Allow-Origin=*` với credentials, thiếu allow-credentials, SameSite/Secure/CORS credentials sai | Thiết kế cụ thể origin + credentials, kiểm tra cookie storage |
| Chỉ POST JSON lỗi | JSON gây preflight; header hoặc method chưa được allow | Kiểm tra OPTIONS trước, rồi POST thật |
| Dùng `curl` thấy API thành công | curl không thực thi CORS | Thử bằng browser thật ở origin khác |
| CORS lỗi lúc có lúc không | CDN/reverse proxy cache response không phân biệt Origin, Gateway/backend ghi trùng headers | Kiểm tra `Vary`, cache policy, trách nhiệm CORS từng lớp |

### 10.1. Spring Security WebFlux phải xử lý preflight đúng vị trí

Tài liệu Spring Security nhấn mạnh **CORS phải được xử lý trước Security** vì preflight không mang session cookie. Nếu request OPTIONS bị lớp xác thực chặn trước khi CORS handler đánh giá, cấu hình Gateway globalcors đúng cũng có thể chưa đủ.

Trong **reactive WebFlux**, lớp lọc liên quan là `CorsWebFilter` và `SecurityWebFilterChain`; **đừng áp nguyên ví dụ `CorsFilter`/Servlet MVC** sang Gateway WebFlux. Hãy bảo đảm Spring Security tích hợp với nguồn `CorsConfigurationSource`/CORS processor phù hợp phiên bản, và tránh tạo hai nguồn CORS cạnh tranh ghi header. Có thể cần cấu hình chính sách cho preflight trong security chain, nhưng không đồng nghĩa cho phép **mọi OPTIONS từ Internet** vượt qua các biện pháp kiểm soát ngoài CORS.

### 10.2. CORS có liên quan tới route predicate hay filter order không?

Có. Gateway chỉ áp dụng **route-specific CORS metadata** nếu một handler/route phù hợp được xác định. Khi `Method` predicate loại OPTIONS, `add-to-simple-url-handler-mapping` giúp áp dụng **global CORS** cả cho requests không được route predicate nhận.

Các Gateway filter như `StripPrefix`, `SetRequestHeader` hoặc `Retry` **không phải công cụ thay thế CORS processor**. Trong luồng đúng, preflight thường được trả lời ở tầng CORS mà **không cần forward OPTIONS đến microservice**; actual request mới đi qua route/filter và LoadBalancer khi được phép.

Nếu bạn buộc backend xử lý OPTIONS, cần bảo đảm request đó thực sự đi đến backend và backend trả header đúng; tuy nhiên với Gateway là một API facade, cấu hình CORS ở gateway thường dễ kiểm soát chính sách tập trung hơn.

## 11. Những bẫy bảo mật và vận hành

### 11.1. CORS không ngăn CSRF

Simple request có thể được trình duyệt gửi **ngay cả khi response không được phép đọc**. Một POST form cross-site có thể gây tác dụng phụ nếu server chỉ dựa vào cookie và không bảo vệ CSRF. Chính sách `SameSite` thích hợp là biện pháp bổ trợ, không thay thế CSRF token và authorization.

### 11.2. Access-Control-Allow-Origin không phải danh sách người dùng

Cho `https://app.example.test` đọc response không có nghĩa mọi user ở origin đó đều được quyền xem đơn hàng. Backend vẫn phải kiểm tra token/session, quyền sở hữu đơn hàng và phân quyền nghiệp vụ. Không tin header `Origin` như chứng chỉ danh tính: client ngoài browser có thể tự gửi Origin tùy ý.

### 11.3. Cookie và CORS credentials là hai kiểm soát độc lập

`Access-Control-Allow-Credentials: true` không tự khiến browser gửi cookie bị `SameSite` hoặc third-party cookie policy ngăn. `credentials: "include"` ở frontend cũng không vượt qua `Secure`/`Domain`/`Path` của cookie. Với request có credentials, hãy trả origin cụ thể và `Vary: Origin` khi response có thể được cache theo origin.

### 11.4. Không để Gateway và backend phát policy mâu thuẫn

Nếu Gateway trả `Access-Control-Allow-Origin: http://localhost:5173` nhưng backend cũng trả `Access-Control-Allow-Origin: *`, response có thể có nhiều giá trị ACAO và browser từ chối. Ưu tiên **một nơi chịu trách nhiệm chính**. Gateway có filter `DedupeResponseHeader` để xử lý duplicate trong một số tình huống, nhưng nó không giải quyết một policy sai hoặc quá rộng; nên sửa chính sách ở nguồn.

### 11.5. Proxy, TLS và cache

Nếu HTTPS kết thúc ở ingress còn Gateway nhận HTTP nội bộ, origin công khai của browser vẫn có scheme HTTPS; policy CORS phải so khớp **origin của frontend thật**, không phải scheme backend. `Forwarded` và `X-Forwarded-*` phải được proxy tin cậy chuẩn hóa; không dùng header tự khai để mở rộng CORS allowlist.

Preflight cache do **browser** quản lý dựa trên các điều kiện cụ thể và có giới hạn riêng. Proxy/CDN cũng có thể cache response HTTP; `Vary: Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` khi phù hợp giúp tránh trả response cho sai tổ hợp origin/method/headers.

### 11.6. Retry, rate limiter và circuit breaker

Preflight không phải request nghiệp vụ tạo đơn hàng. Nên thống kê nó riêng để không làm nhiễu request volume/latency hoặc tiêu hao quota không phù hợp. Nếu OPTIONS bị forward và được retry một cách vô ích, backend có thể nhận traffic thừa; nếu rate limiter chặn OPTIONS trước CORS, browser có thể báo CORS error thay vì status 429 hữu ích.

Với actual POST, retry vẫn phải xét idempotency để tránh ghi dữ liệu lặp. Circuit breaker và discovery/load balancing xử lý đường tới backend, không quyết định quyền truy cập cross-origin của browser.

## 12. Checklist kiểm chứng trước khi release

- [ ] Đã xác định **frontend origin** bằng scheme + hostname + port, không chỉ hostname.
- [ ] Biết request nào simple và request nào cần preflight theo **method + headers + Content-Type + các giới hạn khác**.
- [ ] Dùng đúng namespace CORS của **Gateway Server WebFlux** 4.x hoặc 5.x.
- [ ] Policy có allowed origins, methods, headers, exposed headers, credentials và max age phù hợp; không mở `*` tùy tiện.
- [ ] Test `OPTIONS` với đầy đủ `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
- [ ] Khi route có `Method=GET,POST`, đã kiểm chứng preflight được global CORS xử lý thông qua `add-to-simple-url-handler-mapping` khi cần.
- [ ] Preflight không bị auth filter/rate limiter chặn trước lớp CORS phù hợp.
- [ ] Request thật (GET/POST) đi đúng route, path rewrite, headers và backend instance.
- [ ] Response thật cũng có CORS headers hợp lệ, không chỉ response preflight.
- [ ] Cấu hình credentialed response không dùng `Access-Control-Allow-Origin: *`.
- [ ] Trình duyệt đọc được response trong DevTools/JavaScript; không chỉ căn cứ HTTP 200 từ curl.
- [ ] Gateway và backend không phát header CORS trùng lặp hoặc mâu thuẫn.
- [ ] CSRF, xác thực và phân quyền được kiểm soát độc lập với CORS.
- [ ] Metrics/traces phân biệt preflight và actual request; log không chứa token, cookie hay dữ liệu nhạy cảm.

## 13. Tài liệu chính thức để đối chiếu

1. [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): điều kiện simple request, preflight, response headers, credentials và ví dụ browser.
2. [MDN — CORS-safelisted request header](https://developer.mozilla.org/en-US/docs/Glossary/CORS-safelisted_request_header): hạn chế cụ thể về tên, giá trị và độ dài headers.
3. [Spring Cloud Gateway Server WebFlux 5.x — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html): globalcors, per-route metadata và `add-to-simple-url-handler-mapping`.
4. [Spring Cloud Gateway Server WebFlux 4.3.x — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/cors-configuration.html): namespace `spring.cloud.gateway.globalcors`.
5. [Spring Cloud Gateway 4.2.x — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/cors-configuration.html): namespace của bản WebFlux trước.
6. [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): cách HandlerMapping xử lý preflight và actual CORS.
7. [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): `CorsWebFilter` và thứ tự xử lý CORS trước Security.

**Ghi nhớ:** **Simple cross-origin request được browser gửi trực tiếp**, sau đó browser mới kiểm tra CORS trên response. **Request cần preflight gửi `OPTIONS` trước**, hỏi quyền gửi method/headers rồi mới gửi request thật nếu được phép. Trong Spring Cloud Gateway Server WebFlux, cấu hình global CORS theo origin/path, xử lý OPTIONS không khớp predicate, phối hợp đúng với Spring Security và luôn nhớ: **CORS không thay thế xác thực, phân quyền hoặc CSRF protection**.
