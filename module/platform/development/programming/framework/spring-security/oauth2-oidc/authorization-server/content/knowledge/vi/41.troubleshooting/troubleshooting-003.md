# invalid_scope, unauthorized_client và unsupported_grant_type

Ba lỗi `invalid_scope`, `unauthorized_client` và `unsupported_grant_type` thường xuất hiện khi client gửi authorization request hoặc token request không phù hợp với chính sách đã đăng ký trên Spring Authorization Server. Chúng có thể cùng trả về HTTP 400, nhưng chỉ ra ba vấn đề khác nhau: quyền được yêu cầu không hợp lệ, client không được phép dùng grant type đó, hoặc server không hỗ trợ grant type được gửi đến token endpoint.

Bài học này thuộc module `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`, tập trung vào thiết kế và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Authorization Server. Việc chẩn đoán cần xem cả endpoint, loại request, `RegisteredClient`, scope, grant type và trạng thái authorization/consent. Không nên sửa lỗi bằng cách mở rộng quyền của client trước khi xác định điều kiện nào đang bị vi phạm.

## 1. Phân biệt ba lỗi theo hợp đồng OAuth2

| Error code | Ý nghĩa | Câu hỏi chẩn đoán đầu tiên |
|---|---|---|
| `invalid_scope` | Scope được yêu cầu không hợp lệ, không được hỗ trợ hoặc vượt quá quyền client được phép yêu cầu | Scope này có được đăng ký và được phép trong request/grant hiện tại không? |
| `unauthorized_client` | Client đã được nhận diện nhưng không được phép dùng grant type hoặc response type đang yêu cầu | Grant type này có nằm trong danh sách `authorizationGrantTypes` của client không? |
| `unsupported_grant_type` | Token endpoint không hỗ trợ giá trị `grant_type` được gửi | Request có gửi đúng grant type chuẩn và server đã đăng ký provider xử lý grant đó chưa? |

Ba lỗi trên khác với các lỗi thường gặp khác:

- `invalid_client`: client authentication thất bại, ví dụ sai client secret, sai phương thức xác thực hoặc client không được nhận diện.
- `invalid_grant`: credential của grant không hợp lệ, ví dụ authorization code hết hạn/đã dùng, redirect URI không khớp hoặc refresh token không còn hiệu lực.
- `invalid_request`: thiếu tham số bắt buộc, tham số trùng hoặc request sai định dạng.
- `access_denied`: người dùng hoặc chính sách authorization từ chối quyền truy cập.

Ở token endpoint, ba lỗi trong bài thường được trả dưới dạng OAuth2 error response với HTTP 400. `invalid_client` có quy tắc status code riêng tùy phương thức client authentication; vì vậy, không kết luận lỗi chỉ dựa vào status code. Hãy đọc trường `error` trong response body.

## 2. Xác định lỗi phát sinh ở endpoint nào

Spring Authorization Server thường có hai endpoint cần phân biệt:

| Endpoint | Tham số quyết định luồng | Vai trò |
|---|---|---|
| `/oauth2/authorize` | `response_type`, `client_id`, `scope`, `redirect_uri` | Bắt đầu authorization flow, xác thực request và có thể yêu cầu login/consent |
| `/oauth2/token` | `grant_type`, `client_id`, `scope`, grant credential | Đổi authorization code, refresh token hoặc cấp token theo grant đã đăng ký |

`response_type=code` là tham số của authorization endpoint. `grant_type=authorization_code` là tham số của token endpoint khi đổi code. Gửi `response_type` đến token endpoint hoặc gửi `grant_type` thay cho `response_type` ở authorization endpoint không tạo thành một request hợp lệ.

Trước khi điều tra cấu hình, ghi nhận tối thiểu:

1. Endpoint nhận request và HTTP method.
2. Giá trị `grant_type` hoặc `response_type` thực tế sau khi decode form.
3. Client ID đã được ẩn hoặc thay bằng định danh an toàn trong log.
4. Các scope được yêu cầu và scope đã đăng ký cho client.
5. Error code, error description đã được làm sạch và correlation ID.

Không ghi client secret, authorization code, access token, refresh token, PKCE verifier hoặc toàn bộ Authorization header vào log. Các giá trị đó không cần thiết để xác định ba lỗi này.

## 3. Chẩn đoán `invalid_scope`

`invalid_scope` có nghĩa là tập scope trong request không được chấp nhận theo chính sách của authorization server. Scope là các chuỗi phân biệt chữ hoa/chữ thường; một scope có trong client registration không có nghĩa mọi grant hoặc mọi người dùng đều tự động được cấp scope đó.

