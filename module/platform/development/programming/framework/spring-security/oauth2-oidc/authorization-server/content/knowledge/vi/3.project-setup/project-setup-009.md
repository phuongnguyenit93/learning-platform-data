# Quản lý cấu hình nhạy cảm bằng biến môi trường và secret store

> **Chương: Khởi tạo dự án.** Bài học thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**: thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server với Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Mục tiêu là đưa bí mật ra khỏi mã nguồn và artifact, cấp đúng quyền truy cập cho tiến trình chạy, kiểm soát vòng đời và kiểm thử việc thay đổi secret.

## 1. Vì sao Authorization Server cần quản lý secret nghiêm ngặt?

Authorization Server phát hành authorization code, access token và (khi bật OIDC) ID Token cho các client. Nếu lộ khóa ký hoặc một bí mật có quyền cao, kẻ tấn công có thể giả mạo token, mạo danh client hoặc truy cập dữ liệu nhạy cảm. Ngay từ bước khởi tạo dự án, phải tách **cấu hình thường** khỏi **cấu hình nhạy cảm** và xác định ai được phép xem, cập nhật, xoay vòng từng loại.

| Giá trị | Có phải bí mật? | Vị trí sử dụng | Lưu ý |
|---|---|---|---|
| `issuer` (`https://login.example.vn`) | Không | Authorization Server, Client, Resource Server | Cần ổn định, công khai và khớp claim `iss`; thay đổi phải có kế hoạch |
| `client_id`, registered redirect URI | Không | RegisteredClient và OAuth2 Client | Không được xem `client_id` là mật khẩu |
| **Client secret** của confidential client | **Có** | Client khi xác thực với `/oauth2/token`; bản hash trên Authorization Server | Bảo vệ bản rõ ở phía client; phía Authorization Server ưu tiên lưu **hash một chiều** |
| **Private signing key** dùng ký JWT/ID Token | **Có, mức rất cao** | Authorization Server hoặc KMS/HSM | Khóa riêng phải được giữ bí mật; khóa công khai tương ứng có thể xuất bản qua JWKS |
| Password của PKCS#12/keystore | **Có** | Tiến trình tải khóa ký/TLS | Bảo vệ cả file khóa và mật khẩu mở khóa |
| Database password, Redis password, API key tích hợp | **Có** | Hạ tầng và dịch vụ phụ trợ | Giới hạn quyền và vòng đời theo từng môi trường |
| `jwks_uri`, public JWK | Không | Metadata và Resource Server | Công bố public key, không công bố private key |
| Access token, refresh token, authorization code đang hoạt động | **Nhạy cảm** | Dữ liệu giao thức trong lúc chạy | Không phải cấu hình tĩnh; tuyệt đối tránh ghi đầy đủ vào log |

Ví dụ xuyên suốt: Authorization Server dùng issuer `https://login.example.vn`; client web có `client_id=portal-web`, callback `https://app.example.vn/login/oauth2/code/portal`. Tài liệu minh họa hai cách cung cấp client secret: **biến môi trường** và **secret store cấp giá trị vào runtime**. Bí mật trong đoạn mã được biểu diễn bằng tên biến hoặc placeholder, không chứa giá trị thật.

Mục tiêu bảo mật của một hệ thống production:

1. Không có secret trong Git, `application.yml` đã commit, Docker image, JAR, manifest hoặc tài liệu hướng dẫn.
2. Chỉ workload có quyền mới lấy được secret; mỗi môi trường dùng bộ secret khác nhau.
3. Khởi động thất bại rõ ràng khi thiếu secret bắt buộc, không tự thay bằng giá trị yếu.
4. Giảm khả năng secret lộ qua log, cấu hình runtime, công cụ debug và bản sao lưu.
5. Có khả năng thu hồi, thay thế secret và khóa ký mà vẫn giữ tương thích trong khoảng chuyển đổi cần thiết.

## 2. Phân biệt biến môi trường, secret store và cách ứng dụng nhận giá trị

**Biến môi trường** là một **cơ chế đưa cấu hình vào tiến trình**. Nó đơn giản, có sẵn ở hầu hết nền tảng, phù hợp cấu hình 12-factor và có thể dùng cho secret trong hệ thống được kiểm soát. Tuy nhiên, nó **không tự mã hóa hay quản trị vòng đời secret**: biến có thể bị lộ qua công cụ debug, crash dump, process inspection theo quyền hệ điều hành, cấu hình CI/CD hoặc các tiến trình con thừa kế môi trường.

**Secret store** là hệ thống lưu trữ/quản lý bí mật và quyền truy cập, chẳng hạn HashiCorp Vault, AWS Secrets Manager, Azure Key Vault hoặc Google Cloud Secret Manager. Một số nền tảng còn dùng Kubernetes Secret để phân phối giá trị đến Pod; Kubernetes Secret có cơ chế quản lý riêng nhưng **giá trị base64 trong manifest không phải là mã hóa bảo mật**.

