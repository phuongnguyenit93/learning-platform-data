# Authorization theo scope và audience

**Authorization theo scope và audience** là cách bảo vệ API và các dịch vụ mạng bằng cách yêu cầu mỗi access token vừa **được cấp cho đúng tài nguyên/dịch vụ đích** (*audience*), vừa **mang quyền phù hợp với hành động được thực hiện** (*scope*). Cả hai là những điều kiện cần, nhưng vẫn chưa đủ để cấp quyền đối với từng đối tượng dữ liệu: API còn phải xác minh người gọi, tenant, đối tượng và quy tắc nghiệp vụ.

Ví dụ, một ứng dụng di động có access token dành cho **Orders API**, cho phép scope **orders.read**. Token đó có thể đủ điều kiện gọi API đọc đơn hàng theo phạm vi được cấp, nhưng không tự cho phép sửa đơn hàng, truy cập **Billing API**, hoặc xem đơn hàng thuộc về người dùng khác. Nếu API chỉ kiểm tra chữ ký và hạn token rồi bỏ qua audience, hoặc chỉ kiểm tra tên scope rồi bỏ qua quyền sở hữu dữ liệu, hệ thống có thể cho phép truy cập ngoài ý định.

Trong chương **API và network service security** của module **SECURITY_NETWORK_SECURITY**, kiểm soát này là một phần của phòng vệ nhiều lớp cùng với TLS/mTLS, API gateway, reverse proxy, firewall, phân đoạn mạng, VPN, IDS/IPS và giám sát. **TLS bảo vệ kênh truyền và xác thực endpoint theo cấu hình; OAuth access token cung cấp ngữ cảnh cấp quyền; API mới là nơi phải quyết định request cụ thể có được thực hiện hay không.**

> **Nguyên tắc cốt lõi:** Một token có chữ ký hợp lệ không tự là token dành cho API này; một token đúng audience không tự được phép làm mọi việc; và một token có scope phù hợp không tự cấp quyền với mọi bản ghi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **authentication**, **authorization**, **OAuth scope**, **audience**, **issuer**, **client ID**, **subject**, **role** và **resource owner**.
2. Giải thích vai trò của **Authorization Server (AS)**, **Resource Server (RS)**, client và người dùng trong OAuth 2.0.
3. Phân biệt **access token** với **OpenID Connect ID token**, và biết vì sao không dùng ID token như access token của API.
4. Thiết kế ma trận **API → audience → route/method → scope → quyền trên tài nguyên** theo least privilege.
5. Hiểu hai cách token thường được trình bày: **JWT self-contained** và **opaque/reference token**, cùng trách nhiệm xác minh của resource server.
6. Mô tả kiểm tra chữ ký, issuer, audience, expiration, not-before, loại token và những claim bắt buộc theo token profile.
7. Thiết kế quyền khi có nhiều API/microservice, **on-behalf-of/token exchange**, machine-to-machine và nhiều tenant.
8. Phân biệt lỗi **401 Unauthorized** với **403 Forbidden** và cách trả thông tin lỗi đủ dùng nhưng không lộ bí mật.
9. Phân tích giới hạn của API gateway, forwarding headers, TLS, CORS, rate limiting, DPoP/mTLS và token revocation.
10. Xây dựng log, kiểm thử positive/negative và runbook điều tra **cross-audience**, **over-scoped** hoặc **object-level authorization**.

## 2. OAuth 2.0 có những vai trò nào?

OAuth 2.0 là khuôn khổ cho việc cấp quyền truy cập được ủy quyền giữa các thành phần. Trong bối cảnh API, bốn vai trò khái niệm thường gặp là:

| Vai trò | Trách nhiệm | Ví dụ giả lập |
| --- | --- | --- |
| **Resource Owner** | Chủ thể có khả năng cấp hoặc liên quan đến quyền trên tài nguyên được bảo vệ, tùy tình huống | Người dùng sở hữu đơn hàng |
| **Client** | Ứng dụng yêu cầu token để gọi API | Mobile app, web backend, batch job |
| **Authorization Server (AS)** | Xác thực/cấp phép theo flow và phát hành access token | Identity platform của doanh nghiệp |
| **Resource Server (RS)** | API giữ tài nguyên, xác minh token và thực thi quyền truy cập | Orders API, Billing API |

**Authorization Server không phải API chứa dữ liệu** trong mọi kiến trúc. **Client ID không phải danh tính người dùng**; một ứng dụng có thể phục vụ rất nhiều người. **Resource Server không nên chỉ tin rằng Authorization Server đã cấp token hợp lệ là đủ**, vì nó còn phải kiểm tra token được dùng cho chính mình và hành động hiện tại.

### 2.1. AuthN, token issuance và AuthZ

- **Authentication (AuthN):** xác minh người hoặc workload là ai. Ví dụ người dùng đăng nhập với MFA; một service dùng client credentials hoặc chứng thư.
- **Token issuance:** AS phát hành token theo chính sách, với claims và phạm vi quyền.
- **API authorization (AuthZ):** RS quyết định request có được thực hiện dựa trên token, chính sách endpoint và dữ liệu ứng dụng.

Không phải mọi access token đại diện một người dùng. Trong luồng **client credentials**, token thường đại diện quyền của ứng dụng/workload; không nên tự gán nó cho một user cụ thể.

### 2.2. Sơ đồ trách nhiệm

~~~mermaid
flowchart TD
    USER["Người dùng / workload"] --> CLIENT["OAuth client"]
    CLIENT -->|"Yêu cầu quyền theo flow phù hợp"| AS["Authorization Server"]
    AS -->|"Access token: aud + scope + claims"| CLIENT
    CLIENT -->|"HTTPS + Bearer/PoP access token"| API["Resource Server: Orders API"]
    API --> V["Verify issuer, key, token type, time, audience"]
    V --> S["Check required scopes"]
    S --> O["Check subject, tenant, resource ownership & business policy"]
    O --> RESULT{"Được phép?"}
    RESULT -->|Có| ALLOW["Thực hiện thao tác"]
    RESULT -->|Không| DENY["Từ chối và audit"]
~~~

Đường đi ở sơ đồ là khái niệm. Token có thể là JWT được RS xác minh cục bộ hoặc opaque token cần introspection; hệ thống có thể dùng gateway trước API. **Không được bỏ qua bước policy tại resource server chỉ vì có gateway ở trước.**

## 3. Scope là gì?

**Scope** là cách biểu diễn **phạm vi quyền truy cập được cấp cho một token** theo quy ước của AS và hệ sinh thái API. Trong nhiều hệ thống OAuth, scope là các chuỗi phân biệt bằng dấu cách, ví dụ:

~~~text
orders.read orders.write
~~~

Thông thường API hoặc AS quy định mỗi scope có ý nghĩa nào. Các tên như **orders.read**, **orders.write** chỉ là **quy ước minh họa**, không phải từ khóa chuẩn OAuth bắt buộc các nhà cung cấp đều hiểu giống nhau.

| Scope ví dụ | Ý định quyền | Chưa chứng minh điều gì? |
| --- | --- | --- |
| **orders.read** | Gọi những thao tác đọc đơn hàng đã được cho phép | Người gọi sở hữu mọi đơn hàng |
| **orders.write** | Gọi những thao tác tạo/sửa đơn hàng được phép | Được sửa mọi đơn hàng của mọi user |
| **orders.cancel** | Yêu cầu hủy đơn khi thỏa nghiệp vụ | Đơn hàng đang ở trạng thái có thể hủy |
| **billing.read** | Gọi thao tác đọc thông tin thanh toán được cấp | Được đọc tài khoản khách hàng khác |
| **reports.export** | Yêu cầu xuất báo cáo theo quyền | Được tải mọi báo cáo, mọi tenant |
| **admin.audit.read** | Đọc dữ liệu audit được phê duyệt | Có quyền quản trị mọi chức năng |

### 3.1. Scope không đồng nghĩa role

**Role** thường mô tả vị trí/quyền của người dùng trong một tổ chức, ví dụ Finance Analyst, Customer Support hoặc System Admin. **Scope** thường mô tả khả năng được cấp cho **token hoặc client đối với API**. Một role có thể dẫn đến một tập scopes, nhưng không phải hai khái niệm đồng nhất.

Ví dụ nhân viên hỗ trợ thuộc role **support-agent** có thể được AS cấp token có **orders.read**. Tuy nhiên, ứng dụng chỉ cho xem đơn hàng trong tập case được giao; role và scope không tự loại bỏ kiểm tra theo case.

### 3.2. Scope không tự tạo cấu trúc phân cấp

Không có quy tắc chung rằng **orders.write** tự bao gồm **orders.read**, hoặc **orders.\*** tự là wildcard hợp lệ. Những quan hệ này chỉ tồn tại nếu **AS và RS cùng định nghĩa và thực thi rõ ràng**.

Trong nhiều API, nên kiểm tra các scope cần thiết một cách **tường minh**, tránh suy luận wildcard hoặc dùng phép tìm chuỗi con làm tăng quyền ngoài ý muốn.

### 3.3. Requested scope khác granted scope

Client có thể **yêu cầu** một tập scope tại bước cấp token, nhưng AS có thể cấp **ít hơn** hoặc từ chối theo chính sách, sự đồng ý, quyền user, loại client và resource. RS chỉ được sử dụng **quyền thật sự có trong access token đã được xác minh** hoặc kết quả introspection đáng tin.

**Không tin tham số scope trên request ban đầu do client tự gửi đến API** nếu nó không phải quyền được AS xác nhận.

### 3.4. OIDC openid scope khác scope của API

Trong **OpenID Connect (OIDC)**, scope **openid** báo hiệu yêu cầu xác thực danh tính theo OIDC; các scope như profile/email có thể liên quan đến claims danh tính. **openid không đồng nghĩa được đọc Orders API**, và nhận được ID token không tự cấp quyền truy cập API nghiệp vụ.

## 4. Audience (aud) là gì?

**Audience** xác định **bên nhận dự kiến của token** theo quy tắc và token profile đang dùng. Với access token dùng cho API, audience thường phải đại diện đúng **resource server/API**. Resource server có trách nhiệm **từ chối token không được cấp cho mình**, ngay cả khi chữ ký, thời hạn và scopes trông hợp lệ.

Ví dụ:

| Audience ví dụ | Resource server được dự kiến | Token không được dùng thay cho |
| --- | --- | --- |
| **https://orders.api.example.test** | Orders API | Billing API, Admin API |
| **https://billing.api.example.test** | Billing API | Orders API |
| **https://audit.api.example.test** | Audit API | Các API khác |

Các URI dùng domain **example.test** là giá trị tài liệu giả lập, không phải địa chỉ dịch vụ thực.

### 4.1. Audience phải so với giá trị được cấu hình tin cậy

