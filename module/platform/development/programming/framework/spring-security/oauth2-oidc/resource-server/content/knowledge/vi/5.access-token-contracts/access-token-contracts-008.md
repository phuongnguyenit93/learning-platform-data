# Claims bắt buộc, claims tùy chọn và xử lý thiếu hoặc sai kiểu dữ liệu

## 1. Vì sao Resource Server cần một hợp đồng claims?

Khi một client gửi OAuth 2.0 access token đến Spring Boot API, Resource Server không nên chỉ kiểm tra “JWT có chữ ký hợp lệ không?”. Token có thể được ký đúng bởi Authorization Server nhưng **không dành cho API hiện tại**, **đã hết hạn**, **thiếu danh tính cần thiết** hoặc chứa một claim nghiệp vụ ở kiểu dữ liệu khác dự kiến.

Ví dụ một Orders API dự kiến token có thông tin:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "iat": 1999999700,
  "client_id": "shop-web",
  "jti": "token-9f2a",
  "scope": "orders.read",
  "tenant_id": "tenant-42",
  "locale": "vi-VN"
}
~~~

Đây là JSON **minh họa phần claims**, không phải một JWT thực đã ký. Trong ví dụ:

- `iss`, `aud`, `exp` và các claims xác định quyền sử dụng token có ý nghĩa trực tiếp với **xác thực**.
- `scope` và `tenant_id` có thể ảnh hưởng đến **phân quyền**.
- `locale` chỉ dùng cho hiển thị hoặc trải nghiệm; thiếu nó không nhất thiết phải từ chối token.
- `client_id` và `jti` có thể bắt buộc theo **profile access token** mà Authorization Server và API đã chọn.
- Mỗi claim còn có **kiểu dữ liệu**, **giá trị hợp lệ**, **nguồn phát hành** và **hành vi xử lý khi thiếu/sai**.

**Hợp đồng access token** là tài liệu thống nhất giữa Authorization Server, các client, API và gateway (nếu có) về cấu trúc, ý nghĩa và chính sách xử lý token. Hợp đồng quyết định những claim nào Resource Server bắt buộc phải có, claim nào tùy chọn, khi nào từ chối token và khi nào sử dụng giá trị mặc định an toàn.

Bài học tập trung vào **Spring Security OAuth 2.0 Resource Server xử lý JWT access token**. Nếu access token là **opaque token**, API không thể đọc claim trực tiếp từ chuỗi token; nó cần token introspection và xử lý thuộc tính phản hồi theo hợp đồng của Authorization Server.

## 2. Ba tầng quy tắc: JWT chuẩn, profile token, hợp đồng API

Câu hỏi “claim này có bắt buộc không?” không có đáp án duy nhất nếu chưa xác định đang nói tới tầng quy tắc nào.

### 2.1. RFC 7519: các registered claim không bắt buộc trong mọi JWT

RFC 7519 định nghĩa các registered claim names như:

| Claim | Ý nghĩa thông thường | Kiểu JSON theo chuẩn |
|---|---|---|
| `iss` | Bên phát hành token | String / StringOrURI |
| `sub` | Chủ thể của token | String / StringOrURI |
| `aud` | Bên nhận dự kiến | String hoặc mảng các String |
| `exp` | Thời điểm hết hạn | Number theo NumericDate |
| `nbf` | Không hợp lệ trước thời điểm này | Number theo NumericDate |
| `iat` | Thời điểm phát hành | Number theo NumericDate |
| `jti` | Định danh duy nhất cho JWT | String |

**RFC 7519 không yêu cầu mọi JWT phải có toàn bộ các claim trên.** Nó định nghĩa tên, kiểu và ngữ nghĩa khi claim được sử dụng. Các application profile mới xác định tổ hợp claim nào là bắt buộc.

Ví dụ, có thể tồn tại một JWT được ký hợp lệ nhưng không có `aud`. Về cú pháp JWT chung, điều này không tự phủ nhận sự tồn tại của JWT đó. Tuy nhiên, **Orders API** có thể và nên từ chối vì hợp đồng API yêu cầu `aud` phải chứa `orders-api`.

### 2.2. RFC 9068: JWT Profile for OAuth 2.0 Access Tokens

Khi Authorization Server và Resource Server tuyên bố sử dụng **JWT access token profile RFC 9068**, bộ claims trong token có những trường **REQUIRED** rõ ràng:

| Claim | Yêu cầu theo RFC 9068 | Vai trò |
|---|---|---|
| `iss` | REQUIRED | Authorization Server phát hành |
| `exp` | REQUIRED | Hạn sử dụng access token |
| `aud` | REQUIRED | Resource Server đích |
| `sub` | REQUIRED | Chủ thể mà token đại diện |
| `client_id` | REQUIRED | OAuth 2.0 client nhận token |
| `iat` | REQUIRED | Thời điểm token được phát hành |
| `jti` | REQUIRED | Định danh token |

`auth_time`, `acr`, `amr` có thể được cung cấp trong trường hợp có xác thực Resource Owner; chúng không mặc nhiên xuất hiện với mọi access token. Các claim phân quyền hoặc hồ sơ khác, ví dụ `scope`, `groups` hay `tenant_id`, tùy profile và chính sách phát hành cụ thể.

Profile còn mô tả JOSE header `typ` dùng để phân biệt loại token (thường là `at+jwt` hoặc `application/at+jwt` theo quy tắc liên quan). Việc xác minh **loại token** là lớp bảo vệ riêng bên cạnh các claims trong payload: không được dùng OIDC **ID Token** của client như access token chỉ vì cũng là JWT có chữ ký hợp lệ.

