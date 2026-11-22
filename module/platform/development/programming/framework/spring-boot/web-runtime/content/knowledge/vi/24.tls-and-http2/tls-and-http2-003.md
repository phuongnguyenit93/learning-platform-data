# SSL bundle và cấu hình vật liệu tin cậy dùng chung trong Spring Boot

## 1. Bài toán: TLS có nhiều kết nối nhưng không nên cấu hình chứng chỉ rải rác

Một ứng dụng Spring Boot có thể đóng hai vai trò cùng lúc:

- **TLS server:** nhận kết nối HTTPS từ trình duyệt, API client, gateway hoặc một service khác.
- **TLS client:** gọi các dịch vụ downstream qua `RestClient`, `WebClient`, kết nối database, message broker hoặc một giao thức TLS khác.

Nếu mỗi thư viện lại đọc một file chứng chỉ theo đường dẫn riêng, tự tạo `SSLContext` hay cấu hình truststore bằng system property toàn JVM, ứng dụng sẽ khó xoay vòng chứng chỉ, khó kiểm thử và dễ xảy ra lỗi “client A tin CA này nhưng client B không tin”.

Từ **Spring Boot 3.1**, cơ chế **SSL bundles** cho phép khai báo **bộ vật liệu khóa/tin cậy có tên** thông qua `spring.ssl.bundle.*`, rồi tham chiếu tên bundle ở thành phần hỗ trợ. Một bundle có thể chứa key material, trust material và các lựa chọn TLS; ứng dụng không cần sao chép đường dẫn và password tại mọi nơi.

Ví dụ khái niệm:

```text
                    Spring Boot configuration
                  spring.ssl.bundle.jks.* / pem.*
                              │
                  ┌───────────┴──────────────┐
                  │                          │
        local-server bundle            partner-trust bundle
        [certificate + key]             [CA / truststore]
                  │                          │
          server.ssl.bundle        ┌─────────┴────────────┐
                  │                │                      │
           Embedded Tomcat    RestClientSsl          WebClientSsl
             HTTPS :8443          │                      │
                  │         HTTPS tới partner      HTTPS tới partner
                  │                │                      │
             Browser/client       Kiểm tra chuỗi cert + hostname
```

**Điểm cốt lõi:** cùng một **bundle được khai báo một lần** có thể được **nhiều consumer tham chiếu** khi consumer đó hỗ trợ API bundle. Nhưng việc khai báo một bundle **không tự động làm mọi TLS client dùng bundle ấy**; mỗi consumer cần được gắn cấu hình phù hợp.

Bài dùng API và property theo **Spring Boot 3.3.13 / Java 17+** để ví dụ đồng nhất và dễ kiểm chứng. Với sản phẩm đang chạy, hãy dùng phiên bản Spring Boot còn được hỗ trợ và cập nhật bản vá; package API có thể đổi ở các major version mới.

## 2. Thuật ngữ cần hiểu trước khi cấu hình

| Khái niệm | Mục đích | Thường dùng ở đâu |
|---|---|---|
| **TLS** | Xác thực peer, mã hóa và bảo vệ tính toàn vẹn traffic | HTTPS, TLS tới DB/broker |
| **Certificate (X.509)** | Chứa public key, subject/SAN, issuer, thời hạn và chữ ký CA | Server gửi cho client trong TLS handshake |
| **Private key** | Chứng minh quyền sở hữu certificate/public key tương ứng | Bên sở hữu identity, cần bảo mật nghiêm ngặt |
| **CA / trust anchor** | Cơ sở để chấp nhận chuỗi chứng chỉ của peer | Truststore trên client hoặc server mTLS |
| **Keystore** | Lưu identity/key material: certificate chain + private key (hoặc nhiều entry) | HTTPS server, mTLS client |
| **Truststore** | Lưu certificate/CA mà chương trình chấp nhận khi xác thực peer | HTTPS client; server khi yêu cầu client certificate |
| **SAN (Subject Alternative Name)** | Tên DNS/IP mà certificate được phép đại diện | Kiểm tra hostname của HTTPS client |
| **mTLS (mutual TLS)** | Hai phía đều chứng minh identity bằng certificate | Service-to-service, private APIs |
| **ALPN** | Thỏa thuận protocol ứng dụng trên TLS handshake | HTTP/2 `h2` và HTTP/1.1 |
| **SSL bundle** | Container logic tên riêng cho key/trust/options do Spring Boot quản lý | Server, client và integrations hỗ trợ |

**Key ≠ trust:** certificate/private key của ứng dụng để **chứng minh mình là ai**, còn certificate CA/truststore để **quyết định tin ai**. Một SSL bundle có thể chỉ chứa truststore (client tin CA), chỉ chứa keystore (server xuất trình identity) hoặc cả hai (mTLS). Việc chỉ có keystore không có nghĩa ứng dụng đã tin mọi CA khác.

**“SSL” trong tên API là tên lịch sử**, nhưng giao thức cần sử dụng là TLS hiện đại. Không bật SSLv3/TLSv1.0/TLSv1.1 cho production và không tắt xác minh hostname để xử lý lỗi certificate.

## 3. Cấu trúc API SSL bundle của Spring Boot

Spring Boot auto-configure một bean `org.springframework.boot.ssl.SslBundles` để tra các bundle có tên được định nghĩa bằng properties. Truy xuất:

```java
import javax.net.ssl.SSLContext;

import org.springframework.boot.ssl.SslBundle;
import org.springframework.boot.ssl.SslBundles;

// Ví dụ nằm trong constructor hoặc method được Spring inject SslBundles.
SslBundle bundle = sslBundles.getBundle("partner-trust");
SSLContext context = bundle.createSslContext();
```

Đây là **mảnh code minh họa**, cần một biến/parameter `SslBundles sslBundles` và phạm vi class/method thực tế.

Các lớp/khả năng quan trọng:

- `SslBundles.getBundle(name)`: lấy bundle theo tên; nếu tên không tồn tại, lỗi cấu hình sẽ được báo. Tên phải khớp với tên đăng ký (lưu ý quy tắc xử lý tên khi dùng env vars).
- `SslBundle.getStores()`: nhận `SslStoreBundle` với keystore/truststore Java `KeyStore` và một số thông tin liên quan.
- `SslBundle.getManagers()`: truy cập key/trust manager factories và manager arrays.
- `SslBundle.createSslContext()`: tạo `javax.net.ssl.SSLContext` tiện dụng cho client libraries cần JSSE context.
- `SslBundle.getOptions()` và `getProtocol()`: tham chiếu lựa chọn TLS của bundle; không nên giả định mọi consumer đều hỗ trợ tất cả option.
- `SslBundle.getKey()`: thông tin key alias/password theo bundle.

Bundle là **cấu hình được đặt tên và quản lý**, không phải “chứng chỉ toàn cục cho JVM”. Consumer cụ thể vẫn phải hỗ trợ và áp dụng nó. Việc tự tạo một `SSLContext` rồi bỏ đi cũng không làm WebClient/RestClient tự dùng context đó.

## 4. Hai định dạng phổ biến: JKS/PKCS12 và PEM

### 4.1. JKS hoặc PKCS12

Với Java KeyStore, prefix là:

```properties
spring.ssl.bundle.jks.<tên-bundle>.keystore.location=...
spring.ssl.bundle.jks.<tên-bundle>.keystore.password=...
spring.ssl.bundle.jks.<tên-bundle>.keystore.type=PKCS12
spring.ssl.bundle.jks.<tên-bundle>.key.alias=...
spring.ssl.bundle.jks.<tên-bundle>.truststore.location=...
spring.ssl.bundle.jks.<tên-bundle>.truststore.password=...
spring.ssl.bundle.jks.<tên-bundle>.truststore.type=PKCS12
```

Phần `<tên-bundle>` trong block trên là ký hiệu cú pháp, phải thay bằng tên thật (ví dụ `local-server`, `partner-trust`), **không thể dán nguyên khối để chạy**. Một bundle không bắt buộc phải có cả keystore lẫn truststore.

- `keystore` có thể chứa private key và certificate chain của service.
- `truststore` chứa certificate/CA dùng để xác thực phía bên kia.
- `type=PKCS12` nên khai báo khi file là `.p12`/`.pfx`; JKS dùng type `JKS` nếu có nhu cầu.
- `key.alias` hữu ích nếu keystore có nhiều key entries.
- Nếu key password khác keystore password, cấu hình thêm key password theo API tương ứng; đừng giả định hai password luôn trùng.

**PKCS12 và JKS là container binary**, không phải tên giao thức mạng hay thuật toán ký chứng chỉ. Java `keytool` có thể tạo/kiểm tra các container này.

### 4.2. PEM: certificate và private key ở dạng text

Đối với file PEM, prefix là:

```properties
# Identity của ứng dụng (để xuất trình khi TLS handshake).
spring.ssl.bundle.pem.local-server.keystore.certificate=file:/etc/tls/server-chain.crt
spring.ssl.bundle.pem.local-server.keystore.private-key=file:/etc/tls/server.key

# Cơ sở tin cậy của một downstream (không chứa private key).
spring.ssl.bundle.pem.partner-trust.truststore.certificate=file:/etc/tls/partner-ca.pem
```

Ở đây `local-server` và `partner-trust` là **hai bundle độc lập**. File certificate server thông thường cần chứa leaf certificate và chain cần gửi cho peer theo yêu cầu; file trust certificate chứa CA/chứng chỉ được tin. Không sử dụng private key của đối tác như một phần truststore.

Spring Boot 3.3 có thể đọc PEM theo resource location (`classpath:`, `file:`), dữ liệu `base64:` hoặc nội dung PEM trực tiếp theo contract property. Với private key PEM, ưu tiên **PKCS#8** (`BEGIN PRIVATE KEY` hoặc dạng PKCS#8 được mã hóa phù hợp). Không copy private key nguyên văn vào source code, Git, log hoặc ticket.

**Environment variables:** khi định nghĩa bundle qua biến môi trường, tên bundle được Spring Boot chuyển thành chữ thường. Nên dùng tên ASCII chữ thường, ngắn và nhất quán, ví dụ `partnertrust` hoặc `partner-trust`, tránh phụ thuộc phân biệt chữ hoa.

### 4.3. Chọn cấu hình nào?

| Tình huống | Cách phù hợp |
|---|---|
| Java application có file `.p12` do CA/công cụ cấp | `spring.ssl.bundle.jks.*` |
| Kubernetes Secret mount certificate/key PEM | `spring.ssl.bundle.pem.*` |
| Client chỉ tin internal CA | Bundle chỉ có truststore |
| Server chỉ cần HTTPS với certificate của chính mình | Bundle có keystore |
| mTLS client | Bundle có cả client identity và trust material của server |
| TLS server yêu cầu certificate client | Bundle server có identity và trust material CA cấp client cert; bật client auth |
| Nhiều HTTP clients cùng gọi cùng một nhóm CA | Nhiều clients tham chiếu **cùng tên trust bundle** |

Không sử dụng một truststore “tin mọi certificate” để khỏi cấu hình CA, đặc biệt tránh trust-all `TrustManager` và hostname verifier luôn trả `true`.

## 5. Dùng bundle cho HTTPS server và HTTP/2

Để server nhúng mở HTTPS trên cổng 8443 với bundle `local-server`:

```properties
server.port=8443
server.ssl.bundle=local-server
server.http2.enabled=true
```

Trong Spring Boot 3.3, `server.ssl.bundle` tham chiếu SSL bundle được khai báo sẵn, ví dụ `spring.ssl.bundle.jks.local-server.keystore.*`. Boot chuyển cấu hình sang Tomcat/Jetty/Undertow/Reactor Netty tùy stack và embedded server thực sự sử dụng.

