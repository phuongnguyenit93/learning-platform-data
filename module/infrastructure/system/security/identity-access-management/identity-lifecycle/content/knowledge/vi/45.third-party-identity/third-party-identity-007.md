# Partner access scope: xác định phạm vi truy cập của đối tác trong IAM

## 1. Partner access scope là gì?

Trong **Identity and Access Management (IAM)**, **partner access scope** là tập hợp các **giới hạn truy cập được tổ chức sở hữu tài nguyên phê duyệt cho một đối tác và các chủ thể đại diện cho đối tác đó**. Phạm vi không chỉ nói rằng “đối tác B được phép vào ứng dụng A”, mà phải trả lời cụ thể:

- **Ai** đang đại diện B: nhân viên, guest account, nhóm người dùng, API client hay workload?
- **Theo quan hệ nào**: hợp đồng, dịch vụ, dự án hoặc thỏa thuận chia sẻ dữ liệu nào giữa A và B?
- **Ở đâu**: tenant, tổ chức con, dự án, môi trường staging/production, ứng dụng, kho dữ liệu hay nhóm tài nguyên nào?
- **Làm gì**: đọc, tạo mới, cập nhật, phê duyệt, xóa, xuất dữ liệu hoặc quản trị?
- **Trong thời gian nào**: quyền bắt đầu khi nào, kết thúc lúc nào, có cần gia hạn và rà soát?
- **Với điều kiện nào**: xác thực mạnh, ticket được duyệt, thiết bị đáng tin, mục đích sử dụng và chính sách dữ liệu?

**Ví dụ:** Công ty A cung cấp nền tảng quản lý đơn hàng cho nhiều nhà phân phối. Công ty B được hợp tác trong dự án P42 thuộc tenant-B, ba nhân viên B cần xem báo cáo, còn một tích hợp của B cần cập nhật trạng thái đơn. Scope đúng nghĩa là **người có quyền xem chỉ đọc báo cáo P42; client chỉ cập nhật trạng thái các đơn B được giao; mọi truy cập tenant-C hoặc quản trị hệ thống phải bị từ chối**.

Partner access scope là một phần của **vòng đời danh tính Joiner–Mover–Leaver**:

1. **Joiner:** xác minh quan hệ với B, định nghĩa scope tối thiểu, cấp danh tính và quyền phù hợp.
2. **Mover:** khi công việc, hợp đồng hoặc vai trò thay đổi, tính lại scope; thu hồi giới hạn cũ không còn hợp lệ.
3. **Leaver:** khi người dùng rời dự án hoặc đối tác kết thúc quan hệ, thu hồi đúng tập quyền và kiểm chứng không còn quyền tồn dư.

Trong module SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE, scope là điểm nối giữa **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và quản trị quyền truy cập tồn dư**.

### Phân biệt xác thực với giới hạn truy cập

Một nhân viên B đăng nhập thành công bằng SSO qua IdP của B chỉ cho A một cơ sở để **xác minh danh tính**. Việc user đó có role viewer cũng chưa đủ để biết họ được xem **báo cáo của tenant nào**. Bên sở hữu tài nguyên A cần quyết định và thực thi quyền theo đối tượng cụ thể.

| Khái niệm | Trả lời câu hỏi | Điều chưa đảm bảo |
|---|---|---|
| Authentication | Ai đã chứng minh danh tính bằng nguồn nào? | Không tự đảm bảo quyền trên tài nguyên |
| Federation trust | A chấp nhận bằng chứng từ IdP nào? | Không tự xác nhận mọi user của IdP được vào A |
| Partner membership | Principal có thuộc quan hệ/đối tác được phê duyệt không? | Không tự cấp tất cả role trong tenant |
| RBAC role | Nhóm hành động nào có thể được cấp? | Không luôn chỉ rõ đối tượng, tenant, thời hạn |
| ABAC policy | Ngữ cảnh và thuộc tính nào phải thỏa? | Phải có nguồn thuộc tính tin cậy và thực thi ở backend |
| Partner access scope | Chủ thể được làm gì trên phạm vi nào và đến khi nào? | Không thay thế xác thực hoặc quản trị phiên |

**Quy tắc quan trọng:** không suy rằng quyền truy cập tài nguyên đã được phép chỉ từ domain email, một token được ký hợp lệ, vai trò chung “partner” hoặc một đường dẫn không bị ẩn.

## 2. Các chiều của phạm vi truy cập

Scope trong môi trường B2B thường là **giao của nhiều ràng buộc** chứ không phải một flag “partner active”.

| Chiều scope | Câu hỏi thực tế | Giá trị minh họa |
|---|---|---|
| Organization / partner | Quyền thuộc đối tác nào? | partner-B |
| Relationship / contract | Hợp đồng nào tạo cơ sở cho quyền? | CTR-2026-042 |
| Principal | Người hoặc hệ thống nào? | user-U, api-client-B1 |
| Tenant / account | Không gian dữ liệu nào? | tenant-B |
| Project / service | Hạng mục công việc nào? | project-P42 |
| Resource | Đối tượng được phép truy cập là gì? | report-845, order-332 |
| Action | Hành vi cụ thể nào? | report.read, order.status.update |
| Environment | Staging, sandbox hay production? | staging |
| Data classification / field | Dữ liệu nào được phép dùng hoặc xuất? | Chỉ báo cáo đã loại thông tin nhạy cảm |
| Purpose / workflow | Có đúng mục đích hợp tác? | Order fulfillment |
| Time | Có còn trong thời hạn được duyệt? | 30 ngày |
| Context / assurance | Có cần MFA, phiên đặc quyền, ticket? | MFA + ticket khi hỗ trợ production |

### 2.1. Scope cấp tổ chức và hợp đồng

Trước khi cấp quyền cho một người, IAM cần xác định **đối tác B là tổ chức được xác minh** và hợp đồng/quan hệ nào còn hiệu lực. Một đối tác có thể có hai hợp đồng, chẳng hạn hỗ trợ logistics P42 và triển khai phần mềm P51. Khi hợp đồng P42 kết thúc, không nhất thiết khóa hoàn toàn B nếu P51 vẫn hợp lệ; nhưng **không quyền nào phát sinh từ P42 được tồn tại chỉ vì B còn active ở P51**.

Trạng thái đối tác, trạng thái từng relationship và trạng thái từng grant nên được phân biệt. Việc chỉ kiểm tra partner.status = active bỏ qua khả năng hợp đồng cụ thể đã hết hạn.

### 2.2. Scope theo tenant và dự án

Trong ứng dụng **multi-tenant**, tenant thường là ranh giới dữ liệu quan trọng. Một principal có thể được cấp quyền trong tenant-B nhưng không được xem tenant-C, dù role cùng tên. Nếu partner có nhiều tenant hợp pháp, IAM phải biểu diễn membership của từng tenant và không gộp vô điều kiện mọi grants.

Phạm vi dự án có thể hẹp hơn tenant: B có quyền trong tenant-B nhưng chỉ được đọc P42, không có quyền P51. Trạng thái và phạm vi của dự án vẫn cần được kiểm tra tại API.

### 2.3. Scope theo tài nguyên và hành động

Role partner_viewer không nên ngầm cho phép xem mọi đối tượng. Ví dụ, user U chỉ được:

- đọc báo cáo dự án P42;
- không đọc báo cáo của P51;
- không tải xuống dữ liệu thuộc nhóm hạn chế nếu policy cấm;
- không cập nhật hoặc xóa báo cáo;
- không chỉnh danh sách thành viên hoặc thay đổi scope của chính mình.