**Lưu ý:** không phải mọi access token JWT ngoài thực tế đều khẳng định tuân thủ đầy đủ RFC 9068. Một số Identity Provider có profile riêng. API phải thống nhất **profile hợp đồng thật** trước khi yêu cầu các claims; không tuyên bố những claim có trong RFC 9068 là bắt buộc cho *mọi JWT theo mọi hệ thống*.

### 2.3. Hợp đồng nghiệp vụ của Resource Server

Ngoài yêu cầu chuẩn, Orders API có thể đặt các yêu cầu riêng:

- `aud` phải chứa chính xác `orders-api`.
- `scope` phải chứa `orders.read` để gọi `GET /api/orders`.
- `tenant_id` là một chuỗi không rỗng nếu mọi API path thuộc phạm vi đa khách hàng.
- `region` là một enum như `VN`, `SG`, `TH` nếu endpoint phân vùng dữ liệu theo region.
- `locale` là chuỗi tùy chọn để định dạng thông báo; thiếu có thể dùng mặc định `vi-VN`.
- `preferred_username` hoặc `email` chỉ phục vụ hiển thị nếu có; không nên thay `sub` làm định danh bảo mật.

Mỗi claim được xem là **bắt buộc hay tùy chọn đối với một endpoint/flow**, không chỉ toàn hệ thống. Một endpoint kiểm tra trạng thái sức khỏe không cần token; endpoint đọc đơn hàng cần subject, scope và tenant; endpoint dành cho machine-to-machine có thể dùng subject là client theo quy ước issuer.

## 3. Thiết kế bảng hợp đồng claims

Một bảng hợp đồng hữu ích phải bao gồm nhiều hơn tên claim:

| Thuộc tính | Câu hỏi cần thống nhất |
|---|---|
| **Claim name** | Tên chính xác, có phân biệt hoa/thường không? |
| **Issuer/profile** | Token loại nào, do issuer nào và theo profile nào? |
| **Presence** | Bắt buộc trong mọi access token hay chỉ một flow/endpoint? |
| **JSON type** | String, Number, Boolean, Array hay Object? |
| **Domain constraints** | Không rỗng, tập giá trị cho phép, đơn vị thời gian, giới hạn độ dài? |
| **Validation point** | Decoder, token validator, authority converter, service nghiệp vụ? |
| **Missing behavior** | Từ chối hay sử dụng default phù hợp? |
| **Wrong type** | Từ chối, chuẩn hóa có kiểm soát hay bỏ qua claim tùy chọn? |
| **Authorization effect** | Claim quyết định quyền gì? |
| **Logging/privacy** | Claim có nhạy cảm hoặc dùng làm thông tin nhận dạng không? |

Ví dụ hợp đồng nội bộ cho **Orders API**:

| Claim | Loại | Kiểu/điều kiện | Nếu thiếu | Nếu sai kiểu/giá trị |
|---|---|---|---|---|
| `iss` | Bắt buộc | String khớp issuer đã cấu hình | 401 | 401 |
| `aud` | Bắt buộc | String hoặc array String, chứa `orders-api` | 401 | 401 |
| `exp` | Bắt buộc | NumericDate; chưa hết hạn | 401 | 401 |
| `sub` | Bắt buộc trong hợp đồng này | String khác rỗng; nghĩa tùy grant | 401 | 401 |
| `client_id` | Bắt buộc nếu hợp đồng RFC 9068 | String khác rỗng | 401 | 401 |
| `iat` | Bắt buộc nếu hợp đồng RFC 9068 | NumericDate hợp lệ, không quá tương lai theo policy | 401 | 401 |
| `jti` | Bắt buộc nếu hợp đồng RFC 9068 | String khác rỗng | 401 | 401 |
| `scope` | Điều kiện theo endpoint | String các scope cách nhau bằng khoảng trắng | 403 khi thiếu scope cần thiết | Từ chối token nếu vi phạm schema; không tự nâng quyền |
| `tenant_id` | Bắt buộc cho API đa tenant của ví dụ | String không rỗng | 401 | 401 |
| `locale` | Tùy chọn, chỉ hiển thị | String theo danh sách locale hỗ trợ | Dùng default an toàn | Bỏ qua hoặc dùng default theo hợp đồng |
| `roles` | Tùy chọn có ảnh hưởng quyền | Array String thuộc tập role cho phép | Không có role bổ sung | Từ chối hoặc cấp 0 quyền theo chính sách chặt chẽ |

**401** nghĩa là token không đạt hợp đồng xác thực nên Resource Server từ chối. **403** thường dành cho token đã được xác thực hợp lệ nhưng không đủ quyền để truy cập một endpoint/tài nguyên. Không cố gán mọi lỗi thiếu claim thành 403: khi claim là điều kiện để **token được xem là hợp lệ**, thất bại nên xảy ra ở validator trước khi tạo Authentication.

Các lựa chọn như `tenant_id` bắt buộc là **quyết định của hệ thống ví dụ**, không phải claim chuẩn bắt buộc với mọi OAuth 2.0 Resource Server.

## 4. Kiểu dữ liệu: JSON wire format khác kiểu Java sau khi decode

### 4.1. Những giá trị JSON rất dễ nhầm

Các giá trị sau khác nhau cả về kiểu lẫn ngữ nghĩa:

~~~json
{
  "exp": 2000000000,
  "exp_wrong": "2000000000",
  "aud": ["orders-api"],
  "aud_wrong": 42,
  "tenant_id": "tenant-42",
  "tenant_wrong": 42,
  "enabled": true,
  "enabled_wrong": "true",
  "roles": ["ORDER_VIEWER"],
  "roles_wrong": "ORDER_VIEWER"
}
~~~

