# Kiểm thử lỗi

Application events giúp các module Spring Modulith giao tiếp qua những sự kiện nghiệp vụ, nhưng luồng xử lý có thể thất bại ở nhiều thời điểm: transaction phát event rollback, listener chạy sau commit gặp exception, publication bị gửi lại, database timeout hoặc consumer nhận message nhưng không commit offset. Kiểm thử thành công chỉ chứng minh đường đi bình thường hoạt động; kiểm thử lỗi mới cho thấy hệ thống có giữ được dữ liệu, phục hồi được và tránh tạo side effect trùng hay không.

**Kiểm thử lỗi** cần chủ động tạo ra các tình huống thất bại tại đúng ranh giới của hệ thống, xác minh trạng thái sau lỗi và chứng minh lần phục hồi tiếp theo không làm sai nghiệp vụ. Mục tiêu là kiểm tra hành vi quan sát được: transaction, publication, retry, inbox, projection, offset và cảnh báo.

## 1. Xác định các điểm có thể thất bại

Một event thường đi qua nhiều bước. Mỗi bước có một kiểu lỗi và một cơ chế phục hồi khác nhau:

~~~text
Business transaction
       |
       v
Publish application event
       |
       v
Commit transaction
       |
       v
Event Publication Registry
       |
       v
Listener / externalization
       |
       v
Database / Kafka / HTTP dependency
       |
       v
Consumer / projection
~~~

Các nhóm lỗi cần kiểm thử:

| Điểm lỗi | Tình huống | Điều cần xác minh |
|---|---|---|
| Transaction nguồn | Exception trước commit | Không có thay đổi nghiệp vụ hoặc event được giao như thể đã commit |
| Listener | Exception khi xử lý sau commit | Publication không bị đánh dấu hoàn tất giả |
| Persistence | Database timeout hoặc deadlock | Transaction rollback và có thể retry |
| External service | Timeout sau khi request có thể đã tới đích | Không tạo side effect trùng khi retry |
| Message broker | Broker không sẵn sàng hoặc send timeout | Publication còn khả năng phục hồi |
| Consumer | Process dừng trước khi commit offset | Message có thể được giao lại và xử lý idempotent |
| Schema | Payload không deserialize được | Event được quarantine hoặc dead-letter theo policy |
| Ordering | Event version mới đến trước version cũ | Projection không lùi trạng thái |
| Runtime | Process restart giữa các bước | Trạng thái bền vững cho phép tiếp tục |

Không nên chỉ mock toàn bộ dependency rồi kết luận luồng event đáng tin cậy. Unit test phù hợp để kiểm tra policy và nhánh logic; integration test cần xác minh transaction, database constraint, publication state và broker behavior thực tế.

## 2. Kiểm thử event chỉ được xử lý sau commit

Với listener xử lý sau commit, event không nên tạo side effect nếu transaction nguồn rollback. Đây là một trong những kiểm thử quan trọng nhất cho ranh giới nghiệp vụ.

Một kịch bản cần kiểm tra:

1. Bắt đầu transaction nghiệp vụ.
2. Phát application event.
3. Chủ động rollback transaction.
4. Xác minh listener không thực hiện side effect sau commit.
5. Chạy một transaction commit thành công.
6. Xác minh listener được thực thi sau khi commit.

Ví dụ kiểm thử minh họa với Spring Test:

~~~java
@SpringBootTest
class OrderEventTransactionTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderProjectionRepository projectionRepository;

    @Test
    void rolledBackTransactionDoesNotUpdateProjection() {
        assertThrows(
            IllegalStateException.class,
            () -> orderService.placeOrderAndFail()
        );

        assertFalse(
            projectionRepository.existsByOrderId(TEST_ORDER_ID)
        );
    }
}
~~~

Ví dụ giả định phương thức placeOrderAndFail phát event rồi ném exception trong cùng transaction. Cần xác minh transaction thực sự rollback và listener được cấu hình theo semantics sau commit. Nếu test method tự mang transaction, transaction của test có thể làm thay đổi thời điểm commit; hãy chủ động điều khiển transaction trong test để không kiểm tra nhầm một transaction chưa kết thúc.

Ngoài rollback, kiểm tra trường hợp transaction commit nhưng listener chạy bất đồng bộ. Không dùng một assertion tức thời ngay sau method call nếu listener chạy trên executor khác. Dùng Awaitility hoặc cơ chế đồng bộ test phù hợp để chờ điều kiện cuối cùng với timeout hữu hạn.

