# Action authorization: kiểm soát quyền theo hành động nghiệp vụ

## 1. Mục tiêu bài học

Trong chương **Authorization Rules** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **action authorization** là việc quyết định một chủ thể có được thực hiện **một hành động nghiệp vụ cụ thể** trên đối tượng và trong ngữ cảnh đang xét hay không.

Câu hỏi trung tâm là:

> Chủ thể này có được thực hiện hành động này trên đối tượng này, với các giá trị và điều kiện hiện tại không?

Ví dụ, một nhân viên có thể xem yêu cầu hoàn tiền nhưng không được duyệt; có thể duyệt yêu cầu trong hạn mức nhưng không được phát lệnh chi trả; có thể hủy bản nháp do mình tạo nhưng không được hủy một khoản đã thanh toán.

Sau bài học, bạn có thể:

- Xác định hành động theo ý nghĩa nghiệp vụ thay vì chỉ theo HTTP method hoặc quyền CRUD.
- Kết hợp quyền hành động với phạm vi đối tượng, tenant, tham số và điều kiện bắt buộc.
- Tách quyết định cấp quyền khỏi các tiền điều kiện nghiệp vụ mà vẫn thực thi đầy đủ cả hai.
- Đặt kiểm tra trong luồng xử lý để tránh bỏ qua qua API khác, cập nhật trường hoặc xử lý đồng thời.
- Kiểm thử quyền bằng các trường hợp đổi hành động, đổi đối tượng, sửa tham số, gửi lại và gọi hàng loạt.

## 2. Đăng nhập, thấy dữ liệu và được hành động là những câu hỏi khác nhau

| Câu hỏi | Ví dụ | Điều chưa được chứng minh |
|---|---|---|
| Authentication: người gọi là ai? | Danh tính của nhân viên Lan đã được xác thực | Lan được duyệt hoàn tiền |
| Object access: có được tiếp cận đối tượng này không? | Lan được xem refund R trong phạm vi được giao | Lan được sửa, hủy hoặc duyệt R |
| Action authorization: có quyền cho hành động này không? | Lan được approve R trong hạn mức | R đang ở trạng thái có thể approve |
| Business preconditions: có thực hiện được lúc này không? | R đang SUBMITTED và chưa có quyết định | Nội dung có thể vi phạm quy tắc số tiền nếu chưa kiểm tra |
| Invariants: trạng thái sau có còn đúng không? | Hạn mức hoàn tiền không bị vượt | Các hành động khác cũng đã được kiểm soát quyền |

Một request chỉ được tạo hiệu ứng nghiệp vụ khi đáp ứng đầy đủ các lớp liên quan.

Có role APPROVER cũng chưa đủ: reviewer có thể thuộc tenant khác, ngoài phạm vi đối tượng, thiếu hạn mức hoặc là chính người tạo bị chính sách cấm tự duyệt.

## 3. Hành động phải thể hiện ý định nghiệp vụ

### 3.1. Quyền CRUD thường quá rộng

Một API có thể dùng POST cho mọi command:

~~~text
POST /refunds
POST /refunds/{id}/submit
POST /refunds/{id}/approve
POST /refunds/{id}/cancel
POST /refunds/{id}/execute
~~~

Cùng là POST nhưng các hành động tạo nghĩa vụ và rủi ro khác nhau. Ngược lại, cùng một hành động approve có thể được gọi qua REST, GraphQL hoặc công cụ nội bộ.

Một tập quyền nghiệp vụ có thể là:

~~~text
REFUND_CREATE
REFUND_READ
REFUND_EDIT_DRAFT
REFUND_SUBMIT
REFUND_APPROVE
REFUND_REJECT
REFUND_CANCEL_PENDING
REFUND_EXECUTE
REFUND_EXPORT
~~~

Tên cụ thể tùy dự án. Điểm cần giữ là mỗi quyền tương ứng với một ý định đủ rõ để kiểm tra và audit.

### 3.2. “Được sửa” không đồng nghĩa “được duyệt”

Mẫu cập nhật tổng quát sau dễ mở đường vượt quyền:

~~~json
{
  "status": "APPROVED",
  "approvedBy": "another-user",
  "amount": 1000
}
~~~

Nếu endpoint PATCH chỉ kiểm tra REFUND_EDIT rồi bind toàn bộ payload vào entity, người được sửa bản nháp có thể thực hiện hành động approve qua trường status.

Các trường thể hiện quyết định nghiệp vụ như approvedBy, approvedAt, approvedAmount, paidAt và trạng thái chuyển bước cần do command tương ứng thiết lập.

DTO hẹp giúp giới hạn dữ liệu người gọi được quyết định. Ví dụ command approve chỉ nhận id, expectedVersion và idempotency key; số tiền được duyệt lấy từ revision đã lưu và được bảo vệ ở server.

### 3.3. Server xác định hành động thực sự sẽ chạy

Không cấp quyền dựa trên một trường action do client gửi rồi thực hiện một thao tác khác:

~~~text
Client khai action = READ
    → server kiểm tra quyền READ
    → payload hoặc nhánh xử lý lại thực hiện APPROVE
