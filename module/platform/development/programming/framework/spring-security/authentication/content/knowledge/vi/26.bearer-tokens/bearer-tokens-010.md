# Thời gian sống, thu hồi token và thay đổi quyền sau khi token đã được cấp

> **Bối cảnh:** Spring Security Authentication, nhóm **Bearer token**, tập trung vào OAuth2 access token dùng cho REST API. Các ví dụ Java hướng đến Java 17+, Spring Boot 3.x và Spring Security 6.x trên Servlet stack. Cơ chế của Authorization Server/Identity Provider (IdP) có thể khác nhau: luôn kiểm tra hợp đồng token, revocation, introspection và chính sách thực tế của nhà cung cấp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc đúng `exp`, `nbf`, `iat`, `jti`, `iss`, `aud` và `scope` trong access token; giải thích vì sao **hết hạn token** không đồng nghĩa **thu hồi token ngay lập tức**.
2. Phân biệt **JWT self-contained** được Resource Server kiểm tra cục bộ với **opaque token** được introspection trên Authorization Server.
3. Thiết kế khả năng thu hồi access token/refresh token sau logout, lộ token, khóa tài khoản hoặc thay đổi quyền.
4. Chứng minh vì sao quyền nằm trong token có thể **cũ hơn quyền hiện tại trong database** và chọn chiến lược kiểm soát theo mức độ nhạy cảm.
5. Cấu hình Spring Security Resource Server để kiểm tra issuer, audience, chữ ký, thời gian và authorities; kết hợp kiểm tra quyền động khi cần.
6. Kiểm thử cả các trường hợp token vẫn chưa hết hạn nhưng **đã bị thu hồi** hoặc người dùng đã bị **giảm quyền**.

## 1. Bearer token là gì và rủi ro khi quyền thay đổi?

Bearer token là credential mà bên giữ token có thể dùng để gọi API theo phạm vi cho phép; nó không tự chứng minh người gọi chính là chủ token bằng một khóa bổ sung. Client thường gửi:

```http
GET /api/reports HTTP/1.1
Host: api.example.org
Authorization: Bearer eyJ...example...
```

Chỉ cần token bị đánh cắp và vẫn có hiệu lực, bên khác có thể phát lại token, trừ khi hệ thống có thêm cơ chế ràng buộc người gửi như mTLS-bound token hoặc DPoP đúng chuẩn. Vì vậy, cần bảo vệ token qua TLS, giới hạn audience/scope và thời gian sống, không ghi token thô vào URL, log hay lỗi trả về client.

Xét tình huống:

- **09:00:** máy chủ phát hành access token có scope `reports:read reports:delete` và `exp` ở **09:15**.
- **09:03:** quản trị viên thu hồi quyền `reports:delete` của người dùng.
- **09:04:** client tiếp tục dùng chính access token cũ gọi `DELETE /api/reports/7`.
- **09:15:** access token mới hết hạn theo `exp`; mốc thực tế có thể chịu ảnh hưởng từ clock skew validator được cấu hình.

Nếu Resource Server chỉ xác minh **JWT chữ ký hợp lệ, `exp` chưa tới và scope trong token**, request lúc 09:04 có thể vẫn được chấp nhận, dù database đã giảm quyền lúc 09:03. Điều này là hệ quả của thiết kế **quyền được chụp lại tại thời điểm token được phát hành**.

**Vấn đề cần giải quyết có hai trục riêng biệt:**

- **Tính hợp lệ của token:** token do issuer tin cậy phát hành? đúng audience? chưa hết hạn? có bị thu hồi không?
- **Quyền hiện tại đối với hành động:** chủ thể còn active? còn quyền truy cập resource/tenant cụ thể không? chính sách thay đổi sau lúc cấp token thế nào?

`Authentication` chỉ trả lời ai hoặc client nào đã được xác thực; authorization hiện tại vẫn cần được đánh giá cho request và tài nguyên cụ thể.

## 2. Các mốc thời gian cần hiểu đúng

Một JWT access token minh họa:

```json
{
  "iss": "https://idp.example.org",
  "sub": "user-42",
  "aud": ["https://api.example.org"],
  "iat": 1767229200,
  "nbf": 1767229200,
  "exp": 1767230100,
  "jti": "access-123456",
  "scope": "reports:read reports:delete",
  "authz_version": 7
}
```

Các số timestamp ở ví dụ chỉ để minh họa cấu trúc; đừng suy luận từ chúng một thời điểm hiện tại hoặc khóa thật.

| Claim | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| `iss` | Issuer phát hành token | Chỉ tin issuer đã cấu hình và đối chiếu chính xác |
| `aud` | Resource Server mà token dành cho | Token phải được cấp cho **API này**, không nhận token cho ứng dụng khác |
| `sub` | Subject theo issuer, thường là user hoặc workload | Định danh phải nằm đúng namespace/tenant; không suy từ email |
| `iat` | Issued at, lúc token được phát hành | Hữu ích cho kiểm tra phiên bản/thu hồi theo thời điểm; không tự nói token còn hợp lệ |
| `nbf` | Not before: thời điểm trước đó token chưa được phép dùng | Từ chối token trước `nbf`, trừ dung sai đồng hồ có kiểm soát |
| `exp` | Expiration time: mốc token hết hiệu lực | Từ chối khi thời điểm xác minh đã tới/vượt `exp` theo validator |
| `jti` | ID riêng của token nếu issuer cấp | Có thể dùng cho denylist; phải namespace theo issuer và đảm bảo chống va chạm |
| `scope` hoặc `scp` | Phạm vi được cấp tại lúc phát hành | Chỉ là một trong các điều kiện authorization; có thể trở nên cũ |
| `authz_version` | Claim **tự định nghĩa**, không phải yêu cầu bắt buộc của JWT/OAuth2 | Chỉ có tác dụng nếu API tra và đối chiếu phiên bản quyền đang có |

