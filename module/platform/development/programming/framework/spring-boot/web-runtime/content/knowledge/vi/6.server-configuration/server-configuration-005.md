# Giới hạn kích thước header yêu cầu và cấu hình theo máy chủ trong Spring Boot

## 1. Vì sao HTTP request header cần giới hạn?

HTTP request mang metadata qua các header như `Host`, `Authorization`, `Cookie`, `Accept`, `User-Agent`, `Content-Type`, `Forwarded` hoặc các trường tùy biến. Embedded web server phải đọc và giải mã header trước khi request được chuyển tới Spring MVC controller, Spring WebFlux handler hoặc các thành phần xử lý nghiệp vụ.

Header quá lớn có thể xuất hiện khi cookie tích tụ, JWT chứa nhiều claim, proxy gắn thêm thông tin trace/xác thực, hoặc client gửi header tùy biến dài. Nếu server không đặt giới hạn phù hợp, một lượng lớn dữ liệu header từ nhiều request đồng thời có thể làm tăng tiêu thụ bộ nhớ, gây quá tải parser hoặc tạo điều kiện cho tấn công từ chối dịch vụ (DoS).

Mục tiêu của cấu hình header limit là:

- Cho phép những request hợp lệ trong giới hạn kỹ thuật và nghiệp vụ.
- Ngăn request có header lớn bất thường chiếm nhiều tài nguyên.
- Giữ giới hạn nhất quán giữa client, CDN/WAF, reverse proxy, API gateway và embedded server.
- Phân biệt đúng giới hạn header với request body, file upload, form và URL.
- Hiểu sự khác biệt giữa Tomcat, Jetty, Undertow và Reactor Netty.

**Lưu ý:** Header bị từ chối ở HTTP parser thường chưa đi tới controller hoặc `@ControllerAdvice`; việc debug cần bắt đầu từ log web server hoặc proxy, không chỉ từ mã Java nghiệp vụ.

## 2. Header size được tính như thế nào?

Một request HTTP/1.1 có cấu trúc dạng:

```http
GET /api/orders?status=paid HTTP/1.1
Host: example.com
Authorization: Bearer eyJhbGciOi...
Cookie: session=abc123
Accept: application/json

```

Cần phân biệt các loại giới hạn:

| Giới hạn | Nội dung | Ví dụ |
|---|---|---|
| Request header size | Lượng dữ liệu header HTTP cho phép, theo quy tắc của từng server | Tổng các header hoặc kích thước từng field |
| Single header field size | Kích thước một header cụ thể | Một field `Cookie` dài |
| Header count | Số header field tối đa | 200 field dù mỗi field rất ngắn |
| Request line / initial line | Method + request-target + HTTP version trong HTTP/1.x | `GET /path?... HTTP/1.1` |
| Request body | Dữ liệu bên trong payload, JSON, multipart, file | File 10MB không nằm trong header |

Giá trị `16KB` trong Spring Boot dùng kiểu `DataSize` và tương đương **16 × 1024 = 16.384 byte**. Byte trên giao thức không phải luôn bằng số ký tự `String.length()` trong Java. Một số server còn tính dấu phân cách, whitespace, CRLF và request line.

Đặc biệt, tài liệu Spring Boot chỉ rõ **Tomcat áp dụng ngưỡng cho tổng request line, tên và giá trị các header**; **Netty áp dụng ngưỡng riêng cho từng header field khi giải mã**. Do đó, cùng cấu hình `16KB` không cam kết cùng kết quả cho mọi embedded server.

## 3. Cấu hình chung trong Spring Boot 3.x và 4.x

Thuộc tính chuẩn:

```properties
# application.properties
server.max-http-request-header-size=16KB
```

Tương đương trong YAML:

```yaml
# application.yml
server:
  max-http-request-header-size: 16KB
```

Theo danh sách Common Application Properties của Spring Boot 3.5 và 4.0, giá trị mặc định là **8KB**. Đây là ngưỡng mặc định của property Spring Boot; không nên nhầm với giá trị mặc định của server chạy độc lập không do Spring Boot cấu hình.

