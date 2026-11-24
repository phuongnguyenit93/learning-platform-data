# Authorization matrix documentation — Tài liệu ma trận phân quyền

## 1. Mục tiêu và phạm vi

Một bảng ghi “nhân viên được sửa, quản lý được duyệt, admin được làm tất cả” chưa đủ để bảo vệ quy tắc nghiệp vụ. Người sửa đối tượng nào? Trong tenant nào? Được sửa trường nào và ở trạng thái nào? Người tạo yêu cầu có được tự duyệt nếu đồng thời giữ vai trò quản lý không?

**Authorization matrix documentation** là việc mô tả có cấu trúc ai được thực hiện hành động nào trên tài nguyên nào, trong điều kiện gì, và những giới hạn nào vẫn phải giữ. Ma trận giúp nối yêu cầu nghiệp vụ với kiểm soát tại API, worker, công cụ quản trị và bộ kiểm thử.

Bài học thuộc chương Documentation của module SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY. Trọng tâm là bảo vệ bất biến nghiệp vụ khỏi thao tác sai quyền, sửa giá, bỏ phê duyệt, chuyển trạng thái sai và xử lý yêu cầu trùng. Một bảng vai trò chỉ là điểm vào; tài liệu cần đi tới quyền theo đối tượng, trường dữ liệu, transaction và idempotency.

Sau bài học, bạn có thể:

- Chọn đúng đơn vị hành động, tài nguyên và điều kiện cho ma trận.
- Phân biệt vai trò có khả năng thực hiện với quyết định cho phép trên một đối tượng cụ thể.
- Ghi rõ quyền theo trường, trạng thái, hạn mức và quan hệ giữa các chủ thể.
- Mô tả cách áp dụng quyền trên luồng bất đồng bộ và lúc điều kiện thay đổi.
- Chuyển từng dòng thành ca kiểm thử hợp lệ, vượt quyền và cạnh tranh.
- Quản lý phiên bản, bằng chứng triển khai và thay đổi chính sách.

## 2. Ma trận phân quyền cần trả lời những câu hỏi nào?

Một quyết định phân quyền thường phụ thuộc vào nhiều chiều:

```text
decision = authorize(
    authenticatedSubject,
    businessAction,
    trustedResource,
    requestedFieldSet,
    verifiedContext,
    effectivePolicyVersion
)
```

Đây là mô hình khái niệm, không phải API của một thư viện cụ thể.

| Chiều | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Chủ thể | Ai hoặc dịch vụ nào đang thao tác? | Nhân viên, người duyệt, worker |
| Hành động | Hiệu lực nghiệp vụ nào được yêu cầu? | Sửa bản nháp, duyệt hoàn tiền, thực hiện hoàn |
| Tài nguyên | Đối tượng và đối tượng liên quan nào bị tác động? | Yêu cầu hoàn, khoản thanh toán, đơn hàng |
| Phạm vi | Quan hệ nào cho phép tác động? | Tenant, chủ sở hữu, hồ sơ được giao, ủy quyền |
| Trường | Được xem hoặc thay đổi thuộc tính nào? | Được sửa lý do nhưng không sửa người tạo |
| Trạng thái | Đối tượng đang ở giai đoạn nào? | Chỉ sửa khi DRAFT |
| Ngữ cảnh | Điều kiện bổ sung có hiệu lực không? | Phân công còn hiệu lực, hạn mức duyệt, ngoại lệ |
| Thời điểm | Quyền được xét tại bước nào? | Lúc nhận lệnh, worker chạy, công bố hoặc tải file |

Quyền gọi endpoint không đồng nghĩa quyền trên mọi object ID mà endpoint nhận. Cùng vai trò và cùng tenant cũng chưa đủ nếu chính sách yêu cầu quan hệ chủ sở hữu hoặc được phân công.

Hành động nên là hành động nghiệp vụ. PUT một đối tượng có thể vừa đổi số tiền, đổi người thụ hưởng và kích hoạt trạng thái đã duyệt. Nếu tài liệu chỉ có quyền “update”, các hiệu lực khác nhau dễ bị gộp vào một quyền quá rộng.

## 3. Chuẩn hóa đầu vào và nguồn tin cậy

Trước khi lập bảng, xác định nguồn của các thuộc tính dùng để ra quyết định.

| Thuộc tính | Nguồn có thể dùng theo thiết kế | Điều không được mặc định tin |
| --- | --- | --- |
| Subject ID | Danh tính đã xác thực qua ranh giới tin cậy | actorId tự khai trong body |
| Vai trò hoặc quyền được cấp | Kho quyền hoặc thông tin xác thực được xác minh, còn hiệu lực theo hợp đồng | Chuỗi role do client gửi |
| Tenant của tài nguyên | Bản ghi tài nguyên hoặc ánh xạ đáng tin cậy | Chỉ tenantId trong URL hoặc header |
| Người tạo | Thuộc tính được server gán và bảo vệ | createdBy trong payload cập nhật |
| Người được giao | Dữ liệu phân công có phiên bản và thời hạn phù hợp | Người gọi tự đặt assignedTo |
| Trạng thái, revision | Dữ liệu đã commit hoặc phiên bản được kiểm soát | status do client đề nghị |
| Số tiền và tiền tệ | Dữ liệu nghiệp vụ đã xác minh | Giá trị yêu cầu chưa đối chiếu với đối tượng |
| Phê duyệt | Bản ghi phê duyệt gắn đúng nội dung và phạm vi | approved=true do người gọi gửi |
| Idempotency key | Định danh yêu cầu cần ràng buộc với chủ thể, phạm vi và nội dung | Bằng chứng đã được cấp quyền |

Tài liệu cần mô tả ranh giới xác minh, không chỉ tên trường. Token đã được xác thực vẫn có thể chứa quyền cũ; cần quy định thời hạn hiệu lực, cách thay đổi quyền được áp dụng và cách xử lý cache.

Với dịch vụ thay mặt người dùng, phân biệt danh tính dịch vụ với danh tính người ủy quyền. Quyền kết nối của service không tự hợp thức hóa mọi tác động tới dữ liệu người dùng.

Với webhook hoặc message, danh tính nguồn phải được ràng buộc với cơ chế tích hợp đáng tin. Trường source có tên đúng không tự chứng minh người gửi có quyền tác động tới khoản thanh toán hoặc tenant được khai.

## 4. Quy ước đọc ma trận và kết hợp quyền

### 4.1. Ô cho phép phải dẫn tới điều kiện

