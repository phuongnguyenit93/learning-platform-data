# Least privilege access: truy cập với đặc quyền tối thiểu trong Zero Trust IAM

## 1. Cấp đủ quyền để làm việc, trong một phạm vi xác định

**Least privilege access** là nguyên tắc chỉ cấp cho một chủ thể những quyền cần thiết để thực hiện nhiệm vụ được chấp nhận, trên đúng tài nguyên, trong đúng phạm vi và trong khoảng thời gian cần thiết.

Chủ thể có thể là người dùng, tài khoản quản trị, dịch vụ, job nền hoặc một tích hợp bên ngoài. Đặc quyền tối thiểu không chỉ áp dụng cho tài khoản có tên `admin`; một tài khoản chỉ đọc nhưng đọc được mọi dữ liệu khách hàng cũng có thể mang quyền vượt nhu cầu.

Trong Zero Trust IAM, nguyên tắc này giúp giới hạn hậu quả khi một danh tính, phiên hoặc workload bị sử dụng sai. Thay vì để việc đăng nhập mở ra một vùng truy cập rộng, mỗi yêu cầu phải nằm trong quyền được xác lập cho chủ thể và ngữ cảnh đó.

Ví dụ, Lan cần đối chiếu hợp đồng của dự án `project-27` thuộc công ty An Bình. Nhu cầu này không tự đòi hỏi:

- Xem toàn bộ hợp đồng của mọi dự án.
- Tải hàng loạt tài liệu khách hàng.
- Sửa hoặc xóa hợp đồng.
- Tạo người dùng và gán vai trò.
- Truy cập tenant khác hoặc môi trường sản xuất khác.

Thiết kế đúng bắt đầu từ nhiệm vụ đối chiếu, sau đó xác định quyền đủ cho nhiệm vụ. Nó không bắt đầu bằng vai trò có sẵn rộng nhất rồi hy vọng người dùng chỉ sử dụng phần mình cần.

## 2. Quyền tối thiểu có nhiều chiều

Một phép cấp quyền cần được xem xét theo nhiều chiều thay vì chỉ có “đọc” hoặc “ghi”.

| Chiều giới hạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Chủ thể | Ai thực sự cần quyền? | Lan hoặc workload đối soát đã định danh |
| Hành động | Được thực hiện thao tác nào? | Đọc nội dung hợp đồng, không được xóa |
| Tài nguyên | Được tác động đến đối tượng nào? | Hợp đồng của `project-27` |
| Phạm vi | Quyền thuộc tenant, tổ chức hoặc môi trường nào? | An Bình, môi trường nghiệp vụ được phép |
| Dữ liệu | Được xem phần dữ liệu nào? | Không trả thông tin thanh toán không cần cho nhiệm vụ |
| Điều kiện | Khi nào yêu cầu được chấp nhận? | Còn tham gia dự án, đáp ứng điều kiện xác thực |
| Thời gian | Quyền bắt đầu và kết thúc khi nào? | Trong thời gian được phân công hoặc thời hạn phê duyệt |
| Ủy quyền | Có được chuyển hoặc mở rộng quyền không? | Không tự gán quyền cho người khác |

Một mô hình khái niệm:

```text
Grant
  subject
  allowedActions
  resourceScope
  tenantOrEnvironmentScope
  conditions
  validFrom
  validUntil
  delegationRules
```

Không phải mọi hệ thống đều lưu các trường này trong một bản ghi. Chúng có thể được thể hiện bằng vai trò, quan hệ, thuộc tính và chính sách. Điều quan trọng là kết quả quyền thực tế có những giới hạn cần thiết.

“Quyền nhỏ” cũng không chỉ là số lượng ít. Một quyền duy nhất như `manage_all` có thể rộng hơn hàng chục quyền cụ thể, được giới hạn chặt.

## 3. Mối liên hệ với xác thực và phân quyền

Xác thực trả lời chủ thể là ai. Phân quyền quyết định chủ thể có được thực hiện hành động trên tài nguyên hay không. Đặc quyền tối thiểu là một nguyên tắc thiết kế và quản trị các quyền dùng trong quyết định đó.

