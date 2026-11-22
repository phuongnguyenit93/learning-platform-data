# 10.10. Xử lý các trường mở rộng trong token response

## 1. Bối cảnh: token endpoint trả về nhiều hơn các trường OAuth 2.0 chuẩn

Trong ứng dụng **Spring Security OAuth 2.0 OIDC Client**, sau khi browser hoàn tất bước xác thực/ủy quyền tại nhà cung cấp danh tính, backend sử dụng authorization code để gọi **Token Endpoint**. Một phản hồi thành công không chỉ có Access Token mà còn có thể có Refresh Token, ID Token (khi dùng OpenID Connect) và các thuộc tính riêng của nhà cung cấp.

Ví dụ, một Authorization Server trả về:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "scope": "openid profile email api.read",
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token_expires_in": 86400,
  "ext_expires_in": 600,
  "session_state": "server-side-session-reference",
  "tenant_id": "company-a",
  "account_region": "ap-southeast-1"
}
~~~

Đây là payload **minh họa**, không phải token hợp lệ để dùng trong ứng dụng thật. Một provider thực tế có thể trả ít trường hơn hoặc đặt tên khác.

Tình huống triển khai thường gặp:

1. Spring Security cần đọc những trường **chuẩn** để xây dựng `OAuth2AccessTokenResponse`.
2. OIDC login cần giữ `id_token` để kiểm tra danh tính người dùng.
3. Một số hệ thống cần đọc thêm metadata như `tenant_id` hay thời hạn Refresh Token nhằm phục vụ nghiệp vụ hoặc giám sát.
4. Provider cũ có thể sử dụng định dạng không chuẩn (ví dụ `expires_in_ms` thay cho `expires_in`) khiến converter mặc định không hiểu.
5. Ứng dụng phải xử lý trường mở rộng mà **không phá vỡ xác minh token, không làm lộ bí mật và không biến metadata bên ngoài thành quyền truy cập đã tin cậy**.

Bài học này phân tích **mô hình phản hồi token, cơ chế ánh xạ vào Spring Security, vị trí tùy biến token response converter và cách sử dụng các trường mở rộng đúng mục đích trong Servlet client**.

## 2. Token response là gì, ở đâu trong Authorization Code flow?

Authorization Code flow phân biệt hai loại thông điệp: response từ authorization endpoint gửi qua **browser** và response từ token endpoint gửi **trực tiếp về backend**.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant C as Spring Boot Servlet OAuth2 Client
    participant AS as OAuth2/OIDC Provider
    U->>C: GET /oauth2/authorization/company
    C-->>U: 302 authorization endpoint (state, PKCE...)
    U->>AS: Đăng nhập / consent
    AS-->>U: 302 callback với authorization code + state
    U->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>C: Khôi phục authorization request và kiểm tra correlation
    C->>AS: POST token endpoint với code, client auth, PKCE verifier
    AS-->>C: JSON token response: chuẩn + trường mở rộng
    C->>C: Token response converter tạo OAuth2AccessTokenResponse
    C->>C: Xác minh OIDC ID Token nếu scope openid
    C-->>U: Session đăng nhập / success handler
~~~

**Token response không phải OAuth authorization callback.** Trường `error` trong callback có `state` được xử lý ở authorization response; lỗi token endpoint có thể được trả bằng HTTP 400 với JSON `error`/`error_description`. Không dùng cùng cách parse một response thành công và một error response.

Ví dụ token request tối giản, minh họa form body:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=CODE_VALUE&redirect_uri=...&code_verifier=...
~~~

Tùy loại client, request còn phải có **client authentication** như `client_secret_basic` hoặc `private_key_jwt`. Không bỏ xác thực client chỉ vì ví dụ trên chưa thể hiện toàn bộ HTTP headers.

## 3. Trường chuẩn và trường mở rộng cần được phân biệt

### 3.1. Các trường OAuth 2.0 token response thường gặp

| Trường | Vai trò | Cách hiểu khi xử lý |
| --- | --- | --- |
| `access_token` | Giá trị credential cấp quyền gọi tài nguyên | Trường bắt buộc với token response thành công kiểu Bearer |
| `token_type` | Kiểu token, thường là `Bearer` | Không tự giả định mọi token type đều dùng được như Bearer |
| `expires_in` | Thời gian sống của Access Token, đơn vị **giây** | Phải chuyển thành số giây hợp lệ; không nhầm milliseconds |
| `refresh_token` | Token dùng để xin token mới nếu được cấp | Tùy chọn; không phải flow nào cũng trả |
| `scope` | Những scope thực sự được cấp, nếu response có trường này | Thường là chuỗi cách nhau bằng khoảng trắng |

Trong OAuth 2.0, `expires_in` được khuyến nghị nhưng không phải trường luôn bắt buộc trong mọi response. Nếu provider không cung cấp, client cần có chính sách vòng đời token phù hợp; đừng tự suy đoán rằng Access Token có hạn dùng vô hạn.

Ví dụ giá trị scope:

~~~json
{
  "scope": "openid profile email api.read"
}
~~~

Đây là **một chuỗi** với các scope cách nhau bởi dấu cách, không phải mảng JSON theo cú pháp token response chuẩn.

### 3.2. Trường bổ sung bởi OpenID Connect: `id_token`

Với **OIDC Authorization Code flow**, token response có thêm **`id_token`**:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile",
  "id_token": "HEADER.PAYLOAD.SIGNATURE"
}
~~~

`id_token` là một thành phần **được chuẩn hóa bởi OIDC**, không phải custom field tùy ý của provider. Trong API tổng quát `OAuth2AccessTokenResponse` của Spring Security, nó có thể xuất hiện trong `additionalParameters` vì không phải một thuộc tính chính của OAuth 2.0 Access Token response model.

**Không loại bỏ `id_token` khi tùy biến converter.** Spring Security cần nó cho quá trình xác thực OIDC; thiếu ID Token trong response OIDC hợp lệ hoặc bỏ mất trường này khi chuyển đổi sẽ khiến đăng nhập thất bại.

ID Token cũng **không tự trở nên đáng tin** chỉ vì đã có trong `additionalParameters`. OIDC client phải xác minh chữ ký, issuer, audience, thời gian và những ràng buộc giao dịch như nonce khi áp dụng.