## 3. Kiểm thử exception trong listener

Listener thất bại phải có hành vi đúng với policy. Nếu exception được truyền ra khỏi listener và publication được registry theo dõi, publication có thể còn incomplete để phục hồi. Nếu listener bắt exception rồi kết thúc bình thường, registry có thể coi lần xử lý là thành công.

Ví dụ listener cần giữ lỗi để cơ chế theo dõi nhận biết:

~~~java
@Component
class PaymentProjectionListener {

    private final PaymentProjection projection;

    PaymentProjectionListener(PaymentProjection projection) {
        this.projection = projection;
    }

    @ApplicationModuleListener
    void on(PaymentCaptured event) {
        projection.apply(event);
    }
}
~~~

Một unit test có thể mock service để ném lỗi và xác minh exception được truyền ra:

~~~java
@Test
void listenerPropagatesFailure() {
    PaymentProjection projection = mock(PaymentProjection.class);
    PaymentProjectionListener listener =
        new PaymentProjectionListener(projection);

    PaymentCaptured event = samplePaymentCaptured();

    doThrow(new TransientDataAccessException("temporary") {})
        .when(projection)
        .apply(event);

    assertThrows(
        TransientDataAccessException.class,
        () -> listener.on(event)
    );
}
~~~

Đây là kiểm thử đơn vị cho hành vi listener. Nó chưa chứng minh Event Publication Registry lưu trạng thái incomplete; cần integration test chạy qua application context và persistence registry thực tế.

Cũng cần kiểm thử nhánh lỗi được bỏ qua có chủ đích. Nếu policy cho phép skip, xác minh quyết định skip được ghi audit và listener chỉ kết thúc bình thường sau khi việc ghi nhận đó thành công.

## 4. Kiểm thử Event Publication Registry

Event Publication Registry theo dõi publication của event tới listener. Kiểm thử lỗi cần xác minh các trạng thái quan trọng:

- Publication được tạo khi event được phát trong luồng transaction phù hợp.
- Listener thành công thì publication được đánh dấu hoàn tất.
- Listener thất bại thì publication vẫn có thể được nhận diện là incomplete.
- Resubmit một publication incomplete có thể kích hoạt listener lại.
- Publication đã hoàn tất không bị xử lý lại ngoài ý muốn.
- Trạng thái publication còn tồn tại sau restart khi registry dùng persistence bền vững.

Có thể dùng abstraction **IncompleteEventPublications** để truy vấn hoặc yêu cầu resubmit publication cũ chưa hoàn tất, tùy API của phiên bản Spring Modulith đang dùng. Không giả định một lời gọi resubmit trả về thành công đồng nghĩa listener đã xử lý thành công; listener bất đồng bộ có thể hoàn tất sau đó.

Một integration test nên cố ý làm listener thất bại ở lần đầu và thành công ở lần sau. Sau lần đầu, kiểm tra publication chưa hoàn tất. Sau khi resubmit, chờ listener hoàn thành rồi kiểm tra trạng thái publication đã được đánh dấu hoàn tất.

Registry không phải event store đầy đủ. Test cần kiểm tra publication lifecycle, không giả định registry giữ toàn bộ lịch sử event đã hoàn tất để replay từ đầu.

## 5. Kiểm thử retry và backoff

Retry policy cần được kiểm thử độc lập với thời gian thực. Dùng Clock có thể điều khiển hoặc abstraction scheduler để test thời điểm được retry.

Các tình huống cần có:

| Tình huống | Kết quả mong đợi |
|---|---|
| Lỗi tạm thời ở attempt đầu | Lên lịch retry |
| Chưa tới nextAttemptAt | Không resubmit |
| Đã tới thời điểm retry | Publication được claim và thử lại |
| Lỗi tiếp tục lặp | Delay tăng theo policy và không vượt max delay |
| Nhiều worker cùng chạy | Một publication chỉ được claim bởi một worker tại một thời điểm |
| Hết max attempts | Chuyển quarantine/manual review và phát cảnh báo |
| Lỗi vĩnh viễn | Không retry vô hạn |
| Retry thành công | Publication hoàn tất và retry state được đóng |

Ví dụ test policy với clock giả:

~~~java
@Test
void retryIsNotDueBeforeScheduledTime() {
    Instant now = Instant.parse("2026-11-25T10:00:00Z");
    Clock clock = Clock.fixed(now, ZoneOffset.UTC);

    RetryState state = new RetryState(
        PUBLICATION_ID,
        1,
        now.plusSeconds(30)
    );

    assertFalse(state.isDue(clock.instant()));
}
~~~

Ví dụ giả định RetryState là model do ứng dụng định nghĩa. Với backoff có jitter, inject nguồn random hoặc tách phép tính cơ sở khỏi random để test có kết quả xác định. Không dùng Thread.sleep dài trong test vì làm suite chậm và dễ flaky.

## 6. Kiểm thử duplicate và idempotency

Message có thể được giao lại sau timeout, restart hoặc khi consumer xử lý xong nhưng chưa commit offset. Kiểm thử cần chứng minh cùng một event không tạo hiệu ứng nghiệp vụ hai lần.

Một inbox table thường dùng unique constraint theo consumer và event ID:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Các tình huống cần kiểm tra:

1. Gửi event lần đầu và xác minh projection được cập nhật.
2. Gửi lại cùng event ID và xác minh không tạo thêm hiệu ứng.
3. Gửi event khác ID cho cùng aggregate và xác minh event mới vẫn được xử lý.
4. Làm projection update thất bại sau inbox insert và xác minh transaction rollback cả hai.
5. Gửi đồng thời cùng event từ hai worker và xác minh chỉ một transaction áp dụng hiệu ứng.
6. Replay event cũ sau một khoảng thời gian và xác minh chính sách retention deduplication vẫn bảo vệ dữ liệu.

Không chỉ mock repository để giả lập exists-check. Race condition chỉ được kiểm tra đáng tin cậy khi chạy với database thật hoặc Testcontainers, có unique constraint và transaction tương ứng.

## 7. Kiểm thử event sai thứ tự và version gap

Nếu projection phụ thuộc thứ tự event theo aggregate, cần tạo các kịch bản version:

~~~text
Current projection version: 5

Receive version 7
Receive version 6
Receive version 7 again
Receive version 4
~~~

Xác minh:

- Version 7 không được áp dụng như delta nếu version 6 còn thiếu.
- Khi version 6 được xử lý, hệ thống có thể tiếp tục version 7.
- Version 7 được giao lại không tạo hiệu ứng trùng.
- Version 4 cũ không ghi đè projection hiện tại.
- Gap không được retry vô hạn mà không có cảnh báo hoặc deadline.

Với event snapshot đầy đủ, policy có thể cho phép áp dụng version mới nhất mà không cần từng delta trước đó. Test phải phản ánh semantics snapshot/delta thực tế; không dùng cùng expectation cho cả hai loại.

Nếu dùng Kafka, gửi các event cùng aggregate key và xác minh chúng được xử lý theo partition/order policy. Test cũng nên mô phỏng rebalance hoặc consumer restart nếu luồng phụ thuộc vào offset.

## 8. Kiểm thử lỗi database và transaction

Các lỗi database thường gồm deadlock, lock timeout, connection loss, constraint violation và transaction rollback. Cần phân biệt lỗi tạm thời có thể retry với lỗi dữ liệu không nên retry.

Kịch bản quan trọng:

- Database ngắt kết nối trước khi ghi projection.
- Deadlock xảy ra khi nhiều transaction cập nhật cùng aggregate.
- Unique constraint phát hiện duplicate event.
- Projection update lỗi sau inbox insert.
- Process dừng trước commit.
- Transaction commit thành công nhưng ứng dụng mất kết nối trước khi nhận kết quả.

Với lỗi sau commit nhưng mất phản hồi, trạng thái phía ứng dụng có thể không rõ. Khi retry, idempotency phải ngăn side effect lặp. Test cần xác minh kết quả cuối cùng ở database thay vì chỉ kiểm tra exception được ném.

Không nên mô phỏng mọi lỗi bằng một RuntimeException. Dùng lỗi cụ thể hoặc fault injection ở đúng ranh giới để bảo đảm policy phân loại đúng.

## 9. Kiểm thử Kafka producer và consumer failure

Với Kafka, cần kiểm tra producer và consumer riêng:

**Producer:**

