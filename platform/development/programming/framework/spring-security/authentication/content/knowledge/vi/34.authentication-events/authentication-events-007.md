# Tính nhất quán khi có nhiều provider, thử lại và xác thực trên nhiều yêu cầu

## 1. Mục tiêu và bài toán trong Spring Security

Một ứng dụng Spring Boot có thể đồng thời chấp nhận **mật khẩu đăng nhập web**, **API key của hệ thống tích hợp**, **bearer token OAuth2**, hoặc xác thực qua hệ thống danh tính bên ngoài. Các cơ chế đó có thể đi qua nhiều `AuthenticationProvider`, nhiều `ProviderManager` và nhiều `SecurityFilterChain`. Sau mỗi lần kiểm tra, ứng dụng muốn phát sự kiện **authentication success/failure** để audit, monitoring hoặc giới hạn hành vi bất thường.

Nhưng “đã xác thực thành công” và “mỗi sự kiện chỉ xuất hiện một lần trên toàn hệ thống” là hai chuyện khác nhau:

- Một `ProviderManager` có thể thử **nhiều provider trong một lần** gọi `authenticate(...)`.
- Một HTTP request có thể chứa **một lần đăng nhập** hoặc không thử xác thực mới nếu đã có session hợp lệ.
- Một client stateless có thể phải **xác thực lại ở từng request**.
- Client hoặc gateway có thể **gửi lại request** khi timeout, làm phát sinh một lần thử mới.
- Event listener có thể được gọi lặp bởi **cấu hình nhiều publisher**, hoặc event có thể được gửi lại khi chuyển sang message broker/outbox.
- Hai request đồng thời có thể cùng đọc/cập nhật session, credential state hoặc audit counter.
- Một event cho biết **authentication đã thành công**, không chứng minh controller đã xử lý thành công hay user có quyền đối với mọi resource.

Bài học thuộc nhóm **“Sự kiện xác thực”** trong module Spring Security - authentication. Mục tiêu không phải phát triển một hệ thống event broker đầy đủ, mà là hiểu **ngữ nghĩa và ranh giới** của sự kiện khi có nhiều provider, retry và nhiều yêu cầu liên tiếp. Bạn sẽ có thể:

1. Dự đoán thứ tự `AuthenticationProvider` và kết quả cuối cùng của `ProviderManager`.
2. Phân biệt **provider attempt**, **authentication-manager decision**, **HTTP request**, **interactive login event**, **session** và **business operation**.
3. Hiểu nơi phát `AuthenticationSuccessEvent` và `AbstractAuthenticationFailureEvent`; vì sao publisher thiếu hoặc bị cấu hình trùng làm audit sai.
4. Thiết kế retry đúng cho credential failure, lỗi phụ thuộc tạm thời, one-time token và request bị trùng.
5. Giữ kết quả login nhất quán qua nhiều request stateful/stateless và tránh rò `SecurityContext` qua thread.
6. Viết ứng dụng Spring Boot 3.5.x / Java 17+ với hai loại provider, một manager, một event publisher và một listener thread-safe.
7. Kiểm thử success/failure ở nhiều HTTP request bằng MockMvc, nhận ra khác biệt giữa event count và business request count.
8. Dùng correlation ID, deduplication và outbox khi sự kiện có tác dụng phụ quan trọng.

**Nguyên tắc tổng quát:** phân loại đúng đối tượng mà bạn cần tính nhất quán. Không thể dùng một bộ đếm `AuthenticationSuccessEvent` để suy ra chính xác số user session, số người dùng duy nhất hoặc số request API đã thành công.

## 2. Sáu khái niệm khác nhau thường bị gộp làm một

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Provider attempt** | Một provider được manager hỏi để xử lý một `Authentication` | Provider A thấy `UsernamePasswordAuthenticationToken`, kiểm tra mật khẩu |
| **Manager authentication decision** | Kết quả cuối của một lần gọi `AuthenticationManager.authenticate(...)` | Manager trả Authentication hợp lệ hoặc ném AuthenticationException |
| **Authentication event** | Thông báo trong Spring ApplicationContext về kết quả xác thực | `AuthenticationSuccessEvent` hay `AuthenticationFailureBadCredentialsEvent` |
| **HTTP request** | Một yêu cầu do client gửi qua mạng | `POST /login`, `GET /private/me`, `GET /api/key/whoami` |
| **SecurityContext/session** | Nơi chứa Authentication cho request hiện tại và có thể tái sử dụng qua session | User login một lần, sau đó GET 5 trang không cần nhập lại mật khẩu |
| **Business operation** | Hành động nghiệp vụ yêu cầu authorization và xử lý riêng | Tạo hóa đơn, chuyển tiền, đổi email, tạo API key |

**Không có quan hệ 1:1 bắt buộc.** Một lần `authenticate` có thể đi qua nhiều provider; một phiên có thể chứa nhiều request; một request stateless có thể gọi `authenticate` mỗi lần; một authentication thành công có thể bị `AuthorizationFilter` từ chối ở bước sau.

Sơ đồ ranh giới:

```text
HTTP request
    |
    v
Authentication filter (khi cơ chế cần xác thực ở request này)
    |
    v
AuthenticationManager.authenticate(token)  <-- 1 decision
    |
    +--> Provider A (supports? result/null/error)
    |
    +--> Provider B (nếu cần)
    |
    +--> optional parent AuthenticationManager
    |
    v
Final Authentication / AuthenticationException
    |
    +--> AuthenticationEventPublisher
    |       +--> success/failure event
    |
    +--> Filter:
            +--> SecurityContext
            +--> session persistence hoặc stateless request context
            +--> success/failure response
    |
    v
Authorization, Controller, Service, Business transaction
```

Event publisher nói về **kết quả xác thực**, không bao hàm commit thành công của database transaction ở cuối sơ đồ.

## 3. ProviderManager quyết định thế nào khi nhiều provider cùng tồn tại?

Spring Security định nghĩa `AuthenticationManager` là interface nhận một Authentication chưa xác thực và trả một Authentication đã được xác thực hoặc ném `AuthenticationException`. Implementation thường gặp nhất là `ProviderManager`, nắm một danh sách có thứ tự các `AuthenticationProvider`.

