# 16.9. Xử lý invalid_client, invalid_scope và giới hạn quyền

## 1. Bài toán: service không xin được Access Token hoặc bị từ chối gọi API

Trong **Spring Security OAuth 2.0 OIDC Client**, grant **Client Credentials** cho phép một backend service xin Access Token bằng thông tin xác thực của **chính client**, thay vì thông qua người dùng đăng nhập trên browser. Đây là mô hình phổ biến cho job xử lý dữ liệu, tích hợp hệ thống, đồng bộ theo lịch và các request machine-to-machine (M2M).

Ví dụ, dịch vụ `report-exporter` gọi API báo cáo mỗi giờ:

~~~text
report-exporter (OAuth2 Client)
    |
    | POST /oauth2/token
    | grant_type=client_credentials
    | client authentication
    | scope=reports.read
    v
Authorization Server
    |
    | access_token
    v
report-exporter
    |
    | GET /api/reports
    | Authorization: Bearer <access_token>
    v
Reports Resource Server
~~~

Khi mọi thứ đúng, client nhận Access Token và gửi token đó đến API phù hợp. Trong thực tế, có hai nhóm sự cố rất khác nhau:

1. **Token Endpoint từ chối cấp token**, thường trả JSON OAuth 2.0 error như `invalid_client` hoặc `invalid_scope`.
2. **Token đã được cấp nhưng Resource Server từ chối request**, có thể trả HTTP `401` hoặc `403`, ví dụ do Access Token hết hạn, sai audience, thiếu scope hoặc chính sách API không cho phép.

Hai nhóm cần cách chẩn đoán và xử lý khác nhau. **Không nên sửa lỗi `invalid_client` bằng cách thêm scope**, và cũng không nên giải quyết HTTP 403 từ API bằng cách xoay Client Secret khi vấn đề thực sự là thiếu quyền.

Mục tiêu của bài:

- Hiểu chính xác ý nghĩa `invalid_client` và `invalid_scope` trong **Client Credentials grant**.
- Phân biệt HTTP status, OAuth error code, Bearer challenge và chính sách API.
- Cấu hình client authentication, token URI và scopes trong Spring Security Servlet/backend.
- Xử lý lỗi qua `OAuth2AuthorizedClientManager` mà không làm lộ credential hoặc retry không kiểm soát.
- Thiết kế scope tối thiểu, audience/resource phù hợp và cách tách quyền giữa các service.
- Có quy trình troubleshooting, observability và bộ tình huống kiểm thử dành cho hệ thống M2M.

## 2. Client Credentials không phải đăng nhập OIDC của người dùng

Trước khi phân tích lỗi, cần xác định grant đang chạy:

| Thuộc tính | Client Credentials | Authorization Code + OIDC Login |
| --- | --- | --- |
| Chủ thể được ủy quyền | Ứng dụng/client hoặc service identity | Người dùng và client đã được ủy quyền |
| Browser redirect | Không cần | Có |
| Authorization code | Không có | Có |
| `state` và PKCE | Không dùng cho grant cơ bản này | Dùng để ràng buộc giao dịch theo cấu hình |
| `nonce` / ID Token | Không phải một phần chuẩn của Client Credentials | Liên quan xác thực OIDC |
| Token Endpoint | Có, dùng `grant_type=client_credentials` | Có, dùng `grant_type=authorization_code` |
| Refresh Token | Theo OAuth 2.0, thông thường **không nên cấp** cho Client Credentials | Có thể được cấp tùy provider/scope/policy |
| Cách cấp token mới | Thực hiện Client Credentials grant mới | Refresh Token grant hoặc yêu cầu người dùng cấp quyền lại |

**Client Credentials không xác thực một end-user.** Nếu downstream API cần biết “người dùng nào đang xem báo cáo”, client credentials token một mình không cung cấp ngữ cảnh delegated user đó. Không dùng `sub` của service token hoặc email nhân viên giả lập để biến một machine identity thành user identity.

Tên module có OIDC vì ứng dụng Spring Security có thể hỗ trợ cả OAuth2 Client và OIDC Login, nhưng **Client Credentials là OAuth 2.0 grant**, không nhất thiết có ID Token hoặc UserInfo.

## 3. Token request và token response chuẩn

### 3.1. Request từ confidential client

Một Token Endpoint request được gửi trực tiếp từ backend:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.net
Authorization: Basic <BASE64_OF_CLIENT_ID_COLON_CLIENT_SECRET>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=reports.read
~~~

Đây là request **minh họa**. Không đưa chuỗi client secret thật vào tài liệu, log hoặc repository.

Giải thích:

- `grant_type=client_credentials` chọn loại grant.
- `scope` là tham số tùy chọn, chỉ xin những quyền cần cho công việc.
- Với `client_secret_basic`, client xác thực tại Token Endpoint bằng HTTP Basic Authentication.
- Authorization Server kiểm tra client credentials, grant được phép, scope được cấp và các policy khác trước khi phát token.
- Toàn bộ request phải được thực hiện qua **HTTPS với TLS validation**.

Nếu client dùng `private_key_jwt`, mTLS hoặc phương thức xác thực khác thì request sẽ khác. Không thay đổi phương thức client authentication tùy tiện vì mỗi registration tại Authorization Server thường có hợp đồng rõ ràng.

### 3.2. Response thành công

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

Theo OAuth 2.0, response thành công có `access_token` và `token_type`; `expires_in` mô tả thời hạn Access Token **theo giây** khi được trả. Scope trong response, nếu được gửi, cho biết phạm vi đã cấp theo quy tắc OAuth 2.0. **Không mặc định mọi scope client yêu cầu đều đã được cấp** nếu provider trả response khác mong đợi.

Refresh Token nói chung không phải cơ chế mặc định của Client Credentials; client có thể xin Access Token mới bằng cách tiếp tục xác thực với token endpoint. Nếu provider có extension khác, cần đọc contract cụ thể thay vì giả định đây là hành vi chung của chuẩn.

### 3.3. Response lỗi

Ví dụ Token Endpoint không chấp nhận client authentication:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="token"
Cache-Control: no-store

{
  "error": "invalid_client"
}
~~~

Hoặc yêu cầu scope không hợp lệ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store

{
  "error": "invalid_scope",
  "error_description": "Requested scope is not allowed"
}
~~~

Các response là **ví dụ**, không phải bảo đảm mọi provider trả cùng HTTP status, header hoặc error description. Để phân loại lỗi, xem **OAuth error code** và ngữ cảnh thực tế thay vì chỉ dựa vào một số HTTP status.

**Không in nguyên `error_description` vào giao diện hoặc log production**: đó là chuỗi do hệ thống bên ngoài gửi và có thể chứa chi tiết nội bộ, dữ liệu nhạy cảm hoặc nội dung không đáng tin.

## 4. invalid_client: Authorization Server không chấp nhận danh tính client

### 4.1. Ý nghĩa chính xác

Trong OAuth 2.0, `invalid_client` biểu thị **client authentication thất bại** — chẳng hạn client không được biết đến, thông tin xác thực sai, không gửi client authentication đúng cách hoặc phương thức xác thực không được hỗ trợ.

Với Client Credentials, đây thường là lỗi **ở bước client chứng minh danh tính với Token Endpoint**, trước khi bàn đến việc token có quyền gọi API nào.

Nguyên nhân cụ thể:

| Nguyên nhân | Ví dụ |
| --- | --- |
| Client ID không đúng | Dùng ID của môi trường staging để gọi production Authorization Server |
| Client Secret sai hoặc đã xoay vòng | Service còn dùng secret cũ sau một lần rotation |
| Sai client authentication method | Provider cấu hình `client_secret_basic`, client gửi body kiểu `client_secret_post` |
| Sai Token Endpoint/tenant | Đăng ký client ở realm A nhưng gọi `token-uri` của realm B |
| Client bị vô hiệu hóa | Tài khoản service bị khóa, hết hạn hoặc chưa được kích hoạt |
| Chứng thư/JWT client assertion không hợp lệ | mTLS cert hoặc `private_key_jwt` hết hạn, sai issuer/audience, key hoặc assertion |
| Header/encoding sai | Basic header bị tạo không đúng, client ID/secret encode sai |
| Secret injection lỗi | Biến môi trường rỗng, secret mount thiếu hoặc config placeholder chưa resolve |

