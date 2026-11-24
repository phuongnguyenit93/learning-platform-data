# Gán organization trong Identity enrollment

## 1. Gán organization là gì?

Trong **Identity and Access Management (IAM)**, *identity enrollment* là quá trình tiếp nhận và xác minh thông tin về một chủ thể, thiết lập danh tính số, liên kết danh tính với các thực thể có liên quan và chuẩn bị điều kiện để cấp tài khoản hoặc quyền truy cập. **Gán organization** (*organization assignment*) là bước xác lập quan hệ giữa một danh tính và **tổ chức hoặc phạm vi tổ chức mà danh tính đó có căn cứ hợp lệ để tham gia**.

Ví dụ, một nhân viên mới được xác minh là người thuộc Công ty A. Hệ thống IAM có thể liên kết danh tính của họ với organization `org-company-a`. Liên kết này giúp xác định phạm vi quản lý danh tính, chính sách onboarding, đầu mối phê duyệt và những tài nguyên có thể được xem xét cấp quyền. Nếu nhân viên được phân công vào phòng Kỹ thuật, hệ thống có thể lưu thêm quan hệ phòng ban hoặc vị trí bên trong tổ chức.

**Gán organization không tự động có nghĩa là cấp mọi quyền của tổ chức.** Một người có thể thuộc Công ty A nhưng không được truy cập mọi repository, báo cáo hoặc tài liệu của Công ty A. Quyền thực tế vẫn phải được quyết định qua chính sách **RBAC/ABAC**, nhóm, vai trò, entitlement, điều kiện bảo mật và kiểm tra tại hệ thống đích.

Trong quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, quan hệ organization ảnh hưởng trực tiếp đến việc xác định ai thuộc phạm vi nào, ai chịu trách nhiệm duyệt quyền, ai được phép dùng tài nguyên nào và khi nào phải thay đổi hoặc thu hồi quyền truy cập.

### Mục tiêu cần đạt

Một phép gán organization tốt phải trả lời được:

1. **Danh tính nào** đang được gán, đã được xác minh và liên kết đúng người hoặc workload chưa?
2. **Organization nào** là đích, có mã định danh ổn định, trạng thái hợp lệ và ranh giới quản trị rõ ràng không?
3. **Vì sao được gán**: hợp đồng lao động, quan hệ đối tác, phân công dự án, quyền bảo trợ hay quyết định được duyệt?
4. **Ai có thẩm quyền xác nhận** nguồn dữ liệu và người phê duyệt?
5. **Quan hệ có hiệu lực khi nào**, có cần tự kết thúc hoặc xem xét lại khi thay đổi vai trò không?
6. **Những quyền nào phụ thuộc vào quan hệ**, và sẽ bị thu hồi như thế nào khi quan hệ mất hiệu lực?

## 2. Phân biệt organization với những khái niệm gần nhau

Từ `organization` được các HRIS, IdP, ứng dụng SaaS và nền tảng cloud sử dụng theo nhiều nghĩa. Trước khi xây dựng luồng enrollment, tổ chức phải định nghĩa đúng phạm vi.

| Khái niệm | Ý nghĩa | Ví dụ | Tác động đến IAM |
| --- | --- | --- | --- |
| **Organization** | Thực thể hoặc miền quản trị được hệ thống công nhận | `org-company-a` | Phạm vi quản lý, phê duyệt, chính sách và tài nguyên |
| **Legal entity** | Pháp nhân hoặc đơn vị tuyển dụng trong HR | Công ty A Việt Nam | Căn cứ quan hệ lao động, tuân thủ và chủ thể tuyển dụng |
| **Department / Org unit** | Bộ phận trong cơ cấu tổ chức | Kỹ thuật, Kế toán | Thuộc tính cho RBAC/ABAC và tuyến quản lý |
| **Project / Team** | Phạm vi phân công công việc | Dự án Atlas | Căn cứ cấp quyền theo dự án, thường có thời hạn |
| **Tenant** | Ranh giới cách ly dữ liệu hoặc cấu hình của một ứng dụng/dịch vụ | Tenant A trên nền tảng SaaS | Quy tắc phân tách truy cập cần thực thi tại ứng dụng |
| **Directory / IdP realm** | Miền lưu trữ và xác thực các danh tính | Directory của doanh nghiệp | Nguồn tài khoản, chính sách đăng nhập và đồng bộ |
| **Group** | Tập danh tính/tài khoản để quản trị hoặc phân phối quyền | `engineering-readers` | Có thể dẫn tới entitlement cụ thể |
| **Role** | Tập quyền hoặc trách nhiệm được định nghĩa | `ReportViewer` | Quyết định loại hành động được phép |

Các khái niệm này **có thể trùng về mặt tổ chức nhưng không nhất thiết tương ứng một–một**. Một tập đoàn có nhiều pháp nhân trong cùng một tenant; một organization có nhiều tenant ứng dụng; một người có thể làm việc cho hai organization; một department có thể đổi tên nhưng mã organization không đổi.

Vì vậy, không nên ngầm hiểu:

- `organizationId` luôn chính là `tenantId`;
- một email domain đồng nghĩa với một organization;
- thành viên organization tự động là thành viên mọi group của tổ chức;
- người quản lý của nhân viên có quyền truy cập mọi dữ liệu thuộc organization;
- đổi department luôn có nghĩa cần đổi organization.