Mỗi provider có hai phương thức:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
```

Đây là **chữ ký rút gọn** từ interface, không phải class Java độc lập. Kết hợp hai phương thức có các tình huống:

| Provider xử lý | Ý nghĩa đối với manager |
| --- | --- |
| `supports(tokenType) == false` | Bỏ qua provider đó, không gọi `authenticate` |
| `supports(...) == true` và trả **Authentication khác null** | Thành công; dừng duyệt providers, dùng kết quả đó |
| Trả `null` | Provider chưa quyết định; tiếp tục tìm provider khác |
| Ném `BadCredentialsException` | Ghi nhận lỗi; một provider tiếp theo vẫn có thể quyết định thành công theo contract `ProviderManager` |
| Ném `AccountStatusException` (ví dụ locked/disabled) | Ngừng thử providers tiếp theo; không để provider sau bypass chính sách trạng thái account |
| Không provider nào hỗ trợ hoặc quyết định được | Có thể nhận `ProviderNotFoundException` hoặc lỗi cuối cùng; nếu có parent manager, parent có thể được thử theo contract |

Theo Javadoc `ProviderManager`, nếu một provider sau **thành công**, lỗi từ provider trước bị bỏ qua và **kết quả thành công cuối cùng** được sử dụng. Nếu không có provider sau thành công, lỗi phù hợp cuối cùng được ném. `AccountStatusException` là ngoại lệ quan trọng làm dừng quá trình.

### 3.1. Ví dụ thứ tự hai cơ chế tách biệt

```text
ProviderManager [
    DaoAuthenticationProvider           -> UsernamePasswordAuthenticationToken
    ApiKeyAuthenticationProvider        -> ApiKeyAuthenticationToken
]
```

- Browser `POST /login` tạo `UsernamePasswordAuthenticationToken`: Dao provider kiểm tra; API-key provider không hỗ trợ token đó.
- Machine client gửi `X-API-Key` tạo `ApiKeyAuthenticationToken`: Dao provider không hỗ trợ; API-key provider kiểm chứng digest.
- Hai token type khác nhau giúp ngăn một provider vô tình “thử vận may” với một credential của cơ chế khác.

**Thứ tự provider vẫn cần quản lý**, đặc biệt nếu hai provider đều hỗ trợ **cùng một loại token**. Ví dụ password provider A dùng LDAP và provider B dùng database cũ: nếu A báo `BadCredentialsException`, B vẫn có thể chấp nhận cùng username/password. Đó có thể là yêu cầu thiết kế có chủ đích, nhưng cũng có thể là **bypass** của account policy.

### 3.2. Bảng kiểm tra kết quả cuối cùng

| Provider A | Provider B | Kết luận thực tế |
| --- | --- | --- |
| Không hỗ trợ token | Xác thực thành công | Thành công do B |
| Trả `null` | Xác thực thành công | Thành công do B |
| `BadCredentialsException` | Xác thực thành công | Thành công do B, không được mặc nhiên kết luận event failure cuối cùng |
| Xác thực thành công | Không gọi | Thành công do A, dừng |
| `DisabledException`/`LockedException` | Không gọi | Thất bại do trạng thái account; không fallback |
| Không provider nào hỗ trợ | Không provider nào hỗ trợ | Lỗi `ProviderNotFoundException` nếu không có parent phù hợp |
| Provider A/B đều gặp lỗi phụ thuộc | Không thành công | Lỗi cuối cùng theo contract; **không** tự cho qua bằng account anonymous |

**Không dùng fallback để biến outage thành bypass:** nếu credential store trung tâm mất kết nối, không nên tự động rơi về một local account store yếu hơn trừ khi có threat model, policy, account binding và kiểm thử rõ ràng. “Availability” không được đổi lấy xác thực giả.

## 4. Spring Security phát sự kiện ở ranh giới nào?

Spring Security dùng `AuthenticationEventPublisher` để chuyển quyết định authentication thành Spring application events. Implementation điển hình là `DefaultAuthenticationEventPublisher`.

Các loại thường gặp:

- `AuthenticationSuccessEvent`: một lần gọi manager đạt kết quả authentication thành công.
- `AuthenticationFailureBadCredentialsEvent`: lỗi bad credentials theo mapping mặc định.
- `AuthenticationFailureDisabledEvent` / `AuthenticationFailureLockedEvent`: lỗi account state tương ứng.
- `AuthenticationFailureProviderNotFoundEvent`: không tìm được provider thích hợp.
- `AuthenticationFailureServiceExceptionEvent`: lỗi xác thực do sự cố hệ thống được mapping.
- `AbstractAuthenticationFailureEvent`: superclass để listener nghe nhiều loại failure.
- `InteractiveAuthenticationSuccessEvent`: một sự kiện khác có thể được authentication filter phát cho interactive login thành công; **không đồng nghĩa manager đã chạy thêm một lần**.

Các sự kiện này không đồng nghĩa với `HttpSessionCreatedEvent`, `SessionFixationProtectionEvent`, `LogoutSuccessEvent` hay event của nghiệp vụ. **Không gom tất cả event có chữ “success” thành “người dùng login một lần”.**

### 4.1. Một lần manager.authenticate, nhiều provider: có bao nhiêu event?

Với một `ProviderManager` chuẩn có một publisher được gắn đúng và provider không tự phát event:

```text
authenticate(token)
  Provider A -> BadCredentialsException
  Provider B -> Authentication success
  ProviderManager -> quyết định SUCCESS
  Publisher -> AuthenticationSuccessEvent
```

**Kết quả cuối là success.** Không nên đoán mỗi provider attempt sẽ tạo một `AuthenticationFailureBadCredentialsEvent` độc lập. Nếu provider A/B tự gọi `ApplicationEventPublisher.publishEvent(...)` bên trong, đó là **custom event do ứng dụng phát**, không còn tương đương một manager-level final outcome.

Ngược lại:

```text
authenticate(token)
  Provider A -> BadCredentialsException
  Provider B -> BadCredentialsException
  ProviderManager -> quyết định FAILURE
  Publisher -> AuthenticationFailureBadCredentialsEvent
```

Đây là **một lần thử authentication thất bại từ góc nhìn manager**, dù có hai provider được gọi.

### 4.2. Quan trọng: tự khởi tạo ProviderManager không mặc nhiên có publisher

Javadoc `ProviderManager` cho biết publisher mặc định của một manager tự tạo là implementation không phát event. Vì vậy:

```java
// Chưa đủ nếu hệ thống cần nhận sự kiện xác thực:
ProviderManager manager = new ProviderManager(
    List.of(providerOne, providerTwo));
```

Nên gắn `AuthenticationEventPublisher` tương ứng:

```java
ProviderManager manager = new ProviderManager(
    List.of(providerOne, providerTwo));
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
```

Đây là **trích đoạn**; tên biến provider được cấp qua cấu hình bên dưới. Để tránh sự kiện “biến mất” trong audit, test phải chứng minh không chỉ login thành công mà **listener nhận được event mong muốn**.

Trong cấu hình chuẩn của Spring Security/Boot, event publisher có thể được tự đăng ký theo cách framework tạo manager. Nhưng **đừng áp đặt giả định đó lên một `new ProviderManager(...)` do bạn tự khởi tạo**. Hãy chỉ định publisher tường minh tại nơi bạn sở hữu lifecycle của manager.

### 4.3. Parent manager và sự kiện nhân đôi

`ProviderManager` có thể nhận **parent AuthenticationManager**. Nếu child không giải quyết được, parent được hỏi. Javadoc lưu ý child cũng có thể publish event từ kết quả của parent; nếu **cả child và parent đều có publisher phát sự kiện**, có nguy cơ **double publication**.

```text
Child ProviderManager
  |
  +-- local providers -> không quyết định
  |
  v
Parent ProviderManager -> success
  |
  +-- parent publisher emits success event
  |
  v
Child receives parent's result
  |
  +-- child publisher emits success event AGAIN
```

**Khuyến nghị:** chọn **một nơi chịu trách nhiệm phát event** trong chuỗi manager có parent, hoặc chủ động deduplicate theo thiết kế. Không mặc định rằng hai sự kiện có nghĩa user đã login hai lần. Và không vì sợ duplicate mà vô hiệu toàn bộ auth audit.

### 4.4. Mapping AuthenticationException có giới hạn

`DefaultAuthenticationEventPublisher` ánh xạ những exception được biết đến thành failure events. Spring Security 6.5 docs nói cơ chế mapping mặc định dùng **exact exception class match**, không tự mở rộng sang mọi subclass tùy biến.

Ví dụ ứng dụng có:

```java
public final class ExternalIdentityUnavailableException
        extends AuthenticationServiceException {
    public ExternalIdentityUnavailableException(String message) {
        super(message);
    }
}
```

Nếu publisher không có mapping cho **đúng class custom**, có thể **không phát failure event như bạn mong**. Bổ sung `setAdditionalExceptionMappings(...)` hoặc fallback event phù hợp; đừng ép exception thành `BadCredentialsException` chỉ để “có event”, vì như vậy làm sai nghĩa lỗi.

## 5. Authentication event không phải HTTP request event

Một user browser thường login một lần rồi gửi nhiều request:

```text
T0 POST /login + password đúng
   -> manager.authenticate(...) SUCCESS
   -> AuthenticationSuccessEvent
   -> session lưu SecurityContext

T1 GET /private/me + JSESSIONID
   -> SecurityContextRepository load authentication
   -> controller trả 200
   -> không nhất thiết có lần manager.authenticate mới

