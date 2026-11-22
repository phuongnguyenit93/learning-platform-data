# MappedJwtClaimSetConverter và chuyển kiểu, điều chỉnh claims

Trong **Spring Security OAuth 2.0/OIDC Resource Server** chạy trên Servlet stack, JWT access token thường chứa một tập claims dưới dạng JSON. Tuy nhiên, giá trị JSON và kiểu dữ liệu Java mà ứng dụng mong đợi không phải lúc nào cũng giống nhau. Chẳng hạn:

- `exp` trong JWT là *NumericDate* (số giây tính từ Unix epoch), nhưng code Java thường cần `Instant`.
- `aud` có thể là chuỗi đơn hoặc mảng JSON, trong khi Spring Security cung cấp `Jwt.getAudience()` theo danh sách audience.
- Authorization Server có thể phát hành một claim riêng như `tenant_id`, `preferred_username`, `groups` hoặc `legacy_user_id` với kiểu/định dạng cần được chuẩn hóa trước khi sử dụng.
- Ứng dụng cần phân biệt **định danh chính của principal** với tên hiển thị, tên đăng nhập hoặc quyền được ánh xạ từ token.

Spring Security có **`MappedJwtClaimSetConverter`** để tùy chỉnh cách ánh xạ các claim trong JWT sang tập claims của đối tượng `Jwt`. Nó hoạt động ở **tầng chuyển đổi dữ liệu claims** của `NimbusJwtDecoder`, không phải cơ chế bỏ qua chữ ký số, không phải validator quyết định token hợp lệ, và cũng không phải converter tạo `GrantedAuthority`.

Bài học này hướng dẫn cách hiểu vị trí converter, sử dụng các chuyển kiểu mặc định, tùy chỉnh một claim hoặc nhiều claims, tránh làm mất những conversion quan trọng, và chọn đúng công cụ khi mục tiêu thực sự là thay tên principal hay ánh xạ scope/role.

> **Điểm quan trọng:** Chuyển đổi claim giúp ứng dụng hiểu **kiểu dữ liệu và cấu trúc**; validator kiểm tra **token có được chấp nhận**; authentication converter tạo **principal và authorities**; authorization quyết định **quyền truy cập**. Đây là bốn công việc khác nhau.

## 1. Đặt claim conversion đúng vị trí trong chuỗi Servlet

Khi client gọi API bằng JWT access token:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

Spring Security Resource Server thường xử lý qua các thành phần:

```mermaid
flowchart TD
    A["Authorization: Bearer JWT"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtAuthenticationProvider"]
    C --> D["NimbusJwtDecoder"]
    D --> E{"JWS, chữ ký, khóa và thuật toán hợp lệ?"}
    E -- "Không" --> F["Xác thực thất bại"]
    E -- "Có" --> G["Claim-set conversion: mặc định + tùy biến"]
    G --> H["Jwt chứa headers và claims đã chuyển kiểu"]
    H --> I{"JwtValidators và custom validators đạt?"}
    I -- "Không" --> F
    I -- "Có" --> J["JwtAuthenticationConverter"]
    J --> K["JwtAuthenticationToken và GrantedAuthority"]
    K --> L["SecurityContext"]
    L --> M{"Authorization cho endpoint và dữ liệu?"}
    M -- "Không" --> N["Thường 403"]
    M -- "Có" --> O["Controller / service"]
    F --> P["Thường 401 hoặc lỗi xử lý xác thực phù hợp"]
```

Sơ đồ mô tả các giai đoạn logic trong cách triển khai JWT Resource Server thông dụng. Chi tiết nội bộ khi parse, xác minh và chuẩn hóa claim phụ thuộc decoder/phiên bản, nhưng điều bắt buộc là **không được dùng claims chưa xác thực để cấp quyền**.

| Thành phần | Đầu vào | Đầu ra / mục đích |
|---|---|---|
| `NimbusJwtDecoder` | Chuỗi JWT từ request | Xác minh chữ ký, chuyển đổi claims và chạy validators; trả `Jwt` hoặc lỗi |
| `MappedJwtClaimSetConverter` | `Map<String, Object>` chứa claim values | `Map<String, Object>` với dữ liệu/kiểu đã chuẩn hóa theo hợp đồng |
| `OAuth2TokenValidator<Jwt>` | Đối tượng `Jwt` | Kết quả chấp nhận hoặc từ chối token theo issuer, thời gian, audience, claims khác |
| `JwtAuthenticationConverter` | `Jwt` đã qua xác thực | `JwtAuthenticationToken` với tên principal và authorities |
| `JwtGrantedAuthoritiesConverter` | Claims liên quan quyền | Danh sách `GrantedAuthority`, ví dụ `SCOPE_orders.read` |
| `AuthorizationFilter` và method security | `Authentication` đã xác thực và context request | Quyết định API/action/tài nguyên có được phép truy cập không |

Nếu muốn chuẩn hóa `tenant_id` từ cách biểu diễn của issuer sang định dạng được API hiểu, đó thường là **claim-set conversion**. Nếu muốn buộc `tenant_id` phải thuộc allowlist, đó là **claim validation**. Nếu muốn tên trong `Authentication.getName()` là một claim khác, đó có thể là **principal mapping** chứ không phải sửa claim. Nếu muốn scope biến thành authority, đó là **authority mapping**.

## 2. Claims JSON và claims Java khác nhau thế nào?

JWT có cấu trúc JWS compact:

```text
base64url(header).base64url(payload).base64url(signature)
```

