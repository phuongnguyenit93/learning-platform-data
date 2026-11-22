# Tùy chỉnh introspector bằng phép hợp thành phản ứng

## 1. Bối cảnh: vì sao cần tùy chỉnh introspection trong WebFlux?

Trong **Spring Security OAuth 2.0/OIDC Resource Server** chạy **Spring WebFlux**, API có thể xác thực Bearer access token bằng **OAuth 2.0 Token Introspection** theo RFC 7662. Thay vì tự xác minh chữ ký JWT bằng public key, Resource Server gửi chuỗi token tới một introspection endpoint đáng tin cậy và hỏi Authorization Server (AS) xem token có còn được công nhận hay không.

Ví dụ client gọi:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer Aq6p7W...opaque-access-token...
```

Resource Server gửi tới AS:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <introspection-client-credential>
Content-Type: application/x-www-form-urlencoded

token=Aq6p7W...opaque-access-token...
```

AS có thể trả:

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "scope": "orders:read orders:export",
  "tenant_id": "tenant-a",
  "exp": 1893456000
}
```

Tình huống phổ biến: AS trả `active=true` và scope hợp lệ, nhưng ứng dụng còn muốn:

1. Chỉ nhận token dành cho **`orders-api`**, không phải `payments-api`.
2. Giới hạn issuer/client registration được tin cậy theo hợp đồng.
3. Chuẩn hóa authorities từ metadata đã được AS xác nhận mà **không cấp thêm quyền vô ý**.
4. Bổ sung metric, tracing, timeout hoặc một giới hạn cache an toàn.
5. Duy trì đường xử lý **không blocking**, không biến lỗi xác thực thành thành công.

Điểm mở rộng chính trong WebFlux là **`ReactiveOpaqueTokenIntrospector`**. Cách tùy chỉnh thường hiệu quả là **phép hợp thành phản ứng** (*reactive composition*): bọc một introspector tin cậy, nhận `Mono<OAuth2AuthenticatedPrincipal>`, dùng các Reactor operators để thẩm định/biến đổi kết quả, rồi trả một `Mono` mới.

> **Nguyên tắc:** Hãy **hợp thành thêm những bảo đảm** quanh bước introspection gốc; đừng thay nó bằng việc tự đọc token, bỏ qua `active` hoặc tạo principal khi AS không xác minh được token.

## 2. Introspector giữ vai trò nào trong chuỗi WebFlux?

Đường xử lý khái niệm:

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as AuthenticationWebFilter
    participant M as OpaqueTokenReactiveAuthenticationManager
    participant D as Decorator Introspector
    participant R as Remote Reactive Introspector
    participant AS as Authorization Server
    participant A as AuthorizationWebFilter
    C->>F: Authorization: Bearer token
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>D: introspect(rawToken)
    D->>R: delegate.introspect(rawToken)
    R->>AS: POST introspection + client auth
    AS-->>R: active + metadata
    alt Token inactive hoặc introspection error
        R-->>D: Mono.error(...)
        D-->>M: Mono.error(...)
        M-->>F: Authentication failure
        F-->>C: 401 / lỗi phù hợp
    else Token được AS xác nhận
        R-->>D: Mono<OAuth2AuthenticatedPrincipal>
        D->>D: Audience / issuer / attributes / authorities
        alt Local token contract không đạt
            D-->>M: Mono.error(...)
            M-->>F: Authentication failure
        else Local token contract đạt
            D-->>M: Mono<OAuth2AuthenticatedPrincipal>
            M-->>F: BearerTokenAuthentication
            F->>A: Reactor SecurityContext
            A-->>C: 2xx hoặc 403 theo quyền
        end
    end
```

Các thành phần đáng nhớ:

| Thành phần | Vai trò |
| --- | --- |
| `SecurityWebFilterChain` | Chọn luồng bảo mật HTTP reactive. |
| `ServerHttpSecurity` | DSL cấu hình Resource Server WebFlux. |
| `AuthenticationWebFilter` | Chuyển request thành Authentication token chưa xác thực rồi gọi reactive manager. |
| `OpaqueTokenReactiveAuthenticationManager` | Gọi `ReactiveOpaqueTokenIntrospector` để xác thực token. |
| `ReactiveOpaqueTokenIntrospector` | Hợp đồng introspection trả `Mono<OAuth2AuthenticatedPrincipal>`. |
| `SpringReactiveOpaqueTokenIntrospector` | Implementation dùng HTTP reactive để hỏi AS, tùy version. |
| `OAuth2AuthenticatedPrincipal` | Dữ liệu principal, attributes và granted authorities đã được introspector chấp nhận. |
| `BearerTokenAuthentication` | Authentication cho token đã được manager xác thực qua introspection. |
| `AuthorizationWebFilter` và reactive method security | Kiểm tra quyền dựa trên authentication đã có. |

**Không nhầm WebFlux với Servlet**. Servlet dùng `OpaqueTokenIntrospector` đồng bộ trả thẳng `OAuth2AuthenticatedPrincipal`, còn WebFlux dùng `ReactiveOpaqueTokenIntrospector` trả `Mono`. Tương tự, Servlet dùng `HttpSecurity`/`SecurityFilterChain`; WebFlux dùng `ServerHttpSecurity`/`SecurityWebFilterChain`.

### 2.1. Introspection không đồng nghĩa authorization đầy đủ

AS có thể trả `active=true` cho token thuộc hệ sinh thái OAuth của mình. API vẫn phải quyết định token đó có đúng **resource**, có đúng **scope**, và principal có quyền trên **tài nguyên cụ thể** hay không.

Ví dụ user A có `SCOPE_orders:read` không có nghĩa họ được đọc đơn hàng của user B. Introspector thường xử lý **hợp đồng token**; owner/tenant access trên `orderId` cần được kiểm soát ở service/repository/authorization layer.

## 3. Hợp đồng ReactiveOpaqueTokenIntrospector

Giao diện chính:

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

Đoạn trên mô tả chữ ký cốt lõi; class thật nằm ở package `org.springframework.security.oauth2.server.resource.introspection`.

Với phép hợp thành, phải hiểu ba tín hiệu của `Mono`:

| Tín hiệu | Ý nghĩa | Quy tắc bảo mật |
| --- | --- | --- |
| `onNext(principal)` rồi `onComplete()` | Introspection đã trả principal được chấp nhận theo đường delegate. | Tiếp tục kiểm tra policy bổ sung trước khi cho manager tạo Authentication. |
| `onError(error)` | Token bị từ chối hoặc có lỗi khi xác minh. | **Không tạo principal**, chuyển lỗi phù hợp. |
| Chỉ `onComplete()`, không có principal | Không có kết quả introspection. | **Fail-closed**; không coi empty là token hợp lệ. |

Một introspector hợp lệ không nên trả `Mono.just(...)` từ chuỗi token chưa được AS xác nhận, trừ khi nó chính là một **trusted implementation** khác đã xác minh token bằng hợp đồng tương đương.

### 3.1. Tính lười thực thi của Mono

Trong mô hình Reactor, các toán tử như `map`, `flatMap` và `doOnError` thường chỉ mô tả pipeline; network call được thực hiện khi có subscription. Ví dụ:

```java
Mono<OAuth2AuthenticatedPrincipal> result =
        delegate.introspect(rawToken)
                .map(principal -> transform(principal));
```

Trong WebFlux, framework subscribe vào chuỗi xử lý HTTP. Không nên gọi `.block()` hoặc `.subscribe()` thủ công trong authentication path chỉ để lấy principal “ngay lập tức”.

```java
// SAI: chặn reactive request thread.
OAuth2AuthenticatedPrincipal principal =
        delegate.introspect(rawToken).block();

// SAI: tự subscribe rồi trả principal khác khi chưa xác minh xong.
delegate.introspect(rawToken).subscribe();
return Mono.just(makeDefaultPrincipal());
```

### 3.2. Các exception thông dụng

`BadOpaqueTokenException` đại diện tình huống token opaque không hợp lệ/không được chấp nhận. `OAuth2IntrospectionException` mô tả lỗi liên quan quá trình introspection. Các exception phải được xử lý phù hợp với version Spring Security và error policy của hệ thống.

**Lỗi AS timeout hoặc credential introspection sai** khác với **AS trả `active=false`**. Cả hai đều phải fail-closed, nhưng phân loại vận hành khác nhau.

## 4. Phép hợp thành phản ứng là gì?

Thay vì kế thừa hoặc sửa implementation HTTP của Spring Security, ta xây một **decorator**:

```text
External Bearer token
       |
       v
ReactiveOpaqueTokenIntrospector (custom decorator)
       |
       +-- delegate.introspect(token)
       |      |
       |      +-- HTTP introspection qua endpoint tin cậy
       |      +-- active=false -> error
       |      +-- active=true  -> OAuth2AuthenticatedPrincipal
       |
       +-- validate audience/issuer/client contract
       +-- map/limit authorities khi cần
       +-- observe latency/error category an toàn
       |
       +-- return Mono<OAuth2AuthenticatedPrincipal>
```

Các toán tử Reactor phù hợp:

