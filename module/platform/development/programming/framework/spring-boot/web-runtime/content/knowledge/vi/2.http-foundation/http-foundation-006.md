# Phân biệt HTTP/1.1, HTTP/2 và yêu cầu TLS

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** Nền tảng HTTP

## 1. Mục tiêu và cách phân biệt đúng

Sau bài này, bạn cần giải thích được HTTP/1.1 và HTTP/2 khác nhau ở cách truyền thông điệp, cách xử lý nhiều yêu cầu đồng thời, cách mã hóa header và ảnh hưởng tới độ trễ; đồng thời phân biệt rõ **phiên bản HTTP**, **HTTPS/TLS** và **cách triển khai Spring Boot**.

Ba câu cần nhớ:

- **HTTP/1.1 và HTTP/2** đều thực hiện những ngữ nghĩa HTTP cốt lõi: method, URI, status, header, request body, response body. Controller không cần đổi nghiệp vụ chỉ vì đường truyền sử dụng HTTP/2.
- **TLS** là lớp bảo vệ kết nối, cung cấp mã hóa, kiểm tra tính toàn vẹn và xác thực máy chủ bằng chứng chỉ. **HTTPS không đồng nghĩa với HTTP/2**: HTTP/1.1 cũng chạy trên TLS.
- **HTTP/2 có hai cách sử dụng liên quan TLS:** **h2** là HTTP/2 qua TLS (thông dụng với trình duyệt); **h2c** là HTTP/2 qua TCP không TLS (có thể dùng trong một số kết nối nội bộ). Khi dùng h2, đặc tả yêu cầu TLS 1.2 trở lên.

## 2. HTTP/1.1 hoạt động thế nào?

HTTP/1.1 sử dụng thông điệp có dòng bắt đầu và header ở dạng văn bản, phần body theo quy tắc đóng khung thông điệp. Ví dụ minh họa request và response của một tài nguyên đơn giản:

~~~http
GET /hello HTTP/1.1
Host: example.test
Accept: text/plain

~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Length: 2

OK
~~~

Đường truyền thực tế dùng ký tự kết thúc dòng theo chuẩn HTTP; đây là bản trình bày để người đọc dễ theo dõi. Method **GET**, status **200**, header và body sẽ vẫn mang cùng ý nghĩa ở HTTP/2.

Các điểm vận hành quan trọng:

1. **Kết nối có thể tái sử dụng.** HTTP/1.1 mặc định hỗ trợ kết nối duy trì (persistent connection): nhiều cặp request/response có thể dùng lại một TCP connection, tránh kết nối lại cho từng tài nguyên. Duy trì kết nối không tự động tạo cơ chế truyền xen kẽ response.
2. **Một connection HTTP/1.1 thông thường không đa luồng request độc lập.** Pipelining từng được định nghĩa để gửi nhiều request trước khi nhận response, nhưng response vẫn phải được trả theo thứ tự; kỹ thuật này ít được trình duyệt sử dụng vì độ phức tạp và hiện tượng chặn đầu hàng.
3. **Để tải đồng thời, client thường mở nhiều TCP connection** tới cùng máy chủ hoặc sử dụng các cơ chế quản lý pool kết nối. Cách này tiêu tốn thêm socket, handshake và tài nguyên.
4. **Head-of-line blocking ở tầng HTTP:** trên cùng một kết nối/pipeline, response chậm ở phía trước có thể trì hoãn response phía sau. HTTP/1.1 không có khái niệm stream độc lập như HTTP/2.

Ví dụ: trang cần tải CSS, JavaScript và ảnh; với HTTP/1.1, trình duyệt có thể mở nhiều connection để tải đồng thời, nhưng trong từng connection vẫn chịu các giới hạn sắp thứ tự tương ứng.

## 3. HTTP/2 thay đổi những gì?

HTTP/2 được chuẩn hóa hiện hành tại **RFC 9113**. Nó giữ nguyên ngữ nghĩa HTTP và thay cách biểu diễn trên kết nối TCP thành **binary framing**:

- **Frame** là đơn vị truyền tải, gồm những loại như **HEADERS** (thông tin request/response), **DATA** (body), **SETTINGS** (thỏa thuận tham số kết nối) và **WINDOW_UPDATE** (điều khiển luồng).
- **Stream** là luồng logic gắn với một trao đổi request/response. Nhiều stream đồng thời tồn tại trên cùng một TCP connection; các frame của những stream khác nhau có thể truyền xen kẽ.
- **Multiplexing** cho phép một response chậm không bắt các response khác phải đợi theo thứ tự ở tầng HTTP/2. Tính song song vẫn chịu giới hạn về stream đồng thời, bộ nhớ, điều khiển luồng và tài nguyên máy chủ.
- **HPACK** nén thông tin header, giúp giảm sự lặp lại của tên/giá trị header qua nhiều request trên một connection. **HPACK không phải nén toàn bộ response body**; nén nội dung bằng gzip/br là cơ chế khác.
- **HTTP/2 không phải văn bản HTTP/1.1 thêm mã hóa.** Các trường logic của HTTP/2 được gửi trong HEADERS frame theo cách mã hóa đặc tả; một gói tin không nhất thiết chứa trọn một request.

Biểu diễn logic của cùng request ở HTTP/2 (đây **không phải bytes thô gửi trên mạng**):

~~~text
:method: GET
:scheme: https
:authority: example.test
:path: /hello
accept: text/plain
~~~

Bốn trường có dấu hai chấm đầu là **pseudo-header** biểu diễn method, scheme, authority và path. HTTP/2 thường yêu cầu tên header dạng chữ thường trong phần header được mã hóa. Những gì application thấy qua Spring MVC vẫn là một request GET tới đường dẫn /hello.

**Giới hạn quan trọng:** HTTP/2 vẫn truyền trên **TCP**. Nếu một TCP segment bị mất, TCP phải khôi phục byte theo thứ tự, có thể khiến các stream HTTP/2 cùng connection cùng bị chậm. HTTP/2 cải thiện việc chặn đầu hàng **ở tầng HTTP**, nhưng **không loại bỏ TCP head-of-line blocking**. Đừng mặc định mọi tình huống HTTP/2 đều nhanh hơn HTTP/1.1.

## 4. Bảng so sánh thực dụng

| Khía cạnh | HTTP/1.1 | HTTP/2 |
| --- | --- | --- |
| Ngữ nghĩa method/status/URI | Có | Giữ nguyên |
| Biểu diễn trên wire | Dòng bắt đầu và header dạng văn bản | Frame nhị phân và các stream logic |
| Nhiều yêu cầu trên một connection | Tái sử dụng tuần tự; pipelining có giới hạn | Multiplex nhiều stream trên cùng connection |
| Chặn đầu hàng ở tầng HTTP | Có thể xảy ra rõ trong pipeline | Giảm đáng kể nhờ frame xen kẽ |
| Mất gói ở tầng TCP | Ảnh hưởng connection | Vẫn có thể ảnh hưởng mọi stream chung connection |
| Header | Lặp lại theo từng thông điệp | HPACK nén header |
| TLS | Không bắt buộc ở giao thức HTTP/1.1; HTTPS dùng TLS | h2 dùng TLS 1.2+; h2c là TCP không TLS |
| Môi trường phổ biến | HTTP hoặc HTTPS, nhiều hệ thống cũ/mới | Trình duyệt qua HTTPS/h2; một số tuyến nội bộ h2c |

HTTP/2 có tính năng server push trong đặc tả, nhưng hỗ trợ và lợi ích thực tiễn thay đổi theo client; **không** nên xem server push là điều kiện cần để dùng HTTP/2 hoặc là lý do chính để chuyển đổi.

## 5. TLS và HTTPS: các yêu cầu chính xác

**TLS (Transport Layer Security)** bảo vệ dữ liệu trên đường truyền giữa hai đầu TLS: mã hóa để người ngoài khó đọc, kiểm tra tính toàn vẹn để phát hiện sửa đổi và cho phép client xác thực danh tính server qua certificate chain/trust store/hostname. TLS **không** thay thế authentication hoặc authorization ở tầng ứng dụng; endpoint vẫn cần kiểm tra người dùng và quyền truy cập phù hợp.

Cần phân biệt các trường hợp:

| Kết nối | HTTP version | TLS | Kết luận |
| --- | --- | --- | --- |
| http://... với HTTP/1.1 | HTTP/1.1 | Không | Nội dung có thể truyền rõ trên mạng |
| https://... với HTTP/1.1 | HTTP/1.1 | Có | HTTPS bảo vệ HTTP/1.1 bình thường |
| https://... với ALPN chọn h2 | HTTP/2 (h2) | **Có, TLS 1.2+** | Cách sử dụng HTTP/2 phổ biến trên trình duyệt |
| http://... với HTTP/2 prior knowledge | HTTP/2 (h2c) | Không | Chỉ dùng khi cả hai đầu và môi trường tin cậy hỗ trợ |

