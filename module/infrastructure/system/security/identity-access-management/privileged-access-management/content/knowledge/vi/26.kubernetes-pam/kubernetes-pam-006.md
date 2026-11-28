# Admission approval

## Mục tiêu bài học

Trong chương Kubernetes PAM của module Privileged Access Management (PAM), **admission approval** là cách gắn việc phê duyệt một thay đổi nhạy cảm với quyết định chấp nhận hoặc từ chối yêu cầu tại Kubernetes API.

Bài toán không dừng ở việc một người có quyền gọi API. Tổ chức còn cần biết thay đổi cụ thể đã được ai duyệt, áp dụng cho đối tượng nào, có còn hiệu lực không và có đúng nội dung được phép hay không.

Ví dụ, một kỹ sư có thể được quyền cập nhật Deployment trong một namespace. Điều đó không nên đồng nghĩa mọi thay đổi image, danh tính workload hoặc cấu hình nhạy cảm đều được phép mà không có kiểm soát bổ sung.

Bài học phân biệt cơ chế Kubernetes với mô hình approval do tổ chức xây dựng. Các bản ghi approval, tên controller và mã giả là thiết kế minh họa, không phải tính năng mặc định hoặc cấu hình hoàn chỉnh để triển khai vào production.

Sau bài học, bạn có thể:

- Phân biệt authentication, authorization, admission và phê duyệt của con người.
- Thiết kế approval gắn với đúng principal, cluster, đối tượng và thay đổi.
- Chọn cách kiểm tra phù hợp bằng policy hoặc validating webhook.
- Xử lý mutation, controller, retry, dry-run và thời hạn.
- Tránh việc annotation tự khai trở thành bằng chứng phê duyệt.
- Lưu bằng chứng từ quyết định approval tới kết quả thực tế.

## 1. Admission nằm ở đâu trong đường xử lý?

Admission diễn ra sau authentication và authorization, trước khi thay đổi được lưu. Nó áp dụng cho các thao tác thay đổi phù hợp và một số kết nối; các yêu cầu đọc như get, list, watch không đi qua lớp này. Vì vậy, không thể dùng admission để thay thế kiểm soát quyền đọc Secret. [Kubernetes: Admission Control](https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/)

Có thể hình dung luồng kiểm soát:

```text
Người hoặc workload gửi yêu cầu
             |
             v
Authentication: chủ thể là ai?
             |
             v
Authorization: được gọi thao tác này không?
             |
             v
Admission: nội dung và ngữ cảnh có được chấp nhận không?
             |
             v
Lưu thay đổi nếu các bước liên quan đều thành công
             |
             v
Controller và workload phản ứng với trạng thái mới
```

Một approval hợp lệ không biến một yêu cầu không có quyền thành yêu cầu có quyền. Ngược lại, có quyền cập nhật một đối tượng không đủ chứng minh thay đổi đã được phê duyệt theo quy trình của tổ chức.

PAM có thể tham gia ở hai vị trí khác nhau:

- Cấp khả năng gọi API trong một cửa sổ JIT.
- Cung cấp bằng chứng approval để admission kiểm tra thay đổi cụ thể.

Hai việc bổ trợ nhau. Không nên mặc nhiên cấp cluster-admin chỉ vì đã có một webhook kiểm tra approval.

### “Approval” không phải chờ một người ngay trong lời gọi admission

Thiết kế nên tách bước phê duyệt khỏi lời gọi API đang được kiểm tra. Khi approval chưa sẵn sàng, yêu cầu bị từ chối với thông tin hướng dẫn phù hợp; người dùng hoặc pipeline gửi lại sau khi approval hợp lệ.

Không giữ một lời gọi webhook trong nhiều phút để chờ người quản lý bấm duyệt. Điều đó tạo một phụ thuộc đồng bộ khó vận hành và không phù hợp với vai trò kiểm tra nhanh của admission.

## 2. Mối đe dọa mà admission approval cần xử lý

Giả sử một pipeline được phép cập nhật ứng dụng production. Người duyệt đã cho phép đổi image từ phiên bản A sang phiên bản B. Sau phê duyệt, một người sửa manifest để:

- Dùng image khác.
- Chọn một ServiceAccount mạnh hơn.
- Thêm volume chứa dữ liệu nhạy cảm.
- Tăng quyền của container.
- Đổi namespace hoặc đối tượng đích.
- Thêm một thay đổi RBAC không nằm trong kế hoạch.

Nếu hệ thống chỉ kiểm tra một annotation approved=true, mọi thay đổi trên có thể đi qua.

Do đó, điều cần được duyệt không phải một nhãn “đã duyệt”, mà là **một ý định thay đổi được xác định rõ** cùng các ràng buộc thực thi.

| Nguy cơ | Câu hỏi kiểm soát |
|---|---|
| Tự ghi annotation approved | Ai có thẩm quyền phát hành bằng chứng approval? |
| Dùng approval cho đối tượng khác | Approval có ràng buộc cluster, namespace, loại và tên đối tượng không? |
| Sửa manifest sau phê duyệt | Có kiểm tra nội dung hoặc phép biến đổi đã được duyệt không? |
| Dùng lại ở cluster khác | Bằng chứng có giới hạn audience hoặc cluster không? |
| Pipeline bị chiếm quyền | Principal thực thi còn bị giới hạn ngoài logic ứng dụng không? |
| Gửi lại đồng thời | Có phân biệt một kế hoạch với nhiều lần admission và kết quả commit không? |
| Bỏ qua policy bằng nhãn | Ai có quyền sửa nhãn chọn phạm vi hoặc ngoại lệ? |
| Tắt webhook | Ai có thể sửa cấu hình admission và thành phần thực thi? |

