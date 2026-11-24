# Manager trong nguồn dữ liệu nhân sự và quản lý vòng đời danh tính IAM

> **Chương: Nguồn dữ liệu nhân sự.** Trong hệ thống Identity and Access Management (IAM), **Manager** thường biểu thị người quản lý trực tiếp của một nhân sự, được xác định từ dữ liệu tổ chức có thẩm quyền như HRIS/HCM. Quan hệ này được dùng để định tuyến yêu cầu cấp quyền, xác nhận nhu cầu công việc, rà soát quyền truy cập và xử lý các sự kiện **Joiner–Mover–Leaver**. Manager cũng có thể là một vai trò nghiệp vụ trong ứng dụng, nhưng hai ý nghĩa đó cần được phân biệt rõ.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của **Manager** như một quan hệ báo cáo trực tiếp trong dữ liệu nhân sự, khác với vai trò quản trị hay quyền phê duyệt.
2. Mô tả cách xác định, liên kết và cập nhật quan hệ **employee → manager** giữa HR, IdP, hệ thống quản trị quyền và ứng dụng.
3. Thiết kế luồng sử dụng Manager trong **Joiner, Mover, Leaver**, bao gồm các trường hợp quản lý đổi vị trí, nghỉ việc hoặc ủy quyền.
4. Hiểu cách biểu diễn quan hệ quản lý trong **SCIM Enterprise User extension** và giới hạn của IdP/SSO, RBAC/ABAC đối với dữ liệu Manager.
5. Nhận diện lỗi ánh xạ, dữ liệu cũ, vòng lặp quản lý, phê duyệt sai người và quyền truy cập tồn dư; xây dựng bước đối soát và kiểm toán tương ứng.

## 1. Manager trong IAM là gì?

Trong hồ sơ nhân sự, **manager** thường là tham chiếu tới **người quản lý trực tiếp** của một nhân viên hoặc nhà thầu. Nó có thể được lưu bằng mã nhân sự của người quản lý, một định danh của quan hệ quản lý hoặc một cấu trúc phức hợp tùy sản phẩm HR.

Ví dụ:

- Nhân viên **An** (employeeId = EMP-2001) báo cáo cho **Bình** (employeeId = EMP-1004).
- HR có thể lưu quan hệ này bằng **managerEmployeeId = EMP-1004**, rồi các hệ thống IAM ánh xạ EMP-1004 sang identityId/User ID tương ứng.
- Khi An gửi yêu cầu truy cập kho dữ liệu của dự án, luồng phê duyệt có thể định tuyến bước xác nhận nhu cầu nghiệp vụ tới Bình nếu chính sách yêu cầu.
- Khi An chuyển nhóm sang đội do **Chi** quản lý, HR cập nhật quan hệ manager; IAM phải biết cả **người phê duyệt mới** lẫn những quyền đang tồn tại cần rà soát.

Từ “Manager” có ít nhất ba cách sử dụng:

| Ý nghĩa | Ví dụ | Vì sao cần phân biệt |
| --- | --- | --- |
| **Manager relationship** — quan hệ quản lý | An có managerEmployeeId trỏ đến Bình. | Là thuộc tính tổ chức của An; **không tự trao quyền** cho Bình trong mọi hệ thống. |
| **Manager role** — vai trò quản lý | Một User có role TeamManager trong CRM. | Là tập quyền do ứng dụng hoặc RBAC gán; có thể không trùng với dữ liệu HR. |
| **Approval authority** — thẩm quyền phê duyệt | Người có quyền duyệt truy cập sản xuất là chủ sở hữu hệ thống hoặc người được ủy quyền. | Phải do chính sách xác định; **manager trực tiếp không mặc nhiên là người đủ thẩm quyền**. |

**Nguyên tắc cốt lõi:** quan hệ “An báo cáo cho Bình” là **dữ kiện tổ chức**, còn việc “Bình được đọc dữ liệu của An” hoặc “Bình có quyền cấp đặc quyền cho An” là **quyết định phân quyền/phê duyệt** độc lập cần có chính sách rõ ràng.

## 2. Manager đến từ nguồn nào?

Đối với nhân viên, một hệ thống HRIS/HCM hoặc hệ thống quản lý tổ chức thường là **source of truth** (nguồn có thẩm quyền) cho tuyến báo cáo trực tiếp. Tuy nhiên, không phải mọi loại danh tính đều dùng cùng một nguồn:

