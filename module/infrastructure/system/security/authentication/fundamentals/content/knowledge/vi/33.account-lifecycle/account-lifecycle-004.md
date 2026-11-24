# Role change — Quản lý thay đổi vai trò trong vòng đời tài khoản

> **Chương:** Account lifecycle  
> **Chủ đề:** Role change

**Role change** là quá trình thay đổi quyền và trách nhiệm được gán cho một danh tính trong một phạm vi cụ thể, chẳng hạn chuyển học viên thành giảng viên, bổ nhiệm nhân viên thành quản trị viên hoặc thu hồi quyền quản lý khi một người chuyển bộ phận. Thay đổi vai trò có thể làm tăng, giảm hoặc thay đổi loại quyền truy cập; vì vậy đây là một sự kiện bảo mật quan trọng trong vòng đời tài khoản.

Một role không phải thuộc tính trang trí của hồ sơ người dùng. Nó thường đại diện cho tập quyền có thể tác động tới dữ liệu, người dùng và chức năng trong một tenant hoặc tài nguyên. Nếu role được cấp sai, giữ lại quá lâu hoặc chỉ cập nhật ở giao diện mà không đồng bộ tới session, token và API, người dùng có thể tiếp tục truy cập vượt quá trách nhiệm hiện tại.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối role change với authentication, authorization, session, token, SSO, provisioning, deprovisioning và recovery. Trọng tâm là thay đổi vai trò có kiểm soát, nguyên tắc least privilege, phê duyệt, tách nhiệm vụ, thu hồi quyền kịp thời và xử lý nhất quán trong hệ thống nhiều dịch vụ.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt role, permission, group, membership và attribute.
2. Xác định phạm vi role theo account, tenant, project hoặc resource.
3. Thiết kế quy trình yêu cầu, phê duyệt, áp dụng, hết hạn và thu hồi role.
4. Áp dụng least privilege, separation of duties và just-in-time privilege.
5. Xử lý thay đổi vai trò trong hệ thống RBAC, ABAC và mô hình kết hợp.
6. Đồng bộ role change với session, access token, refresh token, cache và các API.
7. Ngăn privilege escalation, self-approval, stale privilege và race condition.
8. Thiết kế audit, thông báo, rollback và kiểm thử cho role change.

## 2. Role, permission và membership

Các khái niệm này thường xuất hiện cùng nhau nhưng không thể dùng thay thế nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Principal** | Danh tính thực hiện request | User, service account, workload |
| **Role** | Tên tập trách nhiệm/quyền được định nghĩa | Learner, instructor, tenant admin |
| **Permission** | Quyền thực hiện một hành động trên loại tài nguyên | course:read, grade:publish |
| **Group** | Tập hợp principal để quản lý hoặc ánh xạ | Faculty of Science |
| **Membership** | Quan hệ principal thuộc tenant/project/team | User là thành viên trường A |
| **Attribute** | Thuộc tính dùng trong quyết định policy | Department, region, employment status |
| **Assignment** | Quan hệ gán role cho principal trong một scope | User X là instructor tại tenant A |

Role thường gom nhiều permission để thuận tiện quản trị. Membership xác định người dùng thuộc phạm vi nào; role assignment xác định trách nhiệm của họ trong phạm vi đó. Một người có thể là giảng viên ở trường A, học viên ở trường B và không có quyền ở trường C.

### 2.1. Role không phải danh tính

Role không chứng minh người dùng là ai. Authentication xác minh principal; authorization đánh giá principal có được phép thực hiện hành động hay không. Việc người dùng khai “Tôi là giảng viên” trong form không đủ để cấp role instructor.

### 2.2. Role không phải permission đơn lẻ

Một role có thể bao gồm nhiều permission và có thể thay đổi theo phiên bản policy. Không nên để client gửi một role name rồi API tin trực tiếp. Server phải tải assignment từ nguồn có thẩm quyền và tính quyền hiệu lực theo policy.

## 3. Vì sao role change là sự kiện bảo mật?

Role change có thể thay đổi đáng kể khả năng truy cập:

- Học viên được nâng thành giảng viên và có quyền xem bảng điểm;
- Nhân viên được bổ nhiệm làm quản trị viên tenant;
- Quản trị viên chuyển sang bộ phận khác và cần mất quyền cũ;
- Nhà thầu kết thúc hợp đồng và bị thu hồi membership;
- Nhân viên nghỉ việc nhưng session hoặc API key vẫn còn;
- Một user bị hạ quyền nhưng access token cũ vẫn chứa role cao.

