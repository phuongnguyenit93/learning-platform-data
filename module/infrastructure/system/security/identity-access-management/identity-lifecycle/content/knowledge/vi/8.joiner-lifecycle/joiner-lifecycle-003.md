# Tạo identity mới trong Joiner lifecycle

> **Chương: Joiner lifecycle.** Tạo identity mới là bước thiết lập một bản ghi danh tính đáng tin cậy, có mã định danh ổn định và liên kết với nguồn dữ liệu có thẩm quyền, để từ đó quản lý xác thực, tài khoản và quyền truy cập trong suốt vòng đời. Trong IAM, việc tạo identity là **một quy trình có kiểm soát**, không chỉ là thao tác thêm một dòng User vào cơ sở dữ liệu.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **identity**, hồ sơ nhân sự, User tại IdP, account ở ứng dụng đích, credential và entitlement.
2. Xác định các điều kiện để tạo danh tính mới: sự kiện Joiner hợp lệ, xác minh nguồn, identity proofing, đối sánh chống trùng và phê duyệt theo chính sách.
3. Thiết kế khóa định danh bền vững, ánh xạ đa hệ thống và trạng thái vòng đời của identity.
4. Mô tả luồng tạo identity tại kho IAM, cấp phát tài khoản qua IdP/SCIM, thiết lập SSO và gán quyền ban đầu theo RBAC/ABAC.
5. Xử lý sự kiện trùng, đến sai thứ tự, provisioning lỗi một phần, tài khoản tồn tại từ trước và quyền truy cập dư thừa.
6. Xây dựng tiêu chí hoàn thành, kiểm tra readback, kiểm toán và khả năng chuyển tiếp sang Mover–Leaver.

## 1. Vì sao phải tạo identity trước khi cấp quyền?

Giả sử doanh nghiệp tuyển **Minh** vào nhóm phát triển phần mềm. Minh cần email, công cụ mã nguồn, kho tài liệu và một số môi trường thử nghiệm. Cách làm thiếu kiểm soát là mỗi hệ thống tự tạo tài khoản từ một email được gửi qua chat. Hậu quả có thể gồm tài khoản trùng, người khác được cấp nhầm quyền, không có owner để thu hồi khi Minh nghỉ việc, hoặc một tài khoản cũ được mở lại với đặc quyền cao.

Trong mô hình **Identity and Access Management (IAM)**, cần thiết lập một danh tính chính thức để trả lời:

- **Đây là ai?** Có sự kiện từ hệ thống nhân sự hoặc nguồn được ủy quyền xác nhận mối quan hệ hợp lệ hay không?
- **Danh tính này đã tồn tại chưa?** Một nhân viên từng là nhà thầu hoặc từng nghỉ việc có thể đã có hồ sơ liên kết trước đó.
- **Bằng chứng xác minh đủ chưa?** Identity proofing có đáp ứng mức bảo đảm theo rủi ro và chính sách không?
- **Danh tính được nhận diện bền vững bằng mã nào?** Có thể truy vết dù người đó đổi tên, email, phòng ban hoặc tài khoản ứng dụng?
- **Phải tạo tài khoản nào và cấp quyền gì?** Quyền có đúng chức năng, phạm vi, thời hạn và phê duyệt?
- **Ai chịu trách nhiệm và làm sao biết việc tạo đã thành công?** Có owner, nguồn dữ liệu, trạng thái thực tế và nhật ký kiểm toán?

Đầu ra mong muốn không đơn thuần là “tạo user thành công”, mà là **identity được xác lập đúng người, được quản trị bằng chính sách và có đường đi rõ ràng tới các tài khoản cũng như quyền truy cập**.

### Sáu đối tượng liên quan

| Đối tượng | Vai trò | Ví dụ trong quá trình Joiner |
| --- | --- | --- |
| **Person / workforce record** | Hồ sơ con người và quan hệ lao động tại nguồn HR. | EMP-2041, ngày bắt đầu, loại hợp đồng, đơn vị. |
| **Identity** | Biểu diễn danh tính trong IAM, có khóa nội bộ và liên kết nguồn. | ID-8F31 đại diện cho Minh. |
| **IdP User** | Bản ghi phục vụ xác thực, nhóm và chính sách đăng nhập. | User của Minh tại hệ thống nhận dạng doanh nghiệp. |
| **Application account** | Tài khoản trong một ứng dụng cụ thể. | Tài khoản Git, CRM hoặc SaaS. |
| **Credential / authenticator** | Yếu tố cho phép chứng minh quyền kiểm soát tài khoản. | Passkey, mật khẩu ban đầu, khóa phần cứng. |
| **Entitlement** | Vai trò, nhóm, quyền hoặc đặc quyền được gán. | DeveloperReader tại dự án A. |

**Một identity có thể liên kết nhiều account.** Việc tạo identity không tự tạo tài khoản ở mọi ứng dụng. Ngược lại, một account cục bộ tồn tại không chứng minh rằng nó đã được gắn đúng với người trong HR.

## 2. Điều kiện đầu vào của Joiner

