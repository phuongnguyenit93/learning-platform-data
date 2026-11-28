# Privileged access: Kiểm soát truy cập đặc quyền

## 1. Privileged access là gì?

**Privileged access** (truy cập đặc quyền) là quyền cho phép một danh tính thực hiện các **hành động có khả năng gây tác động lớn** hơn hoạt động thông thường, chẳng hạn sửa cấu hình bảo mật, cấp quyền cho người khác, triển khai lên production, đọc dữ liệu nhạy cảm trên diện rộng, quản lý khóa và secret, sửa/xóa cơ sở dữ liệu hay hoàn tiền cho khách hàng.

Danh tính sử dụng quyền này có thể là **con người** (quản trị viên, SRE, DBA, nhân viên hỗ trợ, nhà cung cấp) hoặc **non-human identity** (service account, workload identity, robot CI/CD, automation job, API token). Một pipeline với quyền thay đổi môi trường production có thể gây hậu quả tương đương thao tác của người quản trị.

Trong chương **Kiểm soát truy cập** thuộc module **SECURITY_SECURITY_ASSURANCE**, privileged access phải được quản lý như một **security control có bằng chứng**. Tổ chức cần truy vết được: **rủi ro → yêu cầu bảo mật → cơ chế cấp và sử dụng quyền → kiểm thử/giám sát → kết luận assurance → phát hiện → khắc phục và xác minh lại**.

Ví dụ:

- Kỹ sư được đọc log hằng ngày nhưng chỉ có quyền **sửa cấu hình production** trong một phiên thay đổi đã phê duyệt.
- Nhân viên hỗ trợ có thể xem trạng thái đơn hàng nhưng muốn **hoàn tiền** phải có quyền chuyên biệt, giới hạn giao dịch và dấu vết kiểm toán.
- Một CI job có thể build mã, nhưng chỉ workload identity chuyên biệt mới có thể **deploy** tới production.
- Database operator được bảo trì chỉ mục nhưng không mặc định có quyền tải xuống dữ liệu khách hàng của mọi tenant.

> **Nguyên tắc cốt lõi:** đặc quyền phải được gắn với **đúng danh tính, đúng hành động, đúng tài nguyên, đúng điều kiện và khoảng thời gian cần thiết**. Có công cụ PAM hoặc có mật khẩu mạnh không tự chứng minh hoạt động đặc quyền đã được kiểm soát đầy đủ.

### 1.1. Phân biệt các khái niệm

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Authentication – xác thực** | Danh tính là ai, bằng chứng xác thực có hợp lệ? | Quản trị viên đăng nhập với xác thực mạnh |
| **Authorization – phân quyền** | Chủ thể có quyền thực hiện hành động này trên tài nguyên này? | Chỉ người được cấp quyền có thể xóa một tài khoản |
| **Privileged access – truy cập đặc quyền** | Quyền tác động cao được yêu cầu, cấp, dùng, theo dõi, thu hồi và hậu kiểm thế nào? | Kích hoạt quyền deploy production trong 30 phút |
| **Accountability – trách nhiệm giải trình** | Ai hoặc workload nào đã làm gì, khi nào, theo phê duyệt nào? | Audit event liên kết change ticket và grant |
| **Security assurance** | Bằng chứng nào chứng minh control hoạt động trong phạm vi đã đánh giá? | Test vượt quyền, log cấp/thu hồi, audit và retest |

**MFA chỉ hỗ trợ xác thực**, không thay thế việc phân quyền theo tài nguyên. Một token hợp lệ không làm cho mọi hành động của người giữ token trở nên được phép.

### 1.2. Khi nào một quyền là đặc quyền?

Không nên dựa vào tên tài khoản có chữ “admin” hay không. Hãy xem **hậu quả có thể gây ra**:

- Có thể cấp, sửa, thu hồi role/permission, chính sách IAM hoặc security policy.
- Có thể xóa log, tắt cảnh báo, thay cấu hình bảo mật hoặc trust relationship.
- Có thể sửa/xóa dữ liệu giao dịch, xuất hàng loạt dữ liệu nhạy cảm.
- Có thể triển khai code, thay artifact, cấu hình infrastructure, database schema hoặc secret.
- Có thể hành động thay danh tính khác, đổi hạn mức nghiệp vụ hoặc vượt kiểm soát bình thường.
- Có thể tạo một đường **leo thang gián tiếp**, như sửa pipeline có credential production.

Quyền hỗ trợ khách hàng “đăng nhập thay người dùng”, quyền xuất dữ liệu toàn bộ tenant hay quyền sửa workflow deploy có thể là đặc quyền dù không được gọi là root.

## 2. Phạm vi danh tính và hoạt động đặc quyền

| Nhóm tài sản | Danh tính hoặc hành động | Rủi ro điển hình |
| --- | --- | --- |
| **Identity/IAM** | Quản trị IdP, cấp role, đặt lại MFA, thay trust policy | Chiếm quyền, cấp quyền bền vững trái phép |
| **Máy chủ và hệ điều hành** | Root, sudo, local administrator, remote shell | Cài mã độc, đọc secret, xóa dữ liệu hoặc log |
| **Cloud** | Organization administrator, cloud root, quản lý IAM | Tác động nhiều tài nguyên và tài khoản |
| **Kubernetes** | Cluster admin, thay RBAC/Secret, tạo workload đặc biệt | Leo thang quyền, truy cập workload khác |
| **Database** | DBA, tài khoản export/backup, quyền ALTER/DROP | Sửa/xóa/trích xuất dữ liệu nhạy cảm |
| **Ứng dụng nghiệp vụ** | Refund, impersonation, thay hạn mức, sửa giá | Gian lận hoặc tác động tới khách hàng |
| **CI/CD và chuỗi cung ứng** | Publish artifact, ký release, deploy production | Đưa artifact sai hoặc độc hại vào production |
| **Security/observability** | Sửa detection rule, dừng log collection, xóa audit | Che dấu sự kiện, vô hiệu hóa phát hiện |
| **Key/secret management** | Quản trị vault/KMS, dùng khóa ký, phát token | Chiếm quyền nhiều thành phần phụ thuộc |

Một danh tính có thể mang quyền đặc biệt **trực tiếp** hoặc có **quyền dẫn đến đặc quyền khác**. Ví dụ, quyền sửa IAM trust policy không phải role admin theo tên nhưng có thể mở đường cấp quyền rộng. Vì vậy, phạm vi kiểm kê cần bao gồm **permission chain và khả năng leo thang**.

### 2.1. Con người và machine identity có control khác nhau

**Human privileged identity** thường gắn với một nhân sự và một tài khoản quản trị riêng; có thể dùng xác thực đa yếu tố, thiết bị quản trị được quản lý, phê duyệt nhiệm vụ và session recording phù hợp.

