# Chuẩn hóa đường dẫn, HttpFirewall và giới hạn dữ liệu đầu vào

> Phạm vi: Spring Security cho **ứng dụng Servlet/Spring MVC** (Spring Boot 3.x, Java 17+). Bài học thuộc chủ đề **Bảo vệ trình duyệt**, tập trung vào cách đường dẫn HTTP được diễn giải, cơ chế chặn request đáng ngờ trước khi phân quyền và giới hạn đầu vào ở đúng tầng.

## 1. Vì sao phải quan tâm đến hình dạng request?

Khi lập trình viên bảo vệ `/admin/**` nhưng client gửi một biến thể như `/admin/../public`, `/admin//users`, `/admin;v=1/users` hay `/admin%2Fusers`, các thành phần trên đường đi có thể *không cùng hiểu một đường dẫn*:

- Trình duyệt hoặc client có thể tự chuẩn hóa URI trước khi gửi.
- Reverse proxy, WAF, load balancer và servlet container có thể giải mã hoặc từ chối các ký tự khác nhau.
- Bộ so khớp route, bộ so khớp quy tắc bảo mật và controller có thể quan sát các biểu diễn path khác nhau.
- Kẻ tấn công cố tình khai thác sự khác nhau ấy để đi vào route không mong đợi, vượt qua phép kiểm tra URL hoặc gây lỗi xử lý.

Mục tiêu là **kiểm tra request trước bước phân quyền**, chỉ cho phép các dạng path được hỗ trợ nhất quán, đồng thời **giới hạn kích thước và cấu trúc đầu vào** để giảm rủi ro lạm dụng tài nguyên. `HttpFirewall` giúp chặn một số request đáng ngờ; nó không thay thế kiểm tra quyền, xác thực, kiểm tra dữ liệu nghiệp vụ hay giới hạn kích thước của HTTP server.

### Luồng xử lý cần hình dung

```text
Client
  → CDN / reverse proxy / gateway
  → HTTP connector + servlet container (parse request, áp giới hạn HTTP)
  → Servlet FilterChainProxy của Spring Security
       → HttpFirewall kiểm tra / bao bọc request
       → SecurityFilterChain: authentication, CSRF, authorization, ...
  → DispatcherServlet → Controller → Service
  → Response
```

Một request bị proxy/container từ chối có thể **chưa từng đến Spring Security**. Request bị `StrictHttpFirewall` từ chối có thể **chưa từng đến controller**. Vì vậy, khi quan sát mã trạng thái lỗi cần xác định tầng chặn thực tế.

## 2. Hiểu đúng “chuẩn hóa đường dẫn”

URL có các thành phần khác nhau. Trong `https://example.test/app/api/products/42?sort=asc`, `/app` có thể là `contextPath`, `/api/products/42` là phần path ứng dụng dùng để định tuyến, còn `sort=asc` là query. `servletPath` và `pathInfo` do servlet container phân rã; `queryString` **không phải** phần path để so khớp quy tắc route.

“Chuẩn hóa” là đưa những biểu diễn được chấp nhận về cách hiểu nhất quán; “kiểm tra canonical form” là **từ chối** biểu diễn nhập nhằng thay vì tự sửa chúng. Trong ranh giới an ninh, việc cố gắng sửa path sau khi đã phân quyền có thể tạo ra cách diễn giải khác với cách được kiểm tra.

| Biến thể path do client thử gửi | Rủi ro / điểm cần hiểu |
| --- | --- |
| `/api/../admin` hoặc `/api/./users` | Các đoạn `..`, `.` có thể thay đổi path sau chuẩn hóa. |
| `/api//users` | Dấu gạch chéo lặp có thể được xử lý khác nhau giữa các tầng. |
| `/api/%2e%2e/admin` | Dấu chấm được percent-encode; hành vi tùy tầng giải mã và cấu hình. |
| `/api%2Fadmin` | `%2F` là slash được mã hóa, có thể tạo khác biệt khi tách segment. |
| `/api%5Cadmin` | Backslash có thể bị xem là dấu phân cách ở một số tầng. |
| `/api;v=1/admin` | Dấu chấm phẩy/path parameter có thể ảnh hưởng matcher và matrix variable. |
| `/api/%252e%252e/admin` | Nhiều lần decode liên tiếp có thể khiến chuỗi đổi nghĩa. |

