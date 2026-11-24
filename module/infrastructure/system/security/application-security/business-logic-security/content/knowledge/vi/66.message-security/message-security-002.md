# Phân quyền cho consumer xử lý thông điệp (Message consumer authorization)

Trong chương **Message Security** của module **Bảo mật logic nghiệp vụ**, bài học này tập trung vào việc xác định consumer được phép làm gì khi nhận một thông điệp. Consumer là thành phần đọc thông điệp và xử lý chúng, thường là một dịch vụ hoặc worker chạy nền.

Một consumer có thể giữ tài khoản cơ sở dữ liệu mạnh, truy cập nhiều đơn vị và gọi nhiều dịch vụ nội bộ. Vì vậy, nếu nó coi mọi thông điệp đọc được là một lệnh hợp lệ, kẻ lạm dụng có thể mượn quyền của consumer để sửa giá, bỏ qua phê duyệt, thao tác chéo đơn vị hoặc tạo giao dịch trùng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt quyền kết nối broker, quyền nhận dữ liệu và quyền thực hiện một hành động nghiệp vụ.
- Xác định chủ thể cần kiểm tra khi consumer xử lý lệnh được ủy quyền, sự kiện nghiệp vụ hoặc nghĩa vụ hệ thống.
- Kiểm tra quyền theo đơn vị, đối tượng, hành động, tham số và trạng thái hiện tại.
- Ngăn consumer trở thành đại diện bị lợi dụng để thực hiện thao tác vượt quyền.
- Kết hợp phân quyền, transaction, inbox, outbox và idempotency để giữ bất biến khi có retry.
- Thiết kế quyết định từ chối, cách ly và phát lại có kiểm toán mà không tạo đường vòng bỏ qua quyền.

## 2. Ba quyết định quyền ở ba ranh giới

Thông điệp thường đi qua nhiều ranh giới tin cậy. Mỗi ranh giới cần một quyết định riêng.

| Ranh giới | Câu hỏi cần trả lời | Ví dụ kiểm soát |
| --- | --- | --- |
| Kết nối và đăng ký nhận | Dịch vụ nào được đọc nguồn thông điệp nào? | Danh tính dịch vụ, kết nối bảo mật, ACL hoặc chính sách tương ứng của broker |
| Tiếp nhận và diễn giải | Nguồn này có được gửi loại thông điệp và phạm vi này không? | Xác minh nguồn tin cậy, loại thông điệp, phiên bản, đích nhận và giới hạn nguồn phát |
| Tạo tác động nghiệp vụ | Hành động cụ thể này có được phép với đối tượng hiện tại không? | Quyền theo đối tượng, ủy quyền, phê duyệt, trạng thái, hạn mức và bất biến |

Một broker bảo vệ tốt đường đọc giúp giảm nguồn có thể tiếp cận dữ liệu. Quyết định đổi trạng thái đơn hàng vẫn cần được bảo vệ tại dịch vụ áp dụng thay đổi.

Ví dụ: consumer được đọc hàng đợi yêu cầu hoàn tiền. Điều đó không tự cho phép nó hoàn bất kỳ số tiền nào cho bất kỳ đơn hàng nào. Nó còn phải xác minh nguồn yêu cầu, nghĩa vụ hoàn tiền, người được ủy quyền nếu có, đơn vị sở hữu, giới hạn và trạng thái thanh toán.

Quyền đọc cũng là một quyền quan trọng: thông điệp có thể chứa dữ liệu khách hàng, giá nội bộ hoặc thông tin giao dịch. Consumer chưa được phép đọc dữ liệu của một đơn vị thì không nên nhận toàn bộ payload rồi mới bỏ qua sau.

## 3. Phân biệt các chủ thể tham gia

Trong một lần xử lý có thể tồn tại nhiều danh tính:

| Chủ thể | Ý nghĩa | Sai lầm thường gặp |
| --- | --- | --- |
| Danh tính consumer | Dịch vụ đang thực hiện mã xử lý | Dùng quyền mạnh của dịch vụ để hợp thức hóa mọi yêu cầu |
| Nguồn phát đã được xác minh | Dịch vụ hoặc thành phần được phép tạo thông điệp | Tin chuỗi `producerService` do payload tự khai |
| Người khởi tạo | Người tạo yêu cầu nghiệp vụ ban đầu | Tin một `userId` mà không có bằng chứng ủy quyền |
| Chủ thể được ủy quyền thực thi | Danh tính mà một quyền cấp cho phép hành động thay mặt | Cho phép một consumer khác dùng lại quyền không dành cho nó |
| Đơn vị và chủ sở hữu đối tượng | Phạm vi dữ liệu, tài nguyên và quyền | Lấy `tenantId` từ body làm kết luận cuối cùng |

Nguồn phát hợp lệ vẫn có thể gửi yêu cầu ngoài phạm vi được cấp do lỗi hoặc bị xâm nhập. Cần ràng buộc nguồn với loại hành động, đơn vị và đối tượng hoặc nhóm đối tượng mà nó được phép tác động.

