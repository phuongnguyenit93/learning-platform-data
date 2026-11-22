# Thời gian chờ kết nối, keep-alive và giới hạn riêng của máy chủ

Trong Spring Boot, một API chạy tốt ở môi trường phát triển vẫn có thể gặp lỗi khi nhiều client giữ kết nối mở, gửi request chậm, tái sử dụng socket lâu hoặc vượt giới hạn tài nguyên của embedded web server. Các tham số `timeout`, `keep-alive` và `max connections` giúp kiểm soát vòng đời kết nối, nhưng mỗi tham số tác động đến một giai đoạn khác nhau. Việc cấu hình cần dựa trên **server thực tế đang chạy** (Tomcat, Jetty, Undertow hoặc Reactor Netty), loại giao thức HTTP, proxy phía trước và đặc điểm tải.

Bài này giải thích sự khác biệt giữa các loại timeout, cơ chế tái sử dụng kết nối, các giới hạn cấp server, cách cấu hình bằng Spring Boot 3.3.x và phương pháp kiểm chứng khi triển khai. Các giá trị trong ví dụ là điểm bắt đầu để thử nghiệm, **không phải cấu hình tối ưu mặc định cho mọi hệ thống**.

## 1. Kết nối HTTP trải qua những giai đoạn nào?

Với một request HTTP/1.1 điển hình:

1. Client kết nối TCP đến server, có thể thực hiện TLS handshake nếu dùng HTTPS.
2. Server chấp nhận socket và chờ request line/header.
3. Client gửi request; server nhận body nếu có.
4. Spring xử lý request qua servlet/filter/controller hoặc chuỗi xử lý WebFlux.
5. Server ghi response.
6. Kết nối được đóng hoặc giữ lại để client gửi request tiếp theo.

Một sơ đồ rút gọn:

~~~text
Client -- TCP/TLS --> Server socket
                    |
                    +-- đợi request line / headers
                    |
                    +-- nhận body, xử lý controller
                    |
                    +-- gửi response
                    |
                    +-- keep-alive idle -> request tiếp theo?
                                      | yes: tái sử dụng
                                      | no : đóng kết nối
~~~

Các pha này có thể có bộ đếm thời gian riêng. Vì vậy, chỉ nói “server timeout 30 giây” là chưa đủ: cần biết **timeout nào, bắt đầu tính từ lúc nào, dừng ở sự kiện nào và do thành phần nào áp dụng**.

## 2. Phân biệt những loại timeout thường bị nhầm

| Loại giới hạn | Áp dụng khi | Ý nghĩa thực tế |
|---|---|---|
| Client connect timeout | Client cố thiết lập kết nối đến server | Client chờ kết nối thành công bao lâu; thường nằm ở HTTP client |
| Server connection/request-line timeout | Kết nối được chấp nhận nhưng request ban đầu chưa đủ | Giới hạn thời gian chờ client bắt đầu request theo quy tắc của server |
| Connection idle timeout | Socket không có hoạt động I/O theo quy tắc server | Kết nối không hoạt động quá lâu sẽ bị đóng |
| HTTP keep-alive timeout | Sau một response, server chờ request kế tiếp | Giới hạn khoảng rảnh giữa các request trên kết nối được tái sử dụng |
| Request processing timeout | Request đang được xử lý | Giới hạn thời gian xử lý toàn request hoặc tác vụ bất đồng bộ; thường do framework, ứng dụng hoặc proxy quyết định |
| Response/client read timeout | Client chờ byte response | Thường cấu hình ở HTTP client/proxy, không đồng nghĩa với server keep-alive |
| Graceful shutdown timeout | Server đang dừng | Khoảng chờ các công việc/request hiện có hoàn tất trước khi đóng tài nguyên |

Không có một property Spring Boot duy nhất áp dụng đồng thời cho tất cả các timeout trên.

Ví dụ: `server.tomcat.connection-timeout` mô tả thời gian Tomcat chờ **request URI line sau khi chấp nhận kết nối**, không phải tổng thời gian controller được chạy. `server.tomcat.keep-alive-timeout` lại điều khiển việc chờ request **tiếp theo** sau khi response trước đã xong.

Khi debug, phải phân biệt lỗi xảy ra **trước khi request được đọc**, **trong lúc request đang xử lý** hay **sau response khi socket được giữ lại**.