Các kiểm soát bổ trợ không thay thế nhau:

| Kiểm soát | Vai trò | Điều vẫn phải giới hạn |
| --- | --- | --- |
| MFA | Tăng bằng chứng xác thực | Hành động và tài nguyên được phép |
| SSO | Tập trung hoặc liên kết trải nghiệm đăng nhập | Quyền riêng của từng ứng dụng |
| VPN | Kiểm soát một đường kết nối | Quyền nghiệp vụ của bên gọi |
| Token tồn tại ngắn | Giới hạn thời gian sử dụng thông tin xác thực | Phạm vi quyền chứa trong token |
| Mã hóa đường truyền | Bảo vệ dữ liệu trên kênh truyền | Ai được đọc hoặc thay đổi dữ liệu |
| RBAC hoặc ABAC | Biểu diễn và đánh giá quyền | Mức rộng của vai trò, thuộc tính và chính sách |

Một quản trị viên xác thực bằng MFA vẫn có thể có quá nhiều quyền. Một token chỉ tồn tại ít phút vẫn có thể gây hậu quả lớn nếu trong thời gian đó nó cho phép xóa mọi tài nguyên.

Ngược lại, giảm quyền quá mức đến mức không hoàn thành được nhiệm vụ cũng không phải mục tiêu. Cần xác định một tập quyền đủ, có căn cứ và có người chịu trách nhiệm phê duyệt.

## 4. Bắt đầu từ nhiệm vụ và danh mục hành động

### 4.1. Mô tả nhu cầu bằng hành động cụ thể

Yêu cầu “Lan cần quyền vào hệ thống hợp đồng” quá mơ hồ để cấp quyền.

Một mô tả có thể sử dụng được là:

> Lan cần xem các hợp đồng thuộc dự án 27 của An Bình để đối chiếu thông tin, không cần xuất hàng loạt, sửa nội dung hoặc quản lý thành viên.

Từ đó, hệ thống xác định:

```text
subject: user-lan
action: contract:read
resourceScope: project-27
tenantScope: tenant-an-binh
condition: còn được phân công vào project-27
```

Nếu sau này Lan cần sửa trạng thái hợp đồng, đó là nhu cầu bổ sung cần được đánh giá, không phải lý do cấp trước mọi quyền quản trị.

### 4.2. Tách những hành động có hậu quả khác nhau

Một API `manageContract` bao gồm xem, sửa, xóa và xuất dữ liệu khiến việc cấp quyền tối thiểu khó hơn.

Danh mục quyền có thể tách:

- `contract:read`: xem trong phạm vi được cấp.
- `contract:update`: sửa các trường được phép.
- `contract:approve`: phê duyệt theo quy trình.
- `contract:export`: tạo tệp xuất dữ liệu.
- `contract:delete`: xóa theo chính sách.
- `contract:grant-access`: thay đổi người được truy cập.

Cách chia phải theo nghiệp vụ và khả năng thực thi của hệ thống. Chia quá nhỏ mà không quản lý được cũng tạo chi phí và lỗi. Cần đặc biệt tách các hành động có khả năng mở rộng quyền, tiết lộ nhiều dữ liệu hoặc gây tác động khó khôi phục.

### 4.3. Tính đến nhiệm vụ ít xảy ra

Lịch sử sử dụng giúp phát hiện quyền thừa nhưng không phải nguồn duy nhất để xác định quyền cần thiết.

Một quyền phục hồi sự cố có thể ít được dùng nhưng vẫn cần thiết cho một vai trò nhất định. Thay vì giữ quyền thường trực rộng vì “có thể cần”, hãy xác định cách cấp có kiểm soát khi tình huống phát sinh.

## 5. Thiết kế vai trò, thuộc tính và quan hệ

### 5.1. Vai trò nên đại diện cho trách nhiệm

Trong RBAC, một vai trò nên gắn với một tập trách nhiệm có thể giải thích được.

