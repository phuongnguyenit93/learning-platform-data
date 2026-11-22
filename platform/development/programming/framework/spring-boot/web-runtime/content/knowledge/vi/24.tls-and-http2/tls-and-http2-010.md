# Quản lý bí mật, thời hạn và khả năng nạp lại chứng thư theo máy chủ

> **Module:** Spring Boot - web-runtime · **Nhóm:** TLS và HTTP/2. Bài học tập trung vào vòng đời **chứng thư TLS (certificate)** và **khóa bí mật (private key)** khi Spring Boot chạy với Tomcat, Reactor Netty, Jetty hoặc đứng sau reverse proxy; giải thích thời hạn, tự động gia hạn, nạp lại (reload/rotation), khả năng tương thích từng máy chủ và quy trình kiểm chứng từ client. Ví dụ dùng **Spring Boot 4.1.2**, **Java 17+**, Maven, OpenSSL và SSL bundles. Các hướng dẫn liên quan đến production cần điều chỉnh theo kiến trúc và chính sách bảo mật thực tế.

## Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt **private key, certificate, certificate chain, truststore và mật khẩu keystore**; biết thứ gì là bí mật và thứ gì thường có thể công khai.
2. Thiết kế cách cung cấp chứng thư và khóa qua **secret manager/volume được quản trị**, không commit private key vào Git, không lưu cố định trong image/JAR hoặc in ra log.
3. Đọc `notBefore`/`notAfter`, SAN, issuer, certificate chain và xác minh tên miền, ngày hết hạn, key match, quyền sử dụng khóa.
4. Cấu hình `spring.ssl.bundle.pem.*` hoặc `spring.ssl.bundle.jks.*` và liên kết bundle vào `server.ssl.bundle`; hiểu điểm khác so với `server.ssl.key-store` hoặc các thuộc tính TLS rời.
5. Nắm bảng hỗ trợ **reload-on-update**: Spring Boot tài liệu hóa Tomcat và Reactor Netty; không mặc định Jetty/Undertow hoặc mọi SSL consumer có cùng năng lực hot reload.
6. Xây demo HTTPS/HTTP/2, kiểm thử certificate **trên đường truyền** và thay chứng thư mà không restart ở server tương thích.
7. Lập runbook giám sát hạn chứng thư, gia hạn trước hạn, rollout nhiều instance, cảnh báo và rollback an toàn.

## 1. Những đối tượng nằm trong một kết nối TLS

Với client HTTPS, máy chủ thường trình ra **leaf certificate** để chứng minh danh tính hostname. Chứng thư chứa **public key**, danh tính chứng thư, ngày hiệu lực, issuer và chữ ký của CA; nó không chứa private key. Server dùng **private key** tương ứng trong bắt tay TLS để chứng minh quyền sở hữu khóa.

~~~text
HTTPS client / browser
   |
   | TCP connect, TLS ClientHello
   | SNI = api.example.com, ALPN = h2,http/1.1
   v
TLS terminating endpoint
   |
   +-- certificate cho api.example.com
   +-- intermediate certificate chain khi cần
   +-- private key tương ứng với leaf certificate
   |
   +-- TLS handshake / verify / negotiate ALPN
   v
HTTP/2 (h2) hoặc HTTP/1.1
   |
   v
Spring controller, API, static resources
~~~

**Lưu ý:** ALPN quyết định giao thức HTTP được thương lượng sau TLS; thay/chỉnh chứng thư TLS **không tự bật HTTP/2**, và bật HTTP/2 **không tự gia hạn chứng thư**.

| Đối tượng | Tính chất | Quản lý thế nào |
| --- | --- | --- |
| **Private key** (ví dụ `privkey.pem`) | **Bí mật quan trọng nhất**; sở hữu khóa cho phép kẻ xấu mạo danh nếu có cert tương ứng | Secret manager/KMS/HSM hoặc volume riêng; quyền đọc tối thiểu; không log, không commit |
| Leaf certificate (ví dụ `cert.pem`) | Public certificate chứa SAN, issuer, notBefore/notAfter | Công khai được; vẫn cần tính đúng chain và vòng đời |
| Certificate chain (ví dụ `fullchain.pem`) | Leaf + intermediates thường cần gửi cho client | Đảm bảo thứ tự và chain hợp lệ; không gửi private key trong chain |
| CA root/trust anchor | Dùng để kiểm chứng danh tính bên kia | Cấu hình truststore/OS/browser trust; không nhầm với keystore private key |
| Keystore JKS/PKCS12 | Container có thể chứa private key + cert chain, có mật khẩu | File và password đều cần được bảo vệ, phân quyền và rotation |
| Truststore | Chứa các chứng thư/CA mà phía kết nối tin cậy | Không phải nơi chứa private key của web server; quản lý tin cậy có kiểm soát |
| TLS certificate expiry | Thời điểm chứng thư hết hiệu lực; tính theo UTC | Giám sát từ **endpoint đang được phục vụ**, không chỉ file trên ổ đĩa |

Một tổ hợp TLS hợp lệ cần **đúng private key, leaf cert, chuỗi CA, tên miền SAN và thời gian hiệu lực**. Browser tin domain dựa trên chuỗi CA/trust và name checks. Không lấy `CN` làm cơ chế tên miền duy nhất; với chứng thư TLS hiện đại, **Subject Alternative Name (SAN)** là thành phần trọng yếu.

### Khái niệm hết hạn

- `notBefore`: chứng thư chưa có hiệu lực trước mốc này.
- `notAfter`: hết hiệu lực sau mốc này; kiểm tra bằng UTC/đồng hồ chuẩn.
- `subject`/`SAN`: hostname, IP được chứng thư đại diện.
- `issuer`: đơn vị ký; phải tạo được chain tới trust anchor thích hợp.
- `keyUsage` và `extendedKeyUsage`: mục đích dùng khóa/chứng thư, thường có `serverAuth` đối với TLS server certificate.

Chứng thư hết hạn gây lỗi xác minh TLS ngay cả khi app vẫn sống và health endpoint bên trong trả 200. Hạn chứng thư **không liên quan trực tiếp** đến TTL của DNS record, hết hạn session, cookie hoặc thời gian sống của private key.

## 2. Xác định nơi TLS thực sự kết thúc

Trước khi chỉnh Spring Boot, cần biết TLS được **terminate** ở đâu:

~~~text
A. TLS end-to-end tại ứng dụng:
Browser HTTPS -> Tomcat/Netty HTTPS -> application

B. TLS terminate tại gateway/CDN:
Browser HTTPS -> CDN/Nginx/Ingress (certificate public)
              -> HTTP hoặc HTTPS nội bộ -> Spring Boot

C. Re-encryption/mTLS nội bộ:
Browser HTTPS -> ingress TLS -> HTTPS backend Spring Boot
              -> database/client HTTPS theo trust và secret riêng
~~~