Giả sử payload JWT minh họa:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "web-portal",
  "preferred_username": "  phuong.nguyen  ",
  "tenant_id": 42,
  "scope": "orders.read orders.write",
  "iat": 1794715200,
  "exp": 1794718800
}
```

Đây là một JSON minh họa, **không phải token đã ký**. Sau khi JWT được parser xử lý và các chuyển đổi được áp dụng, ứng dụng có thể nhìn các giá trị như:

| Claim | Biểu diễn JSON | Cách ứng dụng Java thường muốn đọc |
|---|---|---|
| `iss` | Chuỗi issuer URI | `jwt.getIssuer()` hoặc chuỗi issuer theo contract |
| `sub` | Chuỗi | `jwt.getSubject()` |
| `aud` | Chuỗi hoặc mảng chuỗi | `jwt.getAudience()` trả danh sách audience |
| `iat` | NumericDate | `jwt.getIssuedAt()` trả `Instant` khi có |
| `exp` | NumericDate | `jwt.getExpiresAt()` trả `Instant` khi có |
| `nbf` | NumericDate nếu có | `jwt.getNotBefore()` trả `Instant` khi có |
| `tenant_id` | Chuỗi hoặc số theo hợp đồng issuer | Chuỗi hoặc kiểu domain có chủ đích, không tự suy đoán |
| `scope` | Chuỗi cách nhau bằng dấu cách, hoặc cấu trúc theo profile | Dữ liệu để authority converter xử lý |
| `preferred_username` | Chuỗi | Thuộc tính người dùng/username hiển thị nếu được phép dùng |
| `groups` | Mảng tên nhóm theo issuer | Danh sách, thường cần ánh xạ riêng để cấp authority |

Spring Security và Nimbus có bộ chuyển đổi claims mặc định phục vụ các registered JWT claims. Ví dụ điển hình là **thời gian sang `Instant` và audience sang danh sách**, giúp `Jwt` có API truy cập tiện lợi.

Dù vậy, **không được mặc định rằng claim tùy biến có kiểu giống hệt các claim chuẩn**. Parser JSON có thể tạo `Integer`, `Long`, các dạng `Number` hoặc `List<?>` tùy dữ liệu và thư viện. Cần biết hợp đồng claim của issuer và kiểu mà decoder hiện tại trả về.

### 2.1. Chuyển đổi không chứng minh claim đúng

Có thể đổi một số JSON thành chuỗi Java, ví dụ `42` → `"42"`. Nhưng phép chuyển đổi ấy **không xác nhận** tenant 42 tồn tại, người dùng có quyền trên tenant 42, hoặc token dành cho API đang nhận.

Tương tự, chuyển `exp` thành `Instant` mới giúp code **đọc được thời gian**; token có hết hạn hay chưa còn là trách nhiệm của timestamp validator.

### 2.2. Chuyển đổi không thay chữ ký JWS

Chữ ký JWS bảo vệ **byte representation của header và payload đã ký**. Claim-set converter hoạt động trên biểu diễn claims **sau quá trình đọc JWT**, để xây dựng đối tượng `Jwt` có cấu trúc phù hợp code. Nó không viết lại JWT rồi ký lại.

Vì vậy, sau conversion, một claim có thể nhìn khác dạng JSON ban đầu nhưng không có nghĩa Authorization Server đã ký chính **dạng Java đã chuyển đổi**. Đó là biểu diễn nội bộ mà decoder chấp nhận. Đừng sử dụng converter để hợp thức hóa claim bảo mật vốn sai với hợp đồng issuer.

## 3. `MappedJwtClaimSetConverter` làm gì?

Spring Security cung cấp class:

```java
org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter
```

Đây là một converter từ một claim map sang claim map:

```java
Converter<Map<String, Object>, Map<String, Object>>
```

Khi xây dựng `MappedJwtClaimSetConverter`, bạn có thể cung cấp những converter riêng cho **từng tên claim**. Thông thường cách thuận tiện và an toàn là dùng:

```java
MappedJwtClaimSetConverter.withDefaults(customConverters)
```

Phương thức này bắt đầu từ **các chuyển đổi claim mặc định** của Spring Security rồi thêm/thay converter được chỉ định trong `customConverters`.

Ví dụ:

```text
Dữ liệu claim được parser trả về:
  "exp"                  -> number
  "aud"                  -> list/string
  "tenant_id"            -> 42
  "preferred_username"   -> "  phuong.nguyen  "

MappedJwtClaimSetConverter.withDefaults(...):
  "exp"                  -> Instant, theo default converter
  "aud"                  -> danh sách audience, theo default converter
  "tenant_id"            -> "42", theo converter riêng
  "preferred_username"   -> "  phuong.nguyen  " hoặc theo rule riêng

Kết quả:
  Map<String,Object> được dùng để dựng đối tượng Jwt
```

Phần tùy chỉnh không nhất thiết được dùng để thay mọi field. **Nên giữ các default claim converters**, đặc biệt với những claim mà validator tiêu chuẩn dựa vào, như `exp`, `nbf` và issuer.

### 3.1. Vì sao `withDefaults(...)` quan trọng?

Nếu lập trình viên tự tạo một bộ chuyển đổi thay toàn bộ cấu trúc theo cách thiếu hiểu biết, code có thể làm mất kiểu chuẩn của những claims dùng trong API như:

```java
jwt.getExpiresAt()
jwt.getIssuedAt()
jwt.getAudience()
jwt.getIssuer()
```

Điều này có thể gây lỗi khi validators hoặc code downstream giả định claim đã được chuẩn hóa.

Khuyến nghị: **ghi đè đúng claim thật sự cần thay**, và bắt đầu từ defaults. Không tự chuyển đổi tất cả claims thành String bằng `Object.toString()`; đó có thể làm mất cấu trúc danh sách, thời gian và các kiểu dữ liệu quan trọng.

## 4. Chuyển một claim tùy chỉnh bằng `withDefaults(...)`

Giả sử issuer có hợp đồng cũ phát hành:

```json
"tenant_id": 42
```

nhưng API dùng mã tenant ở dạng chuỗi. Một cách chuyển đổi được kiểm soát:

```java
Converter<Object, Object> tenantIdConverter = value -> {
    if (value instanceof String text) {
        return text;
    }

    if (value instanceof Number number) {
        return number.toString();
    }

    // Giữ nguyên trường hợp bất thường để validator từ chối rõ ràng.
    return value;
};

Map<String, Converter<Object, ?>> overrides = new HashMap<>();
overrides.put("tenant_id", tenantIdConverter);

Converter<Map<String, Object>, Map<String, Object>> claimConverter =
    MappedJwtClaimSetConverter.withDefaults(overrides);
```

Các import:

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
```

Ở đây:

1. Nếu `tenant_id` là chuỗi, giữ nguyên.
2. Nếu là một số Java, chuyển sang chuỗi bằng `number.toString()`.
3. Nếu là kiểu khác, để validator kiểm tra thay vì âm thầm tạo giá trị ngẫu nhiên.
4. `withDefaults(...)` tiếp tục giữ các quy tắc chuyển đổi tiêu chuẩn cho registered claims.

**Cảnh báo quan trọng về định danh dạng số:** Nếu tenant ID trên thực tế là **một định danh** chứ không phải đại lượng số học, tốt nhất AS nên phát hành nó dưới dạng **chuỗi ngay từ đầu**. JSON number có thể gây mất leading zero, mất độ chính xác đối với số lớn hoặc tạo khác biệt biểu diễn (`42`, `42.0`). Chuyển `42` thành `"42"` chỉ hợp lệ khi **hai dạng đó đã được hợp đồng issuer xác nhận là cùng một định danh**.

### 4.1. Một lựa chọn đơn giản hơn: chuẩn hóa chuỗi

Nếu issuer gửi claim phụ phục vụ hiển thị:

```json
"preferred_username": "  phuong.nguyen  "
```

có thể chuẩn hóa khoảng trắng hai đầu:

```java
Converter<Object, Object> usernameConverter = value -> {
    if (value instanceof String text) {
        return text.strip();
    }
    return value;
};

Map<String, Converter<Object, ?>> overrides = new HashMap<>();
overrides.put("preferred_username", usernameConverter);

Converter<Map<String, Object>, Map<String, Object>> converter =
    MappedJwtClaimSetConverter.withDefaults(overrides);
```

