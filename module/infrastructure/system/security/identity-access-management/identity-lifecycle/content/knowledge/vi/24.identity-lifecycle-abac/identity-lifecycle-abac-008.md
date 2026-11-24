# Attribute freshness trong ABAC: độ mới thuộc tính và quyết định quyền truy cập

> **Chương:** ABAC  
> **Bài:** Attribute freshness  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Bối cảnh:** Quản lý vòng đời danh tính trong IAM theo **Joiner–Mover–Leaver (JML)**, từ xác minh và cấp quyền đến thay đổi vai trò, rà soát và thu hồi; kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** nhằm hạn chế quyền truy cập tồn dư.

## 1. Tại sao Attribute freshness quan trọng?

Nhân viên An thuộc phòng Kế toán tại Hà Nội và được phép đọc báo cáo tài chính của chi nhánh này. Lúc 09:00, hệ thống nhân sự xác nhận An đã **chuyển sang phòng Vận hành tại Đà Nẵng**. Tuy nhiên, lúc 09:10 API vẫn cho An xem báo cáo Hà Nội vì dịch vụ phân quyền đang sử dụng thuộc tính `department=finance`, `region=HN` được cache từ 08:30.

Tình huống này không nhất thiết là lỗi xác thực: An vẫn là nhân viên hợp lệ và phiên SSO có thể hoàn toàn đúng. Nó là lỗi **thời điểm hiệu lực và độ mới của dữ liệu dùng trong phân quyền**.

**Attribute freshness (độ mới của thuộc tính)** là mức độ mà giá trị thuộc tính được dùng để ra quyết định **phản ánh trạng thái nguồn có thẩm quyền đủ gần với thời điểm quyết định**, theo yêu cầu rủi ro và chính sách của tài nguyên. Trong ABAC, độ mới cần được đánh giá cho:

- **Subject attributes:** trạng thái nhân viên, department, role-related attributes, nhóm, tình trạng đối tác, trạng thái service principal.
- **Resource attributes:** owner, tenant, classification, sensitivity, trạng thái hóa đơn, ACL/label.
- **Environment/context attributes:** trạng thái thiết bị, phiên, rủi ro, vị trí/ngữ cảnh, thời gian.
- **Policy và entitlement data:** phiên bản quy tắc, grant, exception, SoD, kết quả access review.

Một giá trị có thể **đúng tại thời điểm được ghi nhận** nhưng **quá cũ tại thời điểm cấp quyền**.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích freshness khác tính hợp lệ của token, tính đúng của giá trị, nguồn gốc và mức hoàn chỉnh dữ liệu.
2. Phân biệt `effectiveAt`, `sourceChangedAt`, `observedAt`, `lastVerifiedAt`, `cachedAt` và `decisionAt`.
3. Thiết kế chính sách độ mới dựa trên **rủi ro của action/resource**, thay vì một TTL dùng cho mọi loại quyền.
4. Phát hiện stale attributes trong kiến trúc **PEP–PDP–PIP**, IdP, SSO, SCIM, caches và access tokens.
5. Tích hợp Joiner–Mover–Leaver, reconciliation và revocation để giảm thời gian giữ quyền cũ.
6. Xử lý nguồn thuộc tính bị lỗi, dữ liệu thiếu hoặc đến sai thứ tự theo nguyên tắc an toàn.
7. Đo lường, kiểm thử và kiểm toán bằng chứng về độ mới của quyết định phân quyền.

## 2. Attribute freshness nằm ở đâu trong ABAC?

**ABAC (Attribute-Based Access Control)** ra quyết định dựa trên thuộc tính của subject, resource, action và environment, kết hợp chính sách. Ví dụ:

~~~text
PERMIT khi:
    subject.employmentStatus == ACTIVE
    AND subject.department == resource.owningDepartment
    AND subject.tenantId == resource.tenantId
    AND action == "document.read"
    AND resource.classification IN subject.allowedClassifications
~~~

Quy tắc trên chưa đủ nếu `subject.department` được làm mới mỗi ngày nhưng nhân sự chuyển phòng ngay trong ngày. ABAC cần trả lời thêm:

**“Giá trị này được xác minh lúc nào, có còn đáp ứng mức độ mới cần thiết cho request này không?”**

Một biểu diễn khái niệm:

~~~text
Decision = Evaluate(
    TrustedSubjectAttributes,
    TrustedResourceAttributes,
    Action,
    TrustedEnvironmentAttributes,
    Policy,
    FreshnessRequirements
)
~~~

### 2.1. Độ mới là thuộc tính của bằng chứng, không chỉ của dữ liệu

Hai bản ghi cùng chứa `department=finance`:

- Bản ghi A được HRIS xác nhận hôm nay, sau sự kiện Mover gần nhất.
- Bản ghi B được copy vào JWT tuần trước, không có chứng cứ trạng thái mới hơn.

Hai giá trị giống nhau về **nội dung**, nhưng mức độ đáng tin tại thời điểm ra quyết định khác nhau.

Ngoài giá trị, một attribute record nên có **nguồn có thẩm quyền, thời điểm/phiên bản quan sát và provenance** đủ để kiểm chứng. Chỉ thêm trường `updatedAt` chưa bảo đảm dữ liệu đủ mới.

### 2.2. Độ mới khác tính đúng

- **Fresh but wrong:** dữ liệu vừa được đồng bộ nhưng nguồn sai hoặc người dùng được phép tự chỉnh `department`.
- **Old but still correct:** department không đổi trong một năm; giá trị cũ có thể vẫn đúng, nhưng cần bằng chứng xác nhận gần đây nếu policy đòi hỏi.
- **Fresh and verified:** nguồn có thẩm quyền mới xác nhận lại giá trị và đáp ứng hạn.
- **Unknown freshness:** không biết được dữ liệu last verified lúc nào; phải có cách xử lý theo policy.

Freshness cần đi cùng **provenance, integrity, correctness, completeness và authority**. Làm mới liên tục một nguồn không đáng tin không khiến ABAC an toàn hơn.

## 3. Các dấu thời gian quan trọng

Không nên dùng một trường `timestamp` mơ hồ cho toàn bộ lifecycle.

| Trường | Ý nghĩa | Rủi ro khi diễn giải sai |
|---|---|---|
| `effectiveAt` | Thời điểm thay đổi nghiệp vụ **phải có hiệu lực** | Nhầm thời điểm nhập liệu thành thời điểm hết quyền |
| `sourceChangedAt` | Khi nguồn có thẩm quyền ghi nhận thay đổi | Không phản ánh ngay thời điểm thay đổi phải được thực thi |
| `eventPublishedAt` | Khi event được phát sang hệ thống downstream | Không chứng minh target đã cập nhật |
| `eventReceivedAt` | Khi connector nhận event | Nhận muộn không có nghĩa event mới nhất |
| `observedAt` | Khi hệ thống đọc một giá trị từ nguồn hoặc target | Có thể chỉ là đọc từ cache khác |
| `lastVerifiedAt` | Khi một bước kiểm chứng hợp lệ xác nhận giá trị/trạng thái | Chỉ có ý nghĩa nếu biết **đã kiểm chứng với nguồn nào** |
| `cachedAt` | Khi giá trị được đưa vào cache cục bộ | Cache có thể chứa dữ liệu vốn đã cũ |
| `tokenIssuedAt` / `iat` | Khi token được phát hành theo hợp đồng | Không chứng minh mọi claim được lấy từ nguồn mới |
| `decisionAt` | Khi PDP/PEP đánh giá request | Mốc tính độ cũ của dữ liệu ở quyết định |
| `sourceVersion` | Phiên bản/sequence có thẩm quyền của trạng thái nguồn | Giúp chống sự kiện đến sai thứ tự |

### 3.1. Vì sao không dùng `updatedAt` để đo mọi trường hợp?

Giả sử một nhân viên không đổi phòng ban suốt hai năm. HRIS được truy vấn và **xác minh hôm nay rằng vẫn thuộc Kế toán**. Trường `updatedAt` của hồ sơ có thể vẫn là hai năm trước, nhưng **lastVerifiedAt** là hôm nay.