Trong bài này:

- Ô chứa mã R-xx nghĩa là vai trò có thể được xem xét theo quy tắc đó.
- Dấu “—” nghĩa là vai trò không cấp khả năng cho hành động trong chính sách minh họa.
- Có vai trò phù hợp không có nghĩa bỏ qua điều kiện theo đối tượng, trường hoặc trạng thái.
- Thiếu hành động hoặc thiếu quy tắc phù hợp dẫn tới từ chối theo mặc định của chính sách này.

Không dùng ô trống để đồng thời mang nghĩa “chưa quyết định”, “không áp dụng” và “cho phép”. Nếu chính sách chưa rõ, ghi rõ khoảng trống và người chịu trách nhiệm giải quyết; không tự suy ra quyền từ bảng chưa hoàn thiện.

### 4.2. Nhiều vai trò không được xóa điều kiện cấm

Trong chính sách minh họa, các điều kiện cấm bắt buộc được xét trước. Sau đó mới tìm quyền phù hợp và kiểm tra điều kiện của quyền đó.

Ví dụ, cùng giữ REQUESTER và APPROVER không cho phép tự duyệt yêu cầu mình tạo. Điều kiện tách nhiệm vụ áp dụng cho danh tính chủ thể, không phụ thuộc người dùng chọn vai trò nào trong giao diện.

Đây là quy tắc kết hợp của ví dụ. Hệ thống sử dụng cơ chế kết hợp khác phải ghi rõ thứ tự, xung đột và kết quả; không mặc định mọi policy engine đều có cùng hành vi.

### 4.3. Tách từ chối quyền khỏi xung đột nghiệp vụ

Người được phép duyệt có thể nhận xung đột vì revision đã thay đổi hoặc trạng thái không còn chờ duyệt. Kết quả đó khác với một người không có quyền duyệt.

Tài liệu nên phân biệt kết quả nội bộ như DENY_AUTHORIZATION, REJECT_BUSINESS_PRECONDITION, CONFLICT_VERSION và INDETERMINATE. Hợp đồng trả lỗi bên ngoài phải tránh lộ thông tin đối tượng ngoài quyền; không nhất thiết công khai toàn bộ lý do nội bộ.

## 5. Xác định phạm vi ví dụ hoàn tiền

### 5.1. Đối tượng và trạng thái

Ví dụ dùng yêu cầu hoàn tiền F gắn với khoản thanh toán P và một hồ sơ xử lý trong cùng tenant. Các giá trị tiền dùng số nguyên theo đơn vị tiền được quy định; không trộn tiền tệ khi xét hạn mức.

State machine rút gọn:

```text
DRAFT -> PENDING_APPROVAL -> APPROVED -> EXECUTING -> SUCCEEDED
   |             |                            |
   v             v                            v
CANCELLED     REJECTED                 FAILED or OUTCOME_UNKNOWN
```

Trong ví dụ, người tạo có thể hủy ở DRAFT hoặc PENDING_APPROVAL; sơ đồ chỉ thể hiện một số nhánh để dễ đọc. Trạng thái kết quả chưa rõ của dịch vụ ngoài không được coi như chưa từng tạo hiệu lực.

Bản nháp được sửa trước khi gửi duyệt. Sau khi gửi, thay đổi nội dung quyết định nghiệp vụ phải đi qua quy trình sửa đổi được định nghĩa riêng; mẫu này không cho phép sửa trực tiếp số tiền trên yêu cầu đã duyệt.

Phê duyệt không tự tạo khoản hoàn bên ngoài. Bước thực thi còn phải kiểm tra hạn mức khả dụng, giữ nghĩa vụ nguyên tử và điều phối kết quả theo thiết kế.

### 5.2. Các vai trò

| Vai trò | Trách nhiệm trong ví dụ | Giới hạn quan trọng |
| --- | --- | --- |
| REQUESTER | Tạo và quản lý bản nháp trong hồ sơ được giao | Không tự duyệt hoặc thực thi |
| APPROVER | Duyệt hoặc từ chối trong phạm vi được giao | Không duyệt yêu cầu mình tạo, không vượt hạn mức |
| EXECUTOR_SERVICE | Thực thi yêu cầu đã được duyệt | Chỉ dùng danh tính dịch vụ và phạm vi công việc được cấp |
| TENANT_ADMIN | Quản lý thành viên cơ bản theo phạm vi riêng | Không mặc nhiên có quyền hoàn tiền |
| AUDITOR | Đọc dữ liệu kiểm toán được giới hạn | Không sửa, duyệt hoặc thực thi |

Một tài khoản có thể giữ nhiều vai trò, nhưng điều kiện cấm vẫn áp dụng. TENANT_ADMIN trong mẫu không được tự cấp vai trò tài chính hoặc tăng hạn mức duyệt. Các quyền nhạy cảm đó cần quy trình và ma trận riêng.

### 5.3. Quan hệ theo đối tượng

REQUESTER chỉ tạo trên khoản thanh toán thuộc hồ sơ được giao còn hiệu lực. Với yêu cầu đã tạo, quyền sửa và hủy còn yêu cầu người thao tác là người tạo và quan hệ phân công vẫn phù hợp.

APPROVER phải có phạm vi duyệt và phân công phù hợp với hồ sơ. AUDITOR cần phạm vi kiểm toán được cấp. Cùng tenant là điều kiện cần trong mẫu, không phải điều kiện đủ.

## 6. Ma trận vai trò và quy tắc theo đối tượng

### 6.1. Bảng khả năng

| Hành động nghiệp vụ | REQUESTER | APPROVER | EXECUTOR_SERVICE | TENANT_ADMIN | AUDITOR |
| --- | --- | --- | --- | --- | --- |
| Tạo bản nháp hoàn tiền | R-01 | — | — | — | — |
| Đọc yêu cầu hoàn tiền | R-02 | R-03 | R-04 | — | R-05 |
| Sửa bản nháp | R-06 | — | — | — | — |
| Gửi yêu cầu duyệt | R-07 | — | — | — | — |
| Duyệt yêu cầu | — | R-08 | — | — | — |
| Từ chối yêu cầu | — | R-09 | — | — | — |
| Thực thi yêu cầu | — | — | R-10 | — | — |
| Hủy yêu cầu | R-11 | — | — | — | — |
| Quản lý thành viên cơ bản | — | — | — | R-12 | — |

