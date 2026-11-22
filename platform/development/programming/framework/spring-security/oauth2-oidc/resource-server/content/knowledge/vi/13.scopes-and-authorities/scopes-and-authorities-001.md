# Scope trong OAuth và GrantedAuthority trong Spring Security

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, một access token hợp lệ giúp API biết **credential này có thể được tin cậy**. Nhưng để quyết định một request có được phép đọc đơn hàng, cập nhật sản phẩm hoặc thực hiện thao tác quản trị hay không, API còn phải xem **quyền được cấp cho token** và **chính sách truy cập của tài nguyên**.

Hai khái niệm xuất hiện liên tục ở đây là:

- **OAuth 2.0 scope:** chuỗi biểu diễn phạm vi quyền mà Authorization Server có thể cấp cho một access token; ý nghĩa cụ thể được hệ thống OAuth định nghĩa.
- **Spring Security `GrantedAuthority`:** đối tượng mô tả một authority đã được đưa vào `Authentication` trong ứng dụng Java, để các bộ phận authorization của Spring Security có thể đánh giá.

Chúng **liên quan nhưng không đồng nhất**. Một scope có thể được chuyển thành một `GrantedAuthority`; ngoài scope, một `Authentication` còn có thể chứa authorities từ vai trò, quyền nghiệp vụ hoặc cơ chế xác thực khác. Ngược lại, việc Spring Security có authority cũng không tự chứng minh rằng người gọi sở hữu một bản ghi dữ liệu cụ thể.

Bài học giải thích đường đi từ lúc client xin scope đến lúc Resource Server kiểm tra `hasAuthority("SCOPE_orders.read")`, các cách mapping mặc định và tùy chỉnh, phân biệt với role, cùng những ranh giới bảo mật cần giữ khi dùng JWT hoặc opaque access token.

## 1. Mô hình tổng thể: scope từ OAuth, authority trong Spring Security

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders Resource Server
    C->>AS: Yêu cầu access token với scope orders.read
    AS->>AS: Xác thực client/user và áp chính sách cấp quyền
    AS-->>C: Access token có phạm vi được cấp
    C->>RS: GET /api/orders, Authorization: Bearer token
    RS->>RS: Xác minh token và lấy scopes đã được cấp
    RS->>RS: Chuyển orders.read thành SCOPE_orders.read
    RS->>RS: Kiểm tra endpoint authority + quyền dữ liệu
    RS-->>C: 200 / 401 / 403 tùy kết quả
```

Trong sơ đồ:

1. **Client yêu cầu** phạm vi truy cập; việc yêu cầu không buộc Authorization Server phải cấp.
2. **Authorization Server quyết định** scope nào thực sự được cấp sau khi xét client, người dùng, grant type, consent và chính sách.
3. **Access token mang hoặc tham chiếu** các quyền đã cấp theo hợp đồng; với JWT chúng có thể ở claim `scope`/`scp`, với opaque token chúng có thể được trả về bởi introspection.
4. **Resource Server xác thực token trước**, rồi chuyển thông tin quyền đã được xác thực thành authorities nếu cần.
5. **Spring Security kiểm tra authorities** cho URL hoặc method.
6. **Ứng dụng kiểm tra quyền với đối tượng dữ liệu** như chủ đơn hàng, tenant và trạng thái.

Không có bước nào cho phép frontend tự thêm chuỗi `orders.write` vào HTTP header để nâng quyền. Nếu muốn thay đổi phạm vi, client phải có một credential được **Authorization Server cấp hợp lệ**.

### 1.1. Ba câu hỏi không thay thế nhau

| Câu hỏi | Cơ chế thường dùng | Ví dụ |
|---|---|---|
| **Token có đáng tin và dành cho API này?** | JWT signature/issuer/audience/time hoặc introspection | `iss` tin cậy, `aud` chứa `orders-api`, `exp` còn hạn |
| **Token được cấp loại thao tác nào?** | OAuth scope → `GrantedAuthority`, policy endpoint | `orders.read` → `SCOPE_orders.read` |
| **Chủ thể được thao tác trên bản ghi nào?** | Business authorization, ownership, tenant, ACL | `user-842` chỉ đọc đơn hàng của mình |

Một API an toàn phải giải quyết **cả ba** câu hỏi theo hợp đồng, không chỉ có chữ ký đúng hoặc scope đúng.

## 2. Scope trong OAuth 2.0 là gì?

Theo OAuth 2.0, scope là một cách biểu diễn **phạm vi truy cập được yêu cầu hoặc được cấp** cho access token. Các giá trị scope là những **chuỗi phân biệt chữ hoa/chữ thường** do Authorization Server và Resource Server thống nhất; bản thân OAuth không quy định rằng `orders.read` phải có nghĩa gì.

Ví dụ:

```text
orders.read
orders.write
inventory.read
payments.refund
```

Một hệ thống có thể chọn cách đặt tên `orders:read` thay cho `orders.read`. Đây là quyết định thiết kế của API. Spring Security không tự hiểu rằng dấu chấm hay dấu hai chấm có ý nghĩa phân cấp; đối chiếu authority thường là **so sánh chuỗi chính xác**.

### 2.1. Scope được yêu cầu và scope thực sự được cấp

Ở một authorization request, client có thể yêu cầu nhiều scope:

```http
GET /authorize?response_type=code&client_id=shop-web&scope=openid%20profile%20orders.read&redirect_uri=https%3A%2F%2Fclient.example%2Fcallback&state=xyz HTTP/1.1
Host: idp.example.com
```

Ví dụ URL trên chỉ minh họa tham số `scope`, **không phải một authorization request đầy đủ** cho triển khai production: ứng dụng thực tế cần các điều kiện về PKCE, redirect URI, state/nonce theo luồng tương ứng.

Authorization Server có thể:

- Cấp tất cả scope đã yêu cầu.
- Chỉ cấp một tập con vì quyền của client/user/consent.
- Từ chối yêu cầu do scope không hợp lệ hoặc không được phép.
- Áp thêm quy tắc về audience, loại client, grant type và chính sách tài nguyên.

**Resource Server phải dựa vào scope đã được cấp và xác thực qua token/introspection**, không dựa vào danh sách scope mà client từng yêu cầu.

Ví dụ:

```text
Client yêu cầu:          orders.read orders.write
AS cấp trong token:      orders.read
Resource Server nhận:    chỉ quyền orders.read
```

Client không có quyền ghi chỉ vì từng gửi tham số `scope=orders.write` khi xin token.

### 2.2. Scope là tập quyền phẳng, không phải biểu thức mặc định

Với hai scope:

```text
orders.read
orders.write
```

OAuth 2.0 **không tự nói** rằng `orders.write` bao hàm `orders.read`. Nếu một API muốn scope ghi tự bao gồm quyền đọc, cần mã hóa rõ quy tắc đó trong authorization policy hoặc quy tắc cấp token của IdP. Một kiểm tra `hasAuthority("SCOPE_orders.read")` bình thường sẽ không tự thỏa chỉ vì token có `SCOPE_orders.write`.

Tương tự:

```text
admin
orders.*
orders.read.all
```

không có wildcard hoặc role hierarchy tự động nếu ứng dụng không triển khai. Không coi tên scope trông “mạnh hơn” là một quyền thay thế khi policy chỉ kiểm tra chuỗi đúng.

### 2.3. Scope không nhất thiết là quyền người dùng

Access token có thể được cấp qua:

- **Authorization Code + PKCE**: thường liên quan quyền của một client thay mặt end-user đã xác thực.
- **Client Credentials**: đại diện cho một client/service, không có người dùng đăng nhập tương tác.
- **Token Exchange/ủy quyền nhiều tầng**: quyền có thể được giới hạn lại hoặc gắn với actor/delegation theo hợp đồng cụ thể.

Vì vậy, `orders.read` không nói token thuộc người dùng hay service nào. Để biết principal, cần kiểm tra token type, `sub`, `client_id`, actor claim và chính sách của issuer trong từng grant. Không lấy scope làm bằng chứng “một người dùng đã đăng nhập”.

### 2.4. Scope khác audience

**Audience** trả lời “token dành cho Resource Server nào?”, trong khi **scope** trả lời “token được phép làm loại việc gì?”.

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Orders API chỉ nên chấp nhận token khi issuer/khóa/chữ ký/thời gian và audience đều hợp lệ. Token có `scope=orders.read` nhưng `aud=["payments-api"]` **không phải access token đúng đối tượng nhận cho Orders API**. Không sử dụng scope để bỏ qua audience.

## 3. GrantedAuthority của Spring Security là gì?

`GrantedAuthority` thuộc Spring Security, không phải một trường chuẩn của OAuth. Interface có phương thức:

```java
package org.springframework.security.core;

