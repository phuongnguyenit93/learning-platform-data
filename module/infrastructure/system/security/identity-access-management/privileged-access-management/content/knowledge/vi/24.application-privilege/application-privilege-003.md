# Privileged function

## Mục tiêu bài học

Trong chương Application privilege của module Privileged Access Management (PAM), **privileged function** là chức năng ứng dụng có thể tạo tác động nhạy cảm hoặc sử dụng quyền vượt quá hoạt động thông thường. Ví dụ gồm cấp quyền quản trị, thay đổi quan hệ tin cậy, xuất dữ liệu trên diện rộng, vô hiệu hóa một cơ chế bảo vệ hoặc điều khiển credential của tài khoản dịch vụ.

Kiểm soát tài khoản đăng nhập chưa đủ để kiểm soát những chức năng này. Người dùng có thể đăng nhập bằng tài khoản hợp lệ nhưng gọi một thao tác không thuộc thẩm quyền. Ngược lại, một API chạy dưới service account có quyền kỹ thuật rộng có thể bị lợi dụng để thực hiện yêu cầu mà người gọi không được phép thực hiện.

Sau bài học, bạn có thể:

- Nhận diện chức năng đặc quyền theo tác động thực tế thay vì tên màn hình.
- Mô hình hóa người gọi, hành động, tài nguyên, phạm vi và điều kiện.
- Thiết kế kiểm tra quyền ở phía máy chủ và tại thời điểm thực thi.
- Gắn JIT, giới hạn thao tác, phê duyệt và bằng chứng với một yêu cầu cụ thể.
- Xử lý các đường gọi API, tác vụ nền, chạy lại và lỗi thực thi.
- Xây dựng các tình huống kiểm thử cho phép, từ chối và vượt phạm vi.

Bài học dùng ví dụ và mã giả để diễn giải thiết kế. Các tên hàm, thuộc tính và policy không phải API hay cấu hình của một sản phẩm cụ thể.

## 1. Privileged function là gì?

Một chức năng được xem là đặc quyền khi việc sử dụng sai có thể làm thay đổi đáng kể quyền truy cập, trạng thái bảo vệ, dữ liệu nhạy cảm hoặc khả năng vận hành của hệ thống.

Ví dụ:

| Chức năng | Tác động cần kiểm soát |
|---|---|
| Cấp role quản trị | Tạo khả năng thực hiện các hành động đặc quyền tiếp theo |
| Thay đổi policy truy cập | Mở rộng hoặc thu hẹp quyền trên tài nguyên |
| Xuất dữ liệu nhiều người dùng hoặc nhiều tenant | Tăng phạm vi dữ liệu được tập hợp và đưa ra ngoài |
| Thay đổi đích cấp phát credential | Chuyển quyền nhận hoặc sử dụng bí mật sang chủ thể khác |
| Vô hiệu hóa audit hoặc cảnh báo | Giảm khả năng phát hiện và điều tra |
| Chạy tác vụ bảo trì trên production | Thay đổi trạng thái hệ thống với phạm vi ảnh hưởng lớn |
| Dùng chức năng hỗ trợ dưới danh tính người khác | Tạo hành động có thể bị hiểu nhầm về nguồn gốc |
| Thay đổi cấu hình định danh hoặc quan hệ tin cậy | Thay đổi ai có thể xác thực hoặc nhận quyền |

Không phải mọi chức năng đặc quyền đều mang tên “admin”. Một nút “Export all”, một API hỗ trợ hoặc một job sửa dữ liệu cũng có thể đặc quyền dù nằm trong ứng dụng thông thường.

### 1.1. Đặc quyền được xác định theo tác động và phạm vi

Cùng một loại thao tác có thể có mức nhạy cảm khác nhau:

- Xem báo cáo của chính người dùng khác với xem báo cáo toàn tổ chức.
- Cập nhật cấu hình cá nhân khác với cập nhật cấu hình xác thực toàn hệ thống.
- Chạy lại một job thử nghiệm khác với chạy lại tác vụ thay đổi production.
- Khóa một tài khoản theo thẩm quyền khác với vô hiệu hóa toàn bộ cơ chế đăng nhập.

Vì vậy, không chỉ hỏi “đây có phải thao tác ghi không?”. Cần hỏi nó tác động tới ai, tài nguyên nào, quy mô bao nhiêu và có mở thêm khả năng truy cập nào không.

### 1.2. Chức năng đặc quyền không đồng nghĩa với endpoint nội bộ

Một endpoint ở mạng nội bộ vẫn cần kiểm tra quyền. Một chức năng được ẩn khỏi giao diện cũng chưa được bảo vệ nếu người gọi có thể gửi yêu cầu trực tiếp.

Tương tự, việc yêu cầu người dùng đi qua một cổng PAM hoặc được cấp phiên quản trị không thay thế kiểm tra quyền của chính ứng dụng. Ứng dụng phải xác định phiên đó được phép thực hiện chức năng nào trên tài nguyên nào.

## 2. Phân biệt tài khoản đặc quyền, quyền và chức năng đặc quyền

Ba khái niệm này liên quan nhưng không đồng nhất.

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Tài khoản hoặc định danh | Ai đang hành động? | Người vận hành, service account |
| Permission | Được phép thực hiện hành động nào? | Có quyền đề nghị thay đổi role trong một phạm vi |
| Privileged function | Ứng dụng thực hiện nghiệp vụ nhạy cảm nào? | Gán một role cho một tài khoản đích |

