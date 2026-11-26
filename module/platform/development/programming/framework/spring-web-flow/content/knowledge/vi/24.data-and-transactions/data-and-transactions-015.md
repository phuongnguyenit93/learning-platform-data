# Chống xử lý trùng tại service khi xác nhận bị gửi lại

Trong chương **Dữ liệu và giao dịch**, bài này hướng dẫn bảo vệ thao tác xác nhận khi cùng một yêu cầu có thể đến service nhiều lần. Với một hành trình Spring Web Flow, người dùng có thể nhấn nút hai lần, trình duyệt gửi lại POST, mạng bị timeout sau khi server đã commit hoặc client tự retry. Nếu mỗi request đều tạo một đơn, đặt chỗ hay giao dịch mới, dữ liệu nghiệp vụ sẽ bị nhân đôi.

Module **SPRING_WEB_FLOW** dùng state, event, transition và subflow để mô hình hóa quy trình nhiều bước; form binding và validation giúp thu thập dữ liệu qua nhiều request. Tuy nhiên, event `confirm` có thể được gửi lại ở tầng HTTP hoặc service được gọi từ nhiều luồng khác nhau. Vì vậy, khả năng chống trùng phải được thực hiện tại ranh giới service/domain và được bảo đảm bằng transaction cùng ràng buộc dữ liệu.

## 1. Vì sao một event xác nhận có thể đến nhiều lần?

Giả sử người dùng xem lại đơn hàng rồi nhấn **Xác nhận**. Trình duyệt gửi POST chứa event `_eventId_confirm`. Server xử lý thành công, tạo đơn và commit transaction, nhưng response bị mất trên đường truyền. Người dùng không biết thao tác đã hoàn tất nên nhấn lại. Request thứ hai đến server trong khi đơn đầu tiên đã được tạo.

Các tình huống tương tự gồm:

- Người dùng double-click nút xác nhận hoặc nhấn Enter nhiều lần.
- Trình duyệt, proxy hoặc ứng dụng di động retry khi kết nối chập chờn.
- Người dùng refresh hoặc gửi lại form sau khi trình duyệt cảnh báo resubmit.
- Hai tab cùng gửi event cho một đơn hoặc một bản nháp.
- Một flow execution được tiếp tục lại sau timeout, trong khi request trước đã commit.
- Một message hoặc job nền được giao lại sau khi worker không nhận được acknowledgement.

Đây là hành vi bình thường của hệ thống phân tán: ứng dụng không thể luôn biết chắc client đã nhận response hay chưa. Vì thế, không nên dựa vào giả định một request chỉ được gửi một lần.

## 2. Idempotency là gì?

Một thao tác **idempotent** có cùng kết quả nghiệp vụ khi cùng một ý định được gửi một lần hoặc nhiều lần. Nếu cùng yêu cầu xác nhận được gửi lại, hệ thống trả về kết quả đã tạo thay vì tạo thêm đơn hoặc thực hiện side effect lần nữa.

Ví dụ:

| Số lần request cùng một ý định | Kết quả mong đợi |
|---|---|
| Gửi lần đầu | Tạo một xác nhận và lưu kết quả. |
| Gửi lại sau khi response bị mất | Trả lại xác nhận đã lưu. |
| Double-click gần như đồng thời | Chỉ một lần thay đổi trạng thái nghiệp vụ được commit. |
| Retry sau lỗi trước khi transaction commit | Request sau có thể thực hiện thao tác nếu lần trước đã rollback hoàn toàn. |
| Dùng lại cùng key nhưng gửi nội dung khác | Từ chối vì một key không được đại diện cho hai ý định khác nhau. |

Idempotency không có nghĩa mọi request luôn trả cùng HTTP status hoặc cùng response bytes. Điều cần giữ ổn định là kết quả nghiệp vụ và các side effect được kiểm soát. Request đầu có thể trả kết quả vừa tạo; request lặp có thể trả cùng resource ID hoặc receipt đã lưu.

## 3. Vì sao phải đặt bảo vệ ở service/domain?