### 3.3. Các trường mở rộng do provider phát hành

Những tên sau là **ví dụ** thường gặp trong các hệ thống cụ thể; không được coi là một bộ trường OAuth 2.0/OIDC bắt buộc:

| Trường minh họa | Ý nghĩa có thể có | Lưu ý |
| --- | --- | --- |
| `refresh_token_expires_in` | Hạn dùng Refresh Token theo giây | Cách tính và ý nghĩa do provider định nghĩa |
| `ext_expires_in` | Thời gian sống mở rộng theo chính sách riêng | Không đồng nghĩa thời hạn hợp lệ chuẩn của Access Token |
| `session_state` | Metadata liên quan phiên của IdP | Không thay thế HTTP session của ứng dụng |
| `tenant_id` | Mã tenant của provider | Chỉ dùng sau khi đối chiếu với issuer/định danh tin cậy |
| `account_region` | Khu vực xử lý dữ liệu/tài khoản | Metadata nghiệp vụ, không phải quyền API |
| `not-before-policy` | Chính sách mốc thời gian riêng | Cần hợp đồng cụ thể với provider |
| `issued_token_type` | Loại token được cấp trong một số grant mở rộng, ví dụ token exchange | Chỉ diễn giải theo đặc tả grant tương ứng |
| `custom_claims` | Metadata mở rộng dưới dạng object | Không mặc nhiên tin để cấp role |

**Cùng một tên trường có thể có ngữ nghĩa khác nhau giữa các provider.** Chỉ sử dụng khi tài liệu provider quy định rõ kiểu dữ liệu, đơn vị, phạm vi áp dụng, vòng đời và trách nhiệm bảo mật.

### 3.4. Trường nào ảnh hưởng đến việc xác thực?

| Dữ liệu | Có dùng làm bằng chứng login OIDC không? | Có dùng để gọi API không? |
| --- | --- | --- |
| `id_token` | Có, **sau khi xác minh theo OIDC** | Không dùng thay Access Token |
| `access_token` | Không tự nó chứng minh login OIDC | Có, với resource server được cấp token |
| `refresh_token` | Không | Không gửi đến API; chỉ dùng với token endpoint đúng quy trình |
| `session_state` | Không | Không |
| `tenant_id` | Không tự nó đủ làm định danh/tin cậy | Không tự tạo scope/role |
| `refresh_token_expires_in` | Không | Không; dùng cho chính sách quản lý vòng đời nếu đúng hợp đồng |

Một nguyên tắc quan trọng: **metadata trả cùng Access Token không đồng nghĩa nó đã được ký, xác minh hay có cùng mức tin cậy với ID Token.** Việc token endpoint sử dụng TLS giúp bảo vệ kênh truyền, nhưng ứng dụng vẫn phải xác định dữ liệu nào được phép điều khiển quyết định nghiệp vụ.

## 4. Spring Security biểu diễn token response như thế nào?

Trong Spring Security OAuth2 Client, kiểu dữ liệu trung tâm sau khi chuyển đổi thành công là:

~~~java
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;
~~~

Những phương thức thường được sử dụng:

~~~java
OAuth2AccessTokenResponse response = /* kết quả token client */;

String tokenValue = response.getAccessToken().getTokenValue();
Set<String> grantedScopes = response.getAccessToken().getScopes();
Instant expiresAt = response.getAccessToken().getExpiresAt();

OAuth2RefreshToken refreshToken = response.getRefreshToken();
Map<String, Object> extras = response.getAdditionalParameters();
~~~

Ví dụ trên diễn giải cách đọc giá trị; cần import `java.time.Instant`, `java.util.Map`, `java.util.Set` và `OAuth2RefreshToken` trong code thật.

### 4.1. `additionalParameters` là gì?

`OAuth2AccessTokenResponse.getAdditionalParameters()` chứa một map tên-trường-đến-giá-trị mà converter giữ lại ngoài các thuộc tính lõi của response:

~~~java
Map<String, Object> extras = response.getAdditionalParameters();

Object idToken = extras.get("id_token");
Object refreshExpires = extras.get("refresh_token_expires_in");
Object sessionState = extras.get("session_state");
Object tenantId = extras.get("tenant_id");
~~~

Với converter đúng, map có thể chứa:

~~~text
additionalParameters
  id_token: "HEADER.PAYLOAD.SIGNATURE"
  refresh_token_expires_in: 86400
  ext_expires_in: 600
  session_state: "..."
  tenant_id: "company-a"
  account_region: "ap-southeast-1"
~~~

**Không nên giả định một field bất kỳ luôn có**, hoặc luôn là `String`. JSON number có thể được parser giữ dưới dạng số; object/array có thể là `Map`/`List`. Cần kiểm tra kiểu trước khi chuyển đổi.

### 4.2. `additionalParameters` có phải nơi Spring lưu token mãi mãi?

Không. Cần phân biệt ba vòng đời:

~~~text
HTTP token response từ Authorization Server
            |
            v
OAuth2AccessTokenResponse
  accessToken, refreshToken, additionalParameters
            |
            v
OAuth2/OIDC Authentication flow
  ID Token được dùng khi OIDC login
            |
            v
OAuth2AuthorizedClient
  clientRegistration, principalName, accessToken, refreshToken
~~~

`OAuth2AuthorizedClient` dùng để truy xuất Access Token/Refresh Token cho một registration và principal. API này **không cung cấp lại toàn bộ `additionalParameters`** từ token response như một map mặc định.

Nếu ứng dụng cần sử dụng `tenant_id` hoặc `refresh_token_expires_in` sau khi login đã hoàn tất, phải thiết kế một kênh lưu trữ riêng, an toàn và có phạm vi rõ ràng (ví dụ session metadata hoặc kho thông tin tích hợp), chứ không giả định `OAuth2AuthorizedClientRepository` sẽ lưu mọi field mở rộng.

### 4.3. Field mở rộng khác claim của JWT

Đừng đánh đồng:

~~~text
Token response JSON:
{
  "access_token": "eyJ...",
  "tenant_id": "company-a"
}

Payload bên trong Access Token nếu nó là JWT:
{
  "iss": "...",
  "aud": "...",
  "scope": "api.read",
  "tenant": "company-a"
}
~~~

