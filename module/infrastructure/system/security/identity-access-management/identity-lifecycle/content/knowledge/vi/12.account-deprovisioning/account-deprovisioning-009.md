# Deprovisioning thất bại trong IAM: phát hiện, cô lập và khắc phục quyền tồn dư

> **Chương:** Account deprovisioning  
> **Bài:** Deprovisioning thất bại  
> **Module:** `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`  
> **Ngữ cảnh:** Quản lý vòng đời danh tính theo mô hình **Joiner–Mover–Leaver (JML)**, kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Bài toán: lệnh thu hồi đã gửi nhưng quyền vẫn còn

Trong một đợt nghỉ việc, bộ phận nhân sự xác nhận nhân viên Bình kết thúc hợp đồng lúc 18:00. Hệ thống IAM nhận sự kiện **Leaver**, khóa tài khoản tại Identity Provider (IdP) và yêu cầu các ứng dụng thu hồi quyền. Giao diện vận hành hiển thị “đã xử lý”, nhưng sáng hôm sau Bình vẫn truy cập được một ứng dụng SaaS bằng phiên đăng nhập còn hoạt động.

Tình huống này xảy ra khi tổ chức nhầm lẫn giữa ba mốc:

1. **Yêu cầu deprovisioning được tạo:** hệ thống đã biết cần ngừng quyền truy cập.
2. **Lệnh deprovisioning được gửi/nhận:** connector, API hoặc ticket đã phản hồi một trạng thái kỹ thuật.
3. **Quyền truy cập thực tế đã được chặn và xác minh:** không còn đường truy cập trái chính sách tại những đích liên quan.

Chỉ mốc thứ ba mới là bằng chứng phù hợp để kết luận một mục tiêu thu hồi quyền đã hoàn thành. Tùy nền tảng, có thể tồn tại phiên hoặc token chưa hết hạn, quyền gán trực tiếp, local account, API key, chứng chỉ hoặc ứng dụng không được connector quản lý.

**Deprovisioning thất bại** là tình huống hệ thống không đưa danh tính, tài khoản, quyền hoặc credential về **trạng thái đích đã được phê duyệt** đúng thời điểm, hoặc không thể xác minh trạng thái đó. “Thất bại” bao gồm lỗi rõ ràng và trạng thái **chưa xác nhận/không đầy đủ**; không chỉ là phản hồi HTTP lỗi.

### 1.1. Mục tiêu của bài học

Sau bài này, người học có thể:

- Phân biệt thất bại phát hiện sự kiện, truyền lệnh, thực thi, thu hồi phiên/token và đối soát.
- Xác định quyền tồn dư sau Leaver hoặc Mover tại IdP, SaaS, API, cloud, tài khoản dịch vụ.
- Xây dựng quy trình ưu tiên **chặn truy cập nguy hiểm**, rồi khôi phục và đối soát.
- Thiết kế retry an toàn, idempotency, dead-letter queue, escalation và trạng thái từng hệ thống đích.
- Hiểu giới hạn thực tế của SSO, SCIM, RBAC/ABAC, PAM/JIT và kiểm toán.
- Ghi bằng chứng rằng deprovisioning được **xác minh**, không chỉ “đã gửi”.

## 2. Điều gì thật sự phải được deprovision?

Không phải mọi hệ thống đều yêu cầu xóa vĩnh viễn account. Trạng thái đích có thể là **disabled**, **suspended**, **removed from role/group**, **revoked credential** hoặc **deleted**, tùy chính sách lưu giữ và phụ thuộc nghiệp vụ.

| Đối tượng | Trạng thái đích thường cần | Lỗ hổng khi bỏ sót |
|---|---|---|
| Danh tính tại IdP/directory | Chặn đăng nhập mới hoặc vô hiệu hóa theo ngày hiệu lực | Vẫn có thể lấy phiên/token mới qua IdP |
| Tài khoản tại SaaS/ứng dụng nội bộ | Disable hoặc hủy khả năng đăng nhập phù hợp | Local login có thể hoạt động ngoài SSO |
| Group, role, entitlement | Loại quyền không còn hợp lệ | Quyền dữ liệu hoặc đặc quyền vẫn tồn tại |
| Token, phiên, refresh token | Thu hồi/hết hạn theo cơ chế nền tảng | Vẫn truy cập trong phiên cũ |
| API key, khóa SSH, chứng chỉ | Thu hồi hoặc thay thế đúng phạm vi | Đường truy cập máy với máy không phụ thuộc mật khẩu user |
| PAM/JIT và phiên đặc quyền | Kết thúc quyền đang hoạt động và kiểm tra tại đích | Còn quyền quản trị sau thời điểm kết thúc |
| Quyền gán trực tiếp, tài khoản cục bộ | Thu hồi và đối soát riêng | Connector trung tâm không thấy quyền cấp tay |
| Workload/service identity | Chỉ thu hồi nếu workload kết thúc hoặc quyền không còn cần | Bot/tích hợp có thể tiếp tục dùng credential cũ |
| Quyền sở hữu tài nguyên/dữ liệu | Bàn giao theo quy định, không giữ quyền cá nhân để giữ dữ liệu | Không xử lý được hồ sơ nhưng lại giữ quyền của người nghỉ |

Một **Leaver của nhân viên** không mặc định là Leaver của mọi ứng dụng mà người đó từng quản lý. Cần chuyển owner của workload còn phục vụ nghiệp vụ, rồi thu hồi quyền cá nhân của nhân viên. Nếu workload cũng bị ngừng, phải thực hiện Leaver riêng cho service principal và credential của nó.

### 2.1. “Thu hồi thành công” được định nghĩa theo từng đích

Ví dụ chính sách cho một tài khoản SaaS:

~~~text
Target: finance-saas
Identity: employee-4012
Desired state:
  account.loginEnabled = false
  privilegedRoles = []
  directGrants = []
  refreshTokens = revoked_if_supported
  interactiveSessions = invalidated_or_expired_per_policy
  auditVerification = confirmed
~~~

Đây là mô hình minh họa, không phải cấu hình được hỗ trợ nguyên dạng ở mọi SaaS. Những thành phần không có API để truy vấn hoặc thu hồi trực tiếp cần được ghi rõ **giới hạn xác minh**, biện pháp thay thế và người chịu trách nhiệm theo dõi, thay vì ghi “đã chặn hết” một cách không có căn cứ.

## 3. Các nhóm nguyên nhân làm deprovisioning thất bại

