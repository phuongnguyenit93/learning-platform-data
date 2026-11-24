# Gán thuộc tính chuẩn khi đăng ký danh tính (Identity enrollment)

Khi một nhân viên gia nhập tổ chức, hệ thống nhân sự có thể gửi các giá trị như mã nhân viên, họ tên, phòng ban, chức danh và ngày bắt đầu. Tuy nhiên, từng hệ thống đích có thể đặt tên trường khác nhau, dùng các mã phòng ban khác nhau hoặc hiểu trạng thái tài khoản theo cách riêng. Nếu IAM sao chép trực tiếp dữ liệu mà không kiểm tra và chuẩn hóa, danh tính có thể bị gắn sai, cấp quyền sai hoặc không được thu hồi khi quan hệ làm việc thay đổi.

**Gán thuộc tính chuẩn** là quá trình nhận các thuộc tính từ nguồn có thẩm quyền, xác minh ý nghĩa và chất lượng dữ liệu, đưa chúng về **mô hình danh tính thống nhất**, sau đó ánh xạ có kiểm soát sang IdP và những ứng dụng cần sử dụng. Đây là một bước quan trọng của **Identity enrollment**: đăng ký một danh tính đủ tin cậy để các bước tạo tài khoản, xác thực, SSO, cấp quyền và quản trị vòng đời tiếp theo hoạt động chính xác.

Bài học thuộc mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE** về quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**. Trọng tâm là gán thuộc tính chuẩn cho các danh tính nhân viên, nhà thầu và chủ thể liên quan; đồng thời liên kết thực tế với **HRIS, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và việc giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt thuộc tính nguồn, thuộc tính chuẩn của IAM, thuộc tính tài khoản ở hệ thống đích và quyền truy cập.
- Xây dựng bảng ánh xạ thuộc tính kèm nguồn có thẩm quyền, kiểu dữ liệu, cách kiểm tra và quy tắc cập nhật.
- Giải thích các điểm cần chú ý khi đồng bộ thuộc tính qua **SCIM**, khi phát hành claim qua **OIDC/SAML** và khi dùng thuộc tính trong **RBAC/ABAC**.
- Xử lý thuộc tính trống, sai định dạng, trùng, mâu thuẫn, thay đổi theo thời gian và trường hợp tái tuyển dụng.
- Truy vết vì sao một danh tính có thuộc tính hoặc quyền nhất định và xác minh dữ liệu tại hệ thống đích.

## 1. Thuộc tính chuẩn là gì và vì sao phải gán?

**Thuộc tính danh tính (identity attribute)** là một thông tin về chủ thể: mã nhận diện, loại quan hệ với tổ chức, tên, phòng ban, đơn vị, trạng thái hoặc người quản lý. **Thuộc tính chuẩn (canonical attribute)** là thuộc tính được IAM định nghĩa thống nhất về **tên, ý nghĩa, kiểu dữ liệu, tập giá trị hợp lệ, nguồn tin cậy và quy tắc cập nhật**.

Ví dụ ba nguồn có thể biểu diễn cùng một khái niệm theo các cách khác nhau:

| Hệ thống nguồn | Trường | Giá trị | Ý nghĩa nghiệp vụ |
| --- | --- | --- | --- |
| HRIS A | \`dept_code\` | \`FIN\` | Phòng Tài chính. |
| HRIS B | \`organizationUnit\` | \`Finance\` | Phòng Tài chính. |
| Hệ thống nhà thầu | \`cost_center_unit\` | \`D020\` | Có thể là mã trung tâm chi phí, **chưa chắc** tương đương phòng ban. |

IAM có thể chuẩn hóa hai giá trị đầu thành \`departmentId=FINANCE\` sau khi tra bảng mã được quản trị. Không được tự gán \`D020\` thành \`FINANCE\` nếu chưa có quy tắc ánh xạ chính thức; **các trường có tên gần giống có thể biểu đạt khái niệm khác nhau**.

Gán thuộc tính chuẩn giúp:

1. **Định danh đúng người:** sử dụng mã chủ thể và khóa nguồn ổn định để liên kết tài khoản.
2. **Cấp quyền nhất quán:** tính vai trò/quyền từ các thuộc tính đã xác minh, tránh phụ thuộc tên trường của từng hệ thống.
3. **Đồng bộ có kiểm soát:** chuyển dữ liệu sang IdP và ứng dụng qua SCIM/API với kiểu và ý nghĩa phù hợp.
4. **Cập nhật vòng đời:** khi chuyển bộ phận, tạm ngưng hoặc rời tổ chức, các hệ thống nhận thay đổi đúng ngữ nghĩa.
5. **Kiểm toán được:** truy ngược từ thuộc tính hiện tại đến nguồn, phiên bản, thời điểm hiệu lực và quyết định thay đổi.

**Gán thuộc tính chuẩn không phải là cấp quyền.** Ví dụ, \`departmentId=FINANCE\` chỉ là thông tin về chủ thể; quyền \`finance-report-read\` chỉ được cấp nếu chính sách RBAC/ABAC và các phê duyệt áp dụng cho phép.

## 2. Phân biệt các lớp dữ liệu trong enrollment

Một lỗi thiết kế thường gặp là trộn thông tin về *con người*, *quan hệ làm việc*, *tài khoản* và *quyền* vào cùng một đối tượng mà không biết trường nào thuộc lớp nào.

| Lớp | Câu hỏi | Ví dụ | Nguyên tắc |
| --- | --- | --- | --- |
| **Person/Subject** | Chủ thể này là ai? | \`subjectId=person-1042\`. | Có định danh ổn định, không dùng lại cho người khác. |
| **Engagement** | Chủ thể có quan hệ nào với tổ chức? | \`engagementId=EMP-5812\`, \`workerType=EMPLOYEE\`, \`startDate\`. | Một người có thể có nhiều giai đoạn hoặc loại quan hệ. |
| **Identity profile** | IAM đang tin vào những thuộc tính nào? | \`departmentId\`, \`managerSubjectId\`, \`lifecycleState\`. | Có nguồn, phiên bản, chất lượng và thời điểm hiệu lực. |
| **Account** | Chủ thể có tài khoản ở đâu? | \`idpAccountId\`, \`scimUserId\`, \`userName\`. | Một chủ thể có thể có nhiều tài khoản. |
| **Credential** | Tài khoản được xác thực bằng gì? | Passkey, mật khẩu, chứng chỉ, token. | Bảo vệ và quản lý vòng đời riêng; không lưu bí mật trong hồ sơ thuộc tính. |
| **Entitlement** | Tài khoản/chủ thể có quyền gì? | Role, nhóm, quyền API hoặc phạm vi dữ liệu. | Quyền được quyết định theo chính sách và có thể bị thu hồi. |

Ví dụ, nhân viên Hà chuyển sang phòng ban mới: \`subjectId\` của Hà thường **giữ nguyên**, còn \`departmentId\`, \`jobCode\` và quyền ứng dụng thay đổi theo thời điểm hiệu lực. Nếu Hà nghỉ việc và được tuyển lại, hồ sơ *Person* có thể được liên kết sau xác minh, trong khi **engagement mới** cần ngày bắt đầu và phê duyệt quyền mới.

### 2.1. Khóa định danh không được nhầm với thuộc tính hiển thị

- **\`subjectId\`**: khóa nội bộ ổn định của IAM đại diện cho đúng chủ thể trong phạm vi quản lý.
- **\`sourcePersonId\` / \`engagementId\`**: ID do nguồn có thẩm quyền cấp, dùng để truy ngược hồ sơ và giai đoạn làm việc.
- **\`accountId\`**: ID của đối tượng tài khoản tại IdP hoặc một ứng dụng.
- **\`userName\` / email**: thuộc tính đăng nhập hoặc liên hệ; có thể đổi, trùng hoặc được tái sử dụng.

Đối với OpenID Connect (**OIDC**), bên nhận thường định danh người dùng bằng cặp **issuer + \`sub\`**; không nên coi riêng \`sub\` là khóa chung giữa mọi nhà cung cấp danh tính. Đối với SCIM, \`id\` của tài nguyên do **service provider** cấp; \`externalId\` là mã tham chiếu do **provisioning client** quản lý trong phạm vi tích hợp, không phải ID toàn cục bắt buộc duy nhất giữa mọi hệ thống.

## 3. Thiết kế bộ thuộc tính chuẩn

Không có một danh sách trường cố định phù hợp mọi doanh nghiệp. Dưới đây là **mô hình minh họa** cho IAM quản lý Employee/Contractor; tổ chức cần thống nhất ý nghĩa, tính bắt buộc và kiểm soát trước khi triển khai.

| Thuộc tính chuẩn | Kiểu/giá trị gợi ý | Nguồn có thẩm quyền | Mục đích |
| --- | --- | --- | --- |
| \`subjectId\` | ID bất biến, duy nhất trong miền IAM | Dịch vụ đăng ký danh tính | Liên kết mọi tài khoản và sự kiện với đúng chủ thể. |
| \`subjectType\` | \`PERSON\`, \`WORKLOAD\` | Quy trình xác minh/chủ sở hữu dịch vụ | Phân biệt con người và danh tính máy. |
| \`sourceSystem\` | ID hệ thống | Cấu hình tích hợp được phê duyệt | Truy vết nguồn của thuộc tính. |
| \`sourcePersonId\` | Chuỗi theo namespace nguồn | HRIS hoặc nguồn người có thẩm quyền | Đối chiếu hồ sơ cá nhân. |
| \`engagementId\` | Chuỗi duy nhất trong nguồn | HRIS/hệ thống hợp đồng | Phân biệt các giai đoạn làm việc. |
| \`workerType\` | \`EMPLOYEE\`, \`CONTRACTOR\`, v.v. | HRIS/hợp đồng/sponsor | Chọn chính sách vòng đời phù hợp. |
| \`lifecycleState\` | \`PENDING\`, \`ACTIVE\`, \`SUSPENDED\`, \`TERMINATED\` | IAM tính từ sự kiện nguồn và chính sách | Điều phối mở/khóa truy cập. |
| \`legalName\` | Đối tượng họ/tên theo nguồn | Nguồn nhân sự đã xác minh | Định danh con người theo quy trình hợp lệ. |
| \`displayName\` | Chuỗi có Unicode | Quy trình quản lý hồ sơ được chấp thuận | Hiển thị; không làm khóa định danh. |
| \`workEmail\` | Email công việc, có trạng thái xác minh | Directory/HR theo phân định | Thông báo hoặc đăng nhập khi được phép. |
| \`departmentId\` | Mã bộ phận từ bảng mã thống nhất | Nguồn tổ chức được phân quyền | Xác định cơ cấu và quy tắc cấp quyền. |
| \`jobCode\` | Mã chức danh chuẩn | HRIS | Tính vai trò nghiệp vụ. |
| \`managerSubjectId\` | Tham chiếu \`subjectId\` hợp lệ | HRIS + dịch vụ đối chiếu danh tính | Xác định tuyến phê duyệt và quan hệ quản lý. |
| \`startDate\`, \`endDate\` | ISO 8601 date-only | HRIS/hợp đồng | Xác định thời gian quan hệ có hiệu lực. |
| \`effectiveAt\` | Timestamp có múi giờ | Nguồn sự kiện/quy tắc IAM | Áp dụng thay đổi đúng thời điểm. |
| \`attributeVersion\` | Số phiên bản hoặc mã phiên bản | Kho danh tính IAM | Ngăn sự kiện cũ ghi đè dữ liệu mới. |

Các tên như \`subjectId\`, \`workerType\` và \`lifecycleState\` ở bảng trên là **thuộc tính chuẩn nội bộ minh họa**, không mặc nhiên là trường gốc của SCIM, OIDC hoặc SAML.

### 3.1. Ai sở hữu từng thuộc tính?

Nên xây dựng **ma trận thẩm quyền theo từng thuộc tính**, thay vì tuyên bố “HRIS là nguồn duy nhất cho mọi trường”:

| Nhóm thuộc tính | Nguồn được ưu tiên | Ai có thể cập nhật? | Điều cần kiểm tra |
| --- | --- | --- | --- |
| Quan hệ lao động, ngày bắt đầu/kết thúc | HRIS hoặc hệ thống hợp đồng | HR/quy trình được ủy quyền | Trạng thái hồ sơ, ngày hiệu lực và phiên bản. |
| Đơn vị/phòng ban, quản lý | Hệ thống tổ chức hoặc HRIS theo quy định | Bộ phận sở hữu dữ liệu tổ chức | Mã bộ phận tồn tại, người quản lý hợp lệ. |
| Email và tên đăng nhập | Directory/IdP hoặc nguồn được ủy quyền | Dịch vụ quản lý tài khoản | Không trùng trong phạm vi ứng dụng, có quy tắc đổi tên. |
| Kết quả xác minh danh tính | Quy trình identity proofing | Nhân sự/đơn vị xác minh được ủy quyền | Bằng chứng, mức tin cậy, thời điểm xác minh. |
| Trạng thái tài khoản tại một ứng dụng | Chính ứng dụng/connector | Hệ thống provisioning có quyền | Đọc lại trạng thái, xử lý lỗi đồng bộ. |
| Phê duyệt quyền ngoại lệ | Owner ứng dụng/người quản lý thích hợp | Người được ủy quyền phê duyệt | Phạm vi, lý do, thời hạn và xung đột nhiệm vụ. |

Khi các nguồn mâu thuẫn, **không chọn giá trị “đến sau cùng” một cách mù quáng**. Cần quy định nguồn chủ sở hữu, mức ưu tiên, ngày hiệu lực và quy trình giải quyết xung đột cho từng trường.

## 4. Quy trình gán thuộc tính chuẩn

~~~mermaid
flowchart TD
    A["Nguồn có thẩm quyền<br/>HRIS / hợp đồng / owner workload"] --> B["Kiểm tra nguồn, chữ ký / quyền gửi,<br/>schema và phiên bản"]
    B --> C["Giải quyết đúng subject<br/>và engagement"]
    C --> D{"Trùng hoặc<br/>mâu thuẫn?"}
    D -->|Có| E["Chờ kiểm tra thủ công<br/>có ghi nhận bằng chứng"]
    D -->|Không| F["Chuẩn hóa kiểu dữ liệu,<br/>mã giá trị, ngày hiệu lực"]
    F --> G["Kiểm tra ràng buộc<br/>và nguồn sở hữu thuộc tính"]
    G --> H["Lưu profile chuẩn<br/>kèm provenance/version"]
    H --> I["Tính lifecycle + quyền<br/>theo chính sách"]
    I --> J["Ánh xạ tới IdP,<br/>SCIM/API và SSO claims"]
    J --> K["Đọc lại và đối soát<br/>trạng thái tại hệ thống đích"]
    K --> L["Lưu dấu vết kiểm toán"]
~~~

### Bước 1. Nhận dữ liệu có xác thực

Chỉ tiếp nhận dữ liệu từ nguồn hoặc kênh đã được đăng ký. Kiểm tra danh tính của hệ thống gửi, quyền phát sự kiện, định dạng, kiểu trường, ID sự kiện và phiên bản bản ghi. Một file CSV do người dùng gửi qua email không tự trở thành nguồn đáng tin cậy cho thuộc tính phân quyền.

### Bước 2. Xác định đúng danh tính và quan hệ

Tra cứu bằng ID ổn định và namespace của nguồn. Kiểm tra hồ sơ người trùng tên, tái tuyển dụng và chuyển từ Contractor sang Employee. Nếu có nhiều ứng viên mà không đủ bằng chứng kết nối, chuyển sang quy trình xác minh thủ công; **không tự chọn tài khoản trùng email**.

### Bước 3. Chuẩn hóa dữ liệu và ánh xạ mã

Biến giá trị nguồn thành bộ giá trị đã được định nghĩa. Ví dụ \`FIN\` và \`FINANCE_DIV\` chỉ trở thành \`FINANCE\` nếu bảng ánh xạ của phiên bản hiện tại xác nhận chúng cùng ý nghĩa. Đối với trường không có ánh xạ, đưa vào trạng thái cần xử lý thay vì tự tạo mã tùy ý.

### Bước 4. Kiểm tra chất lượng và quan hệ phụ thuộc

Kiểm tra trường bắt buộc, mã đơn vị tồn tại, ngày hợp lệ, manager có chủ thể tương ứng, email có định dạng phù hợp và mối liên hệ giữa \`workerType\` với nguồn. Những trường dùng để quyết định quyền hoặc trạng thái truy cập cần kiểm soát nghiêm hơn trường chỉ phục vụ hiển thị.

### Bước 5. Ghi profile chuẩn và nguồn gốc dữ liệu

Lưu giá trị đã chuẩn hóa kèm nguồn, thời điểm nguồn ghi nhận, thời điểm có hiệu lực, phiên bản và kết quả xác minh. Phải truy được **giá trị đến từ đâu và vì sao được chấp nhận**.

### Bước 6. Tính trạng thái, cấp tài khoản và quyền

Dùng profile chuẩn làm đầu vào cho chính sách JML, RBAC/ABAC và những phê duyệt cần thiết. Chỉ gửi thuộc tính mà ứng dụng thực sự cần. Việc ghi một giá trị vào IdP không đồng nghĩa mọi ứng dụng đã nhận đúng giá trị hoặc tự thu hồi quyền cũ.

### Bước 7. Xác minh tại hệ thống đích

Kiểm tra kết quả tạo/cập nhật tài khoản qua SCIM/API, đọc lại các trường thiết yếu khi cần, xác nhận tài khoản và quyền phù hợp. Nếu lệnh thất bại, ghi trạng thái và mở tác vụ xử lý thay vì đánh dấu enrollment hoàn tất.

## 5. Quy tắc chuẩn hóa dữ liệu cần quy định rõ

### 5.1. Mã định danh và mã nghiệp vụ

Định danh như \`EMP-0012\` nên được lưu dưới dạng **chuỗi**, tránh chuyển sang số làm mất số 0 ở đầu. ID nguồn phải được hiểu trong namespace hệ thống phát hành: \`HRIS-A:0012\` và \`HRIS-B:0012\` không mặc nhiên là cùng một người.

Với các trường có tập mã (\`workerType\`, \`departmentId\`, \`countryCode\`, \`jobCode\`), duy trì bảng mã có **phiên bản**, owner và quy trình sửa. Không đồng nhất mã trung tâm chi phí với phòng ban nếu chưa có quy định.

### 5.2. Họ tên và Unicode

Tên người có thể có dấu tiếng Việt, nhiều thành phần, ký tự đặc biệt hoặc cách cấu trúc không theo mô hình “first name/last name” đơn giản. Chỉ chuẩn hóa Unicode theo một quy tắc nhất quán đã đánh giá; **không tự xóa dấu, đảo thứ tự tên hoặc viết hoa toàn bộ** làm mất giá trị gốc. Có thể lưu riêng \`legalName\`, \`preferredName\` và \`displayName\` khi có nhu cầu hợp lệ và nguồn đáng tin cậy.

### 5.3. Email và số điện thoại

Email có thể thay đổi, bị tái sử dụng hoặc chưa được xác minh. Kiểm tra cú pháp và sự trùng lặp theo quy tắc của dịch vụ đích; **không tự chuyển toàn bộ phần trước @ sang chữ thường** rồi coi đó là định danh giống nhau nếu nhà cung cấp không bảo đảm quy tắc so sánh ấy. Nếu dùng email để gửi mã kích hoạt, phải có bước xác nhận quyền kiểm soát kênh liên lạc thích hợp.

Số điện thoại có thể chuẩn hóa theo định dạng được thống nhất như E.164 nếu cần, nhưng không nên coi đó là ID bền vững hoặc căn cứ đủ để gắn hai hồ sơ danh tính.

### 5.4. Ngày, thời gian và múi giờ

**\`startDate=2026-12-01\`** là một ngày lịch; còn **\`effectiveAt=2026-12-01T08:00:00+07:00\`** là một thời điểm có múi giờ. Hệ thống phải biết chính sách chuyển từ ngày nhân sự sang thời điểm kích hoạt. Không mặc định một ngày theo lịch nghĩa là **00:00 UTC**, nhất là với nhân viên ở nhiều quốc gia.

Khi nguồn gửi thay đổi trong tương lai, lưu ngày hiệu lực và lên lịch áp dụng; tác vụ đến hạn phải **kiểm tra lại phiên bản trạng thái mới nhất** trước khi cấp/thu hồi quyền.

### 5.5. Trống, thiếu và xóa không mang cùng ý nghĩa

Một thông điệp cập nhật có thể biểu diễn các tình huống khác nhau:

| Tình huống | Diễn giải đúng | Cách xử lý gợi ý |
| --- | --- | --- |
| Không có trường \`managerId\` trong sự kiện thay đổi bộ phận. | Sự kiện không cập nhật thông tin quản lý. | Giữ giá trị cũ nếu ngữ nghĩa API là cập nhật một phần. |
| \`managerId=null\` trong bản ghi đầy đủ. | Có thể là giá trị chưa biết hoặc yêu cầu xóa, tùy hợp đồng dữ liệu. | Áp dụng quy ước nguồn; không tự xóa/giữ nếu không rõ. |
| \`managerId=""\`. | Chuỗi rỗng, có thể không hợp lệ. | Kiểm tra định dạng và chính sách làm sạch dữ liệu. |
| \`departmentId\` mang mã không thuộc bảng mã. | Chưa thể xác nhận đơn vị. | Cách ly thay đổi phụ thuộc mã này, cảnh báo owner dữ liệu. |
| Trường bị yêu cầu xóa rõ ràng bằng thao tác PATCH/điều khiển đã định nghĩa. | Yêu cầu xóa có chủ đích. | Kiểm tra quyền sửa và tác động đến chính sách truy cập trước khi áp dụng. |

Đặc biệt lưu ý: trong SCIM, **PUT** và **PATCH** có ngữ nghĩa cập nhật khác nhau; không áp dụng một quy tắc “thiếu trường = xóa” chung cho tất cả nguồn và giao thức.

## 6. Ví dụ ánh xạ từ HRIS sang profile chuẩn

Giả sử HRIS gửi dữ liệu:

~~~json
{
  "eventId": "hr-evt-9201",
  "sourceSystem": "hris-primary",
  "recordVersion": 8,
  "employee": {
    "personKey": "P000842",
    "employmentKey": "EMP-5812",
    "fullName": "Nguyễn Thị Mai",
    "deptCode": "FIN",
    "positionCode": "ACC2",
    "directManagerKey": "P000517",
    "companyEmail": "mai.nguyen@example.test",
    "startDate": "2026-12-01",
    "employmentState": "ONBOARDING"
  }
}
~~~

Các giá trị ở đây là **dữ liệu giả định**, dùng để minh họa quy trình:

| Trường nguồn HRIS | Thuộc tính chuẩn của IAM | Quy tắc |
| --- | --- | --- |
| \`personKey\` | \`sourcePersonId\` | Gắn kèm \`sourceSystem\`; tra hoặc tạo \`subjectId\` sau xác minh. |
| \`employmentKey\` | \`engagementId\` | Giữ nguyên kiểu chuỗi và namespace nguồn. |
| \`fullName\` | \`displayName\` | Giữ Unicode; chỉ phân tách họ/tên nếu có dữ liệu hoặc quy tắc đáng tin cậy. |
| \`deptCode=FIN\` | \`departmentId=FINANCE\` | Tra bảng ánh xạ đã phê duyệt. |
| \`positionCode=ACC2\` | \`jobCode=ACCOUNTANT_LEVEL_2\` | Tra bảng mã có phiên bản. |
| \`directManagerKey\` | \`managerSubjectId\` | Resolve ID nguồn sang đúng subject của quản lý. |
| \`companyEmail\` | \`workEmail\` | Kiểm tra chính sách email/ứng dụng; không dùng làm khóa chủ thể. |
| \`startDate\` | \`startDate\` | Giữ dạng ngày lịch, bổ sung chính sách timezone khi tính kích hoạt. |
| \`employmentState=ONBOARDING\` | \`lifecycleState=PENDING\` | Dùng bảng trạng thái và điều kiện enrollment, không ánh xạ mặc định sang account active. |

Sau khi các bước xác minh và ánh xạ thành công, IAM có thể lưu profile như:

~~~json
{
  "subjectId": "person-1042",
  "subjectType": "PERSON",
  "sourceSystem": "hris-primary",
  "sourcePersonId": "P000842",
  "engagementId": "EMP-5812",
  "workerType": "EMPLOYEE",
  "lifecycleState": "PENDING",
  "displayName": "Nguyễn Thị Mai",
  "workEmail": "mai.nguyen@example.test",
  "departmentId": "FINANCE",
  "jobCode": "ACCOUNTANT_LEVEL_2",
  "managerSubjectId": "person-778",
  "startDate": "2026-12-01",
  "attributeVersion": 8,
  "mappingVersion": "hr-to-iam-v3",
  "sourceEventId": "hr-evt-9201"
}
~~~

Đây là **schema chuẩn nội bộ minh họa**. \`subjectId=person-1042\` và \`managerSubjectId=person-778\` chỉ được ghi sau khi có bằng chứng liên kết từ các ID nguồn tới đúng chủ thể. Không tự tạo kết quả này bằng cách đoán họ tên.

## 7. Ánh xạ thuộc tính chuẩn sang SCIM

**SCIM (System for Cross-domain Identity Management)** hỗ trợ quản lý tài nguyên người dùng và nhóm giữa hệ thống cấp phát và ứng dụng đích. SCIM có schema chuẩn cho **User** và **Group**, đồng thời hỗ trợ extension. Dữ liệu chuẩn của IAM cần được ánh xạ theo schema mà **service provider** thực tế hỗ trợ.

### 7.1. Những trường SCIM cần hiểu đúng

| Trường SCIM | Ý nghĩa và lưu ý |
| --- | --- |
| \`id\` | ID tài nguyên do service provider gán; thường xuất hiện trong phản hồi khi tạo tài khoản. |
| \`externalId\` | Mã tham chiếu do client cung cấp để đối chiếu tài nguyên; duy nhất/toàn cục hay không phụ thuộc phạm vi tích hợp. |
| \`userName\` | Tên người dùng bắt buộc trong SCIM User, phải duy nhất theo phạm vi mà service provider quy định. |
| \`name\` | Đối tượng tên có thể có \`formatted\`, \`givenName\`, \`familyName\`; không tự chia tên nếu dữ liệu nguồn không đáng tin. |
| \`displayName\` | Tên hiển thị; có thể đổi, không làm khóa đối sánh danh tính. |
| \`emails\` | Thuộc tính nhiều giá trị; mỗi mục có thể có \`value\`, \`type\`, \`primary\`. |
| \`active\` | Trạng thái hoạt động của **tài khoản người dùng tại service provider**; không đồng nhất trực tiếp với tình trạng hợp đồng. |
| \`groups\` | Các nhóm liên quan; cách đồng bộ nhóm và membership phụ thuộc hỗ trợ của ứng dụng. |
| Enterprise User extension | Có thể chứa \`employeeNumber\`, \`department\`, \`manager\`, \`costCenter\`... theo schema extension mà provider hỗ trợ. |

Ví dụ **yêu cầu tạo User theo SCIM**, sau khi quy trình xác minh và chính sách cho phép chuẩn bị tài khoản:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "externalId": "person-1042",
  "userName": "mai.nguyen@example.test",
  "displayName": "Nguyễn Thị Mai",
  "emails": [
    {
      "value": "mai.nguyen@example.test",
      "type": "work",
      "primary": true
    }
  ],
  "active": false,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "EMP-5812",
    "department": "FINANCE",
    "manager": {
      "value": "manager-scim-user-id"
    }
  }
}
~~~

Trong ví dụ, \`active=false\` thể hiện **tài khoản tại ứng dụng đang chờ kích hoạt theo chính sách**; nó không có nghĩa HRIS đã chấm dứt quan hệ lao động. \`manager.value\` phải được ánh xạ tới **ID SCIM của tài nguyên người quản lý tại ứng dụng đích**, không tự dùng \`managerSubjectId\` nội bộ nếu provider không công nhận nó. Có thể cần tạo/liên kết tài khoản của manager trước.

Trong triển khai thực tế:

- Kiểm tra \`/Schemas\` và khả năng được công bố qua \`/ServiceProviderConfig\` của provider khi có hỗ trợ; không giả định mọi extension/thuộc tính đều được nhận.
- Quản lý ánh xạ **\`subjectId\` ↔ \`externalId\` ↔ \`id\` của đích** để tránh tạo trùng.
- Không tự hiểu \`active=true\` là “đã cấp đủ quyền”: RBAC, group membership và quyền ứng dụng có thể được quản lý riêng.
- Với cập nhật nhiều trường, ghi nhận lỗi từng hệ thống và đọc lại thuộc tính/quyền quan trọng; một phản hồi thành công không tự chứng minh phiên/token đã bị thu hồi.
- Khi xóa hoặc thay đổi thuộc tính qua PATCH, tuân thủ ngữ nghĩa provider và áp dụng quy tắc trường thiếu/trường xóa rõ ràng.

## 8. Gán thuộc tính vào IdP, SSO và token

IdP lưu tài khoản và có thể phát hành **claim** cho ứng dụng qua **OIDC** hoặc thuộc tính khẳng định danh tính qua **SAML**. Không phải mọi thuộc tính trong profile chuẩn đều cần xuất hiện trong token hoặc assertion.

Ví dụ thiết kế ánh xạ:

| Thuộc tính IAM | IdP/directory | OIDC/SAML hoặc ứng dụng đích |
| --- | --- | --- |
| \`subjectId\` | ID liên kết nội bộ | Ánh xạ tới định danh ứng dụng ổn định; với OIDC dùng đúng cặp \`iss\` + \`sub\` do IdP phát hành. |
| \`displayName\` | Tên hiển thị | Claim \`name\` nếu client được phép và có nhu cầu. |
| \`workEmail\` | Email công việc | Claim \`email\` và \`email_verified\` khi IdP có cơ sở xác minh phù hợp. |
| \`departmentId\` | Thuộc tính tùy chỉnh hoặc directory attribute | Chỉ phát hành cho ứng dụng cần để phân quyền/hiển thị; tên claim phụ thuộc hợp đồng tích hợp. |
| \`jobCode\` | Thuộc tính hoặc mapping role | Có thể dùng nội bộ để tính nhóm/role; không nhất thiết đưa vào token. |
| \`lifecycleState\` | Dữ liệu chính sách truy cập | Ưu tiên thực thi trạng thái tại IdP/ứng dụng; tránh để client coi một claim cũ là trạng thái mới nhất. |

**SSO giải quyết đăng nhập liên thông, không thay thế quy trình chuẩn hóa thuộc tính**. Nếu IdP đã cập nhật \`departmentId\` nhưng ứng dụng còn dùng phiên hoặc claim phát hành trước đó, quyền có thể tạm thời phản ánh dữ liệu cũ.

Giảm rủi ro bằng thời hạn token phù hợp, kiểm tra hiệu lực tại phía máy chủ khi cần, chính sách buộc xác thực lại hoặc làm mất hiệu lực phiên đối với thay đổi nhạy cảm. Tuyệt đối không đưa giấy tờ xác minh, dữ liệu nhân sự nhạy cảm hoặc thông tin không phục vụ chức năng của ứng dụng vào mọi token.

## 9. Gán thuộc tính có ý nghĩa thế nào với RBAC và ABAC?

### 9.1. RBAC: thuộc tính dẫn tới vai trò

**Role-Based Access Control (RBAC)** gán quyền theo role được tổ chức định nghĩa. Ví dụ:

~~~text
workerType == EMPLOYEE
departmentId == FINANCE
jobCode == ACCOUNTANT_LEVEL_2
        |
        v
Mapping policy: finance-accountant-standard
        |
        v
Vai trò IAM: finance-basic
        |
        v
Quyền được phê duyệt: đọc báo cáo chi phí và thực hiện đối soát
~~~

\`departmentId=FINANCE\` không tự tạo quyền nếu policy chưa cho phép. Chính sách cũng có thể yêu cầu tách biệt nhiệm vụ (SoD), phê duyệt riêng hoặc ngày hiệu lực sau Start date.

### 9.2. ABAC: thuộc tính trực tiếp tham gia quyết định

**Attribute-Based Access Control (ABAC)** có thể đánh giá đồng thời thuộc tính của chủ thể, tài nguyên, hành động và ngữ cảnh:

~~~text
ALLOW if
    subject.workerType == "EMPLOYEE"
    AND subject.lifecycleState == "ACTIVE"
    AND subject.departmentId == resource.ownerDepartmentId
    AND action == "read"
    AND resource.classification <= subject.approvedClearance
~~~

Đây là giả mã minh họa, không phải cú pháp tiêu chuẩn của một sản phẩm IAM. \`approvedClearance\` phải được cấp từ nguồn và quy trình có thẩm quyền, **không tự suy ra từ jobCode hoặc email**.

ABAC đặc biệt nhạy với **độ tươi và độ tin cậy của thuộc tính**. Một nhân viên đã chuyển phòng ban nhưng IdP hoặc ứng dụng chưa cập nhật \`departmentId\` có thể vẫn được hệ thống cho phép truy cập tài nguyên cũ. Do đó, khi thuộc tính thay đổi cần tính lại role, đồng bộ, thu hồi quyền cũ và xác minh trạng thái đích; riêng quyền nhạy cảm cần kiểm soát thời gian truyền cập nhật.

### 9.3. Tránh cấp quyền từ dữ liệu tự khai không xác minh

Không nên cho người dùng tự sửa \`workerType\`, \`departmentId\`, \`isPrivileged\`, \`managerSubjectId\` hoặc nhóm đặc quyền rồi dùng các giá trị đó làm căn cứ cấp quyền. Tài khoản có thể cho phép người dùng chỉnh *preferredName* hoặc số liên lạc cá nhân, nhưng những trường điều khiển quyền phải có **chủ sở hữu và đường cập nhật riêng**.

## 10. Duy trì thuộc tính chuẩn xuyên suốt Joiner–Mover–Leaver

Enrollment là điểm khởi đầu, nhưng thuộc tính không bất biến: chúng thay đổi theo công việc và tình trạng quan hệ. Một profile được chuẩn hóa đúng lúc tạo mới vẫn có thể trở nên nguy hiểm nếu các bước cập nhật sau này không được quản lý.

| Giai đoạn | Thuộc tính chính | Hành động cần làm | Rủi ro nếu bỏ sót |
| --- | --- | --- | --- |
| **Joiner** | \`subjectId\`, \`engagementId\`, \`workerType\`, \`startDate\`, \`departmentId\`, \`jobCode\`. | Xác minh, chuẩn hóa, tạo tài khoản chờ, cấp quyền đúng ngày. | Gắn nhầm người, cấp quyền trước hạn hoặc sai bộ phận. |
| **Mover** | \`departmentId\`, \`jobCode\`, \`managerSubjectId\`, thời điểm hiệu lực. | Cập nhật profile, tính lại RBAC/ABAC, cấp mới và thu hồi quyền cũ. | Privilege creep, thiếu người phê duyệt phù hợp. |
| **Leaver** | \`endDate\`, trạng thái quan hệ, trạng thái tài khoản. | Đánh dấu quan hệ hết hiệu lực, khóa IdP và ứng dụng, thu hồi quyền/phiên/token khi hỗ trợ. | Tài khoản mồ côi, quyền còn tồn dư. |
| **Rehire** | Person ID, engagement ID mới, Start date mới, vai trò mới. | Xác minh đúng người, nối lịch sử hợp lệ, đánh giá quyền từ quan hệ mới. | Tự khôi phục quyền của hợp đồng cũ. |
| **Worker type conversion** | \`workerType\`, ID quan hệ cũ và mới, thời điểm chuyển đổi. | Thu hồi quyền theo quan hệ cũ, tính quyền theo quan hệ mới. | Hai hồ sơ/tài khoản độc lập cộng dồn quyền. |

### 10.1. Start date, End date và trạng thái là ba khái niệm riêng

\`startDate\` và \`endDate\` thường là **ngày nghiệp vụ** từ HRIS; \`lifecycleState\` là trạng thái IAM được tính theo nguồn và chính sách; \`active\` của SCIM là **trạng thái của tài khoản trong ứng dụng đích**. Không nên ánh xạ một-một mà bỏ qua quy tắc thời gian, xác minh hoặc ngoại lệ.

Ví dụ, nhà thầu có \`endDate\` vào cuối tháng nhưng chủ hợp đồng xác nhận chấm dứt ngay hôm nay. IAM cần xử lý sự kiện chấm dứt hợp lệ theo chính sách, thay vì chỉ nhìn End date cũ. Ngược lại, Employee nghỉ dài hạn có thể vẫn là nhân viên nhưng bị tạm khóa quyền trong thời gian đó.

### 10.2. Tài khoản dịch vụ và workload identity

Tài khoản dịch vụ là **chủ thể phi con người**, không nên ép vào schema Employee với các trường nhân sự giả. Thuộc tính chuẩn phù hợp có thể gồm:

| Thuộc tính workload | Ý nghĩa |
| --- | --- |
| \`workloadId\` | ID ổn định của workload, service principal hoặc ứng dụng. |
| \`workloadType\` | Loại tác vụ/dịch vụ, ví dụ batch job hoặc CI/CD. |
| \`ownerSubjectId\` / \`ownerTeamId\` | Chủ thể hoặc nhóm chịu trách nhiệm vận hành. |
| \`environment\` | Môi trường như development, staging, production. |
| \`serviceLifecycleState\` | Trạng thái vòng đời của dịch vụ, độc lập HRIS. |
| \`credentialRotationPolicy\` | Quy tắc vòng đời bí mật/chứng chỉ theo hệ thống quản lý credential. |

Khi Employee làm owner nghỉ việc hoặc chuyển bộ phận, cần cập nhật **owner** của service account, rà soát quyền và thông tin xác thực. Không tự thu hồi toàn bộ tài khoản máy nếu điều đó gây gián đoạn dịch vụ mà chưa có quy trình thay thế; cũng không để account không có owner tiếp tục hoạt động vô thời hạn.

## 11. Xử lý trùng, xung đột và sự kiện đến sai thứ tự

Giả sử HRIS lần lượt phát:

1. Phiên bản 11: \`departmentId=FINANCE\`, hiệu lực ngày 01/12.
2. Phiên bản 12: \`departmentId=OPERATIONS\`, hiệu lực ngày 05/12.
3. Do lỗi hàng đợi, **phiên bản 11 đến sau phiên bản 12**.

Nếu IAM luôn ghi đè theo **thời điểm nhận**, hệ thống sẽ đưa nhân viên trở lại phòng Tài chính và có thể khôi phục quyền không còn hợp lệ.

Quy trình an toàn nên có các tính chất:

- **Idempotency:** cùng một sự kiện được xử lý lặp không tạo thêm chủ thể hoặc tài khoản.
- **Version ordering:** so sánh phiên bản/sự kiện có thẩm quyền để tránh ghi đè bằng dữ liệu cũ.
- **Effective dating:** biết dữ liệu có hiệu lực khi nào, kể cả thay đổi đã lên lịch trong tương lai.
- **Conflict handling:** khi hai nguồn có giá trị trái ngược, ưu tiên nguồn sở hữu thuộc tính hoặc chuyển kiểm tra thủ công.
- **Reconciliation:** định kỳ so sánh profile IAM và trạng thái ứng dụng với nguồn có thẩm quyền, có người chịu trách nhiệm xử lý chênh lệch.
- **Safe failure:** với thuộc tính thiết yếu cho phân quyền mà chưa đáng tin, tạm giữ việc cấp quyền phụ thuộc thay vì tự suy đoán.

Ví dụ giả mã xử lý một thay đổi thuộc tính:

~~~text
onAuthoritativeAttributeEvent(event):
    verifySourceAndEventSchema(event)
    if alreadyProcessed(event.eventId):
        return

    subject = resolveByStableSourceKey(event.sourceSystem, event.personKey)
    if subject is ambiguous:
        createManualReviewCase(event)
        return

    if event.recordVersion < subject.latestTrustedSourceVersion:
        recordIgnoredStaleEvent(event)
        return

    normalized = mapAndValidate(event.attributes, approvedMappingVersion)
    if normalized.hasCriticalErrors:
        quarantineEventAndAlertOwner(event, normalized.errors)
        return

    applyAttributesWithProvenance(subject, normalized, event)
    expectedAccountsAndRights = evaluateLifecycleAndAccessPolicies(subject)
    provisionOrRevokeApprovedChanges(expectedAccountsAndRights)
    verifyTargetSystemState(subject)
    writeAuditResult(event, subject)
~~~

Giả mã này mô tả **logic mong muốn**, không phải triển khai hoàn chỉnh. Trong hệ thống thực tế cần xử lý bất đồng bộ, sự kiện cập nhật một phần, phiên bản từng thuộc tính, thao tác có hiệu lực trong tương lai và lỗi khi nhiều hệ thống đích chỉ hoàn tất một phần.

## 12. Truy vết, bảo mật và quản trị dữ liệu thuộc tính

Để kiểm toán một quyết định IAM, tổ chức cần trả lời **“Giá trị thuộc tính nào được dùng, đến từ đâu, ai thay đổi, có hiệu lực khi nào và đã dẫn đến quyền nào?”**

### 12.1. Các bằng chứng nên lưu

| Bằng chứng | Ví dụ | Giá trị điều tra |
| --- | --- | --- |
| Nguồn và ID bản ghi | \`hris-primary:EMP-5812\` | Truy về hồ sơ/quan hệ có thẩm quyền. |
| ID sự kiện và phiên bản | \`hr-evt-9201\`, \`recordVersion=8\` | Biết thay đổi nào mới/cũ và tránh xử lý lặp. |
| Giá trị trước/sau | \`FINANCE -> OPERATIONS\` | Hiểu vì sao quyền phải thay đổi. |
| Phiên bản mapping | \`hr-to-iam-v3\` | Giải thích cách chuyển mã nguồn sang mã chuẩn tại thời điểm đó. |
| Thời điểm nguồn và hiệu lực | \`occurredAt\`, \`effectiveAt\` | Đánh giá quyền thay đổi đúng thời gian. |
| Quyết định chính sách | Policy ID, version, kết quả, phê duyệt | Biết vì sao role/entitlement được cấp hoặc thu hồi. |
| Kết quả hệ thống đích | Yêu cầu SCIM/API, phản hồi và trạng thái đọc lại | Chứng minh tài khoản/quyền thực sự đã đổi. |
| Ngoại lệ và người xử lý | Case ID, owner, hạn xử lý | Theo dõi sai lệch đến khi khép kín. |

Nên liên kết sự kiện theo **\`traceId\`/correlation ID** khi khả thi, từ HRIS đến IAM, IdP và ứng dụng. Nếu ứng dụng không hỗ trợ ID liên kết, có thể quản lý ánh xạ request ID, target account ID, thời điểm và mã phản hồi.

### 12.2. Tối thiểu hóa dữ liệu và bảo vệ quyền riêng tư

Không phải thuộc tính HRIS nào cũng nên đưa vào IdP, token SSO hay SCIM. Chỉ phát tán trường cần cho mục đích cụ thể theo quy tắc bảo vệ dữ liệu của tổ chức:

- Thông tin nhạy cảm về nhân sự, giấy tờ xác minh, thông tin sức khỏe hoặc tài chính cá nhân không nên được sao chép vào mọi ứng dụng.
- Mật khẩu, token, OTP, khóa bí mật và cookie phiên **không phải thuộc tính hồ sơ nên ghi vào audit log**.
- Dữ liệu cần được phân quyền đọc/sửa theo vai trò, có lưu vết truy cập nhạy cảm, thời hạn lưu và quy trình xử lý yêu cầu hợp lệ.
- Giá trị dùng trong RBAC/ABAC phải được bảo vệ khỏi người dùng tự sửa để nâng quyền.
- Khi xuất dữ liệu ra báo cáo, có thể dùng định danh giả/pseudonym nếu vẫn bảo đảm đối chiếu có kiểm soát khi điều tra.

Kho nhật ký chống sửa/xóa giúp bảo vệ **tính toàn vẹn lịch sử**, nhưng không tự bảo đảm giá trị nguồn đã đúng. Cần kết hợp xác minh nguồn, kiểm tra logic và đối soát dữ liệu hiện hành.

## 13. Bài tập tình huống: chuyển từ Contractor sang Employee

**Bối cảnh:** An làm nhà thầu từ tháng 9 đến hết 30/11. Từ 01/12, An trở thành Employee tại bộ phận Tài chính. Hai nguồn gửi dữ liệu khác nhau:

| Trường | Hệ thống nhà thầu | HRIS |
| --- | --- | --- |
| Person/record ID | \`CTR-P-411\` | \`P-842\` |
| Worker type | \`CONTRACTOR\` | \`EMPLOYEE\` |
| Department | \`costCenter=D020\` | \`deptCode=FIN\` |
| End/Start date | \`endDate=2026-11-30\` | \`startDate=2026-12-01\` |
| Email | \`an@example.test\` | \`an@example.test\` |
| Quyền hiện tại | Đọc dữ liệu dự án ngoài tổ chức | Cần quyền xử lý báo cáo Tài chính |

**Không nên làm:** gộp hai hồ sơ chỉ vì cùng email; tự coi \`D020\` bằng \`FIN\`; giữ nguyên quyền Contractor khi kích hoạt Employee; hoặc xóa lịch sử Contractor làm mất dấu cấp quyền cũ.

**Quy trình đúng:**

1. Xác minh hai hồ sơ có đại diện **cùng một người thật** hay không qua quy trình tin cậy; sau đó liên kết nguồn với một \`subjectId\` phù hợp.
2. Giữ **hai engagement** riêng và ngày hiệu lực riêng. Ghi rõ nguồn có thẩm quyền cho từng quan hệ.
3. Dùng mapping đã được phê duyệt để chuyển \`deptCode=FIN\` thành \`departmentId=FINANCE\`; không tự suy đoán ý nghĩa \`D020\`.
4. Tính lại quyền Employee theo vai trò mới và phê duyệt; đồng thời lên lịch thu hồi quyền Contractor không còn hợp lệ.
5. Đồng bộ tài khoản và quyền tới IdP/ứng dụng bằng SCIM/API; nếu tái sử dụng tài khoản, phải đối chiếu chủ thể và đánh giá thông tin xác thực, phiên, quyền cũ.
6. Đọc lại quyền thực tế và lưu dấu vết nguồn, mapping, quyết định, lệnh và kết quả tại từng hệ thống đích.

**Điểm kiểm tra:** Ngày 02/12, An vẫn thấy được thư mục chỉ dành cho nhà thầu. Cần tra quyền đó có đến từ nhóm Contractor cũ, quyền được cấp trực tiếp hay phiên/token chưa hết hiệu lực. Việc \`workerType\` đã đổi thành \`EMPLOYEE\` trong IdP **không tự chứng minh quyền cũ được thu hồi**.

## 14. Đo chất lượng gán thuộc tính chuẩn

| Chỉ số | Cách đo gợi ý | Vấn đề phát hiện |
| --- | --- | --- |
| **Tỷ lệ enrollment có thuộc tính thiết yếu hợp lệ** | Số hồ sơ đạt đầy đủ kiểm tra ID, loại quan hệ, trạng thái và các mã bắt buộc / tổng hồ sơ. | Thiếu/không hợp lệ trước khi cấp tài khoản. |
| **Tỷ lệ ánh xạ thành công** | Giá trị mã nguồn ánh xạ được bằng bảng mã đã phê duyệt / tổng giá trị cần ánh xạ. | Mã lạ, mapping lỗi thời. |
| **Số hồ sơ danh tính trùng hoặc không rõ chủ thể** | Số ca chưa thể resolve chắc chắn tới một \`subjectId\`. | Nguy cơ gắn nhầm tài khoản. |
| **Độ trễ cập nhật thuộc tính quan trọng** | Thời gian từ mốc có hiệu lực tại nguồn đến khi được xác minh tại hệ thống đích. | Quyền dựa trên thuộc tính cũ. |
| **Tỷ lệ Mover đã đồng bộ và thu hồi quyền cũ** | Mover có trạng thái đích phù hợp chính sách mới / tổng Mover cần xử lý. | Tích lũy quyền truy cập. |
| **Tỷ lệ tài khoản không khớp profile IAM** | Tài khoản có giá trị/chính sách lệch so với profile chuẩn / tổng tài khoản đã đối soát. | Lỗi SCIM/API, cập nhật ngoài quy trình. |
| **Số ngoại lệ mapping tồn đọng quá hạn** | Các ca thiếu mã nguồn, conflict, mismatch chưa được owner giải quyết đúng hạn. | Lỗ hổng quản trị dữ liệu. |
| **Tỷ lệ thay đổi có chuỗi kiểm toán hoàn chỉnh** | Thay đổi thuộc tính có bằng chứng nguồn → mapping → quyết định → đích / tổng thay đổi cần kiểm toán. | Khó điều tra quyền sai. |

Cần xác định mẫu số, phạm vi hệ thống và ngưỡng theo mức rủi ro của tổ chức. Việc connector phản hồi thành công chỉ là **một bằng chứng kỹ thuật**, chưa luôn thay thế được đối soát quyền thực tế.

## 15. Checklist áp dụng vào một hệ thống IAM

1. Có phân biệt rõ **Person/Subject**, **Engagement**, **Account** và **Entitlement** không?
2. Thuộc tính thiết yếu đã có **tên, định nghĩa, kiểu dữ liệu, tập mã, nguồn có thẩm quyền và chủ sở hữu** chưa?
3. Có ID ổn định, không tái sử dụng để liên kết danh tính; có xử lý trùng tên, đổi email và tái tuyển dụng không?
4. Mỗi mapping từ nguồn sang profile chuẩn và từ profile sang hệ thống đích có **phiên bản, quy tắc kiểm tra và xử lý giá trị không rõ** không?
5. Có giữ đúng Unicode, ý nghĩa ngày/giờ/múi giờ, dữ liệu nhiều giá trị và quy tắc phân biệt trường thiếu/trường xóa không?
6. Có xác minh \`workerType\`, \`departmentId\`, \`managerSubjectId\`, \`lifecycleState\` trước khi dùng cho RBAC/ABAC không?
7. Các thuộc tính SCIM (\`id\`, \`externalId\`, \`userName\`, \`active\`) có được hiểu đúng theo phạm vi provider và không bị nhầm với trường nội bộ không?
8. Claim OIDC/SAML có được **giới hạn theo nhu cầu ứng dụng**, tránh lộ thông tin nhân sự hoặc mang trạng thái cũ quá lâu không?
9. Joiner–Mover–Leaver có cập nhật thuộc tính, cấp/thu hồi quyền và **xác minh trạng thái tại hệ thống đích** không?
10. Tài khoản dịch vụ có schema và owner riêng, không bị gán nhầm thuộc tính Employee không?
11. Hệ thống có chống sự kiện lặp/đến muộn, xử lý xung đột và theo dõi ngoại lệ dữ liệu không?
12. Có thể truy vết từ giá trị nguồn, phiên bản mapping tới quyết định phân quyền và quyền hiện hữu ở ứng dụng không?

**Ghi nhớ:** Gán thuộc tính chuẩn trong Identity enrollment là biến dữ liệu nguồn thành **hồ sơ danh tính có định nghĩa, nguồn gốc, kiểm chứng và thời điểm hiệu lực rõ ràng**, rồi dùng hồ sơ ấy để đồng bộ IdP/ứng dụng và áp dụng chính sách IAM. **Đúng thuộc tính, đúng chủ thể, đúng nguồn và đúng thời điểm** giúp Joiner được cấp quyền phù hợp, Mover không tích lũy quyền cũ, Leaver được thu hồi đầy đủ và toàn bộ quá trình có thể truy vết khi kiểm toán.
