# Thay đổi mức quyền trong Mover lifecycle của IAM

> **Chương:** Mover lifecycle  
> **Bài:** Thay đổi mức quyền  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Bối cảnh:** Quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, kết nối Identity Provider (IdP), SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Tại sao thay đổi mức quyền là một bài toán riêng?

Một nhân viên không nhất thiết phải đổi phòng ban mới phát sinh sự kiện **Mover**. Quyền truy cập có thể cần tăng, giảm hoặc thay đổi phạm vi ngay trong cùng một vị trí: nhân viên được giao phê duyệt khoản chi lớn hơn, trưởng nhóm hết nhiệm kỳ, kỹ sư được cấp quyền quản trị tạm thời để xử lý sự cố, hoặc một chuyên viên không còn được phép xuất dữ liệu khách hàng.

Ví dụ, tài khoản của An đang có quyền:

- Đọc báo cáo bán hàng của chi nhánh A.
- Sửa đơn hàng trong hạn mức được giao.
- Không có quyền xuất toàn bộ dữ liệu hoặc quản trị tài khoản.

Khi An trở thành trưởng nhóm, tổ chức muốn cho phép duyệt một số đơn hàng. Nếu hệ thống chỉ thêm nhóm `sales-manager` mà không rà soát quyền cũ, xung đột giữa **tạo đơn** và **duyệt đơn** có thể xuất hiện. Khi An thôi làm trưởng nhóm, nếu quyền duyệt không được thu hồi, An sẽ giữ **quyền truy cập tồn dư**. Đây là rủi ro ngay cả khi tài khoản vẫn hoạt động, người dùng xác thực MFA đúng và không có sự kiện nghỉ việc.

**Thay đổi mức quyền (privilege-level change)** là quá trình kiểm soát sự khác biệt giữa **quyền đang có** và **quyền được phép có sau một sự kiện thay đổi**, sau đó cấp, điều chỉnh, thu hồi và xác minh trạng thái thực tế của các hệ thống liên quan.

Bài toán này có ba chiều độc lập:

1. **Mức đặc quyền:** đọc, sửa, duyệt, xuất dữ liệu, cấu hình, quản trị hệ thống.
2. **Phạm vi:** tài nguyên, chi nhánh, tenant, môi trường dev/staging/prod, dữ liệu được truy cập.
3. **Điều kiện và thời hạn:** chỉ khi trực ca, từ thiết bị tin cậy, trong khoảng thời gian phê duyệt, hoặc sau một bước phê duyệt riêng.

Vì vậy, “mức quyền cao hơn” không chỉ là số nguyên lớn hơn. Chuyển từ quyền duyệt tài chính sang quyền quản trị hạ tầng là **thay đổi loại năng lực và rủi ro**, không thể xếp trên một trục cấp bậc duy nhất.

## 2. Nhận diện thay đổi quyền: tăng, giảm, chuyển ngang và tạm thời

| Kiểu thay đổi | Tình huống | Yêu cầu quản trị quan trọng |
|---|---|---|
| **Nâng quyền (elevation)** | Nhân viên được giao thêm quyền duyệt hồ sơ | Đánh giá mục đích, phạm vi, SoD và phê duyệt quyền nhạy cảm |
| **Giảm quyền (downgrade)** | Trưởng nhóm kết thúc nhiệm kỳ | Thu hồi quyền quản lý, xử lý nhóm/role và token còn hiệu lực |
| **Thay đổi phạm vi (scope change)** | Chỉ còn phụ trách chi nhánh B thay vì A | Gỡ truy cập chi nhánh A, cấp B; không gộp hai phạm vi vô thời hạn |
| **Chuyển ngang (role transition)** | Chuyển từ bộ phận vận hành sang phát triển | So sánh hai tập entitlement, xử lý quyền cũ không còn căn cứ |
| **Nâng quyền có thời hạn (JIT)** | Kỹ sư cần quyền admin trong 45 phút | Có yêu cầu, giới hạn thời gian, phiên được kiểm soát và tự thu hồi |
| **Nâng quyền khẩn cấp (break-glass)** | Xử lý sự cố khi cơ chế phê duyệt thông thường bị gián đoạn | Ràng buộc tài khoản/credential, giám sát, cảnh báo và hậu kiểm |
| **Thay đổi chủ sở hữu kỹ thuật** | Bot đổi đội quản lý hoặc chuyển sang production | Rà soát service principal, API scope, secret, trust và owner |

Điểm chung: tổ chức phải biết **quyền nào hợp lệ trước sự kiện, quyền nào hợp lệ sau sự kiện** và ai chịu trách nhiệm xác minh việc chuyển đổi.

### 2.1. Quyền của người dùng không chỉ nằm trong một role

Quyền hiệu lực có thể đến từ nhiều nguồn:

- Role được gán trực tiếp tại ứng dụng.
- Group trong IdP, kể cả nhóm lồng nhau.
- Thuộc tính nhân sự hoặc dự án được ABAC đánh giá động.
- Permission được chủ dữ liệu cấp trực tiếp.
- Quyền tạm thời/JIT do Privileged Access Management (PAM) cấp.
- Quyền trong ứng dụng SaaS không được đồng bộ với IdP.
- API key, chứng chỉ, session/token còn hiệu lực.
- Quyền chia sẻ thư mục, dữ liệu, cloud policy hoặc local account.

Do đó, chỉ nhìn một cột `role` trên IdP có thể không phản ánh **quyền thực sự đang được hệ thống đích chấp nhận**.

## 3. Mô hình hóa quyền cần thay đổi

Mỗi quyền nên được mô tả đủ rõ để tính khác biệt và kiểm toán.

