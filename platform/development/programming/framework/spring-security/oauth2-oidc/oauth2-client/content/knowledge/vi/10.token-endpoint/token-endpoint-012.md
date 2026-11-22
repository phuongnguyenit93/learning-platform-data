# 10.12. Chuyển đổi OAuth2Error và xử lý response không đúng chuẩn

## 1. Vị trí của xử lý lỗi trong Token Endpoint

Trong **Spring Security OAuth 2.0/OIDC Client**, sau khi người dùng được chuyển hướng về callback với authorization code hợp lệ, Client gửi yêu cầu đến **Token Endpoint** của Authorization Server để đổi code lấy token. Với một số grant khác, chẳng hạn client credentials hay refresh token, Token Endpoint cũng là nơi xử lý yêu cầu cấp hoặc làm mới token.

Phần lớn ví dụ giới thiệu Token Endpoint đều minh họa trường hợp thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "REFRESH_TOKEN_VALUE",
  "scope": "openid profile",
  "id_token": "ID_TOKEN_VALUE"
}
~~~

Response này chỉ là ví dụ cấu trúc; các chuỗi token là placeholder. Tùy grant, scope, Client và nhà cung cấp, token response có thể không có refresh token hoặc ID Token. Với OIDC Authorization Code Flow, ID Token có các quy tắc xác minh riêng sau khi được cấp.

Trong thực tế, Token Endpoint còn có thể trả lỗi chuẩn OAuth 2.0, lỗi dạng JSON riêng của provider, lỗi HTML do reverse proxy/WAF, HTTP 200 nhưng body lại chứa lỗi, JSON hỏng, hoặc lỗi kết nối trước khi nhận response. Khi đó ứng dụng phải:

1. **Nhận diện được lỗi** ở tầng HTTP hoặc tầng giao thức.
2. **Chuyển lỗi về biểu diễn nhất quán** để các thành phần Spring Security xử lý.
3. **Không nhận nhầm lỗi thành token response hợp lệ.**
4. **Không làm lộ** authorization code, client secret, access token, refresh token hoặc nội dung nhạy cảm của provider trong log hay phản hồi cho trình duyệt.
5. **Giữ nguyên ngữ nghĩa lỗi quan trọng** để vận hành và khắc phục đúng nguyên nhân.

Lớp giá trị cốt lõi của Spring Security phục vụ mục tiêu này là **<code>OAuth2Error</code>**. Bài học tập trung vào cách biểu diễn, chuyển đổi và xử lý an toàn những response không đúng chuẩn tại Token Endpoint trong ứng dụng **OAuth2/OIDC Client**, đặc biệt với Servlet OAuth2 Login.

## 2. Lỗi chuẩn OAuth 2.0 tại Token Endpoint

### 2.1. Cấu trúc lỗi theo RFC 6749

RFC 6749, mục 5.2, định nghĩa response lỗi của Token Endpoint với các trường:

| Trường | Bắt buộc? | Nội dung |
|---|---|---|
| <code>error</code> | Có | Mã lỗi dạng chuỗi, chẳng hạn <code>invalid_grant</code> |
| <code>error_description</code> | Không | Mô tả nhằm hỗ trợ chẩn đoán lỗi |
| <code>error_uri</code> | Không | URI dẫn tới tài liệu giải thích lỗi |

Ví dụ lỗi khi authorization code đã hết hạn:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant",
  "error_description": "Authorization code is expired or invalid"
}
~~~

Các mã lỗi Token Endpoint cơ bản:

| Mã lỗi | Ý nghĩa thường gặp | Hướng điều tra |
|---|---|---|
| <code>invalid_request</code> | Thiếu tham số, tham số lặp, request sai cú pháp hoặc không hợp lệ | Kiểm tra form encoding, <code>grant_type</code>, các tham số bắt buộc |
| <code>invalid_client</code> | Client authentication thất bại hoặc Client không được nhận diện | Kiểm tra client ID, secret, phương thức xác thực, khóa ký nếu dùng private-key JWT |
| <code>invalid_grant</code> | Grant/code/refresh token không hợp lệ, hết hạn, bị thu hồi, đã sử dụng hoặc không khớp ràng buộc | Kiểm tra vòng đời code, redirect URI, PKCE, Client binding, refresh token |
| <code>unauthorized_client</code> | Client không được phép sử dụng grant type đang yêu cầu | Kiểm tra registration và chính sách của Authorization Server |
| <code>unsupported_grant_type</code> | Token Endpoint không hỗ trợ grant type được yêu cầu | Kiểm tra <code>grant_type</code>, cấu hình provider và giao thức |
| <code>invalid_scope</code> | Scope không hợp lệ, không được phép hoặc không phù hợp grant | Kiểm tra scopes và quyền của Client |

**Không suy ra nguyên nhân duy nhất từ một mã lỗi.** Ví dụ <code>invalid_grant</code> có thể xuất hiện do authorization code bị dùng lần hai, PKCE verifier sai hoặc redirect URI không khớp. Nó không có nghĩa session của người dùng đã được xác thực hay chưa; kiểm tra state/callback có thể diễn ra trước Token Endpoint.

Token Endpoint thường trả **HTTP 400** khi request grant không hợp lệ. Trường hợp **<code>invalid_client</code>**, server có thể trả **HTTP 401**; nếu Client đã dùng HTTP <code>Authorization</code> header để xác thực, RFC 6749 yêu cầu response 401 và <code>WWW-Authenticate</code> phù hợp. Vì vậy, không thiết kế logic chỉ xem HTTP 400 mới là lỗi OAuth 2.0.

### 2.2. Lỗi HTTP và lỗi OAuth là hai thông tin khác nhau

**HTTP status** nói về kết quả xử lý yêu cầu ở tầng HTTP. **OAuth error code** nói về điều kiện nghiệp vụ/giao thức mà Authorization Server công bố.

Ví dụ:

~~~text
HTTP status: 400
OAuth error: invalid_grant
Cause nghi ngờ: code hết hạn, PKCE sai, redirect URI khác...
~~~

Hai trường này có liên hệ nhưng **không thay thế nhau**. Một response HTTP 502 từ gateway có thể không hề chứa OAuth error code. Ngược lại, provider triển khai sai có thể trả <code>{"error":"invalid_grant"}</code> với HTTP 200; phần body vẫn cho thấy thất bại và tuyệt đối không thể coi đó là token response thành công.

