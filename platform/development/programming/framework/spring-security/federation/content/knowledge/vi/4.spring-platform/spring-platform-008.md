# Tách cấu hình theo môi trường và quản lý thông tin bí mật trong Spring Security Federation

## 1. Mục tiêu và phạm vi

Một ứng dụng Spring Boot làm **Relying Party (RP)** của OpenID Connect (OIDC) hoặc **Service Provider (SP)** của SAML 2.0 phải biết kết nối tới đúng máy chủ định danh, nhận callback ở đúng địa chỉ công khai, xác thực thông điệp bằng đúng khóa tin cậy và giữ bí mật những credential có khả năng cấp quyền hoặc giả mạo danh tính. Các giá trị này thường khác nhau giữa `local`, `dev`, `staging` và `prod`.

Nếu sao chép một cấu hình sang mọi môi trường, các lỗi có thể xuất hiện: localhost redirect tới client production, ứng dụng test chấp nhận IdP production, client secret bị commit vào Git, SP ký SAML bằng private key dùng chung giữa các môi trường, hoặc key đã xoay vòng nhưng JVM chưa tải lại.

**Mục tiêu:** xây dựng một cách tổ chức cấu hình có thể triển khai lặp lại, bảo mật và kiểm thử được; phân biệt rõ cấu hình môi trường, secret và dữ liệu tin cậy; dùng đúng Spring Profiles, externalized configuration, Secret Manager/Kubernetes Secret, OIDC/SAML registration; vận hành và xoay vòng khóa không làm giảm xác thực.

Bài học sử dụng Spring Boot 3.x / Spring Security 6.x làm mặt bằng ví dụ (các tên thuộc tính cần được đối chiếu với phiên bản thực tế của dự án). Các đường dẫn URL, tên miền và ID trong ví dụ là **giả định**, không phải dịch vụ hoạt động sẵn.

## 2. Phân biệt cấu hình thường, thông tin nhạy cảm và trust material

Không phải mọi giá trị liên quan SSO đều là bí mật:

| Loại | Ví dụ trong federation | Có thể lưu trong Git? | Bảo vệ quan trọng |
| --- | --- | --- | --- |
| Cấu hình không nhạy cảm, phụ thuộc môi trường | Base URL public, issuer URI, redirect URI, SAML ACS URL, timeout, tên registration | Thường có, tùy chính sách nội bộ | Đúng miền, đúng tenant, nhất quán với IdP/OP |
| Định danh công khai | OAuth2/OIDC `client_id`, SAML SP `entityID`, X.509 certificate công khai, JWKS public key | Có thể, nếu không chứa thông tin nội bộ cần hạn chế công bố | Tính đúng đắn và nguồn tin cậy |
| **Bí mật ứng dụng** | OIDC `client_secret`, private key SAML signing/decryption, private key `private_key_jwt`, mật khẩu kho khóa | **Không** | Kiểm soát quyền đọc, mã hóa lưu trữ, rotation, tránh log |
| Dữ liệu đăng nhập theo phiên | Authorization code, ID/Access/Refresh Token, SAML Response/Assertion, cookie phiên | **Không** | Thời hạn ngắn nhất hợp lý, hạn chế log/cache, kiểm tra replay và audience |
| Trust configuration | OIDC `issuer-uri`, bộ key verify IdP, metadata SAML, thuật toán được phép | Phần public có thể | **Toàn vẹn cấu hình và nguồn gốc**: thay đổi sai có thể chuyển lòng tin sang IdP giả |

**Một giá trị không bí mật vẫn có thể tối quan trọng về bảo mật.** Ví dụ, `issuer-uri` công khai nhưng bị thay từ IdP doanh nghiệp sang một IdP do kẻ tấn công kiểm soát có thể làm ứng dụng tin sai nguồn token. Cũng vậy, `client_id` thường công khai; chỉ `client_secret` mới cần giữ bí mật, nhưng `client_id` sai môi trường có thể làm authentication fail hoặc trộn luồng đăng nhập.

### Phân vùng trust theo môi trường

Nên đăng ký **OIDC client và SAML SP riêng cho từng môi trường** trong IdP/OP, cùng redirect/ACS/entityID đúng host của môi trường đó. Đặc biệt:

- `dev` dùng client ID/credential và issuer của IdP dev, không có quyền xác thực thay cho production.
- `staging` có đăng ký riêng, có thể dùng IdP sandbox với bộ người dùng kiểm thử. Chỉ dùng IdP production cho staging khi có quyết định rõ và biện pháp kiểm soát phù hợp.
- `prod` chỉ nhận cấu hình IdP/OP và trust anchor đã được phê duyệt.
- `test` ưu tiên mock OIDC provider/test certificate hoặc môi trường IdP dành cho test; không để automated test đọc secret production.

Một **Spring profile** chỉ là cơ chế chọn cấu hình và bean; nó **không tự tạo ranh giới bảo mật**. Quyền truy cập secret store, danh tính workload, mạng, môi trường IdP và quyền triển khai mới quyết định giới hạn sự cố khi một môi trường bị chiếm quyền.

