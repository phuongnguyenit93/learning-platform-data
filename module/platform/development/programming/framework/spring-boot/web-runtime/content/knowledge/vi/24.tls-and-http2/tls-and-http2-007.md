# Bật HTTP/2 và kiểm tra điều kiện hỗ trợ của máy chủ trong Spring Boot

## 1. Mục tiêu: bật đúng giao thức, đo đúng kết quả

HTTP/2 là phiên bản giao thức HTTP có cơ chế **binary framing**, **multiplexing** nhiều luồng request/response trên một kết nối và **nén header** (HPACK). Trong Spring Boot, ta có thể bật hỗ trợ bằng một property:

```properties
server.http2.enabled=true
```

Nhưng đây **chỉ là yêu cầu cấu hình**. Client thực sự có dùng HTTP/2 hay không còn phụ thuộc:

- **HTTP server đang chạy:** Tomcat, Jetty, Undertow hoặc Reactor Netty, và các module HTTP/2 đi kèm.
- **Cách kết nối:** `h2` (HTTP/2 qua TLS/HTTPS) hay `h2c` (HTTP/2 không TLS).
- **JDK/TLS provider/ALPN:** với `h2`, client và server phải thương lượng được giao thức trong TLS handshake.
- **Client:** curl, trình duyệt, load balancer, ingress hoặc proxy có hỗ trợ HTTP/2 trên chính kết nối đó không.
- **Đường đi mạng:** HTTP/2 giữa **browser và reverse proxy** không đồng nghĩa HTTP/2 giữa **reverse proxy và Spring Boot**.
- **Chứng chỉ và chính sách TLS:** certificate, ciphers, TLS version và hostname phải hợp lệ theo yêu cầu production.

Đích kiểm thử không phải chỉ thấy ứng dụng khởi động thành công hoặc thấy property bằng `true`. Phải quan sát **HTTP version thực tế** trên kết nối, ví dụ output từ `curl -w '%{http_version}'` hoặc ALPN được chọn.

Bài này minh họa bằng **Spring Boot 3.5.x, Java 17+ và Tomcat nhúng**. Khi nói tới Jetty, Undertow và Reactor Netty, cần kiểm tra chính xác phiên bản Spring Boot/embedded server, không lấy hướng dẫn của Boot 2.x hoặc 4.x áp dụng nguyên xi.

## 2. Phân biệt HTTP/1.1, HTTP/2, h2, h2c và HTTPS

### 2.1. HTTP/2 cải thiện điều gì?

HTTP/1.1 hỗ trợ keep-alive để dùng lại kết nối, nhưng việc chở nhiều request song song trên một kết nối bị giới hạn. Browser thường phải dùng nhiều kết nối hoặc chờ request. HTTP/2 cho phép các **streams** cùng tồn tại trên một kết nối, mỗi stream được chia thành những **frames** nhị phân và có flow control.

Lợi ích có thể thấy ở trang nhiều tài nguyên nhỏ hoặc API gọi nhiều request trên một kết nối:

- Nhiều stream đồng thời giúp tránh một số hạn chế tuần tự của HTTP/1.1.
- HPACK giảm trùng lặp header so với việc gửi nguyên header trên nhiều request.
- Một kết nối được dùng hiệu quả hơn trong một số kiểu tải.
- HTTP semantics như `GET`, `POST`, URL, status code vẫn giữ nguyên; phần lớn controller/service không cần sửa vì đổi giao thức.

HTTP/2 **không** biến JDBC blocking thành reactive, không tự cải thiện truy vấn DB chậm và không bảo đảm độ trễ luôn thấp hơn. Một kết nối TCP vẫn chịu ảnh hưởng TCP head-of-line blocking ở tầng vận chuyển; HTTP/3 dựa trên QUIC giải quyết một số hạn chế theo hướng khác. Server Push từng là tính năng HTTP/2 nhưng không nên thiết kế ứng dụng mới phụ thuộc vào nó: hỗ trợ của browser đã suy giảm đáng kể.

### 2.2. Hai cách chạy HTTP/2

| Thuật ngữ | Transport | Dùng ở đâu | Cách thương lượng |
| --- | --- | --- | --- |
| `http/1.1` | TCP, có thể kèm TLS | Phổ biến và tương thích rộng | HTTP/1.1, có thể được chọn khi không có HTTP/2 |
| **`h2`** | TLS/HTTPS | Kết nối browser ↔ server/reverse proxy thông thường | **ALPN** trong TLS handshake |
| **`h2c`** | TCP không TLS | Mạng nội bộ, proxy → backend, môi trường thử nghiệm | HTTP/1.1 `Upgrade: h2c` hoặc HTTP/2 prior knowledge |
| **HTTP/3** | QUIC/UDP, có TLS tích hợp | Hệ sinh thái HTTP/3 riêng | Không được bật bằng property HTTP/2 |

**H2 và H2C không thay thế nhau:**

- `h2` cần TLS và ALPN thương lượng protocol identifier `h2`.
- `h2c` không mã hóa đường truyền. Chỉ nên sử dụng khi bạn thật sự kiểm soát đoạn mạng, chẳng hạn link nội bộ sau reverse proxy/mesh bảo mật.
- Đa số trình duyệt triển khai HTTP/2 **qua HTTPS (h2)**, không dùng h2c tùy tiện cho website công khai.
- `server.http2.enabled=true` không tự phát hành chứng chỉ TLS, không tự bật HTTPS và không tự sửa cấu hình proxy.

### 2.3. HTTP/2 khác “TLS 2” hoặc “SSL 2”

TLS phiên bản 1.2/1.3 là **giao thức bảo mật transport**; HTTP/2 là **phiên bản giao thức ứng dụng** chạy trên đó trong chế độ h2. Ký hiệu `h2` không có nghĩa TLS phiên bản 2. HTTP/2 cũng không bắt buộc mọi ứng dụng web dùng reactive programming.

Sơ đồ:

```text
Browser                         Spring Boot nhúng Tomcat
  |                                     |
  | TCP connect :8443                   |
  |------------------------------------>|
  | TLS ClientHello + ALPN h2,http/1.1  |
  |------------------------------------>|
  | TLS ServerHello + chọn h2           |
  |<------------------------------------|
  | HTTP/2 frames: GET /api/protocol    |
  |====================================>|
  | HTTP/2 frames: 200 + response       |
  |<====================================|
  | nhiều streams có thể chung kết nối  |
```

Nếu TLS chọn `http/1.1` thay vì `h2` thì cùng một endpoint vẫn có thể trả HTTP 200, nhưng **không có nghĩa đã kiểm thử thành công HTTP/2**.

## 3. Property chính trong Spring Boot