~~~mermaid
flowchart LR
    Dev["Mã nguồn + application.yml<br/>chỉ chứa tên property"] --> Build["Build JAR / image<br/>không nhúng secret"]
    Store["Secret store<br/>IAM, audit, rotation"] --> Agent["Workload identity / CSI / operator<br/>kiểm tra quyền"]
    Agent --> Runtime["Runtime:<br/>environment hoặc file mount"]
    Build --> App["Spring Boot Authorization Server"]
    Runtime --> App
    App --> Registered["RegisteredClientRepository<br/>client secret được hash"]
    App --> Signer["Signing service/JWKSource<br/>private key được bảo vệ"]
    Signer --> Public["JWKS: chỉ public key"]
~~~

Có ba kiểu triển khai chính:

| Cách cung cấp | Điểm mạnh | Giới hạn cần kiểm soát |
|---|---|---|
| Biến môi trường do runtime inject | Đơn giản với Spring Boot, container, CI/CD | Có thể xuất hiện trong env dump, process snapshot, mô tả deployment; thay đổi thường cần khởi động lại |
| File secret chỉ đọc, gắn vào container/VM | Tránh đưa nội dung vào biến môi trường; có thể áp dụng quyền file | Cần chặn đọc trái phép, quản lý mount, tránh copy file vào image; thay file chưa có nghĩa bean Spring sẽ tự reload |
| Gọi secret store trực tiếp hoặc qua operator/agent | IAM, audit, versioning, rotation tập trung | Tăng phụ thuộc vào quyền truy cập, mạng, API/quota, cơ chế cache và chiến lược khi store mất kết nối |

Một **secret store** và cách **chuyển secret vào tiến trình** là hai quyết định có thể kết hợp: ví dụ secret nằm trong Vault, được agent cấp qua volume; Spring Boot đọc nội dung volume bằng `configtree:`. Lựa chọn triển khai phải phù hợp hạ tầng và rủi ro, không có một cơ chế nào tự đủ an toàn cho mọi môi trường.

## 3. Cấu hình Spring Boot bằng biến môi trường

### 3.1. Chỉ commit placeholder vào `application.yml`

Ví dụ cấu hình nền của **Authorization Server**:

~~~yaml
# src/main/resources/application.yml
app:
  authorization-server:
    issuer: ${AUTH_SERVER_ISSUER}
    client:
      id: ${PORTAL_CLIENT_ID:portal-web}
      secret: ${PORTAL_CLIENT_SECRET}
      redirect-uri: ${PORTAL_REDIRECT_URI}

# Cần import cấu hình bảo mật riêng cho môi trường có secret volume?
# Xem mục 4 để bổ sung spring.config.import.
~~~

`issuer`, `client.id` và `redirect-uri` là cấu hình triển khai thông thường; `client.secret` là giá trị nhạy cảm. Tuy cả bốn đều có thể đưa qua biến môi trường để thay đổi theo local/staging/production, chỉ `PORTAL_CLIENT_SECRET` phải được cấp/quản lý như bí mật. Không đặt default kiểu `dev-secret` cho `PORTAL_CLIENT_SECRET` trong file có thể chạy ở production: thiếu biến cần gây lỗi sớm.

Bảng ánh xạ cho ví dụ:

| Biến runtime | Spring Boot property | Ví dụ giá trị |
|---|---|---|
| `AUTH_SERVER_ISSUER` | `app.authorization-server.issuer` qua placeholder | `https://login.example.vn` |
| `PORTAL_CLIENT_ID` | `app.authorization-server.client.id` | `portal-web` |
| `PORTAL_REDIRECT_URI` | `app.authorization-server.client.redirect-uri` | `https://app.example.vn/login/oauth2/code/portal` |
| `PORTAL_CLIENT_SECRET` | `app.authorization-server.client.secret` | **Không đưa giá trị thật vào tài liệu, log hay Git** |

Ở đây `PORTAL_CLIENT_SECRET` là tên **placeholder được tham chiếu tường minh**, nên không phụ thuộc vào việc suy đoán tên biến môi trường theo relaxed binding. Spring Boot cũng có cơ chế ánh xạ thuộc tính sang biến môi trường theo quy tắc riêng; khi kết hợp nhiều nguồn cấu hình, nên chọn một quy ước và kiểm thử giá trị được bind.

### 3.2. Bind thành đối tượng cấu hình, kiểm tra khi khởi động

Ví dụ Java 17+ dùng `@ConfigurationProperties` và Bean Validation:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.authorization-server")
public record AuthorizationProperties(
        @NotBlank String issuer,
        @Valid @NotNull Client client) {

    public record Client(
            @NotBlank String id,
            @NotBlank String secret,
            @NotBlank String redirectUri) {
    }
}
~~~

Bật binding trong configuration class và dùng giá trị đã được kiểm tra:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

