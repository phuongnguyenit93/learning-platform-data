# Thay đổi vai trò trong Mover lifecycle: cập nhật danh tính và quyền truy cập an toàn

Trong quản lý vòng đời danh tính **Identity and Access Management (IAM)**, **Mover** là tình huống một người đang có quan hệ với tổ chức chuyển sang vai trò, bộ phận, vị trí, trách nhiệm hoặc phạm vi công việc khác. **Thay đổi vai trò** (*role change*) là một trong những sự kiện Mover quan trọng nhất: người dùng vẫn có thể giữ nguyên danh tính và tài khoản đăng nhập, nhưng tập quyền truy cập hợp lệ phải được đánh giá lại.

Ví dụ, một kỹ sư vận hành chuyển sang vai trò phân tích dữ liệu. Trước đây người đó có quyền sửa cấu hình sản xuất; ở vị trí mới họ cần quyền đọc một số tập dữ liệu, nhưng không còn lý do giữ quyền triển khai hoặc quyền quản trị. Nếu IAM chỉ **cấp thêm** quyền của vị trí mới, đặc quyền cũ có thể tồn tại nhiều năm. Hiện tượng này gọi là **quyền tích lũy** (*privilege accumulation*) hoặc **quyền truy cập tồn dư** (*residual access*).

Bài thuộc chương **Mover lifecycle**, trong module IAM theo mô hình **Joiner–Mover–Leaver (JML)**. Trọng tâm là quy trình xác định và áp dụng thay đổi vai trò từ HRIS/nguồn có thẩm quyền, đối chiếu **RBAC/ABAC**, kiểm tra **least privilege** và **Segregation of Duties (SoD)**, đồng bộ qua IdP/SSO/SCIM hoặc API ứng dụng, xử lý phiên và tài khoản đặc quyền, kiểm toán và xác nhận rằng quyền cũ đã được thu hồi thực sự.

## 1. “Vai trò” ở đây có thể mang những nghĩa nào?

Muốn quản lý một sự kiện Mover đúng, trước tiên cần biết **vai trò nào đang thay đổi**. Tên gọi *role* trong HRIS và ứng dụng không luôn biểu diễn cùng một đối tượng.

| Khái niệm | Mô tả | Ví dụ | Ý nghĩa khi Mover |
| --- | --- | --- | --- |
| **Job / Position** — chức danh/vị trí | Vị trí công tác được ghi nhận trong HRIS hoặc hệ thống quản lý tổ chức. | `Operations Engineer`, `Finance Analyst`. | Là một tín hiệu nghiệp vụ mạnh để xác định nhu cầu truy cập mới. |
| **Business role** — vai trò nghiệp vụ | Tập trách nhiệm được doanh nghiệp định nghĩa để quy đổi ra quyền. | `Payment Reviewer`, `Customer Support`. | Cần đánh giá lại khi trách nhiệm thay đổi, dù chức danh không đổi. |
| **Technical / Application role** — vai trò kỹ thuật | Nhóm permission do một nền tảng hay ứng dụng triển khai. | `crm-editor`, `db-read-only`, `cloud-admin`. | Là đối tượng thực tế có thể phải cấp/gỡ tại hệ thống đích. |
| **Group membership** — thành viên nhóm | Cơ chế nhóm trong directory, IdP hoặc ứng dụng; có thể ánh xạ vào role. | `ops-prod-deployers`. | Có thể cần xóa nhóm cũ và thêm nhóm mới; phải kiểm tra hiệu quả ở ứng dụng. |
| **Entitlement** — quyền được cấp | Đơn vị quyền một hệ thống quản lý, như role, group, license hoặc quyền truy cập tài nguyên. | Quyền deploy vào production; quyền đọc báo cáo tài chính. | Là đơn vị cần đối soát giữa quyền mong muốn và quyền thực tế. |
| **Contextual attribute** — thuộc tính ngữ cảnh | Bộ phận, vị trí, dự án, khu vực, loại hợp đồng hoặc trạng thái nhân sự. | `department=finance`. | Có thể làm thay đổi kết quả ABAC mà không trực tiếp thêm/gỡ nhóm. |

**Ví dụ phân biệt:** HRIS cập nhật `jobCode=FIN-ANALYST` không có nghĩa ứng dụng đã gán một role đúng tên `FIN-ANALYST`. Chính sách IAM có thể ánh xạ job đó thành quyền đọc báo cáo, nhóm thư mục chung và yêu cầu phê duyệt riêng đối với dữ liệu nhạy cảm. Ngược lại, một người có thể giữ nguyên chức danh nhưng được giao nhiệm vụ phê duyệt thanh toán; đây vẫn là thay đổi trách nhiệm có khả năng kéo theo quyền truy cập.

### 1.1. Mover khác Joiner và Leaver ở điểm nào?

- **Joiner:** bắt đầu quan hệ làm việc hoặc hợp tác; cần xác minh danh tính, tạo/liên kết account và cấp quyền đầu tiên.
- **Mover:** quan hệ vẫn tiếp tục nhưng điều kiện sử dụng quyền đã thay đổi; thường **giữ identity ID**, đánh giá lại các entitlement hiện hành, thu hồi những quyền không phù hợp và cấp quyền mới.
- **Leaver:** kết thúc quan hệ hoặc tư cách được phép truy cập; cần chặn các đường truy cập theo thời điểm quy định và thực hiện deprovisioning.

Một Mover không nhất thiết chỉ là một nhân viên chuyển phòng ban. Người lao động có thể chuyển quản lý, đổi cấp bậc, được luân chuyển tạm thời, đổi dự án, đổi địa điểm hoặc thay đổi trách nhiệm trên cùng một vị trí. Với nhà thầu, người bảo trợ có thể đổi phạm vi công việc. Tổ chức phải định nghĩa **những sự kiện nào có thể làm thay đổi quyền**, dựa trên chính sách và dữ liệu được quản trị.

## 2. Mục tiêu kiểm soát khi thay đổi vai trò

Quy trình Mover hiệu quả phải bảo đảm đồng thời các mục tiêu:

1. **Đúng người và đúng thời điểm:** sự kiện đổi vai trò liên kết với đúng identity, xác định chính xác ngày có hiệu lực và nguồn có thẩm quyền.
2. **Quyền mới đáp ứng công việc:** cấp quyền cần thiết cho vị trí mới theo nguyên tắc đặc quyền tối thiểu, thẩm quyền phê duyệt và điều kiện của tài nguyên.
3. **Quyền cũ không còn lý do được gỡ:** không chỉ thêm quyền mới, mà phải xem lại toàn bộ entitlement bị ảnh hưởng bởi thay đổi vai trò.
4. **Tránh xung đột nhiệm vụ:** nhận diện quyền kết hợp không an toàn, đặc biệt khả năng vừa lập vừa phê duyệt cùng một giao dịch.
5. **Không bỏ sót đường truy cập:** xét nhóm directory, quyền trực tiếp trong ứng dụng, tài khoản cục bộ, đặc quyền tạm thời, session, token và credential liên quan.
6. **Có bằng chứng và người chịu trách nhiệm:** biết ai xác nhận thay đổi, chính sách/phê duyệt nào được áp dụng, thao tác nào đã chạy và kết quả thực tế là gì.