Một người có role vận hành chưa chắc được phép thực hiện mọi chức năng trên mọi tenant. Một service account của ứng dụng có quyền ghi cơ sở dữ liệu cũng không có nghĩa mọi người dùng gọi ứng dụng được phép yêu cầu nó ghi tùy ý.

### 2.1. Quyền kỹ thuật của backend không phải thẩm quyền của người gọi

Giả sử backend có quyền cập nhật bảng gán role. API nhận một yêu cầu gán role từ người dùng.

Nếu backend chỉ kiểm tra mình có thể ghi cơ sở dữ liệu rồi thực hiện, nó đã bỏ qua câu hỏi quan trọng: người gọi có được cấp role đó cho đối tượng đó không?

Backend đang thực hiện hành động thay mặt một chủ thể khác. Nó phải kiểm tra thẩm quyền của người gọi trước khi sử dụng quyền kỹ thuật của mình.

### 2.2. Tách danh tính ban đầu và danh tính thực thi

Một luồng đặc quyền có thể có:

- Người yêu cầu ban đầu.
- Người phê duyệt.
- Workload hoặc dịch vụ thực thi.
- Tài khoản kỹ thuật tại hệ thống đích.

Bằng chứng cần giữ được quan hệ giữa các danh tính này. Nếu mọi sự kiện chỉ ghi “service-admin đã cập nhật”, việc điều tra sẽ không biết ai yêu cầu, ai duyệt và người đó được phép tới đâu.

Không nên giả mạo log để biến hành động của backend thành hành động trực tiếp của người dùng. Hãy ghi rõ hành động được thực hiện bởi dịch vụ, thay mặt người yêu cầu nào, qua quyết định và workflow nào.

## 3. Lập danh mục chức năng đặc quyền

Muốn kiểm soát phải biết các chức năng tồn tại ở đâu. Danh mục cần bao phủ cả giao diện lẫn đường gọi không có giao diện:

- Trang quản trị và chức năng hỗ trợ.
- API công khai, API nội bộ và API cho tích hợp.
- Tác vụ theo lịch và hàng đợi.
- Công cụ dòng lệnh hoặc script vận hành.
- Luồng import, chạy lại, sửa lỗi và phục hồi.
- Chức năng quản lý chính các quyền của ứng dụng.

### 3.1. Thông tin cần ghi nhận

Với từng chức năng, cần mô tả:

1. Tên hành động và mục đích.
2. Chủ thể nào có thể yêu cầu.
3. Tài nguyên và phạm vi chịu tác động.
4. Danh tính thực thi tại hệ thống đích.
5. Điều kiện cấp quyền và các ràng buộc nghiệp vụ.
6. Yêu cầu xác thực tăng cường, phê duyệt hoặc JIT khi áp dụng.
7. Bằng chứng trước, trong và sau khi thực hiện.
8. Hành vi khi bị từ chối, lỗi hoặc thực thi một phần.
9. Owner chịu trách nhiệm về chức năng.
10. Các đường gọi tương đương cần cùng được kiểm soát.

### 3.2. Ví dụ mô tả một chức năng

~~~yaml
privileged_function:
  id: role-assignment.change
  purpose: Thay doi role cua mot tai khoan trong pham vi duoc duyet
  application_owner: identity-operations
  request_channels:
    - admin-ui
    - administrative-api
  resources:
    - target-account
    - target-role
    - tenant
  controls:
    server_side_authorization: required
    trusted_resource_lookup: required
    prevent_out_of_scope_assignment: required
    approval: Theo policy cua hanh dong va muc rui ro
    durable_audit: required
  execution:
    service_identity: role-management-service
    outcome_tracking: required
~~~

Đây là tài liệu mô tả ý định kiểm soát, không phải một policy đã được máy chủ thực thi. Mỗi yêu cầu trong đó phải được ánh xạ tới cơ chế thực tế và có cách kiểm chứng.

## 4. Mô hình một quyết định cấp quyền

Một quyết định nên xem ít nhất các thành phần sau:

> Chủ thể + hành động + tài nguyên + phạm vi + điều kiện hiện tại.

Ví dụ:

- Chủ thể: người vận hành đã được xác thực.
- Hành động: gán role được phê duyệt.
- Tài nguyên: tài khoản đích và role đích.
- Phạm vi: tenant mà người vận hành được giao quản lý.
- Điều kiện: quyền còn hiệu lực, phê duyệt khớp yêu cầu và không vi phạm quy tắc phân tách nhiệm vụ.

### 4.1. Cấp quyền ở mức chức năng và mức đối tượng

Hai loại kiểm tra thường cần cùng tồn tại:

**Mức chức năng:** người gọi có được sử dụng thao tác gán role hay không?

**Mức đối tượng:** người gọi có được gán role cụ thể này cho tài khoản cụ thể này trong tenant cụ thể này hay không?

Chỉ kiểm tra mức chức năng dễ tạo lỗi vượt phạm vi. Ví dụ, người vận hành được gán role trong tenant A nhưng thay ID tài khoản đích để tác động tenant B.

