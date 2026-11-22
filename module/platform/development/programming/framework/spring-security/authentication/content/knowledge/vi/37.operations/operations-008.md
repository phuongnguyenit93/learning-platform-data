# Luân chuyển khóa, API key và chứng thư trong vận hành Spring Security authentication

## 1. Vì sao phải luân chuyển thông tin mật?

**Rotation (luân chuyển)** là quá trình đưa thông tin mật/khóa mới vào sử dụng và rút thông tin cũ ra một cách có kiểm soát. Mục đích là giới hạn thời gian một credential bị lộ có thể bị khai thác, duy trì chính sách cryptographic, tránh chứng thư hết hạn đột ngột và làm việc thay đổi tài sản bảo mật trở thành quy trình có thể thử nghiệm, rollback và audit.

Trong hệ thống Spring Security authentication, ít nhất bốn đối tượng có vòng đời riêng:

1. **Khóa ký JWT / JWS:** Authorization Server hoặc IdP giữ **private signing key**; Resource Server nhận **public verification key** qua JWKS hoặc cấu hình tin cậy. Luân chuyển ảnh hưởng đến token còn hạn, JWK cache, `kid` và thuật toán.
2. **API key / client secret:** Credential bí mật dùng cho ứng dụng hoặc service tích hợp. Luân chuyển thường cần **hai key còn hợp lệ tạm thời**, cập nhật client, quan sát old-key usage và revoke có chủ đích.
3. **Chứng thư TLS / mTLS X.509:** Bao gồm leaf certificate, private key tương ứng, intermediate chain và **trust anchors** ở client/server. Luân chuyển ở điểm kết thúc TLS, reverse proxy, client HTTP hoặc service mesh. Chứng thư TLS **không phải** khóa ký JWT chỉ vì đều dùng RSA/EC.
4. **Khóa đối xứng hoặc khóa mã hóa dữ liệu:** HMAC JWT, application secret, encryption key hoặc KEK có thể đòi **giải mã/verify phiên bản cũ** trong lúc chỉ mã hóa/ký bằng khóa mới. Việc đổi khóa không tự tái mã hóa dữ liệu cũ hoặc revoke token đã phát hành.

Các trường hợp rotation khác nhau:

| Đối tượng | Ai giữ secret/private key? | Ai cần cập nhật? | Thế nào là hoàn tất? |
| --- | --- | --- | --- |
| JWT asymmetric signing key | Authorization Server/HSM/KMS | JWKS và mọi verifier Resource Server | Ký mới bằng K2; old JWT được xử lý theo TTL; K1 bị retire đúng thời điểm |
| HMAC secret | Bên ký và bên kiểm cùng biết secret | Tất cả bên verify và signer | K2 dùng tạo MAC; K1 ngừng verify khi không còn thông điệp hợp lệ |
| API key | Client dùng key; server nhận bản băm/metadata | Từng client/integration và auth service | Mọi client dùng key mới; key cũ revoked, usage old = 0 |
| TLS server certificate | TLS terminator (Ingress/Proxy/embedded server) giữ private key | Endpoint server, đôi khi client truststore | Chứng thư mới được phục vụ, hostname/chain hợp lệ, key cũ không còn được dùng |
| mTLS client certificate | Client giữ private key | Client, server trust policy/identity mapping | Client mới bắt tay được; cert cũ bị chặn theo chính sách |
| Encryption-at-rest key | KMS/HSM hoặc app, tùy envelope design | Dịch vụ encrypt/decrypt và key metadata | Dữ liệu mới dùng key mới, dữ liệu cũ đọc được hoặc đã rewrap/re-encrypt |

**Cảnh báo:** “Rotation đã xong” không đồng nghĩa “toàn bộ credential cũ lập tức vô hiệu”. Ở rotation theo kế hoạch thường cần overlap để tránh downtime; khi **nghi khóa đã bị lộ**, overlap cũ có thể kéo dài thời gian attacker sử dụng. Phải áp **runbook sự cố** khác runbook bảo trì.

## 2. Vòng đời và ranh giới tin cậy của từng loại

### 2.1. Lifecycle chuẩn

```text
Inventory & owner
      |
      v
Generate K2 with CSPRNG / approved KMS/HSM
      |
      v
Store securely -> authorize access -> tag version and purpose
      |
      v
Deploy verification/trust for K2 BEFORE active use (where needed)
      |
      v
Switch producer/signing/encryption/client to K2
      |
      v
Observe traffic: K1 last-used, K2 success, error rate, latency
      |
      v
Retire K1 by policy; revoke when necessary
      |
      v
Delete/destroy unused material according to retention/backup rules
      |
      v
Audit evidence & next rotation schedule
```

Để kiểm soát thay đổi, lập **credential inventory** có owner, issuer, môi trường, mục đích, key ID/certificate serial, service dependencies, thời điểm tạo/hết hạn, lịch rotation, người phê duyệt và kế hoạch rollback. Không ghi raw secrets trong inventory.

### 2.2. Phân biệt các thao tác

- **Generate:** tạo key/secret mới có entropy, thuật toán và kích thước đáp ứng chính sách. Private key không phải thứ copy từ kho mã nguồn.
- **Publish trust:** đưa public JWK mới/trust anchor hợp lệ tới verifier hoặc cung cấp API key mới đến client đã xác minh.
- **Activate:** producer bắt đầu ký/mã hóa/gửi credential mới; phải tách khỏi publish trust.
- **Expire:** một token/certificate tới `exp`/`notAfter` theo thời gian; không đồng nghĩa key đã bị thu hồi.
- **Retire:** không phát sinh credential mới bằng key cũ, rồi dừng verify/accept khi hết cửa sổ hợp lệ.
- **Revoke:** chủ ý từ chối credential/key ngay theo chính sách, có thể làm gián đoạn token/cert còn hạn.
- **Destroy:** xóa private/secret material sau khi bảo đảm không còn nhu cầu giải mã/điều tra/khôi phục hợp pháp; backup và recovery key cần chính sách riêng.

### 2.3. Vai trò KMS/HSM/secret manager

Không đặt private key, API key hay password keystore trực tiếp trong Git, Docker image, issue tracker hoặc log. Chọn secret manager/KMS/HSM có IAM phân quyền, audit, versioning, rotation policy và hạn chế export private key. Với HSM, **non-exportable** key giảm rủi ro nhưng không loại bỏ nguy cơ lạm dụng quyền ký khi credential KMS bị chiếm. Phân tách quyền tạo, kích hoạt, revoke và đọc metadata; ưu tiên nguyên tắc **least privilege** và break-glass có kiểm soát.

Các nguồn dữ liệu nên được tin khác nhau:

- **JWKS URL cấu hình từ trusted issuer:** public key verification có thể tải từ endpoint IdP đáng tin. Đó **không phải** nơi cất private signing key.
- **JWS header từ client:** `kid`/`alg` do token đưa vào là **dữ liệu chưa đáng tin**, phải bị kiểm theo allowlist và key set đã định sẵn.
- **Chứng thư từ TLS peer:** phải validate chain, SAN, thời hạn, EKU và expected identity; nhận một certificate bất kỳ không tự có quyền trong Spring Security.
- **API key nhận qua HTTP:** là một secret bearer; chỉ lookup được key ID/hash không thay phần xác minh owner/status/expiry/permissions.

## 3. Luân chuyển khóa ký JWT qua JWK Set: K1 → K2

### 3.1. Luồng JWT và JWKS trong Spring Security

Ở hệ thống OAuth2/OIDC:

```text
Authorization Server / IdP
  Private signing key K1
     |
     | sign JWT {iss, aud, sub, exp, ...} ; JWS protected header kid=k1
     v
Client nhận Bearer JWT
     |
     | Authorization: Bearer <jwt>
     v
Spring Security Resource Server
  NimbusJwtDecoder / JwtAuthenticationProvider
     |
     | tải JWKS từ issuer-configured trusted URL (có cache)
     | chọn public key theo kid và algorithm policy
     | verify signature + iss/aud/exp/nbf + roles/scopes
     v
Authentication / authorization -> API resource
```

JWKS minh họa chỉ chứa **public** fields:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "auth-2026-10-k1",
      "n": "<public-rsa-modulus>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "alg": "RS256",
      "kid": "auth-2026-11-k2",
      "n": "<new-public-rsa-modulus>",
      "e": "AQAB"
    }
  ]
}
```

Đây là **JSON mô phỏng**; `n` dạng placeholder, không phải JWK hợp lệ để verify. Với RSA, JWK private có thể chứa `d`/`p`/`q`/`dp`/`dq`/`qi` và **không bao giờ xuất bản** chúng trên public JWKS. Các trường `kid`, `kty`, `alg` và `use` hỗ trợ chọn/giới hạn khóa; riêng `kid` **không chứng minh** endpoint cung cấp key đáng tin.

**Ngăn key injection:** không tự động fetch `jku`/`x5u` từ JWS header do attacker điều khiển, không chấp nhận `alg=none` hoặc chuyển HS256/RS256 tùy ý. Trust anchor là **issuer + JWKS URI/operator configuration đã kiểm soát**, không phải link bên trong token. Các trường `iss`/`aud`, key type, algorithm và tenancy phải khớp policy.

### 3.2. Quy trình rotation theo kế hoạch, không gián đoạn

Ví dụ K1 đang ký JWT TTL tối đa 15 phút; verifier có thể cache JWKS vài phút:

1. **T-1: Chuẩn bị K2.** Tạo key pair mới trong KMS/HSM hoặc key store được bảo vệ; định danh `kid=k2` **khác** k1. Không tái sử dụng K1 dưới một kid mới.
2. **T0: Publish public K2, vẫn ký bằng K1.** JWKS đáng tin phải đồng thời chứa K1 và K2. Kiểm endpoint thực, HTTP cache/CDN, phân vùng/region và mọi Resource Server có thể tải public K2.
3. **T0 + propagation:** chờ thời gian refresh JWKS cache có tính đến edge, failover và network. Spring Security 6.5 reference mô tả Resource Server cache JWK set trong memory mặc định khoảng **5 phút**; custom cache/CDN có thể khác. Không switch signer trước khi verifier nhìn được K2.
4. **T1: Switch active signing key sang K2.** JWT mới có `kid=k2` và được ký bằng private K2. Từ đây **không phát JWT mới bằng K1**. K1 public vẫn nằm trong JWKS để các JWT chưa hết hạn tiếp tục verify.
5. **T1 + TTL + skew/buffer:** chờ đến khi **JWT cuối cùng ký bằng K1** đã hết hạn theo cấu hình xác minh, bao gồm clock skew được cho phép, processing delay và các consumer đặc biệt. Ví dụ: ký K1 cuối 09:00, JWT TTL 15 phút, skew 1 phút → duy trì public K1 ít nhất tới sau **09:16** (và thêm buffer theo SLO).
6. **Retire K1 public trust:** gỡ K1 khỏi JWKS khi không còn token hợp lệ cần nó; canary API/region; theo dõi lỗi `kid not found`, 401, JWT signature errors. Sau đó hủy/disable private K1 theo retention/break-glass policy. Private K1 nên được **ngừng sử dụng để ký ngay ở T1**.
7. **Audit/close:** ghi mã change, owner, thời điểm publish/switch/retire, verifier health, số JWT K1 còn lại/old-kid attempts đã lọc secret và kế hoạch rotation kế tiếp.

**Cửa sổ overlap không phải con số tùy tiện 5 phút.** Nó phụ thuộc thời điểm token K1 **được phát cuối**, max token lifetime, allowed skew, sự phân phối JWKS và cache tầng trung gian. Nếu JWT TTL tới 2 giờ, giữ K1 public 5 phút rồi xóa sẽ làm một lượng lớn request hợp lệ nhận 401.

### 3.3. Canary, rollback và độ sẵn sàng

- Canary signer K2 trên test tenant/client nội bộ trước, kiểm Resource Server tất cả region chấp nhận `kid=k2`.
- Verify cả **token K1 còn hạn** và **token K2 mới** trong giai đoạn overlap; thử token ký bằng key lạ, `kid` giả, sai issuer/audience và hết hạn phải bị từ chối.
- Rollback khi K2 chưa phân phối: quay lại **ký bằng K1** chỉ trong rotation bình thường **nếu K1 chưa bị lộ/retire** và còn được kiểm soát. Nếu K1 bị compromise, không “rollback” về K1 để cứu availability.
- Cache TTL, DNS, proxy/CDN, issuer metadata, JWK set cache và verifiers có cấu hình cố định public key cần được kiểm; một pod dùng key hardcoded có thể là single point gây outage.
- Nếu public JWKS endpoint tạm thời không truy cập được, verifier có thể dùng cache hiện tại theo cấu hình và phiên bản, nhưng khi cần K2 chưa cache sẽ fail. **Không fail-open** (accept JWT chưa verify) để giảm 401.

## 4. Cấu hình Spring Boot 3.x / Spring Security 6.5 Resource Server

Ví dụ ứng dụng **xác minh JWT**, không phải nơi sở hữu private JWT signing key. Dùng Spring Boot 3.x + Spring Security 6.5 Servlet, Java 17+. Khi chạy thực, thay issuer/JWKS/audience từ OAuth provider tin cậy, sử dụng HTTPS, xác nhận metadata và dependency version.

### 4.1. Gradle dependencies

Trong project Spring Boot có `build.gradle` và plugins tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 4.2. application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/tenant-a
          jwk-set-uri: https://idp.example.test/tenant-a/jwks
          audiences: api://orders
          jws-algorithms: RS256
```

Giải thích:

- `issuer-uri` thiết lập chính sách `iss`; nếu cấu hình thêm `jwk-set-uri` để Resource Server không cần gọi issuer discovery khi startup, Spring vẫn có thể validate issuer claim từ `issuer-uri`.
- `jwk-set-uri` phải trỏ đến URL **được operator tin cậy**, không lấy từ claim/header token. Path endpoint cụ thể tùy IdP, không có một JWKS path bắt buộc áp cho mọi issuer.
- `audiences` yêu cầu `aud` thuộc API đúng (tên/cấu hình tương thích Spring Boot/Security version). Token cho API khác dù có chữ ký đúng phải bị từ chối.
- `jws-algorithms` giới hạn thuật toán chấp nhận; ví dụ chỉ dùng **RS256**. Không mở toàn bộ algorithms tùy theo `alg` do token yêu cầu.

**Về phiên bản:** đây là cấu hình Spring Boot 3/Spring Security 6.5 theo tài liệu thuộc cùng dòng. Nếu ứng dụng đã tự khai báo `JwtDecoder` bean, có thể **thay thế phần auto-configuration của Boot**, khiến `issuer-uri`/`audiences` không tự được áp như bạn nghĩ. Khi custom decoder, thiết lập `JwtValidator` cho issuer/audience/exp/nbf và algorithm trust **rõ ràng**; viết negative tests để xác nhận.

### 4.3. SecurityFilterChain nhận JWT

