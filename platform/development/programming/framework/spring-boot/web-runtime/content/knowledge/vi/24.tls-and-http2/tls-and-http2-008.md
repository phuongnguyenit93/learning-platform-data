# Phân biệt h2, h2c và cơ chế thương lượng giao thức

**Module:** Spring Boot - web-runtime  
**Chủ đề cha:** TLS và HTTP/2

## 1. Vấn đề thực tế: bật HTTP/2 chưa đủ để biết request chạy giao thức nào

Bạn cấu hình **server.http2.enabled=true** trong một ứng dụng Spring Boot. Khi gọi **https://api.example.com** trên trình duyệt, DevTools hiện **h2**. Nhưng khi gọi **http://localhost:8080** qua curl, bạn có thể thấy **HTTP/1.1**, **h2c** hoặc request bị lỗi tùy cách client khởi tạo kết nối. Đặt cùng một server sau reverse proxy lại cho kết quả khác: browser dùng **h2** với proxy trong khi proxy dùng **HTTP/1.1** hoặc **h2c** với Spring Boot.

Sự khác biệt nằm ở **transport bảo mật** và **cơ chế hai bên xác định cùng dùng HTTP/2**, không chỉ trong cấu hình endpoint Java.

Bài này cần làm rõ:

1. **h2** và **h2c** đều thực hiện HTTP/2 framing, streams, flow control và semantics, nhưng khác nhau về **TLS**.
2. Với **HTTPS**, HTTP/2 phải được nhận diện bằng **ALPN trong TLS handshake**, sử dụng protocol identifier **h2**; **h2c không phải giá trị ALPN hợp lệ cho kết nối TLS**.
3. Với **HTTP cleartext**, HTTP/2 hiện được RFC 9113 mô tả theo cơ chế **prior knowledge**, bắt đầu gửi HTTP/2 connection preface trực tiếp. Cơ chế **HTTP/1.1 Upgrade: h2c** là dạng lịch sử của RFC 7540, đã được RFC 9113 đánh dấu deprecated/obsolete dù một số server/client vẫn hỗ trợ.
4. Chỉ thị **server.http2.enabled=true** trong Spring Boot 3.3 có thể bật **h2 nếu SSL được cấu hình**, hoặc **h2c nếu chưa bật SSL**, với điều kiện embedded server hỗ trợ; nhưng **client và từng hop proxy** vẫn phải dùng giao thức tương thích.
5. Cần kiểm tra bằng **curl, openssl, HTTP response metadata** và log thực tế; không suy từ URL, port hoặc tên property.

## 2. h2 và h2c giống và khác ở đâu?

| Thuộc tính | **h2** | **h2c** |
| --- | --- | --- |
| HTTP semantic và wire framing | HTTP/2 binary frames, streams, HPACK headers, multiplexing | Cũng chính cơ chế HTTP/2 đó |
| Kênh vận chuyển | **HTTP/2 chạy trên TLS qua TCP** | **HTTP/2 chạy trực tiếp trên cleartext TCP**, không có TLS trong hop ấy |
| URI thường gặp | **https://** | **http://** ở một hop không TLS |
| Nhận diện ban đầu | **TLS ALPN** chọn protocol ID **h2** | **Prior knowledge**: client biết trước server hỗ trợ, gửi HTTP/2 preface trực tiếp |
| HTTP/1.1 Upgrade | Không dùng **Upgrade: h2** để vào TLS HTTP/2 | **Upgrade: h2c** từng được định nghĩa trong RFC 7540, đã lỗi thời theo RFC 9113 |
| Mã hóa dữ liệu trên hop | Có bảo mật TLS nếu cấu hình/kiểm certificate đúng | **Không**; dữ liệu có thể quan sát/sửa đổi trên đường truyền không tin cậy |
| Khả năng dùng trên web public | Thông dụng ở browser/CDN HTTPS | Thường dành cho nội bộ tin cậy, backend hop hoặc client chuyên dụng; browser nói chung không dựa vào h2c |
| HTTP/2 frame sau khi thiết lập | Có **SETTINGS**, **HEADERS**, **DATA**, **WINDOW_UPDATE**, v.v. | Cùng cấu trúc frame đó |

**Không nên nói “h2 là HTTP/2, h2c là giao thức khác HTTP/2”.** Chúng cùng thuộc HTTP/2; chữ **c** trong h2c nhấn mạnh cleartext, còn **h2** là tên được dùng khi HTTP/2 chạy trên TLS.

**Không nên nói “HTTP/2 luôn bắt buộc TLS”.** Chuẩn có mô hình HTTP/2 trên cleartext TCP với prior knowledge. Tuy nhiên, **HTTP/2 trên HTTPS bắt buộc tuân thủ TLS và ALPN**, còn HTTP/2 cleartext không có tính bảo mật của TLS. Vì thế giao diện browser truy cập HTTPS trong thực tế thường dùng h2, trong khi backend sau TLS termination có thể dùng h2c.

### Bảng so sánh thêm với HTTP/1.1 và HTTP/3

| Cách kết nối | Transport | Cách chọn giao thức | Ghi nhớ |
| --- | --- | --- | --- |
| HTTP/1.1 + HTTPS | TCP + TLS | Có thể chọn **http/1.1** bằng ALPN hoặc fallback tương thích | HTTPS **không đồng nghĩa** h2. |
| HTTP/2 h2 | TCP + TLS | **ALPN h2** | HTTP/2 trên kết nối TLS. |
| HTTP/2 h2c | TCP cleartext | **Prior knowledge**, hoặc Upgrade cũ ở hệ thống còn hỗ trợ | Không có TLS trên hop. |
| HTTP/3 h3 | QUIC (UDP + TLS 1.3 tích hợp) | Cơ chế HTTP/3 và ALPN **h3** | Không phải tên mới của h2 hoặc h2c. |

HTTP/2 sử dụng multiplexing để nhiều stream cùng đi trên một TCP connection; có **flow control ở cấp stream và connection**. HPACK nén **header fields** của HTTP/2; đây là cơ chế riêng so với **gzip/br cho response body** qua Content-Encoding.

## 3. ALPN: thương lượng HTTP/2 trong TLS handshake