Máy chủ phải lấy thông tin tài nguyên từ nguồn đáng tin cậy và kiểm tra quan hệ phạm vi. Không tin rằng một trường tenant trong request tự chứng minh đối tượng thuộc tenant đó.

### 4.2. RBAC, ABAC và quy tắc nghiệp vụ

Role có thể xác định nhóm chức năng được phép sử dụng. Thuộc tính có thể giới hạn theo môi trường, tenant, trạng thái tài nguyên hoặc phiên làm việc. Quy tắc nghiệp vụ kiểm soát những tổ hợp không được chấp nhận.

Ví dụ:

- Role cho phép tiếp cận chức năng quản lý quyền.
- Thuộc tính giới hạn người vận hành trong tenant được giao.
- Quy tắc chặn tự cấp role cao hơn phạm vi được phép.
- Một thay đổi nhạy cảm cần người duyệt độc lập.
- Quyền JIT phải còn hiệu lực tại thời điểm cần kiểm tra.

Không có một mô hình duy nhất phù hợp mọi ứng dụng. Điều cần bảo đảm là các điều kiện phải rõ, được thực thi phía máy chủ và không thể bị người gọi tự sửa để mở quyền.

### 4.3. Xác thực mạnh không thay thế permission

Xác thực tăng cường có thể làm giảm nguy cơ một phiên bị sử dụng trái phép. Nó không tự cho phép người dùng thực hiện một chức năng ngoài thẩm quyền.

Một người đã vượt qua bước xác thực bổ sung vẫn có thể bị từ chối vì tài nguyên nằm ngoài phạm vi, role không được phép cấp hoặc phê duyệt không khớp.

## 5. Đặt điểm kiểm soát tại phía máy chủ

Giao diện có thể ẩn hoặc khóa nút để hướng dẫn trải nghiệm. Quyết định bảo mật phải nằm ở thành phần có quyền kiểm soát hành động thực tế.

~~~mermaid
flowchart TD
    A[Yêu cầu từ UI, API hoặc tác vụ] --> B[Xác thực và xác định chủ thể]
    B --> C[Đọc tài nguyên từ nguồn tin cậy]
    C --> D[Kiểm tra quyền và ràng buộc]
    D --> E{Đủ điều kiện?}
    E -->|Không| F[Từ chối và ghi sự kiện phù hợp]
    E -->|Có| G[Kiểm tra phê duyệt và trạng thái hiện tại]
    G --> H[Thực hiện qua dịch vụ đặc quyền]
    H --> I[Ghi nhận kết quả và bằng chứng]
~~~

Sơ đồ thể hiện các trách nhiệm logic. Trong triển khai thực tế, một số bước cần nằm trong transaction hoặc được điều phối qua workflow để tránh sai lệch giữa kiểm tra và thực thi.

### 5.1. Mọi đường vào phải đi qua kiểm soát tương đương

Nếu UI kiểm tra quyền nhưng API không kiểm tra, người dùng có thể bỏ qua giao diện. Nếu API chính kiểm tra nhưng endpoint chạy lại tác vụ không kiểm tra, rủi ro vẫn tồn tại.

Có thể gom logic vào một lớp dịch vụ hoặc điểm thực thi policy chung. Tuy nhiên, “dùng chung middleware” chưa chứng minh mọi hành động đã được bảo vệ: vẫn cần kiểm tra các đường gọi trực tiếp, phiên bản API cũ và tác vụ nền.

### 5.2. Mặc định từ chối khi không đủ căn cứ

Chức năng đặc quyền không nên được cho phép chỉ vì dịch vụ policy lỗi, thiếu thuộc tính hoặc không đọc được trạng thái phê duyệt.

Hành vi cần được thiết kế rõ. Nếu không thể xác nhận điều kiện bắt buộc, yêu cầu phải dừng thay vì tự suy ra quyền từ một giá trị mặc định rộng.

Với nhu cầu vận hành khẩn cấp, dùng quy trình ngoại lệ hoặc break-glass đã được ủy quyền trước, có phạm vi, thời hạn và bằng chứng. Không biến sự cố của hệ thống kiểm soát thành quyền quản trị tự động.

### 5.3. Dữ liệu do người gọi gửi không phải bằng chứng thẩm quyền

Các trường như role hiện tại, tenant, trạng thái phê duyệt hoặc cờ “isAdmin” không thể được tin chỉ vì xuất hiện trong request.

Máy chủ phải xác định nguồn tin cậy cho từng thuộc tính. Định danh phiên có thể đến từ cơ chế xác thực được kiểm chứng; trạng thái tài nguyên từ kho dữ liệu có thẩm quyền; phê duyệt từ workflow kiểm soát.

Một lý do do người dùng nhập có ích để giải thích yêu cầu nhưng không tự tạo quyền thực hiện.

## 6. Phê duyệt phải gắn với đúng hành động

Phê duyệt có ích khi nó ràng buộc một quyết định cụ thể. Một ticket có chữ “approved” nhưng không xác định đối tượng và thay đổi thì quá yếu.

Thông tin cần liên kết có thể gồm:

- Người yêu cầu và người phê duyệt.
- Loại hành động.
- Tài nguyên và tenant.
- Nội dung thay đổi.
- Phiên bản hoặc trạng thái liên quan.
- Thời hạn hiệu lực.
- Quy tắc số lần sử dụng.
- Điều kiện thu hồi hoặc hủy.