| Toán tử | Khi nào dùng | Cảnh báo |
| --- | --- | --- |
| `map` | Biến đổi đồng bộ một principal đã có, ví dụ ánh xạ authorities. | Không đặt HTTP/JDBC blocking vào `map`. |
| `flatMap` | Policy trả một `Mono`, ví dụ kiểm tra async hoặc trả `Mono.error` có điều kiện. | Không phát principal nếu policy thất bại. |
| `filter` | Giữ phần tử đáp ứng predicate. | `filter` có thể trả **Mono.empty()**; với authentication, nên đổi từ chối thành lỗi rõ ràng. |
| `switchIfEmpty` | Xử lý trường hợp không có principal. | Nên **fail-closed**, không tạo fallback admin/user. |
| `doOnNext` / `doOnSuccess` | Ghi metric/event quan sát. | Không log token, secret hoặc attributes chứa PII. |
| `doOnError` | Quan sát lỗi, phân loại nội bộ. | Không nuốt lỗi hoặc ghi nguyên exception message bừa bãi. |
| `timeout` | Giới hạn thời gian chờ introspection. | Timeout phải dẫn tới deny/lỗi dependency, không cấp quyền. |
| `onErrorMap` | Chuyển exception sang nhóm lỗi phù hợp. | Không xóa mất khác biệt token inactive và upstream outage trong vận hành. |
| `retryWhen` | Retry bounded cho một số lỗi mạng tạm thời. | Không retry mọi lỗi hoặc token `active=false`. |
| `defer` | Tạo pipeline tại thời điểm subscribe khi cần. | Không làm phát sinh nhiều lượt introspection ngoài ý muốn. |
| `contextWrite` / `deferContextual` | Đọc hoặc bổ sung Reactor Context theo policy. | Context không phải nguồn xác thực của Bearer token. |

### 4.1. Vì sao decorator thường tốt hơn viết lại remote introspector?

Một implementation HTTP introspection đã phải xử lý nhiều chi tiết:

- HTTP POST với `application/x-www-form-urlencoded`.
- Client authentication của Resource Server, có thể gồm Basic hoặc cơ chế được AS hỗ trợ.
- Xử lý `active`, response JSON và chuyển đổi metadata.
- Phân loại HTTP errors, timeout và transport failures.
- Bảo vệ credential khi gọi tới endpoint.

Nếu chỉ cần **thêm audience validator hoặc hạn chế authorities**, viết lại cả HTTP client làm tăng nguy cơ sai protocol. Decorator giữ nguyên một delegate đã được cấu hình đúng và chỉ thêm những bước cần thiết.

## 5. Ví dụ 1: decorator kiểm tra audience một cách fail-closed

Giả sử AS cam kết trả `aud` trong introspection response và API chỉ nhận token dành cho `orders-api`.

Một implementation độc lập:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class AudienceCheckingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
                .switchIfEmpty(Mono.error(
                        new BadOpaqueTokenException(
                                "No principal from introspection")))
                .flatMap(principal -> {
                    Object aud = principal.getAttribute("aud");

                    boolean matches =
                            (aud instanceof String one
                                    && expectedAudience.equals(one))
                            || (aud instanceof Collection<?> many
                                    && many.contains(expectedAudience));

                    return matches
                            ? Mono.just(principal)
                            : Mono.error(new BadOpaqueTokenException(
                                    "Token is not intended for this API"));
                });
    }
}
```

**Cách hoạt động:**

1. `delegate.introspect(token)` là nơi thực hiện remote introspection và đánh giá `active`.
2. Nếu delegate báo lỗi, `Mono.error` được truyền tiếp; `flatMap` không chạy.
3. Nếu delegate hoàn thành rỗng, `switchIfEmpty` chuyển thành lỗi, **không cho qua**.
4. Nếu đã có principal, policy kiểm tra `aud` là **exact string** hoặc collection chứa exact string.
5. Nếu `aud` thiếu, sai kiểu hoặc sai resource, trả `BadOpaqueTokenException`.
6. Chỉ khi mọi điều kiện đạt mới trả **chính principal từ delegate**.

Giả sử:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "orders:read"
}
```

Token vẫn phải bị từ chối ở `orders-api`, dù AS trả `active=true` và token có `orders:read`.

### 5.1. Tại sao không dùng filter một mình?

Có thể viết:

```java
return delegate.introspect(token)
        .filter(principal -> hasAudience(principal, "orders-api"));
```

Nhưng khi audience không khớp, kết quả là **`Mono.empty()`**, không phải một failure được phân loại rõ. Tùy manager/composition, empty có thể được hiểu là không đưa ra quyết định hoặc gây lỗi khác. Với **authentication**, lựa chọn an toàn và dễ chẩn đoán là phát `Mono.error(new BadOpaqueTokenException(...))`.

### 5.2. Nếu AS không trả aud?

RFC 7662 không buộc mọi AS trả đầy đủ `aud` cho mọi token. Nếu policy API bắt buộc resource-binding, việc không có `aud` **không thể mặc nhiên được xem là pass**.

Có hai hướng đúng:

- Yêu cầu AS trả `aud` theo **introspection contract**.
- Hoặc tài liệu hóa một cơ chế tương đương: AS chỉ trả `active=true` cho token dành đúng Resource Server đang xác thực bằng client registration/credential đó, và có integration test chứng minh.

Không suy đoán rằng **mọi** `active=true` đều dành cho API hiện tại.

## 6. Ví dụ 2: xác minh issuer và client theo hợp đồng

Nếu Resource Server chấp nhận token từ một issuer cụ thể, và introspection response công bố `iss`, có thể ghép thêm điều kiện:

```java
private static Mono<OAuth2AuthenticatedPrincipal> requireIssuer(
        OAuth2AuthenticatedPrincipal principal,
        String trustedIssuer) {

    Object issuer = principal.getAttribute("iss");

    return trustedIssuer.equals(issuer)
            ? Mono.just(principal)
            : Mono.error(new BadOpaqueTokenException(
                    "Unexpected token issuer"));
}
```

Kết hợp:

```java
return delegate.introspect(token)
        .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException("No introspection result")))
        .flatMap(principal -> requireIssuer(
                principal, "https://login.example.test"))
        .flatMap(principal -> requireAudience(
                principal, "orders-api"));
```

`requireAudience` trong ví dụ là helper tương đương policy ở mục 5, được trích thành method riêng để giảm lặp. Đây là **pipeline minh họa**, không phải một class đầy đủ cho copy/paste.

### 6.1. Không lấy issuer từ token chưa được xác minh

Không làm:

```java
// SAI: issuer/endpoint được tạo từ input của client.
String uri = request.getHeader("X-Introspection-URL");
ReactiveOpaqueTokenIntrospector delegate =
        buildIntrospector(uri, clientSecret);
```

Introspection endpoint và credentials phải đến từ **cấu hình được tin cậy**. Cho client chọn endpoint có thể gây SSRF hoặc làm lộ Basic credentials của Resource Server.

### 6.2. client_id trong response không phải client_id của Resource Server

Trong introspection response:

```json
{
  "active": true,
  "client_id": "orders-mobile",
  "scope": "orders:read"
}
```

`client_id` thường chỉ **OAuth client được cấp access token**. Nó có thể khác `client_id` mà Resource Server dùng **để xác thực khi gọi introspection endpoint**.

API có thể kiểm tra allowlist OAuth client IDs nếu contract yêu cầu:

```java
Set<String> permittedClients =
        Set.of("orders-web", "orders-mobile");

Object clientId = principal.getAttribute("client_id");
boolean allowed =
        clientId instanceof String value
        && permittedClients.contains(value);
```

Nhưng đây là **policy bổ sung theo token profile**, không thay kiểm tra scope/audience. Không dùng tiền tố hoặc substring `startsWith("orders")` nếu client IDs là danh tính chính xác.

## 7. Ghép các bước bằng một policy pipeline có thể tái sử dụng

Khi có nhiều điều kiện, đặt tất cả trong một `flatMap` sẽ khó đọc. Có thể tách các policy thành những hàm cùng hợp đồng:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class ComposedReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final List<Function<
            OAuth2AuthenticatedPrincipal,
            Mono<OAuth2AuthenticatedPrincipal>>> steps;

    public ComposedReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            List<Function<
                    OAuth2AuthenticatedPrincipal,
                    Mono<OAuth2AuthenticatedPrincipal>>> steps) {
        this.delegate = Objects.requireNonNull(delegate);
        this.steps = List.copyOf(steps);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        Mono<OAuth2AuthenticatedPrincipal> result =
                delegate.introspect(token);

        for (var step : steps) {
            result = result.flatMap(step);
        }

        return result.switchIfEmpty(Mono.error(
                new BadOpaqueTokenException(
                        "Introspection policy did not produce a principal")));
    }
}
```

Tạo các bước:

```java
var composed = new ComposedReactiveIntrospector(
        remoteIntrospector,
        List.of(
                principal -> requireIssuer(
                        principal, "https://login.example.test"),
                principal -> requireAudience(
                        principal, "orders-api"),
                principal -> requireAllowedClient(
                        principal, permittedClients)));