| Vai trò minh họa | Quyền thường trực | Quyền không tự có |
| --- | --- | --- |
| Người đối chiếu hợp đồng | Đọc hợp đồng trong dự án được phân công | Xuất toàn tenant, xóa, gán quyền |
| Người phê duyệt | Đọc và phê duyệt trong phạm vi được giao | Quản lý danh tính hoặc cấu hình SSO |
| Quản trị thành viên tenant | Quản lý thành viên theo giới hạn của tenant | Đọc mọi nội dung nghiệp vụ nếu không cần |
| Người vận hành báo cáo | Vận hành job báo cáo được cho phép | Truy cập tương tác vào mọi cơ sở dữ liệu |

Đây là ví dụ phân chia trách nhiệm; tổ chức cần xác định mô hình phù hợp với nghiệp vụ thực tế.

Không nên dùng một vai trò `admin` chung cho mọi tác vụ. Cũng không nên tạo vai trò mới chỉ để che giấu việc một cá nhân đã tích lũy nhiều quyền không liên quan.

### 5.2. Thêm phạm vi bằng thuộc tính hoặc quan hệ

Vai trò `contract_reader` có thể biểu diễn hành động đọc, còn quan hệ dự án xác định tài nguyên nào được đọc.

```text
cho phép contract:read khi:
    tài khoản còn hoạt động
    VÀ thành viên thuộc đúng tenant
    VÀ vai trò cho phép đọc
    VÀ hợp đồng nằm trong dự án được phân công
    VÀ điều kiện ngữ cảnh được đáp ứng
```

Trong ABAC, các thuộc tính như phòng ban, phân loại dữ liệu hoặc trạng thái thiết bị có thể làm điều kiện. Nguồn thuộc tính phải đáng tin cậy; không để client tự khai phòng ban hoặc tenant để mở rộng quyền.

### 5.3. Kiểm tra khả năng tự nâng quyền

Một quyền có vẻ gián tiếp vẫn có thể mang đặc quyền lớn:

- Sửa vai trò có quyền gán thêm quyền.
- Đổi thành viên của nhóm đặc quyền.
- Tạo thông tin xác thực cho tài khoản mạnh hơn.
- Thay cấu hình liên kết danh tính hoặc ánh xạ claim sang vai trò.
- Đổi danh tính mà một job hoặc dịch vụ sử dụng.

Khi đánh giá đặc quyền tối thiểu, cần xét chủ thể có thể làm gì thông qua những thay đổi này, không chỉ danh sách API được gọi trực tiếp.

## 6. Đánh giá quyền thực tế thay vì chỉ nhìn một vai trò

Một người dùng có thể nhận quyền từ nhiều nguồn:

```text
Người dùng
  -> quyền gán trực tiếp
  -> vai trò
  -> nhóm và nhóm lồng nhau
  -> quyền trên tài nguyên
  -> quyền tạm thời
  -> quan hệ ủy nhiệm
```

Quyền thực tế phụ thuộc cách hệ thống kết hợp các nguồn này với điều kiện, giới hạn và quy tắc từ chối. Không thể mặc định mọi mô hình đều chỉ cộng các quyền lại hoặc đều có cùng thứ tự ưu tiên.

Ví dụ, bỏ `contract:export` khỏi vai trò của Lan chưa chắc thu hồi được quyền xuất nếu Lan vẫn thuộc một nhóm khác đang cấp quyền đó.

Một lần rà soát cần trả lời:

1. Lan có thể thực hiện hành động nào?
2. Trên tập tài nguyên nào?
3. Quyền đến từ đâu và ai sở hữu nguồn cấp đó?
4. Có điều kiện hoặc giới hạn nào thực sự được thực thi?
5. Lan có thể tạo thêm quyền hoặc thông tin xác thực nào?

Để giải thích được quyết định, hệ thống nên lưu được nguồn cấp quyền hoặc đường suy ra quyền. Một màn hình chỉ hiển thị tên vai trò chính có thể khiến người quản trị bỏ sót quyền kế thừa.