### 6.1. Không cho phép thay payload sau khi duyệt

Giả sử yêu cầu được duyệt để cấp role vận hành hạn chế cho tài khoản A. Nếu người gọi có thể đổi payload thành role quản trị hoặc tài khoản B nhưng giữ nguyên approval ID, phê duyệt đã mất ý nghĩa.

Hệ thống phải kiểm tra nội dung thực thi khớp với nội dung được chấp thuận. Có thể dùng bản ghi yêu cầu bất biến và tham chiếu phiên bản, hoặc cơ chế ràng buộc tương đương được thiết kế phù hợp.

Nếu dùng dấu vân tay nội dung, cần xử lý biểu diễn dữ liệu và các trường được ràng buộc nhất quán. Việc chỉ tạo một chuỗi hash không tự giải quyết lỗi bỏ sót trường hoặc diễn giải payload khác nhau.

### 6.2. Phân tách nhiệm vụ cần kiểm tra ở máy chủ

Nếu policy yêu cầu người duyệt độc lập với người yêu cầu, hệ thống phải kiểm tra điều đó từ định danh đáng tin cậy.

Không chỉ dựa vào giao diện ẩn nút “Approve” của chính người yêu cầu. API phê duyệt, tác vụ tự động và đường chạy lại cũng phải giữ ràng buộc tương ứng.

Việc một người có nhiều tài khoản cũng có thể ảnh hưởng ý nghĩa phân tách nhiệm vụ. Mô hình kiểm soát cần xác định mức danh tính được dùng, thay vì chỉ so hai chuỗi tên tài khoản khi điều đó không đáp ứng yêu cầu tổ chức.

### 6.3. Phê duyệt không thay thế kiểm tra trạng thái hiện tại

Giữa lúc duyệt và thực thi, tài nguyên có thể đổi tenant, role có thể đổi nội dung hoặc quyền JIT có thể hết hạn.

Do đó, cần kiểm tra lại các điều kiện hiện tại mà policy yêu cầu. Một quyết định cũ không nên được tái sử dụng vô hạn cho trạng thái mới.

## 7. Kiểm soát khoảng cách giữa kiểm tra và thực thi

Một lỗi khó thấy xảy ra khi kiểm tra hợp lệ ở thời điểm đầu nhưng trạng thái đã đổi trước khi ghi thay đổi.

Ví dụ:

1. Backend đọc tài khoản đích thuộc tenant A.
2. Backend xác nhận người gọi quản lý tenant A.
3. Một thay đổi đồng thời chuyển đối tượng sang phạm vi khác.
4. Backend tiếp tục cập nhật mà không phát hiện trạng thái đã đổi.

Cần thiết kế tính nhất quán phù hợp với kho dữ liệu và luồng xử lý. Có thể sử dụng kiểm tra phiên bản, thao tác có điều kiện hoặc transaction theo khả năng nền tảng.

### 7.1. Kiểm tra lại ràng buộc ngay tại điểm thay đổi

Đối với thay đổi trong cùng kho dữ liệu, các ràng buộc quan trọng nên được xác nhận nhất quán với thao tác cập nhật.

Nếu trạng thái không còn khớp với phiên bản đã được kiểm tra hoặc phê duyệt, dừng và yêu cầu đánh giá lại. Không tự động chuyển một phê duyệt cho trạng thái cũ sang trạng thái mới.

Không phải mọi thuộc tính đều nằm trong một transaction. Nếu quyết định phụ thuộc dịch vụ khác, cần xác định rõ thời hạn, mức nhất quán và rủi ro còn lại thay vì tuyên bố toàn bộ luồng là nguyên tử.

### 7.2. Mã giả cho chức năng gán role

Đoạn dưới mô tả các trách nhiệm; không phải mã triển khai hoàn chỉnh:

~~~text
function changeRole(request, authenticatedContext):
    actor = resolveTrustedActor(authenticatedContext)
    intent = parseAndValidateRequest(request)

    requirePermission(
        actor,
        action = "role-assignment.change",
        requestedScope = intent.scope
    )

    approval = loadTrustedApproval(intent.approvalId)

    beginConsistentChange:
        target = loadCurrentTargetForChange(intent.targetId)
        role = loadCurrentRoleDefinition(intent.roleId)

        requireSameAuthorizedScope(actor, target, role)
        requireBusinessRules(actor, target, role)
        requireCurrentPrivilegeConditions(actor)

        requireApprovalMatches(
            approval,
            actor,
            target,
            role,
            intent.expectedVersion
        )

        requireApprovalNotExpiredOrRevoked(approval)
        requireRequestNotReplacedByAnotherPayload(intent)
        requireTargetVersion(target, intent.expectedVersion)

        result = applyRoleAssignment(target, role)
        recordApprovalUseAccordingToPolicy(approval, intent)
        persistChangeEvidence(actor, intent, result)
        commitConsistentChange

    returnSafeResult(result)
~~~

Trong một hệ thống cụ thể, cần bổ sung quản lý lỗi, retry, idempotency, giới hạn tài nguyên và bảo vệ dữ liệu. Nếu hành động nằm ở hệ thống bên ngoài, không thể giả định thao tác ngoại vi được rollback chỉ vì transaction cục bộ thất bại.