## 3. HTTP keep-alive là gì?

Trong HTTP/1.1, kết nối bền vững (persistent connection) là hành vi mặc định khi không có tín hiệu đóng kết nối. Một TCP connection có thể chuyên chở nhiều cặp request/response tuần tự. Điều này giúp giảm chi phí kết nối TCP, TLS handshake và cấp phát tài nguyên.

Ví dụ mô tả logic:

~~~http
GET /api/products/1 HTTP/1.1
Host: localhost:8080

HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 10

{"id":1}

GET /api/products/2 HTTP/1.1
Host: localhost:8080

HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 10

{"id":2}
~~~

Hai request trong ví dụ có thể đi qua **cùng một TCP connection** nếu server và client đều cho phép tái sử dụng. Ví dụ là mô hình giao thức, không phải mã để gửi bằng một lệnh shell.

Một số điểm cần nhớ:

- Trong HTTP/1.1, không bắt buộc phải gửi `Connection: keep-alive` để có kết nối bền vững; phần lớn client dùng persistent connection mặc định.
- `Connection: close` yêu cầu kết nối được đóng sau khi hoàn tất message hiện tại.
- Header `Keep-Alive: timeout=...` hoặc `Keep-Alive: max=...` nếu xuất hiện chỉ là thông tin/hint ở mức hop-by-hop; client không thể ép server giữ socket sống vô hạn.
- HTTP/2 dùng nhiều stream trên một kết nối và quy tắc quản lý kết nối khác HTTP/1.1. Không đưa header `Connection` vào HTTP/2; việc nhiều request chia sẻ một TCP connection không đồng nghĩa với số lượng request HTTP/1.1 tuần tự.
- HTTP keep-alive khác **TCP SO_KEEPALIVE**. TCP keepalive là cơ chế thăm dò socket ở tầng TCP nhằm phát hiện kết nối không còn sống, không thay thế timeout chờ request HTTP kế tiếp.

Giữ kết nối lâu có lợi cho độ trễ nhưng cũng giữ file descriptor, socket, buffer và trạng thái ở server. Giữ quá ngắn gây nhiều lần kết nối mới; giữ quá dài có thể làm cạn tài nguyên khi nhiều client để kết nối rảnh.

## 4. Hai giới hạn keep-alive: thời gian và số request

Có ít nhất hai câu hỏi độc lập:

1. **Kết nối rảnh bao lâu thì đóng?** — keep-alive/idle timeout.
2. **Một kết nối được phục vụ tối đa bao nhiêu request?** — max keep-alive requests.

Ví dụ giả định:

~~~text
timeout giữa hai request: 15 giây
tối đa request trên một kết nối: 100
~~~

Nếu client im lặng quá 15 giây, server có thể đóng socket dù mới xử lý 2 request. Nếu client gửi liên tục 100 request, server có thể đóng kết nối sau khi hoàn tất giới hạn ngay cả khi thời gian rảnh rất ngắn.

Giới hạn số request là tính năng theo từng server; đừng suy đoán Tomcat, Jetty, Undertow và Reactor Netty cùng dùng một property. Cần đọc tài liệu của server và phiên bản Spring Boot đang vận hành.

## 5. Spring Boot phân biệt các embedded server

Spring Boot có thể chạy nhiều web server nhưng property chỉ có tác dụng khi server tương ứng được sử dụng.

| Web stack / server | Thường được kích hoạt bởi | Vùng cấu hình chính |
|---|---|---|
| Spring MVC + Tomcat | `spring-boot-starter-web` với dependency mặc định | `server.tomcat.*` |
| Spring MVC + Jetty | Dùng Jetty thay Tomcat | `server.jetty.*` |
| Spring MVC + Undertow | Dùng Undertow thay Tomcat | `server.undertow.*` |
| Spring WebFlux + Reactor Netty | `spring-boot-starter-webflux` với dependency mặc định | `server.netty.*` |

Không thể cấu hình Tomcat bằng cách đặt `server.netty.idle-timeout` nếu tiến trình thực tế đang chạy Tomcat. Khi dự án mang cả Servlet và Reactive dependency, Spring Boot thường ưu tiên loại ứng dụng Servlet theo mặc định; hãy xác nhận web stack từ dependency, startup log và loại `WebApplicationContext` thực tế.

