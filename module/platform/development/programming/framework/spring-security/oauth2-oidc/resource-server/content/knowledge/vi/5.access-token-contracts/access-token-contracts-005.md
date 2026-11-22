# Scope, roles, permissions và quy tắc cấp quyền do hệ thống quy định

Trong một hệ thống dùng **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, access token có thể chứa `scope`, `roles`, `permissions` và các thông tin về chủ thể. Các thông tin này giúp API quyết định request có được thực hiện hay không, nhưng **tên claim xuất hiện trong token không tự tạo ra một quy tắc phân quyền chung cho mọi hệ thống**.

OAuth 2.0 chuẩn hóa cơ chế **xin, cấp và sử dụng quyền truy cập**. Còn các câu hỏi như “`orders.read` cho phép đọc loại đơn hàng nào?”, “nhân viên hỗ trợ có được xem đơn của tenant khác không?”, “role `ADMIN` có quyền hủy đơn hay chỉ xem báo cáo?” cần được **hệ thống phát hành token và API thỏa thuận, định nghĩa và thực thi rõ ràng**.

> **Trọng tâm của bài:** Scope mô tả phạm vi quyền đã được cấp cho một access token; role mô tả vai trò của chủ thể theo mô hình tổ chức/ứng dụng; permission mô tả hành động cụ thể được phép. Chính sách phân quyền kết hợp những dữ kiện này với tài nguyên và ngữ cảnh request. Spring Security chuyển một số claim thành **GrantedAuthority** để kiểm tra, nhưng không tự hiểu quyền nghiệp vụ nếu ứng dụng chưa quy định.

## 1. Đặt scope, role, permission vào đúng vị trí

Giả sử hệ thống bán hàng gồm:

- **Shop Web**: OAuth2 Client dùng để yêu cầu và sử dụng access token.
- **Identity Server**: Authorization Server xác thực và cấp token.
- **Orders API**: Resource Server bảo vệ dữ liệu đơn hàng.
- **Order Service / Database**: nơi lưu owner, tenant, trạng thái đơn và các quy tắc nghiệp vụ.

Một request thông dụng:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Để trả đơn hàng 42, Orders API cần trả lời **nhiều câu hỏi**, chứ không chỉ xem chuỗi `scope`:

1. Token có hợp lệ, do issuer tin cậy phát hành và dành cho `orders-api` không?
2. Token có quyền **gọi thao tác đọc đơn hàng** không?
3. Chủ thể trong token là người dùng hay ứng dụng? Vai trò và permission nào được thừa nhận?
4. Đơn hàng 42 thuộc tenant/owner nào, có đang ở trạng thái được phép đọc không?
5. Chính sách hiện hành có cho **chủ thể này** thực hiện **hành động này** trên **đối tượng đó** trong **ngữ cảnh request** hay không?

Phân biệt các khái niệm ngay từ đầu:

| Khái niệm | Trả lời câu hỏi | Ví dụ | Nguồn/ngữ nghĩa |
| --- | --- | --- | --- |
| **Scope** | Access token này được cấp cho phạm vi thao tác nào? | `orders.read`, `orders.write` | Client đề nghị; Authorization Server cấp theo chính sách; API định nghĩa cách sử dụng |
| **Role** | Chủ thể đang có vai trò gì trong tổ chức/ứng dụng? | `ORDER_SUPPORT`, `TENANT_ADMIN` | Hệ thống định danh hoặc ứng dụng quản lý; chỉ có ý nghĩa theo miền và tenant đã quy định |
| **Permission** | Chủ thể có khả năng thực hiện hành động cụ thể nào? | `order:read:own`, `order:read:tenant` | Mô hình quyền do hệ thống định nghĩa; có thể được cấp trực tiếp hoặc suy ra từ role |
| **Policy / quy tắc cấp quyền** | Trong hoàn cảnh này, cho phép hay từ chối? | “Có scope đọc, có quyền đọc đơn của mình và đúng tenant” | Resource Server/lớp nghiệp vụ thực thi từ token đã xác minh và dữ liệu đáng tin |
| **Authority trong Spring Security** | Tập chuỗi quyền nội bộ để biểu thức security đối chiếu | `SCOPE_orders.read`, `ROLE_ORDER_SUPPORT`, `PERM_order:read:own` | Được tạo từ authentication và converter/cấu hình ứng dụng |

Đừng đồng nhất **role với scope**, **permission với claim** hay **authority với mọi thứ có trong JWT**. Chúng liên hệ với nhau qua **hợp đồng chuyển đổi và chính sách** do đội phát triển xác lập.

## 2. Scope: phạm vi quyền của access token

### 2.1. Scope là khái niệm của OAuth 2.0

Trong OAuth 2.0, Client có thể đề nghị một hoặc nhiều **scope** bằng tham số `scope` khi xin quyền/token. Theo cách biểu diễn phổ biến trong giao thức, scope là các chuỗi phân biệt chữ hoa/chữ thường, được phân tách bằng dấu cách.

Ví dụ:

~~~text
scope=orders.read orders.write
~~~

Authorization Server xem xét đăng ký của Client, loại grant, quyền của chủ thể và các điều kiện bảo mật để quyết định **scope được cấp thực tế**. Scope Client đề nghị không tự động trở thành scope mà Client được cấp.

Access token dạng JWT có thể thể hiện kết quả cấp quyền như:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