File `src/main/java/com/example/orders/ApiSecurityConfig.java` (đặt trong project Spring Boot đã có `@SpringBootApplication`):

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/actuator/health").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là **app config fragment**, không runnable độc lập bằng `javac`: cần web app, issuer thật, trust material thật và token hợp lệ. Các quyền chi tiết của API như `SCOPE_orders.read`/tenant và object ownership phải được khai báo riêng; ví dụ chỉ cho thấy lifecycle xác minh.

**Điểm nguy hiểm:** một resource server có JWT decoder **không phải** Authorization Server phát JWT. Đừng đặt private signing key trong resource-server container chỉ vì nó cần kiểm chữ ký. Với asymmetric JWS, resource-server chỉ cần **public key** từ issuer đáng tin.

### 4.4. JWK cache và hành vi lỗi lúc rotation

Theo Spring Security 6.5 reference, Resource Server mặc định cache JWK set trong-memory khoảng **5 phút**, có thể tùy chỉnh qua `NimbusJwtDecoder`/Spring Cache. Tùy Nimbus version và cache implementation, behavior refresh khi gặp `kid` mới có thể thay đổi; không hứa “mọi verifier sẽ refresh ngay lập tức mỗi lần có kid lạ”.

Quan sát những trường hợp quan trọng:

| Scenario | Kết quả kỳ vọng | Hướng điều tra |
| --- | --- | --- |
| K1 token còn hạn, JWKS chứa K1+K2 | 200 (nếu đủ quyền) | Kiểm issuer, audience, signature |
| K2 token mới, verifier cache chưa có K2 | Có thể 401 trong propagation window | Kiểm cache TTL/HTTP cache, thời điểm publish và rollout |
| K1 bị retire khi token K1 vẫn còn `exp` | 401 khi verifier hết cache hoặc update | Old-key retirement quá sớm |
| JWKS endpoint tạm lỗi | Tùy cache/HTTP timeout; chưa chắc 100% fail ngay | Circuit/last-known-good cache theo policy, không accept token chưa verify |
| `kid` trùng nhưng public key khác | Có thể chọn sai key/verify fail, khó chẩn đoán | Không tái sử dụng kid trong trust domain |
| Token có `jku` attacker URL | Không được tải key tùy ý từ header | Ràng buộc JWKS URL theo issuer/operator |
| Issuer mới nhưng JWKS chung | Không tự tin issuer mới | Validate `iss`/tenant/aud độc lập, không chỉ key match |
| Token hợp lệ nhưng thiếu scope | 403 theo auth policy | Không đổ lỗi key rotation khi đã decode thành công |

**JWK rollover cần giám sát:** tỷ lệ `401 invalid_token`, unknown kid, JWKS fetch failures/timeouts, theo issuer, environment, region, key ID (metadata), issuance timestamp và verifier version. Không log raw JWT hoặc header `Authorization`.

## 5. Khóa đối xứng, signing key và khóa mã hóa dữ liệu: không dùng một playbook cho tất cả

### 5.1. JWT dùng HMAC (HS256)

Với HS256, **cùng secret** được dùng ký và verify. Không thể công bố public JWKS để “chia sẻ secret”: một đối tác giữ secret HMAC cũng có khả năng **tạo chữ ký giả** nếu bị lộ hoặc có hành vi không tin cậy. Chỉ dùng HMAC khi mô hình trust phù hợp; giữa tổ chức độc lập, bất đối xứng RSA/EC thường cho phân quyền verifier dễ hơn.

Để xoay HS256:

- Tạo secret H2 mạnh trong secret manager; deploy H2 đến **tất cả verifier được phép** trước.
- Hệ thống ký chuyển sang H2, token mới có key version/`kid` được kiểm soát.
- Verifier giữ H1/H2 trong overlap theo max JWT TTL và skew; không đoán secret theo `alg` hoặc brute-force cả kho không giới hạn.
- Sau thời điểm retirement, disable H1. Nếu H1 lộ, revoke sớm và chấp nhận ảnh hưởng tới token cũ theo incident policy.

### 5.2. Encryption keys (AES, data encryption key, KEK)

Khóa ký JWT không giống khóa **mã hóa dữ liệu**. Khi đổi khóa mã hóa, dữ liệu cũ có thể chỉ đọc được bằng khóa cũ. Mô hình envelope encryption thường có:

- **DEK (Data Encryption Key):** mã hóa dữ liệu hoặc từng object.
- **KEK (Key Encryption Key):** mã hóa/wrap DEK. Một số KMS cho phép rotate KEK và giữ version cũ để decrypt; không nhất thiết re-encrypt mọi dữ liệu ngay.
- **Key version metadata:** mỗi ciphertext gắn version/identifier đúng để chọn decrypt key đã cho phép. Không tin identifier mà bỏ integrity/tag check.
- **Đọc cũ/ghi mới:** ứng dụng mới encrypt bằng K2; decrypt dữ liệu từ K1/K2 theo version, rồi migrate/rewrap dần.
- **Khẩn cấp:** khi DEK/KEK lộ, đánh giá dữ liệu bị lộ và re-encryption; chỉ ngừng ký JWT không giảm hậu quả lộ plaintext cũ.

**Không xóa key cũ trước khi chắc chắn đã re-encrypt/rewrap** toàn bộ dữ liệu và backup cần đọc. Nhưng cũng không giữ khóa compromised online vô thời hạn vì sợ mất dữ liệu; cần migration/isolation/incident plan. Key rotation là việc vận hành bảo đảm confidentiality **và** availability.

### 5.3. Secret dùng ký cookie, CSRF hoặc remember-me

Một số ứng dụng có secret ký remember-me cookie hoặc application token. Đổi secret có thể **đăng xuất hàng loạt** nếu server không chấp nhận token còn được ký bằng secret cũ. Đây có thể là chủ ý khi có sự cố. Không tự động lấy playbook JWKS/public-key overlap áp cho cookie HMAC hoặc session store mà không biết lớp nào thực sự kiểm chữ ký. Spring Security CSRF token lifecycle, remember-me và OAuth JWT có cơ chế khác nhau.

## 6. Luân chuyển API key: hai key hợp lệ trong thời gian ngắn

### 6.1. API key là credential gì?

API key phổ biến để định danh/ủy quyền **service-to-service hoặc client tích hợp**, thường là bearer string: ai có giá trị key có thể gửi nó tới API theo scope. Nó không mặc định là OAuth access token, không có sẵn signature/issuer/audience như JWT, và **Spring Security không tự cung cấp một API-key authentication scheme chuẩn duy nhất cho mọi dự án**.

Ứng dụng có thể dùng custom `AuthenticationFilter`/`AuthenticationProvider`, gateway hoặc filter riêng để đọc header `X-API-Key` hoặc một `Authorization` scheme được thiết kế. Không nên chấp nhận API key trong URL query (dễ rò qua log/history/referrer). Luôn dùng HTTPS; không log header key.

Một key nên có metadata:

| Field | Vai trò | Lưu ý |
| --- | --- | --- |
| `keyId` | ID công khai, không phải secret | Cho lookup/audit và thông báo client nào cần rotate |
| `secretHash` | Digest của **secret entropy cao** hoặc HMAC với pepper phù hợp | Không lưu plaintext key trong DB thông thường |
| `ownerClientId` | Service/client đã đăng ký | Không để client tự ghi owner trong request rồi tin |
| `scope/role/resource` | Quyền tối thiểu | Tách key deploy-prod với dev/test |
| `createdAt/lastUsedAt` | Theo dõi vòng đời | Metrics không chứa full key |
| `expiresAt/revokedAt` | Cơ chế loại bỏ | Kiểm cả expiry, revoked, client status |
| `environment/tenant` | Giới hạn phạm vi | Không tái sử dụng key đa tenant/env |
| `rotationGroupId` | Liên kết K1/K2 cùng client (nếu cần) | Cho overlap và báo cáo tiến độ |

