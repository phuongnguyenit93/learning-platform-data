# Khóa chống xử lý trùng

Idempotency là khả năng nhận cùng một yêu cầu hoặc event nhiều lần nhưng chỉ tạo ra một kết quả nghiệp vụ như thể nó được xử lý một lần. Trong hệ thống hướng sự kiện, khả năng này rất quan trọng vì message broker, Event Publication Registry và cơ chế retry có thể khiến cùng một event được giao lại.

**Khóa chống xử lý trùng (idempotency key)** là định danh ổn định để consumer nhận ra một công việc đã được xử lý. Với application event, khóa thường dựa trên event ID và phạm vi consumer. Consumer lưu dấu mốc xử lý cùng với thay đổi nghiệp vụ trong một ranh giới transaction phù hợp.

Trong Spring Modulith, Event Publication Registry theo dõi publication tới từng listener và hỗ trợ phục hồi publication chưa hoàn tất. Registry không tự bảo đảm một side effect nghiệp vụ chỉ xảy ra một lần. Listener vẫn cần idempotency vì có thể được gọi lại sau retry, resubmit hoặc khi tiến trình dừng ở thời điểm không rõ kết quả.

## 1. Vì sao cùng một event có thể được xử lý nhiều lần?

Một event có thể được giao lại dù producer và consumer đều hoạt động đúng theo cơ chế phục hồi của chúng. Một số tình huống thường gặp:

- Producer gửi message tới broker thành công nhưng mất kết nối trước khi nhận publisher confirm, sau đó gửi lại.
- Consumer hoàn tất thay đổi database nhưng tiến trình dừng trước khi gửi acknowledgement.
- Listener đã xử lý xong nhưng publication chưa kịp được đánh dấu hoàn tất trong registry.
- Event Publication Registry resubmit một publication còn incomplete.
- Broker giao lại message khi consumer connection hoặc channel đóng trước acknowledgement.
- Người vận hành phát lại message từ dead-letter queue hoặc một công cụ replay.
- Một client gửi lại yêu cầu vì timeout mà không biết lần trước đã thành công hay chưa.

Ví dụ, module Đơn hàng phát OrderPaid để module Kế toán ghi nhận doanh thu. Listener cập nhật database thành công, nhưng tiến trình dừng trước khi publication được xác nhận hoàn tất. Khi phục hồi, cùng event có thể được giao lại. Nếu listener luôn tạo một dòng doanh thu mới, dữ liệu sẽ bị ghi nhận hai lần.

Retry là cơ chế phục hồi; duplicate là một kết quả có thể xảy ra khi phục hồi. Consumer cần được thiết kế để xử lý an toàn cả hai.

## 2. Idempotency key là gì?

Idempotency key là một định danh ổn định cho một lần xử lý logic. Khi cùng một công việc được gửi lại, key phải giữ nguyên để consumer nhận diện đó là lần giao lặp.

Một event thường có các định danh khác nhau với vai trò riêng:

| Định danh | Ý nghĩa | Ví dụ |
|---|---|---|
| eventId | Nhận diện một event cụ thể | UUID của OrderPaid |
| businessId | Nhận diện thực thể nghiệp vụ | orderId |
| sagaId | Nhận diện một quy trình nhiều bước | ID của saga đặt hàng |
| correlationId | Liên kết các hoạt động trong cùng luồng | ID của checkout |
| idempotencyKey | Nhận diện một lần xử lý logic tại một consumer | accounting:producer-a:event-uuid |

Trong nhiều trường hợp, event ID có thể được dùng làm idempotency key. Tuy nhiên, key cần có phạm vi rõ ràng. Nếu một event được gửi đến hai listener độc lập, việc listener A đã xử lý không được làm listener B bỏ qua event.

Một khóa lưu trữ phổ biến là:

~~~text
(consumer_id, producer_id, event_id)
~~~

Nếu event ID được bảo đảm duy nhất toàn hệ thống, có thể bỏ producer_id. Nếu ID chỉ duy nhất trong từng producer, phải giữ producer_id trong khóa. consumer_id xác định handler hoặc nhóm xử lý chịu trách nhiệm cho side effect đó.

Không tạo event ID mới trong mỗi lần retry. Event ID phải được sinh khi event được tạo và giữ nguyên trong suốt vòng đời gửi, giao lại và replay.

