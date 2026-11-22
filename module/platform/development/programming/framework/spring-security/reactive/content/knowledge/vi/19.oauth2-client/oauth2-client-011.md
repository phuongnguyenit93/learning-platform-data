# Xử lý token bị từ chối, xóa OAuth2AuthorizedClient và tránh vòng lặp thử lại trong Spring Security reactive

## 1. Mục tiêu

Một ứng dụng **Spring WebFlux** dùng **OAuth2 Client** gọi resource server bằng `WebClient`. Access token từng hoạt động bình thường, nhưng một thời điểm API downstream trả **HTTP 401** với Bearer error `invalid_token`, hoặc token endpoint từ chối refresh token bằng OAuth2 error `invalid_grant`. Nếu ứng dụng cứ giữ nguyên `OAuth2AuthorizedClient` trong cache rồi dùng lại cùng token, mỗi request sẽ tiếp tục 401. Nếu thêm `retryWhen(Retry.indefinitely())` hoặc tự làm vòng lặp refresh → gọi API → 401 → refresh, hệ thống có thể gây bão request tới Authorization Server và Resource Server.

Bài này đi sâu vào ba quyết định **khác nhau nhưng liên quan**:

1. **Phân loại lỗi:** 401/403 từ resource server khác lỗi `invalid_grant` từ token endpoint và khác outage 5xx/timeout.
2. **Quản lý trạng thái OAuth2AuthorizedClient:** dùng đúng `ReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientService` hoặc `ServerOAuth2AuthorizedClientRepository`, có thể xóa thông tin token không còn dùng được.
3. **Giới hạn retry:** biết khi nào **không retry**, khi nào cấp lại token ở **request tiếp theo**, khi nào retry tối đa có backoff cho một thao tác GET idempotent, và khi nào cần re-login hoặc operator can thiệp.

Bạn sẽ học API reactive **Spring Security 7.1**, phân biệt hai constructor của `ServerOAuth2AuthorizedClientExchangeFilterFunction`, dùng failure handler có sẵn, xem một ứng dụng Spring Boot 4.1.x/Java 17+ minh họa việc loại bỏ client token bị từ chối, và kiểm thử cách tránh retry loop.

> **Nguyên tắc:** xóa `OAuth2AuthorizedClient` là hành động **xóa trạng thái cấp quyền/token được lưu tại client**, không đồng nghĩa server xác thực đã thu hồi token ở mọi nơi; và **không tự bảo đảm một user có quyền mới**. Phát sinh 403 do thiếu scope/role thường phải xử lý policy, không thể sửa chỉ bằng refresh vô hạn.

## 2. Bốn thực thể đừng nhầm

| Thành phần | Chức năng | Điều không nên suy ra |
| --- | --- | --- |
| `ClientRegistration` | Cấu hình client-id, grant type, token-uri, scopes, provider | Không phải access token đã cấp |
| `OAuth2AuthorizedClient` | Gắn `ClientRegistration` với principal, access token và optional refresh token | Không phải authenticated `SecurityContext` của user |
| `ReactiveOAuth2AuthorizedClientManager` | Authorize/re-authorize và điều phối provider, persistence, success/failure handler | Không tự retry vô hạn resource request |
| `ReactiveOAuth2AuthorizedClientService` | Lưu/load/xóa authorized client ở application/service layer | Không revoke refresh token từ IdP khi chỉ gọi remove |
| `ServerOAuth2AuthorizedClientRepository` | Lưu/load/xóa authorized client trong bối cảnh `ServerWebExchange`/web request | Không dùng interchangeably với service mà thiếu principal/exchange |
| `ReactiveOAuth2AuthorizedClientProvider` | Thực hiện grant như `authorization_code`, `refresh_token`, `client_credentials` | Không xử lý HTTP status downstream thay `WebClient` |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Gắn Bearer token vào request `WebClient` và forward một số failure tới handler | Không mặc định cùng hành vi giữa hai constructor |
| `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` | Xóa authorized client với các **OAuth2 error code** đã được cấu hình | Không xóa mọi 403 chỉ vì status là 403 |

**Phân biệt hai chiều:** token được cấp từ **Authorization Server / token endpoint**, còn token được trình lên **Resource Server / API downstream**. Một lỗi xuất hiện lúc refresh token và một lỗi xuất hiện lúc API sử dụng access token đi theo những đường xử lý khác nhau.

## 3. Luồng lỗi OAuth2 Client trong WebFlux

~~~text
         Reactor request / background job
                      |
                      v
          ReactiveOAuth2AuthorizedClientManager
                      |
           load OAuth2AuthorizedClient?
                      |
        +-------------+--------------+
        |                            |
        v                            v
     không có                  đã có token
        |                            |
 token endpoint                 access token sắp
 lấy access token               hết hạn? có refresh?
        |                            |
        |                 +----------+----------+
        |                 |                     |
        |            refresh thành công     invalid_grant
        |                 |                     |
        |                 |             failure handler xóa
        |                 |             authorized client cũ
        v                 v                     |
      WebClient gắn Bearer token                STOP
                      |
              Resource Server
                      |
          +-----------+-----------+
          |                       |
         2xx                 401 / 403
          |                       |
          v                       v
       kết quả              phân loại response
                                  |
              +-------------------+-------------------+
              |                   |                   |
       invalid_token        insufficient_scope    lỗi khác
              |                   |                   |
       remove token cũ      không refresh loop     xử lý riêng
       khi handler được       báo thiếu quyền        có thể retry 5xx
       cấu hình phù hợp                             có giới hạn
              |
           STOP request hiện tại
              |
   Request hợp lệ tiếp theo có thể xin
   token mới / reauthorization theo grant
~~~

Sơ đồ thể hiện **quyết định khuyến nghị**, không có nghĩa mọi phiên bản hoặc mọi constructor tự làm đủ từng nhánh. Hành vi cụ thể phụ thuộc manager/filter, OAuth2 error code và repository/service bạn dùng.

### 3.1. Khi token **chưa hết hạn** vẫn bị 401

Access token có `expiresAt` trong `OAuth2AuthorizedClient` nhưng resource server có thể từ chối nó sớm vì:

- Token bị revoke hoặc account/app permission thay đổi.
- Resource server dùng issuer/audience khác hoặc chưa nhận JWK rotation.
- Resource server không hỗ trợ token type/scope được cấp.
- Token được ký đúng nhưng không được API cụ thể chấp nhận.
- Đồng hồ, cache, cluster hoặc gateway cấu hình sai.
- Token đã bị thay đổi/hỏng trong quá trình truyền.

**Đừng chỉ nhìn expiresAt để kết luận token còn dùng được.** Resource server mới là nơi kiểm tra token khi sử dụng; một 401 Bearer `invalid_token` có thể cho thấy token đang lưu không nên tiếp tục gửi.

### 3.2. HTTP status chỉ là đầu mối, chưa phải toàn bộ lỗi

Ví dụ lỗi chuẩn từ resource server:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Còn trường hợp thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.read"
~~~

