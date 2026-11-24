# Provisioning thất bại trong quản lý vòng đời danh tính IAM

## 1. Provisioning thất bại là gì?

**Account provisioning** là quá trình tạo, liên kết, cập nhật hoặc cấp quyền cho tài khoản trên một hay nhiều hệ thống đích dựa trên danh tính và quyết định truy cập hợp lệ. Trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, provisioning liên kết sự kiện **Joiner–Mover–Leaver (JML)** với **nguồn danh tính, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và việc giảm quyền truy cập tồn dư**.

**Provisioning thất bại** (*provisioning failure*) xảy ra khi kết quả yêu cầu tại hệ thống đích **không đạt trạng thái mong muốn** trong phạm vi và thời hạn đã quy định. Một yêu cầu có thể bị từ chối ngay, bị lỗi sau khi bắt đầu, bị kẹt ở hàng đợi hoặc có phản hồi thành công nhưng trạng thái thực tế vẫn sai.

Ví dụ: HRIS gửi sự kiện nhận nhân viên mới. IAM tạo được tài khoản tại IdP và đồng bộ được thông tin người dùng sang một ứng dụng SaaS, nhưng thao tác gán nhóm cấp quyền vào ứng dụng bị lỗi. Người dùng có tài khoản và đăng nhập được bằng SSO, song **chưa thể thực hiện công việc** vì thiếu quyền ứng dụng. Ngược lại, khi một nhân viên nghỉ việc, IAM có thể khóa đăng nhập IdP thành công nhưng không thu hồi được tài khoản local tại ứng dụng cũ. Đây là thất bại đặc biệt nguy hiểm vì **quyền truy cập tồn dư** có thể vẫn còn hoạt động.

Điểm cốt lõi là phân biệt **lệnh đã gửi**, **đích đã nhận**, **đích thực thi**, và **đích đã được đối soát đúng**. Không nên dựa vào một thông báo HTTP thành công, một job có trạng thái DONE hoặc việc gửi email xác nhận để kết luận toàn bộ provisioning đã hoàn tất.

### Trạng thái cần phân biệt

| Trạng thái | Ý nghĩa | Có thể coi là hoàn tất? |
|---|---|---|
| **Requested** | Đã có yêu cầu từ workflow nghiệp vụ | Chưa |
| **Validated** | Nguồn, chủ thể, chính sách và yêu cầu hợp lệ | Chưa |
| **Dispatched** | Đã gửi yêu cầu đến connector hoặc API đích | Chưa |
| **Acknowledged** | Hệ thống đích xác nhận tiếp nhận/phản hồi | Chưa chắc |
| **Applied** | Thay đổi được hệ thống đích báo đã áp dụng | Cần xác minh theo rủi ro |
| **Verified** | Readback/đối soát xác nhận trạng thái thực tế đạt mong muốn | Có, cho hạng mục đã kiểm tra |
| **Retryable failure** | Lỗi có khả năng phục hồi an toàn | Chưa |
| **Permanent/policy failure** | Yêu cầu hoặc chính sách cần sửa, không nên thử lại y nguyên | Chưa |
| **Partially completed** | Một số đích hoặc bước thành công, phần khác lỗi | Chưa hoàn tất toàn bộ |

Một workflow có thể chứa nhiều hạng mục ở các trạng thái khác nhau. Vì vậy, cần theo dõi **trạng thái riêng của từng tài khoản, nhóm, quyền, credential và hệ thống đích**.

## 2. Provisioning có thể thất bại ở những lớp nào?

Quy trình provisioning thường đi qua nhiều thành phần. Lỗi ở mỗi lớp đòi hỏi cách khắc phục khác nhau.

~~~mermaid
flowchart TD
    H[HRIS / quản lý nhà thầu / nguồn danh tính] --> E[Sự kiện Joiner / Mover / Leaver]
    E --> V[IAM / IGA: xác minh và đối chiếu identity]
    V --> P[RBAC / ABAC / phê duyệt / SoD]
    P --> O[Orchestrator: kế hoạch provisioning]
    O --> IDP[IdP / directory]
    O --> SCIM[SCIM / API connector]
    O --> LEGACY[Ứng dụng legacy / ticket thủ công]
    IDP --> R[Readback / account reconciliation]
    SCIM --> R
    LEGACY --> R
    R --> D{Thực tế đạt mục tiêu?}
    D -->|Có| PASS[Verified / hoàn tất hạng mục]
    D -->|Không| F[Phân loại lỗi / retry / cảnh báo]
    F --> O
~~~

| Lớp lỗi | Tình huống ví dụ | Tác động |
|---|---|---|
| **Nguồn danh tính** | HRIS không gửi sự kiện hoặc dữ liệu sai nhân sự | Workflow không chạy hoặc chạy nhầm người |
| **Đối chiếu danh tính** | Không tìm được khóa người dùng; trùng email | Có thể tạo tài khoản trùng, nhầm hoặc không tạo được |
| **Chính sách quyền** | Role mapping sai, thiếu phê duyệt, xung đột SoD | Quyền cần thiết không được cấp hoặc bị từ chối đúng chính sách |
| **Orchestrator** | Sự kiện sai thứ tự, job mất, timeout, deadlock | Trạng thái workflow bị kẹt hoặc ghi sai |
| **Kết nối/ủy quyền** | SCIM token hết hạn, scope API thiếu, TLS lỗi | Không liên lạc hoặc không được phép sửa đích |
| **Schema/dữ liệu** | Thiếu trường bắt buộc, thuộc tính không hỗ trợ, giá trị xung đột | API từ chối hoặc dữ liệu đồng bộ sai |
| **Hệ thống đích** | Rate limit, không sẵn sàng, kiểm tra định dạng khác dự kiến | Cập nhật trễ hoặc thất bại |
| **Quyền/entitlement** | User được tạo nhưng thiếu nhóm, license, role | Tài khoản hiện hữu nhưng chưa đáp ứng nhu cầu |
| **Đối soát** | Phản hồi thành công nhưng readback cho trạng thái khác | Sai lệch kéo dài mà monitoring không phát hiện |
| **Thủ công/legacy** | Ticket chưa ai nhận, chưa có xác nhận khóa account | Không có bằng chứng kết thúc |

