# Job duplicate prevention — Ngăn xử lý trùng tác vụ nền

## 1. Vấn đề cần giải quyết: một ý định, nhiều lần thực thi

Một tác vụ nền có thể chạy nhiều lần dù người dùng chỉ muốn thực hiện nghiệp vụ một lần. Người dùng bấm lại nút vì giao diện chậm, API nhận lại request sau timeout, broker giao lại message, scheduler tạo lại một lịch chạy hoặc worker chết trước khi xác nhận đã xử lý.

Trong bảo mật logic nghiệp vụ, rủi ro nằm ở tác động của những lần chạy đó: hoàn tiền hai lần, cộng thưởng nhiều lần, phát hành nhiều mã ưu đãi cho cùng một quyền lợi, hoặc gửi một yêu cầu chi trả nhiều lần. Kẻ tấn công có thể chủ động tạo các điều kiện này bằng request đồng thời, replay hoặc chọn đúng thời điểm hệ thống chuyển trạng thái.

**Job duplicate prevention** là tập hợp cơ chế nhận diện cùng một ý định nghiệp vụ và ngăn những lần xử lý lặp tạo ra tác động ngoài quy tắc. Một thiết kế tốt vẫn cho phép retry để phục hồi lỗi, đồng thời bảo đảm retry không trở thành nghiệp vụ mới.

### Ví dụ xuyên suốt

Hệ thống cho phép tạo yêu cầu hoàn tiền rồi thực hiện qua worker:

~~~text
Khách hàng hoặc nhân viên
    → Refund API
    → Cơ sở dữ liệu + outbox
    → Hàng đợi
    → Refund worker
    → Cổng thanh toán
~~~

Một yêu cầu hoàn tiền đã được chấp thuận có định danh `refundId`. Worker có thể xử lý lại yêu cầu đó nhiều lần, nhưng không được hoàn thêm tiền.

Cùng một đơn hàng vẫn có thể có nhiều lần hoàn tiền một phần hợp lệ. Vì vậy, “chỉ được có một job cho mỗi đơn hàng” thường là quy tắc quá rộng. Cần phân biệt:

- **Cùng yêu cầu hoàn tiền được thử lại:** giữ cùng ý định và cùng tác động.
- **Yêu cầu hoàn tiền một phần mới:** là ý định mới, phải kiểm tra lại quyền và số tiền còn có thể hoàn.
- **Yêu cầu mới được tạo để né chống trùng:** dù có định danh khác, vẫn phải tuân thủ giới hạn nghiệp vụ tổng thể.

Ngăn trùng không thay thế phân quyền hoặc kiểm tra số tiền. Những cơ chế này cần hoạt động cùng nhau.

## 2. Phân biệt các định danh trước khi chọn khóa chống trùng

Không phải mọi loại ID đều biểu diễn cùng một điều.

| Định danh | Đại diện cho | Có thay đổi khi retry không? |
| --- | --- | --- |
| `requestId` | Một lần gọi API để truy vết | Thường có |
| `idempotencyKey` | Ý định gọi API được client muốn thử lại | Không, trong cùng ý định và phạm vi |
| `refundId` | Yêu cầu hoàn tiền nghiệp vụ đã được server chấp nhận | Không |
| `jobId` | Một công việc được hệ thống lập lịch hoặc đưa vào hàng đợi | Tùy thiết kế; không dùng làm định danh duy nhất của tác động |
| `messageId` hoặc `eventId` | Một thông điệp hoặc sự kiện logic | Giữ nguyên khi giao lại cùng sự kiện |
| `attemptId` | Một lần worker thử xử lý | Có |
| `effectKey` | Tác động bên ngoài hoặc bút toán cần bảo vệ | Không, nếu vẫn là cùng tác động |
| `leaseToken` hoặc `fence` | Quyền xử lý của một lần nhận việc | Có khi chuyển quyền cho lần nhận mới |

Một broker có thể tạo delivery ID mới khi giao lại cùng message. Một thao tác phát lại thủ công cũng có thể tạo message mới cho cùng `refundId`. Do đó, chỉ chống trùng theo ID vận chuyển không đủ bảo vệ tác động nghiệp vụ.

### 2.1. Khóa cần phản ánh đúng phạm vi

Khóa API thường được ràng buộc với tenant, danh tính hoặc phạm vi gọi được xác định, loại thao tác và idempotency key:

~~~text
(tenantId, requesterScope, operationType, idempotencyKey)
~~~

Định danh tác động có thể dùng:

~~~text
(tenantId, refundId, effectType)
~~~

Tenant và quyền truy cập phải được suy ra hoặc kiểm chứng từ danh tính đã xác thực. Không coi `tenantId` do client hay message tự khai là bằng chứng người gọi được quyền xử lý dữ liệu đó.

Nếu hai nhân viên cùng tạo hai yêu cầu cho một quyền lợi chỉ được dùng một lần, khóa theo người gọi không ngăn được hai yêu cầu này. Cần thêm khóa hoặc điều kiện ở cấp nghiệp vụ, chẳng hạn `(tenantId, entitlementId, redemptionType)`.

### 2.2. Fingerprint để phát hiện tái sử dụng key sai nghĩa

