# Deny by default: mặc định từ chối truy cập trong IAM

## 1. Chỉ cho phép khi có căn cứ cấp quyền rõ ràng

**Deny by default** là nguyên tắc mặc định từ chối một yêu cầu truy cập nếu hệ thống chưa xác lập được một quyết định cho phép hợp lệ cho yêu cầu đó.

Nguyên tắc này đặt trách nhiệm chứng minh ở phía cấp quyền: phải có căn cứ để cho phép chủ thể thực hiện hành động trên tài nguyên trong phạm vi tương ứng. Việc không tìm thấy một quy tắc cấm không đủ để cho phép.

Ví dụ, Lan đã đăng nhập vào ứng dụng quản lý hợp đồng của An Bình. Lan được cấp quyền đọc hợp đồng của dự án 27, nhưng chưa được cấp quyền xuất dữ liệu. Nếu API xuất dữ liệu không tìm thấy một chính sách phù hợp, kết quả phải là từ chối; không phải “người dùng đã đăng nhập nên cứ cho chạy”.

Có thể mô tả quy tắc nền tảng:

```text
Nếu có quyết định cho phép hợp lệ
    VÀ đáp ứng các ràng buộc bắt buộc
    VÀ thực thi được đầy đủ giới hạn của quyết định:
        cho phép trong phạm vi đã xác định
Ngược lại:
        từ chối
```

“Cho phép hợp lệ” bao gồm việc đánh giá đúng chủ thể, hành động, tài nguyên, phạm vi, điều kiện và hiệu lực. Một quyền tồn tại ở tenant khác hoặc một grant đã hết hạn không phải căn cứ để cho phép request hiện tại.

## 2. Phân biệt với các nguyên tắc liên quan

| Khái niệm | Câu hỏi chính | Quan hệ với deny by default |
| --- | --- | --- |
| Xác thực | Chủ thể là ai? | Danh tính hợp lệ chưa đủ để được cấp quyền |
| Phân quyền | Chủ thể có được làm việc này không? | Quyết định phải có kết quả cho phép rõ ràng |
| Least privilege | Nên cấp quyền rộng đến mức nào? | Giới hạn những quyền được cấp tường minh |
| Explicit deny | Có quy tắc từ chối cụ thể không? | Là một loại quy tắc, khác với việc mặc định từ chối khi không được cho phép |
| Fail closed | Điều gì xảy ra khi không thể kiểm tra điều kiện bắt buộc? | Lỗi không được tự biến thành quyền truy cập |
| Kiểm soát truy cập công khai | Truy cập nào không cần danh tính cá nhân? | Vẫn là lựa chọn chính sách tường minh cho một tài nguyên và hành động |

Deny by default không có nghĩa chặn mọi người vĩnh viễn. Hệ thống vẫn cần cho phép các nhiệm vụ hợp lệ. Điểm khác biệt là quyền được mở ra bằng chính sách có chủ đích, thay vì tồn tại mặc nhiên cho đến khi ai đó viết thêm một quy tắc cấm.

Một chính sách chặn hết request có thể an toàn theo nghĩa không ai đọc được dữ liệu, nhưng không đáp ứng được mục tiêu vận hành. Vì vậy, kiểm thử cần chứng minh cả truy cập hợp lệ được thực hiện và truy cập thiếu quyền bị từ chối.

## 3. Vì sao mặc định cho phép dễ tạo lỗ hổng?

Xét một cách triển khai theo danh sách cấm:

```text
if action == "contract:delete" and user is not administrator:
    deny()

allow()
```

Đoạn mã chỉ chặn một trường hợp đã biết. Khi có thêm hành động `contract:export`, `contract:share` hoặc `contract:grant-access`, những hành động này có thể rơi xuống nhánh cho phép dù chưa được đánh giá.

Một hướng tổ chức phù hợp hơn:

```text
decision = evaluateKnownPolicy(subject, action, resource, context)

if decision is an applicable and valid ALLOW:
    enforceDecisionAndExecute()
else:
    deny()
```