Đây là **mẫu HTTP minh họa theo RFC 6750**. 401 còn có thể do authentication gateway thiếu header; 403 còn có thể do authorization business policy dù token hợp lệ. **Không xóa mọi authorized client khi thấy status 401 hoặc 403**, rồi mong xin token mới giải quyết được role/scope mismatch.

### 3.3. invalid_grant xuất hiện ở đâu?

Khi một refresh token đã hết hạn, bị revoke, sai rotation hoặc bị gửi trùng, **token endpoint** có thể trả:

~~~json
{
  "error": "invalid_grant"
}
~~~

`invalid_grant` là **OAuth2 token endpoint error**, khác `invalid_token` trong `WWW-Authenticate` của Resource Server. Với manager mặc định, lỗi refresh `invalid_grant` thường khiến client được lưu bị xóa bởi `ReactiveOAuth2AuthorizationFailureHandler`. Nhưng xóa token không bảo đảm flow tự đăng nhập lại thành công: với `authorization_code` cần tương tác user/consent; với `client_credentials` có thể lấy token mới ở request sau nếu client credentials/config còn hợp lệ.

## 4. Chọn manager phù hợp với ngữ cảnh

Spring Security reactive có hai manager thường gặp:

| Ngữ cảnh | Manager | Storage chính |
| --- | --- | --- |
| Request WebFlux có `ServerWebExchange` và user đang login | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| Background job/scheduled task/service-to-service không có web request | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |

**Không** dùng `DefaultOAuth2AuthorizedClientManager` (Servlet/non-reactive) hoặc `OAuth2AuthorizedClientService` (blocking) khi đang thiết kế WebFlux reactive. Phải phân biệt package và interface có chữ `Reactive`.

### 4.1. DefaultReactiveOAuth2AuthorizedClientManager

Ví dụ cấu hình một manager cho web request, trong Spring configuration:

~~~java
@Bean
ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository repository) {

    ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .authorizationCode()
                    .refreshToken()
                    .clientCredentials()
                    .build();

    DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                    registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Đây là **method bean snippet**, cần Spring Security imports và đúng `ServerWebExchange` cho request thực tế. Javadoc của manager cho biết nó mặc định lưu client khi authorize thành công, và khi refresh thất bại do `invalid_grant`, có thể xóa authorized client qua failure handler.

### 4.2. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

Với job/service:

~~~java
@Bean
ReactiveOAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService clientService) {

    var provider = ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager = new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, clientService);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Với `client_credentials`, principal là **service identity** ổn định, không phải user browser. Trong phần thực hành sẽ dùng principal `"reports-backend"`, nên khi xóa client phải dùng **đúng registrationId + principalName** này.

**Điểm quan trọng:** thay provider bằng mỗi `.clientCredentials()` là lựa chọn phù hợp demo; nó không kích hoạt refresh token grant. Một ứng dụng browser `authorization_code` cần cấu hình đúng provider chain và account lifecycle riêng; không copy y nguyên client_credentials provider rồi mong user login tự refresh.

## 5. Hành vi mặc định của manager khi refresh thất bại

Theo Spring Security reactive OAuth2 Client reference:

- Khi authorize/re-authorize thành công, manager gọi `ReactiveOAuth2AuthorizationSuccessHandler`, thường **lưu authorized client mới**.
- Khi authorize/re-authorize thất bại, manager gọi `ReactiveOAuth2AuthorizationFailureHandler`.
- Với `invalid_grant`, mặc định của `DefaultReactiveOAuth2AuthorizedClientManager` và `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` có thể **xóa authorized client đã lưu** qua `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler`.

Nhưng:

1. Đây là **lỗi từ authorization/token endpoint**, không phải tự động xử lý mọi HTTP 401 từ API downstream.
2. Failure handler chỉ xóa **đúng key client registration/principal**, không xóa global user session hoặc mọi token ở IdP.
3. Mặc định error code nào kích hoạt xóa phụ thuộc handler/phiên bản. Handler `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` chỉ remove khi `OAuth2Error.getErrorCode()` thuộc tập configured codes.
4. Xóa client không đồng nghĩa retry request đang lỗi ngay lập tức.
5. Với refresh token đã dùng và bị rotation, concurrent refresh có thể gặp race; xem phần concurrency.

