# Retry giữa gRPC và broker

## 1. Một thao tác có nhiều tầng retry

Trong **SPRING_GRPC**, client gọi RPC theo hợp đồng Protocol Buffers đến service Spring. Ingress có thể lưu command vào database/outbox, publish qua message broker, rồi để consumer xử lý nghiệp vụ. Một thao tác như vậy có nhiều nơi có thể retry:

- **gRPC client retry:** gọi lại RPC khi nhận status có thể phục hồi hoặc kết quả lần gọi không rõ ràng.
- **Producer retry:** Kafka/RabbitMQ client thử gửi lại message khi broker hoặc kết nối tạm lỗi.
- **Outbox relay retry:** đọc lại record chưa được broker xác nhận và publish tiếp.
- **Consumer retry/redelivery:** xử lý lại message khi consumer gặp lỗi tạm thời hoặc acknowledgement/offset commit không hoàn tất.
- **Downstream RPC retry:** consumer gọi service khác và có thể retry lời gọi đó.

Các tầng này có mục tiêu và failure boundary khác nhau. Không nên bật retry vô hạn ở mọi tầng rồi kỳ vọng hệ thống tự phục hồi. Retry phải có giới hạn, backoff, phân loại lỗi và cơ chế idempotency để một ý định nghiệp vụ không tạo side effect nhiều lần.

~~~mermaid
flowchart TD
    C["gRPC client"] -->|bounded RPC retry| G["Spring gRPC ingress"]
    G --> O["Database + outbox"]
    O -->|relay retry| P["Broker producer"]
    P --> B["Message broker"]
    B -->|redelivery / consumer retry| W["Consumer"]
    W -->|bounded downstream retry| D["Downstream gRPC"]
    W --> X["Business side effect"]
~~~

## 2. Phân loại lỗi trước khi retry

Retry chỉ có ích khi lỗi có khả năng tự hết sau một khoảng thời gian. Lỗi request hoặc lỗi nghiệp vụ cố định sẽ không được sửa bằng cách gửi lại cùng một thao tác.

| Lỗi | Có nên retry? | Cách xử lý |
|---|---|---|
| Mất kết nối tạm thời, broker unavailable | Thường có | Backoff, giới hạn attempt và giữ nguyên message/operation ID |
| Timeout, không rõ server/broker đã nhận hay chưa | Có điều kiện | Retry cùng idempotency key; truy vấn operation nếu cần |
| Database deadlock hoặc lỗi tạm thời | Thường có | Retry transaction ở boundary an toàn |
| Quá tải hoặc quota | Có điều kiện | Tôn trọng backoff/quota; tránh retry dồn dập |
| `INVALID_ARGUMENT` | Không | Sửa request |
| `PERMISSION_DENIED` | Không | Sửa quyền hoặc policy |
| `UNAUTHENTICATED` | Không tự động | Làm mới credential theo flow xác thực rồi quyết định gọi lại |
| `NOT_FOUND` hoặc `FAILED_PRECONDITION` | Thường không | Xử lý trạng thái nghiệp vụ |
| Message sai schema/không deserialize được | Không retry vô hạn | Quarantine hoặc dead-letter để điều tra |
| Consumer lỗi nghiệp vụ không thể phục hồi | Không | Ghi failure state và xử lý theo domain policy |

`UNAVAILABLE` thường biểu thị lỗi tạm thời ở gRPC. `DEADLINE_EXCEEDED` là kết quả không chắc chắn: server có thể đã commit trước khi response bị mất. `RESOURCE_EXHAUSTED` chỉ nên retry khi hệ thống xác định đó là giới hạn tạm thời và có thời gian chờ phù hợp. Không dùng một danh sách status retry chung cho mọi RPC.

## 3. gRPC client retry có giới hạn

gRPC Java hỗ trợ retry policy qua service config. Ví dụ cấu hình retry cho method `SubmitOrder` khi nhận `UNAVAILABLE`:

~~~java
Map<String, Object> retryPolicy = Map.of(
        "maxAttempts", 4.0,
        "initialBackoff", "0.1s",
        "maxBackoff", "1s",
        "backoffMultiplier", 2.0,
        "retryableStatusCodes", List.of("UNAVAILABLE"));