Resource server cần có **danh sách audience được chấp nhận** do cấu hình đáng tin, chẳng hạn một API resource identifier. Không nên tự lấy bất kỳ giá trị **Host**, **X-Forwarded-Host** hoặc **aud** client khai rồi coi đó là expected audience.

Nếu hệ thống dùng URI làm audience, cách so sánh, chuẩn hóa và những bí danh hợp lệ cần được quy định rõ để tránh chấp nhận một audience khác ngoài ý định. **Không dùng phép kiểm tra chuỗi con** như “contains orders” để cấp quyền.

### 4.2. Một audience hay nhiều audiences?

Trong JWT, claim **aud** có thể là một chuỗi hoặc danh sách chuỗi tùy token profile. Một token có nhiều audiences có thể được thiết kế hợp lệ theo chính sách AS, nhưng nó đồng thời có thể **mở rộng phạm vi các resource server chấp nhận token**.

Do đó nên ưu tiên **access token với audience hẹp** cho từng API khi kiến trúc cho phép. Nếu cần nhiều audiences, phải xác định rõ:

1. Vì sao một token cần được dùng tại nhiều resource servers?
2. API nào có quyền nhận token và điều kiện scope ra sao?
3. Token có thể bị truyền nhầm hoặc bị tái sử dụng giữa các dịch vụ không?
4. Các API có cùng trust level và cùng mô hình tenant/permission không?

### 4.3. Audience không phải client ID trong mọi trường hợp

Với **OIDC ID token**, claim **aud** thường nhận diện **client/Relying Party** mà ID token dành cho; với **access token cho API**, aud phải gắn với **resource server đích** theo profile của hệ thống. Nhầm hai trường hợp này là nguyên nhân phổ biến của việc **API chấp nhận ID token như access token**.

## 5. Access token, ID token và refresh token

| Loại token | Dùng để làm gì? | Bên nhận dự kiến | Có nên dùng trực tiếp gọi API nghiệp vụ? |
| --- | --- | --- | --- |
| **Access token** | Client trình tới resource server để xin truy cập | RS/audience được cấp | **Có**, sau khi RS xác minh và cấp quyền |
| **ID token (OIDC)** | Chuyển kết quả xác thực danh tính cho client OIDC | Client/Relying Party | **Không** dùng thay access token |
| **Refresh token** | Client dùng với AS để xin access token mới theo chính sách | Authorization Server | **Không** gửi tới API tài nguyên |

**Không phải access token nào cũng là JWT.** Định dạng token có thể là chuỗi opaque; client thường nên xem access token là một credential, không dựa vào việc tự đọc payload để quyết định quyền.

### 5.1. Vì sao ID token không được dùng như access token?

ID token có audience và các ràng buộc dành cho **client OIDC**, không nhất thiết chứa scope/audience và những ràng buộc của API resource server. Nếu API chỉ nhìn thấy tên user trong ID token rồi cho phép, nó có thể bị **token confusion**: chấp nhận một credential dành cho vai trò khác.

### 5.2. Bearer token là quyền sử dụng theo việc nắm giữ

Với **Bearer access token**, bên nắm token có thể trình nó tới resource server phù hợp, nếu chưa bị hết hạn hoặc bị từ chối theo những chính sách khác. Vì vậy cần:

- Chỉ truyền qua **TLS đã xác minh server**.
- Không đưa token vào URL query, log công khai, source code, trang lỗi hay screenshot.
- Không truyền token của API A cho API B không cùng audience.
- Bảo vệ storage/token lifecycle theo loại client và thiết bị.
- Cân nhắc sender-constrained tokens như **mTLS hoặc DPoP** khi phù hợp.

### 5.3. Refresh token không được lan xuống microservices

Refresh token thường nên ở nơi client được ủy quyền quản lý, dùng với AS theo chính sách. **API/resource server không nên nhận refresh token rồi sử dụng nó như access token** hoặc chuyển tiếp cho dịch vụ downstream tùy ý.

## 6. Ví dụ JWT access token và cách đọc claims

Giả sử một Authorization Server đã phát hành **JWT access token** theo profile phù hợp, có dữ liệu được giải mã như sau. **Đây là JSON giả lập, không có chữ ký và không phải token có thể sử dụng**.

~~~json
{
  "header": {
    "alg": "RS256",
    "typ": "at+jwt",
    "kid": "training-key-2026-01"
  },
  "payload": {
    "iss": "https://identity.example.test",
    "sub": "user-0042",
    "aud": "https://orders.api.example.test",
    "client_id": "mobile-orders-app",
    "scope": "orders.read orders.cancel",
    "iat": 1795861200,
    "nbf": 1795861200,
    "exp": 1795863000,
    "jti": "synthetic-access-token-id-42",
    "tenant_id": "tenant-a"
  },
  "note": "Dữ liệu minh họa đã giải mã; không phải JWT có chữ ký"
}
~~~

Trong một JWT thật, header và payload được mã hóa dạng base64url và liên kết với phần chữ ký hoặc cấu trúc mật mã tương ứng. **Chỉ giải mã JSON không phải xác minh chữ ký.** Ngay cả khi JWT chứa trường **scope**, RS vẫn phải kiểm tra cả audience, issuer, hạn, signature và quyền thực tế.

### 6.1. Các claim quan trọng

| Claim | Ý nghĩa thường gặp | Cần xác minh |
| --- | --- | --- |
| **iss** | Issuer đã phát hành token | Khớp issuer được RS tin, chính xác theo cấu hình |
| **sub** | Chủ thể của token | Ngữ nghĩa user/workload theo token profile; không tự là quyền truy cập |
| **aud** | Bên nhận token được dự kiến | Bao gồm đúng resource identifier của API |
| **exp** | Mốc token hết hạn | Thời gian hiện tại nằm trước hạn theo chính sách |
| **nbf** | Không dùng token trước mốc này nếu được khai báo | Kiểm tra đồng hồ và clock skew được phép |
| **iat** | Thời điểm phát hành | Có ích cho freshness, audit, kiểm tra bất thường |
| **scope** | Quyền token được cấp theo quy ước | Có đủ scope bắt buộc cho request không? |
| **client_id / azp** | Nhận diện client hoặc authorized party theo profile | Chỉ dùng khi ý nghĩa đã được token profile định nghĩa |
| **jti** | ID của token | Có thể hỗ trợ audit/revocation, không tự tạo quyền |
| **tenant_id** | Tenant context theo quy ước riêng | Phải được xác minh nguồn và ràng buộc với dữ liệu thực |

Không phải mọi claim ở bảng đều bắt buộc với mọi loại token. Ví dụ **scope**, **client_id** và **tenant_id** có thể được mã hóa khác trong sản phẩm; cần xác định profile và chính sách sử dụng trước khi lập quy tắc.

### 6.2. Scope string và scp array

Một số nền tảng sử dụng claim **scope** dạng chuỗi cách nhau bằng dấu cách; một số sử dụng **scp** hoặc cách biểu diễn quyền khác. Resource server phải được cấu hình **chính xác nguồn claim nào được issuer của mình bảo đảm**, không ghép tất cả claim tìm thấy rồi vô điều kiện cho phép.

Không nên kiểm tra kiểu “scope chứa chuỗi read” vì **orders.read** và **billing.read** là hai quyền khác nhau. Phải tách và so khớp **đúng từng scope**.

## 7. Xác minh JWT access token tại resource server

Đối với JWT access token, resource server phải dựa trên **thư viện JWT/OAuth đáng tin và token profile được hỗ trợ**, thay vì tự viết parser hoặc tự so chuỗi base64url.

### 7.1. Các kiểm tra thường cần thiết

1. **Token type/profile:** đây có phải access token cho RS này không? Với profile JWT AT theo RFC 9068, cần xem yêu cầu token type **at+jwt** và những claim tương ứng.
2. **Issuer:** iss phải thuộc danh sách issuer được tin và khớp chính sách cấu hình.
3. **Signature:** chữ ký token phải được xác minh bằng khóa của issuer phù hợp, lấy theo cơ chế tin cậy.
4. **Algorithm allowlist:** không cho client tùy chọn một thuật toán không được phép hoặc **alg=none** để bỏ qua chữ ký.
5. **Audience:** aud phải khớp **resource identifier** của API.
6. **Time:** exp, nbf và các yêu cầu freshness/clock skew trong chính sách phải đạt.
7. **Các claim bắt buộc:** subject/client identity, client type hoặc các giá trị theo profile phải hợp lệ khi được yêu cầu.
8. **Scopes:** tập quyền đã cấp đủ cho HTTP method/endpoint hoặc operation cụ thể.
9. **Resource authorization:** owner, tenant, object state và business policy phải cho phép.
10. **Token/session revocation nếu áp dụng:** kiểm tra cơ chế được triển khai, không tự giả định một JWT chưa hết hạn chưa từng bị thu hồi.

**Không nên coi danh sách này là “chỉ cần check aud và scope”.** Nếu JWT chưa được kiểm tra chữ ký, những claims trong đó chưa phải dữ liệu đáng tin.

### 7.2. Trust issuer và JWKS

Nhiều AS công bố public keys dưới dạng **JSON Web Key Set (JWKS)** qua metadata được quản lý. RS có thể cache các khóa đó và dùng **kid** để chọn khóa ứng viên.

Các yêu cầu an toàn:

- Chỉ sử dụng **issuer/JWKS endpoint đã được cấu hình hoặc khám phá qua kênh tin cậy**.
- Không tải khóa từ URL do JWT header tự chỉ định nếu chưa được chính sách tin cậy cho phép.
- Không nhầm **kid** là một câu lệnh, đường dẫn file hoặc URL cần mở tùy ý.
- Giới hạn các thuật toán được phép; tránh **algorithm confusion** giữa đối xứng/bất đối xứng.
- Hỗ trợ **key rotation** với cache TTL, thời gian overlap và xử lý khi AS/JWKS tạm không truy cập được.
- Nếu có nhiều issuers, ràng buộc mỗi issuer với **tập keys, audience và claim rules** tương ứng, không trộn lẫn.

### 7.3. Clock skew và freshness

Giữa AS và RS có thể có sai số đồng hồ nhỏ. Cấu hình cho phép một khoảng **clock skew hữu hạn** giúp giảm lỗi giả, nhưng không nên mở quá rộng làm tăng thời gian token được chấp nhận ngoài ý định. Đồng bộ thời gian và theo dõi drift vẫn cần thiết.

### 7.4. Token có aud là danh sách

Khi aud chứa danh sách, thư viện nên kiểm tra **có resource identifier chính xác được cho phép**, không so substring, không lấy tùy ý phần tử đầu tiên rồi coi là danh tính của API. Token nhiều audiences chỉ nên được chấp nhận khi đúng **token profile và chính sách tin cậy** của tổ chức.

## 8. Opaque access token và introspection

**Opaque token** không mang claims mà API có thể tự hiểu và kiểm tra theo cách JWT. Resource server có thể gọi **token introspection endpoint** của AS hoặc một dịch vụ được ủy quyền để lấy thông tin trạng thái/claims, tùy giao thức và thiết kế.

