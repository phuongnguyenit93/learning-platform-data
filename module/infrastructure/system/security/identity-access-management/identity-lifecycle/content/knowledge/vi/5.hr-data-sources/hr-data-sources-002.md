# Employee record: bản ghi nhân viên làm nguồn dữ liệu cho vòng đời danh tính IAM

## 1. Employee record là gì và vì sao IAM cần nó?

**Employee record** là bản ghi có cấu trúc về một người lao động hoặc một quan hệ làm việc do hệ thống quản lý nhân sự (**HRIS**, *Human Resource Information System*) lưu giữ. Tùy tổ chức, bản ghi này có thể mô tả người, hợp đồng/quan hệ lao động, vị trí, đơn vị tổ chức, quản lý, thời gian gia nhập, thay đổi công tác và trạng thái kết thúc quan hệ làm việc.

Trong **Identity and Access Management (IAM)**, thông tin HR là một đầu vào quan trọng để quyết định **khi nào tạo danh tính số, ai đủ điều kiện có tài khoản, cần những quyền nào và khi nào phải thu hồi**. Chẳng hạn, nếu HR xác nhận một nhân viên nghỉ việc vào thời điểm xác định, IAM cần chấm dứt những quyền xuất phát từ quan hệ làm việc đó, kể cả khi tên đăng nhập vẫn còn tồn tại trong một ứng dụng.

Employee record **không đồng nghĩa** với:

- **Person:** một con người thực, có thể có nhiều giai đoạn hợp đồng hoặc quan hệ công việc.
- **Identity:** bản ghi danh tính số do IAM/IdP quản lý, có định danh, trạng thái và các liên kết cần để xác thực/ủy quyền.
- **Account:** tài khoản kỹ thuật ở IdP, hệ điều hành, dịch vụ SaaS, database hoặc ứng dụng.
- **Entitlement:** quyền truy cập tài nguyên hoặc hành động cụ thể; không tự xuất hiện chỉ vì có bản ghi nhân sự.

Ví dụ: một nhân viên có một bản ghi người trong HRIS, hai lần tuyển dụng ở các thời kỳ khác nhau và nhiều tài khoản ở IdP, Git, hệ thống ERP. IAM phải phân biệt **người là ai**, **quan hệ làm việc nào đang hiệu lực** và **tài khoản/quyền nào gắn với quan hệ đó**.

Mục tiêu của bài là hiểu cách sử dụng employee record làm nguồn tín hiệu đáng tin cậy trong chu trình **Joiner–Mover–Leaver (JML)**, kết hợp xác minh danh tính, cung cấp tài khoản, RBAC/ABAC, IdP, SSO, SCIM, kiểm toán và phát hiện quyền truy cập tồn dư.

## 2. Phân biệt bản ghi người, bản ghi công việc và tài khoản

Hệ thống HRIS ở các tổ chức không có mô hình dữ liệu thống nhất. Một số hệ thống lưu mọi thông tin trong một record “employee”; hệ thống khác tách thành người, quan hệ lao động, hợp đồng và phân công công việc.

| Thành phần | Câu hỏi chính | Đặc điểm |
| --- | --- | --- |
| **Person record** | Đây là người nào? | Dữ liệu định danh cá nhân, có thể tồn tại qua nhiều đợt làm việc |
| **Employment / worker record** | Người này có quan hệ làm việc nào với tổ chức? | Loại nhân sự, ngày bắt đầu/kết thúc, trạng thái, đơn vị tuyển dụng |
| **Assignment / position record** | Hiện tại người này làm gì, ở đâu, do ai quản lý? | Vị trí, phòng ban, dự án, người quản lý, lịch sử thay đổi |
| **IAM identity** | Danh tính số nào đại diện cho chủ thể được xác minh? | Định danh trung tâm, trạng thái IAM, quy tắc quản trị |
| **Application account** | Chủ thể sử dụng hệ thống nào? | Username và ID cục bộ trong ứng dụng, trạng thái được cấp phát |
| **Access assignment** | Vì sao chủ thể được phép tới tài nguyên nào? | Role, group, entitlement, chính sách, phê duyệt và thời hạn |

Quan hệ giữa các thực thể có thể hình dung như sau:

~~~mermaid
flowchart TD
    P["Person<br/>Con người"] -->|"có một hoặc nhiều"| E["Employment / Worker record<br/>Quan hệ làm việc"]
    E -->|"có theo thời gian"| A["Assignment<br/>Phân công công việc"]
    P -->|"được xác minh, liên kết"| I["IAM identity<br/>Danh tính số"]
    E -->|"cung cấp trạng thái / điều kiện"| I
    A -->|"cung cấp thuộc tính / chính sách"| G["Group / Role<br/>Nhóm và vai trò"]
    I -->|"được cung cấp"| C["Application account<br/>Tài khoản ứng dụng"]
    G -->|"được ánh xạ tới"| R["Entitlement<br/>Quyền truy cập"]
    R -->|"áp dụng trên"| T["Resource<br/>Tài nguyên"]