Tạo identity nên bắt đầu từ **sự kiện hợp lệ của nguồn có thẩm quyền**: HRIS/HCM đối với nhân viên, hệ thống hợp đồng đối với nhà thầu, quy trình đăng ký được phê duyệt đối với đối tác, hoặc hệ thống đăng ký workload đối với danh tính máy.

| Dữ liệu đầu vào | Mục đích | Kiểm tra tối thiểu |
| --- | --- | --- |
| **Source system + source ID** | Xác định chủ thể trong đúng hệ thống nguồn. | Nguồn được tin cậy, ID hiện hữu, có namespace. |
| **Loại quan hệ** | Phân biệt nhân viên, nhà thầu, đối tác hoặc workload. | Đúng quy trình proofing, owner và thời hạn. |
| **Trạng thái và ngày hiệu lực** | Ngăn cấp quyền quá sớm hoặc sau khi hết nhu cầu. | Joiner được duyệt; thời gian hợp lệ và nhất quán. |
| **Thuộc tính tổ chức** | Làm đầu vào cho vai trò, phạm vi và người phê duyệt. | Phòng ban, chức danh, manager/sponsor được xác minh. |
| **Kết quả proofing** | Bảo đảm danh tính khai báo được liên kết đúng chủ thể. | Phương thức, kết quả, thời điểm, mức bảo đảm theo chính sách. |
| **Đối tượng ứng dụng cần dùng** | Xác định tài khoản và quyền cần cấp. | Có yêu cầu công việc và owner tài nguyên. |
| **Sự kiện/correlation ID** | Chống xử lý trùng và truy vết toàn luồng. | ID sự kiện, phiên bản nguồn hoặc mốc hiệu lực. |

Không nên lấy một email không xác minh hoặc một form tự điền làm căn cứ duy nhất để cấp quyền nhân viên. **Nguồn có thẩm quyền về trạng thái làm việc** và **bằng chứng identity proofing** có thể do hai hệ thống khác nhau cung cấp; cả hai phải được kiểm tra theo chính sách.

### Joiner diễn ra trước ngày đi làm

Doanh nghiệp thường cần chuẩn bị trước: tạo identity ở trạng thái chờ, đặt lịch provisioning hoặc gửi thông tin thiết lập xác thực. Cần phân biệt:

- **Được phép chuẩn bị:** tạo bản ghi identity, kiểm tra dữ liệu, đăng ký yêu cầu và lên lịch cấp phát.
- **Được phép kích hoạt:** bật đăng nhập và quyền truy cập chỉ từ thời điểm được chính sách cho phép, có thể phụ thuộc ngày bắt đầu hợp đồng và hoàn tất proofing.
- **Được phép truy cập tài nguyên nhạy cảm:** còn phụ thuộc MFA, phê duyệt, vai trò, điều kiện truy cập và chính sách ứng dụng.

Tránh dùng một cờ “account created” để suy ra cả ba điều trên đã thành công.

## 3. Xác minh danh tính và phát hiện hồ sơ đã tồn tại

Trước khi tạo identity, phải kiểm tra nguy cơ **identity duplicate** và **account misbinding**.

Một nhân sự có thể quay lại làm việc, chuyển từ nhà thầu sang chính thức hoặc đồng thời có nhiều quan hệ hợp đồng. Nếu mỗi sự kiện đều tạo identity mới, hệ thống sẽ phân tán quyền, khó đối soát và dễ bỏ sót khi Leaver.

### Chiến lược đối sánh có kiểm soát

1. Xác định **khóa nguồn có phạm vi rõ ràng**, ví dụ cặp (HRIS-A, EMP-2041), không lấy EMP-2041 đơn lẻ nếu nhiều nguồn có thể dùng cùng giá trị.
2. Tra cứu bảng liên kết nguồn → identityId để nhận biết quan hệ đã đăng ký.
3. Kiểm tra trạng thái: identity đang hoạt động, đã vô hiệu hóa, đang chờ hay đã hợp nhất theo quyết định trước đó.
4. Khi có dấu hiệu cùng người nhưng khóa nguồn mới, dùng quy trình **identity resolution** có bằng chứng, tránh gộp tự động chỉ vì trùng họ tên, số điện thoại hoặc email.
5. Xác minh identity proofing và mức độ tin cậy cần thiết trước khi liên kết tài khoản có quyền.
6. Ghi nhận quyết định: **CREATE_NEW**, **LINK_EXISTING** hoặc **REVIEW_REQUIRED** kèm cơ sở và người chịu trách nhiệm.

**Không nên tái sử dụng định danh bị giải phóng cho người khác.** Email hoặc username có thể đổi hoặc được cấp lại; identityId và khóa liên kết có thể được thiết kế bất biến để giữ khả năng truy vết.

### Ví dụ: nhân viên được tuyển lại

Minh từng có tài khoản với email minh@example.org, nghỉ việc và quay lại sau hai năm. Quy trình nhận sự kiện HR mới nhưng phát hiện một identity cũ có cùng tên và email.