Lưu fingerprint của nội dung nghiệp vụ cùng idempotency key. Với cùng key:

- Cùng nội dung đã chuẩn hóa: trả lại kết quả phù hợp hoặc cho biết tác vụ đang xử lý.
- Khác nội dung nghiệp vụ: từ chối xung đột, không thực thi nội dung mới.

Ví dụ fingerprint của yêu cầu hoàn tiền có thể bao gồm tenant, giao dịch gốc, số tiền theo đơn vị nhỏ nhất, tiền tệ và loại hoàn tiền. Server phải chuẩn hóa kiểu dữ liệu trước khi so sánh; không chỉ băm nguyên chuỗi JSON với thứ tự field tùy ý.

Trace ID, thời gian gửi lại hoặc ghi chú không ảnh hưởng ý nghĩa không nên vô tình biến một retry thành ý định mới. Ngược lại, những trường làm thay đổi đối tượng, số tiền hoặc phạm vi quyền phải được tính đến.

**Fingerprint không phải khóa chống lạm dụng hoàn chỉnh.** Hai yêu cầu có hai key khác nhau vẫn có thể vi phạm giới hạn tổng số tiền hoàn.

## 3. Các business invariant phải luôn đúng

### 3.1. Một ý định không tạo nhiều tác động thành công

~~~text
Với mỗi (tenantId, refundId, effectType):
    Số tác động hoàn tiền thành công không vượt quá một.
~~~

Trong một cơ sở dữ liệu, có thể bảo vệ một bút toán bằng unique constraint và transaction. Khi tác động nằm ở cổng thanh toán, cần cơ chế idempotency hoặc tra cứu phù hợp của phía nhận, cùng quy trình xử lý kết quả không xác định. Một cờ trong cơ sở dữ liệu cục bộ không tự tạo ra bảo đảm cho hệ thống bên ngoài.

### 3.2. Tổng nghĩa vụ không vượt giới hạn nghiệp vụ

Đối với hoàn tiền một phần:

~~~text
completedRefundAmount + reservedRefundAmount <= refundableAmount
~~~

`reservedRefundAmount` là số tiền đã giữ cho các yêu cầu có thể còn tạo tác động, gồm yêu cầu đang xử lý hoặc chưa biết kết quả phía cổng thanh toán. Việc giữ chỗ tránh để hai yêu cầu hợp lệ riêng lẻ cùng tiêu số dư còn lại.

Ví dụ một giao dịch còn có thể hoàn 1.000.000 VND. Hai request đồng thời, mỗi request xin hoàn 600.000 VND, không được cùng vượt qua chỉ vì cả hai cùng đọc số dư ban đầu. Kiểm tra và giữ chỗ phải được tuần tự hóa bằng khóa, cập nhật có điều kiện hoặc cơ chế giao dịch tương đương.

Không giải phóng khoản giữ chỗ chỉ vì worker timeout. Nếu cổng thanh toán đã hoàn tiền nhưng phản hồi bị mất, giải phóng sớm có thể cho phép một yêu cầu khác hoàn vượt mức.

### 3.3. Chuyển trạng thái phải có điều kiện

Worker chỉ được chuyển trạng thái theo state machine và phiên bản hiện tại. Một message cũ không được đưa yêu cầu `SUCCEEDED` trở lại `RUNNING`, hoặc biến yêu cầu đã hủy hợp lệ thành một lệnh thanh toán mới.

### 3.4. Chống trùng không được cấp thêm quyền

Biết một idempotency key, `jobId` hoặc `refundId` không cho phép xem kết quả hay phát lại tác vụ. Nhánh trả kết quả cũ cũng phải kiểm tra quyền hiện tại đối với dữ liệu được trả.

### 3.5. Retry phải giữ nguyên ý định và tác động

Mỗi lần thử có thể có `attemptId` mới. Nó vẫn phải tham chiếu cùng `refundId`, cùng thông số đã được chấp thuận và cùng `effectKey`. Không tạo effect key mới chỉ vì lần trước bị timeout.

## 4. Bảo vệ lúc tạo job: idempotency và transaction

### 4.1. Không dùng “đọc trước, chèn sau” làm bảo đảm duy nhất

Mẫu sau bị race:

~~~text
Request A: Không thấy key K
Request B: Không thấy key K
Request A: Tạo refund và job
Request B: Tạo refund và job
~~~

Unique constraint tại kho dữ liệu có thẩm quyền cần quyết định ai được tạo bản ghi cho key đó. Ứng dụng xử lý xung đột để trả kết quả cũ hoặc trạng thái đang xử lý theo hợp đồng API.

Nếu hai request cùng chèn, cần xử lý tình huống bản ghi của request đầu chưa commit. Không đọc một bản ghi chưa hoàn tất rồi trả nhầm kết quả thành công.

### 4.2. Tạo ý định, giữ chỗ và ghi sự kiện cùng transaction

Mã sau là mã giả theo phong cách Java; các thao tác repository và transaction phải được triển khai theo cơ sở dữ liệu thực tế.