Trong OAuth Token Introspection (RFC 7662), phản hồi có thể có:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "internal-dashboard",
  "sub": "user-0042",
  "aud": "https://orders.api.example.test",
  "iss": "https://identity.example.test",
  "exp": 1795863000,
  "token_type": "Bearer"
}
~~~

Đây là **JSON minh họa**. Phản hồi introspection thực tế còn phụ thuộc AS và những trường được hỗ trợ.

### 8.1. Active=true chưa đủ

**active=true** thường cho biết token đang được AS xem là active theo chính sách của nó. RS còn phải kiểm tra:

- Kết quả introspection đến từ **endpoint được tin**, qua kênh được bảo vệ.
- Token có **audience đúng API** hoặc resource binding tương ứng.
- Quyền/scope được cấp có đủ cho request.
- Các claim liên quan issuer/client/tenant phù hợp với chính sách.
- Việc cache introspection không vượt quá tuổi token hoặc SLA thu hồi.

Không dùng một dịch vụ introspection trả **active=true** cho token thuộc API khác để tự động cấp quyền vào API hiện tại.

### 8.2. Khi introspection endpoint lỗi

Không được mặc định **allow tất cả** khi introspection không khả dụng. Hệ thống có thể thiết kế cache kết quả đã xác minh còn hiệu lực hoặc chính sách fail-closed theo rủi ro, nhưng phải ghi nhận chính xác **không xác minh được quyền mới**.

Khả năng HA của AS/introspection là một phần của thiết kế availability cho API có yêu cầu bảo mật cao.

### 8.3. JWT không phải lúc nào cũng tốt hơn opaque

JWT giúp RS xác minh cục bộ, giảm số lần gọi AS, nhưng việc thu hồi từng token trước exp có thể đòi hỏi cơ chế riêng. Opaque token có thể cho phép AS quản lý trạng thái tập trung, nhưng tạo phụ thuộc vào introspection endpoint và cache. **Chọn định dạng dựa trên mô hình rủi ro, latency, revocation và vận hành**, không chỉ trên khả năng đọc payload.

## 9. Chính sách authorization cần nhiều tầng

Một authorization decision có thể được xem là phép giao của nhiều điều kiện:

~~~text
allow =
    token_is_authentic_and_current
    AND token_is_intended_for_this_API
    AND token_has_required_scope
    AND caller_identity_or_client_is_allowed
    AND caller_is_authorized_for_this_resource
    AND resource_state_and_business_policy_allow
    AND required_device_or_session_conditions_are_met
~~~

Trong triển khai cụ thể, không phải mọi API có device posture hoặc user identity. Nhưng **scope + audience không đủ thay thế những điều kiện mà nghiệp vụ thật sự yêu cầu**.

### 9.1. Endpoint-level authorization

API xác định HTTP route/method hoặc RPC operation được phép khi token có scope tương ứng.

Ví dụ:

| API operation | Required audience | Required scope |
| --- | --- | --- |
| GET /orders | Orders API | orders.read |
| GET /orders/{id} | Orders API | orders.read |
| POST /orders | Orders API | orders.write |
| POST /orders/{id}/cancel | Orders API | orders.cancel |
| GET /billing/invoices | Billing API | billing.read |
| GET /audit/events | Audit API | admin.audit.read |

Hệ thống cần quyết định rõ một operation có yêu cầu **tất cả scopes** hay **một trong các scopes**. Ví dụ request xem dữ liệu nhạy cảm có thể đòi **orders.read và pii.read** đồng thời; một phép kiểm tra chỉ cần “một trong hai” sẽ cấp quá quyền.

### 9.2. Object-level authorization

Với **GET /orders/42**, token có orders.read chỉ cho biết client được phép thực hiện nhóm thao tác đọc đơn hàng; backend còn cần xác minh **user hoặc client được quyền đọc đơn hàng 42**.

Đây là một phần cốt lõi để chống **Broken Object Level Authorization (BOLA)**. Một ứng dụng có thể có gateway check đầy đủ OAuth nhưng vẫn lộ dữ liệu nếu truy vấn database chỉ dựa trên ID do client gửi.

### 9.3. Function-level authorization

Các chức năng như **approve refund, export all tenants, rotate API keys, configure firewall** thường đòi quyền hẹp hơn các chức năng đọc phổ thông. **Broken Function Level Authorization (BFLA)** xuất hiện khi một API endpoint có quyền nhạy cảm bị thiếu kiểm tra vai trò/chức năng.

### 9.4. State-based policy

Một order đang ở trạng thái **shipped** có thể không cho phép cancel dù token mang orders.cancel và user sở hữu đơn. Đây là quyết định **nghiệp vụ**, không thể biểu diễn đầy đủ bằng việc có hay không có scope trong token.

## 10. Thiết kế scope theo least privilege

Một bộ scope hữu ích phải đủ rõ để quản trị nhưng không tạo hàng nghìn quyền khó duy trì.

### 10.1. Scope tốt cần có ý nghĩa ổn định

- Tên gắn với **khả năng API cụ thể**, ví dụ orders.read, orders.cancel.
- Mỗi scope có **chủ sở hữu**, mô tả chính xác, resource server đích và độ nhạy cảm.
- Scope nhạy cảm đòi chính sách cấp riêng, không tự nằm trong mọi token user.
- Khi chia API theo domain, tránh đặt scope quá chung như **read.all** được mọi backend diễn giải theo cách khác nhau.
- Các scope cũ khi thay đổi ngữ nghĩa cần kế hoạch versioning/migration, tránh mở quyền ngoài ý định.

### 10.2. Nguyên tắc cấp tối thiểu

Client chỉ nên yêu cầu những scopes nó thực sự cần. AS chỉ cấp scopes phù hợp với:

1. **Client được đăng ký** và quyền client được phép xin.
2. **Người dùng/resource owner** nếu flow dựa trên user.
3. **Resource/audience** dự định.
4. **Consent/approval và chính sách rủi ro** nếu áp dụng.
5. **Context** như thiết bị được quản lý hoặc môi trường thực thi khi kiến trúc yêu cầu.

**Một client được phép yêu cầu scope không có nghĩa mọi user của client được phép sử dụng thao tác đó trên mọi tài nguyên.**

### 10.3. Không dùng tên scope để che thiếu kiểm tra dữ liệu

Scope như **orders.read.own** có thể có ý nghĩa tốt ở mức thiết kế, nhưng RS phải thật sự **kiểm tra owner của từng đơn hàng**. Chỉ đặt tên “own” mà sau đó truy vấn SELECT không lọc theo quyền sẽ không tạo bảo mật.

### 10.4. Scope và permission giữa các API

Không tái sử dụng scope trùng tên giữa nhiều API rồi suy rằng mỗi API có cùng nghĩa. Một hệ thống có thể có **billing.read** tại Billing API nhưng không có ý nghĩa tại Orders API. Audience giúp ngăn token bị dùng sai API; scope giúp giới hạn việc được làm **tại API đó**.

## 11. Resource indicators và cấp token đúng audience

Trong OAuth 2.0, **resource indicators** (RFC 8707) cung cấp cách client chỉ ra resource server dự định khi yêu cầu token, trong môi trường AS hỗ trợ.

Ví dụ ở mức khái niệm:

~~~http
POST /oauth/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&resource=https%3A%2F%2Forders.api.example.test&scope=orders.read
~~~

Đoạn này **chỉ là biểu diễn giả lập của yêu cầu**, thiếu cơ chế client authentication và các tham số cụ thể để sử dụng thực tế; không có credential nào được đưa ra. Authorization Server sẽ xác định token có thể được cấp cho resource và scope này hay không theo chính sách.

### 11.1. Audience và resource không phải tham số tùy tiện

**Không phải AS nào cũng hỗ trợ tham số resource theo cách giống nhau**. Một số nền tảng dùng API identifiers, resource-specific scope names hoặc cơ chế khác. Client và RS cần căn cứ vào **issuer/AS contract** được phê duyệt, không tự phỏng đoán cách map từ request sang aud.

### 11.2. Một token chung mọi backend dễ gây vấn đề

Ví dụ ba API **Orders**, **Billing** và **Admin** chấp nhận cùng một token với audience **all-services** và nhiều scopes. Khi một API bị lộ bearer token, token đó có thể trở nên hữu ích ở nhiều nơi. Thiết kế **audience-specific access token** giúp giới hạn nơi token được chấp nhận.

Nếu có lý do hợp lệ để dùng chung audience cho một API platform, phải có chính sách scope, trust zones, identity và authorization đủ chặt cho các backend thuộc platform đó.

## 12. Multi-service: tại sao không tự chuyển token của API A sang API B?

Trong kiến trúc microservices, một yêu cầu có thể đi theo đường:

**Client → Orders API → Billing API → Notification Service**.

Nếu client nhận token có audience **Orders API**, Orders API không nên đơn giản lấy nguyên token đó rồi chuyển sang Billing API và yêu cầu Billing API chấp nhận. Token đã được cấp cho **Orders**, không mặc nhiên được cấp cho **Billing**.

~~~mermaid
flowchart LR
    C["Client"] -->|"Token A: aud=Orders, scope=orders.read"| O["Orders API"]
    O -. "Không chuyển Token A trực tiếp như token hợp lệ" .-> B["Billing API"]
    O -->|"Yêu cầu credential/token phù hợp với downstream"| AS["Authorization Server / token service"]
    AS -->|"Token B: aud=Billing, quyền được giới hạn"| O
    O -->|"Token B dùng cho Billing"| B
    B -->|"Kiểm tra aud, scopes, subject/client và dữ liệu"| P["Policy / Data"]
~~~

### 12.1. Những lựa chọn kiến trúc hợp lệ

- **Service credential riêng:** Orders API tự xác thực như workload và xin token theo **client credentials** dành cho Billing API, khi tác vụ không cần đại diện quyền riêng của người dùng.
- **Token exchange / on-behalf-of:** Orders API đổi một credential/token đầu vào sang token có audience Billing, trong phạm vi được AS cho phép và theo ngữ nghĩa ủy quyền phù hợp.
- **Direct client token cho Billing:** nếu flow và quyền user cho phép, client lấy access token dành cho Billing rồi gọi Billing qua đường được phê duyệt.
- **Service mesh/mTLS và identity policy:** có thể bổ sung xác thực service, nhưng backend vẫn cần nguồn user context phù hợp cho thao tác nhân danh người dùng.

**Không tự tạo JWT mới bằng khóa của Orders API rồi tuyên bố nó đến từ AS** nếu Orders không được cấp quyền phát hành token và Billing không có hợp đồng tin cậy tương ứng.

### 12.2. Token exchange giải quyết bài toán gì?

**OAuth 2.0 Token Exchange** (RFC 8693) mô tả cách yêu cầu token mới dựa trên token hoặc credential được cung cấp theo chính sách AS. Trong tình huống đúng thiết kế, token downstream có thể:

- Có audience **Billing API**, không phải Orders API.
- Chỉ có scope cần thiết như **billing.read**, không giữ toàn bộ quyền của token đầu vào.
- Mang ngữ cảnh subject và/hoặc actor khi token profile hỗ trợ và AS cấp.
- Có thời hạn ngắn và ràng buộc đúng dịch vụ đích.

**Token exchange không mặc nhiên cho phép leo thang quyền.** AS phải xác minh nguồn, quyền client xin token, ngữ nghĩa delegated/actor và quyền user/workload trước khi cấp. **Billing API** vẫn kiểm tra dữ liệu/tenant được phép.

### 12.3. Confused deputy

**Confused deputy** xảy ra khi một dịch vụ có quyền mạnh hơn bị lợi dụng để thực hiện hành động thay cho bên không có quyền, do dịch vụ không ràng buộc đúng nguồn yêu cầu, mục đích hoặc phạm vi ủy quyền.

Ví dụ Orders API có client credential đọc Billing, nhưng nhận bất kỳ order ID do người dùng gửi rồi gọi Billing mà **không kiểm tra người dùng có quyền với order tương ứng**. Audience/token của Orders tới Billing có thể hợp lệ về mật mã, nhưng logic ủy quyền ở Orders vẫn bị thiếu.

## 13. Machine-to-machine và client credentials

Trong các job tự động, CI/CD, backend service và workload cloud, có thể không có người dùng hiện diện. Với flow **client credentials** phù hợp, token thể hiện quyền được AS cấp cho client/workload theo chính sách.

Ví dụ một đồng bộ tồn kho được cấp:

| Client | Audience | Scope | Phạm vi nghiệp vụ |
| --- | --- | --- | --- |
| inventory-sync | Inventory API | inventory.write | Chỉ cập nhật sản phẩm thuộc tenant được phê duyệt |
| report-scheduler | Reporting API | reports.create | Chỉ tạo báo cáo của bộ phận được cấp |
| billing-reconcile | Billing API | billing.reconcile | Chỉ chạy tác vụ đối soát được duyệt |

### 13.1. Client identity không phải user identity

Không nên gán **sub** hoặc các trường client cho một người dùng tưởng tượng nếu token profile đại diện workload. API phải biết mình đang xử lý **service principal** hay **user-delegated access**.

Một số token profile sử dụng **client_id**, **sub**, **azp** hoặc những claim khác theo quy tắc riêng. **Không đồng nhất ngữ nghĩa của các trường trên mọi issuer**; hãy kiểm tra hợp đồng dữ liệu và chính sách cấp token.

### 13.2. Quyền workload cũng cần tối thiểu

Một service chạy trong mạng private hoặc Kubernetes cluster không tự có quyền gọi mọi API. **NetworkPolicy và mTLS** giảm bề mặt kết nối, trong khi **audience và scope** giới hạn token được sử dụng ở đâu và làm gì.

### 13.3. Không lưu client secret tùy tiện

Nếu client cần xác thực để xin token, hãy bảo vệ secret/private key trong cơ chế quản lý bí mật phù hợp, ưu tiên những phương thức xác thực client mạnh được AS và kiến trúc hỗ trợ. Không đặt credential dài hạn trong mã nguồn, image public hoặc client ứng dụng di động nơi secret không thể được giữ bí mật đáng tin.

## 14. Authorization trong hệ thống nhiều tenant

**Multi-tenancy** làm tăng yêu cầu ràng buộc giữa **issuer, subject, client, tenant, resource và audience**.

Giả sử một token có:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-0042",
  "aud": "https://orders.api.example.test",
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

Đây là claims giả lập để thảo luận, không phải JWT đầy đủ. Khi nhận request **GET /orders/42**, Orders API còn phải kiểm tra:

1. Token đã được xác minh từ **issuer đúng** và có audience Orders.
2. Scope **orders.read** đã được cấp.
3. Đơn hàng 42 thực sự thuộc **tenant-a** hoặc phạm vi liên quan được phê duyệt.
4. Subject user-0042 có quyền đọc đơn hàng 42 theo membership/assignment hiện hành.
5. Tenant trên URL, Host hoặc request body **không thể ghi đè tenant context đã xác minh**.

### 14.1. Tenant claim là một tín hiệu, không tự là toàn bộ policy

Nếu AS đưa tenant_id vào token, RS phải biết claim đó được **issuer có thẩm quyền phát hành** và có ý nghĩa gì. Khi người dùng thuộc nhiều tenant, cần xác định **cách chọn tenant và thời điểm token được cấp**, không tự coi một trường do client tự gửi trong HTTP body là nguồn tin cậy.

### 14.2. BOLA: scope đúng nhưng xem sai đơn hàng

Một lỗi điển hình:

~~~text
# Phản ví dụ KHÔNG an toàn (giả mã):
if token.scope contains "orders.read":
    return database.getOrder(request.path.orderId)
~~~

Lỗi không chỉ ở cách kiểm tra scope; ứng dụng còn thiếu kiểm tra **ownership/tenant** trước khi trả đơn. Khi triển khai đúng, dữ liệu phải được lọc theo quyền hoặc được xác minh qua authorization service/truy vấn bảo đảm tenant isolation.

~~~text
# Mô hình phòng vệ:
principal = validateAccessTokenForOrdersApi(request)
require principal.hasExactScope("orders.read")
order = database.loadOrderWithinAuthorizedTenant(
    orderId = request.path.orderId,
    tenantId = principal.verifiedTenant
)
require order exists
require policy.canReadOrder(principal, order)
return approvedOrderView(order)
~~~

**Đừng tự xây dựng truy vấn database chỉ dựa trên token mà bỏ qua ràng buộc tenant của đối tượng.** Và không để client tự chọn một tenant khác mà không có bước xác thực, kiểm tra membership hoặc context switching hợp lệ.

### 14.3. Mỗi API phải biết chủ thể chịu trách nhiệm

Trong service-to-service, Orders API có thể dùng token workload để gọi Billing. Billing cần phân biệt:

- Workload **Orders API** được phép gọi phương thức nào.
- Thao tác có diễn ra **nhân danh người dùng** hay là một job tự động.
- Tenant và resource nào được phép truy cập.
- Quyết định cần dựa trên **user permissions**, **service permissions**, hay cả hai.

Một token với actor/client hợp lệ không tự cho phép cross-tenant data access.

## 15. API gateway, reverse proxy và phân chia trách nhiệm

Gateway có thể thực hiện **coarse-grained authorization**: xác minh JWT, kiểm tra issuer, audience, scopes và route. Backend nên thực hiện **fine-grained authorization**: owner, tenant, record state, business role.

~~~mermaid
flowchart TB
    U["Client / Internet / VPN"] -->|"HTTPS + Access token"| G["API Gateway / Reverse proxy"]
    G -->|"Validate issuer, aud, signature, time, coarse scope"| ROUTE["Approved API route"]
    ROUTE -->|"Verified context + protected transport"| ORD["Orders API"]
    ROUTE -->|"Separate policy/context"| BILL["Billing API"]
    ORD --> OAUTH["Object, tenant, business authorization"]
    BILL --> BAUTH["Object, tenant, business authorization"]
    OAUTH --> DB1[("Orders data")]
    BAUTH --> DB2[("Billing data")]
    G -. "AuthN/AuthZ gateway logs" .-> SOC["SIEM / SOC"]
    ORD -. "Resource policy logs" .-> SOC
    BILL -. "Resource policy logs" .-> SOC
~~~

### 15.1. Không tin dữ liệu identity từ Internet

Nếu gateway thêm header như **X-Verified-User**, **X-Verified-Scopes** hoặc **X-Tenant-ID**, nó phải xóa/ghi đè những header cùng tên do client gửi. Backend chỉ chấp nhận dữ liệu do **gateway được ủy quyền** tạo ra, qua đường mạng được bảo vệ và có cơ chế xác minh nguồn phù hợp.

**Một header scope không được ký hoặc không bị ràng buộc với nguồn có thẩm quyền không tương đương access token đã xác minh.**

### 15.2. Bypass gateway

Nếu backend còn public IP, alternate cloud load balancer, Kubernetes Service exposed hoặc đường VPN nội bộ cho phép gọi thẳng API, attacker có thể bypass policy ở gateway. Backend cần:

- Chỉ cho traffic từ đường vào được phê duyệt, bằng firewall/network policy.
- Có khả năng tự kiểm tra token hoặc xác minh nguồn ngữ cảnh đã được gateway cấp, tùy kiến trúc.
- Không mặc định trust mọi request đến từ **private IP** hoặc tên mạng “internal”.
- Giám sát những đường trực tiếp, gồm cả IPv6 và failover region.

### 15.3. Gateway không hiểu hết nghiệp vụ

Gateway có thể biết **GET /orders/{id} yêu cầu orders.read**, nhưng thường không biết **order {id} thuộc user/tenant nào** nếu không tích hợp authorization chuyên biệt. Không đưa toàn bộ object authorization về một rule chỉ dựa trên URL hoặc method.

## 16. Bearer token, DPoP và mTLS sender-constrained tokens

### 16.1. Bearer token bị lộ có nguy cơ gì?

Khi token là **bearer**, một bên khác có token có thể trình nó tới RS trong điều kiện còn hiệu lực và các policy khác cho phép. Nguy cơ này xuất hiện khi token bị lộ trong log, URL, browser storage không phù hợp, đường truyền yếu hoặc sự cố endpoint.

**Audience giúp giảm nơi token có thể được chấp nhận; scope giúp giảm quyền token mang.** Nhưng một token đúng audience và scope vẫn có thể bị sử dụng sai nếu bị đánh cắp.

### 16.2. Sender-constrained access token

Một số kiến trúc có thể dùng **mTLS-bound access tokens** hoặc **DPoP (Demonstrating Proof of Possession)** để ràng buộc token với khóa của bên trình token.

| Cơ chế | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| **Bearer** | Bên có token có thể dùng nếu thỏa điều kiện API | Bảo vệ token khỏi lộ, dùng TTL ngắn và scopes hẹp |
| **mTLS-bound token** | Token gắn với chứng thư/khóa của client và verifier kiểm tra ràng buộc | Cần certificate lifecycle, xác minh hai lớp và tương tác proxy |
| **DPoP** | Client cung cấp proof được ký cho request theo quy tắc hỗ trợ | Kiểm tra proof, khóa ràng buộc token, htm/htu, freshness và replay protection |

Các cơ chế này **không thay thế audience, scope hoặc resource ownership**. Một request có DPoP proof hợp lệ vẫn phải bị từ chối nếu token được cấp cho API khác hoặc không có quyền.

### 16.3. Lưu ý khi API đặt sau reverse proxy