Ví dụ này minh họa chuyển đổi dữ liệu đơn giản. Nhưng **tên hiển thị không nên thay thế định danh ổn định `sub`** cho mục đích truy cập tài khoản, ownership hoặc audit chỉ vì dễ nhìn hơn.

### 4.2. Chuyển đổi cần nhất quán với cách validator đọc claims

Nếu converter biến `tenant_id` thành String, validator nên kiểm tra **String**, thay vì vừa cho phép Number vừa cho phép String theo nhiều cách không tương thích.

Ví dụ:

```java
OAuth2TokenValidator<Jwt> tenantValidator = jwt -> {
    Object raw = jwt.getClaim("tenant_id");

    if (raw instanceof String tenant && "42".equals(tenant)) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Unexpected tenant_id claim",
            null
        )
    );
};
```

Converter **chuyển kiểu**; validator **ra quyết định chấp nhận**. Nếu phép chuyển kiểu không có quy tắc rõ ràng, đừng chấp nhận mọi giá trị sau khi dùng `String.valueOf(...)`.

## 5. Gắn claim converter vào `NimbusJwtDecoder`

`NimbusJwtDecoder` cho phép đặt claim-set converter:

```java
decoder.setClaimSetConverter(claimConverter);
```

Ví dụ tổng thể, Resource Server tin issuer `shop` và yêu cầu audience `orders-api`:

```java
@Configuration
public class JwtDecoderConfiguration {

    private static final String ISSUER =
        "https://login.example.test/realms/shop";

    private static final String AUDIENCE =
        "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        Converter<Object, Object> tenantToString = value -> {
            if (value instanceof String text) {
                return text;
            }
            if (value instanceof Number number) {
                return number.toString();
            }
            return value;
        };

        Map<String, Converter<Object, ?>> overrides = new HashMap<>();
        overrides.put("tenant_id", tenantToString);

        decoder.setClaimSetConverter(
            MappedJwtClaimSetConverter.withDefaults(overrides)
        );

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for orders-api",
                    null
                )
            );
        };

        OAuth2TokenValidator<Jwt> tenantValidator = jwt -> {
            Object raw = jwt.getClaim("tenant_id");
            if (raw instanceof String tenant &&
                    "42".equals(tenant)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Unexpected tenant",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audienceValidator,
                tenantValidator
            )
        );

        return decoder;
    }
}
```

Các import cho ví dụ:

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
```

### 5.1. Cách đọc cấu hình trên

- `withIssuerLocation(ISSUER)` xây dựng decoder dựa trên issuer được tin cậy và cơ chế khám phá metadata/JWKS phù hợp.
- `tenantToString` chỉ tác động đến một claim riêng do issuer phát hành.
- `MappedJwtClaimSetConverter.withDefaults(overrides)` giữ những chuyển đổi mặc định cho claims chuẩn.
- `setClaimSetConverter(...)` nối converter vào bước xử lý claim-set của decoder.
- `JwtValidators.createDefaultWithIssuer(ISSUER)` bảo lưu validation issuer/thời gian phù hợp với phiên bản Spring Security.
- `audienceValidator` kiểm tra token được cấp cho API này.
- `tenantValidator` áp dụng chính sách tenant **sau khi claim đã được chuyển kiểu**.
- `DelegatingOAuth2TokenValidator` ghép các điều kiện bắt buộc.

Nếu một tenant khác cũng được API này phục vụ, **đừng hardcode tenant bằng `"42"`** ở decoder toàn cục. Khi đó validator có thể chỉ kiểm tra cấu trúc claim, còn quyền truy cập tenant của từng request cần được đánh giá ở tầng authorization nghiệp vụ.

### 5.2. Kết nối với Servlet `SecurityFilterChain`

```java
@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Sau khi JWT được xác minh và các validators chấp nhận, Spring Security có thể chuyển `scope=orders.read` thành authority `SCOPE_orders.read`. Một token có audience đúng và tenant đúng nhưng **thiếu scope** vẫn phải bị từ chối khi gọi endpoint yêu cầu quyền đọc.

## 6. `withDefaults(...)` khác với một Converter tự viết từ đầu

Giả sử bạn muốn chỉnh một claim tùy biến và giữ nguyên toàn bộ claims khác. Có hai cách, nhưng mục đích khác nhau.

**Cách A — Ghi đè conversion của một claim:**

```java
Map<String, Converter<Object, ?>> overrides = new HashMap<>();
overrides.put("tenant_id", tenantToString);

Converter<Map<String, Object>, Map<String, Object>> converter =
    MappedJwtClaimSetConverter.withDefaults(overrides);
```

Ở đây mỗi converter được chỉ định theo **tên claim**. Phù hợp khi chỉ cần đổi **giá trị/kiểu của claim đã có**.

**Cách B — Dùng một converter cho toàn bộ map:** Nếu muốn sao chép hoặc thêm một claim mới dựa vào claim khác, cần đọc nhiều giá trị trong claim map; chỉ một converter theo tên claim có thể không đủ.

Ví dụ: AS cấp `preferred_username`; ứng dụng muốn tạo một claim nội bộ `display_name` nhưng **không sửa `sub`**.

```java
Converter<Map<String, Object>, Map<String, Object>> defaults =
    MappedJwtClaimSetConverter.withDefaults(Map.of());

Converter<Map<String, Object>, Map<String, Object>> claimSetConverter =
    rawClaims -> {
        Map<String, Object> normalized =
            new LinkedHashMap<>(defaults.convert(rawClaims));

        Object username = normalized.get("preferred_username");

        if (username instanceof String text && !text.isBlank()) {
            normalized.put("display_name", text.strip());
        }

        return normalized;
    };

decoder.setClaimSetConverter(claimSetConverter);
```

Imports bổ sung:

```java
import java.util.LinkedHashMap;
```

Điểm cần chú ý:

1. Converter ngoài gọi `MappedJwtClaimSetConverter.withDefaults(Map.of())` để **không bỏ chuyển đổi registered claims**.
2. Tạo một `LinkedHashMap` mới từ kết quả, tránh phụ thuộc map kết quả có mutable hay không.
3. Chỉ thêm `display_name` khi giá trị gốc đúng kiểu và không rỗng.
4. Không xóa `iss`, `aud`, `exp` hoặc `sub`.
5. Token validators vẫn phải quyết định JWT đã được chấp nhận tại API chưa.

`display_name` là dữ liệu trình bày của ứng dụng, không phải bằng chứng người dùng đã xác minh tên pháp lý. Không dùng nó làm khóa chính nhận diện tài khoản nếu có thể thay đổi hoặc trùng người dùng.

### 6.1. Trường hợp cần đổi tên claim

Giả sử AS có claim legacy `legacy_user_name` nhưng code giao diện muốn đọc `display_name`. Có thể:

- Dùng converter toàn claim map để **thêm một alias** `display_name` từ `legacy_user_name`, giữ original claim.
- Sửa code ở boundary của ứng dụng để đọc đúng claim gốc.
- Điều chỉnh hợp đồng issuer để AS phát hành claim chuẩn hơn, nếu bạn quản lý được AS.