## 3. Phân biệt duplicate delivery và duplicate nghiệp vụ

Có hai trường hợp dễ bị nhầm:

**Duplicate delivery** là cùng một event được giao nhiều lần, thường có cùng event ID. Đây là trường hợp idempotency key dựa trên event ID xử lý tốt.

**Duplicate nghiệp vụ** là hai event khác event ID nhưng cùng biểu diễn một hành động nghiệp vụ đã xảy ra. Ví dụ, hai message khác ID cùng yêu cầu ghi nhận một khoản thanh toán có cùng paymentTransactionId.

Bảng inbox theo event ID chỉ loại được lần giao lại của cùng event. Nó không tự loại được hai event khác ID nhưng cùng đại diện cho một giao dịch. Với trường hợp thứ hai, cần thêm ràng buộc nghiệp vụ như unique constraint trên paymentTransactionId, invoiceNumber hoặc khóa giao dịch của hệ thống nguồn.

Ví dụ:

| Tình huống | Cơ chế bảo vệ phù hợp |
|---|---|
| Cùng OrderPaid được giao lại | Unique key theo consumer và eventId |
| Hai event khác ID cùng tham chiếu một payment transaction | Unique constraint theo paymentTransactionId |
| Client gửi lại cùng lệnh tạo đơn | Idempotency key của request và ràng buộc đơn hàng |
| Cùng event đến hai listener độc lập | Inbox riêng theo từng consumer |
| Event cũ đến sau event mới | Sequence/version check ngoài deduplication |

Không nên dùng orderId làm khóa duy nhất cho mọi event của đơn hàng. Một đơn có thể hợp lệ phát nhiều event khác nhau như OrderPaid, OrderPacked và OrderShipped. Khóa chống trùng phải nhận diện đúng một hành động, không chặn các bước nghiệp vụ hợp lệ.

## 4. Inbox pattern và bảng lưu dấu mốc

Inbox pattern lưu dấu mốc event đã được consumer xử lý. Bảng inbox cần có khóa duy nhất để database bảo vệ trước cả những lần giao trùng đồng thời.

Ví dụ cấu trúc:

~~~sql
CREATE TABLE processed_events (
    consumer_id   VARCHAR(120) NOT NULL,
    producer_id   VARCHAR(120) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_id, producer_id, event_id)
);
~~~

Khi consumer nhận event, nó cố gắng ghi key vào inbox. Nếu key đã tồn tại, event đã được xử lý trước đó trong phạm vi consumer này. Nếu insert thành công, consumer tiếp tục thay đổi nghiệp vụ trong cùng transaction.

Với PostgreSQL, thao tác nhận quyền xử lý có thể dùng ON CONFLICT DO NOTHING:

~~~sql
INSERT INTO processed_events (
    consumer_id,
    producer_id,
    event_id,
    processed_at
)
VALUES (
    :consumerId,
    :producerId,
    :eventId,
    CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_id, producer_id, event_id)
DO NOTHING;
~~~

Nếu số dòng được insert bằng 1, đây là lần xử lý đầu tiên. Nếu số dòng bằng 0, key đã tồn tại và consumer có thể kết thúc lần giao này như một duplicate đã hoàn tất.

Cú pháp trên là ví dụ cho PostgreSQL. Với hệ quản trị khác, dùng cơ chế insert-if-absent hoặc unique constraint tương đương. Điểm cốt lõi là quyết định nhận key phải nguyên tử ở database; kiểm tra bằng một câu SELECT riêng rồi mới INSERT không đủ an toàn khi có nhiều consumer chạy đồng thời.

## 5. Ghi inbox và thay đổi nghiệp vụ trong cùng transaction

Với side effect nằm trong cùng database, inbox marker và thay đổi nghiệp vụ phải commit hoặc rollback cùng nhau.

~~~mermaid
flowchart TD
    A["Consumer nhận event"] --> B["BEGIN transaction"]
    B --> C["Insert idempotency key"]
    C --> D{"Insert thành công?"}
    D -->|Không, key đã tồn tại| E["Bỏ qua duplicate"]
    D -->|Có| F["Cập nhật dữ liệu nghiệp vụ"]
    F --> G{"Nghiệp vụ thành công?"}
    G -->|Có| H["COMMIT inbox + dữ liệu"]
    G -->|Không| I["ROLLBACK cả hai"]
    H --> J["ACK / hoàn tất publication"]
    E --> J
    I --> K["Retry theo chính sách"]
