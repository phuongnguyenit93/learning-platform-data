# Đồng bộ tài khoản bằng SCIM tại hệ thống chuyên trách và giới hạn của Spring Security

**SCIM (System for Cross-domain Identity Management)** là một bộ tiêu chuẩn để **cấp phát, cập nhật, vô hiệu hóa và quản lý dữ liệu danh tính** giữa hệ thống quản trị nguồn và ứng dụng đích. SCIM 2.0 được mô tả chủ yếu bởi **RFC 7643** (Core Schema) và **RFC 7644** (Protocol), dựa trên HTTP và JSON. SCIM thường phục vụ vòng đời **joiner–mover–leaver**: nhân viên mới được cấp account, chuyển nhóm được cập nhật quyền, nghỉ việc được vô hiệu hóa tài khoản ở các ứng dụng liên quan.

**Spring Security không phải một hệ thống SCIM provisioning/synchronization chuyên trách.** Nó cung cấp **authentication, SecurityContext, UserDetails, AuthenticationProvider, OAuth2/OIDC và authorization** cho một ứng dụng Spring; không tự chạy bộ điều phối đồng bộ danh tính đến hàng trăm hệ thống, không tự tạo các endpoint SCIM chuẩn, không tự triển khai reconciler, HR lifecycle, connector catalog hay giải quyết xung đột đa nguồn. Có thể dùng Spring Security **để bảo vệ một SCIM API do bạn xây**, và dùng dữ liệu account đã được SCIM provision **để quyết định login/authorization** trong ứng dụng; đó là hai trách nhiệm tách biệt.

**Quy tắc quan trọng:** **SCIM provisioning không đồng nghĩa SSO**, **SCIM group không tự là GrantedAuthority**, và **active=false tại hệ thống đích không mặc nhiên thu hồi mọi Spring session, OAuth token hay API key đã được phát trước đó**. Phải thiết kế luồng dữ liệu, identity mapping, account-state enforcement và revocation rõ ràng.

Bài thuộc **Spring Security – federation → Thư mục và tài khoản**, đi từ mô hình kiến trúc, Users/Groups schema, HTTP operations, deprovisioning, consistency, bảo mật, multi-tenant mapping đến ví dụ Spring Security, chương trình Java 17 độc lập và checklist production.

## 1. Khi nào cần SCIM thay vì chỉ có đăng nhập SSO?

Một tổ chức có nhân viên trong hệ thống nhân sự (HRIS), danh tính được quản lý tại IAM/IdP và hàng chục ứng dụng như CRM, kế toán, LMS, Helpdesk. Nếu chỉ cấu hình OIDC/SAML SSO:

- Người dùng có thể chứng minh danh tính khi đến trang đăng nhập.
- Ứng dụng chưa chắc **đã có tài khoản nội bộ**, license, cấu hình tenant hoặc nhóm.
- Người dùng nghỉ việc có thể còn dữ liệu account, quyền, session, API tokens trong hệ thống đích.
- Account có thể được tạo **Just-In-Time (JIT)** ở lần đăng nhập đầu tiên nhưng bị bỏ sót khi chưa từng login; xóa account cũng không tự xảy ra.
- Group/department/manager thay đổi ở HRIS không tự cập nhật sang mọi ứng dụng.
- Cần kiểm toán những ứng dụng nào còn tài khoản hoạt động cho một người.

SCIM giải quyết **data plane cấp phát danh tính**: service provisioning chuyên trách gửi lệnh tạo/sửa/disable Users và Groups tới SCIM endpoints được phê duyệt. SSO giải quyết **authentication plane**. Ứng dụng vẫn phải thực thi **authorization plane** theo chính sách riêng.

~~~text
       HRIS / Directory / IAM authoritative systems
                         |
                  Joiner / Mover / Leaver
                         |
                         v
        Identity Governance / Provisioning Engine
        - Xác định nguồn dữ liệu có thẩm quyền
        - Mapping schema & tenant
        - Quản lý connector, token, retry, audit
                         |
               SCIM 2.0 client requests
                         |
                  HTTPS + client auth
                         |
                         v
          Dedicated SCIM Service / SCIM Provider
          POST/GET/PATCH/PUT/DELETE Users, Groups
                         |
                Account + Membership Store
                         |
              +----------+------------+
              |                       |
              v                       v
       Business application     Authorization service
        Spring Security          entitlement/role policy
              |
        OIDC/SAML/other login
              |
      Check local account active,
      tenant and resource permissions
~~~

**Không bắt buộc dịch vụ SCIM và app business phải ở hai máy khác nhau**: với sản phẩm hỗ trợ SCIM native, chúng có thể trong cùng deployment. Tuy nhiên **trách nhiệm nghiệp vụ provisioning** vẫn cần component/owner riêng, không gán nó cho Spring Security core.

## 2. Các vai trò SCIM và ai sở hữu dữ liệu

| Vai trò | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Authoritative source** | Hệ thống quyết định một loại dữ liệu là sự thật | HRIS quản lý ngày nghỉ việc, directory quản lý account identity |
| **Provisioning engine / SCIM Client** | Đọc sự kiện/đối chiếu, gửi SCIM requests | IAM/IGA connector |
| **SCIM Service Provider** | REST API đích cung cấp Users/Groups | Dịch vụ provisioning của ứng dụng SaaS |
| **Target account repository** | Lưu danh tính và trạng thái trong app | Bảng users, memberships, entitlements |
| **Identity Provider / Authorization Server** | Xác thực, phát SAML/OIDC tokens | IdP doanh nghiệp |
| **Relying Party / Resource Server** | Tiếp nhận người dùng/token và kiểm quyền | Spring Boot Portal/API |
| **Business authorization owner** | Phê duyệt chính sách chức năng/tenant | Nhóm chủ sở hữu Billing |
| **Reconciliation/audit component** | Phát hiện sai lệch, khắc phục có kiểm soát | Provisioning job hoặc IGA |

**Không nhầm SCIM Client với browser của nhân viên**: SCIM Client thường là ứng dụng máy–máy có credentials riêng, gọi trực tiếp SCIM endpoint được bảo vệ. **Người dùng không cần tự gửi username/password vào SCIM** để đăng nhập.

## 3. SCIM giải quyết gì và không giải quyết gì?

| Câu hỏi | SCIM | Thành phần khác |
| --- | --- | --- |
| Tạo tài khoản tại ứng dụng đích? | **Có**, khi target hỗ trợ create | HRIS/IAM quyết định khi nào tạo |
| Cập nhật display name, email, department? | **Có**, theo schema/extension | Data owner quyết định đúng nguồn |
| Thêm/bỏ thành viên nhóm? | **Có**, qua Groups/members nếu target hỗ trợ | Authorization owner quyết định group tương ứng quyền nào |
| Khóa hoặc vô hiệu hóa user? | **Có thể**, thường `active=false` | App phải thực thi block login/sessions |
| Xóa user khỏi đích? | **Có**, DELETE theo provider contract | Retention, legal hold, audit do app/business |
| Đăng nhập người dùng bằng SSO? | **Không** | OIDC/SAML/Kerberos/other authentication |
| Xác thực mật khẩu mỗi request? | **Không** | Spring Security/IdP |
| Cấp OAuth access token cho user? | **Không phải chức năng SCIM** | Authorization Server |
| Tự chuyển Group thành ROLE_ADMIN? | **Không** | Application entitlement/role mapping |
| Thu hồi mọi session đã cấp? | **Không mặc định** | Session registry, logout/revocation strategy |
| Thiết kế workflow phê duyệt quyền? | **Không thuộc giao thức cốt lõi** | IAM/IGA, policy engine |
| Tự bảo đảm mọi target đồng bộ tức thì? | **Không** | Delivery/retry/reconciliation + SLA |
| Dedupe across tenants và identity brokers? | **Không tự động** | Identity linking & source namespace policy |

**SCIM là giao thức quản trị dữ liệu**, không phải một magic switch làm Spring Security “biết tất cả người dùng và vai trò”.

## 4. Bộ RFC nền tảng và phiên bản

**SCIM 2.0** có ba tài liệu cốt lõi:

1. **RFC 7642 — Definitions, Overview, Concepts and Requirements:** bối cảnh quản lý danh tính cross-domain.
2. **RFC 7643 — Core Schema:** định nghĩa User, Group, thuộc tính chung, enterprise extension, schema discovery.
3. **RFC 7644 — Protocol:** URI/HTTP methods, filter, pagination, PATCH/PUT/DELETE, bulk, error format, concurrency và bảo mật.

REST base URI thường được đặt dạng `https://provisioning.example.test/scim/v2`, **nhưng đó là ví dụ**, không phải mọi server bắt buộc có path đúng `/scim/v2`. Các đường dẫn tương đối chuẩn thường là:

~~~text
/Users
/Users/{id}
/Groups
/Groups/{id}
/ServiceProviderConfig
/ResourceTypes
/Schemas
~~~

Client nên lấy capabilities từ discovery thay vì giả định mọi implementation hỗ trợ tất cả operation/optional features. Ví dụ **PATCH, bulk, filtering, sorting, ETag** có capability flags; không tự suy ra “SCIM 2.0 nghĩa là mọi feature đều bật”.