- `exp` chuẩn là **NumericDate**, giá trị JSON Number; chuỗi `"2000000000"` là sai kiểu JSON nếu hợp đồng yêu cầu NumericDate chuẩn.
- `aud` theo RFC 7519 cho phép **một String hoặc mảng String**; cả `"orders-api"` và `["orders-api"]` có thể hợp lệ tùy profile.
- `tenant_id` của hợp đồng ví dụ là **String**. `42` không thể tự chuyển thành `"42"` để chấp nhận nếu không có quy tắc chuyển đổi được phê duyệt.
- `enabled` là Boolean, khác chuỗi `"true"`.
- `roles` nếu được định nghĩa là array String, một String đơn không được tự coi là array một phần tử.

Dùng `String.valueOf(jwt.getClaim("tenant_id"))` có thể biến giá trị Number, Boolean hoặc thậm chí `null` thành String và **che mất lỗi schema**. Tránh kiểu ép “dùng được thì dùng” đối với claim có ý nghĩa bảo mật.

### 4.2. NumericDate không phải chuỗi ngày

RFC 7519 định nghĩa **NumericDate** là số giây kể từ Unix epoch, cho phép biểu diễn số không nguyên trong một số trường hợp. Nó **không mặc định là mili giây**, và **không phải ISO-8601 String**.

~~~json
{
  "iat": 1999999700,
  "exp": 2000000000
}
~~~

Những giá trị sau không tương đương:

~~~json
{
  "exp_as_millis": 2000000000000,
  "exp_as_string": "2000000000",
  "exp_as_iso": "2033-05-18T03:33:20Z"
}
~~~

Nếu issuer gửi timestamp ở mili giây nhưng decoder hiểu là giây, token có thể bị diễn giải là còn hiệu lực cực lâu. Vì vậy phải thống nhất đơn vị và kiểu dữ liệu; hạn chế chấp nhận các format dự phòng cho claims quyết định thời gian.

Các boundary cần xem xét:

- `exp` phải ở tương lai tại thời điểm chấp nhận token, với clock skew chỉ trong giới hạn cho phép.
- `nbf` (nếu có) không được ở tương lai vượt ngưỡng cho phép.
- `iat` không nên ở tương lai quá ngưỡng policy, và cần tồn tại nếu profile yêu cầu.
- Khoảng cách `exp - iat` có thể bị giới hạn theo policy để ngăn token sống quá lâu.
- Tránh số âm không hợp lệ theo hợp đồng, overflow, giá trị quá lớn hoặc định dạng Number không được parser hỗ trợ.

### 4.3. Spring Security ánh xạ claim sang Java

Khi dùng **`NimbusJwtDecoder`** với Spring Security, claim set thường được chuyển về kiểu Java thuận tiện qua **`MappedJwtClaimSetConverter`**. Các kiểu quy ước phổ biến:

| JWT claim | Java type mà Spring cố gắng chuẩn hóa |
|---|---|
| `aud` | `Collection<String>` |
| `exp` | `Instant` |
| `iat` | `Instant` |
| `nbf` | `Instant` |
| `iss` | `String` |
| `sub` | `String` |
| `jti` | `String` |

Bởi vậy khi gọi:

~~~java
Jwt jwt = /* principal đã được xác thực */;
String subject = jwt.getSubject();
Collection<String> audiences = jwt.getAudience();
Instant expiresAt = jwt.getExpiresAt();
~~~

chương trình đang đọc **giá trị đã được decoder chuẩn hóa**, không nhất thiết là kiểu JSON thô vừa nhận từ wire.

Điều này giúp xử lý JWT thuận tiện, nhưng có một hệ quả quan trọng: **kiểm tra kiểu ở giai đoạn `OAuth2TokenValidator<Jwt>` chỉ nhìn thấy claim sau bước conversion**. Nếu hợp đồng yêu cầu kiểm tra kiểu JSON gốc cực kỳ nghiêm ngặt, phải bảo đảm converter/parser không tự chấp nhận những kiểu sai theo quy tắc mặc định; có thể cần **claim-set converter được cấu hình tường minh**, validation bổ sung hoặc chuẩn hóa profile ở bên phát hành.

Không sửa sai profile issuer bằng cách ép mọi giá trị String, Number, Array về một kiểu mong muốn. Việc chuyển đổi chỉ phù hợp khi các dạng đầu vào đều được **hợp đồng chính thức** chấp nhận.

## 5. Sự khác biệt giữa thiếu, null, trống và sai kiểu

Ví dụ bốn payload:

**Không có claim:**

~~~json
{"sub":"user-123"}
~~~

**Có claim nhưng null:**

~~~json
{"sub":"user-123","tenant_id":null}
~~~

**Có claim là String rỗng:**

~~~json
{"sub":"user-123","tenant_id":""}
~~~

**Có claim sai kiểu:**

~~~json
{"sub":"user-123","tenant_id":["tenant-42"]}
~~~

Nếu hợp đồng yêu cầu `tenant_id` là String không rỗng, **cả bốn trường hợp đều không hợp lệ**. Không thể mặc định:

- Missing → tenant “public” vì dễ làm token vượt phạm vi dữ liệu.
- `null` → String `"null"`.
- Chuỗi rỗng → tenant mặc định.
- Array một phần tử → String phần tử đầu tiên.

Với claim tùy chọn chỉ ảnh hưởng giao diện như `locale`, có thể thiết kế:

~~~text
locale thiếu hoặc sai định dạng -> sử dụng "vi-VN" cho hiển thị
~~~

Nhưng với claim xác định **tenant, role, scope, assurance level, client identity**, thiếu hoặc sai kiểu phải được xem xét như **lỗi chứng thực hợp đồng hoặc quyền**, tránh việc parser linh động khiến token được cấp thêm quyền.

### 5.1. Có quyền mặc định không?

Hãy dùng nguyên tắc:

- **Không được cấp quyền mới do fallback.**
- Với claim tùy chọn mang quyền, thiếu có thể nghĩa là **không có quyền thêm**.
- Sai kiểu của claim quyền có thể được **từ chối** ngay khi xác thực hoặc quy về **không có quyền**, tùy profile; lựa chọn từ chối thường dễ phát hiện issuer bị lỗi và tránh cách diễn giải không nhất quán.
- Với claim hoàn toàn không liên quan đến bảo mật (ngôn ngữ UI, theme), có thể fallback theo policy.
- Với `sub` hoặc `tenant_id` bắt buộc để định danh tài nguyên, không fallback sang claim ít tin cậy hơn như email hoặc preferred username.

### 5.2. Trường hợp claim có danh sách

Ví dụ hợp đồng:

~~~json
{
  "roles": ["ORDER_VIEWER", "ORDER_EDITOR"]
}
~~~

Nếu `roles` bắt buộc là array String, cần kiểm tra từng phần tử:

- Không chấp nhận `roles: "ORDER_EDITOR"` chỉ vì danh sách có một role.
- Không chấp nhận `roles: [true, "ORDER_EDITOR"]`.
- Không chấp nhận `roles: [""]`.
- Nên có tập role được cho phép và giới hạn kích thước danh sách, tránh chuỗi lạ hoặc quá dài.
- Nếu danh sách rỗng được hợp đồng cho phép, giải thích rõ nó tương đương **không có role**.

Tránh tự động trộn role từ nhiều nguồn không tương đương, chẳng hạn `groups` là nhóm tổ chức nhưng `roles` là quyền nội bộ.

## 6. Nền tảng cấu hình Resource Server

### 6.1. Chữ ký, issuer, expiry và audience

Với Spring Boot, thêm dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences: orders-api
~~~

Giá trị issuer ở đây chỉ là ví dụ và phải trùng với claim `iss` mà Authorization Server thực tế phát hành.

`issuer-uri` cấu hình issuer mà decoder tin cậy và cho phép tìm metadata/JWKS theo provider. `audiences` là Spring Boot property giúp ràng buộc token với audience của API trong những phiên bản hỗ trợ cấu hình này.

Resource Server JWT mặc định xác minh chữ ký với khóa tin cậy và xử lý các validator cơ bản cho `exp`, `nbf`, `iss`. **Đừng mặc định rằng mọi claim của RFC 9068, mọi custom claim và mọi quy tắc kiểu dữ liệu đã được xác thực chỉ nhờ `issuer-uri`.**

`audiences` thực hiện kiểm tra audience; nếu hợp đồng cần nhiều quy tắc bổ sung, có thể xây validator riêng.

### 6.2. SecurityFilterChain bảo vệ endpoint theo scope

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Trong cấu hình mặc định, Spring Security có thể ánh xạ scope từ access token thành authority với tiền tố `SCOPE_`. Vì thế `scope: "orders.read"` có thể cung cấp `SCOPE_orders.read` cho request.

**Scope không thay thế kiểm tra quyền sở hữu dữ liệu.** Token có `orders.read` vẫn không được xem đơn hàng của tenant khác. Cần áp dụng kiểm tra theo `sub`/`tenant_id` và các rule nghiệp vụ.

## 7. Viết validator cho claim bắt buộc và claim tùy chọn

### 7.1. Tổ hợp validator

Với yêu cầu cụ thể hơn cấu hình tự động, ứng dụng có thể tạo `JwtDecoder` và gắn `OAuth2TokenValidator<Jwt>` riêng.

Ví dụ hợp đồng **Orders API**:

- `iss` là issuer được cấu hình.
- `aud` phải chứa `orders-api`.
- `exp`, `nbf` được kiểm tra theo validator mặc định.
- `tenant_id` bắt buộc là String có nội dung.
- `client_id` bắt buộc là String có nội dung.
- `jti` bắt buộc là String có nội dung.
- `iat` bắt buộc (sau conversion là `Instant`).
- `locale` tùy chọn; nếu có phải là String thuộc một trong hai locale được hỗ trợ. Vì đây là claim chỉ dùng hiển thị, ví dụ bỏ qua giá trị không hỗ trợ trong controller, nhưng không dựa vào nó để phân quyền.

Ví dụ mã Java:

~~~java
package com.example.orders.security;

import java.time.Instant;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class AccessTokenContractConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> contract =
            AccessTokenContractConfig::validateContract;

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(defaults, contract)
        );
        return decoder;
    }

    private static OAuth2TokenValidatorResult validateContract(Jwt jwt) {
        if (!jwt.getAudience().contains(AUDIENCE)) {
            return invalid("Token has no audience for orders-api");
        }

        if (!nonBlankString(jwt.getClaim("sub"))) {
            return invalid("Missing or invalid subject");
        }

        if (!nonBlankString(jwt.getClaim("client_id"))) {
            return invalid("Missing or invalid client_id");
        }

        if (!nonBlankString(jwt.getClaim("jti"))) {
            return invalid("Missing or invalid jti");
        }

        if (!nonBlankString(jwt.getClaim("tenant_id"))) {
            return invalid("Missing or invalid tenant_id");
        }

        Instant issuedAt = jwt.getIssuedAt();
        if (issuedAt == null) {
            return invalid("Missing issued-at timestamp");
        }

        // Không tự xác thực scope ở đây: SecurityFilterChain kiểm tra
        // scope theo endpoint; claim schema riêng vẫn có thể cần validator.
        return OAuth2TokenValidatorResult.success();
    }

    private static boolean nonBlankString(Object claim) {
        return claim instanceof String value && !value.isBlank();
    }

    private static OAuth2TokenValidatorResult invalid(String reason) {
        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", reason, null)
        );
    }
}
~~~

Trong ví dụ, `JWKS_URI` dùng cấu trúc thường gặp của một số Identity Provider; phải lấy giá trị `jwks_uri` thực tế từ metadata đáng tin. Với bean decoder tự tạo, **việc gọi `JwtValidators.createDefaultWithIssuer(ISSUER)` giữ validator cơ bản**, sau đó mới bổ sung hợp đồng riêng.