~~~

Nếu thay đổi nghiệp vụ thất bại, transaction rollback cả inbox marker. Lần giao tiếp theo vẫn có thể thử xử lý. Nếu marker được commit trước, rồi tiến trình dừng trước khi cập nhật dữ liệu, lần retry sẽ thấy key đã tồn tại và bỏ qua công việc chưa hoàn tất.

Ví dụ service xử lý:

~~~java
@Service
class AccountingEventHandler {

    private final ProcessedEventRepository inbox;
    private final RevenueRepository revenue;

    AccountingEventHandler(
            ProcessedEventRepository inbox,
            RevenueRepository revenue) {
        this.inbox = inbox;
        this.revenue = revenue;
    }

    @Transactional
    public void handle(OrderPaid event) {
        boolean firstDelivery = inbox.registerIfAbsent(
            "accounting",
            event.producerId(),
            event.eventId()
        );

        if (!firstDelivery) {
            return;
        }

        revenue.record(
            event.orderId(),
            event.paymentTransactionId(),
            event.amount(),
            event.currency()
        );
    }
}
~~~

registerIfAbsent là phương thức repository do ứng dụng định nghĩa, cần được triển khai bằng thao tác insert nguyên tử và unique constraint. Ví dụ giả định inbox và revenue dùng cùng database transaction manager. Nếu hai repository thuộc hai database hoặc transaction manager khác nhau, một @Transactional thông thường không làm chúng trở thành một giao dịch nguyên tử.

Listener có thể gọi service này:

~~~java
@Component
class AccountingListener {

    private final AccountingEventHandler handler;

    AccountingListener(AccountingEventHandler handler) {
        this.handler = handler;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        handler.handle(event);
    }
}
~~~

Ví dụ minh họa cách tách listener khỏi xử lý nghiệp vụ. Cần bảo đảm transaction thực sự bao trùm cả inbox và thay đổi dữ liệu, theo cấu hình Spring và cách listener được gọi. Không đặt @Transactional lên một lời gọi nội bộ cùng bean rồi giả định proxy transaction luôn được kích hoạt.

## 6. Vì sao SELECT rồi INSERT không đủ?

Một cách làm tưởng như hợp lý là kiểm tra key đã tồn tại hay chưa, nếu chưa thì xử lý rồi lưu key:

~~~java
if (!inbox.existsByEventId(event.eventId())) {
    revenue.record(event);
    inbox.save(event.eventId());
}
~~~

Cách này có race condition. Hai thread hoặc hai instance có thể cùng đọc kết quả "chưa tồn tại", sau đó cả hai cùng ghi nhận doanh thu. Một lần kiểm tra ở tầng ứng dụng không khóa được toàn bộ tiến trình trên nhiều instance.

Hãy để database thực hiện kiểm tra và chiếm key bằng một thao tác nguyên tử. Unique constraint là lớp bảo vệ cuối cùng ngay cả khi hai consumer cùng nhận message trong cùng thời điểm.

Nếu dùng database không hỗ trợ insert-if-absent trực tiếp, có thể dùng insert và xử lý vi phạm unique constraint theo cách phù hợp với transaction manager. Cần kiểm tra trạng thái transaction sau lỗi constraint; một số hệ quản trị đánh dấu transaction không thể tiếp tục sau lỗi, nên không thể đơn giản bắt exception rồi thực hiện thêm truy vấn trong cùng transaction.

## 7. Idempotency với side effect ở hệ thống bên ngoài

Không phải mọi side effect đều nằm trong database của consumer. Listener có thể gọi payment gateway, gửi email, tạo vận đơn hoặc gọi API của một dịch vụ khác.

Không thể dùng một transaction database để rollback side effect đã xảy ra ở hệ thống từ xa. Ví dụ:

1. Consumer gọi payment gateway và giao dịch thành công.
2. Gateway trả kết quả thành công.
3. Consumer dừng trước khi lưu kết quả và inbox marker.
4. Message được giao lại.
5. Consumer gọi gateway lần nữa.

Nếu gateway hỗ trợ idempotency key, hãy truyền cùng một key trong mọi lần gọi lại. Gateway sẽ nhận diện yêu cầu lặp và trả về kết quả của giao dịch đã tạo thay vì thực hiện giao dịch mới.

