# Xác định identity source trong thiết kế chương trình IAM

Trong một chương trình Identity and Access Management (IAM), câu hỏi đầu tiên khi tạo, cập nhật hoặc thu hồi tài khoản không phải là “cấp quyền ở ứng dụng nào?”, mà là **“hệ thống nào được phép xác nhận danh tính này tồn tại, đang thuộc tổ chức và có những thuộc tính nào?”**. Hệ thống trả lời câu hỏi đó là *identity source* — nguồn dữ liệu danh tính được tổ chức công nhận cho một phạm vi cụ thể.

Việc chọn sai nguồn có thể khiến nhân viên đã nghỉ việc vẫn đăng nhập được, nhà thầu hết hợp đồng vẫn giữ quyền, hoặc một lần thay đổi phòng ban tạo ra hai hồ sơ danh tính. Với vòng đời **Joiner–Mover–Leaver (JML)**, xác định đúng nguồn là điều kiện để IdP, SSO, SCIM, RBAC/ABAC, kiểm toán và quy trình thu hồi quyền hoạt động nhất quán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt *identity source*, kho danh tính, Identity Provider (IdP) và hệ thống đích nhận tài khoản.
2. Chỉ định nguồn có thẩm quyền theo **loại danh tính, thuộc tính và sự kiện vòng đời**, thay vì mặc định một hệ thống làm chủ mọi dữ liệu.
3. Thiết kế bảng quản trị nguồn, khóa định danh, quy tắc xử lý xung đột và hợp đồng đồng bộ.
4. Xác định nguồn phát tín hiệu JML để cấp, đổi, thu hồi truy cập đúng thời điểm và có thể kiểm toán.
5. Nhận diện trường hợp đặc biệt: nhà thầu, đối tác, tài khoản dịch vụ, danh tính máy và trạng thái khóa khẩn cấp.

## 2. Identity source là gì?

**Identity source** là hệ thống hoặc quy trình được giao trách nhiệm cung cấp bản ghi hoặc sự kiện đáng tin cậy để IAM xác định một thực thể danh tính và các thuộc tính thuộc quyền quản lý của nguồn đó. Trong thực tế, thuật ngữ *authoritative source* nhấn mạnh rằng hệ thống ấy **có thẩm quyền** đối với một tập thông tin xác định, ví dụ HRIS có thẩm quyền đối với trạng thái tuyển dụng của nhân viên.

Không có quy tắc rằng mọi thông tin về một người phải thuộc một nguồn. HRIS có thể sở hữu mã nhân viên và ngày chấm dứt hợp đồng; cổng hồ sơ cá nhân sở hữu tên hiển thị ưa thích; hệ thống phê duyệt truy cập sở hữu quyết định cấp một quyền đặc biệt. IAM phải biết nguồn nào được chấp nhận cho từng dữ kiện và vì sao.

| Thành phần | Trả lời câu hỏi | Ví dụ trách nhiệm |
|---|---|---|
| **Identity source / system of record** | “Ai là thực thể này? Quan hệ với tổ chức và dữ kiện gốc có hiệu lực ra sao?” | HRIS xác nhận nhân viên đang làm việc; hệ thống quản lý nhà thầu xác nhận ngày hết hạn hợp đồng. |
| **Identity registry / IGA** | “Làm sao liên kết bản ghi, áp chính sách vòng đời và điều phối phê duyệt?” | Chuẩn hóa nguồn, lập hồ sơ danh tính, theo dõi quyền và thực hiện JML. |
| **Directory / IdP** | “Ai có thể xác thực và nhận phiên đăng nhập?” | Entra ID, Okta hoặc dịch vụ danh mục điều khiển tài khoản và phiên xác thực. |
| **SSO** | “Người dùng đăng nhập vào các ứng dụng thế nào?” | SAML/OIDC cho đăng nhập liên kết, truyền thông tin xác thực hoặc claim. |
| **SCIM / provisioning API** | “Tài khoản, nhóm ở hệ thống đích được tạo/cập nhật/vô hiệu hóa ra sao?” | Đồng bộ tài khoản từ nền tảng IAM/IdP xuống ứng dụng SaaS. |
| **Ứng dụng và công cụ PAM** | “Quyền cụ thể nào tồn tại trong tài nguyên?” | Quyền quản trị, nhóm ứng dụng, quyền truy cập đặc quyền hoặc quyền theo phiên. |