**Quy tắc quan trọng:**

- **Không kết hợp** `server.ssl.bundle` với các thuộc tính **keystore/PEM rời** khác dưới `server.ssl` (như `server.ssl.key-store` hoặc `server.ssl.certificate`). Chỉ dùng một nguồn identity đúng contract.
- Khi dùng bundle, các property `server.ssl.ciphers`, `server.ssl.enabled-protocols` và `server.ssl.protocol` **bị bỏ qua**; đặt các lựa chọn này ở `spring.ssl.bundle.<type>.<name>.options.*` nếu consumer hỗ trợ.
- `server.ssl.client-auth` vẫn liên quan tới việc có bắt buộc nhận certificate từ client hay không. Nếu bật `need`, phải cấu hình trust material cho server và client cần xuất trình chứng chỉ hợp lệ.
- `server.port=8443` giờ là **HTTPS**, không đồng thời tự mở một cổng HTTP thuần ở 8080. Muốn có cả hai connector phải cấu hình thêm bằng code hoặc đặt reverse proxy/ingress phù hợp.
- Nếu TLS termination ở load balancer/ingress, kết nối HTTP trong container có thể là HTTP/1.1 hay h2c. Đừng kết luận “client dùng HTTP/2 tới Spring Boot” chỉ từ `server.http2.enabled=true` nếu TLS kết thúc ở proxy.

**HTTP/2 không phải certificate format.** Với `server.http2.enabled=true` và SSL ở server, Spring Boot hỗ trợ `h2` trên TLS qua ALPN khi embedded server và client đàm phán thành công. Nếu không bật SSL, `h2c` là dạng HTTP/2 không dùng TLS trong các cấu hình/server hỗ trợ. Một client có thể vẫn đàm phán HTTP/1.1 dù server cho phép HTTP/2; cần kiểm tra giao thức đã negotiated thực tế.

## 6. Ví dụ chạy được: tạo local certificate, khai báo hai bundle và tái sử dụng trust

Ví dụ này dùng **Spring Boot 3.3.13, Java 17+, Gradle**, tạo HTTPS server bằng Tomcat và hai HTTP clients cùng tin **một trust bundle**: `RestClient` (blocking) và `WebClient` (reactive). App demo gọi **chính server local** để bạn quan sát được hai client dùng chung certificate trust policy mà không cần network ngoài.

Lưu ý: certificate tự ký và password `changeit` ở đây **chỉ phục vụ local/demo**. Không đưa key/cert/password demo vào production, không commit keystore private key vào repository.

### 6.1. Cấu trúc project

```text
ssl-bundle-demo/
├── build.gradle
├── certs/
│   ├── server.p12           # Sinh bằng keytool tại local, không commit.
│   ├── server.crt           # Public certificate của local server.
│   └── truststore.p12       # Public certificate được import để tin server.
└── src/main/
    ├── java/com/example/sslbundle/SslBundleApplication.java
    └── resources/application.properties
```

Trong thực tế nên thêm `certs/*.p12` và `certs/*.key` vào `.gitignore`. Certificate public không phải secret nhưng vẫn cần quản trị vòng đời; private key/password mới là thông tin tối mật.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao có cả hai starters?** Ví dụ chủ ý minh họa RestClient và WebClient trong cùng app. Khi có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot 3.3 thường chọn **Servlet/MVC + Tomcat** làm web server, còn `WebClient` vẫn dùng được để gọi downstream. Đây **không phải** server WebFlux tự động được kích hoạt.

### 6.2. Sinh cert và truststore local bằng keytool

Từ thư mục gốc project (có JDK 17+ và `keytool`), tạo thư mục `certs` rồi thực hiện ba lệnh **trên một máy phát triển**:

```bash
mkdir -p certs

keytool -genkeypair \
  -alias local-server \
  -keyalg RSA -keysize 3072 \
  -validity 30 \
  -storetype PKCS12 \
  -keystore certs/server.p12 \
  -storepass changeit -keypass changeit \
  -dname "CN=localhost, OU=Learning, O=Demo, C=VN" \
  -ext "SAN=dns:localhost,ip:127.0.0.1"

keytool -exportcert \
  -alias local-server \
  -keystore certs/server.p12 \
  -storetype PKCS12 -storepass changeit \
  -rfc -file certs/server.crt

keytool -importcert \
  -alias local-server \
  -file certs/server.crt \
  -keystore certs/truststore.p12 \
  -storetype PKCS12 -storepass changeit \
  -noprompt
```

- `server.p12` lưu **private key và certificate** của HTTPS server.
- `server.crt` là public certificate xuất ra để client có thể kiểm tra/đặt trust anchor trong ví dụ local.
- `truststore.p12` lưu public certificate đã được tin. **Nó không cần chứa server private key.**
- `SAN=dns:localhost,ip:127.0.0.1` giúp certificate khớp với host local. Nếu chỉ ghi CN mà không có SAN thích hợp, client hiện đại có thể báo hostname mismatch.
- `-validity 30` chỉ tạo chứng chỉ tồn tại 30 ngày cho demo; sau thời hạn đó phải tạo lại.

Lệnh ở trên dùng shell kiểu Bash; trên Windows PowerShell, hãy chạy từng lệnh `keytool` trên một dòng hoặc đổi ký tự nối dòng theo PowerShell. `mkdir -p` chỉ là cách tạo thư mục trong Bash; PowerShell có thể dùng `New-Item -ItemType Directory -Force certs`.

**Không dùng certificate tự ký này làm root CA chung của công ty.** Production thường dùng CA được quản lý, certificate chain hợp lệ, private key được bảo vệ và cơ chế rotate định kỳ.

### 6.3. Định nghĩa bundle cho server và trust bundle dùng chung

