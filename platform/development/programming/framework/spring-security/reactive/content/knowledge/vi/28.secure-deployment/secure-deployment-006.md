# Luân chuyển khóa, secret và chứng thư mà không mở rộng quyền tạm thời

## 1. Mục tiêu và phạm vi

Bài học thuộc **Spring Security reactive / triển khai an toàn**. Sau khi học, bạn cần thực hiện được một đợt thay thế khóa ký JWT, secret dùng để ứng dụng xác thực với dịch vụ ngoài, và chứng thư TLS/mTLS mà vẫn giữ nguyên chính sách **ai được làm gì**. Bạn cũng cần biết khi nào phải chấp nhận giai đoạn hai phiên bản cùng tồn tại, khi nào phải thu hồi ngay, cách phối hợp với Reactor/WebFlux, và cách kiểm chứng trước khi tắt phiên bản cũ.

**Nguyên tắc cốt lõi:** *Luân chuyển thông tin xác thực là thay vật liệu chứng minh danh tính; không phải cấp thêm quyền.* Trong giai đoạn chuyển đổi, có thể tạm thời chấp nhận **hai khóa công khai xác minh chữ ký**, hoặc **hai secret ứng dụng có cùng phạm vi**, hoặc **hai chứng thư cùng đại diện đúng một danh tính**. Điều đó không cho phép thêm principal mới, nới `scope`/`role`/`audience`, bỏ xác thực hoặc bỏ kiểm tra hostname/chữ ký.

Các thành phần cần phân biệt:

| Vật liệu | Vai trò | Phần thường cần thay | Quyền phải giữ nguyên |
| --- | --- | --- | --- |
| Khóa ký JWT (bất đối xứng) | Authorization server dùng **private key** để ký; WebFlux resource server dùng **public JWK** để xác minh | Cặp khóa mới, `kid` mới, JWKS của issuer | `iss`, `aud`, thời hạn, thuật toán được chấp nhận và ánh xạ scope/authority |
| OAuth2 client secret, API key, mật khẩu DB | Workload xác thực với nhà cung cấp dịch vụ hoặc DB | Phiên bản secret ở secret manager và phía đối tác | Client identity, service account, quyền DB, danh sách scope được cấp |
| TLS server certificate/private key | Chứng minh danh tính endpoint HTTPS | Leaf certificate, khóa riêng, chain tương ứng | DNS/SAN hợp lệ, trust anchor được phép và chính sách TLS |
| mTLS client certificate | Chứng minh workload gọi API | Client certificate/private key và có thể là issuer CA | Workload identity, SAN/SPIFFE ID (nếu dùng), access policy tại server |
| CA/trust bundle | Quyết định danh tính nào được tin | Trusted CA/intermediate hoặc pin cụ thể | Tập danh tính được phép phải có ràng buộc; không biến CA trust thành quyền API |

Ví dụ: resource server kiểm tra bearer token `orders.read` do một issuer hợp lệ ký. Khi đổi khóa ký `k-old` sang `k-new`, trong một khoảng thời gian nó có thể xác minh cả hai chữ ký, **nhưng vẫn chỉ chấp nhận** issuer, audience, signature algorithm, expiry và quyền `orders.read` như trước. Token có chữ ký hợp lệ không tự nhiên được phép thao tác `orders.write`.

## 2. Hai chiều của rotation: tương thích và đặc quyền

Một rotation an toàn cần giải quyết **hai vấn đề khác nhau**:

1. **Tính sẵn sàng:** client/server chưa chuyển hết sang khóa/secret/certificate mới vẫn có thể xử lý yêu cầu hợp lệ trong cửa sổ đã tính toán.
2. **Tính bất biến của quyền:** không có giai đoạn “nới tạm” quyền để tránh lỗi chuyển đổi. Một vật liệu mới không được dùng để biến tài khoản `reader` thành `admin`, cho phép audience mới hay bỏ kiểm tra chứng thư.

Tách ba khái niệm:

- *Identity* — principal/service account hoặc danh tính chứng thư được xác thực.
- *Credential/material* — thứ chứng minh danh tính: private key, bearer token, secret, certificate.
- *Authorization* — quyền của danh tính đó với tài nguyên cụ thể.

Một identity có thể có nhiều credential đang hợp lệ trong giai đoạn thay đổi; **authorization phải được đánh giá riêng**, cho từng request/connection/token với cùng chính sách hiện hành. Chính sách phát token của authorization server và chính sách quyết định access ở resource server đều cần được giữ ổn định.

Ví dụ phản mẫu cần loại bỏ:

```java
// SAI: thay đổi quyền truy cập chỉ để rotation "đỡ lỗi".
return http.authorizeExchange(ex -> ex
        .anyExchange().permitAll())
    .build();
```

Tương tự, không tạm dùng `hasAnyRole("READER", "ADMIN")`, không tắt xác minh signature/JWT issuer, không cho mọi CA được tin, không chuyển TLS client sang chế độ `trustAll` và không cấp quyền `get/list secrets` toàn namespace cho workload chỉ để đọc secret mới.

## 3. Mô hình rotation chuẩn: chuẩn bị → đồng tồn tại → chuyển → thu hồi

Mô hình này dùng cho kế hoạch bình thường khi vật liệu **chưa bị lộ**. Khi có bằng chứng compromise, chuyển sang quy trình khẩn cấp ở phần 10.