### 5.1. Khi thiếu refresh token

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` trả empty publisher khi không thể refresh theo grant/context (ví dụ không có refresh token hoặc token chưa đến ngưỡng hết hạn). Manager có thể trả lại authorized client cũ nếu chưa cần refresh. **Không** ép refresh trong vòng lặp khi token thiếu/không còn hợp lệ.

### 5.2. Khi client_credentials bị invalid_client

`invalid_client` từ Authorization Server có thể là secret sai/hết hạn, client bị vô hiệu hoặc policy thay đổi. Xóa cached OAuth2AuthorizedClient và liên tục xin lại bằng **cùng secret sai** chỉ tạo request storm. Cần báo lỗi cấu hình/credential tới hệ thống quan sát, dừng retry không có giới hạn, và có hành động vận hành như rotate secret.

## 6. WebClient OAuth2 filter: hai constructor, hai hành vi

`ServerOAuth2AuthorizedClientExchangeFilterFunction` là integration quan trọng cho `WebClient`. Nó tìm `OAuth2AuthorizedClient`, có thể authorize/refresh, rồi gắn Bearer token vào downstream HTTP request.

### 6.1. Constructor dùng repository: có failure handler mặc định

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                clientRegistrations, authorizedClientRepository);

WebClient webClient = WebClient.builder()
        .filter(oauth2)
        .build();
~~~

Đây là snippet khi có `ReactiveClientRegistrationRepository` và `ServerOAuth2AuthorizedClientRepository`. Theo Javadoc Spring Security **7.1**, constructor `(registrations, repository)` **tự cấu hình** `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` để xử lý các auth/authz errors được chuyển từ resource server và **có OAuth2 error code thuộc danh sách remove**.

Trong request service:

~~~java
webClient.get()
        .uri("https://resource.example.com/api/me")
        .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction
                        .clientRegistrationId("corp"))
        .retrieve()
        .bodyToMono(String.class);
~~~

Đây là snippet, `corp` là client registration đã cấu hình và tài nguyên phải là **URL/host đáng tin**, không được truyền host tùy ý từ user rồi làm lộ Bearer token.

### 6.2. Constructor dùng manager: **không tự đăng ký resource-server failure handler**

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
~~~

Javadoc Spring Security 7.1 nêu rõ với constructor này, lỗi HTTP **401/403 từ resource server** không tự forward tới `ReactiveOAuth2AuthorizationFailureHandler`. Dù bản thân manager có handler cho `invalid_grant` khi refresh, điều đó **không** có nghĩa HTTP 401 downstream tự xóa authorized client.

Cần gắn handler phù hợp nếu muốn OAuth filter loại token đã bị từ chối:

~~~java
RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler
        remover = new RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler(
                (registrationId, principal, attributes) ->
                        authorizedClientService.removeAuthorizedClient(
                                registrationId, principal.getName()));

oauth2.setAuthorizationFailureHandler(remover);
~~~

Đây là snippet dùng **service-backed store**; `authorizedClientService` là `ReactiveOAuth2AuthorizedClientService` tương ứng với manager, không phải store khác. Lambda signature được Javadoc xác nhận:

~~~java
Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        Map<String, Object> attributes);
~~~

`onAuthorizationFailure(...)` của handler nhận `OAuth2AuthorizationException`, principal và attributes. Handler kiểm **OAuth2 error code** và chỉ gọi remover nếu code thuộc tập đã cấu hình; không phải mọi 403 đều bị xóa.

**Ranh giới:** handler gắn lên filter xử lý lỗi **khi resource server trả 401/403**, còn manager failure handler xử lý lỗi **khi authorize/re-authorize**. Có thể cần cả hai để tránh stale token. Nếu tự thay success/failure handler của manager bằng một implementation riêng, phải bảo toàn hành vi persistence/removal cần thiết, không tự nhiên “mất refresh” mà không biết.

### 6.3. Cảnh báo setDefaultOAuth2AuthorizedClient(true)

Filter có `setDefaultOAuth2AuthorizedClient(true)`: nó có thể lấy client mặc định từ current Authentication và gắn access token vào requests. Javadoc khuyến cáo thận trọng vì **nhiều HTTP requests** có thể mang token nếu client được resolve. Đừng bật trên một WebClient dùng chung có URI do user quyết định, dễ rò Bearer token sang host ngoài danh sách.

Ưu tiên:

- `clientRegistrationId("known-registration")` tường minh.
- Fixed, allowlisted resource server base URL.
- Phân quyền riêng khi proxy user OAuth2 token, không mặc nhiên dùng token user cho API ngoài.
- Không log `Authorization` header, access/refresh token hoặc toàn bộ response body lỗi chứa thông tin bí mật.

## 7. API xóa OAuth2AuthorizedClient chính xác

### 7.1. Trong service/background context

`ReactiveOAuth2AuthorizedClientService` có:

~~~java
Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        String principalName);
~~~

Ví dụ:

~~~java
return authorizedClientService.removeAuthorizedClient(
        "downstream", "reports-backend");
~~~

Đây là snippet **trong method trả Mono<Void>**. **Phải return hoặc compose publisher** để removal thực thi; không gọi method rồi bỏ qua publisher, không tự `block()`.

Khóa `registrationId + principalName` phải trùng với key được manager dùng khi save/load. Xóa sai principal có thể báo hoàn tất nhưng client stale thật sự vẫn còn ở key khác.

### 7.2. Trong ServerWebExchange/repository context

`ServerOAuth2AuthorizedClientRepository` sử dụng:

~~~java
Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        ServerWebExchange exchange);
~~~

Snipppet gọi:

~~~java
return authorizedClientRepository.removeAuthorizedClient(
        "corp", authentication, exchange);
~~~

Dùng service hay repository tùy nơi client được lưu. Không nên có hai kho độc lập mà manager load từ A còn failure handler xóa ở B: hành động xóa “thành công” nhưng request sau vẫn thấy token cũ.

### 7.3. Xóa client không phải thu hồi token ở IdP

Việc xóa record local:

- Không gọi OAuth2 revocation endpoint theo mặc định.
- Không đảm bảo access token ở resource server đã hết hiệu lực.
- Không xóa mọi WebSession/browser cookie.
- Không xóa ClientRegistration/secret.
- Không sửa scope, user role hay client policy ở IdP.

Nếu cần **revocation thực sự**, phải gọi revocation endpoint theo RFC 7009 khi provider hỗ trợ và được phép, hoặc dùng policy quản trị token riêng. **Không tự coi local remove là logout toàn cục**.

## 8. Phân loại lỗi và quyết định có retry không

| Nguồn lỗi | Ví dụ | Cleanup | Retry? |
| --- | --- | --- | --- |
| Token endpoint | `invalid_grant` khi refresh token | Manager mặc định có thể xóa authorized client | **Không** lặp lại refresh bằng token cũ; cần re-login/new grant |
| Token endpoint | `invalid_client` | Điều tra client-id/secret | Không retry vô hạn bằng cấu hình sai |
| Resource server | 401 + Bearer `invalid_token` | Có thể xóa cached client qua configured failure handler | **Không** replay request đang lỗi theo mặc định |
| Resource server | 401 thiếu challenge hoặc do gateway | Điều tra auth scheme, proxy/header | Không xóa bừa/không retry mù |
| Resource server | 403 `insufficient_scope` | Giữ token trừ khi policy riêng | Không refresh loop; cần scope/consent/quyền |
| Resource server | 403 business authorization | Không coi token hỏng | Không retry để “đổi role” |
| Network timeout/502/503/504 | Sự cố tạm thời | Không xóa token chỉ vì gateway lỗi | Có thể **một lần** với backoff cho GET idempotent, nếu budget cho phép |
| 429 | Rate limit | Không xóa token | Chỉ retry theo Retry-After, giới hạn và backpressure |
| 400 payload invalid | Lỗi input | Không xóa token | Không retry tự động |
| POST thanh toán/ghi dữ liệu | Timeout nhưng server có thể đã xử lý | Không xóa token vì timeout | Không replay nếu thiếu idempotency key/transaction model |

**Điểm quyết định:** một `retryWhen` ở WebClient thường **resubscribe cả pipeline**, có thể gọi lại manager, token endpoint và API. Nếu lỗi luôn xảy ra, retry không giới hạn trở thành **vòng lặp cấp token và bắn request**.

### 8.1. Tại sao 403 không phải “token hết hạn”?

Một access token hợp lệ nhưng chỉ có scope `reports.read` sẽ không được phép gọi API đòi `reports.admin`. Refresh token thường cấp lại **scope đã được phép**, không tự thêm role mới. Một vòng lặp refresh → 403 sẽ lặp vô ích, tốn quota và làm khó log.

### 8.2. Nguyên tắc retry an toàn

1. Mặc định **không retry 401/403**.
2. Với `invalid_token`, xóa cached authorized client theo error code; **để request tiếp theo** giải quyết acquisition/reauthorization.
3. Với `invalid_grant`, dừng flow hiện tại; yêu cầu re-login hoặc tạo grant mới khi hợp đồng cho phép.
4. Chỉ retry lỗi network/transient **có giới hạn**, có exponential backoff + jitter, timeout, tổng retry budget.
5. Chỉ replay thao tác idempotent hoặc có idempotency key/replay-safe contract; GET không được có side effect.
6. Không gọi `retryWhen(Retry.indefinitely())` trên request mang token.
7. Không retry lồng nhau ở WebClient + API gateway + circuit breaker mà không tính tổng số attempts.
8. Có circuit breaker/rate limiting, đặc biệt khi IdP/token endpoint lỗi.
9. Nếu retry sau khi cleanup, cần refresh/acquire trên phiên hợp lệ, tránh dùng lại client stale được giữ trong biến.
10. Quan sát metric theo error code, registrationId, upstream host đã cho phép, **không** log token.

### 8.3. Một quyết định “retry tối đa một lần” không đồng nghĩa “luôn retry”

Giả sử request GET tới downstream nhận HTTP 503. Sau một backoff ngắn, có thể thử một lần nữa nếu timeout budget còn. Nhưng nếu GET trả 401 `invalid_token` hoặc 403 `insufficient_scope`, phải dừng và xử lý đúng nguyên nhân. Nếu request là POST không có idempotency key, timeout có thể xảy ra **sau khi downstream đã commit side effect**; retry có thể tạo giao dịch kép.

## 9. Demo Java 17 thuần: chính sách retry có thể chạy độc lập

Trước khi liên kết OAuth2 thật, chạy một lớp Java đơn giản để chứng minh bảng quyết định **không retry authentication/authorization failure**.

Tạo file `RetryPolicyDemo.java`:

~~~java
public final class RetryPolicyDemo {

    enum Decision {
        REMOVE_AND_STOP,
        STOP_PERMISSION_DENIED,
        RETRY_ONCE_WITH_BACKOFF,
        STOP
    }

    private RetryPolicyDemo() {
    }

    static Decision decide(int status, String oauthError,
            boolean idempotent, int previousRetries) {

        if (status == 401 && "invalid_token".equals(oauthError)) {
            return Decision.REMOVE_AND_STOP;
        }
        if (status == 403 &&
                "insufficient_scope".equals(oauthError)) {
            return Decision.STOP_PERMISSION_DENIED;
        }
        if ((status == 502 || status == 503 || status == 504)
                && idempotent && previousRetries == 0) {
            return Decision.RETRY_ONCE_WITH_BACKOFF;
        }
        return Decision.STOP;
    }

    public static void main(String[] args) {
        System.out.println("invalid_token=" +
                decide(401, "invalid_token", true, 0));
        System.out.println("scope=" +
                decide(403, "insufficient_scope", true, 0));
        System.out.println("transient_get=" +
                decide(503, null, true, 0));
        System.out.println("second_attempt=" +
                decide(503, null, true, 1));
        System.out.println("post_timeout=" +
                decide(503, null, false, 0));
        System.out.println("unknown_401=" +
                decide(401, null, true, 0));
    }
}
~~~

Chạy độc lập với JDK 17+:

~~~bash
javac RetryPolicyDemo.java
java RetryPolicyDemo
~~~

**Stdout xác định:**

~~~text
invalid_token=REMOVE_AND_STOP
scope=STOP_PERMISSION_DENIED
transient_get=RETRY_ONCE_WITH_BACKOFF
second_attempt=STOP
post_timeout=STOP
unknown_401=STOP
~~~

Đây là **pure Java policy example**; nó không tự gọi IdP hoặc xóa repository. Nó mã hóa một điểm kiểm thử: **số retry không phụ thuộc việc token lỗi có lặp nhiều lần**, và 401/403 không được coi là lỗi transient. Trong ứng dụng thực cần thêm deadline, jitter, budget, circuit breaker và kiểm thử idempotency contract; enum ở đây không tự thực thi sleep/retry.

## 10. Ứng dụng Spring Boot WebFlux: loại bỏ access token bị từ chối, không replay

Để dễ nhìn thấy luồng chính xác, demo sử dụng **client_credentials grant** của một backend service tên `reports-backend`. Nó **không dựa vào browser login**, vì vậy dùng `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` với `ReactiveOAuth2AuthorizedClientService`.

Khi gọi API downstream:

1. Manager load cached OAuth2AuthorizedClient hoặc lấy access token mới từ token endpoint.
2. `WebClient` gắn token vào **HTTPS resource server cố định**.
3. Downstream 2xx → trả body.
4. Downstream 401 có Bearer challenge `error="invalid_token"` → **xóa đúng authorized client được lưu**, phát lỗi ứng dụng hiện tại, **không retry ngay**.
5. Downstream 403 → báo lỗi quyền/upstream, **không xóa token tự động**.
6. Một HTTP request **mới** có thể làm manager lấy token mới; nếu IdP hoặc resource vẫn từ chối thì không tạo loop trong một request.

**Phạm vi demo:** cần một Authorization Server thực sự cấp `client_credentials` và một resource server đã tin issuer/token đó; không có IdP giả định bí mật được hard-code. Phần RetryPolicyDemo chạy offline; phần WebFlux chỉ chạy end-to-end khi cấu hình hai dịch vụ ngoài hợp lệ.

### 10.1. pom.xml

Tạo Maven project `reactive-client-recovery`, group `com.example`, Java 17+. Spring Boot **4.1.2** có starter OAuth2 Client mang tên `spring-boot-starter-security-oauth2-client` (trong Boot 4 tên này thay thế starter OAuth2 Client cũ).

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-client-recovery</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dùng Boot BOM, không tự override Spring Security core/client/web phiên bản lệch nhau. Không thêm `spring-boot-starter-web` MVC vào WebFlux chỉ vì muốn tạo REST controller.

### 10.2. application.properties

Tạo file `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.client.registration.downstream.provider=downstream
spring.security.oauth2.client.registration.downstream.client-id=${DEMO_CLIENT_ID}
spring.security.oauth2.client.registration.downstream.client-secret=${DEMO_CLIENT_SECRET}
spring.security.oauth2.client.registration.downstream.authorization-grant-type=client_credentials
spring.security.oauth2.client.registration.downstream.scope=reports.read
spring.security.oauth2.client.provider.downstream.token-uri=${DEMO_TOKEN_URI}