Nếu một hệ thống dùng khái niệm organization như **ranh giới bảo mật của tenant**, mọi truy vấn tài nguyên phải áp dụng ranh giới tương ứng. Nếu chỉ là **thuộc tính phân loại trong HR**, cần có chính sách riêng quyết định tác động tới quyền.

## 3. Organization assignment là một quan hệ có vòng đời

Thay vì chỉ coi `organizationId` là trường văn bản trong profile, hãy nhìn phép gán như một quan hệ có nguồn gốc và trạng thái:

> Identity X **thuộc** Organization Y, **theo căn cứ** Z, **trong khoảng thời gian** T, **được xác nhận** bởi nguồn có thẩm quyền.

Các trường nên xác định tùy mô hình hệ thống:

| Thuộc tính quan hệ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `identityId` | Danh tính số được gán | `id-482` |
| `organizationId` | Mã organization ổn định | `org-company-a` |
| `relationshipType` | Loại quan hệ | `employee`, `contractor`, `partner` |
| `sourceSystem` | Hệ thống có thẩm quyền xác nhận | `hris-main` |
| `sourceReference` | Mã bản ghi lao động/hợp đồng/bảo trợ | `employment-2026-18` |
| `validFrom`, `validUntil` | Khoảng hiệu lực nghiệp vụ | Bắt đầu ngày vào làm, kết thúc theo hợp đồng |
| `status` | Dự kiến, đang hiệu lực, đình chỉ, đã kết thúc | `active` |
| `approvalReference` | Bằng chứng duyệt nếu chính sách yêu cầu | `approval-705` |
| `ownerOrSponsor` | Người chịu trách nhiệm về quan hệ | Người quản lý hoặc sponsor hợp lệ |
| `sourceVersion` | Phiên bản cập nhật từ hệ thống gốc | `8` |

**Một danh tính có thể liên kết nhiều organization** khi nghiệp vụ cho phép. Mô hình cần quy định rõ `primary organization` (nếu thực sự cần), quan hệ thứ cấp, phạm vi áp dụng từng quan hệ và cách chọn ngữ cảnh khi đăng nhập. Không tự áp đặt quy tắc một danh tính chỉ thuộc duy nhất một organization nếu hệ thống phải hỗ trợ nhiều hợp đồng, khách hàng hay tenant.

### Sơ đồ quan hệ khái niệm

~~~mermaid
flowchart LR
    H["Nguồn có thẩm quyền<br/>HRIS / hệ thống đối tác"] -->|"xác nhận"| E["Employment / Sponsorship<br/>Quan hệ nghiệp vụ"]
    P["Person / Workload<br/>Chủ thể"] -->|"được ánh xạ"| I["IAM identity"]
    E -->|"căn cứ gán"| M["Organization membership<br/>Quan hệ có thời hạn"]
    I -->|"chủ thể của"| M
    M -->|"thuộc phạm vi"| O["Organization"]
    O -->|"có thể liên kết"| U["Org unit / Project / Tenant"]
    M -->|"đầu vào cho"| C["IAM policy / Approval"]
    C -->|"gán khi đủ điều kiện"| R["Group / Role / Entitlement"]
    R -->|"kiểm soát"| T["Resource"]
    I -->|"provision"| A["Application account"]
    A -->|"truy cập qua kiểm soát đích"| T
~~~

Sơ đồ thể hiện quan hệ giữa dữ liệu tổ chức và việc đánh giá quyền. Quyền cuối cùng được thực thi tại **ứng dụng hoặc dịch vụ sở hữu tài nguyên**, kể cả khi danh tính đã có organization trong IAM.

## 4. Nguồn có thẩm quyền cho phép gán organization

Không nên để người dùng tự chọn bất kỳ organization nào rồi coi giá trị đó là căn cứ bảo mật. Tổ chức cần chỉ định **nguồn có thẩm quyền (*authoritative source*)** theo loại danh tính và quan hệ.

| Loại danh tính | Nguồn xác nhận organization (ví dụ) | Căn cứ cần có |
| --- | --- | --- |
| Nhân viên | HRIS và đơn vị quản trị nhân sự | Bản ghi tuyển dụng, pháp nhân, trạng thái và ngày hiệu lực |
| Nhân viên chuyển tổ chức | HRIS/quy trình luân chuyển đã duyệt | Organization cũ/mới, ngày hiệu lực và quan hệ còn lại |
| Nhà thầu | Hệ thống quản lý nhà thầu/đối tác | Hợp đồng, sponsor, thời hạn và organization được bảo trợ |
| Đối tác B2B | Danh mục đối tác hoặc quy trình mời vào tổ chức | Pháp nhân đối tác, người mời có thẩm quyền, phạm vi hợp tác |
| Khách hàng của ứng dụng đa tenant | Hệ thống tenant/membership của sản phẩm | Lời mời hợp lệ, quyền quản trị tenant, xác minh liên kết |
| Workload / service identity | Danh mục dịch vụ và đội quản trị ứng dụng | Chủ sở hữu, ứng dụng, môi trường, organization chịu trách nhiệm |

Trong một tổ chức, **HRIS có thể là nguồn có thẩm quyền về quan hệ lao động nhưng không phải nguồn chuẩn cho mọi quyền trong cloud**. Tương tự, danh sách thành viên trong ứng dụng có thể phản ánh trạng thái thực tế nhưng không nhất thiết có quyền quyết định ai còn là nhân viên.