| Loại danh tính | Nguồn Manager/owner có thể có | Điểm cần kiểm tra |
| --- | --- | --- |
| Nhân viên chính thức | HRIS/HCM và sơ đồ tổ chức. | Ngày hiệu lực, nhân viên chuyển nhóm, người quản lý đang hoạt động. |
| Nhà thầu | Hệ thống quản lý nhà thầu, HR hoặc đầu mối bảo trợ (sponsor). | Không nhầm sponsor/contract owner với line manager nếu hai vai trò khác nhau. |
| Nhân viên dự án ma trận | HR manager và project manager riêng. | Ai có thẩm quyền duyệt yêu cầu thuộc từng dự án? |
| Đối tác/khách hàng | Chủ sở hữu quan hệ hợp đồng hoặc administrator của tổ chức đối tác. | Không suy ra có một nhân viên HR làm manager trực tiếp. |
| Tài khoản dịch vụ/workload | Owner nghiệp vụ, owner kỹ thuật hoặc nhóm ứng dụng. | Không tạo quan hệ manager giả cho tài khoản máy; dùng owner rõ ràng và quy trình thu hồi riêng. |

Trong IAM nên xác định **nguồn nào có quyền cập nhật thuộc tính Manager**. Không cho một ứng dụng ít tin cậy sửa dữ liệu Manager rồi tự động biến thay đổi ấy thành quyền phê duyệt có hiệu lực toàn doanh nghiệp.

### Mã định danh nào nên dùng?

Để ánh xạ manager an toàn, cần phân biệt:

- **employeeId / personId:** mã cá nhân do hệ thống nhân sự cấp, sử dụng trong phạm vi và chính sách của HR.
- **identityId:** mã danh tính trong lớp IAM/IGA, giúp liên kết tài khoản ở nhiều hệ thống.
- **id / subject của IdP:** định danh User tại một IdP cụ thể; có thể khác employeeId.
- **applicationUserId:** mã User tại CRM, công cụ mã nguồn hoặc nền tảng SaaS.
- **email/displayName:** thuộc tính dễ thay đổi hoặc trùng; không nên là khóa đối sánh duy nhất.

Ví dụ, trường HR **managerEmployeeId = EMP-1004** không thể tùy tiện ghi nguyên giá trị đó vào trường **manager User ID** của tất cả ứng dụng. Từng hệ thống đích có namespace riêng, nên luồng đồng bộ phải **resolve** danh tính người quản lý rồi chuyển thành mã User phù hợp của đích.

## 3. Mô hình quan hệ employee → manager

Một quan hệ quản lý có thể được biểu diễn là cạnh có hướng giữa hai danh tính:

~~~mermaid
flowchart TD
    HR["HR: người quản lý có thẩm quyền<br/>EMP-1004 — Bình"] --> IAM["IAM: identityId = ID-BINH"]
    E["HR: nhân viên EMP-2001 — An<br/>managerEmployeeId = EMP-1004"] --> R["Resolve managerEmployeeId"]
    IAM --> R
    R --> P["IAM: quan hệ An → Bình<br/>effectiveFrom, source, version"]
    P --> W["Workflow phê duyệt<br/>kiểm tra chính sách"]
    P --> SCIM["Provisioning đến IdP/ứng dụng"]
    SCIM --> T["Tài khoản đích và trường manager"]
    T --> V["Đối soát / kiểm toán"]
    W --> V
~~~

Một mô hình nội bộ minh họa có thể như sau. **Đây không phải schema bắt buộc của sản phẩm IAM hay SCIM**:

~~~json
{
  "personId": "EMP-2001",
  "identityId": "ID-AN",
  "department": "CustomerSupport",
  "status": "ACTIVE",
  "reportingLine": {
    "managerPersonId": "EMP-1004",
    "managerIdentityId": "ID-BINH",
    "relationType": "LINE_MANAGER",
    "source": "HRIS",
    "effectiveFrom": "2026-12-01",
    "sourceVersion": 184
  }
}
~~~

Các thuộc tính trong ví dụ phục vụ những mục đích khác nhau:

| Thuộc tính | Tác dụng |
| --- | --- |
| managerPersonId | Tham chiếu tới người quản lý trong HR, làm đầu vào đối sánh. |
| managerIdentityId | Liên kết tới danh tính được IAM nhận biết, dùng cho workflow và xuất sang hệ thống đích. |
| relationType | Phân biệt quản lý trực tiếp, quản lý dự án hoặc người bảo trợ nếu mô hình hỗ trợ nhiều tuyến. |
| source | Ghi nhận nguồn dữ liệu có thẩm quyền cho quan hệ. |
| effectiveFrom | Thời điểm quan hệ bắt đầu có hiệu lực; tránh cập nhật quá sớm khi thay đổi đã lên lịch. |
| sourceVersion | Hỗ trợ xác định bản ghi mới hơn, chống ghi đè bởi sự kiện cũ đến trễ. |