Với DPoP, những giá trị về **HTTP method và URI** được proof ràng buộc phải được kiểm tra theo quy tắc profile, đặc biệt khi reverse proxy rewrite path, đổi scheme hoặc hostname. Không tự dùng header chưa xác minh để làm nguồn tin cậy cho URI gốc.

Với mTLS, phải phân biệt **client → gateway** và **gateway → backend**. Nếu TLS bị terminate ở gateway, backend không tự nhìn thấy chứng thư của client cuối; cần một cơ chế truyền kết quả xác thực **được ràng buộc nguồn** phù hợp với thiết kế, không chỉ copy chuỗi PEM vào header tùy ý.

## 17. Token lifecycle: TTL, revocation và key rotation

### 17.1. Token có thời hạn hữu hạn

Một access token sống càng lâu thì **cửa sổ bị sử dụng ngoài ý muốn** có thể càng lớn khi token bị lộ hoặc user đổi quyền. TTL nên dựa trên tính nhạy cảm, mô hình client, latency và khả năng làm mới token; không có một con số chung phù hợp mọi hệ thống.

### 17.2. Thu hồi token và quyền người dùng

Những tình huống cần xem xét:

- Tài khoản bị vô hiệu hóa hoặc rời tổ chức.
- Client credentials bị thu hồi.
- User bị gỡ role nhạy cảm.
- Token bị lộ.
- Một quyền/scope không còn được cho phép.
- AS signing key hoặc client private key nghi bị lộ.

**Một JWT chưa hết hạn có thể vẫn được RS chấp nhận theo xác minh cục bộ**, nếu hệ thống chưa có cơ chế thu hồi và cập nhật quyền phù hợp. Các lựa chọn như TTL ngắn, token denylist/introspection, continuous evaluation hoặc chấm dứt session phải được thiết kế cụ thể.

### 17.3. Quản lý JWKS rotation

Khi AS xoay khóa ký:

1. Khóa mới cần được RS nhận đúng qua nguồn JWKS được tin.
2. Token cũ còn hiệu lực có thể cần khóa cũ trong giai đoạn overlap.
3. RS phải giới hạn tuổi cache nhưng tránh phụ thuộc liên tục vào network fetch.
4. Nếu phát hiện khóa bị xâm phạm, quy trình thu hồi có thể khác rotation bình thường.
5. Monitoring phải phân biệt **unknown kid**, lỗi JWKS availability, chữ ký sai và audience mismatch.

**Không giải quyết unknown kid bằng cách tắt signature verification.** Hãy kiểm tra issuer, metadata/JWKS, cache, change ticket và trạng thái khóa.

### 17.4. Cập nhật quyền trong phiên

Nếu user bị gỡ khỏi nhóm **Finance** lúc 14:00 nhưng token cũ chứa scope **billing.read** đến 14:30, RS có thể còn chấp nhận token theo cấu hình. Với dịch vụ nhạy cảm, cần xác định SLA thu hồi và kiểm thử **cơ chế làm quyền mới có hiệu lực**, không chỉ gỡ membership ở IdP.

## 18. Các lỗi HTTP: 401 và 403

### 18.1. 401 Unauthorized

Mã **401 Unauthorized** thường được dùng khi request thiếu credential xác thực hợp lệ, token không có hoặc không được chấp nhận theo cơ chế Bearer/API được triển khai. Phản hồi thường có header **WWW-Authenticate** phù hợp theo tiêu chuẩn, chẳng hạn:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
Cache-Control: no-store
~~~

Các trường lỗi trong ví dụ chỉ có ý nghĩa khi được dùng đúng theo tiêu chuẩn và không làm lộ chi tiết nhạy cảm. **401 có thể bao gồm token sai audience** khi token không hợp lệ cho resource này theo policy của API.

### 18.2. 403 Forbidden

Mã **403 Forbidden** thường phù hợp khi credential đã được xác thực nhưng người gọi **không đủ quyền** cho hành động hiện tại. Trong OAuth Bearer Token Usage (RFC 6750), trường hợp thiếu scope có thể sử dụng lỗi **insufficient_scope**:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope", scope="orders.cancel"
Cache-Control: no-store
~~~

**Không phải mọi 403 đều cần công bố scope yêu cầu**. Với API nhạy cảm hoặc tài nguyên không được phép tiết lộ sự tồn tại, ứng dụng có thể dùng chính sách phản hồi phù hợp, ví dụ 404 trong bối cảnh được thiết kế để tránh lộ tài nguyên.

### 18.3. Bảng xử lý

| Tình huống | Ví dụ quyết định | Lưu ý |
| --- | --- | --- |
| Không có access token khi endpoint yêu cầu | 401 | Hướng client tới cơ chế xác thực hợp lệ |
| Chữ ký hoặc issuer sai | 401 / invalid_token | Không bật fallback bỏ kiểm tra chữ ký |
| Access token đúng chữ ký nhưng aud thuộc API khác | 401 / invalid_token | Không chấp nhận cross-audience |
| Token hết hạn hoặc chưa đến nbf | 401 / invalid_token | Xem clock skew hữu hạn |
| Token hợp lệ nhưng thiếu required scope | 403 / insufficient_scope | Chỉ công bố scope nếu policy cho phép |
| Có scope nhưng user không sở hữu object | 403 hoặc 404 theo policy | Kiểm tra ownership/tenant, không chỉ scope |
| Backend không thể liên hệ introspection | Lỗi kiểm soát theo kiến trúc; không tự allow | Phân biệt availability với token revoked |
| API có scope nhưng không đủ quyền nghiệp vụ | 403 theo policy | Phân tách gateway và application AuthZ |

Trong mọi trường hợp, **log nội bộ có thể ghi nguyên nhân chi tiết hơn response công khai**, miễn là không ghi token hoặc dữ liệu nhạy cảm.

## 19. Phòng tránh các lỗi authorization phổ biến

| Lỗi thiết kế | Hệ quả | Kiểm soát |
| --- | --- | --- |
| Chỉ verify JWT signature, không kiểm tra aud | Token API A có thể được dùng ở API B | Audience validation chính xác |
| Nhận ID token như access token | Token confusion, dùng sai loại credential | Token type/profile validation |
| Chấp nhận mọi issuer dùng một JWKS chung | Trust boundary giữa IdP/tenant yếu | Issuer-key-audience policy riêng |
| Tin scope claim khi token chưa verify | Client giả quyền qua payload | Signature/introspection trước khi áp quyền |
| Scope check bằng substring | billing.read có thể bị nhầm với orders.read | Exact scope matching |
| Coi scope là quyền với mọi object | BOLA/IDOR, lộ dữ liệu cross-user | Object/tenant authorization |
| Coi role admin trong JWT là quyền vĩnh viễn | Quyền cũ còn tới khi token hết hạn | TTL/revocation/JIT theo rủi ro |
| Dùng aud=all-services không có kiểm soát | Token quá rộng giữa microservices | Resource-specific tokens |
| Forward user token sang downstream sai audience | Token confusion, token leakage | Token exchange/credential phù hợp |
| Tin X-Verified-Scopes từ request Internet | Mạo danh quyền qua header | Gateway sanitize, backend trust restriction |
| Dựa vào CORS để bảo vệ API | Non-browser clients vẫn gửi request | OAuth/AuthZ ở server |
| Tin private IP hoặc VPN là có quyền API | Bypass khi network exposure thay đổi | AuthN/AuthZ trên từng API |
| Token chứa nhiều quyền không cần thiết | Tăng tác động khi lộ | Scope tối thiểu, audience hẹp |
| Bỏ qua kid/JWKS rotation errors bằng verify=false | API chấp nhận token giả | Quản lý key rotation và fail mode |
| Không kiểm tra tenant context | Cross-tenant disclosure | Verified tenant + DB-level isolation |
| Ghi access token vào logs/URL | Replay và lộ bí mật | Redaction, header transport, retention |
| Không test negative cases | Không phát hiện quyền thừa | Ma trận tests cross-audience, scope, object |

### 19.1. CORS không phải authorization

**Cross-Origin Resource Sharing (CORS)** là cơ chế trình duyệt giới hạn việc một trang có thể đọc response từ origin khác. Một curl client, một service backend hoặc một ứng dụng tùy chỉnh không bị CORS ràng buộc theo cùng cách.

**Không dùng Access-Control-Allow-Origin** làm tiêu chí duy nhất để quyết định API có được gọi. API vẫn cần kiểm tra token, scopes, audience và quyền dữ liệu.

### 19.2. Rate limiting không phải authorization

Rate limiting giới hạn tốc độ theo user/client/IP/route được xác minh, hữu ích chống lạm dụng và quá tải. Nhưng một người gọi được phép gửi 1 request/giây vẫn có thể truy cập trái phép nếu **object authorization bị thiếu**. Chặn nhiều request không sửa được lỗ hổng quyền trên từng request.

## 20. Ma trận phân quyền cho hệ thống API giả lập

Giả sử một doanh nghiệp có ba resource servers:

- **Orders API:** quản lý đơn hàng của khách.
- **Billing API:** quản lý hóa đơn và đối soát thanh toán.
- **Audit API:** phục vụ nhân viên bảo mật và vận hành.

Với mỗi API, định nghĩa **resource identifier, nhóm scope, vai trò/ngữ cảnh và điều kiện dữ liệu**.

| API | Audience được chấp nhận | Operation | Required scope | Kiểm tra bổ sung |
| --- | --- | --- | --- | --- |
| Orders | https://orders.api.example.test | GET /orders/{id} | orders.read | User được xem order của tenant/assignment phù hợp |
| Orders | https://orders.api.example.test | POST /orders | orders.write | Tenant active, payload hợp lệ, quota/owner rule |
| Orders | https://orders.api.example.test | POST /orders/{id}/cancel | orders.cancel | User có quyền, đơn còn trạng thái hủy được |
| Billing | https://billing.api.example.test | GET /invoices/{id} | billing.read | Đúng tenant và quyền đối với hóa đơn |
| Billing | https://billing.api.example.test | POST /reconciliations | billing.reconcile | Chỉ workload hoặc vai trò vận hành được duyệt |
| Audit | https://audit.api.example.test | GET /events | admin.audit.read | Vai trò audit, giới hạn bộ dữ liệu và thời gian |

**Ma trận này chưa đủ để triển khai** nếu thiếu rules trên từng HTTP method, authn flow, policy version và cơ chế xác thực token. Nó là cơ sở để nhóm API, IAM và SOC thống nhất ai có quyền gì.

### 20.1. Ví dụ bốn request với cùng token

Giả sử access token **T1** được AS xác minh có:

~~~text
iss = https://identity.example.test
aud = https://orders.api.example.test
scope = "orders.read"
sub = user-0042
tenant = tenant-a
~~~

