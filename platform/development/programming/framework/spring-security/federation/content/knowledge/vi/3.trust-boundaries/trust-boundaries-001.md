# Xác định bên phát hành, bên tiếp nhận và tài nguyên được bảo vệ trong liên kết danh tính

Trong hệ thống liên kết danh tính (identity federation), một quyết định tin cậy luôn phải trả lời được ba câu hỏi độc lập:

1. **Ai phát hành bằng chứng?** Nhà cung cấp danh tính hoặc máy chủ ủy quyền nào đã phát hành assertion/token, và hệ thống có thực sự tin nguồn đó?
2. **Ai là bên được phép tiếp nhận?** Ứng dụng/client/service provider hoặc API nào là đối tượng nhận dự kiến của bằng chứng?
3. **Tài nguyên nào được bảo vệ?** Sau khi nhận bằng chứng hợp lệ, người dùng được thao tác gì trên API, dữ liệu, bản ghi và tenant cụ thể nào?

Một token có chữ ký hợp lệ mới chứng minh nó xuất phát từ khóa được tin cậy; **chưa đủ** để sử dụng token ở bất kỳ ứng dụng nào hoặc cấp quyền tới bất kỳ dữ liệu nào. Xác định sai một trong ba vai trò có thể dẫn đến nhận nhầm token, nhầm tổ chức, liên kết nhầm tài khoản hoặc truy cập chéo tenant.

Bài học tập trung vào cách nhận diện ba vai trò và ranh giới tin cậy trong SSO doanh nghiệp, OpenID Connect (OIDC), OAuth 2.0, SAML 2.0 và ứng dụng Spring Security.

## 1. Ba vai trò cốt lõi và các thuật ngữ liên quan

| Câu hỏi | Vai trò | Thuật ngữ thường gặp | Trách nhiệm |
| --- | --- | --- | --- |
| Ai chứng thực và phát hành? | **Bên phát hành** | Identity Provider (IdP), OpenID Provider (OP), Authorization Server (AS), SAML IdP | Xác thực người dùng hoặc cấp quyền, ký/phát hành bằng chứng theo giao thức |
| Ai nhận và xử lý bằng chứng? | **Bên tiếp nhận** | Relying Party (RP), OIDC Client, SAML Service Provider (SP), OAuth 2.0 Resource Server | Xác minh bằng chứng đúng nguồn, đúng đối tượng nhận, đúng điều kiện; thiết lập ngữ cảnh bảo mật |
| Điều gì cần được bảo vệ? | **Tài nguyên được bảo vệ** | Protected Resource, API endpoint, đối tượng dữ liệu, tenant, nghiệp vụ | Thực thi authorization theo subject, phạm vi, role, tenant và ngữ cảnh |

**Lưu ý:** Một thành phần có thể giữ nhiều vai trò tùy giao thức và luồng. Ứng dụng web là OIDC client/RP khi nhận ID token để đăng nhập; API do ứng dụng ấy gọi có thể là resource server khi nhận access token. Trong OAuth 2.0, **resource server cũng là bên tiếp nhận access token**, nhưng không nhất thiết là nơi người dùng đăng nhập qua trình duyệt.

Để gọi tên đúng vai trò, cần phân biệt thêm:

- **Subject (`sub` / NameID):** danh tính mà bằng chứng nói tới. Subject không phải issuer; một chuỗi subject giống nhau từ hai issuer khác nhau không phải tự động là một người.
- **Trust anchor:** cấu hình tin cậy, ví dụ issuer đã cho phép, metadata, khóa ký/JWKS hoặc chứng thư SAML, client registration và chính sách của tổ chức. URL đến một IdP không tự tạo quan hệ tin cậy.
- **Audience (`aud` / AudienceRestriction):** đối tượng nhận mà bằng chứng được phát hành cho. Không đồng nhất với “người dùng sẽ được xem mọi tài nguyên”.
- **Recipient/destination:** nơi thông điệp SAML được gửi tới; phải phù hợp với điểm tiếp nhận và luồng đã đăng ký.
- **Tenant/organization:** phạm vi quản trị và dữ liệu mà người dùng đang truy cập. Tenant thuộc chính sách ứng dụng, không phải một quyền tự xuất hiện từ chữ ký token.
- **Scope/authority/role:** thông tin có thể hỗ trợ quyết định quyền; phải phân biệt nguồn cấp scope, cách ánh xạ role và chính sách của tài nguyên cụ thể.

## 2. Cách đặt ba câu hỏi trên một sơ đồ

Giả sử nhân viên công ty B cần dùng ứng dụng quản lý đơn hàng của công ty A:

~~~mermaid
flowchart LR
    U["Nhân viên B"]
    I["IdP B<br/>Bên phát hành danh tính"]
    W["Portal A<br/>OIDC Client / RP"]
    API["Orders API của A<br/>Resource Server"]
    D[("Đơn hàng tenant B<br/>Tài nguyên được bảo vệ")]
    U -->|"Đăng nhập"| I
    I -->|"ID token cho Portal A"| W
    W -->|"Access token phù hợp API"| API
    API -->|"Policy tenant + order"| D
~~~

Sơ đồ thể hiện **quan hệ trách nhiệm logic**; tùy kiến trúc, Portal A có thể dùng phiên máy chủ, tự gọi API bằng token khác, hoặc ứng dụng được trao access token có đúng audience của API. ID token từ IdP B dành cho Portal A **không được chuyển thẳng thành bearer token của Orders API** chỉ vì người dùng đã đăng nhập.

Xác định vai trò theo từng chặng:

| Chặng | Bên phát hành | Bên tiếp nhận dự kiến | Tài nguyên/quyết định bảo vệ |
| --- | --- | --- | --- |
| OIDC đăng nhập Portal | OpenID Provider được Portal A tin cậy | OIDC client Portal A (ID token có audience phù hợp client) | Tạo/duy trì phiên đăng nhập sau khi xác minh |
| OAuth 2.0 gọi Orders API | Authorization Server phát hành access token | Orders API hoặc cơ chế introspection/authorization được cấu hình cho API | Endpoint, hành động, đơn hàng và tenant |
| SAML đăng nhập vào một SP | SAML IdP | SP có entityID/ACS được cấu hình | Phiên của SP; quyền tài nguyên vẫn do SP quyết định |
| Đồng bộ SCIM (nếu có) | Nguồn quản trị vòng đời/người dùng | SCIM service endpoint | Tạo, sửa, vô hiệu hóa tài khoản; không thay token đăng nhập |

Có thể có một sản phẩm IdP kiêm Authorization Server, nhưng vai trò xác thực, cấp access token và kiểm tra quyền API vẫn là các bước logic khác nhau.

## 3. Xác định bên phát hành: ai thực sự đứng sau `iss`?

### Với OpenID Connect

ID token dạng JWT thường chứa các claim:

~~~json
{
  "iss": "https://login.partner-b.example",
  "sub": "employee-842",
  "aud": "portal-a-client",
  "iat": 1760000000,
  "exp": 1760003600
}
~~~

Đây là **payload minh họa**, không phải JWT đã ký và không thể dùng để xác thực. Muốn kết luận issuer được tin cậy, RP phải xác minh token thật theo metadata, thuật toán và khóa ký được cho phép, đồng thời đối chiếu `iss` với issuer đã cấu hình. Không lấy giá trị `iss` từ JSON chưa xác minh để tự động tin hoặc tải cấu hình từ một URL bất kỳ do người dùng cung cấp.

Checklist với issuer OIDC:

1. Tên issuer đã được đăng ký và cho phép đối với ứng dụng/tenant liên quan.
2. Discovery metadata, JWKS URI và quy trình xoay khóa được lấy từ nguồn tin cậy phù hợp cấu hình.
3. Chữ ký hợp lệ theo thuật toán được cho phép; từ chối `alg=none` và thuật toán không được chính sách chấp nhận.
4. `iss` khớp issuer mong đợi; token hợp thời gian `iat`, `exp` và các điều kiện khác theo loại token.
5. Token được phát hành **cho đúng bên nhận** qua `aud`, không dùng lẫn token của client/API khác.
6. `sub` được giải thích trong phạm vi issuer, sau đó mới ánh xạ vào danh tính nội bộ.

Issuer là *nguồn chịu trách nhiệm về tuyên bố danh tính hoặc token*; địa chỉ email công ty, domain hiển thị trong login page, hostname trong redirect URL và issuer của token không phải lúc nào cũng giống nhau. Không suy ra trust chỉ dựa vào hậu tố `@partner-b.example`.

### Với OAuth 2.0

Authorization Server cấp **access token** để client truy cập tài nguyên. Tùy hệ thống, token có thể là JWT hoặc opaque token. Nếu là JWT có issuer, API cần kiểm tra chữ ký, issuer và audience theo cấu hình; nếu opaque token, API cần introspection hoặc cách xác minh đã được triển khai. Một access token hợp lệ cho API X không tự hợp lệ cho API Y.

**OAuth 2.0 bản thân nó không phải giao thức đăng nhập.** OIDC cung cấp ID token và các quy tắc xác thực danh tính cho client. “Authorization Server đã phát hành access token” không đồng nghĩa “API có thể dùng access token như ID token để đăng nhập”.