~~~

Nếu API nhận command type trong body, server phải ánh xạ nó vào tập hành động được hỗ trợ, kiểm tra đúng quyền và chỉ chạy đúng handler tương ứng. Giá trị không được nhận diện phải bị từ chối trước hiệu ứng.

Kiểm tra quyền phải gắn với hành động thực tế, không với nhãn thuận tiện mà người gọi có thể sửa.

## 4. Mô hình một quyết định cấp quyền

Có thể biểu diễn:

~~~text
Decision = authorize(subject, action, resource, context, parameters)
~~~

Trong đó:

- subject: danh tính đã xác thực và nguồn thẩm quyền liên quan.
- action: ý định nghiệp vụ được server xác định.
- resource: đối tượng hoặc phạm vi mục tiêu có thẩm quyền.
- context: tenant đang hoạt động, chính sách, delegation, thời gian và dữ liệu liên quan.
- parameters: các giá trị ảnh hưởng đến phạm vi hay mức độ của hành động.

Một chính sách minh họa:

~~~text
permit =
    activeSubject
    ∧ actionCapabilityGranted
    ∧ tenantMembershipValid
    ∧ objectScopeAllowed
    ∧ actionParametersAllowed
    ∧ mandatoryRestrictionsSatisfied
~~~

Sau đó:

~~~text
canExecute =
    permit
    ∧ currentBusinessPreconditions
    ∧ invariantCanBePreserved
~~~

Trạng thái có thể được dùng trong policy hoặc được kiểm tra như tiền điều kiện tại domain layer. Dù tổ chức mã theo cách nào, phải bảo đảm cả quyền lẫn điều kiện trạng thái đều được đánh giá trước khi tạo hiệu ứng.

### 4.1. Quyết định phải có cách xử lý khi thiếu dữ liệu

Kết quả nội bộ có thể phân biệt:

| Kết quả | Ý nghĩa | Hành vi tại điểm thực thi |
|---|---|---|
| Permit | Đủ căn cứ cấp quyền theo chính sách | Tiếp tục kiểm tra và thực hiện nghiệp vụ |
| Deny | Có căn cứ không cho phép | Không tạo hiệu ứng của hành động |
| Indeterminate | Thiếu dữ liệu hoặc không đánh giá được | Không mặc định thành Permit |

Ví dụ dịch vụ quyền không trả lời không có nghĩa actor được phép duyệt. Có thể trả lỗi tạm thời hoặc giữ công việc chờ xử lý, nhưng không cho luồng nghiệp vụ tiếp tục bằng một giá trị allow mặc định.

Cơ chế ngoại lệ, nếu sản phẩm cần, phải được đặc tả như một chính sách riêng; nó không nên xuất hiện do catch exception rồi trả true.

### 4.2. Ghép quyền không được làm mất ràng buộc bắt buộc

Một người có thể nhận quyền qua nhiều role. Chính sách cần nói rõ cách kết hợp chúng.

Trong ví dụ này, có bất kỳ nguồn cấp quyền hợp lệ nào có thể đáp ứng actionCapabilityGranted, nhưng mọi điều kiện bắt buộc như tenant, object scope, hạn mức và cấm tự duyệt vẫn phải đúng.

Không viết:

~~~text
hasRole(APPROVER) OR hasRole(ADMIN) OR passesAllBusinessRestrictions
~~~

Biểu thức đó cho phép một role làm mất hiệu lực các hạn chế còn lại. Quyền quản trị kỹ thuật không mặc nhiên là thẩm quyền duyệt hoặc chi tiền.

## 5. Ví dụ chính sách cho hoàn tiền

Giả sử hệ thống có các nhóm chức năng:

- Nhân viên hỗ trợ tạo và xử lý yêu cầu trong phạm vi được giao.
- Người duyệt có hạn mức và phạm vi phê duyệt riêng.
- Worker chi trả có danh tính dịch vụ và quyền thực thi giới hạn.
- Người kiểm tra có quyền báo cáo/xuất dữ liệu theo chính sách.

Đây là vai trò minh họa, không phải quy tắc áp dụng cho mọi doanh nghiệp.

| Hành động | Quyền và phạm vi cần có | Tiền điều kiện nghiệp vụ minh họa |
|---|---|---|
| CREATE | Quyền tạo trên payment/đơn hàng mục tiêu trong tenant | Payment đủ điều kiện mở yêu cầu; số tiền hợp lệ |
| READ | Quyền xem đối tượng và các trường tương ứng | Đối tượng tồn tại, chưa vượt chính sách truy cập/lưu trữ |
| EDIT_DRAFT | Quyền sửa đúng bản nháp, đúng tập trường | Đang DRAFT; revision/version còn khớp |
| SUBMIT | Quyền gửi yêu cầu trong phạm vi phụ trách | Đang DRAFT; dữ liệu bắt buộc đầy đủ |
| APPROVE | Quyền duyệt theo đối tượng, đủ hạn mức, không xung đột nhiệm vụ | Đang SUBMITTED; revision đúng; hạn mức hoàn tiền còn đủ |
| REJECT | Quyền từ chối theo chính sách reviewer | Đang SUBMITTED; lý do phù hợp |
| CANCEL_PENDING | Quyền hủy yêu cầu trước phê duyệt theo chính sách | Đang DRAFT/SUBMITTED và chưa có hiệu ứng chi trả |
| EXECUTE | Quyền dịch vụ cho bước chi trả của operation được giao | Đã có phê duyệt hợp lệ; số tiền và đối tượng khớp |
| EXPORT | Quyền xuất đúng tập dữ liệu, dòng và cột | Bộ lọc và dung lượng đáp ứng quy tắc sản phẩm |