**Không tự đổi `legacy_user_name` thành `sub`** chỉ để `Authentication.getName()` đẹp hơn. `sub` là định danh chủ thể cốt lõi theo issuer, có ý nghĩa liên quan ownership, audit và tenant. Thay `sub` có thể khiến ứng dụng gán quyền cho sai principal.

### 6.2. Khi cần loại bỏ một claim

Một số converter có thể dùng `null` làm kết quả để loại bỏ claim được ánh xạ, tùy hành vi triển khai của `MappedJwtClaimSetConverter`. Tuy nhiên, **không dùng loại bỏ claim như một cách “bỏ qua validation”**. Việc xóa `exp`, `iss`, `aud` hoặc claim xác định quyền có thể làm hệ thống mất khả năng đánh giá token đúng cách.

Nếu mục đích chỉ là **không trả claim nhạy cảm ra response**, giải pháp thích hợp thường là **lọc dữ liệu tại controller/DTO**, không phải thay đổi tập claims mà mọi tầng bảo mật dựa vào.

## 7. Chuyển kiểu số, chuỗi, thời gian và danh sách

Đây là những tình huống phổ biến khi tùy biến claim-set converter.

### 7.1. NumericDate nên được giữ ở kiểu thời gian của Spring

JWT có:

```json
{
  "iat": 1794715200,
  "nbf": 1794715200,
  "exp": 1794718800
}
```

Các giá trị này là NumericDate theo JWT, thường thể hiện số giây kể từ Unix epoch. Spring Security sử dụng kiểu thời gian phù hợp trong `Jwt`, ví dụ `Instant`, để validator thời gian và code sử dụng.

Khi chỉ cần chỉnh `tenant_id` hay `preferred_username`, **không nên viết converter toàn map biến mọi Number thành String**. Làm vậy có thể khiến `getExpiresAt()` hoặc timestamp validation sai kiểu và hoạt động không đúng kỳ vọng.

Nếu issuer gửi thời gian theo một định dạng không đúng hợp đồng JWT (ví dụ số mili giây nhưng đặt tên `exp`), **ưu tiên sửa issuer**. Việc sửa ngầm ở Resource Server có thể che giấu sai lệch chuẩn và làm nhiều hệ thống diễn giải cùng một token khác nhau.

### 7.2. Audience là danh sách, không chỉ một chuỗi

JSON có thể viết:

```json
"aud": "orders-api"
```

hoặc:

```json
"aud": ["orders-api", "inventory-api"]
```

Code Spring Security nên kiểm tra bằng `jwt.getAudience()` thay vì giả định `jwt.getClaim("aud")` luôn là String:

```java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    boolean valid = jwt.getAudience().contains("orders-api");

    return valid
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Wrong audience",
                null
            )
        );
};
```

Định danh `orders-api` là **Resource Server**; không dùng `client_id` của ứng dụng gọi thay thế audience.

Nếu đang chuyển đổi claim `aud` tùy biến, cần giữ đúng ngữ nghĩa JWT: audience phải đại diện cho đối tượng được phép nhận token, không được mặc nhiên thêm audience của API hiện tại vào token chỉ để vượt validation. Làm như vậy có thể biến một token dành cho API khác thành token được chấp nhận sai mục đích.

### 7.3. Claims dạng danh sách và nhóm

Một số AS cấp:

```json
{
  "groups": ["sales", "support"],
  "roles": ["ORDER_VIEWER"]
}
```

Hệ thống khác có thể trả chuỗi:

```json
{
  "groups": "sales support",
  "roles": "ORDER_VIEWER"
}
```

Hai biểu diễn **không tự có cùng ngữ nghĩa**. Nếu hợp đồng AS quy định danh sách cách nhau bởi dấu cách, có thể chuyển đổi theo quy tắc đó; nhưng cần xử lý escape, khoảng trắng, tên nhóm có dấu cách và duplicate.

Ví dụ một claim tùy chỉnh `tags` có hợp đồng chuỗi cách nhau bởi dấu phẩy, converter có thể:

```java
Converter<Object, Object> tagsConverter = value -> {
    if (value instanceof String text) {
        return Arrays.stream(text.split(","))
            .map(String::strip)
            .filter(item -> !item.isEmpty())
            .distinct()
            .toList();
    }
    return value;
};
```

Import:

```java
import java.util.Arrays;
```

**Chỉ dùng cách tách này khi định dạng đầu vào được xác định rõ**: dấu phẩy thực sự là delimiter và không phải một phần hợp lệ bên trong tag. Với `groups` hoặc `roles` dùng để cấp quyền, không nên tự đoán delimiter.

### 7.4. Number và định danh có leading zero

Giả sử AS đưa:

```json
{"merchant_code": 123}
```

nhưng database lưu `"00123"`. Không thể khôi phục leading zeros từ JSON number `123` nếu issuer đã bỏ thông tin đó. Claim converter không thể suy ra người dùng thực sự là merchant `00123` hay `123` nếu hợp đồng không nói.

**Khóa định danh nên có biểu diễn ổn định**, thường là chuỗi. Với claim có giá trị số học, hãy dùng kiểm tra kiểu/range, không ép sang String vô điều kiện.

## 8. Phân biệt claim conversion và principal name mapping

Trong Resource Server, principal mà Spring Security đưa vào `Authentication` có tên định danh, thường lấy từ claim `sub`.

Một JWT:

```json
{
  "sub": "9d7e1b48-5d53-4ecb-a321-b9fafbe1ae38",
  "preferred_username": "phuong.nguyen",
  "email": "user@example.test"
}
```

Có ba khái niệm khác nhau:

| Khái niệm | Ví dụ | Nên dùng cho gì? |
|---|---|---|
| `sub` | UUID/subject ổn định của issuer | Nhận diện principal và liên kết quyền/tài nguyên nếu hợp đồng bảo đảm |
| `preferred_username` | `phuong.nguyen` | Tên đăng nhập/hiển thị, có thể thay đổi |
| `email` | `user@example.test` | Thông tin liên hệ, không mặc nhiên định danh chính |

Nếu API muốn `Authentication.getName()` dùng một claim khác, Spring Security có **`JwtAuthenticationConverter.setPrincipalClaimName(...)`**. Đây thường là công cụ phù hợp hơn việc sửa `sub` trong claim-set converter.

```java
JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setPrincipalClaimName("preferred_username");
```

Sau đó gắn converter vào JWT Resource Server:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();

    authenticationConverter.setPrincipalClaimName(
        "preferred_username"
    );

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(authenticationConverter)
            )
        )
        .build();
}
```

Imports liên quan:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;
```

**Lưu ý bảo mật:** Chỉ chọn `preferred_username` làm principal name khi issuer bảo đảm claim đó luôn có, có ý nghĩa ổn định cần thiết và không gây nhầm danh tính. Với hệ thống cần ánh xạ ownership hoặc audit chính xác, giữ `sub` là cách thường an toàn hơn; tên hiển thị có thể đọc riêng bằng `@AuthenticationPrincipal Jwt`.

