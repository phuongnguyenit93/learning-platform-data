# Resource Owner, Client, Authorization Server và Resource Server

> **Chương:** Giao thức và thuật ngữ  
> **Phạm vi:** OAuth 2.0/OpenID Connect (OIDC) Authorization Server với Spring Security, Spring Authorization Server và Spring Boot.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt chính xác bốn **vai trò logic** được định nghĩa trong OAuth 2.0: Resource Owner, Client, Authorization Server và Resource Server.
2. Giải thích ai xác thực người dùng, ai cấp token, ai sử dụng token và ai thực thi quyền truy cập tài nguyên.
3. Mô tả một luồng Authorization Code kết hợp PKCE; phân biệt access token, ID token và refresh token.
4. Ánh xạ từng vai trò sang các thành phần Spring Security/Spring Authorization Server; nhận diện các lỗi thiết kế thường gặp.
5. Xác định các ranh giới tin cậy và điểm cần kiểm thử khi triển khai ứng dụng thật.

## 1. Tại sao phải tách bốn vai trò?

Giả sử một hệ thống đặt phòng có ứng dụng web, dịch vụ quản lý đặt phòng và một hệ thống đăng nhập tập trung. Người dùng muốn xem các đặt phòng của mình mà không cung cấp mật khẩu cho từng API. OAuth 2.0 tách **quyền kiểm soát tài nguyên**, **ứng dụng đang yêu cầu quyền**, **dịch vụ cấp quyền** và **dịch vụ giữ tài nguyên** thành bốn vai trò.

**OAuth 2.0 chủ yếu là một khung ủy quyền truy cập (authorization framework)**: một client được cấp quyền truy cập có giới hạn vào tài nguyên được bảo vệ. OIDC xây thêm một lớp **xác thực danh tính (authentication)** trên OAuth 2.0 để client có thể xác minh người dùng đã đăng nhập.

Bốn vai trò là những **trách nhiệm trong giao thức**, không bắt buộc là bốn máy chủ, bốn microservice hoặc bốn codebase. Một ứng dụng có thể đóng nhiều vai trò về mặt triển khai, nhưng vẫn phải phân biệt trách nhiệm và kiểm tra bảo mật của từng vai trò.

| Vai trò | Câu hỏi vai trò này trả lời | Trách nhiệm cốt lõi | Ví dụ |
| --- | --- | --- | --- |
| **Resource Owner** (chủ sở hữu tài nguyên) | Ai có quyền cho phép truy cập tài nguyên? | Kiểm soát hoặc có thẩm quyền cho phép truy cập tài nguyên được bảo vệ | Người dùng sở hữu dữ liệu đặt phòng |
| **Client** (ứng dụng khách) | Ứng dụng nào đang xin và sử dụng quyền truy cập? | Khởi tạo yêu cầu cấp quyền, nhận token và gọi API thay mặt người dùng hoặc cho chính ứng dụng | Web đặt phòng, ứng dụng di động, backend tích hợp |
| **Authorization Server (AS)** (máy chủ cấp quyền) | Ai xác thực và cấp token? | Xác thực theo chính sách, xử lý yêu cầu ủy quyền, đăng ký client, cấp và quản lý token | Dịch vụ đăng nhập dùng Spring Authorization Server |
| **Resource Server (RS)** (máy chủ tài nguyên) | API nào bảo vệ dữ liệu? | Nhận access token, xác minh token và kiểm tra quyền trước khi trả dữ liệu | Booking API dùng Spring Security Resource Server |

### 1.1. Resource Owner: người có thẩm quyền đối với tài nguyên

Resource Owner thường là **người dùng cuối** trong các kịch bản đăng nhập tương tác. Ví dụ, Lan có quyền xem dữ liệu đặt phòng của Lan và có thể cho phép ứng dụng web sử dụng phạm vi quyền `booking.read`. Resource Owner có thể là một thực thể khác tùy mô hình nghiệp vụ; định nghĩa giao thức không bắt buộc mọi tài nguyên đều gắn với một cá nhân.

Điểm cần nhớ:

- **Resource Owner không phải Client.** Lan sử dụng ứng dụng web, nhưng ứng dụng web là Client; Lan là người có quyền đối với dữ liệu.
- **Resource Owner không phải Authorization Server.** Trang đăng nhập có thể do AS hiển thị, nhưng chính sách xác thực và chấp thuận quyền do AS thực thi thay mặt hệ thống.
- **Đăng nhập không tự động có nghĩa là đồng ý với mọi quyền.** AS có thể yêu cầu consent theo phạm vi hoặc có chính sách cho phép bỏ qua màn hình consent trong những trường hợp phù hợp.
- **Danh tính và quyền trên đối tượng cụ thể khác nhau.** Biết `sub` của người dùng không đủ để kết luận người đó được xem mọi đơn đặt phòng. RS vẫn phải kiểm tra chủ sở hữu, tenant và quy tắc nghiệp vụ.

### 1.2. Client: ứng dụng yêu cầu quyền

Client là ứng dụng tương tác với AS để nhận quyền truy cập và sử dụng access token khi gọi RS. Trong OAuth, chữ “client” **không đồng nghĩa với trình duyệt**: một backend Spring Boot cũng có thể là client.

Hai kiểu client phổ biến:

| Kiểu client | Đặc điểm | Hệ quả thiết kế |
| --- | --- | --- |
| **Confidential client** | Có khả năng giữ an toàn thông tin xác thực client ở phía máy chủ | Ví dụ backend/BFF; có thể xác thực bằng client secret hoặc cơ chế phù hợp khác |
| **Public client** | Không thể giữ bí mật lâu dài, chẳng hạn SPA thuần hoặc ứng dụng di động phân phối cho người dùng | Không nhúng client secret như một bí mật; dùng Authorization Code + PKCE và các biện pháp phù hợp với nền tảng |

Mỗi client được AS nhận diện bằng `client_id` và đăng ký các thông số như redirect URI, phương thức xác thực client, grant type và scope được phép yêu cầu. **`client_id` là định danh, không phải mật khẩu.**

Một client có thể đóng vai trò **Relying Party (RP)** khi dùng OIDC để đăng nhập. Cũng có thể một dịch vụ vừa là RS khi nhận API call, vừa là Client khi nó tiếp tục gọi một API khác; hai hành vi phải được cấu hình theo đúng trách nhiệm.

### 1.3. Authorization Server: bên cấp quyền và token

AS xử lý phần **cấp phép ở mức giao thức**:

1. Nhận yêu cầu ủy quyền của client và kiểm tra client, redirect URI, grant type, scope.
2. Xác thực Resource Owner khi luồng yêu cầu người dùng tương tác; lấy hoặc áp dụng quyết định chấp thuận quyền theo chính sách.
3. Phát hành authorization code và/hoặc token theo grant type hợp lệ.
4. Quản lý trạng thái ủy quyền, vòng đời token và chính sách liên quan như hạn dùng, thu hồi, khóa ký, consent.
5. Với OIDC, đóng vai trò **OpenID Provider (OP)** và phát hành ID token khi đáp ứng yêu cầu giao thức.

**AS không nhất thiết lưu trữ dữ liệu nghiệp vụ**. Nó có thể biết ai là người dùng và client được cấp những scope nào nhưng không cần sở hữu bảng đặt phòng. Khả năng cấp access token không thay thế việc RS kiểm tra quyền trên từng bản ghi.

Trong hệ Spring, **Spring Authorization Server** cung cấp các endpoint và cơ chế xây dựng AS, còn ứng dụng triển khai chịu trách nhiệm cấu hình user authentication, client registration, khóa, lưu trữ, chính sách và vận hành.

### 1.4. Resource Server: API bảo vệ tài nguyên

RS là máy chủ nhận yêu cầu đến tài nguyên được bảo vệ, ví dụ `GET /api/bookings/123`. Nó có nhiệm vụ:

- Chỉ chấp nhận access token theo cơ chế mà hệ thống đã cấu hình.
- Kiểm tra tính hợp lệ của token: chữ ký hoặc introspection, thời hạn, issuer, audience và các ràng buộc liên quan.
- Kiểm tra scope/authority và quyền nghiệp vụ đối với dữ liệu được yêu cầu.
- Trả `401 Unauthorized` khi thiếu hoặc không có thông tin xác thực hợp lệ; trả `403 Forbidden` khi đã xác thực nhưng không đủ quyền trong tình huống phù hợp.

RS **không cấp access token** chỉ vì nó có endpoint API. Đối với JWT, RS có thể tự xác minh chữ ký bằng khóa công khai từ AS và cache khóa; không cần gọi AS cho từng request. Đối với opaque token, RS thường phải gọi endpoint **token introspection** theo cấu hình để biết token có hiệu lực và có thông tin gì.