Sai sót có thể gây lộ dữ liệu, sửa đổi trái phép, gian lận, vi phạm separation of duties hoặc làm mất khả năng kiểm soát hệ thống.

### 3.1. Tăng quyền và giảm quyền

Tăng quyền thường cần phê duyệt và xác thực mạnh hơn vì mở rộng khả năng hành động. Giảm quyền hoặc thu hồi quyền thường cần được áp dụng nhanh, đặc biệt khi có thay đổi công việc, rời tổ chức hoặc sự cố bảo mật.

Tuy vậy, giảm quyền cũng cần kiểm tra tác động nghiệp vụ: có thể làm gián đoạn một quy trình đang chạy hoặc khiến người dùng mất quyền hoàn tất nhiệm vụ được giao. Giải pháp là lập kế hoạch chuyển giao và thu hồi theo thời hạn rõ, không giữ quyền cũ vô thời hạn.

## 4. Mô hình role change trong vòng đời tài khoản

Role assignment có vòng đời riêng, không nhất thiết trùng với vòng đời account.

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Gửi yêu cầu role
    Requested --> PendingApproval: Kiểm tra điều kiện
    PendingApproval --> Approved: Người có thẩm quyền duyệt
    PendingApproval --> Rejected: Từ chối
    Approved --> Scheduled: Có hiệu lực trong tương lai
    Approved --> Active: Áp dụng ngay
    Scheduled --> Active: Đến thời điểm hiệu lực
    Active --> Suspended: Tạm ngừng
    Active --> Expired: Hết thời hạn
    Active --> Revoked: Thu hồi
    Suspended --> Active: Khôi phục được duyệt
    Rejected --> [*]
    Expired --> [*]
    Revoked --> [*]
~~~

Các trạng thái trên là mô hình khái niệm. Một hệ thống có thể biểu diễn bằng assigned_at, effective_from, expires_at, revoked_at, approval_status và version thay vì enum.

### 4.1. Role assignment record

Một assignment nên xác định tối thiểu:

- Principal/user reference;
- Tenant/project/resource scope;
- Role ID và role version nếu có;
- Người yêu cầu, người phê duyệt và nguồn cấp;
- Lý do nghiệp vụ;
- Thời điểm bắt đầu và hết hạn;
- Trạng thái active/suspended/revoked;
- Thời điểm thay đổi và correlation/audit reference.

Không lưu role assignment chỉ trong profile JSON hoặc local storage của browser. Nguồn dữ liệu có thẩm quyền phải nằm phía server và có khả năng kiểm toán.

## 5. Phạm vi role và multi-tenant

Một role có thể áp dụng ở nhiều phạm vi. Nếu không gắn scope rõ, role của một tổ chức có thể vô tình ảnh hưởng đến tổ chức khác.

### 5.1. Các phạm vi thường gặp

- **Global:** quyền trên toàn bộ hệ thống; cần giới hạn rất chặt.
- **Tenant:** quyền trong một tổ chức/trường/doanh nghiệp.
- **Project/team:** quyền trong một dự án hoặc nhóm.
- **Resource-specific:** quyền trên một lớp học, hồ sơ hoặc tài nguyên cụ thể.
- **Environment:** quyền ở development, staging hoặc production.

### 5.2. Ví dụ

Một giảng viên thuộc hai trường:

~~~text
Principal: usr_417

Tenant A:
  membership: active
  role: instructor
  permissions: course:read, grade:write

Tenant B:
  membership: active
  role: learner
  permissions: course:read, assignment:submit

Tenant C:
  membership: none
  effective permissions: none
~~~

Không được lấy role instructor ở tenant A để cấp quyền grade:write trong tenant B. Mọi request cần xác định tenant/resource từ context đáng tin cậy và kiểm tra membership hiện thời.

### 5.3. Không tin tenant ID từ client

Client có thể gửi tenant ID trong URL hoặc request body, nhưng đây chỉ là yêu cầu phạm vi. Server phải xác minh principal có membership và assignment hợp lệ trong tenant đó. Không dùng tenant ID do client gửi làm căn cứ cấp role.

## 6. RBAC, ABAC và role change

### 6.1. Role-Based Access Control (RBAC)

RBAC gán permission cho role, rồi gán role cho user trong scope.

~~~mermaid
flowchart LR
    U["Principal"] --> A["Role assignment"]
    A --> R["Role"]
    R --> P["Permissions"]
    P --> D["Authorization decision"]
    D --> X["Resource/action"]