Tình huống **confused deputy** xảy ra khi consumer có quyền mạnh bị dẫn dắt làm việc mà người yêu cầu không được phép làm. Ví dụ, một dịch vụ tiếp nhận yêu cầu có thể gửi `orderId` do khách hàng nhập; consumer dùng tài khoản nội bộ để hoàn tiền cho đơn đó mà không kiểm tra quyền sở hữu.

Cách bảo vệ là làm rõ chuỗi thẩm quyền và kiểm tra đối tượng tại nơi tạo tác động, thay vì suy ra quyền từ việc “thông điệp đã vào được hệ thống”.

## 4. Chọn mô hình quyền theo ý nghĩa thông điệp

Không phải mọi thông điệp đều mang cùng ngữ nghĩa. Cần phân biệt lệnh đề nghị một tác động với sự kiện ghi nhận một sự thật đã xảy ra.

### 4.1. Lệnh được người dùng ủy quyền

Ví dụ: `ApproveRefundRequested` đề nghị phê duyệt hoàn tiền cho một đơn cụ thể.

Consumer cần bằng chứng cho biết ai được phép yêu cầu, ai được phép thực thi, hành động nào, phạm vi nào, thời hạn nào và những phê duyệt nào phải có. Nếu chính sách yêu cầu quyền còn hiệu lực khi xử lý, việc người dùng có quyền lúc gửi chưa đủ.

Một thông điệp được tiếp nhận lúc 10:00 nhưng xử lý lúc 10:20 có thể phải bị từ chối nếu quyền đã bị thu hồi hoặc phê duyệt đã hết hạn trước điểm quyết định thực thi.

### 4.2. Sự kiện về một nghiệp vụ đã commit

Ví dụ: `PaymentCaptured` thông báo rằng khoản thu đã được xác nhận và ghi nhận bền vững.

Consumer cần xác minh nguồn được phép phát sự kiện đó, bằng chứng hoặc tham chiếu nghiệp vụ phù hợp, phạm vi đối tượng và chuyển trạng thái được phép. Nó có thể thực hiện một nghĩa vụ tiếp theo bằng thẩm quyền dịch vụ đã định.

Không nhất thiết yêu cầu người dùng ban đầu còn quyền hiện tại để xử lý một sự thật đã commit. Nếu khách hàng đóng tài khoản sau khi thanh toán, hệ thống vẫn cần ghi nhận hoặc đối soát khoản thanh toán đúng cách.

Ngược lại, đặt tên `PaymentCaptured` không làm dữ liệu trở thành sự thật. Nguồn phát phải thực sự có thẩm quyền khẳng định sự kiện và sự kiện phải khớp với hợp đồng, danh tính giao dịch cùng các bất biến.

### 4.3. Nghĩa vụ hệ thống

Ví dụ: thu hồi quyền đến hạn, giải phóng giữ chỗ hoặc cập nhật trạng thái theo một quyết định đã được phê duyệt.

Có thể dùng thẩm quyền dịch vụ giới hạn theo loại nghĩa vụ và đối tượng. Người dùng ban đầu hết phiên không nên vô tình ngăn một nghĩa vụ bảo vệ bắt buộc, nhưng consumer vẫn phải chứng minh nghĩa vụ tồn tại và các điều kiện hiện tại cho phép hành động.

| Loại thông điệp | Căn cứ quyền chính | Điều phải tránh |
| --- | --- | --- |
| Lệnh được ủy quyền | Quyền cấp và chính sách thực thi tương ứng | Giữ quyền vô thời hạn từ một lần kiểm tra ở API |
| Sự kiện đã commit | Nguồn có thẩm quyền và sự thật nghiệp vụ hợp lệ | Biến sự kiện tự khai thành quyền sửa mọi đối tượng |
| Nghĩa vụ hệ thống | Chính sách dịch vụ và bản ghi nghĩa vụ | Tài khoản dịch vụ có quyền toàn cục không ràng buộc đối tượng |

Mỗi handler cần được gắn với mô hình rõ ràng. Không để cùng một handler lúc thì tin quyền người dùng, lúc thì tự chuyển sang quyền dịch vụ chỉ vì kiểm tra thất bại.

## 5. Các bất biến phân quyền của consumer

Một tập bất biến minh họa:

1. Chỉ nguồn được phép mới tạo được loại thông điệp mà handler chấp nhận.
2. Danh tính nguồn và các trường ảnh hưởng quyết định phải có bằng chứng toàn vẹn phù hợp với kiến trúc.
3. Hành động chỉ tác động đối tượng thuộc đúng phạm vi được cấp; biết ID không tạo quyền.
4. Lệnh được ủy quyền không vượt hành động, tham số, thời hạn hoặc hạn mức đã duyệt.
5. Consumer không dùng quyền tài khoản dịch vụ để bù cho quyền người yêu cầu bị thiếu.
6. Phê duyệt phải khớp nội dung và phiên bản nghiệp vụ; đổi số tiền hoặc người nhận không được giữ phê duyệt cũ.
7. Một nghĩa vụ nghiệp vụ chỉ tạo tác động theo số lần được phép dù thông điệp bị giao lại.
8. Thay đổi trạng thái phải hợp lệ ngay tại nơi áp dụng, kể cả khi payload phản ánh trạng thái cũ.
9. Từ chối hoặc cách ly phải có dấu vết phù hợp; retry không biến một lệnh trái quyền thành hợp lệ.
10. Mọi đường phát lại và thao tác hỗ trợ đều chịu cùng ràng buộc nghiệp vụ.

