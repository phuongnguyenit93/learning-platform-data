# 6.3. Liên kết registration với provider bằng provider ID

> **Module:** Spring Security OAuth 2.0 OIDC Client  
> **Chương:** 6. Cấu hình provider  
> **Trọng tâm:** Sử dụng thuộc tính `spring.security.oauth2.client.registration.<registrationId>.provider` để nối từng OAuth 2.0 Client registration với cấu hình OpenID Provider/Authorization Server phù hợp.

Khi một ứng dụng Spring Boot triển khai đăng nhập OpenID Connect (OIDC) hoặc gọi API bằng OAuth 2.0 Client, cấu hình thường chia làm hai nhóm: **registration** mô tả Client mà ứng dụng đại diện, còn **provider** mô tả nhà cung cấp dịch vụ ủy quyền/xác thực mà Client giao tiếp.

Hai nhóm này có thể có tên giống nhau, nhưng không bắt buộc. Thuộc tính `provider` dưới mỗi registration chính là **khóa liên kết** giữa chúng. Hiểu đúng khóa này giúp cấu hình nhiều Client, tái sử dụng provider, đặt tên có ý nghĩa nghiệp vụ và tránh trộn nhầm issuer, token endpoint hoặc thông số của các hệ thống khác nhau.

Bài học sử dụng cú pháp cấu hình phổ biến của Spring Boot 3.x và Spring Security 6.x, trong ứng dụng Servlet/MVC. Ở các phiên bản khác, đối chiếu tài liệu tương ứng để biết chính xác tên property và hành vi auto-configuration.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **registration ID** và **provider ID** khác nhau về chức năng.
2. Khai báo registration có tên tùy ý và liên kết với provider qua `registration.<id>.provider`.
3. Dùng `provider.<providerId>.issuer-uri` để cấu hình OIDC discovery hoặc khai báo endpoint thủ công khi cần.
4. Thiết lập nhiều registrations dùng chung một provider, đồng thời giữ riêng client ID, client secret, scope và redirect URI.
5. Phân biệt cấu hình provider được định nghĩa trong YAML với những provider phổ biến mà Spring Security có cấu hình mặc định.
6. Nhận biết ảnh hưởng của `registrationId` lên URL bắt đầu đăng nhập, callback, và việc tìm authorized client.
7. Chẩn đoán lỗi do alias sai, thiếu thông số provider, issuer URI không khớp hoặc dùng nhầm cấu hình giữa các tenant.

## 2. Bức tranh tổng thể: registration và provider kết nối với nhau thế nào?

Trong cấu hình Spring Boot, hai nhánh properties liên quan trực tiếp:

~~~text
spring.security.oauth2.client
├── registration
│   └── <registrationId>
│       ├── provider: <providerId>    <-- khóa liên kết
│       ├── client-id: ...
│       ├── client-secret: ...
│       ├── authorization-grant-type: authorization_code
│       ├── redirect-uri: ...
│       └── scope: ...
└── provider
    └── <providerId>
        ├── issuer-uri: ...            # thường dùng cho OIDC
        ├── authorization-uri: ...     # có thể khai báo tường minh
        ├── token-uri: ...
        ├── jwk-set-uri: ...
        ├── user-info-uri: ...
        └── user-name-attribute: ...
~~~

Ví dụ, nếu registration có ID `web` và provider có ID `company-idp`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web:
            provider: company-idp
            client-id: web-client
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company-idp:
            issuer-uri: https://identity.example.test/realms/training
~~~

Dòng `provider: company-idp` mang ý nghĩa: **registration `web` sử dụng cấu hình provider có khóa `company-idp`**. Nó không có nghĩa Client có tên `company-idp`, và cũng không yêu cầu đường dẫn login phải chứa chuỗi `company-idp`.

Với cấu hình này:

- **Registration ID:** `web`.
- **Provider ID:** `company-idp`.
- **Client ID đăng ký tại OP:** `web-client`.
- **Issuer URI:** `https://identity.example.test/realms/training`.
- **URL bắt đầu đăng nhập mặc định:** `/oauth2/authorization/web`.
- **URL callback mặc định:** `/login/oauth2/code/web`.

Ba tên `web`, `company-idp` và `web-client` là ba định danh khác nhau, phục vụ ba mục đích khác nhau.

### 2.1. Sơ đồ ánh xạ

~~~mermaid
flowchart LR
    subgraph REG["Client registrations trong ứng dụng"]
        W["registration.web<br/>client-id: web-client<br/>provider: company-idp"]
        A["registration.admin<br/>client-id: admin-client<br/>provider: company-idp"]
    end
    subgraph PROV["Provider configuration trong ứng dụng"]
        P["provider.company-idp<br/>issuer-uri: https://identity.example.test/realms/training"]
    end
    OP["OpenID Provider thực tế"]
    W -->|"provider ID"| P
    A -->|"cùng provider ID"| P
    P -->|"discovery/authorization/token"| OP
~~~

Mỗi **registration** đại diện cho một cấu hình Client. Một **provider configuration** có thể được nhiều registrations tham chiếu nếu chúng thực sự dùng chung nhà cung cấp và cùng thông số giao thức tương ứng.

### 2.2. Các tên thường bị nhầm

| Tên | Nằm ở đâu | Mục đích | Ví dụ |
|---|---|---|---|
| `registrationId` | Khóa dưới `registration` | Spring Security định danh một Client registration; dùng chọn login và authorized client | `web` |
| `providerId` | Giá trị `registration.web.provider` và khóa dưới `provider` | Chọn bộ cấu hình provider để liên kết với registration | `company-idp` |
| `client-id` | `registration.web.client-id` | Định danh Client mà Authorization Server/OP đã đăng ký | `web-client` |
| `issuer-uri` | `provider.company-idp.issuer-uri` | Định danh issuer của OP; hỗ trợ discovery và kiểm tra issuer | `https://identity.example.test/realms/training` |
| `redirect-uri` | `registration.web.redirect-uri` | Callback mà Client nhận authorization response | `{baseUrl}/login/oauth2/code/{registrationId}` |
| `scope` | `registration.web.scope` | Phạm vi quyền/claim mà registration yêu cầu | `openid`, `profile` |

**Provider ID là một bí danh cấu hình do ứng dụng đặt**, không phải bằng chứng danh tính, không phải issuer URI, không phải OAuth scope và cũng không phải hostname bắt buộc trùng với nhà cung cấp.

## 3. Vì sao tách registration và provider?

Nếu chỉ có một Client và một OP, bạn có thể đặt cùng ID cho cả hai nhóm và khó nhận ra sự phân biệt. Khi dự án phát triển, hai nhóm mô tả những thứ thay đổi với nhịp khác nhau.