**Media type** chuẩn cho JSON SCIM là `application/scim+json`. SCIM có thể dùng bearer token hoặc HTTP authentication khác; chính RFC không bắt buộc một loại OAuth grant duy nhất.

## 5. Dữ liệu User chuẩn: id, externalId và userName

Trong RFC 7643, ba trường rất dễ nhầm nhau:

| Trường | Ai cấp? | Tính chất | Có nên dùng làm khóa liên kết? |
| --- | --- | --- | --- |
| `id` | **SCIM Service Provider** (đích) | Bắt buộc, unique/stable/non-reassignable trong provider; read-only | Dùng để gọi `/Users/{id}`, lưu mapping đích |
| `externalId` | **Provisioning Client** | Tùy chọn, thuộc namespace provisioning domain; provider không bắt buộc enforce unique | Tốt cho ánh xạ nguồn nếu kèm source/tenant scope |
| `userName` | **SCIM Service Provider xác định semantics**; client thường gửi lúc create | User bắt buộc, unique trong provider's Users, case-insensitive theo core schema | Không nên là khóa lifecycle bất biến, vì có thể đổi |
| `emails` | Nguồn theo contract | Multi-value, có thể cập nhật/tái cấp | Không dùng làm bằng chứng identity-link duy nhất |
| `active` | Client hoặc target theo policy | Trạng thái user theo SCIM core | Dùng để cập nhật login eligibility; chưa tự revoke sessions |

**Không dùng email làm primary key provisioning.** Một nhân viên đổi tên/email, alias bị tái cấp hoặc partner có email trùng vẫn phải giữ đúng identity. Nên dùng **(authoritative_source, externalId)** làm identity link ở provisioning layer và **SCIM id** để thao tác tài nguyên đích. Khi userName thay đổi, tránh tạo thêm account thứ hai.

### Ví dụ SCIM User

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "externalId": "hris-employee-0042",
  "userName": "alice@corp.example.test",
  "active": true,
  "name": {
    "givenName": "Alice",
    "familyName": "Nguyen"
  },
  "emails": [
    {
      "value": "alice@corp.example.test",
      "type": "work",
      "primary": true
    }
  ],
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "0042",
    "department": "Finance",
    "costCenter": "F-120"
  }
}
~~~

Dữ liệu, tên miền và employee ID trên chỉ mang tính minh họa. **Không gửi `id` khi tạo** vì id do provider cấp; Enterprise User extension cần target thật sự hỗ trợ theo `/ResourceTypes`/`/Schemas`.

## 6. Group schema và member reference

Một SCIM Group có `displayName` và có thể có một tập `members` tham chiếu Users/Groups bằng **SCIM resource IDs** của target service.

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:Group"
  ],
  "externalId": "iam-group-finance-readers",
  "displayName": "finance-readers",
  "members": [
    {
      "value": "user-100",
      "type": "User",
      "$ref": "https://provisioning.example.test/scim/v2/Users/user-100"
    }
  ]
}
~~~

**Phân biệt ID của Group và tên hiển thị**. Một group có `displayName=finance-readers` ở tenant North không tự là cùng group ở tenant South. Group membership là dữ kiện cấp phát; application phải quyết định group ID/namespace nào tương ứng role hay entitlement nào.

**Nhóm lồng nhau (nested groups)** là mô hình schema có thể diễn tả, nhưng khả năng xử lý group nesting/cascade ở các sản phẩm khác nhau có thể bị hạn chế. Kiểm `/Schemas` và vendor contract, không tự tuyên bố mọi target tự mở rộng recursive membership hoặc cập nhật mọi quyền tức thì.

## 7. Discovery endpoints và khả năng tương thích

Một SCIM Client mới nên đọc cấu hình từ đúng Service Provider đã được đăng ký:

~~~http
GET /scim/v2/ServiceProviderConfig HTTP/1.1
Host: provisioning.example.test
Accept: application/scim+json
Authorization: Bearer SCIM_CLIENT_TOKEN
~~~

Ví dụ rút gọn về capabilities:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
  ],
  "patch": { "supported": true },
  "bulk": {
    "supported": false,
    "maxOperations": 0,
    "maxPayloadSize": 0
  },
  "filter": {
    "supported": true,
    "maxResults": 100
  },
  "changePassword": { "supported": false },
  "sort": { "supported": false },
  "etag": { "supported": true },
  "authenticationSchemes": [
    {
      "type": "oauthbearertoken",
      "name": "OAuth Bearer Token"
    }
  ]
}
~~~

Các endpoints còn lại:

- `GET /ResourceTypes`: resource types và schema extensions được công bố.
- `GET /Schemas`: trường, kiểu, mutability, required, uniqueness, multi-valued.
- `GET /ServiceProviderConfig`: optional capabilities, auth schemes và limits.

**Lưu ý:** một số discovery endpoints có thể được server công khai theo RFC, nhưng doanh nghiệp có thể yêu cầu authentication. Không hardcode rằng không cần token. Việc discovery public không cho phép ghi dữ liệu khi chưa được authorization.

## 8. Tạo tài khoản: POST /Users

SCIM Client có thể gửi user mới tới target:

~~~http
POST /scim/v2/Users HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json
Accept: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "externalId": "hris-0042",
  "userName": "alice@corp.example.test",
  "active": true,
  "name": {
    "givenName": "Alice",
    "familyName": "Nguyen"
  }
}
~~~

Khi tạo thành công, server trả **HTTP 201 Created**, phát `id` riêng và `Location` URL phù hợp:

~~~http
HTTP/1.1 201 Created
Location: https://provisioning.example.test/scim/v2/Users/u-100
Content-Type: application/scim+json
ETag: W/"v1"

{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "id": "u-100",
  "externalId": "hris-0042",
  "userName": "alice@corp.example.test",
  "active": true,
  "meta": {
    "resourceType": "User",
    "location": "https://provisioning.example.test/scim/v2/Users/u-100",
    "version": "W/\"v1\""
  }
}
~~~

Phản hồi là **mẫu minh họa**; ETag/meta.version xuất hiện khi provider hỗ trợ versioning. Không đưa token thật vào tài liệu/log, và không mặc định server sẽ giữ nguyên toàn bộ giá trị request.

### Khi POST bị timeout

POST không tự là một operation idempotent. Nếu client không nhận response, **không gửi POST lặp vô hạn** vì có thể đã tạo user. Hãy truy vấn theo stored target id, hoặc filter theo scoped externalId/userName nếu provider hỗ trợ; reconcile trước khi tạo lại. Với `409 uniqueness`, giải quyết trùng lặp có kiểm soát, không tạo account mới bằng userName ngẫu nhiên để “né lỗi”.

## 9. GET, ListResponse, filter và pagination

Đọc một user theo target id:

~~~http
GET /scim/v2/Users/u-100 HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Accept: application/scim+json
~~~

Tìm kiếm theo externalId **khi provider hỗ trợ filter**:

~~~text
GET /scim/v2/Users?filter=externalId%20eq%20%22hris-0042%22
~~~

Trong thực tế cần URL-encode filter đầy đủ, giới hạn user-supplied values và không tự ghép thành câu filter không escape, tránh sai cú pháp hoặc dò dữ liệu ngoài tenant scope.

Response danh sách SCIM thường dùng schema URI **ListResponse**:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:ListResponse"
  ],
  "totalResults": 1,
  "startIndex": 1,
  "itemsPerPage": 1,
  "Resources": [
    {
      "schemas": [
        "urn:ietf:params:scim:schemas:core:2.0:User"
      ],
      "id": "u-100",
      "externalId": "hris-0042",
      "userName": "alice@corp.example.test",
      "active": true
    }
  ]
}
~~~

**Phân trang theo chỉ số** trong RFC 7644 dùng `startIndex` **bắt đầu từ 1** và `count` là số kết quả mong muốn. Các tiện ích filter/sort có thể là optional features; kiểm `ServiceProviderConfig`. Với một tập user lớn, dùng pagination và checkpoint/reconciliation đúng thay vì GET toàn bộ rồi giả như server sẽ trả không giới hạn.

**Không coi một kết quả rỗng là bằng chứng user đã bị xóa vĩnh viễn** khi client có filter hoặc entitlement không đủ quyền đọc. Kiểm status, filter support, tenant scope và retry trước khi quyết định tạo lại.

## 10. PATCH: thay đổi một vài thuộc tính mà không ghi đè cả user

RFC 7644 định nghĩa SCIM PATCH nhưng **PATCH là optional capability của server**, được quảng bá ở `ServiceProviderConfig.patch.supported`. Cấu trúc body có schema **PatchOp** và mảng **Operations** gồm `add`, `remove`, `replace`.

Ví dụ thay department:

~~~http
PATCH /scim/v2/Users/u-100 HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department",
      "value": "Accounting"
    }
  ]
}
~~~

Ví dụ đơn giản hơn để vô hiệu hóa account:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

**Phân biệt SCIM PATCH với JSON Patch (RFC 6902)**: SCIM dùng `Operations`, các đường dẫn thuộc tính SCIM và không hỗ trợ index array như JSON Patch. Các operations trong một SCIM PATCH request phải được **xử lý atomic**: nếu một operation thất bại, resource quay về trạng thái ban đầu theo RFC.

