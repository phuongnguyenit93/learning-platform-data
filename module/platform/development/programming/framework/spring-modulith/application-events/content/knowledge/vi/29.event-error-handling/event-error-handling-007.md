# Không nuốt lỗi

Trong hệ thống hướng sự kiện, exception là tín hiệu cho biết listener chưa hoàn tất công việc theo hợp đồng xử lý. Nếu listener bắt exception rồi kết thúc bình thường, framework có thể hiểu rằng event đã được xử lý thành công. Publication được đánh dấu hoàn tất, message có thể được xác nhận và hệ thống mất cơ hội retry hoặc phục hồi.

**Không nuốt lỗi** nghĩa là không che giấu một thất bại chưa được xử lý. Khi listener không thể hoàn thành công việc, nó cần để exception đi tới thành phần chịu trách nhiệm retry hoặc quản lý lỗi. Nếu ứng dụng đã xử lý lỗi theo một quyết định nghiệp vụ hợp lệ, kết quả đó phải được ghi nhận rõ ràng trước khi listener kết thúc bình thường.

Trong Spring Modulith, application events giúp các module giao tiếp qua hợp đồng nghiệp vụ. Event Publication Registry theo dõi việc giao event tới listener và hỗ trợ phục hồi publication chưa hoàn tất. Cơ chế này chỉ có ý nghĩa khi listener phản ánh đúng kết quả xử lý. Nuốt exception có thể biến một lần xử lý thất bại thành một publication được coi là hoàn tất.

## 1. Nuốt lỗi là gì?

Nuốt lỗi xảy ra khi code bắt exception nhưng không truyền lỗi tiếp, không thực hiện hành động thay thế đầy đủ và cũng không ghi nhận trạng thái thất bại có thể phục hồi.

Ví dụ:

~~~java
@ApplicationModuleListener
void on(OrderPaid event) {
    try {
        accountingService.recordPayment(event);
    } catch (Exception ex) {
        log.warn("Cannot record payment", ex);
    }
}
~~~

Nếu recordPayment thất bại, listener vẫn kết thúc bình thường. Với cơ chế quản lý publication, việc listener trả về bình thường có thể được xem là xử lý xong. Hệ thống không còn tín hiệu đáng tin cậy để biết công việc chưa hoàn tất và cần retry.

Một biến thể còn nguy hiểm hơn là chỉ ghi log hoặc bỏ qua exception:

~~~java
try {
    inventoryService.reserve(event.orderId());
} catch (RuntimeException ignored) {
    // bỏ qua
}
~~~

Log không thay thế trạng thái xử lý. Nếu không có retry, dead-letter, compensation hoặc quyết định nghiệp vụ được lưu lại, event có thể bị coi là đã xử lý dù tồn kho chưa được giữ.

Nuốt lỗi thường xuất phát từ ý định giữ ứng dụng chạy liên tục hoặc tránh làm gián đoạn publisher. Nhưng với event bất đồng bộ, che giấu lỗi ở listener thường khiến công việc bị mất dấu và tạo ra trạng thái nghiệp vụ không nhất quán.

## 2. Vì sao exception quan trọng với event publication?

Event Publication Registry theo dõi publication tới từng listener. Khi listener hoàn tất bình thường, publication tương ứng có thể được đánh dấu hoàn tất. Khi listener thất bại và exception được truyền ra khỏi lời gọi xử lý, publication có thể tiếp tục ở trạng thái chưa hoàn tất để được phục hồi theo chính sách của ứng dụng.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Event được phát"] --> B["Registry ghi publication"]
    B --> C["Listener xử lý"]
    C --> D{"Xử lý hoàn tất?"}
    D -->|Có| E["Publication hoàn tất"]
    D -->|Không, exception được truyền ra| F["Publication còn incomplete"]
    F --> G["Retry hoặc phục hồi"]
    G --> C
    D -->|Nuốt exception và trả về bình thường| H["Có thể bị đánh dấu hoàn tất"]
    H --> I["Công việc lỗi bị mất dấu"]
~~~

Registry theo dõi việc giao publication, không hiểu ý nghĩa nghiệp vụ của exception. Nó không thể biết listener đã thực hiện thanh toán, cập nhật kho hay ghi sổ thành công nếu listener báo kết thúc bình thường.

