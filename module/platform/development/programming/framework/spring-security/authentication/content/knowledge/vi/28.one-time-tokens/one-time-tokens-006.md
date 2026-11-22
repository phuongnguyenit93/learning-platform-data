# Magic link, URL công khai và giới hạn địa chỉ chuyển hướng

> **Ngữ cảnh:** Spring Security Authentication, nhóm **Token dùng một lần**. Bài học giải thích cách tạo liên kết đăng nhập qua email (magic link), xây dựng URL công khai an toàn khi ứng dụng nằm sau reverse proxy và kiểm soát chuyển hướng sau đăng nhập để tránh lộ token, giả mạo domain và open redirect. Ví dụ áp dụng cho Java 17+, Spring Boot 3.x, Spring Security 6.4–6.5 trên **Servlet stack**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt magic link với password, OAuth access token, TOTP và One-Time Token (OTT) của Spring Security; giải thích vòng đời yêu cầu → sinh token → gửi link → nhập token → đăng nhập.
2. Xây dựng **public base URL** từ cấu hình đáng tin, không từ `Host`, `Forwarded`, `X-Forwarded-Host` hoặc URL do người dùng nhập.
3. Ngăn **Host Header Injection**, gửi magic link tới hostname của kẻ tấn công, lộ token qua redirect và referrer, URL có thông tin xác thực.
4. Chỉ cho phép chuyển hướng tới **đích nội bộ được duyệt**, sử dụng server-side destination key thay vì chuyển trực tiếp `next` hoặc `returnUrl` sang `Location`.
5. Cấu hình `oneTimeTokenLogin()` trong Spring Security 6.5, custom `OneTimeTokenGenerationSuccessHandler` và dịch vụ email an toàn.
6. Thiết kế token có entropy đủ mạnh, TTL ngắn, **single use nguyên tử**, chống đọc quét email tự động, giới hạn rate và tránh lộ danh tính người dùng.
7. Kiểm thử end-to-end cả ứng dụng lẫn reverse proxy khi chạy sau load balancer, CDN hoặc API gateway.

## 2. Magic link thực chất là gì?

**Magic link** là URL có một **bí mật dùng một lần** được gửi tới kênh giao tiếp mà ứng dụng xem là đủ tin cậy để thực hiện đăng nhập, thường là hộp thư email đã được đăng ký và xác minh theo chính sách sản phẩm. Người nắm được link có thể trình bí mật đó cho server để hoàn tất đăng nhập. Đây là một dạng **possession-based authentication**: quyền truy cập vào mailbox hoặc hệ thống giao nhận link trở thành một phần của ranh giới bảo mật.

Ví dụ liên kết có dạng:

```text
https://app.example.org/login/ott?token=b64url_random_secret_example
              ↑                  ↑
        Origin công khai     Bí mật dùng một lần
```

Chuỗi ở ví dụ chỉ để minh họa; **không dùng token cố định hoặc dễ đoán trong production**.

**One-Time Token (OTT)** là giá trị ngẫu nhiên do server cấp, gắn với một danh tính và thời hạn, được tiêu thụ một lần; nó khác **TOTP/HOTP** (one-time password tính toán từ seed/counter/thời gian) và khác **OAuth2 access token** (credential cấp quyền truy cập API theo grant). Magic link là cách **vận chuyển OTT** từ server tới người dùng.

Một request đăng ký link không tự xác thực người gửi; người dùng chỉ được xác thực khi **token hợp lệ được server tiêu thụ và policy tài khoản chấp nhận**. Cũng không phải mọi email đều đáng tin như nhau: nếu mailbox bị chiếm, bị forward, mailbox dùng chung hoặc email chưa được xác minh, magic link có thể trở thành một đường chiếm tài khoản.

### Luồng tổng thể

```text
Trình duyệt của người dùng
   │ 1. POST /ott/generate, nhập username/email
   ▼
Spring Security / ứng dụng
   │ 2. Rate-limit, kiểm tra trạng thái/địa chỉ đã xác minh
   │ 3. Sinh OTT ngẫu nhiên; lưu hash + subject + purpose + expiresAt
   │ 4. Tạo URL từ public origin được cấu hình cố định
   │ 5. Gửi link qua email; trả thông báo trung tính
   ▼
Hộp thư người dùng
   │ 6. Người dùng mở link qua HTTPS
   ▼
GET /login/ott?token=...
   │ 7. Trang tiếp nhận không được tiêu thụ token tùy tiện
   │    bởi email-scanner/link-prefetch
   │ 8. Người dùng chủ động xác nhận, POST token + CSRF
   ▼
OneTimeTokenService.consume(...)
   │ 9. Kiểm tra token chưa hết hạn/chưa dùng/đúng mục đích,
   │    tiêu thụ nguyên tử
   │ 10. Kiểm tra account active, tạo Authentication/session
   ▼
Ứng dụng
   │ 11. Redirect tới một path được chọn từ allowlist
   ▼
/dashboard hoặc /orders (cùng origin tin cậy)
```

Spring Security OTT DSL cung cấp các thành phần tạo/tiêu thụ token và tích hợp login. Các bước gửi email, quản lý contact, URL public, chính sách chống spam/scanner và redirect kinh doanh vẫn cần cấu hình hoặc triển khai phù hợp.

## 3. Hai loại URL tuyệt đối không được nhầm lẫn

### 3.1. Public URL dùng trong email

Đây là địa chỉ mà người nhận **thực sự truy cập từ Internet**. Ví dụ:

```text
https://login.example.org/login/ott?token=...
```

Nó phải lấy từ **cấu hình đáng tin của môi trường triển khai**, ví dụ `app.magic-link.public-origin=https://login.example.org`, được quản trị bởi hệ thống deploy. Nếu chạy sau reverse proxy, hostname nội bộ có thể là `web-07.internal:8080`, trong khi domain công khai là `login.example.org`.