| Request | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| GET Orders /orders/42 | Order 42 thuộc tenant-a và user-0042 được quyền đọc | **Allow** |
| POST Orders /orders | Token thiếu orders.write | **Deny** |
| GET Billing /invoices/42 | Token audience Orders, không phải Billing | **Deny** ngay từ kiểm tra token cho Billing |
| GET Orders /orders/900 | Order 900 thuộc tenant-b hoặc không được user cấp quyền | **Deny** dù aud và orders.read đúng |

**Bài kiểm tra quan trọng nhất** là hai tình huống cuối: chúng tách biệt rõ lỗi dùng token **sai resource** với lỗi **quyền đối tượng**.

### 20.2. Token khác issuer

Một token được phát hành bởi **https://other-identity.example.test** không tự được chấp nhận chỉ vì chứa aud Orders và scope orders.read. RS phải dựa vào danh sách issuer tin cậy và **key binding theo issuer**. Nếu hỗ trợ nhiều issuers, mỗi issuer cần hợp đồng audience/claim mapping và chính sách riêng.

## 21. Chính sách YAML trung lập với nhà cung cấp

Đây là tài liệu **mô tả ý định bảo mật**, không phải cấu hình chạy trực tiếp trên API gateway, Spring Security, Envoy, Nginx, Kong, cloud API gateway hoặc IdP:

~~~yaml
apiAuthorizationPolicy:
  name: scoped-audience-authorization
  environment: isolated-training
  trust:
    acceptedIssuer: https://identity.example.test
    jwksSource: managed-issuer-metadata
    allowedSigningAlgorithms:
      - RS256
      - ES256
    requireSignatureVerification: true
    rejectUnsignedTokens: true
    requireAccessTokenTypeValidation: true
    requireExpirationCheck: true
    requireNotBeforeCheck: when-present
    clockSkew: bounded-by-security-policy
  resourceServers:
    - name: orders-api
      audience: https://orders.api.example.test
      tokenProfile: issuer-approved-oauth-access-token
      defaultAction: deny
      operations:
        - method: GET
          path: /orders/{id}
          scopesAll:
            - orders.read
          additionalPolicy:
            - verified-tenant-boundary
            - object-ownership-or-approved-assignment
        - method: POST
          path: /orders
          scopesAll:
            - orders.write
          additionalPolicy:
            - tenant-active
            - payload-and-business-validation
        - method: POST
          path: /orders/{id}/cancel
          scopesAll:
            - orders.cancel
          additionalPolicy:
            - object-ownership-or-approved-assignment
            - cancellation-state-allowed
    - name: billing-api
      audience: https://billing.api.example.test
      tokenProfile: issuer-approved-oauth-access-token
      defaultAction: deny
      operations:
        - method: GET
          path: /invoices/{id}
          scopesAll:
            - billing.read
          additionalPolicy:
            - verified-tenant-boundary
            - invoice-access-policy
    - name: audit-api
      audience: https://audit.api.example.test
      tokenProfile: issuer-approved-oauth-access-token
      defaultAction: deny
      operations:
        - method: GET
          path: /events
          scopesAll:
            - admin.audit.read
          additionalPolicy:
            - active-auditor-role
            - approved-data-scope
  propagation:
    neverForwardTokensToWrongAudience: true
    downstreamTokenExchange: only-by-authorized-client
    stripUntrustedIdentityHeaders: true
    preserveTrustedIdentityViaAuthenticatedChannel: true
  tokenLifecycle:
    enforceShortLivedAccess: risk-based
    manageRevocationAndRoleChanges: true
    supportSigningKeyRotation: true
    prohibitBearerTokenInQueryOrLogs: true
  defenseInDepth:
    tlsClientToGateway: required
    tlsGatewayToBackend: verify-upstream-identity
    denyDirectBackendExposure: true
    protectIpv4AndIpv6: true
    applicationResourceAuthorization: required
  observability:
    logIssuerAudienceScopeDecision: without-token-secrets
    logPolicyAndResourceId: minimal-necessary
    monitorCrossAudienceRejections: true
    monitorMissingScopesAndObjectDenials: true
    auditPolicyChanges: true
  governance:
    requireApiScopeCatalogOwner: true
    reviewPrivilegedScopes: true
    requireApprovedChanges: true
    testPositiveAndNegativeCases: true
    keepRollbackPlan: true
~~~

**Lưu ý về danh sách thuật toán:** RS256 và ES256 trong mẫu chỉ minh họa lựa chọn theo hợp đồng mật mã. Hệ thống thực tế **chỉ cho những thuật toán/khóa đã được AS và RS phê duyệt**, không phải tự bật tất cả thuật toán để “tương thích”.

Các trường như **scopesAll**, **tokenProfile** hoặc **requireAccessTokenTypeValidation** cần được chuyển sang tính năng và claim conventions **thực sự có trên nền tảng**. Một YAML mô tả deny không chứng minh product đã enforce.

## 22. Giả mã resource server: xác minh rồi mới cấp quyền

Giả mã sau minh họa trách nhiệm tách biệt giữa token validation, scope checking và resource authorization. Đây **không phải mã chạy được hoặc một triển khai JWT parser mới**.

~~~text
function authorizeRequest(request, apiConfig):
    credential = extractAccessTokenFromApprovedTransport(request)
    if credential is missing:
        return deny401("missing_token")

    validated = trustedOAuthTokenValidator.validate(
        credential,
        trustedIssuers = apiConfig.trustedIssuers,
        requiredAudience = apiConfig.audience,
        acceptedTokenProfiles = apiConfig.acceptedTokenProfiles,
        signingKeyAndAlgorithmPolicy = apiConfig.keyPolicy,
        requiredTemporalClaims = apiConfig.timePolicy
    )
    if validated is invalid:
        return deny401("invalid_token")

    matchedOperation = apiConfig.operations.match(
        normalizedPath = request.path,
        method = request.method
    )
    if matchedOperation is missing:
        return denyByDefault()

    if not validated.hasAllExactScopes(matchedOperation.requiredScopes):
        return deny403("insufficient_scope")

    principal = mapValidatedSubjectAndClient(validated)
    resource = loadResourceWithinVerifiedContext(
        resourceId = request.path.resourceId,
        tenant = principal.verifiedTenantContext
    )

    if not businessPolicy.isAllowed(principal, matchedOperation, resource):
        return denyAccordingToResourceDisclosurePolicy()

    return executeApprovedOperation(principal, resource)
~~~

### 22.1. Những bất biến cần bảo đảm

- **trustedOAuthTokenValidator** phải là thư viện/bộ xác minh phù hợp, không chỉ base64-decode JSON.
- **requiredAudience** đến từ cấu hình server, không lấy từ aud hoặc Host do client tùy ý gửi.
- **hasAllExactScopes** so khớp những scope đã được xác minh theo profile và chính sách.
- **resource** phải được lấy theo tenant/quyền đúng, không chỉ id do client khai.
- **denyByDefault** bao gồm route mới hoặc method mới chưa được bảo vệ.
- **HTTP response** không nên tiết lộ token, key material hay những chi tiết xác minh nhạy cảm.

### 22.2. Kiểm tra ở gateway và backend

Nếu gateway đã xác thực access token, backend có thể **tự xác minh token** lần nữa hoặc sử dụng ngữ cảnh tin cậy được truyền qua một cơ chế đã được bảo vệ; cách triển khai phụ thuộc kiến trúc. Nhưng backend không được **tin header do client trực tiếp đặt** hoặc bỏ qua object authorization.

### 22.3. Không lẫn lộn mã lỗi

Một token **sai aud** không trở thành hợp lệ vì endpoint có scope tương ứng; hệ thống nên từ chối trong bước token validation. Nếu token đúng API nhưng thiếu scope, bước resource policy cần trả deny rõ ràng theo quy tắc đã chọn.

## 23. Thử request hợp lệ trong môi trường được cấp phép

Các ví dụ sau chỉ dùng trong **lab hoặc API do bạn được phép kiểm thử**. Không dùng token thật của người khác, không xuất token ra log và không thử endpoint ngoài phạm vi.

### 23.1. Yêu cầu qua HTTPS

~~~bash
# Chạy trong lab với ACCESS_TOKEN do AS lab cấp.
# Không đưa token trực tiếp vào URL, log hoặc tài liệu.
curl --fail-with-body \
  --header "Authorization: Bearer $ACCESS_TOKEN" \
  --header "Accept: application/json" \
  "https://orders.api.example.test/orders/42"
~~~

**Domain example.test chỉ là minh họa**; phải thay bằng tên dịch vụ lab được kiểm soát khi thực hành. Tùy phiên bản curl, tùy chọn --fail-with-body có thể không tồn tại; sử dụng chức năng tương ứng của phiên bản đang cài nếu cần.

Không sử dụng **-k/--insecure** để bỏ qua xác minh TLS trong phép thử xác thực token. Việc API cho phép Bearer token nhưng TLS bị bỏ xác minh có thể khiến credential lộ ở đường truyền.

### 23.2. Kiểm tra HTTP status và log

Trong môi trường lab, kết quả **200** chưa chứng minh đã có kiểm tra object-level authorization; có thể đó là dữ liệu công khai hoặc user test có nhiều quyền. Hãy kết hợp:

- Positive test với token có đúng aud, scope, object.
- Negative test với sai aud và thiếu scope.
- Negative test với đúng aud/scope nhưng sai user/tenant.
- Gateway/backend logs để xác định **rule nào thực thi**.

### 23.3. Vì sao không giải mã token trên website không tin cậy?

Một access token là credential; đưa nguyên token lên một website debug hoặc chat công khai có thể làm lộ quyền truy cập. Nếu cần phân tích JWT trong lab, dùng công cụ được tổ chức cho phép, **chỉ đưa payload đã được làm giả hoặc che bí mật**, và hiểu rằng chỉ giải mã không xác minh signature.

## 24. Giám sát authorization theo scope và audience

**Một request bị chặn** có thể là hoạt động hợp lệ nhưng client dùng nhầm token, lỗi cấu hình route hoặc hành vi dò quyền. SOC/NOC cần log đủ để phân loại, tránh mặc định mọi 403 là tấn công.

### 24.1. Những trường cần có

| Trường | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Timestamp / request ID / trace ID | Gateway và backend | Ghép sự kiện xuyên nhiều dịch vụ |
| API/service name | Resource server | Biết audience nào đáng lẽ được chấp nhận |
| Token issuer (đã xác minh nếu có) | Token validator | Phân biệt issuer được tin hoặc token sai |
| Expected audience | API config | Cơ sở quyết định đúng resource |
| Actual audience classification | Validator | Phân biệt match/mismatch; hạn chế ghi dữ liệu token không cần thiết |
| Required vs granted scope category | AuthZ layer | Xác định thiếu quyền theo operation |
| Client ID và subject pseudonym | AS/validator | Phân biệt workload, ứng dụng và user |
| Tenant/record class | Application policy | Phân tích cross-tenant và BOLA |
| Validation reason | Validator | invalid_signature, expired, wrong_audience, unknown_kid... |
| Authorization outcome | API | allow/deny và rule ID |
| Policy/config version | Deployment | Liên kết lỗi với thay đổi mới |
| Network context | Proxy/TLS layer | IP đã xác minh, upstream route, mTLS state khi cần |

