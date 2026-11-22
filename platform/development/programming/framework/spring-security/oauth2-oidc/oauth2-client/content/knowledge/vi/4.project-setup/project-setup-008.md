# 4.8. Thiết lập Redirect URI cho local, staging và production

Khi cấu hình **Spring Security OAuth 2.0 / OIDC Client**, một trong những giá trị dễ gây lỗi nhất là **Redirect URI**. Chỉ cần sai giao thức `http/https`, tên miền, cổng, context path hoặc `registrationId`, luồng đăng nhập có thể bị Identity Provider từ chối trước khi ứng dụng nhận được authorization code. Lỗi khác xuất hiện khi ứng dụng nằm sau reverse proxy: trình duyệt truy cập bằng HTTPS công khai nhưng Spring Boot sinh callback có HTTP hoặc hostname nội bộ.

Bài này hướng dẫn thiết lập Redirect URI nhất quán cho ba môi trường **local**, **staging** và **production** bằng cấu hình Spring Boot, Spring Security và đăng ký ứng dụng trên Authorization Server/OpenID Provider (OP).

## 1. Redirect URI nằm ở đâu trong luồng OAuth 2.0 / OIDC?

**Redirect URI** (còn gọi là *callback URI*) là địa chỉ của **client application** mà Authorization Server đưa trình duyệt quay về sau bước xác thực và cấp quyền. Với **Authorization Code Flow**, callback thường nhận tham số `code` và `state`.

Ví dụ người dùng mở:

```text
https://app.example.test/account
```

Ứng dụng chuyển người dùng tới OP:

```text
https://id.example.test/authorize?
  response_type=code&
  client_id=web-prod&
  redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
  scope=openid%20profile&
  state=<random-state>
```

Sau xác thực, OP đưa trình duyệt về:

```text
https://app.example.test/login/oauth2/code/company?code=<authorization-code>&state=<random-state>
```

Ứng dụng Spring Security kiểm tra `state`, dùng authorization code để gọi token endpoint và, với OIDC, xác minh ID token trước khi hoàn tất đăng nhập.

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant App as Spring Boot Client
    participant OP as Authorization Server / OP

    U->>B: Mở /account
    B->>App: GET https://app.example.test/account
    App-->>B: Redirect đến OP /authorize
    B->>OP: response_type=code; redirect_uri=public callback
    OP->>U: Đăng nhập, MFA, consent (nếu cần)
    OP-->>B: Redirect đến app callback với code, state
    B->>App: GET /login/oauth2/code/company?code=...&state=...
    App->>App: Kiểm tra state, authorization request
    App->>OP: Đổi authorization code lấy token
    OP-->>App: Token response
    App->>App: Xác thực OIDC, thiết lập phiên
    App-->>B: Trả về ứng dụng / trang ban đầu
```

### Cần phân biệt ba URL

| URL | Vai trò | Ví dụ |
| --- | --- | --- |
| **Authorization endpoint của OP** | Nơi trình duyệt đi đến để đăng nhập/xin quyền | `https://id.example.test/authorize` |
| **Redirect URI của client** | Nơi OP đưa trình duyệt trở lại với `code` và `state` | `https://app.example.test/login/oauth2/code/company` |
| **Trang đích sau khi login** | Trang mà ứng dụng muốn hiển thị khi login thành công | `https://app.example.test/account` |

**Redirect URI không phải trang chủ hay trang đích sau đăng nhập.** Spring Security xử lý callback ở một endpoint chuyên dụng, sau đó mới chuyển người dùng tới tài nguyên họ đang yêu cầu hoặc success URL được cấu hình.

**OIDC post-logout redirect URI cũng là một loại URI khác.** Nó dùng để đưa người dùng quay về sau quy trình logout tại OP, không thay thế login Redirect URI.

## 2. Quy ước callback mặc định của Spring Security

Với Servlet application dùng `oauth2Login()`, Spring Security thường dùng cặp endpoint mặc định:

| Bước | Mẫu URL |
| --- | --- |
| Khởi động đăng nhập cho một registration | `/oauth2/authorization/{registrationId}` |
| Nhận callback Authorization Code | `/login/oauth2/code/{registrationId}` |