### 3.2. Destination (đích) sau khi login

Đây là **trang hiển thị sau khi token đã được xác thực**, ví dụ `/dashboard` hoặc `/orders`. Đích này là quyết định **điều hướng**, không phải bí mật xác thực. Vì đích có thể đến từ nút UI hoặc tham số `next`, server phải kiểm tra độc lập. Nếu không kiểm soát, kẻ tấn công có thể lợi dụng domain thật để tạo link lừa đảo và đưa người dùng sang website khác.

| Dữ liệu | Ví dụ | Nguồn tin cậy |
|---|---|---|
| Canonical public origin | `https://login.example.org` | Cấu hình server/triển khai đã phê duyệt |
| Token ngẫu nhiên | Base64url của 32 byte SecureRandom | Token service phía server |
| Địa chỉ nhận email | Email đăng nhập đã verified và gắn với local account | Kho user đáng tin |
| Trang sau login | `/dashboard`, `/orders` | Allowlist trên server hoặc mã đích được map trên server |
| `Host`, `X-Forwarded-Host` | Header do network path đưa tới | **Không** mặc định đáng tin để xây URL gửi email |
| `next`, `returnUrl`, `redirect_uri` từ client | `https://evil.example` | **Không** chuyển thẳng vào response `Location` |

**Phân biệt:** OAuth/OIDC `redirect_uri` là URL callback đã đăng ký với IdP, còn magic-link **post-login destination** là trang trong ứng dụng. Cả hai đều cần giới hạn nhưng không dùng cùng một cơ chế kiểm tra đơn giản cho mọi ngữ cảnh.

## 4. Host Header Injection: vì sao không được dựng link từ request?

Mẫu dễ sai:

```java
// KHÔNG dùng trong luồng phát magic link ra email
String root = request.getScheme() + "://" +
              request.getServerName();
String url = root + "/login/ott?token=" + token;
```

Nếu cấu hình reverse proxy không bảo vệ `Host` hoặc header forwarding, một request có thể khiến ứng dụng tưởng hostname là `attacker.example`. Khi ấy email của người dùng thật sẽ nhận một link chứa bí mật login nhưng trỏ đến domain do attacker kiểm soát. Người dùng bấm link, token bị gửi tới kẻ tấn công; attacker có thể dùng lại token ở đúng ứng dụng trước khi hết hạn.

Thậm chí khi request đang qua HTTPS, nếu hostname được chấp nhận từ client thì **HTTPS không ngăn thao túng header**.

### Ví dụ tấn công

```http
POST /ott/generate HTTP/1.1
Host: attacker.example
X-Forwarded-Host: attacker.example
Content-Type: application/x-www-form-urlencoded

username=mai
```

Hệ thống dễ bị tấn công nếu sinh email:

```text
https://attacker.example/login/ott?token=SECRET_FOR_MAI
```

Đường dẫn và token có vẻ hợp lệ nhưng hostname đã bị thay thế. Kết quả cần có khi phòng vệ đúng:

```text
https://login.example.org/login/ott?token=SECRET_FOR_MAI
```

**Cách phòng vệ quan trọng nhất:** không dùng `request.getRequestURL()`, `ServletUriComponentsBuilder.fromCurrentRequest()`, `UrlUtils.buildFullRequestUrl(request)` hoặc hostname rút ra từ `Forwarded`/`X-Forwarded-*` để **quyết định origin trong magic link gửi email** nếu không có trust boundary chặt chẽ. Những API có thể hữu ích ở ngữ cảnh được kiểm soát nhưng không thể tự chứng minh header là đáng tin.

Bên cạnh canonical URL trong ứng dụng, hạ tầng cần:

- Proxy chỉ nhận những `Host` public nằm trong danh sách domain được phục vụ; yêu cầu sai host bị từ chối.
- Proxy **xóa và tự đặt lại** `Forwarded`, `X-Forwarded-Host`, `X-Forwarded-Proto` từ nguồn client không đáng tin; app chỉ nhận metadata forwarding từ proxy được phép.
- Backend không có đường public khác đi vòng qua proxy hoặc làm rò HTTP port nội bộ.
- Không bật tin tưởng tất cả forwarded headers trên một backend có thể bị truy cập trực tiếp.
- TLS certificate, hostname, HSTS và DNS của domain public được vận hành đúng.

Tùy nhu cầu, cấu hình `server.forward-headers-strategy=framework` hoặc tương đương có thể cần để một số redirect/cookie của Spring Boot hoạt động sau proxy, nhưng **nó không thay thế việc cấu hình riêng canonical public origin** cho link chứa token.

### Nhiều domain/tenant thì sao?

Không lấy `tenantDomain` từ query hay `Host` client và ghép link tùy ý. Nên có mapping **tenant ID đã được xác minh ở phía server → canonical HTTPS origin do quản trị viên cấu hình**. Khi phát OTT, chọn domain từ bản ghi tenant của user và issuer/route được cho phép; không cho user gửi một chuỗi domain bất kỳ. Cần kiểm tra domain ownership, tránh subdomain takeover và kiểm soát việc tenant chuyển domain.

## 5. Open redirect: giới hạn địa chỉ chuyển hướng

**Open redirect** xuất hiện khi server lấy trực tiếp URL do người gọi cung cấp làm đích chuyển hướng. Ví dụ sai:

```java
// KHÔNG DÙNG: attacker tự chọn bất kỳ Location nào
response.sendRedirect(request.getParameter("next"));
```

Một đường dẫn gây hiểu nhầm:

```text
https://login.example.org/login/complete?next=https://evil.example/phishing
```