**Machine identity** là workload, service principal, pipeline, robot hoặc agent. MFA tương tác thường **không phù hợp** cho kiểu danh tính này. Các control thay thế gồm **workload identity federation, certificate, token ngắn hạn, secret vault, rotation/revocation, scoped IAM policy, điều kiện workload và giám sát**.

Không nên áp một checklist MFA tương tác lên mọi service account rồi cấp ngoại lệ không thời hạn. Phải xác định yêu cầu phù hợp với **cách danh tính được sử dụng** và rủi ro thực tế.

## 3. Những nguyên tắc thiết kế cốt lõi

### 3.1. Least privilege – quyền tối thiểu

**Least privilege** nghĩa là mỗi danh tính chỉ được cấp những permission và phạm vi tài nguyên **thực sự cần thiết**.

- Developer cần xem log của dịch vụ A không mặc định phải có quyền sửa log retention của toàn tổ chức.
- Service A cần đọc bảng orders không mặc định cần quyền sửa IAM hoặc đọc mọi schema.
- Kỹ sư cần restart pod trong namespace X không mặc định cần quyền quản trị toàn cluster.

Quyền nhỏ về mặt tên nhưng quá rộng về **resource/tenant/environment** vẫn có thể là đặc quyền quá mức. Thiết kế nên xét **action + resource + condition + time**.

### 3.2. Just-in-time (JIT) và Just-enough-access (JEA)

**JIT** cấp hoặc kích hoạt quyền mạnh **chỉ khi cần** và có giới hạn thời gian. **JEA** giới hạn **tập thao tác** để người dùng không có toàn quyền khi chỉ cần một hành động hẹp.

Ví dụ, kỹ sư đủ điều kiện vận hành production nhưng chỉ kích hoạt quyền **restart service X trong 30 phút** khi có change phù hợp. Hết phiên, quyền bị thu hồi hoặc không còn hiệu lực ở hệ thống đích.

Khái niệm **zero standing privileges** mô tả mục tiêu giảm/loại bỏ đặc quyền thường trực ở nơi khả thi. Tuy nhiên JIT không tự bảo đảm least privilege nếu grant tạm thời vẫn cho phép thao tác trên mọi hệ thống.

### 3.3. Separation of duties (SoD) – phân tách nhiệm vụ

Hành động nhạy cảm có thể đòi hỏi **người đề xuất, người phê duyệt và người thực hiện/kiểm tra** không phải cùng một cá nhân.

Ví dụ, người thay hạn mức hoàn tiền không được tự phê duyệt khoản hoàn tiền vượt ngưỡng; người viết workflow deploy không tự quyết định bỏ kiểm tra release quan trọng.

Cần kiểm tra **độc lập thật**: hai tài khoản do cùng một người nắm giữ không tạo SoD chỉ bằng việc hiển thị hai username khác nhau.

### 3.4. Defense in depth – nhiều lớp bảo vệ

Kiểm soát đặc quyền tốt có thể gồm:

1. Xác minh identity, độ tin cậy của thiết bị và điều kiện truy cập.
2. Xác thực phù hợp với rủi ro.
3. Kiểm tra eligibility và workflow approval.
4. Giới hạn action/resource/tenant/environment.
5. Kích hoạt theo thời hạn và thu hồi có hiệu lực.
6. Kiểm tra authorization tại nơi thực thi thao tác.
7. Log, giám sát và phản ứng.
8. Đánh giá quyền định kỳ, xử lý ngoại lệ và retest.

Nhiều lớp không đồng nghĩa mọi lớp độc lập. Nếu cả PAM, ứng dụng và logging đều tin vào cùng một giả định sai, một failure mode chung có thể làm tất cả thất bại.

### 3.5. Default deny và fail securely

Khi không xác định được identity, grant, approval, scope hoặc thời hạn của quyền, thao tác đặc quyền phải **bị từ chối theo chính sách**. Lỗi dịch vụ phân quyền không nên mặc định cho phép thao tác nguy hiểm chỉ để tránh gián đoạn.

Đường khẩn cấp **break-glass** được thiết kế riêng cho khả năng phục hồi, có kiểm soát và hậu kiểm, **không phải fail-open mặc định**.

## 4. Threat scenario liên quan đến privileged access

| Kịch bản | Điều kiện/điểm yếu | Hậu quả | Control quan trọng |
| --- | --- | --- | --- |
| **Chiếm phiên quản trị** | Token bị đánh cắp, phishing, xác thực yếu | Sửa quyền, đổi cấu hình, truy cập dữ liệu | Xác thực mạnh, session protection, JIT, alert |
| **Standing privilege quá rộng** | Quyền mạnh liên tục, nhân viên đổi vai trò nhưng không revoke | Tăng phơi nhiễm và blast radius | Least privilege, review, time-bound grant |
| **Privilege escalation** | Role binding/trust policy hoặc automation cho phép tự cấp quyền | Đạt đặc quyền ngoài thẩm quyền | Phân tách cấp–dùng quyền, kiểm tra permission chain |
| **Tài khoản admin dùng chung** | Nhiều người biết credential, không có attribution | Khó điều tra, khó thu hồi riêng | Vault, session attribution, identity riêng |
| **Credential sống quá lâu** | API key/SSH key/token ít xoay vòng | Duy trì truy cập sau xâm phạm | Short-lived identity, rotation và revoke |
| **Đi đường vòng bypass PAM** | SSH/API/console cho phép direct admin ngoài luồng | Mất approval và logging | Network path control, deny direct access |
| **Lạm dụng quyền hợp lệ** | Người được cấp quyền vượt phạm vi nghiệp vụ | Gian lận, sửa giao dịch | SoD, hạn mức, kiểm tra nghiệp vụ, audit |
| **Đổi/xóa audit log** | Admin có quyền tắt giám sát | Không thể điều tra đáng tin | Tách quyền và bảo vệ log |
| **Break-glass bị sử dụng sai** | Quyền khẩn cấp dùng như tài khoản thường ngày | Đường đặc quyền khó kiểm soát | Chỉ dùng khẩn cấp, alert, hậu kiểm |
| **Revoke không thực thi** | Token cache, session sống lâu | Dùng quyền sau khi hết hạn | Kiểm tra revoke/expiry tại hệ thống đích |

Threat source không chỉ là người tấn công bên ngoài: thao tác nhầm, automation lỗi hoặc người nội bộ lạm dụng quyền hợp lệ cũng là đối tượng cần đánh giá.

## 5. PAM và PIM trong chương trình kiểm soát

