# HTTP keep-alive: phân biệt kết nối và một yêu cầu trong Spring Boot

## Mục tiêu

Sau bài này, bạn có thể phân biệt **một kết nối mạng** với **một HTTP request**, giải thích cách HTTP keep-alive tái sử dụng kết nối, nhận biết khác biệt giữa HTTP/1.1, HTTP/2 và HTTP/3, đồng thời quan sát hành vi đó trong một ứng dụng Spring Boot chạy trên Servlet container.

Ý cốt lõi: **một kết nối có thể phục vụ nhiều HTTP request; mỗi request vẫn có phương thức, đường dẫn, header, body, quá trình xử lý và response riêng**. Việc kết nối còn mở không có nghĩa một request đang tiếp tục chạy.

## 1. Kết nối khác request như thế nào?

- **Kết nối (connection)** là kênh truyền giữa hai đầu ở một chặng mạng. Với HTTP/1.1 và HTTP/2 thông thường, đó là một kết nối TCP; HTTPS còn có TLS bảo vệ dữ liệu. Một kết nối được thiết lập, có thể ở trạng thái rảnh, được sử dụng lại rồi đóng.
- **HTTP request** là một thông điệp logic mà client gửi: phương thức như `GET`/`POST`, target/path, headers và body nếu có. Server xử lý một request, tạo response cho request ấy; request kết thúc khi việc trao đổi liên quan hoàn tất.
- **HTTP response** có status, headers và body nếu có. Ranh giới của response phải được xác định chính xác để các byte tiếp theo trên cùng kết nối có thể thuộc response/request tiếp theo.
- **HTTP session** (ví dụ `HttpSession`, cookie `JSESSIONID`) là trạng thái ứng dụng theo phiên người dùng; phiên có thể trải qua nhiều request **và nhiều kết nối**. Nó không phải TCP connection.

| Tiêu chí | Kết nối mạng | HTTP request |
| --- | --- | --- |
| Đơn vị | TCP connection (HTTP/1.1, HTTP/2) hoặc QUIC connection (HTTP/3) | Thông điệp HTTP mang method, target, headers, body |
| Vòng đời | Từ khi thiết lập đến lúc đóng; có thể rảnh giữa các lần dùng | Từ khi gửi/nhận yêu cầu đến khi xử lý/trao đổi xong |
| Số lượng | Một kết nối có thể dùng cho nhiều request | Mỗi request là một lần tương tác logic riêng |
| Trạng thái Spring MVC | Do server/connector quản lý, không đồng nhất với một controller invocation | Mỗi lần định tuyến đến handler có request/response context riêng |
| Giữ danh tính người dùng? | Không tự gắn với một phiên đăng nhập | Xác thực/phiên được xác định theo quy tắc của từng request |

Ví dụ, client gọi `GET /products/1` rồi `GET /products/2`. Đó là **hai request khác nhau** dù cả hai có thể đi qua **cùng một TCP connection**.

## 2. HTTP keep-alive giải quyết điều gì?

Trong HTTP/1.1, **persistent connection**, thường gọi là *HTTP keep-alive*, cho phép giữ kết nối sau một cặp request/response để dùng cho các cặp tiếp theo.

Không tái sử dụng kết nối:

```text
TCP/TLS setup -> GET /a -> response /a -> đóng kết nối
TCP/TLS setup -> GET /b -> response /b -> đóng kết nối
```

Có tái sử dụng kết nối:

```text
TCP/TLS setup
    |
    +-> GET /a -> response /a
    |
    +-> GET /b -> response /b
    |
    +-> rảnh trong một khoảng thời gian -> đóng khi cần
```

Nhờ tái sử dụng, client và server có thể tránh một số lần bắt tay TCP/TLS, giảm độ trễ và chi phí tạo socket khi gửi nhiều yêu cầu đến cùng endpoint. **Hai GET vẫn là hai request và hai response**, không bị gộp thành một request. Mỗi lần gửi vẫn tốn thời gian truyền và xử lý dữ liệu.

Giữ kết nối không có nghĩa giữ vĩnh viễn: server, client, proxy hoặc load balancer có thể đóng kết nối do idle timeout, giới hạn số request, vòng đời tiến trình, bảo trì hoặc lỗi mạng.

## 3. Quy tắc cần nhớ trong HTTP/1.1