Không giả định mọi server trả resource body sau PATCH: có thể trả **200 cùng resource** hoặc **204 No Content** theo trường hợp. Với deprovisioning nhạy cảm, client có thể GET/reconcile để xác nhận trạng thái thực.

## 11. PUT: full replacement và nguy cơ vô tình xóa thuộc tính

`PUT /Users/{id}` dùng để **thay thế các thuộc tính resource** theo mutability rules của SCIM. Khác PATCH, PUT có thể khiến những thuộc tính không được gửi bị xóa/đặt default tùy schema và RFC behavior.

**Rủi ro:** provisioning engine chỉ muốn đổi department nhưng gửi PUT thiếu group-related hoặc enterprise extension fields, gây mất dữ liệu mà target đang quản lý.

Nguyên tắc:

1. Dùng PATCH nếu server hỗ trợ và chỉ muốn cập nhật một số trường.
2. Với PUT, đọc resource hiện tại, hiểu owner từng attribute và gửi representation đầy đủ theo contract.
3. Không ghi đè các thuộc tính read-only như `id`/`meta.created` bằng client value.
4. Không dùng PUT để tạo user mới nếu resource không tồn tại; RFC quy định PUT không được dùng để create SCIM resource.
5. Khi nhiều provisioning clients, dùng version/ETag nếu được hỗ trợ.
6. Tránh việc nguồn HRIS vô tình ghi đè các custom fields của ứng dụng nếu HRIS không là authoritative owner.
7. Kiểm thử trên tài khoản canary và so sánh trước–sau.
8. Không dùng retry PUT vô hạn khi `If-Match` xung đột; phải reconcile.

**Không suy luận “PUT giống updateProfile() của JPA”**. Trong REST/SCIM, đây là resource replacement có ngữ nghĩa schema và concurrency riêng.

## 12. Đồng bộ Group và danh sách members

Khi nhân viên chuyển nhóm, provisioning engine có thể sửa `/Groups/{id}`. Ví dụ thêm người đã tồn tại vào Group (khi PATCH được hỗ trợ):

~~~http
PATCH /scim/v2/Groups/g-finance HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        {
          "value": "u-100",
          "type": "User"
        }
      ]
    }
  ]
}
~~~

Để xóa một user khỏi nhóm, SCIM PATCH hỗ trợ **valuePath filter**, ví dụ về ý tưởng:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"u-100\"]"
    }
  ]
}
~~~

Cần xác minh target hỗ trợ group PATCH, valuePath và đúng server-specific constraints. **Không thử xóa group membership bằng cách gửi array rỗng tới mọi provider** mà chưa xem semantics: có thể vô tình xóa toàn bộ members.

**Quan trọng:** Group membership thay đổi trong SCIM repository **không tự làm Spring SecurityContext của user đang login cập nhật ngay**. Nếu quyền nhạy cảm, cần entitlement lookup/version check/session invalidation tại app.

## 13. Deprovisioning: active=false khác DELETE

Hai hành động thường được nhắc đến khi nhân viên nghỉ việc:

- **Deactivate (logical disable):** cập nhật `active=false` nếu SCIM server hỗ trợ và ứng dụng có contract xử lý. Resource vẫn có thể tồn tại để giữ lịch sử, mapping, audit và retention.
- **DELETE /Users/{id}:** yêu cầu xóa resource theo SCIM protocol và business policy. Kết quả có thể là delete/tombstone/soft delete tùy implementation; không được giả định lúc nào cũng xóa vật lý toàn bộ bản ghi và log.
- **Suspend/lock bởi ứng dụng:** một trạng thái local có thể độc lập với `active`; application phải xử lý các trạng thái chặn truy cập theo chính sách.

~~~text
HRIS: employee left
    |
    v
Provisioning engine
    | -- SCIM PATCH active=false --> target
    | -- update group membership --> target
    v
Target account DB: active=false
    |
    +--> New login: DENY dù IdP session còn active
    |
    +--> Existing web session: phải revoke hoặc kiểm active mỗi request
    |
    +--> API keys/service tokens: policy thu hồi độc lập
    |
    +--> Audit/retention: giữ theo pháp luật và dữ liệu nghiệp vụ
~~~

**Không hứa “SCIM deactivate = đăng xuất ngay mọi thiết bị”.** Nếu Spring chỉ nạp UserDetails một lần khi đăng nhập, local session còn authorities cũ. IdP cũng có thể vẫn phát token tới khi upstream thực hiện revocation. Cần bảo đảm **denial at application** hoặc session/token revocation theo SLA đã thống nhất.

## 14. Vòng đời Joiner–Mover–Leaver chi tiết

| Sự kiện HR/IAM | Tác vụ SCIM | Tác vụ ứng dụng bổ sung |
| --- | --- | --- |
| Joiner: nhân viên được tuyển | Create User, active theo policy, add Groups | Cấp license nếu có; link IdP subject; không mặc định auto-admin |
| Pre-hire: chưa đến ngày nhận việc | Có thể create active=false | Không cho login trước ngày hiệu lực |
| Mover: đổi phòng ban | PATCH enterprise attributes, update group membership | Rút quyền nhóm cũ, cập nhật entitlement cache |
| Mover: chuyển tenant | Chuyển/loại membership theo policy | Kiểm data isolation, owner chuyển tài nguyên nếu được phép |
| Rename: đổi tên/email | PATCH name/email/userName khi thích hợp | Giữ stable SCIM id và external identity link |
| Leave: nghỉ việc | active=false hoặc DELETE theo policy | Revoke sessions, refresh tokens, API keys, delegated grants |
| Rehire: nhân viên quay lại | Quyết định restore hay new identity theo HR/IGA policy | Chống link nhầm tài khoản cũ, lịch sử/entitlement |
| Identity merge/split | Workflow điều chỉnh source links có phê duyệt | Không tự gộp hai người vì trùng email |
| Group removed | Update /Groups membership | Rút quyền, kiểm existing sessions/authorization |
| Tenant closed | Bulk disable/remove memberships theo policy | Ngăn cross-tenant access và giữ legal retention |

**Giai đoạn Mover thường khó hơn Joiner:** việc **rút quyền cũ** phải được kiểm thử, không chỉ cấp thêm quyền mới. Một provisioning job tạo user thành công nhưng không remove quyền của vị trí trước có thể gây privilege accumulation.

## 15. Source of truth: tránh hệ thống nào cũng ghi mọi thứ

Trong tổ chức lớn, nhiều hệ thống đều có dữ liệu “đúng” theo nghĩa riêng:

| Attribute | Nguồn có thể authoritative | Không nên để |
| --- | --- | --- |
| Employee number, hire/leave date | HRIS | Business app tự ghi đè |
| Identity subject/issuer link | IAM/IdP directory | Email form tự sửa và tự link |
| Display name | HRIS hoặc directory | SCIM target sửa tùy tiện rồi bị overwrite |
| Department/manager | HRIS/IGA | Local app ghi ngược nếu không được phê duyệt |
| Account status | HR lifecycle + security suspensions | SCIM active=true tự mở khóa security suspension |
| Application roles | App entitlement owner/IGA policy | Mọi SCIM group string tự thành quyền |
| Tenant membership | Tenant administrator/IGA contract | Header tenant do browser chọn |
| License quota | SaaS target/commerce system | SCIM client đoán không kiểm target constraints |
| Audit/retention | Compliance/legal owner | DELETE xóa lịch sử bất chấp legal hold |

**Sự kiện “active=true” từ HRIS không được bỏ qua khóa account do Security Operations đặt**. Có thể cần trạng thái hợp thành:

~~~text
effective_login_allowed =
    scim_provisioned_active
    AND NOT locally_suspended
    AND security_policy_allows
    AND tenant_access_current
    AND (other application requirements)
~~~

Đừng dùng một boolean `active` làm state machine duy nhất của mọi kiểm soát an ninh.

## 16. Đồng bộ không phải giao dịch xuyên các hệ thống

Một sự kiện HRIS có thể cập nhật 10 ứng dụng qua SCIM. Có thể 9 ứng dụng thành công và 1 ứng dụng lỗi 503/429. **SCIM không cung cấp distributed transaction/atomic rollback xuyên các Service Providers**.

Cần kiến trúc vận hành:

1. **At-least-once delivery:** các event có thể được gửi lại.
2. **Idempotent apply theo source key:** không tạo user trùng khi event lặp.
3. **Ordering hoặc version:** event leave không bị event join cũ ghi đè.
4. **Retry có backoff + jitter:** tôn trọng rate limit/Retry-After khi provider đưa.
5. **Dead-letter queue/quarantine:** sự kiện không sửa tự động được.
6. **Reconciliation:** so sánh authoritative intended state với target actual state định kỳ.
7. **Alerting:** đặc biệt deactivation failure hoặc privilege removal failure.
8. **Audit & provenance:** biết event nào, ai, lúc nào và target đã xác nhận gì.
9. **Rollback có kiểm soát:** không auto-reenable user chỉ vì rollback một deployment.
10. **Manual intervention có phân quyền:** ví dụ conflict identity/tenant cần human approval.