```

`requireIssuer`, `requireAudience` và `requireAllowedClient` là helpers áp dụng policy; có thể được viết để trả `Mono.just(principal)` khi pass và `Mono.error(...)` khi fail. Việc dùng `List.copyOf` bảo đảm danh sách steps không bị thay đổi từ bên ngoài sau khi khởi tạo.

### 7.1. Thứ tự có thể ảnh hưởng hiệu năng và thông tin

Giả sử một bước chỉ kiểm tra string `aud`, bước sau cần gọi một reactive user registry để xác định actor. Hãy chạy **kiểm tra rẻ và thuần dữ liệu** trước, rồi mới xét bước có chi phí I/O khi contract thực sự cần.

Nhưng đừng phụ thuộc “thứ tự trả lỗi” để cung cấp cho client danh sách issuer/audience tin cậy. Response công khai vẫn nên tối giản; error categories chi tiết chỉ dành cho telemetry nội bộ đã redaction.

### 7.2. Không phải mọi policy đều nên nằm trong introspector

Nếu điều kiện phụ thuộc **`orderId` của request**, như “user có sở hữu đơn hàng này không?”, `introspect(String token)` **không có tham số orderId**. Ép introspector đọc request context bên ngoài để kiểm tra ownership tạo coupling và dễ lỗi với Reactor Context/async.

Hãy chia:

- **Introspector**: trạng thái token, resource audience, issuer/client contract, điều kiện về principal metadata.
- **Method/domain authorization**: scope của hành động, user/tenant membership, owner của tài nguyên, trạng thái đơn hàng.

## 8. Ví dụ 3: ánh xạ và giới hạn authorities theo hợp đồng

Spring Security thường ánh xạ scope từ introspection response:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export"
}
```

Thành:

```text
SCOPE_orders:read
SCOPE_orders:export
```

Tuy nhiên, một API có thể muốn **giữ lại đúng các authorities được công nhận**. Ta có thể dùng `map` vì đây là bước xử lý thuần trong bộ nhớ:

```java
import java.util.List;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

private static OAuth2AuthenticatedPrincipal restrictAuthorities(
        OAuth2AuthenticatedPrincipal principal) {

    Set<String> accepted = Set.of(
            "SCOPE_orders:read",
            "SCOPE_orders:export");

    List<GrantedAuthority> filtered =
            principal.getAuthorities().stream()
                    .filter(authority ->
                            accepted.contains(authority.getAuthority()))
                    .toList();

    return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            filtered);
}
```

Ghép sau introspection và policy:

```java
return delegate.introspect(token)
        .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException("Missing principal")))
        .flatMap(principal -> requireAudience(
                principal, "orders-api"))
        .map(MyAuthorityPolicy::restrictAuthorities);
```

Trong ví dụ, `MyAuthorityPolicy` là lớp do ứng dụng định nghĩa chứa helper `restrictAuthorities`. Dữ liệu từ `getAttributes()` được giữ để phục vụ những policy khác, còn `getAuthorities()` dùng để quyết định quyền ở Spring Security.

### 8.1. Cẩn thận với authorities không phải scope

Một số phiên bản Spring Security có thể thêm authority mô tả **authentication factor** hoặc thông tin cơ chế xác thực, không chỉ `SCOPE_...`. Nếu lọc sạch toàn bộ authorities khác allowlist scope, ứng dụng có thể làm thay đổi những policy dựa trên authorities khác.

Vì vậy:

- Hiểu **toàn bộ authority contract** của phiên bản framework.
- Chỉ giới hạn authorities theo policy được phê duyệt.
- Test cả quyền được giữ và quyền bị loại.
- Không tự thêm `ROLE_ADMIN` hoặc `SCOPE_orders:write` chỉ vì `client_id` hoặc email trông giống admin.

### 8.2. Không nên dùng map để cấp thêm quyền

Ví dụ nguy hiểm:

```java
// SAI: biến mọi token active thành admin.
List<GrantedAuthority> authorities =
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"));
```

Hợp thành introspector là điểm mở rộng nhạy cảm: bất kỳ authority nào được thêm ở đây sẽ được authorization layer nhìn nhận như quyền của principal. Chỉ thêm quyền khi AS đã xác nhận dữ liệu nguồn, policy mapping có allowlist và có test chống privilege escalation.

### 8.3. Attributes và authorities có thể khác cách biểu diễn

Nếu filter authorities nhưng để lại raw `scope` trong attributes, code downstream nào đó tự đọc `scope` có thể hiểu khác policy đã lọc. Hãy quy định:

**Spring Security authorization dựa vào `Authentication.getAuthorities()` được chuẩn hóa**; code nghiệp vụ không tự parse raw `scope` để cấp quyền theo cách riêng.

Để truy vết, có thể giữ raw claims trong principal nội bộ theo quyền truy cập, nhưng không gửi toàn bộ attributes cho HTTP caller.

## 9. Bước đồng bộ thì dùng map; bước bất đồng bộ thì dùng flatMap

Ví dụ:

```java
return delegate.introspect(token)
        // Đồng bộ, không I/O.
        .map(MyAuthorityPolicy::restrictAuthorities)
        // Reactive policy trả Mono.
        .flatMap(principal ->
                accountStatusPolicy.requireEligibleAccount(principal));
```

Giả sử `accountStatusPolicy.requireEligibleAccount` trả `Mono<OAuth2AuthenticatedPrincipal>` và không tạo principal khi tài khoản không hợp lệ.

**Không làm**:

```java
// SAI: map tạo Mono<Mono<Principal>> thay vì Mono<Principal>.
return delegate.introspect(token)
        .map(principal ->
                accountStatusPolicy.requireEligibleAccount(principal));
```

Với `flatMap`, Reactor chờ kết quả của async operation rồi mới tiếp tục. Tránh ép dữ liệu không đồng bộ thành boolean bằng `.block()`.

### 9.1. Có nên truy vấn membership trong introspector?

Nếu một account status hoặc tenant membership **thực sự là điều kiện chấp nhận token đối với cả API**, có thể cân nhắc một bước reactive check theo contract. Tuy nhiên, việc đó:

- Thêm dependency database vào mọi authentication.
- Tăng latency và tạo thêm trường hợp lỗi.
- Có thể khiến kiểm tra tài khoản thay đổi tần suất theo caching.
- Không thay object-level policy cho từng order.

Với đa số ứng dụng, tốt hơn là giữ introspector xác minh **access-token contract**, và dùng **reactive authorization/service layer** cho quyền động trên dữ liệu.

### 9.2. Gọi database đồng bộ trong map là anti-pattern

```java
// SAI: JDBC có thể blocking trên Netty event-loop.
return delegate.introspect(token)
        .map(principal -> {
            jdbcTemplate.queryForObject(
                    "select active from accounts where id=?",
                    Boolean.class,
                    principal.getName());
            return principal;
        });
```

Với WebFlux, dùng reactive driver/repository hoặc thực hiện bounded scheduling cho legacy blocking I/O trong một lớp tách biệt, có capacity planning. Không tự dùng `Mono.just(jdbcCall())`, vì lời gọi blocking xảy ra **trước khi Mono được tạo**.

## 10. Ví dụ 4: kiểm tra metadata có kiểu dữ liệu rõ ràng

Introspection response có thể trả claims dưới nhiều kiểu JSON. Policy không nên dùng `toString()` cho mọi loại:

```json
{"active":true,"tenant_id":"tenant-a"}
```

khác với:

```json
{"active":true,"tenant_id":{"id":"tenant-a"}}
```

Nếu token contract yêu cầu `tenant_id` là string giới hạn cú pháp:

```java
private static Mono<OAuth2AuthenticatedPrincipal> requireTenantClaim(
        OAuth2AuthenticatedPrincipal principal) {

    Object raw = principal.getAttribute("tenant_id");

    if (raw instanceof String tenant
            && tenant.matches("[a-zA-Z0-9_-]{1,64}")) {
        return Mono.just(principal);
    }

    return Mono.error(new BadOpaqueTokenException(
            "Tenant claim violates token contract"));
}
```

Điều này kiểm tra **định dạng claim**, không chứng minh user thuộc tenant đó hay được đọc bản ghi của tenant đó. Các quyết định ấy cần nguồn tin cậy và domain policy.

### 10.1. Khác biệt subject của user và client credentials token

Trong client credentials grant, token có thể đại diện một **service principal**, không phải human user. `sub`, `client_id` và metadata service identity phải được diễn giải đúng profile.

Không lấy `email` hoặc `preferred_username` làm identity key ổn định nếu chưa có hợp đồng. Với end-user, một mô hình thường dùng là liên kết **`(verified issuer, verified subject)`** tới internal user ID; với workload, xác định service identity riêng.

## 11. Cấu hình Spring Boot WebFlux dùng delegate và decorator

Ví dụ dependency Gradle Groovy DSL:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

Một API WebFlux thường cấu hình introspection endpoint và client credentials qua properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

**Client secret ở đây thuộc Resource Server khi gọi AS**, khác với Bearer access token của người gọi. Không commit secret production vào Git, không xuất secret qua logs hoặc response.

### 11.1. Tạo custom ReactiveOpaqueTokenIntrospector bean