### 8.1. Đọc `Jwt` trong controller mà không đổi principal name

```java
@GetMapping("/api/me")
public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of(
        "subject", jwt.getSubject(),
        "username", jwt.getClaimAsString("preferred_username")
    );
}
```

Code trên là minh họa, giả định claim `preferred_username` tồn tại; `Map.of(...)` không chấp nhận giá trị null. Trong code thực tế, xử lý trường hợp claim vắng mặt và chỉ trả dữ liệu được phép công bố.

Việc controller đọc claims sau khi Spring Security xác thực token **khác** việc controller tự decode Base64URL rồi tin payload.

## 9. Phân biệt claim conversion và authority mapping

Nhiều hệ thống muốn chuyển claim `scope`, `scp`, `permissions` hoặc `roles` thành `GrantedAuthority`.

Đây là việc của **`JwtGrantedAuthoritiesConverter`** kết hợp `JwtAuthenticationConverter`, không phải mặc định của `MappedJwtClaimSetConverter`.

### 9.1. Scope chuẩn

Token:

```json
{"scope": "orders.read orders.write"}
```

Trong cấu hình thông dụng, Spring Security chuyển thành:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Rồi authorization có thể dùng:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

### 9.2. Claim quyền tùy chỉnh

Giả sử issuer có contract:

```json
{
  "permissions": ["orders:read", "orders:export"]
}
```

Bạn có thể cấu hình converter authority:

```java
JwtGrantedAuthoritiesConverter authoritiesConverter =
    new JwtGrantedAuthoritiesConverter();

authoritiesConverter.setAuthoritiesClaimName("permissions");
authoritiesConverter.setAuthorityPrefix("PERM_");

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(
    authoritiesConverter
);
```

Imports:

```java
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
```

Khi đó `orders:read` có thể được ánh xạ thành `PERM_orders:read`. Nếu có nhiều nguồn quyền cần hợp nhất, có thể dùng một authority converter kết hợp phù hợp; không tự động tin mọi claim giống tên role.

**Phân biệt rõ:**

- **Claim-set converter:** `permissions` có hình dạng/kiểu Java nào?
- **Authority converter:** `permissions` được dịch thành quyền Spring Security nào?
- **Authorization:** Endpoint này yêu cầu authority nào?

Nếu tên claim bị lạ, không nhất thiết phải **đổi tên claim gốc** bằng `MappedJwtClaimSetConverter`: thay `authoritiesClaimName` trong `JwtGrantedAuthoritiesConverter` có thể đơn giản và an toàn hơn.

### 9.3. Không tùy tiện nâng quyền ở tầng conversion

Sai về mặt bảo mật:

```text
JWT có groups=["users"]
  -> tự thêm claim "roles": ["ADMIN"] trong claim-set converter
  -> JwtAuthenticationConverter cấp ROLE_ADMIN
```

Một converter chạy trong Resource Server không có thẩm quyền **tự nâng quyền** chỉ để code nội bộ tiện sử dụng. Mapping từ claim sang authority phải phản ánh **chính sách và hợp đồng quyền đã được issuer chứng thực**, được review và giới hạn rõ.

## 10. Cần chuyển đổi hay validate claim?

Hãy xét bốn nhu cầu:

| Nhu cầu | Công cụ phù hợp | Ví dụ |
|---|---|---|
| Chuyển định dạng claim theo contract | `MappedJwtClaimSetConverter` hoặc converter claim-set | `tenant_id` Number → String, `tags` CSV → List |
| Bắt token đáp ứng một điều kiện | `OAuth2TokenValidator<Jwt>` / `JwtClaimValidator<T>` | `aud` chứa `orders-api`; tenant thuộc allowlist |
| Chọn tên principal / authority | `JwtAuthenticationConverter` / `JwtGrantedAuthoritiesConverter` | Principal từ `sub` hoặc claim khác; `permissions` → `PERM_...` |
| Kiểm tra quyền endpoint/tài nguyên | `authorizeHttpRequests`, method security, service | Scope đọc, tenant/ownership của đơn hàng |

### 10.1. Ví dụ: tenant_id là chuỗi nhưng rỗng

Token đã ký có:

```json
"tenant_id": ""
```

Claim-set converter có thể giữ chuỗi rỗng vì nó vốn là String. Nếu contract cấm giá trị rỗng, **validator phải từ chối**:

```java
OAuth2TokenValidator<Jwt> tenantPresence = jwt -> {
    Object value = jwt.getClaim("tenant_id");

    if (value instanceof String text && !text.isBlank()) {
        return OAuth2TokenValidatorResult.success();
    }

    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Missing or blank tenant_id",
            null
        )
    );
};
```

Converter không nên tự thay tenant rỗng bằng tenant mặc định của Resource Server; điều đó có thể biến một token lỗi thành token hợp lệ ngoài ý định của AS.

### 10.2. Ví dụ: quyền đọc đơn hàng số 42

Token có:

```json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Không có converter hoặc validator chung nào xác nhận `user-123` có quyền đọc **đơn hàng 42**, trừ khi hệ thống có contract rất cụ thể về đối tượng trong token. Đây là quyền nghiệp vụ: controller/service hoặc method security cần đối chiếu ownership, tenant và chính sách chia sẻ.

## 11. Những thay đổi claim có thể làm hỏng bảo mật

Không phải mọi thao tác chuẩn hóa đều vô hại. Đặc biệt, những claims sau có vai trò trong JWT validation:

| Claim | Nguy cơ khi đổi tùy tiện |
|---|---|
| `iss` | Có thể hợp thức hóa token từ issuer/realm không được phép nếu tự thay issuer sai thành issuer đúng |
| `aud` | Có thể cho phép token dành cho API khác đi qua audience validator |
| `exp`, `nbf` | Có thể kéo dài thời hạn, bỏ thời điểm bắt đầu hiệu lực hoặc làm sai time validation |
| `sub` | Có thể gán request cho sai người dùng/service principal |
| `client_id` | Có thể giả mạo danh tính ứng dụng nhận token nếu dùng làm policy |
| `scope`, `permissions`, `roles` | Có thể cấp quyền quá mức nếu tự thêm/đổi giá trị |
| `cnf` | Có thể làm sai cơ chế sender-constrained access token (DPoP/mTLS binding) nếu hệ thống dùng |
| `jti` | Có thể ảnh hưởng cơ chế chống replay/denylist/audit nếu dựa vào JWT ID |

Ví dụ đặc biệt nguy hiểm:

```java
// MINH HỌA KHÔNG AN TOÀN:
// Không được tự sửa audience để token dành cho API khác trở thành hợp lệ.
normalized.put("aud", List.of("orders-api"));

// Không được xóa exp vì token hết hạn.
normalized.remove("exp");