| Kiến trúc | Chứng thư nào cần rotate? | Ai nạp lại? |
| --- | --- | --- |
| TLS trực tiếp ở Tomcat | Cert/key do embedded Tomcat phục vụ | Spring Boot SSL bundle → Tomcat connector khi tương thích |
| TLS trực tiếp ở Reactor Netty | Cert/key do embedded Netty phục vụ | Spring Boot SSL bundle → Netty khi tương thích |
| Public TLS ở Nginx/Envoy/CDN/Ingress | Cert/key của gateway/CDN, **không nhất thiết nằm trong JVM** | Controller của ingress, CDN hoặc proxy theo cách riêng |
| Ingress HTTPS rồi HTTPS backend | Có **hai** TLS hops và có thể hai cert khác nhau | Tách rotation/expiry monitoring cho từng hop |
| HTTP nội bộ h2c sau TLS termination | Chứng thư dùng ở TLS edge, backend chạy h2c nếu được phép | Không có backend TLS cert để Spring Boot hot reload trên hop đó |
| Outbound `WebClient`/JDBC TLS/mTLS | Client identity/trust material có thể khác inbound cert | Tùy client/connector có hỗ trợ reload bundle hay không |

**Không sửa `server.ssl.*` để “gia hạn cert” nếu browser thực sự thấy cert của CDN.** Kiểm certificate bằng client từ ngoài mạng công khai và có SNI đúng, xác định frontend và backend trước.

HTTP/2 với TLS thường được thương lượng qua ALPN token `h2`. Spring Boot hỗ trợ `server.http2.enabled=true` cho server tương thích; có thể dùng **h2** khi TLS bật, hoặc **h2c** (cleartext HTTP/2) trên hop không có SSL nếu môi trường cho phép. Không truyền h2c trên internet chỉ để tránh cấu hình TLS.

## 3. Quản lý bí mật: private key không được sống trong mã nguồn

### Thông tin nào là bí mật?

- Private key PEM/PKCS12/JKS có private key, token tới secret manager, keystore password, client-auth private keys: **bí mật**.
- Public certificate PEM/CA trust chain: có thể công khai theo thiết kế PKI; tuy nhiên đường dẫn, metadata và hạ tầng nội bộ có thể vẫn cần được quản lý.
- Keystore password không thay được quyền filesystem: dù file PKCS12 có password, kẻ tấn công có thể lấy file và tiến hành offline attack. Ngược lại, private key PEM chưa mã hóa càng cần ACL/volume nghiêm ngặt.

**Không làm:**

~~~properties
# Không dùng trong cấu hình production được commit:
server.ssl.key-store-password=my-real-production-password
spring.ssl.bundle.jks.web.keystore.password=super-secret
~~~

Không copy private key vào `src/main/resources/` rồi commit hoặc đóng chung vào executable JAR/Docker image. Không đẩy certificate private key vào ticket, log, email, crash dump hoặc issue tracker.

### Các cách cấp phát được khuyến nghị

1. **Secret manager/KMS/Vault**: ứng dụng hoặc orchestrator có định danh workload; secret manager cấp quyền đọc đúng secret; rotation và audit tập trung.
2. **Mount file từ volume bí mật**: ví dụ Kubernetes Secret/CSI volume, Docker secrets hoặc file do agent bảo mật tạo; Spring Boot đọc qua `file:...`. Phân quyền root/owner và tất cả ancestor phù hợp.
3. **Keystore PKCS12 được quản lý**: nếu tổ chức chuẩn hóa PKCS12/JKS; password lấy từ kênh không hardcode.
4. **TLS termination tại edge**: chứng thư public internet do Ingress/CDN quản lý; JVM có thể chỉ phục vụ HTTP nội bộ hoặc TLS riêng khi cần.

**Chọn cách có thể luân chuyển khóa mà không cần build lại image.** Tệp nằm trên classpath hoặc JAR có thể thuận tiện cho dev, nhưng không phải lựa chọn tốt để hot reload cert production. Với Spring Boot PEM reload, dùng **đường dẫn file thật** và watcher; không giả định classpath resource trong JAR có thể sửa trực tiếp lúc runtime.

### Ví dụ mount bí mật

~~~text
/run/secrets/webserver/
  fullchain.pem   # leaf + intermediate certs
  privkey.pem     # private key, chỉ account dịch vụ đọc
~~~

Ví dụ property (đường dẫn riêng theo môi trường):

~~~properties
server.port=8443
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:/run/secrets/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/run/secrets/webserver/privkey.pem
spring.ssl.bundle.pem.webserver.reload-on-update=true
~~~

Đảm bảo container/process Spring Boot đọc được file sau khi volume được mount, nhưng không để tài khoản không tin cậy **ghi** vào thư mục hoặc thay symlink. Không mở quyền file thành 777 để chữa lỗi permission.

### Environment variables có phải an toàn tuyệt đối?

Không. Đưa password vào environment variables tránh hardcode trong repository nhưng môi trường của tiến trình có thể bị lộ qua crash logs, /proc, diagnostics hoặc các công cụ quản trị khi quyền không chặt. Nên lựa chọn secret delivery phù hợp threat model; che/loại bí mật khỏi `/actuator/env` và logging. Không ghi toàn bộ Spring `Environment` hay config properties ra log khi debug TLS.

Spring property placeholder có thể dùng cho keystore password:

~~~properties
spring.ssl.bundle.jks.web.keystore.password=${WEB_KEYSTORE_PASSWORD}
~~~

Đây là **ví dụ cú pháp**, không có mật khẩu thực và vẫn yêu cầu secret delivery đáng tin.

## 4. SSL bundles trong Spring Boot

Spring Boot có abstraction `SslBundle` được khai báo bằng `spring.ssl.bundle.pem.*` hoặc `spring.ssl.bundle.jks.*`. Bundle gộp key/trust material và các thiết lập TLS; consumer như embedded web server có thể tham chiếu theo tên.

### 4.1. PEM certificate và private key

~~~properties
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/run/secrets/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/run/secrets/webserver/privkey.pem
server.ssl.bundle=webserver
server.port=8443
~~~

`webserver` là **tên bundle do bạn đặt**. `keystore.certificate` dùng chuỗi chứng thư server cần trình; `keystore.private-key` phải tương ứng leaf certificate. Khi dùng Let's Encrypt, tài liệu Boot minh họa `fullchain.pem` và `privkey.pem`.

### 4.2. JKS/PKCS12 với password từ secret manager

~~~properties
spring.ssl.bundle.jks.webserver.keystore.location=file:/run/secrets/webserver/server.p12
spring.ssl.bundle.jks.webserver.keystore.password=${WEB_KEYSTORE_PASSWORD}
spring.ssl.bundle.jks.webserver.keystore.type=PKCS12
spring.ssl.bundle.jks.webserver.key.alias=server

server.port=8443
server.ssl.bundle=webserver
~~~

Alias phải trỏ tới entry private key/cert chain thực trong keystore. Trường hợp password key khác keystore có thể cần thuộc tính phù hợp hoặc quy trình tạo keystore. **Không dùng cùng lúc** `server.ssl.bundle` với các cấu hình private key/keystore rời dưới `server.ssl`: Boot ghi rõ các hướng cấu hình này không được kết hợp. Khi dùng bundle, cấu hình protocol/ciphers trong bundle options nếu cần thay vì trông chờ `server.ssl.enabled-protocols` ghi đè.

### 4.3. Key store khác trust store