**ALPN** (*Application-Layer Protocol Negotiation*, RFC 7301) là phần mở rộng TLS để client và server chọn giao thức ứng dụng trên **cùng một TLS connection**. Với h2, client gửi danh sách protocol IDs có thể dùng, ví dụ **h2** và **http/1.1**. Server chọn một giá trị được cả hai hỗ trợ.

Dòng thời gian rút gọn:

~~~text
Client                                      TLS server / Spring Boot / Edge
   |                                                    |
   | TCP connect                                        |
   |--------------------------------------------------->|
   | TLS ClientHello: ALPN = ["h2", "http/1.1"]         |
   | TLS ClientHello: SNI = "api.example.com"           |
   |--------------------------------------------------->|
   |       TLS handshake, certificate, key exchange     |
   |<-------------------------------------------------->|
   | TLS ALPN result: "h2"                               |
   |<---------------------------------------------------|
   |                                                    |
   | HTTP/2 connection preface + SETTINGS              |
   |--------------------------------------------------->|
   |<------------------------------- SETTINGS ----------|
   | HEADERS (request stream)                           |
   |--------------------------------------------------->|
   |<--------------------------- HEADERS + DATA --------|
~~~

Sơ đồ mang tính logic; trong TLS 1.3, chi tiết handshake và thời điểm trường ALPN được truyền/bảo vệ khác TLS 1.2. Ý chính là **phải hoàn tất thương lượng TLS và chọn h2 trước khi trao đổi HTTP/2 frames**.

**SNI và ALPN khác nhau:**

- **SNI (Server Name Indication)** nói client muốn tới hostname nào; server có thể dựa vào đó chọn certificate và virtual host.
- **ALPN** cho biết client/server dùng protocol ứng dụng nào trên TLS connection.
- Có **certificate hợp lệ** không tự chứng minh server đã chọn h2. Ngược lại **ALPN h2** không thay thế kiểm tra certificate, hostname và chuỗi tin cậy.
- HTTP/2 trên TLS yêu cầu **TLS 1.2 trở lên** theo RFC 9113; triển khai TLS 1.2 còn phải đáp ứng các hạn chế về cipher suite, renegotiation và các đặc điểm bảo mật. TLS 1.3 có quy tắc riêng. Không chỉ dựa vào việc handshake TLS thành công mà kết luận h2 chắc chắn khả dụng.

### Kết quả ALPN thường gặp

| Client gửi | Server hỗ trợ/chọn | Kết quả có thể thấy |
| --- | --- | --- |
| **h2, http/1.1** | Chọn **h2** | Client dùng HTTP/2 trên TLS. |
| **h2, http/1.1** | Chọn **http/1.1** | Client dùng HTTP/1.1 dù đang HTTPS. |
| Chỉ **http/1.1** | Chọn **http/1.1** | Không có h2 trong hop này. |
| Chỉ **h2** | Server không hỗ trợ h2 | Không có giao thức ứng dụng được thống nhất; handshake/giao tiếp có thể thất bại, không tự cam kết fallback. |
| **h2, http/1.1** | Server không hỗ trợ ALPN/không chọn h2 | Phụ thuộc client/server: có thể dùng HTTP/1.1 theo tương thích hoặc lỗi. |

**Fallback không phải phép đổi HTTP/2 thành HTTP/1.1 ở giữa một stream h2 đang hoạt động.** Nó là kết quả của quá trình chọn giao thức ban đầu hoặc kết nối mới theo chính sách client. Một khi h2 đã được chọn, bytes HTTP trên connection phải tuân thủ HTTP/2 framing, không trộn request line HTTP/1.1.

## 4. h2c với prior knowledge: không có TLS, cũng không có ALPN

**Prior knowledge** nghĩa là client **đã được cấu hình hoặc biết từ một cơ chế bên ngoài** rằng peer trên cổng đó chấp nhận HTTP/2 cleartext. Client mở TCP socket và gửi HTTP/2 connection preface ngay; không gửi request HTTP/1.1 để xin nâng cấp.

~~~text
Client h2c                              Server h2c
    |                                         |
    | TCP connect                            |
    |---------------------------------------->|
    | HTTP/2 client connection preface        |
    | PRI * HTTP/2.0 + magic sequence         |
    | SETTINGS frame                          |
    |---------------------------------------->|
    |<------------------------- SETTINGS -----|
    | HEADERS (GET /api/protocol)             |
    |---------------------------------------->|
    |<---------------- HEADERS + DATA --------|
~~~

Client connection preface bắt đầu bằng chuỗi 24 octet đặc biệt:

~~~text
PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n
~~~

Trong văn bản trên, **\r\n** thể hiện byte CRLF, không phải hai ký tự backslash-r và backslash-n trong wire. Sau chuỗi magic, client gửi **SETTINGS frame**. Server cũng gửi **SETTINGS frame** của mình. Preface giúp nhận biết định dạng kết nối; nó **không cung cấp xác thực hoặc mã hóa** cho traffic cleartext.

Theo **RFC 9113 §3.3**, cleartext HTTP/2 dùng cơ chế prior knowledge. Điều này tạo ra một yêu cầu triển khai: **không thể trông chờ ALPN trên một HTTP không TLS để khám phá h2c**. Client phải biết cấu hình backend hoặc có thông tin từ bên ngoài (ví dụ proxy/backend route được cấu hình rõ).

Đối với trình duyệt phổ biến, **http://** công khai thường dùng HTTP/1.1 hoặc các hành vi riêng của client; không nên giả định browser sẽ thử h2c tự động. Trong ứng dụng web public, chọn **HTTPS/h2** để vừa được HTTP/2 vừa được TLS; h2c phù hợp nhất với hop backend có kiểm soát nếu thực sự cần.

## 5. HTTP/1.1 Upgrade: h2c — cơ chế lịch sử, không phải lựa chọn chuẩn mới

Cần hiểu **hai thế hệ đặc tả** để đọc tài liệu và log không nhầm.

### Theo RFC 7540 trước đây

Client chưa có prior knowledge có thể bắt đầu với HTTP/1.1 và thử nâng cấp bằng các header:

~~~http
GET /api/protocol HTTP/1.1
Host: localhost:8080
Connection: Upgrade, HTTP2-Settings
Upgrade: h2c
HTTP2-Settings: <base64url-encoded-settings>
~~~