### 3.1. Bật hỗ trợ HTTP/2

```properties
server.http2.enabled=true
```

Theo tài liệu **Spring Boot 3.5**, cả hai biến thể được hỗ trợ:

- Khi **server SSL/TLS được bật**, HTTP/2 sử dụng **`h2`** qua TLS (nếu server/JDK/client thương lượng được).
- Khi **SSL không bật**, server có thể hỗ trợ **`h2c`** qua TCP; phù hợp một số triển khai phía sau proxy thực hiện TLS termination.

Không cần viết `@RestController` đặc biệt để “mở HTTP/2”: việc chọn protocol nằm ở **web server/connector**, trước khi request tới controller. Controller có thể không thay đổi dù client dùng HTTP/1.1 hoặc HTTP/2.

### 3.2. Kết hợp HTTPS

Cấu hình kiểu PKCS#12 keystore có thể là:

```properties
server.port=8443
server.http2.enabled=true
server.ssl.enabled=true
server.ssl.key-store=file:./dev-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localdev
```

Đây là **ví dụ cấu hình môi trường học tập**. `file:./dev-keystore.p12` là keystore nằm **ngoài JAR**, tương đối với working directory khi chạy process. Password lấy từ environment variable, không hardcode vào source. Nếu keystore/certificate sai, server có thể không khởi động hoặc TLS handshake không thành công; `server.http2.enabled` không khắc phục được.

Đối với production, nên quản lý certificate/private key bằng secret manager, mounted secret hoặc SSL bundles phù hợp, dùng CA đáng tin và hostname đúng. **Không commit private key/keystore vào Git** và không dùng chứng chỉ self-signed demo cho traffic thật.

### 3.3. Cấu hình khác cần phân biệt

| Property/cơ chế | Tác dụng | Liên quan tới HTTP/2 thế nào? |
| --- | --- | --- |
| `server.http2.enabled` | Bật hỗ trợ HTTP/2 ở web server | Cờ chính |
| `server.port` | Cổng listener | Không xác định protocol |
| `server.ssl.*` | TLS certificate, keys, protocol/cipher | Cần cho h2 qua HTTPS |
| `server.ssl.bundle` | Tham chiếu SSL bundle có tên | Cách quản lý TLS thay thế cấu hình discrete |
| `server.forward-headers-strategy` | Cách xử lý forwarded headers từ proxy | Không trực tiếp biến upstream thành HTTP/2 |
| `server.compression.enabled` | Nén response body HTTP | Độc lập với HTTP/2/HPACK |
| `management.server.port` | Cổng Actuator riêng nếu cấu hình | Cần kiểm tra protocol/certificate của listener riêng |
| `spring.main.web-application-type` | Servlet, reactive hoặc none | Ảnh hưởng loại web server được tạo, không trực tiếp bắt buộc h2 |

**Không nhầm HPACK với gzip:** HTTP/2 nén **headers** bằng HPACK; response **body** có thể vẫn dùng gzip/br tùy `Accept-Encoding` và cấu hình compression. Bật HTTP/2 không có nghĩa mọi JSON/image/body đã được nén.

## 4. Điều kiện hỗ trợ theo embedded server

Spring Boot có thể chạy trên nhiều web server; HTTP/2 không phải một “dependency Spring MVC” thuần túy.

### 4.1. Ma trận cho Spring Boot 3.5

| Server | Web stack thông dụng | h2 TLS | h2c không TLS | Điều kiện chính |
| --- | --- | --- | --- | --- |
| **Tomcat 10.1.x** | Spring MVC Servlet mặc định | Có | Có | Java 17+ và TLS/ALPN phù hợp, Boot bật `server.http2.enabled` |
| **Jetty** | Servlet hoặc reactive adapter | Có | Có | **Cần thêm Jetty HTTP/2 server module**; h2 TLS còn cần ALPN provider tương ứng |
| **Reactor Netty** | Spring WebFlux mặc định | Có | Có | Hỗ trợ trong stack mặc định; native TLS library là tùy chọn hiệu năng, không mặc định bắt buộc |
| **Undertow** | Servlet hoặc adapter nếu bản Boot hỗ trợ | Có | Có | Boot/server tích hợp đúng và phiên bản phù hợp |

**Phạm vi phiên bản:** bảng dựa trên hướng dẫn Spring Boot **3.5.x**, không phải cam kết mọi starter/server có tên tương tự đều tồn tại ở Boot 4.x. Ví dụ, Spring Boot phiên bản mới có thể thay đổi các web server được hỗ trợ. Kiểm tra đúng BOM/guide của version đang chạy.

### 4.2. Tomcat (mặc định cho `spring-boot-starter-web`)

Với Spring Boot 3.5, starter web thường kéo theo **Tomcat 10.1.x**. Tomcat hỗ trợ `h2` và `h2c` mà không cần cài thêm native library để dùng HTTP/2 trong môi trường Java hiện đại. JDK 17 có ALPN trong JSSE nên có thể thử h2 TLS ngay với cấu hình đúng.

Tomcat có tùy chọn `libtcnative`/OpenSSL để dùng TLS native trong một số tình huống; đó là **lựa chọn tối ưu/triển khai**, không phải yêu cầu mặc định để chạy HTTP/2 trên Java 17.

Đối với một Tomcat cài **riêng ngoài Spring Boot**, quản trị viên có thể phải cấu hình `UpgradeProtocol`/connector thủ công. Nhưng đối với **embedded Tomcat do Spring Boot auto-configure**, hãy bắt đầu bằng `server.http2.enabled=true` trước khi viết cấu hình connector tự chế.

### 4.3. Jetty: chú ý module HTTP/2/ALPN

Trong dòng Spring Boot 3.5, khi chọn Jetty thay Tomcat, chỉ thêm `spring-boot-starter-jetty` mà thiếu module HTTP/2 **có thể chưa đủ**. Tài liệu Boot nêu dependency:

```xml
<dependency>
    <groupId>org.eclipse.jetty.http2</groupId>
    <artifactId>jetty-http2-server</artifactId>
</dependency>
```

Đây là **fragment dependency**, không phải POM đầy đủ. Với **h2 qua TLS**, trên JDK có ALPN thường cần thêm:

```xml
<dependency>
    <groupId>org.eclipse.jetty</groupId>
    <artifactId>jetty-alpn-java-server</artifactId>
</dependency>
```

Một lựa chọn thay thế theo tài liệu Jetty là dùng Conscrypt và `jetty-alpn-conscrypt-server` nếu môi trường được cấu hình như vậy. Không thêm đồng thời mọi ALPN provider theo thói quen. Với `h2c` không TLS, Jetty HTTP/2 server module là bước quan trọng, không cần TLS ALPN provider.

