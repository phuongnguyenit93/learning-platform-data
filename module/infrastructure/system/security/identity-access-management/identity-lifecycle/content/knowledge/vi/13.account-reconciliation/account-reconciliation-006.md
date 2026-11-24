# Phát hiện thuộc tính lệch trong Account reconciliation

> **Chương: Account reconciliation.** Trong quản lý vòng đời danh tính (**Identity and Access Management — IAM**), **thuộc tính lệch (attribute drift)** xuất hiện khi một hoặc nhiều thuộc tính của danh tính hay tài khoản tại hệ thống đích không khớp với **giá trị đáng lẽ phải có theo nguồn có thẩm quyền và chính sách hiện hành**. Việc phát hiện drift giúp hạn chế gán nhầm danh tính, quyết định RBAC/ABAC dựa trên dữ liệu cũ, cấp quyền sai phạm vi và để quyền truy cập tồn dư sau Joiner–Mover–Leaver.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **attribute drift**, **identity-correlation conflict**, **entitlement drift** và **độ trễ đồng bộ hợp lệ**.
2. Xác định nguồn có thẩm quyền **theo từng thuộc tính**, xây dựng giá trị mong muốn và thu thập giá trị thực tế tại HR, IAM, IdP, SCIM và ứng dụng.
3. Thiết kế phép so sánh có chuẩn hóa, quan tâm đến định danh bền vững, tenant, null/absent, thuộc tính đa giá trị, timestamp và độ đầy đủ của nguồn quan sát.
4. Liên hệ thuộc tính lệch với rủi ro **Joiner–Mover–Leaver**, RBAC/ABAC, quyền tối thiểu và kiểm toán.
5. Phân loại sai lệch theo tác động, xử lý thủ công hoặc đồng bộ tự động đúng **field ownership**, kiểm chứng kết quả và tránh vòng lặp sửa qua lại.
6. Áp dụng quy trình phát hiện, xử lý, đo lường và giám sát drift trong hệ thống phân tán.

## 1. Thuộc tính lệch là gì?

Một identity có thể xuất hiện đồng thời trong nhiều hệ thống:

- **HRIS/HCM** ghi mã nhân viên, bộ phận, quản lý trực tiếp, loại hợp đồng và ngày hiệu lực.
- **IAM/IGA** liên kết mã nguồn với identityId, tính trạng thái vòng đời và áp dụng chính sách.
- **IdP** lưu User, trạng thái đăng nhập, nhóm và một số thuộc tính tổ chức để phục vụ SSO.
- **Ứng dụng SaaS hoặc nội bộ** lưu account riêng với userName, active, department, manager, tenant hoặc các thuộc tính được đồng bộ qua SCIM/API.
- **Policy engine** có thể đọc department, employmentStatus hoặc tenantId để thực hiện ABAC.

Ví dụ, HR ghi nhân viên **An** đã chuyển từ **Support** sang **Finance** vào ngày 01/12. IAM và IdP đã cập nhật department thành Finance, nhưng CRM vẫn lưu Support. Đó có thể là **attribute drift**. Nếu CRM dùng department để xác định những hồ sơ khách hàng An được xem, sai lệch này trở thành **rủi ro phân quyền**, không chỉ là vấn đề hiển thị.

Một số sai lệch khác:

| Thuộc tính | Giá trị mong muốn | Giá trị tại đích | Nguy cơ |
| --- | --- | --- | --- |
| department | FINANCE | SUPPORT | Quyền ABAC hoặc tuyến phê duyệt tiếp tục theo phòng ban cũ. |
| manager | ID-MGR-CHI | ID-MGR-BINH | Duyệt quyền sai người, manager cũ còn xem dữ liệu cấp dưới. |
| employmentStatus | TERMINATED | ACTIVE | Đích vẫn cho phép truy cập sau Leaver. |
| endAt | 2026-12-31 | Không có giá trị | Nhà thầu có thể giữ quyền quá hạn. |
| tenantId | tenant-b | tenant-a | User bị gán sai tổ chức/phạm vi dữ liệu. |
| identity link | HRIS:EMP-2041 | Liên kết EMP-2042 | Có nguy cơ cấp quyền hoặc thu hồi nhầm người. |
| displayName | An Nguyen | An N. | Chủ yếu ảnh hưởng hiển thị nếu không dùng làm khóa hoặc điều kiện quyền. |

**Không phải mọi khác biệt đều là drift cần sửa.** Hai hệ thống có thể hiển thị tên khác nhau theo thiết kế; một bản cập nhật có thể đang trong khoảng trễ đồng bộ được chấp nhận. Cần xác định *nguồn chuẩn*, *quy tắc chuyển đổi*, *thời điểm hiệu lực*, *mức tin cậy của quan sát* và *tác động của thuộc tính* trước khi kết luận.

### Phân biệt bốn loại vấn đề

| Vấn đề | Bản chất | Ví dụ | Hướng xử lý |
| --- | --- | --- | --- |
| **Attribute drift** | Giá trị thuộc tính ở đích khác giá trị mong muốn đã chuẩn hóa. | HR ghi Finance, IdP vẫn ghi Support. | Đối soát field, kiểm tra độ mới, đồng bộ đúng nguồn. |
| **Identity-correlation conflict** | Không chắc account thuộc identity nào hoặc mapping sai. | Một SCIM User cùng externalId với hai HR person. | Dừng sửa tự động, xác minh danh tính và mapping. |
| **Entitlement drift** | Role, group hoặc quyền thực tế khác chính sách. | An còn quyền SupportAdmin. | Thu hồi/cấp quyền qua workflow, xét SoD và phê duyệt. |
| **Synchronization lag** | Giá trị mới chưa đến đích trong khoảng trễ dự kiến. | SCIM update đang chờ ứng dụng xử lý. | Theo dõi pending, retry readback, không báo sai lệch vĩnh viễn quá sớm. |