**`src/main/resources/application.properties`:**

```properties
# HTTPS server (identity):
server.port=8443
server.ssl.bundle=local-server
server.http2.enabled=true

spring.ssl.bundle.jks.local-server.keystore.location=file:./certs/server.p12
spring.ssl.bundle.jks.local-server.keystore.type=PKCS12
spring.ssl.bundle.jks.local-server.keystore.password=${LOCAL_SERVER_STORE_PASSWORD:changeit}
spring.ssl.bundle.jks.local-server.key.alias=local-server

# MỘT trust bundle dùng lại cho nhiều HTTP clients:
spring.ssl.bundle.jks.local-trust.truststore.location=file:./certs/truststore.p12
spring.ssl.bundle.jks.local-trust.truststore.type=PKCS12
spring.ssl.bundle.jks.local-trust.truststore.password=${LOCAL_TRUST_STORE_PASSWORD:changeit}
```

Trong Spring properties, cú pháp `${LOCAL_SERVER_STORE_PASSWORD:changeit}` có nghĩa: lấy environment variable khi có, không thì dùng password demo `changeit`. Trong production phải **bỏ fallback secret** và dùng secret store/file mount/credential manager thích hợp. Đường dẫn `file:./certs/...` là đường dẫn tương đối theo working directory của process; khi chạy jar trong container, đường dẫn này có thể khác. Nếu muốn ổn định ở production hãy dùng đường dẫn tuyệt đối từ mount secret.

Bundle tên `local-server` dùng **keystore** và được tham chiếu bởi `server.ssl.bundle`. Bundle tên `local-trust` dùng **truststore**, được tái sử dụng ở nhiều HTTP clients. Các thuộc tính trên không dùng `server.ssl.key-store` rời.

### 6.4. Mã Java 17+ dùng RestClientSsl và WebClientSsl

**`src/main/java/com/example/sslbundle/SslBundleApplication.java`:**

```java
package com.example.sslbundle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class SslBundleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SslBundleApplication.class, args);
    }
}

@Service
class LocalTlsClients {
    private final RestClient blockingClient;
    private final WebClient reactiveClient;

    LocalTlsClients(RestClient.Builder restBuilder, RestClientSsl restSsl,
                    WebClient.Builder webBuilder, WebClientSsl webSsl) {

        this.blockingClient = restBuilder
                .baseUrl("https://localhost:8443")
                .apply(restSsl.fromBundle("local-trust"))
                .build();

        this.reactiveClient = webBuilder
                .baseUrl("https://localhost:8443")
                .apply(webSsl.fromBundle("local-trust"))
                .build();
    }

    String pingBlocking() {
        return blockingClient.get()
                .uri("/ping")
                .retrieve()
                .body(String.class);
    }

    Mono<String> pingReactive() {
        return reactiveClient.get()
                .uri("/ping")
                .retrieve()
                .bodyToMono(String.class);
    }
}

@RestController
class ProbeController {
    private final LocalTlsClients clients;

    ProbeController(LocalTlsClients clients) {
        this.clients = clients;
    }

    @GetMapping(path = "/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String ping() {
        return "pong over tls";
    }

    @GetMapping(path = "/probe/rest",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String checkBlockingClient() {
        return clients.pingBlocking();
    }

    @GetMapping(path = "/probe/webclient",
            produces = MediaType.TEXT_PLAIN_VALUE)
    Mono<String> checkReactiveClient() {
        return clients.pingReactive();
    }
}
```

Mã này nằm trong **một file Java hợp lệ**: chỉ có `SslBundleApplication` là top-level `public class`; các class còn lại package-private và cùng package để component scanning tìm thấy. Các import `RestClientSsl` và `WebClientSsl` là **package của Spring Boot 3.3**, không sao chép package của Spring Boot 4.x vào project 3.3.

Luồng chính:

1. Boot đọc định nghĩa `local-server`, tạo embedded HTTPS Tomcat.
2. `LocalTlsClients` nhận những builder được Boot auto-configure, cùng hai adapter SSL.
3. `restSsl.fromBundle("local-trust")` và `webSsl.fromBundle("local-trust")` dùng **cùng tên trust bundle**, nhưng tạo các client/connector theo API tương ứng.
4. Khi gọi `/probe/rest`, MVC handler gọi RestClient blocking; với `/probe/webclient`, handler trả `Mono<String>` mà MVC có thể adapt như async return value.
5. Các client xác thực server certificate và hostname `localhost` dựa trên truststore; không có `trustAll`/`insecure`.

**Vì sao project gọi lại chính nó?** Để kiểm chứng end-to-end TLS mà không cần server downstream riêng. Thiết kế self-call này **chỉ dành cho demo**, không phải kiến trúc đề xuất cho nghiệp vụ: nó dùng thêm network/connection, có thể ảnh hưởng thread pool và gây deadlock nếu tài nguyên cực hạn.

### 6.5. Chạy và quan sát kết quả

Trong thư mục project đã có ba file certs đúng đường dẫn:

```bash
gradle bootRun
```

Nếu đã có Gradle Wrapper, dùng `./gradlew bootRun` (Linux/macOS) hoặc `.\gradlew.bat bootRun` (Windows PowerShell). Phải dùng JDK 17+ và phiên bản Gradle tương thích với Spring Boot 3.3.

Gọi bằng curl và **cấp CA/certificate dùng cho local**, thay vì tắt kiểm tra TLS:

```bash
curl -i --cacert certs/server.crt https://localhost:8443/ping

curl -i --cacert certs/server.crt https://localhost:8443/probe/rest

curl -i --cacert certs/server.crt https://localhost:8443/probe/webclient
```

Cả ba request dự kiến trả **HTTP 200** với text body chính xác:

```text
pong over tls
```

