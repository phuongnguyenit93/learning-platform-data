# Ánh xạ principal có tra cứu phản ứng khi nghiệp vụ cần

Trong **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server dùng WebFlux**, sau khi một Bearer JWT access token được xác minh, Spring Security cần tạo một đối tượng **`Authentication`** để biết request đến từ chủ thể nào và đang có những authorities nào. Mặc định, principal thường dựa trên **`Jwt`** đã xác minh, còn `Authentication.getName()` thường được suy ra từ claim `sub`. Với nhiều ứng dụng, thông tin đó đã đủ: API kiểm tra scope, issuer, audience và ra quyết định.

Nhưng nghiệp vụ thực tế có thể cần thêm: tài khoản nội bộ tương ứng với `(iss, sub)` là ai? Tài khoản ấy đã được kích hoạt chưa? Người này có liên kết với khách hàng hoặc nhân viên nào trong database? Quyền đang có trong tổ chức/tenant hiện tại là gì? Những dữ liệu này thường **không nằm trong JWT**, hoặc có thể thay đổi sau lúc JWT được cấp.

Trong WebFlux, ta không thể giải quyết vấn đề bằng việc gọi repository đồng bộ rồi dùng `.block()` trong JWT converter. Thay vào đó, **tra cứu phải được đưa vào chuỗi phản ứng `Mono`/`Flux`**, hoặc được dời sang service/authorization layer khi chỉ một số thao tác nghiệp vụ cần. Bài này làm rõ hai lựa chọn, cách ánh xạ principal đúng chỗ và các ranh giới bảo mật cần giữ.

> **Nguyên tắc cốt lõi:** JWT đã được xác minh là nguồn tin cho **danh tính bên ngoài và claims đã ký**, còn hệ thống nội bộ là nguồn tin cho **liên kết tài khoản, trạng thái và quyền nghiệp vụ động**. Nếu cần tra cứu, hãy làm theo mô hình **non-blocking** và **fail closed**. Không phải request nào cũng cần tra cứu database; chỉ đặt lookup ở bước authentication khi đó là điều kiện bắt buộc chung cho mọi request protected.

## 1. Bối cảnh: từ JWT tới principal trong WebFlux

Giả sử hệ thống bán hàng gồm:

- **Identity Server**: Authorization Server phát hành JWT access token.
- **Shop Web**: OAuth2/OIDC Client xin token và gọi API.
- **Orders API**: WebFlux Resource Server, xác minh JWT và phân quyền.
- **Identity Link Database**: ánh xạ người dùng bên ngoài tới mã người dùng nội bộ.
- **Order Database**: lưu đơn theo owner, tenant, trạng thái.

Một request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <signed-jwt-access-token>
~~~

JWT đã xác minh có claims minh họa:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "external-user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "exp": 1893459600
}
~~~

Trong hệ thống nghiệp vụ, người này có thể được lưu dưới mã **`user-0042`**, không phải `external-user-842`. Bảng liên kết:

| Issuer | Subject bên ngoài | Internal user ID | Trạng thái |
| --- | --- | --- | --- |
| `https://identity.example.test/realms/shop` | `external-user-842` | `user-0042` | Enabled |
| `https://identity.partner.example.test` | `external-user-842` | `user-1290` | Enabled |

Hai hàng có cùng chuỗi `sub` nhưng **khác issuer** có thể đại diện **hai tài khoản hoàn toàn khác nhau**. Vì vậy, không lấy `sub` làm khóa toàn cục nếu API có thể tin nhiều issuer, và không mặc định email/username là định danh ổn định.

Một chuỗi xử lý:

~~~mermaid
flowchart TD
    A["HTTP Bearer JWT"]
    B["Spring Security WebFlux SecurityWebFilterChain"]
    C["ReactiveJwtDecoder: chữ ký, issuer, audience, time"]
    D{"JWT hợp lệ?"}
    E["Authentication failure, không tạo principal"]
    F["Reactive JWT authentication converter"]
    G{"Nghiệp vụ có bắt buộc liên kết local account cho mọi request?"}
    H["Reactive repository / client: tìm (iss, sub)"]
    I["Tạo JwtAuthenticationToken với internal user ID"]
    J["Dùng principal JWT mặc định"]
    K["Reactive authorization và business policy"]
    L["Tra cứu resource/owner/tenant nếu endpoint cần"]
    M["Kết quả được phép"]

    A --> B --> C --> D
    D -->|Không| E
    D -->|Có| F --> G
    G -->|Có| H --> I --> K
    G -->|Không| J --> K
    K --> L --> M
~~~

**Thứ tự đặc biệt quan trọng:** JWT phải được xác minh **trước** khi API dùng `iss`/`sub` để tra cứu tài khoản được tin cậy. Không lấy payload từ một JWT chưa kiểm tra chữ ký rồi truy vấn account hoặc cấp authority theo dữ liệu đó.

## 2. `Jwt`, principal, name và authorities khác nhau thế nào?

Spring Security sử dụng `Authentication` để biểu diễn chủ thể đã xác thực cùng quyền.

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| **`Jwt`** | Access token đã được `ReactiveJwtDecoder` xác minh và biểu diễn thành claims | `iss`, `sub`, `aud`, `scope` |
| **`Authentication`** | Ngữ cảnh xác thực của request | `JwtAuthenticationToken` |
| **`Authentication.getPrincipal()`** | Đối tượng đại diện principal, thường là chính `Jwt` | Một `Jwt` đã xác minh |
| **`Authentication.getName()`** | Chuỗi tên principal cho audit/ứng dụng | Mặc định từ `sub`; có thể map thành mã nội bộ |
| **`Authentication.getAuthorities()`** | Tập `GrantedAuthority` được dùng để phân quyền | `SCOPE_orders.read`, `ROLE_MEMBER` |
| **Local account/profile** | Dữ liệu riêng của Orders API hoặc doanh nghiệp | `internalUserId=user-0042`, `enabled=true` |
| **Resource-level permission** | Quyền trên đơn 42, tenant A, assignment... | Caller có được đọc **đơn này** không? |

**Không đồng nhất `Authentication.getPrincipal()` với `Authentication.getName()`.** Nếu ta tạo `JwtAuthenticationToken(jwt, authorities, "user-0042")`, thì:

- `authentication.getPrincipal()` vẫn là đối tượng **`Jwt`**.
- `authentication.getName()` là **`user-0042`**.
- `authentication.getAuthorities()` là tập authority đã truyền.

Điều này thường đã đáp ứng nhu cầu “đổi tên principal sang ID nội bộ” mà **không phải tạo một kiểu token authentication riêng**.

### 2.1. `@AuthenticationPrincipal Jwt` nhận gì?

Trong WebFlux controller:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
class IdentityController {

    @GetMapping("/token-subject")
    Mono<String> subject(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(jwt.getSubject());
    }
}
~~~

Trong cấu hình JWT mặc định hoặc khi dùng `JwtAuthenticationToken`, `@AuthenticationPrincipal Jwt` đọc **JWT principal**, không tự trả một `LocalUser` lấy từ database.

Nếu cần mã local user ID, controller/service có thể nhận `Authentication` rồi đọc `getName()` **nếu converter đã đặt name thành mã nội bộ**. Nếu không, hãy tra cứu local account theo `(iss, sub)` khi nghiệp vụ cần. Tránh dựa vào một email có thể thay đổi làm khóa dữ liệu nghiệp vụ.

### 2.2. Scope không phải local role

JWT:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

thường được Spring Security ánh xạ thành:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Local role có thể là:

~~~text
ROLE_MEMBER
ROLE_ORDER_SUPPORT
~~~

Hai loại quyền khác nhau. Scope do Authorization Server cấp cho Client/token; role hoặc assignment nội bộ có thể do hệ thống nghiệp vụ quản lý. **Không tự nâng một scope thành role admin**, và không xem claim `roles` tùy ý trong JWT là trusted authority nếu chưa có hợp đồng mapping rõ.

## 3. “Tra cứu phản ứng” nghĩa là gì?

Trong Spring WebFlux, I/O có độ trễ được biểu diễn qua **Publisher** như `Mono<T>` hoặc `Flux<T>`. Tra cứu tài khoản có thể dùng:

- **Spring Data R2DBC / ReactiveCrudRepository** khi database hỗ trợ reactive access.
- **Reactive Redis** hoặc một reactive cache/client tương thích.
- **`WebClient`** gọi một identity/membership service qua HTTP không chặn.
- Một reactive service kết hợp nhiều nguồn và sử dụng `flatMap`/`zip` theo policy.

Ví dụ:

~~~java
Mono<IdentityLink> linkMono =
    identityLinkRepository.findByIssuerAndSubject(issuer, subject);
~~~