Các loại này **liên quan nhưng không đồng nhất**: department lệch có thể dẫn tới entitlement drift; role dư có thể còn dù department đã đúng. Vì vậy, kiểm tra một trường không đủ chứng minh toàn bộ quyền truy cập đã hợp lệ.

## 2. Xác định nguồn có thẩm quyền theo thuộc tính

Để phát hiện lệch, trước hết phải trả lời **ai có quyền quyết định giá trị đúng**. Không nên gọi HR hoặc IdP là nguồn chuẩn cho *mọi* trường.

| Thuộc tính | Nguồn có thẩm quyền thường gặp | Ghi chú thiết kế |
| --- | --- | --- |
| personId, employmentType | HR / hệ thống quản lý hợp đồng | Không tự lấy từ email hoặc username. |
| department, position, lineManager | HR hoặc nguồn tổ chức đã được giao quyền | Cần thời điểm hiệu lực; dự án ma trận có thể có nguồn riêng. |
| startAt, endAt, employmentStatus | HR / contract registry | Dùng để tính JML, activation và thời hạn truy cập. |
| identityId, account mappings | Hệ thống quản trị identity/IAM | Phải bảo vệ tính duy nhất và lịch sử liên kết. |
| proofing result | Quy trình/đơn vị identity proofing được ủy quyền | Không suy ra từ việc đăng nhập MFA thành công. |
| authenticator enrollment, sign-in control | IdP / hệ thống xác thực | Không tự quyết định chức danh hoặc hợp đồng. |
| role/entitlement approved | Policy engine/IGA, resource owner, PAM tùy loại quyền | Phải theo phê duyệt và thời hạn; không coi hiện trạng là chính sách. |
| app-specific profile | Ứng dụng sở hữu dữ liệu đó | Có thể hợp lệ khi khác thuộc tính HR tương tự tên gọi. |
| workload owner, service purpose | Service registry/owner kỹ thuật | Tài khoản máy không có line manager HR theo nghĩa thông thường. |

**Field ownership** là bản đồ chỉ rõ nguồn nào được ghi và nguồn nào chỉ được đọc cho từng thuộc tính. Nếu HR sở hữu department nhưng quản trị viên SaaS có thể thay department trực tiếp, hệ thống cần xem sửa tay đó là **ngoại lệ/độ lệch** hoặc đồng bộ ngược theo quy trình được phê duyệt; không tự chọn giá trị “mới nhất” từ bất kỳ nguồn nào.

### Cấu hình mapping khái niệm

Ví dụ sau chỉ mô tả ý tưởng cấu hình nội bộ, không phải chuẩn SCIM:

~~~yaml
attributeRules:
  - field: department
    authority: HRIS
    target: IDP.user.department
    transform: organizationalCodeMap
    compareAs: enum
    affectsAuthorization: true
  - field: manager
    authority: HRIS
    target: SAAS.enterpriseUser.manager.value
    transform: resolveManagerToTargetUserId
    compareAs: targetReference
    affectsAuthorization: true
  - field: displayName
    authority: HRIS
    target: CRM.user.displayName
    transform: allowedDisplayNameFormat
    compareAs: normalizedText
    affectsAuthorization: false
~~~

Trong triển khai, từng rule còn cần namespace/tenant, giá trị thiếu, phép chuẩn hóa, cách xử lý lỗi, độ trễ cho phép và owner. Trường **manager** thường cần resolve từ mã HR của người quản lý sang User ID cụ thể ở hệ thống đích; so sánh hai chuỗi ID thuộc namespace khác nhau trực tiếp là sai.

### Trạng thái mong muốn không phải bản sao của một hệ thống

Giả sử IdP hiển thị department=Support và CRM cũng hiển thị Support, nhưng HR đã chuyển An sang Finance. **Hai hệ thống đồng ý với nhau không chứng minh chúng đúng.** Desired state phải được tính từ nguồn hiện hành, rule mapping và mốc hiệu lực. Ngược lại, nếu HR chưa có hiệu lực cho việc chuyển bộ phận trong tương lai, không nên coi department đang dùng hôm nay là drift.

## 3. Trước khi so sánh: liên kết đúng identity và account

Phát hiện thuộc tính lệch bằng cách so sánh nhầm hai người có thể gây hậu quả nặng hơn việc bỏ sót drift. Mọi phép đối soát phải xác minh **identity correlation**.

Một liên kết đáng tin có thể đi qua:

~~~mermaid
flowchart LR
    H["HRIS<br/>source + personId"] --> I["IAM<br/>identityId"]
    I --> P["IdP<br/>subject / User ID"]
    I --> S["SCIM service provider<br/>User.id / externalId"]
    I --> C["Ứng dụng cục bộ<br/>localAccountId"]
    H --> E["Expected attributes<br/>version + effectiveAt"]
    P --> O["Observed attributes"]
    S --> O
    C --> O
    E --> D["Compare theo rule"]
    O --> D
    D --> F["Drift findings<br/>và mức độ rủi ro"]
~~~

### Những định danh không thể thay thế cho nhau

- **source + personId:** khóa ở nguồn HR/hợp đồng. Một personId có thể không duy nhất ngoài nguồn phát hành.
- **identityId:** khóa nội bộ của hệ thống IAM, nên ổn định trong vòng đời.
- **IdP subject/User ID:** định danh tại một issuer/IdP; cần xét issuer và tenant.
- **SCIM id:** ID tài nguyên do SCIM service provider cấp; không mặc nhiên giống employeeId.
- **SCIM externalId:** giá trị client provisioning đưa vào để đối chiếu; cần xác minh namespace, nguồn và tính duy nhất.
- **localAccountId:** khóa account tại ứng dụng cụ thể.
- **email, userName, displayName:** có thể đổi, trùng hoặc được tái sử dụng; không nên là bằng chứng duy nhất để gộp hay ghi đè account.