demo.resource-base-url=${DEMO_RESOURCE_BASE_URL}
~~~

Sau khi lưu bài, các ký hiệu `${...}` được chuyển sang placeholder chuẩn Spring `$...`, được resolve bằng biến môi trường lúc chạy.

- `DEMO_TOKEN_URI`: endpoint HTTPS của Authorization Server phát `client_credentials`, ví dụ từ IdP công ty.
- `DEMO_RESOURCE_BASE_URL`: **base URL HTTPS của resource server mà bạn kiểm soát và tin cậy**.
- `DEMO_CLIENT_ID` / `DEMO_CLIENT_SECRET`: credentials được IdP cấp cho service này, không để trong Git.
- Resource server phải có GET `/reports/summary`; hoặc đổi URI trong Java theo API thật.
- Client registration `downstream` và principal `reports-backend` là khóa cố định để load/remove authorized client.

**Không có token endpoint công khai giả định nào được cung cấp trong bài.** Nếu chưa cấu hình IdP/client credential hợp lệ, app có thể khởi chạy nhưng request `/demo/report` sẽ báo lỗi khi authorize; không thể gọi đó là bug của retry policy.

### 10.3. Java source hoàn chỉnh

Tạo file `src/main/java/com/example/clientrecovery/ReactiveClientRecoveryApplication.java`:

~~~java
package com.example.clientrecovery;