Đối với sơ đồ tổ chức theo tuyến quản lý, cần kiểm tra **tính toàn vẹn tham chiếu**: manager có tồn tại không, có thuộc namespace hợp lệ không, có tự trỏ vào chính mình không và có tạo chu trình bất hợp lý không. Tùy tổ chức, lãnh đạo cấp cao có thể không có manager, hoặc có quan hệ báo cáo đặc thù; trạng thái **manager = null** có thể hợp lệ theo chính sách, không nhất thiết là lỗi.

### Kiểm tra chu trình trong đồ thị quản lý

Giả sử An → Bình, Bình → Chi và Chi → An. Một hệ thống dùng chuỗi quản lý để chuyển cấp duyệt có thể rơi vào vòng lặp.

Các biện pháp:

1. Chặn liên kết tự tham chiếu nếu chính sách không cho phép.
2. Phát hiện chu trình trước khi sử dụng tuyến báo cáo làm đường phê duyệt.
3. Giới hạn độ sâu truy vấn; thiếu người quản lý hoặc có chu trình thì chuyển tới hàng chờ xử lý thủ công được kiểm soát.
4. Không tự suy đoán manager từ họ tên hoặc email khi không resolve được tham chiếu.

## 4. Dùng Manager trong vòng đời Joiner–Mover–Leaver

### Joiner: người quản lý xác nhận nhu cầu truy cập

Khi một nhân viên mới gia nhập:

1. HR xác minh hồ sơ, ngày vào làm, bộ phận, chức danh và **manager**.
2. IAM tạo hoặc liên kết danh tính của nhân viên với mã HR ổn định.
3. IAM xác minh manager được chỉ định có danh tính hợp lệ, đang hoạt động và đủ điều kiện nhận yêu cầu theo chính sách.
4. Quyền nền được tính theo vai trò/bộ phận; các quyền nhạy cảm cần thêm chủ sở hữu tài nguyên, bảo mật hoặc người có thẩm quyền phê duyệt tùy quy định.
5. Sau khi phê duyệt, provisioning tạo/cập nhật tài khoản và quyền ở IdP, ứng dụng qua SCIM hoặc connector.
6. IAM kiểm tra quyền thực tế tại đích, lưu bằng chứng yêu cầu, người duyệt, thời điểm và kết quả.

**Ví dụ:** An gia nhập đội hỗ trợ. Bình là line manager trong HR, có thể xác nhận An cần quyền SupportAgent. Nhưng quyền quản trị CRM vẫn cần hệ thống chính sách hoặc owner CRM phê duyệt; việc Bình là manager không đủ để vượt qua kiểm soát đặc quyền.

### Mover: đổi người quản lý chưa chắc đổi mọi quyền, nhưng phải xem lại

Sự kiện Mover có thể xuất hiện khi nhân viên:

- Đổi line manager mà không đổi vai trò công việc.
- Chuyển phòng ban, chức danh, dự án hoặc địa điểm làm việc.
- Có thêm project manager trong mô hình báo cáo ma trận.
- Tạm thời được giao người quản lý thay thế trong thời gian bàn giao.

IAM phải xem thay đổi Manager **có tác động tới chính sách nào**. Ví dụ, một chính sách RBAC theo bộ phận không cần thay quyền nếu chỉ đổi manager trong cùng đội; nhưng nhóm quyền “nhân viên dưới quyền của Bình” có thể phải thay đổi ngay. Với ABAC, nếu chính sách xét quan hệ quản lý, phạm vi dữ liệu của cả người quản lý cũ và mới cần được tính lại.

Quy trình Mover nên:

1. Nhận sự kiện và thời điểm hiệu lực từ nguồn HR.
2. Ánh xạ manager mới và kiểm tra tính hợp lệ.
3. Tính lại quyền mong muốn của nhân viên và quyền được suy ra từ quan hệ cấp dưới của manager.
4. Thu hồi những quyền/đường xem dữ liệu không còn hợp lệ; cấp quyền mới sau phê duyệt khi cần.
5. **Chuyển các yêu cầu phê duyệt đang chờ** tới người có thẩm quyền theo chính sách, bảo toàn lịch sử yêu cầu; không tự thay người duyệt đã ra quyết định.
6. Đối soát quyền và thuộc tính manager tại các hệ thống đích.

Đây là nơi dễ phát sinh **quyền truy cập tồn dư**: manager cũ có thể tiếp tục xem dữ liệu nhân sự hoặc phê duyệt yêu cầu của nhân viên đã chuyển đội nếu hệ thống sử dụng quan hệ quản lý được cache quá lâu.

### Leaver: hai tình huống khác nhau