Đoạn code trên là **validator dựa trên `Jwt` sau khi conversion**. Nó minh họa cách từ chối claim thiếu/sai kiểu còn thấy được ở model Java; không tự chứng minh rằng kiểu JSON *thô* của từng registered claim ban đầu đúng chính xác với profile RFC 9068. Muốn bắt lỗi ép kiểu ngầm, cần kiểm soát thêm tầng claim conversion, như phân tích ở phần sau.

**Với tên claim `sub` và `jti`:** `jwt.getClaim(...)` trả lại giá trị đã chuẩn hóa nếu decoder có converter. `nonBlankString` kiểm tra kiểu Java và không nhận String rỗng. Với `tenant_id` là custom claim, kiểu dữ liệu thường giữ theo JSON trừ khi ứng dụng cấu hình converter riêng.

### 7.2. Kiểm tra claim tùy chọn một cách rõ ràng

Giả sử `locale` chỉ để định dạng tên/đơn vị hiển thị:

~~~java
package com.example.orders.service;

import org.springframework.security.oauth2.jwt.Jwt;

public final class LocalePolicy {

    public static String localeForDisplay(Jwt jwt) {
        Object claim = jwt.getClaims().get("locale");

        if (!(claim instanceof String locale)) {
            return "vi-VN";
        }

        return switch (locale) {
            case "vi-VN", "en-US" -> locale;
            default -> "vi-VN";
        };
    }
}
~~~

Nếu claim `locale` không có, là null, khác String hoặc có giá trị ngoài allowlist, ứng dụng dùng default an toàn cho **hiển thị**. Không áp dụng kiểu fallback này cho tenant, account ownership, audience hoặc roles.

Nếu `locale` có ý nghĩa **bảo mật hoặc tuân thủ** (ví dụ quyết định phạm vi dữ liệu theo quốc gia), nó không còn là claim UI tùy chọn đơn thuần và phải có validation nghiêm ngặt hơn.

### 7.3. Claim tùy chọn nhưng có quyền: `roles`

Giả sử profile định nghĩa `roles` là mảng String; thiếu nghĩa là không có quyền từ roles.

Một helper có thể xử lý an toàn:

~~~java
package com.example.orders.security;

import java.util.Collection;
import java.util.Set;

import org.springframework.security.oauth2.jwt.Jwt;

public final class RoleClaims {

    private static final Set<String> ALLOWED =
        Set.of("ORDER_VIEWER", "ORDER_EDITOR", "ORDER_ADMIN");

    public static Set<String> readRoles(Jwt jwt) {
        Object raw = jwt.getClaims().get("roles");

        if (raw == null) {
            return Set.of(); // Không có claim -> không cấp thêm role
        }

        if (!(raw instanceof Collection<?> values)) {
            throw new IllegalArgumentException(
                "Claim roles must be an array of strings");
        }

        for (Object value : values) {
            if (!(value instanceof String role)
                    || !ALLOWED.contains(role)) {
                throw new IllegalArgumentException(
                    "Invalid role claim value");
            }
        }

        return values.stream()
            .map(String.class::cast)
            .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }
}
~~~

Đoạn helper trên chỉ mô tả **kiểm tra dữ liệu và nguyên tắc không cấp quyền khi thiếu claim**. Nếu `roles` là claim bảo mật theo hợp đồng, nên đặt kiểm tra schema ở **decoder/validator trước khi tạo Authentication**, rồi ánh xạ sang authorities theo chính sách. Không chờ controller tự parse role và ném `IllegalArgumentException` thành lỗi 500.

Tương tự, nếu Spring Security mặc định chỉ đọc `scope`/`scp` để tạo authorities, một custom `roles` **không tự biến thành quyền truy cập**; cần cấu hình `JwtAuthenticationConverter` hoặc chính sách authorization tương ứng. Mọi role được chấp nhận phải đến từ issuer đáng tin và thuộc tập quyền được API công nhận.

## 8. Tránh ép kiểu ngầm tại Claim Set Converter

### 8.1. Tại sao validator có thể chưa đủ?

Giả sử một Authorization Server phát hành lỗi:

~~~json
{
  "sub": 12345,
  "exp": "2000000000",
  "aud": "orders-api"
}
~~~

Trong một số đường parse/conversion, thư viện có thể chuẩn hóa claim về kiểu Java tiện dụng, hoặc cũng có thể từ chối tùy dạng và phiên bản. Nếu `sub: 12345` bị ép thành `"12345"` trước khi `OAuth2TokenValidator<Jwt>` chạy, validator kiểm tra `sub instanceof String` sẽ **không còn phân biệt được** kiểu JSON gốc.

Vì thế có hai lớp yêu cầu khác nhau:

- **Semantic validation**: sau khi decode, `iss` đúng, `aud` chứa audience, `tenant_id` có nội dung, `exp` chưa quá hạn.
- **Strict wire-schema validation**: payload JSON đầu vào thực sự có `sub` là String, `exp` là Number, `roles` là Array String; không cho converter “chữa” kiểu sai.

Nếu contract yêu cầu strict wire schema, cần xử lý các kiểm tra này ở điểm có dữ liệu gốc đáng tin sau khi **xác minh chữ ký**, hoặc dùng custom claim-set conversion không làm mất thông tin mà hợp đồng cần; tuyệt đối không tự bypass verification để đọc và tin payload.

### 8.2. `MappedJwtClaimSetConverter` dùng để chuẩn hóa có kiểm soát

Spring Security cho phép cấu hình:

~~~java
import java.util.Map;

import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

NimbusJwtDecoder decoder =
    NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