Ví dụ, HR mã EMP-2041 không có nghĩa SCIM User có id=EMP-2041. Một connector có thể ánh xạ EMP-2041 tới SCIM id=49fd3, trong khi externalId lưu EMP-2041. Nếu phát hiện hai account ở cùng tenant có externalId giống nhau, cần mở **identity conflict** trước khi cập nhật department hoặc disable account.

**Quy tắc an toàn:** Khi liên kết account không đủ tin cậy, đánh dấu **UNRESOLVED_IDENTITY**, không tự sửa/xóa thuộc tính của một User được tìm thấy chỉ bằng tên hoặc email.

## 4. Chuẩn hóa để không báo sai lệch giả

Các hệ thống thường lưu một ý nghĩa bằng định dạng khác nhau. Engine phải tách **khác biệt có nghĩa** khỏi **khác biệt hình thức**, nhưng không được chuẩn hóa quá mức làm che mất sự khác biệt quan trọng.

| Kiểu thuộc tính | Desired | Observed | Cách xét phù hợp |
| --- | --- | --- | --- |
| Mã phòng ban | FINANCE | FIN | Áp bảng mapping đã phê duyệt, không so text trực tiếp. |
| Thời điểm | 2026-12-01T08:00:00+07:00 | 2026-12-01T01:00:00Z | Cùng instant; so timestamp sau chuyển đổi. |
| Display name | Nguyễn Văn An | Nguyễn  Văn An | Có thể chuẩn hóa khoảng trắng cho mục đích hiển thị nếu rule cho phép. |
| Email | An@Example.Org | an@example.org | Chỉ dùng quy tắc chuẩn hóa được chính sách/provider xác nhận, không tự bỏ dấu chấm hoặc ký tự cộng. |
| Manager | HR:EMP-1004 | SCIM:scim-u-771 | Resolve mapping sang cùng identity/target ID rồi so. |
| Danh sách nhóm | [A, B] | [B, A] | Nếu nghĩa là tập hợp, so phần tử thay vì thứ tự. |
| Trạng thái | TERMINATED | active=false | Cần mapping semantics của sản phẩm, không so giá trị chuỗi. |
| Tenant | tenant-a | tenant-b | Khác biệt thực sự; không được bỏ qua namespace. |

### Phân biệt absent, null, empty và unknown

Đây là nguồn lỗi phổ biến khi đối soát:

| Trạng thái | Ý nghĩa có thể có | Xử lý |
| --- | --- | --- |
| **Absent** | Trường không được trả về, do projection/filter, quyền đọc hoặc schema không hỗ trợ. | Không tự kết luận giá trị đích rỗng; xác minh khả năng đọc. |
| **Null** | Hệ thống biểu diễn chưa có giá trị hoặc yêu cầu xóa giá trị theo quy ước. | So theo định nghĩa field và API, không gộp với absent vô điều kiện. |
| **Empty string** | Chuỗi rỗng được lưu hoặc trả về. | Có thể là giá trị không hợp lệ đối với field bắt buộc. |
| **Empty collection** | Tập giá trị được quan sát là rỗng. | Chỉ có ý nghĩa nếu phép quét chắc chắn đầy đủ. |
| **Unknown / incomplete** | Không đọc được hoặc chưa đủ bằng chứng. | Giữ trạng thái chưa kết luận; retry/điều tra quan sát. |
| **Explicit value** | Một giá trị cụ thể đủ nguồn gốc. | Chuẩn hóa và so sánh theo rule. |

Ví dụ, một SCIM response chỉ yêu cầu thuộc tính userName nên không có department. Không thể suy ra department đã bị xóa chỉ vì trường đó vắng mặt. Tương tự, lỗi thiếu trang trong kết quả truy vấn đa giá trị không thể được diễn giải là đã gỡ group.

### Các bước chuẩn hóa tối thiểu

1. **Chọn đúng rule theo field, loại danh tính, tenant và hệ thống đích.**
2. **Xác minh provenance:** nguồn nào cấp dữ liệu, thời điểm hiệu lực, version, cơ chế đọc.
3. **Giữ nguyên raw value theo chính sách lưu giữ** hoặc tham chiếu có bảo vệ để giải thích kết luận; chỉ dùng normalized value cho so sánh.
4. **Áp mapping có phiên bản:** mã tổ chức, trạng thái, loại hợp đồng, định danh manager và từ điển tenant.
5. **Đánh dấu đặc biệt các giá trị không đọc được/không tồn tại**, tránh biến tất cả thành null.
6. **Đối chiếu ý nghĩa bảo mật:** với case/Unicode hay email, chỉ dùng quy tắc tương thích với nhà cung cấp; đối với mã bảo mật, không được lowercase tùy tiện.
7. **Gắn kết quả với sourceVersion và observedAt** để tránh so một giá trị tương lai với snapshot quá khứ.

## 5. Thời điểm hiệu lực, độ mới và tính nhất quán cuối cùng

Hệ thống HR, IAM và SaaS thường đồng bộ bất đồng bộ. Một khác biệt xuất hiện trong thời gian ngắn sau Mover có thể là *pending sync*, nhưng cũng có thể là lỗi cần xử lý khẩn cấp nếu nó duy trì quyền quản trị sau Leaver.

Các mốc cần ghi:

- **sourceEffectiveAt:** giá trị HR có hiệu lực về nghiệp vụ từ khi nào?
- **sourceVersion:** bản ghi/sự kiện nguồn mới nhất là gì?
- **ingestedAt:** IAM nhận dữ liệu lúc nào?
- **provisionedAt:** thay đổi được gửi/áp dụng vào hệ thống đích lúc nào?
- **observedAt:** snapshot của đích được đọc lúc nào?
- **verifiedAt:** đến khi nào đã xác nhận giá trị/điều kiện đúng?

Ví dụ, An chuyển sang Finance lúc 08:00. Snapshot CRM đọc lúc 07:58 ghi Support **không phải bằng chứng drift sau Mover**. Snapshot 08:05 ghi Support có thể đang trong cửa sổ đồng bộ được chấp nhận; snapshot 10:00 vẫn ghi Support khi quá hạn dự kiến là một finding cần xử lý.