Ví dụ, IdP có thể đang hiển thị người dùng **Active**, nhưng trạng thái này chưa chứng minh người đó vẫn là nhân viên. Nếu HRIS cho biết hợp đồng đã chấm dứt, IAM cần xử lý thu hồi quyền dù thư mục hiện chưa đồng bộ. Ngược lại, nếu đội an ninh đã chủ động khóa tài khoản, một sự kiện HRIS **Active** không được tự động gỡ khóa bảo mật.

> **Nguyên tắc thiết kế:** “Có bản ghi trong IdP” không tương đương “đủ điều kiện truy cập”; “đủ điều kiện truy cập” cũng không tự động tương đương “được cấp mọi quyền”. Nguồn danh tính, điều kiện đăng nhập và quyết định phân quyền là ba trách nhiệm liên quan nhưng khác nhau.

## 3. Chọn nguồn theo nhóm danh tính

Trước khi thiết kế đồng bộ, hãy liệt kê toàn bộ nhóm danh tính có quyền truy cập vào hệ thống, bao gồm cả con người lẫn máy. Một công ty có thể phải dùng nhiều nguồn cùng lúc:

| Nhóm danh tính | Nguồn có thẩm quyền thường gặp | Dữ kiện vòng đời quan trọng | Rủi ro nếu chọn sai |
|---|---|---|---|
| **Nhân viên** | HRIS/hệ thống nhân sự | Mã nhân viên, ngày bắt đầu, trạng thái lao động, phòng ban, người quản lý, ngày nghỉ việc | Tạo tài khoản trước thời điểm cho phép, không thu hồi khi nghỉ việc, giữ quyền sau khi chuyển nhóm. |
| **Nhà thầu/thời vụ** | Vendor Management System, hồ sơ hợp đồng có người bảo trợ | Mã hợp đồng, đơn vị cung cấp, người bảo trợ, ngày hết hạn, trạng thái hợp đồng | Không có ngày kết thúc rõ ràng; tài khoản còn hoạt động khi hợp đồng đã hết. |
| **Đối tác B2B** | Cổng đối tác/CRM kết hợp đăng ký và phê duyệt người bảo trợ | Tổ chức đối tác, người phụ trách, phạm vi hợp tác, ngày chấm dứt quan hệ | Quan hệ doanh nghiệp hết hiệu lực nhưng tài khoản đối tác còn quyền. |
| **Khách hàng B2C** | CIAM/hệ thống đăng ký người dùng và xác minh tương ứng | Mã khách hàng, trạng thái tài khoản, xác thực email/điện thoại, yêu cầu khóa/xóa | Nhầm người sở hữu tài khoản, dựa vào thông tin chưa xác minh, xử lý sai yêu cầu xóa. |
| **Tài khoản dịch vụ** | Service catalog/CMDB, nền tảng quản lý workload và người sở hữu kỹ thuật | Mã dịch vụ, môi trường, workload, chủ sở hữu, ngày hết hạn hoặc mốc đánh giá | Tài khoản không còn chủ sở hữu, credential tồn dư, quyền cao không được rà soát. |
| **Danh tính máy/workload** | Cloud IAM, orchestration, inventory workload hoặc cơ chế cấp danh tính theo thời gian chạy | Workload ID, môi trường, trust boundary, vòng đời triển khai và hủy | Tái sử dụng credential tĩnh, danh tính còn tồn tại sau khi workload bị xóa. |

Những nguồn trên là **mẫu tham khảo**, không phải cấu hình bắt buộc. Chẳng hạn công ty nhỏ có thể chưa có VMS; lúc đó quy trình quản lý hợp đồng có người chịu trách nhiệm, mã định danh và kiểm soát phê duyệt vẫn có thể đóng vai trò nguồn chuẩn tạm thời. Điều quan trọng là ghi rõ **ai chịu trách nhiệm tính đúng đắn của dữ liệu và ai có thể thay đổi nó**.

### Khi một người xuất hiện trong nhiều nguồn

Một cá nhân có thể vừa là nhân viên cũ, vừa là nhà thầu, hoặc có tài khoản khách hàng cá nhân. Không nên gộp tất cả bản ghi chỉ vì chúng trùng email, họ tên hay số điện thoại. Các giá trị này có thể thay đổi, trùng nhau hoặc bị tái sử dụng.

Nên tách ba lớp:

- **Khóa bản ghi nguồn:** cặp `(sourceSystem, sourceRecordId)`, chẳng hạn `(HRIS, EMP-1042)`; phải duy nhất trong phạm vi nguồn.
- **Identity ID nội bộ:** khóa ổn định của hồ sơ IAM, độc lập với email hoặc username.
- **Liên kết đến một con người:** chỉ tạo sau khi có đủ bằng chứng đối chiếu và quy trình xử lý sai ghép; một người vẫn có thể sở hữu nhiều danh tính ứng với nhiều mối quan hệ.