`tenant_id` là metadata trong **response body**; `tenant` là claim bên trong một token (nếu định dạng token thực sự là JWT). Hai giá trị không tự có cùng độ tin cậy, không cần giống nhau và không thay thế việc resource server xác minh Access Token.

Đặc biệt, Access Token **có thể là opaque string**. Client không cần tự parse token để xử lý trường mở rộng trong response.

## 5. Luồng chuyển đổi HTTP response trong Spring Security Servlet

Khi `oauth2Login()` thực hiện Authorization Code flow:

~~~mermaid
flowchart TD
    A["Token Endpoint HTTP response"] --> B["HTTP message converter đọc JSON -> Map"]
    B --> C{"Trường chuẩn đúng format?"}
    C -->|Có| D["OAuth2AccessTokenResponse"]
    C -->|Cần thích nghi provider| E["Custom map-to-token-response converter"]
    E --> D
    C -->|Không hợp lệ| F["Lỗi token response / authentication failure"]
    D --> G["Access Token và Refresh Token"]
    D --> H["AdditionalParameters"]
    H --> I["ID Token được OIDC login xử lý"]
    H --> J["Metadata provider do ứng dụng đọc nếu cần"]
    G --> K["OAuth2AuthorizedClient"]
    I --> L["OIDC principal sau xác minh"]
~~~

Trong Spring Security 6.x, những điểm mở rộng thường được nhắc đến gồm:

| Thành phần | Trách nhiệm |
| --- | --- |
| `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` | Gửi token request và nhận phản hồi sau Authorization Code grant |
| `OAuth2AccessTokenResponseHttpMessageConverter` | Chuyển HTTP token response thành `OAuth2AccessTokenResponse` |
| `Converter<Map<String, Object>, OAuth2AccessTokenResponse>` | Điều chỉnh ánh xạ map dữ liệu token response sang object |
| `DefaultAuthorizationCodeTokenResponseClient` | Token response client dựa trên RestTemplate trong các nhánh Spring Security 6.x |
| `RestClientAuthorizationCodeTokenResponseClient` | Token response client sử dụng RestClient ở các phiên bản Spring Security mới có hỗ trợ |
| `HttpSecurity.oauth2Login().tokenEndpoint()` | Điểm cấu hình token response client của Servlet OAuth2 Login |

**Chọn đúng API cho phiên bản Spring Security của dự án.** Tên class/method và mức độ deprecated có thể khác nhau giữa Spring Security 6.x, 7.x và các bản vá. Không copy đồng thời hai cơ chế RestTemplate và RestClient vào cùng một ứng dụng chỉ vì đều xuất hiện trong tài liệu.

Phần ví dụ bên dưới minh họa **cách ánh xạ map vào response và tích hợp kiểu Spring Security 6.x dùng RestTemplate**. Với phiên bản mới hơn, giữ nguyên nguyên tắc xử lý trường mở rộng nhưng dùng token response client do phiên bản đó khuyến nghị.

## 6. Mặc định đã giữ trường mở rộng thì có cần custom converter không?

**Không phải lúc nào cũng cần.** Nếu provider trả JSON đúng chuẩn OAuth 2.0 cho những trường cốt lõi, converter mặc định của Spring Security có thể chuyển thành `OAuth2AccessTokenResponse` và duy trì các trường bổ sung qua `additionalParameters`.

Ví dụ:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "api.read",
  "tenant_id": "company-a",
  "refresh_token_expires_in": 86400
}
~~~

Với payload chuẩn như vậy, thường chỉ cần dùng converter mặc định, không phải tự viết code để nhận `tenant_id`. Chỉ tùy biến khi có lý do rõ ràng, như:

- Provider trả thời hạn bằng `expires_in_ms` và không có `expires_in`.
- Provider trả scope ở dạng array riêng, cần chuẩn hóa thành chuỗi OAuth 2.0.
- Provider dùng field khác tên chuẩn nhưng có hợp đồng tích hợp rõ ràng.
- Cần kiểm tra chính sách dữ liệu riêng hoặc chặn một dạng token response không được ứng dụng hỗ trợ.

**Không tạo converter riêng chỉ để in toàn bộ token response vào log.** Làm vậy có thể vô tình ghi Access Token, Refresh Token, ID Token và các metadata nhạy cảm.

## 7. Tùy biến converter: giữ nguyên phần chuẩn và metadata

Giả sử một provider legacy có hợp đồng đặc biệt:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in_ms": 300000,
  "scope": "api.read",
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token_expires_in": 86400,
  "tenant_id": "company-a"
}
~~~

`expires_in_ms` không phải tên trường chuẩn theo OAuth 2.0, trong khi `expires_in` mới là đơn vị **giây**. Ta sẽ tạo converter chỉ chuyển `expires_in_ms` sang giây khi thiếu `expires_in`, sau đó tạo response và **giữ lại mọi field ngoài danh sách trường chuẩn**.

### 7.1. Một converter minh họa tự chứa

~~~java
package com.example.security.oauth2;

import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

