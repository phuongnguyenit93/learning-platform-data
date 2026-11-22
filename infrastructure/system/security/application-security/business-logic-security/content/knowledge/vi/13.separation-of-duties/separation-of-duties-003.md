# Creator approver separation: tách người tạo khỏi người phê duyệt

## 1. Một người không được tự xác nhận công việc của chính mình

An tạo một đề nghị chi trả, sau đó dùng quyền `PAYMENT_APPROVER` để duyệt chính đề nghị đó. API kiểm tra đúng role, hồ sơ đang ở trạng thái chờ duyệt và số tiền trong hạn mức nên chấp nhận.

Các kiểm tra riêng lẻ đều có vẻ hợp lý, nhưng hệ thống đã bỏ mất một bất biến: **người tạo đề nghị không được là người phê duyệt đề nghị đó**.

**Creator approver separation** là việc tách chủ thể tạo ra một đề nghị hoặc căn cứ nghiệp vụ khỏi chủ thể độc lập chấp nhận đề nghị đó. Cách tổ chức này thường được gọi là maker–checker: một bên lập, một bên kiểm tra và quyết định.

Mục đích là giảm khả năng một người tự tạo điều kiện có lợi rồi tự thông qua, chẳng hạn tự duyệt khoản chi, thay thông tin người nhận rồi duyệt thay đổi, hoặc tạo yêu cầu cấp quyền và tự cấp cho mình.

Để bảo vệ logic nghiệp vụ, không thể chỉ ẩn nút duyệt trên giao diện hoặc so sánh hai chuỗi tên tài khoản. Phải xác định đúng người tạo theo nghĩa nghiệp vụ, đúng người đang quyết định và đúng phiên bản hồ sơ được duyệt; sau đó giữ quy tắc này ở mọi đường thực thi.

Sau bài này, bạn có thể:

- Phân biệt phân vai trò tĩnh với kiểm tra không tự duyệt trên từng hồ sơ.
- Xác định người tạo trong các luồng tạo hộ, ủy quyền, import và tự động hóa.
- Thiết kế dữ liệu danh tính và nguồn gốc để tránh lách bằng tài khoản phụ hoặc đổi chủ hồ sơ.
- Thực thi kiểm tra độc lập trong transaction và khi có nhiều yêu cầu đồng thời.
- Kiểm thử các đường vòng thường gặp của quy tắc maker–checker.

## 2. Có role duyệt chưa đủ để được duyệt mọi hồ sơ

Một tổ chức có thể cho An vừa tạo đề nghị vừa duyệt đề nghị của đồng nghiệp. Điều bị cấm là An duyệt hồ sơ do chính An tạo hoặc chịu trách nhiệm lập theo chính sách.

Đây là sự khác biệt giữa hai dạng phân tách nhiệm vụ:

| Dạng | Quy tắc minh họa | Hệ quả |
|---|---|---|
| Phân tách tĩnh | Không một danh tính nào được đồng thời giữ role tạo và role duyệt | Hạn chế ngay khi cấp quyền, có thể phù hợp với tổ chức chuyên trách |
| Phân tách động | Một người có thể giữ cả hai role nhưng không được duyệt hồ sơ của chính mình | Cần kiểm tra quan hệ với từng hồ sơ tại thời điểm quyết định |

Phân tách tĩnh không tự giải quyết mọi đường vòng nếu hệ thống cho một người dùng nhiều tài khoản không được liên kết. Phân tách động cũng không thể chỉ dựa vào role vì hai người có cùng tập role vẫn có quan hệ khác nhau với từng đề nghị.

Một quyết định duyệt mới cần đồng thời thỏa mãn:

```text
được xác thực
AND có quyền duyệt hiện hành
AND hồ sơ thuộc phạm vi được phép
AND người duyệt độc lập với bên lập theo chính sách
AND trạng thái, phiên bản và các điều kiện nghiệp vụ phù hợp
```

Quy tắc không tự duyệt là một điều kiện bắt buộc trong quyết định phân quyền theo đối tượng. Nó không thay thế kiểm tra tenant, phòng ban, hạn mức hoặc state machine.

### 2.1. Tách rõ các vai trò nghiệp vụ

Các khái niệm sau có thể trùng người nhưng không đồng nghĩa:

- **Người thao tác tạo:** tài khoản hoặc service identity thực hiện lệnh tạo.
- **Người khởi xướng nghiệp vụ:** người đưa ra yêu cầu mà lệnh tạo đại diện.
- **Người đứng tên hoặc chủ hồ sơ:** chủ thể được hồ sơ phục vụ hoặc đang được giao quản lý.
- **Người sửa căn cứ:** người thay dữ liệu có thể ảnh hưởng quyết định, như số tiền hoặc người nhận.
- **Người phê duyệt:** người thực sự ra quyết định chấp nhận.

Ví dụ, trợ lý nhập hồ sơ thay An, còn đề nghị thuộc ngân sách của phòng B. Không thể chọn một trường `ownerId` rồi mặc định nó thể hiện đầy đủ mọi vai trò trên.

Chính sách phải nói rõ những chủ thể nào bị cấm duyệt. Với một số quy trình, chỉ người lập bị loại; với quy trình khác, cả người khởi xướng và người sửa căn cứ trọng yếu cũng bị loại. Không mở rộng hoặc thu hẹp tập này một cách ngầm định trong code.

## 3. Định nghĩa bất biến trước khi chọn cách triển khai

Giả sử một quy trình chi trả nội bộ chọn chính sách:

1. Người khởi xướng, người thao tác lập hồ sơ thay người khác và người sửa căn cứ trọng yếu của phiên bản đang duyệt đều không được duyệt phiên bản đó.
2. Người duyệt phải có quyền và hạn mức phù hợp trong đúng tenant/phạm vi.
3. Nếu quyết định được thực hiện qua ủy quyền, phải kiểm tra cả người thao tác thực tế và danh tính được đại diện theo quy tắc chống lách đã chọn.
4. Đổi chủ hồ sơ không xóa lịch sử người lập.
5. Mọi quyết định gắn với đúng vòng duyệt và gói căn cứ nghiệp vụ.

Đây là một chính sách minh họa có chủ ý. Một sản phẩm khác có thể chọn tập người bị loại khác, nhưng cần định nghĩa cùng mức rõ ràng.

Có thể mô hình hóa:

```text
M(basis) = tập danh tính bị loại vì tham gia lập căn cứ đó
R(command) = tập danh tính phải xét của bên thực hiện quyết định

độc lập ⇔ giao của M(basis) và R(command) là rỗng
```

Các tập được dựng từ dữ liệu có thẩm quyền, không lấy trực tiếp từ danh sách ID do client khai.

### 3.1. Vì sao không chỉ dùng creatorId != approverId?

Điều kiện đó hữu ích trong mô hình rất đơn giản, nơi mỗi người chỉ có một tài khoản, không tạo hộ, không ủy quyền và creator được ghi đúng. Khi các giả định này không còn đúng, hai ID khác nhau có thể vẫn đại diện cùng một người.

Ví dụ:

| Đường vòng | So sánh tài khoản đơn thuần bỏ sót điều gì? |
|---|---|
| An dùng tài khoản thường để tạo, tài khoản quản trị để duyệt | Hai tài khoản cùng một danh tính người |
| Service tạo hộ An | `createdBy` là service nhưng người khởi xướng là An |
| An chuyển owner sang Bình rồi duyệt | Owner hiện tại không phải lịch sử người lập |
| Người lập dùng ngữ cảnh đại diện để duyệt | Danh tính thực hiện bị che sau danh tính được đại diện |
| An sửa tài khoản nhận tiền trên hồ sơ của Bình rồi duyệt | Người tạo ban đầu không thể hiện người làm thay đổi căn cứ hiện tại |
| Batch duyệt nhiều hồ sơ chỉ kiểm tra một hồ sơ đầu tiên | Một phần batch có thể chứa hồ sơ của chính người gọi |

Điều cần bảo vệ là tính độc lập theo nghĩa nghiệp vụ, không phải sự khác nhau hình thức của hai giá trị trong request.

### 3.2. Không tự duyệt không đồng nghĩa chống được mọi gian lận

Hai người có thể thông đồng. Một người có thể dùng tài khoản của người khác nếu hệ thống xác thực hoặc quản lý tài khoản yếu. Quy tắc maker–checker giảm một nhóm rủi ro, không tự chứng minh nội dung đúng hoặc người duyệt đã kiểm tra kỹ.

Nó cần được kết hợp với bằng chứng nghiệp vụ, kiểm soát danh tính, hạn mức, kiểm tra bất thường và audit phù hợp. Không nên dùng việc “đã có hai tài khoản” làm bảo đảm tuyệt đối về tính độc lập.

## 4. Mô hình danh tính và nguồn gốc hồ sơ

### 4.1. Phân biệt tài khoản với danh tính người

Một mô hình có thể quản lý các lớp sau:

| Khái niệm | Ý nghĩa |
|---|---|
| `principalId` | Tài khoản hoặc service identity được cơ chế xác thực nhận diện |
| `personIdentityId` | Danh tính người được hệ thống tổ chức liên kết với một hay nhiều tài khoản |
| `tenantMembershipId` | Quan hệ tham gia tenant, cùng trạng thái và phạm vi hiện hành |
| `delegationId` | Căn cứ cho phép hành động thay chủ thể khác trong phạm vi xác định |
| `originContextId` | Tham chiếu nguồn khởi xướng đã được máy chủ xác minh |

Không phải hệ thống nào cũng có định danh người ngoài tài khoản. Nếu chưa có khả năng liên kết đáng tin, cần thừa nhận giới hạn đó thay vì tuyên bố đã chặn việc tự duyệt qua mọi tài khoản phụ.

Không dùng email, tên hiển thị, IP hoặc mã do người dùng tự nhập làm định danh người độc lập duy nhất. Các thuộc tính này có thể đổi, dùng chung hoặc bị khai giả.

Nếu policy yêu cầu xác định danh tính người mà không phân giải được, cần từ chối hoặc chuyển sang quy trình xử lý được kiểm soát. Không âm thầm fallback sang “account ID khác nhau là đủ”.

### 4.2. Dữ liệu nguồn gốc nên giữ những gì?

Một hồ sơ có thể cần:

```text
tenantId
requestId
creationPrincipalId
originalInitiatorIdentityId
creationMode
originContextId
currentOwnerId
currentBasisPackageId
currentApprovalRoundId
version
```

Trong đó, các trường nguồn gốc đã được xác nhận không được sửa như thuộc tính thông thường. `currentOwnerId` có thể thay đổi qua lệnh được phép, nhưng không được dùng thay cho `originalInitiatorIdentityId`.

Đối với người sửa căn cứ, có thể có một sổ sự kiện hoặc tập đóng góp gắn với phiên bản:

```text
requestId + basisPackageId + identityId + contributionType
```

