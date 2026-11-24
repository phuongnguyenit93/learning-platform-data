# Threshold bypass prevention: Ngăn vượt cơ chế phê duyệt theo ngưỡng

## 1. Ngưỡng phê duyệt là ràng buộc nghiệp vụ

Giả sử một hệ thống chi trả có chính sách nội bộ:

- Tổng giá trị đến 100 triệu đồng được cấp L1 phê duyệt.
- Trên 100 triệu đồng cần thẩm quyền L2.
- Từ 500 triệu đồng trở lên cần đồng thời các phê duyệt độc lập theo quy định.

Nếu người dùng có thể sửa số tiền sau khi duyệt, chia nhỏ yêu cầu, tự gửi `approved = true` hoặc gọi thẳng API thực hiện, ngưỡng trên chỉ còn là hướng dẫn giao diện.

**Threshold bypass prevention** là việc bảo đảm mọi đường dẫn đến hành động có tác động nghiệp vụ đều thực thi đầy đủ chính sách ngưỡng, trên đúng nội dung, đúng chủ thể và đúng trạng thái.

Mục tiêu không chỉ là ngăn request có trường `amount` lớn. Cần ngăn việc tạo cùng một tác động bằng chuỗi thao tác khác:

~~~text
Tạo yêu cầu nhỏ
→ lấy phê duyệt thấp
→ sửa nội dung thành yêu cầu lớn
→ dùng phê duyệt cũ để thực hiện
~~~

Hoặc:

~~~text
Chia một nhu cầu lớn thành nhiều yêu cầu nhỏ
→ gửi đồng thời
→ từng request thấy tổng cũ
→ tất cả đi qua tuyến duyệt thấp
~~~

Các số tiền trong bài chỉ minh họa một chính sách ứng dụng, không phải quy định pháp lý hay tư vấn tài chính.

## 2. Mô hình hóa điều kiện được phép thực hiện

Một điều kiện đầy đủ có thể diễn đạt:

~~~text
CanExecute =
  caller có quyền yêu cầu thực hiện trên đối tượng
  AND request ở trạng thái cho phép
  AND nội dung thực hiện khớp nội dung được duyệt
  AND chính sách áp dụng được xác định hợp lệ
  AND đủ phê duyệt cho giá trị và phạm vi hiện tại
  AND đáp ứng tách nhiệm vụ
  AND thẩm quyền phê duyệt còn hợp lệ theo hợp đồng
  AND hạn mức/tài nguyên liên quan được giữ đúng
  AND chưa thực hiện cùng ý định trước đó
~~~

Không được rút gọn điều kiện này thành:

~~~java
if (request.isApproved()) {
    paymentGateway.pay(request);
}
~~~

Cờ `approved` không cho biết:

- Ai duyệt và dựa vào quyền nào.
- Duyệt phiên bản nội dung nào.
- Số tiền, tiền tệ và người nhận khi duyệt là gì.
- Có đủ các chữ ký độc lập không.
- Chính sách hoặc phạm vi đã thay đổi chưa.
- Giao dịch đã được thực hiện ở lần thử trước hay chưa.

Các ràng buộc cốt lõi:

1. Mỗi lần cho phép thực hiện phải có căn cứ phê duyệt phù hợp.
2. Căn cứ đó phải gắn với đúng phiên bản nội dung có tác động.
3. Mọi đường thực hiện cùng tuân thủ một chính sách có thẩm quyền.
4. Người dùng không tự cung cấp kết quả đánh giá hoặc vai trò của mình.
5. Retry không thực hiện thêm tác động.
6. Thay đổi quan trọng phải dẫn đến đánh giá lại theo chính sách.

## 3. Định nghĩa chính xác số tiền và toán tử biên

### 3.1. Giá trị dùng xét ngưỡng phải do server xác định

Một yêu cầu có:

~~~text
Giá trị hàng hóa: 96 triệu
Thuế và phí thuộc phạm vi hạn mức: 8 triệu
Tổng xét ngưỡng: 104 triệu
~~~

Nếu API duyệt dựa trên subtotal 96 triệu nhưng thực hiện chi 104 triệu, người dùng đã đi qua thẩm quyền thấp hơn quy định.

Cần định nghĩa giá trị hạn mức gồm những gì: thuế, phí, chiết khấu, dòng điều chỉnh, số lượng, cam kết nhiều kỳ hoặc tổng hợp đồng. Server tính từ dữ liệu đã xác minh.