**Phân biệt quan trọng:** việc HRIS xác nhận một vai trò mới là **thay đổi dữ liệu nguồn**; IAM tính ra quyền mong muốn là **quyết định chính sách**; gửi tác vụ provisioning là **yêu cầu thực thi**; còn đọc lại quyền từ ứng dụng là **xác minh kết quả**. Bốn việc này không tự thay thế cho nhau.

## 3. Luồng Mover từ HRIS tới ứng dụng đích

~~~mermaid
flowchart TD
    HR["HRIS / Nguồn có thẩm quyền: vai trò cũ → mới"] --> ING["Nhận sự kiện, kiểm tra identity, hiệu lực, phiên bản"]
    ING --> POL["IAM / IGA: tính desired access"]
    CATALOG["Role catalog, policy RBAC/ABAC, owner"] --> POL
    POL --> SOD{"SoD, rủi ro, phê duyệt"}
    SOD -->|Hợp lệ| PLAN["Kế hoạch: giữ / thu hồi / cấp / kiểm tra"]
    SOD -->|Cần phê duyệt| APR["Owner phê duyệt / từ chối"]
    APR --> PLAN
    APR -->|Từ chối| REJECT["Không cấp quyền chưa được duyệt"]
    PLAN --> IDP["Directory / IdP: thuộc tính, nhóm"]
    PLAN --> CON["SCIM / API / IAM connector"]
    CON --> APP["Ứng dụng: account, role, entitlement"]
    IDP --> SSO["SSO: xác thực và truyền claim"]
    SSO --> APP
    APP --> VERIFY["Đối soát trạng thái thực tế"]
    IDP --> VERIFY
    VERIFY -->|Lệch quyền| REM["Lỗi/ticket, owner, retry hoặc thu hồi thủ công"]
    REM --> VERIFY
    VERIFY -->|Khớp| CLOSE["Đóng sự kiện Mover, giữ audit evidence"]
~~~

Đây là **mô hình tham khảo**, không phải cấu trúc bắt buộc của một sản phẩm IAM. Một doanh nghiệp có thể dùng nhiều nguồn có thẩm quyền, hỗ trợ cả cập nhật tự động lẫn thủ công, hoặc chỉ áp dụng chính sách tại ứng dụng. Dù triển khai bằng cách nào, cần phân biệt **ai có quyền quyết định**, **ai thực thi** và **ai kiểm chứng**.

### 3.1. Bước 1 — Nhận sự kiện vai trò thay đổi

Nguồn thường là **HRIS**, hệ thống quản lý hợp đồng hoặc một workflow phân công trách nhiệm đã được tổ chức ủy quyền. Dữ liệu tối thiểu cần đủ để xác định:

| Trường logic | Ý nghĩa |
| --- | --- |
| **identity / employment reference** | Chủ thể nào được tác động; nhận diện người qua ID ổn định, có nguồn/phạm vi rõ. |
| **oldRole / newRole** | Vai trò trước và sau, theo từ điển vai trò nghiệp vụ hoặc mã vị trí có định nghĩa. |
| **effectiveAt** | Thời điểm thay đổi có hiệu lực về nghiệp vụ. |
| **recordedAt / eventId / sourceVersion** | Thời điểm ghi nhận, khóa chống xử lý trùng, thông tin phiên bản nếu nguồn hỗ trợ. |
| **manager / department / assignment** | Thuộc tính liên quan có thể ảnh hưởng RBAC/ABAC, approver hoặc owner. |
| **reason / approval reference** | Căn cứ thay đổi theo quy trình được phép, nếu chính sách yêu cầu. |

Ví dụ bản tin **minh họa nội bộ**, không phải chuẩn JSON chung của HRIS hoặc SCIM:

~~~json
{
  "eventId": "hr-mover-2026-0142",
  "eventType": "BUSINESS_ROLE_CHANGED",
  "sourceSystem": "HRIS",
  "identityId": "person-2048",
  "employmentRecordId": "employment-923",
  "oldRole": "operations-engineer",
  "newRole": "finance-analyst",
  "effectiveAt": "2026-09-01T00:00:00+07:00",
  "recordedAt": "2026-08-25T08:30:00+07:00",
  "sourceVersion": 34,
  "reasonRef": "hr-change-5821"
}
~~~

**effectiveAt khác recordedAt:** hệ thống có thể biết kế hoạch chuyển vai trò trước nhiều ngày. Cần phân biệt việc **chuẩn bị account/quyền chờ kích hoạt**, việc **cấp quyền có hiệu lực** và thời điểm **thu hồi quyền cũ**. Không tự áp dụng toàn bộ quyền của vị trí mới ngay khi HR vừa nhập quyết định nếu chính sách yêu cầu đợi ngày hiệu lực.

### 3.2. Bước 2 — Xác định đúng identity và các account liên quan

IAM không nên gắn thay đổi vai trò cho người dùng chỉ bằng tên hoặc email. Người có thể đổi email khi chuyển đơn vị; một email có thể bị tái sử dụng theo chính sách; nhiều account có thể ánh xạ với một identity.

Khi tiếp nhận Mover, cần kiểm tra:

- Nguồn sự kiện được tin cậy và có thẩm quyền thay đổi vai trò thuộc phạm vi đó.
- Identity ID, employee identifier và employment/assignment record liên kết nhất quán.
- Có nhiều quan hệ công việc đồng thời hoặc nhiều vai trò hiệu lực không, để không thu hồi nhầm quyền hợp lệ của quan hệ khác.
- Những account đích đã liên kết gồm IdP, ứng dụng nội bộ, tài nguyên cloud, công cụ phát triển, tài khoản đặc quyền và các đường đăng nhập local có liên quan.
- Có account chưa được ánh xạ hoặc account mồ côi cần đưa vào đối soát hay không.

Việc **thay đổi vai trò** thông thường không có nghĩa tạo một identity mới. Nếu chính sách yêu cầu tách account vì nhiệm vụ đặc biệt, IAM vẫn phải giữ liên kết và trách nhiệm giải trình giữa người, các account và quyền.

### 3.3. Bước 3 — Tính lại quyền mong muốn (desired access)

Thay vì diễn giải Mover thành “thêm nhóm của vai trò mới”, hãy tính **tập quyền hợp lệ sau thay đổi** từ chính sách hiện hành.

Một mô hình trực quan:

\[
D_{after} = f(R_{new}, A_{effective}, E_{active}, P, X_{approved})
\]

Trong đó:

- `R_new`: vai trò và trách nhiệm nghiệp vụ có hiệu lực.
- `A_effective`: thuộc tính HR và assignment có hiệu lực, như phòng ban, địa điểm, loại hợp đồng.
- `E_active`: các quan hệ công việc/dự án khác vẫn hợp lệ.
- `P`: chính sách RBAC/ABAC, SoD và quy tắc bắt buộc.
- `X_approved`: ngoại lệ được phê duyệt và còn thời hạn.