**Không lưu access token, refresh token, Authorization header, DPoP private key, client secret hoặc raw session cookie** trong log. Nếu cần correlation, sử dụng ID phù hợp, hash có kiểm soát hoặc các mã sự kiện không cho phép tái sử dụng credential.

### 24.2. Log giả lập: sai audience

~~~json
{
  "timestamp": "2026-11-28T18:10:00+07:00",
  "environment": "synthetic-training",
  "event": "api_token_validation_failed",
  "request_id": "lab-api-req-101",
  "resource_server": "billing-api",
  "trusted_issuer": "https://identity.example.test",
  "expected_audience": "https://billing.api.example.test",
  "presented_audience_classification": "orders-api-token",
  "validation_stage": "audience",
  "reason": "wrong_audience",
  "http_status": 401,
  "application_operation_executed": false,
  "access_token_recorded": false
}
~~~

Trong ví dụ, token có thể vẫn hợp lệ cho **Orders API**. Việc Billing từ chối là đúng bởi **resource mismatch**; cần kiểm tra client hoặc luồng token exchange trước khi quy kết hành vi xâm nhập.

### 24.3. Log giả lập: đủ scope nhưng sai tenant

~~~json
{
  "timestamp": "2026-11-28T18:12:00+07:00",
  "environment": "synthetic-training",
  "event": "api_resource_authorization_denied",
  "request_id": "lab-api-req-102",
  "resource_server": "orders-api",
  "verified_audience": "https://orders.api.example.test",
  "scope_check": "orders.read:pass",
  "subject_ref": "user-0042",
  "verified_tenant": "tenant-a",
  "resource_tenant": "tenant-b",
  "policy_rule": "deny-cross-tenant-order",
  "decision": "deny",
  "http_status": 403,
  "resource_data_returned": false,
  "access_token_recorded": false
}
~~~

Đây là ví dụ **token đúng audience/scope nhưng object-level authorization từ chối**. Nó chứng minh cần **hai cấp quyền khác nhau**; không nên gộp hai lỗi thành “token invalid”.

### 24.4. Những cảnh báo đáng quan tâm

- Một **client ID** liên tục trình token cho nhiều APIs có audience không phù hợp.
- Tăng đột ngột **insufficient_scope** sau thay đổi issuer, client registration hoặc gateway route.
- Một token hợp lệ cố truy cập nhiều IDs/tenants không được cấp phép.
- Resource server mới **không có audience check** hoặc dùng wildcard audience.
- Sự kiện **unknown kid** hoặc invalid signature tăng sau AS key rotation.
- Token được cấp scopes mạnh hoặc nhiều audiences ngoài baseline.
- API backend bị gọi **ngoài đường gateway dự kiến**.
- Tài khoản hoặc service bị thu hồi quyền nhưng phiên/token cũ vẫn được chấp nhận quá SLA.

## 25. Lộ trình triển khai và quản trị scope/audience

### Bước 1 – Kiểm kê resource servers

Liệt kê từng API, hostname, backend, public/internal route, audience identifier và điểm TLS termination. Phân biệt **Orders**, **Billing**, **Admin** và các service theo mức tin cậy. Không dùng một audience chung nếu không có lý do kiến trúc được phê duyệt.

### Bước 2 – Xây dựng catalog scope

Với mỗi API operation:

1. Định nghĩa **required scope(s)**.
2. Mô tả user/workload role nào có thể được AS cấp.
3. Ghi rõ scope có **read/write/export/admin** và rủi ro tương ứng.
4. Gắn **object/tenant/business policy** phải kiểm tra sau scope.
5. Chỉ định owner và versioning khi đổi ý nghĩa scope.

### Bước 3 – Thiết lập issuer và token profile

Thống nhất **trusted issuer, JWKS, token format, audience, time claims và scope claim mapping**. Nếu có nhiều issuers, tách rõ từng chính sách và khóa tin cậy.

### Bước 4 – Rà soát client và OAuth flows

Client tương tác người dùng nên dùng flow phù hợp, thường là **authorization code với PKCE** trong các trường hợp được khuyến nghị; workload có thể dùng **client credentials** khi đúng điều kiện. Cách client xin scopes/audience phải được AS hỗ trợ và phê duyệt. Không gán mọi client toàn bộ scope để “tránh lỗi 403”.

### Bước 5 – Thực thi tại gateway và backend

Gateway kiểm tra access token và coarse policy, backend kiểm tra object/tenant/business. Kiểm tra header trust chain, TLS/mTLS upstream, firewall và đường bypass, kể cả IPv6/cloud.

### Bước 6 – Positive và negative tests

Kiểm thử các cặp đúng/sai issuer, audience, scopes, role, subject, tenant, object và token type. Kiểm tra thiếu token, token hết hạn, JWKS rotation và introspection outage theo môi trường.

### Bước 7 – Staged rollout

Triển khai theo API/operation, canary và policy version, có cảnh báo 401/403 tăng bất thường. Thống nhất cơ chế xử lý client cũ; **không bỏ audience check** chỉ để tránh lỗi tương thích.

### Bước 8 – Vòng đời và rà soát

Định kỳ kiểm tra scopes được cấp, token TTL, client registrations, endpoint mới, các route exempt, nhóm workload quyền cao, thời gian thu hồi và log correlation. Đánh giá lại khi có microservice mới, tenant mới hoặc thay đổi gateway topology.

## 26. Ma trận kiểm thử an toàn trong lab

Các phép thử sau chỉ dùng **token, client và API giả lập thuộc hệ thống bạn quản lý hoặc được phép kiểm thử**. Không thử token thật của người khác, không khai thác dữ liệu production và không đưa credential vào file/log công khai.

| Mã | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| T-01 | Token hợp lệ, đúng issuer/aud Orders, scope orders.read, order thuộc user | **Allow** đọc order đúng quyền |
| T-02 | Token Orders dùng gọi Billing | **Deny** vì wrong audience |
| T-03 | Token đúng Billing nhưng thiếu billing.read | **Deny** vì insufficient scope |
| T-04 | Token đúng Orders và orders.read nhưng đọc order tenant khác | **Deny** theo object/tenant policy |
| T-05 | Token đúng Orders nhưng ký bằng key không tin cậy | **Deny** invalid signature |
| T-06 | Token do issuer khác không được RS tin cấp, claims trông hợp lệ | **Deny** invalid issuer |
| T-07 | Token hết exp hoặc chưa đến nbf | **Deny** theo time policy |
| T-08 | JWT header thử algorithm không được cho phép/unsigned | **Deny** theo key/algorithm policy |
| T-09 | ID token OIDC được trình như Orders access token | **Deny** sai token type/audience/profile |
| T-10 | Scope claim chứa billing.read, operation cần orders.read | **Deny**, không so substring |
| T-11 | Token có audience array trong profile cho phép, chứa đúng Orders | Áp chính sách và test scope/object; không tự allow mọi route |
| T-12 | Token có aud array nhưng không có Orders | **Deny** wrong audience |
| T-13 | Token opaque active=true nhưng audience API khác | **Deny** wrong audience |
| T-14 | Introspection unavailable trong lab | Không tự allow-all; cache/fail mode đúng thiết kế |
| T-15 | Orders đổi token đúng policy để gọi Billing | Billing xác minh token downstream và quyền resource |
| T-16 | Orders chuyển nguyên token sai aud sang Billing | Billing **deny** |
| T-17 | Client credentials token không đại diện user cố gọi endpoint user-delegated | **Deny** nếu endpoint yêu cầu user context |
| T-18 | Token đủ scope nhưng trạng thái order không cho cancel | **Deny** theo business policy |
| T-19 | Client tự gửi X-Verified-Scopes hoặc X-Verified-User | Gateway xóa/ghi đè; không tạo quyền |
| T-20 | Backend có đường direct origin trong lab | Firewall/authz chặn theo policy; không bypass gateway |
| T-21 | Thu hồi role/disable user trong khi token còn hạn | Hành vi revoke/recheck đáp ứng SLA đã phê duyệt |
| T-22 | AS xoay signing key hợp lệ | Token mới được xác minh, token cũ xử lý theo overlap đã duyệt |
| T-23 | API qua IPv6 hoặc failover route | Cùng kiểm tra issuer/aud/scope/object như IPv4 |
| T-24 | DPoP/mTLS sender binding đúng hoặc proof sai trong lab hỗ trợ | Token bị ràng buộc nguồn và proof được kiểm tra đúng |

### 26.1. Bằng chứng cho mỗi ca

1. **Environment, API/audience, operation, required scopes** và policy version.
2. Token profile và **metadata đã che bí mật**, không ghi bearer token thật.
3. Kết quả xác minh issuer/signature/time/audience.
4. Kết quả scope và object/tenant authorization riêng rẽ.
5. HTTP response code và log tại **đúng lớp enforcement**.
6. Xác minh **request không đến backend** nếu gateway có trách nhiệm chặn, hoặc **không trả dữ liệu** nếu backend từ chối.
7. Ảnh hưởng tới client hợp lệ và phương án rollback.

### 26.2. Vì sao chỉ có HTTP 403 chưa đủ?

Một 403 có thể đến từ gateway, WAF, application hoặc rule mạng. Để kết luận **audience check đã chặn đúng**, cần log cho thấy **token bị từ chối ở bước audience validation**, không phải do endpoint offline hoặc backend tùy tiện trả 403.

### 26.3. Kiểm thử một ca “đúng token nhưng sai dữ liệu”

Với hai tenants giả lập A và B, cấp token Orders hợp lệ cho user thuộc A. Yêu cầu đọc một order thuộc B **phải bị từ chối**, dù token có aud Orders và orders.read. Đây là phép thử trọng yếu của authorization ở tầng đối tượng.

## 27. Runbook khi phát hiện sai quyền scope/audience

Giả sử SOC phát hiện Billing API trả dữ liệu cho một client vốn chỉ có access token dành cho Orders API. Sự kiện có thể do lỗi config, một đường backend bỏ validation hoặc service mới dùng chung authentication middleware không đúng.

### Giai đoạn 1 – Xác minh

1. Ghi **request ID, API, thời điểm, client ID, issuer, expected audience, actual audience classification và policy version**.
2. Kiểm tra token profile và kết quả xác minh chữ ký/issuer/time; **không lưu token thật trong ticket**.
3. Xem request đi qua gateway nào, có bypass hoặc alternate LB/VPN route hay không.
4. Kiểm tra Billing có thực sự **thực hiện operation và trả dữ liệu** hay chỉ có response code/log nhầm.
5. Đối chiếu thay đổi gần nhất ở AS token claims, API audience configuration, gateway/backend và service deployment.
6. Ước lượng những clients/tokens khác chịu ảnh hưởng cùng rule.