`linkMono` là **một mô tả tính toán bất đồng bộ/lười thực thi**, không phải một `IdentityLink` đã có sẵn ngay lúc gọi hàm. Khi Spring Security subscribe chuỗi authentication, repository mới thực hiện tác vụ I/O theo cơ chế publisher.

**Đừng gọi:**

~~~java
// SAI trong luồng WebFlux event loop:
IdentityLink link = repository
    .findByIssuerAndSubject(issuer, subject)
    .block();
~~~

`block()` biến công việc phản ứng thành chờ đồng bộ, có thể làm nghẽn Netty event loop, giảm throughput hoặc phát sinh lỗi Reactor do blocking call trên thread non-blocking.

Cũng không nên:

~~~java
// SAI: subscribe thủ công rồi lập tức trả authentication.
repository.findByIssuerAndSubject(issuer, subject)
    .subscribe(link -> updateGlobalPrincipal(link));

return Mono.just(defaultAuthentication);
~~~

Vì `subscribe()` chủ động chạy tác vụ ngoài chuỗi authentication, **request có thể tiếp tục trước khi tra cứu xong**. Lỗi không được truyền về đúng chỗ, state có thể rò giữa requests và dễ tạo fail-open/race condition.

**Đúng:** trả một `Mono<AbstractAuthenticationToken>` chứa lookup; Spring Security chờ publisher hoàn thành rồi mới coi quá trình chuyển đổi authentication hoàn tất.

## 4. Khi nào cần lookup ngay trong JWT authentication converter?

Lookup **tại authentication** hợp lý khi mọi protected request **bắt buộc** đáp ứng một điều kiện thuộc danh tính nội bộ:

- Mọi user phải liên kết với một local account.
- Local account bị disabled thì không được gọi bất cứ API protected nào.
- Audit và hệ thống dưới đều bắt buộc có internal user ID.
- API cần một authority chung được cấp từ trạng thái tài khoản đã xác minh.

Ví dụ chính sách:

~~~text
JWT verified
  -> find local account by (issuer, subject)
  -> account exists?
  -> enabled?
  -> tạo JwtAuthenticationToken với name = internalUserId
  -> xét scope của endpoint
~~~

Nếu mọi protected endpoint đòi local account, đây là một **authentication contract** rõ ràng. Nhưng nếu một số endpoint công khai hoặc dành cho service không cần user account, đặt lookup bắt buộc ở mọi request có thể khiến các request hợp lệ bị chặn một cách không cần thiết.

### 4.1. Khi chỉ vài endpoint cần dữ liệu nghiệp vụ

Ví dụ:

- `GET /api/public/catalog` không cần login.
- `GET /api/catalog` có thể chỉ cần token/`catalog.read`.
- `GET /api/me/profile` cần local account/profile.
- `GET /api/orders/42` cần local account và quyền trên Order 42.

Trong trường hợp này, **đừng bắt mọi access token phải tra cứu Profile DB ngay trong converter** chỉ để phục vụ `/api/me`. Giữ authentication dựa trên JWT, sau đó tra cứu profile trong **reactive service** của endpoint cần dữ liệu.

**Ranh giới thiết kế:** “Ai là người gọi?” có thể được xác nhận bằng JWT; “người này trong database đang có trạng thái/quyền nào?” là quyết định của local account service hoặc resource policy, có thể được kiểm tra khi thực sự cần.

### 4.2. Bảng quyết định vị trí lookup

| Nhu cầu | Vị trí nên cân nhắc | Vì sao |
| --- | --- | --- |
| Chỉ cần `sub`, `scope`, issuer | Không lookup; converter mặc định | Tránh I/O không cần thiết |
| Muốn tên principal lấy từ một JWT claim đã xác minh | `ReactiveJwtAuthenticationConverter.setPrincipalClaimName(...)` | Không cần database |
| Tất cả protected endpoints đòi local account enabled | Custom **reactive JWT converter** | Xác thực chung phụ thuộc account state |
| Chỉ `/api/me` cần hồ sơ trong DB | Controller/service reactive | Không làm mọi request phải đọc profile |
| Phân quyền trên Order 42, tenant hiện tại | Reactive authorization/service/repository | Quyền theo từng resource, không phù hợp global principal |
| Tất cả requests cần kiểm tra role sống trong DB | Reactive converter hoặc authorization manager có cache policy | Quyền có thể thay đổi sau khi phát JWT |
| Quyền dựa trên URL path và trạng thái đơn | Service/method-level resource policy | Chưa biết order ID ở converter chung |

Một quy tắc thực dụng: **đặt lookup ở lớp hẹp nhất đáp ứng điều kiện bảo mật cần thiết**, không biến authentication converter thành một business workflow lớn.

## 5. Pipeline JWT trong Spring Security WebFlux

Với WebFlux Resource Server:

~~~text
ServerWebExchange
  |
  v
SecurityWebFilterChain
  |
  v
Bearer token extraction
  |
  v
ReactiveJwtDecoder
     verify signature, issuer, audience, exp/nbf...
  |
  v
Converter<Jwt, Mono<AbstractAuthenticationToken>>
     default: claims -> JwtAuthenticationToken
     custom: reactive lookup -> mapping -> JwtAuthenticationToken
  |
  v
Authentication trong Reactor Context
  |
  v
authorizeExchange, reactive method security, service policy
~~~

**WebFlux khác Servlet ở cách lưu ngữ cảnh**. Không nên giả định `SecurityContextHolder` trên một `ThreadLocal` sẽ luôn đi theo request qua mọi thread trong Reactor. Trong WebFlux, truy cập security context theo chuỗi reactive bằng **`ReactiveSecurityContextHolder`**, hoặc nhận principal qua cơ chế argument resolver của controller.

### 5.1. Các lớp và kiểu thường dùng

| Kiểu | Công dụng |
| --- | --- |
| `ReactiveJwtDecoder` | Xác minh và giải mã JWT không chặn theo pipeline phản ứng |
| `Jwt` | JWT claims đã được decoder chấp nhận |
| `Converter<Jwt, Mono<AbstractAuthenticationToken>>` | Biến JWT thành authentication theo kiểu reactive |
| `ReactiveJwtAuthenticationConverter` | Converter reactive mặc định/có cấu hình ánh xạ JWT authorities/name |
| `ReactiveJwtAuthenticationConverterAdapter` | Bọc converter **đồng bộ** để tương thích API reactive; **không biến blocking I/O thành non-blocking** |
| `JwtGrantedAuthoritiesConverter` | Map `scope`/`scp` JWT sang `SCOPE_...` (đồng bộ, CPU-only) |
| `JwtAuthenticationToken` | Một authentication phổ biến giữ principal là `Jwt` |
| `ReactiveSecurityContextHolder` | Đọc/đưa security context vào Reactor subscriber context |
| `SecurityWebFilterChain` | Bảo vệ exchange, chọn rule HTTP |
| `@EnableReactiveMethodSecurity` | Bật method security theo mô hình reactive |

Nếu đang chuyển code Servlet sang WebFlux, **không** sao chép `JwtAuthenticationConverter` (đồng bộ) rồi gọi một repository reactive bằng `.block()`. Hãy chọn converter với output `Mono` hoặc chuyển lookup sang reactive service.

## 6. Chuẩn bị dữ liệu liên kết danh tính

Giả sử ứng dụng dùng PostgreSQL và Spring Data R2DBC. Bảng minh họa:

~~~sql
CREATE TABLE identity_links (
    id BIGSERIAL PRIMARY KEY,
    issuer VARCHAR(320) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    internal_user_id VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_identity_issuer_subject UNIQUE (issuer, subject)
);
~~~

**Unique constraint trên `(issuer, subject)` là phần bảo vệ tính duy nhất**, không chỉ tối ưu tốc độ tra cứu. Một OAuth subject có thể trùng giữa các issuers, nên lưu mỗi `sub` đơn lẻ thường không đủ.

Record và repository:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("identity_links")
public record IdentityLink(
        @Id Long id,
        String issuer,
        String subject,
        String internalUserId,
        boolean enabled) {
}
~~~

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface IdentityLinkRepository
        extends ReactiveCrudRepository<IdentityLink, Long> {

    Mono<IdentityLink> findByIssuerAndSubject(
            String issuer, String subject);
}
~~~

Dependency nếu dùng Spring Data R2DBC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Tên phiên bản dependency được Spring Boot quản lý theo BOM khi sử dụng dependency management tương ứng. Không dùng Hibernate/JPA repository đồng bộ như thể nó là R2DBC repository chỉ vì method trả `Mono`: **I/O phía dưới phải thực sự không chặn** hoặc được cô lập có kiểm soát.

### 6.1. Không lưu mọi claim thành hồ sơ chuẩn

