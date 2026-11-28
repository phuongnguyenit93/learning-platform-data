# Explicit identity context

## 1. Explicit identity context là gì?

**Explicit identity context** là ngữ cảnh danh tính được biểu diễn rõ ràng để một thành phần biết ai đang yêu cầu hành động, bằng chứng xác thực đến từ đâu, phạm vi nào đang được sử dụng và thông tin nào còn đủ tin cậy cho quyết định hiện tại.

Trong IAM theo hướng Zero Trust, việc request đến từ mạng nội bộ, một VPN hoặc một máy chủ quen thuộc không tự tạo ra quyền truy cập. Thành phần thực thi cần có căn cứ cụ thể về danh tính và quyền đối với tài nguyên đang xét.

Ví dụ, dịch vụ báo cáo nhận yêu cầu “xuất dữ liệu của tenant An”. Chỉ biết request đến từ API Gateway chưa trả lời được:

- Người dùng nào khởi tạo yêu cầu?
- Dịch vụ nào đang trực tiếp gọi?
- Tenant An có phải phạm vi người dùng được phép hoạt động không?
- Danh tính đã được xác thực bằng cách nào và vào thời điểm nào?
- Quyền xuất dữ liệu còn hiệu lực không?
- Dịch vụ nhận có phải đích được phép nhận bằng chứng hoặc ủy quyền này không?

Explicit identity context làm rõ những câu hỏi đó. Nó không phải một loại token duy nhất, một chuẩn JSON bắt buộc hay một quyết định ALLOW được mang đi khắp hệ thống. Nó là cách tổ chức và sử dụng bằng chứng danh tính sao cho mỗi nơi ra quyết định hiểu được ý nghĩa, nguồn và giới hạn của bằng chứng.

## 2. Tách xác thực, ngữ cảnh và phân quyền

Ba lớp sau có liên hệ nhưng có nhiệm vụ khác nhau:

| Lớp | Câu hỏi chính | Kết quả minh họa |
|---|---|---|
| Xác thực | Credential hoặc phiên này chứng minh danh tính nào? | Subject nội bộ `u-174` đã được xác thực qua nguồn được chấp nhận |
| Ngữ cảnh danh tính | Danh tính đó đang tham gia request với vai trò gì, phạm vi nào và bằng chứng nào? | Người dùng `u-174`, caller `svc-reports`, tenant `tenant-an` |
| Phân quyền | Với tài nguyên và hành động cụ thể, có cho phép không? | Cho phép `document.read` đối với tài liệu thuộc tenant An |

Một context hợp lệ không đồng nghĩa mọi hành động đều được phép. Người dùng có thể đã được xác thực mạnh nhưng không có quyền xuất dữ liệu; một workload có credential hợp lệ nhưng không được thao tác trong tenant đang yêu cầu.

Ngược lại, role được gán trong cơ sở dữ liệu cũng không thay thế xác thực. Máy chủ phải biết role thuộc về subject nào và subject đó có thực sự là bên đang thực hiện request hay không.

Một quyết định có thể được biểu diễn ở mức khái niệm:

```text
decision = policy(
    identity_context,
    requested_action,
    resource_context,
    current_authorization_state
)
```

`identity_context` cung cấp bằng chứng về chủ thể và cách chủ thể tham gia. `resource_context` mô tả tài nguyên thật mà máy chủ đã phân giải. `current_authorization_state` gồm những trạng thái cần kiểm tra như membership, quyền đã bị thu hồi hoặc tenant bị khóa. Không lấy tất cả các đầu vào này từ một JSON do client tự gửi.

## 3. Những thành phần cần làm rõ

