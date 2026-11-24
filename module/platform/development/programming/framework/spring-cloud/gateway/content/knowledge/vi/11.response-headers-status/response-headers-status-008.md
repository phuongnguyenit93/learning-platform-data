# Cookie, thuộc tính Set-Cookie và tác động của proxy

## 1. Vì sao cookie dễ gặp lỗi khi đi qua Spring Cloud Gateway?

Một website có thể gọi API qua địa chỉ công khai `https://api.example.test/api/auth/login`, trong khi dịch vụ xác thực thực tế chạy ở `http://auth-service:8080/auth/login`. Spring Cloud Gateway nhận request, chọn route theo predicate, xử lý filter chain, có thể bỏ prefix đường dẫn hoặc thay header rồi chuyển tiếp request. Khi service trả response chứa **`Set-Cookie`**, gateway lại gửi response đó về client.

Vấn đề là trình duyệt lưu cookie dựa trên **URL mà trình duyệt nhìn thấy**, kèm các thuộc tính trong `Set-Cookie`. Trình duyệt không biết đường dẫn hay tên host nội bộ mà gateway dùng để gọi backend. Nếu backend đặt cookie với `Path` hoặc `Domain` dành cho địa chỉ nội bộ, client có thể không lưu cookie hoặc không gửi cookie ở request tiếp theo, dù response đăng nhập đã trả **200 OK**.

Bài thuộc chương **Header và trạng thái** của **SPRING_CLOUD_GATEWAY**, tập trung vào:

- Quan hệ giữa header **`Set-Cookie` trong response** và **`Cookie` trong request**.
- Ý nghĩa các thuộc tính `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, `Max-Age`, `Expires` và các trường hợp đặc biệt.
- Tác động của reverse proxy, TLS termination, path rewriting, host, redirect, CORS và nhiều tầng cache.
- Cách cấu hình và kiểm chứng cookie trong Spring Cloud Gateway Server WebFlux mà không vô tình phá session hoặc làm yếu cơ chế xác thực.

Các kiến thức này liên quan trực tiếp tới xây dựng API Gateway an toàn cho microservices: route predicate, filter chain, biến đổi path/header, service discovery, xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và quan sát request.

> **Phạm vi:** Ví dụ dùng **Spring Cloud Gateway Server WebFlux**. Tên dependency và namespace YAML thay đổi giữa một số phiên bản Spring Cloud. Các ví dụ test dùng HTTP trên `localhost` với cookie giả lập; đối với phiên đăng nhập thật trên Internet, cần HTTPS và cơ chế xác thực/phân quyền phù hợp.

## 2. Cookie đi qua hai chiều HTTP khác nhau

Một cookie được **server đề xuất lưu** bằng header `Set-Cookie` trong response. Sau đó, **client tự quyết định** có lưu và gửi lại cookie hay không theo các quy tắc của trình duyệt: domain, path, secure transport, SameSite, hạn dùng và chính sách quyền riêng tư.

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant G as Gateway
    participant A as auth-service
    C->>G: POST /api/auth/login
    Note over G: StripPrefix=1
    G->>A: POST /auth/login
    A-->>G: 200 + Set-Cookie: sid=...; Path=/api/auth
    G-->>C: 200 + Set-Cookie
    Note over C: Kiểm tra và lưu cookie<br/>theo URL công khai + thuộc tính
    C->>G: GET /api/auth/profile<br/>Cookie: sid=...
    G->>A: GET /auth/profile<br/>Cookie: sid=...
    A-->>G: 200 + dữ liệu
    G-->>C: 200 + dữ liệu
~~~

| Header | Hướng | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| **`Set-Cookie`** | Backend → Gateway → client | `Set-Cookie: sid=abc; Path=/api/auth; HttpOnly; Secure; SameSite=Lax` | Đề nghị client lưu/cập nhật cookie kèm phạm vi và ràng buộc |
| **`Cookie`** | Client → Gateway → backend | `Cookie: sid=abc` | Client gửi các cookie đủ điều kiện cho request hiện tại |

**Cookie request không mang theo thuộc tính `Path`, `Domain`, `Secure` hay `HttpOnly`.** Các thuộc tính này được client dùng khi lưu và chọn cookie. Backend chỉ nhận các cặp `name=value` trong header `Cookie`. Nếu có nhiều cookie cùng tên nhưng khác path/domain, client có thể gửi nhiều cặp trùng tên; backend không thể suy ra scope ban đầu chỉ từ header request.

Một HTTP response có thể có **nhiều dòng `Set-Cookie` độc lập**:

~~~http
HTTP/1.1 200 OK
Set-Cookie: sid=token-abc; Path=/api/auth; Secure; HttpOnly; SameSite=Lax
Set-Cookie: ui_theme=dark; Path=/; Secure; SameSite=Lax
Content-Type: application/json

{"status":"ok"}
~~~

Không được gom hai dòng thành một dòng `Set-Cookie` bằng cách nối dấu phẩy. Khác với nhiều header HTTP dạng danh sách, `Set-Cookie` phải giữ từng trường riêng; `Expires` còn có thể chứa **dấu phẩy trong ngày tháng HTTP**, nên tách/gộp bằng `split(",")` là sai.

## 3. Các thuộc tính Set-Cookie cần hiểu thật rõ

Ví dụ response từ địa chỉ công khai `https://api.example.test/api/auth/login`:

~~~http
Set-Cookie: sid=opaque-token; Path=/api/auth; Max-Age=1200; Secure; HttpOnly; SameSite=Lax
~~~

| Thuộc tính | Tác dụng | Hệ quả khi đi qua proxy |
| --- | --- | --- |
| **`name=value`** | Tên và giá trị cookie | Không đặt access token hoặc thông tin nhạy cảm có thể đọc hiểu được dưới dạng plain text chỉ vì đã bật HTTPS |
| **`Domain`** | Nếu bỏ trống, cookie là **host-only**, gắn với host công khai đã trả response; nếu đặt, cookie áp dụng cho domain đó và các subdomain phù hợp | Backend đặt `Domain=auth-service.internal` sẽ không hợp lệ khi response đến từ `api.example.test` |
| **`Path`** | Trình duyệt chỉ gửi cookie khi path request nằm trong phạm vi hợp lệ | Backend đặt `Path=/auth` sẽ không khớp URL công khai `/api/auth/profile` |
| **`Secure`** | Chỉ gửi cookie qua HTTPS (trình duyệt có ngoại lệ riêng đối với `localhost`) | TLS có thể kết thúc tại edge; browser đánh giá HTTPS của **URL ngoài**, không dựa vào HTTP nội bộ |
| **`HttpOnly`** | Ngăn truy cập cookie bằng `document.cookie` | Không ngăn trình duyệt tự gửi cookie trong request JavaScript nếu các quy tắc cookie/credentials cho phép |
| **`SameSite=Strict`** | Chỉ gửi trong ngữ cảnh same-site theo chính sách của browser | Phù hợp khi muốn hạn chế tối đa gửi cookie từ ngữ cảnh website khác |
| **`SameSite=Lax`** | Same-site và một số điều hướng top-level cross-site an toàn | Thường hợp lý cho phiên đăng nhập web; không bảo vệ hoàn toàn khỏi CSRF |
| **`SameSite=None`** | Cho phép ngữ cảnh cross-site theo chính sách browser | Browser hiện đại yêu cầu đi kèm **`Secure`**; còn phụ thuộc chính sách third-party cookies |
| **`Max-Age`** | Số giây cookie còn hiệu lực; `0` hoặc âm thường làm cookie hết hạn | Khi có cả `Max-Age` và `Expires`, `Max-Age` được ưu tiên |
| **`Expires`** | Ngày/giờ hết hạn tuyệt đối, theo HTTP-date | Cần định dạng hợp lệ; lệch đồng hồ server/client có thể ảnh hưởng cách browser tính thời hạn |
| **`Partitioned`** | Lưu cookie trong kho được phân vùng theo top-level site (CHIPS) ở browser hỗ trợ | Bắt buộc có `Secure`; cần kiểm tra hỗ trợ trình duyệt và ngữ cảnh dùng thực tế |

### 3.1. Domain: backend host khác browser host

Nếu client gọi `https://api.example.test/api/auth/login` thì **host công khai là `api.example.test`**, kể cả khi Gateway forward tới `http://auth-service:8080`.

Đây là cookie thường hợp lệ cho client:

~~~http
Set-Cookie: sid=abc; Path=/api/auth; Secure; HttpOnly; SameSite=Lax
~~~

Do không có `Domain`, nó là **host-only** trên `api.example.test`. Trong khi đó:

~~~http
Set-Cookie: sid=abc; Domain=auth-service.internal; Path=/; Secure; HttpOnly
~~~

không phù hợp với host `api.example.test` nên trình duyệt sẽ từ chối. Một server chỉ được đặt `Domain` thuộc host của response hoặc domain cha hợp lệ, không được đặt tùy ý domain không liên quan hoặc public suffix như `com`.

Khi không có yêu cầu chia sẻ cookie giữa các subdomain, **ưu tiên bỏ `Domain`** thay vì khai báo phạm vi rộng như `Domain=example.test`. Cookies không được giới hạn theo **port**; ví dụ `localhost:8080` và `localhost:9091` vẫn dùng cùng tên host cho phạm vi domain. Vì thế, test hai dịch vụ trên hai port cùng `localhost` không mô phỏng đầy đủ việc đổi domain trong production.

### 3.2. Path: browser so với đường dẫn được gateway rewrite

Giả sử:

~~~text
Client gọi:        /api/auth/login
Gateway StripPrefix=1
Backend nhận:      /auth/login

Request kế tiếp bên client: /api/auth/profile
Path cookie cần khớp:      /api/auth/profile
~~~

Nếu backend trả:

~~~http
Set-Cookie: sid=abc; Path=/auth; Secure; HttpOnly; SameSite=Lax
~~~

thì cookie có thể được trình duyệt lưu nhưng **không được gửi** khi client gọi `/api/auth/profile`: path công khai không nằm dưới `/auth`. Cấu hình đúng cho yêu cầu ở ví dụ này có thể là:

~~~http
Set-Cookie: sid=abc; Path=/api/auth; Secure; HttpOnly; SameSite=Lax
~~~