Nhìn theo chuỗi sự kiện JML → IAM → provisioning connector → ứng dụng đích, thất bại có thể phát sinh ở nhiều lớp.

| Lớp | Dạng lỗi | Ví dụ | Hệ quả |
|---|---|---|---|
| **Nguồn sự kiện** | Leaver không được phát, phát muộn hoặc sai người | HRIS thiếu ngày kết thúc hợp đồng | Không có workflow thu hồi |
| **Liên kết identity** | Không ánh xạ đúng account đích | User đổi email nhưng mapping theo email cũ | Khóa nhầm hoặc bỏ sót account |
| **Chính sách** | Không liệt kê đủ target/entitlement | Ứng dụng được thêm ngoài danh mục IAM | Bỏ sót một con đường truy cập |
| **Hàng đợi/workflow** | Sự kiện bị kẹt, xử lý trùng, đến sai thứ tự | Mover cũ tới sau Leaver | Quyền có thể bị cấp lại |
| **Xác thực connector** | Token/khoá kết nối hết hạn hoặc mất quyền | SCIM token bị thu hồi | Không gửi được lệnh tới SaaS |
| **Kết nối/API** | Timeout, lỗi mạng, giới hạn tốc độ, HTTP 5xx | SaaS đang bảo trì hoặc trả 429 | Thu hồi chậm/không chắc lệnh đã áp dụng |
| **Đặc tính hệ thống đích** | Đã nhận lệnh nhưng áp dụng bất đồng bộ | SCIM trả thành công, user vẫn active | Chưa đạt trạng thái đích |
| **Quyền ngoài phạm vi** | Local role, direct grant, nested group | Một admin gán trực tiếp quyền cao | Thu hồi nguồn nhóm nhưng vẫn có quyền |
| **Phiên và credential** | Token còn hạn, session độc lập, API key riêng | User vẫn có token truy cập API | Account bị khóa nhưng đường truy cập cũ tồn tại |
| **Kiểm toán/đối soát** | Không readback hoặc báo trạng thái sai | Job đánh dấu COMPLETE ngay sau HTTP 200 | Thất bại bị ẩn |
| **Con người/quy trình** | Ticket thủ công bị bỏ quên, owner không rõ | Ứng dụng legacy không có người xác nhận | Rủi ro kéo dài không có người xử lý |

### 3.1. Ba dạng lỗi đặc biệt khó phát hiện

**Lỗi âm thầm (silent failure):** connector trả lời “success” nhưng ứng dụng không thực thi đúng entitlement hoặc áp dụng trễ. Cần đọc lại trạng thái và, ở nơi phù hợp, kiểm tra quyền hiệu lực.

**Lỗi một phần (partial failure):** 9 trong 10 hệ thống thu hồi thành công, một hệ thống vẫn hoạt động. Không được gộp toàn bộ job thành công chỉ vì tỷ lệ cao.

**Lỗi tái cấp quyền (reprovisioning after revoke):** job cũ hoặc policy động chạy lại và thêm user vào nhóm sau khi đã thu hồi. Đây là rủi ro cần kiểm soát bằng phiên bản sự kiện và trạng thái danh tính hiện hành.

## 4. Trạng thái workflow: gửi yêu cầu khác với hoàn tất

Trạng thái deprovisioning nên phản ánh được **từng ứng dụng và từng loại quyền**, không chỉ một cờ chung `completed=true`.

~~~mermaid
flowchart TD
    A[Leaver / Mover có hiệu lực] --> B[Xác minh identity và trạng thái đích]
    B --> C[Tạo kế hoạch revoke theo từng target]
    C --> D[Thực thi lệnh và ghi correlation ID]
    D --> E{Phản hồi / trạng thái đích?}
    E -- Lỗi tạm thời --> F[Retry có giới hạn và backoff]
    F --> D
    E -- Không rõ --> G[Readback và điều tra tính bất định]
    E -- Lỗi cố định --> H[Escalation tới owner / ứng cứu]
    E -- Nhận thành công --> I[Readback account, quyền, token nếu hỗ trợ]
    G --> I
    I --> J{Đã đạt trạng thái đích?}
    J -- Chưa --> H
    J -- Rồi --> K[VERIFIED từng target]
    H --> L[Containment, ticket, trạng thái PARTIAL]
    L --> M[Khắc phục, đối soát, hậu kiểm]
    M --> I
    K --> N{Tất cả target bắt buộc đã VERIFIED?}
    N -- Chưa --> L
    N -- Rồi --> O[Đóng sự kiện và lưu bằng chứng]
~~~

### 4.1. Bộ trạng thái tham khảo

| Trạng thái | Ý nghĩa |
|---|---|
| `REQUESTED` | Đã nhận yêu cầu/sự kiện và xác định thời điểm hiệu lực |
| `VALIDATED` | Đã xác minh identity, nguồn, target và chính sách |
| `DISPATCHED` | Lệnh đã được gửi; chưa kết luận trạng thái đích |
| `APPLYING` | Connector/target đang xử lý |
| `PENDING_VERIFICATION` | Phản hồi kỹ thuật đã có nhưng chưa kiểm chứng quyền thực tế |
| `PARTIAL` | Ít nhất một target chưa đạt trạng thái đích |
| `RETRY_SCHEDULED` | Lỗi được đánh giá có thể retry, đang chờ thực hiện lại |
| `ESCALATED` | Lỗi không tự hồi phục hoặc quá ngưỡng rủi ro/thời hạn |
| `VERIFIED` | Đích đã có bằng chứng trạng thái phù hợp |
| `CLOSED` | Tất cả target bắt buộc được xử lý theo điều kiện đóng và ngoại lệ đã được quản trị |

Bảng trên chỉ là mô hình nghiệp vụ. Không nên cho `CLOSED` đồng nghĩa với “đã có 200 OK”. Nếu ngoại lệ bắt buộc chưa thu hồi, trạng thái cuối phải phản ánh việc chấp nhận rủi ro có thẩm quyền, giới hạn thời gian và kế hoạch xử lý — không được giả là quyền đã biến mất.

### 4.2. Ví dụ một Leaver có nhiều trạng thái đích

| Hệ thống | Yêu cầu | Trạng thái hiện tại | Kết luận |
|---|---|---|---|
| IdP | Chặn đăng nhập mới | Đã đối soát disabled | `VERIFIED` |
| CRM | Khóa account và hạ role | Account disabled nhưng local admin role còn | `PARTIAL` |
| VPN | Thu hồi chứng chỉ/phiên | Không kết nối được connector | `ESCALATED` |
| SaaS quản lý dự án | Remove group | Đã nhận 2xx, chưa đọc lại | `PENDING_VERIFICATION` |