## 3. Cơ chế externalized configuration của Spring Boot

Spring Boot lấy thuộc tính qua Spring `Environment` từ nhiều nguồn: `application.yml`/`application.properties`, file theo profile, external config, biến môi trường, system properties, tham số dòng lệnh, và các nguồn cấu hình bổ sung. Nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị từ nguồn ưu tiên thấp hơn theo quy tắc của phiên bản Spring Boot.

Các quy tắc thực hành quan trọng:

1. `application.yml` chứa **giá trị mặc định dùng chung và cấu trúc cấu hình**, không lưu secret thực.
2. `application-dev.yml` và `application-prod.yml` chứa **giá trị khác biệt, không nhạy cảm**; profile đang hoạt động quyết định file nào được nạp.
3. Secret được cấp từ bên ngoài lúc chạy: biến môi trường, tệp secret mount read-only, hoặc nhà cung cấp secret manager tích hợp qua cơ chế được hỗ trợ.
4. Tham số dòng lệnh/biến môi trường có thể override config file; bảo vệ quyền sửa deployment và CI/CD vì sửa một thuộc tính trust như `issuer-uri` cũng có thể nguy hiểm.
5. Đặt `spring.profiles.active` ở **biến môi trường, tham số khởi chạy hoặc cấu hình không đặc thù profile**. Không đặt nó trong chính `application-prod.yml` hoặc tài liệu YAML đã kích hoạt bằng `spring.config.activate.on-profile`.
6. Nếu không profile nào được kích hoạt, Spring Boot có profile `default`. Đừng mặc nhiên xem trạng thái đó là dev/prod; hãy quy định profile bắt buộc rõ ràng trong manifest deployment.

Có thể khởi chạy bằng:

```bash
# Ví dụ shell POSIX; credential được hệ thống triển khai cấp riêng.
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun

# Ví dụ artifact đã build, trên máy chủ production.
SPRING_PROFILES_ACTIVE=prod java -jar app.jar
```

Lệnh thứ hai chỉ minh họa cách chọn profile; ứng dụng thực tế còn cần cung cấp OIDC/SAML credentials qua nguồn an toàn. Không đưa `--spring.security.oauth2.client.registration.corp.client-secret=...` vào command line: tham số có thể xuất hiện trong log, lịch sử shell hoặc thông tin tiến trình.

### 3.1. Chọn giữa profile và property override

- Dùng **profile** khi một nhóm setting rõ ràng thuộc về môi trường (issuer dev/prod, public callback host, policy log, cấu hình proxy).
- Dùng **biến môi trường** khi từng lần triển khai cung cấp một giá trị biến đổi hoặc bí mật (client ID, client secret, credential location).
- Dùng **Secret Manager / mounted secret** cho private key, client secret, mTLS credential, các dữ liệu có lifecycle và quyền truy cập riêng.
- Dùng `@Profile` để chọn bean implementation **chỉ khi hành vi thực sự khác**; không tạo nhiều `SecurityFilterChain` cho dev/prod nếu cùng một cơ chế đăng nhập chỉ khác thuộc tính.

Không đặt logic dạng `if (profile.equals("prod"))` rải rác trong code để chọn secret hoặc issuer. Cấu hình được nạp trước, bind theo quy tắc ổn định, kiểm tra hợp lệ, rồi dùng một triển khai chung sẽ đơn giản và dễ audit hơn.

## 4. Một bố cục cấu hình OIDC theo môi trường

Giả sử ứng dụng backend Spring Boot là OIDC RP với registration ID `corp`, dùng authorization code và phiên server-side. Có thể tổ chức:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-staging.yml
  application-prod.yml

# Không tồn tại trong source control:
# OIDC_CLIENT_SECRET, SAML private key, refresh token, secret store dump
```

### 4.1. Cấu hình chung – `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

Giải thích:

- `corp` là `registrationId` nhất quán trong route khởi tạo đăng nhập và callback.
- `client-id` thường không bí mật, nhưng được đưa từ deployment để mỗi môi trường nhận giá trị đúng.
- `client-secret` được giải bằng placeholder của Spring từ biến môi trường **có tên chính xác** `OIDC_CLIENT_SECRET`; không lưu giá trị thực trong YAML.
- `redirect-uri` có các biến mẫu được Spring Security hỗ trợ. Public base URL phải được tính đúng khi ứng dụng chạy sau reverse proxy.
- Chỉ dùng `openid` khi mục tiêu là OIDC login; có thể thêm scope theo yêu cầu tối thiểu của ứng dụng. Không yêu cầu scope dư hoặc refresh token nếu không cần.

**Không đặt giá trị mặc định giả cho secret**, ví dụ `${OIDC_CLIENT_SECRET:change-me}`: hệ thống có thể khởi động với một credential sai/không được quản lý mà người vận hành không nhận ra. Cần kiểm tra thiếu secret trước khi mở lưu lượng production.

### 4.2. Cấu hình phát triển – `application-dev.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: "https://idp.dev.example.test/realms/team"

server:
  port: 8080