Không phải lỗi nào cũng là sự cố bảo mật. Một yêu cầu bị từ chối vì **SoD** hoặc vì người dùng chưa được phê duyệt đặc quyền có thể cho thấy **kiểm soát đang hoạt động đúng**. Vấn đề cần giải quyết là workflow phải biểu diễn và thông báo trạng thái đó chính xác.

## 3. Những biểu hiện thường gặp của provisioning thất bại

### 3.1. Không tạo được tài khoản

Ví dụ connector nhận yêu cầu tạo người dùng nhưng thiếu thuộc tính cần thiết hoặc vi phạm quy tắc định danh của đích. Kết quả: account chưa tồn tại. Nếu hệ thống đầu nguồn vẫn ghi “đã tạo”, người dùng sẽ gặp lỗi khi đăng nhập ứng dụng.

### 3.2. Tạo được account nhưng chưa đủ quyền

SCIM có thể tạo **User** thành công, trong khi cập nhật **Group** hoặc role qua API riêng bị lỗi. Đây là **thất bại một phần**. Chỉ kiểm tra sự tồn tại của người dùng không đủ; cần đọc lại entitlement thực tế.

### 3.3. Tạo nhiều account cho cùng danh tính

Một yêu cầu bị timeout sau khi đích đã tạo thành công. Orchestrator không có idempotency nên gửi lại **POST tạo account** và tạo trùng. Khi liên kết sai account, Mover/Leaver sau đó có thể bỏ sót một account còn quyền.

### 3.4. Cập nhật bị ghi đè do sự kiện cũ

Nhân viên chuyển từ vai trò A sang B; một job cập nhật A đến muộn và áp lại quyền cũ. Điều này có thể dẫn đến **privilege accumulation** hoặc quyền sai. Không nên giải quyết chỉ bằng cách retry liên tục; phải kiểm tra phiên bản nguồn và trạng thái hiện hành.

### 3.5. Thu hồi chưa hết hoặc phản hồi sai lệch

Leaver khóa IdP thành công, nhưng refresh token ứng dụng, khóa API, tài khoản local hoặc phiên VPN vẫn còn. Nếu orchestration chỉ ghi trạng thái từ IdP, **quyền truy cập tồn dư** bị che giấu. Tình huống này cần ưu tiên an ninh cao hơn lỗi cấp quyền thông thường.

### 3.6. Thất bại trong chuyển giao/owner

Tài khoản của người nghỉ sở hữu repository, dashboard, lịch tự động hoặc một service account. Việc xóa account trước khi bàn giao gây mất chủ tài nguyên; nếu bỏ qua bước này và giữ nguyên quyền cũ quá lâu, lại tạo rủi ro bảo mật. Cần xử lý **owner/resource lifecycle** như một hạng mục rõ ràng.

## 4. Phân loại lỗi: tạm thời, vĩnh viễn và xung đột chính sách

Nhận diện đúng loại lỗi giúp quyết định **retry**, **sửa dữ liệu**, **yêu cầu phê duyệt** hay **khẩn cấp chặn truy cập**.

| Nhóm lỗi | Dấu hiệu | Hướng xử lý |
|---|---|---|
| **Transient/network** | Timeout, reset kết nối, lỗi DNS/tạm mất mạng | Retry có backoff; xác minh trạng thái đích trước khi tạo lại |
| **Throttling/quota** | Rate limit hoặc vượt giới hạn được phép | Chờ theo tín hiệu server, giảm tốc, chia tải |
| **Authentication to target** | Credential connector hết hạn hoặc không hợp lệ | Khôi phục credential trong secret manager; cảnh báo owner |
| **Authorization to target** | Connector không đủ quyền ghi user/group | Sửa scope/quyền sau phê duyệt, không tự tăng đặc quyền |
| **Validation/schema** | Thiếu trường, sai loại, thuộc tính đích không chấp nhận | Sửa mapping/nguồn, không retry y nguyên |
| **Conflict** | Duplicate identifier, account đã tồn tại, version mismatch | Tra cứu và đối chiếu đúng thực thể; tránh tạo trùng |
| **Policy/business** | Phê duyệt bị từ chối, quyền xung đột SoD | Giữ trạng thái pending/denied; không bypass chính sách |
| **Unsupported capability** | Connector không hỗ trợ PATCH, nhóm nested hoặc một entitlement | Chọn tích hợp phù hợp hoặc quy trình thủ công có kiểm soát |
| **Partial success** | User tạo xong nhưng group hoặc token chưa xử lý | Tiếp tục theo trạng thái từng bước, đối soát từng quyền |
| **Unknown outcome** | Yêu cầu timeout sau khi gửi; không biết đích đã thay đổi chưa | **Read-after-timeout** trước khi retry thao tác không idempotent |

Một lỗi **chưa biết kết quả** không nên lập tức được gọi là **thất bại vĩnh viễn**. Có thể hệ thống đích đã xử lý xong nhưng response bị mất. Ngược lại, response 2xx cũng không tự bảo đảm mọi bước downstream đã đạt trạng thái cần thiết.