~~~

Sơ đồ là mô hình khái niệm. Trong thực tế, quyết định cấp quyền phải đi qua chính sách và kiểm tra phù hợp; một mũi tên nối dữ liệu không có nghĩa hệ thống tự cho phép truy cập.

**Điểm cần nhớ:** employee record là **nguồn sự thật có thẩm quyền đối với những thuộc tính nhân sự được tổ chức giao HR quản lý**. Nó không mặc nhiên là nguồn sự thật duy nhất cho mọi quyền, dự án, tài khoản dịch vụ hoặc phân công vận hành.

## 3. Các trường dữ liệu cần hiểu trong employee record

Không có bộ trường bắt buộc áp dụng cho mọi HRIS. Bảng sau mô tả những trường **thường hữu ích cho tích hợp IAM**, không phải yêu cầu phải sao chép toàn bộ hồ sơ nhân sự:

| Nhóm dữ liệu | Ví dụ trường | Công dụng với IAM | Lưu ý |
| --- | --- | --- | --- |
| **Định danh** | `personId`, `workerId`, `employmentId` | Liên kết chính xác người, quan hệ làm việc và danh tính số | Cần hiểu phạm vi duy nhất và khả năng tái sử dụng từng ID |
| **Loại lao động** | `workerType`, `employmentType` | Phân biệt nhân viên, nhà thầu, thực tập sinh theo chính sách | Không tự suy quyền chỉ từ một nhãn |
| **Trạng thái** | `employmentStatus` | Kích hoạt Joiner, Mover, Leaver hoặc rà soát | Giá trị HRIS phải được ánh xạ thành trạng thái IAM cụ thể |
| **Ngày hiệu lực** | `startDate`, `endDate`, `effectiveFrom` | Lên lịch kích hoạt/thu hồi theo thời điểm | Dùng múi giờ và quy ước thời gian nhất quán |
| **Tổ chức** | `legalEntity`, `departmentId`, `costCenter` | Định tuyến quản trị, gán phạm vi tổ chức phù hợp | Cập nhật phòng ban có thể làm thay đổi quyền |
| **Vai trò công việc** | `jobCode`, `positionId`, `jobTitle` | Căn cứ xét role cơ bản và rà soát quyền | Ưu tiên mã chuẩn; tên chức danh tự do thường không ổn định |
| **Quản lý** | `managerWorkerId` | Xác định tuyến phê duyệt, trách nhiệm và xử lý ngoại lệ | Cần xác minh người quản lý còn hiệu lực |
| **Địa điểm** | `workLocation`, `region` | Điều kiện ABAC, giới hạn dữ liệu theo phạm vi | Không đồng nghĩa vị trí vật lý hoặc quyền truy cập |
| **Phân công** | `assignmentId`, `projectId`, `assignmentEnd` | Tính phạm vi tài nguyên và thời hạn quyền | Nguồn có thẩm quyền có thể là hệ thống dự án |
| **Liên hệ** | `workEmail`, `displayName` | Giao tiếp, gợi ý tài khoản, hiển thị UI | Email và tên có thể đổi; tránh dùng làm khóa liên kết duy nhất |
| **Dữ liệu vận hành** | `recordVersion`, `updatedAt`, `sourceSystem` | Đối soát, xử lý bản ghi cũ và truy vết thay đổi | Thời điểm sửa bản ghi khác thời điểm nghiệp vụ có hiệu lực |

Các dữ liệu như thông tin lương, số giấy tờ tùy thân, địa chỉ gia đình hoặc hồ sơ y tế **thường không cần được sao chép vào IdP để quyết định quyền truy cập**. Chỉ chuyển tiếp trường phục vụ mục đích IAM đã xác định, với kiểm soát bảo vệ dữ liệu cá nhân phù hợp.

### Khóa định danh: phần quan trọng nhất khi tích hợp

Một thiết kế nên trả lời rõ:

1. `personId` chỉ một **con người** hay một **lần tuyển dụng**?
2. `workerId` có được giữ khi nghỉ rồi quay lại làm việc không?
3. Có nhiều `employmentId` hoặc hợp đồng đồng thời với cùng một person không?
4. Phạm vi duy nhất của ID là toàn tổ chức hay chỉ trong từng công ty con/tenant?
5. Khi hợp nhất công ty hoặc di chuyển HRIS, ánh xạ ID cũ sang ID mới thế nào?

Không nên tự động hợp nhất tài khoản dựa trên **họ tên hoặc email trùng nhau**. Việc liên kết sai có thể khiến người này kế thừa quyền của người khác. Nếu có khả năng tái tuyển dụng, cần cơ chế đối soát người thật, bản ghi hợp đồng cũ/mới và chính sách cấp lại tài khoản.

## 4. Bản ghi nhân viên nào được coi là đáng tin cậy?