- Nếu nguồn có cơ sở xác nhận đó là **cùng người**, cần xử lý quan hệ tái tuyển dụng theo chính sách và đánh giá lại proofing.
- Nếu không đủ chắc chắn, phải chuyển review; **không tự kích hoạt lại** tài khoản cũ hoặc chuyển quyền từ hồ sơ cũ.
- Dù cùng người, quyền cũ vẫn phải được tính lại từ công việc hiện tại. Không tự khôi phục nhóm quản trị hay các quyền đặc quyền trước đây.

## 4. Thiết kế mã định danh và mô hình dữ liệu identity

Để một identity sống được qua Joiner–Mover–Leaver, nên tách **mã danh tính nội bộ ổn định** khỏi những thuộc tính có thể đổi.

| Trường dữ liệu khái niệm | Ví dụ | Ghi chú thiết kế |
| --- | --- | --- |
| identityId | ID-8F31 | Khóa IAM nội bộ; tránh gắn ý nghĩa thay đổi theo thời gian. |
| sourceAuthority | HRIS-A | Tên/namespace nguồn cấp quan hệ. |
| sourcePersonId | EMP-2041 | Khóa từ nguồn; cần đi kèm sourceAuthority. |
| identityType | EMPLOYEE | Chọn quy trình phù hợp loại danh tính. |
| lifecycleState | PENDING_ACTIVATION | Trạng thái được quản lý bằng chuyển trạng thái có kiểm soát. |
| startAt, endAt | Theo sự kiện nguồn | Thời điểm hiệu lực cho kích hoạt và thu hồi. |
| department, managerRef | Engineering, ID-MGR21 | Thuộc tính tổ chức có nguồn, phiên bản và thời điểm cập nhật. |
| proofingStatus, proofingRef | VERIFIED, CASE-102 | Tham chiếu kết quả, không tự sao chép toàn bộ bằng chứng nhạy cảm. |
| linkedAccounts | IdP, Git, CRM | Lưu ánh xạ identity ↔ local account ID tại từng đích. |
| desiredEntitlements | DeveloperReader | Quyền mong muốn theo chính sách; phân biệt quyền thực tế. |

Mô hình JSON minh họa của lớp IAM:

~~~json
{
  "identityId": "ID-8F31",
  "type": "EMPLOYEE",
  "source": {
    "authority": "HRIS-A",
    "personId": "EMP-2041",
    "eventVersion": 37
  },
  "lifecycle": {
    "state": "PENDING_ACTIVATION",
    "startAt": "2026-12-01T08:00:00+07:00",
    "endAt": null
  },
  "proofing": {
    "status": "VERIFIED",
    "evidenceRef": "CASE-102"
  },
  "organization": {
    "department": "ENGINEERING",
    "managerIdentityId": "ID-MGR21"
  },
  "desiredEntitlements": [
    {
      "resource": "CODE_REPOSITORY",
      "role": "DeveloperReader",
      "scope": "project-a"
    }
  ],
  "linkedAccounts": []
}
~~~

**Đây là schema minh họa, không phải định dạng chuẩn của SCIM hoặc giao thức OIDC.** Trong triển khai thật cần phân quyền đọc/ghi thuộc tính, xử lý dữ liệu cá nhân, định danh tenant và mô hình hóa lịch sử thay đổi.

### Vì sao email không nên là khóa chính?

Email có thể đổi theo tên, tên miền, yêu cầu bảo mật hoặc cơ cấu tổ chức; cũng có thể được tái sử dụng. Một bản ghi liên kết chỉ bằng email có thể gây **account takeover** hoặc cấp quyền sai chủ thể khi email được tái cấp.

Nên duy trì bảng ánh xạ có namespace:

| Identity IAM | Hệ thống đích | Local account ID | Trạng thái |
| --- | --- | --- | --- |
| ID-8F31 | Corporate IdP | idp-u728 | ENABLED |
| ID-8F31 | Code repository | git-u310 | ACTIVE |
| ID-8F31 | Issue tracker | issue-u095 | PENDING |

Khi identity chuyển bộ phận hoặc Leaver, hệ thống biết phải điều chỉnh tài khoản nào mà không cần đoán qua tên hoặc email.

## 5. Quy trình tạo identity mới theo từng giai đoạn

~~~mermaid
flowchart TD
    A["Nguồn có thẩm quyền phát Joiner<br/>ID, loại quan hệ, ngày hiệu lực"] --> B["Validate nguồn, schema,<br/>chữ ký/quyền truy cập và trạng thái"]
    B --> C["Tìm identity hiện có<br/>và kiểm tra trùng/liên kết"]
    C --> D{"Quyết định identity"}
    D -->|Đã tồn tại hợp lệ| E["Liên kết/tiếp tục quy trình<br/>theo chính sách"]
    D -->|Có mâu thuẫn| X["REVIEW_REQUIRED<br/>không tự cấp quyền"]
    D -->|Tạo mới| F["Kiểm tra kết quả proofing<br/>và yêu cầu bảo đảm"]
    F --> G["Tạo identityId ổn định<br/>ghi trạng thái, nguồn, owner"]
    E --> H["Tính quyền mong muốn<br/>RBAC/ABAC, phê duyệt, hiệu lực"]
    G --> H
    H --> I["Provision IdP User và<br/>ứng dụng đích qua SCIM/API"]
    I --> J["Thiết lập xác thực, MFA,<br/>SSO và chính sách đăng nhập"]
    J --> K["Readback từng đích:<br/>account, role, trạng thái"]
    K --> L{"Đúng quyền và<br/>đúng thời điểm?"}
    L -->|Có| M["READY/ACTIVE theo chính sách<br/>lưu audit và correlation ID"]
    L -->|Chưa| N["PARTIAL/FAILED<br/>retry, cảnh báo, đối soát"]
    N --> K