1. **HTTP/1.1 mặc định ưu tiên kết nối bền vững** khi hai bên hỗ trợ và thông điệp được phân định đúng. Không cần gửi `Connection: keep-alive` trên mọi request để bật tính năng này.
2. Header `Connection: close` cho biết bên gửi muốn đóng kết nối sau khi hoàn thành thông điệp liên quan. Vì vậy, **không được giả định request tiếp theo luôn dùng lại kết nối**.
3. `Connection: keep-alive` và header `Keep-Alive` (nếu xuất hiện) liên quan từng chặng truyền (*hop-by-hop*); giá trị timeout/max do một server nêu ra không phải lời hứa áp dụng toàn đường đi. Header `Keep-Alive` cũng không đồng nghĩa một gói tin heartbeat gửi theo chu kỳ.
4. Với HTTP/1.0, kết nối thường không mặc định bền vững; các triển khai hỗ trợ có thể dùng cơ chế keep-alive theo thỏa thuận. Không suy từ mặc định HTTP/1.1 sang HTTP/1.0.
5. Muốn tái sử dụng HTTP/1.1 connection, các bên phải xác định được điểm kết thúc của từng thông điệp. Tùy trường hợp, framing dùng `Content-Length`, `Transfer-Encoding: chunked` hoặc quy tắc riêng cho status/method; đóng kết nối cũng có thể là dấu kết thúc ở một số kiểu response. Nếu một client bỏ dở response body hoặc framing bị lỗi, connection có thể không tái sử dụng an toàn.

Ví dụ hai response có body khác nhau không thể bị coi là một luồng body duy nhất chỉ vì cùng đi trên một socket. Bộ phân tích HTTP xác định ranh giới thông điệp, còn ứng dụng nhận từng request độc lập.

**Keep-alive không phải HTTP pipelining.** Với HTTP/1.1, trường hợp thông dụng là gửi một request và nhận response trước khi sử dụng lại connection cho request tiếp theo. HTTP/1.1 pipelining có thể gửi nhiều request khi response trước chưa hoàn tất, nhưng hỗ trợ thực tế hạn chế và thứ tự response vẫn bị ràng buộc. Đừng nhầm pipelining với khả năng multiplex của HTTP/2.

## 4. HTTP/2 và HTTP/3 dùng kết nối như thế nào?

| Giao thức | Kết nối nền tảng | Nhiều request trên một kết nối | Điểm khác biệt |
| --- | --- | --- | --- |
| HTTP/1.1 | TCP; HTTPS dùng thêm TLS | Có, thường tái sử dụng theo lượt | Không có multiplexing stream độc lập như HTTP/2 |
| HTTP/2 | TCP + TLS ở cách triển khai HTTPS phổ biến | Có, **nhiều stream có thể hoạt động đồng thời** | Mỗi request/response thuộc một stream riêng, chia sẻ connection |
| HTTP/3 | QUIC chạy trên UDP, tích hợp TLS | Có, nhiều QUIC stream | Không dùng TCP; stream độc lập hơn khi có mất gói |

Trong HTTP/2, một TCP connection có thể mang nhiều request/response trên các stream cùng lúc. Trong HTTP/3, khái niệm tái sử dụng kết nối vẫn có nhưng nền tảng là QUIC. Do đó, cách diễn đạt chính xác là **nhiều HTTP request có thể chia sẻ một kết nối giao thức**, thay vì khẳng định HTTP luôn chạy trên một TCP socket.

Header `Connection` và các header chỉ dành cho connection của HTTP/1.1 không được dùng như cách điều khiển kết nối trong HTTP/2/HTTP/3. Cũng đừng đồng nhất HTTP keep-alive với **TCP keepalive** (probe ở lớp TCP để phát hiện peer mất liên lạc), với cơ chế **PING** của HTTP/2, hoặc với trạng thái phiên đăng nhập.

## 5. Liên hệ với Spring Boot web runtime

Trong ứng dụng Spring Boot MVC dùng `spring-boot-starter-web` và embedded Tomcat:

- **Tomcat/HTTP connector** chấp nhận và quản lý kết nối, phân tích byte thành các HTTP request. Spring MVC nhận request đã được parse, chọn handler/controller, chạy filter/interceptor phù hợp và tạo response.
- **Một connection tái sử dụng không có nghĩa tái sử dụng cùng đối tượng `HttpServletRequest`, cùng transaction, cùng security context hay cùng thread xử lý.** Các dữ liệu có scope theo request được hiểu theo từng request. Không cất dữ liệu riêng của request vào field dùng chung của singleton controller.
- Một client gửi nhiều request có thể được phục vụ bởi các worker thread khác nhau. Ngược lại, một thread trong pool có thể phục vụ request đến từ những connection khác nhau theo thời gian. Không dùng thread ID làm connection ID.
- Cấu hình keep-alive/idle timeout/số lần tái sử dụng phụ thuộc web server, phiên bản và hạ tầng. Khi sử dụng embedded Tomcat, hãy kiểm tra cấu hình connector và reverse proxy đang triển khai; đừng giả định chỉ thay đổi controller là điều khiển được kết nối.
- Ứng dụng WebFlux/Reactor Netty dùng mô hình xử lý khác Servlet MVC, nhưng **request vẫn là đơn vị giao tiếp HTTP** và connection vẫn có thể được tái sử dụng.

Nếu có Nginx/API gateway/load balancer:

```text
Browser -- connection A --> Proxy -- connection B --> Spring Boot
                         Proxy -- connection C --> Spring Boot
```

Connection A không nhất thiết tương ứng một-một với B hoặc C. Proxy có thể tạo pool kết nối phía upstream và tái sử dụng chúng cho nhiều request, thậm chí từ các client khác nhau. Vì vậy, địa chỉ/port mà Servlet thấy thường là **peer trực tiếp của chặng proxy -> app**; nó không tự chứng minh connection của browser đã được tái sử dụng.

Một kết nối còn mở cũng **không đồng nghĩa người dùng vẫn đăng nhập**. Cookie, session, token và kiểm tra quyền thuộc logic xử lý request; không được gắn quyền truy cập vào giả định "đây là socket cũ".

## 6. Thực hành: quan sát hai request qua Spring Boot