@Configuration
@EnableConfigurationProperties(AuthorizationProperties.class)
class AuthorizationSettingsConfig {

    @Bean
    AuthorizationServerSettings authorizationServerSettings(AuthorizationProperties properties) {
        return AuthorizationServerSettings.builder()
                .issuer(properties.issuer())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            AuthorizationProperties properties,
            PasswordEncoder encoder) {

        AuthorizationProperties.Client client = properties.client();

        RegisteredClient portal = RegisteredClient.withId("portal-web-registration")
                .clientId(client.id())
                // Băm bằng encoder; repository chỉ giữ chuỗi có dạng {bcrypt}...
                .clientSecret(encoder.encode(client.secret()))
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(client.redirectUri())
                .scope(OidcScopes.OPENID)
                .clientSettings(ClientSettings.builder().requireProofKey(true).build())
                .build();

        return new InMemoryRegisteredClientRepository(portal);
    }
}
~~~

**Ranh giới của ví dụ:** Đây là các bean tập trung vào quản lý cấu hình. Một Authorization Server hoạt động còn cần `SecurityFilterChain`, cấu hình đăng nhập, lưu trữ authorization và `JWKSource<SecurityContext>` thích hợp; bật OIDC nếu phát ID Token. `InMemoryRegisteredClientRepository` chỉ phù hợp minh họa/test, không phải kho client bền vững cho production. Dùng starter xác thực cấu hình như `spring-boot-starter-validation` để kích hoạt `@NotBlank` và `@NotNull`.

**Điểm cần hiểu về client secret:**

- Confidential client gửi **secret bản rõ** tới token endpoint qua phương thức xác thực đã đăng ký, trên kết nối TLS.
- Authorization Server đối chiếu với chuỗi **đã băm** trong `RegisteredClient`. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo giá trị mã hóa kèm id thuật toán như `{bcrypt}`.
- Trong production, nên cấp client ban đầu bằng quy trình provisioning và lưu **hash** trong `JdbcRegisteredClientRepository` hoặc repository bền vững tương đương. Khi đó Authorization Server không nhất thiết phải giữ secret bản rõ của client trong môi trường lúc khởi động; client mới là nơi cần giữ bản rõ.
- Secret của confidential client **không** phải private signing key; không dùng client secret làm khóa ký ID Token/JWT theo các thuật toán asymmetric như RS256.
- Nếu đổi `PORTAL_CLIENT_SECRET` và restart bean in-memory ở ví dụ trên, client cần chuyển sang secret tương ứng. Thay biến môi trường của Pod đang chạy thường **không** làm repository tự nhận secret mới.

### 3.3. Chạy local mà không ghi secret vào lịch sử shell

Ví dụ trên Bash khi thử nghiệm cục bộ:

~~~bash
export AUTH_SERVER_ISSUER='http://127.0.0.1:9000'
export PORTAL_REDIRECT_URI='http://127.0.0.1:8080/login/oauth2/code/portal'
export PORTAL_CLIENT_ID='portal-web'

# Gõ secret trực tiếp tại terminal, không đặt nó trong một lệnh đã lưu history.
read -r -s -p 'PORTAL_CLIENT_SECRET: ' PORTAL_CLIENT_SECRET
printf '\n'
export PORTAL_CLIENT_SECRET

# Khởi động theo cơ chế build/run của dự án Spring Boot.
java -jar authorization-server.jar
~~~

Địa chỉ HTTP loopback trong ví dụ **chỉ dành cho local development**; triển khai thực phải dùng HTTPS hợp lệ và đăng ký chính xác redirect URI. Sau khi kiểm thử, đóng shell/phiên hoặc dọn biến môi trường trong phạm vi phù hợp, nhưng đừng xem việc `unset` là biện pháp xóa được mọi bản sao trong bộ nhớ của tiến trình đã khởi chạy.

Đối với file `.env`: Spring Boot **không mặc nhiên** nạp file `.env` theo quy ước của một số công cụ JavaScript. Docker Compose hoặc công cụ khởi chạy có thể đọc file để truyền env. Nếu dùng `.env` local, đưa file vào `.gitignore`, dùng `.env.example` chỉ gồm **tên biến/placeholder**, giới hạn quyền file và không commit secret thật. Không coi `.gitignore` là biện pháp cứu dữ liệu đã từng được commit.

## 4. Cấp secret từ secret store qua file mount và `configtree:`

### 4.1. Một đường triển khai

Một đội vận hành có thể lưu `PORTAL_CLIENT_SECRET` trong Vault/cloud secret manager; operator, CSI driver hoặc agent đã xác thực bằng **workload identity** đọc giá trị đó rồi gắn nó thành file chỉ đọc trong container:

~~~text
/run/secrets/
└── PORTAL_CLIENT_SECRET    # nội dung file = giá trị secret, không chứa tên biến
~~~

Spring Boot hỗ trợ import dạng *configuration tree*, theo đó **tên file là key** và **nội dung file là value**. Bổ sung vào `application.yml`:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"