Nếu nguồn tái sử dụng mã nhân viên hoặc thay đổi khóa chính, cần quy trình đổi khóa có kiểm chứng. Tuyệt đối không coi email là khóa chính của vòng đời truy cập.

## 4. Thiết lập ma trận thẩm quyền dữ liệu

“HRIS là nguồn của nhân viên” vẫn còn quá chung. Một chương trình IAM có thể nhận tên hiển thị từ cổng nhân sự, nhóm công tác từ HRIS, yêu cầu quyền bổ sung từ hệ thống phê duyệt và trạng thái khóa khẩn cấp từ bộ phận an ninh. Vì vậy nên tạo **ma trận thẩm quyền theo từng thuộc tính**.

Ví dụ cho danh tính nhân viên:

| Thuộc tính hoặc quyết định | Nguồn được quyền thay đổi | Cách IAM dùng thông tin |
|---|---|---|
| `employeeId`, quan hệ lao động, ngày bắt đầu/kết thúc | HRIS | Định danh bản ghi và xác định điều kiện vòng đời. |
| `departmentId`, `managerId`, địa điểm làm việc | HRIS hoặc hệ thống tổ chức được chỉ định | Tính lại thuộc tính ABAC, vai trò cơ sở và người phê duyệt. |
| Tên hiển thị ưa thích | Cổng hồ sơ nhân viên đã xác minh | Hiển thị và đồng bộ xuống hệ thống phù hợp, không làm khóa liên kết. |
| Tài khoản bị khóa vì sự cố bảo mật | SOC/IdP theo quy trình an ninh | Chặn truy cập cho đến khi lệnh khóa được gỡ bởi đúng chủ thể có quyền. |
| Quyền cơ sở cho chức danh | Bộ chính sách IAM được phê duyệt | Xác định entitlement từ RBAC/ABAC, không sao chép trực tiếp tên phòng ban thành quyền tùy ý. |
| Quyền đặc biệt, đặc quyền quản trị | Người quản lý ứng dụng/PAM và quy trình phê duyệt | Cấp có điều kiện, thời hạn, người sở hữu và lịch sử phê duyệt. |
| `lastLoginAt`, trạng thái MFA | IdP | Quan sát hành vi xác thực và đánh giá bảo mật, không thay thế dữ kiện nhân sự. |

Ma trận nên ghi thêm: **owner nghiệp vụ, owner kỹ thuật, kiểu dữ liệu, độ nhạy, quy tắc ghi đè, thời gian hiệu lực, độ trễ mục tiêu và cách xử lý khi không có dữ liệu**. Mỗi thuộc tính quan trọng cần một thẩm quyền chính và quy tắc ngoại lệ rõ ràng.

### Quy tắc xử lý xung đột

Giả sử IdP nhận `department=Finance` trong khi HRIS đã đổi sang `Engineering`. Nếu HRIS là nguồn có thẩm quyền cho phòng ban, IAM phải cập nhật hồ sơ chuẩn theo HRIS và điều phối việc sửa dữ liệu ở các hệ thống đích, đồng thời ghi nhận xung đột. Không áp dụng quy tắc “bên nào cập nhật sau cùng thì thắng” giữa hai hệ thống có thẩm quyền khác nhau.

Thực hành thường dùng:

1. **Quy định thứ tự ưu tiên theo thuộc tính**, không dùng một thứ tự ưu tiên chung cho mọi dữ kiện.
2. **Chỉ chấp nhận bản cập nhật có nguồn hợp lệ**, khóa nguồn xác định được và phiên bản/thời điểm phù hợp.
3. **Phân biệt dữ kiện gốc và quyết định bảo mật:** HRIS `ACTIVE` là điều kiện cần cho nhân viên truy cập, nhưng không ghi đè `securityHold=true`.
4. **Thao tác ghi đè khẩn cấp phải có hạn sử dụng**, lý do, người phê duyệt, lịch sử và quy trình hòa giải lại với nguồn.
5. **Thiếu dữ liệu không có nghĩa dữ liệu đã bị xóa:** mất kết nối nguồn không được tự động hiểu là tất cả nhân viên đều đã nghỉ việc.

## 5. Kết nối nguồn với Joiner–Mover–Leaver

Một nguồn hữu ích cho IAM phải cung cấp **sự kiện có nghĩa nghiệp vụ**, không chỉ danh sách tài khoản hiện tại.