## 2. Hình dung ranh giới giữa các vai trò

~~~mermaid
flowchart LR
    U["Resource Owner<br/>Người dùng Lan"]
    C["Client<br/>Booking Web / BFF"]
    AS["Authorization Server<br/>Đăng nhập và cấp token"]
    RS["Resource Server<br/>Booking API"]

    U -->|"Sử dụng ứng dụng"| C
    U <-->|"Đăng nhập / consent<br/>qua trình duyệt"| AS
    C <-->|"Yêu cầu ủy quyền<br/>đổi code lấy token"| AS
    C -->|"Access token + API request"| RS
    RS -->|"Dữ liệu được phép trả về"| C
    RS -.->|"Lấy khóa công khai / introspection<br/>khi cần"| AS
~~~

Trong một triển khai BFF, trình duyệt thường giữ session với backend; backend đóng vai trò Client, lưu token ở phía server và gửi access token tới RS. Với client public, vị trí lưu token và cơ chế bảo vệ khác đi, nhưng trách nhiệm giao thức vẫn tương tự.

Bảng dưới đây giúp không nhầm “ai nói chuyện với ai”:

| Tương tác | Ý nghĩa |
| --- | --- |
| Resource Owner ↔ AS | Đăng nhập và quyết định chấp thuận quyền khi luồng cần tương tác |
| Client ↔ AS | Yêu cầu cấp quyền, đổi authorization code lấy token, refresh token nếu được hỗ trợ |
| Client → RS | Gọi API với **access token** |
| RS ↔ AS | Truy xuất khóa công khai, metadata hoặc introspection theo kiểu token; không phải lúc nào cũng có cuộc gọi ở mỗi request |
| Resource Owner ↔ Client | Người dùng thao tác trên ứng dụng; đó là hành vi sản phẩm, không phải bằng chứng RS đã ủy quyền |

## 3. Ví dụ xuyên suốt: xem đặt phòng bằng Authorization Code + PKCE

Giả định hệ thống có các thành phần:

- **Resource Owner:** Lan, người muốn xem dữ liệu của mình.
- **Client:** `booking-web`, một Spring Boot BFF được đăng ký với AS.
- **AS:** `https://auth.example.test`.
- **RS:** `https://api.example.test`, cung cấp Booking API.
- **Scope:** `booking.read`, mô tả phạm vi API mà client yêu cầu.
- **OIDC scope:** `openid` nếu ứng dụng đồng thời cần đăng nhập bằng OIDC.

> Tên miền `.example.test` và tên ứng dụng bên dưới chỉ dùng minh họa, không phải endpoint đang hoạt động.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Resource Owner (Lan)
    participant C as Client (Booking Web/BFF)
    participant AS as Authorization Server
    participant RS as Resource Server (Booking API)

    U->>C: Mở trang đặt phòng của tôi
    C-->>U: Chuyển hướng tới AS kèm state, PKCE challenge, scope
    U->>AS: Mở yêu cầu /oauth2/authorize
    AS->>U: Đăng nhập và xin consent nếu chính sách yêu cầu
    U->>AS: Xác thực / chấp thuận
    AS-->>U: Redirect về client với code và state
    U->>C: Truy cập redirect URI mang code và state
    C->>C: Kiểm tra state
    C->>AS: POST /oauth2/token với code và code_verifier
    AS-->>C: Access token (và ID token nếu OIDC)
    C->>RS: GET /api/bookings với Bearer access token
    RS->>RS: Xác minh token, scope và quyền trên dữ liệu
    RS-->>C: Chỉ các đặt phòng được phép xem
    C-->>U: Hiển thị kết quả
~~~

### 3.1. Diễn giải từng chặng

**Chặng A — Client xin quyền.** Khi Lan mở trang cần truy cập API, Client chuyển trình duyệt tới authorization endpoint của AS. Yêu cầu thường có `response_type=code`, `client_id`, `redirect_uri`, `scope`, `state`, `code_challenge` và `code_challenge_method=S256`. Client tạo `code_verifier` và giữ lại để đổi code; chỉ gửi challenge trong bước này. Nếu sử dụng OIDC, scope phải chứa `openid`.