Bảng này mô tả **rủi ro**, không cam kết một mã HTTP cố định cho từng chuỗi. Ký tự có thể bị từ chối ở gateway, container hoặc firewall, và client có thể tự sửa URI trước khi gửi. **Không mặc định percent-decode hai lần**; mỗi tầng phải thống nhất chính sách đối với path và encoding.

**Phân biệt quan trọng:** `%2F` nằm trong *path* khác với chuỗi ký tự `%2F` trong *giá trị query hoặc JSON body*. Không suy từ chính sách chặn path sang việc cấm tất cả dữ liệu hợp lệ chứa ký tự phần trăm.

## 3. `HttpFirewall` nằm ở đâu và làm gì?

Trong ứng dụng Servlet, Spring Security dùng `FilterChainProxy` để điều phối các `SecurityFilterChain`. `HttpFirewall` của `FilterChainProxy` kiểm tra request và có thể cung cấp một request wrapper để bộ so khớp bảo mật nhìn thấy đường dẫn được xử lý nhất quán. Chiến lược mặc định là `StrictHttpFirewall`.

`StrictHttpFirewall` thường từ chối:

1. Path không ở dạng chuẩn hoặc có biến thể dễ gây lệch phép so khớp.
2. Các ký tự/path encoding nguy hiểm như semicolon, backslash, URL-encoded slash, encoded percent hoặc NUL theo quy tắc mặc định.
3. HTTP method không thuộc danh sách cho phép; mặc định cho phép `DELETE`, `GET`, `HEAD`, `OPTIONS`, `PATCH`, `POST`, `PUT`.
4. Header name, header value và parameter name chứa ký tự điều khiển hay ký tự không được định nghĩa theo quy tắc mặc định.
5. Host hoặc parameter value vi phạm predicate **nếu ứng dụng đã cấu hình thêm điều kiện**. Mặc định không đồng nghĩa với kiểm tra đầy đủ mọi giá trị parameter hoặc allowlist host.

Khi kiểm tra thất bại, `StrictHttpFirewall` ném `RequestRejectedException`. Trong cấu hình thông thường, request được trả về **400 Bad Request** qua handler tương ứng, nhưng proxy/container có thể chặn sớm hơn với phản hồi khác. Đây không phải `AccessDeniedException` do người dùng thiếu quyền; **400 và 403 có ý nghĩa khác nhau**.

Spring Security khuyến nghị từ chối path không chuẩn thay vì tự viết “bộ normalize” để sửa mọi URL. Nếu cần hỗ trợ một cấu trúc đặc biệt, hãy xác định yêu cầu giao thức, cách container parse và ảnh hưởng bảo mật trước khi nới một quy tắc.

### Ba tầng bảo vệ có trách nhiệm khác nhau

| Tầng | Câu hỏi cần trả lời | Công cụ thường dùng |
| --- | --- | --- |
| HTTP/gateway/container | Request có hợp lệ, đủ nhỏ và parse an toàn không? | HTTP parser, proxy limits, Tomcat/Jetty settings |
| Firewall/security | Path/method/header có đáng tin và requester có quyền tới resource không? | `StrictHttpFirewall`, `SecurityFilterChain`, `@PreAuthorize` |
| Input/business | Dữ liệu có đúng kiểu, độ dài, định dạng và được phép dùng không? | Jakarta Bean Validation, kiểm tra nghiệp vụ, truy vấn tham số hóa |

