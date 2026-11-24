# Employee trong IAM: quản lý danh tính và quyền truy cập của nhân viên

Trong quản lý danh tính và truy cập (*Identity and Access Management* — **IAM**), **Employee** là chủ thể con người có quan hệ lao động được tổ chức công nhận. Employee thường là nhóm danh tính phổ biến nhất của hệ thống IAM doanh nghiệp, nhưng cũng là nhóm thay đổi liên tục: nhân viên gia nhập, thử việc, chuyển phòng ban, được bổ nhiệm, nghỉ phép dài hạn, nghỉ việc hoặc được tuyển dụng trở lại. Mỗi thay đổi có thể tác động đến hàng chục tài khoản và quyền truy cập.

Bài học thuộc chương **Chủ thể và vai trò** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mục tiêu là hiểu **Employee như một loại chủ thể IAM** và cách quản lý vòng đời theo **Joiner–Mover–Leaver (JML)**: xác minh nhân viên, tạo danh tính và tài khoản, cấp quyền, rà soát, thay đổi và thu hồi quyền. Nội dung kết nối hệ thống nhân sự (**HRIS**), nhà cung cấp danh tính (**IdP**), đăng nhập một lần (**SSO**), cấp phát tài khoản qua **SCIM**, phân quyền **RBAC/ABAC**, quản lý tài khoản dịch vụ và kiểm toán để giảm truy cập tồn dư.

Sau bài học, người học có thể:

- Phân biệt **Employee** với các loại chủ thể khác, đồng thời phân biệt **loại chủ thể**, **vai trò công việc** và **vai trò cấp quyền**.
- Mô tả quan hệ giữa hồ sơ nhân viên trong HRIS, danh tính số trong IAM, tài khoản IdP và tài khoản ứng dụng.
- Thiết kế những bước kiểm soát chủ yếu cho nhân viên ở từng giai đoạn Joiner, Mover và Leaver.
- Xử lý các trường hợp dễ nhầm như chuyển phòng ban, nghỉ dài hạn, tái tuyển dụng, thay đổi loại hợp đồng và tài khoản đặc quyền.
- Đánh giá quyền truy cập còn dư, chất lượng dữ liệu danh tính và bằng chứng kiểm toán.

## 1. Employee là ai trong mô hình IAM?

**Employee** mô tả **mối quan hệ của một người với tổ chức**: người đó được tổ chức ghi nhận là nhân viên trong một khoảng thời gian nhất định. Trong thực tế, nguồn xác nhận quan hệ thường là HRIS hoặc quy trình nhân sự được ủy quyền. Mỗi tổ chức có thể định nghĩa chi tiết về nhân viên chính thức, nhân viên thời vụ và người thử việc khác nhau; hệ thống IAM cần sử dụng chính sách phân loại đã được thống nhất.