Không chấp nhận `approvalAmount` thấp hơn `paymentAmount` do client tự khai. Nếu hai giá trị khác nhau vì một nghiệp vụ hợp lệ, quan hệ đó phải được chính sách mô hình hóa rõ.

### 3.2. Xét biên một cách tường minh

Với chính sách đầu bài:

| Giá trị | Phê duyệt cần có |
| --- | --- |
| Dưới 100 triệu | L1 nếu các điều kiện khác đúng |
| Đúng 100 triệu | L1 nếu các điều kiện khác đúng |
| Trên 100 triệu, dưới 500 triệu | L2 |
| Đúng hoặc trên 500 triệu | Các phê duyệt độc lập theo chính sách |

Không dùng mô tả “quanh 100 triệu” hoặc các phép làm tròn khác nhau giữa duyệt và thực hiện.

Các cấp trên là nhãn minh họa. Không mặc nhiên giả định người có L2 có mọi quyền L1 trên mọi pháp nhân. Quyền còn có phạm vi và quan hệ tổ chức.

Hai chữ ký L1 cũng không tự tạo thành một chữ ký L2. Chỉ được kết hợp nếu chính sách định nghĩa tổ hợp đó là đủ.

### 3.3. Chuẩn hóa tiền và tiền tệ

Dùng số nguyên theo đơn vị nhỏ nhất đã quy định hoặc kiểu thập phân chính xác. Kiểm tra số âm, số lượng, làm tròn và tràn số.

Không dùng số thực nhị phân cho phép so sánh ngưỡng tiền. Nếu cộng bằng `long` trong Java, có thể dùng `Math.addExact` để phát hiện tràn, sau đó từ chối dữ liệu không thể xử lý thay vì cắt giá trị.

Không cộng trực tiếp các tiền tệ khác nhau. Nếu quy đổi về tiền tệ chính sách, tỷ giá và cách làm tròn phải có nguồn, phiên bản và thời điểm rõ ràng. Thay đổi giá trị quy đổi có thể làm thay đổi yêu cầu duyệt.

## 4. Những đường vượt ngưỡng thường gặp

| Đường lạm dụng | Sai sót phía hệ thống | Ràng buộc cần bảo vệ |
| --- | --- | --- |
| Sửa số tiền sau duyệt | Phê duyệt chỉ gắn request ID | Gắn với phiên bản nội dung |
| Sửa người nhận hoặc tài khoản nhận | Chỉ so sánh tổng tiền | Bảo vệ toàn bộ nội dung có tác động |
| Gửi `approved`, `requiredLevel` hoặc `approverRole` | Tin dữ liệu client | Server tự xác định quyền và quyết định |
| Gọi API thực hiện trực tiếp | Chỉ kiểm tra ở màn hình hoặc endpoint duyệt | Kiểm tra tại cổng thực hiện |
| Chia nhỏ yêu cầu | Chỉ kiểm tra từng chứng từ | Cộng gộp theo phạm vi chính sách |
| Gửi đồng thời | Đọc tổng và ghi độc lập | Transaction và điều phối đồng thời |
| Dùng chữ ký cũ cho bản mới | Không kiểm tra phiên bản hoặc fingerprint | Khớp quyết định với nội dung |
| Đổi pháp nhân, dự án, người tạo | Phạm vi từ request không được xác minh | Kiểm tra quan hệ và quyền theo đối tượng |
| Dùng ủy quyền quá rộng | Quyền được ủy vượt quyền gốc | Giới hạn và xác minh chuỗi ủy quyền |
| Retry lệnh chi trả | Không có idempotency xuyên luồng | Một ý định chỉ có một tác động |
| Gọi đường import, batch hoặc worker | Các đường phụ thiếu policy gate | Cùng giao thức bảo vệ |
| Hạ cấu hình ngưỡng hoặc bỏ kiểm tra khi lỗi | Chính sách fallback không an toàn | Cấu hình có thẩm quyền và xử lý lỗi rõ ràng |

Không cần hệ thống có lỗi xác thực để các tình huống này xảy ra. Người dùng có thể được phép tạo hoặc sửa yêu cầu nhưng sử dụng quyền đó để phá ý định của quy trình.

## 5. Đưa kiểm tra về phía server và cổng thực hiện

Nút “Duyệt” ẩn trên giao diện chỉ phục vụ trải nghiệm. Người dùng vẫn có thể gửi request bằng công cụ khác hoặc phát lại một request cũ.