import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveClientRecoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ReactiveClientRecoveryApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        // Demo chỉ có GET; không dùng permitAll cho API private production.
        return http.authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/demo/report").permitAll()
                    .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        var provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    WebClient resourceWebClient(
            WebClient.Builder builder,
            @Value("${demo.resource-base-url}") String baseUrl) {
        // baseUrl phải là HTTPS endpoint cố định đã được kiểm tra trust.
        return builder.baseUrl(baseUrl).build();
    }

    @Service
    static class ResourceGateway {
        private static final String REGISTRATION_ID = "downstream";
        private static final String SERVICE_PRINCIPAL = "reports-backend";

        private final ReactiveOAuth2AuthorizedClientManager manager;
        private final ReactiveOAuth2AuthorizedClientService service;
        private final WebClient webClient;

        ResourceGateway(
                ReactiveOAuth2AuthorizedClientManager manager,
                ReactiveOAuth2AuthorizedClientService service,
                WebClient resourceWebClient) {
            this.manager = manager;
            this.service = service;
            this.webClient = resourceWebClient;
        }

        Mono<String> fetchOnce() {
            OAuth2AuthorizeRequest authorizeRequest =
                    OAuth2AuthorizeRequest
                            .withClientRegistrationId(REGISTRATION_ID)
                            .principal(SERVICE_PRINCIPAL)
                            .build();

            return manager.authorize(authorizeRequest)
                    .switchIfEmpty(Mono.error(
                            new IllegalStateException(
                                    "Client authorization unavailable")))
                    .flatMap(authorizedClient ->
                            webClient.get()
                                    .uri("/reports/summary")
                                    .headers(headers ->
                                            headers.setBearerAuth(
                                                    authorizedClient
                                                            .getAccessToken()
                                                            .getTokenValue()))
                                    .exchangeToMono(response -> {

                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(String.class);
                }

                if (response.statusCode().value() == 401) {
                    String challenge = response.headers()
                            .asHttpHeaders().getFirst(
                                    HttpHeaders.WWW_AUTHENTICATE);

                    Mono<Void> cleanup =
                            hasInvalidTokenChallenge(challenge)
                                    ? service.removeAuthorizedClient(
                                            REGISTRATION_ID,
                                            SERVICE_PRINCIPAL)
                                    : Mono.empty();

                    return response.releaseBody()
                            .then(cleanup)
                            .then(Mono.error(new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "upstream_authentication_rejected")));
                }

                if (response.statusCode().value() == 403) {
                    // Thiếu scope/role không sửa được bằng refresh loop.
                    return response.releaseBody()
                            .then(Mono.error(new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "upstream_authorization_denied")));
                }

                return response.releaseBody()
                        .then(Mono.error(new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "upstream_unavailable")));
            }));
        }

        // Parser tối giản, chỉ phục vụ demo challenge RFC 6750 phổ biến.
        // Production dùng filter/handler Spring Security để parse lỗi.
        private static boolean hasInvalidTokenChallenge(
                String challenge) {
            if (challenge == null) {
                return false;
            }
            String value = challenge.trim().toLowerCase(Locale.ROOT);
            return value.startsWith("bearer ")
                    && value.contains("error=\"invalid_token\"");
        }
    }

    @RestController
    static class DemoController {
        private final ResourceGateway gateway;

        DemoController(ResourceGateway gateway) {
            this.gateway = gateway;
        }

        @GetMapping(value = "/demo/report",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> report() {
            return gateway.fetchOnce();
        }
    }
}
~~~

**Phân tích hành vi:**

- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` hỗ trợ `client_credentials` mà không cần current browser user.
- Principal `reports-backend` là hằng ổn định. Manager lưu client tương ứng dưới key `downstream/reports-backend`.
- `manager.authorize(...)` lấy client đang lưu hoặc xin token mới khi cần; `switchIfEmpty` từ chối khi provider không hỗ trợ hoặc không thể authorize.
- Resource URL cố định dưới `demo.resource-base-url`, không được dựng từ untrusted query/header.
- Khi downstream 2xx, trả body text.
- Với 401, demo **chỉ xóa client** khi `WWW-Authenticate` có Bearer `error="invalid_token"` theo một cú pháp quen thuộc. 401 không có error cụ thể vẫn báo lỗi, **không xóa bừa**.
- `response.releaseBody()` giải phóng response body trước khi hoàn tất nhánh lỗi.
- `service.removeAuthorizedClient(...)` là `Mono<Void>` được compose bằng `then(...)`; do đó removal được subscribe **trước** khi phát lỗi hiện tại.
- HTTP 403 downstream không tự xóa token, bởi đây có thể là quyền/scope thiếu.
- Demo chuyển lỗi upstream 401/403 thành **502 Bad Gateway** ở facade, vì token client_credentials thuộc backend service chứ **không phải credentials của người dùng HTTP gọi facade**. Một sản phẩm khác có thể chọn status mapping khác theo hợp đồng.
- Không có `retryWhen`, recursion hoặc `repeat()`; một lần `GET /demo/report` chỉ có **một downstream resource call** sau bước acquire/re-authorize.
- Không log raw token hay `WWW-Authenticate` đầy đủ; phần challenge chỉ dùng nội bộ để xác định loại lỗi.
- `hasInvalidTokenChallenge` là **parser tối giản cho mục đích học**, không xử lý đầy đủ mọi cú pháp RFC 6750 (giá trị unquoted, nhiều challenge, escape, case). Với hệ thống production, ưu tiên `ServerOAuth2AuthorizedClientExchangeFilterFunction` cùng `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` xử lý lỗi theo contract framework; hoặc dùng parser được kiểm thử đầy đủ.

### 10.4. Vì sao parser không nên xóa client trên mọi HTTP 401?

Một reverse proxy có thể trả 401 vì chính proxy yêu cầu cơ chế auth khác, hoặc một endpoint API được đổi. Nếu xóa client không kiểm điều kiện, mỗi request lại tới token endpoint xin token mới rồi vẫn bị 401, tạo rate-limit storm. Parser trong demo chỉ làm cleanup khi có tín hiệu Bearer `invalid_token`. Ngay cả khi cleanup hợp lệ, **đó không phải chỉ thị tự replay**.

### 10.5. Vì sao không dùng WebClient OAuth2 filter trong code demo?

Để thấy rõ trình tự authorize → request → phân loại → delete → stop. Trong ứng dụng thực, filter `ServerOAuth2AuthorizedClientExchangeFilterFunction` thường thuận tiện hơn. Khi dùng constructor manager, **phải set failure handler** nếu muốn resource 401/403 được xử lý, như phần 6. Code demo chủ động gọi manager và xử lý status nên không phụ thuộc cơ chế auto-forward của filter.

### 10.6. Storage trong demo và production

Spring Boot OAuth2 client auto-configuration thường cung cấp `ReactiveOAuth2AuthorizedClientService`, mặc định in-memory khi chưa có store riêng. Bộ nhớ này **không chia sẻ giữa replicas** và mất khi ứng dụng restart. Với nhiều node hoặc yêu cầu quản lý token bền vững, cân nhắc `R2dbcReactiveOAuth2AuthorizedClientService` hay một implementation phân tán được bảo vệ, encrypted-at-rest và có cơ chế concurrency control. Không cho nhiều pods refresh token rotation cùng lúc mà không phối hợp.

## 11. Chạy và kiểm thử ứng dụng

### 11.1. Khởi động

Với IdP/resource server hợp lệ đã provision, đặt environment variables:

~~~bash
export DEMO_CLIENT_ID='reports-service'
export DEMO_CLIENT_SECRET='secret-from-your-idp'
export DEMO_TOKEN_URI='https://idp.example.com/oauth2/token'
export DEMO_RESOURCE_BASE_URL='https://resource.example.com'

./mvnw clean package
./mvnw spring-boot:run
~~~

Những host/secret trên là **giá trị minh họa**, phải thay bằng URL/credential thực được IdP cấp. Trên Windows PowerShell dùng `$env:DEMO_CLIENT_ID="..."` và tương tự cho các biến khác, rồi `.\mvnw.cmd spring-boot:run`.

`client_credentials` không cần browser login, nhưng cần Authorization Server chấp nhận grant, scope `reports.read` phù hợp và resource server `GET /reports/summary` thực sự tồn tại. Nếu chưa có các dịch vụ này, chỉ có `RetryPolicyDemo` chạy offline; không tuyên bố integration test OAuth đã hoàn tất.

### 11.2. Gọi facade

~~~bash
curl -i http://localhost:8080/demo/report
~~~

Khi token hợp lệ và downstream 200, facade trả **200** với body resource đã trả. Nếu downstream 401 với Bearer `invalid_token`, facade trả **502** do `ResponseStatusException` sau khi xóa authorized client tương ứng. Request hiện tại **dừng**, không tự phát lại tới resource server.

Một lần gọi **mới**:

~~~bash
curl -i http://localhost:8080/demo/report
~~~

Có thể dẫn đến xin token lại từ IdP, vì record cũ đã bị remove. Nếu IdP vẫn từ chối hoặc resource vẫn trả 401, facade tiếp tục báo lỗi theo chính sách, **không lặp vô hạn trong cùng request**.

### 11.3. Những điều cần assert trong integration test

| Case | Mock token endpoint / downstream | Mong đợi |
| --- | --- | --- |
| Chưa có authorized client | Token endpoint trả 200, API trả 200 | 1 lần acquire, 1 call resource |
| Client đã cache còn hợp lệ | API trả 200 | Dùng client đã lưu, không xin token mới không cần thiết |
| API trả 401 `invalid_token` | Bearer challenge hợp lệ | Remove `downstream/reports-backend` đúng một lần; facade 502; **không replay** |
| API trả 401 không có Bearer error | Generic 401 | Không tự xóa theo demo, facade 502 |
| API trả 403 `insufficient_scope` | Bearer 403 | Không remove; facade 502; không refresh loop |
| Token endpoint trả `invalid_client` | Client credentials lỗi | Không bão retry; báo lỗi vận hành |
| Refresh token flow khác trả `invalid_grant` | Refresh thất bại | Manager failure handler xóa client cũ |
| API trả 503 | Downstream outage | Không xóa token; demo trả 502, không retry |
| 10 request 401 đồng thời | Cùng cached token | Mỗi request bounded; thiết kế concurrency ở production |
| Client credentials của service A | Principal khác service B | Không xóa nhầm key khác |
| API POST có side effect | Timeout | Không replay nếu không có idempotency contract |
| Bearer token gắn sang untrusted host | SSRF/redirect test | Không để rò Bearer header |

### 11.4. Test API bằng WebTestClient

Trong WebFlux, `WebTestClient` có thể kiểm facade nhưng cần fake `ReactiveOAuth2AuthorizedClientManager`, fake `ReactiveOAuth2AuthorizedClientService` và mock `ExchangeFunction`/resource server:

~~~java
// Test snippet, không phải JUnit class độc lập:
webTestClient.get()
        .uri("/demo/report")
        .exchange()
        .expectStatus().isBadGateway();
~~~

Để test **quan hệ side effect**, chỉ assert 502 là chưa đủ. Fake service/repository phải ghi nhận `removeAuthorizedClient("downstream","reports-backend")`; mock downstream phải ghi nhận **chính xác một request**. Nếu có 10 call song song, assertions phải phân biệt “mỗi call một lần” với “một lần toàn hệ thống”.

Nên dùng `StepVerifier` để xác nhận publisher removal completes, và dùng mock resource server trả chuẩn `WWW-Authenticate`. Các test không cần token/secret thật; dữ liệu test tuyệt đối không được log trong production.

## 12. Cấu hình retry có kiểm soát cho lỗi transient

Nếu muốn một request GET idempotent thử lại **tối đa một lần** khi `503 Service Unavailable`, có thể đặt chính sách Reactor ở **lớp adapter biết rõ idempotency**:

~~~java
// Snippet minh họa trên Mono<String> chỉ gọi GET idempotent.
// UpstreamTemporarilyUnavailableException do adapter của bạn phát cho 503.
return fetchIdempotentGet()
        .retryWhen(Retry.backoff(1, Duration.ofMillis(200))
                .filter(ex -> ex instanceof UpstreamTemporarilyUnavailableException));
~~~

Đây là **snippet**, không phải file runnable độc lập; `fetchIdempotentGet()` và exception phải được định nghĩa theo API. Điều kiện quan trọng:

- `Retry.backoff(1, ...)` cho phép **tối đa một retry**, nên tổng tối đa hai attempts (nếu request đầu thất bại).
- Error `UpstreamTemporarilyUnavailableException` chỉ được tạo cho lỗi transient đã được phân loại; **không** tạo nó cho HTTP 401/403.
- Theo quy tắc Reactor, resubscribe có thể tạo lại toàn bộ pipeline, gồm authorize và downstream. Phải bảo đảm GET idempotent, timeout và retry budget.
- Tránh đặt `retryWhen` vừa ở adapter, vừa ở controller, vừa ở gateway mà không tính multiplicative retries.
- Với POST/PUT/DELETE, cần idempotency key được server chấp nhận hoặc cơ chế transaction/deduplication trước khi retry.

### 12.1. Vòng lặp cần tránh

~~~java
// Anti-pattern: có thể khiến token endpoint/resource bị flood.
return callResourceWithOAuth()
        .retryWhen(Retry.indefinitely());
~~~

Nếu tài nguyên liên tục trả 401, exception lặp lại vô hạn. Ngay cả `Retry.fixedDelay(100, ...)` với 100 lần cũng quá nhiều cho lỗi authentication chắc chắn không tự hết. Một retry chỉ hữu ích khi **nguyên nhân là transient và operation an toàn để replay**.

### 12.2. Retry-After của 429

Khi downstream trả `429 Too Many Requests`, có thể cân nhắc `Retry-After`, global rate limiter, queue/backpressure và circuit breaker. Nhưng header này cần parse có giới hạn, không tin hoàn toàn một giá trị không hợp lệ hoặc quá dài; tránh thử lại đồng thời hàng nghìn clients. **429 không phải lý do để xóa OAuth2AuthorizedClient**.

## 13. Concurrency: refresh token rotation và stale invalidation

### 13.1. Hai request cùng refresh token

~~~text
Request A                      Request B                   Authorization Server
   |                              |                                |
load client X                  load client X                      |
   |                              |                                |
refresh R0 ---------------------> |                                |
   |                          refresh R0 ------------------------->|
   |                              |                                |
receive access A1, R1          invalid_grant (R0 reused)          |
   |                              |                                |
save new client X               remove client X                     |
   |                              |                                |
result: last-write / deletion race -> client mới có thể mất
~~~

Đây là **một tình huống race có thể xảy ra**, không khẳng định mọi IdP luôn rotate hoặc cho phép một request thắng trước. Trong thực tế, nhiều IdP rotate refresh token; một request dùng R0 thành công và lấy R1, request kia dùng lại R0 bị `invalid_grant`. Nếu handler xóa record sau khi một request khác vừa lưu R1, authorized client mới có thể bị xóa.

### 13.2. Cách giảm race

- Với cùng `clientRegistrationId + principalName`, dùng **single-flight refresh**/lock phù hợp.
- Nếu nhiều node, lock phải phân tán hoặc store hỗ trợ conditional update; lock local JVM không đủ cho cluster.
- Dùng compare-and-swap/version check để không xóa token mới do stale error từ request cũ.
- Khi cần, phân biệt access token ID/hash **không đảo ngược** (trong log chỉ lưu fingerprint không nhạy cảm) để theo dõi token nào bị từ chối.
- Xác định tính nhất quán giữa save new token và remove old token; tránh operations chạy lẫn khi refresh concurrent.
- Không retry `invalid_grant` liên tục vì refresh token R0 đã bị rotate/revoke thì retry bằng R0 vô nghĩa.
- Theo dõi duplicate refresh attempts, oauth2 refresh failure, token rotation và cleanup errors.

**Lưu ý code demo:** `ReactiveOAuth2AuthorizedClientService.removeAuthorizedClient(registrationId, principalName)` thường là thao tác theo key, **không phải compare-and-delete có điều kiện**. Trong cluster production, muốn không xóa nhầm token mới cần thiết kế repository/versioning phù hợp; đừng tưởng API remove mặc định đã giải quyết race.

### 13.3. Thử lại request sau cleanup và idempotency

Ngay cả khi cleanup giúp request mới lấy token mới, không có nghĩa thao tác cũ **chưa được thực hiện** ở downstream. Với network timeout hoặc gateway retry, downstream có thể đã xử lý dữ liệu nhưng response thất lạc. Vì vậy không replay POST thanh toán/đặt hàng chỉ vì lỗi client thấy là 401/timeout; phải có idempotency contract và request IDs từ downstream.

## 14. Observability, bảo mật và cảnh báo

### 14.1. Metrics hữu ích

Theo dõi theo các nhãn **có số lượng giá trị giới hạn**:

| Metric | Ví dụ lý do |
| --- | --- |
| `oauth2.client.authorize.success` | Lấy client/access token thành công |
| `oauth2.client.authorize.failure` | `invalid_grant`, `invalid_client`, timeout |
| `oauth2.client.removal` | `invalid_token`/`invalid_grant` có cleanup |
| `oauth2.resource.401` | Downstream từ chối authentication |
| `oauth2.resource.403` | Insufficient scope hoặc permission denied |
| `oauth2.refresh.concurrent` | Nhiều refresh cùng client/principal |
| `oauth2.retry.attempts` | Tổng số attempts / request |
| `oauth2.credential.rotation` | Token/client-secret lifecycle failures |

Đây là **tên metric gợi ý**, không phải những Micrometer meter Spring Security luôn tự cung cấp theo tên đó. Không đặt nguyên access token, refresh token, email/subject ID hoặc request URL tùy ý vào metric tag để tránh cardinality/PII.

### 14.2. Những gì không nên log

- Header `Authorization: Bearer ...`.
- Access token/refresh token hoặc client secret.
- Raw `WWW-Authenticate` nếu nó chứa dữ liệu nhạy cảm không được kiểm soát.
- Toàn bộ OAuth2 error response của IdP khi chưa đánh giá nội dung.
- JWT claims chứa PII hoặc bí mật nội bộ.

Nên log `registrationId` đã whitelist, upstream ID được cấu hình sẵn, error category, HTTP status, correlation ID và outcome **removed / not removed / retry suppressed**. Nếu cần chẩn đoán token nào, dùng fingerprint một chiều/truncated với key quản trị thay vì log raw token.

### 14.3. Cảnh báo sớm

- `invalid_client` tăng mạnh → client secret hết hạn/đổi sai.
- `invalid_grant` tăng → refresh token rotation bị race, token bị revoke hoặc policy IdP thay đổi.
- Nhiều `invalid_token` sau mỗi lần acquire → issuer/audience/JWK/scope sai, đừng để request loop che cấu hình.
- 403 tăng nhưng token vẫn hợp lệ → quyền/resource scope, đừng tiếp tục refresh.
- Token endpoint 429/503 → phải có backpressure và stop-the-world control.
- Số lần acquire trên một principal tăng đột biến → authorized-client store không persist hoặc cleanup quá rộng.

## 15. Các lỗi triển khai phổ biến

### 15.1. “Đã có manager failure handler nên WebClient 401 tự xóa”

Không nhất thiết. Với `ServerOAuth2AuthorizedClientExchangeFilterFunction(manager)`, Javadoc nêu rõ resource 401/403 không được forward tự động. Cần `setAuthorizationFailureHandler(...)` trên filter hoặc manual classification/cleanup như demo.

### 15.2. “Thấy bất kỳ 403 là xóa và xin token mới”

Sai. 403 có thể là `insufficient_scope` hoặc business authorization. Refresh token không tự tạo permission, chỉ gây vòng lặp.

### 15.3. “Chỉ gọi removeAuthorizedClient(...) rồi response đã đúng”

Method trả `Mono<Void>` là lazy publisher. Nếu không `return`/`then`/`flatMap`, thao tác remove có thể **không chạy**.

### 15.4. “Xóa theo user nhưng không đúng registration”

Key là registration ID + principal name; với repository WebFlux còn cần Authentication và ServerWebExchange phù hợp. Xóa sai key không làm token stale biến mất.

### 15.5. “Xóa local nghĩa là đã revoke token toàn hệ thống”

Không. Local removal chỉ xóa trạng thái client; access token có thể còn hợp lệ ở resource server đến khi hết hạn hoặc bị revoke qua cơ chế riêng.

### 15.6. “RetryWhen sẽ tự tránh các lỗi bảo mật”

Không. `Retry.indefinitely()` không phân biệt 401/403/503 và có thể resubscribe toàn bộ reactive chain. Tự viết policy có filter exception và budget.

### 15.7. “Client credentials thất bại thì yêu cầu user browser login”

Grant `client_credentials` thuộc service identity. Lỗi 401 downstream thường là sự cố service config/token; không tự biến nó thành 401 của user gọi frontend. Phân loại upstream failure và theo dõi vận hành.

### 15.8. “Refresh token invalid_grant thì retry R0 nhiều lần”

Không. R0 có thể bị revoke/rotation; retry cùng token chỉ làm tăng lỗi. Cần discard stale client, re-login hoặc new grant hợp lệ.

### 15.9. “Mọi 401 đều là invalid_token”

Không. Proxy/basic auth, missing token, wrong issuer, wrong audience hay thiếu challenge cũng có thể trả 401. Kiểm `WWW-Authenticate`, client registration, policy và nguồn 401.

### 15.10. “Dùng non-reactive OAuth2AuthorizedClientService trên Netty event loop”

Không dùng blocking service hay `.block()` vô tội vạ; Spring WebFlux cần reactive manager/service/repository, tránh chặn event loop.

### 15.11. “Nhiều instance cùng lưu token trong memory là ổn”

In-memory store mỗi node độc lập; refresh rotation và token invalidation có thể không nhất quán, buộc phải điều phối state hoặc chia sẻ store khi traffic lớn.

### 15.12. “Dùng filter tự gắn token cho mọi URL kể cả user nhập”

Một WebClient global với `setDefaultOAuth2AuthorizedClient(true)` và URI do user tự tạo có thể rò Bearer token. Cần fixed trusted base URL và explicit client registration.

### 15.13. “Chỉ nhìn status facade 502 nên tưởng downstream không xử lý gì”

Facade mapping HTTP status không chứng minh side effect hay không; khi timeout/network error, downstream có thể đã commit. Thử lại request thay đổi dữ liệu cần idempotency.

### 15.14. “Không có lỗi trong log nghĩa là cleanup hoạt động”

Cần assert authorized-client store được xóa và request mới không dùng token cũ. Xem metric removal outcome, test connector và kiểm tra principal/registration đúng.

## 16. Checklist production

1. Phân biệt token endpoint `invalid_grant` với resource `invalid_token` và `insufficient_scope`.
2. Biết client đang dùng `DefaultReactiveOAuth2AuthorizedClientManager` hay `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
3. Biết authorized clients lưu ở repository hay service, key nào được manager sử dụng.
4. Với WebClient OAuth filter, kiểm tra **constructor** và việc cài `ReactiveOAuth2AuthorizationFailureHandler`.
5. Chỉ remove khi OAuth2 error code/chính sách chỉ rõ token stale; không xóa mọi 403.
6. Không replay current request theo mặc định khi token bị từ chối.
7. Có re-login/new grant strategy phù hợp authorization_code vs client_credentials.
8. Retry transient có limit, backoff, jitter, deadline, circuit breaker; không retry auth errors.
9. POST/PUT/DELETE cần idempotency key và downstream contract trước khi cho phép replay.
10. Không gửi Bearer token tới URL do user đưa hoặc host không được allowlist.
11. Không log token/secret/raw claims; phân loại metric theo registration và error code.
12. Test stale token, missing challenge, invalid_grant, invalid_client, insufficient_scope, timeout, 429/503 và 2xx.
13. Test concurrency khi refresh token rotate, stale cleanup, multi-node và store shared.
14. Khi xóa client, compose `Mono<Void>`, không bỏ publisher hoặc tự block.
15. Không nhầm local remove với OAuth2 token revocation/logout toàn cục.
16. Kiểm tra dependency Spring Security đúng version; không copy Servlet failure handler vào WebFlux.
17. Có runbook rotate client secret, làm mới quyền và khắc phục issuer/audience/JWK không nhất quán.
18. Có giới hạn requests/token acquisitions per principal để tránh retry storm khi IdP gặp sự cố.