Identity link chỉ cần những dữ liệu tối thiểu phục vụ ánh xạ và kiểm tra account state. Không tự sao chép `email`, `roles`, `groups` hay toàn bộ JWT payload vào database mỗi request. Những field này có thể thay đổi, có liên quan quyền riêng tư hoặc cần hợp đồng cập nhật riêng.

### 6.2. Ai được tạo identity link?

**Không được auto-create một account có quyền cao chỉ vì JWT chứa `email` hoặc `sub` mới**. Account linking/onboarding phải có policy:

- Issuer thuộc tập được tin cậy.
- Subject đã qua xác minh token.
- Email có thể thay đổi hoặc chưa được verified theo profile.
- Không tự ghép account bằng email giống nhau giữa hai issuer.
- Liên kết mới có thể cần invitation, tenant membership hoặc bước phê duyệt.
- Một token Client Credentials không tự đại diện một user account.

Nếu không tìm thấy link, API có thể từ chối ở authentication **khi hợp đồng mọi caller phải có local account**, hoặc trả một trạng thái onboarding rõ ràng ở endpoint cho phép chủ thể chưa liên kết.

## 7. Custom reactive JWT converter: tra cứu rồi tạo authentication

Ví dụ cốt lõi này đáp ứng chính xác yêu cầu: **JWT đã được xác minh → truy vấn reactive identity link → kiểm tra account → tạo principal name nội bộ**.

### 7.1. Converter triển khai `Converter<Jwt, Mono<AbstractAuthenticationToken>>`

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public final class LinkedPrincipalJwtConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final IdentityLinkRepository links;
    private final JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

    public LinkedPrincipalJwtConverter(IdentityLinkRepository links) {
        this.links = links;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        // Chỉ tới đây sau khi ReactiveJwtDecoder đã xác minh JWT.
        String issuer = jwt.getIssuer() != null
                ? jwt.getIssuer().toString()
                : null;
        String subject = jwt.getSubject();

        if (issuer == null || subject == null || subject.isBlank()) {
            return Mono.error(new BadCredentialsException(
                    "Verified issuer or subject is missing"));
        }

        return links.findByIssuerAndSubject(issuer, subject)
            .switchIfEmpty(Mono.error(
                new BadCredentialsException(
                    "No local account is linked to this identity")))
            .flatMap(link -> {
                if (!link.enabled()) {
                    return Mono.error(new DisabledException(
                            "Local account is disabled"));
                }

                Collection<GrantedAuthority> tokenScopes =
                        scopeConverter.convert(jwt);
                List<GrantedAuthority> authorities =
                        new ArrayList<>();

                if (tokenScopes != null) {
                    authorities.addAll(tokenScopes);
                }

                // Chỉ cấp role chung theo dữ liệu account hợp lệ.
                authorities.add(new SimpleGrantedAuthority(
                        "ROLE_MEMBER"));

                AbstractAuthenticationToken authentication =
                        new JwtAuthenticationToken(
                                jwt,
                                authorities,
                                link.internalUserId());

                return Mono.just(authentication);
            });
    }
}
~~~

### 7.2. Vì sao cách này là reactive?

- `IdentityLinkRepository.findByIssuerAndSubject(...)` trả **`Mono<IdentityLink>`**; không có `block()`.
- `switchIfEmpty(...)` từ chối khi identity chưa được liên kết theo **hợp đồng ví dụ**.
- `flatMap(...)` tiếp tục chuỗi sau khi I/O hoàn thành.
- Nếu account disabled, chuỗi kết thúc bằng **`Mono.error(...)`**, không trả authentication giả.
- Nếu account hợp lệ, converter trả **`Mono<AbstractAuthenticationToken>`**.
- JWT ban đầu vẫn nằm trong `JwtAuthenticationToken`; `getName()` bây giờ là local user ID.

**Đây không phải một hệ thống user/role hoàn chỉnh.** Bài ví dụ chỉ cấp thêm role `ROLE_MEMBER` cho local account enabled. Nếu muốn thêm tenant-specific roles, phải có bước tra cứu membership và policy rõ ràng. Không được coi mọi người thuộc một bảng identity link là **`ROLE_ADMIN`**.

### 7.3. Vì sao dùng `iss + sub` mà không chỉ `sub`?

JWT `sub = user-842` do issuer A phát có thể khác hoàn toàn JWT `sub = user-842` do issuer B phát. Dùng `(iss, sub)` tránh **identity collision/cross-issuer account confusion**. Tuy nhiên, điều này chỉ có ý nghĩa khi **ReactiveJwtDecoder đã kiểm tra issuer/token từ nguồn tin cậy**, không cho một JWT tùy ý tự điền `iss` và truy vấn local account.

### 7.4. Vì sao giữ `JwtAuthenticationToken`?

Khi chỉ cần **name nội bộ và authorities**, giữ `JwtAuthenticationToken` có những lợi ích:

- `getPrincipal()` vẫn là JWT đã xác minh.
- `@AuthenticationPrincipal Jwt` tiếp tục có ý nghĩa.
- Các thành phần nhận biết OAuth2 Bearer authentication vẫn thấy đúng họ token.
- Không phải tự viết một subtype `Authentication` rồi xử lý toàn bộ token attributes, credential và exception integration.

**Đánh đổi:** `getPrincipal()` **không trở thành `IdentityLink` hoặc domain `User`**. Nếu controller cần nguyên đối tượng user, nên dùng reactive service tra cứu khi cần, hoặc thiết kế một authentication subtype chứa domain principal **có chủ đích** và kiểm thử tương thích với Spring Security Bearer handling.

### 7.5. Thiếu identity link: 401 hay 403?

Trong ví dụ này, **liên kết local account là điều kiện xác thực chung**. Không có link/disabled account khiến converter phát `AuthenticationException` và request thường thất bại ở authentication, phổ biến 401.

Nhưng một hệ thống khác có thể cho phép người dùng JWT hợp lệ đi tới `/api/onboarding` dù chưa có local account. Khi đó không nên đặt `switchIfEmpty(BadCredentialsException)` cho **mọi** protected endpoint. Có thể giữ authentication từ JWT và kiểm tra account link ở dịch vụ onboarding/kinh doanh; thiếu quyền truy cập một resource cụ thể khi đã xác thực thường dẫn tới 403/404 theo policy.

**Chọn trạng thái theo hợp đồng**, không dựa đơn thuần vào việc repository có trả một record hay không.

## 8. Gắn converter vào `SecurityWebFilterChain`

Một cấu hình WebFlux Resource Server với Java 17+, Spring Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.web.server
        .ServerHttpSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.core.convert.converter.Converter;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class WebFluxOrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            Converter<Jwt, Mono<AbstractAuthenticationToken>>
                    jwtAuthenticationConverter) {

        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/catalog")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                    jwtAuthenticationConverter)))
            .build();
    }
}
~~~

`LinkedPrincipalJwtConverter` ở mục 7 là Spring bean `@Component` triển khai đúng interface `Converter<Jwt, Mono<AbstractAuthenticationToken>>`, nên có thể được inject làm tham số của `apiChain(...)`. Đừng đăng ký thêm một bean converter cùng kiểu không rõ Spring sẽ chọn bean nào.

### 8.1. application.yml cấu hình JWT decoder

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}
~~~

Issuer URI và JWKS URI là **ví dụ cấu hình**, cần lấy giá trị đúng từ Identity Server. Resource Server phải xác minh JWT **trước** converter. Chỉ cấu hình issuer/JWKS **không có nghĩa mọi phiên bản tự kiểm tra audience theo mong muốn ứng dụng**; hãy thiết lập audience validator cho `orders-api` theo cách phù hợp `ReactiveJwtDecoder` và phiên bản đang dùng.

Token type/profile, hạn dùng, thuật toán được phép và xử lý rotate JWKS cũng cần được xác định trong security contract. **Không giải quyết validation JWT bằng cách đặt logic ở controller** hoặc tin các claims chưa được decoder xác minh.

### 8.2. CSRF trong cấu hình mẫu

`csrf(...disable)` ở đây được dùng trong giả định API chỉ xác thực bằng **Bearer token do Client chủ động gửi trong Authorization header**, không chấp nhận session cookie/token cookie như credential web. Nếu API dựa vào cookie tự gửi, CSRF cần được thiết kế phù hợp, bất kể JWT được xử lý theo kiểu stateless.

### 8.3. Rule HTTP vẫn cần authorization nghiệp vụ

`GET /api/orders/42` được phép ở HTTP rule nếu authentication có `SCOPE_orders.read`. **Không được suy ra mọi order đều thuộc quyền user**. Cần kiểm tra owner, tenant hoặc assignment trong reactive service/repository.

### 8.4. URL path và WebFlux khác Servlet