**Authoritative source** là hệ thống hoặc quy trình được tổ chức chỉ định có thẩm quyền tạo và cập nhật một loại dữ liệu. HRIS thường có thẩm quyền về tình trạng nhân sự chính thức; hệ thống dự án có thể có thẩm quyền về tư cách thành viên dự án; chủ tài nguyên và hệ thống cấp quyền có thẩm quyền về entitlement được phê duyệt.

| Sự kiện/thông tin | Nguồn được giao thẩm quyền (ví dụ) | IAM sử dụng |
| --- | --- | --- |
| Nhân viên ký hợp đồng, ngày bắt đầu | HRIS | Tạo luồng Joiner; lập lịch kích hoạt |
| Chấm dứt quan hệ lao động | HRIS/quy trình nhân sự được ủy quyền | Bắt đầu thu hồi và xác nhận các tài khoản liên quan |
| Đổi phòng ban/chức danh/người quản lý | HRIS | Đánh giá Mover, tái tính quyền theo chính sách |
| Được phân công dự án đặc biệt | Hệ thống quản lý dự án được chỉ định | Gán hoặc thu hồi quyền theo dự án |
| Được duyệt đọc dữ liệu nhạy cảm | Chủ tài nguyên/quy trình phê duyệt | Ghi nhận entitlement cụ thể, giới hạn phạm vi và thời hạn |
| Tài khoản thực sự đang có trên ứng dụng | Ứng dụng/IdP đích | Đối soát trạng thái provisioning và quyền hiệu lực |

Nếu hai nguồn bất đồng, không nên chọn tùy tiện bản ghi “mới nhất”. Cần quy tắc giải quyết theo **trường dữ liệu**, thẩm quyền và thời điểm hiệu lực. Chẳng hạn, một tài khoản SaaS ở trạng thái `active` không bác bỏ thông tin HR đã xác nhận nhân viên nghỉ việc; nó có thể là bằng chứng cần thu hồi tài khoản còn sót.

**Độ tin cậy của dữ liệu** còn phụ thuộc cách employee record được tạo. Cần phân biệt dữ liệu đã xác minh, bản nháp dự kiến tuyển dụng, yêu cầu chưa duyệt và cập nhật chính thức. Một lịch dự kiến tuyển nhân viên tháng sau không nên ngay lập tức tạo quyền truy cập đến hệ thống sản xuất.

## 5. Chu trình employee record và trạng thái IAM

Trạng thái HR không nhất thiết giống trạng thái kỹ thuật của danh tính. Ví dụ, `pre-hire` có thể cho phép đặt trước account nhưng chưa cho đăng nhập; `on leave` không phải lúc nào cũng có nghĩa phải xóa mọi quyền. Tổ chức cần **bảng ánh xạ chính sách** thay vì giả định mọi mã trạng thái có cùng ý nghĩa.

| Tình trạng nghiệp vụ (minh họa) | Ý nghĩa | Hành động IAM có thể áp dụng |
| --- | --- | --- |
| **Planned / pre-hire** | Đã có hồ sơ dự kiến, chưa đến ngày làm việc | Đối soát identity, chuẩn bị tài khoản ở trạng thái chưa sử dụng |
| **Active** | Quan hệ làm việc có hiệu lực | Kích hoạt theo điều kiện xác minh và vai trò đã được phê duyệt |
| **Leave / suspended** | Nghỉ dài hạn hoặc tạm dừng | Điều chỉnh quyền theo chính sách, mức độ nhạy cảm và loại nghỉ |
| **Transfer / assignment change** | Chuyển vai trò, phòng ban hoặc dự án | Tính chênh lệch quyền cũ/mới, thu hồi quyền không còn căn cứ |
| **Terminated / ended** | Quan hệ làm việc kết thúc | Vô hiệu hóa/thu hồi đường truy cập phát sinh từ quan hệ đó |
| **Rehire** | Người từng làm việc quay lại với quan hệ mới | Xác minh, liên kết đúng người, đánh giá lại quyền từ đầu |

Các nhãn trên là **ví dụ**, không phải từ vựng chuẩn chung của HRIS. Với người có **nhiều quan hệ lao động đang hoạt động**, kết thúc một hợp đồng có thể chỉ cần thu hồi những quyền gắn với hợp đồng đó; việc có nên khóa identity dùng chung phụ thuộc chính sách và các quan hệ còn hiệu lực. Không nên máy móc biến mọi sự kiện `termination` thành xóa hoàn toàn thông tin danh tính nếu còn nghĩa vụ lưu vết hoặc công việc hợp lệ khác.

### Ngày có hiệu lực khác ngày dữ liệu được ghi nhận

Giả sử HR nhập sự kiện ngày 10/11, thông báo nhân viên chuyển bộ phận từ ngày 18/11:

- **Recorded/updated time:** 10/11 — hệ thống biết có thay đổi.
- **Effective time:** 18/11 — từ thời điểm này chính sách quyền mới bắt đầu áp dụng.
- **Processed time:** thời điểm IAM thực nhận, tính toán và đồng bộ sự kiện.