Theo RFC 9113 đối với **HTTP/2 over TLS**:

1. **Phải dùng TLS 1.2 hoặc cao hơn.** TLS 1.3 là lựa chọn hiện đại; không nên cấu hình các phiên bản TLS cũ. Với TLS 1.2 cần tuân thủ hạn chế đối với tính năng/cipher suite kém an toàn của HTTP/2.
2. **ALPN (Application-Layer Protocol Negotiation) xác định giao thức ứng dụng trong quá trình TLS handshake.** Client có thể quảng bá **h2** và **http/1.1**; server chọn giao thức nó hỗ trợ. Nếu kết nối thương lượng được **http/1.1**, chỉ đặt cấu hình HTTP/2 ở ứng dụng chưa có nghĩa request đang dùng HTTP/2.
3. **SNI (Server Name Indication)** giúp server chọn chứng chỉ/host thích hợp khi phục vụ nhiều hostname. Chứng chỉ phải còn hạn, được client tin cậy và khớp tên host; SNI/ALPN/certificate có vai trò khác nhau.
4. Khi dùng **TLS 1.2 với h2**, đặc tả cấm TLS compression và TLS renegotiation, đồng thời hạn chế các bộ mã cũ. Cấu hình máy chủ và thư viện TLS quyết định việc tuân thủ, không chỉ một cờ bật HTTP/2.
5. **h2c không mã hóa.** RFC 9113 mô tả bắt đầu bằng cơ chế prior knowledge trên kết nối TCP rõ; cơ chế nâng cấp HTTP/1.1 bằng **Upgrade: h2c** được đặc tả hiện hành đánh dấu deprecated. Trình duyệt web thông thường sử dụng h2 trên HTTPS thay vì dựa vào h2c.

Hình dung handshake khi client truy cập https://example.test/hello và server hỗ trợ h2:

~~~text
Client                           Server / TLS termination
  |---- TCP connect ------------------------>|
  |---- TLS ClientHello: SNI, ALPN h2 ------>|
  |<--- TLS chọn h2, gửi chứng chỉ ----------|
  |---- Xác thực chứng chỉ, hoàn tất TLS --->|
  |==== Kênh TLS được mã hóa ================|
  |---- HTTP/2 connection preface/SETTINGS ->|
  |<--- SETTINGS ----------------------------|
  |---- HEADERS stream 1 ------------------->|
  |---- HEADERS stream 3 ------------------->|
  |<--- DATA/HEADERS trên các stream --------|
~~~

Sơ đồ chỉ mô tả luồng khái niệm: thứ tự/chi tiết cụ thể của handshake, SETTINGS và frame có thể khác. Một TLS connection có thể mang nhiều HTTP/2 stream; **không có TLS handshake riêng cho mỗi stream**.

## 6. Áp dụng với Spring Boot (Java 17+, Spring Boot 3.x)

Spring Boot cho phép bật HTTP/2 bằng **server.http2.enabled=true**. Khi có SSL/TLS, đường kết nối được cấu hình theo **h2**; khi không bật SSL, server tương thích có thể phục vụ **h2c**. Ví dụ bên dưới dùng **spring-boot-starter-web** (Spring MVC + embedded Tomcat) và một chương trình tối thiểu. Với Jetty, Reactor Netty hoặc reverse proxy, khả năng và dependency cần kiểm tra theo web server thực tế.

**Tệp src/main/java/com/example/httplab/HttpLabApplication.java:**

~~~java
package com.example.httplab;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpLabApplication.class, args);
    }
}

@RestController
class ProtocolController {
    @GetMapping("/protocol")
    String protocol(HttpServletRequest request) {
        return request.getProtocol();
    }
}
~~~

Điều kiện chạy: project Spring Boot 3.x với dependency **org.springframework.boot:spring-boot-starter-web**, Java 17+, class nằm dưới package được component scan. Endpoint trả về chuỗi giao thức request nhìn thấy ở Servlet container; kết quả hiển thị có thể là **HTTP/1.1** hoặc **HTTP/2.0**, tùy kết nối thực tế.