// Không được tự đặt sub cho một user mặc định.
normalized.put("sub", "admin-user");
```

**Không dùng claim-set converter để “sửa” token không đáp ứng hợp đồng xác thực.** Nếu AS phát hành audience sai, cần sửa cấu hình AS/token request hoặc validator expectation. Nếu thời hạn sai, cần sửa đồng hồ và cấu hình issuer, không xóa claim.

### 11.1. Chuẩn hóa phải có lý do và dữ liệu nguồn đáng tin

Một converter chỉ nhận thông tin đã nằm trong JWT được issuer ký. Nếu chuyển đổi từ `legacy_user_name` sang `display_name`, bạn đang đổi biểu diễn thông tin đã được issuer gửi.

Tuy nhiên, ánh xạ `legacy_role=admin` sang `ROLE_ADMIN` là **quyết định quyền truy cập**. Cần có hợp đồng rằng `legacy_role` thực sự có nghĩa đó, quyền tương ứng được phép sử dụng tại API, và mọi issuer được chấp nhận đều tuân cùng ngữ nghĩa.

### 11.2. Xử lý sai kiểu: đừng biến lỗi thành giá trị hợp lệ

Giả sử `tenant_id` theo contract phải là String, nhưng issuer bất ngờ gửi object:

```json
{"tenant_id": {"value": "shop"}}
```

Một converter dùng `String.valueOf(value)` có thể tạo chuỗi như `"{value=shop}"`, làm code downstream gặp lỗi hoặc vô tình match theo những quy tắc lạ. Tốt hơn là **giữ nguyên kiểu bất thường để validator phát hiện**, hoặc fail validation theo quy tắc rõ ràng; không tự suy luận cách đọc dữ liệu không có trong hợp đồng.

## 12. Claim converter và các validator mặc định phải đi cùng nhau

Một JWT decoder cần nhiều điều kiện:

1. JWT được ký bằng khóa của issuer tin cậy.
2. Thời gian JWT hợp lệ.
3. Issuer `iss` khớp.
4. Audience `aud` dành cho API.
5. Các claim bắt buộc theo hợp đồng, ví dụ `tenant_id`.
6. Token type phù hợp profile access token, không nhầm OIDC ID token.

`MappedJwtClaimSetConverter` **không thay** những bước này. Nó chỉ giúp điều chỉnh claims về cấu trúc/kiểu.

Khi khai báo decoder tùy biến, nên bảo lưu validators tiêu chuẩn:

```java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        tenantValidator
    )
);
```

Nếu chỉ thêm:

```java
decoder.setJwtValidator(tenantValidator);
```

mà không kết hợp những validators còn lại, có thể mất kiểm tra issuer/thời gian do `setJwtValidator(...)` thay toàn bộ validator hiện có. Đây là vấn đề cấu hình **validation**, khác với việc tạo `MappedJwtClaimSetConverter.withDefaults(...)` để giữ default **conversions**.

Nhớ hai chữ “defaults” nằm ở **hai nơi khác nhau**:

- **`MappedJwtClaimSetConverter.withDefaults(...)`:** giữ bộ chuyển đổi kiểu claim mặc định.
- **`JwtValidators.createDefaultWithIssuer(...)`:** giữ bộ validator JWT mặc định cùng điều kiện issuer.

Chúng phục vụ hai trách nhiệm, nên một cái **không thay thế cái còn lại**.

## 13. Có thể tạo claim mặc định khi thiếu không?

Có thể viết converter thêm một claim khi thiếu, nhưng cần phân biệt **giá trị hỗ trợ hiển thị** với **giá trị dùng cho bảo mật**.

Ví dụ nếu `display_name` là trường chỉ dùng cho giao diện và thiếu, có thể dùng `preferred_username` hoặc giá trị placeholder do ứng dụng chọn:

```java
Converter<Map<String, Object>, Map<String, Object>> defaults =
    MappedJwtClaimSetConverter.withDefaults(Map.of());

Converter<Map<String, Object>, Map<String, Object>> converter = raw -> {
    Map<String, Object> claims =
        new LinkedHashMap<>(defaults.convert(raw));

    if (!claims.containsKey("display_name")) {
        Object source = claims.get("preferred_username");
        if (source instanceof String name && !name.isBlank()) {
            claims.put("display_name", name);
        }
    }

    return claims;
};
```

Nhưng **không tự điền những claim bảo mật bắt buộc** như:

- `sub` khi thiếu subject.
- `tenant_id` khi dùng tenant để phân quyền.
- `aud` khi token không dành cho API.
- `exp` khi token thiếu expiry mà contract yêu cầu.
- `roles=ADMIN` khi issuer không cấp quyền.

Giá trị bổ sung cho mục đích UI nên được ghi rõ là **derived/internal**, không được gọi là một claim xác thực mà AS đã phát hành.

## 14. Phân tích trường hợp nhiều issuers

Một Resource Server có thể nhận JWT từ hai issuers:

```text
Issuer A:
  https://login.example.test/realms/customers
  claim "tenant_id": "shop"

Issuer B:
  https://login.example.test/realms/partners
  claim "organization": "partner-shop"
```

Có thể muốn chuẩn hóa cả hai về một trường nội bộ `tenant_code`. Tuy nhiên, trước khi làm vậy phải bảo đảm:

- Cả A và B đều là issuer **được cấu hình tin cậy**.
- Decoder/JWKS đúng issuer được sử dụng.
- Claims `tenant_id` và `organization` có ý nghĩa tương đương theo hợp đồng.
- Không có issuer nào sử dụng cùng tên claim nhưng nghĩa hoàn toàn khác.
- Audience và loại access token của từng issuer được xác thực riêng.
- Quyền truy cập tenant sau conversion vẫn được kiểm tra theo chính sách.

**Không dùng một converter toàn cục lỏng lẻo để tự hợp nhất danh tính** từ các issuers khác nhau chỉ vì hai chuỗi trông giống nhau. Một người dùng có cùng username ở hai realms không nhất thiết là cùng một subject.

### 14.1. Ngữ cảnh principal phải gắn với issuer

Khi sử dụng `sub` để xác định người dùng, một mô hình an toàn thường gắn danh tính với cặp:

```text
(iss, sub)
```

chứ không chỉ `sub` khi chấp nhận nhiều issuers.

Chuyển `sub` về một username ngắn hoặc bỏ issuer khỏi khóa danh tính có thể khiến hai tài khoản khác nhau bị gộp nhầm. Nếu cần xây dựng identity nội bộ, nên làm theo một chính sách mapping đã được kiểm chứng, không tùy ý viết trong converter và giả định tính duy nhất.

## 15. Đọc claims trong controller và service

Sau khi decoder chấp nhận JWT và Spring Security tạo Authentication, controller có thể đọc principal:

```java
@RestController
@RequestMapping("/api")
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        Map<String, Object> result = new LinkedHashMap<>();

        result.put("subject", jwt.getSubject());
        result.put("tenantId", jwt.getClaimAsString("tenant_id"));
        result.put("displayName", jwt.getClaimAsString("display_name"));

        return result;
    }
}
```

Imports:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
```