**Thông số của registration** thường phụ thuộc từng ứng dụng hoặc từng mục đích truy cập:

- Client ID và Client secret do OP cấp cho một đăng ký cụ thể.
- Grant type, ví dụ `authorization_code` hoặc `client_credentials` theo thiết kế.
- Callback URI cho ứng dụng đăng nhập.
- Scopes cần xin, có thể khác nhau giữa web UI và công cụ vận hành.
- Client authentication method và những tùy chọn riêng cho từng Client.

**Thông số của provider** mô tả nơi Client thực hiện giao thức:

- Authorization endpoint nhận yêu cầu ủy quyền qua trình duyệt.
- Token endpoint trao đổi authorization code hoặc grant thích hợp.
- JWK Set URI phục vụ kiểm tra chữ ký JWT/ID token khi áp dụng.
- UserInfo endpoint và tên thuộc tính định danh đối với OAuth2/OIDC user.
- Issuer URI định danh OP và cho phép tải metadata khi hỗ trợ discovery.

Nếu hai registrations dùng cùng OP, chúng có thể dùng chung issuer và endpoint nhưng vẫn cần **client ID/secret/scope/redirect** khác nhau. Nếu hai OP có issuer khác nhau, chúng không nên cùng tham chiếu một provider config chỉ vì cùng chạy trên một domain hoặc cùng phần mềm.

### 3.1. Quy tắc quyết định nhóm thuộc tính

Tự hỏi:

- “Giá trị này thay đổi khi tôi tạo thêm một Client mới ở **cùng OP**?” Nếu có, thường thuộc **registration**.
- “Giá trị này mô tả OP/Authorization Server mà nhiều Client cùng liên hệ?” Nếu có, thường thuộc **provider**.
- “Giá trị này là cách Spring Security đặt tên cấu hình trong ứng dụng?” Đây là **registrationId** hoặc **providerId**; không nhất thiết xuất hiện nguyên văn ở hệ thống IdP.

Tách rạch ròi như vậy giảm việc sao chép endpoint và giúp thay đổi cấu hình an toàn hơn.

## 4. Cú pháp liên kết chính xác trong application.yml