**Tạo certificate tự ký chỉ cho máy local** (lệnh keytool của JDK, chạy tại thư mục gốc project và bảo đảm thư mục src/main/resources đã có):

~~~bash
keytool -genkeypair -alias localdev -keyalg RSA -keysize 3072 -validity 30 -storetype PKCS12 -keystore src/main/resources/localdev.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

**Tệp src/main/resources/application.properties:**

~~~properties
server.port=8443
server.http2.enabled=true
server.ssl.enabled=true
server.ssl.key-store=classpath:localdev.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
~~~

Trong shell Bash, đặt password tương ứng rồi chạy ứng dụng bằng Gradle wrapper của một project đã cấu hình Spring Boot:

~~~bash
export TLS_KEYSTORE_PASSWORD=changeit
./gradlew bootRun
~~~

Password và chứng chỉ tự ký trên đây **chỉ dùng để học trên local**. Không commit private key/keystore hoặc password thật; môi trường triển khai cần quản lý secret, certificate hợp lệ, chính sách TLS và gia hạn certificate thích hợp. Đặt HTTPS trên port **8443** theo ví dụ; cấu hình này không tự tạo thêm HTTP listener trên port 8080.

**Kiểm chứng phiên bản đã thương lượng** bằng curl có hỗ trợ HTTP/2 (xem **curl -V** để kiểm tra feature HTTP2):

~~~bash
curl -k -sS --http1.1 -o /dev/null -w '%{http_version}' https://localhost:8443/protocol
curl -k -sS --http2 -o /dev/null -w '%{http_version}' https://localhost:8443/protocol
curl -vk --http2 https://localhost:8443/protocol
~~~

- Lệnh thứ nhất dự kiến in **1.1**.
- Lệnh thứ hai dự kiến in **2** **nếu ALPN chọn h2**. Nếu in **1.1**, hãy xem cấu hình server/proxy/TLS và log, vì **--http2 trên HTTPS yêu cầu thương lượng và có thể fallback**.
- Lệnh thứ ba cung cấp dấu vết ALPN và dòng trạng thái HTTP để xác nhận. **-k** bỏ xác minh certificate chỉ vì đây là certificate tự ký tại local; không dùng **-k** như mặc định cho hệ thống thật.

**Thử riêng h2c trong môi trường kiểm soát:** bỏ các thuộc tính server.ssl.*, dùng **server.port=8080** và **server.http2.enabled=true**, khởi động lại, rồi dùng client hỗ trợ prior knowledge:

~~~bash
curl --http2-prior-knowledge -sS -o /dev/null -w '%{http_version}' http://localhost:8080/protocol
~~~

Nếu máy chủ và curl đều hỗ trợ h2c prior knowledge, kết quả kỳ vọng là **2**. Đây là **một cấu hình thay thế** cho demo HTTPS ở trên, không phải mở đồng thời cả hai cổng chỉ nhờ thêm vài dòng properties. Không mở h2c trực tiếp qua mạng không tin cậy.

## 7. TLS termination và reverse proxy trong triển khai thực tế

Nhiều hệ thống không để Spring Boot trực tiếp bắt tay TLS với browser:

~~~text
Browser ---- HTTPS + h2 ----> Reverse proxy / Load balancer
                                      |
                                      +---- HTTP/1.1 hoặc h2c/h2 ----> Spring Boot
~~~

Tại đây, **HTTP version có thể khác nhau ở hai chặng**. Trình duyệt có thể dùng h2 tới Nginx/Ingress/Load Balancer trong khi proxy nói HTTP/1.1 tới Tomcat. Điều này vẫn đem lại lợi ích h2 trên đường browser–proxy; cờ **server.http2.enabled** của backend không tự đổi giao thức ở chặng public. Ngược lại, khi proxy cần HTTP/2 ở chặng upstream, nó cũng phải được cấu hình hỗ trợ giao thức đó.

Trong vận hành, xác định rõ nơi **TLS termination**, kiểm tra ALPN và certificate ở nơi đó, kiểm tra giao thức upstream riêng, và chỉ tin các header chuyển tiếp như Forwarded/X-Forwarded-* từ proxy đáng tin cậy. HTTPS ở ngoài không bảo đảm chặng proxy–backend cũng được mã hóa; cân nhắc TLS/mTLS nội bộ tùy mô hình tin cậy.

## 8. Khi nào HTTP/2 có lợi và cần đo gì?