WebFlux sử dụng `SecurityWebFilterChain` và `ServerHttpSecurity.authorizeExchange(...)`, không phải `SecurityFilterChain`/`HttpSecurity.authorizeHttpRequests(...)` của Servlet stack. Code security giữa hai mô hình không được đổi tên class một cách cơ học rồi mong filter và context hoạt động giống nhau.

## 9. Khi chỉ cần đổi name từ JWT claim: không cần database

Nếu Authorization Server đã cung cấp một claim tin cậy phù hợp làm tên principal, có thể cấu hình `ReactiveJwtAuthenticationConverter` mà **không tra cứu I/O**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication
        .ReactiveJwtAuthenticationConverter;

@Bean
ReactiveJwtAuthenticationConverter simpleJwtConverter() {
    ReactiveJwtAuthenticationConverter converter =
            new ReactiveJwtAuthenticationConverter();
    converter.setPrincipalClaimName("sub");
    return converter;
}
~~~

`sub` thường là lựa chọn ổn định hơn display name/email trong phạm vi một issuer. Nếu dùng claim khác như `preferred_username`, phải biết nó có thể thay đổi và không nhất thiết unique. **Chọn principal name là một quyết định định danh**, không phải một bước phân quyền.

`ReactiveJwtAuthenticationConverter` mặc định có khả năng ánh xạ scope/authorities từ JWT theo profile Spring. Khi cần quyền theo DB, sử dụng converter reactive như mục 7 hoặc một `Converter<Jwt, Flux<GrantedAuthority>>` cho authorities theo cơ chế mà phiên bản hỗ trợ.

### 9.1. `ReactiveJwtAuthenticationConverterAdapter` không biến JDBC thành reactive

Adapter này có thể bọc một converter JWT **đồng bộ, CPU-only** để sử dụng trong pipeline WebFlux:

~~~java
// Ý tưởng minh họa: một converter đồng bộ chỉ đọc JWT claims
// có thể được adapter chuyển thành API reactive.
new ReactiveJwtAuthenticationConverterAdapter(
    new JwtAuthenticationConverter());
~~~

Nhưng nếu converter đồng bộ ấy gọi JPA/JDBC, LDAP blocking hoặc `WebClient.block()` thì bọc bằng adapter **không khiến I/O trở thành non-blocking**. Dùng repository reactive hoặc di chuyển lookup sang một service phản ứng đúng nghĩa.

## 10. Phương án thứ hai: chỉ tra cứu khi endpoint nghiệp vụ cần

Đây thường là lựa chọn thích hợp nếu API **không yêu cầu mọi caller có local account**. SecurityWebFilterChain có thể dùng converter JWT mặc định:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
~~~

Sau khi token được xác minh, controller/service mới truy vấn database cho những endpoint cần profile hoặc resource policy.

### 10.1. Controller nhận JWT đã xác minh và gọi reactive service

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/me")
class MyProfileController {

    private final MyProfileService profiles;

    MyProfileController(MyProfileService profiles) {
        this.profiles = profiles;
    }

    @GetMapping
    Mono<ProfileDto> myProfile(
            @AuthenticationPrincipal Jwt jwt) {

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();
        return profiles.findByExternalIdentity(issuer, subject);
    }
}
~~~

`MyProfileService` và `ProfileDto` là thành phần nghiệp vụ minh họa. Đoạn này phù hợp khi `/api/me` là endpoint cần local profile; các endpoint khác không phải chịu I/O lookup tương tự.

### 10.2. Reactive service xử lý vắng profile

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
class MyProfileService {

    private final IdentityLinkRepository links;
    private final ReactiveProfileRepository profiles;

    MyProfileService(
            IdentityLinkRepository links,
            ReactiveProfileRepository profiles) {
        this.links = links;
        this.profiles = profiles;
    }

    Mono<ProfileDto> findByExternalIdentity(
            String issuer, String subject) {

        return links.findByIssuerAndSubject(issuer, subject)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not linked")))
            .flatMap(link -> profiles
                .findByInternalUserId(link.internalUserId()))
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Profile not found")));
    }
}
~~~

`ReactiveProfileRepository`/`ProfileDto` là thành phần riêng của ứng dụng. **Không có profile** có thể trả 404, 403 hoặc một response onboarding theo hợp đồng. Đừng mặc định 404 luôn đúng; đoạn code chỉ minh họa một chính sách cho `/api/me`.

### 10.3. Tại sao phương án này khác tra cứu ngay khi authentication?

| Lookup trong converter | Lookup trong business service |
| --- | --- |
| Mỗi authentication protected cần lookup | Chỉ những endpoint sử dụng local account mới lookup |
| Không tìm thấy link có thể làm JWT không được nhận như authentication | JWT vẫn có thể hợp lệ, nhưng một thao tác nghiệp vụ bị từ chối |
| `Authentication.getName()` có thể là internal user ID | Name mặc định thường là JWT `sub` |
| Dễ thống nhất account-active gate toàn API | Dễ phân biệt các luồng user/service/onboarding |
| Tăng phụ thuộc vào database cho tất cả protected requests | Hạn chế phụ thuộc vào những chức năng cần dữ liệu |
| Có nguy cơ làm converter phình to thành business logic | Policy theo resource ở đúng service |

Không có cách nào luôn đúng cho mọi hệ thống. **Chọn vị trí lookup theo invariant**: điều kiện toàn API thì có thể đặt ở converter; điều kiện theo nghiệp vụ/resource thì đặt ở service/authorization.

## 11. Reactive Security Context: không dựa vào ThreadLocal

Trong Servlet stack, nhiều ví dụ đọc:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

Trong WebFlux, một request có thể được xử lý qua nhiều operator và threads theo Reactor. Vì vậy **không lấy `SecurityContextHolder` ThreadLocal làm nguồn mặc định cho reactive service**. Dùng:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication());
}
~~~

`ReactiveSecurityContextHolder` sử dụng **Reactor Context**, được truyền cùng subscription context khi pipeline được cấu hình đúng.

### 11.1. Đọc internal principal name trong service

Khi đã dùng converter mục 7, `Authentication.getName()` là `internalUserId`:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
class OrderQueryService {

    private final ReactiveOrderRepository orders;

    OrderQueryService(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    Mono<OrderDto> getOwnOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED)))
            .flatMap(authentication -> {
                if (!(authentication
                        instanceof JwtAuthenticationToken)) {
                    return Mono.error(new ResponseStatusException(
                            HttpStatus.UNAUTHORIZED));
                }

                String internalUserId = authentication.getName();
                // Tốt hơn so cả tenant nếu hệ thống đa tenant.
                return orders.findByIdAndOwnerUserId(
                        orderId, internalUserId);
            })
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Order not found")));
    }
}
~~~

`ReactiveOrderRepository.findByIdAndOwnerUserId(...)` và `OrderDto` là thành phần minh họa. Query phải **lọc theo owner tại database**, không chỉ fetch toàn bộ đơn rồi dựa vào UI ẩn dữ liệu. Nếu có tenant, cần lọc cả tenant và trạng thái theo policy.

**Lưu ý về lỗi:** ví dụ phản hồi 404 nhằm hạn chế tiết lộ việc đơn của người khác có tồn tại. API khác có thể chọn 403 theo contract. Điều bắt buộc là **không trả dữ liệu hoặc thực hiện thay đổi khi caller không có quyền**.

### 11.2. Lấy Authentication bằng method argument

WebFlux controller cũng có thể nhận `Authentication`/principal qua argument resolution:

~~~java
@GetMapping("/me/id")
Mono<String> internalId(Authentication authentication) {
    return Mono.just(authentication.getName());
}
~~~

Chỉ dựa vào `authentication.getName()` là internal ID khi **converter đã cam kết** điều đó. Nếu dùng converter mặc định, tên có thể vẫn là `sub`. **Không trộn hai quy ước** trong nhiều endpoints.

### 11.3. Không dùng một biến static/global để giữ principal

~~~java
// SAI nghiêm trọng:
static String currentUserId;
~~~

Các request WebFlux chạy đồng thời, có thể xen kẽ nhiều subscriber. Đưa identity vào static field hoặc dùng mutable singleton theo request có thể gây **cross-user data leakage**. Reactor Context hoặc method arguments là cách phù hợp.

## 12. Tra cứu vai trò/permission phản ứng khác tra cứu principal

Nhiều hệ thống cần lấy **roles** từ database theo identity link:

~~~text
JWT (iss, sub)
  -> identity link
  -> internal user ID
  -> roles / memberships từ DB
  -> GrantedAuthority
~~~

Đây là một lựa chọn, nhưng cần phân biệt:

- **Principal mapping**: liên kết danh tính bên ngoài với local account.
- **Authority mapping**: đưa quyền được tin cậy thành `GrantedAuthority`.
- **Resource authorization**: kiểm tra user có được làm việc với **đơn/tenant cụ thể** không.

### 12.1. Reactive authorities converter

Spring Security cung cấp `ReactiveJwtAuthenticationConverter`, có thể tùy chỉnh một converter authorities trả `Flux<GrantedAuthority>` theo interface phiên bản tương ứng.

Ví dụ khái niệm, nếu một reactive role repository trả tên role **đã được allowlist**:

~~~java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication
        .ReactiveJwtAuthenticationConverter;

import reactor.core.publisher.Flux;

ReactiveJwtAuthenticationConverter converter =
        new ReactiveJwtAuthenticationConverter();

JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

converter.setJwtGrantedAuthoritiesConverter(jwt -> {
    Flux<GrantedAuthority> scopeAuthorities =
            Flux.fromIterable(scopes.convert(jwt));

    Flux<GrantedAuthority> roleAuthorities =
            roleRepository.findAllowedRolesByIssuerAndSubject(
                    jwt.getIssuer().toString(), jwt.getSubject())
                .map(roleCode -> (GrantedAuthority)
                    new SimpleGrantedAuthority("ROLE_" + roleCode));

    return Flux.concat(scopeAuthorities, roleAuthorities);
});
~~~

`roleRepository` là reactive repository/service **được ứng dụng xây dựng**, và các role code trả về phải được giới hạn vào **allowlist**. Ví dụ này chỉ minh họa **lấy authorities phản ứng**; không đổi `JwtAuthenticationToken.getName()` sang local user ID. Khi vừa cần internal user ID vừa cần roles, custom converter tổng hợp như mục 7 hoặc một service điều phối reactive có thể phù hợp hơn.

**Cảnh báo:** `Flux.fromIterable(scopes.convert(jwt))` giả định converter trả collection có dữ liệu; tùy custom converter và framework, cần xử lý rỗng/null theo contract. Không để lỗi mapping scope làm API tự thêm quyền mặc định ngoài chính sách.

### 12.2. Không nhúng mọi tenant role vào global authentication

Ví dụ user là admin tại tenant A nhưng chỉ reader tại tenant B. Nếu converter tạo:

~~~text
ROLE_TENANT_ADMIN
~~~

không kèm ngữ cảnh tenant, một endpoint tenant B có thể hiểu sai role này và cấp quyền vượt phạm vi.

Cách an toàn hơn:

- Chỉ cấp global authorities thực sự toàn cục.
- Lưu tenant-scoped entitlements theo namespace rõ ràng **nếu policy đã được thiết kế**.
- Khi truy cập Order 42, kiểm tra tenant và membership/assignment **đối với Order 42**.
- Không tin `X-Tenant-Id` hoặc path tenant do Client gửi như bằng chứng caller thuộc tenant đó.

**Role được lấy từ database không tự loại trừ BOLA/IDOR**. Phải kiểm tra quyền đối tượng cụ thể.

## 13. Reactive authorization theo tài nguyên

Một quyền `SCOPE_orders.read` cho phép **loại thao tác đọc**, nhưng không nhất thiết cho phép đọc đơn của user khác.

Giả sử Order:

~~~json
{
  "id": "42",
  "ownerUserId": "user-0042",
  "tenantId": "tenant-A",
  "status": "PAID"
}
~~~

Một request:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <jwt-of-user-0042>
~~~

cần kiểm tra cả:

~~~text
JWT valid + aud = orders-api
AND scope orders.read
AND identity maps to user-0042
AND order belongs to tenant allowed for this caller
AND caller is owner or assigned support under policy
~~~

### 13.1. Data-filtering ngay tại repository

Đối với endpoint chỉ cho phép chủ đơn xem:

~~~java
Mono<OrderDto> findByIdAndOwnerUserId(
        String orderId, String ownerUserId);
~~~

Nếu đa tenant:

~~~java
Mono<OrderDto> findByIdAndTenantIdAndOwnerUserId(
        String orderId, String tenantId, String ownerUserId);
~~~

`tenantId` cần đến từ **membership/policy đã xác minh** (hoặc context đã được server kiểm tra), không phải cứ lấy từ query/header rồi coi là tin cậy. Việc lọc tại database có thể giúp tránh fetch nhầm dữ liệu rồi chỉ chặn ở controller.

### 13.2. Authorization manager reactive khi policy thuộc tầng HTTP

Trong một số trường hợp, có thể dùng `ReactiveAuthorizationManager<AuthorizationContext>` để kết hợp Authentication và I/O kiểm tra quyền:

~~~java
// Pseudocode minh họa flow, không phải toàn bộ class/config:
Mono<AuthorizationDecision> check(
        Mono<Authentication> authentication,
        AuthorizationContext context) {

    String id = context.getVariables().get("id");
    return authentication
        .flatMap(auth -> accessPolicy.canReadOrder(
                auth.getName(), id))
        .map(AuthorizationDecision::new)
        .defaultIfEmpty(new AuthorizationDecision(false));
}
~~~

Tùy Spring Security version, kiểu `ReactiveAuthorizationManager`/`AuthorizationContext` và cách truy cập path variables phải được cấu hình đúng trong DSL `authorizeExchange`. **Đây là pseudocode** về vị trí policy, không phải một config chạy độc lập.

Đối với hệ thống phức tạp, kiểm tra quyền trong **reactive domain service** thường rõ hơn vì service nắm trạng thái nghiệp vụ và có thể thực hiện kiểm tra/giao dịch dữ liệu ở nơi thích hợp. Nếu áp dụng policy ở HTTP layer, vẫn phải bảo vệ những đường gọi service khác nếu nghiệp vụ có thể được gọi từ job/message consumer.

### 13.3. Method security trong WebFlux

`@EnableReactiveMethodSecurity` có thể cho phép `@PreAuthorize` trên các method được proxy bảo vệ. Ví dụ:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderDto> getOrder(String orderId) {
    return orderQueryService.getOwnOrder(orderId);
}
~~~

**Scope check ở method không thay lookup quyền trên Order**. Trong code thực tế, cần bảo đảm method được gọi qua Spring proxy và trả kiểu reactive được hỗ trợ. Nếu authorization phụ thuộc trạng thái tenant/assignment, logic nên dùng một reactive policy service mà không blocking.

## 14. Mối nguy đặc biệt: tra cứu dữ liệu trước khi xác minh token

Một lỗi kiến trúc:

~~~text
HTTP Bearer JWT
  -> tự Base64 decode payload
  -> lấy sub và email
  -> tìm DB và tạo principal với ROLE_MEMBER
  -> sau đó mới kiểm tra chữ ký
~~~

Không nên làm như vậy. JWT payload trước khi xác minh có thể bị thay đổi tùy ý. Một attacker có thể tự điền `sub` của người khác hoặc `roles` đặc quyền.

Pipeline đúng:

~~~text
Bearer token
  -> ReactiveJwtDecoder kiểm tra chữ ký + validators
  -> chỉ khi thành công mới nhận Jwt
  -> Converter dùng iss/sub đã được xác minh để lookup
  -> Authentication/authorities
  -> authorization theo endpoint/resource
~~~

**Lưu ý audience:** JWT ký hợp lệ bởi issuer đúng nhưng dành cho Billing API cũng không được tự dùng cho Orders API. Phải xác nhận `aud` theo hợp đồng, không chỉ có chữ ký hợp lệ.

### 14.1. Email linking là một rủi ro riêng

Giả sử hai issuer cấp cùng `email`, hoặc user đổi email, hoặc claim `email_verified` không được profile đảm bảo. Nếu API dùng email để tự liên kết:

~~~text
email = user@example.test
  -> tìm tài khoản local trùng email
  -> mặc định nhận user đó
~~~

có thể tạo **account takeover hoặc identity confusion**. Ưu tiên một mapping được phê duyệt theo **`(iss, sub)`**, có quy trình onboarding/link account an toàn, không tự “gộp tài khoản” chỉ vì email trùng.

### 14.2. Token Client Credentials không phải user token

Một access token theo `client_credentials` có thể mang subject/client ID của service:

~~~json
{
  "sub": "nightly-sync",
  "client_id": "nightly-sync",
  "scope": "orders.sync",
  "aud": ["orders-api"]
}
~~~

Nếu custom converter bắt buộc tìm account user cho **mọi token**, service token hợp lệ có thể bị chặn. Nếu API hỗ trợ cả user và service callers, thiết kế profile riêng:

- User JWT: ánh xạ identity theo `(iss, sub)` tới local user.
- Service JWT: kiểm tra Client identity/audience và service policy riêng.
- Không biến `client_id` thành internalUserId hoặc quyền sở hữu đơn.
- Không cấp ROLE_MEMBER/ROLE_ADMIN cho mọi token chỉ vì authentication thành công.