```

`issuer-uri` phải khớp giá trị `iss` trong ID Token do OP dev phát hành và metadata discovery của OP. URL `.test` chỉ minh họa cấu hình; người học phải thay bằng nhà cung cấp thực trong môi trường riêng.

Trong console quản lý IdP dev, đăng ký redirect URI phù hợp, ví dụ `http://localhost:8080/login/oauth2/code/corp` nếu chính sách của OP cho phép localhost ở môi trường phát triển. **Không** thêm redirect localhost vào registration production. Dù client ID không phải secret, vẫn cấp riêng `OIDC_CLIENT_ID` và `OIDC_CLIENT_SECRET` cho dev.

### 4.3. Cấu hình production – `application-prod.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: "https://login.example.com/realms/company"

server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

Trong ví dụ, ingress/reverse proxy nhận HTTPS trên public domain và truyền request cho Spring Boot. `forward-headers-strategy: framework` giúp ứng dụng hiểu scheme/host gốc khi proxy gửi header chuẩn, **chỉ an toàn khi ingress xóa/ghi đè các header `Forwarded`/`X-Forwarded-*` do client Internet cung cấp** và backend không bị truy cập trực tiếp ngoài ranh giới tin cậy.

OP production cần registration riêng:

- Client ID/secret production, được phân phối cho đúng workload RP production.
- Redirect URI công khai chính xác, ví dụ `https://app.example.com/login/oauth2/code/corp`.
- Issuer và chứng chỉ HTTPS của OP production đúng tenant, không dùng đường dẫn của OP dev.
- Chính sách cookie phiên, CSRF, timeout và HTTPS phù hợp, không chỉ dựa vào hai thuộc tính cookie trên.

Khi ứng dụng dùng nhiều replica, mọi instance phải được cấu hình cùng một bộ client credentials và session strategy; nếu chia sẻ session, phải bảo vệ session store riêng. Không tạo client secret mới trên từng pod nếu OP chỉ đăng ký một credential.

### 4.4. Môi trường staging

`application-staging.yml` dùng cấu trúc tương tự production nhưng chọn issuer/callback và registration của staging. Không cần tạo một bản sao lớn của `application.yml`. Chỉ override những thuộc tính khác: issuer, public host, session cookie hoặc timeout nếu có yêu cầu riêng.

**Điểm cần QA:** Với mọi môi trường, xác định bộ 4: `registrationId`, `clientId`, `issuerUri`, `redirectUri`. Đăng nhập chỉ hoạt động đúng khi cấu hình trong RP và đăng ký của OP thống nhất, và mọi endpoint do RP tải về đều thuộc OP đã tin cậy.

## 5. Secret được đưa vào lúc chạy như thế nào?

### 5.1. Biến môi trường

Khi dùng placeholder `${OIDC_CLIENT_SECRET}`, một biến môi trường có tên `OIDC_CLIENT_SECRET` được hệ thống triển khai cấp vào process. Spring Boot đọc giá trị từ `Environment` lúc bind OAuth2 client registration. Không cần viết code gọi `System.getenv` để tự gắn vào builder.

Tuy nhiên, biến môi trường **không phải kho bí mật tuyệt đối**: tùy hệ điều hành, quyền container, công cụ chẩn đoán hoặc log vận hành, giá trị có thể lộ qua crash dump, diagnostic endpoint, lệnh kiểm tra môi trường hoặc quyền đọc process. Vì vậy:

- Không đặt secret trong `Dockerfile ENV`, `ARG` build, image layer, file `.env` được commit hoặc pipeline log.
- Không viết `printenv`, `env`, `set`, `echo $OIDC_CLIENT_SECRET` trong log CI để “kiểm tra” secret.
- Không in nguyên `Environment`, đối tượng `ClientRegistration`, auth headers hay request tới token endpoint vào log.
- Giới hạn ai được thay giá trị secret ở deployment và ai có thể đọc process/container.
- Ưu tiên secret injection được kiểm soát thay vì lưu plaintext trong repository hoặc manifest public.

**Kiểm tra an toàn** là kiểm tra biến **có tồn tại** và endpoint có liên kết đúng, không in giá trị. Ví dụ vận hành có thể báo `OIDC_CLIENT_SECRET configured: yes`, nhưng ngay cả trạng thái này cũng chỉ nên xuất hiện trong log nội bộ an toàn.

### 5.2. Tệp secret được mount và `configtree:`

Spring Boot có thể tải một thư mục nơi **tên file trở thành property key**, nội dung file trở thành property value. Cách này phù hợp với Docker/Kubernetes volumes hoặc secret agent có khả năng mount dữ liệu read-only.

Trong lựa chọn sử dụng **config tree trực tiếp**, `application-prod.yml` có thể khai báo:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/oidc/"
```

Thư mục phải tồn tại ở production vì không dùng `optional:`. Nếu ứng dụng cần chạy không có mount ở dev, chỉ khai báo import trong profile prod, hoặc dev dùng cách khác. Trên máy chủ ví dụ, có hai file:

```text
/run/secrets/oidc/
  spring.security.oauth2.client.registration.corp.client-id
  spring.security.oauth2.client.registration.corp.client-secret