decoder.setClaimSetConverter(
    MappedJwtClaimSetConverter.withDefaults(
        Map.of("tenant_id", value -> {
            if (value == null) {
                return null;
            }
            if (!(value instanceof String tenant)) {
                throw new IllegalArgumentException(
                    "tenant_id must be a JSON string");
            }
            return tenant;
        })
    )
);
~~~

Đây là đoạn minh họa cấu hình **một claim tùy chỉnh**; `jwksUri` phải có giá trị thực từ ứng dụng. Converter có thể bảo đảm `tenant_id` chỉ là String nếu được cung cấp, và validator phía sau sẽ từ chối nếu giá trị null hoặc rỗng. Lựa chọn `withDefaults(...)` giữ các rule conversion tiêu chuẩn cho claims khác.

**Cẩn trọng khi tùy chỉnh registered claims**: thay conversion của `exp`/`iat`/`aud` có thể ảnh hưởng trực tiếp đến Spring validators. Nếu cần bắt lỗi schema từ JSON thô, thiết kế điểm kiểm tra phù hợp với phiên bản Spring/Nimbus đang dùng và không vô hiệu hóa thời hạn, issuer, audience, signature validation.

Trong production, nếu issuer gửi sai format nhất quán, nên ưu tiên **sửa phía phát hành** và thống nhất hợp đồng hơn là xây một chuỗi fallback chấp nhận nhiều kiểu ngầm.

## 9. Quy tắc kiểm tra các claim thường gặp

### 9.1. `iss`: issuer tin cậy

`iss` phải trùng **chính xác** issuer mà Resource Server tin cậy. Không so sánh bằng `contains` hay chỉ đối chiếu domain một cách lỏng lẻo.

Ví dụ:

~~~text
Configured issuer: https://id.example.test/realms/shop

Accepted:
  https://id.example.test/realms/shop

Rejected:
  https://id.example.test/realms/another
  http://id.example.test/realms/shop
~~~

Ứng dụng phải dùng metadata và JWKS từ issuer tin cậy, không để token tự chọn nguồn khóa xác minh.

### 9.2. `aud`: audience đúng API

`aud` có thể là một String hoặc mảng String:

~~~json
{"aud": "orders-api"}
~~~

~~~json
{"aud": ["orders-api", "reports-api"]}
~~~

Nếu hợp đồng cho phép nhiều audience, membership `orders-api` là hợp lệ. Nếu security policy yêu cầu **đúng một audience duy nhất**, đó là ràng buộc bổ sung cần khai báo rõ và kiểm tra. Không dùng câu lệnh chỉ lấy phần tử đầu tiên khi `aud` là mảng.

JWT có `aud: "shop-web"` là ID Token/client audience trong nhiều luồng OIDC, thường **không dành cho Orders API**, dù chữ ký có thể hợp lệ.

### 9.3. `exp` và `nbf`: thời gian

- `exp` là ranh giới hết hạn.
- `nbf` giới hạn thời điểm token bắt đầu hợp lệ.
- Clock skew có thể được áp dụng một cách giới hạn để xử lý chênh lệch đồng hồ nhỏ.
- Token hết hạn hoặc chưa có hiệu lực không được nâng thành hợp lệ bằng cách cố đọc raw claims trong controller.
- `iat` mô tả khi token được phát hành; cần validator riêng nếu profile yêu cầu không được cấp từ tương lai vượt tolerance hoặc có tuổi thọ tối đa.

Tăng clock skew quá lớn để “sửa lỗi đồng hồ” có thể kéo dài khoảng chấp nhận token không mong muốn. Đồng hồ hệ thống nên được đồng bộ chính xác.

### 9.4. `sub`: chủ thể của token

Một access token cấp theo Authorization Code Flow có `sub` thường là người dùng. Trong **Client Credentials Flow**, theo RFC 9068, `sub` có thể đại diện cho **client application**.

Vì vậy:

~~~java
String subject = jwt.getSubject();
~~~

không tự chứng minh rằng một người dùng đã đăng nhập. Đừng mặc định `sub` luôn là user ID để dùng trong mọi flow. Hợp đồng nên xác định:

- Token nào đại diện người dùng, token nào đại diện service/client.
- Loại grant và thông tin actor cần thiết (nếu có).
- Endpoint nào được gọi bởi machine principal.
- Phạm vi dữ liệu mà subject được phép sử dụng.
- Cách kết hợp `iss` + `sub` để định danh đúng phạm vi.

### 9.5. `scope` và `roles`: phân quyền

`scope` có thể được biểu diễn theo profile phổ biến dưới dạng một chuỗi các scope cách nhau bởi dấu cách:

~~~json
{"scope": "orders.read orders.write"}
~~~

Một số provider dùng `scp` dạng Array String; đây là **biến thể theo issuer** cần thống nhất. Không tự đồng nhất mọi claim `roles`, `groups`, `permissions` với scope chuẩn nếu chưa có converter và chính sách rõ.

Phân biệt:

1. **Claim có hợp lệ theo schema không?** Ví dụ `scope` là String đúng format.
2. **Token có quyền cần thiết cho endpoint không?** Ví dụ chứa `orders.read`.
3. **Chủ thể có quyền với bản ghi cụ thể không?** Ví dụ chỉ xem đơn hàng cùng tenant.

Thiếu claim `scope` có thể không làm token vô hiệu nếu profile không buộc nó tồn tại, nhưng endpoint yêu cầu `orders.read` phải **từ chối quyền**.

### 9.6. Custom claims: `tenant_id`, `region` và `customer_id`

Đối với custom claim:

- Định nghĩa **namespace/tên claim** để tránh trùng ý nghĩa với claim chuẩn.
- Xác định String vs Number, nhất là với mã định danh có số 0 ở đầu như `"00123"`.
- Không dùng `Integer.parseInt` cho mã String nếu hợp đồng không định nghĩa kiểu Number.
- Xác định multi-tenancy và ownership; không lấy `tenant_id` từ input HTTP để ghi đè claim đã xác thực.
- Khi business rule yêu cầu định danh tenant, phải từ chối token thiếu/không hợp lệ tại điểm kiểm tra phù hợp.

## 10. Khi nào 401, khi nào 403?

Một chính sách nhất quán giúp client sửa lỗi mà không làm lộ thông tin nhạy cảm.

| Trường hợp | Kết quả thường gặp | Lý do |
|---|---|---|
| Không gửi Bearer token tới endpoint bảo vệ | **401** | Chưa xác thực |
| Token sai chữ ký/issuer/hạn | **401** | Token không hợp lệ |
| Token thiếu `aud` bắt buộc hoặc sai audience | **401** | Token không dành cho API |
| Token thiếu `tenant_id` bắt buộc ở decoder contract | **401** | Vi phạm hợp đồng access token |
| Token có `tenant_id` dạng Number nhưng yêu cầu String | **401** | Sai schema bảo mật |
| Token hợp lệ nhưng thiếu `orders.read` | **403** | Đã xác thực nhưng thiếu quyền endpoint |
| Token hợp lệ có `orders.read`, yêu cầu đơn hàng tenant khác | **403** hoặc **404** tùy policy tránh lộ tài nguyên | Không được truy cập đối tượng nghiệp vụ |
| Token hợp lệ, `locale` thiếu | **Không cần từ chối** | Dùng mặc định cho hiển thị |
| Token hợp lệ, `roles` không có và quyền role là tùy chọn | Không có role bổ sung | Fail closed trong phân quyền |

Các status là hành vi dự kiến của cấu hình bảo mật thông thường; gateway, exception handler và yêu cầu API có thể điều chỉnh chi tiết response. Không log nguyên token hoặc toàn bộ claims khi báo lỗi; chỉ ghi các metadata cần thiết (ví dụ mã lỗi và correlation ID).

### Ví dụ kiểm tra bằng curl

~~~bash
curl -i \
  -H "Authorization: Bearer <VALID_ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Nếu hợp đồng yêu cầu đủ claims và token qua validation, controller mới có thể xử lý. Không cần đưa JWT thật vào ví dụ công khai, kho mã hoặc dịch vụ decode token của bên thứ ba.

Với lỗi, client có thể thấy response kèm:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Không phải mọi response đều có body JSON chi tiết. Theo RFC 6750, header `WWW-Authenticate` giúp mô tả lỗi ở lớp Bearer; không nên đưa plaintext token hay claims nhạy cảm vào thông báo cho client.

## 11. Thiết kế bảng trường hợp để kiểm thử hợp đồng

Một bộ case điển hình:

| Case | Đầu vào | Kết quả mong đợi |
|---|---|---|
| Hợp lệ | `iss`, `aud`, `exp`, `sub`, `tenant_id` đúng; đủ `orders.read` | Có thể 200 |
| Không có `aud` | JWT ký đúng nhưng không có audience | 401 |
| `aud` dạng Number | `"aud": 123` | Từ chối theo schema |
| `aud` mảng không chứa Orders API | `["billing-api"]` | 401 |
| `exp` là String | `"exp": "2000000000"` | Từ chối nếu strict NumericDate schema |
| `exp` đã hết hạn | NumericDate quá khứ | 401 |
| Không có `tenant_id` | Claim không xuất hiện | 401 nếu bắt buộc |
| `tenant_id` là null | `"tenant_id": null` | 401 |
| `tenant_id` rỗng | `"tenant_id": ""` | 401 |
| `tenant_id` là Number | `"tenant_id": 42` | 401 |
| Không có `locale` | Không có locale | Fallback hiển thị |
| `locale` sai kiểu | `"locale": 10` | Không dùng để quyết định quyền |
| `roles` dạng String | `"roles": "ORDER_ADMIN"` | Từ chối theo schema role đã định |
| `scope` thiếu `orders.read` | Token hợp lệ, quyền không đủ | 403 |
| ID Token gửi thay access token | `aud`/`typ` không phù hợp profile API | Từ chối |

Để kiểm thử thực tế, nên tạo **token test được ký bằng khóa test của issuer** có thể chủ động điều chỉnh payload, thay vì sửa payload trên JWT production: sửa payload làm chữ ký không hợp lệ, không cho phép tách biệt lỗi schema và lỗi signature.

Với các case về kiểu dữ liệu JSON thô, phải đảm bảo bộ test sử dụng đúng pipeline parse/claim-conversion của decoder và có khả năng xác định kiểu đầu vào mà application contract yêu cầu. Không chỉ test controller với `Jwt` được khởi tạo sẵn bằng `Jwt.withTokenValue(...)` rồi kết luận rằng decoder đã từ chối mọi input sai kiểu.

## 12. Ràng buộc bảo mật khi vận hành

### 12.1. Không suy diễn quyền từ claim không đáng tin

Claims chỉ đáng tin sau khi Resource Server đã xác minh token hợp lệ với issuer/key/profile đúng. Không Base64URL-decode payload rồi tin `roles` hoặc `tenant_id` trước khi xác minh chữ ký và claims validation.

Sau khi xác thực, dữ liệu claim vẫn là **statement của issuer**, không phải quyết định cấp quyền cuối cùng cho mọi tài nguyên. API có thể cần tra chính sách dữ liệu nội bộ và quyền sở hữu bản ghi.

### 12.2. Không thêm default có thể mở rộng quyền

Default cho UI có thể phù hợp; default cho principal và scope/tenant thường không. Cảnh báo những đoạn mã như:

~~~java
String tenantId = jwt.hasClaim("tenant_id")
    ? jwt.getClaimAsString("tenant_id")
    : "global";  // Nguy hiểm nếu "global" cho truy cập rộng hơn
