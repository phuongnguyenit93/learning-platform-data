# Xác thực chứng thư X.509 và ánh xạ chứng thư thành người dùng

> **Module:** Spring Security – reactive  
> **Nhóm kiến thức:** Xác thực mở rộng  
> **Đề bài:** Xác thực chứng thư X.509 và ánh xạ chứng thư thành người dùng.  
> **Stack ví dụ:** Java 17+, Spring WebFlux, Spring Security 6.5.11, Spring Boot 3.5.16, Reactor Netty, JUnit 5 và WebTestClient.

## 1. Vấn đề thực tế: một chứng thư không tự cấp quyền nghiệp vụ

Giả sử API báo cáo được gọi từ các dịch vụ/ứng dụng nội bộ qua HTTPS. Thay vì yêu cầu `Authorization: Basic ...` hoặc `Authorization: Bearer ...`, máy chủ yêu cầu client trình **chứng thư X.509** khi bắt tay TLS (*mutual TLS*, viết tắt **mTLS**).

Máy chủ kiểm tra rằng client sở hữu private key tương ứng với chứng thư và chứng thư có chuỗi tin cậy hợp lệ. Spring Security sau đó đọc thông tin chứng thư từ TLS request, trích xuất một **principal identifier**, tìm bản ghi người dùng/service tương ứng và nạp roles/authorities hiện hành.

Ví dụ:

```text
Client sở hữu private key + client certificate
       |
       | TLS handshake: trình certificate, chứng minh sở hữu private key
       v
Reactor Netty HTTPS server (trusted CA, TLS policy, client-auth=need)
       |
       | TLS xác minh certificate chain / thời hạn / chữ ký / EKU theo cấu hình
       | (thất bại ở đây => handshake không hoàn tất)
       v
Spring Security WebFlux x509 authentication
       |
       | X509PrincipalExtractor: SAN URI
       | spiffe://example.test/users/alice  --->  "alice"
       v
ReactivePreAuthenticatedAuthenticationManager
       |
       | ReactiveUserDetailsService: findByUsername("alice")
       | kiểm tra account enabled/locked/expired
       | nạp ROLE_READER
       v
Authenticated principal + authorities trong Reactor Context
       |
       | AuthorizationWebFilter: /api/reports cần ROLE_READER
       v
Controller / service xử lý báo cáo
```

**Ba câu hỏi tách biệt:**

1. **Chứng thư có đáng tin và private key có đúng chủ thể đang kết nối không?** → TLS/trust store/PKI.
2. **Chứng thư hợp lệ này được ánh xạ đến tài khoản nào?** → `X509PrincipalExtractor` và chính sách subject/SAN.
3. **Tài khoản đó có được phép gọi endpoint này không?** → user directory/account status/roles và Spring Security authorization.

Một certificate hợp lệ từ CA tin cậy **không tự** có `ROLE_ADMIN`. Việc tin CA là tin **khả năng phát hành chứng thư theo một chính sách**, còn quyền nghiệp vụ phải do ứng dụng quyết định.

### 1.1. Kết quả học tập

Sau bài, bạn có thể:

- Giải thích mTLS/X.509, trust anchors, leaf certificate, issuer/subject, SAN, EKU, key usage, serial number, thumbprint và private key.
- Phân biệt handshake TLS với WebFlux authentication: lỗi TLS có thể không tạo HTTP 401/403.
- Sử dụng `ServerHttpSecurity.x509(Customizer)`, `X509PrincipalExtractor`, `ReactivePreAuthenticatedAuthenticationManager`, `ReactiveUserDetailsService`.
- Hiểu mapping mặc định theo CN và cách làm chặt hơn với **Subject Alternative Name URI**.
- Viết `SanUriPrincipalExtractor` kiểm soát namespace, cú pháp, ambiguity và thất bại khi thiếu identity.
- Đọc chứng thư từ **trusted TLS `SslInfo`**, không từ `X-Client-Cert` HTTP header không đáng tin.
- Cấu hình Spring Boot `server.ssl.client-auth=need`, truststore/keystore và tạo chứng thư **chỉ cho máy học** bằng OpenSSL/keytool.
- Phân biệt certificate-authentication với OAuth2 Resource Server JWT/opaque, Basic và session.
- Viết tests cho mapping, account lock, role, HTTP security bằng TLS giả lập *chỉ trong test*, và biết các tests đó **không chứng minh handshake TLS thực tế**.
- Vận hành CA rotation, certificate revocation, identity collision, proxy termination và observability mà không làm lộ private keys.

## 2. X.509, PKI và mutual TLS

### 2.1. Chứng thư chứa gì?

Một chứng thư X.509 thường gồm:

| Trường | Ý nghĩa | Chú ý |
| --- | --- | --- |
| Subject | Danh tính do CA công bố, ví dụ `CN=alice,O=Example` | CN không luôn là identity tốt nhất |
| Issuer | CA đã phát hành chứng thư | Tên issuer không đủ: phải kiểm tra signature/chain |
| Serial Number | Số định danh certificate dưới issuer | Có thể dùng cùng issuer để audit/revoke |
| Validity | `notBefore` và `notAfter` | Đồng bộ đồng hồ; không dùng cert hết hạn |
| Subject Alternative Name (SAN) | DNS, email, URI, IP... | Thích hợp đưa identity có namespace |
| Key Usage | Quyền dùng key, ví dụ `digitalSignature` | Phải phù hợp với TLS |
| Extended Key Usage (EKU) | Ví dụ `clientAuth` / `serverAuth` | Client certificate cần `clientAuth` theo policy |
| Basic Constraints | CA hay end-entity | Leaf không nên được cấp quyền ký CA |
| Public key | Dùng trong xác minh chữ ký/chứng minh sở hữu key | Public key không phải bí mật |
| Signature | CA ký nội dung certificate | Cần chain đến trust anchor đáng tin |

**Private key của client không nằm trong certificate**. Khi mTLS, client chứng minh mình giữ private key qua các bản tin cryptographic của TLS; không gửi private key lên mạng. Server kiểm tra chứng thư bằng trust anchors và TLS policy. Nếu client certificate chỉ là chuỗi PEM được gửi trong HTTP body/header, **đó không phải mTLS**.

### 2.2. Một chiều TLS và hai chiều TLS

**HTTPS thông thường:** client xác minh chứng thư server và bảo mật kênh truyền, còn server xác thực client qua token/session/password hoặc để anonymous.

**mTLS:** ngoài bước trên, server yêu cầu client certificate và xác minh certificate đó, nhờ vậy hai đầu cùng có cryptographic authentication. Tuy nhiên mTLS **không tự giải quyết** role/tenant/resource authorization.

```text
TLS thông thường:
  Browser/Client --- verify server certificate ---> HTTPS Server

mTLS:
  Client <--- verify server certificate --- HTTPS Server
  Client --- present trusted client cert -----> Server
  Client --- prove key possession -----------> Server
  Application --- cert identity -> app user ---> Authorization rules
```

### 2.3. server.ssl.client-auth: need, want, none

| Giá trị | TLS handshake | Hệ quả |
| --- | --- | --- |
| `need` | Yêu cầu client certificate bắt buộc | Không có cert/không đáng tin thường thất bại trước HTTP |
| `want` | Yêu cầu nhưng không bắt buộc | Phù hợp hệ thống hỗn hợp, song endpoint phải kiểm tra identity |
| `none` | Không yêu cầu client certificate | Bật Spring `.x509(...)` riêng không thể tạo mTLS |

Trong demo, `need` áp dụng **cho cả cổng HTTPS** — kể cả đường `/health`. `permitAll("/health")` chỉ cho anonymous ở tầng Spring **sau khi TLS handshake thành công**. Với `client-auth=need`, client không trình chứng thư có thể không nhận được **bất kỳ HTTP status** nào vì TLS bị từ chối ngay trước khi request được chuyển tới WebFlux.

### 2.4. Truststore khác keystore

- **Server keystore:** private key và server certificate/chain của chính server, để server chứng minh danh tính với client.
- **Server truststore:** danh sách CA/public trust anchors được server chấp nhận để xác minh **client certificates**.
- **Client private key/cert:** credential của client để hoàn tất mTLS.
- **Client CA trust:** nơi client lấy trusted server CA để xác minh HTTPS server, tránh bị MITM.

Không thêm tùy ý một root CA công khai khổng lồ vào server truststore cho client-auth khi bạn chỉ định chấp nhận internal clients; nguyên tắc **least trust** quan trọng hơn “nhiều CA thì ít lỗi”.

## 3. Luồng xác thực X.509 trong Spring WebFlux

Spring Security reactive X.509 cung cấp cấu hình:

```java
@Bean
SecurityWebFilterChain springSecurity(ServerHttpSecurity http) {
    return http
        .x509(Customizer.withDefaults())
        .authorizeExchange(exchanges ->
            exchanges.anyExchange().authenticated())
        .build();
}
```

Đây là snippet đặt trong `@Configuration`, cần import Spring WebFlux security classes. Trong Spring Security 6.5.11, DSL `x509(Customizer)` dùng đúng kiểu WebFlux; tránh `http.x509()` không tham số vì đường DSL đó đã bị deprecated trong nhánh 6.x.