| Thuộc tính | Câu hỏi | Ví dụ |
|---|---|---|
| Subject / principal | Danh tính nào nhận quyền? | `user-214`, `svc-reporting-prod` |
| Resource | Tài nguyên nào bị ảnh hưởng? | `invoice-api`, `tenant-west` |
| Action | Được làm gì? | `invoice.approve` |
| Scope | Phạm vi áp dụng ở đâu? | Phòng ban miền Tây, hạn mức dưới 100 triệu |
| Conditions | Điều kiện nào phải đúng? | Trạng thái nhân sự active; thiết bị compliant |
| Entitlement source | Quyền cấp qua đường nào? | IAM role, group, local grant, PAM session |
| Approval | Ai phê duyệt quyền? | Chủ dữ liệu kế toán |
| Effective interval | Quyền có hiệu lực từ khi nào đến khi nào? | Từ 09:00 đến 18:00 ngày được duyệt |
| Provenance | Quyền gắn với yêu cầu hoặc sự kiện nào? | Change request và event ID |
| Target state | Hệ thống đích đã xác nhận trạng thái chưa? | `CONFIRMED_GRANTED` / `CONFIRMED_REVOKED` |

**Lưu ý:** việc dùng thông tin “giá trị quyền” trong một bảng danh mục chỉ là mô hình tham khảo. Nền tảng cloud, database, hệ điều hành và SaaS có thể biểu diễn quyền bằng ngữ nghĩa và cú pháp khác nhau. IAM phải ánh xạ về hành động và tài nguyên cụ thể để tránh sai lệch.

### 3.1. Quyền mong muốn và quyền thực tế

Gọi:

- \( E_\text{before} \): tập quyền hiệu lực được phép trước sự kiện.
- \( E_\text{after} \): tập quyền được phép sau khi thay đổi.
- \( A_\text{observed} \): tập quyền hiện quan sát được ở hệ thống đích.

Hai tập thao tác cơ bản là:

\[
\text{Grant} = E_\text{after} \setminus E_\text{before}
\]

\[
\text{Revoke} = E_\text{before} \setminus E_\text{after}
\]

Trong môi trường thực, còn cần so sánh `E_after` với **toàn bộ quyền đang thực có** để phát hiện quyền cấp tay không xuất hiện trong `E_before`. Nếu một permission bị thu hồi từ group nhưng vẫn tồn tại do direct grant, quyền hiệu lực vẫn có thể giữ nguyên.

Trạng thái đạt yêu cầu là **quyền thực tế thỏa chính sách sau thay đổi**, không nhất thiết biểu diễn bằng phép so sánh chuỗi đơn giản. Ví dụ, quyền wildcard, role kế thừa và policy phủ định cần được giải nghĩa trước khi kết luận.

### 3.2. Ví dụ ma trận quyền

Nhân viên Bình chuyển từ vai trò `support-agent` sang `support-supervisor`.

| Tài nguyên / hành động | Trước Mover | Sau Mover được duyệt | Hành động |
|---|---:|---:|---|
| Xem ticket của nhóm | Có | Có | Giữ |
| Cập nhật ticket được phân công | Có | Có | Giữ |
| Xem báo cáo chất lượng toàn nhóm | Không | Có | Cấp |
| Phê duyệt hoàn tiền đến hạn mức quy định | Không | Có | Cấp sau kiểm tra điều kiện |
| Quản trị tài khoản nhân viên | Không | Không | Không cấp |
| Xuất toàn bộ dữ liệu khách hàng | Không | Không | Không cấp |

Nếu Bình quay về `support-agent`, hai quyền của supervisor phải được thu hồi theo thời điểm hiệu lực. Nếu Bình từng có quyền `customer.export-all` do dự án cũ cấp trực tiếp, cần phát hiện và rà soát quyền đó riêng, thay vì kết luận “đã xóa role supervisor nên hoàn tất”.

## 4. Nguồn kích hoạt Mover và căn cứ tăng/giảm quyền

Một yêu cầu thay đổi quyền không nên chỉ xuất phát từ tin nhắn “hãy thêm admin giúp tôi”. Trước khi thi hành cần xác định **sự kiện có thẩm quyền và người chịu trách nhiệm**.

Những nguồn thường gặp:

1. **HRIS/hồ sơ tổ chức:** thay chức danh, bộ phận, người quản lý, vị trí hoặc trạng thái hợp đồng.
2. **Hệ thống quản lý dự án:** tham gia/kết thúc dự án, đổi vai trò trong một workspace.
3. **Chủ ứng dụng/chủ dữ liệu:** phê duyệt quyền nhạy cảm hoặc điều chỉnh phạm vi truy cập.
4. **Hệ thống PAM/JIT:** yêu cầu nâng quyền ngắn hạn kèm lý do và phạm vi tác vụ.
5. **Sự kiện bảo mật:** thiết bị không còn compliant, tài khoản có rủi ro hoặc quyền phải tạm dừng.
6. **Thay đổi workload:** service account nhận trách nhiệm mới, chuyển môi trường hoặc ngừng sử dụng một API.

Mỗi nguồn có mức thẩm quyền khác nhau. HRIS có thể xác nhận nhân viên chuyển phòng ban, nhưng **không mặc nhiên là người có thẩm quyền duyệt quyền quản trị production**. Quyền nhạy cảm có thể yêu cầu chủ dữ liệu hoặc chủ tài nguyên phê duyệt bổ sung.

### 4.1. Hợp đồng sự kiện thay đổi quyền

Một sự kiện đủ dùng để điều phối thường có:

- ID sự kiện để đối chiếu và tránh xử lý trùng.
- ID danh tính ổn định; không chỉ dựa vào tên hoặc email có thể đổi.
- Loại thay đổi và giá trị cũ/mới.
- Thời điểm hiệu lực nghiệp vụ và nguồn đã xác thực.
- Người hoặc hệ thống có thẩm quyền phê duyệt.
- Danh sách mục tiêu cần xét hoặc tham chiếu đến chính sách tính quyền.
- Correlation ID để ghép yêu cầu với kết quả thi hành.