~~~java
RefundResult requestRefund(Actor actor, RefundCommand command) {
    return transaction.execute(() -> {
        TenantId tenantId = authorization.resolveTenant(actor);
        authorization.requireCanRequestRefund(actor, tenantId);

        CanonicalRefund payload = validation.normalize(command);
        IdempotencySlot slot = idempotency.claimOrLoad(
            tenantId, actor.requesterScope(), "REQUEST_REFUND",
            command.idempotencyKey(), payload.fingerprint()
        );

        if (slot.isCompleted()) {
            authorization.requireCanViewRefund(actor, slot.refundId());
            return slot.previousResult();
        }

        Payment payment = payments.lockByTenantAndId(
            tenantId, payload.paymentId()
        );
        authorization.requireCanRefund(actor, payment);
        policy.requireApprovalAndRefundConditions(actor, payment, payload);

        // Kiểm tra và giữ chỗ dưới cùng khóa của giao dịch gốc.
        payment.reserveRefundAmount(payload.amountMinor());

        RefundIntent refund = refunds.createAccepted(
            payment, actor, payload
        );
        jobs.createIfAbsent(refund.id(), "EXECUTE_REFUND");
        outbox.append(RefundRequested.from(refund));

        RefundResult result = RefundResult.accepted(refund.id());
        idempotency.complete(slot, refund.id(), result);
        return result;
    });
}
~~~

Toàn bộ cập nhật giữ chỗ, ý định hoàn tiền, bản ghi job, outbox và kết quả idempotency phải commit nhất quán. Nếu giao dịch thất bại, không được để lại khoản giữ chỗ hoặc sự kiện khẳng định yêu cầu đã được chấp nhận một cách rời rạc.

Cần lưu tiền tệ và biểu diễn số tiền chính xác, chẳng hạn số nguyên theo đơn vị nhỏ nhất phù hợp với tiền tệ và hợp đồng thanh toán. Không dùng số thực nhị phân cho phép cộng trừ hạn mức.

### 4.3. Vì sao cần outbox?

Nếu ghi refund rồi gửi message ngoài transaction, tiến trình có thể chết sau commit và không đưa job vào hàng đợi. Nếu gửi message trước commit, worker có thể thấy một yêu cầu chưa tồn tại hoặc bị rollback.

Transactional outbox ghi sự kiện trong cùng transaction với ý định nghiệp vụ. Publisher gửi sự kiện sau commit và có thể gửi lại nếu chưa biết lần gửi trước có thành công hay không.

Outbox giải quyết khoảng trống ghi nhận và phát sự kiện. Consumer vẫn cần chống trùng vì cùng sự kiện có thể được phát hoặc giao nhiều lần.

## 5. Bảo vệ lúc nhận message: inbox và công việc bền vững

Broker có thể giao lại message sau timeout, mất kết nối hoặc worker khởi động lại. Acknowledge của broker chỉ nói rằng consumer đã nhận trách nhiệm theo hợp đồng xử lý; nó không tự chứng minh tiền đã được hoàn.

Có hai cách tổ chức cần phân biệt:

| Cách tổ chức | Khi nào được acknowledge message? | Lớp tiếp tục bảo vệ |
| --- | --- | --- |
| Consumer thực hiện tác động hoàn toàn trong cơ sở dữ liệu cục bộ | Sau khi inbox, tác động và kết quả cùng commit | Transaction và khóa nghiệp vụ |
| Consumer chỉ chuyển message thành job bền vững | Sau khi inbox và job đã cùng commit | Worker, state machine và effect key của job |

Ở cách thứ hai, một inbox có trạng thái “đã tiếp nhận” không được bị hiểu thành “đã hoàn tiền”. Nếu tiến trình chết sau acknowledge, job trong cơ sở dữ liệu vẫn phải được scheduler hoặc worker khác lấy lại.

### 5.1. Inbox ngăn xử lý lại cùng sự kiện

Một ràng buộc như sau hữu ích:

~~~text
UNIQUE(consumerName, eventId)
~~~

Nếu event ID không được bảo đảm toàn cục trong hệ thống, thêm nguồn phát và tenant theo hợp đồng định danh. Chỉ nhận sự kiện từ nguồn được xác thực; không cho người gửi tùy ý chọn ID của một sự kiện khác để làm nó bị bỏ qua.

Inbox không thay thế khóa nghiệp vụ. Hai event ID khác nhau vẫn có thể tham chiếu cùng `refundId`. Cần khóa riêng để không tạo nhiều job hoặc nhiều effect cho cùng ý định.

### 5.2. Không ghi “đã xử lý” trước tác động

~~~text
Sai:
    Ghi inbox DONE
    → Gọi thanh toán
    → Worker chết
    → Retry bị bỏ qua vì inbox đã DONE
~~~

Tương tự, ghi `SUCCEEDED` trước khi gọi cổng thanh toán có thể làm mất hoàn tiền. Gọi cổng thanh toán trước rồi đánh dấu `SUCCEEDED` cũng có khoảng trống tạo trùng nếu không có cơ chế ở phía nhận.

Tên trạng thái phải thể hiện đúng bằng chứng: đã nhận message, đã tạo job, đang thử gọi, chưa biết kết quả hoặc đã xác nhận tác động.

## 6. Tác động trong cùng cơ sở dữ liệu: bảo đảm bằng transaction

Nếu job chỉ cộng điểm trong sổ cái nội bộ, có thể dùng một transaction để bảo vệ cả bản ghi tác động lẫn thay đổi số dư.