Không dùng một regex trong controller làm giải pháp thay thế cả ba tầng.

## 4. Cấu hình Spring Security an toàn

Với Spring Boot 3.x/Spring Security 6.x, nên bắt đầu từ `StrictHttpFirewall` mặc định. Chỉ tùy chỉnh khi yêu cầu rõ ràng. Ví dụ sau minh họa một ứng dụng chỉ chấp nhận các method `GET`, `HEAD`, `POST`, `OPTIONS` ở tầng firewall, đồng thời mặc định yêu cầu xác thực đối với request khác `/public/**`.

```java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.firewall.StrictHttpFirewall;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    StrictHttpFirewall httpFirewall() {
        StrictHttpFirewall firewall = new StrictHttpFirewall();
        firewall.setAllowedHttpMethods(
            List.of("GET", "HEAD", "POST", "OPTIONS")
        );
        return firewall;
    }
}
```

Đây là **mã cấu hình trong một dự án Spring Boot có dependency Spring Security**, không phải tệp Java độc lập để chạy bằng `java SecurityConfig`. Bean `httpFirewall` được Spring Security dùng cho filter chain; `SecurityFilterChain` vẫn định nghĩa **ai** được truy cập. Trong ví dụ, các request `PUT`, `PATCH`, `DELETE` bị firewall từ chối ngay cả khi controller có mapping tương ứng; đó là **chính sách minh họa**, không phù hợp với mọi REST API. Khi dùng `OPTIONS` cho CORS, cấu hình CORS đúng cách vẫn cần thiết; firewall chỉ cho phép method chứ không tự xác thực nguồn cross-origin. CSRF vẫn được bật theo cấu hình mặc định của `HttpSecurity` trong ví dụ.

Để giữ mặc định về các method và path, **có thể bỏ hẳn bean `httpFirewall`**. Đây thường là lựa chọn an toàn và ít bảo trì hơn. Nếu muốn giới hạn method, cần kiểm kê các route thực tế, logout, upload, API và health check.

### Vì sao phải cân nhắc kỹ `setAllowSemicolon(true)`?

Spring MVC có thể dùng *matrix variables* như `/products;color=red`. `StrictHttpFirewall` mặc định chặn semicolon vì một số container/matcher có cách hiểu path parameter khác nhau. Cho phép semicolon là thay đổi **bề mặt tấn công**:

```java
@Bean
StrictHttpFirewall httpFirewall() {
    StrictHttpFirewall firewall = new StrictHttpFirewall();
    firewall.setAllowSemicolon(true); // Chỉ khi đã đánh giá nhu cầu matrix variable
    return firewall;
}
```

Đây là **ví dụ riêng, thay thế** bean cùng tên ở ví dụ trước, không thêm cả hai bean vào một cấu hình. Trước khi bật: kiểm thử nhất quán giữa proxy, container, MVC routing và security matchers; xác nhận quyền trên mọi biến thể path. Tương tự, tránh bật đại trà các tùy chọn `setAllowUrlEncodedSlash(true)`, `setAllowBackSlash(true)`, `setAllowUrlEncodedPercent(true)` hoặc `setUnsafeAllowAnyHttpMethod(true)` để “chữa” lỗi 400. Nếu client phát sinh URI sai, ưu tiên sửa client.

### Giới hạn Host, header, parameter

`StrictHttpFirewall` có API `setAllowedHostnames(Predicate<String>)`, `setAllowedHeaderNames(Predicate<String>)`, `setAllowedHeaderValues(Predicate<String>)`, `setAllowedParameterNames(Predicate<String>)` và `setAllowedParameterValues(Predicate<String>)`. Các predicate này phù hợp với chính sách nhỏ, ổn định và được kiểm thử. Chẳng hạn, khi chỉ có một hostname truy cập trực tiếp, có thể *xem xét* allowlist host chính thức. Tuy nhiên, môi trường proxy, nhiều tên miền, kiểm thử cục bộ và health check làm điều kiện đó phức tạp; cần kiểm tra giá trị mà ứng dụng thực sự nhận được trước khi áp dụng.