- Inbound HTTPS **server** cần keypair + chứng thư; đó là **server identity**.
- Khi bật **client certificate authentication (mTLS)**, server còn cần trust material để xác minh cert của client; cần `truststore`/CA policy và `server.ssl.client-auth` thích hợp.
- Khi Spring Boot gọi **outbound HTTPS** bằng WebClient/RestClient, phía client cần trust CA của server; nếu mutual TLS, nó cũng cần client cert/private key riêng.

Không lấy PEM server public certificate làm truststore toàn cầu cho mọi client rồi tắt hostname verification. Không dùng `trust-all` hoặc `NoopHostnameVerifier` như giải pháp lỗi chứng thư. Mục tiêu là chain/SAN/trust policy đúng, không bỏ kiểm tra TLS.

## 5. Nạp lại chứng thư: reload-on-update không phải gia hạn chứng thư

Có **ba thao tác khác nhau**:

1. **Cấp mới (issuance):** CA/ACME/internal PKI ký chứng thư mới.
2. **Triển khai (deployment):** đặt file cert/key/chain mới vào đường dẫn được server đọc.
3. **Reload (activation):** TLS server bắt đầu sử dụng key/certificate mới cho các **handshake mới**.

Spring Boot **không tự đăng ký/gia hạn** chứng thư Let's Encrypt. Công cụ như Certbot, cert-manager, Vault PKI hoặc hệ thống CA doanh nghiệp làm bước 1 và thường hỗ trợ bước 2. Spring Boot SSL bundle reload hỗ trợ bước 3 khi consumer phù hợp.

### Khả năng thực tế theo máy chủ

| Vị trí/máy chủ | Spring Boot 4.1.x | Reload SSL bundle theo tài liệu | Ghi chú |
| --- | --- | --- | --- |
| **Embedded Tomcat** (Spring MVC) | Có | **Có** | Spring Boot bundle watcher thông báo Tomcat để refresh chứng thư trên SSL connectors |
| **Embedded Reactor Netty** (WebFlux) | Có | **Có** | Consumer Netty tương thích reloadable SSL bundles |
| **Embedded Jetty** | Có | **Không được liệt kê** là consumer hỗ trợ reload theo tài liệu Boot hiện hành | Không tự hứa hot reload; thử thực tế hoặc dùng restart/rolling deployment |
| **Undertow embedded** | **Đã bỏ hỗ trợ trong Spring Boot 4** do yêu cầu Servlet 6.1 | Không áp dụng cho Boot 4 | Spring Boot 3 từng có Undertow; đừng dùng bản cũ để suy ra khả năng Boot 4 |
| **Nginx/Envoy/Ingress/CDN** | Ngoài JVM | Không do `spring.ssl.bundle.*` điều khiển | Dùng cơ chế reload/rolling của chính TLS terminator |
| **Embedded server riêng/custom SSL consumer** | Phụ thuộc tích hợp | Không mặc định | Consumer phải hỗ trợ reload; `SslBundles` có bundle không đồng nghĩa mỗi client tự cập nhật SSLContext |
| **Load balancer managed TLS** | Ngoài ứng dụng | Không do Spring Boot quyết định | Cơ chế rotation thuộc cloud LB/certificate manager |

**Quan trọng:** “Jetty không được liệt kê” không phải khẳng định Jetty không bao giờ có cơ chế refresh riêng. Nó chỉ có nghĩa **không bảo đảm chức năng hot reload chung của Spring Boot SSL bundle** khi chưa kiểm cụ thể version, connector và integration. Với Jetty dùng trong production, chọn kế hoạch rolling restart hoặc cơ chế riêng đã được kiểm thử.

### Bật PEM reload-on-update

~~~properties
spring.ssl.bundle.pem.webserver.reload-on-update=true
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/run/secrets/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/run/secrets/webserver/privkey.pem
server.ssl.bundle=webserver
~~~

Tài liệu Boot mô tả một **file watcher** theo dõi thay đổi của các file đã cấu hình; khi watcher phát hiện thay đổi và qua quiet period, bundle được cập nhật, sau đó consumer tương thích như Tomcat/Netty nhận bản mới.

Có thể điều chỉnh khoảng chờ watcher:

~~~properties
spring.ssl.bundle.watch.file.quiet-period=2s
~~~

Chờ một khoảng yên lặng giảm nguy cơ reload đúng lúc bên cấp chứng thư còn ghi file; **không** biến việc thay cặp cert/key thành giao dịch nguyên tử. Một cert mới và một key cũ không khớp có thể làm reload thất bại. Vì vậy quá trình triển khai cert và key phải được thiết kế nhất quán.

### Với Certbot / Let's Encrypt

Ví dụ chính thức theo path phổ biến:

~~~properties
spring.ssl.bundle.pem.webserver.reload-on-update=true
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/letsencrypt/live/example.com/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/letsencrypt/live/example.com/privkey.pem
server.ssl.bundle=webserver
server.port=8443
~~~

Đường dẫn `/etc/letsencrypt/live/...` thường là symlink sang `archive/...`. Tài liệu Boot cho biết file watcher **theo symlink** để xử lý những update mục tiêu đó. Dù vậy, quyền truy cập symlink target, watch event của filesystem/container, timing cập nhật hai file và việc reload vào server đang chạy **vẫn phải được test**.

Dùng `certbot renew --dry-run` để kiểm cơ chế ACME của môi trường *nếu bạn đã cấu hình Certbot và có đủ quyền/domain phù hợp*. Đây không phải lệnh tạo được chứng thư thật trên mọi laptop. Không thực hiện yêu cầu ACME thật trong demo local.

### Tránh lầm tưởng về JKS hot reload

Spring Boot hỗ trợ JKS/PKCS12 bundle để cấu hình TLS. Tuy nhiên phần tài liệu **reload-on-update** cung cấp ví dụ **PEM file bundle** và nêu consumer tương thích Tomcat/Netty. Đừng suy ra rằng mọi kiểu keystore hoặc mọi `server.ssl.*` legacy config đều tự reload khi file đổi. Nếu hệ thống dùng PKCS12/JKS và cần zero-downtime rotation, hãy xác minh rõ hỗ trợ của **đúng phiên bản, loại bundle và embedded server**; nếu chưa có bằng chứng, dùng rolling restart.

### Mối quan hệ giữa connection cũ và connection mới

Một TLS certificate được trình trong **handshake**. Khi reload, những kết nối đã thiết lập có thể tiếp tục hoạt động với trạng thái TLS trước đó cho đến khi đóng; điều quan trọng là **một kết nối mới sau reload** nhìn thấy certificate mới. HTTP/2 còn có thể giữ một kết nối rất lâu và multiplex nhiều requests. Vì vậy không kiểm rotation chỉ bằng một tab browser đang giữ connection cũ.

TLS session resumption, keep-alive, reverse proxy pool, HTTP/2 connection reuse có thể làm việc quan sát phức tạp hơn. Phải **mở kết nối mới**, dùng SNI chính xác, và nếu cần buộc client không reuse session để kiểm chứng được leaf cert của server.

## 6. HTTP/2 và TLS: tác động của chứng thư đến máy chủ

Spring Boot có:

~~~properties
server.http2.enabled=true
~~~

Khi SSL được bật và server hỗ trợ, client có thể thương lượng HTTP/2 qua TLS/ALPN token `h2`; nếu không, tùy client/server có thể dùng HTTP/1.1. Khi SSL tắt, một số embedded server hỗ trợ `h2c` ở mạng nội bộ, nhưng **h2c không mã hóa**.