Khi có key prefix dễ nhận diện như `ak_live_<public-id>.<random-secret>`, **public ID** không được phép trở thành authentication factor. Chỉ khi secret được verify và key record còn active, mới cấp `Authentication`/scopes.

### 6.2. Runbook zero/minimal-downtime cho API key

1. **Inventory client và quyền:** client A đang dùng key A1; record scopes, owner, traffic pattern, contact và lịch deploy.
2. **Issue A2** bằng CSPRNG (ít nhất mức entropy đủ mạnh, ví dụ 256-bit random) trong manager/secure admin interface; hiển thị **một lần** qua kênh đã xác thực và bảo mật. Giữ A1 hoạt động tạm thời.
3. **Deploy client A2** qua secret manager/config/CI pipeline an toàn, không in key vào logs hoặc build artifacts. Canary một instance, rồi rollout fleet.
4. **Dual-accept:** server chấp nhận A1 và A2 với cùng owner/scope hoặc scope được giảm theo policy. Không được vô tình nâng quyền của A2.
5. **Observe:** đếm last-used của A1 theo key ID, region và client; xác nhận traffic A2 ổn định. Kiểm consumer batch/offline có thể không gọi API hàng ngày.
6. **Notify deadline** và **disable A1** theo cửa sổ đã thỏa thuận, sau đó thu hồi vĩnh viễn. Test A1 trả 401/403 theo scheme của ứng dụng và A2 vẫn hoạt động.
7. **Record rotation evidence:** ai phát, ai xác nhận, lịch revoke, usage old-key về 0 và các downstream incidents. Không ghi secret value vào ticket.

**Nếu A1 đã bị lộ:** không chờ mọi client cập nhật xong mới revoke trong mọi tình huống; cân nhắc revoke ngay, giảm scope, cô lập client, giám sát abuse và đổi credential phụ thuộc. Kế hoạch khẩn cấp ưu tiên containment, kể cả gây gián đoạn.

### 6.3. Vì sao không thay key tại một ô duy nhất?

Một thiết kế “mỗi client chỉ có một key trong DB” khiến khi đổi từ A1 sang A2, client ở các pod đã rollout một phần còn dùng A1 bị 401 ngay. Dual-active với **deadline có giới hạn** cho phép chuyển đổi có thể quan sát. Overlap **không phải đồng nghĩa cấp hai keys vĩnh viễn**: mỗi key có expiration, revoke button và audit.

**Các lỗi thường gặp:** client có key mới nhưng server vẫn cache key revoked, CD pipeline in raw key, key mới vô tình được cấp scope rộng hơn key cũ, metrics chia sẻ key value, A1 vẫn sống sau deadline, hoặc chấp nhận A2 mà không kiểm owner/tenant.

## 7. API key + Spring Security: điều gì cần tự thiết kế?

### 7.1. Authentication và Authorization phải tách riêng

Nếu app nhận `X-API-Key`, thành phần nhận key phải:

1. Trích xuất từ đúng header và giới hạn kích thước/format; reject nhiều header trùng nếu chính sách không cho phép.
2. Xác minh **secret** với record lưu trong trusted DB/secret manager; key ID chỉ là lookup hint.
3. Check revoked/expired/disabled, owner, tenant, environment, allowed API/scopes và rate limiting.
4. Chuyển kết quả thành `Authentication` đã được provider xác minh, ánh xạ `GrantedAuthority` tối thiểu.
5. Dùng Spring Security authorization để kiểm `hasAuthority(...)` và resource ownership ở controller/service.
6. Không tự đánh dấu `authenticated=true` dựa vào việc “header có tồn tại”.

**Chọn đúng cơ chế:** nếu yêu cầu OAuth2 access scopes/delegation/client authentication, xem OAuth2 Client Credentials hoặc mTLS thay vì tự xây API key cho mọi hệ thống. API key không tự có expiry/jti/replay protection như JWT; chỉ là opaque secret trừ khi bạn bổ sung metadata.

### 7.2. Kế hoạch tích hợp SecurityFilterChain

Đoạn sau là **phác thảo chính sách** cho app đã có custom `AuthenticationProvider`/filter triển khai an toàn; các API key authentication cụ thể không tồn tại tự động trong Spring Boot:

```java
@Bean
SecurityFilterChain apiKeyChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/partner/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/partner/health").permitAll()
            .anyRequest().hasAuthority("SCOPE_partner.read"))
        // Đăng ký AuthenticationFilter/Provider chuyên biệt ở cấu hình thật.
        // Chỉ cho permitAll() route health, KHÔNG cho cả /partner/**.
        .build();
}
```

Phải import `HttpSecurity`/`SecurityFilterChain`, khai báo bean và đặt filter/handler đúng với Spring Security version. **Đoạn trên không xác thực API key**; nếu copy nguyên và không gắn provider/filter, mọi request chưa có authentication sẽ bị chặn. Không coi nó là API key implementation hoàn chỉnh.

Một API key bị trộm có thể **bị replay cho tới khi revoke/expire** vì đây là bearer secret. Khóa theo IP hoặc mTLS client certificate có thể giảm phạm vi lạm dụng nhưng IP allowlist không phải cryptographic proof; phải định nghĩa cả khi client có NAT/proxy/CDN và tình huống đổi IP.

## 8. Luân chuyển chứng thư TLS: chứng thư, private key, chain và CA

### 8.1. Chứng thư TLS khác JWT/JWKS

Một TLS server certificate X.509 có các trường như Subject/SAN, issuer, serial, `notBefore`/`notAfter`, public key, signature và extensions (EKU/KeyUsage). TLS server phải giữ private key tương ứng (hoặc dùng KMS/HSM), đồng thời trình bày đúng **certificate chain** khi bắt tay TLS.

Ba đối tượng cần phân biệt:

| Đối tượng | Ví dụ | Nếu luân chuyển sai |
| --- | --- | --- |
| **Leaf server certificate** | `api.example.test`, SAN=DNS:api.example.test | Handshake fail vì expired/hostname mismatch |
| **Intermediate CA certificate** | CA trung gian trong full chain | Một số client thiếu chain sẽ báo unknown_ca |
| **Trust anchor / root CA** | CA public được OS/JVM tin hoặc private CA nội bộ | Client không tin server/client certificate mới |
| **Server private key** | Private key tương ứng leaf cert | Handshake fail nếu cert và key không khớp; bị lộ có nguy cơ impersonation |
| **mTLS client certificate** | Service A xác minh danh tính tại server B | Client bị deny hoặc ánh xạ sai principal khi cert đổi |

**Đổi leaf cert** không đồng nghĩa **đổi root CA**. Với public CA renewal, client có thể tiếp tục tin chain mới qua truststore hiện có. Với **private PKI / cross-sign / mTLS**, đổi CA/trust anchor cần rollout trust **hai chiều và đúng thứ tự**; nếu xóa CA cũ trước khi client mới hoạt động sẽ làm gián đoạn handshake.

### 8.2. ACME và renewal

**RFC 8555 (ACME)** mô tả protocol để client xin cấp/renew chứng thư, chứng minh kiểm soát identifier/domain và quản lý tài khoản ACME. ACME account key dùng **ký request đến CA**, **không phải** leaf certificate private key và càng không phải JWT signing key.

Quy trình:

1. Theo dõi certificate expiry của **mọi endpoint thực** (domain, regional LB, internal gRPC, outbound mTLS), không chỉ file trong repo.
2. Tạo CSR/new key pair theo policy; xác minh SAN/EKU/KeyUsage và chain, tên miền/dịch vụ, quyền truy cập private key.
3. Sử dụng ACME client (hoặc CA nội bộ) để cấp cert mới **trước khi** cert cũ hết hạn, có monitoring và lịch retry; chọn thời gian rotation trước expiry theo SLO, không chờ còn 1 ngày.
4. Cài cert+private key mới vào ingress/Load Balancer/embedded server; cập nhật fullchain đúng.
5. Thực hiện handshake mới với SNI và hostname validation đúng; canary từ **client thật** (JVM truststore, mobile app, service mesh) và quan sát TLS handshake errors.
6. Khi mọi endpoint đã dùng cert mới, rút cert/key cũ khỏi deployment. Nếu private key cũ bị compromise, phối hợp CA revocation và trust/incident policy.

**Chứng thư bị thu hồi:** CA có thể phát CRL hoặc OCSP; hiệu lực phát hiện revocation phụ thuộc cách client kiểm tra (hard-fail/soft-fail, stapling, caching). **Không khẳng định chỉ gọi CA revoke là mọi client ngay lập tức chặn cert**. Với dịch vụ nội bộ mTLS, cần chính sách revoke/allowlist serial hoặc short-lived cert và kiểm tra tại TLS terminator.

### 8.3. Kiểm tra cert mà không lộ private key

Có OpenSSL trên máy test:

```bash
# Kiểm SAN và hiệu lực, không in private key:
openssl x509 -in server.crt -noout -dates -issuer -subject -ext subjectAltName

# Quan sát server thực trình bày certificate/chain:
openssl s_client -connect api.example.test:443 \
  -servername api.example.test -showcerts </dev/null
```

**Cảnh báo:** `s_client -showcerts` hiển thị chain **không tự chứng minh** client Java đã validate SAN/CA/hostname. Test dùng JVM truststore và HTTP client thật là cần thiết; kiểm không bật `trustAll` hoặc disable hostname verifier chỉ để khỏi lỗi certificate.

Không dùng `openssl rsa -in server.key -text` để debug trên terminal công khai: nó có thể in private key vào logs/history. Khi test cert/key match, dùng phương pháp kiểm public key từ certificate và private-key-derived public key trong môi trường bảo vệ, không chia sẻ private key ra ticket.

## 9. Spring Boot SSL bundles: thay cert mà tránh restart khi được hỗ trợ

Spring Boot 3.x hỗ trợ **SSL bundles** cho JKS/PKCS12 hoặc PEM. Với phiên bản Spring Boot hỗ trợ `reload-on-update` và consumer tương thích (theo tài liệu: **Tomcat và Netty web server**), có thể reload certificate/key từ file update. Spring Boot **không tự yêu cầu hoặc gia hạn chứng thư Let's Encrypt**; ACME/Certbot hoặc cơ chế bên ngoài cung cấp file mới.

Ví dụ cho embedded HTTPS Tomcat/Netty, PEM files được operator quản lý:

```yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: file:/run/tls/fullchain.pem
            private-key: file:/run/tls/privkey.pem
server:
  port: 8443
  ssl:
    bundle: webserver
```

Điều kiện:

- `/run/tls/fullchain.pem` là cert+chain hợp lệ; `privkey.pem` tương ứng đúng leaf public key. File phải có filesystem permissions chỉ service cần đọc.
- Đảm bảo **cả hai file** được update nhất quán (atomic deployment/rename hoặc file watcher quiet period) để tránh thời điểm cert mới đi với private key cũ, gây handshake fail.
- Chỉ dùng reload khi **Boot version + web server consumer** hỗ trợ. Một số môi trường dùng TLS ở Ingress/LB, lúc đó thay cert ở LB, không phải `server.ssl.bundle` trong JVM.
- Nếu tải PEM qua classpath đóng gói vào JAR, file watcher thường không có file thay đổi thực như `file:` ngoài container; đối chiếu cách mount secret/volume.
- Sau update, **kiểm handshake thực** ở mọi listener/region, không coi “đã ghi file mới” là đã hoàn tất rotation.
- Certificate renewal phải được điều phối riêng: Boot không quản lý ACME challenge, không tự gia hạn cert khi tới hạn.

**Rollback planned cert rotation:** nếu cert mới bị sai SAN/chain, có thể tạm phục vụ cert cũ **nếu còn hợp lệ và không bị compromise** để sửa. Nếu private key cũ đã bị lộ, rollback về cert/key đó là nguy cơ nghiêm trọng, cần containment thay vì coi availability là ưu tiên duy nhất.

## 10. mTLS: luân chuyển chứng thư client và truststore

Với **mutual TLS**, cả hai phía có thể có chứng thư: server chứng minh danh tính cho client, **client chứng minh danh tính** cho server. Khi client cert sắp hết hạn:

1. Issue client certificate/key mới với intended EKU `clientAuth`, SAN/subject identity và thời hạn theo private PKI.
2. Nếu vẫn cùng CA được tin, server có thể không cần thêm CA mới nhưng vẫn phải cập nhật mapping identity/serial/pinning nếu có.
3. Nếu đổi CA: **deploy new CA trust trước** tại server trước khi client bắt đầu trình bày cert mới; tạm giữ old CA trust có giới hạn trong planned migration.
4. Client rollout cert/key mới qua secret manager/service mesh; test outbound connection với TLS terminator thật và server authorization.
5. Thu hồi/loại client cert cũ; cập nhật CRL/OCSP/serial allowlist theo cơ chế thực thi. Kiểm server **thật sự thực hiện** revocation check, không chỉ có một API “revoke”.
6. Test client không có cert, cert hết hạn, sai CA, wrong SAN/identity, key không khớp, cert cũ revoked và cert của tenant khác.

Spring Security có X.509 pre-authentication cho Servlet thông qua `http.x509(...)`, nhưng khi TLS termination nằm ở proxy thì **không tự tin một header X-Client-Cert từ internet**. Phải bảo vệ chain of trust từ LB/proxy và xóa header client-supplied ở edge; app chỉ tin thông tin được proxy đáng tin chuyển tiếp trong kênh được xác thực.

**Đừng nhầm mTLS certificate identity với OAuth scopes/roles:** X.509 chứng minh rằng peer sở hữu private key liên kết cert được trust; app vẫn cần mapping đúng principal và authorization. Một cert hợp lệ về TLS không tự có `ROLE_ADMIN` hay quyền đọc mọi tenant.

## 11. Incident rotation: khóa bị lộ khác planned rotation

### 11.1. Dấu hiệu sự cố

- Secret/API key hoặc private JWT signing key xuất hiện trong public Git, container image, build logs, issue/ticket, email hoặc package artifact.
- HSM/KMS audit có signing operations bất thường, key export bị nghi, login client không khớp vùng địa lý.
- Bearer token với `kid` cũ hoặc revoked key xuất hiện sau lịch retirement; API key cũ vẫn đang được dùng khi đã thông báo revoke.
- TLS private key hoặc ACME account key được phát hiện trên máy không đáng tin; certificate issuance không được phép.
- Có nhiều JWT ký hợp lệ nhưng claims/issuer/client pattern lạ, nghi signer credential bị chiếm quyền.

### 11.2. Runbook ưu tiên containment