Trong ví dụ, Client có thể đã xin `orders.read orders.write`, nhưng token **chỉ mang `orders.read`**. Khi gọi endpoint ghi dữ liệu, Orders API phải dựa vào scope đã được xác minh từ token, không tin vào scope Client từng yêu cầu.

**Scope là một tập tên quyền được thỏa thuận; bản thân tên không tự có nghĩa nghiệp vụ toàn cục.** OAuth 2.0 không định nghĩa rằng `orders.write` luôn bao gồm `orders.read`, hay `admin` cho phép mọi hành động. Nếu hệ thống muốn có quan hệ bao hàm giữa các scope, quan hệ ấy phải được định nghĩa và thực thi rõ ràng.

### 2.2. Scope là quyền ở mức API, thường khá thô

Một hợp đồng scope có thể là:

| Scope | Ý nghĩa đã thỏa thuận | Endpoint có thể yêu cầu |
| --- | --- | --- |
| `orders.read` | Được phép yêu cầu đọc đơn hàng theo chính sách dữ liệu | `GET /api/orders/{id}` |
| `orders.create` | Được phép yêu cầu tạo đơn hàng | `POST /api/orders` |
| `orders.cancel` | Được phép yêu cầu hủy đơn hàng | `POST /api/orders/{id}/cancel` |
| `reports.export` | Được phép gọi chức năng xuất báo cáo | `POST /api/reports/export` |

Nên hiểu `orders.read` là **quyền bước đầu để gọi thao tác đọc**, không phải bằng chứng cho phép đọc **tất cả** đơn hàng. Quyền vào từng bản ghi phụ thuộc tenant, owner, vai trò, trạng thái hoặc các điều kiện khác.

### 2.3. Tên scope thuộc hợp đồng giữa nhà phát hành và API

Thực tế có nhiều cách đặt tên: `orders.read`, `read:orders`, `api://orders/read`. Không có một tên duy nhất được OAuth 2.0 chuẩn hóa cho hành động đọc đơn hàng.

Client, Authorization Server và Resource Server phải thống nhất:

- Chính tả tên scope, phân biệt chữ hoa/chữ thường.
- Ý nghĩa và endpoint tương ứng.
- Client/loại grant nào được xin và được cấp.
- Quy tắc scope có bao hàm nhau hay phải kiểm tra tách biệt.
- Nguồn claim thể hiện scope trong JWT hoặc kết quả introspection.

Đặc biệt, `openid`, `profile` và `email` là các scope **OIDC** phục vụ yêu cầu danh tính ở Client; chúng **không mặc nhiên thay thế** scope nghiệp vụ như `orders.read` của Orders API.

## 3. Roles: vai trò của chủ thể trong hệ thống

**Role** mô tả một nhóm trách nhiệm hoặc vị trí của chủ thể trong một miền nghiệp vụ. Ví dụ:

- `CUSTOMER`: khách hàng có thể thao tác trên đơn hàng của chính mình.
- `ORDER_SUPPORT`: nhân viên hỗ trợ đơn hàng trong tenant được giao.
- `TENANT_ADMIN`: người quản trị một tenant nhất định.
- `PLATFORM_AUDITOR`: nhân sự có quyền xem dữ liệu audit theo chính sách kiểm toán.

Role thường thuộc mô hình **Role-Based Access Control (RBAC)**: hệ thống gán role cho chủ thể, gán permission cho role, rồi đánh giá quyền theo các role hiện hành.

~~~mermaid
flowchart LR
    User["Chủ thể: user-842"] --> Role["Role: ORDER_SUPPORT"]
    Role --> Perm1["Permission: order:read:tenant"]
    Role --> Perm2["Permission: order:comment"]
    Perm1 --> Policy["Quy tắc API + tenant + dữ liệu"]
    Perm2 --> Policy
    Policy --> Decision["Cho phép hoặc từ chối"]
~~~

Role không phải một claim bắt buộc của JWT. Authorization Server có thể phát hành role trong `roles`, `realm_access.roles` hoặc claim có namespace riêng; nhiều hệ thống **không đưa role vào token** mà Resource Server tự tra cứu từ database, policy service hoặc dịch vụ phân quyền.

### 3.1. Role không tự xác định một hành động

Role `ORDER_SUPPORT` **không có nghĩa phổ quát** là được hủy đơn, chỉnh giá, xuất báo cáo hoặc truy cập tenant khác. Cần một bảng ánh xạ role → permission và các ràng buộc nghiệp vụ rõ ràng.

Ví dụ hợp đồng của một tổ chức:

| Role | Permission được gán | Phạm vi hiệu lực |
| --- | --- | --- |
| `CUSTOMER` | `order:read:own`, `order:cancel:own` | Đơn hàng của chính người dùng, khi trạng thái cho phép |
| `ORDER_SUPPORT` | `order:read:tenant`, `order:comment:tenant` | Đơn trong tenant được phân công |
| `TENANT_ADMIN` | `order:read:tenant`, `order:export:tenant` | Tenant do người dùng quản trị |
| `PLATFORM_AUDITOR` | `audit:read` | Dữ liệu audit trong phạm vi được cấp |

Đây chỉ là **ví dụ chính sách**. Một hệ thống khác có thể định nghĩa role cùng tên nhưng permission rất khác.