Tên hành động là hợp đồng nghiệp vụ, chưa phải danh sách endpoint. Một hành động có thể được tiếp cận từ nhiều kênh; mọi kênh phải được ánh xạ tới đúng quy tắc.

### 6.2. Điều kiện bắt buộc

| Quy tắc | Điều kiện theo đối tượng và ngữ cảnh | Hiệu lực được phép |
| --- | --- | --- |
| R-01 | Tenant đã xác minh khớp P; có phân công hợp lệ; P thuộc hồ sơ; trường đầu vào hợp lệ | Tạo DRAFT với người tạo do server gán |
| R-02 | Có quyền REQUESTER và là người tạo hoặc có phân công đọc phù hợp | Đọc bộ trường REQUESTER_VIEW |
| R-03 | Có phạm vi và phân công duyệt với hồ sơ của F | Đọc bộ trường APPROVAL_VIEW |
| R-04 | Service đã xác thực, công việc được cấp gắn đúng tenant và F | Đọc bộ trường EXECUTION_MINIMUM |
| R-05 | Có phạm vi kiểm toán phù hợp với F | Đọc bộ trường AUDIT_MASKED |
| R-06 | Là người tạo; còn phân công; F ở DRAFT; revision khớp | Sửa các trường bản nháp được liệt kê |
| R-07 | Là người tạo; còn phân công; DRAFT hợp lệ; revision khớp | Chuyển sang PENDING_APPROVAL |
| R-08 | Có phân công duyệt; khác người tạo; PENDING_APPROVAL; revision khớp; trong hạn mức theo tiền tệ | Ghi phê duyệt cho đúng nội dung và chuyển APPROVED |
| R-09 | Có phân công duyệt; khác người tạo; PENDING_APPROVAL; revision khớp | Ghi lý do từ chối và chuyển REJECTED |
| R-10 | Service hợp lệ; quyền công việc đúng F; phê duyệt còn hợp lệ và khớp revision; đủ điều kiện thực thi | Giữ nghĩa vụ và bắt đầu thực thi theo hợp đồng |
| R-11 | Là người tạo; còn phân công; DRAFT hoặc PENDING_APPROVAL; revision khớp | Chuyển CANCELLED, không tạo khoản hoàn |
| R-12 | Tenant admin đúng phạm vi; chỉ loại thành viên cơ bản được liệt kê | Quản lý tư cách thành viên cơ bản, không cấp quyền tài chính |

Mọi dòng tác động tới F phải ràng buộc F, P và hồ sơ với tenant đã xác minh theo chính sách này. Không chỉ so sánh tenant của người gọi với một tham số URL.

Hạn mức duyệt áp dụng cho R-08. R-09 trong mẫu không dùng hạn mức số tiền để ngăn người được phân công từ chối yêu cầu; đây là khác biệt có chủ đích cần được ghi rõ.

“Đủ điều kiện thực thi” của R-10 phải được triển khai thành các tiền điều kiện cụ thể: số tiền và tiền tệ đúng, khoản thanh toán phù hợp, khả năng hoàn còn đủ, chưa có hiệu lực cùng thao tác và kết quả bên ngoài không đang bị xử lý sai như thất bại chắc chắn. Ma trận dẫn tới đặc tả các điều kiện này, không thay thế chúng bằng một nhãn chung.

## 7. Ma trận quyền theo trường và hiệu lực

Quyền sửa đối tượng không đồng nghĩa quyền sửa mọi thuộc tính. Tài liệu cần liệt kê rõ tập trường được nhận, tập trường được trả và các trường chỉ server được gán.

| Thuộc tính | Khi tạo bản nháp | Khi sửa bản nháp | Khi duyệt hoặc thực thi |
| --- | --- | --- | --- |
| Tenant | Suy ra và xác minh từ phạm vi đã cấp | Không đổi qua lệnh sửa | Giữ nguyên, đối chiếu lại với đối tượng |
| Người tạo | Server gán từ danh tính đã xác thực | Không cho client đổi | Dùng cho điều kiện tách nhiệm vụ |
| Khoản thanh toán | Nhận tham chiếu rồi xác minh quan hệ | Mẫu này không cho đổi trực tiếp | Phải khớp nội dung được duyệt |
| Số tiền và tiền tệ | Nhận theo hợp đồng, kiểm tra tính hợp lệ | Chỉ REQUESTER ở DRAFT theo R-06 | Không sửa kèm lệnh duyệt hoặc thực thi |
| Lý do yêu cầu | Nhận theo giới hạn và chính sách dữ liệu | Được sửa ở DRAFT | Không dùng để chèn trường điều khiển |
| Trạng thái | Server đặt DRAFT | Không nhận như trường tùy ý | Chỉ chuyển qua lệnh nghiệp vụ hợp lệ |
| Người duyệt, thời điểm duyệt | Chưa có | Client không được gán | Server ghi khi R-08 thành công |
| Nội dung đã duyệt | Chưa có | Không tự khai | Gắn với content revision được duyệt |
| Kết quả nhà cung cấp | Chưa có | Client không được gán | Ghi từ nguồn được xác minh |

Nếu API dùng object binding hoặc patch tổng quát, phải ghi rõ cách xử lý trường ngoài tập cho phép: từ chối hay bỏ qua theo hợp đồng. Trong mẫu, yêu cầu cố sửa trường điều khiển như trạng thái, tenant hoặc người duyệt bị từ chối; không chỉ âm thầm nhận rồi hy vọng serializer không áp dụng.

Các bộ trường đọc cũng cần định nghĩa, chẳng hạn:

- REQUESTER_VIEW: tham chiếu yêu cầu, số tiền, tiền tệ, trạng thái và thông tin cần theo dõi yêu cầu.
- APPROVAL_VIEW: thông tin cần đánh giá phê duyệt, bằng chứng liên quan và revision nội dung.
- EXECUTION_MINIMUM: tham chiếu thao tác, khoản thanh toán, số tiền, tiền tệ và dữ liệu kỹ thuật tối thiểu để thực thi.
- AUDIT_MASKED: tham chiếu kiểm toán, trạng thái, số tiền và lịch sử quyết định đã giảm dữ liệu theo chính sách.

Không mặc định bộ trường này chứa số tài khoản đầy đủ, token hoặc nội dung tự do có dữ liệu cá nhân. Nếu quy trình cần dữ liệu bổ sung, nêu căn cứ, đối tượng nhận và cách kiểm soát riêng.

Một vai trò có quyền đọc bản ghi vẫn có thể không có quyền đọc một trường nhạy cảm, download file đính kèm hoặc xuất hàng loạt. Các hành động đó cần dòng và điều kiện riêng khi nằm trong phạm vi hệ thống.

