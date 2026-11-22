# Lựa chọn phiên bản TLS và bộ mã hóa được cho phép trong Spring Boot

## 1. Vì sao phải chủ động quản lý phiên bản TLS và cipher suites?

Khi browser truy cập `https://api.example.com`, trước khi gửi HTTP request, client và server thiết lập một kết nối bảo mật bằng **TLS (Transport Layer Security)**. Trong quá trình handshake, hai bên thương lượng **phiên bản TLS**, các thuật toán mã hóa/chứng thực phù hợp và khóa dùng để bảo vệ dữ liệu. Nếu client và server không có tập lựa chọn tương thích, kết nối có thể thất bại **trước khi request đến Spring MVC controller hoặc WebFlux handler**.

Một cấu hình TLS hợp lý cần cân bằng:
- **Bảo mật**: không thương lượng giao thức cũ hoặc các cipher suite yếu/không phù hợp.
- **Tương thích**: còn hỗ trợ các client hợp lệ, phiên bản Java, hệ điều hành và gateway mà sản phẩm phải phục vụ.
- **HTTP/2**: bảo đảm lựa chọn TLS/cipher không vi phạm các ràng buộc của HTTP/2 over TLS.
- **Khả năng vận hành**: hiểu TLS được kết thúc ở Spring Boot hay ở reverse proxy/load balancer, và có phương pháp đo, rollout, rollback.

Bài học tập trung vào **hai quyết định**:
1. **Cho phép phiên bản nào?** Ví dụ `TLSv1.3` và `TLSv1.2`.
2. **Cho phép bộ mã hóa nào?** Ví dụ `TLS_AES_128_GCM_SHA256` cho TLS 1.3, `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` cho TLS 1.2 với chứng chỉ RSA.

Hai danh sách liên quan nhưng **không đồng nghĩa**. Với Spring Boot 3.5, các thuộc tính trực tiếp của embedded server là `server.ssl.enabled-protocols` và `server.ssl.ciphers`. Nếu server sử dụng **SSL bundle** qua `server.ssl.bundle`, cần đặt protocol/cipher trong `spring.ssl.bundle.<type>.<name>.options` thay vì dựa vào các thuộc tính trực tiếp bị bỏ qua ở cấu hình bundle. Chi tiết và ví dụ nằm ở các mục sau.

> **Phiên bản:** ví dụ runnable dùng Java 17+, Spring Boot **3.5.x**, Spring MVC và embedded Tomcat với JSSE của JDK. Với Spring Boot 4.x, starter MVC là `spring-boot-starter-webmvc` thay vì `spring-boot-starter-web`; các property và hỗ trợ từng server cần đối chiếu theo version thực tế. Cấu hình TLS cũng có thể khác khi dùng Jetty, Reactor Netty, provider OpenSSL/native hoặc termination ở gateway.

## 2. Phân biệt TLS, HTTPS, HTTP/2, chứng chỉ và cipher suite

| Thành phần | Giải quyết vấn đề gì? | Ví dụ |
|---|---|---|
| TLS protocol version | Quy tắc handshake, key schedule và bảo mật truyền tải | `TLSv1.3`, `TLSv1.2` |
| Cipher suite | Các thuật toán mã hóa/xác thực được chọn cho kết nối | `TLS_AES_128_GCM_SHA256` |
| Certificate | Server chứng minh danh tính qua chứng chỉ X.509 phù hợp với hostname | SAN chứa `api.example.com` |
| Private key | Server chứng minh quyền kiểm soát danh tính tương ứng | Key trong PKCS12/PEM |
| Trust store | Những CA/chứng chỉ mà bên xác minh tin cậy | Public CA roots, internal CA |
| HTTPS | HTTP chạy trên kết nối TLS | `https://...` |
| HTTP/2 over TLS | HTTP/2 truyền qua TLS, lựa chọn giao thức ứng dụng qua ALPN | ALPN `h2` |
| SNI | Client báo hostname mong muốn trong TLS handshake | `api.example.com` |
| mTLS | Server cũng xác minh chứng chỉ của client | `server.ssl.client-auth` + trust store |

**Không đánh đồng:** bật `server.http2.enabled=true` không tự chọn một cipher an toàn; bật HTTPS không tự xác minh rằng các client cũ không còn thương lượng được TLS 1.0/1.1; chỉnh cipher list không thay chứng chỉ hết hạn hoặc SAN sai.

### Hai lớp thương lượng khác nhau

~~~text
ClientHello
  +--- Supported TLS versions: TLS 1.3, TLS 1.2
  +--- Cipher suites offered
  +--- Supported groups / signature algorithms
  +--- SNI hostname
  +--- ALPN: h2, http/1.1
                 |
                 v
            TLS endpoint
                 |
                 +--- TLS protocol version được chọn
                 +--- Cipher suite phù hợp
                 +--- Key exchange / chứng chỉ / chữ ký
                 +--- ALPN protocol được chọn
                 |
                 v
       Kết nối TLS đã được xác thực
                 |
                 v
       HTTP/2 hoặc HTTP/1.1 request
                 |
                 v
       Spring Boot controller / handler
~~~

Sơ đồ rút gọn các bước handshake; thứ tự và chi tiết thông điệp khác nhau giữa TLS 1.2 và 1.3. Chỉ khi TLS handshake thành công, ứng dụng HTTP mới có cơ hội xử lý request.

## 3. Nên cho phép phiên bản TLS nào?

### TLS 1.3 — ưu tiên cho client hiện đại

TLS 1.3 đơn giản hóa và nâng cấp handshake, loại bỏ nhiều thuật toán cũ. Cipher suites của TLS 1.3 chỉ nêu **AEAD cipher** cùng hàm băm cho key schedule, trong khi key exchange và signature được thương lượng bằng các extension/cơ chế riêng. Đây là lý do không thể dùng nguyên tên cipher TLS 1.2 để mô tả lựa chọn TLS 1.3.

Các suite TLS 1.3 phổ biến:
- `TLS_AES_128_GCM_SHA256`
- `TLS_AES_256_GCM_SHA384`
- `TLS_CHACHA20_POLY1305_SHA256` khi provider/runtime hỗ trợ

Dữ liệu được bảo vệ bằng thuật toán **AEAD** (authenticated encryption with associated data). Cần xác minh hỗ trợ của JDK/provider, chứ không giả định cả ba suite đều có trên mọi runtime/container.

### TLS 1.2 — vẫn hữu ích khi cần tương thích