## 15. Không chặn Netty event loop

Trong WebFlux, blocking I/O tại converter có thể làm giảm throughput nghiêm trọng. Sai:

~~~java
@Override
public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
    // Ví dụ SAI: JPA blocking call trên event loop
    LocalUser user = jpaRepository.findByExternalSubject(
            jwt.getSubject());
    return Mono.just(createAuthentication(jwt, user));
}
~~~

Một repository JPA/JDBC đồng bộ vẫn **blocking**, ngay cả khi ta bọc kết quả trong `Mono.just(...)`. `Mono.just(...)` chỉ đóng gói **giá trị đã tính xong**; nó không tự chuyển I/O blocking thành non-blocking.

### 15.1. Ưu tiên driver và client reactive

~~~text
Spring Data R2DBC / reactive identity service
  -> Mono<IdentityLink>
  -> flatMap(account validation)
  -> Mono<Authentication>
~~~

Nếu một hệ thống legacy **bắt buộc** dùng API blocking, cách cô lập tạm thời có thể là:

~~~java
Mono<LocalUser> userMono = Mono.fromCallable(
        () -> legacyBlockingRepository.findUser(issuer, subject))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là **giải pháp chuyển tiếp**, không làm driver thành reactive. Cần giới hạn concurrency, timeout, connection pool và quan sát tải. Không chạy lượng lớn blocking lookup trên event-loop, và không dùng bounded elastic như cách che đi vấn đề kiến trúc mãi mãi. Với database/service hỗ trợ reactive, nên dùng client reactive thực.

### 15.2. Không dùng `parallel()` tùy tiện

Tăng parallelism không làm database nhanh hơn nếu connection pool hoặc downstream không đủ capacity. Một request có thể cần profile, group và membership; nếu gọi ba service song song, phải quản lý fan-out, timeout, số kết nối và phản ứng khi một dependency lỗi.

`Mono.zip(...)` có thể hữu ích khi các lookup độc lập, nhưng **không được trả Authentication trước khi mọi điều kiện bắt buộc đã hoàn thành**.

## 16. Độ trễ, cache, stale roles và availability

Đặt lookup trong authentication converter khiến **mọi request protected** có thể phát sinh database/network access. Điều này tạo chi phí:

- P50/P95/P99 latency tăng do thêm một hop.
- Database/identity service trở thành dependency của authentication.
- Số lượng connection, thread và concurrent requests phải được giới hạn hợp lý.
- Nếu downstream mất khả dụng, API có thể không xác thực request dù JWT vẫn hợp lệ.
- Quyền động có thể mới hơn JWT, nhưng caching làm giảm độ mới.

### 16.1. Có nên cache identity link?

Có thể, nhưng phải định nghĩa rõ:

| Vấn đề | Quyết định cần có |
| --- | --- |
| Cache key | Tối thiểu phân biệt `issuer + subject`, và tenant/context nếu kết quả phụ thuộc tenant |
| TTL | Giới hạn theo rủi ro, account disable và chính sách cập nhật |
| Revocation | Làm sao user disabled hoặc link bị thu hồi được phản ánh sớm? |
| Authorities | Có cache role động không? Nếu có, độ trễ thu hồi quyền bao lâu? |
| Invalidation | Có event/policy version khi thay role/membership không? |
| Cache miss | Lookup reactive bình thường, không tự cho qua |
| Outage | Có được dùng snapshot còn hợp lệ không? Điều kiện nào? |

Một `Mono.cache()` gọi trên **một Publisher duy nhất** có thể cache kết quả của publisher đó; nó không tự biến mọi request JWT thành một cache có TTL và invalidation đúng. Ngược lại, global cache không thời hạn có thể giữ **account enabled** dù người dùng đã bị khóa.

### 16.2. Authentication lookup failure phải fail closed

Không dùng:

~~~java
// SAI: Lỗi DB không có nghĩa caller là admin.
return links.findByIssuerAndSubject(issuer, subject)
    .onErrorResume(ex -> Mono.just(adminIdentityLink));
~~~

Một lỗi I/O khiến hệ thống **chưa có chứng cứ tin cậy để gắn identity**. Không tạo authentication hợp lệ từ dữ liệu giả. Có thể phản hồi lỗi phụ thuộc 5xx theo policy/exception handling hoặc từ chối authentication tương ứng; nhưng **không thực thi thao tác được bảo vệ**.

### 16.3. Phân biệt “không tìm thấy link” và “DB đang lỗi”

~~~text
Mono.empty():
  -> không có bản ghi theo hợp đồng
  -> có thể từ chối account linking/onboarding

Mono.error(databaseTimeout):
  -> chưa thể xác định account
  -> dependency failure, không được cho qua
~~~

**Đừng biến mọi lỗi network thành “tài khoản không tồn tại”** khi điều tra sự cố; cũng không biến mọi lỗi network thành “tài khoản đã hợp lệ”. Log và metric phải phân biệt nhưng không tiết lộ thông tin nhạy cảm tới Client.

### 16.4. Time-of-check/time-of-use

Giả sử converter xác nhận account enabled ở T1, nhưng quyền bị thu hồi ở T2 trước khi cập nhật đơn. Nếu hành động cực nhạy cảm, kiểm tra quyền tại thời điểm **ghi dữ liệu** hoặc trong transaction/policy phù hợp có thể cần thiết.

**Một snapshot principal đầu request không tự giải quyết mọi race condition về quyền**. Đây là lý do resource policy cần ở gần thao tác nghiệp vụ, không chỉ gắn các role tại authentication.

## 17. Kiểm thử converter bằng Reactor Test `StepVerifier`

Vì converter trả `Mono<AbstractAuthenticationToken>`, có thể unit test logic mà không chạy web server.

### 17.1. Tạo JWT fixture

~~~java
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;

static Jwt jwt(String subject) {
    return Jwt.withTokenValue("test-jwt-not-signed")
        .header("alg", "RS256")
        .issuer("https://identity.example.test/realms/shop")
        .subject(subject)
        .audience(List.of("orders-api"))
        .claim("scope", "orders.read")
        .build();
}
~~~

Đây là **Jwt object giả cho unit test**, không phải token được ký hoặc xác minh thật. Nó chỉ phù hợp để kiểm tra logic **sau decoder**. Signed-JWT integration test phải dùng token được ký bằng khóa test và decoder thật.

### 17.2. Test principal name được ánh xạ

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class LinkedPrincipalJwtConverterTest {

    private static final String ISSUER =
        "https://identity.example.test/realms/shop";

    @Test
    void mapsVerifiedExternalIdentityToLocalPrincipalName() {
        IdentityLinkRepository repo =
                mock(IdentityLinkRepository.class);
        when(repo.findByIssuerAndSubject(
                ISSUER, "external-user-842"))
            .thenReturn(Mono.just(new IdentityLink(
                1L,
                ISSUER,
                "external-user-842",
                "user-0042",
                true)));

        var converter = new LinkedPrincipalJwtConverter(repo);

        StepVerifier.create(
                converter.convert(jwt("external-user-842")))
            .assertNext(authentication -> {
                assertTrue(authentication
                        instanceof JwtAuthenticationToken);
                assertEquals("user-0042",
                        authentication.getName());
                assertTrue(authentication.getAuthorities()
                    .stream()
                    .anyMatch(a ->
                        a.getAuthority().equals(
                            "SCOPE_orders.read")));
            })
            .verifyComplete();
    }
}
~~~

`jwt(...)` là helper ở mục 17.1, cần đặt vào class test hoặc helper chung. JUnit/Mockito/Reactor Test được dùng đúng phạm vi **unit test converter**, không chạy Gradle hay dùng JWT ký production.

### 17.3. Test không có local account

~~~java
@Test
void rejectsUnlinkedIdentity() {
    IdentityLinkRepository repo = mock(IdentityLinkRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER, "unknown-subject"))
        .thenReturn(Mono.empty());

    var converter = new LinkedPrincipalJwtConverter(repo);

    StepVerifier.create(converter.convert(jwt("unknown-subject")))
        .expectError(BadCredentialsException.class)
        .verify();
}
~~~

Nếu hệ thống cho phép onboarding không có local account, test này cần thay theo **contract khác**, không copy mặc định.

### 17.4. Test disabled account và DB failure

~~~java
@Test
void rejectsDisabledAccount() {
    IdentityLinkRepository repo = mock(IdentityLinkRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER, "external-user-842"))
        .thenReturn(Mono.just(new IdentityLink(
            1L, ISSUER, "external-user-842", "user-0042", false)));

    var converter = new LinkedPrincipalJwtConverter(repo);
    StepVerifier.create(converter.convert(jwt("external-user-842")))
        .expectError(DisabledException.class)
        .verify();
}