Ví dụ sử dụng builder trong những phiên bản Spring Security hỗ trợ API này:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        ReactiveOpaqueTokenIntrospector remote =
                SpringReactiveOpaqueTokenIntrospector
                        .withIntrospectionUri(uri)
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .build();

        return new AudienceCheckingIntrospector(
                remote, "orders-api");
    }
}
```

**Lưu ý phiên bản:** API builder `withIntrospectionUri` của Spring reactive introspector phải được đối chiếu với Javadoc Spring Security mà dự án sử dụng. Các dòng cũ hơn có thể dùng constructor hoặc cấu hình HTTP client khác. Mục tiêu ở đây là **đưa implementation tin cậy vào decorator**; không phụ thuộc business code vào một constructor cụ thể.

Nếu Spring Boot đã auto-configure một introspector mặc định mà ứng dụng **đăng ký bean cùng interface**, Boot có thể không tạo bean mặc định nữa. Vì vậy, cách viết đúng là **chủ động dựng delegate** rồi bọc, hoặc cấu hình một graph bean có tên/qualifier rõ; đừng trông chờ auto-wiring introspector cùng interface vào chính bean đang xây và tạo dependency vòng.

### 11.2. Bật Resource Server trong SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(opaque ->
                                opaque.introspector(introspector)))
                .build();
    }
}
```

Ý nghĩa:

- `.opaqueToken(...)` chọn **introspection-based authentication**.
- `.introspector(introspector)` bảo đảm chain sử dụng **decorator đã cấu hình**.
- `hasAuthority("SCOPE_orders:read")` kiểm tra scope/authority sau authentication.
- Request không có token hợp lệ vẫn không thể vượt authentication.

**Không nhầm** với Servlet `HttpSecurity` và `OpaqueTokenIntrospector` đồng bộ. Với WebFlux, cả manager, introspector và filter chain đều thuộc reactive stack.

### 11.3. Nếu ứng dụng có nhiều SecurityWebFilterChain

Mỗi chain có matcher và order phù hợp. Chain rộng `/**` có thể được chọn trước một chain hẹp nếu cấu hình thiếu cẩn thận. Hãy test endpoint thực sự sử dụng đúng introspector; **có bean trong context không chứng minh nó được chain mong muốn gọi**.

Nếu một endpoint chỉ chấp nhận JWT, phải dùng JWT manager/decoder tương ứng. Không kỳ vọng Spring tự đọc dấu chấm trong token rồi chuyển giữa JWT và opaque.

## 12. Thời điểm thực thi: Mono.defer và lazy composition

Một decorator nên bảo đảm không vô tình introspect **hai lần**:

```java
// Có thể tạo hai subscription và hai HTTP calls:
Mono<OAuth2AuthenticatedPrincipal> source =
        delegate.introspect(token);

Mono<Boolean> hasAudience = source.map(this::matchesAudience);
Mono<String> name = source.map(OAuth2AuthenticatedPrincipal::getName);

return Mono.zip(hasAudience, name)
        .map(tuple -> buildPrincipal(tuple.getT2()));
```

Đây là **ví dụ khái niệm có các helper giả định**, minh họa nguy cơ: nhiều subscriptions vào một cold publisher có thể làm nhiều remote introspection calls. Khi cùng một principal cần nhiều kiểm tra, thường đơn giản hơn:

```java
return delegate.introspect(token)
        .flatMap(principal -> {
            // Cùng một principal, không cần subscribe nguồn thêm lần nữa.
            if (!matchesAudience(principal)
                    || !matchesIssuer(principal)) {
                return Mono.error(new BadOpaqueTokenException(
                        "Token contract rejected"));
            }
            return Mono.just(principal);
        });
```

### 12.1. Mono.defer có ích khi nào?

Nếu việc dựng remote call hoặc đọc credential/current config cần diễn ra tại lúc subscribe:

```java
return Mono.defer(() -> {
    ReactiveOpaqueTokenIntrospector activeDelegate =
            delegateProvider.currentTrustedDelegate();
    return activeDelegate.introspect(token);
});
```

`delegateProvider` là abstraction do ứng dụng tự định nghĩa, chịu trách nhiệm trả delegate đáng tin và có chính sách secret rotation. **Không lấy URI/credential từ HTTP request hoặc token** để tạo delegate.

Với một delegate cố định, viết trực tiếp `return delegate.introspect(token).flatMap(...)` thường đã đủ. Không dùng `defer` như cách “chữa” blocking I/O của một HTTP client đồng bộ.

### 12.2. Hạn chế subscribe thủ công

`subscribe()` tách một tác vụ khỏi chuỗi xác thực mà Spring Security đang điều khiển. Khi subscription thất bại, filter có thể không biết, và bạn đã có thể trả authentication quá sớm. Hãy **return Mono** nguyên vẹn cho manager.

## 13. Observability bằng doOn... mà không làm lộ credential

Một decorator có thể đo latency/đếm lỗi. Cách đơn giản là gắn các side-effect operators:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token)
            .flatMap(principal ->
                    requireAudience(principal, "orders-api"))
            .doOnNext(principal ->
                    metrics.increment("introspection.accepted"))
            .doOnError(error ->
                    metrics.increment("introspection.rejected"));
}
```

`metrics` là abstraction minh họa, không phải API Reactor; ứng dụng có thể dùng Micrometer tương ứng. Đoạn code không phân loại lỗi cụ thể, chỉ minh họa chỗ đặt instrumentation.

**Không làm**:

```java
.doOnError(error ->
        log.error("token={} introspection error={}",
                token, error.getMessage()))
```

Vì:

- `token` là Bearer credential.
- Exception message có thể chứa introspection URI, response body, client registration hoặc dữ liệu khác.
- Metric label dùng token/subject chưa xác thực có thể gây rò rỉ và cardinality rất lớn.

### 13.1. Đo thời gian bằng signal-safe logic

Nếu cần đo latency:

```java
return Mono.defer(() -> {
    long started = System.nanoTime();

    return delegate.introspect(token)
            .flatMap(this::verifyContract)
            .doFinally(signal ->
                    metrics.recordNanos(
                            "introspection.duration",
                            System.nanoTime() - started));
});
```

`verifyContract` và `metrics.recordNanos` là những phương thức ứng dụng cần triển khai. `doFinally` được gọi khi pipeline complete/error/cancel, thích hợp để đo duration nhưng **không nên coi cancellation tương đương token invalid**.

### 13.2. Reactor Context và correlation ID

Trong WebFlux, request context có thể đi qua **Reactor Context**, không dựa vào ThreadLocal như Servlet.

```java
return Mono.deferContextual(context -> {
    String requestId = context.getOrDefault(
            "requestId", "unknown");

    return delegate.introspect(token)
            .doOnError(error ->
                    audit.recordFailure(
                            requestId,
                            "INTROSPECTION_FAILURE"));
});
```

`audit` ở đây là abstraction ứng dụng. Nếu `requestId` có nguồn từ header client, phải validate giới hạn dài/charset trước khi dùng làm log identifier. **Context là metadata của luồng xử lý**, không phải bằng chứng caller đã được xác thực.

## 14. Timeout và exception mapping: fail-closed

Remote introspection tạo dependency runtime. Một AS chậm có thể khiến API chậm dù domain service rất nhanh.

Ví dụ bọc timeout:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;

return delegate.introspect(token)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(TimeoutException.class, error ->
                new OAuth2IntrospectionException(
                        "Introspection dependency timeout"));
```

Đây là **mẫu chuyển nhóm lỗi**, không phải chính sách HTTP status hoàn chỉnh. Trước khi áp dụng, cần bảo đảm timeout đã được cấu hình cả ở HTTP client/network, và phân biệt:

1. Token được AS xác định `active=false`: authentication failure.
2. AS từ chối **introspection client credentials**: sự cố config/secret rotation.
3. AS/HTTP client timeout/TLS/DNS/5xx: dependency unavailable.
4. Token active nhưng thiếu `SCOPE_orders:read`: authorization failure.

Trong mọi trường hợp **không tự tạo authenticated principal**. Nhưng telemetry vận hành phải phân biệt nguyên nhân để không chẩn đoán nhầm outage là token bị revoke.

### 14.1. Anti-pattern fail-open

```java
// NGUY HIỂM: tất cả token đều được chấp nhận khi AS gặp lỗi.
return delegate.introspect(token)
        .onErrorResume(error ->
                Mono.just(createAdministratorPrincipal()));
```

Khi dịch vụ phụ thuộc không sẵn sàng, không có dữ liệu để chứng minh token hợp lệ. Đây là **privilege escalation**.

Một fallback khác cũng nguy hiểm:

```java
// NGUY HIỂM: dùng principal cũ từ cache vô thời hạn.
return delegate.introspect(token)
        .onErrorResume(error ->
                cachedPrincipalWithoutExpiry(token));
```

Nếu có cache, phải có TTL và revocation policy rõ ràng; không dùng nó như cơ chế fail-open cho token chưa xác minh hoặc đã hết hạn.

### 14.2. Phân loại HTTP status không thuộc riêng introspector