```

Mỗi file chứa **đúng một giá trị**; chẳng hạn file thứ hai chứa client secret được cấp từ secret store. Spring Boot có thể ánh xạ tên file có dấu chấm thành property tương ứng. Khi dùng **phương án này**, các thuộc tính `client-id` và `client-secret` ở `application.yml` có thể được bỏ đi, để file secret cung cấp trực tiếp các property chuẩn. Tránh duy trì hai nguồn giá trị không rõ ưu tiên.

Ví dụ mount dạng Kubernetes Deployment *rút gọn*; Secret `rp-oidc-prod` phải được tạo và cấp quyền từ hạ tầng quản lý secret trước:

```yaml
spec:
  template:
    spec:
      containers:
        - name: rp
          image: registry.example.test/federation-rp:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          volumeMounts:
            - name: oidc-credentials
              mountPath: /run/secrets/oidc
              readOnly: true
      volumes:
        - name: oidc-credentials
          secret:
            secretName: rp-oidc-prod
```

Đây là phần `spec` của manifest Deployment, không phải Deployment đầy đủ (thiếu `apiVersion`, `kind`, `metadata`, `selector`, v.v.). Hai key trong Kubernetes Secret cần trùng hai tên file mong muốn. Kubernetes Secret có thể được lưu dưới dạng Base64 trong manifest: **Base64 là encoding, không phải mã hóa an toàn**. Cần RBAC, giới hạn quyền `get/list/watch`, kiểm soát etcd encryption-at-rest và quyền đọc volume.

Dùng file mount có lợi cho các credential dài, private key PEM và tránh đưa secret vào process environment, nhưng **file vẫn ở dạng có thể đọc trong container bởi tiến trình có quyền**. Quyền filesystem, service account, container isolation và audit của secret provider vẫn rất quan trọng.

### 5.3. Secret Manager ngoài ứng dụng

Các hệ thống như HashiCorp Vault hoặc dịch vụ quản lý secret của nhà cung cấp đám mây có thể cấp credential qua một trong các mô hình:

1. **Secret injection trước startup:** init container/agent hoặc orchestrator lấy secret bằng workload identity rồi cấp qua mount/env.
2. **Spring ConfigData integration hoặc extension chính thức:** ứng dụng tải secret khi khởi tạo `Environment` bằng thư viện tích hợp phù hợp phiên bản.
3. **Runtime API client:** ứng dụng gọi secret manager có xác thực và cache/refresh chủ động nếu thật sự cần rotation động.

Hãy chọn **một nguồn sở hữu chính** cho mỗi secret, ghi rõ ai cập nhật, ứng dụng nhận secret ở thời điểm nào và cách kiểm tra đổi khóa. Không bật các thư viện tích hợp chỉ vì có tên “secret manager” nếu dự án không cần refresh động; đường truyền, quyền, token của workload và lỗi fallback phải được thiết kế rõ.

**Không lưu credential dùng để đăng nhập Secret Manager lại trong Git.** Dùng workload identity, service account hoặc một cơ chế phát hành credential ngắn hạn do nền tảng quản lý.

## 6. SAML 2.0: tách metadata, signing key và decryption key theo môi trường

SAML có nhiều loại giá trị liên quan trust. Với Spring Security Servlet, cấu hình `RelyingPartyRegistration` kết hợp dữ liệu của SP và IdP:

- **IdP metadata / entity ID / SingleSignOnService URL:** xác định IdP mà SP tin cậy và endpoint gửi AuthnRequest. Đó là trust configuration; URL/certificate public không phải secret nhưng phải lấy từ nguồn đáng tin.
- **IdP verification certificate:** public key để SP xác minh chữ ký `SAMLResponse`/`Assertion`; cần hỗ trợ rotation certificate.
- **SP signing private key + certificate:** SP ký `AuthnRequest`/logout message khi profile và đối tác yêu cầu; private key là secret.
- **SP decryption private key + certificate:** SP giải mã `EncryptedAssertion` khi IdP mã hóa cho SP; private key là secret.
- **SP entity ID + Assertion Consumer Service (ACS) URL:** thường khác giữa dev/prod và phải được IdP đăng ký đúng.

Ví dụ cấu hình **minh họa** dưới `application-prod.yml` nếu tổ chức cấp file credential qua filesystem:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-saml:
            entity-id: "https://app.example.com/saml2/service-provider-metadata/corp-saml"
            acs:
              location: "https://app.example.com/login/saml2/sso/corp-saml"
            assertingparty:
              metadata-uri: "https://idp.example.com/metadata"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/etc/saml/sp-signing.crt"
            decryption:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-decryption.key"
                  certificate-location: "file:/etc/saml/sp-decryption.crt"
```