~~~

Khi role change, hệ thống thay đổi assignment. Các API sau đó tính lại permission từ role hiện hành. RBAC dễ quản trị khi trách nhiệm ổn định, nhưng role quá nhiều hoặc role chứa quyền không liên quan có thể gây role explosion và excessive privilege.

### 6.2. Attribute-Based Access Control (ABAC)

ABAC quyết định dựa trên thuộc tính của principal, resource, action và environment. Ví dụ, một giảng viên chỉ sửa điểm khi:

- Có membership active ở tenant;
- Department phù hợp;
- Được phân công vào lớp;
- Resource thuộc học kỳ hiện tại;
- Account chưa suspended.

Role change có thể cập nhật một attribute như department hoặc employment_status; quyết định authorization thay đổi theo policy mà không nhất thiết cần tạo role mới.

### 6.3. Mô hình kết hợp

Nhiều hệ thống dùng role để xác định nhóm quyền cơ bản và attribute để giới hạn phạm vi. Ví dụ role instructor có permission grade:write, nhưng ABAC chỉ cho phép sửa lớp được phân công. Role change không được bỏ qua điều kiện resource-level.

## 7. Nguyên tắc least privilege

Người dùng chỉ nên có những quyền cần thiết để thực hiện nhiệm vụ hiện tại, trong phạm vi và thời gian cần thiết.

Áp dụng least privilege khi:

- Tạo role mới;
- Nâng quyền;
- Chuyển bộ phận hoặc tenant;
- Giao quyền tạm thời;
- Cấp quyền cho support/admin;
- Tích hợp service account hoặc workload.

### 7.1. Không cấp role lớn để giải quyết một việc nhỏ

Nếu người dùng chỉ cần xem một báo cáo, cấp quyền report:read cho resource cụ thể thay vì tenant admin. Nếu cần hỗ trợ một lớp, cấp assignment cho lớp đó thay vì quyền instructor trên toàn trường.

### 7.2. Tách role theo trách nhiệm

Tránh role “super user” gom quá nhiều quyền. Có thể tách:

- User administrator;
- Billing administrator;
- Course administrator;
- Security auditor;
- Support operator.

Các role này có phạm vi và quyền khác nhau. Nếu một nhiệm vụ cần phối hợp nhiều role, áp dụng separation of duties và approval phù hợp.

## 8. Separation of duties và phê duyệt

Người yêu cầu quyền không nên tự phê duyệt quyền của chính mình khi quyền đó có tác động cao. Cần tách nhiệm vụ giữa requester, approver và operator theo rủi ro.

### 8.1. Quy trình phê duyệt

1. Người dùng hoặc manager gửi yêu cầu với role, scope, thời hạn và lý do.
2. Policy engine kiểm tra eligibility, conflict và mức quyền.
3. Người có thẩm quyền duyệt hoặc từ chối.
4. Hệ thống áp dụng assignment theo thời điểm hiệu lực.
5. Ghi audit và thông báo cho các bên.
6. Theo dõi hết hạn và review định kỳ.

### 8.2. Approver phải có thẩm quyền

Approver cần được xác định theo tenant, loại role và phạm vi. Một manager có thể duyệt quyền trong team của họ nhưng không có quyền cấp global administrator. Không chỉ dựa vào email hoặc chức danh do người yêu cầu tự khai.

### 8.3. Dual control

Với quyền rất nhạy cảm, có thể yêu cầu hai người phê duyệt độc lập. Hai approval phải gắn với cùng request/version và không được một người tạo nhiều identity để tự duyệt. Cần kiểm soát xung đột lợi ích và audit.

### 8.4. Không dùng approval thay authorization

Approval cho phép tạo assignment; mỗi request runtime vẫn cần authorization. Một role đã được duyệt không đồng nghĩa mọi hành động đều được phép trong mọi resource hoặc sau khi membership thay đổi.

## 9. Just-in-time privilege và role tạm thời

Một số công việc cần quyền cao trong thời gian ngắn. Thay vì giữ role admin thường trực, hệ thống có thể cấp quyền just-in-time (JIT).

### 9.1. Quy trình JIT

- Người dùng có account cơ bản và đủ điều kiện;
- Gửi yêu cầu role tạm thời với purpose;
- Xác thực step-up bằng phương thức phù hợp;
- Approver duyệt nếu policy yêu cầu;
- Hệ thống cấp assignment có expires_at;
- Quyền tự hết hạn và được thu hồi ở nguồn có thẩm quyền;
- Audit mọi hành động trong thời gian elevated.