@Test
void doesNotAuthenticateWhenRepositoryFails() {
    IdentityLinkRepository repo = mock(IdentityLinkRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER, "external-user-842"))
        .thenReturn(Mono.error(
            new IllegalStateException("Database unavailable")));

    var converter = new LinkedPrincipalJwtConverter(repo);
    StepVerifier.create(converter.convert(jwt("external-user-842")))
        .expectError(IllegalStateException.class)
        .verify();
}
~~~

Đây là các **method test minh họa** dùng cùng imports/fixture như mục trước. Chúng xác minh không có fallback tự cấp quyền khi lookup trả rỗng, disabled hoặc error.

### 17.5. Test một subject giống nhau ở hai issuer

Một test quan trọng:

~~~text
iss=shop,    sub=user-842 -> internal user-0042
iss=partner, sub=user-842 -> internal user-1290
~~~

Verifier phải xác nhận repository được gọi với **đúng issuer và subject** trong mỗi trường hợp, và authentication name không bị lẫn nhau. Đây là negative test cho identity confusion/cross-issuer mapping.

## 18. WebFlux test với `WebTestClient`

Spring Security Test hỗ trợ `mockJwt()` cho WebFlux nhằm dựng authentication với claims/authorities giả lập.

Ví dụ minh họa:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

**Điểm quan trọng:** `mockJwt()` có thể **bỏ qua `ReactiveJwtDecoder` và custom converter**, bằng cách đặt authentication giả lập vào web test. Nó là công cụ tốt để kiểm tra authorization/handler **khi đã có Authentication**, không chứng minh reactive identity lookup được gọi hoặc JWT signature hợp lệ.

### 18.1. Bộ test cần tách ra

| Mức test | Công cụ | Điều được chứng minh |
| --- | --- | --- |
| Unit converter | `StepVerifier` + mock reactive repository | `(iss, sub)` mapping, disabled account, authority/name, error propagation |
| HTTP authorization | `WebTestClient` + `mockJwt()` | Rule `pathMatchers`, scope và 401/403 paths khi mock authentication |
| JWT decoder integration | Signed test JWT + mock JWKS + real `ReactiveJwtDecoder` | Chữ ký, issuer, audience, time và decoder |
| Authentication integration | Signed JWT + real converter + test R2DBC/service | Tra cứu non-blocking chạy trước khi tạo authentication |
| Business policy | Repository/service test | Owner, tenant, membership, no cross-user access |
| Load/resilience | Controlled dependency latency/failure | Timeout, pool pressure, fallback fail-closed |

### 18.2. Tình huống kiểm thử đầu-cuối

~~~text
1. Signed JWT hợp lệ, account enabled, scope đủ
   -> authenticated, name = localUserId, đi qua HTTP rule

2. Signed JWT hợp lệ, account link không tồn tại
   -> bị từ chối theo contract bắt buộc linking

3. Signed JWT hợp lệ, account disabled
   -> bị từ chối

4. Signed JWT hợp lệ, scope không đủ
   -> authentication có thể thành công, HTTP authorization 403

5. Chữ ký JWT sai
   -> decoder từ chối, converter/repository không được dùng làm nguồn tin

6. Issuer/audience sai
   -> decoder/validator từ chối trước lookup

7. JWT hợp lệ, account enabled, có scope,
   nhưng Order 42 thuộc tenant khác
   -> business policy từ chối

8. Identity DB timeout
   -> không có authentication hợp lệ giả, không chạy protected action

9. JWT của service Client Credentials
   -> không bị ép nhầm vào user policy nếu endpoint hỗ trợ service
~~~

Nên assert thêm **không có ghi database hoặc event nghiệp vụ** khi request bị từ chối. Một HTTP status 403 cuối cùng không đủ nếu side effect đã xảy ra trước đó.

### 18.3. Giả lập bất đồng bộ để kiểm tra pipeline

Trong unit test có thể cho repository trả `Mono.defer(...)` hoặc một publisher hoàn thành chậm, xác nhận authentication **không xuất hiện trước khi lookup hoàn thành**. Không tự gọi `subscribe()` trong converter để “đẩy nhanh” xử lý.

Một bài test có thể dùng `StepVerifier.withVirtualTime(...)` khi publisher dùng scheduler/clock thích hợp; đây là kỹ thuật test Reactor, không thay test kết nối database thật. Mục tiêu là **chuỗi authentication chờ đúng kết quả**, không phải tăng số lượt subscribe.

## 19. Quan sát, bảo mật thông tin và vận hành

Một reactive principal lookup đưa **dịch vụ identity/database vào đường nóng của authentication**. Cần quan sát:

- Thời gian `ReactiveJwtDecoder` xác minh token.
- Tỷ lệ converter lookup: hit/missing/disabled/error.
- Latency của identity repository (P95/P99), kết nối và pool.
- Số lỗi timeout, saturation, rate limit hoặc circuit breaker.
- Tỷ lệ request không đủ scope sau authentication.
- Số trường hợp bị chặn vì tenant/owner.

**Không log nguyên JWT**, Authorization header, refresh token hoặc client secret. `iss`/`sub`/local user ID cũng có thể là dữ liệu định danh cần quản lý theo quy định audit/PII. Với issuer sai hoặc JWT chưa xác minh, mọi giá trị claim đọc từ token phải xem như **dữ liệu do caller kiểm soát**, không dùng làm metric label không giới hạn.

### 19.1. Quyền và identity có thể thay đổi trong lúc JWT chưa hết hạn

Một JWT có `exp` sau 30 phút nhưng local account bị khóa sau 5 phút. Nếu converter luôn tra cứu account enabled, request sau khi khóa có thể bị từ chối nhanh theo database. Nếu cache principal/role lâu, account disabled có thể không được phản ánh kịp.

Việc bảo vệ API phụ thuộc các quyết định:

- Cần thu hồi user/role gần như tức thì hay chấp nhận độ trễ?
- Cache theo (iss,sub), token hay tenant?
- Có sự kiện invalidation không?
- Khi identity database down, có chấp nhận cached active status còn hợp lệ trong TTL không?
- Nếu identity link bị thay đổi, authentication cũ đã cache có thể gắn sai user không?

Đây là **trade-off giữa hiệu năng, khả dụng và độ mới của quyền**, không thể giải bằng một dòng `.cache()`.

### 19.2. Không dùng global mutable principal

WebFlux phục vụ nhiều request đồng thời. Một singleton có field `currentPrincipal` hoặc static `currentUserId` là thiết kế sai: giá trị của user A có thể bị user B ghi đè. Dùng immutable data, Reactor Context, method arguments và database queries có điều kiện quyền.

### 19.3. Khi AS/JWKS down và khi DB identity down

Đây là hai failure modes khác nhau:

| Dependency | Vai trò | Khi không sẵn sàng |
| --- | --- | --- |
| Authorization Server / JWKS | Cung cấp khóa/metadata để xác minh JWT | Decoder có thể dùng khóa cache hợp lệ theo policy; không tự chấp nhận token chưa xác minh |
| Identity Link DB | Ánh xạ external principal sang local user | Converter bắt buộc linking không thể xác thực tiếp nếu không có kết quả đáng tin |
| Order DB | Kiểm tra quyền và trả resource | Không trả tài nguyên khi không kiểm tra được resource policy |

**Không biến outage thành `permitAll()` hay cấp ROLE_ADMIN mặc định**. Phân biệt lỗi vận hành khỏi identity-not-found trong log nội bộ, nhưng không tiết lộ token/PII nhạy cảm cho Client.

## 20. Những lỗi triển khai phổ biến

### “Dùng `.block()` trong reactive JWT converter cho nhanh”

Sai mô hình WebFlux, có thể nghẽn event-loop. Dùng R2DBC/WebClient phản ứng và trả `Mono<Authentication>`.

### “Bọc JPA bằng `Mono.just(jpaRepository.find(...))` là non-blocking”

Không. JPA đã chặn thread **trước khi `Mono.just` chạy**. Dùng driver reactive hoặc cô lập legacy blocking I/O trong bounded scheduler như giải pháp chuyển tiếp.

### “`ReactiveJwtAuthenticationConverterAdapter` tự chuyển blocking repo thành reactive”

Không. Adapter chỉ bọc API converter đồng bộ; nó không làm I/O bên trong biến thành non-blocking.

### “Converter được gọi trước khi JWT decoder kiểm tra chữ ký”

Không phải pipeline chuẩn. Converter của Resource Server nhận một `Jwt` sau khi decoder chấp nhận token. Đừng tự viết filter decode payload chưa xác minh để lookup quyền.

### “`sub` đủ duy nhất cho mọi issuer”