Map<String, Object> methodConfig = Map.of(
        "name", List.of(Map.of(
                "service", "orders.v1.OrdersIngress",
                "method", "SubmitOrder")),
        "retryPolicy", retryPolicy);

ManagedChannel channel = ManagedChannelBuilder
        .forTarget(target)
        .defaultServiceConfig(Map.of(
                "methodConfig", List.of(methodConfig)))
        .enableRetry()
        .build();
~~~

`maxAttempts` bao gồm lần gọi đầu tiên. Ví dụ này cho phép tối đa bốn lần thử, với backoff tăng dần và giới hạn một giây. Cần kiểm tra service config được áp dụng cho channel/resolver của môi trường triển khai; không giả định mọi channel đều bật retry tự động.

Deadline phải được đặt một lần cho toàn bộ RPC:

~~~java
SubmitOrderReply reply = blockingStub
        .withDeadlineAfter(900, TimeUnit.MILLISECONDS)
        .submitOrder(request);
~~~

Không tạo deadline 900 ms mới bên trong vòng lặp cho từng attempt. Tổng thời gian retry, backoff và network phải nằm trong deadline của caller. Nếu ngân sách hết, client nhận `DEADLINE_EXCEEDED` dù server có thể đã xử lý request.

## 4. Retry RPC cần idempotency ở tầng nghiệp vụ

Giả sử ingress commit order và outbox thành công, nhưng response gRPC bị mất. Client thấy timeout và retry. Nếu lần gọi mới tạo `commandId` hoặc `eventId` mới, một ý định đặt hàng có thể được thực hiện hai lần.

Hợp đồng request nên có idempotency key:

~~~proto
message SubmitOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
}

message SubmitOrderReply {
  string operation_id = 1;
  OperationState state = 2;
}
~~~

Ingress lưu mapping có unique constraint theo `(tenantId, idempotencyKey)`:

1. Lần đầu nhận key, tạo `operationId`/`commandId` ổn định và lưu fingerprint payload.
2. Retry cùng key, cùng payload trả lại operation đã tồn tại và trạng thái hiện tại.
3. Cùng key nhưng payload khác trả conflict theo API contract.
4. Command/outbox record dùng lại ID đã tạo; không phát một ý định nghiệp vụ mới.

Việc kiểm tra và tạo mapping phải nguyên tử để hai request đồng thời cùng key không tạo hai operation. Correlation ID có thể mới cho mỗi RPC attempt; operation ID và idempotency key giữ ổn định qua retry của cùng ý định.

## 5. Phân biệt retry RPC với retry command

Khi RPC trả `ACCEPTED`, ingress đã ghi nhận command bền vững theo hợp đồng. Nếu client retry chỉ vì muốn biết kết quả, ingress nên trả cùng `operationId` và trạng thái hiện tại. Không publish command mới chỉ vì client gọi lại RPC.

Nếu client nhận `DEADLINE_EXCEEDED` hoặc mất kết nối trước khi biết kết quả, trạng thái có thể không chắc chắn. Client nên gọi lại với cùng idempotency key hoặc truy vấn operation theo key/ID. Không tạo key mới để “thử lại cho chắc”.

Với request/reply giữ RPC mở đến khi worker trả kết quả, mỗi RPC attempt có thể có correlation ID riêng và pending future riêng. Tuy nhiên, mọi attempt vẫn phải tham chiếu cùng operation nếu đó là cùng một ý định. Reply đến muộn của attempt cũ không được ghép nhầm vào future của attempt mới.

## 6. Producer retry và outbox relay retry

Producer retry xử lý lỗi gửi message trong thời gian producer còn hoạt động. Outbox relay retry xử lý trường hợp ứng dụng cần tiếp tục publish sau khi process restart hoặc sau khi producer đã hết retry nội bộ.

Với Kafka, có thể cấu hình producer idempotence và acknowledgement mạnh:

~~~java
props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.RETRIES_CONFIG, Integer.MAX_VALUE);
props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120_000);
~~~