app:
  authorization-server:
    issuer: ${AUTH_SERVER_ISSUER}
    client:
      id: ${PORTAL_CLIENT_ID:portal-web}
      secret: ${PORTAL_CLIENT_SECRET}
      redirect-uri: ${PORTAL_REDIRECT_URI}
~~~

Với `/run/secrets/PORTAL_CLIENT_SECRET`, placeholder `${PORTAL_CLIENT_SECRET}` có thể được giải quyết từ configuration tree. Ở local, khi thư mục mount không tồn tại, từ khóa `optional:` cho phép bỏ qua nguồn file; lúc đó vẫn cần biến môi trường `PORTAL_CLIENT_SECRET`. Nếu cả hai không cung cấp secret, ứng dụng phải **khởi động thất bại**.

Đối với deployment **chỉ chấp nhận file mount**, có thể dùng `configtree:/run/secrets/` (bỏ `optional:`) để thiếu mount gây lỗi ngay, đồng thời áp dụng kiểm tra secret không rỗng. Khi một key xuất hiện trong nhiều nguồn, thứ tự ưu tiên nguồn cấu hình có thể làm giá trị khác được chọn; cần kiểm thử cấu hình thực tế và tránh để nguồn quyền cao vô tình ghi đè secret.

### 4.2. Minh họa Kubernetes Secret volume

Ví dụ chỉ mô tả **cách gắn một Secret đã được tạo ngoài Git** vào Pod:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: auth-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: auth-server
  template:
    metadata:
      labels:
        app: auth-server
    spec:
      serviceAccountName: auth-server
      containers:
        - name: auth-server
          image: registry.example.vn/auth-server:REPLACE_WITH_PINNED_TAG
          volumeMounts:
            - name: runtime-secrets
              mountPath: /run/secrets
              readOnly: true
          env:
            - name: AUTH_SERVER_ISSUER
              value: "https://login.example.vn"
            - name: PORTAL_REDIRECT_URI
              value: "https://app.example.vn/login/oauth2/code/portal"
      volumes:
        - name: runtime-secrets
          secret:
            secretName: auth-server-runtime
~~~

Secret `auth-server-runtime` cần có **key** `PORTAL_CLIENT_SECRET`, để volume tạo đúng tên file. YAML trên là phần minh họa; một deployment thực phải bổ sung image, port, readiness/liveness, resource limit, RBAC/network policy và cách cấp Secret theo hạ tầng. Không commit manifest `Secret` chứa `data` đã mã hóa base64 rồi coi đó là an toàn: dữ liệu base64 có thể giải mã dễ dàng. Dùng encryption at rest, RBAC tối thiểu, kiểm soát truy cập etcd và pipeline/secret operator phù hợp.

Điểm thực tế: cập nhật Kubernetes Secret có thể làm nội dung **volume** thay đổi sau một khoảng trễ, nhưng Spring Boot bean đã bind configuration và secret đã chuyển thành `RegisteredClient` **không tự thay đổi**. Env var lấy từ Secret thậm chí không cập nhật trong container đang chạy. Cần chiến lược restart/rollout hoặc cơ chế reload được thiết kế và kiểm thử rõ ràng. Với mount dạng `subPath`, việc cập nhật nội dung Secret còn có hạn chế riêng.

### 4.3. Truy cập trực tiếp secret store

Ngoài volume, một ứng dụng có thể dùng SDK hoặc Spring integration phù hợp để đọc secret store lúc khởi động hoặc theo chu kỳ an toàn. Không có một property Spring Boot chung nào tự kết nối mọi Vault/KMS.

Chu trình cần thiết:

1. Workload xác thực bằng **identity do nền tảng cấp** (service account, IAM role, managed identity); hạn chế dùng access key tĩnh để đọc một secret khác.
2. Secret store kiểm tra policy theo môi trường, application và tên secret, ghi audit theo chính sách.
3. Ứng dụng nhận bản secret hiện hành qua TLS, xác minh định dạng và khởi tạo bean/kết nối.
4. Khi xoay vòng, runtime lấy phiên bản mới và chuyển đổi có kiểm soát; không tự động thay từng bean tùy tiện.
5. Khi store không khả dụng, ứng dụng xử lý theo chiến lược đã định nghĩa: startup cần secret phải **fail closed**; với instance đang chạy, dùng cache hiện hành hay ngừng phục vụ tùy thời hạn, rủi ro và yêu cầu vận hành.

Đừng gắn quyền truy cập toàn bộ vault cho mọi Pod. Cần phân tách namespace/path và policy theo ứng dụng, môi trường, chức năng (đọc/ghi/xoay vòng), kiểm soát thay đổi và audit. Dù có TLS, giá trị secret vẫn phải được hạn chế khi vào memory và log của ứng dụng.

## 5. Bí mật đặc biệt của Authorization Server: khóa ký JWT/ID Token