T2 GET /private/report + JSESSIONID
   -> load SecurityContext, authorization
   -> không nhất thiết có event authentication success mới

T3 POST /logout
   -> logout/session cleanup; event khác nếu cấu hình
```

**Một authentication event không cho biết có bao nhiêu request đã phục vụ trong session.** Ngược lại, một user có thể login lại sau logout, có nhiều browser sessions, hoặc reauthentication/step-up khiến có nhiều event cho cùng principal.

Với API key/bearer token stateless:

```text
GET /api/key/whoami + X-API-Key: secret
    -> kiểm chứng key trong request này
    -> AuthenticationSuccessEvent

GET /api/key/whoami + cùng key, request thứ hai
    -> kiểm chứng lại key
    -> AuthenticationSuccessEvent lần nữa
```

Nếu endpoint filter thực sự gọi manager **mỗi request**, nhận hai success events là bình thường. Đừng deduplicate hai lần xác thực thật chỉ vì `principal` giống nhau, kẻo làm mất tín hiệu audit.

Một biến thể cache token validation có thể không gọi manager mọi request; do đó tần suất event phụ thuộc **authentication architecture**, không phải cam kết cố định của Spring Security.

## 6. Retry: ba khái niệm phải phân biệt

### 6.1. Retry ở tầng provider

Ví dụ provider truy vấn một identity server tạm thời timeout. Một lần `authenticate(...)` có thể có quy trình retry nội bộ nếu ứng dụng tự triển khai. Nhưng:

- **Không tự retry `BadCredentialsException`** nhiều lần: mật khẩu sai không trở nên đúng vì retry; vừa tăng tải vừa làm audit khó đọc.
- **Không retry `DisabledException`/`LockedException`** bằng provider khác để bypass trạng thái account.
- Lỗi transient như network timeout có thể thử lại **có giới hạn**, timeout/budget/circuit breaker, và chỉ với operation xác thực thực sự an toàn để retry.
- Những credential **dùng một lần** như OTP, magic link, authorization code, WebAuthn challenge bị tiêu thụ hoặc gắn ceremony có thể không an toàn khi gửi lại như một giao dịch mới.
- Nếu hệ thống xác thực bên ngoài có side effect (lockout counter, access log, failed-attempt counter), retry làm tăng số lần kiểm tra và số dấu vết.

**Retry nội bộ provider không tự nghĩa là manager phát nhiều sự kiện**; publisher của manager thường thấy kết quả cuối của một lần gọi. Nếu provider phát event riêng theo mỗi network attempt thì phân biệt rõ `provider_attempt` với `authentication_outcome`.

### 6.2. Retry ở tầng HTTP client/gateway

Nếu request `POST /login` timeout sau khi backend đã xử lý thành công, client có thể không nhận response/cookie và **gửi lại**. Backend nhìn thấy một request mới:

```text
Client                Gateway                 Server
  | POST /login A        |                      |
  |--------------------->|---- attempt A ------>|
  |                      |                auth SUCCESS
  |                      |                session/context stored
  |       timeout        |                      |
  |<---------------------X                      |
  | POST /login A retry  |                      |
  |--------------------->|---- attempt B ------>|
  |                      |                auth SUCCESS again
  |<---------------------|<----- response ------|
```

Hai authentication success events có thể phản ánh **hai lần gửi thực** chứ không phải publisher bug. Không dùng “request POST thường idempotent” làm giả định: HTTP POST không có tính idempotent mặc định; chỉ ứng dụng mới có thể cung cấp semantics riêng.

Nếu cần xử lý retry an toàn, phải xác định **ý nghĩa của retry**: cùng yêu cầu xác thực cần giữ nguyên kết quả? hay lần thử mới để rate limiting? **Không bao giờ cho client đặt một idempotency key tùy ý rồi vì “đã từng thành công” mà bỏ qua kiểm chứng credential ở lần sau.**

### 6.3. Retry khi đẩy event sang hệ thống ngoài

Nếu listener phát sự kiện ra Kafka/RabbitMQ/outbox/HTTP collector, một lỗi ACK có thể khiến cùng event **được gửi lại**. Đây là **delivery retry**, khác hoàn toàn việc user thử đăng nhập lần hai.

Cách xử lý:

1. Tạo **event ID ổn định** cho một sự kiện nghiệp vụ/audit cần gửi ra ngoài, tại nguồn tạo event.
2. Lưu event cùng trạng thái giao dịch trong outbox hoặc nơi bền vững; nếu downstream lỗi thì retry **cùng event ID**.
3. Consumer áp dụng unique constraint/dedup theo event ID và nghiệp vụ; khi nhận lại cùng ID thì bỏ qua **side effect**, không xóa bản ghi lịch sử request xác thực khác.
4. Bảo đảm metrics không đếm lại khi nhận duplicate delivery. Các chỉ số request count và delivered-event count vẫn nên tách.
5. Cần thiết kế quy trình dead-letter/replay và audit khi event không được giao.

**Spring `AuthenticationSuccessEvent` không phải một outbox event với durable event ID và exactly-once delivery tự động.** Nếu ứng dụng cần bảo đảm như thế, bạn phải bổ sung lớp persistence/transaction/dedup phù hợp.

## 7. Phân loại kết quả để tránh dữ liệu audit sai

Một event audit tối thiểu nên phân biệt:

| Field | Ví dụ | Lý do |
| --- | --- | --- |
| `event_id` | UUID do server tạo cho **một** event persisted | Giúp dedup delivery, không thay “attempt count” |
| `attempt_id` | Correlation ID của một lần manager invocation, nếu có | Kết nối provider diagnostics với manager decision |
| `request_id` | HTTP request ID từ reverse proxy tin cậy/server | Kết nối log, trace và request retry |
| `principal_ref` | User/service ID đã được pseudonymize hoặc access-controlled | Không lưu plaintext password hoặc raw API key |
| `auth_method` | password, API key, bearer, WebAuthn | Phân loại cơ chế |
| `result` | SUCCESS/FAILURE/ERROR | Tách sai mật khẩu và lỗi hạ tầng |
| `provider_id` | provider identifier an toàn | Debug routing nếu có nhiều providers |
| `failure_code` | BAD_CREDENTIALS, ACCOUNT_LOCKED, SERVICE_UNAVAILABLE | Không dùng raw exception text làm public contract |
| `occurred_at` | UTC timestamp server | Phân tích retry/freshness và ordering |
| `session_ref` | Session ref pseudonymized nếu stateful | Phân biệt request/session |
| `policy_version` | Phiên bản rule authentication khi thích hợp | Debug thay đổi hành vi giữa deployments |

Phần này là **schema thiết kế gợi ý**, không phải fields Spring tự đưa ra trong mọi event. Đừng log trực tiếp `Authentication.toString()` nếu token/principal/details có thể chứa credentials hoặc dữ liệu cá nhân.

Đối với thất bại của username/password, username có thể do attacker gửi tùy ý và có thể chứa dữ liệu nhạy cảm. Dùng giá trị chuẩn hóa, masked/hash có kiểm soát, hoặc không lưu username nếu không cần thiết. Đừng tin `X-Forwarded-For` nếu gateway chưa cấu hình trust boundary.

**Một số metric nên riêng:**

- `auth_attempts_total`: lần gọi manager hoặc lần thử thực theo định nghĩa của sản phẩm.
- `auth_success_total` / `auth_failure_total`: outcomes, không phải sessions.
- `http_requests_total`: HTTP requests sau ingress.
- `active_sessions`: số session còn sống theo repository/registry.
- `auth_event_delivery_retries_total`: số lần retry đưa event ra hệ thống ngoài.
- `login_users_distinct`: số principal duy nhất trong khoảng đo, cần privacy và định nghĩa chính xác.

Nếu một dashboard tổng hợp các metric này thành một biểu đồ “Số lượt đăng nhập thành công” mà không định nghĩa, kết quả sẽ sai khi chuyển từ session sang stateless hoặc khi thay provider.

## 8. Bảo toàn Authentication và SecurityContext qua nhiều request

Spring Security Servlet thường dùng `SecurityContextHolder` để giữ Authentication trên thread đang xử lý request. `SecurityContextRepository` quyết định cách lưu/khôi phục Authentication khi request tiếp theo đến.

Có ba kho điển hình:

| Repository | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu SecurityContext trong HttpSession | Web login stateful/session cookie |
| `RequestAttributeSecurityContextRepository` | Giữ context trong dispatch của request hiện tại | Error/forward dispatch cần truy cập context |
| `NullSecurityContextRepository` | Không lưu SecurityContext cho request sau | API stateless phải xác thực mỗi request |

Spring Security 6.x mặc định sử dụng `SecurityContextHolderFilter` với mô hình **require explicit save**. Nếu custom filter/controller tự gán context và muốn lưu sang request sau, phải gọi:

```java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

