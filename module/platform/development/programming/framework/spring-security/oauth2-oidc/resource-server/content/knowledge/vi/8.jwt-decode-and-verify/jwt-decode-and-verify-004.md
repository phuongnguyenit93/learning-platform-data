# Xác minh chữ ký trước khi sử dụng claims để quyết định quyền

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, access token dạng JWT thường chứa những claim như `sub`, `iss`, `aud` và `scope`. API có thể dựa trên các claim này để biết bên gọi là ai và có thể thực hiện thao tác gì. Tuy nhiên, **claim chỉ là dữ liệu mà token đang tuyên bố**. Trước khi dùng claim để xác thực người gọi hoặc phân quyền, Resource Server phải bảo đảm JWT được bảo vệ bằng cơ chế mật mã hợp lệ và được cấp bởi nguồn đáng tin cậy.

Một người bất kỳ đều có thể tạo một chuỗi JSON ghi `"scope": "orders.admin"` hoặc `"role": "ADMIN"` rồi mã hóa nó bằng Base64URL. Dữ liệu đó có thể nhìn giống payload JWT, nhưng **không có giá trị cấp quyền nếu chưa được xác minh**.

> **Quy tắc cốt lõi:** Resource Server phải **xác minh chữ ký/MAC của JWS bằng khóa và thuật toán được phép**, sau đó **kiểm tra các điều kiện chấp nhận token** như issuer, audience, thời hạn và mục đích sử dụng, rồi mới **ánh xạ claims thành danh tính và authorities để quyết định quyền truy cập**. Việc giải mã Base64URL đơn thuần không phải là xác minh JWT.

## 1. Vì sao đọc claims trước khi xác minh lại nguy hiểm?

Giả sử Orders API nhận request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Payload token được nhìn thấy sau khi decode:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ORDER_SUPPORT"],
  "exp": 1893459600
}
~~~

Nếu code kiểm tra `scope` ngay sau khi giải mã payload, API có thể vô tình **tin một phát biểu do chính người gửi tự tạo**. Những trường hợp khác nhau có thể cho ra payload trông giống hệt nhau:

| Tình huống | Payload giải mã được? | Có được tin claim để phân quyền không? |
| --- | --- | --- |
| JWT hợp lệ, được issuer đáng tin ký và dành cho Orders API | Có | **Có thể**, sau khi kiểm tra thêm thời hạn, audience, scope và quyền nghiệp vụ |
| Payload bị sửa từ `orders.read` thành `orders.admin` sau khi ký | Có | **Không**, chữ ký không còn hợp lệ |
| JWT do người lạ ký bằng khóa riêng của họ | Có | **Không**, không có chuỗi tin cậy tới issuer/khóa được cấu hình |
| JWT được ký hợp lệ nhưng do issuer khác phát hành | Có | **Không**, nếu issuer đó không được API chấp nhận |
| JWT hợp lệ của Billing API mang `aud = billing-api` | Có | **Không**, token không dành cho Orders API |
| JWT có chữ ký hợp lệ nhưng đã hết hạn | Có | **Không**, token không còn được chấp nhận |
| JWT hợp lệ và đủ scope nhưng đơn 42 thuộc người khác | Có | **Không**, nếu chính sách dữ liệu không cho phép |

Hàng đầu tiên chỉ nói rằng API **có cơ sở để tin các claim đã qua xác minh**. Nó không có nghĩa mọi request chứa token ấy đều phải được trả dữ liệu.

### Một ví dụ code sai

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

// KHÔNG dùng kết quả này để xác thực hoặc phân quyền!
String[] parts = bearerToken.split("\\.");
String json = new String(
        Base64.getUrlDecoder().decode(parts[1]),
        StandardCharsets.UTF_8);

// Sai nếu parse "json" rồi tin scope/roles/sub để cho phép truy cập.
~~~

Đoạn trên chỉ thực hiện **Base64URL decode** của một phần token; nó không hề:

- Kiểm tra chữ ký hoặc MAC.
- Kiểm tra khóa ký có thuộc issuer được tin cậy hay không.
- Xác nhận thuật toán bảo vệ token được cho phép.
- Kiểm tra `iss`, `aud`, `exp`, `nbf` hoặc mục đích token.
- Xác nhận caller được truy cập bản ghi cụ thể.

Thư viện parse JWT có thể cho phép đọc claims của một token chưa được xác minh. Nếu API sử dụng kết quả đó để tạo `Authentication`, xây `GrantedAuthority` hoặc trả dữ liệu, ranh giới tin cậy đã bị vượt qua.

## 2. JWS bảo vệ nội dung JWT như thế nào?

JWT là cách biểu diễn một **JWT Claims Set**; JWT có thể được bao bọc bởi JWS để bảo vệ tính toàn vẹn, hoặc JWE để mã hóa nội dung. Trường hợp phổ biến với OAuth 2.0 Resource Server là **signed JWT dưới dạng JWS Compact Serialization**, có ba phần:

~~~text
BASE64URL(Protected Header).BASE64URL(Payload).BASE64URL(Signature)
~~~

Header ví dụ:

~~~json
{
  "alg": "RS256",
  "kid": "orders-signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

Payload là claims set:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

`typ: "at+jwt"` là ví dụ khi nhà phát hành sử dụng **JWT profile cho OAuth 2.0 access token**; không phải mọi nhà phát hành đều dùng cùng `typ`. API phải biết profile token nào nó chấp nhận và kiểm tra đúng theo hợp đồng.

### 2.1. Phần nào thực sự được ký?

Với **JWS Compact Serialization** và cách dùng JWT thông thường, dữ liệu đầu vào của thuật toán ký là:

~~~text
ASCII(BASE64URL(Protected Header) + "." + BASE64URL(Payload))
~~~

Chữ ký/MAC được tính trên **cả protected header và payload**. Khi xác minh, thư viện JOSE nhận chuỗi token, chọn khóa phù hợp từ nguồn đáng tin, kiểm tra thuật toán được phép và xác minh chữ ký bằng chính signing input này.

~~~mermaid
flowchart TD
    Receive["Nhận Bearer JWT"]
    Parts["Phân tích cấu trúc JWS Compact"]
    Policy["Chọn thuật toán và khóa theo chính sách tin cậy"]
    Verify{"Chữ ký/MAC hợp lệ?"}
    Claims["Claims có thể được dùng cho kiểm tra token"]
    Reject["Từ chối token"]

    Receive --> Parts
    Parts --> Policy
    Policy --> Verify
    Verify -->|Không| Reject
    Verify -->|Có| Claims
~~~

Sơ đồ mô tả **ranh giới tin cậy**: trước khi JWS được xác minh, header và payload là dữ liệu không đáng tin. Trong triển khai thật, một bộ giải mã cần **đọc header chưa xác minh** để biết `kid` và cách định tuyến đến bộ khóa đã cấu hình. Điều này được phép **nếu giá trị header chỉ được dùng làm gợi ý có kiểm soát trong chính sách khóa/thuật toán**; không được để token tự chỉ định thuật toán tùy ý hoặc kho khóa mà API lập tức tin.

### 2.2. Đọc được không có nghĩa sửa được mà vẫn hợp lệ

Base64URL chỉ là cách biểu diễn byte thành ký tự an toàn khi truyền qua giao thức. Payload của signed JWT thường **không bí mật**: ai cầm token cũng có thể đọc claim của nó. Nhưng nếu thay đổi `scope` hoặc `sub` trong payload sau khi JWT được ký, chữ ký gốc **không còn xác minh thành công**.

Vì vậy cần tách rõ:

~~~text
Decode JWT       -> nhìn thấy các trường, chưa xác minh
Verify JWS       -> chứng minh token không bị sửa và khớp khóa tin cậy
Validate claims  -> kiểm tra token có được API chấp nhận ở thời điểm này
Authorize        -> quyết định caller được thực hiện hành động trên dữ liệu nào
~~~

**Xác minh chữ ký không bảo vệ tính bí mật của payload.** Nếu cần che giấu claims, hệ thống phải quản lý dữ liệu phát hành hoặc dùng JWE/cơ chế mã hóa phù hợp. Gửi JWT qua HTTPS và bảo vệ Bearer token khỏi bị lộ vẫn là yêu cầu quan trọng.

## 3. Chữ ký hợp lệ với khóa nào mới đáng tin?

Một chữ ký mật mã chỉ có ý nghĩa bảo mật nếu Resource Server xác minh bằng **khóa đáng tin cậy** và thuật toán phù hợp.

### 3.1. Trường hợp phổ biến: khóa bất đối xứng

Ví dụ Authorization Server phát JWT ký bằng **RS256**:

- Authorization Server giữ **private key** và dùng nó để ký token.
- Authorization Server công bố **public key** hoặc các JWK công khai qua JWKS endpoint.
- Resource Server tải hoặc sử dụng khóa công khai **từ nguồn đã cấu hình tin cậy** để xác minh.

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as JWKS tin cậy
    participant API as Resource Server

    AS->>AS: Ký JWT bằng private key
    AS->>JWKS: Công bố public JWK theo chính sách
    API->>JWKS: Lấy/cập nhật public keys
    JWKS-->>API: JWKS
    API->>API: Xác minh JWS bằng khóa công khai phù hợp
    API->>API: Sau đó kiểm tra iss, aud, thời hạn, scope...
~~~

API **không cần private signing key** để xác minh JWT ký bất đối xứng. Không được đưa private key của Authorization Server vào Resource Server cho mục đích này.

Một số thuật toán khác dùng trong JOSE:

| Nhóm | Ví dụ | Ý nghĩa vận hành |
| --- | --- | --- |
| Chữ ký bất đối xứng RSA | `RS256`, `PS256` | AS ký bằng private key; API xác minh bằng public key |
| Chữ ký bất đối xứng EC | `ES256` | AS ký bằng private key EC; API xác minh bằng public key EC |
| MAC dùng khóa đối xứng | `HS256` | Bên ký và bên xác minh cùng biết một secret |

Với `HS256`, Resource Server muốn xác minh phải có **shared secret** và người sở hữu secret đó có khả năng tạo MAC hợp lệ. Do vấn đề phân phối và giới hạn bên có thể ký, nhiều hệ thống nhiều API ưu tiên mô hình ký bất đối xứng. Dù chọn thuật toán nào, **danh sách thuật toán được chấp nhận phải được cấu hình có chủ đích**.

### 3.2. `kid` dùng để chọn khóa, không tạo ra tin cậy

JOSE header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01"
}
~~~