~~~

Quy trình trên chỉ là kiến trúc tham khảo. Trên thực tế, việc thiết lập authenticator có thể diễn ra trước hoặc sau khi tạo account ở từng ứng dụng; một số ứng dụng cấp account theo lần đăng nhập đầu tiên, số khác dùng SCIM hoặc connector. **Tiêu chí hoàn thành dựa trên trạng thái thực tế**, không dựa trên thứ tự gọi API cố định.

### Bước 1 — Tiếp nhận và xác thực sự kiện Joiner

Chỉ chấp nhận sự kiện từ nguồn đã được ủy quyền. Kiểm tra ID của sự kiện, phiên bản/timestamp nghiệp vụ, chủ thể, loại quan hệ, ngày hiệu lực và trạng thái. Sự kiện chưa đủ thông tin cần đi vào luồng xử lý có trạng thái thay vì tạo một identity “tạm đoán”.

### Bước 2 — Đối sánh danh tính và kiểm tra proofing

Tìm identity liên quan từ khóa nguồn đã được chuẩn hóa; đánh giá nguy cơ trùng, rehire, thay đổi loại hợp đồng hoặc dữ liệu mâu thuẫn. Kết quả identity proofing phải gắn với đúng người và đáp ứng yêu cầu tin cậy của quy trình. **MFA không thay thế proofing**, vì MFA xác thực quyền kiểm soát authenticator còn proofing xác minh liên kết danh tính ban đầu.

### Bước 3 — Tạo identity chính thức

Khi đủ điều kiện, phát sinh identityId ổn định, ghi liên kết nguồn, loại identity, trạng thái, mốc hiệu lực, thông tin tổ chức và tham chiếu bằng chứng. Ghi nhận quyền ghi từng trường: HR sở hữu dữ liệu công việc, IAM quản lý trạng thái identity, hệ thống proofing sở hữu kết quả xác minh.

Một giao dịch tạo identity cần có cơ chế chống trùng theo khóa nguồn. Ví dụ, cùng sự kiện Joiner được gửi hai lần không được tạo hai identityId khác nhau.

### Bước 4 — Xác định quyền nền theo công việc

Áp dụng **least privilege** cho nhóm quyền có thể cấp mặc định (birthright access). Nên phân biệt:

- **Quyền nền:** quyền thực sự cần cho một vai trò hoặc loại nhân sự, với phạm vi mặc định hợp lý.
- **Quyền có điều kiện:** chỉ cấp khi có thuộc tính đáp ứng chính sách, ví dụ department, tenant hoặc dự án cụ thể.
- **Quyền cần phê duyệt:** quyền nhạy cảm cần manager, resource owner hoặc cơ chế kiểm soát độc lập.
- **Đặc quyền cao:** có thể yêu cầu PAM, MFA nâng cao, JIT, giới hạn phiên và kiểm tra SoD.

Quyền cần được mô tả theo **chủ thể + hành động + tài nguyên + phạm vi + điều kiện + thời hạn**. Ví dụ, DeveloperReader tại project-a không có nghĩa được quyền ghi vào mọi kho mã nguồn của tổ chức.

### Bước 5 — Provisioning tại IdP và ứng dụng

IdP thường quản lý User phục vụ xác thực; **SSO** giúp đăng nhập vào nhiều ứng dụng liên kết, còn **SCIM** hoặc API provisioning giúp tạo/cập nhật User và nhóm ở hệ thống đích. Ba việc này bổ sung cho nhau nhưng có vai trò khác nhau:

| Công nghệ | Công việc liên quan đến identity mới | Điều không được suy ra |
| --- | --- | --- |
| **IdP** | Tạo User, thiết lập chính sách xác thực, MFA, nhóm và thuộc tính. | Mọi app đã có account hoặc mọi quyền nghiệp vụ đã đúng. |
| **SSO / OIDC / SAML** | Liên kết đăng nhập giữa IdP và ứng dụng tin cậy. | Tự tạo toàn bộ User đích hoặc thu hồi tất cả quyền cục bộ. |
| **SCIM** | Trao đổi dữ liệu User/Group, tạo, cập nhật, vô hiệu hóa tùy khả năng hệ thống. | Tự xác minh danh tính người hoặc quản lý mọi session/token. |
| **RBAC/ABAC** | Quyết định quyền theo vai trò, thuộc tính và điều kiện. | Role tồn tại nghĩa là được phép truy cập mọi tenant/tài nguyên. |
| **IGA / workflow** | Yêu cầu, duyệt, rà soát và đối soát quyền. | Phê duyệt trong workflow đồng nghĩa app đích đã áp dụng quyền. |

