# Quản lý client secret, khóa và mật khẩu bằng cấu hình bảo mật bên ngoài (Spring Security Reactive)

> **Bối cảnh:** Triển khai ứng dụng Spring Boot WebFlux/Spring Security ở môi trường phát triển, CI, staging và production. Bài này giải thích cách đưa OAuth2 client secret, mật khẩu kết nối dịch vụ, khóa TLS/khóa ký và thông tin xác thực ra khỏi source code, JAR, container image và các file cấu hình được commit. Các giá trị trong ví dụ chỉ là tên biến, đường dẫn hoặc dữ liệu test giả; không chứa thông tin đăng nhập sử dụng thật.

## 1. Mục tiêu và nguyên tắc cốt lõi

Sau bài học, bạn sẽ biết:

1. Phân loại secret cần **đọc lại nguyên bản** với mật khẩu người dùng chỉ cần **so khớp một chiều**; chọn cách lưu trữ phù hợp cho từng loại.
2. Dùng Spring Boot Externalized Configuration, environment variables, `spring.config.import` và `configtree:` để nạp secret vào một ứng dụng reactive.
3. Kết nối cấu hình bên ngoài với `spring.security.oauth2.client.registration.<id>.client-secret` mà không hardcode giá trị vào `application.yml`.
4. Mount secret từ Kubernetes/secret manager vào Pod một cách có kiểm soát; hiểu giới hạn của Kubernetes Secret, biến môi trường và các lần cập nhật secret.
5. Quản lý private key, TLS certificate, keystore password; tách khóa ký của authorization server khỏi khóa công khai mà resource server dùng để xác minh.
6. Thiết kế cấp quyền, theo dõi truy cập, kiểm thử cấu hình, xoay vòng và thu hồi secret, giảm nguy cơ lộ qua Git, image, log, Actuator và CI.

**Quy tắc nền:** Mã nguồn chỉ khai báo *tên khóa cấu hình* hoặc *đường dẫn đến nguồn secret*. Nguồn cung cấp giá trị thật nằm ở runtime/deployment và cấp riêng cho từng môi trường. Ẩn giá trị khỏi Git không có nghĩa là secret đã an toàn: phải bảo vệ cả nơi lưu, đường vận chuyển, quyền đọc, log và vòng đời của nó.

## 2. Những gì được coi là secret và cách xử lý

| Loại dữ liệu | Ví dụ trong WebFlux | Cách bảo vệ đúng | Sai lầm thường gặp |
| --- | --- | --- | --- |
| OAuth2 confidential client secret | `spring.security.oauth2.client.registration.billing.client-secret` | Nạp từ secret store/volume/env đã kiểm soát; phân quyền theo ứng dụng | Ghi trong YAML, biến thành `ARG`/`ENV` trong Dockerfile |
| Mật khẩu DB/Redis/SMTP, API key | `spring.r2dbc.password`, khóa gọi dịch vụ | Cấp runtime, hạn chế TTL/scope, xoay vòng | In ra log khi debug cấu hình |
| TLS private key, keystore password | File `server.p12`, `server-key.pem`, mật khẩu keystore | Lưu riêng trong KMS/HSM hoặc volume bảo vệ; hạn chế quyền đọc | Đưa private key vào `src/main/resources` hoặc image |
| Khóa dùng ký JWT | RSA/EC private key tại authorization server | HSM/KMS hoặc secret store; phân tách signer và verifier | Copy private key sang tất cả resource server |
| Public key/JWKS, CA public certificate | `jwk-set-uri`, trust certificate công khai | Không cần giữ bí mật nhưng phải đảm bảo tính xác thực và khả năng chống sửa đổi | Coi public key như mật khẩu hoặc tắt TLS verification |
| Mật khẩu đăng nhập người dùng | Password do user nhập | Lưu **hash thích ứng có salt** (bcrypt/Argon2/PBKDF2/scrypt) và so khớp `PasswordEncoder.matches` | Lưu plain text, tự SHA-256 một vòng, hoặc hash client secret cần dùng nguyên bản |
| Access/refresh token | `OAuth2AuthorizedClient`, token dùng cho WebClient | Bảo vệ trong quá trình lưu trữ, truyền và log; TTL/scope hợp lý | Cho token xuất hiện trong log/trace hoặc API response |

**Phân biệt quan trọng:**

- Mật khẩu người dùng để kiểm tra đăng nhập: hệ thống **không cần biết lại mật khẩu gốc**. Dùng `PasswordEncoder`.
- Client secret, mật khẩu DB, API key, private key: ứng dụng thường **phải trình nguyên giá trị** cho hệ thống ngoài hoặc dùng giá trị để ký. Không thể thay chúng bằng hash một chiều rồi mong kết nối vẫn hoạt động. Sử dụng vault/KMS/secret store, hoặc mã hóa có quản lý khóa nếu phải lưu lại.
- `client-id` thường là định danh có thể công khai trong protocol, **client-secret** mới là giá trị cần bảo vệ. Với public client (SPA/mobile), không có cách giấu bí mật lâu dài trong mã chạy trên thiết bị người dùng; dùng flow phù hợp như Authorization Code + PKCE thay vì nhúng client secret.