Bảng chọn chính sách hủy hẹp để minh họa. Nếu sản phẩm cho phép hủy sau duyệt hoặc khi chi trả đang xử lý, cần command và quy trình riêng để giải quyết reservation, kết quả chưa rõ và nghĩa vụ hoàn tác.

### 5.1. Quyền tạo kiểm tra trên phạm vi đích

Khi CREATE, đối tượng refund chưa tồn tại. Không thể bỏ qua kiểm tra vì “chưa có resource”.

Resource để quyết định có thể là payment gốc, đơn hàng, tài khoản khách hàng hoặc tenant mục tiêu. Cần xác minh actor được tạo yêu cầu trên chính phạm vi đó và các liên kết được gửi là hợp lệ.

Không cho một người tạo refund trong tenant của mình nhưng trỏ paymentId sang tenant khác.

### 5.2. Quyền xem không tự bao gồm quyền xuất

Export thường truy cập nhiều đối tượng, nhiều trường và có thể đưa dữ liệu ra khỏi giao diện đang kiểm soát. Cần quyền hành động và phạm vi dữ liệu tương ứng.

Một người xem được một refund không mặc nhiên được tải toàn bộ refund của tổ chức. Lọc dòng và giới hạn cột cũng cần áp dụng với báo cáo, file tải xuống và truy vấn nền.

## 6. Dữ liệu dùng để cấp quyền phải có thẩm quyền

### 6.1. Không để người gọi tự khai chủ thể và phạm vi

Các trường như actorId, approvedBy, role hoặc isAdmin trong body không phải bằng chứng cấp quyền.

Server lấy chủ thể từ ngữ cảnh xác thực đã được kiểm chứng. Nếu người dùng chọn tenant đang làm việc, server phải xác nhận quyền thành viên và phạm vi tương ứng; tenantId trong URL hoặc body không tự cấp quyền thành viên.

Tương tự, amount trong request approve không được dùng làm số tiền để kiểm tra hạn mức nếu thao tác thực tế sẽ duyệt số tiền khác đang lưu trong refund.

Một lỗi điển hình:

~~~text
Client gửi amount = 1000.
Policy thấy 1000 nhỏ hơn hạn mức nên cho phép.
Handler approve số tiền thực tế 50000000 trong cơ sở dữ liệu.
~~~

Policy và handler phải nói về cùng một đối tượng, cùng revision và cùng tham số thực thi.

### 6.2. Role là một đầu vào, không phải toàn bộ quyết định

Một quyết định có thể dùng:

- Role và capability đã được xác thực.
- Quan hệ actor với đối tượng hoặc đơn vị.
- Hạn mức theo hành động.
- Assignment hoặc delegation còn hiệu lực.
- Danh tính người tạo/người hưởng lợi.
- Trạng thái, revision và phân loại đối tượng.
- Điều kiện ngữ cảnh được chính sách quy định.

RBAC có thể cung cấp quyền nền, các thuộc tính bổ sung giới hạn phạm vi, và quan hệ với đối tượng quyết định khả năng thao tác. Không bắt buộc phải chọn một mô hình duy nhất để diễn tả mọi điều kiện.

### 6.3. Actor thực tế và quyền được ủy nhiệm

Với thao tác thay mặt, cần giữ được người thực hiện thực tế, danh tính có hiệu lực và nguồn quyền được sử dụng.

Một delegation cho phép READ không tự cho phép APPROVE. Delegation cho một đối tượng hoặc một hạn mức không được mở rộng sang đối tượng khác hoặc số tiền lớn hơn.

Một service account gọi nội bộ cũng phải có quyền cho đúng hành động và phạm vi. Việc request đến từ mạng nội bộ chưa đủ làm căn cứ cho phép chi tiền.

## 7. Đặt kiểm tra tại điểm thực thi nghiệp vụ

### 7.1. Kiểm tra đầu vào và kiểm tra khi thực hiện

Gateway hoặc middleware có thể xác thực và kiểm tra quyền thô như “được truy cập nhóm API hoàn tiền”. Tầng ứng dụng/domain có dữ liệu để quyết định hành động cụ thể trên đối tượng cụ thể.

Một kiến trúc có thể tách:

~~~text
Authentication
    → xác định subject tin cậy

Application command handler
    → nạp đối tượng và dữ liệu cần thiết
    → yêu cầu quyết định quyền

Policy evaluator
    → tính Permit/Deny từ action, resource, context

Domain + repository
    → kiểm tra nghiệp vụ, ghi dữ liệu có bảo vệ concurrency

