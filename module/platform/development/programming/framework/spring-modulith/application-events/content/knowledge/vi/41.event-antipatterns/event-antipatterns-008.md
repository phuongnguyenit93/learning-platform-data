# Không có idempotency

Không có idempotency là một anti-pattern trong hệ thống hướng sự kiện: consumer thực hiện side effect mỗi lần nhận message mà không nhận diện được lần giao lại của cùng một công việc. Khi broker giao trùng, listener được retry hoặc publication được phục hồi, cùng một event có thể tạo nhiều bản ghi, trừ tồn kho nhiều lần, gửi nhiều email hoặc capture thanh toán lặp.

Vấn đề thường không xuất hiện trong happy path. Producer phát event, consumer nhận một lần và mọi thứ có vẻ đúng. Lỗi chỉ lộ ra khi tiến trình dừng ở một thời điểm không thuận lợi, acknowledgement bị mất, network timeout hoặc operator replay message. Vì vậy, kiểm thử bằng một lần publish thành công không chứng minh consumer an toàn.

Trong Spring Modulith, application events giúp các module giao tiếp qua hợp đồng nghiệp vụ và Event Publication Registry theo dõi publication tới listener. Registry có thể hỗ trợ phục hồi publication chưa hoàn tất; listener vì thế cần chịu được việc được gọi lại. Idempotency bảo vệ side effect nghiệp vụ khi điều đó xảy ra. Đây là yêu cầu thiết kế của consumer, không phải thuộc tính tự có của broker hay registry.

## 1. Anti-pattern không có idempotency là gì?

Một handler không idempotent tạo ra kết quả khác nhau mỗi lần chạy, dù đầu vào đại diện cho cùng một hành động nghiệp vụ. Ví dụ:

~~~java
@ApplicationModuleListener
void on(OrderPaid event) {
    accountingRepository.insertRevenue(
        event.orderId(),
        event.amount()
    );
}
~~~

Nếu cùng OrderPaid được giao hai lần, code trên có thể tạo hai dòng doanh thu. Handler không lưu dấu mốc đã xử lý, không có unique constraint bảo vệ và không kiểm tra giao dịch nghiệp vụ đã được áp dụng hay chưa.

Idempotency là thuộc tính mà khi cùng một yêu cầu logic được áp dụng nhiều lần, trạng thái nghiệp vụ cuối cùng tương đương với việc áp dụng một lần. Trong event processing, điều này thường được thực hiện bằng idempotency key ổn định, inbox record và ràng buộc duy nhất ở database.

Không nên nhầm idempotency với việc handler được gọi đúng một lần. Hệ thống phân tán thường phải chấp nhận delivery có thể lặp. Mục tiêu thực tế là ngăn side effect bị nhân đôi dù lần giao hoặc lần chạy có thể xảy ra nhiều lần.

## 2. Vì sao event có thể được giao nhiều lần?

Duplicate delivery là một phần bình thường của nhiều cơ chế phục hồi. Một số tình huống điển hình:

- Producer gửi message tới broker thành công nhưng mất kết nối trước khi nhận publisher confirm, nên gửi lại.
- Consumer commit database thành công rồi dừng trước khi gửi acknowledgement.
- Broker đã giao message nhưng consumer connection đóng trước khi broker nhận ack.
- Listener xử lý xong nhưng Event Publication Registry chưa kịp ghi nhận publication hoàn tất.
- Publication chưa hoàn tất được resubmit sau khi ứng dụng khởi động lại.
- Retry queue, dead-letter redrive hoặc công cụ replay đưa message cũ trở lại.
- Client gửi lại command sau timeout vì không biết lần trước đã thành công hay chưa.
- Hai consumer instance nhận cùng logical event trong khoảng thời gian chồng lấn.

Ví dụ với RabbitMQ, consumer cập nhật database rồi process chết trước basicAck. Broker có thể giao message lại. Với Kafka, consumer xử lý record rồi dừng trước khi commit offset; record có thể được đọc lại sau khi consumer group rebalance hoặc khởi động lại.