Nếu server chấp nhận, nó có thể trả:

~~~http
HTTP/1.1 101 Switching Protocols
Connection: Upgrade
Upgrade: h2c
~~~

Sau response 101, hai bên trao đổi HTTP/2 frames và thực hiện các yêu cầu tiếp theo bằng HTTP/2. Đây là mô hình từng được mô tả trong **RFC 7540**; dấu **<base64url-encoded-settings>** là placeholder minh họa, không phải một giá trị header để sao chép vào request thật.

### Theo RFC 9113 hiện hành

**RFC 9113 (2022, thay thế RFC 7540)** xác định rằng cơ chế **HTTP/1.1 Upgrade: h2c** không được triển khai rộng và đã **deprecated**. Header **HTTP2-Settings** và upgrade token **h2c** cho cách nâng cấp này được đánh dấu **obsolete**. Chuẩn hiện hành mô tả khởi tạo HTTP/2 cleartext bằng **prior knowledge**.

**Hệ quả khi thực hành:**

- Lệnh **curl --http2 http://host** có thể thử **HTTP/1.1 Upgrade** vì curl vẫn hỗ trợ cơ chế đó, mặc dù RFC 9113 coi nó là lỗi thời. Không lấy việc một server trả 101 làm bằng chứng đây là khuyến nghị cho hệ thống mới.
- Lệnh **curl --http2-prior-knowledge http://host** gửi HTTP/2 cleartext **ngay từ đầu**, đúng với mô hình prior knowledge hiện hành.
- Một số server thực tế (ví dụ Tomcat 10.1) vẫn có khả năng phục vụ h2c bằng cả **Upgrade** lẫn **direct/prior-knowledge** để tương thích; tính năng thực tế không có nghĩa RFC 9113 đã khôi phục Upgrade thành khuyến nghị.
- Nếu môi trường h2c chỉ hỗ trợ một trong hai kiểu, client dùng kiểu còn lại có thể lỗi; cần xác định **connection preface** hoặc **101 Switching Protocols** thực tế từ trace.

**Không dùng Upgrade: h2 để bật HTTP/2 trên HTTPS.** H2 over TLS phải dùng **ALPN h2**. **Không gửi h2c trong ALPN**: đó là cleartext identifier, không phải lựa chọn protocol TLS.

## 6. Vì sao cần thương lượng trước khi gửi HTTP/2 frames?

HTTP/1.1 dùng start line và header bằng text:

~~~http
GET /hello HTTP/1.1
Host: example.test
Accept: application/json
~~~

HTTP/2 lại dùng các **binary frames**; request method/path/authority/scheme được biểu diễn bằng **pseudo-header fields** như **:method**, **:path**, **:scheme**, **:authority**. Các frame thuộc những **stream** có ID riêng và được multiplex qua một connection.

Nếu client gửi **HTTP/2 connection preface** đến server chỉ hiểu HTTP/1.1, server không thể hiểu đây là một HTTP/2 request bình thường. Nếu client gửi request line HTTP/1.1 đến một endpoint chỉ chấp nhận HTTP/2 prior knowledge, server cũng không có nghĩa vụ hiểu request ấy như stream HTTP/2.

**ALPN h2** giải quyết bài toán nhận diện định dạng HTTP/2 trên TLS một cách rõ ràng. **Prior knowledge** giải quyết cleartext bằng cam kết cấu hình từ trước. HTTP/1.1 Upgrade từng là cách chuyển giao định dạng giữa chừng, nhưng đã lỗi thời trong RFC 9113.

HTTP/2 vẫn giữ semantics HTTP quen thuộc: method, status code, headers, URI, cache và cookie. Đổi framing không có nghĩa bạn phải sửa mọi **@GetMapping** hoặc **@RestController**. Tuy nhiên những header dành cho **connection HTTP/1.1** không có ý nghĩa hoặc bị cấm trong HTTP/2 (ví dụ **Connection**, **Keep-Alive**, **Upgrade**, **Transfer-Encoding: chunked**). Ứng dụng và proxy phải chuyển đổi đúng representation giữa các phiên bản.

### Trình tự SETTINGS và flow control

Sau khi khởi tạo HTTP/2, mỗi peer gửi **SETTINGS**, còn các luồng **HEADERS/DATA** mang request/response. Có thể thấy **WINDOW_UPDATE** khi bên nhận báo còn khả năng nhận DATA bytes; **RST_STREAM** huỷ stream, **GOAWAY** báo kế hoạch dừng dùng connection. Dù dùng h2 hay h2c, các cơ chế này cùng là HTTP/2.

**Ưu điểm HTTP/2** gồm multiplex streams và HPACK header compression, nhưng không xoá **TCP head-of-line blocking** khi mất packet. HTTP/2 cũng không tự biến code Spring MVC blocking thành non-blocking hoặc bảo đảm tốc độ ứng dụng cao hơn trong mọi trường hợp. Vấn đề này thuộc performance runtime, không phải lựa chọn h2/h2c.

## 7. Spring Boot 3.3: server.http2.enabled hỗ trợ h2 và h2c

Tài liệu **Spring Boot 3.3 – Embedded Web Servers** ghi:

- **server.http2.enabled=true** bật hỗ trợ HTTP/2 ở embedded server phù hợp.
- Nếu cấu hình **SSL/TLS** cho server, đường **h2** được sử dụng qua TLS khi client thương lượng thành công bằng ALPN.
- Nếu **không bật SSL** trên listener, Spring Boot 3.3 hỗ trợ **h2c** trên TCP cleartext.
- **Tomcat 10.1.x**, **Undertow** và **Reactor Netty** hỗ trợ h2/h2c theo khả năng server; **Jetty** cần các dependency HTTP/2 bổ sung theo tài liệu của phiên bản.
- Những hướng dẫn Spring Boot **cũ** nói "Boot không hỗ trợ h2c" áp dụng cho phiên bản cũ, **không được dùng để kết luận về Spring Boot 3.3**.

Với dự án dùng **spring-boot-starter-web**, embedded Tomcat là lựa chọn mặc định. Với **spring-boot-starter-webflux**, mặc định là Reactor Netty; vẫn cần xác nhận dependency và server chạy thực tế. Nếu cả hai starter có mặt, Spring Boot thông thường chọn Servlet/MVC theo auto-configuration; đừng giả định framework là reactive chỉ vì có WebFlux trên classpath.