Audit/outbox
    → lưu bằng chứng và ý định hiệu ứng tiếp theo
~~~

Tên lớp và cách chia tùy dự án. Điều cần chứng minh là không có đường tạo hiệu ứng trước hoặc ngoài điểm kiểm tra.

UI có thể dùng allowedActions để hiển thị nút phù hợp. Danh sách này chỉ phản ánh một lần đánh giá; handler vẫn phải kiểm tra lại khi command đến.

### 7.2. Mọi đường vào phải có cùng ý nghĩa quyền

REFUND_APPROVE có thể được gọi từ:

- REST endpoint.
- GraphQL mutation.
- Công cụ quản trị.
- Batch job.
- Tích hợp nghiệp vụ.
- Luồng khôi phục sau lỗi.

Nên đưa chúng qua command hoặc dịch vụ nghiệp vụ được bảo vệ chung. Nếu có các đường thực thi riêng, phải có cùng quy tắc về quyền và bất biến tương ứng.

Một endpoint cũ vẫn cho phép cập nhật status có thể vô hiệu hóa endpoint approve mới dù endpoint mới được kiểm tra rất kỹ.

### 7.3. Java minh họa hành động approve

Mã dưới đây là phác thảo tầng ứng dụng với các repository và dịch vụ giả định. Nó không phải chương trình độc lập.

Giả định:

- actor chứa danh tính và tenant đang hoạt động đã được kiểm chứng.
- Refund thuộc payment cố định; mọi luồng ghi liên quan tuân thủ thứ tự khóa chung.
- Policy facts được nạp từ nguồn có thẩm quyền theo cam kết độ mới của hệ thống.
- Các repository, audit và outbox cùng tham gia một transaction.
- Exception bắt buộc làm rollback; transaction chỉ trả thành công ra ngoài sau commit.

~~~java
ApprovalResult approve(AuthenticatedActor actor, ApproveCommand cmd) {
    return transactions.required(() -> {
        var route = refunds.findRoutingInfo(
                actor.activeTenantId(), cmd.refundId())
                .orElseThrow(NotFound::new);

        var payment = payments.lockForUpdate(
                actor.activeTenantId(), route.paymentId());
        var refund = refunds.lockForUpdate(
                actor.activeTenantId(), cmd.refundId());
        requireSameParentAndTenant(refund, payment);

        var facts = policyFacts.requireFor(
                actor, Action.REFUND_APPROVE, refund);

        authorization.requirePermit(
                actor, Action.REFUND_APPROVE, refund, facts);

        requireVersion(refund, cmd.expectedVersion());
        requireState(refund, SUBMITTED);
        refundRules.requireApprovable(refund, payment);

        long amount = refund.requestedAmountMinor();
        var decisionId = decisionIds.next();

        payment.reserveExact(amount);
        refund.approve(
                actor.personId(), amount,
                clock.instant(), decisionId);

        payments.save(payment);
        refunds.save(refund);
        audit.insertApproval(
                actor, refund, decisionId, facts.policyVersion());
        outbox.insertRefundApproved(decisionId, refund);

        return ApprovalResult.from(refund);
    });
}
~~~

Trong luồng mẫu:

- Action được handler xác định cố định là REFUND_APPROVE.
- Policy kiểm tra quyền duyệt, phạm vi, hạn mức và hạn chế như cấm tự duyệt trên chính refund được nạp.
- expectedVersion chặn việc quyết định trên revision đã thay đổi.
- refundRules kiểm tra trạng thái tiền tệ, số tiền và hạn mức hoàn còn lại.
- Khóa payment bảo vệ tài nguyên chung, không chỉ trạng thái riêng của refund.
- Các phương thức domain chỉ sửa những trường mà command được phép tác động.
- Chưa có lời gọi chi trả bên ngoài; approve chỉ tạo trạng thái và nghĩa vụ nội bộ theo hợp đồng.

Policy cho phép không thay thế kiểm tra nghiệp vụ. Ngược lại, refund hợp lệ về số tiền cũng không thay thế quyết định cấp quyền.

### 7.4. Vì sao kiểm tra bên ngoài transaction có thể sai?

Ví dụ:

~~~text
T1: Policy đọc amount = 10 triệu và cho phép.
T2: Một command khác đổi amount thành 100 triệu.
T1: Handler approve amount hiện tại mà không kiểm tra version.
~~~

T1 đã sử dụng một quyết định quyền cho dữ liệu khác với dữ liệu được duyệt.

Cần bảo vệ các dữ kiện ảnh hưởng đến quyết định bằng cơ chế phù hợp: khóa, version, cập nhật có điều kiện hoặc giao thức nhất quán khác. Quyết định có thể phải được ràng buộc với action, objectId, revision và các tham số trọng yếu.

Một transaction cục bộ không tự khóa được dịch vụ quyền bên ngoài. Nếu hạn mức hoặc quyền có thể thay đổi đồng thời, phải định nghĩa thời điểm có hiệu lực và cơ chế đọc/kiểm chứng đáp ứng cam kết đó.