### Tránh sai thứ tự sự kiện

Các webhook có thể đến lặp hoặc sai thứ tự:

~~~text
HR event v41: department = Support
HR event v42: department = Finance
Connector nhận v42 trước, sau đó nhận lại v41
~~~

Nếu connector áp v41 cuối cùng chỉ vì đến sau, nó tạo ra drift mới và có thể khôi phục quyền cũ. Nên dùng **version/timestamp có thẩm quyền**, ràng buộc cập nhật có điều kiện hoặc hàng đợi theo subject. Trong phép đối soát, khi phát hiện snapshot cũ, không tự lấy dữ liệu lỗi thời làm desired state.

### Bẫy eventual consistency

- Không báo **VERIFIED** chỉ vì lệnh PATCH trả mã thành công.
- Không xem sai lệch đang chờ dưới ngưỡng trễ là đã thất bại vĩnh viễn.
- Không tự cho phép quyền thừa sau Leaver tồn tại vô hạn với lý do “đang đồng bộ”.
- Nếu API chỉ trả dữ liệu cache cũ, cần biết giới hạn độ mới hoặc dùng nguồn quan sát khác phù hợp.
- Khi quét đủ account nhưng không đủ entitlement hoặc thuộc tính, kết luận **partial coverage**, không xem toàn bộ tài khoản đã đạt.

## 6. Luồng phát hiện thuộc tính lệch end-to-end

~~~mermaid
flowchart TD
    E["Sự kiện JML / lịch quét / cảnh báo"] --> S["Tải nguồn có thẩm quyền<br/>và version hiện hành"]
    S --> R["Resolve identity và target account<br/>namespace + local ID"]
    R --> C{"Liên kết chắc chắn?"}
    C -->|Không| U["IDENTITY_CONFLICT<br/>review thủ công"]
    C -->|Có| D["Tính desired attributes<br/>field ownership + effectiveAt"]
    D --> O["Đọc observed attributes<br/>và metadata độ đầy đủ"]
    O --> Q{"Snapshot đủ và tin cậy?"}
    Q -->|Không| X["OBSERVATION_INCOMPLETE<br/>retry / owner"]
    Q -->|Có| N["Normalize theo field rules"]
    N --> F["Diff theo field<br/>và impact RBAC/ABAC"]
    F --> T{"Có drift có ý nghĩa?"}
    T -->|Không| V["MATCH / VERIFIED<br/>lưu readback"]
    T -->|Có| H["Phân loại rủi ro, nguồn và owner"]
    H --> K{"Được phép tự sửa?"}
    K -->|Không| M["Manual review / approval<br/>kiểm soát bù khi cần"]
    K -->|Có| P["Remediate idempotent<br/>đúng field owner"]
    P --> B["Readback và kiểm tra lại<br/>desired state mới nhất"]
    B --> Z{"Đã khớp?"}
    Z -->|Có| V
    Z -->|Không| Y["PARTIAL_FAILURE<br/>retry và escalation"]
~~~

### Bước 1 — Chọn phạm vi và rule

Xác định loại identity (nhân viên, nhà thầu, workload), các nguồn/destination, thuộc tính nào thuộc phạm vi, quyền đọc/ghi và owner. Dùng danh mục field đã được duyệt thay vì lấy mọi thuộc tính trong API rồi tự động sửa những thứ chưa hiểu.

### Bước 2 — Tính desired state theo thời điểm

Đọc HR/nguồn hợp đồng và sự kiện JML hiện hành; áp rule chuyển đổi và phê duyệt. Nếu Mover có ngày hiệu lực trong tương lai, chỉ cập nhật desired khi chính sách cho phép. Với Leaver đã có hiệu lực, desired access phải phản ánh việc chấm dứt truy cập, không để job cũ bật lại account.

### Bước 3 — Xác minh identity correlation

Dựa vào source key, identityId, issuer/tenant và local account ID. Nếu có account trùng hoặc mâu thuẫn, không tự gộp, đổi thuộc tính hoặc khóa account của người không xác định. Với trường hợp rủi ro cao, sử dụng quy trình điều tra và hạn chế truy cập **trong phạm vi đã xác minh**.

### Bước 4 — Đọc observed state đầy đủ

Sử dụng API/directory hợp lệ, đảm bảo pagination, filter, schema, quyền đọc và thời gian quan sát. Thu thập cả thông tin độ tin cậy: response không đầy đủ, app không hỗ trợ field, dữ liệu cache hoặc fetch timeout phải được ghi nhận.

### Bước 5 — Normalize và diff

Áp mapping theo field; so trạng thái của từng thuộc tính, không chỉ so toàn record dạng chuỗi JSON. Với manager, đối chiếu reference; với multivalue field, so các phần tử theo semantics; với timestamp, so instant; với trạng thái account, áp mapping có xét hành vi thực tế của đích.

### Bước 6 — Phân loại và quyết định

Ưu tiên drift ảnh hưởng tới định danh, trạng thái Leaver, tenant, ABAC và quyền đặc quyền. Thuộc tính hiển thị có thể xử lý theo lô. Với field do app sở hữu, không ghi đè từ HR nếu không có chính sách cho phép.

### Bước 7 — Remediate và verify

Cập nhật bằng API thích hợp, chống trùng theo khóa tác vụ, kiểm tra lifecycle/version mới nhất rồi **đọc lại trạng thái đích**. Nếu kết quả không khớp, giữ trạng thái lỗi, ghi lý do và owner; không che giấu bằng flag thành công chung.

## 7. Phát hiện drift với SCIM và IdP

**SCIM (System for Cross-domain Identity Management)** có mô hình User/Group và API phục vụ cấp phát, cập nhật và truy vấn tài khoản. Nhiều hệ thống SaaS hỗ trợ SCIM nhưng **không phải mọi ứng dụng đều lưu đủ thuộc tính hoặc có cùng semantics**.