### 9.2. Ràng buộc thời hạn

Không tạo role tạm thời nhưng quên đặt expires_at. Thời hạn phải được server xác định theo policy, không cho client tự gửi một giá trị tùy ý. Có thể yêu cầu người dùng xin gia hạn và được duyệt lại.

### 9.3. Step-up khi kích hoạt

Yêu cầu quyền admin tạm thời thường cần reauthentication hoặc phishing-resistant MFA. Step-up proof phải gắn với đúng role request và transaction; không dùng kết quả step-up của một hành động khác.

### 9.4. Không nhầm JIT với JEA

Just-in-time privilege cấp quyền trong một khoảng thời gian. Just Enough Administration/privilege giới hạn chính xác hành động có thể thực hiện. Hai ý tưởng có thể kết hợp: cấp quyền tạm thời và chỉ cho phép một tập action cụ thể.

## 10. Nguồn cấp role và provisioning

Role assignment có thể đến từ nhiều nguồn:

- Quản trị viên trong ứng dụng;
- Hệ thống HR hoặc student information system;
- Identity Provider qua group/role claims;
- SCIM provisioning;
- Workflow approval;
- Policy engine hoặc automation đã được kiểm soát.

### 10.1. Chọn authoritative source

Mỗi loại role cần biết nguồn nào có thẩm quyền. Ví dụ, trạng thái nhân viên do HR quản lý; membership học viên do trường quản lý; quyền admin trong sản phẩm có thể do tenant owner phê duyệt.

Không để nhiều nguồn ghi đè nhau mà không có precedence rõ. Nếu IdP gửi group claim nhưng admin ứng dụng cũng chỉnh role, cần xác định role nào được quản lý bởi IdP và role nào là local assignment.

### 10.2. Mapping group sang role

Group claim từ IdP phải qua mapping allowlist theo issuer và tenant. Không tự động coi mọi group có tên giống “admin” là quyền quản trị. Cần kiểm tra:

- Issuer đã được tin cậy;
- Subject đúng;
- Group claim thuộc đúng tenant;
- Mapping được quản trị và audit;
- Claim còn mới và được xác minh;
- Deprovisioning được truyền tới ứng dụng.

### 10.3. SCIM và đồng bộ

SCIM có thể cập nhật user/group membership, nhưng ứng dụng cần xử lý event mất, trùng hoặc đến sai thứ tự. Cần idempotency, version/ETag nếu phù hợp, reconciliation định kỳ và xử lý deactivation. Không chỉ dựa vào lần đồng bộ cuối cùng nếu quyền nhạy cảm cần thu hồi nhanh.

## 11. Role change và session/token

Đây là một trong những phần dễ bị bỏ sót. Role thay đổi ở database nhưng session hoặc token cũ vẫn có thể mang quyền trước đó.

### 11.1. Role trong JWT

Nếu access token chứa role/permission tại thời điểm phát hành, token có thể giữ claim cũ đến khi hết hạn. API chỉ kiểm tra chữ ký và exp có thể tiếp tục cho phép quyền đã bị thu hồi.

Các lựa chọn:

- Access token TTL ngắn;
- Kiểm tra authorization state/version ở API;
- Token introspection;
- Denylist/revocation cho token hoặc session cần thu hồi;
- Không nhúng quyền chi tiết vào token nếu cần cập nhật tức thời;
- Dùng claims làm gợi ý, nhưng truy vấn policy hiện tại cho action nhạy cảm.

### 11.2. Session version

Có thể lưu authorization_version hoặc role_version trên principal/tenant. Khi role change, tăng version; request kiểm tra version của session/token so với version hiện tại. Nếu lệch, yêu cầu refresh/re-auth hoặc từ chối và tạo lại context.

Cơ chế này chỉ hiệu quả nếu các API thực sự kiểm tra version và cache invalidation có SLA phù hợp. JWT tự chứa không tự biết role đã thay đổi.

### 11.3. Refresh token

Refresh token có thể tiếp tục cấp access token mới. Khi thu hồi quyền hoặc account bị deprovision, cần revoke refresh token family/session theo policy. Nếu authorization server vẫn phát token với claim cũ, role change chưa có hiệu lực đầy đủ.

### 11.4. Session hiện tại

Với giảm quyền hoặc compromise, có thể thu hồi session liên quan hoặc yêu cầu session refresh. Với thay đổi nhỏ, có thể cập nhật authorization context ở request tiếp theo. Quyết định phụ thuộc mức rủi ro và consistency requirement.