Những bất biến này phải được đặt trong lớp thực thi dùng chung hoặc nơi tạo tác động. Kiểm tra ở một màn hình quản trị không bảo vệ được đường worker gọi trực tiếp.

## 6. Ngữ cảnh quyền trong thông điệp

Một lệnh có thể mang các tham chiếu sau:

```json
{
  "messageId": "msg-742",
  "messageType": "ApproveRefundRequested",
  "schemaVersion": 1,
  "intendedConsumer": "refund-approval-worker",
  "tenantId": "tenant-17",
  "initiatorId": "user-31",
  "delegationId": "grant-906",
  "operationId": "refund-208",
  "orderId": "order-551",
  "expectedOrderVersion": 12,
  "requestedAt": "2026-11-22T03:00:00Z",
  "expiresAt": "2026-11-22T03:10:00Z"
}
```

Đây là ví dụ cấu trúc, chưa có nghĩa các trường đã đáng tin. Consumer cần lấy nguồn đã xác minh từ cơ chế kết nối hoặc bảo vệ thông điệp phù hợp, rồi đối chiếu với chính sách phía máy chủ.

Các nguyên tắc thiết kế:

- `initiatorId` là tham chiếu cần xác minh; nó không tự chứng minh người đó đã ủy quyền.
- `delegationId` cần trỏ tới quyền cấp hợp lệ, hoặc được thay bằng một chứng thư ủy quyền có điều kiện và cơ chế thu hồi phù hợp.
- `intendedConsumer` giới hạn nơi quyền được dùng; consumer phải kiểm tra đích được cấp theo hợp đồng.
- `expiresAt` do người gọi gửi không được kéo dài quyền cấp gốc. Quyết định phải xét cả các giới hạn có thẩm quyền liên quan.
- `operationId` giúp xác định nghĩa vụ ổn định qua nhiều lần giao thông điệp.
- `expectedOrderVersion` có thể phát hiện nội dung đã được duyệt trên phiên bản cũ, theo chính sách của thao tác.

Không đưa mật khẩu hoặc token phiên người dùng dài hạn vào payload để consumer tùy ý dùng lại. Quyền ủy nhiệm cần giới hạn rõ hành động, người nhận, phạm vi và thời gian.

Nếu dùng chữ ký hoặc MAC, dữ liệu được bảo vệ phải bao phủ các trường có thể thay đổi quyết định, gồm định danh thông điệp, loại, đích, phạm vi, quyền cấp và nội dung nghiệp vụ. Cần một cách biểu diễn hoặc ký bytes được định nghĩa nhất quán; không tùy ý ký một bản JSON rồi xác minh một bản diễn giải khác.

Xác minh toàn vẹn thành công chứng minh một mối liên hệ với khóa hoặc danh tính tin cậy theo giao thức. Quyết định nguồn đó có được yêu cầu hành động trên đối tượng này vẫn thuộc chính sách phân quyền.

## 7. Kiểm tra quyền theo đối tượng tại consumer

Một quy trình xử lý nên trả lời tuần tự:

1. Nguồn đã được xác minh là ai, có được gửi loại thông điệp và phạm vi này không?
2. Handler này có phải đích được phép của lệnh hoặc sự kiện không?
3. Đây là lệnh ủy quyền, sự kiện đã commit hay nghĩa vụ hệ thống?
4. Đối tượng thực tế thuộc đơn vị nào, đang ở phiên bản và trạng thái nào?
5. Chuỗi thẩm quyền có cho phép đúng hành động và tham số hiện tại không?
6. Tác động có làm sai bất biến, hạn mức hoặc phân tách nhiệm vụ không?
7. Nghĩa vụ đã được thực hiện hoặc có một lần xử lý đang cạnh tranh chưa?

Ví dụ, khi xử lý `order-551`, consumer phải tải dữ liệu theo một phạm vi đã được xác minh và kiểm tra quan hệ sở hữu. Không chỉ so sánh hai trường `tenantId` cùng lấy từ payload rồi kết luận đã chống truy cập chéo đơn vị.

Đối tượng liên quan cũng phải được kiểm tra. Một đơn hàng đúng đơn vị không cho phép thay người nhận tiền sang một tài khoản ngoài phạm vi. Các tham số nhạy cảm như số tiền, giá đã duyệt và tài khoản nhận nên được đối chiếu với nguồn nghiệp vụ có thẩm quyền.

Với batch, quyền phải bao phủ từng đối tượng. Cần quy định rõ toàn bộ batch là nguyên tử hay từng phần có kết quả độc lập. Không cho phép một đối tượng hợp lệ ở đầu danh sách làm căn cứ thực thi cho các đối tượng còn lại.

## 8. Thời điểm kiểm tra quyền và thu hồi

Thông điệp có thể nằm chờ lâu. Quyết định ở API tiếp nhận không đủ chứng minh lệnh được phép khi consumer thực hiện.