public interface GrantedAuthority extends java.io.Serializable {
    String getAuthority();
}
```

Implementation phổ biến là `SimpleGrantedAuthority`:

```java
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

GrantedAuthority readOrders =
    new SimpleGrantedAuthority("SCOPE_orders.read");

System.out.println(readOrders.getAuthority());
// SCOPE_orders.read
```

Một `Authentication` chứa collection các authorities:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null) {
    for (GrantedAuthority authority : authentication.getAuthorities()) {
        System.out.println(authority.getAuthority());
    }
}
```

Ví dụ chỉ nhằm cho thấy API; trong ứng dụng thật không nên in toàn bộ thông tin người dùng/quyền vào log production không có kiểm soát. `SecurityContextHolder` thông thường cung cấp Authentication của **request/thread hiện tại** sau khi Spring Security đã xác thực.

### 3.1. Authority là “đầu vào” cho bộ máy authorization

Khi cấu hình:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read"))
```

Spring Security không trực tiếp xem claim `scope` raw trong đoạn DSL này. Nó kiểm tra collection `GrantedAuthority` của Authentication đã được tạo từ token. Chính vì vậy, bước **chuyển scope thành authority** là cầu nối quyết định.

`GrantedAuthority` có thể đại diện:

- Scope được cấp trong OAuth access token.
- Role do ứng dụng hoặc IdP ánh xạ.
- Permission nội bộ từ một nguồn quyền tin cậy.
- Quyền do một cơ chế authentication khác cấp.

Không phải tất cả authorities đều nhất thiết xuất phát từ OAuth scope.

### 3.2. Vì sao có tiền tố SCOPE_?

Mặc định Spring Security JWT Resource Server thường chuyển một scope:

```text
OAuth scope:           orders.read
Spring authority:      SCOPE_orders.read
```

Tiền tố `SCOPE_` giúp phân biệt **scope của access token** với các authority khác như role `ROLE_ADMIN` hoặc permission tự định nghĩa. Nó là **quy ước mapping của Spring Security**, không phải phần bắt buộc trong giá trị scope mà Authorization Server phải phát hành.

Vì vậy IdP thường phát hành:

```json
{
  "scope": "orders.read orders.write"
}
```

chứ **không cần** phát hành:

```json
{
  "scope": "SCOPE_orders.read SCOPE_orders.write"
}
```

Nếu IdP phát hành sẵn `SCOPE_orders.read`, converter mặc định có thể thêm tiếp tiền tố và tạo `SCOPE_SCOPE_orders.read`. Hợp đồng giữa IdP và API cần thống nhất scope raw và mapping của ứng dụng.

## 4. Từ JWT claim scope/scp đến GrantedAuthority

Với signed JWT Resource Server, các thành phần thường gặp:

```mermaid
flowchart LR
    H["Authorization: Bearer JWT"] --> BF["BearerTokenAuthenticationFilter"]
    BF --> JP["JwtAuthenticationProvider"]
    JP --> DEC["JwtDecoder<br/>signature + claims validators"]
    DEC --> JAT["JwtAuthenticationConverter"]
    JAT --> GAC["JwtGrantedAuthoritiesConverter"]
    GAC --> A["JwtAuthenticationToken<br/>principal + authorities"]
    A --> SEC["SecurityContextHolder"]
    SEC --> AUTHZ["hasAuthority / method security"]
```

Lưu ý `JwtAuthenticationProvider` sử dụng decoder để xác minh JWT. Sau khi token được xác thực, converter mới biến claims đã được tin cậy thành authorities. **Giải mã payload bằng Base64 rồi tự thêm authorities trước khi xác minh chữ ký là sai ranh giới tin cậy**.

### 4.1. JWT với scope dạng chuỗi

Payload minh họa:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "scope": "orders.read orders.write"
}
```

Khi xác thực thành công và dùng mapping mặc định, Authentication thường có:

```text
Principal name:
  user-842

GrantedAuthority:
  SCOPE_orders.read
  SCOPE_orders.write
```

Token có thể mang nhiều scope trong **một chuỗi cách nhau bằng dấu cách** theo quy tắc của OAuth. Các tên scope như `orders.read` là toàn bộ giá trị; dấu chấm trong tên scope không có vai trò tách token.

### 4.2. JWT với scp dạng mảng

Một số IdP sử dụng claim `scp`:

```json
{
  "scp": ["orders.read", "orders.write"]
}
```