Các chi tiết delivery khác nhau theo broker và cấu hình, nhưng cùng một nguyên tắc: consumer không được giả định mỗi event chỉ xuất hiện một lần.

## 3. Failure window tạo side effect trùng

Một lỗi phổ biến là side effect và acknowledgement nằm ở hai hệ thống khác nhau. Không có transaction nguyên tử bao trùm cả database và broker, nên luôn có một khoảng thời gian mà consumer không thể biết chắc cả hai bên đã hoàn tất hay chưa.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Database
    B->>C: Deliver OrderPaid
    C->>D: Insert revenue
    D-->>C: Commit success
    Note over C: Process stops before ACK
    B->>C: Redeliver OrderPaid
    C->>D: Insert revenue again
    D-->>C: Commit duplicate
    C->>B: ACK
~~~

Nếu consumer ack trước khi commit database, một failure window khác xuất hiện: broker loại message nhưng database chưa lưu nghiệp vụ. Khi đó event có thể bị mất khỏi luồng xử lý.

Nếu consumer commit trước rồi ack, duplicate có thể xảy ra khi ack thất bại. Đây thường là lựa chọn phù hợp hơn với at-least-once processing, nhưng yêu cầu idempotency để lần giao lại không lặp side effect.

Không có thứ tự đơn giản giữa hai thao tác độc lập nào tự tạo ra exactly-once end-to-end. Cần kết hợp transaction local, inbox/outbox, idempotency key và phục hồi có kiểm soát.

## 4. Hậu quả nghiệp vụ

Thiếu idempotency không chỉ làm tăng số dòng dữ liệu. Nó có thể phá vỡ invariant và tạo tác động khó đảo ngược.

| Nghiệp vụ | Side effect trùng | Hậu quả |
|---|---|---|
| Kế toán | Ghi doanh thu hai lần | Báo cáo và sổ cái sai |
| Kho | Trừ tồn kho hai lần | Tồn kho âm hoặc thiếu hàng giả |
| Thanh toán | Capture cùng giao dịch nhiều lần | Thu tiền khách nhiều lần |
| Giao hàng | Tạo nhiều vận đơn | Giao trùng và tăng chi phí |
| Thông báo | Gửi email/SMS lặp | Trải nghiệm khách hàng kém |
| Loyalty | Cộng điểm nhiều lần | Phát sinh quyền lợi sai |
| Process manager | Tạo cùng bước saga nhiều lần | Trạng thái quy trình không nhất quán |

Một số side effect có thể sửa bằng cách xóa bản ghi trùng. Một số khác cần compensation, hoàn tiền, thu hồi vận đơn hoặc liên hệ khách hàng. Càng gần hệ thống tài chính hoặc hệ thống bên ngoài, chi phí khắc phục càng lớn.

Không nên đánh giá mức độ nghiêm trọng chỉ bằng số lượng duplicate. Hãy xem side effect có thể đảo ngược không, dữ liệu có ảnh hưởng đến hệ thống khác không và việc đối soát có xác định được bản ghi đúng hay không.

## 5. Những dấu hiệu nhận biết

Anti-pattern này thường có các biểu hiện:

- Listener insert hoặc update mà không có event ID, business key hay inbox marker.
- Cùng một event xuất hiện nhiều lần trong log nhưng tạo nhiều kết quả nghiệp vụ.
- Retry làm tăng số bản ghi hoặc gửi lại cùng thông báo.
- Replay từ DLQ tạo giao dịch mới dù giao dịch trước đã thành công.
- Hai instance xử lý đồng thời cùng event và cùng ghi side effect.
- Timeout của API bên ngoài dẫn đến gọi lại thao tác có thể tính phí.
- Database không có unique constraint cho logical operation.
- Test chỉ chạy một lần publish và không mô phỏng redelivery.
- Team tin rằng broker hoặc Event Publication Registry bảo đảm exactly-once.

Một dấu hiệu khác là code dùng câu kiểm tra rồi mới insert:

~~~java
if (!repository.existsByEventId(event.eventId())) {
    repository.save(toRecord(event));
}
~~~

Đoạn code này vẫn có race condition. Hai thread có thể cùng đọc kết quả chưa tồn tại và cùng thực hiện insert. Kiểm tra ở tầng ứng dụng không thay thế unique constraint và thao tác nhận key nguyên tử trong database.

## 6. Event ID và idempotency key phải ổn định

Event ID nhận diện một event cụ thể. Idempotency key nhận diện một lần xử lý logic trong phạm vi consumer hoặc operation. Trong nhiều thiết kế, event ID là thành phần chính của key.

Một khóa có thể gồm:

~~~text
(consumer_id, producer_id, event_id)
~~~

consumer_id phân biệt các listener độc lập. Cùng event có thể hợp lệ được xử lý bởi module Kế toán và module Thông báo; việc Kế toán đã xử lý không được làm Thông báo bỏ qua event.

producer_id cần thiết nếu event ID chỉ duy nhất trong phạm vi producer. Nếu event ID được bảo đảm duy nhất toàn hệ thống, có thể không cần thành phần này.

Không tạo event ID mới khi retry hoặc redrive. Nếu mỗi lần gửi lại lại sinh UUID mới, consumer sẽ coi các lần giao là công việc khác nhau và deduplication mất tác dụng.

Correlation ID thường liên kết nhiều event trong một workflow. Không dùng correlation ID làm idempotency key nếu một workflow có nhiều event hợp lệ, vì các event khác nhau sẽ bị gộp thành một.

## 7. Inbox pattern và unique constraint

Inbox pattern lưu dấu mốc event đã được consumer xử lý. Database bảo vệ key bằng unique constraint, nhờ đó hai lần giao đồng thời cũng không thể cùng chiếm quyền xử lý.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_events (
    consumer_id   VARCHAR(120) NOT NULL,
    producer_id   VARCHAR(120) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_id, producer_id, event_id)
);
~~~

Với PostgreSQL, có thể dùng INSERT ... ON CONFLICT DO NOTHING để đăng ký key nguyên tử:

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

Nếu insert tạo một dòng, consumer đã chiếm key và có thể thực hiện nghiệp vụ. Nếu không có dòng mới, key đã tồn tại; consumer có thể kết thúc lần giao này như một duplicate đã xử lý.

Câu lệnh trên là ví dụ PostgreSQL. Với database khác, dùng cơ chế insert-if-absent hoặc unique constraint tương đương. Không thay thao tác nguyên tử bằng SELECT rồi INSERT.

## 8. Ghi inbox và side effect trong cùng transaction

Với side effect nằm trong cùng database, inbox marker và thay đổi nghiệp vụ phải commit hoặc rollback cùng nhau.

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

registerIfAbsent phải dựa trên insert nguyên tử và unique constraint. Nếu revenue.record thất bại, transaction rollback cả inbox marker. Lần giao sau vẫn có thể thử xử lý.

Listener có thể ủy quyền cho service:

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

Tách listener và service giúp transaction proxy hoạt động ở lời gọi qua bean. Không đặt @Transactional ở một phương thức rồi gọi nội bộ cùng bean và mặc định rằng proxy transaction luôn được kích hoạt.

Ví dụ giả định inbox và revenue cùng database và transaction manager. Nếu chúng thuộc hai database khác nhau, một @Transactional thông thường không làm chúng thành một giao dịch nguyên tử.

## 9. Không dùng event ID để chặn mọi duplicate nghiệp vụ

Inbox theo event ID xử lý tốt trường hợp cùng một event được giao lại. Nó không tự phát hiện hai event có ID khác nhau nhưng cùng biểu diễn một giao dịch nghiệp vụ.

Ví dụ hai message khác eventId cùng chứa paymentTransactionId = PAY-9001. Có thể producer đã phát cùng hành động hai lần, hoặc hai adapter tạo hai event cho cùng một giao dịch.