1. **Declare incident & scope:** xác định credential type, tenant/env, accounts/endpoints phụ thuộc và mức tin cậy của logs. Đừng gửi secret lộ qua chat phổ thông để hỏi đồng nghiệp.
2. **Block/revoke compromised credential:** tắt API key cũ, thay signer key và gỡ public compromised key khỏi verify trust khi phù hợp; trigger forced logout/denylist/identity reauthentication nếu cần. Ưu tiên giảm attacker access.
3. **Generate independent replacement** từ nguồn tin cậy trên KMS/HSM khác hoặc được cách ly nếu trust root cũ có nguy cơ lộ; tránh reuse keypair/cert cũ.
4. **Propagate verify-policy changes** tới mọi node, JWKS cache/CDN/edge, service mesh/truststores và downstream consumers. Nếu verifier vẫn cache public K1 bị compromise, attacker có thể tiếp tục tạo token bằng K1 và ký hợp lệ tới khi cache bị xóa/TTL hết.
5. **Test rejection:** một JWT ký K1 sau compromise dù `exp` còn hạn phải bị từ chối nếu policy đã revoke K1; API key revoked không dùng được; mTLS cert compromised không vượt handshake/authorization.
6. **Audit impact:** xác định dữ liệu, requests và sessions bị ảnh hưởng; kiểm API logs theo key ID/correlation mà không log secrets; báo cáo breach/notifications theo chính sách pháp lý.
7. **Root cause và prevention:** cài secret scanning, hạn chế IAM, sửa CI logs, cải thiện network egress, rotation automation và cảnh báo.
8. **Recovery/rollback:** ưu tiên **new trusted material**; đừng khôi phục K1 đã compromise như “rollback nhanh”.

**Chấp nhận trade-off:** retire ngay public K1 có thể làm JWT của người dùng hợp pháp bị 401 và buộc họ nhận token mới. Đó là hậu quả có thể cần thiết khi key đã lộ; giữ K1 để “không gián đoạn” có thể cho phép attacker ký JWT giả. Runbook planned overlap **không áp dụng máy móc** cho sự cố.

### 11.3. Không nhầm loại revoke

| Credential bị lộ | Biện pháp trực tiếp | Điều không tự xảy ra |
| --- | --- | --- |
| JWT signing private key | Dừng signing, loại key khỏi trusted verification, cache invalidation, token revoke/re-auth khi cần | Đổi cert TLS không revoke JWT |
| API key | Server disable/revoke key ID, phát key mới, giám sát abuse | Rotate JWT signer không làm key cũ vô hiệu |
| TLS leaf private key | Issue new cert/key, deploy, revoke old cert, kiểm trust behavior | Logout HttpSession không sửa cert bị lộ |
| ACME account private key | ACME account key rollover/deactivation theo RFC 8555, rà soát unauthorized cert issuance | Đổi leaf cert không tự thay ACME account key |
| Refresh token | Revoke/rotate refresh token family, incident checks | Xóa một HttpSession không revoke refresh token ở IdP |
| Database encryption key | Key lifecycle/rewrap/re-encrypt, đánh giá dữ liệu lộ | Chỉ cấp key mới không mã hóa lại ciphertext cũ |

## 12. Kiểm thử tự động và thủ công: chuỗi before/during/after

Một rotation an toàn phải được kiểm bằng **từng trạng thái**, không chỉ “deploy xong 200”. Dùng isolated fixture và client test, không thử token production trên hệ thống không được phép.

| ID | Khi nào | Thao tác | Kết quả |
| --- | --- | --- | --- |
| J01 | Trước rotation | JWT K1 hợp lệ, đúng iss/aud/exp | Chấp nhận |
| J02 | Chuẩn bị K2 | JWKS có K1+K2, signer vẫn K1 | JWT K1 vẫn chấp nhận |
| J03 | Sau cache propagation | K2 token hợp lệ | Được verify ở mọi region |
| J04 | During overlap | K1 JWT chưa expired + K2 JWT mới | Cả hai được verify |
| J05 | Sau K1 retirement | JWT K1 dù signature toán học đúng | Từ chối theo trust policy mới |
| J06 | Mọi giai đoạn | JWT `kid` không thuộc trusted JWKS | Từ chối |
| J07 | Mọi giai đoạn | Header `jku` trỏ website attacker | Không fetch/untrusted key |
| J08 | Mọi giai đoạn | JWT `alg=none` hoặc algorithm confusion | Từ chối |
| J09 | Mọi giai đoạn | JWT đúng signature nhưng wrong issuer | Từ chối |
| J10 | Mọi giai đoạn | JWT đúng issuer nhưng wrong audience/tenant | Từ chối |
| J11 | Mọi giai đoạn | JWT đã expired | Từ chối |
| J12 | JWKS unreachable | Verifier cache thiếu K2 | Fail closed, không accept unknown token |
| A01 | API key mới phát | A1+A2 đang active | Đúng client được dùng cả hai trong overlap |
| A02 | Trong overlap | Client khác gửi key A2 | Không được nhận owner khác |
| A03 | A1 revoked | A1 request | Unauthorized, không side effect |
| A04 | A1 revoked | A2 request | Vẫn hoạt động theo scope |
| A05 | Expired API key | Dùng key sau expiresAt | Từ chối |
| A06 | Reuse API key ngoài scope | Gọi admin route | Từ chối dù key đúng |
| A07 | Multi-pod revoke | Dùng A1 ở mọi region | Không pod nào còn accept cached revoked key |
| C01 | Trước cert rotation | TLS handshake/SNI/hostname | Pass từ JVM truststore thật |
| C02 | Cert mới deploy | Fullchain + SAN/EKU/expiry + keypair | Pass |
| C03 | Cert sai hostname | Kết nối từ client thật | Fail; không disable hostname verification |
| C04 | Cert hết hạn/CA lạ | Kết nối | Fail |
| C05 | mTLS client cert mới | Same allowed service identity | Pass và authority đúng |
| C06 | mTLS client cert old revoked | Connect | Fail theo revocation policy |
| C07 | Reload TLS | Update cert files | Handshake mới trình bày cert mới |
| I01 | Compromised JWT K1 | Ngay sau retire/invalidate | K1 forged token bị từ chối tại mọi verifier |
| I02 | Compromised API key | Revoke A1 | A1 request bị từ chối ngay, A2 tiếp tục nếu an toàn |
| I03 | Rollback | New key deployment lỗi | Chỉ dùng rollback cũ nếu **không compromise** |

**Ngoài status HTTP:** assert authorization thật, không có DB write/payment nếu auth fail, session identity không bị đổi sai, cache và metrics không chứa raw secret. Test canary multi-region và retry/circuit behavior khi JWKS, KMS hoặc CA endpoint chập chờn.

## 13. Java 17 độc lập: mô phỏng hai-key signing overlap và API-key rollover

Bài lab sau chạy bằng Java 17 **không dùng Spring, JWT, KMS hoặc TLS**. Nó chủ ý thực hiện phép ký/verify thật bằng RSA SHA256 và mô phỏng API key ngẫu nhiên được băm SHA-256 trong store. Mục tiêu: minh họa **public key K1/K2 overlap**, chuyển signer, retire trust và **API key dual acceptance → revoke key cũ**.

**Không áp dụng trực tiếp cho production:** code lưu private RSA keys trong heap thay vì KMS/HSM, không ký JWS/serialize JWT, không kiểm issuer/audience/token expiry, không có database transaction hoặc audit. SHA-256 của **API key ngẫu nhiên 256-bit** trong demo nhằm minh họa lookup; với hệ thống thật cần thiết kế chống enumeration/constant-time, rate limit, secret manager, key ID/owner/scope và cache invalidation. Không in raw keys ra stdout.