Một số provider cũng dùng mã lỗi riêng cho policy hoặc tình huống gần giống. Vì thế, hãy kiểm tra documentation và audit events của Authorization Server khi cần xác định nguyên nhân cuối cùng.

### 4.2. HTTP 401 có chắc là invalid_client không?

Không. HTTP 401 **tại Token Endpoint** có thể liên quan đến client authentication. Nếu OAuth response chứa `invalid_client`, đây là mã lỗi hữu ích. Nhưng HTTP 401 **từ Resource Server** khi gọi API lại thường nói về **Access Token** chứ không phải client authentication lúc xin token.

~~~text
POST https://auth.example.net/oauth2/token
  -> 401 + error=invalid_client
  => Kiểm tra client authentication/token endpoint.

GET https://api.example.net/reports
  -> 401 + WWW-Authenticate: Bearer error="invalid_token"
  => Kiểm tra Access Token được gửi tới API.
~~~

Đừng nhầm hai request chỉ vì chúng đều trả 401.

### 4.3. Cách xử lý khi gặp invalid_client

Một chuỗi điều tra có thứ tự:

1. Kiểm tra **`registrationId` và `token-uri`** đang được ứng dụng dùng có thuộc cùng Authorization Server/tenant với client registration không.
2. Xác định **`client-authentication-method`** được đăng ký ở Authorization Server và cấu hình trong Spring Security.
3. Kiểm tra **nguồn cấp secret** hoạt động, nhưng không in secret để kiểm tra.
4. Kiểm tra client có bị disable, xóa, thu hồi hoặc rotate credentials không.
5. Nếu dùng private key/mTLS, kiểm tra certificate, key ID, assertion audience, thời gian và trust chain.
6. Kiểm tra log máy chủ Authorization Server theo **correlation ID** hoặc request ID an toàn.
7. Khắc phục cấu hình/credential, sau đó mới thực hiện một yêu cầu cấp token mới.

**Không retry `invalid_client` vô hạn**. Nếu secret sai hoặc client bị disable, retry nhanh chỉ làm tăng tải và có thể kích hoạt rate limiting hoặc khóa tài khoản.

### 4.4. Không “sửa” invalid_client bằng cách nới quyền

Tăng scope từ `reports.read` thành `reports.read reports.write` **không sửa** sai client credentials. Đồng thời, đổi sang `client_secret_post` mà không có hợp đồng provider phù hợp vừa không giải quyết gốc lỗi vừa tăng rủi ro lộ secret trong một số lớp quan sát.

Việc chuyển sang phương thức xác thực yếu hơn hoặc bỏ TLS validation chỉ vì Token Endpoint đang trả `invalid_client` là **không chấp nhận được**.

## 5. invalid_scope: client xin một phạm vi không hợp lệ hoặc không được phép

### 5.1. Ý nghĩa trong OAuth 2.0

`invalid_scope` được dùng khi scope được yêu cầu **không hợp lệ, không được biết đến, có định dạng sai hoặc vượt quyền mà Authorization Server cho phép**.

Ví dụ client `report-exporter` đã được phép dùng:

~~~text
reports.read
metrics.read
~~~

Nhưng request lại gửi:

~~~text
scope=reports.read reports.admin
~~~

Nếu `reports.admin` không tồn tại hoặc chưa được cấp cho client, Token Endpoint có thể trả:

~~~json
{
  "error": "invalid_scope"
}
~~~

Lỗi này nói về **quyền được xin tại Authorization Server**, không có nghĩa client ID/secret nhất thiết sai.

### 5.2. Các nguyên nhân thường gặp

| Nguyên nhân | Ví dụ |
| --- | --- |
| Typo trong tên scope | `report.read` thay vì `reports.read` |
| Scope không được provider công bố | Client xin `billing.export` nhưng Authorization Server chỉ hỗ trợ `billing.read` |
| Scope được biết nhưng chưa được cấp cho client | Service xin quyền admin không nằm trong allowed scopes |
| Scope dành cho một grant/loại client khác | Scope chỉ cho delegated users, không cho `client_credentials` |
| Sai tenant/environment | Scope ở staging chưa tồn tại hoặc chưa được phép trên production |
| Định dạng tham số sai | Scope bị truyền thành JSON array hoặc nối sai dấu phân cách |
| Default scopes bị thay đổi | Ứng dụng không gửi scope, Authorization Server áp dụng default mới không phù hợp |
| Policy quản trị thay đổi | Quản trị viên gỡ scope được phép khỏi client |

Theo cách sử dụng OAuth 2.0 thường gặp, `scope` trong token request là **chuỗi cách nhau bởi khoảng trắng**, không phải một mảng JSON. Với `application/x-www-form-urlencoded`, dấu cách phải được mã hóa đúng khi truyền HTTP.

### 5.3. invalid_scope không nhất thiết là 403 của API

So sánh:

~~~text
Client xin scope không được phép:
  POST /oauth2/token
  scope=reports.admin
  -> HTTP 400 + error=invalid_scope

Client xin token thành công:
  scope=reports.read
  -> Access Token được cấp.

Client dùng token chỉ có reports.read để xóa báo cáo:
  DELETE /api/reports/123
  -> HTTP 403, có thể kèm insufficient_scope
~~~

`invalid_scope` xuất hiện khi **xin token**. `insufficient_scope` thường liên quan việc **Resource Server từ chối Bearer Token** vì thiếu quyền cho thao tác cụ thể. Hai lỗi có thể bắt nguồn từ cùng một policy nhưng không cùng giai đoạn giao thức.

### 5.4. Cách xử lý khi gặp invalid_scope

1. Xác nhận tên scope và chính sách đã đăng ký tại Authorization Server.
2. Kiểm tra phạm vi đó có được phép cho **Client Credentials grant** không.
3. So sánh scope ứng dụng cấu hình với **scope tối thiểu** mà API thật sự cần.
4. Nếu một scope không còn được cấp, quyết định **loại bỏ tính năng phụ thuộc** hoặc yêu cầu quản trị viên cấp quyền chính thức.
5. Không tự động thay `reports.read` bằng `reports.admin` hay `*`.
6. Nếu có nhiều chức năng với quyền khác nhau, cân nhắc tách client registrations hoặc service identities.
7. Theo dõi việc thay đổi scope như một thay đổi cấu hình/authorization policy, có kiểm thử tích hợp với API đích.

Với service chạy không tương tác, **không có màn hình consent của người dùng để giải quyết `invalid_scope`**. Thường cần quản trị viên Authorization Server hoặc người sở hữu quyền API cập nhật đăng ký client/policy đúng quy trình.

## 6. Giới hạn quyền: một token được cấp không có nghĩa có toàn quyền

Client Credentials xác thực client và có thể nhận token dành cho tài nguyên cụ thể. Resource Server vẫn quyết định token có đủ quyền để thao tác hay không dựa trên scope, audience, issuer và chính sách nghiệp vụ.

### 6.1. Bốn ranh giới không nên trộn lẫn

| Ranh giới | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Client authentication** | Client có chứng minh đúng danh tính với Token Endpoint không? | Secret/certificate hợp lệ |
| **Grant permission** | Client có được dùng `client_credentials` không? | Registration cho phép grant tương ứng |
| **Scope/audience issuance** | Authorization Server có cấp token cho phạm vi và API được xin không? | `reports.read` cho Reports API |
| **Resource Server authorization** | Token cụ thể có được phép đọc/sửa dữ liệu này không? | GET cho phép, DELETE từ chối |

Một client có secret đúng **không mặc nhiên** có quyền `reports.admin`. Một Access Token có scope `reports.read` **không mặc nhiên** dùng được cho Billing API. Và một token hợp lệ của Reports API có thể vẫn bị từ chối vì resource-level policy.

### 6.2. Scope tối thiểu

Đối với job chỉ xuất báo cáo, scope có thể là:

~~~text
reports.read
~~~

Không nên cấp mặc định:

~~~text
reports.read reports.write reports.delete users.admin
~~~

chỉ vì “sau này có thể cần”. Mỗi scope dư thừa làm tăng phạm vi thiệt hại nếu secret hoặc token bị lộ.

**Least privilege** áp dụng ở cả hai phía:

1. Client chỉ **xin** scope cần thiết.
2. Authorization Server chỉ **cho phép cấp** scope phù hợp với service identity.
3. Resource Server kiểm tra token và áp dụng policy theo tài nguyên thực tế.

### 6.3. Audience/resource cũng quan trọng như scope

Ví dụ:

~~~text
Access Token A:
  issuer   = company-auth
  audience = reports-api
  scope    = reports.read

Access Token B:
  issuer   = company-auth
  audience = billing-api
  scope    = billing.read
~~~

Ngay cả khi hai API dùng tên scope giống nhau, Access Token dành cho API A không tự được API B chấp nhận. Với JWT Access Token, Resource Server phải kiểm tra signature, issuer, audience, expiration và scope/policy theo contract. Với opaque token, có thể dùng introspection hoặc cơ chế validation phù hợp provider.

**OAuth2 scope không thay cho audience.** Không dựa vào chuỗi scope trong token để gửi token sang mọi service có hostname khác nhau.

Một số provider dùng tham số `resource` hoặc `audience` riêng khi cấp token. Đây là đặc điểm phụ thuộc chuẩn extension/provider; chỉ cấu hình khi Authorization Server hỗ trợ và tài liệu tích hợp yêu cầu.

### 6.4. Role nội bộ không tự biến thành scope

Một ứng dụng web có thể có `ROLE_ADMIN` trong `Authentication` sau OIDC Login. Điều đó **không làm Access Token của Client Credentials grant có thêm scope** hoặc cho phép token service gọi API quản trị.

Ngược lại, client credentials token có `reports.read` không chứng minh một người dùng cụ thể có `ROLE_READER` trong portal. Hai khái niệm authorization ở hai tầng khác nhau.

## 7. Cấu hình Spring Security cho Client Credentials

### 7.1. Dependency

Với Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Nếu ứng dụng có Spring MVC/Servlet Controller, thêm các starter web/security phù hợp. Với Spring Boot 4.x, các starter Spring Security được tách module; chọn dependency theo Spring Boot BOM/version của dự án. Ví dụ Java phía dưới sử dụng các API OAuth2 Client phổ biến trong Spring Security 6.x.

### 7.2. application.yml

Ví dụ một backend exporter:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Lưu ý:

- `reports-service` là **registration ID** dùng trong Java code.
- `company-auth` xác định cấu hình nhà cung cấp/token URI.
- `client_secret_basic` phải đúng phương thức Authorization Server đã đăng ký.
- `client_credentials` không cần `redirect-uri`, `authorization-uri`, `state` hoặc `nonce` cho grant cơ bản này.
- `scope` được giới hạn ở `reports.read` thay vì yêu cầu mọi quyền.
- Client secret không ghi trực tiếp vào YAML; giá trị nằm trong secret manager/environment phù hợp.
- Token URI phải đến từ cấu hình đáng tin cậy, không lấy từ input HTTP của người dùng.

### 7.3. Hai đăng ký cho hai nhóm quyền khác nhau