Người dùng thấy domain tin cậy trước, nhưng sau bước đăng nhập có thể bị chuyển tới website giả mạo. Nếu code ghép thêm `token`, email, session ID hoặc các query nhạy cảm vào `next`, open redirect còn làm rò credential. Open redirect đôi khi được dùng để vượt qua allowlist callback của các luồng khác hoặc tạo URL phishing có độ tin cậy giả.

### 5.1. Ưu tiên destination key thay vì nhận URL

Thiết kế dễ kiểm soát nhất: UI chỉ gửi một **mã đích ngắn** như `dashboard` hoặc `orders`; server ánh xạ mã này sang đường dẫn nội bộ:

```text
dashboard  → /dashboard
orders     → /orders
profile    → /account/profile
không hợp lệ → /dashboard
```

Trong lúc tạo token, có thể lưu mã đích đã kiểm tra vào bản ghi intent phía server hoặc session có ràng buộc flow. Sau khi token được tiêu thụ thành công, server lấy lại mã đích đã được duyệt và thực hiện `sendRedirect("/orders")`. Không lấy mã đích mới từ callback rồi thay đổi quyết định mà không kiểm tra.

**Ưu điểm:** không cần tự kiểm tra mọi biểu diễn URL. Các chuỗi `https://evil.example`, `//evil.example`, `%2F%2Fevil.example` hay đường dẫn có backslash, userinfo, control chars sẽ không khớp khóa được phép.

### 5.2. Nếu nghiệp vụ bắt buộc nhận URL

Chỉ cho phép các URL mà ứng dụng thật sự cần; ưu tiên **relative paths trên cùng origin**, giới hạn path prefix/endpoint, hoặc canonical origin có **scheme HTTPS + host chính xác + port phù hợp + không có userinfo**. Parse bằng URI parser, từ chối path bắt đầu `//`, backslash, encoded delimiter nguy hiểm, Unicode/control char, dot-segments bất thường và mọi biến thể khác cho phép đổi host sau khi trình duyệt diễn giải. Chuẩn hóa và so sánh canonical form theo quy tắc an toàn đã kiểm thử. Không dùng các kiểu so sánh chuỗi:

- `url.startsWith("https://login.example.org")`: có thể qua mặt bởi `https://login.example.org.evil.example`.
- `url.contains("example.org")`: chấp nhận domain attacker chứa chuỗi đó.
- Chỉ nhìn prefix `/`: `//evil.example` là **protocol-relative URL**, không phải path nội bộ an toàn.
- Chỉ kiểm tra phía client: server redirect vẫn có thể bị gọi trực tiếp.
- Chỉ kiểm tra khi phát magic link: callback/finish handler có thể bị thay `next` và tạo lỗi sau khi login.

### 5.3. Quyền truy cập sau redirect là kiểm tra riêng

Ngay cả đích nội bộ hợp lệ `/admin` cũng không phải ai đăng nhập cũng được vào. Authorization ở endpoint/service vẫn phải kiểm tra roles/permissions. Redirect allowlist chỉ quyết định điều hướng, không cấp quyền. Tránh truyền token trong URL sau khi đăng nhập, hoặc lưu nó vào `Location` của bước tiếp theo.

## 6. Token dùng một lần phải được sinh và lưu thế nào?

### 6.1. Sinh token đủ entropy

Một lựa chọn phổ biến là lấy **32 byte ngẫu nhiên bằng CSPRNG**, rồi mã hóa Base64url không padding. Đó là khoảng **256 bit entropy** trước mã hóa. Không dùng:

- `Math.random()`, timestamp, sequence ID, username/email để tự dựng token.
- JWT có chữ ký nhưng không có trạng thái single-use rồi gọi là “magic link dùng một lần” khi không kiểm tra `jti`/revocation.
- Token cố định cho demo hoặc token dùng lại mãi; URL có thể bị forward, scan hoặc lộ qua log.