Đối với quyền yêu cầu còn hiệu lực tại thời điểm xử lý, consumer cần kiểm tra lại:

- Người hoặc dịch vụ được cấp còn được phép thực thi.
- Quyền chưa hết hạn, bị thu hồi, bị thay thế hoặc hết hạn mức.
- Phê duyệt vẫn khớp nội dung và phiên bản cần áp dụng.
- Đối tượng chưa bị hủy, đóng hoặc chuyển sang trạng thái không cho phép.
- Chính sách quy định cho lệnh vẫn được đáp ứng.

Chữ ký của một token không tự thể hiện việc quyền đã bị thu hồi sau khi token được tạo. Nếu yêu cầu thu hồi phải có hiệu lực với các lệnh mới, cần tra trạng thái đủ nhất quán hoặc cơ chế xác minh tương đương.

Trong cùng cơ sở dữ liệu, có thể phối hợp kiểm tra quyền và cập nhật bằng khóa hoặc phiên bản. Luồng thu hồi phải dùng giao thức tương ứng. Nếu transaction thu hồi đã có hiệu lực trước điểm kiểm tra của lệnh, lệnh phải bị chặn.

Nếu lệnh đã giành quyền thực thi theo giao thức trước khi thu hồi hoàn tất, cần quy định rõ nó có thể hoàn tất hay phải bị ngăn ở một bước sau. Không hứa thu hồi hồi tố một tác động đã commit.

Khi quyền và tác động nằm ở các dịch vụ khác nhau, phải xác định độ trễ chấp nhận được và điểm quyết định có thẩm quyền. Cache quyền, thời hạn token ngắn hoặc một trường phiên bản không tự tạo ra bảo đảm thu hồi tức thời toàn hệ thống.

## 9. Minh họa luồng xử lý có transaction và inbox

Mã giả kiểu Java dưới đây minh họa một handler phê duyệt hoàn tiền theo ủy quyền. Nó giả định dữ liệu quyền, nghiệp vụ, inbox và outbox có thể được bảo vệ trong cùng cơ sở dữ liệu. Các repository và chính sách cần được triển khai theo cơ chế transaction thực tế.

```java
Disposition handle(TrustedDelivery delivery, byte[] rawMessage) {
    VerifiedMessage message = verifier.verifyAndParse(delivery, rawMessage);

    // Nguồn lấy từ bằng chứng tin cậy, không từ producerService trong body.
    VerifiedScope scope = sourcePolicy.requireAllowed(
        message.sourceIdentity(),
        message.type(),
        message.intendedConsumer(),
        message.tenantId()
    );

    return transaction.run(() -> {
        InboxEntry entry = inbox.lockOrCreate(
            HANDLER_ID, message.sourceIdentity(), message.messageId()
        );
        entry.requireSameProtectedContent(message);

        if (entry.isCompleted()) {
            // Không tạo tác động và không trả payload nghiệp vụ ra ngoài.
            return Disposition.ACK_DUPLICATE;
        }

        DelegationGrant grant =
            grants.lockForUpdate(message.delegationId());

        RefundContext context = refunds.lockContextForTenant(
            scope.tenantId(), message.operationId()
        );
        Instant checkedAt = databaseClock.currentInstant();

        authorization.requireDelegatedRefundApproval(
            message, scope, grant, context, checkedAt
        );

        OperationReceipt operation = operations.lockOrCreate(
            context.tenantId(), "REFUND_APPROVE", context.refundId()
        );
        operation.requireSameBusinessIntent(context, message);

        if (operation.isCompleted()) {
            entry.completeWithoutNewEffect(operation.id());
            return Disposition.ACK_DUPLICATE;
        }

        context.requireApprovalTransitionAllowed();
        ApprovalResult result = context.approveRefund(
            grant.authorizedSubjectId(), checkedAt
        );
        grants.consumeBudgetIfLimited(grant, context);

        operation.complete(result);
        audit.appendApproval(message, grant, context, checkedAt);
        outbox.appendRefundApproved(context, operation.id());
        entry.complete(operation.id());

        return Disposition.ACK_COMMITTED;
    });
}
```

Hàm `requireDelegatedRefundApproval` phải kiểm tra đủ các quan hệ có ý nghĩa, chẳng hạn:

- Quyền dành cho đúng consumer và chủ thể khởi tạo đã được xác minh.
- Hành động `REFUND_APPROVE` nằm trong quyền cấp.
- Đơn vị, đơn hàng và yêu cầu hoàn tiền khớp nhau.
- Số tiền, người nhận, phiên bản được duyệt và hạn mức nằm trong phạm vi.
- Quyền và phê duyệt còn hiệu lực tại điểm quyết định.
- Người phê duyệt độc lập với người yêu cầu nếu chính sách bắt buộc.
- Nghĩa vụ và đối tượng không bị hủy hoặc bị thay thế theo điều kiện liên quan.

Một số điều kiện của giao thức:

1. Inbox có ràng buộc duy nhất theo phạm vi đã chọn; hai consumer xử lý đồng thời không được cùng tạo hai bản ghi tự do.
2. Dấu vân tay hoặc nội dung bảo vệ của thông điệp phải bao gồm dữ liệu ảnh hưởng quyết định. Cùng ID nhưng khác nội dung là xung đột cần xử lý, không phải bản sao hợp lệ.
3. Kho nghĩa vụ nghiệp vụ cũng có ràng buộc chống trùng riêng. Hai `messageId` khác nhau vẫn có thể yêu cầu cùng một lần phê duyệt.
4. Các đường thu hồi, sửa quyền, sửa yêu cầu hoàn tiền và thực thi phải tuân giao thức khóa hoặc phiên bản nhất quán.
5. Thời gian dùng để xét hạn được lấy sau các bước chờ khóa cần thiết, với ngữ nghĩa nguồn thời gian đã xác định.
6. Audit, outbox, kết quả nghiệp vụ và inbox được commit cùng nhau trong mô hình này.
7. Consumer chỉ xác nhận thông điệp sau khi transaction cần thiết đã commit thành công.

Nếu tiến trình chết sau commit nhưng trước xác nhận với broker, thông điệp có thể được giao lại. Inbox đã hoàn tất giúp nhận ra bản giao lại chính xác và không thực hiện lần nữa.

Nhánh `ACK_DUPLICATE` chỉ xác nhận một thông điệp đã có kết quả bền vững hoặc một nghĩa vụ đã được xử lý theo điều kiện của nhánh đó. Nó không trả kết quả nhạy cảm cho một người gọi tùy ý. Nếu có API đọc biên nhận, API đó cần phân quyền đọc riêng.

## 10. Inbox và idempotency không thay thế quyền

Có hai bài toán khác nhau:

- Inbox ngăn cùng một thông điệp gây tác động lặp trong phạm vi handler đã chọn.
- Idempotency nghiệp vụ ngăn cùng một nghĩa vụ được thực hiện lại qua các thông điệp hoặc đường gọi khác nhau.

Ví dụ, hai thông điệp `msg-742` và `msg-743` cùng đề nghị phê duyệt `refund-208`. Inbox có thể coi đó là hai thông điệp khác nhau. Ràng buộc nghiệp vụ vẫn phải ngăn việc phê duyệt hoặc chi trả trùng cho cùng nghĩa vụ.

Ngược lại, một thông điệp có ID mới và khóa idempotency hợp lệ vẫn phải qua phân quyền. Chống trùng không làm một lệnh ngoài phạm vi trở thành hợp lệ.

Với thông điệp đã hoàn tất và được giao lại nguyên vẹn, có thể xác nhận bản sao sau khi xác minh nguồn, nội dung bảo vệ và biên nhận phù hợp, dù quyền thực thi ban đầu nay đã hết hạn. Không có tác động mới trong trường hợp đó.

Với một yêu cầu tạo tác động mới, consumer phải áp dụng chính sách quyền tương ứng. Không dùng một biên nhận cũ cho một payload đã đổi số tiền, đối tượng hoặc người nhận.

Thời gian giữ inbox cần phù hợp cửa sổ giao lại và nhu cầu kiểm toán. Nếu xóa inbox sớm, bất biến hoặc biên nhận nghiệp vụ vẫn phải ngăn một tác động cũ bị tạo lại. Hết thời gian lưu bản sao kỹ thuật không làm phát sinh quyền thực hiện nghiệp vụ thêm lần nữa.

## 11. Xử lý từ chối, lỗi tạm thời và thông điệp không rõ kết quả

Mọi trường hợp xử lý thất bại không nên cùng đi vào một vòng retry.

| Tình huống | Quyết định điển hình | Điều phải giữ |
| --- | --- | --- |
| Không xác minh được nguồn hoặc tính toàn vẹn | Từ chối hoặc cách ly theo chính sách | Không tạo tác động; không tin metadata chưa được xác minh |
| Nguồn không được phép gửi loại hành động | Từ chối có kiểm toán | Không chuyển sang handler quyền mạnh hơn |
| Lệnh ngoài phạm vi đơn vị hoặc đối tượng | Từ chối | Không làm lộ thông tin đối tượng không được phép |
| Quyền đã hết hạn hoặc bị thu hồi | Kết quả bị từ chối theo chính sách | Retry không kéo dài quyền |
| Dịch vụ quyết định quyền không phản hồi | Giữ lỗi có thể thử lại hoặc chuyển xử lý có giới hạn | Không tự cho phép vì thiếu quyết định |
| Nghĩa vụ đã hoàn tất | Xử lý bản sao theo bằng chứng | Không tạo thêm tác động |
| Gọi bên ngoài bị timeout sau khi đã gửi | Đối soát kết quả | Không giả định chắc chắn chưa thực hiện |

Việc từ chối một lệnh có thể là kết quả nghiệp vụ cuối cùng cần báo lại cho hệ thống yêu cầu. Cần phân biệt kết quả đó với việc thông điệp không thể xác thực hoặc không thể phân tích.

Nếu transaction xử lý bị rollback, bản ghi từ chối trong cùng transaction cũng có thể mất. Đường ghi nhận từ chối hoặc cách ly phải được thiết kế phù hợp để có bằng chứng bền vững mà không tạo tác động nghiệp vụ trái phép.