## 8. Idempotency, retry và thực thi một phần

Người dùng có thể bấm lại khi không thấy phản hồi. Client có thể retry sau timeout. Hàng đợi có thể giao lại thông điệp. Chức năng đặc quyền phải xác định cách xử lý các lần gọi này.

### 8.1. Một khóa idempotency cần gắn với đúng yêu cầu

Không nên coi cùng một khóa là đủ để cho qua một payload khác.

Hệ thống cần xác định phạm vi của khóa, chẳng hạn theo chủ thể, tenant, loại hành động và nội dung đã được ràng buộc. Nếu khóa cũ được dùng với nội dung khác, cần từ chối hoặc xử lý theo quy tắc rõ ràng.

Kết quả cũ cũng không được trả cho một người gọi không có quyền xem. Cơ chế tránh thực thi lặp không thay thế authorization đối với dữ liệu phản hồi.

### 8.2. Khi thao tác đã xảy ra nhưng phản hồi bị mất

Giả sử hệ thống đích đã nhận thay đổi, nhưng backend mất kết nối trước khi lưu kết quả.

Không nên tự ghi “FAILED” như thể chắc chắn chưa có tác động, rồi thực hiện lại mù quáng. Cần có trạng thái thể hiện chưa xác định kết quả, tham chiếu tương quan và bước đối soát.

Nếu API đích hỗ trợ idempotency hoặc tra cứu kết quả theo mã yêu cầu, có thể dùng các cơ chế đó. Nếu không, workflow phải có cách xác minh trạng thái và xử lý thủ công khi cần.

### 8.3. Audit cần phân biệt ý định và kết quả

Một sự kiện “đã yêu cầu thực hiện” không chứng minh thay đổi thành công. Có thể cần các trạng thái:

- Requested.
- Authorized hoặc denied.
- Approved nếu quy trình yêu cầu.
- Execution started.
- Succeeded.
- Failed trước khi có tác động.
- Partially completed.
- Outcome unknown, cần đối soát.
- Compensated hoặc remediated khi có xử lý tiếp theo.

Tên trạng thái tùy hệ thống, nhưng ý nghĩa phải rõ. Không nên gộp mọi lỗi kết nối thành một kết luận nghiệp vụ chắc chắn.

## 9. Chức năng đặc quyền chạy qua tác vụ nền

Một chức năng được yêu cầu qua UI có thể thực thi vài phút sau trong worker. Nếu chỉ kiểm tra ở lúc enqueue, các điều kiện có thể đã thay đổi khi job chạy.

Cần xác định policy yêu cầu kiểm tra lại những gì tại thời điểm thực thi:

- Quyền của người yêu cầu còn hiệu lực hay không.
- Phê duyệt còn hiệu lực và đúng nội dung không.
- Tài nguyên còn thuộc phạm vi đã được duyệt không.
- Chức năng có bị hủy hoặc chuyển sang trạng thái không cho phép không.
- Quyền JIT có cần còn hiệu lực tại lúc thực hiện không.
- Dịch vụ thực thi có đúng quyền tối thiểu cho tác vụ không.

Nếu thiết kế sử dụng một ủy quyền đã được phát hành, phải xác định rõ phạm vi, thời hạn, điều kiện thu hồi và ý nghĩa của việc quyền người yêu cầu thay đổi. Không mặc nhiên coi ủy quyền là vĩnh viễn.

### 9.1. Thông điệp hàng đợi không tự tạo thẩm quyền

Một thông điệp ghi “approved=true” chỉ đáng tin nếu nguồn phát, nội dung và quan hệ với hồ sơ phê duyệt được bảo vệ phù hợp.

Worker không nên thực hiện mọi payload chỉ vì nó tới từ queue nội bộ. Nó cần xác minh ngữ cảnh và ràng buộc được yêu cầu, đồng thời không cho phép payload chọn tùy ý tài khoản thực thi đặc quyền hơn.

### 9.2. Giữ dấu vết người yêu cầu ban đầu

Bản ghi job cần liên kết tới yêu cầu ban đầu, actor, quyết định phê duyệt và tài nguyên đích. Dịch vụ thực thi vẫn được ghi là bên thực thi kỹ thuật.

Không đưa credential của người dùng hoặc token đặc quyền dài hạn vào thông điệp chỉ để giữ ngữ cảnh. Dữ liệu truy nguyên và cơ chế ủy quyền cần được thiết kế riêng.

## 10. Kết hợp với PAM, JIT và giới hạn thao tác

PAM có thể hỗ trợ quản lý credential, kiểm soát phiên hoặc cấp đặc quyền theo yêu cầu. Ứng dụng vẫn cần mô hình hóa quyền của từng chức năng.

### 10.1. JIT giới hạn thời gian, không tự giới hạn hành động

Một người được cấp role tạm thời có thể vẫn có quyền quá rộng trong khoảng hiệu lực. Cần kết hợp:

- Chức năng nào được phép.
- Tài nguyên nào nằm trong phạm vi.
- Điều kiện xác thực hoặc phê duyệt nào cần đáp ứng.
- Khi nào quyền bắt đầu và kết thúc.
- Cách xử lý phiên hoặc job đã khởi tạo.

