# Kiểm tra audience, issuer hoặc loại token khi metadata có yêu cầu tương ứng

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, việc một **opaque access token** được Authorization Server (AS) xác nhận còn hoạt động chưa đủ để API quyết định cho phép truy cập. Introspection endpoint có thể trả `active: true` kèm những metadata như `aud`, `iss`, `token_type` hoặc trường tùy chỉnh xác định **mục đích sử dụng token**. Resource Server cần biết **metadata nào là bắt buộc**, **metadata nào có thể vắng mặt** và **phải đối chiếu nó với hợp đồng nào**.

Giả sử Orders API và Billing API cùng sử dụng Identity Server. Một token được cấp cho Billing API vẫn có thể ở trạng thái active. Nếu Orders API chỉ thấy `active: true` và một scope trùng tên rồi chấp nhận token, hệ thống có nguy cơ **token substitution**: credential hợp lệ ở một Resource Server bị sử dụng sai tại Resource Server khác. Tương tự, một hệ thống có nhiều realm/issuer có thể trả token active từ môi trường hoặc tổ chức không được Orders API tin cậy.

> **Nguyên tắc:** Introspection đáng tin là nền tảng xác thực, nhưng **active không đồng nghĩa đúng audience, đúng issuer, đúng loại token hoặc đủ quyền**. Những thuộc tính này phải được kiểm tra **khi metadata và hợp đồng yêu cầu**, hoặc phải có **bảo đảm tương đương từ endpoint/AS được tin cậy**. Nếu thiếu bằng chứng cần thiết, Resource Server phải từ chối thay vì tự gán giá trị cho token.

## 1. Bối cảnh: opaque token đi qua Resource Server như thế nào?

Giả sử hệ thống gồm:

- **Identity Server**: Authorization Server phát hành opaque access token và cung cấp introspection endpoint.
- **Shop Web**: OAuth2/OIDC Client xin access token rồi gửi đến API.
- **Orders API**: Spring Security Resource Server bảo vệ đơn hàng; audience logic `orders-api`.
- **Billing API**: Resource Server khác; audience logic `billing-api`.

Client gọi:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer 8xqP2...opaque-access-token...
~~~

Orders API gọi introspection:

~~~http
POST /introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <credential-cua-orders-api>
Content-Type: application/x-www-form-urlencoded

token=8xqP2...opaque-access-token...&token_type_hint=access_token
~~~

Phản hồi minh họa:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"],
  "token_type": "Bearer",
  "token_usage": "access_token",
  "sub": "user-842",
  "client_id": "shop-web",
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

**`token_usage` trong ví dụ là metadata tùy chỉnh theo hợp đồng của Identity Server**, không phải claim bắt buộc của RFC 7662. Mặt khác, `token_type: "Bearer"` là thông tin về **kiểu sử dụng credential**, không tự chứng minh token này là một OAuth access token thay vì ID token.

Luồng xử lý mong muốn:

~~~mermaid
flowchart TD
    A["Nhận Bearer opaque token"]
    B["OpaqueTokenIntrospector gọi AS đã tin cậy"]
    C{"active là true?"}
    X["Từ chối token / authentication"]
    D["Kiểm tra hợp đồng metadata"]
    E{"audience/resource phù hợp?"}
    F{"issuer được tin cậy?"}
    G{"token purpose đúng?"}
    H["Tạo OAuth2AuthenticatedPrincipal"]
    I["Ánh xạ scope/roles/permissions"]
    J["HTTP và method authorization"]
    K["Owner, tenant, trạng thái dữ liệu"]
    L["Thực hiện request được bảo vệ"]

    A --> B --> C
    C -->|Không| X
    C -->|Có| D --> E
    E -->|Không| X
    E -->|Có| F
    F -->|Không| X
    F -->|Có| G
    G -->|Không| X
    G -->|Có| H --> I --> J --> K --> L
~~~

Sơ đồ là **một chính sách minh họa**, không khẳng định mọi AS đều trả tất cả trường. Nếu AS không trả một metadata, API cần xác định **điều kiện tương đương nào được chứng minh bởi endpoint/credential/profile** trước khi quyết định bỏ kiểm tra trực tiếp.

## 2. Phân biệt `active` với các điều kiện chấp nhận token

Trong **OAuth 2.0 Token Introspection (RFC 7662)**, `active` là thuộc tính trọng tâm phản ánh token có còn được AS công nhận theo chính sách của nó hay không.

Token inactive:

~~~json
{
  "active": false
}
~~~

Token active không nhất thiết được cấp cho Orders API:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

Hai câu hỏi khác nhau:

1. **Token còn hiệu lực trong hệ thống của AS không?**
2. **Token có được phép dùng để gọi API này và thực hiện thao tác này không?**

| Tình huống | Nhận định đúng |
| --- | --- |
| `active: false` | Không tạo authentication thành công |
| `active: true`, đúng `aud`, `iss` và purpose | Có thể tiếp tục xét scope và quyền |
| `active: true`, audience của Billing API | Từ chối nếu Orders API yêu cầu `orders-api` |
| `active: true`, issuer ngoài danh sách được tin | Từ chối khi issuer là ràng buộc bắt buộc |
| `active: true` nhưng token purpose là ID token | Từ chối nếu API chỉ nhận OAuth access token |
| `active: true`, thiếu audience bắt buộc | Từ chối, trừ khi có resource binding đáng tin thay thế |
| `active: true`, đúng scope nhưng sai tenant | Từ chối tại chính sách quyền trên dữ liệu |

Thành công của introspection là **điều kiện để tin metadata**, không có nghĩa mọi API đều được chấp nhận token ấy. Nhiều Authorization Server đã giới hạn token được introspect theo quyền của Client Resource Server; nếu dựa vào bảo đảm này, cần có hợp đồng và test rõ ràng.

## 3. Những metadata nào có trong RFC 7662?

RFC 7662 mô tả request `POST` với tham số `token` và tùy chọn `token_type_hint`, cùng phản hồi JSON chứa `active` và các metadata có thể xuất hiện.