Khi client certificate hợp lệ đã được TLS chấp nhận và exposed qua `ServerHttpRequest.getSslInfo().getPeerCertificates()`, X.509 authentication filter của Spring:

1. Nhận chain client certificate từ thông tin TLS của request.
2. Dùng `X509PrincipalExtractor` để lấy principal đại diện cho certificate.
3. Chuyển principal thành authentication request kiểu pre-authenticated.
4. Gọi `ReactiveAuthenticationManager` phù hợp.
5. Nếu account hợp lệ, tạo authenticated principal và authorities trong Spring Security context.
6. Quy tắc `authorizeExchange` quyết định endpoint có được truy cập hay không.

**Pre-authenticated** nghĩa là tầng TLS/upstream tin cậy **đã xác thực credential cryptographically**, sau đó Spring Security chỉ ánh xạ principal và kiểm tra account/roles. Không có nghĩa ứng dụng bỏ qua bước kiểm tra account status hoặc cho phép mọi certificate tự trở thành admin.

### 3.1. Những API cốt lõi

| API | Package | Vai trò |
| --- | --- | --- |
| `ServerHttpSecurity` | `org.springframework.security.config.web.server` | Reactive security DSL |
| `SecurityWebFilterChain` | `org.springframework.security.web.server` | Filter chain WebFlux |
| `X509PrincipalExtractor` | `org.springframework.security.web.authentication.preauth.x509` | `Object extractPrincipal(X509Certificate)` |
| `SubjectX500PrincipalExtractor` | Cùng package | Trích CN hoặc emailAddress theo thiết kế mặc định mới |
| `ReactivePreAuthenticatedAuthenticationManager` | `org.springframework.security.web.server.authentication` | Tra user, kiểm tra khóa/vô hiệu/hết hạn, nạp authorities |
| `PreAuthenticatedAuthenticationToken` | `org.springframework.security.web.authentication.preauth` | Authentication credential đã được lớp upstream xác minh |
| `ReactiveUserDetailsService` | `org.springframework.security.core.userdetails` | Tìm UserDetails theo principal |
| `MapReactiveUserDetailsService` | Cùng package | Kho người dùng in-memory cho demo |
| `ReactiveSecurityContextHolder` | `org.springframework.security.core.context` | Đọc authentication từ Reactor Context |
| `SslInfo` | `org.springframework.http.server.reactive` | TLS session ID và peer X.509 certificate chain |

### 3.2. Vì sao không đọc chứng thư từ header?

Một request HTTP có thể chứa:

```http
X-Client-Cert: CN=admin
X-SSL-Client-DN: CN=admin
X-User: admin
```

Đó là **dữ liệu do client tự gửi**, hoàn toàn không chứng minh client giữ private key. Không dùng những headers đó để cấp `ROLE_ADMIN`. Nếu TLS termination xảy ra tại API gateway, backend có thể cần **hợp đồng identity forwarding được bảo vệ riêng**: gateway phải tự xác minh certificate, xóa header giả từ client, ký/ràng buộc metadata nếu cần, dùng mTLS riêng gateway→backend, chỉ trust traffic từ gateway qua network policy. Bật `.x509(...)` ở backend không tự hồi sinh TLS peer certificate khi gateway đã chấm dứt TLS ở phía trước.

## 4. Ánh xạ chứng thư thành người dùng

Xác thực **certificate** và ánh xạ **principal của ứng dụng** là hai bước. Một certificate có thể chứa `CN=alice` hoặc SAN URI `spiffe://example.test/users/alice`, nhưng ứng dụng phải biết giá trị nào được chấp nhận và tài khoản nào tương ứng.

### 4.1. Ánh xạ mặc định theo CN

Theo tài liệu Spring Security reactive, default principal extractor là `SubjectX500PrincipalExtractor`, lấy `CN` trong Subject X.500; default authentication manager là `ReactivePreAuthenticatedAuthenticationManager`, kiểm tra account có tồn tại, không bị khóa/vô hiệu/hết hạn.

Ví dụ conceptual:

```text
Client certificate Subject: CN=alice,O=Example
               |
               v
SubjectX500PrincipalExtractor
               |
               v
principal "alice"
               |
               v
ReactiveUserDetailsService.findByUsername("alice")
               |
               v
UserDetails(alice, ROLE_READER)
```

Nếu người dùng là email được biểu diễn qua distinguished name, extractor có `setExtractPrincipalNameFromEmail(true)`. Chỉ dùng khi **chính sách cấp chứng thư** đảm bảo trường email không thể bị mạo danh/trùng lặp; không suy email ở một issuer bất kỳ là identity global.

### 4.2. Bảo mật CN và CVE-2026-47838

Tháng 6/2026 Spring công bố **CVE-2026-47838**, liên quan cách `SubjectDnX509PrincipalExtractor` đời cũ phân tích một số `CN` bất thường, có nguy cơ ánh xạ sang username không chính xác. Nhánh Spring Security **6.5.0–6.5.10** nằm trong phạm vi ảnh hưởng và bản sửa OSS cho nhánh này là **6.5.11**. Class `SubjectDnX509PrincipalExtractor` đã deprecated; khuyến nghị dùng `SubjectX500PrincipalExtractor`.

**Bài học an toàn:** Không tự parse `certificate.getSubjectDN().getName()` bằng regex kiểu `CN=(.*?)` để xác định identity. Distinguished Name có escaping, thứ tự RDN, multi-valued RDN và những giá trị bất thường. Cần dùng parser chuẩn `X500Principal` hoặc tốt hơn là identity SAN/CA policy đã định nghĩa rõ.

Trong ví dụ runnable sau, ta chọn **SAN URI có namespace riêng** để minh họa một identity contract chặt hơn. Không phải mọi hệ thống đều bắt buộc SAN URI; quan trọng là nguồn identity do **CA được kiểm soát** cấp và mapping không nhập nhằng.

### 4.3. Ánh xạ bằng Subject Alternative Name URI

Một client certificate do CA nội bộ phát hành có extension:

```text
Subject: CN=Alice Laptop,O=Example
X509v3 Subject Alternative Name:
    URI:spiffe://example.test/users/alice
Extended Key Usage:
    TLS Web Client Authentication
```

Application mapping:

```text
SAN URI spiffe://example.test/users/alice
   |
   +-- scheme = spiffe
   +-- trust domain = example.test
   +-- path = /users/alice
   +-- query/fragment/userinfo/port không được chấp nhận
   +-- username pattern = [a-z][a-z0-9-]{0,31}
   |
   v
username = alice -> ReactiveUserDetailsService -> UserDetails
```

**Lưu ý:** `spiffe://...` ở đây là **quy ước nhận diện URI trong ví dụ**, không khẳng định ứng dụng đã triển khai đầy đủ SPIFFE Workload API, SPIRE hay workload attestation. Dùng một trust domain và certificate issuance policy phù hợp. Khi CA có thể cấp URI `/users/admin` tùy ý cho bất kỳ khách hàng nào, mapping sẽ nguy hiểm **dù code parse đúng**; phải bảo vệ quá trình đăng ký và phát hành chứng thư.

### 4.4. Các lựa chọn mapping trong sản phẩm thật

| Kiểu mapping | Điểm mạnh | Điều phải kiểm soát |
| --- | --- | --- |
| CN trong X.500 Subject | Dễ bắt đầu, Spring hỗ trợ sẵn | RDN parser an toàn, không trùng CN, CA issuance |
| SAN RFC822 email | Dễ gắn account directory | Email mutable/alias, issuer và tenant |
| SAN URI theo namespace | Identity rõ ràng, support workload/service IDs | Chỉ trust domain allowlist, path format, uniqueness |
| Serial + Issuer | Certificate-specific mapping, audit/revocation | Rotation certificate phải cập nhật mapping |
| Public-key fingerprint/SPKI pin | Ràng buộc key cụ thể | Key rotation, pin management |
| SAN URI + tenant + issuer | Tốt cho nhiều tenants | Cần registry/lookup có thẩm quyền |
| Header `X-Client-Cert` tự khai | **Không đáng tin** | Không dùng làm bằng chứng TLS |

**Không** hardcode role bằng tên CN, ví dụ `if (cn.equals("admin")) ROLE_ADMIN`. Role phải đến từ **user directory được quản trị**, và certificate issuing policy phải ngăn giả mạo SAN/CN.

## 5. Cấu hình TLS cấp máy chủ trước khi bật x509()

Spring Security `.x509(...)` không tạo CA, không tự bật HTTPS và không thay Netty TLS handshake. Phần quan trọng đầu tiên là Spring Boot SSL configuration:

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:certs/server.p12
    key-store-type: PKCS12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD:localpass}
    trust-store: file:certs/trust.p12
    trust-store-type: PKCS12
    trust-store-password: ${SERVER_TRUSTSTORE_PASSWORD:localpass}
    client-auth: need