`kid` là **key identifier** giúp chọn khóa khi JWKS chứa nhiều khóa do quá trình quay vòng. Resource Server có thể tìm JWK có `kid` khớp trong tập khóa của issuer đáng tin; sau đó vẫn phải xác minh chữ ký.

Không được nghĩ rằng:

- Có `kid` đúng là chữ ký tự động hợp lệ.
- Token được phép tự yêu cầu tải public key từ URL bất kỳ rồi tin luôn.
- Có thể chọn khóa từ mọi issuer chung một “thùng khóa” mà không ràng buộc issuer và audience.
- JWKS công khai cho phép tùy ý thêm public key từ nguồn không được quản trị.

`kid`, `jku` hoặc các tham số chỉ tới khóa nếu được hỗ trợ đều là **input chưa đáng tin**. Khóa được sử dụng phải bị ràng buộc với cấu hình issuer, endpoint JWKS được kiểm soát và policy thuật toán.

### 3.3. Tránh algorithm confusion và `alg: none`

Các lỗi nguy hiểm có thể xuất hiện khi API:

- Chấp nhận `"alg": "none"` như một token đã xác thực trong khi endpoint bắt buộc signed token.
- Để token tự chọn thuật toán mà code không giới hạn thuật toán được phép.
- Dùng nhầm public key bất đối xứng như secret của MAC đối xứng.
- Bỏ qua kiểm tra chữ ký nếu một thư viện parse trả về Claims Set.
- Chấp nhận token ký bởi khóa đúng định dạng nhưng không thuộc nguồn tin cậy.

Những rủi ro này được gọi chung trong nhiều tài liệu là **JWT algorithm/key confusion**. Cách xử lý là dùng thư viện JOSE đáng tin cậy, chấp nhận **chính xác thuật toán/khóa/issuer được cấu hình**, không cho token tùy ý thay đổi điều kiện xác minh.

## 4. Chữ ký đúng là điều kiện cần, chưa phải điều kiện đủ

Sau khi xác minh chữ ký/MAC, Resource Server phải đánh giá **token có hợp lệ cho ngữ cảnh API này không**.

| Kiểm tra | Câu hỏi | Nếu bỏ qua |
| --- | --- | --- |
| **Issuer (`iss`)** | Token có được nhà phát hành mà API tin cậy cấp không? | API có thể nhận token từ nguồn khác |
| **Audience (`aud`)** | Token có được cấp cho chính API này không? | Token của API khác có thể bị dùng chéo |
| **Expiration (`exp`)** | Token còn hiệu lực tại thời điểm request không? | Token hết hạn vẫn có thể được sử dụng |
| **Not Before (`nbf`)** | Token đã đến thời điểm được sử dụng chưa? | Token chưa có hiệu lực bị chấp nhận |
| **Token type / profile** | Đây có đúng loại token mà API chấp nhận không? | Có thể nhầm ID token với access token |
| **Client / subject / context** | Claim về Client hoặc chủ thể có phù hợp loại grant/chính sách không? | Token dịch vụ bị hiểu nhầm là phiên người dùng |
| **Scope / authority** | Token được cấp phạm vi hành động cần thiết không? | Caller có thể truy cập endpoint vượt quyền |
| **Policy dữ liệu** | Caller có quyền đối với bản ghi/tenant/trạng thái này không? | Rò rỉ dữ liệu hoặc thao tác lên bản ghi không thuộc quyền |

### 4.1. Kiểm tra issuer

Ví dụ token có claim:

~~~json
{
  "iss": "https://id.dev.example.test/realms/shop"
}
~~~

Orders API production chỉ tin:

~~~text
https://login.example.com/realms/shop
~~~

Dù JWT ký hợp lệ bằng một khóa của hệ thống dev, **production phải từ chối** nếu issuer dev không được cấu hình là nguồn được phép. Việc dùng chung tên role/scope giữa các môi trường không tạo ra sự tin cậy.

### 4.2. Kiểm tra audience

Một Authorization Server có thể cấp token cho nhiều API khác nhau:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