public final class VendorTokenResponseConverter
        implements Converter<Map<String, Object>, OAuth2AccessTokenResponse> {

    @Override
    public OAuth2AccessTokenResponse convert(Map<String, Object> body) {
        if (body == null) {
            throw invalidResponse("Token response body bị thiếu");
        }

        String accessToken = requireText(body, "access_token");
        String tokenType = requireText(body, "token_type");
        if (!"Bearer".equalsIgnoreCase(tokenType)) {
            throw invalidResponse("Chỉ hỗ trợ token_type=Bearer");
        }

        long expiresIn = parseExpirySeconds(body);
        Set<String> scopes = parseScopes(body.get("scope"));

        OAuth2AccessTokenResponse.Builder builder =
            OAuth2AccessTokenResponse.withToken(accessToken)
                .tokenType(OAuth2AccessToken.TokenType.BEARER)
                .expiresIn(expiresIn)
                .scopes(scopes);

        Object refresh = body.get("refresh_token");
        if (refresh instanceof String value && !value.isBlank()) {
            builder.refreshToken(value);
        }

        // Chỉ bỏ các trường đã được ánh xạ vào model lõi.
        // id_token và metadata vendor phải được giữ lại.
        Map<String, Object> extras = new LinkedHashMap<>(body);
        extras.remove("access_token");
        extras.remove("token_type");
        extras.remove("expires_in");
        extras.remove("refresh_token");
        extras.remove("scope");

        return builder.additionalParameters(extras).build();
    }

    private static long parseExpirySeconds(Map<String, Object> body) {
        Object seconds = body.get("expires_in");
        if (seconds != null) {
            return positiveLong(seconds, "expires_in");
        }

        Object millis = body.get("expires_in_ms");
        if (millis != null) {
            long value = positiveLong(millis, "expires_in_ms");
            long secondsValue = value / 1000L;
            if (secondsValue < 1) {
                throw invalidResponse("expires_in_ms phải >= 1000");
            }
            return secondsValue;
        }

        // Ví dụ chọn chính sách nghiêm ngặt vì provider này đã cam kết TTL.
        throw invalidResponse("Thiếu thời hạn token theo hợp đồng provider");
    }

    private static long positiveLong(Object raw, String field) {
        try {
            long result = Long.parseLong(raw.toString());
            if (result <= 0) {
                throw new NumberFormatException("non-positive");
            }
            return result;
        } catch (NumberFormatException ex) {
            throw invalidResponse("Giá trị không hợp lệ của " + field);
        }
    }

    private static Set<String> parseScopes(Object raw) {
        if (raw == null) {
            return Collections.emptySet();
        }
        if (!(raw instanceof String scopeString)) {
            throw invalidResponse("scope phải là chuỗi phân tách bằng khoảng trắng");
        }
        return Arrays.stream(scopeString.trim().split("\\s+"))
            .filter(value -> !value.isEmpty())
            .collect(Collectors.toCollection(LinkedHashSet::new));
    }

    private static String requireText(
            Map<String, Object> body, String field) {
        Object raw = body.get(field);
        if (!(raw instanceof String text) || text.isBlank()) {
            throw invalidResponse("Thiếu trường bắt buộc: " + field);
        }
        return text;
    }

    private static OAuth2AuthenticationException invalidResponse(
            String reason) {
        return new OAuth2AuthenticationException(
            new OAuth2Error("invalid_token_response", reason, null));
    }
}
~~~

Đoạn này dùng cú pháp Java 17 (pattern matching cho `instanceof`), phù hợp với nhiều dự án Spring Boot 3.x. Đây là **converter dành cho một hợp đồng provider cụ thể**, không phải converter chuẩn thay thế toàn bộ Spring Security trong mọi trường hợp.

Những quyết định có chủ đích:

1. **`access_token` và `token_type` bắt buộc:** vì ứng dụng ví dụ chỉ hỗ trợ Bearer Access Token.
2. **`expires_in` được ưu tiên:** nếu provider trả đúng tên chuẩn, giữ đúng đơn vị giây.
3. **`expires_in_ms` chỉ là fallback đã thỏa thuận:** chuyển millisecond thành giây; không nhầm `300000 ms` thành `300000 s`.
4. **`scope` được chấp nhận theo format OAuth 2.0:** chuỗi cách nhau bằng khoảng trắng.
5. **`refresh_token` là tùy chọn:** nếu không có thì không tạo Refresh Token.
6. **`extras` giữ lại `id_token` và vendor metadata:** tránh đánh mất dữ liệu OIDC cần thiết.
7. **Exception không chứa giá trị token:** lỗi chỉ nói tên field/loại lỗi; không đưa credential vào message.

Nếu provider trả `expires_in` vắng mặt một cách hợp lệ theo OAuth 2.0, converter nghiêm ngặt này **không áp dụng nguyên xi**. Khi đó cần thiết kế chính sách thời hạn dựa trên hợp đồng provider; không tự đặt TTL bất kỳ rồi coi đó là thời hạn bảo đảm.

### 7.2. Vì sao không dùng một `Map<String, String>` cho mọi trường?

JSON response có thể chứa số và object:

~~~json
{
  "expires_in": 300,
  "refresh_token_expires_in": 86400,
  "tenant": {
    "id": "company-a",
    "region": "ap-southeast-1"
  },
  "features": ["reports", "directory"]
}
~~~

`Map<String, Object>` giữ được các kiểu này, trong khi ép mọi giá trị sang `String` có thể làm mất cấu trúc hoặc gây `ClassCastException`. Với trường mở rộng, kiểm tra kiểu dữ liệu theo hợp đồng:

~~~java
Object raw = response.getAdditionalParameters().get("tenant_id");
if (raw instanceof String tenantId && !tenantId.isBlank()) {
    // Chỉ dùng sau khi đối chiếu tenant với cấu hình tin cậy của ứng dụng.
}
~~~

Đối với số lớn, đừng ép sang `Integer` nếu dữ liệu có thể vượt phạm vi 32-bit. Đối với một thời hạn tính bằng giây, nên parse rõ kiểu số và giới hạn hợp lý theo yêu cầu hệ thống.

## 8. Gắn converter vào token endpoint của Servlet OAuth2 Login

Trong Spring Security **6.x sử dụng `DefaultAuthorizationCodeTokenResponseClient`**, có thể thay message converter của RestTemplate được dùng để gọi token endpoint:

~~~java
package com.example.security.oauth2;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.FormHttpMessageConverter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.DefaultAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.http.OAuth2ErrorResponseErrorHandler;
import org.springframework.security.oauth2.core.http.converter.OAuth2AccessTokenResponseHttpMessageConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.client.RestTemplate;

@Configuration
public class TokenEndpointConfig {

    @Bean
    OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            customAuthorizationCodeTokenClient() {

        OAuth2AccessTokenResponseHttpMessageConverter converter =
            new OAuth2AccessTokenResponseHttpMessageConverter();
        converter.setAccessTokenResponseConverter(
            new VendorTokenResponseConverter());

        RestTemplate restTemplate = new RestTemplate(
            List.of(new FormHttpMessageConverter(), converter));

        // Giữ xử lý error response của OAuth 2.0 Token Endpoint.
        restTemplate.setErrorHandler(new OAuth2ErrorResponseErrorHandler());

        DefaultAuthorizationCodeTokenResponseClient client =
            new DefaultAuthorizationCodeTokenResponseClient();
        client.setRestOperations(restTemplate);
        return client;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
                customAuthorizationCodeTokenClient) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(
                        customAuthorizationCodeTokenClient)))
            .build();
    }
}
~~~