Trong thiết kế vận hành, nên giữ thông tin HTTP status riêng ở lớp telemetry/exception context khi cần, còn <code>OAuth2Error</code> biểu diễn lỗi giao thức được chuẩn hóa.

## 3. OAuth2Error và ngoại lệ trong Spring Security

### 3.1. Lớp OAuth2Error

Spring Security định nghĩa:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_grant",
    "Authorization code could not be redeemed",
    null
);
~~~

Ba giá trị truyền vào constructor là:

1. <code>errorCode</code>: mã lỗi, ví dụ <code>invalid_grant</code>.
2. <code>description</code>: thông điệp mô tả có thể để <code>null</code>.
3. <code>uri</code>: liên kết tài liệu lỗi có thể để <code>null</code>.

<code>OAuth2Error</code> là **giá trị mô tả lỗi**, không phải HTTP response và không tự chứa HTTP status, request ID, token hay thông tin session. Từ một OAuth2Error, ứng dụng có thể quyết định phân loại lỗi, ghi telemetry an toàn hoặc chuyển thành exception.

### 3.2. OAuth2AuthorizationException

Trong các thao tác OAuth 2.0 như token exchange, lỗi ở bước lấy token thường được biểu diễn bằng <code>OAuth2AuthorizationException</code>:

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_client",
    "Client authentication failed",
    null
);

throw new OAuth2AuthorizationException(error);
~~~

Exception này cho phép tầng gọi lấy lại lỗi thông qua <code>getError()</code>. Có thể truyền thêm exception gốc vào constructor tương ứng nếu cần giữ cause phục vụ chẩn đoán nội bộ, nhưng không được gửi stack trace hoặc thông điệp nhạy cảm cho trình duyệt.

### 3.3. OAuth2AuthenticationException

Khi lỗi được đưa lên quá trình đăng nhập/xác thực trong Spring Security, có thể gặp <code>OAuth2AuthenticationException</code>. Nó là một <code>AuthenticationException</code>, cũng mang một <code>OAuth2Error</code>.

~~~java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

OAuth2Error error = new OAuth2Error(
    "invalid_token_response",
    "Token endpoint response is not usable",
    null
);

throw new OAuth2AuthenticationException(error);
~~~

<code>invalid_token_response</code> trong ví dụ là mã lỗi phục vụ triển khai/kiểm tra token response; **không nằm trong sáu mã lỗi Token Endpoint cơ bản của RFC 6749 mục 5.2**. Khi dùng mã riêng, phải phân biệt rõ với mã chuẩn của provider.

Các lớp cần ghi nhớ:

| Lớp | Đại diện cho | Thường gặp ở |
|---|---|---|
| <code>OAuth2Error</code> | Mã lỗi, mô tả và error URI | Tầng mô hình lỗi |
| <code>OAuth2AuthorizationException</code> | Thao tác OAuth authorization/token bị lỗi | OAuth2 token response client, authorized client manager |
| <code>OAuth2AuthenticationException</code> | Lỗi trong quá trình tạo/kiểm tra authentication | OAuth2 Login, OIDC authentication provider |
| <code>AuthenticationFailureHandler</code> | Cách ứng dụng trả lời browser khi đăng nhập thất bại | Servlet OAuth2 Login |

Không nên xem tất cả exception này là tương đương: **giai đoạn thất bại** và **ngữ cảnh xử lý** khác nhau. Ví dụ callback sai state thường thất bại trước khi gọi token endpoint; không nên bịa một lỗi <code>invalid_grant</code> của Token Endpoint cho trường hợp đó.

## 4. Token response đi qua các thành phần nào?

Với Authorization Code Flow ở Spring Security Servlet:

~~~mermaid
flowchart TD
    A["OAuth2LoginAuthenticationFilter nhận callback"] --> B["OAuth2LoginAuthenticationProvider / OIDC provider"]
    B --> C["OAuth2AccessTokenResponseClient cho authorization_code"]
    C --> D["HTTP request tới Token Endpoint"]
    D --> E{"HTTP response"}
    E -->|2xx JSON token hợp lệ| F["Chuyển thành OAuth2AccessTokenResponse"]
    E -->|4xx JSON OAuth error| G["Đọc và chuyển thành OAuth2Error"]
    E -->|Sai định dạng / lỗi transport| H["Lỗi chuyển đổi hoặc exception ở HTTP layer"]
    G --> I["OAuth2AuthorizationException"]
    H --> J["Adapter xử lý an toàn theo provider, hoặc fail closed"]
    J --> I
    I --> K["Luồng login thất bại, AuthenticationFailureHandler"]
    F --> L["Xử lý OAuth2/OIDC authentication tiếp theo"]
~~~

Những API/lớp có liên quan:

- <code>OAuth2AccessTokenResponseClient&lt;T extends AbstractOAuth2AuthorizationGrantRequest&gt;</code>: hợp đồng lấy token response theo một grant request.
- <code>OAuth2AuthorizationCodeGrantRequest</code>: chứa thông tin cần để đổi authorization code lấy token.
- <code>OAuth2AccessTokenResponse</code>: biểu diễn token response đã được chuyển đổi thành công.
- <code>OAuth2ErrorHttpMessageConverter</code>: converter cho response lỗi OAuth 2.0 dạng JSON ở các đường xử lý HTTP tương ứng.
- <code>OAuth2AccessTokenResponseHttpMessageConverter</code>: converter dùng khi đọc token response thành công và có các hook chuyển đổi dữ liệu.
- <code>OAuth2ErrorResponseErrorHandler</code>: handler có thể được sử dụng trong cơ chế HTTP dựa trên <code>RestTemplate</code> để chuyển lỗi chuẩn thành exception.

Tên client HTTP thực tế phụ thuộc phiên bản Spring Security. Chẳng hạn Spring Security 6.4+ có <code>RestClientAuthorizationCodeTokenResponseClient</code>; các phiên bản trước sử dụng <code>DefaultAuthorizationCodeTokenResponseClient</code> với <code>RestOperations</code>. Khi triển khai tùy biến, cần sử dụng đúng API của phiên bản đang chạy và điểm mở rộng được nó hỗ trợ.

Điều cần hiểu là **có hai hướng chuyển đổi**:

1. **Success converter:** chuyển JSON token hợp lệ thành <code>OAuth2AccessTokenResponse</code>.
2. **Error converter / error handler:** nhận biết response lỗi và chuyển thành <code>OAuth2Error</code>/<code>OAuth2AuthorizationException</code>.

Không chuyển một JSON lỗi thành success token chỉ vì HTTP status trả 200, và cũng không tạo token response với access token rỗng để che giấu lỗi.

## 5. Phân loại response không đúng chuẩn

Không phải mọi response lỗi đều có cùng cách xử lý. Trước khi viết adapter, cần phân loại rõ.

| Response thực tế | Đánh giá | Hành vi nên có |
|---|---|---|
| HTTP 400 với JSON <code>{"error":"invalid_grant"}</code> | Lỗi chuẩn | Chuyển thành OAuth2Error <code>invalid_grant</code> |
| HTTP 401 với JSON <code>{"error":"invalid_client"}</code> | Lỗi xác thực Client, có thể chuẩn | Giữ đúng mã lỗi; kiểm tra Client authentication |
| HTTP 400 với <code>{"error_code":"CODE_EXPIRED"}</code> | Provider dùng tên trường riêng | Adapter chuyên biệt ánh xạ theo hợp đồng đã biết |
| HTTP 400 với <code>{"error":{"code":"INVALID_CODE"}}</code> | JSON lỗi lồng object | Adapter chuyên biệt đọc schema provider |
| HTTP 200 với <code>{"error":"invalid_grant"}</code> | Provider gửi sai HTTP status | Nhận diện body lỗi và từ chối token exchange |
| HTTP 200 với <code>{"access_token": "...", "error": "..."}</code> | Response mâu thuẫn, không đáng tin | Từ chối, không chọn tùy tiện một nhánh |
| HTTP 200 nhưng thiếu <code>access_token</code> hoặc <code>token_type</code> | Success body không đạt yêu cầu token response | Báo response sai định dạng; không bịa giá trị |
| HTTP 502/503 với body HTML | Lỗi gateway/OP | Phân loại lỗi hạ tầng, không phân tích HTML thành OAuth code |
| HTTP 429 với JSON riêng của gateway | Rate limit | Ghi nhận HTTP 429 và retry policy riêng, không đổi thành <code>invalid_grant</code> |
| HTTP 302 về trang login của provider | Token endpoint trả redirect bất thường | Không follow redirect vô điều kiện; kiểm tra URL, auth và proxy |
| Timeout, DNS/TLS failure, connection reset | Không có OAuth response hoàn chỉnh | Ghi lỗi transport, không tự đoán lỗi OAuth |
| HTTP 400 với body không phải JSON hoặc JSON bị cắt | Không thể parse theo giao thức | Fail closed, giữ mã lỗi kỹ thuật an toàn |

**Fail closed** ở đây nghĩa là không cho phép luồng đăng nhập/trao đổi token tiếp tục như thành công khi chưa có một token response hợp lệ và được kiểm tra.

## 6. Thứ tự xử lý an toàn ở ranh giới Token Endpoint

Một adapter đáng tin cậy không chỉ đổi tên trường từ <code>error_code</code> sang <code>error</code>. Nó cần có quy tắc nhận diện lỗi, kiểm tra giới hạn input và phân biệt lỗi giao thức với lỗi mạng.

Có thể mô hình hóa:

~~~mermaid
flowchart TD
    A["Nhận kết quả HTTP từ Token Endpoint"] --> B{"Có response HTTP?"}
    B -->|Không| N["Transport error: timeout, TLS, DNS..."]
    B -->|Có| C{"Kích thước/Content-Type có chấp nhận được?"}
    C -->|Không| X["Invalid/unexpected token response"]
    C -->|Có| D{"HTTP status"}
    D -->|2xx| E{"JSON có error / success fields?"}
    E -->|Lỗi| L["Chuẩn hóa lỗi provider"]
    E -->|Token hợp lệ| S["Chuyển token response"]
    E -->|Thiếu/mâu thuẫn| X
    D -->|4xx| F{"Có OAuth error chuẩn hoặc schema hỗ trợ?"}
    F -->|Có| L
    F -->|Không| X
    D -->|429/5xx/redirect| G["Phân loại HTTP/provider failure"]
    L --> O["OAuth2Error, sau đó exception phù hợp"]
    X --> O
    G --> O
    N --> O
    S --> T["Đi tiếp quy trình OIDC/OAuth2 validation"]
~~~

### 6.1. Chỉ chấp nhận schema mà ứng dụng có chủ đích hỗ trợ

Ví dụ provider A tài liệu hóa response:

~~~json
{
  "error_code": "AUTHORIZATION_CODE_EXPIRED",
  "message": "Please authorize again",
  "request_id": "req-demo-42"
}
~~~

Ta có thể ánh xạ <code>AUTHORIZATION_CODE_EXPIRED</code> sang <code>invalid_grant</code> vì **ngữ nghĩa được xác nhận rõ**. Không nên viết quy tắc chung “mọi lỗi HTTP 400 → invalid_grant”; nó sẽ che khuất <code>invalid_client</code>, <code>invalid_scope</code> và những lỗi khác.

Nếu provider không tài liệu hóa schema riêng, ưu tiên **giữ lỗi kỹ thuật generic** và lưu thông tin phân loại an toàn phục vụ điều tra. Tự đoán nguyên nhân theo một thông điệp tiếng Anh hoặc HTML thường dễ sai khi provider đổi ngôn ngữ, phiên bản hoặc tầng proxy.

### 6.2. Giới hạn dữ liệu lỗi bên ngoài

Nội dung lỗi của provider là dữ liệu **không đáng tin cậy**:

- Giới hạn kích thước response đọc vào bộ nhớ. Một trang HTML lỗi hàng MB không cần được giữ làm OAuth2Error.
- Không chuyển toàn bộ body, stack trace, headers chứa credential hoặc URL có authorization code vào <code>error_description</code>.
- Không phản chiếu <code>error_description</code> thô ra trang login hoặc JSON gửi cho người dùng.
- Không tự động mở <code>error_uri</code> khi URI đến từ provider không được kiểm chứng; ứng dụng có thể bỏ giá trị này hoặc chỉ chấp nhận URL tài liệu từ host tin cậy.
- Không chuyển đổi loại lỗi một cách quá rộng khiến hệ thống giám sát mất tín hiệu của các lỗi HTTP 5xx, 429, TLS hoặc timeout.

