# Đường dẫn gốc của ứng dụng, servlet mapping và URL điểm truy cập trong Spring Boot

## Mục tiêu học tập

Bài này giải thích cách URL của một HTTP request được phân tích và định tuyến đến đúng endpoint trong ứng dụng Spring Boot, đặc biệt là Spring MVC trên Servlet container. Sau bài học, bạn có thể:

- Phân biệt scheme, host, port, URL path, query string và fragment.
- Phân biệt context path của ứng dụng Servlet, servlet mapping của DispatcherServlet và mapping của controller.
- Tính được URL truy cập một endpoint từ cấu hình server và các annotation.
- Hiểu sự khác nhau giữa server.servlet.context-path, spring.mvc.servlet.path và spring.webflux.base-path.
- Xác định vị trí của Actuator, reverse proxy và API gateway trong quá trình tạo URL công khai.
- Điều tra có hệ thống lỗi 404, 405, tiền tố URL bị lặp và sai đường dẫn khi triển khai.

## 1. Một URL HTTP gồm những phần nào?

Ví dụ:

~~~text
https://api.example.com:8443/shop/gateway/orders/42?verbose=true
|----- scheme + host + port ----|----------- path -------|-- query --|
~~~

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Scheme | HTTPS | Giao thức từ client đến điểm nhận kết nối; có thể khác giao thức backend sau proxy. |
| Host | api.example.com | Tên miền hoặc địa chỉ IP được client dùng. |
| Port | 8443 | Cổng ở phía client; có thể được lược bỏ khi là cổng mặc định của giao thức. |
| Path | /shop/gateway/orders/42 | Chuỗi đường dẫn được dùng để định tuyến HTTP request. |
| Query string | verbose=true | Tham số sau dấu hỏi, thường đọc bằng @RequestParam. |
| Fragment | #details | Phần do client xử lý; trình duyệt không gửi fragment tới server trong HTTP request. |

Scheme và hostname public có thể do load balancer, ingress hoặc reverse proxy cung cấp. Thuộc tính server.port trong Spring Boot là cổng ứng dụng lắng nghe, không nhất thiết là cổng bên ngoài mà người dùng truy cập.

URL của một endpoint là đường dẫn giao tiếp mạng. Nó không đồng nghĩa với đường dẫn thư mục trong dự án, tên package Java, tên file controller hay đường dẫn tới file JAR.

## 2. Các tầng của URL trong Spring MVC

Với ứng dụng Servlet thông thường, ta có thể hình dung:

~~~text
URL client gửi
    |
    +-- scheme://host[:port]
    |
    +-- context path của ứng dụng Servlet
    |
    +-- prefix của DispatcherServlet mapping (nếu cấu hình)
    |
    +-- controller mapping + method mapping
    |
    +-- query string (nếu có)
~~~

Chẳng hạn:

~~~text
http://localhost:9090/shop/gateway/api/orders/42
                      |---|-------|-------------|
                    context servlet    handler
                      path   prefix       path
~~~

Công thức này chỉ diễn tả tầng trách nhiệm, không phải một quy tắc nối chuỗi thô cho mọi HTTP server. URL encoding, dạng servlet mapping và proxy rewrite có thể thay đổi kết quả thực tế.

### 2.1. Context path: đường dẫn gốc của ứng dụng

Trong Spring Boot chạy Servlet stack, cấu hình context path bằng:

~~~properties
server.servlet.context-path=/shop
~~~

Context path định danh ứng dụng web bên trong Servlet container. Nếu controller xử lý /api/orders/42 và dùng DispatcherServlet mặc định, URL trở thành /shop/api/orders/42.

Những điều quan trọng:

- Context path áp dụng ở tầng ứng dụng Servlet, trước khi container định tuyến tới servlet.
- Không khai báo lặp /shop trong từng @RequestMapping nếu đã đặt context path ở /shop.
- Mặc định ứng dụng Spring Boot Servlet chạy ở root context, tức không thêm tiền tố kiểu /shop.
- Cấu hình này ảnh hưởng đến các URL của ứng dụng Servlet, bao gồm controller và thường cả tài nguyên tĩnh.
- Root context không có nghĩa request GET / bắt buộc thành công: còn phải có handler hoặc tài nguyên tương ứng.

Ví dụ cấu hình:

~~~properties
server.port=9090
server.servlet.context-path=/shop
~~~

Nếu không có proxy hoặc cấu hình khác, máy khách kết nối trực tiếp đến ứng dụng bằng host localhost, port 9090 và path bắt đầu từ /shop.

### 2.2. Servlet mapping: container chọn servlet nào

Tomcat hoặc Servlet container nhận HTTP request rồi chọn servlet dựa trên URL pattern đã đăng ký. Spring MVC dùng DispatcherServlet làm front controller: servlet này nhận request rồi chuyển cho handler mapping tìm phương thức controller phù hợp.

Trong ứng dụng Spring MVC do Spring Boot cấu hình thông thường, DispatcherServlet dùng default servlet mapping /, đủ cho phần lớn REST API. Nếu có nhu cầu đặc biệt tách không gian URL giữa nhiều servlet, có thể đặt tiền tố bằng:

~~~properties
spring.mvc.servlet.path=/gateway
~~~

Khi được cấu hình hợp lệ, request có thể phải đi qua /gateway trước khi được DispatcherServlet xử lý. Nếu đồng thời có context path /shop, phần đường dẫn trước controller sẽ là /shop/gateway.

**Cảnh báo tương thích:** Tài liệu Spring Boot cho biết một servlet path prefix tùy chỉnh có thể không tương thích với chiến lược PathPatternParser mặc định. Với phiên bản Spring Boot 3.x hỗ trợ AntPathMatcher, cách cấu hình thường gặp khi bắt buộc có servlet prefix là:

~~~properties
spring.mvc.servlet.path=/gateway
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Cần đối chiếu với đúng phiên bản Spring Boot của dự án trước khi áp dụng. Nếu chỉ muốn mọi API có tiền tố /api, nhiều khi chỉ cần @RequestMapping ở controller hoặc context path, không cần đổi DispatcherServlet mapping.

Một số kiểu servlet URL pattern:

| Pattern | Ý nghĩa |
|---|---|
| / | Default servlet mapping. |
| /gateway/* | Prefix mapping cho URL có tiền tố gateway. |
| /status | Exact mapping cho một URL path. |
| *.jsp | Extension mapping theo hậu tố. |

Các pattern đó là quy tắc của Servlet container. Một custom servlet có mapping /legacy/* có thể phục vụ các URL riêng, và không tự trở thành tiền tố cho controller Spring MVC.

### 2.3. Controller mapping: Spring MVC tìm handler

Controller mapping khai báo tuyến đường bên trong Spring MVC. Ví dụ:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    String findById(@PathVariable("id") long id) {
        return "order:" + id;
    }
}
~~~

Trong ví dụ:

- Class-level @RequestMapping tạo phần /api/orders.
- Method-level @GetMapping tạo phần /{id} và giới hạn HTTP method là GET.
- @PathVariable lấy id từ đoạn URL, không phải query string.
- Kết quả mapping của handler là GET /api/orders/{id}, trước khi ghép context và servlet prefix.
- Nếu gọi đúng path nhưng sai method, response có thể là 405 Method Not Allowed thay vì 404 Not Found.

Đặt server.servlet.context-path=/shop rồi lại đặt @RequestMapping("/shop/api/orders") sẽ làm tiền tố bị lặp. Một request có thể phải mang /shop/shop/api/orders/42 mới tới đúng handler, dù đó không phải URL thiết kế ban đầu.

## 3. Ví dụ Spring Boot MVC chạy được

Ví dụ dùng Java 17+ và Spring Boot với starter Spring MVC. Với Spring Boot 3.x, starter thường dùng là spring-boot-starter-web. Trong Spring Boot 4.x, spring-boot-starter-webmvc là tên starter được khuyến nghị. Chọn artifact phù hợp với major version và để Spring Boot quản lý các version phụ thuộc.

Giả sử project Java chứa ba file sau.

### File 1: PathsApplication.java

Đường dẫn: src/main/java/com/example/paths/PathsApplication.java

~~~java
package com.example.paths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathsApplication {

    public static void main(String[] args) {
        SpringApplication.run(PathsApplication.class, args);
    }
}
~~~

### File 2: OrderController.java

Đường dẫn: src/main/java/com/example/paths/OrderController.java

~~~java
package com.example.paths;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public String findById(@PathVariable("id") long id) {
        return "order:" + id;
    }
}
~~~

### File 3: application.properties

Đường dẫn: src/main/resources/application.properties

~~~properties
server.port=9090
server.servlet.context-path=/shop
~~~

Không cấu hình spring.mvc.servlet.path trong ví dụ chính; DispatcherServlet dùng mapping mặc định.

Chạy ứng dụng qua Maven Wrapper đã có trong dự án:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows, nếu dùng Command Prompt hoặc PowerShell, có thể chạy mvnw.cmd spring-boot:run.

Gửi HTTP request:

~~~bash
curl -sS http://localhost:9090/shop/api/orders/42
~~~

Body trả về chính xác:

~~~text
order:42
~~~

Đường dẫn được hình thành như sau:

~~~text
server.port                 -> 9090
server.servlet.context-path -> /shop
DispatcherServlet mapping   -> /
class @RequestMapping       -> /api/orders
method @GetMapping          -> /{id}
PathVariable id             -> 42

GET http://localhost:9090/shop/api/orders/42
~~~

Khi thử lệnh sau:

~~~bash
curl -i http://localhost:9090/api/orders/42
~~~

request thiếu context path /shop, nên thông thường sẽ trả 404. Body lỗi thực tế phụ thuộc cấu hình Spring Boot, nội dung handler lỗi và phiên bản ứng dụng.

Nếu đổi server.servlet.context-path=/demo, endpoint trở thành /demo/api/orders/42; không sửa annotation controller.

### Thử thêm servlet path trong cấu hình tương thích

Nếu ứng dụng MVC dùng một phiên bản Spring Boot có thể cấu hình AntPathMatcher cho servlet prefix, ví dụ với Spring Boot 3.x:

~~~properties
server.port=9090
server.servlet.context-path=/shop
spring.mvc.servlet.path=/gateway
spring.mvc.pathmatch.matching-strategy=ant-path-matcher
~~~

Khi khởi động thành công với các thiết lập tương thích, URL là:

~~~text
GET http://localhost:9090/shop/gateway/api/orders/42
~~~

Body vẫn là order:42. Phần /gateway là đường dẫn tới DispatcherServlet, không được khai báo lặp lại trong @RequestMapping của controller.

## 4. Các trường path mà Servlet API cung cấp

Với request:

~~~text
GET /shop/gateway/api/orders/42?verbose=true HTTP/1.1
~~~

Giả sử ứng dụng có context path /shop và DispatcherServlet được đăng ký bằng prefix mapping /gateway/*:

| API | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| request.getRequestURI() | /shop/gateway/api/orders/42 | Path của HTTP request mà Servlet container nhìn thấy, không có query. |
| request.getContextPath() | /shop | Prefix định danh ứng dụng Servlet. |
| request.getServletPath() | /gateway | Phần path gắn với servlet prefix mapping. |
| request.getPathInfo() | /api/orders/42 | Phần còn lại sau servlet prefix trong trường hợp prefix mapping. |
| request.getQueryString() | verbose=true | Query string thô, không có dấu hỏi. |

Giá trị servletPath và pathInfo phụ thuộc dạng servlet mapping. Với default mapping /, servletPath thường thể hiện đường dẫn trong context và pathInfo là null; không giả định mọi request đều được phân chia giống prefix mapping.

Spring MVC tự xác định lookup path để ánh xạ tới @RequestMapping và xử lý escaping/URL decoding theo cơ chế của framework. Tránh tự lấy getRequestURI() rồi cắt chuỗi theo độ dài context path để chọn controller; logic như vậy dễ sai với servlet prefix và các ký tự URL được encode.

## 5. Context path, servlet path và controller mapping khác nhau thế nào?

Giả sử một controller được map tới GET /api/orders/42 và ứng dụng lắng nghe cổng 9090:

| Cấu hình / cách khai báo | URL nội bộ điển hình | Tầng chịu trách nhiệm |
|---|---|---|
| Mọi prefix giữ mặc định | http://localhost:9090/api/orders/42 | MVC handler mapping. |
| Context path /shop | http://localhost:9090/shop/api/orders/42 | Servlet application context. |
| DispatcherServlet prefix /gateway, matching tương thích | http://localhost:9090/gateway/api/orders/42 | Servlet mapping. |
| Context /shop + Servlet prefix /gateway | http://localhost:9090/shop/gateway/api/orders/42 | Hai tầng prefix độc lập. |
| Controller tự map /shop/api/orders, context mặc định | http://localhost:9090/shop/api/orders/42 | Chỉ controller mapping. |

Hai URL nhìn giống nhau có thể được tạo bằng cấu hình khác nhau. Khi chuyển ứng dụng sang một context khác, mô hình dùng context path sẽ ảnh hưởng nhiều servlet và tài nguyên trong ứng dụng hơn mô hình chỉ đổi @RequestMapping của vài controller.

Một quy ước dễ vận hành là quyết định rõ ai sở hữu từng tiền tố. Ví dụ /shop là context của ứng dụng và /api là tiền tố của REST controller. Khi đó hãy đặt server.servlet.context-path=/shop và controller mapping bắt đầu bằng /api; không cần tự thêm /shop lần nữa vào các controller.

## 6. Điểm khác biệt khi dùng Spring WebFlux

Spring WebFlux không phụ thuộc bắt buộc vào Servlet API. Nếu ứng dụng chạy WebFlux thuần với Reactor Netty, thuộc tính phù hợp để đặt tiền tố cho tất cả web handler là:

~~~properties
spring.webflux.base-path=/shop
~~~

Với handler map tới /api/orders/42, URL trở thành /shop/api/orders/42.

Không dùng server.servlet.context-path hoặc spring.mvc.servlet.path để đặt tiền tố cho WebFlux thuần. Chúng thuộc cấu hình Servlet/MVC. Đặt các thuộc tính đó trong một dự án WebFlux rồi tưởng rằng sẽ đổi toàn bộ route có thể làm mất thời gian điều tra lỗi 404.

Nếu cả starter MVC và WebFlux cùng có mặt, Spring Boot thường ưu tiên MVC theo cấu hình mặc định. Chỉ thêm WebFlux để dùng WebClient không đồng nghĩa server đang chạy WebFlux; kiểm tra web application type và dependency thực tế.

## 7. Actuator: đường dẫn quản trị là một nhóm riêng

Spring Boot Actuator cung cấp endpoint quản trị, ví dụ health, thường dùng tiền tố HTTP mặc định /actuator. Điều kiện là ứng dụng đã thêm dependency Actuator và endpoint được expose theo chính sách cấu hình.

Khi Actuator dùng cùng cổng với ứng dụng Servlet, web base path của nó được tính tương đối theo context path. Ví dụ:

~~~properties
server.port=9090
server.servlet.context-path=/shop
management.endpoints.web.base-path=/manage
~~~

Địa chỉ health điển hình:

~~~text
http://localhost:9090/shop/manage/health
~~~

Nếu không đổi management.endpoints.web.base-path, mặc định thường là /actuator, tạo URL /shop/actuator/health.

Nếu sử dụng cổng quản trị riêng:

~~~properties
management.server.port=9091
~~~

Actuator có management web context riêng, và base path của các management endpoint lúc này được tính tương đối theo management.server.base-path. Không ghép máy móc context path /shop của web server chính vào URL trên cổng 9091.

Đường dẫn Actuator cũng không nhất thiết chịu servlet prefix /gateway như controller nghiệp vụ; tài liệu Spring Boot xác định web base path của management endpoint theo context/management context. Cần kiểm tra đúng phiên bản và mapping thực tế.

Không mở mọi management endpoint công khai để sửa lỗi 404. Những endpoint chẩn đoán như mappings cần giới hạn quyền truy cập trong môi trường phù hợp.

## 8. URL public khi có reverse proxy và API gateway

Trong hệ thống triển khai thực, ứng dụng có thể lắng nghe trên cổng 8080 bên trong container, còn khách truy cập qua HTTPS trên tên miền riêng.

Ví dụ:

~~~text
Public client                         API gateway                 Spring Boot
https://api.example.com/v1/orders/42 -> http://service:8080/orders/42 -> Controller /orders/{id}
                        prefix /v1    gateway bỏ prefix /v1
~~~

Nếu proxy đã loại bỏ /v1 trước khi gửi tới backend, Spring Boot không cần biết /v1 là context path. Ngược lại, nếu proxy giữ nguyên /v1, ứng dụng hoặc router backend phải có mapping tương ứng.

Trước khi quyết định URL thực, cần biết:

1. Proxy có giữ nguyên path hay rewrite path?
2. Proxy có thêm hoặc loại bỏ prefix không?
3. HTTPS kết thúc tại proxy hay tại ứng dụng?
4. Host/port bên ngoài khác host/port nội bộ thế nào?
5. Đường dẫn redirect, tài nguyên tĩnh, Actuator và Spring Security có cùng quy tắc không?

Spring Boot hỗ trợ cấu hình xử lý forwarded headers:

~~~properties
server.forward-headers-strategy=framework
~~~

Các header liên quan có thể bao gồm Forwarded, X-Forwarded-Proto, X-Forwarded-Host và X-Forwarded-Prefix. Chỉ tin các header được chuẩn hóa bởi proxy đáng tin cậy; client có thể tự gửi header giả nếu lớp biên mạng không chặn hoặc thay thế chúng.

Cũng cần phân biệt server.address=0.0.0.0 với URL công khai. Giá trị này cho server bind trên các địa chỉ mạng phù hợp, nhưng không tạo DNS name hoặc thay đổi public HTTPS endpoint. Trong Docker/Kubernetes, port mapping và ingress có thể chuyển cổng khác với server.port.

## 9. Lỗi 404, 405 và URL bị lặp: cách tìm nguyên nhân

Một quy trình kiểm tra thực tế:

1. Xác nhận đúng host, scheme, port và phiên bản ứng dụng đang chạy.
2. Xác định web stack: Spring MVC hay Spring WebFlux.
3. Với MVC, kiểm tra server.servlet.context-path có đặt prefix không.
4. Kiểm tra spring.mvc.servlet.path; nếu có, xác nhận DispatcherServlet mapping và chiến lược matching tương thích.
5. Ghép class-level @RequestMapping và method-level @GetMapping/@PostMapping.
6. Kiểm tra HTTP method và tham số path; đúng path nhưng sai method có thể trả 405.
7. Xác định gateway giữ/bỏ/thêm prefix như thế nào.
8. Kiểm tra Spring Security matcher, route tài nguyên tĩnh và endpoint Actuator khi có liên quan.
9. Dùng request log, controller mapping log hoặc endpoint mappings được bảo vệ trong môi trường kiểm thử.

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| /api/orders/42 báo 404 sau khi đặt context /shop | Thiếu context path trên URL client | Gọi /shop/api/orders/42. |
| URL phải chứa /shop/shop | Đã đặt /shop ở cả context path và @RequestMapping | Chỉ giữ prefix ở tầng đã thiết kế. |
| Thêm /gateway rồi ứng dụng có lỗi mapping | Servlet prefix không tương thích PathPatternParser của phiên bản | Kiểm tra matching strategy và tài liệu version tương ứng. |
| Endpoint nội bộ chạy, endpoint public 404 | Proxy rewrite hoặc giữ prefix khác dự kiến | Đối chiếu access log gateway và request URI tới backend. |
| GET nhận 405 | Handler chỉ hỗ trợ một HTTP method khác | Gọi đúng method hoặc sửa annotation. |
| /actuator/health không tồn tại | Actuator chưa có dependency, base path hoặc management port khác | Xác nhận cấu hình và trạng thái expose endpoint. |
| Redirect sinh http://backend thay vì https://domain | Thông tin forwarded headers/proxy chưa đồng bộ | Cấu hình trusted proxy và xử lý forwarded headers. |

Một phép thử nhanh với ứng dụng ở phần 3:

~~~bash
curl -i http://localhost:9090/shop/api/orders/42
curl -i http://localhost:9090/api/orders/42
curl -i "http://localhost:9090/shop/api/orders/42?verbose=true"
~~~

Request thứ nhất khớp endpoint và trả body order:42. Request thứ hai thiếu /shop nên thường trả 404. Request thứ ba có cùng URL path với request thứ nhất: query string verbose=true không làm đổi handler mapping của ví dụ.

Khi cần quan sát, có thể log request.getRequestURI(), getContextPath() và getServletPath() tại môi trường phát triển. Tránh ghi token, cookie hay dữ liệu nhạy cảm trong log.

## 10. Bài tập tự kiểm tra

Cho ứng dụng Spring MVC có:

~~~properties
server.port=9000
server.servlet.context-path=/catalog
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/books")
class BookController {

    @GetMapping("/{isbn}")
    String find(@PathVariable("isbn") String isbn) {
        return isbn;
    }
}
~~~

Trả lời:

1. URL trực tiếp để GET sách có ISBN 9780000000000 là gì?
2. Thêm query ?lang=vi có đổi handler mapping không?
3. Nếu đổi class mapping thành /catalog/api/books nhưng vẫn giữ context /catalog, URL mới là gì?
4. Nếu có thêm servlet prefix /dispatcher với cấu hình tương thích, URL của ví dụ gốc là gì?
5. Nếu xây ứng dụng WebFlux thuần, thuộc tính nào đặt base path /catalog?
6. Vì sao server.port=9000 không đủ để xác định URL public qua API gateway?
7. Với Actuator dùng cùng port và base path mặc định, URL health thường là gì?

### Đáp án

1. http://localhost:9000/catalog/api/books/9780000000000.
2. Không. Query string được xử lý riêng, có thể đọc bằng @RequestParam nếu cần.
3. /catalog/catalog/api/books/9780000000000 vì prefix bị ghép hai lần ở hai tầng.
4. http://localhost:9000/catalog/dispatcher/api/books/9780000000000.
5. spring.webflux.base-path=/catalog.
6. Gateway có thể đổi scheme, host, port và rewrite path.
7. Thường là http://localhost:9000/catalog/actuator/health, nếu Actuator đã được thêm và health endpoint được expose.

## 11. Tài liệu tham khảo chính thức

- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC, DispatcherServlet và chiến lược path matching.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): context path, servlet path và WebFlux base path.
- [Spring Framework — Path Matching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/handlermapping-path.html): Servlet path, context path và handler lookup path.
- [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): Actuator base path và management port.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): base path cho WebFlux.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): starter Spring MVC theo phiên bản.