// CHỈ khi cơ chế này thực sự muốn lưu qua request sau:
securityContextRepository.saveContext(
    context, request, response);
```

Đây là **trích đoạn**, với `authenticated` đã được kiểm tra và `securityContextRepository` do ứng dụng cung cấp. Không dùng đoạn này khi chỉ cần stateless request authentication. Nếu custom authentication filter không save mà lại mong login được duy trì ở request sau, lần đầu có thể trả 200 nhưng request thứ hai thành anonymous.

**Điểm quan trọng:** các authentication filters chuẩn như form login xử lý context/session theo cấu hình của framework. Không cần tự chèn `saveContext` vào controller sau form login thông thường.

### 8.1. Stateful session và sự kiện

Một user được xác thực một lần, context lưu trong session, sau đó nhiều request lấy context mà không gọi lại AuthenticationManager. Vì vậy:
- Một user có thể có nhiều request nhưng một manager success event.
- Session hết hạn hoặc logout không “xóa” audit events lịch sử.
- Khi cập nhật quyền ở database, session cũ có thể vẫn giữ authorities đến khi refresh/revalidate.
- Nếu có nhiều ứng dụng instances, cần session store chia sẻ/affinity và xem behavior khi deploy hoặc failover.

### 8.2. Stateless credentials và sự kiện

Với bearer token, API key, mTLS hoặc request signature, mỗi request có thể được xác thực độc lập. Khi filter gọi manager mỗi lần:
- Mỗi request hợp lệ có thể phát một success event.
- Revocation có thể hiệu lực theo tốc độ kiểm tra/caching; không dùng một event cũ để cho phép request mới.
- Client retry tạo thêm request và event nếu cơ chế lặp lại verification.
- Khi scale ngang, counters in-memory của mỗi instance không bằng tổng toàn hệ thống; cần metrics aggregation hoặc durable audit pipeline.

**Không tự lưu API key raw hoặc bearer token vào HttpSession chỉ để giảm event count.** Đó là thay đổi threat model và hành vi thu hồi credential.

## 9. Đồng thời: ThreadLocal, session race và concurrent login

### 9.1. SecurityContextHolder và request threads

`SecurityContextHolder` mặc định dùng chiến lược `MODE_THREADLOCAL` trong Servlet stack. Request threads được pool tái sử dụng; do vậy code custom phải:

- Dựng `SecurityContext` mới sau xác thực thành công.
- Chỉ cho đúng request/thread đang xử lý nhìn thấy Authentication.
- Dọn context trong `finally` sau filter nếu tự quản lý lifecycle.
- Không lưu một `SecurityContext` static toàn cục cho tất cả requests.
- Không đặt Authentication của user A trong async task rồi để user B dùng thread đó.

Ví dụ cơ chế custom request-only:

```java
try {
    SecurityContext context =
        SecurityContextHolder.createEmptyContext();
    context.setAuthentication(authenticated);
    SecurityContextHolder.setContext(context);
    chain.doFilter(request, response);
} finally {
    SecurityContextHolder.clearContext();
}
```

Code này chỉ là trích đoạn trong `OncePerRequestFilter` và **chưa** bao gồm kiểm chứng credential. Bài demo đầy đủ ở phần 11 triển khai cả hai.

Nếu chạy tác vụ không đồng bộ cần context được truyền theo thiết kế (như `DelegatingSecurityContextExecutor` hoặc Spring Security async integration); không giả định ThreadLocal tự lan sang thread mới. Với job long-running, ưu tiên truyền user ID đã xác minh và kiểm tra lại quyền khi thực thi nếu cần.

### 9.2. Cùng một session, hai request đồng thời

Hai request trong cùng browser session có thể bắt đầu gần nhau:

```text
Request A (GET /private/me)            Request B (POST /logout)
  |                                        |
  +-- load SecurityContext cũ              +-- invalidate session
  |                                        |
  +-- controller xử lý                     +-- complete logout
  |
  +-- response đã được xử lý theo snapshot trước logout
```

Việc logout hoàn tất ở request B **không tự hủy tức thời mọi thread đang thực thi request A**. Với hành động cực kỳ nhạy cảm, cần kiểm tra trạng thái account/session/revocation ngay gần transaction commit theo yêu cầu hệ thống; đừng coi một snapshot SecurityContext cũ là khóa toàn cục.

### 9.3. Nhiều phiên trên các thiết bị khác nhau

Spring Security hỗ trợ concurrent session control:

```java
// Trích đoạn SessionManagement DSL cho form login:
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true));
```

Nếu dùng giới hạn session, cấu hình `HttpSessionEventPublisher`/session registry phù hợp theo tài liệu; nhiều-node environment cần giải pháp registry/session store phân tán. Cấu hình này **giới hạn số phiên login**, không biến các authentication events thành exactly-once events.

Nếu `SessionRegistry` dùng custom `UserDetails`, phải bảo đảm `equals()/hashCode()` phù hợp để kiểm soát session chính xác; có nhiều instances thì in-memory registry trên mỗi instance không tự tổng hợp được.

## 10. Thiết kế idempotency và consistency khi sự kiện có side effect

Lắng nghe sự kiện xác thực để tăng bộ đếm metrics thường đơn giản. Nhưng nếu listener kích hoạt:

- Gửi email cảnh báo “đăng nhập mới”;
- Ghi sổ audit tuân thủ;
- Tăng số failed-attempt dẫn đến khóa tài khoản;
- Cập nhật risk score;
- Tạo phiên external hoặc cấp quyền truy cập;
- Gửi event sang pipeline tính phí…

…thì **xử lý trùng có thể gây hậu quả**. Cần phân định operation nào là **idempotent**:

| Side effect | Chiến lược an toàn hơn |
| --- | --- |
| Metrics counter theo event | Gắn định nghĩa metric; nếu tiêu thụ qua broker thì dedup event deliveries hoặc dùng counter tại producer |
| Compliance audit | Append records với event ID ổn định, unique constraint khi retry delivery |
| Email notification | Kiểm soát tần suất theo user/session/device và event ID; không gửi vô hạn khi retry |
| Failed login counter | Đếm **lần thử xác thực thực** theo policy, không đếm duplicate broker delivery; chống bot/distributed attacks |
| External provisioning | Đặt idempotency key cho một operation được ủy quyền, kiểm tra trạng thái đích |
| Critical business transaction | Không thực thi chỉ vì AuthenticationSuccessEvent; cần request hợp lệ, authorization, validation và transaction riêng |

Một mô hình outbox đơn giản:

```text
Authentication outcome -> ứng dụng xác lập audit event
    |
    | durable write trong transaction/đơn vị công việc phù hợp
    v
audit_outbox(event_id UNIQUE, event_type, payload, status)
    |
    | publisher retry khi broker chưa ACK
    v
message broker
    |
    | consumer INSERT ... ON CONFLICT DO NOTHING
    v