HTTP/2 thường hữu ích khi một client tải **nhiều tài nguyên nhỏ/độc lập** và có nhiều request đồng thời, vì giảm số connection và chi phí header. Với API chỉ có một request lớn hoặc mạng có mất gói, tốc độ có thể không cải thiện rõ; HTTP/2 cũng cần giới hạn stream, flow control và xử lý frame phù hợp.

Khi so sánh, giữ nguyên payload/điều kiện client và đo **latency p50/p95/p99**, throughput, số connection, CPU, mức tải proxy, tình trạng mất gói, thời gian TLS handshake và HTTP version đã thương lượng. Đừng chỉ bật cờ rồi kết luận là đã tối ưu. **HTTP/3** dùng QUIC và có đặc tính khác về mất gói; đây là phiên bản riêng, không phải tên gọi khác của HTTP/2.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng hoặc nhận định | Nguyên nhân cần kiểm tra / cách hiểu đúng |
| --- | --- |
| Bật server.http2.enabled=true nhưng curl vẫn hiện 1.1 | Kiểm tra endpoint thực sự được gọi, proxy ở trước, SSL đã bật hay chưa, ALPN có chọn h2 không, server có hỗ trợ h2 không. |
| Trình duyệt không dùng h2 với http://localhost | h2c không phải đường giao tiếp HTTP/2 thông dụng của trình duyệt; dùng HTTPS/h2 hoặc client h2c phù hợp để thử. |
| curl báo không hỗ trợ --http2 | Bản libcurl hiện tại không có feature HTTP2; xem curl -V và dùng bản build hỗ trợ. |
| SSL handshake hoặc certificate verification thất bại | Kiểm tra đúng port HTTPS, đường dẫn/password keystore, hostname/SAN, hiệu lực và chuỗi tin cậy của certificate, cấu hình TLS/cipher. |
| Mọi stream cùng chậm khi mạng mất gói | HTTP/2 multiplex ở tầng ứng dụng nhưng vẫn cùng TCP connection; kiểm tra packet loss, flow control và hiệu năng mạng. |
| Dùng HTTPS nên chắc chắn là HTTP/2 | HTTPS có thể chở HTTP/1.1; cần xem kết quả ALPN hoặc protocol ở client. |
| HTTP/2 tự bảo đảm endpoint an toàn | TLS không thay thế phân quyền, xác thực người dùng, kiểm tra đầu vào và chính sách ứng dụng. |
| Backend nhận HTTP/1.1 dù browser dùng h2 | Proxy có thể chủ động chuyển đổi phiên bản giao thức giữa hai chặng; kiểm tra hai chặng độc lập. |

## 10. Câu hỏi tự kiểm tra

1. **HTTP/2 khác HTTP/1.1 về GET/POST, status code không?** Không; khác chủ yếu về biểu diễn/truyền tải, multiplex, nén header và điều khiển luồng.
2. **HTTP/2 bắt buộc TLS trong mọi trường hợp?** Không: h2 cần TLS 1.2+; h2c là cleartext TCP khi được hỗ trợ. Trong trình duyệt, h2 qua HTTPS là đường phổ biến.
3. **Một request chậm ở HTTP/2 có chặn mọi request khác?** Thông thường không ở tầng frame/stream HTTP, nhưng mất gói TCP hoặc giới hạn tài nguyên/flow control vẫn ảnh hưởng chung.
4. **Bật HTTP/2 trong Spring Boot có tự phát hành certificate?** Không. Cần cấu hình TLS/certificate hoặc cấu hình TLS termination ở proxy.
5. **Muốn biết người dùng thật đang dùng HTTP/2 phải kiểm tra ở đâu?** Kiểm tra client–proxy/edge thông qua ALPN, DevTools hoặc curl; kết quả ở backend có thể khác vì proxy chuyển giao thức.

## 11. Tài liệu tham khảo

- **IETF RFC 9113 – HTTP/2:** https://www.rfc-editor.org/rfc/rfc9113 (đặc tả framing, multiplexing, h2/h2c, ALPN, TLS 1.2+).
- **Spring Boot 3.3 – Embedded Web Servers:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html (server.http2.enabled, SSL và hỗ trợ theo embedded server).
- **curl manual:** https://curl.se/docs/manpage.html (tùy chọn --http1.1, --http2, --http2-prior-knowledge, kiểm tra giao thức thương lượng).