Có thể disable nút trong giao diện sau lần nhấn đầu, nhưng đó chỉ là cải thiện trải nghiệm. Người dùng vẫn có thể gửi request trực tiếp, mở nhiều tab hoặc retry từ một client khác. Kiểm tra event trong flow cũng chưa đủ vì cùng nghiệp vụ có thể được gọi từ controller, API, job nền hoặc một flow khác.

Service/domain là nơi biết ý nghĩa của thao tác: đơn nào được xác nhận, trạng thái nào được phép chuyển, tài nguyên nào bị tiêu thụ và kết quả nào đã được tạo. Do đó, service phải tự bảo vệ thao tác trước khi ghi dữ liệu.

Flow vẫn có nhiệm vụ điều phối event và state. Khi nhận `confirm`, flow gọi command service; service kiểm tra quyền, tính hợp lệ, idempotency và transaction. Kết quả service được flow dùng để đi đến màn hình xác nhận hoặc màn hình lỗi phù hợp.

## 4. Dùng idempotency key cho một ý định xác nhận

Mỗi ý định xác nhận cần một khóa duy nhất, thường gọi là `idempotencyKey` hoặc `confirmationKey`. Khóa này do server tạo và gắn với một lần xác nhận nghiệp vụ. Tất cả retry của cùng ý định phải dùng lại đúng khóa đó.

Các nguyên tắc quan trọng:

- Tạo key một lần khi bắt đầu ý định xác nhận; không tạo key mới mỗi lần người dùng nhấn nút hoặc mỗi lần request retry.
- Giữ key trong flow scope trong suốt execution để các request tiếp theo dùng cùng giá trị.
- Nếu flow execution có thể mất nhưng người dùng được tiếp tục bản nháp, lưu key hoặc command intent ở phía server để flow mới có thể dùng lại.
- Phạm vi key nên gắn với actor và loại thao tác; có thể gắn thêm resource ID để giới hạn rõ hơn.
- Không dùng session ID, flow execution key hoặc một giá trị do client tự chọn làm bằng chứng duy nhất cho idempotency.
- Không đưa key bí mật hoặc thông tin nhạy cảm vào URL; truyền trong request body và giữ ở server-side state khi có thể.

Ví dụ tạo key khi flow bắt đầu:

```xml
<flow xmlns="http://www.springframework.org/schema/webflow">
    <input name="orderId" type="java.util.UUID" required="true"/>

    <on-start>
        <evaluate expression="confirmationKeyFactory.createForOrder(flowScope.orderId)"
                  result="flowScope.confirmationKey"/>
    </on-start>

    <view-state id="review" view="order/review">
        <transition on="back" to="editOrder"/>
        <transition on="confirm" to="confirmOrder"/>
    </view-state>

    <action-state id="confirmOrder">
        <evaluate expression="orderConfirmationService.confirm(flowScope.orderId, currentActor.userId, flowScope.confirmationKey, flowScope.orderForm)"
                  result="flowScope.confirmationResult"/>
        <transition on="success" to="confirmed"/>
    </action-state>

    <end-state id="confirmed" view="order/confirmation"/>
</flow>
```

`confirmationKeyFactory` và `currentActor` là các bean minh họa. Actor phải lấy từ principal đã xác thực, không nhận từ hidden field. Khi người dùng gửi lại event trong cùng flow, `flowScope.confirmationKey` giữ nguyên. Nếu cần mở flow execution mới để tiếp tục cùng ý định sau khi execution cũ mất, service phải khôi phục key từ bản ghi command/draft phía server thay vì tạo key mới một cách mù quáng.

## 5. Lưu receipt và ràng buộc unique ở database

Service cần một bản ghi receipt hoặc command record để biết một key đã được xử lý hay chưa. Có thể dùng bảng riêng cho các command cần idempotency:

```sql
CREATE TABLE command_receipt (
    idempotency_key UUID NOT NULL,
    actor_id        VARCHAR(100) NOT NULL,
    operation       VARCHAR(80) NOT NULL,
    request_hash    VARCHAR(128) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    result_id       UUID NULL,
    created_at      TIMESTAMP NOT NULL,
    completed_at    TIMESTAMP NULL,
    CONSTRAINT uq_command_receipt
        UNIQUE (actor_id, operation, idempotency_key)
);
```