Hàm trên là **mô hình khái niệm**, không phải một công thức tiêu chuẩn hóa. Mỗi hệ thống IAM phải triển khai ngữ nghĩa rõ ràng, bao gồm cách quản lý quyền được cấp trực tiếp và ngoại lệ.

Giả sử:

- `C` là tập entitlement thực tế đã biết trên các hệ thống đích.
- `D` là tập entitlement mong muốn đã được phê duyệt tại thời điểm áp dụng.
- `T_remove = C − D` là các quyền cần đánh giá thu hồi.
- `T_grant = D − C` là các quyền cần cấp sau khi đủ điều kiện.
- `T_keep = C ∩ D` là các quyền tiếp tục phù hợp.

Trong thực tế phải phân biệt **quyền điều khiển bởi IAM** với quyền đặc biệt/khác phạm vi hoặc trạng thái đang chờ đồng bộ; không được tự động xóa một quyền chỉ dựa trên phép trừ nếu hệ thống chưa có đủ nguồn dữ liệu, owner hoặc chính sách để xác định tính hợp lệ. Nhưng mọi quyền ngoài desired state cần được **điều tra và đưa về trạng thái có căn cứ**, tránh để quyền thừa tồn tại vô thời hạn.

### 3.4. Bước 4 — Kiểm tra rủi ro và phê duyệt

Một Mover có thể cần quyền có độ nhạy cao hơn vai trò cũ. Quy trình cần kiểm tra:

- **Baseline / birthright access:** quyền mặc định theo role mới có đủ điều kiện tự động cấp không?
- **Access request/approval:** quyền vượt chuẩn do người có thẩm quyền nào phê duyệt?
- **Least privilege:** phạm vi tài nguyên và thời hạn quyền có vượt nhu cầu công việc không?
- **SoD:** vai trò cũ và mới cùng tồn tại tạm thời có tạo xung đột không? Có quy tắc cấm hai loại quyền trên cùng giao dịch?
- **Privileged access:** quyền admin nên yêu cầu PAM, MFA mạnh, Just-in-Time (JIT), giới hạn phiên hoặc giám sát bổ sung khi phù hợp.
- **ABAC:** thuộc tính vai trò, đơn vị, vị trí, thiết bị, mức nhạy cảm có thay đổi điều kiện truy cập tại thời điểm yêu cầu không?

**Thu hồi một quyền cũ** thường không cần cùng loại phê duyệt như **cấp quyền nhạy cảm mới**, nhưng tổ chức có thể có quy trình bàn giao hoặc ngoại lệ với owner và ngày hết hạn. Không nên lấy việc chưa có phê duyệt quyền mới làm lý do giữ vĩnh viễn quyền cũ đã hết căn cứ.

## 4. “Giữ, thu hồi, cấp” là ba quyết định riêng

Giả sử một nhân viên rời nhóm vận hành để sang phân tích tài chính:

| Entitlement | Trước Mover | Sau Mover mong muốn | Hành động |
| --- | --- | --- | --- |
| `company:sso-user` | Có | Có | **Giữ** account, MFA và quyền dùng dịch vụ chung. |
| `ops:monitor-read` | Có | Không, trừ khi assignment khác còn cần | **Thu hồi** theo policy mới. |
| `ops:production-deploy` | Có | Không | **Thu hồi ưu tiên**, kiểm tra phiên/token liên quan. |
| `finance:reports-read` | Không | Có, khi thuộc tính hợp lệ | **Cấp** theo baseline đã phê duyệt. |
| `finance:payment-approve` | Không | Chưa có phê duyệt | **Không tự cấp**; tạo yêu cầu owner xét duyệt nếu có nhu cầu. |
| `developer:git-account` | Có | Tùy nhiệm vụ còn hiệu lực | **Rà soát**; có thể giữ account nhưng gỡ quyền repo/admin cũ. |

Điều quan trọng là không đồng nhất **account** với **entitlement**. Với Mover, tài khoản có thể còn tồn tại để duy trì email, lịch sử và khả năng đăng nhập, trong khi các role và permission bên trong thay đổi đáng kể. **Đóng toàn bộ account** có thể sai nếu người đó vẫn thuộc tổ chức; **giữ nguyên toàn bộ quyền** cũng sai nếu chức năng mới không còn cần chúng.

### 4.1. Quyền cấp gián tiếp và quyền cấp trực tiếp

Một nhân viên có thể nhận quyền qua nhiều đường:

~~~text
Identity
  ├── HR business role -> IAM access policy -> IdP group -> App role
  ├── Project membership -> Application group -> Resource scope
  ├── Direct app assignment -> App entitlement
  ├── Privileged / JIT access -> Time-bound admin permission
  └── Local credentials / tokens -> Additional access path
~~~

Gỡ một IdP group **có thể chưa đủ** nếu người đó còn được cấp trực tiếp `app-admin` trong ứng dụng. Cần xem cả quyền thông qua nhóm lồng nhau, quyền được phân quyền trong cloud IAM, API key/personal access token và ngoại lệ còn hiệu lực. Mô hình quyền nào áp dụng tùy từng sản phẩm; IAM phải có bản đồ entitlement đủ tin cậy để quyết định và đối soát.

### 4.2. RBAC và ABAC kết hợp trong Mover

**RBAC (Role-Based Access Control)** xác định tập quyền dựa trên vai trò. **ABAC (Attribute-Based Access Control)** xét thêm thuộc tính của subject, tài nguyên, hành động và ngữ cảnh; những chính sách này có thể kết hợp.

Ví dụ minh họa, không phải cú pháp của một policy engine cụ thể:

~~~text
ALLOW read finance-report
WHEN
    subject.employmentStatus == "ACTIVE"
    AND subject.businessRole == "finance-analyst"
    AND subject.departmentId == resource.ownerDepartmentId
    AND resource.classification != "RESTRICTED"
ELSE DENY
~~~

Nếu người dùng vừa chuyển sang tài chính nhưng **departmentId** chưa cập nhật ở ứng dụng, một chính sách ABAC có thể từ chối yêu cầu đúng luật nghiệp vụ; đó là tín hiệu cần xem luồng đồng bộ. Ngược lại, token hoặc phiên cũ còn chứa role vận hành có thể gây nguy cơ nếu ứng dụng tin hoàn toàn vào claim lâu hạn mà không đánh giá lại quyền khi cần.

**Role catalog** phải chỉ rõ vai trò nào được HR định nghĩa, role nào là đối tượng kỹ thuật, quyền nào nằm trong baseline và ai sở hữu từng chính sách. Nếu tạo một role kỹ thuật riêng cho mọi tổ hợp phòng ban × địa điểm × dự án, việc quản trị có thể trở nên quá phức tạp; có thể dùng business role cộng thuộc tính/scope tùy công cụ hỗ trợ.

## 5. Ngày hiệu lực, giai đoạn bàn giao và nhiều vai trò đồng thời

### 5.1. Khi nào quyền cũ phải bị thu hồi?

Hãy phân biệt các mốc:

| Mốc | Ý nghĩa |
| --- | --- |
| `recordedAt` | HRIS hoặc hệ thống nguồn đã ghi nhận quyết định đổi vai trò. |
| `effectiveAt` | Vai trò mới bắt đầu có hiệu lực về nghiệp vụ. |
| `grantScheduledAt` | Thời điểm dự kiến cấp quyền mới; có thể chuẩn bị trước hoặc ngay khi hiệu lực, tùy policy. |
| `oldAccessExpiresAt` | Thời điểm quyền cũ phải không còn sử dụng được theo chính sách hoặc ngoại lệ. |
| `verifiedAt` | Thời điểm IAM xác minh quyền thực tế tại đích đã đúng. |

Không có quy tắc toàn cầu rằng **mọi quyền cũ phải mất chính xác tại 00:00** hoặc mọi quyền mới có thể mở trước. Với quyền nhạy cảm, yêu cầu hạn chế chồng lấn và độ trễ thu hồi có thể rất nghiêm ngặt. Với quyền bàn giao hợp lệ, tổ chức có thể cấp quyền tạm thời **có owner, lý do, phạm vi, thời hạn và kiểm toán**.

### 5.2. Ví dụ quyền bàn giao có thời hạn

Lan chuyển từ nhóm vận hành sang tài chính ngày **01/09**. Nhóm vận hành cần Lan hỗ trợ đọc log sự cố đến **03/09**, nhưng không được deploy nữa.

Một kế hoạch phù hợp có thể là:

1. Ngày 01/09: gỡ ngay `ops:production-deploy` và mọi đặc quyền liên quan; giữ `ops:logs-read` dưới ngoại lệ đã duyệt.
2. Ngày 01/09: cấp `finance:reports-read` theo quyền hợp lệ của vị trí mới.
3. Chậm nhất 03/09 theo mốc phê duyệt: thu hồi `ops:logs-read`, không để ngoại lệ kéo dài vì “quên đóng ticket”.
4. Ghi evidence owner vận hành chấp thuận quyền bàn giao, owner tài chính phê duyệt quyền mới, và kết quả xác minh entitlement tại các hệ thống đích.

Nếu việc cấp quyền mới trước thời điểm gỡ quyền cũ tạo SoD conflict, phải **đánh giá hoặc ngăn chặn** giai đoạn chồng lấn. Một ngoại lệ SoD không nên được coi là hợp lệ chỉ vì có ticket; chính sách có thể cấm tuyệt đối một số tổ hợp hoặc yêu cầu biện pháp giảm thiểu được chấp thuận.

### 5.3. Người có nhiều assignment đồng thời

Một nhân viên có thể vừa giữ nhiệm vụ chính ở tài chính, vừa tham gia dự án ngắn hạn ở vận hành. Việc thay đổi **một** assignment không đồng nghĩa phải gỡ các quyền vẫn hợp lệ cho **assignment khác**. Desired access nên tính từ **tập quan hệ/assignment đang có hiệu lực**, áp dụng quy tắc hợp nhất, xung đột và thời hạn; đồng thời cần tránh cho quyền tạm thời trở thành quyền vĩnh viễn.

Trong hệ thống chưa quản lý được nhiều assignment, trường role đơn trị có thể gây mất quyền hợp lệ hoặc giữ quyền không đúng. Cần định nghĩa rõ business role chính, trách nhiệm bổ sung và entitlement tạm thời, thay vì gộp nhiều role vào một chuỗi văn bản khó xử lý.

## 6. Thực thi Mover qua IdP, SSO, SCIM và API

### 6.1. Cập nhật IdP/Directory

Directory hoặc **Identity Provider (IdP)** có thể lưu các thuộc tính như department, job title, nhóm, trạng thái account. Sau Mover, IAM có thể cập nhật những thuộc tính đã được chính sách chọn, thay đổi group membership và điều kiện xác thực.

**IdP xác thực danh tính**, trong khi **IAM/IGA hoặc ứng dụng** quyết định quyền nghiệp vụ. Một IdP group có thể ánh xạ thành ứng dụng/role, nhưng cần xác định rõ: ai sở hữu mapping, nhóm nào có quyền nhạy cảm và thay đổi nhóm mất bao lâu để tác động đến target.

**Single Sign-On (SSO)** giúp người dùng đăng nhập qua IdP bằng SAML hoặc OIDC theo cấu hình ứng dụng. Đăng nhập SSO thành công sau Mover không chứng minh các entitlement tại mọi ứng dụng đã cập nhật. SSO cũng không tự hủy toàn bộ phiên đang tồn tại hoặc personal access token của ứng dụng.

### 6.2. SCIM và provisioning

**SCIM 2.0** cung cấp mô hình tài nguyên/API thường được dùng để tạo, cập nhật và vô hiệu hóa User/Group giữa các hệ thống. Ví dụ cấu trúc logic của một thay đổi sau Mover có thể gồm:

~~~yaml
event: MOVER
identityId: person-2048
desiredChanges:
  - target: CorporateIdP
    action: UPDATE_ATTRIBUTES
    changes:
      department: Finance
  - target: CRM
    action: REMOVE_ENTITLEMENT
    entitlement: ops-production-deploy
  - target: FinanceAnalytics
    action: GRANT_ENTITLEMENT_AFTER_APPROVAL
    entitlement: finance-reports-read
verification:
  requireObservedState: true
  onFailure: ALERT_AND_RECONCILE
~~~

**Đây là kế hoạch IAM minh họa, không phải cú pháp yêu cầu SCIM chuẩn.** Trong SCIM, User và Group có các thuộc tính chuẩn; entitlement/role cụ thể phụ thuộc schema và khả năng provider. Không thể giả định rằng mọi quyền của ứng dụng đều được quản lý trực tiếp qua trường `roles` hoặc `groups`; có thể cần API riêng hoặc thao tác thủ công.

Đối với ứng dụng cho phép provisioning qua SCIM, một yêu cầu PATCH cập nhật thuộc tính User có thể trông như sau:

~~~http
PATCH /scim/v2/Users/12345 HTTP/1.1
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    { "op": "Replace", "path": "title", "value": "Finance Analyst" }
  ]
}
~~~

Đây là ví dụ **cập nhật thuộc tính `title` trên User**, không phải thao tác thu hồi role. Việc thay đổi `title` không mặc nhiên làm ứng dụng gỡ nhóm vận hành hoặc cấp quyền tài chính. Connector cần thực hiện các thay đổi entitlement/Group membership tương ứng theo hợp đồng tích hợp và tiếp tục readback.

### 6.3. Phiên, token và quyền còn hiệu lực

Trong một số hệ thống, quyền được kiểm tra **liên tục** dựa trên trạng thái hiện tại; trong hệ thống khác, quyền có thể được sao chép vào token hoặc session tại thời điểm đăng nhập. Sau Mover:

- **ID token** của OIDC mô tả thông tin xác thực danh tính theo giao thức; không nên dùng nó như một cơ chế bảo đảm mọi quyền API đã cập nhật.
- **Access token** có thể chứa scope/claim được áp dụng khi token còn hiệu lực, tùy cách API kiểm tra và hỗ trợ thu hồi.
- **Refresh token** có thể cho phép xin access token mới nếu authorization server chưa thu hồi hoặc chưa áp dụng chính sách mới.
- **Session ứng dụng/IdP** có thể vẫn tồn tại sau khi nhóm hoặc thuộc tính tại directory thay đổi.
- **Personal access token, API key, credential cục bộ** có thể tạo đường truy cập độc lập với SSO, cần quản lý riêng khi quyền cũ bị thu hồi.