Mỗi đường tạo tác động cần đi qua logic nghiệp vụ có thẩm quyền:

~~~text
HTTP endpoint / batch / import / worker / callback
                    ↓
        kiểm tra danh tính và quyền trên đối tượng
                    ↓
        nạp nội dung và ngữ cảnh được bảo vệ
                    ↓
        tính yêu cầu phê duyệt từ chính sách
                    ↓
        xác minh quyết định duyệt và trạng thái
                    ↓
        ghi quyền thực hiện/tác động một cách nguyên tử
~~~

Không để một adapter gọi thẳng repository để đặt trạng thái thành `EXECUTED` hoặc gửi lệnh sang dịch vụ chi trả mà bỏ qua cổng này.

Phân biệt hai lớp:

- **Quyền gọi thao tác:** chủ thể có thể gửi yêu cầu thực hiện cho đối tượng đó hay không.
- **Điều kiện nghiệp vụ:** đối tượng hiện đã đủ căn cứ để thực hiện hay chưa.

Một service account có quyền kỹ thuật gọi API chưa chắc được quyền miễn phê duyệt. Nếu có ngoại lệ, đó phải là một thẩm quyền được mô hình hóa, giới hạn và audit.

DTO đầu vào nên chỉ chứa ý định và tham số được phép thay đổi. Các trường trạng thái, người duyệt, cấp yêu cầu, tổng đã tính và dấu vết quyết định thuộc phía server.

Ngay cả khi dùng cơ chế chống mass assignment ở framework, domain vẫn phải kiểm tra các chuyển trạng thái. Không dựa vào danh sách trường bị chặn ở một controller để bảo vệ toàn bộ ứng dụng.

## 6. Ràng buộc phê duyệt với phiên bản nội dung

### 6.1. Nội dung nào cần được bảo vệ?

Một quyết định duyệt thường cần gắn với:

~~~text
request_id
content_version
tenant và pháp nhân
số tiền, tiền tệ, thuế và phí liên quan
người nhận và phiên bản thông tin tài khoản nhận
dự án, hợp đồng, mục đích
các dòng hàng hoặc nghĩa vụ tạo thành tổng
cơ sở tỷ giá nếu có
phiên bản chính sách hoặc quy tắc lựa chọn chính sách
~~~

Chỉ hash `request_id + amount` chưa đủ. Người dùng có thể giữ nguyên số tiền nhưng đổi tài khoản người nhận.

Nếu tài khoản ngân hàng nằm trong hồ sơ đối tác có thể sửa độc lập, cần gắn với snapshot hoặc phiên bản thông tin nhận tiền. Gắn mỗi `beneficiary_id` chưa chứng minh dữ liệu thực hiện khớp dữ liệu đã duyệt.

### 6.2. Phiên bản bất biến và fingerprint

Một cách triển khai:

1. Người dùng sửa draft.
2. Khi gửi, server tạo revision nội dung đã chuẩn hóa.
3. Quyết định duyệt tham chiếu revision đó.
4. Sửa trường quan trọng tạo revision mới.
5. Revision mới quay lại quy trình đánh giá và phê duyệt cần thiết.
6. Lệnh thực hiện chỉ sử dụng revision đã được cho phép.

Fingerprint có thể hỗ trợ đối chiếu nội dung chuẩn hóa. Quy tắc chuẩn hóa phải có phiên bản, xác định trường nào được bảo vệ và xử lý kiểu tiền, null, danh tính cùng dữ liệu lồng nhau nhất quán.

Không hash một JSON tùy ý của client rồi coi hash đó là bằng chứng phê duyệt. Server phải tạo hoặc xác minh nội dung chuẩn trước.

Fingerprint chứng minh sự khớp nội dung theo cơ chế đã thiết kế; nó không tự chứng minh người ký có đủ quyền.

### 6.3. Trường nào sửa mà không cần duyệt lại?

Có thể cho sửa một ghi chú không ảnh hưởng quyết định, nhưng phải định nghĩa danh sách và ý nghĩa rõ. Các trường ảnh hưởng giá trị, người nhận, phạm vi, rủi ro hoặc nghĩa vụ không nên được coi là “metadata vô hại”.

Test cần chứng minh các endpoint sửa phụ cũng tuân thủ cùng quy tắc, kể cả cập nhật hồ sơ tham chiếu.