### Với SAML 2.0

Bên phát hành là SAML IdP với `Issuer` (entityID) đã tin cậy. SP kiểm tra chữ ký XML đúng ngữ cảnh, chứng thư ký được cấu hình, metadata và các điều kiện assertion. Không suy ra issuer bằng tên miền trên trình duyệt, hoặc bằng NameID/email của người dùng.

### Khi có identity broker

~~~mermaid
flowchart LR
    U["Người dùng"]
    O["IdP nguồn của B"]
    B["Identity broker của A"]
    R["Ứng dụng RP của A"]
    U --> O
    O -->|"Assertion/token upstream"| B
    B -->|"Token do broker phát hành"| R
~~~

Nếu RP trực tiếp nhận **token do broker ký**, issuer mà RP xác minh thường là **broker**. IdP B là nguồn xác thực **upstream**, không phải issuer trực tiếp của token ấy. Chỉ sử dụng một claim “upstream identity provider” khi broker cam kết, bảo vệ và định nghĩa rõ ý nghĩa claim. Không tin claim tùy ý từ browser để “đổi issuer”.

## 4. Xác định bên tiếp nhận: bằng chứng được phát hành cho ai?

Việc xác minh chữ ký và issuer chưa đủ: token/assertion phải **ràng buộc đúng bên nhận**.

### OIDC ID token: RP/Client và `aud`

Giả sử một IdP phục vụ hai ứng dụng:

- Portal A có `client_id = portal-a-client`.
- Dashboard C có `client_id = dashboard-c-client`.

ID token với `aud = portal-a-client` dành cho **Portal A**. Dashboard C không được chấp nhận token đó để đăng nhập, dù chữ ký và issuer đúng. Khi `aud` có nhiều giá trị, cần áp dụng đầy đủ quy tắc OIDC liên quan đến audience và `azp` (authorized party) trong trường hợp có yêu cầu. RP cũng phải kiểm soát `state`, `nonce` theo luồng, redirect URI và code exchange để ngăn trộn giao dịch và tấn công login CSRF.

### OAuth 2.0 access token: Resource Server và API audience

Giả sử cùng Authorization Server phát token cho:

- `orders-api`: xem và sửa đơn hàng.
- `payroll-api`: xem dữ liệu lương.

Token dành cho `orders-api` không được chấp nhận tại `payroll-api`. Điều kiện audience phải được kiểm tra theo contract của **access token**, có thể khác `aud` của ID token dùng cho Portal. `scope` như `orders.read` cũng không đồng nghĩa với quyền xem mọi đơn hàng của mọi tenant.

Nếu access token là opaque và chỉ có thể xác minh qua introspection, API phải kiểm tra token đang active, quyền/phạm vi và thông tin resource phù hợp với mô hình máy chủ ủy quyền. Không cố giải mã opaque token như JWT.

### SAML Assertion: SP entityID, ACS và điều kiện recipient

Đối với SAML Web Browser SSO:

- `Issuer` xác định IdP.
- `AudienceRestriction` giới hạn assertion cho **SP entityID** dự kiến.
- `SubjectConfirmationData Recipient` thường phải khớp ACS URL tiếp nhận phù hợp.
- `Destination`, `InResponseTo` (khi áp dụng), `NotBefore`/`NotOnOrAfter` và replay cache giúp ràng buộc đúng thông điệp và thời điểm.

SP X không chấp nhận assertion cho SP Y. Không chỉ tìm một assertion có “đúng email” rồi cấp session. Với SAML cần dùng thư viện xử lý XML Signature có chống signature wrapping, xác minh đúng phần thông điệp được tham chiếu và được yêu cầu ký.

### Bảng nhận diện nhanh

| Bằng chứng | Bên phát hành cần xác minh | Bên nhận cần kiểm tra | Không dùng thay cho |
| --- | --- | --- | --- |
| OIDC ID token | OP/issuer được trust | OIDC client (`aud`/`azp` theo quy tắc) | Access token cho API |
| OAuth JWT access token | Authorization Server/issuer được trust | API/resource audience và token policy | ID token để đăng nhập người dùng |
| OAuth opaque access token | Authorization Server qua introspection hoặc cơ chế tương đương | Resource/API, active, scope, ràng buộc chính sách | JWT có thể tự xác minh chữ ký |
| SAML assertion | SAML IdP/entityID được trust | SP entityID, recipient/ACS, điều kiện assertion | Bearer token tùy ý cho API |
| Cookie phiên ứng dụng | Ứng dụng phát hành/quản lý phiên | Ứng dụng sở hữu session | Chứng thư liên tổ chức hay API access token |