Không có danh sách field áp dụng cho mọi ứng dụng. Một context nên đủ cho chính sách của hệ thống, có nguồn rõ ràng và tránh thu thập dữ liệu không cần thiết.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Subject | Chủ thể mà quyền đang được đánh giá | Người dùng `u-174` hoặc workload `svc-importer` |
| Caller trực tiếp | Bên đã xác thực ở kết nối hoặc request hiện tại | Dịch vụ `svc-reports` |
| Loại chủ thể | Giúp tránh trộn người dùng, workload và anonymous | USER, WORKLOAD |
| Nguồn danh tính | Miền xác thực hoặc nguồn phát hành được tin cậy | Kết nối danh tính đã cấu hình |
| Tenant hoặc tổ chức | Phạm vi tổ chức đang được yêu cầu và đã được kiểm tra đến mức nào | `tenant-an` |
| Bằng chứng xác thực | Cách, thời điểm và mức xác thực có ý nghĩa trong hệ thống | Xác thực gần đây bằng phương thức được chấp nhận |
| Đích sử dụng | Thành phần nào được phép tiếp nhận credential hoặc ủy quyền | `documents-api` |
| Ủy quyền | Caller được hành động thay mặt ai và trong giới hạn nào | Đọc báo cáo của người dùng trong một tenant |
| Thuộc tính có liên quan | Đầu vào chính sách từ nguồn được chấp nhận | Membership version, trạng thái thiết bị |
| Thông tin truy vết | Liên kết request và quyết định để điều tra | Request ID, decision ID |

Request ID giúp truy vết nhưng không phải bằng chứng xác thực. Tenant ID giúp chỉ ra phạm vi nhưng không chứng minh membership. Một field mang tên `verified` cũng không có giá trị nếu người gọi tự đặt nó.

Đối với đăng nhập liên kết, định danh bên ngoài cần được hiểu trong phạm vi nguồn phát hành. Không mặc định hai giá trị subject giống nhau từ hai nguồn là cùng một người. Email và tên hiển thị phù hợp cho nhiều nhu cầu giao diện, nhưng không nên được dùng thay khóa danh tính ổn định.

## 4. Subject, caller và actor không phải lúc nào cũng là một

### 4.1. Người dùng gọi trực tiếp

Trong một request đơn giản, client gửi access token đại diện cho người dùng và API xác thực token đó. Subject của quyết định là người dùng. Danh tính phần mềm client, nếu được cung cấp và kiểm chứng, là một thành phần khác.

Không suy ra danh tính ứng dụng client từ `User-Agent` hoặc một header tự khai. Chúng có thể phục vụ chẩn đoán nhưng không đủ làm căn cứ cấp quyền.

### 4.2. Dịch vụ hành động thay người dùng

Giả sử:

```text
Lan -> Reports API -> Documents API
```

Ở Documents API:

- Lan có thể là subject mà quyền truy cập tài liệu cần được đánh giá.
- Reports API là caller trực tiếp.
- Quan hệ ủy quyền phải giải thích vì sao Reports API được phép thực hiện hành động thay Lan.
- Tài nguyên và tenant đích vẫn cần được kiểm tra tại Documents API.

Nếu Documents API chỉ biết “caller là Reports API” rồi sử dụng toàn bộ quyền quản trị của Reports API để đáp ứng mọi yêu cầu từ người dùng, dịch vụ có thể bị biến thành một bên trung gian sử dụng quyền rộng hơn quyền mà người dùng thực sự có. Đây là vấn đề thường được mô tả bằng khái niệm confused deputy.

Cách xử lý không phải chỉ thêm `X-User-Id`. Dịch vụ nhận cần có bằng chứng hoặc cơ chế ủy quyền mà nó thực sự tin cậy, ràng buộc với subject, caller, đích sử dụng và phạm vi thích hợp.

### 4.3. Workload tự hoạt động

Một job đồng bộ định kỳ có thể không có người dùng hiện diện. Subject lúc này là workload với grant của chính nó. Không cần tạo một người dùng giả hoặc gán `user_id=admin` để đi qua luồng kiểm tra.

Nếu job được tạo từ một yêu cầu của Lan, thông tin “Lan đã khởi tạo” có thể cần cho audit, nhưng nó không tự trở thành quyền vĩnh viễn cho job. Thiết kế phải xác định job chạy theo ủy quyền của Lan, theo grant riêng của workload hay theo một mô hình được phê duyệt khác.