**Ranh giới phiên bản:** mẫu trên minh họa API token client kiểu RestTemplate của Spring Security 6.x. Ở các phiên bản mới có `RestClientAuthorizationCodeTokenResponseClient`, hãy dùng API cấu hình response converter của token client tương ứng thay vì tạo RestTemplate chỉ để làm theo ví dụ cũ. Một số class cũ được deprecated hoặc thay thế theo nhánh phiên bản; không áp dụng code mà không kiểm tra tài liệu của Spring Security đang dùng.

**Không cần thêm custom token client cho mọi registration.** Cấu hình vào `oauth2Login().tokenEndpoint()` ở trên có thể ảnh hưởng các login dùng cùng `SecurityFilterChain`. Nếu ứng dụng có nhiều provider và chỉ một provider trả dữ liệu legacy, nên dùng converter có nhánh chính xác theo hợp đồng từng provider hoặc kiến trúc token client riêng, không áp đặt phép chuyển đổi `expires_in_ms` cho provider chuẩn.

### 8.1. Vì sao phải giữ `OAuth2ErrorResponseErrorHandler`?

Token endpoint có thể trả HTTP 400:

~~~json
{
  "error": "invalid_grant",
  "error_description": "Authorization code is invalid or expired"
}
~~~

Đây là **OAuth2 error response**, không phải token response thành công. Nếu tùy biến RestTemplate mà bỏ error handler phù hợp, ứng dụng có thể nhận exception khó phân loại hoặc cố chuyển JSON lỗi thành object token. Điều này gây thông báo sai và khó chẩn đoán.

Không trả nguyên `error_description` từ provider ra browser hoặc ghi toàn bộ response body vào log, vì nội dung bên ngoài có thể chứa dữ liệu nhạy cảm.

### 8.2. Đặt đúng điểm mở rộng trong Spring Security

~~~text
oauth2Login()
  .tokenEndpoint(...)
    .accessTokenResponseClient(...)
      -> POST Authorization Code đến Token Endpoint
      -> Xử lý response thành công và lỗi
      -> OAuth2AccessTokenResponse (extras còn nguyên)
    -> OIDC validation và Authentication
~~~

Đừng chỉnh `OAuth2UserService` chỉ để chuyển `expires_in_ms`: user service thường nhận nhiệm vụ tải và ánh xạ người dùng sau khi token exchange đã hoàn thành. Lỗi parse token response cần xử lý tại **token response client/converter**, đúng vị trí dữ liệu đi vào framework.

Ngược lại, nếu cần ánh xạ claim UserInfo thành tên hiển thị, đó là trách nhiệm user service hoặc mapping ứng dụng, **không phải** token response converter.

## 9. Dữ liệu mở rộng có tồn tại sau Authorization Code login không?

Khi converter đã trả về `OAuth2AccessTokenResponse`:

- Framework sử dụng Access Token và Refresh Token cho `OAuth2AuthorizedClient`.
- Với OIDC, `id_token` được xử lý theo quy trình xác thực OIDC.
- Những trường như `tenant_id` hoặc `refresh_token_expires_in` có thể được đọc tại **điểm xử lý token response**.
- Nhưng `OAuth2AuthorizedClient` không mặc định lưu mọi `additionalParameters` để lấy lại về sau.

Một vấn đề thiết kế: **muốn dùng `refresh_token_expires_in` ở trang quản lý kết nối sau vài giờ thì lưu ở đâu?**

Có thể cân nhắc các lựa chọn:

| Cách tiếp cận | Khi phù hợp | Điều kiện an toàn |
| --- | --- | --- |
| Không lưu; chỉ dùng khi phản hồi đến | Field chỉ giúp quyết định tức thời hoặc quan sát | Không ghi token, chỉ dùng các metadata thật sự cần |
| Lưu metadata đã chuẩn hóa trong server-side session | Chỉ phục vụ phiên web hiện tại | Ràng buộc người dùng và registration, TTL, xóa khi logout |
| Lưu vào bảng tích hợp backend | Cần theo dõi vòng đời kết nối lâu hơn phiên | Mã hóa/kiểm soát truy cập, key theo user/provider, xóa khi disconnect |
| Không dùng field của vendor; dựa vào API chuẩn | Provider không cam kết field ổn định | Tối giản phụ thuộc |

Nếu cần **chuyển metadata từ token response sang một dịch vụ nghiệp vụ**, phải thiết kế điểm mở rộng phù hợp để quan sát và xử lý response tại thời điểm token client nhận được. Không cố lấy map đã mất bằng cách parse lại raw token từ authorized client.

**Không ghi thẳng toàn bộ `additionalParameters` vào database**. Map này có thể chứa `id_token` và những thuộc tính nhạy cảm khác; chỉ trích xuất, kiểm tra và lưu dữ liệu tối thiểu theo chính sách đã định nghĩa.

## 10. Token response khi refresh token: không giống lần đầu

Một lỗi phổ biến là chỉ xem trường mở rộng ở lần **Authorization Code token response**, rồi giả định chúng tồn tại trên mọi lần refresh.

Khi Access Token hết hạn, OAuth2 Client có thể gửi:

~~~http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=REFRESH_TOKEN_VALUE
~~~

Yêu cầu thực tế còn cần client authentication và các tham số provider yêu cầu. Phản hồi có thể như:

~~~json
{
  "access_token": "NEW_ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "api.read",
  "refresh_token": "NEW_REFRESH_TOKEN_VALUE",
  "refresh_token_expires_in": 72000
}
~~~

Các điểm cần hiểu:

1. Authorization Server **có thể** xoay vòng Refresh Token; nếu trả token mới thì client phải sử dụng theo cơ chế quản lý của framework.
2. Có provider **không trả lại Refresh Token** ở một số lần refresh; không được hiểu giá trị vắng mặt là chủ động thu hồi token đang có nếu thư viện/token manager có quy tắc giữ token trước đó.
3. **Không mặc định có `id_token` trong refresh response**. Quy tắc riêng của OIDC cho các response có ID Token vẫn phải được kiểm tra khi có.
4. Trường mở rộng như `refresh_token_expires_in` có thể được cập nhật, thiếu đi hoặc thay ngữ nghĩa giữa các grant.
5. **Tùy biến Authorization Code token client không tự áp dụng cho Refresh Token grant.** Với Spring Security cần cấu hình refresh token response client/authorized client provider tương ứng nếu phải xử lý field mở rộng ở flow refresh.