**Trường hợp A — Nhân viên nghỉ việc:** IAM cần thu hồi tài khoản, nhóm, quyền, phiên và credential của nhân viên theo quy trình Leaver. Manager thường nhận thông tin hoặc chịu trách nhiệm xác nhận bàn giao, nhưng không thay thế nguồn sự kiện Leaver có thẩm quyền.

**Trường hợp B — Chính người quản lý nghỉ việc:** IAM phải xử lý đồng thời:

- Thu hồi quyền và tài khoản của người quản lý theo thời điểm hiệu lực.
- Xác định người đang báo cáo cho manager đó để cập nhật tuyến báo cáo theo nguồn HR.
- Chuyển hoặc dừng các yêu cầu phê duyệt đang treo, tránh rơi vào hàng đợi của tài khoản đã vô hiệu hóa.
- Thu hồi các quyền suy ra từ quan hệ quản lý cũ, gồm quyền xem dữ liệu cấp dưới nếu có.
- Kiểm tra owner của quyền, dự án, ứng dụng hoặc tài khoản dịch vụ mà người quản lý sắp rời đi chịu trách nhiệm.

**Không trì hoãn việc khóa quyền của người nghỉ việc chỉ vì dữ liệu manager mới chưa sẵn sàng.** Có thể đưa quy trình phê duyệt về hàng chờ xử lý khẩn cấp hoặc escalation theo chính sách trong khi HR bổ sung tuyến quản lý.

### Ma trận sự kiện minh họa

| Sự kiện | Thay đổi dữ liệu Manager | Tác động cần đánh giá | Bước xác minh |
| --- | --- | --- | --- |
| An bắt đầu làm việc | Tạo liên kết An → Bình. | Định tuyến yêu cầu quyền mới; áp chính sách Joiner. | Manager resolve đúng, quyền đầu vào đúng. |
| An đổi sang đội Chi | An → Chi thay cho An → Bình. | Thu hồi quyền theo đội cũ, cập nhật người duyệt và quyền xem cấp dưới. | Không còn quyền dựa trên quan hệ cũ. |
| Bình nghỉ việc | Quan hệ cấp dưới của Bình cần được HR cập nhật. | Khóa tài khoản Bình, định tuyến lại phê duyệt, xử lý owner còn treo. | Không có approval queue phụ thuộc tài khoản đã khóa. |
| Chi đi công tác và ủy quyền cho Dũng | Giữ quan hệ line manager theo HR; bổ sung ủy quyền có hạn. | Dũng chỉ nhận quyền duyệt loại yêu cầu được ủy quyền trong thời gian cho phép. | Có phê duyệt, hạn kết thúc, nhật ký và thu hồi. |

## 5. Manager trong IdP, SSO và SCIM

Manager có thể xuất hiện dưới dạng một thuộc tính hồ sơ User, nhưng việc có trường đó **không tự tạo quyền**.

### IdP và SSO

**IdP (Identity Provider)** có thể lưu hoặc đồng bộ thuộc tính Manager từ HR. SSO dùng xác thực để người dùng truy cập ứng dụng liên kết, thường qua OIDC hoặc SAML. Một số ứng dụng có thể nhận thuộc tính tổ chức qua claim hoặc provisioning theo cấu hình.

Các điểm cần nhớ:

- **Manager không phải claim chuẩn bắt buộc trong mọi ID token/OIDC hay SAML assertion.**
- Không tin giá trị Manager từ một token hoặc payload chưa kiểm tra nguồn phát hành, chữ ký, audience, thời hạn và độ tin cậy của thuộc tính.
- Nếu ứng dụng dùng Manager để phân quyền trên dữ liệu hiện tại, cần xem xét **độ mới của thuộc tính**: thông tin gắn trong phiên hoặc token cũ có thể không phản ánh thay đổi Mover vừa xảy ra.
- Trường Manager trong IdP có thể là bản sao của HR; cần xác định rõ ai là nguồn có thẩm quyền khi dữ liệu không khớp.

### SCIM Enterprise User extension

**SCIM 2.0** định nghĩa tài nguyên User và cơ chế provisioning. Quan hệ Manager được hỗ trợ trong **SCIM Enterprise User extension**, với URI schema:

~~~text
urn:ietf:params:scim:schemas:extension:enterprise:2.0:User
~~~

Ví dụ biểu diễn rút gọn của User An tại một SCIM service provider:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "id": "scim-an-33",
  "userName": "an@example.org",
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "employeeNumber": "EMP-2001",
    "department": "CustomerSupport",
    "manager": {
      "value": "scim-binh-15",
      "$ref": "https://id.example.org/scim/v2/Users/scim-binh-15",
      "displayName": "Binh"
    }
  }
}
~~~