## 7. Quyền theo đối tượng, tách nhiệm vụ và ủy quyền

### Quyền theo đối tượng

Không chỉ hỏi người dùng có role `APPROVER` hay không. Cần xác định quyền đó có áp dụng cho pháp nhân, đơn vị, dự án, loại chi phí và giá trị của yêu cầu không.

Danh tính và quyền xuất phát từ ngữ cảnh đã xác thực hoặc nguồn phân quyền có thẩm quyền, không từ `userId`, `role` hay `limit` trong body.

### Tách nhiệm vụ

Nếu chính sách cấm tự duyệt, cần đối chiếu danh tính nghiệp vụ thực sự. Không chỉ so sánh với tài khoản kỹ thuật cuối cùng ghi bản ghi.

Ví dụ một người tạo yêu cầu qua hệ thống tích hợp rồi tự duyệt bằng tài khoản cá nhân. Nguồn gốc người khởi tạo phải được lưu bằng dữ liệu tin cậy.

Với yêu cầu nhiều phê duyệt độc lập, kiểm tra người ký và quan hệ theo chính sách. Một người ký lại hai lần hoặc dùng hai phiên đăng nhập không tạo hai người duyệt.

### Ủy quyền

Một ủy quyền cần có phạm vi, thời hạn, trạng thái và nguồn quyền gốc. Quyền được sử dụng không được rộng hơn phần đã được cấp hợp lệ.

Cần kiểm tra:

- Người ủy quyền thực sự có quyền gốc cần thiết.
- Phạm vi người nhận được phép hành động.
- Hạn mức và thời gian.
- Thu hồi, hết hạn và khả năng ủy quyền tiếp.
- Các hạn chế về tự duyệt hoặc xung đột lợi ích.

Không cộng hạn mức của nhiều giấy ủy quyền thành một mức lớn hơn nếu chính sách không cho phép.

Quy tắc kiểm tra quyền tại lúc duyệt hay tiếp tục tại lúc thực hiện phải rõ. Nếu nguồn quyền ở hệ thống khác, cần mô hình nhất quán và hiệu lực thu hồi phù hợp; một bản cache không tự bảo đảm thu hồi tức thì.

## 8. Chống chia nhỏ và tranh chấp hạn mức

Ngay cả khi từng request có đủ phê duyệt riêng, người dùng vẫn có thể chia một nhu cầu lớn để đi qua ngưỡng thấp hơn.

Cần xác định phạm vi cộng gộp phù hợp: pháp nhân, đơn vị khởi tạo, dự án, hợp đồng, người thụ hưởng hoặc khoảng thời gian. Một chính sách có thể xét nhiều chiều cùng lúc.

Ví dụ:

~~~text
A = 40 triệu
B = 40 triệu
C = 40 triệu

Mỗi request < 100 triệu
Tổng cùng phạm vi = 120 triệu
~~~

Nếu chính sách ngưỡng áp dụng cho tổng cùng nhu cầu, C không được thực hiện chỉ dựa trên thẩm quyền thấp.

Các yêu cầu đang chờ duyệt hoặc đã duyệt chưa thực hiện có thể phải được tính vào tổng để tránh cùng hứa sử dụng một phần hạn mức. Việc tính trạng thái nào phải được quy định, không suy ra từ giao diện.

Một mẫu bảo vệ:

~~~text
aggregate = gross_executed + reserved_pending
~~~

Gửi yêu cầu tạo contribution một lần; thực hiện chuyển pending sang executed; hủy trước thực hiện giải phóng pending đúng một lần. Trong chính sách tổng giá trị dương này, hoàn tiền sau thực hiện không tự xóa gross.

### Các request đồng thời

Nếu tổng hiện tại là 80 triệu, hai request 15 triệu cùng đọc tổng cũ có thể cùng kết luận 95 triệu. Tổng thật sau đó là 110 triệu.

Phải bảo vệ việc ghi contribution và đánh giá bằng cùng giao thức đồng thời: hàng tổng được khóa, cập nhật có điều kiện hoặc một thiết kế tương đương có chứng minh bất biến.

Khóa duy nhất trên danh tính phạm vi giúp ngăn tạo hai bucket đại diện cùng tổng. Tất cả thao tác sửa, hủy, duyệt, thực hiện và quản trị phải dùng cùng giao thức.

Không dùng dữ liệu tổng từ cache hoặc replica trễ để cấp quyền cần nhất quán chặt.