Với Mover nhạy cảm, chính sách cần quyết định lúc nào thu hồi session/token, buộc xác thực lại, giới hạn thời lượng token, hoặc kiểm tra quyền tại backend trên mỗi yêu cầu. Không được suy ra “đã hết quyền” chỉ từ việc thuộc tính HR hoặc IdP đã thay đổi.

## 7. Thay đổi vai trò có đặc quyền và xung đột nhiệm vụ

### 7.1. Nguyên tắc least privilege với quyền quản trị

Đối với quyền `cloud-admin`, `db-owner`, `production-deploy` hoặc quyền quản lý thông tin nhạy cảm, thay đổi vai trò phải đánh giá cả **quyền trực tiếp**, **vai trò được kế thừa**, **đặc quyền qua hệ thống khác**, và **credential có thể tiếp tục sử dụng**.

**PAM (Privileged Access Management)** có thể hỗ trợ cấp quyền quản trị theo phiên, ghi nhận yêu cầu/phê duyệt, giám sát hoạt động đặc quyền hoặc xoay vòng mật khẩu theo khả năng sản phẩm. **JIT (Just-in-Time)** cho phép mở quyền trong thời gian giới hạn theo điều kiện; Mover cần bảo đảm những quyền được kích hoạt tạm thời không trở thành ngoại lệ vĩnh viễn.

Khi nhân viên rời vai trò quản trị, ngoài gỡ nhóm admin còn có thể cần kiểm tra session SSH/RDP, cloud sessions, credentials đã cấp, API tokens hoặc quyền được ủy quyền cho tài khoản khác. Không phải mọi đường truy cập đều nằm dưới một IdP.

### 7.2. Kiểm tra SoD trước khi cấp quyền mới

**Segregation of Duties** giảm rủi ro một người tự thực hiện nhiều bước phải tách biệt về trách nhiệm. Ví dụ:

| Tổ hợp quyền | Rủi ro | Kiểm soát minh họa |
| --- | --- | --- |
| `payment-create` + `payment-approve` trên cùng tập giao dịch | Có thể tạo và tự phê duyệt thanh toán. | Tách role hoặc áp dụng policy kiểm tra người thực hiện ở cấp giao dịch. |
| `user-grant-admin` + `audit-log-delete` | Có thể mở rộng đặc quyền rồi che giấu dấu vết. | Phân tách quản trị tài khoản và quyền quản lý audit log. |
| `production-deploy` + `security-approval` | Có thể tự phê duyệt thay đổi rủi ro cao. | Quy trình phê duyệt độc lập, kiểm soát theo nhiệm vụ. |

**Static SoD** có thể từ chối gán hai role cùng lúc; **dynamic SoD** có thể từ chối một hành động trên một giao dịch nếu người dùng đã thực hiện bước xung đột trước đó. IAM cần biết phạm vi kiểm tra để không nhầm “không có conflict role” với “mọi workflow nghiệp vụ đều an toàn”.

Khi một Mover được duyệt role mới nhưng role cũ chưa được thu hồi, hệ thống có thể tạo **xung đột tạm thời**. Kế hoạch thay đổi cần đặt thứ tự hoặc ràng buộc thực thi phù hợp, đặc biệt với quyền nhạy cảm: ví dụ xác minh gỡ quyền phê duyệt cũ trước khi kích hoạt quyền tạo giao dịch mới nếu chính sách cấm cùng tồn tại.

## 8. Quản trị tài khoản dịch vụ khi owner đổi vai trò

Một kỹ sư vận hành có thể là **owner** của service account `billing-etl`, trong khi tài khoản đó phục vụ công việc tự động lâu dài. Khi kỹ sư chuyển sang vai trò tài chính, IAM không nên mặc nhiên khóa service account chỉ vì owner đổi role. Cần phân biệt:

- **Human identity:** danh tính nhân viên và các quyền cá nhân phải thay đổi theo Mover.
- **Service/workload identity:** danh tính của job, ứng dụng hoặc môi trường thực thi; có owner, mục đích, entitlement và credential riêng.
- **Ownership relationship:** người hoặc nhóm chịu trách nhiệm cấu hình, cấp quyền và vận hành service; có thể cần bàn giao.

Quy trình Mover nên kiểm tra các **non-human accounts** do người đó sở hữu hoặc có quyền thao tác:

1. Chỉ định owner mới hoặc nhóm chịu trách nhiệm phù hợp; tránh orphaned service account.
2. Chuyển quyền quản trị service nếu người chuyển vai trò không còn cần vận hành.
3. Đánh giá và xoay vòng credential/secret nếu người cũ có thể biết bí mật hoặc giữ đường truy cập không còn hợp lệ.
4. Rà soát quyền của workload theo công việc thực tế; không sửa tùy tiện khiến dịch vụ đang chạy ngừng hoạt động.
5. Ghi nhận thời điểm bàn giao, người phê duyệt, kết quả và kế hoạch deprovision khi workload ngừng.

**Ví dụ:** người quản lý hệ thống cũ rời nhóm vận hành nhưng `billing-etl` vẫn phải chạy hằng đêm. Owner được bàn giao cho đội dữ liệu, credential bị lộ cho người cũ (nếu có) được thay thế, quyền cá nhân của nhân viên được gỡ. Tài khoản dịch vụ chỉ bị deprovision khi **vòng đời workload** yêu cầu.

## 9. Tính an toàn của sự kiện và xử lý lỗi

### 9.1. Sự kiện đến muộn, phát lại và thay đổi liên tiếp

Giả sử HRIS phát hai sự kiện:

- **Version 34:** nhân viên từ vận hành chuyển sang tài chính, có hiệu lực 01/09.
- **Version 35:** quyết định thay đổi được sửa: nhân viên chuyển sang kiểm toán nội bộ, có hiệu lực 01/09.

Nếu version 34 đến **sau** version 35, IAM không được tự áp dụng bản cũ như trạng thái hiện hành. Cần kiểm tra source version, effective time và quy tắc cập nhật từ nguồn có thẩm quyền. `eventId` hỗ trợ chống xử lý trùng (*idempotency*), nhưng **eventId một mình không giải quyết thứ tự sự kiện**.

Những tình huống cần thiết kế rõ:

- **Duplicate event:** nhận cùng một sự kiện nhiều lần không tạo account/role trùng.
- **Out-of-order event:** sự kiện cũ không ghi đè trạng thái hợp lệ mới.
- **Retroactive correction:** HR sửa quyết định có hiệu lực từ trước; cần đánh giá lại quyền đang tồn tại và giữ lịch sử.
- **Concurrent assignments:** nhiều sự kiện ảnh hưởng các quan hệ khác nhau không tự xóa quyền vẫn còn hợp lệ.
- **Partial failure:** một đích cập nhật thành công nhưng đích khác lỗi; không có transaction toàn cục mặc định giữa các SaaS.
- **Manual grant drift:** admin cấp quyền trực tiếp ngoài IAM; việc đổi role không chắc tự phát hiện quyền này nếu không có đối soát.