**Không đặt predicate `value -> true` cho header/parameter chỉ để tránh bị chặn:** thao tác này có thể bỏ kiểm tra an toàn mặc định. Header `Host` và `Forwarded`/`X-Forwarded-*` còn cần chính sách *trusted proxy* tại gateway; đừng tự tin vào header do client tùy ý gửi. Cũng đừng nhầm predicate kiểm tra *giá trị* với giới hạn **byte-size** của header hoặc body.

## 5. Giới hạn dữ liệu đầu vào: áp dụng ở đúng tầng

Firewall chủ yếu xử lý tính an toàn của request/matching, không đặt trần tổng byte cho mọi loại body, JSON, file upload hay số trường nhập. Thiết kế giới hạn cần phối hợp **gateway → container → parser → controller/service**.

| Loại đầu vào | Nơi nên giới hạn | Ví dụ / lưu ý |
| --- | --- | --- |
| Request line, URI, header | Proxy và HTTP connector | `server.max-http-request-header-size` đặt trần header; giới hạn chính xác phụ thuộc server, và có thể bao gồm request line ở Tomcat. |
| Form `application/x-www-form-urlencoded` | Servlet container | `server.tomcat.max-http-form-post-size` áp dụng cho form POST theo Tomcat, không phải trần byte cho mọi JSON request. |
| Upload `multipart/form-data` | Multipart resolver/container/gateway | `spring.servlet.multipart.max-file-size` và `max-request-size` giới hạn file riêng và toàn multipart. |
| JSON/text/XML body | Gateway hoặc middleware đọc body có giới hạn, cộng validation | Không suy rằng `max-http-form-post-size` hoặc multipart settings giới hạn JSON. Với body lớn, nên chặn *trước khi* parse/đệm toàn bộ. |
| Số trường, độ sâu JSON, số phần multipart | Parser/container/cấu hình chuyên biệt | Ngăn parameter pollution, parser/resource exhaustion; API hỗ trợ thay đổi theo server và phiên bản. |
| Giá trị trường, ID, page size, tên file | Controller/service | Bean Validation, kiểm tra format, danh sách giá trị hợp lệ, giới hạn truy vấn. |
| Tần suất/request burst | API gateway/rate limiter | Rate limiting tách biệt với firewall và giới hạn kích thước. |

Ví dụ `application.yml` cho ứng dụng Spring Boot dùng **embedded Tomcat** và có upload nhỏ:

```yaml
server:
  max-http-request-header-size: 16KB
  tomcat:
    max-http-form-post-size: 256KB

spring:
  servlet:
    multipart:
      max-file-size: 2MB
      max-request-size: 3MB
```

Các số trên chỉ là **ví dụ chính sách**, không phải khuyến nghị chung. Chọn giới hạn dựa trên nhu cầu thực, overhead hợp lệ của session/cookie, loại file, số trường và giới hạn gateway phía trước. Khi thay Tomcat bằng Jetty/Undertow hoặc dùng WebFlux, tên property và ý nghĩa có thể khác. Với `max-http-request-header-size`, tài liệu Spring Boot lưu ý **Tomcat tính chung request line, tên và giá trị header**, trong khi Netty áp giới hạn theo từng header; không coi chúng tương đương.

Nếu ứng dụng phục vụ JSON API, hãy cấu hình **max request body** tại ingress/proxy hoặc bộ lọc đọc body theo streaming với cơ chế ngắt đúng lúc, rồi bổ sung kiểm tra cấu trúc sau parse. Chỉ dùng `Content-Length` để quyết định là chưa đủ cho streaming/chunked transfer, trường hợp thiếu header và các trung gian truyền tải. Bất kỳ bộ lọc nào đọc body phải giữ tương thích với xử lý Servlet, multipart và luồng đọc body của controller; tránh tự viết wrapper chỉ để đếm byte nếu gateway/container đã hỗ trợ phù hợp.