Quyết định xác nhận, từ chối giao lại hoặc chuyển DLQ phụ thuộc giao thức broker. Dù dùng cơ chế nào, không nên loại bỏ thông điệp cần điều tra trước khi bằng chứng tối thiểu và trạng thái xử lý đã được lưu theo chính sách.

Khi có lỗi phân quyền tạm thời, retry cần ngân sách và thời hạn. Một lệnh hết hạn trong lúc chờ phải được xét lại theo thời gian hiện tại; thời gian retry không làm đứng đồng hồ quyền.

## 12. Phát lại, DLQ và công cụ vận hành

DLQ là nơi giữ thông điệp không xử lý được. Nó không cấp thêm thẩm quyền cho thông điệp.

Một đường phát lại cần giữ hoặc xác minh được:

- Nguồn ban đầu và bằng chứng của nội dung cần bảo vệ.
- Handler, đơn vị và đối tượng đích.
- Định danh nghĩa vụ và các khóa chống trùng liên quan.
- Quyền hoặc căn cứ nghiệp vụ phải dùng khi thực thi lại.
- Lý do phát lại, người thực hiện và phê duyệt bổ sung nếu cần.

Thông điệp có thể được bọc trong một envelope của công cụ vận hành. Consumer phải phân biệt danh tính công cụ phát lại với căn cứ thẩm quyền ban đầu. Việc công cụ có quyền đọc DLQ không có nghĩa mọi payload bên trong đều được thi hành bằng quyền quản trị.

Nếu nội dung nghiệp vụ được sửa, đó là một lệnh mới hoặc một phiên bản cần xem xét lại theo chính sách. Không giữ chữ ký, phê duyệt hoặc biên nhận cũ cho nội dung đã thay đổi.

Quyền xem payload, quyền chọn phát lại và quyền tạo tác động là các quyền riêng. Giao diện hỗ trợ cần kiểm tra theo đơn vị và đối tượng, thay vì cho mọi người trực vận hành xem hoặc phát lại toàn bộ hệ thống.

Phát lại hàng loạt cũng phải có kiểm soát tác động và kết quả từng nghĩa vụ. Không để một thao tác vận hành vô tình tạo hàng nghìn tác động mới chỉ vì các bản ghi inbox đã hết hạn lưu.

## 13. Quyền của consumer đối với broker và dữ liệu

Ngoài quyết định nghiệp vụ, cần hạn chế quyền kỹ thuật của consumer:

- Dùng danh tính dịch vụ có thể truy vết, tách theo nhu cầu triển khai và ranh giới tin cậy phù hợp.
- Chỉ cho đọc các nguồn và tham gia các nhóm nhận hoặc hàng đợi được phép theo cơ chế của broker.
- Giới hạn khả năng tạo nguồn thông điệp, sửa cấu hình định tuyến, quản trị quyền hoặc ghi vào nguồn khác.
- Hạn chế quyền cơ sở dữ liệu và API đích theo vai trò dịch vụ.
- Kiểm soát ai có thể truy cập log, DLQ, thông tin kết nối và bí mật của consumer.

Tên topic, queue hoặc group không tự chứng minh thẩm quyền của nội dung. Cũng không nên xây chính sách chỉ từ một phần tên do người gọi chọn, chẳng hạn “topic chứa tenant-17 thì được tác động mọi dữ liệu của tenant-17”.

Với dữ liệu đa đơn vị, lựa chọn kiến trúc có thể là tách nguồn, tách consumer hoặc dùng một dịch vụ trung tâm được cấp phạm vi rõ. Dù chọn cách nào, phải kiểm soát cả việc đọc payload lẫn tác động. Một bộ lọc trong handler không thu hồi được dữ liệu đã bị consumer đọc hoặc ghi vào log.

Thu hồi danh tính consumer cần được phối hợp với thông điệp đang xử lý, quyền kết nối và khả năng gọi đích. Dừng nhận thông điệp mới chưa chắc dừng một thao tác bên ngoài đang chạy; cần hiểu giới hạn của từng cơ chế.

## 14. Giữ ngữ cảnh quyền qua các bước xử lý

### 14.1. Không để ngữ cảnh của thông điệp này rò sang thông điệp khác

Consumer có thể xử lý đồng thời nhiều đơn vị trên cùng tiến trình. Một biến toàn cục hoặc `ThreadLocal` không được dọn đúng cách có thể khiến thông điệp sau chạy dưới phạm vi đơn vị của thông điệp trước.

Ưu tiên truyền ngữ cảnh quyền bất biến theo từng lần gọi. Nếu framework dùng ngữ cảnh theo luồng hoặc theo tác vụ bất đồng bộ, cần bảo đảm thiết lập, truyền và giải phóng đúng vòng đời. Không suy ra đơn vị hiện tại từ một giá trị được giữ lại sau lần xử lý cũ.

### 14.2. Không biến việc gửi tiếp thành chuyển toàn bộ quyền

Consumer A có thể gọi dịch vụ B hoặc phát một lệnh tiếp theo. Quyền của A trong bước hiện tại không tự áp dụng cho mọi bước tiếp theo.