Ví dụ quy tắc: một quyền lợi `entitlementId` chỉ được cộng thưởng một lần.

~~~text
Trong cùng transaction:
    1. Đọc và kiểm tra trạng thái quyền lợi trong đúng tenant.
    2. Chèn bút toán với UNIQUE(tenantId, entitlementId, effectType).
    3. Cập nhật số dư tương ứng.
    4. Đánh dấu quyền lợi đã được sử dụng và job hoàn tất.
    5. Commit.
~~~

Nếu unique constraint phát hiện tác động đã có, không cộng số dư lần nữa. Nếu bước cập nhật số dư thất bại, transaction phải rollback cả bút toán mới.

Các điểm cần giữ:

- Khóa phải gắn với quyền lợi nghiệp vụ, không chỉ với một `jobId` có thể được tạo mới.
- Bút toán và số dư phải nằm trong cùng ranh giới transaction nếu đang dựa vào tính nguyên tử này.
- Mọi đường ghi số dư, kể cả job quản trị, phải tuân thủ cùng invariant.
- Không bắt rồi bỏ qua lỗi unique một cách chung chung; phải xác định đó đúng là xung đột của tác động đang bảo vệ.
- Nếu job tạo thêm sự kiện, ghi outbox trong transaction để không mất hoặc phát sai kết quả.

Có thể chứng minh một bút toán cục bộ không bị ghi hai lần theo khóa nghiệp vụ. Không mở rộng kết luận đó thành bảo đảm “mọi hệ thống bên ngoài đều thực hiện đúng một lần”.

## 7. Tác động bên ngoài: khoảng trống cần đối soát

### 7.1. Timeout không chứng minh chưa hoàn tiền

~~~text
Worker                 Cổng thanh toán
   |--- Hoàn tiền ---------->|
   |                         | Đã thực hiện
   |<--- Phản hồi bị mất -----X
   |
   | Timeout: chưa biết kết quả
~~~

Tại thời điểm này, tạo một refund mới hoặc effect key mới có thể dẫn tới hoàn thêm tiền. Đánh dấu thất bại chắc chắn rồi giải phóng khoản giữ chỗ cũng có thể làm yêu cầu khác sử dụng lại hạn mức đã bị tiêu.

Cần có trạng thái `UNKNOWN` hoặc `RECONCILING` và một quy trình tìm bằng chứng từ cổng thanh toán.

### 7.2. Giữ effect key ổn định qua mọi lần thử

Nếu cổng thanh toán hỗ trợ idempotency cho thao tác cần dùng, server tạo và lưu key gắn với ý định:

~~~text
effectKey = định danh ổn định của (tenantId, refundId, REFUND_PAYMENT)
~~~

Không cần key phải là phép nối chuỗi có thể đoán được. Điều quan trọng là server lưu ràng buộc ổn định và không cho client thay đổi key hoặc payload của ý định đã được chấp nhận.

Trước khi dựa vào khả năng này, phải xác định từ hợp đồng của nhà cung cấp:

- Key có hiệu lực trong phạm vi tài khoản, API hoặc khu vực nào.
- Cùng key nhưng payload khác được xử lý thế nào.
- Request đồng thời được xử lý ra sao.
- Key được giữ trong bao lâu.
- Có API tra cứu bằng key hoặc mã tham chiếu nghiệp vụ không.
- Trường hợp nào được retry và trường hợp nào cần đối soát trước.

Không giả định mọi API đều có cùng ngữ nghĩa. Một tính năng chống trùng ở gateway hoặc broker không tự bảo vệ giao dịch tại cổng thanh toán.

### 7.3. Luồng xử lý mẫu

~~~mermaid
sequenceDiagram
    participant Worker as Refund worker
    participant DB as Cơ sở dữ liệu
    participant PSP as Cổng thanh toán
    participant Reconciler as Bộ đối soát

    Worker->>DB: Nhận job bằng lease, kiểm tra ý định và effect key
    DB-->>Worker: refundId, payload cố định, fence
    Worker->>PSP: Hoàn tiền với effect key ổn định
    alt Có bằng chứng thành công
        PSP-->>Worker: Mã giao dịch hoàn tiền
        Worker->>DB: Ghi kết quả và chuyển giữ chỗ thành đã hoàn
    else Kết quả không xác định
        Worker->>DB: Ghi UNKNOWN, tiếp tục giữ chỗ
        Reconciler->>PSP: Tra cứu bằng tham chiếu đã lưu
        PSP-->>Reconciler: Kết quả có thể xác minh
        Reconciler->>DB: Hoàn tất hoặc quyết định retry theo chính sách
    end
~~~

Mọi lần ghi kết quả cần kiểm tra trạng thái, phiên bản và quyền của tiến trình xử lý. Một phản hồi đến muộn từ worker cũ có thể được giữ làm bằng chứng đối soát, nhưng không được tùy ý ghi đè trạng thái mới.

Chỉ giải phóng giữ chỗ khi có căn cứ rằng tác động sẽ không xảy ra, chẳng hạn thất bại dứt điểm theo hợp đồng hoặc hủy trước khi gửi. Khi đã thành công, chuyển khoản giữ chỗ sang tổng đã hoàn trong transaction ghi kết quả.