| Giai đoạn | Người vận hành thực hiện | Điều phải xác nhận |
| --- | --- | --- |
| 0. Kiểm kê | Liệt kê issuer, secret/cert ID, owner, môi trường, workload tiêu thụ, cách refresh, TTL, cache, kết nối tồn tại lâu, deadline hết hạn | Không bỏ sót consumer hoặc client đặt cấu hình cứng |
| 1. Chuẩn bị | Tạo vật liệu mới, lưu trong secret manager/KMS/CA, đặt quyền đọc tối thiểu, kiểm tra format/SAN/chuỗi chứng thư | Credential mới đại diện **cùng identity và quyền**, không tạo wildcard trust |
| 2. Phân phối trước | Công bố public verification key/JWKS, thêm đúng credential mới ở hệ thống xác thực hoặc trust chain phù hợp | Consumer đã thấy phiên bản mới trước khi sử dụng; thử canary |
| 3. Chuyển active | Cho signer hoặc client mới bắt đầu dùng phiên bản mới; rollout theo canary/rolling | AuthN/AuthZ đúng; 401/403, TLS handshake và độ trễ không tăng bất thường |
| 4. Giai đoạn chồng lấp | Hỗ trợ phiên bản cũ còn hợp lệ đúng thời gian đã duyệt | Không phát mới bằng vật liệu cũ; không mở thêm scope, issuer, CA |
| 5. Thu hồi/dọn | Ngừng chấp nhận phiên bản cũ; xóa bản cũ khỏi secret store/JWKS/trust nếu đã đủ điều kiện | Mọi client dùng mới; token cũ hết hạn; cache đã hết; không rò rỉ backup |
| 6. Xác nhận | Thử cố tình dùng vật liệu cũ và vật liệu sai quyền | Từ chối đúng; đánh dấu version cũ revoked và lưu bằng chứng vận hành |

Chuyển **reader trước writer** là quy tắc thường gặp của khóa JWT: công bố public key mới để những nơi xác minh biết trước, rồi mới dùng private key mới để phát token. Với client secret, chuẩn bị phía nhà cung cấp cho phép secret mới trước rồi triển khai phía client; với TLS CA, các bên cần thống nhất trust chain trước khi đổi leaf/cert client.

**Khoảng overlap không có công thức cố định.** Nó phụ thuộc token lifetime, `exp` cuối cùng của token do khóa cũ ký, clock skew, cache JWKS, thời gian refresh của consumer, deployment/rollback và thời gian sống connection. Chỉ giữ overlap đến khi đã đáp ứng các điều kiện thực tế. Overlap quá dài kéo dài tác dụng của credential cũ; overlap quá ngắn gây lỗi cho người dùng hợp lệ.

## 4. Rotation khóa ký JWT trong Spring Security WebFlux

### 4.1. Kiến trúc hợp lệ

```text
Authorization Server / Identity Provider
  Signing keys: old private key → new private key
  Public JWK Set: {old public JWK, new public JWK} trong giai đoạn overlap
                          |
                          | HTTPS + cache/refresh
                          v
Spring Security Reactive Resource Server
  Bearer token → ReactiveJwtDecoder → kiểm tra chữ ký
                                   → iss / aud / exp / nbf
                                   → scope/authority
                                   → authorizeExchange()
                          |
                          v
                     API protected
```

Header `kid` giúp bộ xác minh chọn public JWK tương ứng; nó **chỉ là gợi ý do token cung cấp**, không phải bằng chứng tin cậy. Phải xác minh chữ ký, thuật toán cho phép và tất cả claims bắt buộc. Không sử dụng `kid` để đọc đường dẫn file tùy ý hoặc gọi URL do token chỉ định; không chấp nhận `alg=none`. Trong trường hợp nhiều tenant, phải ràng buộc issuer/JWKS theo cấu hình hoặc danh sách allowlist, không cho bearer token tự định nghĩa issuer đáng tin.

Trong dự án Spring Boot 3.3 với WebFlux, thêm những starter tương ứng và để Spring Boot quản lý dependency versions:

```groovy
// build.gradle của ứng dụng Spring Boot đang có dependency management
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Cấu hình issuer, JWKS và audience cụ thể cho **cùng một hệ thống**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://id.example.org/tenant-a"
          jwk-set-uri: "https://id.example.org/tenant-a/jwks"
          audiences:
            - "orders-api"
```

`issuer-uri` để xác minh claim `iss`. Cung cấp thêm `jwk-set-uri` khi muốn biết trước endpoint JWKS thay vì phụ thuộc khám phá endpoint lúc khởi tạo. Spring Security reactive hỗ trợ khóa public mới trong JWKS và tự cập nhật khóa dùng để xác minh trong các điều kiện refresh/cache của decoder. **Không tự thay decoder bằng implementation cố định một public key** nếu cần rotation liên tục. Nếu khai báo `ReactiveJwtDecoder` tùy chỉnh, phải tự bảo toàn các validator bắt buộc (issuer, audience, thời gian) và chiến lược refresh/caching.

Policy WebFlux minh họa:

```java
// ApiSecurityConfig.java trong package được Spring scan
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfig {
    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Spring Security mặc định map các scope JWT thông dụng sang authority có tiền tố `SCOPE_`. Tại **mọi thời điểm rotation**, đường dẫn đọc đơn hàng vẫn đòi `SCOPE_orders.read`; các thao tác không khai báo vẫn bị từ chối. Đây là một component cấu hình của ứng dụng Spring WebFlux, không phải chương trình `main` chạy riêng. Cần tự cấu hình endpoint readiness/management theo hạ tầng của bạn; không đổi `anyExchange().denyAll()` thành `permitAll()` chỉ vì cần kiểm tra sức khỏe dịch vụ.

### 4.2. Quy trình ký JWT với `kid` và JWKS

Giả sử IdP ký JWT có lifetime tối đa 15 phút, `kid=k1`. Một lịch mẫu:

| Thời điểm | JWKS công bố | Khóa phát token mới | Kỳ vọng |
| --- | --- | --- | --- |
| T0 | `k1` | `k1` | Các token hiện tại hợp lệ |
| T1 | `k1`, `k2` | `k1` | Resource server nhận biết `k2` qua refresh; xác minh canary |
| T2 | `k1`, `k2` | **`k2`** | Token mới dùng `k2`; token `k1` chưa hết `exp` vẫn được chấp nhận |
| T3 | `k1`, `k2` | `k2` | Không còn token `k1` hợp lệ theo TTL và skew; xác minh consumer/cache |
| T4 | **`k2`** | `k2` | Gỡ `k1`; token ký bằng `k1` bị từ chối sau khi các bộ xác minh làm mới JWKS |

T1 phải đủ sớm để JWKS cache phân tán có thể học khóa mới. T3 phải đủ muộn so với **token k1 được phát cuối cùng**, không chỉ so với lúc k2 được tạo. T4 có thể chưa có hiệu lực ngay ở mọi consumer nếu cache cũ chưa được làm mới; vì vậy phải theo dõi TTL cache, timeout khi IdP mất kết nối và hành vi refresh thực tế.

Nếu chính sách yêu cầu **thu hồi lập tức** token bị đánh cắp, JWT tự chứa xác minh offline không cung cấp revocation tức thì chỉ bằng cách xóa một JWK ở IdP. Các consumer đã cache khóa vẫn có thể xác minh cho đến khi cache hết hoặc bị invalidation. Cần cơ chế revocation/denylist, token lifetime ngắn, opaque token/introspection hoặc thiết kế kiểm soát phiên phù hợp với yêu cầu, và phải thử thực nghiệm.

### 4.3. Không làm sai lệch quyền khi đổi khóa

Lỗi nguy hiểm không nằm ở việc có hai public JWK mà ở việc policy bị thay:

- Không thêm issuer khác như fallback nếu JWKS của issuer hiện tại gặp lỗi.
- Không bỏ kiểm tra `aud` hoặc đổi sang audience wildcard.
- Không mở danh sách thuật toán ký “mọi thuật toán” để thử token khác loại.
- Không dùng quyền từ claim chưa xác minh, không tin `role=admin` chỉ vì payload JWT đọc được.
- Không cho token `k1` hoặc `k2` có policy riêng theo version. Quyền lấy từ identity/claims đã xác minh và hệ thống authorization nhất quán.
- Khi nguồn JWKS không truy cập được, lựa chọn cache cũ có thời hạn hoặc từ chối xác thực theo chính sách đã duyệt; tuyệt đối không chấp nhận chữ ký chưa kiểm tra.

Đừng thay **private signing key** trên resource server nếu server chỉ đóng vai trò verify. Private key thuộc signer/authorization server hoặc HSM/KMS; JWKS công bố public key tương ứng, **không bao giờ công bố private key**.

## 5. Rotation secret cho OAuth2 client, API key và DB

Khác với JWT public verification key, client secret/API key hoặc mật khẩu DB thường là **bí mật dùng trực tiếp để xác thực**. Cơ chế rollover là việc hai secret khác nhau có thể đại diện đúng **một identity với cùng quyền** trong cửa sổ ngắn, khi nhà cung cấp hỗ trợ.

### 5.1. OAuth2 client credentials

Ví dụ ứng dụng WebFlux `orders-api` gọi `inventory-api` bằng OAuth2 `client_credentials`:

- Client registration dùng `client-id=orders-reader` với scope tối đa `inventory.read`.
- Secret v1/v2 chỉ thay cách chứng minh client là `orders-reader`; **không cấp thêm `inventory.write`**, grant type, audience hoặc role.
- Ở IdP, tạo secret v2 cho client hiện hữu nếu IdP cho phép nhiều secret hoạt động đồng thời; triển khai v2 đến ứng dụng; kiểm tra lấy token mới; thu hồi v1.
- Nếu IdP chỉ cho một secret, cần kỹ thuật rotation có kiểm soát bởi nhà cung cấp (ví dụ client identity song song với policy **tương đương** và chuyển dịch được giám sát), chấp nhận downtime có kế hoạch hoặc dùng phương thức xác thực dựa trên khóa/cert được hỗ trợ. Không mặc định mọi nhà cung cấp đều cho phép dual-secret.

Spring Security reactive có `ReactiveOAuth2AuthorizedClientManager` và integration với `WebClient` để xin/refresh access token theo lifecycle. **Thay client secret không tự xóa access token đã phát trước đó**, cũng không chắc bean `ClientRegistration` hay authorization manager tạo từ cấu hình lúc startup sẽ tự đọc secret mới. Cần xác định cách tải cấu hình, cache authorized client, refresh token, restart/recreate client registration hoặc rolling restart đúng thiết kế. Kiểm tra rằng *lần xin token mới sau cutover* đã sử dụng secret v2, không chỉ dựa vào một request thành công nhờ access token cũ vẫn còn hạn.

Với hệ thống cần mTLS hoặc private_key_jwt thay client secret tĩnh, hãy dùng cơ chế do IdP hỗ trợ và pin policy được chấp thuận. Không tự chế cơ chế JWT client authentication thiếu claim `aud`, `iss`, `sub`, `jti` và điều kiện replay protection của nhà cung cấp.

### 5.2. Secret manager và ranh giới reactive

Ứng dụng nên nhận secret ở runtime từ secret manager/mounted volume hoặc cơ chế workload identity có quyền đọc đúng secret path. Không ghi secret trong Git, Docker image, log, command-line argument, exception, trace attribute hay response. Không đặt chính giá trị secret vào Reactor `Context` chỉ để đi xuyên các operator; với dữ liệu cần dùng ngắn hạn, dùng thành phần chuyên trách và giới hạn thời gian sống/khả năng quan sát.

Nếu SDK secret manager chỉ có API **blocking**, không gọi trực tiếp nó trên Netty event-loop:

```java
// Mẫu tích hợp, không phải chương trình độc lập.
// secretClient.readCurrent() là API blocking giả định của SDK nhà cung cấp.
Mono<SecretVersion> fetched = Mono.fromCallable(
            () -> secretClient.readCurrent("orders/inventory-client"))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(3));