### Ví dụ quan sát một SCIM User

Một phản hồi User minh họa:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "id": "scim-an-77",
  "externalId": "EMP-2041",
  "userName": "an@example.org",
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "EMP-2041",
    "department": "Support",
    "manager": {
      "value": "scim-binh-15",
      "displayName": "Binh"
    }
  }
}
~~~

Giả sử nguồn HR hiện có **department=Finance**, **manager=EMP-1005** (Chi) và bảng mapping xác nhận **EMP-1005 → scim-chi-21** tại SaaS này. Đối soát thấy hai drift:

1. **department:** Support ở đích so với Finance theo mapping.
2. **manager:** scim-binh-15 ở đích so với scim-chi-21 mong muốn.

Không nên kết luận chỉ bằng việc đọc manager.displayName, vì đây là nhãn hiển thị; **manager.value** tham chiếu tới User resource của người quản lý tại SCIM service provider. Đồng thời, **id**, **externalId** và **userName** có ý nghĩa khác nhau; cần kiểm tra identity mapping trước mọi cập nhật.

### Cập nhật theo phạm vi field và xác minh lại

Khi rule được duyệt và service provider hỗ trợ, có thể cập nhật department bằng SCIM PATCH minh họa:

~~~http
PATCH /scim/v2/Users/scim-an-77 HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department",
      "value": "Finance"
    }
  ]
}
~~~

Đây là ví dụ ý tưởng; hệ thống đích phải hỗ trợ schema, đường dẫn và khả năng cập nhật tương ứng. Với manager, cần resolve người quản lý đã tồn tại ở đích trước khi cập nhật reference. Sau PATCH, phải GET/readback để xác nhận giá trị, xem có rule của ứng dụng ghi đè lại không và kiểm tra quyền chịu ảnh hưởng.

### Giới hạn SCIM

- **SCIM active** không phải bản sao mặc định của trạng thái HR; mapping có thể phụ thuộc pending activation, suspension, Leaver và chính sách ứng dụng.
- **SCIM không phải hệ thống identity proofing**; một account có active=true không chứng minh người dùng đã được xác minh danh tính đủ mức.
- **SCIM không tự bảo đảm quyền thực tế**: role trực tiếp, ACL, session, PAT, token và dữ liệu cache của ứng dụng có thể nằm ngoài tài nguyên User/Group.
- **SSO/OIDC/SAML** giúp truyền kết quả xác thực/claim; claim trong phiên cũ có thể tiếp tục chứa department trước Mover. Sửa SCIM User chưa chắc làm mọi token/phiên hiện tại được làm mới ngay.
- Đối soát field phải biết **ứng dụng nào được phép ghi ngược**: một profile field người dùng tự thay đổi được không nên bị xem là drift của HR trừ khi chính sách thực sự có ownership như vậy.

## 8. Phân loại drift theo ảnh hưởng bảo mật

Không nên coi mọi sai lệch nghiêm trọng như nhau. Một tên hiển thị cũ thường khác mức rủi ro với thuộc tính trạng thái tài khoản hoặc tenant dùng để phân quyền.

| Nhóm drift | Ví dụ | Tác động | Cách phản ứng |
| --- | --- | --- | --- |
| **Identity binding** | externalId/account mapping trỏ sai người. | Có thể cấp hoặc khóa quyền nhầm chủ thể. | Ưu tiên điều tra, ngăn sửa tự động, kiểm soát đường truy cập đã xác minh. |
| **Lifecycle status** | HR đã Leaver nhưng app active=true. | Truy cập tồn dư sau chấm dứt. | Khóa/thu hồi có ưu tiên, xử lý session/credential và readback. |
| **Tenant / organizational scope** | tenantId sai, department sai được ABAC sử dụng. | Đọc dữ liệu hoặc thao tác sai phạm vi. | Sửa field, xét lại quyền và cache policy. |
| **Manager / approver relationship** | Manager cũ vẫn được nhận yêu cầu duyệt. | Duyệt sai người, quyền xem cấp dưới không phù hợp. | Cập nhật mapping, định tuyến lại approval còn chờ và rà soát quyền phụ thuộc. |
| **Contract end date** | Nhà thầu không có endAt. | Không có mốc thu hồi tự động. | Xác minh nguồn, áp chính sách thời hạn và điều tra ngoại lệ. |
| **Authentication attribute** | Email khôi phục không đúng người. | Rủi ro chiếm đoạt account hoặc recovery. | Bảo vệ luồng recovery, xác minh người sở hữu và nguồn cập nhật. |
| **Display/profile** | Tên hiển thị không cùng định dạng. | Chủ yếu gây nhầm lẫn giao diện, đôi khi ảnh hưởng nghiệp vụ. | Xử lý theo rule và lịch quét phù hợp. |

**Kết luận rủi ro phải dựa vào cách ứng dụng sử dụng thuộc tính.** Nếu một hệ thống chỉ hiển thị department thì drift có thể tác động nhỏ; nếu ABAC dùng department để cấp quyền xem hóa đơn, cùng drift đó trở thành vấn đề kiểm soát truy cập.

### Hệ quả với RBAC/ABAC

**RBAC** thường phân quyền theo role; thuộc tính HR có thể được dùng để quyết định role nào được gán. **ABAC** xét trực tiếp attribute của chủ thể, tài nguyên và bối cảnh tại lúc truy cập.

Ví dụ pseudocode:

~~~text
ALLOW invoice.read KHI
    subject.lifecycleStatus = ACTIVE
    AND subject.department = FINANCE
    AND subject.tenantId = invoice.tenantId
    AND subject.proofingRequirementSatisfied
    AND session.authStrength đủ cho dữ liệu
ELSE DENY
~~~