Lưu ý: Một access token có thể là JWT hoặc opaque string; các claim `exp`, `scope` bên trong bảng nói về **dạng JWT**, hoặc về metadata trả về từ introspection tương ứng. Không cố giải mã opaque token như JWT.

### Độ dài TTL và clock skew

Giả sử token được cấp lúc `t0` và `exp=t0+900 giây`, thì TTL theo token là **15 phút**. Khi API có dung sai lệch đồng hồ, thực tế có thể tồn tại biên chấp nhận muộn hơn một chút; đây là lý do cần đồng bộ NTP và cấu hình clock skew hợp lý. **Không đặt clock skew rất lớn** để chữa lỗi hạ tầng, vì điều đó vô tình tăng cửa sổ token cũ còn dùng được.

Không đồng nhất:

- **Access token TTL:** thời gian token gọi API hợp lệ.
- **Refresh token TTL:** thời gian credential có thể xin access token mới; thường dài hơn, chịu chính sách lưu trữ/rotation/revocation khác.
- **IdP session:** trạng thái đăng nhập trên hệ thống định danh; logout IdP không bảo đảm các access token đã được phát hành bị vô hiệu lập tức.
- **Session ứng dụng/browser:** có thể có cookie hoặc server-side session riêng; đăng xuất trình duyệt không tự động xóa một JWT đã copy ra ngoài.

`exp` là **giới hạn hết hạn theo thời gian**, không phải danh sách các token bị thu hồi. Một JWT có chữ ký hợp lệ và chưa hết hạn vẫn có thể bị từ chối sớm hơn nếu hệ thống triển khai check revocation hoặc check quyền mới.

## 3. JWT kiểm tra cục bộ và opaque token introspection

### 3.1. JWT access token (self-contained)

Resource Server có thể kiểm tra chữ ký bằng public key/JWK, xác nhận `iss`, `aud`, `exp`, `nbf` và đọc authorities từ claims. Ưu điểm là ít phụ thuộc network vào Authorization Server ở từng request, độ trễ thấp và dễ scale.

```text
Client ── Authorization: Bearer <JWT> ──► API
                                          │
                                          ├─ Verify signature / trusted JWK
                                          ├─ Validate iss, aud, exp, nbf
                                          ├─ Map scopes / authorities
                                          └─ Check application authorization
                                               │
                                               └─ Có thể KHÔNG hỏi IdP ở mỗi request
```

Nếu chỉ làm các bước trên, một JWT cũ có claim `roles=["ADMIN"]` vẫn chứa claim đó sau khi DB đã hạ vai trò. **Authorization Server xóa refresh token không thể tự sửa chữ ký hoặc payload của JWT đã phát hành.**

### 3.2. Opaque token + introspection

Opaque access token thường là chuỗi không mang dữ liệu người dùng có thể đọc trực tiếp. Resource Server gửi token đến introspection endpoint được bảo vệ và dùng câu trả lời của Authorization Server, ví dụ:

```json
{
  "active": true,
  "sub": "user-42",
  "scope": "reports:read",
  "client_id": "web-client",
  "iss": "https://idp.example.org",
  "aud": "https://api.example.org",
  "exp": 1767230100
}
```

Nếu IdP nhận biết việc thu hồi và trả `"active": false`, API từ chối. Tuy vậy **không phải mọi introspection endpoint tự cập nhật role/scope đã cấp**; tùy thiết kế, nó có thể chỉ trả metadata quyền đã cấp trước đây. API vẫn cần kiểm tra quyền hiện tại khi chính sách đòi hỏi.

```text
Client ── Bearer opaque ──► API
                             │
                             └─ POST token → Authorization Server introspection
                                                   │
                                         active=true/false + metadata
                                                   │
                                      API thực hiện authorization
```

**Độ trễ và tính sẵn sàng:** introspection tạo thêm cuộc gọi mạng, phụ thuộc dịch vụ xác thực và timeout. Nếu cache kết quả introspection, hệ thống có thể tiếp tục thấy `active=true` cho đến khi cache hết hạn, dù token vừa bị revoke. Cache chỉ nên sống ngắn, không vượt quá token `exp`; các endpoint đặc biệt nhạy cảm có thể không cache hoặc áp dụng kiểm tra bổ sung.

| Tiêu chí | JWT xác minh cục bộ | Opaque + introspection |
|---|---|---|
| Kiểm tra chữ ký/token mỗi request | Cục bộ qua key tin cậy | Dựa vào AS/introspection endpoint |
| Phụ thuộc AS lúc request | Thường không, nếu key cache sẵn | Thường có, trừ cache introspection |
| Thu hồi access token sớm | Cần denylist, version, live-check, introspection JWT hoặc TTL ngắn | AS có thể trả inactive khi revocation được hỗ trợ |
| Quyền thay đổi | Claim cũ còn tồn tại đến khi token không hợp lệ | Metadata có thể cũng cũ; cần biết hành vi IdP và policy |
| Scale/độ trễ | Thường tốt hơn cho kiểm tra cục bộ | Tăng I/O/latency; cache làm tăng độ trễ cập nhật trạng thái |
| Sự cố AS | JWT đã cấp có thể vẫn xác minh được | Nếu không kiểm tra được, endpoint cần fail closed theo rủi ro |