Các nguồn cần được quy định theo từng thuộc tính: `legalEntityId` đến từ HR, `projectId` có thể đến từ hệ thống dự án, `organizationId` trong SaaS có thể do hệ thống quản trị tenant quản lý. Khi các nguồn xung đột, áp dụng quy tắc ưu tiên đã định nghĩa theo loại quan hệ thay vì tùy chọn giá trị cập nhật mới nhất.

### Vấn đề ánh xạ ID

Một organization có thể có nhiều mã ở các hệ thống: `org-company-a` trong IAM, `legal-018` trong HRIS và `tenant-a-01` trong SaaS. Cần **bảng ánh xạ được quản trị** giữa các định danh này. Không nên dựa riêng vào tên hiển thị như “Công ty A”, tên phòng ban hoặc domain email vì chúng có thể đổi, trùng hoặc được sử dụng chung.

## 5. Điều kiện kiểm tra trước khi gán

Trước khi tạo hoặc kích hoạt membership, luồng enrollment nên thực hiện các kiểm tra sau:

1. **Danh tính hợp lệ:** đã xác minh chủ thể ở mức phù hợp; liên kết đúng `personId`/`workerId` hoặc workload; không có dấu hiệu account linking nhầm.
2. **Organization tồn tại:** `organizationId` có thực, không bị vô hiệu hóa, không dùng mã từ tenant khác do người yêu cầu tự nhập.
3. **Căn cứ hợp lệ:** quan hệ lao động, hợp đồng, lời mời hoặc sponsorship đã được xác nhận; không dùng bản nháp chưa duyệt làm căn cứ kích hoạt.
4. **Người yêu cầu có thẩm quyền:** quản trị viên, sponsor hoặc quy trình tự động chỉ được gán vào organization thuộc phạm vi ủy quyền.
5. **Quan hệ không mâu thuẫn:** có hỗ trợ nhiều organization không, membership mới có trùng, đè lên hoặc xung đột với quan hệ đang hiệu lực không?
6. **Ngày hiệu lực đúng:** xác định `validFrom`, `validUntil`, timezone và quy tắc inclusive/exclusive khi đầu vào là ngày lịch.
7. **Chính sách quyền phù hợp:** organization assignment nào cần phê duyệt bổ sung, yêu cầu xác thực mạnh hoặc phân tách nhiệm vụ?
8. **Kiểm soát dữ liệu:** chỉ chuyển các thuộc tính cần thiết sang IdP, token hoặc ứng dụng; tránh lộ dữ liệu cá nhân từ HR.

Nếu không thể xác minh một điều kiện **cần thiết cho việc gán an toàn**, nên giữ yêu cầu ở trạng thái chờ xử lý thay vì âm thầm gán theo organization mặc định. Trường hợp cần quyền tối thiểu để hoàn tất onboarding, phải có chính sách rõ ràng, giới hạn tài nguyên và thời hạn.

## 6. Quy trình gán organization khi identity enrollment

Luồng thường gặp từ đầu vào nhân sự/đối tác tới quyền truy cập:

~~~mermaid
flowchart TD
    A["Nhận enrollment request / HR event"] --> B["Xác minh identity và liên kết người/workload"]
    B --> C["Lấy organization từ nguồn có thẩm quyền"]
    C --> D["Đối chiếu organization ID, trạng thái, tenant, thời hạn"]
    D --> E{"Dữ liệu hợp lệ và đủ căn cứ?"}
    E -->|"Không"| F["Chặn kích hoạt, ghi lỗi và xử lý ngoại lệ"]
    E -->|"Có"| G{"Cần chủ organization phê duyệt?"}
    G -->|"Có"| H["Xác minh phê duyệt"]
    H -->|"Từ chối"| F
    H -->|"Đồng ý"| I["Lưu quan hệ identity–organization"]
    G -->|"Không"| I
    I --> J["Tính chính sách nhóm, role, entitlement có điều kiện"]
    J --> K["Provision IdP / ứng dụng nếu cần"]
    K --> L["Đối soát quyền thực tế và lưu audit"]
~~~

**Bước 1 – Nhận yêu cầu.** Thu thập tối thiểu ID danh tính, ID organization, nguồn dữ liệu, loại quan hệ và mốc hiệu lực. Không dùng quyền truy cập đã có ở hệ thống đích làm bằng chứng duy nhất về tư cách tổ chức.

**Bước 2 – Xác minh và liên kết.** Nếu người đã có identity, đối chiếu mã ổn định thay vì gộp theo email. Nếu là người quay lại làm việc, kiểm tra việc tái sử dụng identity và những quyền từ giai đoạn cũ.

**Bước 3 – Kiểm tra tổ chức.** Organization phải là đối tượng đã được quản trị, với chủ sở hữu/đầu mối và trạng thái phù hợp. Khi tổ chức có nhiều tenant, xác định ánh xạ tenant rõ ràng.

**Bước 4 – Duyệt và lưu.** Tạo quan hệ có lịch sử, trạng thái và thời hạn. Nên hỗ trợ thao tác lặp an toàn (*idempotent*) để một sự kiện bị gửi lại không tạo membership hoặc cấp quyền trùng.

**Bước 5 – Tính quyền phát sinh.** Dựa trên quy tắc RBAC/ABAC, loại lao động, vai trò, dự án và mức nhạy cảm. Quyền đặc biệt cần chủ tài nguyên xác nhận khi chính sách yêu cầu.

**Bước 6 – Provision và kiểm chứng.** Đồng bộ trạng thái cần thiết đến IdP và ứng dụng, sau đó đối chiếu account, nhóm, role, ACL và quyền hiệu lực. Khi có lỗi từng hệ thống, lưu trạng thái xử lý để retry hoặc chuyển người phụ trách giải quyết.