Cấu hình này chỉ dùng được nếu đối tác SAML đã được thiết lập tương ứng, IdP có metadata đáng tin cậy và các file thực sự tồn tại. Khi IdP **không** yêu cầu SP ký AuthnRequest hoặc không gửi EncryptedAssertion, có thể không cần các credential tương ứng; tránh thêm private key nếu không có yêu cầu thực tế. Với một số release Spring Security/Spring Boot, tên property và cách khai báo `acs` cần đối chiếu với phiên bản dependency đang sử dụng; một lựa chọn là xây dựng `RelyingPartyRegistration` bằng Java config và bind các path từ external configuration.

**Đừng đổi private key của SP chỉ bằng cách thay certificate công khai.** IdP phải nhận certificate public mới ở đúng thời điểm; bản SP production phải có private key khớp, và mọi đối tác cần thống nhất giai đoạn overlap nếu hỗ trợ. Signing key và decryption key có thể có lịch rotation khác nhau; private key tuyệt đối không lưu trong `classpath` của JAR được phát hành.

### Tại sao không cho mọi môi trường dùng chung SAML key?

Nếu dev bị truy cập trái phép, private key ký SP của dev có thể bị sử dụng để ký request trong phạm vi trust của IdP dev. Nếu cùng key ấy cũng được tin ở production, phạm vi hậu quả tăng lên. Tương tự, private decryption key dùng chung có thể làm lộ assertion mà nhiều môi trường nhận được. Do đó tách keypair, IdP trust metadata, SP entity ID và ACS theo môi trường; không sao chép `.p12` production cho laptop để “test nhanh”.

Một chứng chỉ IdP verification có thể công khai, nhưng **quy trình thay certificate này** phải được kiểm soát vì thay key tin cậy sai có thể khiến SP chấp nhận chữ ký của bên ngoài.

## 7. Kiểm tra cấu hình fail-fast và không làm lộ secret

Các lỗi cần phát hiện **trước khi nhận traffic**:

- Profile hiện hành không hợp lệ, chẳng hạn production workload chạy profile dev.
- Thiếu client ID/secret hoặc URI issuer, sai URL, sai protocol hoặc không khớp metadata discovery.
- Token endpoint/JWKS endpoint không truy cập được; lỗi DNS/TLS/trust store.
- OAuth2 redirect URI/registration không được IdP cho phép.
- SAML IdP metadata không đọc được, SP entity ID/ACS không khớp IdP, thiếu key PEM/certificate hoặc key không ghép cặp.
- Bật decryption nhưng không có credential giải mã, hoặc không tin certificate verify của IdP.
- Có cấu hình local test cho phép bypass authentication còn tồn tại trong production.

Đối với property tùy chỉnh, Spring Boot có `@ConfigurationProperties` và Bean Validation để ràng buộc `@NotBlank`, `@NotNull`, định dạng URL, v.v. Ví dụ một lớp **dùng trong ứng dụng Spring Boot**, không phải chương trình Java SE chạy độc lập:

```java
package demo.federation.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.sso")
public record SsoProperties(
        @NotBlank String expectedIssuer,
        @NotBlank String publicBaseUrl
) { }
```

Đăng ký record bằng `@ConfigurationPropertiesScan` trên class `@SpringBootApplication` hoặc `@EnableConfigurationProperties(SsoProperties.class)` trong configuration; thêm `spring-boot-starter-validation` cho môi trường Boot 3.x. Nếu property `app.sso.expected-issuer` hay `app.sso.public-base-url` không được cung cấp hợp lệ, binding validation có thể làm startup thất bại với tên thuộc tính tương ứng.

**Cần phân biệt rõ:** `SsoProperties` là ví dụ về **cấu hình tùy chỉnh**, không tự động thay thế `spring.security.oauth2.client...`. Nếu không có Java code tiêu thụ chúng để đối chiếu registration, chúng chỉ là dữ liệu đã được validate. Đừng tạo một “nguồn sự thật thứ hai” cho issuer; lý tưởng là bind một cấu hình duy nhất rồi xây đăng ký hoặc kiểm tra cross-property nhất quán.

Nếu thêm kiểm tra startup, thông báo lỗi nên là: `Missing required secret for OIDC registration 'corp'` hoặc `Unexpected OIDC issuer for profile 'prod'`; không đưa secret/token/PEM hoặc full request body vào exception. Kiểm tra token đúng issuer/audience/chữ ký vẫn thuộc trách nhiệm thư viện authentication; validation của configuration không thay thế kiểm tra giao thức.

## 8. Thứ tự ưu tiên và những bất ngờ khi override

Giả sử `application-prod.yml` khai báo:

```yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corp:
            issuer-uri: "https://login.example.com/realms/company"
```

Nếu deployment đồng thời đặt biến môi trường:

```text
SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_CORP_ISSUERURI=https://other.example.test
```

Tùy quy tắc relaxed binding của phiên bản Boot, biến môi trường có thể bind/override thuộc tính issuer. Cách viết env thông dụng là bỏ dấu gạch ngang trong segment và thay dấu chấm bằng gạch dưới. Điều này nhấn mạnh: **người có quyền sửa deployment variables có thể thay trust config, dù file production trong Git không đổi**.