### 3.1. Kiểm tra scope đã đăng ký cho client

Spring Authorization Server lưu scope được phép trong `RegisteredClient`. Ví dụ một client service được đăng ký với hai scope:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.client.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient ordersClient = RegisteredClient.withId("orders-client-row")
        .clientId("orders-service")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .scope("orders.write")
        .build();
```

Với registration này, `orders.read` và `orders.write` là hai scope client có thể yêu cầu theo grant và các chính sách bổ sung. Nếu client gửi `orders.admin`, authorization server có thể trả `invalid_scope` vì scope đó chưa được đăng ký hoặc không được phép.

Đọc registration thực tế từ đúng repository đang được ứng dụng sử dụng:

```java
import java.util.Set;

RegisteredClient client = registeredClientRepository.findByClientId("orders-service");

if (client == null) {
    throw new IllegalStateException("Client registration was not found");
}

Set<String> registeredScopes = client.getScopes();
```

Nếu registration được lưu bằng JDBC, kiểm tra dữ liệu qua `JdbcRegisteredClientRepository` hoặc công cụ quản trị database đã được cấp quyền. Không chỉ xem file cấu hình hoặc dữ liệu seed: registration có thể đã được cập nhật trong database, còn cache hoặc node khác vẫn đang dùng bản cũ.

### 3.2. Kiểm tra cách truyền tham số scope

OAuth2 truyền scope dưới dạng danh sách các scope token được phân tách bằng dấu cách. Ví dụ:

```text
scope=orders.read%20orders.write
```

Không truyền danh sách bằng dấu phẩy (`orders.read,orders.write`) trừ khi ứng dụng có một giao thức tùy biến riêng. Khi gửi `application/x-www-form-urlencoded`, dấu cách cần được encode đúng. Tên scope cũng phải khớp chính xác với giá trị đăng ký; `Orders.Read` khác `orders.read`.

Ví dụ request client credentials:

```bash
curl --user orders-service:test-secret \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=orders.read" \
  https://auth.example.com/oauth2/token
```

Thử thay scope thành `orders.admin` để xác nhận test âm trả `invalid_scope`. Trong môi trường thật, dùng secret test được quản lý an toàn; không đặt secret production trực tiếp trong lịch sử shell hoặc tài liệu.

### 3.3. Phân biệt scope client và consent của người dùng

Trong Authorization Code flow, client có thể yêu cầu scope đã đăng ký nhưng người dùng vẫn phải consent nếu chính sách yêu cầu. Consent trả lời câu hỏi người dùng đã chấp thuận quyền nào; `RegisteredClient.getScopes()` trả lời câu hỏi client được phép yêu cầu quyền nào. Hai điều kiện này khác nhau.

Nếu scope không nằm trong registration, việc thêm scope vào consent hiện có không làm request trở nên hợp lệ. Nếu scope đã đăng ký nhưng consent chưa có, server có thể chuyển người dùng đến consent page hoặc từ chối theo chính sách ứng dụng. Hãy xác định request đã thất bại ở bước kiểm tra registration hay ở bước consent.

Kiểm tra consent theo đúng cặp client và principal. Consent của user A không thể dùng để suy ra user B đã chấp thuận cùng quyền. Khi test dùng database chung, dọn consent cũ để tránh kết quả phụ thuộc thứ tự chạy test.

### 3.4. Kiểm tra scope theo grant và chính sách ứng dụng

Một scope có thể được đăng ký cho client nhưng vẫn bị giới hạn bởi grant type, tenant, resource, người dùng hoặc policy tùy biến. Ví dụ, service client chỉ được cấp `orders.read` qua client credentials, còn `orders.write` cần một luồng có người dùng và consent. Trong trường hợp đó, không mở rộng danh sách scope toàn cục chỉ để làm cho một request service thành công.

Nếu ứng dụng dùng `OAuth2TokenCustomizer`, authorization consent tùy biến hoặc provider riêng, kiểm tra logic này có lọc scope hay thay đổi claims sau khi grant đã được xác thực không. Scope trong access token và authority được resource server ánh xạ cũng cần được kiểm tra riêng.

Một request token endpoint thành công nhưng gọi API nhận `403 Forbidden` thường là vấn đề authorization ở resource server, không phải `invalid_scope` của token endpoint. Hãy kiểm tra token có chứa scope/authority dự kiến và resource server có ánh xạ chúng thành `SCOPE_...` hoặc authority tùy biến đúng cách không.

## 4. Chẩn đoán `unauthorized_client`

`unauthorized_client` thường cho biết client được nhận diện nhưng không được phép dùng grant type hoặc response type đang yêu cầu. Kiểm tra `authorizationGrantTypes` của `RegisteredClient` trước khi xem token provider hoặc credential.

### 4.1. Grant type chưa được đăng ký

Ví dụ client chỉ được phép dùng client credentials:

```java
RegisteredClient serviceClient = RegisteredClient.withId("service-client-row")
        .clientId("billing-service")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("billing.read")
        .build();