Nếu department ở ứng dụng vẫn là Support sau Mover, có thể gây **thiếu quyền hợp lệ**; nguy hiểm hơn, nếu chính sách dựa trên giá trị Support để cho xem dữ liệu hỗ trợ, nó có thể duy trì **quyền cũ ngoài nhu cầu**. Vì vậy, sau khi sửa thuộc tính, nên tính lại tập quyền mong muốn, kiểm tra role/ACL và xác nhận hệ thống thực thi dùng giá trị đủ mới.

## 9. Phát hiện drift trong Joiner–Mover–Leaver

| Sự kiện vòng đời | Thuộc tính cần kiểm tra | Sai lệch điển hình | Yêu cầu xử lý |
| --- | --- | --- | --- |
| **Joiner** | personId, identityId, tenant, department, manager, startAt, active. | Tạo account cho nhầm người, thiếu manager hoặc kích hoạt trước ngày. | Kiểm tra proofing/nguồn, đối sánh, đúng mốc và quyền nền tối thiểu. |
| **Mover** | department, title, manager, cost center, tenant, project scope. | Giữ giá trị bộ phận hoặc manager cũ, dẫn đến role/ABAC cũ. | Đồng bộ thuộc tính mới, gỡ quyền không còn hợp lệ, cập nhật approval. |
| **Leaver** | employmentStatus, account active, endAt, owner, credential liên quan. | App vẫn active, token còn hạn, tài khoản cục bộ không nằm trong kiểm kê. | Ưu tiên chặn truy cập, thu hồi và kiểm chứng trạng thái thực tế. |
| **Rehire** | source person mapping, account link, effective start. | Tự mở lại account cũ cùng email, phục hồi quyền cũ. | Xác minh liên kết đúng người và cấp lại quyền theo công việc hiện tại. |
| **Đổi owner dịch vụ** | serviceOwner, workload identity, trust/role mapping. | Owner cũ đã nghỉ nhưng credential vẫn được biết. | Chuyển owner, rotate credential phù hợp và rà soát quyền máy. |

### Joiner: kiểm tra trước và sau provisioning

Trước khi tạo User tại IdP hoặc gửi SCIM, xác minh khóa định danh nguồn và các trường bắt buộc; nếu manager chưa resolve được hoặc department chưa xác định, đưa vào trạng thái cần bổ sung dữ liệu theo chính sách. Sau provisioning, readback xác nhận account được tạo **đúng identity**, ở trạng thái kích hoạt và phạm vi đã được duyệt.

### Mover: phát hiện quyền dựa trên thuộc tính cũ

An chuyển phòng ban, HR cập nhật department và manager. Engine phải:

1. Xác định sourceVersion và thời điểm thay đổi hiệu lực.
2. So các thuộc tính tổ chức ở IdP và ứng dụng đích.
3. Sửa drift theo field ownership và theo dõi cache/claim đã phát hành.
4. Tính lại role/quyền theo RBAC/ABAC; thu hồi quyền nhóm cũ và cấp quyền mới khi có phê duyệt.
5. Đối soát effective permissions, không chỉ xác nhận chuỗi department đã đổi.

### Leaver: field đúng chưa đủ để đảm bảo thu hồi

HR có thể ghi TERMINATED và SCIM đã active=false, nhưng người nghỉ việc vẫn giữ PAT hoặc một phiên trong ứng dụng. Khi đó **attribute drift đã hết** nhưng **residual access chưa hết**. Quy trình Leaver phải mở rộng đối soát account, session, token, credential và quyền cục bộ theo khả năng đích.

**Không đợi xử lý hết một drift hiển thị rồi mới thu hồi truy cập Leaver.** Nên ưu tiên đường truy cập nguy hiểm và thời điểm hiệu lực.

## 10. Thuật toán phát hiện và quy tắc sửa an toàn

Pseudocode sau thể hiện tư duy một lượt kiểm tra **attribute drift**. Đây không phải mã triển khai đầy đủ của SCIM/IdP:

~~~text
detectAttributeDrift(identityId, targetSystem):
    identity = loadIdentity(identityId)
    latest = loadAuthoritativeLifecycle(identity.sourceKey)
    rules = loadApprovedFieldOwnershipRules(targetSystem)

    link = resolveAccountWithStableKeys(
        identity,
        targetSystem,
        issuerAndTenant
    )
    if link.ambiguous:
        openIdentityConflictCase(identityId, targetSystem)
        return IDENTITY_CONFLICT

    snapshot = fetchTargetAttributes(
        link.localAccountId,
        requiredFields=rules.fields
    )
    if not snapshot.complete or snapshot.stale:
        recordObservationGap(snapshot)
        return OBSERVATION_INCOMPLETE

    findings = []
    for rule in rules:
        expected = deriveFromAuthority(rule, latest)
        actual = readObservedField(snapshot, rule.field)

        if actual.isUnknown or expected.isUnresolved:
            findings.add(INDETERMINATE(rule.field))
            continue

        normalizedExpected = normalizeForField(rule, expected)
        normalizedActual = normalizeForField(rule, actual)

        if not semanticEquals(rule, normalizedExpected, normalizedActual):
            findings.add(DRIFT(
                field=rule.field,
                expected=normalizedExpected,
                observed=normalizedActual,
                risk=assessImpact(rule, latest)
            ))

    for finding in findings:
        if finding.isDrift:
            routeToOwnerOrRemediate(
                finding,
                expectedSourceVersion=latest.version
            )

    verification = readBackAfterSafeChanges(targetSystem)
    audit(identityId, rules.version, findings, verification)
    return summarize(findings, verification)
~~~

### Những nguyên tắc khi tự động sửa