## 8. Viết đặc tả đầy đủ cho một ô cho phép

Mỗi mã quy tắc nên dẫn tới một đặc tả có thể triển khai và kiểm thử. R-08 có thể được mô tả như sau:

```text
Rule: R-08
Action: refund.approve
Subject:
    authenticated human principal with APPROVER capability
Resource:
    refund F, related payment P, assigned case
Required scope:
    verified tenant match
    active approval assignment covering F
Mandatory exclusion:
    canonical subject identity differs from F.createdByPrincipalRef
Business preconditions:
    F.state = PENDING_APPROVAL
    request row version matches current row version
    F.amountMinor <= subject approval limit for F.currency
Approved content:
    payment reference, amount, currency, destination reference,
    and other policy-defined decision fields
Allowed effect:
    create approval bound to current contentRevision
    transition F to APPROVED atomically
Forbidden effect:
    modify amount, tenant, creator, or destination during approval
Decision evidence:
    rule ID, policy version, subject reference, object reference,
    content revision, row version and outcome
```

Các tên là mô tả hợp đồng, không phải cú pháp cấu hình của một policy engine.

### 8.1. Phân biệt content revision và row version

Hai loại phiên bản thường phục vụ mục tiêu khác nhau:

- **Content revision** thay đổi khi nội dung quyết định nghiệp vụ thay đổi, chẳng hạn số tiền hoặc người thụ hưởng.
- **Row version** thay đổi khi cập nhật bản ghi để phát hiện cạnh tranh, có thể bao gồm cả chuyển trạng thái.

Phê duyệt cần gắn với content revision. Lệnh duyệt cần so sánh row version để tránh ghi đè cập nhật cạnh tranh. Khi chuyển từ PENDING_APPROVAL sang APPROVED làm row version tăng, điều đó không tự làm phê duyệt vừa ghi mất hiệu lực.

Do đó, từ “revision khớp” trong bảng phải được cụ thể hóa theo từng bước. Không dùng một giá trị không có định nghĩa cho mọi loại so sánh.

### 8.2. Định nghĩa biên và dữ liệu thiếu

Hạn mức cần đơn vị, tiền tệ, nguồn và quy tắc biên. Trong mẫu, số tiền bằng hạn mức được phép xét duyệt; vượt hạn mức thì không được duyệt theo R-08.

Nếu chưa có hạn mức cho tiền tệ tương ứng, không tự quy đổi bằng tỷ giá bất kỳ hoặc coi như không giới hạn. Kết quả phải theo hợp đồng về thiếu cấu hình và được ghi nhận phù hợp.

Danh tính dùng cho tách nhiệm vụ cũng cần rõ. Nếu tổ chức yêu cầu tách theo con người, hai tài khoản thuộc cùng một người không được coi như hai chủ thể độc lập chỉ vì account ID khác nhau. Cần nguồn liên kết danh tính đáng tin cậy theo mô hình đó.

### 8.3. Ghi ví dụ được phép và bị từ chối

| Tình huống | Kết quả theo mẫu |
| --- | --- |
| Đúng vai trò, phân công, tenant, khác người tạo, số tiền bằng hạn mức | Có thể duyệt nếu các tiền điều kiện khác đạt |
| Có APPROVER nhưng chưa được phân công hồ sơ | Từ chối theo phạm vi |
| Cùng giữ REQUESTER và APPROVER, duyệt yêu cầu của chính mình | Từ chối do tách nhiệm vụ |
| Đúng quyền nhưng row version cũ | Xung đột phiên bản, không ghi phê duyệt mới |
| Số tiền đã đổi sau lần đọc | Đánh giá lại nội dung hiện tại theo hợp đồng, không duyệt mù |
| Dữ liệu quyền hoặc phân công không xác định được | Chưa xác định quyết định; không mặc định cho phép |

Ví dụ giúp loại bỏ các cách diễn giải khác nhau của cùng một ô. Chúng bổ trợ đặc tả, không thay thế danh sách điều kiện đầy đủ.

## 9. Nối ma trận với state machine và phê duyệt

Ma trận trả lời ai có khả năng yêu cầu chuyển đổi; state machine và điều kiện nghiệp vụ quyết định chuyển đổi nào hợp lệ trên trạng thái hiện tại.

| Chuyển đổi | Quy tắc | Điều không được bỏ qua |
| --- | --- | --- |
| Chưa có yêu cầu -> DRAFT | R-01 | Quan hệ với khoản thanh toán và hồ sơ |
| DRAFT -> DRAFT với nội dung mới | R-06 | Tập trường cho phép, content revision và row version |
| DRAFT -> PENDING_APPROVAL | R-07 | Nội dung hợp lệ, không chèn trạng thái được duyệt |
| PENDING_APPROVAL -> APPROVED | R-08 | Tách nhiệm vụ, hạn mức, phiên bản và phạm vi |
| PENDING_APPROVAL -> REJECTED | R-09 | Quyền từ chối và trạng thái hiện tại |
| APPROVED -> EXECUTING | R-10 | Phê duyệt đúng nội dung, quyền service và khả năng hoàn |
| DRAFT hoặc PENDING_APPROVAL -> CANCELLED | R-11 | Người tạo, phân công và điều kiện cạnh tranh |

Không cho endpoint cập nhật trạng thái tổng quát trở thành đường đi vòng quanh các lệnh này. Công cụ quản trị, import và job sửa dữ liệu cũng cần hành động được cấp quyền cụ thể.

Cần ghi rõ tuổi thọ của phê duyệt: điều gì làm hết hiệu lực, ai được thu hồi, có hết hạn không và nội dung nào làm phê duyệt cũ không còn áp dụng.

Thu hồi vai trò của người duyệt không mặc nhiên có cùng nghĩa với thu hồi mọi quyết định họ đã tạo. Chính sách phải quy định quyết định đã cấp có tiếp tục hợp lệ hay không. Trong mẫu, worker dùng bản ghi phê duyệt còn hiệu lực theo điều kiện đã công bố; không tự suy luận lại bằng vai trò hiện tại của người duyệt rồi thay đổi ý nghĩa lịch sử.

Nếu cho phép sửa yêu cầu sau duyệt, cần quy trình riêng để tăng content revision, làm mất hiệu lực hoặc thay thế phê duyệt cũ và kiểm soát công việc đã chạy. Không chỉ mở thêm quyền sửa trong ma trận rồi bỏ qua các hiệu lực đang diễn ra.