```

Client này không được phép thực hiện Authorization Code grant hoặc Refresh Token grant chỉ vì token endpoint có hỗ trợ các loại grant đó. Nếu gửi `grant_type=authorization_code` hoặc `grant_type=refresh_token`, server có thể trả `unauthorized_client` khi grant được nhận diện nhưng không được đăng ký cho client.

Nếu nghiệp vụ yêu cầu Authorization Code và Refresh Token, registration phải khai báo cả hai:

```java
RegisteredClient webClient = RegisteredClient.withId("web-client-row")
        .clientId("web-portal")
        .clientSecret(passwordEncoder.encode("test-secret"))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://portal.example.com/login/oauth2/code/portal")
        .scope("openid")
        .scope("profile")
        .build();
```

Public client dùng PKCE thường đăng ký `ClientAuthenticationMethod.NONE` và không có client secret. Confidential client cần dùng phương thức xác thực client phù hợp với registration. Đừng thay phương thức xác thực để chữa lỗi grant type; lỗi xác thực client thường được báo là `invalid_client`.

### 4.2. Kiểm tra authorization request và response type

Ở `/oauth2/authorize`, `response_type=code` yêu cầu Authorization Code flow. Nếu client không được cấu hình để dùng authorization code, server có thể trả `unauthorized_client` hoặc lỗi giao thức phù hợp theo ngữ cảnh.

Hãy kiểm tra:

- Client ID có trỏ đến đúng `RegisteredClient` không.
- Registration có `AuthorizationGrantType.AUTHORIZATION_CODE` không.
- Redirect URI có khớp chính xác một URI đã đăng ký không.
- Client settings có yêu cầu PKCE hoặc consent không và request có đáp ứng không.
- Ứng dụng có tùy biến authorization endpoint/provider làm thay đổi quyết định không.

Không nhầm `response_type=code` với `grant_type=authorization_code`. Request authorization bắt đầu bằng response type; grant type chỉ xuất hiện khi client đổi code tại token endpoint.

### 4.3. Kiểm tra Refresh Token grant

Một client dùng Authorization Code có thể được cấu hình để nhận refresh token. Nếu ứng dụng muốn client dùng refresh token, đăng ký `AuthorizationGrantType.REFRESH_TOKEN` và kiểm tra chính sách phát hành refresh token, chẳng hạn scope `offline_access` trong OIDC khi ứng dụng yêu cầu, consent và `TokenSettings`.

Nếu client nhận access token nhưng không nhận refresh token, trước tiên xác định server có chính sách phát hành refresh token cho client/flow đó không. Không gửi `grant_type=refresh_token` chỉ dựa vào giả định rằng mọi authorization code flow đều tự động cấp refresh token.

## 5. Chẩn đoán `unsupported_grant_type`

`unsupported_grant_type` cho biết token endpoint không hỗ trợ giá trị `grant_type` được gửi. Lỗi này thường phát sinh trước khi server đánh giá client có được phép dùng grant đó hay không.

### 5.1. Kiểm tra tên grant type và endpoint

Các giá trị chuẩn thường gặp:

| Grant | Giá trị `grant_type` |
|---|---|
| Authorization Code | `authorization_code` |
| Client Credentials | `client_credentials` |
| Refresh Token | `refresh_token` |
| Device Authorization Grant | `urn:ietf:params:oauth:grant-type:device_code` |
| Token Exchange | `urn:ietf:params:oauth:grant-type:token-exchange` |

Các grant mở rộng dùng định danh URI theo đặc tả tương ứng. Không tự rút gọn thành `device_code` hoặc `token_exchange` nếu giao thức yêu cầu URI đầy đủ.

Kiểm tra request có gửi form parameter `grant_type` tại `/oauth2/token`, không phải query parameter sai vị trí hoặc JSON body không được endpoint hỗ trợ. Xác nhận đúng URL token endpoint từ discovery metadata thay vì suy ra URL theo thói quen.

### 5.2. Phân biệt grant không được hỗ trợ và grant không được phép

| Tình huống | Lỗi thường mong đợi |
|---|---|
| `grant_type` bị viết sai hoặc server không có converter/provider cho grant đó | `unsupported_grant_type` |
| Server có hỗ trợ `client_credentials`, nhưng client hiện tại không đăng ký grant này | `unauthorized_client` |
| Client được phép dùng grant, nhưng thiếu/sai credential của grant | Thường là `invalid_request` hoặc `invalid_grant`, tùy tham số và loại grant |
| Client authentication thất bại | `invalid_client` |

Ví dụ: nếu server đã cấu hình client credentials nhưng client chỉ đăng ký authorization code, thêm grant type vào registration khi nghiệp vụ cho phép. Nếu server chưa triển khai một custom grant, thêm grant vào `RegisteredClient` một mình không đủ; token endpoint vẫn cần thành phần chuyển request và provider xử lý grant.

### 5.3. Kiểm tra custom grant

Spring Authorization Server hỗ trợ mở rộng token endpoint bằng `AuthenticationConverter` và `AuthenticationProvider` phù hợp. Một custom grant cần:

1. Định nghĩa grant type theo định danh URI ổn định.
2. Đăng ký grant type đó cho từng `RegisteredClient` được phép sử dụng.
3. Cung cấp converter để chuyển HTTP request thành đối tượng `Authentication` của grant.
4. Cung cấp provider để xác thực client, kiểm tra quyền, xác minh dữ liệu grant và phát hành token.
5. Đăng ký converter/provider vào token endpoint của đúng `SecurityFilterChain`.
6. Kiểm thử grant hợp lệ, client không được phép, dữ liệu grant sai và grant type không được hỗ trợ.

Khi thêm custom grant, kiểm tra converter có nhận đúng `grant_type` và provider có được thêm vào danh sách provider của token endpoint hay không. Chỉ thêm `.authorizationGrantType(customGrantType)` vào `RegisteredClient` mà thiếu converter/provider thường dẫn đến `unsupported_grant_type`.

API cấu hình DSL và chữ ký constructor có thể khác giữa các phiên bản Spring Authorization Server. Dùng đúng tài liệu của phiên bản dependency đang cài để đăng ký `accessTokenRequestConverter` và `authenticationProvider`; tránh sao chép ví dụ của phiên bản khác mà không đối chiếu.

## 6. Quy trình điều tra theo thứ tự

Thực hiện theo thứ tự sau để tách lỗi giao thức khỏi lỗi registration:

1. **Xác định endpoint.** `/oauth2/authorize` hay `/oauth2/token`? Kiểm tra method và content type.
2. **Đọc error body.** Lấy `error` và correlation ID; không suy luận chỉ từ HTTP status.
3. **Xác thực client.** Kiểm tra client ID, authentication method và credential. Nếu nhận `invalid_client`, giải quyết bước này trước.
4. **Kiểm tra grant.** Đọc `RegisteredClient.getAuthorizationGrantTypes()` và so với `response_type`/`grant_type` đang dùng.
5. **Kiểm tra scope.** So sánh scope request với `RegisteredClient.getScopes()` và policy/consent tùy biến.
6. **Kiểm tra provider.** Với grant chuẩn, xác nhận token endpoint có hỗ trợ; với custom grant, xác nhận converter và provider đã đăng ký.
7. **Kiểm tra dữ liệu lưu trữ/cache.** So sánh registration ở các instance và kiểm tra cache có dữ liệu cũ không.
8. **Chạy lại test tối thiểu.** Chỉ thay một điều kiện mỗi lần và xác nhận error code chuyển đúng theo mong đợi.

Một ví dụ log chẩn đoán an toàn:

```text
event=oauth2_token_error
request_id=8f1c...
client_id=orders-service
grant_type=client_credentials
requested_scopes=[orders.read, orders.admin]
registered_grants=[client_credentials]
registered_scopes=[orders.read, orders.write]
oauth_error=invalid_scope
```

Đây là log minh họa đã loại bỏ credential và token. Không ghi toàn bộ form body hoặc header xác thực.

## 7. Kiểm thử lỗi bằng MockMvc

Test token endpoint nên chạy với `RegisteredClientRepository`, `OAuth2AuthorizationService`, security filter chain và provider thật. Có thể dùng MockMvc để xác nhận error code trả về.

Ví dụ client credentials yêu cầu scope không được đăng ký:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.http.MediaType;

mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("orders-service", "test-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "client_credentials")
        .param("scope", "orders.admin"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("invalid_scope"));
```