Ví dụ Java 17 để sinh token (đoạn class helper độc lập, phải dùng store phía server khi triển khai):

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class MagicTokenGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    private MagicTokenGenerator() {}

    public static String newToken() {
        byte[] bytes = new byte[32]; // 256 bit
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(bytes);
    }
}
```

**Không in token thật ra log**. Secret trong URL là credential; ai có URL trong thời hạn sử dụng có thể thử đăng nhập.

### 6.2. Lưu hash và metadata cần thiết

Với một token store tự triển khai, nên lưu **SHA-256/HMAC-SHA-256 của token ngẫu nhiên** thay vì token raw, gắn với:

- `user_id`/username nội bộ được xác định từ kho account đáng tin;
- `purpose` chính xác, ví dụ `MAGIC_LOGIN`, không tái sử dụng cùng token cho password reset, đổi email hoặc MFA;
- `expires_at` ngắn (chẳng hạn vài phút theo chính sách), `consumed_at`, `created_at`;
- tham chiếu flow/session, tenant, destination key nếu policy cần;
- thông tin audit an toàn, nhưng tránh lưu toàn bộ URL/token vào logs.

Token raw chỉ dùng để gửi trong email và so khớp ở thời điểm tiêu thụ; ứng dụng tính hash token người dùng nộp rồi truy vấn row. Nếu hệ thống có yêu cầu bảo mật cao và nhiều loại secret, cân nhắc HMAC với key do secret manager quản lý để không công khai pattern hash; với token 256 bit ngẫu nhiên, SHA-256 đã chống đoán brute-force offline trong thực tế, nếu rate-limit và mã hóa truyền dẫn đúng.

### 6.3. Tiêu thụ token nguyên tử

Trong hệ thống nhiều worker/node, phải đảm bảo **hai request cùng token không thể đều thành công**. Bảng PostgreSQL minh họa:

```sql
CREATE TABLE magic_login_tokens (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_hash BYTEA NOT NULL UNIQUE,
    local_user_id BIGINT NOT NULL REFERENCES local_users(id),
    purpose VARCHAR(30) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX magic_login_expiry_idx
    ON magic_login_tokens(expires_at);
```

Sau khi tính `:sha256_of_presented_token` ở backend, một lệnh tiêu thụ có tính nguyên tử:

```sql
UPDATE magic_login_tokens
SET consumed_at = now()
WHERE token_hash = :sha256_of_presented_token
  AND purpose = 'MAGIC_LOGIN'
  AND consumed_at IS NULL
  AND expires_at > now()
RETURNING local_user_id;
```

PostgreSQL chỉ cho một giao dịch cập nhật thành công row chưa tiêu thụ; giao dịch cạnh tranh sẽ thấy điều kiện không còn thỏa mãn. Nếu không có hàng trả về, token sai, hết hạn hoặc đã dùng; client chỉ nhận một lỗi trung tính. Sau đó cần kiểm tra local account vẫn active/được phép login, tạo session an toàn, tránh TOCTOU theo policy. Nếu dùng nhiều dịch vụ/transaction, cần tránh đánh dấu token đã tiêu thụ rồi vẫn trả lỗi mà vô tình sinh session không đồng nhất.

**Không dùng**:

```text
SELECT token WHERE consumed=false
if found:
    grantLogin()
    UPDATE consumed=true
```

Hai request đồng thời đều có thể `SELECT` thành công trước khi cùng `UPDATE`. Redis có thể dùng `GETDEL`/Lua atomic hoặc transaction phù hợp; yêu cầu vẫn là **một lần tiêu thụ được chấp nhận** trên toàn cụm.

### 6.4. Hết hạn và xử lý lỗi

Một link có thể hết hạn trước khi email được giao hoặc người dùng bấm; cho phép **yêu cầu link mới** với rate limit và thông báo rõ, không kéo dài TTL token đã hết hạn. Có thể vô hiệu các token cũ khi phát token mới, tùy chính sách, nhưng cần cân nhắc nhiều tab/device và trải nghiệm.

Nếu user bị disable/locked hoặc địa chỉ nhận mail không còn verified, không để OTT tự bỏ qua account status. Một số version/cấu hình Spring Security OTT có thể cần thêm `UserDetailsChecker`/policy kiểm tra trạng thái tài khoản; không mặc định rằng cung cấp token hợp lệ đã đáp ứng mọi điều kiện nghiệp vụ.

## 7. Spring Security 6.5: sử dụng One-Time Token Login

Spring Security từ dòng 6.4 có DSL `oneTimeTokenLogin()` cho ứng dụng Servlet. Luồng chuẩn:

1. Một POST tới `/ott/generate` (mặc định) yêu cầu token cho username.
2. `OneTimeTokenService.generate(...)` tạo token.
3. `OneTimeTokenGenerationSuccessHandler` tự triển khai **gửi token qua email/SMS**.
4. Link đưa người dùng đến trang submit, mặc định `GET /login/ott?token=...`; trang mặc định điền token vào form.
5. **POST `/login/ott`** xử lý token. Khi CSRF đang bật, form submit cần CSRF token như các POST khác.
6. `OneTimeTokenService.consume(...)` kiểm tra và tiêu thụ token; provider thực hiện authentication; successful login tạo security context/session theo cấu hình.

**Điểm đặc biệt quan trọng:** mặc định **GET** tới trang submit không phải lời hứa rằng có thể tùy tiện login bằng GET; Spring Security 6.5 cấu hình endpoint xử lý **POST**. Email scanners có thể truy cập GET để quét link, vì thế không tự gắn logic consume vào GET của bạn.

### 7.1. Dependency Gradle

Dự án Spring Boot 3.x đã có plugin/BOM phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Cần tự cung cấp `UserDetailsService`/kho user và mail transport (`spring.mail.*` hoặc mail service). Nếu dùng JDBC token store, thêm JDBC/DataSource và cấu hình schema, transaction thích hợp. Spring Security mặc định có `InMemoryOneTimeTokenService` hữu ích khi thử nghiệm **một node**; production nhiều node nên dùng một store chia sẻ có cơ chế consume an toàn (Spring Security có `JdbcOneTimeTokenService` hoặc custom store).

### 7.2. Canonical public origin được cấu hình cố định

`src/main/resources/application.yml`:

```yaml
app:
  magic-link:
    public-origin: ${MAGIC_LINK_PUBLIC_ORIGIN:https://login.example.org}

spring:
  mail:
    host: ${SMTP_HOST:localhost}
    port: ${SMTP_PORT:1025}
```

Trong production, `MAGIC_LINK_PUBLIC_ORIGIN` được quản trị khi deploy; mặc định trên chỉ là ví dụ, phải thay bằng tên miền TLS thực tế. Không cho user đổi origin qua request, header hoặc input email.

### 7.3. SecurityFilterChain cho OTT

`src/main/java/com/example/security/OttSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OttSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            MagicLinkGenerationHandler generationHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/login/ott", "/ott/sent", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(generationHandler));

        return http.build();
    }
}
```

Đây là một class cấu hình trong ứng dụng Spring Boot có `@SpringBootApplication`, database/user repository và mail service, không phải một chương trình chạy được bằng `javac` đơn lẻ. `oneTimeTokenLogin` thêm filters tạo/submit token; việc phát mail được giao cho `generationHandler`. Trước khi triển khai, kiểm tra rõ request matcher, đường login đã tùy biến, CSRF, account status và public pages. **Không tắt toàn bộ CSRF** chỉ để POST `/ott/generate` hoặc `/login/ott` chạy dễ hơn.

Nếu muốn giữ password login song song, `formLogin` có thể hữu ích; nếu sản phẩm chỉ dùng magic link, cần thiết kế trang login và cấu hình phù hợp thay vì sao chép cấu hình hai phương thức mà không chủ đích.

### 7.4. Handler gửi magic link dùng cấu hình origin

Ví dụ triển khai handler **tích hợp Spring Boot**. Nó xây link từ `public-origin` đã xác minh, chỉ gửi tới địa chỉ login đã verified được tra từ kho user; không lấy địa chỉ nhận hoặc domain link từ input trên request.

File `src/main/java/com/example/security/MagicLinkGenerationHandler.java`:

```java
package com.example.security;