Có thể lấy giá trị từ biến môi trường:

```properties
server.max-http-request-header-size=${HTTP_REQUEST_HEADER_LIMIT:16KB}
```

Hoặc truyền qua command line khi đã có JAR Spring Boot:

```bash
java -jar app.jar --server.max-http-request-header-size=16KB
```

Nếu dùng nhiều profile, hãy kiểm tra cấu hình hiệu lực của profile đang chạy. Property `server.max-http-request-header-size` được Spring Boot ánh xạ tới factory của embedded server tương ứng, nhưng cách giải mã và từ chối request do server quyết định.

**Khi nào nên dùng property?** Với nhu cầu đặt request header limit phổ thông, luôn ưu tiên thuộc tính này trước khi tự viết `WebServerFactoryCustomizer`. Customizer phù hợp nếu cần thiết lập API cấp thấp mà property chưa hỗ trợ, ví dụ cấu hình đặc thù cho một loại connector hoặc server protocol.

### Thay đổi so với Spring Boot 2.x

Các ví dụ cũ có thể sử dụng:

```properties
server.max-http-header-size=16KB
```

Spring Boot 3.0 đã thay bằng `server.max-http-request-header-size` để xử lý sự thiếu nhất quán trước đó. Tên cũ ảnh hưởng cả request và response với Tomcat, còn với Jetty, Netty và Undertow chủ yếu áp dụng cho request. Tên mới tập trung vào giới hạn **request header**.

Khi nâng cấp từ Spring Boot 2.x lên 3.x/4.x, nên đổi sang property mới và kiểm thử lại trên web server đang dùng. Không kỳ vọng cấu hình request header có thể đồng thời điều chỉnh response header.

## 4. So sánh các embedded server

| Server | Stack phổ biến | Cách áp dụng request header limit | Điểm cần kiểm tra |
|---|---|---|---|
| **Tomcat** | Spring MVC / Servlet | Tổng request line và headers, gồm nhiều overhead của HTTP/1.x | `maxHttpRequestHeaderSize`, bộ đệm và bộ nhớ |
| **Jetty** | Spring MVC / Servlet; một số adapter reactive | Cấu hình HTTP parser qua `HttpConfiguration` | Request và response có setting riêng |
| **Undertow** | Servlet trên phiên bản được hỗ trợ | `UndertowOptions.MAX_HEADER_SIZE` | Byte limit khác giới hạn số header |
| **Reactor Netty** | Spring WebFlux | Theo mô tả của Boot: giới hạn từng header field | Initial line và HTTP/2 có những giới hạn khác |

Các thư viện server thay đổi giữa phiên bản. Bảng mô tả nguyên tắc trong môi trường Spring Boot thông thường; cần xem HTTP version và dependency thực tế nếu muốn đưa ra cam kết chính xác tại ngưỡng biên.

## 5. Tomcat: tổng request line và các header

Tomcat HTTP Connector có tham số `maxHttpRequestHeaderSize`. Với HTTP/1.x, giới hạn áp dụng cho lượng byte nhận được của request line cùng header, gồm tên field, giá trị field, khoảng trắng, ký tự kết thúc dòng và các phần liên quan.

Ví dụ giả định:

- Request line và các header thông thường: khoảng 1,5KB.
- `Authorization`: khoảng 5KB.
- `Cookie`: khoảng 6KB.

Tổng đã trên 12KB; một request như vậy có thể vượt limit 8KB của Tomcat dù không field đơn lẻ nào trên 8KB.

Cấu hình Spring Boot:

```properties
server.max-http-request-header-size=16KB
```

Khi cần tách response header limit:

```properties
server.max-http-request-header-size=16KB
server.tomcat.max-http-response-header-size=16KB
```

Dòng thứ hai kiểm soát giới hạn response header ở Tomcat trong các phiên bản Boot hỗ trợ, ví dụ response nhiều `Set-Cookie` hoặc `Location` dài; không giúp request header lớn được chấp nhận.