`operation` phân biệt các loại command, ví dụ `ORDER_CONFIRM` hoặc `BOOKING_CONFIRM`. `request_hash` là hash của dữ liệu có ý nghĩa với command sau khi chuẩn hóa; nó giúp phát hiện trường hợp cùng key bị dùng lại với payload khác. `result_id` trỏ đến kết quả nghiệp vụ đã tạo. Kiểu dữ liệu, độ dài hash và cú pháp SQL cần điều chỉnh theo database thực tế.

Ràng buộc unique là hàng rào bắt buộc. Một đoạn code chỉ làm `findByKey()` rồi `insert()` không đủ an toàn: hai transaction có thể cùng truy vấn trước khi một transaction nào kịp ghi, rồi cả hai đều nghĩ key chưa tồn tại. Unique constraint khiến database chỉ chấp nhận một bản ghi cho cùng phạm vi key.

## 6. Quy trình xử lý trong service

Một command xác nhận có thể đi qua các bước sau:

1. Lấy actor từ ngữ cảnh xác thực và kiểm tra actor có quyền thực hiện thao tác trên resource.
2. Chuẩn hóa dữ liệu command và tính `request_hash` từ các trường nghiệp vụ liên quan.
3. Thử đăng ký key một cách nguyên tử bằng insert/claim có ràng buộc unique.
4. Nếu key đã có, so sánh hash. Hash khác nhau thì từ chối; hash giống và đã hoàn tất thì trả lại kết quả cũ.
5. Nếu đây là lần đầu, kiểm tra trạng thái domain và thực hiện thay đổi trong transaction.
6. Lưu kết quả nghiệp vụ, đánh dấu receipt hoàn tất và ghi outbox event trong cùng transaction.
7. Commit. Nếu response bị mất, request lặp sẽ tra receipt và trả kết quả đã lưu.

Việc kiểm tra quyền vẫn cần diễn ra trước khi trả dữ liệu receipt đã lưu. Nếu chỉ biết key là có thể đọc kết quả, một actor khác có thể đoán hoặc lấy được receipt không thuộc quyền của mình.

## 7. Ví dụ service với repository claim nguyên tử

Ví dụ sau thể hiện hợp đồng mà repository cần cung cấp. `claimOrLoad` không phải API có sẵn của Spring Data; ứng dụng phải triển khai nó bằng câu lệnh database phù hợp, bảo đảm unique constraint và xử lý tranh chấp trong transaction.

```java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderConfirmationService {

    private final OrderRepository orderRepository;
    private final OrderAccessPolicy accessPolicy;
    private final CommandReceiptRepository receiptRepository;
    private final CommandHasher commandHasher;
    private final OrderOutboxRepository outboxRepository;

    public OrderConfirmationService(
            OrderRepository orderRepository,
            OrderAccessPolicy accessPolicy,
            CommandReceiptRepository receiptRepository,
            CommandHasher commandHasher,
            OrderOutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.accessPolicy = accessPolicy;
        this.receiptRepository = receiptRepository;
        this.commandHasher = commandHasher;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public ConfirmationResult confirm(
            UUID orderId, String actorId, UUID key, ConfirmOrderForm form) {

        var order = orderRepository.findByIdForUpdate(orderId)
                .orElseThrow(OrderNotFoundException::new);
        accessPolicy.assertCanConfirm(actorId, order);

        String requestHash = commandHasher.hash(
                orderId, form.getDeliveryOption(), form.getAcceptedQuoteVersion());

        var claim = receiptRepository.claimOrLoad(
                actorId, "ORDER_CONFIRM", key, requestHash);

        if (claim.isExisting()) {
            if (!claim.requestHash().equals(requestHash)) {
                throw new IdempotencyKeyReuseException();
            }
            if (claim.isCompleted()) {
                return ConfirmationResult.from(claim.resultId());
            }
            return ConfirmationResult.inProgress();
        }

        order.assertConfirmable();
        order.confirm(form.getDeliveryOption(), form.getAcceptedQuoteVersion());
        var confirmation = orderRepository.saveConfirmation(order);

        outboxRepository.addOrderConfirmed(confirmation, key);
        receiptRepository.complete(claim.id(), confirmation.getId());

        return ConfirmationResult.confirmed(confirmation);
    }
}
```