**Chặng B — AS xác thực và cấp authorization code.** AS kiểm tra client, redirect URI và phạm vi yêu cầu; xác thực Lan nếu cần, áp dụng quy tắc consent. Nếu thành công, nó chuyển hướng về redirect URI hợp lệ cùng **authorization code ngắn hạn, chỉ sử dụng một lần** và `state`. Code là vật chứng trung gian để đổi token; **code không phải access token**.

**Chặng C — Client đổi code.** Client kiểm tra `state` để đối chiếu yêu cầu đã tạo, rồi gọi token endpoint với authorization code, redirect URI tương ứng và `code_verifier`. Confidential client còn phải xác thực với AS bằng phương thức đã đăng ký, nếu cấu hình yêu cầu. AS kiểm tra PKCE và điều kiện cấp token, sau đó trả access token; có thể trả refresh token và, trong OIDC, ID token.

**Chặng D — Client gọi API.** Client gửi access token ở header HTTP:

~~~http
GET /api/bookings HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

**Chặng E — RS xác minh và quyết định.** RS kiểm tra token được phát hành bởi AS tin cậy, dành cho API này, chưa hết hạn, có scope phù hợp, rồi tiếp tục kiểm tra rằng bản ghi đặt phòng thuộc quyền của Lan. Chỉ khi các điều kiện đều đạt, RS mới trả tài nguyên.

Điểm mấu chốt: **AS quyết định việc phát hành token**, còn **RS quyết định yêu cầu API cụ thể có được phép hay không**. Một access token hợp lệ vẫn có thể bị RS từ chối vì thiếu quyền.

## 4. Token là gì và mỗi vai trò dùng token nào?

| Hiện vật | Ai phát hành? | Ai nhận/sử dụng? | Mục đích |
| --- | --- | --- | --- |
| **Authorization code** | AS | Client đổi tại token endpoint | Chứng minh client hoàn tất chặng authorization và đổi lấy token theo ràng buộc |
| **Access token** | AS | Client gửi đến RS; RS xác minh | Cấp quyền truy cập tài nguyên trong phạm vi, đối tượng nhận và thời hạn nhất định |
| **ID token** (OIDC) | OP/AS | OIDC Client/RP xác minh | Truyền thông tin về sự kiện xác thực và danh tính người dùng cho client |
| **Refresh token** (nếu được cấp) | AS | Client gửi đến AS | Yêu cầu access token mới theo chính sách, không dùng để gọi API |
| **Client secret** (nếu có) | Được thiết lập lúc đăng ký client | Confidential client dùng để xác thực với AS | Thông tin xác thực client; **không phải token người dùng** |

Cần phân biệt ba khái niệm:

- **Access token không đồng nghĩa với ID token.** API phải xử lý **access token** đúng đối tượng nhận; không lấy ID token làm Bearer token cho API.
- **JWT chỉ là một định dạng token.** Access token có thể là JWT hoặc opaque. RS phải tuân theo định dạng và cơ chế xác minh đã thỏa thuận với AS.
- **Scope không thay thế toàn bộ phân quyền.** `booking.read` cho biết token có phạm vi đọc Booking API; nó không cho biết client được đọc booking ID nào.

Ví dụ các claim có thể xuất hiện trong một JWT access token:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": ["booking-api"],
  "exp": 1893456000,
  "scope": "booking.read"
}
~~~

Đây là payload **minh họa**, không phải token hợp lệ và không chứa chữ ký. `sub` thường nhận diện người dùng trong luồng có người dùng, nhưng trong một số grant như client credentials có thể nhận diện client. `aud` là đối tượng nhận token, cần được AS thiết kế/phát hành phù hợp với RS; không mặc định suy ra từ `scope`.

## 5. OAuth 2.0 và OIDC thay đổi trách nhiệm như thế nào?

Với **OAuth 2.0 thuần**, Client chủ yếu quan tâm liệu nó đã có access token hợp lệ để gọi RS hay chưa. OAuth 2.0 tự nó không đưa ra cơ chế xác thực người dùng chuẩn hóa để Client có thể dựa vào một access token rồi kết luận chắc chắn “người dùng đã đăng nhập là ai”.