Orders API yêu cầu `aud` chứa `orders-api`. Nếu chỉ kiểm tra issuer và chữ ký, token của Billing API có nguy cơ được chấp nhận nhầm ở Orders API. **Audience là ranh giới giữa các Resource Server**, không phải thông tin trang trí của payload.

### 4.3. Kiểm tra thời hạn

JWT thường dùng NumericDate (số giây kể từ Unix epoch) trong `exp`, `nbf` và `iat`. API không được chấp nhận token tại hoặc sau thời điểm hết hạn, có thể áp dụng dung sai lệch đồng hồ nhỏ theo chính sách.

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

Không dùng thời hạn token dạng mili-giây khi profile yêu cầu NumericDate. Kiểm tra `iat` chỉ có ý nghĩa khi policy xác định ràng buộc cần thiết, ví dụ không chấp nhận thời điểm phát hành quá xa trong tương lai.

### 4.4. Phân biệt ID token và access token

**OIDC ID token** chứng minh kết quả xác thực người dùng cho **OIDC Client**. **OAuth 2.0 access token** là credential gọi Resource Server. Cả hai có thể đều là JWT và được cùng issuer ký.

Ví dụ:

~~~text
ID token:      aud = shop-web
               dùng tại OIDC Client để xử lý đăng nhập

Access token:  aud = orders-api
               scope = orders.read
               dùng tại Orders API
~~~

Resource Server phải chấp nhận đúng **access token** theo profile/hợp đồng. Trong JWT profile cho OAuth 2.0 access token (RFC 9068), header `typ` có thể là `at+jwt`, và có những quy tắc xác minh cụ thể. Các nhà phát hành khác có thể dùng profile khác; API phải phối hợp với issuer để áp dụng đúng ràng buộc, tránh chấp nhận ID token chỉ vì chữ ký hợp lệ.

## 5. Thứ tự tin cậy trong Spring Security Resource Server

Với API sử dụng Bearer JWT, Spring Security cung cấp một luồng xử lý tiêu chuẩn:

~~~mermaid
flowchart TD
    HTTP["HTTP request<br/>Authorization: Bearer ..."]
    Extract["BearerTokenAuthenticationFilter<br/>trích token"]
    Provider["JwtAuthenticationProvider"]
    Decoder["JwtDecoder<br/>xác minh JWS và validate JWT"]
    Valid{"Token hợp lệ?"}
    Converter["JwtAuthenticationConverter<br/>tạo principal, authorities"]
    Authz["AuthorizationFilter / method security<br/>kiểm tra endpoint"]
    Domain["Service / policy<br/>kiểm tra bản ghi, tenant, owner"]
    Success["Trả dữ liệu"]
    Reject401["401 Unauthorized"]
    Reject403["403 / 404 theo chính sách"]

    HTTP --> Extract
    Extract --> Provider
    Provider --> Decoder
    Decoder --> Valid
    Valid -->|Không| Reject401
    Valid -->|Có| Converter
    Converter --> Authz
    Authz -->|Thiếu quyền| Reject403
    Authz -->|Đủ scope| Domain
    Domain -->|Không được phép| Reject403
    Domain -->|Được phép| Success
~~~

Đây là sơ đồ khái niệm. Việc chuyển lỗi thành status và thứ tự filter cụ thể phụ thuộc cấu hình. Điểm quan trọng là **claims chưa xác minh không được biến thành principal/authorities đáng tin**.

### 5.1. Những thành phần cần hiểu

| Thành phần | Trách nhiệm |
| --- | --- |
| `BearerTokenAuthenticationFilter` | Lấy Bearer token từ request theo cơ chế được cấu hình |
| `JwtAuthenticationProvider` | Yêu cầu `JwtDecoder` giải mã/xác minh token, sau đó chuyển kết quả thành authentication |
| `JwtDecoder` / `NimbusJwtDecoder` | Xử lý JWS và các validator đã cấu hình; chỉ trả về `Jwt` hợp lệ theo hợp đồng |
| `JwtAuthenticationConverter` | Từ `Jwt` đã được chấp nhận tạo `Authentication`, có thể ánh xạ `scope` thành `GrantedAuthority` |
| `SecurityFilterChain` / method security | Đối chiếu authorities và các quy tắc truy cập endpoint/phương thức |
| Lớp nghiệp vụ/policy | Kiểm tra quyền vào bản ghi, tenant, owner, trạng thái và các điều kiện chuyên biệt |

Trong thực tế, decoder có thể parse header và payload để thực hiện validation, nhưng **ứng dụng chỉ nên sử dụng đối tượng `Jwt` sau khi decoder đã hoàn tất xác minh**. Đừng tự parse claims từ Bearer token bên cạnh Spring Security rồi dùng chúng thay `Authentication` đáng tin.

### 5.2. Vì sao việc ánh xạ authorities phải xảy ra sau xác minh?

JWT có thể chứa:

~~~json
{
  "sub": "user-842",
  "scope": "orders.read orders.cancel",
  "roles": ["ORDER_SUPPORT"]
}
~~~

Nếu Resource Server đã xác minh token, `JwtAuthenticationConverter` có thể biến scope thành authority `SCOPE_orders.read` và `SCOPE_orders.cancel`. Nếu chưa xác minh, việc biến chuỗi `scope` thành authority sẽ cho người gửi **tự gắn quyền của họ**.

Spring Security mặc định thường ánh xạ scope từ claim `scope` hoặc `scp` phù hợp thành authorities tiền tố `SCOPE_`. Claim role tùy chỉnh như `roles` không tự động được hiểu giống nhau ở mọi issuer; muốn tạo `ROLE_ORDER_SUPPORT` phải thiết kế converter và hợp đồng claim tương ứng.

## 6. Cấu hình signed JWT trong Spring Boot

Ví dụ bên dưới dùng **Spring Boot 3 / Spring Security 6** với Orders API nhận JWT access token do Identity Server phát hành.

### 6.1. Thêm dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 6.2. Cấu hình issuer và JWKS đáng tin

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
~~~

Các biến ví dụ cho một môi trường:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

Các URI này chỉ để minh họa. Phải lấy **issuer và JWKS endpoint thực tế do Authorization Server công bố**; đường dẫn JWKS không cố định giữa các sản phẩm. Khi chỉ dùng `issuer-uri`, Spring Security có thể dùng discovery để xác định khóa. Khi cung cấp thêm `jwk-set-uri`, ứng dụng có thể không cần gọi metadata discovery lúc khởi động, nhưng vẫn phải kiểm tra claim `iss`.

Resource Server xác minh JWT ký bất đối xứng thường dùng **khóa công khai**, không cần client secret của Client đã xin token. Nếu hệ thống dùng opaque token và introspection, cơ chế xác minh khác; ví dụ trong bài tập trung vào **signed JWT**.

### 6.3. Tạo JwtDecoder có kiểm tra audience

Để minh họa chính xác ranh giới giữa **xác minh mật mã** và **kiểm tra hợp đồng claims**, có thể cấu hình `JwtDecoder` như sau:

~~~java
import org.springframework.beans.factory.annotation.Value;
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
public class JwtVerificationConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        // Dùng một JWKS endpoint đã được cấu hình là đáng tin.
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri)
                        .build();

        // Giữ kiểm tra tiêu chuẩn, gồm thời hạn và issuer.
        OAuth2TokenValidator<Jwt> standardValidators =
                JwtValidators.createDefaultWithIssuer(issuer);

        // Chữ ký hợp lệ vẫn không đủ nếu token dành cho API khác.
        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            boolean intendedForThisApi =
                    jwt.getAudience().contains(expectedAudience);

            if (intendedForThisApi) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Unexpected token audience",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standardValidators,
                        audienceValidator));

        return decoder;
    }
}
~~~

Trong ví dụ:

1. `NimbusJwtDecoder` lấy/cập nhật public JWK từ **JWKS URI đã cấu hình** và xác minh chữ ký phù hợp chính sách của decoder.
2. `JwtValidators.createDefaultWithIssuer(issuer)` áp dụng các kiểm tra JWT tiêu chuẩn, bao gồm các ràng buộc thời gian và issuer.
3. `audienceValidator` từ chối token không có audience `orders-api`.
4. Nếu chữ ký/validation thất bại, quá trình authentication thất bại; token không được chuyển thành principal đáng tin để tiếp tục phân quyền.

Ví dụ chọn builder mặc định cho thuật toán của decoder; trong hệ thống thực tế, hãy cấu hình **đúng tập thuật toán được issuer thỏa thuận** và các điều kiện token profile. Không nới rộng danh sách thuật toán chỉ để token lạ được chấp nhận. Nếu ứng dụng tạo bean `JwtDecoder` riêng, tránh vô tình ghi đè các validator mặc định bằng một validator chỉ kiểm tra audience.

### 6.4. Bảo vệ endpoint sau bước xác minh JWT

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ này giả định `/api/**` là REST API chỉ dùng Bearer token, không xác thực request bằng session cookie. Vì vậy ví dụ tắt CSRF và yêu cầu stateless ở filter chain API. Nếu ứng dụng cũng phục vụ browser dùng cookie, cần thiết kế riêng filter chain/session/CSRF phù hợp.

Khi nhận request `GET /api/orders/42`, Spring Security xác minh token trước; chỉ sau khi có authentication hợp lệ mới kiểm tra authority `SCOPE_orders.read`. Nếu token có `scope = "orders.write"` mà không có `orders.read`, request bị từ chối theo chính sách trên, dù token được ký hợp lệ.

## 7. Đọc claim từ Jwt đã được xác minh