### Quy tắc triage

- **Có thể thử lại an toàn:** lỗi hạ tầng tạm thời, miễn mỗi lần retry không gây tác dụng phụ sai.
- **Phải sửa trước khi thử lại:** lỗi schema, định danh trùng, thiếu quyền connector, chính sách từ chối.
- **Phải kiểm tra trước khi làm lại:** timeout/unknown outcome, sự kiện đến muộn, kết quả không nhất quán.
- **Phải xử lý khẩn:** còn truy cập sau mốc Leaver hoặc quyền nhạy cảm bị cấp trái chính sách.

## 5. Lỗi thường gặp khi dùng SCIM 2.0 và HTTP API

**SCIM** (*System for Cross-domain Identity Management*) là giao thức chuẩn hỗ trợ quản lý các đối tượng như **User** và **Group** giữa provisioning client và service provider. SCIM không tự định nghĩa mọi entitlement ứng dụng, không thay thế chính sách RBAC/ABAC và cũng không bảo đảm mọi dịch vụ hỗ trợ mọi khả năng như nhau.

Mỗi connector cần kiểm tra **schema**, khả năng endpoint và cách diễn giải trạng thái của ứng dụng đích. Bảng dưới minh họa nhóm phản hồi HTTP thường gặp trong tích hợp SCIM/API; cần đọc body lỗi và tài liệu thực tế để xác định nguyên nhân.

| Phản hồi | Ý nghĩa thường gặp | Cách tiếp cận |
|---|---|---|
| **400 Bad Request** | Payload, filter, đường dẫn, giá trị hoặc schema không hợp lệ | Xem validation và mapping; không retry y nguyên |
| **401 Unauthorized** | Xác thực của client gọi API thất bại | Kiểm tra credential/token connector, cấu hình xác thực |
| **403 Forbidden** | Client không có đủ quyền thực hiện thao tác | Kiểm tra scope/role tại đích, quy trình cấp quyền connector |
| **404 Not Found** | Đối tượng hoặc endpoint không tìm thấy | Đối chiếu external ID/target ID; nhận diện account đã mất hoặc route sai |
| **409 Conflict** | Xung đột trạng thái hoặc ràng buộc duy nhất | Tìm account tương ứng, hòa giải dữ liệu, tránh tạo trùng |
| **412 Precondition Failed** | Điều kiện phiên bản khi dùng ETag/If-Match không còn đúng | Readback phiên bản mới rồi đánh giá lại thay đổi |
| **429 Too Many Requests** | Bị giới hạn tần suất theo đích | Backoff và tôn trọng Retry-After nếu được trả |
| **5xx** | Lỗi phía hệ thống đích hoặc gateway | Retry có giới hạn, theo dõi trạng thái sau lỗi và escalation |

**Không phải mọi phản hồi 4xx đều có cùng ngữ nghĩa**, và không phải mọi API ngoài SCIM đều trả những mã như trên. Đặc biệt, 404 có thể là một hệ quả hợp lệ khi thao tác thu hồi đã xảy ra trước đó; nhưng không nên tự ghi SUCCESS nếu chưa xác nhận đúng tài khoản, đúng scope và trạng thái đích.

### Ví dụ SCIM PATCH thay đổi trạng thái

Request body minh họa cập nhật thuộc tính **active** của đối tượng User:

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "Replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Điều này minh họa **nội dung thay đổi**, không phải giao dịch hoàn chỉnh. Đích phải hỗ trợ endpoint và thuộc tính tương ứng, client phải gửi định danh đối tượng và thông tin xác thực hợp lệ. Từng dịch vụ có thể xử lý việc **active=false**, session, token và xóa dữ liệu khác nhau. **Deactivation account không tự đồng nghĩa tất cả phiên/token đều đã mất hiệu lực.**

### Ví dụ tạo User bị trùng

Một account đã tồn tại theo định danh bên ngoài nhưng orchestrator không lưu ID đích. Gửi thêm POST tạo User có thể dẫn đến **409 Conflict** hoặc tạo một tài khoản gần giống nếu ràng buộc đích lỏng lẻo. Cách xử lý là **tra cứu và xác minh account hiện có** thông qua khóa liên kết đáng tin cậy, chỉ cập nhật sau khi chứng minh đó đúng chủ thể; không lấy email trùng làm bằng chứng duy nhất.

## 6. Nguyên nhân sâu xa: sai dữ liệu danh tính và quyền

Lỗi provisioning không phải lúc nào nằm ở API. **Dữ liệu nguồn, quan hệ định danh và chính sách phân quyền** thường là gốc của sai lệch.

### 6.1. Khóa định danh không ổn định

Tên người, email và tên đăng nhập có thể đổi. Khi người dùng đổi tên hoặc tái gia nhập, connector chỉ dựa email có thể tạo mới sai hoặc gắn vào account không đúng. Hệ thống nên có **identity ID bền vững**, bản ghi mapping **source identity ↔ target account ID** và quy trình giải quyết trùng hợp lệ.

### 6.2. Thiếu thuộc tính mà đích yêu cầu

Ứng dụng đích có thể yêu cầu giá trị không xuất hiện trong HRIS, chẳng hạn location code hoặc tên đơn vị theo danh mục. Nếu mapping tự chế giá trị mặc định sai, kết quả có thể là account được tạo nhưng quyền không đúng. Cần **kiểm tra tính đầy đủ và nguồn gốc thuộc tính trước khi gửi**.

### 6.3. Role mapping khác nhau giữa các ứng dụng