Phần headers và HTTP version hiển thị có thể khác theo curl, proxy và ALPN. Nếu `curl` chạy từ thư mục khác, chỉnh lại đường dẫn `--cacert`. Nếu kết nối bằng IP khác không nằm trong SAN, có thể lỗi hostname verification dù certificate được trust.

Nếu chạy `curl https://localhost:8443/ping` **không có `--cacert`** trên máy chưa tin self-signed certificate, kết nối thường bị từ chối vì certificate chưa thuộc trust anchors. Điều đó là **kết quả bảo mật đúng**, không nên “sửa” bằng `-k`/`--insecure` cho production.

### 6.6. Kiểm tra HTTP/2 h2 thực sự

Nếu bản curl có hỗ trợ HTTP/2, thử:

```bash
curl --http2 -v --cacert certs/server.crt \
  https://localhost:8443/ping
```

Quan sát phần thương lượng TLS/ALPN trong verbose output. Khi server và client hỗ trợ `h2` và đàm phán thành công, request sẽ dùng HTTP/2; nếu không, có thể fallback HTTP/1.1 hoặc báo lỗi tùy client. `server.http2.enabled=true` **không chứng minh** mọi client đã dùng HTTP/2. Trong hạ tầng có reverse proxy, kiểm tra riêng hai chặng browser→proxy và proxy→Spring Boot.

## 7. Viết bài test TLS thay cho chỉ đọc log

Một smoke test hữu ích là khởi động HTTPS trên random port, dùng RestClient có bundle trust và kiểm tra response. Đây là **file test bổ sung** cho project `ssl-bundle-demo`; chạy được khi `certs` tồn tại và cấu hình ứng dụng ở mục 6.3 hợp lệ.

**`src/test/java/com/example/sslbundle/TlsBundleIntegrationTest.java`:**

```java
package com.example.sslbundle;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TlsBundleIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    RestClient.Builder builder;

    @Autowired
    RestClientSsl ssl;

    @Test
    void customTrustBundleValidatesHttpsServer() {
        RestClient trusted = builder
                .baseUrl("https://localhost:" + port)
                .apply(ssl.fromBundle("local-trust"))
                .build();

        String body = trusted.get()
                .uri("/ping")
                .retrieve()
                .body(String.class);

        assertEquals("pong over tls", body);
    }
}
```

Chạy:

```bash
gradle test
```

Test này dùng `@SpringBootTest(RANDOM_PORT)` để không xung đột port 8443; cấu hình SSL vẫn có hiệu lực. `@LocalServerPort` lấy **port thực tế** mà Tomcat đã bind. Client tiếp tục xác minh certificate và tên `localhost` thông qua bundle. Nếu chứng chỉ đã hết hạn hoặc truststore thiếu certificate, test phải thất bại ở TLS handshake, chứ không pass vì đã tắt xác minh.

**Lưu ý giới hạn:** test này dùng certificate tự ký local và kiểm tra một RestClient; chưa thay thế được bài test rotation, mTLS hoặc certificate chain thật của production. Với CI, có thể tạo test keystore/truststore ở bước setup test thay vì commit private key vào repository.

## 8. Tái sử dụng trust material ở nhiều outbound clients

Mục đích chính của SSL bundles là tránh cấu hình lặp và rời rạc.

Giả sử ứng dụng gọi hai HTTPS APIs của cùng miền tin cậy nội bộ. Cấu hình một bundle:

```properties
spring.ssl.bundle.pem.internal-ca.truststore.certificate=file:/etc/company/pki/internal-ca-chain.pem
```

Với **RestClient** của Spring Boot 3.3:

```java
import org.springframework.boot.autoconfigure.web.client.RestClientSsl;
import org.springframework.web.client.RestClient;

// Mảnh code trong constructor/service có builder và restSsl được inject:
RestClient billing = restBuilder
        .baseUrl("https://billing.internal.example")
        .apply(restSsl.fromBundle("internal-ca"))
        .build();

RestClient inventory = restBuilder
        .baseUrl("https://inventory.internal.example")
        .apply(restSsl.fromBundle("internal-ca"))
        .build();
```

Hai `RestClient` dùng **cùng trust policy** theo tên `internal-ca`, nhưng mỗi client vẫn có base URL và behavior riêng.

Với **WebClient**:

```java
import org.springframework.boot.autoconfigure.web.reactive.function.client.WebClientSsl;
import org.springframework.web.reactive.function.client.WebClient;

// Mảnh code trong constructor/service có webBuilder và webSsl được inject:
WebClient billingReactive = webBuilder
        .baseUrl("https://billing.internal.example")
        .apply(webSsl.fromBundle("internal-ca"))
        .build();

WebClient inventoryReactive = webBuilder
        .baseUrl("https://inventory.internal.example")
        .apply(webSsl.fromBundle("internal-ca"))
        .build();
```

Đây là **mảnh code**, cần service/context với các biến được inject; không phải hai file Java độc lập. Chỉ dùng cùng trust bundle nếu các services thật sự thuộc cùng trust domain và CA đó phù hợp; không phải cứ “nội bộ” là mọi service phải tin cùng một CA.

**Truststore có thể thay thế chứ không tự hợp nhất với toàn bộ Java default trust anchors.** Nếu cùng một client phải gọi public APIs và internal CA, kiểm tra chính xác trust manager construction của thư viện: cấu hình truststore riêng có thể khiến public CA bình thường không còn được tin. Đừng chữa bằng trust-all; thay vào đó chia clients theo trust domain hoặc xây truststore thích hợp có quản lý.

**Không dùng `System.setProperty("javax.net.ssl.trustStore", "...")` vô điều kiện** nếu chỉ muốn sửa một client. Thuộc tính JVM làm thay đổi môi trường tin cậy cho nhiều kết nối dùng JSSE mặc định, gây coupling và khó debug. Named SSL bundles giúp giới hạn blast radius rõ hơn.

## 9. Mở rộng sang mTLS: client và server đều xác thực certificate