Ngược lại, cache được cập nhật lúc 09:05 từ một replica có dữ liệu 08:00; `cachedAt=09:05` không có nghĩa thuộc tính có độ mới năm phút so với source of truth.

Cần làm rõ **bằng chứng xác minh có đến từ nguồn có thẩm quyền hoặc snapshot với cam kết nhất quán đủ mạnh không**, không chỉ ghi thời điểm đọc.

### 3.2. Thời điểm hiệu lực và độ trễ triển khai

Một sự kiện Leaver được ghi vào HRIS lúc 16:50, có `effectiveAt=17:00`. Trước 17:00, chính sách có thể cho phép nhân viên làm việc bình thường; từ 17:00, quyền phải được thu hồi theo yêu cầu của tổ chức.

Nếu một connector thực thi lúc 17:08, độ trễ triển khai là một vấn đề kiểm soát. Không nên sửa `effectiveAt` thành 17:08 để báo cáo là “thu hồi đúng giờ”.

### 3.3. Đồng hồ và hệ múi giờ

Dấu thời gian nên dùng instant có timezone rõ ràng, thống nhất việc chuyển đổi UTC, kiểm soát clock skew và đồng bộ thời gian. Không được trừ hai giá trị local-time không có timezone hoặc diễn giải ngày nghỉ việc theo múi giờ server bất kỳ.

## 4. Phân loại thuộc tính theo yêu cầu freshness

Không phải tất cả attributes đều cần một ngưỡng tối đa giống nhau.

| Nhóm thuộc tính | Ví dụ | Vì sao quan trọng | Đánh giá độ mới |
|---|---|---|---|
| **Trạng thái vòng đời** | `employmentStatus`, `disabled`, `contractEnd` | Quyết định còn được truy cập hay không | Có thể cần phản ứng rất nhanh với Leaver hoặc đình chỉ |
| **Entitlement/role** | Group, project membership, `adminRole` | Cấp chức năng hoặc đặc quyền | Ngắn hơn khi quyền cao/rủi ro lớn |
| **Thuộc tính phân vùng** | Tenant, region, department | Giới hạn dữ liệu được xem | Phụ thuộc mức nhạy cảm resource và Mover |
| **Resource security state** | Classification, owner, ACL, sharing | Resource đổi người chịu trách nhiệm hoặc mức nhạy cảm | Kiểm tra đủ mới trước action quan trọng |
| **Ngữ cảnh xác thực** | `auth_time`, assurance, kết quả step-up | Độ mới của chứng minh danh tính | Chính sách về auth freshness riêng |
| **Thiết bị** | Managed, compliant, compromised | Có thể thay đổi nhanh khi thiết bị bị sự cố | Gắn khả năng cập nhật posture/risk |
| **Thông tin hiển thị** | Display name, avatar, locale | Ít liên quan tới quyết định quyền | Có thể cache lâu hơn nếu không dùng cấp quyền |
| **Workload trust** | Principal enabled, key status, environment | Chặn dịch vụ đã ngừng hoặc bị thu hồi trust | Theo rủi ro API, credential và quyền production |

**Ngưỡng freshness là lựa chọn chính sách theo rủi ro và năng lực hệ thống**, không có con số chung như “mọi attribute phải dưới 5 phút”.

### 4.1. Giá trị ổn định vẫn cần nguồn xác nhận

Tenant ID hoặc loại resource có thể hiếm khi đổi. Tuy nhiên nếu chúng được dùng để cô lập dữ liệu nhạy cảm, việc “không thấy event thay đổi” chỉ có giá trị khi pipeline sự kiện hoạt động, không mất event và có cơ chế đối soát.

### 4.2. Attribute dẫn xuất thường có nhiều nguồn

`canApprovePayment` có thể được tính từ:

- HRIS employment status.
- Group và role tại IdP/IGA.
- Approval limit từ hệ thống tài chính.
- SoD từ lịch sử giao dịch.
- Authentication context từ phiên hiện tại.

Một kết quả dẫn xuất **không thể tươi hơn nguồn thiết yếu đã cũ**, trừ khi có cơ chế kiểm chứng mới thực sự. Không lấy thời gian tính lại expression làm bằng chứng mọi đầu vào đã được làm mới.

## 5. Luồng dữ liệu qua PIP, PDP và PEP

Một hệ thống ABAC có thể có:

- **PIP (Policy Information Point):** cung cấp attributes có nguồn và metadata xác minh.
- **PDP (Policy Decision Point):** đánh giá policy với attributes và freshness requirement.
- **PEP (Policy Enforcement Point):** chặn/cho request tại API hoặc service.
- **PAP (Policy Administration Point):** quản trị policy, phiên bản, người phê duyệt.

~~~mermaid
flowchart LR
    HR[HRIS / authoritative identity] --> PIPE[Event / sync pipeline]
    PIPE --> STORE[Trusted attribute store / PIP]
    IDP[IdP groups and sessions] --> STORE
    RES[Resource DB: owner, tenant, ACL] --> STORE
    API[API / PEP] --> PDP[PDP: ABAC policy]
    STORE --> PDP
    PAP[PAP: freshness + access policies] --> PDP
    PDP -->|Permit / Deny / Indeterminate| API
    API --> DATA[(Protected resource)]
~~~

### 5.1. Tin cậy nguồn trước khi tính độ mới

PIP nên cho biết:

1. **Nguồn:** HRIS, IdP, SaaS, resource store hoặc policy service nào.
2. **Authority:** nguồn đó có thẩm quyền cho attribute này không.
3. **Identity/resource key:** có liên kết đúng subject và đúng tenant không.
4. **Version/thời gian:** thời điểm xác minh, nguồn version và trạng thái pipeline.
5. **Completeness:** kết quả có đầy đủ hay chỉ một phần.
6. **Quality:** có lỗi đồng bộ, xung đột hay tài liệu chưa được phân loại không.

Một dữ liệu mới nhưng do user tự khai `isAdmin=true` không phải input hợp lệ cho PDP.

### 5.2. PEP vẫn phải enforce từng request

Ngay cả khi IdP phát token có claim `department=finance`, API vẫn cần kiểm tra quyền trên **resource cụ thể**. PEP/PDP có thể kết hợp token claims với dữ liệu entitlement được đọc đủ mới, và đảm bảo không có đường bypass qua URL khác, API batch hoặc truy cập trực tiếp backend.

## 6. TTL, Max Age và thời gian sống hiệu lực

Một mô hình đơn giản:

~~~text
attributeAge = decisionAt - lastVerifiedAt

attributeFresh =
    trustedSource
    AND attributeAge <= policy.maxAllowedAge
    AND sourceVersion/epoch chưa bị invalidate
    AND không có trạng thái xung đột quan trọng
~~~

Đây là mô hình **khái niệm**. Trong thực tế, phải xét cách chứng minh lần kiểm chứng, eventual consistency, thời điểm hiệu lực, phiên bản dữ liệu và các trường hợp nguồn không khả dụng.

### 6.1. Max age khác cache TTL

- **Cache TTL:** thời gian lưu/bỏ một entry trong cache.
- **Maximum acceptable attribute age:** độ cũ tối đa mà policy cho phép dùng để ra quyết định.
- **Token lifetime:** thời gian token được chấp nhận theo `exp` và các điều kiện khác.
- **Entitlement validity window:** thời hạn nghiệp vụ một grant có hiệu lực.

Các khoảng thời gian này **không đồng nhất**. Cache vừa được nạp từ bản ghi stale vẫn stale. Token còn hạn không đảm bảo entitlement còn hợp lệ.

### 6.2. Một policy có thể chọn nhiều ngưỡng

Ví dụ hoàn toàn minh họa:

| Action | Yêu cầu về freshness |
|---|---|
| Xem bản tin công ty | Trạng thái user đủ mới theo policy cơ sở |
| Xem hồ sơ khách hàng | Department/tenant và account status không vượt hạn dành cho dữ liệu khách hàng |
| Export toàn bộ khách hàng | Entitlement, tenant, data classification và assurance phải mới hơn/được kiểm tra thêm |
| Phê duyệt giao dịch | Role, approval limit, SoD và tài nguyên phải được đánh giá gần thời điểm hành động |
| Sửa IAM policy production | Trạng thái account, role đặc quyền, approval và step-up được kiểm tra chặt chẽ |