Một role trong IAM có thể ánh xạ tới nhiều group/entitlement ở SaaS, database và cloud. Nếu một hệ thống thay tên role hoặc yêu cầu license, provisioning có thể thất bại dù các bước khác thành công. Cần version hóa policy/mapping và theo dõi quyền **được yêu cầu – được cấp – được xác nhận**.

### 6.4. Thiếu phê duyệt hoặc xung đột SoD

Quyền được yêu cầu có thể vượt baseline và cần phê duyệt. Nếu xung đột **Segregation of Duties (SoD)**, việc từ chối là mong muốn. Workflow không nên tự giảm yêu cầu mà vẫn ghi “đủ mọi quyền”, càng không được tăng đặc quyền cho connector để vượt policy.

### 6.5. Dữ liệu đã thay đổi trước khi tác vụ chạy

Một job Joiner được tạo trước ngày bắt đầu nhưng nhân sự sau đó đổi bộ phận hoặc quyết định gia nhập bị hủy. Khi job chạy, thông tin cũ đã lỗi thời. Cần đối chiếu **version và trạng thái nguồn hiện hành ngay trước các thao tác có tác động lớn**.

## 7. Thất bại một phần và vấn đề tính nhất quán

Provisioning xuyên nhiều hệ thống thường là **workflow phân tán**, không phải một giao dịch ACID duy nhất. Một bước có thể thành công và bước khác lỗi.

Ví dụ cùng một yêu cầu Joiner:

| Thành phần | Trạng thái | Hệ quả |
|---|---|---|
| IdP user | **Verified** | Có đối tượng danh tính trung tâm |
| Đăng ký MFA bắt buộc | **Pending** | Chưa đủ điều kiện mở một số truy cập |
| SaaS User | **Verified** | Tài khoản ứng dụng đã tồn tại |
| SaaS Group | **Failed** | Chưa có quyền chức năng |
| VPN role | **Not requested** | Không thuộc baseline, không phải lỗi |
| Workflow tổng | **Partially completed** | Chưa thể tuyên bố sẵn sàng làm việc |

Một chiến lược khôi phục cần giữ lại **những bước hợp lệ đã hoàn tất**, thử lại hoặc bù trừ những bước còn thiếu theo rủi ro, và tránh vô tình xóa dữ liệu cần thiết.

### Khi nào cần bù trừ?

Nếu account mới được tạo nhưng bước proofing/phê duyệt bắt buộc bị từ chối, có thể phải **khóa hoặc thu hồi account tạm** để tránh tạo đường truy cập ngoài ý muốn. Nhưng khi ứng dụng tạm lỗi gán nhóm, **xóa rồi tạo lại toàn bộ người dùng** có thể làm mất dữ liệu, trùng account hoặc hỏng liên kết. Cách bù trừ phải được quy định theo **loại thao tác, trạng thái đích và nhu cầu nghiệp vụ**.

### Những bất biến quan trọng

1. Không mở quyền cao hơn quyền đã được chính sách và phê duyệt chấp thuận.
2. Không chấp nhận **Mover** thêm quyền mới mà âm thầm bỏ qua thu hồi quyền cũ nhạy cảm.
3. Không đánh dấu **Leaver closed** khi còn đường truy cập thuộc phạm vi chưa được xác minh và xử lý.
4. Không liên kết user với target account chỉ dựa trên thuộc tính có thể trùng/thay đổi.
5. Không cho một sự kiện cũ hoặc retry tự động **tái kích hoạt** tài khoản đã Leaver.
6. Không coi sự tồn tại của tài khoản là bằng chứng đầy đủ các entitlement đúng.

## 8. Retry an toàn: idempotency, backoff và hạn mức

Retry giúp phục hồi lỗi tạm thời nhưng có thể tạo trùng hoặc ghi đè dữ liệu nếu không thiết kế cẩn thận.

### Idempotency

**Idempotency** nghĩa là thực hiện lại cùng một yêu cầu có cùng ý nghĩa không tạo thêm kết quả sai. Ví dụ, một lệnh **đảm bảo user thuộc nhóm A** khi chạy lại không nên thêm bản ghi thành viên trùng hoặc gỡ những quyền khác.

Để đạt điều này, nên lưu:

- **Event/workflow ID** và phiên bản dữ liệu nguồn.
- **Định danh chủ thể ổn định** cùng target ID đã xác minh.
- **Operation ID** cho mỗi đích, loại hành động và đối tượng entitlement.
- Trạng thái **desired** và **observed** gần nhất, thời điểm readback.
- Kết quả retry, số lần thử, lỗi cuối và mốc thử tiếp theo.

Đối với **POST tạo user**, không được giả định API sẽ tự khử trùng. Một timeout sau khi gửi phải dẫn đến **readback/lookup trước khi gửi tạo mới**. Nếu đích có hỗ trợ idempotency key, sử dụng theo hợp đồng của API; không tự đoán endpoint nào cũng hỗ trợ.

### Exponential backoff và jitter

Với lỗi tạm thời, có thể áp dụng chờ tăng dần và một thành phần ngẫu nhiên:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt)
delay = random(0, delay)   # full jitter, minh họa
~~~

Không có khoảng chờ “chuẩn cho mọi API”. Nên tôn trọng **Retry-After** nếu đích trả về, giới hạn số retry và tránh làm cạn quota khi nhiều worker đồng thời.

### Không retry máy móc

- **400/schema invalid:** yêu cầu sửa dữ liệu hoặc mapping.
- **403/insufficient permission:** cần kiểm soát quyền connector và phê duyệt; lặp lại không tạo được quyền.
- **409/duplicate identity:** cần đối chiếu thực thể.
- **412/version conflict:** đọc phiên bản hiện tại trước khi tính lại thao tác.
- **429/5xx:** retry có backoff và theo dõi, nhưng vẫn xác minh kết quả không chắc chắn.
- **Policy denied:** giữ trạng thái từ chối/chờ phê duyệt; không bypass.