### Giai đoạn 2 – Khoanh vùng

- Sửa audience allowlist của Billing cho đúng **resource identifier** được phê duyệt.
- Đảm bảo backend không dựa vào header scope/role từ nguồn không được xác minh.
- Nếu bị lộ bearer tokens, kích hoạt quy trình revoke/shorten TTL theo năng lực AS và đánh giá scope/audience của token liên quan.
- Hạn chế đường backend bypass qua firewall/mTLS/API gateway khi phù hợp.
- Không cấp một audience **all** hoặc tắt signature validation để “sửa nhanh” sai cấu hình.
- Với thay đổi có thể ảnh hưởng dịch vụ, dùng staged rollout, rollback và giám sát.

### Giai đoạn 3 – Xác minh sửa lỗi

1. Token Orders gọi Orders hợp lệ: **allow** theo scope/object.
2. Cùng token gọi Billing: **deny** ở audience validation.
3. Token Billing có scope hợp lệ nhưng thiếu quyền object: **deny**.
4. Token Billing đúng mọi điều kiện: **allow**.
5. Direct backend/IPv6/failover: không bypass authorization.
6. App và gateway logs gắn đúng request ID, không chứa token bí mật.

### Giai đoạn 4 – Đánh giá tác động và rút kinh nghiệm

Nếu dữ liệu có thể đã bị truy cập sai, kết hợp logs của gateway, API, database và tenant để xác định bản ghi nào bị trả ra theo bằng chứng. Ghi timeline, nguyên nhân gốc, thời gian phát hiện, phạm vi dữ liệu và thay đổi phòng ngừa. **Không suy rằng một request có HTTP 200 chắc chắn đã đọc dữ liệu nhạy cảm** nếu chưa đối chiếu body/result và application logs; nhưng cũng không phủ nhận nguy cơ khi bằng chứng chưa đầy đủ.

## 28. Tình huống tổng hợp: token Orders bị dùng nhầm ở Billing

Một ứng dụng khách hàng có hai chức năng: xem đơn hàng và xem hóa đơn. Ứng dụng dùng OIDC đăng nhập người dùng và nhận access token **audience Orders**, mang scope orders.read.

Ở phiên bản mới, client sử dụng lại token này để gọi **Billing API** vì cho rằng “người dùng đã đăng nhập một lần thì token có thể dùng ở mọi dịch vụ”. Billing gateway chỉ kiểm tra signature và exp từ issuer chung, nhưng chưa kiểm tra aud. Kết quả Billing xử lý request dù token không dành cho dịch vụ này.

### 28.1. Sai lầm nằm ở đâu?

- **Ở client:** dùng token không đúng resource server; cần xin token đúng audience hoặc sử dụng flow được AS hỗ trợ.
- **Ở Billing:** thiếu audience validation, cho phép **token substitution/cross-audience use**.
- **Ở quản trị:** thiếu matrix audience-to-API và kiểm thử negative.
- **Ở kiến trúc nhiều dịch vụ:** nếu Billing được gọi thông qua Orders, cần thiết kế token exchange/credential riêng và quyền user/tenant, không chuyển token tùy ý.

### 28.2. Không chữa bằng cách mở thêm quyền

Một phản ứng sai là sửa Billing để chấp nhận **Orders audience** hoặc cấp mọi token **billing.read**. Điều này **mở rộng quyền** và che lấp vấn đề. Cần xác định client flow đúng, AS cấp token đúng target và Billing xác minh bắt buộc.

### 28.3. Kịch bản sau khi sửa

| Request | Token | Kết quả |
| --- | --- | --- |
| GET Orders /orders/42 | aud Orders, orders.read, owner đúng | Allow |
| GET Billing /invoices/42 | aud Orders, orders.read | Deny wrong audience |
| GET Billing /invoices/42 | aud Billing, billing.read, invoice đúng tenant/owner | Allow |
| GET Billing /invoices/99 | aud Billing, billing.read, invoice tenant khác | Deny object authorization |
| GET Billing /invoices/42 | ID token có aud client_id | Deny token type/profile |

### 28.4. Kết luận

**Audience kiểm soát token được chấp nhận tại đâu; scope kiểm soát nhóm thao tác token được phép yêu cầu; resource-level authorization kiểm soát trên dữ liệu nào.** Cả ba điều kiện phải được xác minh độc lập theo đúng nguồn tin cậy.

## 29. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

Scope và audience khác nhau ở mục đích nào?

**Gợi ý:** audience xác định API/resource dự kiến; scope xác định quyền thao tác được cấp trong ngữ cảnh token.

### Câu hỏi 2

Vì sao một JWT có signature hợp lệ và scope billing.read vẫn phải bị Billing từ chối nếu aud chỉ có Orders?

**Gợi ý:** token không được cấp cho Billing, nên không hợp lệ như credential của Billing.

### Câu hỏi 3

Vì sao access token khác ID token, đặc biệt ở ý nghĩa aud?

**Gợi ý:** ID token dành cho OIDC client, access token dành cho resource server được cấp; không dùng ID token thay access token.

### Câu hỏi 4

Hai token đều có orders.read nhưng một token cho phép đọc order 42, token kia không. Điều này có thể đúng không?

**Gợi ý:** Có. Quyền user/tenant/resource ownership được kiểm tra độc lập với scope.

### Câu hỏi 5

Nhận được opaque token với kết quả introspection **active=true** có đủ cho phép API đọc dữ liệu chưa?

**Gợi ý:** Chưa. Cần kiểm tra audience, scope, resource, issuer/context và chính sách.

### Câu hỏi 6

Tại sao API không nên dùng phép **substring** để kiểm tra scope?

**Gợi ý:** tên scopes là các định danh độc lập theo hợp đồng; cần so khớp tokenized exact values.

### Câu hỏi 7

Một service Orders cần gọi Billing nhân danh user. Những lựa chọn an toàn hơn việc gửi nguyên token Orders là gì?

**Gợi ý:** token exchange/on-behalf-of được AS cho phép hoặc credential riêng theo ngữ nghĩa workload.

### Câu hỏi 8

Issuer được tin công bố signing key mới nhưng API báo unknown kid. Có nên tắt verify để hoạt động không?

**Gợi ý:** Không. Kiểm tra metadata/JWKS cache, key rotation, cấu hình issuer và chính sách fail mode.

### Câu hỏi 9

Bearer token có aud/scope đúng nhưng bị lộ. DPoP/mTLS, TTL và revocation đóng vai trò gì?

**Gợi ý:** giảm khả năng token bị sử dụng bởi bên không sở hữu key, giảm thời gian token có thể bị dùng, thu hồi quyền theo khả năng hệ thống.

### Câu hỏi 10

Vì sao CORS, VPN và API gateway đều không thay thế được authorization theo object và tenant?

**Gợi ý:** CORS là hạn chế browser; VPN là đường kết nối; gateway có thể chỉ biết coarse policy, không biết mọi quyền dữ liệu.

### Câu hỏi 11

Khi nào nên trả 401, khi nào nên trả 403 đối với token không hợp lệ và thiếu scope?

**Gợi ý:** 401 thường cho credential không được chấp nhận; 403 thường cho credential đã xác thực nhưng bị từ chối quyền, tùy profile và chính sách API.

### Câu hỏi 12

Một client credentials token gọi API endpoint dành cho tác vụ chỉ user mới được làm. Vì sao API cần từ chối dù scope có vẻ đúng?

**Gợi ý:** endpoint có yêu cầu subject type/delegation và user/business context, không chỉ scope string.

### Bài tập thiết kế

Một doanh nghiệp triển khai **Orders API**, **Billing API**, **Reporting API** và **Audit API** dưới API gateway, có cả mobile clients và workloads trong Kubernetes. Hãy:

1. Chỉ định **audience/resource identifier riêng** cho từng API và những issuers được tin.
2. Thiết kế **catalog scope**, phân biệt quyền đọc, ghi, hủy, đối soát và xuất báo cáo.
3. Xây dựng ma trận **HTTP/RPC operation → audience → scopes → object/tenant authorization**.
4. Vẽ luồng một mobile client xin token để xem đơn hàng và một workload gọi Billing theo client credentials.
5. Mô tả khi nào dùng **token exchange** khi Orders API cần gọi Billing thay user; chỉ rõ vì sao token Orders không nên được chuyển tiếp nguyên trạng.
6. Viết rules cho JWT và opaque token: issuer, signature/introspection, audience, token type, time claims, scope và resource rights.
7. Lập ít nhất **mười positive/negative tests**, gồm wrong aud, missing scope, ID token misuse, cross-tenant, JWT key rotation và API bypass.
8. Thiết kế logs không lộ token, có request ID, policy version và lý do deny riêng cho gateway và backend.
9. Đề xuất cách xử lý khi một user rời tổ chức nhưng token cũ chưa hết hạn.
10. Giải thích vai trò bổ sung của **TLS/mTLS, firewall, WAF, rate limiting, DNS, VPN và IDS/IPS** với authorization của API.

**Tiêu chí đạt:** mỗi API có audience rõ, mỗi operation có scope phù hợp, mỗi object/tenant được kiểm tra theo quyền thật và hệ thống chứng minh được điều kiện **từ chối** chứ không chỉ trường hợp được phép.

## 30. Những điều cần ghi nhớ

- **Audience (aud) giới hạn resource server nào được phép chấp nhận token**; token đúng chữ ký nhưng sai audience phải bị từ chối.
- **Scope giới hạn khả năng được cấp cho access token**, theo ngữ nghĩa AS và API đã thỏa thuận; không tự là role hoặc quyền đọc mọi object.
- **ID token không phải access token**; không chấp nhận token sai loại, issuer, profile hoặc audience.
- **JWT phải được xác minh chữ ký, issuer, time claims, algorithm/key và audience** trước khi tin scope; opaque token cần introspection đáng tin theo chính sách.
- **Endpoint scope checking và object/tenant/business authorization là hai bước độc lập**; cả hai cần thiết để hạn chế BOLA/BFLA.
- **Token chỉ nên có audience/scopes tối thiểu**. Không tự truyền access token của API này sang API khác; dùng token exchange hoặc credential phù hợp với quyền thật.
- **Bearer token bị lộ có thể bị dùng lại**; TTL, bảo vệ secrets, revocation và DPoP/mTLS khi phù hợp giúp giảm rủi ro nhưng không thay Authorization.
- **API gateway kiểm soát coarse policy, backend vẫn cần kiểm tra tài nguyên và chống bypass** bằng TLS, firewall, service identity và policy dữ liệu.
- **401, 403 và audit logs phải phản ánh đúng lý do kỹ thuật**, không tiết lộ access token hoặc thông tin nhạy cảm.
- **Kiểm thử positive và negative cases từ issuer/audience/scope đến tenant/object**, bao gồm thay đổi quyền theo thời gian và đường IPv4/IPv6, là cách chứng minh policy được thực thi.