## 12. Thu hồi quyền kịp thời trong hệ thống phân tán

Một role có thể được cache ở nhiều API instance, service hoặc region. Khi thu hồi, các nơi này cần nhận trạng thái mới.

### 12.1. Các cơ chế

- Đọc assignment từ database/authorization service chung;
- Publish domain event có outbox/retry;
- Invalidate cache theo principal/tenant/role version;
- Dùng token introspection hoặc policy decision point;
- Đặt TTL cache ngắn theo yêu cầu thu hồi;
- Reconcile định kỳ để phát hiện event bị mất.

### 12.2. Định nghĩa SLA thu hồi

Không tuyên bố quyền bị thu hồi tức thời nếu cache có thể giữ dữ liệu cũ vài phút. Hãy xác định:

- Thời gian tối đa role change lan tới API;
- Hành động nào cần check online;
- Cache nào được phép stale;
- Điều gì xảy ra khi event bus hoặc authorization service lỗi;
- Cách chứng minh SLA bằng metric và test.

### 12.3. Fail closed cho hành động nhạy cảm

Nếu không thể xác minh quyền hiện tại cho hành động có tác động lớn, policy có thể từ chối hoặc yêu cầu retry thay vì dùng cache stale vô thời hạn. Hành động ít rủi ro có thể dùng degraded mode nếu tổ chức chấp nhận.

## 13. Role change khi chuyển bộ phận hoặc tenant

Chuyển vị trí công việc thường đòi hỏi cả cấp quyền mới lẫn thu hồi quyền cũ. Chỉ thêm role mới mà quên xóa role cũ là nguyên nhân phổ biến của privilege accumulation.

### 13.1. Chuyển bộ phận

1. Nguồn HR ghi nhận department/employment change.
2. Policy xác định role cũ cần thu hồi và role mới có thể cấp.
3. Manager/owner phê duyệt nếu cần.
4. Membership và assignment được cập nhật theo effective date.
5. Session/token/cache được cập nhật hoặc thu hồi.
6. Tài nguyên, dữ liệu và công việc đang sở hữu được chuyển giao.
7. Audit và notification được ghi nhận.

### 13.2. Chuyển tenant

Một user chuyển từ trường A sang trường B không có nghĩa membership A tự động chuyển thành membership B. Hai tenant có policy và nguồn authoritative riêng. Cần:

- Thu hồi assignment A theo ngày hiệu lực;
- Xác minh eligibility tại B;
- Cấp membership/role B theo approval;
- Kiểm tra dữ liệu và resource ownership;
- Không cho session A tiếp tục truy cập tài nguyên A sau khi quyền đã bị thu hồi.

### 13.3. Nghỉ việc hoặc kết thúc hợp đồng

Deprovisioning cần xử lý account, membership, role, session, refresh token, API key, certificate và linked identity. Nếu chỉ đặt user inactive nhưng token hoặc service credential còn hiệu lực, quyền vẫn có thể tồn tại.

## 14. Role conflict và toxic combination

Một số tổ hợp quyền có thể tạo xung đột, dù từng role riêng lẻ đều hợp lệ.

Ví dụ:

- Người tạo nhà cung cấp đồng thời tự phê duyệt thanh toán;
- Người quản lý điểm đồng thời sửa audit log;
- Người tạo tài khoản admin đồng thời tự phê duyệt role admin;
- Người triển khai thay đổi production đồng thời tự duyệt thay đổi đó;
- Người có quyền xuất dữ liệu đồng thời quản lý chính sách giám sát.

### 14.1. Conflict matrix

Tổ chức có thể định nghĩa các role/action không được đồng thời gán cho cùng principal trong cùng scope. Khi yêu cầu role mới, policy kiểm tra assignment hiện tại và các quyền kế thừa.

### 14.2. Mitigation

Nếu nghiệp vụ cần ngoại lệ:

- Yêu cầu phê duyệt độc lập;
- Giới hạn thời gian;
- Bắt buộc step-up;
- Tăng audit/monitoring;
- Áp dụng dual control tại điểm commit;
- Review định kỳ và tự hết hạn.

Không chỉ kiểm tra role name. Hai role khác tên có thể chứa cùng permission và tạo conflict ở mức hành động.

## 15. Role hierarchy và quyền kế thừa