Vì vậy, listener cần tuân thủ một quy tắc đơn giản:

- Hoàn tất đúng công việc hoặc đã xử lý lỗi bằng một kết quả nghiệp vụ được ghi nhận rõ ràng: kết thúc bình thường.
- Chưa hoàn tất và cần thử lại hoặc phục hồi: ném exception để cơ chế quản lý lỗi nhận biết thất bại.
- Lỗi không thể tự phục hồi: chuyển sang trạng thái cách ly hoặc quy trình xử lý thủ công có lưu vết, sau đó mới kết thúc theo chính sách đã định.

Không nên dùng log message làm cơ chế điều khiển retry. Exception và trạng thái publication phải phản ánh chính xác kết quả xử lý.

## 3. Phân biệt listener đồng bộ và bất đồng bộ

Cách exception lan truyền phụ thuộc cách listener được gọi.

### Listener đồng bộ

Với listener đồng bộ, lời gọi listener diễn ra trong luồng phát event. Nếu listener ném exception, exception có thể truyền ngược về publisher. Publisher có thể nhận biết lời gọi thất bại và xử lý theo ranh giới transaction hiện tại.

Tuy nhiên, cần phân biệt listener đồng bộ thông thường với listener được gắn transaction phase. Nếu listener chạy sau khi transaction commit, exception xảy ra ở thời điểm sau commit không thể rollback giao dịch nghiệp vụ đã hoàn tất.

### Listener bất đồng bộ

ApplicationModuleListener được Spring Modulith cung cấp để khai báo listener ở ranh giới module với cơ chế xử lý bất đồng bộ và transaction riêng theo cấu hình của framework. Vì listener chạy ở luồng xử lý riêng, publisher ban đầu không thể nhận exception như một lời gọi đồng bộ thông thường.

Trong trường hợp này, exception vẫn phải được truyền ra khỏi listener để hạ tầng xử lý bất đồng bộ và publication registry nhận biết lần xử lý chưa hoàn tất. Nếu listener bắt exception rồi trả về, hệ thống có thể ghi nhận publication hoàn tất dù công việc thất bại.

Ví dụ listener giữ nguyên exception:

~~~java
@Component
class AccountingListener {

    private final AccountingService accountingService;

    AccountingListener(AccountingService accountingService) {
        this.accountingService = accountingService;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        accountingService.recordPayment(event);
    }
}
~~~

Service chịu trách nhiệm transaction và để exception truyền ra:

~~~java
@Service
class AccountingService {

    @Transactional
    public void recordPayment(OrderPaid event) {
        accountingRepository.record(
            event.orderId(),
            event.paymentId(),
            event.amount()
        );
    }
}
~~~

Nếu repository ném exception, listener không bắt rồi bỏ qua. Transaction của bước xử lý có thể rollback và framework có thể nhận biết listener thất bại.

Chi tiết transaction phase, executor, retry và publication storage phụ thuộc cấu hình ứng dụng và phiên bản Spring Modulith. Cần xác minh cơ chế thực tế đang sử dụng; không giả định mọi listener đều chạy đồng bộ hoặc mọi exception đều quay về publisher.

## 4. Khi nào được bắt exception?

Bắt exception là cần thiết khi ứng dụng có thể đưa ra quyết định cụ thể dựa trên loại lỗi. Vấn đề nằm ở việc bắt lỗi mà không xử lý kết quả.

Một số trường hợp hợp lệ:

- Bổ sung context vào log rồi ném lại exception.
- Chuyển exception kỹ thuật thành exception miền có ý nghĩa hơn rồi ném lại.
- Phân loại lỗi để chọn retry hoặc dead-letter.
- Thực hiện compensation hoặc cập nhật trạng thái lỗi trong một transaction riêng.
- Xử lý một kết quả từ chối nghiệp vụ đã được định nghĩa trong contract và lưu lại kết quả đó.

Ví dụ ghi log rồi ném lại:

~~~java
@ApplicationModuleListener
void on(OrderPaid event) {
    try {
        accountingService.recordPayment(event);
    } catch (DataAccessException ex) {
        log.error(
            "Cannot record payment for orderId={}",
            event.orderId(),
            ex
        );
        throw ex;
    }
}
~~~