Các tên gọi subject, actor và caller cần được định nghĩa trong hệ thống. Nếu một dịch vụ dùng `actor` để chỉ người khởi tạo còn dịch vụ khác hiểu là workload hiện tại, audit và phân quyền có thể trở nên mâu thuẫn dù cùng dùng một tên field.

## 5. Tạo context ở một ranh giới tin cậy rõ ràng

Một luồng xử lý điển hình:

```text
Request và credential
        |
        v
Xác minh credential/phiên và nguồn phát hành
        |
        v
Ánh xạ thành danh tính nội bộ
        |
        v
Phân giải tenant, caller và ủy quyền
        |
        v
Bổ sung thuộc tính từ nguồn có thẩm quyền
        |
        v
Tạo identity context nội bộ
        |
        v
Đánh giá chính sách đối với hành động và tài nguyên
```

### 5.1. Xác minh bằng chứng trước khi sử dụng claim

Giải mã payload của token chỉ giúp đọc dữ liệu. Nó không tự xác minh nguồn phát hành, tính toàn vẹn, thời hạn hoặc đích sử dụng.

Cơ chế xác thực cần thực hiện các kiểm tra phù hợp với loại credential: ví dụ nguồn được chấp nhận, chữ ký theo cấu hình tin cậy, thời hạn, đích nhận và trạng thái phiên khi hệ thống yêu cầu. Không chọn thuật toán hoặc nguồn khóa tùy ý theo dữ liệu chưa tin cậy từ token.

Với phiên phía máy chủ, ứng dụng cần kiểm tra session còn hợp lệ rồi tra cứu subject tương ứng. Không coi một cookie chứa user ID là bằng chứng nếu không có cơ chế bảo vệ và xác thực phù hợp.

Credential đăng nhập và credential gọi API có mục đích khác nhau. Không mặc định một token dùng để chứng minh kết quả đăng nhập cũng có thể được dùng như access token của mọi API.

### 5.2. Phân giải tenant từ yêu cầu

Tenant ID trong URL hoặc header là yêu cầu chọn phạm vi. Máy chủ cần kết hợp nó với danh tính đã xác thực và chính sách, thay vì coi việc client khai tenant là bằng chứng người dùng thuộc tenant.

Nếu credential đã bị ràng buộc vào tenant A mà request nhắm tenant B, phải xử lý theo hợp đồng đã xác định, thường là từ chối khi không có cơ chế hợp lệ cho việc đổi phạm vi. Không âm thầm thay tenant trong context mà bỏ qua ràng buộc của credential.

### 5.3. Bổ sung thuộc tính có nguồn gốc

Membership có thể đến từ kho quyền; trạng thái thiết bị có thể đến từ dịch vụ đánh giá thiết bị; trạng thái tài khoản có thể đến từ hệ thống danh tính.

Mỗi thuộc tính cần có ý nghĩa, nguồn và thời điểm đánh giá phù hợp. Hai nguồn báo cùng tên role không có nghĩa chúng có cùng thẩm quyền cấp role đó.

Không đưa tất cả dữ liệu hồ sơ vào context chỉ vì có thể đọc được. Context lớn làm tăng dữ liệu nhạy cảm lan truyền, chi phí xử lý và nguy cơ các dịch vụ hiểu sai thuộc tính.

## 6. Ví dụ context nội bộ

Đây là một schema minh họa do ứng dụng tự định nghĩa, không phải mẫu access token hoặc một chuẩn claim bắt buộc.

```json
{
  "subject": {
    "kind": "USER",
    "id": "u-174",
    "identity_domain": "company-login"
  },
  "caller": {
    "kind": "WORKLOAD",
    "id": "svc-reports"
  },
  "tenant_id": "tenant-an",
  "authentication": {
    "authenticated_at": "2026-05-10T08:20:00Z",
    "assurance_profile": "strong-user-auth",
    "evidence_source": "validated-user-session"
  },
  "delegation": {
    "recipient": "documents-api",
    "permitted_actions": ["document.read"],
    "expires_at": "2026-05-10T08:30:00Z"
  },
  "attributes": {
    "membership_id": "m-508",
    "membership_version": 12
  },
  "request_id": "req-728"
}
```