Để kiểm tra `unauthorized_client`, dùng client đã xác thực thành công nhưng không đăng ký grant được gửi:

```java
mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("billing-service", "test-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "refresh_token")
        .param("refresh_token", "test-refresh-token"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("unauthorized_client"));
```

Test này cần client `billing-service` đã được đăng ký và chỉ cho phép `client_credentials`. Đừng để client authentication thất bại, vì khi đó test chỉ nhận `invalid_client`.

Để kiểm tra `unsupported_grant_type`, gửi một grant type mà server không hỗ trợ và client không có converter/provider tương ứng:

```java
mockMvc.perform(post("/oauth2/token")
        .with(httpBasic("orders-service", "test-secret"))
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "urn:example:params:oauth:grant-type:unknown"))
    .andExpect(status().isBadRequest())
    .andExpect(jsonPath("$.error").value("unsupported_grant_type"));
```

Mỗi test âm cần có một test dương tương ứng: scope hợp lệ được cấp, client dùng grant đã đăng ký thành công và custom/standard grant được hỗ trợ có thể hoàn tất. Điều đó chứng minh test thất bại do đúng điều kiện đang nhắm đến.

## 8. Ma trận lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `invalid_scope` với client credentials | Scope không nằm trong `RegisteredClient.getScopes()` | Đăng ký scope đúng nếu được phép hoặc sửa request về scope hợp lệ |
| `invalid_scope` dù scope có trong file seed | Database hoặc cache còn registration cũ | Đọc registration thực tế từ repository và kiểm tra mọi instance |
| `invalid_scope` trong authorization request | Scope sai chính tả, không được hỗ trợ hoặc vượt policy | Kiểm tra scope list, consent và policy theo user/tenant |
| Token được cấp nhưng API trả 403 | Resource server không có authority tương ứng hoặc scope bị downscope | Kiểm tra claim `scope` và mapping authority ở resource server |
| `unauthorized_client` khi dùng authorization code | Client không đăng ký `authorization_code` hoặc response type không được phép | Kiểm tra grant types và client settings |
| `unauthorized_client` khi refresh | Client không đăng ký `refresh_token` hoặc refresh policy không cho phép | Kiểm tra registration, token issuance và refresh policy |
| `unsupported_grant_type` với grant chuẩn | Sai giá trị `grant_type`, sai endpoint hoặc cấu hình server không hỗ trợ | Đối chiếu protocol value và discovery metadata |
| `unsupported_grant_type` với custom grant | Thiếu converter/provider hoặc provider không được đăng ký vào token endpoint | Kiểm tra extension wiring và SecurityFilterChain |
| Lỗi chỉ xảy ra trên một node | Cấu hình hoặc cache `RegisteredClient` giữa các node không đồng nhất | Đồng bộ cấu hình, cache invalidation và repository dùng chung |
| Không phân biệt được lỗi do status 400 | Chỉ kiểm tra HTTP status mà không đọc OAuth2 error body | Assert `$.error` và lưu correlation ID |