Các lớp repository, policy, hasher và domain method là thành phần minh họa. `findByIdForUpdate` dùng khóa bản ghi trong transaction; có thể thay bằng optimistic locking hoặc cập nhật có điều kiện nếu phù hợp. `claimOrLoad` phải được triển khai dựa trên khả năng nguyên tử của database, không được giả lập bằng hai lệnh đọc rồi ghi không có unique constraint.

Trong ví dụ đồng bộ, việc claim, thay đổi order, lưu confirmation, ghi outbox và đánh dấu receipt hoàn tất cùng nằm trong một transaction. Nếu transaction rollback, claim và thay đổi domain cũng rollback. Nếu transaction commit nhưng response mất, request sau sẽ thấy receipt hoàn tất và trả lại kết quả.

## 8. Xử lý cạnh tranh khi hai request đến đồng thời

Idempotency không chỉ xử lý request đến sau. Hai request có thể đến gần như cùng lúc và cùng dùng một key. Cả hai phải tranh quyền claim key ở database.

Có hai cách triển khai thường gặp:

- **Insert có unique constraint:** transaction đầu tiên insert receipt; transaction thứ hai chờ hoặc gặp xung đột unique tùy database. Sau khi transaction thắng commit, request thua đọc receipt đã hoàn tất và trả kết quả đó.
- **Upsert/claim nguyên tử hoặc khóa bản ghi:** dùng cú pháp database cụ thể để tạo hoặc khóa receipt theo key, sau đó đọc trạng thái trong cùng transaction.

Không chỉ dùng `synchronized` hoặc một biến map trong JVM. Cách đó không bảo vệ khi ứng dụng chạy nhiều instance, khởi động lại hoặc có nhiều node xử lý cùng command.

Với JPA, nếu `save()` receipt gây `DataIntegrityViolationException`, transaction hiện tại có thể đã bị đánh dấu rollback-only. Không nên bắt exception đó bên trong cùng transaction rồi tiếp tục ghi order như thể chưa có gì. Hãy để transaction thua rollback, sau đó đọc receipt đã commit trong một transaction mới và trả kết quả tương ứng. Chi tiết phụ thuộc database và cách transaction manager xử lý lỗi.

Với command chạy lâu hoặc bất đồng bộ, có thể lưu trạng thái `PROCESSING` cùng lease/heartbeat. Cần quy định thời điểm lease hết hạn, cách worker khác tiếp quản và cách xác định tác vụ trước đã hoàn tất hay chưa. Không để bản ghi `PROCESSING` treo vô hạn mà không có cơ chế phục hồi.

## 9. Phân biệt request lặp với key bị tái sử dụng sai

Key nhận diện một ý định xác nhận cụ thể. Nếu cùng key được dùng với dữ liệu khác, service phải từ chối thay vì trả receipt cũ hoặc âm thầm xử lý nội dung mới.

Ví dụ, lần đầu người dùng xác nhận đơn với phương thức giao hàng `STANDARD`; request retry sau đó gửi cùng key nhưng đổi thành `EXPRESS`. Đây không còn là retry cùng một command. `request_hash` khác nhau phải dẫn đến lỗi xung đột hoặc yêu cầu tạo một ý định xác nhận mới sau khi người dùng xem lại.

Hash cần được tính từ dữ liệu có ý nghĩa nghiệp vụ sau khi chuẩn hóa: resource ID, lựa chọn, phiên bản báo giá hoặc các trường command được phép thay đổi. Không hash toàn bộ JSON thô nếu thứ tự field, whitespace hoặc trường không liên quan có thể thay đổi. Không lưu raw payload nhạy cảm chỉ để so sánh request.

## 10. Phối hợp transaction và side effect bên ngoài

Transaction database có thể bảo vệ các thay đổi trong cùng database. Nó không thể tự rollback email đã gửi, khoản thanh toán đã được nhà cung cấp xử lý hoặc message đã publish sang hệ thống khác.

Đối với side effect bên ngoài, dùng transactional outbox:

1. Trong transaction xác nhận, lưu order/confirmation, receipt và một outbox event có event ID ổn định.
2. Commit tất cả cùng nhau.
3. Worker đọc outbox và gửi message hoặc gọi hệ thống ngoài.
4. Worker đánh dấu đã gửi; nếu retry, dùng event ID hoặc idempotency key tương ứng ở hệ thống nhận.
5. Consumer cũng phải chống xử lý trùng vì message broker có thể giao lại message.