Nếu nhà cung cấp không có idempotency đủ mạnh và không thể tra cứu tin cậy, không có một cờ cục bộ nào giải quyết được hoàn toàn khoảng trống gọi ra ngoài. Cần hạn chế retry tự động trong trạng thái không xác định và có đối soát hoặc can thiệp theo thẩm quyền.

## 8. Lease, lock và fencing: bảo vệ quyền xử lý

### 8.1. Nhận job phải là thao tác nguyên tử

Mẫu “đọc job đang chờ rồi cập nhật thành đang chạy” có thể cho hai worker cùng nhận việc. Thao tác nhận cần dùng cơ chế khóa hoặc cập nhật có điều kiện để chỉ một worker thắng tại một thời điểm.

Một bản ghi nhận việc thường có:

~~~text
jobId
state
leaseOwner
leaseUntil
fence
attemptCount
nextAttemptAt
version
~~~

Khi job được nhận lại hợp lệ, hệ thống tăng `fence`. Khi hoàn tất, worker cập nhật có điều kiện theo `jobId`, trạng thái và fence đã nhận. Deadline lease nên được đánh giá từ nguồn thời gian nhất quán phù hợp với kho điều phối; tránh để mỗi máy tự quyết định trên đồng hồ lệch nhau.

### 8.2. Lease hết hạn không có nghĩa worker cũ đã dừng

Một worker có thể bị dừng lâu do GC, mất mạng hoặc bị treo rồi tiếp tục sau khi lease hết hạn. Worker mới lúc đó có thể đã nhận cùng job.

Fencing token giúp kho nhận cập nhật nhận ra quyền xử lý cũ. Nhưng hiệu lực chỉ tồn tại ở nơi thực sự kiểm tra token:

| Cơ chế | Bảo vệ được | Giới hạn |
| --- | --- | --- |
| Khóa trong bộ nhớ | Luồng trong cùng tiến trình | Không ngăn worker ở máy khác |
| Distributed lock có thời hạn | Giảm xử lý đồng thời trong thời gian giữ khóa | Worker cũ có thể tiếp tục sau khi khóa hết hạn |
| Conditional update với fence | Chặn worker cũ ghi kết quả vào kho có kiểm tra fence | Không tự ngăn một cuộc gọi ngoài đã phát đi |
| Effect key phía cổng thanh toán | Kiểm soát tác động lặp theo hợp đồng API | Phụ thuộc phạm vi và thời hạn của nhà cung cấp |
| Unique constraint trên bút toán | Chặn bút toán cục bộ trùng theo khóa | Không tự kiểm soát hệ thống ngoài |

Không coi “có distributed lock” là bằng chứng tiền không thể bị hoàn hai lần. Nếu hệ thống ngoài không kiểm tra fence, cần dùng effect key hoặc cơ chế tương đương tại chính ranh giới tác động.

### 8.3. Thu hồi lease phải xem xét giai đoạn tác động

Job chưa gọi ra ngoài có thể được nhận lại theo chính sách. Job có khả năng đã gửi lệnh ra ngoài nhưng chưa biết kết quả cần chuyển qua đường xử lý không xác định.

Trước khi thử lại, worker phải biết retry với cùng key còn được nhà cung cấp bảo vệ hay cần đối soát. Việc lease hết hạn không được tự động biến mọi job thành một request mới an toàn.

## 9. State machine cho retry, hủy và phát lại

Một mô hình đơn giản:

~~~text
READY → RUNNING → SUCCEEDED
           |
           ├── RETRY_WAIT → READY
           ├── UNKNOWN → RECONCILING
           └── FAILED_FINAL

READY → CANCELLED
RECONCILING → SUCCEEDED / RETRY_WAIT / FAILED_FINAL / MANUAL_REVIEW
~~~

Các nhánh chỉ hợp lệ khi có đủ bằng chứng. `FAILED_FINAL` cần có nghĩa rõ là không còn tác động có thể phát sinh theo quy trình, hoặc phải tách một trạng thái can thiệp khác để không giải phóng nghĩa vụ quá sớm.

### 9.1. Retry là lần thử mới, không phải ý định mới

Retry phải giữ nguyên payload nghiệp vụ đã được chấp thuận. Nếu số tiền hoặc người thụ hưởng cần thay đổi, xử lý như thay đổi nghiệp vụ có kiểm soát hoặc ý định mới, với kiểm tra quyền và hạn mức tương ứng.

Đếm số lần thử ở server, giới hạn tần suất và dùng lịch retry có khoảng chờ. Không nhận `attemptCount=0` từ message rồi cho phép bắt đầu lại vô hạn.

### 9.2. Hủy cần xác định đã qua điểm tác động hay chưa

Có thể hủy job chưa gửi lệnh ra ngoài và giải phóng giữ chỗ trong transaction phù hợp. Với job đang chạy, một cờ `cancelRequested` chỉ là yêu cầu dừng; không chứng minh rằng thanh toán đã bị hủy.

Nếu lời gọi ngoài đang diễn ra hoặc kết quả không rõ, tiếp tục đối soát. Không đổi thẳng sang `CANCELLED` rồi cho phép tạo một khoản hoàn mới như thể lần trước chắc chắn chưa thực hiện.

