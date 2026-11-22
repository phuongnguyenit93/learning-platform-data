# Kiểm thử sự kiện trùng, sai thứ tự và gián đoạn downstream

Trong chương **Dự án xử lý sự kiện**, một pipeline serverless phải xử lý đúng dữ liệu ngay cả khi message được giao nhiều lần, event đến sai thứ tự hoặc dịch vụ phía sau tạm thời không phản hồi. Những lỗi này là đặc tính bình thường của hệ thống phân tán: producer có thể retry sau timeout, queue có thể giao lại message, nhiều Lambda có thể chạy song song và downstream có thể đã thực hiện side effect dù caller chưa nhận được response.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Dự án này biến các rủi ro đó thành bộ kiểm thử có thể chạy lặp lại, quan sát được và xác minh bằng trạng thái dữ liệu cuối cùng.

## 1. Mục tiêu của dự án

Xây dựng một event-processing flow cho nghiệp vụ đơn hàng. Producer phát các event như OrderCreated, PaymentAuthorized và OrderCancelled. Java consumer nhận event từ queue hoặc event bus, cập nhật trạng thái đơn hàng và gọi một dịch vụ downstream.

Bộ kiểm thử phải chứng minh được ba nhóm hành vi:

1. **Duplicate delivery:** cùng một event được giao hai hoặc nhiều lần nhưng business effect chỉ được áp dụng một lần.
2. **Out-of-order delivery:** event version mới đến trước event cũ hoặc event bị thiếu; hệ thống không ghi đè trạng thái mới bằng dữ liệu cũ và có quy tắc xử lý gap.
3. **Downstream interruption:** API hoặc database phía sau timeout, trả 5xx/throttling hoặc ngừng hoạt động; hệ thống giữ được công việc, retry có kiểm soát và phục hồi sau khi dependency hoạt động trở lại.

Không chỉ kiểm tra HTTP status hoặc log. Mỗi test cần xác minh trạng thái bền vững: order version, inbox/dedup record, outbox record, số side effect, message retry/DLQ và kết quả cuối cùng.

## 2. Kiến trúc tham chiếu

~~~mermaid
flowchart TD
    P["Order producer"] --> Q["Queue / Event bus"]
    Q --> C["Java Lambda consumer"]
    C --> V["Validate event and version"]
    V --> I["Inbox / idempotency store"]
    I --> DB["Order database"]
    C --> D["Downstream API"]
    C --> O["Outbox for follow-up events"]
    Q --> DLQ["DLQ / quarantine"]
    C --> M["Metrics, logs and traces"]
    D --> M
    DB --> M
~~~

Các thành phần cần có trong môi trường test:

- Producer hoặc fixture tạo event có eventId và aggregateVersion ổn định.
- Queue/event source để mô phỏng delivery, retry và redrive.
- Java handler chịu trách nhiệm validate, deduplicate và cập nhật business state.
- Database có unique constraint, conditional update hoặc transaction.
- Downstream stub có thể trả success, timeout, 429 hoặc 5xx theo kịch bản.
- DLQ/quarantine để giữ message lỗi quá số lần thử.
- Metrics/logs/traces để quan sát retry, duplicate, stale event và processing lag.

Với dự án nhỏ, có thể chạy consumer như một Java service trong test. Sau đó thêm adapter kiểm thử cho Lambda event format hoặc event source mapping. Tách business logic khỏi adapter giúp unit test không phụ thuộc runtime cloud.

## 3. Event contract dùng trong bài test

Mỗi event nên có định danh, aggregate và version rõ ràng:

~~~json
{
  "eventId": "evt-order-42-v3",
  "eventType": "OrderStatusChanged",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "order-42",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-17T10:15:00Z",
  "correlationId": "corr-checkout-77",
  "payload": {
    "status": "PAID",
    "paymentId": "payment-91"
  }
}
~~~

Các field có vai trò khác nhau:

- eventId nhận diện một event qua retry, redrive và replay.
- aggregateId xác định entity mà event thay đổi.
- aggregateVersion biểu diễn thứ tự nghiệp vụ trong aggregate.
- eventType xác định cách xử lý.
- schemaVersion xác định cấu trúc payload.
- correlationId liên kết các bước trong một workflow.