- Broker không sẵn sàng khi gửi.
- Send timeout hoặc lỗi xác nhận.
- Producer retry và idempotence theo cấu hình.
- Broker đã ghi record nhưng ứng dụng dừng trước khi registry ghi nhận listener hoàn tất.
- Publication được resubmit và consumer nhận duplicate.

**Consumer:**

- Deserialization failure.
- Listener exception trước khi ghi database.
- Listener exception sau một phần xử lý.
- Process dừng sau database commit nhưng trước offset commit.
- DLT send failure.
- Retry topic làm thay đổi thứ tự record.

Khi consumer gửi record sang dead-letter topic, chỉ commit offset gốc sau khi record lỗi đã được lưu bền vững theo policy. Nếu DLT send thất bại, không được acknowledge record gốc như thể đã xử lý xong.

Dùng Kafka broker test hoặc Testcontainers để xác minh headers, key, partition, offset và acknowledgment. Mock KafkaTemplate không thể chứng minh broker thực sự đã ghi record.

## 10. Kiểm thử timeout và kết quả không xác định

Một timeout không nhất thiết có nghĩa thao tác bên ngoài thất bại. Request có thể đã tới dịch vụ đích và được thực hiện, nhưng response bị mất trên đường về.

Ví dụ, producer gọi API tạo thanh toán. Client timeout nhưng dịch vụ thanh toán đã ghi nhận giao dịch. Retry bằng request mới có thể tạo thanh toán thứ hai.

Test cần mô phỏng:

1. Dịch vụ đích nhận request và thực hiện side effect.
2. Response bị trì hoãn hoặc bị cắt trước khi client nhận.
3. Producer/consumer ghi nhận timeout.
4. Retry dùng cùng idempotency key hoặc truy vấn trạng thái giao dịch.
5. Xác minh chỉ có một giao dịch nghiệp vụ được tạo.

Nếu không có idempotency key hoặc API truy vấn trạng thái, policy cần đưa event vào reconciliation/manual review thay vì retry mù quáng hoặc compensation ngay.

## 11. Kiểm thử process restart và phục hồi

Một hệ thống event đáng tin cậy phải phục hồi sau khi process dừng ở các điểm khác nhau:

| Điểm dừng | Trạng thái cần kiểm tra sau restart |
|---|---|
| Trước khi transaction nguồn commit | Không có event được coi là đã phát thành công |
| Sau commit, trước listener | Publication có thể được phục hồi |
| Trong listener trước khi transaction projection commit | Transaction rollback và event có thể thử lại |
| Sau projection commit, trước khi publication complete | Redelivery không tạo side effect trùng |
| Sau khi claim retry, trước khi resubmit | Lease hết hạn để worker khác tiếp quản |
| Sau khi ghi DLT, trước khi commit Kafka offset | Redelivery không tạo bản ghi lỗi trùng hoặc side effect trùng |

Integration test có thể khởi động application context, thực hiện một phần công việc, đóng context và khởi động lại với cùng database/container. Dùng persistence thật cho registry, inbox và retry state. Không chỉ kiểm tra restart bằng cách tạo object mới trong cùng JVM nếu điều đó không tái hiện mất process state.

## 12. Kiểm thử observability và audit khi lỗi

Khi lỗi xảy ra, hệ thống cần để lại dấu vết đủ để điều tra:

- Event ID và publication ID.
- Event type và listener ID.
- Aggregate ID/version nếu có.
- Attempt hiện tại và next attempt time.
- Error category và policy action.
- Trace ID, correlation ID và causation ID.
- Kafka topic/partition/offset nếu có.
- Quarantine/DLT reference khi đã chuyển lỗi.

Kiểm thử cần xác minh log hoặc telemetry có các trường cần thiết, nhưng không chứa token, credential hoặc payload nhạy cảm. Không dùng event ID hay trace ID làm metric label vì cardinality cao; dùng chúng trong log hoặc trace.

Một số metric nên theo dõi:

| Metric | Mục tiêu |
|---|---|
| listener_failure_total | Phát hiện listener thường xuyên lỗi |
| publication_incomplete | Theo dõi publication chưa hoàn tất |
| publication_oldest_age | Phát hiện event bị kẹt |
| retry_attempt_total | Theo dõi tần suất retry |
| retry_exhausted_total | Phát hiện event hết ngân sách |
| quarantine_total | Theo dõi event cần can thiệp |
| duplicate_event_total | Theo dõi redelivery |
| event_processing_duration | Theo dõi độ trễ xử lý |