Các thời điểm và tên profile chỉ là dữ liệu ví dụ. Hệ thống phải có quy tắc ánh xạ nguồn bằng chứng sang các giá trị này, không cho client tự chọn `strong-user-auth`.

Cần hiểu các giới hạn của context:

- `subject.id` chỉ có ý nghĩa nếu được tạo sau khi xác minh và ánh xạ danh tính.
- `caller.id` cần được lấy từ cơ chế xác thực workload, không phải tên service do caller tự khai.
- `tenant_id` cần khớp phạm vi được phép và tài nguyên.
- `permitted_actions` là giới hạn của ủy quyền trong ví dụ, không bỏ qua các điều kiện phân quyền khác.
- `membership_version` là thông tin phục vụ đối chiếu; nó không chứng minh membership chưa bị thu hồi nếu không được kiểm tra.
- `request_id` chỉ phục vụ liên kết quan sát.

Nếu context này được truyền qua mạng như dữ liệu, tính toàn vẹn, nguồn gửi, người nhận và hiệu lực của nó phải được bảo vệ bởi hợp đồng giao tiếp. Không gửi JSON trên rồi coi mọi service trong mạng nội bộ đều có quyền tạo bản tương đương.

## 7. Truyền context qua nhiều dịch vụ

### 7.1. Không tin header chỉ vì nằm trong mạng nội bộ

Một thiết kế dễ sai:

```http
X-User-Id: u-174
X-Tenant-Id: tenant-an
X-Role: ADMIN
```

Nếu service chỉ đọc ba header này và cấp quyền, bất kỳ bên nào có thể gửi request tới service đều có thể tự khai danh tính hoặc đặc quyền.

Một gateway đáng tin cậy có thể là nơi xác thực ban đầu, nhưng các điều kiện cần được thực thi gồm:

- Xóa hoặc ghi đè những header danh tính không đáng tin cậy từ client.
- Xác thực bên gửi tại kết nối tới dịch vụ đích.
- Bảo đảm không có đường gọi tắt làm bỏ qua cơ chế bảo vệ.
- Có hợp đồng về nguồn, ý nghĩa và phạm vi context.
- Ngăn một service không được phép tự tạo context của người khác.
- Kiểm tra phân quyền tại nơi thực thi hành động hoặc tại điểm thực thi không thể bị bỏ qua.

Không thể chỉ cấu hình gateway thêm header rồi kết luận toàn bộ hệ thống đã có context đáng tin cậy.

### 7.2. Chọn cơ chế phù hợp với ranh giới

Một số cách truyền có thể được áp dụng tùy kiến trúc:

| Cách truyền | Điều cần bảo đảm |
|---|---|
| Service đích tự xác minh credential hợp lệ cho nó | Credential đúng đích, phạm vi và loại sử dụng |
| Context được bảo vệ bởi bên trung gian có thẩm quyền | Nguồn ký hoặc nguồn gửi được chấp nhận, người nhận, hiệu lực và quyền tạo context |
| Credential ủy quyền dành cho service kế tiếp | Subject, caller, tenant và phạm vi không bị mở rộng ngoài phép |
| Tham chiếu tới trạng thái phía máy chủ | Người gọi được xác thực và không thể dùng tham chiếu để đọc context của request khác |

Một kết nối mTLS có thể xác thực workload trình bày credential tại kết nối đó theo cấu hình tin cậy. Nó không tự chứng minh danh tính người dùng gốc hoặc cho caller quyền hành động thay mọi người dùng.

Tương tự, context có chữ ký không tự bảo đảm dữ liệu còn mới hoặc hành động được phép. Service nhận vẫn phải hiểu bên ký được quyền khẳng định những thuộc tính nào và kiểm tra các ràng buộc cần thiết.