**PAM (Privileged Access Management)** là tập hợp chính sách, quy trình và công cụ quản lý quyền đặc biệt. **PIM (Privileged Identity Management)** thường nhấn mạnh vòng đời danh tính đặc quyền, eligibility, yêu cầu và kích hoạt role. Ranh giới tên gọi thay đổi theo sản phẩm; nên đánh giá **control thực tế**, không dựa riêng trên tên công cụ.

Một hệ thống quản lý privileged access thường có thể hỗ trợ:

- **Discovery:** tìm các danh tính, credential và đường truy cập đặc quyền.
- **Vault/credential management:** lưu secret có kiểm soát, cấp sử dụng, rotation và revoke.
- **Approval workflow:** yêu cầu lý do, quyền, tài nguyên, thời lượng và người phê duyệt.
- **Access brokering:** điều phối phiên qua gateway, bastion hoặc cơ chế phù hợp.
- **JIT elevation:** kích hoạt theo điều kiện và thời gian.
- **Monitoring:** audit event, session metadata, detection và cảnh báo.
- **Recertification:** xem xét lại quyền, ngoại lệ và trạng thái tài khoản.
- **Response:** cô lập quyền, thu hồi credential và kiểm tra sau sự cố.

### 5.1. Luồng kích hoạt quyền tạm thời

~~~mermaid
flowchart TD
    A["Người dùng đã xác thực"] --> B["Yêu cầu action, resource, lý do và thời lượng"]
    B --> C["Kiểm tra eligibility, SoD và điều kiện truy cập"]
    C --> D{"Phê duyệt hợp lệ?"}
    D -- "Không" --> X["Từ chối và ghi audit"]
    D -- "Có" --> E["Kích hoạt grant có scope và hạn"]
    E --> F["Truy cập qua đường được kiểm soát"]
    F --> G["Authorize từng hành động nhạy cảm"]
    G --> H["Ghi audit và cảnh báo bất thường"]
    H --> I["Hết hạn / kết thúc / revoke"]
    I --> J["Kiểm tra revoke và hậu kiểm"]
    J --> K["Cập nhật risk/control/evidence"]
~~~

Sơ đồ là **mô hình mục tiêu**; không phải kết quả kiểm chứng của một công cụ cụ thể. Với hành động tác động cao có thể cần kiểm tra thiết bị, xác thực lại, phê duyệt hai người hoặc áp dụng hạn mức.

### 5.2. Eligibility khác approval, activation và usage

| Giai đoạn | Ý nghĩa | Bằng chứng cần có |
| --- | --- | --- |
| **Eligible** | Có thể xin quyền theo vai trò/nhiệm vụ | Role assignment và người chịu trách nhiệm |
| **Requested** | Có yêu cầu cụ thể về action/resource/thời gian | Request ID, lý do, change/case ID |
| **Approved** | Được phê duyệt đúng chính sách/SoD | Approver, điều kiện, thời điểm |
| **Activated** | Grant thực sự có hiệu lực | Grant ID, phạm vi, start/end |
| **Used** | Hành động đặc quyền đã thực hiện | Actor, action, target, result, correlation |
| **Revoked/expired** | Quyền không còn hiệu lực theo cơ chế thực | Revoke event và kiểm tra truy cập sau revoke |
| **Reviewed** | Phiên được đánh giá và xử lý phát hiện khi cần | Review record, finding, remediation |

Một approval có thể hợp lệ nhưng hệ thống đích lại cấp **quyền rộng hơn**. Ngược lại, grant được đánh dấu expired trong giao diện vẫn có thể được sử dụng nếu token/session chưa hết hạn và hệ thống không kiểm tra revoke. Phải test từng giai đoạn.

## 6. Vòng đời privileged access

### Bước 1. Kiểm kê và nhận diện quyền quan trọng

Inventory nên bao gồm human admin, service principal, robot CI, API key, database credential, cloud/Kubernetes role và break-glass. Ghi:

- Identity ID, owner, nguồn xác thực và loại human/machine.
- Role/permissions, action, resource, tenant/environment.
- Loại credential, nơi lưu, TTL, rotation/revoke.
- Mức hậu quả nếu bị chiếm quyền và permission chain.
- Đường sử dụng, lịch review và trạng thái bất thường.
- Nghĩa vụ chính sách, standard và bằng chứng đã có.

**Không chỉ tìm tài khoản tên admin/root**; ai có quyền sửa pipeline hoặc đọc secret của admin workload cũng có thể có privileged path.

### Bước 2. Thiết lập quyền tối thiểu và baseline

Xây yêu cầu theo nhiệm vụ, không theo sự thuận tiện:

1. Tài nguyên nào thật sự cần quản lý?
2. Những action cụ thể nào được phép?
3. Có cần quyền chỉ đọc, thực thi lệnh hẹp hay full admin?
4. Có giới hạn tenant, account, namespace hoặc environment?
5. Có hạn mức hoặc phê duyệt theo giao dịch?
6. Quyền kéo dài đến khi nào và thu hồi thế nào?
7. Ai phê duyệt và ai chịu trách nhiệm rủi ro?

Ví dụ, permission **refund:execute** không tự bao gồm **refund:approve-large**, **limit:change** hoặc **audit:delete**.

### Bước 3. Cấp và kích hoạt quyền có điều kiện

Trước activation phải xác minh identity, eligibility, mục đích, action/resource/time, approval và SoD. Cần ghi cả **request scope** lẫn **actual granted scope** để phát hiện sai khác.

Thời hạn phải được thực thi bởi IAM, privileged grant service hoặc hệ thống đích. Nếu giao diện ghi grant chỉ tồn tại 30 phút nhưng API vẫn cho phép sau 30 phút, **JIT không hiệu quả**.

### Bước 4. Giám sát việc dùng quyền

Những hành động rủi ro cao nên có dấu vết đủ để xác định:

- Ai/workload nào đã thực hiện?
- Hành động trên tài nguyên nào, lúc nào?
- Grant/approval/change reference nào liên quan?
- Thành công, bị từ chối hoặc lỗi?
- Có vượt scope/thời gian hoặc điều kiện bất thường?
- Có cảnh báo và hành động phản ứng thích hợp?

Audit log **không nên chứa password, token nguyên bản, khóa bí mật hoặc dữ liệu khách hàng không cần thiết**. Session recording nếu triển khai phải quản lý quyền riêng tư, kiểm soát truy cập, retention và yêu cầu pháp lý áp dụng.

### Bước 5. Thu hồi và kết thúc phiên

Thu hồi diễn ra khi hết hạn, kết thúc công việc, chuyển vai trò, nghỉ việc, thay service owner, thu hồi approval hoặc nghi ngờ compromise. Phải kiểm tra:

- Role/grant thật sự biến mất hoặc bị đánh dấu không còn hiệu lực.
- Token/certificate/credential còn hiệu lực trong hệ thống đích hay không.
- Session đang mở có tiếp tục thực hiện thao tác sau revoke không.
- Credential bị lộ đã rotation/revoked và mọi nơi phụ thuộc được cập nhật.
- Quyền được cấp qua đường phụ, cache hoặc service-to-service có tồn tại không.