Role hierarchy có thể làm role cấp cao kế thừa quyền của role cấp thấp. Điều này tiện lợi nhưng có thể khiến quyền tăng ngoài dự kiến.

~~~mermaid
flowchart BT
    L["Learner"] --> I["Instructor"]
    I --> C["Course administrator"]
    C --> T["Tenant administrator"]
~~~

Sơ đồ minh họa một mô hình kế thừa đơn giản; không phải thiết kế bắt buộc. Nếu role hierarchy tồn tại, cần:

- Xác định rõ quyền được kế thừa;
- Tránh chu kỳ hoặc quan hệ không rõ;
- Kiểm tra effective permissions, không chỉ role trực tiếp;
- Phân tích conflict ở cả quyền kế thừa;
- Audit khi role cha hoặc role con thay đổi;
- Test giảm quyền và thu hồi sau khi hierarchy thay đổi.

Không giả định role tên “admin” luôn kế thừa mọi quyền; policy phải được định nghĩa tường minh.

## 16. Role change và SSO/federation

Với SSO, role có thể được ánh xạ từ group/claim do IdP phát hành hoặc được quản lý cục bộ tại RP.

### 16.1. Claim không phải nguồn quyền vô điều kiện

RP cần xác minh issuer, audience, chữ ký, thời hạn và subject của token/assertion trước khi dùng claim. Sau đó, group/role phải được ánh xạ theo tenant và allowlist. Không tin group claim do client tự gửi.

### 16.2. Claim cũ trong session

Một ID/access token được phát hành trước role change có thể chứa group claim cũ. RP phải xác định khi nào cần kiểm tra lại membership/role tại nguồn authoritative. Đối với action nhạy cảm, không chỉ dựa vào token dài hạn.

### 16.3. SCIM deprovisioning

Nếu IdP gửi SCIM update để xóa user khỏi group, RP cần cập nhật assignment và thu hồi session/token theo SLA. Sự kiện đến trễ hoặc bị mất cần được phát hiện qua reconciliation.

## 17. Quy trình role change an toàn

~~~mermaid
sequenceDiagram
    participant U as Requester
    participant P as Policy engine
    participant A as Approver
    participant R as Role service
    participant E as Event bus
    participant API as Application APIs
    U->>P: Yêu cầu role + scope + thời hạn
    P->>P: Kiểm tra eligibility, conflict và least privilege
    P-->>A: Yêu cầu phê duyệt nếu cần
    A-->>P: Approve / reject
    P->>R: Quyết định đã được xác thực
    R->>R: Cập nhật assignment nguyên tử + version
    R->>E: Phát role-changed event qua outbox
    E->>API: Invalidate cache / refresh authorization state
    API->>API: Áp dụng role hiện tại ở request tiếp theo
    R-->>U: Kết quả và thời điểm hiệu lực
~~~

### 17.1. Kiểm tra trước khi thay đổi

- Requester có được yêu cầu role này không?
- Approver có thẩm quyền trong scope không?
- Principal có active và đủ điều kiện không?
- Role có xung đột với assignment hiện tại không?
- Phạm vi và thời hạn có hợp lệ không?
- Có cần step-up hoặc dual approval không?
- Có nguồn authoritative nào đang quản lý assignment này không?

### 17.2. Cập nhật nguyên tử

Thay đổi assignment, version và audit reference cần nhất quán. Nếu hệ thống vừa xóa role cũ vừa thêm role mới trong một quy trình chuyển bộ phận, cần transaction hoặc state transition để tránh khoảng thời gian có quyền sai.

### 17.3. Event delivery

Nếu database commit thành công nhưng event publish thất bại, cache có thể giữ role cũ. Dùng transactional outbox hoặc cơ chế retry bền vững. Consumer cần idempotent và xử lý event đến sai thứ tự bằng version.

## 18. Pseudocode kiểm tra và áp dụng role change

~~~text
request_role_change(request):
    require requester_is_authenticated(request.actor)
    require account_is_active(request.subject)
    require scope_is_valid(request.tenant, request.scope)

    policy = load_role_policy(request.role, request.scope)
    require requester_may_request(policy, request.actor)
    require subject_is_eligible(policy, request.subject)
    require no_unmitigated_role_conflict(request.subject, request.role)
    require requested_duration_within_policy(request.duration)

    if policy.requires_step_up:
        require verified_step_up_for_purpose(request.actor, ROLE_CHANGE)

    approval = evaluate_approval_requirements(policy, request)
    if approval.required:
        require independent_approval_from_authorized_approver(approval)

    begin transaction
    lock_role_assignments(request.subject, request.scope)
    recheck_current_version_and_conflicts()
    apply_assignment_transition(request)
    increment_authorization_version(request.subject, request.scope)
    write_audit_event_without_secrets(request)
    write_outbox_event("ROLE_CHANGED", request)
    commit

    notify_affected_parties()
    return effective_date_and_assignment_status()