| Thuộc tính | Ý nghĩa phổ biến | Cách sử dụng an toàn |
| --- | --- | --- |
| **`active`** | Token có hoạt động không? | Phải có kết quả đáng tin trước khi xác thực |
| **`scope`** | Danh sách OAuth2 scopes của token | Dùng để cấp `SCOPE_...` theo hợp đồng |
| **`client_id`** | OAuth2 Client được cấp token | Không phải Client ID của Resource Server dùng gọi introspection |
| **`username`** | Tên người dùng | Không mặc nhiên là khóa danh tính ổn định |
| **`token_type`** | Token type, phổ biến là `Bearer` | Không đồng nghĩa token purpose là `access_token` |
| **`exp`** | Thời điểm hết hạn | Giới hạn cache và kiểm tra chính sách thời gian khi cần |
| **`iat`** | Thời điểm phát hành | Dùng theo profile nếu cần |
| **`nbf`** | Token chưa dùng trước thời điểm này | Có thể kiểm tra bổ sung theo policy |
| **`sub`** | Chủ thể token đề cập | Có thể là user hoặc service tùy grant |
| **`aud`** | Audience/resource của token | Kiểm tra nếu contract yêu cầu hoặc có resource binding tương đương |
| **`iss`** | Issuer của token | Kiểm tra theo contract hoặc ràng buộc từ AS endpoint |
| **`jti`** | Token identifier | Không tự tạo ra quyền hay tính hợp lệ |
| **`token_usage`**, **`token_use`** | Custom token-purpose metadata | Chỉ có nghĩa khi AS định nghĩa schema và tập giá trị |

**Không phải mọi response đều chứa `aud`, `iss`, `token_type` hoặc custom token usage.** Nếu chúng là bắt buộc với Orders API, hai bên phải thống nhất và kiểm thử. Không nên ép một field không tồn tại rồi kết luận mọi opaque token đều sai; cũng không nên bỏ yêu cầu bảo mật chỉ vì AS không trả field đó.

### 3.1. Nguồn tin cậy của metadata

~~~text
Bearer token của caller
  -> credential chưa xác thực

Introspection response từ AS
  -> chỉ tin sau khi kết nối đúng endpoint,
     xác thực Resource Server với AS và xử lý active

Policy của Orders API
  -> kiểm tra audience/issuer/purpose
     rồi mới quyết định quyền
~~~

Không được dùng header tùy ý như:

~~~http
X-Token-Audience: orders-api
X-Token-Issuer: https://identity.example.test/realms/shop
X-Token-Usage: access_token
~~~

để thay thế metadata từ AS. Caller hoàn toàn có thể tự điền những giá trị ấy.

## 4. Audience: token được cấp cho Resource Server nào?

Audience là một ranh giới quan trọng giữa các API dùng chung một Authorization Server.

Token hợp lệ về audience cho Orders API:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
~~~

Token của API khác:

~~~json
{
  "active": true,
  "aud": ["billing-api"],
  "scope": "orders.read",
  "sub": "user-842"
}
~~~

Trường hợp sau phải **bị từ chối theo audience**, dù nó active và có cùng chuỗi scope.

### 4.1. Audience có thể là chuỗi hoặc danh sách

Tùy AS/serialization, introspection response có thể trả:

~~~json
{"aud": "orders-api"}
~~~

hoặc:

~~~json
{"aud": ["orders-api", "reports-api"]}
~~~

Một policy thường gặp là kiểm tra **tập audience chứa expected audience**. Nhưng không phải mọi API đều muốn chấp nhận multi-audience token; có thể yêu cầu chỉ một audience hoặc kiểm tra resource indicator bổ sung. Cần ghi rõ chính sách thay vì mặc định accept mọi tập có tên API.

### 4.2. Định danh audience không nhất thiết bằng URL API

~~~text
orders-api
https://api.example.test/orders
urn:example:resource:orders
~~~

Đây là ba kiểu định danh có thể được dùng trong những hệ thống khác nhau. Không tự suy diễn rằng `aud` luôn là hostname, OAuth2 Client ID hay key dưới `resource_access`. Giá trị phải được thỏa thuận giữa AS và Resource Server.

### 4.3. Nếu response thiếu `aud`

Phân biệt rõ:

1. **Hợp đồng bắt buộc trả `aud`:** thiếu là invalid metadata → từ chối.
2. **AS bảo đảm resource binding qua endpoint/credential:** ví dụ Resource Server `orders-api` chỉ được introspect token dành cho nó, token của Billing API sẽ trả inactive. API có thể dựa trên bảo đảm đó nếu **được tài liệu hóa và kiểm thử**.
3. **Không có field và không có resource binding được chứng minh:** không có cơ sở để biết token dành cho API nào. Phải bổ sung metadata hoặc cơ chế ràng buộc; không chấp nhận mọi token active.

Chỉ có introspection Client ID tên “orders-api” **không tự chứng minh** rằng AS đã giới hạn token theo audience. Đây phải là một chính sách thực tế của AS.

## 5. Issuer: giới hạn nhà phát hành được tin cậy

Issuer xác định nguồn cấp token khi AS đưa thuộc tính `iss` trong response. Orders API production có thể chỉ tin:

~~~text
https://identity.example.test/realms/shop
~~~

Một phản hồi phù hợp:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"]
}
~~~

Một phản hồi khác nguồn:

~~~json
{
  "active": true,
  "iss": "https://id.dev.example.test/realms/shop",
  "aud": ["orders-api"]
}
~~~

Nếu hợp đồng yêu cầu issuer production, phản hồi thứ hai phải bị từ chối. Scope hoặc tên role giống nhau ở dev và production **không làm hai issuer trở thành một**.

### 5.1. Tin endpoint introspection và kiểm tra `iss` khác nhau

Với opaque token, Resource Server chủ yếu dựa trên **phản hồi từ introspection endpoint đáng tin** thay vì tự xác minh JWS bằng public key. Có hai lớp ràng buộc:

| Lớp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Endpoint trust | AS nào được Resource Server liên lạc qua HTTPS và credential đúng | `https://identity.example.test/introspect` |
| Metadata issuer | Token được AS báo là do issuer nào phát hành | `https://identity.example.test/realms/shop` |

Nếu endpoint **chỉ introspect token do một issuer duy nhất phát**, endpoint trust có thể thay thế việc kiểm tra claim `iss` khi AS không trả claim đó và hợp đồng cho phép. Nếu một gateway introspection xử lý token của **nhiều realm/issuer**, `iss` hoặc cơ chế định tuyến/ràng buộc riêng lại trở nên quan trọng.

**Không tự điền giá trị expected issuer vào response khi trường vắng** rồi tuyên bố đã xác minh issuer. Đó chỉ là gán một chuỗi do API đặt, không phải bằng chứng token thuộc issuer ấy.

### 5.2. So khớp issuer theo giá trị định danh chính thức

~~~text
https://identity.example.test/realms/shop
https://identity.example.test/realms/shop/
~~~

Hai giá trị có thể khác nhau theo hợp đồng issuer. Không tự bỏ path, hạ cấp `https` thành `http`, xóa slash hoặc chỉ so sánh hostname nếu không có quy tắc chuẩn hóa được nhà phát hành thỏa thuận.

Với multi-issuer API, mỗi issuer cần có **credential/endpoint hoặc claim mapping, audience và role semantics** phù hợp. Không gộp quyền của các issuer chỉ vì cùng role `admin`.

## 6. Token type khác token purpose

Một nhầm lẫn đặc biệt nguy hiểm là coi:

~~~json
{"token_type": "Bearer"}
~~~

đồng nghĩa:

~~~text
Token này chắc chắn là OAuth 2.0 access token.
~~~

Trong OAuth 2.0:

- **Access token** là credential mà Client dùng truy cập Resource Server.
- **Bearer** là cách sử dụng token: bên giữ credential có thể trình nó mà không cần proof-of-possession trong mô hình Bearer.
- **OIDC ID token** phục vụ OIDC Client xác nhận kết quả đăng nhập, không phải access token cho API.

Vì vậy **`token_type: "Bearer"` không tự chứng minh token purpose là `access_token`**. Tương tự, request introspection có `token_type_hint=access_token` chỉ là một **gợi ý**, không phải kết quả xác minh token kind.

### 6.1. Một contract custom có thể định nghĩa `token_usage`

Giả sử AS được cấu hình trả:

~~~json
{
  "active": true,
  "token_type": "Bearer",
  "token_usage": "access_token",
  "aud": ["orders-api"],
  "iss": "https://identity.example.test/realms/shop"
}
~~~

Khi đó Orders API có thể kiểm tra **custom field `token_usage` bằng `access_token`**. Nhưng field này là một phần hợp đồng tùy chỉnh, **không bắt buộc theo RFC 7662**. Nhà phát hành khác có thể dùng `token_use: "access"`, một loại `purpose`, hoặc hoàn toàn không trả field mà **endpoint introspection chỉ cho phép access token**.

Không viết:

~~~java
// SAI về ngữ nghĩa RFC 7662:
"access_token".equals(principal.getAttribute("token_type"))
~~~

Nếu AS trả `token_type = Bearer`, đoạn code trên sẽ từ chối token hợp lệ mà không kiểm tra đúng mục đích token.

### 6.2. Không suy ra loại token từ hình dạng

Những suy luận sau không an toàn:

~~~text
Có 3 phần phân tách bằng dấu chấm -> chắc chắn là access token.
Không có dấu chấm -> chắc chắn là opaque token với mục đích access.
Header Authorization là Bearer -> chắc chắn đúng loại token.
AS trả active = true -> token chắc chắn dùng được cho mọi API.
~~~

OAuth access token có thể là JWT hoặc opaque; ID token thường là JWT nhưng **không được sử dụng thay access token**. Resource Server phải dựa trên profile/metadata của AS và audience riêng.

### 6.3. Khi không có field token-purpose

Nếu AS không trả `token_usage`, cần hỏi:

- Endpoint introspection có **chỉ công nhận OAuth access token** không?
- Có khi nào ID token hoặc refresh token cũng được trả active không?
- Credential introspection của Orders API có chỉ được dùng kiểm tra access token cho resource này không?
- Có metadata khác xác định purpose hoặc resource binding không?

Chỉ khi có một bảo đảm đáng tin, API mới có thể bỏ kiểm tra custom field này. Đừng tự đặt “default = access_token” khi field vắng.

## 7. Một hợp đồng metadata tốt phải phân biệt bắt buộc và tùy chọn

Ví dụ chính sách của Orders API:

| Metadata | Chính sách minh họa | Nếu thiếu |
| --- | --- | --- |
| `active` | Bắt buộc true | Không xác thực |
| `aud` | Bắt buộc chứa `orders-api` | Từ chối nếu chưa có resource binding đáng tin thay thế |
| `iss` | Bắt buộc bằng issuer shop production | Từ chối nếu chưa có ràng buộc issuer tương đương |
| `token_usage` | Bắt buộc `access_token` với custom profile này | Từ chối nếu profile cam kết cung cấp |
| `token_type` | Nếu AS trả thì phải bằng `Bearer` | Nếu AS không cam kết trả, thiếu chưa tự chứng minh token sai |
| `scope` | Cần `orders.read` khi gọi GET | Có thể xác thực nhưng thiếu quyền → 403 |
| `sub` | Bắt buộc cho endpoint user theo profile | Từ chối hoặc sử dụng service policy riêng |
| `client_id` | Chỉ chấp nhận Client theo quy tắc endpoint khi cần | Xử lý theo client contract |
| `tenant_id` | Bắt buộc cho một số API đa tenant | Từ chối hoặc tra cứu tenant từ nguồn tin cậy |
| `exp` | Giới hạn thời gian/cache theo profile | Không cache vô hạn khi không biết thời hạn |

### 7.1. Ba cấp độ bảo đảm

1. **Required metadata**: AS cam kết trả trường đó; thiếu, sai kiểu hoặc sai giá trị → reject.
2. **Optional but checked if present**: field có thể vắng; khi xuất hiện phải đúng. Chỉ an toàn nếu điều kiện đó không cần thiết hoặc được bảo đảm ở nơi khác.
3. **Bound by AS endpoint/registration**: metadata không trả trong body, nhưng chính endpoint, credential hoặc registration bảo đảm cùng điều kiện. Đây phải là **một ràng buộc được kiểm chứng**, không phải suy đoán.

Đừng biến một field bắt buộc thành optional chỉ để mọi request thành công sau khi triển khai. Việc thay đổi policy phải được đánh giá như **một thay đổi bảo mật**.

### 7.2. Ví dụ phản hồi không đủ dữ liệu

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "shop-web"
}
~~~

Không thể kết luận issuer, audience hay token purpose **chỉ từ JSON này**. Nếu AS endpoint có hợp đồng bảo đảm đủ cả ba, có thể đưa chúng vào các ràng buộc server-side; nếu không, Resource Server cần thêm chứng cứ thay vì chấp nhận token dựa trên scope.

## 8. Spring Security xử lý opaque token và metadata ở đâu?

Luồng chung trong Spring Security 6:

~~~text
HTTP Authorization: Bearer <opaque-token>
     |
BearerTokenAuthenticationFilter
     |
OpaqueTokenAuthenticationProvider
     |
OpaqueTokenIntrospector
     |-> POST tới AS bằng credential của Resource Server
     |-> Kiểm tra trạng thái active và parse metadata
     |
Custom OpaqueTokenIntrospector wrapper
     |-> Kiểm tra issuer / audience / token purpose
     |-> Throw nếu sai contract
     |
OAuth2AuthenticatedPrincipal
     |
BearerTokenAuthentication, authorities
     |
authorizeHttpRequests / @PreAuthorize
     |
Business policy: owner, tenant, trạng thái
~~~

Các thành phần cần hiểu:

| Thành phần | Trách nhiệm |
| --- | --- |
| `OpaqueTokenIntrospector` | Interface xác minh một opaque token qua introspection |
| `NimbusOpaqueTokenIntrospector` hoặc implementation tương đương | Gửi yêu cầu HTTP và diễn giải phản hồi theo framework |
| `OAuth2AuthenticatedPrincipal` | Principal cùng attributes/authorities được introspector trả |
| `BadOpaqueTokenException` | Từ chối token không được chấp nhận theo quy tắc |
| `BearerTokenAuthentication` | Authentication của request Bearer đã xác thực |
| `SecurityFilterChain` | Đối chiếu HTTP method, URL và authority |
| Method security/service | Kiểm tra quyền trên resource thực tế |

**Vị trí hợp lý của kiểm tra metadata chung là trong `OpaqueTokenIntrospector` hoặc một lớp authentication policy tập trung.** Nếu chỉ kiểm tra audience ở controller A nhưng quên controller B, cùng một token có thể bị xử lý không nhất quán.

## 9. Cấu hình Spring Boot Resource Server

Ví dụ dưới đây dùng **Spring Boot 3 / Spring Security 6**, API dùng opaque access token.

### 9.1. Dependency

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 9.2. Cấu hình introspection và expected metadata

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}

app:
  security:
    expected-issuer: ${OAUTH_EXPECTED_ISSUER}
    expected-audience: ${OAUTH_EXPECTED_AUDIENCE}
    expected-token-usage: access_token
~~~

Ví dụ environment:

~~~text
OAUTH_INTROSPECTION_URI=https://identity.example.test/realms/shop/protocol/openid-connect/token/introspect
OAUTH_INTROSPECTION_CLIENT_ID=orders-api-introspection
OAUTH_INTROSPECTION_CLIENT_SECRET=<secret-duoc-cap-boi-secret-manager>
OAUTH_EXPECTED_ISSUER=https://identity.example.test/realms/shop
OAUTH_EXPECTED_AUDIENCE=orders-api
~~~

URI chỉ minh họa; endpoint thực tế và cách Resource Server xác thực với AS do nhà phát hành quy định. Secret phải được cấp qua hệ thống quản lý bí mật, **không commit vào repository, log hoặc file cấu hình công khai**.

### 9.3. Bảo vệ HTTP endpoint

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
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Ví dụ giả định `/api/**` là REST API chỉ nhận Bearer token, không dùng session cookie. Vì vậy chỉ trong chain này CSRF được tắt và session là stateless. Nếu còn endpoint ngoài `/api/**`, cần một SecurityFilterChain khác hoặc chính sách fallback phù hợp để không vô tình bỏ sót.

## 10. Tạo `OpaqueTokenIntrospector` kiểm tra metadata theo hợp đồng

Thiết kế một **decorator**:

1. Delegate introspector gửi token đến endpoint AS đáng tin và đánh giá `active`.
2. Wrapper đọc **chính metadata đã introspect** và kiểm tra `iss`, `aud` cùng custom `token_usage`.
3. Nếu thiếu/sai trường bắt buộc, wrapper phát sinh lỗi.
4. Chỉ khi hợp lệ mới trả nguyên `OAuth2AuthenticatedPrincipal` để Spring Security áp dụng scope và policy.

Trong ví dụ này, **hợp đồng bắt buộc cả `iss`, `aud` và `token_usage`**. Không hiểu đây là điều kiện bắt buộc của mọi RFC 7662 response.

### 10.1. Decorator kiểm tra issuer, audience, usage và Bearer token type

~~~java
import java.util.Collection;
import java.util.Objects;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class ExpectedTokenMetadataIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedIssuer;
    private final String expectedAudience;
    private final String expectedTokenUsage;

    public ExpectedTokenMetadataIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedIssuer,
            String expectedAudience,
            String expectedTokenUsage) {

        this.delegate = Objects.requireNonNull(delegate);
        this.expectedIssuer = Objects.requireNonNull(expectedIssuer);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
        this.expectedTokenUsage = Objects.requireNonNull(expectedTokenUsage);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Delegate chịu trách nhiệm giao thức, kết nối AS và active.
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object issuer = principal.getAttribute("iss");
        if (!expectedIssuer.equals(issuer)) {
            throw new BadOpaqueTokenException(
                "Token issuer is not accepted");
        }

        Object audience = principal.getAttribute("aud");
        if (!containsAudience(audience, expectedAudience)) {
            throw new BadOpaqueTokenException(
                "Token audience is not accepted");
        }

        // Đây là CUSTOM attribute của AS, không phải chuẩn RFC 7662.
        Object usage = principal.getAttribute("token_usage");
        if (!expectedTokenUsage.equals(usage)) {
            throw new BadOpaqueTokenException(
                "Token usage is not accepted");
        }

        // Bearer = kiểu credential, KHÔNG phải access token purpose.
        Object tokenType = principal.getAttribute("token_type");
        if (tokenType != null && !"Bearer".equals(tokenType)) {
            throw new BadOpaqueTokenException(
                "Token type is not supported");
        }

        return principal;
    }

    static boolean containsAudience(Object rawAudience, String expected) {
        if (rawAudience instanceof String value) {
            return expected.equals(value);
        }
        if (rawAudience instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }
}
~~~

Những quyết định trong đoạn code:

- **`iss` và `aud` bắt buộc** theo profile ví dụ: null hoặc khác giá trị đều bị từ chối.
- **`token_usage` bắt buộc** và phải là `access_token`: không tự fallback sang loại token khác.
- **`token_type` nếu có thì phải là `Bearer`**. Nếu AS cam kết luôn trả, có thể đổi thành kiểm tra bắt buộc; nếu AS không trả trường này, phải dựa vào cách sử dụng token và cơ chế riêng của contract.
- **Audience có thể là String hoặc Collection**. Dữ liệu sai kiểu sẽ không khớp và bị từ chối.
- Wrapper không phân tích raw opaque token, không đọc header tùy ý do caller gửi, không tự tạo quyền admin.
- Khi thành công, trả **nguyên principal** từ delegate để giữ metadata/authorities đã được tạo theo chính sách framework.

**Chú ý:** Implementation của introspection có thể chuyển metadata sang các kiểu Java khác tùy phiên bản và response. Cần đối chiếu đúng kiểu thực tế với AS, không xử lý lỗi kiểu dữ liệu bằng cách bỏ qua kiểm tra an toàn.

### 10.2. Đăng ký decorator trong Spring Security

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaque-token.introspection-uri}")
            String introspectionUri,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaque-token.client-secret}")
            String clientSecret,
            @Value("${app.security.expected-issuer}") String issuer,
            @Value("${app.security.expected-audience}") String audience,
            @Value("${app.security.expected-token-usage}") String usage) {

        OpaqueTokenIntrospector delegate =
                new NimbusOpaqueTokenIntrospector(
                        introspectionUri,
                        clientId,
                        clientSecret);

        return new ExpectedTokenMetadataIntrospector(
                delegate, issuer, audience, usage);
    }
}
~~~