Mục tiêu không phải thêm bước bấm nút cho mọi thao tác. Mục tiêu là một thay đổi nhạy cảm không thể vượt quá thẩm quyền đã được xác định.

## 3. Mô hình phê duyệt ngoài đường admission

Một kiến trúc có thể gồm bốn thành phần:

```text
Người yêu cầu hoặc pipeline
    |
    | gửi kế hoạch thay đổi
    v
Hệ thống PAM / approval
    |
    | phê duyệt kế hoạch bất biến
    v
Kho bằng chứng hoặc bộ phát hành approval
    |
    | trạng thái đáng tin / bằng chứng được xác minh
    v
Admission validator
    |
    | cho phép hoặc từ chối yêu cầu Kubernetes
    v
Kết quả API và vòng đối soát sau khi lưu
```

Đây là mô hình thiết kế. Tổ chức có thể lưu approval ngoài cluster hoặc dùng một tài nguyên riêng với cơ chế bảo vệ thích hợp. Việc tạo CRD không tự tạo tính đáng tin cho nội dung của nó.

### Trách nhiệm của từng thành phần

| Thành phần | Trách nhiệm |
|---|---|
| Người yêu cầu | Nêu mục đích và phạm vi thay đổi |
| Người hoặc cơ chế phê duyệt | Kiểm tra thẩm quyền với đúng môi trường và nội dung |
| Bộ phát hành approval | Tạo bằng chứng gắn với kế hoạch được duyệt |
| Validator | Xác minh yêu cầu hiện tại nằm trong kế hoạch còn hợp lệ |
| Controller hoặc hệ thống thực thi | Thực hiện thay đổi theo danh tính được phép |
| Bộ đối soát | Nối quyết định admission với kết quả thực tế |
| Hệ thống bằng chứng | Bảo vệ lịch sử yêu cầu, phê duyệt và thực thi |

Cần kiểm soát riêng quyền yêu cầu, quyền phê duyệt và quyền sửa thành phần kiểm tra. Nếu người yêu cầu tự sửa bản ghi thành APPROVED hoặc đổi public key xác minh, quy trình có thể bị vô hiệu hóa.

## 4. Approval phải ràng buộc những gì?

Một bản ghi khái niệm:

```yaml
# Mô hình giảng dạy; không phải API approval tích hợp sẵn của Kubernetes.
approvalId: change-842
revision: 3
requester:
  identityRef: engineer-18
executor:
  identityRef: gitops-production
target:
  clusterRef: cluster-prod-A
  namespace: payments
  apiGroup: apps
  resource: deployments
  name: payment-api
operation: UPDATE
approvedChange:
  baselineRef: observed-object-revision
  desiredIntentDigest: approved-canonical-intent-digest
  policyProfile: deployment-image-change
validity:
  notBefore: approved-start
  expiresAt: approved-deadline
decision:
  state: APPROVED
  approverRefs:
    - service-owner
    - independent-approver
```

Từng trường phải có nguồn đáng tin và cách kiểm tra thực tế. Không coi ví dụ YAML là bảo đảm rằng Kubernetes tự kiểm tra các giá trị này.

### Ràng buộc cluster và namespace

Tên Deployment có thể giống nhau ở nhiều namespace và cluster. Approval cho payment-api trong cluster thử nghiệm không được tái sử dụng cho payment-api ở production.

Cluster reference phải đến từ cấu hình triển khai đã bảo vệ, không phải annotation tùy ý của client. Nếu tên namespace có thể bị tái sử dụng sau khi xóa, mô hình cần cân nhắc định danh phiên bản namespace hoặc cơ chế tránh áp dụng approval cũ cho một namespace mới cùng tên.

### Ràng buộc principal

Phải phân biệt người yêu cầu với danh tính gọi Kubernetes API. Trong GitOps, người yêu cầu là kỹ sư, còn executor có thể là ServiceAccount của controller.

Không so sánh người dùng cuối với executor một cách máy móc rồi miễn trừ mọi controller. Cần một đường liên kết được xác minh giữa thay đổi đã được duyệt và controller thực thi.

### Ràng buộc thao tác

Một approval cho UPDATE Deployment không mặc nhiên cho phép CREATE RoleBinding, sửa một subresource hoặc DELETE đối tượng.

Với thao tác cập nhật, hệ thống cần đánh giá cả trạng thái cũ và trạng thái đề nghị. “Đối tượng cuối cùng trông hợp lệ” chưa chắc đủ nếu thay đổi thực tế bao gồm việc mở quyền ngoài kế hoạch.

### Ràng buộc thời gian và trạng thái

Kiểm tra thời hạn tại lúc đánh giá yêu cầu, dùng nguồn thời gian được kiểm soát. Không chỉ kiểm tra khi tạo ticket hoặc lúc người dùng mở giao diện.

Nếu approval bị thu hồi trước deadline, validator cần có cơ chế nhận biết phù hợp. Một bản sao cache hoặc bằng chứng tự chứa vẫn có các giới hạn cập nhật cần được thiết kế rõ.