Cộng gộp theo ngày chưa chắc chống chia nhỏ qua nhiều ngày. Nếu chính sách xét toàn hợp đồng, cần chiều theo hợp đồng. Client cũng không được tự đổi ngày, pháp nhân hoặc mã mục đích để tạo bucket trống.

## 9. State machine và cổng thực hiện có transaction

### 9.1. Trạng thái phải thể hiện nghĩa vụ thực sự

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL: Gửi revision
    PENDING_APPROVAL --> APPROVED: Đủ quyết định duyệt
    PENDING_APPROVAL --> REJECTED: Từ chối
    APPROVED --> PENDING_APPROVAL: Sửa nội dung hoặc cần duyệt lại
    APPROVED --> EXECUTION_AUTHORIZED: Kiểm tra cuối và ghi lệnh
    EXECUTION_AUTHORIZED --> EXECUTED: Xác nhận thực hiện thành công
    DRAFT --> CANCELLED: Hủy
    PENDING_APPROVAL --> CANCELLED: Hủy hợp lệ
    APPROVED --> CANCELLED: Hủy trước cấp lệnh nếu được phép
~~~

`EXECUTION_AUTHORIZED` không đồng nghĩa dịch vụ ngoài đã thực hiện. Nó ghi nhận một lệnh có nội dung bất biến và căn cứ cho phép cụ thể.

Sau khi cấp lệnh, không sửa trực tiếp revision để đổi số tiền hoặc người nhận của lệnh đó. Nếu cần hủy khi lệnh có thể đã được gửi, phải dùng giao thức hủy và đối soát; đổi cờ trong cơ sở dữ liệu chưa tự thu hồi được tác động ngoài.

### 9.2. Giả mã kiểm tra cuối

~~~java
return transaction.execute(() -> {
    ApprovalRequest request = requests.lockForUpdate(
        principal.tenantId(), requestId
    );
    authorization.requireRequestExecution(principal, request);

    Optional<ExecutionResult> previous = idempotency.findSameIntent(
        principal, operationKey, requestFingerprint
    );
    if (previous.isPresent()) {
        return previous.get();
    }

    request.requireApproved();

    ImmutableRevision revision = revisions.load(request.revisionId());
    revision.verifyTrustedContent();

    ProtectedContext context = protectedContext.loadForDecision(
        request, revision
    );
    Instant decisionAt = decisionTimeSource.readAfterLocks();

    ApprovalRequirement requirement = policy.evaluate(
        revision, context, decisionAt
    );

    ApprovalCheck check = approvalVerifier.check(
        request.persistedApprovals(),
        revision,
        requirement,
        context,
        decisionAt
    );

    if (!check.satisfied()) {
        request.requireMoreApproval(check.reason());
        requests.save(request);
        return ExecutionResult.moreApprovalRequired();
    }

    context.verifyBudgetAndAggregation();
    context.ensureContributionRecordedOnce(request);

    ExecutionCommand command = executionCommands.createImmutable(
        request, revision, requirement, check, decisionAt
    );

    request.authorizeExecution(command.id());
    requests.save(request);
    outbox.addExecutionCommand(command);

    ExecutionResult result = ExecutionResult.authorized(command.id());
    idempotency.save(operationKey, requestFingerprint, result);

    return result;
});
~~~

Các hàm và kiểu trên là giả mã. Khi hiện thực cần bảo đảm:

- `ProtectedContext` sử dụng khóa, phiên bản hoặc cơ chế nhất quán đã thiết kế cho hạn mức, quyền và chính sách.
- Thứ tự khóa được dùng thống nhất ở mọi đường ghi để tránh deadlock.
- Clock được đọc sau các khóa cần thiết nếu hợp đồng chọn mốc đó.
- Contribution đã có không bị cộng thêm khi kiểm tra lại.
- Approvals được đọc từ dữ liệu bền vững, không lấy danh sách người duyệt từ request thực hiện.
- Revision thực hiện đúng revision được các phê duyệt áp dụng bao phủ.
- Request, lệnh, idempotency và outbox cùng commit hoặc rollback.
- Lỗi nguồn chính sách hoặc cơ sở dữ liệu không bị biến thành kết quả “đủ quyền”.

Việc nạp dữ liệu vào một object có tên `ProtectedContext` không tự làm nó an toàn. Implementation phải bảo vệ được các thay đổi cạnh tranh có thể làm quyết định lỗi thời.

### 9.3. Sửa và duyệt chạy đồng thời