Hết hạn role không luôn đồng nghĩa mọi token, phiên hoặc job đã phát hành bị dừng ngay. Hành vi cần được xác minh theo cơ chế thực tế.

### 10.2. Giới hạn chức năng thay vì mở shell toàn quyền

Nếu nhu cầu là “khởi động lại một dịch vụ đã chỉ định”, nên xem khả năng cung cấp đúng thao tác đó qua giao diện kiểm soát thay vì mặc định cấp phiên quản trị toàn máy.

Tuy nhiên, một wrapper chỉ có vài nút chưa chắc là giới hạn thực sự. Nếu người gọi sửa được đường dẫn lệnh, script, tham số nguy hiểm hoặc cấu hình thực thi, quyền có thể mở rộng ngoài ý định.

Cần bảo vệ cả định nghĩa chức năng, nguồn mã, tham số và tài khoản kỹ thuật phía sau. Giới hạn thao tác chỉ có ý nghĩa khi các đường ảnh hưởng khác cũng được xem xét.

### 10.3. Break-glass là một luồng có trách nhiệm

Trong tình huống khẩn cấp, có thể cần đường xử lý đặc biệt. Luồng đó phải được xác định trước về thẩm quyền, phạm vi, thời hạn và hậu kiểm.

Không nên dùng một cờ do client gửi để bỏ qua toàn bộ authorization. Cũng không nên giữ quyền khẩn cấp như quyền thường trực sau khi tình huống đã kết thúc.

## 11. Bằng chứng và giám sát

Với chức năng đặc quyền, audit cần giúp trả lời:

> Ai yêu cầu, ai phê duyệt, ai thực thi, làm gì, trên tài nguyên nào, dựa trên quyết định nào và kết quả thực tế ra sao?

### 11.1. Trường dữ liệu cần cân nhắc

| Nhóm | Nội dung minh họa |
|---|---|
| Tương quan | Request ID, workflow ID, job ID |
| Chủ thể | Actor ban đầu, dịch vụ thực thi, tài khoản đích |
| Phạm vi | Tenant, môi trường, tài nguyên |
| Hành động | Function ID và loại thay đổi |
| Quyết định | Cho phép hoặc từ chối, tham chiếu policy hoặc phiên bản |
| Phê duyệt | Approval ID, người duyệt, phạm vi được duyệt |
| Thực thi | Thời điểm, trạng thái, mã tương quan hệ thống đích |
| Thay đổi | Tham chiếu trước và sau với dữ liệu đã được bảo vệ |
| Kết quả | Thành công, lỗi, một phần hoặc chưa xác định |

Không phải mọi sự kiện cần lưu toàn bộ payload. Chọn dữ liệu đủ để điều tra và kiểm toán nhưng tránh lưu secret hoặc nội dung nhạy cảm không cần thiết.

### 11.2. Lưu bằng chứng phải phù hợp với việc thực thi

Nếu policy bắt buộc có bằng chứng bền vững trước hoặc cùng thay đổi, không thực hiện hành động rồi bỏ qua lỗi ghi audit.

Với thay đổi cục bộ, có thể thiết kế bản ghi sự kiện hoặc outbox bền vững cùng transaction, rồi chuyển tới nơi lưu tập trung. Cần kiểm soát cả việc chuyển tiếp và cảnh báo khi bị tồn đọng.

Với hệ thống bên ngoài, cần workflow ghi ý định, theo dõi kết quả và đối soát. Không tuyên bố tính nguyên tử giữa hai hệ thống nếu chưa có cơ chế bảo đảm tương ứng.

### 11.3. Ghi hình phiên chưa đủ cho mọi đường gọi

Session recording có thể cung cấp ngữ cảnh cho thao tác tương tác. API, automation và job nền có thể không xuất hiện trong một phiên được ghi hình.

Vì vậy, bằng chứng ở mức chức năng và thay đổi vẫn cần thiết. Một đoạn video cũng có thể không thể hiện rõ ID tài nguyên, policy áp dụng hay kết quả cuối cùng ở hệ thống đích.

### 11.4. Tín hiệu cần điều tra

Một số tín hiệu hữu ích:

- Nhiều lần gọi chức năng ngoài phạm vi.
- Tăng đột ngột số lượng đối tượng bị thay đổi.
- Dùng phê duyệt hết hạn hoặc không khớp nội dung.
- Thay đổi quyền ngay sau khi nhận JIT.
- Thực thi qua đường gọi ít được dùng hoặc endpoint cũ.
- Xuất dữ liệu vượt kích thước hay phạm vi dự kiến.
- Có tác động tại hệ thống đích nhưng thiếu workflow tương ứng.

Các tín hiệu cần được đánh giá theo bối cảnh; một bất thường không tự chứng minh hành vi xấu. Điều quan trọng là có đủ dữ liệu để xác minh và hành động.

## 12. Tình huống xuyên suốt: API gán role vượt tenant

### Bối cảnh

Một ứng dụng quản trị có nút gán role. UI chỉ hiển thị các tài khoản trong tenant của người vận hành. Backend dùng một service account có khả năng cập nhật role trên nhiều tenant.

API kiểm tra người dùng có role “operator”, nhưng không xác minh tài khoản đích thuộc phạm vi họ quản lý.

### Vấn đề