import java.io.IOException;
import java.net.URI;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.security.web.authentication.ott.RedirectOneTimeTokenGenerationSuccessHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

@Component
public final class MagicLinkGenerationHandler
        implements OneTimeTokenGenerationSuccessHandler {

    private final JavaMailSender mail;
    private final LoginContactDirectory contacts;
    private final URI publicOrigin;

    private final OneTimeTokenGenerationSuccessHandler sent =
        new RedirectOneTimeTokenGenerationSuccessHandler("/ott/sent");

    public MagicLinkGenerationHandler(
            JavaMailSender mail,
            LoginContactDirectory contacts,
            @Value("${app.magic-link.public-origin}") String origin) {
        this.mail = mail;
        this.contacts = contacts;
        this.publicOrigin = checkedOrigin(origin);
    }

    private static URI checkedOrigin(String configured) {
        URI uri = URI.create(configured);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty())) {
            throw new IllegalArgumentException(
                "Magic-link origin must be HTTPS scheme + host only");
        }
        return uri;
    }

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       OneTimeToken token)
            throws IOException, ServletException {

        // Tra email đăng nhập đã verified từ user store của ứng dụng.
        // Null: không tiết lộ sự tồn tại tài khoản ra client.
        String address = contacts.verifiedLoginEmail(token.getUsername());

        if (address != null) {
            String magicLink = UriComponentsBuilder
                .fromUri(this.publicOrigin)
                .path("/login/ott")
                .queryParam("token", token.getTokenValue())
                .encode()
                .build()
                .toUriString();

            SimpleMailMessage message = new SimpleMailMessage();
            message.setTo(address);
            message.setSubject("Liên kết đăng nhập một lần");
            message.setText(
                "Mở liên kết đăng nhập: " + magicLink +
                "\nNếu bạn không yêu cầu, hãy bỏ qua email này.");

            this.mail.send(message);
        }

        // Trả luồng UI xác nhận đã gửi, không lộ username tồn tại.
        this.sent.handle(request, response, token);
    }
}
```

Thêm contract user repository để class biên dịch khi có implementation thực:

```java
package com.example.security;

public interface LoginContactDirectory {
    // Trả email đã được xác minh cho tài khoản còn đủ điều kiện nhận link.
    // Trả null khi không có địa chỉ hợp lệ.
    String verifiedLoginEmail(String username);
}
```

**Cần tự cung cấp một Spring bean của `LoginContactDirectory`** truy cập user store an toàn; class handler trên có thể biên dịch trong project với dependencies tương ứng nhưng không chạy độc lập nếu thiếu bean, SMTP/IdP hoặc các components Spring Boot. Phải kiểm tra tình trạng tài khoản ở cả thời điểm phát link và lúc consume, đồng thời rate-limit endpoint phát link. Ví dụ không cố thực hiện gửi email thật trong bối cảnh chưa có SMTP được cấu hình.

**Vì sao `checkedOrigin` nghiêm ngặt?** Nó từ chối `http://`, host trống, userinfo kiểu `user@host`, query/fragment và base path tùy ý. Mẫu này chủ ý hỗ trợ origin **không có context path**. Nếu app chạy dưới `/portal`, cần thêm một `public-base-path` riêng được cấu hình, kiểm tra canonical và xây URL với URI builder; không lấy path từ inbound request. Việc kiểm tra giá trị origin phải diễn ra ngay khi khởi động ứng dụng, không đợi gửi email đầu tiên mới phát hiện misconfiguration.

**Không cần sửa các header forwarding để giải quyết riêng việc tạo magic link** vì origin đã từ cấu hình. Nhưng cookie secure, OAuth redirects và URL khác trong ứng dụng vẫn phải được proxy xử lý/kiểm tra riêng.

### 7.5. Điểm cần hoàn thiện cho production

- Khi user không tồn tại, trả cùng thông báo phía UI, quản lý tốc độ response/độ trễ tránh user enumeration; không phát mail tới địa chỉ do requester nhập nếu không thuộc tài khoản đã verified.
- Tùy cơ chế mặc định `OneTimeTokenService` hoặc custom, kiểm soát TTL (mặc định Spring Security 6.5 khoảng **5 phút**, có thể tùy biến `GenerateOneTimeTokenRequestResolver`).
- Sử dụng shared token store cho nhiều instance; đảm bảo single-use nguyên tử và không log giá trị token raw.
- Chặn token dùng sai mục đích, token đã hết hạn, đã revoke, tài khoản bị khóa hoặc đã đổi email nhạy cảm.
- Thực hiện xử lý failure của SMTP/queue theo chính sách để không làm rò user existence hoặc tạo account lockout ngoài ý muốn.
- Không dùng `UriComponentsBuilder.fromCurrentRequest()` để lấy origin từ request attacker, dù ví dụ trong tài liệu framework có thể trình bày cách xây URL từ request vì mục đích minh họa đơn giản.

## 8. Java 17 độc lập: xây magic link và chọn redirect an toàn

Ví dụ sau có thể dùng `javac`/`java` trực tiếp, **không cần Spring**. Nó chỉ minh họa **cách tạo link trên origin cố định và map redirect key**, không tạo OTT ngẫu nhiên, không gửi email hay xác thực người dùng. Token trong `main` là **chuỗi giả định cố định cho demo**, tuyệt đối không dùng làm credential thật.