| Máy chủ | HTTP/2 theo tài liệu Boot 4.x | TLS/rotation cần lưu ý |
| --- | --- | --- |
| Tomcat 11.x | Hỗ trợ `h2` và `h2c` | Dùng TLS bundle để bật HTTPS; bundle reload được tài liệu hóa |
| Reactor Netty | Hỗ trợ `h2` và `h2c` | Reload SSL bundle được tài liệu hóa; bảo đảm client có ALPN support |
| Jetty | HTTP/2 cần dependency bổ sung theo tài liệu (và ALPN phù hợp) | Không suy ra hot reload bundle; test đúng cấu hình |
| Reverse proxy edge | Có thể thương lượng h2 ở phía public, HTTP/1.1 hoặc h2c ở backend | Cert public phải được quản lý tại edge |

**TLS version khác HTTP version.** TLS 1.3 không tự nghĩa là HTTP/2, và HTTP/2 over TLS vẫn cần certificate chain hợp lệ. Một cert hết hạn chặn xác thực HTTPS trước khi request HTTP/2 có thể được gửi an toàn.

Nếu TLS terminate tại CDN mà backend Spring Boot là HTTP/1.1, browser vẫn có thể đang dùng HTTP/2 tới CDN. Để xác định giao thức trên **mỗi hop**, đo cả phía client→edge và edge→backend.

## 7. Dự án thực hành: Spring Boot 4.1.2 HTTPS/HTTP/2 có PEM hot reload

Ví dụ cố ý nhỏ để tập trung vào TLS: Tomcat mặc định của Spring MVC dùng file PEM tại thư mục local được cấu hình từ resource `file:` và có `reload-on-update=true`. Không đặt key trong `src/main/resources/` hoặc Git; ví dụ chạy với certificate tự ký **chỉ để học**.

**Yêu cầu:** JDK 17+, Maven tương thích Spring Boot 4, OpenSSL CLI trên macOS/Linux/WSL/Git Bash. Trên Windows, có thể dùng PowerShell và OpenSSL binary phù hợp; lệnh Bash dùng dấu `\` chỉ là cú pháp tiếp dòng của shell POSIX.

### 7.1. Cấu trúc

~~~text
tls-rotation-demo/
  pom.xml
  .gitignore
  tls/                         # tạo lúc chạy; không commit
    server.crt                 # public cert demo
    server.key                 # private key demo
  src/main/java/com/example/tlsdemo/
    TlsDemoApplication.java
    PingController.java
  src/main/resources/
    application.properties
~~~

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tls-rotation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

`spring-boot-starter-webmvc` là starter MVC của Boot 4.x; Tomcat là embedded server mặc định khi không thay dependency. Nếu chuyển demo sang WebFlux/Reactor Netty, dùng `spring-boot-starter-webflux` và handler reactive phù hợp; cùng SSL bundle PEM property có thể được áp dụng cho Netty, nhưng không lấy servlet API để chạy trên WebFlux.

### 7.3. TlsDemoApplication.java

~~~java
package com.example.tlsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TlsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TlsDemoApplication.class, args);
    }
}
~~~

### 7.4. PingController.java

~~~java
package com.example.tlsdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }
}
~~~

Endpoint không biết key/cert; TLS xảy ra **trước** khi HTTP request được controller xử lý.

### 7.5. application.properties

~~~properties
server.port=8443
server.http2.enabled=true
server.ssl.bundle=webserver

spring.ssl.bundle.pem.webserver.keystore.certificate=file:./tls/server.crt
spring.ssl.bundle.pem.webserver.keystore.private-key=file:./tls/server.key
spring.ssl.bundle.pem.webserver.reload-on-update=true
spring.ssl.bundle.watch.file.quiet-period=2s
~~~

- `file:./tls/server.crt` và `file:./tls/server.key` là file paths tương đối với **working directory** của process. Trong production nên dùng đường dẫn tuyệt đối tới secret mount.
- `server.ssl.bundle=webserver` nối tên bundle đã khai báo vào embedded server; không khai đồng thời `server.ssl.key-store` hoặc `server.ssl.certificate` nữa.
- `server.http2.enabled=true` yêu cầu hỗ trợ HTTP/2 từ embedded server và client; sử dụng ALPN khi TLS.
- `quiet-period=2s` chỉ ảnh hưởng file watcher; không thay thế kiểm tra cặp cert/key nhất quán và không tự động xin/gia hạn chứng thư.

### 7.6. .gitignore

~~~gitignore
/tls/
/target/
~~~

Đừng hiểu `.gitignore` là bảo mật hoàn chỉnh: nó chỉ giúp Git không tự theo dõi file chưa được track. Nếu khóa từng bị commit, phải **revoke/rotate key thực**, thu hồi secret khỏi hệ thống lộ và xử lý history theo quy trình. Đừng dùng private key demo cho server có thể truy cập qua internet.

### 7.7. Tạo chứng thư self-signed cho localhost

Trong thư mục project, với OpenSSL có hỗ trợ `-addext`:

~~~bash
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/server.key \
  -out tls/server.crt \
  -days 7 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

# Giảm quyền đọc private key (POSIX); vẫn cần ACL/ownership đúng.
chmod 600 tls/server.key

# Kiểm thông tin public cert, không in private key.
openssl x509 -in tls/server.crt -noout \
  -subject -issuer -dates -serial -ext subjectAltName
~~~

Lệnh tạo RSA private key không mã hóa **chỉ để demo local**, vì server cần đọc tự động. Trong production, ưu tiên CA/ACME trusted, secret manager hoặc HSM khi phù hợp và nguyên tắc quyền tối thiểu. Không dùng tự ký trên public site. `-days 7` là tuổi sống ngắn để dễ học, không phải khuyến cáo thời hạn cert production.

Chứng thư tự ký chưa thuộc truststore của browser/OS; vì vậy request HTTPS bình thường có thể bị báo lỗi “unknown authority”. **Không giải quyết bằng cách tắt xác minh certificate trong ứng dụng thật.**

### 7.8. Chạy Spring Boot

~~~bash
mvn spring-boot:run
~~~

Khi chạy từ thư mục gốc, Boot đọc hai file trong `tls/`, tạo HTTPS listener trên port 8443. Một số hệ thống có thể thiếu native ALPN/h2 support ở client; với Tomcat/JDK 17, server hỗ trợ HTTP/2 theo tài liệu Boot.

Gọi với certificate self-signed của demo đã biết trước:

~~~bash
curl --cacert tls/server.crt -i https://localhost:8443/ping
~~~

Response thành công điển hình:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"status":"ok"}
~~~

Đây chỉ là **minh họa cấu trúc**; thực tế status line có thể là `HTTP/2 200` nếu curl thương lượng h2, thứ tự headers và content length khác. Dùng `--cacert` để trust **đúng file cert demo**, tránh `-k` khi không cần. Trên máy khác, không chép tràn lan private key để test; chỉ dùng public cert/CA root phù hợp.

Để thử HTTP/2 (phụ thuộc bản curl có HTTP/2):

~~~bash
curl --http2 --cacert tls/server.crt -i https://localhost:8443/ping
curl -V
~~~

Quan sát protocol trên status/verbose output. HTTP/2 có thể không bật trên một hop dù HTTPS hoạt động. Nếu kết nối qua load balancer, cần phân biệt protocol giữa browser→edge và edge→app.

### 7.9. Xem chứng thư thật mà server đang trình

Lệnh sau kiểm tra handshake trực tiếp với listener; **nên chạy trên kết nối mới**:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -alpn h2 \
  -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -serial -subject -dates -fingerprint -sha256
~~~

- `-servername localhost` gửi **SNI**. Khi một server host nhiều domain, thiếu SNI có thể thấy default certificate thay vì cert của tên bạn đang kiểm.
- `-connect localhost:8443` chỉ đo **listener local**. Nếu public traffic đi qua CDN, phải kiểm public hostname ở port 443 thay vì chỉ backend.
- `-fingerprint -sha256` và serial là dấu để so sánh trước/sau rotation; không cần in private key.
- `-alpn h2` gửi đề xuất HTTP/2; để xem kết quả ALPN, quan sát output verbose của `s_client` (không bị lọc qua `openssl x509`).

Trên môi trường production, kiểm tra cả chứng thư và chain:

~~~bash
openssl s_client -connect api.example.com:443 \
  -servername api.example.com \
  -verify_return_error -showcerts </dev/null
~~~

Không lấy kết quả `Verify return code: 0` làm bằng chứng duy nhất nếu client truststore, SNI hoặc hostname checking chưa đúng. Dùng HTTP client chuẩn xác minh hostname/CA như `curl -v https://api.example.com/...` mà **không** bật `-k`. `openssl s_client` có thể thêm `-verify_hostname api.example.com` trên các phiên bản hỗ trợ để kiểm SAN.