Với token tự chứa, quyền đã nằm trong token có thể tiếp tục đến **thời điểm token hết hạn**, trừ khi có cơ chế tra trạng thái hoặc thu hồi bổ sung. Điều này phải được xem là một **giả định thiết kế** khi áp dụng JIT.

### Bước 6. Review và recertification

Review định kỳ và theo sự kiện cần xác nhận **nội dung quyền còn cần thiết, phạm vi còn đúng và owner còn tồn tại**, thay vì chỉ bấm nút “approve all”.

Trigger bao gồm: đổi vị trí/đội, nhân sự nghỉ việc, hợp đồng kết thúc, workflow/CI thay đổi, nhà cung cấp mới, IAM policy sửa, secret leak, incident/audit finding và quyền không sử dụng lâu ngày.

Kết quả review cần có **phê duyệt đúng quyền, quyết định giữ/giảm/thu hồi, action owner, ngày thực hiện và bằng chứng revoke**.

## 7. Những control quan trọng đối với quyền đặc biệt

| Control | Mục tiêu | Điều phải kiểm chứng |
| --- | --- | --- |
| **Xác thực mạnh cho admin tương tác** | Giảm chiếm tài khoản người dùng | Mọi đường quản trị thuộc scope có bảo vệ phù hợp? |
| **Least privilege và scoped permissions** | Giới hạn hành động và blast radius | Role/resource/tenant/action có quá rộng? |
| **JIT / expiry** | Giảm thời gian phơi nhiễm | Quyền hết hiệu lực thực sự, kể cả token/session? |
| **JEA / command restriction** | Giới hạn thao tác | Có thể làm nhiệm vụ mà không cấp toàn quyền admin? |
| **SoD / approval** | Ngăn tự duyệt hành động rủi ro cao | Có kiểm tra người duyệt và xung đột quyền? |
| **Credential vault / short-lived identity** | Giảm rò rỉ secret | Lưu secret an toàn, audit access, rotation/revoke |
| **Managed workstation / bastion** | Kiểm soát điểm truy cập quản trị | Có đường SSH/console/API bypass không? |
| **Privileged action audit** | Phát hiện và điều tra thao tác quan trọng | Actor/action/resource/grant/time/outcome được ghi an toàn |
| **Break-glass** | Bảo đảm khôi phục quyền khi control thường lỗi | Bảo vệ, cảnh báo, diễn tập và hậu kiểm |
| **Recertification** | Loại bỏ quyền không cần thiết | Người review có dữ kiện và quyền thực sự được thu hồi? |
| **Separation of environments** | Giảm lan quyền dev → production | Credential/role môi trường có được tách? |
| **Change/release control** | Ngăn triển khai mã chưa được phép | Ai sửa CI, ai ký artifact, ai được deploy? |

Công cụ chỉ là một phần của control. Bằng chứng phải cho thấy **mục tiêu bảo mật đạt trong phạm vi**, không chỉ một tùy chọn cấu hình đã được bật.

## 8. Break-glass: quyền truy cập khẩn cấp

**Break-glass access** là cơ chế duy trì hoặc khôi phục quyền quản trị khi đường thường bị lỗi, chẳng hạn hệ thống IdP, PAM hoặc JIT không khả dụng. Đây là **đường khẩn cấp có kiểm soát**, không phải tài khoản dùng chung để tránh approval.

### 8.1. Yêu cầu của một đường break-glass

- Có tình huống sử dụng được định nghĩa và phê duyệt.
- Tài khoản/role khẩn cấp ít nhất có thể đáp ứng khả năng khôi phục.
- Credential được bảo vệ với cơ chế thích hợp, tránh cùng điểm lỗi với đường thường nếu cần.
- Có khả năng xác định người sử dụng, alert ngay hoặc theo điều kiện sự cố.
- Log/record được bảo vệ ngoài quyền của người sử dụng khi khả thi.
- Có quy trình hậu kiểm, thu hồi/rotation và xem lại residual risk.
- Có diễn tập để chứng minh phương án dùng được trong sự cố.
- Có biện pháp ngăn tài khoản khẩn cấp trở thành quyền thường trực hàng ngày.

Chính sách xác thực của tài khoản khẩn cấp có thể cần thiết kế khác đường thường để phục hồi sau một loại sự cố; sự khác biệt phải được **đánh giá rủi ro, phê duyệt và có control bù trừ**, không mặc định giảm yêu cầu an toàn.

### 8.2. Tình huống nào không phải emergency?

| Tình huống | Nguyên tắc xử lý |
| --- | --- |
| IdP/PAM bị lỗi, cần khôi phục hệ thống trọng yếu | Dùng phương án khẩn cấp được ủy quyền, bảo toàn evidence |
| Kỹ sư quên xin quyền trước giờ deploy | Không tự dùng break-glass chỉ để khỏi đợi approval |
| Incident cần ngăn tác động lan rộng | Thực hiện ứng cứu theo quyền và workflow khẩn cấp |
| Tài khoản khẩn cấp bị dùng vào ngày bình thường | Cảnh báo, điều tra, hậu kiểm |
| Diễn tập phương án khẩn cấp | Có kế hoạch, giới hạn an toàn và lưu kết quả |

## 9. Quản lý privileged access của workload và hạ tầng

### 9.1. Machine identities và CI/CD

Workload identity cần **owner, quyền tối thiểu, credential có hạn, phạm vi môi trường, giám sát và revoke**.

Một pipeline có thể tách:

- **Build identity**: chỉ lấy mã và xây artifact.
- **Signing identity**: ký artifact với điều kiện kiểm tra nguồn và phê duyệt.
- **Deploy identity**: chỉ triển khai artifact đã được phê duyệt tới môi trường mục tiêu.
- **Runtime identity**: ứng dụng chỉ truy cập các tài nguyên cần cho công việc.

Không nên nhúng credential cloud lâu dài vào mọi job CI nếu có thể dùng federation hoặc token ngắn hạn phù hợp. Người có quyền sửa workflow thực thi với deploy credential cũng cần được xem như có **đường ảnh hưởng đặc quyền**.

### 9.2. Database, cloud và Kubernetes

**Database:** tách tài khoản ứng dụng khỏi tài khoản migration, backup và quản trị; kiểm soát quyền ALTER/DROP, đọc bản sao lưu, export và sửa role. Cần audit những lệnh có thể tác động dữ liệu hàng loạt.

**Cloud:** bảo vệ quyền root/organization admin và những role có thể sửa IAM/resource policy, disable security logging hoặc thay key. Có thể sử dụng role assumption có điều kiện, MFA thích hợp cho người dùng, JIT và điều kiện môi trường theo năng lực nền tảng.