### 10.1. Khi nào cần custom refresh handling?

Giả sử provider chỉ phát `expires_in_ms` trên cả token response ban đầu và response refresh. Nếu lần đầu converter xử lý đúng nhưng refresh vẫn dùng converter mặc định không hiểu field này, ứng dụng có thể xử lý vòng đời token sai hoặc refresh thất bại.

Vì vậy, khi tùy biến định dạng response, hãy xác định **những grant thực sự được ứng dụng sử dụng**:

| Grant / flow | Token response cần xử lý? | Điểm cấu hình |
| --- | --- | --- |
| Authorization Code / OIDC Login | Có | `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)` |
| Refresh Token | Có, nếu client tự refresh | Token response client của refresh provider/authorized client manager |
| Client Credentials | Có, với backend service client | Authorized client provider cho Client Credentials |
| Token Exchange | Có, nếu tích hợp grant mở rộng | Token client/provider phù hợp grant và đặc tả token exchange |

Không tự tin rằng một converter cài cho authorization code sẽ xử lý mọi token request của ứng dụng. Phải nắm rõ kiến trúc refresh/cấp token mới đang dùng.

## 11. Những sai lầm liên quan đến hạn dùng và scope

### 11.1. `expires_in` tính bằng giây, không phải milliseconds

Ví dụ:

~~~text
expires_in = 300       -> 300 giây = 5 phút
expires_in_ms = 300000 -> 300000 mili giây = 5 phút (theo contract vendor)
~~~

Nếu đọc nhầm `expires_in_ms=300000` thành số **giây**, ứng dụng tưởng token còn hiệu lực lâu hơn thực tế khoảng 1000 lần. Khi gọi API, token đã hết hạn vẫn được dùng dẫn tới 401 liên tục.

Ngược lại, nếu đọc `expires_in=300` như milliseconds, token bị coi hết hạn gần như tức thời, khiến ứng dụng refresh quá mức. Đơn vị phải được chuẩn hóa **trước khi tạo `OAuth2AccessTokenResponse`**.

### 11.2. Refresh Token không chia sẻ mặc định hạn dùng với Access Token

`expires_in` nói về Access Token. `refresh_token_expires_in` (nếu có) có thể nói về Refresh Token, nhưng cần đọc chính sách provider để biết bắt đầu tính từ thời điểm nào, có sliding expiration không và liệu chính sách thu hồi có thể rút ngắn thời hạn.

Không lấy `refresh_token_expires_in` gán cho `OAuth2AccessTokenResponse.Builder.expiresIn(...)`. Làm vậy khiến Access Token lifecycle sai.

### 11.3. Không tự cấp thêm scope từ metadata

Ví dụ token response:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read",
  "tenant_id": "company-a",
  "role_hint": "admin"
}
~~~

Không tự suy luận `role_hint=admin` trong response là quyền quản trị đã được ứng dụng phê duyệt. Resource Server cần xác minh token, audience, scope và chính sách quyền trên API; quyền nội bộ có thể cần mapping/đồng bộ riêng.

Nếu `scope` trong token response vắng mặt, OAuth 2.0 có quy tắc liên quan việc scope được cấp so với scope được yêu cầu. Không suy diễn “scope không có thì được tất cả”; hãy tuân thủ quy tắc giao thức và cách Spring Security/provider thể hiện scope.

### 11.4. Trường `issued_token_type` trong token exchange

Trong OAuth 2.0 Token Exchange (RFC 8693), `issued_token_type` là một trường có ý nghĩa theo extension grant, ví dụ loại token nhận được. Không đánh đồng nó với `token_type`:

| Field | Câu hỏi trả lời |
| --- | --- |
| `token_type` | Client truyền token tới resource server theo cách nào? Ví dụ `Bearer` |
| `issued_token_type` | Loại token nào được phát hành theo protocol token exchange? Ví dụ URI định danh loại token |

Chỉ hỗ trợ token exchange nếu authorization server và Spring Security client được cấu hình đúng; đừng nhìn thấy `issued_token_type` rồi tự thay đổi loại `OAuth2AccessToken` hoặc bỏ qua kiểm tra audience/token purpose.

## 12. Bảo mật khi xử lý trường mở rộng

### 12.1. Giữ đúng ranh giới tin cậy

Các trường response đến từ token endpoint **được cấu hình tin cậy**, nhưng bản thân chúng không thay thế các bước bảo mật của client. Một chuỗi `tenant_id` hoặc `roles` trong JSON response không có ngữ nghĩa OAuth 2.0 chuẩn buộc resource server phải chấp nhận.

Các nguyên tắc:

- Token endpoint phải là URL được cấu hình/khám phá từ **issuer tin cậy**, không chọn theo input chưa được kiểm soát.
- Sử dụng HTTPS và kiểm tra TLS certificate. Không tắt xác minh server identity khi gặp lỗi kết nối.
- Với OIDC, giữ `id_token` nguyên vẹn và để **OIDC validation** xác minh chữ ký, issuer, audience, expiration và các ràng buộc.
- Access Token được gửi **chỉ cho resource server phù hợp**; không tái sử dụng ID Token làm Access Token.
- Nếu metadata mở rộng ảnh hưởng quyền, cần kiểm tra issuer, tenant mapping và chính sách nội bộ. Không cấp quyền chỉ vì provider gửi một chuỗi trông như `admin`.
- Khi field thay đổi kiểu hoặc thiếu, dùng fallback an toàn hoặc báo lỗi theo hợp đồng, không tạo mặc định quá rộng quyền.

### 12.2. Không log toàn bộ token response

Không nên:

~~~java
// Không sử dụng trong sản phẩm thật:
logger.info("token response: {}", response);
logger.info("extra params: {}", response.getAdditionalParameters());
~~~