Không dùng queue message ID thay eventId nghiệp vụ nếu cùng event có thể được publish qua nhiều transport. Không dùng timestamp đơn thuần để quyết định event nào mới hơn; đồng hồ producer có thể lệch.

Test fixture phải giữ eventId và version giống nhau khi mô phỏng duplicate. Nếu mỗi lần gửi test lại tạo eventId mới, test không còn kiểm tra duplicate mà đang kiểm tra hai event độc lập.

## 4. Định nghĩa invariant trước khi viết test

Invariant là điều kiện dữ liệu phải luôn đúng. Với order processing, ví dụ:

- Một eventId chỉ được áp dụng một lần cho cùng consumer.
- Order version chỉ tăng theo quy tắc đã định.
- Event cũ không được ghi đè trạng thái mới.
- Event có version bị thiếu không được áp dụng vượt qua gap nếu nghiệp vụ yêu cầu tuần tự.
- Một payment authorization không được tạo hai lần charge.
- Message chỉ được ACK sau khi business state hoặc pending state đã được lưu bền vững.
- Một lỗi downstream không được làm mất event.
- Retry không được tạo ra side effect không kiểm soát.

Viết invariant thành assertion cụ thể. Ví dụ, sau khi gửi cùng một PaymentAuthorized event ba lần, order vẫn ở trạng thái PAID, version chỉ tăng một lần và payment provider chỉ ghi nhận một operation với cùng idempotency key.

## 5. Thiết kế trạng thái xử lý event

Một consumer có thể phân loại kết quả:

| Kết quả | Ý nghĩa | Hành động với message |
|---|---|---|
| APPLIED | Event đã được áp dụng và commit | ACK/checkpoint |
| DUPLICATE | Event đã được áp dụng trước đó | ACK sau khi xác minh |
| STALE | Event cũ theo version/sequence | ACK hoặc audit theo policy |
| DEFERRED_GAP | Thiếu event version trước | Lưu pending bền vững rồi ACK, hoặc retry theo thiết kế |
| RETRYABLE_FAILURE | Dependency lỗi tạm thời | Không ACK; retry theo trigger policy |
| PERMANENT_FAILURE | Payload/schema/business error không thể tự hết | Quarantine/DLQ |
| CONFLICT | Cùng version nhưng nội dung/event identity xung đột | Quarantine và cảnh báo |

Không gom mọi exception thành RETRYABLE_FAILURE. AccessDenied, payload malformed hoặc version conflict thường không tự hết khi retry. Ngược lại, nếu một event version gap đã được lưu vào pending table bền vững, có thể ACK message gốc và để một worker riêng xử lý khi gap được lấp.

## 6. Bộ test duplicate delivery

Duplicate có thể xảy ra khi:

- Consumer xử lý xong nhưng timeout trước ACK.
- Queue visibility timeout hết trong khi invocation cũ vẫn chạy.
- Publisher gửi thành công nhưng crash trước khi ghi nhận published.
- Event được redrive hoặc replay.
- Producer retry vì không nhận được response.

Test phải gửi cùng eventId nhiều lần và kiểm tra kết quả nghiệp vụ, không chỉ số lần handler được gọi.

### 6.1. Test cùng một event tuần tự

Ví dụ JUnit 5 với repository và handler được cấu hình trong test:

~~~java
@Test
void duplicateEventDoesNotRepeatBusinessEffect() {
    OrderCreated event = fixtures.orderCreated(
            "evt-100",
            "order-42",
            1);

    ProcessingResult first = handler.handle(event);
    ProcessingResult second = handler.handle(event);
    ProcessingResult third = handler.handle(event);

    assertThat(first).isEqualTo(ProcessingResult.APPLIED);
    assertThat(second).isEqualTo(ProcessingResult.DUPLICATE);
    assertThat(third).isEqualTo(ProcessingResult.DUPLICATE);

    assertThat(orderRepository.find("order-42").version()).isEqualTo(1);
    assertThat(inboxRepository.count("order-consumer", "evt-100"))
            .isEqualTo(1);
    assertThat(outboxRepository.countByCausationId("evt-100"))
            .isEqualTo(1);
}
~~~

Các repository và fixture ở đây là abstraction của dự án. Test integration phải dùng database thật hoặc Testcontainers để xác minh unique constraint và transaction, không chỉ mock repository.

### 6.2. Test duplicate đồng thời