Khác biệt thể hiện rõ khi hệ thống thay đổi:

- Thêm endpoint mới nhưng chưa gắn chính sách.
- Thêm loại tài nguyên mà bộ máy phân quyền chưa nhận diện.
- Thêm vai trò nhưng chưa định nghĩa quyền.
- Nhận một giá trị hành động không được hỗ trợ.
- Gặp dữ liệu thành viên hoặc chính sách bị thiếu.

Với mặc định từ chối, các khoảng trống đó không tự mở quyền. Chúng cần được xử lý trước khi tính năng mới phục vụ truy cập được bảo vệ.

## 4. Định nghĩa đầy đủ một yêu cầu cần cấp quyền

Muốn quyết định cho phép, hệ thống cần hiểu chính xác yêu cầu:

```text
AccessRequest
  subject
  action
  resource
  tenantOrOrganization
  environment
  relevantContext
```

Ví dụ:

```text
subject = user-lan
action = contract:read
resource = contract-417
tenant = tenant-an-binh
environment = production
```

Nếu Lan có `contract:read` trong tenant Minh Hải, quyền đó không đáp ứng request trên. Nếu Lan chỉ có quyền đọc một dự án khác của An Bình, kết quả cũng không tự trở thành cho phép.

Các thành phần dùng để quyết định cần có nguồn đáng tin:

- Danh tính lấy từ quá trình xác thực đã được kiểm tra.
- Tenant được xác lập cùng quan hệ truy cập hợp lệ.
- Chủ sở hữu tài nguyên lấy từ dữ liệu có thẩm quyền.
- Vai trò và quan hệ lấy từ nguồn quản lý quyền.
- Ngữ cảnh bổ sung được xác minh theo chính sách.

Không nên cho client tự khai `isAdmin=true`, `resourceOwnerId` hoặc `policyPassed=true` rồi dùng trực tiếp để quyết định.

Nếu thiếu một trường bắt buộc để xác định phạm vi, hệ thống không nên bỏ điều kiện đó ra khỏi kiểm tra. Ví dụ, thiếu tenant không có nghĩa chuyển sang truy vấn mọi tenant.

## 5. Không khớp chính sách, bị cấm và lỗi đánh giá là các tình huống khác nhau

Trong nội bộ, bộ máy phân quyền nên phân biệt lý do quyết định để vận hành và điều tra. Một mô hình khái niệm có thể gồm:

| Tình huống | Ý nghĩa | Hành vi với tài nguyên được bảo vệ |
| --- | --- | --- |
| Cho phép áp dụng được | Có chính sách phù hợp và đủ điều kiện | Thực thi trong phạm vi được cho phép |
| Từ chối tường minh | Có quy tắc cấm áp dụng | Từ chối theo cơ chế kết hợp chính sách |
| Không có chính sách phù hợp | Chưa tìm được căn cứ cấp quyền | Từ chối |
| Thiếu thuộc tính bắt buộc | Không thể xác nhận điều kiện | Từ chối hoặc yêu cầu bổ sung qua luồng đã định |
| Lỗi đánh giá | Không đọc được dữ liệu, chính sách sai hoặc phụ thuộc lỗi | Không tự cho phép |
| Có điều kiện chưa hoàn tất | Ví dụ cần xác thực tăng cường | Chưa thực hiện hành động |

Đây là cách phân loại để thiết kế, không phải tập trạng thái bắt buộc của mọi sản phẩm IAM.

Deny by default không tự quy định toàn bộ thứ tự ưu tiên giữa nhiều chính sách. Một hệ thống có quy tắc từ chối tường minh cần định nghĩa cách kết hợp với các quy tắc cho phép, điều kiện và giới hạn tổ chức.

Ví dụ, nếu chính sách tổ chức cấm xuất dữ liệu khi tenant bị tạm dừng, việc một vai trò cấp `contract:export` không được âm thầm bỏ qua lệnh cấm đó. Cơ chế kết hợp phải phản ánh đúng ý nghĩa này.