Tài nguyên có thể là một hàng dữ liệu, đơn hàng, thư mục, repository, API endpoint hoặc dịch vụ. Cần định nghĩa **quy tắc sở hữu tài nguyên**: tài nguyên đó thuộc tenant/dự án nào, ai có quyền quyết định và dữ liệu bên trong thuộc mức nhạy cảm nào.

### 2.4. Scope theo môi trường và thời hạn

Quyền vận hành staging không được mặc nhiên mở rộng sang production. Với quyền hỗ trợ nhạy cảm, có thể dùng **Privileged Access Management (PAM)** để cấp đặc quyền **Just-in-Time (JIT)** theo ticket, môi trường và thời hạn cụ thể.

Cần phân biệt:

- **Contract expiry:** ngày kết thúc quan hệ hợp tác;
- **Membership expiry:** khi principal không còn tham gia tenant/dự án;
- **Grant expiry:** khi quyền trên một tài nguyên/hành động hết hiệu lực;
- **Session lifetime:** thời gian hiệu lực phiên ứng dụng;
- **Token expiry:** thời gian hiệu lực token đã phát hành;
- **Review due date:** ngày phải xác nhận lại nhu cầu, không tự đồng nghĩa với expiry.

Ví dụ: Hợp đồng còn ba tháng nhưng grant production chỉ có hiệu lực hai giờ. Kéo dài hợp đồng không tự gia hạn grant hai giờ; đồng thời kết thúc hợp đồng phải khiến mọi grant phụ thuộc bị đánh giá lại, bất kể chưa đến hạn grant.

## 3. Kiến trúc thực thi partner access scope

~~~mermaid
flowchart LR
    subgraph B["Tổ chức đối tác B"]
      HU["Người dùng B"]
      IDP["IdP B"]
      CLIENT["Workload B / API client"]
      HU --> IDP
    end
    subgraph A["Nền tảng của A"]
      RP["Cổng B2B / RP / SP"]
      API["API gateway / resource server"]
      REG["Partner, contract, membership registry"]
      POL["Authorization policy: RBAC + ABAC"]
      RES["Tài nguyên theo tenant / project"]
      AUD["Audit / review / reconciliation"]
      RP --> POL
      API --> POL
      POL --> REG
      POL --> RES
      RP --> AUD
      API --> AUD
      REG --> AUD
    end
    IDP -->|"OIDC / SAML khi có trust"| RP
    CLIENT -->|"OAuth access token / mTLS nếu dùng"| API
    OWNER["Sponsor + resource owner A"] -->|"Duyệt scope và hạn"| REG
    SYNC["Provisioning service"] -->|"SCIM nếu hỗ trợ"| REG
~~~

Các quyết định cần được đặt ở đúng lớp:

1. **IdP và federation:** xác thực danh tính con người theo nguồn tin cậy; OIDC ID token/SAML assertion không tự cấp quyền trên dữ liệu A.
2. **Partner/relationship registry:** liên kết chủ thể với partner và hợp đồng đã được xác minh.
3. **Membership và grant store:** giữ các quyền được phê duyệt, hạn, owner, resource và action cụ thể.
4. **Policy decision:** RBAC/ABAC kết hợp principal, relationship, resource ownership, hành động và ngữ cảnh để tạo allow/deny.
5. **Policy enforcement:** API/backend/resource server thực sự chặn hành động không hợp lệ.
6. **Lifecycle và audit:** cập nhật quyền theo sự kiện Joiner–Mover–Leaver, so sánh quyền dự kiến và quyền còn thực tế ở hệ thống đích.

### 3.1. Principal, partner và resource là ba khóa khác nhau

Không đồng nhất **partner_id** với **issuer IdP**: một đối tác có thể đổi IdP hoặc dùng nhiều issuer, còn nhiều đối tác có thể dùng chung nhà cung cấp IdP. Dùng partner_id nội bộ ổn định, sau đó ánh xạ nguồn danh tính đã kiểm chứng tới partner/membership.

Với OIDC, external human principal thường được liên kết qua **cặp (iss, sub)** sau khi kiểm tra token đúng giao thức. Với workload, dùng client hoặc workload identity đã xác minh, không tin client_id do caller tự ghi trong payload.

### 3.2. Ghi nhận ownership của resource

Một báo cáo có thể chứa:

~~~json
{
  "resource_id": "report-845",
  "tenant_id": "tenant-B",
  "project_id": "P42",
  "classification": "internal-partner",
  "resource_owner_id": "owner-A-9"
}
~~~

Backend phải lấy những thuộc tính này từ dữ liệu đã được hệ thống quản lý, không dựa riêng vào tenant_id hoặc project_id do request không đáng tin gửi lên. Đó là nền tảng để từ chối quyền truy cập chéo tenant và đối tượng.

## 4. Mô hình cấp quyền gắn với quan hệ hợp tác

### 4.1. Các thực thể đề xuất

| Thực thể | Ý nghĩa |
|---|---|
| Partner organization | Đối tác được xác minh, định danh partner_id ổn định |
| Partner relationship | Hợp đồng, project, phạm vi dữ liệu, owner và thời hạn |
| Federated principal | Người hoặc workload, định danh nguồn và local ID |
| Membership | Principal gắn partner/tenant/project, trạng thái và hạn |
| Entitlement / grant | Các action/resource được phép kèm điều kiện |
| Sponsor / resource owner | Ai chứng thực nhu cầu, ai phê duyệt quyền trên tài nguyên |
| Audit/review record | Nguồn sự kiện, phê duyệt, đổi quyền, thu hồi, kết quả |

Đôi khi một **role assignment** đã chứa scope; đôi khi scope được biểu diễn bằng grant riêng. Điều quan trọng là **truy vết được quan hệ grant -> principal -> partner -> hợp đồng -> resource owner**, có thể thu hồi chọn lọc khi một quan hệ kết thúc.

### 4.2. Ví dụ bản ghi quyền

Mẫu YAML dưới đây là mô hình giải thích, không phải schema chuẩn của SCIM/OAuth:

~~~yaml
grant:
  grant_id: "grant-P42-U"
  principal_id: "external-user-U"
  principal_kind: "human"
  partner_id: "partner-B"
  relationship_id: "CTR-2026-042"
  tenant_id: "tenant-B"
  project_ids:
    - "P42"
  resource_types:
    - "order-report"
  allowed_actions:
    - "reports.read"
  environments:
    - "staging"
  sponsor_id: "sponsor-A-17"
  approved_by: "owner-A-9"
  status: "active"
  valid_until: "2026-12-31T00:00:00Z"
  review_due: "2026-12-01T00:00:00Z"
~~~

Định danh principal và partner phải được kiểm tra tại bước provisioning và khi quyết định quyền. Một caller không được tự chọn một partner_id khác để mượn grants của đối tác đó.

### 4.3. Ma trận quyền: cùng đối tác, khác mục đích

| Principal | Partner | Tenant / project | Action | Môi trường | Thời hạn |
|---|---|---|---|---|---|
| Nhân viên U | B | tenant-B / P42 | reports.read | staging | 30 ngày |
| Kỹ sư V | B | tenant-B / P42 | support.ticket.read | staging | 14 ngày |
| Client W | B | tenant-B / P42 | orders.status.update | production API được duyệt | Theo hợp đồng, có review |
| Nhân viên X | C | tenant-C / P51 | reports.read | production | 30 ngày |

U không thể dùng role viewer để truy cập báo cáo của C; V không thể ghi đơn hàng; W không được dùng token máy để truy cập console admin hoặc tài nguyên của C. Các hành động bị từ chối phải được ghi nhận phù hợp.

## 5. Quan hệ giữa OAuth scope, RBAC/ABAC và partner scope

Các hệ thống thường dùng chung từ **scope**, nhưng ý nghĩa có thể khác nhau.

### 5.1. OAuth scope không phải toàn bộ quyền nghiệp vụ