Các property liên quan đều cần kiểm tra theo phiên bản. Ví dụ Spring Boot 3.3.x và 4.x có thể dùng cùng tên nhiều property nhưng mặc định, khả năng hỗ trợ và hành vi trong server nền có thể khác nhau.

## 6. Tomcat: connection timeout và keep-alive

### 6.1. Các property trọng tâm

Trong Spring Boot 3.3.x, Tomcat cung cấp những property quan trọng:

| Property | Ý nghĩa |
|---|---|
| `server.tomcat.connection-timeout` | Khoảng chờ request URI line sau khi Tomcat chấp nhận kết nối |
| `server.tomcat.keep-alive-timeout` | Khoảng chờ request kế tiếp trước khi đóng kết nối |
| `server.tomcat.max-keep-alive-requests` | Giới hạn request được xử lý trên một kết nối keep-alive |
| `server.tomcat.max-connections` | Giới hạn kết nối mà Tomcat chấp nhận/xử lý đồng thời |
| `server.tomcat.accept-count` | Kích thước hàng đợi kết nối đến khi giới hạn khả năng xử lý đã đạt |
| `server.tomcat.threads.max` | Giới hạn worker thread của connector theo cấu hình thread pool thông thường |
| `server.tomcat.threads.min-spare` | Số worker thread dự phòng tối thiểu |

Theo tài liệu cấu hình Spring Boot 3.3, các mặc định thường được liệt kê là `max-keep-alive-requests=100`, `max-connections=8192`, `accept-count=100` và `threads.max=200`. Đây là **giá trị tham khảo của phiên bản**, không phải khuyến nghị đặt lại mọi ứng dụng về các số đó.

### 6.2. Ví dụ cấu hình Tomcat

Trong `src/main/resources/application.yml` của ứng dụng Spring MVC chạy Tomcat:

~~~yaml
server:
  port: 8080
  tomcat:
    connection-timeout: 10s
    keep-alive-timeout: 15s
    max-keep-alive-requests: 100
    max-connections: 2000
    accept-count: 100
    threads:
      max: 200
      min-spare: 10
~~~

Giải thích:

- `connection-timeout: 10s` giới hạn thời gian chờ request line đầu tiên khi kết nối đã được chấp nhận.
- `keep-alive-timeout: 15s` giới hạn khoảng rảnh khi chờ request tiếp theo.
- `max-keep-alive-requests: 100` giới hạn số request trên mỗi kết nối bền vững.
- `max-connections: 2000` giới hạn số kết nối được Tomcat chấp nhận và xử lý.
- `accept-count: 100` liên quan hàng đợi kết nối đang chờ khi server bận; hiệu quả thực tế còn phụ thuộc backlog hệ điều hành.
- `threads.max: 200` giới hạn worker thread theo mô hình thread pool truyền thống, không có nghĩa chỉ được mở 200 TCP connection.

Đây là **ví dụ minh họa quan hệ giữa các tham số**, chưa được đo tải, không nên copy sang production mà không kiểm chứng. Khi bật virtual threads trên phiên bản hỗ trợ, một số property thread pool như `server.tomcat.threads.max` có thể không còn tác dụng theo cách truyền thống; cần theo dõi cách runtime đang xử lý request.

### 6.3. Khi không khai báo keep-alive-timeout

Với Tomcat, nếu `server.tomcat.keep-alive-timeout` không được đặt, thời gian chờ request tiếp theo dùng giá trị connection timeout của connector. Nếu đặt `-1`, Tomcat không áp dụng timeout keep-alive theo property này. Không nên dùng thời gian chờ vô hạn cho hệ thống công khai nếu chưa có chính sách kết nối và năng lực tài nguyên tương ứng.

`max-keep-alive-requests` với `0` hoặc `1` có thể vô hiệu hóa keep-alive/pipelining theo quy tắc Tomcat; giá trị `-1` cho phép số request không giới hạn bởi tham số đó. Không nhầm `max-keep-alive-requests` với `max-connections`: một tham số đếm request **trên một socket**, tham số kia đếm **socket đồng thời**.

## 7. Tomcat: tài nguyên kết nối, queue và worker thread

Ba số thường bị đánh đồng:

~~~text
max-connections     -> số socket có thể được chấp nhận/xử lý
threads.max         -> số worker thread xử lý công việc
accept-count        -> hàng đợi kết nối đến khi đã quá tải
~~~