Trong đó:

- **manager.value** tham chiếu tới **id của User resource đại diện cho manager tại SCIM service provider này**, không phải mặc nhiên là employeeId ở HR.
- **manager.$ref** là tham chiếu tới tài nguyên User của manager khi được cung cấp.
- **manager.displayName** thuận tiện hiển thị, không nên dùng để xác định danh tính duy nhất.
- Các thuộc tính mở rộng như **employeeNumber**, **department**, **manager** thuộc schema Enterprise User khi ứng dụng hỗ trợ và triển khai chúng.

Đây là ví dụ khái niệm về nội dung tài nguyên, **không chứng minh mọi nhà cung cấp hỗ trợ ghi, cập nhật hoặc đọc các trường như nhau**. Cần kiểm tra schema và khả năng xử lý của hệ thống đích. Khi manager chưa được tạo tại đích, quy trình provisioning cần xác định thứ tự tạo tài khoản, cơ chế retry hoặc trạng thái chờ; không tự gửi mã HR thay cho SCIM User ID.

### Quy trình đồng bộ quan hệ Manager

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IGA as IAM / IGA
    participant IDP as IdP
    participant APP as Ứng dụng SCIM
    HR->>IGA: Mover: An đổi manager từ Bình sang Chi
    IGA->>IGA: Xác minh hiệu lực và resolve identity Chi
    IGA->>IDP: Đồng bộ thuộc tính quan hệ theo chính sách
    IGA->>APP: Resolve ứng dụng User ID của Chi
    IGA->>APP: Cập nhật manager tham chiếu tới Chi
    APP-->>IGA: Trả kết quả cập nhật
    IGA->>APP: Đọc lại User An và quan hệ manager
    APP-->>IGA: Trạng thái thực tế tại đích
    IGA->>IGA: So sánh desired vs observed; audit
~~~

Sơ đồ là một luồng triển khai minh họa. Thực tế, dữ liệu có thể đi qua IdP, HR connector, provisioning engine hoặc IGA theo đường khác; bước đối soát cuối cùng vẫn cần có.

## 6. Manager tham gia phê duyệt quyền như thế nào?

Một mô hình phê duyệt thường có nhiều cấp trách nhiệm:

| Người/thành phần | Trách nhiệm ví dụ | Không nên mặc định |
| --- | --- | --- |
| **Line manager** | Xác nhận nhu cầu công việc, phạm vi vai trò, hạn dùng quyền. | Có quyền tự duyệt mọi loại truy cập hoặc xem mọi dữ liệu cấp dưới. |
| **Resource owner** | Xác nhận quyền đối với ứng dụng, hệ thống hay dữ liệu cụ thể. | Mọi quyền đều chỉ cần xác nhận của line manager. |
| **Security / IAM / PAM policy** | Kiểm tra rủi ro, SoD, đặc quyền và yêu cầu bổ sung. | Có thể bị bỏ qua vì manager đã bấm duyệt. |
| **Delegated approver** | Thực hiện bước duyệt đã được ủy quyền hợp lệ. | Được ủy quyền vĩnh viễn và tự nhận mọi quyền của manager. |
| **IAM workflow** | Xác minh chủ thể, điều kiện, thời điểm, phê duyệt và kết quả thực thi. | Tin một trường manager bất kỳ mà không kiểm chứng. |

### Ví dụ: yêu cầu quyền đọc báo cáo

An xin vai trò **SalesReportReader** trong 30 ngày. Chính sách nội bộ giả định yêu cầu:

1. Manager trực tiếp xác nhận An có nhiệm vụ phân tích doanh số.
2. Chủ sở hữu dữ liệu xác nhận phạm vi chi nhánh và loại báo cáo.
3. IAM kiểm tra xung đột vai trò, thời hạn quyền và trạng thái đang hoạt động.
4. Sau khi đủ điều kiện, cấp quyền có hạn và xác minh tại hệ thống báo cáo.
5. Tới hạn, tự động thu hồi, đối soát và lưu bằng chứng.

Điểm đáng chú ý: **Manager xác nhận lý do công việc**, còn quyền truy cập thật sự phụ thuộc thêm resource owner, kiểm soát chính sách và hệ thống đích.

### Quy tắc phân quyền theo quan hệ quản lý

Một ứng dụng quản trị nhân sự đôi khi cho phép manager xem hồ sơ của cấp dưới. Ví dụ chính sách **pseudocode**:

~~~text
ALLOW "employee.profile.read" KHI
    requester.active = true
    AND target.active = true
    AND reportingRelationship.isCurrent = true
    AND reportingRelationship.managerIdentityId = requester.identityId
    AND requestedField thuộc danh_sách_trường_được_phép
    AND requester.session đáp ứng yêu_cầu_xác_thực
