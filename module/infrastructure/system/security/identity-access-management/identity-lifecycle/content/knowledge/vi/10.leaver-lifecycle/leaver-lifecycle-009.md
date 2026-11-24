# Lưu giữ dữ liệu cần thiết khi Leaver: bảo toàn hồ sơ, thu hồi truy cập và xóa đúng hạn

Khi một nhân viên hoặc nhà thầu rời tổ chức, hệ thống **Identity and Access Management (IAM)** phải ngăn họ tiếp tục truy cập tài nguyên. Đồng thời, tổ chức có thể vẫn cần một số hồ sơ liên quan đến người đó để trả lương, thực hiện nghĩa vụ pháp lý, đối soát công việc, duy trì dịch vụ, điều tra sự cố hoặc chứng minh quyền đã được thu hồi. **Lưu giữ dữ liệu cần thiết** là quá trình xác định *dữ liệu nào phải được giữ, vì sao, ai được truy cập, giữ trong bao lâu và xử lý thế nào khi hết hạn*.

Đây là nội dung của chương **Leaver lifecycle**, thuộc mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)** từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò; đồng thời kết nối HRIS, **IdP**, **SSO**, **SCIM**, **RBAC/ABAC**, tài khoản dịch vụ và kiểm toán để giảm quyền truy cập tồn dư. Với Leaver, mục tiêu kép là **chấm dứt truy cập không còn hợp lệ** và **giữ lại đúng dữ liệu có căn cứ trong thời hạn được phép**.

Sau bài học, người học có thể:

- Phân biệt **vô hiệu hóa tài khoản**, **thu hồi quyền**, **chuyển giao dữ liệu**, **lưu trữ**, **xóa** và **ẩn danh hóa**.
- Lập danh mục dữ liệu liên quan Leaver và xác định mục đích, chủ sở hữu, căn cứ lưu giữ, thời điểm bắt đầu tính hạn và người được truy cập.
- Giải thích cách HRIS, IGA, IdP, SCIM và ứng dụng phối hợp khi một chủ thể rời tổ chức nhưng dữ liệu nghiệp vụ vẫn cần tồn tại.
- Thiết kế quy trình lưu giữ có kiểm soát với lịch lưu giữ (*retention schedule*), ngoại lệ bảo toàn chứng cứ (*legal hold*) và xóa/hủy đúng hạn.
- Đánh giá rủi ro tài khoản tồn dư, dữ liệu bị mất khi xóa sớm, bản sao lưu, quyền truy cập sai và dữ liệu giữ lâu hơn cần thiết.

## 1. Lưu giữ dữ liệu cần thiết có nghĩa gì?

Trong IAM, một sự kiện **Leaver** thường làm mất hiệu lực quan hệ sử dụng dịch vụ của một chủ thể. Nhưng **quyền truy cập của chủ thể** và **dữ liệu do chủ thể tạo ra hoặc liên quan đến chủ thể** có vòng đời khác nhau.

Ví dụ: Lan nghỉ việc cuối ngày 30/11. Từ thời điểm chấm dứt có hiệu lực, Lan không còn được đăng nhập hệ thống doanh nghiệp. Tuy nhiên:

- Hồ sơ thanh toán lương và nghĩa vụ nhân sự có thể phải được lưu theo quy định áp dụng.
- Hóa đơn đã phê duyệt, tài liệu dự án hoặc mã nguồn công việc có thể vẫn cần để vận hành và kiểm toán.
- Nhật ký thay đổi quyền truy cập của Lan có thể cần để giải trình một sự cố.
- Tài khoản ứng dụng của Lan không cần tiếp tục hoạt động chỉ vì dữ liệu công việc cần lưu.
- Bản sao hộp thư cá nhân hoặc toàn bộ thư trao đổi **không mặc nhiên** được lưu không thời hạn; phải xác định mục đích, phạm vi và quyền truy cập phù hợp.

**Nguyên tắc trọng tâm:** *giữ dữ liệu cần thiết không đồng nghĩa giữ tài khoản, phiên đăng nhập hoặc quyền truy cập của Leaver*. Hệ thống phải bảo toàn những bản ghi hợp lệ mà vẫn thu hồi hiệu quả credential, session, token và entitlement của người đã rời tổ chức.

### 1.1. Phân biệt các thao tác

| Thao tác | Tác dụng | Điều không được suy ra |
| --- | --- | --- |
| **Disable/suspend account** | Ngăn hoặc hạn chế đăng nhập qua tài khoản theo khả năng hệ thống. | Không chắc đã xóa dữ liệu, quyền ứng dụng cục bộ hoặc phiên đã phát hành. |
| **Revoke access** | Thu hồi nhóm, role, quyền trực tiếp, token, phiên hoặc credential. | Không nhất thiết xóa tài khoản hay hồ sơ phục vụ kiểm toán. |
| **Transfer ownership** | Chuyển trách nhiệm đối với tài sản công việc sang người/nhóm được phép. | Không cấp quyền xem toàn bộ dữ liệu cá nhân của Leaver cho manager mới. |
| **Archive** | Di chuyển hoặc đánh dấu bản ghi sang chế độ lưu trữ có kiểm soát. | Không mặc nhiên là xóa, ẩn danh hay không thể truy cập. |
| **Retention** | Giữ một loại dữ liệu vì mục đích xác định trong thời hạn hợp lệ. | Không có nghĩa giữ mọi dữ liệu vô thời hạn. |
| **Deletion/destruction** | Loại bỏ dữ liệu theo quy trình được kiểm chứng khi hết căn cứ lưu. | Có thể không hoàn tất ngay với backup, bản sao hoặc hệ thống bất đồng bộ. |
| **Anonymization** | Biến đổi để không còn xác định được cá nhân bằng phương tiện có khả năng hợp lý được sử dụng. | Đổi tên thành mã giả (*pseudonymization*) thường vẫn là dữ liệu có thể liên kết về cá nhân. |

## 2. Bắt đầu từ mục đích và căn cứ lưu giữ

Trước khi quyết định giữ dữ liệu của Leaver, phải biết **vì sao tổ chức có quyền hoặc nghĩa vụ giữ dữ liệu đó**. Các căn cứ có thể đến từ luật áp dụng, hợp đồng, yêu cầu kiểm toán, an ninh, bảo đảm hoạt động kinh doanh hoặc nhiệm vụ lưu trữ đã được phê duyệt. Yêu cầu cụ thể phụ thuộc **quốc gia, loại dữ liệu, quan hệ lao động và quy định nội bộ**; không có một số năm lưu giữ chung cho mọi hồ sơ IAM.