Lưu thành `CredentialRotationLab.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.Instant;
import java.util.*;

public final class CredentialRotationLab {

    record SignedPayload(String kid, String body, byte[] signature) {}
    record ClientKey(String owner, Instant expiresAt) {}

    private static final SecureRandom RANDOM = new SecureRandom();

    static String randomSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    static String sha256Hex(String secret) throws GeneralSecurityException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hashed = digest.digest(
                secret.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(hashed);
    }

    static final class SigningKeys {
        private final Map<String, PublicKey> trusted = new HashMap<>();
        private final Map<String, PrivateKey> signing = new HashMap<>();

        void create(String kid) throws GeneralSecurityException {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            KeyPair pair = generator.generateKeyPair();
            signing.put(kid, pair.getPrivate());
            trusted.put(kid, pair.getPublic());
        }

        SignedPayload sign(String kid, String payload)
                throws GeneralSecurityException {
            PrivateKey key = signing.get(kid);
            if (key == null) {
                throw new InvalidKeyException("No active signer for kid");
            }
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(key);
            signer.update(payload.getBytes(StandardCharsets.UTF_8));
            return new SignedPayload(kid, payload, signer.sign());
        }

        boolean verify(SignedPayload token) throws GeneralSecurityException {
            PublicKey trustedKey = trusted.get(token.kid());
            if (trustedKey == null) {
                return false; // kid chọn trong local trusted set
            }
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(trustedKey);
            verifier.update(token.body().getBytes(StandardCharsets.UTF_8));
            return verifier.verify(token.signature());
        }

        void stopSigning(String kid) {
            signing.remove(kid);
        }

        void retirePublic(String kid) {
            trusted.remove(kid);
        }
    }

    static final class ApiKeyStore {
        private final Map<String, ClientKey> byHash = new HashMap<>();

        String issue(String owner, Instant expiresAt)
                throws GeneralSecurityException {
            String value = randomSecret();
            byHash.put(sha256Hex(value), new ClientKey(owner, expiresAt));
            return value; // trả secret cho client đúng một lần
        }

        boolean accepts(String value, String expectedOwner, Instant now)
                throws GeneralSecurityException {
            ClientKey found = byHash.get(sha256Hex(value));
            return found != null
                    && found.owner().equals(expectedOwner)
                    && now.isBefore(found.expiresAt());
        }

        void revoke(String value) throws GeneralSecurityException {
            byHash.remove(sha256Hex(value));
        }
    }

    public static void main(String[] args) throws Exception {
        SigningKeys jwk = new SigningKeys();
        jwk.create("k1");
        SignedPayload old = jwk.sign("k1", "user=alice");

        jwk.create("k2");
        SignedPayload fresh = jwk.sign("k2", "user=alice");

        System.out.println("oldDuringOverlap=" + jwk.verify(old));
        System.out.println("newDuringOverlap=" + jwk.verify(fresh));

        jwk.stopSigning("k1");
        System.out.println("oldVerifiableAfterSwitch=" + jwk.verify(old));

        jwk.retirePublic("k1");
        System.out.println("oldDeniedAfterRetire=" + !jwk.verify(old));
        System.out.println("newStillWorks=" + jwk.verify(fresh));

        SignedPayload tampered = new SignedPayload(
                "k2", "user=bob", fresh.signature());
        System.out.println("tamperedRejected=" + !jwk.verify(tampered));

        ApiKeyStore api = new ApiKeyStore();
        Instant now = Instant.parse("2026-11-06T00:00:00Z");

        String a1 = api.issue("service-a", now.plusSeconds(3600));
        String a2 = api.issue("service-a", now.plusSeconds(7200));

        System.out.println("oldKeyInitiallyWorks=" +
                api.accepts(a1, "service-a", now));
        System.out.println("newKeyWorks=" +
                api.accepts(a2, "service-a", now));
        System.out.println("wrongClientDenied=" +
                !api.accepts(a2, "service-b", now));

        api.revoke(a1);
        System.out.println("oldKeyRevoked=" +
                !api.accepts(a1, "service-a", now));
        System.out.println("newKeyStillWorks=" +
                api.accepts(a2, "service-a", now));
        System.out.println("keyExpired=" +
                !api.accepts(a2, "service-a", now.plusSeconds(7201)));
    }
}
```

Chạy:

```bash
javac CredentialRotationLab.java
java CredentialRotationLab
```

**Stdout chính xác**, không phụ thuộc giá trị RSA/API key được sinh ngẫu nhiên:

```text
oldDuringOverlap=true
newDuringOverlap=true
oldVerifiableAfterSwitch=true
oldDeniedAfterRetire=true
newStillWorks=true
tamperedRejected=true
oldKeyInitiallyWorks=true
newKeyWorks=true
wrongClientDenied=true
oldKeyRevoked=true
newKeyStillWorks=true
keyExpired=true
```

Giải thích:

- Cùng lúc K1/K2 public được tin, cả chữ ký cũ và mới đều verify.
- Ngừng **ký** bằng K1 không làm mất khả năng **verify** chữ ký K1 trước khi retire public K1.
- Sau khi retire public K1, signature toán học K1 vẫn đúng nhưng **hệ thống không còn tin key đó**.
- Payload bị sửa từ Alice sang Bob mà không ký lại phải fail signature.
- API key A1/A2 cùng active trong overlap; revoke A1 không làm A2 hỏng; key hết hạn hoặc owner sai bị từ chối.

**Ranh giới:** `SigningKeys` là kho key local trong RAM, không có JWKS endpoint/cache hay JWT expiration; `ApiKeyStore` không có distributed cache hoặc transaction. Trong production, key lifecycle chạy qua KMS/secret manager, key ID, policy scoped OAuth/API và các test integration thực.

## 14. Giám sát và SLO: đo cái gì sau rotation?

Vận hành an toàn cần nhìn **đúng nơi dùng key** mà không rò secret:

| Metric/Signal | Cách dùng | Lưu ý |
| --- | --- | --- |
| JWT issued_by_kid (K1/K2) | Đảm bảo signer thực sự đã switch | Chỉ log kid metadata, không JWT |
| JWT verification success/fail theo kid/issuer/region | Phát hiện verifier stale JWKS hoặc key sai | Không log raw Authorization |
| JWKS fetch/cache hit/errors/latency | Biết cache propagation và dependency failure | Phân biệt 401 do network với 403 do thiếu scope |
| API key usage theo key ID, owner và version | Quyết định ngày revoke old A1 | Không log secret/hash như metric label có cardinality cao |
| API key revoked/expired attempts | Phát hiện client quên đổi hoặc abuse | Ẩn danh tính nhạy cảm theo policy audit |
| TLS cert remaining lifetime | Cảnh báo trước expiry | Đo **cert phục vụ thực tế** ở mọi listener/SNI, không chỉ file |
| TLS handshake failure theo trust reason | Sai SAN, CA, chain, expiry hoặc key mismatch | Không disable verify để “giảm lỗi” |
| mTLS principal mapping failures | Phát hiện cert mới chưa được policy tin | So account/service identity |
| Secret-manager/KMS signing errors | HSM permission, throttling, outages | Không fail-open hoặc tự tạo key local |
| Rotation change audit | Chứng minh hoàn thành step, rollback, retire | Ai/bao giờ/phiên bản, không raw secret |

### Alert ngắn gọn

- Key cũ vẫn **được sử dụng** sau switch deadline hoặc secret đã revoked vẫn được chấp nhận.
- Tỷ lệ 401/invalid_token tăng mạnh sau JWT signer switch; unknown-kid theo region/pod.
- Certificate thật ở endpoint public còn dưới ngưỡng cảnh báo và automation renewal thất bại.
- TLS handshake failure hoặc mTLS auth failure tăng sau deployment.
- JWKS/KMS/secret manager unreachable kéo dài; không biết liệu cache stale sẽ hết hạn khi nào.
- API key tồn tại lâu mà không có owner, mục đích hoặc lịch rotation.