```

Trong demo, `localpass` là password **chỉ dùng cho key/truststore cục bộ**. Nó **không** phù hợp cho production; thực tế phải quản lý keystore password và private key qua secret manager/file permissions/rotation. `file:certs/...` là đường dẫn **tương đối với thư mục chạy Maven**, và các files này được tạo bằng lệnh OpenSSL/keytool ở mục 12.

**Không dùng** `server.ssl.client-auth: need` nếu chưa có truststore nhận diện đúng client CA — Netty có thể không tin bất kỳ certificate nào hoặc ứng dụng không khởi động theo cấu hình.

### 5.1. Certificate chain được kiểm tra tại TLS, account status tại Spring

| Bước | Nếu lỗi | Hệ quả |
| --- | --- | --- |
| Server private key / certificate không hợp lệ | Không phục vụ HTTPS | Server khởi động lỗi hoặc bắt tay TLS lỗi |
| Client không gửi cert khi `need` | TLS client auth thất bại | Thường **không có HTTP response** |
| Cert ký bởi CA không nằm trong truststore | TLS trust thất bại | Thường không có HTTP response |
| Cert hết hạn, không đúng key usage, chain sai | TLS policy reject (tùy provider) | Không chạy đến Spring controller |
| Cert đã qua TLS nhưng SAN không hợp policy app | Spring authentication reject | Request bị từ chối; HTTP status tùy entry point |
| SAN hợp lệ nhưng account không tồn tại | Spring pre-auth lookup reject | HTTP authentication failure |
| Account locked/disabled | Manager từ chối | Không có quyền truy cập |
| Account hợp lệ nhưng thiếu role | AuthorizationWebFilter từ chối | Thường HTTP 403 |
| Account hợp lệ, role đúng | Controller xử lý | Thường HTTP 200 |

Trong một reverse proxy, lỗi có thể được chuyển sang trang/status của proxy. Vì vậy đừng máy móc kết luận “mTLS luôn trả HTTP 401 khi không có cert”: handshake **có thể thất bại trước cả HTTP**.

### 5.2. Client-auth=want khi nào?

`want` cho phép TLS connection không có chứng thư, hữu ích trên cùng cổng có public endpoints hoặc cơ chế auth khác. Tuy nhiên nếu route nhạy cảm yêu cầu X.509, bạn phải cấu hình Spring authorization chain để **không** fallback sang anonymous hoặc Basic ngoài ý muốn. Nếu toàn bộ cổng chỉ phục vụ mTLS, `need` thường dễ audit hơn.

## 6. Project Java 17+: WebFlux X.509 + SAN URI + user lookup

Dự án sử dụng **Spring Boot 3.5.16** và chỉ định **Spring Security 6.5.11** trong BOM để tránh các bản Spring Security 6.5 bị ảnh hưởng bởi CVE CN parser. Spring Boot 3.5.x đã kết thúc OSS support theo Spring; dùng baseline này cho học API 6.5, còn triển khai production mới nên chọn một nhánh Boot/Security đang được hỗ trợ và test migration tương ứng.

Project gồm:

```text
reactive-x509-mtls/
├── pom.xml
├── certs/                         # Tạo local bằng OpenSSL/keytool; không commit keys
│   ├── ca.crt
│   ├── ca.key
│   ├── server.p12
│   ├── trust.p12
│   ├── alice.crt / alice.key
│   ├── admin.crt / admin.key
│   ├── locked.crt / locked.key
│   └── stranger.crt / stranger.key
└── src/
    ├── main/
    │   ├── java/demo/x509/
    │   │   ├── Application.java
    │   │   ├── SanUriPrincipalExtractor.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── ApiController.java
    │   └── resources/application.yml
    └── test/java/demo/x509/
        ├── SanUriPrincipalExtractorTests.java
        ├── ReactivePreAuthManagerTests.java
        └── X509WebFluxTests.java
```

Project phân tách **ba lớp kiểm thử**: unit parser, reactive account manager và WebFlux security với peer certificates **giả lập bởi test-only WebFilter**. Thử mTLS thật qua `curl` ở mục 13 là bước riêng; unit/mock tests không thực thi handshake TLS hoặc validate truststore.

### 6.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-x509-mtls</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <!-- Dùng bản đã khắc phục CVE-2026-47838. -->
        <spring-security.version>6.5.11</spring-security.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
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

**Không cần** `spring-boot-starter-oauth2-resource-server` cho ví dụ xác thực client certificate thuần túy này. Nếu API dùng cả JWT/opaque Bearer và X.509, đó là thiết kế nhiều authentication mechanisms cần phân vùng route/security chains, không tự được tạo ra bởi `.x509(...)`.

**Kiểm tra dependency version:**

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Hãy kiểm tra `spring-security-web` và các Spring Security modules thống nhất **6.5.11**, không pha 6.5.10 với 6.5.11. Override version trong ví dụ là cách được Spring Security mô tả cho Boot-managed Maven dependency versions; không kết luận đã nâng cấp an toàn nếu chưa kiểm tra tree và chạy regression tests.

### 6.2. src/main/resources/application.yml

```yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: file:certs/server.p12
    key-store-password: ${SERVER_KEYSTORE_PASSWORD:localpass}
    key-store-type: PKCS12
    trust-store: file:certs/trust.p12
    trust-store-password: ${SERVER_TRUSTSTORE_PASSWORD:localpass}
    trust-store-type: PKCS12
    client-auth: need
```

Không dùng `https://...` trong Boot key-store path vì ở đây keystore nằm trong filesystem cục bộ. Server sẽ đọc `certs/server.p12` và `certs/trust.p12` được tạo ở mục 12; thiếu hai file này thì chạy app HTTPS thật có thể thất bại, **đó là hành vi chính xác**.

### 6.3. src/main/java/demo/x509/Application.java

```java
package demo.x509;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

## 7. Custom X509PrincipalExtractor bằng SAN URI

Thay vì parse chuỗi `CN=...`, extractor nhận đối tượng `X509Certificate` do Spring Security lấy từ trusted transport. Chỉ chấp nhận **một** SAN loại **URI (GeneralName type 6)** thuộc trust domain `example.test` với path `/users/{username}`.

### 7.1. src/main/java/demo/x509/SanUriPrincipalExtractor.java

```java
package demo.x509;

import java.net.URI;
import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.authentication.preauth.x509.X509PrincipalExtractor;

public final class SanUriPrincipalExtractor
        implements X509PrincipalExtractor {

    private static final String SCHEME = "spiffe";
    private static final String TRUST_DOMAIN = "example.test";
    private static final String PATH_PREFIX = "/users/";

    @Override
    public Object extractPrincipal(X509Certificate certificate) {
        try {
            Collection<List<?>> sans =
                certificate.getSubjectAlternativeNames();

            if (sans == null || sans.isEmpty()) {
                throw new BadCredentialsException(
                    "Client certificate has no subjectAltName");
            }

            String username = null;
            for (List<?> entry : sans) {
                if (entry.size() < 2 ||
                        !(entry.get(0) instanceof Integer tag) ||
                        tag != 6 ||
                        !(entry.get(1) instanceof String rawUri)) {
                    continue;
                }

                URI uri = URI.create(rawUri);
                String path = uri.getPath();

                if (!SCHEME.equals(uri.getScheme()) ||
                        !TRUST_DOMAIN.equals(uri.getHost()) ||
                        uri.getPort() != -1 ||
                        uri.getUserInfo() != null ||
                        uri.getRawQuery() != null ||
                        uri.getRawFragment() != null ||
                        path == null ||
                        !path.startsWith(PATH_PREFIX)) {
                    continue;
                }

                String candidate = path.substring(PATH_PREFIX.length());
                // Tránh path traversal, slash phụ, username trống hay ký tự lạ.
                if (!candidate.matches("[a-z][a-z0-9-]{0,31}")) {
                    throw new BadCredentialsException(
                        "Invalid certificate user identifier");
                }

                // Hai SAN khớp namespace => identity không rõ ràng.
                if (username != null) {
                    throw new BadCredentialsException(
                        "Ambiguous certificate user identifiers");
                }
                username = candidate;
            }

            if (username == null) {
                throw new BadCredentialsException(
                    "No trusted user URI in certificate");
            }
            return username;
        }
        catch (CertificateParsingException | IllegalArgumentException ex) {
            throw new BadCredentialsException(
                "Invalid certificate subjectAltName", ex);
        }
    }
}
```

**Các đặc tính có chủ đích:**

- Không dùng regex trên DN hoặc tin CN để làm user ID.
- Chỉ nhận SAN URI, không nhận DNS SAN/email SAN thay thế bất chợt.
- Chỉ nhận scheme `spiffe`, trust domain `example.test`, path `/users/{username}`; không có query/fragment/userInfo/port.
- Chỉ nhận username dạng ASCII lowercase, không có slash hay dấu chấm, hạn chế path confusion/normalization.
- Nếu **không có** SAN hợp lệ hoặc có **hai SAN** khớp, từ chối thay vì đoán.
- Không cấp role ngay trong parser; parser **chỉ chọn username**. Quyền đến từ user directory.
- Certificate parsing lỗi thì reject với `BadCredentialsException`.

Trong dự án nhiều tenants, đưa tenant/issuer vào identity key và restrict trust domain/CA theo tenant. Một namespace URI sạch **không thay thế** PKI issuance controls: CA phải bảo đảm chỉ Alice được cấp URI `spiffe://example.test/users/alice`.