Người vận hành có thể gửi trực tiếp ID của một tài khoản thuộc tenant khác. Nếu backend làm theo, quyền kỹ thuật của nó đã bị dùng vượt thẩm quyền người gọi.

Ẩn tài khoản tenant khác trên giao diện không giải quyết được lỗi. Bật xác thực tăng cường cũng không thay thế kiểm tra phạm vi đối tượng.

### Thiết kế điều chỉnh

1. Xác định actor từ ngữ cảnh xác thực đã được kiểm chứng.
2. Nạp tài khoản và role đích từ nguồn dữ liệu có thẩm quyền.
3. Kiểm tra actor được thực hiện loại hành động này.
4. Kiểm tra tài khoản, role và tenant đều thuộc phạm vi được phép.
5. Áp dụng quy tắc chặn tự tăng quyền hoặc gán role ngoài giới hạn.
6. Kiểm tra phê duyệt khi policy yêu cầu, ràng buộc đúng nội dung.
7. Xử lý thay đổi đồng thời bằng cơ chế nhất quán phù hợp.
8. Thực hiện và lưu bằng chứng actor, executor, đích và kết quả.
9. Bảo đảm API chạy lại và job nền áp dụng kiểm soát tương đương.

### Giảm quyền của backend

Song song với kiểm tra ứng dụng, nên xem có thể thu hẹp quyền của service account thực thi theo tenant hoặc chức năng hay không.

Nếu backend buộc phải giữ quyền rộng, cần quản lý rủi ro đó rõ ràng. Authorization ở ứng dụng trở thành một ranh giới quan trọng nhưng không phải lý do bỏ qua least privilege của tài khoản kỹ thuật.

## 13. Kiểm thử privileged function

Kiểm thử cần đi qua API hoặc điểm thực thi thực tế, không chỉ kiểm tra nút có xuất hiện trên UI.

| Tình huống | Kết quả mong đợi |
|---|---|
| Actor đúng quyền, đúng đích, đủ điều kiện | Thực hiện đúng thay đổi được phép |
| Actor thiếu quyền chức năng | Từ chối, không có tác động |
| Actor đúng chức năng nhưng đích ngoài tenant | Từ chối, không có tác động |
| Payload xin role cao hơn phạm vi được duyệt | Từ chối |
| Approval ID đúng nhưng payload đã đổi | Từ chối |
| Phê duyệt hết hạn hoặc bị thu hồi | Từ chối theo policy |
| Người yêu cầu tự duyệt khi bị cấm | Từ chối |
| Trạng thái hoặc phiên bản đối tượng thay đổi | Dừng hoặc đánh giá lại theo thiết kế |
| Gọi trực tiếp API bỏ qua UI | Vẫn chịu cùng kiểm soát |
| Job chạy sau khi điều kiện bắt buộc hết hiệu lực | Xử lý theo policy thực thi đã xác định |
| Gửi lại cùng yêu cầu | Không gây tác động lặp ngoài thiết kế |
| Dùng lại khóa cũ với payload khác | Không thực thi như thể đã được duyệt |
| Hệ thống policy hoặc audit bắt buộc không khả dụng | Không tự động mở quyền |
| Timeout sau khi hệ thống đích có thể đã thay đổi | Có trạng thái và cơ chế đối soát |

### 13.1. Kiểm tra tác động, không chỉ mã phản hồi

Một phản hồi từ chối chưa đủ nếu thay đổi đã xảy ra trước khi lỗi được trả về. Cần xác minh trạng thái đích, job liên quan và bằng chứng.

Ngược lại, một phản hồi thành công chưa đủ nếu tác vụ chỉ mới được đưa vào queue. Phản hồi và trạng thái giao diện cần phân biệt tiếp nhận với hoàn tất.

### 13.2. Kiểm thử trong môi trường phù hợp

Dùng tài khoản, tenant và dữ liệu mô phỏng để thử các ranh giới. Không chạy hành động phá hủy trên production chỉ nhằm chứng minh chức năng bị chặn.

Bằng chứng kiểm thử cần ghi đúng actor và ngữ cảnh. Nếu test dùng credential quản trị toàn hệ thống, kết quả không chứng minh quyền của người vận hành hạn chế.

## 14. Sai lầm thường gặp

### Chỉ kiểm tra đăng nhập

Đăng nhập hợp lệ không trả lời người đó được làm gì trên đối tượng nào. Cần authorization cho chức năng và tài nguyên.

### Chỉ kiểm tra role tổng quát

Một role có thể quá rộng hoặc không thể hiện tenant, môi trường và loại thay đổi. Cần bổ sung ràng buộc phù hợp với chức năng.

### Tin vào tenant hoặc cờ admin từ request

Đó là dữ liệu do người gọi kiểm soát. Máy chủ phải xác định thuộc tính thẩm quyền từ nguồn đáng tin cậy.

### Duyệt một ticket nhưng cho sửa yêu cầu sau đó

Phê duyệt phải gắn với nội dung và phạm vi thực thi. Nếu thay đổi nội dung quan trọng, cần quy trình đánh giá lại.

### Kiểm tra ở API nhưng bỏ qua worker

Tác vụ nền vẫn là đường thực thi đặc quyền. Phải thiết kế rõ ngữ cảnh, thời hạn và điều kiện được kiểm tra tại lúc chạy.