### 3.2. Role theo tenant khác role toàn cục

Trong mô hình multi-tenant, một người có thể là `TENANT_ADMIN` của tenant A nhưng chỉ là `CUSTOMER` ở tenant B. Nếu access token chứa `"roles": ["TENANT_ADMIN"]` mà không có ngữ cảnh tenant, API có nguy cơ áp dụng nhầm quyền quản trị cho tenant khác.

Hợp đồng cần chọn một cách biểu diễn rõ ràng, chẳng hạn:

~~~json
{
  "sub": "user-842",
  "aud": ["orders-api"],
  "tenant_id": "tenant-A",
  "roles": ["TENANT_ADMIN"]
}
~~~

Khi ấy API phải xác minh tenant của **resource được truy cập**, tenant gắn với role và tư cách thành viên còn hiệu lực theo chính sách. Nếu một token dành cho nhiều tenant, cần thiết kế claim/nguồn chính sách có thể biểu diễn **role theo từng tenant**, không chỉ một mảng role toàn cục.

## 4. Permissions: hành động cụ thể trên tài nguyên

**Permission** thường mô tả một khả năng chi tiết hơn role, chẳng hạn:

~~~text
order:read:own
order:read:tenant
order:comment:tenant
order:cancel:own
order:refund:approved
report:export:tenant
~~~

Các tên trên không do OAuth 2.0 hay Spring Security chuẩn hóa. Chúng là quy ước của ví dụ. Trong thiết kế thực tế, permission có thể là chuỗi, mã số, object chính sách hoặc dữ liệu trong policy engine.

Role thường trả lời **“chủ thể thuộc nhóm trách nhiệm nào?”**; permission trả lời **“nhóm/chủ thể ấy có loại khả năng nào?”**. Còn quyết định cuối cùng có thể cần điều kiện **“được áp dụng lên bản ghi nào, trong trạng thái nào?”**.

Ví dụ với permission `order:cancel:own`:

~~~text
Có permission "order:cancel:own"
        AND order.owner == authenticatedSubject
        AND order.tenant == authorizedTenant
        AND order.status IN [NEW, CONFIRMED]
        => có thể hủy theo chính sách
~~~

Nếu order đã giao vận hoặc thuộc người khác, quyền `order:cancel:own` **không tự động** khiến hành động hủy hợp lệ.

### 4.1. Permission có thể nằm trong token hoặc ở backend

Hai cách triển khai phổ biến:

| Cách quản lý permission | Ưu điểm | Giới hạn cần xử lý |
| --- | --- | --- |
| **Đưa permissions vào access token** | API có thể kiểm tra nhanh các permission được issuer chứng thực; ít phụ thuộc tra cứu online | Quyền có thể thay đổi trước khi token hết hạn; token có thể lớn; phải kiểm tra chính xác issuer/audience và ngữ nghĩa claim |
| **Tra cứu permission phía API/policy service** | Có thể áp dụng quyền hiện tại và chính sách phụ thuộc dữ liệu | Cần quản lý độ trễ, khả dụng, cache và nguồn dữ liệu đáng tin |

Có thể kết hợp: token mang scope/identity/tenant, còn Resource Server tra cứu role và permission hiện tại. Không có một mô hình duy nhất phù hợp mọi hệ thống.

### 4.2. Không nhầm permission với một claim tùy ý do Client gửi

Nếu API nhận:

~~~http
X-Role: TENANT_ADMIN
X-Permissions: order:read:tenant
~~~

thì những header này **không đáng tin chỉ vì Client đã gửi**. Chúng có thể bị giả mạo. Resource Server chỉ sử dụng role/permission khi nguồn của chúng đáng tin: claim từ token đã xác minh, hệ thống session/identity nội bộ được bảo vệ, hoặc dữ liệu phân quyền do server quản lý.

## 5. Quy tắc cấp quyền: từ token tới quyết định truy cập

**Authorization policy** là quy tắc xác định một subject có thể thực hiện một action trên một resource trong context nào. Có thể biểu diễn ngắn gọn:

~~~text
allow = authenticated_token
    AND intended_for_this_api
    AND required_scope
    AND required_permission_or_role_policy
    AND resource_constraints
    AND contextual_constraints
~~~

Đây là **mô hình minh họa**; một số tổ chức xây policy theo tập luật allow/deny, ưu tiên deny, hoặc áp dụng permission riêng thay vì yêu cầu cùng lúc mọi loại claim. Quy tắc kết hợp phải được viết thành hợp đồng rõ ràng.

### 5.1. Ví dụ chính sách theo endpoint và bản ghi

| Hành động | Scope cần có | Điều kiện role/permission | Ràng buộc dữ liệu |
| --- | --- | --- | --- |
| Xem đơn của bản thân | `orders.read` | `order:read:own` | `sub` khớp owner; đúng tenant |
| Nhân viên xem đơn để hỗ trợ | `orders.read` | `order:read:tenant` hoặc role tương ứng | Đơn trong tenant/nhóm được phân công |
| Khách hàng hủy đơn | `orders.cancel` | `order:cancel:own` | Chủ đơn; trạng thái được phép hủy |
| Xuất báo cáo tenant | `reports.export` | `report:export:tenant` | Tenant hợp lệ; tuân thủ giới hạn dữ liệu |
| Batch service đồng bộ đơn | `orders.sync` | Client/service principal nằm trong danh sách được phép | Chỉ dữ liệu, thời điểm và mục đích đã cấp |