### Ví dụ validation ở tầng controller

Dependency cần có trong dự án Boot: `spring-boot-starter-web`, `spring-boot-starter-validation` và `spring-boot-starter-security` (hoặc phần security đã có). DTO dùng `jakarta.validation`; các kích thước tối đa dưới đây là giới hạn **giá trị sau parse**, không thay cho giới hạn HTTP byte-size.

```java
package com.example.web;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record CreatePostRequest(
    @NotBlank @Size(max = 100) String title,
    @NotBlank @Size(max = 2000) String content
) {}

@RestController
@RequestMapping("/api/posts")
class PostController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    String create(@Valid @RequestBody CreatePostRequest request) {
        // Demo nhận dữ liệu hợp lệ; dịch vụ lưu trữ được lược bỏ.
        return "accepted";
    }
}
```

Khi input vi phạm `@NotBlank`/`@Size`, Spring MVC thông thường phản hồi **400** với lỗi validation của `@RequestBody`. Nhưng request có JSON quá lớn vẫn có thể tiêu tốn tài nguyên **trước khi** Bean Validation chạy nếu chưa có giới hạn ở tầng HTTP/parser. Với file upload, phải kiểm tra thêm kiểu nội dung thực, quyền người dùng, tên file và vị trí lưu, không chỉ dựa vào extension hoặc `Content-Type` client cung cấp.

## 6. Phân quyền URL phải khớp với tài nguyên thật

Giả sử định nghĩa:

- `/public/**` công khai.
- `/admin/**` chỉ cho `ROLE_ADMIN`.
- Mọi đường dẫn khác cần đăng nhập.

Nếu một tầng coi `/admin;anything/users` thuộc `/admin/**`, còn tầng khác coi đó là đường dẫn khác, phép so khớp có thể lệch. Firewall giảm những khác biệt nguy hiểm này; **quy tắc cuối `anyRequest().authenticated()` vẫn cần**, và với tài nguyên nhạy cảm thường nên áp dụng phân quyền ở service bằng method security.

Một điều cần phân biệt:

- `permitAll()`: request vẫn đi qua Spring Security filter chain và firewall; chỉ không cần xác thực ở rule cụ thể.
- `web.ignoring()` hoặc request không đi qua filter chain: có thể bỏ qua nhiều lớp bảo vệ của Spring Security; chỉ dùng khi thực sự hiểu tác động, không dùng như cách chữa 400 do firewall.
- Có nhiều `SecurityFilterChain`: kiểm tra `securityMatcher` và thứ tự chain; cần chắc không để lọt đường dẫn ngoài vùng bảo vệ vì rule không khớp.

Nếu bạn thao tác với **đường dẫn tệp trên server** (ví dụ tải file qua `/download/{name}`), đó là bài toán bổ sung ngoài URL authorization. Không dùng mỗi `Path.normalize()` để “làm sạch” URL. Sau khi phân quyền resource, vẫn phải giải quyết đường dẫn trên filesystem so với thư mục gốc được phép, kiểm tra traversal và symlink theo mô hình lưu trữ, và không đưa tên tệp client gửi trực tiếp vào lời gọi I/O thiếu kiểm tra.

## 7. Kiểm thử thực tế từ client đến controller

Nên test ở ít nhất hai mức: **unit/integration cho rule của ứng dụng** và **end-to-end qua cùng proxy/container với production**. Test Spring MVC `MockMvc` hữu ích cho rule nhưng không mô phỏng đầy đủ việc parse URI ở connector hoặc transform của proxy.

Khởi chạy ứng dụng Boot có cấu hình phù hợp; dùng `curl` để khảo sát, chú ý `--path-as-is` giúp curl không tự loại một số dot-segment trước khi gửi:

```bash
# Request thông thường (đối chiếu authentication/authorization)
curl -i http://localhost:8080/public/info

# Dấu chấm phẩy trong path: StrictHttpFirewall mặc định thường chặn nếu đến được nó
curl -i --path-as-is 'http://localhost:8080/public;v=1/info'

# Đường dẫn có dot-segment: có thể bị container hoặc firewall từ chối
curl -i --path-as-is 'http://localhost:8080/admin/../public/info'

# Slash được mã hóa: kết quả phụ thuộc cả connector và firewall
curl -i --path-as-is 'http://localhost:8080/admin%2Fusers'

# Method TRACE bị StrictHttpFirewall mặc định từ chối nếu đến được firewall
curl -i -X TRACE http://localhost:8080/public/info

# Dữ liệu JSON sai giới hạn giá trị: tầng Bean Validation xử lý
curl -i -H 'Content-Type: application/json' \
  -d '{"title":"","content":"test"}' \
  http://localhost:8080/api/posts
```

**Diễn giải kết quả:** không gán cứng mọi thử nghiệm thành 400. Container có thể trả 400 trước firewall, một route hợp lệ có thể trả 302 tới login, 401, 403 hoặc 404 tùy cấu hình authentication/authorization/routing. Khi tự động hóa, assert **không thể truy cập trái phép** và ghi nhận *tầng xử lý*, rồi bổ sung expectation cụ thể theo stack đã kiểm chứng. Đừng gửi request “tấn công” lên dịch vụ ngoài phạm vi bạn được phép kiểm thử.

### Ma trận test tối thiểu

| Kiểm tra | Kỳ vọng an ninh |
| --- | --- |
| Path hợp lệ đến route public | Không bị firewall chặn chỉ vì path; kết quả phụ thuộc route. |
| Path hợp lệ đến route admin, người không đủ quyền | Không trả dữ liệu admin; xác thực/phân quyền xử lý. |
| `..`, `//`, semicolon, encoded slash trong path | Không được chuyển thành truy cập trái phép; nơi từ chối phụ thuộc stack. |
| Method ngoài allowlist (vd. `TRACE`) | Không thực thi controller; bị chặn ở tầng HTTP/firewall. |
| Header quá giới hạn | Từ chối sớm trước khi ứng dụng phải xử lý; mã HTTP tùy server. |
| Multipart vượt `max-file-size` hoặc `max-request-size` | Upload bị từ chối; không lưu dữ liệu quá giới hạn. |
| JSON hợp lệ về byte-size nhưng field quá dài | Validation/trình xử lý nghiệp vụ từ chối. |
| JSON vượt ngưỡng body của gateway | Ngắt sớm, không deserialize nội dung vô hạn. |
| Đường dẫn qua proxy/ingress và truy cập trực tiếp | Cùng chính sách truy cập; không có đường vòng do rewrite/decoding. |

Khi chẩn đoán, có thể ghi lại **mã trạng thái, component từ chối, correlation ID, route logic và loại vi phạm**. Tránh ghi toàn bộ URI/header/body chứa token, cookie, email hoặc dữ liệu cá nhân vào log. Với `RequestRejectedException`, đặt mức log và cơ chế giám sát phù hợp để thấy spike bất thường, nhưng không diễn giải mọi 400 là một cuộc tấn công.

## 8. Những lỗi triển khai thường gặp