TLS 1.2 có thể được giữ trong danh sách cho phép để phục vụ hệ thống client vẫn hợp lệ nhưng chưa nâng cấp lên 1.3. Với TLS 1.2, nên ưu tiên các suite có:
- Trao đổi khóa **ECDHE** cung cấp forward secrecy.
- AES-GCM hoặc AEAD phù hợp.
- Chữ ký/chứng chỉ phù hợp với thuật toán xác thực ở tên cipher.

Ví dụ với **chứng chỉ server RSA**:
- `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`
- `TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384`

Ví dụ với **chứng chỉ server ECDSA**:
- `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256`
- `TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384`

Các suite ECDHE_RSA và ECDHE_ECDSA ở TLS 1.2 không hoán đổi tùy ý nếu chứng chỉ/khả năng xác thực của server không tương thích. Số bit 256 không tự động khiến một lựa chọn phù hợp hơn trong mọi trường hợp; cần xem hiệu năng, policy và client support.

### TLS 1.0 và TLS 1.1 — không bật lại vì client cũ

TLS 1.0/1.1 đã lỗi thời và không nên được mở trong hệ thống hiện đại chỉ để “cho một client nào đó chạy”. Nếu có client legacy thực sự phải duy trì, giải pháp nên là nâng cấp client, phân tách gateway chuyển tiếp có kiểm soát và kế hoạch loại bỏ rủi ro, thay vì hạ chính sách TLS của toàn bộ public API.

**Cấu hình xuất phát điểm thực tế:** hỗ trợ `TLSv1.3` và `TLSv1.2` nếu có nhu cầu tương thích. Chỉ cho phép TLS 1.3 khi có bằng chứng toàn bộ client/systems trung gian đều tương thích và policy tổ chức cho phép. Không có một danh sách phù hợp tuyệt đối cho tất cả dịch vụ.

### Bảng quyết định

| Bối cảnh | Chính sách gợi ý để kiểm chứng | Lý do |
|---|---|---|
| Public API có client mới và một số client Java/OS cũ còn hỗ trợ | TLS 1.3 + 1.2, cipher AEAD phù hợp | Cân bằng an toàn/tương thích |
| Internal API do một đội kiểm soát hoàn toàn client | Cân nhắc TLS 1.3-only sau test | Thu hẹp surface nếu đã kiểm chứng |
| HTTP/2 over TLS và có fallback TLS 1.2 | Cho phép suite TLS 1.2 tuân thủ HTTP/2 | Tránh `INADEQUATE_SECURITY` |
| Gặp client chỉ có TLS 1.0/1.1 | Nâng cấp client hoặc thiết kế phương án chuyển tiếp riêng | Không hạ bảo mật public endpoint |
| Yêu cầu FIPS/regulatory cụ thể | Tuân policy và provider được phê duyệt | Không suy luận tuân thủ chỉ từ tên cipher |

## 4. Cipher suites của TLS 1.3 khác TLS 1.2 như thế nào?

Một cách dễ đọc tên suite:

**TLS 1.2:**

~~~text
TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
    |     |       |   |   |   |
    |     |       |   |   |   +--- SHA-256 (gắn với cơ chế TLS 1.2)
    |     |       |   |   +------- GCM (AEAD mode)
    |     |       |   +----------- khóa AES 128 bit
    |     |       +--------------- AES
    |     +----------------------- RSA authentication/certificate
    +----------------------------- ECDHE key agreement
~~~

**TLS 1.3:**

~~~text
TLS_AES_128_GCM_SHA256
    |   |   |      |
    |   |   |      +--- HKDF/hash
    |   |   +---------- authenticated encryption mode
    |   +-------------- symmetric key size
    +------------------ AEAD algorithm family
~~~

Với TLS 1.3, tên cipher không nêu ECDHE_RSA vì key exchange và certificate authentication được lựa chọn riêng. Không có chuyện `TLS_AES_128_GCM_SHA256` chạy trên TLS 1.2 chỉ vì nó có chữ AES-GCM, hoặc `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` là tên TLS 1.3.

| Suite | TLS version | Khi nào có thể được chọn |
|---|---|---|
| `TLS_AES_128_GCM_SHA256` | TLS 1.3 | Client, server và provider hỗ trợ |
| `TLS_AES_256_GCM_SHA384` | TLS 1.3 | Client, server và provider hỗ trợ |
| `TLS_CHACHA20_POLY1305_SHA256` | TLS 1.3 | Provider hỗ trợ và policy cho phép |
| `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` | TLS 1.2 | Có capability RSA auth + ECDHE phù hợp |
| `TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256` | TLS 1.2 | Có capability ECDSA auth + ECDHE phù hợp |
| `TLS_RSA_WITH_AES_128_CBC_SHA` | TLS 1.2 | Legacy; **không chọn cho cấu hình mới** |

**Không nên bật** các suite legacy như RC4, 3DES, NULL, EXPORT, static RSA key exchange hoặc cấu hình CBC lỗi thời cho ứng dụng mới. Đây không phải chỉ vì tên thuật toán “xấu”; rủi ro liên quan đến tính bảo mật, forward secrecy, lỗi triển khai và các giới hạn chuẩn hiện hành.

RFC về TLS 1.3 giải thích các khác biệt này; RFC 9325 (BCP 195) đưa ra hướng dẫn sử dụng TLS/DTLS an toàn. Luôn đối chiếu policy tổ chức và các bản cập nhật tiêu chuẩn.

## 5. Thực tế chọn suite: giao điểm của nhiều giới hạn

Khi có một TLS handshake, không phải mọi suite có trong YAML đều tự động có thể thương lượng. Suite kết quả chịu đồng thời:

1. **Client offer:** những TLS versions/cipher suites client quảng cáo.
2. **Server policy:** danh sách versions/suites được phép.
3. **JDK/provider:** JSSE hoặc OpenSSL/native phải triển khai hỗ trợ.
4. **JDK security restrictions:** `jdk.tls.disabledAlgorithms` trong `java.security` có thể loại bỏ protocol/algorithm yếu.
5. **Certificate/key:** loại khóa RSA/ECDSA, key size, signature algorithms và trust chain.
6. **Groups/key exchange:** elliptic curves/finite-field groups có giao nhau không.
7. **HTTP application protocol:** nếu dùng HTTP/2, TLS 1.2 có tập suite không được khuyến nghị và những hạn chế riêng.
8. **Tầng thực sự kết thúc TLS:** Spring Boot, gateway, Envoy, Nginx, cloud load balancer hay CDN.

Có thể hình dung:

~~~text
Negotiable suites
  = Client-supported
  ∩ TLS-version-compatible
  ∩ Server-allowed
  ∩ Provider-implemented
  ∩ JDK-security-policy-allowed
  ∩ Certificate/key-compatible
  ∩ Protocol/application constraints
~~~

Công thức tập hợp mang tính khái niệm, không thay thế handshake thật. Cấu hình chỉ một suite cực hẹp có thể khiến toàn bộ clients hợp lệ từ chối kết nối nếu chúng không hỗ trợ suite đó.

### `server.ssl.protocol` khác `enabled-protocols`

Trong Spring Boot:
- `server.ssl.protocol` (thường mặc định `TLS`) là tên thuật toán/protocol dùng để khởi tạo SSL context hoặc TLS implementation.
- `server.ssl.enabled-protocols` là tập TLS protocol versions được bật, ví dụ `TLSv1.3` và `TLSv1.2`.

**Không ghi** `server.ssl.protocol: TLSv1.3` rồi mặc định cho rằng đã có chính sách phiên bản rõ ràng như `enabled-protocols`. Hãy dùng đúng property cho enabled versions và kiểm chứng handshake trên runtime.

## 6. Spring Boot cấu hình trực tiếp bằng `server.ssl.*`

Spring Boot hỗ trợ SSL qua keystore hoặc PEM. Với ứng dụng embedded server tự kết thúc TLS, cấu hình trực tiếp cơ bản có thể là:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:local-tls.p12
    key-store-type: PKCS12
    key-store-password: changeit
    key-alias: localtls
    enabled-protocols:
      - TLSv1.3
      - TLSv1.2
    ciphers:
      - TLS_AES_128_GCM_SHA256
      - TLS_AES_256_GCM_SHA384
      - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
      - TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384
  http2:
    enabled: true
~~~

Đây là **cấu hình học tập** cho keystore RSA tự ký tạo ở mục 8. `changeit` chỉ là mật khẩu đơn giản cho demo; **không dùng trong production**. Các suite TLS 1.2 minh họa phù hợp với chứng chỉ RSA được tạo trong bài. Các suite TLS 1.3 không phụ thuộc nhãn RSA/ECDSA trong tên; tính tương thích thực tế còn phụ thuộc provider và chữ ký/chứng chỉ.

Nếu cần hỗ trợ client/thiết bị không hỗ trợ một suite trong danh sách, **không vội thêm ciphers yếu**. Trước tiên kiểm tra server JSSE provider, client capabilities, kết quả handshake, certificate key, hỗ trợ AES/GCM/ChaCha và mục tiêu tương thích.

### Giải thích từng cấu hình

| Thuộc tính | Công dụng | Điều không được suy ra |
|---|---|---|
| `server.port: 8443` | Cổng embedded server HTTPS trong ví dụ | Không tự bật TLS nếu không có SSL material hợp lệ |
| `server.ssl.enabled: true` | Bật cấu hình TLS | Không thay việc phải cung cấp chứng chỉ và private key |
| `server.ssl.key-store` | Nơi đọc key/certificate trong keystore | Không phải truststore xác minh client |
| `server.ssl.key-store-type` | Kiểu keystore, như `PKCS12` | Không quyết định TLS version |
| `server.ssl.key-store-password` | Mật khẩu mở keystore | Không đặt hardcode trong repo production |
| `server.ssl.key-alias` | Alias entry key/certificate | Phải đúng với alias khi tạo keystore |
| `server.ssl.enabled-protocols` | Các version được phép | Không quyết định HTTP protocol version |
| `server.ssl.ciphers` | Các cipher suites có thể dùng | Không buộc chọn đúng suite đầu tiên trong mọi provider |
| `server.http2.enabled` | Cho server hỗ trợ HTTP/2 nếu runtime cho phép | Không tự bảo đảm TLS/cipher phù hợp hoặc client sẽ dùng h2 |

Trong ví dụ chỉ có một HTTPS connector trên cổng 8443. Spring Boot không tự tạo đồng thời một HTTP connector 8080 chỉ vì trước đây ứng dụng chạy HTTP. Muốn có cả HTTP→HTTPS redirect phải thiết kế thêm tại proxy hoặc cấu hình connector thích hợp theo server; không mong một property duy nhất tạo cả hai cổng.

**Điểm quan trọng cho production:** hardcode mật khẩu keystore trong YAML committed vào repository là không phù hợp. Cung cấp bằng secret manager, mounted secret, environment binding như `SERVER_SSL_KEY_STORE_PASSWORD` hoặc cấu hình bảo mật do nền tảng quản lý. File private key và keystore phải được phân quyền tối thiểu.

## 7. SSL bundles: cấu hình protocol và cipher đúng chỗ

Từ các phiên bản Spring Boot hỗ trợ SSL bundles, có thể gom key/trust material, options và tham chiếu bằng tên. Ví dụ với bundle tên `webserver`:

~~~yaml
spring:
  ssl:
    bundle:
      jks:
        webserver:
          key:
            alias: localtls
          keystore:
            location: classpath:local-tls.p12
            password: changeit
            type: PKCS12
          options:
            enabled-protocols:
              - TLSv1.3
              - TLSv1.2
            ciphers:
              - TLS_AES_128_GCM_SHA256
              - TLS_AES_256_GCM_SHA384
              - TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256
              - TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384

server:
  port: 8443
  ssl:
    bundle: webserver
  http2:
    enabled: true
~~~

**Không ghép hai kiểu cấu hình vào cùng một server.** Tài liệu Spring Boot nói rõ:
- Khi đặt `server.ssl.bundle`, không kết hợp với những lựa chọn rời rạc về keystore/PEM dưới `server.ssl`.
- `server.ssl.ciphers`, `server.ssl.enabled-protocols` và `server.ssl.protocol` **bị bỏ qua khi dùng bundle**.
- Đặt những lựa chọn đó tại `spring.ssl.bundle.<type>.<name>.options`, ví dụ `spring.ssl.bundle.jks.webserver.options.enabled-protocols`.

Đây là một nguyên nhân thực tế khiến đội vận hành “sửa allowed protocols rồi test lại vẫn thấy TLS cũ”: property được đặt ở sai tầng do có `server.ssl.bundle`.

### Bundle và quản lý certificate

- `spring.ssl.bundle.jks` hỗ trợ Java KeyStore (JKS, PKCS12).
- `spring.ssl.bundle.pem` hỗ trợ PEM certificate/private key.
- Bundle có thể được tham chiếu cho embedded server hoặc một số client/data technologies do Boot tích hợp.
- Có cơ chế reload SSL bundles trong các trường hợp và server tương thích, nhưng **đổi material/ciphers trên một bundle không có nghĩa mọi runtime tự hot-reload đầy đủ mọi TLS option**. Kiểm tra hỗ trợ cụ thể và tổ chức deploy/rollback rõ ràng.