Khi vượt ngưỡng, đưa job vào **hàng đợi xử lý lỗi (dead-letter queue – DLQ)** hoặc ticket có người phụ trách. DLQ là cơ chế lưu vết và xử lý, **không phải nơi bỏ quên lỗi không thời hạn**.

## 9. Thứ tự sự kiện và chống phục hồi quyền đã thu hồi

Mô hình Joiner–Mover–Leaver tạo ra những thay đổi trạng thái theo thời gian. Event bus không luôn đảm bảo mọi connector nhận sự kiện đúng thứ tự.

Ví dụ:

1. HRIS ghi nhận một nhân viên chuyển vai trò **Mover v18**.
2. Một giờ sau, HRIS ghi nhận **Leaver v19**.
3. Connector xử lý Leaver v19 trước, vô hiệu hóa account.
4. Job Mover v18 đến muộn và thực hiện **active=true** để áp role mới.

Nếu không kiểm tra version, job cũ có thể **mở lại tài khoản** đã bị chặn.

### Quy tắc phòng tránh

- Dùng **version đơn điệu theo bản ghi nguồn/quan hệ** khi có thể.
- Kiểm tra **trạng thái nguồn hiện hành** trước khi thao tác kích hoạt hoặc cấp quyền mới.
- Không dùng timestamp của máy nhận làm thứ tự nghiệp vụ duy nhất.
- Có cơ chế **fencing** để job với version cũ không ghi đè version mới.
- Với Leaver có hiệu lực, chính sách chặn truy cập phải có mức ưu tiên phù hợp khi gặp job cấp quyền cũ.
- Khi HR hủy/sửa một quyết định, cần workflow có kiểm soát; không khôi phục toàn bộ quyền chỉ vì xuất hiện event mới.

~~~mermaid
sequenceDiagram
    participant H as HRIS
    participant O as IAM Orchestrator
    participant C as Connector
    participant A as Ứng dụng
    H->>O: Mover v18
    H->>O: Leaver v19
    O->>C: Deactivate v19
    C->>A: Vô hiệu hóa
    A-->>O: Đã xác minh inactive
    O->>C: Job Mover v18 đến muộn
    C->>O: Kiểm tra version và trạng thái nguồn
    O-->>C: Từ chối v18 vì đã cũ
    Note over C,A: Không kích hoạt lại account
~~~

Đây là nguyên tắc quan trọng nhất khi xử lý provisioning thất bại có retry kéo dài: **khôi phục một job lỗi không được làm đảo ngược quyết định vòng đời mới hơn**.

## 10. Đối soát: kiểm tra trạng thái thực tế thay vì chỉ tin response

**Reconciliation** là quá trình so sánh **desired state** theo IAM/chính sách với **observed state** đọc từ từng hệ thống đích.

Ví dụ người dùng phải thuộc hai nhóm trong ứng dụng, nhưng readback trả chỉ một nhóm:

~~~text
desired:
  active: true
  groups: [APP_READER, APP_APPROVER]

observed:
  active: true
  groups: [APP_READER]

difference:
  missing: [APP_APPROVER]
  unexpected: []
~~~

Chênh lệch cần được đưa thành **finding có owner và thời hạn**, không bị ẩn trong log debug. Nếu nhóm APP_APPROVER chưa được duyệt, **desired state phải được tính lại** theo chính sách thay vì tự cấp nó chỉ vì xuất hiện trong một bản kế hoạch cũ.

### Các bước đối soát

1. Đọc trạng thái danh tính và quan hệ công việc hiện hành từ nguồn có thẩm quyền.
2. Tính tập account, nhóm và quyền **phải có** theo policy, ngoại lệ hợp lệ, thời hạn và các phê duyệt.
3. Đọc tập account, entitlement và credential **đang có** từ hệ thống đích.
4. So sánh để phát hiện **missing account**, **missing entitlement**, **unexpected account**, **unexpected entitlement**, **stale credentials**.
5. Ưu tiên xử lý sai lệch theo rủi ro; quyền không mong muốn hoặc Leaver còn truy cập phải được leo thang nhanh.
6. Thực hiện thay đổi hoặc mở ticket và **xác minh lại readback**.
7. Ghi kết quả cuối, những ngoại lệ chưa đóng và giới hạn quan sát (ví dụ API không cung cấp session list).

**Không phải mọi hệ thống cho phép đọc lại toàn bộ quyền**, nhất là ứng dụng legacy. Nếu không xác minh trực tiếp được, cần dùng một cơ chế bằng chứng thay thế được phê duyệt (ticket có người kiểm tra, báo cáo của chủ hệ thống, kiểm thử quyền được phép) và nêu rõ mức tin cậy.

### Phân biệt inconsistency và propagation delay

Một hệ thống đích có thể cập nhật bất đồng bộ. Trong một khoảng thời gian ngắn, readback có thể chưa phản ánh thay đổi vừa ghi. Cần xác lập **cửa sổ nhất quán** theo đặc tính connector, kiểm tra lại có giới hạn và không tuyên bố thành công vĩnh viễn khi trạng thái vẫn sai sau cửa sổ.

## 11. Runbook xử lý sự cố provisioning

Một runbook tốt giúp người trực xử lý biết phải kiểm tra điều gì mà không gây cấp quyền sai hoặc xóa nhầm dữ liệu.

### Bước 1 — Xác nhận tác động và mức ưu tiên