ELSE DENY
~~~

Trong sản phẩm thực tế, có thể cần thêm giới hạn tenant, vai trò, loại hợp đồng, yêu cầu pháp lý và quyền riêng tư. Quan hệ cấp dưới cũng có thể là **trực tiếp** hoặc **gián tiếp**; chính sách phải nói rõ được phép tới cấp nào. Không suy ra toàn bộ chuỗi cấp dưới đều được đọc nếu chỉ có quyền xem nhân viên báo cáo trực tiếp.

**Tránh tự phê duyệt (self-approval):** nếu An là người yêu cầu, các điều kiện phải ngăn An trở thành người duyệt chính yêu cầu đó qua quan hệ manager sai, quyền ủy quyền, một tài khoản thứ hai hoặc chu trình workflow. Đối với quyền nhạy cảm cần SoD và kiểm tra người duyệt độc lập.

## 7. Xử lý các tình huống dữ liệu khó

### 7.1. Manager chưa có tài khoản tại ứng dụng đích

HR đã xác nhận người quản lý là Chi, nhưng Chi chưa có User tại ứng dụng nhận SCIM. Không nên ghi giá trị tùy đoán hoặc gán nhầm theo email. Provisioning có thể phải tạo User Chi trước, đưa quan hệ của An vào trạng thái chờ, retry rồi đọc lại sau khi có ánh xạ. Nếu ứng dụng không hỗ trợ manager attribute, giữ quan hệ ở nguồn IAM phù hợp thay vì cưỡng ép schema không tồn tại.

### 7.2. Manager nghỉ việc hoặc bị khóa

Phê duyệt mới không được gửi vào hộp thư hoặc tài khoản đã mất quyền truy cập. Workflow cần cập nhật tuyến báo cáo từ nguồn hợp lệ hoặc chuyển sang tuyến escalation đã cấu hình. Vẫn phải khóa tài khoản người nghỉ việc đúng thời hạn; đừng trì hoãn thu hồi chỉ để đợi đổi manager trong HR.

### 7.3. Manager thay đổi trong khi yêu cầu đang chờ

Nếu Bình đã nhận yêu cầu truy cập của An nhưng An được chuyển sang Chi, hãy áp dụng chính sách về hiệu lực và phân công: yêu cầu đang chờ có thể phải được chuyển cho Chi hoặc một người duyệt thay thế. Không ghi đè nhật ký phê duyệt đã diễn ra; nếu người duyệt trước đó không còn hợp lệ, xác định có cần duyệt lại không.

### 7.4. Nhiều Manager trong mô hình ma trận

An có line manager Bình, project manager Chi và sponsor Dũng. Không gộp tất cả thành một trường manager không rõ nghĩa. Dùng loại quan hệ và phạm vi trách nhiệm rõ ràng; quy định ai duyệt loại quyền nào.

### 7.5. Manager tạm quyền hoặc ủy quyền

Khi Bình nghỉ phép, Dũng được ủy quyền duyệt yêu cầu trong một khoảng xác định. **Ủy quyền phê duyệt** nên là một bản ghi độc lập với quan hệ HR line manager: có người ủy quyền, người nhận ủy quyền, phạm vi yêu cầu, thời gian hiệu lực, cơ chế thu hồi và lịch sử sử dụng.

### 7.6. Dữ liệu HR đến trễ hoặc sai thứ tự

Sự kiện “An → Chi” được xử lý trước, rồi một sự kiện cũ “An → Bình” mới đến. Nếu không kiểm tra phiên bản hoặc thời điểm hiệu lực, hệ thống sẽ phục hồi quan hệ sai. Có thể dùng version/sequence của nguồn, idempotency key, lịch sử hiệu lực và bước đối soát snapshot HR. Không coi thời điểm webhook được nhận là thứ tự nghiệp vụ tuyệt đối.

### 7.7. Manager trỏ đến chính mình, thiếu hoặc tạo vòng lặp

Các trường hợp này có thể gây lỗi suy luận cấp quản lý hoặc luồng phê duyệt. Cần kiểm tra tính toàn vẹn tham chiếu, phát hiện chu trình, xác định ngoại lệ hợp lệ cho vị trí cao nhất và dùng tuyến xử lý thủ công được kiểm soát khi không thể xác thực manager.

## 8. Thiết kế đồng bộ và kiểm toán quan hệ Manager

Một pipeline dữ liệu Manager nên có các giai đoạn:

**Bước 1 — Ingest:** nhận dữ liệu và sự kiện từ nguồn có thẩm quyền; xác định danh tính đối tượng, manager, ngày hiệu lực và mã phiên bản.