Tomcat có các tham số cấp Connector khác như `maxHeaderCount` để hạn chế số header. Đây là giới hạn về số lượng, khác `maxHttpRequestHeaderSize`. Dùng `WebServerFactoryCustomizer<TomcatServletWebServerFactory>` khi thật sự cần thay đổi các thuộc tính connector không được expose qua property, và phải dùng import/phương thức đúng với phiên bản Spring Boot.

**Cảnh báo tài nguyên:** tài liệu Apache Tomcat nhấn mạnh `maxHttpRequestHeaderSize` cao làm tăng mức cấp phát bộ đệm cho các request đang xử lý. Tăng lên 1MB cho hàng trăm request đồng thời có thể gây áp lực lớn lên heap. Không đặt ngưỡng hàng MB chỉ để giải quyết một số cookie/JWT không hợp lý.

Nếu Tomcat được triển khai **bên ngoài** dưới dạng servlet container quản lý WAR, việc cấu hình listener/Connector thuộc trách nhiệm server bên ngoài. Property embedded server trong Spring Boot không được xem là cơ chế chung để điều khiển mọi Tomcat bên ngoài.

## 6. Jetty: cấu hình request và response riêng

Jetty cung cấp API `HttpConfiguration.setRequestHeaderSize(int)` và `setResponseHeaderSize(int)`; cách áp dụng cụ thể phụ thuộc phiên bản Jetty và transport.

Với request header, cấu hình Spring Boot chung vẫn là:

```properties
server.max-http-request-header-size=16KB
```

Trong các phiên bản Spring Boot hỗ trợ, có thuộc tính Jetty riêng cho response:

```properties
server.jetty.max-http-response-header-size=16KB
```

Không nhầm request size với response size; tăng response limit chỉ giúp server tạo response header lớn hơn, không thay đổi việc phân tích request từ client.

Nếu cần customizer Jetty chuyên biệt, tìm đúng web server factory và API `HttpConfiguration` của phiên bản đang chạy. Không sao chép đoạn code dành cho Jetty 9/11 để giả định tương thích hoàn toàn với Jetty 12. Hãy ưu tiên cấu hình bằng property chung trước khi can thiệp cấu trúc connector.

## 7. Undertow: byte limit khác giới hạn số lượng

Undertow có option `UndertowOptions.MAX_HEADER_SIZE`, biểu diễn giới hạn kích thước HTTP request header theo byte. Trong Spring Boot, cách cơ bản là:

```properties
server.max-http-request-header-size=16KB
```

Undertow có thêm giới hạn số lượng header:

```properties
server.undertow.max-headers=200
```

Hai cấu hình kiểm soát hai điều khác nhau:

- Request chứa 220 header ngắn có thể bị chặn bởi `max-headers=200`, dù tổng byte dưới limit.
- Request chỉ có vài header rất dài vẫn có thể bị chặn bởi giới hạn kích thước byte.

Các thuộc tính như `server.undertow.max-cookies` hay `server.undertow.max-parameters` cũng độc lập; không thể thay bằng header byte limit.

Khi cần sử dụng `server.undertow.options.server.*`, phải kiểm tra tên `UndertowOptions` và cách binding thuộc tính đúng với phiên bản Spring Boot/Undertow. Không nên ghi đè option thấp tầng nếu property chung đã giải quyết nhu cầu.

## 8. Reactor Netty và Spring WebFlux

Spring Boot thường sử dụng Reactor Netty làm server mặc định cho ứng dụng Spring WebFlux. Với Reactor Netty, `server.max-http-request-header-size` được Spring Boot mô tả là giới hạn đối với **từng header field** thay vì tổng như Tomcat. Do đó, một request nhiều field nhỏ có thể có kết quả khác với cùng request đi qua Tomcat.

```properties
server.max-http-request-header-size=16KB
```

Một tùy chọn riêng trong Spring Boot là:

```properties
server.netty.max-initial-line-length=4KB
```

Property này liên quan độ dài initial request line, không thay thế kích thước header field. Nếu URL/query string quá dài, tăng header limit chưa chắc giải quyết được lỗi parser.