Trong OAuth 2.0, scope là cách mô tả phạm vi được yêu cầu/cấp cho **access token** theo quy tắc của authorization server và resource server. Ví dụ token mang scope orders.read có thể cho phép một lớp thao tác đọc đơn hàng.

Tuy nhiên, chỉ thấy orders.read không cho biết:

- đơn hàng thuộc partner hoặc tenant nào;
- caller có hợp đồng còn hiệu lực hay không;
- principal có được cấp quyền trên chính order đang yêu cầu không;
- dữ liệu/order có bị hạn chế theo classification hoặc dự án không;
- quyền có bị đình chỉ trước khi token hết hạn không.

Vì vậy **resource server phải kết hợp token validation, OAuth scope phù hợp và quyết định authorization theo partner/tenant/object**. Không dùng một chuỗi scope như quyền toàn cục trên mọi tenant.

### 5.2. RBAC cho nhóm hành động, ABAC cho ngữ cảnh

RBAC có thể định nghĩa:

| Role | Các action cơ bản |
|---|---|
| partner_report_viewer | reports.read |
| partner_order_operator | orders.read, orders.status.update |
| partner_project_editor | documents.read, documents.update |
| partner_delegated_admin | members.read, members.manage trong phạm vi ủy quyền |

ABAC giới hạn thêm role theo partner.status, relationship.status, resource.tenant_id, project_id, resource classification, valid_until, điều kiện xác thực và môi trường.

**Ví dụ:** partner_order_operator có thể cập nhật trạng thái đơn P42, nhưng không được đổi giá, thông tin thanh toán, chủ sở hữu hoặc trạng thái đơn của P51 nếu các hành động/tài nguyên đó không được cấp.

### 5.3. Delegated administration có trần quyền

Một đối tác có thể cần quản lý người dùng của mình: mời nhân viên B mới, gỡ người B đã nghỉ việc hoặc gán một số role thấp. A có thể cho phép **delegated admin**, nhưng:

1. chỉ thao tác trên membership/tenant thuộc B;
2. chỉ gán role nằm trong danh sách A đã cho phép;
3. không tự cấp quyền admin toàn cục hoặc quyền vượt trần;
4. không thay đổi sponsor/resource owner phía A nếu chưa được phép;
5. mọi thao tác có audit và chịu các điều kiện review/expiry.

Quyền quản lý thành viên **không** tự bao gồm quyền xem toàn bộ dữ liệu nghiệp vụ của thành viên đó.

## 6. Thiết kế quyết định quyền tại backend

**Điểm kiểm soát cuối cùng của partner access scope là nơi tài nguyên được sử dụng**, thường là API/resource server, database access layer hoặc ứng dụng đích. Một giao diện ẩn menu của tenant-C không có nghĩa người B không thể gửi HTTP request trực tiếp tới endpoint tenant-C.

### 6.1. Đầu vào cần đánh giá

| Nhóm | Thuộc tính cần lấy từ đâu? | Ví dụ |
|---|---|---|
| Chủ thể | Token/phiên đã xác thực và ánh xạ nội bộ | principal_id, kind, partner membership |
| Quan hệ | Partner/contract registry tin cậy | partner.status, relationship.expires_at |
| Quyền | Grant store hoặc policy engine được quản trị | role, action, project, resource |
| Tài nguyên | Backend/database trả về ownership thật | tenant_id, project_id, classification |
| Ngữ cảnh | Nguồn đáng tin theo policy | thời điểm, assurance, JIT approval |
| Yêu cầu | Hành động caller đang cố thực hiện | reports.read hoặc orders.update |

**Không coi project_id, tenant_id hay role nằm trong request body là sự thật được phép**, vì client có thể sửa các trường đó. Resource server phải kiểm tra với resource metadata và grants hiện hành.

### 6.2. Mã giả kiểm tra scope

~~~text
authorize(subject, action, resourceId, context):
    if not context.authentication_valid: DENY
    if subject.status != "active": DENY

    resource = load_resource_from_trusted_store(resourceId)
    if resource is missing: DENY

    membership = load_effective_membership(
        subject.principal_id, resource.tenant_id
    )
    if membership is missing or membership.status != "active": DENY

    partner = load_partner(membership.partner_id)
    if partner.status != "active": DENY

    relationship = load_relationship(
        membership.partner_id, resource.project_id
    )
    if relationship is missing: DENY
    if relationship.status != "active": DENY
    if now >= relationship.expires_at: DENY

    grant = load_grant(subject.principal_id, resource, action)
    if grant is missing or grant.status != "active": DENY
    if now >= grant.expires_at: DENY
    if action not in grant.actions: DENY
    if resource.tenant_id != grant.tenant_id: DENY
    if resource.project_id not in grant.project_ids: DENY
    if resource.environment not in grant.environments: DENY
    if not satisfies_data_and_risk_policy(subject, resource, context): DENY

    ALLOW
~~~

Đây là mô hình minh họa, không phải cấu hình cho một framework cụ thể. Trong sản phẩm thực tế, có thể sử dụng RBAC, ABAC, policy engine tập trung hoặc phối hợp. Quyết định phải phản ánh **quan hệ, quyền và tài nguyên hiện tại**; nếu thiếu chứng cứ cần thiết, mặc định từ chối theo chính sách an toàn.

### 6.3. Xác thực trước khi phân quyền

Với con người dùng OIDC, ứng dụng nhận cần xác minh chữ ký, issuer, audience, thời hạn và các điều kiện giao thức, rồi liên kết cặp (issuer, subject) với local principal. Với SAML, cần xác minh assertion, issuer, audience, recipient, thời gian và ràng buộc theo luồng đăng nhập.

Với API dùng OAuth access token, resource server kiểm tra issuer/authorization server đáng tin, chữ ký hoặc introspection tùy loại token, audience/resource, thời hạn và scope thích hợp. Những bước này **không thay thế** kiểm tra resource ownership.

### 6.4. Những quyết định mẫu

| Yêu cầu | Điều kiện | Kết quả |
|---|---|---|
 U đọc report P42 của tenant-B | Identity hợp lệ, membership B active, grant reports.read P42 còn hiệu lực | ALLOW |
 U đọc report P51 của tenant-C | U chỉ có membership B | DENY |
 U cập nhật report P42 | U chỉ có reports.read | DENY |
 U đọc report P42 sau khi grant hết hạn | Session vẫn còn nhưng grant không còn active | DENY |
 Client W gọi orders.status.update của B | Token đúng audience/scope, client thuộc B, đúng order | ALLOW |
 Client W gọi API quản trị tài khoản A | Token không có permission/entitlement phù hợp | DENY |
 Delegated admin B cấp global-admin | Vượt role ceiling của B | DENY |

### 6.5. Cẩn trọng cache, thời hạn và trạng thái không nhất quán

Nếu policy được cache quá lâu, một grant đã bị thu hồi vẫn có thể được cho phép cho đến khi cache hết hạn. Cần xác định yêu cầu nhất quán theo độ nhạy tài nguyên và thiết kế TTL, invalidation hoặc kiểm tra trạng thái phù hợp. Đặc biệt không tuyên bố “thu hồi tức thì” nếu token tự chứa hoặc ứng dụng downstream chưa hỗ trợ cơ chế đó.

Đối với truy cập nhạy cảm, cân nhắc kiểm tra lại quyền trước thao tác ghi và tránh sử dụng kết quả authorization cũ khi ownership của tài nguyên vừa thay đổi. Mọi cơ chế tối ưu phải được kiểm thử với các ca **revoke, Mover và thay đổi tenant**.

## 7. Joiner: tạo partner access scope ban đầu