### Joiner — bắt đầu quan hệ

HRIS tạo bản ghi nhân viên với trạng thái hợp lệ, mã định danh và thời điểm bắt đầu. IAM xác minh các trường bắt buộc, tính thời điểm được cấp truy cập, tạo danh tính nội bộ, sau đó mới điều phối tài khoản IdP và quyền cơ sở. Ngày lập hồ sơ nhân sự có thể **sớm hơn ngày được phép truy cập**; hai thời điểm này không nên bị đồng nhất.

Ví dụ: hồ sơ được nhập ngày 01/06 nhưng ngày vào làm là 15/06. Quy trình có thể chuẩn bị tài khoản trước ngày 15/06 theo chính sách, nhưng trạng thái đăng nhập và quyền sử dụng hệ thống chỉ có hiệu lực vào thời điểm được phê duyệt.

### Mover — thay đổi quan hệ hoặc vai trò

Khi nguồn có thẩm quyền đổi `departmentId`, `managerId`, địa điểm, loại hợp đồng hoặc nhóm công việc, IAM phải tính lại điều kiện RBAC/ABAC. Mover không chỉ là “thêm quyền mới”: quyền cũ không còn hợp lệ cần được thu hồi, và quyền đặc biệt có thể phải phê duyệt lại.

Ví dụ: nhân viên chuyển từ bộ phận kế toán sang kỹ thuật. Trạng thái làm việc vẫn là `ACTIVE`, nhưng nhóm truy cập dữ liệu tài chính có thể phải được gỡ. Nên đánh giá chênh lệch quyền trước/sau thay đổi, xử lý quyền có rủi ro cao theo thứ tự kiểm soát phù hợp, sau đó đối soát quyền thực tế ở ứng dụng đích.

### Leaver — kết thúc hoặc mất điều kiện

Khi HRIS xác nhận nghỉ việc, hoặc hệ thống quản lý hợp đồng xác nhận hợp đồng nhà thầu đã hết hiệu lực, IAM phát hành yêu cầu thu hồi đăng nhập, phiên đăng nhập/token còn hiệu lực và quyền ứng dụng theo chính sách. Việc vô hiệu hóa truy cập phải **tách khỏi xóa hồ sơ**, vì hồ sơ có thể cần được giữ cho kiểm toán, pháp lý hoặc xử lý tái tuyển dụng.

Thông điệp Leaver cần phân biệt:

- **Nghỉ việc theo kế hoạch:** thời điểm hiệu lực rõ ràng, cho phép chuẩn bị hành động thu hồi.
- **Chấm dứt ngay lập tức:** sự kiện ưu tiên cao, cần kênh xử lý khẩn cấp và bằng chứng hoàn thành.
- **Nghỉ phép dài hạn hoặc tạm đình chỉ:** có thể yêu cầu trạng thái truy cập riêng; không tự đồng nhất với nghỉ việc.
- **Đổi loại quan hệ:** nhân viên chuyển thành nhà thầu có thể cần kết thúc một hồ sơ quan hệ và khởi tạo hồ sơ khác với quyền phù hợp.

Ngay cả khi một IdP ngăn đăng nhập thành công, token phiên cũ, khóa API, tài khoản cục bộ hoặc quyền trực tiếp tại ứng dụng vẫn có thể tồn tại. Vì vậy **khóa đăng nhập không chứng minh đã thu hồi toàn bộ quyền**. Cần đối soát entitlement và phiên/credential tại các hệ thống đích.

### Trạng thái nguồn khác trạng thái truy cập

Một mô hình tối giản có thể tính điều kiện truy cập nhân viên như sau:

~~~text
eligibleForAccess =
    employmentStatus == ACTIVE
    AND effectiveStart <= now
    AND (effectiveEnd is null OR now < effectiveEnd)
    AND securityHold == false
    AND mandatoryChecksPassed == true
~~~

Đây là **minh họa chính sách**, không phải công thức dùng nguyên xi cho mọi tổ chức. Tài khoản có thể còn cần MFA, phê duyệt, đánh giá rủi ro, giới hạn thời gian và chính sách của từng tài nguyên. Điều kiện trong nguồn chỉ là một phần của quyết định cấp quyền.

## 6. Kiến trúc tham chiếu cho luồng identity source