## 5. Phê duyệt nội dung nào: toàn bộ manifest hay ý định bảo mật?

Băm toàn bộ manifest nghe đơn giản nhưng dễ gặp khác biệt do trường do máy chủ quản lý, defaulting, mutation hoặc metadata không liên quan.

Ngược lại, chỉ băm tên image có thể bỏ sót thay đổi ServiceAccount, command, volume và cấu hình quyền.

Một cách thiết kế là định nghĩa **phần nội dung được kiểm soát** cho từng loại nhiệm vụ. Ví dụ, kế hoạch “đổi image” có thể yêu cầu:

- Đúng đối tượng và baseline đã xác định.
- Chỉ những đường trường được cho phép thay đổi.
- Image mới khớp định danh artifact bất biến được duyệt.
- Các trường nhạy cảm khác giữ nguyên hoặc theo quy tắc đã duyệt.
- Metadata dùng cho approval không được tự thay đổi thẩm quyền.

### Chuẩn hóa phải là một đặc tả, không phải mẹo xử lý chuỗi

Nếu dùng digest, cần quy định:

1. Những trường được đưa vào nội dung tính digest.
2. Cách biểu diễn dữ liệu và thứ tự các phần tử có ý nghĩa.
3. Trường nào được loại bỏ và tại sao.
4. Cách xử lý giá trị thiếu, giá trị mặc định và phiên bản API.
5. Cách xử lý các thay đổi do mutating component được phép tạo.
6. Khi nào thay đổi buộc phải xin approval mới.

Không nối vài giá trị bằng dấu phân cách rồi coi đó là chuẩn hóa an toàn. Các biểu diễn khác nhau có thể bị hiểu sai hoặc bỏ sót ý nghĩa bảo mật.

Đây là quyết định thiết kế cần được kiểm thử bằng các trường hợp thay đổi có chủ đích, không chỉ bằng một manifest “đúng”.

### Mutation không được làm approval mở rộng ngầm

Nếu một thành phần thêm sidecar, thay image hoặc đổi thuộc tính nhạy cảm, validator cuối cùng cần biết kết quả có còn nằm trong ý định được duyệt không.

Có thể phê duyệt trước một tập mutation xác định theo policy profile. Tuy nhiên, profile phải đủ cụ thể và được quản lý phiên bản. Câu “mọi thay đổi do hệ thống thêm đều được tin” sẽ mở một phạm vi quá rộng.

Không dựa vào giả định một webhook cụ thể luôn chạy ở vị trí mong muốn để làm điểm kiểm tra cuối cùng. Thiết kế nên đối chiếu trạng thái mà validator nhận được với toàn bộ quy tắc cần giữ.

## 6. Annotation là tham chiếu, không phải bằng chứng tự thân

Một đối tượng có thể mang:

```yaml
metadata:
  annotations:
    pam.example.org/approval-id: change-842
    pam.example.org/approval-revision: "3"
```

Ví dụ này chỉ mang định danh để tìm approval. Nếu người gọi có quyền sửa đối tượng, họ có thể sửa annotation. Validator phải xác minh bản ghi hoặc bằng chứng thực tế rồi đối chiếu phạm vi.

Không dùng các dạng sau làm căn cứ duy nhất:

```text
approved=true
approver=security-team
expiresAt=thời điểm do client chọn
```

### Nếu sử dụng bằng chứng có chữ ký

Một lựa chọn thiết kế là bộ phát hành tạo một bằng chứng có chữ ký chứa phạm vi và thời hạn. Validator cần xác minh nguồn phát hành, khóa tin cậy, audience, principal, nội dung được duyệt và các điều kiện liên quan.

Chữ ký hợp lệ chỉ cho biết bằng chứng đến từ bên nắm khóa tương ứng và nội dung không bị sửa theo cơ chế đó. Nó không tự chứng minh approval chưa bị thu hồi hoặc principal hiện tại còn đủ điều kiện.

Cần quy định rotation khóa xác minh, hành vi khi khóa bị lộ và giới hạn độ cũ của trạng thái. Không nhận một public key do chính đối tượng cần xét duyệt cung cấp làm gốc tin cậy.

Bằng chứng cũng không nên trở thành một bearer token rộng. Sao chép annotation sang đối tượng khác hoặc gửi bằng principal khác phải bị từ chối nếu không nằm trong phạm vi.

## 7. Chọn policy hay webhook

Kubernetes có ValidatingAdmissionPolicy để khai báo kiểm tra bằng CEL trong control plane; policy cần binding để có hiệu lực. Đây là lựa chọn cho quy tắc diễn đạt được bằng dữ liệu và cơ chế tham số được hỗ trợ. [Kubernetes: Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)

Một cách phân chia thiết kế:

| Nhu cầu | Hướng xem xét |
|---|---|
| Kiểm tra cấu trúc và giới hạn trên đối tượng | Policy khai báo hoặc cơ chế kiểm tra sẵn có |
| Bảo vệ những trường luôn bị cấm | Guardrail độc lập với approval |
| Đối chiếu một bản ghi approval riêng | Cơ chế tham số phù hợp hoặc validator được thiết kế để đọc trạng thái đáng tin |
| Xác minh một bằng chứng phức tạp | Webhook hoặc thành phần chuyên trách phù hợp |
| Chờ con người quyết định | Hệ thống approval ngoài lời gọi admission |
| Kết thúc workload sau thời hạn | Controller vòng đời hoặc cơ chế thực thi riêng |