Tài khoản có thể được tạo trước nhưng chưa được phép đăng nhập. Cần ghi **kết quả từng đích** cùng mã local account ID và trạng thái thực tế.

### Bước 6 — Kích hoạt an toàn

Tại thời điểm được phép:

1. Xác minh trạng thái quan hệ công việc, kết quả proofing và điều kiện cấp truy cập.
2. Cho người dùng đăng ký authenticator an toàn, thiết lập MFA/SSO theo chính sách và bảo vệ luồng khôi phục.
3. Kích hoạt User hoặc access policy phù hợp, không gửi credential bí mật qua kênh thiếu kiểm soát.
4. Kiểm tra đăng nhập bằng cơ chế hợp lệ nếu cần, đồng thời kiểm tra quyền tại API/tài nguyên thực tế.
5. Ghi kết quả provisioning và readback; thông báo vấn đề cho owner khi hệ thống đích chưa sẵn sàng.

### Bước 7 — Xác minh, kiểm toán và bàn giao vòng đời

Một identity chỉ nên được coi là **READY** khi các điều kiện bắt buộc của Joiner đã đạt. Quyền và tài khoản không bắt buộc có thể tiếp tục xử lý trong trạng thái theo dõi; không đánh dấu “hoàn tất mọi ứng dụng” khi chỉ có IdP thành công.

Ghi lại identityId, source person ID, sự kiện Joiner, bằng chứng proofing theo tham chiếu, các quyết định cấp quyền, local account IDs, người phê duyệt, thời điểm hiệu lực và kết quả đối soát. Sau đó lifecycle engine phải tiếp tục nhận Mover/Leaver theo cùng liên kết nguồn.

## 6. State machine: identity được tạo khác identity đã sẵn sàng truy cập

Một mô hình trạng thái minh họa:

| Trạng thái | Ý nghĩa | Quyền/hoạt động phù hợp |
| --- | --- | --- |
| **RECEIVED** | Đã nhận sự kiện Joiner. | Chưa cấp truy cập; đang kiểm tra đầu vào. |
| **IDENTITY_REVIEW_REQUIRED** | Dữ liệu trùng, sai hoặc proofing chưa đủ. | Chờ xác minh; chặn cấp quyền nhạy cảm tự động. |
| **IDENTITY_CREATED** | Đã tạo identityId, mapping nguồn và metadata nền. | Chưa suy ra IdP/app đã có tài khoản. |
| **PROVISIONING** | Đang tạo hoặc cập nhật tài khoản và quyền. | Theo dõi trạng thái riêng của từng đích. |
| **PENDING_ACTIVATION** | Tài khoản đã chuẩn bị nhưng chưa đến hiệu lực hoặc còn bước xác thực. | Giữ giới hạn truy cập trước ngày hiệu lực. |
| **READY / ACTIVE** | Các điều kiện bắt buộc được xác minh và trạng thái truy cập hợp lệ. | Được đăng nhập và dùng quyền trong phạm vi chính sách. |
| **PARTIAL_FAILURE** | Có đích lỗi hoặc trạng thái không khớp. | Retry, cảnh báo, đối soát; không tuyên bố hoàn tất. |
| **SUSPENDED** | Có yêu cầu hạn chế truy cập theo chính sách. | Xử lý sự cố hoặc điều kiện chưa đáp ứng. |

Đây là **tên trạng thái mang tính thiết kế**, không phải schema bắt buộc của IdP/SCIM. Trong thực tế cần quy định chuyển trạng thái hợp lệ, khả năng retry, owner xử lý lỗi, thứ tự sự kiện và **ngày hiệu lực**. Một identity có thể đã được tạo mà account chưa sẵn sàng; một account đã provision cũng có thể chưa được phép kích hoạt.

## 7. Chống trùng, xử lý retry và lỗi một phần

### Sự kiện Joiner được gửi lặp lại

Webhook từ HR hoặc hàng đợi sự kiện thường có thể gửi lại khi timeout. Nếu mỗi lần đều tạo account mới, hệ thống sẽ sinh danh tính và quyền trùng.

Nên dùng **idempotency** theo tổ hợp nguồn + subject ID + event ID hoặc phiên bản sự kiện, kết hợp ràng buộc duy nhất cho mapping nguồn. Không được coi một yêu cầu có response timeout là thất bại chắc chắn: phải **kiểm tra trạng thái thực tế** trước khi thử tạo lại.

Pseudocode khái niệm:

~~~text
processJoiner(event):
    assert trustedSource(event.source)
    assert validEffectiveDates(event)

    if alreadyProcessed(event.id, event.version):
        return previousOutcome(event.id)

    identity = findBySourceKey(event.source, event.subjectId)
    if identity is ambiguous:
        createReviewCase(event)
        return IDENTITY_REVIEW_REQUIRED

    if identity is absent:
        assert proofingRequirementSatisfied(event.subjectId)
        identity = createWithUniqueSourceMapping(event)

    desired = calculateEntitlements(identity, policy, approvals)
    results = reconcileTargets(identity, desired)
    recordAudit(event, identity, desired, results)

    if mandatoryTargetsVerified(results) and activationAllowed(identity):
        return READY
    return PARTIAL_FAILURE_OR_PENDING