Ví dụ một tổ chức có thể chọn kiểm chứng quyền đặc biệt trong vài phút nhưng thông tin hiển thị trong nhiều giờ. Các số liệu phải đến từ SLA/SLO và mô hình rủi ro thực tế, không sao chép máy móc sang production.

### 6.3. Quyết định có hạn dùng

Một decision được PDP cache cũng là một đối tượng có **freshness**. Nếu cấp `PERMIT` lúc 09:00 và role bị thu hồi lúc 09:02, ứng dụng không nên tái sử dụng vô điều kiện kết quả cũ đến 10:00 cho hành động nhạy cảm.

Nếu cache authorization decisions, cần định nghĩa **cache key** chứa đúng principal, resource, action, tenant, policy version và những điều kiện ảnh hưởng đến kết quả; invalidate khi role/ACL/policy thay đổi.

## 7. Các cơ chế làm mới thuộc tính

Có nhiều cách truyền trạng thái từ nguồn tới PIP/PDP/PEP:

| Cơ chế | Điểm mạnh | Giới hạn |
|---|---|---|
| **Request-time fetch** | Có thể lấy dữ liệu mới khi ra quyết định | Tăng latency và phụ thuộc nguồn |
| **TTL cache** | Giảm số request và tải nguồn | Có cửa sổ stale theo TTL/độ trễ nguồn |
| **Event-driven invalidation** | Phản ứng nhanh với thay đổi | Event có thể mất, trễ hoặc sai thứ tự |
| **Polling/batch synchronization** | Đơn giản và dễ vận hành | Độ trễ giữa các lần chạy |
| **CDC / change stream** | Theo thay đổi dữ liệu có thứ tự theo nguồn | Cần kiểm soát offset, lag, replay |
| **SCIM provisioning** | Đồng bộ User/Group đến ứng dụng hỗ trợ | Không mặc định quản lý mọi role, token hoặc session |
| **Token refresh** | Cấp claims mới theo hợp đồng issuer | Không chứng minh nguồn claims đã mới |
| **Periodic reconciliation** | Phát hiện drift/mất event/account mồ côi | Có độ trễ, cần inventory và owner |

Chiến lược thường là **kết hợp**: event để phản ứng nhanh, request-time verification cho quyền đặc biệt, cache có TTL để đạt hiệu năng, reconciliation để phát hiện sai lệch.

### 7.1. Event-driven không có nghĩa nhất quán tức thời

Ví dụ:

~~~text
09:00 HRIS chốt Mover
09:00:02 Event được publish
09:00:04 Consumer nhận event
09:00:05 IAM lưu giá trị mới
09:00:08 Cache PDP bị invalidated
09:00:15 SaaS SCIM cập nhật group
09:00:20 API tại SaaS đã dùng policy mới
~~~

Các mốc minh họa cho một pipeline; không phải cam kết của SCIM hay IdP. Ở 09:06, nội bộ đã đổi group nhưng SaaS có thể vẫn dùng role cũ. Cần đo **thời điểm quyền hiệu lực tại đích**, không chỉ lúc nhận event.

### 7.2. Cache refresh theo yêu cầu

Một số API có thể:

1. Nhận request.
2. Kiểm tra cache age và source version.
3. Nếu dữ liệu quá cũ, yêu cầu PIP refresh từ nguồn đáng tin.
4. Chỉ quyết định sau khi có bằng chứng đủ mới hoặc xử lý stale theo policy.
5. Ghi log lý do/phiên bản quyết định.

Cần giới hạn tần suất refresh, tránh cache stampede và timeout dây chuyền khi lượng request lớn.

## 8. JWT, SSO và vấn đề claims cũ

Một IdP có thể phát access token dạng JWT chứa:

~~~json
{
  "iss": "https://idp.corp.example",
  "sub": "employee-1042",
  "aud": "crm-api",
  "iat": 1795400100,
  "exp": 1795403700,
  "department": "finance",
  "region": "HN",
  "roles": ["crm.support"]
}
~~~

Claims chỉ là **ví dụ**, không mặc định có mặt trong tất cả access token. Token cần được Resource Server xác minh signature, issuer, audience, thời hạn và type theo hợp đồng.

### 8.1. Chữ ký hợp lệ nhưng entitlement đã đổi

Khi user Mover, token cũ vẫn có thể chứa `region=HN` đến khi hết hạn. API chỉ tin token mà không kiểm tra trạng thái mới có thể giữ quyền ngoài chính sách.

Không nên nhầm:

- **JWT signature validity:** thông tin do issuer phát hành, chưa bị sửa trái phép.
- **Token validity:** token còn hợp lệ theo điều kiện của issuer/RS.
- **Attribute freshness:** các claim có còn phản ánh trạng thái phù hợp tại thời điểm request?
- **Authorization correctness:** user có quyền trên resource/action cụ thể không?

Bốn điều này khác nhau.

### 8.2. `iat` không chứng minh claim mới

Nếu AS vừa phát token lúc 09:30 nhưng `department` được lấy từ directory cache cũ lúc 08:00, `iat=09:30` không chứng minh department mới. Cần biết **dòng dữ liệu lấy thuộc tính** và hạn làm mới ở nguồn.

### 8.3. `auth_time` không phải freshness của HR attributes

Trong OIDC, `auth_time` là thông tin thời điểm xác thực người dùng theo giao thức. Nó có thể giúp chính sách step-up kiểm tra **độ mới của authentication**, nhưng không chứng minh `employmentStatus`, `manager`, `region` hoặc `approvalLimit` đã được xác minh gần đây.

**Yêu cầu user nhập MFA thêm một lần không tự làm mới department bị stale.** Hai bài toán cần hai cơ chế kiểm tra khác nhau.

### 8.4. Introspection và revocation có thể hỗ trợ nhưng không đủ tự động

Token introspection có thể giúp RS kiểm tra trạng thái token qua AS nếu triển khai. Nhưng `active=true` không tự chứng minh mọi entitlement hoặc resource attribute mới nhất; semantics phụ thuộc issuer và cách AS cập nhật nguồn.

JWT offline validation và introspection có trade-off về latency, độ trễ revocation, cache và tính sẵn sàng. Chọn theo **nguy cơ của tài nguyên** và hợp đồng giữa AS/RS.

## 9. SCIM, IdP và freshness trong vòng đời danh tính

Một pipeline thường gặp:

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM / IdP
    participant SCIM as SCIM Connector
    participant SaaS as SaaS target
    participant API as Resource API / PDP
    HR->>IAM: Mover/Leaver với identity ID và effectiveAt
    IAM->>IAM: Cập nhật trạng thái và policy
    IAM->>SCIM: Yêu cầu đồng bộ User/Group
    SCIM->>SaaS: PATCH User/Group theo hợp đồng
    SaaS-->>SCIM: Response kỹ thuật
    SCIM->>SaaS: GET/readback trạng thái đích
    SaaS-->>SCIM: Trạng thái User/Group quan sát được
    IAM->>API: Invalidate / cập nhật entitlement theo kiến trúc
    API->>API: Kiểm tra freshness và quyền thực tế
~~~

SCIM hỗ trợ provisioning User/Group và membership, nhưng **không tự bảo đảm hủy session, token, API key, role local, hoặc mọi quyết định authorization runtime**.

### 9.1. `meta.lastModified` trong SCIM có nghĩa gì?

`meta.lastModified` (nếu được provider hỗ trợ và cung cấp) mô tả metadata cập nhật resource ở provider theo hợp đồng. Nó không mặc nhiên là:

- Lúc HRIS xác minh employee status.
- Lúc một grant local ở SaaS bị thu hồi.
- Lúc người dùng mất session.
- Lúc API đã áp dụng policy mới.

Muốn kết luận hiệu lực, cần đối chiếu với **desired state và quyền thực tế tại target**.