Muốn chuyển từ Tomcat sang Jetty trên Spring MVC, phải loại Tomcat starter và thêm Jetty starter đúng version. Ví dụ **snippet thay thế phần dependencies** của `spring-boot-starter-web`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
<dependency>
    <groupId>org.eclipse.jetty.http2</groupId>
    <artifactId>jetty-http2-server</artifactId>
</dependency>
<dependency>
    <groupId>org.eclipse.jetty</groupId>
    <artifactId>jetty-alpn-java-server</artifactId>
</dependency>
```

Không copy fragment này vào `pom.xml` demo Tomcat ở mục 7 trừ khi **chủ động chuyển server** và kiểm tra tài liệu dành cho Spring Boot đúng phiên bản.

### 4.4. Reactor Netty và WebFlux

Với `spring-boot-starter-webflux` thông thường, Spring Boot dùng **Reactor Netty**. Trong dòng Boot 3.5, Reactor Netty hỗ trợ h2 và h2c. Java 17 có TLS/ALPN hiện đại; có thể thêm `io.netty:netty-tcnative-boringssl-static` nếu muốn dùng native TLS library trên nền tảng tương thích để tối ưu, nhưng **không cần nó chỉ để chứng minh HTTP/2 hoạt động**.

Nếu một project khai báo **cả** `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường ưu tiên **Servlet MVC web application type**, trừ khi được cấu hình khác. Đừng nhìn thấy `reactor-netty` trong dependency tree rồi kết luận server HTTP hiện tại đang là Netty.

### 4.5. Undertow

Spring Boot 3.5 hỗ trợ HTTP/2 h2/h2c trong Undertow mà không cần một module h2 bổ sung theo hướng dẫn embedded web server. Tuy vậy điều kiện thực tế còn phụ thuộc cấu hình, JDK/TLS và runtime. Với Boot major mới hơn, kiểm tra lại xem Undertow starter còn được hỗ trợ trước khi sao chép một POM cũ.

### 4.6. Checklist trước khi bật

1. Xác định **Spring Boot version thật** và managed server version thông qua Maven/Gradle dependency tree.
2. Xác định **web application type**: MVC/Tomcat, WebFlux/Netty hay custom server.
3. Xác định **cấp TLS termination**: Spring Boot tự nhận HTTPS hay load balancer/ingress nhận HTTPS.
4. Kiểm tra Java runtime bằng `java -version`; trong ví dụ này dùng **JDK 17+**, đã có ALPN support chuẩn.
5. Nếu dùng Jetty, thêm đúng HTTP/2/ALPN modules theo phiên bản.
6. Cấu hình `server.http2.enabled=true` và certificate/SSL cho h2.
7. Xác minh bằng **client có HTTP/2** thay vì chỉ log application started.
8. Kiểm tra thêm HTTP/1.1 fallback và security/operational metrics.

## 5. ALPN: vì sao HTTPS chưa chắc là HTTP/2?

**ALPN** (Application-Layer Protocol Negotiation) là TLS extension cho client/server chọn giao thức ứng dụng trên một kết nối TLS. Browser có thể đề xuất `h2` và `http/1.1`; server chọn protocol hỗ trợ. Nếu server chỉ chọn `http/1.1`, HTTPS vẫn hoạt động bình thường nhưng kết nối **không phải HTTP/2**.

Dòng xử lý:

```text
TLS ClientHello
  ALPN protocols: ["h2", "http/1.1"]
                     |
                TLS server
             certificate + key
             TLS version/ciphers
             HTTP/2 capability
                     |
ALPN selected: h2   (nếu client/server hỗ trợ phù hợp)
                     |
 HTTP/2 connection preface và frames
```

### Java và ALPN

- JDK 17 có hỗ trợ ALPN trong chuẩn Java TLS stack; không cần lấy hướng dẫn cũ yêu cầu **JDK 8 ALPN boot patch** làm điều kiện bắt buộc.
- Nếu chạy JDK/JSSE provider tùy biến, môi trường FIPS, proxy SSL hoặc native TLS đặc biệt, phải xác nhận giao thức thực tế bằng `curl`/`openssl`.
- HTTP/2 qua TLS yêu cầu sử dụng TLS và cipher suites phù hợp với quy định HTTP/2; trong production nên dùng TLS 1.2/1.3 hiện đại, certificate/key đủ mạnh.
- TLS 1.3 không phải **điều kiện duy nhất** để dùng HTTP/2: h2 có thể hoạt động trên TLS 1.2 phù hợp.
- Certificate không hợp lệ hoặc hostname không khớp là lỗi TLS/trust; không được “sửa” bằng cách tắt xác minh certificate trong production.

### Kiểm tra ALPN bằng OpenSSL

Khi server TLS local chạy ở 8443:

```bash
openssl s_client -connect localhost:8443 -servername localhost -alpn h2,http/1.1
```

Trong output thành công, tìm dòng tương tự:

```text
ALPN protocol: h2
```

Giá trị thực có thể là `h2`, `http/1.1` hoặc không có protocol được thương lượng, tùy server/client. Lệnh trên **chưa gửi HTTP/2 request hoàn chỉnh**; nó chỉ kiểm tra phần TLS/ALPN. Sau đó cần kiểm thử request thật bằng `curl --http2`.

Certificate self-signed ở local vẫn có thể làm OpenSSL in lỗi verify — đây là chuyện **trust của certificate**, khác việc ALPN có chọn `h2` hay không.

## 6. Phân biệt HTTP/2 ở edge, upstream và client

Khi dùng reverse proxy:

```text
Browser --HTTPS + h2--> Nginx / Ingress / CDN
                              |
                   HTTP/1.1 hoặc h2c hoặc h2
                              |
                       Spring Boot backend
```

Có **hai kết nối độc lập**. Proxy hoàn toàn có thể hỗ trợ HTTP/2 bên ngoài nhưng gửi HTTP/1.1 vào app. Trong trường hợp đó:

- Browser DevTools cho thấy HTTP/2.
- `curl --http2 https://public-domain` cho thấy HTTP/2.
- Backend request có thể vẫn là HTTP/1.1 và không cần `server.http2.enabled`.
- Tối ưu giao thức ở bên ngoài **không chứng minh** HTTP/2 tới backend.

Nếu kiến trúc yêu cầu HTTP/2 end-to-end hoặc gRPC upstream, phải kiểm tra proxy có hỗ trợ **HTTP/2/h2c upstream** cụ thể, cấu hình gateway tương ứng, và thử kết nối **trực tiếp** hoặc từ pod/host thuộc mạng backend. Nhiều proxy cấu hình `proxy_pass` HTTP upstream mặc định dùng HTTP/1.1; không tự nâng lên h2c chỉ vì edge bật h2.