`JwtGrantedAuthoritiesConverter` của Spring Security hỗ trợ đọc các claim authority phổ biến như `scope` hoặc `scp`, với khả năng nhận giá trị dạng chuỗi hoặc collection theo đường xử lý được hỗ trợ. Mapping kết quả thường vẫn là:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Khi IdP dùng claim đặc thù khác, ví dụ `permissions` hoặc `authorities`, cần tùy biến converter. Không tự giả định Spring Security hiểu mọi claim có tên giống quyền.

### 4.3. Nếu JWT đồng thời có scope và scp?

Một số token có thể chứa cả:

```json
{
  "scope": "orders.read",
  "scp": ["orders.write"]
}
```

Không nên kỳ vọng converter mặc định tự động **hợp nhất cả hai**. Với những phiên bản thông dụng, `JwtGrantedAuthoritiesConverter` chọn một well-known claim theo thứ tự nhận diện (`scope` trước `scp`) hoặc claim do ứng dụng cấu hình rõ. Để tránh nhầm:

- Ưu tiên **một định dạng scope đã thống nhất** trong hợp đồng issuer/API.
- Nếu thật sự cần hợp nhất nhiều nguồn, viết một converter có quy tắc rõ ràng và nguồn đáng tin.
- Không coi scope ở hai claim có ý nghĩa cộng quyền mặc định, vì có thể sinh quyền vượt quá mong đợi.

### 4.4. Khi không có scope

Một token có thể hợp lệ về chữ ký/issuer/audience nhưng không mang phạm vi `orders.read`:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "service-42",
  "aud": ["orders-api"],
  "exp": 1893459600
}
```

Đối với endpoint yêu cầu `SCOPE_orders.read`, Authentication không có authority đó phải bị từ chối theo policy. Không mặc định “token hợp lệ thì cấp mọi scope”. Nếu một client credentials flow theo hợp đồng dùng claim role riêng thay vì scope, chính sách cần được thiết kế rõ cho loại principal đó; không tự bỏ bảo vệ endpoint.

## 5. JwtAuthenticationToken và SecurityContextHolder

Khi JWT Resource Server xác thực thành công, Spring Security thường tạo `JwtAuthenticationToken`. Đây là một implementation của `Authentication`; nó mang principal kiểu `Jwt` và collection authorities đã chuyển từ scope/claim.

Ví dụ controller kiểm tra:

```java
import java.util.List;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentAccessController {

    @GetMapping("/api/me/access")
    public List<String> grantedAuthorities(
            Authentication authentication) {
        return authentication.getAuthorities().stream()
            .map(authority -> authority.getAuthority())
            .toList();
    }
}
```

Ví dụ nhằm minh họa phương thức đọc; route này cần được bảo vệ phù hợp và không nên đưa thông tin quyền nhạy cảm ra ngoài nếu không có nhu cầu sản phẩm. Nếu chỉ cần subject của JWT có thể dùng `@AuthenticationPrincipal Jwt`; nếu chỉ cần quyền, `Authentication` phù hợp hơn vì không phụ thuộc trực tiếp định dạng token.

### 5.1. Scope được kiểm tra từ Authentication của request hiện tại

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

boolean mayRead = auth != null &&
    auth.getAuthorities().stream()
        .anyMatch(a -> "SCOPE_orders.read".equals(a.getAuthority()));
```

Đoạn code trên minh họa sự tồn tại của authority. Trong ứng dụng thông thường, **ưu tiên authorization DSL hoặc method security** thay vì lặp lại thủ công việc duyệt collection ở từng controller.

Với API bearer stateless, mỗi request mang token riêng và Spring Security xây dựng Authentication cho phạm vi request đó. Không lưu authority của “người gọi gần nhất” vào field singleton/static rồi dùng cho request kế tiếp.

## 6. Phân biệt scope, authority, role và permission nghiệp vụ

Các khái niệm dễ bị gộp thành “quyền”:

| Khái niệm | Thuộc lớp nào? | Ví dụ | Hạn chế |
|---|---|---|---|
| **OAuth scope** | Hợp đồng Authorization Server ↔ Resource Server | `orders.read` | Không tự mô tả ownership/tenant |
| **GrantedAuthority** | Spring Security `Authentication` | `SCOPE_orders.read` | Chỉ là dữ liệu quyền mà authorization rules diễn giải |
| **Role** | Chính sách tổ chức/ứng dụng, có thể được diễn đạt bằng authority | `ROLE_ADMIN` | Ý nghĩa cụ thể do ứng dụng xác định |
| **Permission** | Quy tắc thao tác hoặc dữ liệu nghiệp vụ | “user được sửa ORD-123” | Có thể cần truy vấn DB và ngữ cảnh |
| **Audience** | Hợp đồng token | `orders-api` | Không phải quyền thao tác |
| **Principal/subject** | Danh tính | `user-842` hoặc `service-42` | Không tự suy ra quyền |

### 6.1. hasAuthority và hasRole khác gì?

Trong cấu hình chuẩn:

```java
.hasAuthority("SCOPE_orders.read")
```

kiểm tra authority string **đúng bằng** `SCOPE_orders.read`.

Trong khi:

```java
.hasRole("ADMIN")
```

thường kiểm tra authority **`ROLE_ADMIN`** vì Spring Security có convention tiền tố `ROLE_` cho role expression. Tiền tố mặc định cho role có thể được tùy biến ở ứng dụng; `hasRole` không phải cách mặc định để kiểm tra OAuth scope.

Các cách kiểm tra tương đương trong cấu hình dùng role prefix mặc định:

```java
.hasRole("ADMIN")
.hasAuthority("ROLE_ADMIN")
```

Nhưng:

```java
.hasRole("orders.read")          // thường tìm ROLE_orders.read
.hasAuthority("SCOPE_orders.read") // tìm scope authority thật
```

Hai dòng cuối **không tương đương**. Để bảo vệ API theo OAuth scope mặc định, dùng `hasAuthority("SCOPE_...")` rõ ràng giúp tránh hiểu nhầm.

### 6.2. Một role có thể chứa nhiều quyền, nhưng không tự có hierarchy

Ví dụ sản phẩm định nghĩa role `ORDER_MANAGER` được đọc/ghi đơn hàng:

```text
ROLE_ORDER_MANAGER
    -> orders.read
    -> orders.write
```

Đây là **chính sách riêng**, không phải quy định của OAuth hoặc mặc định `GrantedAuthority`. Muốn ánh xạ role thành quyền, ứng dụng phải có quy tắc, nguồn dữ liệu tin cậy và kiểm tra tương ứng.

Trong API có cả scope và role, có thể kiểm tra kết hợp:

```java
.access(/* AuthorizationManager biểu diễn chính sách kết hợp */)
```

hoặc dùng method security với biểu thức điều kiện thích hợp. Không tự coi một tên role trong JWT như `admin` là đủ để vượt qua audience, issuer hoặc kiểm tra quyền của tài nguyên.