Lưu `MagicLinkUrlPolicyDemo.java`:

```java
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;

public final class MagicLinkUrlPolicyDemo {

    private static final URI PUBLIC_ORIGIN =
        URI.create("https://login.example.org");

    private static final Map<String, String> DESTINATIONS = Map.of(
        "dashboard", "/dashboard",
        "orders", "/orders",
        "profile", "/account/profile"
    );

    private MagicLinkUrlPolicyDemo() {}

    static String magicLink(String token) {
        if (token == null
                || !token.matches("[A-Za-z0-9_-]{20,256}")) {
            throw new IllegalArgumentException("Invalid token format");
        }
        return PUBLIC_ORIGIN + "/login/ott?token=" +
            URLEncoder.encode(token, StandardCharsets.UTF_8);
    }

    static String redirectPath(String requestedKey) {
        return DESTINATIONS.getOrDefault(requestedKey, "/dashboard");
    }

    public static void main(String[] args) {
        // Chỉ là token minh họa, không có entropy thực.
        String demoToken = "AbCdEf0123456789_XyZabcdefghijklmN";

        System.out.println("Link: " + magicLink(demoToken));
        System.out.println("Allowed: " + redirectPath("orders"));
        System.out.println("External: " +
            redirectPath("https://evil.example"));
        System.out.println("Protocol-relative: " +
            redirectPath("//evil.example"));
        System.out.println("Encoded: " +
            redirectPath("%2F%2Fevil.example"));
    }
}
```

Lệnh:

```bash
javac MagicLinkUrlPolicyDemo.java
java MagicLinkUrlPolicyDemo
```

Stdout chính xác:

```text
Link: https://login.example.org/login/ott?token=AbCdEf0123456789_XyZabcdefghijklmN
Allowed: /orders
External: /dashboard
Protocol-relative: /dashboard
Encoded: /dashboard
```

**Giải thích:**

- `PUBLIC_ORIGIN` là canonical origin cố định, không phụ thuộc `HttpServletRequest`.
- `magicLink` kiểm tra **định dạng** base64url của token; regex **không chứng minh token có entropy hoặc chưa bị sử dụng**. Production phải dùng token CSPRNG từ Spring OTT/service đã phát hành.
- `URLEncoder` mã hóa token an toàn trong query parameter; token ở ví dụ toàn ký tự base64url nên kết quả không đổi.
- `redirectPath` chỉ ánh xạ **key** sang path cố định. Mọi chuỗi lạ, gồm URL ngoài và protocol-relative, đều về `/dashboard`. Ứng dụng vẫn phải áp dụng authorization cho path đã chọn.
- Không tạo URL magic link bằng `PUBLIC_ORIGIN.resolve(userInput)`: URI.resolve có thể chuyển sang origin ngoài nếu input là absolute/protocol-relative. Chỉ ghép **path cố định** với token được mã hóa.

Nếu một session đã đăng nhập mà user muốn vào `/orders`, một server-side redirect handler có thể gọi `response.sendRedirect(redirectPath(destinationKey))`; đây chỉ là minh họa chính sách chọn đích, không phải thay thế các thành phần authentication của Spring Security.

## 9. Magic link rất dễ lộ nếu xử lý URL sai

### 9.1. URL có token là một credential

Khi token nằm trong query, nó có thể xuất hiện ở:

- Browser history, thanh địa chỉ hoặc ảnh chụp màn hình.
- Reverse proxy, access logs, APM, crash report, analytics hoặc tracing tự động.
- Header `Referer` gửi đến tài nguyên bên thứ ba nếu trang chứa link/token tải ảnh, script, font hoặc click external link và không có chính sách referrer bảo vệ.
- Hệ thống email forwarding, anti-spam scanner, link rewriting, máy tính dùng chung.
- Redirect chain nếu code vô tình ghép toàn bộ URL trước đó hoặc query chứa token vào `Location` của bước tiếp.