Sau khi Spring Security tạo `Authentication` thành công, controller hoặc service mới nên sử dụng thông tin từ principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrdersController {

    private final OrderService orders;

    OrdersController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    OrderDto getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        // Service phải kiểm tra quyền trên đơn hàng cụ thể.
        return orders.findVisibleOrder(id, issuer, subject);
    }
}
~~~

`OrderService` và `OrderDto` là các kiểu minh họa thuộc nghiệp vụ, không phải class có sẵn của Spring Security. `findVisibleOrder` phải xác định tài nguyên thuộc chủ thể/tenant được phép và từ chối nếu không đáp ứng chính sách. Nếu API cho phép cả `client_credentials`, service cần phân biệt **service principal** với **người dùng cuối**; không mặc định mọi `sub` đều là ID người mua hàng.

**Một lỗi tinh vi cần tránh:** Controller đã có `@AuthenticationPrincipal Jwt` nhưng lại nhận một tham số `userId` do Client truyền và dùng `userId` ấy để bỏ qua so khớp chủ thể. Dữ liệu Client cung cấp có thể phục vụ xác định *đối tượng muốn truy cập*, nhưng quyền trên đối tượng đó phải được quyết định bằng **claim đáng tin và dữ liệu server**.

### Sử dụng method security khi phù hợp

Nếu bật `@EnableMethodSecurity`, có thể yêu cầu scope ở tầng service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(String id) {
        // Tải bản ghi và kiểm tra owner/tenant trong nghiệp vụ.
        throw new UnsupportedOperationException("Example only");
    }
}
~~~

Code này minh họa **điểm gắn quyền**, không phải triển khai service hoàn chỉnh; phần ownership và data policy vẫn phải được hiện thực. Method security không thay thế xác minh JWT ở `JwtDecoder`.

## 8. Tình huống: JWT hợp lệ nhưng vẫn phải từ chối

### 8.1. Token đúng chữ ký nhưng sai audience

JWT được Authorization Server tin cậy ký:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Orders API yêu cầu audience `orders-api`. Dù chữ ký đúng, API phải từ chối **ở giai đoạn validate token**. Đây là một lý do phổ biến dẫn đến 401 khi Client gửi token cấp cho API khác.

### 8.2. Token đúng chữ ký nhưng hết hạn

JWT có `exp` nhỏ hơn thời gian hiện tại (sau khi xét clock skew được chấp nhận). API phải từ chối vì thời hạn token đã kết thúc. Không dùng việc `sub` hoặc `scope` “vẫn giống trước” để bỏ qua `exp`.

### 8.3. Token đúng issuer/audience nhưng thiếu scope

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Khi gọi `POST /api/orders`, API đòi `SCOPE_orders.write`. Sau khi JWT đã xác minh thành công, yêu cầu vẫn phải bị từ chối với **403 Forbidden** vì thiếu quyền ghi.

### 8.4. Token đủ scope nhưng thiếu quyền đối tượng

`user-842` có token hợp lệ mang `orders.read`, nhưng đơn 42 thuộc `user-999` hoặc tenant khác. Endpoint phải từ chối theo chính sách, có thể là **403** hoặc **404** để tránh tiết lộ sự tồn tại tài nguyên. Không coi scope là giấy phép truy cập mọi bản ghi.

### 8.5. Token OIDC ID token bị gửi nhầm đến API

Client đăng nhập nhận ID token với audience `shop-web`. Nếu gửi token ấy tới Orders API, Resource Server phải từ chối theo audience/token profile mặc dù chữ ký thuộc cùng issuer. ID token mô tả kết quả xác thực người dùng cho Client; access token phục vụ gọi API.

## 9. Điều gì thay đổi khi access token là opaque?

Không phải mọi OAuth 2.0 access token đều là JWT. Nếu Authorization Server cấp **opaque token**, Resource Server thường gọi **token introspection endpoint** để hỏi trạng thái và thuộc tính token.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Resource Server
    participant AS as Authorization Server

    C->>API: Bearer opaque-token
    API->>AS: Introspection với credential phù hợp
    AS-->>API: active + thuộc tính token
    API->>API: Kiểm tra active, audience, scope, chủ thể, policy
    API-->>C: Tài nguyên hoặc từ chối
~~~

Trong cơ chế này, API **không xác minh JWS chữ ký cục bộ** vì token không có dạng JWS để xử lý. Thay vào đó, API tin vào phản hồi introspection từ Authorization Server sau khi thiết lập kênh liên lạc và xác thực endpoint đúng cách. Nguyên tắc không đổi: **không được sử dụng thông tin token chưa được xác minh/tin cậy để cấp quyền**.

Spring Security hỗ trợ cơ chế opaque token bằng `oauth2ResourceServer().opaqueToken(...)` và cấu hình introspection URI/credentials. Chọn JWT validation hoặc opaque introspection theo hợp đồng token thực tế; không “decode base64” một opaque token rồi suy diễn quyền.

## 10. Vận hành khóa và JWKS an toàn