Không khi hệ thống tin nhiều issuer. Cần ràng buộc issuer và subject.

### “Có email trùng thì tự gắn account”

Nguy hiểm do email mutable/cross-issuer/verification khác nhau. Account linking cần quy trình riêng.

### “Đổi `getName()` nghĩa là `getPrincipal()` tự thành domain User”

Không. `JwtAuthenticationToken(jwt, authorities, name)` vẫn giữ principal là `Jwt`, chỉ thay name.

### “Cần quyền trên Order 42 thì lookup trong authentication converter”

Thường không phù hợp: converter không biết resource cụ thể và có thể chạy cho endpoint không cần đơn hàng. Hãy kiểm tra ở reactive business policy hoặc authorization layer theo resource.

### “Mọi token user và service đều phải có local user ID”

Không nếu API hỗ trợ Client Credentials service principal. Tách contract và quyền cho người dùng/dịch vụ.

### “Một ROLE_TENANT_ADMIN chung đủ cho mọi tenant”

Không. Role thuộc tenant A không được cấp quyền tenant B nếu không có scope/tenant binding và kiểm tra resource.

### “Tra cứu repository lỗi thì tạo principal guest/admin để tránh downtime”

Fail open. Không có bằng chứng identity hợp lệ thì không được thực hiện protected action.

### “`Authentication.getName()` là email vì OIDC login có email”

Không mặc định. Tên phụ thuộc converter; JWT Resource Server không đồng nghĩa OAuth2/OIDC Client login principal.

### “Dùng `SecurityContextHolder` ThreadLocal trong mọi reactive operator”

Không an toàn với Reactor thread switching. Dùng `ReactiveSecurityContextHolder` hoặc WebFlux argument resolver.

### “MockJwt WebTestClient pass nghĩa converter reactive chạy đúng”

Không. `mockJwt()` có thể bypass decoder/converter; phải unit test converter và integration test với signed JWT.

### “Scope đúng là được xem mọi đơn”

Không. Phải kiểm tra owner, tenant, assignment và policy dữ liệu.

### “Cache không TTL sẽ tăng hiệu năng mà không ảnh hưởng quyền”

Sai. Disabled status, role và membership có thể stale. Cần TTL/invalidation và bảo vệ cache key.

## 21. Checklist khi xây dựng principal mapping trong WebFlux

1. JWT có được xác minh bằng `ReactiveJwtDecoder` với issuer/audience/time đúng hợp đồng trước khi converter chạy không?
2. `(iss, sub)` có phải khóa liên kết danh tính được AS bảo đảm không?
3. Nhu cầu local user lookup có bắt buộc cho **mọi** protected endpoint không?
4. Nếu chỉ vài endpoint cần profile, đã dời lookup tới service phù hợp chưa?
5. Repository và HTTP client có thực sự non-blocking không?
6. Có `.block()` hoặc `.subscribe()` thủ công trong security flow không?
7. Account thiếu/disabled có dẫn tới hành vi fail-closed theo contract không?
8. DB outage có bị phân biệt với account-not-found trong vận hành không?
9. `Authentication.getName()` và `getPrincipal()` đã được định nghĩa đúng và không bị nhầm lẫn chưa?
10. Authorities từ token và local role có prefix/mapping allowlist rõ ràng không?
11. Tenant-specific permission có được kiểm tra với tenant/resource cụ thể không?
12. JWT Client Credentials có cần policy riêng không?
13. Cache có TTL, invalidation và không dùng key dễ trộn users không?
14. Service có đọc context qua Reactor hoặc nhận Authentication đúng cách không?
15. Test có bao gồm signed JWT, WebTestClient, StepVerifier và negative cases không?
16. Request bị từ chối có chắc chắn **không gây side effect** không?

## 22. Bài tập tình huống

**Tình huống A:** JWT đã ký đúng, `sub=external-user-842`, database lưu `user-0042`. Muốn `Authentication.getName()` trả `user-0042` trong WebFlux, nên làm gì?

**Có thể** dùng custom `Converter<Jwt, Mono<AbstractAuthenticationToken>>` để tra cứu `(iss, sub)` phản ứng rồi tạo `JwtAuthenticationToken(jwt, authorities, "user-0042")`. Không cần bắt buộc custom principal subtype nếu chỉ cần name nội bộ.

**Tình huống B:** Developer viết `identityLinkRepository.findByIssuerAndSubject(...).block()` trong JWT converter. Rủi ro?

**Blocking event loop**, giảm concurrency và có thể phát sinh lỗi Reactor. Trả `Mono` từ converter và để Spring subscribe; dùng repository/reactive client thật.

**Tình huống C:** Hai issuer đều có `sub="user-842"` nhưng ánh xạ đến hai local users. Nếu chỉ lookup theo `sub` thì sao?

Có thể **gắn nhầm tài khoản**, gây quyền và dữ liệu chéo issuer. Lookup bằng `(iss, sub)` theo contract, sau khi JWT đã được xác minh.

**Tình huống D:** API có endpoint catalog chỉ cần scope, nhưng converter luôn yêu cầu user profile. Profile DB down, catalog protected cũng down. Có cách thiết kế nào phù hợp hơn?

Nếu account link **không phải điều kiện chung**, giữ principal JWT ở authentication và chỉ tra cứu profile tại những endpoint cần nó. Việc dời lookup giúp giảm phụ thuộc không cần thiết.

**Tình huống E:** Token có scope `orders.read`, local account enabled, nhưng Order 42 thuộc tenant khác. Có cho phép?

**Không.** Authentication mapping và HTTP scope đều có thể thành công; quyền resource vẫn phải từ chối theo owner/tenant.

**Tình huống F:** Một token Client Credentials có `client_id=nightly-sync`, không có local user. Converter bắt tìm user rồi trả 401. Có phải token hỏng?

**Chưa chắc.** Token service có thể hợp lệ nhưng **không phù hợp contract converter user-only**. Nếu API hỗ trợ service, cần principal/policy riêng; không tự coi service là user.

**Tình huống G:** Unit test dùng `mockJwt()` và WebTestClient trả 200. Có chứng minh database reactive lookup được gọi không?

**Không.** `mockJwt()` có thể đặt authentication trực tiếp. Test converter bằng `StepVerifier` và kiểm thử chuỗi thật với JWT có chữ ký + decoder + repository.

**Tình huống H:** JWT còn 30 phút, account đã disabled nhưng cache local account tồn tại vô hạn. Rủi ro?

API có thể tiếp tục nhận account đã bị vô hiệu. Cần TTL/invalidation phù hợp chính sách thu hồi và không cache không hạn định.

**Tình huống I:** Converter gọi repository bằng `subscribe()` rồi trả `Mono.just(authentication)` ngay. Điều gì sai?

Authentication có thể hoàn thành **trước lookup**, lỗi không được truyền theo pipeline và dễ gây race condition. Kết quả lookup phải nằm trong **cùng chuỗi `Mono<Authentication>`** mà Spring Security chờ.

**Tình huống J:** Đổi `JwtAuthenticationToken` name thành local user ID, sau đó dùng `@AuthenticationPrincipal Jwt jwt`. Controller có nhận domain user không?

**Không.** Principal vẫn là `Jwt`; chỉ `getName()` đổi. Muốn domain user thì tra cứu reactive khi cần hoặc thiết kế authentication subtype với contract riêng.

---

## Kết luận

Trong **Spring Security JWT Resource Server dùng WebFlux**, ánh xạ principal có tra cứu dữ liệu nội bộ phải tôn trọng **hai ranh giới**: **JWT được xác minh trước**, sau đó **tra cứu danh tính/quyền nghiệp vụ bằng pipeline reactive non-blocking**. Nếu mọi protected request bắt buộc có local user enabled, một custom **`Converter<Jwt, Mono<AbstractAuthenticationToken>>`** có thể tra cứu `(iss, sub)` bằng R2DBC/WebClient, rồi tạo `JwtAuthenticationToken` với `getName()` là internal user ID. Không dùng `.block()`, `.subscribe()` thủ công hoặc fallback cấp quyền khi repository lỗi.

Nếu chỉ một số thao tác cần profile hay quyền trên tài nguyên, nên giữ **JWT authentication gọn nhẹ** và **tra cứu phản ứng tại service/authorization layer khi nghiệp vụ thực sự cần**. `ReactiveSecurityContextHolder`, Reactor `Mono`/`Flux` và reactive repository giúp truyền identity qua WebFlux đúng cách. Trong mọi lựa chọn, không được lẫn `sub` giữa issuers, không suy role admin từ token/local lookup tùy ý, phải kiểm tra tenant/owner tại resource và dùng **StepVerifier, WebTestClient cùng integration test signed JWT** để xác nhận cả đường cho phép lẫn đường bị từ chối.