Hoặc `Path=/` nếu phiên thực sự cần trên toàn bộ host, nhưng phạm vi rộng có thể tăng khả năng xảy ra xung đột giữa các ứng dụng. **`Path` là quy tắc gửi cookie, không phải ranh giới bảo mật mạnh**; cookie cùng host có thể bị tác động bởi ứng dụng hoặc script không đáng tin tùy bối cảnh.

Nếu không đặt `Path`, trình duyệt dùng **default path suy ra từ URL công khai của request đã nhận `Set-Cookie`**, không dùng path nội bộ mà backend nhìn thấy. Giá trị mặc định không nhất thiết là `/`, nên cookie phiên nên đặt path một cách có chủ ý.

### 3.3. Secure, TLS termination và SameSite

Proxy thường kết thúc TLS ở cạnh ngoài:

~~~text
Browser -- HTTPS --> Load Balancer -- HTTP --> Gateway -- HTTP --> auth-service
          ^ browser đánh giá Secure ở chặng này
~~~

Backend có thể gửi `Set-Cookie: ...; Secure` dù chính nó nhận HTTP nội bộ: trình duyệt chỉ thấy response công khai qua HTTPS. **`Secure` vẫn cần thiết** cho cookie đăng nhập. Nếu browser thực sự gọi một URL HTTP trên Internet, không thể giả làm HTTPS bằng cách gửi `X-Forwarded-Proto: https` để cookie tự trở nên an toàn.

TLS public không bảo vệ mặc định các chặng nội bộ; nếu hạ tầng yêu cầu mã hóa đầu-cuối, cấu hình TLS/mTLS phù hợp cho các hop giữa proxy, gateway và backend.

`SameSite` phân loại theo **site**, không hoàn toàn giống khái niệm **origin** của CORS. Hai origin khác port vẫn có thể cùng site; hai hostname khác có thể cùng registrable domain, nhưng scheme còn ảnh hưởng theo mô hình schemeful SameSite. Khi frontend gọi API cross-origin qua `fetch`, vẫn phải xử lý CORS/credentials, kể cả khi cookie không phải third-party cookie theo cách browser phân loại.

### 3.4. Thời hạn và xóa cookie

Để xóa cookie, trả `Set-Cookie` có cùng tên, **Path** và **Domain** tương ứng với cookie cần xóa; đặt `Max-Age=0`:

~~~http
Set-Cookie: sid=; Path=/api/auth; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Nếu lúc đăng nhập tạo `Path=/api/auth` nhưng lúc logout chỉ xóa `Path=/`, cookie cũ vẫn có thể tồn tại vì hai scope không trùng nhau. Khi dùng nhiều cookie trùng tên trên các path khác nhau, cần xem rõ từng bản ghi cookie trong trình duyệt. Ngoài xóa client cookie, hệ thống xác thực còn phải vô hiệu hóa session/token phía server nếu yêu cầu bảo mật đòi hỏi.

## 4. Prefix cookie và chính sách bảo vệ phiên

Browser hỗ trợ một số prefix giúp ràng buộc thuộc tính:

| Tên cookie | Ràng buộc nổi bật | Khi dùng |
| --- | --- | --- |
| `__Secure-sid` | Phải có `Secure` và được thiết lập qua ngữ cảnh HTTPS hợp lệ | Phiên bảo mật khi vẫn cần chọn Path hoặc Domain cụ thể |
| `__Host-sid` | `Secure`, **`Path=/`**, **không có `Domain`**, được thiết lập qua ngữ cảnh HTTPS hợp lệ | Cookie host-only, không cho subdomain tự thiết lập phạm vi chia sẻ |
| `__Http-sid` | `Secure` và `HttpOnly` trong browser hỗ trợ prefix này | Ràng buộc cookie phải được thiết lập qua response `Set-Cookie` |
| `__Host-Http-sid` | Kết hợp yêu cầu của `__Host-` và `__Http-` | Trường hợp cần ràng buộc chặt, tùy hỗ trợ browser |

Ví dụ cho phiên tại host công khai:

~~~http
Set-Cookie: __Host-sid=opaque; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1200
~~~

Không nên sao chép `__Host-sid` rồi đặt `Path=/api/auth`: trình duyệt tuân thủ prefix sẽ từ chối vì không phải `Path=/`. Prefix cũng **không thay thế xác thực**, CSRF protection, chống XSS, bảo vệ token phía server hay chính sách CORS. Các ràng buộc phụ thuộc browser có hỗ trợ prefix đó.

## 5. Spring Cloud Gateway tác động đến cookie như thế nào?

Spring Cloud Gateway Server WebFlux chuyển tiếp request và response HTTP qua route đã chọn. Các filter có thể điều chỉnh path, header hoặc status, nhưng cần phân biệt điều gì **thực sự được sửa**.