### 10.1. Quay vòng khóa

Authorization Server có thể thêm khóa mới vào JWKS, bắt đầu ký JWT bằng khóa mới, rồi rút khóa cũ sau khi các token còn hiệu lực sử dụng khóa cũ đã hết hạn theo kế hoạch. Resource Server cần hỗ trợ **lấy/cập nhật JWKS** và xác minh nhiều `kid` hợp lệ trong giai đoạn chuyển đổi.

Không nên:

- Gắn cứng một public key vào code rồi không hỗ trợ thay đổi khi issuer quay vòng khóa.
- Tắt xác minh chữ ký tạm thời nếu token mới có `kid` chưa được nhận diện.
- Chấp nhận mọi JWKS từ một địa chỉ do request chỉ định để “tránh lỗi”.

Nếu Resource Server không tìm thấy khóa phù hợp, cần kiểm tra metadata/JWKS và cơ chế cache/rotation. Một `kid` lạ không phải lý do để mặc định chấp nhận token.

### 10.2. Phân chia issuer và môi trường

Dev, staging và production thường có issuer, JWKS và audience riêng. Nếu Resource Server production vô tình sử dụng public key hoặc issuer dev, token có thể bị từ chối đúng cách hoặc tạo rủi ro tin cậy chéo nếu các chính sách khác không chặt.

Các giá trị liên quan nên đến từ cấu hình môi trường:

~~~text
OAUTH_ISSUER_URI=https://login.example.com/realms/shop
OAUTH_JWKS_URI=https://login.example.com/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

Không tự động tin nhiều issuer chỉ vì cùng một tổ chức quản lý chúng. Mỗi issuer cần có chính sách khóa, audience và claim mapping tương ứng.

### 10.3. Chữ ký không giúp thu hồi JWT ngay lập tức

Một JWT có chữ ký đúng và chưa hết hạn có thể tiếp tục được chấp nhận khi kiểm tra cục bộ, ngay cả khi phiên web đã đăng xuất hoặc quyền người dùng thay đổi, trừ khi hệ thống áp dụng cơ chế thu hồi/kiểm tra trạng thái bổ sung.

Đối với quyền nhạy cảm, có thể cân nhắc token sống ngắn, introspection, tra cứu trạng thái chủ thể/permission hiện tại hoặc cơ chế revocation theo kiến trúc. Xác minh chữ ký bảo đảm nguồn/tính toàn vẹn của token, **không bảo đảm dữ liệu quyền trong token luôn là trạng thái mới nhất**.

## 11. Xử lý lỗi và quan sát trong hệ thống thật

Nếu xác minh JWT hoặc authorization thất bại, Spring Security có các kết quả thường gặp:

| Giai đoạn | Ví dụ lỗi | Phản hồi điển hình |
| --- | --- | --- |
| Trích token | Thiếu Bearer token cho endpoint yêu cầu xác thực | **401 Unauthorized** |
| Xác minh JWS | Chữ ký sai, thuật toán không được chấp nhận, không tìm được khóa tin cậy | **401 Unauthorized** |
| Validate JWT | Issuer, audience hoặc thời hạn không hợp lệ | **401 Unauthorized** |
| Kiểm tra authority | Token hợp lệ nhưng thiếu `SCOPE_orders.write` | **403 Forbidden** |
| Kiểm tra dữ liệu | Có scope nhưng không có quyền trên đơn hàng cụ thể | **403** hoặc **404** theo policy |

Các mã status là quy tắc điển hình của Bearer authentication; kết quả cụ thể còn phụ thuộc cấu hình entry point/access denied handler. Với Bearer token, header `WWW-Authenticate` có thể chứa thông tin theo RFC 6750, chẳng hạn `invalid_token` hoặc `insufficient_scope` khi phù hợp.

Để điều tra sự cố, có thể ghi **request ID, endpoint, issuer đã được xác minh, loại lỗi, tên audience mong đợi và kết quả policy** theo quy tắc quản trị log. Tránh ghi **nguyên access token**, refresh token, client secret, private key hoặc dữ liệu nhạy cảm từ claims.

### Một checklist vận hành dễ áp dụng

1. Đúng issuer/JWKS/audience theo môi trường?
2. Token là OAuth 2.0 access token, đúng token profile mà API chấp nhận?
3. Algorithm và khóa ký nằm trong tập tin cậy?
4. `exp`/`nbf` còn hiệu lực, clock của máy chủ được đồng bộ?
5. Claim scope/roles có được ánh xạ thành authority đúng tên?
6. Endpoint và tầng nghiệp vụ đã kiểm tra permission, owner và tenant?
7. Lỗi được ghi đủ thông tin chẩn đoán mà không rò rỉ credential?

## 12. Những hiểu nhầm phổ biến

**“JWT có ba phần, decode ra JSON là an toàn.”** Không. Dạng ba phần chỉ là đặc trưng của JWS compact thông dụng. Không có xác minh mật mã thì dữ liệu vẫn do người gửi tự khai.