## 5. Xác định tài nguyên được bảo vệ: địa chỉ API chỉ là lớp đầu

“Tài nguyên” không dừng ở endpoint. Một API `GET /api/orders/812` có thể trả về đơn hàng thuộc tenant B; người dùng C dù có scope `orders.read` vẫn không được thấy đơn ấy.

Các lớp kiểm tra nên được phân tách:

1. **Authentication:** token/assertion hoặc phiên có hợp lệ và thuộc principal xác định?
2. **Token acceptance:** issuer, audience, thời hạn, trạng thái, ràng buộc giao thức có phù hợp đúng ứng dụng/API?
3. **Coarse authorization:** token có scope/authority cần thiết để gọi nhóm API này?
4. **Tenant membership:** principal có thành viên hợp lệ trong tenant đích theo dữ liệu ứng dụng kiểm soát?
5. **Object-level authorization:** bản ghi/đơn hàng thuộc tenant nào, chủ sở hữu là ai, có chia sẻ hợp lệ không?
6. **Business policy:** trạng thái đơn hàng, phân tách nhiệm vụ, hạn mức hay điều kiện nghiệp vụ có cho phép hành động?

Ví dụ kiểm tra cho `GET /api/tenants/B/orders/812`:

| Điều kiện | Kết quả mong đợi |
| --- | --- |
| JWT chữ ký hợp lệ, issuer đúng, audience chứa `orders-api` | Có thể xác thực token cho API |
| Token có scope `orders.read` | Được phép tiến tới kiểm tra nghiệp vụ đọc đơn |
| Principal chỉ là thành viên tenant C | **DENY** do không thuộc tenant B |
| Principal thuộc B, nhưng order 812 thuộc C | **DENY** do quyền truy cập đối tượng |
| Principal thuộc B, order 812 thuộc B và có quyền đọc | **ALLOW** nếu các điều kiện khác cũng đạt |

Tên tenant trong URL, path, query, header hoặc body là dữ liệu do client lựa chọn. Máy chủ phải đối chiếu nó với membership và quyền thật; không tin `X-Tenant-Id` hoặc claim `tenant` tự phát từ một nguồn chưa được ủy quyền làm nguồn quyền tối hậu. Có thể dùng claim tenant được cấp bởi authorization server tin cậy, nhưng vẫn cần chính sách nhất quán về owner của claim, phạm vi tenant và quyền đối tượng.

**ID token không cấp quyền truy cập dữ liệu.** Một người đăng nhập thành công chỉ có nghĩa bên nhận đã xác thực danh tính theo policy; quyền từng tài nguyên phải được đánh giá riêng.

## 6. Mô hình liên kết nội bộ và liên tổ chức

### Ví dụ A: công ty có nhiều ứng dụng nội bộ

- IdP công ty A là bên phát hành ID token cho Portal, Wiki và HR.
- Portal, Wiki, HR là ba RP với client registration/audience riêng.
- HR API là resource server, dữ liệu lương là tài nguyên đặc biệt nhạy cảm.

Nhân viên đã đăng nhập Portal qua SSO vẫn không tự có quyền đọc lương. HR phải xác minh token phù hợp HR API và role/membership. Token của Wiki có issuer hợp lệ nhưng audience là Wiki phải bị HR từ chối.

### Ví dụ B: tổ chức A hợp tác với B và C

- IdP B và IdP C là hai nguồn danh tính ngoài.
- Cổng đối tác A là RP hoặc một broker trong A là RP upstream.
- Orders API của A bảo vệ bản ghi theo tenant và hợp đồng.
- A là chủ thể quyết định membership/role của khách B/C trong dữ liệu A.

Công ty B có thể tự xác thực nhân viên của B, nhưng **không được tự cấp quyền quản trị toàn bộ dữ liệu của A** chỉ bằng group/role do B phát hành. Nếu claim `groups = ["admin"]` đến từ B, A chỉ sử dụng sau khi có hợp đồng ánh xạ quyền và policy cụ thể, tránh chuyển role sang phạm vi khác.

### Ví dụ C: nhiều IdP qua một broker

- Broker chấp nhận và xác minh token upstream từ B/C.
- Broker phát hành token mới cho Portal A.
- Portal A xác minh issuer/audience của **token broker**.
- Broker phải cung cấp thông tin upstream một cách tin cậy nếu A cần phân biệt bên B/C, và A vẫn kiểm tra tenant membership.

Điểm cần nhớ: số bên phát hành/tiếp nhận thay đổi theo **từng chặng token**, không theo tên thương mại của sản phẩm. Mỗi chặng có bên nhận và trust policy riêng.