**Bước 2 — Validate:** kiểm tra cú pháp, định danh, tenant, tình trạng chủ thể, quan hệ hợp lệ và không tạo chu trình ngoài chính sách.

**Bước 3 — Resolve:** ánh xạ manager từ HR personId sang IAM identityId và applicationUserId của đích; quản lý quan hệ chưa resolve được như lỗi/đang chờ có trạng thái.

**Bước 4 — Evaluate:** tính lại trạng thái mong muốn của thuộc tính Manager, tuyến phê duyệt và các quyền phụ thuộc quan hệ. Đánh giá SoD, thời hạn và ủy quyền.

**Bước 5 — Provision:** cập nhật IdP, SCIM/API hoặc hệ thống quản lý quyền; hỗ trợ retry có kiểm soát, idempotency và theo dõi lỗi theo từng đích.

**Bước 6 — Reconcile:** đọc lại trạng thái của hệ thống đích, so sánh **desired state** với **observed state**, xử lý sai lệch có chủ sở hữu.

**Bước 7 — Audit:** lưu dấu ai/cái gì thay đổi Manager, giá trị trước/sau, nguồn, thời điểm hiệu lực, lý do, người duyệt, những quyền/tuyến phê duyệt bị ảnh hưởng và kết quả áp dụng.

### Ví dụ record kiểm toán

~~~json
{
  "eventId": "evt-7952",
  "eventType": "MANAGER_CHANGED",
  "subjectIdentityId": "ID-AN",
  "oldManagerIdentityId": "ID-BINH",
  "newManagerIdentityId": "ID-CHI",
  "source": "HRIS",
  "effectiveAt": "2026-12-01T00:00:00+07:00",
  "sourceVersion": 184,
  "provisioningState": "RECONCILED",
  "actorType": "HR_SOURCE",
  "correlationId": "corr-2290"
}
~~~

Đây là bản ghi minh họa, không phải một chuẩn event chung. Trong hệ thống thật cần giới hạn dữ liệu cá nhân được ghi, phân quyền đọc log và tránh đưa mật khẩu, private key hoặc token nguyên vẹn vào nhật ký.

### Các chỉ số giúp phát hiện lỗi vận hành

| Chỉ số | Giá trị kiểm soát |
| --- | --- |
| **Tỷ lệ manager reference không resolve được** | Phát hiện HR không đồng nhất hoặc user manager thiếu ở đích. |
| **Số quan hệ manager trỏ tới danh tính không hoạt động** | Cảnh báo tuyến báo cáo/approval lỗi thời. |
| **Độ trễ cập nhật quan hệ sau Mover** | Đo rủi ro manager cũ còn quyền xem hoặc duyệt. |
| **Số phê duyệt đang chờ ở manager đã nghỉ việc** | Phát hiện tắc nghẽn và luồng duyệt có rủi ro. |
| **Số bản ghi ủy quyền quá hạn còn hiệu lực** | Phát hiện ngoại lệ tạm thời chưa được thu hồi. |
| **Tỷ lệ manager giữa HR, IAM và ứng dụng đích không khớp** | Đánh giá hiệu quả provisioning và reconciliation. |

Không tự đặt một ngưỡng số học áp dụng cho mọi tổ chức; các ngưỡng cảnh báo và thời gian xử lý cần dựa trên mức nhạy cảm quyền, rủi ro và cam kết vận hành cụ thể.

## 9. Tình huống thực hành

### Tình huống 1 — Mover nhưng manager cũ vẫn duyệt

An chuyển từ đội Bình sang đội Chi. HR đã cập nhật đúng, nhưng workflow IAM lấy trường manager từ token phát hành trước Mover. Bình tiếp tục được chỉ định duyệt quyền tài chính của An.

**Câu hỏi:** Vấn đề nằm ở đâu và nên xử lý thế nào?

**Gợi ý:** Hệ thống dùng **quan hệ quản lý lỗi thời** để quyết định người duyệt. Cần dùng nguồn dữ liệu manager đủ tin cậy và đủ mới tại thời điểm đánh giá, cập nhật hoặc vô hiệu hóa cache, định tuyến lại yêu cầu đang chờ theo chính sách và ghi nhận sự thay đổi. Với quyền nhạy cảm, xác minh vai trò của resource owner và yêu cầu phê duyệt bổ sung.

### Tình huống 2 — SCIM trả lỗi vì chưa có manager User

Ứng dụng SaaS nhận yêu cầu cập nhật manager.value = scim-chi-22, nhưng User Chi chưa tồn tại trong ứng dụng.