Sự kiện tổng chưa thể coi là hoàn tất. Với quyền VPN hoặc admin còn hiệu lực, mức ưu tiên xử lý có thể cao hơn một group quyền đọc thông thường; phân loại phải theo chính sách của tổ chức.

## 5. Quy trình xử lý ưu tiên khi deprovisioning thất bại

Không nên chờ connector tự phục hồi nếu quyền truy cập nguy hiểm vẫn mở. Hành động đúng phụ thuộc rủi ro và công nghệ, nhưng thường theo trình tự sau.

### 5.1. Bước 1: xác nhận sự kiện và mức độ ảnh hưởng

Xác minh:

- Identity ID ổn định, employee ID hoặc workload principal ID; không chỉ dựa vào email.
- Leaver hay Mover, thời điểm quyền phải hết hiệu lực và loại quyền cần thu hồi.
- Danh mục ứng dụng, group, direct grants, tài khoản cục bộ, secret/token và tài sản liên quan.
- Các target chưa đạt trạng thái đích; rủi ro đặc quyền, dữ liệu nhạy cảm, production.
- Lịch sử đăng nhập/truy cập sau mốc phải thu hồi, nếu có telemetry đáng tin.

Đối với quyền rất nhạy cảm còn hoạt động, coi đây có thể là **sự cố kiểm soát truy cập**, không chỉ là một ticket kỹ thuật chờ xử lý.

### 5.2. Bước 2: cô lập con đường truy cập có nguy cơ

Nếu cần ngăn truy cập ngay, có thể triển khai biện pháp phù hợp mà không phụ thuộc duy nhất vào connector lỗi:

- Vô hiệu hóa identity tại IdP để ngăn cấp phiên mới, đồng thời rà soát đường đăng nhập cục bộ.
- Thu hồi grant trực tiếp hoặc tài khoản ở giao diện quản trị ứng dụng đích nếu có thẩm quyền.
- Kết thúc session/refresh token hoặc hạn chế endpoint theo cơ chế của nền tảng.
- Thu hồi API key, chứng chỉ, khóa SSH hoặc credential đã bị liên kết với đối tượng phải ngừng.
- Vô hiệu hóa role đặc quyền, khóa session PAM hoặc chặn đường truy cập production phù hợp.
- Giới hạn truy cập API/tài nguyên tại điểm thực thi chính sách khi cần và được phê duyệt.

**Lưu ý:** khóa IdP thường không thể thu hồi tức thời mọi access token tự chứa đã được phát, mọi session của SaaS hoặc dữ liệu offline. Phải nắm giới hạn của từng hệ thống, thực hiện biện pháp bù trừ khi cần và ghi rõ rủi ro còn lại.

### 5.3. Bước 3: phân loại lỗi trước khi retry

Không retry mù quáng mọi phản hồi. Cần biết lỗi thuộc loại nào, thao tác trước có thể đã thực hiện chưa và việc chạy lại có an toàn không.

| Tình huống | Diễn giải thận trọng | Hướng xử lý |
|---|---|---|
| Timeout khi gửi yêu cầu | Không biết đích đã nhận lệnh chưa | Readback theo identity/target; retry idempotent nếu an toàn |
| HTTP 429 | Đích giới hạn lưu lượng | Tôn trọng chỉ dẫn retry/quota, dùng backoff và jitter |
| HTTP 5xx | Đích lỗi tạm thời hoặc xử lý không chắc chắn | Retry có giới hạn và xác minh |
| HTTP 401 | Credential connector không hợp lệ | Sửa xác thực/rotation; không retry liên tục với token sai |
| HTTP 403 | Connector thiếu quyền hoặc chính sách từ chối | Điều tra scope/role và owner phê duyệt |
| HTTP 404 | Tài nguyên không tìm thấy theo ID được hỏi | Xác minh mapping/account tồn tại ở ID khác; không mặc định “đã xóa” |
| HTTP 409 hoặc lỗi dữ liệu | Trùng trạng thái hoặc xung đột cập nhật tùy API | Kiểm tra hợp đồng provider, đọc lại phiên bản trạng thái |
| HTTP 2xx | API nhận/xử lý request theo hợp đồng | Vẫn readback hoặc chờ nhất quán eventual consistency |
| Job không có response | Workflow/hàng đợi mất liên kết hoặc bị treo | Kiểm tra correlation ID, retry policy và trạng thái ứng dụng |

Không có một ý nghĩa chuẩn duy nhất cho tất cả mã lỗi ở mọi connector. Phải đối chiếu tài liệu và hành vi thực tế của hệ thống đích.

### 5.4. Bước 4: xử lý nguyên nhân gốc và đối soát

Khôi phục connector, sửa mapping identity, cập nhật chính sách, xử lý direct grant/role local, hoặc chạy tác vụ được phê duyệt tại đích. Sau đó:

1. Đọc lại account status, membership, role, API grants, credential và session state khi hỗ trợ.
2. Xác minh thao tác nhạy cảm bị từ chối trong phạm vi kiểm thử được cho phép.
3. Ghi nhận thời điểm quyền thực sự bị chặn; không lấy thời điểm “lệnh gửi” thay cho thời điểm xác minh.
4. Đóng các ticket và ngoại lệ chỉ sau khi đạt tiêu chí rõ ràng.

### 5.5. Bước 5: hậu kiểm và phòng tái diễn

Điều tra vì sao sự cố không được phát hiện sớm, liệu các danh tính khác cùng connector có bị ảnh hưởng hay không và liệu sự kiện trễ có thể tái cấp quyền. Cập nhật runbook, cảnh báo, quyền của connector, giám sát và phương án kiểm tra chủ động.

## 6. SCIM và những lỗi deprovisioning thường gặp

**SCIM** hỗ trợ quản lý tài nguyên User/Group ở hệ thống tương thích và thường được dùng để đồng bộ trạng thái tài khoản hoặc membership. Tuy nhiên, SCIM không phải cơ chế thu hồi mọi token, phiên, ứng dụng, API key hoặc local role theo mặc định.

### 6.1. Vô hiệu hóa account qua SCIM

Một provider SCIM hỗ trợ thuộc tính `active` có thể nhận yêu cầu cập nhật như ví dụ bên dưới:

~~~http
PATCH /scim/v2/Users/abc-123 HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer <redacted-token>

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "Replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Đây là **minh họa** theo cấu trúc SCIM PATCH. Endpoint, ID và khả năng hỗ trợ thuộc tính/operation phải được kiểm tra ở provider. Không coi `active=false` là lệnh xóa toàn bộ dữ liệu hoặc hủy mọi phiên hiện hành trong mọi sản phẩm.

### 6.2. Ba lớp xác minh

1. **Lớp connector:** lệnh gửi thành công, response và correlation ID được ghi.
2. **Lớp đối tượng tại đích:** GET/readback thể hiện account đã inactive/disabled, role/group bị gỡ theo phạm vi trách nhiệm connector.
3. **Lớp quyền hiệu lực:** thao tác truy cập không hợp lệ bị chặn theo chính sách; những đường độc lập như local account hay token được xử lý riêng.

Có provider đồng bộ bất đồng bộ hoặc nhất quán sau một khoảng trễ. Khi readback chưa khớp ngay, workflow nên giữ `PENDING_VERIFICATION`, retry đọc theo thời hạn phù hợp và escalations khi vượt ngưỡng, không báo thành công quá sớm.

### 6.3. Lỗi mapping người dùng

Nếu IAM xác định người dùng bằng email `binh.old@example.org` còn hệ thống đích đã chuyển sang `binh.new@example.org`, một lệnh xóa theo tên cũ có thể tác động sai hoặc trả “not found”. Cần duy trì ánh xạ giữa **identity ID chuẩn** và **account ID bất biến hoặc ổn định của từng đích**, cùng quy trình kiểm tra account trùng.

Việc vô hiệu hóa nhầm tài khoản đang hoạt động là một sự cố khác, không được “sửa nhanh” bằng cách mở lại mọi account liên quan mà chưa xác minh đúng chủ thể.

### 6.4. Group và quyền ngoài phạm vi connector

SCIM cập nhật thành viên của một group nhưng ứng dụng có thể giữ quyền admin được gán trực tiếp. Một số connector chỉ hỗ trợ User/Group chứ không sửa role nội bộ hoặc API permission.

Vì vậy phải lập **bản đồ quyền tại đích**: quyền nào do SCIM quản lý, quyền nào do local admin hoặc API riêng quản lý, quyền nào được cấp qua cloud role, secret hoặc công cụ PAM.

## 7. SSO/IdP đã chặn nhưng ứng dụng vẫn truy cập được

SSO và deprovisioning xử lý những phần khác nhau của bài toán:

- **IdP/SSO:** xác thực người dùng và kiểm soát cấp phiên đăng nhập mới qua kênh liên kết.
- **Ứng dụng đích:** có thể giữ phiên đã tạo, quyền local, API token hoặc đường đăng nhập riêng.
- **Authorization tại API:** xét quyền trên thao tác/tài nguyên ở thời điểm yêu cầu, có thể dựa trên token, cache hoặc nguồn policy.
- **SCIM/connector:** đồng bộ account/group theo capability, không phải bộ thu hồi mọi thứ.

### 7.1. Phiên và token có tuổi thọ riêng

Một access token dạng JWT tự chứa có thể tiếp tục được API tin cậy cho đến khi hết hạn nếu API chỉ kiểm tra chữ ký/thời gian và không có cơ chế thu hồi phù hợp. Refresh token có thể bị thu hồi để ngăn nhận access token mới, nhưng **không đồng nghĩa access token đã phát hành bị vô hiệu tức thời**.

Tương tự, session cookie của SaaS có thể do SaaS tự quản lý. Khóa account tại IdP không nhất thiết xóa session đó ngay.

Các cơ chế giảm rủi ro có thể gồm:

- Token sống ngắn, hạn chế scope/audience và không cấp quyền rộng.
- Cơ chế introspection/kiểm tra trạng thái hoặc thu hồi session nếu nền tảng hỗ trợ.
- Thu hồi refresh token và session tại từng ứng dụng quan trọng.
- Kiểm tra trạng thái tài khoản/quyền trong API đối với hành động nhạy cảm.
- Chính sách truy cập lại/reauthentication và cảnh báo truy cập sau Leaver.

**Không giả định** nhà cung cấp nào cũng có API thu hồi token tức thời, và không khẳng định đã hết quyền nếu không thể xác minh giới hạn còn lại.

### 7.2. RBAC, ABAC và cache quyền

Khi xóa user khỏi group `finance-approver`, có thể gặp:

- RBAC role còn được cấp trực tiếp tại SaaS.
- Nested group khác tiếp tục mang lại role tương đương.
- ABAC attribute như `department=finance` chưa cập nhật trong hệ thống đích.
- Policy quyết định dựa trên cache thuộc tính hoặc claim được phát hành trước Mover.
- API không kiểm tra tình trạng account khi nhận request mang token cũ.

Cần kiểm tra **effective permissions**, không chỉ thành viên group ở một directory.

## 8. Deprovisioning thất bại trong Joiner–Mover–Leaver

### 8.1. Joiner: cấp nhầm và thu hồi sau khi phát hiện

Trong Joiner, một account có thể được tạo sai hoặc cấp quyền nhạy cảm trước thời điểm bắt đầu. Khi phát hiện sai, tổ chức cần quy trình thu hồi tương tự deprovisioning:

- Chặn quyền sai và xử lý session/credential đã cấp.
- Giữ lại quyền hợp lệ nếu danh tính đúng và nhân viên vẫn cần ứng dụng.
- Điều tra nguyên nhân nguồn dữ liệu, mapping group hoặc phê duyệt.
- Đối soát quyền trên hệ thống đích, không chỉ sửa rule provisioning.

Không tự động xóa toàn bộ danh tính khi chỉ có một entitlement cấp nhầm.

### 8.2. Mover: quyền cũ không được thu hồi

Một nhân viên chuyển từ tài chính sang vận hành có quyền mới nhưng vẫn giữ `payment.approve` từ vai trò cũ. Đây là **deprovisioning thất bại đối với quyền cũ** dù tài khoản user vẫn active.

Quy trình đúng là tính lại quyền kỳ vọng, thu hồi group/role/direct grant cũ, xử lý xung đột Separation of Duties (SoD), đối soát quyền thực tế và xử lý session/token có claim cũ nếu cần. Không coi Mover hoàn tất chỉ vì cấp được quyền mới.