Hai invocation có thể chạy song song trên hai execution environment. Test đồng thời giúp phát hiện race condition khi code chỉ thực hiện “check rồi insert” bằng hai thao tác riêng biệt.

~~~java
@Test
void concurrentDuplicateIsAppliedOnlyOnce() throws Exception {
    OrderPaid event = fixtures.orderPaid(
            "evt-pay-200",
            "order-42",
            2);

    var pool = Executors.newFixedThreadPool(2);
    try {
        var first = pool.submit(() -> handler.handle(event));
        var second = pool.submit(() -> handler.handle(event));

        List<ProcessingResult> results =
                List.of(first.get(), second.get());

        assertThat(results)
                .containsExactlyInAnyOrder(
                        ProcessingResult.APPLIED,
                        ProcessingResult.DUPLICATE);

        assertThat(paymentRepository.countByEventId("evt-pay-200"))
                .isEqualTo(1);
    } finally {
        pool.shutdownNow();
    }
}
~~~

Trong test thực tế, cần đồng bộ hai worker để chúng cùng bắt đầu gần như đồng thời, ví dụ dùng CountDownLatch. Nếu test chỉ chạy tuần tự do scheduler, nó chưa chắc tạo ra race. Unique constraint hoặc conditional write phải là lớp bảo vệ cuối cùng ở database.

### 6.3. Test crash sau side effect nhưng trước ACK

Đây là cửa sổ lỗi quan trọng:

1. Consumer gọi downstream thành công.
2. Consumer ghi business state hoặc nhận response.
3. Invocation bị dừng trước ACK.
4. Queue giao lại event.
5. Consumer nhận lại cùng eventId.

Kết quả mong đợi là downstream không thực hiện side effect lần hai. Nếu provider hỗ trợ idempotency key, gửi cùng key trong cả hai lần. Test cần xác minh provider stub ghi nhận một operation logic dù nhận nhiều HTTP request.

Nếu downstream không hỗ trợ idempotency, cần một trạng thái operation nội bộ và reconciliation cho kết quả không rõ. Không thể chỉ dựa vào một boolean trong memory của Lambda.

## 7. Test event sai thứ tự

Giả sử order hiện ở version 1, rồi producer phát:

- Version 2: trạng thái PAID.
- Version 3: trạng thái FULFILLING.

Nếu consumer nhận version 3 trước version 2, cách xử lý phụ thuộc event contract. Với delta event yêu cầu tuần tự, version 3 phải được giữ chờ. Với snapshot event tự chứa trạng thái đầy đủ, có thể áp dụng snapshot mới hơn nếu domain cho phép bỏ qua intermediate state. Test phải cố định semantics này.

### 7.1. Test event đến ngược thứ tự

~~~java
@Test
void versionGapIsDeferredUntilMissingEventArrives() {
    OrderStatusChanged version3 = fixtures.statusChanged(
            "evt-order-v3",
            "order-42",
            3,
            "FULFILLING");

    OrderStatusChanged version2 = fixtures.statusChanged(
            "evt-order-v2",
            "order-42",
            2,
            "PAID");

    ProcessingResult early = handler.handle(version3);
    assertThat(early).isEqualTo(ProcessingResult.DEFERRED_GAP);
    assertThat(orderRepository.find("order-42").version()).isEqualTo(1);

    ProcessingResult next = handler.handle(version2);
    assertThat(next).isEqualTo(ProcessingResult.APPLIED);

    pendingEventDispatcher.processReady("order-42");

    Order finalOrder = orderRepository.find("order-42");
    assertThat(finalOrder.version()).isEqualTo(3);
    assertThat(finalOrder.status()).isEqualTo("FULFILLING");
}
~~~

Test cần xác minh version 3 đã được lưu pending trước khi message gốc được ACK. Sau khi version 2 được commit, pending dispatcher áp dụng version 3 đúng một lần.

### 7.2. Test event cũ đến sau event mới

Nếu order đã ở version 3, event version 2 đến muộn không được ghi đè trạng thái. Kết quả có thể là STALE hoặc DUPLICATE tùy eventId và lịch sử đã xử lý.

Phân biệt hai trường hợp:

- Cùng eventId đã áp dụng: duplicate.
- eventId khác nhưng version thấp hơn current: stale hoặc conflict theo contract.