- Là **Joiner không có quyền làm việc**, **Mover còn quyền cũ**, hay **Leaver chưa thu hồi được**?
- Hệ thống đích có nhạy cảm hoặc quyền đặc quyền không?
- Có đường truy cập thực tế còn hoạt động ngoài mong đợi không?
- Ảnh hưởng một người, một nhóm hay toàn bộ connector?

**Leaver còn quyền truy cập** và **quyền đặc quyền bị cấp trái policy** thường cần xử lý cao hơn lỗi Joiner đang thiếu quyền thông thường.

### Bước 2 — Lấy bằng chứng chính xác

Tra cứu theo **person/subject ID, relationship ID, workflow ID, connector, target account ID, operation ID, correlation ID**. Xem request/response đã được loại dữ liệu nhạy cảm, mã lỗi, số lần retry và timestamp. Không tìm account chỉ bằng tên/email rồi thay đổi ngay.

### Bước 3 — Xác minh desired state hiện tại

Đối chiếu HRIS hoặc nguồn có thẩm quyền, policy/role mapping, approval và version mới nhất. Nếu job đã lỗi thời, hủy hoặc thay bằng job mới; không replay yêu cầu cũ.

### Bước 4 — Readback hệ thống đích

Xác nhận account có tồn tại không, trạng thái hoạt động, group/role trực tiếp, token/credential còn liên quan và các quyền được hỗ trợ kiểm tra. Với timeout, readback là bước đặc biệt quan trọng trước khi tạo account lần nữa.

### Bước 5 — Chọn cách khắc phục

| Kết luận | Biện pháp |
|---|---|
| Mạng/API tạm lỗi | Retry có backoff, giới hạn, kiểm tra sau retry |
| Sai mapping/thuộc tính | Sửa dữ liệu nguồn hoặc mapping, tạo job mới theo version |
| Token connector hết hạn | Cập nhật qua secret manager theo thẩm quyền, thử lại |
| Không đủ quyền connector | Yêu cầu cấp quyền cần thiết, không mở rộng tùy tiện |
| Target account đã tồn tại | Xác minh liên kết và sử dụng thao tác cập nhật phù hợp |
| Thất bại một phần | Chỉ xử lý các hạng mục còn sai, không xóa thành quả hợp lệ |
| Leaver chưa vô hiệu được | Chặn qua lớp độc lập nếu có, cảnh báo Security và xử lý khẩn |
| Không xác định được kết quả | Điều tra trạng thái, tránh replay thao tác nguy hiểm |

### Bước 6 — Xác minh và đóng

Sau khi sửa, đọc lại trạng thái đích và đối chiếu với desired state. Ghi **ai thực hiện, thao tác nào, thời điểm nào, trạng thái trước/sau, bằng chứng gì**. Nếu vẫn còn ngoại lệ, giữ trạng thái **PARTIAL/OPEN**, owner, deadline và biện pháp giảm thiểu; không đóng ticket với lý do “đã gửi lệnh”.

## 12. Joiner, Mover và Leaver: tác động và ưu tiên khác nhau

| Sự kiện | Provisioning thất bại có thể gây gì? | Cách xử lý ưu tiên |
|---|---|---|
| **Joiner** | Tài khoản chưa tạo, chưa enroll MFA, thiếu quyền baseline | Kiểm tra identity proofing và dữ liệu nguồn; tạo/đồng bộ lại sau khi hợp lệ |
| **Mover** | Quyền mới thiếu; quyền cũ vẫn còn; xung đột SoD | Tính lại chênh lệch, thu hồi quyền cũ không hợp lệ, sau đó cấp quyền mới theo policy |
| **Leaver** | Account, phiên, token hoặc quyền không còn hợp lệ vẫn hoạt động | Ưu tiên chặn truy cập và đối soát từng hệ thống; mở incident khi cần |
| **Rejoiner** | Khôi phục nhầm quyền đã thu hồi, gắn sai account cũ | Xác minh quan hệ mới, tính quyền mới, kiểm soát account linking |
| **Hết hạn hợp đồng** | Không có event HRIS nên quyền kéo dài vô thời hạn | Dùng authoritative contract expiration, owner và thời hạn được phê duyệt |

### Joiner thất bại

Nếu provisioning chưa hoàn tất, nên thông báo rõ **“tài khoản/ứng dụng X đang chờ xử lý”**, tránh hướng dẫn người dùng tìm cách vòng qua chính sách. Không sao chép quyền của đồng nghiệp chỉ để xử lý nhanh nếu tập quyền của người đó có ngoại lệ hoặc quyền tạm thời.

### Mover thất bại

**Mover thường tạo nguy cơ tích lũy quyền**. Nếu người chuyển từ Sales sang Finance, IAM có thể cấp quyền Finance thành công nhưng không thu hồi được quyền xuất dữ liệu CRM. Workflow phải hiển thị lỗi **thu hồi quyền cũ**, kiểm tra SoD và ưu tiên giảm quyền ngoài phạm vi. Chỉ cấp quyền mới mà ghi SUCCESS là sai ngữ nghĩa.

### Leaver thất bại

Nếu IdP bị khóa nhưng SaaS legacy không hỗ trợ SCIM, phải sử dụng API riêng hoặc ticket thủ công có **chủ xử lý, SLA, xác nhận từ hệ thống đích**. Cần kiểm tra token cá nhân, tài khoản local, VPN, cloud key, nhóm đặc quyền và tài khoản dịch vụ mà người rời đi có thể biết credential.