### TLS termination tại Spring Boot

```text
Client -- TLS/ALPN h2 --> Spring Boot:8443
```

Bật `server.http2.enabled=true` và TLS của Spring Boot. Trực tiếp kiểm chứng cả ALPN và server handler.

### TLS termination tại proxy

```text
Client -- TLS/ALPN h2 --> Gateway -- HTTP/1.1 --> Spring Boot:8080
```

HTTP/2 ở phía client được gateway xử lý. Việc backend dùng HTTP/1.1 có thể vẫn là lựa chọn **hợp lý**, không phải lỗi. Nên ưu tiên độ an toàn, khả năng tương thích và đo hiệu năng trước khi yêu cầu h2c upstream.

### h2c trong mạng nội bộ

```text
Gateway -- h2c trên mạng tin cậy --> Spring Boot:8081
```

Spring Boot 3.5 có thể hỗ trợ h2c khi SSL không bật. Nhưng **h2c không bảo mật nội dung**, không xác thực peer bằng TLS; cần security boundary ở tầng mạng, service mesh hoặc TLS end-to-end khi dữ liệu nhạy cảm.

**Cẩn trọng với forwarded headers:** `X-Forwarded-Proto: https` mô tả scheme công khai trước proxy, không phải “upstream đang dùng HTTP/2”. Đừng dùng header đó để suy ra protocol HTTP/2, và không tin forwarded headers do client Internet có thể tự giả mạo.

## 7. Ví dụ chạy được: Java 17 + Spring Boot MVC + embedded Tomcat

Project demo sau có thể được build và chạy trên JDK 17+, Maven và Spring Boot **3.5.0** (một bản phát hành của nhánh 3.5, không phải lời khẳng định đây là bản vá mới nhất). Hãy cập nhật patch version theo chính sách dự án thực.

Ta tạo ba file cấu hình:

- `application.properties`: bật HTTP/2 chung.
- `application-tls.properties`: profile HTTPS/`h2` ở port 8443.
- `application-h2c.properties`: profile HTTP/`h2c` ở port 8081.

Hai profile độc lập giúp **không cần nạp key-store password trong lần thử h2c**, đồng thời dễ quan sát sự khác nhau.

### 7.1. Cấu trúc thư mục

```text
http2-demo/
├── pom.xml
├── dev-keystore.p12            (tạo bằng keytool; chỉ local, không commit)
└── src/
    └── main/
        ├── java/
        │   └── com/example/http2demo/
        │       └── Http2DemoApplication.java
        └── resources/
            ├── application.properties
            ├── application-tls.properties
            └── application-h2c.properties
```

`dev-keystore.p12` **không nằm trong `src/main/resources`** nên không bị đóng gói vào executable JAR theo cấu trúc này. Chạy command từ thư mục gốc có POM để `file:./dev-keystore.p12` được resolve đúng.

### 7.2. `pom.xml` hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>http2-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

`spring-boot-starter-web` đưa vào Spring MVC cùng Tomcat nhúng được Boot quản lý. Không cần dependency `jetty-http2-server` vì ví dụ **không dùng Jetty**. Cấu hình Java17 được Spring Boot parent/Maven plugin sử dụng để biên dịch.

### 7.3. Java source hoàn chỉnh

File `src/main/java/com/example/http2demo/Http2DemoApplication.java`:

```java
package com.example.http2demo;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class Http2DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(Http2DemoApplication.class, args);
    }
}

@RestController
class ProtocolController {

    @GetMapping(value = "/protocol", produces = MediaType.TEXT_PLAIN_VALUE)
    public String protocol(HttpServletRequest request) {
        return "servletProtocol=" + request.getProtocol()
                + "\nscheme=" + request.getScheme()
                + "\nsecure=" + request.isSecure() + "\n";
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "hello\n";
    }
}
```

Trong cùng file Java, `Http2DemoApplication` là class `public` đúng tên file; `ProtocolController` là package-private và vẫn được component scan phát hiện. `HttpServletRequest#getProtocol()` cho thấy giao thức **backend server đang xử lý trực tiếp** (trong Tomcat với h2 thường là `HTTP/2.0`). `getScheme()`/`isSecure()` cho biết request nhìn từ Servlet container; nếu chạy qua proxy và bật forwarded-header processing, kết quả đó có thể chịu ảnh hưởng forwarded headers được tin cậy.

Việc controller trả chuỗi đơn giản chứng minh **business code không cần tự viết HTTP/2 frame**. Spring/Tomcat tạo frame/header tương ứng.

### 7.4. Properties

File `src/main/resources/application.properties`:

```properties
server.http2.enabled=true
```

File `src/main/resources/application-tls.properties`:

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./dev-keystore.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=localdev
```

File `src/main/resources/application-h2c.properties`:

```properties
server.port=8081
server.ssl.enabled=false
```

**Quan trọng:** bật **một profile** trong mỗi lần khởi động. Không chạy đồng thời hai profile `tls,h2c` trong demo vì properties cùng mục đích sẽ ghi đè nhau theo thứ tự, không tạo hai listener độc lập.

### 7.5. Tạo certificate self-signed bằng JDK keytool

Từ thư mục `http2-demo`, tạo keystore PKCS12 dùng cho **thử nghiệm local**:

```bash
keytool -genkeypair -alias localdev -keyalg RSA -keysize 2048 -storetype PKCS12 -keystore dev-keystore.p12 -storepass changeit -keypass changeit -validity 30 -dname "CN=localhost, OU=Development, O=Example, L=HCMC, ST=HCMC, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Lệnh là một dòng để chạy được ở Bash, PowerShell hoặc shell thông thường khi đã có JDK/keytool trong PATH. SAN chứa `localhost` và `127.0.0.1` để certificate đúng tên host của demo. Certificate **self-signed** không được CA công cộng tin mặc định; browser/curl sẽ báo lỗi verify nếu không chỉ định trust hoặc chế độ kiểm thử.

Xác nhận keystore (không cần xuất private key):

```bash
keytool -list -keystore dev-keystore.p12 -storetype PKCS12 -storepass changeit
```

Output phải cho thấy alias `localdev` (các dòng timestamp/metadata phụ thuộc JDK). **Không đưa keystore và password “changeit” này vào production.** Thêm `dev-keystore.p12` vào `.gitignore` nếu project dùng Git.

### 7.6. Build ứng dụng

Tại thư mục có POM:

```bash
mvn clean package
```

Sau khi build thành công, có file `target/http2-demo-1.0.0.jar`. Điều kiện quan trọng khi chạy:

- File `dev-keystore.p12` tồn tại ở working directory.
- Environment variable `TLS_KEYSTORE_PASSWORD` được đặt.
- Port `8443` chưa bị process khác chiếm.
- JDK và OS có khả năng dùng TLS/ALPN.

Với **Bash/Linux/macOS**:

```bash
export TLS_KEYSTORE_PASSWORD=changeit
java -jar target/http2-demo-1.0.0.jar --spring.profiles.active=tls
```

Với **PowerShell**:

```powershell
$env:TLS_KEYSTORE_PASSWORD = 'changeit'
java -jar target/http2-demo-1.0.0.jar --spring.profiles.active=tls
```

Đây là **mật khẩu demo**; trong production cấp qua secret manager/secured environment, không log giá trị và không commit file bí mật. Nếu password không được cấp, placeholder môi trường không thể resolve và app có thể fail startup; đó là hành vi đúng giúp tránh dùng keystore sai.

### 7.7. Kiểm tra HTTPS/h2 bằng curl

Ở terminal thứ hai, trước hết kiểm tra curl hỗ trợ HTTP/2:

```bash
curl -V
```

Trong output curl/libcurl cần có feature **`HTTP2`** (hoặc thông tin build tương đương). Không phải mọi build curl đều hỗ trợ HTTP/2, đặc biệt trên một số máy Windows cũ hoặc bản build tùy chỉnh. Nếu thiếu, lệnh `--http2` có thể báo lỗi **trước khi** kiểm tra được server; cần dùng curl đã build với thư viện HTTP/2 hoặc công cụ kiểm thử tương ứng.

Kiểm thử bản h2 TLS:

```bash
curl -sk --http2 -o /dev/null -w 'http_version=%{http_version}\n' https://localhost:8443/hello
```

Nếu thương lượng `h2` thành công, output đúng trọng tâm là:

```text
http_version=2
```

**`-k`/`--insecure` chỉ để bỏ qua verify certificate self-signed trong demo. Không dùng `-k` trong kiểm tra bảo mật production.** Với site production có CA tin cậy, bỏ `-k`.

Nếu output là `http_version=1.1`, response HTTP có thể vẫn là 200 nhưng **ALPN đã không chọn h2** hoặc client/server đang fallback HTTP/1.1. Chỉ thấy `server.http2.enabled=true` trong config là chưa đủ để gọi QA thành công.

Lệnh có chi tiết handshake:

```bash
curl -vk --http2 https://localhost:8443/protocol
```

Tìm các tín hiệu như:

```text
ALPN: server accepted h2
using HTTP/2
```

Tên/format log thay đổi theo curl version. Response body có thể giống:

```text
servletProtocol=HTTP/2.0
scheme=https
secure=true
```

Đây là **minh họa kết quả thường gặp trên Tomcat nhúng**; protocol string thực có thể khác cách hiển thị giữa servlet server/adapter, nên nên lấy dòng `http_version=2` từ **curl** làm bằng chứng trực tiếp về phiên truyền HTTP.

Kiểm thử client cố ý dùng HTTP/1.1 trên cùng listener:

```bash
curl -sk --http1.1 -o /dev/null -w 'http_version=%{http_version}\n' https://localhost:8443/hello
```

Kỳ vọng:

```text
http_version=1.1
```

Việc server hỗ trợ cả HTTP/2 và HTTP/1.1 **không phải lỗi**. Chế độ `server.http2.enabled=true` cho phép HTTP/2, không bắt mọi client dùng h2.

### 7.8. Kiểm tra h2c không TLS

Dừng ứng dụng TLS rồi chạy profile `h2c`:

```bash
java -jar target/http2-demo-1.0.0.jar --spring.profiles.active=h2c
```

Không cần password/keystore với profile này. Kết nối `http://localhost:8081` là **HTTP không TLS**:

```bash
curl -s --http2-prior-knowledge -o /dev/null -w 'http_version=%{http_version}\n' http://localhost:8081/hello
```

Trong môi trường Tomcat 10.1.x và curl hỗ trợ HTTP/2 prior knowledge, kỳ vọng:

```text
http_version=2
```

Tomcat 10.1 hỗ trợ h2c qua cả HTTP/1.1 Upgrade và **direct HTTP/2 prior knowledge**. Một cách kiểm tra khác:

```bash
curl -v --http2 http://localhost:8081/protocol
```

Với URL `http://`, `curl --http2` thường đề nghị nâng cấp bằng HTTP/1.1 `Upgrade: h2c`. Còn `--http2-prior-knowledge` gửi HTTP/2 trực tiếp; đây là hai cách thử **khác nhau**. Proxy/firewall có thể cho phép một cách và chặn cách còn lại.

Nếu request chỉ chạy HTTP/1.1 khi dùng curl thường:

```bash
curl -s --http1.1 -o /dev/null -w 'http_version=%{http_version}\n' http://localhost:8081/hello
```

Kết quả `http_version=1.1` là bình thường. Browser phổ thông không tự chuyển mọi HTTP thường thành h2c, nên không dùng browser truy cập `http://localhost:8081` rồi kết luận server không hỗ trợ HTTP/2.

**Bảo mật:** không phơi public port h2c trên Internet như một lựa chọn thay HTTPS. Nếu sử dụng h2c upstream, phải bảo vệ đoạn mạng và quyền kết nối.

## 8. Cách kiểm tra nhanh trước và sau khi bật

### 8.1. Ba loại kiểm tra khác nhau

| Câu hỏi | Công cụ | Bằng chứng đúng |
| --- | --- | --- |
| App đã **cấu hình** HTTP/2 chưa? | Xem `server.http2.enabled`, active profile, startup logs | Hỗ trợ có được bật |
| TLS có **thương lượng ALPN h2** không? | `openssl s_client -alpn h2,http/1.1`; `curl -v` | `ALPN protocol: h2` |
| Request **thực sự chạy HTTP/2** không? | `curl -w '%{http_version}'`, browser DevTools Protocol | `2`/`h2` tại hop đang đo |

Không tráo các tiêu chí. Một app khởi động tốt chưa chắc có HTTP/2; certificate hợp lệ chưa chắc ALPN chọn h2; browser dùng h2 đến CDN chưa chắc upstream đến Spring Boot là h2.

### 8.2. Quy trình kiểm tra h2 production