Vì `additionalParameters` có thể chứa **ID Token** hoặc dữ liệu cá nhân/nhạy cảm. Toàn bộ `OAuth2AccessTokenResponse` cũng chứa Access Token và có thể có Refresh Token.

Thay vào đó, chỉ ghi metadata an toàn:

~~~text
event=oauth_token_response_received
registration=company
grant=authorization_code
has_id_token=true
has_refresh_token=true
extension_fields_count=3
correlation_id=internal-safe-reference
~~~

Đây là định dạng log đề xuất, không phải output mặc định của framework. `correlation_id` nên độc lập với authorization code, Access Token, Refresh Token, PKCE verifier và session cookie.

### 12.3. Không chuyển các giá trị tùy ý thành redirect URL

Nếu provider trả field mở rộng `next_url`, `redirect` hoặc `login_hint`, không lập tức dùng làm URL redirect browser. Metadata mở rộng có thể bị khai thác nếu ứng dụng biến nó thành điều hướng ngoài phạm vi cho phép. Dùng danh sách URL/route đã được ứng dụng kiểm soát; việc login success/failure nên được điều khiển bằng Spring Security handlers phù hợp.

### 12.4. Giới hạn kích thước và kiểu dữ liệu

Một token response có thể chứa extension JSON dài, object lồng nhau hoặc danh sách lớn. Khi cần lưu một phần metadata, hãy đặt giới hạn kích thước, độ sâu và TTL, chỉ chấp nhận field đã biết. Đừng sao chép nguyên map mở rộng vào session, cookie, log hoặc database chỉ vì converter có khả năng giữ nguyên dữ liệu đó.

## 13. Lỗi thường gặp và cách phân tích

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Token endpoint trả thành công nhưng Spring không parse được response | `token_type`, `access_token` hoặc kiểu `expires_in` sai chuẩn | So sánh payload **đã được che token** với RFC/hợp đồng provider; chỉ chuẩn hóa phần ngoại lệ cần thiết |
| OIDC login báo thiếu ID Token | Custom converter đã bỏ `id_token` khỏi additional parameters | Giữ `id_token` khi tạo `OAuth2AccessTokenResponse` |
| OIDC ID Token sai issuer/chữ ký/audience | Token không hợp lệ hoặc sai provider/registration | Không tắt validation; sửa issuer, JWKS, audience và provider configuration |
| Token hết hạn nhưng app tưởng còn hạn | `expires_in_ms` bị đọc thành giây | Chuẩn hóa units trước khi build response |
| Access Token bị refresh liên tục | `expires_in` bị coi là milliseconds hoặc trả giá trị gần 0 | Kiểm tra contract và phép chuyển đổi TTL |
| Trường `tenant_id` có trong response nhưng không đọc được sau login | `OAuth2AuthorizedClient` không lưu nguyên `additionalParameters` | Thiết kế bước trích xuất/lưu metadata có kiểm soát khi token response đến |
| Lần đầu login ổn nhưng refresh thất bại | Chỉ custom converter Authorization Code, refresh grant vẫn dùng mặc định | Cấu hình đúng refresh token client/provider nếu cần |
| API trả 403 dù `role_hint=admin` | Field vendor không tương đương scope/role được API kiểm tra | Cấu hình đúng token audience/scope và policy của API |
| Provider trả `scope` dưới dạng array | Format không theo chuẩn OAuth2 token response thường dùng | Yêu cầu provider sửa hoặc converter riêng xử lý có hợp đồng |
| Trường số bị `ClassCastException` | Ép `Long` thành `Integer` hoặc JSON number thành `String` | Kiểm tra `Number`/`String`; parse rõ đơn vị và khoảng giá trị |
| Exception custom converter chứa raw token | Throw/log map response nguyên văn | Thay bằng mã lỗi và tên field không nhạy cảm |
| Cài converter nhưng không thấy hoạt động | Sai security chain hoặc cấu hình nhầm token client | Kiểm tra `oauth2Login().tokenEndpoint()` của Servlet chain đang xử lý callback |
| Provider trả `invalid_grant` từ token endpoint | Authorization code sai/hết hạn, PKCE hoặc redirect URI không khớp | Xử lý OAuth error response; không cố parse như token thành công |

### 13.1. Phân biệt lỗi mapping với lỗi token thật

Hai lỗi này có bản chất khác nhau:

~~~text
Mapping lỗi:
  Token response có expires_in_ms theo contract
  -> converter hiện tại chỉ hiểu expires_in
  -> cần chuẩn hóa field trước khi tạo response

Token không hợp lệ:
  Token response có id_token
  -> chữ ký, issuer, aud, nonce hoặc exp không hợp lệ
  -> OIDC login phải từ chối; sửa cấu hình/issuer/token
~~~

**Không dùng custom converter để “chữa” một ID Token không hợp lệ**. Converter chỉ xử lý biểu diễn dữ liệu token response; xác minh danh tính OIDC là công việc riêng với quy tắc bảo mật không được bỏ qua.

## 14. Ví dụ sử dụng metadata trong nghiệp vụ một cách an toàn

Giả sử hệ thống nhiều tenant cần biết người dùng thuộc tenant nào để hiển thị đúng giao diện sau login. Provider trả `tenant_id` tại token endpoint.

Một thiết kế hợp lý:

1. **Chuẩn hóa response:** converter giữ `tenant_id` trong `additionalParameters`.
2. **Đọc field tại điểm nhận token:** xác nhận nó là chuỗi có định dạng hợp lệ và không vượt giới hạn.
3. **Đối chiếu identity đã xác minh:** dùng `iss`/`sub` từ ID Token OIDC và mapping tenant đáng tin cậy.
4. **Chỉ lưu metadata tối thiểu:** chẳng hạn tenant ID đã ánh xạ thành tenant nội bộ sau kiểm tra, không lưu lại Access Token/ID Token trong trường metadata.
5. **Phân quyền riêng:** quyền đọc/ghi dữ liệu của tenant vẫn phải kiểm tra bởi ứng dụng hoặc API; `tenant_id` không thay thế authorization policy.