TLS HTTPS bình thường: server cung cấp certificate, client xác minh. **mTLS** bổ sung: server yêu cầu certificate của client và xác minh bằng trust material tương ứng.

```text
              mTLS giữa hai services

Service A (client)                         Service B (server)
  │                                                │
  │──── ClientHello + SNI/ALPN ────────────────────►│
  │◄─── Server certificate chain ───────────────────│
  │                                                │
  │  Validate B: chain + CA + SAN + validity        │
  │                                                │
  │◄─── Request client certificate ─────────────────│
  │──── Client certificate + proof of private key ─►│
  │                                                │
  │          Validate A: chain + client CA          │
  │◄──────────────── TLS established ───────────────►│
  │                      HTTP
```

Một **client bundle mTLS** có cả:
- `keystore`: **client certificate và client private key** do một CA phù hợp cấp.
- `truststore`: **server CA** mà client chấp nhận khi gọi Service B.

Ví dụ PEM cho outbound mTLS:

```properties
spring.ssl.bundle.pem.partner-mtls.keystore.certificate=file:/etc/tls/client/client-chain.pem
spring.ssl.bundle.pem.partner-mtls.keystore.private-key=file:/etc/tls/client/client-key.pk8
spring.ssl.bundle.pem.partner-mtls.truststore.certificate=file:/etc/tls/partner/server-ca.pem
```

Consumer sẽ tham chiếu `partner-mtls` thay cho `internal-ca`, ví dụ `restSsl.fromBundle("partner-mtls")`. Server downstream **phải được cấu hình yêu cầu certificate từ client**, nếu không việc client có key material không tự biến HTTPS thường thành mTLS theo đúng policy.

Ở **inbound Spring Boot server**, nếu muốn yêu cầu client certificate, bundle server có thể gồm keystore của server và truststore chứa CA cấp client certificates:

```properties
spring.ssl.bundle.pem.inbound-mtls.keystore.certificate=file:/etc/tls/server/server-chain.pem
spring.ssl.bundle.pem.inbound-mtls.keystore.private-key=file:/etc/tls/server/server-key.pk8
spring.ssl.bundle.pem.inbound-mtls.truststore.certificate=file:/etc/tls/client-ca.pem

server.port=8443
server.ssl.bundle=inbound-mtls
server.ssl.client-auth=need
```

Đây là **cấu hình thay thế** (không đặt song song với ví dụ `local-server` trong cùng profile). `client-auth=need` yêu cầu client certificate hợp lệ trong TLS handshake; `want` chấp nhận client certificate nếu có nhưng không nhất thiết bắt buộc.

**Có client cert hợp lệ chưa đủ để được phép gọi mọi endpoint.** TLS xác thực certificate ở tầng transport, còn authorization nghiệp vụ phải map identity (subject/SAN/SPIFFE...) tới principal/role/tenant đáng tin và kiểm soát quyền. Không cấp quyền quản trị chỉ vì client cert được cùng CA ký.

## 10. Truststore, CA bundle và certificate rotation

### 10.1. Phân tách trách nhiệm

Nên quản lý nhiều bundle theo **vai trò và trust domain**:

| Bundle | Chứa gì | Consumer |
|---|---|---|
| `server-identity` | Certificate chain + private key của ứng dụng | Embedded HTTPS server |
| `billing-ca` | CA của billing gateway | RestClient/WebClient billing |
| `partner-mtls` | Client cert/key + CA tin partner | Outbound HTTP mTLS |
| `db-ca` | CA xác minh database server | JDBC/R2DBC connector có tích hợp bundle |
| `admin-server` | Certificate riêng của management endpoint | Management server nếu tách port/TLS |

Những thành phần tích hợp khác (database, messaging, mail...) **chỉ dùng được SSL bundle khi thư viện/auto-config cụ thể hỗ trợ**. Không suy đoán rằng đặt `spring.ssl.bundle.*` là mọi driver JDBC, R2DBC, Kafka hay một HTTP library bất kỳ sẽ tự dùng nó. Hãy kiểm tra các property như `spring.data.redis.ssl.bundle` hoặc cấu hình SSL của integration tương ứng trong đúng phiên bản Spring Boot và driver.

### 10.2. Rotation không đơn giản là thay file

Khi certificate sắp hết hạn hoặc CA thay đổi, cần:
1. Cấp certificate/key mới, kiểm tra SAN, validity, key usage và certificate chain.
2. Phát hành trust anchor mới đến bên **xác minh** trước khi bên **xuất trình** chuyển certificate nếu chuyển CA.
3. Tạo giai đoạn overlap: truststore tạm tin cả CA cũ và mới nếu policy cho phép; không tạo gap làm handshake fail.
4. Cập nhật certificate/key/cấu hình và xác định thành phần nào phải restart, thành phần nào hỗ trợ hot reload.
5. Đo handshake failures, certificate expiry, h2/ALPN nếu có ảnh hưởng, và rollback plan.
6. Thu hồi chứng chỉ/CA cũ theo chính sách sau khi hết cửa sổ chuyển đổi.

Spring Boot 3.3 hỗ trợ `spring.ssl.bundle.pem.<name>.reload-on-update=true` và file watcher cho một số tình huống, với **consumer hỗ trợ reload**, trong tài liệu 3.3 là Tomcat web server và Netty web server. Ví dụ:

```properties
spring.ssl.bundle.pem.webserver.keystore.certificate=file:/etc/tls/webserver/fullchain.pem
spring.ssl.bundle.pem.webserver.keystore.private-key=file:/etc/tls/webserver/key.pk8
spring.ssl.bundle.pem.webserver.reload-on-update=true
server.ssl.bundle=webserver
```