## 7. Ma trận trust phải khai báo tường minh

Để xây hệ thống nhiều tổ chức, thiết kế ma trận tin cậy thay vì tự suy ra từ domain email hoặc URL redirect:

| Mối quan hệ | Issuer/IdP cho phép | Bên tiếp nhận | Token/Assertion | Tài nguyên và policy |
| --- | --- | --- | --- | --- |
| A → Portal A | `https://idp.a.example` | `portal-a-client` | OIDC ID token | Tạo session Portal; tiếp theo kiểm membership |
| B → Portal A | `https://login.b.example` | `portal-b2b-client` | OIDC ID token | Chỉ khách đã được A mời |
| A AS → Orders API | `https://auth.a.example` | `orders-api` | Access token | Scope + role + tenant + ownership |
| A IdP → Legacy SP | `https://idp.a.example/saml` | `urn:sp:legacy-a` | SAML assertion | Phiên Legacy; policy riêng |

Bảng là ví dụ thiết kế; URI dùng domain `.example` không tồn tại để triển khai trực tiếp. Trong thực tế cần lưu cấu hình khóa/chứng thư, metadata, client IDs, ACS/redirect URI, thời hạn, mức xác thực, cách rotate/revoke và người chịu trách nhiệm.

**Không có quan hệ tin cậy bắc cầu mặc định.** Nếu Portal A tin broker X, và X tin IdP B, điều đó không có nghĩa mọi dịch vụ khác của A tự tin trực tiếp token IdP B; cũng không có nghĩa B được phát token hợp lệ cho mọi API của A. Mỗi RP/resource server phải có trust contract riêng.

## 8. Quy trình phân tích một yêu cầu khi có nhiều token

Khi xem sơ đồ kiến trúc hoặc sự cố, sử dụng quy trình sau cho **từng chặng**:

1. Xác định request/response nào mang token, assertion hay cookie; **không nhầm ID token với access token**.
2. Xác định chính xác **người ký/phát hành** token (issuer, entityID, authorization server, session authority).
3. Xác định token được phát hành cho **client/API/SP nào** bằng `aud`, entityID, recipient, cấu hình redirect/ACS.
4. Xác định bên tiếp nhận thật: reverse proxy, backend, RP hay API? Bên đó có tự kiểm tra token hay chỉ tin header từ proxy?
5. Chỉ rõ ranh giới tin cậy của từng bước, ví dụ Internet → RP, RP → API, proxy → backend, tenant B → dữ liệu A.
6. Liệt kê tài nguyên (endpoint, object, tenant, dữ liệu), hành động (read/write/admin) và các điều kiện nghiệp vụ.
7. Xác định ai là chủ dữ liệu và nguồn quyền. Không tự biến claim bên ngoài thành quyền nội bộ.
8. Vẽ các trường hợp **deny**: token sai audience, issuer lạ, hết hạn, sai tenant, bị thu hồi membership, object của bên khác.

Trong kiến trúc reverse proxy hoặc API gateway, cần làm rõ ai là **điểm xác minh token cuối cùng**. Nếu backend tin một header `X-User` do gateway truyền, kết nối gateway→backend phải được bảo vệ, header do client gửi phải bị xóa/ghi đè tại gateway, và chính sách authorization của backend phải rõ ràng. Không tin header người dùng tùy ý từ Internet.

## 9. Áp dụng với Spring Security: OIDC login tại RP

Với Spring Boot 3.x, Java 17+ và ứng dụng Servlet sử dụng OIDC, hai dependency thường gặp là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Ví dụ `application.yml` minh họa **hai bên phát hành**, mỗi issuer có một client registration đã đăng ký riêng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-a:
            provider: corp-a
            client-id: portal-a-client
            client-secret: REPLACE_WITH_SECRET_MANAGER_VALUE
            authorization-grant-type: authorization_code
            scope: [openid, profile]
          partner-b:
            provider: partner-b
            client-id: portal-b2b-client
            client-secret: REPLACE_WITH_SECRET_MANAGER_VALUE
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          corp-a:
            issuer-uri: https://idp.a.example
          partner-b:
            issuer-uri: https://login.b.example
~~~

Các issuer/secret trên đều là dữ liệu giả. `issuer-uri` được dùng để tìm cấu hình giao thức OIDC nếu IdP hỗ trợ discovery đúng chuẩn. Redirect URI trên IdP phải khớp callback của client theo cấu hình ứng dụng; mặc định trong nhiều cấu hình Spring Security có dạng `/login/oauth2/code/{registrationId}`. URL khởi tạo login thường có dạng `/oauth2/authorization/corp-a` hoặc `/oauth2/authorization/partner-b`.