Với **OpenID Connect**, Client yêu cầu scope `openid` và trở thành **Relying Party (RP)**. AS hỗ trợ OIDC được gọi là **OpenID Provider (OP)**. OP phát hành **ID token** chứa các claim được xác định theo OIDC (ví dụ `iss`, `sub`, `aud`, `exp`, `iat`). Client phải xác minh ID token theo yêu cầu OIDC, chẳng hạn chữ ký, issuer, audience, thời hạn và nonce nếu có gửi nonce. OP có thể cung cấp UserInfo endpoint để trả thêm claim theo scope và chính sách.

Ví dụ, `booking-web` có hai mục đích riêng:

1. Dùng **ID token** (cùng cơ chế phiên đăng nhập của ứng dụng) để biết người dùng đã được OP xác thực.
2. Dùng **access token** để gọi `booking-api`.

RS không cần nhận ID token để chứng minh “Lan là ai”; nó cần access token và kiểm tra quyền truy cập thích hợp.

## 6. Ánh xạ sang Spring Security và Spring Authorization Server

Trong ứng dụng Spring Boot, tên thư viện thể hiện trách nhiệm chính; cùng một hệ thống có thể dùng nhiều nhóm cấu hình.

| Vai trò giao thức | Thành phần Spring thường dùng | Chức năng |
| --- | --- | --- |
| Resource Owner | Người dùng/tài khoản, cơ chế đăng nhập như `UserDetailsService` hoặc nhà cung cấp danh tính kết nối | Đại diện chủ thể được xác thực theo chính sách; không có annotation “ResourceOwner” riêng |
| Client | `spring-security-oauth2-client`, `ClientRegistration`, OAuth2 Login/Authorized Client | Đăng ký provider và client, hỗ trợ đăng nhập OIDC, lưu/quản lý authorized client và gọi API |
| Authorization Server | **Spring Authorization Server**, `RegisteredClientRepository`, `OAuth2AuthorizationService`, cấu hình endpoint/khóa ký | Xử lý giao thức ủy quyền, phát hành token, đăng ký client và lưu trạng thái ủy quyền |
| Resource Server | `spring-security-oauth2-resource-server`, `JwtDecoder` hoặc opaque-token introspector, `SecurityFilterChain` | Xác minh access token và bảo vệ API |

### 6.1. Ví dụ cấu hình Resource Server

Một Booking API dùng JWT do AS phát hành có thể cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

Và quy định scope bắt buộc khi đọc booking:

~~~java
@Bean
SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/bookings/**")
                .hasAuthority("SCOPE_booking.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

Trong cấu hình JWT Resource Server của Spring Security, các giá trị scope thường được ánh xạ thành authority mang tiền tố `SCOPE_`, vì thế `booking.read` trở thành `SCOPE_booking.read`. Mã trên mô tả **chặn truy cập ở lớp endpoint**; phần kiểm tra booking có thuộc người dùng/tenant tương ứng hay không vẫn cần đặt trong tầng nghiệp vụ hoặc chính sách truy cập dữ liệu.

**Lưu ý về audience:** `issuer-uri` giúp xác định nguồn metadata/khóa đáng tin cậy và các kiểm tra JWT mặc định tương ứng. Trong hệ thống có nhiều API, hãy cấu hình/đăng ký thêm kiểm tra `aud` theo audience được AS phát hành. Không giả định chỉ có issuer đúng thì token tự động dành cho mọi RS.

### 6.2. Ví dụ cấu hình OAuth2/OIDC Client

Một backend/BFF Spring Boot cần đăng nhập với AS có thể đăng ký client qua cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          booking-web:
            provider: booking-idp
            client-id: booking-web
            client-secret: ${BOOKING_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - booking.read
        provider:
          booking-idp:
            issuer-uri: https://auth.example.test
~~~

Đây là ví dụ cho **confidential client có backend giữ client secret**. Phía AS phải đăng ký đúng `client_id`, redirect URI, phương thức xác thực, grant type và các scope được phép. Secret trong ví dụ được cung cấp từ biến môi trường; không đưa secret thật vào repository. PKCE cần được bật/cấu hình nhất quán với loại client và AS.

### 6.3. Ví dụ trách nhiệm của Authorization Server

Ở phía Spring Authorization Server, các khái niệm thường gặp gồm:

- **`RegisteredClientRepository`:** lưu định danh và chính sách của client; ví dụ `booking-web` được dùng Authorization Code, redirect URI nào, scope nào.
- **`OAuth2AuthorizationService`:** lưu thông tin authorization và token phục vụ vòng đời cấp quyền.
- **`OAuth2AuthorizationConsentService`:** lưu chấp thuận quyền khi ứng dụng cần consent.
- **`AuthorizationServerSettings`:** thiết lập issuer, endpoint và các thông số AS.
- **`JWKSource` / khóa ký:** cung cấp khóa để ký token và công bố phần khóa thích hợp để RS xác minh JWT.
- **Cấu hình OIDC:** bật những endpoint/chức năng OIDC cần thiết, bên cạnh các endpoint OAuth 2.0.

Tạo một AS không tự động biến mọi API trong cùng ứng dụng thành RS. Muốn bảo vệ API, phải có cấu hình và kiểm tra truy cập của RS tương ứng. Khi triển khai production, cần lưu bền vững client/authorization/consent phù hợp, bảo vệ khóa ký, lên kế hoạch xoay khóa và xác định issuer HTTPS ổn định.

## 7. Các tình huống dễ nhầm

### Tình huống A — Ứng dụng gọi API mà không có người dùng

Một service báo cáo gọi Booking API bằng **Client Credentials**. Client là service báo cáo, AS xác thực client rồi cấp access token, RS kiểm tra token. **Không có chặng người dùng đăng nhập hoặc consent trong yêu cầu này.** Resource Owner không nhất thiết xuất hiện như một người đang thao tác ở runtime, vì grant dựa trên quyền của client đã được hệ thống cho phép. Quyền của service cần được giới hạn riêng; không giả định token đại diện cho một người dùng cụ thể.

### Tình huống B — Một service có hai vai trò

Booking API nhận access token từ Web App (**RS**) và sau đó cần gọi Payment API (**Client** đối với Payment API). Booking API phải xác thực request đến như một RS, đồng thời phải có cơ chế lấy/chuyển tiếp quyền truy cập đi phù hợp như một Client. Không được tự ý dùng lại một access token cho Payment API nếu token không có audience/quyền phù hợp.

### Tình huống C — Người dùng đăng nhập rồi xem dữ liệu của người khác

Lan có access token chứa `booking.read`. Lan gọi `GET /api/bookings/999`, nhưng booking 999 thuộc Minh. Access token có scope hợp lệ **không cấp quyền đọc booking 999**. RS phải trả từ chối theo chính sách nghiệp vụ. Đây là ví dụ điển hình về kiểm soát truy cập ở mức đối tượng (object-level authorization).

### Tình huống D — ID token bị dùng thay access token

Web App đã nhận ID token qua OIDC và gửi nó đến Booking API với `Authorization: Bearer ...`. Đó là sai mục đích: ID token hướng tới Client/RP, còn RS phải yêu cầu access token dành cho API. Việc cả hai đều có thể là JWT không làm chúng hoán đổi được cho nhau.

## 8. Các lỗi bảo mật và biện pháp phòng tránh

| Lỗi thiết kế | Tại sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Đặt client secret trong mã JavaScript phát đến trình duyệt | Người dùng hoặc bên thứ ba có thể xem secret | Dùng public client với PKCE, hoặc BFF/confidential client giữ secret phía server |
| Bỏ qua `state` hoặc không ràng buộc PKCE | Làm yếu bảo vệ luồng chuyển hướng và đổi code | Dùng `state`, Authorization Code + PKCE (`S256`), kiểm tra callback và redirect URI |
| API chấp nhận token chỉ vì giải mã JSON được | Payload có thể bị giả mạo hoặc token dành cho bên khác | Xác minh chữ ký/introspection, issuer, hạn dùng, audience và quyền |
| API chỉ kiểm tra `scope` mà bỏ quyền sở hữu bản ghi | Có thể đọc dữ liệu của người dùng khác (BOLA/IDOR) | Kiểm tra chủ sở hữu/tenant/quyền trên từng đối tượng tài nguyên |
| Dùng ID token để gọi API | Sai đối tượng nhận và mục đích token | Client kiểm tra ID token; RS kiểm tra access token |
| Ghi token, authorization code, client secret vào log | Bí mật có thể lộ qua log và giám sát | Che/mask thông tin nhạy cảm, giảm log dữ liệu xác thực |
| Không có quy trình xoay khóa hoặc thu hồi | Khóa/token lộ khó xử lý; xác minh bị gián đoạn | Quản lý vòng đời khóa, thời hạn token, refresh token và chiến lược thu hồi |

Bên cạnh đó, sử dụng HTTPS cho các endpoint thực tế, đặt chính xác redirect URI và tách môi trường phát triển/production. Token kiểu Bearer cho phép bên nắm được token sử dụng token trong giới hạn của nó, nên cơ chế lưu giữ và truyền token là một phần của thiết kế an toàn.

## 9. Kiểm thử theo đúng trách nhiệm từng vai trò

Một bộ kiểm thử tích hợp tối thiểu có thể đi theo luồng từ Client đến RS:

| Bài kiểm thử | Kỳ vọng | Trách nhiệm nổi bật |
| --- | --- | --- |
| Client gửi redirect URI không đăng ký | AS từ chối yêu cầu | AS |
| Client đổi code với `code_verifier` sai | Token endpoint từ chối | AS |
| Người dùng không hoàn tất đăng nhập hoặc từ chối consent khi cần | Không cấp quyền hợp lệ cho client | Resource Owner / AS |
| API thiếu Bearer token | Trả `401` cho tài nguyên yêu cầu xác thực | RS |
| API nhận token hết hạn, sai chữ ký, sai issuer hoặc sai audience | Từ chối truy cập | RS |
| API nhận token đúng audience nhưng thiếu `booking.read` | Không cho đọc Booking API | RS |
| API nhận token có `booking.read` nhưng yêu cầu booking của người khác | Từ chối do quyền nghiệp vụ | RS |
| Client gửi ID token thay access token | API không coi đó là quyền truy cập hợp lệ | Client / RS |
| Client Credentials gọi endpoint chỉ dành cho người dùng | Từ chối nếu thiếu danh tính/quyền người dùng theo chính sách | RS |

Trong Spring Security, test mức controller/service với các đối tượng xác thực giả lập có thể xác minh quy tắc scope và business authorization. Test tích hợp thực tế cần bổ sung bằng chứng rằng AS phát token đúng cấu hình và RS xác minh chữ ký, issuer, audience, thời gian hiệu lực đúng cách.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Người dùng đã đăng nhập thành công, nhưng Web App không thể đọc dữ liệu API vì token thiếu scope. Lỗi nằm ở “authentication” hay “authorization”?  
**Gợi ý:** Đăng nhập chứng minh danh tính; scope là một điều kiện cấp quyền truy cập.

**Câu 2.** Nếu Resource Server xác minh JWT bằng public key của AS, tại sao không cần hỏi AS trên từng request?  
**Gợi ý:** Chữ ký và claim có thể được xác minh cục bộ bằng khóa công khai tin cậy; chính sách thu hồi tức thời cần cơ chế bổ sung phù hợp.

**Câu 3.** Một client có thể đồng thời là Resource Server không?  
**Đáp án:** Có, nếu ứng dụng vừa bảo vệ endpoint của mình vừa gọi một API khác. Vai trò được xác định theo từng tương tác.

**Câu 4.** Có `scope=booking.read` đã đủ để truy cập mọi booking chưa?  
**Đáp án:** Chưa. RS còn phải kiểm tra quyền trên đối tượng, tenant và quy tắc nghiệp vụ.

**Câu 5.** Trong OIDC, token nào để Client biết kết quả xác thực người dùng, token nào để gọi API?  
**Đáp án:** Client xác minh ID token để xử lý đăng nhập OIDC; Client dùng access token để gọi RS.

## 11. Ghi nhớ khi thiết kế hệ thống

- **Resource Owner** là chủ thể có thẩm quyền đối với tài nguyên; thường là người dùng.
- **Client** là ứng dụng xin và dùng quyền truy cập; có thể là trình duyệt, mobile app, BFF hoặc backend.
- **Authorization Server** quản lý việc xác thực/cấp quyền theo giao thức và phát hành token.
- **Resource Server** bảo vệ API, xác minh access token và thực thi quyền truy cập thực tế.
- **OAuth 2.0** định nghĩa ủy quyền; **OIDC** thêm xác thực người dùng cho Client thông qua ID token và các quy tắc liên quan.
- **Access token hợp lệ chưa bảo đảm đủ quyền**; kiểm tra audience, scope và quyền trên tài nguyên là trách nhiệm không thể bỏ qua của RS.

Hiểu rạch ròi bốn vai trò này là nền tảng để cấu hình Spring Authorization Server, Spring Security OAuth2 Client và Resource Server mà không nhầm lẫn nơi phát hành token với nơi bảo vệ dữ liệu.