### 9.2. IdP disable không chứng minh SaaS hết quyền

Khi Leaver, IdP có thể chặn xác thực mới; nhưng SaaS giữ phiên cũ hoặc local password riêng. Freshness của trạng thái `active=false` tại IdP không thay cho **readback** của account, session và entitlement tại SaaS.

## 10. Joiner: kiểm tra dữ liệu đủ mới trước khi cấp quyền

Joiner tạo danh tính và cấp account/quyền theo nguồn có thẩm quyền.

Các vấn đề freshness cần xét:

1. HRIS đã xác minh người mới, loại hợp đồng và **ngày bắt đầu hiệu lực**?
2. Dữ liệu department, manager, cost center và location có phải bản chính thức hiện tại?
3. Có event onboarding mới hơn đang chờ áp dụng?
4. IdP/group dynamic đã dựa trên dữ liệu đúng phiên bản?
5. SCIM target đã nhận account và membership chưa?
6. Account được chuẩn bị trước ngày bắt đầu có bị cho truy cập **trước effectiveAt**?
7. Quyền nhạy cảm có approval/owner và thời hạn rõ ràng?
8. Readback target cho thấy đúng role/resource scope?

### 10.1. Ví dụ cấp quyền quá sớm

HRIS dự kiến An bắt đầu 01/12, nhưng connector tạo và kích hoạt account từ 23/11. Nếu PDP chỉ kiểm tra `employmentStatus=PRE_HIRE` hoặc dữ liệu thiếu ngày hiệu lực mà vẫn cho phép, An có thể truy cập trước thời điểm được phép.

Chính sách có thể yêu cầu `now >= employmentStartAt` với timezone/nguồn phù hợp, cộng điều kiện approval và account status, không chỉ tin “account đã tồn tại”.

### 10.2. Ghi nhận nguồn cho mỗi quyết định cấp quyền

Một grant Joiner có thể được gắn với `sourceVersion`, `policyVersion`, thời điểm kiểm chứng và người phê duyệt. Khi HRIS thay đổi thông tin trước ngày vào làm, workflow có căn cứ để tính lại desired state.

## 11. Mover: thuộc tính cũ là nguồn quyền truy cập tồn dư

Mover gồm đổi role, phòng ban, project, chi nhánh, manager hoặc trách nhiệm đặc quyền. Đây là tình huống kinh điển của ABAC stale attributes.

Ví dụ:

| Thuộc tính | Trước Mover | Sau Mover | Nguy cơ nếu stale |
|---|---|---|---|
| Employment status | ACTIVE | ACTIVE | Không phát hiện chỉ qua trạng thái active |
| Department | Finance | Operations | Vẫn đọc tài liệu Finance |
| Region | HN | DN | Truy cập dữ liệu chi nhánh cũ |
| Approver entitlement | Có | Không | Vẫn duyệt thanh toán |
| Project membership | Project A | Project B | Giữ quyền repo/ticket A |
| Assurance requirement | Phương thức cơ sở | Cần chống phishing cho vai trò mới | Quyền mới dùng authentication chưa đạt |

### 11.1. Thu hồi trước hoặc đồng thời với cấp mới

Khi Mover có quyền nhạy cảm, chiến lược nên tránh kéo dài quyền cũ trong lúc chờ hệ thống mới:

1. Tính trạng thái quyền kỳ vọng từ dữ liệu nguồn đã được xác nhận.
2. Đặt thời điểm hiệu lực và giới hạn overlap nếu cần bàn giao.
3. Thu hồi những grants không còn hợp lệ.
4. Cấp quyền mới có approval.
5. Invalidate/refresh caches, authorization decisions hoặc tokens theo khả năng.
6. Kiểm tra direct grants, nested group, local role tại SaaS.
7. Readback **effective access** trên các resource quan trọng.

Không nên chỉ thêm group mới và cho rằng Mover thành công.

### 11.2. Claims cũ và resource owner thay đổi

Có hai phía thay đổi:

- **Subject changed:** An đổi phòng ban.
- **Resource changed:** tài liệu đổi owner/classification hoặc dự án chuyển tenant.

Nếu PDP chỉ làm mới subject attributes, nó vẫn có thể cho phép dựa trên **resource attributes cũ**. Cả hai phía phải được xem xét theo policy.

### 11.3. Cửa sổ bàn giao

Nếu tổ chức cho An giữ quyền cả hai phòng trong một tuần để bàn giao, đây là **ngoại lệ có chủ ý** cần owner, approval, resource scope, `validUntil` và cơ chế tự thu hồi. Không gọi đó là dữ liệu “đủ mới” để che đậy một quyền tồn dư không được duyệt.

## 12. Leaver: độ trễ freshness có thể giữ đường truy cập

Một nhân viên nghỉ việc lúc 17:00. Nếu PIP chỉ làm mới `employmentStatus` sau 60 phút, API có thể thấy user `ACTIVE` trong khoảng này.

Leaver cần phân biệt:

- **Thời điểm quyền phải hết:** `effectiveAt`.
- **Thời điểm nguồn ghi nhận:** `sourceChangedAt`.
- **Thời điểm các hệ thống nhận event:** `receivedAt`.
- **Thời điểm policy và target thật sự chặn quyền:** `effectiveRevocationAt`.
- **Thời điểm đã kiểm chứng:** `verifiedAt`.

Không lấy `receivedAt` hoặc thời điểm HTTP 200 thay cho bằng chứng quyền đã biến mất.

### 12.1. Các lớp cần phối hợp

1. HRIS/nguồn có thẩm quyền xác nhận Leaver và ngày hiệu lực.
2. IdP chặn xác thực mới theo thời điểm.
3. IAM/SCIM cập nhật User/Group và entitlements tại ứng dụng đích.
4. API/PDP kiểm tra trạng thái identity/role đủ mới, đặc biệt với quyền cao.
5. Session, access/refresh tokens, local login và API keys được xử lý theo cơ chế từng hệ thống.
6. Reconciliation kiểm tra quyền tồn dư và sự kiện chưa cập nhật.
7. Audit lưu kết quả từng target: `VERIFIED`, `PARTIAL`, `ESCALATED`.

### 12.2. Thời hạn token không bảo đảm Leaver SLA

Một access token JWT còn `exp` hợp lệ có thể vẫn được API chấp nhận sau khi user Leaver, nếu API không có kiểm tra trạng thái hoặc revocation phù hợp. Nếu tổ chức cần chặn sớm hơn thời gian token hết hạn, phải có kiến trúc để đạt yêu cầu đó; không mặc định rằng IdP disable sẽ thu hồi tức thì mọi token.

### 12.3. Lỗi lớn: sự kiện cũ bật lại quyền

Một event Mover cũ đến sau Leaver có thể cập nhật `active=true` hoặc role cũ. Connector phải kiểm tra **lifecycle version, effectiveAt và trạng thái nguồn hiện hành**, không sử dụng thứ tự nhận message làm thứ tự đúng tuyệt đối.

## 13. Thiết kế chính sách freshness an toàn

Một policy có thể diễn đạt các yêu cầu:

- Subject account phải active theo nguồn phù hợp.
- Department/region được xác minh không vượt ngưỡng cho phép.
- Resource tenant/classification được đọc ở phiên bản hợp lệ.
- Quyền đặc quyền phải chưa hết hạn và được duyệt.
- Authentication assurance/độ mới phiên đạt điều kiện riêng khi action nhạy cảm.

Ví dụ **cấu hình minh họa, không phải schema của một sản phẩm**:

~~~yaml
policyId: finance-document-access
policyVersion: "2026-11-v2"
action: document.read
requiredAttributes:
  subject.employmentStatus:
    source: hr-authoritative
    maxAgeSeconds: 120
  subject.department:
    source: hr-authoritative
    maxAgeSeconds: 600
  resource.tenantId:
    source: resource-database
    requireCurrentVersion: true
  resource.classification:
    source: classification-service
    maxAgeSeconds: 300
onUnknownFreshness: DENY
onMissingRequiredAttribute: DENY
onConflictingVersions: DENY_AND_ESCALATE
~~~