## 7. Ví dụ Java: chuẩn hóa lỗi JSON riêng thành OAuth2Error

Sau đây là một mapper đơn giản cho **một provider cụ thể**, chỉ minh họa khâu chuyển đổi JSON lỗi đã nhận được tại HTTP boundary. Giả sử provider tài liệu hóa các mã <code>AUTHORIZATION_CODE_EXPIRED</code>, <code>BAD_CLIENT_CREDENTIALS</code> và <code>SCOPE_NOT_ALLOWED</code>.

Ví dụ dùng Jackson (thường có sẵn với Spring Boot web starter):

~~~java
package example.security.oauth2;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.security.oauth2.core.OAuth2Error;

import java.util.Set;

public final class ProviderTokenErrorMapper {

    private static final int MAX_ERROR_BODY_BYTES = 16 * 1024;
    private static final Set<String> STANDARD_CODES = Set.of(
        "invalid_request",
        "invalid_client",
        "invalid_grant",
        "unauthorized_client",
        "unsupported_grant_type",
        "invalid_scope"
    );

    private final ObjectMapper objectMapper;

    public ProviderTokenErrorMapper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * Nhận HTTP status và body đã được giới hạn/đọc tại HTTP layer.
     * Chỉ tạo metadata lỗi an toàn; tuyệt đối không tạo token response.
     */
    public OAuth2Error fromHttpFailure(int httpStatus, byte[] body) {
        if (body == null || body.length == 0 ||
                body.length > MAX_ERROR_BODY_BYTES) {
            return genericError(httpStatus);
        }

        try {
            JsonNode root = objectMapper.readTree(body);
            if (root == null || !root.isObject()) {
                return genericError(httpStatus);
            }

            String code = text(root, "error");

            // Một số provider trả error dưới dạng object.
            if (code == null && root.path("error").isObject()) {
                code = text(root.path("error"), "code");
            }

            // Chỉ hỗ trợ schema riêng đã biết của provider này.
            if (code == null) {
                code = text(root, "error_code");
            }

            String normalized = normalizeCode(code);
            if (normalized == null) {
                return genericError(httpStatus);
            }

            // Thông điệp có kiểm soát, không phản chiếu message thô.
            return new OAuth2Error(
                normalized,
                safeDescription(normalized),
                null
            );
        } catch (JsonProcessingException exception) {
            return genericError(httpStatus);
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isTextual()) {
            return null;
        }
        String result = value.asText();
        return result.isBlank() ? null : result;
    }

    private static String normalizeCode(String providerCode) {
        if (providerCode == null) {
            return null;
        }
        if (STANDARD_CODES.contains(providerCode)) {
            return providerCode;
        }
        return switch (providerCode) {
            case "AUTHORIZATION_CODE_EXPIRED" -> "invalid_grant";
            case "BAD_CLIENT_CREDENTIALS" -> "invalid_client";
            case "SCOPE_NOT_ALLOWED" -> "invalid_scope";
            default -> null;
        };
    }

    private static OAuth2Error genericError(int httpStatus) {
        String code = httpStatus == 429
            ? "provider_rate_limited"
            : "provider_token_response_error";
        return new OAuth2Error(
            code,
            "OAuth2 token request could not be completed",
            null
        );
    }

    private static String safeDescription(String code) {
        return switch (code) {
            case "invalid_client" -> "Client authentication was rejected";
            case "invalid_grant" -> "Authorization grant was rejected";
            case "invalid_scope" -> "Requested scope was rejected";
            default -> "OAuth2 token request was rejected";
        };
    }
}
~~~

**Giới hạn của ví dụ:** <code>fromHttpFailure</code> chỉ chuẩn hóa **response đã được xác định là lỗi**. Nó không tự gửi token request, không nhận diện success body và không biến mọi HTTP 200 thành lỗi. Một adapter đầy đủ cần kiểm tra response thành công **trước khi** dùng success converter; với response HTTP 200 có trường <code>error</code>, adapter phải phát hiện sự bất thường và chuyển sang nhánh lỗi thay vì gọi success converter.

Cần giới hạn body **ngay khi đọc HTTP stream**, không đọc vô hạn rồi mới kiểm tra <code>body.length</code>. Lớp mapper kiểm tra thêm độ dài ở đây là phòng vệ bổ sung, không thay cho giới hạn ở transport layer.

### 7.1. Vì sao không dùng error_description của provider trực tiếp?

Một response có thể chứa:

~~~json
{
  "error": "invalid_client",
  "error_description": "Secret rejected for client web-prod; token=...; trace=..."
}
~~~

Nếu chép nguyên <code>error_description</code> sang UI hoặc log, ứng dụng có thể làm lộ bí mật hoặc thông tin hạ tầng. Việc ánh xạ thành mô tả cố định giúp phân loại lỗi mà không để nội dung do provider điều khiển lan ra ngoài.

Ở hệ thống giám sát nội bộ, có thể lưu **mã lỗi đã được giới hạn/allowlist**, mã HTTP, tên provider, correlation ID do ứng dụng tạo và thời điểm. Chỉ lưu provider request ID nếu đã được kiểm tra độ dài, định dạng và chính sách dữ liệu.

### 7.2. Một mapper không tự sửa được token response sai chuẩn

Nếu provider trả:

~~~json
{
  "token": "ACCESS_TOKEN_VALUE",
  "type": "Bearer",
  "expires": 3600
}
~~~

đây là trường hợp **success schema không chuẩn**, khác với JSON lỗi. Nếu bắt buộc hỗ trợ provider này, adapter phải chuyển dữ liệu thành representation chuẩn trước khi tạo <code>OAuth2AccessTokenResponse</code>:

~~~json
{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "Bearer",
  "expires_in": 3600
}
~~~

Nhưng chỉ làm điều đó nếu schema, kiểu dữ liệu và giá trị được **tài liệu hóa rõ**. Không tùy ý nhận field có tên <code>token</code> hoặc mặc định <code>token_type=Bearer</code> khi provider không có hợp đồng tương thích. Với OIDC, <code>id_token</code> cần được giữ đúng và phải đi qua xác minh ID Token; không dùng mapper để bỏ kiểm tra chữ ký hoặc issuer.