### 7.3. Thu hẹp khi đi qua một ranh giới mới

Credential có hiệu lực cho Reports API không nên mặc nhiên được chuyển tiếp đến Documents API. Đích nhận cần được cấp bằng chứng hoặc ủy quyền phù hợp với chính nó.

Khi có nhiều tầng dịch vụ, không tự mở rộng quyền:

```text
Người dùng được đọc tài liệu trong tenant An
        |
        v
Reports API được yêu cầu đọc để tạo báo cáo
        |
        v
Documents API chỉ nhận quyền đọc cần thiết trong tenant An
```

Không biến yêu cầu đọc thành quyền xóa tài liệu, không đổi tenant và không dùng danh tính vận hành toàn nền tảng để thay thế một ủy quyền thiếu điều kiện.

## 8. Độ mới, thu hồi và xác thực bổ sung

Context là ảnh chụp của một số bằng chứng ở một thời điểm, không phải sự thật bất biến.

Các thay đổi có thể xảy ra sau khi context được tạo:

- Người dùng bị khóa hoặc rời tenant.
- Role được gỡ.
- Thiết bị không còn đạt điều kiện.
- Phiên bị thu hồi.
- Tenant ngừng hoạt động.
- Credential workload hết hiệu lực.
- Chính sách của hành động được cập nhật.

Thiết kế cần chọn dữ liệu nào có thể dùng từ snapshot, dữ liệu nào phải tra cứu lại và độ trễ tối đa được chấp nhận. Access token còn hạn không tự bảo đảm các quyền hiện tại không thay đổi.

Đối với hành động nhạy cảm, một chính sách có thể yêu cầu xác thực gần đây hoặc một mức bảo đảm phù hợp. Cần phân biệt thời điểm phát hành token với thời điểm người dùng thực sự xác thực. Việc làm mới token không tự chứng minh người dùng vừa xác thực lại.

Các nhãn phương thức hoặc mức xác thực phải được diễn giải theo nguồn và cấu hình được chấp nhận. Không suy ra “đủ mạnh” chỉ từ một chuỗi ký tự do client cung cấp.

Xác thực bổ sung chỉ giải quyết những điều kiện mà nó có thể chứng minh. Một người không còn membership không thể lấy lại quyền bằng cách thực hiện MFA. Chính sách có thể yêu cầu step-up cho một người đã đủ điều kiện cơ bản; nó không dùng step-up để bỏ qua quyền bị thu hồi.

Với stream hoặc tác vụ kéo dài, cần xác định điểm đánh giá lại thay vì giả định kết quả ở đầu phiên còn đúng đến cuối. Mức nhất quán cần tương xứng với hành động và tác động của dữ liệu.

## 9. Thực thi context trong ứng dụng

Một cách tổ chức là tạo context nội bộ sau xác thực, đưa nó rõ ràng vào luồng phân quyền và không cho tầng nghiệp vụ tự đọc danh tính từ header.

Pseudocode minh họa:

```text
handleReadDocument(request):
    credential = extractCredential(request)
    verifiedIdentity = authenticate(credential)

    targetTenant = resolveRequestedTenant(request)
    caller = authenticateImmediateCaller(request)
    delegation = validateDelegationIfRequired(
        verifiedIdentity, caller, targetTenant, recipient="documents-api"
    )

    identityContext = buildContextFromVerifiedEvidence(
        verifiedIdentity, caller, targetTenant, delegation
    )

    resource = loadDocumentWithinTenant(
        targetTenant.id, request.documentId
    )

    currentState = loadAuthorizationState(identityContext, resource)
    decision = evaluate(
        identityContext, action="document.read", resource, currentState
    )

    if decision is not ALLOW:
        rejectUsingApiPolicy(decision)

    return renderPermittedFields(resource, decision)
```