Một kết nối keep-alive rảnh không nhất thiết giữ một worker thread bận liên tục. Với Servlet xử lý đồng bộ, một request đang chạy có thể chiếm worker thread trong lúc controller xử lý. Nếu controller gọi database hoặc HTTP service khác theo cách blocking, worker thread có thể bị giữ trong thời gian chờ kết quả.

Hệ quả:

- **Tăng max-connections** giúp cho phép nhiều socket hơn nhưng có thể tăng bộ nhớ, file descriptor và tải I/O.
- **Tăng threads.max** có thể cải thiện throughput trong vài workload blocking, nhưng nhiều thread quá mức gây context switching, bộ nhớ stack và cạnh tranh tài nguyên.
- **Tăng accept-count** cho phép thêm kết nối chờ nhưng chỉ có thể chuyển lỗi từ từ chối kết nối sang thời gian chờ dài hơn; không làm controller xử lý nhanh hơn.
- **Giảm keep-alive-timeout** thu hồi socket rảnh sớm hơn nhưng tăng số lần client phải mở kết nối mới.

Không có quan hệ `max-connections = threads.max`. Cần đo đồng thời throughput, latency, active connections, busy threads, request queue và kết quả từ client.

## 8. Jetty: idle timeout và giới hạn riêng

Khi ứng dụng Servlet sử dụng Jetty, các property tương ứng gồm:

~~~yaml
server:
  jetty:
    connection-idle-timeout: 30s
    max-connections: 1500
    threads:
      max: 200
      min: 8
~~~

Ý nghĩa:

- `server.jetty.connection-idle-timeout`: kết nối không có hoạt động trong khoảng timeout có thể bị đóng.
- `server.jetty.max-connections`: giới hạn số kết nối mà server chấp nhận và xử lý đồng thời; trong tài liệu Spring Boot 3.3, mặc định `-1` biểu thị không đặt giới hạn theo property này.
- `server.jetty.threads.max` và `server.jetty.threads.min`: kích thước thread pool Jetty theo cơ chế thông thường.
- `server.jetty.threads.idle-timeout`: thời gian thread trong pool rảnh, **không phải** timeout của HTTP connection.
- `server.jetty.threads.acceptors` và `server.jetty.threads.selectors`: điều chỉnh luồng chấp nhận kết nối và xử lý I/O; cần hiểu tài nguyên trước khi thay đổi.

**Lỗi dễ gặp:** đặt `server.jetty.threads.idle-timeout=30s` rồi cho rằng kết nối HTTP sẽ đóng sau 30 giây. Property này liên quan thread pool; để tác động lên kết nối cần xem `server.jetty.connection-idle-timeout`.

Jetty có cơ chế quản lý tài nguyên và connection pool riêng; không được dùng giá trị Tomcat như thể mọi giới hạn có cùng ý nghĩa và mặc định.

## 9. Undertow: no-request-timeout và các giới hạn HTTP

Với Undertow, Spring Boot 3.3.x hỗ trợ:

~~~yaml
server:
  undertow:
    no-request-timeout: 20s
    max-http-post-size: 10MB
    max-cookies: 200
    threads:
      io: 4
      worker: 32
~~~

Trong ví dụ:

- `server.undertow.no-request-timeout`: thời gian mà kết nối có thể rảnh khi không xử lý request trước khi server đóng nó.
- `server.undertow.max-http-post-size`: giới hạn nội dung POST HTTP theo hành vi Undertow.
- `server.undertow.max-cookies`: giới hạn số cookie được chấp nhận.
- `server.undertow.max-headers` và `server.undertow.max-parameters`: giới hạn số header và tham số để giảm rủi ro tiêu thụ tài nguyên quá mức.
- `server.undertow.threads.io`: số I/O thread; không dùng chúng cho tác vụ blocking lâu.
- `server.undertow.threads.worker`: số worker thread xử lý công việc cần chạy ngoài I/O thread.

Spring Boot còn hỗ trợ truyền một số tùy chọn Undertow/XNIO qua `server.undertow.options.server.*` và `server.undertow.options.socket.*`. Phải đối chiếu tên option với phiên bản Undertow đang dùng, vì đây là tầng cấu hình đặc thù và không nhất thiết có property Spring Boot cấp cao tương đương.