Ví dụ JSON **minh họa**, không phải schema bắt buộc:

~~~json
{
  "eventId": "mover-2026-0045",
  "subjectId": "user-214",
  "eventType": "ROLE_CHANGED",
  "source": "trusted-hris",
  "previousRole": "support-agent",
  "newRole": "support-supervisor",
  "effectiveAt": "2026-11-24T08:00:00+07:00",
  "approvalReference": "APR-9205",
  "correlationId": "IAM-CHG-4118"
}
~~~

Trong hệ thống thật, không nên tin các trường `source`, `newRole` hoặc `approvalReference` chỉ vì chúng xuất hiện trong một JSON; chúng phải đến từ kênh và quy trình có kiểm soát.

## 5. Quy trình chuẩn: quyết định → thay đổi → xác minh

Một workflow nâng/giảm quyền nên khép kín từ sự kiện đến kết quả thực tế:

~~~mermaid
flowchart TD
    A[Nhận sự kiện Mover từ nguồn có thẩm quyền] --> B[Kiểm tra identity và thời điểm hiệu lực]
    B --> C[Tính quyền mới theo chính sách RBAC/ABAC]
    C --> D[Thu thập quyền thực tế ở các hệ thống đích]
    D --> E[So sánh quyền cũ, mới và quyền đang có]
    E --> F{Quyền nhạy cảm / SoD / ngoại lệ?}
    F -- Có --> G[Xem xét và phê duyệt]
    F -- Không --> H[Lập kế hoạch Grant và Revoke]
    G --> H
    H --> I[Thực thi theo thứ tự an toàn và thời điểm hiệu lực]
    I --> J[Readback và đối soát từng hệ thống]
    J --> K{Quyền thực tế đúng chính sách?}
    K -- Chưa --> L[Ticket, cảnh báo, retry có kiểm soát]
    L --> J
    K -- Rồi --> M[Đóng sự kiện, lưu bằng chứng kiểm toán]
~~~

### Bước 1. Xác minh định danh và sự kiện

Kiểm tra đối tượng đang hoạt động, ID không bị trùng, nguồn sự kiện có thẩm quyền và ngày hiệu lực. Không dùng email làm khóa duy nhất nếu email có thể đổi sau Mover.

### Bước 2. Tính **quyền kỳ vọng** theo vai trò mới

Áp dụng role catalogue và thuộc tính hợp lệ; xét quyền theo bộ phận, dự án, tenant, mức dữ liệu, điều kiện làm việc và thời hạn. Nếu cấu hình cần ngoại lệ, ghi lý do và người phê duyệt.

### Bước 3. Khảo sát **quyền thực có**

Tổng hợp quyền ở IdP và hệ thống đích, kể cả nhóm trực tiếp/gián tiếp, local grants, vai trò cloud, chia sẻ tệp, session/tokens và quyền JIT chưa hết hạn.

### Bước 4. Kiểm tra SoD, đặc quyền và phạm vi

Xác định hành động nào phải chặn hoặc cần phê duyệt, ví dụ **người tạo nhà cung cấp** không đồng thời **tự duyệt thanh toán** nếu chính sách quy định phân tách trách nhiệm (*Separation of Duties*, SoD).

### Bước 5. Lập kế hoạch thay đổi

Mỗi grant và revoke cần có:

- Hệ thống đích, entitlement ID và phạm vi tài nguyên.
- Thời điểm hiệu lực, hạn hoàn tất và mức ưu tiên rủi ro.
- Ai thực hiện (connector/SCIM/API, PAM hoặc ticket thủ công).
- Cách xác minh thực thi và phương án xử lý lỗi.
- Phương án chuyển tiếp khi cắt quyền cũ có thể làm gián đoạn nghiệp vụ.

### Bước 6. Thực thi có kiểm soát

Không có một thứ tự cho mọi loại Mover. Với quyền nguy hiểm, **thu hồi trước hoặc đồng thời** có thể ưu tiên bảo mật; với quyền hỗ trợ dịch vụ liên tục, có thể cần giai đoạn chồng lấn hẹp, có phê duyệt và TTL. Mọi ngoại lệ phải có chủ sở hữu và thời hạn kết thúc.

### Bước 7. Readback và đóng sự kiện

Gửi lệnh thành công chưa đủ. Cần xác nhận quyền hiệu lực tại từng đích, xử lý các bước lỗi và lưu chứng cứ. Nếu chỉ hoàn thành 4/5 hệ thống, workflow phải biểu thị **PARTIAL**, không được khẳng định Mover đã kết thúc.

## 6. Tăng quyền: đặc quyền mới cần được kiểm soát như thế nào?

Tăng quyền có thể nâng tác động khi tài khoản bị chiếm dụng hoặc sử dụng sai. Khi cấp một quyền, cần đánh giá ít nhất bốn câu hỏi:

1. **Mục đích:** người dùng/workload cần chức năng gì?
2. **Phạm vi:** chỉ tài nguyên nào, dữ liệu nào, môi trường nào?
3. **Thời hạn:** cần lâu dài hay chỉ cho một tác vụ?
4. **Xung đột:** có tạo SoD conflict hoặc vượt quyền phê duyệt của owner không?

Ví dụ, một kỹ sư muốn sửa cấu hình production trong 30 phút. Thay vì gán `cloud-admin` cố định:

- Mở yêu cầu công việc có lý do/ticket.
- Phê duyệt theo mức độ nhạy cảm hoặc cơ chế an toàn được công bố.
- Cấp role giới hạn vào tài nguyên/namespace cần sửa nếu có thể.
- Yêu cầu MFA hoặc xác thực bổ sung khi phù hợp.
- Ghi log sự kiện, thao tác và phiên có đặc quyền.
- Tự thu hồi sau thời hạn, rồi xác minh không còn role/session đặc quyền.