Đừng dựa vào giả định “file prod luôn thắng”. Các nguồn từ command line, environment hoặc config import có thể thay đổi kết quả tùy quy tắc ưu tiên của Boot. Để kiểm chứng:

1. Liệt kê danh sách property source có thể cấp giá trị (không xuất secret value).
2. Xác minh profile được kích hoạt và cấu hình ở `application-{profile}.yml` thực sự được tải.
3. Kiểm tra kết quả cuối cùng của **những thuộc tính không nhạy cảm** như issuer, public base URL, redirect URI, SAML entity ID bằng startup validation/health kiểm soát quyền.
4. Không expose `/actuator/env` hoặc `/actuator/configprops` ra public; nếu buộc dùng cho nội bộ, yêu cầu authentication/authorization, sanitization và mạng bảo vệ. Tuyệt đối không đổi `show-values=ALWAYS` để debug secret.

Một property có thể đúng trên file nhưng sai tại runtime vì deployment override. Chẩn đoán nên đi từ **runtime effective configuration đã được bảo vệ**, không chỉ đọc YAML đã commit.

## 9. Quản lý vòng đời và rotation secret

Credential thường đổi theo chu kỳ hoặc sau sự cố. “Chỉ thay secret ở vault” chưa chắc đủ, vì nhiều ứng dụng nạp secret vào `ClientRegistration`, `RelyingPartyRegistration` hoặc `Environment` **một lần khi khởi động**.

### OIDC client secret

Một quy trình thay secret an toàn thường gồm:

1. Kiểm tra OP có hỗ trợ nhiều secret đồng thời cho một client hay không, hoặc cần tạo client registration mới.
2. Tạo secret mới tại OP, ghi vào secret store với version mới, không xuất qua log/ticket.
3. Cấp quyền cho workload của môi trường tương ứng nhận secret mới.
4. Triển khai rollout/restart để **mọi replica** nạp giá trị mới; kiểm tra token exchange từ backend thành công.
5. Chỉ thu hồi secret cũ khi không còn instance đang sử dụng và đã xác nhận các luồng đăng nhập bình thường.
6. Nếu nghi lộ secret, chuyển sang quy trình incident rotation rút ngắn overlap, điều tra và hạn chế ảnh hưởng.

Nếu OP chỉ có thể giữ **một secret hoạt động**, việc thay secret có thể gây khoảng gián đoạn; chuẩn bị rollout đồng bộ, maintenance window hoặc chiến lược đăng ký song song theo khả năng của IdP. Không giả định secret luôn tự refresh trong Spring Boot.

### OIDC ID Token signing key / JWKS

Đây là **khóa ký của OP**, không phải client secret của RP. Khi OP rotate signing key, RP thường lấy key mới từ JWKS endpoint thuộc issuer đã tin cậy và phải xử lý cache theo cấu hình thư viện. Không chấp nhận JWKS URL hoặc `kid` bất kỳ từ token chưa xác minh; issuer, thuật toán và audience vẫn phải được kiểm tra. Cơ chế nạp lại/caching JWKS cần test ở môi trường staging trước.

### SAML certificate/private key

- **IdP đổi signing certificate:** cập nhật trust configuration của SP theo metadata/certificate đã xác minh; nếu hỗ trợ, duy trì danh sách certificate cũ + mới trong thời gian overlap.
- **SP đổi signing private key:** cập nhật certificate public tương ứng ở IdP, triển khai secret mới cho SP, xử lý giai đoạn IdP chấp nhận cả hai khóa khi có hỗ trợ.
- **SP đổi decryption key:** phối hợp việc IdP mã hóa bằng certificate mới với khả năng SP giải mã các assertion còn hợp lệ được mã hóa cho certificate cũ.
- Khóa ký và khóa giải mã có thể tách riêng để hạn chế quyền sử dụng và vòng đời.

Một lần rotate thành công cần chứng minh SSO login hợp lệ, logout (nếu có), callback, signature validation và các phiên liên quan hoạt động đúng trong giai đoạn chuyển giao.

## 10. Chống rò rỉ secret trong log, Git và CI/CD

### Repository và laptop developer

- Chỉ commit template ví dụ chứa **tên biến**, không commit giá trị thực; đặt file `.env.local`/`secrets/` chứa dữ liệu thực trong ignore và cấu hình secret scanning.
- Bổ sung scan secret ở pre-commit và CI; nếu phát hiện secret trong Git, **thu hồi/rotate secret thực**. Xóa một commit/đổi history không đảm bảo secret chưa được copy.
- Không lưu private key SAML, keystore password hay client secret trong `src/main/resources` vì file có thể được đóng gói vào JAR và phân phối rộng.
- Không đưa credentials thật vào unit test snapshots, golden files, issue tracker hoặc tài liệu hướng dẫn.

### CI/CD và runtime