## 7. Cấp quyền tạm thời: giới hạn quyền và giới hạn thời gian

### 7.1. Quyền đúng nhu cầu của tác vụ

Một người trực vận hành cần chạy lại một job báo cáo lỗi. Nhu cầu này có thể chỉ cần quyền chạy lại đúng loại job trong một môi trường, thay vì quyền quản trị toàn bộ hệ thống báo cáo.

Đây là giới hạn theo năng lực: cấp đúng hành động và tài nguyên cần cho tác vụ.

### 7.2. Quyền chỉ tồn tại trong thời gian cần thiết

Nếu tác vụ chỉ phát sinh khi có sự cố, có thể kích hoạt quyền theo yêu cầu, thường được gọi là **just-in-time access**.

Một luồng minh họa:

```text
Yêu cầu quyền
    -> xác định danh tính và nhiệm vụ
    -> kiểm tra điều kiện hoặc phê duyệt
    -> cấp quyền có phạm vi và thời hạn
    -> thực hiện tác vụ
    -> hết hạn hoặc thu hồi sớm
    -> rà soát hoạt động
```

Yêu cầu cấp quyền có thể gồm:

```text
requester = operator-21
action = report-job:retry
resourceScope = report-job-563
environment = production
reason = incident-128
expiresAt = thời điểm được phê duyệt
```

Không để người yêu cầu tự chọn quyền ngoài danh mục mà chính sách cho phép. Nếu cần phê duyệt, người phê duyệt phải có thẩm quyền với đúng phạm vi đó.

### 7.3. Hết hạn phải có tác dụng tại điểm thực thi

Một trường `expiresAt` trong cơ sở dữ liệu chỉ có ý nghĩa nếu cơ chế quyết định hoặc thực thi tôn trọng nó.

Khi quyền tạm thời hết hạn, cần xem xét cả:

- Phiên đặc quyền đang mở.
- Token đã phát hành.
- Cache quyết định cho phép.
- Kết nối dài hạn.
- Job đã nhận quyền ủy nhiệm.
- Thông tin xác thực phát sinh trong lúc có quyền.

Không hứa thu hồi tức thì nếu kiến trúc chỉ kiểm tra quyền khi đăng nhập và tiếp tục chấp nhận token cũ đến hết hạn.

### 7.4. Tránh biến quyền tạm thành quyền thường trực

Gia hạn liên tục, phê duyệt tự động không xét phạm vi hoặc tạo API key dài hạn trong lúc nâng quyền có thể làm mất mục đích của cơ chế tạm thời.

Quyền được kích hoạt cần được kiểm toán theo người thực hiện thật, tác vụ, tenant hoặc môi trường, thời hạn và hành động đã thực hiện.

## 8. Áp dụng cho workload và tích hợp

Danh tính workload thường chạy tự động, với tần suất cao và ít có tương tác người dùng. Vì vậy, quyền rộng của workload có thể tạo tác động lớn dù không có tài khoản quản trị nào đăng nhập trực tiếp.

### 8.1. Tách danh tính theo trách nhiệm và môi trường

Ví dụ:

```text
contract-api-prod
  -> đọc và cập nhật hợp đồng qua các đường nghiệp vụ được cho phép

report-exporter-prod
  -> đọc dữ liệu cần cho báo cáo và ghi vào vùng đầu ra được cấp

schema-migrator-prod
  -> thực hiện thay đổi lược đồ trong cửa sổ vận hành được kiểm soát
```

Không để API nghiệp vụ thường trực dùng cùng danh tính cơ sở dữ liệu có quyền thay đổi mọi lược đồ chỉ vì tác vụ migration cần quyền đó.

Môi trường phát triển và sản xuất cũng cần ranh giới riêng. Một bí mật bị lộ ở môi trường phát triển không nên mở đường trực tiếp sang tài nguyên sản xuất.

### 8.2. Chỉ cấp loại truy cập cần dùng

Nếu workload chỉ đọc một kho đối tượng, nó không cần quyền xóa kho hoặc quản lý chính sách truy cập của kho.