Đây là pseudocode về trách nhiệm, không quy định mọi ứng dụng đều phải xác thực người dùng và workload bằng hai credential giống nhau. Đối với luồng người dùng trực tiếp, caller có thể được biểu diễn khác; đối với job không có người dùng, subject là workload và không giả lập một phiên người dùng.

Một số nguyên tắc triển khai:

**Dùng context bất biến trong một lần đánh giá.** Không để một đoạn code thay `tenant_id` hoặc `subject_id` rồi tái sử dụng kết quả ALLOW cũ. Nếu thay đổi phạm vi, cần tạo yêu cầu đánh giá mới.

**Giới hạn quyền tạo context.** Chỉ thành phần xác thực hoặc adapter tin cậy tạo đối tượng đã được xác minh. Một hàm nhận DTO từ client không được chuyển thẳng DTO đó thành security context.

**Bảo toàn khi thực thi bất đồng bộ.** Không dựa vào biến toàn cục dùng chung giữa request. Nếu sử dụng ngữ cảnh gắn với luồng thực thi, phải quản lý truyền và dọn đúng vòng đời; pool thread hoặc task bất đồng bộ có thể gây lẫn danh tính nếu dùng sai.

**Xử lý trường hợp thiếu bằng chứng theo chính sách.** Thiếu thuộc tính bắt buộc không được chuyển thành đặc quyền mặc định. Tuy nhiên, không cần bắt mọi endpoint công khai có cùng dữ liệu thiết bị như một endpoint quản trị; yêu cầu phụ thuộc hành động đã định nghĩa.

**Ràng buộc truy vấn với phạm vi đã kiểm tra.** Context đúng vẫn không cứu được truy vấn bỏ tenant scope hoặc dùng một ID tài nguyên khác sau khi đã phân quyền.

## 10. Context trong cache, queue và audit

### 10.1. Cache quyết định truy cập

Cache chỉ theo user ID có thể làm một kết quả cho tenant A bị dùng cho tenant B hoặc cho hành động khác.

Khóa cache cần phản ánh những đầu vào có ảnh hưởng tới quyết định, chẳng hạn:

```text
subject
caller hoặc ủy quyền nếu chính sách sử dụng
tenant
action
resource hoặc phạm vi tài nguyên
phiên bản quyền/chính sách liên quan
```

Không nhất thiết phải nhồi mọi thuộc tính vào một chuỗi khóa. Có thể sử dụng phiên bản hoặc cơ chế vô hiệu hóa phù hợp, nhưng kết quả được dùng lại phải còn đúng với các đầu vào hiện tại và thời hạn đã quy định.

### 10.2. Queue và job

Thông điệp trong queue có thể chứa subject, tenant và request ID để tiếp tục công việc. Những trường đó cần được bảo vệ theo hợp đồng producer–consumer và kiểm tra quyền lúc thực thi theo mô hình đã chọn.

Không coi việc một message từng được xếp hàng là quyền thực hiện vô thời hạn. Cần phân biệt dữ liệu truy vết người khởi tạo với grant hiện hành của job.

Nếu dùng ủy quyền có thời hạn, job hết thời hạn phải được xử lý theo chính sách: dừng, xin một lần ủy quyền mới hoặc chuyển sang một luồng có thẩm quyền riêng. Không tự gia hạn quyền bằng cách sửa thời gian trong payload.

### 10.3. Audit và tối thiểu hóa dữ liệu

Audit hữu ích khi thể hiện được:

- Subject và caller đã được xác minh.
- Tenant, hành động và tài nguyên.
- Nguồn hoặc loại bằng chứng cần thiết cho việc giải thích.
- Quyết định, lý do và phiên bản chính sách.
- Mã liên kết request và thời điểm đánh giá.

Không ghi access token, cookie phiên, mật khẩu hoặc toàn bộ hồ sơ người dùng vào log. Nhiều context chứa dữ liệu có thể liên kết hoạt động của một người; việc lan truyền và lưu giữ cần giới hạn theo mục đích và quyền truy cập đã xác định.