Không gửi email hoặc gọi cổng thanh toán trước khi database commit rồi hy vọng transaction rollback sẽ hoàn tác. Nếu thanh toán là một quy trình nhiều bước, quản lý trạng thái `PENDING`, `SUCCEEDED`, `FAILED` và thao tác bù trừ theo thiết kế nghiệp vụ. Dùng idempotency key do nhà cung cấp thanh toán hỗ trợ nếu có.

## 11. Chọn phạm vi và thời hạn lưu key

Receipt phải tồn tại ít nhất trong khoảng thời gian hệ thống cho phép retry hoặc người dùng có thể gửi lại yêu cầu. Nếu xóa receipt quá sớm, một request cũ có thể được hiểu là command mới và tạo tác động trùng.

Khi thiết kế retention, cân nhắc:

- Thời hạn của flow, draft và session.
- Thời gian retry của trình duyệt, mobile client, gateway hoặc job queue.
- Quy định lưu trữ giao dịch và khả năng tra soát.
- Dữ liệu nào cần giữ để trả lại kết quả và dữ liệu nào có thể xóa/ẩn danh.
- Cách xử lý key hết hạn khi domain resource đã ở trạng thái hoàn tất.

Với thao tác quan trọng như xác nhận đơn hoặc thanh toán, trạng thái domain cuối cùng và unique constraint theo business ID vẫn nên ngăn tạo kết quả thứ hai, kể cả khi receipt idempotency đã hết hạn. Idempotency key là một lớp bảo vệ request; invariant của domain là lớp bảo vệ nghiệp vụ.

## 12. Tích hợp với Spring Web Flow

Trong flow, event xác nhận nên gọi command service một lần theo transition/action-state. Nếu flow vẫn render lại màn hình hoặc nhận request lặp, key phải giữ ổn định. Service không được phụ thuộc vào việc SWF chỉ gọi transition đúng một lần.

Có thể xử lý kết quả như sau:

| Kết quả service | Hành vi flow |
|---|---|
| `CONFIRMED` | Chuyển đến end-state hiển thị receipt. |
| `ALREADY_CONFIRMED` | Hiển thị chính receipt đã tạo trước đó. |
| `IN_PROGRESS` | Hiển thị trạng thái đang xử lý và cho phép kiểm tra lại. |
| Key dùng với payload khác | Hiển thị lỗi xung đột và yêu cầu tạo ý định mới. |
| Lỗi nghiệp vụ có thể sửa | Quay lại state phù hợp để người dùng cập nhật dữ liệu. |
| Lỗi hệ thống tạm thời | Giữ khả năng retry với cùng key sau khi xác định kết quả commit. |

Không tạo key mới mỗi lần transition được chạy lại. Nếu service trả timeout và flow không biết transaction đã commit hay chưa, hãy retry với cùng key hoặc tra receipt trước khi tạo command mới. Không dùng flow execution key làm key nghiệp vụ vì một command có thể được gửi từ nhiều execution khác nhau.

## 13. Kiểm thử idempotency

Kiểm thử cần chứng minh cả request tuần tự và request đồng thời:

| Tình huống | Kết quả mong đợi |
|---|---|
| Gửi cùng key một lần | Tạo một confirmation và một outbox event. |
| Gửi lại cùng key, cùng payload sau khi thành công | Trả cùng confirmation ID; không tạo bản ghi mới. |
| Gửi cùng key nhưng payload khác | Từ chối với lỗi key reuse/conflict. |
| Hai request cùng key chạy đồng thời | Chỉ một transaction tạo tác động; request còn lại nhận kết quả hoặc trạng thái đang xử lý. |
| Hai key khác nhau cùng xác nhận một order | Domain invariant ngăn xác nhận order lần thứ hai. |
| Transaction rollback trước commit | Không có receipt hoàn tất hoặc thay đổi nghiệp vụ dở dang; retry có thể thực hiện. |
| Commit thành công nhưng response bị mất | Retry đọc receipt và trả kết quả đã lưu. |
| Worker gửi outbox rồi mất acknowledgement | Retry không tạo side effect trùng ở consumer/nhà cung cấp. |
| Actor khác dùng key đã biết | Không được đọc receipt hoặc dữ liệu của actor khác. |
| Receipt hết retention nhưng order đã hoàn tất | Domain state vẫn ngăn tạo confirmation thứ hai. |