1. **Giả định firewall tự “sửa URL” an toàn:** `StrictHttpFirewall` ưu tiên *reject* path bất thường. Nếu tích hợp phát sinh `//` hoặc `%2F` ngoài dự kiến, điều tra nguồn phát sinh và các tầng decode.
2. **Mở tất cả tùy chọn allow để hết lỗi:** làm mất hàng rào ngăn path ambiguity. Chỉ nới một điều kiện với lý do, test và đánh giá tác động rõ ràng.
3. **Nhầm route matcher với kiểm tra quyền nghiệp vụ:** `/orders/{id}` chỉ là đường vào; người dùng còn phải có quyền với `id` tương ứng.
4. **Cho rằng `@Size` chống được body rất lớn:** Bean Validation thường chạy sau khi request đã parse; cần chặn byte-size từ tầng sớm.
5. **Dùng giới hạn form/multipart để suy ra giới hạn JSON:** đây là các loại payload khác nhau; phải giới hạn riêng.
6. **Dựa vào chỉ `Content-Length`:** request streaming/chunked có thể không có độ dài cố định.
7. **Tin hoàn toàn `X-Forwarded-*`, `Host` hoặc client-side validation:** cấu hình proxy đáng tin và kiểm tra dữ liệu ở server mới có ý nghĩa bảo mật.
8. **Thử với curl không giữ raw path rồi kết luận firewall hoạt động:** client có thể đã tự chuẩn hóa; dùng `--path-as-is` và quan sát request thực tế.
9. **Tắt Spring Security filter chain cho “static/public route” một cách tùy tiện:** giảm coverage của các filter bảo mật; cân nhắc `permitAll()` trong chain.
10. **Đánh đồng lỗi 400, 401, 403, 404 và 413/414/431:** chúng có thể do các tầng khác nhau trả về; kiểm tra đường đi request và access log trước khi sửa cấu hình.

## 9. Checklist trước khi đưa lên môi trường thật

- [ ] Xác định route public, route cần đăng nhập, route admin; có chính sách mặc định cho request chưa khớp.
- [ ] Giữ `StrictHttpFirewall` mặc định trừ khi có yêu cầu đã được kiểm chứng; ghi rõ mọi ngoại lệ và regression test.
- [ ] Đồng bộ quy tắc xử lý encoded slash, backslash, semicolon, duplicate slash giữa gateway và servlet container.
- [ ] Giới hạn request line/header tại HTTP server/proxy; đo tác động đến cookie/session và request hợp lệ.
- [ ] Đặt trần phù hợp cho form, multipart và body JSON; kiểm soát số trường/độ sâu/cấu trúc khi cần.
- [ ] Áp dụng Bean Validation cho DTO, phân quyền theo resource ở service, xử lý input file an toàn.
- [ ] Kiểm thử cả happy path, input sai, URI nhập nhằng, method không hỗ trợ và tải có kích thước vượt giới hạn.
- [ ] Quan sát đúng tầng gây từ chối, bảo vệ log khỏi lộ dữ liệu nhạy cảm và bảo đảm lỗi không trả stack trace cho client.

### Câu hỏi tự kiểm tra

1. Vì sao có thể nguy hiểm nếu proxy, container và Spring Security giải mã `%2F` theo cách khác nhau?
2. `StrictHttpFirewall` mặc định **từ chối** path bất thường hay tự sửa mọi path rồi cho qua?
3. `setAllowSemicolon(true)` giúp use case nào, và cần kiểm thử rủi ro gì?
4. Vì sao `spring.servlet.multipart.max-request-size` không phải cơ chế giới hạn JSON?
5. Vì sao route `/orders/{id}` vẫn cần kiểm tra quyền với đối tượng đơn hàng sau khi đã qua firewall?

**Gợi ý trả lời:** (1) chúng có thể áp quyền lên một path và thực thi path khác; (2) ưu tiên từ chối; (3) matrix variables nhưng có rủi ro lệch route/matcher; (4) multipart khác JSON và có giai đoạn parse khác; (5) quyền trên URL không chứng minh quyền đối với từng resource ID.

## Tài liệu chính thức để đối chiếu phiên bản

- Spring Security — HttpFirewall: https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html
- Spring Security — StrictHttpFirewall API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html
- Spring Boot 3.3 — Common Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring MVC — @RequestBody và Bean Validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