audit_event_processed(event_id UNIQUE)
    |
    +--> side effect được thực hiện một lần theo event_id
```

**Cảnh báo kỹ thuật:** sự kiện do `DefaultAuthenticationEventPublisher` phát ra thường là Spring application event trong process, **không phải transactionally persisted outbox**. Một DB transaction để lưu user profile có thể rollback sau khi event auth đã được publish. Nếu phải bảo đảm dữ liệu compliance/audit, hãy thiết kế điểm persist/outbox riêng và xử lý failure của audit sink theo SLA, không chỉ đặt `@EventListener` rồi gọi là “exactly once”.

### 10.1. Java 17 độc lập: dedup giao sự kiện, không dedup credential checks

Để thấy sự khác biệt giữa **event delivery duplicate** và **hai lần login thật**, tạo file `EventDeliveryDemo.java`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class EventDeliveryDemo {

    record Delivery(String eventId, String kind) {}

    public static void main(String[] args) {
        List<Delivery> deliveries = List.of(
            new Delivery("event-001", "AUTH_SUCCESS"),
            new Delivery("event-001", "AUTH_SUCCESS"),
            new Delivery("event-002", "AUTH_SUCCESS"),
            new Delivery("event-003", "AUTH_FAILURE")
        );

        Set<String> processed = new HashSet<>();
        int persisted = 0;

        for (Delivery delivery : deliveries) {
            if (processed.add(delivery.eventId())) {
                persisted++;
                System.out.println("stored "
                    + delivery.eventId() + " " + delivery.kind());
            } else {
                System.out.println("duplicate delivery ignored "
                    + delivery.eventId());
            }
        }

        System.out.println("stored events=" + persisted);
    }
}
```

Chạy Java 17+:

```bash
javac --release 17 EventDeliveryDemo.java
java EventDeliveryDemo
```

Stdout chính xác:

```text
stored event-001 AUTH_SUCCESS
duplicate delivery ignored event-001
stored event-002 AUTH_SUCCESS
stored event-003 AUTH_FAILURE
stored events=3
```

**Diễn giải:** `event-001` bị giao lại nên chỉ ghi một lần, nhưng `event-002` dù cũng là AUTH_SUCCESS vẫn phải được ghi vì đó là một event **khác**. Không có quy tắc “một user chỉ được có một AUTH_SUCCESS”. Set ở ví dụ chỉ nằm trong memory; production cần durable uniqueness/index/concurrency control.

## 11. Ví dụ Spring Boot 3.5.16 + Java 17: hai provider, một publisher

Mẫu Servlet/MVC này cố ý tổ chức:

1. `DaoAuthenticationProvider` cho `UsernamePasswordAuthenticationToken` của browser form login.
2. `ApiKeyAuthenticationProvider` cho `ApiKeyToken` riêng của client machine-to-machine.
3. Một `ProviderManager` chứa hai providers **theo thứ tự tường minh**.
4. Một `DefaultAuthenticationEventPublisher` được gắn vào manager.
5. Một `@EventListener` chỉ ghi counters thread-safe cho manager-level success/failure.
6. **Hai `SecurityFilterChain`:** web formLogin stateful và API-key chain stateless.
7. Endpoint `/private/me` có thể đi qua nhiều request với session; `/api/key/whoami` xác thực lại mỗi request.
8. Audit endpoint chỉ dành cho admin của demo, không đưa raw credentials lên response.

Đây là project thực hành; API key ngẫu nhiên hex 256-bit được cấp qua biến môi trường, demo user/password in-memory và một audit counter trong process. **Không xem đây là production auth server**, vì chưa có database key rotation/revocation, distributed rate limiter, durable audit store hoặc credential management.

### 11.1. Cấu trúc file

```text
auth-events-consistency/
├── pom.xml
├── src/main/resources/application.yml
├── src/main/java/demo/events/AuthEventsApplication.java
└── src/test/java/demo/events/AuthEventsApplicationTests.java
```

### 11.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>auth-events-consistency</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

`spring-boot-starter-security` cung cấp `ProviderManager`, `DaoAuthenticationProvider`, `AuthenticationEventPublisher` và các filter liên quan; không cần thêm một library “authentication events” riêng.

### 11.3. application.yml

```yaml
server:
  port: 8080

app:
  api-key:
    secret: "${APP_API_KEY}"
```

Ứng dụng từ chối startup nếu biến `APP_API_KEY` thiếu/sai format (theo provider bên dưới). Ở production, dùng secret manager để cấp key và lưu verifier; không để key thật trong source/version control. Mã `APP_API_KEY` ở ví dụ phải là 64 ký tự hex lowercase do CSPRNG tạo.

### 11.4. AuthEventsApplication.java (file Java đầy đủ)

Tạo `src/main/java/demo/events/AuthEventsApplication.java`:

```java
package demo.events;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.LongAdder;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.context.event.EventListener;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class AuthEventsApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthEventsApplication.class, args);
    }
}

@Configuration
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("local-demo-password"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(learner);
    }

    @Bean
    DaoAuthenticationProvider passwordProvider(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    ApiKeyProvider apiKeyProvider(
            @Value("${app.api-key.secret}") String secret) {
        return new ApiKeyProvider(secret);
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher publisher) {
        return new DefaultAuthenticationEventPublisher(publisher);
    }

    @Bean
    AuthenticationManager authenticationManager(
            DaoAuthenticationProvider passwordProvider,
            ApiKeyProvider apiKeyProvider,
            AuthenticationEventPublisher publisher) {

        // Một manager chịu trách nhiệm quyết định kết quả.
        ProviderManager manager = new ProviderManager(
            List.of(passwordProvider, apiKeyProvider));

        // Gắn publisher trực tiếp: new ProviderManager(...)
        // không mặc định phát events khi tự khởi tạo.
        manager.setAuthenticationEventPublisher(publisher);
        return manager;
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiKeyChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        ApiKeyFilter apiKeyFilter = new ApiKeyFilter(manager);

        return http
            .securityMatcher("/api/key/**")
            .authenticationManager(manager)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            // Chain CHỈ cho header-based machine API key,
            // không dùng cookie/session làm authentication.
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasAuthority("API_READ"))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            // Tạo local, KHÔNG khai báo @Bean filter;
            // tránh Boot đăng ký filter ngoài SecurityFilterChain.
            .addFilterBefore(
                apiKeyFilter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(
            HttpSecurity http,
            AuthenticationManager manager) throws Exception {

        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/audit").hasRole("ADMIN")
                .requestMatchers("/private/**").authenticated()
                .anyRequest().denyAll())
            // Form Login tự quản lý session và CSRF.
            .formLogin(Customizer.withDefaults())
            .build();
    }
}

/**
 * Token cho API key: raw credential chỉ tồn tại trước xác thực.
 */
final class ApiKeyToken extends AbstractAuthenticationToken {

    private final String principal;
    private String rawKey;

    private ApiKeyToken(
            String principal,
            String rawKey,
            Collection<? extends GrantedAuthority> authorities,
            boolean verified) {
        super(authorities);
        this.principal = principal;
        this.rawKey = rawKey;
        super.setAuthenticated(verified);
    }

    static ApiKeyToken requested(String rawKey) {
        return new ApiKeyToken(null, rawKey, null, false);
    }

    static ApiKeyToken verified(
            String clientId,
            Collection<? extends GrantedAuthority> authorities) {
        return new ApiKeyToken(clientId, null, authorities, true);
    }

    @Override
    public Object getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return rawKey;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        rawKey = null;
    }

    @Override
    public void setAuthenticated(boolean value) {
        if (value) {
            throw new IllegalArgumentException(
                "Use verified factory after credential validation");
        }
        super.setAuthenticated(false);
    }
}

/**
 * Provider cho một API key demo có entropy cao.
 * Mẫu production cần key ID, multiple keys, expiry và revoke store.
 */
final class ApiKeyProvider implements AuthenticationProvider {

    private static final Pattern SECRET_FORMAT =
        Pattern.compile("[0-9a-f]{64}");

    private final byte[] expectedDigest;

    ApiKeyProvider(String secret) {
        if (secret == null ||
                !SECRET_FORMAT.matcher(secret).matches()) {
            throw new IllegalArgumentException(
                "APP_API_KEY must be 64 lowercase hex characters");
        }
        expectedDigest = sha256(secret);
    }

    @Override
    public boolean supports(Class<?> tokenType) {
        return ApiKeyToken.class.isAssignableFrom(tokenType);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        if (!(request instanceof ApiKeyToken token)
                || token.isAuthenticated()) {
            return null;
        }

        Object value = token.getCredentials();
        if (!(value instanceof String key)
                || !SECRET_FORMAT.matcher(key).matches()
                || !MessageDigest.isEqual(
                    expectedDigest, sha256(key))) {
            throw new BadCredentialsException("Invalid API key");
        }

        // Quyền và principal lấy từ server, KHÔNG từ header.
        return ApiKeyToken.verified(
            "integration-reader",
            List.of(new SimpleGrantedAuthority("API_READ")));
    }

    private static byte[] sha256(String secret) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(secret.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 unavailable", ex);
        }
    }
}

/**
 * Chỉ nằm trong /api/key/** security chain.
 * Mỗi request có API key được đưa qua cùng manager;
 * không lưu Authentication vào HttpSession.
 */
final class ApiKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager manager;

    ApiKeyFilter(AuthenticationManager manager) {
        this.manager = manager;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Enumeration<String> headers =
            request.getHeaders("X-API-Key");

        if (!headers.hasMoreElements()) {
            reject(response);
            return;
        }

        String rawKey = headers.nextElement();
        if (headers.hasMoreElements()) {
            // Không nhận nhiều giá trị key trên cùng request.
            reject(response);
            return;
        }

        try {
            Authentication accepted =
                manager.authenticate(ApiKeyToken.requested(rawKey));

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(accepted);
            SecurityContextHolder.setContext(context);

            chain.doFilter(request, response);
        } catch (AuthenticationException rejected) {
            // Publisher đã xử lý failure cho manager outcome.
            // Không tự phát thêm cùng AuthenticationFailureEvent.
            response.sendError(
                HttpServletResponse.SC_UNAUTHORIZED);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private void reject(HttpServletResponse response)
            throws IOException {
        SecurityContextHolder.clearContext();
        response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
    }
}

/**
 * Listener thread-safe, tránh ghi raw credentials và full Authentication.
 * Đây là counters TRONG MỘT JVM, không phải durable global audit.
 */
@org.springframework.stereotype.Component
final class AuthEventCounters {

    private final LongAdder successes = new LongAdder();
    private final LongAdder failures = new LongAdder();

    @EventListener
    void onSuccess(AuthenticationSuccessEvent event) {
        successes.increment();
    }

    @EventListener
    void onFailure(AbstractAuthenticationFailureEvent event) {
        failures.increment();
    }

    long successes() {
        return successes.sum();
    }

    long failures() {
        return failures.sum();
    }
}

@RestController
class Endpoints {

    private final AuthEventCounters events;

    Endpoints(AuthEventCounters events) {
        this.events = events;
    }

    @GetMapping("/health")
    String health() {
        return "ok";
    }

    @GetMapping("/private/me")
    Map<String, String> browserUser(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @GetMapping("/api/key/whoami")
    Map<String, String> apiClient(Principal principal) {
        return Map.of("name", principal.getName());
    }

    @GetMapping("/audit")
    Map<String, Long> audit() {
        return Map.of(
            "successes", events.successes(),
            "failures", events.failures());
    }
}
```

**Các điểm bảo toàn tính nhất quán trong mã:**

- Chỉ có **một** `AuthenticationManager` được chia sẻ, với hai provider tách bằng token type; password không bị “kiểm tra như API key”.
- `ProviderManager.setAuthenticationEventPublisher(...)` được gọi đúng một lần tại điểm tạo manager; event listener không tự publish lại cùng event.
- `@EventListener` chỉ lắng nghe `AuthenticationSuccessEvent` và `AbstractAuthenticationFailureEvent`; không đếm `InteractiveAuthenticationSuccessEvent` vào cùng metric như một lần manager success khác.
- `LongAdder` tránh lost-update ở bộ đếm khi nhiều request đồng thời trong **cùng JVM**.
- API key chain dùng `SessionCreationPolicy.STATELESS` và `NullSecurityContextRepository`; mỗi request API xác thực riêng. Web chain dùng form login/session.
- `ApiKeyFilter` chạy một lần trên đúng chain, bắt `AuthenticationException` và trả 401. Khi thiếu key/duplicate headers, filter từ chối **trước khi gọi manager**, nên **không phát manager failure event** cho những request đó; log HTTP rejection riêng nếu cần audit.
- `ApiKeyToken` có hai dạng: before auth có raw key, after auth có principal/authority từ server và không giữ raw key.
- `MessageDigest.isEqual` so SHA-256 digest demo với key có entropy cao; không lưu plaintext secret trong source. Mẫu production cần key ID/DB/revocation/expiry và limit request sizes.
- Đã đăng nhập browser **không** đồng nghĩa được gọi `/api/key/**` qua session; chain stateless yêu cầu header riêng.
- Một request API key thành công ở manager có thể tiếp tục bị 403 nếu thiếu quyền vào endpoint mới; **success event không đảm bảo HTTP 2xx**.

### 11.5. Chạy trên máy local

Tạo API key ngẫu nhiên bằng OpenSSL:

```bash
export APP_API_KEY="$(openssl rand -hex 32)"
mvn spring-boot:run
```

Chạy ở máy có Java 17+ và Maven. Không in key vào log công cộng hoặc lưu plaintext trong Git. Để test API ở terminal có cùng biến môi trường:

```bash
curl -i http://localhost:8080/health

curl -i http://localhost:8080/api/key/whoami \
  -H "X-API-Key: $APP_API_KEY"

curl -i http://localhost:8080/api/key/whoami
```

Kết quả mong đợi:

- `/health`: HTTP 200, body `ok`.
- API với đúng key: HTTP 200 và JSON `{"name":"integration-reader"}`.
- API thiếu key: HTTP 401, không có success event; đây là request không hề đưa credential cho manager.
- Gọi API với key đúng **lần thứ hai**: có thể có success event **lần thứ hai**, vì chain không nhớ session.
- Mở `http://localhost:8080/private/me` trong browser khi chưa login: chuyển về trang login.
- Đăng nhập `learner` / `local-demo-password` trên **máy học local**; khi login thành công, session cho phép nhiều GET `/private/me`.
- `/audit` chỉ user có `ROLE_ADMIN` mới đọc được metrics in-memory.

**Lưu ý:** shell `export` không tự có ở cửa sổ terminal mới; chia sẻ key cần kênh quản lý secret, không chụp màn hình hoặc paste key vào issue tracker.

## 12. Kiểm thử bằng MockMvc: manager outcome và nhiều request

Bài test dưới đây có hai goals:

1. Chứng minh **hai provider tương ứng hai token type** đều xác thực đúng.
2. Chứng minh **event theo lần manager.authenticate**, không theo số request đã đăng nhập trước đó.

Tạo `src/test/java/demo/events/AuthEventsApplicationTests.java`:

```java
package demo.events;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.api-key.secret=" +
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
})
@AutoConfigureMockMvc
class AuthEventsApplicationTests {

    private static final String KEY =
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    @Autowired
    MockMvc mvc;

    @Autowired
    AuthEventCounters events;

    @Test
    void apiKeyAuthenticatesViaItsOwnProvider()
            throws Exception {
        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name")
                .value("integration-reader"));
    }

    @Test
    void repeatedStatelessRequestsProduceSeparateSuccessEvents()
            throws Exception {
        long before = events.successes();

        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk());

        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key", KEY))
            .andExpect(status().isOk());

        assertThat(events.successes())
            .isEqualTo(before + 2);
    }

    @Test
    void invalidKeyProducesManagerFailureEvent()
            throws Exception {
        long before = events.failures();

        mvc.perform(get("/api/key/whoami")
                .header("X-API-Key",
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"))
            .andExpect(status().isUnauthorized());

        assertThat(events.failures())
            .isEqualTo(before + 1);
    }

    @Test
    void missingKeyIsRejectedBeforeCallingManager()
            throws Exception {
        long before = events.failures();

        mvc.perform(get("/api/key/whoami"))
            .andExpect(status().isUnauthorized());

        assertThat(events.failures())
            .isEqualTo(before);
    }

    @Test
    void passwordLoginSurvivesSubsequentRequestsViaSession()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "local-demo-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);

        assertThat(session).isNotNull();

        mvc.perform(get("/private/me")
                .session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));

        mvc.perform(get("/private/me")
                .session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("learner"));
    }

    @Test
    void badPasswordIsARealAuthenticationFailure()
            throws Exception {
        long before = events.failures();

        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "wrong"))
            .andExpect(status().is3xxRedirection());

        assertThat(events.failures())
            .isEqualTo(before + 1);
    }
}
```

Chạy:

```bash
mvn test
```

Kỳ vọng trong môi trường Java 17+ và dependency phù hợp là **6 test pass**. Đây là dự đoán từ thiết kế, không phải báo cáo đã chạy Maven. Khi các test chạy **song song** hoặc có nhiều test class cùng ghi counters, assertions dựa trên hiệu số trước/sau không còn cô lập hoàn toàn; hãy tắt parallel tests cho fixture này hoặc dùng spy/event collector theo test scope và correlation ID rõ ràng.

**Giới hạn của test:** `MockMvc` mô phỏng Servlet layer, không xác minh reverse proxy, session cluster, network retries, gateway duplication, DB outbox, broker at-least-once delivery hoặc external identity server thật. Các yêu cầu đó cần integration/load/fault-injection tests.

### 12.1. Kết quả nào chứng minh điều gì?

| Test | Điều được chứng minh | Điều chưa được chứng minh |
| --- | --- | --- |
| API key đúng | Provider riêng và manager xử lý được token | Key issuance/rotation và revoke production |
| Hai GET API key | Hai lần gọi manager tạo hai success events trong cùng process | Số login user duy nhất toàn hệ thống |
| API key sai | Một failure event từ manager cho một rejected credential | Rate limiter, account lockout, broker durability |
| Thiếu key | Không có manager failure event nếu filter chặn trước manager | Không có HTTP request; thực tế vẫn có một rejected HTTP request |
| Form login và hai GET | Session tái dùng authentication khi GET sau login | Logout/expired session behavior ở cluster |
| Sai password | Manager phát failure event cho một login attempt | Timing side-channel, brute force defense |

## 13. Lỗi khó: ProviderManager, event publisher và cache

### 13.1. Trùng publisher khi có parent manager

Nếu parent và child đều publish, một outcome có thể đi qua cả hai nơi. Giải pháp không phải kiểm tra “same username trong 5 giây” vì sẽ làm mất các lần login thật sát nhau. Kiểm tra **kiến trúc publisher**, provider routing và event source; nếu cần dedup delivery dùng **event ID do server cấp**, không chỉ username/time.

### 13.2. Duplicate event do listener tự publish lại

`@EventListener` không nên gọi `publisher.publishEvent(event)` trên cùng instance event mà không có guard, vì có thể tạo vòng lặp. Nếu cần chuyển sang một loại event khác, định nghĩa event mới với nghĩa rõ (ví dụ `AuditAuthOutcomeRecorded`) và boundary trách nhiệm.

### 13.3. Erase credentials và cached principal

`ProviderManager` mặc định xóa credentials ở `Authentication` thành công nếu phù hợp `CredentialsContainer`. Đây là hành vi bảo mật tốt, nhưng nếu `Authentication.principal` chia sẻ **cùng một object UserDetails** đang được cache rồi credentials bị xóa, lần xác thực sau có thể gặp vấn đề với password hash đã bị xóa.

Cách đúng là tạo/copy principal an toàn, thiết kế cache không chia sẻ đối tượng bị mutate hoặc cấu hình cache/provider phù hợp. **Không vội tắt `eraseCredentialsAfterAuthentication` trên toàn manager** để chữa lỗi cache, vì sẽ giữ password/token trong session lâu hơn cần thiết.

### 13.4. Provider rơi về local fallback sau khi external outage

Nếu hai providers cùng hỗ trợ `UsernamePasswordAuthenticationToken`, local fallback có thể chấp nhận tài khoản mà external IdP đang đánh dấu locked/revoked. Tránh dùng cùng username namespace hoặc fallback mơ hồ; dùng token type, realm, tenant, chain và provider mapping rõ ràng. Một provider không thể quyết định thì trả `null`; credential sai/trạng thái locked phải thất bại theo contract và threat model.

### 13.5. Event listener chặn request hoặc ném lỗi

Spring application events theo mặc định thường được dispatch đồng bộ, trừ khi cấu hình async. Một listener gửi HTTP hoặc ghi DB chậm có thể làm tăng latency của login; một listener ném unchecked exception có thể ảnh hưởng đường xác thực.

Nếu audit có tính bắt buộc, phải quyết định policy khi audit unavailable (fail-closed hay degraded mode có kiểm soát) và dùng outbox/buffer phù hợp. Nếu metrics có thể chấp nhận mất mẫu trong sự cố, listener nên nhẹ và cô lập lỗi; **không vô tình coi monitoring outage như password sai**.

### 13.6. Event count thay đổi sau khi migration sang stateless

Một app vốn session-based có một auth event lúc login, nhưng khi đổi sang bearer/API key mỗi request, số events có thể tăng lên bằng request rate. Đừng cấu hình “mỗi AuthenticationSuccessEvent gửi email đăng nhập mới” cho API client theo logic cũ; cần threshold/window và loại mechanism.

## 14. Checklist tính nhất quán theo các lớp

| Lớp | Câu hỏi kiểm tra | Quy tắc gợi ý |
| --- | --- | --- |
| Provider | Có nhiều provider hỗ trợ cùng token type không? | Định nghĩa rõ thứ tự/fallback và trạng thái account |
| Manager | Có shared parent không? | Tránh double publication, chứng minh final outcome |
| Event publisher | Tự tạo ProviderManager đã được gắn publisher chưa? | Một publisher có ownership rõ |
| Exception mapping | Custom exception có event không? | Cấu hình exact mapping/fallback và test |
| Filter | Một request có thể authenticate hai lần do filter auto-register không? | Quản lý SecurityFilterChain và FilterRegistration |
| Session | Browser GET sau login có reauthenticate không? | Kiểm tra SecurityContextRepository và session mode |
| Stateless | Key/bearer được kiểm chứng mỗi request không? | Không dùng session event count làm request count |
| Retry | Retry mạng có tạo authentication attempt mới không? | Phân loại retry nội bộ/HTTP/event delivery |
| OTP | Token đã consume có bị reuse không? | Một lần sử dụng theo policy, chống replay |
| Concurrency | Counter và event processing có thread-safe không? | LongAdder/DB atomic updates/unique constraints |
| Audit | Sự kiện phải durable không? | Transactional outbox, event ID, replay và dedup |
| Security | Có log raw password/token không? | Redaction, least privilege, retention |
| Authorization | Auth event success có nhầm với business operation success không? | Kiểm tra quyền riêng ở API/service |
| Deployment | Nhiều instance có chia sẻ session/counters không? | Session store/metrics aggregation/outbox |