Không tuyên bố thu hồi quyền tức thời nếu hệ thống thực tế chỉ kiểm tra claim hoặc cache còn hiệu lực trong một khoảng thời gian.

## 8. Quyền theo trường và tham số của hành động

### 8.1. Cùng một action có thể có phạm vi khác nhau

Ví dụ với EDIT_DRAFT:

~~~text
Nhân viên hỗ trợ:
  được sửa lý do và tài liệu bổ sung
  không được đổi paymentId hoặc người hưởng lợi tùy ý

Nhân viên điều chỉnh nghiệp vụ:
  có thể sửa số tiền trong giới hạn và trạng thái cho phép
  phải tạo revision/audit tương ứng
~~~

Không chỉ kiểm tra “được edit đối tượng” rồi áp dụng mọi trường trong payload.

Có thể dùng command riêng cho các ý định quan trọng, như ChangeRefundAmount, thay vì một update tổng quát ngày càng nhiều ngoại lệ.

### 8.2. Tính toán giá trị có thẩm quyền ở server

Với giá, chiết khấu, phí, hạn mức hoặc số tiền duyệt:

- Phân biệt giá trị client được đề xuất và giá trị server chấp nhận.
- Xác thực nguồn dữ liệu và quan hệ nghiệp vụ.
- Kiểm tra quyền đối với đúng giá trị sẽ được lưu/thực hiện.
- Gắn quyết định với revision chứa các giá trị đó.
- Không cho thay đổi trường khác để gián tiếp mở rộng hiệu ứng.

Ví dụ actor được đổi lý do hoàn không có nghĩa được thay paymentId sang giao dịch có giá trị cao hơn, dù amount giữ nguyên.

### 8.3. Giới hạn số lượng và tập mục tiêu

Một quyền điều chỉnh một đối tượng không mặc nhiên cho phép điều chỉnh một nghìn đối tượng hoặc toàn bộ tenant.

Nếu chính sách có hạn mức theo lần thực thi, ngày hoặc nhóm đối tượng, phải đánh giá trên phạm vi tương ứng và bảo vệ bộ đếm khi chạy đồng thời.

Kiểm tra từng phần tử độc lập không tự bảo đảm hạn mức tổng. Ngược lại, tổng hợp lệ cũng không chứng minh actor có quyền trên mọi phần tử.

## 9. Batch, bất đồng bộ, idempotency và cache

### 9.1. Quyền trong thao tác hàng loạt

Với batch approve, cần:

1. Xác định đầy đủ tập mục tiêu thực sự sẽ xử lý.
2. Kiểm tra action và scope cho từng đối tượng.
3. Kiểm tra hạn mức/tập ràng buộc tổng nếu có.
4. Quy định toàn bộ thành công hoặc kết quả theo từng phần tử.
5. Ghi trạng thái, audit và receipt theo đúng hợp đồng đó.

Không chỉ authorize phần tử đầu tiên rồi dùng cùng kết quả cho cả batch. Cũng không âm thầm bỏ phần tử không có quyền rồi trả thông báo “tất cả đã duyệt”.

Nếu API hỗ trợ kết quả từng phần tử, thông tin trả về vẫn phải tuân thủ chính sách không tiết lộ đối tượng ngoài quyền.

### 9.2. Công việc chạy sau khi request đã kết thúc

Một job cần lưu ý định, mục tiêu, revision và nguồn thẩm quyền phù hợp. Worker kiểm tra điều kiện thực thi theo chính sách dành cho công việc bất đồng bộ, thay vì sử dụng vô hạn một giá trị allowed=true từ lúc tạo job.

Cần xác định rõ:

- Quyền nào được đánh giá khi chấp nhận công việc.
- Điều kiện nào phải được kiểm tra lại khi thực thi.
- Worker dùng danh tính dịch vụ và phạm vi ủy nhiệm nào.
- Nếu người khởi tạo mất quyền, công việc đang chờ được tiếp tục hay dừng theo quy tắc nào.

Ghi nhận một kết quả thanh toán thực tế đã xảy ra khác với xin phép tạo khoản thanh toán mới. Việc người khởi tạo bị khóa không cho phép bỏ qua sự thật tài chính; hệ thống phải ghi nhận rồi xử lý nghĩa vụ theo trạng thái phù hợp.

### 9.3. Replay cũng phải kiểm tra quyền truy cập kết quả

Idempotency bảo vệ khỏi hiệu ứng lặp; nó không cấp quyền.

Receipt nên được giới hạn theo tenant, subject/phạm vi được thiết kế, action và key, đồng thời gắn với fingerprint của command. Cần phân biệt cùng ý định với cùng key nhưng khác object hoặc tham số.

Khi trả receipt cũ, kiểm tra người gọi hiện được xem kết quả đó. Không trả dữ liệu chỉ vì họ biết key.

Nếu receipt chỉ trả kết quả của command đã hoàn tất, không tạo hiệu ứng mới. Nếu hệ thống thật sự tiếp tục một công việc chưa hoàn tất, áp dụng thêm các điều kiện thực thi hiện hành theo hợp đồng công việc.

### 9.4. Cache quyết định quyền cần có phạm vi và hiệu lực