Một security filter chain tối thiểu cho login web:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfiguration {
    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đặt lớp trên ở `PortalSecurityConfiguration.java` trong dự án Spring Boot có dependencies nói trên. `oauth2Login` hỗ trợ xử lý code flow và xác minh dữ liệu OIDC theo registration; **cấu hình mẫu chưa hề quyết định người nào được xem đơn hàng hay thuộc tenant nào**. Sau đăng nhập, ứng dụng cần tra mapping theo issuer/subject đã xác minh và membership tại A, rồi quyết định quyền đối tượng ở service/repository.

Không xây danh sách issuer bằng giá trị `issuer` chưa xác minh từ query string; tenant lựa chọn phải ràng buộc với registration được phép theo cấu hình server. Đối với **SAML**, dùng Spring Security SAML2 Service Provider (`spring-security-saml2-service-provider` với `saml2Login`) và `RelyingPartyRegistration` đã cấu hình metadata/chứng thư/entityID/ACS phù hợp. RP OIDC và SP SAML có thuật ngữ khác nhau nhưng cùng cần kiểm tra bên phát hành, bên nhận và quyền ứng dụng.

## 10. Áp dụng với Spring Security: resource server bảo vệ API

Giả sử Orders API của A chấp nhận JWT access token từ **một issuer được tin cậy**, chỉ khi audience có `orders-api`. Có thể cấu hình `spring-boot-starter-oauth2-resource-server`, thêm security chain và validator audience. Đây là **ví dụ thiết kế cho một issuer**; môi trường nhiều issuer cần registry/allowlist và resolver được cấu hình riêng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {
    private static final String TRUSTED_ISSUER = "https://auth.a.example";
    private static final String REQUIRED_AUDIENCE = "orders-api";

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withIssuerLocation(TRUSTED_ISSUER)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(REQUIRED_AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                            "Token audience is not orders-api", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience));
        return decoder;
    }
}
~~~

Đây là **lớp cấu hình trong ứng dụng**, không phải chương trình Java chạy độc lập. Với JWT chuẩn, thư viện giải mã và kiểm chữ ký theo khóa từ issuer đã cấu hình. `JwtValidators.createDefaultWithIssuer` kiểm issuer cùng các điều kiện mặc định liên quan thời gian; validator thứ hai kiểm audience. Spring Security mặc định thường ánh xạ scope của access token thành authority `SCOPE_...` theo cấu hình JWT resource server thông thường. Nếu provider dùng claim khác, cần converter riêng có kiểm soát.

**Giới hạn quan trọng:** `hasAuthority("SCOPE_orders.read")` chỉ kiểm tra scope, chưa kiểm tra order/tenant cụ thể. Endpoint/controller/service phải tìm order theo ID, xác định tenant thật, membership và quyền theo đối tượng. Không mặc định rằng người có `orders.read` được xem mọi đơn hàng. Trong hệ thống nhiều client/issuer, không mở decoder nhận mọi issuer chỉ để tránh lỗi đăng nhập; chỉ cho phép issuer đã có hợp đồng trust, kiểm audience riêng cho từng API và tránh confusable issuer.

**Tại sao token của Portal không thay được access token?** ID token thường có audience là client của Portal, trong khi Orders API yêu cầu audience là `orders-api`. Nếu API chỉ xem chữ ký rồi chấp nhận mọi token cùng issuer, kẻ tấn công có thể đưa token hợp lệ **dành cho bên nhận khác** tới API (token substitution/confused deputy).

## 11. Java 17 chạy độc lập: xác minh ba vai trò ở tầng policy

Đoạn sau mô phỏng **quyết định policy sau khi bằng chứng đã được kiểm chứng mật mã**. Nó **không ký, giải mã, xác minh JWT hay thực hiện đăng nhập**. Trong sản phẩm thật, các trường `issuer`/`subject`/`audience` của `VerifiedContext` phải đến từ Spring Security hoặc thành phần xác minh token đáng tin cậy; chúng không được lấy trực tiếp từ dữ liệu người dùng gửi.