### 7.10. Kiểm thử reload với cert mới nhưng GIỮ cùng key

Để cô lập cơ chế watcher, tạo **certificate mới ký bằng cùng private key demo**, từ đó chỉ cần thay đổi một file. **Đây là kiểm thử reload certificate, không phải private-key rotation.**

~~~bash
openssl req -new -x509 -sha256 \
  -key tls/server.key \
  -out tls/server-next.crt \
  -days 8 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

openssl x509 -in tls/server-next.crt -noout -serial -dates

# Với cùng filesystem POSIX, thay tên file ở đích.
# Chỉ thực hiện trong demo local, không thao tác lên cert production.
mv -f tls/server-next.crt tls/server.crt
~~~

Khi watcher nhận thay đổi, bundle đọc lại cert và consumer Tomcat tương thích áp dụng cho những handshake mới. Sau một khoảng ngắn đủ cho watcher/quiet period, chạy lại lệnh xem `-serial`/`-fingerprint` tại port 8443; **bản mới phải khác** bản trước nếu reload thành công.

Vì chứng thư demo tự ký đã được thay, public cert cũ mà `curl --cacert tls/server.crt` từng trust sẽ không còn đúng nếu client vẫn dùng bản cũ. Client dùng file chứng thư mới/CA thích hợp để xác minh, không tự xem cert mới là trusted chỉ vì cùng private key.

**Trên Windows:** thao tác thay file/rename có semantics khác; nên dùng OpenSSL/PowerShell thích hợp và kiểm quyền. Không copy command `mv -f` POSIX vào script production Windows mà chưa kiểm tính atomic và file watcher.

**Nếu reload không xảy ra:** kiểm file watcher logs, quyền đọc file, đường dẫn `file:`, quiet period, version Boot/server và đối chiếu cert trực tiếp từ handshake. Đừng kết luận chỉ vì file trên disk đổi. Trong CI có thể tạo hai cert và kiểm handshake mới, không cần restart app, nhưng tránh hardcode thời gian cố định dễ gây flaky tests.

### 7.11. Khi cần rotate cả private key và certificate

Trong production, hãy dùng công cụ phát hành/triển khai cert có đảm bảo:

- Generate key/cert pair mới và xác minh **match**.
- Cập nhật chain hoàn chỉnh, SAN, EKU và ngày hiệu lực.
- Stage file vào thư mục riêng có ACL đúng; kiểm trước khi publish.
- Publish cặp cert/key theo quy trình **nhất quán** (ví dụ versioned secret volume/atomic symlink switch do hệ thống quản trị hỗ trợ), tránh watcher nhìn thấy cert mới với key cũ.
- Tạo quan sát/alert nếu reload thất bại; giữ phiên bản cũ để rollback theo policy.
- Test handshake mới trên **từng instance/pod**, không chỉ qua một load balancer có thể đưa request tới pod khỏe.
- Chỉ thu hồi/hủy key cũ sau khi xác nhận dịch vụ không còn cần và theo quy tắc PKI.

Dù cert/key file được triển khai vào một nơi, **không có nghĩa mọi listener/SSLContext đã refresh**. Hãy đo cert **đang được phục vụ** ở socket.

## 8. Theo dõi thời hạn chứng thư: giám sát endpoint, không chỉ ổ đĩa

Các mốc quan sát nên có:

| Mốc trước ngày hết hạn | Hành động gợi ý |
| --- | --- |
| 30 ngày | Tạo cảnh báo sớm, xác nhận cơ chế auto-renew và người phụ trách |
| 14 ngày | Điều tra nếu chưa có cert mới hoặc có lỗi renew |
| 7 ngày | Tăng ưu tiên khắc phục và kiểm triển khai trên mọi instance |
| 3 ngày / 1 ngày | Cảnh báo khẩn theo SLO, sẵn sàng phương án failover/rotation |
| Sau ngày hết hạn | Incident; khách hàng có thể bị lỗi TLS handshake |

Các mốc là **ví dụ policy vận hành**, không phải yêu cầu RFC. Với cert sống ngắn, đặt cảnh báo theo tỷ lệ vòng đời và lịch renew, đồng thời giữ đủ buffer cho CA/challenge/maintenance window. Nếu chỉ kiểm lúc gần hết hạn, một lỗi đồng bộ thời gian hoặc CA outage có thể làm trễ quá trình phục hồi.

### Hai đối tượng cần đo tách biệt

1. **Chứng thư ở source**: file `fullchain.pem` mới, secret manager mới, metadata chứng thư PKCS12 mới.
2. **Chứng thư đang được phục vụ qua TLS**: leaf cert nhận từ một **handshake mới** tới endpoint, có SNI/port đúng.

Nếu file có notAfter năm sau nhưng server vẫn trình chứng thư hết hạn tuần này, **đường deploy/reload đã sai**. Nếu edge certificate mới nhưng backend mTLS cert cũ, việc kiểm chỉ public site không bắt được lỗi hop nội bộ.

### Lệnh OpenSSL cơ bản

~~~bash
# Chứng thư file local:
openssl x509 -in /run/secrets/webserver/fullchain.pem -noout \
  -subject -issuer -serial -dates -ext subjectAltName

# Kiểm chứng thư sẽ hết hạn trong 30 ngày tới (2.592.000 giây).
# Exit code 0: còn hợp lệ sau khoảng đó; non-zero: sắp hết hạn/lỗi.
openssl x509 -in /run/secrets/webserver/fullchain.pem \
  -noout -checkend 2592000