## 10. Ánh xạ quyền tới mọi kênh xử lý

### 10.1. API chi tiết, danh sách và tìm kiếm

Tài liệu cần chỉ ra nơi thực thi quyền theo đối tượng. Với danh sách, truy vấn và tìm kiếm, chỉ kiểm tra vai trò trước khi trả mọi bản ghi là không đủ.

Cần mô tả phạm vi của tập kết quả, trường dữ liệu, tổng số, bộ lọc, gợi ý tìm kiếm và thông tin phân trang. Một endpoint không trả nội dung bản ghi nhưng làm lộ sự tồn tại hoặc số lượng đối tượng ngoài quyền vẫn có thể vi phạm hợp đồng.

Cursor hoặc token phân trang không tự cấp quyền. Nếu dùng lại sau thay đổi quyền, hệ thống phải thực thi chính sách đã công bố thay vì tin rằng “đã được cấp cursor” nghĩa là tiếp tục được đọc.

### 10.2. Batch, import và export

Hành động hàng loạt cần quyết định ở cấp tập và cấp từng đối tượng theo mô hình. Tài liệu phải chọn rõ toàn bộ cùng thành công hoặc có kết quả riêng từng phần; không để người đọc tự suy đoán.

Lỗi cho một phần tử không được vô tình làm lộ chi tiết phần tử ngoài quyền. Cần giới hạn số lượng, trường và loại tài nguyên phù hợp, đồng thời giữ khả năng truy nguyên hiệu lực đã tạo.

Export và download là hành động riêng nếu chúng có phạm vi hoặc tác động khác đọc một bản ghi. Việc file được tạo đúng quyền không tự chứng minh người tải có quyền tại thời điểm tải.

### 10.3. Worker, message và công cụ vận hành

Ghi rõ worker dùng quyền nào: quyền service độc lập, quyền được ủy quyền có giới hạn, hay quyết định đã cấp còn hiệu lực theo hợp đồng. Không để câu “worker nội bộ” thay thế mô hình quyền.

Message phải ràng buộc đúng thao tác, đối tượng và tenant. Worker không được tin một tenant hoặc số tiền bị sửa trong payload để mở rộng phạm vi công việc.

Các đường retry, dead-letter queue và phát lại phải giữ cùng giới hạn. Chuyển thông điệp sang hàng đợi khác không cấp thêm quyền thực thi.

Công cụ quản trị và thao tác khẩn cấp cần hành động, phạm vi, căn cứ và bằng chứng riêng. Không ghi “admin bypass” như một quyền không có giới hạn hoặc thời hạn.

### 10.4. Thời điểm áp dụng thay đổi quyền

Ma trận cần quy định quyền được đánh giá lúc nhận lệnh, lúc thực thi, lúc công bố kết quả hay lúc tải. Với luồng nhiều bước, có thể cần nhiều điểm đánh giá có mục tiêu khác nhau.

Nếu dùng cache hoặc token có thời hạn, nêu cửa sổ cập nhật quyền và cách xử lý thu hồi. Không tuyên bố thu hồi tức thời nếu các đường thực thi vẫn có thể dùng quyền cũ trong thời gian đã thiết kế.

Điểm quan trọng là hợp đồng phải rõ và được kiểm thử. Không áp một quy tắc thời điểm duy nhất cho mọi loại quyết định nghiệp vụ khi ý nghĩa của chúng khác nhau.

## 11. Transaction, cạnh tranh và idempotency

### 11.1. Kiểm tra rồi sử dụng là một ranh giới cần đặc tả

Sau khi kiểm tra quyền, tài nguyên có thể đổi chủ sở hữu, trạng thái hoặc nội dung trước khi hiệu lực được ghi. Đây là vấn đề thời điểm kiểm tra và thời điểm sử dụng.

Với dữ liệu trong cùng database, tài liệu có thể yêu cầu kiểm tra phiên bản, cập nhật có điều kiện hoặc cơ chế khóa phù hợp trong ranh giới transaction. Phải nói rõ điều kiện nào được bảo vệ và điều gì xảy ra khi cạnh tranh.

Transaction không tự làm dữ liệu quyền ở hệ thống ngoài trở nên đồng bộ nguyên tử. Nếu phân quyền lấy từ cache hoặc dịch vụ độc lập, nêu phiên bản, thời hạn hiệu lực và ranh giới bảo đảm; không vẽ một transaction bao phủ mọi hệ thống khi thực tế không có.

### 11.2. Quyền hợp lệ chưa chứng minh bất biến tổng hợp được giữ

Hai yêu cầu có thể đều được phép theo vai trò và đối tượng nhưng cùng tiêu thụ vượt hạn mức hoàn. R-10 cần nối tới cơ chế giữ nghĩa vụ nguyên tử, không chỉ một lần đọc “còn đủ tiền”.

Tương tự, phê duyệt hợp lệ không cho phép thực hiện cùng thao tác hai lần. Tài liệu phải tách kiểm tra quyền, kiểm tra trạng thái, bảo vệ tổng hợp và chống hiệu lực trùng, đồng thời chỉ ra chúng phối hợp ở đâu.

### 11.3. Idempotency không cấp quyền

Khóa chống trùng nên được ràng buộc theo phạm vi thao tác, danh tính hoặc căn cứ ủy quyền phù hợp, và nội dung có ý nghĩa nghiệp vụ.

Các trường hợp cần ghi rõ:

- Cùng khóa và cùng nội dung sau khi thao tác đã hoàn tất.
- Cùng khóa nhưng khác số tiền, tài nguyên hoặc tenant.
- Người không có quyền dùng khóa của người khác để lấy kết quả cũ.
- Quyền thay đổi trước khi người gọi đọc lại kết quả.
- Retry khi kết quả bên ngoài chưa rõ.

Tìm thấy idempotency key không được làm bỏ qua quyền đọc kết quả hoặc trả artifact ngoài phạm vi. Ngược lại, việc từ chối một lượt truy cập mới không chứng minh hiệu lực bên ngoài trước đó đã bị hủy.

Không cho request chưa được xác thực hoặc ngoài quyền tùy tiện chiếm khóa làm thao tác hợp lệ sau đó bị bỏ qua. Ranh giới xác minh và ghi trạng thái tiếp nhận cần được nêu rõ theo thiết kế.

### 11.4. Lỗi nguồn quyền