- **Không tự sửa khi mapping identity mơ hồ.** Một lỗi liên kết có thể khiến công cụ cập nhật dữ liệu hoặc disable tài khoản của người khác.
- **Không ghi field mà connector không sở hữu.** Ví dụ thuộc tính hồ sơ người dùng tự điều chỉnh ở SaaS có thể khác dữ liệu HR một cách hợp lệ.
- **Không tự gán quyền đặc quyền chỉ vì phát hiện thuộc tính hoặc vai trò thiếu.** Chính sách, approval và SoD vẫn phải đạt.
- **Không ghi bằng sourceVersion cũ.** Trước khi cấp/bật account, đọc lại lifecycle mới nhất và chặn nếu Leaver có hiệu lực.
- **Không xóa dữ liệu khi quan sát chưa đầy đủ.** API timeout hoặc thiếu quyền đọc không phải bằng chứng field absent.
- **Không retry vô hạn.** Phân biệt lỗi tạm thời với mâu thuẫn dữ liệu, chính sách từ chối và đích không hỗ trợ field.
- **Không kết luận thành công khi chỉ có response ghi.** Readback và kiểm tra những hệ quả phân quyền liên quan.

### Vòng lặp hai nguồn cùng muốn ghi

Ví dụ HR quản lý department nhưng một đồng bộ ứng dụng khác liên tục đổi department của IdP về Support. Bộ đối soát có thể sửa thành Finance mỗi giờ nhưng drift quay lại sau vài phút.

Giải pháp là xác định **source of authority, field ownership và writer cạnh tranh**, ghi audit các actor thay đổi, sửa rule nguồn và khóa đường ghi sai. Không nên duy trì một vòng “cập nhật qua lại” vô hạn; nó tạo nhiễu log và có thể gây các quyết định truy cập không ổn định.

## 11. Theo dõi phát hiện drift và bằng chứng kiểm toán

Một finding nên có đủ dữ liệu để trả lời:

- **Ai?** identityId, nguồn có thẩm quyền, target account/local ID, tenant.
- **Trường nào?** tên field chuẩn, mapping rule, kiểu dữ liệu và semantics.
- **Giá trị nào?** expected/observed được chuẩn hóa, nhưng cần bảo vệ dữ liệu cá nhân và bí mật.
- **Dựa vào đâu?** sourceVersion, effectiveAt, observedAt, mức đầy đủ snapshot, policy version.
- **Rủi ro gì?** ảnh hưởng tới đăng nhập, quyền, tenant, phê duyệt hay chỉ hiển thị.
- **Ai chịu trách nhiệm?** owner, resource owner, service desk hoặc nhóm IAM.
- **Đã xử lý gì?** hành động, phê duyệt, thời điểm, trạng thái, readback và hạn theo dõi.

Ví dụ bản ghi finding nội bộ, **không phải chuẩn giao thức**:

~~~json
{
  "findingId": "drift-01294",
  "identityId": "ID-AN-2041",
  "sourceKey": "HRIS:EMP-2041",
  "sourceVersion": 42,
  "target": {
    "system": "CRM",
    "tenant": "tenant-b",
    "localAccountId": "crm-u-903"
  },
  "attribute": "department",
  "expected": "FINANCE",
  "observed": "SUPPORT",
  "effectiveAt": "2026-12-01T08:00:00+07:00",
  "observedAt": "2026-12-01T08:30:00+07:00",
  "ruleVersion": "attr-map-v8",
  "observationComplete": true,
  "classification": "AUTHORIZATION_RELEVANT_DRIFT",
  "status": "ACTION_REQUIRED",
  "owner": "IDENTITY_OPERATIONS",
  "correlationId": "mover-2041-v42"
}
~~~

Trong production, không phải mọi giá trị expected/observed đều nên lưu nguyên văn. Với dữ liệu nhạy cảm, có thể lưu mã tham chiếu, bản băm có kiểm soát hoặc thay bằng mô tả lỗi phù hợp; bảo vệ log, giới hạn quyền đọc và đặt thời hạn lưu giữ.

### Chỉ số vận hành

| Chỉ số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **Attribute coverage** | Tỷ lệ field/đích quan trọng có khả năng quan sát đầy đủ. | Không tính field không được API hỗ trợ như đã verified. |
| **Drift detection latency** | Độ trễ từ lúc nguồn thay đổi có hiệu lực tới lúc phát hiện sai lệch. | Phân biệt so với thời điểm webhook đến. |
| **Time to remediate** | Thời gian từ finding đến khi readback đạt. | Ưu tiên lifecycle/authorization drift. |
| **Critical drift count** | Sai lệch liên quan identity binding, account active, tenant, đặc quyền. | Cần điều tra tác động truy cập thực tế. |
| **Repeated drift rate** | Sai lệch bị sửa rồi xuất hiện trở lại. | Tìm nguồn ghi cạnh tranh hoặc mapping sai. |
| **Unresolved identity conflicts** | Tài khoản không thể nối chắc chắn với identity. | Không tự sửa dựa vào email; theo dõi quyền rủi ro. |
| **Observation gaps** | API thiếu field, thiếu trang, lỗi fetch hoặc dữ liệu stale. | Bảo vệ chống kết luận giả absent. |
| **Incorrect remediation incidents** | Sửa nhầm field/người/tenant. | Đo chất lượng mapping và kiểm soát phê duyệt. |
| **Residual access after JML** | Quyền còn lại sau Mover/Leaver do sai lệch thuộc tính hoặc quyền. | Kết hợp entitlement/session/credential reconciliation. |

Tần suất quét nên dựa trên rủi ro: các trường chi phối quyết định truy cập nhạy cảm hoặc Leaver thường cần theo dõi sát hơn displayName. Không áp một ngưỡng thời gian cố định cho tất cả ứng dụng.

## 12. Các tình huống thực hành

### Tình huống A — Department lệch sau Mover

**Bối cảnh:** HR ghi An đã chuyển sang Finance từ 08:00, IdP đúng Finance, CRM vẫn Support lúc 09:30. CRM dùng department làm điều kiện ABAC.

**Câu hỏi:** Đâu là điều kiện để kết luận drift có ý nghĩa và cách xử lý?

**Gợi ý:** Kiểm tra phiên bản HR, mốc hiệu lực, độ trễ đồng bộ cho phép, completeness của CRM readback và mapping department. Nếu drift vượt hạn hợp lệ, cập nhật theo field ownership; đồng thời đánh giá quyền ABAC/role cũ, cache và phiên còn hiệu lực, không dừng ở việc sửa chuỗi department.