Nếu xử lý nhầm thời điểm, quyền cũ có thể bị cắt quá sớm hoặc vẫn còn sau khi nhân viên đổi vai trò. Cần quy ước timezone, định nghĩa khi nào một ngày theo lịch tương ứng với thời điểm kỹ thuật, và xử lý trường hợp thay đổi được nhập **lùi ngày**. Với nghỉ việc khẩn cấp, quy trình có thể yêu cầu thu hồi ngay theo kênh đã được phê duyệt thay vì chờ một batch định kỳ.

## 6. Luồng dữ liệu từ HRIS đến hệ thống truy cập

Một luồng tích hợp phổ biến gồm **HRIS → hệ thống đồng bộ/chuẩn hóa → IAM governance → IdP → ứng dụng đích**. Trong đó, từng hệ thống có trách nhiệm khác nhau:

~~~mermaid
flowchart TD
    H["HRIS<br/>Employee record, sự kiện hiệu lực"] --> X["Connector / Integration<br/>Lọc trường, kiểm tra, chuẩn hóa"]
    X --> I["IAM governance<br/>Liên kết identity, đánh giá chính sách"]
    I --> P["IdP<br/>Trạng thái, thuộc tính, nhóm"]
    P -->|"SCIM / API nếu hỗ trợ"| A["Ứng dụng đích<br/>Account, group, role"]
    P -->|"SSO / claim"| S["Xác thực đăng nhập"]
    I --> C["Chủ tài nguyên / Workflow phê duyệt"]
    C --> I
    A --> V["Đối soát quyền thực tế<br/>và trạng thái tài khoản"]
    V --> I
    I --> L["Nhật ký / kiểm toán"]
~~~

- **HRIS** cung cấp dữ liệu nhân sự thuộc thẩm quyền và những thay đổi đã xác nhận.
- **Connector/integration** xác thực nguồn, kiểm tra schema, lọc PII không cần, chuẩn hóa mã trường, xử lý trùng bản ghi và chuyển sự kiện.
- **IAM governance** liên kết đúng person/worker/identity/account; xác định quyền theo chính sách và yêu cầu phê duyệt.
- **IdP** quản lý danh tính đăng nhập, xác thực, trạng thái, nhóm và những thuộc tính cần thiết cho ứng dụng.
- **SSO (Single Sign-On)** giúp đăng nhập thống nhất; không tự quyết định quyền trên mọi tài nguyên bên trong ứng dụng.
- **SCIM (System for Cross-domain Identity Management)** hỗ trợ provisioning/cập nhật/vô hiệu hóa tài khoản và nhóm tại ứng dụng hỗ trợ; phạm vi entitlement tùy khả năng từng hệ thống.
- **Ứng dụng đích** là nơi cần kiểm tra quyền **thực tế có hiệu lực**, gồm vai trò cục bộ, ACL, quyền kế thừa và các token còn hạn.

Đừng xem thông báo “đã gửi sự kiện HR” là bằng chứng người dùng đã có hoặc đã mất quyền. Cần đối chiếu kết quả ở điểm thực thi cuối cùng.

## 7. Employee record trong ba giai đoạn Joiner–Mover–Leaver

### 7.1. Joiner: tạo danh tính đúng người, đúng thời điểm

Ví dụ HRIS tạo employee record của An với `workerId` ổn định, `startDate` tuần tới, phòng ban kỹ thuật và manager đã được xác minh. Quy trình điển hình:

1. Kiểm tra record thuộc trạng thái đủ tin cậy để bắt đầu onboarding; xác minh danh tính và chính sách áp dụng với loại lao động của An.
2. Tìm person/identity hiện có bằng **ID và quy trình liên kết đáng tin cậy**, tránh tạo trùng hoặc gắn nhầm tài khoản.
3. Tạo identity, tài khoản IdP và những account cần thiết theo chính sách; có thể chuẩn bị trước nhưng trì hoãn kích hoạt đến đúng mốc.
4. Suy ra nhóm và role cơ bản từ phòng ban, job code, loại nhân sự; quyền nhạy cảm hoặc đặc thù dự án cần căn cứ/phê duyệt bổ sung.
5. Đặt kỳ rà soát, thời hạn phù hợp, xác nhận tài khoản được cấp thành công và ghi nhận dấu vết.

Việc nhân viên có `departmentId = engineering` chỉ chứng minh thuộc một đơn vị, **không có nghĩa** được cấp quyền quản trị tất cả hạ tầng kỹ thuật.

### 7.2. Mover: thay đổi phân công và loại bỏ quyền tồn dư

Nếu employee record đổi `departmentId`, `jobCode`, `managerWorkerId` hoặc thay đổi assignment, IAM cần so sánh **trạng thái quyền hiện tại** và **trạng thái quyền cần có ở thời điểm hiệu lực**:

| Bước | Công việc |
| --- | --- |
| Phát hiện | Nhận sự kiện cập nhật đã được xác thực, xác định các trường thay đổi có ảnh hưởng quyền |
| Đánh giá | Xác định những nhóm, role, entitlement phải giữ, thêm, thu hồi |
| Phê duyệt | Yêu cầu chủ tài nguyên xác nhận quyền bổ sung hoặc ngoại lệ bàn giao khi cần |
| Thực thi | Thu hồi quyền cũ không còn căn cứ; cấp quyền mới theo thứ tự phù hợp nghiệp vụ |
| Xác minh | Đối chiếu IdP, ứng dụng và quyền thực tế; xử lý quyền trực tiếp hoặc nhóm kế thừa |

Chỉ thêm quyền mới mà không trừ quyền cũ gây **privilege accumulation**. Đối với giai đoạn bàn giao, quyền tạm thời phải có phạm vi, người phê duyệt và **thời điểm hết hạn** rõ ràng.

### 7.3. Leaver: thu hồi quyền phát sinh từ quan hệ làm việc

Khi HR xác nhận kết thúc quan hệ lao động, luồng Leaver cần:

1. Xác định chính xác identity và **mọi account** liên kết với quan hệ làm việc đó.
2. Xử lý vô hiệu hóa/thu hồi vào đúng thời điểm, ưu tiên biện pháp khẩn cấp nếu rủi ro hoặc chính sách yêu cầu.
3. Thu hồi nhóm, role, quyền trực tiếp, quyền API, phiên và token theo khả năng của hệ thống đích.
4. Kiểm tra tài khoản ứng dụng không đồng bộ, tài khoản cục bộ và quyền phát sinh từ nhóm lồng nhau.
5. Chuyển giao trách nhiệm sở hữu tài nguyên, quy trình tự động và tài khoản dịch vụ do người rời tổ chức quản lý.
6. Đối soát quyền hiệu lực; lưu sự kiện và kết quả trong hồ sơ kiểm toán với thời gian lưu phù hợp.

**Tài khoản dịch vụ/workload identity** cần được quản lý vòng đời riêng. Employee record có thể chỉ ra người chịu trách nhiệm hiện tại đã nghỉ việc, nhưng không nên tự động xóa service account đang phục vụ sản xuất nếu nhiệm vụ vẫn hợp lệ. IAM phải chuyển ownership, rà soát entitlement/credential và có phương án thay thế an toàn.

## 8. Ví dụ dữ liệu employee record và sự kiện thay đổi

Ví dụ JSON dưới đây chỉ phục vụ học tập, không đại diện chuẩn API của HRIS cụ thể. Tất cả giá trị đều giả lập; các trường thực tế phải dựa trên hợp đồng dữ liệu giữa HRIS và IAM.

~~~json
{
  "schemaVersion": "1",
  "sourceSystem": "example-hris",
  "personId": "person-482",
  "workerId": "worker-910",
  "employmentId": "employment-2026-18",
  "workerType": "employee",
  "employmentStatus": "active",
  "startDate": "2026-05-04",
  "endDate": null,
  "departmentId": "sales",
  "jobCode": "SALES_ANALYST",
  "managerWorkerId": "worker-117",
  "effectiveFrom": "2026-11-18T00:00:00+07:00",
  "recordVersion": 17,
  "updatedAt": "2026-11-10T08:30:00+07:00"
}
~~~

Ví dụ một sự kiện HR đã được xác nhận chuyển phòng ban, cũng ở dạng minh họa:

~~~json
{
  "eventId": "hr-event-8231",
  "eventType": "employment.assignment_changed",
  "workerId": "worker-910",
  "employmentId": "employment-2026-18",
  "before": {
    "departmentId": "sales",
    "jobCode": "SALES_ANALYST"
  },
  "after": {
    "departmentId": "finance",
    "jobCode": "FINANCE_ANALYST"
  },
  "effectiveAt": "2026-11-18T00:00:00+07:00",
  "publishedAt": "2026-11-10T08:31:00+07:00",
  "sourceVersion": 18
}
~~~

Không nên dựa duy nhất vào `eventType` để cấp/thu hồi. IAM phải đánh giá **snapshot hiện hành có hiệu lực**, chuỗi phiên bản và chính sách. Một sự kiện đến trễ có thể đã bị một quyết định sau đó thay thế.

### Kiểm soát sự kiện trùng, đến trễ và đảo thứ tự

Các kết nối theo sự kiện thường có thể gửi lại thông điệp, gặp timeout hoặc giao sự kiện không đúng thứ tự. Tích hợp cần:

- **Idempotency:** xử lý lại cùng sự kiện không tạo thêm tài khoản/quyền trùng hoặc thu hồi sai.
- **Versioning:** dùng mã phiên bản, sequence hoặc kiểm tra trạng thái hiện hành có thẩm quyền để không ghi đè dữ liệu mới bằng dữ liệu cũ.
- **Correlation:** ánh xạ `workerId`/ `employmentId` sang identity và các account đúng đích.
- **Reconciliation:** định kỳ đối soát snapshot HRIS với trạng thái IAM/IdP/ứng dụng, xử lý sự kiện bị mất.
- **Exception handling:** ghi nhận dữ liệu thiếu manager, ID trùng, record mâu thuẫn, giao dịch thất bại và phân công người giải quyết.
- **Auditability:** lưu mã sự kiện, nguồn, phiên bản, quyết định chính sách, kết quả cập nhật và thời điểm thực thi; tránh ghi PII nhạy cảm không cần thiết.