Một cache key chỉ có userId và role có thể áp dụng nhầm quyền giữa tenant, action hoặc đối tượng.

Những dữ kiện ảnh hưởng đến quyết định có thể gồm action, tenant, resource, revision, policy version, phiên bản quyền, delegation và tham số. Cách cache phải phản ánh các phụ thuộc đó hoặc chỉ cache những dữ kiện ổn định hơn rồi tính lại quyết định cuối.

Cần có quy tắc hết hạn/vô hiệu hóa phù hợp với yêu cầu thu hồi quyền. TTL không tự bảo đảm quyền bị thu hồi có hiệu lực ngay.

Danh sách allowedActions đã gửi cho UI cũng là một dạng ảnh chụp; không được xem nó là giấy phép thực hiện vô thời hạn.

## 10. Từ chối quyền phải ngăn được hiệu ứng

### 10.1. Không có thay đổi nghiệp vụ của hành động bị chặn

Một request bị từ chối trước khi thực hiện không được để lại:

- Refund chuyển trạng thái.
- Reservation hoặc hạn mức bị tiêu thụ.
- Quyết định approve/reject thành công.
- Outbox yêu cầu chi trả của hành động bị chặn.
- File export hoặc job có thể tiếp tục thực hiện thay người gọi.
- Thông tin nhạy cảm được trả ra ngoài phạm vi được phép.

Security log về lần thử có thể được ghi để giám sát. Nó khác với audit chứng minh một hành động nghiệp vụ đã thành công.

Không tạo job trước rồi mới kiểm tra người dùng có quyền tạo job hay không. Worker có thể đã bắt đầu xử lý trong khoảng trống đó.

### 10.2. Phân biệt lỗi quyền và xung đột nghiệp vụ

Các loại kết quả nên được phân biệt trong hợp đồng API:

| Tình huống | Cách biểu đạt minh họa |
|---|---|
| Chưa có xác thực được chấp nhận | Yêu cầu xác thực, thường dùng 401 theo cơ chế API |
| Đã xác thực nhưng không được phép thực hiện action | Từ chối quyền, thường dùng 403 |
| Đối tượng không tồn tại hoặc không được phép tiết lộ sự tồn tại | Có thể dùng 404 theo chính sách nhất quán |
| Có quyền nhưng version/trạng thái đã đổi | Xung đột nghiệp vụ, có thể dùng 409 |
| Không đánh giá được quyền do phụ thuộc lỗi | Lỗi xử lý/tạm thời phù hợp, không mặc định cho phép |

Đây là ví dụ thiết kế hợp đồng, không phải yêu cầu mọi lỗi nghiệp vụ phải có cùng một mã.

Không trả chi tiết như tên tenant khác, số tiền hoặc trạng thái nội bộ cho người không có quyền biết đối tượng. Lý do đầy đủ có thể được ghi nội bộ với quyền truy cập phù hợp.

### 10.3. Permit và “đã thực hiện” là hai sự kiện khác nhau

Policy có thể trả Permit nhưng transaction sau đó rollback vì version xung đột hoặc không còn hạn mức hoàn tiền.

Audit cần phân biệt:

~~~text
đánh giá quyền cho phép
command được chấp nhận
thay đổi nghiệp vụ đã commit
hiệu ứng ngoài hệ thống được xác nhận
~~~

Không dùng một dòng log “authorized” làm bằng chứng khoản hoàn đã được chi trả. Ngược lại, thiếu response tới client không chứng minh command chưa commit.

## 11. Kiểm thử quyền theo hành động

### 11.1. Xây dựng ma trận kiểm thử

Một cách tổ chức là chọn các chiều độc lập:

~~~text
Subject:
  có quyền / thiếu quyền / bị vô hiệu hóa

Action:
  read / edit / submit / approve / execute / export

Resource:
  đúng scope / cùng tenant nhưng ngoài scope / tenant khác

Parameters:
  hợp lệ / vượt hạn mức / thay trường không được phép

State/version:
  phù hợp / không phù hợp / dữ liệu cũ

Context:
  trực tiếp / delegation / service / dữ liệu quyền không sẵn sàng
~~~

Không cần kiểm thử mù mọi tích Descartes. Chọn các cặp có khả năng phát hiện đường vượt quyền và các ranh giới quan trọng của chính sách.