## 7. Ví dụ bản ghi gán organization

Ví dụ JSON minh họa, **không phải schema chuẩn bắt buộc của một sản phẩm IAM hay giao thức SCIM**:

~~~json
{
  "relationshipId": "membership-2026-340",
  "identityId": "id-482",
  "organizationId": "org-company-a",
  "relationshipType": "employee",
  "sourceSystem": "hris-main",
  "sourceReference": "employment-2026-18",
  "status": "active",
  "validFrom": "2026-11-23T00:00:00+07:00",
  "validUntil": null,
  "isPrimary": true,
  "approvalReference": "hr-confirmation-778",
  "sourceVersion": 8,
  "createdAt": "2026-11-22T10:31:00+07:00"
}
~~~

Ví dụ một event Mover về thay đổi organization:

~~~json
{
  "eventId": "hr-event-940",
  "eventType": "employment.organization_changed",
  "personId": "person-482",
  "employmentId": "employment-2026-18",
  "oldOrganizationId": "org-company-a",
  "newOrganizationId": "org-company-b",
  "effectiveAt": "2026-12-01T00:00:00+07:00",
  "approved": true,
  "sourceVersion": 9
}
~~~

Một phép cập nhật an toàn phải xác định rõ **quan hệ nào chấm dứt**, **quan hệ nào được tạo** và **quyền nào cần tính lại**. Nếu người này có quan hệ hợp lệ khác với `org-company-a`, việc kết thúc `employment-2026-18` không nhất thiết làm mất mọi quyền tại organization A.

### Mã giả cho thao tác gán

~~~text
assignOrganization(identityId, requestedOrgId, sourceEvent):
    identity = lookupVerifiedIdentity(identityId)
    organization = lookupManagedOrganization(requestedOrgId)
    require(identity != null AND organization.isActive)
    require(isTrustedAuthoritativeSource(sourceEvent))
    require(sourceEvent.isApprovedFor(requestedOrgId))
    require(sourceEvent.subjectMatches(identity))
    require(requestedOrgId IN permittedOrganizationScope(sourceEvent.actor))
    require(sourceEvent.version >= currentAcceptedVersion(sourceEvent.sourceReference))

    membership = upsertIdempotently(
        identityId,
        requestedOrgId,
        sourceEvent.sourceReference,
        sourceEvent.effectiveInterval
    )
    recordAudit(sourceEvent, membership)
    targetAccess = evaluatePolicies(identity, membershipsAtEffectiveTime(identity))
    provisionAndReconcile(targetAccess)
    return membership
~~~

Đây chỉ là mã giả thể hiện trách nhiệm nghiệp vụ. Với hệ thống thực tế, cần xử lý cạnh tranh cập nhật, lưu trạng thái giao dịch và retry idempotent, đồng bộ bất đồng bộ, kiểm tra phiên bản và phục hồi khi cập nhật một phần thành công.

## 8. Primary organization, secondary organization và đa tổ chức

Một số hệ thống yêu cầu mỗi identity có **một organization chính** để xác định đơn vị quản lý hoặc danh bạ mặc định. Trong khi đó, các ứng dụng đa tenant có thể cho phép người dùng thuộc **nhiều organization**.

Ví dụ:

- Nhân viên công ty mẹ được phân công làm việc cho công ty con: organization chính có thể vẫn là công ty tuyển dụng, còn tổ chức thứ cấp phản ánh quyền cộng tác đã được duyệt.
- Chuyên gia tư vấn có hợp đồng với hai khách hàng: mỗi quan hệ cần sponsor, thời hạn và tập quyền riêng.
- Người sử dụng ứng dụng SaaS được mời vào hai tenant: quyền trong tenant A không được tự động lan sang tenant B.

Các nguyên tắc:

1. **Phân biệt membership với ngữ cảnh đang chọn.** Khi người dùng chuyển organization trong giao diện, ứng dụng phải đánh giá quyền theo organization đích; không sử dụng quyền của organization trước đó.
2. **Không hợp nhất quyền từ nhiều organization nếu chính sách không cho phép.** Nhất là dữ liệu khách hàng hoặc pháp nhân khác nhau.
3. **Quan hệ có thời hạn riêng.** Hết hợp đồng A chỉ thu hồi quyền phát sinh từ A, không tùy tiện chặn quan hệ B còn hợp lệ.
4. **Primary không đồng nghĩa đặc quyền cao hơn.** Nó chỉ có ý nghĩa theo định nghĩa hệ thống, có thể dùng để định tuyến quản trị hoặc chọn ngữ cảnh mặc định.
5. **Chống rò rỉ xuyên tenant.** Truy vấn, API, cache, export và job nền phải kiểm tra ranh giới tenant/organization được phê duyệt.

Việc đổi organization chính cần được đánh giá như một sự kiện quan trọng trong vòng đời danh tính. Nó có thể ảnh hưởng người quản lý, loại tài khoản, chính sách đăng nhập, ứng dụng được cấp và các ràng buộc lưu trữ dữ liệu.

## 9. Từ organization assignment đến RBAC và ABAC

**RBAC (Role-Based Access Control)** áp dụng vai trò theo công việc hoặc chức năng. Quan hệ organization có thể là một điều kiện để cấp vai trò, ví dụ người làm việc tại organization A và có job code `SALES_ANALYST` được xem xét cấp `SalesReportViewer` trong phạm vi A.

