# Batch processing

Khi số lượng application events tăng, xử lý từng event một có thể tạo nhiều lần gọi database, nhiều lần mở transaction và nhiều lần gửi message nhỏ. **Batch processing** gom một nhóm event hoặc bản ghi để xử lý trong một lượt, giúp giảm overhead và tăng throughput. Tuy nhiên, batch cũng làm tăng lượng dữ liệu nằm trong bộ nhớ, kéo dài transaction và mở rộng phạm vi ảnh hưởng khi một phần tử lỗi.

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, cần phân biệt batching ở tầng ứng dụng, tầng lưu trữ projection và tầng message broker. Mỗi tầng có ranh giới xác nhận khác nhau. Một batch chỉ được coi là hoàn tất khi mọi phần tử đã được xử lý hoặc đã được chuyển sang trạng thái lỗi bền vững theo policy.

## 1. Batch processing giải quyết vấn đề gì?

Giả sử một listener nhận 1.000 event và mỗi event thực hiện một câu lệnh update riêng. Cách xử lý tuần tự có thể tạo 1.000 lần round-trip tới database. Nếu gom 100 event vào một batch, ứng dụng có thể giảm số lần round-trip đáng kể.

Lợi ích thường thấy:

- Giảm số lần gọi database hoặc broker.
- Tận dụng prepared statement và network round-trip hiệu quả hơn.
- Tăng throughput khi workload có nhiều thao tác nhỏ tương tự nhau.
- Giảm overhead tạo transaction nếu nhóm thao tác có thể dùng chung transaction.
- Dễ điều tiết lưu lượng bằng batch size và số worker đồng thời.

Batch không tự làm thuật toán nhanh hơn trong mọi trường hợp. Nếu thao tác bị giới hạn bởi một truy vấn chậm, một dịch vụ ngoài hoặc một hot partition, gom thêm event có thể chỉ làm tăng độ trễ. Cần đo bottleneck trước khi tăng batch size.

## 2. Phân biệt event, batch và batch event

Có ba khái niệm khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event đơn | Một sự kiện nghiệp vụ độc lập | Một đơn hàng được thanh toán |
| Batch xử lý | Một nhóm event độc lập được xử lý cùng lượt | Worker đọc 100 event pending rồi cập nhật projection |
| Batch event | Một event envelope chứa nhiều item nghiệp vụ | Một event StockSnapshotImported chứa danh sách nhiều dòng tồn kho |

Thông thường, nên giữ mỗi application event đại diện cho một sự kiện nghiệp vụ. Batch xử lý là chi tiết thực thi, không nhất thiết phải thay đổi contract event. Điều này giúp consumer có thể retry, audit và deduplicate từng event.

Batch event chỉ phù hợp khi nghiệp vụ thực sự xem cả nhóm là một đơn vị, ví dụ hoàn tất một lần import snapshot. Khi đó contract phải quy định rõ tính nguyên tử: toàn bộ batch thành công hay từng item có kết quả riêng. Không gộp nhiều event độc lập thành một payload lớn chỉ để giảm số message nếu điều đó làm mất khả năng xử lý lỗi theo từng event.

## 3. Batching nằm ở những tầng nào?

Một luồng event có thể batching tại nhiều điểm:

~~~text
Application events
       |
       v
Durable inbox / staging
       |
       v
Batch worker
       |
       v
Projection database batch write
       |
       v
Outbox (nếu cần side effect ngoài DB)
       |
       v
Kafka producer batching
       |
       v
Kafka topic
       |
       v
Kafka batch consumer
~~~

Các tầng này có mục tiêu riêng:

- **Application batching:** gom event đã được lưu bền vững để worker xử lý theo nhóm.
- **Database batching:** thực hiện nhiều insert/update bằng một batch API hoặc một transaction.
- **Producer batching:** client Kafka gom nhiều record trước khi gửi request tới broker.
- **Consumer batching:** consumer lấy nhiều record trong một lần poll và xử lý theo nhóm.