**Không hiểu sai thành “mọi client và thư viện sẽ hot reload”.** Client tạo `SSLContext`/connection pool từ bundle một lần có thể cần tạo lại hoặc restart để nhận trust/key mới; tùy API và version. Chỉ xác nhận thành phần đã reload khi thử kết nối mới và quan sát certificate thực tế. Với path `classpath:` đóng gói trong jar, file watcher không giống mount `file:` có thể thay đổi khi chạy.

Đối với Kubernetes, secret mount cập nhật có thể thay đổi symlink hoặc file inode; kiểm tra behavior của watcher ở phiên bản Boot/OS cụ thể. Với PKCS12/JKS và secret rotation, đừng đoán hot reload nếu tài liệu consumer không cam kết.

### 10.3. Password và secret handling

- Dùng secret manager, environment/volume có quyền tối thiểu thay vì commit `keystore.password` trong repo.
- Không in private key, keystore bytes hoặc password khi debug. Nếu cần log cấu hình, chỉ log **tên bundle** và metadata công khai, không log giá trị secret.
- Tách keystore và truststore theo quyền. Public CA certificates có thể chia sẻ rộng hơn private keys.
- Mỗi môi trường dev/staging/prod nên có trust roots/keys riêng và cơ chế rollback rõ.
- Giám sát trước hạn certificate; xoay vòng không nhất thiết đồng nghĩa thay CA.
- Với TLS tới dịch vụ bên ngoài, vẫn phải kiểm tra hostname. Trust anchor chỉ chứng minh chain được một CA tin cậy ký, không chứng minh server có tên DNS mà bạn đang truy cập.

## 11. Kỹ thuật kiểm tra HTTPS, trust và HTTP/2

**Kiểm tra certificate public:**

```bash
keytool -list -v \
  -keystore certs/truststore.p12 \
  -storetype PKCS12 -storepass changeit
```

Xem alias, Subject, Issuer, validity và SAN của certificate. Không cần mở hay in private key.

**Kiểm tra handshake bằng OpenSSL (nếu cài):**

```bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile certs/server.crt \
  -verify_return_error </dev/null
```

Đây là lệnh kiểu Bash/macOS/Linux; trên PowerShell xử lý stdin khác. Với TLS local đúng, OpenSSL có thể báo chuỗi certificate verify thành công. Khi debug server cần dùng SNI, `-servername` đảm bảo gửi tên host để server chọn certificate đúng.

**Kiểm tra HTTP/2:**

```bash
curl --http2 -v --cacert certs/server.crt \
  https://localhost:8443/ping
```

Quan sát ALPN accepted protocol hoặc HTTP version ở output. Khả năng dùng `--http2` tùy curl build. Nếu chỉ thấy HTTP/1.1, kiểm tra server implementation, client ALPN, TLS termination ở proxy, hoặc cấu hình `server.http2.enabled`; **không kết luận do truststore sai** chỉ từ việc không dùng được h2 nếu TLS handshake đã thành công.

**Kiểm tra lỗi trust có chủ đích:**
- Thử dùng một CA khác không cấp certificate server: handshake phải fail, không được “tự chữa” bằng trust-all.
- Thử kết nối bằng hostname không có trong SAN: hostname verification phải fail nếu client xác minh đúng.
- Thử certificate hết hạn trong test fixture (nếu có): client phải từ chối.
- Thử rotation khi overlap CA mới/cũ và quan sát kết quả.
- Với mTLS, thử client không cung cấp cert hoặc dùng cert do CA ngoài trust domain ký: inbound server `client-auth=need` phải từ chối ở handshake.

**Lưu ý:** Đặt `curl -k`/`--insecure` làm test chứng chỉ chỉ chứng minh kết nối được khi bỏ qua xác minh; nó **không** chứng minh hệ thống cấu hình trust an toàn.

## 12. Lỗi thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân đáng nghi | Kiểm tra và sửa đúng |
|---|---|---|
| `NoSuchSslBundleException` | `fromBundle("name")` khác tên khai báo, env var khác cách viết | So key `spring.ssl.bundle.<type>.<name>`, kiểm tra tên chữ thường |
| `FileNotFoundException` / load resource fail | `classpath:`/`file:` sai, working directory khác | Kiểm tra mount path, runtime cwd, quyền đọc file |
| `UnrecoverableKeyException` / key password fail | Password hoặc key alias sai | Kiểm tra keystore type/alias/password bằng `keytool -list` |
| TLS handshake fail “PKIX path building failed” | Client thiếu CA/chứng chỉ được tin | Cấu hình truststore đúng cho **client**, kiểm tra chain và CA rotation |
| `No subject alternative DNS name matching` | URL hostname không có trong SAN | Cấp lại cert có SAN đúng; không tắt hostname verification |
| `SSLHandshakeException: Received fatal alert: bad_certificate` | mTLS thiếu client cert/hay cert không được trust | Kiểm tra cả hai bundle và `client-auth` |
| Server lỗi vì `server.ssl.bundle` và `server.ssl.key-store` | Hai cách cấu hình xung đột | Dùng bundle duy nhất, đưa thông tin key/trust vào bundle |
| Cập nhật `server.ssl.enabled-protocols` không có tác dụng | Khi dùng bundle, lựa chọn discrete server protocols có thể bị bỏ qua | Chuyển sang `spring.ssl.bundle.<type>.<name>.options.enabled-protocols` |
| `RestClient` hoạt động, `WebClient` không tin CA | WebClient khác connector/không áp bundle | Dùng `WebClientSsl.fromBundle` cho builder cụ thể |
| Một client public HTTPS bị PKIX fail sau khi thêm internal truststore | Custom truststore thay trust mặc định | Tách client theo trust domain hoặc quản lý union CA rõ ràng |
| Chỉ có HTTP/1.1 dù bật HTTP/2 | ALPN/client/proxy/server chưa thương lượng h2 | Dùng curl verbose, kiểm tra đúng endpoint TLS và server |
| Sau rotation vẫn dùng certificate cũ | Consumer không hỗ trợ hot reload, pool/context chưa tái tạo | Kiểm tra support của version; restart/recreate client khi cần |
| TLS chạy local nhưng lỗi trong Docker | Secret chưa mount đúng, cwd khác, permission hoặc DNS/SAN khác | Dùng absolute file mount và certificate cho DNS thực tế |
| “Connection refused” | Server chưa mở hoặc cổng sai | Đây là vấn đề TCP/bind, khác lỗi certificate/PKIX |
| TLS handshake xong nhưng HTTP 401/403 | Authentication/authorization ứng dụng thất bại | Xem Spring Security, token, role, client identity mapping, không sửa truststore mù quáng |