Không đánh dấu mọi event version thấp là duplicate mà không kiểm tra identity. Hai event khác nhau cùng version có thể chỉ ra producer bug.

### 7.3. Test cùng version nhưng khác payload

Tạo hai event có cùng aggregateId và aggregateVersion nhưng eventId hoặc payload khác nhau. Consumer cần phát hiện conflict, không chọn event đến sau một cách tùy tiện. Ghi audit, giữ payload và đưa vào quarantine/manual review nếu không có quy tắc domain rõ ràng.

## 8. Test downstream interruption

Downstream có thể:

- Trả 429 do rate limit.
- Trả 500/502/503 do sự cố.
- Không phản hồi cho tới khi client timeout.
- Đóng kết nối giữa chừng.
- Thành công nhưng response bị mất.
- Trả lỗi vĩnh viễn như 400 hoặc 403.

Mỗi loại lỗi cần hành vi riêng. Không retry mọi status code.

| Failure injection | Hành vi mong đợi |
|---|---|
| HTTP 429 | Tôn trọng Retry-After nếu có, backoff và giới hạn tốc độ |
| HTTP 500/503 | Retry có giới hạn với exponential backoff và jitter |
| Connect/read timeout | Xem kết quả có thể chưa rõ; retry bằng cùng idempotency key |
| HTTP 400 | Quarantine hoặc trả lỗi nghiệp vụ, không retry vô hạn |
| HTTP 403 | Cảnh báo cấu hình/quyền, dừng retry nhanh |
| Connection refused | Giữ message, retry theo policy |
| Database unavailable | Không ACK trước khi state được commit |
| Downstream phục hồi | Backlog được xử lý dần mà không tạo burst |

Nếu dependency lỗi kéo dài, circuit breaker hoặc load shedding có thể ngăn worker liên tục gọi một dịch vụ đang mất khả năng phục vụ. Queue tạo buffer để công việc chờ phục hồi thay vì giữ hàng nghìn invocation đang sleep.

## 9. Mô phỏng downstream bằng WireMock

WireMock có thể cấu hình response theo số lần gọi hoặc endpoint. Ví dụ, hai lần đầu trả 503, lần thứ ba trả 200:

~~~java
stubFor(post(urlEqualTo("/payments/authorize"))
        .inScenario("temporary-outage")
        .whenScenarioStateIs(Scenario.STARTED)
        .willReturn(aResponse().withStatus(503))
        .willSetStateTo("second-failure"));

stubFor(post(urlEqualTo("/payments/authorize"))
        .inScenario("temporary-outage")
        .whenScenarioStateIs("second-failure")
        .willReturn(aResponse().withStatus(503))
        .willSetStateTo("recovered"));

stubFor(post(urlEqualTo("/payments/authorize"))
        .inScenario("temporary-outage")
        .whenScenarioStateIs("recovered")
        .willReturn(aResponse().withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("{\"status\":\"AUTHORIZED\"}")));
~~~

Test chạy consumer với retry policy thật, chờ đến khi operation hoàn tất rồi xác minh số lần thử và kết quả. Không dùng sleep cố định dài nếu có thể dùng Awaitility hoặc polling assertion với timeout tổng rõ ràng.

Để mô phỏng network delay, connection reset hoặc packet loss, có thể dùng Toxiproxy hoặc một proxy fault-injection tương đương. WireMock phù hợp với HTTP response behavior; proxy giúp kiểm tra lỗi ở tầng network.

## 10. Test timeout sau khi downstream đã commit

Timeout không chứng minh downstream chưa thực hiện thao tác. Một tình huống quan trọng:

1. Client gửi request với idempotency key.
2. Downstream ghi nhận giao dịch.
3. Downstream chậm trả response.
4. Client timeout.
5. Consumer retry.

Test phải cấu hình stub ghi nhận side effect trước khi trì hoãn response vượt client timeout. Lần retry dùng cùng idempotency key và nhận lại kết quả đã lưu. Assertion là một payment operation logic, không phải một HTTP request duy nhất.

Nếu stub tạo operation mới ở mỗi request, test chưa mô phỏng idempotency của provider. Nếu provider không có cơ chế đó, cần kiểm tra quy trình query/reconciliation khi kết quả lần đầu không rõ.

## 11. Retry, backoff và retry budget

Exponential backoff có jitter giúp tránh nhiều worker retry đồng thời:

\[
delay_n = random(0,\ min(maxDelay,\ baseDelay \times 2^n))
\]

Cần kiểm thử:

- Delay tăng theo attempt nhưng không vượt maxDelay.
- Jitter làm phân tán thời điểm retry.
- Tổng thời gian retry không vượt deadline hoặc event age policy.
- Retry-After được tôn trọng khi dependency trả header hợp lệ.
- Permanent error không bị retry.
- Khi hết retry, event đi đúng DLQ/quarantine.
- Redrive sau khi sửa lỗi vẫn dùng eventId/idempotency key gốc.

Trong queue-triggered Lambda, thường nên để queue visibility timeout và event source mapping điều khiển lần giao lại thay vì sleep trong handler. Sleep giữ invocation và concurrency trong lúc không xử lý được message. Với HTTP request đồng bộ, trả 429/503 kèm Retry-After có thể phù hợp hơn nếu caller có thể retry.

Retry ở SDK, application và queue có thể nhân số lần gọi. Ghi rõ retry budget ở từng tầng và tính tổng số attempt tối đa.

## 12. Test circuit breaker và recovery

Circuit breaker thường có ba trạng thái:

- CLOSED: request được gửi và lỗi được theo dõi.
- OPEN: tạm chặn request tới dependency.
- HALF_OPEN: cho một số request thử để kiểm tra phục hồi.

Test cần xác minh:

1. Sau ngưỡng lỗi, breaker chuyển OPEN.
2. Request mới không gọi dependency khi OPEN.
3. Sau thời gian reset, một số request thử được phép.
4. Khi dependency thành công, breaker trở về CLOSED.
5. Khi thử vẫn lỗi, breaker trở lại OPEN.
6. Không có retry storm trong thời gian breaker OPEN.

Với Lambda scale-out, circuit breaker lưu trong memory chỉ có hiệu lực trên một execution environment. Test local breaker không chứng minh được global circuit breaker. Nếu cần quota/circuit state toàn cục, cần shared mechanism hoặc bảo vệ ở gateway/downstream.

## 13. Kiểm tra queue buffer và DLQ

Trong test tích hợp, mô phỏng downstream ngừng hoạt động trong một khoảng thời gian:

1. Gửi một batch event.
2. Cho downstream trả 503 hoặc timeout.
3. Xác minh message vẫn có thể được giao lại và chưa bị ACK mất.
4. Theo dõi queue age và retry count.
5. Khi vượt ngưỡng, xác minh message chuyển DLQ theo cấu hình.
6. Khôi phục downstream và sửa nguyên nhân.
7. Redrive một nhóm nhỏ message.
8. Xác minh trạng thái nghiệp vụ đúng và không có side effect trùng.

SQS Standard có thể giao message nhiều lần và không đảm bảo thứ tự toàn cục. SQS FIFO hỗ trợ ordering trong MessageGroupId nhưng vẫn cần idempotency và hiểu semantics dedup của queue. Không dùng FIFO như lời hứa exactly-once cho toàn bộ workflow.

Với Kinesis hoặc Kafka, failure có thể ảnh hưởng checkpoint/offset và làm record được đọc lại. Test phải xác minh đúng semantics của source đang dùng, không dùng một giả định retry chung cho mọi trigger.

## 14. Java service boundary để dễ kiểm thử

Business logic nên phụ thuộc interface, còn AWS SDK, queue adapter và HTTP client được inject từ ngoài:

~~~java
public interface PaymentGateway {
    PaymentResult authorize(
            String paymentId,
            long amountMinor,
            String idempotencyKey);
}

public interface EventInbox {
    boolean claim(String consumerName, String eventId);
    void markDeferred(String consumerName, String eventId);
    void markCompleted(String consumerName, String eventId);
}

public interface OrderRepository {
    boolean applyIfVersionMatches(
            String orderId,
            long expectedVersion,
            String newStatus);
}
~~~

Handler điều phối transaction và phân loại kết quả. Adapter AWS chuyển đổi SQS/Kinesis/EventBridge payload sang event domain. Adapter HTTP gọi downstream và ánh xạ status/timeout thành exception hoặc result rõ ràng.

Không để code nghiệp vụ phụ thuộc trực tiếp vào toàn bộ event JSON của một cloud provider. Khi đó unit test có thể dùng event domain đơn giản; integration test riêng xác minh adapter mapping.