Đây là nguyên tắc **just-in-time (JIT) privileged access**. JIT giảm thời gian tồn tại quyền mạnh; nó không thay thế kiểm soát phạm vi, chứng minh danh tính hoặc kiểm toán.

### 6.1. Quyền “quản trị” không phải mức quyền mặc định của quản lý

Trở thành trưởng nhóm kinh doanh có thể làm thay đổi quyền duyệt đơn trong CRM, nhưng không cần quyền `super-admin` trên IdP hoặc quản trị cơ sở dữ liệu. **Vai trò tổ chức** và **vai trò kỹ thuật trên từng hệ thống** phải được ánh xạ có chủ sở hữu; không chuyển thẳng chức danh sang role quyền cao.

### 6.2. Privileged Access Management (PAM)

PAM có thể bổ sung quy trình:

- Xác thực mạnh cho hành động đặc quyền.
- Phê duyệt hoặc điều kiện nhận quyền.
- Cấp quyền/session chỉ khi cần.
- Bảo vệ, quản lý và xoay vòng credential đặc quyền.
- Ghi nhận phiên, lệnh hoặc nhật ký tương ứng với mức độ rủi ro.
- Hết hạn và thu hồi có đối soát.

Không nên coi việc người dùng thoát giao diện PAM là bằng chứng quyền hoặc session tại hệ thống đích đã chấm dứt, nếu công nghệ đó còn cho phép session tiếp tục.

### 6.3. Phân quyền theo nhiệm vụ và cấp tạm thời

Một kỹ sư chỉ cần đọc log phục vụ điều tra không nên được cấp luôn quyền sửa cấu hình. Nếu hệ thống có vai trò `log-reader`, hãy cấp quyền đọc đúng vùng log; với sự cố nhạy cảm, quyền tạm thời có thể bị giới hạn theo thời điểm, môi trường và người duyệt.

## 7. Giảm quyền: phần khó nhất là xác minh đã thu hồi thật

Giảm quyền thường bị xem là thao tác “bỏ tick” một role. Trong thực tế, quyền có thể còn tồn tại ở nhiều nơi:

| Đường cấp quyền | Vì sao quyền còn tồn tại? | Biện pháp kiểm tra |
|---|---|---|
| Group IdP | Group lồng nhau hoặc thuộc tính tự động thêm lại | Tính membership hiệu lực và kiểm tra quy tắc gán |
| Local role ở SaaS | Quyền cấp thủ công ngoài connector | Đọc danh sách role/entitlement trực tiếp ở SaaS |
| SCIM/API | Connector lỗi hoặc hỗ trợ thu hồi chưa đầy đủ | Kiểm tra phản hồi chi tiết và đọc trạng thái đích |
| Cloud IAM | Gắn role qua nhóm, policy kế thừa hoặc resource scope khác | Tính effective permissions theo cơ chế của cloud |
| Database / file share | Grant trực tiếp hoặc owner cũ chưa chuyển giao | Đối chiếu ACL và user/role trong DB/file system |
| Token, session | Access token đã phát hành còn hiệu lực, session cache | Thu hồi hoặc giới hạn thời hạn theo khả năng của hệ thống |
| PAM/JIT | Phiên đặc quyền còn chạy hoặc TTL chưa kết thúc | Kiểm tra trạng thái phiên, quyền và credential |
| API key/service account | Credential độc lập với user group | Quản lý credential và ownership trong vòng đời riêng |

### 7.1. Gỡ nguồn cấp quyền chưa chắc gỡ quyền hiệu lực

Giả sử Bình nhận `reports.export` từ cả group `analyst` và một grant trực tiếp. Sau khi gỡ Bình khỏi group, direct grant vẫn còn. Vì vậy:

- **Thao tác đã làm:** remove group membership.
- **Trạng thái cần chứng minh:** Bình không thể xuất báo cáo trái chính sách.
- **Bằng chứng:** truy vấn entitlement tại hệ thống đích hoặc kiểm tra hiệu lực theo cơ chế API, có cân nhắc thời hạn phiên/tokens.

Điều này quan trọng khi user chuyển vai trò nhiều lần và quyền tích lũy qua năm tháng.

### 7.2. Token và phiên sau khi hạ quyền

Trong một số triển khai, access token tự chứa mang claim quyền tại thời điểm phát hành. Sau khi bỏ role, token cũ có thể vẫn được API chấp nhận cho đến khi hết hạn hoặc có biện pháp thu hồi/kiểm tra trạng thái. Mức độ thu hồi tức thời phụ thuộc kiến trúc.

Cần phân biệt:

- **Đã cập nhật entitlement ở nguồn**.
- **Không được cấp token/phiên mới chứa quyền cũ**.
- **Token hoặc phiên cũ đã hết hiệu lực**.
- **Tài nguyên đích thực sự từ chối thao tác không còn được phép**.

Với quyền rủi ro cao, tổ chức có thể dùng token ngắn hạn, cơ chế revoke/invalidation, kiểm tra chính sách tại API hoặc các biện pháp khác tương thích nền tảng.

### 7.3. Giảm quyền không đồng nghĩa khóa cả tài khoản

Một nhân viên mất quyền phê duyệt nhưng vẫn làm việc ở bộ phận khác. Mục tiêu Mover là thu hồi **quyền không còn hợp lệ**, duy trì quyền còn cần thiết theo chính sách; việc xóa tài khoản hoàn toàn có thể phá vỡ hoạt động bình thường.

## 8. RBAC và ABAC hỗ trợ thay đổi mức quyền ra sao?

### 8.1. RBAC: ánh xạ vai trò tới tập quyền

RBAC thường quản lý vai trò công việc hoặc vai trò kỹ thuật:

~~~text
support-agent:
  - tickets.read.assigned
  - tickets.update.assigned

support-supervisor:
  - tickets.read.team
  - tickets.update.team
  - quality-report.read
  - refunds.approve.limited
~~~

Khi Mover, IAM phải tính lại role assignment và entitlement, thay vì giữ mọi role đã từng có. Tên role chỉ là nhãn; các permission bên trong cần được duy trì và kiểm tra tính nhất quán theo phiên bản chính sách.

### 8.2. ABAC: thay đổi mức quyền theo thuộc tính

ABAC quyết định dựa trên thuộc tính của **subject, resource, action và môi trường**. Ví dụ, người được phép duyệt hoàn tiền cần:

- `user.employmentStatus == "active"`.
- `user.role == "support-supervisor"`.
- `refund.region == user.region`.
- `refund.amount <= user.approvalLimit`.
- Các điều kiện xác thực, phiên hoặc thiết bị theo chính sách.

Khi người dùng chuyển chi nhánh, cập nhật `user.region` có thể làm thay đổi quyền hiệu lực ngay nếu API đánh giá thuộc tính mới ở mỗi request. Tuy nhiên, nếu ứng dụng **cache thuộc tính trong token** hoặc sao chép sang dữ liệu cục bộ, cần có cơ chế làm mới/đồng bộ để tránh quyền cũ tồn tại.

### 8.3. Ví dụ pseudo-policy kết hợp RBAC và ABAC

~~~text
function canApproveRefund(principal, refund, session):
    if principal.status != ACTIVE:
        return DENY

    if not principal.hasRole("support-supervisor"):
        return DENY

    if refund.region != principal.region:
        return DENY

    if refund.amount > principal.approvalLimit:
        return DENY

    if session.authStrength < policy.requiredAuthStrength:
        return STEP_UP_OR_DENY

    return ALLOW
~~~

Đây là mã giả. Nền tảng thực tế phải xác minh các thuộc tính từ nguồn tin cậy; API không nên lấy `role`, `region` hay `approvalLimit` từ một request tự khai báo mà không xác thực.

## 9. IdP, SSO, SCIM và hệ thống đích khi tăng/giảm quyền

Một workflow Mover có thể trải qua nhiều thành phần:

~~~mermaid
sequenceDiagram
    participant HR as HR / nguồn thay đổi
    participant IAM as IAM Lifecycle Workflow
    participant Owner as Chủ quyền / người duyệt
    participant IdP as IdP / Group & Role
    participant SaaS as SaaS / API đích
    participant Audit as Audit log
    HR->>IAM: Role changed, effectiveAt
    IAM->>IAM: Tính entitlement diff và kiểm tra SoD
    IAM->>Owner: Yêu cầu duyệt quyền nhạy cảm nếu cần
    Owner-->>IAM: Quyết định có bằng chứng
    IAM->>IdP: Gỡ role cũ / gán role mới theo policy
    IAM->>SaaS: SCIM / API / tác vụ thủ công
    SaaS-->>IAM: Kết quả thực thi
    IAM->>SaaS: Readback entitlement thực tế
    SaaS-->>IAM: Effective access / trạng thái mục tiêu
    IAM->>Audit: Trạng thái cuối và bằng chứng
~~~

**IdP:** lưu/điều phối danh tính, group, role, thuộc tính và cấu hình xác thực tùy sản phẩm. Cập nhật IdP không bảo đảm mọi hệ thống đã nhận thay đổi.

**SSO:** hỗ trợ người dùng đăng nhập vào nhiều ứng dụng. Đăng nhập SSO thành công chưa chứng minh người dùng được làm mọi hành động trong ứng dụng. SSO cũng không tự xử lý mọi role local, API key hoặc session đã cấp.

**SCIM:** hỗ trợ provisioning và đồng bộ User/Group/thuộc tính đến ứng dụng tương thích. Mức độ đồng bộ **app role, quyền riêng trong SaaS hoặc khóa API** phụ thuộc connector và sản phẩm; không nên mặc định tất cả được cập nhật.

**RBAC/ABAC tại hệ thống đích:** nơi thực thi quyết định quyền trên thao tác và dữ liệu. IAM cần đối soát trạng thái ở đó.

Ví dụ, nhân viên rời vai trò `finance-approver`:

1. HRIS ghi nhận thay đổi có hiệu lực.
2. IAM cập nhật group/role ở IdP.
3. Connector cập nhật nhóm và role bên SaaS tài chính nếu tích hợp hỗ trợ.
4. Hệ thống tài chính có thể còn direct grant hoặc phiên đã phát hành.
5. Workflow kiểm chứng quyền `payment.approve` thực tế đã bị chặn, giải quyết mọi ngoại lệ và ghi bằng chứng.

Không nên coi phản hồi `200 OK` của một API là bằng chứng mọi quyền trên tất cả hệ thống đã đúng.

## 10. Trình tự thay đổi và xử lý lỗi khi nhiều hệ thống không đồng bộ

Các nền tảng IAM, SaaS, cloud và database thường không chia sẻ cùng một giao dịch nguyên tử. Một thay đổi quyền có thể thành công ở hệ thống A nhưng thất bại ở B.

### 10.1. Chọn thứ tự theo rủi ro và tính liên tục

Ví dụ, chuyển từ bộ phận thanh toán sang kiểm toán có thể yêu cầu:

- Thu hồi quyền **duyệt thanh toán** trước khi cấp quyền **kiểm toán giao dịch**, nếu chính sách SoD cấm hai quyền đồng thời.
- Cấp quyền xem dữ liệu mới đúng ngày hiệu lực để không gián đoạn công việc.
- Khi cần bàn giao tạm thời, định nghĩa cửa sổ chồng lấn có phê duyệt, phạm vi hẹp và thời điểm hết hạn.