Trong trường hợp này cần thêm ràng buộc theo business key:

~~~sql
ALTER TABLE revenue_entries
ADD CONSTRAINT uq_revenue_payment
UNIQUE (payment_transaction_id);
~~~

Các ví dụ khác:

| Logical operation | Business key có thể dùng |
|---|---|
| Ghi nhận thanh toán | paymentTransactionId |
| Tạo vận đơn | shipmentRequestId hoặc orderId theo quy tắc |
| Cộng điểm | loyaltyOperationId |
| Phát hành hóa đơn | invoiceRequestId |
| Giữ một dòng hàng | orderId + lineItemId + reservationType |

Không dùng orderId làm unique key cho mọi event của đơn hàng. Một đơn có thể hợp lệ phát OrderPaid, OrderPacked và OrderShipped. Khóa phải nhận diện đúng một hành động, không chặn các bước nghiệp vụ khác nhau.

Nếu cùng business key nhưng payload khác nhau, không coi đó là duplicate bình thường. Ghi nhận conflict, so sánh payload hash và cách ly để điều tra.

## 10. Idempotency với side effect bên ngoài

Database transaction không thể rollback một API đã thực hiện ở hệ thống từ xa. Ví dụ listener gọi payment gateway, gateway capture thành công nhưng response bị mất. Consumer không biết giao dịch đã thành công và có thể gọi lại.

Nếu dịch vụ đích hỗ trợ idempotency key, hãy gửi cùng một key trong mọi lần retry:

~~~java
paymentGateway.capture(
    event.paymentTransactionId(),
    event.amount(),
    event.eventId().toString()
);
~~~

Contract của dịch vụ đích cần quy định phạm vi key, thời gian lưu key và hành vi khi cùng key được gửi với payload khác nhau. Nếu cùng key nhưng amount khác, dịch vụ nên từ chối thay vì trả kết quả cũ một cách mơ hồ.

Nếu dịch vụ đích không hỗ trợ idempotency, hãy lưu workflow state như REQUESTED, SUCCEEDED, FAILED hoặc UNKNOWN. Khi timeout không rõ kết quả, truy vấn trạng thái hoặc đối soát trước khi gọi lại thao tác có thể tạo tác động không đảo ngược.

Không coi timeout là thất bại chắc chắn. Timeout chỉ cho biết consumer không nhận được kết quả trong thời hạn; side effect ở phía xa có thể đã hoàn tất.

## 11. Idempotency cho API command

Cùng anti-pattern xuất hiện khi client gửi lại API request sau timeout hoặc mất kết nối. Ví dụ người dùng bấm thanh toán hai lần hoặc HTTP client tự retry POST.

API có thể nhận Idempotency-Key trong header và lưu:

- Key cùng phạm vi client hoặc tenant.
- Hash của request đã chuẩn hóa.
- Trạng thái xử lý và thời điểm bắt đầu.
- Kết quả hoặc resource ID đã tạo.
- Thời điểm hoàn tất và thời hạn lưu key.

Khi nhận lại cùng key và cùng payload, server trả lại kết quả đã lưu. Nếu cùng key nhưng payload khác, server từ chối vì một key không được đại diện cho hai ý định nghiệp vụ.

Key cần có scope. Không dùng một key toàn cục cho mọi client. Đồng thời, không dùng request ID mới cho mỗi lần retry; client phải giữ nguyên key cho cùng ý định.

## 12. Retry và Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication tới từng listener. Với registry lưu bền vững, ứng dụng có thể tìm và resubmit publication chưa hoàn tất sau lỗi.

Một tình huống quan trọng:

1. Listener cập nhật doanh thu và transaction commit.
2. Tiến trình dừng trước khi publication được ghi nhận hoàn tất.
3. Registry vẫn thấy publication incomplete.
4. Publication được resubmit.
5. Listener nhận lại cùng event.

Nếu listener không có idempotency, bước 5 có thể ghi doanh thu lần hai. Registry giúp phục hồi delivery, nhưng không thể suy ra side effect nghiệp vụ đã được commit hay chưa nếu listener không có dấu mốc riêng.

