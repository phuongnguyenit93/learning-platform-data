# Áp dụng SSL bundle và kiểm tra chứng thư máy chủ đích trong Spring Boot HTTP client

> **Module:** Spring Boot - web-runtime · **Nhóm:** HTTP client. Bài này tập trung vào chiều **ứng dụng Spring Boot gọi HTTPS ra bên ngoài**, kiểm tra chứng thư và danh tính **máy chủ đích** thông qua SSL bundle. Không nhầm với cấu hình `server.ssl.*` để mở HTTPS cho server nhận request. Ví dụ dùng **Spring Boot 4.1.2**, **Java 17+**, Maven, OpenSSL và `RestClient`; bổ sung cách dùng `WebClient`, `RestTemplate`, JKS/PKCS12, mTLS và quy trình vận hành truststore an toàn.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích TLS server authentication, trust anchor, certificate chain, **Subject Alternative Name (SAN)**, thời hạn và hostname verification.
2. Phân biệt **truststore của HTTP client** với **keystore/private key của chính client**, cũng như keystore của HTTP server.
3. Khai báo `spring.ssl.bundle.pem.<tên>.truststore.certificate` hoặc `spring.ssl.bundle.jks.<tên>.truststore.*`.
4. Gắn bundle vào `RestClient` thông qua `RestClientSsl`; vào `WebClient` thông qua `WebClientSsl`; vào `RestTemplate` bằng `RestTemplateBuilder.sslBundle(...)` theo Spring Boot 4.1.
5. Chạy một project Maven có HTTPS server tự ký ở localhost và một RestClient tin đúng cert đó, **vẫn giữ việc xác minh hostname**.
6. Kiểm thử thất bại khi CA không được tin, hostname/SAN sai, cert quá hạn hoặc thiếu intermediate; phân biệt handshake failure với HTTP 401/403.
7. Thiết kế quản lý CA rotation, client mTLS identity, timeout/connection pool, proxy, redirect và bảo vệ khỏi SSRF.

## 1. Phải xác minh server, không chỉ mã hóa kết nối

Một ứng dụng gọi:

~~~http
GET /v1/orders HTTP/1.1
Host: partner.example.com
Authorization: Bearer (token của ứng dụng)
~~~

Nếu chỉ yêu cầu một kênh TLS mã hóa nhưng **không kiểm tra chứng thư của đối tác**, kẻ tấn công trên đường mạng có thể trình một certificate của chính họ và đứng giữa client/server. TLS chỉ đạt mục tiêu khi kết nối được **đúng endpoint đã định**, không chỉ một endpoint bất kỳ có hỗ trợ HTTPS.

~~~text
Spring Boot / RestClient                   Server đối tác
   |
   +---- TCP + TLS ClientHello (SNI=partner.example.com) --->
   |<--- Certificate (leaf + intermediate chain) ------------+
   |
   +-- Kiểm chain đến trusted root/anchor
   +-- Kiểm notBefore/notAfter
   +-- Kiểm SAN của cert với hostname URL
   +-- Kiểm key usages / crypto policy
   |           |
   |           +-- KHÔNG hợp lệ -> handshake error, không gửi HTTP body
   |
   +---- HTTP request bên trong TLS ------------------------->
   |<--- HTTP response --------------------------------------+
~~~

- **Encryption/integrity:** dữ liệu được bảo vệ khi truyền.
- **Authentication:** máy chủ thực sự tương ứng hostname/định danh bạn cần gọi.
- **Authorization API:** token, session, Basic hoặc mTLS identity vẫn cần được kiểm sau/bên cạnh TLS.

Nếu TLS thành công mà API trả HTTP 401, đó thường là **thiếu/không hợp lệ credential ứng dụng**, không phải yêu cầu đổi truststore. Nếu TLS bị PKIX error thì ứng dụng chưa có bằng chứng đủ tin để gửi dữ liệu nhạy cảm.

### Những thuật ngữ quan trọng

| Thuật ngữ | Ý nghĩa thực tế |
| --- | --- |
| Leaf/server certificate | Public certificate của endpoint, chứa public key, SAN, issuer, validity |
| Intermediate CA certificate | Chứng thư CA trung gian để tạo đường xác thực đến trust anchor |
| Root CA/trust anchor | CA/certificate mà client quyết định tin |
| Certificate chain | Dãy leaf/intermediate dùng để xác minh chữ ký đến trust anchor |
| **Truststore** | Tập certificates/CA mà client dùng để **tin máy chủ bên kia** |
| **Keystore** | Kho có thể chứa certificate chain và **private key của bên sở hữu** |
| SSL bundle | Tập hợp TLS key/trust material + tùy chọn, được đặt tên trong Spring Boot |
| Hostname verification | So hostname/IP đích trong URL với SAN trên server certificate |
| SNI | Server Name Indication trong TLS ClientHello, giúp server chọn cert theo tên |
| ALPN | Thương lượng protocol như `h2` hay `http/1.1` sau TLS; khác việc xác minh cert |
| mTLS | Cả client kiểm server cert lẫn server kiểm client certificate |

**Server-auth TLS thông thường không cần private key bên HTTP client.** Client chỉ cần trust material của CA/endpoint; private key của client chỉ cần khi server yêu cầu mTLS.

## 2. Các phép kiểm mà HTTP client phải thực hiện

### 2.1. PKIX path building tới CA được tin cậy

Ví dụ:

~~~text
server leaf: inventory.internal.example
   signed by: Company Issuing CA
   signed by: Company Root CA

client truststore:
   Company Root CA
~~~

Client nhận leaf và chain (server nên gửi intermediate phù hợp), xác minh chữ ký, basic constraints, key usage, validity và xây chain tới trust anchor. Nếu client không có CA thích hợp, một lỗi điển hình:

~~~text
javax.net.ssl.SSLHandshakeException:
  PKIX path building failed:
  unable to find valid certification path to requested target
~~~

Những nguyên nhân thường gặp: private CA chưa nằm trong truststore, server quên intermediate, app dùng **sai SSL bundle**, corporate TLS proxy thay chain, certificate quá hạn, policy thuật toán không phù hợp. **Không sửa bằng cách tạo TrustManager tin mọi cert.**

### 2.2. Hostname/SAN phải trùng URL thực

Khi gọi `https://orders.example.com`, certificate phải có danh tính hợp lệ cho `orders.example.com`. Một cert cho `api.example.com` không trở thành hợp lệ chỉ vì cùng tổ chức hay cùng CA cấp.