Audit là bằng chứng về quyết định đã diễn ra. Việc có một dòng log “user=admin” không làm cho quyết định đó đúng nếu danh tính đầu vào chưa được xác minh.

## 11. Ví dụ quyết định với cùng một người dùng

Giả sử Lan thuộc tenant An, có quyền đọc tài liệu và dùng Reports API để tạo báo cáo.

| Tình huống | Quyết định phù hợp |
|---|---|
| Context hợp lệ, caller được ủy quyền, tài liệu thuộc tenant An | Có thể ALLOW nếu các điều kiện chính sách khác đạt |
| Client tự gửi `X-Role: ADMIN` | Không sử dụng giá trị tự khai để cấp quyền |
| Credential dành cho Reports API được đưa tới API khác không chấp nhận đích đó | Từ chối credential cho luồng này |
| Caller được xác thực nhưng không có ủy quyền đọc thay Lan | Từ chối luồng thay mặt người dùng |
| Tenant trong request không khớp phạm vi credential | Từ chối hoặc yêu cầu luồng chọn phạm vi hợp lệ theo hợp đồng |
| Lan bị gỡ membership sau khi token được phát hành | Áp dụng cơ chế kiểm tra và thu hồi hiện hành; không tin snapshot vô hạn |
| Lan có quyền nhưng hành động xuất yêu cầu xác thực mới hơn | Yêu cầu xác thực bổ sung theo chính sách |
| Thiếu thuộc tính bắt buộc để đánh giá hành động nhạy cảm | Không mặc định cho phép |
| Job không có người dùng, dùng grant hợp lệ của workload | Đánh giá workload như chủ thể của chính nó |

Điểm cốt lõi là mọi bằng chứng chỉ có tác dụng trong ý nghĩa và phạm vi mà hệ thống chấp nhận. Cùng tên người dùng không làm hai request có cùng mức tin cậy, cùng tenant hoặc cùng quyền.

## 12. Những lỗi cần tránh

| Lỗi | Hệ quả | Hướng thiết kế |
|---|---|---|
| Tin caller vì IP nội bộ | Một workload bị chiếm quyền có thể giả danh bên khác | Xác thực caller và áp dụng quyền theo yêu cầu |
| Dùng email làm danh tính duy nhất trên mọi nguồn | Nhầm hoặc gộp chủ thể sai | Dùng định danh ổn định có phạm vi nguồn |
| Giải mã token rồi tin claim | Dữ liệu chưa được kiểm chứng trở thành quyền | Xác minh credential trước khi dựng context |
| Chỉ có user ID, không có tenant | Lẫn quyền giữa tổ chức | Biểu diễn và kiểm tra phạm vi tenant |
| Chỉ có service ID trong luồng thay người dùng | Quyền workload có thể che quyền người dùng | Tách subject, caller và ủy quyền |
| Chuyển tiếp một credential đến mọi service | Credential bị dùng sai đích và lan truyền quá rộng | Dùng bằng chứng đúng người nhận và phạm vi |
| Tin role snapshot mãi mãi | Quyền bị thu hồi vẫn tiếp tục được dùng | Có độ mới, hiệu lực và cơ chế vô hiệu hóa |
| Cho phép client ghi đè context nội bộ | Giả danh hoặc đổi tenant | Chỉ dựng context từ các nguồn đã được kiểm chứng |
| Dùng chung biến danh tính giữa request | Rò rỉ context và hành động sai chủ thể | Quản lý vòng đời context theo request/task |
| Ghi toàn bộ context kèm secret vào log | Mở thêm đường lộ credential và dữ liệu cá nhân | Ghi bằng chứng tối thiểu, có kiểm soát |

Explicit identity context giúp IAM biến các giả định mơ hồ thành đầu vào có thể đánh giá: chủ thể nào, caller nào, tenant nào, bằng chứng nào và hiệu lực đến đâu. Giá trị của nó đến từ nguồn đáng tin cậy, cách ràng buộc context với hành động và tài nguyên, cùng việc thực thi nhất quán tại những nơi dữ liệu thực sự được truy cập.