## 9. Checklist trước khi phát hành

- [ ] Client ID và phương thức client authentication được xác minh độc lập.
- [ ] `RegisteredClient.authorizationGrantTypes` chỉ chứa các grant client thực sự cần.
- [ ] `RegisteredClient.scopes` phản ánh đúng quyền client được phép yêu cầu.
- [ ] Scope request dùng dấu cách phân tách, đúng chữ hoa/thường và đúng form encoding.
- [ ] Consent và policy người dùng được kiểm tra riêng với scope registration.
- [ ] Authorization Code flow dùng `response_type=code`; token exchange dùng `grant_type=authorization_code`.
- [ ] Refresh token chỉ được dùng khi client và chính sách phát hành cho phép.
- [ ] Grant type chuẩn được gửi đúng giá trị giao thức tại token endpoint.
- [ ] Custom grant có converter, provider và registration tương ứng.
- [ ] Registration và cache nhất quán giữa các instance.
- [ ] Test xác nhận cả lỗi âm lẫn luồng dương tương ứng.
- [ ] Log có correlation ID và error code nhưng không chứa secret, code hoặc token.

Khi phân biệt đúng scope không hợp lệ, grant client không được phép và grant server chưa hỗ trợ, việc khắc phục trở nên rõ ràng: sửa scope hoặc policy, điều chỉnh registration của đúng client, hoặc triển khai đầy đủ grant provider. Giữ ba điều kiện này riêng biệt giúp Authorization Server chỉ cấp quyền mà client thực sự được phép sử dụng.