**ABAC (Attribute-Based Access Control)** kiểm tra thuộc tính của chủ thể, tài nguyên và ngữ cảnh; organization là một thuộc tính thường gặp. Một chính sách có thể yêu cầu organization của chủ thể khớp organization sở hữu tài nguyên, identity còn hiệu lực và role cho phép hành động.

Ví dụ chính sách **mã giả**, không đại diện cú pháp của sản phẩm cụ thể:

~~~text
ALLOW subject READ resource IF:
    subject.identityStatus == ACTIVE
    AND activeMembership(subject, resource.organizationId)
    AND subject.roleWithin(resource.organizationId) includes REPORT_VIEWER
    AND resource.sensitivity <= subject.approvedClearance
    AND request.tenantContext == resource.tenantId
    AND noHigherPriorityDeny(subject, resource, request)
ELSE DENY
~~~

Điều kiện `activeMembership` phải kiểm tra **quan hệ có hiệu lực** tại thời điểm yêu cầu, không chỉ một claim cũ từ lần đăng nhập trước. Tùy kiến trúc, backend có thể truy vấn nguồn quyền, xác thực token mới, dùng cache có kiểm soát hoặc áp dụng cơ chế thu hồi chủ động.

### Ví dụ sai: organization là tất cả quyền

Nếu ứng dụng chỉ có điều kiện `user.organizationId == resource.organizationId`, nhân viên mới thuộc organization A có thể thấy mọi dữ liệu tài chính, nhân sự và bí mật kinh doanh của A. Mô hình đúng phải tiếp tục kiểm tra **vai trò, tài nguyên, hành động, phân loại dữ liệu và điều kiện bổ sung**.

## 10. Vai trò của HRIS, IdP, SSO và SCIM

Gán organization thường đi qua nhiều lớp hệ thống. Mỗi lớp có phạm vi trách nhiệm:

| Thành phần | Vai trò trong organization assignment | Giới hạn cần hiểu |
| --- | --- | --- |
| **HRIS / nguồn đối tác** | Xác minh quan hệ lao động/đối tác và organization thuộc phạm vi nghiệp vụ | Không phải nơi quản trị mọi entitlement kỹ thuật |
| **IAM governance** | Liên kết identity–organization; đánh giá điều kiện, phê duyệt, thời hạn và JML | Trạng thái mục tiêu phải được xác nhận ở hệ thống đích |
| **IdP (Identity Provider)** | Quản lý danh tính đăng nhập, trạng thái, nhóm, thuộc tính organization cần thiết | Nhóm/claim IdP không bao phủ tất cả ACL cục bộ |
| **SSO (Single Sign-On)** | Truyền thông tin xác thực và claim đã được cấu hình tới ứng dụng | Login thành công không tự cấp quyền vào mọi tài nguyên của organization |
| **SCIM (System for Cross-domain Identity Management)** | Đồng bộ lifecycle của User/Group với ứng dụng hỗ trợ | Không có bảo đảm mọi ứng dụng tự hiểu custom `organizationId` hay quyền tenant |
| **Ứng dụng đích** | Ánh xạ tài khoản/nhóm và thực thi kiểm soát tài nguyên, tenant, ACL | Có thể có quyền cục bộ hoặc phiên chưa bị thu hồi |

Trong SCIM, việc truyền organization có thể cần **trường/extension được ứng dụng hỗ trợ và hợp đồng mapping rõ ràng**. Không nên giả định chỉ cần gửi một trường `organizationId` là mọi ứng dụng sẽ tự tạo membership tenant hoặc trao đúng quyền.

Trong SSO dùng OIDC hoặc SAML, các claim về organization/tenant nếu có phải được ứng dụng kiểm tra **nguồn phát hành đáng tin cậy**, chữ ký, audience, thời hạn và ngữ cảnh phù hợp. **Claim do client gửi tùy ý** không thể thay thế quyết định thành viên organization phía máy chủ. Nếu người dùng đổi organization, ứng dụng cần bảo đảm token/phiên và quyền hiệu lực được cập nhật đúng.

### Ví dụ luồng đồng bộ

~~~mermaid
sequenceDiagram
    participant HR as HRIS / nguồn có thẩm quyền
    participant IAM as IAM governance
    participant IdP as IdP
    participant App as Ứng dụng đích
    HR->>IAM: Organization mới, identity, thời điểm hiệu lực
    IAM->>IAM: Kiểm tra nguồn, tổ chức và chính sách
    IAM->>IAM: Ghi quan hệ identity–organization
    IAM->>IdP: Cập nhật thuộc tính / nhóm được duyệt
    IdP->>App: SCIM / API nếu ứng dụng hỗ trợ
    App-->>IAM: Kết quả provisioning / membership
    IAM->>App: Đối soát quyền thực tế và ranh giới tenant
    App-->>IAM: Trạng thái xác nhận / lỗi cần xử lý
~~~

Một phản hồi đồng bộ thành công chỉ phản ánh phần việc đã chạy. Để chứng minh yêu cầu đã hoàn thành, cần kiểm tra **membership và effective access tại ứng dụng**.

## 11. Quan hệ organization trong Joiner–Mover–Leaver

### 11.1. Joiner — xác lập tổ chức hợp lệ từ đầu