Nếu tích hợp chỉ đẩy webhook cho An Bình, thông tin xác thực của nó không nên cho phép đọc mọi tenant.

Giới hạn thời gian thông tin xác thực, thay thế bí mật và bảo vệ nơi lưu bí mật là các lớp bổ sung. Chúng cần đi cùng quyền đúng phạm vi.

### 8.3. Giữ giới hạn khi thao tác thay mặt người dùng

Một dịch vụ có quyền kỹ thuật rộng có thể bị lợi dụng để thực hiện hành động mà người dùng không được phép tự làm.

Khi thay mặt Lan xuất báo cáo, dịch vụ không nên dùng toàn bộ quyền của tài khoản kỹ thuật chỉ vì request đã đến được hàng đợi. Nó cần kiểm tra một quan hệ ủy nhiệm hợp lệ và phạm vi được chấp nhận cho job.

Về mặt thiết kế, khả năng thực hiện cần bị chặn bởi cả chính sách đối với dịch vụ lẫn quyền hoặc ủy nhiệm của tác vụ. Cơ chế kết hợp cụ thể tùy hệ thống, nhưng không được tự làm rộng quyền nghiệp vụ của người yêu cầu.

## 9. Thực thi tại tài nguyên, dữ liệu và API

### 9.1. Bảo vệ API phía server

Ẩn nút “Xóa” trên giao diện không thu hồi được quyền nếu API xóa vẫn chấp nhận request trực tiếp.

Điểm thực thi phải nhận diện hành động và tài nguyên thật, lấy quyền từ nguồn được chấp nhận, rồi quyết định trước khi tạo tác động nghiệp vụ.

### 9.2. Giới hạn truy vấn và nội dung trả về

Quyền `contract:read` cần có phạm vi dữ liệu, không chỉ kiểm tra tên quyền rồi truy vấn toàn bảng.

Ví dụ SQL minh họa với tham số đặt tên:

```sql
SELECT id, project_id, title, status
FROM contract
WHERE tenant_id = :verified_tenant_id
  AND project_id = :authorized_project_id
  AND id = :contract_id;
```

Các tham số phạm vi phải được xác lập từ ngữ cảnh và quyết định quyền đáng tin cậy. Bản thân bộ lọc không thay thế các điều kiện khác của chính sách.

Không trả các trường nhạy cảm mà nhiệm vụ không cần, rồi chỉ che chúng bằng giao diện. Khi dữ liệu đã được gửi về client, việc ẩn hiển thị không còn là một ranh giới bảo vệ.

### 9.3. Kiểm tra cả đường truy cập phụ

Phạm vi quyền cần được giữ nhất quán ở:

- Tìm kiếm, xem chi tiết và xử lý theo danh sách.
- Xuất dữ liệu và tải tệp.
- API quản trị hoặc API nội bộ.
- Hàng đợi và công việc nền.
- Sự kiện thời gian thực.
- Bản sao dữ liệu phục vụ báo cáo.

Một API chính đã được giới hạn không bảo vệ được một đường tải tệp có quyền rộng hơn. Tương tự, kiểm tra phần tử đầu tiên không đủ để cấp quyền cho cả danh sách tài nguyên.

## 10. Mã giả đánh giá quyền tối thiểu

Đoạn dưới minh họa một request đọc hợp đồng. Nó không đại diện cho một thư viện hoặc chính sách có thể dùng nguyên trạng.

```text
function readContract(request, credential):
    actor = authenticateAndValidate(credential)
    context = establishVerifiedTenantContext(actor, request.tenantId)

    membership = loadCurrentMembership(actor.id, context.tenantId)
    if membership is absent or membership.state != "ACTIVE":
        deny()

    contract = repository.findWithinTenant(
        tenantId = context.tenantId,
        contractId = request.contractId
    )
    if contract is absent:
        return unavailableResourceResponse()

    decision = authorize(
        subject = actor,
        action = "contract:read",
        resource = contract,
        membership = membership,
        currentContext = context
    )

    if decision.type != "ALLOW":
        auditDeniedAttempt(actor, context, contract.id)
        deny()

    requireDecisionStillApplicable(decision, contract, context)

    result = projectOnlyAuthorizedFields(
        contract,
        allowedFields = decision.allowedFields
    )

    auditCompletedRead(actor, context, contract.id, decision)
    return result
```