~~~

Đoạn mã minh họa tư duy, chưa bao gồm chi tiết transaction, khóa đồng thời, security controls và cú pháp của nền tảng cụ thể.

### IdP thành công nhưng ứng dụng đích thất bại

Ví dụ IAM tạo IdP User thành công và gửi SCIM tạo account trong Git, nhưng Git trả lỗi tạm thời. Khi đó:

- Giữ lại identity và mapping tới IdP User đã được tạo, tránh tạo ID mới.
- Đánh dấu Git ở trạng thái thất bại hoặc đang chờ, lưu correlation ID và nguyên nhân kỹ thuật phù hợp.
- Retry theo chính sách có backoff và chống trùng, kiểm tra khả năng account đã tồn tại trước khi POST lần nữa.
- Đối chiếu desired state với observed state; không gắn READY cho khả năng sử dụng Git nếu chưa được xác minh.
- Báo cho owner nếu quá hạn phục hồi; áp dụng cơ chế rollback/compensation khi chính sách yêu cầu và khi có thể làm an toàn.

**Không nên xóa toàn bộ identity chỉ vì một ứng dụng đích tạm thời lỗi.** Nếu phải hoàn tác, cần định nghĩa rõ tài nguyên nào mới tạo, quyền nào đã có từ trước và cách thu hồi an toàn để không ảnh hưởng tài khoản hợp lệ.

### Account đã tồn tại tại ứng dụng đích

Khi provisioning phát hiện một username/email đã tồn tại, không nên tự gắn account đó vào identity mới. Trước hết phải xác minh:

- Account hiện có thuộc cùng người và cùng tổ chức/tenant hay không.
- Có mapping nguồn hoặc lịch sử liên kết đáng tin cậy không.
- Quyền hiện tại, credential và trạng thái account có được phép kế thừa không.
- Tài khoản có phải một identity cũ, account cục bộ ngoại lệ hay của người khác không.

Nếu mâu thuẫn, đưa vào **manual review**, tránh nhầm quyền hoặc takeover.

### Sự kiện đến không đúng thứ tự

Một Mover hoặc Leaver có hiệu lực có thể đến trước khi retry của Joiner hoàn thành. Workflow phải so sánh phiên bản và thời điểm hiệu lực của nguồn để không kích hoạt lại quyền cũ sau khi nhân viên đã chuyển vai trò hoặc rời tổ chức.

Ví dụ, nếu Leaver đã có hiệu lực thì job retry Joiner không được tự bật lại User chỉ vì nhìn thấy một provisioning task tồn đọng. Nên sử dụng **trạng thái vòng đời mới nhất** trong mọi lần đánh giá quyền và thực hiện đối soát định kỳ.

## 8. Tài khoản dịch vụ, nhà thầu và trường hợp đặc biệt

### Nhà thầu, người ngoài tổ chức

Nhà thầu có thể không có hồ sơ nhân viên chính thức trong HR, nhưng vẫn cần một **source of authority**, sponsor/owner, loại quan hệ, ngày hết hạn và mức proofing phù hợp. Quyền nền thường cần hạn chế hơn và gắn với phạm vi dự án, thời gian hợp đồng.

Không nên tự động đặt thời hạn vô hạn chỉ vì nguồn nhà thầu không cung cấp endAt. Khi thiếu thông tin quan trọng, cần workflow xác minh hoặc dùng chính sách giới hạn thời gian và gia hạn có phê duyệt.

### Service account và workload identity

Đối với danh tính máy, quá trình tạo identity khác với proofing con người:

| Thành phần | Identity của con người | Identity của workload |
| --- | --- | --- |
| Nguồn tạo | HR, đối tác, quy trình đăng ký người dùng. | Hệ thống đăng ký dịch vụ/workload, CI/CD hoặc hạ tầng có thẩm quyền. |
| Bước xác minh | Identity proofing theo rủi ro. | Xác nhận dịch vụ tồn tại, owner, nguồn triển khai và trust relationship. |
| Phương thức xác thực | Passkey, MFA, SSO theo chính sách. | Workload federation, chứng chỉ/token ngắn hạn khi hỗ trợ. |
| Quyền mặc định | Theo nhiệm vụ, vai trò, phạm vi dữ liệu. | Theo service, môi trường, API và tài nguyên cụ thể. |
| Sự kiện hết vòng đời | Mover/Leaver, hợp đồng kết thúc. | Service decommission, đổi owner, khóa trust, hết dự án. |

**Không nên tạo service account chung cho nhiều job** nếu có thể tách thành danh tính máy riêng. Mỗi identity workload phải có owner, purpose, phạm vi quyền, thời hạn hoặc điều kiện tồn tại, cách xoay vòng/thu hồi credential và khả năng kiểm toán.