## 9. Từ trường HR đến RBAC và ABAC

**RBAC (Role-Based Access Control)** sử dụng vai trò được xác định theo chức năng công việc. Employee record có thể cung cấp `jobCode` hoặc `departmentId` để xác định một role cơ bản, nhưng mỗi role cần được quản trị với chủ sở hữu và quyền cụ thể đã phê duyệt.

**ABAC (Attribute-Based Access Control)** kiểm tra thuộc tính của chủ thể, tài nguyên và ngữ cảnh tại thời điểm yêu cầu. Employee record thường cung cấp các thuộc tính chủ thể như trạng thái làm việc hoặc khu vực nghiệp vụ; hệ thống tài nguyên có thể cung cấp thuộc tính phân loại hoặc dự án.

Ví dụ chính sách **mã giả**:

~~~text
ALLOW identity READ sales_report NẾU:
    employment_status(identity) = ACTIVE
    VÀ verified_employment(identity) = true
    VÀ job_role(identity) cho phép READ_SALES_REPORT
    VÀ assignment_region(identity) = sales_report.region
    VÀ policy_permission(identity, sales_report).chưa_hết_hạn
    VÀ không tồn tại quy tắc DENY ưu tiên cao hơn
ELSE DENY
~~~

Ở đây trạng thái và job code có thể đến từ employee record, trong khi `assignment_region` có thể do một hệ thống khác làm nguồn thẩm quyền. Việc có role “Sales Analyst” không đủ để đọc **mọi báo cáo bán hàng**; chính sách còn phải xác định **đúng tài nguyên, hành động và điều kiện**.

Hai nguyên tắc:

1. **Thay đổi thuộc tính HR không trực tiếp trao quyền đặc biệt:** phải có quy tắc ánh xạ và phê duyệt cần thiết.
2. **Kiểm tra tại hệ thống đích:** chỉ ẩn dashboard trên giao diện hoặc chỉ sửa claim SSO không thay thế kiểm soát backend/API và dữ liệu bên dưới.

## 10. Đồng bộ IdP, SSO, SCIM: cùng dữ liệu nhưng trách nhiệm khác nhau

Employee record thường được chuẩn hóa rồi cung cấp **một phần trường cần thiết** cho IdP. Sau đó:

| Cơ chế | Employee record đóng góp gì? | Điều không nên nhầm lẫn |
| --- | --- | --- |
| **IdP** | Trạng thái chủ thể, mã định danh liên kết, nhóm/thuộc tính phục vụ kiểm soát | IdP không tự có mọi dữ liệu tài nguyên và ACL ở các ứng dụng |
| **SSO** | Thuộc tính danh tính được phép đưa vào claim khi đăng nhập | Xác thực thành công không có nghĩa được phép truy cập mọi dữ liệu |
| **SCIM** | Thay đổi danh tính, trạng thái tài khoản, thành viên nhóm khi ứng dụng hỗ trợ | SCIM không mặc nhiên xử lý mọi entitlement/ACL, khóa API hay phiên hiện hành |
| **IAM governance** | Căn cứ công việc, thay đổi JML để đánh giá quyền và yêu cầu duyệt | Quyền mục tiêu phải được đối chiếu với quyền đã thực thi |

Ví dụ, HRIS đổi `departmentId` sang `finance`. IdP có thể cập nhật nhóm, SCIM có thể chuyển nhóm tới một ứng dụng, nhưng tài khoản vẫn có **quyền chia sẻ trực tiếp** tới thư mục Sales. Việc rà soát và thu hồi quyền tồn dư phải xét **quyền hiệu lực**, không chỉ kết quả đồng bộ nhóm.

Với tài khoản dịch vụ, người phụ trách từ employee record có thể là owner, song danh tính workload, credential, quyền trên API và trạng thái triển khai đến từ nguồn vận hành phù hợp. Những nguồn này cần kết nối để giải quyết sự kiện người phụ trách nghỉ việc mà không làm gián đoạn hệ thống.

## 11. Chất lượng dữ liệu và cách xử lý tình huống khó

### 11.1. Dữ liệu thiếu hoặc mâu thuẫn

Giả sử HRIS có `employmentStatus = active` nhưng thiếu `workerId`, hoặc hai người dùng cùng một identifier đáng lẽ duy nhất. Tích hợp cần chặn hoặc cô lập bản ghi rủi ro để xử lý theo quy trình, thay vì gán nhầm vào một identity đang tồn tại. Với trường phụ không ảnh hưởng truy cập, có thể tiếp nhận có cảnh báo tùy chính sách.

### 11.2. Người nghỉ rồi quay lại (rehire)