Cả thao tác sửa lẫn duyệt cần điều phối trên cùng request hoặc kiểm tra version có điều kiện.

Nếu sửa thắng, người duyệt không được ghi quyết định cho revision cũ thành phê duyệt của revision mới.

Nếu duyệt thắng, lần sửa sau phải tạo revision mới và làm mất hiệu lực áp dụng của quyết định cũ theo chính sách. Không có kết quả hợp lệ nào cho phép duyệt 90 triệu nhưng thực hiện 190 triệu bằng cùng căn cứ không đổi.

## 10. Idempotency, lệnh bất biến và tác động bên ngoài

Một transaction nội bộ không thể tự rollback một khoản chi mà hệ thống ngoài đã nhận. Vì vậy cần ranh giới rõ:

~~~text
Transaction nội bộ:
  kiểm tra đủ điều kiện
  → ghi lệnh bất biến
  → ghi outbox
  → commit

Consumer:
  đọc lệnh
  → xác minh lệnh đủ điều kiện gửi theo hợp đồng
  → gọi hệ thống ngoài với khóa chống trùng ổn định
  → ghi và đối soát kết quả
~~~

Khóa chống trùng cần gắn với ý định thực hiện hoặc lệnh, không tạo key mới cho mỗi lần retry mạng.

Các yêu cầu:

- Retry API sau commit trả tham chiếu lệnh đã có, không cấp thêm lệnh.
- Consumer nhận cùng outbox nhiều lần không tạo thêm tác động.
- Cùng key nhưng khác revision hoặc số tiền phải bị từ chối.
- Timeout không đồng nghĩa hệ thống ngoài chưa thực hiện.
- Kết quả chưa rõ không được coi là thất bại chắc chắn rồi giải phóng mọi cam kết.
- Lệnh được phát chỉ dùng snapshot nội dung đã được cho phép, không nạp một bản ghi có thể sửa để đổi người nhận lúc gửi.

Cần định nghĩa hiệu lực của quyền thực hiện khi chính sách hoặc quyền người duyệt thay đổi sau khi lệnh được cấp.

Một thiết kế có thể giữ hiệu lực của quyền đã cấp trong khoảng cho phép; thiết kế khác yêu cầu consumer kiểm tra lại trước khi gửi. Nếu chọn kiểm tra lại, phải bảo đảm không có đường consumer bỏ qua và phải xử lý các lệnh bị chặn.

Không thể hứa thu hồi tức thì một tác động mà bên ngoài đã chấp nhận. Việc dừng lệnh chưa gửi, đối soát lệnh chưa rõ kết quả và bù trừ tác động đã xảy ra là các nghiệp vụ khác nhau.

## 11. Chính sách, cấu hình và ngoại lệ

### 11.1. Chính sách là dữ liệu bảo mật

Ngưỡng, đơn vị tiền, nhóm quyền, phạm vi cộng gộp và luật kết hợp chữ ký cần được quản lý bằng quyền phù hợp, lịch sử phiên bản và kiểm tra tính hợp lệ.

Ví dụ cấu hình thiếu đơn vị tiền hoặc hai khoảng ngưỡng chồng lấn không được âm thầm tạo một tuyến “không cần duyệt”.

Nếu nguồn chính sách lỗi:

- Không lấy cấp duyệt từ client.
- Không tự đặt ngưỡng vô hạn.
- Không dùng một cấu hình mặc định làm giảm yêu cầu.
- Chỉ dùng fallback khi đó là chính sách dự phòng đã được định nghĩa và kiểm soát.

Giá trị cấu hình trong cache cần quy tắc hiệu lực. Một cache cũ không tự là căn cứ cho phép tiếp tục áp dụng hạn mức cũ sau khi chính sách yêu cầu đánh giá lại.

### 11.2. Chính sách đổi trong lúc chờ duyệt

Xác định rõ yêu cầu đang chờ giữ phiên bản cũ hay chuyển sang phiên bản mới. Khi cần chuyển, lưu dấu vết và đánh giá lại trước thực hiện.

Không chỉ đổi `policy_version` rồi coi tất cả phê duyệt cũ vẫn đủ. Cũng không gắn version vào khóa tổng theo cách vô tình xóa lịch sử cộng gộp.

### 11.3. Ngoại lệ cần là một quy trình có thẩm quyền

Một trường `skipApproval = true` hoặc quyền kỹ thuật chung của tài khoản vận hành dễ tạo đường vượt ngưỡng.