Ví dụ dùng PEM, thay vì JKS, cho bundle:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          keystore:
            certificate: file:/etc/my-app/tls/fullchain.pem
            private-key: file:/etc/my-app/tls/privkey.pem
          options:
            enabled-protocols:
              - TLSv1.3
              - TLSv1.2

server:
  ssl:
    bundle: webserver
~~~

Đây là **fragment production**, giả định file và quyền đọc đã được cung cấp bởi hạ tầng. Không để `privkey.pem` trong public static resources hoặc repository. PEM private key có thể cần ở định dạng PKCS#8 tùy thư viện; kiểm tra tài liệu embedded server/Boot nếu material không load được.

## 8. Bài thực hành Java 17: HTTPS với TLS 1.2/1.3

Mục tiêu: tự chạy ứng dụng Spring Boot, tạo chứng chỉ self-signed cho local, kiểm tra TLS 1.2 và TLS 1.3 thành công, kiểm tra TLS cũ bị từ chối nếu client thử được, và xem HTTP/2 ALPN.

**Cần có:** JDK 17+, `keytool`, Gradle wrapper trong project Spring Boot, `curl` và tùy chọn `openssl`. Tạo dự án bằng Spring Initializr:
- Spring Boot 3.5.x, Java 17+, Gradle.
- Dependency **Spring Web**.
- Không cần Spring Security cho bài này.
- Dự án dùng embedded Tomcat mặc định của starter.

Trong một dự án Boot 3.5 đã có Gradle plugin/dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Đoạn trên chỉ là **dependency fragment**, không phải toàn bộ file `build.gradle`.

### 8.1. Tạo keystore PKCS12 tự ký cho localhost

Trong root project do Spring Initializr tạo (đã có thư mục `src/main/resources`), chạy:

~~~bash
keytool -genkeypair \
  -alias localtls \
  -keyalg RSA \
  -keysize 2048 \
  -sigalg SHA256withRSA \
  -validity 30 \
  -storetype PKCS12 \
  -keystore src/main/resources/local-tls.p12 \
  -storepass changeit \
  -keypass changeit \
  -dname "CN=localhost, OU=Learning, O=Demo, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"
~~~

Trong **Windows PowerShell**, multiline Bash dùng dấu backslash không phù hợp; chạy `keytool` trên **một dòng** với cùng flags hoặc dùng cú pháp continuation của PowerShell.

Các tham số:
- `-genkeypair`: tạo cặp khóa và chứng chỉ self-signed cho thử nghiệm.
- `-keyalg RSA -keysize 2048`: khóa RSA 2048-bit, phù hợp để minh họa suites ECDHE_RSA của TLS 1.2. Chọn loại/key size production theo policy CA và bảo mật hiện hành.
- `-sigalg SHA256withRSA`: thuật toán ký chứng chỉ demo.
- `-validity 30`: chứng chỉ demo có giá trị 30 ngày từ lúc tạo.
- `-storetype PKCS12`: keystore PKCS12.
- `-alias localtls`: phải khớp với `server.ssl.key-alias`.
- `-ext SAN=...`: đưa DNS `localhost` và IP `127.0.0.1` vào Subject Alternative Name để thử đúng hostname.

**Bảo mật:** file này chứa **private key** dù chỉ dùng demo; không commit lên Git hoặc gửi công khai. Mật khẩu `changeit` không thích hợp cho triển khai thật. **Self-signed** không nằm trong danh sách CA được browser/curl tin theo mặc định.

### 8.2. Class Java hoàn chỉnh

Tạo file `src/main/java/demo/tls/TlsDemoApplication.java`:

~~~java
package demo.tls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class TlsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TlsDemoApplication.class, args);
    }

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "hello tls";
    }
}
~~~

Đây là một class runnable hoàn chỉnh trong project Spring Boot đã tạo. Tạo file `src/main/resources/application.yml` với **cấu hình trực tiếp ở mục 6**. Không thêm đồng thời cấu hình SSL bundle ở mục 7.

### 8.3. Khởi động

Từ thư mục gốc dự án:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau khi console cho biết embedded server sẵn sàng, URL là:

~~~text
https://localhost:8443/hello
~~~

Không gọi `http://localhost:8443/hello`: cổng ví dụ đang nói TLS, nên HTTP plaintext thường bị đóng kết nối hoặc báo lỗi giao thức.

### 8.4. Test HTTPS với curl

~~~bash
curl -k -i https://localhost:8443/hello
~~~

**Phần response body kỳ vọng:**

~~~text
hello tls
~~~

Option `-k`/`--insecure` chỉ bỏ kiểm tra độ tin cậy chứng chỉ **trong bài thử local**. Nó không chứng minh certificate chain/trust/hostname production đúng; **không dùng `-k` trong client production**.

Kiểm tra khóa phiên bản bằng curl có hỗ trợ các tùy chọn tương ứng:

~~~bash
curl -k --tlsv1.3 --tls-max 1.3 -i https://localhost:8443/hello
curl -k --tlsv1.2 --tls-max 1.2 -i https://localhost:8443/hello
~~~

Với JDK/provider và curl hỗ trợ, cả hai request trên kỳ vọng hoàn thành handshake, trả HTTP 200 và body `hello tls`. `--tlsv1.2` ở curl là **tối thiểu TLS 1.2** trên nhiều phiên bản curl, vì vậy thêm `--tls-max 1.2` mới ép chính xác 1.2. Tương tự với TLS 1.3.

Muốn xem protocol và cipher thật được chọn:

~~~bash
curl -k -v --tlsv1.3 --tls-max 1.3 \
  https://localhost:8443/hello
~~~

`curl -v` có thể hiển thị handshake/version/cipher tùy TLS backend; không nên lấy output cụ thể ở một hệ điều hành làm chuẩn cho mọi curl.

### 8.5. Test qua OpenSSL s_client

Nếu máy đã có OpenSSL hỗ trợ TLS 1.2/1.3:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -tls1_3 \
  -ciphersuites TLS_AES_128_GCM_SHA256 \
  -brief
~~~

Để thử TLS 1.2 với một suite cụ thể, **OpenSSL dùng cách đặt tên khác JSSE ở một số lệnh**:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -tls1_2 \
  -cipher ECDHE-RSA-AES128-GCM-SHA256 \
  -brief