Khi nhân viên mới được HR xác minh, IAM liên kết identity với organization theo `employmentId` hoặc căn cứ tương ứng. Tùy quy trình, account có thể được chuẩn bị trước ngày vào làm nhưng quyền truy cập chỉ được kích hoạt từ mốc cho phép. Sau đó áp dụng chính sách role nền tảng, phê duyệt entitlement bổ sung và theo dõi kết quả cấp phát.

Ví dụ nhân viên vào organization A, bộ phận Kỹ thuật. Quan hệ `member_of_organization A` thiết lập phạm vi quản trị, còn `department Engineering` cùng job code và dự án xác định các quyền cụ thể. Hệ thống phải tránh cấp quyền của organization B chỉ vì tên nhóm hoặc email giống nhau.

### 11.2. Mover — đổi organization hoặc đơn vị trực thuộc

Một người chuyển từ organization A sang B có thể yêu cầu:

1. Kiểm tra có thực sự **đổi organization** hay chỉ đổi phòng ban/dự án trong cùng organization.
2. Xác định ngày hiệu lực, quan hệ HR/đối tác mới và phê duyệt.
3. Tính **quyền hiện tại** và **quyền mục tiêu** ở từng organization.
4. Thu hồi quyền gắn với A khi không còn căn cứ, gồm nhóm, vai trò ứng dụng, ACL, chia sẻ trực tiếp và quyền API nếu có.
5. Gán membership B và cấp quyền B theo chính sách; quyền nhạy cảm cần duyệt riêng khi áp dụng.
6. Đối soát account IdP, ứng dụng, tenant và token/phiên theo yêu cầu rủi ro.

Nếu cần bàn giao trong thời gian ngắn, quan hệ A còn hiệu lực phải được ghi thành **ngoại lệ có phạm vi, phê duyệt và ngày hết hạn**, không để lại membership vô thời hạn vì tiện công việc.

### 11.3. Leaver — kết thúc quan hệ tổ chức

Khi hợp đồng hoặc quyền bảo trợ chấm dứt, IAM phải chấm dứt **quan hệ organization thuộc căn cứ đó** và thu hồi các entitlement phát sinh. Nếu không còn quan hệ làm việc hợp lệ khác, quy trình Leaver có thể vô hiệu hóa identity/account theo chính sách; nếu còn quan hệ B, phải bảo toàn quyền thực sự hợp lệ của B và thu hồi phần thuộc A.

Chỉ xóa một trường `organizationId` trong profile hoặc xóa khỏi một nhóm IdP chưa chứng minh được rằng ứng dụng đích không còn quyền cũ. Cần đối soát các tài khoản cục bộ, ACL trực tiếp, nhóm kế thừa, phiên và token theo khả năng từng hệ thống.

| Tình huống | Xử lý hợp lý |
| --- | --- |
| Nhân viên đổi department trong cùng organization | Rà soát role/quyền theo department; không nhất thiết đổi organization |
| Nhân viên chuyển pháp nhân A sang B | Cập nhật quan hệ có nguồn HR, xử lý quyền A/B và trạng thái account phù hợp |
| Nhà thầu hết hạn sponsorship ở A | Thu hồi membership và quyền A theo hạn, đánh giá quan hệ khác nếu có |
| Người dùng SaaS rời tenant A nhưng còn tenant B | Chỉ thu hồi quyền A và xác minh không rò quyền xuyên tenant |
| Người chịu trách nhiệm workload nghỉ việc | Chuyển ownership, rà soát khóa/role của workload và quyền cá nhân |

## 12. Organization cho service account và workload identity

Danh tính của máy, dịch vụ, job hoặc API client thường **không có employee record của riêng nó**. Organization assignment của chúng nên xuất phát từ danh mục dịch vụ, ứng dụng, môi trường chạy và đội vận hành có trách nhiệm.

Ví dụ `billing-sync-prod` là workload phục vụ hệ thống thanh toán của organization A:

- `organizationId` cho biết đơn vị chịu trách nhiệm và phạm vi tài nguyên.
- `ownerTeam` chỉ nhóm có thẩm quyền phê duyệt và rà soát.
- `workloadId` xác định dịch vụ/môi trường đang dùng identity.
- Entitlement chỉ cấp tới API, secret, queue, database cần thiết.
- Trạng thái của workload phải được xem xét khi dịch vụ ngừng hoạt động, đổi owner, chuyển organization hoặc môi trường.

Người owner rời tổ chức **không mặc nhiên là lý do xóa ngay workload identity đang chạy**, vì có thể gây gián đoạn hệ thống. Quy trình cần chuyển người chịu trách nhiệm, rà soát quyền và credential, đồng thời thu hồi đặc quyền cá nhân đã cấp cho người cũ.

Tài khoản dịch vụ dùng chung giữa nhiều organization là điểm có rủi ro cao. Nếu buộc phải hỗ trợ, cần tách quyền theo tenant, định danh ngữ cảnh chính xác, ghi nhật ký theo từng organization và tránh dùng một credential có quyền quản trị mọi tenant khi không cần thiết.

## 13. Các rủi ro bảo mật khi gán sai organization