Nếu ứng dụng thực sự có hai công việc độc lập:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-reader:
            provider: company-auth
            client-id: ${REPORTS_READER_CLIENT_ID}
            client-secret: ${REPORTS_READER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.read]
          billing-reader:
            provider: company-auth
            client-id: ${BILLING_READER_CLIENT_ID}
            client-secret: ${BILLING_READER_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [billing.read]
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Đây là cấu hình **minh họa thay thế** cho ví dụ `reports-service`, không phải đoạn cần chép chồng vào YAML trước. Tách các client identities giúp quản lý cấp/thu hồi quyền và rotation độc lập hơn nếu chính sách Authorization Server cho phép.

**Không nhất thiết phải tạo client registration mới cho từng HTTP endpoint**; sự phân tách phụ thuộc trust boundary, loại dữ liệu và yêu cầu vận hành. Nhưng tránh một client ID có toàn quyền trên nhiều API không liên quan khi có lựa chọn an toàn hơn.

## 8. OAuth2AuthorizedClientManager dùng cho service-to-service

Với Client Credentials chạy trong scheduled job hoặc service không có Servlet request, `AuthorizedClientServiceOAuth2AuthorizedClientManager` là lựa chọn phù hợp.

### 8.1. Cấu hình manager

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ServiceOAuth2ClientConfig {

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            serviceAuthorizedClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Một số điểm:

1. `clientCredentials()` cho phép manager xin Access Token bằng grant tương ứng.
2. `OAuth2AuthorizedClientService` giữ các authorized clients đã cấp để dùng lại theo registration và principal name.
3. Khi token hết hạn hoặc cần cấp mới, manager phối hợp với provider để gọi Token Endpoint.
4. Không bắt buộc có `HttpServletRequest`, phù hợp với backend job.
5. Không tự thêm `refreshToken()` chỉ vì muốn “refresh” client credentials: grant này thông thường xin token **mới bằng client authentication**, không dựa vào Refresh Token.

### 8.2. Gọi authorize() với service principal ổn định

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-service")
        .principal("system-report-exporter")
        .build();

OAuth2AuthorizedClient authorizedClient =
    serviceAuthorizedClientManager.authorize(request);

if (authorizedClient == null) {
    throw new IllegalStateException(
        "Không nhận được authorized client cho reports-service");
}

// Chỉ dùng authorizedClient.getAccessToken() ở backend.
~~~

Ở đây `serviceAuthorizedClientManager` là biến được dependency injection vào class sử dụng. `system-report-exporter` là principal **phục vụ khóa lưu trữ của service**, không phải người dùng cuối được xác thực bởi OIDC.

Nếu thay principal name ngẫu nhiên ở mỗi lần gọi, manager có thể không tìm thấy authorized client cũ và phát sinh cấp token lại liên tục. Dùng namespace ổn định, tách đúng service identities và không dùng danh tính từ user input.

### 8.3. Lưu token không đồng nghĩa token dùng được mọi nơi

`OAuth2AuthorizedClientService` có thể tải client đã cấp theo `registrationId + principalName`, nhưng việc tìm thấy Access Token **không chứng minh Resource Server chấp nhận token**.

~~~text
authorizedClient != null
  -> có bản ghi token
  -> cần kiểm tra lifecycle/grant qua manager
  -> gửi token đến API đúng audience/scope
  -> API còn có quyền từ chối theo policy.
~~~

## 9. Bắt và phân loại lỗi OAuth2 của Token Endpoint

Spring Security có thể biểu diễn OAuth2 error qua `OAuth2AuthorizationException` hoặc một dạng exception liên quan tùy tầng xử lý/version. Mã lỗi OAuth2 thường nằm ở `OAuth2Error.getErrorCode()`.

### 9.1. Ví dụ service phân loại invalid_client và invalid_scope

~~~java
package com.example.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.stereotype.Service;

@Service
public class ReportServiceTokenProvider {

    private static final Logger log =
        LoggerFactory.getLogger(ReportServiceTokenProvider.class);

    private final AuthorizedClientServiceOAuth2AuthorizedClientManager manager;

    public ReportServiceTokenProvider(
            AuthorizedClientServiceOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient requireAuthorizedClient() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-service")
                .principal("system-report-exporter")
                .build();

        try {
            OAuth2AuthorizedClient client = manager.authorize(request);
            if (client == null) {
                throw new IllegalStateException(
                    "Không thể cấp token trong ngữ cảnh hiện tại");
            }
            return client;
        } catch (OAuth2AuthorizationException exception) {
            String code = exception.getError().getErrorCode();

            if ("invalid_client".equals(code)) {
                log.warn(
                    "OAuth2 M2M token request rejected: invalid_client; registration=reports-service");
                throw new ServiceCredentialException(
                    "Cấu hình xác thực OAuth2 client không hợp lệ",
                    exception);
            }

            if ("invalid_scope".equals(code)) {
                log.warn(
                    "OAuth2 M2M token request rejected: invalid_scope; registration=reports-service");
                throw new ScopePolicyException(
                    "Scope yêu cầu không được Authorization Server chấp nhận",
                    exception);
            }

            log.warn(
                "OAuth2 M2M token request failed; registration=reports-service; errorCode={}",
                safeCode(code));
            throw new UpstreamAuthorizationException(
                "Không thể xin Access Token từ Authorization Server",
                exception);
        }
    }

    private static String safeCode(String code) {
        if (code == null) {
            return "unknown";
        }
        return switch (code) {
            case "invalid_request", "unauthorized_client",
                 "unsupported_grant_type", "invalid_grant",
                 "server_error", "temporarily_unavailable" -> code;
            default -> "other";
        };
    }
}
~~~

**Đây là ví dụ cấu trúc xử lý:** `ServiceCredentialException`, `ScopePolicyException` và `UpstreamAuthorizationException` là **các application exception do dự án tự định nghĩa**. Để dùng trong dự án thực tế, cần tạo ba exception classes tương ứng hoặc thay bằng exception hierarchy của ứng dụng. Mã sử dụng Java 17 `switch` expression.

Ví dụ tuyệt đối **không log**:

~~~java
// PHẢN VÍ DỤ: nguy cơ ghi raw OAuth2 token/secret/error description.
logger.error("OAuth error: {}", exception.getError().getDescription());
logger.error("Authorized client: {}", authorizedClient);
~~~

Một số lỗi kết nối hoặc lỗi HTTP không được parse thành OAuth error hợp lệ có thể phát sinh exception khác. Vì vậy phân loại ở đây **không bắt mọi sự cố mạng/TLS**; tầng integration cần thêm xử lý timeout, transport exception và monitoring thích hợp.

### 9.2. Một cách định nghĩa application exceptions

~~~java
package com.example.service;

public class ServiceCredentialException extends RuntimeException {
    public ServiceCredentialException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Các exception `ScopePolicyException` và `UpstreamAuthorizationException` có thể khai báo tương tự trong **file Java riêng của dự án**. Ví dụ này cho thấy cách phân biệt lỗi cấu hình xác thực, lỗi chính sách scope và lỗi upstream chung mà không lộ token qua thông điệp gửi người dùng.

Nếu application dùng scheduled job, exception này có thể được bắt bởi scheduler/worker để đưa vào cảnh báo vận hành. Với REST API gọi gián tiếp token manager, controller có thể trả một lỗi 503 hoặc thông điệp nghiệp vụ đã kiểm soát tùy loại sự cố, **không trả nguyên OAuth error description của Authorization Server**.

### 9.3. Cẩn trọng với failure handler của manager

`OAuth2AuthorizedClientManager` có điểm mở rộng **`OAuth2AuthorizationFailureHandler`**. Với một số grant, failure handler có thể xóa authorized client không hợp lệ dựa trên mã lỗi và policy.

Không thay failure handler rồi:

- Tự xóa tất cả authorized clients mỗi khi có HTTP 500.
- Dùng `invalid_client` như tín hiệu phải tự động tạo client registration mới.
- Retry Client Credentials trực tiếp ở failure handler không giới hạn.
- Biến `invalid_scope` thành yêu cầu scope rộng hơn mà không phê duyệt.

Nếu cần alerting, tốt hơn là ghi metric/log tối thiểu, bảo toàn hành vi mặc định phù hợp và xử lý quyết định retry/disable integration ở lớp điều phối có thể kiểm soát.

**Một lỗi `invalid_client` không có nghĩa Access Token đã cấp trước đó lập tức vô hiệu trong mọi Resource Server**; Authorization Server và policy có thể quyết định khác. Tuy nhiên không nên cố dùng token cũ để vòng tránh việc service identity đã bị thu hồi; cần thực thi chính sách khóa/incident response của hệ thống.

## 10. Chiến lược retry: không đối xử mọi lỗi giống nhau

Mô hình quyết định:

~~~mermaid
flowchart TD
    A["Client Credentials token request thất bại"] --> B{"Nguyên nhân?"}
    B -->|"invalid_client"| C["Không retry mù; sửa client authentication/secret/tenant"]
    B -->|"invalid_scope"| D["Không tự nâng scope; kiểm tra allowlist và policy"]
    B -->|"unauthorized_client"| E["Kiểm tra grant permission, client registration"]
    B -->|"429 / 5xx / timeout"| F["Retry có giới hạn, backoff, jitter, circuit breaker"]
    B -->|"Khác/không rõ"| G["Phân loại theo provider contract; điều tra an toàn"]
    C --> H["Cảnh báo vận hành và chặn công việc phụ thuộc"]
    D --> H
    E --> H
    F --> I["Thành công hoặc trả lỗi có kiểm soát"]
    G --> H
~~~

### 10.1. Lỗi thường không nên retry tự động

| Lỗi | Nguyên nhân thường gặp | Chính sách đề xuất |
| --- | --- | --- |
| `invalid_client` | Client authentication sai/không còn hiệu lực | Dừng retry liên tục, cảnh báo chủ cấu hình/secret |
| `invalid_scope` | Xin scope sai hoặc vượt quyền | Dừng tự động; cập nhật cấu hình/policy có phê duyệt |
| `unauthorized_client` | Client không được phép dùng grant này | Kiểm tra registration và grant permission |
| `unsupported_grant_type` | Authorization Server không hỗ trợ `client_credentials` trong cấu hình này | Sửa cấu hình/provider, không retry |
| `invalid_request` | Thiếu hoặc sai tham số request | Sửa request serialization/auth method |

### 10.2. Lỗi có thể retry sau khi đánh giá

Các trường hợp như timeout mạng, HTTP 429, 502/503 hoặc sự cố tạm thời ở Token Endpoint có thể phù hợp với **retry có giới hạn**, nhưng cần biết provider có chính sách rate limiting và retry riêng hay không.

Một thiết kế thường gồm:

- **Exponential backoff** thay vì retry ngay liên tục.
- **Jitter** để nhiều instance không cùng “đánh thức” Token Endpoint một lúc.
- Giới hạn số lần/độ dài retry; không để job treo vô hạn.
- Tôn trọng header `Retry-After` khi có và phù hợp.
- Circuit breaker hoặc tạm dừng đồng bộ khi hệ thống upstream đang lỗi kéo dài.
- Giám sát phân biệt token endpoint unavailable với client authentication failure.

**Không retry đồng thời từ hàng trăm pods khi token cũ vừa hết hạn.** Nếu cần, cơ chế caching/coordination của authorized client có thể giảm “thundering herd” khi token mới phải được cấp.

### 10.3. Không retry bằng cách tăng quyền

Giả sử xin `scope=reports.read` thất bại. Không được tự “thử mạnh hơn” bằng:

~~~text
scope=reports.read reports.write reports.admin
~~~

Việc nới quyền vừa không có cơ sở giải quyết lỗi vừa vi phạm least privilege. Một client không đủ quyền phải báo thiếu quyền hoặc bị chặn cho đến khi policy được cập nhật hợp lệ.

## 11. Resource Server trả 401 hoặc 403: xử lý riêng với lỗi Token Endpoint

Sau khi token được cấp, client gửi request đến Reports API:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.net
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

### 11.1. HTTP 401 và invalid_token

API có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nguyên nhân có thể:

- Token hết hạn hoặc bị thu hồi.
- Sai issuer/audience hoặc gửi token đến API khác với resource được cấp.
- Chữ ký JWT không hợp lệ, JWKS/key rotation chưa đồng bộ hoặc introspection thất bại.
- Header Bearer sai định dạng hoặc thiếu token.

Ứng dụng có thể xin token mới qua AuthorizedClientManager khi phù hợp, nhưng **không được mặc định retry vô hạn** nếu token tiếp tục bị từ chối. Nếu API nói sai audience, refresh/token issuance lại với cùng cấu hình thường không giải quyết được.

### 11.2. HTTP 403 và insufficient_scope

Ví dụ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

Token có thể hợp lệ nhưng không đủ quyền để **sửa** báo cáo. Hành vi an toàn:

1. Dừng thao tác bị từ chối.
2. Kiểm tra API contract và scope mà endpoint yêu cầu.
3. Nếu service thực sự cần thao tác đó, yêu cầu cấp quyền qua governance/quy trình quản trị.
4. Tách quyền đọc và quyền ghi nếu cần thay vì cấp `reports.write` cho mọi job đọc.
5. Không đổi Access Token, tự ghép scope hoặc bỏ Resource Server authorization.

**HTTP 403 không luôn có nghĩa thiếu scope.** API có thể từ chối do tenant, ownership, trạng thái tài nguyên, chính sách IP hoặc một điều kiện nghiệp vụ khác. Chỉ diễn giải `insufficient_scope` khi có tín hiệu phù hợp từ API/Bearer challenge hoặc tài liệu chính thức.

### 11.3. Bảng đối chiếu bốn trường hợp dễ nhầm

| Nơi lỗi | Dấu hiệu | Điều cần điều tra |
| --- | --- | --- |
| Token Endpoint | `invalid_client` | Xác thực client ID/secret/key/cert và token URI |
| Token Endpoint | `invalid_scope` | Scope được yêu cầu, scope được phép, grant policy |
| Resource Server | `401 invalid_token` | Access Token hết hạn, sai issuer/audience, revoked, bearer format |
| Resource Server | `403 insufficient_scope` | Scope đã cấp cho token và quyền endpoint yêu cầu |

Đây là lý do việc chỉ lưu một metric `oauth_failed=1` là không đủ. Để vận hành tốt, cần biết **giai đoạn**, **registration**, **mã lỗi an toàn** và **API liên quan**.

## 12. Token response có scope hẹp hơn yêu cầu thì sao?

Client xin:

~~~text
scope=reports.read metrics.read
~~~

Nhưng response trả:

~~~json
{
  "access_token": "ACCESS_TOKEN_PLACEHOLDER",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

Không được tự kết luận rằng token có cả `metrics.read` chỉ vì **request ban đầu** đã xin scope đó. Nếu Authorization Server cấp scope khác với scope được yêu cầu, response phải phản ánh phạm vi được cấp theo các quy tắc OAuth 2.0.

Một service có thể cần logic:

~~~java
OAuth2AuthorizedClient authorizedClient = /* kết quả manager */;

Set<String> grantedScopes =
    authorizedClient.getAccessToken().getScopes();

if (!grantedScopes.contains("reports.read")) {
    throw new IllegalStateException(
        "Token không được cấp scope bắt buộc reports.read");
}
~~~

Code giả định đã có authorized client và thêm import `java.util.Set`. Kiểm tra scopes tại client giúp tránh gọi API chắc chắn thất bại, nhưng **Resource Server vẫn phải kiểm tra và thực thi quyền**, không tin việc client tự đánh giá scope.

Chú ý: Một số provider sử dụng claim `scp` hoặc `scope` bên trong JWT Access Token, hoặc trả trường `scope` của token response theo contract riêng. Không tự parse JWT bất kỳ để “thêm” scopes vào `OAuth2AccessToken`; hãy dựa trên OAuth2 response model và contract/validation đúng chuẩn.

### 12.1. Nếu scope vắng mặt trong token response

OAuth 2.0 có quy tắc về phạm vi đã cấp khi scope response không được trả và giống/khác request. Không xem việc vắng mặt `scope` nghĩa là “được toàn bộ quyền” hoặc “không có quyền” trong mọi provider; cần hiểu cách Spring Security và Authorization Server diễn giải trường này theo giao thức.

Với một tích hợp nhạy cảm, nên xác định scope mong đợi bằng hợp đồng API, không để service tự đoán quyền hoặc tự mở rộng.

### 12.2. Scope là tập quyền, không phải vai trò người dùng

Ví dụ `reports.read` có thể chỉ cho phép service đọc báo cáo chung mà API định nghĩa, trong khi nghiệp vụ còn giới hạn tenant hoặc loại báo cáo. Client Credentials token không gắn với user consent nên việc phân quyền theo tenant/service identity cần được Resource Server thực thi độc lập với scope tổng quát.

## 13. Giới hạn blast radius bằng nhiều client identities

Một tổ chức có:

- `report-exporter` cần `reports.read`.
- `billing-reconciler` cần `billing.read`.
- `account-provisioner` cần `users.manage`.

Nếu cả ba chia sẻ một Client Secret với toàn bộ scope, việc lộ secret ở một job ít tin cậy có thể cho attacker xin token quyền cao.

Mô hình tốt hơn có thể là:

~~~mermaid
flowchart LR
    A["Report exporter"] --> B["Client registration: reports-reader"]
    C["Billing reconciler"] --> D["Client registration: billing-reader"]
    E["Account provisioner"] --> F["Client registration: provisioning-admin"]
    B --> G["Authorization Server"]
    D --> G
    F --> G
    G --> H["Scope/audience-bound Access Tokens"]
    H --> I["Resource Server policy"]
~~~

### 13.1. Các nguyên tắc phân tách

1. Tách client credentials theo **service boundary** và mức độ nhạy cảm của quyền.
2. Cấp quyền theo **API và tác vụ thật sự cần**, không dùng admin client cho job đọc dữ liệu.
3. Quản lý vòng đời secret/cert độc lập, có rotation và thu hồi.
4. Hạn chế network egress đến Token Endpoint/Resource Server phù hợp.
5. Theo dõi token issuance bất thường theo client identity mà không ghi credential.
6. Dùng audience/resource binding khi provider hỗ trợ, không để token của API A dùng ngang sang API B.

Tách registration không loại bỏ hoàn toàn rủi ro nếu nhiều registrations cùng dùng **một client ID/secret có toàn quyền**. Quyền thực tế phải được giới hạn ở Authorization Server, không chỉ ở tên bean Java.

### 13.2. Không tự xin scope rộng rồi lọc quyền trong code

Một cấu hình kiểu “xin hết để tiện, sau đó service tự không gọi API nguy hiểm” **không đạt least privilege**. Nếu credential bị lộ, attacker có thể dùng token để làm những việc mà code thông thường không làm. Giới hạn quyền phải được thực thi bởi Authorization Server và Resource Server.

## 14. Client authentication method và lỗi invalid_client

### 14.1. client_secret_basic

~~~yaml
client-authentication-method: client_secret_basic
~~~

HTTP request sử dụng Authorization Basic theo quy định OAuth 2.0. Với confidential client có client secret, đây là một cơ chế phổ biến. Secret **không xuất hiện trong form body** nếu client đã dùng Basic đúng cách.

### 14.2. client_secret_post

~~~yaml
client-authentication-method: client_secret_post
~~~

Token request có thể chứa `client_id` và `client_secret` trong form body khi provider cho phép. Cách này chỉ phù hợp khi đã được đăng ký/cho phép. Body của Token Endpoint cũng nhạy cảm, có thể bị ghi bởi proxy/trace nếu logging sai.

Không tự thử một loạt authentication methods và gửi cùng secret ở nhiều vị trí nếu chưa được provider chấp thuận.

### 14.3. private_key_jwt, mTLS và cơ chế không dùng shared secret

Một số tích hợp M2M sử dụng client authentication mạnh hơn:

- JWT client assertion được ký bằng private key của client.
- Mutual TLS để xác thực certificate của client.
- Phương thức tích hợp riêng do Authorization Server hỗ trợ.

Những cơ chế này có thể giảm phụ thuộc vào shared client secret nhưng vẫn cần key/cert lifecycle, rotation và policy chặt chẽ. Nếu sai key, JWT audience, thời gian hoặc certificate, Authorization Server cũng có thể báo `invalid_client`.

**Không giả định chỉ cần đổi thuộc tính YAML sang `private_key_jwt` là đủ.** Cần cấu hình client assertion/certificate, key material và token client phù hợp theo phiên bản Spring Security/provider.

## 15. Quản lý secret và xử lý rotation

Một nguyên nhân rất thực tế của `invalid_client` là **secret rotation** không đồng bộ.

~~~text
T0: Authorization Server chấp nhận secret V1
T1: V2 được tạo trong secret manager
T2: Một số app instances vẫn có V1
T3: Authorization Server thu hồi V1
T4: Các instance còn V1 nhận invalid_client
~~~

### 15.1. Quy trình rotation hợp lý

1. Chuẩn bị secret/certificate mới thông qua hệ thống quản trị đáng tin cậy.
2. Nếu Authorization Server hỗ trợ cửa sổ chuyển tiếp, dùng chính sách rotation có overlap phù hợp.
3. Cập nhật secret manager/mount và rollout các instance theo kế hoạch.
4. Kiểm tra khả năng cấp token bằng service registration đúng môi trường (không in secret).
5. Thu hồi credential cũ theo chính sách.
6. Quan sát `invalid_client` rate và khả năng gọi API sau rotation.

**Đừng tự tạo “fallback” sang secret V1 đã bị thu hồi trong code production**. Một lần invalid_client sau rotation cần điều tra instance nào đang dùng configuration cũ, không phải lý do lưu secret cũ vĩnh viễn.

### 15.2. Logging không được tiết lộ credential

Không nên:

~~~java
// PHẢN VÍ DỤ:
log.info("Client secret = {}", clientSecret);
log.error("Token request form = {}", requestBody);
~~~

Chỉ log thông tin như:

~~~text
event=oauth2_client_credentials_failed
registration=reports-service
stage=token_endpoint
oauth_error=invalid_client
environment=production
correlation_id=internal-trace-9f2e
~~~

Đây là format log **minh họa**, không phải output mặc định. Không ghi Authorization header, client assertion, Client Secret, Access Token hoặc nguyên token response/error description.

## 16. Không đưa lỗi M2M ra màn hình đăng nhập của người dùng

Một service nền không có người dùng đang chờ consent. Khi Authorization Server trả `invalid_scope` cho `report-exporter`, hiển thị trang “Bạn đã từ chối cấp quyền” là sai ngữ cảnh.

Hãy phân biệt UX/operational response:

| Bối cảnh | Đối tượng cần biết | Phản hồi phù hợp |
| --- | --- | --- |
| Scheduled job xin token thất bại | Đội vận hành, owner tích hợp | Alert theo registration, mã lỗi, thời điểm, tác vụ |
| API nội bộ gọi service nhận lỗi phụ thuộc token | Caller/service upstream | Mã lỗi ứng dụng có kiểm soát, retry policy rõ ràng |
| Web page cần dữ liệu từ API M2M | Người dùng cuối | Thông báo tính năng tạm không khả dụng, không lộ client secret/error internals |
| Quản trị viên cập nhật scope/credential | Người có quyền quản trị | Hướng dẫn cấu hình/secret rotation và mức quyền cần thiết |

`AuthenticationFailureHandler` của `oauth2Login()` xử lý browser login failure, **không phải cơ chế trung tâm để bắt lỗi Client Credentials trong scheduled job**. Những lỗi này phát sinh trong luồng client manager/token endpoint và được xử lý tại service/worker/monitoring.

## 17. Authorized client storage và sự nhất quán quyền

`OAuth2AuthorizedClientService` có thể lưu token của service dưới khóa:

~~~text
(registrationId, principalName)
~~~

Ví dụ:

~~~text
("reports-service", "system-report-exporter")
    -> OAuth2AuthorizedClient(accessToken, issuedAt, expiresAt, scopes)
~~~

### 17.1. Token đã lưu có thể mang quyền cũ

Giả sử Authorization Server đã **thu hẹp allowed scopes** của client, nhưng service vẫn còn Access Token được cấp trước khi thay đổi. Token cũ có thể tiếp tục hợp lệ đến khi hết hạn hoặc bị thu hồi, tùy policy.

Vì vậy:

- Không coi sửa YAML scope là cơ chế thu hồi token đã được cấp trước đó.
- Nếu thay đổi quyền quan trọng, cần có kế hoạch token revocation/introspection/cache invalidation theo hạ tầng.
- Resource Server không chỉ dựa vào trạng thái “có bản ghi authorized client trong DB”.
- Client manager có thể tái sử dụng token đến khi cần cấp mới; việc role/scope thay đổi ở Authorization Server không bảo đảm được phản ánh tức thời.

### 17.2. Một token cho nhiều chức năng?

Không nên dùng cùng một Access Token cho tất cả các API nếu token chỉ có audience cho một API. Nếu client cần nhiều resources với quyền khác nhau, thiết kế authorized clients/registrations và cách cấp token phù hợp.

Với Access Token dạng opaque, không tự giải mã/giả định scope. Với JWT Access Token, client cũng không nên tự lấy claim chưa xác minh rồi cho rằng Resource Server chắc chắn sẽ chấp nhận.

### 17.3. Client Credentials và cleanup

Một authorized client của service có thể được xóa khi:

- Service/registration bị retire.
- Token hoặc credentials được thu hồi theo incident response.
- Chính sách storage yêu cầu cleanup.
- Cần buộc lần authorize tiếp theo phải xin token theo cấu hình mới, với cơ chế an toàn và có kiểm soát.

Tuy nhiên, **xóa local authorized client không đồng nghĩa token được revoke ở Authorization Server**. Nếu quyền cần ngừng ngay, phải xem cơ chế revocation và enforcement tại Resource Server.

## 18. Bảng xử lý lỗi tổng hợp

| Bước | Mã/triệu chứng | Ý nghĩa thường gặp | Hành động ưu tiên |
| --- | --- | --- | --- |
| Token Endpoint | `invalid_client` | Client authentication không thành công | Kiểm tra ID/secret/method/key/tenant; dừng retry mù |
| Token Endpoint | `invalid_scope` | Scope không hợp lệ/không được phép | Sửa scope hoặc policy theo phê duyệt |
| Token Endpoint | `unauthorized_client` | Client không được phép dùng grant | Kiểm tra Client Credentials grant enabled |
| Token Endpoint | `unsupported_grant_type` | Grant không được hỗ trợ | Kiểm tra `grant_type` và nhà cung cấp |
| Token Endpoint | `invalid_request` | Thiếu/sai tham số request | Kiểm tra form encoding và token client |
| Token Endpoint | `400 invalid_grant` | Không phải lỗi điển hình của Client Credentials chuẩn; có thể là grant khác hoặc extension | Kiểm tra request/grant thực tế, không quy tất cả về secret |
| Token Endpoint | HTTP 429 / 5xx | Rate limit hoặc upstream tạm lỗi | Retry có giới hạn, backoff/jitter/Retry-After |
| Token Endpoint | TLS/timeout | Kết nối/certificate/network | Sửa trust/network, retry theo loại lỗi |
| Resource Server | `401 invalid_token` | Access Token không hợp lệ/hết hạn/không được chấp nhận | Kiểm tra issuer, audience, expiration, lifecycle |
| Resource Server | `403 insufficient_scope` | Thiếu quyền API | Kiểm tra scope được cấp và policy Resource Server |
| Resource Server | HTTP 403 khác | Policy nghiệp vụ/tenant/ownership | Điều tra API authorization, không tự nâng scope |
| Client Manager | `authorize()` trả null | Không có client phù hợp/không thể authorize trong context | Kiểm tra manager, provider, registration/principal |
| Storage | Không tìm thấy authorized client | Sai key, store/session/restart | Kiểm tra `registrationId + principalName`, backing store |

Không có một exception class duy nhất bảo đảm bao trùm mọi dòng trong bảng. Tầng HTTP, token client, Spring Security provider và Resource Server có thể đưa ra exception/response khác nhau.

## 19. Quy trình debug có thứ tự

### 19.1. Khi Token Endpoint trả invalid_client

~~~text
1. Xác nhận request đang dùng grant_type=client_credentials.
2. Xác nhận registrationId thực tế và token-uri.
3. Xác nhận environment/tenant/realm đúng.
4. Kiểm tra client ID và phương thức client authentication.
5. Kiểm tra secret manager hoặc key/certificate đã được mount.
6. Xem client có bị revoke/disable/rotate.
7. Đối chiếu log Authorization Server bằng correlation ID.
8. Sửa config và thử lại có kiểm soát.
~~~

Không in secret ra màn hình hoặc log để đối chiếu thủ công. Có thể kiểm tra secret presence/version metadata trong secret manager mà không tiết lộ giá trị.

### 19.2. Khi Token Endpoint trả invalid_scope

~~~text
1. In/quan sát danh sách tên scope được cấu hình (không phải credential).
2. Đối chiếu scope với tài liệu Authorization Server.
3. Kiểm tra scope được grant cho đúng client, đúng environment.
4. Xem scope có được hỗ trợ với client_credentials hay không.
5. Kiểm tra scope formatting/URL encoding.
6. Xác định chức năng nào thật sự cần scope.
7. Xin phê duyệt scope mới hoặc giảm scope/request functionality.
8. Kiểm thử API đích với token hợp lệ sau khi cấu hình được sửa.
~~~

### 19.3. Khi token được cấp nhưng API vẫn 403

~~~text
1. Xác định API endpoint/method đang được gọi.
2. Kiểm tra token có được cấp cho đúng audience/resource không.
3. Kiểm tra scope đã được cấp, không chỉ scope đã yêu cầu.
4. Kiểm tra Bearer challenge hoặc contract của API.
5. Xem còn policy tenant, ownership, IP, resource state nào không.
6. Không tự nâng scope hoặc tắt Resource Server authorization.
7. Nếu API yêu cầu scope mới, cập nhật policy qua quy trình chính thức.
~~~

## 20. Tình huống kiểm thử cần thiết

Một bài kiểm thử tốt cần tách **Token Endpoint** khỏi **Resource Server**, đồng thời sử dụng client credentials **giả** trong môi trường test.

| Tình huống | Token Endpoint / API mô phỏng | Kết quả mong đợi |
| --- | --- | --- |
| Client đúng, scope đúng | HTTP 200 token response | Manager tạo/lưu authorized client |
| Client Secret sai | `401 invalid_client` | Báo lỗi cấu hình, không retry vô hạn |
| Sai client authentication method | `invalid_client` | Giữ nguyên policy, sửa registration |
| Client bị disable | `invalid_client` hoặc provider-specific policy error | Không cố bypass bằng client khác |
| Scope không tồn tại | `400 invalid_scope` | Không tự sửa thành scope admin |
| Scope chưa được cấp cho client | `invalid_scope` | Cảnh báo cấu hình/owner |
| Grant `client_credentials` không được phép | `unauthorized_client` | Không cố chạy authorization code bằng browser giả |
| Scope response hẹp hơn request | HTTP 200 có `scope` hẹp | Không giả định có scope rộng hơn |
| API nhận token đã hết hạn | `401 invalid_token` | Xin token mới nếu phù hợp, có giới hạn |
| API từ chối thao tác ghi | `403 insufficient_scope` | Chặn thao tác, không tự cấp quyền |
| API từ chối theo tenant | HTTP 403 theo policy | Không quy chắc chắn là invalid_scope |
| Token Endpoint tạm 503 | HTTP 503 | Retry backoff/jitter theo giới hạn |
| Token Endpoint 429 | HTTP 429, có thể Retry-After | Giới hạn retry và giảm concurrency |
| Hai workers cùng xin token | Nhiều instance | Không tạo bão request không cần thiết |
| Secret rotation | Một instance secret cũ, một instance secret mới | Quan sát đúng `invalid_client`, rollout an toàn |
| Mã lỗi chưa biết | OAuth error code tùy provider | Fallback an toàn, không crash vì parse giả định |
| Token response chứa refresh token ngoài dự kiến | Extension provider | Không dựa vào token này nếu grant/policy chưa được thiết kế |

### 20.1. Test xử lý mã OAuth2Error mà không gọi mạng

Có thể tách logic phân loại lỗi ra thành hàm thuần:

~~~java
public enum TokenFailureKind {
    CLIENT_AUTHENTICATION,
    SCOPE_POLICY,
    GRANT_CONFIGURATION,
    OTHER
}

public static TokenFailureKind classify(String errorCode) {
    if ("invalid_client".equals(errorCode)) {
        return TokenFailureKind.CLIENT_AUTHENTICATION;
    }
    if ("invalid_scope".equals(errorCode)) {
        return TokenFailureKind.SCOPE_POLICY;
    }
    if ("unauthorized_client".equals(errorCode)
            || "unsupported_grant_type".equals(errorCode)) {
        return TokenFailureKind.GRANT_CONFIGURATION;
    }
    return TokenFailureKind.OTHER;
}
~~~

Đây là **đoạn mã minh họa** để đặt trong một utility class; khi triển khai cần bố trí enum và method đúng cấu trúc Java. Unit test có thể assert:

~~~java
assertEquals(
    TokenFailureKind.CLIENT_AUTHENTICATION,
    classify("invalid_client"));

assertEquals(
    TokenFailureKind.SCOPE_POLICY,
    classify("invalid_scope"));

assertEquals(
    TokenFailureKind.OTHER,
    classify(null));
~~~

Unit test phân loại error code **không chứng minh** token client đã xác thực đúng với Authorization Server hoặc Resource Server thực thi đúng scopes. Cần integration test với provider/test server để kiểm tra request/response thật, và test Resource Server riêng cho 401/403.

### 20.2. Không dùng production secret trong test

Để mô phỏng `invalid_client`, dùng client registration/cert/secret **test-only** hoặc mock Token Endpoint, không cố gửi secret production sai nhiều lần. Điều đó có thể gây cảnh báo an ninh, khóa client hoặc làm lộ credential qua test logs.

## 21. Kiến trúc observability và cảnh báo

Một service M2M có thể xuất metrics không nhạy cảm:

~~~text
oauth2_token_authorization_total{
  registration="reports-service",
  outcome="failure",
  error_class="invalid_client"
}

oauth2_resource_call_total{
  resource="reports-api",
  outcome="forbidden",
  error_class="insufficient_scope"
}
~~~

Đây là format **minh họa ý tưởng metrics**, không phải tên metric có sẵn của Spring Security.

### 21.1. Những tín hiệu hữu ích

| Tín hiệu | Ý nghĩa vận hành |
| --- | --- |
| Tỷ lệ `invalid_client` tăng đột biến | Secret rotation, client disable, sai môi trường hoặc auth method |
| Tỷ lệ `invalid_scope` sau deploy | Scope trong config thay đổi, provider policy chưa cập nhật |
| Số lần cấp token quá cao | Cache/authorized client store không tái sử dụng được, principal name thay đổi hoặc token có TTL ngắn |
| HTTP 401 của API tăng | Token expiry, audience/issuer mismatch, resource configuration lỗi |
| HTTP 403 của API tăng | Scope/tenant/policy thay đổi hoặc client đang gọi sai endpoint |
| Token Endpoint timeout/5xx | Sự cố kết nối/upstream, cần circuit breaker và retry hợp lý |

Không gắn raw token, Client Secret, certificate private key hoặc thông tin cá nhân không cần thiết vào metric labels. Label có cardinality cao như request IDs riêng lẻ cũng không phù hợp với các metric tổng hợp.

### 21.2. Khi nào cần cảnh báo?

Vì `invalid_client` và `invalid_scope` thường khó tự khôi phục, việc cảnh báo sớm cho owner/service team có ý nghĩa hơn retry liên tục. Ngược lại, một vài timeout tạm thời có thể xử lý bằng backoff trong giới hạn rồi mới escalate.

Một cảnh báo tốt cần có **registration, môi trường, endpoint loại nào (Token Endpoint/API), mã lỗi đã phân loại và thời điểm**. Không gửi token/secret hoặc raw response vào alert.

## 22. Các sai lầm triển khai phổ biến

### 22.1. Dùng Client Credentials để “đóng giả” một người dùng

`client_credentials` là machine-to-machine. Nếu API yêu cầu delegated user, cần một grant/flow đúng mục đích. Không gán cứng `userId=admin` vào request để đi qua kiểm tra quyền.

### 22.2. Coi mọi HTTP 401 là invalid_client

HTTP 401 tại Token Endpoint và HTTP 401 tại Resource Server có ngữ nghĩa khác nhau. Điều tra đúng host/endpoint trước khi đổi client secret.

### 22.3. Tự nâng scope khi nhận invalid_scope

Tăng scope để “thử lại” là vi phạm least privilege và thường không giải quyết lỗi. Chỉ cập nhật scope theo hợp đồng API và quyền được phê duyệt.

### 22.4. Xin scope quá rộng rồi tin code sẽ tự giới hạn

Nếu Access Token đã được cấp quyền admin, attacker sở hữu token có thể gọi trực tiếp API admin cho dù code bình thường không làm thế. Phải giới hạn ở Authorization Server/Resource Server.

### 22.5. Ghi client secret trong URL hoặc log

Client Secret thuộc credential và chỉ nên được xử lý trong cơ chế client authentication đã được đăng ký. Không đưa vào query string; không log HTTP Basic header, form body chứa secret hoặc JWT client assertion.

### 22.6. Retry invalid_client liên tục

Nếu credentials sai, mỗi request lại lỗi; retry nhanh chỉ tăng tải và có thể kích hoạt khóa tài khoản. Dừng retries cho lỗi cấu hình/credentials không thể tự khôi phục.

### 22.7. Xóa mọi authorized client khi xảy ra bất kỳ lỗi nào

Timeout Token Endpoint không tự chứng minh token trước đó đã bị thu hồi. Việc xóa toàn bộ store hoặc logout mọi user có thể gây gián đoạn không cần thiết. Quyết định cleanup dựa trên policy và loại lỗi cụ thể.

### 22.8. Dùng Refresh Token grant cho Client Credentials như mặc định

Thông thường Client Credentials không nhận Refresh Token; client xin token mới bằng grant `client_credentials`. Đừng thêm `offline_access` hoặc refresh logic dành cho OIDC end-user login chỉ để “bật token lâu dài”.

### 22.9. Trộn Access Token của nhiều Resource Server

Token dành cho Reports API không mặc định dùng được cho Billing API. Cần xem audience/resource, scope và cấu hình cấp token đúng đích.

### 22.10. Chỉ nhìn scope được yêu cầu, không nhìn scope được cấp

Nếu response có scope hẹp hơn, ứng dụng không được tự coi token có scope còn thiếu. Resource Server quyết định quyền cuối cùng, không phải các kỳ vọng ở client.

### 22.11. Dùng ID Token để gọi API M2M

Client Credentials chuẩn không tạo user ID Token. ID Token từ một lần đăng nhập OIDC khác không phải Access Token của service và không nên được gửi thay Bearer Token tới API.

### 22.12. Đổi client-authentication-method tùy tiện

Nếu Authorization Server đã đăng ký `client_secret_basic`, không nên đổi sang `client_secret_post` hoặc `none` chỉ để thử ngẫu nhiên. Xác định contract và chọn đúng method, đặc biệt với private key JWT/mTLS.

## 23. Các tình huống thực tế

### Tình huống A — Secret bị đổi sau khi deploy

Job đang dùng secret V1; Authorization Server đã revoke V1 và chỉ chấp nhận V2. Token Endpoint trả `invalid_client`.

**Hướng xử lý:** kiểm tra secret version/mount của instance, rollout V2 an toàn, xác nhận authentication method, không log V1/V2 và không retry vô hạn.

### Tình huống B — Scope chỉ có trong staging

Ứng dụng xin `reports.export` ở production trong khi scope này chỉ được cấu hình ở staging. Token Endpoint trả `invalid_scope`.

**Hướng xử lý:** đồng bộ contract/policy theo quy trình; nếu production chưa cấp quyền thì chức năng export phải chờ phê duyệt, không dùng scope admin thay thế.

### Tình huống C — API trả 403 sau khi token được cấp

Client nhận token có `reports.read` rồi gọi `POST /reports` để tạo báo cáo. API yêu cầu `reports.write`.

**Hướng xử lý:** coi là vấn đề API authorization, không phải `invalid_client`. Nếu service thực sự cần ghi, phải xin quyền phù hợp qua policy review.

### Tình huống D — Dùng token của tenant sai

Backend gọi Token Endpoint tenant A, nhưng Reports API chỉ chấp nhận issuer tenant B. Token response thành công, API trả 401.

**Hướng xử lý:** sửa issuer/resource/audience mapping. Không thay scope trước khi xác định sai tenant.

### Tình huống E — Client Credentials token hết hạn giữa job

Một job kéo dài làm Access Token hết hạn; API trả 401.

**Hướng xử lý:** dùng manager để xin token mới bằng client credentials khi phù hợp, retry API có giới hạn và đảm bảo thao tác API idempotent hoặc có cơ chế tránh lặp tác dụng.

### Tình huống F — Token Endpoint tạm thời trả 503

Authorization Server bảo trì ngắn; một số worker cần xin token mới.

**Hướng xử lý:** backoff, jitter, circuit breaker và cảnh báo khi vượt ngưỡng. Không tạo hàng trăm yêu cầu cùng lúc hoặc chuyển sang endpoint không tin cậy.

### Tình huống G — Client xin quyền admin “cho tiện”

Một service đọc báo cáo được cấp `reports.admin` dù không có tính năng ghi/xóa.

**Hướng xử lý:** tách scope/registration, chỉ xin `reports.read`, thu hồi quyền admin dư thừa ở Authorization Server; không chỉ sửa code để không gọi endpoint nguy hiểm.

### Tình huống H — Một secret dùng chung cho nhiều jobs

Ba jobs cùng dùng client ID/secret có quyền đọc báo cáo, cập nhật users và xóa dữ liệu.

**Hướng xử lý:** phân tách service identities/credentials theo trust boundary, quản lý rotation và audit độc lập, áp dụng audience/scope giới hạn.

### Tình huống I — Manager cấp token nhưng một số node tiếp tục xin lại

Instance A đã có Access Token trong in-memory store; instance B không thấy và vẫn xin mới.

**Hướng xử lý:** xem thiết kế authorized client service, principal key và nhu cầu shared store/coordination; không coi đây là lỗi `invalid_scope`.

### Tình huống J — Provider thay đổi cấu trúc lỗi

Token Endpoint trả HTTP 400 với body tùy biến, không đúng format `OAuth2Error`. Ứng dụng phát sinh transport/parse exception thay vì `OAuth2AuthorizationException` có mã dễ đọc.

**Hướng xử lý:** phân loại theo tầng và contract provider, có fallback an toàn, không log body nguyên văn chứa credential hoặc thông tin nhạy cảm. Không bắt buộc mọi lỗi đều là một trong hai mã `invalid_client`/`invalid_scope`.

## 24. Tài liệu tham khảo

- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — OAuth2 Client Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — OAuth2AuthorizedClientProviderBuilder Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html
- OAuth 2.0 Authorization Framework (RFC 6749), Client Credentials Grant: https://www.rfc-editor.org/rfc/rfc6749#section-4.4
- OAuth 2.0 Authorization Framework (RFC 6749), Token Endpoint Error Response: https://www.rfc-editor.org/rfc/rfc6749#section-5.2
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Authorization Server Metadata (RFC 8414): https://www.rfc-editor.org/rfc/rfc8414
- Resource Indicators for OAuth 2.0 (RFC 8707): https://www.rfc-editor.org/rfc/rfc8707

## 25. Tổng kết: sửa đúng lớp lỗi và không vượt quá quyền được cấp

~~~text
Service gọi manager.authorize(...)
    |
    +-- Client Credentials token request
    |      |
    |      +-- invalid_client
    |      |      -> client authentication / secret / method / tenant
    |      |      -> dừng retry mù, sửa cấu hình
    |      |
    |      +-- invalid_scope
    |      |      -> scope không hợp lệ hoặc vượt grant policy
    |      |      -> không tự tăng quyền, đối chiếu allowlist
    |      |
    |      +-- thành công
    |             -> OAuth2AuthorizedClient
    |             -> Access Token + scope/audience được cấp
    |             -> lưu/tiếp tục gọi API đúng đích
    |
    +-- Resource Server response
           |
           +-- 401 invalid_token
           |      -> token validation, expiry, issuer/audience
           |
           +-- 403 insufficient_scope
           |      -> scope/authorization policy API
           |
           +-- 403 khác
                  -> tenant, ownership, resource policy, API contract
~~~

**Ba nguyên tắc quan trọng nhất:**

1. **`invalid_client` là vấn đề xác thực client tại Token Endpoint**, không phải yêu cầu thêm quyền; kiểm tra credentials, phương thức xác thực và provider/tenant.
2. **`invalid_scope` là vấn đề phạm vi được xin/cấp**, không phải lý do để tự động nâng scope; áp dụng least privilege và quy trình phê duyệt.
3. **Access Token được cấp thành công vẫn phải vượt qua kiểm tra của Resource Server** về issuer, audience, scope và các chính sách trên tài nguyên. Không nhầm `invalid_scope` khi xin token với `insufficient_scope` khi gọi API.

Với Spring Security, hãy đặt cấu hình Client Credentials tại **`ClientRegistration`**, điều phối cấp mới/tái sử dụng qua **`OAuth2AuthorizedClientManager`**, phân loại lỗi theo đúng tầng và giữ token/secret trong ranh giới backend an toàn. Cách tiếp cận này giúp dịch vụ machine-to-machine vận hành ổn định mà không đánh đổi quyền tối thiểu hoặc khả năng kiểm soát an ninh.