Tạo một dự án Spring Boot **3.x, Java 17+**, với dependency `spring-boot-starter-web` (Servlet/Tomcat). Đặt lớp sau trong file `src/main/java/com/example/demo/KeepAliveDemoApplication.java`. Đây là lớp khởi động hoàn chỉnh trong dự án Spring Boot mới đã có dependency nói trên; không phải chương trình chỉ cần `javac` thuần JDK là chạy được.

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.UUID;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class KeepAliveDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(KeepAliveDemoApplication.class, args);
    }

    @GetMapping("/probe")
    public Probe probe(HttpServletRequest request) {
        return new Probe(
            UUID.randomUUID().toString(),
            request.getRemoteAddr() + ":" + request.getRemotePort(),
            request.getProtocol()
        );
    }

    public record Probe(String requestId, String remoteEndpoint, String protocol) {}
}
```

Chạy ứng dụng Maven (hoặc thao tác tương đương với Gradle):

```bash
mvn spring-boot:run
```

Trong **một lệnh curl**, gửi hai URL đến server ở chế độ HTTP/1.1:

```bash
curl --http1.1 -v http://localhost:8080/probe http://localhost:8080/probe
```

Quan sát **hai JSON response**:

- `requestId` là UUID mới cho mỗi request, nên hai giá trị khác nhau.
- `remoteEndpoint` là địa chỉ và cổng nguồn TCP mà **server quan sát**. Trong môi trường localhost trực tiếp, nếu curl tái sử dụng TCP connection, giá trị này thường giống nhau ở hai response.
- `protocol` cho biết giao thức mà Servlet container báo, thường là `HTTP/1.1` trong thử nghiệm này.
- Output chi tiết của `curl -v` có thể cho thấy kết nối đang được dùng lại; câu chữ phụ thuộc phiên bản curl. Vì UUID và cổng động, **không có stdout cố định** để chép nguyên xi.

Đối chiếu bằng cách yêu cầu đóng kết nối:

```bash
curl --http1.1 -v -H "Connection: close" http://localhost:8080/probe http://localhost:8080/probe
```

Khi server thực hiện yêu cầu đóng kết nối sau response, curl phải mở kết nối khác cho URL tiếp theo. Hai `requestId` vẫn khác nhau trong cả hai trường hợp; chính **connection có được dùng lại hay không** mới thay đổi.

**Lưu ý khi diễn giải:** cùng `remoteEndpoint` là dấu hiệu hữu ích trong thí nghiệm đơn giản, **không phải định danh connection được bảo đảm toàn cục**. Port có thể được tái sử dụng theo thời gian; proxy/NAT thay đổi điểm nhìn; timeout hoặc chính sách server có thể làm hai request trong lệnh đầu vẫn dùng hai connection. Nếu chạy `curl` thành hai tiến trình/lệnh riêng, mỗi tiến trình có pool kết nối riêng và không dùng lại socket của tiến trình trước.

## 7. Tác động đến hiệu năng và vận hành

**Lợi ích:** giảm việc tạo kết nối và bắt tay TLS lặp lại, nhất là khi client có nhiều request nối tiếp; connection pooling phía HTTP client và proxy thường khai thác điều này.

**Chi phí và giới hạn:** mỗi connection đang mở có thể tốn socket, file descriptor, bộ nhớ và trạng thái trên server, proxy hoặc client. Nhiều connection rảnh kéo dài cần timeout/giới hạn hợp lý. Keep-alive **không tự làm cho controller nhanh hơn**, không xóa độ trễ xử lý database, và không đảm bảo một connection tồn tại tới request kế tiếp.

Khi điều tra một ứng dụng Spring Boot, hãy phân biệt:

- **Số request**: tải logic mà app phải xử lý; nên theo dõi request rate, response time, status/error.
- **Số connection đang mở/rảnh**: tài nguyên transport của connector, proxy và client pool; có thể nhiều hoặc ít hơn số request đang chạy.
- **Số request đồng thời**: phụ thuộc giao thức, thread pool/event loop, cấu hình và cách ứng dụng xử lý; không thể suy trực tiếp chỉ từ số socket.
- **Số HTTP session đang tồn tại**: đơn vị trạng thái ứng dụng độc lập với số request và connection.

Nếu client thường xuyên tạo socket mới, kiểm tra `Connection: close`, việc tiêu thụ response body, idle timeout của server/proxy, giới hạn connection pool và HTTP version được thương lượng. Nếu gặp lỗi khi một pooled connection đã bị bên kia đóng, xử lý timeout/retry đúng loại thao tác; **không tự động gửi lại một POST có tác dụng phụ khi chưa biết lần đầu đã được thực hiện hay chưa**.

## 8. Những hiểu lầm thường gặp

**“Một TCP connection chỉ có đúng một HTTP request.”** Sai đối với kết nối persistent. HTTP/1.1 có thể tái sử dụng lần lượt; HTTP/2 còn multiplex được nhiều stream.

**“Keep-alive nghĩa là request chưa kết thúc.”** Sai. Request trước có thể hoàn tất, response đã được đọc hết, còn connection chỉ đang rảnh để chờ request mới.

**“Thêm `Connection: keep-alive` chắc chắn sẽ giữ socket mãi.”** Sai. HTTP/1.1 thường persistent mặc định, nhưng bất kỳ bên nào liên quan có thể đóng theo chính sách hoặc khi có lỗi. Header này không điều khiển end-to-end qua mọi proxy.

**“Hai request dùng cùng connection thì cùng user/session/transaction/thread.”** Sai. Connection thuộc transport; session, xác thực, request scope và transaction được xác định theo cơ chế riêng.

**“Giữ kết nối là cách gửi nhiều request đồng thời ở mọi bản HTTP.”** Sai. Cần phân biệt reuse tuần tự trong HTTP/1.1 với multiplexing của HTTP/2/HTTP/3.

## 9. Tự kiểm tra

1. Một browser gửi ba request `GET` liên tiếp trên một connection HTTP/1.1. Có bao nhiêu request? **Ba**; số connection dùng có thể là **một**.
2. Request `GET /a` đã trả đủ body, socket còn mở. Request còn sống không? **Không**; chỉ connection vẫn sẵn sàng để tái sử dụng.
3. Hai request có cùng `remoteEndpoint` nhưng `requestId` khác nhau trong demo. Điều này nói gì? **Có khả năng chúng dùng chung kết nối được server quan sát**, song mỗi request vẫn tách biệt; cần loại trừ ảnh hưởng proxy và việc tái sử dụng port trước khi khẳng định tuyệt đối.
4. Trong HTTP/2, hai request đang chạy đồng thời có cần hai TCP connection? **Không nhất thiết**; chúng có thể là hai stream trên cùng một connection.
5. Đóng keep-alive connection có tự hủy `HttpSession` không? **Không**; vòng đời session do cơ chế session, timeout và ứng dụng quyết định.

**Ghi nhớ:** *Connection là đường vận chuyển có thể tái sử dụng; request là một thông điệp và một lần xử lý độc lập.* Đây là điểm mấu chốt để hiểu keep-alive, connection pooling, HTTP/2 multiplexing và hành vi của Spring Boot web server.