Không cần bật batching ở tất cả các tầng. Hãy chọn điểm gây overhead thực tế. Ví dụ, database batch write có thể đủ nếu listener đang tốn nhiều round-trip; producer batching có thể hữu ích khi gửi nhiều record nhỏ; consumer batching có thể tăng throughput khi xử lý record độc lập.

## 4. Spring Modulith listener không tự động là batch listener

Một listener Spring Modulith thường nhận một application event theo phương thức handler:

~~~java
@Component
class OrderProjectionListener {

    private final OrderProjectionService service;

    OrderProjectionListener(OrderProjectionService service) {
        this.service = service;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        service.apply(event);
    }
}
~~~

Annotation **@ApplicationModuleListener** giúp tổ chức listener theo cơ chế Spring Modulith, bao gồm semantics xử lý sau commit và bất đồng bộ theo cấu hình phù hợp. Không nên giả định rằng framework tự gom nhiều publication thành một lời gọi method nhận List.

Nếu muốn gom nhiều event, cần tạo một tầng tích lũy hoặc durable inbox riêng. Listener có thể ghi event vào inbox trong transaction ngắn; worker đọc nhiều dòng pending rồi xử lý theo batch. Listener chỉ nên kết thúc thành công sau khi event đã được xử lý hoặc đã được bàn giao bền vững cho inbox. Không ghi vào một queue trong bộ nhớ rồi trả về thành công, vì process restart có thể làm mất các event đã được registry đánh dấu hoàn tất.

## 5. Thiết kế durable inbox cho batch worker

Một inbox lưu event cần xử lý và trạng thái của từng event. Khóa duy nhất theo consumer và event ID ngăn cùng event được ghi nhận nhiều lần:

~~~sql
CREATE TABLE event_inbox (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    aggregate_id UUID,
    aggregate_version BIGINT,
    event_type VARCHAR(200) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Listener nhận event và lưu vào inbox:

~~~java
@Component
class OrderInboxListener {

    private final EventInboxRepository inbox;

    OrderInboxListener(EventInboxRepository inbox) {
        this.inbox = inbox;
    }

    @ApplicationModuleListener
    void on(OrderPaid event) {
        inbox.insertIfAbsent(
            "order-summary",
            event.eventId(),
            event.orderId(),
            event.aggregateVersion(),
            "OrderPaid",
            event
        );
    }
}
~~~

Ví dụ minh họa; repository cần thực hiện insert có unique constraint và xử lý duplicate một cách nguyên tử. Việc ghi inbox nên cùng transaction với listener để khi insert thất bại, publication không bị coi là đã bàn giao thành công.

Sau khi inbox commit, batch worker có thể xử lý độc lập. Khi đó Event Publication Registry theo dõi việc event đã được bàn giao tới listener; inbox theo dõi công việc projection còn pending. Hai trạng thái có ý nghĩa khác nhau.

## 6. Claim batch an toàn khi chạy nhiều worker

Nếu có nhiều instance cùng chạy batch worker, chúng không được claim cùng một event. Một cách triển khai với PostgreSQL là dùng row-level lock và SKIP LOCKED:

~~~sql
SELECT consumer_name, event_id, payload
FROM event_inbox
WHERE status = 'PENDING'
  AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
ORDER BY received_at, event_id
FOR UPDATE SKIP LOCKED
LIMIT :batch_size;
~~~

Trong transaction ngắn, worker chọn một nhóm dòng và chuyển chúng sang trạng thái đang xử lý hoặc gắn lease. Các worker khác sẽ bỏ qua dòng đang bị khóa và lấy nhóm khác.

Nếu transaction không thể giữ lock trong suốt quá trình xử lý, dùng lease:

- Claim các dòng và ghi worker ID cùng lease expiration.
- Commit claim để giải phóng transaction.
- Xử lý batch ngoài transaction claim.
- Hoàn tất hoặc lên lịch retry trong transaction riêng.
- Worker khác chỉ được lấy lại dòng khi lease hết hạn.

Lease phải có timeout và cơ chế gia hạn nếu xử lý batch lâu. Nếu worker dừng đột ngột, lease hết hạn để event có thể được tiếp quản. Không giữ transaction database mở trong lúc gọi HTTP hoặc chờ broker.

Cú pháp SKIP LOCKED phụ thuộc database. Với hệ quản trị khác, dùng cơ chế claim tương đương như optimistic update có điều kiện hoặc queue partitioning.

## 7. Chọn batch size và thời gian chờ

Batch size là số event tối đa xử lý trong một lượt. Batch lớn giảm overhead trên mỗi event nhưng tăng memory, thời gian xử lý và phạm vi rollback.

Cần cân nhắc nhiều giới hạn:

| Yếu tố | Tác động khi batch quá lớn |
|---|---|
| Memory | Payload và object được giữ đồng thời nhiều hơn |
| Transaction duration | Lock và connection bị giữ lâu hơn |
| Failure scope | Một lỗi có thể làm nhiều event phải retry |
| Latency | Event đầu batch phải chờ đủ nhóm hoặc timeout |
| Database load | Burst ghi lớn có thể làm nghẽn connection pool và I/O |
| Fairness | Một nhóm lớn có thể chiếm worker lâu, làm event khác chờ |

Có thể bắt đầu bằng batch size nhỏ, đo throughput và p95/p99 processing latency rồi điều chỉnh. Các giá trị như 50, 100 hoặc 500 chỉ là điểm thử nghiệm, không phải mặc định đúng cho mọi hệ thống.

Nên có cả ngưỡng số lượng và thời gian gom batch. Ví dụ, worker xử lý khi đủ 100 event hoặc khi event cũ nhất đã chờ 500 ms. Điều này cân bằng throughput và latency khi lưu lượng thấp.

Không chờ vô hạn để đủ batch. Với traffic thấp, timer flush bảo đảm event vẫn được xử lý trong giới hạn thời gian nghiệp vụ.

## 8. Batch write với JdbcTemplate

Với nhiều thao tác tương tự, JdbcTemplate hỗ trợ batchUpdate để giảm số lần round-trip:

~~~java
@Repository
class OrderProjectionBatchWriter {

    private final JdbcTemplate jdbc;

    OrderProjectionBatchWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    void upsertAll(List<OrderSummaryRow> rows) {
        jdbc.batchUpdate(
            """
            INSERT INTO order_projection (
                order_id, status, total_amount, version, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (order_id) DO UPDATE
            SET status = EXCLUDED.status,
                total_amount = EXCLUDED.total_amount,
                version = EXCLUDED.version,
                updated_at = EXCLUDED.updated_at
            WHERE order_projection.version < EXCLUDED.version
            """,
            rows,
            rows.size(),
            (statement, row) -> {
                statement.setObject(1, row.orderId());
                statement.setString(2, row.status());
                statement.setBigDecimal(3, row.totalAmount());
                statement.setLong(4, row.version());
                statement.setTimestamp(5, Timestamp.from(row.updatedAt()));
            }
        );
    }
}
~~~

Ví dụ dùng cú pháp upsert PostgreSQL và batch API của Spring JDBC. Cần điều chỉnh SQL, kiểu dữ liệu và batch API theo database cùng phiên bản Spring đang dùng.

Batch write không tự bảo đảm event không bị áp dụng lặp. Nếu một event được gửi lại, câu lệnh upsert phải có version guard hoặc inbox deduplication. Với phép cộng dồn, phải ghi nhận event ID đã xử lý trong cùng transaction trước khi áp dụng hiệu ứng.

## 9. Batch với JPA và persistence context

Khi dùng JPA, gọi save cho nhiều entity không đồng nghĩa tất cả được gửi xuống database bằng một batch statement. Hibernate cần được cấu hình JDBC batching và entity phải được flush theo nhóm.

Một số điểm cần chú ý:

- Cấu hình batch size phù hợp trong Hibernate.
- Dùng flush định kỳ để gửi SQL xuống database.
- Dùng clear định kỳ để giải phóng persistence context.
- Tránh giữ hàng chục nghìn managed entity trong một transaction.
- Kiểm tra loại ID generation vì một số chiến lược có thể hạn chế JDBC insert batching.
- Đo SQL thực tế để xác nhận batch được sử dụng.

Ví dụ vòng lặp theo chunk:

~~~java
@Transactional
public void persistChunk(List<OrderSummary> summaries) {
    int count = 0;

    for (OrderSummary summary : summaries) {
        entityManager.merge(summary);
        count++;

        if (count % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Con số 100 là minh họa. Nếu phương thức được gọi với một danh sách rất lớn, transaction vẫn bao trùm toàn bộ phương thức dù persistence context được clear. Muốn giới hạn transaction duration, chia danh sách thành chunk và gọi mỗi chunk qua một transaction riêng.

Cũng cần lưu ý rằng merge có thể phát sinh SELECT tùy mapping và trạng thái entity. Với bulk projection write, JdbcTemplate hoặc native upsert đôi khi phù hợp hơn JPA entity lifecycle.

## 10. Chọn ranh giới transaction theo chunk

Có hai cách phổ biến:

| Cách | Ưu điểm | Đánh đổi |
|---|---|---|
| Một transaction cho cả batch | Tất cả thành công hoặc rollback cùng nhau | Transaction dài, lock lâu, một lỗi làm rollback toàn bộ |
| Một transaction cho mỗi chunk | Giới hạn phạm vi rollback và thời gian giữ tài nguyên | Một batch tổng thể có thể hoàn thành một phần |

Với batch 1.000 event, có thể chia thành 10 chunk, mỗi chunk 100 event và một transaction riêng. Nếu chunk thứ 7 thất bại, các chunk đã commit vẫn được giữ; worker chỉ cần tiếp tục các event còn pending hoặc retry.

Không đánh dấu cả batch hoàn tất trước khi các chunk đã được ghi nhận. Trạng thái từng event hoặc từng chunk cần đủ chi tiết để phục hồi sau crash. Nếu có side effect ngoài database, ghi outbox trong cùng transaction với projection rồi gửi bằng worker riêng.

## 11. Xử lý lỗi trong batch

Một batch có thể chứa nhiều event độc lập. Khi một event lỗi, cần chọn một trong hai semantics:

- **All-or-nothing:** cả batch rollback nếu một item lỗi. Phù hợp khi các item tạo thành một đơn vị nghiệp vụ nguyên tử.
- **Per-item result:** từng event có kết quả riêng; item thành công được hoàn tất, item lỗi được retry hoặc quarantine. Phù hợp với các event độc lập.

Không để một poison event chặn mãi các event khác nếu nghiệp vụ cho phép xử lý độc lập. Có thể tách batch khi gặp lỗi để xác định item gây lỗi, nhưng cần giới hạn số lần chia nhỏ để tránh chi phí retry tăng theo cấp số nhân.

Một chiến lược thực tế:

1. Thử ghi batch trong transaction.
2. Nếu thành công, đánh dấu tất cả item đã xử lý.
3. Nếu thất bại do lỗi tạm thời của database, retry cả chunk sau backoff.
4. Nếu lỗi do dữ liệu của một item, chia nhỏ chunk hoặc xử lý từng item để xác định record lỗi.
5. Chuyển item lỗi vĩnh viễn sang quarantine, giữ nguyên event ID và lý do.
6. Chỉ xác nhận item thành công sau khi dữ liệu và trạng thái inbox đã commit.

Không bắt exception trong batch rồi đánh dấu toàn bộ item thành công. Kết quả từng phần phải được biểu diễn rõ ràng trong persistence.

## 12. Idempotency và xử lý batch lặp

Batch worker có thể dừng sau khi database commit nhưng trước khi cập nhật trạng thái inbox hoặc xác nhận message ở broker. Khi khởi động lại, một số item có thể được xử lý lại.

Cần thiết kế idempotency ở cấp từng event:

- Inbox có unique constraint theo consumer và event ID.
- Projection lưu aggregate version hoặc sequence đã áp dụng.
- Upsert chỉ cập nhật khi event mới hơn.
- Phép cộng dồn dùng ledger hoặc deduplication trước khi cộng.
- Replay giữ nguyên event ID.
- Trạng thái inbox và projection update nằm trong cùng transaction khi cùng database.

Không chỉ lưu một batch ID rồi coi cả batch là đã xử lý. Nếu batch được chia lại hoặc thứ tự item thay đổi, batch ID không đủ để nhận diện từng event đã hoàn tất.

Nếu batch chứa event của nhiều aggregate, mỗi aggregate cần version guard riêng. Không dùng một version chung cho toàn batch.

## 13. Ordering khi xử lý song song

Batching và concurrency có thể làm thay đổi thứ tự xử lý. Nếu các event độc lập, có thể phân phối chúng cho nhiều worker. Nếu event của cùng aggregate cần tuần tự, phải giữ chúng cùng partition hoặc cùng khóa xử lý.

Một số cách:

- Group event theo aggregate ID trước khi xử lý.
- Giữ thứ tự version trong từng nhóm.
- Chạy song song giữa các aggregate nhưng tuần tự bên trong một aggregate.
- Dùng Kafka key theo aggregate để các record liên quan đi cùng partition.
- Phát hiện version gap và chờ hoặc retry thay vì áp dụng delta sai thứ tự.

Không giả định ORDER BY received_at đủ để bảo đảm thứ tự nghiệp vụ. Timestamp có thể trùng hoặc lệch. Dùng aggregate version/sequence nếu nguồn cung cấp.

## 14. Batching ở Kafka producer và consumer

Kafka producer có thể tự gom record thành batch theo partition trước khi gửi. Một số cấu hình quan trọng:

~~~yaml
spring:
  kafka:
    producer:
      properties:
        batch.size: 32768
        linger.ms: 5
        compression.type: zstd
~~~

Các giá trị trên chỉ là ví dụ. batch.size là ngưỡng kích thước batch theo byte; linger.ms cho producer thêm thời gian gom record trước khi gửi; compression.type chọn thuật toán nén. Tăng linger có thể tăng throughput nhưng cũng tăng latency. Batch của producer được gom theo partition, không phải một transaction nghiệp vụ của nhiều event.

Ở consumer, Spring Kafka có thể cấu hình batch listener để nhận nhiều record trong một lần poll:

~~~java
@KafkaListener(
    topics = "inventory.stock-reserved.v1",
    groupId = "projection-service"
)
void consume(List<StockReserved> events) {
    projectionService.applyBatch(events);
}
~~~

Ví dụ cần được dùng với container factory đã bật batch listener và deserializer phù hợp. Cấu hình factory, acknowledgment mode và API có thể khác theo phiên bản Spring Kafka.

Nếu consumer batch listener xử lý xong một phần rồi thất bại, cần hiểu chính xác offset nào được commit và record nào sẽ được giao lại. Có thể chọn xử lý toàn batch hoặc per-record acknowledgment/error handling tùy yêu cầu. Không commit offset cho record chưa được xử lý hoặc chưa được lưu bền vững vào inbox/DLT.

## 15. Backpressure và giới hạn tài nguyên

Nếu producer phát event nhanh hơn tốc độ consumer xử lý, backlog sẽ tăng. Tăng batch size không giải quyết được chênh lệch throughput kéo dài.

Cần kiểm soát:

- Số batch worker đồng thời.
- Batch size tối đa và thời gian gom batch.
- Số request database đồng thời.
- Connection pool và giới hạn I/O.
- Kafka consumer max.poll.records và max.poll.interval.ms phù hợp thời gian xử lý.
- Tốc độ retry và concurrency tới dependency ngoài.
- Ngưỡng backlog kích hoạt giảm tốc producer hoặc cảnh báo.

Khi backlog tăng, có thể giảm concurrency ở dependency đang quá tải, tăng worker nếu còn tài nguyên, hoặc tạm dừng một số luồng không khẩn cấp. Tăng consumer count vượt số partition không làm tăng song song cho một topic nếu không có thêm partition hoặc topic phù hợp.

Backpressure nên lan truyền có kiểm soát. Tránh để worker lấy một batch lớn rồi giữ toàn bộ trong memory trong khi database đang chậm.

## 16. Quan sát batch processing

Cần đo cả throughput lẫn latency và tỷ lệ lỗi:

| Metric | Ý nghĩa |
|---|---|
| event_batch_size | Số event thực tế trong mỗi batch |
| event_batch_duration | Thời gian xử lý một batch |
| event_batch_items_total | Tổng số item đã xử lý |
| event_batch_failure_total | Số batch thất bại |
| event_batch_partial_failure_total | Số batch có item lỗi |
| event_batch_retry_total | Số lần retry batch/chunk |
| event_batch_queue_depth | Số item đang chờ |
| event_batch_oldest_age | Tuổi item chờ lâu nhất |
| projection_write_duration | Thời gian ghi projection |
| kafka_consumer_lag | Độ trễ consumer so với log mới nhất |

Log nên có batch ID, worker ID, số item, thời gian bắt đầu/kết thúc, số thành công, số retry và danh sách event ID lỗi khi cần điều tra. Không ghi toàn bộ payload.

Không dùng batch ID, event ID hoặc aggregate ID làm metric tag vì cardinality cao. Có thể dùng event type, destination, consumer group và outcome làm tag.

## 17. Kiểm thử batch processing

Kiểm thử nên xác minh cả kết quả dữ liệu và hành vi phục hồi:

1. Batch nhỏ hơn batch size vẫn được flush khi hết thời gian chờ.
2. Batch đạt giới hạn item được xử lý ngay.
3. Batch write tạo đúng dữ liệu và giảm số lần gọi persistence theo thiết kế.
4. Event duplicate không tạo side effect lặp.
5. Một item lỗi được xử lý theo semantics all-or-nothing hoặc per-item đã chọn.
6. Worker dừng giữa batch có thể phục hồi từ trạng thái bền vững.
7. Hai worker đồng thời không claim cùng một item.
8. Event cùng aggregate giữ đúng ordering/version.
9. Transaction rollback không để inbox đánh dấu hoàn tất khi projection chưa commit.
10. Kafka offset chỉ commit sau khi batch hoặc item đã xử lý/lưu lỗi bền vững.
11. Backpressure giới hạn concurrency và queue growth.
12. Batch size thay đổi không làm sai kết quả nghiệp vụ.

Dùng database và broker test phù hợp để xác minh locking, batch SQL, acknowledgment và offset. Mock repository có thể kiểm tra orchestration nhưng không chứng minh batching thực sự được database driver thực hiện.

## 18. Checklist trước khi đưa batch vào production

Trước khi bật batch processing, xác nhận:

- Biết rõ tầng nào đang cần batching và bottleneck đã được đo.
- Event độc lập hay là một batch event nghiệp vụ đã được phân biệt.
- Listener chỉ xác nhận sau khi event được xử lý hoặc bàn giao bền vững.
- Inbox có event ID duy nhất và trạng thái từng item.
- Batch size có giới hạn theo item, byte và thời gian chờ.
- Claim/lease an toàn khi chạy nhiều worker.
- Transaction được chia chunk phù hợp với thời gian và phạm vi rollback.
- Upsert và deduplication bảo đảm idempotency.
- Ordering theo aggregate được giữ nếu nghiệp vụ yêu cầu.
- Lỗi từng item, retry, quarantine và replay có policy rõ.
- Kafka producer/consumer batch và acknowledgment được cấu hình nhất quán.
- Backpressure, metrics, logs và cảnh báo đã sẵn sàng.
- Có phương án giảm batch size hoặc tắt worker khi dependency quá tải.

Batch processing giúp tăng hiệu quả khi nhiều event cần thực hiện các thao tác tương tự, nhưng chỉ an toàn khi trạng thái từng event vẫn được theo dõi. Kết hợp durable inbox, batch size có giới hạn, transaction theo chunk, idempotency, ordering và backpressure giúp ứng dụng Spring Modulith tăng throughput mà vẫn có thể phục hồi chính xác khi một phần batch gặp lỗi.