### 11.2. Ma trận tình huống lạm dụng

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Có READ nhưng gọi APPROVE | Bị từ chối; không đổi trạng thái hay reservation |
| Có EDIT_DRAFT rồi gửi status=APPROVED | Không tạo được hiệu ứng approve qua cập nhật trường |
| Có APPROVE nhưng gọi EXECUTE | Không được chi trả chỉ nhờ quyền duyệt |
| Là owner của request và có role reviewer | Vẫn bị chặn nếu chính sách cấm tự duyệt |
| Đổi refundId sang đối tượng cùng tenant nhưng ngoài scope | Không truy cập/thao tác ngoài phạm vi |
| Đổi tenantId trong URL/body | Không tự có quyền trong tenant mới |
| CREATE trỏ paymentId ngoài quyền | Không tạo liên kết hoặc yêu cầu hoàn trái phép |
| Gửi amount nhỏ trong approve nhưng dữ liệu lưu có số tiền lớn | Policy đánh giá số tiền thực sự sẽ duyệt |
| Đổi trường paymentId, người hưởng lợi hoặc approvedBy qua DTO tổng quát | Không sửa được dữ liệu ngoài quyền hành động |
| Gửi command/action không được hỗ trợ | Từ chối trước hiệu ứng |
| Gọi endpoint cũ hoặc GraphQL thay endpoint chính | Cùng quy tắc quyền vẫn được áp dụng |
| Batch có một đối tượng ngoài quyền | Hành vi đúng hợp đồng toàn bộ/từng phần; không lặng lẽ thông qua |
| Export bằng quyền chỉ đủ xem một đối tượng | Không lấy được tập dữ liệu rộng hơn hoặc cột ngoài quyền |
| Cache đã có Permit cho tenant/action khác | Không áp dụng nhầm quyết định |
| Quyền hoặc delegation hết hiệu lực | Xử lý đúng cam kết độ mới/thu hồi đã đặc tả |
| Dịch vụ quyền không trả lời | Không có hiệu ứng do mặc định allow |
| Hai command cạnh tranh làm thay số tiền/version | Không dùng Permit của dữ liệu cũ cho dữ liệu mới |
| Retry cùng key sau commit | Không thêm decision, reservation hoặc hiệu ứng chi trả |
| Người khác biết idempotency key | Không đọc receipt hoặc thực thi ngoài quyền |
| Worker nhận job ngoài phạm vi được giao | Không thực hiện chỉ vì message đến từ hàng đợi nội bộ |

### 11.3. Kiểm thử phải quan sát dữ liệu sau khi command kết thúc

Ví dụ: actor chỉ có REFUND_READ cố approve một refund SUBMITTED.

Một kiểm thử có ý nghĩa kiểm tra:

~~~text
Trước:
  refund = SUBMITTED
  reserved của payment = R
  chưa có decision/outbox của lần thử

Thực thi:
  gọi hành động approve với actor chỉ có READ

Sau:
  response thể hiện từ chối theo hợp đồng
  refund vẫn SUBMITTED
  reserved vẫn R
  không có approval decision mới
  không có approval outbox mới
  không có lệnh chi trả
~~~

Đọc lại qua transaction mới để xác nhận trạng thái bền vững. Một unit test chỉ mock authorization rồi kiểm tra nó được gọi không chứng minh endpoint thật sự không có đường ghi trước khi kiểm tra.

Với kiểm thử bị từ chối, security log có thể xuất hiện đúng thiết kế; không gộp nó vào điều kiện “không có audit thành công”.

### 11.4. Kiểm thử theo tham số thực sự được thực hiện

Giả sử Hùng được duyệt tối đa 30 triệu VND và có scope đúng đối tượng. Refund lưu số tiền 50 triệu VND.

Client gửi:

~~~json
{
  "expectedVersion": 7,
  "amount": 1000
}
~~~

API approve mẫu không cho client quyết định amount. Kết quả phù hợp là từ chối trường không hỗ trợ hoặc bỏ qua nó theo hợp đồng đã công bố, rồi đánh giá quyền trên 50 triệu.

Không được duyệt 50 triệu vì đã authorize 1000. Không được âm thầm đổi số tiền thành 1000 để đi qua hạn mức mà không có command sửa nội dung hợp lệ.

Kiểm thử thêm đúng tại ranh giới hạn mức và ngay trên ranh giới. Với nhiều currency, dùng chính sách quy đổi đã xác định thay vì chỉ đổi ký hiệu tiền tệ của cùng một con số.

### 11.5. Kiểm thử quyền và concurrency cùng nhau

Tạo một refund 20 triệu ở version 7, Hùng có hạn mức 30 triệu.

Điều phối hai command qua các transaction độc lập:

~~~text
Command A: Hùng approve theo version 7.
Command B: Một actor hợp lệ sửa refund thành 50 triệu,
           nếu trạng thái và chính sách cho phép sửa.
~~~

Kết quả phải tương ứng với một thứ tự hợp lệ:

- B thắng: dữ liệu/version mới được thấy và A không thể dùng quyết định cũ để duyệt 50 triệu.
- A thắng: B không được ghi đè nội dung đã duyệt bằng đường sửa thông thường.

Kiểm tra quyền riêng và kiểm tra khóa riêng có thể đều qua nhưng vẫn bỏ sót lỗi nếu hai cơ chế bảo vệ các dữ kiện khác nhau. Ca kiểm thử này xác nhận quyết định quyền và dữ liệu được duyệt thực sự gắn với nhau.

## 12. Các lỗi thiết kế thường gặp