**Kubernetes:** hạn chế cluster-admin, quyền sửa RoleBinding/ClusterRoleBinding, xem Secret, tạo workload đặc quyền và quyền sử dụng service account của workload khác. Phải xem cả **quyền leo thang gián tiếp**, không chỉ role trực tiếp.

### 9.3. Shared responsibility

Một IdP/PAM tập trung có thể quản lý identity và activation, nhưng ứng dụng vẫn cần **authorization theo hành động và dữ liệu nghiệp vụ**. Tương tự, gateway xác thực token không thay thế kiểm tra quyền trên đơn hàng hoặc hóa đơn trong service.

Cần ghi rõ:

- Nền tảng chịu trách nhiệm cơ chế chung nào.
- Ứng dụng chịu trách nhiệm check hành động/tài nguyên nào.
- Đường trực tiếp hay internal job nào có thể bypass.
- Ai tạo bằng chứng và ai xác nhận end-to-end.

## 10. Ví dụ: kiểm soát quyền hoàn tiền đặc biệt trong Java/Spring Boot

Giả sử **Orders API** có chức năng refund. Đây là **privileged business action** vì có thể chuyển tiền và gây thiệt hại nếu bị dùng ngoài phạm vi.

### 10.1. Threat scenario và security claim

**Tài sản:** giao dịch hoàn tiền, tiền và dữ liệu khách hàng.

**Threat scenario:** nhân viên support có account hợp lệ gửi refund cho order ngoài vụ việc được giao; hoặc tiếp tục refund sau khi grant JIT đã hết hạn. Nếu API chỉ kiểm tra role support, một tài khoản có thể tạo giao dịch trái phép.

**Security claim:** “Chỉ danh tính có permission refund và grant đang hiệu lực đúng order mới được thực hiện refund; các điều kiện nghiệp vụ về hạn mức, SoD và phê duyệt bổ sung phải được kiểm tra theo chính sách.”

### 10.2. Sơ đồ trust boundary và luồng kiểm soát

~~~mermaid
flowchart LR
    U["Support agent"] -->|"Xác thực + request grant"| ID["Identity / PAM"]
    ID -->|"Grant tạm thời"| GR["Grant policy/store"]
    U -->|"POST /orders/id/refund"| API["Orders API - Spring Boot"]
    API -->|"Kiểm tra role, grant và scope"| GR
    API -->|"Nếu được phép"| REF["Refund/Payment Service"]
    API -->|"Audit decision"| LOG[("Protected Audit Store")]
    GR -->|"Activation / revoke"| LOG
    REF -->|"Kết quả giao dịch"| LOG
~~~

Đây là mô hình **minh họa**, không chứng minh một production system thật. Cần xác minh nơi kiểm tra identity, approval, thời hạn, grant revoke, bảo vệ audit, hạn mức giao dịch và quyền đặc biệt theo vai trò.

### 10.3. Enforcement ở tầng service

Spring Security có thể hỗ trợ **method-level authorization**. Ví dụ sau yêu cầu permission riêng và grant đúng resource:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
    // Kich hoat Spring Security method authorization.
}

@Service
public class RefundApplicationService {
    private final RefundRepository refundRepository;

    public RefundApplicationService(RefundRepository refundRepository) {
        this.refundRepository = refundRepository;
    }

    @Transactional
    @PreAuthorize(
        "hasAuthority('SCOPE_orders.refund') " +
        "and @refundGrantPolicy.canRefund(authentication, #orderId)"
    )
    public RefundReceipt refund(
            @P("orderId") UUID orderId,
            RefundCommand command) {

        // Con phai xac minh business policy: han muc, trang thai,
        // SoD, approval cap hai, idempotency va audit.
        return refundRepository.performAuthorizedRefund(orderId, command);
    }
}
~~~

Đoạn code **không phải ứng dụng chạy độc lập**; cần định nghĩa RefundRepository, RefundReceipt, RefundCommand và các quy tắc nghiệp vụ. **@P** là annotation đặt tên tham số cho method authorization. Kiểm tra tại service giảm rủi ro route bypass so với chỉ ẩn nút giao diện.

**Chú ý kỹ thuật:** @PreAuthorize yêu cầu **@EnableMethodSecurity** và lời gọi đi qua cơ chế method interception của Spring. **Self-invocation** trong cùng bean có thể không đi qua Spring AOP proxy, làm bỏ qua method interceptor. Phải test đường gọi thực tế và bảo đảm các đường nội bộ/automation chịu cùng chính sách.

Một policy evaluator minh họa:

~~~java
@Component("refundGrantPolicy")
public class RefundGrantPolicy {
    private final ActivePrivilegeGrantService grants;
    private final RefundScopeService scope;

    public RefundGrantPolicy(ActivePrivilegeGrantService grants,
                             RefundScopeService scope) {
        this.grants = grants;
        this.scope = scope;
    }

    public boolean canRefund(Authentication authentication, UUID orderId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || orderId == null) {
            return false;
        }

        String subject = authentication.getName();

        return grants.hasActiveGrant(subject, "orders.refund", orderId)
                && scope.isOrderWithinApprovedScope(subject, orderId);
    }
}
~~~

**ActivePrivilegeGrantService** và **RefundScopeService** là các interface/service giả định. Bản thực tế phải kiểm tra **approval, action, resource, thời hạn, revoke, tenant, hạn mức và các điều kiện rủi ro**. authentication.getName() chỉ đáng tin khi chuỗi xác thực đã kiểm chứng token/session, mapping principal và các claim cần thiết.

Với grant cache, phải đánh giá thời gian trễ thu hồi. Với refund có trạng thái biến đổi, cần kiểm soát **idempotency, cạnh tranh giao dịch, xác nhận nghiệp vụ** và audit ở boundary thực thi. Role hoặc JWT scope **không tự thay thế** kiểm tra grant và quy tắc nghiệp vụ.

### 10.4. Ma trận kiểm thử bắt buộc

| Test case | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- |
| User không có permission refund | Từ chối | Negative authorization test |
| User có permission nhưng không có active grant | Từ chối | Grant absence test |
| Grant cho order X, request order Y | Từ chối | Resource scope test |
| Grant đã hết hạn | Từ chối sau thời điểm hiệu lực kết thúc | Expiry test với clock có kiểm soát |
| Grant bị thu hồi khi session còn sống | Không được tiếp tục sử dụng ngoài quyền | Revoke/session test |
| User có grant đúng order và trạng thái hợp lệ | Cho phép theo quy trình | Positive test |
| Tự phê duyệt giao dịch cần hai người | Từ chối/chuyển quy trình | SoD/approval test |
| Vượt hạn mức | Từ chối hoặc cần approval bổ sung | Business limit test |
| Grant store/IdP lỗi | Không fail-open cho thao tác ngoài quyền | Failure-mode test |
| Internal job gọi service | Không bypass enforcement | Integration/architecture test |
| Hành động có audit log | Actor/action/resource/grant/outcome, không chứa secret | Audit validation |
| Đã sửa lỗi ở build mới | Retest đạt trên build/env mục tiêu | Regression + deployment evidence |