Các giá trị 120/600/300 **chỉ để minh họa việc có thể dùng ngưỡng khác nhau**, không phải hướng dẫn SLA cho production.

### 13.1. Bản chất của fail-safe

Khi một attribute cần thiết để cấp quyền **thiếu, không có nguồn đáng tin, quá cũ hoặc xung đột**, PDP nên phản ánh trạng thái chưa thể đưa ra quyết định tin cậy. PEP đối với tài nguyên được bảo vệ không nên tự coi trường hợp đó là `PERMIT`.

Điều này không đòi mọi tình huống đều trả HTTP 403: lỗi dịch vụ có thể cần mã lỗi thích hợp cho sự cố hệ thống. Quan trọng là **không trả dữ liệu hoặc thực hiện hành động khi căn cứ cho phép chưa đủ**.

### 13.2. Step-up không chữa được thuộc tính stale

Nếu department của user không được xác nhận gần đây, yêu cầu MFA lần nữa **không làm department mới hơn**. Chỉ dùng step-up để giải quyết thiếu độ bảo đảm xác thực; với thiếu freshness của quyền nghiệp vụ, cần nguồn thông tin phù hợp hoặc từ chối/đợi kiểm chứng.

### 13.3. Trường hợp công khai và ngoại lệ có phê duyệt

Một tài nguyên public thật sự có thể có chính sách không yêu cầu subject attributes như dữ liệu nhạy cảm. Nhưng public phải là **policy được định nghĩa trước và được phân loại bởi nguồn có thẩm quyền**, không phải hành vi “thấy classification thiếu thì cho public”.

Ngoại lệ quyền tạm nên có phạm vi, owner, lý do, thời điểm hết và audit; không được dùng exception vô hạn để bỏ freshness.

## 14. Pseudocode cho quyết định ABAC có kiểm tra độ mới

~~~text
function authorize(request):
    principal = verifyPrincipalAndToken(request)
    if principal is NONE:
        return DENY_UNAUTHENTICATED

    resource = loadResourceByTrustedId(request.resourceId)
    if resource is NONE:
        return NOT_FOUND

    policy = loadApplicablePolicyVersion(resource, request.action)
    requirements = policy.freshnessRequirements

    subjectFacts = PIP.getFacts(principal.identityId, requirements.subject)
    resourceFacts = PIP.getFacts(resource.id, requirements.resource)
    contextFacts = getTrustedContext(request)

    for each fact in requiredFacts(subjectFacts, resourceFacts, contextFacts):
        if fact is MISSING:
            return DENY_OR_INDETERMINATE
        if not fact.sourceIsAuthoritative:
            return DENY_OR_INDETERMINATE
        if not fact.provenanceVerified:
            return DENY_OR_INDETERMINATE
        if fact.isOlderThan(requirements.maxAgeFor(fact)):
            fact = PIP.refreshFromTrustedSource(fact)

        if fact is still STALE or fact.hasVersionConflict:
            return DENY_OR_INDETERMINATE

    if subjectFacts.employmentStatus != ACTIVE:
        return DENY

    if subjectFacts.tenantId != resourceFacts.tenantId:
        return DENY

    if not evaluateABAC(policy, principal, resource, request.action,
                        subjectFacts, resourceFacts, contextFacts):
        return DENY

    return PERMIT_WITH_DECISION_METADATA
~~~

Đây là **pseudocode**, không tự giải quyết distributed transactions, cache invalidation, retries hoặc latency. Triển khai thực cần thêm bảo vệ TOCTOU, policy version và điều kiện resource state phù hợp với action.

### 14.1. Không cho phép PIP trả dữ liệu không rõ nguồn

Một attribute record minh họa:

~~~json
{
  "attribute": "department",
  "subjectRef": "employee-1042",
  "value": "operations",
  "authority": "hr-master",
  "sourceVersion": "emp-1042-v83",
  "effectiveAt": "2026-11-23T09:00:00+07:00",
  "lastVerifiedAt": "2026-11-23T09:00:12+07:00",
  "observedAt": "2026-11-23T09:00:14+07:00",
  "cacheStoredAt": "2026-11-23T09:00:15+07:00",
  "verificationStatus": "CONFIRMED"
}
~~~

Mẫu này không phải schema chuẩn ABAC. Việc dùng `lastVerifiedAt` phải gắn với **quy trình thực sự xác minh với nguồn có thẩm quyền**, không được tự đặt thành `now` mỗi khi chuyển bản ghi qua một service.

### 14.2. Ví dụ policy test

~~~text
Case 1: department vừa được xác minh, tenant đúng, role hợp lệ
    => PERMIT theo policy

Case 2: department cũ hơn maxAge, refresh thành công và không còn quyền
    => DENY

Case 3: department quá cũ, nguồn HRIS không truy cập được
    => DENY/INDETERMINATE, PEP không thực thi action được bảo vệ

Case 4: token mới nhưng nguồn group có lag vượt ngưỡng
    => Không tự coi group claim đủ mới

Case 5: resource vừa bị nâng classification lên restricted
    => Quyết định cũ không còn được tái sử dụng
~~~

## 15. Đồng bộ, phiên bản sự kiện và xử lý sai thứ tự

Trong hệ thống phân tán, **thời gian nhận message không quyết định đâu là trạng thái mới nhất**.

~~~mermaid
flowchart TD
    A[HRIS phát sự kiện version 101: Mover] --> Q[Message queue]
    B[HRIS phát sự kiện version 102: Leaver] --> Q
    Q --> C[Consumer nhận version 102 trước]
    C --> D[Cập nhật trạng thái TERMINATED]
    Q --> E[Consumer nhận version 101 muộn]
    E --> F{Event version mới hơn trạng thái đã áp dụng?}
    F -- Không --> G[Bỏ sự kiện cũ và ghi audit]
    F -- Có --> H[Áp dụng nếu qua policy]
    D --> I[PIP / PDP invalidation]
    G --> I
~~~

### 15.1. Lifecycle version và nguồn authoritative

Cần thiết kế:

- Event ID để deduplicate.
- Subject/resource ID ổn định và đúng tenant.
- Version/sequence từ nguồn có thẩm quyền hoặc logic so sánh được quy định.
- `effectiveAt` và trạng thái hiện hành.
- Quy tắc xử lý khi nhiều nguồn xung đột.
- Retry không làm bật lại quyền cũ.
- Reconciliation định kỳ để sửa drift.

Chỉ lưu `receivedAt` không đủ để xử lý mọi trường hợp replay.

### 15.2. Đồng bộ đa vùng và read-after-write

Một cập nhật có thể được ghi vào primary nhưng read replica chưa phản ánh ngay. Nếu action rủi ro cao yêu cầu trạng thái mới, PDP có thể cần **đọc từ nguồn có mức nhất quán phù hợp hoặc dùng version watermark**, thay vì lặp đi lặp lại truy vấn vào replica cũ.

Cần phân biệt độ mới của PIP cache và độ trễ của **nguồn mà PIP đang đọc**.

### 15.3. Invalidation có thể đến trước data update

Nếu event yêu cầu invalidate cache đến trước khi database/policy source cập nhật, một lần refresh quá sớm có thể nạp lại giá trị cũ. Có thể cần version checks, retry sau khi nguồn đạt expected version hoặc cơ chế đồng bộ có bảo đảm thứ tự thích hợp.

## 16. Freshness của resource attributes và lỗi TOCTOU

Một tài liệu `DOC-200` được phân loại `internal` lúc 10:00, nhưng lúc 10:01 nhóm bảo mật nâng lên `restricted`. Một request export chạy lúc 10:02 có thể bị cho phép sai nếu API dùng classification cache cũ.

Các thuộc tính resource thường thay đổi:

- Owner/access owner.
- Tenant/project/workspace.
- Classification hoặc retention flags.
- Approval workflow state.
- `locked`, `archived`, `deleted`.
- ACL/share links và parent folder.
- Hạn mức thanh toán hoặc trạng thái invoice.

### 16.1. TOCTOU: kiểm tra và thực thi khác thời điểm

Một API:

1. Đọc invoice đang `DRAFT`.
2. Kiểm tra user có quyền sửa.
3. Một worker khác chuyển invoice sang `APPROVED`.
4. API tiếp tục sửa invoice theo kết quả kiểm tra cũ.

Đó là vấn đề **time-of-check to time-of-use (TOCTOU)**. Freshness chỉ xét `lastVerifiedAt` chưa đủ; action có thể cần optimistic concurrency, transactional conditions hoặc recheck tại thời điểm ghi.

### 16.2. Java/Spring: ví dụ pattern optimistic version

~~~java
@Entity
class Invoice {
    @Id
    UUID id;

    @Version
    long version;

    String tenantId;
    String status;
}
~~~

Khi thao tác sửa, service cần kiểm tra authorization trên invoice hiện hành và bảo đảm transaction/concurrency phù hợp. Trường `@Version` có thể giúp phát hiện cập nhật cạnh tranh khi ORM quản lý đúng, nhưng **không tự thực hiện authorization**, không bảo đảm tenant isolation và không thay việc kiểm tra quyền ở API.

### 16.3. Truy vấn dữ liệu cần ràng buộc scope

~~~sql
UPDATE invoices
SET status = 'APPROVED'
WHERE id = :invoiceId
  AND tenant_id = :trustedTenantId
  AND status = 'PENDING_APPROVAL'
  AND version = :expectedVersion;
~~~

Đây chỉ là mẫu minh họa một số điều kiện dữ liệu, **không phải toàn bộ policy**: vẫn phải kiểm tra role, hạn mức, SoD, approval và các điều kiện nghiệp vụ trước/in transaction. Hãy xác nhận đúng số hàng được cập nhật.

## 17. Multi-tenant và federation: freshness phải gắn đúng namespace

Hai tenant có thể cùng có `sub=123` hoặc account nội bộ tên giống nhau. Một attribute được xác minh cho **issuer A** không tự hợp lệ cho **issuer B**.

Khi lưu cache ABAC cần gắn context như:

~~~text
Cache key (conceptual):
  trustedIssuer
  subjectId
  tenantId
  resourceId
  attributeName
  policyVersion / sourceVersion (khi cần)
~~~

Không nhất thiết dùng mọi trường ở mọi cache, nhưng phải bảo đảm **không va chạm identity, tenant, resource hoặc policy context**. Tránh một cache entry từ tenant A vô tình phục vụ authorization của tenant B.

### 17.1. Attribute của đối tác

Trong B2B federation, đối tác có thể gửi `department` hoặc `groups`. Tổ chức nhận phải xác định thuộc tính nào đáng tin để ra quyết định trên resource nội bộ.

Một claim `groups=["admin"]` được phát **vừa mới** bởi IdP đối tác vẫn không được tự map thành quyền admin nội bộ. **Freshness không thay trust scope và approval.**

### 17.2. Ranh giới tenant của resource

Một user có `role=viewer` đúng nhưng `tenantId` stale hoặc ánh xạ sai có thể truy cập dữ liệu khách hàng khác. Với resource dữ liệu nhạy cảm, nên kiểm tra tenant theo nguồn tin cậy ở cả principal và resource tại thời điểm request.

## 18. Tài khoản dịch vụ và workload attributes

ABAC không chỉ áp dụng cho nhân viên. Workload có thể dùng các thuộc tính:

- Principal/service identity ID.
- Môi trường `prod` hoặc `staging`.
- Issuer/subject/audience của workload federation.
- Trạng thái workload còn hoạt động.
- Project, namespace, owner kỹ thuật/nghiệp vụ.
- Certificate/key validity và trạng thái trust.
- API scopes, resource constraints và approval.

Ví dụ job `svc-reporting-prod` được phép đọc `report.aggregate.read` của tenant A. Nếu workload chuyển từ staging sang production nhưng PDP dùng attribute `environment=staging` cũ, có thể cấp nhầm quyền hoặc tạo đường bypass.

### 18.1. Credential validity khác workload entitlement freshness

Một certificate còn hạn hoặc token client credentials mới phát không chứng minh role/workload trust vừa được phê duyệt vẫn có hiệu lực. Cần kiểm soát credential/trust và quyền tới resource riêng.

### 18.2. Joiner–Mover–Leaver cho workload

- **Joiner:** tạo principal, owner, trust binding, scope và resource policy.
- **Mover:** đổi môi trường, API, owner, role; thu hồi scope cũ, invalidate caches phù hợp.
- **Leaver:** thu hồi credential, trust, API grants, role, service account khi workload ngừng.
- **Bàn giao nhân sự:** khi owner con người nghỉ việc mà workload còn chạy, chuyển owner và quyền quản trị, không tự xóa workload hợp lệ.

SCIM có thể hỗ trợ User/Group của một số ứng dụng nhưng **không mặc nhiên quản lý mọi service principal, certificate hoặc cloud IAM role**.

## 19. Lỗi nguồn dữ liệu và chiến lược vận hành

### 19.1. Khi HRIS/PIP không khả dụng

Nếu một action cần `employmentStatus` đủ mới nhưng nguồn không thể xác minh, hệ thống không nên cấp quyền nhạy cảm bằng một giá trị quá cũ.

Các bước vận hành:

1. Xác định thuộc tính bắt buộc và thời gian last verified.
2. Thử truy vấn nguồn tin cậy theo timeout/retry có giới hạn.
3. Nếu không thể đáp ứng, PDP trả trạng thái không đủ căn cứ hoặc deny theo policy.
4. PEP không thực thi hành động được bảo vệ.
5. Ghi alert, owner và tác động tới nghiệp vụ.
6. Khi nguồn hồi phục, làm mới và đối soát các decision/grants liên quan.

### 19.2. Không làm “last verified” giả

Không nên nạp lại entry từ cache B sang cache A rồi đặt `lastVerifiedAt=now` nếu cache B chứa dữ liệu cũ. Chỉ cập nhật bằng chứng xác minh khi đã có bước kiểm tra thực sự hợp lệ với nguồn và mức nhất quán đã định.

### 19.3. Vận hành và hiệu năng

Biện pháp thường cân nhắc:

- TTL phân tầng theo mức rủi ro.
- Event-based invalidation có khả năng retry/dedup.
- Đồng bộ định kỳ để phát hiện mất event.
- Rate limiting/circuit breaker khi nguồn quá tải.
- Single-flight refresh hoặc kỹ thuật tránh cache stampede.
- Theo dõi replica lag, queue lag, cache age và source health.
- Chính sách fallback rõ ràng khi không thể xác minh.

Hiệu năng không phải lý do bỏ mọi kiểm tra freshness cho quyền nhạy cảm. Ngược lại, yêu cầu gọi HRIS trực tiếp cho **mọi** request cũng có thể không thực tế; cần thiết kế cân bằng nhưng có bằng chứng đạt SLA.

## 20. Case study: Mover rồi Leaver trên hệ thống thanh toán

### 20.1. Bối cảnh

Nhân viên Minh là `payment.approver` ở phòng Tài chính. API thanh toán dùng ABAC:

~~~text
PERMIT payment.approve khi:
  subject.status == ACTIVE
  AND subject.approverRole == true
  AND resource.tenantId == subject.tenantId
  AND resource.amount <= subject.approvalLimit
  AND not violatesSoD(subject, resource)
  AND authContext.meetsRequiredAssurance
~~~

PIP cache role trong 30 phút; token web tồn tại lâu hơn. Minh chuyển sang phòng Vận hành và quyền approver phải chấm dứt lúc 10:00. Đến 16:00, HRIS xác nhận Minh nghỉ việc lúc 17:00.

### 20.2. Dòng thời gian minh họa