### Tình huống B — Manager hiển thị khác nhưng reference đúng

**Bối cảnh:** HR gọi người quản lý là “Nguyễn Thị Chi”, SaaS hiển thị “Chi Nguyen”. Cả hai tham chiếu tới cùng identity và SCIM User ID.

**Câu hỏi:** Có nhất thiết báo drift của quan hệ manager không?

**Gợi ý:** Không. So manager reference theo identity mapping, không chỉ so displayName. Nếu mục đích là đồng bộ nhãn hiển thị, xử lý bằng rule riêng với mức ưu tiên phù hợp.

### Tình huống C — Một field không được trả về

**Bối cảnh:** Connector gọi API lấy userName và active; response không chứa endAt. Engine đánh dấu endAt đã bị xóa, rồi tự cập nhật account.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** Field vắng mặt có thể do projection hoặc API không hỗ trợ, không chứng minh giá trị null. Cần phân biệt absent/unknown, kiểm tra schema/khả năng quan sát trước khi diff/remediate.

### Tình huống D — Hai User cùng externalId

**Bối cảnh:** Một SaaS có hai account cùng externalId=EMP-2041; một account có quyền quản trị.

**Câu hỏi:** Có thể lấy tài khoản đầu tiên rồi đồng bộ department không?

**Gợi ý:** Không. Đây là identity-correlation conflict. Phải đối chiếu nguồn, tenant, local ID, bằng chứng liên kết và owner; tránh sửa hoặc khóa nhầm. Các đường quyền đã xác minh là rủi ro cần được kiểm soát theo quy trình.

### Tình huống E — Leaver đã active=false nhưng vẫn còn quyền

**Bối cảnh:** HR xác nhận Leaver và SCIM User active=false. Tuy nhiên, Git vẫn chấp nhận PAT cũ.

**Câu hỏi:** Có thể kết luận attribute reconciliation đã bảo đảm offboarding không?

**Gợi ý:** Không. Account state có thể đúng nhưng residual access vẫn tồn tại. Cần token/credential reconciliation, revoke phù hợp và xác minh riêng đường truy cập Git.

### Tình huống F — Đồng bộ ngược liên tục

**Bối cảnh:** IAM đặt department=Finance; một integration khác đổi về Support hàng giờ, và reconciliation cứ sửa lại Finance.

**Câu hỏi:** Đâu là giải pháp bền vững?

**Gợi ý:** Xác định writer và field owner, kiểm tra log, quyền ghi và cấu hình mapping. Sửa nguồn ghi cạnh tranh hoặc ràng buộc quyền cập nhật. Đừng chỉ tăng tần suất reconciliation.

## 13. Câu hỏi tự kiểm tra

**1. Hai hệ thống cùng ghi department=Support có chứng minh dữ liệu đúng không?**

Không. Cần đối chiếu nguồn có thẩm quyền, phiên bản và thời điểm hiệu lực; cả hai có thể đã đồng bộ từ một snapshot cũ.

**2. Vì sao không nên so managerEmployeeId với SCIM manager.value như hai chuỗi thông thường?**

Vì chúng thuộc hai namespace khác nhau. Phải resolve manager HR tới đúng User ID của service provider rồi so trên cùng hệ quy chiếu.

**3. Nếu API đích không trả department, có được coi là drift kiểu “department bị xóa” không?**

Không tự động. Phải xác minh API có yêu cầu và được phép đọc field đó hay không; nếu chưa rõ, kết luận observation incomplete.

**4. Một thuộc tính đã khớp nhưng role cũ vẫn còn sau Mover. Account đã hoàn toàn đúng chưa?**

Chưa. Attribute và entitlement drift là hai lớp kiểm tra; cần xét role, ACL, session và quyền hiệu lực.

**5. Tại sao cần lưu sourceVersion và effectiveAt cho một finding?**

Để phân biệt snapshot mới/cũ, tránh xử lý sự kiện sai thứ tự và so giá trị theo đúng thời điểm nghiệp vụ.

**6. Khi mapping identity mơ hồ, có nên tự xóa account theo email không?**

Không. Cần identity resolution có bằng chứng và kiểm soát rủi ro; email có thể đổi hoặc tái sử dụng.

**7. Với Leaver, tại sao active=false chưa đủ?**

Vì tài khoản cục bộ khác, token đã phát hành, session hoặc credential có thể còn sử dụng được; phải kiểm tra và thu hồi ở từng đường truy cập.

## Ghi nhớ

- **Phát hiện thuộc tính lệch** là so sánh **giá trị mong muốn từ nguồn có thẩm quyền** với **giá trị thực tế của đúng account**, sau khi chuẩn hóa theo semantics và thời điểm hiệu lực.
- **Field ownership, identity correlation và mapping có phiên bản** quyết định phép diff có ý nghĩa; không lấy email/displayName làm khóa liên kết duy nhất.
- **Absent, null, empty, unknown, pending và mismatch** phải được phân biệt; quan sát chưa đầy đủ không chứng minh thuộc tính đã bị xóa hay đúng.
- **Joiner** cần đúng nguồn, thuộc tính và activation; **Mover** phải đồng bộ thuộc tính tổ chức và thu hồi quyền cũ; **Leaver** cần trạng thái không còn quyền truy cập được xác minh.
- **SCIM/IdP/SSO** hỗ trợ tài khoản, đồng bộ và đăng nhập; **RBAC/ABAC** có thể sử dụng thuộc tính để thực thi quyền. Sửa field chưa chắc rút mọi token, phiên hoặc đặc quyền.
- **Phân loại rủi ro, remediation đúng owner, idempotency, kiểm tra version, readback và audit** giúp xử lý drift mà không gây sửa nhầm người, cấp quyền dư hoặc vòng lặp đồng bộ.