~~~java
paymentGateway.capture(
    paymentId,
    event.amount(),
    event.eventId().toString()
);
~~~

Ở đây event ID chỉ là ví dụ về key. Contract với dịch vụ đích phải quy định key có phạm vi nào, được lưu trong bao lâu và hành vi khi cùng key được gửi với payload khác nhau.

Nếu dịch vụ đích không hỗ trợ idempotency, hãy dùng một workflow bền vững để theo dõi trạng thái như PENDING, REQUESTED, SUCCEEDED, FAILED hoặc UNKNOWN. Khi timeout không rõ kết quả, truy vấn trạng thái hoặc đối soát trước khi gửi lại thao tác có thể tạo tác dụng phụ. Không tự coi timeout là thất bại.

## 8. Idempotency key cho API và command

Nguyên tắc tương tự áp dụng cho API nhận yêu cầu có thể được client gửi lại. Client tạo một idempotency key cho một ý định nghiệp vụ và giữ nguyên key khi retry.

Ví dụ, client gửi lệnh tạo thanh toán với key checkout-2026-00421. Server lưu key, request hash và kết quả. Nếu nhận lại cùng key và cùng request, server trả lại kết quả đã lưu. Nếu cùng key nhưng payload khác, server từ chối vì client đang dùng một key cho hai ý định khác nhau.

Một record request có thể lưu:

- idempotency key và phạm vi client/tenant.
- Hash của payload đã chuẩn hóa.
- Trạng thái xử lý.
- Kết quả hoặc resource ID được tạo.
- Thời điểm bắt đầu, hoàn tất và hết hạn.
- Mã lỗi có thể trả lại khi request được gửi lại.

Không dùng một key toàn cục cho mọi request. Key cần được giới hạn theo client, tenant hoặc loại operation để tránh xung đột giữa các bên không liên quan.

## 9. Idempotency không thay thế kiểm tra thứ tự

Deduplication ngăn cùng một event được áp dụng nhiều lần. Nó không ngăn event cũ đến sau event mới.

Ví dụ, consumer nhận OrderShipped trước rồi mới nhận OrderPaid do retry hoặc cấu hình giao nhận. Cả hai event đều có ID khác nhau, vì vậy inbox sẽ coi cả hai là event mới. Nếu consumer áp dụng mù quáng, trạng thái đơn hàng có thể bị lùi.

Với aggregate có thứ tự, hãy mang version hoặc sequence number trong event:

~~~json
{
  "eventId": "e9f2d2b3-44b2-4a73-aaf4-3f31f5e6e2c1",
  "orderId": "ORD-42",
  "aggregateVersion": 7,
  "eventType": "OrderShipped"
}
~~~

Consumer kiểm tra version so với trạng thái đã lưu. Event có version cũ hoặc không hợp lệ được xử lý theo chính sách stale-event; event có khoảng trống version có thể được chờ, truy vấn bổ sung hoặc yêu cầu đồng bộ lại.

Idempotency và ordering giải quyết hai vấn đề khác nhau: một bên ngăn áp dụng cùng công việc lặp lại, bên kia bảo vệ trình tự hợp lệ của các thay đổi.

## 10. Idempotency trong Spring Modulith

Spring Modulith Event Publication Registry ghi nhận publication tới từng listener. Với registry lưu bền vững, ứng dụng có thể tìm và resubmit publication chưa hoàn tất sau lỗi. Đây là cơ chế phục hồi delivery ở phía ứng dụng.

Idempotency bảo vệ side effect ở phía listener. Hai cơ chế bổ sung cho nhau:

| Cơ chế | Câu hỏi được trả lời |
|---|---|
| Event Publication Registry | Publication tới listener đã được ghi nhận hoàn tất chưa? |
| Inbox/idempotency store | Consumer này đã áp dụng event này vào nghiệp vụ chưa? |
| Broker acknowledgement | Consumer đã xác nhận delivery với broker chưa? |
| Saga state store | Quy trình nhiều bước đang ở trạng thái nào? |

Nếu listener commit dữ liệu nghiệp vụ nhưng tiến trình dừng trước khi registry ghi nhận publication hoàn tất, registry có thể resubmit. Inbox sẽ nhận diện event đã xử lý và bỏ qua side effect trùng; listener có thể hoàn tất lần giao lại để publication được đánh dấu hoàn tất.