- CI build artifact **không cần biết secret production** nếu ứng dụng đọc secret lúc chạy; ưu tiên tách build identity và deployment identity.
- Giới hạn job deploy prod bằng permission/approval phù hợp; che secret trong log nhưng **masking không bảo vệ trước mọi cách biến đổi dữ liệu hoặc stack trace**.
- Không chạy build/test với service account có quyền đọc production secret nếu không thực sự cần.
- Tách quyền “deploy artifact” khỏi quyền “đọc toàn bộ secret”. Workload chỉ được đọc các secret của chính môi trường và ứng dụng.
- Kiểm tra request/response logging ở proxy và backend; Authorization header, cookie, code, ID/Access/Refresh Token, SAMLResponse có thể rất nhạy cảm.
- Với file mount, cấp quyền đọc tối thiểu cho process và thiết lập audit/alert trên thay đổi secret bất thường.

**Các thông số vận hành có thể log an toàn:** tên môi trường, tên registration, issuer đã cấu hình (khi chính sách cho phép), loại lỗi mạng/token, request correlation ID không chứa PII, ngày hiệu lực của certificate public, kết quả “secret present”. Không in secret value, raw token, assertion hoặc private key.

## 11. Ma trận triển khai và QA trước khi mở production

| Kiểm tra | Dev / Staging | Production |
| --- | --- | --- |
| Profile | Đúng `dev`/`staging` | Chỉ `prod`; chặn default/dev theo chính sách |
| OIDC client | Client riêng trên IdP thử nghiệm | Client production, secret từ store được kiểm soát |
| Issuer/JWKS | URL và token `iss` của môi trường thử nghiệm | Pinned issuer/metadata từ OP prod được phê duyệt |
| Redirect URI | Host dev/staging, localhost chỉ dev nếu cho phép | HTTPS public host, đúng registration |
| SAML SP/IdP | Entity ID/ACS/certificate riêng | Entity ID/ACS/certificate prod; key private không đóng gói |
| Secret exposure | Scan repository và pipeline; mock secret cho test | RBAC, filesystem/workload identity, audit và rotation |
| Proxy/cookie | Đo scheme và callback được tạo | Trusted forwarded headers, TLS, Secure/HttpOnly/SameSite đúng luồng |
| Logging | Chỉ thông tin chẩn đoán có kiểm soát | Redact token/code/assertion, giới hạn Actuator và log |
| Khởi động | Phát hiện sai profile/missing config | Fail-fast trên sai trust/secret; rollback rõ ràng |
| Rotation | Diễn tập đổi secret, IdP cert, SAML keys | Có runbook, overlap nếu hỗ trợ, xác nhận trên mọi replica |

### Ba bài kiểm tra tích hợp đặc biệt hữu ích

**Test A – Sai issuer.** Dùng IdP dev phát ID Token có `iss` dev, nhưng RP cấu hình tin issuer prod. Kết quả mong đợi: login bị từ chối do token không thỏa issuer/verification policy; không “sửa” bằng cách bỏ kiểm tra chữ ký hoặc audience.

**Test B – Thiếu client secret.** Khởi chạy production với secret không được cấp (hoặc một đường dẫn mount bắt buộc không tồn tại). Kết quả mong đợi: kiểm tra startup/deployment health từ chối đưa ứng dụng vào phục vụ; log chỉ nêu tên property/registration thiếu, không in giá trị nhạy cảm. Cần thiết kế explicit fail-fast vì không phải mọi cấu hình trống đều được mọi release phát hiện cùng thời điểm.

**Test C – Đổi secret khi nhiều replica.** Thực hiện rotation tại OP/secret store, rollout các replica, kiểm tra login liên tục, xác nhận không instance nào vẫn dùng secret cũ trước khi revoke. Kết quả mong đợi: không còn `invalid_client` sau rollout, không cần can thiệp mã nguồn, và alert phân biệt lỗi configuration với lỗi mạng.

## 12. Các lỗi phổ biến và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách xử lý đúng |
| --- | --- | --- |
| OIDC trả `invalid_client` tại Token Endpoint | Sai client ID/secret, secret đã rotate, sai authentication method hoặc sai tenant | Đối chiếu registration và secret version với OP; kiểm tra tất cả replica; không in secret |
| `redirect_uri_mismatch` hoặc callback sai HTTP/HTTPS | Cấu hình URL sai, ingress không xử lý forwarded headers đáng tin | Kiểm tra redirect thực tế, public base URL, proxy header và danh sách callback ở OP |
| Local chạy được nhưng prod trỏ IdP dev | Profile sai hoặc environment override `issuer-uri` | Kiểm tra active profile và nguồn effective property; chỉnh permission/deployment |
| Không tải được discovery/JWKS | DNS/TLS/trust store, proxy outbound, metadata URL sai | Kiểm tra kết nối backend đến OP và trust store; không tắt xác minh TLS |
| SAML `Invalid Signature` | Sai IdP verify cert hoặc metadata chưa rotate | Lấy metadata/cert từ kênh tin cậy, kiểm tra trust và thời hạn |
| SAML decrypt failed | Thiếu/sai private decryption key, IdP đang dùng certificate khác | So cặp public certificate + private key và thứ tự rollout |
| SAML `Recipient`/`Destination` không đúng | Sai ACS/entity ID do deploy host, reverse proxy hoặc profile | Căn chỉnh host, route, IdP registration, forwarded headers |
| Secret có mặt trong vault nhưng app vẫn dùng giá trị cũ | Ứng dụng đọc lúc khởi động, không có refresh runtime | Rollout/restart có kiểm soát hoặc triển khai refresh đúng thiết kế |
| Secret nằm trong log CI | Script debug environment/command hoặc plugin in property | Dừng in, phân quyền log, thu hồi/rotate secret và quét lịch sử liên quan |