~~~mermaid
flowchart TD
    A["Token response chứa tenant_id và id_token"] --> B["Response converter giữ additionalParameters"]
    B --> C["OIDC client xác minh ID Token"]
    C --> D{"Danh tính iss + sub hợp lệ?"}
    D -->|Không| E["Từ chối login"]
    D -->|Có| F["Đối chiếu tenant_id với mapping tin cậy"]
    F --> G{"Tenant được phép?"}
    G -->|Không| H["Từ chối liên kết hoặc giới hạn quyền"]
    G -->|Có| I["Lưu tenant metadata tối thiểu"]
    I --> J["API kiểm tra policy trên từng tài nguyên"]
~~~

Với provider OAuth2 thuần không cấp ID Token, cần dùng định danh tài khoản từ API hồ sơ đáng tin theo hợp đồng provider và chính sách account linking tương ứng; không giả định `tenant_id` trong response tự xác thực người dùng.

## 15. Các tình huống luyện tập

### Tình huống A: Trường mở rộng không ảnh hưởng parse chuẩn

Provider trả `access_token`, `token_type=Bearer`, `expires_in=300` và `tenant_id`.

**Cách làm:** ưu tiên converter mặc định. `tenant_id` có thể được giữ trong `additionalParameters`; chỉ bổ sung logic khi nghiệp vụ thật sự cần sử dụng nó.

### Tình huống B: Trường `expires_in_ms` thay thế `expires_in`

Provider trả `expires_in_ms=300000`.

**Cách làm:** chỉ nếu đây là hợp đồng được xác nhận, chuyển thành `300` giây bằng converter; xử lý giá trị âm, zero, tràn số hoặc kiểu dữ liệu không hợp lệ. Không đổi nội dung token hay tự đặt ngày hết hạn vô hạn.

### Tình huống C: OIDC có `id_token` nhưng custom converter làm mất field

Ứng dụng cố xóa mọi trường ngoài năm trường OAuth 2.0 cơ bản, khiến `id_token` biến mất.

**Kết quả:** OIDC login có thể thất bại. Cần bảo toàn `id_token` trong `additionalParameters` để framework xác minh theo OIDC.

### Tình huống D: Refresh response có cấu trúc khác lần đầu

Lần đăng nhập đầu có `expires_in=300`, lần refresh có `expires_in_ms=300000`.

**Cách làm:** xác định riêng token response client dùng cho refresh. Chỉ thay converter ở `oauth2Login().tokenEndpoint()` có thể không xử lý được lần refresh.

### Tình huống E: Metadata báo quyền admin

Provider trả field `role_hint=admin` trong JSON token response, nhưng Access Token không có scope API cần thiết.

**Kết luận:** không tự cấp quyền admin hoặc sửa scope. Cần thiết kế nguồn quyền đáng tin và thực thi policy tại Resource Server/ứng dụng.

### Tình huống F: Token response chứa trường số dạng string

Provider trả `"refresh_token_expires_in": "86400"` thay vì JSON number.

**Cách làm:** chỉ parse trường đó nếu ứng dụng cần và provider cam kết hỗ trợ dạng này; sử dụng logic kiểm tra number/string rõ ràng. Không ép kiểu trực tiếp sang `Long` và không xem nó là `expires_in` của Access Token.

### Tình huống G: Trường mở rộng cần dùng sau vài giờ

Ứng dụng cần `tenant_id` khi người dùng mở lại trang quản lý kết nối, nhưng lúc ấy chỉ còn `OAuth2AuthorizedClient`.

**Cách làm:** thêm cơ chế trích xuất/lưu metadata riêng đã kiểm tra tại thời điểm token response, có TTL và ràng buộc user/provider. Đừng giả định `OAuth2AuthorizedClient` cung cấp mọi `additionalParameters`.

### Tình huống H: Token endpoint trả JSON lỗi

Provider trả HTTP 400 với `error=invalid_grant`, `error_description`.

**Cách làm:** xử lý qua cơ chế OAuth2 error handler; không đưa JSON này vào converter của token response thành công hoặc hiển thị raw error description ra browser.

## 16. Tài liệu tham khảo

- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — OAuth2AccessTokenResponse Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/endpoint/OAuth2AccessTokenResponse.html
- Spring Security — OAuth2AccessTokenResponseHttpMessageConverter Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/http/converter/OAuth2AccessTokenResponseHttpMessageConverter.html
- OAuth 2.0 Authorization Framework, Section 5.1 — Successful Response: https://www.rfc-editor.org/rfc/rfc6749#section-5.1
- OAuth 2.0 Authorization Framework, Section 5.2 — Error Response: https://www.rfc-editor.org/rfc/rfc6749#section-5.2
- OpenID Connect Core 1.0 — Token Response: https://openid.net/specs/openid-connect-core-1_0.html
- OAuth 2.0 Token Exchange (RFC 8693): https://www.rfc-editor.org/rfc/rfc8693

## 17. Kết luận

Một phản hồi từ token endpoint có thể chứa **các trường chuẩn OAuth 2.0**, **`id_token` của OIDC** và **metadata mở rộng do provider định nghĩa**. Trong Spring Security, `OAuth2AccessTokenResponse` là đối tượng trung tâm, còn `additionalParameters` là nơi có thể giữ những field không nằm trong mô hình lõi.

~~~text
Token Endpoint JSON
  |
  +-- Các trường chuẩn
  |     access_token, token_type, expires_in, refresh_token, scope
  |     -> OAuth2AccessTokenResponse: AccessToken / RefreshToken
  |
  +-- ID Token của OIDC
  |     id_token
  |     -> additionalParameters
  |     -> OIDC login validation
  |
  +-- Metadata riêng của provider
        refresh_token_expires_in, session_state, tenant_id, ...
        -> additionalParameters
        -> chỉ trích xuất, kiểm tra và lưu khi thực sự cần
~~~

**Thứ tự ưu tiên khi triển khai:** dùng converter mặc định khi response đã chuẩn; chỉ tùy biến phần cần thiết khi provider có hợp đồng ngoại lệ; luôn giữ `id_token` cho OIDC và thông tin PKCE/token lifecycle đúng cách; không tự biến các field mở rộng thành quyền truy cập đã được chứng thực. Cuối cùng, hãy nhớ rằng **Authorization Code, Refresh Token và các grant khác có thể dùng những token response clients khác nhau**, nên cần xác định đúng điểm mở rộng trước khi áp dụng converter.