Trong cấu hình client của Spring Boot, thuộc tính quan trọng là:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
```

Trong đó:

- **`{baseUrl}`**: URL gốc mà Spring Security tính từ request hiện tại, thường gồm scheme, host, port và context path.
- **`{registrationId}`**: tên registration trong cấu hình, ở ví dụ này là `company`.
- **`/login/oauth2/code/*`**: đường dẫn callback mà `OAuth2LoginAuthenticationFilter` mặc định xử lý.

Ví dụ khi ứng dụng chạy trực tiếp tại `http://localhost:8080`, URI được tạo là:

```text
http://localhost:8080/login/oauth2/code/company
```

Với public origin `https://app.example.test`:

```text
https://app.example.test/login/oauth2/code/company
```

**Điểm then chốt:** giá trị gửi trong tham số `redirect_uri` của authorization request phải là URI hợp lệ được đăng ký ở OP cho đúng `client_id`. Hầu hết OP yêu cầu khớp chính xác với một entry đã đăng ký theo chính sách của mình. Đừng giả định có thể đổi port hoặc hostname mà không cập nhật phía OP.

## 3. Thiết kế cho local, staging và production

Giả sử ứng dụng cùng dùng `registrationId = company` trên mỗi môi trường, nhưng có **client registration riêng ở Authorization Server** để tách secret, redirect URI và chính sách truy cập.

| Môi trường | Public origin mà trình duyệt sử dụng | Redirect URI cần đăng ký tại OP |
| --- | --- | --- |
| **Local** | `http://localhost:8080` | `http://localhost:8080/login/oauth2/code/company` |
| **Staging** | `https://staging.app.example.test` | `https://staging.app.example.test/login/oauth2/code/company` |
| **Production** | `https://app.example.test` | `https://app.example.test/login/oauth2/code/company` |

Các tên miền `example.test` chỉ phục vụ minh họa; hãy thay bằng địa chỉ triển khai thật.

Một cách sắp xếp trên OP:

```text
Authorization Server / OpenID Provider
├── Client: app-local
│   ├── Client ID: <local-client-id>
│   └── Redirect URI:
│       http://localhost:8080/login/oauth2/code/company
├── Client: app-staging
│   ├── Client ID: <staging-client-id>
│   └── Redirect URI:
│       https://staging.app.example.test/login/oauth2/code/company
└── Client: app-prod
    ├── Client ID: <production-client-id>
    └── Redirect URI:
        https://app.example.test/login/oauth2/code/company
```

Ba client ID ở OP **không bắt buộc phải trùng `registrationId` trong Spring Boot**. `registrationId` là khóa cấu hình nội bộ của ứng dụng; `client-id` là danh tính mà OP cấp cho client. Việc giữ cùng tên `company` trong từng bản triển khai giúp tái sử dụng cấu hình và callback path.

Tách client ID và secret giữa staging/production thường hữu ích vì có thể thu hồi riêng, giới hạn redirect allowlist, scope và quyền của từng môi trường. Nếu OP hỗ trợ realm/tenant riêng, cân nhắc cô lập cả tài khoản thử nghiệm và API staging khỏi dữ liệu production.

### Vì sao nên giữ callback path nhất quán?

Giữ cùng `/login/oauth2/code/company` trên các môi trường giúp:

1. Tránh sửa Java code chỉ vì thay domain hoặc cổng.
2. Dễ đối chiếu một URI đã đăng ký tại OP với URI ứng dụng phát ra.
3. Giữ các SecurityFilterChain và cấu hình OAuth2 Login thống nhất.
4. Làm rõ khác biệt môi trường thực sự nằm ở **public origin**, **client credentials**, **issuer** và hạ tầng proxy.

Tuy nhiên, không buộc mọi môi trường dùng cùng path nếu hạ tầng định tuyến khác nhau. Khi path khác, cả cấu hình Spring Security lẫn allowlist phía OP phải tương ứng.

## 4. Cấu hình chung trong Spring Boot

Ví dụ dành cho **Spring Boot 3.x / Spring Security 6.x**, một web application Servlet đăng nhập bằng OIDC Authorization Code.

### 4.1. `application.yml`: cấu hình dùng chung

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

server:
  port: 8080
```

- **`OIDC_CLIENT_ID`** và **`OIDC_CLIENT_SECRET`** đến từ cấu hình bí mật của đúng môi trường; không commit giá trị thật vào repository.
- **`OIDC_ISSUER_URI`** trỏ tới issuer của OP có hỗ trợ discovery tương ứng; issuer trong token phải khớp những gì client tin cậy.
- **`redirect-uri`** dùng placeholder chuẩn của Spring Security, tránh hardcode localhost vào image/container triển khai.
- **`server.port`** là cổng mà Spring Boot lắng nghe bên trong môi trường chạy. Port công khai có thể là 443 nếu ứng dụng đứng sau reverse proxy.

Tùy tổ chức, có thể đặt client ID/secret/issuer bằng environment variables, secrets manager, Kubernetes Secret, hoặc cơ chế cấu hình tập trung. Điều thiết yếu là **mỗi deployment nhận đúng bộ biến môi trường**, và địa chỉ callback công khai nằm trong allowlist của OP tương ứng.

### 4.2. Cấu hình SecurityFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Khi người dùng truy cập tài nguyên được bảo vệ, Spring Security có thể đưa họ tới trang chọn đăng nhập hoặc bắt đầu authorization flow theo cấu hình. Bạn cũng có thể tạo liên kết:

```html
<a href="/oauth2/authorization/company">Đăng nhập bằng tài khoản công ty</a>
```

Với configuration mặc định, **không cần tự viết controller cho `/login/oauth2/code/company`**. Callback được filter OAuth2 Login xử lý trước khi MVC controller nhận request. Tự khai báo một controller cùng URL thường không giải quyết được lỗi redirect URI và có thể gây nhầm luồng.

## 5. Thiết lập local

Trong môi trường local, một ứng dụng Spring Boot chạy:

```text
http://localhost:8080
```

Có thể đăng ký callback sau vào client `app-local` tại OP:

```text
http://localhost:8080/login/oauth2/code/company
```

Ví dụ khởi động với profile `local` cùng cấu hình biến môi trường phù hợp:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:OIDC_CLIENT_ID = "<local-client-id>"
$env:OIDC_CLIENT_SECRET = "<local-secret>"
$env:OIDC_ISSUER_URI = "https://id-dev.example.test/realms/demo"

./mvnw spring-boot:run
```

Dùng `./gradlew bootRun` nếu dự án sử dụng Gradle; các lệnh trên chỉ minh họa cách khởi chạy, không bắt buộc framework build cụ thể.

**Chi tiết dễ sai khi làm local:**

- `localhost` và `127.0.0.1` là hai hostname khác nhau đối với so khớp Redirect URI.
- `8080` và `8081` là hai cổng khác nhau. Nếu đổi `server.port`, callback cũng đổi.
- `http` và `https` là hai scheme khác nhau.
- `/login/oauth2/code/company` và `/login/oauth2/code/company/` có dấu slash cuối khác nhau.
- Một số OP chỉ cho phép `http` với loopback/localhost trong môi trường phát triển; production phải dùng HTTPS. Quy tắc cụ thể tùy OP.
- Nếu OP chạy trong Docker nhưng người dùng đăng nhập bằng browser ngoài container, **Redirect URI vẫn phải là URL mà browser truy cập được**, không phải hostname Docker nội bộ như `http://spring-app:8080`.

Trường hợp bạn chạy app trong container ánh xạ cổng `-p 8080:8080`, browser vẫn đến `localhost:8080` và callback tương ứng vẫn là localhost. Nếu browser thực tế vào qua domain hoặc port khác, phải lấy URL thực tế ấy làm cơ sở.

### 5.1. Khi local dùng HTTPS

Nếu cấu hình TLS local tại `https://localhost:8443`, hãy đăng ký URI đúng dạng:

```text
https://localhost:8443/login/oauth2/code/company
```

Chứng chỉ local cần được trình duyệt tin cậy để tránh cảnh báo/gián đoạn. Không tắt xác minh TLS một cách tùy tiện trong cấu hình mang sang môi trường thật.

## 6. Thiết lập staging

Staging thường có **domain riêng, HTTPS và proxy/load balancer** phía trước Spring Boot. Ví dụ:

```text
Internet / Browser
    |
    | HTTPS https://staging.app.example.test
    v
Ingress / Reverse Proxy :443
    |
    | HTTP http://spring-app:8080 (mạng nội bộ)
    v
Spring Boot
```

Ở đây phải đăng ký **public URL**:

```text
https://staging.app.example.test/login/oauth2/code/company
```

**Không đăng ký URI nội bộ** như `http://spring-app:8080/login/oauth2/code/company` vì browser không truy cập được, và nó không phản ánh địa chỉ mà người dùng sử dụng.

Staging có thể dùng client ID, secret và issuer thử nghiệm:

```text
OIDC_CLIENT_ID=<staging-client-id>
OIDC_CLIENT_SECRET=<staging-client-secret>
OIDC_ISSUER_URI=https://id-staging.example.test/realms/company
```

Khi dùng placeholder `{baseUrl}`, Spring Security phải biết rằng browser đang dùng HTTPS và hostname công khai mặc dù backend nhận request nội bộ. Điều này liên quan tới **forwarded headers** (mục 8).

## 7. Thiết lập production

Production cần có origin ổn định và HTTPS:

```text
https://app.example.test/login/oauth2/code/company
```

Tại OP, tạo client riêng cho production và khai báo chính xác URI này. Chỉ cấp những scope cần thiết; quản lý client secret bằng hệ thống secrets có kiểm soát quyền truy cập.

Một quy ước triển khai rõ ràng:

| Thông số | Local | Staging | Production |
| --- | --- | --- | --- |
| `SPRING_PROFILES_ACTIVE` | `local` | `staging` | `prod` |
| Public origin | `http://localhost:8080` | `https://staging.app.example.test` | `https://app.example.test` |
| `OIDC_CLIENT_ID` | Client ID local | Client ID staging | Client ID production |
| `OIDC_CLIENT_SECRET` | Secret local nếu cần | Secret staging | Secret production |
| `OIDC_ISSUER_URI` | Issuer local/dev | Issuer staging | Issuer production |
| Redirect URI tại OP | Theo origin local | Theo origin staging | Theo origin production |

Một image ứng dụng có thể được triển khai ở cả ba môi trường với **cấu hình ngoài ứng dụng** khác nhau. Tránh sửa file Java hoặc rebuild image chỉ để thay URL callback.

### Khi nào dùng một client ID chung cho nhiều environment?

Một số OP cho phép liệt kê nhiều Redirect URI cho cùng client ID. Cấu hình đó có thể vận hành được, nhưng tạo ra sự phụ thuộc chung về secret, scope và chính sách giữa các môi trường. **Tách client đăng ký** giúp hạn chế khả năng secret ở staging ảnh hưởng production, giảm nhầm callback và dễ thu hồi độc lập.

Tương tự, nếu staging và production dùng chung OP, vẫn nên dùng client ID/secret và audience/quyền phù hợp; lý tưởng hơn là tách các realm/tenant khi yêu cầu cô lập dữ liệu và danh tính.

## 8. Reverse proxy, ingress và `{baseUrl}`

Đây là nguyên nhân phổ biến của lỗi:

```text
Invalid redirect_uri:
http://spring-app:8080/login/oauth2/code/company
```

Mặc dù người dùng thực tế truy cập:

```text
https://staging.app.example.test
```

### 8.1. Tại sao Spring Boot sinh sai URL?

Reverse proxy nhận HTTPS ở cổng 443 nhưng chuyển tiếp vào backend bằng HTTP trên cổng 8080. Nếu ứng dụng nhìn request nội bộ, nó có thể suy ra:

- Scheme = `http`.
- Host = `spring-app` hoặc hostname service nội bộ.
- Port = `8080`.

Khi `{baseUrl}` mở rộng từ thông tin đó, OP nhận một `redirect_uri` không có trong allowlist hoặc browser không thể truy cập.

### 8.2. Cho Spring xử lý forwarded headers

Với Spring Boot trên Servlet stack, có thể dùng:

```yaml
server:
  forward-headers-strategy: framework
```

Cấu hình này cho framework xử lý các header chuyển tiếp như `Forwarded` hoặc `X-Forwarded-Proto`, `X-Forwarded-Host` và các thông tin phù hợp khác do proxy tin cậy gửi tới. Một số môi trường có thể dùng chiến lược `native` dựa vào servlet container; lựa chọn phụ thuộc hạ tầng và cách container hỗ trợ forwarded headers.

Ví dụ reverse proxy (Nginx) trong trường hợp HTTPS terminate ở proxy:

```nginx
location / {
    proxy_pass http://spring-app:8080;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port 443;
}
```

Ví dụ này giả định proxy chỉ phục vụ HTTPS tại 443 và `spring-app:8080` là upstream nội bộ có thể truy cập được. Cấu hình thực tế cần xét thêm các route và chính sách của ingress.

**Yêu cầu bảo mật:** ứng dụng chỉ nên tin forwarded headers đến từ **reverse proxy do mình kiểm soát**. Proxy cần loại bỏ/ghi đè những header `Forwarded` / `X-Forwarded-*` do client bên ngoài tự gửi, và backend không nên cho phép truy cập trực tiếp từ Internet. Nếu tin header do kẻ tấn công tự khai báo, ứng dụng có thể tạo URL chuyển hướng trỏ tới hostname không mong muốn.

### 8.3. Khi proxy thêm hoặc bỏ prefix

Giả sử URL công khai là:

```text
https://app.example.test/portal/login/oauth2/code/company
```

nhưng backend thực tế nhận:

```text
/login/oauth2/code/company
```

vì proxy bỏ prefix `/portal`. Khi đó cần bảo đảm thông tin public prefix được truyền và diễn giải thống nhất (ví dụ cấu hình `X-Forwarded-Prefix` ở các môi trường hỗ trợ) **hoặc cấu hình Redirect URI công khai một cách tường minh**. Phía OP phải cho phép chính xác URL công khai có `/portal`; proxy phải chuyển request về callback mà Spring Security xử lý được.

Nếu ứng dụng tự cấu hình:

```yaml
server:
  servlet:
    context-path: /portal
```

thì callback phục vụ trực tiếp từ app thường nằm dưới prefix `/portal`. Không nên vừa thêm context path ở backend vừa thêm prefix cùng tên ở proxy mà không xét routing, vì dễ tạo `/portal/portal/...`.

**Quy tắc:** Đăng ký tại OP URL mà **trình duyệt thực sự thấy**; đồng thời bảo đảm URL ấy được định tuyến đến filter callback tương ứng trên ứng dụng.

## 9. Khi nào nên đặt Redirect URI tường minh?

Placeholder `{baseUrl}` phù hợp khi công khai origin của app được proxy chuyển tiếp chính xác. Với hạ tầng phức tạp, bạn có thể dùng một biến môi trường chứa **toàn bộ callback URL**, để không phụ thuộc suy luận host/scheme từ request:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "${OIDC_REDIRECT_URI}"
```

Đặt theo môi trường:

```text
# Local
OIDC_REDIRECT_URI=http://localhost:8080/login/oauth2/code/company

# Staging
OIDC_REDIRECT_URI=https://staging.app.example.test/login/oauth2/code/company

# Production
OIDC_REDIRECT_URI=https://app.example.test/login/oauth2/code/company
```

**Ưu điểm:** callback được xác định rõ và dễ đối chiếu với OP. **Đánh đổi:** khi đổi hostname/port/context path, phải cập nhật cả biến môi trường, routing và redirect allowlist tại OP. Lựa chọn này rất hữu ích nếu public origin cố định, ingress có nhiều lớp hoặc khó bảo đảm forwarded headers đáng tin.

Đừng lấy `redirect_uri` động từ tham số request do người dùng gửi để xây URL callback. Với login OAuth/OIDC, callback phải xuất phát từ cấu hình đã tin cậy hoặc URI được validate nghiêm ngặt, tránh tạo **open redirect** hoặc gửi code/token đến endpoint của kẻ tấn công.

## 10. Tùy chỉnh callback path ngoài mặc định

Một số dự án cần callback:

```text
https://app.example.test/auth/callback/company
```

Khi đó phải điều chỉnh **cả** registration redirect URI **và** endpoint mà Spring Security đón callback.

### 10.1. Đổi cấu hình client

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
```

### 10.2. Đổi endpoint trong SecurityFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class CustomCallbackSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .redirectionEndpoint(redirection -> redirection
                    .baseUri("/auth/callback/*")))
            .build();
    }
}
```

### 10.3. Đăng ký URI mới tại OP

```text
https://app.example.test/auth/callback/company
```

Nếu chỉ đổi `redirect-uri` nhưng **không đổi** `redirectionEndpoint().baseUri(...)`, callback có thể không được filter OAuth2 Login xử lý. Nếu chỉ đổi filter mà không đổi đăng ký tại OP, OP có thể từ chối authorize request vì Redirect URI không nằm trong allowlist.

Hai URL dưới đây là **hai chức năng khác nhau**:

```text
/oauth2/authorization/company  -> BẮT ĐẦU đăng nhập
/auth/callback/company         -> NHẬN CALLBACK đăng nhập
```

Đổi callback không đồng nghĩa bắt buộc đổi URL bắt đầu đăng nhập. `authorizationEndpoint().baseUri(...)` là cấu hình độc lập nếu muốn đổi endpoint khởi động.

## 11. Những sai lệch thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| OP trả `invalid_redirect_uri` hoặc “redirect URI mismatch” | Scheme/host/port/path không trùng allowlist, client ID chọn sai, thiếu prefix | Đối chiếu tham số `redirect_uri` thật trong authorize request với URI đã đăng ký cho đúng client |
| OP thấy `http://spring-app:8080/...` thay vì HTTPS public | Proxy chưa chuyển forwarded headers, hoặc Spring chưa sử dụng chúng | Sửa proxy và `forward-headers-strategy`, hoặc dùng URI tường minh |
| Callback tới 404 | Sai path/context path, ingress route sai hoặc custom filter không khớp | Đối chiếu public URL, rewrite tại proxy và `redirectionEndpoint().baseUri` |
| Browser về callback nhưng login thất bại với `invalid_state` | Mất session/cookie, callback vào instance khác, state bị thay đổi, restart giữa flow | Kiểm tra cookie, session persistence, sticky sessions/distributed session và hostname |
| Callback vào app nhưng Spring không nhận code | Chưa bật `oauth2Login()`, đường dẫn callback không khớp, security chain không áp dụng | Kiểm tra filter chain xử lý request và custom callback |
| Local chạy 8081 nhưng đã đăng ký 8080 | Port đã thay đổi | Đăng ký URI cổng 8081 hoặc đưa app về cổng 8080 |
| `localhost` hoạt động còn `127.0.0.1` không | Host không khớp hoặc chính sách OP khác nhau | Dùng một hostname nhất quán và đăng ký đúng |
| Staging callback redirect về production | Dùng nhầm client ID, secret, issuer hoặc config redirect môi trường | Tách cấu hình/deployment secret và kiểm tra tham số authorize |
| Lỗi loop giữa app và OP sau login | Session không được lưu, cookie Secure/SameSite sai bối cảnh, domain đổi giữa chừng, route yêu cầu login liên tục | Kiểm tra Set-Cookie, callback, security context và proxy |
| OIDC callback thành công nhưng OP không chịu logout redirect | Nhầm login Redirect URI với post-logout Redirect URI | Cấu hình URI logout riêng theo giao thức hỗ trợ |

**Lưu ý về lỗi `invalid_state`:** với mặc định của Servlet OAuth2 Login, authorization request đang chờ thường được lưu theo HTTP session. Nếu callback từ OP không gửi lại cookie phiên, hoặc vào replica không có trạng thái session tương ứng, Spring Security không khớp được yêu cầu gốc. Lúc này sửa duy nhất allowlist Redirect URI sẽ không đủ.

### 11.1. Tình huống: HTTPS public nhưng callback là HTTP

Browser mở `https://staging.app.example.test`, ingress chuyển tiếp bằng HTTP. Trong tab Network, authorize request có:

```text
redirect_uri=http%3A%2F%2Fspring-app%3A8080%2Flogin%2Foauth2%2Fcode%2Fcompany
```

Điều này chứng tỏ URI được ứng dụng dựng từ **địa chỉ backend nội bộ**. Kiểm tra cấu hình proxy, forwarded headers và chiến lược xử lý header trong Spring Boot; có thể dùng `OIDC_REDIRECT_URI` tường minh nếu public origin ổn định.

### 11.2. Tình huống: URI đúng, nhưng callback bị `invalid_state`

Authorization Server trả về:

```text
https://app.example.test/login/oauth2/code/company?code=...&state=...
```

nhưng Spring Security không tìm được authorization request gốc. Khi đó:

1. Kiểm tra cookie phiên trên request đi ra OP và callback quay về app.
2. Xác minh callback trở về **cùng origin/session** chứ không đổi từ `www` sang non-`www` hoặc từ HTTPS sang HTTP.
3. Nếu có nhiều replica, kiểm tra session được chia sẻ hoặc định tuyến nhất quán; không dựa vào memory session của một pod duy nhất khi callback vào pod khác.
4. Với cookie `SameSite`, xem xét kiểu redirect thực tế của OP. OAuth2 code flow trả callback qua top-level GET thường tương thích `Lax`; callback POST/cross-site có yêu cầu cookie khác và phải tính cả rủi ro CSRF.
5. Xác minh tham số `state` được OP trả nguyên vẹn, không bị rewrite/cắt.

Không nên “sửa” `invalid_state` bằng cách bỏ kiểm tra `state`.

### 11.3. Tình huống: callback custom path trả 404

Bạn đặt:

```yaml
redirect-uri: "{baseUrl}/signin/callback/{registrationId}"
```

nhưng không sửa `.oauth2Login(...redirectionEndpoint...)`. Khi callback đến `/signin/callback/company`, filter vẫn đang đợi `/login/oauth2/code/*`. Cập nhật base URI của callback filter và allowlist tại OP theo cùng cấu trúc.

## 12. Cách kiểm tra trước khi đưa môi trường vào sử dụng

Không cần in hoặc lưu authorization code, token hay secret để biết redirect đã cấu hình đúng. Bạn có thể quan sát **URL authorize** trước khi đăng nhập hoàn tất.

### 12.1. Kiểm tra browser Network

1. Mở ứng dụng tại public origin dự kiến của môi trường.
2. Điều hướng tới `/oauth2/authorization/company`.
3. Trong Developer Tools → Network, tìm response redirect đi tới authorization endpoint của OP.
4. Giải mã tham số `redirect_uri` trong URL authorize; so sánh đầy đủ scheme, host, port, path với allowlist OP của đúng client ID.
5. Đăng nhập bằng tài khoản thử nghiệm và xác nhận callback quay về domain mong đợi, rồi ứng dụng thiết lập phiên.
6. Thử một request kế tiếp có xác thực để xác định cookie/session có được duy trì.

**Không copy nguyên URL chứa authorization code hoặc token vào ticket/log chia sẻ**. Khi ghi nhận lỗi, giữ lại chỉ phần callback path, host, loại lỗi và các metadata không nhạy cảm.

### 12.2. Kiểm tra bằng ma trận môi trường

| Kiểm tra | Local | Staging | Production |
| --- | :---: | :---: | :---: |
| App được mở bằng public origin mong đợi | ✓ | ✓ | ✓ |
| OP có callback URI đúng scheme/host/port/path | ✓ | ✓ | ✓ |
| `client-id` thuộc đúng môi trường | ✓ | ✓ | ✓ |
| Authorize request sinh `redirect_uri` đúng | ✓ | ✓ | ✓ |
| Callback được định tuyến đến OAuth2 Login filter | ✓ | ✓ | ✓ |
| `state` và session được khôi phục đúng | ✓ | ✓ | ✓ |
| Forwarded headers đáng tin / URI tường minh | Theo topology | ✓ | ✓ |
| HTTPS và cookie phù hợp với public origin | Theo local | ✓ | ✓ |

Bảng này là hướng dẫn thực hành cho người cấu hình môi trường; các lựa chọn cụ thể cần phù hợp topology và chính sách OP.

## 13. Nguyên tắc bảo mật khi đăng ký Redirect URI

### 13.1. Đăng ký URI cụ thể, tránh wildcard rộng

Một allowlist như:

```text
https://*.example.test/*
```

nếu OP cho phép, có thể mở rộng đáng kể các địa chỉ nhận authorization response. Ưu tiên entry cụ thể:

```text
https://app.example.test/login/oauth2/code/company
```

Không cho phép một hostname không kiểm soát hoặc một path tùy ý nhận code. Nếu OP hỗ trợ redirect pattern, đánh giá chính sách cụ thể của nó; **không coi wildcard là cấu hình mặc định an toàn**.

### 13.2. Giữ HTTPS cho staging/production

Authorization code được trả qua browser redirect. HTTPS giúp bảo vệ đường truyền khỏi nghe lén/sửa đổi. Trường hợp `http://localhost` là ngoại lệ phát triển cục bộ theo chính sách OP; không dùng HTTP public ở production.

### 13.3. Không tạo callback từ tham số do người dùng kiểm soát

Tránh logic kiểu:

```text
redirect_uri = request.queryParameter("returnUrl")
```

vì nếu một kẻ tấn công điều khiển `returnUrl`, ứng dụng có thể yêu cầu OP chuyển code đến đích ngoài dự kiến. Nếu ứng dụng cần đưa người dùng trở lại một trang sau login, dùng SavedRequest/success handler với validation URL đích phù hợp thay vì biến trang đích thành OAuth Redirect URI.

### 13.4. Giữ kiểm tra `state`, OIDC nonce và PKCE

- **`state`** ràng buộc authorization response với request gốc, giúp ngăn CSRF/login injection.
- **OIDC nonce**, khi được sử dụng, giúp ràng buộc ID token với phiên xác thực thích hợp.
- **PKCE** bảo vệ quá trình đổi authorization code bằng `code_verifier`, đặc biệt quan trọng với public clients.

Tất cả là các cơ chế bổ sung; **một Redirect URI chính xác không thay thế được chúng**.

### 13.5. Bảo vệ secret, cookie và session

- Không commit client secret vào Git; cung cấp theo secret management từng môi trường.
- Đặt cookie `Secure` trên HTTPS, `HttpOnly` cho session, chọn `SameSite` theo login flow và chính sách CSRF.
- Tránh log header `Authorization`, token response hoặc nguyên callback query chứa code.
- Với môi trường nhiều replica, triển khai session persistence/routing thích hợp.
- Chỉ chấp nhận forwarded headers từ trusted proxy/ingress.

## 14. Bài thực hành tổng hợp

Giả sử bạn có một Spring Boot application với `registrationId=company`, phát hành bởi một OP chung, được deploy ở ba địa chỉ:

```text
Local      http://localhost:8080
Staging    https://staging.app.example.test
Production https://app.example.test
```

**Yêu cầu:** khi bấm đăng nhập, ở mọi môi trường OP đưa browser về callback chuẩn, Spring Security xử lý code và tạo phiên đăng nhập.

**Bước 1 — Xác định callback và khai báo tại OP:**

```text
Local:
  http://localhost:8080/login/oauth2/code/company

Staging:
  https://staging.app.example.test/login/oauth2/code/company

Production:
  https://app.example.test/login/oauth2/code/company
```

Tạo client riêng theo môi trường, đặt client ID/secret tương ứng.

**Bước 2 — Giữ cùng cấu hình application:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
```

**Bước 3 — Cấp biến môi trường:** cung cấp `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` và `OIDC_ISSUER_URI` đúng deployment, không hardcode secret.

**Bước 4 — Cấu hình proxy:** trên staging/production, công khai HTTPS, bảo vệ forwarded headers và cấu hình `server.forward-headers-strategy` khi cần. Nếu ingress rewrite prefix phức tạp, dùng giá trị `OIDC_REDIRECT_URI` tường minh như mục 9.

**Bước 5 — Quan sát authorization request:** xác nhận tham số `redirect_uri` gửi tới OP khớp **chính xác** callback của từng môi trường. Sau khi xác thực, callback phải được Spring Security xử lý và phiên còn sử dụng được ở request kế tiếp.

### Tự kiểm tra hiểu bài

**Câu 1:** Ứng dụng production chạy trong container cổng 8080, người dùng truy cập qua `https://app.example.test`. Có nên đăng ký `http://container-name:8080/login/oauth2/code/company` tại OP?

> Không. Địa chỉ callback phải là URL công khai browser truy cập được, ở ví dụ là `https://app.example.test/login/oauth2/code/company`. Backend 8080 là chi tiết nội bộ của hạ tầng.

**Câu 2:** Bạn đã thay `redirect-uri` thành `{baseUrl}/custom/callback/{registrationId}` nhưng không đổi SecurityFilterChain. Điều gì xảy ra?

> OP có thể redirect thành công về URL mới, nhưng filter OAuth2 Login mặc định không bắt callback ở đó. Cần cấu hình `redirectionEndpoint().baseUri("/custom/callback/*")` và cập nhật allowlist OP.

**Câu 3:** `http://localhost:8080/login/oauth2/code/company` đã được allowlist, nhưng ứng dụng chạy ở `http://localhost:8081`. Có thể giữ nguyên allowlist không?

> Thông thường không. Cổng là một phần của Redirect URI. Phải đổi cổng ứng dụng về 8080 hoặc đăng ký callback mới ở 8081 theo chính sách OP.

**Câu 4:** Tại sao staging có thể hiện `redirect_uri=http://spring-app:8080/...` dù browser mở URL HTTPS?

> Vì proxy kết thúc HTTPS rồi gửi HTTP vào backend; Spring chưa dùng đúng public scheme/host. Cần cấu hình và tin cậy forwarded headers đúng cách, hoặc dùng Redirect URI tường minh.

**Câu 5:** Callback URL khớp allowlist nhưng login vẫn báo thiếu `state`. Có nên vô hiệu hóa kiểm tra state?

> Không. Hãy kiểm tra callback có cùng session/cookie với authorize request, cấu hình nhiều replica, hostname, cookie policy và proxy routing. Kiểm tra state là cơ chế bảo vệ quan trọng của OAuth/OIDC.

---

## Ghi nhớ

Một cấu hình Redirect URI đúng cần **ba nơi thống nhất**: (1) URL mà Spring Security gửi trong `redirect_uri`, (2) allowlist URI của **đúng client ID** tại Authorization Server, và (3) public route dẫn callback về **đúng filter** của ứng dụng.

Với callback mặc định, công thức thực dụng là:

```text
{public-origin}{context-path}/login/oauth2/code/{registrationId}
```

Local thường dùng `http://localhost:port`; staging và production dùng HTTPS và hostname công khai. Nếu triển khai qua proxy, xử lý forwarded headers từ nguồn đáng tin hoặc cấu hình một Redirect URI tường minh theo môi trường. Khi debug, hãy so sánh **giá trị `redirect_uri` thực sự trong authorize request** trước khi thay đổi code.