Khi kết hợp inbox và transaction đúng cách, lần resubmit sẽ thấy key đã tồn tại và không tạo side effect trùng. Listener kết thúc bình thường, cho phép publication được hoàn tất theo cơ chế registry.

Không coi registry là inbox. Registry quản lý publication theo listener; inbox quản lý việc áp dụng event vào nghiệp vụ. Hai thành phần trả lời hai câu hỏi khác nhau và bổ sung cho nhau.

## 13. Outbox không thay thế inbox

Transactional outbox giúp producer ghi business state và message cần gửi trong cùng transaction. Publisher đọc outbox rồi gửi message tới broker. Nếu publisher không chắc lần gửi trước đã thành công, message có thể được gửi lại.

Outbox bảo vệ chiều phát message; inbox bảo vệ chiều nhận và áp dụng side effect:

~~~mermaid
flowchart LR
    A["Business transaction"] --> B["Outbox record"]
    B --> C["Publisher retry"]
    C --> D["Broker delivery"]
    D --> E["Consumer inbox"]
    E --> F["Business side effect"]
~~~

Một producer có outbox vẫn có thể gửi cùng message nhiều lần. Consumer có inbox vẫn không tự bảo đảm producer đã ghi nhận được message cần gửi. Hệ thống cần chọn cơ chế cho cả hai ranh giới.

Nếu ứng dụng dùng Spring Modulith Event Publication Registry hoặc externalization adapter, hãy xác định chính xác cơ chế nào ghi publication, cơ chế nào gửi broker và cơ chế nào đánh dấu consumer đã xử lý. Không gộp tất cả vào một khái niệm exactly-once.

## 14. Concurrency: hai consumer cùng nhận một event

Deduplication phải an toàn khi hai instance xử lý cùng key đồng thời. Mô hình SELECT rồi INSERT không bảo vệ được trường hợp này vì cả hai có thể cùng thấy key chưa tồn tại.

Unique constraint là điểm đồng bộ cuối cùng ở database. Hai transaction cạnh tranh insert cùng key; chỉ một transaction có thể tạo record. Transaction thắng thực hiện side effect cùng inbox marker; transaction còn lại nhận diện conflict và không thực hiện side effect.

Với database không có INSERT ... ON CONFLICT, có thể dùng insert và xử lý unique violation theo semantics transaction của hệ quản trị. Một số database đánh dấu transaction không thể tiếp tục sau lỗi constraint, nên cần rollback hoặc dùng cơ chế phù hợp thay vì bắt exception rồi tiếp tục truy vấn trong cùng transaction.

Nếu side effect ở nhiều hệ thống, unique constraint cục bộ không bảo vệ toàn bộ chuỗi. Cần idempotency ở từng đích, workflow bền vững hoặc saga với các bước có thể phục hồi.

## 15. Ordering là vấn đề riêng với idempotency

Idempotency ngăn áp dụng cùng công việc nhiều lần; nó không bảo đảm event được áp dụng đúng thứ tự.

Ví dụ consumer nhận OrderShipped rồi mới nhận OrderPaid. Hai event có ID khác nhau nên inbox coi cả hai là mới. Nếu handler áp dụng mù quáng, trạng thái có thể bị lùi hoặc invariant bị phá vỡ.

Event có thể mang aggregateVersion hoặc sequence. Consumer kiểm tra version so với state đã lưu:

- Version kế tiếp hợp lệ: áp dụng.
- Version cũ hoặc đã áp dụng: bỏ qua theo stale-event policy.
- Version có khoảng trống: chờ event thiếu, truy vấn bổ sung hoặc đồng bộ lại.

Không dùng event ID để giải quyết ordering. Cần sequence/version, partitioning hoặc cơ chế tuần tự hóa theo aggregate.

## 16. Replay và dead-letter làm lộ thiếu idempotency