Với trang `/login/ott`, đặt ít nhất:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
X-Content-Type-Options: nosniff
```

Dùng Content-Security-Policy nghiêm ngặt tương thích giao diện để hạn chế third-party scripts/resources. Trên trang chứa token, tốt nhất không tải analytics bên thứ ba; tránh lộ full URL trong log hoặc telemetry. Mặt khác, `no-referrer` không xóa browser history, proxy logs hoặc email scanners: phải giảm bề mặt lưu token ở mọi lớp.

### 9.2. Người quét link trong email (link prefetch)

Nhiều hệ thống email an toàn tự mở `GET` tới link để kiểm tra malware. Nếu app **tiêu thụ token ngay ở GET**, scanner có thể “đăng nhập” hoặc khiến token mất hiệu lực trước khi người dùng thực sự bấm. Giải pháp thường là:

1. GET chỉ hiển thị trang xác nhận và chứa form nhận token, không tạo session đăng nhập ngay.
2. Người dùng chủ động submit **POST** kèm token và CSRF token đúng chính sách.
3. Server tiêu thụ token nguyên tử rồi mới tạo session; UI không tự auto-submit trên tải trang hay kích hoạt bằng JavaScript của bên thứ ba.
4. Cân nhắc scanner làm thay đổi URL/query, link rewriting hoặc các môi trường mobile khác browser. Không ràng buộc cứng với một browser gốc trừ khi sản phẩm đã thiết kế cơ chế cross-device phù hợp.

Spring Security 6.5 mặc định có trang `GET /login/ott` và endpoint xác thực `POST /login/ott`, nên cần giữ rõ ranh giới này nếu tùy biến UI. Dù scanner không POST trong nhiều trường hợp, không nên giả định mọi scanner chỉ GET; cần threat model và hỗ trợ fallback “yêu cầu link mới”.

### 9.3. Xóa token khỏi UI sau login

Sau khi xác thực và tạo session, redirect đến một path **không chứa token**, ví dụ `/dashboard`; cấu hình session fixation protection, cookie `Secure`, `HttpOnly`, `SameSite` phù hợp và session timeout. Có thể làm sạch URL của trang landing sau khi token đã được chuyển sang flow an toàn, nhưng không để token tồn tại trong client-side storage lâu dài. Không lưu OTT vào `localStorage`, cookie tiện ích hoặc đường dẫn dùng cho history.

## 10. Kiểm thử ứng dụng và reverse proxy

Kiểm thử thực tế phải bao gồm **đường phát email**, **đường mở link** và **đường redirect sau đăng nhập**. Chỉ test Java unit mà không test proxy thì chưa xác minh Host poisoning.

| Ca kiểm thử | Kỳ vọng |
|---|---|
| User hợp lệ yêu cầu token | Email tới địa chỉ đăng nhập đã được xác minh, với URL canonical HTTPS |
| Username không tồn tại | Trả thông báo trung tính, không lộ account tồn tại |
| Request gửi `Host: evil.example` | Email vẫn có origin `https://login.example.org` hoặc request bị gateway từ chối |
| Request gửi `X-Forwarded-Host: evil.example` | Không ảnh hưởng URL trong email; proxy loại bỏ metadata giả |
| Backend chạy `http://web-07.internal:8080` | Email vẫn chứa domain public, không lộ host/port nội bộ |
| Public origin cấu hình `http://` | Fail fast từ lúc boot, không phát link qua HTTP |
| Public origin chứa userinfo, query, fragment hoặc path chưa hỗ trợ | Fail fast, không dùng origin đó |
| Token không tồn tại/hết hạn | Không đăng nhập, cho phép yêu cầu link mới |
| Token đã được dùng một lần | Không thể dùng lần thứ hai |
| Hai request POST cùng token tới hai node | Tối đa một request tiêu thụ thành công |
| User đã bị disabled trước lúc dùng link | Không tạo Authentication/signed-in session |
| Email scanner chỉ truy cập GET | Token không tự bị tiêu thụ |
| POST không có CSRF khi CSRF đang bật | Bị chặn theo chính sách |
| Client yêu cầu `next=https://evil.example` | Không redirect ra ngoài |
| Client yêu cầu `next=//evil.example` | Không redirect ra ngoài |
| Client yêu cầu `next=%2F%2Fevil.example` | Không redirect ra ngoài |
| Client yêu cầu `next=https://login.example.org.evil.example` | Không redirect ra ngoài |
| Client yêu cầu key `orders` | Redirect tới path `/orders` nội bộ đã duyệt |
| User thiếu quyền vào trang đã duyệt | Authorization trả 403/luồng từ chối phù hợp, không cấp quyền |
| Trang login mở external script/analytics | Không được gửi token đầy đủ qua referrer/log |
| Gửi link liên tục theo email/IP | Rate limit/chống spam, không giúp enumerate users |
| Logout rồi phát lại OTT đã dùng | Không đăng nhập; không hồi sinh token |
| Người dùng đổi email verified | Chỉ gửi tới kênh được hệ thống ghi nhận theo chính sách hiện tại |

### Kịch bản tích hợp cần chạy

**Test A — Host Header Injection.** Gửi cùng yêu cầu `/ott/generate` với `Host` công khai, Host lạ, `Forwarded`/`X-Forwarded-Host` giả. Dùng mail catcher trong test để đọc link đã gửi. So sánh **scheme + host + port + path** với canonical public origin được cấu hình; không chỉ kiểm tra chuỗi `contains("example.org")`.

**Test B — Open redirect.** Bắt đầu với một destination key hợp lệ, rồi thử URL ngoài, URL mở đầu bằng `//`, encoded slash, mixed case, tab/newline, query chứa token và URL có `@` userinfo. Sau consume, response `Location` chỉ có path nội bộ được cho phép, không chứa giá trị token. Nếu dùng key map, mọi input lạ phải về path fallback.

**Test C — One-time nguyên tử.** Phát một token trong store dùng chung, cho hai client/worker đồng thời POST nó. Đúng một request được phép dùng token; request kia bị từ chối. Đọc DB để xác nhận `consumed_at` không bị reset, user không có hai session được tạo chỉ từ một token vì race.

**Test D — Scanner và anti-leak.** Mở GET bằng bot giả, xác nhận không có login session; dùng form POST bình thường, kiểm tra CSRF và redirect. Kiểm tra response headers, proxy access log, tracing và JavaScript tracking: không nơi nào ghi raw token.

**Test E — Cross-tenant/đa môi trường.** Dùng staging và production, hai domain hoặc tenant độc lập. Magic link được phát bởi tenant A phải trỏ đúng origin của A, không tiêu thụ ở tenant B và không tạo session/vai trò lẫn tenant.

## 11. Checklist đưa magic link vào production

1. Origin duy nhất được quản trị bằng cấu hình: **HTTPS + host public chính xác**, kiểm tra lúc khởi động; nhiều tenant phải dùng mapping đáng tin.
2. Reverse proxy chặn Host lạ, strip forwarded headers giả và không để backend public bị truy cập trực tiếp.
3. Chỉ phát link đến contact đã xác minh nằm trong user store; phản hồi yêu cầu link không tiết lộ account tồn tại.
4. Dùng token CSPRNG entropy cao, TTL ngắn, purpose cụ thể, lưu hash, transaction/atomic consume và chống replay trên mọi node.
5. Kiểm tra user chưa bị khóa/disable ngay lúc consume; không coi OTT hợp lệ là quyền admin hoặc vượt authorization.
6. GET landing không tiêu thụ token; POST dùng CSRF protection, tạo session/cookie an toàn và xoay session ID đúng lúc đăng nhập.
7. Không dùng `next`, `returnUrl` hoặc `Location` từ raw request; áp dụng mapping destination key → path nội bộ; mọi endpoint vẫn có authorization.
8. Trang token dùng `Referrer-Policy: no-referrer`, `Cache-Control: no-store`; hạn chế third-party resources, URL logging và client storage.
9. Rate-limit/phát hiện abuse cho OTP generation và token submission; theo dõi email delivery, scanner, replay, brute force và anomalous IP.
10. Test end-to-end trên staging qua CDN/load balancer thật, cả Host poisoning, open redirects, multi-node single-use, TTL, account status và token leak.