Đây chỉ là ví dụ API học tập. Trong production, không nên trả toàn bộ claims/credentials ra response. Với các claims có thể không tồn tại, `LinkedHashMap` cho phép đặt giá trị null; nhưng hợp đồng response nên quyết định có bỏ field hoặc trả giá trị mặc định hay không.

Nếu dùng `@AuthenticationPrincipal Jwt`, controller nhận **Jwt đã được Resource Server xác thực** theo cấu hình filter chain, khác với tự tách JWT từ header rồi dùng Base64URL.

### 15.1. Không biến DTO thành bằng chứng phân quyền

Một DTO trả `tenantId=shop` không tự chứng minh caller có quyền thao tác mọi resource của tenant đó. Service vẫn phải kiểm tra quyền trên từng bản ghi, phạm vi scope, chia sẻ dữ liệu và chính sách nghiệp vụ.

## 16. Phân biệt lỗi claim conversion với lỗi validation

Xét một token có chữ ký hợp lệ và claims:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["orders-api"],
  "tenant_id": {"unexpected": "object"},
  "exp": 1900000000
}
```

Có ít nhất ba cách hệ thống xử lý:

**Trường hợp A — Converter biết kiểu Number/String, gặp Object thì giữ nguyên:** Sau conversion, `tenantValidator` kiểm tra `tenant_id` phải là String và trả `failure(...)`. Đây là lỗi **claim validation**.

**Trường hợp B — Converter không an toàn và ném exception runtime:** Tùy cách decoder xử lý exception, request có thể gặp lỗi giải mã hoặc lỗi hạ tầng. Không nên dựa vào một `ClassCastException` không được xử lý để đạt HTTP response bảo mật mong muốn.

**Trường hợp C — Converter tự biến Object thành chuỗi:** Code tiếp tục với một giá trị không được hợp đồng định nghĩa, có nguy cơ lệch nghiệp vụ. Đây là phương án nên tránh với claim nhận diện/quyền.

Đối với các claims bắt buộc, nên chọn chiến lược **chuyển đổi có kiểm soát + validator tường minh** để dễ xác định đầu vào hợp lệ.

### 16.1. Sai issuer/audience không phải vấn đề converter

Nếu token có:

```json
"aud": ["payments-api"]
```

trong khi Orders API yêu cầu `orders-api`, **không được** viết converter tự thêm `orders-api` vào audience. Token phải bị audience validator từ chối.

Nếu token hết hạn, **không được** dùng converter tự tăng `exp`. Token đã hết hạn phải bị thời gian validator từ chối.

Nếu JWT sai chữ ký, **không có claim converter nào được phép khiến token trở thành hợp lệ**.

## 17. Các tình huống học tập và kết luận

### Tình huống 1 — Issuer gửi `tenant_id=42`, API cần `"42"`

Hợp đồng xác nhận định danh tenant dạng số 42 và chuỗi `"42"` cùng nghĩa, không có leading zero hoặc giá trị lớn vượt giới hạn parser.

**Cách làm:** `MappedJwtClaimSetConverter.withDefaults(...)` chuyển Number → String cho `tenant_id`; thêm validator kiểm tra tenant nằm trong danh sách được phép. Không đổi `iss`, `aud`, `sub` hay `exp`.

### Tình huống 2 — Muốn `Authentication.getName()` là `preferred_username`

**Cách làm:** Xem xét `JwtAuthenticationConverter.setPrincipalClaimName(...)` nếu contract cho phép và yêu cầu về tính ổn định đã được giải quyết. Không tự đổi claim `sub` chỉ để thay tên hiển thị.

### Tình huống 3 — Claim `permissions` chứa danh sách quyền

**Cách làm:** Nếu dữ liệu đã đúng cấu trúc, cấu hình `JwtGrantedAuthoritiesConverter.setAuthoritiesClaimName("permissions")` và prefix phù hợp. Không cần đổi tên claim bằng claim-set converter chỉ để ánh xạ quyền.

### Tình huống 4 — JWT chứa `exp` dưới dạng NumericDate

**Cách làm:** Giữ default conversion để `Jwt.getExpiresAt()` hoạt động với `Instant` và time validator kiểm tra hiệu lực. Không dùng converter toàn map biến mọi value thành String.

### Tình huống 5 — Thiếu `tenant_id` nhưng API yêu cầu bắt buộc

**Cách làm:** Validator từ chối token. Không âm thầm điền một tenant mặc định nếu tenant đó liên quan phân quyền.

### Tình huống 6 — Token có `aud=payments-api` nhưng client gọi Orders API

**Cách làm:** Audience validator từ chối. Không dùng converter “sửa audience” cho khớp API.

### Tình huống 7 — Issuer A và B đều dùng `sub=user-1`

**Cách làm:** Khi đa issuer, xác định identity theo issuer + subject hoặc mapping tin cậy tương ứng. Không tự gộp hai accounts từ hai issuers vì cùng `sub`.

### Tình huống 8 — Claim `groups` là chuỗi nhưng backend cần Set

**Cách làm:** Chỉ chuyển đổi khi issuer có contract delimiter và ngữ nghĩa rõ, hoặc yêu cầu issuer phát hành mảng đúng kiểu. Nếu `groups` quyết định quyền, authority mapping và authorization phải được xác định riêng, tránh suy diễn nhóm thành quyền cao hơn.

## 18. Unit test cho claim converter và kiểm tra tích hợp

Khi phát triển chuyển đổi tùy biến, cần phân biệt thử **logic chuyển kiểu** với thử **JWT xác thực thực tế**.

Một unit test có thể gọi trực tiếp claim-set converter:

```java
@Test
void tenantIdIsConvertedAndStandardClaimsRemainAvailable() {
    Converter<Object, Object> tenantToString = value -> {
        if (value instanceof Number number) {
            return number.toString();
        }
        return value;
    };

    Map<String, Converter<Object, ?>> overrides = new HashMap<>();
    overrides.put("tenant_id", tenantToString);

    Converter<Map<String, Object>, Map<String, Object>> converter =
        MappedJwtClaimSetConverter.withDefaults(overrides);

    Map<String, Object> raw = new HashMap<>();
    raw.put("tenant_id", 42);
    raw.put("aud", List.of("orders-api"));
    raw.put("exp", 1900000000L);

    Map<String, Object> result = converter.convert(raw);

    assertEquals("42", result.get("tenant_id"));
    assertTrue(result.containsKey("aud"));
    assertInstanceOf(Instant.class, result.get("exp"));
}
```

Imports bổ sung cho test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.jwt.MappedJwtClaimSetConverter;
```

**Unit test này không xác minh chữ ký JWT**: nó chỉ cho thấy map converter xử lý values theo kỳ vọng. Kiểm tra tích hợp phải dùng JWT test có chữ ký phù hợp, đi qua `JwtDecoder` thật, kiểm tra issuer, audience, thời gian và converter/validator trong cấu hình Spring Security.