1. Xác định **URL và hop** cần kiểm tra: browser↔edge hay edge↔Spring Boot.
2. Xác định server type và dependency versions; JDK runtime phù hợp.
3. Xác định TLS certificate chain và hostname có hợp lệ trên endpoint công khai.
4. Dùng curl có HTTP/2 để gọi đúng URL, **không dùng `-k`** nếu là production.
5. Quan sát ALPN và `http_version=2`.
6. Thử `--http1.1` để kiểm tra fallback nếu client cũ vẫn cần hoạt động.
7. Kiểm tra nhiều request song song, body lớn và streaming nếu ứng dụng dùng các khả năng đó.
8. Ghi lại protocol version qua log/metrics của proxy **ở đúng hop**, không chỉ tại application.
9. Nếu backend phải chạy h2c, truy cập từ mạng đáng tin tới **backend listener** và kiểm tra độc lập.
10. Sau deploy, theo dõi error rate, TLS handshake failures, HTTP/2 stream resets, p95/p99 latency và proxy upstream errors.

### 8.3. Kiểm tra bằng trình duyệt

Trên Chrome/Edge/Firefox, mở DevTools → Network, bật cột **Protocol** (cách mở cột tùy phiên bản). Khi tải qua HTTPS, request có thể hiện `h2`, `http/1.1` hoặc `h3`. Giá trị đó mô tả **kết nối giữa browser và endpoint mà browser đang truy cập**, thường là proxy/CDN, không mặc định là embedded Spring Boot.

Nếu có service worker, browser cache hoặc prefetch, một số request có thể không tương ứng một network hop mới. Để kiểm thử negotiation, nên gọi `curl` và xem gateway access logs cùng lúc.

### 8.4. Công cụ `nghttp`

`nghttp` (bộ công cụ nghttp2) có thể hiển thị chi tiết HTTP/2 frames/settings:

```bash
nghttp -nv https://localhost:8443/hello
```

Với certificate self-signed, nghttp có thể yêu cầu cấu hình trust hoặc một option test phù hợp phiên bản cài đặt. Không giả định output nghttp tồn tại trên mọi máy; đây là **công cụ bổ sung** khi cần debug stream/frame, không cần để chạy demo.

## 9. Spring Boot SSL bundles: cấu hình production sạch hơn

Spring Boot hỗ trợ **SSL bundles**, gom keystore/truststore hoặc PEM key/cert thành một cấu hình có tên. Sau đó server chọn bundle bằng `server.ssl.bundle`. Ví dụ **fragment** cho server có PKCS#12 keystore, không chạy đồng thời với các property `server.ssl.key-store` trong ví dụ trước:

```properties
spring.ssl.bundle.jks.web.keystore.location=file:/etc/example/tls/web.p12
spring.ssl.bundle.jks.web.keystore.password=${WEB_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.web.keystore.type=PKCS12
spring.ssl.bundle.jks.web.key.alias=web

server.port=8443
server.http2.enabled=true
server.ssl.bundle=web
```

Fragment này giả định tệp `/etc/example/tls/web.p12` do hệ thống triển khai cung cấp và application có quyền đọc. Không phải file sẵn có trong project demo.

**Không trộn** `server.ssl.bundle` với các cấu hình discrete `server.ssl.key-store`, `server.ssl.certificate` và private key options của `server.ssl.*`. Khi dùng bundle, một số cấu hình ciphers/protocols ở `server.ssl.*` được lấy từ options của bundle; nên kiểm tra tài liệu Spring Boot đúng phiên bản thay vì cấu hình trùng rồi dự đoán property nào thắng.

Với PEM certificate/key, Spring Boot cũng hỗ trợ `spring.ssl.bundle.pem.*`, tiện cho secret mount và một số triển khai có cơ chế reload. Nhưng **chỉ cấu hình SSL bundle không bật HTTP/2**; vẫn cần `server.http2.enabled=true` và xác nhận ALPN.

## 10. Giới hạn hiệu năng và các rủi ro vận hành

### 10.1. HTTP/2 multiplexing không đồng nghĩa vô hạn request

Một kết nối HTTP/2 chứa nhiều streams nhưng server vẫn có giới hạn **max concurrent streams, connection count, request header size, body size, timeouts và flow control**. Browser/client cũng có giới hạn. Nếu DB pool chỉ có 10 connections, HTTP/2 không tạo ra 1000 connections DB mới có ích.

HTTP/2 có thể tăng mức đồng thời mà ứng dụng nhận trên một kết nối. Hãy kiểm tra:

- Servlet thread pool, reactive event loop, async task executors;
- database connection pool/HTTP client pools;
- kích thước body và backpressure/streaming;
- timeout, cancellation, disconnect và stream reset;
- tải CPU khi TLS/HPACK/frame processing;
- concurrency limits, max streams, header limits theo web server cụ thể.

Đừng tăng `maxConcurrentStreams` tùy tiện để “tận dụng HTTP/2” mà chưa benchmark.

### 10.2. So sánh trên cùng điều kiện

Khi benchmark HTTP/1.1 và HTTP/2:

1. Dùng cùng phần cứng, JVM, JVM options và workload.
2. Kiểm soát warm-up JIT và connection reuse.
3. Dùng TLS cho cả hai nếu muốn so sánh công bằng trên endpoint HTTPS.
4. Đo p50/p95/p99, RPS, CPU, memory, network, TLS handshakes và errors.
5. Kiểm tra client/load generator **thật sự dùng HTTP/2**. Một flag không xác nhận protocol có thể khiến benchmark vô nghĩa.
6. Thử workload nhiều tài nguyên/requests song song và workload JSON đơn lẻ để thấy trường hợp lợi ích khác nhau.
7. Đo riêng frontend↔proxy và proxy↔backend nếu có gateway.

### 10.3. Nén response và header

`server.compression.enabled=true` là tùy chọn nén response body cho các MIME types/kích thước phù hợp, **độc lập** với HTTP/2. Với ảnh JPEG/PNG hoặc nội dung đã nén, gzip thêm thường không có lợi. HTTP/2 HPACK nén headers nhưng không có nghĩa body JSON được tự gzip.

```properties
server.http2.enabled=true
server.compression.enabled=true
```

Đây là **snippet bổ sung tùy chọn**; cần xác minh `Content-Encoding` và `Vary: Accept-Encoding` phù hợp, đo CPU/latency trước và sau. Không bật nén một cách máy móc cho dữ liệu bí mật nằm sát input do attacker kiểm soát nếu threat model có rủi ro kênh phụ qua độ dài nén.

### 10.4. Bảo mật giao thức

HTTP/2 từng xuất hiện các loại tấn công tài nguyên như flood/reset frames (ví dụ “Rapid Reset”). Các biện pháp thực dụng:

- Cập nhật embedded server/proxy lên patch versions được duy trì.
- Bật rate limiting, connection/stream limits và timeout thích hợp ở gateway/server.
- Theo dõi HTTP/2 resets, frame errors và đột biến request volume.
- Kiểm tra certificate, TLS cipher policy và ALPN; không mở h2c không TLS ra mạng công khai.
- Không dựa vào HTTP/2 như giải pháp chống DDoS hoặc thay thế WAF/authorization.