Ví dụ `contributionType` là khởi xướng, nhập thay hoặc sửa thông tin người nhận. Hệ thống dựng tập người bị loại theo loại đóng góp mà policy quy định.

### 4.3. Dữ liệu danh tính thay đổi theo thời gian

Một nhân viên có thể được cấp tài khoản mới, hoặc hai tài khoản được phát hiện thuộc cùng một người. Không được làm mất liên kết với lịch sử người lập chỉ vì tài khoản cũ đã bị khóa.

Có thể giữ định danh người ổn định và quan hệ tài khoản, hoặc cơ chế ánh xạ danh tính tương đương có lịch sử. Khi gộp/đổi ánh xạ, cần hiểu ảnh hưởng tới các vòng duyệt đang mở và quy tắc nhận diện hiện tại.

Không viết lại audit cũ để giả vờ rằng hệ thống đã biết một liên kết trước khi nó được xác lập. Nếu phát hiện một approval trước đây vi phạm vì thông tin mới, xử lý bằng dấu vết đánh giá hoặc khắc phục riêng.

## 5. Kiểm tra độc lập theo hồ sơ, căn cứ và hành động

Ví dụ An có quyền duyệt trong phòng kế toán nhưng đã lập đề nghị `P-100`. Bình có cùng quyền và đủ hạn mức. Một người khác tên Chi có quyền ở tenant khác.

| Người thực hiện | Quan hệ với `P-100` | Kết quả |
|---|---|---|
| An | Người lập, đủ role và hạn mức | Từ chối vì tự duyệt |
| Tài khoản quản trị của An | Cùng danh tính người với người lập | Từ chối theo cùng quy tắc |
| Bình | Độc lập, đúng phạm vi và đủ quyền | Có thể duyệt nếu các điều kiện khác đạt |
| Chi | Độc lập nhưng ngoài tenant | Từ chối vì ngoài phạm vi |
| Service không được cấp quyền duyệt | Không phải người lập | Từ chối vì thiếu quyền; độc lập không tự cấp quyền |

### 5.1. Quy tắc cần được gọi từ mọi đường ghi

Không tự duyệt phải được áp dụng ở API web, ứng dụng di động, batch, import quyết định, công cụ quản trị và worker có thể ghi approval.

Một endpoint đã bảo vệ đúng không có ý nghĩa nếu endpoint tổng quát khác cho phép:

```http
PATCH /payment-requests/P-100
Content-Type: application/json

{
  "state": "APPROVED",
  "approvedBy": "another-user",
  "createdBy": "someone-else"
}
```

Không bind các trường đặc quyền này trực tiếp vào entity rồi lưu. Chuyển trạng thái duyệt phải đi qua lệnh nghiệp vụ và policy tương ứng.

### 5.2. Kiểm tra trước khi tiết lộ chi tiết

Với người ngoài phạm vi, cần từ chối mà không tiết lộ người tạo, số tiền hay cấu trúc nội bộ của hồ sơ. Đối với người được phép xem nhưng không được tự duyệt, ứng dụng có thể giải thích quy tắc phù hợp.

Mã lỗi như `SELF_APPROVAL_NOT_ALLOWED` hữu ích cho người dùng được phép và audit. Nó không nên trở thành một cách dò xem một ID bất kỳ thuộc về ai.

## 6. Tạo hộ, ủy quyền và tự động hóa

### 6.1. Trợ lý hoặc API tạo hộ

Khi trợ lý tạo đề nghị thay An, hệ thống cần lưu đúng cả người thao tác và người khởi xướng/được đại diện theo hợp đồng nghiệp vụ.

Client không được tùy ý chọn `initiatorId` chỉ để chuyển trách nhiệm sang người khác. Lệnh tạo hộ phải có quyền đại diện, phạm vi và dữ liệu nguồn được xác minh.

Trong chính sách minh họa của bài, cả trợ lý nhập thay lẫn An đều thuộc tập người không được duyệt căn cứ đó. Nếu tổ chức chọn một quy tắc khác, cần ghi rõ và kiểm thử thay vì suy ra từ tên trường.

### 6.2. Ủy quyền duyệt không xóa quan hệ với người lập

Ủy quyền phải trả lời được ai ủy quyền, ai thao tác, được làm gì, trên phạm vi nào, trong thời hạn và hạn mức nào.

Không được cho người lập dùng một ngữ cảnh đại diện để che danh tính thao tác thật. Cũng không nên cho một bên đã bị loại truyền quyền qua chuỗi ủy quyền nhằm vượt chính điều kiện độc lập của hồ sơ.

Quy tắc chống lách có thể xét cả người thực hiện thực tế và người được đại diện, theo policy. Hệ thống phải dựng các danh tính này từ căn cứ ủy quyền được xác thực, không tin một trường `onBehalfOf` trong body.

Ủy quyền chuyển khả năng thực hiện một hành động trong phạm vi được cho phép; nó không mặc định được chuyển quyền bỏ qua bất biến không tự duyệt.

### 6.3. Service tạo hồ sơ theo yêu cầu người dùng

Một kiến trúc nhiều service có thể ghi `creationPrincipalId = payment-service`. Nếu chỉ so sánh người duyệt với service này, mọi người dùng đều trông có vẻ độc lập.

Cần truyền và lưu ngữ cảnh khởi xướng qua cơ chế nội bộ đáng tin, có ràng buộc nguồn, mục đích và phạm vi. Header như `X-User-Id` từ nơi không được xác thực không đủ làm bằng chứng.