### 8.3. Leaver: đứt một mắt xích có thể giữ lại đường truy cập

Với nhân viên nghỉ việc, mục tiêu thường là chặn các kênh truy cập còn khả dụng phù hợp thời điểm hiệu lực. Leaver có thể thất bại khi:

- HRIS không phát sự kiện đúng hạn.
- Identity ID không khớp tài khoản ở SaaS.
- Connector chỉ chạy vào ban đêm nhưng thời điểm nghỉ đã có hiệu lực.
- SaaS offline, khóa API provisioning hết hạn.
- Người dùng còn account local hoặc quyền qua bên thứ ba.
- API token/JIT session vẫn còn hiệu lực.
- Một pipeline cũ “đồng bộ lại” membership sau khi Leaver đã chặn.

**Leaver khẩn cấp** do chấm dứt quyền ngay có thể yêu cầu containment tại IdP và target quan trọng trước, sau đó hoàn tất đối soát toàn bộ hệ thống. SLA cần gắn với mức rủi ro và yêu cầu tổ chức, không suy ra từ một con số chung cho mọi trường hợp.

## 9. Thiết kế retry, idempotency và xử lý sự kiện sai thứ tự

### 9.1. Tại sao retry không đơn giản là “gửi lại”?

Một lệnh `DELETE` hoặc `PATCH` có thể đã được đích thực thi nhưng response bị mất. Nếu hệ thống chỉ đếm lỗi timeout rồi gửi lại không kiểm tra, thao tác có thể gây trùng, tác động nhầm hoặc làm lệch audit.

**Idempotency** giúp lặp lại cùng một thay đổi hướng tới trạng thái đích mà không tạo thêm quyền hay phản tác dụng. Thực tế cần xem capability provider và bảo đảm an toàn ở tầng workflow.

### 9.2. Thuật toán điều phối minh họa

~~~text
onDeprovisionEvent(event):
    assert verifySource(event)
    identity = resolveImmutableIdentityId(event.subjectId)

    if isStaleEvent(event, identity.currentLifecycleVersion):
        record("IGNORED_STALE_EVENT")
        return

    plan = computeDesiredState(identity, event, policyVersion)

    for each target in plan.targets:
        state = readTargetState(target, identity)

        if satisfiesTargetPolicy(state, plan[target]):
            markTarget(target, "VERIFIED")
            continue

        if requiresImmediateContainment(target, event.risk):
            triggerApprovedContainment(target, identity)

        result = applyIdempotentChange(target, plan[target], event.eventId)

        if result.isAmbiguous or result.isTransientFailure:
            scheduleBoundedRetryWithBackoff(target, event)
            markTarget(target, "PENDING_VERIFICATION")
        else if result.isPermanentFailure:
            markTarget(target, "ESCALATED")
            notifyTargetOwner(target)
        else:
            verify = readTargetState(target, identity)
            markTarget(target,
                "VERIFIED" if satisfiesTargetPolicy(verify, plan[target])
                else "PARTIAL")

    if allRequiredTargetsVerified(plan):
        closeCaseWithAuditEvidence(event)
    else:
        keepCaseOpenAndEscalateAsRequired(event)
~~~

Đây là **pseudocode**, không phải mã có thể dùng trực tiếp trong production. Đánh giá hiệu lực token/phiên, tính trạng thái mong muốn, rủi ro của quyền và thao tác containment cần chính sách/adapter phù hợp từng nền tảng.

### 9.3. Một số biện pháp kỹ thuật

- **Event ID/correlation ID:** nhận diện cùng một yêu cầu và ghép lệnh với phản hồi.
- **Lifecycle version:** không xử lý Mover/Joiner cũ nếu identity đã chuyển sang Leaver theo nguồn có thẩm quyền.
- **Desired-state reconciliation:** chạy lại đối soát để sửa drift thay vì chỉ phát lệnh một lần.
- **Exponential backoff với jitter:** tránh retry dồn dập khi API đang lỗi hoặc giới hạn tốc độ.
- **Giới hạn retry:** sau một ngưỡng, đưa vào dead-letter queue hoặc ticket điều tra, không để lỗi âm thầm vô hạn.
- **Phân biệt lỗi tạm thời/cố định:** lỗi quyền connector cần sửa scope/credential, không giải quyết bằng retry liên tục.
- **Cảnh báo quá hạn:** ưu tiên danh tính còn quyền nhạy cảm và những target không có bằng chứng.
- **Không tái cấp quyền trái chính sách:** retry grant cũ phải bị chặn sau Leaver.

### 9.4. Cần tách lỗi transport khỏi lỗi nghiệp vụ

Một API trả 200 có thể biểu thị request hợp lệ, nhưng account chưa vô hiệu hóa do xử lý bất đồng bộ. Một API trả timeout có thể đã áp dụng lệnh. Hệ thống không nên biến cả hai thành kết luận cố định mà thiếu readback.

## 10. Một case study: nghỉ việc, CRM khóa được nhưng VPN vẫn hoạt động

### 10.1. Bối cảnh

Công ty A có nhân viên kỹ thuật Minh. Minh nghỉ việc lúc 17:00. Minh dùng:

- IdP để SSO vào ứng dụng nghiệp vụ.
- CRM có đồng bộ User/Group qua SCIM.
- VPN cấp chứng chỉ riêng, được quản lý bởi hệ thống mạng.
- Cloud console với role tạm/PAM.
- Một API key từng được cấp để chạy script hỗ trợ.

Workflow Leaver khóa IdP và gửi yêu cầu SCIM thành công, nhưng connector VPN mất kết nối và script API key không được đưa vào inventory.

### 10.2. Dòng thời gian minh họa

| Thời điểm | Sự kiện | Điều quan sát | Vấn đề |
|---|---|---|---|
| 16:55 | Nhận sự kiện Leaver, hiệu lực 17:00 | Các target được xếp lịch | Chuẩn bị hợp lệ |
| 17:00 | IdP disable thành công | Không lấy được phiên IdP mới | Chỉ một lớp đã chặn |
| 17:01 | CRM phản hồi cập nhật user | Chưa đọc lại trạng thái user/role | Chưa đủ bằng chứng |
| 17:02 | VPN API timeout | Không biết chứng chỉ đã thu hồi chưa | Trạng thái bất định |
| 17:05 | Hệ thống audit phát hiện API key không có owner | Key còn được chấp nhận | Đường truy cập tồn dư |
| 17:07 | Security kích hoạt xử lý sự cố | Chặn key và thao tác thu hồi VPN có thẩm quyền | Containment |
| 17:15 | Đọc lại CRM và VPN | CRM disabled, VPN certificate revoked | Hai target đã xác minh |
| 17:20 | Kiểm tra key, PAM và session | Những quyền thuộc phạm vi Leaver được xử lý | Bắt đầu đóng sự kiện |