~~~

Đây là pseudocode mô tả trách nhiệm. Triển khai cần xử lý optimistic/pessimistic locking, unique constraints, idempotency, approval expiry, event retry và rollback. Không thực hiện side effect ngoài hệ thống trước khi transaction được commit thành công.

## 19. Kiểm thử role change

Test trong môi trường staging với principal, tenant, role và resource giả lập.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Valid grant | Approver có quyền cấp role trong tenant | Assignment được tạo đúng scope |
| Unauthorized approver | Người duyệt không có thẩm quyền | Từ chối |
| Self approval | Requester tự duyệt role nhạy cảm | Từ chối theo separation-of-duties |
| Least privilege | User chỉ cần permission trên một resource | Không cấp role rộng hơn |
| Tenant isolation | Role tenant A dùng truy cập tenant B | Authorization DENY |
| Role conflict | Gán toxic combination | Từ chối hoặc yêu cầu mitigation |
| Temporary role | Role có expires_at hợp lệ | Tự hết hạn và thu hồi |
| Expired request | Approval hết hạn trước khi áp dụng | Không tạo assignment |
| Concurrent grant | Hai request cùng thay role/version | Không tạo assignment trùng hoặc vượt policy |
| Concurrent revoke | Revoke xảy ra khi request API đang chạy | Kiểm tra quyền tại điểm commit |
| JWT stale claim | Access token chứa role cũ | API chặn theo version/introspection/policy |
| Refresh token | Refresh sau khi role bị thu hồi | Token mới không mang quyền cũ |
| Cache invalidation | Event role change đến API instances | Cache cập nhật trong SLA |
| Event loss | Publish lỗi sau DB commit | Outbox/retry đảm bảo event được phát |
| Out-of-order event | Event version cũ đến sau event mới | Consumer bỏ qua version cũ |
| SCIM update | IdP xóa group membership | Assignment được cập nhật theo mapping |
| User deprovision | Nhân viên rời tổ chức | Session/token/key/membership được xử lý |
| Hierarchy change | Role cha bị đổi permission | Effective permissions được tính lại |
| Session context | User bị hạ quyền khi session còn active | Request tiếp theo không giữ quyền cũ quá SLA |
| Audit | Role tăng/giảm/revoke | Có actor, approver, reason, scope, thời điểm |
| Logging | Bật debug | Không ghi token, password hoặc secret |

### 19.1. Bất biến bảo mật

- User không thể tự cấp role hoặc tự phê duyệt role nhạy cảm;
- Mọi assignment có scope và nguồn cấp rõ;
- Quyền hiệu lực không vượt policy hiện tại;
- Role change được phản ánh tới API/session/token trong SLA;
- Giảm quyền không bị giữ lại vô thời hạn trong cache hoặc token;
- Role tạm thời có thời hạn và cơ chế thu hồi;
- Deprovisioning xử lý cả credential và session liên quan;
- Audit đủ để truy vết requester, approver, actor và thay đổi.

## 20. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Lưu role do client gửi | User tự nâng quyền | Server-side assignment và policy |
| Role không có tenant scope | Quyền rò sang tổ chức khác | Scope rõ và kiểm tra mỗi request |
| Chỉ thêm role mới, không xóa role cũ | Privilege accumulation | Chuyển role có revoke và review |
| Không có approval độc lập | Self-approval/insider abuse | Separation of duties và dual control |
| Role admin thường trực | Tăng blast radius khi account bị chiếm | JIT, expiry và least privilege |
| JWT giữ role cũ | Quyền đã thu hồi vẫn được dùng | TTL/version/introspection/revocation |
| Cache không invalidation | API tiếp tục dùng quyền cũ | Event/outbox, TTL và SLA |
| Group claim được tin trực tiếp | IdP claim sai scope cấp quyền quá mức | Issuer/tenant mapping allowlist |
| Không xử lý role conflict | Một người kiểm soát cả tạo và duyệt | Conflict matrix và mitigation |
| Chuyển tenant không thu hồi tenant cũ | Truy cập dữ liệu sau khi rời tổ chức | Deprovision membership và session |
| Event không idempotent | Duplicate hoặc đảo trạng thái | Version và idempotent consumer |
| Role hierarchy không được tính | Quyền kế thừa ngoài dự kiến | Effective permission analysis |