Ví dụ cần phân biệt:

```text
service thao tác: payment-service
người khởi xướng đã xác minh: An
hồ sơ: P-100

An duyệt P-100 → vẫn là tự duyệt theo chính sách.
```

Một service identity không được làm mất trách nhiệm của người yêu cầu chỉ vì nó là bên trực tiếp ghi cơ sở dữ liệu.

### 6.4. Job tạo hoàn toàn tự động

Nếu job tự tạo hồ sơ theo lịch mà không có một người khởi xướng cụ thể, không nên bịa một `personIdentityId` hoặc coi việc “không có creator là người” đồng nghĩa mọi cách duyệt đều hợp lệ.

Cần mô hình riêng cho nguồn tự động: quy tắc tạo, chủ thể chịu trách nhiệm, phạm vi và yêu cầu kiểm tra độc lập. Hai credential của cùng một workload không tự trở thành hai người độc lập.

Nếu nghiệp vụ cho phép tự động chấp nhận một nhóm rủi ro thấp, hãy ghi đó là quyết định tự động theo policy rõ ràng. Không ghi giả thành một lượt duyệt độc lập của con người để đáp ứng quorum vốn yêu cầu người duyệt.

### 6.5. Chế độ hỗ trợ hoặc impersonation

Khi nhân viên hỗ trợ thao tác trong ngữ cảnh người dùng khác, phải giữ được danh tính thao tác thật. Việc hiển thị giao diện “đang là người dùng B” không làm nhân viên hỗ trợ biến thành B về mặt trách nhiệm.

Quy trình nhạy cảm có thể cấm duyệt trong chế độ này hoặc yêu cầu kiểm tra rõ các bên và quyền đại diện. Không chỉ dùng danh tính đang hiển thị trên UI để xét tính độc lập.

## 7. Thay chủ, sửa căn cứ và mở vòng duyệt mới

### 7.1. Đổi owner không đổi lịch sử người lập

An tạo hồ sơ, chuyển owner cho Bình rồi quay lại duyệt. Nếu hệ thống kiểm tra `currentOwnerId != actorId`, thao tác sẽ lọt.

Owner hiện tại có thể phục vụ phân công xử lý. Nguồn gốc người lập phục vụ bất biến khác. Khi ownership đổi, cần giữ lịch sử và tiếp tục kiểm tra tập người bị loại theo policy.

Nếu policy còn cấm owner hiện tại duyệt, hãy thêm điều kiện đó một cách rõ ràng. Không dùng nó để thay thế điều kiện về người lập.

### 7.2. Người sửa căn cứ có phải được coi là maker không?

Điều này phải do chính sách quyết định. Ví dụ, người thay số tiền hoặc tài khoản người nhận có thể bị coi là bên lập của căn cứ mới, dù họ không tạo hồ sơ ban đầu.

Không nên cấm mọi người từng thêm bình luận hoặc sửa lỗi trình bày nếu các thao tác đó không thuộc định nghĩa tham gia lập căn cứ. Quy tắc quá rộng có thể tạo cách gây khó cho người khác hoặc làm quy trình không còn ai đủ điều kiện duyệt.

Hãy phân loại các thay đổi trọng yếu và ghi đóng góp từ server. Mọi thao tác thay căn cứ phải tăng revision/version liên quan và cập nhật dữ liệu nguồn gốc trong cùng cơ chế nhất quán.

### 7.3. Approval cũ không tự áp dụng cho căn cứ mới

Giả sử Bình duyệt hồ sơ của An. Sau đó Bình sửa người nhận. Nếu giữ nguyên approval, Bình đang sử dụng quyết định cũ để thông qua nội dung mà chính mình vừa tạo ra.

Một mô hình dễ kiểm soát là đóng băng gói căn cứ, mở vòng mới khi có thay đổi cần duyệt lại và tính tập maker cho gói mới. Quyết định cũ vẫn được giữ trong lịch sử nhưng không được đếm cho nội dung mới khi policy không cho phép kế thừa.

### 7.4. Sao chép và tạo lại hồ sơ

Nếu thao tác clone/import chỉ là cách tiếp tục cùng một nghĩa vụ nghiệp vụ, không được làm mất nguồn khởi xướng chỉ vì có request ID mới. Cần giữ liên kết nguồn phù hợp và áp dụng quy tắc chống lách đã chọn.

Nếu đó là một đề nghị mới thực sự, tập người lập cần phản ánh quá trình mới theo chính sách. Không mặc định mọi người từng xuất hiện ở mọi tài liệu nguồn đều bị cấm duyệt mãi mãi.

Điểm quan trọng là định nghĩa ranh giới nghĩa vụ và nguồn gốc, thay vì để việc đổi ID hoặc đổi tên file quyết định ai được coi là độc lập.

## 8. Thiết kế lệnh và minh họa Java

Một lệnh duyệt nên nhận đầu vào hẹp:

```http
POST /payment-requests/{requestId}/approve
Content-Type: application/json
Idempotency-Key: command-key

{
  "expectedVersion": 12,
  "basisPackageId": "basis-4",
  "note": "Đã đối chiếu căn cứ"
}
```

Người gọi không được tự gán người tạo, người duyệt hoặc tập danh tính để so sánh. Một tham chiếu ủy quyền, nếu API hỗ trợ, chỉ là đầu vào để server xác minh quyền đại diện.

### 8.1. Service xử lý lệnh mới