## 3. Threat model: secret có thể lộ qua những đâu?

Secret có thể bị sao chép trước khi ứng dụng nhận request:

```text
Secret manager / KMS / Vault
          |
       (cấp quyền theo identity của workload)
          |
 Deployment runtime: env / mounted volume / API provider
          |
 Spring Boot Environment + ConfigData
          |
 Config binding / OAuth2 ClientRegistration / SSL bundle
          |
 WebFlux runtime -> outbound calls qua WebClient
```

Các điểm cần kiểm soát:

- **Repository và lịch sử Git:** thêm vào `.gitignore` sau khi commit không xóa bí mật trong history. Nếu lộ, phải **thu hồi/xoay vòng**, sau đó mới xử lý lịch sử.
- **CI/CD:** secret có thể xuất hiện trong job log, command line, artifact, test report, cache, Docker build args hoặc output của script. Ưu tiên workload identity/OIDC để lấy credential ngắn hạn thay cho khóa cloud tĩnh.
- **Container image:** secret trong `Dockerfile ENV`, `ARG`, `COPY` hay một layer đã bị xóa ở layer sau vẫn có thể bị khôi phục từ image.
- **Process runtime:** biến môi trường có thể bị xem bởi hệ thống quản lý container, công cụ dump/debug hoặc tiến trình đủ quyền; mounted file bị đọc bởi user/container không được phép nếu mount mode/UID sai.
- **Spring configuration/observability:** không echo `Environment`, `ClientRegistration`, exception chứa URL có userinfo, Authorization headers hoặc nội dung `/actuator/env` và `/actuator/configprops`.
- **Mạng:** secret truyền tới IdP/DB/KMS qua TLS với trust chain đúng; không tắt hostname/certificate verification để “sửa nhanh”.
- **Sao lưu:** secret còn trong snapshot, old revision, Git, log, crash dump hoặc backup sau khi đã rotate; chính sách hủy cũng phải bao gồm bản sao.

Một secret được “mã hóa khi lưu” nhưng ai cũng đọc được khóa giải mã gần như không đạt mục tiêu. Cần **identity + least privilege + audit + rotation** đi cùng mã hóa.

## 4. Cơ chế externalized configuration của Spring Boot

Spring Boot gom các nguồn cấu hình thành `Environment`, rồi bind vào bean qua `@ConfigurationProperties`, `@Value` hoặc auto-configuration. Nguồn có thể là:

- `application.yml`/**profiles**: định nghĩa tên thuộc tính, địa chỉ endpoint, chế độ chạy và tham chiếu tới secret.
- **Environment variables** được runtime cung cấp: phù hợp triển khai đơn giản nhưng có rủi ro lộ qua process/deployment metadata.
- **File ngoài JAR** hoặc **config tree**: đặc biệt phù hợp secret volume của Kubernetes và Docker.
- **Secret management system** (HashiCorp Vault, cloud secret manager, KMS/HSM): cung cấp truy cập có xác thực, phiên bản, thu hồi, audit và nhiều nơi hỗ trợ rotation tự động.
- **Command-line/system properties**: có thể override cấu hình nhưng **tránh truyền secret trực tiếp** vì command line/log/process listing có thể quan sát được.

Với các nguồn có độ ưu tiên khác nhau, cấu hình sau có thể ghi đè nguồn trước. Hãy kiểm tra thứ tự property sources chính thức theo phiên bản Boot đang chạy; đừng suy đoán secret được lấy từ đâu dựa trên tên profile.

### 4.1. Placeholder không chứa giá trị bí mật

Ví dụ trong `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: reactive-billing-api

  security:
    oauth2:
      client:
        registration:
          billing:
            provider: billing-idp
            client-id: reactive-billing-service
            client-secret: ${BILLING_OAUTH2_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: billing.read
        provider:
          billing-idp:
            token-uri: https://identity.example.invalid/oauth2/token

  r2dbc:
    url: r2dbc:postgresql://db.internal:5432/billing
    username: billing_app
    password: ${BILLING_DB_PASSWORD}
```

Đây là **mảnh cấu hình** cho ứng dụng đã cài OAuth2 Client và R2DBC; các hostname `.invalid` minh họa, không hoạt động như một dịch vụ thật. Giá trị secret thật đến từ runtime dưới tên `BILLING_OAUTH2_CLIENT_SECRET`, `BILLING_DB_PASSWORD`. Không thêm fallback kiểu `${BILLING_OAUTH2_CLIENT_SECRET:change-me}` hoặc `:password` ở production vì nó che khuất cấu hình bị thiếu và có thể trở thành secret yếu.

Dependency tương ứng (Gradle Kotlin DSL, bản phát hành do Spring Boot BOM đang dùng quản lý):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Nếu không dùng R2DBC, bỏ starter và khối `spring.r2dbc`; nếu ứng dụng chỉ là **Resource Server nhận JWT**, dùng `spring-boot-starter-oauth2-resource-server`, không cấu hình client secret khi không có nhu cầu OAuth2 Client. Các ví dụ trong bài dùng Java 17+, Spring Boot 3+/4+ và Spring Security phiên bản tương thích do BOM cung cấp.

### 4.2. Cấp giá trị qua environment variables

Orchestrator có thể đặt `BILLING_OAUTH2_CLIENT_SECRET` và `BILLING_DB_PASSWORD` vào process environment trước khi Spring Boot khởi động. Với production, **không** copy giá trị thật vào tập tin script được commit hoặc command line lưu trong shell history. Nếu vận hành cục bộ, nạp secret từ công cụ quản lý credential của nhóm, sử dụng terminal/session được bảo vệ và thu hồi quyền khi kết thúc.

Ví dụ mã Java chỉ đọc trạng thái **có/không có**, không đọc ra log giá trị:

```java
// File SecretPresenceCheck.java — Java 17+, độc lập với Spring
public class SecretPresenceCheck {
    public static void main(String[] args) {
        String secret = System.getenv("BILLING_OAUTH2_CLIENT_SECRET");
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException(
                    "Missing BILLING_OAUTH2_CLIENT_SECRET");
        }
        System.out.println("Required secret is available");
    }
}
```

Chạy `javac SecretPresenceCheck.java` rồi `java SecretPresenceCheck` trong process có biến `BILLING_OAUTH2_CLIENT_SECRET`. Khi biến hợp lệ, stdout **chính xác** là:

```text
Required secret is available
```

Nếu biến không tồn tại/trống, chương trình ném `IllegalStateException` và exit khác 0; không in giá trị. Ví dụ chỉ kiểm tra biến đã được cấp, **không chứng minh** secret đúng, chưa lộ, chưa hết hạn hay đã có quyền truy cập IdP. Đây là chương trình Java độc lập; chạy ứng dụng Spring Boot cần project/dependency và cấu hình tương ứng.

### 4.3. Fail-fast với cấu hình riêng

Với thông tin xác thực tự định nghĩa, dùng binding có validation để phát hiện giá trị trống khi startup. Tạo file `src/main/java/com/example/security/RemoteCredentials.java`:

```java
package com.example.security;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.remote")
public record RemoteCredentials(@NotBlank String apiKey) {
    // Record toString() mặc định sẽ lộ giá trị field; thay bằng bản ẩn.
    @Override
    public String toString() {
        return "RemoteCredentials[apiKey=<redacted>]";
    }
}
```

Đăng ký bean bằng class `src/main/java/com/example/security/SecretsConfiguration.java`:

```java
package com.example.security;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteCredentials.class)
public class SecretsConfiguration {
}
```

Và thêm thuộc tính vào cấu hình môi trường:

```yaml
app:
  remote:
    api-key: ${REMOTE_API_KEY}
```

`@NotBlank` cần Bean Validation provider (`spring-boot-starter-validation`). Cấu hình thiếu có thể gây lỗi ở bước resolve placeholder hoặc binding/validation; hãy kiểm thử trường hợp thiếu thực tế trong môi trường chạy để xác nhận hệ thống **không khởi động** khi secret bắt buộc vắng mặt. Không in exception chứa giá trị bí mật; thông báo validation nên nêu **tên khóa** cần bổ sung, không dump toàn bộ properties.

**Lưu ý:** Ghi đè `toString()` chỉ giảm rủi ro ở một đường log, không thể thay thế chính sách logging, heap dump và quản lý truy cập. Với credential dạng `String`, JVM không bảo đảm xóa tức thời mọi bản sao trong bộ nhớ; quyền truy cập vào process vẫn là một ranh giới bảo mật quan trọng.

## 5. Configuration Tree: đọc secret từ volume ngoài container image

Với `configtree:`, tên file (hoặc đường dẫn thư mục) trở thành **property key**, nội dung file là **property value**. Cấu hình này phù hợp khi orchestrator mount secret thành file và Spring Boot nạp khi khởi động.

Ví dụ production profile `src/main/resources/application-prod.yml`:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

  security:
    oauth2:
      client:
        registration:
          billing:
            provider: billing-idp
            client-id: reactive-billing-service
            authorization-grant-type: client_credentials
            scope: billing.read
        provider:
          billing-idp:
            token-uri: https://identity.example.invalid/oauth2/token
```

Tại runtime có file:

```text
/run/secrets/
└── spring.security.oauth2.client.registration.billing.client-secret
```

Nội dung file đó là secret do nền tảng cấp, **không** nằm trong repo/JAR/image. Spring Boot nhận property `spring.security.oauth2.client.registration.billing.client-secret` từ config tree. Tên file sử dụng dấu chấm như trên là hợp lệ trong config tree; không cần tạo từng thư mục theo mỗi dấu chấm.

Tùy chọn `configtree:/run/secrets/` có ý nghĩa “nơi này **bắt buộc tồn tại**”. `optional:configtree:/run/secrets/` cho phép thư mục vắng mặt và thường phù hợp local/test hơn; với production yêu cầu secret, cân nhắc không dùng `optional:` và có thêm validation để loại trường hợp thư mục tồn tại nhưng file giá trị rỗng/missing.

Không khai báo đồng thời một placeholder không mong muốn ở một property source có thứ tự ưu tiên cao hơn khiến giá trị từ config tree bị ghi đè. Chọn **một cơ chế làm nguồn chuẩn** cho cùng một secret trên mỗi môi trường; nếu kết hợp env + configtree, phải kiểm thử precedence.

### 5.1. Kubernetes Secret mount trong Deployment

Manifest sau **không chứa giá trị bí mật**; giả định cluster đã có Secret tên `billing-oauth2`, key `client-secret` do quy trình cấp phát riêng tạo:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: reactive-billing-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: reactive-billing-api
  template:
    metadata:
      labels:
        app: reactive-billing-api
    spec:
      containers:
        - name: app
          image: registry.example.invalid/billing/reactive-api:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          volumeMounts:
            - name: oauth2-secrets
              mountPath: /run/secrets
              readOnly: true
      volumes:
        - name: oauth2-secrets
          secret:
            secretName: billing-oauth2
            items:
              - key: client-secret
                path: spring.security.oauth2.client.registration.billing.client-secret
```

**Điều kiện vận hành:** Secret `billing-oauth2` phải tồn tại trong **cùng namespace** với Pod và có key `client-secret`. Kubernetes cung cấp file theo mount; Spring Boot đọc file từ `configtree:/run/secrets/`. Người giữ quyền cấp phát có thể dùng External Secrets Operator, Secrets Store CSI Driver, Vault hoặc công cụ cloud tương ứng để đưa secret từ kho tập trung vào cluster. Cách cụ thể phụ thuộc nền tảng, chính sách và phiên bản driver.

Ở production, thực hiện thêm: quyền RBAC chỉ cho controller/identity cần thiết; mã hóa Secret tại etcd khi được hỗ trợ; giới hạn ai có quyền `get/list/watch` Secret và quyền `exec`/`attach` vào Pod; chỉ mount vào container cần dùng; Pod chạy user ít quyền; hạn chế truy cập node/snapshot.

**Không hiểu nhầm `Secret` là tự động mã hóa an toàn:** trường `data` trong Kubernetes Secret là **Base64 encoding**, không phải encryption; mặc định Secret có thể được lưu chưa mã hóa tại datastore nếu cluster chưa bật encryption at rest. Mount volume không tự xóa nguy cơ từ quyền đọc file, backup hay node bị xâm nhập.

### 5.2. Mount file so với env trong Kubernetes

| Tiêu chí | `secretKeyRef` thành env | Secret volume + `configtree:` |
| --- | --- | --- |
| Hình thức | Process environment | File trong filesystem của container |
| Ứng dụng Spring Boot | Bind qua env/property placeholder | Bind các property key qua config tree |
| Khi Secret cập nhật | Env của process đang chạy **không tự đổi**; cần khởi tạo process/Pod mới | File mount thường được kubelet cập nhật sau một độ trễ; **app có nạp lại không** là chuyện riêng |
| Vùng lộ | Env inspection, process dump, deployment metadata | File permissions, container/node access, backup |
| Lưu ý | Không log env, không dump toàn bộ process | Tránh mount qua `subPath` nếu cần cập nhật tự động; kiểm tra file owner/mode |

**Điểm quan trọng:** Dù file trong volume đã đổi, Spring Boot `Environment`, `@ConfigurationProperties`, OAuth2 `ClientRegistration` hay bean đã tạo thường **không tự thay đổi theo**. Muốn credential mới có hiệu lực phải có chiến lược reload được hỗ trợ, refresh/rebind có kiểm soát hoặc rolling restart. Không nói “Kubernetes tự rotate toàn bộ OAuth2 client secret trong ứng dụng” chỉ vì mount cập nhật.

## 6. Secret manager, Vault, KMS và workload identity

Externalized configuration tách mã và dữ liệu bí mật; secret manager bổ sung khả năng phân phối và kiểm soát.

**Các lựa chọn phổ biến:**

- **HashiCorp Vault/Spring Cloud Vault:** Spring Cloud Vault hỗ trợ `spring.config.import: vault://` khi có starter/extension tương thích, Vault URI, TLS và cơ chế xác thực. Workload được cấp policy chỉ đọc path của chính nó; ưu tiên Kubernetes auth/AppRole/OIDC phù hợp hơn việc nhúng root token vào `application.yml`.
- **AWS Secrets Manager / Systems Manager Parameter Store, Azure Key Vault, Google Secret Manager:** sử dụng integration/SDK/CSI/sidecar thích hợp và IAM workload identity. Spring Boot **không mặc định hiểu mọi prefix import của nhà cung cấp** nếu chưa cài connector/dependency tương ứng.
- **KMS/HSM:** giữ key material không xuất ra ngoài (nếu API/provider hỗ trợ) và thực hiện ký/giải mã bằng API được phân quyền. Hữu ích với signing key, envelope encryption và các ranh giới bảo mật nghiêm ngặt. KMS không thay thế hoàn toàn công cụ lưu/password rotation.

Ví dụ ý tưởng **Spring Cloud Vault** (cần cài dependency và đặt phương thức auth thật theo triển khai):

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal.example.invalid:8200
```

Đây chỉ là điểm tích hợp. Chưa thể chạy nếu không có Vault server, trust CA, policy/path/secret backend và authentication phù hợp. **Không đưa `spring.cloud.vault.token` tĩnh, root token hay cloud access key vào Git** chỉ để giúp ứng dụng khởi động. Trong container, ưu tiên identity gắn với service account/workload có TTL và quyền tối thiểu.

Luồng an toàn mẫu:

```text
Pod ServiceAccount / Cloud Workload Identity
    -> authenticate to Secret Manager (TLS)
    -> policy: read exactly billing/prod/client-secret
    -> receive current secret version (or mount it)
    -> Spring Boot binds OAuth2 ClientRegistration
    -> WebClient uses authorized access token for downstream
    -> audit retrieval + rotate/revoke on schedule
```

**Không thực hiện secret-manager SDK blocking call trong event loop WebFlux.** Có thể nạp secret lúc startup qua ConfigData/integration; nếu bắt buộc đọc runtime, dùng SDK non-blocking hoặc đưa thao tác blocking ra `Schedulers.boundedElastic()` sau khi cân nhắc caching, timeout, concurrency, error handling. Việc `block()` trong `SecurityWebFilterChain`/handler/`WebClient` callback có thể làm nghẽn Reactor Netty event loop.

## 7. Quản lý khóa, chứng chỉ và mật khẩu keystore

Không phải mọi “key” đều là string gắn vào `@Value`.

### 7.1. HTTPS inbound của WebFlux (Reactor Netty)

Với PKCS#12 được tạo/cấp từ hệ thống bí mật ngoài JAR, Spring Boot hỗ trợ SSL bundle. Ví dụ `application-prod.yml` (mảnh bổ sung):

```yaml
spring:
  ssl:
    bundle:
      jks:
        web:
          keystore:
            location: "file:/run/keys/server.p12"
            type: PKCS12
            password: ${SERVER_KEYSTORE_PASSWORD}

server:
  port: 8443
  ssl:
    bundle: web
```

`/run/keys/server.p12` là file được mount với read permission cho tiến trình cần thiết; `SERVER_KEYSTORE_PASSWORD` được runtime cấp. Không copy `.p12`, private key hoặc password vào build context/image. Mật khẩu keystore dùng để giải mã/mở keystore; **không thay thế** bảo vệ quyền đọc file và private key.

Với certificate + private key PEM, `spring.ssl.bundle.pem.<name>.keystore.certificate` và `...private-key` có thể trỏ tới đường dẫn `file:/run/keys/...`. SSL bundle có các tùy chọn reload có điều kiện trên phiên bản Spring Boot mới và consumer được hỗ trợ (bao gồm Netty server); **không giả định mọi WebClient, driver, key store hoặc Boot version đều tự hot reload**. Kiểm tra tài liệu version đang chạy và thử đổi chứng chỉ trong staging.

### 7.2. JWT signing key: signer khác verifier

- **Authorization Server** ký JWT bằng **private key**. Giữ private key trong HSM/KMS hoặc một nơi bảo vệ thích hợp; endpoint chỉ được quyền ký theo policy.
- **Reactive Resource Server** thường **xác minh** JWT với public key/JWKS của issuer qua `jwk-set-uri` hoặc cấu hình `issuer-uri` (bao gồm cơ chế discovery phù hợp). Resource server thường **không cần** private signing key hoặc OAuth2 client secret để verify token.
- Dùng HTTPS, kiểm tra issuer, audience theo yêu cầu nghiệp vụ, algorithm cho phép và `kid`; không tin một JWKS URI do user input tùy ý điều khiển.
- Xoay vòng ký JWT: phát hành key mới với `kid` mới, giữ public key cũ trong JWKS đủ lâu cho token hợp lệ còn sống, chuyển sang key mới, đợi token cũ hết hạn rồi loại key cũ. Trường hợp private key bị lộ thì phải kích hoạt kế hoạch ứng phó riêng, có thể buộc thu hồi sớm.

Ví dụ resource server dùng issuer tin cậy:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.invalid/
```

Đây là cấu hình **Resource Server** kiểm JWT inbound, không lưu client secret, và cần dependency `spring-boot-starter-oauth2-resource-server`. Issuer phải hỗ trợ metadata/JWKS tương ứng trong môi trường thật.

## 8. Mật khẩu người dùng: `PasswordEncoder` thay vì config secret

Khi ứng dụng WebFlux cung cấp form login hoặc xác thực bằng username/password, DB nên lưu password hash thích ứng, không chứa mật khẩu gốc. Spring Security có `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, hỗ trợ prefix như `{bcrypt}` để dùng thuật toán phù hợp khi verify.

Ví dụ JUnit 5 hoàn chỉnh trong project đã có Spring Security Crypto và starter test. File `src/test/java/com/example/security/PasswordHashTest.java`:

```java
package com.example.security;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PasswordHashTest {
    @Test
    void usesAdaptiveOneWayPasswordHash() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        String raw = "test-only-user-password";
        String stored = encoder.encode(raw);

        assertNotEquals(raw, stored);
        assertTrue(stored.startsWith("{bcrypt}"));
        assertTrue(encoder.matches(raw, stored));
        assertFalse(encoder.matches("incorrect", stored));
    }
}
```

Chạy `./gradlew test --tests com.example.security.PasswordHashTest` (Windows: `gradlew.bat test --tests com.example.security.PasswordHashTest`). **Kết quả dự kiến:** test pass, không có stdout ứng dụng. Hash bcrypt có salt nên giá trị được encode khác nhau giữa các lượt; đừng assert nguyên một chuỗi hash cố định. Cân chỉnh work factor theo phần cứng/độ trễ mục tiêu; áp dụng chính sách bảo vệ brute force và đăng nhập thất bại ngoài việc hash.

**Không sử dụng `PasswordEncoder` cho mật khẩu DB, OAuth2 client secret hoặc API key phải xuất trình lại**. Hash một chiều làm mất giá trị gốc cần thiết để xác thực với hệ thống ngoài; những credential này cần secret store và cơ chế đọc có bảo vệ.

## 9. Kiểm thử cấu hình OAuth2 Client mà không lộ secret

Với OAuth2 Client, test cần chứng minh **đúng registration ID được bind**, giá trị đến từ test configuration, và không có yêu cầu đến authorization server thật. Ví dụ trong project Spring Boot WebFlux có `spring-boot-starter-oauth2-client`, tạo file `src/test/java/com/example/security/OAuth2SecretBindingTest.java`:

```java
package com.example.security;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(properties = {
        "spring.security.oauth2.client.registration.billing.client-id=test-client",
        "spring.security.oauth2.client.registration.billing.client-secret=test-only-secret",
        "spring.security.oauth2.client.registration.billing.authorization-grant-type=client_credentials",
        "spring.security.oauth2.client.provider.billing.token-uri=https://identity.example.invalid/token"
})
class OAuth2SecretBindingTest {
    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Test
    void bindsExternalizedOAuth2Registration() {
        ClientRegistration registration = registrations
                .findByRegistrationId("billing")
                .block(Duration.ofSeconds(2)); // Chỉ block trong test sync.

        assertNotNull(registration);
        assertEquals("billing", registration.getRegistrationId());
        assertEquals("test-client", registration.getClientId());
        assertEquals("test-only-secret", registration.getClientSecret());
    }
}
```

Dữ liệu `test-only-secret` là **fixture giả**, không phải credential thật và không cần lưu trong secret manager. Kết quả mong đợi: test pass khi Spring Boot auto-config tạo `ReactiveClientRegistrationRepository`; test **không** gửi HTTP request/token request tới URL `.invalid`. Những lớp trên giả định package test được ứng dụng Boot scan và cấu hình ứng dụng không có bean/repository tùy biến thay thế; nếu có, điều chỉnh test context cho phù hợp.

Chạy `./gradlew test --tests com.example.security.OAuth2SecretBindingTest` (Windows: `gradlew.bat test --tests com.example.security.OAuth2SecretBindingTest`). JUnit không in secret; tránh thêm `System.out.println(registration)` hoặc log `ClientRegistration`.

**Ranh giới kiểm thử:**

- Test trên xác nhận **property binding**. Nó không xác nhận file Kubernetes Secret, Vault policy, quyền của Pod, TLS tới IdP hay token grant thật.
- Test môi trường staging cần chứng minh startup lấy được secret bằng workload identity thật; nhưng không in giá trị. Chỉ log tên registration, version/metadata không nhạy cảm hoặc dấu hiệu “configuration ready”.
- Test thiếu secret: chạy trên môi trường sạch, với cấu hình bắt buộc và validation, kiểm tra startup báo **thiếu key** và fail; không in nội dung key.
- Test client secret đã rotate: xác nhận Pod/bean sử dụng version mới và IdP cấp token thành công; kiểm tra những phiên cũ bị thu hồi đúng thời điểm.
- Test luồng OAuth2 client-to-service: dùng `MockWebServer`/WireMock cho downstream, OAuth2 client/manager giả nếu cần; assert header Bearer ở server giả, không ghi access token thật.

## 10. Rotation: từ version cũ đến version mới không gián đoạn

Secret rotation gồm **tạo mới, phát hành, chuyển lưu lượng, kiểm chứng, thu hồi**. Chỉ đổi nội dung một file chưa đủ.

1. **Kiểm kê:** xác định secret owner, nơi dùng, registrationId, phạm vi quyền, thời hạn, nơi lưu version, các Pod/workload phụ thuộc và thủ tục rollback.
2. **Tạo version mới:** tại IdP/DB/secret manager/KMS với thuật toán và entropy phù hợp. Nếu provider hỗ trợ hai credential cùng tồn tại, ưu tiên cửa sổ chồng lắp có hạn.
3. **Phân phối:** cập nhật version trong secret store hoặc volume; xem lịch cập nhật của Kubernetes/CSI/sidecar và các cache liên quan.
4. **Đảm bảo ứng dụng sử dụng version mới:** rolling restart Pod (phổ biến, dễ kiểm chứng), hoặc cơ chế reload đã được hỗ trợ/test cho từng component. Env của process không tự cập nhật; `@ConfigurationProperties` hoặc bean OAuth2 ClientRegistration cũng không tự rebind chỉ vì file đổi.
5. **Kiểm thử:** kiểm tra readiness, token request thành công bằng credential mới, latency/5xx/401/invalid_client, khả năng truy cập downstream và không có traffic gửi credential cũ.
6. **Thu hồi secret cũ:** chỉ khi đã xác minh hết consumer; ghi audit/sự kiện vận hành, thông báo owner, dọn bản sao trong pipeline/kho tạm theo retention policy.
7. **Kế hoạch rollback:** rollback application/version config có thể cần mở cửa sổ cho credential cũ nếu vẫn hợp lệ. Khi credential bị lộ, **không** khôi phục secret đã compromise; phát hành secret an toàn mới.

### Các tình huống riêng

- **OAuth2 client secret:** thay credential ở authorization server và Spring ClientRegistration; request xin token mới có thể trả `invalid_client` nếu hai phía lệch version. Access token đã cấp trước đó có thể còn hợp lệ đến hết TTL, tùy chính sách IdP.
- **Password DB:** có thể cần cơ chế cấp nhiều user/credential song song để chuyển dần; connection pool đang giữ kết nối cũ không chứng minh connection mới dùng mật khẩu mới.
- **TLS certificate/private key:** có thể dùng SSL bundle reload nếu đúng Boot version và Netty consumer hỗ trợ; kiểm tra handshake và chain bằng client thật sau rotation.
- **JWT signing key:** phải phối hợp `kid`, JWKS cache và token TTL; không xóa public key cũ quá sớm gây lỗi xác minh các token vẫn còn hiệu lực.
- **Refresh token:** không cùng vòng đời client secret; lưu an toàn và có thể phải vô hiệu hóa phiên/token khi ứng phó sự cố.

### Khi nghi ngờ đã lộ secret

Ưu tiên chặn lạm dụng: thu hồi/xoay credential tại nhà cung cấp; giới hạn quyền và session/token liên quan; truy xuất audit/usage để xác định phạm vi; cập nhật config và rollout; xử lý Git history/log/artifact/backup theo quy trình điều tra. **Chỉ xóa secret khỏi repo hoặc sửa commit không vô hiệu hóa credential bị lộ.**

## 11. Bảo vệ logs, Actuator, HTTP trace và CI

### Spring Boot Actuator

Endpoint `/actuator/env` và `/actuator/configprops` có cơ chế che giá trị mặc định trong nhiều phiên bản Boot; nhưng không nên xem việc masking là rào chắn duy nhất. Giới hạn exposure và xác thực/authorization cho management endpoints. Ví dụ cấu hình production:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

Không bật `show-values: always` ở production. `/actuator/heapdump`, thread dump, debug endpoints, trace/httpexchanges cũng cần xem xét quyền truy cập. Debug logging của security/OAuth2/HTTP clients có thể lộ payload hoặc Authorization headers thông qua logger/filter tùy chỉnh; **đừng log Bearer token hay request headers nguyên bản**.

### WebClient trong hệ reactive

- `WebClient` gắn Authorization bằng filter khi chọn authorized client; chỉ gửi credential đến đúng host/registration đã thiết kế. Không dùng cơ chế gắn bearer mặc định lên mọi request tới domain bất kỳ.
- Không ghi `Authorization`, `Cookie`, `Set-Cookie`, `client_secret` vào structured logs, traces, exception messages hoặc sự kiện audit.
- Nếu tự viết `ExchangeFilterFunction` để log request, xây bộ **allowlist header** an toàn (method, path đã loại dữ liệu nhạy cảm, status, thời gian), không dùng `request.headers()` nguyên bản.
- Đặt timeout và retry hợp lý đối với KMS/Vault; không retry vô hạn và không fallback sang giá trị tĩnh hardcoded khi secret provider bị lỗi.
- Khi key/secret đọc lại bằng API blocking, không thực hiện call blocking trên Reactor Netty event loop; chuẩn bị cấu hình khi startup hoặc dùng API bất đồng bộ phù hợp.

### CI/CD và quy trình phát triển

- Dùng **secret scanning** (pre-commit + repository/CI), hạn chế quyền người chạy job, quản lý masking và review artifact/log; rà soát false negatives.
- Không truyền secret thật vào `docker build --build-arg`, kiểm soát Docker layer/cache; runtime mount/secret provider là ranh giới phù hợp cho service credentials.
- Không in env bằng `printenv`, `env` hay `set` trong CI job có secret; hạn chế shell debug `set -x`.
- Chỉ dùng **fixture không có giá trị thật** trong `src/test/resources`; secret thật không nằm trong test fixture, screenshot, ticket hoặc PR.
- Phân quyền theo **service + môi trường**: `billing-dev` không đọc `billing-prod`; một service không có quyền đọc secret của service khác.
- Các trường `client-secret`, `password`, `api-key`, `private-key` được kiểm tra qua tên thuộc tính, nhưng scanner cần bao phủ cả giá trị không có tên rõ ràng, log, artifact, history.

## 12. Các lỗi triển khai điển hình

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra an toàn |
| --- | --- | --- |
| Khởi động thiếu secret | Env chưa cấp, path mount sai, key trong configtree sai hoặc không có quyền đọc | Kiểm tra **sự tồn tại/tên** key và mount, service account, file permissions; không in value |
| OAuth2 token endpoint trả `invalid_client` | Sai client-id/client-secret, IdP chưa rotate, giá trị có newline hoặc app đang dùng version cũ | Kiểm tra registration ID, thứ tự property sources, version; xác thực với IdP qua luồng kiểm thử kiểm soát |
| Local chạy được, Pod fail | Local có env; Pod dùng volume nhưng không bật đúng profile hoặc `spring.config.import` | Kiểm tra profile, mount path, namespace, import và bean binding |
| File trong Pod đổi nhưng request vẫn lỗi | Bean/OAuth2 registration đã bind từ startup, chưa refresh | Rolling restart hoặc triển khai reload có kiểm chứng |
| K8s Secret được base64 nhưng vẫn bị lộ | Nghĩ base64 là encryption, quyền RBAC quá rộng, image/log/backup còn secret | Bật encryption at rest, giảm RBAC, rotate và kiểm tra truy vết |
| WebFlux chậm khi Vault gặp sự cố | Blocking SDK gọi trong event loop, retry vô hạn | Đưa I/O ra startup/non-blocking path, timeout/circuit breaker và fail-closed phù hợp |
| Log xuất hiện Authorization token | HTTP filter/log request/trace cấu hình sai | Tắt body/header logging, scrub thông tin nhạy cảm, rotate token bị lộ |
| Resource Server thiếu private key | Cố đem signing key sang verifier | Chỉ cấu hình issuer/JWKS public phù hợp; giữ private key tại signer |
| Password test thất bại sau deploy | Hash không có prefix/algorithm không tương thích hoặc dùng `NoOpPasswordEncoder` | Dùng `DelegatingPasswordEncoder`, kế hoạch migrate và test hash thật |
| Certificate mới được mount nhưng TLS vẫn phục vụ cert cũ | SSL consumer không reload hoặc cấu hình path sai | Kiểm tra Boot/Netty version và hỗ trợ reload; restart nếu cần |

## 13. Checklist kiểm tra trước khi phát hành

- [ ] Không có secret thật trong source, Git history còn dùng được, JAR, image, Helm values/manifest được commit, log, test fixture hoặc CI artifact.
- [ ] Cấu hình ứng dụng chứa **property names** và **secret references**; production lấy giá trị từ cơ chế được tổ chức phê duyệt.
- [ ] Phân loại đúng: **user password hash** bằng `PasswordEncoder`, **service credential và private key** đọc từ secret store/KMS/mount.
- [ ] Identity/service account có quyền tối thiểu tới đúng secret của đúng môi trường; có audit việc đọc và thay đổi version.
- [ ] OAuth2 client registration ID/client-id, grant type, scopes và token endpoint đúng; client-secret không được log.
- [ ] `configtree:`/env/Vault/CSI được test trong container tương tự production, kiểm tra thiếu secret dẫn tới lỗi startup rõ ràng mà không lộ value.
- [ ] Quyền file/volume, network TLS, CA trust, certificate expiry và policy của KMS/secret manager được kiểm chứng.
- [ ] Phân biệt cập nhật mount với cập nhật bean runtime; có chiến lược restart/reload và kiểm thử rotation.
- [ ] Actuator/management endpoints chỉ expose chức năng cần thiết; log/trace/heap dump được kiểm soát.
- [ ] Có owner, lịch rotate, kế hoạch thu hồi, thời gian overlap, kiểm thử dự phòng và quy trình ứng phó khi lộ.

## 14. Câu hỏi tự luyện

1. Vì sao có thể lưu password hash của người dùng nhưng **không** dùng bcrypt thay cho OAuth2 client secret?
2. Viết tên property mà file `/run/secrets/spring.security.oauth2.client.registration.billing.client-secret` cung cấp cho `configtree:/run/secrets/`.
3. Bí mật trong Kubernetes Secret có tự động được mã hóa chỉ vì dữ liệu ở dạng Base64 không? Quyền nào cần hạn chế?
4. Khi secret volume cập nhật nhưng `ReactiveClientRegistrationRepository` vẫn dùng secret cũ, bạn sẽ triển khai và xác minh rotation như thế nào?
5. Tại sao resource server thông thường chỉ cần public key/JWKS để verify JWT, còn private signing key nên ở authorization server?
6. Một filter `WebClient` ghi toàn bộ request headers để debug có thể làm lộ những gì? Cách log an toàn hơn là gì?
7. Khi Vault/KMS API là blocking, vì sao gọi trực tiếp trong WebFlux request handler có thể gây nghẽn service?
8. Trong một ca lộ client secret đã commit lên Git, tại sao “xóa dòng secret khỏi file” chưa phải là phương án xử lý đủ?

## Tài liệu tham khảo chính thức

- Spring Boot – Externalized Configuration và Configuration Trees: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot – SSL Bundles và cơ chế reload: https://docs.spring.io/spring-boot/reference/features/ssl.html
- Spring Boot – Actuator Endpoints và value sanitization: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Security – Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security – Reactive OAuth2 Client core classes: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security – Password Storage / PasswordEncoder: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Kubernetes – Secrets good practices: https://kubernetes.io/docs/concepts/security/secrets-good-practices/
- Spring Cloud Vault – Quick Start / ConfigData: https://docs.spring.io/spring-cloud-vault/reference/quickstart.html

> Hãy đối chiếu chi tiết cấu hình reload, Spring Boot/Cloud version và từng secret provider theo BOM và môi trường triển khai thật. Ví dụ minh họa dùng domain `.invalid` và dữ liệu giả, không chứa credential vận hành.