```

Cần import `reactor.core.publisher.Mono`, `reactor.core.scheduler.Schedulers` và `java.time.Duration`, cùng kiểu `SecretVersion`/`secretClient` của nhà cung cấp. **Không log `SecretVersion` nếu nó chứa giá trị bí mật.** Thiết lập retry có giới hạn/backoff và cơ chế báo động; không chuyển lỗi đọc secret thành `permitAll`, bypass authentication hay “dùng secret bất kỳ gần đúng”. Nếu có SDK không blocking thực sự, ưu tiên nó hơn việc dùng `boundedElastic`.

Tại thời điểm chuyển đổi secret trong bộ nhớ, một snapshot bất biến/atomic reference giúp request mới dùng cùng một phiên bản. Tuy nhiên cần kiểm tra tác động tới connection pool, các client beans và phiên làm việc tồn tại lâu. Thay `AtomicReference` trong JVM không tự thông báo cho IdP, không quay vòng connection pool và không đồng bộ nhiều pod.

### 5.3. Mật khẩu database và pool

Thay mật khẩu của **cùng DB user** chỉ tương thích nếu server hỗ trợ một khoảng thời gian dual credentials, phiên kết nối cũ còn dùng được và pool tạo kết nối mới bằng mật khẩu mới. Với hệ thống không hỗ trợ dual-password, có thể chuẩn bị account v2 **chỉ với cùng quyền tối thiểu** đã kiểm chứng, cập nhật ứng dụng rồi tắt v1 — nhưng account song song phải nằm trong chính sách vận hành chấp thuận và không trở thành đường leo thang quyền.

Đối với R2DBC/reactive DB hoặc pool client bất đồng bộ, kiểm tra: pool có thể tái tạo connection factory khi secret đổi không; connection đã mở còn tồn tại bao lâu; khi rollback có bao nhiêu pod giữ secret v1. Nếu thư viện chỉ đọc password ở startup, dùng rolling restart/rolling redeploy thay vì giả định mọi kết nối đang mở sẽ đổi credential ngay.

## 6. Rotation chứng thư HTTPS/mTLS

### 6.1. Thành phần bắt buộc của TLS

Server certificate phải có SAN khớp hostname mà client gọi, chưa hết hạn, có chain hợp lệ đến trust anchor được phép và dùng thuật toán/extended key usage phù hợp. Khóa riêng mới phải thực sự khớp public key trong chứng thư mới. Khi thay một leaf certificate do **cùng CA** ký, client thường không cần nới trust store. Nếu thay CA, có thể cần thời gian chuyển trust anchor; chỉ tin những CA đúng mục đích, không nhập cả kho CA không liên quan.

**mTLS gồm hai bước riêng:** TLS xác thực certificate của cả hai phía, sau đó hệ thống cần mapping danh tính certificate (ví dụ SAN hoặc SPIFFE workload identity) thành principal được phép gọi API. Chỉ vì chứng thư được một CA tin cậy cấp **không có nghĩa** chủ chứng thư được quyền truy cập mọi endpoint. Không chuyển `client-auth: need` thành `want`/`none` để xử lý lỗi rotation; không bỏ hostname verification khi chứng thư chưa đúng SAN.

### 6.2. Spring Boot WebFlux / Netty SSL bundles

Spring Boot 3.3 có `SslBundle` từ PEM/JKS/PKCS12 và hỗ trợ tải lại PEM bundle được cấu hình bằng file đối với embedded Netty server tương thích. Ví dụ server TLS với chứng thư và khóa được cung cấp từ các file do hạ tầng quản lý:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/app/tls/tls.crt"
            private-key: "file:/etc/app/tls/tls.key"

server:
  ssl:
    bundle: "webserver"
```