~~~

Một đoạn an toàn hơn, khi `tenant_id` bắt buộc, là từ chối token trong validator trước khi request vào nghiệp vụ.

### 12.3. Giới hạn dữ liệu và tránh lạm dụng claims

JWT chỉ được ký, không mặc nhiên mã hóa nội dung. Những người có token có thể đọc claims của JWS bằng Base64URL-decode. Không nhúng thông tin bí mật không cần thiết. Với custom claims:

- Giới hạn độ dài String và số phần tử array.
- Không tin nested JSON object tùy ý có thể vượt hạn mức.
- Xác định versioning khi thay đổi schema.
- Bảo đảm tính ổn định của identifier; email thường không phù hợp làm principal ID.
- Xác định chính sách đối với claims lạ; không biến unknown claim thành quyền.
- Tránh lỗi phân tách dấu phẩy, dấu cách, chuỗi rỗng và định dạng role không thống nhất.

### 12.4. Thay đổi hợp đồng giữa Authorization Server và API

Khi thêm một claim bắt buộc như `tenant_id`:

1. Thống nhất issuer sẽ phát hành đúng kiểu/giá trị cho các loại grant cần hỗ trợ.
2. Xác định liệu token đã phát hành trước đó còn lưu hành hay không.
3. Triển khai versioning, migration hoặc giai đoạn tương thích theo rủi ro.
4. Sau khi hợp đồng được áp dụng, validator mới từ chối token không đáp ứng chính sách.
5. Giám sát tỷ lệ 401/403 theo mã lỗi/correlation ID; không đưa token thật vào log.

Nếu có nhiều issuer hoặc nhiều token profile, chính sách claims có thể cần khác nhau theo **issuer và loại token**. Không áp một hợp đồng chung lỏng lẻo chỉ để mọi loại token đều vượt validation.

## 13. Một ví dụ tổng hợp để suy luận

Giả sử endpoint:

~~~http
GET /api/orders/42
Authorization: Bearer <JWT>
~~~

Hợp đồng giả định:

- Access token có issuer `https://id.example.test/realms/shop`.
- Audience phải chứa `orders-api`.
- Token còn hạn, đúng chữ ký.
- Token có `sub` String không rỗng.
- Token phải có `tenant_id` String không rỗng.
- Endpoint GET cần `orders.read`.
- Dữ liệu đơn hàng số 42 thuộc đúng tenant của token.

Token A:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"orders.read",
  "tenant_id":"tenant-42"
}
~~~

Nếu những claims trên thuộc một JWS đã ký hợp lệ, token chưa hết hạn và **hợp đồng của API không bắt buộc RFC 9068 profile đầy đủ**, token A có thể vượt lớp token validation (sau đó vẫn cần kiểm tra ownership). Nếu API tuyên bố **tuân thủ RFC 9068** và bắt buộc `client_id`, `iat`, `jti`, token A còn thiếu chúng và phải bị từ chối. **Kết luận phụ thuộc vào profile hợp đồng**.

Token B:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"orders.read",
  "tenant_id":42
}
~~~

Token B vi phạm schema `tenant_id` là String. Không thể chấp nhận chỉ vì chữ ký hợp lệ; với policy bắt buộc nên là 401.

Token C:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"profile",
  "tenant_id":"tenant-42"
}
~~~

Nếu claims đáp ứng hợp đồng xác thực và token còn hạn, token C có thể **được xác thực** nhưng thiếu `orders.read`, nên không được truy cập endpoint: thông thường là 403.

Token D:

~~~json
{
  "iss":"https://id.example.test/realms/shop",
  "sub":"user-123",
  "aud":["orders-api"],
  "exp":2000000000,
  "scope":"orders.read",
  "tenant_id":"tenant-42",
  "locale":null
}
~~~

Nếu `locale` thuần túy là claim UI tùy chọn, ứng dụng có thể dùng `vi-VN` làm mặc định; điều này không làm tăng quyền token.

Tất cả payload chỉ để giải thích khác biệt; **chúng không phải JWT đã ký** và không được dùng trực tiếp làm credential thực.

## 14. Những điểm cần ghi nhớ

- **Không có danh sách claims bắt buộc chung cho mọi JWT** trong RFC 7519. Chọn rõ **JWT access token profile** và **hợp đồng API** trước khi quy định tính bắt buộc.
- **RFC 9068** định nghĩa các claims bắt buộc `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, `jti` cho JWT access token theo profile đó.
- **JWT claim có cả kiểu dữ liệu lẫn ý nghĩa**. `aud` có thể là String hoặc array String; `exp`/`iat` là NumericDate; custom `tenant_id` và `roles` phải theo schema đã thống nhất.
- **Missing, null, chuỗi rỗng và sai kiểu không tương đương với giá trị hợp lệ**. Không ép kiểu tùy tiện đối với claim bảo mật.
- Spring Security có cơ chế chuẩn hóa claim types; khi đòi hỏi đúng **wire JSON type**, cần kiểm soát thêm claim conversion/parser ngoài việc validate `Jwt` đã chuyển đổi.
- Claim tùy chọn cho hiển thị có thể có fallback an toàn; claim xác định principal, scope, tenant và quyền thì phải **fail closed**.
- Xác thực token (`iss`, `aud`, signature, time, contract) và phân quyền endpoint/đối tượng (`scope`, ownership) là hai lớp bổ sung.
- Tài liệu hợp đồng nên nêu rõ hành vi với token thiếu/sai kiểu để Authorization Server, Resource Server và client xử lý nhất quán.

### Tài liệu tham khảo

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — MappedJwtClaimSetConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/MappedJwtClaimSetConverter.html)
- [Spring Security API — Jwt](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/Jwt.html)