Hàm `authorize` cần xét quyền hiện hành, quan hệ dự án, thời hạn cấp quyền và các điều kiện đã định. Không nên triển khai nó chỉ bằng một nhánh `if actor.isAdmin then allowAll` nếu đặc quyền quản trị đó không có phạm vi rõ ràng.

Quyền đọc trong ví dụ cũng không được tái sử dụng làm kết quả cho phép cập nhật, xuất hoặc xóa. Mỗi hành động cần được đánh giá theo chính sách của chính nó.

## 11. Duy trì quyền tối thiểu trong vòng đời danh tính

### 11.1. Khi gia nhập

Cấp quyền cơ sở theo nhiệm vụ đã xác định. Những quyền nhạy cảm cần có căn cứ và người chịu trách nhiệm cấp, thay vì sao chép toàn bộ quyền của một nhân viên khác.

Việc sao chép có thể mang theo quyền tạm thời, ngoại lệ cũ hoặc quyền không còn liên quan của người được dùng làm mẫu.

### 11.2. Khi chuyển công việc

Khi Lan chuyển sang dự án mới, cần rà soát cả quyền cũ lẫn quyền mới.

Nếu chỉ thêm quyền cho dự án mới, tài khoản sẽ tích lũy quyền qua các lần chuyển việc. Cần xác định quyền nào kết thúc, quyền nào được giữ có lý do và quyền nào có thời gian chuyển tiếp được phê duyệt.

### 11.3. Khi kết thúc quan hệ hoặc nhiệm vụ

Thu hồi quyền có thể bao gồm thành viên nhóm, vai trò trực tiếp, grant trên tài nguyên, quyền tạm thời và thông tin xác thực.

Khóa tài khoản ở một nơi chưa chắc thu hồi được token, API key hoặc phiên tại mọi hệ thống. Hệ thống phải có thiết kế phối hợp phù hợp với yêu cầu thời gian thu hồi.

### 11.4. Rà soát định kỳ

Người sở hữu tài nguyên hoặc trách nhiệm nghiệp vụ cần xác nhận những quyền còn cần thiết.

Lần rà soát nên có đủ ngữ cảnh: quyền thực tế, nguồn cấp, lần sử dụng, nhiệm vụ hiện hành và các khả năng nâng quyền. Một danh sách tên vai trò không đủ để đánh giá mọi trường hợp.

Với workload, cần có chủ sở hữu và mục đích rõ ràng để quyền không trở thành tài sản bị bỏ quên sau khi dịch vụ thay đổi hoặc ngừng chạy.

## 12. Giảm quyền trong hệ thống đang hoạt động

Một hệ thống cũ có thể đã dùng quyền rộng trong thời gian dài. Giảm quyền cần có bằng chứng và cách triển khai giữ được khả năng làm việc.

Một quy trình thực tế:

1. Lập danh sách chủ thể, tài nguyên và nguồn cấp quyền.
2. Kết hợp nhiệm vụ được giao với dữ liệu sử dụng để nhận diện quyền cần thiết.
3. Tách quyền thường trực khỏi quyền chỉ cần cho tác vụ đặc biệt.
4. Thiết kế chính sách hẹp hơn và xác định chủ sở hữu.
5. Kiểm tra các luồng nghiệp vụ quan trọng, kể cả luồng ít xảy ra.
6. Áp dụng cho phạm vi nhỏ, quan sát từ chối và tác động.
7. Mở rộng sau khi xác nhận, đồng thời thu hồi những đường cấp quyền cũ.