**Định nghĩa acceptance criteria trước khi triển khai**, ví dụ: “Một lần manager.authenticate cuối cùng success chỉ phát một manager success event tại publisher được sở hữu; một event outbox retry cùng ID không được gây side effect hai lần; hai request API key độc lập phải tạo hai auth attempts; browser GET có session không tự làm tăng login counter.”

## 15. Chẩn đoán những hiện tượng thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Login thành công nhưng không có `AuthenticationSuccessEvent` | Tự tạo manager chưa gắn publisher; listener không đăng ký | Kiểm tra `setAuthenticationEventPublisher` và component scan |
| Có hai success events cho một login | Parent/child publisher trùng; filter hai lần; hoặc `InteractiveAuthenticationSuccessEvent` bị cộng nhầm | Kiểm tra event class, call stack, manager graph |
| Password sai ở provider A nhưng provider B cho login | ProviderManager fallback, cả hai hỗ trợ token | Kiểm tra supports/order và account namespace |
| Account locked vẫn login được ở provider khác | Provider tự diễn giải status sai hoặc bỏ qua chính sách | Bảo đảm account status failure dừng đúng và provider không bypass |
| API key request nào cũng tăng login counter | API stateless gọi manager trên mỗi request | Tách metric auth request khỏi session login |
| Browser GET sau login không phát success event mới | Dùng SecurityContext từ session | Bình thường; không ép reauthenticate chỉ để phát event |
| Logout rồi GET cũ vẫn được xử lý | Request đã bắt đầu trước logout hoặc session chưa revoke ở cluster | Đánh giá race, session invalidation, policy transactional |
| Custom login lần đầu thành công, request sau anonymous | Custom filter chỉ set context mà không save repository | Gọi saveContext nếu muốn stateful; kiểm tra session |
| Hai request cùng account làm mất số lần failure | Bộ đếm `int++` không atomic, cache không đồng bộ | AtomicLong/LongAdder hoặc DB atomic update |
| Broker redeliver làm email cảnh báo gửi 2 lần | Consumer thiếu dedup/outbox | Dùng eventId duy nhất và unique constraint |
| Listener lỗi làm POST login 500 | Đồng bộ listener ném exception | Cô lập side effect, cân nhắc audit guarantee policy |
| Custom subclass `AuthenticationServiceException` không có failure event | Default mapping exact exception class | Set additional mappings/fallback |
| Lần thử bị quota chặn nhưng không có auth failure event | Rate limiter chặn trước manager | Audit thêm security rejection event riêng |
| Có 403 dù authentication success event đã phát | AuthorizationFilter thiếu role/scope | Authn success không phải authorization success |
| Không phân biệt network retry và user login lại | Thiếu request ID/attempt ID, log không liên kết | Trace/correlation và idempotency design |
| JWT bị revoke nhưng cache vẫn cho request | Stale token validation/cache/state | Chọn TTL/invalidation phù hợp, fail-closed |

**Quy trình debug tối thiểu:**

1. Request đến đúng chain/filter và chỉ chạy filter một lần?
2. Manager nào được dùng? Có parent? Provider order và `supports(...)` thế nào?
3. Với một call `authenticate(...)`: provider nào trả non-null/null/exception? Kết quả cuối là gì?
4. `AuthenticationEventPublisher` nào được manager dùng? Cả parent và child cùng publish không?
5. Listener đang đếm loại event nào? Có cộng lẫn `InteractiveAuthenticationSuccessEvent`?
6. Request dùng session hay stateless? Request thứ hai có manager invocation thật không?
7. Client/gateway có HTTP retry? Event pipeline có broker redelivery?
8. Counters/audit stores có thread-safe, shared giữa instances và dedup không?
9. Authentication đã thành công nhưng authorization/business transaction có bị từ chối/rollback ở bước sau không?
10. Có rò credentials, session ID hoặc raw exception trong log/tracing không?

Không log full Authentication credentials hoặc exception chứa secret chỉ để debug; dùng correlation ID và exception class/category đã lọc.

## 16. Các câu hỏi tự kiểm tra

1. **Một lần `authenticate` đi qua hai providers có mặc nhiên tạo hai sự kiện authentication?** Không. `ProviderManager` chuẩn publish theo final outcome; custom providers có thể tự phát các sự kiện khác nếu ứng dụng thiết kế.
2. **Provider A ném BadCredentials nhưng B thành công thì manager trả gì?** Kết quả của B; lỗi trước không còn là final outcome.
3. **Provider A ném LockedException thì có tiếp tục B không?** Theo `AccountStatusException` contract, không tiếp tục các providers còn lại.
4. **Tự `new ProviderManager(...)` đã có events mặc định chưa?** Không được giả định; gắn `AuthenticationEventPublisher` rõ ràng.
5. **Tại sao parent/child manager có thể tạo event trùng?** Cả parent và child đều có thể publish outcome mà child nhận từ parent.
6. **Một browser GET có session hợp lệ có bắt buộc phát AuthenticationSuccessEvent không?** Không. Nó có thể chỉ load SecurityContext.
7. **Hai GET API key cùng key có thể phát hai success events không?** Có, nếu manager được gọi ở mỗi request stateless.
8. **AuthenticationSuccessEvent có bảo đảm controller đã trả HTTP 200 không?** Không; authorization, validation hoặc service còn có thể từ chối/thất bại.
9. **Custom AuthenticationException subclass có tự mapped vào parent exception event không?** Không mặc nhiên; default publisher mapping exact class, nên cần mapping nếu cần.
10. **Dùng username và timestamp để dedup mọi authentication events có chính xác không?** Không; hai login thật có thể gần nhau và chia sẻ username.
11. **Bộ đếm LongAdder trong demo có bảo đảm audit cluster không?** Không; chỉ thread-safe trong JVM.
12. **Auth retry từ gateway và broker redelivery khác gì?** Gateway có thể tạo authentication attempt mới; broker redelivery gửi lại cùng audit event.
13. **Có thể bỏ kiểm chứng key khi client gửi lại idempotency key cũ?** Không. Idempotency không được biến thành bypass authentication.
14. **Vì sao custom filter muốn session persistence phải saveContext?** Spring Security 6+ dùng explicit-save behavior cho context do custom code tự set.
15. **SessionConcurrency maximumSessions(1) có bảo đảm chỉ một auth success event mỗi user?** Không. Nó là chính sách phiên, không phải event de-duplication.
16. **Nếu listener gửi mail bị lỗi thì login nên ra sao?** Được quyết định theo policy và bảo đảm audit/availability; không được ngẫu nhiên biến nó thành “bad password”.
17. **Đăng nhập bị rate limiter từ chối trước manager sẽ có manager failure event không?** Không nhất thiết; cần request/security rejection metrics riêng.
18. **Vì sao khi cache UserDetails phải quan tâm `eraseCredentialsAfterAuthentication`?** Vì chia sẻ object bị erase có thể làm dữ liệu kiểm tra ở cache bị xóa ngoài dự kiến.
19. **Làm sao chứng minh retry delivery không gây side effect trùng?** Dùng event ID bền vững, unique constraint và test gửi lại cùng ID.
20. **Một provider có thể trả null để “chờ provider khác” không?** Có, nhưng credential sai/trạng thái account cần được biểu diễn đúng, không dùng null để che lỗi an ninh.

## 17. Tài liệu chính thức

- Spring Security 6.5 – Authentication Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 – Authentication Events: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html
- Spring Security – ProviderManager API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html
- Spring Security – AuthenticationProvider API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationProvider.html
- Spring Security – DefaultAuthenticationEventPublisher API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html
- Spring Security 6.5 – DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 – Session Management and Explicit Save: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security – SecurityContext persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security – Servlet Security Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security – MockMvc Testing: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html
- Spring Security – Concurrent Session Control: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html#_configuring_concurrent_session_control
- Spring Security – DelegatingSecurityContextExecutor: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/concurrency.html
- OWASP – Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP – Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