Reactor Netty có API decoder như `maxHeaderSize(int)` trên `HttpRequestDecoderSpec`. Khi dùng cấu hình sâu qua customizer, phải dựa trên phiên bản thực tế của Reactor Netty và kiểm tra ảnh hưởng đến HTTP/1.1/HTTP/2, thay vì giả định API decoder của mọi bản là giống nhau.

## 9. HTTP/1.1 và HTTP/2 không có phép đo hoàn toàn giống nhau

HTTP/1.1 truyền request line và header field ở dạng cú pháp văn bản theo giao thức. HTTP/2 dùng các header block nén bằng HPACK và các pseudo-headers như `:method`, `:path`, `:scheme`, `:authority`.

Không thể lấy số byte đã nén trên đường truyền HTTP/2 rồi so sánh trực tiếp với limit request header của Tomcat ở HTTP/1.1. Một server/proxy HTTP/2 có thể kiểm soát kích thước header list sau giải mã và từ chối request theo cách riêng.

Để xác định một lỗi chỉ xảy ra trên HTTP/2, hãy thử cùng request qua hai phiên bản HTTP và đọc log đúng giao thức. Đừng dựa vào một phép tính duy nhất trên `Cookie` hoặc `Authorization` mà bỏ qua pseudo-headers hay header do proxy tự thêm.

## 10. Reverse proxy, gateway, CDN và WAF

Trong production, đường đi phổ biến là:

```text
HTTP client
   |
CDN / WAF
   |
Ingress / API gateway / Reverse proxy
   |
Embedded Tomcat / Jetty / Undertow / Reactor Netty
   |
Spring MVC / WebFlux
```

Mỗi tầng có thể đặt giới hạn khác nhau. Ví dụ:

- Gateway chỉ chấp nhận 8KB; Spring Boot 16KB: request 12KB bị chặn tại gateway.
- Gateway 32KB; Tomcat 8KB: request 12KB có thể tới backend rồi bị Tomcat từ chối.
- Proxy thêm nhiều header `Forwarded`, `X-Forwarded-*` hoặc tracing: tổng header nhận ở backend có thể lớn hơn client gửi.

Với Nginx, có các thiết lập như `client_header_buffer_size` và `large_client_header_buffers`; chúng có cách tính riêng cho request line hoặc từng field. Không coi một directive của Nginx tương đương hoàn toàn với property Spring Boot. Với Envoy, Traefik hoặc Kubernetes Ingress Controller, dùng tài liệu đúng sản phẩm và phiên bản.

Khi kiểm tra production, quan sát status và log tại từng tầng, request ID, loại server và HTTP version. Ngưỡng thấp nhất dọc đường đi thường là nơi request bị từ chối đầu tiên.

## 11. Khi header vượt giới hạn thì ứng dụng phản hồi ra sao?

HTTP có status `431 Request Header Fields Too Large`, nhưng kết quả thực tế không thống nhất giữa parser/server/proxy:

- Có hệ thống trả `400 Bad Request` kèm thông báo header quá lớn.
- Có hệ thống trả `431 Request Header Fields Too Large`.
- Có hệ thống đóng kết nối, khiến client thấy `connection reset`, `EOF` hoặc lỗi giao thức.
- HTTP/2 có thể xử lý qua stream reset hoặc cơ chế từ chối riêng của implementation.

Vì vậy, **không viết kiểm thử cứng rằng header quá lớn chắc chắn luôn trả 431**. Cần xác minh hành vi thực tế của stack đang triển khai.

Khi parser chặn request trước khi tạo Spring MVC/WebFlux handler, `@RestController`, `Filter` hoặc `@ControllerAdvice` có thể không thấy request. Hãy kiểm tra access log của server, proxy log, stacktrace decoder và network trace thay vì chỉ debug controller.

## 12. Tạo một ứng dụng Spring Boot thử nghiệm