Không có quy tắc cố định luôn “grant trước, revoke sau” hoặc ngược lại cho mọi ứng dụng. Quy trình cần thể hiện rõ các ràng buộc và thứ tự kiểm soát cụ thể.

### 10.2. Idempotency và xử lý sự kiện trùng

Hệ thống sự kiện có thể phát lại một yêu cầu, hoặc connector tự retry sau timeout. Một workflow an toàn cần hướng tới **idempotency**: cùng một sự kiện hợp lệ được chạy lại không tạo quyền thừa hoặc thay đổi trái mục tiêu.

Có thể dùng:

- Event ID và phiên bản trạng thái danh tính để bỏ qua sự kiện đã xử lý.
- Thao tác “đặt trạng thái đích” thay vì “cộng thêm quyền” không kiểm soát.
- Đối soát tại đích trước/sau retry.
- Chính sách xử lý sự kiện đến sai thứ tự, ví dụ Mover cũ đến sau Leaver.
- Correlation ID cho từng lệnh và kết quả.

### 10.3. Đừng rollback bằng cách tự ý cấp lại quyền nguy hiểm

Nếu grant quyền mới thất bại nhưng revoke quyền cũ đã xong, “rollback” bằng cách cấp lại toàn bộ quyền cũ có thể tạo rủi ro SoD hoặc phá chính sách mới. Nên xác định trước **trạng thái an toàn**, phương án khắc phục và người có thẩm quyền quyết định cấp ngoại lệ.

Khi quyền cũ đã bị thu hồi vì nguy cơ bảo mật, không tự cấp lại chỉ để đạt “all-or-nothing” về mặt vận hành.

### 10.4. Trạng thái job cần biểu đạt chính xác

Một workflow có thể theo dõi riêng:

| Trạng thái | Ý nghĩa |
|---|---|
| REQUESTED | Đã nhận yêu cầu/sự kiện |
| VALIDATED | Đã xác minh danh tính, nguồn và policy đầu vào |
| APPROVAL_PENDING | Chờ người có thẩm quyền duyệt |
| APPLYING | Đang thực thi tại các hệ thống đích |
| PARTIAL | Một hoặc nhiều hệ thống chưa đạt trạng thái mục tiêu |
| VERIFIED | Quyền thực tế đã được kiểm chứng đúng mục tiêu |
| FAILED / ESCALATED | Có lỗi cần xử lý hoặc quyết định ngoại lệ |

Mô hình trạng thái chỉ là ví dụ. Quan trọng nhất là phân biệt **đã gửi lệnh**, **đã nhận kết quả thao tác** và **đã xác minh effective access**.

## 11. Trường hợp đặc biệt: tài khoản dịch vụ và ứng dụng chuyển mức quyền

Service account, application principal và workload identity cũng gặp Mover: chuyển pipeline từ dev sang production, thay API đích, mở quyền ghi cho job trước đây chỉ đọc, hoặc chuyển team sở hữu bot.

Ví dụ, `billing-exporter` đang đọc dữ liệu hóa đơn tổng hợp. Khi tính năng mới cần ghi file đã xử lý vào kho lưu trữ:

- Chỉ cấp quyền ghi vào đúng bucket/path mới nếu cần, không cấp wildcard administrator.
- Giữ tách biệt principal production và staging theo ranh giới tin cậy.
- Xác định owner kỹ thuật/nghiệp vụ, nguồn workload và quan hệ trust (issuer, subject, audience).
- Nếu dùng secret/certificate, đánh giá rotation hoặc phát credential mới khi thay môi trường.
- Thu hồi API grant/trust cũ khi công việc không còn sử dụng.
- Ghi lại ứng dụng nào đã làm gì, tại tài nguyên nào và trong thời gian nào.

**Không dùng tài khoản cá nhân của nhân viên để chạy workload lâu dài.** Khi người đó đổi vai trò hoặc nghỉ, việc xử lý quyền cá nhân có thể vô tình làm dừng dịch vụ, hoặc tổ chức giữ lại tài khoản cá nhân quyền cao để duy trì job.

Một service principal có thể không thuộc hệ thống HRIS; workflow Mover của nó nên đến từ **danh mục ứng dụng, thay đổi deployment hoặc phê duyệt của chủ dịch vụ**, rồi được điều phối IAM với cùng nguyên tắc least privilege, thời hạn và readback.

## 12. Ví dụ thực hành: thay đổi mức quyền của cán bộ tài chính

### 12.1. Bối cảnh

Chị Hòa đang là nhân viên kế toán, có thể nhập yêu cầu thanh toán nhưng không được duyệt. Trong hai tuần, chị Hòa được phân công thay trưởng nhóm và cần duyệt các khoản nhỏ. Kết thúc hai tuần, chị trở lại công việc cũ.

**Chính sách minh họa:**

- `payment.request.create`: tạo yêu cầu.
- `payment.approve.limited`: duyệt trong hạn mức theo phòng ban.
- SoD: người tạo một khoản không được tự duyệt chính khoản đó.
- Quyền `payment.approve.limited` chỉ có hiệu lực trong thời gian được ủy quyền và trên đúng phạm vi.

### 12.2. Đầu vào mong muốn

~~~yaml
eventId: mover-fin-2026-011
principal: user-hoa
type: TEMPORARY_PRIVILEGE_ELEVATION
request:
  permission: payment.approve.limited
  resource: finance-system
  scope:
    businessUnit: north
    maxAmount: 50000000
  effectiveFrom: "2026-11-23T09:00:00+07:00"
  effectiveUntil: "2026-12-07T18:00:00+07:00"
  approvalId: "FIN-APP-902"
controls:
  enforceSeparationOfDuties: true
  requireStrongAuthentication: true
  revokeOnExpiry: true
~~~