### 9.3. Dead-letter và replay vẫn giữ định danh nghiệp vụ

Đưa message vào dead-letter queue là chuyển trách nhiệm xử lý, không phải xóa nghĩa vụ hoàn tiền hoặc xóa trạng thái không xác định.

Khi phát lại:

1. Xác thực người hoặc tiến trình được quyền phát lại.
2. Đọc trạng thái hiện tại từ dữ liệu có thẩm quyền.
3. Giữ `refundId` và `effectKey`; tạo `attemptId` hoặc bản ghi yêu cầu replay mới.
4. Kiểm tra khả năng retry còn an toàn theo hợp đồng hệ thống ngoài.
5. Lưu lý do, người thực hiện và kết quả.
6. Không chạy lại tác động nếu đã có bằng chứng thành công.

Nút “Retry” trên trang quản trị là một endpoint nghiệp vụ có tác động tiền bạc, cần được bảo vệ tương xứng.

## 10. Quyền thực thi khi tác vụ chạy trễ

Job thường được tạo ở thời điểm T1 và chạy ở T2. Quyền người yêu cầu, trạng thái đối tượng hoặc chính sách có thể đã thay đổi trong khoảng đó.

Thiết kế cần chọn và ghi rõ một trong các mô hình phù hợp cho từng loại nghiệp vụ:

| Mô hình | Ý nghĩa | Điều phải kiểm soát |
| --- | --- | --- |
| Kiểm tra quyền lại lúc chạy | Job chỉ chạy nếu yêu cầu vẫn được phép theo quyền hiện tại | Chính sách khi quyền mất hiệu lực, hủy và giải phóng giữ chỗ |
| Thực thi nghĩa vụ đã được chấp thuận | Job hoàn thành một ý định đã có quyết định hợp lệ | Bằng chứng chấp thuận, payload cố định, thời hạn và điều kiện thu hồi |

Không mặc định rằng việc tài khoản người yêu cầu bị khóa phải hủy mọi nghĩa vụ đã được chấp thuận. Cũng không mặc định một snapshot quyền cũ cho phép worker thực hiện mọi hành động vô thời hạn.

Trong cả hai mô hình, worker phải kiểm tra tenant, mối liên hệ đối tượng, trạng thái hiện tại và ràng buộc của ý định. Service account có quyền kỹ thuật rộng không được biến một message tùy ý thành lệnh có quyền nghiệp vụ.

### 10.1. Message là yêu cầu tham chiếu, không phải nguồn sự thật duy nhất

Message có thể chứa:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt_refund_813",
  "eventType": "RefundRequested",
  "tenantId": "tenant_42",
  "refundId": "refund_781",
  "intentVersion": 1
}
~~~

Worker đọc ý định đã lưu để lấy giao dịch gốc, số tiền, tiền tệ, người thụ hưởng và quyết định chấp thuận. Nếu message có các trường này để phục vụ hiệu năng, cần đối chiếu với hợp đồng tin cậy và phiên bản, không nhận giá trị sửa đổi từ nguồn không có thẩm quyền.

Giả sử kẻ tấn công phát lại message hợp lệ nhưng đổi `refundId` hoặc `tenantId`. Kiểm tra nguồn message, quyền truy cập hàng đợi và mối liên hệ trong cơ sở dữ liệu phải ngăn việc xử lý chéo phạm vi. Việc “message đến từ queue nội bộ” không đủ để bỏ mọi kiểm tra nghiệp vụ.

### 10.2. Chống trùng không được tạo kênh rò rỉ

Nếu một request dùng key của người khác, API không được trả nội dung hoàn tiền chỉ vì tìm thấy bản ghi idempotency. Phải xác thực người gọi và kiểm tra quyền xem kết quả trong đúng phạm vi.

Tương tự, endpoint xem job, hủy, phát lại, sửa lịch hoặc đối soát phải có quyền theo đối tượng. Lý do quản trị và audit không thay thế kiểm tra quyền.

## 11. Job định kỳ và job theo lô

### 11.1. Dùng định danh kỳ nghiệp vụ

Scheduler chạy lại sau khi khởi động hoặc nhiều scheduler cùng hoạt động có thể tạo cùng một kỳ xử lý nhiều lần.

Với tác vụ quyết toán theo ngày, khóa nên gắn với kỳ được định nghĩa bởi nghiệp vụ:

~~~text
(tenantId, settlementPolicy, businessDate, runPurpose)
~~~

Không dùng “thời điểm worker thực sự bắt đầu chạy” để định danh kỳ. Nếu một job của ngày hôm trước chạy muộn sau nửa đêm, nó vẫn thuộc kỳ hôm trước.

Cần định nghĩa múi giờ, ranh giới kỳ và hành vi khi thay đổi lịch. Đổi phiên bản triển khai hoặc biểu thức lịch không được tự cấp quyền quyết toán lại kỳ đã hoàn tất. Nếu cần chạy bù hoặc điều chỉnh, đó là một mục đích nghiệp vụ riêng, tham chiếu lần gốc và có kiểm soát.

### 11.2. Chống trùng theo từng phần tử của lô

Một batch có thể đã xử lý 700 trong 1.000 phần tử rồi chết. Chỉ lưu `batchDone=false` không cho biết những phần tử nào đã tạo tác động.