Replay là thao tác đưa event cũ vào luồng xử lý lại. Nó có thể xảy ra khi phục hồi từ DLQ, sửa lỗi consumer, rebuild projection hoặc chạy backfill.

Nếu consumer không idempotent, replay có thể:

- Tạo giao dịch mới cho một payment đã capture.
- Gửi lại email hoặc SMS.
- Cộng điểm loyalty thêm lần nữa.
- Tạo vận đơn trùng.
- Phát lại command gây side effect ở participant khác.

Trước replay, cần xác định loại xử lý có thể chạy lại an toàn. Projection có thể được rebuild trong vùng dữ liệu mới; side effect không thể đảo ngược cần inbox, business unique key hoặc idempotency key phía hệ thống đích.

Giữ event ID ổn định qua redrive. Không tạo ID mới để vượt qua deduplication. Nếu cần chạy lại có chủ đích như một operation nghiệp vụ mới, hãy tạo command mới với operation ID mới và audit lý do.

## 17. Thời gian lưu idempotency record

Nếu xóa inbox record quá sớm, event cũ được replay có thể bị coi là mới. Retention phải bao phủ toàn bộ cửa sổ message có thể xuất hiện lại:

- Message retention của broker và dead-letter queue.
- Thời hạn retry và resubmit của Event Publication Registry.
- Thời gian giữ backup có thể phục hồi.
- Cửa sổ redrive/replay do vận hành cho phép.
- Yêu cầu audit và đối soát nghiệp vụ.

Với thanh toán hoặc sổ cái, có thể cần lưu business unique key lâu dài thay vì chỉ dựa trên inbox có TTL. Với event ít quan trọng, retention có thể ngắn hơn nhưng phải có quyết định rõ và được kiểm tra với replay policy.

Nếu bảng inbox lớn, có thể partition hoặc archive theo thời gian. Trước khi xóa record, cần chứng minh event cũ không còn được replay hoặc vẫn có một ràng buộc nghiệp vụ khác bảo vệ side effect.

## 18. Kiểm thử khi thiếu idempotency

Test chỉ publish một lần thường không phát hiện anti-pattern. Bộ test cần mô phỏng duplicate tuần tự, duplicate đồng thời và failure window.

| Scenario | Cách kích hoạt | Kỳ vọng khi có idempotency |
|---|---|---|
| Redelivery tuần tự | Gửi cùng event hai lần | Một side effect |
| Concurrent delivery | Hai thread cùng xử lý cùng key | Một transaction thực hiện side effect |
| Crash sau commit trước ack | Giao lại event sau commit | Không ghi lần hai |
| Listener resubmit | Publication incomplete được phục hồi | Không lặp nghiệp vụ |
| DLQ redrive | Đưa event đã xử lý trở lại | Không lặp side effect |
| Business duplicate | Hai event ID nhưng cùng payment ID | Unique constraint chặn giao dịch trùng |
| External timeout | Gateway thành công nhưng response mất | Cùng idempotency key trả cùng kết quả |
| Key conflict | Cùng key nhưng payload khác | Ghi nhận conflict, không âm thầm bỏ qua |
| Retention boundary | Replay event cũ | Hành vi theo retention policy |

Với test concurrency, nên dùng database thật hoặc môi trường tương thích để xác minh unique constraint và transaction isolation. Mock repository không chứng minh được hai transaction cạnh tranh an toàn.

Để mô phỏng crash sau commit trước ack, có thể tách transaction xử lý khỏi bước acknowledgement trong test harness hoặc dừng consumer sau khi transaction hoàn tất rồi phát lại cùng message. Không chỉ gọi method handler hai lần và cho rằng đã mô phỏng đầy đủ broker delivery.

## 19. Quan sát và đối soát duplicate

Idempotency cần có tín hiệu vận hành. Nên theo dõi:

- Số lần consumer nhận duplicate key.
- Số side effect bị chặn bởi inbox.
- Số conflict cùng key nhưng payload khác.
- Số unique constraint violation theo consumer.
- Số event replay/redrive.
- Số giao dịch nghiệp vụ trùng được phát hiện qua business key.
- Số external API request được trả kết quả idempotent.
- Tuổi của inbox record và chính sách retention.