Trong nhiều cấu hình Spring Security, `BadOpaqueTokenException` dẫn tới Bearer authentication error như **401 invalid_token**. Lỗi AS unavailable có thể phát ra từ authentication chain và được handler xử lý tùy cấu hình.

Nếu API muốn trả **503 Service Unavailable** cho dependency outage, cần thiết kế exception translation/WebFlux entry point phù hợp, giữ Bearer semantics và không lộ endpoint/credentials. **Không khẳng định `timeout()` tự tạo 503**.

## 15. Retry khi introspection: giới hạn và chỉ cho lỗi phù hợp

Không phải lỗi nào cũng đáng retry:

| Tình huống | Có nên retry trong một request? | Lý do |
| --- | --- | --- |
| `active=false` | **Không** | AS đã xác định token không được công nhận. |
| Audience/issuer mismatch | **Không** | Chính sách token không đạt. |
| Missing scope | **Không** | Retry introspection không tự cấp thêm scope. |
| HTTP 401 do introspection client secret sai | Thường **không** | Cần sửa credential/registration; retry vô ích. |
| HTTP 429 | Có thể, theo `Retry-After` và giới hạn nhỏ | Cần tránh tăng tải cho AS. |
| Timeout/503 transient | Có thể, rất hạn chế | SLA và idempotency của endpoint phải cho phép. |
| TLS validation failure | **Không** theo mặc định | Không bypass TLS; điều tra trust/config. |

Một mẫu code chỉ mang tính phác thảo:

```java
return delegate.introspect(token)
        .retryWhen(Retry.backoff(
                2, Duration.ofMillis(100))
                .filter(this::isKnownTransientDependencyError));
```

`isKnownTransientDependencyError` là method ứng dụng phải triển khai để **allowlist đúng những lỗi mạng/transient được phép retry**, không đơn giản `error instanceof RuntimeException`. Retry cần time budget tổng, jitter/backoff, giới hạn concurrency và quan sát rate.

**Không retry bằng cách đổi issuer hoặc resource endpoint** chỉ vì token không được chấp nhận ở endpoint đang cấu hình.

## 16. Caching kết quả introspection và nguy cơ mất tính mới

Introspection cho phép Resource Server hỏi AS về trạng thái hiện tại của token. Cache có thể cải thiện latency, nhưng tăng rủi ro chấp nhận token sau revocation hoặc sau khi quyền thay đổi.

### 16.1. Đừng cache một Mono chung cho mọi token

Ví dụ sai:

```java
// SAI: shared publisher của token A dùng lại cho token B.
private Mono<OAuth2AuthenticatedPrincipal> sharedPrincipal =
        delegate.introspect("token-A").cache();

@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return sharedPrincipal;
}
```

Mọi người gọi có thể nhận **principal của token A**. Đây là lỗi bảo mật nghiêm trọng.

Ngay cả khi cache theo token, cần quan tâm đến:

- Cache key không làm lộ raw token trong logs/metrics.
- Phân biệt issuer, resource, introspection client registration, policy version và tenant trust context.
- TTL không vượt `exp`/lifetime và revocation SLA.
- Xử lý `active=false`, lỗi AS và policy change theo chiến lược riêng.
- Cache eviction, concurrency và chống stampede.
- Không dùng cached result quá hạn để fail-open trong outage.

### 16.2. Cache ở đâu trong pipeline?

Về nguyên tắc:

```text
Raw token
   -> remote introspection -> active principal
   -> validate audience/issuer/token contract
   -> cache verified result with bounded TTL
   -> authorization checks on current request/resource
```

Nếu cache **trước** audience/issuer policy, các caller có trust context khác nhau có thể vô tình dùng chung principal chưa đạt resource-specific validation. Nếu cache **sau** custom validation, cache key/TTL phải phản ánh version của policy.

Không có một TTL mặc định đúng cho mọi hệ thống. Với API nhạy cảm, có thể không cache; với API có SLA revocation linh hoạt, cache ngắn hạn có thể được chấp thuận sau đánh giá.

### 16.3. Mono.cache(Duration) không thay thế token cache design

`Mono.cache(Duration)` cache signal **cho một publisher cụ thể**. Dùng nó trong một pipeline riêng có thể hạn chế duplicate subscriptions của cùng publisher, nhưng không tự xây được một cache an toàn có key theo token/issuer/resource. Hơn nữa, cache error/completion semantics và cancellation cần được hiểu đúng.

Đừng mặc định `cache()` ở class field sẽ tự an toàn cho nhiều Bearer token.

## 17. Phép hợp thành không được làm mất ranh giới access token

Trong một hệ thống OIDC, có thể có:

- **OIDC ID token** dành cho client đăng nhập.
- **OAuth 2.0 access token** dành cho Resource Server.
- **Refresh token** để client xin access token mới.
- **Client assertion** dùng xác thực một OAuth client với AS.

Introspector chỉ nên chấp nhận **loại token mà AS và Resource Server đã thỏa thuận**. Không dùng `active=true` để suy luận mọi loại token đều là access token hợp lệ cho API.

Nếu AS trả metadata phân biệt `token_type`, `aud`, `client_id` hay token profile, API có thể cần kiểm tra chúng bằng decorator/contract. Nhưng tên claim và giá trị chính xác phụ thuộc issuer; đừng tự áp đặt một tiêu chuẩn không được AS cung cấp.

### 17.1. Token là JWT vẫn có thể introspect

Một AS có thể phát access token là JWT JWS và vẫn cung cấp introspection nhằm kiểm tra trạng thái thu hồi. Nếu Resource Server cấu hình `opaqueToken()`, nó có thể gửi **chuỗi JWT** tới AS để kiểm tra; đường này không mặc định gọi `ReactiveJwtDecoder`.

Không tự phân loại bằng:

```java
// SAI: hình thức token không chứng minh trust contract.
if (token.split("\\.").length == 3) {
    return jwtDecoder.decode(token)
            .map(jwt -> createOpaquePrincipal(jwt));
}
```

Nếu hệ thống cần cả JWT local validation và introspection, phải xác định thứ tự, issuer, audience, failure semantics và ai cấp quyền cho token. Không bỏ qua introspection vì token “trông giống JWT”.

## 18. Phân quyền scope sau khi introspector chấp nhận token

Ví dụ AS trả:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export",
  "aud": ["orders-api"]
}
```

Sau mapping:

```text
Authentication: BearerTokenAuthentication
Authorities:    SCOPE_orders:read
                SCOPE_orders:export
```

Endpoint có:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders:read")
        .pathMatchers(HttpMethod.POST, "/api/orders/**")
            .hasAuthority("SCOPE_orders:write")
        .anyExchange().authenticated())
```

thì request GET có `SCOPE_orders:read` có thể đi tiếp, còn POST cần `SCOPE_orders:write` sẽ bị từ chối.

**Không suy luận** rằng `orders:export` tự bao hàm `orders:read`, hoặc scope có tiền tố `orders:` cho phép mọi hành động. Mối quan hệ quyền chỉ được chấp nhận nếu issuer/API contract định nghĩa rõ.

### 18.1. 401 khác 403

| Tình huống | Authentication | Authorization | HTTP thường gặp |
| --- | --- | --- | --- |
| Không gửi Bearer token | Chưa có principal | Endpoint cần login/token | **401**. |
| AS trả `active=false` | Thất bại | Không tới business layer | **401 invalid_token**. |
| Token active nhưng sai `aud` theo decorator | Thất bại | Không tới business layer | **401 invalid_token**. |
| Token active, audience đúng, thiếu `orders:write` | Thành công | Không đủ authority | **403 Forbidden**. |
| Token active, đúng scope nhưng order thuộc tenant khác | Thành công | Domain policy từ chối | **403/404** theo API contract. |
| AS timeout/credential sai | Chưa xác minh được token | Không cấp quyền | Fail-closed; HTTP handler/config quyết định 401/5xx phù hợp. |

Các mã trong bảng là kết quả điển hình, không phải chuỗi phản hồi được mọi gateway/handler tạo giống hệt.

## 19. Object-level authorization thuộc về tầng nghiệp vụ

Đọc order theo ID:

```java
@Service
public final class OrderService {

    private final ReactiveOrderRepository orders;
    private final ReactiveCurrentActor currentActor;

    public OrderService(
            ReactiveOrderRepository orders,
            ReactiveCurrentActor currentActor) {
        this.orders = orders;
        this.currentActor = currentActor;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public Mono<OrderDto> getOrder(UUID orderId) {
        return currentActor.getAuthorizedActor()
                .flatMap(actor -> orders
                        .findByIdAndOwnerIdAndTenantId(
                                orderId,
                                actor.userId(),
                                actor.tenantId()))
                .map(OrderDto::from);
    }
}
```

`ReactiveOrderRepository`, `ReactiveCurrentActor` và `OrderDto` là **domain types giả định**. Method security ở WebFlux cần `@EnableReactiveMethodSecurity` và phương thức được gọi qua Spring proxy; repository phải áp dụng các điều kiện tenant/owner đúng chính sách.

Tại đây:

- **Introspector** xác nhận access token active, audience đúng và principal metadata phù hợp.
- **Method security** kiểm tra `SCOPE_orders:read`.
- **Reactive repository** chỉ lấy bản ghi thuộc actor/tenant đã xác thực.