Cần định danh và lưu kết quả theo từng phần tử hoặc từng tác động:

~~~text
(batchBusinessId, itemBusinessId, effectType)
~~~

Nếu cùng một quyền lợi có thể xuất hiện trong nhiều batch, khóa tác động còn cần gắn với chính quyền lợi đó. Unique theo batch không ngăn hai batch khác nhau cùng cộng thưởng cho một quyền lợi.

Checkpoint hỗ trợ tiến độ và hiệu năng. Khóa tác động và transaction mới bảo vệ trước việc một phần tử bị xử lý lại.

## 12. Thời hạn lưu khóa, khôi phục và nhiều vùng

### 12.1. TTL phải phù hợp cửa sổ replay

Nếu key API bị xóa sau một khoảng thời gian ngắn nhưng broker hoặc công cụ quản trị có thể phát lại dữ liệu cũ lâu hơn, yêu cầu lặp có thể đi qua lớp chống trùng đã hết hạn.

Cần xác định các cửa sổ:

- Client có thể retry trong bao lâu.
- Message có thể tồn tại, được giữ trong dead-letter hoặc phát lại trong bao lâu.
- Cổng thanh toán giữ idempotency key trong bao lâu.
- Bằng chứng nghiệp vụ và tác động cần được lưu trong bao lâu.

Không nhất thiết giữ toàn bộ payload mãi mãi. Có thể giữ định danh, fingerprint hoặc bản ghi tối thiểu phù hợp chính sách dữ liệu. Nhưng không xóa lớp bằng chứng cuối cùng đang bảo vệ một tác động còn có thể bị replay.

Sau khi key phía nhà cung cấp hết hạn, gửi lại cùng chuỗi key có thể không còn được chống trùng như trước. Cần đối soát hoặc chuyển can thiệp theo chính sách, không tiếp tục retry dựa vào giả định cũ.

### 12.2. Khôi phục dữ liệu có thể làm lùi kiến thức cục bộ

Sau khi khôi phục một bản sao lưu, cơ sở dữ liệu có thể chưa ghi nhận giao dịch mà cổng thanh toán đã thực hiện. Chạy lại ngay các job được nhìn thấy là “chưa xong” có thể tạo trùng tác động.

Quy trình khôi phục cần xem xét khoảng dữ liệu mất, danh sách giao dịch bên ngoài và các effect key đã sử dụng. Tạm dừng nhóm job có rủi ro để đối soát nếu chưa đủ căn cứ, đồng thời giữ dấu vết thao tác khôi phục.

### 12.3. Bảo đảm chỉ có hiệu lực trong phạm vi phối hợp

Unique constraint ở một cơ sở dữ liệu không tự ngăn một vùng khác dùng kho dữ liệu độc lập tạo cùng tác động. Hệ thống nhiều vùng cần một nguồn quyết định nhất quán cho khóa nghiệp vụ, cơ chế sở hữu phân vùng hoặc kiểm soát tương đương theo yêu cầu thực tế.

Cache có thể giảm truy cập, nhưng cache mất dữ liệu hoặc chưa đồng bộ không được làm biến mất bảo đảm chống trùng. Ranh giới bảo đảm phải được mô tả rõ ở nơi có quyền quyết định tác động.

## 13. Kiểm thử tình huống tấn công và lỗi đồng thời

Kiểm thử quan trọng nhất là kiểm chứng số tác động, số tiền và trạng thái cuối cùng dưới các khoảng trống có thể gây lặp. Chỉ kiểm tra response “thành công” là chưa đủ.