### 6.3. Permission trên từng bản ghi luôn là quyết định riêng

Token:

```json
{
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
```

Database:

```text
Order ORD-123:
  owner = user-842
  tenant = tenant-a

Order ORD-999:
  owner = user-901
  tenant = tenant-b
```

Authority `SCOPE_orders.read` cho phép request đi qua tầng kiểm tra loại thao tác **đọc đơn hàng**, nhưng service vẫn phải từ chối ORD-999 nếu user/tenant không có quyền. Nếu không có kiểm tra đối tượng, API có nguy cơ bị **Broken Object Level Authorization (BOLA)**.

## 7. Cấu hình Spring Boot/Spring Security Servlet: dùng scope mặc định

Ví dụ REST API nhận JWT bearer, chỉ cho phép đọc/ghi đơn hàng theo scope. Với Spring Boot 3.x, dependencies phổ biến:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
```

`issuer-uri` khai báo issuer đáng tin, còn `audiences` (ở phiên bản Boot hỗ trợ) ràng buộc `aud` phải dành cho API. JWT decoder cần xác minh chữ ký và kiểm tra claims; authority mapping **không thay thế** các validator đó.

Ví dụ cấu hình HTTP:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            // Ví dụ chỉ dành cho API Bearer header, không dùng
            // cookie/session làm credential cho các thao tác ghi.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Giải thích:

1. Spring Security lấy bearer token từ request header theo quy tắc resolver.
2. `JwtDecoder` xác minh token với issuer/khóa và các validator.
3. `JwtAuthenticationConverter` mặc định đọc scope/scp phù hợp.
4. `GrantedAuthority` `SCOPE_orders.read`/`SCOPE_orders.write` được dùng ở các rule `hasAuthority`.
5. `anyRequest().denyAll()` chọn cách **từ chối những route chưa cấu hình rõ**, thay vì mở rộng nhầm quyền. Với ứng dụng lớn có nhiều chain cần tính toán matcher đầy đủ.
6. Quyền theo từng order vẫn được kiểm tra tại service.

Mẫu `csrf().disable()` chỉ áp dụng cho API xác thực bằng bearer header không phụ thuộc cookie. Nếu ứng dụng còn form login/cookie/session, phải đánh giá bảo vệ CSRF theo kênh xác thực thực tế.

### 7.1. hasAnyAuthority cho nhiều scope thay thế

Một endpoint cho phép đọc nếu token có **ít nhất một** trong hai scope:

```java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAnyAuthority("SCOPE_reports.read", "SCOPE_reports.admin")
```

Đây là quan hệ **OR** giữa hai authorities. Nếu hợp đồng yêu cầu **cả hai** scope, không dùng `hasAnyAuthority`. Cần dùng một biểu thức/AuthorizationManager phù hợp với logic AND.

Không nên tự tạo scope wildcard và giả định `SCOPE_orders.*` sẽ khớp mọi scope con; `hasAuthority` không tự diễn giải wildcard nếu không có policy tùy biến.

### 7.2. Dùng method security

Với `@EnableMethodSecurity`:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto readOrder(String orderId) {
        return loadAndCheckBusinessAccess(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public OrderDto updateOrder(String orderId, UpdateOrderCommand command) {
        return updateAfterBusinessChecks(orderId, command);
    }
}
```

Các method `loadAndCheckBusinessAccess`, `updateAfterBusinessChecks` và kiểu DTO/command là các thành phần minh họa do ứng dụng định nghĩa. Việc có `@PreAuthorize` kiểm tra scope ở method không loại bỏ kiểm tra quyền owner/tenant trong chính service.

**Lưu ý proxy:** method security dựa trên cơ chế Spring AOP/proxy trong cấu hình thông thường. Lời gọi một method có annotation từ chính method khác **trong cùng bean** có thể bỏ qua proxy, khiến annotation không được thực thi theo cách tưởng tượng. Đặt ranh giới service/ủy quyền rõ ràng và không chỉ dựa vào self-invocation.

## 8. Opaque access token: scope cũng có thể trở thành GrantedAuthority

Không phải mọi OAuth access token đều là JWT. Một API có thể dùng **introspection**: Resource Server gửi token đến Authorization Server để biết token còn `active` và thông tin quyền đã cấp.

Ví dụ response introspection minh họa:

```json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop",
  "exp": 1893459600
}
```

Ở Servlet Resource Server opaque-token support, Spring Security có thể dùng `OpaqueTokenIntrospector` để lấy metadata và tạo `BearerTokenAuthentication`. Các scope được trả về thường được ánh xạ thành `GrantedAuthority` có tiền tố `SCOPE_`, tương tự JWT.

Cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
```

Token được nhận qua introspection có thể vẫn có authorities:

```text
SCOPE_orders.read
SCOPE_orders.write
```

Do đó cùng một rule:

```java
.hasAuthority("SCOPE_orders.read")
```

có thể được dùng cho JWT hoặc opaque token **nếu hợp đồng mapping authority giữa hai chế độ tương đương**.

### 8.1. Không mặc định opaque token có Jwt principal

Với JWT, principal thường là `Jwt`. Với opaque token, principal thường là `OAuth2AuthenticatedPrincipal`. Một controller/service chỉ cần tên và authorities nên nhận `Authentication`; code ép `Jwt` ở nơi có opaque authentication có thể không hoạt động.

```java
@GetMapping("/api/me/authorities")
public List<String> currentAuthorities(Authentication authentication) {
    return authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .toList();
}
```

Ví dụ cần import `Authentication`, `GrantedAuthority`, `List` và các Spring MVC annotations tương ứng. Nó không phụ thuộc loại principal của token.

### 8.2. Introspection trả active=true không có nghĩa quyền đủ

`active: true` cho biết credential còn hoạt động theo phản hồi IdP, không cho phép API bỏ qua audience, scope, tenant hay policy riêng. Nếu endpoint introspection không trả thông tin cần để kiểm tra audience, phải điều chỉnh hợp đồng với Authorization Server, không coi một token active là dùng được ở mọi Resource Server.

## 9. Tùy biến cách mapping scope thành GrantedAuthority

Khi IdP sử dụng claim hoặc naming khác, Spring Security cung cấp `JwtGrantedAuthoritiesConverter`. Một số lựa chọn phổ biến:

- `setAuthoritiesClaimName(...)`: xác định claim từ đó đọc các authority string/scope.
- `setAuthorityPrefix(...)`: đổi tiền tố, ví dụ `SCOPE_` hoặc rỗng.
- `setAuthoritiesClaimDelimiter(...)`: định nghĩa cách tách giá trị dạng chuỗi trong các phiên bản hỗ trợ.

Tùy biến có thể là cần thiết, nhưng **phải giữ ranh giới token đã xác thực** và không tự cấp quyền cao hơn hợp đồng.

### 9.1. Tùy biến claim scp và giữ tiền tố SCOPE_

Giả sử IdP luôn phát hành:

```json
{
  "scp": ["orders.read", "orders.write"]
}
```

Có thể cấu hình converter tường minh:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class TokenAuthorityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        scopes.setAuthoritiesClaimName("scp");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(scopes);
        return converter;
    }
}
```