Nếu nghiệp vụ có ngoại lệ khẩn cấp, nên mô hình hóa:

- Người có quyền cho phép ngoại lệ.
- Phạm vi, số tiền và thời gian.
- Lý do và chứng cứ.
- Điều kiện tách nhiệm vụ cần thiết.
- Dấu vết quyết định và kiểm tra sau đó.
- Cách ngăn tái sử dụng ngoại lệ cho ý định khác.

Ngoại lệ không nên là sửa trực tiếp trạng thái hoặc số tiền trong cơ sở dữ liệu mà không có căn cứ bền vững.

## 12. Kiểm thử tình huống vượt ngưỡng

### 12.1. Một chuỗi kiểm thử xuyên suốt

~~~text
1. Tạo revision R1: tổng 90 triệu.
2. L1 duyệt R1.
3. Sửa thành R2: tổng 190 triệu hoặc đổi tài khoản nhận.
4. Gọi execute bằng approval hoặc token của R1.

Expected:
  R2 cần căn cứ phê duyệt phù hợp riêng.
  Không tạo lệnh chi trả theo R2 từ phê duyệt R1.
  Không tiêu hao hoặc giải phóng hạn mức sai.
  Audit giữ được R1, R2 và lý do từ chối.
~~~

Test phải đi qua cả endpoint sửa phụ hoặc dữ liệu tham chiếu, không chỉ endpoint chỉnh số tiền chính.

### 12.2. Ma trận kiểm thử

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Dưới, đúng bằng và trên mỗi ngưỡng | Đúng toán tử biên và tập phê duyệt |
| Subtotal thấp nhưng thuế/phí làm tổng vượt ngưỡng | Đánh giá trên đúng tổng chính sách |
| Số âm, tràn số hoặc scale không hợp lệ | Bị chặn, không làm giảm giá trị xét duyệt |
| Client gửi `approved`, `requiredLevel`, `role` | Không cấp quyền từ dữ liệu giả |
| Gọi execute khi chưa duyệt | Không có lệnh hoặc tác động thực hiện |
| Đổi HTTP method, đi qua batch/import/worker | Vẫn chịu cùng policy gate |
| Duyệt request của tenant hoặc pháp nhân khác | Bị chặn theo quyền đối tượng |
| Người tạo tự duyệt qua tài khoản tích hợp | Không vượt quy tắc tách nhiệm vụ |
| Một người gửi hai chữ ký | Không tạo đủ hai người duyệt độc lập |
| Hai người L1 duyệt yêu cầu cần L2 | Không tự được coi là đủ |
| Ủy quyền hết hạn hoặc vượt phạm vi | Không được dùng làm căn cứ |
| Sửa tiền, tiền tệ hoặc người nhận sau duyệt | Bắt buộc đánh giá lại theo revision |
| Hồ sơ người nhận đổi tài khoản sau duyệt | Không gửi tới thông tin mới bằng căn cứ cũ |
| Duyệt và sửa đồng thời | Không gắn quyết định cũ vào nội dung mới |
| Chia nhỏ cùng nhu cầu qua nhiều yêu cầu | Tổng liên quan vẫn kích hoạt đúng yêu cầu |
| Gửi đồng thời tại phần ngưỡng còn lại | Không dùng cùng tổng cũ để cấp quyền |
| Hủy, hoàn hoặc contribution âm giả | Không làm sạch hạn mức sai |
| Chính sách đổi giữa duyệt và thực hiện | Theo đúng quy tắc phiên bản và hiệu lực |
| Nguồn policy hoặc quyền không khả dụng | Không giảm yêu cầu bằng fallback ngầm |
| Retry API hoặc consumer sau mất response | Chỉ một lệnh và một tác động có hiệu lực |
| Sửa nội dung một lệnh đã cấp | Bị chặn; lệnh gắn revision bất biến |
| Dùng ngoại lệ cũ cho request mới | Bị chặn theo phạm vi và ý định |
| Lỗi sau ghi trạng thái nhưng trước commit | Request, bộ đếm, lệnh và outbox nhất quán |

### 12.3. Kiểm tra dữ liệu sau test

Không chỉ assert mã 403 hoặc lỗi “thiếu duyệt”. Cần đối chiếu:

~~~text
revision đang có hiệu lực
các quyết định duyệt và content_version
trạng thái request
contribution và tổng hạn mức
số execution command
nội dung và fingerprint của command
idempotency record
outbox
số tác động thực tế ở hệ thống ngoài giả lập
~~~

Với tranh chấp, dùng các transaction độc lập và điều phối có timeout. Tạo cả thứ tự sửa thắng duyệt, duyệt thắng sửa, cấp lệnh thắng hủy và hủy thắng cấp lệnh theo hợp đồng của ứng dụng.

Kiểm thử chính sách thuần nên có dữ liệu biên và tiền tệ chuẩn hóa. Integration test cần chứng minh khóa, ràng buộc duy nhất và rollback. Test API cần chứng minh người dùng không gửi trường nội bộ hoặc đi vòng endpoint.

Có thể đánh giá sức mạnh bộ test bằng cách cố ý bỏ kiểm tra revision, đổi toán tử biên hoặc bỏ policy gate ở một adapter trong môi trường phát triển. Các test tương ứng phải phát hiện được thay đổi sai đó.

## 13. Audit và phát hiện hành vi né quy trình

Một bản ghi quyết định hữu ích gồm:

~~~text
request_id, revision_id, content_fingerprint
actor_id, business_originator_id
approver_id và căn cứ thẩm quyền
policy_version, decision_at
số tiền, tiền tệ và cơ sở chuẩn hóa
các phạm vi cộng gộp và tổng dùng để quyết định
tập phê duyệt bắt buộc và đã thỏa mãn
outcome, reason_code
execution_command_id, idempotency_reference
correlation_id
~~~

Thông tin nhạy cảm như tài khoản nhận cần cách lưu, che hiển thị và phân quyền phù hợp. Không cần sao chép toàn bộ request hoặc dữ liệu xác thực vào log.

Các tín hiệu hỗ trợ rà soát:

- Nhiều yêu cầu ngay dưới ngưỡng trong cùng phạm vi.
- Sửa số tiền hoặc người nhận ngay sau duyệt.
- Thử execute nhiều lần khi thiếu căn cứ.
- Đổi pháp nhân, dự án hoặc người khởi tạo để tạo tổng mới.
- Tần suất dùng ngoại lệ bất thường.
- Chênh lệch giữa revision đã duyệt và nội dung lệnh.
- Nhiều lỗi policy gate từ cùng đường batch hoặc consumer.

Theo dõi giúp phát hiện vấn đề, còn ngăn chặn phải nằm tại đường quyết định. Không chờ một job phát hiện chia nhỏ sau khi tất cả lệnh đã được thực hiện.

Audit cần cho phép tái hiện chính sách và dữ liệu lịch sử. Tính lại bằng ngưỡng hiện tại không chứng minh được quyết định cũ đúng hay sai tại thời điểm nó được đưa ra.

## 14. Những câu hỏi cần trả lời trước khi triển khai

1. Giá trị xét ngưỡng được tính từ dữ liệu nào và có bao gồm phí, thuế, tỷ giá không?
2. Ngưỡng áp dụng cho một yêu cầu hay tổng theo những phạm vi nào?
3. Ai có thể thay đổi ngưỡng, cấu hình quyền và dữ liệu người nhận?
4. Phê duyệt gắn với revision hoặc snapshot nào?
5. Những sửa đổi nào làm mất hiệu lực áp dụng của quyết định cũ?
6. Mọi endpoint, batch, worker và callback có chung cổng kiểm tra không?
7. Quyền người duyệt có đúng phạm vi và đáp ứng tách nhiệm vụ không?
8. Điều gì bảo vệ quyết định khỏi sửa hoặc gửi đồng thời?
9. Retry và kết quả chưa rõ ở dịch vụ ngoài được xử lý thế nào?
10. Ngoại lệ có phạm vi, thời hạn và chứng cứ riêng hay chỉ là cờ bỏ qua?
11. Có thể giải thích vì sao một lệnh được cho phép bằng dữ liệu đã lưu không?
12. Test nào chứng minh một phê duyệt cho yêu cầu nhỏ không thể dùng để thực hiện nội dung lớn hơn hoặc khác người nhận?

Ngăn vượt ngưỡng đòi hỏi gắn quyền phê duyệt với nội dung bất biến, cộng gộp đúng phạm vi, bảo vệ transaction và kiểm tra tại điểm tạo tác động. Một quy trình chỉ đáng tin khi người dùng không thể đạt cùng kết quả bằng đường khác ít kiểm soát hơn.