### 9.2. Kế hoạch thực thi có trạng thái

Một workflow Mover có thể theo dõi:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED: HR / approved change
    RECEIVED --> VALIDATING
    VALIDATING --> REVIEW_REQUIRED: Mâu thuẫn/SoD/phê duyệt thiếu
    VALIDATING --> PLANNED: Policy hợp lệ
    REVIEW_REQUIRED --> PLANNED: Được duyệt và giải quyết
    REVIEW_REQUIRED --> REJECTED: Bị từ chối
    PLANNED --> EXECUTING: Đến thời điểm hiệu lực
    EXECUTING --> VERIFYING: Các lệnh đã được thực hiện/nhận phản hồi
    EXECUTING --> REMEDIATION: Lỗi hoặc không chắc trạng thái
    VERIFYING --> COMPLETED: Desired state khớp actual state
    VERIFYING --> REMEDIATION: Còn quyền sai lệch
    REMEDIATION --> VERIFYING: Khắc phục, đối soát lại
    REJECTED --> [*]
    COMPLETED --> [*]
~~~

Trạng thái là **mô hình tham khảo**, không phải chuẩn bắt buộc. Một job trả `HTTP 200` hoặc `204` vẫn có thể chưa đủ nếu đích xử lý bất đồng bộ hay có quyền phát sinh từ đường khác. Workflow nên có **cơ chế readback/reconciliation** và báo cáo target nào còn chưa xác nhận.

### 9.3. Pseudocode tính delta và thực thi an toàn

~~~text
onMoverEvent(event):
    assert trustedSource(event.sourceSystem)
    identity = resolveVerifiedIdentity(event.identityId)
    assert validVersionAndEffectiveTime(event)

    if alreadyProcessed(event.eventId):
        return existingWorkflowResult(event.eventId)

    rolesAfter = effectiveBusinessAssignments(identity, event)
    desired = calculateEntitlements(rolesAfter, policies, approvedExceptions)
    riskCheck = validateSoDAndApprovals(desired, identity)
    if riskCheck.requiresDecision:
        createApprovalOrExceptionReview(event, riskCheck)
        return WAITING_APPROVAL

    actual = discoverManagedAndRelevantDirectAccess(identity)
    toRemove = accessNoLongerJustified(actual, desired)
    toGrant  = desired - actual
    toKeep   = actual intersect desired

    plan = buildTimedPlan(
        remove=toRemove,
        grant=toGrant,
        keep=toKeep,
        effectiveAt=event.effectiveAt,
        conflicts=riskCheck.conflicts
    )
    persistPlanAndAudit(event, plan)
    executeByTargetWithSafeRetries(plan)
    observed = readbackAndReconcile(identity, plan.targets)

    if observed != approvedDesiredStateAtNow(identity):
        assignRemediationOwnerAndAlert(event, observed)
        return PENDING_REMEDIATION

    recordVerifiedCompletion(event, observed)
    return COMPLETED
~~~

Đây là **pseudocode giải thích quy trình**, không phải triển khai production. Quy tắc `actual` và `desired` cần tính đúng các account, quyền không được IAM quản lý, quyền từ nhiều assignment và nguồn cấp quyền; đặc biệt phép so sánh quyền có thể cần chuẩn hóa role/group/permission của từng target. Đối với quyền nhạy cảm, thứ tự *remove/grant* có thể phải tuân theo ràng buộc SoD và các mốc hiệu lực chứ không thực hiện tùy ý. Kết quả có thể nhất quán cuối cùng (*eventual consistency*), vì vậy việc retry cần có deadline, cảnh báo và xác minh.

## 10. Tình huống xuyên suốt: chuyển từ vận hành sang tài chính

**Bối cảnh:** Minh có IAM identity `person-2048` và employee number `004281`. Trước ngày 01/09, Minh thuộc nhóm vận hành hệ thống với quyền xem log và deploy lên production. HR xác nhận Minh chuyển sang vị trí **Finance Analyst** từ ngày 01/09. Minh tiếp tục làm nhân viên, giữ email và account IdP cũ.

| Mốc | Sự kiện / Quyết định | Bằng chứng cần ghi |
| --- | --- | --- |
| **25/08** | HRIS gửi quyết định Mover có hiệu lực 01/09. | Event ID, HR record, role cũ/mới, source version, effective time. |
| **26/08** | IAM tính desired access, kiểm tra SoD, tìm các quyền trực tiếp và JIT còn hoạt động. | Policy/version, permission diff, owner, quyết định phê duyệt hoặc ngoại lệ. |
| **01/09** | Gỡ production deploy; thêm quyền đọc báo cáo tài chính khi đủ phê duyệt. | Tác vụ IdP/SCIM/API, kết quả từng hệ thống. |
| **01/09** | Xác minh tài khoản IdP và ứng dụng đã có trạng thái mới; kiểm tra token/phiên đặc quyền. | Snapshot actual state, session/action log, thời điểm kiểm chứng. |
| **02/09** | Đối soát phát hiện một Git team còn quyền deploy vì được cấp trực tiếp. | Drift report, owner nhận ticket, kết quả thu hồi Git team. |
| **03/09** | Xác minh Git quyền cũ đã mất, quyền tài chính đúng phạm vi. | Verification result, audit trail, ticket close cùng thời điểm. |

### 10.1. Tập quyền trước và sau

~~~text
BEFORE (observed)
  company:sso-user
  ops:monitor-read
  ops:production-deploy
  git:release-maintainer  <-- cấp trực tiếp ở ứng dụng

AFTER (approved desired state)
  company:sso-user
  finance:reports-read

CHANGE PLAN
  KEEP:   company:sso-user
  REMOVE: ops:monitor-read, ops:production-deploy, git:release-maintainer
  GRANT:  finance:reports-read
  DENY:   finance:payment-approve nếu chưa được duyệt
~~~

Đến ngày 01/09, hệ thống đã cập nhật role theo IAM nhưng quyền Git trực tiếp chưa được thu hồi. Điều đó cho thấy **đã gửi yêu cầu Mover thành công** khác với **không còn quyền tồn dư**. Quy trình chỉ được đánh dấu hoàn tất khi có bằng chứng quyền Git đã bị gỡ hoặc trường hợp ngoại lệ hợp lệ được ghi nhận theo chính sách.

### 10.2. Ví dụ dữ liệu audit theo workflow

Đây là **JSON minh họa nội bộ**, không phải schema bắt buộc của SCIM hoặc HRIS:

~~~json
{
  "workflowId": "mover-2048-20260901",
  "eventId": "hr-mover-2026-0142",
  "subject": {
    "identityId": "person-2048",
    "oldBusinessRole": "operations-engineer",
    "newBusinessRole": "finance-analyst"
  },
  "effectiveAt": "2026-09-01T00:00:00+07:00",
  "decision": {
    "policyVersion": "iam-role-policy-v5",
    "approvedGrant": ["finance:reports-read"],
    "requiredRemoval": ["ops:production-deploy", "ops:monitor-read", "git:release-maintainer"]
  },
  "execution": {
    "idpUpdate": "SUCCEEDED",
    "financeProvisioning": "SUCCEEDED",
    "gitDirectGrantRemoval": "FAILED_RETRYABLE"
  },
  "verification": {
    "status": "PENDING_REMEDIATION",
    "drift": ["git:release-maintainer"],
    "ticket": "iam-incident-882",
    "accountableOwner": "git-access-owner"
  }
}
~~~

Một sự kiện tổng hợp có thể được nối từ nhiều event con qua `workflowId`, `eventId`, `targetAccountId` và mã tác vụ. Khi lỗi đã được sửa, nên lưu **sự kiện kiểm chứng mới** thay vì âm thầm sửa lịch sử lỗi thành “chưa từng thất bại”.

## 11. Rà soát quyền và đối soát sau thay đổi vai trò

### 11.1. Access review không trùng với reconciliation

| Hoạt động | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Access review / Recertification** | Quyền đã được duyệt còn phục vụ nhu cầu công việc không? | Quản lý mới xác nhận Minh không còn cần quyền xem log vận hành. |
| **Reconciliation** | Quyền thực tế ở ứng dụng có khớp desired state không? | Git vẫn hiện Minh thuộc nhóm release maintainers dù IAM đã tính phải gỡ. |
| **Audit / Accountability** | Ai yêu cầu, ai phê duyệt, ai thực hiện, hệ thống phản hồi gì và ai sửa lỗi? | Mã HR event, policy version, Git admin change, ticket lỗi, verification result. |

Một quyền có thể được cấp **đúng kỹ thuật** theo chính sách cũ nhưng **không còn hợp lý về nghiệp vụ** sau Mover. Access review giúp phát hiện điều đó. Ngược lại, một người được duyệt quyền mới hợp lệ nhưng ứng dụng **chưa cấp đúng**; reconciliation phát hiện sai lệch triển khai. Hai cơ chế hỗ trợ nhau và không thể thay thế.

### 11.2. Theo dõi residual access

Sau thay đổi vai trò, IAM cần tìm những đường truy cập không còn căn cứ:

- Role/nhóm cũ ở IdP và directory.
- Entitlement được cấp trực tiếp tại ứng dụng, kể cả qua nested group hoặc quyền cloud.
- Account local và admin account chưa đưa vào quản lý tập trung.
- Phiên đang mở, token/API key, credential, SSH key hoặc quyền PAM/JIT chưa hết hạn.
- Quyền tạm thời và ngoại lệ không còn phù hợp sau thay đổi role.
- Tài khoản dịch vụ mà nhân viên vẫn có thể quản trị dù đã chuyển owner.

Không phải mọi mục đều cần bị xóa ngay theo cùng một cách. Cần xét **tính hợp lệ**, **thời điểm hiệu lực**, **khả năng thu hồi**, **mức rủi ro** và **bằng chứng** trên từng target. Quyền còn hợp lệ vì assignment khác phải được ghi rõ để tránh thu hồi nhầm.

## 12. Dấu vết kiểm toán và phân định trách nhiệm

Một workflow Mover có trách nhiệm giải trình nên trả lời được:

1. **Ai xác nhận thay đổi?** HRIS hoặc nguồn assignment nào có thẩm quyền và người/bộ phận sở hữu dữ liệu?
2. **Ai quyết định entitlement?** Chính sách RBAC/ABAC nào, phiên bản nào, application owner/manager nào phê duyệt quyền vượt chuẩn?
3. **Ai thực thi?** IAM connector, service account hoặc admin thủ công nào chạy thay đổi?
4. **Thay đổi gì?** Account nào, role/group/entitlement trước và sau, thời điểm bắt đầu và kết thúc?
5. **Kết quả thực tế là gì?** Target nào đã cập nhật và được readback, target nào còn lỗi hoặc quyền tồn dư?
6. **Ai chịu trách nhiệm xử lý lỗi?** Owner nào nhận ticket, thời hạn hoàn thành, bằng chứng xác nhận đóng?

**Tách trách nhiệm:** HR chủ yếu xác nhận quan hệ và vai trò nghiệp vụ; business/application owner quyết định quyền cần thiết; IAM/IT vận hành quy trình và connector; đội an ninh/kiểm toán kiểm tra các kiểm soát theo nhiệm vụ. Ma trận **RACI** có thể giúp tránh tình trạng mọi người đều được thông báo nhưng không ai sở hữu kết quả thu hồi quyền.

### 12.1. Bảo vệ dữ liệu và bằng chứng

Audit log nên lưu các định danh và tham chiếu đủ để nối sự kiện, nhưng hạn chế dữ liệu cá nhân không cần thiết. Không ghi **mật khẩu, refresh token, access token đầy đủ, private key hoặc secret** vào log. Bảo vệ log khỏi sửa/xóa trái phép, đồng bộ thời gian giữa hệ thống, đặt retention theo quy định áp dụng và hạn chế truy cập bằng nguyên tắc đặc quyền tối thiểu.

Với sự kiện Mover, cần giữ được **lịch sử role cũ/mới và thời điểm hiệu lực**. Nếu chỉ ghi đè `currentRole` mà không lưu lịch sử, việc điều tra vì sao người dùng có quyền tại một thời điểm trong quá khứ có thể trở nên khó khăn.

## 13. Các lỗi thiết kế phổ biến và cách xử lý

| Lỗi triển khai | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ thêm nhóm của vai trò mới. | Quyền vai trò cũ tích lũy và tạo residual access. | Tính desired state mới, lập danh sách giữ/gỡ/cấp và kiểm chứng. |
| Dùng email làm khóa duy nhất của Mover. | Đổi email có thể tạo account trùng hoặc cập nhật nhầm người. | Dùng identity ID và mapping account có nguồn/phạm vi rõ. |
| Coi job title HR là application role. | Mapping ngữ nghĩa sai; ứng dụng cấp sai quyền. | Dùng business role catalog, policy và entitlement mapping có owner. |
| Không xử lý nhiều assignment đồng thời. | Gỡ quyền còn hợp lệ hoặc giữ quyền đã hết hiệu lực. | Tính quyền từ các assignment đang có hiệu lực và ngoại lệ được duyệt. |
| Cập nhật HR/IdP xong coi mọi đích đã đúng. | Local role, token, session và quyền trực tiếp chưa bị thu hồi. | Provisioning từng target, readback, reconciliation và quản lý phiên khi cần. |
| Không kiểm tra SoD trong giai đoạn giao vai trò. | Người dùng tạm có hai tập quyền xung đột. | Kiểm tra cả quyền cũ/mới, thứ tự gỡ/cấp và giới hạn ngoại lệ. |
| Không phân biệt effective date với recorded date. | Quyền mở quá sớm hoặc thu hồi muộn. | Lịch hóa thao tác theo mốc có hiệu lực, theo dõi độ trễ thực tế. |
| Retry sự kiện cũ làm đảo role mới. | Trạng thái và quyền bị cập nhật ngược. | Idempotency, source version, event ordering và chính sách sửa ngược ngày. |
| Xóa account khi chỉ cần thay đổi entitlement. | Mất dịch vụ, dữ liệu hoặc lịch sử công việc. | Phân biệt account lifecycle và entitlement lifecycle. |
| Không chuyển owner của service account. | Tài khoản dịch vụ mồ côi hoặc credential do người không còn trách nhiệm nắm giữ. | Chuyển owner, rà soát quyền và xử lý secret theo risk. |
| Đóng ticket ngay khi SCIM/API trả thành công. | Không biết quyền thực tế ở target còn tồn dư. | Đòi hỏi readback hoặc kiểm chứng tin cậy trước khi hoàn tất. |
| Không có owner xử lý connector lỗi. | Mover bị treo và quyền thừa tồn tại kéo dài. | Phân công owner, cảnh báo theo rủi ro, retry, remediation và xác minh. |