Đoạn sau minh họa mô hình có một người duyệt độc lập là đủ khi các điều kiện khác đạt. Các dependency là hợp đồng do ứng dụng triển khai; mã không phải một ứng dụng hoàn chỉnh. Nhánh xử lý idempotency đã xác định đây là lệnh mới.

```java
record ApproveCommand(
        long expectedVersion,
        UUID basisPackageId,
        String note) {}

ApprovalReceipt approve(UUID requestId, ApproveCommand command) {
    AuthenticatedActor actor = identity.requireAuthenticatedActor();
    validateInput(command);

    return transactions.required(() -> {
        PaymentRequest request = requests
                .lockByTenantAndId(actor.tenantId(), requestId)
                .orElseThrow(NotFound::new);

        ReviewerContext reviewer = reviewerContexts
                .requireVerifiedCurrentContext(actor);

        approvalPolicy.requireCurrentPermission(reviewer, request);

        if (request.version() != command.expectedVersion()) {
            throw new Conflict("STALE_VERSION");
        }
        if (request.state() != RequestState.IN_REVIEW) {
            throw new Conflict("INVALID_SOURCE_STATE");
        }
        if (!request.basisPackageId().equals(command.basisPackageId())) {
            throw new Conflict("APPROVAL_BASIS_CHANGED");
        }

        MakerSet makers = provenance.requireCompleteMakerSet(
                request.id(), request.basisPackageId());

        separationPolicy.requireIndependent(reviewer, makers);
        businessRules.requireApprovalReady(request);

        decisions.appendUniqueApproval(
                request, reviewer, makers, command.note());

        int changed = requests.markApproved(
                actor.tenantId(), request.id(), request.version(),
                request.basisPackageId(), request.approvalRoundId(),
                reviewer.actualIdentityId());

        if (changed != 1) {
            throw new Conflict("CONCURRENT_MODIFICATION");
        }

        ApprovalReceipt receipt = new ApprovalReceipt(
                request.id(), request.version() + 1, "APPROVED");

        audit.appendApproval(request, reviewer, makers, receipt);
        outbox.appendRequestApproved(request, receipt);
        return receipt;
    });
}
```

Các hợp đồng phải được triển khai đúng nghĩa:

- Ngữ cảnh tenant được xác minh; truy vấn theo tenant và ID không thay thế quyền đối tượng trong cùng tenant.
- `ReviewerContext` giữ danh tính thực tế và các danh tính đại diện cần xét, không lấy từ body chưa kiểm tra.
- `requireCompleteMakerSet` không trả tập rỗng như kết quả thành công khi bị thiếu nguồn gốc hoặc gặp lỗi tải dữ liệu.
- `requireIndependent` so sánh danh tính đã được chuẩn hóa theo mô hình liên kết tài khoản của hệ thống.
- `markApproved` có điều kiện theo trạng thái nguồn, version, basis và vòng duyệt; không chỉ cập nhật theo ID.
- Quyết định, cập nhật, audit thành công và outbox bắt buộc phải cùng transaction nếu muốn nguyên tử như ví dụ.
- Lỗi ở bất kỳ ghi bắt buộc nào dẫn tới rollback theo hợp đồng transaction manager.

Nếu cần nhiều người duyệt, thay việc lập tức đánh dấu đã duyệt bằng ghi phiếu và đánh giá quorum. Mỗi phiếu được tính vẫn phải qua cùng điều kiện độc lập với tập maker.

### 8.2. Policy so sánh danh tính

Phần cốt lõi có thể được biểu diễn như sau:

```java
void requireIndependent(ReviewerContext reviewer, MakerSet makers) {
    if (!reviewer.identityResolved() || !makers.complete()) {
        throw new Forbidden("INDEPENDENCE_NOT_ESTABLISHED");
    }

    Set<IdentityId> reviewerIds = reviewer.identitiesRequiredByPolicy();
    if (reviewerIds.isEmpty()) {
        throw new Forbidden("INDEPENDENCE_NOT_ESTABLISHED");
    }

    boolean overlap = reviewerIds.stream()
            .anyMatch(makers.forbiddenIdentityIds()::contains);

    if (overlap) {
        throw new Forbidden("SELF_APPROVAL_NOT_ALLOWED");
    }
}
```

Hai tập phải cùng dùng một không gian định danh có thẩm quyền. So sánh một bên là account ID, một bên là employee ID có thể luôn cho kết quả “khác nhau” dù cùng người.

Hàm này không tự kiểm tra role, hạn mức hoặc trạng thái. Nó là một phần của chính sách tổng thể, không phải toàn bộ quyền duyệt.

## 9. Transaction, cạnh tranh, idempotency và batch

### 9.1. Bảo vệ nguồn gốc cùng với căn cứ

Một khoảng hở có thể xảy ra:

```text
T1: Đọc tập maker của basis hiện tại, không có Bình.
T2: Bình sửa tài khoản nhận tiền, nhưng đường sửa không đổi version cha.
T1: Bình được ghi nhận duyệt theo tập maker cũ.
```

Để tránh, mọi thao tác sửa căn cứ và ghi đóng góp maker tương ứng phải tham gia cùng giao thức khóa/version. Có thể khóa aggregate cha trong transaction hoặc dùng cập nhật lạc quan với revision bao phủ các thay đổi liên quan.

Khóa một hàng request không tự khóa mọi bảng con hoặc kho danh tính. Cần biết chính xác dữ liệu nào đã được bảo vệ và đường ghi nào tuân thủ cùng quy ước.

### 9.2. Không đánh đồng constraint với toàn bộ bất biến