~~~

Lệnh `-checkend` là cách dễ đặt check trong cron/monitoring, nhưng nó chỉ kiểm **file** được đưa vào; không xác minh private key có khớp hoặc listener đã reload. Dùng song song active TLS probe.

### Java 17 CLI: đọc hạn leaf certificate mà không đụng private key

Tạo file `CertDeadline.java` bên ngoài project Spring Boot; đây là **chương trình Java độc lập**, chỉ cần JDK 17:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.time.Duration;
import java.time.Instant;

public class CertDeadline {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CertDeadline <certificate.pem>");
            System.exit(2);
        }

        Path certificatePath = Path.of(args[0]);
        CertificateFactory factory = CertificateFactory.getInstance("X.509");

        X509Certificate certificate;
        try (InputStream in = Files.newInputStream(certificatePath)) {
            certificate = (X509Certificate) factory.generateCertificate(in);
        }

        Instant now = Instant.now();
        Instant notBefore = certificate.getNotBefore().toInstant();
        Instant notAfter = certificate.getNotAfter().toInstant();
        long hoursLeft = Duration.between(now, notAfter).toHours();

        System.out.println("Subject: "
                + certificate.getSubjectX500Principal().getName());
        System.out.println("Not before: " + notBefore);
        System.out.println("Not after:  " + notAfter);
        System.out.println("Hours left: " + hoursLeft);

        if (now.isBefore(notBefore) || !now.isBefore(notAfter)) {
            System.err.println("Certificate is outside validity window");
            System.exit(2);
        }
        if (!notAfter.isAfter(now.plus(Duration.ofDays(30)))) {
            System.err.println("Certificate expires within 30 days");
            System.exit(1);
        }
    }
}
~~~

Chạy từ thư mục chứa file:

~~~bash
javac --release 17 CertDeadline.java
java CertDeadline tls/server.crt
~~~

Output phụ thuộc chứng thư và đồng hồ hệ thống:

~~~text
Subject: CN=localhost
Not before: <thời điểm ISO-8601 lấy từ cert>
Not after:  <thời điểm ISO-8601 lấy từ cert>
Hours left: <số giờ nguyên tính từ thời điểm chạy>
~~~

Các placeholder trong ví dụ output ở trên là mô tả giá trị biến thiên, **không phải stdout cố định**. Lệnh có thể exit 1 với self-signed cert chỉ sống 7 ngày như demo; điều này **đúng thiết kế ngưỡng cảnh báo 30 ngày**, không có nghĩa chương trình hỏng. Khi triển khai giám sát thật, cần monitor endpoint qua TLS và không chỉ dựa vào chương trình đọc local file.

### Theo dõi nhiều tên miền/SNI/instances

Một dịch vụ có thể có nhiều:

- Public domains, wildcard certificates, SAN entries.
- SNI bundle cho mỗi hostname.
- Ingress replicas, regional load balancers, blue/green deployments.
- Internal mTLS identities cho service mesh.
- Client certificates gọi đến database/third-party services.

Monitor phải kiểm **từng hostname + port + SNI** và khi có thể từng instance/backend. Một load balancer trả cert mới ở 95% requests không có nghĩa 5% instance còn lại đã cập nhật. Kiểm tra expiry cả leaf lẫn intermediate chain cần thiết; intermediate hết hạn cũng có thể làm validation thất bại.

## 9. Runbook gia hạn và triển khai chứng thư an toàn

### Bước A — Inventory và ownership

Lưu trong hệ thống quản trị:

- Hostname/SAN và endpoint public, nội bộ.
- TLS termination point: CDN, ingress, Nginx, Tomcat, Netty, Jetty.
- CA/issuer, loại challenge ACME hoặc quy trình PKI nội bộ.
- Secret path/secret object ID (không lưu private key vào inventory).
- Phụ thuộc (app, load balancer, external client, mTLS peer).
- Chủ sở hữu, thời hạn, công cụ renew, lịch cảnh báo, phương án rollback.

### Bước B — Gia hạn sớm

Gia hạn tự động có kiểm soát, kiểm lỗi CA/network/DNS/ACME. Với Let's Encrypt + Certbot, `certbot renew` chỉ có ý nghĩa khi host đã cấu hình issuance; Spring Boot không làm việc đó thay bạn. Với Kubernetes, cert-manager có thể tự renew Secret, nhưng ứng dụng vẫn phải nhìn thấy file mới và reload được consumer. **Chứng thư được cấp mới khác chứng thư đã được server phục vụ.**

### Bước C — Validation trước khi publish

Kiểm:

1. SAN bao phủ hostname cần phục vụ; wildcard không khớp mọi cấp subdomain.
2. notBefore/notAfter hợp lệ theo đồng hồ đã đồng bộ NTP; thời hạn còn đủ buffer.
3. Leaf cert tương ứng private key.
4. Certificate chain đủ intermediate, issuer đáng tin; không nhầm `cert.pem` với `fullchain.pem`.
5. Chứng thư hỗ trợ serverAuth/KeyUsage theo PKI policy; thuật toán/key size theo policy tổ chức.
6. File path, owner, ACL, symlink target đúng; secret manager không xuất bí mật ra log.

Ví dụ kiểm public key cert và key **qua hash SPKI** (không in private key):

~~~bash
# Hai giá trị hash SHA-256 phải giống nhau khi cert/key khớp.
openssl x509 -in tls/server.crt -pubkey -noout \
  | openssl pkey -pubin -outform DER | openssl dgst -sha256

openssl pkey -in tls/server.key -pubout -outform DER \
  | openssl dgst -sha256
~~~

Không upload file private key lên website “certificate checker” không rõ bên vận hành để test. Dùng OpenSSL/keytool nội bộ.

### Bước D — Triển khai

- Stage và kiểm cert/key mới ở vùng có quyền hạn chế.
- Publish nhất quán qua secret manager/versioned mount; với PEM pair, tránh partial update.
- Nếu Boot SSL bundle watcher + Tomcat/Netty được dùng, bảo đảm `reload-on-update` đã bật, path là file được watcher theo dõi và file đã thực sự thay.
- Nếu server không có documented hot reload, dùng **rolling restart** có readiness probes/drain kết nối, không ép một API không được hỗ trợ.
- Nếu TLS terminate ở gateway/CDN, chạy cơ chế reload của gateway/CDN.
- Không làm đồng loạt mọi pod khi chưa có canary; chỉ giảm downtime theo khả năng hệ thống.

### Bước E — Kiểm chứng sau deploy

- Thực hiện TLS handshake mới từ bên ngoài theo hostname/SNI.
- So fingerprint, serial, notAfter, SAN, chain của cert **đang serve** với bản dự kiến.
- Kiểm HTTP 200 và HTTP/2 ALPN (nếu hệ thống yêu cầu).
- Kiểm từng pod/instance hoặc các route canary, không chỉ một lần qua LB.
- Kiểm mTLS client, outbound TLS dependencies và app health/error rate.
- Giữ rollback key/cert cũ trong khoảng thời gian có policy; dọn sau khi hoàn tất.

### Bước F — Giám sát liên tục