Trong một số phiên bản Spring Security 6, có thể dùng `SpringOpaqueTokenIntrospector`/builder được khuyến nghị thay vì constructor `NimbusOpaqueTokenIntrospector`; cơ chế chính vẫn là **delegate một introspector HTTP tin cậy rồi áp dụng metadata validation**. Khi tạo bean tùy chỉnh, cần bảo đảm SecurityFilterChain thật sự dùng bean đó, tránh đăng ký nhiều `OpaqueTokenIntrospector` cạnh tranh hoặc cấu hình trực tiếp một introspector khác bỏ qua wrapper.

### 10.3. Nếu AS không trả issuer/audience/usage

Đoạn code strict ở trên **không dành cho mọi IdP**. Không nên sao chép rồi gỡ từng điều kiện khi endpoint báo lỗi, vì mỗi điều kiện đang biểu diễn một ranh giới bảo mật.

Thay vào đó:

- **Issuer vắng:** xác minh introspection endpoint chỉ xử lý token do issuer duy nhất phát hành, hoặc sử dụng cơ chế ràng buộc issuer khác.
- **Audience vắng:** xác minh AS từ chối introspection token của resource khác đối với credential Orders API, hoặc bổ sung resource binding khác.
- **Usage vắng:** xác minh endpoint chỉ introspect OAuth access token và không công nhận ID/refresh token trong API context; hoặc yêu cầu AS cung cấp custom metadata.
- **Tên field khác:** xác định schema và semantic của sản phẩm AS, ví dụ `token_use: access` không mặc định tương đương `token_usage: access_token`.

Mọi lựa chọn bỏ một field phải được **ghi thành contract, kiểm thử và giám sát**, không dựa vào giả định “mặc định AS hẳn đã kiểm tra”.

## 11. `token_type_hint` không phải kết quả xác minh token

Request introspection có thể chứa:

~~~http
Content-Type: application/x-www-form-urlencoded

token=<opaque-token>&token_type_hint=access_token
~~~

`token_type_hint` là **gợi ý tùy chọn** giúp AS xác định loại token để tra cứu. Nó không có nghĩa token thực sự là access token. AS vẫn phải xác minh token và quyết định `active`.

Không được suy luận:

~~~text
Resource Server gửi token_type_hint=access_token
  -> token chắc chắn là access token
  -> bỏ qua mọi kiểm tra purpose
~~~

Tương tự, Client gửi `Authorization: Bearer ...` chỉ là cách **trình credential**, không chứng minh issuer, audience hay mục đích token.

## 12. Khi nhiều issuer chia sẻ một introspection gateway

Một AS gateway có thể xử lý token từ nhiều nguồn:

~~~text
https://identity-gateway.example.test/introspect
  - shop production
  - shop staging
  - partner-A
  - partner-B
~~~

Nếu gateway trả `active: true` cho token thuộc nhiều issuer, Orders API cần xác định **issuer nào được phép**, thay vì chỉ tin rằng tất cả token gateway biết đều dùng được.

| Issuer/profile | Audience cho phép | Quyền được ánh xạ | Chính sách |
| --- | --- | --- | --- |
| Shop production | `orders-api` | `SCOPE_orders.read` | Kiểm tra user/tenant shop |
| Shop staging | `orders-api-staging` | Quyền môi trường staging | Không cho vào production |
| Partner-A | `partner-orders-api` | Quyền theo hợp đồng partner | Chỉ tenant đã liên kết |
| Partner-B | Chưa đăng ký | Không | Không được tự động chấp nhận |

**Cùng `sub` hoặc cùng role `admin` không đồng nghĩa cùng danh tính/quyền trên hai issuer khác nhau.** Với nhiều issuer hợp lệ, nên có mapping và policy riêng theo từng nguồn, thay vì dùng một converter quét mọi chuỗi role rồi cấp quyền chung.

### 12.1. Audience đa giá trị

Một token có:

~~~json
{"aud": ["orders-api", "billing-api"]}
~~~

Hàm `containsAudience` ví dụ chấp nhận token này vì có `orders-api`. Nếu hệ thống không cho phép token được sử dụng ở nhiều resource, thay chính sách bằng kiểm tra tập audience chính xác và test tương ứng. Không tự xem sự xuất hiện của một audience là đủ trong mọi kiến trúc.

### 12.2. Tách môi trường

~~~text
DEV
  introspection_uri = https://id.dev.example.test/introspect
  issuer            = https://id.dev.example.test/realms/shop
  audience          = orders-api-dev

PRODUCTION
  introspection_uri = https://identity.example.test/introspect
  issuer            = https://identity.example.test/realms/shop
  audience          = orders-api
~~~

Credentials, issuer và audience phải được cấu hình riêng theo môi trường, không chấp nhận token dev tại production chỉ vì scope hoặc role giống nhau.

## 13. Quan hệ với `scope`, `exp` và quyền trên tài nguyên

**Kiểm tra metadata token** và **quyết định quyền** là hai tầng khác nhau.

Phản hồi:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "aud": ["orders-api"],
  "token_usage": "access_token",
  "scope": "orders.read",
  "sub": "user-842",
  "tenant_id": "tenant-A"
}
~~~

cho phép Resource Server xác nhận token đúng profile và, theo converter mặc định, có thể tạo authority `SCOPE_orders.read`. Nhưng caller vẫn **không tự được phép** đọc Order 42 nếu order thuộc tenant-B hoặc subject khác theo policy.

| Tầng | Ví dụ kiểm tra | Nếu thiếu |
| --- | --- | --- |
| Introspection | `active`, issuer, audience, usage | Authentication thất bại |
| HTTP authorization | `SCOPE_orders.read` cho GET | Thường 403 |
| Method authorization | Role/permission chuyên biệt | Thường 403 |
| Data policy | Owner, tenant, assignment, trạng thái | 403/404 hoặc lỗi nghiệp vụ |

`exp`, `nbf` và `iat` có thể hỗ trợ validation và cache policy. Với introspection, AS chịu trách nhiệm xác định trạng thái active; nếu có thêm `exp` thì không được cache response vượt thời hạn token hoặc giới hạn được thỏa thuận. Không trích `exp` từ chuỗi opaque do caller đưa vào rồi tự xác minh.

### 13.1. Principal user khác principal service

Token của `client_credentials` có thể mang:

~~~json
{
  "active": true,
  "aud": ["orders-api"],
  "client_id": "nightly-sync",
  "sub": "nightly-sync",
  "scope": "orders.sync",
  "token_usage": "access_token"
}
~~~

Không được suy ra `sub = nightly-sync` là một khách hàng sở hữu Order 42. API cần phân biệt service principal và user principal theo token/profile, endpoint và quyền được cấp. `client_id` của token được introspect cũng khác `client-id` mà Orders API dùng để xác thực với introspection endpoint.

## 14. Phân loại lỗi để không biến dependency outage thành bypass