## 14. Các chỉ số vận hành Mover đáng theo dõi

Không có ngưỡng đo chung phù hợp mọi tổ chức. Các chỉ số cần công bố rõ **phạm vi**, **mẫu số**, **mốc thời gian** và **độ tin cậy của bằng chứng**.

| Chỉ số | Cách đo tham khảo | Ý nghĩa |
| --- | --- | --- |
| **Mover event coverage** | Sự kiện đổi vai trò có workflow IAM liên kết ÷ sự kiện thuộc phạm vi cần xử lý. | Phát hiện thay đổi HR bị bỏ sót. |
| **Verified access-change completion** | Workflow Mover có desired state được xác minh ở mọi target bắt buộc ÷ workflow đã đến hạn. | Tránh nhầm job đã gửi với việc đã cập nhật quyền. |
| **Old-role revocation latency** | Thời gian từ mốc thu hồi theo policy đến lúc quyền cũ được xác minh không còn hiệu lực. | Đo thời gian tồn dư quyền. |
| **SoD exception rate** | Số chuyển vai trò phải xử lý ngoại lệ/xung đột SoD ÷ số sự kiện có kiểm tra SoD. | Theo dõi mức độ rủi ro và chất lượng mô hình role. |
| **Residual entitlement rate** | Số entitlement cũ không còn căn cứ bị phát hiện ÷ tổng entitlement được đối soát trong phạm vi. | Quan sát quyền tồn dư, nhưng phụ thuộc độ bao phủ đối soát. |
| **Provisioning failure remediation** | Tỷ lệ lỗi ở target được xử lý và xác minh theo thời hạn quy định. | Kiểm tra trách nhiệm giải trình và khả năng phục hồi. |
| **Direct-grant visibility** | Tỷ lệ ứng dụng/quyền quan trọng mà IAM có thể phát hiện direct grants. | Đánh giá khả năng nhìn thấy những quyền nằm ngoài mapping nhóm. |

Một tổ chức có thể ghi nhận 99% nhóm đã cập nhật nhưng vẫn gặp rủi ro lớn nếu **1% còn lại là quyền quản trị production**. Việc đánh giá nên phân tầng theo rủi ro, nhất là quyền nhạy cảm và quyền được sử dụng qua phiên/token độc lập.

## 15. Checklist và bài tập thực hành

### 15.1. Checklist trước khi đóng một sự kiện Mover

- [ ] Sự kiện đến từ nguồn có thẩm quyền; identity/employee/assignment binding đã được xác minh.
- [ ] Role cũ, role mới, thời điểm hiệu lực và các nhiệm vụ khác đang còn hiệu lực đã rõ ràng.
- [ ] IAM đã tính **desired access mới**, xác định quyền **giữ / gỡ / cấp** theo từng target.
- [ ] Quyền cần phê duyệt đã được phê duyệt; SoD và privileged access được xử lý.
- [ ] Các ngoại lệ/bàn giao có owner, lý do, scope và thời điểm hết hạn.
- [ ] IdP/Directory, ứng dụng SCIM/API, direct grants và các đường truy cập quan trọng đã được cập nhật.
- [ ] Quyền đặc quyền, session, token, API key và account local đã được đánh giá theo chính sách.
- [ ] Owner của service account/workload có liên quan đã được bàn giao nếu cần.
- [ ] Reconciliation/readback xác minh quyền thực tế khớp chính sách, không còn residual access chưa được xử lý.
- [ ] Bằng chứng audit, owner và kết quả khắc phục được lưu; lỗi chưa giải quyết không bị đánh dấu hoàn tất.

### 15.2. Tình huống A — Chồng lấn vai trò tài chính

Nhân viên từng có quyền **tạo lệnh thanh toán** nay chuyển sang vai trò **duyệt thanh toán**. HR yêu cầu quyền mới có hiệu lực ngay hôm nay, nhưng ứng dụng cũ mất một ngày để thu hồi quyền tạo lệnh. Hãy xác định rủi ro SoD và đề xuất thứ tự gỡ/cấp hoặc kiểm soát thay thế mà vẫn tôn trọng thời điểm hiệu lực.

### 15.3. Tình huống B — SSO đã cập nhật nhưng Git vẫn còn quyền

Một Mover đã được gỡ khỏi IdP group `ops-admins`. Tuy nhiên, trong Git có một **direct role assignment** và personal access token vẫn còn hiệu lực. Hãy chỉ ra ba trạng thái cần kiểm tra riêng: **group membership**, **application entitlement**, **token/phiên**; xác định bằng chứng để kết luận quyền thực tế đã được thu hồi.

### 15.4. Tình huống C — Hai nhiệm vụ đồng thời

Một nhân viên vừa chuyển sang nhóm phân tích dữ liệu vừa tiếp tục hỗ trợ một dự án vận hành có thời hạn 30 ngày. Hãy thiết kế cách biểu diễn **primary business role**, **temporary assignment**, **time-bound entitlement**, owner và lịch rà soát; tránh xóa quyền hợp lệ hoặc giữ quyền vĩnh viễn.

### 15.5. Tình huống D — Chủ sở hữu service account thay đổi

Một kỹ sư chuyển khỏi nhóm nền tảng đang là owner của `batch-reconciliation`. Workload vẫn chạy và phục vụ hệ thống quan trọng. Hãy phân biệt quyền cá nhân phải gỡ, ownership cần chuyển, credential cần rà soát và điều kiện thực sự để deprovision service account.

**Điểm cần ghi nhớ:** Thay đổi vai trò trong Mover lifecycle là quá trình **tính lại quyền dựa trên trách nhiệm hiện tại**, không chỉ cập nhật chức danh trong HRIS hoặc bổ sung nhóm mới. IAM phải biết **quyền nào giữ, quyền nào cấp, quyền nào thu hồi**, kiểm soát SoD và đặc quyền, xử lý thời điểm hiệu lực, đồng bộ đúng qua IdP/SCIM/API, kiểm tra session/token khi liên quan và **đối soát trạng thái thực tế** để giảm quyền truy cập tồn dư. Một sự kiện Mover chỉ có thể được coi là hoàn tất khi các thay đổi bắt buộc đã có bằng chứng thực thi và kiểm chứng phù hợp.