Joiner cấp đối tác và cấp principal có thể không diễn ra cùng lúc. Một tổ chức B được A xác minh không có nghĩa mọi nhân viên B được phép truy cập. Ngược lại, tạo được một guest record cũng không tự tạo ra role.

### 7.1. Giai đoạn xác minh quan hệ

Trước khi cấp scope:

1. Xác minh pháp nhân/tổ chức B, người đại diện và sponsor phía A.
2. Xác định hợp đồng, dịch vụ, tenant và dự án được phép chia sẻ.
3. Phân loại dữ liệu, hành động và môi trường cần truy cập.
4. Chỉ định resource owner có thẩm quyền phê duyệt entitlement.
5. Định nghĩa hạn, điều kiện access review, sự kiện thu hồi.
6. Xác định kênh nhận thông báo khi người của B nghỉ việc hoặc thay đổi vai trò.

**Business trust, identity trust và authorization cần được xử lý độc lập.** Hợp đồng hợp lệ là cơ sở nghiệp vụ; IdP tin cậy xác thực con người; resource owner/IAM quyết định quyền.

### 7.2. Giai đoạn tạo danh tính và cấp quyền

~~~mermaid
sequenceDiagram
    participant S as Sponsor A
    participant O as Resource owner A
    participant IAM as IAM + partner registry
    participant IDP as IdP B
    participant API as Ứng dụng / API A
    actor U as Người dùng B
    S->>IAM: Yêu cầu U vào P42, reports.read, 30 ngày
    IAM->>O: Kiểm tra tenant, dữ liệu, scope, lý do
    O-->>IAM: Duyệt quyền P42 có giới hạn
    IAM-->>U: Lời mời hoặc hướng dẫn đăng nhập
    U->>IDP: Xác thực theo phương thức đã tin cậy
    IDP-->>IAM: Kết quả xác thực qua luồng federation
    IAM->>IAM: Liên kết principal với partner/membership
    IAM->>API: Provision grant nếu tích hợp
    API-->>IAM: Xác nhận áp dụng
    U->>API: Request báo cáo P42
    API->>IAM: Kiểm tra trạng thái và entitlement
    IAM-->>API: Quyết định allow hoặc deny
~~~

Sơ đồ là luồng logic; tùy kiến trúc, ứng dụng RP/SP có thể trực tiếp nhận và xác minh ID token/assertion rồi gọi IAM. Không phải mọi IdP/ứng dụng có cùng vai trò hoặc giao thức provisioning.

### 7.3. Scope ban đầu nên theo nguyên tắc tối thiểu

Một yêu cầu tốt có các trường: principal, partner_id, relationship_id, sponsor, resource owner, action, tenant, project, resource, environment, expiry, review_due và lý do.

**Ví dụ đúng:** Nhân viên U của B chỉ xem báo cáo P42 thuộc tenant-B trong 30 ngày.

**Ví dụ thiếu an toàn:** Nhân viên U của B được thêm vào nhóm external-all-access mà không có hạn và không kiểm tra tenant.

Với quyền nhạy cảm như quản trị production, nên có workflow phê duyệt riêng, ràng buộc ticket và đặc quyền tạm thời qua PAM/JIT khi phù hợp.

### 7.4. Kiểm thử sau provisioning

- User thuộc B có thể truy cập đúng tài nguyên P42.
- User B khác chưa được cấp grant không tự có quyền, dù SSO thành công.
- Người B không truy cập được tài nguyên thuộc C.
- Client W chỉ có đúng action và endpoint được duyệt.
- Chuyển trạng thái grant/contract thành suspended khiến request mới bị từ chối theo thiết kế.
- Log ghi nhận principal, tenant, resource, action, policy decision và correlation ID.

## 8. Mover: cập nhật scope khi công việc thay đổi

Mover là giai đoạn dễ dẫn đến **privilege accumulation**: quyền cũ còn lại trong khi quyền mới liên tục được thêm.

| Sự kiện | Scope cần đánh giá lại | Hành động |
|---|---|---|
 U chuyển từ P42 sang P51 | Project, resource và grant hiện tại | Thu hồi P42 không cần, duyệt P51 |
 B nhận thêm hợp đồng mới | Quan hệ nào cấp quyền, có trùng tenant không? | Tạo relationship/grant riêng; không tự mở rộng mọi role cũ |
 B ngừng một dịch vụ | Những grants nào phụ thuộc dịch vụ đã dừng? | Thu hồi đúng phần, giữ các quan hệ còn hiệu lực |
 U từ viewer thành editor | Quyền ghi/xóa cần phê duyệt mới? | Review SoD, least privilege và expiry |
 B thay IdP | Issuer/subject mới có ánh xạ an toàn? | Migration có xác minh, không nối theo email |
 Sponsor hoặc resource owner đổi | Ai có trách nhiệm và thẩm quyền tiếp tục? | Chuyển giao, recertification |
 Thêm môi trường production | Mức rủi ro khác staging? | Approval riêng, có thể JIT/PAM |
 Workload đổi API hoặc endpoint | Scope/audience/token có cần đổi? | Đăng ký và thử quyền mới, revoke quyền cũ |

### 8.1. Thu hồi trước khi tích lũy quyền

Giả sử U từng đọc P42 và được chuyển sang P51. Nếu chỉ thêm role cho P51, user vẫn có thể đọc P42 nếu các grant cũ không bị gỡ. Cần:

1. Liệt kê các grants hiệu lực ở P42, gồm group, role và chia sẻ trực tiếp.
2. Sponsor xác nhận U không còn nhu cầu ở P42.
3. Resource owner P51 duyệt phạm vi quyền mới.
4. IAM xóa quyền cũ và cập nhật quyền mới đúng hạn.
5. Kiểm tra backend: P42 trả DENY, P51 trả ALLOW trong đúng phạm vi.
6. Lưu bằng chứng quyền trước/sau và kết quả ứng dụng đích.

Không phải lúc nào cũng phải thu hồi toàn bộ principal khi người đó chuyển dự án: **Leaver ở cấp grant/relationship** có thể xảy ra đồng thời với **Joiner ở cấp dự án mới**.

### 8.2. Thay đổi tổ chức hoặc IdP

Nếu B sáp nhập với C hoặc chuyển issuer, cần xác minh lại quan hệ và định danh. Không chuyển mọi entitlement của B sang C chỉ bằng sửa partner_id hoặc email domain. Cần migration đã được phê duyệt, mapping subject đáng tin và rà soát tác động tenant/resource.

### 8.3. Chống sai lệch khi event đến muộn

Một sự kiện SCIM/HR đến muộn có thể mâu thuẫn với quyết định Mover vừa áp dụng. Workflow nên dùng trạng thái hiện hành, version hoặc sự kiện có thứ tự, kiểm tra trước khi ghi và xử lý idempotent. Không để job cũ tái cấp grant đã được thu hồi theo hợp đồng mới.

## 9. Leaver: thu hồi scope đúng phạm vi

Mục tiêu Leaver không chỉ là xóa một account, mà là **đưa quyền thực tế của principal/partner trở về trạng thái phù hợp với quan hệ đã kết thúc**.

### 9.1. Các lớp Leaver

| Tình huống | Phạm vi thu hồi | Không nên tác động |
|---|---|---|
 U ngừng P42 nhưng tiếp tục P51 | Membership/grant P42 và session quyền đặc biệt liên quan | Grant hợp lệ ở P51 |
 U rời công ty B | Mọi membership U không còn hợp lệ theo B | Các user B khác |
 API client W ngừng tích hợp P42 | Scope, client, key, certificate và API grants của W | Các client B còn dùng |
 Hợp đồng CTR-042 kết thúc | Mọi grants phụ thuộc CTR-042 | Các hợp đồng khác còn hiệu lực |
 Toàn bộ B offboarded | User, workload, federation/provisioning và shares liên quan B | Partner C cùng nền tảng |