## 17. Tự đánh giá

**Câu 1.** Vì sao `invalid_grant` và `invalid_token` phải xử lý riêng?

**Đáp án:** `invalid_grant` thường từ token endpoint khi refresh token thất bại; `invalid_token` thường do resource server trả Bearer challenge cho access token không được chấp nhận. Chúng thuộc hai bước khác nhau và có failure handlers khác nhau.

**Câu 2.** Chỉ dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction(manager)` thì 401 downstream có tự xóa client không?

**Đáp án:** Không mặc định. Theo Javadoc 7.1, phải set authorization failure handler hoặc tự xử lý cleanup; constructor dùng repository mới auto-configure remover.

**Câu 3.** Lệnh `removeAuthorizedClient("downstream","reports-backend")` có revoke access token ở IdP không?

**Đáp án:** Không. Nó xóa cached client theo key. Revocation ở server là cơ chế khác.

**Câu 4.** Nếu 403 `insufficient_scope`, có nên gọi refresh đến khi được 200 không?

**Đáp án:** Không. Vấn đề là scope/quyền; refresh thường không thêm quyền mới và dễ tạo vòng lặp.

**Câu 5.** Vì sao phải return/compose `Mono<Void>` của remove?

**Đáp án:** Reactive operation là lazy; nếu chỉ gọi mà không subscribe theo pipeline, thao tác cleanup có thể không thực thi.

**Câu 6.** Khi nào nên retry tối đa một lần?

**Đáp án:** Với lỗi transient (ví dụ 503) và thao tác idempotent/replay-safe, có backoff và retry budget. Không áp cho 401/403.

**Câu 7.** Vì sao multi-node refresh token rotation có race?

**Đáp án:** Hai worker có thể dùng cùng refresh token cũ; một bên nhận token mới, bên kia `invalid_grant` rồi xóa record mới. Cần single-flight/conditional updates.

**Câu 8.** Vì sao sau khi cleanup có thể vẫn bị 401 ở request mới?

**Đáp án:** Cấp token mới không sửa issuer/audience/scope/JWK hoặc provider/resource misconfiguration. Cần chẩn đoán nguyên nhân, không tự retry vô hạn.

**Câu 9.** Với client_credentials, nên xóa client theo principal của user browser không?

**Đáp án:** Không. Dùng service identity ổn định đã được manager dùng để authorize/save, ví dụ `reports-backend`.

**Câu 10.** Nếu một POST timeout sau khi downstream đã commit, có nên tự replay?

**Đáp án:** Không khi chưa có idempotency contract. Timeout không chứng minh thao tác chưa được thực hiện.

## 18. Tài liệu chính thức

- [Spring Security — Reactive OAuth2 Client: Core Interfaces / Classes](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html)
- [Spring Security — OAuth2 Client in WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Javadoc — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Javadoc — DefaultReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultReactiveOAuth2AuthorizedClientManager.html)
- [Javadoc — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html)
- [Javadoc — RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler.html)
- [Javadoc — OAuth2AuthorizedClientRemover](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler.OAuth2AuthorizedClientRemover.html)
- [Javadoc — ReactiveOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientService.html)
- [Javadoc — ServerOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html)
- [Javadoc — RefreshTokenReactiveOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RefreshTokenReactiveOAuth2AuthorizedClientProvider.html)
- [Spring Boot — OAuth2 Client configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 6750 — OAuth2 Bearer Token Usage, invalid_token / insufficient_scope](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 6749 — OAuth2 Authorization Framework, invalid_grant](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Project Reactor — RetrySpec and RetryBackoffSpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html)