## 8. Tích hợp vào Spring Security OAuth2 Client

Điểm mở rộng được Spring Security cung cấp cho Authorization Code Flow là:

~~~java
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
~~~

Spring Security gọi client này khi thực hiện bước đổi authorization code lấy token. Ứng dụng có thể cung cấp implementation của mình bằng DSL <code>oauth2Login().tokenEndpoint().accessTokenResponseClient(...)</code>.

### 8.1. Ví dụ decorator cho lỗi đã được parse

Khi HTTP converter của thư viện **đã parse được OAuth2Error**, ta có thể bọc token response client để chuẩn hóa một mã riêng của provider. Đây là một wrapper đơn giản, độc lập với cách gửi HTTP request:

~~~java
package example.security.oauth2;

import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

public final class TranslatingAuthorizationCodeTokenClient
    implements OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest> {

    private final OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
        delegate;

    public TranslatingAuthorizationCodeTokenClient(
        OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest> delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AccessTokenResponse getTokenResponse(
            OAuth2AuthorizationCodeGrantRequest request) {
        try {
            return delegate.getTokenResponse(request);
        } catch (OAuth2AuthorizationException ex) {
            OAuth2Error original = ex.getError();

            if ("AUTHORIZATION_CODE_EXPIRED".equals(original.getErrorCode())) {
                OAuth2Error normalized = new OAuth2Error(
                    "invalid_grant",
                    "Authorization grant was rejected",
                    null
                );
                throw new OAuth2AuthorizationException(normalized, ex);
            }

            throw ex;
        }
    }
}
~~~

Wrapper bảo toàn behavior của delegate cho các response hợp lệ và chỉ can thiệp khi bắt được mã lỗi riêng đã biết. Nó **không** thể tự sửa HTML, JSON hỏng hoặc HTTP 200 chứa lỗi nếu delegate không đưa dữ liệu thô đến đây dưới dạng <code>OAuth2AuthorizationException</code> phù hợp.

Để xử lý các trường hợp response sai định dạng, cần chặn ở **tầng HTTP message conversion/error handling** của token response client hoặc tạo một implementation <code>OAuth2AccessTokenResponseClient</code> riêng được thiết kế cho provider đó. Không nên bắt mọi <code>RuntimeException</code> từ delegate rồi trả một token response giả.

### 8.2. Gắn custom client vào oauth2Login()

Ví dụ cấu hình Servlet dùng client bọc ở trên; mã sử dụng lớp <code>RestClientAuthorizationCodeTokenResponseClient</code> có trong các phiên bản Spring Security hỗ trợ RestClient:

~~~java
package example.security;

import example.security.oauth2.TranslatingAuthorizationCodeTokenClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        var delegate = new RestClientAuthorizationCodeTokenResponseClient();
        var translatedClient =
            new TranslatingAuthorizationCodeTokenClient(delegate);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(translatedClient))
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/login?error")));

        return http.build();
    }
}
~~~

Ví dụ này cần dependency <code>spring-boot-starter-oauth2-client</code>, một <code>ClientRegistration</code> hợp lệ và Spring Security phiên bản có <code>RestClientAuthorizationCodeTokenResponseClient</code> (Spring Security 6.4+). Với các dự án Spring Security cũ hơn, điểm khởi tạo HTTP delegate có thể là <code>DefaultAuthorizationCodeTokenResponseClient</code>; không nên sao chép nguyên tên lớp nếu dependency đang chạy chưa có API này.

<code>SimpleUrlAuthenticationFailureHandler</code> chỉ trả người dùng về trang lỗi chung, tránh hiển thị thông điệp nhạy cảm từ token response. Với UI riêng, có thể cung cấp thông báo dễ hiểu và mã hỗ trợ; không nhúng raw <code>error_description</code> của provider vào query string.

> Không cấu hình một custom client chỉ để đổi tên mã lỗi nếu provider đã trả đúng lỗi chuẩn và Spring Security xử lý được. Việc thêm adapter tạo thêm code và điểm lỗi mới, nên chỉ dùng khi có bằng chứng thực tế về khác biệt của provider.

### 8.3. Xử lý response không chuẩn ở HTTP boundary

Một adapter thực tế cho provider trả JSON riêng thường gồm các lớp trách nhiệm:

~~~text
OAuth2AccessTokenResponseClient
  |
  +-- Tạo token request đúng grant/client authentication
  |
  +-- HTTP client (HTTPS, timeout, redirect policy, body size limit)
  |
  +-- Phân loại HTTP status + Content-Type
  |
  +-- Parse lỗi chuẩn hoặc lỗi JSON riêng đã biết
  |     -> ProviderTokenErrorMapper
  |     -> OAuth2AuthorizationException(OAuth2Error)
  |
  +-- Parse success token response đúng schema
        -> OAuth2AccessTokenResponse
~~~

Nên tận dụng token client có sẵn và các hook converter/error handler trước khi tự triển khai toàn bộ token exchange. Nếu buộc tự cài đặt, ngoài việc parse JSON còn phải xử lý chính xác <code>grant_type</code>, <code>code</code>, <code>redirect_uri</code>, client authentication, PKCE verifier, request encoding, HTTPS và những yêu cầu OAuth2/OIDC tương ứng. Sửa response parser không được làm thay đổi cơ chế tạo/token request hợp lệ.

### 8.4. Không nhầm lỗi OAuth2 Login với lỗi gọi API

<code>AuthenticationFailureHandler</code> xử lý **đăng nhập Servlet thất bại**, thường điều hướng browser. Nếu ứng dụng chủ động dùng <code>OAuth2AuthorizedClientManager</code> để lấy token theo client credentials hoặc refresh token, lỗi có thể xuất hiện ở service layer, background job hoặc HTTP API handler, **không đi qua OAuth2 Login failure handler**.

Tương tự, một Resource Server từ chối access token bằng <code>invalid_token</code> ở <code>WWW-Authenticate</code> là tình huống khác với Token Endpoint trả <code>invalid_grant</code>. Không gom mọi OAuth error vào một bộ chuyển đổi bỏ qua ngữ cảnh.

## 9. HTTP 200 nhưng body chứa lỗi