~~~mermaid
flowchart LR
    H["HRIS<br/>Nhân viên"] --> N["Tiếp nhận, xác minh<br/>và chuẩn hóa"]
    V["VMS / cổng đối tác<br/>Nhà thầu, đối tác"] --> N
    C["CIAM / đăng ký<br/>Khách hàng"] --> N
    W["Service catalog / Cloud<br/>Workload, service account"] --> N
    N --> R["Identity registry<br/>Khóa nguồn + nguồn thuộc tính"]
    R --> L["Lifecycle / IGA<br/>JML, chính sách, phê duyệt"]
    L --> I["IdP / Directory<br/>Đăng nhập, MFA"]
    I --> S["SSO<br/>OIDC / SAML"]
    L --> P["Provisioning<br/>SCIM / API"]
    P --> A["Ứng dụng / tài nguyên"]
    L --> D["Audit & reconciliation"]
    I --> D
    A --> D
~~~

Luồng này cho thấy nguồn dữ liệu **không bắt buộc phải trực tiếp tạo tài khoản trong từng ứng dụng**. Nguồn phát dữ kiện; lớp chuẩn hóa ghi rõ xuất xứ và thẩm quyền; bộ điều phối vòng đời đánh giá chính sách; IdP xác thực; SCIM/API cấp và thu hồi tài khoản tại đích; kiểm toán xác minh kết quả. Một sản phẩm thực tế có thể gộp vài thành phần vào một nền tảng, nhưng trách nhiệm logic vẫn cần được mô tả riêng.

SSO giúp giảm số lần đăng nhập; SCIM giúp đồng bộ tài khoản. Cả hai **không tự quyết định** một người đã nghỉ việc hay nhà thầu đã hết hợp đồng. Quyết định đó phải bắt nguồn từ dữ kiện vòng đời có thẩm quyền và chính sách IAM.

## 7. Thiết kế hợp đồng dữ liệu nguồn

Để kết nối một identity source, nhóm IAM cần thống nhất hợp đồng dữ liệu với owner của hệ thống nguồn. Hợp đồng tối thiểu gồm:

- **Danh tính nguồn:** tên hệ thống, owner nghiệp vụ/kỹ thuật, loại danh tính được phép phát hành và phạm vi tổ chức.
- **Khóa và liên kết:** ID bản ghi nguồn ổn định, quy tắc không tái sử dụng, ánh xạ tới identity ID nội bộ; quy trình sửa bản ghi trùng/ghép nhầm.
- **Thuộc tính:** schema, kiểu dữ liệu, trường bắt buộc, nguồn có thẩm quyền cho từng trường, yêu cầu kiểm tra tính hợp lệ.
- **Sự kiện và thời gian:** Joiner/Mover/Leaver, version hoặc sequence, thời điểm phát sinh, thời điểm hiệu lực, múi giờ, sự kiện xóa/khóa.
- **Vận hành:** cơ chế xác thực nguồn, tần suất phát sự kiện, SLA truyền nhận và xử lý, retry, kênh xử lý lỗi và đối soát toàn lượng.
- **Kiểm toán và riêng tư:** correlation ID, nhật ký thay đổi, mức dữ liệu cá nhân tối thiểu, giới hạn truy cập và chính sách lưu giữ.

Ví dụ hợp đồng cấu hình để thảo luận giữa HRIS và IAM:

~~~yaml
# Ví dụ minh họa, không phải schema bắt buộc của sản phẩm cụ thể
identityType: EMPLOYEE
source:
  system: HRIS
  ownerTeam: PeopleOperations
  recordKey: employeeId
  eventKey: eventId
  versionField: version
  effectiveAtField: effectiveAt
attributes:
  employeeId: HRIS
  employmentStatus: HRIS
  departmentId: HRIS
  managerId: HRIS
  preferredDisplayName: EmployeeProfile
controls:
  requireAuthenticatedSender: true
  rejectMissingRecordKey: true
  reconcileEvery: PT24H
  targetLeaverProcessing: PT15M
~~~

Giá trị `PT24H` và `PT15M` ở đây chỉ minh họa cách biểu diễn chu kỳ/SLA; thời hạn thực tế phải xuất phát từ đánh giá rủi ro và khả năng của hệ thống. Đặc biệt, kết thúc khẩn cấp có thể cần luồng ưu tiên nhanh hơn đồng bộ định kỳ.

### Hồ sơ danh tính chuẩn hóa

Một sự kiện sau khi chuẩn hóa có thể có dạng:

~~~json
{
  "identityId": "idn-7f1e",
  "identityType": "EMPLOYEE",
  "sourceRef": {
    "system": "HRIS",
    "recordId": "EMP-1042",
    "version": 17
  },
  "lifecycle": {
    "employmentStatus": "ACTIVE",
    "effectiveAt": "2026-06-15T00:00:00+07:00",
    "effectiveEnd": null
  },
  "attributes": {
    "departmentId": "ENG",
    "managerId": "EMP-1001"
  },
  "audit": {
    "correlationId": "evt-8b3d"
  }
}
~~~

Ở đây `identityId` là định danh nội bộ, còn `sourceRef` giữ dấu vết bản ghi gốc. Dữ liệu sử dụng mã phòng ban/người quản lý để tránh phụ thuộc vào chuỗi tên hiển thị có thể đổi. Các hệ thống đích có thể ánh xạ sang username, email hoặc group name riêng; các giá trị đó không thay thế khóa danh tính chuẩn.

## 8. Đồng bộ đáng tin cậy và kiểm soát chất lượng

Một identity source đúng vẫn có thể tạo rủi ro nếu sự kiện đến trễ, bị nhân đôi hoặc bị mất. Vì vậy cần thiết kế tiếp nhận dữ liệu như một quy trình có thể phục hồi.

**Xử lý sự kiện theo phiên bản và tính lặp an toàn (idempotency):**

~~~text
receive(event):
    verifySenderAndSchema(event)
    identity = lookupBySourceKey(event.sourceSystem, event.sourceRecordId)
    if event.id already processed:
        return ACK
    if event.version is stale relative to accepted source version:
        recordStaleEvent(event)
        return ACK
    validateAuthoritativeFields(event)
    updateOnlyFieldsOwnedBySource(identity, event)
    calculateLifecycleAndEntitlementChanges(identity)
    persistStateAndOutboxAtomically()
    deliverProvisioningActionsWithRetry()
    recordAuditAndCompletionStatus()
~~~

Đây là giả mã để chỉ ra các kiểm soát cần có. Nếu nguồn không cung cấp phiên bản tăng đơn điệu, phải thỏa thuận cơ chế thay thế như snapshot sequence hoặc event ordering có bảo đảm. Không thể dựa duy nhất vào thời gian máy nhận để quyết định sự kiện nào có hiệu lực nghiệp vụ; một thay đổi có thể được lên lịch cho tương lai.

**Đồng bộ sự kiện** giúp phản ứng nhanh khi nhân viên nghỉ việc hoặc đổi vai trò; **đối soát định kỳ** giúp tìm bản ghi/sự kiện bị bỏ sót và sai lệch giữa IAM, IdP và ứng dụng. Hai cơ chế bổ trợ nhau:

| Tình huống | Cách xử lý cần thiết |
|---|---|
| Một event Joiner được gửi hai lần | Không tạo hai identity; xác định bằng khóa nguồn và event ID. |
| Event Mover cũ đến sau event mới | Không ghi đè trạng thái mới nếu version/sequence đã lạc hậu. |
| Kết nối HRIS gián đoạn | Ghi nhận trễ và cảnh báo; hạn chế cấp quyền mới khi chưa xác minh; không vô hiệu hóa hàng loạt chỉ vì mất feed. |
| Hệ thống đích SCIM trả lỗi | Retry có kiểm soát, theo dõi hàng đợi và ticket ngoại lệ; coi thu hồi chưa hoàn tất đến khi có bằng chứng ở đích. |
| Ứng dụng có tài khoản không liên kết với nguồn | Phân loại orphan account, xác minh owner và xử lý theo chính sách; không tự ghép vào người có email trùng. |
| Sự kiện nghỉ việc khẩn cấp nhưng feed thường chậm | Cho phép kênh lệnh khẩn cấp đã xác thực, có thẩm quyền và kiểm toán; sau đó hòa giải với nguồn gốc. |

Đối với dữ liệu nhạy cảm, luồng đồng bộ nên dùng kết nối được xác thực, kiểm soát phạm vi truy cập và không ghi PII/credential không cần thiết vào log. Bản ghi kiểm toán cần trả lời được: ai hoặc hệ thống nào phát thay đổi, thay đổi thuộc tính nào, khi nào có hiệu lực, hệ thống nào đã thực thi, và bước nào chưa hoàn tất.

## 9. Ba tình huống thiết kế cần quyết định rõ

### Tình huống A — HRIS nói “Active”, IdP đang khóa bảo mật

Nhân viên vẫn có hợp đồng hợp lệ nhưng SOC đã khóa đăng nhập do nghi ngờ chiếm đoạt tài khoản. Một event HRIS cập nhật phòng ban đến sau đó.