Ràng buộc duy nhất theo tenant, vòng duyệt và danh tính người duyệt giúp ngăn ghi/đếm trùng. Nó không tự chứng minh người đó khác bên lập.

Một điều kiện hàng đơn giản như `creator_account_id <> approver_account_id` cũng không bao phủ tài khoản phụ, tạo hộ và tập người đóng góp. Dùng constraint cho phần biểu diễn được trong mô hình dữ liệu, kết hợp policy và transaction cho các quan hệ còn lại.

Các trường nguồn gốc cần được bảo vệ ở DTO, domain và quyền ghi dữ liệu thích hợp. Chặn sửa chúng ở một màn hình là chưa đủ nếu đường import vẫn có thể ghi đè.

### 9.3. Quyền và ánh xạ danh tính có thể thay đổi

Đọc authority trong transaction không tự tuần tự hóa với thu hồi quyền. Tương tự, đọc ánh xạ tài khoản–người không tự đóng băng một lần gộp danh tính đang chạy ở hệ thống khác.

Nếu yêu cầu nhất quán rất chặt, các đường thay đổi và quyết định cần cơ chế đồng bộ hoặc phiên bản được kiểm tra đủ mạnh. Nếu chấp nhận độ trễ cache/đồng bộ, phải xác định cam kết đó và kiểm thử trong phạm vi thực tế.

Không tuyên bố chặn tức thời mọi trường hợp tự duyệt khi hệ thống danh tính chỉ cập nhật theo lô mà chưa có kiểm soát bổ sung.

### 9.4. Gửi lại sau khi duyệt thành công

Khi response bị mất, client có thể gửi lại. Cùng một lệnh cần được nhận diện bằng idempotency trong đúng phạm vi, với fingerprint phù hợp.

Nhánh replay không tạo phiếu mới và không thực hiện lại chuyển trạng thái. Nó kiểm tra quyền hiện tại để trả kết quả theo hợp đồng, thay vì đòi trạng thái nguồn vẫn là `IN_REVIEW` như một lệnh mới.

Đổi idempotency key không tạo quyền duyệt hồ sơ của chính mình. Tính duy nhất của quyết định và điều kiện trạng thái vẫn cần ngăn lặp nghiệp vụ.

### 9.5. Duyệt hàng loạt phải xét từng đối tượng

Một batch có thể gồm 99 hồ sơ của đồng nghiệp và một hồ sơ do chính người gọi lập. Kiểm tra role một lần hoặc chỉ kiểm tra hồ sơ đầu tiên sẽ bỏ sót vi phạm.

Mỗi phần tử phải có kiểm tra phạm vi, maker, basis, trạng thái và version tương ứng. API cần chọn rõ toàn bộ thành công hoặc không thành công, hay trả kết quả từng phần; không được im lặng bỏ qua policy ở phần tử khó xử lý.

Nếu trả kết quả từng phần, từng quyết định cần transaction/idempotency phù hợp. Chi tiết lỗi cũng không được làm lộ hồ sơ ngoài quyền.

## 10. Nhiều cấp duyệt và tách người thực thi

### 10.1. Mọi phiếu được tính đều phải hợp lệ

Nếu một hồ sơ cần hai người duyệt, việc người lập tự duyệt một phiếu rồi thêm một người khác không đáp ứng yêu cầu hai người duyệt độc lập với bên lập.

Tập phiếu hợp lệ cần được lọc theo:

```text
đúng hồ sơ, vòng và căn cứ
AND quyền quyết định hợp lệ theo policy
AND độc lập với bên lập
AND không bị thay thế hoặc vô hiệu hóa
AND không đếm trùng danh tính
```

Sau đó mới xét số lượng, vai trò, cấp duyệt và hạn mức. Không dùng `COUNT(approvals)` trên toàn bộ lịch sử làm điều kiện duy nhất.

Nếu các cấp cần những người khác nhau, phải kiểm tra độc lập giữa các cấp. Một người giữ hai role không tự trở thành hai người chỉ vì họ bấm ở hai màn hình.

### 10.2. Người duyệt và người thực thi là hai câu hỏi khác nhau

Tách người tạo với người duyệt không tự yêu cầu ba người khác nhau cho tạo, duyệt và thực thi. Đó là một quy tắc bổ sung nếu rủi ro nghiệp vụ cần.

Ví dụ một ma trận có thể chọn:

| Quan hệ | Quy tắc trong ví dụ |
|---|---|
| Người lập và người duyệt | Bắt buộc độc lập |
| Hai người duyệt khi cần quorum hai người | Bắt buộc khác danh tính |
| Người duyệt và người khởi tạo chi trả | Chỉ bắt buộc khác nếu policy quy định |
| Worker xác nhận kết quả ngoài hệ thống | Quyền hẹp theo operation, không giả làm người duyệt |

Không suy ra quyền thực thi chỉ từ việc đã được duyệt. Lệnh chi trả vẫn cần quyền riêng, căn cứ đã được chấp nhận và kiểm soát chống lặp tác động.

### 10.3. Approval phải còn gắn với nội dung được thực thi

Nếu người tạo có thể sửa số tiền sau khi có người khác duyệt rồi dùng approval cũ để chi, cơ chế tách người vẫn bị vô hiệu về ý nghĩa.

Hành động sau duyệt cần đối chiếu basis đã duyệt với số tiền, loại tiền và người nhận thực tế. Mọi thay đổi cần duyệt lại phải mở lại quy trình theo policy; không chỉ giữ cờ `APPROVED` rồi tin rằng đã có người kiểm tra.