Ví dụ chuyển exception kỹ thuật thành exception xử lý được ở tầng ứng dụng:

~~~java
try {
    shippingGateway.createShipment(command);
} catch (SocketTimeoutException ex) {
    throw new TemporaryShippingFailure(
        command.orderId(),
        ex
    );
}
~~~

Exception mới vẫn phải được ném ra nếu bước nghiệp vụ chưa hoàn tất. Việc phân loại giúp retry policy quyết định hành động tiếp theo.

Không bắt Exception hoặc Throwable ở mọi tầng chỉ để giữ luồng chạy. Bắt quá rộng có thể che giấu lỗi lập trình nghiêm trọng, lỗi cấu hình hoặc lỗi mà tầng hiện tại không biết cách xử lý.

## 5. Phân biệt lỗi kỹ thuật và kết quả nghiệp vụ

Không phải mọi kết quả không thành công đều cần exception. Cần phân biệt lỗi kỹ thuật với một kết quả nghiệp vụ hợp lệ.

Ví dụ, một yêu cầu thanh toán có thể bị ngân hàng từ chối. Đây có thể là kết quả nghiệp vụ bình thường, không phải lỗi hạ tầng. Module Thanh toán có thể ghi nhận trạng thái DECLINED và phát PaymentDeclined. Process manager hoặc module Đơn hàng nhận event này để quyết định hủy đơn hoặc yêu cầu phương thức thanh toán khác.

Ngược lại, nếu gọi ngân hàng bị timeout và không biết giao dịch đã được xử lý hay chưa, đây là trạng thái kỹ thuật không xác định. Không nên chuyển thành PaymentDeclined chỉ để listener kết thúc bình thường.

| Tình huống | Phân loại | Hành vi phù hợp |
|---|---|---|
| Thẻ bị từ chối theo quy tắc ngân hàng | Kết quả nghiệp vụ | Lưu DECLINED và phát event kết quả |
| Dịch vụ thanh toán trả HTTP 503 | Lỗi tạm thời | Ném exception để retry theo chính sách |
| Kết nối timeout, chưa biết giao dịch đã thành công chưa | Kết quả chưa xác định | Đối soát hoặc truy vấn trạng thái trước khi thử lại |
| Payload thiếu trường bắt buộc | Lỗi dữ liệu/contract | Cách ly hoặc dead-letter, tránh retry vô hạn |
| Vi phạm invariant do lỗi lập trình | Lỗi ứng dụng | Để lỗi được nhận diện, cảnh báo và xử lý |
| Đơn hàng không còn ở trạng thái cho phép giao hàng | Kết quả nghiệp vụ hoặc stale event | Ghi nhận quyết định nghiệp vụ theo quy tắc |

Một kết quả nghiệp vụ từ chối cần được biểu diễn trong domain model hoặc event contract. Không sử dụng exception làm cách duy nhất để biểu diễn mọi trường hợp nghiệp vụ không thành công.

## 6. Phân loại lỗi để quyết định retry

Khi listener ném exception, hệ thống cần một chính sách xác định lỗi nào có thể thử lại và lỗi nào cần cách ly. Không nên retry vô hạn mọi loại exception.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout, connection reset, HTTP 503 | Retry với backoff và jitter |
| Quá tải | Rate limit, broker hoặc dịch vụ đích quá tải | Giảm tốc độ và retry sau khoảng chờ |
| Cấu hình | Credential sai, destination không tồn tại | Cảnh báo, sửa cấu hình rồi phục hồi |
| Dữ liệu không hợp lệ | Payload thiếu trường, schema không tương thích | Dead-letter và điều tra |
| Lỗi lập trình | Null bất ngờ, lỗi mapping | Ghi nhận, cảnh báo và sửa lỗi |
| Vi phạm nghiệp vụ | Trạng thái không cho phép hành động | Ghi nhận kết quả hoặc compensation theo quy tắc |

Một retry policy nên quy định số lần thử tối đa, khoảng chờ, nhóm exception được retry, điều kiện chuyển dead-letter và người chịu trách nhiệm phục hồi.