Theo dõi tỷ lệ TLS handshake failure, alert expiry, watcher/reload logs, connectivity error, certificate inventory drift và trạng thái renew job. Cảnh báo nếu **file source đổi nhưng served certificate không đổi** sau thời hạn dự kiến. Có diễn tập rotation trước khi bước vào sự cố thực.

## 10. SNI, nhiều tên miền và nhiều chứng thư

Một JVM listener có thể phục vụ nhiều hostname bằng **Server Name Indication (SNI)**. Client gửi hostname trong ClientHello để TLS terminator chọn đúng cert trước khi HTTP request được xử lý.

Spring Boot hỗ trợ ánh xạ bundle theo server name cho **Tomcat và Netty** theo tài liệu Embedded Web Servers:

~~~properties
server.port=8443
server.ssl.bundle=defaultweb

server.ssl.server-name-bundles[0].server-name=api.example.com
server.ssl.server-name-bundles[0].bundle=apiweb

server.ssl.server-name-bundles[1].server-name=admin.example.com
server.ssl.server-name-bundles[1].bundle=adminweb
~~~

Các bundle `defaultweb`, `apiweb` và `adminweb` phải được khai báo riêng với key/cert phù hợp. Đây là **minh họa fragment config**, không chạy độc lập nếu chưa có bundle. Default bundle phục vụ các kết nối không gửi/match SNI theo rules của server.

Cần monitor mỗi hostname riêng: một TLS listener chạy ổn nhưng cert SNI của một domain đã hết hạn vẫn gây lỗi chỉ cho domain đó. Khi test, luôn dùng hostname thực hoặc `openssl s_client -servername ...`; gọi trực tiếp bằng IP có thể thấy default cert và báo lỗi tên miền.

**Jetty:** tài liệu Boot lưu ý SNI cấu hình theo `server-name-bundles` không hỗ trợ như Tomcat/Netty; Jetty có cơ chế tự SNI khi có nhiều certificates trong một số cấu hình. Không sao chép fragment trên rồi cho rằng Jetty xử lý giống hệt.

## 11. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/khắc phục |
| --- | --- | --- |
| Browser báo certificate expired, app vẫn 200 nội bộ | Public TLS cert trên edge/Tomcat đã hết hạn | Probe public endpoint/hostname/SNI, inspect notAfter |
| File cert mới nhưng browser vẫn thấy cert cũ | Reload chưa chạy, kiểm nhầm hop, giữ session cũ hoặc một pod chưa cập nhật | Kết nối TLS mới; so served fingerprint từng instance |
| Boot không khởi động TLS | Private key không đọc được, key/cert mismatch, bundle name/path sai | Kiểm logs, file ACL, public-key hash, PEM/PKCS12 format |
| `NoSuchFileException` ở file: path | Relative working directory khác dự kiến; secret mount chưa có | Dùng absolute path production, mount before start |
| `SSLHandshakeException` hostname mismatch | Cert SAN không bao phủ hostname hoặc SNI sai | Kiểm SAN và `-servername`; phát hành lại cert đúng tên |
| `PKIX path building failed` | Client không tin root/intermediate, chain thiếu hoặc truststore sai | Kiểm chain/trust, không tắt TLS verification |
| 443 hoạt động nhưng HTTP/2 không được dùng | ALPN/HTTP2 chưa bật ở đúng hop hoặc client thiếu support | Check `server.http2.enabled`, `curl --http2` và proxy config |
| Cert mới nhưng private key cũ | Cặp file bị triển khai không nhất quán | Stage pair và verify SPKI match trước publish |
| Certbot renew thành công nhưng Tomcat vẫn cũ | Certbot chỉ cập nhật file; watcher/consumer không nhận | Bật reload bundle/đúng path hoặc rolling restart |
| Hạn cert trên disk còn dài, public cert sắp hết hạn | Public TLS terminate ở CDN/LB khác hoặc pod khác | Inventory termination, monitor live endpoint |
| `reload-on-update` bật nhưng Jetty không reload | Jetty không nằm trong danh sách consumer hỗ trợ của Boot | Kiểm theo version; dùng restart/rolling hoặc integration riêng |
| Mẫu config Undertow Boot 3 không chạy Boot 4 | Spring Boot 4 đã bỏ embedded Undertow | Dùng Tomcat/Jetty phù hợp hoặc duy trì stack/version đúng |
| Tạo cert mới nhưng client báo unknown CA | Tự ký không được trust hoặc CA chain sai | Dùng CA đáng tin trong production; demo dùng --cacert |
| Chỉ một số khách hàng lỗi TLS | Phân phối pod không đồng đều, SNI, chain/legacy clients khác nhau | Probe từng backend/region/client capability |
| Theo dõi expiry bằng file trong container | File không phải cert thực do edge serve | Monitor from outside handshake + files cho diagnosis |
| Key bị leak vào Git/log | Thiếu secret-handling policy | Rotate/revoke key, giới hạn quyền, xử lý credential incident |
| Rotation làm rớt HTTP/2 sessions | Server restart, connection drain không phù hợp | Graceful shutdown, connection drain, canary rollout |
| Cert xuất hiện trước notBefore | Đồng hồ CA/server/client sai hoặc deploy quá sớm | Đồng bộ NTP, không publish trước hiệu lực |

### Thứ tự điều tra khi TLS lỗi sau một lần rotate

1. Ai là TLS terminator cho request thất bại?
2. SNI/hostname/port nào, certificate serial/fingerprint nào đã được trình?
3. Chứng thư còn hiệu lực và đúng SAN, EKU, chain và CA trust không?
4. File/secret được mong đợi đã có nội dung mới chưa, quyền đọc có đúng?
5. Watcher có báo thay đổi/reload không? Consumer có documented support?
6. Có instance/pod nào giữ cert cũ, session cũ hoặc proxy layer chưa cập nhật?
7. ALPN HTTP/2 có liên quan trực tiếp đến lỗi, hay lỗi xảy ra từ TLS trước khi HTTP bắt đầu?
8. Có thể rollback an toàn/rolling restart không, và cách không làm lộ private key trong debug?

## 12. Khi nào nên dùng rolling restart thay hot reload?

Hot reload giảm nhu cầu restart trong rotation thường xuyên, nhưng không phải luôn phù hợp:

- Chạy Jetty hoặc consumer không có documented bundle reload trong version đang dùng.
- Dùng keystore/format mà chưa xác minh được cơ chế watcher/refresh đúng.
- Secret được cập nhật qua env var tại process start, không thay đổi được đối với JVM đang chạy.
- Hệ thống có nhiều SSLContext/listeners (inbound, management, client) với mức hỗ trợ reload khác nhau.
- File được mount qua filesystem không phát watch event mà Boot trông đợi hoặc cập nhật pair không nguyên tử.
- Tổ chức yêu cầu rollout canary, versioned config và audit nghiêm ngặt.

Với rolling restart, nên có **ít nhất hai replica** và readiness/health gating khi cần high availability; thay từng pod/node, chờ handshake/cert mới được xác minh rồi tiếp tục. “No downtime” là mục tiêu cần test trong workload thực tế, không tự bảo đảm chỉ từ cấu hình `server.shutdown=graceful`.

### Hot reload cũng cần rollback