Giả sử project Spring Boot 3.x hoặc 4.x đã có `spring-boot-starter-web` và `@SpringBootApplication`, thêm controller:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
server.max-http-request-header-size=8KB
```

Dùng Maven Wrapper của project:

```bash
./mvnw spring-boot:run
```

Kiểm tra request ngắn:

```bash
curl -i http://localhost:8080/ping
```

Nếu ứng dụng khởi động đúng, endpoint trả body:

```text
pong
```

Đoạn controller không phải chương trình Java độc lập; phải chạy bên trong project Spring Boot có starter web và class main. Không nhầm output body `pong` với toàn bộ response/status/header hay log của Spring Boot.

## 13. Kiểm thử header dài bằng Java 17 không cần thư viện ngoài

Dùng client standalone để gửi header `X-Header-Size-Probe` với giá trị gồm nhiều ký tự ASCII `a`. File **`HeaderLimitProbe.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.io.IOException;

public class HeaderLimitProbe {

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println(
                "Usage: java HeaderLimitProbe <url> <headerValueLength>");
            System.exit(2);
        }

        String url = args[0];
        int length = Integer.parseInt(args[1]);
        if (length < 0 || length > 100_000) {
            throw new IllegalArgumentException(
                "headerValueLength must be between 0 and 100000");
        }

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                .header("X-Header-Size-Probe", "a".repeat(length))
                .GET()
                .build();

        try {
            HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());
            System.out.println("HTTP status: " + response.statusCode());
        } catch (IOException e) {
            System.out.println(
                "I/O error: " + e.getClass().getSimpleName());
        }
    }
}
```

Mã sử dụng API Java 17 và biên dịch độc lập, không cần dependency Spring. `HttpClient` không được đặt trong try-with-resources vì Java 17 chưa hỗ trợ phương thức `close()` như các bản JDK mới hơn.

Biên dịch:

```bash
javac HeaderLimitProbe.java
```

Chạy với server Spring Boot ví dụ ở cổng 8080:

```bash
java HeaderLimitProbe http://localhost:8080/ping 1000
java HeaderLimitProbe http://localhost:8080/ping 12000
```

Kết quả phụ thuộc server, endpoint và môi trường. Với request hợp lệ mà server trả `200`, chương trình in:

```text
HTTP status: 200
```

Nếu header bị từ chối, có thể nhận `400`, `431` hoặc một lỗi I/O; không có output cố định cho trường hợp vượt ngưỡng. `headerValueLength` là số ký tự `a` trong **một field**, chưa tính tên field, dấu phân cách, request line và header do JDK tự sinh.

Để kiểm tra ranh giới, chạy cả trường hợp nhỏ và lớn gần giới hạn, rồi quan sát log. Với Tomcat, tổng các thành phần có thể vượt ngưỡng trước khi riêng `X-Header-Size-Probe` đạt 8KB. Với Reactor Netty, cần chú ý giới hạn cho từng field theo tài liệu Spring Boot.

## 14. Không nhầm lẫn với body, multipart và response header

| Tên cấu hình/khái niệm | Điều kiểm soát |
|---|---|
| `server.max-http-request-header-size` | Kích thước HTTP request header, theo server |
| `server.tomcat.max-http-response-header-size` | Kích thước response header của Tomcat |
| `server.jetty.max-http-response-header-size` | Kích thước response header của Jetty |
| `server.netty.max-initial-line-length` | Độ dài request initial line của Netty |
| `server.undertow.max-headers` | Số lượng header Undertow nhận |
| `server.tomcat.max-http-form-post-size` | Nội dung form POST mà Tomcat xử lý |
| `spring.servlet.multipart.max-request-size` | Tổng kích thước multipart request trong Servlet stack |
| `spring.codec.max-in-memory-size` | Bộ đệm dùng cho codec trong các trường hợp tương ứng |

Ví dụ: upload file 10MB bị từ chối thường liên quan multipart/body limit, không giải quyết bằng cách tăng header limit. Ngược lại, JWT rất dài trong `Authorization` có thể gây lỗi request header ngay cả khi body rỗng.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng giải quyết |
|---|---|---|
| Đã cấu hình 16KB nhưng còn lỗi | Proxy/WAF vẫn ở 8KB hoặc property không hiệu lực | Kiểm tra log theo từng chặng và cấu hình/profile |
| Tomcat chặn dù từng header dưới 16KB | Tomcat tính tổng request line và các header | Đo tổng byte, giảm Cookie/JWT không cần thiết |
| Undertow chặn nhiều header nhỏ | `server.undertow.max-headers` giới hạn số lượng | Kiểm tra số field và byte limit riêng |
| Netty xử lý khác Tomcat | Ngưỡng được áp dụng theo parser khác nhau | Test đúng embedded server/HTTP version |
| `400` nhưng controller không chạy | Request bị parser từ chối | Xem connector/decoder hoặc proxy log |
| Upload bị từ chối sau khi tăng header limit | Body hoặc multipart limit riêng | Xem `spring.servlet.multipart.*` và server body settings |
| Chỉ HTTP/2 gặp lỗi | Header list/decoder và pseudo-headers khác HTTP/1.1 | Kiểm tra cấu hình HTTP/2 của cả proxy và backend |
| Sau nâng cấp Boot property không như cũ | Sử dụng `server.max-http-header-size` cũ | Chuyển sang `server.max-http-request-header-size` |
| Tăng limit nhiều làm heap/CPU tăng | Bộ đệm request và lưu lượng bất thường | Hạ ngưỡng, giảm nguồn header, đo tải thực tế |

### Quy trình debug có hệ thống

1. Ghi lại request ID, HTTP version, status/lỗi kết nối, environment.
2. Xác định request bị chặn tại CDN/WAF, gateway hay Spring Boot embedded server.
3. Kiểm tra số lượng header, kích thước lớn nhất của một field, tổng byte và độ dài request line.
4. Xác định chính xác server Tomcat/Jetty/Undertow/Reactor Netty và phiên bản.
5. Đọc `server.max-http-request-header-size` hiệu lực cùng cấu hình proxy.
6. Kiểm tra xem cookie, JWT hoặc header trace có dữ liệu dư thừa không.
7. Tối ưu nguồn header trước; chỉ nâng limit nếu có lý do vận hành rõ ràng.
8. Test request thường, sát ngưỡng và vượt ngưỡng; kiểm tra memory và error rate sau thay đổi.

Không log nguyên văn `Authorization`, `Cookie` hoặc token nhạy cảm chỉ để đo kích thước; có thể log **độ dài** và một định danh request an toàn thay vì nội dung.

## 16. Checklist triển khai

- Xác định phiên bản Spring Boot, embedded server và HTTP/1.1 hay HTTP/2.
- Dùng `server.max-http-request-header-size` làm cấu hình cơ bản cho request header.
- Hiểu rằng mặc định của Spring Boot 3.5/4.0 là 8KB; thay đổi theo nhu cầu thực tế.
- Hiểu sự khác nhau về phép tính limit giữa Tomcat và Netty.
- Kiểm tra request line, số lượng header, response header và body là các giới hạn khác nhau.
- Xác minh config của mọi reverse proxy/CDN/WAF/Ingress.
- Đo request hợp lệ, ranh giới và request vượt ngưỡng trên đúng runtime.
- Tránh nâng ngưỡng lên mức rất cao gây tăng bộ nhớ và nguy cơ DoS.
- Ưu tiên thu gọn Cookie, JWT và tracing headers trước khi mở rộng ngưỡng.
- Ghi nhận kết quả kiểm thử và theo dõi lỗi 400/431/I/O sau triển khai.

## 17. Tài liệu tham khảo

- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 4.0 — Common Application Properties: https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html
- Spring Boot 3.0 Migration Guide (đổi tên header property): https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide
- Apache Tomcat 10.1 — HTTP Connector: https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
- Jetty 12 — HttpConfiguration: https://javadoc.jetty.org/jetty-12/org/eclipse/jetty/server/HttpConfiguration.html
- Undertow — `UndertowOptions.MAX_HEADER_SIZE`: https://github.com/undertow-io/undertow/blob/main/core/src/main/java/io/undertow/UndertowOptions.java
- Reactor Netty — HttpDecoderSpec: https://docs.spring.io/projectreactor/reactor-netty/docs/current/api/reactor/netty/http/HttpDecoderSpec.html
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