~~~

**Không nhầm** `-cipher` (cho TLS 1.2 và cũ hơn) với `-ciphersuites` (cho TLS 1.3) ở OpenSSL. Tên `ECDHE-RSA-AES128-GCM-SHA256` của OpenSSL tương ứng với tên JSSE `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256`.

Đầu ra `s_client` có thể báo certificate verify error vì **chứng chỉ self-signed của demo** chưa được trust; điều này khác với **handshake protocol/cipher không tương thích**. Nếu muốn xác minh certificate đúng cách, cung cấp CA/trust material phù hợp bằng `-CAfile` hoặc dùng một chứng chỉ hợp lệ; đừng coi `-k`/bỏ verify là bài test trust thành công.

### 8.6. Thử phiên bản TLS cũ

Với OpenSSL build còn cho phép thử TLS 1.1:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -tls1_1 \
  -brief
~~~

Server chỉ cho phép 1.2/1.3 nên **không được hoàn thành kết nối TLS 1.1**. Tuy nhiên nếu OpenSSL/JDK ở **phía client** đã vô hiệu hóa TLS 1.1, lệnh có thể thất bại ngay tại client trước khi server trả lời. Một lần lệnh không thành công **chưa đủ chứng minh** endpoint thực tế từ chối TLS 1.1: kiểm tra log, handshake trace hoặc scanner có khả năng gửi ClientHello legacy hợp lệ.

### 8.7. Test HTTP/2 qua ALPN

Ví dụ `application.yml` đã bật `server.http2.enabled=true`. Thử curl nếu bản curl hỗ trợ HTTP/2:

~~~bash
curl -k --http2 -v https://localhost:8443/hello
~~~

Tìm handshake ALPN chọn `h2` và HTTP response version tương ứng. `curl --http2` thường đưa h2 vào danh sách ứng dụng client hỗ trợ; nếu server/runtime không hỗ trợ hoặc negotiation chọn HTTP/1.1, cần kiểm tra config/ALPN. Không suy ra chỉ từ TLS 1.3 thành công mà HTTP/2 đã được bật.

Nếu `curl` báo không hỗ trợ `--http2`, bản curl cần build với HTTP/2; đây là giới hạn client test, không đủ chứng minh server không hỗ trợ.

## 9. Liên hệ TLS và HTTP/2: bộ cipher nào có thể gây lỗi?

HTTP/2 over TLS (`h2`) dùng **ALPN** để chọn giao thức application-layer. Theo **RFC 9113**:
- HTTP/2 over TLS yêu cầu **TLS 1.2 hoặc mới hơn**.
- Với TLS 1.2, có danh sách cipher suites **không được khuyến nghị sử dụng** (Appendix A), và endpoint có thể đóng kết nối với lỗi `INADEQUATE_SECURITY` khi thương lượng một suite không phù hợp.
- Triển khai HTTP/2 với TLS 1.2 **phải hỗ trợ** `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` và P-256 theo yêu cầu cụ thể trong chuẩn, nhằm tránh hai phía không có suite tương thích.
- TLS 1.3 có cơ chế khác và tuân các ràng buộc HTTP/2 tương ứng, ví dụ không sử dụng post-handshake TLS 1.3 `CertificateRequest`.

Đây là nguyên nhân cấu hình chỉ chọn một bộ cipher quá hẹp có thể gây ra hiện tượng HTTPS chạy với HTTP/1.1 nhưng HTTP/2 không hoạt động ở một số client. Không nên bật suites TLS 1.2 nằm trong nhóm prohibited chỉ để HTTP/2 “nhận” được connection.

### HTTP/2 có bắt buộc TLS 1.3?

**Không.** `h2` có thể hoạt động qua TLS 1.2 hoặc TLS 1.3, nhưng phải thỏa các điều kiện TLS/ALPN/cipher của HTTP/2. Spring Boot cũng có thể hỗ trợ `h2c` (HTTP/2 trên cleartext TCP) trong bối cảnh phù hợp, thường phía sau proxy, **không phải phương án thay thế mã hóa TLS ở public edge**.

### TLS termination ở proxy thay đổi vị trí kiểm soát

~~~text
Browser --TLS/ALPN--> CDN / LB / reverse proxy
                              |
                              +-- HTTP hoặc HTTPS / mTLS --> Spring Boot
~~~

Nếu TLS được kết thúc tại proxy:
- **Client-facing** TLS protocol/cipher policy nằm ở proxy/CDN/LB. Thay đổi `server.ssl.ciphers` trên Spring Boot **không thay cipher mà browser thương lượng với proxy**.
- Nếu proxy → Boot dùng HTTP plaintext trong mạng riêng, ứng dụng có thể không có embedded HTTPS connector. Cần đánh giá mô hình tin cậy mạng, tránh coi “nội bộ” tự động an toàn.
- Nếu proxy → Boot cũng dùng TLS, phải cấu hình **một hop TLS khác**, với chính sách riêng. Cipher và chứng chỉ ở hai hop có thể khác.
- `server.http2.enabled` của Boot chỉ điều khiển support ở embedded server; browser có dùng HTTP/2 với CDN còn tùy ALPN của CDN.

Trong production phải xác định **TLS endpoint thật** trước khi bắt đầu chỉnh YAML.

## 10. Khi không muốn tự định nghĩa cipher allowlist

Có hai chiến lược phổ biến:

**A. Dựa vào bộ mặc định được cập nhật của JDK/embedded server/provider**, đồng thời chủ động cho phép các TLS versions phù hợp và cập nhật runtime. Ưu điểm là kế thừa bản vá an toàn và khả năng tương thích mặc định. Rủi ro là policy có thể thay đổi khi nâng JDK/runtime, vì vậy cần CI scan để phát hiện thay đổi.

**B. Định nghĩa allowlist cipher rõ ràng** khi có quy định compliance hoặc yêu cầu tương thích chính xác. Ưu điểm là dự đoán được tập suites; nhược điểm là có thể vô tình loại bỏ cipher tốt mới, làm client mất kết nối sau nâng cấp hoặc tạo drift giữa các server.

**Không có một danh sách ngắn cố định tốt nhất cho mọi nơi.** Nếu không có yêu cầu chính sách đặc thù, thường hợp lý hơn khi bắt đầu từ cấu hình mặc định an toàn của runtime hiện hành rồi **đo tập phiên bản/suites được thương lượng**. Chỉ đóng đinh allowlist sau khi có inventory client và thử nghiệm thực tế.