Nếu không xác định được quyền, kết quả là chưa xác định theo hợp đồng. Không biến lỗi kho quyền thành quyền cho phép hoặc âm thầm dùng vai trò do người gọi khai.

Hành vi từ chối, yêu cầu thử lại hay giữ công việc chờ phải được quy định cho từng đường. Chỉ cho phép cơ chế dự phòng có phạm vi, thời hạn và căn cứ rõ ràng nếu chính sách cho phép nó.

## 12. Suy ra kiểm thử từ ma trận

Mỗi dòng cần ít nhất một ca hợp lệ và các ca chỉ thay một điều kiện quan trọng. Chỉ thử “không có vai trò” sẽ bỏ qua phần lớn lỗi quyền theo đối tượng.

| Mã | Biến thể | Kết quả cần kiểm tra |
| --- | --- | --- |
| AM-01 | Đúng vai trò, đối tượng, phạm vi và trạng thái | Đúng hiệu lực và tập trường |
| AM-02 | Có vai trò nhưng tài nguyên thuộc tenant khác | Không đọc, sửa hoặc tạo hiệu lực ngoài quyền |
| AM-03 | Cùng tenant nhưng không có quan hệ được yêu cầu | Từ chối theo phạm vi đối tượng |
| AM-04 | REQUESTER đồng thời là APPROVER, tự duyệt | Điều kiện tách nhiệm vụ vẫn có hiệu lực |
| AM-05 | Số tiền bằng và vượt hạn mức | Biên được thực thi đúng theo tiền tệ |
| AM-06 | Payload chèn tenant, trạng thái hoặc người duyệt | Không thay đổi trường do server quản lý |
| AM-07 | Row version cũ hoặc nội dung đổi đồng thời | Không ghi phê duyệt sai nội dung |
| AM-08 | Đúng vai trò nhưng trạng thái không hợp lệ | Không bỏ qua state machine |
| AM-09 | Chuyển đổi vai trò hoặc đổi tài khoản liên kết | Không né điều kiện danh tính theo chính sách |
| AM-10 | API chính từ chối nhưng dùng batch, worker hoặc đường quản trị | Cùng giới hạn nghiệp vụ vẫn được giữ |
| AM-11 | Replay cùng thao tác hoặc khác nội dung | Không thêm hiệu lực, không lộ kết quả cũ ngoài quyền |
| AM-12 | Thu hồi quyền giữa các bước | Kết quả khớp chính sách thời điểm đã công bố |
| AM-13 | Lỗi nguồn quyền hoặc cache quá tuổi | Không mặc định cho phép |
| AM-14 | Nhiều yêu cầu hợp lệ cạnh tranh | Bất biến tổng hợp và transaction vẫn đúng |
| AM-15 | Đọc qua danh sách, tìm kiếm, export hoặc download | Đúng phạm vi hàng và trường, không chỉ endpoint chi tiết |

Một đặc tả cho AM-04:

```text
fixture:
    principal U has REQUESTER and APPROVER capabilities
    U created refund F in tenant A
    F is PENDING_APPROVAL and within U's approval limit
    all other approval preconditions are satisfied
    another principal V has a valid approval assignment for F

attempt:
    submit approval of F as U, with the current row version

assert:
    result matches the documented denial contract
    F remains PENDING_APPROVAL
    no new approval or execution event was committed for this attempt
    the denial evidence identifies R_08 and the separation condition
    no private data outside U's read scope is returned

positive control:
    submit approval as V using a valid current version
    exactly the allowed approval effect is committed
```

Đây là giả mã cho môi trường kiểm thử, không phải báo cáo đã chạy test. Dữ liệu kỳ vọng đến từ fixture độc lập; không gọi lại chính hàm production có thể sai để quyết định đáp án.

Đọc hiệu lực đã commit bằng ngữ cảnh phù hợp. Kiểm tra mã lỗi là chưa đủ nếu đối tượng đã bị sửa trước khi lỗi được trả. Với worker hoặc dịch vụ ngoài, phải chờ điều kiện kết thúc có thời hạn và kiểm tra cả hiệu lực downstream liên quan.

## 13. Quyền cấp quyền, thay đổi quan hệ và ngoại lệ

Ma trận dễ bị vô hiệu nếu người dùng không có quyền duyệt nhưng có thể tự cấp APPROVER, tăng hạn mức hoặc sửa người tạo của yêu cầu.

Cần đưa các hành động làm thay đổi điều kiện quyền vào phạm vi tài liệu:

| Hành động nhạy cảm | Rủi ro nếu không mô tả | Điều cần ghi |
| --- | --- | --- |
| Cấp hoặc thu hồi vai trò | Tự nâng quyền qua giao diện quản trị | Ai cấp, cho ai, loại vai trò và thời điểm hiệu lực |
| Thay đổi hạn mức | Né giới hạn duyệt mà không đổi vai trò | Người có quyền thay đổi, đơn vị, tiền tệ và lịch sử |
| Phân công hồ sơ | Tự tạo quan hệ đủ để đọc hoặc duyệt | Quyền phân công, phạm vi và điều kiện tách nhiệm vụ |
| Chuyển chủ sở hữu | Dùng chuyển quyền để né kiểm soát trên đối tượng | Điều kiện trước và sau, ảnh hưởng tới quyền cũ |
| Di chuyển tenant | Đưa tài nguyên sang phạm vi có quyền rộng hơn | Quy trình riêng, ràng buộc dữ liệu và quyết định liên quan |
| Đại diện hoặc ủy quyền | Service hoặc người khác hành động vượt ý chí được cấp | Chủ thể gốc, phạm vi, thời hạn và khả năng thu hồi |
| Tạo ngoại lệ | Biến đường khẩn cấp thành quyền thường trực | Người cấp, lý do, phạm vi, thời hạn và bằng chứng |

Trong mẫu, R-12 chỉ quản lý thành viên cơ bản. Nó không bao gồm cấp vai trò tài chính, đổi hạn mức, sửa quan hệ của yêu cầu để tự duyệt hoặc di chuyển tài nguyên giữa tenant.

Ngoại lệ cần hành động được định danh, không phải bỏ qua toàn bộ authorization. Nếu cho phép thao tác khẩn cấp, ghi rõ giới hạn đối tượng, hiệu lực, thời gian và yêu cầu rà soát. Một cờ emergency do client tự đặt không phải căn cứ cho phép.