Một giá trị `no-request-timeout` là chính sách kết nối rảnh. Nó **không bảo đảm** toàn bộ request nghiệp vụ sẽ bị hủy khi controller chạy quá khoảng thời gian đó.

## 10. Reactor Netty: connection và channel idle

Trong ứng dụng WebFlux dùng Reactor Netty, có các property:

~~~yaml
server:
  netty:
    connection-timeout: 10s
    idle-timeout: 30s
    max-keep-alive-requests: 100
    max-initial-line-length: 8KB
~~~

Ý nghĩa theo tài liệu Spring Boot 3.3:

- `server.netty.connection-timeout`: connection timeout của Netty channel. Phải hiểu trong ngữ cảnh server/channel đang chạy, không đồng nhất với timeout mở kết nối của một HTTP client.
- `server.netty.idle-timeout`: thời gian channel rảnh trước khi đóng; nếu không khai báo, tài liệu Boot 3.3 ghi nhận timeout có thể là vô hạn theo thiết lập này.
- `server.netty.max-keep-alive-requests`: số request tối đa trên một kết nối; nếu không đặt, mặc định không giới hạn bởi property này.
- `server.netty.max-initial-line-length`: giới hạn độ dài dòng đầu request HTTP, khác hoàn toàn timeout.
- `server.netty.initial-buffer-size`: dung lượng buffer ban đầu để decode HTTP request.

WebFlux + Reactor Netty dùng cơ chế event loop, nên không thể lấy các giá trị `server.tomcat.threads.max` áp thẳng sang Netty. Nếu handler WebFlux chạy blocking I/O lâu trên event loop, hệ thống có thể chậm dù chỉ có ít kết nối đang mở. Cần chuyển blocking work sang scheduler phù hợp hoặc dùng client/data access thực sự non-blocking.

**Phân biệt server Netty với Reactor Netty HTTP client:** timeout khi ứng dụng gọi một API bên ngoài bằng `WebClient` thường được cấu hình ở HTTP client/`HttpClient` của ứng dụng, ví dụ connect/response timeout. Đặt `server.netty.idle-timeout` chỉ tác động server, không tự thay timeout outbound.

## 11. Giới hạn kích thước header, body, form và multipart

Ngoài thời gian và số socket, web server áp dụng giới hạn đầu vào để bảo vệ bộ nhớ và ngăn request bất thường.

| Nhóm | Ví dụ property Spring Boot 3.3 | Lưu ý |
|---|---|---|
| Request header | `server.max-http-request-header-size` | Mỗi server thực hiện giới hạn khác nhau |
| Form POST Tomcat | `server.tomcat.max-http-form-post-size` | Giới hạn nội dung form POST |
| Swallow body Tomcat | `server.tomcat.max-swallow-size` | Lượng request body Tomcat có thể đọc bỏ khi xử lý |
| Form POST Jetty | `server.jetty.max-http-form-post-size` | Giới hạn form theo Jetty |
| HTTP POST Undertow | `server.undertow.max-http-post-size` | Giới hạn nội dung POST theo Undertow |
| Request line Netty | `server.netty.max-initial-line-length` | Dòng request line, không phải body |
| Multipart Servlet | `spring.servlet.multipart.max-file-size` và `spring.servlet.multipart.max-request-size` | Giới hạn upload file và toàn request multipart |

Ví dụ:

~~~yaml
server:
  max-http-request-header-size: 16KB

spring:
  servlet:
    multipart:
      max-file-size: 5MB
      max-request-size: 10MB
~~~

`server.max-http-request-header-size` **không được các server áp dụng giống nhau**. Tài liệu Boot 3.3 nêu ví dụ: Tomcat tính kết hợp request line và toàn bộ header; Reactor Netty áp giới hạn riêng cho từng header. Vì vậy hai server dùng cùng giá trị `16KB` có thể chấp nhận/từ chối các request khác nhau.

Một lỗi phổ biến là thấy request JSON lớn bị lỗi rồi tăng `server.tomcat.max-http-form-post-size`. Property đó dành cho form POST, không phải “giới hạn dung lượng của mọi JSON request”. Cần xác định tầng thực sự đang từ chối body: proxy, server parser, multipart resolver, framework hay logic ứng dụng.

## 12. Demo runnable: quan sát kết nối được tái sử dụng