Một token có đủ scope nhưng thiếu permission phù hợp có thể bị từ chối. Ngược lại, token có role hỗ trợ nhưng thiếu `orders.read` cũng không nhất thiết được gọi endpoint đọc; hợp đồng ở ví dụ này yêu cầu **cả scope và điều kiện role/permission**.

### 5.2. Ba nhóm quy tắc quen thuộc

- **RBAC (Role-Based Access Control):** Quyết định dựa trên role và các permission gắn với role.
- **ABAC (Attribute-Based Access Control):** Quyết định dựa trên thuộc tính subject, resource và môi trường như tenant, owner, trạng thái hoặc địa điểm.
- **ReBAC (Relationship-Based Access Control):** Quyết định dựa trên quan hệ giữa các đối tượng, ví dụ người dùng là thành viên của nhóm sở hữu đơn.

Các hệ thống thực tế có thể kết hợp chúng. Scope thường làm “cửa đầu vào” của API, còn RBAC/ABAC/ReBAC giải quyết các ràng buộc nghiệp vụ chi tiết.

### 5.3. Nguồn sự thật của quyền phải được xác định

Khi các nguồn không thống nhất, API cần một thứ tự tin cậy:

1. **Token:** Chỉ sử dụng claim đã xác minh và phù hợp hợp đồng issuer/audience/token type.
2. **Dữ liệu danh tính/quyền:** Chỉ nhận role hoặc permission từ issuer đáng tin hoặc nguồn phía server được quản lý.
3. **Dữ liệu tài nguyên:** Lấy owner/tenant/status từ database hoặc nguồn nghiệp vụ có thẩm quyền, không tin ID tenant do Client tự khai.
4. **Chính sách hiện hành:** Áp dụng quy tắc được cấu hình phiên bản phù hợp; nếu thiếu dữ liệu quyết định quan trọng thì từ chối theo nguyên tắc fail closed.

**Authorization Server quyết định cấp token/scope theo chính sách phát hành; Resource Server quyết định truy cập tài nguyên theo chính sách API.** Việc AS cấp `orders.read` không đồng nghĩa AS đã kiểm tra quyền đọc đơn hàng số 42.

## 6. Ai kiểm soát phần nào trong hợp đồng access token?

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server
    participant DB as Order DB / Policy Store

    U->>C: Yêu cầu xem đơn hàng
    C->>AS: Xin token với scope orders.read
    AS->>AS: Kiểm tra Client, grant, user và policy
    AS-->>C: Token được cấp (scope thực tế)
    C->>RS: GET /api/orders/42 + access token
    RS->>RS: Verify chữ ký, iss, aud, exp
    RS->>RS: Đọc scope/roles/permissions đáng tin
    RS->>DB: Lấy order, tenant, owner, trạng thái
    DB-->>RS: Dữ liệu chính thức
    RS->>RS: Áp dụng policy
    RS-->>C: 200 hoặc từ chối 401/403/404
~~~

| Bên | Trách nhiệm chính đối với quyền |
| --- | --- |
| **Client** | Xin scope cần thiết; sử dụng access token được cấp; không tự tăng scope/role/permission |
| **Authorization Server** | Kiểm tra Client/chủ thể/grant; quyết định scope/claim được cấp; ký hoặc bảo vệ token; công bố định dạng và ngữ nghĩa |
| **Resource Server** | Xác minh token; kiểm tra audience, scope/authority; tra cứu dữ liệu cần thiết và thực thi chính sách hành động/tài nguyên |
| **Dịch vụ quản lý quyền/nghiệp vụ** | Duy trì role, permission, tenant membership, ownership, trạng thái đối tượng và các chính sách thay đổi theo thời gian |

Resource Server có thể tự chứa policy hoặc gọi một dịch vụ quyết định quyền riêng. Dù ở đâu, **API phải kiểm soát việc sử dụng kết quả**, không mặc định rằng token hợp lệ đồng nghĩa “allow”.

## 7. Claims và authorities của Spring Security

Trong Spring Security, **`GrantedAuthority`** là biểu diễn quyền được gắn với một đối tượng `Authentication`. Framework dùng các authority đó để đánh giá `hasAuthority(...)`, `hasRole(...)` và những biểu thức truy cập khác.

**Authority là mô hình nội bộ của Spring Security, không phải một trường chuẩn bắt buộc của JWT.** Khi Resource Server xác thực JWT thành công, Spring Security tạo `JwtAuthenticationToken` và chuyển claim được chọn thành authorities qua `JwtGrantedAuthoritiesConverter` hoặc converter tùy chỉnh.

### 7.1. Mapping scope mặc định

Với JWT có claim `scope` hoặc `scp` theo định dạng được hỗ trợ, converter mặc định của Spring Security thường thêm tiền tố **`SCOPE_`**.

Ví dụ:

~~~json
{
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel"
}
~~~

Sau khi token được xác minh, danh sách authority có thể là:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Trong cấu hình HTTP:

~~~java
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

**Lưu ý:** `hasAuthority("orders.read")` không khớp với `SCOPE_orders.read` nếu giữ converter mặc định. Tên authority phải khớp chính xác chuỗi được cấp trong `Authentication`.