### 9.2. Quy trình thu hồi theo quan hệ

1. **Xác nhận nguyên nhân:** hết hạn, nghỉ việc, Mover, đình chỉ, thu hẹp hợp đồng hay rủi ro an ninh.
2. **Truy ngược phạm vi:** lấy các principal, memberships, grants, sessions và workload liên quan đến relationship/tenant/project cần kết thúc.
3. **Chặn cấp mới:** vô hiệu hóa relationship/grant hoặc principal theo phạm vi; ngăn workflow cũ, JIT hoặc SCIM tự tạo lại quyền.
4. **Thu hồi quyền:** gỡ group, role, project membership, ACL, document share, SaaS grants và quyền API.
5. **Xử lý phiên/token:** invalidate session/refresh token nơi được hỗ trợ; kiểm tra hiệu lực access token và cơ chế revalidation của API.
6. **Thu hồi workload:** disable client, key, certificate, webhook và service account khi phụ thuộc relationship bị kết thúc.
7. **Đối soát thực tế:** so sánh actual access ở app đích với expected access sau thu hồi; sửa sai lệch và xác minh lại.
8. **Lưu audit và xử lý dữ liệu:** giữ bằng chứng theo chính sách; thu hồi truy cập không đồng nghĩa phải xóa ngay mọi dữ liệu hợp đồng.

### 9.3. Token còn hạn không chứng minh grant còn hợp lệ

Giả sử token của U có thời hạn một giờ nhưng U bị thu hồi grant sau 10 phút. Nếu API chỉ tin chữ ký và claim role trong token, quyền có thể tồn tại đến lúc token hết hạn. Một thiết kế yêu cầu thu hồi nhanh phải có cơ chế phù hợp: session invalidation, reference token/introspection, policy re-check, token TTL ngắn hoặc giải pháp khác được resource server hỗ trợ.

Không khẳng định SCIM deactivate hay xóa user ở IdP B sẽ tự động hủy tất cả token của mọi ứng dụng A. Việc thu hồi phải được xác minh trên lớp thực thi tương ứng.

### 9.4. Sơ đồ chuyển trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Sponsor yêu cầu quyền
    Requested --> Approved: Resource owner duyệt scope
    Requested --> Rejected: Không đủ điều kiện
    Approved --> Active: Provision + verify
    Active --> Active: Review/Mover còn hợp lệ
    Active --> Suspended: Rủi ro hoặc cần xác minh
    Suspended --> Active: Được tái duyệt
    Active --> Revoking: Hết hạn hoặc Leaver
    Suspended --> Revoking: Kết thúc quan hệ
    Revoking --> Revoked: Downstream verified
    Rejected --> [*]
    Revoked --> [*]
~~~

Một hệ thống có thể tách trạng thái grant, principal, relationship và token thay vì dùng một state machine. Điểm quan trọng là scope bị thu hồi phải trở nên **không còn được phép** tại backend, không chỉ chuyển màu trạng thái trong bảng quản trị.

## 10. Federation và SCIM hỗ trợ scope ra sao?

### 10.1. SSO xác thực nguồn danh tính

Với **B2B federation**, user B có thể dùng IdP B để đăng nhập ứng dụng A qua OIDC hoặc SAML. A cần xác minh đúng issuer/entityID, chữ ký, audience và điều kiện giao thức. Kết quả xác thực được dùng để liên kết external subject với local principal/partner membership.

Nhưng một IdP có thể xác thực tất cả nhân viên B. Không vì thế A tự cấp quyền cho tất cả nhân viên trên toàn tenant. **Resource owner A quyết định entitlement**, thường dựa trên invitation, sponsor, group mapping đã được phê duyệt hoặc request có hạn.

### 10.2. Group claims là đầu vào, không phải trần quyền

Ví dụ IdP B gửi nhóm B-Order-Operators. A có thể thiết lập mapping:

| Claim nhóm từ B | Quyền phía A được duyệt | Scope bổ sung |
|---|---|---|
| B-Report-Readers | partner_report_viewer | Chỉ dự án được gán trong tenant-B |
| B-Order-Operators | partner_order_operator | Chỉ các đơn của B trong hợp đồng |
| B-Delegated-Admins | partner_delegated_admin | Quản lý membership B trong trần quyền |
| B-Global-Admins | Không tự cấp global-admin | Yêu cầu workflow đặc quyền riêng nếu có |

Một nhóm bất kỳ từ B không được tự quyết định quyền trên dữ liệu A. A cần kiểm soát mapping và theo dõi thay đổi khi đối tác thêm/xóa group.

### 10.3. SCIM là provisioning, không phải authorization toàn cục

**SCIM** có thể đồng bộ user/group và trạng thái active giữa hệ thống nguồn với nơi nhận khi đã tích hợp. Ví dụ B thông báo U đã không còn làm việc:

~~~http
PATCH /scim/v2/Users/external-user-U HTTP/1.1
Authorization: Bearer <provisioning-access-token>
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {"op": "Replace", "path": "active", "value": false}
  ]
}
~~~

Ví dụ minh họa cú pháp, không phải mọi hệ thống đều hỗ trợ. SCIM client cần được xác thực, giới hạn quyền đối với đúng partner và kiểm tra kết quả đồng bộ. Sự kiện này có thể kích hoạt thu hồi membership, session và grants tại A theo workflow, nhưng **SCIM một mình không đảm bảo mọi session, OAuth token và quyền ứng dụng đích biến mất**.

### 10.4. JIT provisioning có kiểm soát scope

**Just-in-Time (JIT) provisioning** tạo local principal khi user đăng nhập lần đầu. Không được đồng nhất việc tạo user thành công với tự cấp quyền dữ liệu. Khi thiếu invitation/sponsor/relationship/grant hợp lệ, user có thể được tạo dưới trạng thái pending hoặc no-access tùy chính sách.

Nếu principal đã bị revoked, luồng JIT không được âm thầm tạo bản ghi mới có role rộng từ cùng email. Phải kiểm tra trạng thái account linking, source identity và điều kiện được mời lại.

## 11. Scope cho workload và service account của đối tác

Đối tác không chỉ có người dùng. Workload chạy không tương tác, như đồng bộ đơn hàng hoặc gửi webhook, cần danh tính riêng gắn hợp đồng và phạm vi API.

### 11.1. Tách user scope và machine scope

| Yếu tố | Human external user | Partner workload / service account |
|---|---|---|
| Identity | Local guest/federated principal | OAuth client, workload subject, certificate identity |
| Xác thực | OIDC/SAML/guest login, MFA tùy rủi ro | Client authentication, mTLS hoặc federation máy |
| Cấp quyền | Role, membership, project, data | API scope, resource entitlement, tenant, action |
| Owner | Sponsor A và đầu mối B | Technical owner và business sponsor |
| Vòng đời | Người đổi việc/rời dự án, hợp đồng hết hạn | Tích hợp đổi hoặc ngừng, credential rotation, contract end |
| Thu hồi | Group, grants, session, token | Disable client, key/certificate, API grants, webhook |

**Không sử dụng mật khẩu của một guest cá nhân để chạy job tự động lâu dài.** Việc này làm khó truy vết người thực hiện, phụ thuộc sai vào HR lifecycle và gây rủi ro sau khi người sở hữu tài khoản nghỉ việc.

### 11.2. OAuth client credentials với giới hạn đối tác

~~~mermaid
sequenceDiagram
    participant C as Workload B
    participant AS as Authorization server
    participant API as Resource server A
    participant IAM as Partner policy A
    C->>AS: Client authentication + client_credentials
    AS-->>C: Access token (audience, scope, expiry)
    C->>API: Request cập nhật order của B
    API->>API: Validate token / client identity
    API->>IAM: Kiểm tra partner B, contract, action, order owner
    IAM-->>API: ALLOW hoặc DENY
    API-->>C: Response