Không có định dạng nào tự giải quyết hoàn toàn revocation và thay đổi quyền. Lựa chọn là quyết định về **cửa sổ rủi ro, chi phí kết nối, mức độ nhất quán và khả năng kiểm soát**.

## 4. Thu hồi token theo OAuth2 RFC 7009

RFC 7009 định nghĩa **Token Revocation Endpoint**, để client yêu cầu Authorization Server vô hiệu hóa một access hoặc refresh token:

```http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<opaque-or-refresh-token>&token_type_hint=refresh_token
```

Đây là **request minh họa**, tên path và kiểu xác thực client tùy IdP; không gửi token bí mật vào URL hoặc log. Revocation phải dùng HTTPS. RFC 7009 yêu cầu hỗ trợ thu hồi **refresh token**, khuyến nghị hỗ trợ **access token**; tùy chính sách của Authorization Server, thu hồi một token có thể kéo theo token cùng grant.

**Phân biệt kết quả:**

1. Thu hồi **refresh token** giúp ngăn việc dùng credential đó để lấy access token mới. Nó **không bảo đảm** JWT access token cũ đang được API tự kiểm tra offline bị vô hiệu ngay.
2. Thu hồi **access token** ở Authorization Server chỉ được API nhận biết kịp thời nếu API có cơ chế kiểm tra revocation, introspection hoặc shared state phù hợp.
3. Mã HTTP thành công từ revocation endpoint **không chứng minh token từng tồn tại**; theo chuẩn, yêu cầu thu hồi token không hợp lệ cũng có thể trả 200 để tránh dò token.
4. Nếu Authorization Server có nhiều node hoặc vùng địa lý, có thể tồn tại độ trễ đồng bộ; tài liệu và SLO phải nêu rõ.
5. Không dựa vào thao tác xóa token khỏi browser memory để “revoke”; bản sao bị đánh cắp ở máy khác vẫn có thể dùng trong thời gian hiệu lực nếu API không kiểm tra bổ sung.

### 4.1. Refresh token rotation

Với refresh token có rủi ro bị đánh cắp (đặc biệt public clients), nhiều hệ thống sử dụng **rotation**: mỗi lần refresh thành công sẽ cấp refresh token mới và làm cũ token trước. Nếu một token cũ bị dùng lại trái chính sách, Authorization Server có thể phát hiện replay và thu hồi cả token family/grant.

Rotation bảo vệ cửa sổ phát hành token **mới**; nó không tự biến token đã cấp thành vô hiệu ngay trong API. Cần cấu hình IdP thật, xử lý refresh token dùng đồng thời và đặc tính của từng client. Không ép một con số TTL chung cho mọi hệ thống: đánh giá mức độ rủi ro, loại client, UX, thời hạn truy cập và chính sách tổ chức.

### 4.2. Token bị lộ: hành động phải đủ hai phía

Nếu nghi lộ access token:

- Ngăn **token đã lộ** tiếp tục gọi API: revoke/introspect, denylist `jti`/token hash, cập nhật session/version hoặc thay đổi quyền theo cơ chế đang triển khai.
- Ngăn phát hành **token mới** bằng credential đã lộ: thu hồi refresh token, grant/session phù hợp, đổi khóa hoặc tái xác thực khi cần.
- Tìm nguồn rò rỉ: logs, browser storage, proxy, lỗi TLS, URL, monitoring hoặc build artifacts.
- Kiểm tra audit request trong cửa sổ phơi nhiễm và chủ động phục hồi nếu có thao tác không hợp lệ.

Với incident ảnh hưởng nhiều user, thay đổi signing key là biện pháp lớn có thể làm mất hiệu lực nhiều JWT, nhưng chỉ hiệu quả khi tất cả Resource Servers không còn tin key cũ; key rotation thường còn giữ key cũ để xác minh token chưa hết hạn. Không dùng “đổi key” làm giải pháp revoke từng user nếu không có kế hoạch và blast radius.

## 5. Thay đổi quyền sau khi access token đã cấp

**Khác biệt giữa xác thực và ủy quyền:** `JwtAuthenticationToken` được tạo sau khi JWT hợp lệ; các `GrantedAuthority` thường đến từ `scope`/`scp` của token. `hasAuthority("SCOPE_reports:delete")` sẽ dựa trên scope trong token nếu không có cơ chế kiểm tra quyền hiện tại. Nó không tự hỏi database xem người dùng vừa bị thu hồi vai trò hay không.

Có ba loại quyền thường gặp:

1. **Scope OAuth2:** giới hạn grant mà client/token được cấp, ví dụ `reports:read`. Scope là một trần cho các hành động liên quan, không phải một danh sách quyền hiện tại tuyệt đối.
2. **Role/group:** ví dụ `ROLE_MANAGER`, `GROUP_FINANCE`; có thể thay đổi trong IdP hoặc local database sau khi token cấp.
3. **Quyền dữ liệu theo ngữ cảnh:** ví dụ “user-42 được duyệt hóa đơn #815 trong tenant A”, “owner của report #10”. Dù token vẫn có scope thích hợp, quyền truy cập từng tài nguyên cần kiểm tra ở dữ liệu hiện tại.

**Nguyên tắc:** đối với tác vụ nhạy cảm, request phải thỏa cả **token hợp lệ**, **scope tối thiểu**, **tài khoản còn active**, **quyền hiện hành đối với resource/tenant**. Token hợp lệ là điều kiện cần, chưa đủ.

### 5.1. Các phương án đồng bộ/thu hồi