**Không coi cắt đăng nhập SSO là bằng chứng đã hủy các session, API key hoặc quyền trực tiếp tại đích.** Nếu không thể thu hồi một đường truy cập quan trọng ngay, cân nhắc biện pháp giảm thiểu ở network/gateway, luân chuyển secret hoặc vô hiệu hóa kết nối theo thẩm quyền.

## 13. Danh tính phi con người và các lỗi provisioning đặc biệt

**Service account, device account, bot, CI/CD identity và workload identity** cũng có vòng đời tạo, cấp quyền, luân chuyển credential và thu hồi. Chúng thường không dùng email đăng nhập hay identity proofing giống nhân viên.

Các lỗi cần chú ý:

- **Owner không còn hợp lệ:** nhân viên đã Leaver nhưng service account vẫn gắn owner cá nhân và có quyền cao.
- **Credential không luân chuyển được:** secret hết hạn hoặc bị lộ, gây lỗi ứng dụng hoặc duy trì credential cũ quá lâu.
- **Workload redeploy:** pod/VM thay đổi ID nhưng policy/role vẫn gắn với định danh cũ.
- **Connector dùng tài khoản dịch vụ:** token của connector hết hạn khiến hàng loạt yêu cầu user provisioning lỗi.
- **Thiết bị tái cấp:** account máy và chứng chỉ cũ vẫn tồn tại sau khi đổi người sử dụng.
- **Xóa sai account dùng chung:** gỡ service account của người nghỉ có thể làm dừng hệ thống còn nhu cầu hợp lệ.

Khi xử lý, cần tách rõ **danh tính con người**, **danh tính máy**, **owner chịu trách nhiệm** và **credential thực tế**. Chuyển giao owner và luân chuyển secret có thể cần thiết hơn là xóa ngay một bot đang vận hành. Những quyền không còn hợp lệ phải được thu hồi theo đánh giá; nếu vẫn giữ một quyền để bảo đảm dịch vụ, cần có owner hợp lệ và thời hạn kiểm tra lại.

## 14. Giám sát, cảnh báo và kiểm toán

Một dashboard hữu ích phải phân biệt **tỷ lệ thao tác API thành công** với **tỷ lệ quyền thực tế đúng sau đối soát**.

| Chỉ số | Định nghĩa | Cách dùng |
|---|---|---|
| **Provisioning failure rate** | Tỷ lệ thao tác thất bại theo connector, loại hành động, lý do | Khoanh vùng lỗi hệ thống hoặc mapping |
| **Partial completion rate** | Tỷ lệ workflow có bước thành công và bước còn lỗi | Xác định chênh lệch xuyên nhiều hệ thống |
| **Time to provision** | Từ yêu cầu hợp lệ đến trạng thái verified | Đánh giá khả năng sẵn sàng của Joiner |
| **Time to revoke** | Từ mốc phải thu hồi đến verified deprovision | Đo rủi ro Mover/Leaver |
| **Unknown outcome backlog** | Số thao tác timeout/chưa xác minh được kết quả | Ngăn duplicate và quyền sai kéo dài |
| **Retry exhaustion count** | Số job vượt ngưỡng retry hoặc trong DLQ | Ưu tiên nguyên nhân gốc |
| **Reconciliation mismatch count** | Số sai lệch desired–observed chưa đóng | Đo quyền thiếu và quyền dư |
| **Orphan account count** | Tài khoản không liên kết owner/quan hệ hợp lệ | Tìm account mồ côi |
| **Residual access after Leaver** | Quyền/tài khoản vẫn còn hiệu lực sau mốc cắt | Ưu tiên cảnh báo bảo mật |
| **Stale event rejection** | Số job bị loại vì version cũ | Đo độ trễ và bảo vệ trước đảo thứ tự |

### Cần log những gì?

- **Nguồn:** eventId, source, subjectId, relationshipId, source version.
- **Quyết định:** policy version, loại sự kiện, desired state, phê duyệt/ngoại lệ liên quan.
- **Điều phối:** workflow ID, operation ID, connector ID, correlation ID, timestamp và thứ tự xử lý.
- **Thực thi:** request kind, target object ID, mã lỗi đã được làm sạch, retry count, response type.
- **Đối soát:** observed state, diff, thời điểm readback, kết quả cuối.
- **Khắc phục:** owner, ticket, deadline, biện pháp bù trừ, người phê duyệt và bằng chứng đóng.

**Không ghi access token, refresh token, API key, mật khẩu, private key, mã MFA hay thông tin định danh nhạy cảm không cần thiết vào log.** Kết quả lỗi có thể chứa cả payload cá nhân hoặc thông tin xác thực trong một số API; cần làm sạch trước khi gửi tới SIEM và các nền tảng quan sát.

### Cảnh báo theo rủi ro

- **Khẩn:** Leaver còn đường truy cập quan trọng, cấp nhầm đặc quyền, connector deprovision mất khả năng hoạt động diện rộng.
- **Cao:** Mover giữ quyền cũ nhạy cảm, lỗi provisioning hàng loạt, orphan account ở hệ thống trọng yếu.
- **Vận hành:** Joiner thiếu quyền ít nhạy cảm, thông báo gửi lỗi, yêu cầu cập nhật thông thường đang retry.

Ngưỡng cảnh báo và SLA do tổ chức quyết định theo mức nhạy cảm và hậu quả kinh doanh, không áp cùng một giá trị cho tất cả dịch vụ.

## 15. Tình huống end-to-end: account đã tạo nhưng chưa đủ quyền

Giả sử **Lan**, mã danh tính nội bộ **person-2046**, gia nhập nhóm Finance ngày **01/12/2026**.