### 7.2. Một số input và expected mapping

| SAN URI trong certificate | Kết quả |
| --- | --- |
| `spiffe://example.test/users/alice` | `alice` |
| `spiffe://example.test/users/admin` | `admin` (vẫn phải tra account role) |
| `spiffe://other.test/users/alice` | Reject: sai trust domain |
| `http://example.test/users/alice` | Reject: scheme khác |
| `spiffe://example.test/users/alice/extra` | Reject: không hợp username pattern |
| `spiffe://example.test/users/ALICE` | Reject: không hợp username pattern |
| `spiffe://example.test/users/alice?role=ADMIN` | Reject: query không được cho phép |
| Hai URI SAN cùng namespace | Reject: principal không duy nhất |
| Chỉ có CN, không có SAN | Reject trong policy project |
| Một SAN emailAddr và không có SAN URI | Reject trong policy project |

Trong production, URI normalization/punycode, PKI name constraints, các SAN extensions và phiên bản thư viện cần được threat-model cụ thể; không coi bảng này là checklist thay thế cho PKI audit.

## 8. Reactive user lookup và security configuration

### 8.1. src/main/java/demo/x509/SecurityConfiguration.java

```java
package demo.x509;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.ReactivePreAuthenticatedAuthenticationManager;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    ReactiveUserDetailsService users() {
        // Password field chỉ để hoàn thành UserDetails; không dùng cho
        // credential verification của X.509 pre-authentication.
        UserDetails alice = User.withUsername("alice")
            .password("{noop}unused-x509-only")
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}unused-x509-only")
            .roles("READER", "ADMIN")
            .build();

        UserDetails locked = User.withUsername("locked")
            .password("{noop}unused-x509-only")
            .roles("READER")
            .accountLocked(true)
            .build();

        return new MapReactiveUserDetailsService(alice, admin, locked);
    }

    @Bean
    ReactiveAuthenticationManager x509AuthenticationManager(
            ReactiveUserDetailsService users) {
        return new ReactivePreAuthenticatedAuthenticationManager(users);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager x509AuthenticationManager) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/reports").hasRole("READER")
                .pathMatchers("/api/me").authenticated()
                .anyExchange().denyAll())
            .x509(x509 -> x509
                .principalExtractor(new SanUriPrincipalExtractor())
                .authenticationManager(x509AuthenticationManager))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Điều đáng chú ý:**

1. `users()` là một **React iveUserDetailsService** (tên class chính xác: `ReactiveUserDetailsService`) với một danh bạ in-memory; real app cần R2DBC/LDAP hoặc directory service có SLA phù hợp.
2. `ReactivePreAuthenticatedAuthenticationManager(users)` kiểm tra user tồn tại và account status. Không so password vì **TLS đã xác thực client certificate**. Password `{noop}unused-x509-only` chỉ là dummy field vì `UserDetails` yêu cầu password; **không** bật Basic/form login để nó trở thành credential hợp lệ.
3. `.x509(x509 -> ...)` cấu hình extractor và manager **tường minh**. Không cần tự tạo một `WebFilter` production chuyển HTTP header thành trusted certificate.
4. `hasRole("READER")` dùng convention authority `ROLE_READER`; `hasRole("ADMIN")` dùng `ROLE_ADMIN`.
5. User `admin` có cả READER và ADMIN, `alice` chỉ READER; `locked` có role nhưng manager phải reject vì account locked.
6. `httpBasic` và `formLogin` bị tắt để **không có fallback password** trong demo cert-only. Nếu cùng server dùng OAuth2/JWT, cần thiết kế multi-chain và test no bypass.
7. Không tắt CSRF tùy tiện: client certificates có thể được browser tự trình theo cấu hình trình duyệt; với state-changing browser endpoints, **CSRF threat model vẫn tồn tại**. Demo chỉ có GET, nên để default CSRF behavior.

**Một nhắc nhở quan trọng:** X.509 không mặc nhiên đồng nghĩa “tất cả cert trusted CA đều được phép”. Nếu user `stranger` có certificate hợp lệ do CA demo phát nhưng **không có** trong `MapReactiveUserDetailsService`, ReactivePreAuthenticatedAuthenticationManager sẽ từ chối.

### 8.2. Vai trò pre-authentication và account status

Giả sử client cert đã đi qua TLS:

```text
cert SAN alice  --> "alice"  --> user found, enabled --> ROLE_READER
cert SAN admin  --> "admin"  --> user found, enabled --> ROLE_READER + ROLE_ADMIN
cert SAN locked --> "locked" --> user found, locked  --> authentication reject
cert SAN guest  --> "guest"  --> user missing         --> authentication reject
```

Với database thực, dùng `ReactiveUserDetailsService.findByUsername` không blocking; có thể tăng cường kiểm tra certificate serial/issuer/fingerprint đang được liên kết với account và tình trạng chứng thư. Nếu chỉ map username, việc CA cấp chứng thư mới cùng SAN có thể đại diện cùng account; đó là chính sách cần được định nghĩa và audit, không được vô tình xảy ra.

### 8.3. Default CN extractor với manager chuẩn để đối chiếu

Nếu CA nội bộ cấp danh tính bằng CN và bạn đã thẩm định issuance policy, Spring Security 6.5.11 hỗ trợ:

```java
// Snippet thay cho .x509(...) trong project nếu chọn chính sách CN.
SubjectX500PrincipalExtractor extractor =
    new SubjectX500PrincipalExtractor();

http.x509(x509 -> x509
    .principalExtractor(extractor)
    .authenticationManager(x509AuthenticationManager));
```

Import `SubjectX500PrincipalExtractor` từ `org.springframework.security.web.authentication.preauth.x509`. Đừng dùng `SubjectDnX509PrincipalExtractor` đã deprecated hoặc tự regex trên DN. Không áp đồng thời hai extractors bằng cách “nếu SAN fail thì tự fallback sang CN” trừ khi có identity contract và tests để không tạo đường bypass yếu hơn.

## 9. API controller: lấy principal từ Reactor Context

### 9.1. src/main/java/demo/x509/ApiController.java

```java
package demo.x509;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication ->
                "user=" + authentication.getName());
    }

    @GetMapping("/api/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin OK");
    }
}
```

`/api/me` không đọc `?user=alice` hoặc `X-User: alice`; nó chỉ lấy `Authentication` đã được filter tạo từ **certificate identity + directory lookup**. Không dùng ThreadLocal SecurityContext của Servlet trong reactive service. `Mono` sẽ được Spring WebFlux subscribe trong request pipeline.

Nếu cần trả issuer, subject, serial hoặc thumbprint cho audit, lấy từ một thành phần được kiểm soát và redact đúng; **đừng** gửi toàn bộ client certificate chain hay private key ra HTTP body.

## 10. Unit test principal extractor

Đây là tests Java 17 kiểm tra **thuật toán ánh xạ SAN URI**. Chúng dùng Mockito để mô phỏng `X509Certificate.getSubjectAlternativeNames()`; không ký cert, không xác minh TLS chain.

### 10.1. src/test/java/demo/x509/SanUriPrincipalExtractorTests.java

```java
package demo.x509;