| Cơ chế | Lợi ích | Giới hạn/độ trễ cần đo |
|---|---|---|
| Access token TTL ngắn | Cửa sổ dùng JWT cũ tự kết thúc sớm hơn | Không cho hiệu lực tức thời; tăng nhu cầu refresh |
| Revoke refresh token/grant | Ngăn phát hành access token mới bằng grant cũ | Access token đã cấp có thể vẫn dùng cho tới `exp` |
| Opaque introspection mỗi request | AS có thể trả `active=false` gần thời điểm revoke | Phụ thuộc AS/network; cache có thể giữ trạng thái cũ |
| Denylist token `jti` hoặc hash | Chặn chính xác một số JWT trước `exp` | API phải kiểm tra kho chung; cần TTL cleanup, tránh `jti` collision |
| `authz_version` / `session_version` | Vô hiệu cả nhóm token cũ của user/session khi version tăng | Token phải có claim, API phải tra version hiện tại mỗi request hoặc cache có invalidation |
| `revoked_before` theo `iat` | Chặn token phát hành trước mốc sự kiện | Cần precision/clock chính xác; rủi ro cùng giây và token vừa phát hành |
| Live role/permission lookup | Quyền giảm có hiệu lực khi DB/cache hiện hành phản ánh thay đổi | Tăng I/O, cần xử lý cache/mất kết nối; không giải quyết token bị lộ nếu permission vẫn còn |
| Push event invalidation | Dùng event để cập nhật cache ở nhiều Resource Servers | Event có thể trễ/mất; cần đối soát và cơ chế phục hồi |

Trong hệ thống có dữ liệu nhạy cảm, thường **kết hợp** nhiều lớp: TTL ngắn cho giới hạn tối đa, revocation cho token bị lộ, refresh token rotation, và kiểm tra quyền hiện tại trên các API thao tác quan trọng.

### 5.2. Hai kiểu thay đổi: “giảm quyền” và “thu hồi phiên”

Nếu quản trị viên **giảm role** của user nhưng vẫn cho phép user làm các thao tác ít đặc quyền, kiểm tra permission hiện tại sẽ cho phép những quyền còn lại ngay, còn một chính sách version invalidation có thể buộc user lấy token mới. Cả hai đúng nếu đáp ứng yêu cầu sản phẩm.

Nếu user bị **khóa tài khoản** hoặc nghi session bị chiếm, chỉ kiểm tra role có thể chưa đủ: nên vô hiệu session/token liên quan bằng version, introspection/revoke, denylist hoặc đồng thời các biện pháp khác.

### 5.3. Công thức cửa sổ hiệu lực cũ

Với **JWT kiểm tra cục bộ và chỉ dựa vào `exp`**, thời gian tối đa token cũ còn có thể được chấp nhận sau khi đổi quyền xấp xỉ **TTL còn lại + dung sai đồng hồ phù hợp**. Ví dụ token TTL 15 phút, quyền thay đổi sau 3 phút: còn khoảng 12 phút (ngoài sai lệch clock).

Với **introspection có cache 60 giây**, API có thể tiếp tục dùng kết quả `active=true` từ cache trong phần TTL còn lại; tùy thời điểm cache được ghi, giới hạn chậm cập nhật khoảng thời hạn cache cộng độ trễ propagation, miễn token vẫn hợp lệ. Không nên nêu “thu hồi tức thời” khi cache còn 60 giây.

Với **permission cache** ở từng API node, trạng thái giảm quyền chỉ có hiệu lực khi cache được làm mới hoặc invalidated. Độ trễ cuối cùng là giới hạn từ mọi cache và luồng phân phối chính sách mà đường request đang dùng.

## 6. Spring Security Resource Server: xác minh JWT theo issuer/audience/thời gian

Ví dụ dùng Spring Boot 3.x, Spring Security 6.x, Java 17+. Đây là cấu hình **Resource Server nhận access token**, không phát hành token và không cung cấp revoke endpoint.

### 6.1. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

### 6.2. application.yml

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: https://api.example.org
```

`issuer-uri` để xác minh token từ đúng issuer; `audiences` để kiểm tra token được cấp cho API này. Resource Server tự lấy JWK/metadata theo cơ chế issuer discovery khi điều kiện cấu hình đáp ứng. Hạ tầng phải kết nối được tới endpoint metadata/JWKS hoặc cấu hình `jwk-set-uri` tin cậy tương ứng. Không cấu hình decoder để bỏ kiểm tra chữ ký cho tiện test.

**Mặc định trong Spring Security Resource Server:** JWT được kiểm tra chữ ký và các mốc `exp`/`nbf`, cùng issuer theo `issuer-uri`. Cơ chế xác minh chữ ký phụ thuộc thuật toán tin cậy/khóa phù hợp. Audience chỉ được bảo đảm kiểm tra khi **bạn cấu hình** `audiences` hoặc custom validator tương đương.

### 6.3. SecurityFilterChain nhận bearer JWT

`src/main/java/com/example/security/ResourceServerConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports:read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
```

Đây là lớp cấu hình có thể dùng trong một Spring Boot app với dependency và issuer thật. `SessionCreationPolicy.STATELESS` không dùng HTTP session làm nguồn lưu Authentication; bearer token được xử lý cho từng request. Quy tắc `hasAuthority("SCOPE_reports:read")` mô tả **scope trong token**, chưa đảm bảo user vẫn được phép đọc báo cáo cụ thể ở database.

Để chạy trong dự án Spring Boot có `@SpringBootApplication` và endpoint tương ứng: `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Tạo access token hợp lệ bằng Authorization Server tin cậy; ví dụ không sinh token và không có kết quả HTTP cố định nếu chưa có IdP/keys/endpoint.

**Một số lỗi thường gặp:**