Tạo file `TrustBoundaryDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class TrustBoundaryDemo {
    record IdentityKey(String issuer, String subject) {}
    record VerifiedContext(IdentityKey identity, String audience,
                           Set<String> scopes) {}
    record Order(String id, String tenantId) {}

    private static final Set<String> TRUSTED_ISSUERS =
            Set.of("https://idp.partner-b.example");
    private static final String API_AUDIENCE = "orders-api";

    static boolean canReadOrder(
            VerifiedContext context,
            Order order,
            Map<IdentityKey, Set<String>> memberships) {

        if (!TRUSTED_ISSUERS.contains(context.identity().issuer())) {
            return false;
        }
        if (!API_AUDIENCE.equals(context.audience())) {
            return false;
        }
        if (!context.scopes().contains("orders.read")) {
            return false;
        }
        return memberships
                .getOrDefault(context.identity(), Set.of())
                .contains(order.tenantId());
    }

    public static void main(String[] args) {
        IdentityKey userB = new IdentityKey(
                "https://idp.partner-b.example", "employee-842");
        Map<IdentityKey, Set<String>> memberships =
                Map.of(userB, Set.of("tenant-b"));

        VerifiedContext valid = new VerifiedContext(
                userB, "orders-api", Set.of("orders.read"));
        VerifiedContext wrongAudience = new VerifiedContext(
                userB, "portal-a-client", Set.of("orders.read"));
        VerifiedContext unknownIssuer = new VerifiedContext(
                new IdentityKey("https://unknown.example", "employee-842"),
                "orders-api", Set.of("orders.read"));

        Order orderB = new Order("B-101", "tenant-b");
        Order orderC = new Order("C-201", "tenant-c");

        System.out.println("B order: " +
                canReadOrder(valid, orderB, memberships));
        System.out.println("C order: " +
                canReadOrder(valid, orderC, memberships));
        System.out.println("Wrong audience: " +
                canReadOrder(wrongAudience, orderB, memberships));
        System.out.println("Unknown issuer: " +
                canReadOrder(unknownIssuer, orderB, memberships));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac TrustBoundaryDemo.java
java TrustBoundaryDemo
~~~

Stdout chính xác:

~~~text
B order: true
C order: false
Wrong audience: false
Unknown issuer: false
~~~

Ý nghĩa từng kết quả:

- **B order: true** — đúng issuer, đúng API audience, có scope đọc và là thành viên tenant B.
- **C order: false** — thông tin xác thực/scope giống nhau, nhưng đơn hàng thuộc tenant C.
- **Wrong audience: false** — token dành cho Portal A không được nhận vào Orders API.
- **Unknown issuer: false** — một issuer không có trong allowlist bị từ chối, dù subject có hình thức quen thuộc.

Trong production, policy cần tra quyền hiện hành ở kho dữ liệu, áp dụng unique identity mapping, kiểm tra quyền từng order và không nhận `VerifiedContext` do caller tự dựng. Java demo dùng map trong bộ nhớ để làm rõ ranh giới, không phải giải pháp xác minh token hay phân quyền hoàn chỉnh.

## 12. Mối nguy nếu nhầm bên phát hành, bên tiếp nhận hoặc tài nguyên

| Sai lầm | Ranh giới bị phá | Tấn công/hậu quả | Biện pháp |
| --- | --- | --- | --- |
| Tin issuer bất kỳ từ claim hoặc URL đầu vào | Nguồn phát hành | Token giả/mạo hoặc nguồn không được phê duyệt | Allowlist, metadata/JWKS tin cậy, kiểm chữ ký và issuer |
| Chỉ kiểm chữ ký, bỏ `aud` | Bên tiếp nhận | Dùng token của RP/API khác tại hệ thống hiện tại | Kiểm audience cho đúng client/SP/API |
| Dùng ID token làm bearer token cho API | Loại bằng chứng/bên nhận | Token substitution, cấp quyền sai mục đích | API dùng access token thích hợp, kiểm resource audience |
| Nhầm issuer broker với IdP upstream | Nguồn phát hành | Sai ánh xạ danh tính và chính sách đối tác | Xác minh issuer token đang nhận; upstream qua claim broker đáng tin |
| Gộp user chỉ theo email/subject không kèm issuer | Danh tính liên tổ chức | Account takeover hoặc liên kết nhầm | Dùng issuer + subject + tenant; xác minh trước khi link |
| Tin role từ IdP đối tác thành quyền admin của A | Quyền ứng dụng | Leo thang đặc quyền | Role mapping tường minh, quyền do A quản trị |
| Scope hợp lệ là đủ để đọc mọi bản ghi | Tài nguyên cụ thể | IDOR/BOLA, rò dữ liệu chéo tenant | Membership và object-level authorization |
| SAML kiểm chữ ký nhưng bỏ recipient/audience | Bên nhận SP | Assertion từ SP khác được chấp nhận sai | Validate entityID, ACS, audience, recipient, InResponseTo |
| Chấp nhận header `X-User` từ Internet | Proxy/backend | Mạo danh tại backend | Trusted proxy, loại bỏ header đầu vào, bảo vệ kênh |
| Chỉ khóa login ở IdP, bỏ phiên còn hiệu lực | Vòng đời truy cập | Người đã nghỉ việc dùng session/token cũ | Deprovision, session expiry/revoke và rà soát quyền |

**Kiểm soát sâu hơn:** giới hạn thuật toán chấp nhận, chống replay, bảo vệ `state`/`nonce`, chuẩn hóa đồng hồ/clock skew hợp lý, xoay khóa, MFA/step-up cho nghiệp vụ nhạy cảm, quản lý secret an toàn, không log token/secret, truy vết issuer/subject/tenant và quyết định allow/deny theo quy định bảo vệ dữ liệu.

## 13. Kiểm thử ranh giới tin cậy theo tình huống

Đừng dừng kiểm thử ở “đăng nhập thành công”. Tạo bộ test phủ cả token, bên nhận và tài nguyên:

1. **Issuer hợp lệ + audience đúng + quyền đúng:** request được chấp nhận.
2. **Issuer lạ:** từ chối tại xác minh token, không tạo local user dựa vào email giống người nội bộ.
3. **Issuer hợp lệ, audience của ứng dụng khác:** từ chối tại bên nhận.
4. **JWT quá hạn/không hợp lệ chữ ký hoặc khóa không tin cậy:** từ chối trước authorization.
5. **Token có `orders.read`, nhưng order thuộc tenant khác:** từ chối tại tầng đối tượng.
6. **Cùng `sub` từ hai issuer:** không tự gộp hai người dùng.
7. **Cùng email từ B/C:** không tự liên kết account.
8. **SAML assertion cho SP Y gửi tới SP X:** từ chối vì audience/recipient/ACS không phù hợp.
9. **Gateway bỏ kiểm tra token hoặc chuyển thẳng header client:** backend phải từ chối đường đi không tin cậy.
10. **Quyền/tenancy bị thu hồi sau khi token phát hành:** API tuân theo chính sách hiệu lực và cơ chế revoke/TTL được thiết kế.
11. **Đổi issuer/chứng thư/JWKS hoặc broker:** hệ thống chỉ tiếp nhận theo cấu hình mới được phê duyệt và có quy trình migration/audit.
12. **Hai tổ chức dùng group `admin`:** quyền của B không bao giờ tự trở thành quyền quản trị A.

Khi log kết quả, nên ghi mã lỗi nghiệp vụ và metadata không nhạy cảm như tên registration, issuer đã kiểm tra, audience kỳ vọng, tenant/resource id theo chính sách lưu trữ; tránh lưu toàn bộ bearer token, SAML assertion hay dữ liệu cá nhân không cần thiết.

## 14. Checklist thực hành khi thiết kế Spring Security federation

| Bước | Câu hỏi cần trả lời | Bằng chứng/hiện vật |
| --- | --- | --- |
| Xác định nguồn phát hành | OP/AS/IdP nào đã được tin cho từng tổ chức? | Issuer/entityID allowlist, metadata, khóa/chứng thư |
| Xác định chặng tiếp nhận | RP/SP/API nào đang nhận đúng loại token? | Client registration, redirect URI/ACS, audience, validator |
| Nhận diện danh tính | `issuer + subject` ánh xạ vào ai? | Kho liên kết định danh; kiểm toán link/unlink |
| Xác định tài nguyên | Endpoint, object, data set, tenant nào? | Sơ đồ tài nguyên, ownership, tenant hierarchy |
| Xác định quyền | Ai quản trị scope/role và membership? | Chính sách source of truth, role mapping, điều kiện truy cập |
| Vòng đời | Ai có quyền mời, cấp, sửa và thu hồi quyền? | SCIM/JIT/invitation policy, session revocation và expiry |
| Kiểm thử âm tính | Token sai issuer/audience, đúng scope sai tenant thì sao? | Automated security tests và audit logs |
| Vận hành | Ai quản trị issuer/JWKS/cert và sự cố liên tổ chức? | Runbook, key rotation, cảnh báo, khôi phục |

**Quy tắc ghi nhớ:** với **mỗi token hoặc assertion**, hãy vẽ một mũi tên từ **bên phát hành** đến **bên tiếp nhận được chỉ định**; sau mũi tên là một quyết định riêng về **tài nguyên được bảo vệ**. Xác minh token trả lời “có tin bằng chứng và đúng nơi nhận không?”; authorization trả lời “principal này được làm gì với dữ liệu nào, trong tenant nào?”. Chỉ khi cả hai lớp đều đúng thì ranh giới tin cậy mới được giữ vững.