Các câu hỏi cần trả lời:

1. **Loại dữ liệu nào?** Hồ sơ nhân sự, log IAM, tài liệu dự án, email, dữ liệu khách hàng, báo cáo tài chính, khóa bí mật hay dữ liệu ứng dụng?
2. **Mục đích nào còn tồn tại?** Quyết toán, chứng minh giao dịch, xử lý tranh chấp, vận hành liên tục, ứng phó sự cố hoặc yêu cầu pháp luật?
3. **Ai chịu trách nhiệm?** HR, Legal, Security, owner ứng dụng, chủ hồ sơ hay bộ phận quản trị dữ liệu?
4. **Căn cứ lưu trữ nào?** Điều khoản pháp lý/hợp đồng/chính sách cụ thể, đã được bộ phận có thẩm quyền xác nhận?
5. **Bao lâu?** Thời hạn và *sự kiện bắt đầu tính hạn* là gì?
6. **Ai được xem hoặc xuất dữ liệu?** Có cần phê duyệt, kiểm soát mục đích, ghi log và hạn chế phạm vi?
7. **Khi nào xóa?** Làm gì với bản sao, dữ liệu trong SaaS, backup và ngoại lệ bảo toàn chứng cứ?

**Không nên lưu “để phòng khi cần” mà không có mục đích và kỳ hạn xác định.** Giữ quá mức làm tăng nguy cơ rò rỉ, truy cập không hợp lệ, chi phí quản trị và khó đáp ứng yêu cầu bảo vệ dữ liệu cá nhân.

### 2.1. Phân loại dữ liệu liên quan Leaver