### Tài khoản quản trị và break-glass

Một người có thể có identity chính và account quản trị riêng được liên kết cùng người chịu trách nhiệm. Tuy nhiên, **tạo identity nhân viên không mặc nhiên cấp quyền admin**. Quyền quản trị cần phê duyệt, kiểm soát SoD, PAM/JIT, MFA phù hợp và giới hạn thời hạn hoặc phiên khi khả thi.

Tài khoản khẩn cấp (break-glass) là ngoại lệ có chính sách và owner rõ ràng; cần giám sát đặc biệt, thử nghiệm được kiểm soát và rà soát sau sử dụng.

## 9. Kiểm soát bảo mật và kiểm toán quá trình tạo identity

### Những rủi ro cần theo dõi

| Rủi ro | Dấu hiệu điển hình | Biện pháp kiểm soát |
| --- | --- | --- |
| **Tạo nhầm người** | Hai người trùng tên/email, account cũ bị gán nhầm. | Khóa nguồn ổn định, proofing, identity resolution có kiểm soát. |
| **Danh tính trùng** | Nhiều identityId cho cùng mã nguồn. | Ràng buộc duy nhất, idempotency và đối soát. |
| **Tạo sớm và cấp quyền sớm** | Account có hiệu lực trước ngày bắt đầu. | Trạng thái pending và kiểm soát activation theo thời gian. |
| **Quyền ban đầu quá rộng** | Nhân viên mới mặc định có quyền admin hoặc wildcard. | RBAC/ABAC, least privilege, phê duyệt đặc quyền. |
| **Provisioning thất bại một phần** | IdP thành công nhưng ứng dụng chưa có User hoặc quyền sai. | Trạng thái từng đích, retry, readback và cảnh báo. |
| **Dữ liệu nguồn lỗi thời** | Joiner được kích hoạt sau Mover/Leaver. | Version, effective date, kiểm tra trạng thái mới nhất. |
| **Credential được giao không an toàn** | Mật khẩu ban đầu xuất hiện trong email/log/ticket. | Enrollment an toàn, quản lý bí mật và giảm dữ liệu log. |
| **Không rõ owner** | Account tồn tại nhưng không ai chịu trách nhiệm. | Bắt buộc manager/sponsor/service owner phù hợp. |

### Bằng chứng kiểm toán tối thiểu

Một log hoặc hồ sơ case nên lưu:

1. **Identity và nguồn:** identityId, source authority, source subject ID, loại danh tính.
2. **Nguồn sự kiện:** event ID, version/correlation ID, thời điểm nhận và thời điểm hiệu lực.
3. **Kết quả kiểm tra:** proofing status/reference, đối sánh trùng, quyết định create/link/review.
4. **Quyền và phê duyệt:** role, scope, thời hạn, policy version, người yêu cầu/người duyệt.
5. **Kết quả provisioning:** tên hệ thống, local account ID, operation, trạng thái, lỗi và readback.
6. **Vòng đời sau tạo:** owner, thời hạn hợp đồng, lịch rà soát và dữ liệu cần dùng cho Mover/Leaver.

Không đưa mật khẩu, secret, private key, token đầy đủ hoặc bản sao giấy tờ không cần thiết vào log. Cần phân quyền đọc nhật ký, bảo vệ tính toàn vẹn, đặt thời hạn lưu giữ và tuân theo chính sách bảo vệ dữ liệu cá nhân.

### Chỉ số vận hành hữu ích

| Chỉ số | Ý nghĩa |
| --- | --- |
| Thời gian từ Joiner hợp lệ đến identity được tạo | Đánh giá tốc độ thiết lập danh tính nền. |
| Thời gian đến khi các ứng dụng bắt buộc READY | Đánh giá khả năng onboarding thực tế. |
| Số hồ sơ CREATE/REVIEW vì trùng hoặc mapping sai | Phát hiện chất lượng dữ liệu nguồn và khả năng identity resolution. |
| Tỷ lệ provisioning lỗi theo từng đích | Phát hiện connector/SCIM/API không ổn định. |
| Số tài khoản được kích hoạt trước hiệu lực | Đánh giá kiểm soát ngày bắt đầu. |
| Số quyền ban đầu không có căn cứ hoặc phê duyệt | Phát hiện overprovisioning. |
| Tỷ lệ account không có mapping tới identity | Phát hiện tài khoản mồ côi hoặc tạo ngoài luồng. |

## 10. Ví dụ xuyên suốt: tạo identity cho nhân viên mới

**Bối cảnh:** Minh bắt đầu công việc ở nhóm Engineering ngày 01/12. Nguồn HR cấp employeeId EMP-2041, manager đã được xác minh. Minh cần email, Git và issue tracker, nhưng chỉ được quyền đọc repository project-a lúc đầu.

**Trình tự xử lý:**