**Tổng hợp:**

~~~properties
# Bat HTTP/2 tren embedded web server
server.http2.enabled=true
~~~

Thuộc tính trên **không** có nghĩa:

- Mọi request đều được ép chạy HTTP/2.
- Một endpoint HTTPS tự hoạt động nếu bạn chưa cấu hình TLS certificate/key.
- Browser tự dùng h2c cho mọi URL http.
- Reverse proxy/CDN cũng dùng h2/h2c về phía upstream.
- ALPN được thực hiện trên kết nối không TLS.
- HTTP/3 được bật.

Các điều kiện còn lại phải được kiểm chứng trên **mỗi hop của topology**.

## 8. Ví dụ hoàn chỉnh: Java 17 + Spring Boot 3.3, kiểm h2 và h2c

Để nhìn thấy protocol phía Servlet container, tạo project nhỏ dùng **Spring MVC + embedded Tomcat**. Dùng **hai profile** chạy **lần lượt**, không phải hai server cùng chạy một cổng: **h2c** ở HTTP 8080 và **h2** ở HTTPS 8443.

### 8.1. Cấu trúc project

~~~text
http2-negotiation-demo/
  pom.xml
  src/main/
    java/com/example/h2demo/
      Http2NegotiationDemoApplication.java
    resources/
      application.properties
      application-h2c.properties
      application-h2.properties
      localdev.p12    (tao o buoc TLS)
~~~

**Điều kiện:** Java 17+, Maven và keytool (thuộc JDK) được cài đặt. Ví dụ sử dụng **Spring Boot 3.3.13**, một bản thuộc nhánh 3.3; khi làm dự án mới nên chọn bản Spring Boot còn được hỗ trợ và tương thích với môi trường. Cơ chế h2/h2c/ALPN vẫn cần xác minh theo tài liệu và server cụ thể.

### 8.2. pom.xml hoàn chỉnh

Tạo **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http2-negotiation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. Java application

Tạo **src/main/java/com/example/h2demo/Http2NegotiationDemoApplication.java**:

~~~java
package com.example.h2demo;

import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class Http2NegotiationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(Http2NegotiationDemoApplication.class, args);
    }
}

@RestController
class ProtocolController {