Test Spring Security Test minh họa (dùng CSRF token thử nghiệm hợp lệ để tránh việc HTTP 403 chỉ xuất hiện do CSRF, nếu CSRF đang được bật):

~~~java
@Test
void noGrantMeansRefundDenied() throws Exception {
    mockMvc.perform(
        post("/api/orders/{id}/refund", orderId)
            .with(csrf())
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.refund")))
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"reason\":\"customer-request\"}")
    )
    .andExpect(status().isForbidden());
}
~~~

**Điều kiện quan trọng:** test phải cấu hình MockMvc, fixture, principal, route, và **active grant service thực sự trả không có grant**. Một controller test mock toàn bộ RefundApplicationService **không kiểm chứng** @PreAuthorize đặt trên service. Test cần đi qua bean được bảo vệ, kết hợp các test token thật/issuer/audience và các luồng khác.

Để tránh false positive, cần bảo đảm 403 đến từ **kiểm tra privileged access**, không do CSRF, validation khác hoặc endpoint không tồn tại. Kiểm tra log/decision path và có cả positive test để chứng minh API hoạt động khi đủ quyền.

### 10.5. Liên kết security claim với bằng chứng

| Claim | Control | Evidence phù hợp |
| --- | --- | --- |
| Chỉ nhân sự đủ điều kiện được yêu cầu quyền refund | PIM eligibility / identity verification | Eligibility records, review và approval rule |
| Không ai tự phê duyệt giao dịch thuộc diện SoD | Approval workflow và business policy | Negative test, approval history |
| Quyền tạm thời hết hiệu lực đúng hạn | Time-bound grant + revoke enforcement | Test expiry/revoke, session/token result |
| Không refund ngoài order/phạm vi đã duyệt | Resource-aware authorization | Order X/Y test, code/config review |
| Không vượt hạn mức trái quy trình | Business control, threshold + dual approval | Limit/state machine test |
| Truy vết được quyết định và thao tác | Protected audit log | Actor/grant/action/result correlation |
| Không có đường bypass | Enforcement ở boundary phù hợp | Endpoint inventory, job/worker test, architecture review |

**Có annotation bảo vệ phương thức không đủ** nếu grant store, approval, phạm vi giao dịch hoặc những đường gọi khác chưa được đánh giá.

## 11. Đánh giá hiệu quả control và assurance evidence

### 11.1. Design, implementation và operating effectiveness

| Lớp | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Design effectiveness** | Các control có giảm đúng threat, kể cả escalation và revoke không? | Threat model, SoD matrix, security design, failure analysis |
| **Implementation effectiveness** | Scope, IAM policy, approval, expiry, audit đã được triển khai đúng nơi? | Code review, IAM config, IaC, test integration |
| **Operating effectiveness** | Quyền được cấp/sử dụng/thu hồi và review đúng qua kỳ vận hành? | Activation logs, revoke tests, recertification, alert response |

Một policy yêu cầu MFA hoặc một ảnh chụp bật PAM không đủ chứng minh **operating effectiveness**. Test staging của bản cũ không tự chứng minh build production mới. Bằng chứng phải tương ứng **đúng kỳ, environment, standard version và scope**.

### 11.2. Những test/kiểm tra nên tổ chức

1. **Provisioning:** tài khoản không đủ điều kiện có được cấp quyền?
2. **Approval/SoD:** người yêu cầu có tự duyệt hoặc bypass?
3. **Scope:** grant cho action/resource A dùng được với B không?
4. **Activation:** quyền có hiệu lực trước khi được phê duyệt?
5. **Expiry/revocation:** quyền/tokens/sessions tiếp tục sau hết hạn?
6. **Bypass:** console, SSH, API, CI, job nội bộ có đường ngoài PAM?
7. **Failure mode:** IdP/grant service lỗi có fail-open?
8. **Logging:** actor, action, time, resource và outcome được bảo vệ?
9. **Detection:** break-glass hoặc grant bất thường có cảnh báo và được xử lý?
10. **Recertification:** quyền không cần thiết có được thu hồi?
11. **Machine identity:** credential có còn sau khi service/owner đã ngừng?
12. **Change:** role/policy/config thay có gây drift không?

Kết quả PASS/FAIL cần gắn với **tập kịch bản và mẫu số**, không mặc định mở rộng kết luận cho mọi danh tính/hệ thống.

### 11.3. Chất lượng bằng chứng

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Relevance** | Có chứng minh đúng privileged access claim? |
| **Scope/coverage** | Có những role, identity, path, environment và case quan trọng? |
| **Freshness** | Phù hợp build, policy/standard revision và kỳ đánh giá? |
| **Integrity** | Bằng chứng có nguồn gốc và bảo vệ khỏi sửa đổi? |
| **Repeatability** | Có tái chạy/tái kiểm tra được khi cần? |
| **Independence** | Có reviewer đủ độc lập khi rủi ro cao? |
| **Protection** | Log/session recording không lộ secret và được phân quyền đúng? |

**Insufficient evidence** khác **Ineffective**. Nếu chưa kiểm tra revoke của token, chưa thể nói control thất bại; nhưng cũng **không được kết luận có thu hồi hiệu quả**.

### 11.4. Trạng thái kết luận

- **Effective in assessed scope:** có bằng chứng phù hợp chứng minh các tiêu chí trong phạm vi.
- **Partially effective:** một số phần đạt nhưng còn gap hoặc coverage chưa đầy đủ.
- **Ineffective:** có bằng chứng control thất bại ở kịch bản trọng yếu.
- **Insufficient evidence:** chưa đủ căn cứ để kết luận.
- **Exception approved:** không đáp ứng nhưng có quyết định xử lý residual risk hợp lệ, có điều kiện.
- **Not applicable:** có căn cứ chính thức yêu cầu không áp dụng.

Ngoại lệ được phê duyệt **không biến một control không đạt thành đạt**. Kết luận phải ghi cả **confidence**, phạm vi chưa kiểm tra và người chịu trách nhiệm.

## 12. Chỉ số giám sát privileged access