~~~

Với client credentials, access token chứng minh quyền đã được authorization server cấp cho client trong phạm vi phù hợp; resource server vẫn phải kiểm tra quyền nghiệp vụ và object ownership. Đăng ký **client riêng theo đối tác, mục đích và môi trường**, không sử dụng một credential chung cho nhiều vendor/partner.

### 11.3. Scope máy cần bảo vệ và thu hồi như thế nào?

- Dùng access token có audience, scope và TTL phù hợp; chỉ cấp những action máy thật sự cần.
- Dùng client authentication bảo mật như private_key_jwt, mTLS hoặc client secret được bảo vệ trong secret manager tùy môi trường; ưu tiên cơ chế tránh secret lâu dài nếu có thể.
- Liên kết client với partner_id, relationship_id, owner, tenant và hợp đồng.
- Phân tách credential production với sandbox/staging, xoay khóa theo chính sách.
- Ghi audit theo client/principal để phân biệt nhiều tích hợp của cùng đối tác.
- Khi ngừng một tích hợp, thu hồi riêng client/credential đó; khi hợp đồng kết thúc, tìm mọi workload còn phụ thuộc.

Một chứng thư mTLS hợp lệ chỉ hỗ trợ xác thực khóa/tin cậy kỹ thuật theo cấu hình. Nó không thay cho policy quyết định client được đọc hoặc ghi đơn hàng của tenant nào.

## 12. Quản trị scope: access review, audit và reconciliation

### 12.1. Access review phải xét từng relationship và grant

Nếu chỉ hỏi “đối tác B còn hoạt động không?”, người rà soát có thể bỏ qua những quyền đang vượt nhu cầu. Cần xem từng principal, role, resource scope và hợp đồng:

- **Đối tác và quan hệ:** hợp đồng có còn hiệu lực, đúng pháp nhân và đúng dịch vụ?
- **Con người:** nhân viên B có còn tham gia dự án, được IdP và sponsor xác nhận không?
- **Workload:** client còn gọi API cho mục đích được duyệt, có technical owner không?
- **Role/action:** quyền đang cấp có rộng hơn nhiệm vụ, có action ghi/xóa không cần thiết không?
- **Tenant/project:** scope có tràn sang dự án hoặc khách hàng ngoài hợp đồng không?
- **Môi trường:** quyền production có tồn tại sau phiên hỗ trợ hoặc vượt phạm vi không?
- **Thời hạn:** grant nào quá hạn hoặc liên tục được gia hạn mà không có căn cứ?
- **Downstream access:** ACL, data share và ứng dụng SaaS có giữ quyền ngoài registry không?

Sponsor xác nhận **business need**; resource owner xác nhận quyền trên tài nguyên; IAM/app owner cập nhật và đối soát quyền thực tế. Người duyệt không nên tự tin vào một danh sách chỉ gồm email và lần đăng nhập cuối.

### 12.2. Bằng chứng cần lưu trong audit

| Sự kiện | Thông tin cần lưu |
|---|---|
 Partner/contract onboarding | Partner ID, relationship ID, trạng thái xác minh, sponsor |
 Access request | Principal, tenant, project, resource, action, expiry, lý do |
 Grant approval | Người phê duyệt, policy, scope, thời gian |
 Federation hoặc group mapping change | Issuer/source, ánh xạ trước–sau, người duyệt |
 Provisioning/JIT/SCIM | Nguồn, quyền thay đổi, kết quả ứng dụng |
 Access/API request | Principal, partner, resource, action, allow/deny, correlation ID |
 Mover/review | Grants trước–sau, reviewer, kết quả |
 Leaver | Scope cần gỡ, thời điểm, hệ thống đã xác nhận, ngoại lệ |
 Credential rotation/revoke | Client/secret reference, chủ sở hữu, kết quả |

Audit phải được giới hạn quyền đọc, có cơ chế bảo vệ tính toàn vẹn và thời hạn lưu giữ phù hợp. Không lưu mật khẩu, private key, session cookie hoặc token truy cập còn sử dụng được vào log.

### 12.3. Đối soát expected và actual access

Một grant đã bị thu hồi trong IAM nhưng vẫn có thể tồn tại ở ứng dụng đích nếu hệ thống đó quản lý ACL riêng, provisioning thất bại hoặc có quyền cấp thủ công. Đó là **quyền truy cập tồn dư**.

~~~text
for relationship in all_partner_relationships:
    expected = compute_access_from(
        relationship.status,
        approved_memberships,
        active_grants,
        contract_and_resource_policy
    )
    actual = collect_access_from_target_systems(
        relationship.partner_id,
        relationship.id
    )
    differences = compare(expected, actual)
    if differences:
        alert_sponsor_and_resource_owner(differences)
        remediate_with_system_owners(differences)
        verify_and_record_results()
~~~

Đây là mã giả quản trị. Không phải hệ thống nào cũng có API xuất quyền; cần ghi rõ **mức độ bao phủ**, cách kiểm tra thay thế và các sai lệch chưa thể xử lý. Không báo Leaver “hoàn tất” chỉ vì đã gửi request revoke trong khi app đích chưa xác nhận.

### 12.4. Các KPI có giá trị

| KPI | Mục tiêu quan sát |
|---|---|
 Grant active với relationship đã hết hạn | Phát hiện scope vượt vòng đời hợp đồng |
 Partner principal không có sponsor/resource owner | Phát hiện quyền mồ côi |
 Số grant vượt thời hạn hoặc review quá hạn | Kiểm tra hiệu lực của expiry và governance |
 Thời gian từ Leaver đến verified revoke | Đo độ trễ thu hồi xuyên ứng dụng |
 Số quyền production đặc biệt còn active | Phát hiện JIT/PAM không được kết thúc |
 Số quyền cross-tenant bị từ chối | Theo dõi kiểm soát và hành vi bất thường |
 Số API clients không có owner hoặc credential quá hạn | Phát hiện workload tồn dư |
 Số sai lệch IAM–downstream còn mở | Đo khả năng đối soát và remediation |

Ngưỡng và tần suất phụ thuộc độ nhạy, quy định, hợp đồng và khả năng vận hành. Chỉ số nhiều truy cập bị từ chối **không tự động chứng minh có tấn công**: có thể là lỗi ứng dụng hoặc người dùng thao tác sai.

## 13. Rủi ro thiết kế và anti-pattern thường gặp

| Sai lầm | Rủi ro | Cách phòng tránh |
|---|---|---|
 Chỉ kiểm tra role, không kiểm tra tenant | User B có thể đọc dữ liệu C | Xác minh resource ownership và membership ở API |
 Coi OAuth scope là toàn bộ entitlement | Token orders.read được dùng để đọc đơn của mọi đối tác | Ràng buộc scope với partner, contract, resource |
 Lấy tenant_id do client gửi làm sự thật | Caller có thể đổi tenant tùy ý | Backend xác nhận từ principal và resource metadata |
 Một nhóm partner-all-access | Quyền quá rộng và không phân biệt dự án | Vai trò tối thiểu và grants theo scope |
 Tin group Global-Admin từ IdP đối tác | Đối tác tự nâng quyền ở A | Role mapping có trần quyền do A kiểm soát |
 Tự ghép người dùng theo email | Người mới có thể kế thừa grants cũ | Subject ổn định từ issuer đã xác minh |
 Chia sẻ cùng OAuth client giữa B và C | Khó truy vết/thu hồi chọn lọc | Client riêng theo đối tác, ứng dụng, môi trường |
 Gắn scope chỉ trên frontend | API vẫn bị truy cập trực tiếp | Authorization tại backend cho từng object/action |
 Gỡ grant nguồn nhưng không kiểm tra app | ACL trực tiếp vẫn tồn tại | Reconciliation và xác minh downstream |
 Hết hợp đồng nhưng vẫn cho JIT tự tạo guest | Quyền bị tái kích hoạt | Kiểm tra trạng thái relationship trước provisioning |
 Chỉ disable IdP khi Leaver | Phiên, token và grants ở A còn hiệu lực | Session/token handling và revoke quyền tại A |
 Gia hạn contract đồng nghĩa gia hạn mọi role | Quyền không còn lý do tồn tại | Access review theo từng entitlement |
 Bỏ qua scope dữ liệu nhạy cảm | Guest được phép xem trường dữ liệu không cần thiết | Data classification, masking và policy cấp trường nếu phù hợp |
 Mọi request fail-open khi policy engine lỗi | Lỗi hạ tầng trở thành quyền không kiểm soát | Quy tắc fail-safe/deny mặc định theo rủi ro |