### 7.2. `hasRole` và tiền tố `ROLE_`

Spring Security thường diễn giải:

~~~java
hasRole("ORDER_SUPPORT")
~~~

tương ứng với authority:

~~~text
ROLE_ORDER_SUPPORT
~~~

Trong khi đó:

~~~java
hasAuthority("ROLE_ORDER_SUPPORT")
~~~

kiểm tra trực tiếp đúng chuỗi authority này. Quy ước `ROLE_` là cơ chế của Spring Security, **không có nghĩa JWT buộc phải có claim `role` hoặc `roles`**.

Nếu access token chứa `"roles": ["ORDER_SUPPORT"]`, converter JWT mặc định **không tự bảo đảm** sẽ tạo `ROLE_ORDER_SUPPORT`. Phải xác định nguồn claim và cấu hình cách ánh xạ theo hợp đồng.

### 7.3. Chọn quy ước authority không va chạm

Trong một hệ thống có scope, role và permission, có thể thống nhất:

| Nguồn đã xác minh | Dạng claim ví dụ | GrantedAuthority nội bộ |
| --- | --- | --- |
| Scope | `"scope": "orders.read"` | `SCOPE_orders.read` |
| Role | `"roles": ["ORDER_SUPPORT"]` | `ROLE_ORDER_SUPPORT` |
| Permission | `"permissions": ["order:read:tenant"]` | `PERM_order:read:tenant` |

Cách đặt `PERM_` là **quy ước do ứng dụng tự đặt**, không phải prefix mặc định của Spring Security. Việc dùng tiền tố giúp tránh trùng lặp ngữ nghĩa giữa các nguồn claim, nhưng chỉ hiệu quả nếu converter và policy cùng tuân thủ.

## 8. Ví dụ Resource Server nhận JWT và ánh xạ quyền

Ví dụ dưới đây sử dụng Spring Boot 3 / Spring Security 6 và giả sử **Authorization Server đã phát hành JWT access token** theo hợp đồng:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-842",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["ORDER_SUPPORT"],
  "permissions": ["order:read:tenant"],
  "tenant_id": "tenant-A",
  "exp": 1893459600
}
~~~

Trong hợp đồng ví dụ, `roles` và `permissions` là **mảng chuỗi**; tên role là giá trị không có tiền tố `ROLE_`, tên permission là giá trị không có tiền tố `PERM_`.

### 8.1. Dependency và issuer

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test

app:
  security:
    audience: orders-api
~~~

Issuer trong ví dụ là placeholder cho môi trường được quản lý. Khi triển khai thực tế, API phải dùng đúng issuer do Authorization Server công bố và có thể bổ sung `jwk-set-uri` nếu kiến trúc cần chỉ định JWKS trực tiếp.