Không giả định một biểu thức CEL có thể tự truy vấn bất kỳ API ticket hay kho approval nào. Cần kiểm tra đúng dữ liệu và thư viện được cung cấp bởi môi trường triển khai.

### Webhook là thành phần đặc quyền

Trong AdmissionReview, phản hồi phải gắn đúng request UID và quyết định allowed. Dry-run cần được xử lý phù hợp với khai báo sideEffects. failurePolicy điều khiển lỗi gọi webhook; một phản hồi từ chối hợp lệ vẫn từ chối yêu cầu. [Kubernetes: Dynamic Admission Control](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/)

Các chi tiết trên dẫn tới những yêu cầu thiết kế:

- Endpoint phải được bảo vệ để chỉ nhận ngữ cảnh từ đường gọi đáng tin.
- Không tin userInfo trong một JSON do bất kỳ client bên ngoài nào tự gửi.
- Kết nối tới endpoint, cấu hình tin cậy và quyền sửa webhook cần được quản lý.
- Validator chỉ có quyền đọc tối thiểu với dữ liệu cần kiểm tra.
- Validator không cần credential quản trị toàn cluster chỉ để xem một approval.
- Thông báo lỗi không được làm lộ secret hoặc chi tiết vượt quyền của người gọi.

Phần cấu hình TLS, xác thực kết nối và phạm vi rule phải được triển khai theo phiên bản, nền tảng và mô hình vận hành thực tế.

## 8. Luồng kiểm tra minh họa

Mã giả dưới đây mô tả một validator kiểm tra yêu cầu cập nhật. Các hàm là khái niệm thiết kế, không phải thư viện Kubernetes có sẵn:

```text
function evaluateAdmission(trustedConnection, review):
    require trustedApiServerRequest(trustedConnection)
    request = parseSupportedAdmissionReview(review)

    if not inProtectedScope(request):
        return allow(request.uid)

    if not requestShapeSupported(request):
        return deny(request.uid, "Unsupported protected operation")

    reference = approvalReferenceFrom(request)
    approval = readTrustedApprovalSnapshot(reference)

    if approval is missing:
        return deny(request.uid, "Approval required")

    if not approval.authenticAndApproved:
        return deny(request.uid, "Approval invalid")

    if not approval.validAt(trustedNow()):
        return deny(request.uid, "Approval expired or not active")

    if not approval.matchesCluster(configuredClusterIdentity):
        return deny(request.uid, "Cluster mismatch")

    if not approval.matchesExecutor(request.userInfo):
        return deny(request.uid, "Executor mismatch")

    target = trustedTargetFromRequest(request)
    if not approval.matchesTargetAndOperation(target, request.operation):
        return deny(request.uid, "Scope mismatch")

    oldIntent = projectProtectedFields(request.oldObject)
    newIntent = projectProtectedFields(request.object)

    if not approvedTransition(approval, oldIntent, newIntent):
        return deny(request.uid, "Change exceeds approval")

    if not mandatoryGuardrailsSatisfied(request):
        return deny(request.uid, "Mandatory policy violation")

    return allowWithEvidenceReference(request.uid, approval.reference)
```

Một triển khai thực tế cần có nhánh riêng cho CREATE, UPDATE, DELETE hoặc CONNECT nếu chúng thuộc phạm vi được bảo vệ. Không cố đọc cùng một cấu trúc object cho mọi thao tác.

Hàm inProtectedScope là một phần của kiểm soát. Nếu người dùng có thể sửa một label để thoát khỏi phạm vi, các phép kiểm tra sau đó không còn có tác dụng.

### Không cấp thêm quyền trong validator

Validator không nên tạo RoleBinding hoặc mở quyền khi nó nhìn thấy một yêu cầu chưa đủ quyền. Việc cấp quyền phải là luồng riêng với ownership và bằng chứng rõ ràng.

Tương tự, đừng tự đổi một yêu cầu chưa được duyệt thành được duyệt để “giúp pipeline chạy”. Khi không có căn cứ hợp lệ, trả về quyết định phù hợp và để hệ thống approval xử lý bên ngoài.

### Không đồng nhất quyết định allow với kết quả đã lưu

Một validator có thể cho phép nhưng yêu cầu vẫn thất bại ở bước khác. Vì vậy, bản ghi “validator đã cho phép” chỉ là một phần bằng chứng.

Cần đối soát kết quả API và trạng thái đối tượng sau đó. Với thao tác thay đổi, lưu định danh phiên bản hoặc đối tượng thực tế khi có, không chỉ lưu bản manifest mà client định gửi.

## 9. Retry, dry-run và approval dùng một lần