### 13.1. Đọc chéo dữ liệu (BOLA/IDOR)

Một API ví dụ có endpoint:

~~~http
GET /api/orders/332 HTTP/1.1
Authorization: Bearer <access-token>
~~~

Giả sử order 332 thuộc tenant-C, trong khi caller U chỉ có grant orders.read tại tenant-B. Nếu API chỉ kiểm tra token hợp lệ và quyền orders.read, U có thể đọc order của C bằng cách thay mã order. Đây là dạng thiếu **object-level authorization**, thường được mô tả trong các lỗi BOLA/IDOR.

Kiểm soát đúng: resource server tải order 332 từ nguồn tin cậy, xác định tenant/project sở hữu, đối chiếu với membership/grant hiện tại rồi **DENY** nếu không khớp. Dùng UUID khó đoán không thay thế kiểm tra quyền.

### 13.2. Quyền xuất dữ liệu khác quyền đọc

Một người có thể được xem báo cáo trên giao diện nhưng chưa chắc được phép xuất hàng nghìn bản ghi. Với dữ liệu nhạy cảm, scope nên cân nhắc action reports.export riêng, hạn mức xuất, data minimization, masking và audit. Tùy hệ thống, có thể cần phân quyền theo cột/trường hoặc mục đích xử lý.

### 13.3. Scope từ nhiều grants được tổng hợp thế nào?

Một principal có thể có nhiều grants hợp lệ. Hệ thống có thể cho phép hành động nếu **có ít nhất một grant rõ ràng cấp quyền cho action + resource đang xét**, **đồng thời** mọi điều kiện bảo vệ chung như partner status, tenant isolation, policy dữ liệu, thời hạn và explicit deny đều phải thỏa.

Không cộng dồn vô điều kiện các thuộc tính từ hai grants để tạo quyền mới. Ví dụ một grant cho reports.read tại P42 và grant khác cho reports.update tại P51 không được kết hợp thành reports.update tại P42.

## 14. Case study: hệ thống B2B có hai đối tác và ba loại quyền

Công ty A cung cấp nền tảng hậu cần cho B và C. B phụ trách đơn hàng khu vực miền Nam, C khu vực miền Bắc. Mỗi đối tác có nhân viên đăng nhập SSO và một số API clients riêng.

### 14.1. Bối cảnh

| Chủ thể | Quan hệ | Phạm vi hợp lệ |
|---|---|---|
 Nhân viên U của B | Hợp đồng B–A, dự án P42 | Đọc reports P42, tenant-B, đến 31/12 |
 Kỹ sư V của B | Ticket INC-2048 | Hỗ trợ staging P42; production chỉ theo JIT có duyệt |
 Client W của B | Tích hợp đồng bộ đơn | Cập nhật order status của B qua API |
 Nhân viên X của C | Hợp đồng C–A, dự án P51 | Đọc reports P51, tenant-C |

### 14.2. Sự kiện theo vòng đời

| Mốc | Sự kiện | Thay đổi scope phải thực hiện |
|---|---|---|
 Ngày 1 | A ký hợp đồng với B và C | Tạo partner/relationship riêng; phân định tenant |
 Ngày 2 | U đăng nhập qua IdP B | Liên kết local principal, chỉ cấp grant P42 |
 Ngày 3 | W tích hợp API A | Đăng ký client riêng B, audience/scope/API entitlement phù hợp |
 Ngày 15 | V cần xử lý sự cố production | Resource owner duyệt JIT elevation cho host/ticket, có hạn |
 Ngày 30 | U chuyển từ P42 sang P53 | Thu hồi P42, phê duyệt P53 mới nếu thuộc hợp đồng |
 Ngày 40 | B thu hẹp hợp đồng, bỏ tích hợp W | Disable client W, key/secret và API grants |
 Ngày 60 | Hợp đồng B–A kết thúc | Offboard mọi quyền phát sinh từ quan hệ B; giữ C hoạt động |

### 14.3. Phân tích ba request

**Request A — Hợp lệ:** U đọc report P42 khi grant còn hiệu lực. Backend kiểm tra user U thuộc B, đúng relationship, grant reports.read, report thuộc tenant-B/P42 và thỏa điều kiện chính sách. Kết quả ALLOW.

**Request B — Sai tenant:** U thay ID báo cáo sang report thuộc C. Token của U vẫn hợp lệ và role viewer không thay đổi, nhưng resource.tenant_id là tenant-C trong khi membership/grant chỉ cho tenant-B. Kết quả DENY, ghi audit.

**Request C — Scope máy vượt giới hạn:** Client W gửi yêu cầu xóa một đơn của C bằng token có scope orders.status.update. Resource server từ chối vì token/entitlement không cấp action delete, tài nguyên thuộc C và client gắn B. Có nhiều lý do DENY độc lập; **không cần lộ chi tiết dữ liệu C trong response**.

### 14.4. Kiểm thử Leaver

Ngày 60, nếu A chỉ khóa SSO người B mà chưa vô hiệu hóa client W, một workload có thể vẫn gọi API. Ngược lại, chỉ disable W cũng không gỡ group tài liệu hoặc phiên người dùng. Chấm dứt quan hệ cần truy ngược đầy đủ **grants theo relationship** và đối soát ở API, ứng dụng, SaaS và các kênh chia sẻ.

### 14.5. Bài học triển khai

Ba trạng thái có thể khác nhau: **đối tác còn hợp lệ**, **principal còn được xác thực**, và **grant cho tài nguyên còn hiệu lực**. Mọi quyết định ALLOW đòi hỏi kết hợp đúng ba lớp với scope theo object và action; audit phải cho thấy quyết định đã dựa trên grant nào, theo quan hệ nào.

## 15. Bài tập thiết kế policy cho partner access scope

### 15.1. Yêu cầu

Thiết kế một API quản lý tài liệu với hai tenant B và C:

1. Nhân viên B được đọc tài liệu thuộc P42 nhưng không được ghi.
2. Nhân viên C được đọc và bình luận ở P51; không được truy cập P42.
3. Một auditor bên B được đọc các tài liệu kiểm toán được đánh dấu audit-approved trong P42, không đọc tài liệu hạn chế khác.
4. Client đồng bộ của B chỉ được cập nhật trạng thái đơn thuộc B, không cập nhật thông tin thanh toán.
5. Tất cả quyền hết hiệu lực khi relationship tương ứng bị revoked, dù session hoặc token chưa hết hạn.

Hãy xác định:

- Các role/actions cần dùng;
- Partner, relationship, tenant và project của mỗi grant;
- Thuộc tính của resource mà backend phải tải từ nguồn tin cậy;
- Điều kiện thời hạn, sponsor và resource owner;
- Những request phải bị DENY và cách xác minh kết quả.