Một Authorization Server phát hành JWT/ID Token ký bằng thuật toán asymmetric cần **private key** để ký và **public key** để công bố. Private signing key có mức ảnh hưởng rộng hơn client secret: nếu bị lộ, kẻ tấn công có thể tạo token giả mạo với `iss` của hệ thống cho đến khi các bên tin cậy ngừng chấp nhận khóa đó.

~~~mermaid
flowchart TB
    KeyStore["Secret store / HSM / encrypted keystore<br/>PRIVATE KEY"] --> Sign["Authorization Server ký JWT/ID Token"]
    Sign --> Token["JWT header: kid=key-v2"]
    KeyStore --> Public["Xuất public JWK tương ứng"]
    Public --> JWKS["JWKS endpoint: /oauth2/jwks"]
    Token --> Verify["Client / Resource Server"]
    JWKS --> Verify
    Verify --> Decision{"Signature, iss, aud,<br/>exp, nbf, scope hợp lệ?"}
    Decision -->|Có| Accept["Chấp nhận theo policy"]
    Decision -->|Không| Reject["Từ chối"]
~~~

**Chú ý về cấu hình khóa ký:**

- Không tạo RSA/EC key pair mới **mỗi lần tiến trình khởi động** trong production. Nếu các pod có private key khác nhau mà không phối hợp public JWKS, token vừa phát có thể không được xác thực ở lần yêu cầu sau.
- Có thể giữ khóa trong HSM/KMS với hoạt động ký từ xa, hoặc cấp tệp keystore/PEM theo secret store và mount quyền đọc tối thiểu. Cách dùng KMS/HSM thực tế phải tương thích cơ chế ký/JWK của stack được chọn.
- Nếu dùng PKCS#12, giữ **keystore file** và **password** trong nguồn bảo mật; chỉ lưu các đường dẫn hoặc tên property như `JWT_KEYSTORE_PATH`, `JWT_KEYSTORE_PASSWORD`, `JWT_KEY_ALIAS` trong cấu hình ứng dụng.
- `JWKSource<SecurityContext>` trong Spring Authorization Server phải hỗ trợ key đang ký và public JWK để endpoint `jwks_uri` trả về các public key phù hợp. Không thêm trường private như `d`, `p`, `q` của RSA vào JWKS công khai.
- Mỗi khóa nên có `kid` ổn định, duy nhất trong phạm vi JWKS; chuyển đổi khóa phải được tổ chức theo thời gian sống của token và cache JWKS.
- Password được dùng để **giải mã/mở khóa** private key không thể thay bằng bản hash một chiều: ứng dụng cần dùng khóa hoặc gọi thiết bị ký. Đây là khác biệt quan trọng với client secret mà Authorization Server chỉ cần **so khớp hash**.

Ví dụ cấu hình mang tính chỉ dẫn cho một hệ thống lưu khóa trong mounted file:

~~~yaml
app:
  signing:
    keystore-path: ${JWT_KEYSTORE_PATH:/run/keys/signing.p12}
    keystore-password: ${JWT_KEYSTORE_PASSWORD}
    key-alias: ${JWT_KEY_ALIAS:key-v1}
    key-password: ${JWT_KEY_PASSWORD}
~~~

Các property `app.signing.*` ở trên là **quy ước do ứng dụng định nghĩa**, không phải property tự động bật ký JWT của Spring Authorization Server. Người triển khai phải tự bind, tải khóa, tạo `JWKSource<SecurityContext>`, kiểm tra thuật toán/kid và cấu hình rotation. Không tải trực tiếp private key từ chuỗi literal trong `application.yml`, không ghi PEM vào stack trace hoặc response.

## 6. Xoay vòng và thu hồi secret theo từng loại

Không áp dụng cùng một kiểu rotation cho mọi bí mật. Bảng dưới chỉ ra cách xử lý phù hợp với vai trò của chúng:

| Loại | Cách thay đổi | Lưu ý ngừng chấp nhận giá trị cũ |
|---|---|---|
| Client secret của confidential client | Cấp secret mới qua kênh bảo mật, cập nhật phía client và hash lưu trên Authorization Server | `RegisteredClient` mặc định chỉ có một `clientSecret`; nếu cần giai đoạn chồng lấp phải thiết kế hỗ trợ rõ ràng (ví dụ migration client registration) thay vì giả định tự chấp nhận hai secret |
| Database/Redis credential | Cấp credential mới, sửa nguồn secret, kiểm tra pool connection và rollout | Ưu tiên mô hình thay credential có overlap trong thời gian chuyển đổi; thu hồi cũ khi toàn bộ instance đã cập nhật |
| Private JWT/ID Token signing key | Công bố public key mới, bắt đầu ký bằng private key mới với `kid` mới, giữ public key cũ tạm thời | Chỉ gỡ public key cũ sau thời gian sống token hợp lệ cộng độ lệch đồng hồ/cache cần thiết; khi khóa bị lộ phải xử lý sự cố và thu hồi sớm hơn |
| Password của keystore | Đổi password/keystore và cập nhật nguồn runtime đồng bộ | Kiểm thử mở được keystore và khả năng ký trước khi chuyển traffic |
| Secret store access credential | Ưu tiên identity ngắn hạn/managed identity; xoay vòng qua nền tảng | Không để credential dài hạn trong repo hoặc image; phát hiện lỗi identity/permission ngay khi deploy |