Đây là ví dụ **server TLS một chiều**. Để yêu cầu mTLS inbound, phải cấu hình trust material và bắt buộc chứng thư client, ví dụ **cùng một bundle** có thêm:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/app/tls/tls.crt"
            private-key: "file:/etc/app/tls/tls.key"
          truststore:
            certificate: "file:/etc/app/tls/trusted-client-ca.pem"

server:
  ssl:
    bundle: "webserver"
    client-auth: "need"
```

Đây là cấu hình mẫu trong ứng dụng có sẵn Netty SSL server và một chính sách ánh xạ danh tính chứng thư. **Không** copy cả hai khối `spring`/`server` riêng lẻ vào cùng file mà không hợp nhất YAML; chọn một mô hình phù hợp. Trước rollout, xác minh properties trên đúng phiên bản Spring Boot/Netty của dự án và quan sát certificate thực tế đang được cung cấp qua handshake.

`reload-on-update` là cơ chế theo dõi file và reload khi thay đổi; điều đó **không có nghĩa** mọi thư viện, outbound `WebClient`, cache SSL context hay connection đang mở sẽ tự động dùng vật liệu mới. Connection TLS đã thiết lập thường không handshake lại ngay; cần giới hạn vòng đời connection hoặc tái tạo client/pool khi cần. Nếu môi trường không hỗ trợ reload đầy đủ, rolling restart theo readiness/liveness là đường đi hợp lệ, có canary và rollback.

### 6.3. Kịch bản đổi CA và mTLS client certificate

Khi muốn đổi root/intermediate CA cho client mTLS:

1. Xác thực danh sách workload identity được chấp nhận, SAN/EKU và ACL ứng dụng; làm rõ CA mới có thể cấp cho những danh tính nào.
2. Chuẩn bị trust chỉ cho CA được duyệt; gắn authorization vào **danh tính client cụ thể** thay vì “bất kỳ chứng thư dưới CA này”.
3. Phát hành client certificate mới đúng identity, phân phối khóa riêng an toàn, kiểm thử một client canary.
4. Chuyển các client còn lại sang certificate mới; theo dõi handshake và application `403` riêng biệt.
5. Gỡ CA/certificate cũ khỏi trust theo lịch; nếu CA cũ bị lộ, dùng quy trình khẩn cấp với thu hồi/rotate identity và chấp nhận gián đoạn có kiểm soát.

**Đổi public trust anchor** khác với đổi leaf certificate. Đừng coi “tin tạm cả CA A và CA B” là vô hại: nó có thể làm rộng số chứng thư được xác thực. Nếu overlap CA là cần thiết, giới hạn theo SAN/name constraints, workload mapping, policy và thời gian cụ thể. Không mở rộng danh sách principal/role chỉ vì trust store có thêm CA.

## 7. Hạ tầng phân phối: Kubernetes và secret manager

Trong Kubernetes, secret có thể được gắn vào Pod dưới dạng file hoặc môi trường. Với nhu cầu đọc vật liệu thay đổi khi ứng dụng đang chạy:

- Secret được mount thành volume thông thường có thể được kubelet cập nhật **theo thời gian**, không đảm bảo tức thì; ứng dụng phải có cơ chế đọc lại/reload/rollout tương ứng.
- Secret dùng qua biến môi trường chỉ được nạp vào process khi container khởi động; cập nhật Kubernetes Secret **không làm biến môi trường của process cũ đổi theo**.
- Secret mount qua `subPath` không nhận các bản cập nhật secret volume theo cơ chế thông thường.
- Tạo phiên bản mới cho secret của workload cụ thể, giới hạn RBAC/KMS, triển khai canary, kiểm tra checksum/metadata **không chứa giá trị secret**, rồi mới thu hồi bản cũ.

Ví dụ deployment trích đoạn chỉ mô tả **volume mount**, không phải manifest hoàn chỉnh:

```yaml
spec:
  template:
    spec:
      automountServiceAccountToken: false
      containers:
        - name: orders-api
          image: registry.example.org/orders-api:1.0
          volumeMounts:
            - name: tls-material
              mountPath: /etc/app/tls
              readOnly: true
      volumes:
        - name: tls-material
          secret:
            secretName: orders-server-tls