Đây là phân chia trách nhiệm rõ ràng, tránh ép introspector biết mọi resource ID của từng request.

## 20. Multi-issuer và multiple introspection delegates

Một API có thể cần chấp nhận token do nhiều Authorization Servers phát hành. Khi đó, chỉ dùng một endpoint introspection và một secret cho mọi issuer có thể không đúng hợp đồng.

Ví dụ:

```text
Trust domain A:
  issuer: https://idp-a.example.test/issuer
  introspection: https://idp-a.example.test/introspect
  client credentials: resource-A

Trust domain B:
  issuer: https://idp-b.example.test/issuer
  introspection: https://idp-b.example.test/introspect
  client credentials: resource-B
```

**Không cho client chọn delegate bằng header tùy ý**:

```java
// SAI: attacker điều hướng credential introspection sang endpoint tùy ý.
String target = exchange.getRequest()
        .getHeaders().getFirst("X-Introspection-Uri");
return newRemoteIntrospector(target, resourceServerSecret);
```

Trong ứng dụng đa issuer, cần cơ chế chọn dựa trên **cấu hình được tin cậy**, chẳng hạn route/API contract cụ thể hoặc registration được quản trị. Nếu có bước đọc `iss` chưa được xác minh để chọn ứng viên, dữ liệu đó chỉ được xem như **routing hint**, phải kiểm tra trong allowlist và xác nhận lại bằng introspection đáng tin.

### 20.1. Không fallback sau khi AS từ chối token

Ví dụ nguy hiểm:

```java
return issuerA.introspect(token)
        .onErrorResume(error -> issuerB.introspect(token));
```

Nếu issuer A đã từ chối token, việc thử issuer B với trust policy khác có thể gây token confusion hoặc mở oracle dò token trên nhiều endpoints. Nếu migration thật sự cần nhiều issuers, hãy thiết kế routing contract, client/resource isolation và negative tests một cách tường minh, không biến **mọi** authentication error thành fallback.

### 20.2. Sử dụng SecurityWebFilterChain tách biệt nếu phù hợp

Khi có hai nhóm API rõ:

```text
/api/partner-a/** -> introspection credential và policy A
/api/partner-b/** -> introspection credential và policy B
```

có thể tạo các `SecurityWebFilterChain` riêng với matcher/order và introspector phù hợp. Mọi route còn lại nên có chính sách mặc định an toàn. Hãy test JWT/opaque/partner token sai route để bảo đảm không bị nhận bởi chain ít nghiêm ngặt hơn.

## 21. Bảo vệ thông tin xác thực của Resource Server

Trong introspection request, có **hai credential nhạy cảm**:

1. Access token của caller được gửi trong body `token=...`.
2. Credential của Resource Server khi gọi AS, như Basic client secret, mTLS private key hoặc private-key JWT client assertion.

Chúng có vòng đời và trách nhiệm khác nhau:

| Credential | Chủ thể giữ | Mục đích |
| --- | --- | --- |
| Bearer access token | OAuth client và Resource Server khi xử lý request | Truy cập API theo quyền đã cấp. |
| Introspection client ID/secret | Resource Server/secret manager | Chứng minh Resource Server được phép truy vấn AS. |
| mTLS client certificate/private key | Resource Server | Client authentication tới AS khi registration yêu cầu. |
| JWT signing private key của AS | Authorization Server | Ký JWT; không phải secret dùng gọi introspection. |

**Không log** Bearer header, Basic header, raw `token` form value, private key hay toàn bộ introspection response.

### 21.1. Secret rotation và decorator

Khi client secret đổi trong secret manager, một bean delegate được tạo từ `@Value` lúc startup có thể **vẫn giữ secret cũ**. Decorator không tự khiến HTTP client reload credentials.

Các lựa chọn:

- Rolling redeploy/restart để tạo delegate mới với credential mới.
- Thay delegate qua reference có kiểm soát sau khi credential mới được xác minh.
- AS cho phép hai secrets/registrations active trong cửa sổ overlap, sau đó thu hồi bản cũ.

Nếu AS chỉ cho một secret active, rolling update không mặc nhiên bảo đảm zero downtime. Có thể dùng blue-green client registrations hoặc một cutover có điều phối. Không giữ secret bị nghi lộ active chỉ vì muốn tránh lỗi introspection.

### 21.2. Không hardcode secret hoặc endpoint chưa xác thực

URL introspection phải cố định theo trusted deployment config; TLS/mTLS phải được kiểm tra đúng. Không dùng endpoint từ Bearer token, query string hay unverified issuer.

## 22. Kiểm thử decorator bằng StepVerifier

Vì `ReactiveOpaqueTokenIntrospector` trả `Mono`, **Reactor Test StepVerifier** rất phù hợp để test chính xác đường success/error/empty mà không cần AS thật.

### 22.1. Chuẩn bị fake principal và fake delegate

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class AudienceCheckingIntrospectorTest {

    private static OAuth2AuthenticatedPrincipal principal(String aud) {
        return new DefaultOAuth2AuthenticatedPrincipal(
                "user-123",
                Map.of(
                        "sub", "user-123",
                        "aud", List.of(aud),
                        "scope", "orders:read"),
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")));
    }

    @Test
    void acceptsMatchingAudience() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.just(principal("orders-api"));

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectNextMatches(p ->
                        "user-123".equals(p.getName())
                        && p.getAuthorities().stream().anyMatch(a ->
                                "SCOPE_orders:read"
                                        .equals(a.getAuthority())))
                .verifyComplete();
    }

    @Test
    void rejectsWrongAudience() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.just(principal("payments-api"));

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectError(BadOpaqueTokenException.class)
                .verify();
    }

    @Test
    void doesNotTurnRemoteFailureIntoSuccess() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.error(
                        new BadOpaqueTokenException("inactive"));

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectError(BadOpaqueTokenException.class)
                .verify();
    }

    @Test
    void emptyDelegateMustFailClosed() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.empty();

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectError(BadOpaqueTokenException.class)
                .verify();
    }
}
```

Các tests trên kiểm tra **logic decorator**, không chứng minh remote introspector thực sự gửi HTTP POST, xác thực Basic credentials hoặc xử lý `active=false`. `fake-token` chỉ là placeholder dùng trong unit test.

### 22.2. Kiểm tra số lần introspection được gọi

Một fake delegate với `Mono.defer`:

```java
AtomicInteger calls = new AtomicInteger();

ReactiveOpaqueTokenIntrospector remote = token ->
        Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.just(principal("orders-api"));
        });

ReactiveOpaqueTokenIntrospector decorated =
        new AudienceCheckingIntrospector(remote, "orders-api");

StepVerifier.create(decorated.introspect("test-token"))
        .expectNextCount(1)
        .verifyComplete();

assertEquals(1, calls.get());
```

`assertEquals` đến từ JUnit Jupiter. Đây là bài test xác minh **một subscription** trong case đơn giản tạo một delegate invocation. Nếu subscription được lặp lại cố ý hoặc có retry, số lượt gọi có thể lớn hơn; cần định nghĩa contract tương ứng.

### 22.3. Kiểm tra không có side effect trước subscription

Với fake delegate trên:

```java
Mono<OAuth2AuthenticatedPrincipal> publisher =
        decorated.introspect("test-token");

assertEquals(0, calls.get());

StepVerifier.create(publisher)
        .expectNextCount(1)
        .verifyComplete();

assertEquals(1, calls.get());
```

Đây là ví dụ độc lập, giả định `calls` mới được khởi tạo về 0 trước khi test. Nó minh họa tính **lazy** của `Mono.defer` và giúp phát hiện việc tự subscribe trong implementation.

## 23. Kiểm thử wire protocol với mock introspection server

Unit test bằng fake `ReactiveOpaqueTokenIntrospector` không xác minh lớp HTTP. Nếu dự án tùy chỉnh client credentials, timeout hoặc AS response mapping, cần một test dùng **mock HTTP server** như WireMock/MockWebServer:

1. Cấu hình delegate trỏ tới mock introspection URI đáng tin.
2. Gửi một token test qua `delegate.introspect(...)` hoặc WebFlux filter chain.
3. Assert request **POST** với `Content-Type: application/x-www-form-urlencoded`.
4. Assert form có `token` đúng, HTTP client authentication đúng contract.
5. Mock `{"active":true,"aud":["orders-api"],"scope":"orders:read"}` → principal được decorator chấp nhận.
6. Mock `{"active":true,"aud":["payments-api"]}` → decorator từ chối.
7. Mock `{"active":false}` → delegate/introspector từ chối, không tạo principal.
8. Mock HTTP 401 của AS do introspection credential sai → phân loại **client authentication failure**, không nhầm token inactive.
9. Mock timeout/503/JSON lỗi → không tạo authenticated principal.
10. Assert logs, headers và response không chứa test token/secret markers.

**Không cần dùng production access token hoặc production client secret**. Test credentials phải được tạo riêng cho môi trường kiểm thử.

### 23.1. Vì sao cần kiểm tra Basic auth encoding?

Introspection client ID/secret có thể chứa `+`, `:`, `%`, `/`. Nếu một lớp đã percent-encode credentials rồi builder/HTTP client lại encode lần nữa, AS có thể trả HTTP 401 dù secret về mặt logic là đúng.

Sử dụng builder/HTTP client phù hợp **Spring Security version**, đưa raw credentials ở nơi API yêu cầu, và xác minh wire format ở mock AS. Không log Basic Authorization header chỉ để debug encoding.

### 23.2. Lỗi AS HTTP 401 khác API HTTP 401

```text
AS -> Resource Server: HTTP 401 (introspection client không được AS chấp nhận)
Resource Server -> OAuth client: HTTP 401/5xx theo handler an toàn
```

Hai HTTP status nằm ở **hai request/hop khác nhau**. Nếu AS trả 401 do secret đã rotation, đừng báo mọi user “token đã bị thu hồi” trong audit logs. Phải điều tra credential/registration của Resource Server.

## 24. WebTestClient kiểm thử 401 và 403 qua WebFlux filter chain

Để kiểm tra toàn bộ luồng HTTP, dùng **WebTestClient** với `SecurityWebFilterChain` thật và delegate giả lập có kiểm soát hoặc mock AS.

Ví dụ phác thảo:

```java
webTestClient.get()
        .uri("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer active-read-token")
        .exchange()
        .expectStatus().isOk();