### 8.2. Bảo vệ API bằng scope

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/*/cancel")
                    .hasAuthority("SCOPE_orders.cancel")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đoạn này tập trung vào quyền theo scope tại HTTP layer. Trong một API Bearer-token stateless, cấu hình CSRF và session phải được đánh giá theo kiến trúc cụ thể; nếu cùng ứng dụng có website dùng session cookie, cần bảo vệ luồng đó tương ứng.

### 8.3. Tự ánh xạ role và permission từ claim đáng tin

Spring Security có thể kết hợp mapping scope mặc định với mapping role/permission do ứng dụng định nghĩa:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
class JwtAuthoritiesConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();

        JwtAuthenticationConverter authenticationConverter =
                new JwtAuthenticationConverter();

        authenticationConverter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Collection<GrantedAuthority> authorities =
                    new ArrayList<>(scopes.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    authorities.add(
                            new SimpleGrantedAuthority("ROLE_" + role));
                }
            }

            List<String> permissions =
                    jwt.getClaimAsStringList("permissions");
            if (permissions != null) {
                for (String permission : permissions) {
                    authorities.add(
                            new SimpleGrantedAuthority("PERM_" + permission));
                }
            }
            return authorities;
        });

        return authenticationConverter;
    }
}
~~~

Để dùng converter này, liên kết nó với cấu hình Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)))
        .build();
}
~~~

Đây là **biến thể thay thế** cho bean `apiSecurity` ở mục 8.2 để minh họa việc gắn converter; khi áp dụng vào dự án, gộp các rule endpoint cần thiết trong **một** bean phù hợp, không khai báo hai bean trùng tên. Chỉ ánh xạ `roles` và `permissions` như trên khi issuer, audience và định dạng claim đã được xác minh theo hợp đồng. Nếu nhà phát hành sử dụng role theo tenant hoặc claim nested, logic mapping phải phản ánh đúng cấu trúc và ngữ nghĩa đó.

Trong một hệ thống nhiều issuer, **không áp dụng mù quáng cùng một phép ánh xạ role cho mọi token**. Claim `ADMIN` của issuer A không mặc nhiên tương đương với `ADMIN` của issuer B. Cấu hình xác minh và mapping cần gắn với nguồn phát hành tương ứng.

### 8.4. Kiểm tra issuer, thời hạn và audience

Cấu hình chỉ có issuer giúp API xác minh nguồn phát hành theo khả năng của Spring Security, nhưng còn cần kiểm tra **token dành cho Orders API**. Ví dụ khi tự tạo `JwtDecoder`:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class TokenValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri,
            @Value("${app.security.audience}") String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token is not intended for this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(standard, audience));
        return decoder;
    }
}
~~~

Cấu hình bổ sung cho ví dụ:

~~~yaml
app:
  security:
    issuer: https://identity.example.test
    jwks-uri: https://identity.example.test/.well-known/jwks.json
    audience: orders-api
~~~

URI JWKS là ví dụ, cần thay bằng endpoint thật được issuer tin cậy công bố. Nếu một ứng dụng tự cung cấp `JwtDecoder`, phải bảo toàn việc kiểm tra chữ ký, thuật toán được phép, issuer, thời gian và các điều kiện profile; đừng thay validator mặc định bằng một kiểm tra `aud` đơn lẻ. Resource Server cũng nên phân biệt access token với ID token theo profile phát hành để tránh nhận sai mục đích.

### 8.5. Kiểm tra quyền theo phương thức

Với `@EnableMethodSecurity`, có thể bảo vệ một phương thức nghiệp vụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderQueryService {

    private final OrderRepository orders;
    private final OrderAccessPolicy accessPolicy;

    OrderQueryService(
            OrderRepository orders,
            OrderAccessPolicy accessPolicy) {
        this.orders = orders;
        this.accessPolicy = accessPolicy;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') and " +
        "(hasAuthority('PERM_order:read:own') or " +
        "hasAuthority('PERM_order:read:tenant'))")
    public OrderDto getOrder(String id, CallerContext caller) {
        Order order = orders.findById(id)
                .orElseThrow(OrderNotFoundException::new);

        // Kiểm tra tenant, owner và quyền trên chính bản ghi.
        accessPolicy.assertCanRead(caller, order);
        return OrderDto.from(order);
    }
}
~~~

Các kiểu `OrderRepository`, `OrderAccessPolicy`, `CallerContext`, `OrderDto` và `OrderNotFoundException` là thành phần nghiệp vụ minh họa, không phải class có sẵn của Spring Security. `CallerContext` phải được tạo từ `Authentication` đã xác minh cùng dữ liệu server đáng tin; **không được tin đối tượng caller do request body tự khai**.

Biểu thức `@PreAuthorize` ở đây lọc coarse-grained scope và permission. `assertCanRead` tiếp tục kiểm tra điều kiện cụ thể như:

~~~text
order.tenantId == caller.authorizedTenantId
AND (
    (caller.has("order:read:own") AND order.ownerSubject == caller.subject)
    OR caller.has("order:read:tenant")
)
~~~

Nếu role/permission được tra cứu động từ database, `accessPolicy` có thể đưa quyết định từ nguồn đó thay vì phụ thuộc hoàn toàn vào authorities trong JWT. Điểm quan trọng là **thực thi chính sách trên resource thật**, không chỉ kiểm tra claim ở filter.

## 9. Quy trình cấp token khác quy trình kiểm tra request

### 9.1. Ở Authorization Server: quyết định cấp scope

Trong luồng Authorization Code, quyết định cấp scope có thể dựa trên:

- Client đã đăng ký được phép xin những scope nào.
- Người dùng đã xác thực hay chưa và có những quyền nào.
- Consent có cần không và nếu cần thì người dùng đồng ý gì.
- Tài nguyên/audience mà token được cấp.
- Chính sách tổ chức, tenant và yêu cầu bảo mật.

Ví dụ Shop Web đăng ký `orders.read`, `orders.cancel`. Khi người dùng chưa có quyền hủy, Authorization Server có thể chỉ cấp `orders.read`. Quyết định thực tế tùy chính sách, nhưng **Client không thể tự thêm `orders.cancel` bằng cách sửa payload token**.

Trong luồng `client_credentials`, token có thể đại diện cho chính ứng dụng/dịch vụ, không có người dùng cuối. Scope cần được cấp dựa trên danh tính Client và quyền của dịch vụ; API không được tự coi `sub` trong token này là ID khách hàng.

### 9.2. Ở Resource Server: đánh giá quyền trên request

Một request sau khi nhận Bearer token đi qua các bước:

~~~mermaid
flowchart TD
    A["Nhận access token"] --> B{"Chữ ký/issuer/thời hạn/audience hợp lệ?"}
    B -->|Không| C["401 Unauthorized"]
    B -->|Có| D{"Có scope endpoint yêu cầu?"}
    D -->|Không| E["403 Forbidden"]
    D -->|Có| F{"Role/permission theo chính sách?"}
    F -->|Không| E
    F -->|Có| G{"Owner/tenant/trạng thái cho phép?"}
    G -->|Không| H["403 hoặc 404 theo chính sách"]
    G -->|Có| I["Thực thi hành động"]
~~~

Tình huống thiếu token hoặc token không hợp lệ thường dẫn đến 401; token đã xác thực nhưng thiếu quyền thường dẫn đến 403. Khi cần tránh tiết lộ sự tồn tại của bản ghi, API có thể trả 404 theo chính sách. Hành vi cụ thể còn chịu ảnh hưởng từ cấu hình entry point, access denied handler và ứng dụng.

## 10. Sự khác nhau giữa scope, role và permission trong các luồng phổ biến

### 10.1. Người dùng gọi API qua Client

Token minh họa:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "customer-47",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.cancel",
  "roles": ["CUSTOMER"],
  "permissions": ["order:read:own", "order:cancel:own"],
  "tenant_id": "tenant-A"
}
~~~

Giả sử token đã qua xác minh và chưa hết hạn. `customer-47` có thể thử xem/hủy đơn của mình theo scope, permission và trạng thái đơn. Token này **không cấp quyền đọc đơn của khách khác**, kể cả cùng tenant, khi chính sách không cho phép.

### 10.2. Nhân viên hỗ trợ cùng tenant

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "support-12",
  "aud": ["orders-api"],
  "client_id": "support-console",
  "scope": "orders.read",
  "roles": ["ORDER_SUPPORT"],
  "permissions": ["order:read:tenant"],
  "tenant_id": "tenant-A"
}
~~~

Role/permission của nhân viên hỗ trợ cho phép đọc các đơn mà họ được phân công trong `tenant-A`. Nếu hệ thống có giới hạn theo nhóm hoặc khu vực, API vẫn cần áp dụng giới hạn đó; claim `order:read:tenant` không nhất thiết có nghĩa toàn tenant trong mọi thiết kế.

### 10.3. Service-to-service bằng client credentials

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "nightly-sync",
  "client_id": "nightly-sync",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

`nightly-sync` là một Client dịch vụ, không nhất thiết có role của người dùng. Orders API có thể cho phép endpoint `/internal/sync` khi token dành đúng audience, mang scope `orders.sync` và Client đáp ứng chính sách dịch vụ. API không nên gán quyền `CUSTOMER` chỉ vì token có `sub`.

Nếu service muốn gọi API **thay mặt người dùng**, việc chuyển tiếp token hoặc token exchange cần quy tắc delegation rõ ràng. Một token có audience cho Service A không tự nhiên hợp lệ cho Service B.

## 11. Những sai lầm thường gặp khi định nghĩa quyền

### “Có role ADMIN thì bỏ qua scope”

Một role mang tên `ADMIN` có thể chỉ có hiệu lực trong một tenant hoặc ứng dụng. Nếu hợp đồng API yêu cầu `orders.read`, role đó không tự thay thế scope. Muốn có ngoại lệ cho admin, cần định nghĩa và thực thi riêng, đồng thời tránh biến một role cục bộ thành quyền toàn cục.

### “Có scope orders.read thì xem được mọi đơn hàng”

Scope thường giới hạn loại thao tác được gọi. API phải kiểm tra owner, tenant, assignment, trạng thái và các yếu tố nghiệp vụ khác.

### “Claim roles có trong JWT là Spring Security tự nhận biết”

Converter JWT mặc định chủ yếu ánh xạ scope từ claim được hỗ trợ thành `SCOPE_...`. Muốn sử dụng `roles` hoặc `permissions` theo cấu trúc riêng, phải cấu hình converter hoặc cơ chế policy phù hợp.

### “Client gửi X-Permissions thì API nên dùng”

Client không được tự khẳng định quyền bằng header hay JSON request. Quyền phải đến từ issuer đã xác minh hoặc nguồn dữ liệu phía server được bảo vệ.

### “Permission cấp trong JWT luôn cập nhật tức thì”

JWT đã phát hành có thể giữ claim quyền cũ tới khi hết hạn, trừ khi hệ thống dùng cơ chế kiểm tra/thu hồi bổ sung. Với nghiệp vụ nhạy cảm, nên kết hợp token sống ngắn, introspection, kiểm tra quyền hiện tại hoặc nguồn policy tập trung.

### “Scope giống nhau thì mọi issuer đều đáng tin”

Claim `scope = orders.read` của hai issuer khác nhau không chứng minh cùng mức tin cậy. Resource Server phải kiểm tra issuer, audience, khóa và profile token; chỉ dùng claim theo hợp đồng của issuer đã chấp thuận.

### “Đăng nhập OIDC thành công nghĩa là có quyền gọi Orders API”

OIDC xác thực người dùng cho Client. ID token và các scope `openid profile email` không tự cấp quyền đọc đơn hàng. API cần **access token đúng audience và quyền nghiệp vụ**.

### “Chỉ kiểm tra annotation là đủ”

`@PreAuthorize("hasRole('ORDER_SUPPORT')")` có thể bảo vệ chức năng tổng quát, nhưng chưa chắc kiểm tra việc nhân viên có được truy cập **đơn hàng cụ thể** hoặc **tenant cụ thể**. Authorization cần đến tầng dữ liệu.

## 12. Thiết kế hợp đồng access token có thể triển khai

Một hợp đồng quyền cho Orders API nên ghi rõ:

| Thành phần | Thỏa thuận ví dụ | Bên thực thi |
| --- | --- | --- |
| Issuer | `https://identity.example.test` | AS phát; API xác minh |
| Audience | `orders-api` | AS phát; API xác minh |
| Loại token | OAuth2 access token, không chấp nhận ID token làm Bearer API | AS/Client/API |
| Scope đọc đơn | `orders.read` | AS cấp; API kiểm tra |
| Role claim | `roles` là mảng string với `CUSTOMER`, `ORDER_SUPPORT`... | AS phát hoặc API tra cứu; API ánh xạ |
| Permission claim | `permissions` là mảng string theo bảng permission | AS phát hoặc API tra cứu; API ánh xạ |
| Prefix Spring | `SCOPE_`, `ROLE_`, `PERM_` | API cấu hình |
| Tenant | `tenant_id` và quy tắc liên kết tenant với subject/role | AS hoặc policy store; API kiểm tra |
| Data policy | Owner, tenant, nhóm được phân công, trạng thái đơn | API nghiệp vụ |
| Quyền của service principal | Scope/Client được phép gọi API nội bộ | AS và API |
| Cập nhật quyền | Thời hạn token, cách thu hồi/cache/tra cứu quyền mới | AS/API |
| Phản hồi lỗi | 401 token sai; 403 thiếu quyền; 404 khi cần giấu tài nguyên | API |

Để dễ vận hành, bảng permission có thể dùng cấu trúc rõ ràng:

~~~yaml
# Minh họa tài liệu hợp đồng; không phải cấu hình chuẩn mà Spring tự đọc.
api: orders-api
scope_contract:
  orders.read: "May request order read endpoints"
  orders.cancel: "May request order cancellation"
role_mapping:
  CUSTOMER:
    - order:read:own
    - order:cancel:own
  ORDER_SUPPORT:
    - order:read:tenant
    - order:comment:tenant
policy:
  read_order:
    required_scope: orders.read
    required_any_permission:
      - order:read:own
      - order:read:tenant
    requires_tenant_match: true
    requires_ownership_for: order:read:own
  cancel_order:
    required_scope: orders.cancel
    required_permission: order:cancel:own
    requires_owner_match: true
    allowed_order_statuses:
      - NEW
      - CONFIRMED
~~~

Trong tài liệu thật, cần thêm quy tắc khi role/permission vắng mặt, cách kiểm soát scope được cấp cho từng Client, phạm vi tenant, thay đổi policy và cách quan sát lỗi. Nếu hệ thống dùng policy engine, mẫu YAML này có thể được chuyển thành cấu trúc của engine; nếu không, lập trình viên đưa quy tắc vào tầng bảo mật và nghiệp vụ có kiểm soát.

## 13. Bài tập tư duy theo tình huống

**Tình huống A:** Token có `orders.read`, `ROLE_ORDER_SUPPORT`, nhưng Order 42 ở tenant khác.

Kết quả theo hợp đồng ví dụ: **từ chối**. Scope và role không vượt qua ranh giới tenant.

**Tình huống B:** Token có `roles = ["TENANT_ADMIN"]` nhưng không có `orders.cancel`. Client gửi yêu cầu hủy đơn.

Nếu API yêu cầu `orders.cancel`, request bị từ chối vì thiếu scope, kể cả role có tên “admin”. Muốn role cho phép hủy, phải có quy tắc nhất quán về scope, permission và tenant trong hợp đồng.

**Tình huống C:** Client xin `orders.read orders.cancel`, AS chỉ cấp `orders.read`.

Client được sử dụng token trong phạm vi đã cấp; API phải từ chối hủy đơn vì token không mang quyền đó. Client không thể nâng quyền bằng cách đổi payload hay gửi thêm tham số `scope` khi gọi API.

**Tình huống D:** Token mang `permissions = ["order:cancel:own"]`, nhưng Order 42 đã giao vận.

Ngay cả khi chủ đơn có permission và scope tương ứng, API từ chối nếu chính sách cấm hủy đơn đã giao. Permission mô tả khả năng, không loại bỏ điều kiện trạng thái.

**Tình huống E:** Token của job `client_credentials` có `orders.sync`, nhưng code API cố tìm người dùng dựa trên `sub`.

Đây là giả định sai về loại chủ thể. API phải áp dụng chính sách dành cho **service principal/Client** và không coi token dịch vụ là người dùng cuối.

## 14. Các câu hỏi cần trả lời trước khi đưa vào production

1. Scope được định nghĩa theo chức năng API hay theo vai trò người dùng? Từng scope có ý nghĩa/giới hạn nào?
2. AS quyết định scope được cấp theo Client, chủ thể và grant như thế nào? Client có thể xin quyền vượt phạm vi nào không?
3. Role do ai quản lý, có theo tenant hay toàn cục? Đã có bảng role → permission rõ ràng chưa?
4. Permission được phát trong token hay tra cứu server-side? Khi thu hồi quyền có cần hiệu lực tức thời không?
5. Resource Server có kiểm tra `iss`, `aud`, thời hạn, loại token và chữ ký trước khi đọc claim quyền không?
6. Converter Spring Security ánh xạ claim thành authority đúng tên và prefix không?
7. Chính sách owner, tenant, group, trạng thái, delegation được kiểm tra ở đâu?
8. Thiếu claim quyền hoặc dữ liệu policy thì API từ chối an toàn hay cho phép mặc định?
9. Có phân biệt token người dùng với `client_credentials` không?
10. API có trả mã 401/403/404 nhất quán và ghi log theo request ID mà không lộ Bearer token không?

**Ghi nhớ:** **Scope** giới hạn phạm vi access token được cấp; **role** biểu diễn vị trí của chủ thể trong mô hình nghiệp vụ; **permission** mô tả khả năng thao tác; còn **authorization policy** đưa ra quyết định trên một tài nguyên và ngữ cảnh cụ thể. Trong Spring Security Resource Server, mọi claim cần được đọc từ token đã xác minh và ánh xạ bằng hợp đồng rõ ràng; API vẫn phải kiểm tra quyền trên dữ liệu thực tế trước khi trả kết quả.