| Rủi ro | Ví dụ | Biện pháp kiểm soát |
| --- | --- | --- |
| **Tự chọn organization không hợp lệ** | Người dùng sửa request từ A sang B để vào tenant B | Kiểm tra authorization phía server với nguồn có thẩm quyền |
| **Nhầm organization với tenant** | Dùng `orgId` HR làm `tenantId` SaaS | Quản trị mapping rõ, xác minh ranh giới ứng dụng |
| **Liên kết identity sai người** | Hai người trùng email được gộp vào một identity | Dùng ID đáng tin cậy và quy trình xác minh liên kết |
| **Gán nhầm nhóm quyền rộng** | Membership A tự gán `OrgAdmin` | Tách membership khỏi quyền quản trị, duyệt role đặc quyền |
| **Không hết hạn membership** | Nhà thầu hết hợp đồng vẫn trong organization A | Lưu thời hạn, xử lý JML và đối soát quyền hiệu lực |
| **Quyền cũ tồn dư khi Mover** | Người đổi sang B vẫn xem được tài liệu A | Tính chênh lệch quyền, kiểm tra ACL và phiên/token |
| **Tin vào claim cũ** | Token đăng nhập trước khi đổi organization vẫn truy cập A | Kiểm tra phiên, thời hạn token và khả năng thu hồi theo rủi ro |
| **Trộn cache giữa tenant** | Dữ liệu trả cho tenant A từ cache của B | Phân vùng cache và truy vấn theo ngữ cảnh tenant đã xác thực |
| **Organization bị đổi tên hoặc gộp** | ID ứng dụng không được cập nhật khi sáp nhập | Quản lý định danh bất biến, version và quy trình migration |

Mọi kiểm tra về organization liên quan đến **quyết định truy cập** phải được thực hiện tại điểm tin cậy (backend/API, policy engine hoặc cơ chế được ủy quyền phù hợp). Chỉ ẩn chức năng hoặc dropdown organization trên giao diện người dùng không bảo vệ được dữ liệu.

### Tránh lỗi khi triển khai ứng dụng đa tenant

Giả sử API trả báo cáo theo đường dẫn `/organizations/{orgId}/reports`. Máy chủ cần kiểm tra danh tính **còn là thành viên hợp lệ của orgId**, có role đọc báo cáo **trong đúng ngữ cảnh đó**, và từng tài nguyên được truy vấn thực sự thuộc tenant/organization được phép. Không chấp nhận `orgId` từ đường dẫn như bằng chứng duy nhất về quyền truy cập.

Trong hệ thống có organization hierarchy, quyền kế thừa từ tổ chức cha sang tổ chức con (nếu được cho phép) phải được định nghĩa tường minh. Không mặc định mọi người thuộc tổ chức mẹ đều được đọc dữ liệu bí mật của mọi công ty con.

## 14. Kiểm toán và đối soát organization assignment

Để có thể giải thích tại sao một danh tính thuộc organization, hệ thống nên ghi:

- Identity ID và organization ID, loại quan hệ, nguồn có thẩm quyền, ID bản ghi nguồn.
- Trạng thái phê duyệt, người phê duyệt hoặc sponsor khi cần, mục đích và chính sách áp dụng.
- Thời điểm bắt đầu/kết thúc hiệu lực, thời điểm ghi nhận và thực thi thực tế.
- Trạng thái trước/sau của quan hệ, event ID, source version và kết quả xử lý trùng hoặc đến muộn.
- Những nhóm, role, entitlement chịu ảnh hưởng và trạng thái provisioning/deprovisioning.
- Kết quả đối soát tại hệ thống đích, lỗi retry, ngoại lệ và người chịu trách nhiệm.

Ví dụ bản ghi kiểm toán tối giản:

~~~json
{
  "eventId": "hr-event-940",
  "identityId": "id-482",
  "action": "organization_membership_changed",
  "oldOrganizationId": "org-company-a",
  "newOrganizationId": "org-company-b",
  "effectiveAt": "2026-12-01T00:00:00+07:00",
  "policyDecision": "approved",
  "provisioningStatus": "completed",
  "accessReconciliation": "confirmed",
  "sourceVersion": 9
}
~~~

Ví dụ chỉ mô tả cấu trúc log. Khi hệ thống phát sinh nhiều target, cần trạng thái **riêng cho từng hệ thống**, thay vì một cờ `completed` che giấu lỗi ở ứng dụng khác.

Các chỉ số vận hành hữu ích:

| Chỉ số | Mục đích |
| --- | --- |
| Identity chưa có organization hợp lệ nhưng đang được cấp quyền | Phát hiện liên kết thiếu hoặc tài khoản mồ côi |
| Membership hết hạn nhưng còn hiệu lực | Tìm quyền tồn dư |
| Mismatch giữa HR/đối tác và IAM | Phát hiện nguồn dữ liệu lỗi, bản ghi chưa xử lý |
| Mismatch giữa IAM và ứng dụng đích | Phát hiện SCIM/API/ACL chưa cập nhật |
| Thời gian hoàn thành Mover/Leaver theo organization | Đo độ trễ thu hồi quyền |
| Membership đa organization không có owner hoặc sponsor | Nhận diện quan hệ thiếu trách nhiệm |
| Số sự kiện gán organization bị từ chối do thiếu căn cứ | Theo dõi chất lượng enrollment và quy tắc phê duyệt |

Không có ngưỡng KPI chung cho mọi doanh nghiệp. Tổ chức cần quy định mục tiêu và mức ưu tiên theo tính nhạy cảm của dữ liệu, mức rủi ro và SLA thu hồi.

## 15. Tình huống thực hành: nhân viên chuyển từ organization A sang B

**Bối cảnh:** Nhân viên Mai thuộc `org-retail-a`, có tài khoản IdP, nhóm `retail-a-analysts` và quyền đọc báo cáo của organization A. Từ ngày 01/12, HR chính thức điều chuyển Mai sang `org-retail-b`. Trong ứng dụng báo cáo, Mai còn một quyền xem dashboard A được gán trực tiếp.