- SAN `DNS:orders.example.com` khớp hostname đó.
- SAN wildcard `DNS:*.example.com` thông thường chỉ khớp một cấp như `api.example.com`, không khớp `a.b.example.com` hoặc `example.com`.
- Gọi `https://127.0.0.1` cần SAN **IP Address:127.0.0.1**; SAN `DNS:localhost` không tự đủ.
- Gọi bằng IP nhưng đặt HTTP `Host: orders.example.com` không thể thay hostname verification trước đó của TLS.
- Đừng dùng `CN` thay cho SAN; chứng thư TLS hiện đại dựa trên SAN.

Hostname checking **khác với CA trust**. Một certificate hợp lệ theo CA vẫn có thể sai hostname, và phải bị từ chối.

### 2.3. Hiệu lực, key usage, revocation và clock

`notBefore` và `notAfter` xác định cửa sổ hiệu lực của certificate; client nên có đồng hồ hệ thống đồng bộ NTP. Extended Key Usage như `serverAuth` và policy thuật toán/key size cũng có vai trò. Revocation checking (OCSP/CRL) tùy cấu hình provider/policy, không mặc định suy ra mọi client đều kiểm thu hồi online ở mọi handshake.

Đừng đánh đồng chứng thư được **cấp mới trên đĩa** với chứng thư **đang được endpoint trình ra qua TLS**. Load balancer hoặc một pod khác có thể còn dùng cert cũ.

### 2.4. Public CA và Java default truststore

JDK/JVM có default trust anchors, thường từ truststore runtime (ví dụ `cacerts`). Nếu server dùng public CA mà runtime đã tin, có thể **không cần custom truststore**. SSL bundle riêng thích hợp khi:

- Đối tác sử dụng internal/private CA.
- Muốn phân vùng trust theo từng external API.
- Chạy lab có self-signed localhost cert.
- Cần client keypair cho mTLS.

Custom truststore không mặc nhiên là phép **cộng thêm** CA vào default JVM truststore: nhiều SSLContext/connector sẽ sử dụng chính truststore bạn cung cấp. Vì vậy, đừng lấy bundle chỉ trust internal CA rồi cho rằng cùng client đó vẫn tin tất cả public websites như trước. Thiết kế **client theo đối tác** và test trust tương ứng.

### 2.5. Tránh chỉnh JVM truststore toàn cục

Một số ứng dụng cũ dùng `-Djavax.net.ssl.trustStore=...` hoặc sửa `$JAVA_HOME/lib/security/cacerts`. Điều đó có thể tác động **toàn bộ outbound TLS của JVM**, kể cả thư viện khác, và tạo rủi ro khi rotate CA.

SSL bundle cho phép giới hạn cấu hình rõ ràng:

~~~text
RestClient tới billing.internal      -> bundle billing-ca
WebClient tới events.partner.example -> bundle events-ca
RestClient tới public API           -> JVM trust mặc định nếu phù hợp
Client mTLS tới payments             -> bundle payments-client
~~~

Đây là **quy ước kiến trúc**, không phải cơ chế Boot tự chọn bundle theo URL. Bạn phải áp đúng bundle trên builder tương ứng.

## 3. Cấu hình SSL bundle theo PEM

Spring Boot hỗ trợ `spring.ssl.bundle.pem.*` và `spring.ssl.bundle.jks.*`. Mỗi tên bundle có thể lấy qua `SslBundles` và áp vào các consumer được tích hợp.

### 3.1. PEM truststore cho outbound HTTP client

~~~properties
spring.ssl.bundle.pem.partner.truststore.certificate=file:/etc/myapp/trust/partner-ca.pem
~~~

- `partner` là tên SSL bundle do bạn chọn.
- `truststore.certificate` trỏ tới **certificate public** của CA/endpoint mà bạn quyết định trust theo chính sách.
- `file:` chỉ file do operator/secret mount quản lý; có thể dùng `classpath:` cho cert public ở môi trường có yêu cầu versioning phù hợp, nhưng không thuận tiện cho rotation ngoài app.
- Chỉ định truststore **không có nghĩa tự động mọi RestClient/WebClient dùng bundle**; phải apply vào client.

Đừng đưa **private key của CA hoặc của server** vào truststore client. Khi một service đổi CA, cập nhật trust material có kiểm soát; không sao chép file cert thu được ngẫu nhiên từ một trang lỗi SSL rồi tin nó mà chưa kiểm nguồn.

### 3.2. PEM keystore + truststore cho mTLS

~~~properties
# Client kiểm chứng máy chủ đối tác.
spring.ssl.bundle.pem.payments.truststore.certificate=file:/run/trust/payments-ca.pem

# Server đối tác kiểm chứng client của chúng ta:
spring.ssl.bundle.pem.payments.keystore.certificate=file:/run/identity/my-client-chain.pem
spring.ssl.bundle.pem.payments.keystore.private-key=file:/run/identity/my-client-key.pem
~~~

Trong mTLS, server đích phải được cấu hình yêu cầu/chấp nhận client certificate và trust CA phát hành client certificate. HTTP API vẫn có thể yêu cầu thêm bearer token/permission. Không gửi private key qua network; client chỉ dùng key ở local để chứng minh sở hữu.

### 3.3. Tên bundle và cách đọc

Spring Boot auto-config bean `SslBundles`:

~~~java
// Fragment dùng bên trong Spring-managed component:
SslBundle bundle = sslBundles.getBundle("partner");
~~~

Trong Boot 4.x, types nằm trong `org.springframework.boot.ssl`. Nếu không có tên bundle, `NoSuchSslBundleException` là **lỗi cấu hình** khi lấy bundle; không phải lỗi danh tính server.

Tài liệu hỗ trợ thêm `base64:` hoặc PEM content trực tiếp tùy property; nhưng với config cần rotation, đường dẫn file được quản trị thường dễ vận hành hơn. Nếu dùng environment variables để khai bundle, tên bundle được chuẩn hóa lowercase theo convention Boot; nên đặt tên lowercase nhất quán.

## 4. Cấu hình SSL bundle theo JKS hoặc PKCS12

Java KeyStore có thể chứa CA trust certificates, và khi dùng mTLS có thể chứa private key/cert chain. Một outbound truststore PKCS12:

~~~properties
spring.ssl.bundle.jks.partner.truststore.location=file:/run/trust/partner-trust.p12
spring.ssl.bundle.jks.partner.truststore.type=PKCS12
spring.ssl.bundle.jks.partner.truststore.password=${PARTNER_TRUSTSTORE_PASSWORD}
~~~

Nhớ cấp biến môi trường/secret `PARTNER_TRUSTSTORE_PASSWORD` bằng cơ chế thích hợp, không commit mật khẩu thật vào repository. Không định nghĩa trùng tên `partner` trong cả `pem` và `jks` rồi dựa vào thứ tự ngẫu nhiên của auto-configuration.

Nếu có public CA cert để nhập:

~~~bash
keytool -importcert -noprompt \
  -alias partner-ca \
  -file partner-ca.pem \
  -keystore partner-trust.p12 \
  -storetype PKCS12 \
  -storepass changeit
~~~

`changeit` là mật khẩu **chỉ cho lab**, không dùng trong production. Truyền password qua CLI có thể xuất hiện trong history/process list; môi trường thật nên dùng vault/secret delivery đã phê duyệt.

Để kiểm keystore:

~~~bash
keytool -list -v \
  -keystore partner-trust.p12 \
  -storetype PKCS12
~~~

Output sẽ có alias, validity, entry type và fingerprint của public certificate. Mục đích là xác minh **truststore chứa CA nào**, không chứng minh live server trình đúng cert. Đừng nhập một private key vào client truststore chỉ để giải quyết PKIX error.

### So sánh PEM và JKS

| Tiêu chí | PEM trust material | JKS/PKCS12 trust material |
| --- | --- | --- |
| Định dạng | File text chứa `BEGIN CERTIFICATE` | Binary keystore/truststore |
| Dùng cho private CA | `spring.ssl.bundle.pem.*.truststore.certificate` | `spring.ssl.bundle.jks.*.truststore.*` |
| Dùng mTLS identity | PEM cert chain + PEM private key | Keystore private key entry + chain |
| Quản lý bí mật | Key PEM cần ACL, secret manager | Keystore và password cần ACL, secret manager |
| Rotation | Publish file cert/chain mới, kiểm consumer reload | Publish keystore mới, kiểm consumer reload |
| Chọn định dạng | Theo PKI/secret delivery và client integration | Theo policy Java/keystore management |

Đừng mặc định PEM tốt hơn JKS hoặc ngược lại cho mọi hệ thống; mục tiêu là định dạng được quản trị tốt, đúng trust policy và dùng đúng trong client connector.

## 5. Áp SSL bundle cho HTTP client trong Spring Boot 4.1.2

### 5.1. RestClient (imperative)

Ở **Boot 4.x**, `RestClientSsl` thuộc package **`org.springframework.boot.restclient.autoconfigure`**:

~~~java
import org.springframework.boot.restclient.autoconfigure.RestClientSsl;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class PartnerRestClient {
    private final RestClient client;

    public PartnerRestClient(RestClient.Builder builder, RestClientSsl ssl) {
        this.client = builder
                .baseUrl("https://partner.example.com")
                .apply(ssl.fromBundle("partner"))
                .build();
    }

    public String fetchStatus() {
        return client.get()
                .uri("/health")
                .retrieve()
                .body(String.class);
    }
}
~~~

Đây là class cho một Spring Boot app có bundle `partner`; để chạy được, server và endpoint phải có thật. `RestClient.Builder` do Boot auto-config nên được inject để giữ message converters và các tích hợp khác, thay vì tự dùng `RestClient.create()` khi cần cấu hình Boot.

**Cẩn trọng:** Javadoc Boot 4.1.2 ghi rõ áp dụng `RestClientSsl.fromBundle(...)` có thể **thay thế `ClientHttpRequestFactory` đã cấu hình trước đó**. Nếu đang chỉnh proxy, timeouts hoặc pool trên factory riêng, đừng nghĩ chúng mặc nhiên còn nguyên. Dùng `HttpClientSettings`/`ClientHttpRequestFactoryBuilder` theo tài liệu và test cấu hình hiệu lực.

### 5.2. WebClient (reactive)

Ở **Boot 4.x**, `WebClientSsl` thuộc `org.springframework.boot.webclient.autoconfigure`:

~~~java
import reactor.core.publisher.Mono;