| Thành phần/cơ chế | Ảnh hưởng đến cookie |
| --- | --- |
| `Path` predicate, `Host` predicate | Quyết định **route nào** được chọn; bản thân predicate không đặt cookie |
| `StripPrefix`, `SetPath`, `RewritePath` | Sửa **request path gửi xuống backend**; thông thường không tự sửa `Path=...` trong `Set-Cookie` response |
| `AddRequestHeader`, `SetRequestHeader` | Có thể thay request header đến backend; phải tránh ghi đè hoặc làm sai `Cookie` của người dùng |
| `AddResponseHeader` | Bổ sung response header; dùng tốt với header chẩn đoán như `X-Gateway-Route` |
| `SetResponseHeader` | **Thay thế toàn bộ giá trị** của header được chỉ định; cực kỳ nguy hiểm nếu tên header là `Set-Cookie` |
| `RemoveResponseHeader` | Xóa response header; đặt `RemoveResponseHeader=Set-Cookie` có thể phá phiên đăng nhập |
| `RewriteResponseHeader` | Thay chuỗi response header bằng regex; sửa `Set-Cookie` bừa bãi dễ làm hỏng nhiều cookie, `Expires` hoặc attributes |
| `DedupeResponseHeader` | Loại trùng lặp header thường dùng cho CORS; không nên áp dụng mù quáng lên `Set-Cookie` |
| `RedirectTo`, xử lý `Location` | Có thể khiến client truy cập một URL/host khác; thay đổi scope cookie dùng trong request tiếp theo |
| `SaveSession` | Yêu cầu `WebSession` lưu trước khi forward, hữu ích với Spring Session; **không tự động sửa `Path`/`Domain` của cookie do backend phát hành** |

Theo tài liệu Spring Cloud Gateway, `SetResponseHeader` **thay tất cả giá trị** mang tên đã chọn. Nếu backend trả hai header `Set-Cookie` khác nhau, việc cấu hình `SetResponseHeader=Set-Cookie, ...` có thể xóa cả hai rồi chỉ còn giá trị mới. `DedupeResponseHeader` được thiết kế cho các trường hợp như header CORS trùng lặp giữa gateway và backend; hai cookie cùng tên nhưng khác path/domain có thể là hai cookie **có ý nghĩa riêng**.

Vì vậy, lựa chọn dễ kiểm soát nhất là để **service phát hành cookie đúng domain/path công khai ngay từ đầu**. Nếu bắt buộc hỗ trợ backend legacy trả cookie có `Path`/`Domain` nội bộ, hãy thiết kế lớp biến đổi có kiểm tra cấu trúc từng cookie, bảo toàn các trường `Set-Cookie` độc lập, giới hạn host/path cho phép và kiểm thử đầy đủ; không dùng regex tổng quát để thay mọi giá trị header.

### 5.1. Response commit: sửa Set-Cookie phải đúng thời điểm

Trong WebFlux, `ServerHttpResponse` cho phép thêm cookie bằng `response.addCookie(ResponseCookie)` trước khi response được **commit**. Khi headers đã được gửi xuống client, việc thêm/sửa cookie không còn đáng tin cậy. Nếu viết `GlobalFilter` xử lý response, cần đảm bảo thao tác xảy ra trong giai đoạn phù hợp, có thể đăng ký `beforeCommit(...)` khi thật sự cần, và tránh `block()`/`subscribe()` tự phát trong chuỗi reactive.

Với cơ chế login thông thường, đặt cookie ở **backend auth service hoặc thành phần Spring Security chịu trách nhiệm session** thường rõ ràng hơn việc tạo cookie ở một filter chỉ phục vụ routing.

## 6. Cấu hình route để quan sát cookie qua Gateway

Giả sử gateway chạy `localhost:8080` và auth-service thử nghiệm ở `localhost:9091`. Route sau chỉ bỏ prefix trên đường đến backend; không tự sửa `Set-Cookie`:

### 6.1. Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: cookie-gateway-lab
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: auth-cookie-lab
              uri: http://localhost:9091
              predicates:
                - Path=/api/auth/**
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Gateway-Lab, auth-cookie-lab
~~~

### 6.2. Gateway Server WebFlux 4.2.x và 4.3.x

Với những dòng Gateway WebFlux dùng tiền tố cũ cho danh sách routes, chuyển cùng cấu hình vào `spring.cloud.gateway.routes`:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      routes:
        - id: auth-cookie-lab
          uri: http://localhost:9091
          predicates:
            - Path=/api/auth/**
          filters:
            - StripPrefix=1
            - AddResponseHeader=X-Gateway-Lab, auth-cookie-lab
~~~

Chỉ dùng **namespace đúng với phiên bản** và starter WebFlux của dự án; các phiên bản mới dùng starter thường mang tên `spring-cloud-starter-gateway-server-webflux`, trong khi nhiều dòng trước dùng `spring-cloud-starter-gateway`. Cấu hình trên dùng URI tĩnh để tách lỗi cookie khỏi lỗi service discovery. Khi đổi sang `lb://auth-service`, cần bổ sung LoadBalancer và nguồn khám phá instance phù hợp.

Trong bài này, `X-Gateway-Lab` chỉ là dấu hiệu route đã chạy; nó không chứng minh cookie được browser lưu. Phải kiểm tra **`Set-Cookie` ở response** và **`Cookie` ở request kế tiếp**.

## 7. Thực hành: auth-service giả lập đặt và nhận cookie

Tạo ứng dụng Spring Boot WebFlux độc lập có dependency `spring-boot-starter-webflux`. Mục tiêu chỉ kiểm thử hai chiều HTTP, **không thực hiện xác thực thật**.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 9091

spring:
  application:
    name: cookie-echo-service
~~~

Class khởi chạy:

~~~java
package demo.cookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieApplication.class, args);
    }
}
~~~

Controller đặt cookie với **`Path=/api/auth` là đường dẫn công khai**, dù endpoint backend thực tế là `/auth/login`:

~~~java
package demo.cookie;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/auth")
public class CookieController {

    @PostMapping("/login")
    public Map<String, String> login(ServerHttpResponse response) {
        // Cookie demo; KHÔNG phải một phiên đã xác thực.
        ResponseCookie cookie = ResponseCookie.from(
                        "lab_sid", UUID.randomUUID().toString())
                .path("/api/auth")       // Path mà client nhìn thấy
                .httpOnly(true)
                .secure(false)            // Chỉ dành cho HTTP localhost lab
                .sameSite("Lax")
                .maxAge(Duration.ofMinutes(10))
                .build();

        response.addCookie(cookie);
        return Map.of("result", "demo-cookie-issued");
    }

    @GetMapping("/profile")
    public Map<String, Object> profile(
            @CookieValue(name = "lab_sid", required = false)
                    String cookie) {
        // Chỉ xác nhận client có gửi cookie; KHÔNG xác thực token.
        return Map.of("cookieReceived", cookie != null);
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(ServerHttpResponse response) {
        ResponseCookie expired = ResponseCookie.from("lab_sid", "")
                .path("/api/auth")       // Phải khớp Path lúc tạo
                .httpOnly(true)
                .secure(false)            // Đồng bộ cấu hình HTTP lab
                .sameSite("Lax")
                .maxAge(Duration.ZERO)
                .build();

        response.addCookie(expired);
        return ResponseEntity.status(HttpStatus.NO_CONTENT).build();
    }
}
~~~

Code cố tình dùng `secure(false)` vì bài lab trên `http://localhost`. **Không dùng cấu hình đó cho session thật trên Internet.** Khi triển khai sau HTTPS, đặt `secure(true)`, áp dụng chính sách session/token ở backend, bật CSRF protection khi cần và cấu hình cookie scope phù hợp với host/path công khai. Không log giá trị `lab_sid`.

### 7.1. Khởi động từng tiến trình

Chạy backend và gateway trong **hai terminal riêng**, mỗi lệnh tại thư mục Maven tương ứng:

~~~bash
# Terminal backend:
./mvnw spring-boot:run

# Terminal gateway:
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run` hoặc `mvn spring-boot:run`. Ví dụ giả định dependencies Spring Boot và Spring Cloud BOM tương thích; các kết quả phía dưới là **kỳ vọng**, không phải kết quả đã được đo trên hệ thống của người đọc.

### 7.2. Login: quan sát Set-Cookie và lưu cookie jar

~~~bash
curl -i -X POST "http://localhost:8080/api/auth/login" \
  -c cookie-jar.txt
~~~

Response có thể tương tự:

~~~http
HTTP/1.1 200 OK
X-Gateway-Lab: auth-cookie-lab
Set-Cookie: lab_sid=<giá-trị-ngẫu-nhiên>; Path=/api/auth; Max-Age=600; HttpOnly; SameSite=Lax
Content-Type: application/json

{"result":"demo-cookie-issued"}
~~~

`curl -c cookie-jar.txt` lưu cookie để sử dụng ở request tiếp theo. Hãy xem dòng `Set-Cookie` riêng biệt; không dựa duy nhất vào status 200. File cookie jar có thể chứa giá trị phiên nhạy cảm trong ứng dụng thật: **không commit vào Git hoặc chia sẻ file đó**.

### 7.3. Profile: kiểm tra request Cookie có quay lại backend

~~~bash
curl -i "http://localhost:8080/api/auth/profile" \
  -b cookie-jar.txt
~~~

Response kỳ vọng:

~~~http
HTTP/1.1 200 OK
X-Gateway-Lab: auth-cookie-lab
Content-Type: application/json

{"cookieReceived":true}
~~~

Lần này `curl` gửi header `Cookie: lab_sid=...` trên request đến Gateway; Gateway chuyển tiếp xuống `/auth/profile`, và controller xác nhận cookie đã có mặt. Thử gọi lại **không có `-b cookie-jar.txt`** để thấy `cookieReceived=false`, miễn là không có cookie khác được gửi.

Trong lab này, cookie được chọn theo path công khai `/api/auth/profile`. Nếu thay `.path("/api/auth")` bằng `.path("/auth")` trong controller login rồi chạy lại, cookie có thể vẫn được lưu nhưng sẽ không được gửi cho request công khai `/api/auth/profile`. Đây là lỗi điển hình khi backend không biết gateway đã thay path.

### 7.4. Logout: Max-Age=0 cùng phạm vi

~~~bash
curl -i -X POST "http://localhost:8080/api/auth/logout" \
  -b cookie-jar.txt \
  -c cookie-jar.txt
~~~

Kỳ vọng nhận **204 No Content** và header `Set-Cookie` xóa `lab_sid` với `Path=/api/auth; Max-Age=0`. Gọi `/api/auth/profile` bằng cookie jar đã cập nhật sẽ trả `cookieReceived=false`. Đây là thao tác xóa cookie phía client; ứng dụng xác thực thật còn phải xử lý thu hồi session/token.

### 7.5. Vì sao backend direct test có thể gây nhầm?

Nếu dùng cùng host `localhost` với hai port khác nhau, trình duyệt/cURL không dùng **port** để quyết định scope cookie. Một cookie được tạo khi gọi `localhost:9091` có thể ảnh hưởng các request sang `localhost:8080` nếu path phù hợp. Vì vậy, khi test direct backend và test qua gateway, nên dùng cookie jar riêng hoặc xóa trạng thái cũ để tránh kết luận sai.

## 8. Cấu hình production: Session cookie sau TLS reverse proxy

Giả sử client thật gọi:

~~~text
https://api.example.test/api/auth/login
        │ TLS
        ▼
Load Balancer / Ingress (TLS termination)
        │ HTTP hoặc HTTPS nội bộ
        ▼
Spring Cloud Gateway
        │ route /api/auth/** + StripPrefix=1
        ▼
auth-service:8080/auth/login
~~~

Nếu session chỉ được dùng trên host `api.example.test`, có thể chọn cookie:

~~~http
Set-Cookie: __Host-sid=opaque-session-token; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1200
~~~

`__Host-` yêu cầu `Path=/` và không có `Domain`; trường hợp chỉ muốn path hẹp `/api/auth` thì dùng tên cookie khác, chẳng hạn `__Secure-sid`, và đảm bảo Secure/HTTPS. Không đặt `Domain=auth-service` vì backend nội bộ không phải host mà browser giao tiếp.

### 8.1. Backend xác định scheme HTTPS thế nào?

Khi TLS bị kết thúc trước backend, `getURI()` hoặc thông tin kết nối nội bộ có thể hiện `http` dù client gọi `https`. Nếu backend sinh redirect hoặc absolute URL, nó cần thông tin proxy tin cậy về host/scheme, chẳng hạn `Forwarded` hoặc `X-Forwarded-Proto`/`Host` đã được **edge proxy xác minh**.

Tuy nhiên, `X-Forwarded-Proto: https` do client tự gửi không chứng minh request đã dùng TLS. Phải cấu hình ingress để xóa hoặc chuẩn hóa forwarded headers từ Internet, giới hạn nguồn kết nối gateway và kiểm tra chính sách của WebFlux/forwarded header theo phiên bản. `Secure` được đánh giá theo kết nối browser với URL công khai, không phải bằng một header bất kỳ.

### 8.2. Có nên rewrite Domain/Path ở gateway?

**Ưu tiên backend biết hợp đồng public cookie** và trả đúng thuộc tính. Nếu backend cũ luôn sinh:

~~~http
Set-Cookie: sid=abc; Domain=auth.internal; Path=/auth; HttpOnly
~~~

trong khi client truy cập `https://api.example.test/api/auth/login`, cần thiết kế phương án chuyển đổi rõ ràng. Gateway có filter `RewriteResponseHeader` dựa trên regex, nhưng với `Set-Cookie` cần hết sức thận trọng:

- Một response có thể có **nhiều dòng** `Set-Cookie` khác nhau.
- Dòng cookie có thể chứa `Expires=Wed, 21 Oct ...` với dấu phẩy.
- Cookie có thể có `Domain`/`Path` khác nhau, prefix và attribute tùy chọn.
- Thay đổi một cách tổng quát có thể làm hỏng session hoặc mở rộng phạm vi cookie trái chính sách.

Trong hệ thống thực tế, dùng **cơ chế rewrite cookie được proxy hỗ trợ một cách rõ ràng** hoặc filter tùy biến có parser/serializer đúng chuẩn, áp dụng chỉ cho route và cookie đã kiểm soát. Không dùng `SetResponseHeader=Set-Cookie,...` để thay toàn bộ cookie response. Thử nghiệm cần bao gồm nhiều cookie, logout, redirect và cookie attributes mới.

### 8.3. Redirect sau đăng nhập

Đăng nhập có thể trả `302` hoặc `303` với hai header:

~~~http
HTTP/1.1 303 See Other
Location: /app/home
Set-Cookie: sid=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Client có thể lưu cookie từ response redirect rồi gửi ở request tiếp theo nếu scope cho phép. Khi debug, `curl -i` xem từng response; `curl -L` đi theo redirect nên có thể che mất response trung gian nếu không bật hiển thị headers. Nếu backend trả `Location: http://auth-service:8080/...`, cần sửa cách backend xây URL công khai hoặc dùng filter phù hợp để rewrite `Location`. Việc sửa `Location` **không tự sửa cookie Domain/Path**.

### 8.4. Nhiều proxy thêm cookie riêng

Load balancer, CDN hoặc ingress đôi khi cũng phát hành cookie cho affinity/sticky session. Cookie này có thể cùng tồn tại với cookie đăng nhập, nhưng cần khác tên và phạm vi để tránh xung đột. Sticky session không thay thế xác thực; khi dùng nhiều instance backend, session state vẫn phải được chia sẻ hoặc mô hình xác thực phải cho phép request được phục vụ ở instance khác.

## 9. Frontend khác origin: CORS, credentials và SameSite

Giả sử frontend ở `https://app.example.test` gọi API tại `https://api.example.test` bằng JavaScript:

~~~javascript
const response = await fetch("https://api.example.test/api/auth/profile", {
  method: "GET",
  credentials: "include"
});
~~~

Hai URL là **khác origin** vì hostname khác, dù có thể cùng site theo quy tắc SameSite. Để browser cho phép request/response dùng credentials qua CORS, API cần CORS policy phù hợp: `Access-Control-Allow-Origin` phải khớp origin được cho phép (không dùng `*` với credentials), `Access-Control-Allow-Credentials: true` khi cần, và xử lý preflight nếu request kích hoạt preflight.

`Set-Cookie` là response header mà JavaScript trình duyệt **không thể đọc trực tiếp** qua `response.headers.get("set-cookie")`. Hãy quan sát tại **DevTools → Network/Storage** hoặc dùng `curl -i`. Browser cũng có thể bỏ qua `Set-Cookie` trong fetch/XHR CORS nếu cấu hình credentials không phù hợp.

Khi frontend và API thật sự **cross-site**, `SameSite=Lax` hoặc `Strict` có thể chặn cookie trong nhiều request cross-site. `SameSite=None; Secure` là một lựa chọn kỹ thuật nhưng còn phụ thuộc hạn chế third-party cookies và chính sách riêng tư của từng browser. Không dùng `SameSite=None` chỉ để “sửa lỗi login” khi chưa hiểu ngữ cảnh, CSRF và CORS.

Đặc biệt, cookie được browser tự động gửi kèm có thể mở đường cho **CSRF**. `HttpOnly` giảm khả năng JavaScript đọc cookie nhưng **không chặn request gây tác dụng phụ**. Với ứng dụng cookie-based auth, cần CSRF token hoặc biện pháp chống CSRF phù hợp với mô hình request và chính sách SameSite.

## 10. Các triệu chứng thường gặp và cách khoanh vùng

| Triệu chứng | Nguyên nhân đáng kiểm tra | Bước đối chiếu |
| --- | --- | --- |
| Login 200 nhưng browser không lưu cookie | `Domain` không hợp lệ, `Secure` không phù hợp URL, `SameSite=None` thiếu Secure, chính sách third-party cookie | DevTools Network/Storage và response `Set-Cookie` |
| Browser lưu cookie nhưng không gửi request sau | `Path` không khớp URL công khai, Domain sai, cookie hết hạn, SameSite/credentials chặn | So sánh browser request path với cookie scope |
| Login hoạt động direct backend nhưng lỗi qua gateway | Backend đặt `Path=/auth` trong khi client gọi `/api/auth/...` | So sánh header `Set-Cookie` và path trước/sau `StripPrefix` |
| Chỉ một cookie còn sau khi đi qua gateway | Filter `SetResponseHeader=Set-Cookie` hoặc cơ chế proxy gộp/xóa header | Kiểm tra **từng** header `Set-Cookie` ở backend và client |
| Logout trả 204 nhưng vẫn đăng nhập | Xóa cookie khác `Path`/`Domain`, hoặc server session chưa bị vô hiệu hóa | Đối chiếu key cookie và session store |
| Cookie xuất hiện ở HTTP nội bộ nhưng browser không chấp nhận | Browser thấy URL công khai HTTP hoặc Secure/SameSite không hợp lệ | Kiểm tra HTTPS public và TLS termination |
| Có 302 nhưng điều hướng sai host | Backend sinh `Location` từ hostname nội bộ hoặc forwarded header không tin cậy | Kiểm tra `Location`, `Host`, `Forwarded`/`X-Forwarded-*` |
| 401/403 dù có Cookie header | Cookie không phải session hợp lệ, token hết hạn, backend từ chối quyền | Xem security logs/trace và trạng thái phiên phía server |
| API trả 429 trước khi login xử lý | Rate limiter ở gateway chặn request | Phân biệt status gateway với response backend và retry policy |
| Nhiều instance cho kết quả phiên khác nhau | Session lưu cục bộ, affinity không nhất quán hoặc khóa ký khác nhau | Kiểm tra session store/shared key và route instance được chọn |

Một quy trình điều tra nhanh:

1. **Client → Gateway:** kiểm tra URL công khai, HTTPS, status và response `Set-Cookie`.
2. **Gateway → backend:** kiểm tra route/predicate, path đã rewrite và các filter response có sửa/xóa `Set-Cookie` hay không.
3. **Browser lưu cookie:** kiểm tra Domain, Path, Secure, SameSite, Max-Age và lý do browser báo rejected.
4. **Request sau:** xem client có gửi `Cookie` tới URL công khai không; nếu có, gateway có chuyển cookie xuống backend không.
5. **Backend/auth:** kiểm tra token/session có hợp lệ và đủ quyền không; đừng đồng nhất “cookie tồn tại” với “người dùng đã xác thực”.
6. **Mở rộng:** khi dùng `lb://`, retry, circuit breaker hoặc caching, kiểm tra instance đích, số lần request được gửi và bất kỳ phản hồi nào làm thay đổi cookie.

## 11. Các lưu ý khi kết hợp resilience, cache và quan sát

**Retry và đăng nhập:** Một request tạo session hoặc refresh token có tác dụng phụ. Retry không có idempotency key/logic chống lặp có thể tạo nhiều session hoặc nhiều `Set-Cookie` không như dự kiến. Phải xác định điều kiện retry theo method, status, khả năng đọc lại body và tính an toàn nghiệp vụ. Circuit breaker/fallback cũng không nên tự tạo “phiên giả” khi auth-service đang lỗi.

**Cache và CDN:** Response chứa session cookie hoặc dữ liệu người dùng không nên bị chia sẻ giữa các client qua cache dùng chung. Với endpoint đăng nhập hoặc trả thông tin nhạy cảm, cân nhắc `Cache-Control: no-store` và cấu hình CDN/reverse proxy phù hợp. Đừng cho rằng có `Set-Cookie` thì mọi proxy tự động không cache response trong mọi trường hợp.

**TLS:** bảo vệ chặng browser → gateway và cân nhắc HTTPS/mTLS cho các chặng nội bộ theo threat model; không đặt giá trị nhạy cảm trong `Cookie` nếu cơ chế vận chuyển/ghi log chưa được kiểm soát.

**Tracing và logs:** ghi route ID, method, **path công khai**, path chuyển tiếp, status, latency, trace ID và kết quả chẩn đoán cookie ở mức “có/không” khi phù hợp. Không ghi giá trị header `Cookie` hoặc `Set-Cookie` chứa token phiên vào access log, metric tags, tracing attributes hay exception messages.

**Phân quyền:** Gateway có thể xác thực một lớp chung, nhưng backend vẫn cần phân quyền theo tài nguyên. Header `X-User-Id` do client tự gửi và cookie chưa kiểm tra chữ ký/session không phải bằng chứng danh tính. Các predicate theo path/host/cookie chỉ chọn route; chúng không thay thế security policy.

## 12. Bảng kiểm trước khi triển khai

- [ ] Cookie được tạo cho **URL công khai của browser**, đã xác định rõ host và path cần gửi lại.
- [ ] `Domain` được bỏ trống nếu không cần chia sẻ subdomain; không chứa tên service nội bộ.
- [ ] Cookie phiên thật dùng `Secure` qua HTTPS, `HttpOnly` khi JavaScript không cần đọc; `SameSite` và thời hạn phù hợp.
- [ ] Không dùng prefix `__Host-` với `Path` khác `/` hoặc với `Domain`.
- [ ] Nếu có `StripPrefix`, `RewritePath` hay `SetPath`, đã đối chiếu scope cookie với **path ngoài**.
- [ ] Response nhiều cookie vẫn giữ **nhiều dòng Set-Cookie** riêng; không gộp, dedupe hoặc overwrite vô ý.
- [ ] Logout trả cookie hết hạn với cùng tên/Path/Domain và vô hiệu hóa session phía server khi cần.
- [ ] Ingress/CDN thực hiện TLS termination và xử lý forwarded header theo ranh giới tin cậy; không tin header giả từ client.
- [ ] Với frontend cross-origin, đã kiểm tra CORS, credentials, SameSite, chính sách browser và CSRF.
- [ ] Tài liệu/test tách rõ HTTP `localhost` lab khỏi cấu hình HTTPS production.
- [ ] Kiểm thử login, profile, logout, 302/303, 401, 403, 429 và trường hợp backend lỗi/chuyển instance.
- [ ] Không cache chia sẻ response nhạy cảm và không ghi token phiên vào log/trace.

## 13. Tài liệu tham khảo

1. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): các thuộc tính Domain, Path, Secure, HttpOnly, SameSite, Max-Age, Expires, Partitioned và cookie prefixes.
2. [MDN — Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cookie): request Cookie, nhiều cookie cùng tên và phạm vi gửi cookie.
3. [MDN — Secure Cookie Configuration](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Cookies): nguyên tắc giảm phạm vi và bảo vệ session cookies.
4. [Spring Cloud Gateway Server WebFlux — SetResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/setresponseheader-factory.html): filter thay các giá trị header response cùng tên.
5. [Spring Cloud Gateway Server WebFlux — DedupeResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/deduperesponseheader-factory.html): loại trùng lặp header, thường dùng với CORS.
6. [Spring Cloud Gateway Server WebFlux — RewriteResponseHeader](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/rewriteresponseheader-factory.html): rewrite response header dựa trên regex.
7. [Spring Framework — ResponseCookie](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html): xây dựng và phát hành cookie trên server.

**Ghi nhớ:** `Set-Cookie` thuộc **response** và `Cookie` thuộc **request tiếp theo**; trình duyệt quyết định phạm vi theo **host/path công khai**, không theo địa chỉ backend sau Gateway. Hãy đặt Domain/Path phù hợp với URL bên ngoài, bảo vệ cookie phiên bằng HTTPS/Secure/HttpOnly/SameSite, giữ các header `Set-Cookie` độc lập và kiểm chứng thực tế trước khi triển khai proxy cho microservices.