Cũng cần tránh suy luận rằng điều kiện của một grant không thỏa mãn luôn tương đương một lệnh cấm toàn cục. Nó có thể chỉ có nghĩa grant đó không cấp quyền; quyền từ nguồn khác còn phải được đánh giá theo mô hình đã định.

## 6. Thiết lập điểm thực thi bao phủ các đường truy cập

### 6.1. Bảo vệ phía server

Ẩn nút xuất dữ liệu trên giao diện không bảo vệ API xuất. Client có thể gọi API trực tiếp.

Điểm thực thi cần đứng trước nơi dữ liệu được trả về hoặc tác động nghiệp vụ được tạo ra. Nó phải kiểm tra hành động thực tế, không chỉ sự hiện diện của một phiên đăng nhập.

Các đường đọc, ghi, tải tệp, xuất báo cáo, thao tác hàng loạt và chạy job nền đều có thể cần kiểm tra tương ứng.

### 6.2. Endpoint mới phải có chính sách

Một hệ thống có thể áp dụng cơ chế chặn toàn bộ endpoint được bảo vệ, sau đó khai báo những endpoint được phép và điều kiện của chúng.

Ví dụ danh mục minh họa:

```text
GET  /contracts/{id}        -> action contract:read
POST /contracts/{id}/close -> action contract:close
POST /contract-exports     -> action contract:export
```

Nếu xuất hiện `POST /contracts/{id}/share` nhưng chưa có ánh xạ hoặc chính sách, request không được tự bỏ qua kiểm tra.

Cần tính cả method, phiên bản API và đường dẫn thay thế. Bảo vệ một đường `GET` không tự bảo vệ mọi đường `POST` hoặc API nội bộ có cùng dữ liệu.

### 6.3. Không có đường đi vòng

Nếu gateway đã kiểm tra quyền nhưng backend có thể được gọi qua một đường không được bảo vệ, kiểm soát chưa bao phủ đầy đủ.

Các tầng có thể chia sẻ trách nhiệm, nhưng phải biết tầng nào xác thực danh tính, tầng nào đánh giá quyền tài nguyên và tầng nào ngăn đường gọi trực tiếp vượt kiểm tra.

CORS, vị trí mạng hoặc một header có tên “internal” không thay thế quyết định phân quyền cho bên gọi.

## 7. Tài nguyên công khai cũng phải được khai báo rõ

Deny by default không loại trừ nội dung công khai. Nó yêu cầu lựa chọn công khai phải có chủ đích.

Ví dụ, một trang giới thiệu sản phẩm có thể cho phép người chưa đăng nhập thực hiện hành động đọc. Điều này không có nghĩa mọi tài nguyên trong cùng ứng dụng đều trở thành công khai.

Một khai báo khái niệm:

```text
subjectClass = anonymous
action = public-page:read
resourceScope = published-public-pages
effect = ALLOW
```

Các giới hạn vẫn quan trọng:

- Chỉ nội dung đã được đánh dấu công khai.
- Chỉ hành động cần thiết, chẳng hạn đọc.
- Không trả trường nội bộ hoặc dữ liệu riêng của tenant.
- Không cho phép cập nhật hoặc quản trị qua cùng ngoại lệ.
- Không dùng wildcard rộng khiến endpoint mới vô tình được mở.

Endpoint kiểm tra tình trạng hệ thống cũng cần đánh giá nội dung được trả về và đối tượng được phép xem. Một endpoint được dùng cho vận hành không mặc nhiên nên công khai cấu hình, kết nối hoặc thông tin nhạy cảm.

## 8. Thực thi theo tài nguyên và tenant

### 8.1. Không chỉ kiểm tra tên quyền

Nếu Lan có `contract:read`, hệ thống vẫn phải biết quyền đọc áp dụng cho những hợp đồng nào.

Mã giả:

```text
function readContract(request, credential):
    actor = authenticateAndValidate(credential)
    context = establishVerifiedTenantContext(actor, request.tenantId)

    contract = repository.findByTenantAndId(
        context.tenantId,
        request.contractId
    )

    if contract is absent:
        return unavailableResourceResponse()

    decision = authorize(
        actor = actor,
        action = "contract:read",
        resource = contract,
        context = context
    )

    if decision.type != "ALLOW":
        recordDeniedAttempt(actor, context, decision)
        denyWithoutReturningContract()

    requireAllObligationsAreEnforceable(decision)
    return applyAuthorizedView(contract, decision)
```

Một ID tài nguyên khó đoán không thay cho kiểm tra. Một request hợp lệ về định dạng cũng không chứng minh quyền sở hữu.

### 8.2. Tạo tài nguyên phải có phạm vi hợp lệ

Với tạo mới, tài nguyên chưa tồn tại để kiểm tra chủ sở hữu. Hệ thống cần xác lập tenant hoặc vùng chứa mà chủ thể được phép tạo trong đó, rồi gán quyền sở hữu từ ngữ cảnh được chấp nhận.

Không cho phép payload lựa chọn tùy ý tenant đích hoặc người sở hữu để tạo đối tượng ngoài phạm vi của bên gọi.

### 8.3. Thao tác hàng loạt

Với danh sách tài nguyên, cần đánh giá phạm vi cho mọi phần tử.

Nếu hợp đồng API là xử lý toàn bộ hoặc không xử lý gì, mọi điều kiện quyền cần được xác nhận trước khi tạo các tác động không được phép xảy ra từng phần.

Nếu API cho phép kết quả từng phần, cách trả kết quả phải được thiết kế tường minh, chỉ xử lý các đối tượng được cấp quyền và không tiết lộ dữ liệu ngoài phạm vi. Không mặc định phần tử đầu tiên hợp lệ nghĩa là cả danh sách hợp lệ.

## 9. Fail closed khi không thể xác minh điều kiện bắt buộc

### 9.1. Lỗi không phải là quyết định cho phép

Một xử lý lỗi nguy hiểm:

```text
try:
    return policyService.isAllowed(request)
catch:
    return true
```

Khi dịch vụ chính sách gặp lỗi, toàn bộ lớp bảo vệ có thể bị vô hiệu hóa.

Hướng xử lý cần giữ được mặc định từ chối:

```text
try:
    decision = policyService.evaluate(request)
catch:
    recordAuthorizationDependencyFailure()
    return DENY

if decision is missing or malformed:
    return DENY

return decision only if it is valid for the current request
```

Không nên coi danh sách quyền `null` là “không giới hạn”, lỗi đọc thành viên là “thành viên mặc định”, hoặc action không nhận diện được là “hành động thông thường”.

### 9.2. Sử dụng cache có giới hạn

Cache có thể cung cấp một quyết định hoặc dữ liệu quyền còn hợp lệ theo chính sách đã định. Đây không phải lý do để dùng bất kỳ kết quả cho phép cũ nào khi phụ thuộc lỗi.

Cần xác định:

- Khóa cache gồm chủ thể, hành động, tài nguyên và phạm vi nào.
- Kết quả được tái sử dụng trong bao lâu.
- Điều kiện nào khiến kết quả mất hiệu lực.
- Có sự kiện thu hồi hoặc phiên bản chính sách cần kiểm tra không.
- Hành động nhạy cảm có bắt buộc dữ liệu mới hơn không.

Nếu bằng chứng bắt buộc đã quá hạn và không thể làm mới, không nên kéo dài hiệu lực vô hạn chỉ để request tiếp tục chạy.

### 9.3. Khả năng hoạt động và cơ chế khẩn cấp

Để giảm gián đoạn, hệ thống có thể dùng dự phòng, kiểm tra tính hợp lệ của cấu hình trước triển khai và thiết kế nguồn dữ liệu quyền có độ sẵn sàng phù hợp.

Nếu cần truy cập khẩn cấp, phải có chính sách riêng về người được dùng, phạm vi, thời hạn, điều kiện và audit. Một cơ chế khẩn cấp được bảo vệ vẫn là quyền cho phép có chủ đích; nó khác với việc bỏ qua mọi kiểm tra khi có lỗi.