Dịch vụ B cần xác định nguồn có thẩm quyền, phạm vi đối tượng và căn cứ hành động của riêng nó. Nếu chuyển quyền ủy nhiệm, quyền đó cần dành cho B và giới hạn theo đúng mục đích; không gửi một thông tin vai trò tổng quát như `ADMIN` để B tự tin tưởng.

Một sự kiện `RefundApproved` có thể làm phát sinh nghĩa vụ chi trả theo chính sách dịch vụ. Handler chi trả phải xác minh phê duyệt và nghĩa vụ tương ứng; không cho phép bất kỳ nguồn nào gửi sự kiện cùng tên để chuyển tiền.

### 14.3. Kiểm soát thứ tự và trạng thái theo ngữ nghĩa

Thông điệp có thể đến chậm, lặp hoặc sai thứ tự. Một lệnh trên phiên bản đối tượng cũ có thể phải bị từ chối. Một sự kiện lịch sử hợp lệ lại có thể vẫn cần được ghi nhận hoặc đối soát.

Không áp dụng cùng một quy tắc “phiên bản khác hiện tại thì bỏ” cho mọi loại thông điệp. Cần xác định handler đang cập nhật trạng thái hiện hành, xử lý nghĩa vụ hay xây dựng lịch sử.

Dùng phiên bản, định danh nghĩa vụ và máy trạng thái phù hợp. Thời gian do payload tự khai hoặc thứ tự nhận của worker không phải bằng chứng đủ để ghi đè dữ liệu đã mới hơn.

## 15. Audit và bằng chứng quyết định

Một bản ghi quyết định hữu ích thường bao gồm:

- Handler và danh tính consumer thực thi.
- Nguồn đã xác minh, `messageId`, `operationId` và định danh lần xử lý.
- Loại thông điệp, phiên bản schema và phiên bản chính sách liên quan.
- Chủ thể khởi tạo, quyền cấp hoặc căn cứ nghĩa vụ hệ thống.
- Đơn vị, đối tượng, hành động và giới hạn đã được kiểm tra.
- Thời điểm quyết định, kết quả cho phép hoặc từ chối và mã lý do có cấu trúc.
- Kết quả nghiệp vụ hoặc liên kết đến biên nhận và sự kiện đã lưu.

Không ghi token, bí mật kết nối, toàn bộ thông tin thanh toán hoặc payload nhạy cảm chỉ để tiện điều tra. Có thể dùng định danh và dấu vân tay nội dung được chuẩn hóa phù hợp để đối chiếu.

Với thông điệp chưa xác minh, các chuỗi tự khai phải được đánh dấu đúng nguồn gốc và giới hạn độ dài. Không để dữ liệu đó giả mạo danh tính trong log, chèn nội dung điều khiển hoặc làm tăng vô hạn số nhãn theo dõi.

Cảnh báo nên giúp phát hiện các mẫu như nhiều yêu cầu chéo đơn vị, lặp cùng ID với nội dung khác, dùng quyền hết hạn hoặc một nguồn cố gửi loại hành động ngoài phạm vi. Cảnh báo hỗ trợ phát hiện; quyết định chặn vẫn phải nằm ở đường thực thi.

## 16. Tình huống xuyên suốt: phê duyệt hoàn tiền qua hàng đợi

Giả sử `user-31` được cấp quyền phê duyệt yêu cầu hoàn tiền `refund-208` của `tenant-17`, có hạn mức và yêu cầu độc lập với người tạo yêu cầu.

1. API tiếp nhận xác minh người dùng và tạo lệnh gắn với quyền cấp, đối tượng và phiên bản cần duyệt. Nó không cho người dùng tự chọn vai trò hoặc đơn vị ngoài phạm vi.
2. Nguồn phát được phép đưa lệnh tới consumer phê duyệt. Bằng chứng nguồn và nội dung được giữ theo giao thức đã định.
3. Consumer xác minh nguồn, loại thông điệp và đích. Nó lấy quyền cấp và dữ liệu hoàn tiền từ nguồn có thẩm quyền.
4. Trong phạm vi đồng bộ phù hợp, consumer kiểm tra quyền hiện tại, số tiền, đối tượng, phê duyệt, phân tách nhiệm vụ và trạng thái.
5. Consumer ghi kết quả phê duyệt, biên nhận nghĩa vụ, audit, outbox và inbox theo transaction đã chọn.
6. Nếu tiến trình chết sau commit nhưng trước xác nhận broker, bản giao lại được nhận diện và không tạo thêm lần phê duyệt.
7. Nếu một lệnh có ID mới vẫn nhắm cùng nghĩa vụ, ràng buộc nghiệp vụ ngăn tác động trùng.
8. Nếu quyền đã bị thu hồi trước điểm kiểm tra có hiệu lực, lệnh bị từ chối. Consumer không chuyển sang dùng quyền quản trị của chính nó để tiếp tục.
9. Khi một dịch vụ khác xử lý nghĩa vụ chi trả, nó xác minh căn cứ phê duyệt và bất biến chi trả riêng, không chỉ tin tên sự kiện.

Nếu thông điệp bị đưa vào DLQ rồi phát lại sau nhiều giờ, quyền và trạng thái cần được đánh giá theo mô hình của lệnh. Người vận hành không thể làm quyền hết hạn sống lại bằng cách bấm “replay”.