## 15. Ví dụ xử lý event có idempotency và version

Pseudocode Java minh họa thứ tự các bước:

~~~java
public ProcessingResult handle(OrderEvent event) {
    return transactionTemplate.execute(status -> {
        if (!inbox.claim("order-consumer", event.eventId())) {
            return ProcessingResult.DUPLICATE;
        }

        Order current = orders.findForUpdate(event.aggregateId());

        if (event.aggregateVersion() <= current.version()) {
            inbox.markCompleted("order-consumer", event.eventId());
            return ProcessingResult.STALE;
        }

        if (event.aggregateVersion() != current.version() + 1) {
            pendingEvents.save(event);
            inbox.markDeferred("order-consumer", event.eventId());
            return ProcessingResult.DEFERRED_GAP;
        }

        boolean updated = orders.applyIfVersionMatches(
                event.aggregateId(),
                current.version(),
                event.newStatus());

        if (!updated) {
            throw new ConcurrentModificationException();
        }

        outbox.append(OrderStatusChanged.from(event));
        inbox.markCompleted("order-consumer", event.eventId());

        return ProcessingResult.APPLIED;
    });
}
~~~

Đây là pseudocode để giải thích luồng, không phải implementation hoàn chỉnh. Khi lưu pending event, inbox chuyển sang DEFERRED chứ chưa phải COMPLETED. Pending dispatcher đọc bản ghi đã lưu, áp dụng business update trong transaction và chỉ chuyển inbox sang COMPLETED sau khi commit. Lần giao lại cùng event trong lúc đang DEFERRED không được tạo pending record thứ hai; handler có thể trả kết quả đã tiếp nhận để ACK vì pending state đã bền vững. Nếu không lưu pending bền vững, không được ACK message gốc.

Nếu gọi downstream API bên ngoài transaction, không giữ database lock trong lúc chờ network. Tạo operation/outbox task trong transaction rồi worker riêng gọi downstream với idempotency key. Sau đó cập nhật trạng thái operation bằng transaction khác.

## 16. Test crash giữa các bước

Tạo fault hook hoặc test double để dừng xử lý tại từng điểm:

| Điểm dừng | Điều cần xác minh |
|---|---|
| Trước inbox insert | Message retry có thể bắt đầu bình thường |
| Sau inbox claim, trước business update | Transaction rollback hoặc claim có lease/timeout để phục hồi |
| Sau business update, trước commit | Không có partial commit |
| Sau commit, trước ACK | Redelivery trở thành duplicate |
| Sau downstream success, trước lưu kết quả | Retry cùng idempotency key không lặp side effect |
| Sau broker publish, trước mark outbox | Event có thể gửi lặp; consumer deduplicate |
| Sau khi lưu pending gap, trước ACK | Redelivery không tạo pending record trùng |

Fault injection phải mô phỏng crash thực tế càng gần càng tốt. Throw exception trong cùng transaction thường kiểm tra rollback; kill process/container hoặc ngắt kết nối giúp kiểm tra crash window và acknowledgement behavior thực tế hơn.

## 17. Test batch và partial failure

Một Lambda có thể nhận nhiều record trong một invocation. Nếu một record lỗi, cần kiểm tra các record thành công không bị xử lý lại không cần thiết.

Với SQS, bật partial batch response khi phù hợp và trả danh sách message ID thất bại. Với Kinesis/DynamoDB Streams, response failure cần theo đúng format và sequence semantics của event source mapping.

Test batch nên có:

- Record A thành công.
- Record B transient failure.
- Record C thành công.
- Handler trả B là failure.
- A và C không tạo side effect trùng khi batch được giao lại.
- B được retry và sau khi phục hồi chỉ áp dụng một lần.

Với FIFO, nếu một record trong message group thất bại, cần dừng xử lý các record sau trong cùng group nếu tiếp tục sẽ phá thứ tự. Không dùng cùng logic batch cho Standard và FIFO mà không xét semantics.

## 18. Công cụ kiểm thử phù hợp