### Cho mọi thao tác chạy dưới một tài khoản toàn quyền

Làm tăng tác động khi logic ứng dụng hoặc một đường gọi bị lỗi. Cần đánh giá tách danh tính thực thi và thu hẹp permission theo chức năng.

### Ghi “thành công” khi chỉ mới gửi lệnh

Cần phân biệt yêu cầu được tiếp nhận, lệnh được gửi và trạng thái đích đã được xác minh.

### Lưu toàn bộ request vào audit

Payload có thể chứa secret hoặc dữ liệu nhạy cảm. Chỉ ghi các trường cần thiết với cơ chế bảo vệ phù hợp.

## 15. Bài tập thực hành

Một ứng dụng hỗ trợ có ba chức năng:

- Mở khóa một tài khoản thuộc phạm vi được giao.
- Xuất danh sách tài khoản của một tenant.
- Gán role vận hành cho người dùng khác.

Backend dùng một service account có quyền trên nhiều tenant. UI ẩn các nút theo role; API hiện chỉ yêu cầu đăng nhập.

Hãy thiết kế trên mô hình giả lập:

1. Lập danh mục ba chức năng với actor, action, resource và scope.
2. Chỉ ra những kiểm tra bắt buộc phải thực hiện phía máy chủ.
3. Xác định chức năng hoặc trường hợp nào cần phê duyệt theo policy giả định của bạn.
4. Nêu cách ràng buộc phê duyệt với payload.
5. Thiết kế dữ liệu audit để truy nguyên người yêu cầu và dịch vụ thực thi.
6. Nêu cách xử lý export chạy nền khi quyền hoặc phạm vi thay đổi.
7. Viết ba tình huống kiểm thử vượt tenant và thay payload.
8. Xác định cách xử lý khi timeout khiến kết quả chưa rõ.

### Gợi ý đánh giá

Một phương án tốt không chỉ thêm kiểm tra “isOperator”. Nó phải phân biệt loại chức năng, tài nguyên đích và phạm vi của actor.

Với export, cần kiểm soát phạm vi dữ liệu, nơi nhận kết quả và quyền tải kết quả. Người không được xem dữ liệu không nên lấy được một file đã tạo chỉ bằng cách biết ID job.

Với gán role, cần kiểm tra actor được cấp role nào, cho ai và có bị quy tắc phân tách nhiệm vụ giới hạn không.

Với tác vụ nền, mô tả rõ thẩm quyền được kiểm tra lúc yêu cầu và lúc thực thi. Với kết quả chưa rõ, có trạng thái đối soát thay vì tự động thực hiện lại không giới hạn.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao ẩn nút quản trị không bảo vệ đủ một chức năng đặc quyền?**

Vì người gọi có thể đi trực tiếp qua API hoặc đường khác. Quyết định phải được thực thi phía máy chủ tại điểm kiểm soát hành động.

**2. Một người đã qua xác thực tăng cường có được gọi mọi chức năng đặc quyền không?**

Không. Vẫn phải kiểm tra quyền chức năng, phạm vi tài nguyên và các điều kiện liên quan.

**3. Vì sao cần ghi cả actor và executor?**

Actor giải thích ai yêu cầu; executor giải thích thành phần nào thực hiện hành động kỹ thuật. Giữ cả hai giúp truy nguyên mà không làm sai nguồn gốc.

**4. Phê duyệt hợp lệ có thể được dùng cho payload khác không?**

Không được coi là hợp lệ cho nội dung khác nếu chưa có cơ chế chấp thuận tương ứng. Phê duyệt phải ràng buộc với hành động, đích và phạm vi được duyệt.

**5. Kiểm tra quyền lúc enqueue đã đủ cho mọi job chưa?**

Chưa thể kết luận. Cần xác định những điều kiện phải còn đúng khi thực thi, cách ủy quyền và cách xử lý khi điều kiện thay đổi.

**6. Vì sao timeout không luôn đồng nghĩa thao tác chưa xảy ra?**

Hệ thống đích có thể đã áp dụng thay đổi trước khi phản hồi bị mất. Cần đối soát hoặc cơ chế idempotency phù hợp.

**7. Session recording có thay thế audit ở mức chức năng không?**

Không. Các đường API và automation cần bằng chứng riêng; ghi hình cũng không luôn thể hiện policy, tài nguyên và kết quả cuối cùng.

**8. Nếu backend có quyền rộng thì ứng dụng có thể bỏ kiểm tra người gọi không?**

Không. Backend phải bảo đảm việc sử dụng quyền kỹ thuật nằm trong thẩm quyền của người yêu cầu và các ràng buộc của chức năng.

## 17. Điểm cần ghi nhớ

Privileged function là một điểm sử dụng quyền cần được kiểm soát theo tác động, tài nguyên và phạm vi. Tên role, màn hình quản trị hay phiên đăng nhập chỉ cung cấp một phần ngữ cảnh.

Một thiết kế đáng tin cậy giữ được sự liên kết giữa người yêu cầu, quyết định cấp quyền, phê duyệt, thực thi và kết quả thực tế. Kiểm soát phải theo chức năng qua mọi đường gọi, bao gồm API, tác vụ nền, chạy lại và xử lý khẩn cấp.