Các mốc chỉ minh họa quy trình, không phải SLA hay bảo đảm khả năng thu hồi của mọi nền tảng.

### 10.3. Điều gì làm quy trình này an toàn hơn?

1. Không kết luận Leaver hoàn tất khi IdP đã disable.
2. Danh mục target được lập theo **effective access** chứ không chỉ danh sách ứng dụng SSO.
3. VPN timeout được đánh dấu `PENDING_VERIFICATION`, không âm thầm bỏ qua.
4. API key có owner/nguồn cấp được xác minh và thu hồi theo quy trình riêng.
5. Đội xử lý sự cố có quyền áp dụng containment được phê duyệt.
6. Hệ thống đọc lại, lưu audit và chỉ đóng những target có bằng chứng.

### 10.4. Điều gì cần làm ở hậu kiểm?

- Bổ sung VPN và API key inventory vào phạm vi Leaver.
- Bổ sung health check connector, cảnh báo timeout và người chịu trách nhiệm.
- Kiểm tra các nhân viên nghỉ việc trước đó có gặp lỗi tương tự hay không.
- Đánh giá thời hạn token, cơ chế revoke session, local account và role quyền cao.
- Bổ sung reconciliation chạy định kỳ với trạng thái danh tính nguồn.
- Rà soát lại tài khoản dịch vụ/secret do Minh quản lý để bàn giao hoặc thu hồi.

## 11. Tài khoản dịch vụ và định danh phi con người cũng có thể deprovision thất bại

Không chỉ user account gặp vấn đề. Một job `etl-prod` ngừng vận hành nhưng vẫn giữ:

- Service principal trên cloud.
- Key hoặc certificate có hiệu lực.
- Quyền đọc database.
- API grant tại SaaS.
- Trust binding cho CI/CD hoặc workload federation.
- Quyền ghi vào hàng đợi và object storage.

Nếu chỉ xóa Deployment hoặc pipeline, các quyền đó có thể vẫn được cấp cho bất kỳ ai có khả năng sử dụng credential/trust liên quan.

### 11.1. Leaver của workload cần có nguồn kích hoạt riêng

Danh tính con người thường gắn với HRIS; workload cần nguồn như danh mục ứng dụng, thay đổi kiến trúc/deployment, yêu cầu owner hoặc quyết định ngừng dịch vụ. Workflow phải trả lời:

- Ai là owner kỹ thuật và owner nghiệp vụ?
- Dịch vụ thực sự ngừng hay chỉ chuyển đội/môi trường?
- Credential nào dùng trong thực tế, có các bản sao/phiên bản cũ không?
- Quyền cấp trực tiếp ở target có tồn tại không?
- Có workload khác đang dùng chung principal/key hay không?

Cấp chung một service identity cho nhiều ứng dụng làm thu hồi rủi ro hơn. Về lâu dài nên tách identity theo ranh giới tin cậy, môi trường và chức năng để việc deprovision không gây gián đoạn không cần thiết.

### 11.2. Mover của service principal

Một bot chuyển từ staging sang production có thể bị cấp thêm role prod mà không gỡ role staging hoặc trust cũ. Đây là quyền tồn dư do Mover. Cần rà soát policy, issuer/subject/audience của federation, secret/cert và thực tế truy cập. Không mặc định SCIM User/Group sẽ quản lý mọi service principal hoặc API key của cloud.

### 11.3. Giữ dịch vụ hoạt động khi owner nghỉ việc

Nếu kỹ sư sở hữu một service account nghỉ việc nhưng ứng dụng vẫn cần chạy, tổ chức phải **chuyển chủ sở hữu và thay đường quản trị cá nhân**, không xóa bừa principal của ứng dụng. Đồng thời phải thu hồi credential riêng của kỹ sư, quyền quản trị và những key cá nhân mà script có thể đang phụ thuộc. Thiếu bước bàn giao có thể biến deprovisioning thành nguyên nhân gián đoạn hệ thống.

## 12. Rà soát định kỳ để tìm deprovisioning bị bỏ sót

Không phải sai lệch nào cũng xuất hiện trong log lỗi. Nhiều quyền bị tồn dư vì **ứng dụng không có connector**, event không đến hoặc quyền được cấp thủ công.

### 12.1. Reconciliation từ nguồn có thẩm quyền

Một chương trình đối soát nên so sánh:

1. Danh sách identity đã Leaver hoặc Mover theo nguồn nghiệp vụ đáng tin.
2. Danh sách account, role, group, privilege, key và principal được quan sát từ các hệ thống đích.
3. Quyền **được phép tồn tại** theo policy, owner và thời điểm hiện tại.
4. Sai lệch giữa quyền thực tế và quyền kỳ vọng.
5. Kết quả xử lý sai lệch, kể cả ngoại lệ có phê duyệt và hạn hết hiệu lực.

Tập quyền hiệu lực có thể phức tạp vì group lồng nhau, role kế thừa, wildcard, deny policy hoặc attribute động. Không nên chỉ so sánh tên role bằng chuỗi rồi kết luận quyền tương đương.

### 12.2. Phát hiện account mồ côi và quyền tồn dư

Dấu hiệu có thể gồm:

- Tài khoản đích còn `active` nhưng identity nguồn đã `terminated`.
- User mất role nhưng ứng dụng còn direct grant hoặc session đặc quyền.
- Service account không có owner hợp lệ.
- API key không được dùng trong thời gian dài nhưng vẫn active và chưa có quyết định giữ lại.
- Group mapping đã xóa nhưng quyền cũ vẫn còn trên SaaS.
- Một identity có nhiều account tại một target, trong đó chỉ một account được khóa.
- Connector không có heartbeat, tỷ lệ lỗi tăng hoặc hàng đợi deprovisioning bị backlog.
- Truy cập API xảy ra **sau** thời điểm quyền phải bị thu hồi.

Không dùng “không có hoạt động đăng nhập gần đây” làm căn cứ duy nhất để xóa account: có job chạy theo quý hoặc tài khoản dự phòng được quản lý chính thức. Cần owner, purpose và quyết định có thẩm quyền.