Ví dụ sau dùng Java 17+ và Spring Boot 3.3.x với `spring-boot-starter-web` (Tomcat mặc định). Đặt mã trong tệp `src/main/java/com/example/demo/ServerLimitsApplication.java` của một project Spring Boot đã có dependency và build plugin tương ứng:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServerLimitsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerLimitsApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping(path = "/ping", produces = MediaType.TEXT_PLAIN_VALUE)
    String ping() {
        return "pong\n";
    }
}
~~~

Đặt cấu hình trong `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  tomcat:
    connection-timeout: 10s
    keep-alive-timeout: 15s
    max-keep-alive-requests: 100
~~~

Chạy trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Chạy trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Để thử client gửi hai HTTP/1.1 request trong **một tiến trình curl**, dùng:

~~~bash
curl --http1.1 -v http://localhost:8080/ping http://localhost:8080/ping
~~~

Body response của mỗi request là một dòng:

~~~text
pong
pong
~~~

Với server và client đều cho phép tái sử dụng, phần verbose có thể hiển thị thông tin kiểu `Re-using existing connection` ở request thứ hai (cách ghi có thể thay đổi theo phiên bản curl). Hai lần chạy **hai tiến trình curl độc lập** không chứng minh được việc tái sử dụng cùng socket, vì mỗi tiến trình thường có connection pool riêng.

Để yêu cầu đóng sau response:

~~~bash
curl --http1.1 -v -H "Connection: close" \
  http://localhost:8080/ping http://localhost:8080/ping
~~~

Tùy nền tảng shell, hãy dùng cú pháp xuống dòng phù hợp. Trên Windows PowerShell, có thể viết nguyên lệnh một dòng và dùng `curl.exe` để tránh nhầm alias của Windows PowerShell cũ.

**Thí nghiệm tiếp theo:** đổi `server.tomcat.max-keep-alive-requests` thành `1`, khởi động lại rồi quan sát lần kết nối thứ hai. Kỳ vọng là client cần một connection khác sau mỗi response; xác minh bằng verbose output và thông tin socket, không chỉ bằng body `pong`.

## 13. Kiểm tra timeout thật bằng phương pháp phù hợp

Lệnh `curl -v` ở trên hữu ích để thấy hành vi keep-alive, nhưng không đủ để đo mọi timeout.

Để kiểm tra **server connection timeout**, cần một client có thể mở TCP socket nhưng gửi request line chậm có kiểm soát. Một request HTTP bình thường hoàn tất rất nhanh nên không kích hoạt giới hạn này.

Để kiểm tra **keep-alive idle timeout**, cần tái sử dụng cùng connection và chủ động giữ nó không hoạt động giữa hai request. Nếu đóng tiến trình client rồi mở kết nối mới, phép thử không đo timeout của socket cũ.

Để kiểm tra **max connections hoặc accept queue**, cần công cụ load test tạo nhiều kết nối đồng thời, kèm quan sát tài nguyên và lỗi kết nối. Test tuần tự vài request không chứng minh được giới hạn đồng thời.

Để kiểm tra **max-keep-alive-requests**, gửi nhiều request trên một connection và đếm số lần socket được tạo/đóng theo client log, packet capture hoặc server telemetry.

Khi chạy test:
- Xác nhận phiên bản Spring Boot và embedded server thật.
- Ghi nhận HTTP/1.1 hay HTTP/2 và việc dùng TLS.
- Xác nhận có proxy, ingress hoặc load balancer ở giữa không.
- Đo ít nhất throughput, p95/p99 latency, connection count, CPU, bộ nhớ, thread/event loop và tỷ lệ lỗi.
- Thử sau khi restart để biết cấu hình đã được nạp thực sự.
- Không thử giới hạn quá tải trực tiếp trên hệ thống production không có biện pháp kiểm soát.

## 14. Reverse proxy và load balancer cũng có timeout riêng

Một request có thể đi qua nhiều hop:

~~~text
Browser / API client
         |
         v
CDN / Load Balancer  <-- client-side idle timeout
         |
         v
Ingress / Reverse Proxy  <-- upstream keep-alive, read timeout
         |
         v
Spring Boot embedded server <-- server.tomcat / server.jetty / server.netty ...
~~~

Mỗi hop có thể có pool kết nối, idle timeout và giới hạn concurrent connection khác nhau. Khi client nhìn thấy HTTP 502/504 hoặc lỗi reset connection, nguyên nhân không nhất thiết nằm ở Spring Boot; proxy có thể đã đóng kết nối upstream hoặc ngừng chờ response.

Ví dụ: reverse proxy cố tái sử dụng upstream connection mà server đã đóng vì keep-alive timeout. Client/proxy cần phát hiện socket đã hết hạn và mở kết nối mới đúng cách; không thể chỉ tăng timeout của một phía rồi mặc định lỗi sẽ hết.

Trong vận hành, phải so sánh chính sách timeout của từng hop, khả năng đóng kết nối an toàn, HTTP version và retry semantics. Với POST không idempotent, retry tự động có thể tạo thao tác trùng nếu không có cơ chế chống lặp.

## 15. Connection timeout không giải quyết request chạy lâu

Nếu controller gọi database 60 giây rồi trả kết quả, tăng `server.tomcat.keep-alive-timeout` từ 15 giây lên 90 giây **không biến controller thành nhanh hơn** và không tự đảm bảo request đang xử lý được chờ đủ 90 giây.

Các thời gian chờ khác cần phân biệt:
- Timeout kết nối/câu lệnh database, thường do datasource hoặc database client.
- Timeout outbound HTTP, thường do `RestClient`, `RestTemplate`, `WebClient` hoặc HTTP client bên dưới.
- Timeout tác vụ bất đồng bộ Servlet, ví dụ `spring.mvc.async.request-timeout` khi dùng mô hình MVC async tương ứng.
- Timeout của reverse proxy/load balancer chờ upstream response.
- Chính sách timeout của ứng dụng: cancellation, deadline, circuit breaker, retry.

Trong WebFlux, không nên xem `server.netty.idle-timeout` là deadline tổng thời gian của một pipeline reactive. Nếu nghiệp vụ cần giới hạn 5 giây, hãy dùng timeout ở tầng reactive operation/client phù hợp và xử lý cancellation, resource cleanup, error mapping.

## 16. Các triệu chứng, nguyên nhân và hướng xử lý

| Triệu chứng | Có thể liên quan | Nên kiểm tra |
|---|---|---|
| Client bị đóng socket khi rảnh | Keep-alive/idle timeout hoặc proxy | Timeout từng hop, TCP trace, log đóng kết nối |
| Client thường xuyên mở TCP connection mới | Keep-alive bị tắt/giới hạn quá ngắn, max request thấp | HTTP version, `Connection: close`, client pooling |
| Connection refused hoặc timeout dưới tải lớn | Giới hạn connection, backlog hoặc OS | max-connections, accept-count, file descriptors, số socket |
| Latency cao nhưng CPU thấp | Worker thread bị chặn I/O, queue dài | Busy threads, thread dump, downstream latency |
| Header quá lớn bị từ chối | Parser/limit header ở server hoặc proxy | server.max-http-request-header-size và limit từng hop |
| Upload multipart bị từ chối | Multipart limit, form limit hoặc proxy body size | spring.servlet.multipart.*, server và proxy |
| 502/504 ở ingress | Upstream reset hoặc timeout đọc response | Proxy upstream logs, server logs, response time |
| WebFlux chậm khi handler blocking | Event loop bị chặn | Blocked thread, scheduler, non-blocking client |
| Hết file descriptor / nhiều connection rảnh | Keep-alive dài, giới hạn socket cao | Open sockets, OS ulimit, idle timeouts |

Đọc log cùng timestamp từ client, proxy và Spring Boot để xác định nơi đóng kết nối đầu tiên. Một thông báo client như “Connection reset by peer” chỉ cho biết kết nối bị reset; nó không tự chứng minh đó là connection timeout, keep-alive timeout hay lỗi ứng dụng.

## 17. Quy trình tuning an toàn

1. **Xác nhận runtime thật.** Servlet Tomcat/Jetty/Undertow hay WebFlux Reactor Netty; xem build dependency và startup log.
2. **Xác định mục tiêu.** Ví dụ giảm kết nối rảnh, xử lý thêm concurrent clients, tránh request header quá lớn, bảo vệ upload.
3. **Vẽ các hop kết nối.** Client, proxy, ingress, load balancer và embedded server; ghi timeout từng hop.
4. **Đặt baseline.** Chạy tải đại diện và đo connection count, request/giây, latency, thread, event loop, bộ nhớ và lỗi.
5. **Chỉ đổi một nhóm cấu hình.** Trước hết thay timeouts hoặc connection limits liên quan trực tiếp đến vấn đề, sau đó đo lại.
6. **Đo cả mặt trái.** Keep-alive ngắn tăng handshake, worker thread nhiều tăng CPU/memory, queue dài tăng latency.
7. **Kiểm thử ranh giới.** Request header lớn, client gửi chậm, keep-alive rảnh, nhiều kết nối đồng thời, shutdown/restart.
8. **Ghi kết quả vận hành.** Lưu cấu hình, phiên bản server, workload và kết quả đo để lần triển khai sau có cơ sở so sánh.

Nếu bật Actuator/Micrometer, có thể dùng metric HTTP request và runtime, kết hợp các metric server cụ thể khi được expose. Một số connection/thread metric còn phụ thuộc binder và embedded server; không giả định tên metric hoặc số đo có sẵn trong mọi ứng dụng.

## 18. Những lỗi cấu hình phổ biến

1. **Nhầm client connect timeout và server connection timeout.** Client timeout thường thuộc HTTP client; `server.tomcat.connection-timeout` không điều khiển `WebClient` outbound.
2. **Nhầm keep-alive với request processing timeout.** Socket chờ request tiếp theo là chuyện khác với controller đang xử lý lâu.
3. **Dùng property không đúng server.** `server.tomcat.*` không tự tác động Reactor Netty, Jetty hoặc Undertow.
4. **Nhầm số request/connection với concurrent connections.** Một socket có thể phục vụ nhiều request theo thời gian; nhiều socket có thể đồng thời rảnh.
5. **Cho rằng accept-count tăng throughput.** Queue chỉ giữ thêm kết nối đang chờ; hệ thống xử lý chậm vẫn chậm.
6. **Cho rằng thread idle timeout của Jetty là socket idle timeout.** Chúng điều khiển hai tài nguyên khác nhau.
7. **Bỏ quên proxy.** Một hop phía trước có thể đóng kết nối trước embedded server.
8. **Đặt timeout vô hạn mà không đo tài nguyên.** Rất nhiều kết nối rảnh vẫn tiêu thụ socket và file descriptor.
9. **Thay header/form/upload limit mà không xác định lỗi.** Body JSON, multipart và HTTP header có các giới hạn khác nhau.
10. **Sao chép con số “chuẩn” không có benchmark.** Mức phù hợp phụ thuộc traffic, CPU, memory, giao thức, downstream và OS.

## 19. Checklist ngắn trước khi triển khai

- [ ] Xác nhận đúng web stack, embedded server và phiên bản Spring Boot.
- [ ] Biết chính xác timeout áp dụng cho pha nào của kết nối.
- [ ] Biết HTTP/1.1 hay HTTP/2, số hop proxy và timeout từng hop.
- [ ] Phân biệt keep-alive idle timeout, max keep-alive requests, max connections, accept queue và worker thread.
- [ ] Xác nhận header/body/form/multipart limits phù hợp hợp đồng API.
- [ ] Đã kiểm tra tác động dưới tải thực tế và khi client gửi chậm.
- [ ] Có cách quan sát close/reset/timeout và khôi phục cấu hình nếu benchmark xấu đi.

## 20. Tài liệu tham khảo

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): danh mục chính thức các property `server.tomcat.*`, `server.jetty.*`, `server.undertow.*`, `server.netty.*` và giới hạn HTTP.
- [Spring Boot 3.3 — Reference Documentation](https://docs.spring.io/spring-boot/3.3/reference/): cơ chế nhúng web server, cấu hình và vận hành ứng dụng.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): cơ chế kết nối bền vững và xử lý message trong HTTP/1.1.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): cơ chế stream trên kết nối HTTP/2 và các hạn chế của hop-by-hop header.

**Ghi nhớ:** `connection-timeout`, `keep-alive-timeout`, `idle-timeout`, `max-connections` và `threads.max` là những giới hạn có phạm vi khác nhau. Cấu hình đúng bắt đầu từ việc xác định server thực tế, biết thời điểm áp dụng từng giới hạn và kiểm chứng hành vi trên đường đi đầy đủ của request.