| Chỉ số | Giá trị quản trị | Giới hạn |
| --- | --- | --- |
| **Privileged identity inventory coverage** | Theo dõi danh tính và role đã xác định | Có thể bỏ sót quyền leo thang gián tiếp |
| **Standing privilege exposure** | Đo số lượng và phạm vi quyền thường trực | Không chỉ đếm account; xét blast radius |
| **JIT activation coverage** | Các grant được cấp đúng qua workflow JIT | Không chứng minh grant được giới hạn đủ hẹp |
| **Grant expiry/revoke verification** | Kiểm tra quyền thật sự hết hiệu lực | Log UI không thay test session |
| **Human admin MFA coverage** | Bảo vệ đường quản trị tương tác thuộc phạm vi | Machine identity cần tiêu chí khác |
| **Recertification with action** | Review dẫn đến quyết định giữ/giảm/revoke | Ký duyệt hàng loạt không chứng minh chất lượng |
| **Break-glass audit coverage** | Kiểm soát tài khoản khẩn cấp và hậu kiểm | Không có lần dùng không có nghĩa thiết kế an toàn |
| **Privileged action audit coverage** | Bảo đảm truy vết actor/action/resource/result | Tránh ghi token hay dữ liệu nhạy cảm |
| **SoD violations detected** | Phát hiện phê duyệt/xung đột sai quy tắc | Cần mẫu số và các rule áp dụng |
| **Overdue privileged findings** | Theo dõi gap quan trọng chưa khắc phục/retest | Ưu tiên theo rủi ro, không chỉ số lượng |

Ví dụ: có 40 đường truy cập quản trị tương tác đã xác định, 35 đường đã được kiểm chứng dùng phương thức xác thực đúng policy. **Coverage = 35/40 = 87,5%** cho nhóm đó, **không phải an toàn 87,5%**. Năm đường còn lại có thể có quyền rộng hơn toàn bộ những đường đã kiểm tra.

Phải xem **mức trọng yếu**, kiểu danh tính, đường bypass và residual risk bên cạnh KPI trung bình.

## 13. Mẫu control record và hồ sơ assurance

Mẫu YAML dưới đây là **dữ liệu giả định**, không phải báo cáo của một hệ thống thật:

~~~yaml
control_id: "PAM-REFUND-DEMO-007"
title: "Temporary privileged refund access"
control_owner: "Orders API Tech Lead"
risk_owner: "Orders Product Owner"
policy_ref: "POL-PRIVILEGED-ACCESS"
standard_ref:
  id: "STD-PRIVILEGED-ACTIONS"
  version: "demo-1.0"
security_objective: "Prevent unauthorized refunds"
risk_scenarios:
  - "Staff refunds orders outside approved scope"
  - "Expired grant remains usable"
scope:
  service: "orders-api"
  action: "orders.refund"
  environments:
    - "integration"
    - "production"
requirements:
  - "Trusted authenticated principal"
  - "Separate refund authority"
  - "Active grant scoped to order"
  - "Approval and SoD when required"
  - "Audit actor, grant, target and outcome"
controls:
  - "Spring method security"
  - "Resource-aware grant evaluator"
  - "Time-bound approval store"
  - "Protected audit log"
evidence_plan:
  - "Architecture and authorization review"
  - "Negative tests for no grant, expired, wrong order"
  - "Approval conflict and revoke tests"
  - "Deployment/configuration and runtime checks"
assessment:
  conclusion: "INSUFFICIENT_EVIDENCE"
  confidence: "LOW"
  assessed_build: null
  assessed_at: null
  test_run_refs: []
findings: []
next_action: "Verify enforcement and run grant tests"
exception:
  approved: false
  approver: null
~~~

Trong hồ sơ thật cần **ngày giờ, policy/standard revision, build, environment, các đường thao tác, test run, reviewer, bằng chứng audit và quyết định rủi ro**. Trạng thái **INSUFFICIENT_EVIDENCE** ở ví dụ là có chủ ý, vì chưa có kết quả kiểm tra thật.

## 14. Phân công trách nhiệm

| Vai trò | Trách nhiệm | Giới hạn |
| --- | --- | --- |
| **Policy/standard owner** | Định nghĩa yêu cầu, phạm vi, thẩm quyền và revision | Không mặc định control đã đáp ứng |
| **Identity/PAM owner** | Quản lý IAM/PAM, eligibility, grant, credential, expiry và revoke | Không thay authorization nghiệp vụ |
| **Application/control owner** | Triển khai kiểm tra quyền trên action/resource, audit và evidence | Không tự động có quyền chấp nhận residual risk |
| **SRE/platform owner** | Bảo vệ cloud, DB, Kubernetes, CI/CD, workload identity | Phối hợp app owner cho đường end-to-end |
| **Business/risk owner** | Đánh giá tác động và quyết định xử lý residual risk đúng quyền | Không thay review kỹ thuật |
| **Developer/operator** | Cài đặt, vận hành, test, sửa và retest | PR merge không tự đóng finding |
| **Assurance reviewer/auditor** | Đánh giá evidence, nêu kết luận có giới hạn và kiến nghị | Không trở thành owner sửa control |
| **Incident response team** | Thu hồi quyền, điều tra, ứng cứu và bảo toàn evidence khi có incident | Hoạt động theo quy trình và thẩm quyền |

### 14.1. Ma trận RACI minh họa

*R = người thực hiện; A = người chịu trách nhiệm cuối cùng; C = người được tham vấn; I = người được thông báo.*

| Hoạt động | Identity/PAM owner | App/control owner | Kỹ thuật/vận hành | Risk owner | Assurance/audit |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa workflow grant/expiry | **A/R** | C | C | C | C |
| Enforce quyền refund tại ứng dụng | C | **A** | R | C | C |
| Bảo vệ secret, revoke và vận hành | **A** | C | R | I | C |
| Thu thập evidence theo control | R | **A** | R | I | C |
| Đánh giá độc lập khi cần | C | C | C | I | **A/R** |
| Khắc phục finding ứng dụng | C | **A** | R | C | C |
| Chấp nhận residual risk theo quyền | C | C | C | **A/R** | I |

RACI chỉ là **ví dụ**; cần điều chỉnh theo điều lệ và cơ chế phê duyệt thực tế. Độc lập không chỉ là hai cột khác nhau nếu cùng một người nắm cả hai trách nhiệm.

## 15. Những sai lầm thường gặp

### 15.1. Chỉ quản lý account tên admin

CI bot, service principal hoặc nhân viên có quyền impersonation có thể tác động lớn. **Khắc phục:** inventory theo khả năng và permission chain.

### 15.2. Có MFA là đủ

MFA không thay least privilege, JIT, SoD hoặc authorization theo tài nguyên. **Khắc phục:** kiểm soát cả identity và từng privileged action.

### 15.3. Giữ quyền thường trực vì thuận tiện

Quyền mạnh tồn tại lâu tăng thời gian phơi nhiễm. **Khắc phục:** cân nhắc JIT/JEA, expiry thực thi và phương án khẩn cấp được hậu kiểm.