Test nên kiểm tra metric tăng đúng ở nhánh lỗi, retry và quarantine. Với tracing, xác minh trace hoặc log giữ event ID/correlation ID qua producer và consumer theo thiết kế.

## 13. Tổ chức failure test theo tầng

Một test strategy hiệu quả có nhiều tầng:

| Tầng test | Công cụ/phương pháp | Phạm vi |
|---|---|---|
| Unit test | JUnit, Mockito, fake Clock | Phân loại lỗi, backoff, retry policy, listener exception |
| Spring integration test | Application context, transaction manager, test event capture | After-commit, listener wiring, publication lifecycle |
| Database integration test | Database thật hoặc Testcontainers | Unique constraint, inbox atomicity, deadlock, upsert |
| Broker integration test | Kafka Testcontainers hoặc broker test | Producer acknowledgment, consumer offset, DLT, redelivery |
| Recovery test | Restart context/process và giữ persistence | Registry, retry state, lease và replay |
| Contract test | Payload/schema fixtures | Deserialization, schema compatibility và event metadata |

Không cần chạy mọi loại test cho mỗi thay đổi nhỏ. Chọn tầng phù hợp với ranh giới bị thay đổi, nhưng các luồng quan trọng cần có ít nhất một kiểm thử tích hợp chứng minh hành vi persistence và recovery.

Test bất đồng bộ nên dùng Awaitility hoặc polling với timeout hữu hạn. Tránh sleep cố định vì thời gian xử lý trên CI có thể khác máy phát triển. Test cần cleanup dữ liệu và topic riêng để không phụ thuộc vào thứ tự chạy.

## 14. Tránh test flaky và false positive

Một số lỗi kiểm thử thường gặp:

- Assertion ngay sau publish dù listener chạy bất đồng bộ.
- Dùng transaction của test khiến after-commit callback không bao giờ chạy trong thời gian test mong đợi.
- Chỉ verify method được gọi mà không xác minh trạng thái database.
- Mock Event Publication Registry rồi kết luận persistence/restart hoạt động.
- Dùng sleep cố định để đợi consumer.
- Dùng chung topic hoặc consumer group giữa các test gây nhiễu.
- Bắt exception trong listener test nhưng không xác minh publication state.
- Kiểm thử duplicate bằng repository mock thay vì unique constraint thật.
- Dùng thời gian hệ thống trực tiếp làm retry test không xác định.

Để giảm flaky, dùng test fixture có event ID cố định, topic/group riêng, clock giả, timeout rõ và điều kiện kết thúc có thể quan sát. Khi kiểm thử broker, chờ consumer nhận đúng event ID thay vì chờ một khoảng thời gian tùy ý.

## 15. Checklist kiểm thử lỗi

Trước khi xem luồng event đã có khả năng phục hồi, xác nhận:

- Transaction rollback không phát side effect sau commit.
- Listener exception không bị nuốt khi publication cần retry.
- Publication thành công và incomplete được phản ánh đúng trong registry.
- Retry có backoff, max attempts, deadline và hành vi exhausted.
- Event duplicate không tạo side effect trùng.
- Event sai thứ tự hoặc version gap được xử lý theo semantics.
- Database rollback giữ inbox và projection nhất quán.
- Timeout không rõ kết quả dùng idempotency hoặc reconciliation.
- Kafka offset chỉ commit sau khi xử lý hoặc lưu lỗi bền vững.
- DLT send failure không làm mất record gốc.
- Process restart có thể tiếp tục publication/retry đã lưu.
- Log, metric và trace có đủ định danh nhưng không lộ dữ liệu nhạy cảm.
- Test bất đồng bộ không phụ thuộc sleep cố định và không flaky.

Kiểm thử lỗi giúp chứng minh hệ thống có thể chịu được những tình huống xảy ra giữa các bước, nơi transaction đã commit nhưng listener chưa chạy, broker đã nhận message nhưng producer chưa ghi nhận kết quả, hoặc consumer đã cập nhật database nhưng chưa commit offset. Khi kiểm tra các ranh giới này bằng fault injection, persistence thật và assertion trên trạng thái cuối, ứng dụng Spring Modulith có thể phục hồi mà không làm mất event hoặc lặp hiệu ứng nghiệp vụ.