Hãy xem cấu hình một Client tên `sales-portal` dùng OP nội bộ có bí danh `corporate-oidc`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          sales-portal:
            provider: corporate-oidc
            client-id: sales-web
            client-secret: ${SALES_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://login.example.test/realms/employees
~~~

Đọc cấu hình theo đúng thứ tự:

1. `registration.sales-portal` nói rằng ứng dụng có một Client registration tên `sales-portal`.
2. Bên trong registration, `provider: corporate-oidc` chọn cấu hình provider theo ID `corporate-oidc`.
3. `provider.corporate-oidc.issuer-uri` nói OP tương ứng có issuer `https://login.example.test/realms/employees`.
4. `client-id` và `client-secret` xác định Client cụ thể đã đăng ký với OP đó.
5. `scope` có `openid`, vì vậy registration này yêu cầu OIDC khi dùng Authorization Code login.
6. `redirect-uri` chứa placeholder `{registrationId}`, nên callback cho registration này mặc định kết thúc bằng `/sales-portal`.

Mối liên kết là **giá trị chuỗi trùng khớp giữa `provider: corporate-oidc` và khóa `provider.corporate-oidc`**. Bạn có thể đổi bí danh này thành `central-identity` nếu đổi **cả hai nơi**, miễn issuer và những thông số khác vẫn đúng.

### 4.1. Tên provider ID có cần giống issuer hoặc tên sản phẩm?

Không. Ví dụ cả ba giá trị dưới đây có thể khác nhau:

~~~yaml
registration:
  user-login:
    provider: main-sso
    client-id: training-frontend
provider:
  main-sso:
    issuer-uri: https://idp.example.test/realms/company
~~~

- `user-login` là khóa registration trong ứng dụng.
- `main-sso` là khóa provider config trong ứng dụng.
- `https://idp.example.test/realms/company` là issuer mà OP công bố.

Dùng tên có ý nghĩa và nhất quán; đừng gán ý nghĩa giao thức cho chuỗi `main-sso`. Chính **issuer URI**, các endpoint và các quy tắc xác minh OIDC mới định hình quan hệ tin cậy thực tế.

### 4.2. Dùng application.properties thay YAML

Cùng cấu hình có thể biểu diễn bằng properties:

~~~properties
spring.security.oauth2.client.registration.sales-portal.provider=corporate-oidc
spring.security.oauth2.client.registration.sales-portal.client-id=sales-web
spring.security.oauth2.client.registration.sales-portal.client-secret=${SALES_OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.sales-portal.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.sales-portal.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
spring.security.oauth2.client.registration.sales-portal.scope=openid,profile,email
spring.security.oauth2.client.provider.corporate-oidc.issuer-uri=https://login.example.test/realms/employees
~~~

Ở hai định dạng, cấu trúc logic là như nhau. Đặc biệt lưu ý cấp `client.registration.*.provider` và cấp `client.provider.*` khác nhau: thiếu một cấp có thể khiến binding sai hoặc registration không tìm thấy cấu hình mong muốn.

## 5. Trường hợp registration ID trùng provider ID

Trong một ứng dụng nhỏ, có thể khai báo như sau:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          internal:
            client-id: internal-web
            client-secret: ${INTERNAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          internal:
            issuer-uri: https://id.example.test/realms/internal
~~~

Khi một registration tên `internal` có provider configuration cũng mang ID `internal`, Spring Boot có thể liên kết các thông số provider theo quy ước cùng tên. Điều này giúp cấu hình gọn cho một Client.

Tuy vậy, **đặt `provider: internal` tường minh là cách diễn đạt rõ ràng hơn khi dạy hoặc bảo trì hệ thống**:

~~~yaml
registration:
  internal:
    provider: internal
    client-id: internal-web
    client-secret: ${INTERNAL_CLIENT_SECRET}
    authorization-grant-type: authorization_code
    scope: [openid, profile]
provider:
  internal:
    issuer-uri: https://id.example.test/realms/internal
~~~

Cả hai nhóm có cùng ID trong ví dụ, nhưng chúng vẫn là **hai vai trò cấu hình độc lập**. Không nên suy luận rằng bất cứ provider ID nào được đặt cũng tự tạo ra một Client registration; ứng dụng chỉ có registration khi khai báo hoặc cung cấp registration qua repository tương ứng.

## 6. Đặt registration ID khác provider ID: alias tường minh

Đây là trường hợp làm nổi bật vai trò của thuộc tính `provider`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          backoffice-login:
            provider: keycloak-main
            client-id: backoffice-web
            client-secret: ${BACKOFFICE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          keycloak-main:
            issuer-uri: https://sso.example.test/realms/staff
~~~

Đăng nhập của Client này bắt đầu tại:

~~~http
GET /oauth2/authorization/backoffice-login HTTP/1.1
Host: localhost:8080
~~~

Callback thường về:

~~~text
http://localhost:8080/login/oauth2/code/backoffice-login
~~~

Giá trị `keycloak-main` **không phải** registrationId, vì vậy:

- Không giả định đường dẫn bắt đầu login là `/oauth2/authorization/keycloak-main`.
- Không giả định callback là `/login/oauth2/code/keycloak-main`.
- Không viết mã tìm registration bằng `findByRegistrationId("keycloak-main")` khi registration thực tế có ID `backoffice-login`.

Nếu ứng dụng có custom login page, liên kết cần dùng `registrationId`:

~~~html
<a href="/oauth2/authorization/backoffice-login">
  Đăng nhập khu vực nội bộ
</a>
~~~

Có thể đổi tên provider alias mà không đổi liên kết login trên UI, miễn giữ nguyên registrationId và sửa ánh xạ cấu hình. Nhưng đổi **registrationId** có thể ảnh hưởng cả login URL, callback đã đăng ký tại OP, mã nguồn tham chiếu registration và các bản ghi authorized client.

## 7. Một provider được nhiều registrations sử dụng

Một công ty có thể tạo hai Client ở cùng một OP: `customer-portal` cho web khách hàng và `support-console` cho ứng dụng hỗ trợ. Cả hai giao tiếp với cùng issuer nhưng có client ID, secret, scope và callback khác nhau.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          customer-portal:
            provider: shared-sso
            client-id: customer-portal-web
            client-secret: ${CUSTOMER_PORTAL_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]

          support-console:
            provider: shared-sso
            client-id: support-console-web
            client-secret: ${SUPPORT_CONSOLE_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, support.read]

        provider:
          shared-sso:
            issuer-uri: https://identity.example.test/realms/company
~~~

Lúc này hai registrations dùng cùng cấu hình provider, nhưng khác dữ liệu Client:

| Thuộc tính | `customer-portal` | `support-console` |
|---|---|---|
| `provider` | `shared-sso` | `shared-sso` |
| `client-id` | `customer-portal-web` | `support-console-web` |
| Biến secret | `CUSTOMER_PORTAL_SECRET` | `SUPPORT_CONSOLE_SECRET` |
| Scope | `openid profile email` | `openid profile support.read` |
| Login URL | `/oauth2/authorization/customer-portal` | `/oauth2/authorization/support-console` |
| Callback URL | `/login/oauth2/code/customer-portal` | `/login/oauth2/code/support-console` |
| Issuer | Giống nhau | Giống nhau |

**Để chạy được**, mỗi Client phải được đăng ký đúng tại OP với các redirect URIs, scopes và chính sách tương ứng. Việc hai cấu hình cùng chỉ vào một provider ID không làm OP tự tạo thêm Client.

### 7.1. Tại sao thiết kế này có ích?

- Thay đổi issuer hoặc cấu hình endpoint chung chỉ cần chỉnh một provider configuration.
- Ứng dụng có thể chọn registration theo nhu cầu đăng nhập/ủy quyền.
- Client credentials không bị trộn lẫn, dù endpoint OAuth 2.0/OP giống nhau.
- Khi một registration cần thêm quyền API, bạn thay đổi scope ở registration đó mà không tự nâng quyền cho registration còn lại.
- Thông tin authorized client trong Spring Security gắn với registration ID và principal, giúp phân biệt quyền/token tương ứng với từng Client.

**Chú ý:** scope `support.read` trong ví dụ là giá trị giả định. Scope này chỉ có tác dụng khi OP đã cấu hình hỗ trợ và API thực tế hiểu/kiểm tra quyền đó. Scope không mặc nhiên biến người dùng thành nhân viên hỗ trợ.

### 7.2. Khi nào không được tái sử dụng cùng provider?

Không nên dùng `shared-sso` cho hai hệ thống chỉ vì cả hai đều chạy Keycloak hoặc có chung hostname. Nếu chúng thuộc **hai realm/tenant có issuer khác nhau**, cần đặt provider config riêng:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employees:
            provider: employees-oidc
            client-id: employees-web
            client-secret: ${EMPLOYEES_SECRET}
            scope: [openid, profile]

          partners:
            provider: partners-oidc
            client-id: partners-web
            client-secret: ${PARTNERS_SECRET}
            scope: [openid, profile]

        provider:
          employees-oidc:
            issuer-uri: https://identity.example.test/realms/employees

          partners-oidc:
            issuer-uri: https://identity.example.test/realms/partners
~~~

Hai issuer chỉ khác path nhưng là hai định danh OP khác nhau. Điều đó ảnh hưởng discovery, xác minh `iss` trong ID token, khóa JWK, chính sách claim và ranh giới danh tính. **Provider ID là alias cấu hình; bảo đảm không trộn lẫn thông số OP mới là yêu cầu bảo mật.**

## 8. Provider ID liên hệ thế nào với OIDC discovery?

Với OIDC, cấu hình provider thường gọn nhất khi dùng `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          enterprise-idp:
            issuer-uri: https://login.example.test/realms/training
~~~

Khi Spring Boot/Spring Security xây dựng `ClientRegistration` cho registration liên kết với provider này, thư viện có thể sử dụng **OpenID Provider metadata discovery** để biết endpoint cần thiết. OP cần công bố metadata phù hợp, thường theo đường dẫn `.well-known/openid-configuration` được xác định từ issuer và quy tắc discovery áp dụng.

Metadata có thể công bố, tùy provider:

- `issuer`;
- `authorization_endpoint`;
- `token_endpoint`;
- `jwks_uri`;
- `userinfo_endpoint`;
- những thuật toán ký, phương thức xác thực Client và chức năng khác mà OP hỗ trợ.

Spring Security dùng thông tin cần thiết để tạo cấu hình Client phù hợp. Không cần sao chép thủ công tất cả endpoint nếu discovery đã đủ và đúng.

### 8.1. Provider ID không tham gia xác minh issuer thay cho issuer URI

Giả sử:

~~~yaml
registration:
  admin:
    provider: main-idp
    client-id: admin-web
    scope: [openid]
provider:
  main-idp:
    issuer-uri: https://id.example.test/realms/staff
~~~

ID `main-idp` chỉ là khóa nội bộ. ID token hợp lệ cần được xử lý theo các kiểm tra OIDC, bao gồm issuer thực tế phải khớp `https://id.example.test/realms/staff`. Việc đặt provider ID thành `staff` hay `main-idp` không thay đổi issuer trong token.

### 8.2. Đường dẫn discovery và hostname

Hãy dùng **issuer do OP công bố chính thức**, không đoán từ đường dẫn giao diện quản trị hoặc một URL token endpoint. Ví dụ trong hệ thống dùng reverse proxy:

- Ứng dụng biết OP qua URL công khai `https://login.example.test/realms/staff`.
- Metadata và ID token cũng dùng issuer công khai này.
- Một URL nội bộ như `http://identity-service:8080/realms/staff` có thể cho phép kết nối mạng, nhưng nếu nó không trùng issuer mà OP công bố thì có thể tạo lỗi xác minh.

Cần đảm bảo đồng nhất scheme, host, port (nếu có) và path theo cấu hình OP. Với môi trường thực dùng HTTPS và xác minh TLS đúng cách.

### 8.3. Discovery xảy ra lúc nào?

Việc dựng `ClientRegistration` từ issuer URI có thể yêu cầu tải provider metadata trong quá trình khởi tạo ứng dụng, tùy cấu hình và phiên bản. Nếu OP chưa sẵn sàng, DNS/TLS lỗi hoặc metadata không hợp lệ, ứng dụng có thể lỗi ngay lúc khởi động hoặc khi chuẩn bị registration.

Vì vậy, khi thấy lỗi provider initialization, không nên chỉ tìm trong `SecurityFilterChain`; trước hết kiểm tra kết nối đến issuer và metadata được công bố.

## 9. Provider không hỗ trợ OIDC discovery: khai báo endpoint tường minh

Không phải Authorization Server nào cũng là OpenID Provider. Có những OAuth 2.0 provider chỉ hỗ trợ cấp quyền truy cập API, dùng endpoint và API lấy hồ sơ riêng.

Trong trường hợp không có OIDC discovery phù hợp, Spring Boot có thể nhận endpoint từ nhánh `provider`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-account:
            provider: legacy-auth
            client-id: legacy-web
            client-secret: ${LEGACY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [account.read]
        provider:
          legacy-auth:
            authorization-uri: https://auth.partner.example/authorize
            token-uri: https://auth.partner.example/token
            user-info-uri: https://api.partner.example/user
            user-name-attribute: id
~~~

Đây là một **ví dụ OAuth 2.0 Login không mặc nhiên là OIDC**; nó chỉ chạy nếu nhà cung cấp thực sự có các endpoint, định dạng user profile và hành vi phù hợp với Spring Security OAuth2 Login. Tên và URL ở đây là giả định cho bài học.

Sự khác biệt:

- `registration.legacy-account.provider: legacy-auth` vẫn chỉ làm nhiệm vụ liên kết.
- `provider.legacy-auth.authorization-uri` là endpoint người dùng được điều hướng đến.
- `token-uri` là nơi Client đổi code lấy token.
- `user-info-uri` và `user-name-attribute` giúp Client lấy/định danh `OAuth2User` theo contract riêng của provider.
- Không có scope `openid` và ID token OIDC, nên không được mô tả đây là OIDC authentication chỉ vì Spring Security có thể tạo `Authentication` từ dữ liệu nhà cung cấp.

Nếu bạn đang triển khai **OIDC**, nên ưu tiên `issuer-uri` để dùng metadata và quy tắc OIDC phù hợp. Chỉ cấu hình endpoints thủ công khi có yêu cầu cụ thể và hiểu rõ giao thức của nhà cung cấp.

### 9.1. Trường hợp cần JWK Set URI

Với OIDC hoặc những kiểu JWT xác minh qua JWK, provider config có thể liên quan đến `jwk-set-uri`. Tuy nhiên, khi discovery đã cung cấp `jwks_uri` phù hợp, không cần tự nhập URI một lần nữa chỉ để “đủ cấu hình”.

Cũng cần phân biệt JWK Set dùng xác minh ID token cho **Client** với JWK/JWT verification của **Resource Server** nhận access token. Hai thành phần có thể lấy khóa từ cùng OP nhưng kiểm tra token theo mục tiêu và audience khác nhau.

## 10. Provider mặc định phổ biến và cách đặt alias

Spring Security có một số provider phổ biến với bộ thông số mặc định được nhận diện theo provider ID, chẳng hạn `google`, `github`, `facebook` hoặc `okta` tùy khả năng và phiên bản thư viện. Trong dự án Spring Boot, bạn có thể tận dụng bộ cấu hình có sẵn nếu trường hợp tương ứng được hỗ trợ.

Ví dụ muốn đặt registration tên `staff-google` nhưng dùng provider mặc định `google`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff-google:
            provider: google
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope: [openid, profile, email]
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

Ở đây:

- `staff-google` là **registration ID** và xuất hiện trong login URL `/oauth2/authorization/staff-google`.
- `google` là **provider ID** được dùng để chọn các giá trị provider phổ biến do thư viện nhận diện.
- `client-id` và `client-secret` vẫn là dữ liệu Client đã được đăng ký với Google.
- Callback cần đăng ký chính xác với nhà cung cấp theo URL của registration.

Khi dùng provider có cấu hình mặc định, bạn có thể không cần nhánh `provider.google` riêng nếu bộ giá trị mặc định đã đáp ứng. Khi muốn thay đổi cấu hình/endpoint hoặc dùng một provider không có trong danh sách mặc định, hãy khai báo nhánh provider tương ứng.

**Lưu ý:** không nên tự suy rằng provider có sẵn nào cũng hỗ trợ OIDC hoặc scope `openid`. Các nhà cung cấp có giao thức và tính năng khác nhau; ví dụ GitHub OAuth 2.0 Login truyền thống dùng API người dùng theo mô hình OAuth 2.0 và không tự trở thành OIDC Login chỉ vì đặt `provider: github`.

### 10.1. Alias mặc định và alias tùy chỉnh

| Nhu cầu | Registration ID | Provider ID | Nguồn thông số provider |
|---|---|---|---|
| Dùng Google với tên login riêng | `staff-google` | `google` | Provider phổ biến nếu thư viện hỗ trợ |
| Dùng OIDC nội bộ | `web` | `company-idp` | `provider.company-idp.issuer-uri` |
| Dùng hai Clients ở cùng OP | `portal`, `reporting` | `company-idp` | Cùng một provider config |
| Dùng hai tenants khác issuer | `staff`, `partner` | `staff-idp`, `partner-idp` | Hai provider configs riêng |

Tự đặt provider ID tùy ý **không** khiến Spring Security biết các URL OAuth 2.0 chỉ từ tên đó. Một alias mới như `corp-sso` cần cấu hình endpoint hoặc issuer URI hợp lệ, trừ khi nó được liên kết đến bộ provider có sẵn theo cơ chế được hỗ trợ.

## 11. Registration ID ảnh hưởng trực tiếp đến URL và trạng thái OAuth2 Client

Với cấu hình web Servlet phổ biến, Spring Security cung cấp hai đường dẫn mặc định:

| Bước | Mẫu URL |
|---|---|
| Bắt đầu login/ủy quyền | `/oauth2/authorization/{registrationId}` |
| Nhận authorization response | `/login/oauth2/code/{registrationId}` |

Ví dụ:

~~~yaml
registration:
  console:
    provider: central-oidc
    client-id: console-client
    client-secret: ${CONSOLE_SECRET}
    redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
    scope: [openid, profile]
provider:
  central-oidc:
    issuer-uri: https://sso.example.test/realms/core
~~~

Thì:

~~~text
Bắt đầu:  GET http://localhost:8080/oauth2/authorization/console
Callback:     http://localhost:8080/login/oauth2/code/console
~~~

Trình duyệt đi qua Authorization Server được xác định từ `provider.central-oidc`, nhưng các đường dẫn nội bộ trong Client sử dụng **`console`**.

Khi tạo custom login page, hãy dùng:

~~~html
<a href="/oauth2/authorization/console">Đăng nhập Console</a>
~~~

Nếu người học dùng nhầm provider ID:

~~~html
<!-- Không đúng nếu không có registration tên central-oidc -->
<a href="/oauth2/authorization/central-oidc">Đăng nhập Console</a>
~~~

Lỗi xuất hiện vì Spring Security cần tìm `ClientRegistration` theo `registrationId`, chứ không phải lấy khóa provider rồi tự suy ra Client.

### 11.1. Authorized client được xác định theo registration ID

Sau khi OAuth 2.0 Client được ủy quyền, Spring Security dùng khái niệm `OAuth2AuthorizedClient` để giữ thông tin Client registration và token được cấp. Thông tin này thường được tra theo **registration ID** cùng danh tính principal (hoặc ngữ cảnh lưu trữ phù hợp).

Vì thế, hai registrations tham chiếu chung provider vẫn có thể có authorized client và bộ token riêng:

~~~text
registrationId = customer-portal  --> credentials/scopes/tokens của customer-portal
registrationId = support-console  --> credentials/scopes/tokens của support-console
providerId     = shared-sso       --> issuer/endpoints dùng chung
~~~

Việc dùng chung provider **không làm hợp nhất quyền hoặc access token** của hai Clients. Phải lấy token đúng registration và kiểm tra quyền phù hợp với API đích.

### 11.2. Đổi registrationId không chỉ là sửa một tên trong YAML

Nếu đổi `console` thành `operations`:

- URL `/oauth2/authorization/console` phải đổi thành `/oauth2/authorization/operations`.
- Callback mặc định trở thành `/login/oauth2/code/operations`; OP có thể cần cập nhật redirect URI.
- Mã nguồn tham chiếu `@RegisteredOAuth2AuthorizedClient("console")` hoặc tìm registration qua repository phải đổi theo.
- Dữ liệu authorized client được lưu theo registration ID cũ có thể cần xử lý theo chính sách ứng dụng.

Ngược lại, đổi riêng provider alias `central-oidc` thành `company-sso` (và sửa khóa provider tương ứng) không bắt buộc đổi URL login nếu `registrationId` vẫn giữ nguyên.

## 12. Cấu hình HTTP Security để sử dụng registration đã liên kết

Các thuộc tính provider và registration chỉ định nghĩa **thông số OAuth 2.0 Client**. Ứng dụng còn phải bật cơ chế login trong HTTP Security nếu tự định nghĩa `SecurityFilterChain`.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Khi browser truy cập trang được bảo vệ, Spring Security có thể bắt đầu luồng OIDC login. Khi người dùng chọn `/oauth2/authorization/console`, Spring Security tìm `ClientRegistration` có ID `console`. Registration ấy đã được xây dựng bằng dữ liệu Client và provider đã liên kết.

Trong một ứng dụng chỉ dựa vào Spring Boot auto-configuration, Boot có thể tự cung cấp default chain khi đủ điều kiện. Nếu bạn khai báo bean `SecurityFilterChain` riêng, đừng mặc định rằng `oauth2Login()` vẫn được bật; hãy cấu hình nó tường minh ở chain xử lý đăng nhập.

### 12.1. Một registration, một provider: chuỗi xử lý

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant C as Spring Security Client
    participant R as ClientRegistrationRepository
    participant OP as OpenID Provider
    U->>B: Chọn Đăng nhập Console
    B->>C: GET /oauth2/authorization/console
    C->>R: findByRegistrationId("console")
    R-->>C: ClientRegistration(console), provider details
    C-->>B: 302 tới authorization endpoint của OP
    B->>OP: Authorization request với client_id và scope
    OP-->>B: Redirect về /login/oauth2/code/console?code=...&state=...
    B->>C: Gửi callback
    C->>OP: Trao đổi code tại token endpoint
    OP-->>C: Token response theo cấu hình OP/Client
    C->>C: Xử lý OIDC, tạo Authentication/phiên
    C-->>B: Chuyển đến trang ban đầu
~~~

Tại thời điểm chạy, Spring Security làm việc với **`ClientRegistration` và provider details đã được giải quyết**. Provider ID là mối nối trong cấu hình; nó không phải thông tin danh tính mà OP trả về cho Client.

## 13. Kiểm tra mapping trong mã Java

Khi cấu hình nhiều registrations, có thể kiểm tra một `ClientRegistration` thông qua `ClientRegistrationRepository`. Đây là bước chẩn đoán giúp xác nhận ứng dụng đã bind đúng dữ liệu từ YAML.

Ví dụ Spring Boot:

~~~java
import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class ClientRegistrationDiagnostics {

    @Bean
    ApplicationRunner showSafeClientConfiguration(
            ClientRegistrationRepository registrations) {

        return args -> {
            for (String id : List.of("customer-portal", "support-console")) {
                ClientRegistration registration =
                    registrations.findByRegistrationId(id);

                if (registration == null) {
                    throw new IllegalStateException(
                        "Missing OAuth2 registration: " + id);
                }

                System.out.println("registrationId=" +
                    registration.getRegistrationId());
                System.out.println("issuer=" +
                    registration.getProviderDetails().getIssuerUri());
                System.out.println("authorizationUri=" +
                    registration.getProviderDetails().getAuthorizationUri());
            }
        };
    }
}
~~~

Đoạn này chỉ in các giá trị chẩn đoán không phải bí mật, dùng trong môi trường phát triển. Không in client secret, access token, refresh token, authorization code hoặc cookie. Với provider OAuth2 không khai báo issuer, `getIssuerUri()` có thể không có giá trị; endpoint authorization/token mới là dữ liệu cần kiểm tra.

**Điểm kỹ thuật:** `providerId` trong YAML là khóa để Spring Boot kết hợp properties, chứ không nhất thiết có một phương thức `ClientRegistration.getProviderId()`. Sau khi bind, `ClientRegistration` mang `registrationId`, client ID, scope, redirect URI và `ProviderDetails` tương ứng. Khi cần biết alias provider gốc, đọc cấu hình ứng dụng đã khai báo thay vì giả định có getter ấy.

### 13.1. Điều gì xảy ra nếu ứng dụng tự tạo ClientRegistrationRepository?

Nếu ứng dụng tự khai báo bean `ClientRegistrationRepository`, Spring Boot có thể nhường quyền cung cấp repository mặc định từ properties. Khi đó:

- `application.yml` vẫn có thể chứa nhánh `registration`/`provider`, nhưng không thể mặc định rằng repository thủ công đã tải các cấu hình đó.
- Các registration tìm thấy tại runtime phụ thuộc implementation của bean do ứng dụng cung cấp.
- Cần xác định từng `ClientRegistration` được dựng với issuer/endpoints/scopes đúng, nhất là khi cấu hình động theo tenant.

Vì vậy, khi mã Java tìm không ra `registrationId` dù YAML đúng, hãy kiểm tra trước xem có custom repository nào thay thế auto-configuration hay không.

## 14. Lỗi thường gặp do liên kết sai provider ID

### 14.1. Giá trị provider không trùng khóa đã khai báo

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: employee-sso
            client-id: portal-client
            client-secret: ${PORTAL_SECRET}
            scope: [openid]
        provider:
          employees-sso:
            issuer-uri: https://id.example.test/realms/employees
~~~

Registration chọn `employee-sso`, nhưng nhánh provider có ID `employees-sso`. Hai chuỗi khác nhau do thừa chữ `s`. Đây là **lỗi ánh xạ cấu hình**, không phải lỗi tài khoản người dùng.

Ứng dụng có thể thất bại khi dựng registration hoặc không lấy được provider details cần thiết, tùy điều kiện và phiên bản; không nên dựa vào một thông báo ngoại lệ cố định. Sửa thành cùng một ID:

~~~yaml
registration:
  portal:
    provider: employees-sso
    client-id: portal-client
    client-secret: ${PORTAL_SECRET}
    scope: [openid]
provider:
  employees-sso:
    issuer-uri: https://id.example.test/realms/employees
~~~

### 14.2. Nhầm provider ID với registration ID khi tạo link login

Có registration:

~~~yaml
registration:
  intranet:
    provider: company-sso
    client-id: intranet-web
    scope: [openid]
~~~

Liên kết đúng cho registration này là `/oauth2/authorization/intranet`, không phải `/oauth2/authorization/company-sso` trừ khi thực sự có thêm registration tên `company-sso`.

### 14.3. Cấu hình issuer ở sai nhánh

Ví dụ sai về mặt tổ chức:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          intranet:
            provider: company-sso
            client-id: intranet-web
            issuer-uri: https://id.example.test/realms/company
~~~

`issuer-uri` dành cho provider metadata, nên cấu hình cần đặt dưới `spring.security.oauth2.client.provider.company-sso.issuer-uri`. Việc đặt tùy tiện dưới registration không khiến Spring Boot tự hiểu đó là provider configuration đúng.

### 14.4. Cho hai tenant khác issuer cùng provider ID

Ví dụ `sales` và `hr` thuộc hai realm có issuer khác nhau, nhưng đều dùng:

~~~yaml
registration:
  sales:
    provider: company
  hr:
    provider: company
provider:
  company:
    issuer-uri: https://id.example.test/realms/sales
~~~

Khi đó cấu hình `hr` lại dựa trên issuer của `sales`. Nếu token/metadata thuộc realm khác, luồng có thể lỗi hoặc cho thấy ranh giới tin cậy đã được thiết kế sai. Hãy tạo provider riêng cho từng issuer thật và trỏ mỗi registration đúng provider của nó.

### 14.5. Có provider, không có registration

Chỉ khai báo:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-sso:
            issuer-uri: https://id.example.test/realms/company
~~~

không đủ để Spring Security có Client registration tên `company-sso` cho login. Cần ít nhất một registration với client ID và các thuộc tính bắt buộc phù hợp, liên kết đến provider đó.

### 14.6. Không có openid nhưng mong đợi OIDC principal

Một registration có provider OIDC nhưng scope chỉ là `profile` hoặc quyền API không mặc nhiên yêu cầu giao thức OIDC login. Để đăng nhập bằng OIDC, registration cần scope `openid` và OP phải xử lý OIDC đúng chuẩn.

`provider: company-sso` chỉ chọn bộ cấu hình provider. Nó **không tự thêm scope `openid`**, không tự cho biết người dùng có claim nào và không tự bật `oauth2Login()` trong custom filter chain.

### 14.7. Redirect URI không khớp OP

Khi registration ID đổi từ `portal` sang `portal-v2`, callback mặc định cũng đổi. Nếu IdP chỉ cho phép `/login/oauth2/code/portal`, yêu cầu mới với `/login/oauth2/code/portal-v2` có thể bị từ chối.

Lúc này issuer/provider mapping có thể đúng; sai nằm ở **registration và cấu hình redirect URI tại OP**. Phải so sánh đầy đủ scheme, host, port và path, đồng thời xem reverse proxy có làm sai public base URL hay không.

### 14.8. OP không hỗ trợ hoặc không công bố metadata đúng

Nếu `issuer-uri` trỏ vào đường dẫn sai, metadata không truy cập được, TLS lỗi hoặc OP không hỗ trợ discovery, Spring Boot/Spring Security có thể không dựng được registration. Hãy kiểm tra URL issuer được OP công bố và metadata thật; không đổi `providerId` ngẫu nhiên để thử sửa lỗi kết nối.

## 15. Bài thực hành A — Liên kết một registration với provider tùy chỉnh

**Mục tiêu:** làm chủ cú pháp `registration.<id>.provider`.

**Điều kiện:** có một OP hỗ trợ OIDC trong môi trường thử nghiệm, một Client đã đăng ký tại OP và ứng dụng Spring Boot MVC với OAuth2 Client starter.

**Cấu hình:**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          course-ui:
            provider: training-sso
            client-id: course-ui-web
            client-secret: ${COURSE_UI_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          training-sso:
            issuer-uri: https://identity.example.test/realms/training
~~~

Địa chỉ là minh họa; để chạy thật phải thay bằng OP đang sử dụng và client ID/secret được cấp.

**Các bước thực hiện:**

1. Đối chiếu `provider: training-sso` với khóa `provider.training-sso`.
2. Kiểm tra issuer URI trong cấu hình khớp metadata OP.
3. Đảm bảo OP chấp nhận callback `http://localhost:8080/login/oauth2/code/course-ui` nếu ứng dụng chạy tại `http://localhost:8080`.
4. Bật `oauth2Login()` trong chain bảo mật nếu ứng dụng tự cấu hình chain.
5. Mở `http://localhost:8080/oauth2/authorization/course-ui` để bắt đầu đăng nhập.
6. Quan sát redirect tới OP và callback về Client; sau login kiểm tra principal thông qua endpoint an toàn.
7. Không chép token, code hoặc cookie thực vào tài liệu lab.

**Kết quả mong đợi:** `course-ui` được Spring Security tìm như registration ID, còn các endpoints/issuer đến từ provider `training-sso`. Provider ID không xuất hiện như registration ID trong login URL mặc định.

**Câu hỏi:** nếu đổi `training-sso` thành `training-oidc` ở cả hai vị trí, login URL có cần đổi không? Nếu đổi `course-ui` thành `course-portal` thì thành phần nào phải cập nhật?

## 16. Bài thực hành B — Tái sử dụng một provider cho hai registrations

**Mục tiêu:** thấy rõ Client identity khác nhau nhưng endpoint/issuer có thể dùng chung.

**Chuẩn bị:** đăng ký hai Clients `learning-web` và `admin-web` ở cùng OP, mỗi Client có secret và callback phù hợp.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          learner:
            provider: training-idp
            client-id: learning-web
            client-secret: ${LEARNING_WEB_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]

          administrator:
            provider: training-idp
            client-id: admin-web
            client-secret: ${ADMIN_WEB_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, admin.read]

        provider:
          training-idp:
            issuer-uri: https://id.example.test/realms/training
~~~

**Các bước thực hiện:**

1. Bổ sung hai link login trỏ đến `/oauth2/authorization/learner` và `/oauth2/authorization/administrator`.
2. Mở lần lượt từng luồng bằng phiên browser riêng để dễ quan sát.
3. Đối chiếu `client_id` trong authorization request (không chia sẻ giá trị nhạy cảm khác) và redirect URI ở mỗi luồng.
4. Sau login, kiểm tra registration ID của authorized client theo tính năng ứng dụng đang dùng.
5. Quan sát issuer và authorization endpoint đều dẫn đến cùng OP.
6. So sánh phạm vi quyền được yêu cầu và thực tế được cấp; không tự suy quyền admin từ scope có tên `admin.read`.

**Kết quả mong đợi:** hai Client registrations dùng chung provider metadata nhưng có client ID, redirect URI và token được quản lý riêng. Tái sử dụng provider config không có nghĩa các Clients có cùng danh tính ứng dụng hoặc cùng quyền truy cập.

## 17. Bài thực hành C — Chủ động gây và khoanh vùng lỗi liên kết

**Mục tiêu:** phân biệt lỗi alias, lỗi registration và lỗi provider/issuer.

Thực hiện từng biến thể riêng trong môi trường lab, sau đó **hoàn nguyên cấu hình** để tránh các lỗi chồng lên nhau.

| Biến thể | Thay đổi có chủ đích | Dấu hiệu cần quan sát | Kết luận |
|---|---|---|---|
| Alias không trùng | `registration.web.provider: oidc-main` nhưng chỉ có `provider.main-oidc` | Khởi tạo registration hoặc discovery/config không thành công | Sai tên khóa liên kết |
| Dùng nhầm login URL | Dùng `/oauth2/authorization/main-oidc` trong khi registration tên `web` | Không tìm thấy registration cho URL yêu cầu | Login URL cần registrationId |
| Issuer URI sai | Trỏ `issuer-uri` tới issuer/realm khác | Discovery/issuer validation có thể thất bại | Provider identity không khớp |
| Callback cũ | Đổi registration ID nhưng chưa sửa URI tại OP | OP từ chối redirect URI hoặc callback không đúng | Cần đồng bộ Client registration và OP |
| Thiếu scope `openid` | Chỉ xin `profile` ở login | Không nhận hành vi `OidcUser` như kỳ vọng | Provider OIDC chưa đủ; cần yêu cầu OIDC đúng |
| Trùng provider cho hai tenants | Hai registrations khác issuer dùng chung provider | Sai endpoint/issuer/claims hoặc xác minh thất bại | Cần provider riêng theo issuer |

Kết quả cụ thể có thể là lỗi khởi động, từ chối tại OP hoặc lỗi trong quá trình login, tùy cách Spring Security/Boot hiện thực và provider được dùng. Mục đích lab là **xác định lớp cấu hình chịu trách nhiệm**, không ghi nhớ một mã lỗi duy nhất.

## 18. Cách quan sát và xử lý sự cố trong Spring Boot

Để chẩn đoán, nên kiểm tra lần lượt **registration ID → provider alias → issuer/endpoints → redirect URI → HTTP Security**.

### 18.1. Kiểm tra cấu hình được bind

Tìm các nhánh:

~~~text
spring.security.oauth2.client.registration.<registrationId>.provider
spring.security.oauth2.client.registration.<registrationId>.client-id
spring.security.oauth2.client.registration.<registrationId>.scope
spring.security.oauth2.client.provider.<providerId>.issuer-uri
~~~

Xác nhận provider ID trùng chính xác với khóa mong muốn. Nếu cấu hình được ghi đè bằng profile hoặc environment variables, kiểm tra nguồn giá trị sau khi binding theo cách an toàn; không in secret ra log.

### 18.2. Kiểm tra provider metadata

Với OIDC, xác định issuer do OP công bố và endpoint discovery tương ứng. Kiểm tra metadata phản hồi đúng issuer, endpoints và JWK Set URI cần thiết. Nếu dùng reverse proxy, xác định OP đang công bố URL công khai hợp lệ.

Không suy đoán metadata chỉ từ provider ID: `corp-sso` là tên do ứng dụng đặt và không thể thay thế URL thực.

### 18.3. Kiểm tra request vào Spring Security

Nếu cấu hình đăng nhập mặc định, đường dẫn `/oauth2/authorization/{registrationId}` do `OAuth2AuthorizationRequestRedirectFilter` xử lý. Khi dùng `oauth2Login()`, callback mặc định đi qua xử lý login OAuth2 tại `/login/oauth2/code/{registrationId}`.

Nếu ứng dụng tùy chỉnh `SecurityFilterChain`, xác nhận chain đó bao phủ các đường dẫn bắt đầu login và callback. Đừng nhầm lỗi filter matcher với lỗi provider ID; cả hai có thể khiến login không hoạt động, nhưng cách sửa khác nhau.

### 18.4. Bật log có kiểm soát

Trong môi trường phát triển có thể đặt:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Quan sát luồng filter và request mà không lưu raw authorization code, token, client secret, cookie hoặc thông tin đăng nhập. Tránh đưa log nhạy cảm lên hệ thống chia sẻ hoặc bật mức log cao trên production chỉ để giải thích bài lab.

### 18.5. Bảng chẩn đoán nhanh

| Hiện tượng | Câu hỏi cần trả lời |
|---|---|
| Có provider config nhưng không thấy login | Đã khai báo registration chưa? Đã bật `oauth2Login()` trong chain phù hợp chưa? |
| Truy cập `/oauth2/authorization/<providerId>` không có tác dụng | ID này có thực sự là registration ID không? |
| Registration không dựng được | Provider alias có khớp khóa? Provider có thông số discovery/endpoints cần thiết không? |
| Browser vào sai OP | Registration này đã trỏ đúng provider ID chưa? Issuer/endpoints có bị nhầm tenant không? |
| Login OP xong callback bị từ chối | Redirect URI của registration có khớp URI đã đăng ký ở OP không? |
| Token issuer không đúng dự kiến | Cấu hình provider có trỏ sai realm/issuer không? Metadata và ID token dùng issuer nào? |
| Sau khi sửa tên registration, code gọi API tìm không thấy authorized client | Có nơi nào tham chiếu registration ID cũ không? |
| Có hai registrations chung OP nhưng scope bị lẫn | Scope có đặt riêng dưới từng registration không? Có dùng nhầm registration khi lấy token không? |

## 19. Bảo mật và vận hành khi cấu hình nhiều providers

Liên kết bằng provider ID là tiện ích cấu hình, nhưng hệ thống phải dựa vào **thông số giao thức đã xác minh** để thiết lập tin cậy.

- **Issuer đúng:** mỗi OIDC provider config phải dùng issuer URI chính xác; ID token được kiểm tra issuer, audience, chữ ký, thời hạn và các điều kiện OIDC cần thiết.
- **Client credentials tách biệt:** nhiều registrations cùng OP vẫn có thể có secrets khác nhau. Dùng biến môi trường hoặc secret manager; không commit client secret vào repo.
- **Redirect URI hạn chế:** chỉ đăng ký callback cần thiết ở OP. Khi đổi registration ID, cập nhật theo cơ chế kiểm soát thay đổi.
- **Scope tối thiểu:** cấp quyền theo nhu cầu của từng registration; chia sẻ provider không đồng nghĩa chia sẻ mọi scope.
- **Token đúng mục đích:** ID token dành cho Client xác thực người dùng, access token dành cho Resource Server; không dùng lẫn chỉ vì cùng issuer.
- **Kiểm tra HTTP Security:** cấu hình provider không tự bảo vệ đường dẫn nội bộ. Đảm bảo chain và access rules đúng.
- **Tách tenant:** nếu các issuer hoặc trust boundary khác nhau, dùng provider configurations riêng và chính sách liên kết tài khoản có chủ đích.
- **Quan sát an toàn:** chỉ ghi registration ID, issuer, endpoint công khai và kết quả kiểm tra phù hợp trong log/tài liệu; che token, cookie và secrets.

Khi quản trị nhiều môi trường, ví dụ `dev`, `staging` và `production`, có thể dùng profile hoặc external configuration để thay issuer/client ID tương ứng. Đừng để một profile dùng issuer production với client secret của staging. Các giá trị phải đồng bộ theo cùng một cấu hình môi trường.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Cấu hình có `registration.dashboard.provider: central-login` và `provider.central-login.issuer-uri: https://id.example.test/realms/main`. URL bắt đầu login mặc định sẽ có tên nào?

*Gợi ý:* `/oauth2/authorization/dashboard` dùng registration ID, không dùng provider ID.

**Câu 2.** Có thể có hai registrations cùng `provider: central-login` nhưng khác client ID không?

*Gợi ý:* có, nếu chúng thực sự là hai Clients ở cùng nhà cung cấp, được đăng ký và cấp quyền riêng.

**Câu 3.** Có hai realms với issuer khác nhau. Có nên cùng trỏ về một provider ID vì đều chạy Keycloak không?

*Gợi ý:* không. Provider config phải phản ánh đúng issuer/endpoints của mỗi OP.

**Câu 4.** `providerId` có cần bằng `client-id` hoặc domain của OP không?

*Gợi ý:* không. Nó là alias cấu hình trong ứng dụng.

**Câu 5.** Có nhánh `provider.company-sso.issuer-uri` nhưng thiếu `registration`. Spring Security có tự tạo registration login không?

*Gợi ý:* không nên giả định. Provider config mô tả máy chủ; Client registration phải tồn tại riêng.

**Câu 6.** Nếu đổi tên registration từ `web` thành `dashboard`, cần kiểm tra những gì?

*Gợi ý:* login URL, callback đã đăng ký, mã nguồn dùng registration ID và authorized client storage.

**Câu 7.** Vì sao `provider: github` không tự biến một đăng nhập OAuth 2.0 thành OIDC?

*Gợi ý:* giao thức, scope, ID token và metadata thực tế của nhà cung cấp mới quyết định có OIDC hay không.

**Câu 8.** Khi Spring Security đã build `ClientRegistration` từ YAML, có nên tìm `getProviderId()` để biết issuer không?

*Gợi ý:* dùng `getProviderDetails().getIssuerUri()` và thông số provider đã được giải quyết. Alias provider là khóa ở tầng configuration properties.

## 21. Tài liệu tham khảo

- [Spring Boot Reference — Spring Security OAuth2](https://docs.spring.io/spring-boot/reference/web/spring-security.html#web.security.oauth2): khai báo `spring.security.oauth2.client.registration.*` và `provider.*` trong Boot, tùy phiên bản.
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): ClientRegistration, repository, authorized client và cách dùng trong Servlet application.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): URL authorization, login callback và cấu hình đăng nhập.
- [Spring Security API — ClientRegistration](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/registration/ClientRegistration.html): các thuộc tính của registration và provider details.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata, discovery và các endpoint OIDC.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, issuer, audience và kiểm tra xác thực.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): vai trò của Client, Authorization Server, token và các thông số ủy quyền.

**Ghi nhớ:** `registrationId` định danh **Client registration** trong ứng dụng; `providerId` định danh **bộ cấu hình provider** mà registration đó tham chiếu. Dòng `registration.<registrationId>.provider: <providerId>` là cầu nối giữa hai phần. Bạn có thể đặt tên khác nhau, tái sử dụng một provider cho nhiều registrations hoặc tách provider theo từng issuer; luôn đảm bảo client credentials, callback, scope và issuer/endpoints thực sự tương ứng với hệ thống được dùng.