Nếu người vận hành dùng công cụ sửa dữ liệu, cần phân biệt sửa chữa có cấp quyền với hành động nghiệp vụ thông thường. Sửa trạng thái trong database có thể tạo hoặc che hiệu lực; tài liệu phải nói đường sửa chữa được kiểm soát thế nào và bất biến nào vẫn phải giữ.

## 14. Ghi quyết định và duy trì khả năng truy nguyên

### 14.1. Từ rule ID tới bằng chứng

Mỗi quy tắc nên nối được tới yêu cầu nghiệp vụ, điểm thực thi, tập kiểm thử và phiên bản triển khai.

| Liên kết | Ví dụ minh họa |
| --- | --- |
| Yêu cầu | Người tạo không được tự duyệt yêu cầu hoàn |
| Rule ID | R-08, policy refund-authz-P3 |
| Điểm thực thi | Lệnh duyệt tại API và đường quản trị tương ứng |
| Dữ liệu tin cậy | Chủ thể chuẩn hóa, người tạo, phân công, trạng thái và phiên bản |
| Kiểm thử | AM-01, AM-04, AM-07 và các ca liên quan |
| Bằng chứng quyết định | Cho phép hoặc từ chối, rule version và đối tượng |
| Bằng chứng hiệu lực | Phê duyệt đã commit hoặc xác nhận không tạo hiệu lực trái phép |

Các mã là ví dụ, không phải tham chiếu tới code hoặc test đã tồn tại trong một repository cụ thể. Khi dùng thật, liên kết phải mở được và đại diện đúng phiên bản.

### 14.2. Một bản ghi quyết định minh họa

```json
{
  "decisionId": "decision-example-81",
  "policyId": "refund-authz",
  "policyVersion": "P3",
  "ruleId": "R-08",
  "subjectRef": "synthetic-principal-U",
  "action": "refund.approve",
  "resourceRef": "synthetic-refund-F",
  "verifiedTenantRef": "synthetic-tenant-A",
  "resourceRowVersion": 24,
  "contentRevision": 7,
  "outcome": "DENY_AUTHORIZATION",
  "internalReason": "CREATOR_CANNOT_APPROVE",
  "correlationRef": "attempt-example-81"
}
```

Đây là dữ liệu tổng hợp. Bản ghi cho biết hệ thống đã ghi một quyết định; nó không tự chứng minh quyết định đó đúng hoặc không có hiệu lực khác xảy ra sau đó. Khi kiểm tra, cần nối tới dữ liệu có thẩm quyền và hiệu lực thực tế.

Lý do nội bộ có thể chi tiết hơn lỗi trả cho người gọi. Không công khai quyền, người tạo hoặc trạng thái của tài nguyên mà người gọi không được biết.

### 14.3. Bảo vệ tài liệu và dấu vết

Không đưa token, khóa ký, dữ liệu thanh toán đầy đủ hoặc payload riêng tư vào ma trận và log. Dùng ID thay thế hoặc tham chiếu có kiểm soát truy cập khi thích hợp; ID thay thế vẫn có thể liên kết được với một người và cần bảo vệ theo mô hình dữ liệu.

Ghi nhận cả quyết định và kết quả ở các mốc phù hợp. “Đã cho phép” không có nghĩa transaction đã commit; “đã gọi nhà cung cấp” không có nghĩa hiệu lực ngoài đã thành công.

Một lần từ chối có thể cần dấu vết điều tra dù transaction nghiệp vụ không tạo thay đổi. Cơ chế ghi dấu vết đó phải được thiết kế riêng, không suy ra từ một dòng log đặt trong transaction đã rollback.

Thông tin ma trận có thể cần hai mức trình bày: hợp đồng cho bên tích hợp và chi tiết nội bộ cho triển khai, kiểm thử, vận hành. Tập nội dung được công bố phải đủ để dùng đúng API nhưng không làm lộ dữ liệu hoặc căn cứ ngoài quyền.

## 15. Phiên bản, thay đổi và triển khai chính sách

Tài liệu cần có chủ sở hữu, phiên bản, trạng thái quyết định và phạm vi môi trường. Phân biệt bản nháp đang thảo luận với chính sách đã được phê duyệt và phiên bản thực sự có hiệu lực.

Các thay đổi cần xem lại ma trận gồm:

- Thêm vai trò, loại tài nguyên, hành động hoặc trường nhạy cảm.
- Đổi state machine, hạn mức hoặc điều kiện phê duyệt.
- Thêm batch, export, download, worker hoặc tích hợp.
- Đổi nguồn danh tính, phân công, cache quyền hoặc cơ chế ủy quyền.
- Thêm quyền quản trị, đường sửa chữa hoặc ngoại lệ.
- Đổi định danh thao tác và cơ chế trả kết quả idempotent.

Một thay đổi quyền không chỉ là sửa một ô. Cần xác định tác động tới dữ liệu cũ, phê duyệt đã cấp, job đang chờ, token còn hiệu lực, kết quả đã tạo và công cụ vận hành.

Ví dụ, khi siết quy tắc tự duyệt, cần quyết định cách xử lý yêu cầu đã duyệt nhưng chưa thực thi theo quy trình thay đổi. Không để worker cũ và worker mới tự diễn giải khác nhau mà không có hợp đồng chuyển tiếp.

Khi dùng nhiều phiên bản song song, nêu nơi chọn phiên bản và điều kiện tương thích. Người gọi không được tùy chọn một policy version cũ để lấy quyền rộng hơn chỉ bằng cách gửi trường trong request.

Kế hoạch rollback cũng cần xét quyền. Quay về code cũ có thể mở lại đường vượt quyền hoặc diễn giải sai trạng thái do phiên bản mới tạo. Tài liệu và kiểm thử chuyển đổi phải phản ánh rủi ro thực tế đó.

Sau triển khai, đối chiếu phiên bản tài liệu với policy và cấu hình đang chạy. Test của bản code mới không chứng minh mọi instance đã dùng cùng cấu hình hoặc đường quản trị đã được cập nhật.

## 16. Mẫu tài liệu có thể dùng lại

Một mẫu tối thiểu cho từng hành động:

```text
Action ID and business meaning:
Resource types and related objects:
Eligible subject types and capabilities:
Trusted identity and attribute sources:
Tenant and relationship constraints:
Readable fields:
Writable fields and server-managed fields:
Allowed source states and transitions:
Business preconditions and aggregate invariants:
Mandatory exclusions and conflict resolution:
Approval content binding and validity:
Evaluation points across synchronous and asynchronous stages:
Concurrency, transaction and external-boundary assumptions:
Idempotency scope and result-access policy:
Outcomes for deny, conflict, missing data and dependency failure:
Administrative, delegation and emergency paths:
Decision evidence and committed-effect evidence:
Positive, negative, boundary and concurrent test references:
Policy owner, version, deployment scope and change conditions:
```