### Việc kiểm tra định kỳ quan trọng hơn “đóng cứng rồi quên”

Dù không đổi YAML:
- JDK update có thể sửa `jdk.tls.disabledAlgorithms`.
- Tomcat/Jetty/Netty provider có thể thay tập default enabled suites.
- Load balancer/CDN có thể cập nhật TLS policy.
- Certificate có thể rotate từ RSA sang ECDSA, ảnh hưởng TLS 1.2 suites phù hợp.
- Client Java/OS/browser có thể ngừng hỗ trợ giao thức hoặc bộ cipher cũ.

Hãy version-control policy, ghi kết quả scan và thử các client quan trọng sau nâng cấp JDK/Boot/server/gateway.

## 11. Phân biệt khóa, certificate, truststore và TLS cipher policy

Đây là các mục có thể cấu hình cùng trong `server.ssl` nhưng nhiệm vụ khác nhau.

**Key store** chứa chứng chỉ server và private key dùng để xác thực server. Với keystore PKCS12 demo, `keytool -list` có thể giúp xác minh alias:

~~~bash
keytool -list -v \
  -storetype PKCS12 \
  -keystore src/main/resources/local-tls.p12 \
  -storepass changeit
~~~

Đầu ra thật sẽ có alias, certificate chain và chi tiết chứng chỉ phụ thuộc quá trình tạo. Không ghi private key ra console, không copy keystore production ra môi trường không an toàn.

**Trust store** chứa chứng chỉ/CA mà server dùng để xác minh peer theo cấu hình, ví dụ khi bật mTLS client authentication. Nó không tự quyết định cipher nào được chọn.

**Certificate SAN** phải khớp hostname mà client kết nối; cipher list hoàn toàn đúng vẫn có thể bị browser/curl từ chối vì certificate hostname mismatch, hết hạn hoặc self-signed. `curl -k` bỏ kiểm tra identity nên chỉ phục vụ thí nghiệm protocol/cipher, không chứng minh PKI deployment đúng.

### mTLS là một lựa chọn độc lập

Để yêu cầu client certificate ở một dịch vụ nội bộ, Spring Boot hỗ trợ `server.ssl.client-auth` (ví dụ `need`) cùng truststore/CA tin cậy. Tuy nhiên mTLS cần thiết kế về enrollment, revoke/rotate certificate, client identity mapping và trust boundaries. Chỉ thêm `client-auth: need` khi chưa có truststore phù hợp có thể khiến mọi client mất kết nối.

Việc chọn TLS 1.2/1.3 và cipher vẫn được thực hiện trong kết nối mTLS; client authentication **không thay thế** policy phiên bản/cipher an toàn.

## 12. Outbound TLS từ Spring Boot là bài toán khác

`server.ssl.*` cấu hình **kết nối inbound tới embedded server**. Nó **không tự động** quyết định TLS versions/ciphers cho mọi kết nối **outbound** do:
- `RestClient`/`RestTemplate` sử dụng HTTP client implementation nào đó.
- `WebClient`/Reactor Netty client.
- JDBC driver kết nối database qua TLS.
- Kafka, Redis, gRPC hoặc Java socket tự tạo.

Với outbound connections, TLS settings thuộc **client transport**, SSL context/bundle của client hoặc cấu hình driver. Khi client Java gọi API ngoài, JSSE `jdk.tls.client.protocols` có thể ảnh hưởng đến default client protocols trong những tình huống nhất định, nhưng đây không phải một nút cấu hình server và không áp dụng phổ quát cho mọi native TLS provider.

**Ví dụ sai đối tượng:** ứng dụng gọi partner API cũ gây `SSLHandshakeException` từ outbound WebClient. Thay `server.ssl.enabled-protocols` của embedded Tomcat sẽ không giải quyết connection tới partner. Cần xem đúng TLS endpoint, client transport, certificate chain và policy chiều outbound.

Tương tự, `management.server.ssl.*` có thể áp dụng khi Actuator chạy trên cổng quản trị riêng; không tự giả định cổng management dùng cùng chính sách với traffic công khai nếu đã cấu hình tách biệt.

## 13. Kiểm tra hỗ trợ cipher bằng JDK JSSE, không đoán

Một JDK có thể có:
- **Supported cipher suites**: provider có thể triển khai.
- **Default enabled cipher suites**: tập được bật theo mặc định trong context tương ứng.
- **Application-configured** suites: tập ứng dụng/server muốn bật.
- **Actually negotiated** suite: kết quả chỉ có **một** suite cụ thể sau handshake.

Đây là bốn tập thông tin khác nhau.

### Ví dụ Java 17 chạy độc lập để xem JSSE

Lưu tại file `JsseCapabilities.java`:

~~~java
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class JsseCapabilities {
    public static void main(String[] args) throws Exception {
        SSLContext context = SSLContext.getDefault();
        SSLParameters supported = context.getSupportedSSLParameters();
        SSLParameters defaults = context.getDefaultSSLParameters();

        System.out.println("Supported protocols:");
        Arrays.stream(supported.getProtocols()).sorted()
                .forEach(System.out::println);

        System.out.println("Default enabled protocols:");
        Arrays.stream(defaults.getProtocols()).sorted()
                .forEach(System.out::println);

        System.out.println("Default enabled cipher suites:");
        Arrays.stream(defaults.getCipherSuites()).sorted()
                .forEach(System.out::println);
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac JsseCapabilities.java
java JsseCapabilities
~~~

Stdout **không có danh sách cố định** vì phụ thuộc JDK vendor, version, provider, policy bảo mật và cấu hình runtime. Ba nhãn đầu ra chính xác sẽ là:

~~~text
Supported protocols:
...
Default enabled protocols:
...
Default enabled cipher suites:
...
~~~

Dấu `...` chỉ đại diện cho các dòng do JVM in ra, không phải một dòng bắt buộc. Kiểm tra sự tồn tại của `TLSv1.3`, `TLSv1.2` và các suite mong muốn trong danh sách thật; **đừng coi việc Java có hỗ trợ một cipher là bằng chứng embedded server đang quảng cáo cipher đó**. Để biết endpoint thật, vẫn phải dùng kiểm thử TLS handshake trên cổng triển khai.

### Vì sao một suite có tên trong JSSE nhưng không bắt được handshake?

Có thể suite bị loại bởi:
- `jdk.tls.disabledAlgorithms`.
- Version không tương thích.
- Certificate key/signature scheme không tương thích.
- Provider/engine thực tế là OpenSSL/native, không dùng JSSE mặc định.
- Các policy bổ sung của embedded server.
- Client offer không bao gồm suite đó.

Vì vậy cần kết hợp **inventory runtime** và **network handshake tests**.

## 14. Quan sát handshake và đo rủi ro khi chỉnh policy

Không nên mở debug TLS chi tiết tràn lan trên production. Với môi trường test, JSSE có cơ chế debug:

~~~bash
java -Djavax.net.debug=ssl,handshake -jar app.jar
~~~

`app.jar` là tên đại diện; dùng tên JAR build thật. Log handshake có thể chứa nhiều thông tin kết nối, certificate, metadata nhạy cảm; chỉ sử dụng trong môi trường test và tắt sau khi thu đủ bằng chứng. Nếu runtime sử dụng native TLS provider, flag JSSE có thể không phản ánh toàn bộ handshake của native engine.

Ngoài log, nên quan sát:
- Tỷ lệ handshake thành công/thất bại tại **TLS terminator**.
- TLS version distribution và cipher suite negotiated distribution.
- Lỗi certificate trust/hostname mismatch, không có shared cipher và sai protocol version.
- HTTP version thương lượng qua ALPN: h2 hay http/1.1.
- Latency TLS handshake, session resumption, CPU crypto và resource usage.
- Nhóm client/user-agent/SDK bị ảnh hưởng khi rollout chính sách.

Không gắn session secret, certificate private material hoặc personal identifiers vào metric labels. Nếu cần theo dõi client compatibility, gom nhóm theo protocol/cipher/client SDK version hoặc những dimension đủ nhỏ, có chính sách riêng tư phù hợp.

### A/B policy thực tế

Giả sử cấu hình cũ cho phép TLS 1.2/1.3 với bộ cipher do JDK chọn. Bạn muốn khóa TLS 1.2 vào ECDHE_RSA AES-GCM và giữ TLS 1.3:

1. Ghi baseline handshake success theo client version và tỷ lệ TLSv1.2/TLSv1.3.
2. Lập danh sách hệ thống bên ngoài, mobile apps, SDK Java, bots hợp lệ, health probes và monitoring agents.
3. Kiểm thử với đủ hệ điều hành/runtime, kể cả client không hỗ trợ AES-GCM hoặc chưa hỗ trợ TLS 1.3.
4. Test trên canary hoặc một pool endpoint riêng; không làm đứt toàn bộ kết nối public ngay.
5. Kiểm tra cả HTTPS **và** HTTP/2/h2 ALPN.
6. Theo dõi handshake errors; nếu cần, rollback bằng việc đảo lại policy của chính **TLS endpoint đang active**.
7. Chốt tài liệu bao gồm certificate type, key rotation, JDK/provider, client inventory và ngày sunset protocol cũ.

Mục tiêu là **bảo mật và khả năng phục vụ có kiểm chứng**, không phải chỉ đạt “điểm A” từ một scanner rồi bỏ mặc client bị lỗi.

## 15. Các lỗi thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| `SSLHandshakeException: handshake_failure` | Không có suite/version compatible, certificate/signature hoặc group không phù hợp | Dùng `openssl s_client`, JSSE debug, kiểm tra cả certificate và client offer |
| `protocol_version` | Client chỉ hỗ trợ phiên bản bị từ chối | Kiểm tra enabled protocols của hai phía; nâng cấp client |
| `no cipher suites in common` | Allowlist quá hẹp, sai certificate type hoặc provider không hỗ trợ | So sánh suites theo TLS version, RSA/ECDSA, JDK/provider |
| `wrong version number` khi gọi HTTPS | Client gửi HTTP plaintext tới cổng TLS, proxy chuyển sai scheme hoặc dùng port sai | Xác minh URL, port, proxy hop, SSL termination |
| `curl: SSL certificate problem` | Self-signed/CA không được tin, hostname hoặc chain không đúng | Dùng trust material hợp lệ; `-k` chỉ cho test local |
| TLS 1.3 thành công nhưng TLS 1.2 lỗi | List chỉ có TLS 1.3 ciphers hoặc TLS 1.2/certificate mismatch | Thêm suite TLS 1.2 AEAD phù hợp nếu policy cần fallback |
| TLS 1.2 thành công nhưng TLS 1.3 lỗi | Provider/JDK/version/ciphers không hỗ trợ TLS 1.3 | Kiểm tra runtime, `enabled-protocols` và suite TLS 1.3 |
| Chỉnh `server.ssl.ciphers` mà scan không đổi | Đang dùng `server.ssl.bundle`, TLS termination ngoài Boot hoặc sửa sai instance | Xem bundle options, proxy/LB/CDN, deployed config thực tế |
| HTTPS OK nhưng `curl --http2` không dùng h2 | ALPN không chọn h2, server không bật HTTP/2 hoặc TLS 1.2 cipher không phù hợp | Kiểm tra `server.http2.enabled`, provider/server, HTTP/2 dependencies, ALPN trace |
| HTTP/2 kết nối bị `INADEQUATE_SECURITY` | TLS 1.2 đã thương lượng suite thuộc nhóm bị hạn chế | Dùng suite phù hợp RFC 9113 và kiểm tra policy |
| Chỉ HTTPS chạy, HTTP 8080 không hoạt động | Ứng dụng chỉ bật một connector ở 8443 | Tạo redirect ở proxy hoặc cấu hình connector có chủ đích |
| Local keytool keystore không load được | Alias/path/password/type khác thực tế | `keytool -list`, kiểm tra file trong artifact và quyền |
| JAR chạy được local nhưng container lỗi | Không có secret/cert hoặc đường dẫn `file:` khác container | Kiểm tra mount, filesystem permissions và env binding |
| Scanner chỉ thấy cipher của CDN | TLS đã được terminate ở CDN | Scan origin riêng trong môi trường được phép nếu cần; phân biệt từng hop |
| mTLS làm tất cả client lỗi | Client-auth `need` nhưng client không có cert/trust chain | Kiểm tra truststore, client cert và CA |
| OpenSSL `-cipher` không ép được TLS 1.3 | Sai flag | TLS1.3 dùng `-ciphersuites`, TLS1.2 dùng `-cipher` |
| TLS 1.1 test thất bại ngay ở client | Client tool đã tắt TLS 1.1 | Phân biệt “client không thử được” với “server từ chối” |

**Một lỗi tên property đáng lưu ý:** dùng `TLS1.3`, `TLSv1.3` và `TLSv1_3` tùy tiện. Trong JSSE/Spring Boot cấu hình giao thức, tên thường dùng là **`TLSv1.3`** và **`TLSv1.2`**. Sai tên có thể khiến startup/handshake lỗi tùy provider.

## 16. Checklist bảo mật trước khi cho phép cấu hình mới

- [ ] Xác định chính xác TLS terminator mà client kết nối: Spring Boot hay proxy/CDN/LB.
- [ ] Đã chọn TLS 1.3 và TLS 1.2 (hoặc TLS1.3-only dựa trên inventory client), không bật TLS 1.0/1.1.
- [ ] TLS 1.3 suites và TLS 1.2 suites không bị nhầm tên/phiên bản.
- [ ] TLS 1.2 suites ưu tiên ECDHE + AEAD; không bật legacy RSA key exchange/RC4/3DES/NULL/CBC yếu.
- [ ] Certificate RSA/ECDSA, SAN, key size, CA chain và expiration phù hợp.
- [ ] Đã xét `jdk.tls.disabledAlgorithms`, JDK/provider, embedded server và native TLS engine.
- [ ] Nếu dùng SSL bundle, cấu hình options trong bundle chứ không nhầm với `server.ssl.ciphers` bị bỏ qua.
- [ ] Nếu bật HTTP/2, kiểm tra ALPN h2 và yêu cầu TLS 1.2 cipher của RFC 9113.
- [ ] HTTPS client xác thực CA/hostname; không dùng `-k` hoặc trust-all trong production.
- [ ] Private key/keystore password được bảo vệ, không commit vào repo.
- [ ] Kiểm thử TLSv1.3, TLSv1.2, từ chối TLS legacy, một số cipher allowed/disallowed và client thật.
- [ ] Kiểm thử sau proxy/CDN và trên cả backend hop nếu backend có TLS.
- [ ] Có telemetry handshake failure và rollback plan, rollout canary.
- [ ] Có lộ trình cập nhật JDK/Boot và rà lại policy định kỳ.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `server.ssl.protocol: TLS` có tương đương `server.ssl.enabled-protocols: [TLSv1.3, TLSv1.2]` không?

**Đáp án:** Không. `protocol` dùng cho SSL context/implementation, còn `enabled-protocols` chỉ định các TLS protocol versions được phép.

**Câu 2.** Tại sao `TLS_AES_128_GCM_SHA256` không thể thay cho `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` trong cấu hình TLS 1.2?

**Đáp án:** Suite đầu là TLS 1.3, suite sau là TLS 1.2. TLS 1.3 tách key exchange/auth khỏi cipher suite; hai tên không thay thế lẫn nhau giữa các phiên bản.

**Câu 3.** Có thể bật HTTP/2 over TLS mà chỉ cho TLS 1.2 không?

**Đáp án:** Có, nếu đáp ứng ALPN và các yêu cầu TLS 1.2 của HTTP/2. TLS 1.3 rất nên hỗ trợ khi các client phù hợp, nhưng h2 không yêu cầu bắt buộc TLS 1.3.

**Câu 4.** Đã đặt `server.ssl.bundle: webserver` và `server.ssl.ciphers` nhưng scan endpoint không đổi. Khả năng lớn nhất là gì?

**Đáp án:** Khi dùng bundle, các setting trực tiếp `server.ssl.ciphers`/`enabled-protocols`/`protocol` bị bỏ qua; cần đặt vào `spring.ssl.bundle.jks.webserver.options` hoặc bundle type tương ứng, đồng thời xác minh TLS terminator thực tế.

**Câu 5.** Vì sao một cert ECDSA có thể không thương lượng được suite `TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256` ở TLS 1.2?

**Đáp án:** Bộ suite đó đòi khả năng xác thực RSA; chứng chỉ ECDSA có thể không phù hợp. Chọn suite hỗ trợ loại certificate thực tế và client tương ứng.

**Câu 6.** Có thể dùng `curl -k` để kết luận chứng chỉ production đúng danh tính không?

**Đáp án:** Không. `-k` bỏ kiểm tra chứng chỉ. Chỉ dùng cho local self-signed demo; production cần kiểm tra CA, SAN, chain, expiration đúng nghĩa.

**Câu 7.** Nếu browser kết nối CDN qua TLS 1.0, sửa `server.ssl.enabled-protocols` ở Boot origin có giúp chặn không?

**Đáp án:** Không nếu TLS client-facing kết thúc tại CDN. Phải đổi TLS policy ở CDN; origin Boot chỉ kiểm soát hop mà nó là TLS endpoint.

**Câu 8.** Khi TLS 1.1 handshake test thất bại, có đủ bằng chứng server đã từ chối TLS 1.1 không?

**Đáp án:** Chưa hẳn. OpenSSL/curl client có thể chặn TLS 1.1 ngay ở phía client. Cần công cụ có khả năng phát TLS 1.1 ClientHello hợp lệ hoặc quan sát server handshake để xác minh.

**Bài tập mở rộng:** Từ ví dụ mục 8, thử chuyển `enabled-protocols` thành chỉ `TLSv1.3` trên môi trường test, rồi chạy kiểm tra TLSv1.3 và TLSv1.2 bắt buộc. Ghi lại lỗi chính xác và giải thích vì sao request lỗi không vào controller. Sau đó trả lại policy ban đầu, thử chuyển sang SSL bundle mục 7 và chỉ đặt versions/ciphers dưới `spring.ssl.bundle.jks.webserver.options`. Cuối cùng test HTTP/2 và so sánh việc chọn protocol qua ALPN với việc chọn TLS version.

## 18. Nguồn tham khảo

- [Spring Boot 3.5 — Common Application Properties (`server.ssl.*`)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Boot 3.5 — Embedded Web Servers: SSL, SSL bundles và HTTP/2](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot — SSL bundles (JKS/PKCS12/PEM)](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Oracle Java 17 — Transport Layer Security Protocol Overview](https://docs.oracle.com/en/java/javase/17/security/transport-layer-security-tls-protocol-overview.html)
- [Oracle Java 17 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html)
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 9325 — Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325)
- [RFC 9113 — HTTP/2, `9.2` và Appendix A về TLS/cipher suites](https://www.rfc-editor.org/rfc/rfc9113.html)

**Ghi nhớ:** chọn **TLS versions**, **cipher suites**, **certificate/key** và **HTTP/2 ALPN** là bốn quyết định liên quan nhưng khác nhau. Một YAML đúng cú pháp chưa đủ: policy chỉ thật sự có giá trị khi được áp dụng tại **TLS endpoint thực tế** và xác minh bằng handshake của những client mà dịch vụ cần hỗ trợ.