import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class SanUriPrincipalExtractorTests {

    private final SanUriPrincipalExtractor extractor =
        new SanUriPrincipalExtractor();

    private X509Certificate certificate(String... uris)
            throws CertificateParsingException {
        X509Certificate cert = mock(X509Certificate.class);
        List<List<?>> sans = java.util.Arrays.stream(uris)
            .map(uri -> (List<?>) List.of(6, uri))
            .toList();
        when(cert.getSubjectAlternativeNames()).thenReturn(sans);
        return cert;
    }

    @Test
    void validAliceUriMapsToAlice() throws Exception {
        Object principal = extractor.extractPrincipal(
            certificate("spiffe://example.test/users/alice"));
        assertEquals("alice", principal);
    }

    @Test
    void validAdminUriMapsToAdminWithoutGrantingRole() throws Exception {
        Object principal = extractor.extractPrincipal(
            certificate("spiffe://example.test/users/admin"));
        assertEquals("admin", principal);
        // Extractor CHỈ trả username, không quyết định ROLE_ADMIN.
    }

    @Test
    void differentTrustDomainIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://attacker.test/users/alice")));
    }

    @Test
    void wrongSchemeIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("https://example.test/users/alice")));
    }

    @Test
    void extraPathIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://example.test/users/alice/admin")));
    }

    @Test
    void queryOrFragmentIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://example.test/users/alice?role=admin")));
    }

    @Test
    void ambiguousTrustedUrisAreRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(certificate(
                "spiffe://example.test/users/alice",
                "spiffe://example.test/users/admin")));
    }

    @Test
    void missingSanIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(certificate()));
    }

    @Test
    void uppercaseUsernameIsRejected() throws Exception {
        assertThrows(BadCredentialsException.class, () ->
            extractor.extractPrincipal(
                certificate("spiffe://example.test/users/ALICE")));
    }
}
```

Có **9 unit tests** cho parser (trường hợp tốt, sai scheme/domain/path/query, SAN hai identity, missing SAN, uppercase). Dù chúng pass, bạn **chưa chứng minh** mTLS đang bật hay certificate do trusted CA cấp; đây chỉ là test của một function nhận certificate object đã được caller cung cấp.

## 11. Test ReactivePreAuthenticatedAuthenticationManager

`ReactivePreAuthenticatedAuthenticationManager` là lớp **ứng dụng** sau TLS: nhận pre-authentication token, tra user và kiểm tra account status. Tests sau cố ý đưa vào `PreAuthenticatedAuthenticationToken` đã hình thành; điều đó **không chứng minh** credential từ network là an toàn — bước ấy thuộc TLS.

### 11.1. src/test/java/demo/x509/ReactivePreAuthManagerTests.java

```java
package demo.x509;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.web.server.authentication.ReactivePreAuthenticatedAuthenticationManager;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactivePreAuthManagerTests {

    private final ReactiveAuthenticationManager manager =
        new ReactivePreAuthenticatedAuthenticationManager(
            new MapReactiveUserDetailsService(
                User.withUsername("alice")
                    .password("{noop}unused")
                    .roles("READER").build(),
                User.withUsername("admin")
                    .password("{noop}unused")
                    .roles("READER", "ADMIN").build(),
                User.withUsername("locked")
                    .password("{noop}unused")
                    .roles("READER")
                    .accountLocked(true).build()));

    private static Authentication token(String username) {
        // Chỉ cho unit test manager: giả định TLS đã xác minh chứng thư.
        return new PreAuthenticatedAuthenticationToken(
            username, "tls-verified-integration-boundary");
    }

    @Test
    void aliceIsResolvedWithReaderRole() {
        StepVerifier.create(manager.authenticate(token("alice")))
            .assertNext(auth -> {
                assertTrue(auth.isAuthenticated());
                assertEquals("alice", auth.getName());
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
            })
            .verifyComplete();
    }

    @Test
    void adminReceivesAdminAndReaderRoles() {
        StepVerifier.create(manager.authenticate(token("admin")))
            .assertNext(auth -> {
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN")));
                assertTrue(auth.getAuthorities().stream()
                    .anyMatch(a -> a.getAuthority().equals("ROLE_READER")));
            })
            .verifyComplete();
    }

    @Test
    void unknownSubjectDoesNotAuthenticate() {
        StepVerifier.create(manager.authenticate(token("stranger")))
            .expectError()
            .verify();
    }

    @Test
    void lockedSubjectDoesNotAuthenticate() {
        StepVerifier.create(manager.authenticate(token("locked")))
            .expectError()
            .verify();
    }
}
```

Có **4 tests**. `UserDetailsService` tra theo username do pre-authentication cung cấp, trả roles hiện tại hoặc từ chối account chưa được phép. Đừng nhầm unit test này với endpoint cho phép client tự POST `username=admin` rồi coi là đã pre-authenticated.

**Lưu ý về import:** Class `org.springframework.security.authentication.AuthenticationManager` được ghi để minh họa khác biệt imperative/reactive nhưng **không cần dùng trong file test** và có thể xóa khi IDE dọn imports. `ReactiveAuthenticationManager` mới là class được sử dụng.

## 12. Test WebFlux X.509 filter mà không khởi tạo TLS server

Ở Spring Framework 6.2, `WebTestClient.bindToApplicationContext(...)` dùng mock server không hoàn tất handshake TLS thật. Để test X.509 filter, cần **giả lập trusted `SslInfo` bên trong riêng test context**, rồi kiểm tra security chain. Test dưới đây triển khai một `WebFilter` chỉ tồn tại trong `src/test`; filter đọc một header test-only `X-Test-Peer` rồi cung cấp `SslInfo` fake cho mock request.

**Cảnh báo bắt buộc:** Đây **không phải pattern production**. Nếu đưa test filter vào `src/main`, attacker có thể tự đặt header để mạo danh user. Trên mạng thật, peer certificates **chỉ được xuất phát từ handshake mTLS đã xác minh bởi transport**, không được tạo từ user-provided HTTP header. Kiểm thử mạng thực ở mục 13 sử dụng OpenSSL và curl.

### 12.1. src/test/java/demo/x509/X509WebFluxTests.java

```java
package demo.x509;

import java.security.cert.CertificateParsingException;
import java.security.cert.X509Certificate;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.SslInfo;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.WebFilter;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(properties = {"server.ssl.enabled=false",
    "server.ssl.client-auth=none"})
@Import(X509WebFluxTests.TestTlsTransportConfiguration.class)
class X509WebFluxTests {

    @TestConfiguration
    static class TestTlsTransportConfiguration {

        @Bean
        @Order(Ordered.HIGHEST_PRECEDENCE)
        WebFilter testOnlyTlsPeerFilter() {
            return (exchange, chain) -> {
                String identity = exchange.getRequest().getHeaders()
                    .getFirst("X-Test-Peer");
                if (identity == null) {
                    return chain.filter(exchange);
                }

                X509Certificate cert = certificateForTest(identity);
                SslInfo simulatedTls = new SslInfo() {
                    @Override
                    public String getSessionId() {
                        return "test-session-only";
                    }

                    @Override
                    public X509Certificate[] getPeerCertificates() {
                        return new X509Certificate[] {cert};
                    }
                };

                ServerHttpRequest request = exchange.getRequest()
                    .mutate().sslInfo(simulatedTls).build();
                return chain.filter(exchange.mutate()
                    .request(request).build());
            };
        }