Các loại test nên có:

1. Unit test cho command normalization, request hash và quy tắc domain.
2. Integration test với database thật hoặc cùng loại database để kiểm tra unique constraint và transaction.
3. Test đồng thời bằng hai transaction/thread cùng claim một key.
4. Test service retry sau commit nhưng giả lập mất response.
5. Test flow execution để xác nhận event `confirm` dùng lại cùng key.
6. Test outbox/consumer để xác nhận message retry không nhân đôi side effect.

Không chỉ mock `CommandReceiptRepository` rồi khẳng định phương thức service được gọi một lần. Cần test database chứng minh ràng buộc unique hoạt động dưới cạnh tranh thực tế.

## 14. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ disable nút xác nhận | Request trực tiếp hoặc retry vẫn có thể tạo trùng. | Bảo vệ ở service và database. |
| Tạo key mới cho mỗi lần retry | Mỗi request bị xem là ý định mới. | Giữ một key ổn định cho cùng command. |
| Dùng flow execution key làm idempotency key | Cùng nghiệp vụ từ execution khác không được nhận diện là trùng. | Dùng key ở cấp domain command. |
| Chỉ `findByKey()` rồi `insert()` | Race condition khi hai request cùng kiểm tra. | Unique constraint và claim nguyên tử. |
| Cùng key nhưng không kiểm tra request hash | Payload khác có thể nhận nhầm kết quả cũ. | So sánh hash và từ chối key reuse sai. |
| Catch lỗi unique rồi tiếp tục trong transaction hỏng | Có thể commit trạng thái không nhất quán hoặc gặp rollback-only. | Rollback request thua rồi đọc receipt trong transaction mới. |
| Gửi email/thanh toán trong transaction trước commit | Side effect ngoài không rollback theo database. | Transactional outbox và idempotency ở consumer. |
| Xóa receipt quá sớm | Retry cũ có thể tạo tác động mới. | Chọn retention theo retry window và giữ domain invariant. |

## 15. Checklist trước khi đưa command vào production

- [ ] Xác định rõ một ý định nghiệp vụ và những request nào phải dùng chung key.
- [ ] Key được tạo phía server và ổn định qua retry, refresh hoặc tiếp tục flow.
- [ ] Key được giới hạn theo actor/operation/resource phù hợp.
- [ ] Service tự xác thực quyền trước khi trả kết quả receipt.
- [ ] Request hash được tính từ payload chuẩn hóa và được so sánh khi key đã tồn tại.
- [ ] Database có unique constraint; thao tác claim là nguyên tử.
- [ ] Thay đổi domain, receipt và outbox được commit nhất quán.
- [ ] Xử lý riêng request đồng thời và lỗi unique constraint.
- [ ] Retry sau timeout dùng lại key và tra được kết quả đã commit.
- [ ] Consumer hoặc hệ thống ngoài có cơ chế chống side effect trùng.
- [ ] Retention của receipt phù hợp retry window và quy định lưu trữ.
- [ ] Domain invariant vẫn ngăn thao tác nghiệp vụ lần hai khi key hết hạn.
- [ ] Có integration test với database và test cạnh tranh thực tế.

## 16. Kết luận

Khi event xác nhận có thể được gửi lại, flow không thể bảo đảm thao tác chỉ chạy một lần. Hãy tạo một idempotency key ổn định cho từng ý định nghiệp vụ, chuyển key qua flow đến command service, ghi receipt với unique constraint và thực hiện thay đổi domain trong transaction. Khi request lặp đến, service xác minh actor và payload rồi trả kết quả đã lưu. Với request đồng thời hoặc side effect ngoài database, cần cơ chế claim nguyên tử, outbox và idempotency ở consumer. Cách thiết kế này giúp cùng một xác nhận có thể được retry an toàn mà không tạo đơn, giao dịch hoặc thông báo trùng.