Với custom converter, cần gắn nó vào JWT Resource Server DSL:

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(jwt ->
                jwt.jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
```

Đoạn code trên minh họa **kết nối converter vào chain**. Các điều kiện JWT issuer/audience/signature vẫn phải được cấu hình ở decoder. Chỉ tạo `@Bean JwtAuthenticationConverter` mà không dùng nó trong authentication pipeline có thể khiến mapping tùy biến không được áp dụng theo cách mong đợi.

### 9.2. Đổi tiền tố: tác động đến hasAuthority

Giả sử:

```java
scopes.setAuthorityPrefix("");
```

Authority được tạo là `orders.read`, không phải `SCOPE_orders.read`. Policy khi đó phải dùng:

```java
.hasAuthority("orders.read")
```

Nếu giữ `hasAuthority("SCOPE_orders.read")`, request với token có `orders.read` có thể bị 403 do authorities không trùng. Cần thống nhất **cả converter và authorization rules** khi đổi prefix.

Thông thường nên giữ `SCOPE_` để phân biệt scope với role và các authorities từ nguồn khác. Chỉ thay prefix nếu có hợp đồng tương thích rõ và các route/method tests tương ứng.

### 9.3. Chuyển principal name không đồng nghĩa chuyển authorities

`JwtAuthenticationConverter` có thể đặt principal claim:

```java
converter.setPrincipalClaimName("preferred_username");
```

Việc đó ảnh hưởng `Authentication.getName()`, **không tự thay đổi collection authorities**. Nếu muốn ánh xạ `scope`/`scp` phải cấu hình `JwtGrantedAuthoritiesConverter`. Nếu muốn quyền từ claim khác phải có converter phù hợp; đừng nhầm claim danh tính như `email`, `preferred_username` với quyền hành động.

Trong hệ thống nhiều issuer, `preferred_username` không phải định danh ổn định toàn cục. Để xác định chủ thể và ownership, thường phải dùng `iss + sub` hoặc ánh xạ principal nội bộ.

## 10. Gộp scope và một nhóm authorities khác

Một số IdP phát hành cả:

```json
{
  "scope": "orders.read",
  "app_roles": ["ORDER_MANAGER"]
}
```

Mặc định `JwtGrantedAuthoritiesConverter` chỉ xử lý well-known scope claims, **không tự biến mọi phần tử `app_roles` thành `ROLE_...`**. Nếu ứng dụng được phép tin claim `app_roles` từ issuer này, có thể bổ sung một converter kết hợp.

### 10.1. Mẫu converter giữ scope trước khi thêm role

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class ScopeAndRoleAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<GrantedAuthority> result = new ArrayList<>();

        // Giữ các scope authorities mặc định: SCOPE_...
        result.addAll(scopes.convert(jwt));

        // Chỉ dùng claim này nếu issuer và hợp đồng token
        // cho phép Resource Server tin app_roles như role nguồn.
        List<String> roles = jwt.getClaimAsStringList("app_roles");
        if (roles != null) {
            for (String role : roles) {
                if (role.equals("ORDER_MANAGER")) {
                    result.add(
                        new SimpleGrantedAuthority("ROLE_ORDER_MANAGER"));
                }
            }
        }
        return result;
    }
}
```

Sau đó gắn vào `JwtAuthenticationConverter`:

```java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(
    new ScopeAndRoleAuthoritiesConverter());
```

Ý tưởng quan trọng của ví dụ:

1. **Giữ scope mặc định** thay vì thay tất cả authorities chỉ bằng role.
2. Chỉ ánh xạ role **cụ thể đã được chấp nhận theo hợp đồng**.
3. Không lấy mọi chuỗi trong claim `app_roles` rồi vô điều kiện thêm `ROLE_`, đặc biệt khi IdP dùng chung cho nhiều client hoặc claim không được issuer đảm bảo.
4. Không dùng role để bỏ qua `aud`, `iss`, thời gian JWT hoặc ownership/tenant.

Nếu ứng dụng có nhiều issuer, nguồn và ý nghĩa `app_roles` có thể khác. Không tin một role chỉ dựa trên tên claim trong JWT của issuer khác, dù issuer đó được chấp nhận cho một tập endpoint nào đó.

### 10.2. Khi nào không nên đưa role vào JWT?

Một số quyền thay đổi thường xuyên hoặc phụ thuộc dữ liệu hiện tại, ví dụ nhân viên được chuyển nhóm, đơn hàng đổi chủ hoặc dự án bị khóa. JWT self-contained có thể giữ claim cũ cho đến khi hết hạn. Nếu quyết định cần phản ánh thay đổi ngay, nên:

- Kiểm tra quyền hiện tại ở database/policy service.
- Dùng introspection hoặc trạng thái thu hồi theo hợp đồng.
- Giới hạn TTL của access token phù hợp.
- Chỉ lưu trong token những quyền tương đối ổn định và có phạm vi rõ.

Không nên dùng claim role trong JWT như bản sao vĩnh viễn của hệ thống phân quyền nghiệp vụ.

## 11. Quy tắc phân quyền nhiều tầng

Một hệ thống Orders API có thể có:

```text
Layer 1 — Token validation:
  iss, signature, aud, exp, nbf

Layer 2 — Endpoint authorization:
  GET /api/orders/{id} cần SCOPE_orders.read

Layer 3 — Domain authorization:
  actor được xem đúng order id?
  tenant trùng?
  order có trạng thái hạn chế?
```

Ví dụ actor được xây từ JWT đã xác minh:

```java
public record CurrentActor(
    String issuer,
    String subject,
    String tenantId
) {}
```

Controller:

```java
@GetMapping("/api/orders/{orderId}")
public OrderDto getOrder(
        @PathVariable String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    CurrentActor actor = new CurrentActor(
        jwt.getIssuer().toString(),
        jwt.getSubject(),
        jwt.getClaimAsString("tenant_id")
    );

    return orderService.findReadableOrder(actor, orderId);
}
```

Service:

```java
public OrderDto findReadableOrder(CurrentActor actor, String orderId) {
    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    boolean isOwner =
        order.getOwnerIssuer().equals(actor.issuer()) &&
        order.getOwnerSubject().equals(actor.subject());

    boolean sameTenant =
        order.getTenantId().equals(actor.tenantId());

    if (!isOwner || !sameTenant) {
        throw new AccessDeniedException("Order access denied");
    }
    return mapper.toDto(order);
}
```

Các kiểu `Order`, `OrderDto`, `OrderNotFoundException`, `repository`, `mapper` và `orderService` là phần domain do ứng dụng tự triển khai. Ví dụ giả định chính sách một user chỉ đọc đơn hàng mình sở hữu trong tenant tương ứng; với admin, delegated access hoặc các trường hợp khác cần chính sách bổ sung rõ ràng.

**Chú ý:** Ở controller, `@AuthenticationPrincipal Jwt` chỉ phù hợp cho route JWT; với opaque token, lấy `Authentication`/`OAuth2AuthenticatedPrincipal` và chuyển sang actor tương đương.

### 11.1. Có nên yêu cầu cả authority và ownership?

Có. Chúng giải quyết hai mức khác nhau:

```text
SCOPE_orders.read
    -> Được phép sử dụng tính năng đọc đơn hàng trong phạm vi API

owner/tenant policy
    -> Được phép đọc đơn hàng nào trong phạm vi đó
```

Nếu chỉ có ownership mà bỏ scope, client vốn không được cấp quyền đọc đơn hàng vẫn có thể dùng một token có scope không liên quan. Nếu chỉ có scope mà bỏ ownership, người dùng có thể đọc dữ liệu không thuộc mình.

## 12. OIDC scopes không đồng nghĩa scope quyền API

Một authorization request OIDC có thể xin:

```text
openid profile email
```

Các scope trên phục vụ những ngữ nghĩa của **OpenID Connect** như việc yêu cầu xác thực OpenID và truy cập claims người dùng theo giao thức OIDC. Không nên suy ra:

```text
openid => được gọi mọi protected API
profile => được xem profile của mọi user
email => được đọc email của mọi khách hàng
```

Một Resource Server phục vụ Orders API nên yêu cầu scope riêng như `orders.read` theo hợp đồng API. Những token mang `openid profile email` nhưng không có `orders.read` không được tự động đi qua endpoint cần đọc đơn hàng.

**ID token không phải access token.** OIDC ID token có audience là OIDC client, dùng cho client hiểu kết quả xác thực; nó không trở thành access token hợp lệ của Orders API chỉ vì có chữ ký đúng và chứa claims danh tính.

### 12.1. Resource indicator và audience còn quan trọng

Khi có nhiều API, OAuth có thể dùng resource indicators (theo hợp đồng/IdP) để xin token dành cho từng tài nguyên. Ví dụ:

```text
Client xin orders.read cho orders-api
  -> access token aud=orders-api, scope=orders.read

Client xin payments.refund cho payments-api
  -> access token aud=payments-api, scope=payments.refund
```

Nếu Orders API gọi Payments API phía sau, việc có `SCOPE_orders.read` trong SecurityContext của Orders API **không tự cấp quyền cho Payments API**. API đích phải xác thực credential riêng có audience và scope phù hợp; có thể dùng token exchange/on-behalf-of hoặc client credentials tùy mô hình.

## 13. HTTP 401, 403 và insufficient_scope

Có hai nhóm lỗi người học thường nhầm:

### 13.1. Token thiếu hoặc không hợp lệ: 401

Ví dụ request thiếu token:

```http
GET /api/orders/ord-123 HTTP/1.1
Host: orders.example.com
```

Hoặc gửi token hết hạn/sai chữ ký/sai issuer/sai audience. Với endpoint được bảo vệ, Resource Server thường trả **401 Unauthorized** cùng `WWW-Authenticate: Bearer` theo cơ chế phù hợp.

Ở đây hệ thống **chưa có một access-token authentication hợp lệ**. Không giải quyết bằng cách thêm một authority giả vào controller.

### 13.2. Token hợp lệ nhưng scope thiếu: 403

Giả sử token hợp lệ:

```json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "user-842",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "scope": "orders.read"
}
```

Request:

```http
POST /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer VALID_TOKEN_WITH_ORDERS_READ_ONLY
```

Policy yêu cầu `SCOPE_orders.write`, nhưng Authentication chỉ có `SCOPE_orders.read`. Resource Server đã xác thực token, rồi authorization từ chối → thường **403 Forbidden**.

Theo RFC 6750, khi thiếu scope phù hợp, Bearer challenge có thể mang `error="insufficient_scope"` và thông tin scope cần thiết theo cách framework/API cấu hình. Không giả định mọi phản hồi 403 đều có cùng header hoặc body; nội dung chính xác còn phụ thuộc entry point, access denied handler và cấu hình.

### 13.3. Token hợp lệ có scope đủ nhưng business policy từ chối

```text
Authentication:
  sub=user-842
  authority=SCOPE_orders.read

Request:
  GET /api/orders/ord-999

Database:
  ord-999.owner=user-901
```

Tầng HTTP authority có thể cho qua, nhưng service phải từ chối theo chính sách owner/tenant. Ứng dụng có thể trả 403 hoặc 404 theo chính sách không tiết lộ sự tồn tại bản ghi. Đây **không phải lỗi thiếu OAuth scope** nếu `orders.read` đã được cấp.

### 13.4. Chuẩn hóa thông điệp lỗi an toàn

Tránh trả:

```text
Token eyJ... của user-842 không có ROLE_ADMIN và
resource ORD-999 thuộc user-901...
```

Phản hồi không cần lộ token hoặc danh tính của người sở hữu bản ghi. Có thể log metadata đã được lọc theo chính sách quan sát, nhưng tuyệt đối không log raw bearer credential.

## 14. Các trường hợp scope thường gây lỗi

| Tình huống | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Token có `orders.read` nhưng endpoint yêu cầu `SCOPE_orders.read` | Đúng với mapping mặc định; nếu vẫn bị 403 phải xem token/chain/converter | Quan sát authorities sau xác thực một cách an toàn |
| IdP gửi `scp` mà converter bị ép đọc `scope` | Không tìm thấy claim mong đợi | Thống nhất claim hoặc cấu hình `setAuthoritiesClaimName("scp")` |
| Token có cả `scope` và `scp` nhưng chỉ một nhóm quyền được đọc | Converter mặc định không nhất thiết hợp nhất cả hai | Hợp đồng dùng một nguồn; nếu gộp thì viết quy tắc rõ |
| IdP gửi scope đã có `SCOPE_` | Converter có thể thêm tiền tố lần nữa | Phát hành scope raw hoặc chỉnh mapping đúng hợp đồng |
| Dùng `hasRole("orders.read")` | Tìm `ROLE_orders.read` thay vì scope authority | Dùng `hasAuthority("SCOPE_orders.read")` |
| Dùng `hasAuthority("orders.read")` với converter mặc định | Không trùng `SCOPE_orders.read` | Dùng đúng prefix hoặc chỉnh converter và policy đồng bộ |
| Dùng role claim mà không cấu hình converter | Role không tự thành `ROLE_...` | Mapping explicit từ nguồn tin cậy |
| Token có `orders.write`, endpoint đòi `orders.read` | Không có kế thừa scope mặc định | Cấp cả scope hoặc định nghĩa policy tương ứng |
| Token có scope đúng nhưng `aud` dành cho API khác | Token không dành cho Resource Server hiện tại | Kiểm tra audience, không bỏ qua |
| Token có scope đúng nhưng đã hết hạn | Authentication phải từ chối trước authorization | Kiểm tra `exp`/`nbf` và signature |
| Client từng yêu cầu `orders.write` nhưng token chỉ cấp `orders.read` | AS giới hạn scope | Dựa vào token đã cấp, không dựa vào request xin scope |
| Một user đổi role nhưng JWT cũ vẫn có claim quyền | Token self-contained còn hạn | Chính sách TTL/thu hồi/introspection/quyền nghiệp vụ hiện tại |
| Có JWT role ADMIN là cho qua mọi tenant | Trộn role chức năng với quyền đối tượng | Kiểm tra tenant/owner hoặc rule admin riêng rõ ràng |
| Dùng JWT test mock để kết luận decoder xác minh đúng | Mock có thể bypass decode/validator | Tách test authorization và integration JWT thật |

## 15. Test scope mapping và authorization đúng lớp

Các kiểm thử nên tách ba mục tiêu:

1. **Token validation:** JWT có được xác minh chữ ký/issuer/audience/thời gian đúng không?
2. **Authority mapping:** claims được chuyển thành authorities gì?
3. **Authorization policy:** authorities và actor có đủ quyền trên endpoint/bản ghi không?

### 15.1. Unit test JwtGrantedAuthoritiesConverter

Ví dụ dùng JUnit 5 và AssertJ với token giả lập (không có chữ ký thật):

```java
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.assertj.core.api.Assertions.assertThat;

class JwtScopeMappingTest {

    @Test
    void convertsSpaceSeparatedScopeToAuthorities() {
        Instant now = Instant.now();
        Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "RS256")
            .subject("user-842")
            .issuedAt(now.minusSeconds(60))
            .expiresAt(now.plusSeconds(300))
            .claim("scope", "orders.read orders.write")
            .build();

        JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

        assertThat(converter.convert(jwt))
            .extracting(authority -> authority.getAuthority())
            .containsExactlyInAnyOrder(
                "SCOPE_orders.read",
                "SCOPE_orders.write");
    }
}
```

Test này kiểm tra **mapping từ một đối tượng `Jwt` sang authorities**, không kiểm tra chữ ký JWT thực, bearer filter hay audience validator. Nó hữu ích để phát hiện mismatch prefix/claim name khi thay converter.

### 15.2. Unit test cho converter scp

```java
@Test
void readsScpArrayWhenConfigured() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .claim("scp", List.of("orders.read", "orders.write"))
        .build();

    JwtGrantedAuthoritiesConverter converter =
        new JwtGrantedAuthoritiesConverter();
    converter.setAuthoritiesClaimName("scp");

    assertThat(converter.convert(jwt))
        .extracting(GrantedAuthority::getAuthority)
        .contains("SCOPE_orders.read", "SCOPE_orders.write");
}
```

Đoạn code là một test method bổ sung trong test class có imports JUnit/AssertJ, `Jwt`, `List` và `GrantedAuthority`. Khi sử dụng builder `Jwt` của phiên bản khác, có thể cần cung cấp các claim/time bắt buộc theo API cụ thể của bản đó.

### 15.3. Kiểm thử HTTP authorization

Spring Security Test hỗ trợ `MockMvc` và request post processor `jwt()` để giả lập JWT principal/authorities:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void readOrderRequiresScope() throws Exception {
    mockMvc.perform(get("/api/orders/ord-123")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk());
}
```

`mockMvc`, controller, service và dữ liệu test phải được dựng theo ứng dụng thật; ví dụ giả định route trả 200 khi điều kiện nghiệp vụ cũng hợp lệ. Cách `jwt().authorities(...)` **gán authorities giả lập**, nên không chứng minh JWT decoder đã kiểm chứng chữ ký hoặc converter mặc định đọc claim `scope` đúng.

Muốn kiểm tra decoder và pipeline xác thực thực tế, cần test request mang bearer JWT được ký bằng khóa test tin cậy, cấu hình decoder/JWKS test, rồi gửi token đúng/sai issuer, audience, expiration và scope qua filter chain.

### 15.4. Tình huống âm quan trọng

| Token/Request | Điều cần xác minh |
|---|---|
| JWT chữ ký sai nhưng có scope đúng | Authentication bị từ chối |
| JWT đúng chữ ký nhưng sai issuer | Authentication bị từ chối |
| JWT đúng issuer nhưng sai audience | Authentication bị từ chối |
| JWT hết hạn nhưng có `orders.write` | Authentication bị từ chối |
| JWT hợp lệ, chỉ có `orders.read`, request POST cần write | Authorization bị từ chối |
| JWT hợp lệ, có `orders.write`, request POST đúng quyền | Đi tiếp tới business policy |
| JWT hợp lệ, có scope nhưng order khác owner/tenant | Business policy từ chối |
| JWT có `scp` array, converter dùng claim không đúng | Không có scope authority mong đợi |
| JWT dùng custom prefix nhưng route vẫn kiểm tra `SCOPE_` | Policy không trùng authority |
| Opaque token active nhưng không có scope required | Authorization từ chối |

Không chỉ kiểm tra happy path với scope đầy đủ; các tình huống từ chối giúp phát hiện việc làm rơi scope mapping hoặc trộn authentication/authorization.

## 16. Scope trong kiến trúc nhiều API và nguyên tắc quyền tối thiểu

Giả sử hệ thống có Orders API, Payments API và Reporting API:

```text
Orders API:
  audience = orders-api
  scopes   = orders.read, orders.write

Payments API:
  audience = payments-api
  scopes   = payments.read, payments.refund

Reporting API:
  audience = reporting-api
  scopes   = reports.read
```

Nên yêu cầu và cấp **phạm vi tối thiểu cho mục đích đang thực hiện**. Một client chỉ cần đọc đơn hàng không nên xin `orders.write` hoặc `payments.refund`. Một backend service dùng client credentials chỉ nên được cấp scopes và audiences cần cho chức năng đó.

### 16.1. Không chuyển tiếp token sai audience

```mermaid
flowchart LR
    C["Client"] -->|"Token aud=orders-api<br/>scope=orders.read"| O["Orders API"]
    O -->|"Cần gọi Payments API"| T["Token exchange<br/>hoặc client credentials"]
    T -->|"Token aud=payments-api<br/>scope phù hợp"| P["Payments API"]
```

Orders API không có quyền biến token `aud=orders-api` thành token `aud=payments-api` chỉ bằng cách đổi JSON. Nếu Payments API kiểm tra audience đúng, token của Orders API sẽ bị từ chối. Hợp đồng liên dịch vụ có thể yêu cầu token exchange/on-behalf-of hoặc client credentials.

### 16.2. Scope không phải idempotency hay chống replay

Token có `payments.refund` không tự chống việc request refund bị gửi nhiều lần. Cần cơ chế idempotency và kiểm tra trạng thái giao dịch phù hợp. JWT có `jti` cũng không tự đảm bảo “chỉ được gọi một request”, vì bearer access token thường được dùng nhiều lần trong thời gian hiệu lực.

### 16.3. Scope không tự cập nhật khi quyền thay đổi

Với JWT self-contained, scope nằm trong token đã ký và có thể được Resource Server dùng cho đến khi token hết hạn hoặc bị từ chối theo cơ chế trạng thái khác. Việc sửa quyền người dùng ở IdP không tự thay đổi JWT đã cấp. Nếu cần tác động sớm:

- Dùng access token sống ngắn.
- Áp business policy hiện tại trên từng resource.
- Dùng token introspection hoặc revocation/denylist nếu hợp đồng yêu cầu.
- Quản lý tác động của việc đổi client grants hoặc role mapping.

Không coi scope có trong token là quyền vĩnh viễn của principal.

## 17. Câu hỏi thiết kế hợp đồng scope ↔ authority

Trước khi viết rule `hasAuthority`, nhóm API và IdP nên thống nhất:

| Câu hỏi | Ví dụ quyết định |
|---|---|
| Scope là những chuỗi nào? | `orders.read`, `orders.write` |
| Quy ước tên có phân biệt chữ hoa/thường không? | Có; so khớp chính xác |
| Client nào có quyền xin scope? | `shop-web` xin read/write theo policy; batch chỉ read |
| Token dành cho API nào? | `aud` phải chứa `orders-api` |
| JWT dùng claim nào? | `scope` dạng chuỗi cách nhau bởi space |
| Opaque introspection trả quyền ở đâu? | `scope` trong response theo RFC 7662/hợp đồng |
| Spring Security mapping thế nào? | `orders.read` → `SCOPE_orders.read` |
| Có role riêng không? | `ROLE_ORDER_MANAGER` từ nguồn role được kiểm soát |
| Rule nào bắt buộc một scope? | GET cần read; POST/PUT/DELETE cần write |
| Có quan hệ giữa scopes? | Không tự kế thừa; nếu có phải định nghĩa |
| Ai kiểm tra owner/tenant? | Service/domain policy |
| Quyền bị thay đổi có hiệu lực khi nào? | TTL JWT, introspection hoặc quyền hiện tại |
| Ai kiểm tra issuer, ký số, thời hạn? | Resource Server JWT decoder / introspector |

Điều quan trọng là **một nguồn thống nhất cho semantics**: Authorization Server biết scope nào được cấp, Resource Server biết mỗi scope cho phép loại thao tác nào, và Spring Security được cấu hình khớp với tên authority đã ánh xạ.

### 17.1. Dấu hiệu policy sai ranh giới

Nếu một trong các nhận định sau xuất hiện trong thiết kế, cần xem lại:

- “Bearer token được xác thực nên endpoint không cần `hasAuthority`.”
- “Có `openid` hoặc `profile` là được gọi mọi API.”
- “Tên role trong token luôn được Spring Security tự đổi thành `ROLE_...`.”
- “Frontend gửi header `X-Scope: orders.write` là đủ để backend cho ghi.”
- “`orders.write` tự bao gồm `orders.read` vì tên scope có vẻ mạnh hơn.”
- “Đã kiểm tra scope thì không cần kiểm tra owner/tenant nữa.”
- “Một token có `scope=orders.read` dùng được cho bất kỳ API nào cùng IdP.”
- “Một JWT đã cấp sẽ tự đổi scope khi role trong database thay đổi.”

Tất cả đều có thể gây lỗi authorization hoặc mở rộng quyền ngoài chủ đích.

## 18. Tóm lược cách ghi nhớ

```text
OAuth 2.0
  Client yêu cầu scope
         |
         v
  Authorization Server đánh giá và cấp scope
         |
         v
  Access token chứa/tham chiếu scope được cấp
         |
         v
Spring Security Resource Server
  Xác minh JWT hoặc introspect token
         |
         v
  Converter biến scope -> GrantedAuthority
  orders.read -> SCOPE_orders.read
         |
         v
  HTTP/method authorization
  hasAuthority("SCOPE_orders.read")
         |
         v
  Business authorization
  owner / tenant / trạng thái / ACL của bản ghi
```

**Scope là thuật ngữ và dữ liệu quyền của OAuth; `GrantedAuthority` là cách Spring Security biểu diễn quyền trong `Authentication`.** Mapping mặc định cho JWT/opaque Resource Server thường dùng tiền tố `SCOPE_`, để các rule như `hasAuthority("SCOPE_orders.read")` kiểm tra quyền loại thao tác.

Hai lời nhắc cuối:

1. **Scope không thay thế việc xác minh access token**: vẫn phải kiểm tra issuer, audience, chữ ký/thời hạn hoặc introspection.
2. **Authority không thay thế quyền nghiệp vụ**: vẫn phải kiểm tra người gọi có quyền đối với tài nguyên cụ thể đang được yêu cầu.

Khi giữ đúng hai ranh giới này và thống nhất mapping claim → authority → policy, Resource Server có thể sử dụng scope một cách rõ ràng, kiểm thử được và hạn chế cấp quyền quá rộng.

## Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework, Section 3.3 Scope](https://www.rfc-editor.org/rfc/rfc6749#section-3.3): ý nghĩa, biểu diễn và việc cấp OAuth scopes.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer credentials, 401/403 và `insufficient_scope`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active`, `scope` và metadata của token.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): xác định resource/audience khi yêu cầu token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token và claim `scope`.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scopes OIDC và phân biệt ID token với access token.
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, `scope` → `SCOPE_` và authentication converter.
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và ánh xạ scope authorities.
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasAuthority`, `hasRole` và chính sách HTTP.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize` và phân quyền tại method.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): tùy biến claim và tiền tố authority.