**Bước 1 — HRIS phát Joiner.** IAM nhận sự kiện hợp lệ, kiểm tra danh tính đã được xác minh theo chính sách và tính tập quyền baseline: tài khoản IdP, truy cập báo cáo tài chính mức đọc và nhóm ứng dụng Finance.

**Bước 2 — IdP thành công.** Tài khoản được tạo với trạng thái phù hợp, thông báo enrollment MFA được phát hành. IdP trả kết quả chính xác cho phần nó quản lý.

**Bước 3 — SCIM User thành công nhưng Group lỗi.** Ứng dụng đích tạo User, sau đó connector gọi API cập nhật nhóm nhưng nhận **429 Too Many Requests**. Workflow ở trạng thái **PARTIALLY_COMPLETED**; IAM lưu target user ID, group operation ID, nguyên nhân và lịch retry.

**Bước 4 — Retry có kiểm soát.** Connector chờ theo thông tin rate limit/backoff, kiểm tra trạng thái quyền hiện tại rồi thực hiện thao tác bổ sung group theo cơ chế idempotent. Nếu nhóm đã được gán bởi một retry trước nhưng response bị mất, lần kiểm tra trạng thái không tạo thao tác trùng.

**Bước 5 — Đối soát.** Sau khi API trả thành công, IAM đọc lại group/entitlement. Nếu Lan thực sự có quyền xem báo cáo như desired state, hạng mục này chuyển sang **VERIFIED**. Nếu quyền vẫn chưa phản ánh, IAM giữ trạng thái pending/failed và tiếp tục theo hợp đồng connector, không tuyên bố người dùng đã sẵn sàng hoàn toàn.

**Bước 6 — Mover sau ba tháng.** Lan đổi sang vai trò kế toán thanh toán. IAM thu hồi nhóm Finance cũ không còn hợp lệ, tính quyền mới và kiểm tra SoD. Nếu connector thu hồi nhóm cũ lỗi, đây là lỗi **dư quyền**, được ưu tiên xử lý thay vì chỉ theo dõi quyền mới thiếu.

**Bước 7 — Leaver sau sáu tháng.** HRIS gửi Leaver có hiệu lực. IAM chặn IdP, thu hồi phiên và quyền theo từng đích. Nếu ứng dụng Finance không thể deprovision ngay, quy trình còn **OPEN/PARTIAL**, có ticket, owner và biện pháp giảm thiểu. Chỉ khi trạng thái thực tế được xác minh mới ghi hoàn tất.

Ví dụ này minh họa ba điều: **một thành công cục bộ không phải thành công toàn workflow; retry phải an toàn; và lỗi thu hồi sau Leaver nguy hiểm hơn lỗi cấp quyền mới bị chậm**.

## 16. Checklist phòng ngừa provisioning thất bại

1. **Nguồn chính xác:** hệ thống có nguồn authoritative theo từng loại danh tính, subject ID ổn định và quan hệ công việc rõ chưa?
2. **Định danh đích:** mapping từ danh tính gốc tới target account ID có được lưu và kiểm tra trước khi tạo hoặc thu hồi không?
3. **Chính sách:** RBAC/ABAC, SoD, phê duyệt, license và quyền tạm thời có được kiểm tra trước provisioning không?
4. **Connector:** đã kiểm tra schema, khả năng SCIM/API, quyền connector, giới hạn tốc độ và cách đích xử lý active/group chưa?
5. **Idempotency:** event/workflow và từng thao tác cấp quyền có chống replay, timeout sau ghi và trùng account không?
6. **Version:** job cũ có bị ngăn ghi đè trạng thái hiện hành hoặc mở lại quyền đã thu hồi không?
7. **Lỗi tạm thời:** retry có giới hạn, backoff/jitter, xử lý 429/5xx, DLQ và người phụ trách không?
8. **Lỗi vĩnh viễn:** validation, conflict, policy denied có được phân loại và sửa tại nguồn đúng thẩm quyền không?
9. **Partial success:** workflow có trạng thái riêng cho từng hệ thống, mỗi account và từng entitlement không?
10. **Đối soát:** sau khi thao tác, có readback trạng thái thực tế và so sánh desired–observed không?
11. **JML:** Joiner thiếu quyền được xử lý; Mover thu hồi quyền cũ; Leaver được ưu tiên chặn mọi đường truy cập theo phạm vi không?
12. **Phi con người:** service account, bot, device credential và owner có được quản lý/thu hồi theo vòng đời hợp lệ không?
13. **Bảo mật:** token, secret, giấy tờ và PII có được loại khỏi log và hệ thống thông báo không?
14. **Kiểm toán:** có thể biết ai yêu cầu, ai phê duyệt, lỗi tại đâu, đã retry thế nào và khi nào xác minh kết quả không?
15. **Escalation:** các ngoại lệ quyền tồn dư có owner, thời hạn, biện pháp bù trừ và trách nhiệm rõ ràng không?

### Ghi nhớ

**Provisioning thất bại là sự chênh lệch giữa quyền/tài khoản phải có theo trạng thái và chính sách hiện hành với những gì hệ thống đích thực sự cung cấp.** Phải phân loại nguyên nhân, xử lý retry an toàn, chống trùng và sự kiện cũ, theo dõi thất bại một phần, rồi **đối soát trạng thái thật**. Trong IAM lifecycle, **Joiner** cần được cấp đúng quyền, **Mover** phải thu hồi quyền cũ không còn hợp lệ và **Leaver** phải chặn những đường truy cập đã hết thẩm quyền. Kết quả HTTP hoặc thông báo thành công chỉ là một phần bằng chứng; **hoàn tất kỹ thuật cần được xác minh tại hệ thống đích**.