| Công cụ | Mục đích |
|---|---|
| JUnit 5 | Unit và integration test Java |
| Mockito | Mock interface và xác minh lời gọi |
| Testcontainers | Database, Kafka hoặc dependency thật trong container |
| WireMock | HTTP response, delay và failure scenario |
| Toxiproxy | Network latency, reset và connection failure |
| Awaitility | Chờ trạng thái bất đồng bộ với timeout rõ |
| LocalStack | Kiểm thử một số tích hợp AWS trong local |
| Cloud test environment | Xác minh event source mapping, IAM và service semantics thật |

LocalStack hữu ích cho feedback nhanh nhưng không thay thế hoàn toàn môi trường AWS. Những khác biệt về retry, IAM, visibility timeout, stream checkpoint hoặc event source mapping cần được xác minh bằng integration test trên cloud account riêng khi phù hợp.

Không chạy test fault injection trên production queue hoặc database thật. Dùng account/project riêng, dữ liệu giả và resource có thể dọn dẹp.

## 19. Test observability và alert

Một test failure scenario phải kiểm tra cả telemetry vận hành:

- Duplicate event count.
- Stale event count.
- Version gap/pending event count.
- Downstream timeout, 429 và 5xx.
- Retry attempt và retry age.
- Circuit breaker state.
- Queue depth và oldest message age.
- DLQ depth.
- Lambda duration, throttles và concurrency.
- Idempotency hit rate.
- Processing success rate và end-to-end latency.

Log nên chứa eventId, aggregateId, aggregateVersion, correlationId, attempt và failure category. Không log raw payload có PII, credential hoặc payment data. Tránh dùng eventId làm metric dimension có cardinality cao; dùng log/trace để truy vết từng event.

Alert phải phản ánh tình trạng nghiệp vụ. Ví dụ, queue age tăng trong khi Lambda error rate thấp vẫn có thể là dấu hiệu consumer không theo kịp hoặc downstream đang chậm.

## 20. Load test và recovery test

Load test cần mô phỏng phân bố traffic gần production:

- Event bình thường theo chu kỳ.
- Burst khi gateway reconnect.
- Một tenant/device gửi nhiều hơn các thiết bị khác.
- Duplicate ở một tỷ lệ có chủ đích.
- Downstream latency tăng dần.
- Downstream trả 429/503 trong một khoảng thời gian.
- Phục hồi dependency trong khi backlog đang tồn tại.

Đo throughput, p95/p99, queue age, concurrent executions, database write capacity, retry rate và cost trên mỗi event thành công.

Recovery test quan trọng không kém load test. Khi downstream trở lại, hệ thống cần xử lý backlog theo tốc độ an toàn, không dồn toàn bộ message vào dependency trong một đợt. Kiểm tra gradual ramp-up, rate limiter và khả năng pause consumer.

## 21. Bảng kịch bản kiểm thử đầu-cuối

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| DUP-01 | Gửi cùng eventId hai lần | Một business effect, lần sau duplicate |
| DUP-02 | Hai worker xử lý cùng event đồng thời | Unique constraint chỉ cho một claim |
| DUP-03 | Crash sau commit trước ACK | Redelivery không lặp side effect |
| ORD-01 | Version 3 đến trước version 2 | Version 3 được defer hoặc xử lý theo snapshot policy |
| ORD-02 | Version 2 đến sau version 3 | Event cũ không ghi đè state mới |
| ORD-03 | Hai event khác nhau cùng version | Conflict được phát hiện và quarantine |
| DEP-01 | Downstream trả 503 tạm thời | Retry có backoff, cuối cùng thành công |
| DEP-02 | Downstream timeout sau khi commit | Retry cùng idempotency key, một operation logic |
| DEP-03 | Downstream trả 403 | Không retry vô hạn, có alert |
| DEP-04 | Outage kéo dài | Queue giữ backlog, DLQ theo policy |
| REC-01 | Dependency phục hồi | Backlog drain có kiểm soát |
| REC-02 | Redrive DLQ | Event xử lý đúng, không duplicate |
| OBS-01 | Retry và version gap xảy ra | Metrics/logs/alerts phản ánh đúng |

Bảng này là baseline. Dự án cần bổ sung test theo loại trigger, queue, database và downstream thực tế.

## 22. Acceptance criteria

Dự án được xem là đạt khi:

1. Gửi một event hợp lệ tạo đúng business state và outbox event.
2. Gửi lại cùng eventId nhiều lần không lặp side effect.
3. Hai invocation xử lý đồng thời cùng event không tạo hai business update.
4. Event version cũ không ghi đè version mới.
5. Version gap được lưu chờ hoặc xử lý theo snapshot policy đã định nghĩa.
6. Hai event khác nhau cùng version được phát hiện là conflict.
7. Downstream 429/5xx/timeout kích hoạt retry policy đúng.
8. Timeout sau side effect không tạo operation logic thứ hai.
9. Permanent error không bị retry vô hạn.
10. Outage kéo dài không làm mất message; DLQ nhận event theo policy.
11. Sau recovery, backlog được xử lý với concurrency/rate limit an toàn.
12. Partial batch failure không làm lặp side effect của record đã thành công.
13. Metrics và logs đủ để xác định event, attempt và nguyên nhân lỗi.
14. Test chạy độc lập, dùng dữ liệu giả và không tác động production.

Acceptance criteria cần được chuyển thành test assertion và chạy trong CI. Không đánh dấu PASS chỉ vì log có dòng “processed successfully”.

## 23. Những lỗi thường gặp

**Chỉ test handler một lần:** Không phát hiện duplicate hoặc race condition. Test redelivery và concurrency.

**Mock toàn bộ database:** Không kiểm tra unique constraint, transaction và locking. Dùng integration test với database thật.

**Tạo eventId mới cho mỗi lần gửi:** Không còn là duplicate test. Giữ nguyên eventId qua retry.

**Chỉ kiểm tra HTTP response:** Business state có thể đã bị ghi hai lần. Kiểm tra database và external side effect.

**Xem timeout là downstream chưa xử lý:** Có thể downstream đã commit. Retry với idempotency key ổn định.

**Retry mọi lỗi:** 400/403 hoặc schema error không tự hết. Phân loại permanent và transient.

**Dùng sleep trong Lambda để chờ dependency:** Giữ concurrency và tăng chi phí. Để queue/backoff quản lý thời điểm retry.

**Dùng static state để deduplicate:** Không chia sẻ giữa execution environment và có thể mất. Dùng storage bền vững.

**Bỏ qua event version gap:** Event mới có thể áp dụng lên state chưa đủ dữ liệu. Defer hoặc dùng snapshot semantics rõ ràng.

**Không kiểm tra DLQ:** Event có thể bị bỏ quên sau outage. Alert và runbook redrive là bắt buộc.

**Chạy fault injection trên production:** Có thể gây mất dữ liệu thật. Dùng môi trường cô lập và dữ liệu giả.

## 24. Quy trình triển khai dự án

1. Xác định event contract, eventId, aggregateId và aggregateVersion.
2. Viết invariant nghiệp vụ và trạng thái mong đợi.
3. Tách domain handler khỏi adapter AWS.
4. Triển khai inbox/idempotency và conditional update.
5. Thêm pending-event hoặc snapshot policy cho out-of-order.
6. Tạo downstream stub hỗ trợ timeout, 429, 5xx và ambiguous success.
7. Viết unit test duplicate, stale, gap và retry classification.
8. Viết integration test với database và queue/broker.
9. Thêm fault injection cho crash window và network failure.
10. Kiểm tra partial batch, DLQ và redrive.
11. Thêm metrics, logs, traces và alert.
12. Chạy load/recovery test trong môi trường riêng.
13. Đưa test vào CI và lưu test report theo commit.
14. Canary một nhóm consumer trước khi mở rộng production.

## Kết luận

Kiểm thử event-driven system cần xác minh kết quả nghiệp vụ dưới điều kiện duplicate, sai thứ tự và downstream outage. Event ID, inbox/unique constraint và transaction ngăn side effect lặp; aggregate version và pending-event policy bảo vệ thứ tự; timeout, retry có backoff, circuit breaker và queue buffer giúp hệ thống phục hồi khi dependency gián đoạn.

Java Lambda có thể scale và retry độc lập, vì vậy state kiểm soát phải nằm trong storage bền vững và mọi thao tác quan trọng phải idempotent. Bộ test có giá trị khi tạo được failure window thực tế, kiểm tra trạng thái cuối ở database và downstream, đồng thời chứng minh backlog được xử lý an toàn sau recovery. Khi các kịch bản này được tự động hóa trong CI, nhóm phát triển có thể thay đổi consumer và hạ tầng mà vẫn giữ được tính đúng đắn của dữ liệu.