Ví dụ, lỗi timeout có thể retry sau 5 giây, 30 giây và 2 phút. Payload sai schema không nên bị gửi lại hàng nghìn lần vì nguyên nhân sẽ không tự biến mất.

Cần chú ý rằng Event Publication Registry và API resubmit publication chưa hoàn tất không tự định nghĩa đầy đủ retry policy nghiệp vụ. Ứng dụng phải quản lý lịch retry, giới hạn lượt thử, dead-letter và thao tác vận hành phù hợp.

## 7. Transaction rollback và exception

Exception chỉ có thể dẫn đến rollback khi nó xảy ra trong một transaction còn hiệu lực và phù hợp với quy tắc rollback của transaction manager.

Với listener chạy sau commit, transaction phát event đã hoàn tất trước khi listener xử lý. Nếu listener thất bại, không thể rollback giao dịch ban đầu chỉ bằng cách ném exception. Thay vào đó, transaction riêng của listener có thể rollback và publication cần được phục hồi.

Với Spring transaction, mặc định các unchecked exception như RuntimeException thường kích hoạt rollback; checked exception không mặc định rollback trong mọi cấu hình. Có thể khai báo rollbackFor khi nghiệp vụ cần rollback với checked exception:

~~~java
@Transactional(rollbackFor = ExternalServiceException.class)
public void applyPayment(OrderPaid event)
        throws ExternalServiceException {
    paymentRepository.record(event);
    ledgerRepository.update(event);
}
~~~

Cần đặt transaction ở ranh giới phù hợp và kiểm tra exception thực tế. Nếu exception bị bắt bên trong phương thức transactional rồi phương thức trả về bình thường, transaction có thể commit. Nếu transaction đã bị đánh dấu rollback-only ở tầng dưới, việc bắt exception không làm transaction trở lại trạng thái có thể commit.

Không dùng noRollbackFor hoặc bắt exception để che giấu một thay đổi dữ liệu chưa hoàn chỉnh. Chỉ chọn chính sách commit khi trạng thái sau xử lý thực sự hợp lệ.

## 8. Không biến lỗi thành thành công bằng cách trả về mặc định

Một kiểu nuốt lỗi khác là bắt exception rồi trả về giá trị mặc định:

~~~java
boolean reserveInventory(UUID orderId) {
    try {
        return inventoryClient.reserve(orderId);
    } catch (Exception ex) {
        return false;
    }
}
~~~

Nếu caller không phân biệt false do thiếu tồn kho với false do dịch vụ bị timeout, hệ thống có thể đưa ra quyết định nghiệp vụ sai.

Hãy biểu diễn kết quả rõ ràng:

~~~java
sealed interface ReservationResult {
    record Reserved(UUID reservationId)
        implements ReservationResult {}

    record Rejected(String reason)
        implements ReservationResult {}
}
~~~

Kết quả từ chối nghiệp vụ có thể được trả về và lưu trạng thái bình thường. Lỗi kỹ thuật chưa có kết quả đáng tin cậy cần được ném ra hoặc biểu diễn bằng một kiểu kết quả chưa xác định mà workflow biết cách phục hồi. Không ép lỗi kỹ thuật thành một kết quả nghiệp vụ giả.

## 9. Xử lý lỗi có chủ đích và kết thúc publication

Có những trường hợp ứng dụng quyết định không retry một event. Ví dụ, payload cũ không còn tương thích hoặc một đơn hàng đã bị hủy theo quy tắc nghiệp vụ. Trong trường hợp này, listener có thể hoàn tất bình thường sau khi đã lưu quyết định xử lý.

Điều kiện để kết thúc bình thường cần rõ:

1. Đã xác định lỗi hoặc kết quả nghiệp vụ.
2. Đã lưu trạng thái quyết định, lý do và event ID.
3. Đã tạo dead-letter record, yêu cầu compensation hoặc tác vụ điều tra nếu cần.
4. Đã bảo đảm các thao tác lưu trạng thái có transaction phù hợp.
5. Có audit trail để người vận hành biết tại sao event không tiếp tục.

Ví dụ, một handler có thể đưa event không hợp lệ vào bảng quarantine:

~~~java
@Transactional
public void quarantine(InvalidOrderEvent event, String reason) {
    quarantineRepository.save(
        event.eventId(),
        event.orderId(),
        reason,
        Instant.now()
    );
}
~~~

Nếu thao tác quarantine thành công và chính sách quy định event được cách ly thay vì retry, listener có thể kết thúc bình thường. Nếu việc lưu quarantine thất bại, exception cần được truyền ra để publication chưa bị coi là hoàn tất.

Không chỉ log rồi trả về. Log có thể bị mất, không có unique constraint và không đủ để replay hoặc đối soát.

## 10. Kết hợp Event Publication Registry với retry

Event Publication Registry ghi nhận publication cho từng listener. Khi listener thất bại, publication có thể còn incomplete để được resubmit sau khi nguyên nhân được khắc phục.

Trong Spring Modulith, có thể sử dụng API quản lý incomplete publication, chẳng hạn IncompleteEventPublications, để tra cứu hoặc resubmit các publication chưa hoàn tất theo chính sách của ứng dụng. API cụ thể và cách cấu hình storage cần phù hợp với phiên bản Spring Modulith đang dùng.

Một quy trình phục hồi có kiểm soát thường gồm:

1. Tìm publication chưa hoàn tất và xác định listener thất bại.
2. Xem event ID, loại event, thời điểm lỗi và exception gần nhất.
3. Phân loại lỗi là tạm thời, cấu hình, dữ liệu hay nghiệp vụ.
4. Khắc phục nguyên nhân hoặc chọn dead-letter/compensation.
5. Kiểm tra listener có idempotent để chịu được lần giao lại.
6. Resubmit đúng publication cần phục hồi.
7. Xác nhận publication hoàn tất hoặc được cách ly có audit.

Không resubmit hàng loạt một cách mù quáng khi listener đang gặp lỗi diện rộng. Điều đó có thể tạo tải lớn và làm tình trạng sự cố nghiêm trọng hơn.

Registry cũng không thay thế inbox/idempotency. Listener có thể đã commit side effect nhưng publication chưa kịp được đánh dấu hoàn tất; lần resubmit cần được xử lý an toàn.

## 11. Lỗi trong listener bất đồng bộ cần được quan sát riêng

Với listener bất đồng bộ, publisher ban đầu không chờ listener hoàn tất. Vì vậy, việc không thấy exception ở API request hoặc transaction phát event không chứng minh listener đã thành công.

Cần theo dõi trạng thái listener bằng các tín hiệu riêng:

- Số publication incomplete theo listener.
- Tuổi của publication incomplete lâu nhất.
- Tỷ lệ listener thất bại và retry thành công.
- Số event chuyển vào quarantine hoặc dead-letter.
- Số compensation được kích hoạt.
- Thời gian từ lúc event được phát tới lúc listener hoàn tất.

Log có cấu trúc nên chứa event ID, event type, listener ID, module nhận, correlation ID, attempt number và exception type. Không ghi toàn bộ payload nếu có dữ liệu nhạy cảm.

Cảnh báo cần dựa trên tác động nghiệp vụ. Ví dụ, publication của event thanh toán bị treo lâu có thể cần cảnh báo sớm hơn một event phân tích chạy theo lô.

## 12. Idempotency khi listener được retry

Không nuốt lỗi giúp framework biết listener thất bại, nhưng retry có thể khiến listener được gọi nhiều lần. Do đó, mọi side effect cần có cơ chế idempotency phù hợp.

Với side effect trong cùng database, có thể lưu event ID đã xử lý trong cùng transaction với thay đổi nghiệp vụ. Unique constraint giúp hai lần giao đồng thời không cùng thực hiện side effect.

~~~java
@Transactional
public void handle(OrderPaid event) {
    if (!inbox.registerIfAbsent(
            "accounting",
            event.eventId())) {
        return;
    }

    revenueRepository.record(
        event.orderId(),
        event.paymentId(),
        event.amount()
    );
}
~~~

registerIfAbsent cần là thao tác insert nguyên tử dựa trên unique constraint. Nếu thay đổi doanh thu thất bại, inbox marker phải rollback cùng transaction.