## 11. Quản trị quyền, ngoại lệ và các đường đặc quyền

### 11.1. Người quản trị cũng có quan hệ với hồ sơ

Vai trò quản trị hệ thống không mặc định cho phép tự duyệt. Nếu endpoint admin gọi một hàm bỏ qua separation policy, người có quyền quản trị và quyền lập có thể tự hoàn tất toàn bộ chuỗi.

Cần phân biệt quản trị kỹ thuật với thẩm quyền nghiệp vụ. Công cụ sửa dữ liệu, import quyết định và tác vụ vận hành phải có phạm vi, audit và quy trình phù hợp; không coi chúng là đường vô hình ngoài bất biến.

Nếu mô hình đe dọa bao gồm người có thể sửa trực tiếp cơ sở dữ liệu, kiểm tra trong application service không đủ chống người đó. Cần đánh giá quyền ghi, phân tách trách nhiệm quản trị và các lớp kiểm chứng/giám sát tương ứng, thay vì khẳng định policy ứng dụng bảo vệ được mọi cấp đặc quyền.

### 11.2. Ngoại lệ phải được định nghĩa riêng

Nếu quy tắc không tự duyệt là tuyệt đối, không có `force=true` để bỏ qua.

Nếu tổ chức cho phép một loại ngoại lệ, cần định nghĩa riêng ai được kích hoạt, điều kiện, phạm vi hồ sơ, lý do, thời hạn và cách kiểm tra bổ sung. Ghi rõ đó là quyết định ngoại lệ, không ghi giả rằng đã đáp ứng tính độc lập thông thường.

Rà soát sau sự kiện không tương đương việc có người độc lập ngăn chặn trước khi hành động xảy ra. Nó là kiểm soát bù trong một thiết kế khác, cần được đánh giá theo rủi ro thực tế.

Một nút “duyệt khẩn” do chính người lập có thể tự bật không tạo ra sự phân tách nhiệm vụ.

### 11.3. Thay policy là một hành động nhạy cảm

Nếu người lập có thể tự sửa tập maker, ánh xạ danh tính hoặc policy để hợp thức hóa hồ sơ đang chờ của mình, việc kiểm tra ở endpoint duyệt vẫn có thể bị vượt qua.

Các thay đổi này cần quyền và dấu vết riêng. Khi policy đổi giữa một vòng duyệt, phải xác định cách áp dụng cho hồ sơ đang mở; không âm thầm xóa quan hệ xung đột hoặc tính lại lịch sử theo cách có lợi cho người thay đổi.

### 11.4. Chọn người kiểm tra thực sự có ý nghĩa

Tách tài khoản chỉ là một phần. Người được giao duyệt cần đủ quyền xem căn cứ và đủ khả năng đưa ra quyết định theo trách nhiệm đã giao.

Không tự tạo một tài khoản “checker” dùng chung rồi cho người lập nắm credential. Cũng không coi một bot luôn chấp nhận mọi yêu cầu của maker là sự độc lập của con người.

## 12. Audit và quan sát vi phạm

Một quyết định nên truy vết được:

- Tài khoản thực hiện và danh tính người đã phân giải.
- Danh tính được đại diện và căn cứ ủy quyền nếu có.
- Người khởi xướng, các đóng góp maker được xét và phiên bản tập nguồn gốc.
- Hồ sơ, tenant, basis, vòng duyệt và version trước/sau.
- Phiên bản policy và kết quả kiểm tra độc lập.
- Request/correlation ID và thông tin liên quan đến idempotency.

Audit không cần sao chép token, credential hoặc mọi dữ liệu cá nhân. Ghi các tham chiếu có kiểm soát thường hữu ích hơn lưu nguyên body chứa thông tin nhạy cảm.

Những hành vi đáng theo dõi gồm tự duyệt bị chặn lặp lại, đổi owner ngay trước khi duyệt, nhiều tài khoản cùng một danh tính tham gia một vòng, thiếu nguồn khởi xướng ở các luồng service và các lượt dùng ngoại lệ bất thường.

Các tín hiệu này cần được diễn giải trong ngữ cảnh. Đổi owner có thể là thao tác hợp lệ; nó không tự là bằng chứng gian lận. Tuy nhiên, hệ thống vẫn phải giữ bất biến dù người vận hành chưa kịp xem cảnh báo.

Audit thành công có thể ghi cùng transaction với quyết định. Audit từ chối cần cơ chế phù hợp để không mất khi transaction nghiệp vụ rollback. Không biến lỗi ghi log thành lý do cho phép tự duyệt.

## 13. Kiểm thử các đường vòng tự duyệt

### 13.1. Ma trận tình huống cần có