Rehire không mặc nhiên là “bật lại toàn bộ quyền cũ”. Phải xác minh lại người, xác định quan hệ làm việc mới và quyền cần thiết hiện tại. Nếu tái sử dụng tài khoản cũ được tổ chức cho phép, vẫn phải rà soát entitlement, phương thức xác thực, phiên/credential cũ và những liên kết ứng dụng còn sót.

### 11.3. Nhiều quan hệ lao động hoặc nhiều tổ chức

Một người có thể đồng thời là nhân viên của công ty A và nhà thầu cho đơn vị B. Kết thúc hợp đồng B có thể chỉ thu hồi quyền gắn với B; không được vô tình khóa các quyền chính đáng của quan hệ A. Quy tắc quản lý identity dùng chung, tenant, tài khoản riêng và phạm vi pháp nhân phải được xác định trước.

### 11.4. Nhà thầu và nguồn ngoài HRIS

Không phải mọi danh tính đều có employee record trong HRIS. Nhà thầu, đối tác, cộng tác viên hoặc danh tính máy có thể do hệ thống quản trị nhà cung cấp, quản lý dự án hay danh mục dịch vụ quản lý. Cần định nghĩa **nguồn sự thật theo loại danh tính**, người bảo trợ (*sponsor*) và ngày hết hạn bắt buộc khi thích hợp. Không tự tạo employee record giả để lấp thiếu nguồn chỉ nhằm làm cho quy trình cấp quyền hoạt động.

### 11.5. Sai thời điểm và cập nhật hồi tố

Một sự kiện Leaver nhập muộn phải được xử lý theo chính sách thu hồi phù hợp mức độ rủi ro và phải ghi nhận **độ trễ thực tế**; không được ghi lùi thời điểm kỹ thuật như thể đã khóa tài khoản trước đó. Đối với thay đổi nhập hồi tố, cần xác định quyền đã tồn tại trong khoảng sai và có cần điều tra truy cập trong khoảng đó hay không.

## 12. Bảo mật, quyền riêng tư và kiểm toán employee record

Employee record có thể chứa dữ liệu cá nhân nhạy cảm; vì vậy luồng HRIS → IAM cần **tối thiểu hóa dữ liệu**. IAM thường chỉ cần mã định danh ổn định, trạng thái làm việc, vai trò, đơn vị, ngày hiệu lực và những thuộc tính được chứng minh là cần cho quyết định truy cập.

Các thực hành cốt lõi:

- **Giới hạn trường và mục đích sử dụng:** không đẩy toàn bộ hồ sơ HR sang IdP, token SSO, message bus hoặc log.
- **Quyền truy cập tối thiểu cho connector:** tích hợp chỉ được đọc những trường cần thiết và cập nhật đúng hệ thống đích đã phê duyệt.
- **Bảo vệ khi truyền và lưu:** xác thực nguồn, mã hóa phù hợp, quản lý credential/secret, kiểm soát truy cập dữ liệu và quy trình thay khóa.
- **Phân tách trách nhiệm:** nhóm HR quản lý hồ sơ nhân sự; nhóm IAM quản lý ánh xạ và quyền; chủ tài nguyên duyệt quyền tài nguyên nhạy cảm.
- **Kiểm toán có căn cứ:** ghi nguồn, sự kiện, timestamp, phiên bản record, quyết định, người phê duyệt khi cần và trạng thái thực thi.
- **Giữ lại đúng thời hạn:** lưu lịch sử cần cho kiểm toán, điều tra hoặc nghĩa vụ hợp pháp theo chính sách tổ chức và pháp luật áp dụng; không giữ bản sao PII vô hạn vì tiện vận hành.
- **Kiểm soát truy cập log:** log đồng bộ HR có thể suy ra trạng thái nghỉ việc, phòng ban hoặc thông tin cá nhân; cần giới hạn người được xem.

Một bản ghi kiểm toán minh họa:

~~~text
source_event: hr-event-8231
subject_reference: iam-identity-482
decision: REVOKE_ROLE
role: sales-region-a-reader
reason: assignment_changed
effective_at: 2026-11-18T00:00:00+07:00
executed_at: 2026-11-18T00:00:08+07:00
target_system: reporting-app
result: CONFIRMED
~~~

Ví dụ sử dụng định danh tham chiếu và loại thay đổi thay vì đưa dữ liệu cá nhân không liên quan vào log.

## 13. Kiểm tra vận hành và chỉ số theo dõi

Để chứng minh employee record thực sự kiểm soát vòng đời IAM, cần theo dõi **cả dữ liệu đầu vào và quyền đầu ra**:

| Kiểm tra | Câu hỏi đánh giá |
| --- | --- |
| **Độ đầy đủ dữ liệu** | Các trường định danh, trạng thái, thời điểm hiệu lực, nguồn có đủ và hợp lệ không? |
| **Tính duy nhất của liên kết** | Có account hoặc identity nào liên kết nhầm, trùng hoặc không có owner không? |
| **Độ trễ nhập/xử lý sự kiện** | HR thay đổi lúc nào, IAM nhận lúc nào, quyền thực tế đổi lúc nào? |
| **Chênh lệch HR–IAM** | Có danh tính đã chấm dứt làm việc nhưng vẫn active do lỗi xử lý không? |
| **Chênh lệch IAM–ứng dụng** | Quyền mục tiêu và entitlement thực tế trên ứng dụng có khớp không? |
| **Tồn dư sau Mover** | Tài khoản còn quyền dự án/phòng ban cũ không có ngoại lệ hợp lệ không? |
| **Quyền của tài khoản dịch vụ** | Có workload owner nghỉ việc hoặc không còn đội vận hành chịu trách nhiệm không? |
| **Khả năng khôi phục lỗi** | Có retry, đối soát snapshot và xử lý manual cho các bản ghi lỗi không? |

Một số chỉ số có thể dùng: tỷ lệ employee record ánh xạ tới identity chính xác; số account mồ côi; số sự kiện Leaver quá hạn chưa xác nhận thu hồi; thời gian đến khi quyền cũ biến mất sau Mover; tỷ lệ đồng bộ lỗi; số quyền tồn dư không có căn cứ từ HR hoặc chủ tài nguyên. Ngưỡng chấp nhận cần được tổ chức quy định theo rủi ro, mức nhạy cảm và mức độ tự động hóa.

## 14. Tình huống thực hành: từ bản ghi HR đến thu hồi quyền

**Bối cảnh:** Bình hiện là nhân viên phân tích bán hàng, làm việc tại phòng Sales và có quyền xem dữ liệu khách hàng khu vực miền Bắc. HR thông báo Bình chuyển sang Finance vào ngày 18/11.

**Dữ liệu được xác nhận:**

| Trường | Trước 18/11 | Từ 18/11 |
| --- | --- | --- |
| `employmentStatus` | `active` | `active` |
| `departmentId` | `sales` | `finance` |
| `jobCode` | `SALES_ANALYST` | `FINANCE_ANALYST` |
| `managerWorkerId` | Quản lý Sales | Quản lý Finance |
| `effectiveFrom` | Phiên bản phân công cũ | 18/11, theo timezone đã quy định |

**Quy trình cần có:**

1. Nhận bản ghi đã duyệt từ HRIS và xác nhận `workerId` liên kết đúng identity của Bình.
2. Xác định chính sách cho vai trò mới; lấy các quyền hiện có từ IAM và hệ thống đích.
3. Thu hồi các nhóm, ACL, quyền dữ liệu khu vực miền Bắc không còn nhu cầu; xử lý quyền đang nằm ngoài IdP.
4. Cấp quyền Finance trong phạm vi chủ tài nguyên phê duyệt; không suy ra rằng Bình được xem mọi bảng dữ liệu tài chính.
5. Nếu cần bàn giao Sales một thời gian, lưu phê duyệt ngoại lệ và thời điểm hết hạn cụ thể.
6. Đối soát đăng nhập, nhóm, entitlement và truy cập API thực tế, kiểm tra token/phiên nếu việc thay đổi quyền phải có hiệu lực ngay.
7. Ghi lại thời điểm HR quyết định, thời điểm hiệu lực, thời điểm hệ thống đích xác nhận, và các lỗi hoặc ngoại lệ.

**Bài tập:** Giả sử IAM đã xóa Bình khỏi nhóm `sales-analysts`, nhưng Bình vẫn mở được file khách hàng cũ. Hãy chỉ ra ít nhất ba nguyên nhân có thể và cách xác minh.

**Gợi ý giải:** Quyền chia sẻ trực tiếp trong ứng dụng; nhóm khác có quyền kế thừa; role ứng dụng không được đồng bộ; token/phiên còn hiệu lực; lỗi cache hoặc lỗi provisioning. Cần đọc **quyền hiệu lực ở ứng dụng đích** và dấu vết cấp quyền, thay vì chỉ dựa trên employee record hay danh sách nhóm IdP.

## 15. Tổng kết

**Employee record** là nguồn dữ liệu nhân sự quan trọng để IAM hiểu **ai đang có quan hệ làm việc hợp lệ, ở vai trò nào và vào thời điểm nào**. Giá trị lớn nhất của nó nằm ở định danh ổn định, nguồn có thẩm quyền, trạng thái công việc, phân công và mốc hiệu lực được xác nhận. Kết nối employee record với **Joiner–Mover–Leaver** giúp tạo tài khoản đúng người, đánh giá lại quyền khi thay đổi vai trò và thu hồi quyền khi quan hệ làm việc chấm dứt.

Một triển khai hiệu quả cần phối hợp **HRIS, IAM governance, IdP, SSO, SCIM, RBAC/ABAC và hệ thống tài nguyên**, đồng thời xử lý account liên kết, sự kiện trùng/trễ, ngoại lệ, tài khoản dịch vụ, quyền riêng tư và kiểm toán. Thành công phải được chứng minh bằng **quyền thực tế tại hệ thống đích** và khả năng phát hiện, loại bỏ truy cập tồn dư, không chỉ bằng trạng thái `active` hoặc `terminated` trên hồ sơ HR.