    @GetMapping(value = "/api/protocol",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> inspect(HttpServletRequest request) {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("servletProtocol", request.getProtocol());
        result.put("scheme", request.getScheme());
        result.put("method", request.getMethod());
        result.put("path", request.getRequestURI());
        return result;
    }
}
~~~

Đây là ứng dụng Java 17 hợp lệ:

- Chỉ có **một public class** khớp tên file **Http2NegotiationDemoApplication.java**.
- Class **ProtocolController** package-private được component scan vì cùng package root.
- **HttpServletRequest.getProtocol()** cho biết protocol của **request đi tới Servlet container**, ví dụ HTTP/1.1 hoặc HTTP/2.0, **không nhất thiết protocol browser đã dùng với CDN/proxy**.
- **request.getScheme()** cho biết scheme nhìn từ app trong cấu hình hiện tại; ở production với proxy termination, forwarded headers có thể ảnh hưởng scheme được app thấy. Giá trị JSON giúp quan sát, không phải chứng cứ độc lập về TLS hoặc ALPN.

### 8.4. Properties chung

Tạo **src/main/resources/application.properties**:

~~~properties
server.http2.enabled=true
spring.application.name=http2-negotiation-demo
~~~

### 8.5. Profile h2c cleartext

Tạo **src/main/resources/application-h2c.properties**:

~~~properties
server.port=8080
server.ssl.enabled=false
~~~

Ở profile này, listener Spring Boot/Tomcat không có TLS. Khi HTTP/2 được bật, server có thể chấp nhận **h2c** (bao gồm direct/prior-knowledge theo khả năng Tomcat).

### 8.6. Profile h2 với certificate tự ký local

Trước tiên tạo thư mục **src/main/resources** nếu chưa có. Trong terminal có JDK, chạy lệnh từ thư mục project:

~~~bash
keytool -genkeypair \
  -alias localdev \
  -keyalg RSA \
  -keysize 2048 \
  -storetype PKCS12 \
  -keystore src/main/resources/localdev.p12 \
  -storepass changeit \
  -keypass changeit \
  -validity 365 \
  -dname "CN=localhost, OU=Learning, O=Demo, L=Local, ST=Local, C=VN" \
  -ext "SAN=DNS:localhost,IP:127.0.0.1"
~~~

**Lệnh tạo self-signed certificate dùng cho máy thử**, không dùng cho public production. **changeit** chỉ là mật khẩu ví dụ, **không** đưa cùng keystore và password mẫu vào source control thật. Trong production dùng TLS certificate hợp lệ, secret store/SSL bundle phù hợp, lịch rotate và cấu hình HTTPS chính xác.

Tạo **src/main/resources/application-h2.properties**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:localdev.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=changeit
server.ssl.key-password=changeit
server.ssl.key-alias=localdev
~~~

**server.http2.enabled=true** đã ở application.properties chung. Với TLS trên cổng 8443, server có khả năng dùng **ALPN** chọn **h2** hoặc **http/1.1** theo client/server.

### 8.7. Build và chạy profile h2c

~~~bash
mvn -q -DskipTests package

java -jar target/http2-negotiation-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=h2c
~~~

Mở terminal thứ hai. Kiểm xem curl có hỗ trợ HTTP/2:

~~~bash
curl -V
~~~

Output của **curl -V** cần có tính năng **HTTP2** trong Features hoặc thông tin build tương ứng. Nếu curl không được biên dịch với HTTP/2, các tùy chọn **--http2**/ **--http2-prior-knowledge** sẽ không hoạt động dù server hoàn toàn hợp lệ.

**Thử direct h2c:**

~~~bash
curl -v --http2-prior-knowledge \
  http://localhost:8080/api/protocol
~~~

Khi Tomcat và curl đều hỗ trợ h2c direct, body JSON có thể tương tự:

~~~json
{"servletProtocol":"HTTP/2.0","scheme":"http","method":"GET","path":"/api/protocol"}
~~~

Giá trị protocol/scheme là đầu ra điển hình khi trực tiếp gọi Tomcat; kiểm log/trace thực tế nếu container khác hoặc có proxy. **--http2-prior-knowledge** không yêu cầu HTTPS, không thực hiện ALPN trên TCP cleartext.

**Thử HTTP/1.1 trên cùng listener:**

~~~bash
curl -v --http1.1 http://localhost:8080/api/protocol
~~~

Body JSON điển hình:

~~~json
{"servletProtocol":"HTTP/1.1","scheme":"http","method":"GET","path":"/api/protocol"}
~~~

Điều này chứng minh **server hỗ trợ h2c không nhất thiết loại bỏ HTTP/1.1**. Protocol phụ thuộc cách client mở request và khả năng server/connector.

**Thử HTTP/1.1 Upgrade lịch sử (không khuyến nghị cho thiết kế mới):**

~~~bash
curl -v --http2 http://localhost:8080/api/protocol
~~~

Theo hướng dẫn curl, với **http://**, --http2 **thử Upgrade**. Nếu Tomcat chấp nhận, trace có thể chứa **Upgrade: h2c**, **101 Switching Protocols**, rồi frames h2c. Nếu không chấp nhận, hành vi thực tế có thể là HTTP/1.1 fallback hoặc lỗi tùy client/server. **RFC 9113 coi Upgrade: h2c là cơ chế obsolete**; dùng phép thử này để hiểu interoperability, không dùng làm yêu cầu cho browser public.

### 8.8. Chạy profile h2 trên TLS

Dừng server h2c, sau đó chạy:

~~~bash
java -jar target/http2-negotiation-demo-0.0.1-SNAPSHOT.jar \
  --spring.profiles.active=h2
~~~

Thử ALPN với curl:

~~~bash
curl -vk --http2 \
  https://localhost:8443/api/protocol
~~~

- **-v** hiển thị trace TLS/ALPN và request.
- **-k** bỏ qua xác minh certificate chỉ vì demo dùng certificate tự ký. **Không dùng -k làm cấu hình production**.
- **--http2** với HTTPS yêu cầu curl đàm phán HTTP/2 qua ALPN; bản curl có hỗ trợ HTTP/2 cần được dùng.
- Khi server chọn h2, trace thường có dòng tương đương **ALPN: server accepted h2** và phần HTTP hiển thị **HTTP/2**.
- Body JSON điển hình: **servletProtocol=HTTP/2.0**, **scheme=https**. Không khẳng định output trace có cùng chính tả ở mọi phiên bản curl.

So sánh khi ép HTTP/1.1 trên HTTPS:

~~~bash
curl -vk --http1.1 \
  https://localhost:8443/api/protocol
~~~

Có thể nhận **HTTP/1.1** trên cùng cổng TLS vì server cũng hỗ trợ giao thức đó. Điều này là minh họa trực tiếp rằng **TLS và HTTP/2 không đồng nghĩa**.

**Không** gọi **http://localhost:8443** khi cổng đang yêu cầu TLS; cũng không gọi **https://localhost:8080** vào một port đang chạy h2c cleartext. Cặp scheme và listener không khớp có thể khiến handshake/protocol error.

### 8.9. Quan sát ALPN bằng openssl

Nếu có OpenSSL, chạy:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2,http/1.1 \
  </dev/null
~~~

Kết quả mong đợi khi server và OpenSSL hỗ trợ ALPN là dòng **ALPN protocol: h2** hoặc tương đương. Vì certificate tự ký, OpenSSL có thể cảnh báo lỗi xác thực trust chain; điều đó khác vấn đề lựa chọn ALPN.

Thử client chỉ đề xuất HTTP/1.1:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn http/1.1 \
  </dev/null
~~~

Khi server hỗ trợ, output có thể cho thấy **ALPN protocol: http/1.1**. Công cụ **openssl s_client** chỉ xác nhận handshake/ALPN, **không tự gửi một HTTP/2 request hợp lệ**; dùng curl để kiểm luồng HTTP đầy đủ.

## 9. Phân biệt lời chứng từ client, server và proxy

Trong thực tế, bạn có thể có nhiều giao thức trên một đường request:

~~~text
Browser --HTTPS/h2--> CDN / Reverse proxy
          |
          |  TLS termination at edge
          |
          +---- HTTP/1.1 ----> Spring Boot Tomcat
          OR
          +---- HTTP/h2c -----> Spring Boot Tomcat
          OR
          +---- HTTPS/h2 -----> Spring Boot Tomcat
~~~

Đó là **ba đường backend khả dĩ**, không phải ba kết nối đồng thời bắt buộc. Ví dụ browser DevTools hiển thị **h2** vì kết nối **browser↔CDN** là HTTP/2 over TLS, còn **HttpServletRequest.getProtocol()** trong backend có thể trả **HTTP/1.1** do CDN dùng HTTP/1.1 về origin.

**Do đó, mọi câu “API này đang chạy HTTP/2” phải kèm theo câu hỏi: trên hop nào?**

- **Client↔CDN:** DevTools network Protocol, curl -v trực tiếp domain public, TLS/ALPN trace.
- **CDN↔ingress:** dashboard/log của CDN hoặc network trace ở ingress, cùng cấu hình origin protocol.
- **Ingress↔Spring Boot:** log/access trace của ingress và **request.getProtocol()** trên app; profile h2c/h2 của origin.
- **Spring Boot↔service khác:** cấu hình HTTP client thực tế (WebClient, Java HttpClient, OkHttp, Apache HttpClient) và protocol được chọn trong connection đến service đó.

Không dùng header tùy ý **X-Forwarded-Proto: https** làm bằng chứng client chạy HTTP/2. Nó thường mô tả **scheme được proxy báo lại**, không phải token ALPN. Header **Forwarded**/**X-Forwarded-*** phải được xử lý chỉ từ proxy đáng tin cậy để tránh spoofing về scheme/host.

### h2c sau TLS termination có bảo mật không?

Một kiến trúc **browser↔proxy bằng h2/TLS** và **proxy↔Spring Boot bằng h2c/cleartext** bảo vệ đường đầu tiên bằng TLS, **không mã hóa hop proxy↔backend**. Trong cụm nội bộ có network isolation và trust boundary rõ, điều đó có thể được chấp nhận theo threat model. Nếu đường backend đi qua mạng không tin cậy, nhiều tenant hoặc boundary nhạy cảm, cần cân nhắc **TLS/mTLS tới origin** thay vì h2c.

**h2c không đồng nghĩa toàn bộ website là insecure** nếu nó chỉ tồn tại trên hop được bảo vệ riêng, nhưng cũng **không được gọi là mã hóa end-to-end**.

## 10. Chọn chiến lược thương lượng theo bối cảnh triển khai

| Bối cảnh | Cách chọn thường hợp lý | Rủi ro/điểm kiểm tra |
| --- | --- | --- |
| Website/API public từ browser | **HTTPS + h2 qua ALPN**, cho phép HTTP/1.1 nếu cần tương thích | Certificate, TLS 1.2+, cipher, ALPN và fallback phù hợp. |
| Internal service sau TLS termination, network có kiểm soát | **h2c prior knowledge** nếu client và server đều hỗ trợ | Cleartext hop, sidecar/mesh route, policy bảo mật mạng. |
| Internal service cần mTLS | **h2 over TLS** với certificate/client certificate phù hợp | CA trust, SNI, ALPN và chính sách mTLS tại hop thực. |
| Hệ thống legacy client chỉ hỗ trợ HTTP/1.1 | Giữ HTTP/1.1 ở hop client hoặc proxy chuyển đổi | Không ép h2c prior knowledge lên client không hỗ trợ. |
| Lộ trình nâng cấp ứng dụng sau reverse proxy | Bật h2 ở edge trước, đo hop backend độc lập | Tránh báo cáo nhầm “end-to-end h2” khi backend vẫn HTTP/1.1. |
| Client đặc thù dùng h2c Upgrade cũ | Kiểm interoperability và lộ trình migration sang prior knowledge hoặc TLS ALPN | RFC 9113 đánh dấu Upgrade h2c obsolete. |

**Không có một property Spring Boot khiến mọi peer trên internet tự chuyển sang h2.** Chọn giao thức phụ thuộc khả năng của cả client, TLS stack, connector, proxy và policy của mỗi hop.

## 11. Các điều kiện TLS cần kiểm tra khi h2 không được chọn

Theo **RFC 9113 §9.2**, HTTP/2 trên TLS yêu cầu **TLS 1.2 hoặc mới hơn**. Với TLS 1.2, có giới hạn về cipher suites, key exchange, compression và renegotiation; với TLS 1.3 là bộ quy tắc riêng.

Nếu client hiển thị HTTPS nhưng ALPN chọn **http/1.1** hoặc không chọn được h2, cân nhắc:

1. **Server.http2.enabled** chưa bật, hoặc server đang khởi động profile khác/đã dùng phiên bản/config khác.
2. **TLS/certificate** không phù hợp, server hoặc client thiếu ALPN support, hoặc TLS library/JDK quá cũ.
3. **Cipher suite/TLS version** được thương lượng không phù hợp yêu cầu HTTP/2; HTTP/1.1 trên TLS vẫn có thể hoạt động.
4. **Proxy/CDN** kết thúc TLS ở nơi khác. Backend được bạn cấu hình h2 không ảnh hưởng trực tiếp đến ALPN của public endpoint.
5. **HTTP client không hỗ trợ HTTP/2** ở bản build thực tế; kiểm **curl -V** hoặc tính năng thư viện.
6. **ALPN chỉ quảng bá http/1.1** do client cố tình dùng **--http1.1**, cấu hình proxy hoặc chính sách server.
7. **SNI/virtual host** khác nhau khiến server chọn certificate/TLS configuration khác so với hostname đang thử.

Không vô hiệu hóa TLS certificate verification trong production để “sửa ALPN”. **-k** trong demo chỉ nhằm chấp nhận self-signed cert local. Một máy chủ có thể có ALPN h2 tốt nhưng certificate không đáng tin; đó vẫn là kết nối cần được khắc phục trước khi triển khai bảo mật.

## 12. Nhận diện lỗi bằng curl: ma trận kiểm thử nhanh

Giả sử profile **h2c ở :8080** hoặc profile **h2 ở :8443** đang chạy theo từng thời điểm:

| Lệnh | Đường đi và ý định | Điều cần quan sát |
| --- | --- | --- |
| **curl -v --http1.1 http://localhost:8080/api/protocol** | HTTP/1.1 cleartext | Backend thấy HTTP/1.1. |
| **curl -v --http2-prior-knowledge http://localhost:8080/api/protocol** | h2c direct | Backend thấy HTTP/2.0 nếu Tomcat hỗ trợ và chấp nhận. |
| **curl -v --http2 http://localhost:8080/api/protocol** | Thử Upgrade h2c kiểu cũ | Có thể thấy 101 rồi h2c, HTTP/1.1 fallback hoặc lỗi. |
| **curl -vk --http2 https://localhost:8443/api/protocol** | ALPN h2 trên TLS | Trace ALPN, status HTTP/2, certificate self-signed demo. |
| **curl -vk --http1.1 https://localhost:8443/api/protocol** | Ép HTTP/1.1 trên TLS | Kết nối vẫn HTTPS, không nhất thiết dùng HTTP/2. |
| **openssl s_client -connect localhost:8443 -servername localhost -alpn h2,http/1.1** | Chỉ khảo sát TLS ALPN | ALPN negotiated protocol, không tự thực hiện HTTP request. |

Các lệnh dùng **--http2-prior-knowledge** yêu cầu curl được build với HTTP/2. Một số bản curl/SSL backend có chi tiết ALPN hoặc TLS trace khác; dùng khả năng và version của công cụ thực sự đang cài đặt.

### Trường hợp không thành công

**Một:** **curl --http2-prior-knowledge http://...** kết thúc lỗi ngay hoặc server log request không hợp lệ. Có thể server chỉ nhận HTTP/1.1 hoặc bạn đã gọi nhầm cổng TLS. Không chữa bằng việc thêm **Upgrade: h2c** vào header mà không hiểu cơ chế, vì prior knowledge là **direct preface**, khác HTTP/1.1 Upgrade.

**Hai:** **curl --http2 https://...** vẫn hiện HTTP/1.1. Xem **ALPN** đã chọn gì, có reverse proxy không, cert/JDK/container nào xử lý TLS và **server.http2.enabled** có ở chính public endpoint đó không.

**Ba:** **curl báo SSL wrong version number** khi gọi https://localhost:8080. Có thể bạn gửi TLS ClientHello vào cổng HTTP cleartext; xem đúng scheme/port/profiles.

**Bốn:** Browser DevTools hiện h2, còn backend log HTTP/1.1. Không phải mâu thuẫn: có thể browser đang kết nối h2 với proxy, proxy lại gọi HTTP/1.1 tới Spring Boot.

**Năm:** Thử h2c trên cổng public từ internet bị policy chặn. Đây có thể là chính sách ingress/CDN/browser không hỗ trợ cleartext h2; không nên mở h2c công khai chỉ để match một bài test nếu không có nhu cầu thật.

## 13. HTTP/2 không sửa tất cả vấn đề hiệu năng

Sau khi thương lượng thành công, h2/h2c sử dụng cùng HTTP/2 semantics:

- **Multiplexing** cho phép nhiều streams trên một connection, hạn chế sự phụ thuộc thứ tự request ở tầng HTTP/1.1.
- **HPACK** giảm overhead header fields lặp lại; **khác** Content-Encoding gzip/br của body.
- **Flow control** dùng byte-level windows cho DATA frames ở stream và connection; **không** phải Reactive Streams **request(n)** của Reactor.
- **Server push** từng có trong HTTP/2 nhưng nhiều client/browser giảm hoặc ngừng hỗ trợ; không dùng server push như lợi ích mặc định của một hệ thống mới.
- **TCP head-of-line blocking** vẫn có khi packet mất trên connection; HTTP/3 với QUIC xử lý vấn đề theo kiến trúc khác.
- Spring MVC controller thực hiện JDBC blocking vẫn có thể chặn worker thread; h2 không làm JDBC thành non-blocking.
- Một network có RTT thấp, số request ít và payload nhỏ có thể không hưởng lợi đáng kể; đo thực tế thay vì quy mọi tăng tốc cho việc bật HTTP/2.

**h2c không nhanh hơn h2 một cách mặc định** chỉ vì bỏ TLS; TLS session reuse, CPU, network isolation, proxy hop và hạ tầng quyết định tổng latency. Việc bỏ TLS để tiết kiệm vài ms trong hệ thống không đáng tin có thể tạo rủi ro bảo mật lớn hơn nhiều.

## 14. Kiểm thử triển khai đúng tầng và đo protocol thật

Trước khi kết luận cấu hình sản xuất đúng, hãy xác nhận theo trình tự:

1. **Đúng profile/config:** lưu snapshot server.http2.enabled, server.ssl.*, port và embedded server thực sự; tránh lấy property của môi trường dev áp dụng cho prod.
2. **TLS handshake ở public domain:** kiểm cert chain/hostname, TLS version, SNI và ALPN chọn **h2** hay **http/1.1**.
3. **HTTP request thực:** curl hoặc browser DevTools cho thấy HTTP version được dùng, response đúng chức năng và không có stream/protocol error.
4. **Từng proxy hop:** xác định edge↔ingress↔Spring Boot chạy HTTP/1.1/h2/h2c như thiết kế, không suy từ public endpoint.
5. **Khả năng fallback:** client chỉ hỗ trợ HTTP/1.1 có phục vụ được hay không; nếu không, đó là lựa chọn tương thích có chủ đích chứ không phải lỗi bất ngờ.
6. **Cleartext policy:** không expose h2c trên mạng không tin cậy khi chưa được đánh giá; phân định vùng bảo mật rõ ràng.
7. **Observability:** phân loại request theo protocol, TLS handshake errors, connection resets, stream errors, latency/throughput, proxy access logs.
8. **Load test:** đo HTTP/1.1 vs h2 với cùng TLS/network/connection reuse/concurrency và workload, không đo một request localhost rồi kết luận.
9. **Thay đổi liên quan:** bảo đảm HTTP/2-only headers đã được adapter xử lý; không tự đưa header **Connection/Upgrade** không hợp lệ vào HTTP/2.
10. **Đánh giá upgrade legacy:** nếu từng dùng **Upgrade: h2c** và **HTTP2-Settings**, lên kế hoạch dùng prior knowledge/TLS ALPN theo RFC 9113 hoặc duy trì interoperability có kiểm soát.

Công cụ như **Wireshark** có thể thấy cleartext connection preface và frame h2c, còn để quan sát h2 trên TLS thường cần nguồn giải mã hợp lệ hoặc metrics từ endpoint. Không tự giả định packet capture TLS sẽ hiển thị rõ HEADERS/DATA HTTP/2; TLS đang mã hóa payload.

## 15. Lỗi và ngộ nhận phổ biến

| Nhận định hoặc triệu chứng | Điều đúng và cách khắc phục |
| --- | --- |
| **“HTTP/2 luôn dùng TLS.”** | Không hoàn toàn: **h2c** là HTTP/2 cleartext. **h2 qua HTTPS** thì TLS bắt buộc. |
| **“h2c là HTTP/1.1.”** | Không: h2c dùng HTTP/2 binary framing sau khi kết nối được thiết lập. |
| **“Bật server.http2.enabled=true là mọi request thành HTTP/2.”** | Không: server bật **khả năng**, client/hop phải chọn đúng giao thức. |
| **“Có HTTPS nên chắc chắn h2.”** | Không: HTTPS có thể thương lượng **http/1.1**. |
| **“ALPN h2c trên HTTPS.”** | Sai: HTTP/2 over TLS dùng **ALPN h2**, còn **h2c** không dùng TLS/ALPN. |
| **“SNI chọn h2.”** | Sai: SNI chỉ hostname, ALPN mới chọn protocol ứng dụng. |
| **“curl --http2 và --http2-prior-knowledge là giống nhau với http://.”** | Sai: **--http2** thử Upgrade cũ; **--http2-prior-knowledge** gửi h2c preface ngay. |
| **“Upgrade: h2c là chuẩn mới nhất.”** | Sai: RFC 9113 đã đánh dấu **Upgrade h2c/HTTP2-Settings obsolete**; vẫn có legacy support. |
| **“Tomcat 10.1 không hỗ trợ h2c.”** | Không đúng với Spring Boot 3.3/Tomcat 10.1; tài liệu Boot và Tomcat xác nhận hỗ trợ. |
| **“Browser thấy h2 nên backend cũng h2.”** | Không chắc: proxy có thể chuyển h2 thành HTTP/1.1 hoặc h2c ở hop sau. |
| **“h2c sau HTTPS proxy vẫn là TLS end-to-end.”** | Không: hop h2c cleartext, phải xét trust boundary và chính sách network. |
| **“HPACK nén response body.”** | Không: HPACK là header compression; body gzip/br là content coding khác. |
| **“HTTP/2 loại bỏ mọi HOL blocking.”** | Không: vẫn chạy trên TCP, có transport-level head-of-line blocking. |
| **“Đặt HTTPS profile mà không có cert vẫn chạy h2.”** | Không: HTTPS cần cấu hình TLS hợp lệ; demo dùng keystore tự ký chỉ cho local. |
| **“curl -k sửa được vấn đề ALPN.”** | Không: -k bỏ xác minh trust certificate, không tự thêm khả năng server h2 hoặc ALPN. |

## 16. Câu hỏi tự kiểm tra và tình huống thực tế

**Câu 1:** Client gửi **ALPN=[h2,http/1.1]**, server chọn **http/1.1**, TLS handshake thành công. Kết nối đang dùng giao thức gì?  
**Đáp án:** HTTP/1.1 **trên TLS**, không phải h2c hoặc HTTP/2.

**Câu 2:** Client gửi **curl --http2-prior-knowledge http://localhost:8080** đến một Tomcat có h2c direct. Có TLS hoặc ALPN không?  
**Đáp án:** Không. TCP cleartext + HTTP/2 preface và frames.

**Câu 3:** Vì sao **curl --http2 http://localhost:8080** có thể phát **Upgrade: h2c** trong trace, nhưng tài liệu RFC 9113 lại khuyên prior knowledge?  
**Đáp án:** curl vẫn giữ cơ chế tương thích từ RFC 7540; RFC 9113 đã deprecated/obsolete cơ chế Upgrade/HTTP2-Settings vì không được triển khai rộng.

**Câu 4:** Browser DevTools thấy **h2**, nhưng **request.getProtocol()** ở Spring Boot trả **HTTP/1.1**. Ai sai?  
**Đáp án:** Không ai nhất thiết sai: browser nói h2 với proxy/ingress, backend nhận HTTP/1.1 từ proxy.

**Câu 5:** **server.http2.enabled=true** và **server.ssl.enabled=false** trong Spring Boot 3.3 có thể tạo kiểu endpoint nào?  
**Đáp án:** **h2c cleartext** trên embedded server hỗ trợ, nhưng còn tùy client/chặng mạng và có thể đồng thời xử lý HTTP/1.1.

**Câu 6:** Có thể làm **h2** hoạt động trên HTTPS bằng cách thêm header **Upgrade: h2** trong request HTTP/1.1 không?  
**Đáp án:** Không; dùng **TLS ALPN h2**. Gửi HTTP/1.1 Upgrade không thay thế handshake chọn giao thức.

**Câu 7:** Vì sao kết nối h2c backend không an toàn như h2?  
**Đáp án:** h2c không có TLS trên hop, do đó không cung cấp mã hóa, xác thực peer hoặc bảo vệ tính toàn vẹn của TLS. Có thể dùng trong trust boundary nội bộ đã đánh giá, không mặc định đưa ra internet.

**Câu 8:** Một request trên HTTP/2 được gửi qua stream 3, rồi có HEADERS/DATA. HTTP status 200 hay method GET có thay đổi semantics không?  
**Đáp án:** Không; HTTP/2 giữ semantics HTTP, thay đổi framing/multiplexing và cách biểu diễn fields.

**Câu 9:** Nếu **curl -V** không có tính năng HTTP2, bật server.http2.enabled có làm curl --http2 hoạt động không?  
**Đáp án:** Không; client cũng phải hỗ trợ HTTP/2.

**Câu 10:** Khi nào dùng h2c thay vì h2?  
**Đáp án:** Khi một hop backend dùng cleartext theo kiến trúc có kiểm soát, client/server hỗ trợ prior knowledge và chính sách bảo mật cho phép. Với public-facing HTTPS, ưu tiên h2 qua TLS ALPN.

## 17. Tài liệu chính thống để đối chiếu

- **RFC 9113 – HTTP/2 (chuẩn hiện hành):** https://www.rfc-editor.org/rfc/rfc9113.html — §3.1 định danh **h2/h2c**, §3.2 **https/TLS/ALPN**, §3.3 **prior knowledge**, §3.4 **connection preface**, §9.2 **TLS requirements**, §11 đánh dấu Upgrade h2c và HTTP2-Settings obsolete.
- **RFC 7540 – HTTP/2 (đã được RFC 9113 thay thế):** https://www.rfc-editor.org/rfc/rfc7540 — mô tả lịch sử **HTTP/1.1 Upgrade: h2c** để đọc tài liệu và trace cũ, **không dùng thay RFC 9113**.
- **RFC 7301 – TLS ALPN:** https://www.rfc-editor.org/rfc/rfc7301 — protocol negotiation trong TLS.
- **Spring Boot 3.3 – Embedded Web Servers / Configure HTTP/2:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — server.http2.enabled, khả năng **h2/h2c**, SSL, Tomcat/Jetty/Netty/Undertow.
- **Spring Boot 3.3 – SSL và Server Properties:** https://docs.spring.io/spring-boot/3.3/appendix/application-properties/ — server.ssl.*, server.http2.enabled.
- **Apache Tomcat 10.1 – HTTP Connector:** https://tomcat.apache.org/tomcat-10.1-doc/config/http.html — h2 TLS, h2c Upgrade và direct, HTTP2 UpgradeProtocol.
- **curl manual:** https://curl.se/docs/manpage.html — **--http2**, **--http2-prior-knowledge**, **--http1.1**, **-v** và behavior HTTP/HTTPS.
- **OpenSSL s_client manual:** https://docs.openssl.org/3.0/man1/openssl-s_client/ — **-alpn** và **-servername**.