import org.springframework.boot.webclient.autoconfigure.WebClientSsl;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class PartnerReactiveClient {
    private final WebClient client;

    public PartnerReactiveClient(WebClient.Builder builder, WebClientSsl ssl) {
        this.client = builder
                .baseUrl("https://partner.example.com")
                .apply(ssl.fromBundle("partner"))
                .build();
    }

    public Mono<String> fetchStatus() {
        return client.get()
                .uri("/health")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Đoạn này dành cho project có Spring WebFlux dependency và bean `WebClient.Builder` của Boot. Trong WebFlux handler, trả `Mono`/`Flux` lên framework thay vì tự `block()` trên Netty event loop. Dùng `WebClientSsl` để cấu hình trust cho connector và kiểm lại nếu app đã tự set connector/connection provider khác.

Có cả MVC và WebFlux starter trên classpath không mặc nhiên biến server thành WebFlux; Spring Boot thường ưu tiên **Servlet web application type** khi cả hai hiện diện. WebClient dùng làm outbound client được, nhưng đừng nhầm với việc thay cả runtime ứng dụng.

### 5.3. RestTemplate (legacy imperative)

Boot 4.1.2 cung cấp `RestTemplateBuilder.sslBundle(...)`:

~~~java
import org.springframework.boot.restclient.RestTemplateBuilder;
import org.springframework.boot.ssl.SslBundles;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class LegacyPartnerClient {
    private final RestTemplate template;

    public LegacyPartnerClient(RestTemplateBuilder builder,
                               SslBundles bundles) {
        this.template = builder
                .sslBundle(bundles.getBundle("partner"))
                .build();
    }

    public String fetchStatus() {
        return template.getForObject(
                "https://partner.example.com/health", String.class);
    }
}
~~~

Một số hướng dẫn Boot 3.x dùng `setSslBundle(...)` và package khác, nên chọn **API đúng phiên bản**. Với code mới không cần reactive, Boot khuyến nghị `RestClient`; RestTemplate vẫn quan trọng cho codebase hiện tại.

### 5.4. Chọn đúng client

| API | Execution | Áp bundle | Chú ý |
| --- | --- | --- | --- |
| `RestClient` | Imperative | `builder.apply(restClientSsl.fromBundle("partner"))` | Có thể thay request factory, kiểm timeout/proxy |
| `WebClient` | Reactive | `builder.apply(webClientSsl.fromBundle("partner"))` | Kiểm Reactor Netty connector, không block event loop |
| `RestTemplate` | Imperative legacy | `builder.sslBundle(sslBundles.getBundle("partner"))` | Có request factory riêng và API builder mới |
| JDK `HttpClient` | Imperative/async JDK | Tạo SSLContext/trust config theo JSSE | Không tự apply Boot SSL bundle khi tự new builder |
| Apache/Jetty/custom SDK | Theo library | Tùy provider/connector | Phải kiểm thực tế cách trust/hostname được áp dụng |

**Không dùng một HTTP client chung với truststore nội bộ cho mọi external URL.** Client tới đối tác A và B nên có baseUrl và bundle riêng, giảm rủi ro trust quá rộng và rò Authorization header qua redirect.

## 6. Ví dụ chạy được: HTTPS localhost + RestClient tin đúng chứng thư

Mục tiêu: Boot MVC mở HTTPS tại `https://localhost:8443`, và khi startup nó gọi `/ping` qua `RestClient` có SSL bundle client độc lập. Server dùng **private key + certificate**, client chỉ trust **public certificate**; việc kiểm SAN vẫn hoạt động.

**Cấu trúc project:**

~~~text
ssl-bundle-httpclient-demo/
  pom.xml
  .gitignore
  tls/                             # tạo bằng OpenSSL, KHÔNG commit
    server.crt                     # public cert self-signed
    server.key                     # private key
  src/main/java/com/example/ssldemo/
    SslBundleHttpClientDemoApplication.java
    PingController.java
  src/main/resources/
    application.properties
~~~

### 6.1. `pom.xml`

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
    <artifactId>ssl-bundle-httpclient-demo</artifactId>
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

Starter MVC dùng embedded Tomcat và RestClient, không cần WebFlux cho ví dụ blocking. Nếu muốn triển khai WebClient reactive riêng, dùng WebFlux starter trong project khác và đoạn code mục 5.2.

### 6.2. `src/main/resources/application.properties`

~~~properties
# HTTPS listener, server TLS identity
server.port=8443
server.ssl.bundle=localserver

spring.ssl.bundle.pem.localserver.keystore.certificate=file:./tls/server.crt
spring.ssl.bundle.pem.localserver.keystore.private-key=file:./tls/server.key

# Outbound HTTP client TLS trust, KHÔNG chứa private key
spring.ssl.bundle.pem.localpeer.truststore.certificate=file:./tls/server.crt
~~~

**Hai bundle khác nhau:**

- `localserver` có cert/key của **server** nhận request.
- `localpeer` chỉ chứa certificate public để **RestClient** tin server local.
- `server.ssl.bundle=localserver` không tự làm các outbound clients sử dụng `localpeer`; code phải gọi `ssl.fromBundle("localpeer")`.
- Đường dẫn `file:./tls/...` phụ thuộc working directory khi JVM chạy. Demo chạy Maven ở root project; production nên mount secrets và dùng đường dẫn tuyệt đối do operator quản lý.

File cert self-signed được dùng như trust anchor cho **lab**. Trong production, dùng CA root/chain phù hợp, không tin một leaf cert bất kỳ chỉ vì ai đó gửi qua chat.

### 6.3. `SslBundleHttpClientDemoApplication.java`

~~~java
package com.example.ssldemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.restclient.autoconfigure.RestClientSsl;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class SslBundleHttpClientDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SslBundleHttpClientDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner verifyHttps(
            RestClient.Builder builder, RestClientSsl ssl) {
        return args -> {
            RestClient client = builder
                    .baseUrl("https://localhost:8443")
                    .apply(ssl.fromBundle("localpeer"))
                    .build();

            String body = client.get()
                    .uri("/ping")
                    .retrieve()
                    .body(String.class);

            System.out.println("Verified HTTPS response: " + body);
        };
    }
}
~~~

ApplicationRunner chạy sau khi Spring Boot khởi tạo application context và embedded server. Lab tự gọi một HTTPS listener local để chứng minh trust + hostname verification bằng **client thực**. Nếu TLS handshake lỗi, RestClient có thể ném exception khiến startup runner thất bại; **đó là tín hiệu lỗi cần xử lý**, không phải lý do tắt validation.

### 6.4. `PingController.java`

~~~java
package com.example.ssldemo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping(value = "/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }
}
~~~

Controller này trả body text `pong`. Không có business authorization, JWT hoặc database vì mục đích là kiểm HTTPS server identity. Production API sẽ cần xác thực/ủy quyền ở tầng phù hợp.

### 6.5. `.gitignore`

~~~gitignore
/tls/
/target/
~~~

Đừng commit private key. `.gitignore` chỉ bỏ qua file chưa được Git theo dõi; nếu key đã bị commit, phải thực hiện key rotation/revocation và xử lý rò rỉ theo security policy.

### 6.6. Tạo chứng thư self-signed có SAN bằng OpenSSL

Chạy trong project root trên POSIX, macOS, Linux hoặc WSL:

~~~bash
umask 077
mkdir -p tls

openssl req -x509 -newkey rsa:2048 -sha256 -nodes \
  -keyout tls/server.key \
  -out tls/server.crt \
  -days 7 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 tls/server.key

openssl x509 -in tls/server.crt -noout \
  -subject -issuer -dates -ext subjectAltName
~~~

`-nodes` tạo private key không mã hóa **chỉ cho lab**, để app có thể đọc mà không hardcode password. Trong production, dùng PKI/secret manager/ACL phù hợp; không đưa key thực ra internet hay repo. Trên Windows, thay `chmod/umask` bằng thiết lập NTFS ACL. Output OpenSSL thay đổi theo thời điểm tạo, không thể giả định một serial/date cố định.

**SAN** bao gồm DNS localhost và IP 127.0.0.1. Nếu chỉ có `CN=localhost` nhưng không có SAN, nhiều HTTP clients sẽ từ chối. Nếu dùng phiên bản OpenSSL không hỗ trợ `-addext`, cần dùng config extension file tương đương, không đơn giản bỏ SAN.

### 6.7. Chạy ứng dụng

~~~bash
mvn spring-boot:run
~~~

Khi HTTPS server đã sẵn sàng và RestClient gọi thành công, chương trình in:

~~~text
Verified HTTPS response: pong
~~~

Đây là dòng được tạo cố định bởi code, còn log Spring Boot (cổng, thread, thời gian) tùy môi trường. Nếu port `8443` đang được dùng, sửa `server.port` và `baseUrl` thành cùng port hoặc dừng service cũ trước khi chạy lại.

Đóng gói:

~~~bash
mvn package
java -jar target/ssl-bundle-httpclient-demo-0.0.1-SNAPSHOT.jar
~~~

Chạy JAR từ root để các `file:./tls/...` vẫn trỏ đúng. Không chạy `javac` trần cho project Spring Boot khi thiếu dependency classpath.

### 6.8. Kiểm tra bằng cURL

Trong terminal khác, từ thư mục root project:

~~~bash
curl -i --cacert tls/server.crt https://localhost:8443/ping
~~~

Kỳ vọng status 200 và body `pong`. Header `Content-Type` thường là text/plain; số bytes, Date và định dạng status line tùy server/client.

~~~bash
curl -i --cacert tls/server.crt https://127.0.0.1:8443/ping
~~~

Lệnh bằng IP cũng có thể thành công vì cert demo chứa SAN `IP:127.0.0.1`.

**Đừng dùng** `-k`/`--insecure` để chữa lỗi handshake. `--cacert` cung cấp cert public được tin **cho đúng lệnh cURL**, không làm JVM tự thay đổi truststore hoặc SSL bundle.

### 6.9. Kiểm certificate thực qua OpenSSL

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -CAfile tls/server.crt \
  -verify_hostname localhost \
  -verify_return_error </dev/null
~~~

- `-servername` bật SNI, quan trọng khi server có nhiều hostname.
- `-CAfile` đặt public certificate/CA được tin cho CLI OpenSSL.
- `-verify_hostname` kiểm tên đích, không chỉ CA chain.
- `-verify_return_error` yêu cầu lỗi validation làm lệnh báo thất bại.

Output thành công có thể chứa `Verify return code: 0 (ok)`. Phải biết OpenSSL version/trust options thật đang dùng; chỉ nhìn thông tin leaf ở output chưa đủ kết luận client tin server.

Để xem leaf cert đang phục vụ:

~~~bash
openssl s_client \
  -connect localhost:8443 \
  -servername localhost \
  -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout \
      -subject -issuer -serial -dates -fingerprint -sha256 \
      -ext subjectAltName
~~~

Pipeline thứ hai **chỉ in metadata** từ cert server gửi, không phải phép kiểm chain và hostname đầy đủ nếu không cung cấp CA/trust options.

## 7. Thử nghiệm âm tính (negative tests)

### 7.1. Không có CA/cert trusted

~~~bash
curl -i https://localhost:8443/ping
~~~

Với cert tự ký chưa được import vào truststore mặc định của cURL/OS, lệnh thường thất bại do certificate không được tin. Điều này khác HTTP 401/403: nó xảy ra **trước HTTP layer**. Để sửa test, thêm `--cacert tls/server.crt`, không dùng `--insecure`.

### 7.2. Tin CA nhưng hostname sai

~~~bash
curl --noproxy "*" \
  --resolve wrong.example.test:8443:127.0.0.1 \
  --cacert tls/server.crt \
  -i https://wrong.example.test:8443/ping
~~~

Lệnh này buộc DNS tới localhost nhưng URL hostname vẫn là `wrong.example.test`. Cert chỉ có SAN `localhost` và `127.0.0.1`, nên client phải từ chối vì **hostname mismatch**. Đây là bằng chứng rằng **trang truststore không được phép bỏ qua kiểm SAN**.

Nếu môi trường có proxy khác can thiệp, kiểm `--noproxy "*"` và kết nối local trước. Không sửa certificate để tin một wildcard vô hạn, và không viết HostnameVerifier luôn trả true.

### 7.3. Truststore chứa CA khác

Một cách kiểm trong môi trường riêng: tạo cert self-signed khác, trỏ `localpeer.truststore.certificate` vào cert **không ký** `server.crt` rồi khởi động lại demo. RestClient phải thất bại PKIX/unknown CA khi handshake, dù SAN server đúng. Đừng dùng public cert tải từ nguồn chưa được duyệt làm “bài sửa” cho truststore production.

Khi đổi file, đừng mặc định HTTP client đang chạy lập tức cập nhật SSLContext. Trong lab có thể restart; trong production dùng quy trình rotation có kiểm tra support của connector.

### 7.4. Chứng thư hết hạn

~~~bash
openssl x509 -in tls/server.crt -noout -dates
openssl x509 -in tls/server.crt -noout -checkend 259200
~~~

Lệnh `-checkend 259200` kiểm liệu cert còn hợp lệ sau khoảng ba ngày; exit code 0 thường nghĩa là có, nonzero là sắp hết hạn/lỗi. Kiểm ngày là cần thiết nhưng **không thay thế chain/SAN check**.

### 7.5. Thiếu intermediate certificate

Khi server không gửi intermediate cần thiết, client có thể không dựng được chain tới trusted root. Dùng `openssl s_client -showcerts` kiểm server đang gửi gì và kiểm cấu hình full chain. Đừng copy CA private key; cần các public intermediate certificate. Một số clients có cache intermediate nên kết quả giữa môi trường có thể khác nhau: test bằng runtime/network tương tự production.

### 7.6. Bảng lỗi theo giai đoạn

| Symptom | Giai đoạn | Nguyên nhân cần điều tra |
| --- | --- | --- |
| `NoSuchSslBundleException` | Boot configuration | Bundle chưa khai hoặc tên sai |
| `SSLHandshakeException` / PKIX path building failed | TLS verification | CA không tin, thiếu intermediate, chain sai |
| `CertificateExpiredException` | TLS validity | Cert hết hạn hoặc clock sai |
| `No subject alternative DNS name matching` | Hostname verification | Host URL không khớp SAN |
| `handshake_failure` | TLS negotiation | Cipher/protocol, mTLS identity, server policy |
| `Connection refused` | TCP/connect | Sai host/port, server chưa chạy, firewall |
| Timeout | DNS/TCP/TLS/HTTP tùy exception | Network, proxy, server load, timeouts |
| HTTP 401 | HTTP application | Credential/token không được chấp nhận |
| HTTP 403 | HTTP application | Thiếu quyền hoặc policy từ chối |
| HTTP 404 | HTTP application | URL/method/path không đúng |
| HTTP 5xx | HTTP application/gateway | Server error sau TLS |

Không trả nguyên stack trace và secrets/token ra response của API khi outbound call thất bại; chuẩn hóa error contract cho caller và log chi tiết có kiểm soát.

## 8. mTLS: SSL bundle có cả trust và client identity

Nếu server đích yêu cầu **mutual TLS**, client cần cả truststore để **kiểm server** và keystore có private key để **server kiểm client**.

~~~properties
spring.ssl.bundle.pem.mtls-partner.truststore.certificate=file:/run/trust/partner-ca.pem
spring.ssl.bundle.pem.mtls-partner.keystore.certificate=file:/run/identity/client-chain.pem
spring.ssl.bundle.pem.mtls-partner.keystore.private-key=file:/run/identity/client-key.pem
~~~

Áp dụng:

~~~java
// Fragment RestClient trong Spring-managed component.
RestClient client = builder
        .baseUrl("https://payments.internal.example")
        .apply(ssl.fromBundle("mtls-partner"))
        .build();
~~~

Chỉ nên dùng client certificate được cấp đúng cho workload/service identity. Server phải trust client CA hoặc cert theo chính sách; việc trình cert thành công vẫn không loại bỏ yêu cầu authorization/tenant. Không tái sử dụng client key của môi trường production trong lab.

Những sai lầm đặc biệt:

- Dùng truststore mà không keystore trong khi server yêu cầu mTLS → handshake có thể thất bại do thiếu client identity.
- Dùng keystore nhưng bỏ truststore/hostname checks → client không còn chứng minh được server thật.
- Đưa private key của server vào client keystore → sai identity boundary và rò bí mật.
- Dùng chung identity giữa các partner/tenants khi phải phân biệt quyền.
- Đặt keystore password hoặc private key trong source, JAR, Docker image, logs và CI artifacts.
- Nghĩ mTLS tự đồng nghĩa mọi endpoint API được quyền truy cập.

## 9. Timeout, pooling và SSL bundle: kiểm cấu hình thật

TLS handshake thường chỉ diễn ra khi tạo **kết nối mới**. HTTP/1.1 keep-alive và HTTP/2 multiplexing cho phép nhiều HTTP requests dùng cùng TLS connection. Một certificate được đổi ở server/truststore được đổi ở client **không lập tức thay cert trên connection đã tồn tại**.

### 9.1. RestClientSsl có thể thay request factory

Trong Spring Boot 4.1.2, `RestClientSsl.fromBundle(...)` có thể cấu hình một `ClientHttpRequestFactory` mới thay factory trước đó. Nếu trước đây bạn đã đặt proxy, connect timeout, read timeout hoặc SSLContext trong factory riêng, sau khi apply bundle cần xác minh những setting đó có còn được dùng không.

Spring Boot có `HttpClientSettings` và `ClientHttpRequestFactoryBuilder` để phối hợp SSL bundle với client tuning. Không gắn custom factory rồi hy vọng một lần apply sau sẽ giữ nguyên mọi tính năng. Với RestTemplateBuilder, các API `sslBundle(...)` và `clientSettings(...)` cũng ảnh hưởng underlying factory; cần đọc Javadoc đúng Boot version.

### 9.2. WebClient và reactor connection pool

WebClient có thể dùng Reactor Netty pool. Khi chọn bundle:

- Ưu tiên `WebClient.Builder` auto-config, tránh tự đặt connector không có trust policy đúng.
- Khi customize `HttpClient`, verify SSL context, hostname, connect/response timeouts, proxy và pool lifecycle.
- Không gọi `block()` trên Netty event loop; hạn chế blocking ở auth/interceptors/custom filters.
- Khi rotate CA, test **new connection** và xác nhận connector/SSLContext đã được refresh theo cơ chế bạn triển khai.

### 9.3. HTTP redirect có thể rò credentials

Nếu partner trả redirect sang domain khác, ứng dụng phải có **redirect/host allowlist**. TLS hostname verification áp dụng cho hostname đích của từng TLS connection, nhưng nó **không bảo đảm** redirect target được business cho phép nhận token.

Đừng forward `Authorization` sang host không thuộc allowlist, đừng cho client theo redirect từ HTTPS xuống HTTP, và đừng cho input người dùng quyết định toàn bộ URL (SSRF). Với outbound HTTP, DNS rebinding, IP nội bộ, cloud metadata service và private network là các rủi ro khác **không được TLS tự chặn**.

### 9.4. Corporate proxy

Một TLS-intercepting proxy được quản trị có thể trình cert được ký bằng corporate CA. Nếu tổ chức phê duyệt, client trust policy có thể cần CA đó; nếu chưa rõ, coi việc chain đột ngột đổi là tín hiệu phải điều tra, không tự thêm trust-all. Kiểm SNI, hostname, HTTP CONNECT và proxy routing theo đúng môi trường.

## 10. Rotation CA, leaf certificate và khả năng reload

Phân biệt:

1. **Renew server leaf:** bên server thay cert mới có chain/SAN hợp lệ.
2. **Rotate issuing/root CA:** cả server lẫn client có thể cần trust material mới.
3. **Rotate client mTLS keypair:** bên client phải thay identity; server phải trust nó.
4. **Reload SSL context:** HTTP client/connector đang chạy phải dùng material mới cho handshake mới.

### Khi nào client phải đổi truststore?

| Thay đổi | Có cần client truststore mới? |
| --- | --- |
| Leaf cert gia hạn, vẫn cùng CA root được trust | Thường **không**, nếu SAN/chain hợp lệ |
| Intermediate mới dưới cùng root được trust | Thường không, nếu server gửi chain phù hợp |
| Root CA được thay hoàn toàn | Có thể cần thêm CA mới và loại CA cũ theo kế hoạch |
| Server self-signed certificate đổi | Nếu client trust trực tiếp leaf cũ, cần cập nhật trust |
| Server đổi hostname hoặc SAN | Cần cert hợp hostname mới; truststore không giải quyết sai SAN |
| Client mTLS cert hết hạn | Cập nhật keystore client; không chỉ truststore |

### Kế hoạch không gián đoạn

1. Inventory hostname:port, SNI, TLS terminator, CA, cert chain và clients.
2. Cấp cert/CA mới; kiểm SAN, validity, key usage, chain và policy.
3. Triển khai client truststore có thể tin **old + new CA** trong giai đoạn giao nhau nếu PKI policy cho phép.
4. Test trên canary client bằng **new TLS connection** và xác minh hostname.
5. Triển khai server leaf/chain mới, kiểm từng pod/region qua handshake mới.
6. Nếu HTTP client không tự reload, rebuild client/connector/pool hoặc rolling restart theo version được hỗ trợ.
7. Giám sát PKIX errors, TLS handshake failure, latency và readiness.
8. Chỉ gỡ CA cũ/identity cũ khi toàn bộ thành phần đã được xác nhận.

**Không khẳng định** `spring.ssl.bundle.pem.*.reload-on-update=true` sẽ tự cập nhật mọi `RestClient`, `WebClient` hoặc third-party HTTP SDK. Tài liệu Spring Boot nêu hot reload của các consumer tương thích, đặc biệt Tomcat/Netty embedded web servers; outbound client cần được xác minh riêng theo connector, pool lifecycle và version. Thay file trên disk không phải bằng chứng TLS context đang dùng mới.

### Giám sát từ endpoint thực

Quan sát cả:

- Cert trên nguồn phát hành/secret mount.
- Cert **đang được phục vụ** tới URL thật, có SNI/hostname/port đúng.
- Chain/intermediate, expiry, fingerprint, serial của endpoint trên từng region.
- Client-side handshake errors từ JVM, không chỉ kết quả cURL trên laptop.

Một file trên disk có notAfter năm sau nhưng server vẫn trình cert hết hạn là lỗi deploy/reload/route. Theo dõi đầy đủ cả cert server và cert client mTLS nếu sử dụng.

## 11. CLI kiểm chứng live endpoint

### cURL

~~~bash
curl -v https://partner.example.com/health
~~~

Với CA nội bộ:

~~~bash
curl -v --cacert /etc/myapp/trust/partner-ca.pem \
  https://partner.example.com/health
~~~

`curl --cacert` không cấu hình Java `cacerts` hoặc Spring Boot SSL bundle; mỗi thư viện có thể dùng CA/trust provider khác. cURL thành công không có nghĩa HTTP client của JVM đã apply đúng bundle.

### OpenSSL SNI, chain và hostname

~~~bash
openssl s_client \
  -connect partner.example.com:443 \
  -servername partner.example.com \
  -CAfile /etc/myapp/trust/partner-ca.pem \
  -verify_hostname partner.example.com \
  -verify_return_error </dev/null
~~~

Lệnh kiểm tra trust và hostname theo OpenSSL trong môi trường đang chạy. Để inspect leaf server gửi:

~~~bash
openssl s_client \
  -connect partner.example.com:443 \
  -servername partner.example.com \
  -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout \
      -subject -issuer -serial -dates -fingerprint -sha256 \
      -ext subjectAltName
~~~

Pipeline thứ hai chỉ xem metadata; nó **không** tự chứng minh trust chain + hostname đúng nếu không cấu hình verify. Muốn kiểm thời hạn file cert cụ thể:

~~~bash
openssl x509 -in /etc/myapp/trust/partner-ca.pem \
  -noout -dates -fingerprint -sha256
~~~

Chú ý: đây là **CA file**, không phải nhất thiết là leaf server hiện hành.

### Java X509Certificate

Java có `java.security.cert.X509Certificate`:

~~~java
// Fragment, không phải chương trình Java độc lập.
cert.checkValidity();
System.out.println(cert.getSubjectX500Principal().getName());
System.out.println(cert.getNotAfter().toInstant());
~~~

`checkValidity()` chỉ kiểm cửa sổ ngày hiệu lực. Nó **không** xác thực chain tới truststore và không so hostname SAN. Đừng tự viết một bộ “verify” chỉ đọc Subject/CN và trả true, thay thế JSSE.

### JVM handshake diagnostics

Trong môi trường test có kiểm soát:

~~~bash
java -Djavax.net.debug=ssl,handshake \
  -jar target/ssl-bundle-httpclient-demo-0.0.1-SNAPSHOT.jar
~~~

SSL debug có thể in nhiều thông tin handshake/cert và làm giảm hiệu suất. Không bật dài hạn ở production, không log Basic/Bearer token, private key, password hoặc TLS session secrets.

## 12. Cách thiết kế outbound HTTP clients trong production

~~~text
Application
 |
 +-- publicPartnerClient (RestClient)
 |      baseUrl=https://api.public-partner.example
 |      trust=default trusted roots nếu phù hợp
 |
 +-- billingClient (RestClient)
 |      baseUrl=https://billing.internal.example
 |      bundle=billing-ca
 |
 +-- eventStreamClient (WebClient)
 |      baseUrl=https://events.partner.example
 |      bundle=events-ca
 |      reactive pool + response timeouts
 |
 +-- paymentsClient (RestClient)
        baseUrl=https://payments.internal.example
        bundle=payments-mtls
        truststore=payments CA
        keystore=client identity key/cert
~~~

Giữ **baseUrl, trust policy, token/credentials và timeout** theo từng partner; không gộp hết vào một RestClient dùng global trust-all hoặc chung Authorization interceptor.

### Bảo vệ secrets

- Trust certificates public có thể được đóng gói theo nhu cầu, nhưng trust policy và nguồn cert phải được quản trị.
- Private keys, keystore passwords, client credentials, token phải nằm trong secret manager/volume/ACL tối thiểu; tránh repo, JAR, Docker image và logs.
- Một environment variable không tự bảo đảm secret an toàn nếu process dump, diagnostics, shell history hoặc quyền hệ thống có thể đọc.
- Không dùng `NoopHostnameVerifier`, TrustManager chấp nhận mọi X509 cert hoặc `curl -k` để “giải quyết” lỗi TLS.
- Không tự pin một leaf certificate cố định trong production mà không có kế hoạch cert rotation; cân nhắc CA trust hoặc pinning có khả năng rollover.

### Khả năng phục hồi

- Set connect/handshake/response timeouts hợp lý, giới hạn connection pool và concurrency.
- Đặt retry cho lỗi tạm thời **có điều kiện idempotency**; không retry POST payment vô hạn chỉ vì có SSL/network error.
- Không retry PKIX/hostname mismatch như một lỗi transient mà che mất incident.
- Kiểm circuit breaker, DNS refresh, proxy và egress policy.
- Giám sát TLS failure, certificate expiry, remote API latency và response status riêng.
- Đảm bảo SSRF protections trên bất kỳ endpoint nào cho phép user chọn destination URL.

## 13. Những lỗi cấu hình thường gặp

| Sai lầm | Vì sao không đúng? | Cách sửa |
| --- | --- | --- |
| Chỉ đặt `server.ssl.bundle=...` | Đây là cấu hình **inbound** server TLS, không tự cấu hình outbound HTTP client | Dùng RestClientSsl/WebClientSsl hoặc builder SSL |
| Khai SSL bundle nhưng không apply | Client có thể vẫn dùng JVM defaults | Apply từ tên bundle cụ thể |
| Đưa server private key vào client truststore | Sai trust boundary, rò bí mật | Truststore chỉ chứa public CA/cert phù hợp |
| Có CA đúng nhưng hostname SAN sai | CA trust không thay hostname verification | Sửa URL hoặc cấp lại cert có SAN |
| Dùng URL IP nhưng cert chỉ có DNS SAN | IP/DNS là các SAN types khác | Dùng hostname DNS hoặc cấp IP SAN |
| Chỉ kiểm `CN` | Không thay đầy đủ hostname verification chuẩn | Dùng JSSE/Spring HTTP client checks |
| `curl --cacert` pass nhưng JVM PKIX fail | Khác CA providers/SSL bundle/route/proxy | Xem client bean, trust material, live chain |
| Dùng trust-all/NoopHostnameVerifier | MITM có thể mạo danh server | Sửa CA/chain/SAN thay vì bỏ bảo vệ |
| Chỉnh global `cacerts` cho một partner | Mở rộng trust và tác động các clients khác | Bundle theo partner |
| RestClientSsl apply sau custom factory | Có thể thay factory và mất timeout/proxy | Kết hợp HttpClientSettings/FactoryBuilder đúng |
| WebClient tự block trên event loop | Thắt cổ chai/nonblocking semantics bị phá | Trả Mono/Flux, dùng scheduler khi thật cần |
| Chỉ copy file CA mới rồi kỳ vọng hot reload | Client pool/context có thể vẫn dùng material cũ | Rebuild/restart client và test new handshake |
| HTTP 401 sau TLS được hiểu là chứng thư sai | Lẫn HTTP auth với TLS | Kiểm token/permission |
| mTLS nhưng chỉ có truststore | Thiếu client identity khi server yêu cầu | Thêm keystore client cert/key |
| Cấu hình redirect tới host bất kỳ | Lộ Authorization/SSRF | Allowlist scheme/host/port, hạn chế redirect |
| Trust cert không rõ nguồn | Mở rộng trust cho attacker | Xác minh nguồn CA/PKI, fingerprint, ownership |
| Xem cert local mà không xem live endpoint | Một pod/edge có thể còn dùng cert cũ | Probe handshake với SNI đúng, nhiều instances |

## 14. Checklist triển khai và QA

- [ ] Đã biết endpoint URL thực và TLS terminator (server trực tiếp hay edge/proxy)?
- [ ] Client tin CA/certificate đúng, chain và intermediate đầy đủ, SAN khớp URL?
- [ ] Chứng thư đang trong thời gian `notBefore/notAfter`, EKU và crypto policy phù hợp?
- [ ] Dùng SSL bundle đúng loại PEM/JKS, tên bundle chính xác, không trùng/conflict?
- [ ] HTTP client bean thực sự apply bundle: RestClientSsl, WebClientSsl hoặc RestTemplateBuilder?
- [ ] Không có code trust-all/disable hostname verification?
- [ ] Server-auth thông thường không chứa client private key; mTLS có key/cert đúng khi cần?
- [ ] Truststore/keystore/password/identity được quản lý đúng secret policy và quyền OS?
- [ ] Có negative tests cho wrong CA, wrong SAN, expired leaf, incomplete chain?
- [ ] Đã kiểm CA trust trong JVM/connector khác với cURL/OS có thể như thế nào?
- [ ] Khi có proxy/redirect, auth tokens không bị chuyển sang host ngoài allowlist?
- [ ] Timeout, pool, DNS/proxy, retry được test sau khi apply SSL bundle?
- [ ] Có kế hoạch CA rotation, canary, old/new trust overlap và rollback?
- [ ] Đã kiểm handshake **mới** sau khi reload hoặc rolling restart?
- [ ] Có monitor expiry trên server đích thực sự, không chỉ đọc trust file tại client?
- [ ] Không log token, private key, password, TLS secrets hoặc debug handshake quá mức?
- [ ] Có phép thử trên từng pod/region, không kết luận từ một request qua load balancer?

## 15. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** RestClient gọi HTTPS internal API bị `PKIX path building failed`. Có nhất thiết phải tạo client certificate không?

**Đáp án:** Không. Đây thường là lỗi client **không tin chain của server**. Xem CA/truststore, intermediates, bundle, proxy và hostname. Chỉ cần client keypair nếu server yêu cầu mTLS.

**Câu 2.** Khai `spring.ssl.bundle.pem.partner.truststore.certificate=...` là đủ để mọi RestClient tự tin CA đó?

**Đáp án:** Không. Phải áp bundle vào client, chẳng hạn `builder.apply(ssl.fromBundle("partner"))`.

**Câu 3.** Server certificate được CA tin cậy nhưng SAN chỉ có `api.example.com`, client gọi `orders.example.com`. Có thể tắt hostname verification không?

**Đáp án:** Không. Certificate phải hợp đúng hostname của URL, ngoài chain trust.

**Câu 4.** Vì sao certificate có `DNS:localhost` chưa đủ cho `https://127.0.0.1`?

**Đáp án:** Vì kết nối qua IP cần SAN loại IP Address cho IP tương ứng; DNS SAN không tự thay thế IP SAN.

**Câu 5.** Trong Spring Boot 4.1.2, `RestClientSsl` nằm ở đâu?

**Đáp án:** `org.springframework.boot.restclient.autoconfigure.RestClientSsl`.

**Câu 6.** Vì sao có thể mất HTTP client timeout/proxy sau khi apply SSL bundle?

**Đáp án:** Javadoc RestClientSsl cho biết apply có thể thay thế ClientHttpRequestFactory trước đó. Cần tích hợp settings/factory đúng API và test.

**Câu 7.** Khi mTLS, client chỉ cần keystore/private key mà không cần truststore/server checks?

**Đáp án:** Không. mTLS yêu cầu client vẫn kiểm chứng server, đồng thời server kiểm client identity.

**Câu 8.** cURL đã chạy với `--cacert` và pass, nhưng JVM vẫn báo PKIX. Có mâu thuẫn không?

**Đáp án:** Không. cURL và JVM có thể dùng truststore, proxy, SNI hoặc CA provider khác. Kiểm đúng HTTP client bean/bundle đang chạy.

**Câu 9.** Đổi file cert ở truststore có tự làm mọi RestClient/WebClient đang sống dùng CA mới?

**Đáp án:** Không được mặc định. Phải kiểm connector/SSLContext lifecycle, pool và cơ chế refresh, sau đó test new handshake.

**Câu 10.** HTTPS thành công nhưng response là HTTP 403, có nên sửa truststore?

**Đáp án:** Không. 403 là access control ở tầng ứng dụng sau TLS. Kiểm scope, role, token hoặc mTLS identity mapping.

## 16. Tài liệu chính thức và tiêu chuẩn

- [Spring Boot — SSL bundles (PEM, JKS, truststore, SslBundles)](https://docs.spring.io/spring-boot/reference/features/ssl.html).
- [Spring Boot — Calling REST Services, RestClientSsl/WebClientSsl/RestTemplateBuilder](https://docs.spring.io/spring-boot/reference/io/rest-client.html).
- [Spring Boot 4.1.2 API — RestClientSsl](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/autoconfigure/RestClientSsl.html).
- [Spring Boot 4.1.2 API — RestTemplateBuilder.sslBundle](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/restclient/RestTemplateBuilder.html).
- [Spring Boot — Application Properties: spring.ssl.bundle.*](https://docs.spring.io/spring-boot/appendix/application-properties/).
- [Spring Boot 4.1.2 release announcement](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html).
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280).
- [RFC 6125 — Service Identity Verification](https://www.rfc-editor.org/rfc/rfc6125).
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446).
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html).
- [Oracle Java 17 — X509Certificate API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html).

**Kết luận:** Khi Spring Boot **gọi** HTTPS, phải xác minh **đúng server đích**, không chỉ một kênh được mã hóa. Đặt trust material trong SSL bundle PEM/JKS, áp bundle theo đúng RestClient/WebClient/RestTemplate, giữ CA chain + hostname SAN + validity checks, và test cả kết nối thành công lẫn các trường hợp sai CA/hostname. Chỉ thêm private key vào client khi thực sự cần mTLS. Với rotation, xác nhận SSLContext/connection pool và chứng thư **đang phục vụ** bằng một handshake mới, không suy luận từ việc file trên đĩa đã đổi.