- API nhận **ID Token** của OIDC login thay vì **access token** được cấp cho resource này: phải kiểm tra đúng token type/audience/protocol, không dùng ID Token để gọi API chỉ vì nó là JWT.
- Chỉ giải mã payload bằng Base64 mà bỏ verify chữ ký hoặc tin `alg` không được cho phép: bị token giả mạo.
- Chỉ kiểm tra `exp`, bỏ `iss` và `aud`: có thể nhận token của issuer/client khác.
- Bỏ kiểm tra `scope` hoặc quyền dữ liệu: token hợp lệ nhưng không được thực hiện hành động.

## 7. Spring Security: kiểm tra quyền hiện tại ngoài scope trong token

Giả sử `/api/reports/**` yêu cầu scope `reports:read`, nhưng báo cáo #815 thuộc tenant A và user-42 vừa bị xóa khỏi nhóm có quyền đọc. Chỉ `hasAuthority("SCOPE_reports:read")` vẫn có thể cho qua vì claim trong token chưa đổi.

**Giải pháp:** áp dụng method/request authorization ở tầng nghiệp vụ sử dụng **quyền hiện tại** từ kho dữ liệu. Đoạn thiết kế sau là **mã tích hợp dự án**, phải bổ sung `CurrentPermissionRepository` thực tế và endpoint/service của ứng dụng; không phải ví dụ Java chạy độc lập.

```java
package com.example.security;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("liveReportPermission")
public class LiveReportPermission {

    private final CurrentPermissionRepository repository;

    public LiveReportPermission(CurrentPermissionRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long reportId) {
        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        var jwt = jwtAuth.getToken();
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return false;
        }

        // Có thể cần thêm tenant, owner và trạng thái user hiện tại.
        return repository.isCurrentlyAllowed(
            jwt.getIssuer().toString(), jwt.getSubject(), reportId);
    }
}
```

`CurrentPermissionRepository` ở ví dụ là **interface nghiệp vụ do ứng dụng định nghĩa**, ví dụ:

```java
package com.example.security;

public interface CurrentPermissionRepository {
    boolean isCurrentlyAllowed(
        String issuer, String subject, long reportId);
}
```

Triển khai production phải tra user đang active, tenant, quyền hiện tại của report và chính sách DB, không tin `reportId` là owner. Cần cung cấp một bean của interface này. Từ chối khi không thể kiểm tra quyền cho endpoint nhạy cảm; đừng trả `true` khi cache/DB lỗi.

Bật method security trong cấu hình Spring:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