| Kịch bản | Lớp xử lý | Kỳ vọng bảo mật |
| --- | --- | --- |
| Không Bearer token | Authentication filter | Request protected bị từ chối |
| AS trả `active:false` | Delegate introspector | Không có principal xác thực |
| AS trả `active:true` nhưng audience sai | Metadata wrapper | Từ chối token |
| Issuer không được tin | Metadata wrapper | Từ chối token |
| Custom usage không phải access token | Metadata wrapper | Từ chối token |
| Metadata đủ nhưng thiếu scope | HTTP authorization | Thường 403 |
| Đủ scope nhưng sai owner/tenant | Data policy | 403/404 theo chính sách |
| Resource Server dùng sai introspection client secret | AS / HTTP client | Lỗi tích hợp, không cấp quyền |
| AS 503/timeout hoặc DNS/TLS lỗi | Dependency | Không thực hiện thao tác protected |
| AS trả JSON sai hoặc không có `active` | Parser/delegate | Không tạo authentication thành công |

Với Bearer authentication, token không hợp lệ thường dẫn tới **401 Unauthorized**, còn token đã xác thực nhưng thiếu quyền thường dẫn tới **403 Forbidden**. Lỗi HTTP/network khi AS tạm ngừng có thể được framework và exception handler chuyển thành status khác nhau. Trong mọi trường hợp, **không có request được bảo vệ nào được chạy khi token chưa xác minh được**.

### 14.1. Không fail open

~~~java
// MÃ SAI: TUYỆT ĐỐI KHÔNG ÁP DỤNG.
try {
    return delegate.introspect(token);
} catch (RuntimeException unavailable) {
    return createAdminPrincipal();
}
~~~

Khi không truy cập được AS, API không thể mặc định token còn active hoặc có quyền admin. Nếu có cache introspection, sử dụng kết quả chỉ trong **TTL và chính sách thu hồi đã được phê duyệt**, không tự kéo dài vô hạn khi AS down.

### 14.2. Phân biệt token inactive với AS unavailable

~~~text
HTTP 200 + {"active":false}
    -> AS đã đánh giá: token không active

HTTP 503 / timeout / TLS / DNS error
    -> chưa có kết quả xác thực đáng tin
~~~

Cả hai đều không được cho phép thao tác protected, nhưng log/metrics cần phân biệt để tìm lỗi token, lỗi cấu hình hay sự cố dependency.

## 15. Unit test validator với fake introspector

Vì wrapper dựa vào interface `OpaqueTokenIntrospector`, có thể unit test metadata logic mà không gọi HTTP.

### 15.1. Fixture principal

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

final class TestPrincipalFactory {

