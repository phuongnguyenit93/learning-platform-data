# Xử lý retry không gây tác dụng kép

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application event giúp các module giao tiếp qua những sự thật nghiệp vụ đã xảy ra. Khi listener, publication registry hoặc broker gặp lỗi, một event có thể được gửi lại. Retry giúp hệ thống phục hồi, nhưng cũng có thể khiến cùng một tác vụ được thực hiện nhiều lần: trừ tiền hai lần, giữ hàng hai lần, tạo hai hóa đơn hoặc gửi nhiều thông báo giống nhau.

**Idempotency** là thuộc tính giúp một thao tác có thể được thực hiện lặp lại mà kết quả nghiệp vụ vẫn tương đương với việc thực hiện một lần. Đây là nền tảng để retry an toàn trong hệ thống event-driven. Muốn đạt được điều đó, consumer phải nhận diện được cùng một yêu cầu, ghi nhận việc xử lý một cách nguyên tử và bảo vệ cả các tác dụng phụ bên ngoài.

## 1. Idempotency là gì?

Một thao tác idempotent có cùng kết quả quan sát được khi được áp dụng một hoặc nhiều lần với cùng một định danh và cùng dữ liệu đầu vào. Có thể biểu diễn ý tưởng bằng:

~~~text
apply(apply(state, command), command) = apply(state, command)
~~~

Ví dụ:

- Đặt trạng thái đơn hàng thành CONFIRMED nhiều lần vẫn cho kết quả CONFIRMED.
- Ghi nhận event ID đã xử lý nhiều lần vẫn chỉ tạo một bản ghi xử lý.
- Gửi yêu cầu giữ hàng với cùng idempotency key không tạo thêm reservation thứ hai.
- Tạo một hóa đơn theo cùng business operation ID không phát hành hóa đơn mới mỗi lần retry.

Ngược lại, các thao tác sau thường không idempotent nếu không có bảo vệ:

- Trừ 100.000 đồng khỏi số dư mỗi lần nhận message.
- Tăng số lượng hàng đã bán thêm một đơn vị.
- Tạo một bản ghi mới với ID ngẫu nhiên mỗi lần consumer chạy.
- Gửi một email mới mỗi lần listener được gọi.

Idempotency không có nghĩa là listener chỉ chạy một lần. Một listener có thể được gọi nhiều lần, nhưng các lần gọi lặp không tạo thêm tác dụng phụ nghiệp vụ. Mục tiêu là kết quả an toàn dưới retry và redelivery.

## 2. Vì sao event có thể được xử lý nhiều lần?

Trong hệ thống phân tán, producer và consumer không chia sẻ một transaction nguyên tử xuyên suốt. Có những cửa sổ lỗi mà một bên đã hoàn tất nhưng bên kia chưa biết kết quả.

Ví dụ consumer nhận message, cập nhật database thành công rồi process dừng trước khi gửi acknowledgement. Broker không nhận được ack và giao message lại. Consumer thấy cùng message lần nữa dù thay đổi nghiệp vụ trước đó đã commit.

Các tình huống phổ biến:

- Listener ném exception hoặc process dừng sau khi thực hiện một phần công việc.
- Publication registry chưa ghi nhận listener hoàn tất trước khi ứng dụng restart.
- Publisher gửi message đến broker nhưng mất kết nối trước khi nhận publisher confirm.
- Broker đã nhận message nhưng publisher tưởng publish thất bại và gửi lại.
- Consumer đã commit database nhưng ack bị mất.
- Consumer timeout khi gọi API ngoài và không biết dịch vụ đích đã thực hiện yêu cầu hay chưa.
- Operator phát lại message từ dead-letter queue hoặc replay một khoảng event.
- Scheduler hoặc job chạy lại sau khi lần trước hoàn thành nhưng không kịp ghi nhận trạng thái.

Đây là lý do hệ thống thường phải chấp nhận semantics **at-least-once delivery**: message có thể được giao một hoặc nhiều lần để giảm nguy cơ mất công việc. Consumer cần được thiết kế để xử lý lặp an toàn.

## 3. Phân biệt event ID, business key và idempotency key

Không phải mọi định danh đều có cùng mục đích.