```

Khi ứng dụng không cần gọi Kubernetes API, tắt mount service-account token mặc định giúp giảm bề mặt truy cập. Pod **không cần có RBAC quyền `list secrets` toàn namespace** để dùng volume do kubelet mount. Nếu dùng CSI driver/external secret operator, kiểm tra thời điểm đồng bộ và khả năng rollback của chính driver/operator; không mặc định cơ chế cập nhật giống Secret volume mặc định.

Khi phải thay một cặp file certificate/private key, không để process đọc chứng thư mới với khóa cũ trong một trạng thái nửa cập nhật. Dùng cơ chế publish version/atomic directory hoặc symlink mà nền tảng hỗ trợ và kiểm tra bước reload tương thích; thiết kế rollback cả **cặp** certificate-key. Cấp quyền file đủ hẹp, nhưng tránh giải pháp chạy app bằng root chỉ để đọc secret.

## 8. Authorization không đổi qua cutover

“Có hai credential hợp lệ” là trạng thái rất khác với “cấp thêm đặc quyền”:

| Tình huống | Có thể hợp lệ trong overlap? | Vì sao |
| --- | --- | --- |
| Public JWK `k1` và `k2` của **cùng issuer được phép** cùng dùng để xác minh | Có, theo thời gian xác định | Hai cách xác minh chữ ký, cùng validator và policy |
| Secret `v1` và `v2` cho **cùng OAuth client**, cùng grant/scope | Có, nếu IdP hỗ trợ | Phục vụ cutover kỹ thuật |
| Chứng thư leaf mới cho đúng SAN, cùng mức tin cậy | Có | Danh tính endpoint không đổi |
| Chấp nhận token từ issuer khác vì JWKS cũ lỗi | **Không** | Thay đổi nguồn định danh đáng tin |
| Cho `anyExchange().permitAll()` hoặc thêm `SCOPE_admin` | **Không** | Mở rộng authorization |
| Chuyển TLS trust manager sang trust-all | **Không** | Bỏ kiểm chứng danh tính |
| Giao quyền secret-manager wildcard cho service account | **Không** | Mở rộng quyền đọc bí mật |
| Giữ CA cũ và mới nhưng không ràng buộc danh tính certificate | Cần thiết kế lại | CA overlap có thể mở rộng tập workload được xác thực |

Khi resource server nhận hai loại JWT trong cùng cửa sổ, **cùng `SecurityWebFilterChain` phải quyết định quyền cho cả hai**. Dữ liệu JWKS chỉ cung cấp public verification material. Nếu signer trả về claim/scope khác, đó là thay đổi policy cần review riêng, không nên trộn vào đợt rotation.

Để tránh đặc quyền “tạm”, có thể kiểm soát bất biến bằng cách lập baseline như sau:

```text
Trước rotation:
  principal = orders-reader
  scope     = orders.read
  audience  = inventory-api
  issuer    = https://id.example.org/tenant-a

Trong và sau rotation:
  principal = orders-reader
  scope     = orders.read
  audience  = inventory-api
  issuer    = https://id.example.org/tenant-a

Chỉ credential version (v1 → v2) thay đổi.
```

Nếu cần thay bất kỳ principal/scope/audience/issuer/ACL nào, xử lý như một **change request phân quyền riêng**, có thử nghiệm và phê duyệt độc lập. Không tự ghép “cấp tạm thêm quyền” vào kế hoạch đổi credential.

## 9. Demo Java 17: chỉ promote phiên bản giữ nguyên scope

Ví dụ sau là bài luyện tư duy quản lý version. Nó **không chứa secret thật**, không thay thế IAM/IdP, không tự đồng bộ nhiều pod và không phải mã quản lý credential cho production. Mục tiêu là thể hiện invariant: chỉ thay version khi quyền không đổi.

Lưu vào `RotationInvariantDemo.java`:

```java
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

public final class RotationInvariantDemo {
    private static final Set<String> APPROVED_SCOPES =
            Set.of("orders.read");

    record Credential(String version, Set<String> scopes) {
        Credential {
            Objects.requireNonNull(version);
            scopes = Set.copyOf(scopes);
        }
    }

    private static final AtomicReference<Credential> ACTIVE =
            new AtomicReference<>(
                    new Credential("v1", APPROVED_SCOPES));

    static void promote(Credential candidate) {
        if (!candidate.scopes().equals(APPROVED_SCOPES)) {
            throw new IllegalArgumentException("scope drift");
        }
        ACTIVE.set(candidate);
    }