Đây là YAML **minh họa**, không phải cấu hình có thể nhập trực tiếp vào hệ thống IAM. Các số tiền, thời điểm và điều kiện chỉ phục vụ ví dụ học tập.

### 12.3. Thực hiện đúng

1. Xác minh đề nghị từ người quản lý/chủ quyền và sự kiện phân công hai tuần.
2. Đối chiếu tài khoản Hòa, quyền kế toán hiện có và các quyền được cấp tay.
3. Kiểm tra SoD. Nếu chính sách không cho phép một người vừa tạo vừa duyệt cùng khoản, API phải áp dụng ràng buộc ở **mức giao dịch**, kể cả khi người đó tạm có hai năng lực.
4. Phê duyệt quyền nâng cấp đúng scope, mức tiền, từ/đến thời điểm.
5. Cấp quyền tại IdP/hệ thống tài chính theo tích hợp thực tế.
6. Kiểm thử Hòa duyệt được khoản **hợp lệ**, không duyệt được khoản vượt hạn mức/ngoài phòng ban/do chính mình tạo trái chính sách.
7. Đến hạn, thu hồi role, xử lý token/phiên và đối soát trực tiếp ở hệ thống tài chính.
8. Lưu sự kiện, approval, thời điểm, kết quả và mọi ngoại lệ.

### 12.4. Các kết quả sai cần phát hiện

| Hiện tượng | Vì sao sai | Hành động xử lý |
|---|---|---|
| Cấp role duyệt không hạn kết thúc | Quyền tạm biến thành quyền thường trực | Gắn TTL, lịch thu hồi và kiểm chứng |
| Hòa có quyền duyệt mọi phòng ban | Scope vượt phạm vi phân công | Thu hẹp tài nguyên và điều kiện ABAC |
| Hòa tự duyệt khoản mình tạo | Xung đột nhiệm vụ | SoD kiểm tra tại transaction/API |
| Đã gỡ role IdP nhưng còn role local | Quyền tồn dư | Đối soát local entitlement và thu hồi trực tiếp |
| Phiên cũ vẫn duyệt sau hết hạn | Session/token không phản ánh thay đổi | Kiểm soát phiên, token và API theo khả năng hệ thống |
| Worker ghi `COMPLETE` khi một connector lỗi | Mất chứng cứ về quyền chưa thu hồi | Đánh dấu PARTIAL, escalations và retry có kiểm soát |

## 13. Audit trail và cách chứng minh quyền đã thay đổi

Đối với quyền nhạy cảm, một log “đã cập nhật group” thường chưa đủ để giải thích rủi ro. Hệ thống nên liên kết:

- **Sự kiện:** ai/nguồn nào thông báo thay đổi, khi nào có hiệu lực?
- **Quyết định:** entitlement trước/sau, policy/SoD nào đã xét và ai phê duyệt?
- **Thực thi:** hệ thống nào nhận grant/revoke, lúc nào, kết quả gì?
- **Đối soát:** quyền hiệu lực và session/token tại đích có đúng không?
- **Ngoại lệ:** quyền giữ chồng lấn có lý do, owner và ngày hết hạn không?
- **Kết luận:** đã VERIFIED hay còn PARTIAL/PENDING?

Một audit record minh họa:

~~~json
{
  "eventId": "mover-2026-0045",
  "subjectId": "user-214",
  "changeType": "REVOKE",
  "permission": "refund.approve",
  "resource": "finance-api",
  "effectiveAt": "2026-11-24T08:00:00+07:00",
  "approvedBy": "finance-data-owner",
  "executor": "iam-provisioning",
  "executionStatus": "SUCCESS",
  "verificationStatus": "CONFIRMED_REVOKED",
  "correlationId": "IAM-CHG-4118"
}
~~~

Không được ghi `CONFIRMED_REVOKED` chỉ vì connector trả về `SUCCESS`. Trạng thái xác minh phải dựa trên bằng chứng đọc lại hoặc kiểm tra phù hợp với hệ thống đích.

### 13.1. Chỉ số theo dõi hiệu quả

| Chỉ số | Ý nghĩa | Cần phân biệt |
|---|---|---|
| Thời gian nâng quyền hợp lệ | Từ lúc yêu cầu được duyệt/đủ điều kiện đến khi quyền sẵn sàng | Thời gian chờ duyệt và thời gian xử lý kỹ thuật |
| Thời gian hạ quyền | Từ lúc quyền hết hợp lệ đến khi xác minh thu hồi | “Lệnh đã gửi” khác “quyền hết hiệu lực” |
| Số quyền tồn dư sau Mover | Entitlement đang tồn tại mà không còn căn cứ | Có tính direct grants, group lồng và token không? |
| Tỷ lệ Mover hoàn tất toàn bộ hệ thống | Số workflow đã VERIFIED trên số workflow đến hạn | Không đếm PARTIAL là hoàn thành |
| Tỷ lệ quyền JIT hết hạn đúng | Quyền tạm được thu hồi và xác minh theo hạn | Quyền chuyển tiếp quá hạn |
| Số xung đột SoD đã xử lý | Quyền xung đột được chặn hoặc có bù trừ hợp lệ | Không chỉ đếm cảnh báo chưa xử lý |

Cần xác định mẫu số, kỳ báo cáo và mức rủi ro ứng dụng. Tránh đặt cùng một SLA cho quyền xem thông tin công khai và quyền quản trị cơ sở dữ liệu sản xuất.

## 14. Các hiểu lầm thường gặp

**“Thăng chức nghĩa là giữ tất cả quyền cũ rồi thêm quyền mới.”** Không đúng. Quyền cũ không còn phục vụ nhiệm vụ cần được rà soát, kể cả khi tăng cấp bậc.

**“Hạ quyền chỉ cần gỡ role trong IdP.”** Chưa đủ. Ứng dụng có thể giữ local grants, cloud role, token còn hiệu lực hoặc quyền cấp từ nguồn khác.