**“JWT được ký thì mọi claim đều đúng mãi mãi.”** Chữ ký chỉ bảo đảm nội dung đã ký không bị sửa so với khóa được chấp nhận. Token còn phải có issuer, audience, thời hạn và mục đích đúng; dữ liệu về quyền có thể thay đổi sau lúc cấp token.

**“Có `scope = admin` thì API phải cho phép.”** Không. Scope/role phải được phát bởi issuer tin cậy, có ý nghĩa đã thỏa thuận và được API kiểm tra theo chính sách. Tên chuỗi `admin` không có quyền phổ quát.

**“Chữ ký đúng thì token của API nào cũng dùng được.”** Không. Một token có `aud = payments-api` không được tự động chấp nhận tại `orders-api`.

**“Muốn verify JWT thì phải biết private key của Authorization Server.”** Với JWS ký bất đối xứng, Resource Server xác minh bằng **public key**. Private signing key phải được giữ bí mật tại bên ký.

**“`kid` xuất hiện trong token là bằng chứng khóa đáng tin.”** Không. `kid` là gợi ý chọn khóa từ tập tin cậy; khóa vẫn phải gắn với issuer và signature phải được xác minh.

**“JWT và JWE luôn là một.”** Không. JWT là cấu trúc biểu diễn claims; JWS bảo vệ tính toàn vẹn bằng chữ ký/MAC, JWE mã hóa để bảo vệ bí mật. Cấu hình Resource Server nhận signed JWT không mặc nhiên hỗ trợ mọi JWE.

**“Lấy `sub` từ JWT là đủ để cho phép đọc đơn hàng.”** Không. `sub` cho biết chủ thể theo hợp đồng token, không tự chứng minh quyền đối với từng đơn, tenant hay hoạt động.

**“Đăng nhập OIDC thành công là có quyền gọi mọi API.”** Không. ID token phục vụ OIDC Client; Resource Server cần access token hợp lệ, đúng audience, scope và chính sách dữ liệu.

## 13. Tự kiểm tra bằng các tình huống

**Câu 1:** Ứng dụng nhận JWT có payload `{"sub":"u1","scope":"orders.admin"}`. Developer chỉ dùng `Base64.getUrlDecoder()` rồi cấp quyền admin. Sai ở đâu?

**Giải thích:** Claims chưa được xác minh nguồn và tính toàn vẹn. Developer đã biến dữ liệu do caller kiểm soát thành authority. Cần dùng `JwtDecoder` xác minh JWS và token contract trước khi ánh xạ quyền.

**Câu 2:** JWT có chữ ký đúng bằng khóa của Authorization Server, nhưng `aud = reports-api`. Orders API có nhận token không?

**Giải thích:** Không, nếu hợp đồng yêu cầu `aud = orders-api`. Chữ ký hợp lệ không sửa được audience sai.

**Câu 3:** JWT đã xác minh có `scope = orders.read`, người dùng muốn đọc đơn của tài khoản khác. Có cho phép không?

**Giải thích:** Chỉ khi policy dữ liệu cho phép. Scope là quyền loại thao tác; ownership/tenant phải được kiểm tra riêng.

**Câu 4:** Authorization Server đổi `kid` sau khi quay vòng khóa; API không tìm thấy JWK mới và trả 401. Có nên bỏ kiểm tra chữ ký để giữ dịch vụ chạy không?

**Giải thích:** Không. Cần giải quyết nguồn JWKS, cơ chế refresh/cache và quy trình quay vòng của issuer, giữ nguyên nguyên tắc verify.

**Câu 5:** Access token dùng dạng opaque, không có ba phần ngăn bằng dấu chấm. API có thể kiểm tra kiểu JWT không?

**Giải thích:** Không nếu token không phải JWT. Cần introspection hoặc cơ chế xác minh phù hợp loại token, rồi mới tin thuộc tính token để phân quyền.

---

## Kết luận

Khi xây dựng Spring Security OAuth 2.0 Resource Server, **đừng bắt đầu bằng `sub`, `scope` hay `roles` trong chuỗi JWT nhận từ Client**. Hãy bắt đầu từ câu hỏi: *“Tôi có thể xác minh token này do issuer tin cậy phát hành, dành cho API của tôi, còn hiệu lực và đúng mục đích không?”*.

Chỉ sau khi `JwtDecoder` xác minh **chữ ký, khóa, thuật toán và token claims bắt buộc**, Resource Server mới được sử dụng kết quả để tạo `Authentication`, ánh xạ `GrantedAuthority` và thực thi các quy tắc truy cập endpoint. Quyết định cuối cùng vẫn cần kiểm tra **quyền trên dữ liệu thực tế**. Đây là ranh giới căn bản ngăn việc một chuỗi JSON do bên gọi kiểm soát biến thành quyền truy cập trong ứng dụng.