## 17. Kiểm thử phân quyền của consumer

Kiểm thử cần quan sát cả quyết định, dữ liệu nghiệp vụ, hạn mức, inbox, outbox và biên nhận. Một mã lỗi hoặc log từ chối không chứng minh rằng tác động chưa xảy ra.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Dịch vụ không có quyền đọc nguồn | Broker chặn theo chính sách áp dụng |
| Payload tự khai nguồn hoặc vai trò quản trị | Không được tin nếu thiếu căn cứ đã xác minh |
| Nguồn hợp lệ gửi loại hành động ngoài phạm vi | Bị từ chối trước tác động |
| Sửa đích nhận hoặc trường ảnh hưởng quyền | Không vượt kiểm tra toàn vẹn và ràng buộc đích |
| Đổi đơn vị hoặc ID đối tượng trong lệnh | Không tác động chéo đơn vị hoặc đối tượng ngoài quyền |
| Đơn đúng phạm vi nhưng người nhận tiền bị thay | Bị chặn bằng kiểm tra tham số và quan hệ nghiệp vụ |
| Quyền hết hạn trong lúc chờ hàng đợi | Lần thực thi mới bị từ chối theo chính sách |
| Thu hồi cạnh tranh với transaction thực thi | Kết quả tuân điểm quyết định đã công bố |
| Người yêu cầu tự phê duyệt khi chính sách cấm | Không tạo kết quả phê duyệt hợp lệ |
| Hai bản giao cùng thông điệp chạy đồng thời | Một tác động, biên nhận và hạn mức nhất quán |
| Cùng ID nhưng nội dung khác | Xử lý xung đột, không dùng kết quả cũ cho nội dung mới |
| Hai ID khác nhau cho cùng nghĩa vụ | Không tạo tác động nghiệp vụ trùng |
| Tiến trình chết sau commit trước ACK | Bản giao lại không thực hiện lần nữa |
| Quyền hiện tại mất nhưng bản sao đã hoàn tất được giao lại | Không thực thi mới; xử lý bản sao theo bằng chứng phù hợp |
| Dịch vụ phân quyền tạm thời không phản hồi | Không tự cho phép hoặc nâng quyền consumer |
| Phát lại DLQ với payload đã sửa | Không giữ căn cứ quyền hoặc phê duyệt của nội dung cũ |
| Consumer xử lý xen kẽ hai đơn vị | Không rò ngữ cảnh quyền giữa các lần gọi |
| Nguồn sự kiện không có thẩm quyền khẳng định sự thật | Không tạo nghĩa vụ chỉ từ tên sự kiện |
| Người dùng mất quyền sau nghiệp vụ đã commit | Nghĩa vụ hệ thống hợp lệ vẫn được xử lý theo mô hình riêng |
| Gọi bên ngoài timeout sau khi đã thực hiện | Đối soát và chống lặp, không tùy tiện gửi một lệnh mới |

Với cạnh tranh thu hồi, dùng điểm đồng bộ để chủ động tạo thứ tự khóa, quyết định và commit. Với hết hạn, dùng nguồn thời gian có thể điều khiển và kiểm tra trước hạn, đúng hạn, sau hạn.

Với sự kiện đã commit, kiểm thử cả bằng chứng sự thật lẫn nghĩa vụ tiếp theo. Với lệnh ủy quyền, kiểm thử quyền hiện tại và phạm vi. Hai nhóm này cần các kỳ vọng khác nhau; gộp chúng vào một ca “user có role” sẽ bỏ sót quyết định quan trọng.

## 18. Những quyết định cần rõ trước khi triển khai

Một thiết kế consumer đủ cụ thể cần trả lời được:

1. Consumer được đọc nguồn nào và dữ liệu của những đơn vị nào?
2. Nguồn nào được phép gửi từng loại thông điệp và phạm vi?
3. Mỗi handler xử lý lệnh ủy quyền, sự kiện đã commit hay nghĩa vụ hệ thống?
4. Danh tính, quyền cấp và các trường ảnh hưởng quyết định được xác minh thế nào?
5. Quyền theo đối tượng, tham số, phê duyệt và trạng thái được kiểm tra tại đâu?
6. Thu hồi hoặc hết hạn ảnh hưởng thế nào đến lệnh chờ và lệnh đang chạy?
7. Inbox và khóa nghĩa vụ nghiệp vụ ngăn những kiểu trùng nào?
8. Từ chối, lỗi tạm thời và kết quả chưa rõ được xử lý và lưu bằng chứng ra sao?
9. Phát lại hoặc sửa thông điệp cần quyền, phiên bản và phê duyệt nào?
10. Dịch vụ đích kiểm tra gì khi consumer tạo tác động ở một hệ thống khác?

Phân quyền cho consumer bảo vệ chuỗi thực thi từ nguồn thông điệp tới tác động cuối cùng. Mỗi bước cần căn cứ thẩm quyền rõ, phạm vi đối tượng có thể kiểm tra và cơ chế giữ bất biến khi thông điệp đến muộn, bị giao lại hoặc được phát lại bằng công cụ vận hành.