Đây là trường hợp dễ mắc lỗi khi chỉ dựa vào HTTP status:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "error_code": "AUTHORIZATION_CODE_EXPIRED",
  "message": "authorization code has expired"
}
~~~

Nếu HTTP library chỉ kích hoạt error handler cho status 4xx/5xx, JSON này có thể đi vào **success converter**. Success converter thường mong đợi <code>access_token</code> và <code>token_type</code>, rồi báo lỗi parse/validation. Ứng dụng tùy biến cần nhận diện được schema riêng ở ngay HTTP boundary và chuyển về <code>OAuth2Error("invalid_grant", ...)</code> như một **thất bại**, dù HTTP status bằng 200.

Tuy nhiên, không được viết quy tắc quá dễ dãi như:

~~~text
Nếu response JSON có trường "message" thì coi là lỗi.
~~~

Vì <code>message</code> không phải field lỗi chuẩn và có thể xuất hiện ở một object hợp lệ khác. Cách đúng là **nhận diện schema của provider cụ thể** theo tài liệu và giới hạn rõ các trạng thái hỗ trợ.

Response có đồng thời <code>access_token</code> và <code>error</code> cũng không được chấp nhận. Đây là dữ liệu mâu thuẫn, nên phân loại invalid token response, không chọn một phần có lợi để tiếp tục đăng nhập.

## 10. HTTP 401, 429, 5xx và lỗi transport

### 10.1. HTTP 401 và invalid_client

Lỗi <code>invalid_client</code> thường liên quan tới xác thực Client:

- Secret không khớp hoặc đã được thay đổi.
- Chọn sai <code>client-authentication-method</code> như <code>client_secret_basic</code> so với cơ chế IdP đã đăng ký.
- Dùng Client ID/secret của staging với Token Endpoint production.
- Key/certificate không phù hợp khi dùng cơ chế xác thực bất đối xứng.

Không nên tự động “thử lại không có secret” hoặc chuyển từ confidential Client sang public Client để vượt lỗi. Điều đó làm thay đổi mô hình bảo mật và thường chỉ tạo thêm request thất bại.

### 10.2. HTTP 429: rate limit

HTTP 429 thường là giới hạn tốc độ ở provider hoặc gateway. Nó **không phải một trong sáu mã lỗi Token Endpoint cốt lõi**. Có thể ghi nhận một mã nội bộ như <code>provider_rate_limited</code> và giữ status 429 trong telemetry.

Nếu provider đưa header <code>Retry-After</code>, hệ thống có thể tham khảo cho chính sách vận hành. Tuy nhiên, không tự động retry vô hạn hay retry theo một thông điệp lỗi tùy ý. Với authorization code, yêu cầu đổi code thường là yêu cầu **chỉ được thực hiện một lần thành công**.

### 10.3. HTTP 5xx và trạng thái kết quả chưa xác định

Khi nhận HTTP 503 trước khi provider xử lý grant, một lần thử lại có thể hữu ích trong một số môi trường. Nhưng khi **timeout sau khi gửi token request**, Client có thể không biết Token Endpoint đã tiêu thụ authorization code và cấp token hay chưa.

Nếu tự động gửi lại cùng code, server có thể trả <code>invalid_grant</code> vì code đã được dùng một lần. Do đó:

- Không coi mọi timeout là “chắc chắn server chưa xử lý”.
- Không tự động retry Authorization Code Exchange theo chính sách dùng cho GET/idempotent request.
- Phân loại trạng thái **kết quả chưa xác định** và cho người dùng bắt đầu một authorization flow mới khi thích hợp.
- Với client credentials/refresh token, chính sách retry có thể khác, nhưng phải dựa trên semantics và tài liệu cụ thể của provider.

### 10.4. HTML hoặc redirect từ gateway

Ví dụ token endpoint trả:

~~~http
HTTP/1.1 502 Bad Gateway
Content-Type: text/html

<html><body>Upstream temporarily unavailable</body></html>
~~~

Đây không phải một OAuth2Error JSON chuẩn. Không parse HTML bằng regex để tìm cụm <code>invalid_client</code> hoặc <code>invalid_grant</code>. Hãy phân loại hạ tầng/response không hợp lệ và kiểm tra gateway, DNS, TLS, đường dẫn Token Endpoint.

Nếu token endpoint trả HTTP 302 tới trang đăng nhập tương tác, hãy kiểm tra endpoint đã cấu hình và proxy authentication. Một token exchange chuẩn được gửi bởi backend, không nên phụ thuộc vào redirect browser hay HTML form.

## 11. OIDC: lỗi token response và kiểm tra ID Token

Trong OIDC Authorization Code Flow, token response thường có thêm <code>id_token</code>. Sau khi HTTP response được parse thành công, Client vẫn phải kiểm tra:

- Chữ ký ID Token bằng khóa công khai từ JWKS thuộc issuer tin cậy.
- Claim <code>iss</code> đúng OpenID Provider được cấu hình.
- Claim <code>aud</code> phù hợp với Client ID và các ràng buộc <code>azp</code> khi áp dụng.
- <code>exp</code>, <code>iat</code> và các ràng buộc thời gian theo quy định.
- <code>nonce</code> khi được sử dụng trong authorization request và các ràng buộc OIDC tương ứng.

Một provider trả HTTP 200 với các trường token hợp lệ về mặt JSON nhưng ID Token có issuer sai **vẫn là lỗi authentication**, không phải thành công.

Nếu tùy biến success converter để hỗ trợ tên trường riêng của provider, không xóa <code>id_token</code>, không vô hiệu hóa OIDC validation và không chấp nhận một JWT tùy ý làm ID Token. Việc chuẩn hóa schema HTTP chỉ là một phần của kiểm tra giao thức.

## 12. Hành vi ứng dụng và trải nghiệm người dùng khi Token Endpoint lỗi

Một lỗi Token Endpoint thường xảy ra **sau khi người dùng đã thao tác ở OP**, nên thông báo “Sai mật khẩu” có thể hoàn toàn không chính xác. Ứng dụng nên dùng thông điệp chung nhưng hữu ích:

> Không thể hoàn tất đăng nhập. Vui lòng thử lại. Nếu lỗi tiếp diễn, liên hệ bộ phận hỗ trợ và cung cấp mã yêu cầu.

Ở tầng vận hành, có thể phân loại:

| Phân loại nội bộ | Ví dụ | Hành vi gợi ý |
|---|---|---|
| Lỗi cấu hình Client | <code>invalid_client</code>, <code>unauthorized_client</code> | Báo cảnh báo vận hành, không retry vô hạn |
| Grant bị từ chối | <code>invalid_grant</code> | Yêu cầu bắt đầu lại login flow khi thích hợp |
| Yêu cầu scope không hợp lệ | <code>invalid_scope</code> | Điều chỉnh ClientRegistration/permission |
| Lỗi định dạng response | JSON hỏng, thiếu <code>access_token</code>, HTML | Fail closed, phân tích nhà cung cấp/gateway |
| Hạ tầng tạm thời | Timeout, 502, 503, 429 | Ghi metric và chiến lược phục hồi phù hợp |
| Lỗi xác minh OIDC | Sai chữ ký, issuer, audience, nonce | Từ chối authentication, kiểm tra issuer/JWKS/flow |

Với Servlet <code>oauth2Login()</code>, <code>AuthenticationFailureHandler</code> có thể chuyển về trang đăng nhập cùng một thông báo chung. Nếu cần phân biệt lỗi cho người dùng, chỉ truyền **mã hỗ trợ do ứng dụng kiểm soát**, không truyền raw OAuth error, token hay query string callback.

Trong service-to-service Client Credentials Flow, ứng dụng có thể trả HTTP 502/503 hoặc lỗi nghiệp vụ riêng lên caller tùy hợp đồng API, nhưng không nên trả nguyên JSON lỗi chứa thông tin nội bộ của Authorization Server.

## 13. Quan sát lỗi trong production

Một hệ thống có nhiều provider nên theo dõi tối thiểu:

- **Tên registration/provider được allowlist**, không phải URL động do người dùng cung cấp.
- **Grant type**: authorization_code, refresh_token, client_credentials.
- **Giai đoạn lỗi**: tạo request, HTTP transport, parse error response, success converter, ID Token validation.
- **HTTP status** (nếu thực sự nhận response).
- **Mã OAuth2Error chuẩn hóa** hoặc mã lỗi nội bộ có kiểm soát.
- **Tần suất và xu hướng** theo provider/môi trường; correlation ID do ứng dụng tạo.

Tuyệt đối tránh ghi vào log, metric label hoặc exception gửi ra UI:

- <code>client_secret</code>, HTTP <code>Authorization</code> header chứa credential.
- Authorization code, PKCE verifier, refresh token.
- Access token, ID Token nguyên bản.
- Toàn bộ URL callback có <code>code</code>/<code>state</code> trong query.
- Raw body response chưa được rà soát từ Token Endpoint.

Không gắn raw <code>error_description</code> vào metric label vì vừa có thể làm lộ dữ liệu, vừa tạo lượng nhãn không giới hạn. Dùng các nhóm lỗi có tập giá trị hữu hạn.

Nếu cần kiểm tra raw response ở môi trường thử nghiệm do đội phát triển kiểm soát, phải dùng dữ liệu giả, tắt xuất dữ liệu nhạy cảm và giới hạn quyền truy cập. Không dựa vào logging raw token traffic như một phương thức quan sát production.

## 14. Các lỗi thiết kế thường gặp

### 14.1. Bắt mọi exception rồi chuyển thành invalid_grant

~~~java
try {
    return delegate.getTokenResponse(request);
} catch (RuntimeException ex) {
    throw new OAuth2AuthorizationException(
        new OAuth2Error("invalid_grant")
    );
}
~~~

**Không nên triển khai theo cách này.** Nó biến DNS failure, timeout, lỗi JSON và cả bug trong ứng dụng thành <code>invalid_grant</code>, khiến đội vận hành điều tra sai và làm mất nguyên nhân thật. Chỉ ánh xạ **những schema/mã lỗi đã xác nhận**; với lỗi khác, giữ exception hoặc chuyển thành lỗi nội bộ có phân loại rõ.

### 14.2. Coi response 2xx luôn thành công

HTTP 200 có thể chứa body lỗi riêng hoặc JSON thiếu những trường bắt buộc. Cần kiểm tra nội dung trước khi coi token exchange hoàn tất. Không tự tạo access token rỗng để tránh converter ném lỗi.

### 14.3. Coi mọi HTTP 401 là invalid_client

HTTP 401 có thể xuất phát từ reverse proxy hoặc gateway yêu cầu một lớp authentication khác với OAuth2 Client authentication. Chỉ kết luận là <code>invalid_client</code> khi response/nguồn thông tin đáng tin cậy cho thấy điều đó; nếu không, giữ phân loại lỗi HTTP/hạ tầng.

### 14.4. Tắt xác minh TLS hoặc follow redirect tùy ý

Token request mang credential và authorization code/refresh token qua HTTPS. Không tắt kiểm tra chứng chỉ hay tự động chuyển token request sang bất kỳ Location nào từ HTTP 302. Rủi ro tiết lộ bí mật cao hơn nhiều so với lợi ích “đăng nhập qua được”.

### 14.5. Chuyển lỗi nội bộ thành OAuthError chuẩn nhưng sai ngữ nghĩa

Mã chuẩn như <code>invalid_client</code> hoặc <code>invalid_grant</code> mang ý nghĩa cụ thể. Nếu không thể xác nhận nguyên nhân, dùng mã lỗi nội bộ có prefix dễ phân biệt, ví dụ <code>provider_token_response_error</code>. Không mạo nhận đây là lỗi OAuth chuẩn do Authorization Server phát ra.

### 14.6. Bỏ qua AuthenticationFailureHandler

Token response client có thể phân loại lỗi rất tốt, nhưng nếu tầng đăng nhập ném message/raw exception ra trình duyệt thì dữ liệu nhạy cảm vẫn bị lộ. Cần xử lý lỗi xuyên suốt: **HTTP adapter → OAuth2Error/exception → authentication failure handler → thông báo người dùng an toàn**.

## 15. Tình huống thực hành

### Bài 1 — Lỗi chuẩn invalid_grant

Token Endpoint trả:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant","error_description":"code already used"}
~~~

**Câu hỏi:** <code>OAuth2Error.errorCode</code> nên bằng gì? Có nên tự động retry cùng authorization code không?