Đây là cấu hình định hướng; cần phối hợp `delivery.timeout.ms`, request timeout, broker replication và giới hạn thời gian của relay. Producer idempotence giảm duplicate do retry trong phạm vi producer session/protocol. Nó không thay thế event ID ổn định hoặc consumer deduplication sau khi relay restart và publish lại một outbox record.

Relay chỉ đánh dấu outbox record đã publish sau khi nhận acknowledgement. Nếu gửi thất bại hoặc kết quả không chắc chắn, giữ record để retry với cùng `eventId` và payload. Nếu broker đã nhận nhưng acknowledgement bị mất, relay có thể publish lại; consumer phải chịu được duplicate.

Không giữ transaction database mở trong lúc chờ network broker. Claim/lease record trong thời gian ngắn, publish bên ngoài transaction, rồi cập nhật trạng thái sau acknowledgement bằng điều kiện phù hợp để nhiều relay instance không giành cùng record tùy tiện.

## 7. Consumer retry và redelivery

Consumer có thể lỗi sau khi nhận message. Chính sách retry phụ thuộc loại lỗi:

- **Transient:** database deadlock, downstream unavailable, timeout tạm thời. Retry với backoff.
- **Permanent:** payload sai, schema version không hỗ trợ, dữ liệu không hợp lệ theo contract. Không retry vô hạn; đưa vào dead-letter/quarantine.
- **Business rejection:** command không thể thực hiện do trạng thái nghiệp vụ. Ghi kết quả `REJECTED` hoặc failure event; không coi đó là lỗi hạ tầng cần retry.

Ví dụ cấu hình Spring Kafka `DefaultErrorHandler` với ba lần retry sau lần xử lý đầu và dead-letter recoverer:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L));

    handler.addNotRetryableExceptions(
            InvalidOrderCommand.class,
            UnsupportedSchemaVersionException.class);

    return handler;
}
~~~

Ví dụ cần một `DeadLetterPublishingRecoverer` đã được cấu hình với producer phù hợp. `FixedBackOff` ở đây minh họa chính sách đơn giản; hệ thống có thể dùng exponential backoff, retry topic hoặc error handler riêng. Xác minh số lần retry và semantics ack/offset theo phiên bản Spring Kafka đang dùng.

Khi consumer xử lý thành công nhưng offset commit/ack thất bại, message có thể được giao lại. Vì vậy, retry policy không loại bỏ yêu cầu idempotency.

## 8. Idempotent consumer bảo vệ side effect

Consumer nên deduplicate bằng `eventId`/`messageId`, không dùng correlation ID vì nhiều message hợp lệ trong cùng workflow có chung correlation ID.

Với side effect trong cùng database, lưu inbox marker và cập nhật domain state trong cùng transaction:

~~~java
@Transactional
public void handle(OrderCreatedEvent event) {
    if (inboxRepository.existsByMessageId(event.messageId())) {
        return;
    }

    inboxRepository.insert(event.messageId());
    orderProjection.apply(event);
}
~~~

Database cần unique constraint trên `messageId`; việc kiểm tra rồi insert phải được bảo vệ trước race giữa hai consumer. Nếu transaction rollback, cả inbox marker và projection update cùng rollback. Nếu commit thành công nhưng broker offset chưa commit, redelivery sẽ gặp marker và không lặp side effect.

Nếu consumer gọi hệ thống ngoài database, truyền idempotency key ổn định (thường từ operation/event ID) sang API đó hoặc dùng một workflow/outbox riêng. Không thể bảo đảm exactly-once end-to-end chỉ bằng Kafka producer idempotence hoặc một inbox table ở service khác.

## 9. Exponential backoff, jitter và retry budget

Retry dồn dập có thể làm dịch vụ đang lỗi quá tải nặng hơn. Backoff tăng dần tạo khoảng nghỉ giữa các attempt:

\[
delay_n = \min(maxDelay,\ initialDelay \times multiplier^n)
\]

Thêm **jitter** để các client không retry cùng thời điểm:

\[
actualDelay_n \sim U(0,\ delay_n)
\]

Ví dụ policy: initial delay 100 ms, multiplier 2, cap 2 giây, tối đa ba lần retry. Đây chỉ là điểm khởi đầu; chọn giá trị theo latency mục tiêu và loại lỗi.

Retry budget cần giới hạn:

- Số attempt tối đa ở từng boundary.
- Tổng thời gian retry không vượt deadline hoặc command expiry.
- Số request/message đang chờ và concurrency.
- Tổng tỷ lệ retry trên traffic bình thường.
- Số lần retry trước khi chuyển dead-letter hoặc báo lỗi vận hành.

Không retry lỗi validation, schema hoặc authorization. Không đặt backoff quá dài trong thread consumer đang giữ partition nếu thiết kế yêu cầu throughput cao; có thể dùng retry topic hoặc cơ chế pause phù hợp.

## 10. Không nhân retry ở mọi tầng

Giả sử client retry gRPC bốn lần, relay retry nhiều lần, consumer retry bốn lần và downstream client cũng retry bốn lần. Một lỗi downstream có thể tạo lượng công việc lớn hơn nhiều so với một request ban đầu.

Hãy chỉ định boundary sở hữu từng loại retry:

| Boundary | Trách nhiệm retry |
|---|---|
| gRPC client | Lỗi transport tạm thời trước khi nhận kết quả; luôn giữ idempotency key |
| Ingress/outbox | Lưu command một lần; relay retry publish |
| Producer client | Retry network/broker error trong delivery timeout |
| Consumer | Retry lỗi xử lý tạm thời; permanent error chuyển DLQ |
| Downstream client | Retry có giới hạn theo remaining deadline và idempotency |

Không để client retry tạo operation mới, ingress retry tạo command mới, hoặc relay tạo event ID mới. Một operation có thể có nhiều attempt, nhưng phải giữ định danh và trạng thái xuyên suốt.

## 11. Retry, ordering và partition

Retry có thể ảnh hưởng thứ tự message:

- Retry tại partition hiện tại có thể giữ thứ tự nhưng làm chậm các record phía sau.
- Retry topic cho phép partition chính tiếp tục nhưng message lỗi có thể quay lại sau các message mới hơn.
- Dead-letter tách message lỗi khỏi luồng chính nhưng cần quy trình replay có kiểm soát.

Nếu nghiệp vụ cần thứ tự theo aggregate, dùng partition key ổn định và kiểm soát consumer concurrency. Có thể gắn `aggregateVersion` để phát hiện event đến thiếu hoặc sai thứ tự. Khi replay từ DLQ, không mặc định phát lại message cũ ngay vào luồng đang xử lý mới; cần kiểm tra version và trạng thái hiện tại.

## 12. Deadline và command expiry giới hạn retry

Với RPC đồng bộ hoặc request/reply, tất cả attempt và backoff phải nằm trong deadline của client. Mỗi lần retry không được cấp lại toàn bộ timeout.

Với command bất đồng bộ đã được nhận, RPC deadline chỉ giới hạn thời gian ingress phản hồi. Consumer dùng `commandExpiresAt` hoặc processing budget riêng nếu nghiệp vụ có thời hạn. Retry không được làm mới command expiry:

~~~text
Command created: 10:00
Command expires: 10:05
Attempt 1: 10:01 -> database unavailable
Attempt 2: 10:03 -> downstream timeout
Attempt 3: 10:04:50 -> còn 10 giây
After 10:05 -> mark expired; stop retry
~~~

Nếu expiry đã qua, không tiếp tục retry side effect. Ghi operation state `EXPIRED` hoặc dead-letter reason phù hợp. Gia hạn chỉ được thực hiện như một quyết định nghiệp vụ mới có authorization và audit.

## 13. Circuit breaker và backpressure bổ sung cho retry

Retry xử lý lỗi ngắn hạn; circuit breaker ngăn gọi liên tục một dependency đang lỗi. Khi circuit mở, ingress/consumer có thể từ chối sớm, để outbox hoặc broker giữ công việc và thử lại sau theo policy.

Kết hợp:

- **Circuit breaker:** ngăn request mới đến dependency đang lỗi.
- **Bulkhead/concurrency limit:** giới hạn số tác vụ đồng thời.
- **Rate limit/quota:** kiểm soát tải theo tenant hoặc caller.
- **Backpressure:** giảm nhận message khi consumer không theo kịp.
- **Retry budget:** giới hạn số lần và tổng thời gian thử lại.