**Quy trình cần thực hiện:**

1. Xác minh sự kiện HR có thẩm quyền, `employmentId`, organization A/B và mốc hiệu lực. Kiểm tra không nhầm với việc đổi department trong cùng organization.
2. Liên kết sự kiện với đúng IAM identity của Mai bằng ID ổn định; không dựa độc nhất vào email.
3. Xác định quan hệ A nào phải kết thúc, B nào phải bắt đầu; rà soát có hợp đồng hoặc nhiệm vụ khác còn hợp lệ ở A không.
4. Đánh giá role và entitlement mục tiêu. Quyền đọc báo cáo B phải thỏa chính sách và quy trình phê duyệt của chủ tài nguyên B.
5. Thu hồi membership, nhóm và quyền đặc thù A không còn căn cứ; xử lý cả **dashboard A được chia sẻ trực tiếp**.
6. Cập nhật thuộc tính/nhóm trong IdP, đồng bộ SCIM/API nếu ứng dụng hỗ trợ và kiểm tra quyền thực tế tại ứng dụng.
7. Ghi nguồn, phê duyệt, thời điểm thực thi, kết quả đối soát và mọi ngoại lệ bàn giao đã được duyệt.

**Kết quả đúng:** Mai dùng được tài nguyên B trong phạm vi được phê duyệt; không còn truy cập báo cáo A nếu không có căn cứ riêng. Việc chỉ thấy `organizationId = org-retail-b` trong IdP **chưa đủ** để xác nhận thành công.

### Tự kiểm tra

1. **Có thể tin organization do người dùng gửi trong request tạo tài khoản không?** Không thể mặc định tin; cần kiểm tra nguồn và quyền gán ở phía hệ thống tin cậy.
2. **Cùng domain email có chứng minh cùng organization không?** Không; domain có thể chia sẻ, thay đổi hoặc không phản ánh hợp đồng/tenant.
3. **Một người có thể thuộc hai organization không?** Có nếu mô hình và quy trình cho phép; từng quan hệ phải có căn cứ, phạm vi và thời hạn riêng.
4. **Xóa group A đã chắc chắn thu hồi quyền A?** Chưa chắc; có thể còn role ứng dụng, ACL trực tiếp, nhóm kế thừa hoặc token đang hiệu lực.
5. **Gán organization B có tự động trao quyền quản trị B không?** Không; quyền quản trị cần role, chính sách và phê duyệt riêng.

## 16. Checklist thiết kế và triển khai

| Câu hỏi | Điều cần được xác định |
| --- | --- |
| Organization nghĩa là gì trong hệ thống? | Pháp nhân, miền quản trị, org unit hay tenant; ranh giới bảo mật cụ thể |
| Mã organization được cấp và quản lý ở đâu? | ID ổn định, nguồn có thẩm quyền và ánh xạ với hệ thống đích |
| Loại identity nào được gán? | Nhân viên, đối tác, khách hàng, workload; chính sách tương ứng |
| Ai được phép gán hoặc thay đổi? | HR, sponsor, quản trị viên, workflow được ủy quyền |
| Độ tin cậy của danh tính đã đủ chưa? | Xác minh người/workload, account linking và trạng thái hợp lệ |
| Có hỗ trợ nhiều organization không? | Primary/secondary, ngữ cảnh tenant, quyền và hạn riêng |
| Quan hệ bắt đầu, kết thúc thế nào? | Source event, `validFrom`, `validUntil`, timezone, JML |
| Quyền nào phát sinh từ membership? | RBAC/ABAC, owner phê duyệt, tài nguyên và hành động cụ thể |
| Provisioning được xác nhận ra sao? | IdP, SSO claims, SCIM/API, role/ACL, đối soát tại ứng dụng |
| Khi sự kiện trễ, trùng hoặc đảo thứ tự? | Idempotency, version, đối soát snapshot và xử lý ngoại lệ |
| Khi Mover/Leaver, làm sao tránh quyền tồn dư? | So sánh quyền cũ/mới, thu hồi đa đường, kiểm tra hiệu lực token |
| Có kiểm toán đủ không? | Ai, thuộc tổ chức nào, căn cứ, thời hạn, quyết định và kết quả thực thi |

## 17. Tổng kết

**Gán organization** trong *Identity enrollment* là bước thiết lập **quan hệ có căn cứ giữa một danh tính được xác minh và tổ chức mà danh tính đó được phép tham gia**. Để gán đúng, hệ thống phải phân biệt organization với pháp nhân, phòng ban, tenant và nhóm; sử dụng định danh ổn định, nguồn có thẩm quyền, phê duyệt phù hợp và mốc hiệu lực rõ ràng.

Trong vòng đời **Joiner–Mover–Leaver**, quan hệ này cần được tạo, cập nhật hoặc chấm dứt đồng bộ với thay đổi công việc. **HRIS/nguồn đối tác** cung cấp căn cứ; **IAM** quản lý membership và chính sách; **IdP, SSO, SCIM** hỗ trợ xác thực và cung cấp tài khoản; **RBAC/ABAC và ứng dụng đích** kiểm soát quyền trên tài nguyên cụ thể. Cuối cùng, đối soát quyền hiệu lực, quản trị tài khoản dịch vụ và dấu vết kiểm toán giúp phát hiện, loại bỏ quyền truy cập tồn dư cũng như ngăn rò rỉ dữ liệu giữa các organization.