Imports: `org.springframework.context.annotation.Configuration` và `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`. Sau đó ở **Spring-managed service** (không phải method tự gọi bên trong chính class), dùng:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_reports:read') " +
    "and @liveReportPermission.canRead(authentication, #reportId)"
)
public ReportDetails readReport(
        @P("reportId") long reportId) {
    return repository.loadAuthorizedReport(reportId);
}
```

Đoạn trên minh họa điều kiện bảo mật ở service, cần imports `org.springframework.security.access.prepost.PreAuthorize` và `org.springframework.security.access.method.P`. `ReportDetails`/`repository` là kiểu/bean nghiệp vụ của dự án, nên không thể biên dịch riêng từ snippet. Nếu production dùng repository query gộp permission + dữ liệu, nên kiểm tra trong cùng truy vấn/giao dịch phù hợp để hạn chế TOCTOU; ngoài ra cân nhắc thay đổi quyền xảy ra trong lúc request đang chạy.

**Giải thích:** cùng một JWT còn hạn vẫn cần đi qua `isCurrentlyAllowed` lấy quyền mới nhất. Khi quản trị viên thu hồi quyền, request kế tiếp sẽ bị chặn sau khi source of truth/cache được cập nhật. `scope` trong token vẫn hữu ích như một giới hạn ban đầu, nhưng nó không thay thế authorization động của business.

### Độ nhất quán của kho quyền

Nếu dùng Redis/cache quyền, phải có cache invalidation đáng tin, TTL rõ ràng, quy tắc chống đọc nhầm tenant và chiến lược fail closed. Với API xử lý tiền, quản trị hoặc dữ liệu nhạy cảm, lựa chọn tra DB authoritative hoặc hệ thống policy có SLO revocation ngắn có thể phù hợp hơn cache lâu. Không tải quyền tại thời điểm login rồi giữ trong cache vô hạn.

## 8. Spring Security: dùng opaque introspection khi cần thu hồi tập trung

Nếu Authorization Server hỗ trợ introspection chuẩn RFC 7662, Resource Server có thể dùng opaque access token và kiểm tra trạng thái hoạt động:

`src/main/resources/application.yml` (lựa chọn **thay cho cấu hình JWT** ở mục 6.2, không trộn hai phần trong cùng một Resource Server demo):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Trong SecurityFilterChain, thay phần `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` bằng:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

`Customizer` như import ở ví dụ JWT. Introspection endpoint và credentials phải được cấu hình an toàn qua môi trường/secret manager, TLS, timeout; mỗi lần kiểm tra cần phân biệt `active=true` và `active=false`. Không tự suy luận token hợp lệ chỉ vì endpoint trả HTTP 200: **nội dung introspection** mới nói token còn active hay không.

Spring Security mặc định ánh xạ `scope` từ introspection thành authorities `SCOPE_...`. Introspection server cần xác thực Resource Server và hạn chế dữ liệu trả về. Nếu có cache response ở client hoặc trung gian, cần định nghĩa độ trễ thu hồi thực tế và thời gian sống cache ngắn hơn thời hạn token.

Không có gì ngăn Resource Server dùng **JWT nhưng vẫn introspect** hoặc kiểm tra store thu hồi riêng. Đây là lựa chọn kiến trúc, cần bổ sung custom validation/introspection thực tế. Nếu request không thể xác nhận token đang active trên tuyến bắt buộc phải introspect, nên từ chối thay vì lặng lẽ chấp nhận mọi token.

## 9. Mô hình kiểm tra revocation và phiên bản quyền

Các hệ thống cần vô hiệu token đã cấp trước khi `exp` có thể dùng:

### 9.1. Denylist theo token ID

Authorization Server phát JWT có `jti` riêng. Khi revoke, lưu khóa `(issuer, jti)` hoặc hash được tính an toàn của token vào Redis/shared store. Resource Server phải kiểm tra denylist trong bước xử lý mỗi token/request; nếu match thì từ chối.

- Đặt TTL denylist đến `exp` cộng dung sai cần thiết; tránh bảng tăng vô hạn.
- Phân biệt issuer và namespace để tránh `jti` trùng từ các issuer khác.
- Nếu mọi token không có `jti` thì phải quy định cách nhận diện an toàn khác hoặc từ chối token không đáp ứng chính sách.
- Đừng để denylist chỉ nằm trong local memory của một node khi các node còn lại vẫn cho token qua.
- Nếu cache kết quả “token không bị revoke”, nó có thể gây trễ phản ánh denylist; cần invalidate hoặc đặt TTL phù hợp.

### 9.2. Phiên bản quyền / phiên bản session

Khi cấp token, Authorization Server nhúng claim nội bộ `authz_version=7` hoặc `session_version=3`. Kho quyền/current state lưu phiên bản mới nhất. Khi user bị hạ quyền hoặc khóa session, tăng version lên 8 hoặc 4. Resource Server đối chiếu claim với trạng thái hiện tại và từ chối token có version không khớp.

- Với **authz_version**, thay đổi toàn bộ vai trò có thể làm mọi token cũ của người dùng bị từ chối; user cần token mới sau khi policy đã cập nhật.
- Với **session_version**, có thể thu hồi toàn bộ các token của một session/thiết bị, nếu token và kho dữ liệu có định danh session an toàn.
- Nếu có nhiều issuer/tenant, namespace khóa version theo issuer, subject/tenant/client phù hợp.
- **Chỉ thêm claim vào JWT chưa đủ**: API phải thực hiện lookup/compare; nếu không, version cũ vẫn nằm trong JWT hợp lệ và không bị kiểm tra.
- Đừng chỉ dựa vào so sánh `iat >= revoked_before` khi đồng hồ, làm tròn giây, clock skew hoặc cấp token đồng thời có thể tạo khoảng trống; version nguyên tăng đơn điệu dễ kiểm soát hơn cho nhiều trường hợp.

### 9.3. Điểm đặt kiểm tra

Có thể kiểm tra version/denylist trong custom `OAuth2TokenValidator<Jwt>` gắn với `JwtDecoder`, trong một `AuthenticationProvider`/authorization component thích hợp, hoặc ở policy layer; quyết định cần làm rõ token bị coi là **không hợp lệ (401)** hay còn hợp lệ nhưng **thiếu quyền (403)**. Nếu bị revoke, thường nên xử lý như credential không hợp lệ trước khi cấp Authentication. Nếu chỉ thiếu quyền với token còn hợp lệ, HTTP 403 hợp lý hơn.

Không chỉ thêm filter chạy sau controller hoặc một thao tác check chỉ ở màn hình login; người gọi API có thể dùng token mà không đi qua UI.

## 10. Java 17: mô phỏng thời gian sống, revoke và thay đổi quyền

Chương trình độc lập dưới đây minh họa **kiểm tra trạng thái** đối với một token giả định đã được xác thực chữ ký. Nó không tạo JWT thật, không thay thế Spring Security và không mô phỏng server phân tán. Lưu file `BearerTokenPolicyDemo.java`:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class BearerTokenPolicyDemo {

    record Token(
        String subject,
        String tokenId,
        long permissionVersion,
        Instant notBefore,
        Instant expiresAt
    ) {}

    static boolean accepted(
        Token token,
        Instant now,
        Map<String, Long> currentVersions,
        Set<String> revokedIds
    ) {
        return !now.isBefore(token.notBefore())
            && now.isBefore(token.expiresAt())
            && !revokedIds.contains(token.tokenId())
            && token.permissionVersion()
                == currentVersions.getOrDefault(token.subject(), -1L);
    }

    public static void main(String[] args) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        Map<String, Long> versions = new HashMap<>();
        Set<String> revokedIds = new HashSet<>();
        versions.put("user-42", 1L);

        Token original = new Token(
            "user-42", "jti-old", 1L, issued, issued.plusSeconds(300));

        System.out.println("Initially: " +
            accepted(original, issued.plusSeconds(10), versions, revokedIds));

        // User bị giảm quyền: phiên bản thay đổi ngay ở kho dữ liệu.
        versions.put("user-42", 2L);
        System.out.println("After permission change: " +
            accepted(original, issued.plusSeconds(20), versions, revokedIds));

        Token refreshed = new Token(
            "user-42", "jti-new", 2L, issued, issued.plusSeconds(300));

        System.out.println("New token: " +
            accepted(refreshed, issued.plusSeconds(30), versions, revokedIds));

        revokedIds.add("jti-new");
        System.out.println("After revocation: " +
            accepted(refreshed, issued.plusSeconds(40), versions, revokedIds));

        System.out.println("At expiry: " +
            accepted(original, issued.plusSeconds(300), versions, revokedIds));
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac BearerTokenPolicyDemo.java
java BearerTokenPolicyDemo
```