## 12. Sai lầm thường gặp

| Ngộ nhận / lỗi | Hậu quả | Cách sửa |
|---|---|---|
| “TLS đã có nên tin mọi Host header.” | Attacker kiểm soát origin link gửi email | Lấy origin từ cấu hình server, kiểm soát Host ở proxy |
| “Spring ví dụ xây URL từ request, vậy production cũng đủ an toàn.” | Hỏng trust boundary khi proxy nhận header giả | Dùng canonical public origin đã duyệt; kiểm tra network path |
| “Chỉ cần token khó đoán là đủ.” | Token bị lộ/replay hoặc dùng nhiều lần | TTL ngắn, hash lưu store, single-use atomic, bảo vệ logs/referrer |
| “GET magic link đăng nhập ngay sẽ tiện hơn.” | Email scanner có thể tiêu thụ token | GET landing không consume, POST có xác nhận/CSRF |
| “Redirect về URL client đưa vào là vô hại.” | Open redirect phishing và rò credential | Destination key allowlist trên server |
| “Cho phép URL bắt đầu bằng domain công ty.” | `company.example.evil.example` vẫn qua được | Đối chiếu URI canonical chính xác hoặc key map |
| “Mọi path trong cùng domain đều an toàn.” | Path có thể vượt quyền, chức năng nhạy cảm | Redirect allowlist và authorization từng resource |
| “Xóa link khỏi UI là revoke được token.” | Token trong email/log vẫn có thể dùng | Thu hồi ở token store/consumption state |
| “In-memory token service đủ cho cluster.” | Restart/node khác không tìm thấy/không chặn replay | Shared durable store có atomic consume |
| “Mail tới bất kỳ email requester nhập là được.” | Tạo đường đăng nhập vào contact chưa verified, spam | Chọn email đã xác minh từ user store và rate-limit |

## 13. Tự kiểm tra kiến thức

**Câu 1.** Vì sao không được tạo magic link bằng `request.getServerName()` khi API nằm sau reverse proxy?  
**Đáp án:** Host/forwarded metadata có thể do client tác động khi trust boundary hoặc proxy cấu hình sai. Link có token sẽ bị chuyển sang domain attacker; phải dùng canonical public origin từ cấu hình server.

**Câu 2.** `returnUrl=//evil.example` có phải path nội bộ vì bắt đầu bằng `/` không?  
**Đáp án:** Không. Đây là protocol-relative URL có thể hướng browser tới host bên ngoài. Dùng mã đích cố định map sang path nội bộ hoặc parser và policy nghiêm ngặt.

**Câu 3.** Vì sao token “đã dùng một lần” nhưng code `SELECT` rồi `UPDATE` có thể bị replay?  
**Đáp án:** Hai request cạnh tranh có thể cùng đọc trạng thái chưa dùng trước khi cập nhật. Cần atomic consume ở database/Redis hoặc transaction đúng.

**Câu 4.** Vì sao không nên tiêu thụ token tại GET khi mở email?  
**Đáp án:** Email scanner/link prefetch có thể tự gọi GET trước người dùng. Trang GET nên chỉ hiển thị form, POST mới thực hiện tiêu thụ và tạo session.

**Câu 5.** Chỉ dùng `Referrer-Policy: no-referrer` đã chống mọi rò rỉ magic link chưa?  
**Đáp án:** Chưa. Nó hạn chế referrer; vẫn cần xử lý browser history, proxy logs, analytics, email forwarding, URL redirect chain và bảo vệ mailbox.

**Câu 6.** Nếu khách đã login thành công rồi yêu cầu chuyển hướng tới `/admin` qua một key được duyệt thì sao?  
**Đáp án:** Authorization của `/admin` vẫn phải kiểm tra quyền hiện tại; allowlist đích không trao thêm authorities.

**Câu 7.** Khi dùng `oneTimeTokenLogin()`, phần nào ứng dụng phải tự xây dựng?  
**Đáp án:** Giao nhận token qua email/SMS, chọn email đã verified, canonical URL, rate limit, kiểm soát chuyển hướng, chính sách trạng thái tài khoản, store chia sẻ khi nhiều node và kiểm thử proxy/scanner.

## Tài liệu tham khảo

- [Spring Security 6.5 — One-Time Token Login (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html): DSL, `OneTimeTokenService`, generate/submit endpoint, handler gửi token và mặc định TTL.
- [Spring Security 6.5 — OneTimeTokenLoginConfigurer Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/ott/OneTimeTokenLoginConfigurer.html): `tokenGenerationSuccessHandler`, `loginProcessingUrl`, `tokenGeneratingUrl` và cấu hình OTT.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): token entropy, expire/single-use, tránh Host Header Injection, HTTPS và referrer leak (áp dụng các nguyên tắc tương tự cho magic link).
- [OWASP — Unvalidated Redirects and Forwards](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): open redirect và allowlist destination.
- [Spring Security — Proxy Server Configuration](https://docs.spring.io/spring-security/reference/servlet/appendix/proxy-server.html): xử lý URL/cookie và forwarded headers sau reverse proxy.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): xác thực, user enumeration và bảo vệ luồng login.