Một bộ tình huống kỹ thuật cho integration có thể xét:

| Tình huống | Kỳ vọng |
|---|---|
| JWT chữ ký hợp lệ, issuer/audience/time đúng, tenant có thể chuyển kiểu | Decode thành công và trả claim đã chuẩn hóa |
| JWT chữ ký sai, claims trông đúng | Decoder từ chối trước khi tin claims |
| JWT đúng chữ ký nhưng audience khác | Audience validator từ chối |
| JWT hết hạn | Timestamp validator từ chối |
| Tenant sai kiểu và không có quy tắc chuyển hợp lệ | Tenant validator từ chối |
| Tenant rỗng/thiếu khi bắt buộc | Validator từ chối |
| JWT đúng claims nhưng thiếu scope endpoint | Authentication có thể thành công, authorization từ chối |
| JWT có tên hiển thị đổi nhưng `sub` không đổi | Identity ổn định vẫn được bảo toàn nếu dùng subject |

Các kịch bản này là nội dung học cách thiết kế ranh giới dữ liệu, không phải yêu cầu tự chạy test trong một bài viết kiến thức.

## 19. Những sai lầm cần tránh khi điều chỉnh claims

| Sai lầm | Tác hại | Hướng đúng |
|---|---|---|
| Tự parse Base64URL JWT rồi lấy username để cấp quyền | Tin dữ liệu chưa xác thực | Để Spring Security decoder xác thực trước |
| Viết converter toàn map biến mọi claim thành String | Phá kiểu thời gian, mảng, định danh | Chỉ override claims cần thiết, giữ defaults |
| Sửa `aud` cho khớp API | Nhận token dành cho resource khác | Từ chối bằng audience validator |
| Sửa `exp` hoặc xóa `nbf` | Làm yếu thời hạn token | Giữ dữ liệu chuẩn và chạy timestamp validator |
| Thay `sub` bằng display name | Nhầm identity, sai ownership/audit | Dùng `JwtAuthenticationConverter` hoặc DTO hiển thị |
| Dùng `client_id` thay audience | Nhầm ứng dụng xin token với Resource Server | Kiểm tra issuer + expected audience |
| Từ `groups` suy ra ADMIN không có contract | Nâng quyền ngoài ý định issuer | Chỉ ánh xạ authority theo hợp đồng bảo mật |
| Bỏ issuer validator khi custom decoder | Tin token từ issuer không mong muốn | Giữ `JwtValidators.createDefaultWithIssuer(...)` |
| Nuốt exception và chấp nhận token | Fail open | Xác thực không đạt thì từ chối |
| Kết hợp claims của nhiều issuers bằng tên giống nhau | Va chạm định danh/quyền | Ánh xạ issuer-specific có chính sách rõ |

### 19.1. Không nhầm “display name” với identity

Một claim như `preferred_username` có thể đổi khi người dùng đổi tên. `sub` thường được thiết kế để nhận diện chủ thể ổn định trong phạm vi issuer. Đừng để normalization của tên hiển thị làm thay đổi principal mà business services dùng để kiểm tra quyền sở hữu dữ liệu.

### 19.2. Không dùng conversion để giải quyết lỗi bảo mật

Nếu JWT không phù hợp hợp đồng, sửa ở **nguồn phát hành** hoặc **validator/chính sách**. Conversion là công cụ tương thích định dạng, không phải lối tắt để vượt validation.

### 19.3. Nếu opaque token thì sao?

Trong nhánh **opaque token** của Spring Security Resource Server, `OpaqueTokenIntrospector` trả về một `OAuth2AuthenticatedPrincipal` dựa trên kết quả introspection. `MappedJwtClaimSetConverter` là công cụ của **JWT decoder**, không tự được áp dụng vào mọi dữ liệu opaque token.

Khi dữ liệu introspection cần chuẩn hóa, cần thiết kế converter/introspector wrapper phù hợp với hợp đồng AS và chính sách xác thực của nhánh opaque, thay vì mặc định tái sử dụng `NimbusJwtDecoder`.

## 20. Cách quyết định công cụ theo một yêu cầu thực tế

Khi nhận yêu cầu “JWT có claim khác với thứ ứng dụng mong muốn”, hãy xác định:

1. **Có cần đổi kiểu hoặc tạo alias dữ liệu không?** Dùng `MappedJwtClaimSetConverter.withDefaults(...)` hoặc converter toàn claim map có gọi defaults.
2. **Có cần từ chối token thiếu/sai claim không?** Dùng `OAuth2TokenValidator<Jwt>` hoặc `JwtClaimValidator<T>`.
3. **Có cần thay tên trong `Authentication.getName()` không?** Dùng `JwtAuthenticationConverter.setPrincipalClaimName(...)` khi appropriate, đồng thời bảo vệ identity ổn định.
4. **Có cần biến claim thành quyền không?** Dùng `JwtGrantedAuthoritiesConverter` hoặc authority converter tùy biến được kiểm soát.
5. **Có cần quyết định endpoint/user được xem bản ghi nào không?** Dùng `authorizeHttpRequests`, method security và chính sách dữ liệu.
6. **Có cần sửa JWT sai issuer, audience, expiry, chữ ký không?** **Không dùng claim-set converter**; sửa hợp đồng cấp token/cấu hình xác thực hoặc từ chối token.
7. **Có nhiều issuers/tenants không?** Gắn converter và validators với issuer tin cậy, tránh nhập nhằng identity/authority.
8. **Có chạy trên Servlet hay WebFlux?** Ví dụ bài này dành cho Servlet JWT Resource Server dùng `NimbusJwtDecoder`; Reactive stack có cơ chế decoder/cấu hình tương ứng, không bê nguyên filter chain Servlet.

## 21. Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `NimbusJwtDecoder`, claim-set conversion, xác thực JWT và ánh xạ authorities.
- [Spring Security API — MappedJwtClaimSetConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/MappedJwtClaimSetConverter.html): chuyển đổi tập JWT claims và `withDefaults(...)`.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): decoder và `setClaimSetConverter(...)`.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): tên principal và converter authorities.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): chuyển claims quyền thành `GrantedAuthority`.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): những registered claims như `iss`, `sub`, `aud`, `exp`, `iat`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): quy ước claims của JWT access token và mục đích sử dụng tại Resource Server.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): tránh nhầm loại token và xử lý JWT không an toàn.

**Tóm lại:** `MappedJwtClaimSetConverter` giúp **chuyển kiểu và điều chỉnh biểu diễn claims** trong quá trình decode JWT, đặc biệt cho các claim tùy biến của issuer. Dùng `withDefaults(...)` để giữ chuyển đổi chuẩn; không tự sửa issuer, audience, expiry, subject hoặc quyền để “hợp thức hóa” một token sai. `JwtValidators` kiểm tra token, `JwtAuthenticationConverter` xây dựng danh tính/quyền, và authorization quyết định truy cập tài nguyên.