## 11. Các lỗi phổ biến khi bật HTTP/2

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Đã đặt `server.http2.enabled=true` nhưng curl vẫn là `1.1` | Client không hỗ trợ HTTP2; ALPN fallback; proxy downgrade | `curl -V`, `curl -v`, `openssl -alpn`, kiểm tra đúng hop |
| `curl --http2` báo “not supported” | Build curl không có HTTP2/nghttp2 | Dùng curl có feature HTTP2 hoặc nghttp |
| HTTPS lỗi `SSLHandshakeException` | Certificate/key/ciphers/TLS config không phù hợp | Xác nhận keystore alias/password, handshake và certificate |
| Browser báo certificate untrusted | Dùng self-signed hoặc chain thiếu CA | Local test tạm trust hợp lệ; production dùng CA tin cậy |
| `server.ssl.key-store` không tìm thấy file | Working directory khác, đường dẫn `file:` sai | Kiểm tra file, quyền đọc và cách chạy JAR/container |
| Spring khởi động trên port 8080 HTTP thay vì 8443 HTTPS | Sai active profile hoặc config không được load | Xem `--spring.profiles.active=tls`, log startup và actual listener |
| Curl kết nối 8443 qua `http://` bị lỗi | Sai scheme với TLS listener | Dùng `https://localhost:8443` |
| HTTPS trả HTTP 200 nhưng chưa dùng h2 | Server negotiated HTTP/1.1 | In `http_version` và ALPN; HTTP 200 không đủ |
| Boot 3.5 dùng Jetty nhưng không có h2 | Thiếu HTTP/2/ALPN module | Thêm dependencies Jetty phù hợp Boot version |
| Test h2c bằng browser luôn thấy HTTP/1.1 | Browser không dùng h2c tùy tiện | Dùng `curl --http2-prior-knowledge` hoặc upgrade test |
| `--http2-prior-knowledge` vào HTTPS thất bại ở phiên bản curl mới | ALPN h2-only, server không hỗ trợ h2 | Kiểm tra ALPN; dùng `--http2` rồi đọc protocol |
| Gateway báo h2, Spring backend thấy HTTP/1.1 | Proxy TLS termination/proxy upstream downgrade | Kiểm tra cấu hình upstream protocol, log ở đúng hop |
| HTTP/2 bật nhưng ứng dụng vẫn chậm | DB/service blocking/CPU bottleneck hoặc tải khác | Đo backend bottleneck thay vì chỉ giao thức |
| Browser báo `ERR_HTTP2_PROTOCOL_ERROR` | Lỗi frame, headers, proxy, phiên bản server, TLS hoặc compression | Thu log gateway/server, tái hiện curl verbose, cập nhật patch |
| HTTP/2 bị lỗi khi proxy qua ingress | Ingress không hỗ trợ hoặc cấu hình h2/h2c upstream khác nhau | Kiểm tra route/backend protocol annotations và direct test |
| Chạy nhiều instances cho kết quả khác nhau | Config/profile/server versions không đồng nhất | Kiểm kê deployment và test từng instance |
| Config `server.forward-headers-strategy` rồi nghĩ HTTP/2 đã bật | Forwarded headers không điều khiển ALPN | Bật HTTP2 đúng listener; xác nhận `http_version` |

### Trình tự khắc phục lỗi có thể lặp lại

1. **Xác định endpoint và hop.** Test trực tiếp app hoặc public proxy?
2. **Xác nhận runtime.** Spring Boot version, Java version và server thực tế; không đoán từ dependency có sẵn.
3. **Xác nhận cấu hình.** `server.http2.enabled=true` ở active profile; TLS/keystore khi test h2.
4. **Xác nhận client.** `curl -V` có HTTP2.
5. **Xác nhận TLS.** `openssl s_client -alpn h2,http/1.1`, certificate trust và hostname.
6. **Xác nhận request.** `curl --http2 -w '%{http_version}'`. Nếu HTTP/1.1, xem log handshake.
7. **Nếu h2c**, thử direct prior-knowledge và HTTP/1.1 Upgrade; không dùng browser làm công cụ duy nhất.
8. **Nếu có proxy**, kiểm tra riêng outside/client-facing và inside/backend-facing.
9. **Khi chạy được h2**, thử fallback 1.1, concurrency, streaming, error rate và đo hiệu năng thực.
10. Chỉ can thiệp vào server-specific APIs sau khi config chuẩn và dependencies đã được xác nhận.

## 12. HTTP/2 và khả năng tương thích ứng dụng

### 12.1. Controller và REST API có cần sửa không?

Thông thường **không**. Một handler Spring MVC:

```java
@GetMapping("/orders/{id}")
public OrderDto findOrder(@PathVariable long id) {
    return orderService.findById(id);
}
```

Đây là **snippet minh họa**, chưa phải class độc lập: `OrderDto` và `orderService` là thành phần ứng dụng. HTTP request vẫn mang method/path/headers/body theo semantics tương tự. Transport/controller mapping do server và Spring xử lý.

### 12.2. Những gì vẫn cần kiểm thử

- Filter, reverse proxy và security middleware xử lý header/cookie đúng.
- Long polling, SSE, streaming và WebSocket upgrade có yêu cầu riêng; đừng tự suy luận rằng HTTP/2 thay thế mọi cơ chế upgrade cũ.
- Client/server có xử lý content-length, trailers, header normalization và request buffering đúng.
- HTTP/2 header field names là lowercase ở tầng wire; app **không nên phụ thuộc vào chữ hoa/thường của tên HTTP header**.
- Các `Connection`, `Keep-Alive`, `Upgrade` kiểu connection-specific của HTTP/1.1 không được chuyển nguyên dạng sang HTTP/2 frames; để HTTP stack xử lý.
- gRPC dùng HTTP/2 ở nhiều triển khai; nếu cần gRPC qua gateway, xác định rõ proxy có duy trì HTTP/2 ở upstream hay không.

### 12.3. Khi kết quả đo không tốt hơn

HTTP/2 có thể phát huy hiệu quả với nhiều requests song song, nhưng không tự sửa tình trạng controller xử lý blocking lâu, connection pool thiếu, GC pause hay HTTP2 frame/flow-control misconfiguration. Thêm một tầng reverse proxy/gateway có thể tạo overhead khác, nên phải benchmark theo kiến trúc thực.

**Không bắt client dùng HTTP/2 bằng cách loại bỏ HTTP/1.1 tùy tiện** khi vẫn có clients cũ. Nếu bắt buộc HTTP/2 vì hợp đồng/gRPC, cần tài liệu rõ yêu cầu client, đường truyền và kiểm thử thất bại khi không có h2.

