# Chạy thử và kiểm chứng đường dẫn, header, body và mã phản hồi

## 1. Mục tiêu: chứng minh một request đã thực sự đi qua gateway

Ở bước **Khởi tạo** của **SPRING_CLOUD_GATEWAY**, việc ứng dụng khởi động thành công chưa chứng minh route hoạt động đúng. Ta cần gửi HTTP request thật từ client, kiểm tra chính xác **đường dẫn**, **header**, **body**, **mã phản hồi**, đồng thời xác định phản hồi xuất phát từ gateway hay từ microservice.

Spring Cloud Gateway dùng **route predicate** để chọn tuyến, **filter chain** để áp dụng các phép biến đổi path/header hoặc chính sách bảo mật, sau đó chuyển tiếp tới service đích. Bài này thiết lập một backend “echo” nhỏ để quan sát những gì service **thực sự nhận được**. Quy trình kiểm tra là nền tảng trước khi bổ sung discovery/load balancing, xác thực, rate limiting, circuit breaker, retry, TLS hoặc metrics/tracing trong hệ thống microservices.

Sau bài này, bạn sẽ tự kiểm chứng được:

1. Request có khớp predicate và đi vào đúng route không?
2. Đường dẫn sau `StripPrefix` có đúng với endpoint của backend không?
3. Header do gateway thêm hoặc ghi đè có đến backend; header phản hồi có đến client không?
4. JSON body của request có tới backend với dữ liệu đúng không?
5. Status từ backend có được chuyển tới client; status do gateway tạo ra khác gì?
6. Khi test thất bại, nên kiểm tra tại client, gateway hay backend trước?

> **Phạm vi:** Ví dụ dùng **Spring Cloud Gateway Server WebFlux** với backend chạy ngay trên máy phát triển. Hai ứng dụng dùng HTTP trên `localhost` để dễ thử nghiệm; khi triển khai thật, cần thiết kế TLS, xác thực, chính sách header và quan sát truy cập phù hợp.

## 2. Kiến trúc thử nghiệm và kết quả mong đợi

Ta chạy hai ứng dụng ở hai tiến trình/cổng riêng:

| Thành phần | Địa chỉ thử nghiệm | Vai trò |
| --- | --- | --- |
| Client | `curl` hoặc HTTP client | Gọi gateway và đọc kết quả |
| Gateway WebFlux | `http://localhost:8080` | Khớp route, bỏ prefix path, đặt header, chuyển tiếp |
| Echo backend | `http://localhost:9091` | Trả lại method/path/query/header/body đã nhận; tạo status tùy chọn |

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Spring Cloud Gateway :8080
    participant B as Echo service :9091
    C->>G: GET /api/echo/inspect/42?view=full
    Note over G: Predicate Path=/api/echo/** khớp
    Note over G: StripPrefix=1 và SetRequestHeader
    G->>B: GET /echo/inspect/42?view=full
    B-->>G: 200 JSON chứa path và headers đã nhận
    Note over G: AddResponseHeader
    G-->>C: 200 JSON và X-Gateway-Response
~~~

Một route ví dụ sẽ chuyển đổi:

| Thuộc tính | Client gửi đến gateway | Backend nhận |
| --- | --- | --- |
| Method | `GET` | `GET` |
| Path | `/api/echo/inspect/42` | `/echo/inspect/42` |
| Query | `view=full` | `view=full` |
| Header `X-Debug-Client` | `manual-test` | `manual-test` |
| Header `X-Gateway-Marker` | Có thể không có hoặc do client giả mạo | `edge-lab` do gateway đặt lại |
| Body | Không có ở ví dụ GET | Không có |
| Response header `X-Gateway-Response` | Chưa có trước khi gọi | Gateway thêm vào phản hồi gửi client |

Những gì cần so sánh là dữ liệu **thực tế mà backend ghi nhận**, không phải chỉ cấu hình YAML “trông có vẻ đúng”.

## 3. Chuẩn bị hai ứng dụng Spring Boot

Ví dụ giả định bạn có JDK phù hợp với phiên bản Spring Boot/Spring Cloud đang sử dụng, Maven (hoặc Maven Wrapper) và công cụ `curl`. Cần chọn **Spring Cloud release train tương thích với Spring Boot** và import Spring Cloud BOM trong dự án gateway; tránh ghép ngẫu nhiên các phiên bản. Hai ứng dụng nên chạy độc lập để thấy rõ ranh giới mạng.

### 3.1. Echo backend

Tạo ứng dụng Spring Boot có dependency `spring-boot-starter-webflux`. Backend này chỉ dùng để kiểm tra, không cần service registry, database hay bảo mật bổ sung.

`src/main/resources/application.yml` của backend:

~~~yaml
spring:
  application:
    name: echo-service
server:
  port: 9091
~~~

Lớp khởi chạy `EchoApplication.java`:

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

Tạo thêm controller **cùng package** `demo.echo`:

~~~java
package demo.echo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    private Map<String, Object> describe(
            ServerHttpRequest request, String clientHeader, String marker) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("method", request.getMethod().name());
        result.put("path", request.getPath().value());
        result.put("query", request.getURI().getRawQuery());
        result.put("clientHeader", clientHeader);
        result.put("gatewayMarker", marker);
        return result;
    }

    @GetMapping("/echo/inspect/{id}")
    public Map<String, Object> inspect(
            @PathVariable String id,
            @RequestHeader(value = "X-Debug-Client", required = false)
                    String clientHeader,
            @RequestHeader(value = "X-Gateway-Marker", required = false)
                    String marker,
            ServerHttpRequest request) {

        Map<String, Object> result = describe(request, clientHeader, marker);
        result.put("id", id);
        return result;
    }

    @PostMapping("/echo/inspect")
    public Mono<Map<String, Object>> inspectBody(
            @RequestBody Mono<Map<String, Object>> body,
            @RequestHeader(value = "X-Debug-Client", required = false)
                    String clientHeader,
            @RequestHeader(value = "X-Gateway-Marker", required = false)
                    String marker,
            ServerHttpRequest request) {

        return body.map(payload -> {
            Map<String, Object> result =
                    describe(request, clientHeader, marker);
            result.put("body", payload);
            return result;
        });
    }

    @GetMapping("/echo/status/{code}")
    public ResponseEntity<String> status(@PathVariable int code) {
        return ResponseEntity.status(code)
                .header("X-Origin", "echo-service")
                .body("backend-status-" + code);
    }
}
~~~

Controller này cho phép:

- `GET /echo/inspect/{id}`: trả JSON mô tả request đã nhận.
- `POST /echo/inspect`: nhận JSON body thành một `Map` rồi đưa lại vào JSON response để kiểm tra **nội dung dữ liệu**.
- `GET /echo/status/{code}`: chủ động trả mã HTTP cùng header `X-Origin: echo-service` để nhận biết phản hồi từ backend.

Khi backend chưa có gateway phía trước, thử gọi trực tiếp:

~~~bash
curl -i "http://localhost:9091/echo/inspect/42?view=full"
~~~

Kỳ vọng backend trả `200 OK`, JSON có `"path":"/echo/inspect/42"`, `"id":"42"`; các trường `clientHeader` và `gatewayMarker` chưa được đặt sẽ là `null`. Việc kiểm tra backend riêng giúp phân biệt lỗi ứng dụng đích với lỗi định tuyến sau này.

### 3.2. Ứng dụng Spring Cloud Gateway

Trong dự án gateway, dùng Spring Boot với Spring Cloud Gateway **Server WebFlux** và Spring Cloud BOM tương thích. Ở các release mới, starter thường là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>
~~~

Các bản Spring Cloud Gateway trước đây dùng tên starter `spring-cloud-starter-gateway`. Chọn dependency theo tài liệu của **đúng phiên bản** đang dùng; không thêm `spring-boot-starter-web` (Servlet MVC) vào dự án Gateway WebFlux.

Lớp khởi chạy:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
~~~

Với Spring Cloud Gateway Server WebFlux sử dụng namespace cấu hình mới, đặt trong `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: echo-route
              uri: http://localhost:9091
              predicates:
                - Path=/api/echo/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Gateway-Marker, edge-lab
                - AddResponseHeader=X-Gateway-Response, routed
~~~

> **Khác biệt theo phiên bản:** Một số bản Gateway WebFlux dùng `spring.cloud.gateway.routes` thay cho `spring.cloud.gateway.server.webflux.routes`. Với bản đó, chuyển **nguyên danh sách `routes`** vào `spring.cloud.gateway.routes`; không định nghĩa đồng thời cả hai namespace. Nếu cấu hình sai namespace, ứng dụng có thể khởi động nhưng không đăng ký route — các bài test sẽ trả 404.

Ý nghĩa cấu hình:

| Thành phần | Hành vi cần kiểm chứng |
| --- | --- |
| `id: echo-route` | Tên route để nhận diện khi xem cấu hình và log |
| `uri: http://localhost:9091` | Đích HTTP cố định để test mà chưa cần service discovery |
| `Path=/api/echo/**` | Chọn request có đường dẫn bắt đầu theo mẫu này |
| `StripPrefix=1` | Bỏ một phân đoạn đầu tiên (`api`), nên `/api/echo/inspect/42` thành `/echo/inspect/42` |
| `SetRequestHeader` | Đặt lại `X-Gateway-Marker` thành `edge-lab` trên request chuyển tiếp, kể cả khi client tự gửi giá trị khác |
| `AddResponseHeader` | Bổ sung `X-Gateway-Response: routed` vào response của route |

Không có filter nào trong ví dụ được cấu hình để biến đổi JSON body hoặc sửa HTTP status do backend trả.

### 3.3. Khởi động đúng thứ tự

Mở **hai terminal** ở hai thư mục dự án. Khởi động backend trước, kiểm tra endpoint trực tiếp trên `9091`, sau đó khởi động gateway ở `8080`:

~~~bash
# Terminal 1: trong dự án echo-service
./mvnw spring-boot:run

# Terminal 2: trong dự án gateway-lab
./mvnw spring-boot:run
~~~

Nếu dự án dùng Maven đã cài sẵn thì dùng `mvn spring-boot:run`; với Windows có thể dùng `mvnw.cmd spring-boot:run`. Mỗi lệnh phải chạy trong **đúng thư mục dự án** có cấu hình Maven tương ứng.

Khi thử nghiệm, tạm tránh các filter auth, rate limiter, retry hay circuit breaker chưa được giải thích, vì chúng có thể chặn hoặc thay đổi kết quả trước khi ta kiểm chứng route cơ bản.

## 4. Kiểm chứng đường dẫn và query string

Gọi vào gateway:

~~~bash
curl -i "http://localhost:8080/api/echo/inspect/42?view=full" \
  -H "X-Debug-Client: manual-test"
~~~

Một response **minh họa** (thứ tự header và JSON field có thể khác):

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Gateway-Response: routed

{"method":"GET","path":"/echo/inspect/42","query":"view=full","clientHeader":"manual-test","gatewayMarker":"edge-lab","id":"42"}
~~~

Hãy kiểm tra ba giá trị trong body:

1. `path` là `/echo/inspect/42`, chứng tỏ gateway đã áp dụng `StripPrefix=1` trước khi gọi backend.
2. `query` vẫn là `view=full`, chứng tỏ query string được chuyển tiếp qua phép biến đổi prefix.
3. `id` là `42`, chứng tỏ endpoint backend đã khớp và xử lý đúng path mới.

Nếu response hiển thị `"path":"/api/echo/inspect/42"`, rất có thể filter bỏ prefix chưa được nạp, route thực tế không phải route dự kiến, hoặc request được gửi trực tiếp tới backend khác với cấu hình thử nghiệm. Nếu mã là `404`, cần xác định **404 do gateway không tìm thấy route** hay **404 do backend không có endpoint** (xem mục 7).

## 5. Kiểm chứng request header và response header

Trong lệnh GET ở trên, client chủ động gửi `X-Debug-Client: manual-test`; gateway bổ sung/ghi đè `X-Gateway-Marker: edge-lab`. Backend trả lại cả hai trong JSON, nên ta kiểm tra được header có thật sự đi qua hai chặng.

Để chứng minh `SetRequestHeader` **ghi đè** dữ liệu client đưa vào, thử:

~~~bash
curl -i "http://localhost:8080/api/echo/inspect/42" \
  -H "X-Gateway-Marker: forged-value" \
  -H "X-Debug-Client: from-client"
~~~

Kết quả backend phải cho:

~~~json
{
  "method": "GET",
  "path": "/echo/inspect/42",
  "query": null,
  "clientHeader": "from-client",
  "gatewayMarker": "edge-lab",
  "id": "42"
}
~~~

Đồng thời trong **response headers** của lệnh `curl -i`, tìm:

~~~http
X-Gateway-Response: routed
~~~

Ý nghĩa bảo mật: một header do gateway gắn vào cho mục đích chẩn đoán **không tự động trở thành bằng chứng danh tính**. Muốn tin vào header nhận dạng người dùng, phải có cơ chế xác thực, loại bỏ giá trị giả mạo từ client, bảo vệ đường từ gateway đến backend và giới hạn truy cập trực tiếp vào backend.

Không nên kỳ vọng tất cả các header của client đều được chuyển nguyên trạng. Proxy có thể xử lý các header theo từng chặng như `Host`, `Connection`, `Content-Length`, `Transfer-Encoding`; ngoài ra cấu hình `Forwarded` và `X-Forwarded-*` phụ thuộc kiến trúc reverse proxy và danh sách nguồn tin cậy.

## 6. Kiểm chứng request body với POST JSON

Để kiểm tra body, gửi JSON qua gateway vào endpoint `POST /echo/inspect`. Ví dụ trên môi trường Bash:

~~~bash
curl -i -X POST "http://localhost:8080/api/echo/inspect" \
  -H "Content-Type: application/json" \
  -H "X-Debug-Client: body-check" \
  --data-binary '{"orderId":"O-42","quantity":2,"paid":false}'
~~~

Response `200 OK` có thể mang body:

~~~json
{
  "method": "POST",
  "path": "/echo/inspect",
  "query": null,
  "clientHeader": "body-check",
  "gatewayMarker": "edge-lab",
  "body": {
    "orderId": "O-42",
    "quantity": 2,
    "paid": false
  }
}
~~~

Các bước xác minh quan trọng:

- **Path:** backend thấy `/echo/inspect`, không phải `/api/echo/inspect`.
- **Method:** vẫn là `POST`, không vô tình biến thành `GET`.
- **Body:** đủ ba trường `orderId`, `quantity`, `paid` với kiểu dữ liệu đúng (chuỗi, số, boolean).
- **Header:** `Content-Type: application/json` giúp backend chọn bộ giải mã JSON; `X-Gateway-Marker` tiếp tục là `edge-lab`.
- **Status và response header:** request hợp lệ trả `200` và có `X-Gateway-Response: routed`.

Ví dụ này chứng minh **nội dung JSON tương đương về mặt dữ liệu**, không phải từng byte của payload phải giống hệt. Backend đã giải mã JSON thành `Map` rồi mã hóa lại thành JSON để trả, nên khoảng trắng hoặc thứ tự trường có thể khác. Muốn chứng minh tính nguyên vẹn từng byte, cần một backend trả checksum của raw body hoặc so sánh byte ở hai đầu.

**Riêng Windows PowerShell:** sử dụng `curl.exe` để tránh alias `curl` của Windows PowerShell 5.1. Với payload JSON phức tạp, lưu UTF-8 vào `payload.json` rồi dùng `--data-binary "@payload.json"`; lưu ý UTF-8 **không BOM** khi so sánh byte hoặc làm việc với parser nghiêm ngặt.

### Nếu request body không tới backend?

Đối chiếu POST gọi **trực tiếp** vào backend:

~~~bash
curl -i -X POST "http://localhost:9091/echo/inspect" \
  -H "Content-Type: application/json" \
  --data-binary '{"orderId":"O-42","quantity":2,"paid":false}'
~~~

Nếu gọi trực tiếp thành công nhưng qua gateway thất bại, kiểm tra route, filter sửa body, giới hạn request size hoặc filter tự viết có đọc `Flux<DataBuffer>` rồi không đưa body trở lại chain. Với WebFlux, body là luồng dữ liệu reactive; tự gọi `block()` hay `subscribe()` bên trong gateway filter có thể tạo lỗi vòng đời và hiệu năng. Trong bài lab này, `StripPrefix` và `SetRequestHeader` không yêu cầu đọc body, nên JSON được chuyển tiếp mà không có cấu hình body rewrite.

## 7. Kiểm chứng mã phản hồi và nguồn phát sinh lỗi

Gateway có thể trả lỗi ngay tại cổng vào (chẳng hạn không route khớp, bị rate limit hoặc không xác thực), hoặc chuyển tiếp lỗi mà backend chủ động trả. Hai loại này cần được phân biệt.

### 7.1. Backend chủ động trả status khác 200

Gọi endpoint status đã tạo:

~~~bash
curl -i "http://localhost:8080/api/echo/status/418"
~~~

Kỳ vọng:

~~~http
HTTP/1.1 418
X-Origin: echo-service
X-Gateway-Response: routed

backend-status-418
~~~

HTTP status `418` ở đây là mã thử nghiệm được **backend chủ động tạo**. Header `X-Origin: echo-service` và body `backend-status-418` là dấu hiệu phản hồi đi từ backend qua gateway; `X-Gateway-Response: routed` do gateway thêm trên đường về. Bạn có thể thử `/api/echo/status/404` hoặc `/api/echo/status/503` để thấy gateway có thể chuyển tiếp status 4xx/5xx từ backend theo cấu hình hiện tại.

Chạy cùng endpoint trực tiếp:

~~~bash
curl -i "http://localhost:9091/echo/status/418"
~~~

Response trực tiếp sẽ có `X-Origin` nhưng **không có header `X-Gateway-Response`** do gateway cấu hình, giúp so sánh hai đường đi.

### 7.2. Gateway không tìm thấy route

Gọi một path nằm ngoài predicate `Path=/api/echo/**`:

~~~bash
curl -i "http://localhost:8080/api/other/inspect/42"
~~~

Nếu không còn route hoặc handler khác, gateway trả **404 Not Found**. Echo service không nhận request này. Việc không thấy `X-Gateway-Response: routed` cũng là manh mối vì filter này chỉ thuộc route `echo-route`.

### 7.3. Route khớp nhưng backend không có endpoint

Gọi một path **vẫn khớp route** nhưng backend không có mapping:

~~~bash
curl -i "http://localhost:8080/api/echo/missing"
~~~

Gateway khớp `Path=/api/echo/**`, bỏ prefix thành `/echo/missing` và chuyển tiếp; backend có thể trả **404** do không tìm thấy endpoint. Kết quả trên client cùng là 404 nhưng nguyên nhân khác hoàn toàn so với trường hợp 7.2.

| Tình huống | Có khớp route? | Backend có nhận HTTP request? | Dấu hiệu cần đối chiếu |
| --- | --- | --- | --- |
| `/api/other/inspect/42` | Không, nếu chỉ có route ví dụ | Không | 404 tại gateway; không có log request backend |
| `/api/echo/missing` | Có | Có | Backend nhận `/echo/missing` rồi trả 404 |
| `/api/echo/status/418` | Có | Có | Backend tạo 418, `X-Origin` và body đặc trưng |
| `/api/echo/inspect/42` | Có | Có | Backend trả 200 và JSON mô tả request |

Nếu tắt backend để thử lỗi kết nối, gateway thường tạo lỗi 5xx. **Không nên khẳng định một mã duy nhất** cho mọi phiên bản và cấu hình: kết quả phụ thuộc vào bộ xử lý lỗi, timeout, retry, circuit breaker hay fallback đã bật. Với URI tĩnh ở lab, lỗi kết nối cũng khác với `lb://service-id` không tìm thấy instance (thường 503 theo mặc định với Gateway WebFlux LoadBalancer).

## 8. Bảng smoke test và cách đối chiếu

Chạy các phép thử sau **sau khi** hai ứng dụng đã khởi động. Bảng là tiêu chuẩn để bạn tự so với kết quả thực tế, không phải kết quả đã được đo tự động trong bài viết.

| Bài kiểm tra | Request qua gateway | Kỳ vọng chính |
| --- | --- | --- |
| Route và path | `GET /api/echo/inspect/42?view=full` | 200, backend path `/echo/inspect/42`, query `view=full` |
| Header client | GET trên với `X-Debug-Client: manual-test` | JSON phản hồi chứa `clientHeader=manual-test` |
| Ghi đè header | GET trên với `X-Gateway-Marker: forged-value` | JSON phản hồi chứa `gatewayMarker=edge-lab` |
| Response header | GET theo route bất kỳ | Response chứa `X-Gateway-Response: routed` |
| JSON body | `POST /api/echo/inspect` với JSON hợp lệ | 200 và body echo giữ trường/kiểu dữ liệu |
| Status backend | `GET /api/echo/status/418` | 418, `X-Origin: echo-service`, body `backend-status-418` |
| Không khớp route | `GET /api/other/inspect/42` | Thường 404, backend không nhận request |
| Endpoint backend không có | `GET /api/echo/missing` | Thường 404 sau khi route đã khớp |

Ví dụ kiểm tra nhanh status từ terminal Bash, không in toàn bộ body:

~~~bash
curl -sS -o /dev/null -w 'GET inspect: %{http_code}\n' \
  "http://localhost:8080/api/echo/inspect/42"

curl -sS -o /dev/null -w 'Backend status: %{http_code}\n' \
  "http://localhost:8080/api/echo/status/418"

curl -sS -o /dev/null -w 'No route: %{http_code}\n' \
  "http://localhost:8080/api/other/inspect/42"
~~~

Kỳ vọng với **đúng cấu hình** là lần lượt `200`, `418`, `404`. Mã `curl` exit code và HTTP status là **hai tín hiệu khác nhau**: một response HTTP 404 hay 418 vẫn có thể khiến `curl` kết thúc với exit code 0 khi không dùng `--fail`. Khi tự động hóa smoke test, cần kiểm tra giá trị `%{http_code}` hoặc dùng chế độ `--fail-with-body` nếu phiên bản curl hỗ trợ.

Để xem đầy đủ headers và luồng kết nối, dùng `curl -v` hoặc `curl -i`. Với JSON body, nên kiểm tra cấu trúc JSON thay vì phụ thuộc thứ tự field hay dòng xuống hàng.

## 9. Chẩn đoán lỗi theo vị trí

### Gateway trả 404 cho mọi request

Kiểm tra ứng dụng gateway đã nạp **đúng namespace cấu hình routes** của phiên bản chưa, cổng `8080` có phải của gateway không, và predicate `Path=/api/echo/**` có khớp path client gọi không. Nếu ứng dụng có Actuator và endpoint gateway đã được **cho phép truy cập an toàn**, có thể dùng thông tin route được expose để xác minh route thực sự đăng ký. Không mở endpoint quản trị công khai chỉ để debug.

### Gateway trả 502/503/504 hoặc lỗi kết nối

Gọi backend trực tiếp tại `9091` trước. Kiểm tra service đang chạy, URL `uri` đúng và không có nhầm lẫn `localhost` giữa các môi trường. Khi gateway chạy trong Docker container, `localhost:9091` trỏ về **container của gateway**, không phải máy host hay container backend. Cần dùng tên service/mạng container hoặc địa chỉ phù hợp. Kiểm tra cả timeout hay circuit breaker nếu các cơ chế đó đã được bật.

### Backend nhận sai path

In/echo đường dẫn **tại backend**. Trường hợp `/api/echo/inspect/42` không được đổi thành `/echo/inspect/42` thường liên quan đến `StripPrefix` chưa được áp dụng, route khác được chọn hoặc một filter `RewritePath` khác đã thay path trước/sau đó. Route predicate chọn tuyến theo request trước giai đoạn gateway filter; đừng lẫn đường dẫn khớp predicate với đường dẫn được forward.

### Header thiếu hoặc sai

Đối chiếu header ở **cả request và response**. `SetRequestHeader` sửa request tới backend; `AddResponseHeader` sửa response về client. Hai filter này làm việc ở hai chiều khác nhau. Nếu có reverse proxy hoặc load balancer phía trước, cấu hình xử lý header hop-by-hop và `Forwarded`/`X-Forwarded-*` cũng ảnh hưởng tới giá trị thực tế.

### Body rỗng hoặc trả 400

Gọi POST trực tiếp backend để xác nhận endpoint nhận đúng `Content-Type: application/json` và JSON hợp lệ. Nếu chỉ lỗi qua gateway, kiểm tra các filter đọc/biến đổi body, giới hạn kích thước request, sự kiện client hủy kết nối và cách sử dụng `DataBuffer`. Một `GlobalFilter` tự subscribe/consume request body mà không phát lại cho downstream có thể làm hỏng luồng chuyển tiếp.

### Status không giống backend

Kiểm tra có filter response-status, security, rate limiter, circuit breaker/fallback, timeout hoặc exception handler nào tham gia không. Gateway có thể trả 401, 403, 429 hoặc 5xx **trước khi** microservice nhận request; khi backend chủ động trả 4xx/5xx, cấu hình route mặc định thường chuyển tiếp mã đó. Cần kết hợp status, body, headers, access log backend và trace để quy trách nhiệm chính xác.

## 10. Từ bài lab đến gateway nhiều service

Bài khởi tạo dùng `uri: http://localhost:9091` để cô lập việc kiểm chứng HTTP. Trong kiến trúc microservices, bạn có thể thay URI bằng `lb://echo-service` và cấu hình Spring Cloud LoadBalancer cùng nguồn khám phá service phù hợp. Khi đó cùng bộ smoke test vẫn phải đạt đối với path, header, body và status, nhưng xuất hiện thêm bước chọn instance và một nhóm lỗi mới: service ID sai, registry không có instance hoặc instance được chọn không khỏe.

Khi mở rộng thêm các khả năng của Spring Cloud Gateway, nên giữ một bộ test tương tự:

- **Xác thực/ủy quyền:** thêm test token thiếu/sai, quyền không đủ; xác minh request bị chặn tại gateway hay backend và không rò rỉ token vào log.
- **Rate limiting:** gửi nhiều request theo cùng khóa và kiểm tra hành vi 429 theo cấu hình; tránh phụ thuộc vào thời điểm ngẫu nhiên của bucket.
- **Circuit breaker, timeout, retry:** dùng backend giả lập lỗi/chậm để kiểm tra mã, fallback và số lần backend nhận request; đặc biệt thận trọng với retry thao tác tạo mới/ghi dữ liệu.
- **TLS:** kiểm chứng client kết nối HTTPS đúng certificate và, nếu dùng HTTPS/mTLS tới backend, kiểm chứng cả chặng gateway → service.
- **Observability:** truyền trace ID/correlation ID, đo latency từng chặng và log route ID, URL đích đã chọn, status; không log Authorization, cookie hay body chứa dữ liệu nhạy cảm.

**Tiêu chí hoàn thành bài:** Bạn đã có thể chứng minh bằng request/response thực rằng `/api/echo/...` đi qua route, trở thành `/echo/...` tại backend; các header và JSON body có nội dung đúng; status 200, 418 và 404 phản ánh các trường hợp khác nhau; và biết lần theo từng bước khi kết quả sai. Đây là cơ sở thực nghiệm để tiếp tục xây dựng một API Gateway an toàn, quan sát được và dễ vận hành.