### 6.1. Ví dụ trình tự rotation khóa ký

~~~mermaid
sequenceDiagram
    autonumber
    participant Ops as Operator / Key manager
    participant AS as Authorization Server
    participant JWKS as JWKS
    participant RS as Resource Server

    Ops->>AS: Cấp key-v2, giữ key-v1
    AS->>JWKS: Công bố public key-v1 + key-v2
    RS->>JWKS: Tải/cập nhật tập public keys
    JWKS-->>RS: keys v1, v2
    Ops->>AS: Chuyển ký token mới sang kid=key-v2
    AS-->>RS: JWT mới có kid=key-v2
    RS->>RS: Xác minh bằng public key-v2
    Note over AS,RS: Chờ token ký key-v1 hết hạn và cache hết thời gian liên quan
    Ops->>JWKS: Gỡ public key-v1 khi an toàn
    Ops->>AS: Vô hiệu/thu hồi private key-v1
~~~

Thời điểm chờ phụ thuộc `exp`, loại token, clock skew cho phép, khả năng cache JWKS và yêu cầu thu hồi. Có thể cần biện pháp khẩn cấp nếu private key bị rò rỉ; lúc đó không nên chỉ chờ token tự hết hạn.

### 6.2. Nguyên tắc rotation cho client secret

Với ví dụ `RegisteredClientRepository` in-memory, thay `PORTAL_CLIENT_SECRET` sau đó rollout sẽ làm các instance nhận secret mới, trong khi instance chưa rollout vẫn có thể nhận secret cũ. Điều này dễ tạo lỗi ngắt quãng ở `/oauth2/token`. Thiết kế rollout phải xét trình tự client/server và thời gian overlap; nếu yêu cầu hai secret hoạt động đồng thời, cần cơ chế đăng ký/xác thực hỗ trợ chính thức hoặc triển khai có kiểm soát.

Trong hệ thống production lưu RegisteredClient tại DB, quy trình cấp secret mới nên cập nhật **hash** ở repository, phân phối bản rõ cho đúng client qua kênh an toàn và ghi nhận phiên bản/thời điểm. Không viết secret bản rõ vào change request, issue tracker hoặc lịch sử migration. Việc đổi một client secret không đồng nghĩa phải xoay vòng khóa ký JWT.

## 7. Phòng tránh rò rỉ trong vòng đời phát triển và vận hành

### 7.1. Trước khi chạy ứng dụng

- **Git và mã nguồn:** không commit `.env` có secret, `application-prod.yml` chứa mật khẩu, PEM private key, `.p12` thật, token mẫu còn hiệu lực hoặc file xuất từ secret manager. Thêm ignore rule cho artifact nhạy cảm và thực hiện secret scanning trong CI. Nếu đã commit, phải thu hồi/xoay vòng secret và xử lý lịch sử theo quy trình; chỉ xóa dòng ở commit mới là chưa đủ.
- **Build pipeline:** không đặt secret trong `ARG` của Dockerfile, lệnh build xuất ra log, test report hoặc layer image. Runtime nhận secret từ cơ chế phân phối riêng. Hạn chế người và hệ thống có quyền xem cấu hình CI/CD.
- **Máy phát triển:** sử dụng secret riêng cho local, quyền tối thiểu, thời hạn ngắn; không sao chép secret production về laptop để chạy nhanh.
- **Môi trường:** tạo secret riêng cho local, staging, production. Đừng dùng cùng private signing key hoặc client secret giữa môi trường.

### 7.2. Khi đang chạy

- **Ứng dụng:** không log toàn bộ `Environment`, `@ConfigurationProperties`, `HttpServletRequest`, header `Authorization`, body token request, token response, keystore bytes hoặc exception chứa secret. Che giá trị trong lỗi và công cụ quan sát, nhưng không dựa duy nhất vào cơ chế mask theo tên key.
- **Spring Boot Actuator:** giới hạn truy cập các endpoint nhạy cảm như `/actuator/env`, `/actuator/configprops`, heap dump và loggers; chỉ expose endpoint thực sự cần, xác thực/phân quyền chặt. Cấu hình hiển thị giá trị chỉ dành cho người có quyền theo chính sách an toàn.
- **Hệ điều hành/container:** bảo vệ volume và quyền đọc file, process inspection, `/proc`, debug shells, crash dumps và quyền chạy lệnh vào Pod. Không đặt secret ở command-line argument vì command line có thể dễ bị quan sát.
- **Mạng:** kết nối secret store, DB, token endpoint bằng TLS; xác minh chứng chỉ và identity. Không chấp nhận bỏ qua TLS validation trong production.
- **Bản sao lưu:** bảo vệ, phân quyền và có thời hạn giữ dữ liệu tương ứng với dữ liệu nhạy cảm bên trong; kiểm soát khả năng phục hồi khi secret bị mất hoặc bị thu hồi.