webTestClient.get()
        .uri("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer active-no-scope-token")
        .exchange()
        .expectStatus().isForbidden();

webTestClient.get()
        .uri("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer inactive-token")
        .exchange()
        .expectStatus().isUnauthorized();
```

**Giả định** môi trường test đã cấu hình introspector/mock AS trả đúng ba trường hợp và endpoint trả 200 khi đủ quyền. Đây là mẫu cách kiểm tra, **không phải kết quả đã chạy**.

Nếu đang dùng `WebTestClient.bindToApplicationContext(...)`, cần cấu hình Spring Security Test integration phù hợp, thường thông qua `springSecurity()` configurer. Với live server `RANDOM_PORT`, hành vi test mutators khác; hãy dùng mode phù hợp với mục tiêu kiểm tra filter thực.

### 24.1. mockOpaqueToken() không kiểm tra introspection

Spring Security Test cho WebFlux có thể cung cấp `mockOpaqueToken()` để đặt Authentication giả lập:

```java
webTestClient.mutateWith(
        mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus()
        .isOk();
```

Đây là cách tốt để test **authorization rules**, nhưng **không chứng minh** `ReactiveOpaqueTokenIntrospector` hoặc decorator đã chạy. Muốn kiểm tra audience validation thật, phải gửi Bearer header qua filter và dùng delegate/mock AS thực sự được gọi.

### 24.2. Ma trận integration test

| Trường hợp | Remote introspection | Decorator | HTTP kỳ vọng |
| --- | --- | --- | --- |
| Token không có | Không gọi AS | Không chạy | 401 cho protected API. |
| Token active, `aud=orders-api`, có read scope | Principal hợp lệ | Pass | 2xx nếu domain cho phép. |
| Token active, `aud=payments-api`, có read scope | Principal hợp lệ | Deny | 401 invalid_token theo handler. |
| Token active nhưng thiếu `aud` bắt buộc | Principal hợp lệ | Deny | 401. |
| Token active, đúng audience nhưng thiếu read scope | Principal hợp lệ | Pass | 403 do authorization. |
| Token active, đủ scope, sai owner/tenant | Principal hợp lệ | Pass | 403/404 do domain policy. |
| Token inactive | `active=false` | Không nên chạy policy trên principal | 401. |
| Remote introspector trả Mono.empty() | Empty | Fail-closed | Authentication failure, không 2xx. |
| Remote introspection timeout | Error | Không tạo principal | Lỗi an toàn theo handler, có thể 5xx/503. |
| AS trả 401 do introspection client secret sai | HTTP error | Không tạo principal | Lỗi an toàn, log nội bộ phân loại credential. |
| Claim `tenant_id` là object thay vì string | Principal hợp lệ | Deny theo schema | 401 nếu kiểm tra ở authentication. |
| Cố đưa JWT vào opaque endpoint | AS quyết định theo hợp đồng | Không tự auto-switch | Không chấp nhận nếu AS/token profile không cho phép. |

## 25. Reactor Context, cancellation và thời hạn request

Trong WebFlux, security context thường được truyền qua **Reactor Context**:

```java
Mono<Authentication> current =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication);
```

Trong đường introspection, filter đang cố **tạo Authentication**, nên không nên giả định đã có principal tin cậy trong `ReactiveSecurityContextHolder` của cùng request trước khi xác minh token.

### 25.1. Không lấy “user” từ context trước khi xác thực

Một header như `X-User-ID`, query parameter `tenant` hoặc Reactor Context do custom middleware điền vào **không chứng minh identity** nếu chưa được trust boundary xác minh.

Nếu policy cần actor, hãy lấy từ `OAuth2AuthenticatedPrincipal` do introspection trả, rồi kiểm tra external identity mapping theo contract, không dùng dữ liệu client tự khai để cấp quyền.

### 25.2. Cancellation không có nghĩa token invalid

Client có thể hủy request giữa lúc AS đang introspect. Khi Reactor pipeline bị cancel, `doFinally` nhận signal cancellation. Đừng ghi audit “token invalid” hoặc chặn tài khoản chỉ vì request bị cancel.

HTTP client/tài nguyên cần xử lý cancellation, timeout và connection cleanup đúng cách. `retryWhen` hoặc `cache` thiếu kiểm soát có thể giữ network requests sống lâu hơn cần thiết.

## 26. Phân biệt introspector decorator với authentication converter

Trong Spring Security, có hai tầng tùy biến:

1. **Introspector decorator**: nhận raw token, gọi remote introspector, kiểm tra/biến đổi `OAuth2AuthenticatedPrincipal`.
2. **Authentication converter** ở manager (nếu version hỗ trợ): nhận principal/metadata đã được introspect và tạo `Authentication` phù hợp, có thể custom authorities/principal representation.

Hai tầng không thay thế hoàn toàn nhau:

| Mục tiêu | Nơi phù hợp |
| --- | --- |
| Bắt buộc issuer/audience/metadata của access token | Introspector decorator (trước khi tạo Authentication). |
| Quan sát latency và remote introspection errors | Quanh delegate, nhưng không log token/secret. |
| Giới hạn raw principal attributes theo hợp đồng | Decorator với xử lý cẩn thận. |
| Ánh xạ chính thức principal/authorities thành Authentication type khác | Authentication converter có contract hỗ trợ. |
| Kiểm tra owner/tenant của `orderId` | Method/domain authorization hoặc repository query. |
| Kiểm tra signature của JWT cục bộ | `ReactiveJwtDecoder`, **không** phải opaque decorator. |

**Tránh cấu hình mapping authorities ở hai tầng** mà không có precedence rõ. Một tầng có thể lọc quyền, tầng sau lại thêm quyền từ raw `scope`, làm mất ý nghĩa policy ban đầu.

## 27. Những anti-pattern dễ gặp

### 27.1. Viết delegate giả luôn trả principal

```java
ReactiveOpaqueTokenIntrospector insecure =
        token -> Mono.just(adminPrincipal);
```

Nếu không có một nguồn xác thực token đáng tin, mọi chuỗi client gửi đều trở thành admin. Chỉ dùng fake trong **test context riêng**, không đưa vào production.

### 27.2. Dùng onErrorResume để chấp nhận token khi AS timeout

```java
delegate.introspect(token)
        .onErrorResume(error -> Mono.just(lastKnownAdmin));