Log có cấu trúc nên chứa consumer ID, event ID, logical operation ID, producer, source, correlation ID và kết quả deduplication. Không đưa event ID hoặc order ID vào metric tag có cardinality cao; dùng log/trace để điều tra từng trường hợp.

Đối soát định kỳ có thể so sánh số logical event với số business operation, kiểm tra unique key và phát hiện hai event khác ID cùng business key. Nếu phát hiện duplicate đã tạo side effect, cần quy trình compensation hoặc correction có audit.

## 20. Cách khắc phục anti-pattern

Khi phát hiện consumer không idempotent, có thể xử lý theo trình tự:

1. Liệt kê side effect mà listener tạo ra, bao gồm database và hệ thống ngoài.
2. Xác định logical operation ID ổn định cho mỗi side effect.
3. Chọn scope của idempotency key theo consumer và producer.
4. Thêm inbox table hoặc unique business constraint.
5. Đưa inbox marker và side effect vào cùng transaction nếu cùng database.
6. Với API ngoài, dùng idempotency key phía đích hoặc workflow đối soát.
7. Bảo đảm retry và replay giữ nguyên event ID.
8. Kiểm thử duplicate tuần tự, đồng thời và failure window.
9. Theo dõi duplicate bị chặn và conflict trong production.
10. Xác định retention và quy trình xử lý dữ liệu đã bị nhân đôi.

Không thêm một cờ boolean processed trong bộ nhớ của instance để giải quyết duplicate. Process restart sẽ làm mất cờ và nhiều instance không chia sẻ trạng thái. Dấu mốc cần bền vững và được đồng bộ tại nơi side effect được commit.

## 21. Những cách hiểu sai thường gặp

**Broker bảo đảm exactly-once nên consumer không cần idempotency.** Delivery semantics không tự bảo vệ mọi side effect database hoặc API ngoài. Consumer vẫn cần xử lý duplicate.

**Event Publication Registry chỉ gọi listener một lần.** Registry theo dõi publication và phục hồi incomplete; phục hồi có thể dẫn tới lần gọi lại.

**Kiểm tra SELECT trước INSERT là đủ.** Hai instance có thể cùng vượt qua bước kiểm tra. Hãy dùng unique constraint và insert nguyên tử.

**Event ID khác nhau nghĩa là nghiệp vụ khác nhau.** Hai event có thể cùng biểu diễn một payment hoặc operation. Cần business key riêng.

**Ack trước để tránh message lặp.** Điều đó có thể làm mất message nếu database chưa commit. Hãy commit nghiệp vụ trước ack và dùng idempotency để chịu redelivery.

**Chỉ cần idempotency trong database.** API thanh toán hoặc email provider có thể tạo side effect ngoài database. Cần bảo vệ ở từng ranh giới.

**Xóa inbox khi replay để handler chạy lại.** Việc đó có thể tạo side effect không thể đảo ngược. Replay phải có policy và audit.

**Dùng correlation ID làm idempotency key.** Một workflow có nhiều event khác nhau. Key phải nhận diện một logical operation cụ thể.

## Kết luận

Không có idempotency khiến mỗi lần delivery, retry hoặc replay có thể tạo thêm side effect. Anti-pattern này thường ẩn trong happy path và chỉ bộc lộ khi consumer dừng giữa commit và acknowledgement, khi hai instance xử lý đồng thời hoặc khi message cũ được phát lại.

Với Spring Modulith, Event Publication Registry hỗ trợ theo dõi và phục hồi publication; listener cần tự bảo vệ side effect bằng idempotency. Kết hợp event ID ổn định, inbox pattern, unique business constraint, transaction atomicity, idempotency key cho dịch vụ ngoài, ordering/version check và kiểm thử failure window giúp consumer chịu được duplicate mà vẫn giữ invariant nghiệp vụ.