    public static void main(String[] args) {
        System.out.println("before=" + ACTIVE.get().version());
        promote(new Credential("v2", Set.of("orders.read")));
        System.out.println("after=" + ACTIVE.get().version());
        try {
            promote(new Credential(
                    "v3", Set.of("orders.read", "orders.write")));
        } catch (IllegalArgumentException e) {
            System.out.println("reject=" + e.getMessage());
        }
        System.out.println("active=" + ACTIVE.get().version());
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac --release 17 RotationInvariantDemo.java
java RotationInvariantDemo
```

Kết quả stdout:

```text
before=v1
after=v2
reject=scope drift
active=v2
```

`AtomicReference` tạo điểm chuyển active trong một JVM. Trong hệ thống thực, policy/invariant được thực thi ở IdP, IAM, DB grant, API authorization, gateway và/hoặc secret manager; cần giao dịch/rollout nhất quán, cơ chế làm mới client, số liệu quan sát, phát hiện drift và kiểm tra quyền ở mọi thành phần, không chỉ một phép so sánh `Set`.

## 10. Rotation khẩn cấp khi nghi lộ khóa hoặc secret

Không áp dụng lịch overlap bình thường một cách máy móc cho compromise. Credential v1 bị lộ có thể đang được dùng để giả mạo identity; tiếp tục cho v1 hợp lệ chỉ để tránh downtime có thể làm tăng tổn thất.

Quy trình ứng phó phụ thuộc loại vật liệu:

- **JWT signing private key bị lộ:** dừng phát token bằng khóa cũ, phát khóa mới và đưa verifier lên cấu hình tin cậy mới càng nhanh càng tốt; revoke/chặn token cũ theo cơ chế hiện có, kiểm tra cache JWKS, token lifetime và các bản sao; điều tra các token từng được ký. Phải công khai/trao đổi rủi ro availability khi vô hiệu hóa token cũ.
- **OAuth2 client secret/API key bị lộ:** thu hồi secret ở phía IdP/provider, tạo secret mới cùng identity/quyền thấp nhất, cập nhật workload, tìm và vô hiệu token đã phát nếu hệ thống cho phép. Chỉ thay secret không bảo đảm mọi access token cũ bị thu hồi.
- **TLS private key bị lộ:** thu hồi/thay chứng thư, rotate private key, triển khai chain tin cậy mới; kiểm tra OCSP/CRL và cách từng client thực sự xử lý revocation; không giả định mọi client sẽ kiểm tra OCSP hoặc mọi TLS session cũ tự ngắt.
- **CA/private key của CA bị lộ:** xem lại toàn bộ danh tính có thể bị giả mạo, thay trust anchors và ràng buộc identity, không tin tạm tất cả chứng thư do CA đó cấp.

Trường hợp khẩn cấp có thể đòi hỏi **fail closed** hoặc gián đoạn có kiểm soát, đặc biệt khi không thể chặn nhanh consumer đang giữ cache. Quyết định có biên bản, owner chịu trách nhiệm và giới hạn thời gian; không biến ngoại lệ khẩn cấp thành một rule `permitAll` kéo dài.

## 11. Kiểm thử trước, trong và sau rotation

### 11.1. Ma trận test JWT/authorization

| Trường hợp | Kỳ vọng |
| --- | --- |
| Token `k1` trước T2, đúng `iss/aud/exp/scope` | `200` tại endpoint được phép |
| Token `k2` sau T2, cùng claims hợp lệ | `200` tại endpoint được phép |
| Token `k1` còn hạn trong overlap | Được xác minh đến ngưỡng đã duyệt; không có scope phụ |
| Token `k1` sau hết hạn hoặc khi key thực sự revoked | `401` (token không hợp lệ); lưu ý cache key của verifier |
| Token có chữ ký lạ, `kid` không nhận biết, `alg=none` | `401` |
| Token hợp lệ nhưng thiếu `orders.read` | `403` ở endpoint đòi scope; có thể `401` nếu token không qua authentication |
| Token đúng chữ ký nhưng `iss` hoặc `aud` sai | `401` |
| JWKS endpoint ngừng hoạt động | Hành vi có kiểm soát theo cache/timeout; không bypass verification |

Mã HTTP phân biệt **authentication** (401 khi không chứng minh được danh tính) và **authorization** (403 khi đã xác thực nhưng không đủ quyền). Với filter chain, custom exception handler, opaque token hoặc lỗi vận hành, trạng thái cụ thể có thể khác; test phải đối chiếu với policy dự kiến.

### 11.2. Ma trận test secret và TLS

1. **Client credentials:** chỉ sau khi ép xin token mới mới kết luận secret v2 thành công; kiểm tra v1 bị từ chối sau khi revoke. Scope/identity/audience của token mới phải giống baseline.
2. **Concurrent requests:** canary và pod cũ cùng hoạt động, không trộn secret/cert giữa request, không làm lộ credential trong `Reactor Context`, MDC, logs, traces.
3. **Kết nối lâu:** kiểm tra connection pool, WebSocket/HTTP2 (nếu có), TLS renegotiation không được giả định; xác nhận handshake mới dùng certificate mới.
4. **mTLS:** đúng client certificate và đúng workload identity được phép; certificate có chain đúng nhưng danh tính không nằm allowlist vẫn phải bị từ chối.
5. **Chứng thư sai:** SAN không khớp, hết hạn, key không khớp certificate, chain không tin cậy; không dùng trust-all như bước khắc phục.
6. **Phân phối lỗi:** secret manager/JWKS/volume refresh chậm, một pod dùng version cũ; retry có giới hạn, cảnh báo và rollback xác định.
7. **Thu hồi:** sau giai đoạn overlap, cố tình dùng credential cũ và không thể tạo phiên/kết nối mới được chấp nhận; kiểm tra cache không bị bỏ qua.
8. **Quyền:** so sánh danh sách `principal, scope, role, audience, route policy, DB grants, CA/SAN allowlist` trước và sau. Không có quyền bổ sung mà chưa được duyệt.

Không dùng key/secret production để kiểm thử; dùng vật liệu ngắn hạn của môi trường staging/canary có policy tương ứng. Dựng bộ kiểm thử tiêu cực với token sai chữ ký, token thiếu scope và chứng thư sai SAN. Luôn đo cả **tính an toàn lẫn tính sẵn sàng**.

## 12. Quan sát, rollback và vận hành

Các tín hiệu cần có:

- **Chỉ số an toàn:** số lần token không xác minh được, `kid` không được nhận biết, `iss/aud` sai, authentication 401, authorization 403, handshake TLS lỗi, client secret bị provider từ chối. Bám sát baseline và phân biệt lỗi cố ý do test với lỗi thực.
- **Chỉ số triển khai:** version đang active theo workload (chỉ là opaque identifier), số pod đã cập nhật, thời gian tới `exp` token cũ cuối cùng, hạn chứng thư, lần reload SSL thành công/thất bại, tỷ lệ request canary.
- **Chỉ số độ ổn định:** latency, lỗi 5xx do phụ thuộc IdP/secret store, timeout kết nối, pool mới không kết nối được, tình trạng collector và health check.

Logging chỉ nên dùng `credentialVersion=v2` hoặc hash/identifier không thể truy ngược, **không in raw secret, authorization header, JWT, private key, certificate private-key PEM**. Tránh tạo metrics label bằng full token, user ID, serial số lượng lớn hay giá trị secret; giữ cardinality thấp. Vị trí bắt đầu rotation không cần quyền toàn bộ hệ thống: operator/automation cần quyền tạo phiên bản đúng scope, reviewer duyệt policy, workload chỉ đọc credential của chính nó.

Rollback cũng phải có ranh giới: khi secret v1 **chưa bị thu hồi và không bị lộ**, có thể tạm quay lại v1 trong cửa sổ đã duyệt rồi điều tra nguyên nhân. Khi v1 **đã bị compromise/revoked**, rollback về v1 là không an toàn; phải sửa phía v2, tạo v3 hoặc dừng có kiểm soát. Không rollback bằng `permitAll`, `trustAll`, tắt JWT validation hay cấp `admin`.

### Runbook rút gọn trước khi bấm cutover

```text
[ ] Có inventory owner/consumer/TTL/cache và bản sao secret/cert cũ.
[ ] Đã so sánh policy trước–sau: principal, scopes, aud, iss, roles,
    API routes, DB grants, SAN, CA trust và mTLS identity.
[ ] Material mới đã phát hành đúng nơi, khóa riêng/secret được bảo vệ.
[ ] Verifier/trust consumer đã sẵn sàng nhận material mới.
[ ] Canary pass cả test thành công và test từ chối sai quyền.
[ ] Cutover writer/client có quan sát 401/403, TLS, 5xx và latency.
[ ] Đã có mốc hết overlap theo token TTL/cache/connection thực tế.
[ ] Đã thử thu hồi version cũ và bảo đảm client mới vẫn hoạt động.
[ ] Đã xác định rollback cho trường hợp bình thường và incident riêng.
[ ] Đã thu hồi quyền tạm của operator, dọn version/bản sao cũ và lưu audit.
```

Quyền vận hành cấp cho automation (nếu cần) phải được giảm về mức tối thiểu ngay khi kết thúc nhiệm vụ; **không** cấp quyền truy cập bí mật của mọi dự án trong suốt thời gian chờ. Với production nhiều vùng, kiểm tra từng region và từng nhóm consumer trước khi gỡ phiên bản cũ.

## 13. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Xóa `k1` khỏi JWKS ngay sau khi signer đổi `k2` | Token `k1` chưa hết hạn đột ngột 401 | Công bố k2 sớm, chờ TTL + skew + cache hợp lý rồi gỡ k1 nếu không compromise |
| Dựa vào `kid` hoặc payload JWT mà không verify | Có thể tin dữ liệu do attacker tự tạo | Dùng `ReactiveJwtDecoder` đã cấu hình issuer/JWKS/validator |
| Dùng `permitAll`/bỏ kiểm tra issuer vì IdP lỗi | Leo thang quyền | Fail closed theo chính sách, alert, xử lý IdP/cache |
| Chỉ thay secret trong Vault, bean vẫn giữ v1 | Client vẫn xin token với secret cũ | Xác định reload/recreate registration/rolling restart, ép xin token mới |
| Đổi DB password khi pool còn mở, không test kết nối mới | Lỗi muộn khi connection được tạo lại | Canary tạo connection mới, thoát pool cũ có kiểm soát |
| Tải lại TLS server cert rồi nghĩ WebClient outbound cũng đổi | Outbound vẫn sử dụng trust/SSL context cũ | Kiểm tra từng consumer; refresh/recreate outbound client/pool riêng |
| Mở truststore cho CA bất kỳ, bỏ hostname check | Chấp nhận danh tính ngoài phạm vi | Chỉ tin CA được duyệt + SAN/name constraints + authorization identity |
| K8s Secret mount qua `subPath` rồi chờ hot reload | File trong container không cập nhật | Mount directory bình thường hoặc rolling restart |
| Log token/secret trong khi debug sự cố rotation | Rò rỉ mới, tăng blast radius | Log identifier/version/status an toàn, redact mọi credential |
| Thu hồi old signing key nhưng quên JWKS cache | Token cũ còn được xác minh một thời gian | Cấu hình TTL/cache/revocation phù hợp, test tất cả verifier |
| Phát secret v2 bằng grant/scope lớn hơn v1 | Mở quyền ngoài mục tiêu | So sánh policy và từ chối promotion nếu có drift |

## 14. Tổng kết

Một đợt rotation thành công phải thỏa đồng thời **tính liên tục**, **xác thực chính xác**, **quyền bất biến** và **thu hồi kiểm chứng được**. Với Spring Security reactive, dùng `ReactiveJwtDecoder` cùng JWKS/issuer/audience để hỗ trợ đổi khóa JWT mà giữ nguyên `SecurityWebFilterChain`; với OAuth client/API key/DB, phối hợp vòng đời secret với cache và client/pool; với TLS/mTLS, dùng SSL bundle/rollout phù hợp, xác minh chain và danh tính chứng thư. Chỉ cho các phiên bản **vật liệu cùng quyền** cùng tồn tại khi cần; tuyệt đối không nới IAM, API authorization hay TLS trust một cách thiếu kiểm soát để bù lỗi cutover.

## Tài liệu đối chiếu

- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Boot 3.3 — Resource Server configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Boot 3.3 — SSL bundles và reload: https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html
- Kubernetes — Secret distribution/update behavior: https://kubernetes.io/docs/concepts/configuration/secret/
- OWASP Cheat Sheet — Secrets Management: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