```

Đây là fail-open. Phải để lỗi đi tiếp hoặc map thành dependency error được handler xử lý an toàn.

### 27.3. Dùng filter rồi coi empty là authenticated

`filter` loại principal không đạt điều kiện bằng cách trả empty. Một authentication pipeline nên biểu diễn từ chối bằng **Mono.error** và test negative branch.

### 27.4. Tự subscribe trong introspect()

`subscribe()` làm mất quyền kiểm soát kết quả/lỗi của framework và dễ thực hiện network call thừa. Trả pipeline Mono cho manager.

### 27.5. Blocking HTTP/JDBC trong map

`map` không tự làm code synchronous trở thành non-blocking. Dùng reactive I/O hoặc bounded adapter cho legacy blocking dependencies.

### 27.6. Chọn introspection URI từ input không đáng tin

Tạo nguy cơ SSRF hoặc gửi client secret tới attacker host. Endpoint/credential phải đến từ trusted configuration.

### 27.7. Xác nhận active=true rồi bỏ qua aud

Token active có thể dành cho resource khác. Bắt resource-binding theo introspection contract, hoặc dựa trên bảo đảm AS tương đương đã được kiểm thử.

### 27.8. Cấp role theo email hoặc tên người dùng

Email/name có thể thay đổi hoặc trùng. Không dùng chúng thay external identity hợp đồng; không cấp `ROLE_ADMIN` từ chuỗi tự suy đoán.

### 27.9. Cache một Mono dùng chung cho mọi request

Có thể làm user B nhận principal user A. Cache phải có key/context/TTL đúng và đánh giá revocation.

### 27.10. Retry lỗi inactive hoặc wrong audience

AS đã từ chối token hoặc local policy đã xác định mismatch. Retry chỉ tăng tải, có thể gây bypass khi fallback sang issuer khác.

### 27.11. Chỉ test bằng mockOpaqueToken()

Mock Authentication có thể bypass cả remote introspector lẫn decorator. Cần StepVerifier của decorator và integration test HTTP Bearer path.

### 27.12. Trả exception.getMessage() cho client

Introspection errors có thể chứa AS URL/client registration. Phản hồi cần RFC 6750 Bearer error tối giản, không đưa token/secret/stack trace ra ngoài.

## 28. Tình huống thực hành

### Tình huống A — Chặn token của API khác

AS trả `active=true` cho token có `aud=["payments-api"]`. `AudienceCheckingIntrospector` sẽ phát `BadOpaqueTokenException`. API không tạo principal cho `orders-api` dù token có một vài scope tương tự.

### Tình huống B — Giới hạn authorities

AS trả `orders:read orders:export tenant:admin`, nhưng API chỉ chấp nhận hai scopes đầu. Một decorator có thể lọc authorities theo allowlist. Tuy nhiên, phải xác định rõ mapping của các role/factor authorities khác để không làm mất một policy bảo mật có chủ đích.

### Tình huống C — Identity thuộc tenant khác

Token active, audience đúng, nhưng user không thuộc tenant của `orderId`. Decorator có thể pass token contract; **reactive order query** kiểm tra tenant/ownership và không trả bản ghi ngoài quyền.

### Tình huống D — AS trả empty publisher

Một custom delegate bị lỗi logic và trả `Mono.empty()`. Decorator dùng `switchIfEmpty(Mono.error(...))` để không im lặng coi token đã được xác thực.

### Tình huống E — Secret introspection đã rotation

AS từ chối Basic credential cũ bằng HTTP 401. Decorator không tạo principal, logs nội bộ đánh dấu `INTROSPECTION_CLIENT_AUTH_FAILURE`. Ops cập nhật secret/delegate đúng quy trình; không kết luận tất cả user access tokens bị thu hồi.

### Tình huống F — Introspection timeout

HTTP call chậm vượt SLA, `timeout` phát lỗi. API fail-closed, không cấp một principal “tạm thời”. Circuit breaker/retry chỉ được dùng nếu không thay đổi trạng thái xác thực và có time budget.

### Tình huống G — Migration giữa hai issuers

Hai issuers có credentials và audiences khác nhau. Chọn delegate theo trusted route/client registration hoặc allowlist, rồi xác thực resource contract. Không tự chuyển delegate qua token payload chưa được xác minh hoặc fallback sau mọi lỗi.

### Tình huống H — Test pass nhưng production thiếu authority

Test `mockOpaqueToken()` tự đưa `SCOPE_orders:read` nên 200; production introspection chỉ trả `scope="profile"`, thành ra 403. Cần test remote principal/authority mapping thật bằng mock AS và kiểm tra policy scope.

## 29. Câu hỏi tự kiểm tra

**1. `ReactiveOpaqueTokenIntrospector` trả về gì?** `Mono<OAuth2AuthenticatedPrincipal>`, không phải một principal đồng bộ.

**2. Vì sao nên dùng decorator thay vì viết lại HTTP introspection?** Giữ các kiểm tra giao thức, client authentication và `active` từ implementation tin cậy; chỉ thêm policy cần thiết.

**3. `map` và `flatMap` khác nhau thế nào trong composition?** `map` cho biến đổi đồng bộ một phần tử; `flatMap` khi bước trả một publisher/`Mono` cần được nối vào pipeline.

**4. Khi AS trả `active=false`, decorator có nên tạo principal rỗng để API tiếp tục không?** Không. Phải fail-closed.

**5. `Mono.empty()` có phải một kết quả authentication thành công không?** Không. Với token introspection, nên chuyển empty không hợp lệ thành lỗi rõ ràng.

**6. Vì sao `filter` trên principal có thể khó chẩn đoán?** Vì một value không đạt điều kiện trở thành empty publisher, không có failure category tường minh.

**7. Token active có mặc nhiên dành cho mọi API không?** Không. Cần kiểm tra audience/resource binding hoặc bảo đảm tương đương từ AS.

**8. `scope` có thay ownership của order không?** Không. `SCOPE_orders:read` không chứng minh user sở hữu mọi order.

**9. Vì sao không dùng email làm identity key mặc định?** Email thường mutable/reassignable; cần hợp đồng subject/issuer và mapping internal identity.

**10. Có thể gọi `.block()` trong WebFlux introspector không?** Không nên. Nó có thể chặn event-loop và phá đặc tính reactive.

**11. Khi introspection timeout có được dùng fallback admin không?** Không. Đó là fail-open/privilege escalation.

**12. Caching `Mono` chung ở field có rủi ro gì?** Có thể dùng principal của token trước cho token sau; phải thiết kế cache theo key/trust context/TTL.

**13. Vì sao retry `active=false` không hợp lý?** AS đã xác định token không được chấp nhận; retry không làm token hợp lệ theo policy.

**14. Cần thử những trường hợp nào bằng StepVerifier?** Audience đúng/sai, delegate lỗi, empty publisher, propagation và số lần delegate được gọi.

**15. `mockOpaqueToken()` có chứng minh HTTP introspection đã chạy không?** Không. Nó tạo Authentication giả lập để test authorization.

**16. HTTP 401 của AS và HTTP 401 API khác nhau chỗ nào?** AS 401 có thể vì introspection client secret sai; API 401 thường phản ánh Bearer credential không được chấp nhận.

**17. Khi cần truy vấn database để kiểm tra quyền trên `orderId` nên làm ở đâu?** Reactive authorization/service/repository, không ép introspector hiểu request resource.

**18. Vì sao không cho caller gửi `X-Introspection-Uri`?** Đó là input không đáng tin, có thể gây SSRF và lộ Resource Server credentials.

**19. Nếu ghép nhiều policy, làm thế nào bảo đảm tất cả được áp dụng?** Nối các bước bằng `flatMap` và chỉ trả principal sau khi mọi bước thành công; negative tests cho từng điều kiện.

**20. Trong composition, log gì là phù hợp?** Correlation ID, result category, latency và low-cardinality labels; không log raw Bearer token, Basic secret hay full introspection response.

## 30. Tài liệu tham khảo

- **RFC 7662 — OAuth 2.0 Token Introspection**: quy tắc `active`, response metadata và bảo vệ introspection endpoint. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: Bearer transport và các lỗi `invalid_token`, `insufficient_scope`. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — OAuth 2.0 Authorization Framework**: client authentication và scopes. https://www.rfc-editor.org/rfc/rfc6749
- **Spring Security Reference — Reactive OAuth2 Resource Server Opaque Token**: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security API — ReactiveOpaqueTokenIntrospector**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- **Spring Security API — SpringReactiveOpaqueTokenIntrospector**: xem Javadoc đúng dependency Spring Security của dự án.
- **Spring Security API — OpaqueTokenReactiveAuthenticationManager**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html
- **Spring Security Reference — WebFlux Security**: https://docs.spring.io/spring-security/reference/reactive/index.html
- **Spring Security Reference — WebFlux Testing**: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **Project Reactor Reference Guide**: `Mono`, `map`, `flatMap`, error handling, scheduling, context và testing. https://projectreactor.io/docs/core/release/reference/
- **OWASP Logging Cheat Sheet**: giảm lộ credentials/PII trong logs và tracing. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

## 31. Tổng kết

**Tùy chỉnh introspector bằng phép hợp thành phản ứng** nghĩa là giữ `ReactiveOpaqueTokenIntrospector` đáng tin cậy làm **delegate**, rồi dùng `map`, `flatMap`, `switchIfEmpty`, `doOnError`, `timeout` và các toán tử Reactor khác để xây thêm chính sách theo **token contract**.

Mẫu cốt lõi:

```java
return delegate.introspect(token)
        .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException(
                        "Introspection did not return a principal")))
        .flatMap(principal ->
                requireAudience(principal, expectedAudience))
        .flatMap(principal ->
                requireIssuer(principal, trustedIssuer))
        .map(MyAuthorityPolicy::restrictAuthorities);
```

Pipeline này chỉ phát principal sau khi **delegate đã chấp nhận token** và mọi bước bổ sung thành công. Một lỗi từ AS, audience mismatch hoặc empty publisher đều **không thể biến thành Authentication hợp lệ**.

Khi đưa vào WebFlux thực tế, cần giữ ranh giới rõ: **AS xác minh token active**, **decorator kiểm tra hợp đồng issuer/audience/metadata**, **Spring Security kiểm tra authorities**, và **domain layer kiểm tra quyền trên từng tài nguyên**. Tránh blocking, fallback fail-open, cache chung cho mọi token và logging credentials. Để bảo vệ hệ thống, hãy test bằng **StepVerifier**, **mock introspection HTTP server** và **WebTestClient thực sự đi qua Bearer filter chain** — mỗi tầng kiểm tra một trách nhiệm riêng.