1. HR phát Joiner với source key HRIS-A:EMP-2041, ngày hiệu lực và phiên bản sự kiện.
2. IAM kiểm tra proofing, tra mapping nguồn, xác nhận không có identity hiện hữu hoặc case trùng chưa giải quyết.
3. IAM tạo ID-8F31 ở trạng thái PENDING_ACTIVATION, gắn source key và owner.
4. Policy engine tính role DeveloperReader trong phạm vi project-a, không tự cấp quyền viết production.
5. IdP tạo User, thiết lập chính sách đăng nhập/MFA, lưu local IdP User ID.
6. SCIM/connector tạo hoặc liên kết Git User và issue tracker account khi được phép, kiểm tra đúng local ID.
7. Vào thời điểm hợp lệ, Minh đăng ký authenticator và đăng nhập qua SSO; ứng dụng kiểm tra role và project scope.
8. IAM đọc lại trạng thái từng hệ thống; Git hoàn tất còn issue tracker báo lỗi tạm thời. Quy trình giữ trạng thái chưa hoàn chỉnh đối với issue tracker, mở retry và báo owner.
9. Khi issue tracker đã đối soát thành công, IAM ghi dấu READY cho các ứng dụng bắt buộc, lưu bằng chứng.

**Sự kiện tương lai:** Sau sáu tháng Minh chuyển sang nhóm tài chính. IAM sử dụng **cùng identityId** để tính lại quyền, gỡ quyền Engineering không còn cần thiết và cấp quyền mới theo phê duyệt. Khi Minh nghỉ việc, hệ thống có thể lần theo mapping để thu hồi toàn bộ account, quyền, token và credential còn hiệu lực theo khả năng của từng đích.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Có một email mới trong danh sách onboarding. Có đủ căn cứ tạo identity nhân viên chính thức và cấp quyền mặc định chưa?

*Gợi ý:* Chưa. Cần kiểm tra nguồn có thẩm quyền, mã nguồn/quan hệ công việc, kết quả proofing, đối sánh chống trùng và chính sách ngày hiệu lực.

**Câu 2.** Vì sao phải tách identityId khỏi email và applicationUserId?

*Gợi ý:* Email có thể đổi/tái sử dụng, mã User của mỗi ứng dụng có namespace riêng. IdentityId ổn định giúp liên kết tài khoản, truy vết và xử lý Mover/Leaver.

**Câu 3.** HR gửi sự kiện Joiner hai lần vì timeout. IAM nên xử lý thế nào?

*Gợi ý:* Idempotency theo nguồn + subject + event, khóa duy nhất cho mapping, kiểm tra trạng thái thực tế và trả kết quả trước đó khi phù hợp, tránh tạo hai danh tính.

**Câu 4.** IdP đã tạo User nhưng SCIM provisioning vào Git thất bại. Có nên báo toàn bộ onboarding hoàn thành không?

*Gợi ý:* Không. Theo dõi kết quả riêng từng ứng dụng, retry có kiểm soát, readback và cảnh báo. Giữ identity và tài khoản đã tạo hợp lệ, tránh tạo trùng.

**Câu 5.** Một nhân viên tái tuyển dụng có cùng email với tài khoản cũ. Có nên bật lại toàn bộ quyền trước đây?

*Gợi ý:* Không. Xác minh liên kết danh tính, proofing khi cần; tính quyền theo vai trò mới, thu hồi/không khôi phục quyền dư thừa.

**Câu 6.** Nếu Joiner vẫn còn job retry khi Leaver đã có hiệu lực, hệ thống phải làm gì?

*Gợi ý:* Tôn trọng trạng thái vòng đời mới nhất và ngày hiệu lực, không để retry cũ tái kích hoạt quyền; đối soát tất cả đích.

**Câu 7.** Tạo identity cho service account có cần bước chụp giấy tờ của “người dùng” không?

*Gợi ý:* Không áp dụng proofing con người máy móc. Cần xác minh workload, hệ thống nguồn, owner, phạm vi quyền, credential và vòng đời dịch vụ.

## Ghi nhớ

- **Tạo identity mới** thiết lập bản ghi danh tính có nguồn, bằng chứng, mã định danh ổn định, owner và trạng thái vòng đời; khác với việc đơn thuần thêm tài khoản ở ứng dụng.
- Trước khi tạo phải kiểm tra **nguồn Joiner hợp lệ, identity proofing và chống trùng**. Người tái tuyển dụng hoặc thay đổi loại hợp đồng không tự được cấp lại các quyền cũ.
- **IdP/SSO** phục vụ xác thực và đăng nhập liên thông; **SCIM/connector** hỗ trợ cấp phát tài khoản/nhóm; **RBAC/ABAC** và quy trình phê duyệt quyết định quyền phù hợp.
- **Quyền nền cần tối thiểu và có thời hạn/phạm vi hợp lý**. Account đã tạo chưa đồng nghĩa đã được phép kích hoạt hoặc đã provision thành công mọi đích.
- Thiết kế **idempotency, kiểm tra thứ tự sự kiện, retry có kiểm soát, readback và đối soát trạng thái** để tránh tài khoản trùng, lỗi một phần và cấp quyền sai.
- Identity được tạo trong Joiner phải tiếp tục được quản lý theo **Mover–Leaver** để đổi quyền đúng vai trò và thu hồi truy cập tồn dư khi hết nhu cầu.