| Nhóm dữ liệu | Ví dụ | Chủ sở hữu/căn cứ cần xác định | Xử lý sau Leaver |
| --- | --- | --- | --- |
| **Hồ sơ nhân sự** | Hợp đồng, ngày làm việc, chứng từ thanh toán. | HR/Legal, luật và nghĩa vụ liên quan. | Giới hạn truy cập, lưu theo lịch, xóa/hủy đúng hạn. |
| **Hồ sơ danh tính IAM** | \`subjectId\`, loại quan hệ, ID liên kết tài khoản, trạng thái JML. | Identity Governance, nhu cầu đối chiếu/kiểm toán. | Giữ tham chiếu tối thiểu cần thiết, đánh dấu quan hệ đã kết thúc. |
| **Nhật ký an ninh và kiểm toán** | Đăng nhập, cấp/thu hồi quyền, phê duyệt, hoạt động quản trị. | Security/Compliance và lịch lưu giữ log. | Bảo vệ tính toàn vẹn, truy cập theo vai trò, xóa khi hết hạn và không còn ngoại lệ. |
| **Dữ liệu nghiệp vụ** | Báo cáo, hợp đồng khách hàng, mã nguồn, hồ sơ dự án. | Owner nghiệp vụ, chính sách hồ sơ. | Chuyển giao sở hữu có kiểm soát; tiếp tục áp dụng chính sách của bản ghi. |
| **Hộp thư và công cụ cộng tác** | Email công việc, chat, tài liệu cá nhân hóa. | Owner dịch vụ/Legal/HR, phạm vi công việc cần giữ. | Xem xét chọn lọc, chuyển giao hợp lệ, hạn chế quyền đọc thông tin riêng tư. |
| **Bản sao và backup** | Snapshot, bản sao lưu cơ sở dữ liệu, file xuất. | Owner hạ tầng, lịch backup và yêu cầu phục hồi. | Đảm bảo không khôi phục quyền Leaver, áp dụng vòng đời backup. |
| **Credential và secret** | Password, API key, refresh token, chứng chỉ của người nghỉ. | IAM/Security. | **Thu hồi/xoay/tiêu hủy theo chính sách**, không lưu bí mật để tiện điều tra. |
| **Workload/service account** | Job, service principal, token của ứng dụng mà Leaver làm owner. | Owner hệ thống và nhóm vận hành. | Chuyển owner, rà soát quyền và secret, đóng workload không còn cần. |

Mỗi loại dữ liệu có **lịch lưu giữ riêng**. Ví dụ, thời hạn giữ chứng từ tài chính có thể khác thời hạn lưu nhật ký xác thực hoặc dữ liệu chat, nên một nút “Delete employee” không thể quyết định toàn bộ.

## 3. Dữ liệu của Leaver nằm ở đâu?

Dữ liệu liên quan một người có thể được lưu tại nhiều hệ thống, trong khi IAM chỉ kiểm soát trực tiếp một phần tài khoản và quyền.

~~~mermaid
flowchart TD
    HR["HRIS / nguồn hợp đồng<br/>Xác nhận Leaver"] --> IGA["IGA / IAM lifecycle<br/>Điều phối thu hồi"]
    IGA --> IDP["IdP / Directory<br/>Khóa đăng nhập và credential"]
    IGA --> APP["SaaS / ứng dụng nghiệp vụ<br/>SCIM, API hoặc quy trình riêng"]
    IGA --> CATALOG["Danh mục tài sản và dữ liệu<br/>Owner + retention schedule"]
    APP --> CATALOG
    HR --> CATALOG
    CATALOG --> OWNER["HR / Legal / Security / business owner<br/>Quyết định giữ, chuyển giao, xóa"]
    OWNER --> STORE["Kho lưu trữ kiểm soát<br/>Giới hạn truy cập + audit"]
    OWNER --> DELETE["Hủy/xóa khi hết hạn<br/>Kiểm chứng + ghi bằng chứng"]
    IDP --> AUDIT["Audit / đối soát"]
    APP --> AUDIT
    STORE --> AUDIT
    DELETE --> AUDIT
~~~

Vai trò của các thành phần:

- **HRIS** xác nhận trạng thái và ngày giờ kết thúc quan hệ lao động; HR có thể là chủ sở hữu các hồ sơ nhân sự cần lưu.
- **IAM/IGA** tạo sự kiện Leaver, xác định các tài khoản/quyền và chuyển tác vụ tới IdP, SCIM/API, owner dữ liệu và bộ phận quản trị hồ sơ.
- **IdP/SSO** hỗ trợ chặn xác thực mới và kiểm soát các đường đăng nhập tập trung; tài khoản SaaS cục bộ và phiên đã cấp cần được kiểm tra riêng.
- **SCIM** có thể truyền cập nhật \`active=false\` hoặc thao tác tài khoản phù hợp tới ứng dụng. Việc vô hiệu hóa SCIM User **không đồng nghĩa xóa dữ liệu nghiệp vụ thuộc tài khoản**.
- **RBAC/ABAC** quyết định ai được tiếp tục xem, nhận bàn giao hoặc quản lý dữ liệu; quyền đó không mặc nhiên chuyển cho manager hay đồng nghiệp.
- **Audit/đối soát** theo dõi tình trạng thực tế tại từng hệ thống và bằng chứng các quyết định lưu/xóa dữ liệu.

## 4. Phân biệt danh tính, tài khoản và dữ liệu cần giữ

Một chủ thể có thể có nhiều tài khoản ở IdP, CRM, ERP, Git, VPN và hệ thống lưu trữ. Khi Leaver:

1. **Quan hệ làm việc hết hiệu lực:** HRIS phát sự kiện hoặc nguồn có thẩm quyền xác nhận.
2. **Danh tính IAM chuyển trạng thái:** giữ tham chiếu tối thiểu cần thiết cho truy vết, không mặc định xóa ID ngay lập tức.
3. **Tài khoản bị vô hiệu hóa:** truy cập mới phải bị ngăn theo chính sách; xử lý session/token/credential riêng.
4. **Entitlement bị thu hồi:** loại bỏ nhóm, role, quyền API, quyền trực tiếp, quyền quản trị và ủy quyền không còn hợp lệ.
5. **Dữ liệu được phân loại:** bản ghi nghiệp vụ cần giữ được tách khỏi quyền truy cập của Leaver.
6. **Bản ghi hết căn cứ được xóa/hủy:** theo lịch lưu giữ và các ngoại lệ còn hiệu lực.

### 4.1. Vì sao vẫn cần một số ID sau khi xóa tài khoản?

Giả sử một log phê duyệt ghi \`actorId=person-1042\`; nếu xóa toàn bộ ánh xạ ID ngay, kiểm toán viên có thể không xác định được ai thực hiện thay đổi trước đây. Tổ chức có thể giữ **bảng tham chiếu định danh tối thiểu** trong thời hạn phục vụ mục đích kiểm toán hợp lệ, với quyền truy cập hạn chế. Không cần giữ tài khoản đang hoạt động, mật khẩu, MFA secret hoặc toàn bộ thuộc tính cá nhân.

Thiết kế gợi ý:

| Thực thể | Trạng thái sau Leaver | Dữ liệu tối thiểu có thể cần |
| --- | --- | --- |
| **Person/Subject** | Không còn đủ điều kiện truy cập theo quan hệ đã kết thúc. | ID ổn định, liên kết tới các engagement theo thời hạn lưu hợp lệ. |
| **Engagement** | \`TERMINATED\` hoặc giá trị tương đương. | Mốc bắt đầu/kết thúc và tham chiếu nguồn có thẩm quyền. |
| **IdP Account** | Vô hiệu hóa, sau đó xóa theo lịch và khả năng hệ thống. | ID liên kết/audit reference cần giữ ở kho riêng nếu hợp lệ. |
| **Application Account** | Vô hiệu hóa/thu hồi, bàn giao dữ liệu cần thiết theo quy trình. | ID tài khoản phục vụ đối chiếu hoạt động và dữ liệu nghiệp vụ. |
| **Credentials & Sessions** | Thu hồi/làm mất hiệu lực khi khả thi. | Chỉ giữ metadata hoặc log chứng minh đã thu hồi, không giữ bí mật còn dùng được. |
| **Business Records** | Lưu hoặc chuyển owner theo phân loại. | Nội dung cần thiết, phiên bản và lịch sử giao dịch được phép giữ. |

**Không sử dụng việc “cần log” làm lý do bảo lưu credential của Leaver.** Dấu vết kiểm toán nên ghi thời điểm thu hồi, ID tài khoản, loại credential và kết quả xử lý; giá trị bí mật phải được bảo vệ, xoay hoặc vô hiệu hóa.

## 5. Lập lịch lưu giữ dữ liệu (*retention schedule*)

Lịch lưu giữ là bảng quy định nhất quán cho mỗi nhóm hồ sơ. Nội dung tối thiểu nên có:

| Trường | Ý nghĩa |
| --- | --- |
| **Record class / loại hồ sơ** | Phân loại rõ dữ liệu được áp dụng. |
| **Owner / steward** | Bộ phận chịu trách nhiệm quyết định và kiểm tra. |
| **Purpose / legal basis** | Mục đích và căn cứ được phê duyệt. |
| **Retention trigger** | Sự kiện bắt đầu tính hạn: ngày chấm dứt, kết thúc giao dịch, hết hợp đồng, đóng hồ sơ hoặc mốc khác. |
| **Retention period** | Khoảng thời gian lưu theo chính sách/quy định áp dụng. |
| **Storage & access policy** | Nơi lưu, mã hóa, phân quyền và kiểm tra truy cập. |
| **Hold/exception rule** | Quy định tạm dừng hủy khi có tranh chấp, yêu cầu pháp lý hoặc ngoại lệ hợp lệ. |
| **Disposition action** | Xóa/hủy, ẩn danh hóa, chuyển sang lưu trữ khác hoặc hành động được chấp thuận. |
| **Evidence & reviewer** | Ai phê duyệt, khi nào thực hiện, cách ghi nhận kết quả. |

**Mốc bắt đầu tính hạn không nhất thiết là ngày nghỉ việc.** Ví dụ, một hợp đồng thương mại do nhân viên soạn thảo có thể bắt đầu kỳ lưu từ ngày kết thúc hợp đồng hoặc hoàn tất giao dịch, trong khi hồ sơ chấm dứt quan hệ lao động có lịch riêng.

### 5.1. Ví dụ chính sách ở mức khái niệm

~~~yaml
# Minh họa cấu trúc chính sách, không phải thời hạn lưu bắt buộc.
recordClass: access-approval-audit
owner: identity-governance
purpose: security-and-audit
retentionTrigger: request-closed
retentionPeriod: defined-by-approved-policy
accessPolicy: restricted-auditors-and-incident-responders
disposition: delete-after-retention-if-no-active-hold
evidenceRequired: true
~~~

Không điền số tháng/năm theo thói quen. Khi triển khai, phải thay các giá trị minh họa bằng quy tắc cụ thể đã được **Legal, Compliance, HR và chủ dữ liệu** phê duyệt phù hợp pháp luật áp dụng.

### 5.2. Thời hạn lưu và yêu cầu bảo toàn chứng cứ

Một số dữ liệu đang đến hạn xóa nhưng cần được bảo toàn vì yêu cầu điều tra hoặc tranh chấp. Cơ chế **legal hold / preservation hold** cho phép ngăn xóa những hồ sơ **đúng phạm vi, đúng căn cứ** trong thời gian yêu cầu còn hiệu lực.

- Hold cần có ID, người có thẩm quyền, lý do, phạm vi dữ liệu, thời điểm đặt và điều kiện gỡ.
- Kho dữ liệu phải tránh tự động hủy hồ sơ thuộc hold dù lịch thông thường đã hết hạn.
- Hold không có nghĩa tất cả dữ liệu của Leaver được giữ vô thời hạn hoặc mọi nhân viên được xem.
- Khi gỡ hold, phải **đánh giá lại lịch lưu giữ** và tiến hành disposition nếu không còn căn cứ.
- Mọi thao tác đặt/gỡ hold cần có audit trail và kiểm soát truy cập.

Không nên để các nhóm nghiệp vụ tự đặt hold không thời hạn chỉ nhằm giữ dữ liệu thuận tiện cho sử dụng.

## 6. Trình tự xử lý Leaver và lưu giữ dữ liệu

Một quy trình tốt phối hợp **ngăn truy cập ngay khi quan hệ không còn hợp lệ** với **chuyển giao dữ liệu theo thủ tục có kiểm soát**.

### Giai đoạn A — Xác nhận và chuẩn bị

1. Nhận sự kiện từ HRIS/hệ thống hợp đồng, kèm ID chủ thể, thời điểm Leaver có hiệu lực, loại quan hệ và mức độ ưu tiên.
2. Liệt kê tài khoản IdP, tài khoản ứng dụng, nhóm, role, phiên/token, quyền đặc quyền và các owner liên quan.
3. Tra danh mục dữ liệu: hồ sơ cá nhân, dữ liệu nghiệp vụ, mailbox, cloud drive, repository, log và backup.
4. Ánh xạ từng nhóm dữ liệu tới **lịch lưu giữ và người có thẩm quyền quyết định**.
5. Xác định yêu cầu chuyển giao công việc, hold hoặc trường hợp rủi ro cao cần bảo toàn chứng cứ.

### Giai đoạn B — Thu hồi truy cập

1. Tại thời điểm được phê duyệt, khóa/vô hiệu hóa đăng nhập IdP và các ứng dụng có tài khoản cục bộ.
2. Thu hồi nhóm/role/entitlement, VPN, API key, khóa SSH, token, phiên và credential khác theo khả năng kỹ thuật của từng đích.
3. Dùng SCIM/API hoặc thao tác được kiểm soát để vô hiệu hóa tài khoản ứng dụng; không suy luận mọi ứng dụng sẽ vô hiệu hóa ngay theo IdP.
4. Đối soát từng hệ thống; ghi rõ **đã gửi lệnh**, **đã có phản hồi**, **đã xác minh trạng thái** hoặc **còn lỗi**.
5. Kiểm tra các quyền chia sẻ công khai và ủy quyền do Leaver cấp, tài khoản quản trị phụ và service account mà người đó làm owner.

### Giai đoạn C — Giữ và bàn giao dữ liệu cần thiết

1. Xác định hồ sơ công việc nào cần tiếp tục được sử dụng và ai là owner hợp lệ.
2. Chuyển giao tài sản bằng cơ chế của ứng dụng, giữ ID, lịch sử chỉnh sửa và bằng chứng quyền sở hữu khi cần.
3. Chuyển dữ liệu phải lưu sang kho hoặc trạng thái **chỉ đọc/ít quyền** theo chính sách; tránh giữ tài khoản Leaver hoạt động để đồng nghiệp “vào lấy file”.
4. Giới hạn quyền xem dữ liệu cá nhân hoặc nhạy cảm; truy cập mailbox/công cụ cộng tác phải được kiểm soát, chọn lọc và có căn cứ.
5. Lưu nhật ký quyết định, người phê duyệt, dữ liệu được bàn giao và trạng thái hệ thống đích.

### Giai đoạn D — Rà soát định kỳ và xóa đúng hạn

1. Đến kỳ rà soát, kiểm tra mục đích lưu có còn hợp lệ và hồ sơ có thuộc hold không.
2. Xử lý hết hạn bằng quy trình xóa/hủy, ẩn danh hóa hoặc disposition khác đã được phê duyệt.
3. Kiểm tra các bản sao hoạt động, chỉ mục tìm kiếm, dữ liệu xuất và tích hợp có tồn tại thêm bản không.
4. Áp dụng lịch backup và các biện pháp ngăn bản sao khôi phục quyền cũ.
5. Ghi bằng chứng hủy, trường hợp chưa xóa được và chủ thể chịu trách nhiệm giải quyết.

**Luồng thu hồi quyền và luồng lưu giữ dữ liệu có thể chạy song song**, nhưng không được để việc chờ chuyển giao làm trì hoãn việc chặn truy cập của Leaver khi chính sách yêu cầu khóa ngay.

## 7. Bàn giao quyền sở hữu dữ liệu và tài sản công việc

Người rời tổ chức có thể là **owner**, **creator**, **editor** hoặc **approver** của nhiều tài sản. Những vai trò này cần được kiểm tra riêng. Chuyển “ownership” tài liệu cho manager mới không có nghĩa mọi bản ghi mà Leaver từng xem phải được sao chép.

| Tài sản | Nhu cầu thường gặp | Cách bàn giao có kiểm soát |
| --- | --- | --- |
| **Repository mã nguồn** | Duy trì commit, issue, pipeline, quyền release. | Giữ lịch sử tác giả, đổi maintainer/owner dự án, thu hồi SSH/API token cá nhân. |
| **Cloud drive và tài liệu dự án** | Duy trì tài liệu nhóm. | Chọn tài liệu thuộc công việc, chuyển owner/thư mục tới nhóm phù hợp và ghi nhận nguồn gốc. |
| **Hộp thư công việc** | Duy trì chuỗi trao đổi khách hàng đang xử lý. | Chọn lọc bản ghi cần thiết, chuyển giao qua quy trình phê duyệt; tránh cấp quyền đọc toàn bộ tùy tiện. |
| **CRM / hồ sơ khách hàng** | Không mất người phụ trách tài khoản. | Gán owner hồ sơ cho nhân sự mới, giữ audit history, thu hồi quyền account cũ. |
| **ERP / phê duyệt tài chính** | Không để giao dịch treo hoặc mất bằng chứng. | Chuyển nhiệm vụ còn mở theo quy tắc, giữ nguyên người đã phê duyệt giao dịch quá khứ. |
| **Tác vụ tự động / service account** | Duy trì dịch vụ. | Gán owner nhóm/kỹ thuật mới, kiểm tra secret và quyền, không để tài khoản mồ côi. |
| **Bản ghi IAM** | Chứng minh nguồn, phê duyệt và kết quả thu hồi. | Giữ audit reference tối thiểu trong kho được bảo vệ, không kích hoạt lại tài khoản. |

### 7.1. Không sửa lịch sử để “đổi người thực hiện”

Ví dụ, một giao dịch do Lan phê duyệt khi còn làm việc nên giữ **dấu vết Lan là người phê duyệt tại thời điểm đó**. Việc chuyển nhiệm vụ cho Bình chỉ áp dụng cho trách nhiệm hiện tại hoặc bước tiếp theo. Sửa người phê duyệt lịch sử thành Bình để dễ quản lý sẽ làm sai bằng chứng kiểm toán.

### 7.2. Mailbox và dữ liệu cá nhân

Mailbox/công cụ cộng tác có thể chứa cả dữ liệu công việc và thông tin không cần thiết hoặc riêng tư. Việc truy cập sau khi nhân viên nghỉ cần có **mục đích, phạm vi, vai trò phê duyệt, quy trình ghi log và thời hạn cụ thể**. Ưu tiên cơ chế tìm kiếm, xuất và bàn giao có lọc tài liệu liên quan; không dùng tài khoản đăng nhập của Leaver hoặc chia sẻ mật khẩu để truy cập nội dung.

### 7.3. Dữ liệu có đồng tác giả hoặc nhiều owner

Không phải mọi file do Leaver tạo là “dữ liệu cá nhân của Leaver”, và không phải mọi dữ liệu liên quan Leaver đều thuộc quyền chuyển giao của quản lý. Cần căn cứ **loại hồ sơ, chủ dữ liệu, hợp đồng và chính sách sở hữu trí tuệ/quyền riêng tư** để quyết định xử lý. Các quyền của khách hàng và người khác có dữ liệu trong hồ sơ cũng phải được tôn trọng.

## 8. Lưu giữ thông tin danh tính và bằng chứng IAM

Một kho audit đáng tin cần giải thích được sự kiện đã xảy ra mà không duy trì một tài khoản có thể đăng nhập.

### 8.1. Các trường kiểm toán phù hợp

| Trường dữ liệu | Mục đích |
| --- | --- |
| \`subjectId\`, \`engagementId\` | Liên kết đúng người và đúng giai đoạn làm việc. |
| \`sourceSystem\`, \`sourceEventId\` | Xác định sự kiện Leaver từ nguồn có thẩm quyền. |
| \`effectiveAt\`, \`processedAt\`, \`verifiedAt\` | Phân biệt thời điểm chấm dứt, thực thi và xác nhận tại đích. |
| \`targetSystem\`, \`targetAccountId\` | Biết tài khoản ứng dụng nào được xử lý. |
| \`action\`, \`result\`, \`reasonCode\` | Lệnh khóa/thu hồi/giữ/xóa và kết quả. |
| \`requestId\`, \`traceId\` | Truy chuỗi tác vụ qua nhiều hệ thống. |
| \`retentionClass\`, \`retentionTrigger\` | Liên kết hồ sơ với lịch lưu giữ thích hợp. |
| \`approverId\`, \`evidenceRef\` | Truy vết người có thẩm quyền và bằng chứng. |

Ví dụ một bản ghi **xác minh thu hồi tài khoản**; đây là schema nội bộ minh họa:

~~~json
{
  "eventType": "LEAVER_ACCESS_REVOKE_VERIFIED",
  "eventId": "evt-20261130-824",
  "traceId": "leaver-person-1042-20261130",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "sourceSystem": "HRIS",
  "targetSystem": "expense-app",
  "targetAccountId": "usr-882",
  "action": "DISABLE_AND_REVOKE",
  "result": "VERIFIED",
  "effectiveAt": "2026-11-30T17:00:00+07:00",
  "verifiedAt": "2026-11-30T10:01:30Z",
  "retentionClass": "iam-offboarding-evidence",
  "evidenceRef": "audit://case/LEAVER-502"
}
~~~

Không ghi **mật khẩu, session cookie, access token, refresh token, mã MFA hoặc private key** vào log. Khi kiểm toán một lần thu hồi token, lưu ID dẫn xuất hoặc tham chiếu không thể dùng lại và trạng thái thu hồi theo chính sách, không lưu chính token.

### 8.2. Nhật ký IdP, SSO và ứng dụng cần kết hợp

IdP có thể cung cấp bằng chứng tài khoản bị khóa, nhưng **SSO không kiểm soát mọi tài khoản cục bộ hoặc phiên của ứng dụng**. Khi thu hồi qua SCIM, \`active=false\` chỉ thể hiện một thay đổi liên quan tài khoản được gửi/áp dụng tại service provider; phải xem khả năng hệ thống đích để biết phiên/token và dữ liệu nghiệp vụ còn gì.

Vì vậy, audit cần ghép:

1. Sự kiện Leaver có hiệu lực từ nguồn có thẩm quyền.
2. Yêu cầu khóa tài khoản, thu hồi nhóm/quyền, credential và session.
3. Phản hồi SCIM/API và lỗi từ các ứng dụng.
4. Trạng thái thực tế được đọc lại hoặc đối soát tại đích.
5. Quyết định phân loại dữ liệu, bàn giao, archive, hold và disposition.

**Một ticket “Offboarding completed” không đủ bằng chứng** nếu các ứng dụng quan trọng vẫn có tài khoản hoạt động hoặc dữ liệu cần bàn giao chưa được xử lý.

## 9. Bản sao lưu và khôi phục dữ liệu sau Leaver

Backup thường có lịch và cơ chế hủy khác dữ liệu đang hoạt động. Việc một hồ sơ hết hạn lưu trong ứng dụng chính không nhất thiết khiến mọi bản backup bị xóa ngay lập tức. Tuy vậy, cần có **chính sách vòng đời backup cụ thể** và biện pháp bảo vệ dữ liệu còn trong backup.

### 9.1. Những yêu cầu tối thiểu

- Định nghĩa thời gian giữ snapshot/backup theo mục đích phục hồi, yêu cầu pháp lý và khả năng kỹ thuật; tránh giữ vô hạn không có căn cứ.
- Mã hóa, kiểm soát quyền đọc và theo dõi truy xuất backup, đặc biệt bản sao chứa hồ sơ nhân sự hoặc credential lịch sử.
- Phân biệt **xóa logic ở hệ thống chính** với việc bản sao còn ở kho backup.
- Giữ **danh sách sự kiện thu hồi/xóa** có thể phát lại khi phục hồi: tài khoản Leaver không được tự động hoạt động trở lại từ snapshot cũ.
- Khi một bản sao được phục hồi vào môi trường thử nghiệm hoặc điều tra, áp dụng cách ly truy cập, giới hạn dữ liệu và xóa theo quy trình sau khi hoàn tất.

### 9.2. Kịch bản phục hồi đáng chú ý

Ngày 30/11, tài khoản Lan đã bị vô hiệu hóa. Ngày 05/12, một ứng dụng gặp sự cố và được khôi phục từ backup chụp ngày 25/11, khi tài khoản Lan vẫn đang hoạt động.

Nếu hệ thống cho phép đăng nhập ngay sau khi phục hồi mà không **đối soát lại trạng thái danh tính/quyền hiện hành**, Lan có thể lấy lại quyền trái phép. Quy trình phục hồi cần:

1. Cách ly hoặc hạn chế truy cập sau restore cho tới khi các kiểm soát thiết yếu được xác nhận.
2. Đồng bộ lại trạng thái Leaver, các quyền/nhóm đã thu hồi và thay đổi credential từ nguồn có thẩm quyền.
3. Xác minh token, phiên và tài khoản cục bộ không được khôi phục thành khả dụng.
4. Kiểm tra dữ liệu đã có quyết định xóa/hạn chế xử lý; xử lý lại theo chính sách và giới hạn kỹ thuật.
5. Ghi bằng chứng xác minh trước khi đưa ứng dụng trở lại phục vụ.

Backup phục vụ **khả năng phục hồi**, không phải cách bỏ qua quyết định xóa dữ liệu hoặc mở lại quyền của người đã rời tổ chức.

## 10. Xóa, hủy hoặc ẩn danh hóa khi hết hạn

Khi đến thời điểm xử lý cuối (*disposition*), hệ thống phải kiểm tra xem có còn căn cứ giữ dữ liệu hoặc hold hợp lệ hay không.

| Phương thức | Dùng khi | Điều cần xác minh |
| --- | --- | --- |
| **Xóa tại nguồn** | Hồ sơ hết thời hạn lưu và không còn căn cứ xử lý. | Trạng thái bản ghi/đối tượng không còn, log hành động, bản sao phụ thuộc được xử lý theo quy trình. |
| **Hủy an toàn** | Vật mang tin hoặc dữ liệu đặc biệt cần tiêu hủy. | Phương pháp phù hợp độ nhạy, bằng chứng người chịu trách nhiệm. |
| **Ẩn danh hóa** | Vẫn cần số liệu phân tích nhưng không cần nhận diện cá nhân. | Khả năng tái nhận diện đã được đánh giá; thuộc tính liên kết và dữ liệu phụ không phá vỡ mục tiêu. |
| **Giả danh hóa** | Cần hạn chế lộ danh tính nhưng vẫn cần liên kết có kiểm soát. | Khóa ánh xạ được bảo vệ; dữ liệu vẫn phải chịu quản trị phù hợp. |
| **Chuyển sang kho lưu trữ khác** | Còn mục đích và căn cứ lưu dài hạn với mức truy cập thấp hơn. | Chính sách kho mới, người được đọc, thời hạn và khả năng truy xuất. |

Không coi **đổi tên file**, **ẩn khỏi giao diện**, **xóa link chia sẻ** hoặc **disable account** là xóa dữ liệu. Ngược lại, không xóa hồ sơ kiểm toán cần thiết chỉ để “dọn sạch” tài khoản nhanh.

### 10.1. Các trường hợp không thể xóa ngay

Với một số nền tảng SaaS hoặc backup bất biến, xóa từng bản ghi có thể không khả thi tức thời. Tổ chức cần ghi rõ:

- Bản sao nào còn tồn tại và thời gian xử lý dự kiến theo khả năng hệ thống.
- Biện pháp hạn chế truy cập, mã hóa và ngăn dùng dữ liệu ngoài mục đích được phép trong giai đoạn chờ.
- Cách xác minh dữ liệu được loại bỏ ở kỳ hết hạn kế tiếp hoặc khi backup tự hết vòng đời.
- Người chịu trách nhiệm, yêu cầu quản trị/tuân thủ còn mở và bằng chứng hoàn tất.

Không tuyên bố **“đã xóa khỏi mọi nơi”** nếu mới xóa ở ứng dụng chính mà chưa xác minh được các bản sao thuộc phạm vi.

## 11. Trường hợp tài khoản dịch vụ và quyền truy cập đặc biệt

Một nhân viên nghỉ việc có thể đứng tên owner của **service account**, service principal, CI/CD pipeline, bot hoặc ứng dụng sản xuất. Những đối tượng này là **danh tính phi con người** và có thể vẫn cần tồn tại sau Leaver để dịch vụ vận hành.

Quy trình cần:

1. Kiểm kê các workload/service account do Leaver tạo hoặc quản lý; xác định chủ sở hữu nghiệp vụ và kỹ thuật hiện tại.
2. Chuyển owner sang người/nhóm hợp lệ theo phê duyệt; phân tách **người chịu trách nhiệm** với **danh tính kỹ thuật thực thi**.
3. Kiểm tra quyền của service account theo **least privilege** và thời hạn cần thiết.
4. Xoay hoặc thu hồi secret/certificate/token nếu Leaver từng biết hoặc có thể truy cập chúng, theo đánh giá rủi ro và chính sách.
5. Nếu dịch vụ không còn cần, thực hiện kế hoạch dừng và thu hồi quyền/credential, giữ dữ liệu nghiệp vụ cần thiết theo lịch.
6. Ghi log việc chuyển owner, thay đổi quyền, xoay bí mật và kết quả kiểm tra hoạt động.

Với **PAM/break-glass**, cần thu hồi quyền mượn tài khoản đặc quyền, phiên quản trị, khóa SSH, chứng chỉ và quyền khẩn cấp mà Leaver có thể sử dụng. Không giữ credential sử dụng được chỉ vì muốn bảo toàn khả năng kiểm toán các phiên cũ; lưu **metadata và bản ghi phiên được phép** theo chính sách riêng.

## 12. Rủi ro bảo mật và quyền riêng tư trong quá trình lưu giữ

| Rủi ro | Ví dụ | Kiểm soát khuyến nghị |
| --- | --- | --- |
| **Giữ tài khoản để lấy dữ liệu** | Manager dùng mật khẩu của nhân viên đã nghỉ để đọc file. | Khóa tài khoản đúng hạn, chuyển dữ liệu qua cơ chế owner/export có phê duyệt. |
| **Giữ dữ liệu quá hạn** | Lưu toàn bộ hộp thư vô thời hạn vì “có thể cần”. | Retention schedule theo mục đích, rà soát định kỳ và disposition tự động có kiểm soát. |
| **Xóa quá sớm** | Xóa hồ sơ giao dịch chưa hết nghĩa vụ chứng minh. | Tra lịch lưu giữ, kiểm tra hold, phê duyệt disposition theo loại hồ sơ. |
| **Lộ dữ liệu cá nhân** | Chuyển toàn bộ mailbox cho quản lý mới. | Xác định phạm vi dữ liệu công việc, phê duyệt truy xuất có chọn lọc, ghi log. |
| **Tài khoản mồ côi tại SaaS** | IdP khóa nhưng app còn local account. | Inventory, SCIM/API và xác minh tài khoản thực tế tại đích. |
| **Phiên/token còn hiệu lực** | API key của người nghỉ vẫn đọc dữ liệu sau ngày Leaver. | Thu hồi/xoay credential, kiểm tra phiên và đường truy cập ngoài SSO. |
| **Restore quyền từ backup** | Snapshot cũ mở lại tài khoản đã bị khóa. | Đồng bộ lại trạng thái JML, kiểm tra quyền trước khi phục vụ. |
| **Hold không được gỡ** | Dữ liệu bị giữ vô hạn sau khi vụ việc đã kết thúc. | Chủ hold, kỳ rà soát, cơ chế gỡ và tính lại hạn xóa. |
| **Sai owner dữ liệu** | Tài liệu dự án chuyển cho người không có thẩm quyền. | Bàn giao dựa trên phân loại, phạm vi cần biết và phê duyệt. |
| **Mất dấu kiểm toán** | Xóa user ID khiến log không còn đối chiếu được. | Giữ liên kết tối thiểu, bảo vệ ánh xạ và lịch sử theo thời hạn hợp lệ. |

**Hai sai lầm đối nghịch đều gây hại:** giữ quá nhiều dữ liệu và quyền làm tăng nguy cơ lạm dụng; xóa không có phân loại làm mất hồ sơ mà tổ chức vẫn có trách nhiệm bảo quản. Giải pháp là kiểm soát theo **loại hồ sơ, mục đích và thời hạn**, đồng thời tách rõ quyền truy cập khỏi vòng đời bản ghi.

## 13. Ví dụ triển khai: nhân viên nghỉ nhưng dự án vẫn đang hoạt động

**Bối cảnh:** Minh là nhân viên kỹ thuật, kết thúc quan hệ lao động lúc **17:00 ngày 30/11** (giờ Việt Nam). Minh từng quản lý repository, chia sẻ tài liệu dự án, phê duyệt một số thay đổi hạ tầng và làm owner của service account chạy báo cáo. Tổ chức cần tiếp tục vận hành dự án và giữ bằng chứng thay đổi hệ thống theo lịch đã phê duyệt.

| Hạng mục | Hành động sau Leaver | Bằng chứng cần có |
| --- | --- | --- |
| **IdP/SSO và VPN** | Vô hiệu hóa đăng nhập đúng hạn; thu hồi phiên/token theo khả năng. | Thời điểm, tài khoản và kết quả xác minh. |
| **Git/repository** | Thu hồi tài khoản, SSH key và PAT cá nhân; chuyển maintainer; giữ commit history. | Log thu hồi credential, người nhận quyền, lịch sử commit còn nguyên. |
| **Cloud drive** | Phân loại tài liệu dự án, chuyển owner cho nhóm dự án, hạn chế nội dung không cần thiết. | Danh sách hồ sơ được bàn giao và phê duyệt. |
| **ERP/phê duyệt** | Chuyển yêu cầu đang chờ theo policy; giữ tên người phê duyệt giao dịch quá khứ. | Workflow trước/sau và audit trail. |
| **Service account báo cáo** | Gán owner mới, rà soát scope và xoay secret phù hợp. | Ticket, owner mới, kiểm tra job tiếp tục chạy. |
| **Hồ sơ nhân sự** | HR lưu các bản ghi thuộc phạm vi bắt buộc theo lịch. | Loại hồ sơ, căn cứ, người được đọc và thời hạn. |
| **Log IAM/Security** | Giữ chứng cứ cấp/thu hồi quyền trong thời hạn được phê duyệt. | Trace ID, đối soát từng app, lịch retention. |
| **Backup** | Áp dụng lịch lưu backup; ngăn quyền Minh phục hồi khi restore. | Quy trình khôi phục và kết quả kiểm tra. |

### 13.1. Thử một tình huống lỗi

Ngày 02/12, bộ phận dự án phát hiện tài liệu của Minh không thể mở vì owner đã bị xóa khỏi SaaS. Một người đề xuất **kích hoạt lại tài khoản Minh** để tải file. Đây là giải pháp có nguy cơ tái tạo đường truy cập không còn hợp lệ.

Cách xử lý phù hợp:

1. Xác định loại tài liệu và chủ dữ liệu; xác minh có mục đích tiếp tục sử dụng hợp lệ.
2. Kiểm tra chức năng admin/transfer ownership/export của SaaS; cho phép người được ủy quyền trích xuất hoặc đổi owner theo quy trình.
3. Nếu app yêu cầu tài khoản ở trạng thái nhất định để bàn giao, xử lý trong môi trường/quyền quản trị kiểm soát đặc biệt và chỉ khi được phê duyệt theo chính sách; không trả lại credential cho Leaver.
4. Ghi log thao tác, chuyển quyền cho nhóm dự án và tiếp tục để đường truy cập của Minh bị vô hiệu hóa.
5. Đối soát các ứng dụng tương tự để tránh lặp lại lỗi thiếu bước bàn giao.

### 13.2. Ví dụ chuỗi trạng thái nghiệp vụ

~~~text
HRIS: TERMINATED (30/11 17:00 +07:00)
    -> IGA: LEAVER_CASE_OPENED
    -> IdP: account disabled (verified)
    -> App A: SCIM disable (verified)
    -> App B: API error (exception + owner + retry)
    -> Repository: personal credentials revoked (verified)
    -> Data inventory: business files assigned to retention class
    -> Transfer: approved business documents moved to team owner
    -> Archive: audit records stored with restricted access
    -> Scheduled disposition: evaluate deadline and hold status
    -> Deletion/retention outcome: verified and recorded
~~~

Quy trình **thu hồi quyền** có thể hoàn tất sớm hơn quy trình **lưu giữ/xóa dữ liệu**. Cần quản lý hai luồng trạng thái riêng để tránh “Leaver chưa hoàn thành” bị hiểu là người đã nghỉ vẫn được phép đăng nhập.

## 14. Kiểm toán và đo lường việc lưu giữ dữ liệu cần thiết

Để chứng minh quy trình hoạt động đúng, tổ chức cần biết **dữ liệu nào được giữ**, **ai có thẩm quyền**, **hạn xử lý**, **ai đã truy cập** và **đã xóa/hủy khi hết căn cứ hay chưa**.

| Chỉ số | Cách đo gợi ý | Mục đích |
| --- | --- | --- |
| **Tỷ lệ Leaver được kiểm kê dữ liệu đầy đủ** | Số Leaver có danh mục tài sản, ứng dụng, hồ sơ và owner trong phạm vi ÷ tổng Leaver phải kiểm tra. | Giảm bỏ sót dữ liệu/quyền. |
| **Tỷ lệ bản ghi có retention class hợp lệ** | Bản ghi cần quản lý có class, owner và trigger hợp lệ ÷ tổng bản ghi trong phạm vi. | Phát hiện dữ liệu giữ không có căn cứ. |
| **Tỷ lệ chuyển giao hoàn tất đúng hạn** | Tài sản công việc đã chuyển đúng owner và xác minh ÷ tổng tài sản cần bàn giao. | Giữ liên tục hoạt động. |
| **Tỷ lệ tài khoản Leaver đã vô hiệu hóa ở đích** | Tài khoản đã xác minh disabled/revoked ÷ tổng tài khoản phải thu hồi. | Kiểm soát quyền truy cập tồn dư. |
| **Số hồ sơ quá hạn lưu** | Bản ghi đã tới hạn disposition mà không có hold/căn cứ khác, vẫn chưa xử lý. | Tránh giữ dữ liệu không cần thiết. |
| **Tỷ lệ hold được rà soát đúng kỳ** | Hold được đánh giá bởi owner có thẩm quyền ÷ tổng hold tới hạn rà soát. | Ngăn hold vô thời hạn. |
| **Tỷ lệ disposition có bằng chứng** | Các tác vụ xóa/ẩn danh/hủy có kết quả được xác minh ÷ tổng tác vụ đến hạn. | Nâng khả năng giải trình. |
| **Số trường hợp restore làm sai trạng thái Leaver** | Tài khoản hoặc quyền Leaver hoạt động lại sau restore. | Đánh giá an toàn khôi phục. |
| **Tỷ lệ yêu cầu truy cập dữ liệu lưu được phê duyệt** | Lượt đọc/xuất dữ liệu lưu có căn cứ, phê duyệt và audit log phù hợp ÷ tổng lượt yêu cầu thuộc phạm vi. | Bảo vệ dữ liệu nhạy cảm. |

Mỗi chỉ số cần có phạm vi, chủ sở hữu và ngưỡng theo mức rủi ro. **Không thể kết luận hệ thống đã xóa mọi dữ liệu** chỉ từ việc một job trả về \`SUCCESS\`; cần kiểm chứng kết quả, hiểu giới hạn backup và ghi nhận các ngoại lệ.

## 15. Checklist thực hành khi xử lý Leaver

1. **Nguồn có thẩm quyền:** đã xác nhận đúng chủ thể, loại quan hệ và thời điểm Leaver có hiệu lực chưa?
2. **Truy cập:** đã vô hiệu hóa IdP và các tài khoản ứng dụng, thu hồi quyền, credential, phiên, token và tài khoản đặc quyền theo phạm vi chưa?
3. **Phân loại:** đã kiểm kê hồ sơ HR, nghiệp vụ, mailbox, log, service account, bản sao và backup liên quan chưa?
4. **Căn cứ:** mỗi nhóm hồ sơ cần giữ đã có mục đích, chủ sở hữu và retention schedule được phê duyệt chưa?
5. **Bàn giao:** tài liệu và trách nhiệm vận hành được chuyển cho owner hợp lệ, có bảo toàn lịch sử, không mở lại quyền Leaver chưa?
6. **Quyền riêng tư:** có giới hạn quyền đọc mailbox/dữ liệu cá nhân và ghi vết các lần truy xuất không?
7. **Audit:** có liên kết được sự kiện HRIS, lệnh SCIM/API, xác minh thu hồi quyền, quyết định giữ/xóa và tác vụ ngoại lệ không?
8. **Hold:** có cơ chế đặt, giám sát, gỡ yêu cầu bảo toàn chứng cứ với phạm vi và người chịu trách nhiệm rõ ràng không?
9. **Backup/restore:** có biện pháp ngăn tài khoản và quyền cũ được khôi phục từ snapshot không?
10. **Disposition:** dữ liệu hết thời hạn đã được xóa/hủy/ẩn danh theo quy trình, có đối soát bản sao và bằng chứng kết quả chưa?
11. **Service account:** có chuyển owner, rà soát secret và đóng workload không còn cần thiết không?
12. **Kiểm soát ngoại lệ:** tài khoản chưa thu hồi, dữ liệu chưa phân loại và tác vụ xóa thất bại có owner, hạn xử lý và cảnh báo không?

**Ghi nhớ:** Trong **Leaver lifecycle**, dữ liệu cần thiết có thể tiếp tục tồn tại vì nghĩa vụ hoặc mục đích hợp lệ, còn **quyền truy cập của người đã rời tổ chức phải chấm dứt theo chính sách**. Lưu giữ đúng nghĩa là phân loại hồ sơ, xác định căn cứ và thời hạn, bàn giao tài sản công việc hợp lệ, bảo vệ dữ liệu còn lưu, đối soát quyền đã thu hồi và xóa/hủy khi hết căn cứ. Cách tiếp cận này vừa duy trì khả năng vận hành và kiểm toán, vừa hạn chế dữ liệu dư thừa và truy cập tồn dư.