| Tình huống | Cách tạo điều kiện | Bất biến cần chứng minh |
| --- | --- | --- |
| Bấm lại hoặc replay API | Cùng key, cùng payload | Một ý định được tạo; kết quả chấp nhận không biến thành nhiều job có tác động |
| Request đồng thời cùng key | Nhiều kết nối cùng vượt bước nhận request | Unique constraint quyết định một bản ghi; không giữ chỗ nhiều lần |
| Key dùng sai nghĩa | Cùng key, đổi số tiền hoặc giao dịch | Từ chối xung đột; không thực thi payload thứ hai |
| Đổi key để né chống trùng | Nhiều key khác nhau cho cùng quyền lợi | Ràng buộc nghiệp vụ ngăn dùng quyền lợi hoặc hạn mức nhiều lần |
| Hai khoản hoàn đồng thời | Mỗi khoản hợp lệ riêng nhưng tổng vượt số còn lại | Kiểm tra và giữ chỗ không cho tổng nghĩa vụ vượt hạn mức |
| Giao lại cùng event | Broker redelivery sau timeout | Inbox hoặc job bền vững không tạo tác động mới |
| Event mới cho cùng ý định | Replay tạo event ID khác nhưng giữ refund ID | Khóa nghiệp vụ vẫn chặn effect trùng |
| Chết sau commit trước publish | Dừng API sau khi lưu refund | Outbox còn và có thể phát; không mất nghĩa vụ |
| Chết sau nhận message | Đã acknowledge nhưng chưa chạy job | Chỉ cho acknowledge sớm nếu job đã được lưu bền vững |
| Chết sau tác động cục bộ | Gây lỗi giữa bút toán và cập nhật số dư | Cả hai commit cùng nhau hoặc cùng rollback |
| Chết sau tác động ngoài | Cổng thanh toán thành công, DB chưa lưu | Retry giữ effect key; đối soát không hoàn thêm |
| Timeout không biết kết quả | Mất phản hồi từ cổng thanh toán | Không giải phóng giữ chỗ hoặc tạo effect key mới tùy tiện |
| Worker cũ sống lại | Lease hết hạn, worker mới nhận rồi worker cũ tiếp tục | Fence chặn ghi cũ; ranh giới tác động vẫn chống lặp độc lập |
| Message cũ đến muộn | Đã thành công hoặc hủy hợp lệ rồi mới nhận bản cũ | Không làm lùi trạng thái hoặc chạy lại tác động |
| Hủy đua với xử lý | Hủy trong lúc request bên ngoài đang diễn ra | Không coi yêu cầu hủy là bằng chứng chưa có tác động |
| Chéo tenant | Đổi tenant, job hoặc refund trong request/message | Không xem, hủy, thực thi hoặc phát lại ngoài phạm vi |
| Quyền thay đổi khi chờ | Thu hồi quyền giữa lúc chấp nhận và chạy | Tuân thủ đúng mô hình quyền đã chọn, không tự leo quyền |
| TTL đã hết | Replay sau khi cache hoặc key API bị dọn | Bằng chứng nghiệp vụ còn bảo vệ hoặc yêu cầu được đưa đi đối soát |
| Scheduler hoặc batch lặp | Hai scheduler tạo cùng kỳ; chạy lại batch dở | Không tạo lại kỳ hoặc tác động từng phần tử |
| Khôi phục bản sao lưu cũ | Mô phỏng DB chưa biết giao dịch ngoài đã thành công | Quy trình đối soát ngăn gửi lại mù quáng |

Với concurrency, unique constraint và transaction, cần kiểm thử tích hợp trên cơ sở dữ liệu thực tế của hệ thống. Với cổng thanh toán, dùng môi trường kiểm thử hoặc bộ giả lập có thể giữ phản hồi, tạo timeout sau khi tác động đã xảy ra và mô phỏng hết thời hạn idempotency.

Cần kiểm tra trạng thái dữ liệu ở cuối kịch bản: số ý định, tổng đã hoàn, tổng giữ chỗ, số effect, trạng thái job và bằng chứng phía nhận. Một lần xử lý lặp được chặn thành công có thể làm số attempt tăng; đó không phải là tác động trùng.

## 14. Quan sát và xử lý khi nghi ngờ có job trùng

### 14.1. Đo riêng lần thử và tác động

Các chỉ số hữu ích:

- Số request trùng và số xung đột cùng key khác fingerprint.
- Số message giao lại, xung đột inbox và job cùng ý định bị chặn.
- Số lần lease hết hạn, nhận việc lại và ghi kết quả bị fence từ chối.
- Số effect ở trạng thái không xác định và tuổi của effect cũ nhất chưa đối soát.
- Số job quá hạn, dead-letter chưa xử lý và khoản giữ chỗ tồn đọng.
- Chênh lệch giữa sổ cái nội bộ và giao dịch bên ngoài.
- Số trường hợp vượt invariant; kỳ vọng bằng không.

Log nên nối được `tenantId`, `refundId`, `jobId`, `eventId`, `attemptId`, fence và mã tham chiếu bên ngoài. Không ghi token truy cập hoặc toàn bộ dữ liệu nhạy cảm chỉ để thuận tiện điều tra.

Phân quyền sửa và xóa dữ liệu chống trùng cần tách khỏi quyền chạy job thông thường. Nếu một nhân viên có thể xóa effect record rồi nhấn retry, lớp chống trùng dễ bị vô hiệu hóa.

### 14.2. Quy trình can thiệp

Khi có dấu hiệu trùng hoặc kết quả không rõ:

1. Giới hạn hoặc tạm dừng đúng nhóm job có rủi ro để tránh tạo thêm tác động.
2. Xác định ý định gốc và mọi attempt, event, lease liên quan.
3. Tra cứu kết quả bên ngoài bằng effect key hoặc tham chiếu đã lưu.
4. Giữ khoản giữ chỗ khi chưa có bằng chứng đủ chắc chắn.
5. Nếu tác động đã xảy ra, ghi nhận kết quả qua luồng đối soát có audit; không gọi lại để “thử xem”.
6. Nếu có thể retry an toàn, phát lại cùng ý định với effect key cũ và attempt mới.
7. Nếu đã phát sinh tác động trùng, xử lý điều chỉnh bằng nghiệp vụ riêng có thẩm quyền và bằng chứng, không xóa lịch sử để che chênh lệch.

Ngăn trùng tác vụ nền cần bảo vệ từ lúc nhận ý định tới nơi tác động thực sự xảy ra. Idempotency ở API, inbox, transaction, lease và effect key giải quyết các khoảng trống khác nhau. Quy tắc nghiệp vụ và bằng chứng đối soát nối các lớp đó lại để hệ thống có thể thử lại mà không cấp thêm tiền, quyền lợi hoặc quyền thao tác ngoài ý định đã được chấp thuận.