**Câu hỏi:** Có nên thay manager bằng địa chỉ email của Chi để tránh lỗi không?

**Gợi ý:** Không tự thay định danh. Xác minh mapping HR → IAM → SCIM User ID, thứ tự provisioning và tính năng hỗ trợ của ứng dụng. Nếu manager resource chưa có, tạo hoặc đồng bộ khi được phép, sau đó retry có kiểm soát; giữ trạng thái pending và cảnh báo nếu không thể hoàn tất.

### Tình huống 3 — Quản lý rời công ty

Bình nghỉ việc ngay hôm nay. IAM đã khóa tài khoản Bình nhưng mười yêu cầu cấp quyền vẫn nằm trong hàng đợi chờ Bình duyệt. Một số nhân viên cấp dưới chưa có manager mới ở HR.

**Câu hỏi:** Có nên mở lại tài khoản Bình để duyệt hết yêu cầu?

**Gợi ý:** Không. Giữ thu hồi Leaver, tìm tuyến escalation/delegation hợp lệ cho các yêu cầu, đánh dấu những trường hợp thiếu manager để xử lý thủ công có kiểm soát. HR cập nhật tuyến báo cáo; IAM đối soát lại quan hệ và phê duyệt, bảo đảm không ai tự cấp quyền vượt chính sách.

### Tình huống 4 — Một nhân viên có hai người quản lý

An thuộc phòng kỹ thuật dưới quyền Bình nhưng làm dự án tài chính dưới sự điều phối của Chi. An xin quyền đọc dữ liệu tài chính của dự án.

**Câu hỏi:** Chỉ cần trường manager trong HR có đủ để xác định người phê duyệt không?

**Gợi ý:** Chưa chắc. Cần phân biệt line manager với project manager và resource owner. Chính sách có thể yêu cầu Bình xác nhận trách nhiệm công việc, Chi xác nhận nhu cầu dự án và chủ sở hữu dữ liệu phê duyệt phạm vi dữ liệu; quyền được cấp vẫn phải có thời hạn và được đối soát.

## 10. Câu hỏi tự kiểm tra

**1. Manager trong HR có đồng nghĩa với role Admin trong IAM không?**  
Không. Manager là quan hệ tổ chức, còn Admin là quyền hoặc vai trò kỹ thuật; mọi quyền được cấp phải dựa trên chính sách.

**2. Vì sao không nên lưu manager bằng displayName hoặc email làm khóa liên kết duy nhất?**  
Tên có thể trùng; email có thể đổi hoặc tái sử dụng. Cần định danh ổn định theo nguồn và mapping tới namespace của từng hệ thống.

**3. Thuộc tính manager.value trong SCIM Enterprise User thường tham chiếu tới đối tượng nào?**  
Nó tham chiếu tới định danh của User resource đại diện cho manager tại SCIM service provider, không mặc nhiên là employeeId ở HR.

**4. Khi manager đổi sau một sự kiện Mover, phải rà soát quyền của ai?**  
Cần xét quyền của nhân viên, quyền và phạm vi phụ thuộc quan hệ của manager cũ và mới, các yêu cầu phê duyệt đang chờ, phiên/cache và các ứng dụng đích liên quan.

**5. Nếu manager chưa xác định được, có nên tự động cho phép một quyền đặc quyền để tránh gián đoạn?**  
Không. Chính sách nên từ chối hoặc đưa sang tuyến phê duyệt ngoại lệ được kiểm soát; không suy đoán người duyệt hay bỏ qua ràng buộc.

## Ghi nhớ

- **Manager** trong nguồn dữ liệu nhân sự là quan hệ báo cáo có nguồn, định danh, thời điểm hiệu lực và vòng đời; bản thân quan hệ không tự trao quyền quản trị.
- Với IAM, cần **resolve manager theo định danh ổn định**, kiểm tra tham chiếu và đồng bộ quan hệ sang IdP/SCIM/ứng dụng đúng namespace.
- **Joiner** xác nhận tuyến quản lý và nhu cầu cấp quyền; **Mover** cập nhật quan hệ và quyền phụ thuộc; **Leaver** xử lý cả người rời đi, người duyệt đang treo và quyền truy cập còn tồn dư.
- **RBAC/ABAC, SoD, resource owner và chính sách phê duyệt** quyết định thẩm quyền thật sự; manager trực tiếp không mặc nhiên được tự duyệt mọi truy cập hoặc xem toàn bộ dữ liệu cấp dưới.
- Kiểm soát **độ mới dữ liệu, thứ tự sự kiện, ủy quyền có hạn, đối soát và kiểm toán** giúp giữ đúng tuyến phê duyệt và giảm rủi ro quyền tồn dư khi tổ chức thay đổi.