Nếu listener gọi hệ thống ngoài, hãy truyền event ID hoặc idempotency key ổn định tới dịch vụ đích nếu dịch vụ hỗ trợ. Nếu kết quả timeout không rõ, truy vấn trạng thái hoặc đối soát trước khi gọi lại thao tác có thể tạo tác dụng phụ.

Không bắt exception để tránh retry nếu chưa có cơ chế idempotency. Điều đó chỉ che giấu lỗi và làm mất khả năng phục hồi.

## 13. Các lỗi thường gặp

**Bắt exception rồi chỉ ghi log.** Listener kết thúc bình thường và publication có thể bị đánh dấu hoàn tất. Hãy ném lại exception nếu công việc chưa hoàn tất.

**Bắt exception rồi trả về giá trị mặc định.** Lỗi kỹ thuật có thể bị hiểu thành kết quả nghiệp vụ. Hãy phân biệt rõ rejected, failed và unknown.

**Nuốt exception trong listener bất đồng bộ.** Publisher không nhận được lỗi và registry có thể không biết listener thất bại. Hãy để exception truyền tới cơ chế quản lý listener.

**Cho rằng exception luôn rollback transaction phát event.** Listener chạy sau commit có transaction riêng. Hãy hiểu rõ transaction phase và rollback boundary.

**Retry vô hạn mọi exception.** Lỗi dữ liệu hoặc cấu hình không tự hết. Hãy phân loại lỗi, giới hạn retry và dùng dead-letter/quarantine.

**Catch Throwable ở mọi tầng.** Điều này có thể che giấu cả lỗi nghiêm trọng của JVM. Chỉ bắt loại exception mà tầng hiện tại có thể xử lý có chủ đích.

**Đánh dấu publication hoàn tất sau khi chỉ ghi log lỗi.** Log không phải trạng thái nghiệp vụ bền vững. Hãy lưu quyết định quarantine, compensation hoặc kết quả xử lý rõ ràng.

**Không thiết kế idempotency.** Khi exception được retry, side effect có thể lặp. Hãy dùng inbox, unique constraint và idempotency key.

## 14. Kiểm thử hành vi khi listener thất bại

Kiểm thử cần chứng minh exception không bị che giấu và publication giữ trạng thái phù hợp.

Các tình huống nên kiểm tra:

- Listener thành công thì publication được đánh dấu hoàn tất.
- Listener ném exception thì publication còn incomplete theo cơ chế registry.
- Listener catch rồi rethrow vẫn giữ được tín hiệu thất bại.
- Listener catch rồi return được nhận diện là hành vi có thể đánh dấu hoàn tất, để tránh vô tình dùng sai.
- Transaction listener rollback khi gặp exception thuộc rollback policy.
- Listener chạy sau commit không làm rollback transaction phát event.
- Lỗi tạm thời được retry theo giới hạn và backoff đã cấu hình.
- Lỗi dữ liệu không bị retry vô hạn mà được cách ly.
- Lỗi khi lưu quarantine vẫn được truyền ra.
- Resubmit không tạo side effect trùng nhờ idempotency.
- Listener bất đồng bộ được quan sát qua publication registry, log và metric.
- Event được xử lý theo quyết định nghiệp vụ từ chối vẫn có trạng thái và audit rõ ràng.

Nên dùng integration test với publication registry và storage thực tế của ứng dụng để kiểm tra trạng thái incomplete. Unit test chỉ xác minh listener ném exception chưa đủ để chứng minh registry và transaction manager hoạt động đúng.

## Kết luận

Không nuốt lỗi giúp giữ đúng tín hiệu giữa listener, transaction và Event Publication Registry. Khi công việc chưa hoàn tất, exception cần được truyền tới cơ chế retry hoặc phục hồi. Khi lỗi đã được xử lý bằng một quyết định nghiệp vụ, ứng dụng phải lưu kết quả đó rõ ràng trước khi listener kết thúc bình thường.

Trong Spring Modulith, listener bất đồng bộ và xử lý sau commit có ranh giới lỗi riêng với publisher ban đầu. Kết hợp exception propagation, phân loại lỗi, retry có giới hạn, quarantine, idempotency và observability giúp event không bị đánh dấu hoàn tất sai và các module có thể phục hồi công việc mà vẫn bảo vệ ranh giới nghiệp vụ.