### 15.2. Một cách giải tham khảo

| Principal | Role/action | Scope tài nguyên | Điều kiện |
|---|---|---|---|
| U của B | documents.read | tenant-B, P42 | Contract active, grant còn hạn |
| X của C | documents.read, comments.create | tenant-C, P51 | Contract active, grant còn hạn |
| Auditor của B | audit.documents.read | tenant-B, P42, audit-approved only | Thời hạn kiểm toán, phân loại dữ liệu |
| Client W của B | orders.status.update | order thuộc tenant-B | Client active, audience/scope và contract hợp lệ |

Backend truy xuất resource ownership và classification, xác thực principal/token, tìm grant áp dụng cho **đúng action và đúng resource**, kiểm tra trạng thái relationship và các điều kiện bảo mật. Thiết kế các test:

- U đọc tài liệu P42: ALLOW; sửa tài liệu P42: DENY.
- U đọc tài liệu P51: DENY.
- X bình luận trong P51: ALLOW; đọc P42: DENY.
- Auditor B đọc audit-approved P42: ALLOW; đọc tài liệu restricted P42: DENY.
- W cập nhật status đơn thuộc B: ALLOW; cập nhật payment hoặc đơn C: DENY.
- Tất cả request trên bị DENY sau khi relationship tương ứng revoked.

Để tránh test quá khớp một user, nên tạo fixture với nhiều principal và tài nguyên được gán chéo, kể cả tài nguyên đổi tenant hoặc quyền hết hạn trong khi session còn sống.

## 16. Checklist triển khai partner access scope

### Thiết kế quan hệ và quyền

- [ ] Có partner_id và relationship_id ổn định, trạng thái và hạn hợp đồng rõ.
- [ ] Chủ thể human/workload được xác minh, liên kết với đúng partner và membership.
- [ ] Scope bao gồm tenant, project, resource, action, môi trường, expiry và điều kiện cần thiết.
- [ ] Sponsor và resource owner có trách nhiệm, phê duyệt các quyền đúng thẩm quyền.
- [ ] RBAC roles chỉ là nhóm hành động; ABAC/entitlement giới hạn dữ liệu, tenant và ngữ cảnh.
- [ ] Quyền delegated admin có trần role và tenant rõ ràng.

### Thực thi kỹ thuật

- [ ] OIDC/SAML trust xác minh đúng issuer/chữ ký/audience/định danh người dùng.
- [ ] OAuth access token được xác minh nhưng không thay thế kiểm tra tài nguyên.
- [ ] API/backend kiểm tra ownership và scope trên từng object/action, không tin tenant_id tự khai.
- [ ] Có test chéo tenant, sai action, hết hạn grant và relationship bị suspended.
- [ ] Workload có client identity/credential riêng, scope và environment tách biệt.
- [ ] JIT/SCIM không tự cấp quyền rộng hoặc hồi sinh grants đã revoked.

### Vòng đời và kiểm chứng

- [ ] Joiner định nghĩa scope tối thiểu và xác minh provisioning đã áp dụng.
- [ ] Mover so sánh quyền trước/sau, thu hồi quyền không còn cần.
- [ ] Leaver thu hồi đúng relationship/grant và xử lý session/token/workload liên quan.
- [ ] Có access review theo mức rủi ro, thời hạn và owner hợp lệ.
- [ ] Có audit cho grant, identity linking, API decision và kết quả thu hồi.
- [ ] Có reconciliation giữa IAM registry và quyền thực tế tại hệ thống đích.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Một user B có OIDC token hợp lệ và role viewer. Có thể xem mọi báo cáo ở hệ thống A không?

**Trả lời:** Không. Token xác thực danh tính, còn role cần được giới hạn bởi tenant/project/resource, contract và thời hạn. Backend phải kiểm tra report cụ thể nằm trong scope đã cấp.

**Câu 2.** OAuth access token mang scope orders.read. Có đủ để đọc đơn của tenant-C khi client thuộc partner-B?

**Trả lời:** Không. API phải kiểm tra client/principal, quan hệ partner và quyền trên order cụ thể. Scope token là một điều kiện, không thay toàn bộ authorization nghiệp vụ.

**Câu 3.** Vì sao grant của P42 không nên được kết hợp với grant P51 để tạo quyền mới?

**Trả lời:** Các thuộc tính của grants không được trộn tùy ý. Hệ thống chỉ cho phép action khi có grant áp dụng đầy đủ cho đúng resource, đồng thời thỏa các guardrails như tenant isolation và relationship validity.

**Câu 4.** Một người chuyển từ P42 sang P51, có thể chỉ thêm role P51 và giữ P42 cho tiện?

**Trả lời:** Không nếu quyền P42 không còn cần. Cần thu hồi grants cũ để tránh privilege accumulation, sau đó cấp P51 qua phê duyệt phù hợp.

**Câu 5.** Khi một đối tác có hai hợp đồng nhưng một hợp đồng hết hạn, có nên disable toàn bộ partner không?

**Trả lời:** Phụ thuộc phạm vi sự kiện. Nếu chỉ một relationship kết thúc, cần thu hồi grants phát sinh từ relationship đó, giữ quyền hợp lệ còn lại. Nếu toàn bộ quan hệ đã kết thúc hoặc có sự cố cần khóa toàn partner thì xử lý theo chính sách tương ứng.

**Câu 6.** SCIM báo một user inactive. Có thể bỏ qua session và downstream ACL không?

**Trả lời:** Không. SCIM cập nhật các bản ghi/nhóm trong phạm vi tích hợp; session, access token hoặc chia sẻ ứng dụng khác có thể còn. Cần revoke và reconciliation.

**Câu 7.** Làm sao ngăn user B xem tài liệu C bằng cách thay ID trên URL?

**Trả lời:** Backend tải metadata tài liệu từ nguồn tin cậy, kiểm tra tenant/project ownership cùng membership/grant của principal rồi DENY nếu không khớp; không chỉ ẩn tài liệu trên frontend.

**Câu 8.** Khi client B hết hợp đồng, thao tác nào ngoài khóa người dùng cần thực hiện?

**Trả lời:** Tìm và disable OAuth client/service account, thu hồi API key, credential/certificate, grants, webhook và quyền downstream liên quan; kiểm chứng actual access.

**Câu 9.** Vì sao phải phân biệt expiry hợp đồng, grant, session và token?

**Trả lời:** Chúng thuộc các lớp khác nhau. Một token còn hạn không làm một grant đã bị revoke hợp lệ trở lại; một hợp đồng còn hạn cũng không tự kéo dài grant production có thời gian ngắn.

**Câu 10.** Access review chỉ có tên tài khoản và last login đã đủ chưa?

**Trả lời:** Chưa. Cần biết partner/relationship, sponsor, tài nguyên, action, tenant, thời hạn, trạng thái dữ liệu và quyền thực tế ở ứng dụng đích để xác nhận nhu cầu còn hợp lệ.

## Kết luận

**Partner access scope** biến yêu cầu “đối tác được truy cập” thành quyền **đúng người hoặc workload, đúng quan hệ, đúng tenant/dự án, đúng tài nguyên, đúng hành động và đúng thời điểm**. IdP và SSO xác thực danh tính; SCIM/JIT hỗ trợ provisioning; **RBAC/ABAC và resource server** giới hạn, thực thi quyền trên dữ liệu thực tế; sponsor/resource owner phê duyệt mục đích và phạm vi. Khi scope được thiết kế theo **Joiner–Mover–Leaver**, được review, ghi audit và đối soát với hệ thống đích, tổ chức giảm nguy cơ truy cập chéo đối tác và **quyền truy cập tồn dư** sau khi vai trò hoặc hợp đồng thay đổi.