## 21. Checklist production

1. **Role model:** Role, permission, group, attribute và membership có định nghĩa riêng?
2. **Scope:** Assignment gắn với global/tenant/project/resource rõ ràng?
3. **Source of authority:** Ai hoặc hệ thống nào có quyền cấp từng role?
4. **Eligibility:** Điều kiện gán role được kiểm tra server-side?
5. **Least privilege:** Chỉ cấp permission và scope cần thiết?
6. **Approval:** Requester/approver/operator được phân tách theo rủi ro?
7. **Conflict:** Có conflict matrix và kiểm tra quyền kế thừa?
8. **JIT:** Quyền đặc quyền có thời hạn, purpose và step-up?
9. **Lifecycle:** Effective date, expiry, suspension, revocation và transfer có semantics rõ?
10. **Tenant:** Role của tenant này không thể được dùng ở tenant khác?
11. **Session/token:** Role change ảnh hưởng session, access token, refresh token và API theo SLA?
12. **Consistency:** Cache invalidation, event outbox, retry và reconciliation hoạt động?
13. **Federation:** Group/role claims được xác minh và mapping theo issuer/tenant?
14. **Deprovision:** Khi rời tổ chức, membership, credential, session và key được thu hồi?
15. **Audit:** Có requester, approver, reason, scope, old/new assignment, version và timestamp?
16. **Notification:** Người liên quan nhận thông báo phù hợp mà không lộ bí mật?
17. **Testing:** Đã test self-approval, privilege escalation, stale token, race, event loss và cross-tenant?

## 22. Bài tập tình huống

Một giảng viên được chuyển từ trường A sang trường B. Hệ thống chỉ thêm role instructor ở trường B nhưng giữ assignment cũ ở trường A. Access token JWT chứa danh sách role và còn hạn 12 giờ. API chỉ kiểm tra chữ ký và exp. Người dùng có thể gửi role trong request body để cập nhật hồ sơ. Manager có thể tự yêu cầu và tự duyệt quyền tenant admin.

**Yêu cầu:**

1. Xác định ít nhất **tám rủi ro** trong chuyển tenant, privilege accumulation, token staleness và approval.
2. Thiết kế quy trình chuyển role/tenant với effective date, revoke và approval.
3. Đề xuất cách làm cho role change có hiệu lực tới API trước khi JWT cũ hết hạn.
4. Xác định cách kiểm tra role claim và membership từ IdP/SCIM.
5. Thiết kế separation of duties cho tenant admin và phương án JIT privilege.
6. Viết test cho cross-tenant access, stale JWT, concurrent role change và event delivery failure.

**Gợi ý đối chiếu:** assignment phải có tenant scope; chuyển tenant cần revoke role cũ; API cần authorization version/introspection hoặc kiểm tra policy hiện tại; không tin role từ body; approver độc lập; role admin có JIT/expiry và audit.

## 23. Ghi nhớ

- **Role change** là thay đổi quyền theo vòng đời tài khoản; cần scope, nguồn cấp, thời hạn và audit rõ ràng.
- Role, permission, group, membership và attribute là các khái niệm khác nhau; authentication không tự cấp role.
- Least privilege, separation of duties và approval giúp ngăn cấp quyền quá mức hoặc tự phê duyệt.
- Role tạm thời nên dùng JIT privilege, step-up, expiry và thu hồi tự động.
- Role change phải đồng bộ với session, access token, refresh token, cache và API; JWT cũ có thể giữ quyền đã bị thu hồi.
- Chuyển bộ phận/tenant cần cả cấp quyền mới và thu hồi quyền cũ; không để privilege accumulation.
- SSO/SCIM claims phải được xác minh và ánh xạ theo issuer/tenant; deprovisioning cần xử lý session và credential.
- Mọi thay đổi quyền cần audit, thông báo phù hợp, kiểm thử race condition và SLA thu hồi.

Role change an toàn khi tổ chức có thể trả lời rõ **ai được yêu cầu, ai được phê duyệt, quyền nào được cấp trong phạm vi nào, có hiệu lực bao lâu và hệ thống thu hồi quyền cũ nhanh đến đâu**. Việc quản lý assignment nhất quán giúp danh tính luôn phản ánh trách nhiệm hiện tại thay vì tích lũy quyền từ những vai trò đã qua.