### 7.3. Khi xảy ra sự cố lộ secret

1. Xác định loại secret, phạm vi truy cập, phiên bản và hệ thống có thể bị ảnh hưởng.
2. Hạn chế đường truy cập đang rò rỉ: tắt token/credential bị lộ, cập nhật quyền store và cô lập nguồn lộ theo kế hoạch ứng phó.
3. Cấp secret mới, cập nhật các bên dùng nó, rollout và kiểm tra xác thực.
4. Nếu lộ private signing key, coi khả năng phát hành token giả là tình huống nghiêm trọng; thay khóa, đánh giá token đang lưu hành và cân nhắc thu hồi/chặn token theo kiến trúc thực tế.
5. Kiểm tra log, image registry, Git history, CI artifact, backup và ticket để tìm bản sao; ghi nhận sự cố mà không chép lại giá trị secret.

## 8. Kiểm thử cấu hình trước khi đưa vào production

Mỗi bài kiểm thử nên chạy trên môi trường cô lập với **secret giả**, không sử dụng secret production. Một ma trận thực tế:

| Tình huống | Kết quả cần quan sát |
|---|---|
| Không có `PORTAL_CLIENT_SECRET` ở env và volume | Startup thất bại có thông báo cấu hình thiếu, **không in secret khác** |
| `PORTAL_CLIENT_SECRET` rỗng | Binding/validation từ chối hoặc có bước fail-fast rõ ràng |
| Có biến env hợp lệ | Bean cấu hình được khởi tạo; client tương ứng xác thực token endpoint bằng secret thử nghiệm |
| Có file `/run/secrets/PORTAL_CLIENT_SECRET` | Spring Boot đọc đúng giá trị từ `configtree:` và không cần đưa secret vào image |
| Thiếu mount bắt buộc khi dùng `configtree:` không có `optional:` | Startup fail-fast thay vì dùng secret mặc định |
| Client cung cấp secret sai | Token endpoint từ chối xác thực client; không phát token |
| Client đã được cấp lại secret | Secret cũ bị từ chối sau thời điểm thu hồi; rollout không có lỗi bất thường |
| Private signing key mới | JWT có `kid` mới được xác minh; token hợp lệ ký bằng khóa cũ vẫn hoạt động trong giai đoạn overlap đã thiết kế |
| Startup sau reverse proxy | `issuer` công khai đúng `https://login.example.vn` trong metadata và claim `iss` |
| Lỗi tải secret store hoặc lỗi quyền đọc file | Hệ thống không khởi chạy bằng credential mặc định; có alert không chứa secret |
| Kiểm tra log/Actuator/dump | Không hiển thị client secret, token, private key hoặc password |

### 8.1. Kiểm tra cấu hình mà không hiển thị giá trị

Có thể kiểm tra **sự hiện diện** của key trong shell mà không in nội dung:

~~~bash
if [ -n "${PORTAL_CLIENT_SECRET:-}" ]; then
  printf 'PORTAL_CLIENT_SECRET: present\n'
else
  printf 'PORTAL_CLIENT_SECRET: missing/empty\n'
fi
~~~

Lệnh chỉ hữu ích cho **đường env**. Với secret file, cần kiểm tra sự tồn tại/quyền đọc/độ dài không rỗng ở cấp ứng dụng hoặc script khởi động mà **không in nội dung**. Không sử dụng `env`, `printenv`, `set` hoặc `cat /run/secrets/...` để chụp cấu hình đưa vào ticket/log. Một secret được cấp đủ không đồng nghĩa đã an toàn: vẫn cần kiểm tra luồng OAuth2 thực tế và kiểm soát quyền.

### 8.2. Các ca kiểm thử luồng OAuth2 nên kết hợp

- Chạy Authorization Code + PKCE với confidential client thật của môi trường test; bảo đảm `redirect_uri` được đăng ký chính xác, `state` khớp và token endpoint yêu cầu client authentication.
- Thay một ký tự trong client secret và xác nhận lỗi kiểu `invalid_client`, không có access token/ID Token được cấp. Không ghi HTTP Basic header hoặc request body có secret vào log.
- Kiểm tra `issuer` trên `/.well-known/openid-configuration` (nếu bật OIDC), `/.well-known/oauth-authorization-server`, rồi so với claim `iss` và cấu hình Resource Server.
- Đọc public JWKS từ `jwks_uri` và xác nhận **không** có thông số private key; token hợp lệ được xác minh đúng `kid`, thuật toán và key.
- Thử trường hợp secret store mất quyền, hết hạn identity hoặc endpoint tạm không khả dụng để xác minh fail-fast/alert/retry đã thiết kế.
- Tập diễn tập rotation trên staging: thời điểm công bố key mới, đổi key ký, làm mới JWKS, retire key cũ và thời điểm client secret chuyển đổi.