| Định danh | Mục đích | Ví dụ |
|---|---|---|
| Event ID | Nhận diện một event cụ thể trong hệ thống phát | UUID của OrderConfirmed |
| Business key | Nhận diện đối tượng nghiệp vụ | orderId, invoiceNumber |
| Idempotency key | Nhận diện một ý định/thao tác cần chỉ thực hiện một lần | authorize-payment:order-123 |
| Correlation ID | Liên kết nhiều message trong cùng một luồng | checkout request ID |
| Causation ID | Chỉ ra message trực tiếp tạo ra event hiện tại | command ID đã gây ra event |

Event ID phù hợp để chống xử lý lặp cùng một message. Idempotency key có thể gom nhiều lần thử của cùng một thao tác nghiệp vụ, kể cả khi mỗi lần thử có message ID khác nhau.

Ví dụ, cùng một yêu cầu thu tiền có thể được phát lại thành hai message với event ID khác nhau do lỗi phía producer. Nếu chỉ deduplicate theo event ID, consumer vẫn có thể thu tiền hai lần. Một payment operation ID ổn định hoặc idempotency key theo đơn hàng và lần thanh toán giúp bảo vệ nghiệp vụ ở cấp cao hơn.

Cần xác định phạm vi duy nhất của key. Key có thể duy nhất toàn hệ thống, theo tenant, theo consumer, theo loại command hoặc theo aggregate. Phạm vi phải đủ chặt để hai thao tác khác nhau không vô tình dùng chung key.

## 4. Idempotency ở consumer bằng Inbox pattern

Inbox pattern lưu lại các message đã nhận hoặc đã xử lý để consumer có thể nhận biết bản sao. Một bảng inbox tối thiểu có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| consumer_name | Consumer sở hữu bản ghi |
| event_id | Định danh event nguồn |
| event_type | Loại event |
| received_at | Thời điểm nhận |
| processed_at | Thời điểm xử lý hoàn tất |
| status | RECEIVED, PROCESSED hoặc FAILED |
| payload_hash (tùy chọn) | Phát hiện cùng key nhưng payload khác |

Ràng buộc unique thường đặt trên cặp consumer_name và event_id. Cách này cho phép nhiều consumer độc lập xử lý cùng một event, nhưng mỗi consumer chỉ áp dụng event đó một lần.

Luồng xử lý:

1. Consumer nhận event.
2. Trong transaction database, thử ghi event ID vào inbox.
3. Nếu key đã tồn tại ở trạng thái đã xử lý, bỏ qua tác dụng phụ và kết thúc thành công.
4. Nếu đây là lần đầu, thực hiện thay đổi nghiệp vụ.
5. Đánh dấu inbox PROCESSED trong cùng transaction.
6. Commit transaction.
7. Chỉ sau khi xử lý thành công, acknowledgement được gửi theo cơ chế transport.

Điểm quan trọng là ghi inbox, cập nhật domain và đánh dấu hoàn tất phải nằm trong cùng transaction cục bộ. Nếu transaction rollback, cả bản ghi inbox và thay đổi nghiệp vụ đều rollback; message có thể được giao lại và consumer thử lại từ đầu.

### Ví dụ cấu trúc bảng

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Đây là schema minh họa cho database hỗ trợ UUID và timestamp có timezone. Kiểu dữ liệu và cú pháp cần điều chỉnh theo database đang sử dụng.

### Ghi nhận nguyên tử với PostgreSQL

Có thể dùng INSERT ... ON CONFLICT DO NOTHING để claim event một cách nguyên tử:

~~~sql
INSERT INTO processed_events (
    consumer_name,
    event_id,
    event_type,
    processed_at
)
VALUES (
    :consumerName,
    :eventId,
    :eventType,
    CURRENT_TIMESTAMP
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;
~~~

Nếu số dòng được thêm là 1, transaction này nhận quyền xử lý event. Nếu số dòng được thêm là 0, event đã được claim trước đó và consumer có thể bỏ qua. Việc claim và thay đổi domain phải cùng transaction. Đây là cú pháp riêng của PostgreSQL; database khác có thể dùng MERGE, insert-ignore hoặc cơ chế tương đương.

Không nên chỉ truy vấn xem event ID đã tồn tại hay chưa rồi mới insert. Hai consumer đồng thời có thể cùng đọc thấy chưa tồn tại và cùng thực hiện tác dụng phụ. Unique constraint và thao tác claim nguyên tử là lớp bảo vệ cuối cùng trước race condition.

## 5. Không dùng check-then-act thiếu bảo vệ

Mẫu dễ mắc lỗi:

~~~java
if (!processedEvents.exists(event.eventId())) {
    account.debit(event.amount());
    processedEvents.save(event.eventId());
}
~~~

Hai thread có thể cùng chạy exists và đều nhận false. Cả hai cùng trừ tiền trước khi một thread gặp lỗi unique constraint khi lưu event ID. Nếu thay đổi số dư đã commit ở transaction khác, tác dụng kép đã xảy ra.

Cần dùng một trong các cơ chế:

- Insert inbox với unique constraint trước khi thay đổi domain, trong cùng transaction.
- Khóa bản ghi hoặc dùng optimistic locking/version để chỉ một tiến trình áp dụng chuyển trạng thái.
- Dùng câu lệnh cập nhật có điều kiện và kiểm tra số dòng bị ảnh hưởng.
- Dùng một cơ chế claim/lease có thời hạn khi xử lý kéo dài ngoài transaction, đồng thời có fencing token để ngăn worker cũ tiếp tục ghi.

Không dựa vào kiểm tra trong bộ nhớ, synchronized hoặc một lock cục bộ của JVM để bảo vệ consumer chạy trên nhiều instance.

## 6. Ví dụ consumer idempotent với Spring

Ví dụ sau minh họa một listener cập nhật projection và ghi nhận event ID trong cùng transaction. Repository claim cần được triển khai bằng thao tác insert nguyên tử và unique constraint như phần trên.

~~~java
@Component
class OrderConfirmedListener {

    private final ProcessedEventStore processedEvents;
    private final OrderProjectionRepository projections;

    OrderConfirmedListener(
        ProcessedEventStore processedEvents,
        OrderProjectionRepository projections
    ) {
        this.processedEvents = processedEvents;
        this.projections = projections;
    }

    @Transactional
    public void on(OrderConfirmed event) {
        boolean firstDelivery = processedEvents.claim(
            "order-projection",
            event.eventId(),
            "OrderConfirmed"
        );

        if (!firstDelivery) {
            return;
        }

        projections.markConfirmed(
            event.orderId(),
            event.version()
        );
    }
}
~~~

Đây là ví dụ khái niệm; phương thức claim phải trả kết quả dựa trên số dòng insert nguyên tử. Không triển khai claim bằng một lần exists rồi save riêng biệt. Transaction manager phải bao phủ cả inbox và projection repository. Nếu hai repository dùng hai datasource hoặc transaction manager độc lập, tính nguyên tử không còn được bảo đảm.

Nếu listener được gọi bởi Spring Modulith, có thể dùng Event Publication Registry để theo dõi publication. Registry quản lý trạng thái giao event đến listener; inbox vẫn có trách nhiệm bảo vệ tác dụng phụ nghiệp vụ khi listener được gọi lại.

## 7. Idempotency với state transition

Một số thao tác có thể thiết kế idempotent ngay ở cấp domain. Ví dụ đặt trạng thái đơn thành CONFIRMED chỉ khi trạng thái hiện tại là PAID:

~~~sql
UPDATE orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE order_id = :orderId
  AND status = 'PAID';
~~~

Lần đầu câu lệnh có thể cập nhật một dòng. Lần gọi lại khi trạng thái đã CONFIRMED sẽ cập nhật 0 dòng. Consumer cần phân biệt:

- Đã chuyển trạng thái thành công.
- Trạng thái đích đã được đạt trước đó, nên retry là no-op hợp lệ.
- Trạng thái hiện tại không hợp lệ để chuyển tiếp, cần điều tra hoặc xử lý theo quy tắc nghiệp vụ.

Không nên coi mọi trường hợp cập nhật 0 dòng là thành công. Có thể orderId không tồn tại hoặc trạng thái hiện tại mâu thuẫn. Cần đọc hoặc kiểm tra kết quả theo business rule.

Với event có version, chỉ áp dụng snapshot mới hơn:

~~~sql
UPDATE order_projection
SET status = :status,
    version = :incomingVersion
WHERE order_id = :orderId
  AND version < :incomingVersion;
~~~

Câu lệnh này giúp event cũ không ghi đè snapshot mới. Với delta event như cộng số lượng, bỏ qua version thấp hơn có thể làm mất một bước; cần kiểm tra sequence liên tục hoặc lưu từng event đã áp dụng.

## 8. Idempotency cho API và command

Idempotency key đặc biệt hữu ích khi client hoặc một service gọi API có thể retry do timeout. Server có thể lưu kết quả theo key để lần gọi lặp trả về kết quả của lần đầu.

Một bản ghi idempotency có thể gồm:

- Key do client hoặc caller tạo.
- Scope gồm tenant, user, endpoint hoặc operation type.
- Request fingerprint/hash.
- Trạng thái IN_PROGRESS, COMPLETED hoặc FAILED.
- HTTP status và response cần trả lại.
- Thời điểm tạo và hết hạn.
- Business operation ID liên quan.

Quy trình:

1. Client gửi request cùng idempotency key.
2. Server atomically claim key trong phạm vi đã định nghĩa.
3. Nếu key chưa tồn tại, server ghi request fingerprint và bắt đầu xử lý.
4. Nếu key đã COMPLETED và fingerprint giống nhau, trả lại kết quả đã lưu.
5. Nếu key đang IN_PROGRESS, trả trạng thái đang xử lý hoặc cho caller retry sau.
6. Nếu cùng key nhưng payload khác, từ chối vì caller đang tái sử dụng key sai mục đích.
7. Khi xử lý hoàn tất, lưu kết quả và đánh dấu COMPLETED.

Ví dụ: cùng key payment-order-123 được gửi lại với cùng số tiền và loại tiền thì server trả về cùng payment operation. Nếu caller dùng lại key đó với số tiền khác, server cần báo conflict thay vì coi đó là cùng thao tác.

Không tạo idempotency key mới cho mỗi lần retry. Key phải được tạo một lần cho ý định nghiệp vụ và được giữ ổn định qua các lần thử.

## 9. Tác dụng phụ bên ngoài và giới hạn của transaction database

Inbox pattern bảo vệ tốt các thay đổi trong cùng database transaction. Nhưng nếu listener vừa cập nhật database vừa gọi dịch vụ ngoài, email provider hoặc payment gateway, không thể đưa lời gọi HTTP đó vào cùng transaction ACID của database.

Ví dụ:

1. Consumer ghi inbox.
2. Consumer gọi cổng thanh toán để capture tiền.
3. Cổng thanh toán thành công.
4. Process chết trước khi database commit.
5. Message được giao lại và consumer gọi capture lần nữa.

Nếu cổng thanh toán không hỗ trợ idempotency, khách hàng có thể bị thu tiền hai lần.

Các cách xử lý:

**Dùng idempotency key của dịch vụ đích.** Gửi cùng một operation key trong mọi lần retry. Dịch vụ đích trả lại kết quả của lần thực hiện đầu tiên.

**Tách tác dụng phụ thành outbox command.** Trong transaction local, ghi inbox, cập nhật trạng thái và ghi command vào outbox. Một worker gửi command đến dịch vụ ngoài sau commit. Worker có thể retry; command cần idempotency key ổn định.

**Dùng trạng thái tiến trình.** Lưu trạng thái REQUESTED, IN_PROGRESS, SUCCEEDED hoặc FAILED. Sau timeout, tra cứu trạng thái operation ở dịch vụ đích trước khi quyết định gửi lại.

**Đối soát.** Nếu dịch vụ đích không có API idempotency hoặc tra cứu, cần quy trình đối soát để xác định tác dụng phụ đã xảy ra chưa trước khi retry.

Không đánh dấu message hoàn tất chỉ vì request HTTP đã được gửi. Cần định nghĩa rõ thời điểm nghiệp vụ được xem là thành công và cách xử lý kết quả không xác định.

## 10. Outbox và Inbox phối hợp với nhau

Outbox bảo vệ phía phát: ý định gửi message được lưu cùng transaction với thay đổi nghiệp vụ. Inbox bảo vệ phía nhận: event đã được xử lý được ghi nhận cùng transaction với tác dụng phụ nội bộ.

Luồng điển hình:

1. Producer cập nhật domain và ghi outbox trong một transaction.
2. Relay đọc outbox và publish message.
3. Broker có thể giao message một hoặc nhiều lần.
4. Consumer claim event ID trong inbox.
5. Consumer cập nhật domain và đánh dấu processed trong transaction.
6. Consumer ack sau khi transaction commit.

Outbox không ngăn broker giao lặp. Inbox không bảo đảm một message được publish ra khỏi producer. Hai mẫu giải quyết hai phía của cùng một luồng và thường được kết hợp.

~~~mermaid
flowchart TD
    A[Producer transaction] --> B[Update domain]
    B --> C[Write outbox]
    C --> D[Commit]
    D --> E[Relay publish]
    E --> F[Broker]
    F --> G[Consumer receives event]
    G --> H[Claim event ID in inbox]
    H --> I{Already processed?}
    I -- Yes --> J[Ack duplicate]
    I -- No --> K[Apply domain change]
    K --> L[Mark inbox processed]
    L --> M[Commit]
    M --> N[Ack message]
~~~

Nếu process dừng trước commit của consumer, inbox và thay đổi domain cùng rollback. Nếu process dừng sau commit nhưng trước ack, broker giao lại; consumer nhận diện bản sao và ack mà không lặp tác dụng phụ.

## 11. Event Publication Registry trong Spring Modulith

Spring Modulith Event Publication Registry theo dõi publication của application event đến các listener. Với persistence phù hợp, registry giúp ứng dụng nhận biết publication chưa hoàn tất và phục hồi việc giao event sau khi listener lỗi hoặc process restart.

Registry không tự đảm bảo mọi tác dụng phụ chỉ xảy ra một lần. Một listener có thể được gọi lại khi publication được resubmit hoặc khi kết quả hoàn tất chưa được ghi nhận. Vì vậy:

- Listener cần idempotent nếu có tác dụng phụ.
- Dùng event ID ổn định qua các lần retry.
- Ghi inbox cùng transaction với thay đổi domain.
- Không gọi API ngoài theo cách không có idempotency hoặc cơ chế đối soát.
- Theo dõi publication chưa hoàn tất và lỗi lặp.
- Phân biệt publication đã giao cho listener với nghiệp vụ downstream đã hoàn tất.

Nếu listener chạy sau commit, transaction nghiệp vụ ban đầu đã hoàn tất. Thay đổi trong listener cần transaction riêng phù hợp. Khi inbox và domain update cùng dùng transaction manager, consumer có thể commit chúng như một đơn vị. Nếu listener lỗi, transaction của listener rollback và publication có thể được thử lại theo chính sách.

## 12. Retry an toàn và phân loại lỗi

Idempotency làm retry an toàn hơn, nhưng không có nghĩa mọi lỗi đều nên retry vô hạn.

| Loại lỗi | Hướng xử lý |
|---|---|
| Timeout hoặc mất kết nối tạm thời | Retry với exponential backoff và jitter |
| Rate limit hoặc downstream quá tải | Giảm tốc, tôn trọng Retry-After nếu có và thử lại có giới hạn |
| Payload không hợp lệ | Cách ly hoặc dead-letter, không retry liên tục |
| Schema version không hỗ trợ | Đưa vào luồng xử lý tương thích hoặc điều tra |
| Lỗi nghiệp vụ vĩnh viễn | Ghi nhận kết quả thất bại và áp dụng quy tắc domain |
| Lỗi cấu hình hoặc quyền truy cập | Cảnh báo và khắc phục cấu hình trước khi retry hàng loạt |

Một chiến lược retry nên có số lần tối đa, khoảng chờ, jitter và dead-letter. Khi phát lại từ DLQ, giữ event ID hoặc operation key ban đầu. Nếu tạo key mới trong lúc replay, lớp dedup có thể không nhận ra đây là cùng một ý định nghiệp vụ.

Poison message không thể xử lý sẽ làm queue bị kẹt nếu liên tục requeue. Hãy cách ly message, lưu lý do và cung cấp quy trình replay có kiểm soát sau khi sửa nguyên nhân.

## 13. Retention của idempotency record

Bản ghi inbox hoặc idempotency key phải tồn tại lâu hơn khoảng thời gian hệ thống có thể nhận lại cùng một thao tác.

Hãy xác định retention dựa trên:

- Thời gian retry tối đa ở producer và broker.
- Message TTL và thời gian lưu ở dead-letter queue.
- Khoảng thời gian operator được phép replay.
- Thời hạn retry của client/API gateway.
- Yêu cầu audit và quy định nghiệp vụ.
- Khả năng phát lại từ event archive hoặc backup.

Nếu xóa inbox record quá sớm, một message cũ được replay có thể thực hiện tác dụng phụ lần nữa. Nếu lưu vô thời hạn, bảng dedup sẽ tăng liên tục. Có thể partition theo thời gian, archive hoặc cleanup theo batch, nhưng phải bảo đảm mọi bản sao có thể đến muộn đều nằm trong khoảng retention đã tính.

Với payment, refund, hóa đơn hoặc tác vụ tài chính, thời gian bảo vệ có thể cần dài hơn TTL message thông thường. Không dùng một retention chung cho mọi consumer nếu mức rủi ro khác nhau.

## 14. Payload khác nhau nhưng dùng cùng idempotency key

Nếu cùng một key xuất hiện với payload khác, không được âm thầm coi là duplicate hợp lệ. Đây có thể là lỗi caller tái sử dụng key, bug tạo event hoặc dấu hiệu dữ liệu bị sửa.

Có thể lưu request hash hoặc payload fingerprint:

- Cùng key, cùng fingerprint, trạng thái COMPLETED: trả kết quả đã lưu.
- Cùng key, cùng fingerprint, trạng thái IN_PROGRESS: trả trạng thái đang xử lý hoặc hướng dẫn retry.
- Cùng key, fingerprint khác: từ chối và ghi log/audit.
- Cùng event ID nhưng event type hoặc aggregate ID khác: cách ly vì vi phạm hợp đồng định danh.

Không lưu raw payload nhạy cảm chỉ để so sánh. Hash trên representation đã chuẩn hóa hoặc các trường nghiệp vụ quan trọng có thể đủ, tùy yêu cầu. Chuẩn hóa cần nhất quán về thứ tự field, định dạng thời gian, tiền tệ và cách biểu diễn null.

## 15. Idempotency và thứ tự event

Idempotency chỉ ngăn tác dụng kép của cùng một thao tác. Nó không bảo đảm các event khác nhau được xử lý đúng thứ tự.

Ví dụ OrderShipped có thể đến trước OrderConfirmed. Cả hai event đều có ID khác nhau nên inbox cho phép xử lý cả hai. Consumer vẫn cần sequence/version theo aggregate hoặc state transition có điều kiện để không đưa trạng thái đơn hàng lùi lại.

Các nguyên tắc:

- Dùng event ID để deduplicate cùng một message.
- Dùng aggregate version hoặc sequence để kiểm tra thứ tự.
- Dùng state machine để chỉ chấp nhận chuyển trạng thái hợp lệ.
- Xử lý event đến sớm bằng inbox chờ, retry hoặc reconciliation.
- Không dùng timestamp đơn lẻ làm cơ chế ordering.
- Giữ idempotency key qua retry, redelivery và DLQ replay.

## 16. Kiểm thử idempotency

Kiểm thử cần chứng minh cùng một event được gửi nhiều lần nhưng tác dụng phụ chỉ xảy ra một lần.

Các trường hợp nên kiểm tra:

1. Gửi cùng event hai lần tuần tự.
2. Gửi cùng event đồng thời từ nhiều consumer instance.
3. Process dừng sau khi domain update nhưng trước ack.
4. Transaction rollback sau khi claim inbox.
5. Broker redelivery sau connection loss.
6. Hai event ID khác nhau nhưng cùng business operation key.
7. Cùng idempotency key nhưng request payload khác.
8. Retry sau khi idempotency record đã hết hạn.
9. Replay message từ DLQ.
10. Gọi API ngoài timeout khi kết quả ở dịch vụ đích chưa rõ.
11. Event đến sai thứ tự hoặc version cũ.
12. Consumer restart khi operation ở trạng thái IN_PROGRESS.

Kiểm tra cả kết quả nghiệp vụ, số bản ghi inbox, số lần gọi dịch vụ ngoài và trạng thái cuối. Chỉ xác minh listener không ném exception là chưa đủ.

Ví dụ test ý tưởng:

~~~java
@Test
void duplicateEventMustNotApplyProjectionTwice() {
    var event = orderConfirmedEvent();

    listener.on(event);
    listener.on(event);

    assertThat(projectionRepository.countFor(event.orderId()))
        .isEqualTo(1);
}
~~~

Test thực tế cần chạy với database hoặc transaction test phù hợp để xác minh unique constraint và rollback. Một mock repository không thể chứng minh concurrency protection của database.

## 17. Quan sát và vận hành

Theo dõi idempotency giúp phát hiện cả retry bình thường lẫn lỗi producer/consumer.

| Metric | Ý nghĩa |
|---|---|
| Duplicate event count | Số lần consumer nhận event đã xử lý |
| Idempotency hit rate | Tỷ lệ request được trả kết quả cũ |
| Inbox insert conflict | Số lần claim thất bại do key đã tồn tại |
| In-progress age | Thời gian operation ở trạng thái đang xử lý |
| Retry count/rate | Tần suất retry theo event type |
| Dead-letter count | Message bị cách ly |
| External API duplicate response | Dịch vụ đích trả lại kết quả của operation cũ |
| Inbox table size | Tốc độ tăng dữ liệu dedup |
| Reconciliation mismatch | Số operation cần đối soát |

Log nên có eventId, idempotencyKey đã che một phần nếu cần, consumerName, aggregateId, correlationId và kết quả claim. Không ghi token, dữ liệu thanh toán hoặc payload nhạy cảm vào log.

Khi duplicate rate tăng bất thường, kiểm tra publisher confirm, ack, timeout, retry policy và kết nối. Duplicate không nhất thiết là lỗi nếu hệ thống được thiết kế at-least-once; điều quan trọng là consumer xử lý chúng an toàn và tỷ lệ không vượt kỳ vọng.

## 18. Sơ đồ quyết định khi nhận event

~~~mermaid
flowchart TD
    A[Consumer nhận event] --> B[Validate event và key]
    B --> C[Claim event ID trong inbox]
    C --> D{Claim thành công?}
    D -- Không --> E{Payload/key nhất quán?}
    E -- Có --> F[Đã xử lý: bỏ qua tác dụng phụ và ack]
    E -- Không --> G[Cách ly và cảnh báo]
    D -- Có --> H[Kiểm tra state/version]
    H --> I{Chuyển trạng thái hợp lệ?}
    I -- Không --> J[Chờ, đối soát hoặc cách ly]
    I -- Có --> K[Thực hiện domain update]
    K --> L[Ghi trạng thái processed]
    L --> M[Commit transaction]
    M --> N[Ack message]
~~~

Claim inbox, cập nhật domain và đánh dấu processed phải cùng transaction. Nếu bất kỳ bước nào thất bại trước commit, transaction rollback để message có thể được retry. Nếu commit thành công nhưng ack thất bại, lần giao lại sẽ đi vào nhánh duplicate.

## 19. Checklist triển khai

- [ ] Mỗi event có event ID ổn định.
- [ ] Tác vụ có thể retry có idempotency key hoặc business operation key phù hợp.
- [ ] Phạm vi duy nhất của key được định nghĩa rõ.
- [ ] Inbox có unique constraint ở database.
- [ ] Claim key và domain update nằm trong cùng transaction.
- [ ] Không dùng check-then-act thiếu bảo vệ concurrency.
- [ ] Duplicate cùng key nhưng payload khác được phát hiện.
- [ ] External side effect dùng idempotency key của dịch vụ đích hoặc có reconciliation.
- [ ] Outbox được dùng khi cần ghi ý định gửi message cùng transaction.
- [ ] Consumer ack sau khi công việc được bảo vệ hoàn tất.
- [ ] Retry có backoff, jitter, giới hạn và dead-letter.
- [ ] Retention inbox đủ dài cho retry và replay window.
- [ ] Event ordering được bảo vệ riêng bằng version/sequence khi cần.
- [ ] Có kiểm thử duplicate tuần tự, đồng thời, rollback và crash window.
- [ ] Có metric duplicate, retry, in-progress và reconciliation.

## 20. Nguyên tắc retry không gây tác dụng kép

Trong hệ thống Spring Modulith, publication registry giúp theo dõi việc giao application event đến listener và có thể hỗ trợ phục hồi publication chưa hoàn tất. Vì listener có thể được gọi lại, idempotency phải được bảo vệ ở tầng nghiệp vụ bằng event ID, inbox, unique constraint, transaction và state transition phù hợp.

Với message đi ra broker, kết hợp outbox ở phía phát và inbox ở phía nhận. Với tác dụng phụ bên ngoài, dùng idempotency key ổn định do dịch vụ đích hỗ trợ hoặc bổ sung trạng thái tiến trình và đối soát. Giữ bản ghi dedup đủ lâu cho toàn bộ retry/replay window, đồng thời kiểm thử các cửa sổ lỗi và xử lý đồng thời.

Retry an toàn không đòi hỏi message chỉ được giao một lần. Nó đòi hỏi mọi lần giao lặp đều hội tụ về cùng kết quả nghiệp vụ, không tạo thêm tác dụng phụ và vẫn có thể phục hồi khi một bước thất bại.