**“Nếu có SSO thì hệ thống SaaS chắc chắn cập nhật quyền ngay.”** SSO chủ yếu hỗ trợ xác thực/đăng nhập; đồng bộ entitlement phụ thuộc SCIM/API, kiến trúc ứng dụng và cơ chế đối soát.

**“Được phép duyệt thanh toán thì có thể tự duyệt khoản đã tạo.”** SoD có thể chặn hành vi tại mức giao dịch dù cả hai chức năng đều được hiển thị.

**“Quyền JIT hết hạn trên giao diện nghĩa là phiên admin đã kết thúc.”** Tùy hệ thống, session/token cũ có thể cần cơ chế chấm dứt riêng hoặc xác minh trạng thái.

**“Khi cấp quyền mới lỗi, cứ hoàn nguyên bằng cách cấp lại tất cả quyền cũ.”** Điều đó có thể khôi phục quyền đã bị thu hồi vì lý do an ninh. Cần xử lý lỗi theo trạng thái an toàn và chính sách đã phê duyệt.

**“Tài khoản dịch vụ không có Mover.”** Ứng dụng/workload đổi chức năng, môi trường, API hoặc chủ sở hữu cũng làm thay đổi nhu cầu quyền và nguồn tin cậy.

## 15. Bài tập tự kiểm tra

### Tình huống A: tăng cấp nhưng có SoD conflict

Minh vừa được bổ nhiệm làm người phê duyệt mua hàng. Trước đó Minh đã có quyền tạo nhà cung cấp, và chính sách cấm một người vừa tạo vừa duyệt thanh toán cho cùng nhà cung cấp. Có thể cấp nguyên role quản lý mới không?

**Gợi ý:** Cần phân tích entitlement hiệu lực và đối tượng giao dịch; chỉ cấp sau khi giải quyết xung đột (thu hồi quyền không cần, phân tách trách nhiệm hoặc kiểm soát bù trừ được phê duyệt), không chỉ dựa vào chức danh.

### Tình huống B: chuyển chi nhánh

An đang có quyền xem dữ liệu khách hàng chi nhánh A và chuyển sang chi nhánh B. Hệ thống đã thêm `region=B` nhưng token hiện vẫn chứa `region=A` và group A còn hiệu lực.

**Gợi ý:** Phải cập nhật nguồn thuộc tính, gỡ quyền A, làm mới cơ chế đánh giá quyền/token và kiểm chứng không còn truy cập dữ liệu A nếu chính sách không cho phép.

### Tình huống C: nâng quyền tạm trong sự cố

Một kỹ sư cần quyền sửa cấu hình production trong 40 phút để khắc phục lỗi. Kỹ sư đề xuất cấp `global-admin` trong ba tháng vì “lần sau sẽ tiện”.

**Gợi ý:** Áp dụng least privilege, quyền đúng tài nguyên, JIT/TTL và audit. Nhu cầu 40 phút không tạo căn cứ cho quyền cố định ba tháng.

### Tình huống D: quyền đã bị gỡ nhưng vẫn dùng được

Chủ dữ liệu xác nhận đã gỡ tài khoản khỏi group `invoice-approver`. Nhân viên vẫn duyệt được hóa đơn ở SaaS.

**Gợi ý:** Điều tra local role/direct grant, group khác, token/session, cache và connector provisioning; readback effective permission trước khi khẳng định hoàn tất.

### Tình huống E: service account đổi môi trường

Job `build-release` từng dùng role triển khai staging. Khi triển khai production, đội vận hành thêm role production vào cùng principal và giữ nguyên secret cũ.

**Gợi ý:** Đánh giá tách principal theo môi trường, quyền production giới hạn, quan hệ trust và credential, kiểm soát phê duyệt, thu hồi quyền cũ nếu không còn cần.

## 16. Checklist triển khai thay đổi mức quyền

Trước khi đóng một sự kiện Mover, hãy kiểm tra:

1. **Danh tính:** subject ID và nguồn thay đổi có được xác thực?
2. **Thời điểm:** hiệu lực ngay hay trong tương lai; có thời hạn kết thúc không?
3. **Quyền kỳ vọng:** hành động, tài nguyên, scope, điều kiện và role mới có được định nghĩa?
4. **Quyền thực tế:** đã xét direct grants, group lồng, local role, cloud policy, service account và credential chưa?
5. **SoD/least privilege:** có xung đột nhiệm vụ hoặc quyền quá rộng cần chặn/phê duyệt?
6. **Thứ tự:** kế hoạch grant/revoke bảo đảm kiểm soát rủi ro và tính liên tục hoạt động?
7. **Cấp quyền tạm:** có JIT/TTL, giới hạn phạm vi và cơ chế thu hồi tự động?
8. **Tích hợp:** IdP, SCIM, API đích và thủ công đã xử lý đầy đủ?
9. **Phiên/token:** quyền cũ trong token/session có được đánh giá theo mức rủi ro?
10. **Readback:** các hệ thống đích xác nhận quyền hiệu lực đúng chính sách?
11. **Lỗi:** có PARTIAL, retry an toàn, escalation và người chịu trách nhiệm?
12. **Audit:** sự kiện, người duyệt, trước/sau, lệnh, thời điểm và kết quả có truy vết được?

**Điểm cần nhớ:** Trong Mover lifecycle, thay đổi mức quyền là quá trình **tính lại quyền hợp lệ, loại bỏ quyền không còn cần, cấp đúng quyền mới và kiểm chứng trạng thái trên hệ thống đích**. Kết hợp RBAC/ABAC, phê duyệt theo rủi ro, SoD, PAM/JIT, IdP/SCIM và kiểm toán giúp tổ chức đáp ứng công việc mới mà không tích lũy quyền truy cập tồn dư.