### 12.3. Chế độ giám sát hậu Leaver

Với hệ thống có rủi ro cao, có thể giám sát dấu hiệu đăng nhập, phát token, API request hoặc dùng credential sau thời điểm Leaver, trong phạm vi telemetry và chính sách cho phép. Cảnh báo cần xác minh kênh truy cập thật sự, tránh nhầm sự kiện log đến muộn với một lần truy cập mới.

## 13. Audit trail: bằng chứng tối thiểu của một ca thất bại

Một bản ghi có thể cần:

- ID danh tính chuẩn; mã account và target tương ứng.
- Loại sự kiện JML, nguồn, phiên bản trạng thái và thời điểm hiệu lực.
- Quyết định/approval: ai yêu cầu thu hồi, ai duyệt, chính sách nào áp dụng.
- Desired state cho từng target và từng loại quyền.
- Thời điểm gửi lệnh, correlation ID, kết quả kỹ thuật, số lần retry.
- Thời điểm đọc lại trạng thái và dữ liệu xác minh tối thiểu.
- Trạng thái `VERIFIED`, `PARTIAL`, `ESCALATED`, lý do và owner.
- Containment và ngoại lệ có thời hạn nếu việc thu hồi chưa hoàn toàn khả thi.
- Thời điểm đóng case và dấu vết hậu kiểm.

Ví dụ JSON giả lập:

~~~json
{
  "caseId": "DEP-2026-0441",
  "identityId": "employee-4012",
  "lifecycleEvent": "LEAVER",
  "effectiveAt": "2026-11-23T17:00:00+07:00",
  "target": "vpn-service",
  "desiredState": {
    "accountEnabled": false,
    "credentialsRevoked": true
  },
  "execution": {
    "operation": "REVOKE_DEVICE_CERTIFICATE",
    "attempts": 2,
    "lastResult": "TIMEOUT"
  },
  "verification": {
    "status": "PENDING",
    "lastCheckedAt": "2026-11-23T17:07:00+07:00"
  },
  "containment": {
    "status": "APPLIED",
    "measure": "NETWORK_ACCESS_RESTRICTED"
  },
  "caseStatus": "ESCALATED",
  "owner": "network-security-team",
  "correlationId": "IAM-LEAVER-9042"
}
~~~

JSON là ví dụ, không phải schema bắt buộc. Giá trị `APPLIED` trong ví dụ chỉ có ý nghĩa khi hệ thống có bằng chứng biện pháp cô lập thật sự đã áp dụng. **Không ghi token, mật khẩu, private key hoặc nội dung nhạy cảm không cần thiết vào log.**

### 13.1. Không đánh đồng “accepted” và “revoked”

Nên phân biệt rõ:

- `ACCEPTED`: target nhận request.
- `APPLIED`: target cho biết thao tác được thực hiện theo hợp đồng API.
- `PENDING_VERIFICATION`: chưa có bằng chứng trạng thái đích.
- `CONFIRMED_REVOKED`: readback hoặc phép kiểm tra có cơ sở cho thấy quyền đã bị thu hồi.
- `UNVERIFIABLE`: công nghệ không hỗ trợ chứng minh trực tiếp; cần kiểm soát bù trừ và đánh giá rủi ro.

Việc nhảy thẳng từ `ACCEPTED` sang `CONFIRMED_REVOKED` mà không có dữ liệu kiểm tra là lỗ hổng kiểm toán.

## 14. Các chỉ số đánh giá deprovisioning bị lỗi

| Chỉ số | Ý nghĩa thực tế | Cách đọc thận trọng |
|---|---|---|
| **Time to block** | Thời gian từ hiệu lực Leaver đến khi con đường truy cập trọng yếu bị chặn | Phân biệt containment tạm với thu hồi cuối |
| **Time to verify** | Thời gian đến khi target đạt và xác minh trạng thái đích | Không lấy thời gian dispatch thay |
| **Deprovisioning success rate** | Tỷ lệ target/case đạt trạng thái yêu cầu | Xác định rõ mẫu số và đối tượng bị bỏ sót |
| **Residual access count** | Số tài khoản/quyền tồn dư ngoài chính sách | Phát hiện cả local grant và token khi có thể |
| **Partial failure rate** | Tỷ lệ workflow chỉ hoàn thành một phần | Không gộp PARTIAL vào SUCCESS |
| **Retry backlog / oldest pending** | Hàng đợi chậm hoặc bị kẹt | Ưu tiên case quá hạn có quyền nhạy cảm |
| **Orphaned account count** | Account không ánh xạ được identity/owner hợp lệ | Cần xác minh trước khi xóa |
| **Post-termination access signals** | Truy cập sau mốc hiệu lực | Phân biệt log trễ, sự kiện hợp lệ và hành vi đáng nghi |
| **Exceptions past due** | Ngoại lệ chưa được đóng đúng hạn | Có owner và thời điểm xử lý |

Mục tiêu SLA/SLO nên dựa trên loại tài nguyên, yêu cầu tổ chức và tác động rủi ro. Tài khoản quản trị production có thể cần phản ứng khác với quyền đọc tài liệu công khai; không có một con số phù hợp với mọi doanh nghiệp.

## 15. Những sai lầm nghiêm trọng và cách tránh

### “IdP đã disable nên Leaver hoàn tất”

Sai. SaaS có thể có phiên và local login riêng, ứng dụng có thể lưu token, quyền trực tiếp vẫn còn. Cần danh mục target và readback.

### “SCIM trả 200 OK thì không cần kiểm tra nữa”

Sai. Response xác nhận bước kỹ thuật theo hợp đồng API; trạng thái User, Group, role và session có thể khác hoặc cập nhật bất đồng bộ.

### “Cứ retry liên tục cho đến khi hết lỗi”

Không an toàn. Sai credential, sai ID hoặc chính sách từ chối không tự khỏi; retry không giới hạn có thể làm nghẽn hệ thống, mất dấu vết hoặc cấp lại quyền sai nếu event đến sai thứ tự.

### “HTTP 404 nghĩa là tài khoản chắc chắn đã bị xóa”

Chưa chắc. Có thể dùng sai account ID, sai tenant, sai endpoint hoặc người dùng có account thứ hai. Phải xác minh ánh xạ và tài nguyên thực tế.

### “Gỡ group nguồn là đủ”

Không đúng nếu target còn role local, direct grant, nested group hoặc claim token cũ. Cần kiểm tra effective access.