| Tình huống | Kỳ vọng |
|---|---|
| Người lập có role và đủ hạn mức duyệt chính hồ sơ | Bị từ chối vì không độc lập |
| Tài khoản phụ hoặc tài khoản admin của cùng người lập duyệt | Bị từ chối khi cùng danh tính theo mô hình hệ thống |
| Người khác độc lập nhưng ngoài tenant/phòng ban | Bị từ chối vì ngoài phạm vi |
| Người không có role duyệt nhưng không phải maker | Bị từ chối; độc lập không tự cấp quyền |
| Người lập chuyển owner rồi duyệt | Vẫn bị chặn theo lịch sử maker |
| Body giả `createdBy`, `approvedBy` hoặc `initiatorId` | Không thay đổi nguồn gốc/danh tính để vượt policy |
| Người lập dùng ngữ cảnh đại diện để duyệt | Không che được danh tính thật; xử lý đúng policy ủy quyền |
| Service tạo hộ người dùng rồi chính người dùng đó duyệt | Không mất quan hệ khởi xướng qua service |
| Import không có nguồn gốc bắt buộc | Không mặc định cho phép duyệt do tập maker rỗng |
| Người sửa số tiền/người nhận trọng yếu quay lại duyệt | Bị loại nếu policy coi đóng góp đó là maker của basis |
| Chỉ thêm bình luận không ảnh hưởng căn cứ | Không bị loại ngoài điều policy đã định |
| Hai phiếu cùng một danh tính qua hai role | Không được đếm thành hai người độc lập trái policy |
| Có phiếu của maker trong một quorum nhiều người | Phiếu không được chấp nhận/đếm để đạt quorum |
| Một batch chứa cả hồ sơ của người gọi và của người khác | Kiểm tra từng hồ sơ; kết quả đúng chế độ nguyên tử/từng phần |
| Gửi lại sau khi quyết định đã commit | Không ghi thêm phiếu hoặc thực hiện lại transition |
| Đổi idempotency key rồi gửi lại tự duyệt | Vẫn bị chặn bởi policy nghiệp vụ |
| Sửa căn cứ đồng thời với kiểm tra maker | Không duyệt dựa trên tập maker/basis cũ |
| Liên kết hai tài khoản về cùng danh tính trong lúc chờ | Hành vi đúng cam kết cập nhật danh tính của hệ thống |
| Dùng endpoint admin/import để đặt trạng thái đã duyệt | Không có đường ghi bỏ qua bất biến trái chính sách |
| Sửa người nhận sau approval rồi thực thi | Không dùng quyết định cũ cho căn cứ mới chưa được chấp nhận |

### 13.2. Kiểm tra tác động sau lỗi

Một response `403` chưa chứng minh hồ sơ không bị đổi. Sau khi chặn tự duyệt, kiểm tra không có quyết định có hiệu lực mới, không tăng quorum, không đổi trạng thái và không tạo operation thực thi ngoài ý muốn.

Ngược lại, với người duyệt độc lập hợp lệ, kiểm tra đúng basis/vòng, danh tính lấy từ ngữ cảnh server và các ghi bắt buộc cùng commit. Policy quá rộng làm chặn mọi người cũng là một lỗi cần phát hiện.

### 13.3. Kiểm thử cạnh tranh có điều khiển

Những lịch chạy quan trọng gồm:

1. Đọc maker rồi có sửa căn cứ trước cập nhật quyết định.
2. Hai tài khoản của cùng một người cùng gửi phiếu.
3. Giao dịch chuyển owner chạy đồng thời với duyệt.
4. Lệnh duyệt commit nhưng response bị mất, sau đó client gửi lại.
5. Thu hồi quyền hoặc đổi ánh xạ danh tính trong lúc quyết định đang xử lý.

Kiểm thử nên điều khiển ranh giới đọc/ghi để tạo xung đột cụ thể. Với khóa và constraint, cần kiểm thử phù hợp trên loại cơ sở dữ liệu triển khai; mock repository không chứng minh thứ tự commit thực tế.

### 13.4. Kiểm thử chuỗi thao tác

Có thể tạo chuỗi lệnh như:

```text
create → transferOwner → approve
createOnBehalf → approveAsInitiator
create → submit → editPayee → approveAsEditor
create → submit → approveAsOtherPerson → editAmount → execute
create → cloneSameBusinessIntent → approveThroughAlternateAccount
```

Không phải mọi bước đều phải được phép. Sau từng bước, kiểm tra quan hệ người lập–người duyệt và căn cứ được chấp nhận vẫn đúng. Cách này phát hiện lỗ hổng chỉ xuất hiện khi kết hợp nhiều endpoint thay vì gọi riêng từng API.

## 14. Tự rà soát thiết kế maker–checker

Trước khi coi quy tắc không tự duyệt đã được thực thi, hãy trả lời được:

1. “Người tạo” có nghĩa là tài khoản ghi dữ liệu, người khởi xướng hay những chủ thể nào khác theo policy?
2. Các tài khoản của cùng một người được nhận diện ra sao và hệ thống còn giới hạn nào?
3. Tạo hộ, ủy quyền, service trung gian và impersonation có giữ danh tính thực tế không?
4. Đổi owner, clone hoặc import có thể làm mất nguồn gốc liên quan không?
5. Những sửa đổi nào khiến một người trở thành maker của căn cứ mới?
6. Mọi đường ghi approval có chạy cùng policy và kiểm tra đúng basis/vòng duyệt không?
7. Transaction bảo vệ cả căn cứ và tập maker khỏi thay đổi cạnh tranh như thế nào?
8. Batch, gửi lại lệnh và nhiều cấp duyệt có thể tính nhầm một người thành nhiều người không?
9. Đường quản trị và ngoại lệ có được định nghĩa, giới hạn và truy vết đúng bản chất không?
10. Hành động sau duyệt có thực sự dùng nội dung mà người độc lập đã chấp nhận không?

Tách người tạo khỏi người duyệt nghĩa là giữ được tính độc lập ở cấp danh tính và căn cứ nghiệp vụ, xuyên suốt vòng đời hồ sơ. Quy tắc đó chỉ có giá trị khi không thể bị làm mất bằng cách đổi tài khoản, đổi owner, đi qua service hoặc sửa nội dung sau khi đã có quyết định.