| Mẫu xử lý | Rủi ro | Hướng sửa |
|---|---|---|
| “Đã đăng nhập thì được gọi API” | Mọi tài khoản có thể thực hiện hành động nhạy cảm | Kiểm tra action và scope cụ thể |
| Chỉ authorize theo HTTP method | Gộp create, approve, execute vào một quyền POST/write | Dùng hành động nghiệp vụ |
| Quyền EDIT được cập nhật mọi field | Nhảy trạng thái, giả người duyệt, đổi liên kết | Command/DTO hẹp và quyền theo trường |
| Policy đọc tham số client, handler dùng giá trị khác | Vượt hạn mức hoặc đổi đối tượng sau khi được cho phép | Đánh giá trên dữ liệu thực thi có thẩm quyền |
| Kiểm tra ở UI/gateway rồi tin mọi handler | Endpoint phụ hoặc luồng nội bộ bỏ qua rule | Bảo vệ tại command thực sự tạo hiệu ứng |
| Có role ADMIN nên bỏ qua các điều kiện | Bỏ qua scope, hạn mức và phân tách nhiệm vụ | Giữ ràng buộc bắt buộc trong policy áp dụng |
| Authorize một phần tử cho cả batch | Thao tác đối tượng ngoài quyền | Kiểm tra từng mục tiêu và ràng buộc tổng |
| Catch lỗi policy rồi trả true | Phụ thuộc lỗi trở thành đường mở quyền | Kết quả chưa xác định không được tự Permit |
| Cache chỉ theo userId | Nhầm quyền giữa hành động/tenant/đối tượng | Phạm vi cache và vô hiệu hóa phù hợp |
| Biết receipt key thì được xem kết quả | Rò dữ liệu giữa người dùng | Kiểm tra quyền hiện tại và scope receipt |
| Tạo job hoặc gọi dịch vụ trước khi authorize | Hiệu ứng đã xảy ra dù response từ chối | Kiểm tra trước khi commit ý định/hiệu ứng |
| Dùng dữ liệu cũ mà không khóa/version | Quyết định không còn phù hợp lúc ghi | Ràng buộc quyết định với dữ kiện được bảo vệ |

## 13. Audit một hành động được cấp hoặc bị từ chối

Thông tin hữu ích có thể gồm:

~~~text
correlationId / commandId
authenticated subject và actor thực tế
tenantId
action thực tế
resourceId, resourceVersion/revision
policyVersion và nguồn thẩm quyền
decision: permit / deny / indeterminate
reasonCode nội bộ
kết quả command: committed / rejected / rolled back
transitionId hoặc operationId nếu đã phát sinh
~~~

Không cần log toàn bộ payload, token hoặc thông tin thanh toán nhạy cảm. Các tham số phục vụ chứng minh hạn mức phải được xử lý theo chính sách lưu trữ và quyền truy cập.

Theo dõi có thể giúp phát hiện việc một actor liên tục thử action ngoài quyền, đổi objectId/tenantId, dùng endpoint phụ hoặc gửi lại payload với các trường nhạy cảm. Cần xem các tín hiệu trong ngữ cảnh để phân biệt lỗi tích hợp và hành vi lạm dụng.

## 14. Khung đặc tả cho một hành động

Trước khi viết endpoint, có thể hoàn thiện hợp đồng sau:

~~~text
Tên hành động nghiệp vụ:
Chủ thể được hỗ trợ:
Đối tượng hoặc phạm vi đích:
Dữ liệu có thẩm quyền dùng để quyết định:

Quyền nền/capability:
Điều kiện tenant và object scope:
Điều kiện theo tham số, hạn mức và trường dữ liệu:
Ràng buộc bắt buộc, gồm phân tách nhiệm vụ nếu có:

Tiền điều kiện trạng thái/version:
Hiệu ứng được phép:
Trường phải giữ nguyên:
Bất biến sau thực hiện:

Điểm kiểm tra và cơ chế bảo vệ concurrency:
Cách xử lý Permit/Deny/Indeterminate:
Quy tắc batch, async, replay và cache nếu có:
Audit và lỗi trả cho người gọi:
Các ca vượt quyền cần kiểm thử:
~~~

## 15. Câu hỏi tự kiểm tra

1. Vì sao người xem được một refund chưa chắc được approve hoặc export nó?
2. Khi tạo mới một đối tượng, resource nào được dùng để kiểm tra quyền?
3. Làm sao một endpoint cập nhật tổng quát có thể bỏ qua quyền approve?
4. Nếu policy đọc amount từ request nhưng handler đọc amount từ cơ sở dữ liệu, điều gì có thể xảy ra?
5. Những dữ kiện nào phải ổn định từ lúc authorize đến lúc commit?
6. Khi nguồn quyền lỗi, vì sao không được coi thiếu dữ liệu là Permit?
7. Idempotency key có thể dùng thay kiểm tra quyền trong trường hợp nào? Hãy giải thích vì sao câu trả lời cần phân biệt chống trùng với cấp quyền.
8. API batch và background job của bạn đang kiểm tra quyền trên toàn bộ mục tiêu bằng cách nào?

Một quy tắc action authorization có thể kiểm chứng cần gắn **đúng chủ thể, đúng hành động, đúng đối tượng và đúng dữ liệu sẽ được thực hiện**. Quyền đó phải được thực thi tại nơi tạo hiệu ứng và giữ nguyên ý nghĩa khi đi qua các endpoint, worker hoặc lần gửi lại khác nhau.