**Đừng đo bằng cách log raw token/cert private key.** Một giá trị `kid` hay cert serial có thể dùng như metadata nếu tổ chức cho phép; đưa chúng vào metrics với giới hạn cardinality và kiểm quyền truy cập dashboard.

## 15. Troubleshooting: triệu chứng → lớp hỏng

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và sửa |
| --- | --- | --- |
| JWT K2 bắt đầu trả 401 | JWKS chưa publish/TTL cache tại verifier | Kiểm JWKS/issuer, kid, cache refresh và rollout order |
| K1 token còn hạn bị 401 | Gỡ K1 quá sớm, clock skew/TTL lớn hơn dự kiến | Đọc last-issued time và max token lifetime, khôi phục K1 **nếu không compromise** |
| JWT alg khác config bị deny | Verifier chỉ tin RS256 đúng policy | Không nới algorithm không kiểm soát |
| JWT ký đúng nhưng wrong aud | Token cấp cho API khác | Sửa issuer/client/resource audience, không bỏ validation |
| JWKS chứa private `d` | Publish key material nhầm | Xem sự cố compromise, gỡ ngay và rotate |
| Verifier tải JWKS từ header `jku` | Key injection/SSRF vulnerability | Pin trust URI theo issuer, chặn remote URL trong token |
| API key mới không dùng được | Client chưa deploy secret, cache key store stale | Xác minh key ID/owner/expiry, cache invalidation |
| Key cũ vẫn được chấp nhận sau revoke | Regional cache stale, duplicate credential, revocation chưa sync | Đánh giá consistency/quorum, revoke ở mọi node |
| API key đúng nhưng 403 | Scope/tenant/owner không đủ | Kiểm authorization, không ép login lại |
| Client gửi key qua URL | Thao tác debug sai, leak logs/history | Chuyển Authorization/custom header, scrub logs |
| Cert được cấp nhưng handshake fail | SAN sai, private key không khớp, fullchain thiếu | Kiểm cert+key và server SNI thực |
| Cert mới có nhưng vẫn thấy cert cũ | Reload chưa bật/consumer unsupported/Ingress còn cũ | Kiểm TLS terminator, reload support, listener deployment |
| TLS cert chưa hết mà client báo unknown_ca | Truststore/CA/intermediate chưa cập nhật | Rollout trust đúng thứ tự, không trust-all |
| mTLS client cert mới không có quyền | Principal mapper/pinning/serial allowlist chưa đổi | Check identity mapping + authorization |
| X.509 old revoked nhưng vẫn handshake | Client/server chưa kiểm CRL/OCSP/serial policy | Rà revocation enforcement; không mặc định mọi client đều chặn |
| Đổi cert vẫn không revoke JWT | TLS/JWT là hai trust domains riêng | Xác định cần JWT issuer signing key revoke hay không |
| Private key KMS bị lộ mà vẫn muốn overlap | Áp sai runbook planned rotation | Containment và revoke khẩn cấp thay vì giữ trust |
| Key mã hóa cũ bị xóa, dữ liệu không giải mã được | Chưa rewrap/re-encrypt/backups | Khôi phục từ key management recovery plan, lập migration |
| Bật Boot SSL bundle reload nhưng ACME không renew | Boot chỉ reload file, không xin certificate | Cấu hình Certbot/ACME client/CA automation riêng |
| Chỉ thấy 302 trong login test | Frontend redirect, không chứng minh key validity | Assert exact principal, token verification và resource access |
| Spring Resource Server mới không có aud policy | Custom JwtDecoder override Boot validation | Thêm validator đúng, negative-test wrong-audience |

## 16. Checklist và runbook giao ca

### Trước change

- [ ] Đã xác định **đúng loại** credential (JWT signing/public key, HMAC, API key, TLS/mTLS cert, encryption KEK/DEK), owner, tenant và environment.
- [ ] Có inventory toàn bộ consumers/signer/verifier, key store, Secret Manager và endpoints/SNI cần thay.
- [ ] Có max token TTL + clock skew, JWK/cache propagation delay, certificate expiry và API key client rollout timeline.
- [ ] New key/secret tạo từ CSPRNG/KMS/HSM phù hợp, không đưa vào repo/log/CI stdout.
- [ ] Có kế hoạch rollback planned **chỉ nếu old credential chưa bị compromise**; có runbook emergency riêng.
- [ ] Đã định nghĩa quyền phát key, revoke, audit và approval.

### Trong change

- [ ] Với JWT: publish public K2 **trước khi** ký JWT K2; giữ public K1 overlap theo TTL, không đưa private K1 vào JWKS.
- [ ] Với API key: phát A2 an toàn, canary client, quan sát usage A1, revoke A1 sau deadline.
- [ ] Với TLS/mTLS: cert+key match, SAN/EKU/chain chính xác, truststore cập nhật trước nếu đổi CA, reload đúng terminator.
- [ ] Không tắt xác minh chữ ký JWT, hostname verification hoặc TLS trust để “đỡ 401/SSL lỗi”.
- [ ] Canary theo issuer, audience, tenant, region, client, service-to-service workloads.
- [ ] KMS/JWKS/DB outage có fail-closed policy và alert; không tự cấp Authentication khi thiếu verify.

### Sau change

- [ ] JWT mới ký K2 và được mọi verifier nhận; JWT K1 bị retire đúng kỳ; unknown kid/alg/wrong aud fail.
- [ ] API key A1 đã bị revoke, A2 scope/owner chính xác, cache/pods không còn accept A1.
- [ ] TLS endpoint thật trình bày cert mới, kiểm hostname/chain/expiry bằng client JVM; cert cũ bị xử lý theo PKI policy.
- [ ] mTLS cert mới map đúng principal; cert cũ hết quyền khi policy yêu cầu.
- [ ] Dữ liệu mã hóa cũ vẫn đọc được nếu migration chưa xong; key backup/recovery được quản lý.
- [ ] Audit có change ID, owner, time, secret version, trạng thái completed, kết quả negative tests, dashboard và lịch rotation kế tiếp.
- [ ] Tách kết quả “đã rotate JWT key” khỏi “đã revoke toàn bộ JWT” và “đã rotate cert” khỏi “đã thu hồi cert cũ tại mọi client”.

**Nguyên tắc kết luận:** Rotation an toàn gồm **publish trust mới → switch producer/client → quan sát → retire trust cũ** trong thay đổi có kế hoạch; còn khi secret bị lộ, phải ưu tiên **containment và revoke**. JWT signing key, API key, TLS/mTLS certificate và encryption key có đối tượng tin cậy và cơ chế thu hồi khác nhau. Chỉ thay một giá trị cấu hình rồi restart service không chứng minh rằng mọi token/certificate cũ đã hết hiệu lực.

### Tài liệu gốc và tham khảo

- [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth2 Resource Server Authentication](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Boot — SSL Bundles and Reloading SSL bundles](https://docs.spring.io/spring-boot/reference/features/ssl.html)
- [Spring Boot 3.4 — SSL Bundles](https://docs.spring.io/spring-boot/3.4/reference/features/ssl.html)
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP — Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 5280 — X.509 PKI Certificate Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 8555 — Automatic Certificate Management Environment (ACME)](https://www.rfc-editor.org/rfc/rfc8555)
- [RFC 8705 — OAuth 2.0 Mutual TLS](https://www.rfc-editor.org/rfc/rfc8705)