**Quyết định:** HRIS chỉ cập nhật dữ kiện do HRIS sở hữu. IAM có thể tính lại nhóm quyền theo phòng ban, nhưng không được xóa `securityHold` hoặc tự bật đăng nhập. Chỉ quy trình bảo mật được phép gỡ lệnh khóa. Đây là lý do phải phân biệt *source of employment status* với *source of security restriction*.

### Tình huống B — Nhà thầu hết hợp đồng, SaaS vẫn còn tài khoản

VMS ghi nhận hợp đồng kết thúc lúc 18:00 ngày 30/09, nhưng một ứng dụng SaaS vẫn liệt kê nhà thầu là active vào ngày hôm sau.

**Quyết định:** thời điểm và trạng thái hợp đồng từ VMS kích hoạt Leaver; lớp IAM phát yêu cầu vô hiệu hóa và thu hồi quyền ở SaaS, kiểm tra kết quả và đưa lỗi vào hàng đợi xử lý. Trạng thái active ở SaaS là **sai lệch cần đối soát**, không phải căn cứ gia hạn hợp đồng.

### Tình huống C — Tài khoản dịch vụ mất chủ sở hữu

Một service account dùng cho tác vụ đồng bộ dữ liệu vẫn hoạt động sau khi kỹ sư phụ trách rời công ty. HRIS chỉ cho biết người đó đã nghỉ việc, không cho biết liệu workload còn cần tài khoản.

**Quyết định:** catalog dịch vụ hoặc hệ thống quản lý workload phải sở hữu thông tin service account, mục đích, owner, môi trường và thời điểm đánh giá lại. Khi owner nghỉ, IAM tạo sự kiện **rà soát/chuyển giao owner**; tùy rủi ro có thể cách ly hoặc thu hồi quyền, thay vì tự giả định tài khoản máy đã hết nhu cầu. Các credential gắn với người đã nghỉ phải được luân chuyển hoặc thay thế theo chính sách.

## 10. Cách xác định identity source cho một chương trình IAM

Có thể triển khai theo sáu bước, với đầu ra cụ thể ở từng bước:

1. **Lập inventory danh tính:** thống kê ứng dụng, directory, tài khoản cục bộ, tài khoản đặc quyền, người dùng bên ngoài và workload. Đầu ra là danh mục loại identity, hệ thống hiện chứa bản ghi và owner tương ứng.
2. **Tìm nguồn sự thật nghiệp vụ:** phỏng vấn HR, quản lý nhà thầu, đối tác, sản phẩm và chủ sở hữu dịch vụ. Kiểm tra ai có quyền xác nhận một quan hệ bắt đầu/kết thúc, không chỉ ai đang lưu bản sao dữ liệu.
3. **Chốt ma trận thẩm quyền:** lập bảng identity type × attribute × source × owner × rule. Giải quyết xung đột giữa HRIS, IdP và ứng dụng trước khi tự động hóa.
4. **Định nghĩa khóa định danh và hợp đồng sự kiện:** ID ổn định, mapping/correlation, version, ngày hiệu lực, xác thực nguồn, SLA, trường bắt buộc và trường hợp dữ liệu sai.
5. **Pilot một luồng JML có đo lường:** dùng nhóm nhân viên và một ứng dụng đích có khả năng kiểm tra, diễn tập Joiner, chuyển phòng ban, nghỉ việc và khóa khẩn cấp. Đo sự khác biệt giữa “đã gửi yêu cầu” và “đích đã thu hồi”.
6. **Mở rộng và đối soát liên tục:** bổ sung nhà thầu, đối tác, service account; vận hành cảnh báo, báo cáo chênh lệch, rà soát owner và quy trình xử lý orphan account.

### Hồ sơ quyết định nguồn cần lưu lại

Với mỗi identity source, nhóm thiết kế nên có bản ghi ít nhất gồm: tên nguồn và phạm vi, chủ sở hữu nghiệp vụ/kỹ thuật, loại danh tính, khóa bản ghi, các thuộc tính có thẩm quyền, sự kiện JML, độ trễ cho phép, quy tắc xung đột, đường xử lý lỗi, kế hoạch đối soát, căn cứ phê duyệt và ngày rà soát tiếp theo. Đây là tài liệu nền để đội IAM và chủ hệ thống ứng dụng trao đổi khi có sai lệch.

### Chỉ số kiểm chứng sau khi vận hành