## 10. Áp dụng cho workload và dịch vụ nội bộ

Một danh tính dịch vụ được xác thực không mặc nhiên có quyền gọi mọi API nội bộ.

Ví dụ, workload `report-reader` cần đọc hợp đồng trong phạm vi báo cáo. Nếu nó gọi API thay đổi vai trò người dùng, kết quả mặc định phải là từ chối trừ khi có một quyền hợp lệ cho hành động đó.

Chính sách cần nhận diện cả môi trường và phạm vi:

```text
subject = report-reader-prod
action = contract:read-for-report
resourceScope = báo cáo đã được cấp
tenantScope = tenant được chấp nhận cho tác vụ
```

Không sử dụng danh tính môi trường thử nghiệm cho sản xuất hoặc một API key toàn quyền cho mọi workload chỉ vì các dịch vụ nằm trong cùng cụm.

Khi dịch vụ thao tác thay người dùng, cần một cơ chế ủy nhiệm hợp lệ. Quyền kỹ thuật của dịch vụ không được tự biến thành quyền nghiệp vụ rộng hơn cho request của người dùng.

Với job nền, nếu thiếu tenant context hoặc thông tin ủy nhiệm cần thiết, không chuyển sang chế độ “xử lý tất cả”. Job cần thất bại theo cách có thể theo dõi và phục hồi có kiểm soát.

## 11. Chính sách và quyền cũng có vòng đời

### 11.1. Khởi tạo mặc định an toàn

Một tài khoản hoặc vai trò mới không nên tự có quyền quản trị chỉ vì chưa có cấu hình quyền.

Nếu ứng dụng cần một nhóm quyền cơ sở cho thành viên mới, đó phải là một phép cấp được định nghĩa rõ với phạm vi thích hợp. “Mặc định có quyền cơ sở theo chính sách” khác với “không tìm thấy cấu hình nên cho phép mọi thứ”.

Bài toán tạo quản trị viên đầu tiên cần một quy trình khởi tạo có thẩm quyền, giới hạn mục đích và phạm vi. Không giải quyết bằng một endpoint công khai cho phép bất kỳ ai nhận quyền quản trị khi hệ thống chưa có admin.

### 11.2. Thay đổi và thu hồi

Khi quyền bị thu hồi, cần xét cả vai trò trực tiếp, nhóm kế thừa, quyền trên tài nguyên và grant tạm thời.

Nếu một nguồn cấp khác vẫn hợp lệ, chủ thể có thể còn quyền theo mô hình kết hợp. Vì vậy, một kết quả cho phép phải giải thích được quyền đến từ đâu, thay vì chỉ báo rằng “không thấy bị cấm”.

Phiên, token và cache có thể giữ thông tin cũ. Thời gian quyền bị thu hồi thực sự có tác dụng phải được hiểu và kiểm chứng ở các điểm thực thi liên quan.

### 11.3. Triển khai tính năng mới

Một tính năng được bảo vệ cần có ánh xạ hành động, chính sách, điểm thực thi và kiểm thử quyền trước khi mở sử dụng.

Khi chính sách lỗi cú pháp hoặc tham chiếu sai hành động, hệ thống cần phát hiện trong quá trình kiểm tra và triển khai. Không sửa lỗi bằng cách mở một ngoại lệ rộng cho toàn ứng dụng.

## 12. Audit và phản hồi từ chối

Audit giúp phân biệt truy cập thiếu quyền với lỗi vận hành.

Một bản ghi minh họa:

```json
{
  "subjectId": "user-lan",
  "tenantId": "tenant-an-binh",
  "action": "contract:export",
  "resourceId": "project-27",
  "decision": "DENY",
  "reasonCode": "NO_APPLICABLE_ALLOW",
  "policyVersion": "policy-24",
  "correlationId": "corr-92"
}
```