Stdout chính xác:

```text
Initially: true
After permission change: false
New token: true
After revocation: false
At expiry: false
```

**Tại sao ví dụ có ích?** Khi tăng `permissionVersion`, token cũ không còn pass ngay cả khi chưa tới `expiresAt`. Khi thêm token mới vào danh sách thu hồi, nó bị từ chối ngay trước `exp`. Tại `exp`, token không còn hợp lệ theo điều kiện `now.isBefore(expiresAt)`.

**Giới hạn của demo:** `HashMap`/`HashSet` chỉ là bộ nhớ của một JVM, không chịu được restart hay chạy nhiều node; app thật dùng distributed store/database đáng tin. `Token` trong demo là dữ liệu đã được giả định xác thực; production phải **xác minh signature/issuer/audience** bằng Spring Security trước khi dùng chính sách. Demo cũng không xử lý đa issuer, clock skew hay refresh token; không tự copy logic này thành validator JWT trực tiếp nếu chưa có đầy đủ các điều kiện đó.

## 11. HTTP 401/403 và hành vi client khi token không hợp lệ

| Tình huống | Quyết định chính | Phản hồi kỳ vọng trong API đúng chuẩn |
|---|---|---|
| Không có bearer token trên endpoint yêu cầu auth | Chưa xác thực | 401 (challenge) |
| Token giả mạo, sai chữ ký/`iss`/`aud` | Credential không hợp lệ | 401 |
| Token hết `exp`, trước `nbf` | Credential không hợp lệ về thời gian | 401 |
| Token bị revoke/không active | Credential không còn hợp lệ | 401 |
| Token hợp lệ nhưng thiếu `reports:read` | Không đủ scope/quyền | 403, có thể chỉ rõ `insufficient_scope` theo RFC 6750 |
| Token hợp lệ, scope đúng nhưng DB đã hạ quyền trên report #815 | Không còn quyền dữ liệu hiện tại | 403 |
| Introspection bắt buộc nhưng AS timeout | Không thể xác minh token | Fail closed; lỗi HTTP cụ thể (401/503) do chính sách và error handler, không chấp nhận token |
| Refresh token bị revoke | Không thể dùng grant đó để cấp token mới | Thường yêu cầu user xác thực lại; response phụ thuộc token endpoint |

Không lập trình client tự động retry vô hạn khi 401 vì token bị revoke; refresh một lần có kiểm soát nếu grant còn hiệu lực, xử lý `invalid_grant` và hướng người dùng đăng nhập lại khi phù hợp. Không nhầm 403 thiếu quyền với 401 cần refresh; refresh liên tục cũng không tự tạo lại quyền đã bị quản trị viên thu hồi.

## 12. Kiểm thử hành vi theo vòng đời token

### 12.1. Test tối thiểu cho JWT validation

- Token hợp lệ và còn hạn, đúng issuer/audience/scope: có thể vào endpoint tương ứng nếu các business permissions còn hợp lệ.
- Đổi một byte payload/chữ ký JWT: bị từ chối.
- Token có issuer khác hoặc audience của một API khác: bị từ chối.
- Token `exp` đã qua: 401; token `nbf` ở tương lai: từ chối theo validator/clock skew.
- Token chưa hết hạn nhưng nằm trong denylist: không cấp Authentication.
- Token có `authz_version` cũ so với DB: từ chối, ngay cả khi chữ ký và `exp` hợp lệ.
- Token còn hạn, user bị xóa khỏi team/tenant: request đụng tài nguyên team/tenant phải bị từ chối bởi live permission check.
- Token chỉ có `reports:read` nhưng gọi endpoint yêu cầu `reports:delete`: 403.
- User bị khóa: mọi access token liên quan bị chặn theo chính sách, refresh grant bị hủy.
- Nếu hệ thống cho phép nhiều phiên, revoke một session không làm vô hiệu nhầm các session khác trừ khi đó là policy dự kiến.

### 12.2. Test introspection và cache

- Introspection trả `active=true` và đúng thuộc tính: Resource Server chỉ cấp quyền được chấp nhận.
- Introspection trả `active=false`: không xác thực.
- Introspection trả HTTP 200 nhưng JSON thiếu `active=true`: không tự cho phép.
- AS timeout, 5xx, mất TLS hoặc client credentials sai: fail closed; có alert vận hành.
- Revoke token ngay sau lúc API cache `active=true`: đo chính xác thời gian đến khi API bắt đầu từ chối; đối chiếu với SLO.
- Khi `exp` tới, cache không được kéo dài token còn hiệu lực.
- Đăng nhập/refresh ngay sau đổi quyền: token mới không được chứa quyền đã thu hồi.
- Hai node API chạy cùng lúc: denylist/version update phải có hiệu lực nhất quán; theo dõi độ trễ propagation.

### 12.3. Test thực sự quan trọng: thay quyền khi token đang còn hạn

Một bài test tích hợp nên làm theo trình tự:

1. Cấp token cho user với quyền `reports:delete` (hoặc quyền tài nguyên tương đương).
2. Gọi API xóa một báo cáo thử nghiệm, xác minh được phép theo policy ban đầu.
3. Thu hồi role/quyền của user trong source of truth; **không phát token mới**.
4. Gọi lại API với **chính token cũ, vẫn chưa đến `exp`**.
5. Với endpoint yêu cầu quyền tức thời, kết quả phải bị từ chối. Nếu vẫn cho phép, hệ thống đang dùng authorization stale; kiểm tra token claims, resource permission cache và revocation integration.
6. Đo thời gian từ lúc đổi quyền tới lúc request cũ đầu tiên bị chặn; ghi SLO/giới hạn cửa sổ rủi ro.
7. Kiểm thử lại trên mỗi API node, với cache nóng, network chập chờn và token phát ngay trước thời điểm thu hồi.