### 15.4. Chỉ ẩn nút quản trị trên UI

Client không phải ranh giới tin cậy. **Khắc phục:** enforce phía server, tại tầng nghiệp vụ và mọi đường nội bộ phù hợp.

### 15.5. Kiểm tra role nhưng không kiểm tra resource

Có permission refund không tự cho phép mọi order. **Khắc phục:** action, resource, tenant, time, approval và hạn mức phải đi cùng nhau.

### 15.6. Grant expired trên portal nhưng token còn dùng được

Grant và token/session có thể có thời điểm hết hiệu lực khác nhau. **Khắc phục:** kiểm chứng cơ chế revoke, cache và TTL bằng test thực.

### 15.7. Sử dụng break-glass hằng ngày

Tài khoản khẩn cấp không phải đường bỏ approval. **Khắc phục:** điều kiện sử dụng, alert, hậu kiểm và rotation.

### 15.8. Session recording làm lộ secret

Log/recording có thể trở thành điểm rò rỉ. **Khắc phục:** bảo vệ dữ liệu, quyền xem, masking và retention.

### 15.9. Không kiểm tra đường bypass PAM

Một đường SSH, console, API hoặc pipeline có thể bỏ qua workflow. **Khắc phục:** inventory paths, review trust boundaries và negative tests.

### 15.10. Đóng finding ngay khi sửa cấu hình

Chưa có retest trên bản chạy thì chưa đủ cơ sở. **Khắc phục:** xác minh đúng build/environment và lưu kết quả.

### 15.11. Recertification hình thức

Người quản lý bấm duyệt hàng loạt mà không biết quyền có cần nữa không. **Khắc phục:** gắn review với nhiệm vụ, lịch sử sử dụng và phạm vi grant.

### 15.12. Dùng chung một credential mạnh

Không truy vết/thu hồi riêng được. **Khắc phục:** danh tính riêng, audit attribution và vault; ngoại lệ cần rủi ro và control bù trừ.

## 16. Checklist kiểm soát privileged access

- [ ] Đã định nghĩa **privileged action và privileged identity** dựa trên tác động thực tế.
- [ ] Có inventory human, workload, CI/CD, cloud, DB, Kubernetes và break-glass.
- [ ] Mọi quyền có owner, action, resource, environment và phạm vi rõ.
- [ ] Đã rà least privilege và khả năng leo thang quyền gián tiếp.
- [ ] Xác thực phù hợp human privileged access và machine identity.
- [ ] Workflow request, eligibility, approval, activation, expiry và revoke có kiểm soát.
- [ ] SoD được thực thi cho hành động rủi ro cao theo quy tắc áp dụng.
- [ ] JIT/JEA có hiệu lực ở hệ thống đích, không chỉ trong ticket.
- [ ] Credential/secret được quản lý, rotation và revoke đúng phạm vi.
- [ ] API, console, SSH, CI, job và worker không có bypass trái policy.
- [ ] Break-glass có điều kiện, bảo vệ, cảnh báo, diễn tập và hậu kiểm.
- [ ] Audit actor/action/resource/grant/outcome được lưu an toàn, không chứa secret.
- [ ] Đã test expiry/revoke trên token/session, kể cả cache.
- [ ] Đã test no-grant, wrong-resource, failure-mode và approval conflicts.
- [ ] Có recertification theo kỳ và theo các trigger thay đổi quan trọng.
- [ ] Bằng chứng gắn policy/standard revision, build, environment, time và reviewer.
- [ ] Findings có owner, hạn, risk decision và **tiêu chí retest**.
- [ ] Ngoại lệ có thẩm quyền, thời hạn, control bù trừ và residual risk rõ.
- [ ] Kết luận assurance ghi phạm vi, confidence và phần chưa kiểm tra.
- [ ] Có trigger rà soát lại sau thay đổi role, IdP, pipeline, dữ liệu hoặc incident.

Checklist hỗ trợ thực hành, **không thay thế** bằng chứng kiểm thử, log vận hành hoặc đánh giá độc lập khi cần.

## 17. Câu hỏi tự kiểm tra

1. Privileged access khác authentication và authorization ở khía cạnh nào?
2. Vì sao một CI/CD service account có thể là privileged identity dù không có role tên administrator?
3. Phân biệt **least privilege**, **JIT**, **JEA** và **zero standing privileges**.
4. Eligibility, approval, activation, usage và revocation có phải cùng một trạng thái không?
5. Token đã phát hành trước khi grant hết hạn có thể còn được chấp nhận không? Cần kiểm chứng thế nào?
6. Vì sao “admin đã bật MFA” không đủ để kết luận mọi hoạt động đặc quyền được kiểm soát?
7. Nêu hai cách leo thang quyền gián tiếp ngoài việc được cấp role root.
8. Khi nào break-glass hợp lệ? Vì sao phải bảo vệ, alert và hậu kiểm?
9. Người quản trị có quyền xóa audit log của chính mình tạo ra vấn đề assurance gì?
10. Trong ví dụ refund, vì sao permission refund chưa đủ để thực hiện mọi giao dịch?
11. Grant cho order X có nên sử dụng được cho order Y không? Test ra sao?
12. Tại sao controller test mock tầng service chưa đủ chứng minh method security đang chạy?
13. Với workload identity, những control nào thích hợp hơn MFA tương tác?
14. Chỉ số MFA coverage 100% có thể bỏ sót những hệ thống hoặc tài khoản nào?
15. Control owner, risk owner và assurance reviewer có trách nhiệm khác nhau thế nào?
16. Những sự kiện nào nên buộc đánh giá lại privileged access ngoài chu kỳ thường xuyên?

## 18. Tổng kết

**Privileged access** là cách **quản lý chặt các quyền và hành động có thể gây hậu quả lớn**, áp dụng cho cả người dùng và danh tính tự động. Một chương trình hiệu quả phải kiểm kê và giới hạn quyền, xác thực phù hợp, cấp quyền có điều kiện/thời hạn, kiểm tra SoD, quản lý credential, giám sát hành động, thu hồi thật sự, bảo vệ break-glass và rà soát theo rủi ro. Đối với **SECURITY_SECURITY_ASSURANCE**, trọng tâm không phải tuyên bố “có PAM” hay “đã bật MFA”, mà là **kiểm chứng bằng security claim, test âm/dương, log, audit và retest** rằng quyền đặc biệt chỉ hoạt động đúng danh tính, hành động, tài nguyên, điều kiện và thời gian. Kết quả phải được ghi rõ phạm vi, chất lượng bằng chứng và residual risk, để chương trình assurance tiếp tục cải tiến theo thay đổi trong phát triển và vận hành.