Registry không phải bảng chống trùng nghiệp vụ và không thay thế unique constraint trong database của consumer. Ngược lại, inbox không thay thế publication registry vì inbox không giúp producer biết publication nào chưa giao thành công.

Với listener bất đồng bộ hoặc externalized event, cần xem xét transaction phase, publication storage và cơ chế acknowledgement thực tế của integration. Không suy ra rằng event đã được xử lý cuối cùng chỉ vì producer publication đã hoàn tất.

## 11. Giữ idempotency record trong bao lâu?

Nếu xóa inbox record quá sớm, một event cũ được replay có thể được xử lý như mới. Thời gian lưu cần dựa trên toàn bộ cửa sổ mà event có thể xuất hiện lại:

- Retention của broker và dead-letter queue.
- Khoảng thời gian Event Publication Registry có thể resubmit.
- Thời hạn retry của consumer và retry queue.
- Chính sách replay hoặc backfill của đội vận hành.
- Thời gian lưu trữ backup có thể được phục hồi.
- Yêu cầu đối soát và audit của nghiệp vụ.

Với event tài chính hoặc giao dịch quan trọng, có thể cần lưu dấu mốc lâu dài hoặc giữ một ràng buộc nghiệp vụ bền vững thay cho việc chỉ dựa trên bảng inbox có TTL.

Nếu bảng inbox tăng lớn, có thể partition hoặc archive theo thời gian. Trước khi xóa, phải xác định rõ event cũ không còn được phép replay hoặc hệ thống vẫn có một lớp bảo vệ nghiệp vụ khác. TTL là chính sách lưu trữ, không phải một giá trị kỹ thuật có thể chọn tùy tiện.

## 12. Xử lý trạng thái đang chạy và công việc kéo dài

Với xử lý ngắn nằm trong một database transaction, insert inbox marker và thay đổi nghiệp vụ cùng commit là mô hình đơn giản nhất.

Với công việc kéo dài hoặc gọi nhiều hệ thống, không thể giữ một transaction mở trong suốt quá trình. Khi đó có thể dùng bảng inbox/work item với trạng thái:

~~~text
RECEIVED
PROCESSING
SUCCEEDED
RETRY_WAIT
FAILED
NEEDS_RECONCILIATION
~~~

Khi nhận event, consumer ghi work item bằng unique idempotency key. Một worker lấy việc theo lease hoặc cơ chế claim có thời hạn. Khi worker chết, lease hết hạn và công việc có thể được nhận lại. Các bước phải có checkpoint và idempotency riêng để lần chạy lại tiếp tục an toàn.

Không để trạng thái PROCESSING tồn tại vô hạn mà không có lease, heartbeat hoặc cơ chế phục hồi. Không đánh dấu SUCCEEDED trước khi side effect quan trọng hoàn tất. Nếu kết quả bên ngoài không rõ do timeout, dùng NEEDS_RECONCILIATION để kiểm tra trước khi thử lại.

## 13. Bảo đảm idempotency khi phát command tiếp theo

Một handler có thể vừa cập nhật database vừa phát event hoặc gửi command tiếp theo. Nếu cập nhật trạng thái và gửi message là hai thao tác độc lập, tiến trình có thể dừng giữa hai bước.

Ví dụ, handler ghi nhận InventoryReserved và gửi AuthorizePayment. Nếu database commit nhưng gửi command thất bại, saga có thể bị kẹt. Nếu gửi command thành công nhưng tiến trình dừng trước khi ghi nhận kết quả gửi, command có thể được gửi lại.

Transactional outbox giúp ghi nhận message cần gửi cùng transaction với thay đổi nghiệp vụ. Một publisher riêng đọc outbox và gửi message, có retry và event ID ổn định. Consumer của command tiếp tục dùng inbox/idempotency để xử lý duplicate.

Outbox và inbox bổ sung nhau:

- Outbox bảo vệ việc phát thông điệp sau khi thay đổi dữ liệu commit.
- Inbox bảo vệ việc áp dụng thông điệp ở phía nhận.
- Idempotency key giữ side effect an toàn khi bất kỳ chặng nào được retry.

Không có một khóa chống trùng duy nhất thay thế được việc phối hợp các ranh giới transaction trong toàn hệ thống.