Khi debug, phân biệt **tầng cấu hình**, **kết nối TLS**, **giao thức SSO** và **phiên ứng dụng**. Một lỗi certificate TLS của token endpoint không được giải quyết bằng cách tắt ID Token signature validation. Một SAML assertion sai audience không được giải quyết bằng cách chấp nhận mọi audience.

## 13. Quy trình thực hành từ local đến prod

1. **Xác định trust boundary.** Liệt kê RP/SP, OP/IdP, proxy, issuer, callback/ACS và nhóm người dùng cho `dev`, `staging`, `prod`. Với mỗi môi trường, tạo registration tương ứng tại IdP.
2. **Thiết lập cấu trúc file.** Tạo `application.yml` với setting chung và placeholder, `application-{profile}.yml` chứa issuer/host không bí mật. Nếu dùng configtree, đặt import đúng profile.
3. **Tách secret khỏi source.** Client secret và private key nằm ở secret manager hoặc read-only mount, được cấp từ workload identity có phạm vi quyền nhỏ.
4. **Thiết kế startup validation.** Kiểm tra profile, required properties, định dạng URI/key, ranh giới issuer theo môi trường; lỗi phải rõ nhưng không tiết lộ secret.
5. **Đăng ký callback và metadata.** OIDC redirect URI và SAML entity ID/ACS/certificate phải khớp thực tế public host, nhất là khi qua reverse proxy.
6. **Chạy bài test âm.** Thử thiếu secret, issuer sai, cert chưa rotate, ACS sai, network block; đảm bảo hệ thống **từ chối an toàn** và có thông tin chẩn đoán đủ.
7. **Triển khai staging rồi prod.** Kiểm tra nhiều replica, không lộ secret trong log, health, tracing và Actuator; giám sát `invalid_client`, JWKS/SAML verify failure.
8. **Ghi nhận vòng đời.** Ai sở hữu secret, thời điểm rotate, khả năng overlap, các service tiêu thụ, cách rollback và xử lý khi một khóa bị lộ.

Đối với môi trường mới, tránh cách giải quyết “copy YAML và thay vài string”: cần kiểm tra **registration ở nhà cung cấp định danh, trust anchor và identity của workload** cùng với file cấu hình.

## 14. Câu hỏi tự đánh giá

**1. Spring Profile có bảo vệ secret production khỏi môi trường development không?**  
Không. Profile chọn cấu hình. Ranh giới bảo mật phải đến từ quyền secret store, định danh workload, hạ tầng và đăng ký IdP riêng.

**2. Có nên commit `client_id` và `client_secret` chung vào `application-prod.yml`?**  
`client_id` thường không bí mật và có thể nằm trong cấu hình được quản lý nếu chính sách cho phép. `client_secret` là credential thực, cần cấp ngoài mã nguồn qua cơ chế được bảo vệ.

**3. Vì sao issuer URI cần được kiểm soát dù không phải secret?**  
Vì issuer là một phần trust boundary: thay issuer sang hệ thống không mong muốn có thể làm RP tin sai bên phát hành.

**4. Mount Kubernetes Secret vào file rồi sửa Secret có làm Spring Boot tự đổi `ClientRegistration` đang chạy không?**  
Không nên giả định có. Mount có thể được cập nhật nhưng các đối tượng và property đã bind thường được nạp khi startup; cần xác minh cơ chế refresh hoặc rollout/restart.

**5. Có thể đưa private key SAML vào JAR để cả dev và prod cùng sử dụng cho tiện không?**  
Không. Private key nằm trong artifact sẽ lan theo mọi nơi phát hành và làm mất cách ly môi trường. Cấp private key riêng bằng secret manager/mount có quyền phù hợp.

**6. Sau khi Spring Boot báo không thấy `invalid_client`, đã đủ khẳng định federation an toàn chưa?**  
Chưa. Còn phải kiểm tra TLS, issuer/audience, state/nonce/PKCE, signature/certificate SAML, replay, callback và session policy theo giao thức.

## 15. Tài liệu chuẩn để đối chiếu

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): source precedence, property placeholders, `configtree:` và external file.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): `spring.profiles.active`, file theo profile và các giới hạn khi khai báo.
- [Spring Security – OAuth 2.0 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `ClientRegistration`, `client-id`, `client-secret`, issuer và redirect URI.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, metadata, verification và decryption credential.
- [Spring Security – SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): ví dụ property signing credential và thông tin IdP.
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): các phương thức cấp secret, giới hạn của encoding, RBAC và volumes.
- [OWASP – Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ, audit, rotation và hạn chế quyền sử dụng.