Nếu hệ thống **chủ ý** chỉ cập nhật quyền khi phát lại token, phải công bố giới hạn đó, chọn TTL chấp nhận được và phân loại endpoint nào có thể chịu được quyền cũ. Không khẳng định có real-time revocation nếu vẫn chấp nhận JWT cũ cho tới `exp`.

## 13. Vận hành: chính sách và dấu vết cần có

1. **Chọn TTL dựa trên rủi ro.** Endpoint đọc hồ sơ có thể chịu cửa sổ ngắn; thao tác chuyển tiền/xóa dữ liệu/quản trị thường cần kiểm tra trạng thái và quyền gần thời gian thực. Không có TTL phổ quát đúng cho mọi sản phẩm.
2. **Tách access và refresh.** Lưu refresh token an toàn theo loại client, có chính sách rotation/reuse detection phù hợp; revoke khi logout, nghi lộ credential hoặc user bị khóa.
3. **Chặn replay.** Bearer token bị copy có thể sử dụng lại; cân nhắc mTLS/DPoP cho bối cảnh rủi ro cao, đồng thời vẫn cần expiration/revocation.
4. **Vận hành key rotation.** Resource Servers phải theo kịp JWKS rotation; không xóa key cũ vô kế hoạch hoặc giữ key cũ vô hạn. Key rotation không tự đồng nghĩa revoke user.
5. **Đặt cache có giới hạn.** Introspection, permission, denylist, security-version cache phải có TTL/invalidation và xử lý lỗi; đo propagation delay thật.
6. **Không log secrets.** Tránh ghi bearer token, refresh token, authorization code, cookie, signing private key. Nếu cần đối soát token, dùng một tham chiếu đã hash thích hợp và phân quyền log.
7. **Theo dõi audit.** Ghi sự kiện phát hành, revoke, refresh reuse, giảm quyền, session invalidation, 401/403, cache refresh và correlation ID; tránh đưa toàn bộ claims PII ra log phổ thông.
8. **Fail closed theo dữ liệu nhạy cảm.** Khi revocation/permission service không sẵn sàng, tránh fallback cho phép truy cập. Chọn status vận hành và retry phù hợp thay vì đánh đồng mọi lỗi thành sai mật khẩu.
9. **Đảm bảo dữ liệu đa tenant.** `sub` phải gắn với đúng issuer/tenant; token dành cho tenant A không cấp quyền sang tenant B dù user/scope giống nhau.
10. **Thử kịch bản incident.** Giả lập token bị lộ, user bị disable và admin role bị gỡ để biết chính xác khi nào request cũ bị chặn ở tất cả các node.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Vì sao đổi role từ ADMIN sang USER ở database không tự làm JWT đang có `ROLE_ADMIN` mất hiệu lực?  
**Trả lời:** Chữ ký và claim trong JWT đã phát hành không tự thay đổi. Resource Server kiểm tra offline vẫn có thể chấp nhận token đến `exp` nếu không kiểm tra quyền hiện tại/version/revocation.

**Câu 2.** Thu hồi refresh token có chắc chắn làm access token JWT đang lưu ở client hết hiệu lực ngay không?  
**Trả lời:** Không. Revoking refresh token chặn việc phát access token mới từ grant đó, nhưng JWT cũ có thể tiếp tục hợp lệ khi Resource Server chỉ xác minh cục bộ.

**Câu 3.** Muốn chặn access token ngay sau revoke, nên xem xét các cơ chế nào?  
**Trả lời:** Opaque introspection có trạng thái cập nhật, denylist `jti`, security/authz version, custom validation hoặc live state check; kết hợp TTL ngắn và chính sách cache phù hợp.

**Câu 4.** Vì sao introspection có cache 5 phút có thể làm giảm lợi ích revocation tập trung?  
**Trả lời:** API có thể giữ response `active=true` sau khi AS đã revoke, cho đến khi cache hết hạn hoặc bị invalidated; độ trễ đó phải được đánh giá.

**Câu 5.** Sự khác nhau giữa scope trong JWT và quyền đọc báo cáo #815 là gì?  
**Trả lời:** Scope thể hiện quyền đã cấp cho token; quyền với báo cáo #815 còn phụ thuộc tài khoản, tenant, chủ sở hữu và quy tắc nghiệp vụ hiện tại.

**Câu 6.** Khi nào nên trả 401, khi nào nên trả 403?  
**Trả lời:** 401 khi token thiếu/không hợp lệ/hết hạn/bị revoke theo policy; 403 khi token đã xác thực thành công nhưng không đủ quyền cho tài nguyên. Với lỗi dịch vụ introspection cần chính sách lỗi/fail-closed riêng.

**Câu 7.** Nếu tăng `authz_version` trong database mà Resource Server không đọc version thì sao?  
**Trả lời:** Không có tác dụng; JWT cũ vẫn chứa version cũ nhưng API không đối chiếu để từ chối.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): đặc tính bearer token, `Authorization: Bearer`, `invalid_token` và `insufficient_scope`.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009.html): revocation endpoint, refresh/access token và chính sách revocation.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): `active`, metadata, caching và hệ quả bảo mật.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer/audience, timestamp và scope mapping.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và `active`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize` và authorization động.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): bảo vệ access/refresh tokens, replay và OAuth security.