## 13. Câu hỏi tự đánh giá

1. **Bật `server.http2.enabled=true` có chắc browser đã dùng HTTP/2?** Không. Phải kiểm tra ALPN/client/proxy và request thực tế.
2. **Khác biệt cốt lõi giữa h2 và h2c?** H2 dùng TLS/ALPN; h2c là HTTP/2 qua TCP không TLS.
3. **Spring Boot 3.5 có hỗ trợ h2c không?** Có. Tài liệu Boot 3.5 nêu h2c được dùng khi SSL không bật, tùy server hỗ trợ.
4. **JDK 17 có cần ALPN boot patch cũ cho Tomcat h2 không?** Không. ALPN đã có trong nền tảng Java hiện đại; vẫn phải kiểm chứng TLS negotiation.
5. **`curl --http2` trả HTTP 200 có chứng minh h2 không?** Không; curl có thể thương lượng fallback HTTP/1.1. Hãy xem `%{http_version}`.
6. **HTTP/2 trên browser ↔ CDN có chứng minh backend Spring Boot dùng h2 không?** Không; proxy có thể nối về backend bằng HTTP/1.1.
7. **Jetty có cần thêm module HTTP/2 ở Spring Boot 3.5 không?** Có theo hướng dẫn Boot; h2 TLS còn cần ALPN provider tương ứng.
8. **Reactor Netty có hỗ trợ h2c không?** Có trong stack Boot 3.5 theo tài liệu, nếu cấu hình server/runtime phù hợp.
9. **TLS 1.3 có bắt buộc duy nhất cho h2 không?** Không; TLS 1.2 phù hợp vẫn có thể được dùng.
10. **HTTP/2 có tự nén JSON không?** Không. HTTP/2 nén headers với HPACK; body compression là cấu hình riêng.
11. **Khi dùng reverse proxy TLS termination, có nhất thiết bật SSL trên backend không?** Không, tùy kiến trúc. Nhưng đoạn proxy↔backend phải được bảo vệ theo threat model.
12. **Tại sao h2c không phù hợp cho public Internet?** Không có TLS bảo vệ dữ liệu và xác thực ở transport; dùng ở mạng tin cậy khi thật sự cần.
13. **Vì sao phải kiểm tra HTTP/1.1 fallback?** Nhiều client còn sử dụng 1.1; bật h2 không tự đồng nghĩa loại 1.1.
14. **Có cần viết controller mới để HTTP/2 hoạt động không?** Không. HTTP/2 do server/connector thương lượng; controller xử lý HTTP semantics như thường.
15. **Thấy `servletProtocol=HTTP/1.1` trên backend trong khi DevTools hiện h2 có chắc lỗi cấu hình?** Không. Đó có thể là kết quả edge h2 → backend h1 được thiết kế chủ đích.

## 14. Checklist triển khai production

- [ ] Xác nhận chính xác Boot version, JDK và embedded server tại runtime.
- [ ] Chọn hop cần HTTP/2: client↔edge, edge↔backend hay trực tiếp tới Spring Boot.
- [ ] Bật `server.http2.enabled=true` đúng active profile/config source.
- [ ] Với h2, cấu hình TLS certificate đúng SAN/chain, TLS/ciphers phù hợp và ALPN.
- [ ] Không đóng gói/commit private key; sử dụng SSL bundle/secret phù hợp.
- [ ] Nếu dùng Jetty, thêm đúng HTTP/2 server + ALPN modules theo version.
- [ ] Nếu dùng h2c, chỉ dùng trong phân đoạn mạng được bảo vệ và kiểm thử trực tiếp.
- [ ] Kiểm tra `curl -V` có HTTP2; không dùng một build curl thiếu support làm bằng chứng server hỏng.
- [ ] Quan sát ALPN và `curl -w '%{http_version}'` cho URL/hop cần đo.
- [ ] Kiểm tra HTTP/1.1 fallback nếu hệ thống có client cũ.
- [ ] Test controller/filter/security, streaming, body sizes và proxy compatibility.
- [ ] Đo p95/p99 latency, throughput, stream resets và tải TLS/CPU; đừng suy diễn lợi ích từ một request đơn.
- [ ] Cập nhật bản vá server/proxy để giảm rủi ro HTTP/2 flood/DoS.
- [ ] Kiểm tra log/metrics riêng của gateway và backend nếu TLS termination khác nhau.
- [ ] Lập kế hoạch certificate renewal, health check và rollback nếu deployment lỗi handshake.
- [ ] Đánh giá context root, forwarded headers và SNI nếu nhiều virtual hosts/certificates.

## 15. Tài liệu chính thức

- Spring Boot 3.5 — [Embedded Web Servers: Configure HTTP/2](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html) — tài liệu trọng tâm cho `server.http2.enabled`, h2/h2c và ma trận Tomcat/Jetty/Reactor Netty/Undertow.
- Spring Boot — [SSL Bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html) — JKS/PKCS12, PEM, quản lý trust/key material.
- Spring Boot 3.5 — [Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html) — các property `server.http2.*` và `server.ssl.*`.
- Apache Tomcat 10.1 — [HTTP Connector / HTTP/2 support](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html) — h2 TLS, h2c Upgrade và prior knowledge.
- Apache Tomcat 10.1 — [HTTP/2 Upgrade Protocol](https://tomcat.apache.org/tomcat-10.1-doc/config/http2.html) — các giới hạn và cấu hình riêng.
- curl — [HTTP/2 command-line options](https://curl.se/docs/manpage.html) — `--http2`, `--http2-prior-knowledge` và yêu cầu curl hỗ trợ HTTP2.
- Everything curl — [HTTP/2 support](https://everything.curl.dev/http/versions/http2.html) — phân biệt TLS negotiation và HTTP Upgrade.
- IETF — [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113) — framing, h2/h2c, ALPN, connection preface.
- IETF — [RFC 7301: TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301) — ALPN negotiation.

**Tổng kết:** Trong Spring Boot 3.5, bước bật HTTP/2 bắt đầu bằng `server.http2.enabled=true`, nhưng **`h2` cần TLS + ALPN**, còn **`h2c` dành cho TCP không TLS**. Với Java 17 và Tomcat nhúng, có thể chạy h2/h2c theo cấu hình mẫu mà không cần thư viện native bắt buộc. Hãy **đo chính xác giao thức được thương lượng** bằng curl/OpenSSL ở **đúng hop**, kiểm tra dependencies của server, bảo vệ TLS/private key và đánh giá hiệu năng trên tải thực trước khi kết luận triển khai đã thành công.