## 13. Các nhầm lẫn cần tránh

- **SSL bundle không phải certificate.** Nó là cấu trúc tên riêng để quản lý key/trust/options; certificate chỉ là một thành phần.
- **Keystore không giống truststore.** Server identity và client trust là hai vai trò riêng.
- **Cùng bundle không có nghĩa mọi kết nối tự sử dụng nó.** Mỗi consumer phải được gắn hoặc hỗ trợ tích hợp tương ứng.
- **Thêm public CA vào truststore không đồng nghĩa tắt hostname verification.** Cần cả chain và SAN hợp lệ.
- **`server.ssl.bundle` không được trộn tùy tiện với cấu hình SSL rời.** Đây là một ràng buộc cụ thể của Boot.
- **HTTP/2 không tự bật chỉ vì có TLS.** Cần `server.http2.enabled` và thương lượng protocol thích hợp.
- **mTLS không đồng nghĩa người dùng đã được authorize.** Xác thực certificate và phân quyền nghiệp vụ là hai bước khác nhau.
- **`reload-on-update` không phải magic cho mọi client.** Phải kiểm tra consumer hỗ trợ reload và có thể cần restart.
- **Dùng `-k` không phải sửa lỗi trust.** Nó loại bỏ một lớp bảo vệ chính của TLS.
- **Trust-all trong development rất dễ tràn sang production.** Hãy dùng test CA/certificate có SAN đúng và truststore riêng.
- **Một file PKCS12 chứa nhiều entry không có nghĩa sẽ tự chọn đúng key.** Dùng alias/config chính xác.
- **Một truststore chứa internal CA không chắc cộng thêm Java default roots.** Thiết kế rõ trust domain của từng client.

## 14. Câu hỏi tự kiểm tra

**Câu 1:** Browser gọi HTTPS đến Spring Boot, bundle nào phải có private key?  
**Trả lời:** Bundle server mà `server.ssl.bundle` tham chiếu; nó phải có certificate và private key phù hợp để server chứng minh identity.

**Câu 2:** Hai RestClient/WebClient cùng gọi đối tác đã có CA nội bộ. Có phải sao chép certificate path vào từng service?  
**Trả lời:** Không cần nếu API/consumer hỗ trợ SSL bundles; khai báo một trust bundle rồi dùng `RestClientSsl.fromBundle(name)` và `WebClientSsl.fromBundle(name)` trên từng builder.

**Câu 3:** Tại sao vẫn fail TLS khi CA đã nằm trong truststore?  
**Trả lời:** Có thể certificate không khớp hostname/SAN, certificate hết hạn, server gửi thiếu chain, dùng nhầm bundle hoặc TLS protocol/cipher không tương thích. Cần phân biệt chain validation và hostname verification.

**Câu 4:** Có thể dùng `server.ssl.bundle=local-server` đồng thời `server.ssl.key-store=...` không?  
**Trả lời:** Không theo contract Boot 3.3; đưa key material vào bundle và để server tham chiếu bundle.

**Câu 5:** `server.http2.enabled=true` có chứng minh response đã dùng HTTP/2?  
**Trả lời:** Không; client và server/proxy phải thực sự thương lượng `h2`. Kiểm tra ALPN/HTTP version từ traffic.

**Câu 6:** Khi rotate CA, cập nhật certificate server trước hay truststore client trước?  
**Trả lời:** Thông thường cần cho các client chấp nhận CA mới **trước** khi server bắt đầu xuất trình chain mới, có overlap tin cậy để tránh gián đoạn; chi tiết phụ thuộc mô hình deploy.

**Câu 7:** Nếu đã có HTTPS, vì sao vẫn phải kiểm tra authorization?  
**Trả lời:** TLS xác thực kết nối/peer theo chính sách, không tự quyết định user/service có quyền truy cập dữ liệu hoặc endpoint nào.

## 15. Tài liệu chính thức để đối chiếu

1. Spring Boot 3.3.13, **SSL** — JKS/PKCS12 bundles, PEM bundles, `SslBundles`/`SslBundle` và reload: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
2. Spring Boot 3.3.13, **Embedded Web Servers** — `server.ssl.bundle` và HTTP/2: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
3. Spring Boot 3.3.13, **Calling REST Services** — `RestClientSsl` và `WebClientSsl`: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
4. Spring Boot 3.3.13 API, **SslBundle** — stores/managers/options/`createSslContext()`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ssl/SslBundle.html
5. Spring Boot 3.3.13 API, **SslBundles** — registry lookup by name: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ssl/SslBundles.html
6. Spring Boot 3.3.13 **Common Application Properties** — `spring.ssl.bundle.*`, `server.ssl.*`, `server.http2.enabled`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/

**Kết luận:** SSL bundles biến key/certificate/truststore từ những cấu hình TLS rời rạc thành **named trust/key material** có thể tham chiếu và dùng chung theo đúng trust domain. Hãy tách identity khỏi trust, dùng `server.ssl.bundle` cho inbound HTTPS, `RestClientSsl`/`WebClientSsl` cho outbound HTTPS, kiểm tra certificate chain + hostname, và thiết kế rotation/mTLS/HTTP/2 dựa trên khả năng thực tế của từng consumer.