Không retry ngay bên trong circuit breaker đang mở. Không giữ hàng đợi in-memory vô hạn; công việc cần tồn tại qua restart phải được lưu bền vững ở broker/outbox.

## 14. Kiểm thử retry xuyên gRPC và broker

Kiểm thử cần mô phỏng failure ở từng boundary:

| Kịch bản | Điều cần xác minh |
|---|---|
| gRPC trả `UNAVAILABLE` trước khi xử lý | Client retry trong giới hạn và cùng idempotency key |
| Server commit nhưng response bị mất | Retry trả lại cùng operation, không tạo order mới |
| gRPC deadline hết giữa các attempt | Tổng thời gian không vượt deadline; kết quả được tra cứu bằng operation ID |
| Producer gặp lỗi tạm thời | Producer/relay retry cùng event ID |
| Broker nhận message nhưng ack bị mất | Relay có thể gửi duplicate; consumer không lặp side effect |
| Relay restart | Outbox pending tiếp tục được publish |
| Consumer gặp lỗi transient | Retry/backoff đúng số lần |
| Consumer gặp lỗi permanent | Message chuyển DLQ, không retry vô hạn |
| Consumer commit DB nhưng offset commit lỗi | Redelivery không lặp side effect |
| Retry topic làm message đến lệch thứ tự | Version/order policy phát hiện hoặc xử lý đúng |
| Downstream lỗi kéo dài | Circuit breaker và retry budget giới hạn tải |
| Command expiry trong backoff | Retry dừng và operation chuyển `EXPIRED` |

Dùng database và broker thật hoặc containerized broker cho integration test. Mock producer chỉ xác minh code gọi API; nó không chứng minh acknowledgement, redelivery, offset commit hay dead-letter behavior.

## 15. Metrics và chẩn đoán

Theo dõi riêng theo boundary:

- gRPC retry attempt, status, deadline exceeded và idempotency hit.
- Producer send retry, acknowledgement latency, delivery timeout.
- Outbox pending count, tuổi record cũ nhất, relay retry và publish failure.
- Consumer retry count, redelivery, processing latency và DLQ rate.
- Duplicate message bị inbox/idempotency loại bỏ.
- Downstream circuit state, rejected call và retry budget exhaustion.
- Queue lag, partition skew và command expiry.

Dùng operation ID, correlation ID và message ID trong log/trace; không dùng ID có cardinality cao làm metric label. Khi điều tra, tìm một operation và đối chiếu các attempt tại từng boundary để biết retry nào đã xảy ra và mốc nào đã commit.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Retry mọi gRPC status | Lặp request không thể thành công | Allowlist lỗi tạm thời |
| Tạo idempotency key mới mỗi lần retry | Tạo nhiều operation | Giữ key ổn định theo ý định |
| Cấp deadline mới cho mỗi attempt | Tổng thời gian vượt ngân sách | Một deadline cho toàn RPC |
| Trả `ACCEPTED` trước khi lưu bền vững | Command có thể mất sau response | Commit receipt/outbox trước |
| Đánh dấu outbox published trước broker ack | Mất event | Chỉ mark sau acknowledgement |
| Tin producer idempotence bảo đảm exactly-once toàn hệ thống | Consumer vẫn có thể lặp side effect | Inbox/deduplication ở consumer |
| Retry message lỗi schema vô hạn | Poison message chặn luồng | Non-retryable classification và DLQ |
| Không giới hạn retry ở từng tầng | Retry storm và khuếch đại tải | Retry budget, backoff, jitter, circuit breaker |
| Replay DLQ không kiểm tra thứ tự | Aggregate state bị đảo | Version check và replay policy |

**Ghi nhớ:** Retry giữa gRPC và broker phải được thiết kế theo từng boundary: client retry RPC, producer/outbox retry publish và consumer retry xử lý. Phân loại transient với permanent error, giới hạn attempt và tổng thời gian bằng deadline/command expiry, dùng exponential backoff có jitter. Giữ idempotency key, operation ID và event ID ổn định qua retry; dùng outbox để không mất ý định publish và inbox/idempotent consumer để chống duplicate. Retry không thay thế backpressure, circuit breaker hoặc dead-letter policy.