Tài liệu Kubernetes khuyến nghị tránh side effect và vòng phụ thuộc trong webhook, đồng thời giữ đường xử lý nhanh và khả dụng. Các thay đổi ngoài đối tượng đang xét cần được cân nhắc đặc biệt. [Kubernetes: Admission Webhook Good Practices](https://kubernetes.io/docs/concepts/cluster-administration/admission-webhooks-good-practices/)

Một hệ quả trong thiết kế approval là không nên cập nhật “đã tiêu thụ” một cách ngây thơ ngay mỗi khi webhook được gọi.

### Vì sao đánh dấu used ngay trong admission dễ sai?

Xét trình tự:

```text
1. Validator A thấy approval hợp lệ.
2. Validator A đánh dấu approval đã dùng.
3. Một kiểm tra khác từ chối yêu cầu.
4. Đối tượng không được lưu.
5. Client gửi lại và bị từ chối vì approval đã dùng.
```

Trường hợp ngược lại cũng có vấn đề: hai yêu cầu đồng thời cùng đọc một approval chưa dùng và đều nhận allow.

Admission request UID dùng để liên kết một lần gọi, không nên bị coi là định danh lâu dài của kế hoạch nghiệp vụ. Một lần gửi lại có thể tạo lần đánh giá mới.

### Chọn rõ ngữ nghĩa sử dụng approval

Có thể thiết kế theo một trong những mô hình sau:

| Mô hình | Ý nghĩa |
|---|---|
| Approval cho một trạng thái mong muốn | Các lần reconcile hoặc retry cùng trạng thái được kiểm tra theo cùng kế hoạch |
| Approval cho một phép chuyển trạng thái | Chỉ chấp nhận thay đổi từ baseline được xác định tới kết quả được duyệt |
| Approval cho một job thực thi | Controller có danh tính riêng quản lý job và liên kết kết quả |
| Approval có giới hạn số lần | Cần cơ chế đếm, đồng thời và đối soát đủ chặt ngoài một phép đọc đơn giản |

Không tuyên bố “exactly once” chỉ vì có một cột used trong kho approval.

Nếu yêu cầu là một lần thực thi duy nhất, cần thiết kế controller hoặc broker để điều phối, bảo vệ trạng thái, xử lý cạnh tranh và đối soát sau khi API trả kết quả. Một giao dịch local không tự bao trùm cả API server và kho approval bên ngoài.

Đối với UPDATE, có thể ràng buộc baseline và sử dụng cơ chế kiểm soát cập nhật phù hợp. Đối với CREATE, cần xử lý tên, lần tạo thành công, việc xóa rồi tạo lại và ownership. Không giả định một UID đối tượng đã có sẵn trước khi đối tượng được tạo.

### Dry-run không được làm cạn approval

Trong thiết kế đề xuất, dry-run chỉ đánh giá khả năng chấp nhận. Nó không tiêu thụ approval, không cấp quyền mới và không đặt lịch thay đổi hạ tầng.

Kết quả dry-run cũng không phải lời hứa một lần gửi sau chắc chắn thành công. Approval có thể hết hạn, baseline đổi hoặc policy thay đổi trước lần gửi thật.

Cần kiểm thử dry-run như một đường riêng. Không dùng dry-run như cách bỏ qua kiểm tra approval, bởi như vậy kết quả thử sẽ không phản ánh quyết định thực tế.

## 10. Controller và GitOps: ai là executor?

Một người cập nhật Deployment, sau đó controller tạo ReplicaSet và Pod. Những yêu cầu này không nhất thiết có cùng principal với người ban đầu.

Nếu policy yêu cầu mọi Pod phải mang approval của người tạo Deployment nhưng chỉ so sánh userInfo trực tiếp, rollout có thể bị chặn. Nếu miễn trừ toàn bộ controller, thay đổi có thể đi qua mà không được kiểm tra đầy đủ.

### Thiết kế theo chuỗi nguồn gốc đáng tin

Một cách thiết kế là:

1. Kiểm tra và gắn kế hoạch được duyệt với thay đổi workload cấp cha.
2. Bảo vệ template và các trường quyết định quyền.
3. Liên kết đối tượng con với đúng phiên bản hoặc nguồn gốc của kế hoạch.
4. Xác minh danh tính controller và quan hệ sở hữu thực tế.
5. Chỉ cho phép những thay đổi sinh ra nằm trong quy tắc đã định.

Không tin ownerReference hoặc annotation chỉ vì chúng có định dạng giống tài nguyên hệ thống. Một người dùng có thể tạo metadata trông hợp lý; bộ kiểm tra cần xác minh bằng dữ liệu có thẩm quyền và mô hình quyền thực tế.

Nếu dùng cache để kiểm tra quan hệ cha-con, phải xử lý tình huống cache chưa thấy đối tượng mới hoặc vẫn giữ bản cũ. Một lỗi tra cứu không nên tự trở thành miễn trừ cho mọi controller.

### Approval cho rollout khác quyền tồn tại của workload

Có hai yêu cầu khác nhau:

- Cho phép một cấu hình đã được duyệt triển khai và duy trì theo vòng đời ứng dụng.
- Cho phép một workload tạm thời chỉ tồn tại tới một deadline.

Đối với mô hình thứ nhất, cần xác định việc controller tạo lại Pod sau thời điểm phê duyệt còn được phép theo kế hoạch hay không. Nếu luôn yêu cầu approval ban đầu chưa hết hạn, việc reschedule sau sự cố có thể bị chặn.

Đối với mô hình thứ hai, cần một cơ chế kết thúc workload riêng. Admission không liên tục đánh giá lại một Pod đang chạy chỉ vì bản ghi approval đã hết hạn.

Vì vậy, thời hạn được gửi thay đổi, thời hạn kế hoạch rollout và thời hạn tồn tại của workload phải được diễn đạt rõ, không gộp vào một trường expiresAt mơ hồ.

## 11. Phạm vi rule và các đường bỏ sót

Trước khi chọn rule, cần lập danh sách loại thay đổi nhạy cảm:

| Nhóm | Nội dung cần xem xét trong thiết kế |
|---|---|
| Workload cấp cha | Image, template, command, ServiceAccount và nguồn dữ liệu |
| Pod trực tiếp | Những đường tạo workload ngoài controller dự kiến |
| Debug và kết nối | Subresource, danh tính gọi, mục đích và thời hạn thao tác |
| RBAC | Chủ thể nhận quyền, role được tham chiếu, phạm vi |
| Chính cấu hình admission | Ai có thể sửa, bỏ rule hoặc thay endpoint |
| Namespace và tham số policy | Ai sửa nhãn chọn phạm vi, ngoại lệ hoặc dữ liệu kiểm tra |
| Tài nguyên do extension quản lý | Đường từ một custom resource tới workload có quyền |

Các nhóm trên là danh mục phân tích, không phải cấu hình match hoàn chỉnh. Phải ánh xạ sang đúng group, resource, subresource và operation mà API server gửi.

Một policy chỉ kiểm tra Pod CREATE không nên được tuyên bố là đã kiểm soát mọi thay đổi RBAC, workload và debug.

### Kiểm soát privilege escalation ngoài admission

Kubernetes lưu ý rằng quyền tạo workload và sử dụng các ServiceAccount có thể mở những đường quyền gián tiếp; quyền đọc Secret cũng cần được đánh giá đầy đủ. [Kubernetes: RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)

Trong mô hình bài học, điều đó dẫn tới các nguyên tắc:

- Không cấp quyền sửa mọi RoleBinding chỉ để giải quyết một nhu cầu nhỏ.
- Không cho principal bình thường tự sửa policy profile.
- Giới hạn quyền sử dụng danh tính workload mạnh.
- Rà soát đường sửa image, pipeline và cấu hình controller.
- Không dùng một webhook làm lý do bỏ các ràng buộc RBAC nền tảng.

### Approval không tự tạo ngoại lệ cho Pod Security

Pod Security Admission có các mức và chế độ kiểm soát riêng; một Pod vi phạm ở chế độ enforce có thể bị từ chối. [Kubernetes: Pod Security Admission](https://kubernetes.io/docs/concepts/security/pod-security-admission/)

Approval từ một webhook của tổ chức không tự cho phép bỏ qua các kiểm soát độc lập. Nếu nhiệm vụ thật sự cần ngoại lệ, phải thiết kế và quản lý ngoại lệ tại đúng cơ chế liên quan, với chủ sở hữu và phạm vi rõ ràng.

Không hạ chính sách toàn namespace hoặc miễn trừ rộng mọi controller chỉ để một yêu cầu đã duyệt chạy được.

## 12. Khả dụng, failure policy và trạng thái approval

Một admission validator trên đường thay đổi production là thành phần quan trọng về khả dụng. Thiết kế phải tránh việc lỗi ở hệ thống ticket làm toàn cluster không thể tự phục hồi.

### Khi không đọc được trạng thái approval

Cần phân biệt:

- Không có approval.
- Approval tồn tại nhưng không hợp lệ.
- Không xác minh được do phụ thuộc lỗi.
- Snapshot quá cũ để đưa ra quyết định theo chính sách.

Không biến mọi lỗi thành approval hợp lệ. Đồng thời, phải xác định phạm vi nào bắt buộc chặn và phạm vi nào không thuộc cơ chế này.

Với các thay đổi nhạy cảm được bảo vệ, một thiết kế có thể chọn từ chối khi không đủ bằng chứng. Khi đó cần triển khai khả dụng và đường phục hồi tương xứng, thay vì chỉ đặt fail-closed rồi coi nhiệm vụ hoàn tất.

### Ignore không có nghĩa phủ quyết một quyết định deny

Cần phân biệt lỗi gọi validator với quyết định từ chối hợp lệ. failurePolicy không phải một công tắc cho người gọi vượt qua mọi deny.

Trong thiết kế đề xuất, các thông báo lỗi nên có mã phân loại ổn định, ví dụ:

```text
APPROVAL_REQUIRED
APPROVAL_SCOPE_MISMATCH
APPROVAL_EXPIRED
APPROVAL_STATE_UNAVAILABLE
APPROVAL_INTENT_MISMATCH
MANDATORY_GUARDRAIL_FAILED
```

Không trả toàn bộ nội dung approval hoặc danh sách tài nguyên nhạy cảm cho một người không có quyền đọc chúng.

### Tránh tự khóa đường phục hồi

Cần phân tích quan hệ phụ thuộc:

- Webhook có cần chính những Pod mà nó đang chặn để khởi động không?
- Nó có phụ thuộc vào một dịch vụ mạng hoặc secret đang cần được khôi phục không?
- Hệ thống approval có phụ thuộc vào workload mà nó yêu cầu phê duyệt không?
- Khi mất một vùng hoặc một node, thành phần còn khả năng đưa ra quyết định không?

Ngoại lệ phục hồi phải hẹp và được bảo vệ. Một label do người dùng tự đặt để “bỏ qua webhook” không phải đường khẩn cấp phù hợp.

### Cache và thu hồi approval

Cache giúp giảm phụ thuộc đồng bộ nhưng tạo khoảng cách giữa trạng thái nguồn và quyết định tại validator.

Cần quy định độ cũ tối đa, cách nhận thay đổi, hành vi khi mất đồng bộ và thời gian thu hồi dự kiến. Nếu dùng bằng chứng tự chứa, cần xác định việc thu hồi sớm được thực thi bằng cách nào.

Không hứa thu hồi tức thời nếu thiết kế chỉ dựa vào một token còn hạn và không có đường cập nhật trạng thái.

## 13. Bằng chứng: từ phê duyệt tới đối tượng thực tế

Một chuỗi đối soát cần phân biệt:

```text
Kế hoạch được duyệt
    --> lần đánh giá admission
    --> kết quả API
    --> đối tượng và phiên bản thực tế
    --> hành động controller
    --> trạng thái workload
```

Bản ghi allowed=true không chứng minh Deployment đã cập nhật thành công. Deployment được lưu cũng không chứng minh rollout đã hoàn tất.

| Loại bằng chứng | Nội dung cần nối được |
|---|---|
| Approval | ID, revision, người yêu cầu, người duyệt, phạm vi và thời hạn |
| Admission | Request reference, principal thực thi, target, policy revision, verdict |
| API | Kết quả, định danh đối tượng và phiên bản khi áp dụng |
| Controller | Quan hệ với thay đổi được duyệt và đối tượng con |
| Vòng đời | Kết quả rollout, ngoại lệ và thao tác kết thúc nếu có |

Không mặc định AdmissionReview UID, approval ID và audit ID là cùng một giá trị. Hệ thống phải có chiến lược liên kết rõ, dựa vào trường thực sự được cung cấp và dữ liệu do thành phần tin cậy phát hành.

Kubernetes audit hỗ trợ nhiều mức ghi nhận; mức Metadata không chứa request hoặc response body, còn mức chi tiết hơn có thể chứa nội dung. Cần chọn policy theo dữ liệu và nhu cầu đối soát. [Kubernetes: Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/)

Không ghi token, credential, nội dung Secret hoặc toàn bộ payload nhạy cảm vào log chỉ để dễ tìm lỗi. Các thông tin về principal, tài nguyên và approval cũng cần quyền đọc, thời hạn lưu và bảo vệ phù hợp.

### Những dấu hiệu nên được điều tra

- Một approval được dùng cho nhiều đích ngoài kế hoạch.
- Số lượng từ chối vì intent mismatch tăng bất thường.
- Một principal sửa nhãn phạm vi trước khi gửi yêu cầu nhạy cảm.
- Webhook hoặc policy binding bị thay đổi gần thời điểm thao tác.
- Có đối tượng nhạy cảm được lưu nhưng không nối được về approval bắt buộc.
- Thời gian validator không xác minh được trạng thái vượt giới hạn vận hành.
- Một workload tạm không được kết thúc theo kế hoạch.

Mỗi tín hiệu cần một người chịu trách nhiệm và cách điều tra. Chỉ tăng số lượng log không tự tạo ra khả năng kiểm soát.

## 14. Tình huống: đổi image production qua GitOps

### Bối cảnh

Nhóm vận hành muốn đổi image của payment-api trong namespace payments. Một controller GitOps có quyền thực hiện thay đổi. Yêu cầu chỉ cho phép đổi tới một artifact đã được xác định, giữ nguyên danh tính workload và cấu hình nhạy cảm.

### Luồng được duyệt

1. Hệ thống tạo kế hoạch gắn với cluster, đối tượng và baseline.
2. Người có thẩm quyền duyệt nội dung thay đổi.
3. Bộ phát hành tạo approval revision bất biến.
4. Pipeline đưa đúng tham chiếu approval vào manifest.
5. Controller gửi yêu cầu bằng danh tính đã được đăng ký.
6. Validator đối chiếu chủ thể, target, thời hạn và phép chuyển trạng thái.
7. Bộ đối soát nối kết quả API với approval và theo dõi rollout.

### Ba tình huống cần chặn

**Đổi image sau phê duyệt:** nội dung không còn khớp, phải xin approval mới.

**Đổi ServiceAccount cùng lúc:** thay đổi vượt profile “image-only”, phải bị từ chối dù image đúng.

**Sao chép approval sang cluster khác:** cluster reference hoặc audience không khớp, phải bị từ chối.

### Khi rollout chưa hoàn tất

Không ghi “thành công” chỉ từ verdict của validator. Cần phân biệt thay đổi được chấp nhận, Deployment đã được lưu và rollout đạt điều kiện vận hành.

Nếu cần rollback, nó cũng là một thay đổi. Có thể được bao phủ bởi kế hoạch rollback đã duyệt hoặc cần một approval mới theo chính sách. Không để từ “rollback” trở thành ngoại lệ tự do cho mọi manifest cũ.

## 15. Bài thực hành thiết kế trong cluster thử nghiệm

Dùng cluster học tập, namespace riêng và manifest không chứa dữ liệu thật. Không triển khai webhook mới trên production để làm bài.

### Bước 1: Chọn một loại thay đổi

Chọn UPDATE Deployment với profile “image-only”. Xác định:

- Cluster và namespace.
- Định danh Deployment.
- Principal được thực thi.
- Baseline và image đích.
- Trường được thay đổi.
- Thời hạn và người phê duyệt.
- Các policy độc lập vẫn phải được đáp ứng.

### Bước 2: Tạo mô hình approval

Có thể mô phỏng bằng một kho dữ liệu thử hoặc một tài nguyên tự xây dựng. Bảo đảm principal gửi Deployment không tự sửa được phần quyết định approval.

Nếu sử dụng CRD, hãy ghi rõ schema, ai được tạo yêu cầu, ai được thay đổi quyết định và cách bảo vệ các trường. Không coi tên kind Approval là một cơ chế bảo mật.

### Bước 3: Xác định trạng thái thực thi

Thiết kế ít nhất các kết quả:

```text
PENDING_APPROVAL
APPROVED
ADMISSION_ALLOWED
API_CHANGE_OBSERVED
ROLLOUT_OBSERVED
REJECTED
EXPIRED
REVOKED
VERIFICATION_PENDING
```

Đây là trạng thái ứng dụng minh họa. Chọn tên và chuyển trạng thái theo hệ thống thực tế, nhưng không gộp quyết định admission với thành công cuối cùng.

### Bước 4: Kiểm tra các tình huống

| Tình huống | Kết quả mong đợi |
|---|---|
| Đúng kế hoạch, executor, target và còn hạn | Được validator chấp nhận nếu các kiểm soát khác cũng đạt |
| Không có approval | Từ chối trong phạm vi bắt buộc |
| Tự thêm approved=true | Không tạo quyền phê duyệt |
| Dùng approval của người khác với executor không phù hợp | Từ chối |
| Đổi namespace hoặc cluster | Từ chối |
| Đổi image sau khi duyệt | Từ chối |
| Image đúng nhưng thay ServiceAccount | Từ chối theo profile |
| Baseline đã thay đổi | Đánh giá lại hoặc yêu cầu approval mới |
| Gửi qua một operation hoặc subresource ngoài kế hoạch | Từ chối nếu thuộc phạm vi bảo vệ |
| Dry-run hợp lệ | Đánh giá đúng nhưng không tiêu thụ approval |
| Client retry cùng ý định | Hành vi nhất quán với ngữ nghĩa đã chọn |
| Hai lần gửi đồng thời | Không tạo kết luận dùng một lần sai hoặc vượt phạm vi |
| Một kiểm tra khác từ chối sau validator | Không đánh dấu đối tượng đã được lưu |
| Controller tạo đối tượng con | Xác minh được chuỗi được phép, không miễn trừ rộng |
| Approval hết hạn trước một lần gửi mới | Từ chối theo chính sách |
| Approval hết hạn khi Pod đã chạy | Xử lý theo mô hình vòng đời đã định, không giả định admission tự dừng Pod |
| Kho approval không sẵn sàng | Hành vi rõ ràng, có cảnh báo và đường phục hồi |
| Người dùng sửa nhãn để thoát phạm vi | Bị kiểm soát tại đường sửa nhãn hoặc không tạo được bypass |
| Approval hợp lệ nhưng vi phạm guardrail khác | Vẫn bị chặn bởi guardrail |
| Kiểm tra bằng chứng | Nối được approval, verdict, kết quả API; không lộ secret |

### Bước 5: Hoàn thiện hồ sơ

Hồ sơ thực hành nên có một sơ đồ luồng, đặc tả approval, quy tắc nội dung được duyệt, mô hình retry và kết quả các phép kiểm tra phù hợp.

Nếu chưa triển khai một validator đầy đủ, ghi rõ phần nào chỉ là mô hình. Không biến một bản YAML minh họa thành bằng chứng rằng cluster đã thực thi các điều kiện.

## 16. Những lỗi cần tránh

**Dùng annotation làm approval:** annotation do client ghi chỉ nên là tham chiếu; phải xác minh nguồn thẩm quyền.

**Giữ request chờ người duyệt:** tách bước approval ngoài lời gọi admission và gửi lại khi sẵn sàng.

**Đánh dấu approval đã dùng trước khi đối tượng được lưu:** cần mô hình thực thi, đồng thời và đối soát riêng.

**Miễn trừ mọi controller:** phải bảo vệ đường từ kế hoạch tới workload con, không chỉ kiểm tra tên principal.

**Chỉ băm image rồi bỏ các trường quyền:** phê duyệt cần bao phủ ý nghĩa bảo mật của thay đổi, không chỉ một giá trị dễ so sánh.

**Đặt thời hạn rồi cho rằng Pod tự dừng:** kết thúc tài nguyên hoặc phiên cần cơ chế vòng đời phù hợp.

**Cho người vận hành sửa webhook, nhãn ngoại lệ và khóa xác minh:** cần tách quyền sử dụng khỏi quyền sửa cơ chế kiểm soát.

**Coi approval là quyền vượt qua mọi policy:** các guardrail độc lập vẫn có thể từ chối yêu cầu.

**Tuyên bố thành công từ allowed=true:** cần kiểm tra kết quả API và trạng thái nghiệp vụ thực tế.

Admission approval có ý nghĩa khi nó liên kết một quyết định có thẩm quyền với đúng thay đổi mà API đang xét. PAM quản lý ai được yêu cầu, ai được duyệt và trong phạm vi nào; admission là điểm thực thi một phần các ràng buộc đó. Khả năng đối soát sau khi lưu và quản lý vòng đời giúp hoàn thiện phần mà một quyết định đồng bộ không thể tự bảo đảm.