## 9. Sai lầm thường gặp và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Commit `client-secret: supersecret` trong YAML | Secret lan vào repository, cache, image hoặc fork | Dùng placeholder, secret store và secret scanning; rotate ngay nếu đã lộ |
| Dùng `{noop}` với secret bản rõ trong RegisteredClient production | Lưu secret dạng dễ đọc và giảm khả năng bảo vệ dữ liệu lưu trữ | Encode bằng `PasswordEncoder` hỗ trợ, lưu hash trong repository bền vững |
| Nghĩ file `.env` luôn được Spring Boot tự đọc | Startup thiếu cấu hình hoặc môi trường bị cấu hình sai | Dùng env thực do launcher cấp, hoặc cấu hình import/integration tường minh |
| Base64 Kubernetes Secret được xem là mã hóa | Người đọc manifest có thể giải mã trực tiếp | Cấp Secret qua hệ quản lý an toàn; bật encryption at rest, RBAC và kiểm soát truy cập |
| Tạo private signing key ngẫu nhiên mỗi lần restart | Token đã phát không còn xác minh nhất quán | Quản lý khóa bền vững, thống nhất trong cluster và có kế hoạch rotation |
| Tắt TLS vì secret đã ở trong Vault | Secret hoặc token có thể lộ trong khi truyền | Dùng TLS và xác thực peer cho toàn bộ đường truyền |
| Cập nhật Secret rồi tin bean Spring đã thay giá trị | Instance cũ tiếp tục dùng credential/key cũ | Thiết kế rollout/reload, kiểm tra ứng xử với pool, repository và JWKSource |
| Bật `/actuator/env` công khai để debug | Tăng rủi ro lộ cấu hình và khả năng dò tìm hệ thống | Hạn chế Actuator, mask và audit truy cập |
| Thay JWT signing key nhưng gỡ public key cũ lập tức | Các JWT hợp lệ còn sống bị từ chối | JWKS overlap và retire theo thời hạn token/cache, trừ sự cố buộc thu hồi khẩn |

## 10. Checklist triển khai cho một Authorization Server mới

- [ ] Phân loại rõ issuer/client ID/redirect URI, client secret, credential hạ tầng, keystore và private signing key.
- [ ] `application.yml` chỉ có cấu hình không nhạy cảm hoặc placeholder; không có credential thật trong Git/build artifact.
- [ ] Mỗi môi trường có secret riêng và workload identity với quyền **đọc đúng secret cần thiết**.
- [ ] Client secret của confidential client được cấp qua kênh an toàn; Authorization Server lưu **hash** trong RegisteredClient repository bền vững.
- [ ] Private signing key được quản lý bền vững trong secret store/keystore/HSM; public JWKS cung cấp đúng key và `kid`.
- [ ] Khi thiếu secret, ứng dụng fail-fast, lỗi/log không tiết lộ giá trị nhạy cảm.
- [ ] Kết nối secret store/DB/token endpoint dùng TLS; hạn chế Actuator, shell, volume và observability.
- [ ] Có kịch bản và bài diễn tập xoay vòng client secret, database credential, JWT signing key.
- [ ] Có kiểm thử OAuth2/OIDC cho cả secret đúng/sai, issuer, metadata, JWKS và trường hợp startup thiếu quyền.
- [ ] Có runbook thu hồi và xử lý secret lộ, gồm audit và đánh giá các bản sao trong repository/log/backup.

**Câu hỏi tự kiểm tra**

1. Vì sao `PORTAL_CLIENT_SECRET` có thể được đưa bằng biến môi trường nhưng biến môi trường tự nó chưa phải secret store?
2. Tại sao phía Authorization Server có thể lưu hash của client secret, trong khi private key ký JWT cần được bảo vệ và vẫn phải dùng để ký?
3. Điều gì xảy ra khi Kubernetes Secret thay đổi nhưng `RegisteredClientRepository` của ứng dụng được tạo một lần lúc startup?
4. Vì sao thay private key ký JWT cần kế hoạch chuyển tiếp public JWKS và `kid`?
5. Cần kiểm tra điều gì để chắc chắn secret không rò qua CI/CD, image, Actuator, log và thông tin debug?

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), gồm `@ConfigurationProperties`, environment variables và configuration trees.
- [Spring Authorization Server — Core Model/Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html), đặc biệt `RegisteredClient` và `RegisteredClientRepository`.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html), đặc biệt `AuthorizationServerSettings` và JWK Set.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [The Twelve-Factor App — Config](https://12factor.net/config).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517) và [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