Điểm quan trọng là **Employee không phải một quyền truy cập mặc định**. Việc một người là nhân viên chưa tự động cho phép họ đọc mọi tài liệu nội bộ hoặc quản trị hệ thống.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Person** | Một cá nhân ngoài đời thực. | Nguyễn An. |
| **Employee** | Quan hệ lao động hiện tại giữa một Person và tổ chức. | An được HRIS ghi nhận làm nhân viên bộ phận Kế toán. |
| **Digital identity** | Bản ghi định danh số đại diện cho Person hoặc quan hệ với tổ chức. | \`subjectId=person-2041\`, \`workerType=employee\`. |
| **Account** | Tài khoản cụ thể trong IdP hoặc ứng dụng. | \`idpAccountId=acc-771\`, \`erpAccountId=u-315\`. |
| **Job role** | Vị trí/chức năng công việc. | Kế toán viên, Trưởng nhóm Kế toán. |
| **IAM role** | Tập quyền được định nghĩa để cấp phát truy cập. | \`role=finance-basic\`, \`role=invoice-approver\`. |
| **Entitlement** | Quyền cụ thể trên nhóm, chức năng hoặc tài nguyên. | Đọc báo cáo chi phí, phê duyệt hóa đơn dưới ngưỡng. |

Một Employee có thể có nhiều tài khoản (tài khoản thông thường, tài khoản quản trị tách biệt, tài khoản ứng dụng riêng), nhiều vai trò nghiệp vụ hoặc nhiều quyền. Nhưng tất cả phải được **liên kết có kiểm chứng với đúng chủ thể** và có lý do còn hiệu lực.

### Employee khác Contractor, Partner và Service Account

| Loại chủ thể | Căn cứ quan hệ | Ví dụ kiểm soát vòng đời |
| --- | --- | --- |
| **Employee** | Quan hệ lao động được HRIS hoặc nguồn nhân sự có thẩm quyền xác nhận. | Sự kiện tuyển dụng, thay đổi công việc, nghỉ việc từ HRIS. |
| **Contractor** | Hợp đồng hoặc đơn đặt dịch vụ; có đơn vị/người bảo trợ chịu trách nhiệm. | Ngày kết thúc hợp đồng, tái xác nhận sponsor, thu hồi khi hết hạn. |
| **Partner/Guest** | Quan hệ hợp tác hoặc lời mời truy cập có chủ đích. | Giới hạn thời gian, phạm vi dữ liệu, người bảo trợ và chu kỳ xác nhận. |
| **Service Account/Workload** | Danh tính phi con người của ứng dụng, tác vụ hoặc máy. | Owner dịch vụ, vòng đời ứng dụng, khóa/token và chính sách quyền máy. |

Các loại chủ thể có thể dùng chung IdP hoặc ứng dụng nhưng cần quy trình xác minh, phê duyệt và hết hạn khác nhau. Một nhân viên cũng có thể là **owner của service account**; điều đó **không biến service account thành Employee**.

## 2. Hồ sơ nhân viên là điểm xuất phát của danh tính

### 2.1. Nguồn có thẩm quyền

Đối với Employee, **HRIS thường là nguồn có thẩm quyền (authoritative source)** để xác nhận người đó có quan hệ lao động, ngày bắt đầu, ngày kết thúc, bộ phận, vị trí và quản lý trực tiếp. Tuy nhiên, không phải mọi trường thông tin đều nhất thiết thuộc quyền sở hữu của HRIS: sơ đồ tổ chức có thể do một hệ thống khác quản lý, còn nhu cầu quyền đặc thù có thể do người quản lý ứng dụng phê duyệt.

Một bộ thuộc tính thường dùng trong IAM:

| Thuộc tính | Công dụng trong vòng đời | Lưu ý |
| --- | --- | --- |
| \`personId\` hoặc \`subjectId\` | Liên kết danh tính xuyên hệ thống. | Duy nhất, ổn định, không tái sử dụng cho người khác. |
| \`employeeRecordId\` | Truy ngược hồ sơ lao động tại nguồn. | Có thể thay đổi theo đợt tuyển dụng; cần lưu lịch sử liên kết. |
| \`workerType\` | Phân biệt Employee với loại quan hệ khác. | Không suy đoán chỉ từ tên miền email. |
| \`employmentStatus\` | Thể hiện tiền tuyển dụng, đang làm việc, tạm ngưng, đã kết thúc. | Cần quy tắc hiệu lực riêng cho từng trạng thái. |
| \`startDate\`, \`endDate\` | Điều khiển thời điểm cho phép và chấm dứt truy cập. | Thống nhất múi giờ, mốc hiệu lực và trường hợp ngoài giờ. |
| \`departmentId\`, \`jobCode\`, \`managerId\` | Tính vai trò, người duyệt và đối tượng rà soát. | Tránh dựa hoàn toàn vào tên bộ phận dạng văn bản tự do. |
| \`location\`, \`costCenter\` | Điều kiện bổ sung cho một số chính sách. | Chỉ dùng nếu có ý nghĩa nghiệp vụ, đã xác minh và được phép xử lý. |

Chỉ nên đồng bộ những thuộc tính cần cho việc quản lý danh tính, phân quyền và kiểm toán; không nên phát tán hồ sơ nhân sự nhạy cảm sang mọi ứng dụng chỉ vì chúng có tài khoản Employee.

### 2.2. Định danh ổn định và liên kết tài khoản

Các trường **họ tên, email và tên đăng nhập** có thể trùng, thay đổi hoặc được cấp lại. Chúng không nên là khóa duy nhất để khẳng định hai tài khoản thuộc cùng một người. Hệ thống cần một **ID chủ thể ổn định** và lưu ánh xạ tới ID do từng ứng dụng cấp.

Ví dụ bản ghi định danh *minh họa*:

~~~json
{
  "subjectId": "person-2041",
  "subjectType": "employee",
  "source": {
    "system": "HRIS",
    "employeeRecordId": "EMP-9031"
  },
  "employmentStatus": "ACTIVE",
  "departmentId": "FIN",
  "jobCode": "ACCOUNTANT",
  "managerId": "person-1012",
  "accounts": [
    {
      "system": "corporate-idp",
      "accountId": "acc-771"
    },
    {
      "system": "finance-erp",
      "accountId": "u-315"
    }
  ]
}
~~~

Các ID trên là dữ liệu giả định. Nếu ứng dụng dùng OpenID Connect (**OIDC**), nhận diện chủ thể từ IdP thường dựa trên cặp **\`issuer\` + \`sub\`**. Không nên giả định \`sub\` giống nhau giữa các IdP hoặc dùng email thay thế định danh kỹ thuật bền vững. Một nhân viên có thể được tái tuyển dụng với mã hồ sơ lao động mới; chính sách phải quyết định cách nối lịch sử mà vẫn tránh gán nhầm tài khoản cũ.

### 2.3. Xác minh Employee trước khi cấp quyền

Việc xác minh (*identity proofing*) cần gắn với mức độ rủi ro và quy trình tuyển dụng của tổ chức:

1. Kiểm tra sự tồn tại và hiệu lực của hồ sơ từ nguồn nhân sự đáng tin cậy.
2. Đối chiếu người gia nhập với hồ sơ trước đó và người trùng họ tên; trường hợp mơ hồ chuyển sang kiểm tra thủ công.
3. Xác nhận ngày bắt đầu, đơn vị, quản lý và các điều kiện bắt buộc trước khi kích hoạt.
4. Liên kết đúng danh tính gốc với tài khoản IdP; trao thông tin kích hoạt qua kênh đã xác minh.
5. Đăng ký **MFA**, passkey hoặc phương thức xác thực được phê duyệt; bảo vệ cả quy trình khôi phục tài khoản trước nguy cơ mạo danh.
6. Ghi lại kết quả xác minh, nguồn và người/hệ thống phê duyệt ở mức cần thiết cho kiểm toán.

**Xác thực mạnh không sửa được gắn nhầm danh tính.** Nếu cấp tài khoản của An cho một người khác, việc người ấy đăng nhập bằng MFA vẫn không làm quyền trở thành đúng người.

## 3. Employee trong kiến trúc IAM doanh nghiệp

~~~mermaid
flowchart LR
    HR["HRIS<br/>Hồ sơ Employee + sự kiện JML"] --> IGA["IGA / Lifecycle workflow<br/>Quy tắc + phê duyệt + kiểm soát"]
    IGA --> IDP["IdP / Directory<br/>Tài khoản + nhóm + MFA"]
    IDP -->|"SSO (OIDC/SAML)"| APP["Ứng dụng nghiệp vụ"]
    IGA -->|"SCIM / API<br/>cấp, sửa, khóa"| APP
    IGA --> AUDIT["Audit / đối soát"]
    IDP --> AUDIT
    APP --> AUDIT
    AUDIT -->|"Chênh lệch, cảnh báo"| IGA
~~~

Các thành phần có trách nhiệm khác nhau:

- **HRIS** thông báo sự kiện nhân sự và các thuộc tính có thẩm quyền. HRIS không nhất thiết trực tiếp quản lý quyền trên từng ứng dụng.
- **IGA** (*Identity Governance and Administration*) hoặc hệ thống điều phối vòng đời xác định tài khoản và quyền phải có, thu thập phê duyệt và theo dõi thực thi.
- **IdP/Directory** tạo và xác thực tài khoản Employee, quản lý MFA, nhóm và chính sách đăng nhập.
- **SSO** cho phép nhân viên dùng danh tính tập trung để đăng nhập vào ứng dụng tích hợp. SSO không tự quyết định quyền nghiệp vụ hoặc tự vô hiệu hóa mọi tài khoản cục bộ.
- **SCIM** chuẩn hóa hoạt động cấp phát và cập nhật người dùng/nhóm ở ứng dụng có hỗ trợ. Các ứng dụng còn lại có thể cần API riêng hoặc quy trình thủ công được kiểm soát.
- **Audit/đối soát** kết nối sự kiện HRIS, quyết định phân quyền, lệnh thực thi và trạng thái thực tế tại ứng dụng.

Mục tiêu là duy trì sự nhất quán giữa **nhân viên được tổ chức công nhận**, **danh tính có thể xác thực** và **các quyền hiện còn cần thiết**.

## 4. Joiner: Employee mới gia nhập

**Joiner** bắt đầu từ sự kiện tuyển dụng hoặc quyết định cho người lao động tham gia tổ chức. Không phải mọi Employee mới đều được phép truy cập ngay lúc hệ thống biết tin tuyển dụng: ngày có hiệu lực, hoàn tất xác minh và phê duyệt chính sách mới là căn cứ kích hoạt.

### Luồng Joiner tham khảo

1. **Nhận hồ sơ từ HRIS:** có ID bản ghi, loại nhân sự, ngày bắt đầu, bộ phận, vị trí, quản lý; kiểm tra nguồn phát sự kiện.
2. **Xác minh và chống trùng:** xác nhận quan hệ lao động hợp lệ, tìm danh tính trước đó, phân biệt người trùng tên, xử lý tái tuyển dụng.
3. **Tạo danh tính IAM:** sinh hoặc liên kết \`subjectId\`, xác định trạng thái \`PENDING\` trong thời gian chờ bắt đầu.
4. **Tính quyền khởi tạo:** cấp những quyền cơ bản theo quy tắc đã phê duyệt; các quyền nhạy cảm phải có điều kiện/phê duyệt riêng.
5. **Cấp tài khoản:** tạo tài khoản tại IdP và ứng dụng qua SCIM/API; ghi nhận ID tài khoản đích và kết quả.
6. **Kích hoạt đúng thời điểm:** chỉ bật đăng nhập khi đáp ứng điều kiện; bàn giao thông tin kích hoạt qua kênh xác thực và thiết lập MFA.
7. **Đối soát:** kiểm tra mỗi ứng dụng đã có đúng tài khoản, đúng quyền, không có liên kết sai hoặc lỗi cấp phát chưa xử lý.

Ví dụ, Employee mới làm ở bộ phận Chăm sóc khách hàng có thể được cấp email, lịch làm việc, tài liệu chung và quyền vào hệ thống hỗ trợ. Quyền xuất dữ liệu khách hàng hàng loạt hoặc sửa chính sách bảo mật thường cần phê duyệt bổ sung, ngay cả khi người đó đã là Employee hợp lệ.

### Rủi ro Joiner cần phòng ngừa

| Tình huống | Sai sót thường gặp | Kiểm soát |
| --- | --- | --- |
| Hai nhân viên trùng họ tên | Tài khoản bị gắn vào sai hồ sơ. | Đối sánh bằng ID ổn định và nguồn đáng tin cậy; giữ hồ sơ mơ hồ để xử lý thủ công. |
| Nhân viên chưa tới ngày bắt đầu | Tài khoản truy cập trước thời hạn. | Tách tạo trước và kích hoạt; kiểm soát \`effectiveAt\`. |
| Cấp quyền dựa vào vị trí không chính xác | Employee mới có quyền của bộ phận khác. | Kiểm tra thuộc tính nguồn, phiên bản chính sách và kết quả đối soát. |
| Nhân viên chưa đăng ký phương thức xác thực | Dễ bị chiếm tài khoản qua quy trình kích hoạt/khôi phục. | Bàn giao qua kênh kiểm chứng, yêu cầu MFA, kiểm soát khôi phục. |

## 5. Mover: Employee thay đổi vị trí hoặc quan hệ công việc

**Mover** bao gồm nhiều biến động hơn “chuyển phòng ban”: đổi chức danh, thăng chức, chuyển địa điểm, đổi người quản lý, luân chuyển dự án, biệt phái, thay đổi trách nhiệm hoặc loại quan hệ công việc. Những thay đổi này có thể **cấp thêm**, **giảm bớt** hoặc **giữ nguyên** quyền.

Nguyên tắc chính: **danh tính người lao động thường giữ ổn định, còn thuộc tính và quyền phải phản ánh công việc hiện tại**.

### Ví dụ chuyển bộ phận

Nhân viên Bình chuyển từ **Kinh doanh** sang **Tài chính**. Trước đó, Bình có quyền xem danh sách khách hàng và cập nhật báo giá. Vai trò mới cần xem sổ kế toán tổng hợp nhưng không còn cần sửa báo giá.

| Hạng mục | Trước chuyển | Sau chuyển hợp lệ |
| --- | --- | --- |
| Danh tính gốc \`subjectId\` | \`person-317\` | **Giữ nguyên** nếu vẫn cùng người và cùng chính sách định danh. |
| Thuộc tính bộ phận | \`SALES\` | \`FINANCE\` theo ngày hiệu lực. |
| Vai trò IAM | \`sales-basic\` | Thay bằng \`finance-basic\` sau rà soát. |
| Quyền sửa báo giá | Có. | **Thu hồi**, trừ khi có ngoại lệ được phê duyệt và giới hạn thời gian. |
| Quyền xem báo cáo tài chính | Không. | Cấp theo vai trò và điều kiện hợp lệ. |
| Nhật ký thay đổi | Sự kiện trước khi chuyển. | Lưu phê duyệt, quyền trước/sau, kết quả tại từng ứng dụng. |

Luồng xử lý Mover nên:

1. Nhận thay đổi được xác thực từ nguồn có thẩm quyền, kèm thời điểm hiệu lực.
2. Cập nhật thuộc tính Employee tại hệ thống quản trị danh tính/IdP.
3. Tính **tập quyền mong đợi** theo vị trí mới bằng RBAC/ABAC và các ngoại lệ đã phê duyệt.
4. So sánh tập quyền thực tế với quyền mong đợi: **thu hồi quyền cũ không cần thiết**, cấp quyền mới hợp lệ.
5. Rà soát cả nhóm lồng nhau, quyền ứng dụng cục bộ, tài khoản quản trị phụ, quyền được chia sẻ và quyền trực tiếp không đi qua IdP.
6. Xác nhận trạng thái thực tế tại từng ứng dụng; chuyển lỗi sang quy trình xử lý và cảnh báo.

Nếu chỉ cộng quyền mới mà không thu hồi quyền cũ, Employee sẽ tích lũy **quyền truy cập tồn dư** (*privilege creep*). Điều này có thể khiến người đã chuyển việc vẫn truy cập dữ liệu bộ phận trước.

### Tạm nghỉ, tạm ngưng và thay đổi trạng thái

Nghỉ thai sản, nghỉ phép dài hạn, tạm đình chỉ hoặc nghỉ không lương **không đồng nghĩa tự động với Leaver**. Quan hệ lao động có thể vẫn tồn tại nhưng quyền đăng nhập cần thay đổi theo chính sách và quyết định của tổ chức.

- **Leave of absence**: có thể giữ nguyên danh tính và hồ sơ; quyền truy cập được giữ, hạn chế hoặc tạm khóa theo yêu cầu bảo mật và nghiệp vụ.
- **Suspension**: thường cần khóa hoặc hạn chế ngay các đường truy cập được chỉ định, kèm bằng chứng người/phương thức ra quyết định.
- **Return to work**: chỉ khôi phục quyền khi trạng thái được nguồn có thẩm quyền xác nhận; đánh giá quyền và MFA thay vì tự phục hồi mọi quyền cũ.

Tách **trạng thái lao động** khỏi **trạng thái tài khoản** giúp tránh nhầm trường hợp nhân viên tạm nghỉ với trường hợp hợp đồng đã chấm dứt.

## 6. Leaver: Employee nghỉ việc và kết thúc quyền truy cập

**Leaver** là thời điểm cần kiểm soát chặt, vì Employee trước khi nghỉ có thể sở hữu nhiều tài khoản, nhóm, quyền đặc biệt và phiên đăng nhập còn hiệu lực. Việc thu hồi phải dựa trên **thời điểm chấm dứt có hiệu lực** và mức rủi ro, kể cả trường hợp chấm dứt đột xuất.

### Luồng Leaver tham khảo

1. **Xác nhận sự kiện nguồn:** HRIS hoặc quy trình được ủy quyền cung cấp Employee ID, ngày giờ kết thúc quan hệ và trường hợp cần khóa khẩn.
2. **Ngăn đăng nhập mới:** vô hiệu hóa hoặc khóa tài khoản tại IdP/Directory đúng thời điểm; thay đổi chính sách truy cập nếu cần.
3. **Xử lý phiên và thông tin xác thực:** thu hồi phiên, refresh token, API key, chứng chỉ, phương thức xác thực và quyền ủy quyền khi hệ thống hỗ trợ; đánh giá token đã cấp còn thời hạn.
4. **Đồng bộ hệ thống đích:** sử dụng SCIM/API để vô hiệu hóa tài khoản ứng dụng, xử lý tài khoản cục bộ, công cụ không tích hợp SSO và tài khoản quản trị phụ.
5. **Thu hồi quyền:** bỏ nhóm, vai trò, quyền ngoại lệ, quyền trên kho dữ liệu, chia sẻ và tích hợp liên quan.
6. **Chuyển giao sở hữu:** bàn giao nhiệm vụ, dữ liệu, nhóm phê duyệt và service account do Employee quản lý cho người/đơn vị mới theo chính sách.
7. **Đối soát và kiểm toán:** xác nhận kết quả ở từng ứng dụng; cảnh báo những tài khoản còn hoạt động hoặc lệnh thu hồi thất bại; lưu bằng chứng theo chính sách.

**Điểm cần phân biệt:** khóa Employee tại IdP giúp chặn nhiều luồng SSO, nhưng không mặc nhiên làm mọi phiên ứng dụng, tài khoản cục bộ và API token mất hiệu lực. Quy trình Leaver chưa hoàn tất về mặt kỹ thuật cho đến khi các hệ thống thuộc phạm vi đã được kiểm tra hoặc có ngoại lệ đang được quản lý.

### Những trường hợp đặc biệt

- **Nghỉ việc đột xuất hoặc rủi ro cao:** cần ưu tiên khóa ngay theo quy trình đã phê duyệt và giám sát các thao tác còn đang diễn ra.
- **Nhân viên có tài khoản đặc quyền:** thu hồi cả tài khoản quản trị riêng, quyền truy cập hạ tầng, khóa SSH, VPN, credential và quyền trong hệ thống bảo mật.
- **Nhân viên từng là owner của ứng dụng/dịch vụ:** chuyển ownership và bảo đảm các service account vẫn có chủ sở hữu hợp lệ; xoay bí mật nếu chính sách hoặc tình huống đòi hỏi.
- **Tài khoản dùng chung:** cần xem xét cách nhân viên đã sử dụng tài khoản, thu hồi phương thức truy cập hoặc thay thông tin xác thực phù hợp.
- **Dữ liệu công việc:** bảo quản, chuyển giao và xóa theo pháp luật/chính sách; tránh xóa hồ sơ kiểm toán khi chưa hết hạn lưu trữ.

## 7. Rehire và chuyển loại quan hệ: một người có thể có nhiều giai đoạn làm việc

Một người từng nghỉ việc có thể được tuyển trở lại. Cũng có trường hợp Contractor chuyển thành Employee hoặc Employee chuyển sang Contractor. Nếu hệ thống tạo tài khoản mới chỉ dựa trên email hoặc tự động kích hoạt tài khoản cũ, có thể gây **gắn nhầm danh tính** hoặc **phục hồi quyền không còn được chấp thuận**.

Quy trình an toàn cần tách ba cấp:

1. **Person**: người thật cần được xác minh để biết có đúng là người từng có hồ sơ cũ hay không.
2. **Employment engagement**: mỗi giai đoạn/quan hệ lao động có ID, thời hạn và loại quan hệ phù hợp.
3. **Accounts & entitlements**: tài khoản và quyền được cấp theo quan hệ **hiện tại**, có thể tái sử dụng an toàn hoặc tạo mới theo chính sách.

Ví dụ, Hương từng là Employee bộ phận Marketing, nghỉ một năm rồi trở lại trong vai trò Phân tích dữ liệu. Tổ chức có thể nối giai đoạn mới tới cùng hồ sơ Person nếu đã xác minh chắc chắn; tuy nhiên **không được mặc định khôi phục** quyền Marketing, phiên cũ hay khóa cũ. Cần tính lại quyền từ dữ liệu công việc mới và ghi vết quyết định.

Khi đổi loại quan hệ, cần đảm bảo một người không vô tình có hai danh tính hoạt động độc lập với quyền cộng dồn. Việc hợp nhất/hủy liên kết phải có bằng chứng và giữ được lịch sử kiểm toán.

## 8. Employee được cấp quyền ra sao? RBAC, ABAC và ngoại lệ

### RBAC — quyền theo vai trò

**Role-Based Access Control (RBAC)** gắn quyền với vai trò được định nghĩa trước. Employee nhận vai trò phù hợp với công việc.

Ví dụ:

~~~text
Employee An
  jobCode: ACCOUNTANT
  department: FINANCE
      |
      v
IAM role: finance-basic
      |
      +-- Read expense reports
      +-- Submit expense reconciliation
      +-- No production admin access
~~~

RBAC thuận tiện cho quyền phổ biến, nhưng vai trò quá rộng có thể cấp dư và quá nhiều vai trò ngoại lệ có thể khó bảo trì.

### ABAC — quyền theo thuộc tính và ngữ cảnh

**Attribute-Based Access Control (ABAC)** sử dụng thuộc tính của chủ thể, tài nguyên, hành động và môi trường. Ví dụ điều kiện cho phép Employee đọc một báo cáo nội bộ:

~~~text
ALLOW if
  subject.workerType == "employee"
  AND subject.employmentStatus == "ACTIVE"
  AND subject.departmentId == resource.ownerDepartment
  AND action == "read"
  AND resource.classification <= subject.clearance
~~~

Đây là **quy tắc minh họa**, không phải một chính sách mặc định hoặc ngôn ngữ ABAC chuẩn. Hệ thống thực tế cần quy định rõ thứ tự đánh giá, nguồn tin cậy của từng thuộc tính, cơ chế từ chối mặc định và cách xử lý thuộc tính bị thiếu/cũ.

ABAC chỉ đưa ra quyết định phù hợp nếu thuộc tính Employee **đúng và kịp thời**. Khi Employee chuyển phòng ban nhưng \`departmentId\` cũ vẫn được sử dụng, một chính sách viết đúng vẫn có thể cho phép truy cập sai.

### Nguyên tắc cấp quyền và rà soát

- **Least privilege:** cấp phạm vi tối thiểu cần cho công việc, tránh mặc định toàn bộ Employee có quyền trên mọi ứng dụng.
- **Separation of duties (SoD):** hạn chế một người cùng nắm các quyền có xung đột lợi ích, ví dụ tạo nhà cung cấp và tự phê duyệt khoản thanh toán cho nhà cung cấp đó.
- **Time-bound access:** quyền đặc biệt hoặc quyền dự án nên có thời hạn và cơ chế tự thu hồi.
- **Approval & recertification:** người quản lý và owner ứng dụng rà soát quyền định kỳ hoặc theo sự kiện thay đổi vai trò.
- **Privileged Access Management (PAM):** tài khoản/phiên đặc quyền cần kiểm soát tăng cường, tách khỏi tài khoản Employee sử dụng hằng ngày khi thích hợp.

Người phê duyệt quyền cần có đủ thông tin về vai trò và mục đích truy cập; việc một nhân viên là quản lý không đồng nghĩa có thể tự phê duyệt mọi quyền của bản thân.

## 9. Mô hình trạng thái Employee và tác động truy cập

Mỗi tổ chức có thể dùng tên trạng thái khác nhau, nhưng nên định nghĩa rành mạch:

| Trạng thái vòng đời minh họa | Ý nghĩa | Nguyên tắc truy cập |
| --- | --- | --- |
| **PRE_HIRE / PENDING** | Đã có hồ sơ, chưa tới ngày bắt đầu hoặc chưa đủ điều kiện xác minh. | Có thể chuẩn bị tài khoản nhưng chưa kích hoạt quyền nghiệp vụ. |
| **ACTIVE** | Quan hệ lao động có hiệu lực và nhân viên đủ điều kiện. | Quyền theo vai trò, chính sách và các phê duyệt hiện hành. |
| **ON_LEAVE** | Nghỉ dài hạn nhưng quan hệ có thể còn hiệu lực. | Giữ, hạn chế hoặc tạm khóa theo chính sách và tình huống. |
| **SUSPENDED** | Truy cập bị tạm ngưng theo quyết định hợp lệ. | Khóa hoặc hạn chế đường truy cập được chỉ định, theo dõi việc khôi phục. |
| **TERMINATED** | Quan hệ đã kết thúc. | Thu hồi quyền và thông tin xác thực, đối soát ứng dụng đích. |

Trạng thái Employee tại HRIS **không nhất thiết tương ứng một-một** với trạng thái account tại IdP. Ví dụ, trạng thái \`ACTIVE\` trong HRIS nhưng tài khoản vẫn khóa tạm thời do sự cố bảo mật. Vì thế cần tách **trạng thái nghiệp vụ**, **trạng thái định danh** và **trạng thái kỹ thuật của từng tài khoản**.

### Sơ đồ chuyển trạng thái minh họa

~~~mermaid
stateDiagram-v2
    [*] --> PRE_HIRE: Tuyển dụng đã ghi nhận
    PRE_HIRE --> ACTIVE: Xác minh + đến ngày bắt đầu
    ACTIVE --> ON_LEAVE: Bắt đầu nghỉ dài hạn
    ON_LEAVE --> ACTIVE: Được xác nhận trở lại
    ACTIVE --> SUSPENDED: Quyết định tạm ngưng
    SUSPENDED --> ACTIVE: Quyết định khôi phục
    ACTIVE --> TERMINATED: Kết thúc quan hệ
    ON_LEAVE --> TERMINATED: Kết thúc quan hệ
    SUSPENDED --> TERMINATED: Kết thúc quan hệ
    TERMINATED --> [*]
~~~

**Rehire** nên được xử lý như **quan hệ lao động mới có kiểm chứng**: tùy kiến trúc có thể nối về cùng Person nhưng phải cấp quyền dựa trên ngữ cảnh mới; không coi chuyển ngược trực tiếp từ \`TERMINATED\` sang \`ACTIVE\` là khôi phục toàn bộ quyền cũ.

## 10. Một ví dụ kỹ thuật: từ sự kiện HRIS đến quyết định IAM

Giả sử HRIS phát sự kiện thay đổi nhân viên:

~~~json
{
  "eventId": "hr-evt-7215",
  "eventType": "EMPLOYEE_JOB_CHANGED",
  "personId": "person-2041",
  "employeeRecordId": "EMP-9031",
  "effectiveAt": "2026-11-25T00:00:00+07:00",
  "previous": {
    "departmentId": "SALES",
    "jobCode": "SALES_EXEC"
  },
  "current": {
    "departmentId": "FIN",
    "jobCode": "ACCOUNTANT"
  },
  "sourceSystem": "HRIS"
}
~~~

Dữ liệu trên chỉ là ví dụ thiết kế. Luồng xử lý có thể được biểu diễn bằng giả mã:

~~~text
onTrustedHrisEvent(event):
    validateSourceAndSchema(event)
    skipIfAlreadyProcessed(event.eventId)
    rejectIfStaleAgainstCurrentRecord(event)

    employee = resolveEmployeeByStableId(event.personId)
    if employee is ambiguous:
        createManualReviewCase(event)
        return

    verifyEmploymentStateAndEffectiveTime(employee, event)
    expectedAccess = calculatePolicyBasedEntitlements(employee)
    currentAccess = readAccountAndEntitlementInventory(employee)

    changes = diff(currentAccess, expectedAccess)
    enforceRequiredApprovals(changes)
    provisionAndRevoke(changes)
    verifyTargetSystems(changes)
    recordTraceableAuditResult(event, changes)
~~~

Các điểm cần lưu ý khi triển khai:

- Sự kiện HRIS có thể được gửi lặp hoặc đến sai thứ tự. Cần **idempotency** và kiểm soát phiên bản/thời điểm để tránh áp dụng lại sự kiện cũ.
- **\`effectiveAt\`** có thể ở tương lai; không nên áp dụng quyền mới sớm nếu chính sách yêu cầu chờ ngày có hiệu lực.
- Thông tin Employee trong dữ liệu sự kiện phải được đối chiếu với bản ghi nguồn đáng tin cậy khi mức rủi ro đòi hỏi.
- \`provisionAndRevoke\` có thể thành công một phần. Cần ghi kết quả **từng ứng dụng**, retry an toàn và đối soát trạng thái.
- Thời điểm hệ thống gửi lệnh \`disable\` không tự chứng minh ứng dụng đã thu hồi phiên hoặc token.

## 11. Kiểm toán và khả năng truy vết Employee

Một thay đổi liên quan Employee cần cho phép điều tra từ **sự kiện nhân sự → quyết định phân quyền → lệnh thay đổi → kết quả thực tế**.

| Sự kiện | Bằng chứng nên lưu | Giá trị kiểm toán |
| --- | --- | --- |
| **Employee được tạo/xác minh** | Nguồn hồ sơ, ID ổn định, thời gian và kết quả xác minh. | Chứng minh tài khoản thuộc đúng người. |
| **Kích hoạt tài khoản** | Người/nguồn phê duyệt, ngày hiệu lực, tài khoản IdP và ứng dụng. | Tránh kích hoạt sớm hoặc cấp nhầm. |
| **Cấp quyền** | Quyền trước/sau, vai trò, chính sách, người phê duyệt và ứng dụng đích. | Giải trình vì sao Employee có quyền. |
| **Mover** | Vai trò/phòng ban cũ và mới, ngày hiệu lực, quyền cấp và thu hồi. | Phát hiện quyền tích lũy. |
| **Leaver** | Sự kiện chấm dứt, thời điểm khóa, kết quả thu hồi từng ứng dụng, phiên/token. | Chứng minh việc ngừng truy cập thực sự. |
| **Rà soát quyền** | Người đánh giá, quyết định giữ/thu hồi, hạn xử lý và kết quả. | Phát hiện quyền không còn cần thiết. |
| **Ngoại lệ** | Lý do, người chịu trách nhiệm, phê duyệt, thời hạn và đánh giá lại. | Ngăn ngoại lệ tồn tại vô thời hạn. |

Với OIDC/SAML và SSO, log IdP cho biết một lần xác thực hoặc phát hành khẳng định danh tính; để biết Employee **đã thao tác gì trong ứng dụng**, cần kết hợp log của ứng dụng. Không ghi mật khẩu, access token, refresh token, mã MFA hoặc bí mật khác vào kho kiểm toán.

Với SCIM/API, nên phân biệt kết quả \`REQUESTED\`, \`SENT\`, \`ACKNOWLEDGED\`, \`VERIFIED\` và \`FAILED\` để không nhầm **lệnh đã gửi** với **trạng thái đã xác minh ở đích**. Log và bằng chứng phải được bảo vệ khỏi sửa/xóa trái phép, đồng thời giới hạn dữ liệu cá nhân và thời gian lưu theo chính sách.

## 12. Chỉ số kiểm soát vòng đời Employee

| Chỉ số | Cách tính/quan sát | Vấn đề phát hiện |
| --- | --- | --- |
| **Tỷ lệ Employee có danh tính liên kết hợp lệ** | Employee đang hoạt động có \`subjectId\` và ánh xạ tài khoản được xác minh ÷ tổng Employee trong phạm vi. | Hồ sơ trùng, gắn nhầm hoặc thiếu tài khoản. |
| **Tỷ lệ Joiner sẵn sàng đúng hạn** | Người mới có tài khoản/quyền đã xác nhận đúng vào ngày bắt đầu ÷ tổng Joiner được theo dõi. | Chậm cấp phát hoặc lỗi tích hợp. |
| **Tỷ lệ Mover đã thu hồi quyền cũ** | Sự kiện Mover có quyền cũ không còn hợp lệ đã được xác minh thu hồi ÷ tổng Mover cần thu hồi. | Privilege creep. |
| **Độ trễ Leaver** | Thời gian từ khi quan hệ kết thúc có hiệu lực đến lúc tài khoản/quyền được xác minh thu hồi ở hệ thống đích. | Quyền truy cập tồn dư. |
| **Tài khoản Employee mồ côi** | Tài khoản hoạt động không còn liên kết được với Employee/quan hệ hợp lệ. | Tài khoản bị bỏ quên hoặc tài khoản phụ chưa đóng. |
| **Tỷ lệ quyền Employee được rà soát đúng hạn** | Quyền nằm trong kỳ rà soát và có quyết định hợp lệ ÷ tổng quyền phải rà soát. | Quyền ngoại lệ không được kiểm soát. |
| **Tỷ lệ tác vụ JML lỗi hoặc chưa xác nhận** | Tác vụ quá hạn ở trạng thái lỗi/không rõ kết quả ÷ tổng tác vụ thuộc phạm vi. | Mất đồng bộ với ứng dụng. |

Các chỉ số nên phân theo hệ thống, loại quyền và mức rủi ro. Không nên xem \`API 200 OK\` hay \`provisioning completed\` là kết quả thu hồi đầy đủ nếu chưa kiểm chứng quyền và tài khoản ở hệ thống đích.

## 13. Tình huống tổng hợp

**Bối cảnh:** nhân viên Hà đang làm việc tại bộ phận Vận hành, có tài khoản SSO, quyền báo cáo vận hành và một tài khoản quản trị ứng dụng phụ. Hà chuyển sang bộ phận Kiểm thử từ đầu tháng sau, sau đó nghỉ việc hai tháng sau nữa.

**Giai đoạn Mover:**

1. HRIS phát sự kiện chuyển vị trí với ngày hiệu lực. IAM giữ liên kết Person/Employee và cập nhật thuộc tính công việc.
2. Chính sách đánh giá lại quyền: cấp ứng dụng kiểm thử, thu hồi quyền vận hành không còn cần và xem xét quyền quản trị phụ.
3. Hệ thống cấp phát gửi lệnh tới các ứng dụng, rồi đọc lại quyền thực tế. Quyền quản trị phụ không nên bị bỏ qua chỉ vì tài khoản SSO đã đổi nhóm.

**Giai đoạn Leaver:**

1. HRIS phát sự kiện hết hiệu lực quan hệ lao động; IdP khóa tài khoản đúng hạn.
2. Hệ thống vô hiệu hóa tài khoản ứng dụng và tài khoản quản trị phụ, xử lý phiên/token theo cơ chế hỗ trợ.
3. Nếu Hà là owner của một service account phục vụ tác vụ báo cáo, hệ thống cần chuyển owner hoặc chấm dứt workload có kiểm soát.
4. Bộ phận bảo mật đối soát trạng thái cuối và lưu bằng chứng. Nếu ứng dụng kiểm thử không nhận lệnh SCIM, yêu cầu được giữ ở trạng thái lỗi có người phụ trách cho tới khi được xác minh.

Kịch bản này cho thấy việc quản lý Employee cần quan tâm đồng thời đến **đúng người**, **đúng quyền**, **đúng thời điểm**, **khả năng truy vết** và **thu hồi truy cập thực tế**.

## 14. Checklist đánh giá quản lý Employee

1. **Định danh:** mỗi Employee có nguồn có thẩm quyền, định danh ổn định và tài khoản được liên kết có kiểm chứng chưa?
2. **Joiner:** có kiểm tra ngày bắt đầu, xác minh người mới, kích hoạt an toàn và cấp quyền tối thiểu không?
3. **Mover:** thay đổi phòng ban, vai trò, quản lý và nghỉ dài hạn có cập nhật đúng thuộc tính và **thu hồi quyền cũ** không?
4. **Leaver:** có kiểm tra IdP, ứng dụng không SSO, tài khoản đặc quyền, phiên/token và quyền chia sẻ trước khi kết luận thu hồi hoàn tất không?
5. **Phân quyền:** RBAC/ABAC có dựa trên dữ liệu nhân sự đáng tin cậy, còn hiệu lực và có phê duyệt khi cần không?
6. **Trường hợp đặc biệt:** tái tuyển dụng, Employee chuyển thành Contractor, service account mất owner và tài khoản dùng chung có quy trình rõ ràng không?
7. **Kiểm toán:** có thể truy từ sự kiện HRIS đến quyết định, lệnh SCIM/API và trạng thái tại ứng dụng đích không?
8. **Đối soát:** có phát hiện tài khoản mồ côi, quyền tích lũy, luồng đồng bộ lỗi và ngoại lệ quá hạn không?

**Ghi nhớ:** **Employee là loại chủ thể dựa trên quan hệ lao động, không phải một quyền truy cập.** Quản lý Employee trong IAM cần duy trì mối liên hệ đúng giữa người thật, hồ sơ nhân sự, danh tính số, tài khoản và quyền ở từng giai đoạn **Joiner–Mover–Leaver**. Quyền phải đi theo nhu cầu công việc hiện tại và được kiểm chứng đã thu hồi khi quan hệ hoặc vai trò thay đổi; đó là cơ sở để giảm truy cập tồn dư và duy trì khả năng kiểm toán.