| Chỉ số | Điều cần quan sát |
|---|---|
| **Authoritative coverage** | Tỷ lệ danh tính có nguồn, khóa nguồn và owner hợp lệ. |
| **Orphan identity count** | Tài khoản tại IdP/ứng dụng không gắn được với danh tính hoặc nguồn được công nhận. |
| **Leaver deprovision latency** | Thời gian từ mốc nghỉ việc có hiệu lực đến khi các quyền bắt buộc đã bị thu hồi ở đích; nên theo dõi percentile và trường hợp vi phạm SLA. |
| **Attribute conflict / stale event rate** | Tần suất tranh chấp dữ liệu, bản cập nhật sai thẩm quyền hoặc sự kiện lạc hậu. |
| **Reconciliation drift** | Số sai lệch giữa trạng thái mong muốn theo IAM và trạng thái thực tế ở IdP/ứng dụng. |
| **Ownerless service account count** | Tài khoản phi con người thiếu owner, mục đích sử dụng hoặc lịch rà soát. |

Những chỉ số này giúp đánh giá **chất lượng quyết định về nguồn** bằng kết quả vận hành. Tỷ lệ provisioning thành công cao chưa đủ nếu các trường hợp Leaver hoặc thu hồi đặc quyền vẫn tồn dư ở ứng dụng.

## 11. Sai lầm thường gặp

- **Chọn IdP là nguồn cho toàn bộ nhân viên vì “IdP có đủ username”.** Directory thường chứa bản sao thông tin nhân sự và có thể chưa cập nhật khi quan hệ lao động thay đổi.
- **Dùng email làm định danh chính.** Email có thể đổi, trùng hoặc được cấp lại; dùng khóa ổn định của nguồn và identity ID nội bộ.
- **Chỉ định một nguồn cho toàn bộ thuộc tính.** Trạng thái nhân sự, khóa bảo mật và quyết định phân quyền có owner khác nhau.
- **Chỉ đồng bộ thêm người mà không xử lý Mover/Leaver.** Hệ thống sẽ tích lũy quyền cũ dù tài khoản vẫn đăng nhập hợp lệ.
- **Tin rằng SCIM thành công là hoàn thành mọi thu hồi.** Một số quyền cục bộ, token, phiên và tài khoản phụ cần đường thu hồi/đối soát riêng.
- **Quên danh tính máy và tài khoản dịch vụ.** Các identity này có vòng đời riêng, phải có owner và chính sách hết hạn/luân chuyển.
- **Không ghi trạng thái thực thi và sai lệch.** Không thể chứng minh đã thu hồi nếu chỉ có log gửi event mà thiếu xác nhận từ hệ thống đích.

## 12. Bài tập áp dụng

Giả sử doanh nghiệp có: HRIS cho nhân viên, cổng quản lý hợp đồng cho nhà thầu, IdP hỗ trợ SSO, một ứng dụng SaaS hỗ trợ SCIM và một service account chạy tích hợp ban đêm.

Hãy xây dựng một **ma trận thẩm quyền** với năm thuộc tính: `employmentStatus`, `contractEndAt`, `departmentId`, `securityHold` và `serviceOwnerId`. Sau đó trả lời:

1. Hệ thống nào được phép thay đổi từng thuộc tính? Ai chịu trách nhiệm xác nhận khi dữ liệu sai?
2. Sự kiện nào kích hoạt Joiner, Mover và Leaver của nhân viên và nhà thầu? Thời điểm hiệu lực nằm ở đâu?
3. Khi HRIS trả `ACTIVE` nhưng IdP có `securityHold=true`, điều kiện truy cập cuối cùng nên xử lý thế nào?
4. Sau khi SaaS nhận yêu cầu vô hiệu hóa tài khoản, bạn cần bằng chứng nào mới kết luận quá trình Leaver hoàn tất?
5. Khi owner của service account nghỉ việc, nguồn nào cho biết service vẫn còn hoạt động và ai được phê duyệt chuyển giao?

**Tiêu chí hoàn thành:** mỗi loại danh tính có nguồn và owner rõ ràng; mỗi thuộc tính nhạy cảm có thẩm quyền xác định; mỗi sự kiện JML có khóa, thời điểm hiệu lực và quy tắc xung đột; trạng thái truy cập được phân biệt với trạng thái quan hệ; mỗi hành động cấp/thu hồi có đường kiểm chứng ở đích.

Khi các quyết định này đã rõ, tổ chức mới có cơ sở để thiết kế provisioning qua SCIM/API, chính sách RBAC/ABAC, kiểm soát đặc quyền và kiểm toán JML mà không để quyền truy cập tồn dư phát sinh từ một nguồn danh tính mơ hồ.