### “Xóa vĩnh viễn tài khoản là cách thu hồi tốt nhất”

Không phải lúc nào cũng vậy. Quy định lưu giữ, quyền sở hữu dữ liệu, hồ sơ kiểm toán và chuyển giao tài sản có thể yêu cầu giữ tài khoản ở trạng thái không thể truy cập. **Disable** và **delete** là hai quyết định khác nhau.

### “Không thể đọc lại trạng thái thì cứ đánh dấu VERIFIED”

Sai. Phải biểu diễn trạng thái chưa xác minh, cân nhắc biện pháp bù trừ, owner xử lý và hạn chót; không tạo bằng chứng không có thật.

### “Leaver của người viết script đồng nghĩa xóa mọi bot của họ”

Sai. Cần xác định workload còn phục vụ tổ chức không. Nếu còn, chuyển owner và credential phù hợp; đồng thời thu hồi quyền cá nhân, tránh để script phụ thuộc tài khoản người nghỉ việc.

## 16. Bài tập tình huống và đáp án phân tích

### Tình huống A: connector timeout sau khi gửi lệnh revoke

IAM gọi API vô hiệu hóa user; request timeout. Lần sau IAM định gửi cùng lệnh rồi đánh dấu đã xong.

**Phân tích:** Timeout không chứng minh lệnh chưa áp dụng. Cần đọc lại trạng thái trước hoặc sau retry; dùng thao tác đặt trạng thái idempotent và chỉ đánh dấu `VERIFIED` khi account/quyền thật sự đúng.

### Tình huống B: quyền cũ còn sau Mover

Lan chuyển từ nhóm kế toán sang kiểm toán. IAM gỡ `finance-approver` khỏi IdP, nhưng Lan vẫn có thể duyệt hóa đơn ở SaaS.

**Phân tích:** Kiểm tra direct grant, group khác, role local, cache, token/session và hỗ trợ SCIM. Mover còn `PARTIAL` cho đến khi thu hồi và xác minh quyền duyệt thực tế.

### Tình huống C: sự kiện cũ tái cấp quyền

Bình đã Leaver; một job đồng bộ bị trễ gửi lại sự kiện Joiner chứa group `sales-admin`. Nếu chỉ dựa vào sự kiện mới nhận, hệ thống có thể thêm quyền.

**Phân tích:** Cần đối chiếu lifecycle version, ngày hiệu lực và trạng thái hiện hành có thẩm quyền. Quy tắc deprovisioning phải chặn sự kiện cũ tái kích hoạt quyền.

### Tình huống D: SaaS chỉ có console, không có API readback

Một hệ thống legacy yêu cầu admin thao tác thủ công và không có API xác minh role.

**Phân tích:** Tạo ticket có người chịu trách nhiệm, bằng chứng thao tác/đối soát theo quy trình chấp nhận, người kiểm tra độc lập nếu mức rủi ro yêu cầu, và ghi rõ giới hạn của phép kiểm. Không gắn nhãn thu hồi tự động đã được chứng minh bằng một API không tồn tại.

### Tình huống E: API key không gắn với identity nghỉ việc

Một key được tạo từ lâu dưới tên `integration-prod`, nhưng kỹ sư nghỉ việc vẫn biết key. Chưa xác minh liệu dịch vụ khác cũng đang dùng key.

**Phân tích:** Điều tra owner, nơi sử dụng và phạm vi key; triển khai credential thay thế cho workload hợp lệ, thu hồi key có rủi ro theo kế hoạch phù hợp, tránh ngắt dịch vụ trái phép. Về lâu dài tách key/identity theo workload.

## 17. Checklist khép kín một ca deprovisioning thất bại

Trước khi báo một sự kiện JML đã xử lý xong, cần trả lời:

1. **Danh tính:** identity ID và ánh xạ tài khoản đích đã chính xác, tránh nhầm người chưa?
2. **Nguồn và thời điểm:** sự kiện Leaver/Mover có thẩm quyền, ngày hiệu lực và phiên bản trạng thái đúng chưa?
3. **Phạm vi:** đã liệt kê IdP, SaaS, ứng dụng nội bộ, cloud, VPN, local account, service principal, API key và quyền chia sẻ liên quan chưa?
4. **Desired state:** từng target phải disabled, hạ quyền, revoke token/key hay giữ dữ liệu ở trạng thái không thể truy cập?
5. **Containment:** quyền đặc quyền hoặc đường truy cập nguy hiểm đã được hạn chế kịp thời chưa?
6. **Connector:** lỗi có được phân loại đúng, sửa credential/mapping/quota, retry theo khả năng hệ thống không?
7. **Thứ tự sự kiện:** workflow có tránh nhận lại sự kiện cũ và tái cấp quyền sau Leaver không?
8. **SCIM/SSO:** đã tách provisioning account khỏi xác thực và xử lý phiên/token chưa?
9. **Quyền tồn dư:** đã xét direct grant, nested group, role local, RBAC/ABAC, session và PAM/JIT chưa?
10. **Workload:** tài khoản dịch vụ/người quản lý bot đã được bàn giao hoặc thu hồi đúng trạng thái nghiệp vụ chưa?
11. **Readback:** có bằng chứng quyền thực tế tại hệ thống đích đúng chính sách hay vẫn là PENDING/PARTIAL?
12. **Audit:** có event ID, approval, lệnh, lỗi, biện pháp cô lập, người chịu trách nhiệm và thời điểm xác minh?
13. **Escalation:** case chưa đóng có owner, hạn xử lý, cảnh báo và biện pháp kiểm soát bù trừ?
14. **Phòng tái diễn:** đã cải thiện danh mục target, reconciliation, monitoring và quy trình xử lý sai lệch chưa?

---

**Ghi nhớ:** Deprovisioning thành công không chỉ là **gửi lệnh xóa hoặc khóa account**, mà là đưa danh tính và các con đường truy cập về trạng thái được phép, rồi **xác minh hiệu lực tại hệ thống đích**. Khi deprovisioning thất bại, phải nhận diện tác động, cô lập quyền nguy hiểm, xử lý retry/idempotency và đối soát IdP–SCIM–SSO–ứng dụng, bao gồm RBAC/ABAC, phiên/token và tài khoản dịch vụ. Quản lý trạng thái `PARTIAL`/ `ESCALATED` trung thực và có bằng chứng là nền tảng để giảm quyền truy cập tồn dư trong vòng đời Joiner–Mover–Leaver.