        private static X509Certificate certificateForTest(
                String identity) {
            try {
                X509Certificate cert = mock(X509Certificate.class);
                if ("missing-san".equals(identity)) {
                    when(cert.getSubjectAlternativeNames())
                        .thenReturn(List.of());
                }
                else {
                    // Header này CHỈ tồn tại ở test fake TLS transport.
                    String uri = "spiffe://example.test/users/" + identity;
                    when(cert.getSubjectAlternativeNames())
                        .thenReturn(List.<List<?>>of(List.of(6, uri)));
                }
                return cert;
            }
            catch (CertificateParsingException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec get(
            String path, String peer) {
        return client.get().uri(path)
            .headers(headers -> {
                if (peer != null) {
                    headers.set("X-Test-Peer", peer);
                }
            })
            .exchange();
    }

    @Test
    void healthIsPublicInMockTransportWithoutCertificate() {
        get("/health", null)
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void protectedEndpointWithoutPeerCertificateIsDenied() {
        get("/api/me", null)
            .expectStatus().is4xxClientError();
    }

    @Test
    void aliceIsMappedToAuthenticatedUser() {
        get("/api/me", "alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user=alice");
    }

    @Test
    void aliceCanReadReports() {
        get("/api/reports", "alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void aliceCannotUseAdminRoute() {
        get("/api/admin", "alice")
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanUseAdminRoute() {
        get("/api/admin", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void adminCanAlsoReadReports() {
        get("/api/reports", "admin")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void unknownDirectoryIdentityIsDenied() {
        get("/api/me", "stranger")
            .expectStatus().is4xxClientError();
    }

    @Test
    void lockedDirectoryIdentityIsDenied() {
        get("/api/me", "locked")
            .expectStatus().is4xxClientError();
    }

    @Test
    void missingSanIdentityIsDenied() {
        get("/api/me", "missing-san")
            .expectStatus().is4xxClientError();
    }

    @Test
    void invalidSanIdentityIsDenied() {
        get("/api/me", "ALICE")
            .expectStatus().is4xxClientError();
    }

    @Test
    void spoofedOrdinaryIdentityHeaderDoesNotWork() {
        client.get().uri("/api/me")
            .header("X-User", "admin")
            .exchange()
            .expectStatus().is4xxClientError();
    }
}
```

Có **12 WebTestClient tests**. Một phần `is4xxClientError()` thay vì ép mọi invalid cert thành HTTP 401: bởi Spring Security entry point/chains có thể trả khác và test này **không có TLS handshake thật**. Với `client-auth=need` trên server thực, request không có cert/CA không tin cậy **có thể bị từ chối trước HTTP** và curl thấy TLS alert thay vì response 401.

**Điều đã được test và chưa được test:**

| Test level | Có thể chứng minh | Không chứng minh |
| --- | --- | --- |
| `SanUriPrincipalExtractorTests` | SAN parse, ambiguity, trust namespace | Certificate chain, private key ownership |
| `ReactivePreAuthManagerTests` | User lookup/roles/account lock | Caller đã có trusted certificate |
| `X509WebFluxTests` | Filter lấy mocked peer certificate, ánh xạ user, authorize routes | TLS handshake, OpenSSL CA, truststore, cert revocation |
| `curl --cert --key --cacert` real server | TLS client cert + SSL trust + app user policy | Tự động tất cả CRL/OCSP/PKI issuance policies |

**Tổng cộng 25 bài test:** 9 extractor + 4 manager + 12 WebFlux. Đây là số phương thức `@Test` trong ví dụ, không phải khẳng định Maven đã thực thi.

## 13. Tạo chứng thư local và thử mTLS bằng curl

Các lệnh này dành cho **Linux/macOS shell hoặc Git Bash**, với OpenSSL và JDK `keytool` đã cài. Dùng một **CA tự tạo, chỉ sống vài ngày**, vì vậy **không** đem key/CA demo lên production. Không commit `certs/*.key`, `certs/*.p12`, `certs/*.csr` hoặc `certs/ca.key`.

### 13.1. Tạo demo Certificate Authority

```bash
mkdir -p certs

openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 7 \
  -subj "/CN=Local Demo CA" \
  -keyout certs/ca.key -out certs/ca.crt \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign"
```

Tạo CA **chỉ dùng cho học tập**. CA private key `ca.key` phải được bảo vệ đặc biệt: ai sở hữu key này có thể ký certificate mới có SAN `/users/admin`, và nếu server trust CA đó thì họ có khả năng tạo một client identity được Spring ánh xạ thành admin. Trong production, dùng CA issuance workflow được kiểm soát, CA keys tại HSM/offline và audit cấp chứng thư.

### 13.2. Tạo server certificate có DNS SAN localhost

```bash
openssl req -newkey rsa:3072 -nodes \
  -keyout certs/server.key -out certs/server.csr \
  -subj "/CN=localhost"

cat > certs/server.ext <<'EOF'
basicConstraints=critical,CA:FALSE
subjectAltName=DNS:localhost,IP:127.0.0.1
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
EOF

openssl x509 -req -in certs/server.csr \
  -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
  -out certs/server.crt -days 7 -sha256 \
  -extfile certs/server.ext
```

`subjectAltName=DNS:localhost,IP:127.0.0.1` giúp curl xác minh hostname khi kết nối `https://localhost:8443`. **Không dùng** `curl -k`/`--insecure`: chỉ định trusted CA với `--cacert certs/ca.crt`.

### 13.3. Tạo client certificates alice, admin, locked, stranger

```bash
for name in alice admin locked stranger; do
  openssl req -newkey rsa:3072 -nodes \
    -keyout "certs/$name.key" -out "certs/$name.csr" \
    -subj "/CN=$name/O=Learning"

  cat > "certs/$name.ext" <<EOF
basicConstraints=critical,CA:FALSE
subjectAltName=URI:spiffe://example.test/users/$name
extendedKeyUsage=clientAuth
keyUsage=digitalSignature
EOF

  openssl x509 -req -in "certs/$name.csr" \
    -CA certs/ca.crt -CAkey certs/ca.key -CAcreateserial \
    -out "certs/$name.crt" -days 7 -sha256 \
    -extfile "certs/$name.ext"
done
```

Bốn client certificates đều được ký bởi CA demo và có SAN URI theo policy. **Chỉ** `alice`, `admin` và `locked` tồn tại trong user service; `stranger` không có trong directory. `locked` có account nhưng bị khóa, do đó TLS có thể thành công song Spring authentication bị từ chối.

Kiểm tra SAN/EKU:

```bash
openssl x509 -in certs/alice.crt -text -noout
openssl verify -CAfile certs/ca.crt certs/alice.crt
```

Kỳ vọng output `openssl verify` kết thúc bằng `certs/alice.crt: OK`. Nội dung đầy đủ của chứng thư có serial/validity/key ngẫu nhiên nên **không có stdout byte-for-byte cố định** cho lệnh `x509 -text`.

### 13.4. Tạo server keystore và truststore

```bash
openssl pkcs12 -export \
  -inkey certs/server.key -in certs/server.crt \
  -certfile certs/ca.crt -name localhost \
  -out certs/server.p12 -passout pass:localpass

keytool -importcert -noprompt -alias local-demo-ca \
  -file certs/ca.crt -keystore certs/trust.p12 \
  -storetype PKCS12 -storepass localpass
```

`server.p12` giữ private key của HTTPS server. `trust.p12` giữ CA certificate được chấp nhận để xác minh client certs. Private key của CA và client **không** nên xuất hiện trong server truststore.

Nếu dùng Windows PowerShell thuần, chuyển script Bash sang PowerShell tương đương hoặc chạy trong Git Bash/WSL; không paste các vòng lặp/heredoc nguyên vẹn vào PowerShell 5.1.

### 13.5. Chạy Spring Boot và thực hiện request

```bash
java -version
mvn -version
mvn clean test
mvn spring-boot:run
```

**Lưu ý:** `mvn clean test` không yêu cầu kết nối CA thật vì tests override SSL và dùng mock `SslInfo`; `mvn spring-boot:run` cần hai file `certs/server.p12`, `certs/trust.p12` trước khi khởi động HTTPS.

Client `alice` truy cập profile:

```bash
curl --cacert certs/ca.crt \
  --cert certs/alice.crt --key certs/alice.key \
  -i https://localhost:8443/api/me
```

Nếu handshake và account lookup đều thành công, body dự kiến:

```text
user=alice
```

Client `alice` xem báo cáo:

```bash
curl --cacert certs/ca.crt \
  --cert certs/alice.crt --key certs/alice.key \
  -i https://localhost:8443/api/reports
```

Body dự kiến `reports OK`; gọi `/api/admin` cùng cert phải bị **403 Forbidden** vì Alice thiếu `ROLE_ADMIN`.

Client `admin`:

```bash
curl --cacert certs/ca.crt \
  --cert certs/admin.crt --key certs/admin.key \
  -i https://localhost:8443/api/admin
```

Body dự kiến `admin OK` (200) vì server trust CA, SAN maps `admin`, user directory nạp `ROLE_ADMIN`.

Client `stranger`:

```bash
curl --cacert certs/ca.crt \
  --cert certs/stranger.crt --key certs/stranger.key \
  -i https://localhost:8443/api/me
```

Certificate `stranger` do cùng CA demo ký và có thể qua TLS, **nhưng** application không tìm thấy user; request phải bị từ chối bởi Spring Security. Status chính xác tùy authentication entry point, không mặc nhiên là lỗi TLS.

Client **không có certificate**:

```bash
curl --cacert certs/ca.crt -v https://localhost:8443/health
```

Vì `server.ssl.client-auth: need`, dự kiến handshake/request bị từ chối ở TLS. **Không** kết luận từ `permitAll("/health")` rằng không cần client cert.

### 13.6. Bảng test matrix end-to-end

| Client certificate | TLS CA trusted? | Account | Quyền | `/api/me` | `/api/admin` |
| --- | --- | --- | --- | --- | --- |
| Alice | Có | Enabled | READER | 200 | 403 |
| Admin | Có | Enabled | READER, ADMIN | 200 | 200 |
| Locked | Có | Locked | READER trong directory | Từ chối authentication | Từ chối authentication |
| Stranger | Có | Không tồn tại | Không | Từ chối authentication | Từ chối authentication |
| Không cert | Không cung cấp | N/A | N/A | TLS handshake reject | TLS handshake reject |
| Cert từ CA không tin cậy | Không | N/A | N/A | TLS handshake reject | TLS handshake reject |
| Cert hết hạn/không phải clientAuth | TLS policy không chấp nhận | N/A | N/A | TLS reject | TLS reject |

Các kết quả trên là **hành vi thiết kế kỳ vọng**, không phải log thực đo từ hệ thống của bạn. Nếu TLS provider, proxy hoặc mTLS policy được thay, hãy kiểm tra bằng wireshark/OpenSSL debug và app logs đã được redact.

## 14. Bảo vệ khi đi qua reverse proxy / API gateway

mTLS thường được chấm dứt ở Ingress/Gateway:

```text
Client -- mTLS --> Gateway -- TLS? --> WebFlux Backend
                   |
                   +-- verify client CA/chain/status
                   +-- map cert -> trusted identity
                   +-- forward identity under strict policy
```

Nếu backend chỉ nhận HTTP request nội bộ sau TLS termination, `ServerHttpRequest.getSslInfo()` thường phản ánh **TLS của kết nối gateway→backend** hoặc không có peer certificate client gốc. Bật `.x509()` ở backend lúc này **không tự truy xuất certificate của end client**. Cần quyết định:

1. **TLS passthrough:** chuyển kết nối TLS tới WebFlux, để Netty trực tiếp xác minh client cert và cung cấp peer chain.
2. **Gateway terminate mTLS:** gateway xác minh certificate và **cung cấp identity đã được xác thực** qua một cơ chế tin cậy riêng: authenticated proxy principal, signed token/header với end-to-end protection, hoặc cơ chế chuẩn hóa khác. Backend xác minh cơ chế proxy đó, không tin một header raw từ Internet.
3. **mTLS kép:** client→gateway và gateway→backend, nhưng certificate được backend thấy trong hop thứ hai **là certificate của gateway**, không tự động là cert gốc của client.

Không cho phép client bên ngoài tự gửi `X-Forwarded-Client-Cert: CN=admin` hoặc `X-SSL-Client-S-DN: CN=admin` rồi coi là authenticated. Gateway phải strip client-supplied headers, lập boundary riêng với network policy và cryptographic integrity. Nếu không chứng minh được chain of custody của identity header, **không cấp quyền từ header**.

### 14.1. Certificate forwarding không phải certificate verification

Một PEM string chuyển qua HTTP header chỉ là text; nó không chứng minh request hiện tại đã hoàn tất TLS handshake bằng private key tương ứng. Chỉ nên dùng certificate-forwarding nếu gateway đã kiểm tra TLS/key proof và có cách chống header spoofing/tampering khi chuyển tới backend. Nếu không, attacker có thể copy certificate công khai của admin và gửi cùng request; **certificate public không phải secret**.

### 14.2. Load balancer và WebClient client certificates

Khi **ứng dụng của bạn** gọi một service khác qua mTLS bằng WebClient, bạn cấu hình **client key material** của Reactor Netty HTTP client và trust server certificate của đích. Đó là một use case **outbound mTLS client**, khác với `ServerHttpSecurity.x509()` xử lý **inbound mTLS authentication**. Một server có thể đồng thời là mTLS server và mTLS client, nhưng cấu hình keystores/identities/trust domains nên tách biệt theo hướng kết nối.

## 15. Chứng thư, người dùng và quyền: rủi ro production

### 15.1. CA issuance là một phần của authorization boundary

Nếu CA có thể ký cho attacker một cert có SAN `spiffe://example.test/users/admin`, TLS sẽ xác minh chữ ký hợp lệ và extractor sẽ ánh xạ thành `admin`. Vì vậy bộ phận phát hành certificate phải thẩm định **ai được nhận mỗi SAN URI**. Nên kết hợp kiểm tra certificate subject/serial/fingerprint hoặc mapping certificate ID cụ thể theo account khi threat model cần sự ràng buộc mạnh hơn.

Việc cho phép một CA tự tạo bởi khách hàng hoặc trust quá rộng có thể trở thành lỗ hổng impersonation nghiêm trọng. Đừng đặt toàn bộ hệ thống doanh nghiệp trên một CA có phát hành không kiểm soát.

### 15.2. Certificate rotation và sự cố key

Chứng thư và private keys có vòng đời:

- Tạo key bằng RNG đủ mạnh; quản trị tại HSM/secret store nếu có.
- Cấp cert với SAN/EKU/validity đúng, theo CA policy.
- Phân phối client private key an toàn, giới hạn quyền đọc file.
- Rotate trước khi hết hạn, có giai đoạn overlap nếu cần.
- Cập nhật truststore và nạp lại theo khả năng vận hành Spring Boot/Netty.
- Thu hồi certificate khi mất máy/lộ key/employee rời tổ chức.
- Gỡ account/roles kịp thời; TLS cert chưa hết hạn không có nghĩa account vẫn được phép.

Nếu root/intermediate CA bị compromise, chỉ khóa account riêng lẻ là không đủ; phải thu hồi CA/keys và thực hiện PKI incident response.

### 15.3. Revocation không tự động bởi mọi JVM TLS configuration

Một chứng thư vẫn nằm trong validity range và được CA tin cậy ký **có thể đã bị thu hồi**. Kiểm tra CRL/OCSP và policy fail-open/fail-closed là **phần PKI/TLS vận hành cần cấu hình và kiểm thử riêng**; không mặc nhiên nói Spring Security `.x509()` tự truy cập OCSP hoặc CRL cho mọi request. Nếu yêu cầu revoke tức thời, cân nhắc certificate-bound account registry/serial denylist ở tầng trusted authentication kèm quy trình incident response. Không cache “valid certificate” vô hạn.

### 15.4. Role cập nhật nhanh hơn certificate lifetime

Một chứng thư có thể tồn tại nhiều ngày nhưng role người dùng thay đổi mỗi giờ. `ReactiveUserDetailsService` có thể nạp quyền hiện tại từ database hoặc directory. Nếu cache authorities, cần TTL/invalidation rõ, tránh giữ `ROLE_ADMIN` sau khi user bị thu hồi quyền. Tránh gắn roles vào CN/SAN URI để CA trở thành nơi quản trị mọi quyền business.

### 15.5. TLS không thay CSRF/CORS

- **CSRF:** Nếu browser tự trình client certificate cho website có state-changing endpoints, cần phân tích CSRF như mọi credential tự động khác. mTLS không thay CSRF token/origin checks.
- **CORS:** Browser kiểm soát cross-origin frontend access; CORS không chứng minh certificate private-key ownership.
- **Authorization:** mTLS chỉ tạo identity; API vẫn cần hasRole/hasAuthority/object-level checks.
- **Transport confidentiality:** vẫn cần TLS 1.2+/TLS 1.3, ciphers phù hợp và kiểm tra server hostname phía client.
- **Session:** nếu web app lập login session sau X.509, phải có lifecycle/logout/session fixation/expiry riêng.

### 15.6. Private key và logging

Không bao giờ log client private key, server private key, PKCS12 passwords hoặc toàn bộ certificate chain chứa dữ liệu nhạy cảm. Công khai certificate khác công khai private key, nhưng serial, SAN, subject/email vẫn có thể tiết lộ identity và dùng để correlate users. Log request ID, issuer fingerprint hoặc hashed certificate identifier khi cần, user ID, outcome, reason category và chính sách ẩn danh tương ứng.

## 16. Những lỗi hay gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách debug |
| --- | --- | --- |
| TLS handshake fail trước HTTP | Client không có cert, không tin CA, EKU sai, expiry, key mismatch | `curl -v`, OpenSSL, server TLS logs |
| `/health` không vào được nếu không cert | `client-auth=need` cho cả port | Dùng client cert, hoặc cổng health tách riêng có policy |
| `x509()` bật nhưng không có Authentication | HTTPS chưa có mTLS, `SslInfo` không có peer certificate | Kiểm tra Netty TLS config, proxy termination |
| Browser có client cert nhưng API deny | SAN không khớp namespace, user không tồn tại/locked | Inspect cert SAN, directory status |
| CN parse khác kỳ vọng | DN formatting/escaping, extractor cũ | Nâng Spring Security, dùng SubjectX500 hoặc SAN |
| Một certificate ánh xạ hai identities | SAN nhiều URI cùng namespace | Reject ambiguous certificates |
| User `admin` được cấp CN/SAN bởi CA ngoài ý muốn | CA issuance/trust policy rộng | Hạn chế CA, name constraints, enrollment approval |
| User `alice` bị 403 tại admin | Role READER, không có ADMIN | Kiểm tra UserDetails authorities |
| Cert có ROLE_ADMIN trong tên file | Filename chỉ là local convention | Quyền phải dựa vào directory, không filenames |
| Dùng X-Client-Cert header | Có thể spoof qua HTTP | Lấy peer chain từ trusted TLS, hoặc gateway signed identity |
| mTLS tại gateway, backend không thấy client cert | TLS bị terminate trước backend | Passthrough hoặc trusted forwarding design |
| Server cert hợp lệ nhưng curl báo hostname mismatch | SAN server thiếu DNS:localhost | Regenerate server SAN, không tắt verify |
| Curl chạy với --insecure thì “được” | Đang bỏ qua server trust | Dùng --cacert đúng CA |
| TLS verified nhưng stranger vẫn bị deny | Không có UserDetails cho subject | Đúng theo policy; cấp user theo enrollment |
| Bản ghi user locked vẫn có cert chưa hết hạn | Account status không phụ thuộc expiry cert | Manager phải deny |
| Certificate hết hạn nhưng app vẫn cho user | Trust validation/reverse proxy cấu hình sai | Audit TLS certificate verification và chain |
| Truststore sai password/path | Netty SSL init error | Kiểm tra P12 path/password/type |
| Một request HTTP không có cert lại 200 trên path nhạy cảm | Có authentication fallback hoặc permitAll sai | Dùng `need`, tắt Basic/form nếu không cần, review chains |
| WebTestClient giả lập cert pass nhưng curl thật fail | Mock không làm TLS handshake | Dùng real mTLS test theo mục 13 |
| Load balancer trả 502/handshake alert | Lỗi mTLS giữa các hops | Tách client→gateway và gateway→backend |
| CORS error che HTTP status | Browser thiếu CORS headers | Debug CORS riêng, không tắt mTLS |
| Account bị revoke nhưng vẫn có session | Cache/session auth quá dài | Thiết kế session invalidation/account-status refresh |
| Có nhiều tenant cùng username `alice` | Identity key thiếu issuer/tenant | Dùng composite identity mapping |
| Chứng thư bị thu hồi vẫn qua TLS | Chưa cấu hình CRL/OCSP/revocation policy | Thêm revocation controls & tests |
| Tất cả routes bị 403 khi bật x509 | Role mapping/entry point hoặc UserDetails lookup lỗi | Debug preauth, authorities và chain order |

### 16.1. Quy trình debug đúng thứ tự

1. **Có TLS handshake thành công không?** Nếu chưa, đừng điều tra Spring authorization trước.
2. Client có trình cert không; chain/truststore/validity/EKU/key ownership có hợp lệ không?
3. Spring Netty có nhận peer chain trong `SslInfo` không (trực tiếp hay qua proxy)?
4. `X509PrincipalExtractor.extractPrincipal` trả identity nào; SAN/CN/namespace có đúng?
5. `ReactiveUserDetailsService.findByUsername` có user không; account disabled/locked/expired?
6. `ReactivePreAuthenticatedAuthenticationManager` đã tạo authenticated principal hay lỗi?
7. `Authentication.getAuthorities()` chứa `ROLE_READER`/`ROLE_ADMIN` đúng policy?
8. Xem HTTP 403 có do role/CSRF/matcher khác không; không đồng nhất mọi 403 với credential sai.
9. Kiểm tra rotation/revocation/cache/account status khi lỗi chỉ xảy ra rải rác.
10. Tắt mọi việc log private keys/secret, giữ trace ID và nguyên nhân mức cần thiết.

## 17. Bài tập và đáp án

**Câu 1.** Client không có certificate, server `client-auth=need`, `/health` permitAll. Có chắc nhận HTTP 200 không?  
**Đáp án:** Không. TLS yêu cầu cert trước khi Spring xét permitAll.

**Câu 2.** mTLS thành công có nghĩa account có ROLE_ADMIN?  
**Đáp án:** Không. TLS xác minh certificate chain/key; account lookup/role là bước khác.

**Câu 3.** `X509PrincipalExtractor` dùng làm gì?  
**Đáp án:** Ánh xạ một X509Certificate thành principal ID để authentication manager tìm user.

**Câu 4.** WebFlux nên dùng `HttpSecurity` hay `ServerHttpSecurity`?  
**Đáp án:** `ServerHttpSecurity` và `SecurityWebFilterChain`.

**Câu 5.** Tại sao không dùng `X-Client-Cert: CN=admin` do HTTP caller gửi?  
**Đáp án:** Header không chứng minh private key ownership và có thể bị spoof.

**Câu 6.** X.509 principal được trích từ CN nhưng user không tồn tại trong directory?  
**Đáp án:** Preauth manager phải từ chối, không cấp quyền chỉ vì CN đọc được.

**Câu 7.** Chứng thư từ CA khác không nằm trong truststore sẽ thất bại ở đâu?  
**Đáp án:** Tại TLS handshake/validation trước WebFlux controller.

**Câu 8.** Cert của `locked` hợp lệ, account locked. Kết quả?  
**Đáp án:** TLS có thể thành công, Spring pre-authentication từ chối account.

**Câu 9.** `hasRole("READER")` tương ứng authority nào?  
**Đáp án:** Theo convention mặc định là `ROLE_READER`.

**Câu 10.** Vì sao URI SAN tốt hơn việc regex parse CN thủ công?  
**Đáp án:** Có namespace/format xác định, kiểm tra trust domain và loại trừ ambiguous mapping; nhưng vẫn cần CA issuance policy.

**Câu 11.** Một cert có hai SAN URI `/users/alice` và `/users/admin`?  
**Đáp án:** Theo policy project, từ chối vì không có principal duy nhất.

**Câu 12.** `SubjectDnX509PrincipalExtractor` nên dùng tiếp ở bản Spring Security 6.5.10?  
**Đáp án:** Không. Cần vá lên 6.5.11+ và tránh class đã deprecated theo advisory CVE-2026-47838.

**Câu 13.** Trong production, khi key của CA bị lộ, xóa user admin đã đủ không?  
**Đáp án:** Không. Phải xử lý CA compromise, rotate/revoke trust anchors/issued certificates và audit issuance.

**Câu 14.** Browser có client cert, còn cần CSRF không?  
**Đáp án:** Có thể cần; browser có thể tự trình client certificate cho state-changing requests, nên CSRF threat model vẫn tồn tại.

**Câu 15.** Vì sao WebTestClient fake `SslInfo` không thay real mTLS test?  
**Đáp án:** Fake bỏ qua TLS handshake, CA trust, key possession, hostname checks và revocation.

**Câu 16.** Client có cert mTLS còn hạn, nhưng role đã bị rút. App phải làm gì?  
**Đáp án:** Directory/current authorization policy phải từ chối hoặc hạn chế quyền; không giữ ROLE_ADMIN lâu vô hạn.

**Câu 17.** API gateway terminate mTLS, backend chỉ thấy cert gateway. Backend có thấy cert client gốc nhờ `.x509()` không?  
**Đáp án:** Không tự động; cần passthrough hoặc cơ chế truyền identity được bảo vệ riêng.

**Câu 18.** Có nên gửi private key qua HTTP header để backend tự verify không?  
**Đáp án:** Tuyệt đối không. mTLS chỉ gửi certificate public và cryptographic proof, private key được giữ tại client.

**Câu 19.** Chỉ một internal CA trong truststore đã đủ chắc chắn không bị user impersonation?  
**Đáp án:** Chưa. Cần quản trị quyền CA được cấp identity/SAN nào, revocation và mapping user/roles.

**Câu 20.** Trong WebFlux, đọc Authentication từ đâu?  
**Đáp án:** Reactive Security Context trên **Reactor Context**, ví dụ `ReactiveSecurityContextHolder.getContext()`.

## 18. Checklist đưa vào môi trường thật

- [ ] Spring Boot/Framework/Security versions đã được vá (nhánh 6.5 dùng 6.5.11+ cho CVE-2026-47838).
- [ ] TLS 1.2+/1.3 với server certificate, hostname SAN và trusted client CA rõ ràng.
- [ ] `server.ssl.client-auth: need` hoặc chính sách `want` được lựa chọn có chủ đích.
- [ ] Client key material không bị rò; quyền đọc file/HSM/rotation/secret management phù hợp.
- [ ] Truststore chứa đúng trust anchors, không mở rộng vô tội vạ.
- [ ] Client EKU/clientAuth, validity, chain và policy revocation được kiểm thử.
- [ ] Không tin PEM certificate do HTTP caller gửi hoặc header tự khai.
- [ ] Nếu TLS terminates ở gateway, identity forwarding được bảo vệ và chống spoofing.
- [ ] Chọn principal extractor chuẩn, không parse Subject DN bằng regex; dùng SAN namespace khi cần.
- [ ] Mapping có unique identifier và tenant/issuer-aware boundaries, không ambiguous.
- [ ] CA issuance policy ngăn bất kỳ client nào xin SAN của admin/người khác.
- [ ] Preauthenticated account lookup kiểm tra tồn tại, enabled, locked, expired.
- [ ] Authorities/roles do trusted directory quyết định, không từ raw cert filename hay request header.
- [ ] Chỉ mở endpoint theo role/authority và object/tenant ownership phù hợp.
- [ ] CSRF/CORS/session/other auth mechanisms được threat-model riêng.
- [ ] Negative tests: no cert, untrusted CA, expired cert, wrong SAN, unknown/locked user, missing role.
- [ ] Có thực nghiệm TLS thật, không chỉ WebTestClient với fake `SslInfo`.
- [ ] Certificate renew/revoke/CRL-OCSP/truststore rotation và outage policies có runbook.
- [ ] Key/secret/certificate PII không lộ trong logs, traces, screenshots và repo.
- [ ] Multi-instance, gateway, healthcheck và zero-downtime rotation được thử trước production.

## 19. Kết luận và tài liệu chính thức

**Công thức cần nhớ:**

```text
mTLS trust (certificate chain + private-key possession)
           ≠ identity mapping (CN/SAN -> username)
           ≠ authorization (user account + roles + resource policy)
```

`ServerHttpSecurity.x509(...)` trên Spring WebFlux là cầu nối giữa **chứng thư client đã được TLS xác minh** và **Spring Security Authentication**. `X509PrincipalExtractor` chọn identity có chính sách rõ, `ReactivePreAuthenticatedAuthenticationManager` kiểm tra tài khoản và nạp quyền, còn `AuthorizationWebFilter` thực thi permission. Không có phần nào thay thế phần còn lại.

**Nguồn chính thức / tiêu chuẩn:**

- Spring Security 6.5 – Reactive X.509 Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/x509.html
- Spring Security 6.5 – ServerHttpSecurity.x509 API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 – X509Spec: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.X509Spec.html
- Spring Security 6.5 – ReactivePreAuthenticatedAuthenticationManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ReactivePreAuthenticatedAuthenticationManager.html
- Spring Security 6.5 – SubjectX500PrincipalExtractor: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/preauth/x509/SubjectX500PrincipalExtractor.html
- Spring Security CVE-2026-47838 (bản sửa 6.5.11, tránh SubjectDn parser): https://spring.io/security/cve-2026-47838/
- Spring Boot – SSL, key/trust stores và client auth: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot – Common application properties, server.ssl.client-auth: https://docs.spring.io/spring-boot/appendix/application-properties/
- Spring Framework 6.2 – SslInfo: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/server/reactive/SslInfo.html
- Spring Security – Reactive WebTestClient testing authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Boot 3.5.16 release/end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
- IETF RFC 5280 – X.509 PKI Certificate and CRL Profile: https://www.rfc-editor.org/rfc/rfc5280
- IETF RFC 8446 – TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- OWASP – Transport Layer Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