**Đáp án:** Giữ <code>invalid_grant</code>. Không retry tự động cùng code như một request idempotent thông thường. Xem xét code đã bị dùng, hết hạn, redirect URI và PKCE; có thể yêu cầu người dùng khởi tạo lại login flow.

### Bài 2 — HTTP 200 chứa lỗi

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"error_code":"AUTHORIZATION_CODE_EXPIRED","message":"expired"}
~~~

**Câu hỏi:** Vì sao success converter không nên tạo <code>OAuth2AccessTokenResponse</code>?

**Đáp án:** Body không có các trường token bắt buộc và mô tả lỗi theo schema riêng. Adapter đã biết schema provider có thể map <code>AUTHORIZATION_CODE_EXPIRED</code> thành <code>invalid_grant</code>, rồi ném <code>OAuth2AuthorizationException</code>; HTTP 200 không biến lỗi thành thành công.

### Bài 3 — Lỗi gateway trả HTML

~~~http
HTTP/1.1 502 Bad Gateway
Content-Type: text/html

<html><body>Upstream unavailable</body></html>
~~~

**Câu hỏi:** Có nên parse thành <code>invalid_client</code> vì browser/login flow thất bại?

**Đáp án:** Không. Đây là lỗi HTTP/gateway hoặc response sai chuẩn, không đủ bằng chứng về Client authentication. Hãy ghi nhận HTTP 502 cùng tên provider, loại lỗi hạ tầng và correlation ID an toàn; trả thông báo đăng nhập thất bại chung.

### Bài 4 — Mapping sai

Provider trả:

~~~json
{
  "error_code": "SCOPE_NOT_ALLOWED",
  "message": "requested scope is not granted"
}
~~~

**Câu hỏi:** Có thể map sang mã nào? Cần kiểm tra gì?

**Đáp án:** Nếu hợp đồng provider xác nhận đúng ngữ nghĩa, map sang <code>invalid_scope</code>. Sau đó kiểm tra scope được yêu cầu trong ClientRegistration và chính sách cấp scope tại OP, thay vì chỉ thay error message.

### Bài 5 — Timeout sau khi gửi code

Client đã gửi authorization code và bị read timeout, không nhận được response.

**Câu hỏi:** Có thể chắc chắn code chưa được tiêu thụ không?

**Đáp án:** Không. Token Endpoint có thể đã xử lý request nhưng response bị mất. Không retry mù cùng code; cần xử lý tình huống kết quả chưa xác định và khởi tạo flow mới khi phù hợp.

### Bài 6 — Thiết kế một adapter cho provider riêng

Provider nội bộ trả hai kiểu:

~~~json
{"error":{"code":"BAD_CLIENT_CREDENTIALS","detail":"..."}}
~~~

~~~json
{"error":{"code":"AUTHORIZATION_CODE_EXPIRED","detail":"..."}}
~~~

Yêu cầu:

1. Tại HTTP boundary, giới hạn body, kiểm tra Content-Type, HTTP status và schema lỗi đã công bố.
2. Ánh xạ <code>BAD_CLIENT_CREDENTIALS → invalid_client</code>, <code>AUTHORIZATION_CODE_EXPIRED → invalid_grant</code>.
3. Giữ mô tả lỗi do ứng dụng kiểm soát; không echo <code>detail</code>.
4. Ném <code>OAuth2AuthorizationException</code> cùng <code>OAuth2Error</code> phù hợp.
5. Tại OAuth2 Login, chuyển người dùng tới trang lỗi chung bằng <code>AuthenticationFailureHandler</code>.
6. Với JSON lạ/HTML/timeout, không mạo nhận một trong hai mã lỗi đã biết.

Adapter chỉ được triển khai khi provider có hợp đồng rõ ràng. Các bài test tích hợp ở giai đoạn kiểm tra nội dung/kỹ thuật của dự án có thể dùng mock Token Endpoint để quan sát các trường hợp thành công, lỗi chuẩn, lỗi riêng, body hỏng và HTTP 200 bất thường.

## 16. Ghi nhớ

- **Token Endpoint lỗi chuẩn** thường trả JSON gồm <code>error</code>, tùy chọn <code>error_description</code> và <code>error_uri</code>; HTTP status thường 400 hoặc 401 với <code>invalid_client</code>.
- **<code>OAuth2Error</code>** chứa mã, mô tả và URI lỗi. <code>OAuth2AuthorizationException</code> thường thể hiện lỗi token exchange; <code>OAuth2AuthenticationException</code> xuất hiện trong ngữ cảnh authentication.
- **<code>OAuth2AccessTokenResponseClient</code>** là điểm mở rộng Token Endpoint theo grant; khi dùng Servlet OAuth2 Login có thể gắn implementation qua <code>oauth2Login().tokenEndpoint().accessTokenResponseClient(...)</code>.
- **Response không chuẩn** phải được phân loại dựa trên status, Content-Type, schema và ngữ nghĩa đã biết. Không nhận HTTP 200 chứa lỗi thành công, không coi mọi HTTP 400 là <code>invalid_grant</code>.
- **Lỗi kết nối/HTTP gateway** không tự động là OAuth error do Authorization Server trả. Timeout sau khi gửi authorization code có thể dẫn đến kết quả chưa xác định; tránh retry mù.
- **Thông tin lỗi từ provider là dữ liệu không đáng tin cậy**. Chỉ log dữ liệu đã làm sạch, giữ thông báo UI an toàn và không bỏ qua xác minh TLS, PKCE hay ID Token.

### Tài liệu tham khảo

- **RFC 6749 — The OAuth 2.0 Authorization Framework**, mục 5.1 và 5.2: token success/error response, các mã lỗi và HTTP status.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: lỗi Bearer khi Resource Server từ chối access token; phân biệt với Token Endpoint error.
- **RFC 7636 — Proof Key for Code Exchange (PKCE)**: token exchange dùng code verifier và các điều kiện đối với authorization code.
- **OpenID Connect Core 1.0**: token response trong OIDC Authorization Code Flow và xác minh ID Token.
- **Spring Security Reference — OAuth2 Client / OAuth2 Login**: token endpoint customization, OAuth2AccessTokenResponseClient và authentication failure handling.
- **Spring Security Java API**: OAuth2Error, OAuth2AuthorizationException, OAuth2AuthenticationException, OAuth2ErrorHttpMessageConverter và OAuth2AccessTokenResponseHttpMessageConverter.