| Thời điểm | Sự kiện | Rủi ro freshness |
|---|---|---|
| 09:50 | HRIS ghi Mover, `effectiveAt=10:00` | Quyền cũ cần hết hiệu lực lúc 10:00 |
| 10:00 | IAM đổi entitlement | PIP/cache/token ở API có thể vẫn cũ |
| 10:02 | Minh gọi `payment.approve` bằng token trước Mover | JWT hợp lệ nhưng quyền approver đã hết |
| 10:04 | PDP refresh entitlement và từ chối | Quyền hiệu lực tại API mới được kiểm chứng |
| 16:50 | HRIS ghi Leaver, `effectiveAt=17:00` | Cần chuẩn bị revoke đồng bộ |
| 17:00 | IdP chặn login mới, IAM thu hồi grants | Phiên/token đã phát có thể còn |
| 17:03 | API kiểm tra account status mới và chặn | Chứng minh một phần quyền API đã bị thu hồi |
| 17:10 | Reconciliation xác nhận các target liên quan | Có căn cứ để kết luận trạng thái theo phạm vi |

Các mốc chỉ **minh họa**; không phải SLA được chuẩn hóa bởi ABAC, SCIM hay OAuth.

### 20.3. Phân tích lỗi

Lúc 10:02, nếu API chỉ kiểm tra chữ ký JWT và role từ cache 09:45, nó có thể duyệt thanh toán trái chính sách. Bản chất lỗi là **entitlement freshness không đáp ứng thời điểm Mover**, dù authentication còn hợp lệ.

Lúc 17:00, khóa IdP giúp chặn xác thực mới nhưng không chứng minh mọi phiên hoặc token cũ đã bị vô hiệu. Cần kết hợp kiểm tra trạng thái tại API và cơ chế deprovision/revocation phù hợp.

### 20.4. Thiết kế cải tiến

1. Phân loại `payment.approve` là hành động rủi ro cao.
2. Dùng nguồn entitlement có version/nguồn authoritative.
3. Khi Mover/Leaver có hiệu lực, invalidate cache/permission thích hợp.
4. Kiểm tra entitlement đủ mới cho action nhạy cảm, độc lập với `auth_time`.
5. Áp dụng SoD/limit/tenant trên resource thực trong cùng quyết định.
6. Reconciliation sau sự kiện để tìm role local, direct grant và token/session ngoài phạm vi.
7. Báo cáo chênh lệch giữa `effectiveAt` và `effectiveRevocationAt`, không che sự chậm trễ.

## 21. Monitoring, SLO và audit về freshness

Một hệ thống không thể chứng minh freshness chỉ bằng câu “đã bật cache invalidation”. Cần số liệu đo được.

| Chỉ số | Mục đích | Lưu ý |
|---|---|---|
| Attribute age tại decision | Độ cũ thực sự của input được dùng | Tính từ lần xác minh có ý nghĩa |
| Source-to-PIP lag | Thời gian thay đổi tại nguồn tới PIP | Phân biệt event publish/consume |
| PIP-to-PEP/PDP lag | Thời gian chính sách sử dụng dữ liệu mới | Xét cache và phiên bản policy |
| Revocation effectiveness lag | Từ `effectiveAt` tới lúc target chặn quyền | Quan trọng với Mover/Leaver |
| Stale-decision rate | Số quyết định dùng input quá giới hạn hoặc bị chặn vì stale | Tách policy deny khỏi lỗi hệ thống |
| Oldest event backlog | Phát hiện consumer kẹt | Cần theo dõi phân nhóm rủi ro |
| Reconciliation drift | Số trường hợp desired khác observed/effective | Không chỉ đếm lỗi API |
| Source freshness coverage | Tỷ lệ attribute có provenance/verified timestamp | Timestamp tự tạo không tính |
| Policy cache invalidation latency | Thời gian cập nhật sau grant/revoke | Quyền cao cần đánh giá riêng |
| Exceptions past due | Ngoại lệ freshness hết hạn | Có owner, TTL, approval |

### 21.1. Audit event minh họa

~~~json
{
  "eventId": "abac-freshness-2026-008",
  "principalRef": "employee-1042",
  "resourceRef": "payment-2048",
  "action": "payment.approve",
  "policyVersion": "payment-abac-v7",
  "attributeEvidence": [
    {
      "name": "approverRole",
      "authority": "iam-entitlement-store",
      "sourceVersion": "emp-1042-v83",
      "lastVerifiedAt": "2026-11-23T10:00:15+07:00",
      "freshnessStatus": "FRESH"
    },
    {
      "name": "employmentStatus",
      "authority": "hr-master",
      "lastVerifiedAt": "2026-11-23T10:00:10+07:00",
      "freshnessStatus": "FRESH"
    }
  ],
  "decision": "DENY",
  "reasonCode": "APPROVER_ENTITLEMENT_REVOKED",
  "decisionAt": "2026-11-23T10:02:00+07:00",
  "correlationId": "IAM-MOVER-441"
}
~~~

Đây là schema **giả lập**. Audit không nên lưu access token, private key, mật khẩu, OTP hoặc thông tin cá nhân dư thừa. Nếu ghi attribute values, cần giảm dữ liệu, phân quyền xem log và retention phù hợp.

### 21.2. Những sự kiện cần cảnh báo

- PIP không nhận event Leaver từ nguồn theo ngưỡng giám sát.
- User đã terminated nhưng API vẫn có request `PERMIT` được ghi nhận sau mốc cần chặn.
- Role admin tại đích khác trạng thái IAM có thẩm quyền.
- `lastVerifiedAt` liên tục được làm mới nhưng `sourceVersion` không tiến triển dù pipeline thông báo lỗi.
- Cache entries quá hạn vẫn được PDP dùng cho action quan trọng.
- Target SCIM trả success nhưng readback vẫn còn group cũ.
- Workload bị thu hồi trust nhưng API tiếp tục chấp nhận credential còn hạn.

Không có hoạt động truy cập mới **không chứng minh** quyền đã được thu hồi; chỉ là chưa quan sát thấy sử dụng.

## 22. Ma trận kiểm thử Attribute freshness

| Tình huống | Kết quả cần xác minh |
|---|---|
| Department vừa được HRIS xác nhận, đúng tenant | Có thể tiếp tục xét quyền |
| Department vượt maxAge | Refresh hoặc xử lý stale; không tự cấp quyền |
| Cache mới nhưng nguồn replica cũ | Không coi `cachedAt` là freshness thật |
| HRIS không đổi trường nào lâu ngày nhưng vừa xác minh | Có thể coi fresh theo hợp đồng kiểm chứng |
| Claim JWT mới phát nhưng group source stale | Không tự coi claims đủ mới |
| MFA vừa hoàn thành nhưng role cũ đã bị thu hồi | Không cho phép action bị thu hồi |
| IdP disable sau Leaver nhưng access token còn hạn | API nhạy cảm chặn theo SLA revocation thực tế |
| Sự kiện Mover cũ đến sau Leaver | Không tái kích hoạt user/grant |
| CDC event bị mất | Reconciliation phát hiện divergence |
| Event invalidate tới trước source update | Không nạp lại giá trị cũ và tuyên bố đã mới |
| PDP cache decision `PERMIT` rồi ACL bị xóa | Không dùng lại decision sai |
| Resource đổi classification từ internal sang restricted | Áp dụng yêu cầu mới |
| Resource đổi owner trong khi request đang xử lý | Không cho phép stale-owner bypass |
| Tenant A/B trùng subject ID | Không chia sẻ cache across issuer/tenant |
| PIP thiếu `lastVerifiedAt` | Xử lý unknown freshness an toàn |
| Nguồn HRIS/PIP timeout | Không fail-open với resource nhạy cảm |
| Access token gửi sai audience | Từ chối trước khi xét ABAC |
| Service account đổi environment | Không giữ grant sai phạm vi |
| Role local SaaS vẫn còn dù SCIM đã cập nhật | Reconciliation phát hiện quyền hiệu lực |
| Shared file link còn hạn sau Leaver | Xem như một đường quyền cần thu hồi |
| Quyền đúng và inputs đủ mới | PERMIT theo policy, audit đủ metadata |
| Quyền thiếu dù attributes đủ mới | DENY; freshness không tự cấp quyền |

### 22.1. Cách kiểm thử trạng thái trước và sau effectiveAt

Đặc biệt với JML, cần kiểm tra cả:

- Một request **ngay trước** thời điểm hiệu lực.
- Request **đúng hoặc ngay sau** thời điểm hiệu lực.
- Request dùng token/session được cấp **trước** thay đổi.
- Request sau khi event tới PIP nhưng target chưa cập nhật.
- Request khi nguồn bị outage hoặc lag.
- Request sau reconciliation và khi quyền đã được xác minh.

Không chỉ kiểm tra UI hoặc “event đã chạy”; hãy kiểm tra **hành vi thật của API** với tài khoản/tài nguyên kiểm thử được cấp phép.

## 23. Những hiểu lầm phổ biến

**“Dữ liệu có `updatedAt` gần đây là fresh.”** Chưa chắc: timestamp có thể do cache chuyển tiếp tạo, không phản ánh nguồn có thẩm quyền.

**“Thuộc tính không đổi một năm thì chắc chắn stale và sai.”** Không hẳn; giá trị có thể vẫn đúng, nhưng phải phân biệt lần **thay đổi** với lần **xác minh lại**.

**“JWT có chữ ký hợp lệ nên role còn hiệu lực.”** Không mặc định; token có thể mang quyền trước Mover/Leaver.

**“`iat` của token mới chứng minh mọi claims mới.”** Sai nếu AS lấy claims từ nguồn/caches cũ.

**“MFA mới là làm mới mọi thuộc tính.”** Không; MFA là độ mới authentication, không làm mới department/entitlement.

**“SCIM 200 OK nghĩa là mọi API đã chặn.”** Chưa chắc; target có thể bất đồng bộ, local grants hoặc session cũ.

**“Event-driven chắc chắn không có stale.”** Sai; event có thể trễ/mất/sai thứ tự và consumer có thể lỗi.

**“Tất cả thuộc tính cần TTL bằng nhau.”** Không; ngưỡng phải gắn với resource, action và rủi ro.

**“PDP lỗi thì cho phép tạm để tránh gián đoạn.”** Nguy hiểm với tài nguyên được bảo vệ; cần fail-safe theo policy.

**“Làm mới subject là đủ.”** Không nếu resource owner/classification hoặc policy version cũng có thể đã đổi.

**“Người dùng đã nghỉ thì phải xóa mọi workload họ từng quản lý.”** Không; cần xử lý owner và vòng đời workload độc lập.

## 24. Bài tập tình huống

### Tình huống A: mới cache nhưng cũ nguồn

API làm mới cache role lúc 10:05, dữ liệu được lấy từ replica chưa nhận event Mover 10:00. PDP thấy `cachedAt=10:05` và cho phép quyền cũ.

**Phân tích:** Độ mới phải gắn với dữ liệu nguồn đã được xác nhận, không chỉ thời gian ghi cache. Cần source version, replica lag hoặc cơ chế xác minh tại nguồn phù hợp trước action nhạy cảm.

### Tình huống B: department không đổi

Hồ sơ nhân viên có `sourceChangedAt` cách đây hai năm, nhưng HRIS vừa xác nhận today không thay đổi. Chính sách yêu cầu được xác minh trong 24 giờ gần nhất.

**Phân tích:** Nếu `lastVerifiedAt` là bằng chứng đáng tin theo quy trình được chấp thuận, giá trị vẫn có thể đáp ứng freshness. Không dùng `sourceChangedAt` làm bản sao của `lastVerifiedAt`.

### Tình huống C: Leaver nhưng JWT còn hạn

User đã nghỉ lúc 17:00, token JWT còn hạn đến 17:30. API chỉ kiểm tra chữ ký và `exp`.

**Phân tích:** Token có thể vẫn được chấp nhận đến 17:30; nếu SLA yêu cầu chặn sớm, thiết kế phải bổ sung trạng thái/thu hồi hoặc token lifetime phù hợp, rồi kiểm chứng hiệu lực.

### Tình huống D: Role đúng nhưng resource đổi owner

Nhân viên có role editor và được chỉnh tài liệu lúc 09:59. Lúc 10:00 tài liệu chuyển sang tenant khác. Request sửa đến 10:01 sử dụng owner/tenant cache từ trước.

**Phân tích:** Phải làm mới resource attributes và xử lý TOCTOU, không chỉ làm mới user role.

### Tình huống E: Bot chuyển môi trường

Workload chuyển staging sang production; cache vẫn chứa `environment=staging` và scope cũ.

**Phân tích:** Cập nhật principal/trust và quyền tài nguyên theo môi trường, invalidate cache, thu hồi grants cũ và kiểm tra API production; không lấy chứng chỉ còn hạn làm bằng chứng quyền còn hợp lệ.

### Tình huống F: HRIS tạm gián đoạn

PDP cần `employmentStatus` đủ mới cho `payment.approve`, nhưng nguồn HRIS đang timeout và dữ liệu cache đã vượt ngưỡng.

**Phân tích:** Không cho phép thao tác dựa trên giá trị không thể xác minh. Giữ trạng thái thiếu căn cứ, trả phản hồi an toàn, cảnh báo và xử lý nguồn; khi phục hồi cần readback và reconciliation.

## 25. Checklist thiết kế Attribute freshness trong IAM

1. **Nguồn dữ liệu:** từng attribute có source of truth và người quản trị rõ?
2. **Provenance:** giá trị có được xác nhận qua kênh tin cậy, đúng identity/resource/tenant?
3. **Timestamps:** phân biệt effective, changed, observed, verified, cached và decision times?
4. **Version:** có source sequence hoặc cơ chế chống event cũ ghi đè event mới?
5. **Derived facts:** phụ thuộc nhiều nguồn có được tính độ mới từ từng input thiết yếu?
6. **Risk tier:** max age có phù hợp resource/action và mức đặc quyền?
7. **Cache semantics:** TTL, stale age và decision cache validity có khác nhau rõ?
8. **IdP/OIDC:** không suy freshness của department từ `iat` hoặc `auth_time`?
9. **SCIM:** response kỹ thuật được phân biệt với trạng thái target đã readback?
10. **PEP/PDP/PIP:** biết nơi thu thập, đánh giá, thực thi và ghi audit?
11. **Fail-safe:** dữ liệu thiếu/stale/conflict có bị xử lý an toàn?
12. **Source health:** đo lag, backlog, replication delay và cache invalidation?
13. **Joiner:** ngày hiệu lực và quyền ban đầu được đánh giá với dữ liệu mới?
14. **Mover:** quyền cũ được thu hồi dù role mới đã cấp thành công?
15. **Leaver:** có bằng chứng đường truy cập thực tế đã bị chặn theo thời hạn yêu cầu?
16. **Token/session:** giải quyết claims cũ và quyền trong phiên đã phát?
17. **Resource attributes:** owner, tenant, classification và ACL được làm mới khi cần?
18. **TOCTOU:** thao tác mutation bảo đảm trạng thái tại lúc ghi còn hợp lệ?
19. **Multi-tenant:** cache và correlation có namespace issuer, tenant, resource chính xác?
20. **Workload:** principal, trust, credential và resource grants được quản lý theo lifecycle riêng?
21. **Reconciliation:** có kiểm tra desired/observed/effective access khi event mất hoặc connector lỗi?
22. **Exceptions:** quyền tạm có owner, approval, scope và `validUntil`?
23. **Audit:** có quyết định, nguồn, source version, verified timestamp, policy version và correlation?
24. **Metrics:** có theo dõi freshness age, revocation lag và stale decisions?
25. **Tests:** có positive/negative/boundary tests tại effectiveAt, outage, lag và token cũ?

---

**Ghi nhớ:** **Attribute freshness trong ABAC không phải chỉ là dữ liệu được ghi vào cache gần đây.** Nó là bằng chứng rằng các thuộc tính dùng để quyết định **Subject + Resource + Action + Environment** đủ mới, đúng nguồn và đúng phiên bản theo rủi ro của request. Với **Joiner–Mover–Leaver**, sự thay đổi role, department, employment status hoặc owner của resource phải được truyền và kiểm chứng ở IdP, SCIM, PIP/PDP và hệ thống đích. Kiểm soát độ mới, xử lý stale an toàn và **đối soát quyền hiệu lực** là nền tảng để hạn chế **quyền truy cập tồn dư**.