Có thể dùng chế độ đánh giá quan sát để xem chính sách mới sẽ cho phép hoặc từ chối gì trước khi thực thi. Tuy nhiên, quan sát không thay thế kiểm thử và không chứng minh mọi nhiệm vụ hợp lệ đã xuất hiện trong dữ liệu lịch sử.

Khi chính sách mới gây gián đoạn, cần phân biệt lỗi biểu diễn quyền với một yêu cầu đang vượt quyền thật. Không tự biến mọi lần bị từ chối thành việc cấp lại quyền quản trị toàn cục.

Nếu cần phục hồi, nên phục hồi một phiên bản chính sách đã biết hoặc cấp một quyền có giới hạn, có thời hạn và được ghi nhận. Một ngoại lệ không thời hạn dễ trở thành nguồn quyền thừa mới.

## 13. Kiểm thử và kiểm toán kết quả

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| Lan đọc hợp đồng thuộc dự án được phân công | Hoàn thành nhiệm vụ hợp lệ |
| Lan thay ID sang hợp đồng của dự án khác | Không nhận nội dung ngoài phạm vi |
| Lan có quyền đọc nhưng gọi API xóa hoặc xuất | Bị từ chối nếu chưa có quyền tương ứng |
| Vai trò của Lan bị bỏ nhưng nhóm khác vẫn cấp quyền | Hệ thống phát hiện đúng quyền thực tế còn tồn tại |
| Quyền tạm thời hết hạn | Các đường thực thi tuân thủ chính sách hết hạn và thu hồi |
| Lan chuyển công việc | Quyền cũ được xử lý theo quyết định đã ghi nhận |
| Workload báo cáo gọi API quản lý người dùng | Không được phép nếu ngoài nhiệm vụ |
| Danh tính môi trường thử nghiệm gọi tài nguyên sản xuất | Không vượt ranh giới môi trường |
| Một job nhận danh sách tài nguyên có phần tử ngoài phạm vi | Không xử lý tài nguyên không được cấp |
| Người dùng thay tenant trong request | Không dùng quyền của tenant cũ cho tenant mới |
| API trả dữ liệu có trường ngoài nhu cầu được cấp | Trường không được phép không xuất hiện trong kết quả |
| Người quản trị cố cấp cho mình quyền ngoài thẩm quyền | Không tự nâng quyền qua đường quản trị |

Audit cần giúp truy ra ai cấp quyền, cấp cho ai, phạm vi nào, căn cứ gì, thời hạn nào và quyền đã được sử dụng ra sao. Không ghi nguyên token hoặc bí mật vào nhật ký.

Các chỉ số hữu ích có thể gồm số quyền đặc biệt đang thường trực, quyền không có chủ sở hữu, grant đã hết hạn nhưng còn đường sử dụng và những ngoại lệ được gia hạn nhiều lần. Không nên coi “ít quyền hơn” là thành công nếu nhiệm vụ hợp lệ không còn thực hiện được.

## 14. Áp dụng vào tình huống của Lan

Với nhiệm vụ đối chiếu hợp đồng, quyền ban đầu của Lan có thể chỉ là đọc những hợp đồng trong `project-27` của An Bình, với các trường dữ liệu cần cho công việc.

Khi Lan cần xuất một báo cáo đặc biệt, hệ thống đánh giá nhu cầu xuất, phạm vi dữ liệu và thời hạn riêng. Nếu phù hợp, Lan nhận quyền giới hạn cho tác vụ đó; việc cấp quyền không mở thêm quyền xóa hợp đồng hoặc quản lý thành viên.

Khi Lan kết thúc nhiệm vụ tại dự án, quyền tương ứng được thu hồi qua tất cả nguồn cấp liên quan, và hệ thống xử lý phiên, token hoặc job theo cơ chế hiệu lực đã xác định.

Đặc quyền tối thiểu được duy trì khi mỗi quyền có mục đích, phạm vi, thời hạn hoặc điều kiện kết thúc và một điểm thực thi đáng tin cậy. Nó là quá trình quản lý quyền trong suốt vòng đời danh tính, chứ không chỉ là chọn một vai trò nhỏ tại lần đăng ký đầu tiên.