**Hiệu lực cuối cùng (eventual consistency)** phải có **SLA**: thời gian chấp nhận từ HRIS leave đến target deny. Với application nhạy cảm, chỉ polling SCIM mỗi vài giờ có thể không đủ; cần realtime revocation và local authorization guard.

## 17. Idempotency và identity mapping trong provisioning chuyên trách

Một cách nghĩ an toàn:

~~~text
source_system = HRIS_CORP
source_user_id = emp-0042
target_system = BILLING

(source_system, source_user_id, target_system)
    -> target SCIM id = u-100
~~~

Nếu userName đổi, mapping vẫn trỏ `u-100`. Nếu một nguồn khác cũng có externalId `emp-0042`, đó là identity khác:

~~~text
HRIS_CORP  / emp-0042 -> u-100
HRIS_PARTNER / emp-0042 -> u-201
~~~

**Đặc tả SCIM nói `externalId` scoped theo provisioning domain; provider không bắt buộc đảm bảo uniqueness toàn cục.** Vì thế provisioning engine nên giữ source namespace và target identity mapping rõ. Một target app multi-tenant có thể áp thêm constraint ở database theo trust boundary đã thiết kế.

### Xử lý sự kiện lặp

- Trước POST, nếu có target id đã lưu, GET theo id và reconcile.
- Nếu chưa có id, query theo externalId khi filter được hỗ trợ và source namespace rõ.
- Nếu 0 kết quả, tạo; nếu 1 kết quả, update theo policy; nếu nhiều, dừng và điều tra collision.
- Nếu POST trả 409 uniqueness, không tự đổi username thành random; xác minh có phải account của cùng source user không.
- Nếu network timeout sau POST, **không assume create thất bại**.
- Khi PATCH lặp, thiết kế desired state convergent thay vì append group member trùng vô hạn.
- Với event version cũ, không ghi đè trạng thái mới.
- Khi account đã bị security suspended, “event active=true” cũ không reenable.
- Dùng **account version/If-Match** khi target cung cấp ETag.

**Idempotence là tính chất quy trình của provisioning engine**, không phải chức năng tự có của mọi SCIM POST.

## 18. ETag và If-Match để tránh cập nhật mất dữ liệu

Provider SCIM có thể hỗ trợ **ETag**, thể hiện trong HTTP header và `meta.version`. Khi sửa một resource đã đọc, client có thể dùng:

~~~http
PATCH /scim/v2/Users/u-100 HTTP/1.1
Host: provisioning.example.test
Authorization: Bearer SCIM_CLIENT_TOKEN
Content-Type: application/scim+json
If-Match: W/"v7"

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Nếu resource đã thay đổi phiên bản, server có thể trả **412 Precondition Failed**. Client cần GET lại, so sánh desired state và reapply theo policy; không retry với If-Match giả hoặc xóa precondition chỉ để ép ghi đè.

**Không có ETag không có nghĩa server không thể xử lý concurrency**, nhưng provisioning engine phải thiết kế lock/version hoặc reconciliation thay thế. **SCIM PATCH atomic trên một resource** khác với **transaction đồng bộ qua 10 applications**.

## 19. Bảo mật SCIM endpoint

SCIM là **API quản trị quyền lực lớn**: client có thể tạo người dùng, đổi nhóm, khóa hoặc mở tài khoản. Nếu credentials bị lộ, hậu quả có thể rộng hơn một user login thông thường.

Các nguyên tắc:

- **HTTPS/TLS** với xác minh certificate và hostname.
- SCIM client phải được **authentication riêng**, thường là OAuth2 bearer client credentials hoặc mTLS theo provider policy.
- Token phải có **audience dành cho SCIM API**, đúng client identity và scopes/quyền tối thiểu.
- Tách credentials đọc danh sách Users/Groups với credentials tạo/sửa/deactivate nếu có thể.
- Hạn chế tenant/resource được client sửa; không cho một connector của tenant A provision user ở tenant B.
- Không nhận user-supplied target URL, tránh **SSRF hoặc token exfiltration**.
- Không log OAuth token, password, API key, raw PII hoặc JSON user payload không được kiểm soát.
- Kiểm schema, attribute mutability, max payload, số members, rate limit và timeouts.
- Kiểm certificate/key rotation và không dùng long-lived static secret không có owner.
- Không lấy email hoặc displayName làm quyền cấp/admin.
- Audit service identity, operation, target id, tenant, kết quả, correlation id và policy version.

**RFC 7644 không quy định một phương thức authentication duy nhất cho mọi provider**. `ServiceProviderConfig.authenticationSchemes` cho biết những cách được hỗ trợ; Spring Resource Server dùng JWT/opaque token chỉ khi đó là lựa chọn được kiến trúc thống nhất.

## 20. Vì sao cần hệ thống SCIM chuyên trách thay vì đặt vào Spring Security?

**Spring Security quản trị bảo mật của các request**, không phải engine điều phối vòng đời tài khoản. Một provisioning chuyên trách cần nhiều thứ nằm ngoài thư viện này:

| Nhiệm vụ | Spring Security core? | Thành phần thích hợp |
| --- | --- | --- |
| Login OIDC/OAuth2/SAML (khi có module) | Có các integrations tương ứng | Spring Security |
| Xây Authentication/SecurityContext | Có | Spring Security |
| Kiểm hasRole/hasAuthority, method security | Có | Spring Security + business policy |
| Validate bearer JWT/opaque token cho SCIM API | Có qua Resource Server | Spring Security |
| Dựng SCIM Users/Groups resources, schema discovery, PATCH engine | **Không tự cung cấp như SCIM server chuẩn** | SCIM service/vendor/library do đội IAM sở hữu |
| Pull HRIS events, cấp accounts cho hàng chục targets | Không | IGA/provisioning engine |
| Dedupe, cross-system identity mapping | Không | Identity registry/provisioning service |
| Retry, DLQ, reconciliation, conflict resolution | Không | Workflow/event processing |
| Multi-tenant provisioning policy | Không mặc định | IAM + target authorization |
| Thu hồi đồng loạt app sessions/tokens | Không tự động vì SCIM update | Session/revocation service và application |
| License entitlement/offboarding workflow | Không | Business IAM/IGA |
| Data retention, GDPR/legal hold | Không | Data governance + target policy |

**Có thể dùng Spring Boot viết SCIM Service Provider**, và dùng Spring Security bảo vệ API đó; tuy nhiên **tính tương thích RFC 7643/7644 là công việc phải tự triển khai/kiểm thử**, không xuất hiện chỉ do thêm `spring-boot-starter-security`. Không cấu hình một property tưởng tượng như `spring.security.scim.enabled=true` rồi hy vọng có SCIM provisioning tự động.

## 21. Spring Security lấy dữ liệu đã SCIM provision như thế nào?

Một Spring application có thể có bảng account được IAM sync qua SCIM:

~~~text
Identity Provider -- OIDC token ----> Spring Application
                                          |
                                     oauth2Login
                                      hoặc JWT
                                          |
                                  verified issuer + subject
                                          |
                                   local identity link
                                          |
                   SCIM-provisioned local account active/groups
                                          |
                                 Spring Authentication
                                          |
                      GrantedAuthority + tenant/resource policy
~~~

**Đường authentication:** xác minh token/session theo đúng protocol. **Đường provisioning:** cập nhật account repository độc lập. Ứng dụng cần nối chúng bằng một **verified identity link** thay vì tự tin `userName` hoặc email.

Ví dụ:

~~~text
OIDC login identity:
  issuer  = https://idp.example.test/tenant/corp
  subject = user-oidc-7781

SCIM source:
  source_system = HRIS_CORP
  externalId    = emp-0042
  target id     = u-100

Internal linked account:
  local_account_id = acct-100
  active           = true
  tenant           = north
~~~

Chỉ khi IAM/target đã xác minh rằng hai external identities thuộc **cùng một người** thì Spring mới cho `acct-100` đăng nhập. Không auto-link chỉ vì email trùng.

### Trạng thái `active=false` được kiểm ở đâu?

Có thể ở `UserDetailsService`, `OidcUserService`/account linking layer, custom `AuthenticationProvider` hoặc authorization guard; **không nên chỉ dựa vào token còn valid**. Với session JWT stateless và quyền cần thu hồi nhanh, account-state check có thể phải chạy **mỗi request nhạy cảm**, không chỉ lúc login đầu.

## 22. Spring Boot: bảo vệ API SCIM do đội chuyên trách triển khai

Mẫu sau cho một **SCIM Service Provider được viết riêng bằng Spring Boot 3.x/Spring Security 6.x**. Spring Security chỉ **bảo vệ** đường `/scim/v2/**` bằng OAuth2 JWT. Nó **không tự tạo SCIM endpoints, request validation, schema, persistence hoặc synchronization**.

**application.yml** (cần một Authorization Server thật với JWKS/metadata):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://auth.example.test"
          audiences: "scim-provisioning-api"
~~~

**SecurityFilterChain:**