Các mã nguyên nhân có thể phân biệt thiếu quyền, thiếu thuộc tính, phạm vi không khớp, quyền hết hạn hoặc phụ thuộc bị lỗi. Không ghi nguyên token, mật khẩu hay bí mật trong log.

Thông báo trả cho client cần phù hợp với hợp đồng API và chính sách tiết lộ thông tin. Không cần công khai toàn bộ lý do nội bộ, tên chính sách hoặc sự tồn tại của tài nguyên mà người dùng không được biết.

Quan trọng hơn, việc trả lỗi phải xảy ra trước khi dữ liệu nhạy cảm hoặc side effect ngoài quyền được tạo ra. Response từ chối không bù được việc tệp xuất đã được gửi sang một đích không được phép.

## 13. Ma trận kiểm thử mặc định từ chối

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Danh tính hợp lệ có quyền đúng hành động và tài nguyên | Được thực hiện trong phạm vi |
| Đã đăng nhập nhưng không có grant phù hợp | Bị từ chối |
| Endpoint mới chưa có ánh xạ chính sách | Không tự được bỏ qua kiểm tra |
| Action không được nhận diện | Không rơi xuống nhánh cho phép |
| Client tự khai vai trò hoặc tenant của tài nguyên | Không được dùng làm căn cứ cấp quyền |
| Người có quyền trong tenant A gọi tài nguyên tenant B | Bị chặn theo phạm vi |
| Danh sách quyền bị thiếu hoặc đọc lỗi | Không được hiểu là quyền không giới hạn |
| PDP trả kết quả không hợp lệ hoặc không phản hồi | Không tự cho phép truy cập được bảo vệ |
| Quyết định cache đã hết hiệu lực | Không tiếp tục dùng ngoài chính sách |
| Một phần tử trong thao tác hàng loạt thiếu quyền | Xử lý theo hợp đồng đã định, không tạo tác động ngoài quyền |
| Gọi trực tiếp backend qua đường khác gateway | Vẫn chịu các kiểm tra cần thiết |
| Tài nguyên công khai được gọi để đọc | Được phép theo khai báo công khai |
| Ngoại lệ công khai bị dùng để sửa hoặc quản trị | Không được mở rộng ngoài hành động đã cấp |
| Workload hợp lệ gọi API ngoài nhiệm vụ | Bị từ chối |
| Thiếu tenant trong một job bắt buộc có tenant | Không xử lý dữ liệu toàn hệ thống |

Nên kiểm tra cả side effect: dữ liệu có bị sửa, tệp có được tạo, thông báo có được gửi và audit có ghi đúng không. Chỉ kiểm tra mã response là chưa đủ.

Trong hệ thống đang hoạt động, có thể đánh giá chính sách mới trên phạm vi nhỏ hoặc quan sát kết quả trước khi thực thi rộng. Việc chuyển đổi phải có tiêu chí rõ ràng, không để một chế độ bỏ qua kiểm tra trở thành cấu hình lâu dài ngoài dự kiến.

## 14. Áp dụng vào tình huống của Lan

Khi Lan đọc hợp đồng thuộc dự án được phân công, hệ thống có thể tìm được quyền đọc phù hợp, xác nhận tenant và giới hạn dữ liệu trả về.

Khi Lan gọi API xuất dữ liệu mà không có `contract:export`, hệ thống từ chối vì chưa có căn cứ cho phép. Nó không cần chờ một quản trị viên viết thêm quy tắc cấm riêng cho Lan.

Nếu dịch vụ phân quyền bị lỗi đúng lúc Lan gọi API xuất, request không được tự chạy với lý do duy trì hoạt động. Một kết quả cho phép chỉ được sử dụng nếu còn hợp lệ theo cơ chế đã thiết kế cho chính hành động và phạm vi đó.

Deny by default được duy trì khi mọi đường truy cập được bảo vệ đều phải đi qua một quyết định cho phép có căn cứ, các điều kiện bắt buộc được thực thi và khoảng trống chính sách không tự trở thành quyền.