    static OAuth2AuthenticatedPrincipal principal(
            Map<String, Object> attributes) {

        return new DefaultOAuth2AuthenticatedPrincipal(
                "user-842",
                attributes,
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders.read")));
    }

    private TestPrincipalFactory() {}
}
~~~

Đây là principal **giả lập cho unit test**, không đại diện một introspection response thật. Trong production, chỉ delegate được cấu hình tin cậy mới tạo principal từ metadata AS.

### 15.2. Test đúng audience, issuer và usage

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class ExpectedTokenMetadataIntrospectorTest {

    private static final String ISSUER =
            "https://identity.example.test/realms/shop";

    private Map<String, Object> valid() {
        Map<String, Object> attributes = new HashMap<>();
        attributes.put("iss", ISSUER);
        attributes.put("aud", List.of("orders-api"));
        attributes.put("token_type", "Bearer");
        attributes.put("token_usage", "access_token");
        attributes.put("sub", "user-842");
        attributes.put("scope", "orders.read");
        return attributes;
    }

    private OpaqueTokenIntrospector policy(Map<String, Object> attrs) {
        OpaqueTokenIntrospector fakeDelegate =
                token -> TestPrincipalFactory.principal(attrs);

        return new ExpectedTokenMetadataIntrospector(
                fakeDelegate, ISSUER, "orders-api", "access_token");
    }

    @Test
    void acceptsCorrectMetadata() {
        var principal = policy(valid()).introspect("opaque-test-token");
        assertEquals("user-842", principal.getAttribute("sub"));
    }

    @Test
    void rejectsWrongAudience() {
        var attrs = valid();
        attrs.put("aud", List.of("billing-api"));
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsWrongIssuer() {
        var attrs = valid();
        attrs.put("iss", "https://id.dev.example.test/realms/shop");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsWrongTokenUsageEvenIfBearer() {
        var attrs = valid();
        attrs.put("token_usage", "id_token");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsMissingRequiredAudience() {
        var attrs = valid();
        attrs.remove("aud");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }

    @Test
    void rejectsMissingRequiredUsage() {
        var attrs = valid();
        attrs.remove("token_usage");
        assertThrows(BadOpaqueTokenException.class,
                () -> policy(attrs).introspect("opaque-test-token"));
    }
}
~~~

Những test này chỉ chứng minh **logic kiểm tra metadata sau delegate**. Chúng **không chứng minh** Resource Server đã gửi POST đúng endpoint, xác thực với AS đúng secret, xử lý `active`, TLS hay timeout. Để kiểm tra các yếu tố đó phải dùng integration test với mock HTTP AS.

### 15.3. Ma trận negative cases nên có

| Metadata | Test case | Kết quả |
| --- | --- | --- |
| `aud` String | Bằng `orders-api` | Chấp nhận nếu các điều kiện khác đúng |
| `aud` List | Chứa `orders-api` | Chấp nhận theo policy “contains” |
| `aud` List | Chỉ có `billing-api` | Từ chối |
| `aud` | Vắng hoặc sai kiểu | Từ chối theo strict contract |
| `iss` | Issuer dev thay production | Từ chối |
| `iss` | Vắng khi contract bắt buộc | Từ chối |
| `token_usage` | `access_token` | Chấp nhận theo custom profile |
| `token_usage` | `id_token` | Từ chối |
| `token_usage` | Vắng khi contract bắt buộc | Từ chối |
| `token_type` | `Bearer` | Không bị từ chối bởi kiểm tra kiểu |
| `token_type` | Giá trị không được hợp đồng cho phép | Từ chối |
| `scope` | Thiếu `orders.read` | Authentication có thể thành công; authorization 403 |
| `active` | `false` | Delegate phải từ chối trước wrapper |

## 16. Integration test với introspection endpoint giả lập

Sử dụng **WireMock** hoặc **OkHttp MockWebServer** để kiểm thử giao thức thực:

~~~mermaid
sequenceDiagram
    participant C as Test Client
    participant API as Spring Resource Server
    participant AS as Mock AS

    C->>API: Bearer opaque-valid
    API->>AS: POST token + introspection credential
    AS-->>API: active:true, đúng iss/aud/usage
    API->>API: Wrapper chấp nhận metadata
    API-->>C: Qua authentication và policy

    C->>API: Bearer opaque-wrong-audience
    API->>AS: POST token + credential
    AS-->>API: active:true, aud:billing-api
    API->>API: Wrapper từ chối
    API-->>C: Authentication failure
~~~

### 16.1. Các kịch bản quan trọng

1. AS trả `active:true`, issuer/audience/usage đúng và scope đủ → request qua lớp authentication.
2. AS trả `active:false` → từ chối.
3. AS trả active nhưng audience của API khác → từ chối.
4. AS trả issuer dev/partner không được phép → từ chối.
5. AS trả custom usage = `id_token` → từ chối.
6. AS trả `token_type = Bearer` nhưng thiếu required `token_usage` → từ chối theo strict profile.
7. AS trả dữ liệu `aud` sai kiểu hoặc metadata malformed → từ chối.
8. Metadata đúng nhưng scope không đủ → HTTP authorization từ chối.
9. Metadata/scope đúng nhưng owner/tenant không đúng → business policy từ chối.
10. AS trả 401 cho credential introspection sai → không có authentication thành công.
11. AS 5xx/timeout → không thực hiện thao tác protected.
12. AS trả JSON thiếu `active` hoặc sai format → không coi là token đã xác thực.
13. Token của Billing API được introspect bằng credential Orders API → xác định liệu AS trả inactive hay active với audience sai; cả hai đường đều không được cấp quyền Orders.

### 16.2. Xác nhận giao thức HTTP

Mock AS phải quan sát:

~~~text
POST /introspect
Content-Type: application/x-www-form-urlencoded
token=<opaque-test-token>
Authorization: <credential-cua-resource-server>
token_type_hint=access_token (nếu client HTTP gửi)
~~~

**`token_type_hint` là tùy chọn**, không nên đặt test bắt buộc có nếu thư viện không gửi. Mục tiêu là xác nhận AS được gọi với credential hợp lệ, body token đúng và response thực sự đi qua wrapper.

### 16.3. Không chỉ assert mã HTTP

Khi request bị từ chối vì metadata sai, integration test nên kiểm tra:

~~~text
Không có Authentication đáng tin
Không vào controller được bảo vệ
Không gọi service cập nhật dữ liệu
Không ghi database / gửi sự kiện nghiệp vụ
~~~

Một request cuối cùng trả 401/403 nhưng đã thay đổi đơn hàng thì **không đạt yêu cầu bảo mật**.

## 17. Cache introspection và metadata có thể cũ

Caching giảm số lần gọi AS nhưng tạo đánh đổi:

- `active:true` được cache có thể vẫn tồn tại sau khi token bị thu hồi.
- Role/scope có thể thay đổi trong AS nhưng cache chưa cập nhật.
- Resource binding hoặc policy issuer có thể đổi trong khi cache cũ còn giữ metadata.
- Một giá trị cache theo user `sub` thay vì theo token có thể trộn lẫn nhiều token với audience/scope khác nhau.

Nếu dùng cache, cần quản lý:

1. TTL có giới hạn theo `exp` và policy.
2. Quy tắc cache positive/negative results.
3. Invalidation khi token/credential bị thu hồi.
4. Cách bảo vệ cache key vì opaque token là credential bí mật.
5. Quy tắc khi AS down: chỉ dùng kết quả còn trong hạn **đã được phê duyệt**, không kéo dài vô hạn.
6. Policy version: khi thay expected issuer/audience, metadata được kiểm tra theo policy cũ có cần bị invalidation?

Có hai mô hình thường gặp:

~~~text
HTTP introspection -> metadata validation -> cache validated principal

HTTP introspection -> cache AS response -> validation mỗi request
~~~

Nếu chọn mô hình đầu, việc thay chính sách có thể đòi xóa/phiên bản hóa cache. Nếu chọn mô hình sau, cần đảm bảo cả cache và validation được thực thi với dữ liệu/TTL tin cậy.

**Không cache theo `sub`** làm khóa duy nhất, vì cùng subject có thể có nhiều token với scope, audience, expiry khác nhau. Tránh log nguyên token hoặc đưa token plaintext vào metric label.

## 18. Vận hành, quan sát và xử lý thay đổi hợp đồng

Các chỉ số/nhật ký có thể ghi:

- Request/correlation ID, endpoint API.
- Introspection endpoint **được cấu hình** và môi trường.
- Latency, timeout, HTTP 4xx/5xx của dependency.
- Lý do từ chối theo loại: inactive, wrong audience, wrong issuer, wrong usage, missing required metadata, insufficient scope.
- Phiên bản schema/hợp đồng đang dùng.

**Không ghi nguyên opaque token, introspection client secret, refresh token hoặc metadata nhạy cảm không cần thiết.** Khi chưa xác minh token, dữ liệu đầu vào do caller kiểm soát có thể gây log injection/cardinality nếu không xử lý.

### 18.1. Khi AS đổi tên metadata

Ví dụ AS thay:

~~~text
aud = ["orders-api"]
~~~

thành:

~~~text
audience = ["orders-api"]
~~~

Đừng tắt audience validator để tránh lỗi. Hãy cập nhật **hợp đồng, wrapper và bộ test positive/negative** đồng thời. Nếu cần hỗ trợ hai schema trong giai đoạn chuyển tiếp, phải xác định kiểu, phạm vi và thời gian tương thích.

### 18.2. Không để caller tự chọn expected issuer/audience

Sai:

~~~http
X-Expected-Issuer: https://id.dev.example.test
X-Expected-Audience: billing-api
~~~

Expected values phải đến từ **cấu hình server và chính sách định tuyến tin cậy**, không từ header/query/body do caller đặt. Với multi-tenant, xác định tenant/profile cũng phải gắn với ranh giới tin cậy, tránh lấy chuỗi chưa xác minh để mở rộng tập issuer được phép.

## 19. Những hiểu nhầm phổ biến

**“`active:true` nghĩa là mọi API đều nhận được token.”** Sai. Audience/resource binding phải được bảo đảm riêng.

**“RFC 7662 bắt buộc mọi phản hồi trả `aud` và `iss`.”** Không. Metadata có thể khác nhau theo AS.

**“Thiếu `aud` thì cứ bỏ qua.”** Không. Nếu không có resource binding tương đương, thiếu audience bắt buộc phải dẫn tới từ chối.

**“`token_type: Bearer` đồng nghĩa access token.”** Không. Bearer là phương thức sử dụng, không phải purpose.

**“`token_type_hint=access_token` là bằng chứng token đúng loại.”** Không. Đây chỉ là gợi ý khi gửi introspection.

**“Opaque token đọc được claims giống JWT.”** Không có hợp đồng decode local; chỉ tin kết quả AS hoặc cơ chế được thỏa thuận.

**“Cùng issuer thì token của Billing API cũng dùng được ở Orders API.”** Không. Issuer và audience là hai kiểm tra khác nhau.

**“Đã chọn đúng introspection URI thì khỏi cần kiểm tra issuer.”** Chưa chắc. Nếu endpoint đa issuer, vẫn cần ràng buộc issuer từ metadata hoặc policy.

**“Metadata đúng tức là có quyền trên mọi đơn hàng.”** Không. Scope và chính sách owner/tenant vẫn áp dụng.

**“Để kiểm tra token type chỉ cần lấy đuôi chuỗi opaque token.”** Sai. Token purpose phải do AS/profile xác định.

**“Khi AS down thì mặc định mọi token đã gặp trước đó còn active.”** Sai. Chỉ dùng cache còn hiệu lực theo chính sách, không fail open.

**“Unit test fake introspector chứng minh HTTP client đã xác thực với AS.”** Không. Cần integration test POST/form/credential và xử lý lỗi thực.

## 20. Mẫu hợp đồng giữa Identity và Orders API

~~~yaml
# Hợp đồng ví dụ, không phải cấu hình được Spring tự động đọc.
resource_server: orders-api
token_format: opaque
trusted_authorization_server: https://identity.example.test
introspection_endpoint: https://identity.example.test/introspect
introspection_auth: client_secret_basic

metadata:
  active:
    required: true
    equals: true
  audience:
    claim: aud
    required: true
    contains: orders-api
  issuer:
    claim: iss
    required: true
    exact: https://identity.example.test/realms/shop
  token_usage:
    claim: token_usage
    provenance: "custom metadata from Authorization Server"
    required: true
    equals: access_token
  token_type:
    claim: token_type
    required: false
    if_present: Bearer
  scope:
    endpoint_rules:
      GET_orders: orders.read
      POST_orders: orders.write

missing_required_metadata: reject
unexpected_metadata: reject
upstream_unavailable: fail_closed
data_policy: verify_owner_and_tenant
~~~

Nếu một IdP không trả `iss` hoặc `token_usage`, hợp đồng có thể thay yêu cầu trực tiếp bằng **ràng buộc qua endpoint và chính sách AS đã kiểm chứng**. Điều đó phải được mô tả riêng; không được “làm giả” field rồi coi là hợp lệ.

### Những câu hỏi cần thống nhất trước khi triển khai

1. Endpoint introspection chỉ chấp nhận token của một issuer hay nhiều issuer?
2. Token của Billing API gửi qua credential của Orders API sẽ nhận kết quả gì?
3. AS có trả `aud` không, dưới dạng String hay array, và định danh nào là đúng?
4. Nếu không trả `iss`, endpoint/registration bảo đảm nguồn phát hành thế nào?
5. AS có thể introspect ID token hoặc refresh token không?
6. `token_type` của AS phản ánh Bearer hay một ý nghĩa tùy chỉnh khác?
7. Có custom `token_usage`/`token_use` không và các giá trị hợp lệ là gì?
8. Field nào là bắt buộc, optional hoặc đã được ràng buộc bởi endpoint?
9. Token đa audience có được Orders API chấp nhận không?
10. Token `client_credentials` có policy riêng với user token không?
11. Cache có TTL, invalidation, policy version rõ ràng chưa?
12. AS down có chắc chắn không dẫn tới bypass authentication không?

## 21. Bài tập tình huống

**Tình huống A:** AS trả `active:true`, `aud:["billing-api"]`, `scope:"orders.read"`. Orders API có thể nhận không?

**Không**, nếu yêu cầu audience `orders-api`. Scope trùng tên không sửa được audience sai.

**Tình huống B:** AS trả `active:true` và `token_type:"Bearer"`. Có thể kết luận đây chắc chắn là access token?

**Không.** `Bearer` nói về loại credential/protocol sử dụng. Token purpose cần dựa vào profile/metadata hoặc bảo đảm của introspection endpoint.

**Tình huống C:** AS có custom `token_usage:"id_token"`. Orders API chỉ nhận access token. Kết quả?

**Từ chối**, dù token active và audience/issuer nhìn có vẻ phù hợp.

**Tình huống D:** Response thiếu `iss`; developer tự gán `iss = expectedIssuer` trước khi validate. Có phải xác minh issuer?

**Không.** Cần nguồn tin cậy chứng minh issuer hoặc ràng buộc endpoint thay thế, không tự điền giá trị.

**Tình huống E:** AS cam kết credential introspection Orders API chỉ trả active cho token dành cho Orders API, nhưng response không trả `aud`. Có nhất thiết tự yêu cầu field `aud`?

**Không theo RFC 7662** nếu ràng buộc resource tương đương đã được thỏa thuận, xác thực và kiểm thử. Nhưng không được giả định điều đó khi AS không có policy ấy.

**Tình huống F:** Token metadata đúng, nhưng thiếu `SCOPE_orders.read`. Đây là authentication failure hay authorization failure?

Token **có thể xác thực thành công**, sau đó HTTP authorization phải từ chối, thường là 403.

**Tình huống G:** Fake `OpaqueTokenIntrospector` trả principal đúng và unit test pass, nhưng production trả 401 vì client secret introspection sai. Vì sao?

Unit test **không kiểm tra giao thức HTTP/credential**. Cần integration test với mock AS và kiểm tra cấu hình môi trường.

**Tình huống H:** Token đã xác thực đúng issuer/audience, có `orders.read`, nhưng đơn thuộc tenant khác. Cho đọc được không?

**Không** nếu policy tenant/owner không cho phép. Introspection không thay quyền trên dữ liệu.

---

## Kết luận

Khi tùy chỉnh **opaque-token introspection** trong Spring Security Resource Server, hãy bắt đầu từ **hợp đồng metadata thật của Authorization Server**. `active: true` chỉ xác nhận trạng thái token theo AS; khi hợp đồng yêu cầu, Resource Server còn phải đối chiếu **audience**, **issuer** và **token purpose**. `token_type: Bearer` **không đồng nghĩa** `token_usage: access_token`, còn `token_type_hint` chỉ là gợi ý trong request.

**`OpaqueTokenIntrospector` decorator** là vị trí phù hợp để kết hợp introspection từ nguồn đáng tin với validator metadata trước khi tạo principal/authorities. Nếu trường bắt buộc thiếu hoặc sai, phải từ chối; nếu nhà phát hành không trả trường ấy, chỉ được thay bằng **bảo đảm tương đương đã có hợp đồng và kiểm thử**. Sau khi xác thực, API vẫn phải kiểm tra scope, role và quyền thực tế đối với owner/tenant/resource. Tuyệt đối không bỏ kiểm tra token khi AS không sẵn sàng hoặc khi metadata không đáp ứng yêu cầu.