## 14. Kiểm thử idempotency

Kiểm thử phải chứng minh hai lần giao cùng event chỉ tạo một kết quả nghiệp vụ, kể cả khi có lỗi hoặc xử lý đồng thời.

Các tình huống nên kiểm thử:

- Giao cùng event hai lần tuần tự chỉ tạo một side effect.
- Hai thread hoặc hai instance cùng xử lý một event chỉ có một lần chiếm được inbox key.
- Lỗi nghiệp vụ làm rollback cả inbox marker và dữ liệu.
- Database commit xong nhưng consumer mất acknowledgement; lần giao lại không tạo side effect trùng.
- Hai event ID khác nhau nhưng cùng paymentTransactionId bị chặn bởi ràng buộc nghiệp vụ.
- Hai consumer độc lập có thể xử lý cùng event vì inbox key có consumer scope.
- Event cũ đến sau event mới được xử lý theo version/sequence policy.
- Cùng API idempotency key với payload khác bị từ chối.
- Gọi dịch vụ ngoài với cùng idempotency key không tạo giao dịch thứ hai.
- Event replay sau thời gian dài vẫn được bảo vệ theo retention policy.
- Worker dừng ở trạng thái PROCESSING có thể phục hồi qua lease hoặc reconciliation.

Với kiểm thử concurrency, không chỉ mock repository. Hãy dùng database thật hoặc môi trường tương thích để xác minh unique constraint và transaction isolation thực tế. Với external side effect, dùng stub có khả năng ghi nhận số lần thực thi theo idempotency key và mô phỏng timeout sau khi đã thực hiện.

## 15. Lỗi thiết kế thường gặp

**Tạo event ID mới mỗi lần retry.** Consumer sẽ coi mỗi lần giao là event khác. Hãy tạo ID một lần khi event được hình thành và giữ nguyên qua retry.

**Dùng SELECT rồi INSERT như một thao tác chống trùng.** Hai instance có thể cùng vượt qua bước kiểm tra. Hãy dùng unique constraint và insert nguyên tử.

**Lưu inbox marker trong transaction riêng trước nghiệp vụ.** Nếu tiến trình dừng sau khi lưu marker, lần retry có thể bỏ qua công việc chưa hoàn tất. Hãy commit marker cùng thay đổi nghiệp vụ khi chúng cùng database.

**Dùng eventId làm khóa cho mọi consumer.** Listener này có thể vô tình chặn listener khác. Hãy thêm consumer identity vào phạm vi key.

**Chỉ chống duplicate delivery mà bỏ qua duplicate nghiệp vụ.** Hai event ID khác nhau vẫn có thể đại diện cho cùng một giao dịch. Hãy thêm unique constraint theo business key.

**Ack message trước khi xử lý bền vững.** Broker có thể loại message trong khi nghiệp vụ chưa commit. Hãy ack sau khi transaction hoặc work item bền vững hoàn tất theo thiết kế.

**Coi idempotency là exactly-once delivery.** Broker vẫn có thể giao trùng. Mục tiêu là làm side effect có hiệu lực một lần trong phạm vi nghiệp vụ đã định nghĩa.

**Xóa inbox record quá sớm.** Replay hoặc redelivery cũ có thể chạy lại. Hãy gắn retention với cửa sổ retry, replay và yêu cầu audit.

**Bỏ qua side effect ở hệ thống ngoài.** Database transaction không rollback được API từ xa. Hãy dùng idempotency key phía dịch vụ đích hoặc quy trình đối soát.

## Kết luận

Khóa chống xử lý trùng giúp consumer nhận diện một event hoặc yêu cầu đã được áp dụng. Với application event, key thường kết hợp consumer identity, producer identity và event ID. Inbox pattern cùng unique constraint giúp chiếm key nguyên tử; thay đổi nghiệp vụ và inbox marker cần commit trong cùng transaction khi chúng nằm trong cùng database.

Trong Spring Modulith, Event Publication Registry hỗ trợ theo dõi và phục hồi publication, còn idempotency bảo vệ side effect khi listener được gọi lại. Khi kết hợp inbox/outbox, idempotency key ở dịch vụ ngoài, version check, retention và kiểm thử concurrency, hệ thống có thể retry và replay event mà vẫn giữ kết quả nghiệp vụ nhất quán.