Mẫu là khung hỏi để tạo một hợp đồng đầy đủ. Không cần điền dài ở mọi mục nếu hành động đơn giản, nhưng mục không áp dụng phải được xác nhận có lý do. Không dùng “theo mặc định của hệ thống” khi chưa có nguồn quy tắc được định danh.

Với module lớn, có thể tách ma trận khả năng, bảng quy tắc, danh mục trường, state machine và bản đồ kênh. Các phần cần dùng cùng action ID và rule ID để tránh một hành động có nhiều nghĩa khác nhau.

Tài liệu ngắn vẫn có thể tốt nếu các điều kiện được dẫn tới nguồn rõ ràng và còn đúng phiên bản. Một ma trận rất lớn nhưng đầy ô “có” không giúp người triển khai biết phải kiểm tra object ID hay revision nào.

## 17. Rà soát ma trận bằng tình huống và sai lầm thường gặp

Một buổi rà soát có thể chọn một thao tác cụ thể rồi lần lượt thay đổi chủ thể, tài nguyên, trường, trạng thái và lịch thực thi. Với mỗi thay đổi, yêu cầu người tham gia chỉ ra quy tắc và bằng chứng cho kết quả.

Ví dụ, bắt đầu từ R-08 hợp lệ, sau đó đổi lần lượt sang yêu cầu của chính người duyệt, hồ sơ khác, tenant khác, số tiền vượt hạn mức và nội dung vừa thay đổi. Nếu không thể xác định kết quả từ tài liệu, đó là khoảng trống cần giải quyết trước khi tự triển khai giả định.

Tiếp tục kiểm tra cùng thao tác qua API khác, batch, worker và công cụ vận hành. Rà soát quyền cấp quyền để biết người không đủ quyền có thể tự tạo điều kiện cho mình hay không.

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ ghi vai trò nhân với endpoint | Bỏ sót quyền theo đối tượng và hiệu lực thật | Dùng hành động nghiệp vụ, tài nguyên và điều kiện |
| Ô “admin: tất cả” | Tạo quyền không có giới hạn hoặc căn cứ | Liệt kê hành động quản trị và ngoại lệ cụ thể |
| Cùng tenant thì cho phép | Bỏ qua chủ sở hữu, phân công hoặc ủy quyền | Ghi quan hệ bắt buộc theo đối tượng |
| Quyền update bao gồm mọi trường | Có thể sửa trạng thái, người tạo hoặc phê duyệt | Tách tập trường và lệnh nghiệp vụ |
| Nhiều vai trò tự cộng thành quyền tối cao | Né tách nhiệm vụ | Ghi điều kiện cấm và cách kết hợp quyền |
| Chỉ kiểm tra lúc mở giao diện | API và worker có thể tạo hiệu lực khác | Ánh xạ mọi kênh tới quy tắc |
| Phê duyệt không gắn nội dung | Sửa số tiền hoặc người thụ hưởng sau duyệt | Ràng buộc content revision và trường có ý nghĩa |
| Dùng một revision không rõ nghĩa | Hoặc bỏ lọt cạnh tranh, hoặc làm phê duyệt luôn sai | Phân biệt content revision và row version |
| Dùng idempotency key như bằng chứng quyền | Lộ kết quả cũ hoặc bỏ kiểm tra truy cập | Ràng buộc phạm vi và quyền đọc kết quả |
| Không mô tả lỗi nguồn quyền | Dễ cho phép ngoài ý muốn khi phụ thuộc lỗi | Quy định kết quả chưa xác định và phục hồi |
| Ma trận không có chủ sở hữu hoặc phiên bản | Tài liệu khác hành vi thực tế | Quản lý thay đổi cùng code, policy và cấu hình |

Không sửa tài liệu để hợp thức hóa mọi hành vi production hiện tại. Nếu hành vi trái bất biến đã thống nhất, cần ghi nhận khoảng cách và sửa kiểm soát theo quy trình thích hợp. Nếu nghiệp vụ thật sự thay đổi, cập nhật có chủ đích cùng các tác động liên quan.

## 18. Danh sách kiểm tra hoàn thiện

- Hành động được định nghĩa theo hiệu lực nghiệp vụ, không chỉ tên HTTP hoặc màn hình.
- Mỗi hành động xác định tài nguyên, đối tượng liên quan và nguồn dữ liệu tin cậy.
- Vai trò chỉ mở khả năng xét quyền; phạm vi tenant và quan hệ vẫn được kiểm tra.
- Có tập trường đọc, tập trường ghi và thuộc tính do server quản lý.
- Có trạng thái nguồn, chuyển đổi, tiền điều kiện và bất biến tổng hợp.
- Điều kiện tách nhiệm vụ, hạn mức và cách kết hợp nhiều vai trò được ghi rõ.
- Phê duyệt gắn với nội dung cụ thể và có điều kiện hiệu lực được định nghĩa.
- Content revision và row version có ý nghĩa riêng trong từng bước.
- API, danh sách, batch, worker, export, download và đường quản trị có ánh xạ phù hợp.
- Thời điểm đánh giá, cache và cửa sổ thu hồi quyền được công bố đúng khả năng thực tế.
- Cạnh tranh, transaction và ranh giới dịch vụ ngoài không bị mô tả quá mức bảo đảm.
- Retry và idempotency không tạo đường bỏ qua quyền hoặc thêm hiệu lực.
- Quyền cấp quyền, thay đổi quan hệ và ngoại lệ không bị để ngoài mô hình.
- Có ca hợp lệ, vượt quyền, biên, lỗi phụ thuộc và cạnh tranh từ từng quy tắc.
- Quyết định và hiệu lực truy được tới đúng phiên bản, môi trường và bằng chứng.
- Có người sở hữu, điều kiện cập nhật và cách xử lý công việc trong giai đoạn chuyển đổi.

Ma trận phân quyền hữu ích khi người phát triển, người kiểm thử và người vận hành có thể đi từ một thao tác cụ thể tới cùng một kết luận có căn cứ. Nó cần làm rõ giới hạn quyền và các bất biến phải giữ, đủ chi tiết để phát hiện đường đi vòng quanh kiểm soát thay vì chỉ liệt kê ai có vai trò nào.