Nếu cert mới sai SAN hoặc private key không khớp, watcher có thể gặp lỗi. Cần biết server sẽ tiếp tục phục vụ cert cũ, ngừng listener hay thay đổi theo cơ chế implementation—**không giả định** một hành vi nhất định cho mọi phiên bản. Giữ bản cũ, kiểm logs, có playbook publish lại bản cũ hoặc restart có kiểm soát sau khi nguyên nhân được sửa.

## 13. Checklist dành cho production

### Quản lý bí mật và cấp phát

- [ ] Private key, password và CA issuance credentials không có trong repository, Docker image, JAR, ticket, logs hoặc build artifact?
- [ ] Secret manager/volume có identity, RBAC/IAM, ACL và audit hợp lý; chương trình chỉ được đọc phần nó cần?
- [ ] TLS termination point của mỗi public/internal hostname được ghi nhận, không nhầm edge cert và backend cert?
- [ ] Key được tạo bằng thuật toán/key length theo tiêu chuẩn của tổ chức; private key được rotate nếu compromise?
- [ ] Có thể thay file/secret mà không build và deploy lại mã ứng dụng khi quy trình yêu cầu?

### Chất lượng chứng thư

- [ ] SAN bao phủ đúng hostname/IP; không chỉ dựa vào CN?
- [ ] Certificate đang còn trong `notBefore/notAfter` và chain tới CA tin cậy?
- [ ] Cert/key SPKI match; intermediates đầy đủ, trust root hợp lệ?
- [ ] Có kiểm EKU/KeyUsage, revocation/policy khi tổ chức yêu cầu?
- [ ] Đồng hồ hệ thống/cert monitoring được đồng bộ và không làm lộ dữ liệu?

### Reload và tính liên tục

- [ ] Đã xác nhận embedded server thực tế là Tomcat, Reactor Netty hay Jetty?
- [ ] Với Boot reload, dùng PEM file bundle và consumer có documented support Tomcat/Netty?
- [ ] `reload-on-update` được bật và watch file path thật, quiet period phù hợp?
- [ ] Rotation pair được triển khai nhất quán, không nạp chứng thư/key lệch nhau?
- [ ] Probe cert qua handshake mới, SNI đúng, mỗi instance/region, cả sau rotation?
- [ ] Có rolling restart fallback khi watcher/reload không hoạt động?
- [ ] Có xử lý HTTP/2 keepalive, graceful shutdown và connection drain phù hợp?

### Vận hành và đo lường

- [ ] Có inventory certificate và chủ sở hữu, cùng ngưỡng cảnh báo trước expiry?
- [ ] Renewal job được giám sát, có test dry-run/rollback và kiểm TLS serve thực tế?
- [ ] Có alert cho expired/not-yet-valid, chain mismatch, cert drift giữa pods, TLS handshake errors?
- [ ] Có phân biệt status TLS hop public, backend re-encryption và outbound/mTLS?
- [ ] Không bật trust-all/disableHostnameVerification chỉ để bỏ lỗi certificate?

## 14. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Spring Boot bật `spring.ssl.bundle.pem.webserver.reload-on-update=true` thì tự gia hạn cert Let's Encrypt?

**Đáp án:** Không. Boot theo dõi và reload material khi file đổi; ACME/Certbot/cert-manager/Vault PKI cấp và gia hạn. Phải xác nhận cert mới được triển khai và server dùng thật.

**Câu 2.** File cert mới có notAfter sau một năm nhưng browser vẫn cảnh báo expired. Nên làm gì?

**Đáp án:** Kiểm TLS terminator thật từ ngoài bằng hostname + SNI, xem fingerprint/serial/expiry của cert **đang serve**. Có thể edge khác, pod chưa cập nhật, watcher không hoạt động hoặc connection cũ.

**Câu 3.** Có thể áp dụng hot reload SSL bundle mặc định cho mọi máy chủ Spring Boot 4?

**Đáp án:** Không. Tài liệu Boot liệt kê Tomcat và Netty; Jetty không được bảo đảm qua cơ chế đó. Undertow embedded bị loại khỏi Boot 4. Kiểm đúng version và fallback rolling restart.

**Câu 4.** `server.http2.enabled=true` có giải quyết được cert hết hạn?

**Đáp án:** Không. HTTP/2 là giao thức HTTP đã được thương lượng sau TLS; client vẫn phải xác minh certificate và bắt tay TLS thành công.

**Câu 5.** Keystore password trong environment variable thì private key hoàn toàn an toàn?

**Đáp án:** Không. Environment và file vẫn có thể bị lộ qua quyền hệ thống, log/dump hoặc kênh vận hành. Cần IAM/ACL tối thiểu, audit và rotation.

**Câu 6.** Vì sao chỉ kiểm file `fullchain.pem` không đủ?

**Đáp án:** Vì file có thể khác cert đang dùng; reload hoặc proxy/instance có thể chưa cập nhật. Phải probe handshake mới từ client và xác định hop.

**Câu 7.** Khi thay đồng thời private key và cert, có thể copy ngẫu nhiên từng file vào path đang watch không?

**Đáp án:** Không nên. Trong lúc copy có thể có cert/key mismatch, reload lỗi. Stage/verify pair và publish nhất quán qua cơ chế secret/version được hỗ trợ.

**Câu 8.** Cùng listener phục vụ api.example.com và admin.example.com; cần test gì?

**Đáp án:** Kiểm SNI/hostname từng domain, SAN/chain và notAfter của từng leaf cert. Default certificate khi thiếu SNI không chứng minh cert cho mọi hostname đúng.

**Câu 9.** Cert tự ký localhost dùng `curl -k` được, có nên làm vậy cho production?

**Đáp án:** Không. Trong demo có thể dùng `--cacert tls/server.crt` để tin đúng cert. Production dùng PKI đáng tin; không vô hiệu hóa hostname/trust validation.

**Câu 10.** Reload TLS thành công có nhất thiết thay certificate trên HTTP/2 connection đã mở?

**Đáp án:** Không. TLS handshake diễn ra khi thiết lập kết nối; HTTP/2 có thể reuse connection cũ. Dùng một handshake mới để kiểm cert được trình sau reload.

## 15. Tài liệu chính thức

- [Spring Boot — SSL bundles, PEM/JKS, reload-on-update, Let's Encrypt](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot — Embedded Web Servers, SSL bundle, SNI, HTTP/2](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — Common Application Properties: server.ssl.*, spring.ssl.bundle.*](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot 4.0 Migration Guide — Undertow removed](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 7301 — ALPN](https://www.rfc-editor.org/rfc/rfc7301)
- [Let's Encrypt — Certificates](https://letsencrypt.org/docs/)
- [Certbot — Renewing Certificates](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates)
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)

**Ghi nhớ:** Chứng thư server chỉ có giá trị khi có **private key được bảo vệ, chain và SAN hợp lệ, chưa hết hạn và được TLS terminator thật sử dụng**. Tách bí mật khỏi source/image; gia hạn từ CA/ACME, triển khai file nhất quán, sau đó reload qua **SSL bundle ở Tomcat hoặc Netty khi được hỗ trợ**, hay rolling restart cho trường hợp khác. Kiểm thành công bằng **handshake mới từ client với SNI đúng** và giám sát từng endpoint/instance, không chỉ nhìn file đã được thay trên đĩa.