~~~java
package com.example.provisioning.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ScimApiSecurityConfiguration {

    @Bean
    SecurityFilterChain scimApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/scim/v2/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.read")
                        .requestMatchers(HttpMethod.POST, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .requestMatchers(HttpMethod.PUT, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .requestMatchers(HttpMethod.PATCH, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .requestMatchers(HttpMethod.DELETE, "/scim/v2/**")
                        .hasAuthority("SCOPE_scim.write")
                        .anyRequest().denyAll())
                .sessionManagement(s -> s
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(csrf -> csrf.disable())
                .oauth2ResourceServer(oauth ->
                        oauth.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Rất quan trọng khi áp dụng:**

1. Đây là **class trong project Spring**, cần dependencies Spring Web, Spring Security và OAuth2 Resource Server; không phải code JDK standalone.
2. `csrf.disable()` chỉ thích hợp trong security chain **machine-to-machine Bearer-only thực sự không dùng cookies**. Nếu service có browser session, phải thiết kế CSRF riêng; không tắt global CSRF vô điều kiện.
3. `SCOPE_scim.read`/`SCOPE_scim.write` là **ví dụ scopes do AS/application tự định nghĩa**. RFC SCIM không chuẩn hóa những chuỗi đó.
4. Chỉ match `/scim/v2/**`; cần **các SecurityFilterChains khác** bảo vệ ứng dụng business và management endpoints.
5. Kiểm JWT `iss`/`aud`/`exp`/signature; ứng dụng còn cần xác nhận **client ID, tenant scope, operation và resource-level authorization** vì chỉ có generic write scope có thể quá rộng.
6. Discovery endpoints có thể có read policy riêng; mẫu này yêu cầu token cho GET, là một policy hợp lệ khi tổ chức chọn.
7. Controller/service/DAO phải thực hiện đúng SCIM semantics: IDs, errors, PATCH atomic, filters, Groups, ETags, data persistence.
8. Trong môi trường có nhiều OAuth clients, một client chỉ được phép sửa những resources thuộc tenant/scope đã đăng ký; đừng dựa duy nhất vào Bearer scope toàn hệ thống.
9. Spring Boot properties và API cần kiểm bằng **đúng version BOM**; JWT `audiences` là cấu hình đã được Spring Boot hỗ trợ ở nhiều bản hiện đại nhưng cần test build/release.
10. Không dùng API-level security như bằng chứng danh tính người dùng cuối đã được cấp quyền truy cập business app; SCIM client là machine identity.

**Không coi SecurityFilterChain trên là SCIM server hoàn chỉnh.** Nó chỉ xác thực và giới hạn requests tới bộ xử lý SCIM riêng.

## 23. Spring app đăng nhập khi tài khoản chưa được provision

Có thể xuất hiện race:

~~~text
09:00 HRIS tạo người dùng.
09:01 IAM mở SSO/IdP login.
09:02 Người dùng đăng nhập OIDC thành công.
09:03 SCIM POST vào target chưa chạy hoặc đang 503.
09:04 Spring không tìm thấy linked local account.
~~~

**Không nên tự tạo local admin account từ email trong token** chỉ để user khỏi thấy lỗi.

Các chiến lược:

- **Fail closed** và hiển thị thông báo provisioning pending, kèm request correlation ID.
- **Deferred activation:** chỉ cho đăng nhập vào target sau khi target SCIM provisioning xác nhận.
- **Controlled JIT provisioning:** nếu policy cho phép, tạo account tối thiểu qua một luồng riêng đã xác minh, có mapping nguồn và entitlement hạn chế; không tự thay thế SCIM lifecycle/deprovisioning.
- **Wait/retry có giới hạn:** nếu IAM đã xác nhận một event pending, không vòng lặp vô hạn/không cấp quyền trong lúc chưa có data.
- **Monitoring:** cảnh báo user đã được cấp SSO nhưng target chưa hoàn thành provisioning theo SLA.
- **Reconciliation:** khi SCIM tạo account xong, lần đăng nhập mới có thể thành công theo policy.

**JIT và SCIM có thể cùng tồn tại nhưng cần owner rõ**: ai là authoritative source, cách tránh duplicate, account state merge và cách xử lý leave. Không có quy tắc bắt buộc SCIM luôn chạy trước SSO ở mọi hệ thống.

## 24. Java 17 độc lập: mô phỏng idempotent upsert và account disable

Ví dụ này mô phỏng **chính sách phía provisioning repository** và **kiểm quyền phía ứng dụng**, không triển khai SCIM server/protocol thật. Nó dùng **source + externalId** làm khóa để tránh tạo trùng, giữ target ID ổn định khi cập nhật, từ chối quyền khi account inactive và không tự map nhóm `ROLE_ADMIN` thô thành quyền quản trị.

Tạo file **ScimLifecycleDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class ScimLifecycleDemo {

    record Key(String source, String externalId) {}

    record Account(
            String targetId,
            Key key,
            String userName,
            boolean active,
            Set<String> groups,
            int version) {}

    static final class TargetDirectory {
        private final Map<Key, Account> accounts = new HashMap<>();
        private int idSequence;

        Account upsert(
                String source,
                String externalId,
                String userName,
                boolean active,
                Set<String> groups) {

            Key key = new Key(source, externalId);
            Account old = accounts.get(key);
            Set<String> safeGroups = Set.copyOf(groups);

            if (old != null
                    && old.userName().equals(userName)
                    && old.active() == active
                    && old.groups().equals(safeGroups)) {
                return old; // Duplicate event: no new id/version.
            }

            String id = old == null
                    ? "usr-" + (++idSequence)
                    : old.targetId();
            int version = old == null ? 1 : old.version() + 1;
            Account current = new Account(
                    id, key, userName, active, safeGroups, version);
            accounts.put(key, current);
            return current;
        }

        Account find(String source, String externalId) {
            return accounts.get(new Key(source, externalId));
        }

        int size() {
            return accounts.size();
        }

        String authorize(
                String source,
                String externalId,
                String tenant,
                String permission) {

            Account account = find(source, externalId);
            if (account == null) {
                return "DENY_UNKNOWN";
            }
            if (!account.active()) {
                return "DENY_INACTIVE";
            }
            if (!"north".equals(tenant)) {
                return "DENY_TENANT";
            }

            // App policy, không dùng raw ROLE_ADMIN làm quyền.
            String requiredGroup = switch (permission) {
                case "invoice.read" -> "north:invoice-readers";
                case "invoice.approve" -> "north:invoice-approvers";
                default -> null;
            };
            if (requiredGroup == null
                    || !account.groups().contains(requiredGroup)) {
                return "DENY_ENTITLEMENT";
            }
            return "ALLOW " + account.targetId();
        }
    }

    public static void main(String[] args) {
        TargetDirectory target = new TargetDirectory();

        Account created = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                true, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Created: "
                + created.targetId() + " v" + created.version());

        Account duplicate = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                true, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Duplicate event: "
                + duplicate.targetId() + " count=" + target.size()
                + " v" + duplicate.version());

        System.out.println("Read invoice: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.read"));

        System.out.println("Approve invoice: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.approve"));

        System.out.println("Other tenant: " + target.authorize(
                "HRIS_CORP", "emp-42", "south", "invoice.read"));

        Account disabled = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                false, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Deactivated: v" + disabled.version());
        System.out.println("Existing identity: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.read"));

        Account retried = target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                false, Set.of("north:invoice-readers", "ROLE_ADMIN"));

        System.out.println("Retry disable: v" + retried.version());

        System.out.println("Wrong source: " + target.authorize(
                "HRIS_PARTNER", "emp-42", "north", "invoice.read"));

        target.upsert(
                "HRIS_CORP", "emp-42", "alice@corp.example.test",
                true, Set.of("north:invoice-readers"));

        System.out.println("After reactivation: " + target.authorize(
                "HRIS_CORP", "emp-42", "north", "invoice.read"));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac ScimLifecycleDemo.java
java ScimLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
Created: usr-1 v1
Duplicate event: usr-1 count=1 v1
Read invoice: ALLOW usr-1
Approve invoice: DENY_ENTITLEMENT
Other tenant: DENY_TENANT
Deactivated: v2
Existing identity: DENY_INACTIVE
Retry disable: v2
Wrong source: DENY_UNKNOWN
After reactivation: ALLOW usr-1
~~~

### Ý nghĩa từng dòng

- Event tạo user cấp target ID `usr-1` và version 1.
- Event gửi lặp không tạo user thứ hai, không tự tăng version.
- Group `north:invoice-readers` chỉ cấp quyền đọc hóa đơn North theo policy.
- Chuỗi `ROLE_ADMIN` từ nguồn provisioning **không tự trở thành quyền approve**.
- Chuyển sang tenant South bị từ chối.
- `active=false` làm local policy từ chối ngay, dù user vẫn tồn tại trong repository.
- Disable event lặp giữ nguyên version 2.
- `externalId` giống nhau nhưng nguồn khác không tự match.
- Reactivation là một **event đã được policy cho phép trong mô phỏng**, không chứng minh HRIS có quyền bỏ qua security suspension thật.

**Giới hạn:** ví dụ **đơn luồng, HashMap**, không có SCIM HTTP/JSON parser, DB transaction, optimistic locking, sequence/version sự kiện nguồn, distributed delivery, JWT verification, session invalidation hay account permission kiểm chứng theo người dùng. Không dùng trực tiếp để bảo vệ endpoint production. Với domain nhạy cảm, **reactivation phải được security workflow phê duyệt**, không chỉ một boolean từ event cũ.

## 25. Dữ liệu SCIM vào Spring UserDetails và authorities

Ứng dụng Spring có thể có account repository riêng được SCIM cập nhật. Sau khi authentication bằng OIDC/SAML/password, cần kiểm account:

~~~java
// Fragment thuộc một UserDetailsService trong ứng dụng,
// localAccounts là dependency từ DB/repository của dự án.
@Override
public UserDetails loadUserByUsername(String linkedLocalAccountId) {
    LocalAccount account = localAccounts.find(linkedLocalAccountId);

    if (account == null) {
        throw new UsernameNotFoundException("Account is not provisioned");
    }

    if (!account.isProvisionedActive()
            || account.isLocallySuspended()) {
        throw new DisabledException("Account is not allowed to login");
    }

    return User.withUsername(account.getLocalId())
            .password("{noop}UNUSED_IN_FEDERATED_LOGIN")
            .disabled(false)
            .authorities(mapApprovedPermissions(account))
            .build();
}
~~~

**Đây là một fragment Spring**, không phải class runnable; `LocalAccount`, `localAccounts` và `mapApprovedPermissions` phải do ứng dụng định nghĩa. Password marker **không được sử dụng cho password-based authentication**; nếu app còn hỗ trợ form login, cần tách credential handling và PasswordEncoder đúng.

**Quan trọng:** `loadUserByUsername` có thể được gọi khi login, không nhất thiết mỗi HTTP request. Nếu session hoặc JWT vẫn tồn tại sau khi SCIM gửi `active=false`, code trên **chưa đủ** để thu hồi quyền ngay. Cần account status/entitlement check ở các request nhạy cảm hoặc invalidation sessions/tokens.

### Phân quyền theo SCIM Groups

**Không nên:**

~~~java
// Không dùng cho raw SCIM Group displayName:
new SimpleGrantedAuthority(group.getDisplayName());
~~~

**Nên:** ánh xạ group ID/source/tenant được phê duyệt sang application permissions:

~~~text
(source=HRIS_CORP, targetGroup=g-101, tenant=north)
    -> ROLE_INVOICE_VIEWER

(source=HRIS_CORP, targetGroup=g-102, tenant=north)
    -> ROLE_INVOICE_APPROVER

group displayName = "ROLE_ADMIN" (chưa được phê duyệt)
    -> Không cấp quyền
~~~

Mọi domain action vẫn cần ownership/tenant checks. Group membership từ SCIM có thể là **snapshot** của entitlement, không phải lời khẳng định quyền hiện tại trong session cũ.

## 26. Quyền trong JWT/claims và SCIM không đồng nhất

Một user có thể:

- Được IdP xác thực và có ID Token/Access Token còn hạn.
- Được SCIM provision ở Billing nhưng đang `active=false`.
- Đã bị xóa khỏi SCIM Group `finance-approvers` trong khi JWT cũ còn `scope=invoice.approve` hoặc Spring session còn authorities cũ.

**Authentication thành công không giải quyết account lifecycle.** Cần quyết định **policy precedence**:

~~~text
ALLOW request
 IF JWT/session đã được xác minh đúng issuer/audience/time
 AND local SCIM-provisioned account vẫn active
 AND NOT locallySuspended
 AND current tenant membership hợp lệ
 AND action permission còn hiệu lực
 AND resource ownership/ABAC rules pass
ELSE DENY
~~~

Với pure JWT stateless app, có thể cần **short token TTL**, introspection, token revocation/denylist hoặc server-side account-state/version check. Với browser app, có thể cần Spring Session registry invalidate sessions theo SCIM disable event. **SCIM không tự gọi Spring LogoutHandler cho mọi thiết bị**.

**Không copy SCIM `active=true` vào JWT rồi tin mãi tới khi token hết hạn** nếu yêu cầu thu hồi nhanh hơn lifetime của token.

## 27. SCIM Client credentials, scopes và quyền vận hành

Một SCIM connector thường chạy dưới **machine identity**. Nếu dùng OAuth2, có thể cấp bằng `client_credentials`, nhưng phải phân biệt hai luồng:

~~~text
SCIM provisioning:
  IAM client -> AS (machine token) -> SCIM Provider API
  Token audience: scim-provisioning-api
  Token scopes: scim.read/scim.write (ví dụ tự định nghĩa)

User login:
  Browser -> OIDC OP -> Spring application
  ID Token subject = user identity
  Access token for business API != SCIM machine token
~~~

**Không đưa SCIM client write token vào trình duyệt**, vì nó có thể tạo/disable users. Không để business API chấp nhận provisioning token như user token chỉ vì cùng issuer hoặc JWT signature hợp lệ. **Audience và token type** phải tách biệt.

Trong ứng dụng SCIM, kiểm quyền theo operation:

- Client HRIS_CORP được tạo/update Users của nguồn HRIS_CORP, không phải mọi users.
- Client GroupManager chỉ được sửa groups thuộc phạm vi được cấp.
- Client audit read-only không có PATCH/DELETE.
- Client partner không thể provision user sang tenant north trái contract.
- Token issuer, exp, aud, client_id và scopes phải được xác minh, còn resource-level policy vẫn áp dụng.
- Kể cả client có write scope, **DELETE/activate admin accounts** có thể cần policy đặc biệt.

**SCIM không buộc phải dùng OAuth2**. Nếu target sử dụng mTLS hoặc một authentication scheme khác được discovery công bố, cần implementation tương ứng, không ép mọi vendor theo một grant duy nhất.

## 28. Data minimization, privacy và retention

SCIM có thể chứa thông tin cá nhân: tên, địa chỉ email, số điện thoại, department, manager, employee number, ảnh và custom extension attributes.

**Chỉ đồng bộ thuộc tính target thật sự cần**:

1. Xác định mục đích và data owner của từng attribute.
2. Với app chỉ cần display name và ID, không tự gửi salary, ngày sinh hoặc toàn bộ HR record.
3. Dùng HTTPS, at-rest encryption và giới hạn quyền đọc SCIM repository.
4. Tránh log request/response SCIM body ở gateway/APM; token và PII phải được redact.
5. Không đưa email/employee number làm metric label cardinality cao.
6. Đặt retention khi người dùng nghỉ việc, xử lý legal hold/anonymization theo chính sách.
7. Xác định `DELETE` nghĩa là gì trong target system; không hứa xóa mọi log/backups.
8. Với multi-tenant SaaS, bảo đảm ID filter/queries không lộ dữ liệu tenant khác.
9. Kiểm các schema extensions trước khi đồng bộ custom PII.
10. Có audit trail cho ai đã sửa attribute nào, không lưu raw secret trong audit.
11. Quyền self-service user update không được ghi đè authoritative source nếu không có quy trình merge.
12. Thử data removal và access revocation trên một user canary.

**Privacy và security là hai câu hỏi khác nhau:** SCIM token được bảo vệ không đồng nghĩa target có quyền lưu tất cả HR fields vô thời hạn.

## 29. Khả năng tương thích giữa các nhà cung cấp

Dù cùng quảng bá “hỗ trợ SCIM 2.0”, các sản phẩm có thể khác nhau về:

| Khía cạnh | Cần kiểm nghiệm |
| --- | --- |
| Base URL | `/scim/v2` hay path vendor-specific |
| Resource types | Users, Groups, extensions nào? |
| Create | Tên trường bắt buộc và uniqueness của userName |
| Update | PATCH được hỗ trợ hay chỉ PUT? |
| Group membership | PATCH add/remove, nested groups, size limits |
| Filtering | Hỗ trợ `eq`, `externalId`, attribute nào? |
| Pagination | Page size, startIndex, count, limits |
| ETag | Có response version và `If-Match` không? |
| Bulk | Có bật hay không, limits và partial failures |
| Deactivate | `active=false` có khóa login thật không? |
| Delete | Hard delete, soft delete hoặc tombstone? |
| Schema extension | Enterprise User và custom attributes |
| Authentication | OAuth bearer, mTLS hoặc vendor-specific scheme |
| Error model | 409 uniqueness, 412 precondition, 401/403 và scimType |
| Rate limit | 429/Retry-After và vendor limits |
| Tenant scoping | Per-tenant token/base URL, cross-tenant ID isolation |
| Event order | Updates cũ có thể overwrite state mới? |
| Account linking | externalId scoped source; email không unique |
| Consistency | Thời gian từ PATCH success tới application permission change |
| Session revocation | Deactivate đã invalidate user sessions/tokens chưa? |

**Phải chạy conformance/integration tests với provider thật** và đọc `ServiceProviderConfig`. Một MockMvc test chỉ kiểm controller trả 201 không chứng minh id stable, PATCH atomic hoặc deactivate có chặn login.

## 30. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| POST tạo user bị 409 | userName trùng hoặc uniqueness violation | Reconcile identity, không auto-random userName |
| POST timeout rồi retry tạo 2 accounts | Thiếu idempotent identity mapping | Query target id/externalId trước retry |
| User rename làm xuất hiện user mới | Dùng email/userName làm khóa chính | Dùng source externalId + SCIM id ổn định |
| PATCH trả 501 | Server không hỗ trợ PATCH | Kiểm discovery, dùng PUT đúng contract nếu cần |
| PATCH body lỗi | Dùng JSON Patch `ops` thay SCIM `Operations` | Dùng PatchOp schema và paths chuẩn |
| PUT làm mất groups/custom attrs | Gửi representation thiếu fields | Dùng PATCH hoặc full read-modify-write theo schema |
| If-Match trả 412 | Resource đã đổi version | GET, reconcile và update an toàn |
| GET filter trả 0 dù user tồn tại | Filter unsupported/tenant scope sai | Kiểm ServiceProviderConfig, access rights |
| Group update thành công nhưng app vẫn 403 | Roles chưa được map/refresh | Kiểm entitlement mapping/session/cache |
| active=false nhưng user vẫn vào API | JWT/session cũ và thiếu account-state check | Revoke/epoch/online checks |
| SCIM user active=true nhưng SSO login fail | Identity link chưa xác minh hoặc IdP policy chặn | Đối chiếu subject/issuer, đừng auto-link email |
| User rời tenant vẫn thấy dữ liệu | Business authorization thiếu tenant checks | Kiểm object ownership tại app |
| User nghỉ việc bị tự bật lại | Event cũ ghi đè disable mới | Enforce source event ordering/version |
| Một group tên admins thành ROLE_ADMIN | Raw group mapping | Dùng allowlist và approval |
| Rate limit 429 làm queue backlog | Không backoff/Retry-After | Retry có jitter, monitor SLA |
| Thay đổi group hàng loạt vượt giới hạn | Bulk không hỗ trợ hoặc payload quá lớn | Chunk có kiểm soát, per-operation status |
| SCIM bearer token bị đưa vào frontend | Thiết kế credential sai | Machine-only secret store, rotate credentials |
| SCIM PATCH bị chặn 403 | Scope/client/tenant policy không cho phép | Cấp quyền tối thiểu theo target |
| SCIM client gửi target URL lạ | SSRF/token exfiltration risk | Fixed allowlist endpoints |
| App disable nhưng rehire khôi phục nhầm người | Identity link không có chứng cứ | Quy trình rehire/merge có phê duyệt |
| Spring login auto tạo role khi SCIM chậm | JIT fallback quá rộng | Fail closed/provisioning pending |

**Không sửa sự cố bằng cách** tắt TLS, bỏ authorization check, tự tạo admin, bypass account disabled hoặc mở rộng SCIM write scope toàn hệ thống.

## 31. Ma trận kiểm thử end-to-end

| # | Tình huống | Kỳ vọng |
| --- | --- | --- |
| 01 | POST User hợp lệ, chưa có | 201, trả provider id ổn định |
| 02 | Event create lặp | Không sinh duplicate user |
| 03 | POST duplicate userName | 409 uniqueness theo RFC/contract |
| 04 | externalId giống nhau từ hai provisioning domains | Không tự merge account |
| 05 | userName/email đổi | Giữ target id và identity link |
| 06 | active=false PATCH đúng | Target deactivated theo policy |
| 07 | Người bị disabled thử login OIDC | Backend từ chối dù token hợp lệ |
| 08 | Người đã login trước disable | Session/token bị revoke hoặc online check chặn theo SLA |
| 09 | Active=true event cũ tới sau disable | Không tự re-enable |
| 10 | User có locallySuspended=true, SCIM active=true | Vẫn từ chối theo local security policy |
| 11 | PATCH chưa được server hỗ trợ | Client không gửi hoặc fallback đúng |
| 12 | PATCH nhiều ops, một op lỗi | Resource giữ trạng thái cũ (atomic) |
| 13 | PUT thiếu custom fields | Phát hiện nguy cơ data loss |
| 14 | GET /Users/{id} | Đúng resource với id/mapping hiện hành |
| 15 | ListResponse có startIndex=1 | Pagination không bỏ/nhân đôi users |
| 16 | Filter externalId unsupported | Client phát hiện, không tự tạo duplicate |
| 17 | ETag/If-Match version stale | 412, reconcile trước retry |
| 18 | Group add member hợp lệ | Target membership update |
| 19 | Group remove member | Quyền được rút theo SLA |
| 20 | Nested Group không được provider hỗ trợ | Không giả group expansion |
| 21 | Client read-only gọi PATCH | 403 |
| 22 | Client tenant A gọi User tenant B | 403/deny tenant |
| 23 | SCIM token đúng chữ ký sai audience | 401 |
| 24 | SCIM bearer token hết hạn | 401 |
| 25 | Client secret/mTLS certificate rotate | Hoạt động theo runbook |
| 26 | Client gửi unknown schema attribute | Validation/rejection đúng contract |
| 27 | Client gửi id read-only lúc create | Server không chấp nhận/không tin client ID |
| 28 | Email trùng, subject khác | Không account takeover |
| 29 | Login OIDC trước SCIM provisioning | Fail closed hoặc controlled JIT |
| 30 | User thiếu local identity link | Không tự merge theo email |
| 31 | Group displayName=ROLE_ADMIN | Không tự cấp admin |
| 32 | Wrong tenant resource request | Domain deny dù user/group tồn tại |
| 33 | SCIM service outage | Retry/DLQ/reconciliation, có alert |
| 34 | 429 rate limit | Respect backoff/Retry-After |
| 35 | Event mover tới out of order | Desired state/version kiểm soát |
| 36 | Delete User theo legal hold | Không phá retention policy ngoài ý muốn |
| 37 | Partial multi-target provisioning | Track target failures riêng; không tuyên bố global success |
| 38 | Bulk unsupported | Client dùng per-resource operations |
| 39 | SCIM write logs chứa raw PII/token | Redaction và retention controls hoạt động |
| 40 | Disable 1 account ở 10 targets | Báo rõ 10 kết quả và remediation target lỗi |
| 41 | Rehire với cùng email khác identity | Chờ linking proof/approval |
| 42 | Role đổi trong Spring session | Staleness guard/session revocation |
| 43 | Signed JWT có user inactive | Account-state policy deny |
| 44 | Concurrent PATCH trên một user | ETag/version không mất cập nhật |
| 45 | Tenant-level provisioner bị thu hồi token | Không sửa được target resources nữa |

**Một hệ thống chỉ PASS khi kiểm cả provisioning state và hành vi đăng nhập/quyền thực tế**. Kết quả 200/204 từ SCIM API **chưa đủ** để chứng minh user đã bị chặn ở mọi existing session.

## 32. Runbook triển khai từ đầu đến production

### Pha A — Phân tích và phân chia trách nhiệm

1. Xác định authoritative sources, provisioning engine, target SCIM servers và ứng dụng Spring.
2. Mô tả Users/Groups, enterprise extensions và attribute ownership.
3. Chọn immutable external identity key và mapping per source/tenant/target.
4. Xác định lifecycle joiner–mover–leaver và deactivation semantics.
5. Thiết kế group→role/entitlement mapping với app owner.
6. Chốt yêu cầu latency từ event leave đến **đăng nhập bị chặn** và **existing sessions bị thu hồi**.
7. Xác định quy trình account-linking, JIT policy và xử lý rehire.

### Pha B — Chuẩn bị kết nối SCIM

1. Đăng ký endpoint, mTLS hoặc OAuth2 machine client, scopes/resource ownership.
2. Kiểm `/ServiceProviderConfig`, `/ResourceTypes` và `/Schemas` của target.
3. Test POST, GET, supported PATCH/PUT, Groups, DELETE/deactivate với canary users.
4. Kiểm filter/pagination/ETag/bulk capabilities trước khi bật connector.
5. Thiết lập secret rotation, monitoring, TLS trust và network ACL.
6. Giới hạn write client theo tenant và operation.
7. Ghi audit correlation, không log raw payload/credentials.

### Pha C — Đồng bộ và reconciliation

1. Gửi một batch canary, xác minh target IDs được lưu trong mapping table.
2. Test event lặp, POST timeout, 409 uniqueness và 412 version conflict.
3. Xác minh event versioning/tombstone để không resurrect departed accounts.
4. Dùng retry có exponential backoff+jitter với bounded queue.
5. Thêm dead-letter triage có owner, không tự retry vĩnh viễn.
6. Chạy reconciliation giữa desired state và actual target state.
7. Với 10 targets, ghi kết quả riêng từng target, không nói “sync thành công” khi chỉ 9 thành công.

### Pha D — Tích hợp Spring Security

1. Login qua IdP được xác minh đúng issuer/subject/audience.
2. Link external subject đến SCIM-provisioned local account có chứng cứ.
3. Kiểm account active và locallySuspended, không tự bật khi SCIM active=true trái security policy.
4. Map groups qua approved app policies, tenant/resource authorization.
5. Tích hợp session/token revocation khi SCIM deactivation.
6. Giữ route `/scim/v2/**` machine-only; không cho browser có quyền provisioning token.
7. Test signed token còn hạn nhưng account bị deactivate.
8. Không dùng JIT như cơ chế bỏ qua approval/SCIM lifecycle.

### Pha E — Rollout và vận hành

1. Canary một tenant, một app, một target group trước khi bật tất cả.
2. Theo dõi SLA provisioning latency, partial failures, 401/403 login anomalies.
3. Kiểm group-removal và deactivation behavior trên web session và API token.
4. Thử provider outage, retry, reconciliation, duplicate detection.
5. Kiểm retention, data minimization và legal hold.
6. Thiết lập alert cho deactivation failure/P0 security exposure.
7. Có runbook rollback không re-enable user trái policy.
8. Duyệt thay đổi schema/mapping khi vendor nâng phiên bản SCIM.

## 33. Observability và kiểm toán

Các metrics sau là đề xuất do provisioning engine/SCIM provider triển khai, **không phải metrics Spring Security tự động cung cấp**:

| Metric | Cách hiểu |
| --- | --- |
| `scim_provision_requests_total` | Requests theo target/operation/status |
| `scim_provision_success_total` | Operation target xác nhận thành công |
| `scim_provision_failures_total` | Lỗi 4xx/5xx/timeout theo reason |
| `scim_provision_latency_seconds` | Độ trễ API call/response |
| `identity_lifecycle_end_to_end_delay` | Từ HR event đến target state có hiệu lực |
| `scim_deactivation_backlog` | Users chờ bị vô hiệu ở các targets |
| `scim_reconcile_drift_total` | Sai lệch desired vs actual state |
| `scim_duplicate_identity_conflicts` | Collision externalId/userName/tenant |
| `scim_group_membership_changes` | Add/remove members; tránh raw PII labels |
| `scim_412_version_conflicts` | Concurrency conflicts phải xử lý |
| `scim_429_rate_limits` | Rate limits, cần backoff |
| `scim_dlq_depth` | Event không xử lý được |
| `app_inactive_account_access_denied` | Từ chối truy cập sau deprovision |
| `app_stale_session_revocation_delay` | Độ trễ thu hồi local session/token |

**Không dùng raw email, subject, externalId, token, group membership chứa PII làm metric labels**. Dùng hash/correlation id nội bộ có kiểm soát khi cần audit, phân quyền truy cập logs và đặt retention.

**Cảnh báo ưu tiên cao:** `active=false` ở IAM nhưng request nhạy cảm vẫn được Spring chấp nhận; group đã bị rút nhưng user còn quyền approve; provisioning client write token bị lộ; tenant connector sửa tài khoản ngoài phạm vi; retry queue làm lỡ thời hạn offboarding.

## 34. Câu hỏi tự đánh giá

**1. SCIM có thay Spring Security xác thực người dùng không?**  
Không. SCIM quản trị tài khoản/nhóm; Spring Security kiểm authentication và authorization theo cấu hình, dùng dữ liệu đã được đồng bộ.

**2. Có thêm spring-boot-starter-security là lập tức có SCIM /Users và /Groups không?**  
Không. Phải có SCIM service/provider implementation chuyên trách hoặc thư viện/vendor hỗ trợ và triển khai RFC semantics.

**3. externalId và id khác nhau thế nào?**  
SCIM `id` do provider cấp và ổn định; `externalId` do client cấp, scoped theo provisioning domain.

**4. Có nên dùng email để biết user đã được provision chưa?**  
Không làm identity key duy nhất. Dùng source/externalId/target id và verified issuer+subject mapping.

**5. Nếu SCIM group tên ROLE_ADMIN thì Spring phải cấp admin chứ?**  
Không. Ứng dụng phải map allowlist theo nguồn, tenant, role owner và account status.

**6. PATCH có bắt buộc ở mọi SCIM 2.0 server không?**  
Không. RFC 7644 định nghĩa PATCH như optional server capability; kiểm `ServiceProviderConfig`.

**7. SCIM PATCH có phải RFC 6902 JSON Patch nguyên xi không?**  
Không. Nó sử dụng `schemas` PatchOp và `Operations` với SCIM attribute paths/semantics.

**8. PUT có thể tự tạo user mới không?**  
Theo RFC 7644, PUT không được dùng để create resource mới; dùng POST.

**9. Khi POST timeout, có nên gửi POST lặp ngay không?**  
Không mù quáng. Phải reconcile xem account đã được tạo chưa để tránh duplicate.

**10. active=false có tự hủy Spring SecurityContext cũ không?**  
Không. Cần session/token revocation hoặc account-state check ở request.

**11. SCIM user active nhưng đăng nhập OIDC thất bại có mâu thuẫn không?**  
Không. Provisioning và authentication là hai planes riêng; IdP policy/account mapping vẫn có thể từ chối.

**12. Vì sao cần reconciliation?**  
Vì nhiều targets cập nhật không đồng thời, có retries, errors, out-of-order events và drift.

**13. Cần làm gì khi group membership bị rút?**  
Update SCIM Groups, rút entitlement trong target, kiểm existing sessions/authorization freshness.

**14. SCIM API có thể dùng OAuth2 client_credentials không?**  
Có nếu provider/AS hỗ trợ; nhưng RFC không bắt buộc duy nhất OAuth2. SCIM client token là machine credential, không phải user login token.

**15. Khi nào xây SCIM service bằng Spring Boot?**  
Khi đội cần một Service Provider/API chuyên trách và sẵn sàng tự triển khai RFC 7643/7644, persistence, entitlement, error handling, tenant isolation và conformance tests. Spring Security chỉ bảo vệ API.

## 35. Checklist production

- [ ] Phân biệt rõ **SCIM provisioning**, **SSO authentication** và **application authorization**.
- [ ] Có hệ thống IAM/IGA/provisioning chịu trách nhiệm joiner–mover–leaver, retry, DLQ và reconciliation.
- [ ] Target SCIM Service Provider hỗ trợ Users/Groups và các schema được discovery xác minh.
- [ ] Không giả định PATCH/filter/sort/bulk/ETag luôn có; kiểm ServiceProviderConfig.
- [ ] Có mapping **(source, externalId, target)** → SCIM `id` ổn định; không dùng email làm khóa duy nhất.
- [ ] POST duplicate/timeout xử lý idempotence và identity conflict an toàn.
- [ ] PUT replacement và PATCH atomic semantics được kiểm thử.
- [ ] PATCH Groups add/remove được đối chiếu với quyền thực của ứng dụng.
- [ ] SCIM machine client có TLS, auth riêng, audience/scopes/tenant boundaries và rotation.
- [ ] Backend SCIM API chặn cross-tenant edits, schema spoof, payload overlimit và unauthorized DELETE.
- [ ] Không log raw SCIM tokens, account PII hoặc entitlement data ngoài mục đích.
- [ ] Deactivation `active=false` được backend thực thi, không chỉ lưu ở bảng users.
- [ ] Locally suspended/locked state không bị SCIM active=true tự động xóa.
- [ ] Có revocation plan cho Spring sessions, JWT/refresh tokens, API keys và delegated credentials.
- [ ] Group/role mapping là approved allowlist, không auto grant admin từ displayName.
- [ ] Account linking từ OIDC issuer+subject sang SCIM ID có chứng cứ, không dựa email.
- [ ] Race login trước provisioning được xử lý fail closed/controlled JIT.
- [ ] Concurrent updates và out-of-order lifecycle events không resurrect departed account.
- [ ] Có target-specific rollout, audit logs, reconciliation SLA và incident handling.
- [ ] Có conformance tests với provider thật, không chỉ unit test dữ liệu JSON.
- [ ] Spring Security chỉ được giao đúng nhiệm vụ authentication/authorization/API protection.
- [ ] Data minimization, legal retention và privacy của SCIM attributes đã được phê duyệt.

## 36. Kết luận

**SCIM 2.0** là nền tảng giao tiếp chuẩn cho **cấp phát và đồng bộ tài khoản/nhóm**, thường được triển khai ở **hệ thống IAM/IGA/provisioning hoặc Service Provider chuyên trách**. Ba khái niệm cần phân biệt là: **danh tính được tạo/disable qua SCIM**, **người dùng được xác thực qua OIDC/SAML/cơ chế khác**, và **quyền truy cập do ứng dụng quyết định dựa trên local account/tenant/resource policy**.

**Spring Security có thể bảo vệ một SCIM API do ứng dụng xây và có thể đọc dữ liệu account đã provision để từ chối hoặc cho phép login, nhưng không tự là một SCIM synchronization engine.** Với production, phải có stable identity mapping, schema/capability discovery, Idempotency, group reconciliation, bảo mật machine client, xử lý fail closed và thu hồi local sessions/tokens. **Cấp phát thành công chưa đủ; thay đổi quyền và vô hiệu hóa phải thật sự có hiệu lực tại application runtime.**

### Tài liệu tham khảo chính thức

- IETF RFC 7642 — SCIM Definitions, Overview, Concepts, Requirements: https://www.rfc-editor.org/rfc/rfc7642
- IETF RFC 7643 — SCIM Core Schema (Users, Groups, Enterprise User, id/externalId): https://www.rfc-editor.org/rfc/rfc7643
- IETF RFC 7644 — SCIM Protocol (CRUD, PATCH, filter, pagination, ETag, error/security): https://www.rfc-editor.org/rfc/rfc7644
- Spring Security — Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — UserDetailsService: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
