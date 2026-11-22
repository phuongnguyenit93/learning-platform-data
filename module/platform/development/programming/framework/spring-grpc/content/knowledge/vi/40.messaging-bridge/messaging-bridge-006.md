# Async reply từ message về gRPC

## 1. Ghép request/reply với message processing

Trong **SPRING_GRPC**, client gọi RPC theo hợp đồng Protocol Buffers đến service Spring. Một số use case cần xử lý ở worker qua message broker nhưng vẫn muốn trả kết quả nghiệp vụ trong cùng RPC. Ingress gửi command, tạm giữ RPC trong một khoảng thời gian có giới hạn, nhận reply message từ consumer rồi chuyển reply thành protobuf response.

Luồng này thường được gọi là **asynchronous request/reply**:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as gRPC ingress
    participant B as Message broker
    participant W as Worker / consumer
    C->>G: SubmitOrder(request)
    G->>G: Register pending reply
    G->>B: Publish command + correlation + replyTo
    B->>W: Deliver command
    W->>W: Execute use case
    W->>B: Publish reply(correlationId)
    B->>G: Deliver reply
    G->>G: Complete pending future
    G-->>C: SubmitOrderReply
~~~

RPC và message có vòng đời khác nhau. gRPC là một call có deadline và cancellation; message có thể được retry, redeliver hoặc xử lý sau khi client đã ngừng chờ. Ingress phải quản lý mối liên hệ giữa hai vòng đời đó bằng correlation ID và một pending-reply registry.

## 2. Khi nào nên dùng asynchronous reply?

Mô hình này phù hợp khi consumer cần xử lý bất đồng bộ nhưng thời gian hoàn tất vẫn tương đối ngắn và có giới hạn, ví dụ gọi một worker chuyên biệt, tích hợp service legacy qua broker hoặc thực hiện một bước tính toán rồi trả kết quả ngay trong cùng request.

Không nên giữ RPC mở cho workflow dài, hàng đợi có thể backlog lâu hoặc tác vụ phụ thuộc con người. Với những trường hợp đó, trả `ACCEPTED` cùng `operationId`, sau đó cung cấp RPC truy vấn trạng thái hoặc notification riêng. Giữ một RPC mở lâu sẽ tiêu tốn connection, pending state và tài nguyên server trong suốt thời gian chờ.

## 3. Correlation ID ghép reply với đúng RPC

Ingress tạo một correlation ID riêng cho lần request/reply và đưa nó vào command message. Worker phải copy ID đó sang reply:

~~~text
gRPC call A
  correlationId = corr-A
  command       = cmd-100
  replyTo       = orders.reply.instance-2

Worker reply
  correlationId = corr-A
  commandId     = cmd-100
  result        = ACCEPTED_BY_DOMAIN
~~~

Correlation ID nhận diện cặp request/reply. Nó không nhất thiết là `operationId` hoặc idempotency key:

| ID | Vai trò |
|---|---|
| `correlationId` | Ghép reply với RPC đang chờ |
| `operationId` / `commandId` | Nhận diện ý định nghiệp vụ ổn định qua retry |
| `messageId` | Nhận diện một command hoặc reply message cụ thể |
| `causationId` | Chỉ ra message đã gây ra reply |
| `traceId` | Nối các span của distributed trace |

Nếu client retry cùng ý định, `operationId` và idempotency key nên giữ nguyên. Mỗi RPC attempt có thể dùng correlation ID mới vì mỗi attempt có pending future riêng. Reply đến từ attempt cũ phải được xử lý theo policy, không ghép nhầm vào RPC mới.

## 4. Message contract cần có reply destination

Command cần mang đủ thông tin để worker trả reply:

~~~json
{
  "messageId": "msg-100",
  "messageType": "orders.submit.v1",
  "schemaVersion": 1,
  "commandId": "cmd-100",
  "correlationId": "corr-A",
  "replyTo": "orders.reply.instance-2",
  "tenantId": "tenant-12",
  "deadlineAt": "2026-11-19T10:15:35Z",
  "payload": {
    "customerId": "customer-9"
  }
}
~~~

Reply message nên mang lại correlation ID và tham chiếu command:

~~~json
{
  "messageId": "reply-501",
  "messageType": "orders.submit.reply.v1",
  "correlationId": "corr-A",
  "causationId": "msg-100",
  "commandId": "cmd-100",
  "outcome": "ACCEPTED_BY_DOMAIN",
  "failureCode": ""
}
~~~

`replyTo` phải là destination được hệ thống cho phép, không nhận tùy ý từ caller để tránh biến worker thành một publisher có thể gửi message đến bất kỳ topic/queue nào. `deadlineAt` biểu đạt thời hạn xử lý/chờ theo hợp đồng; không được nhầm nó với việc broker tự hủy message khi hết hạn.

## 5. Pending-reply registry

Ingress cần một registry ánh xạ correlation ID sang future đang chờ. Registry phải:

- Đăng ký future **trước khi publish command**, vì worker có thể phản hồi rất nhanh.
- Từ chối correlation ID trùng đang pending.
- Có timeout và giới hạn số request chờ.
- Xóa entry khi hoàn tất, lỗi, timeout hoặc cancellation.
- Xử lý reply đến trễ hoặc reply không có entry.

Ví dụ đơn giản dùng `ConcurrentHashMap` và `CompletableFuture`:

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;

public final class PendingReplyRegistry {
    private final ConcurrentMap<String, CompletableFuture<OrderReply>> pending =
            new ConcurrentHashMap<>();

    public CompletableFuture<OrderReply> register(
            String correlationId,
            Duration timeout) {

        if (timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("timeout must be positive");
        }

        CompletableFuture<OrderReply> future = new CompletableFuture<>();
        if (pending.putIfAbsent(correlationId, future) != null) {
            throw new IllegalStateException("correlation ID is already pending");
        }

        future.orTimeout(timeout.toMillis(), TimeUnit.MILLISECONDS);
        future.whenComplete((reply, failure) ->
                pending.remove(correlationId, future));
        return future;
    }

    public void complete(String correlationId, OrderReply reply) {
        CompletableFuture<OrderReply> future = pending.get(correlationId);
        if (future == null || !future.complete(reply)) {
            recordUnmatchedReply(correlationId);
        }
    }

    public void fail(String correlationId, Throwable failure) {
        CompletableFuture<OrderReply> future = pending.get(correlationId);
        if (future != null) {
            future.completeExceptionally(failure);
        }
    }

    private void recordUnmatchedReply(String correlationId) {
        // Metrics/log có giới hạn; không dùng correlationId làm metric label.
    }
}
~~~

`orTimeout` có từ Java 9. Đây là skeleton cho một instance; production registry cần giới hạn capacity, metrics và chính sách khi server shutdown. `CompletableFuture.complete(...)` là thao tác cạnh tranh an toàn: chỉ một trong reply, timeout, cancellation hoặc lỗi publish có thể hoàn tất future trước.

Không giữ pending future vô thời hạn. Nếu ingress restart, map trong bộ nhớ mất; client cũng không thể tiếp tục chờ trên RPC cũ. Nếu kết quả cần tồn tại sau restart, hãy lưu operation status bền vững và dùng mô hình operation API thay vì xem pending map là kho trạng thái nghiệp vụ.

## 6. Đăng ký trước, publish sau

Thứ tự hai thao tác là quan trọng:

~~~text
1. Tạo correlationId
2. Tạo pending future trong registry
3. Publish command kèm correlationId và replyTo
4. Worker nhận command và publish reply
5. Reply listener tìm future và complete
6. gRPC adapter chuyển reply thành protobuf response
~~~

Nếu publish trước rồi mới đăng ký future, worker có thể trả lời trước khi registry có entry. Reply khi đó bị xem là unmatched và RPC chờ đến timeout dù kết quả đã có.

Khi producer báo lỗi, hoàn tất future bằng exception để adapter trả status phù hợp. Nếu broker đã nhận message nhưng acknowledgement bị mất, kết quả publish là không chắc chắn; client retry cần dùng idempotency key ổn định để không tạo side effect trùng.

## 7. Reply listener hoàn tất pending future

Reply consumer đọc correlation ID từ envelope hoặc broker header, xác minh loại reply rồi chuyển payload thành application reply:

~~~java
@KafkaListener(
        topics = "orders.reply.instance-2",
        groupId = "orders-reply-instance-2")
public void onReply(ConsumerRecord<String, OrderReplyMessage> record) {
    String correlationId = readCorrelationId(record.headers());
    OrderReply reply = replyMapper.toApplicationReply(record.value());
    pendingReplyRegistry.complete(correlationId, reply);
}
~~~

Đoạn code minh họa listener của một ingress instance có reply topic và consumer group riêng. Khi triển khai, topic/group phải được cấp theo instance identity hoặc được ánh xạ qua một cơ chế partitioning tương đương. Đây là điều kiện kiến trúc quan trọng khi scale nhiều instance; chỉ dùng một topic và một consumer group chung có thể khiến reply đến nhầm instance.

Reply không tìm thấy waiter có thể là reply đến muộn, duplicate hoặc được gửi đến sai instance. Ghi metric và log đã kiểm soát; không tạo một future mới chỉ vì nhận được reply không mong đợi. Nếu cần xử lý reply đến muộn để cập nhật operation status, lưu kết quả theo `operationId` trong một store bền vững.

## 8. Định tuyến reply khi có nhiều ingress instance

Giả sử có ba instance gRPC, mỗi instance giữ pending registry trong bộ nhớ:

~~~text
Ingress A: pending {corr-A}
Ingress B: pending {corr-B}
Ingress C: pending {corr-C}
~~~

Nếu reply topic dùng chung một consumer group, broker có thể giao reply `corr-A` cho listener ở ingress B. B không có future tương ứng và không thể hoàn tất RPC đang chờ ở A.

Các cách định tuyến thường dùng:

| Cách | Cách hoạt động | Lưu ý |
|---|---|---|
| Reply destination theo instance | Mỗi ingress instance có reply topic/queue riêng; command mang `replyTo` | Dễ định tuyến; cần quản lý lifecycle destination |
| Partition theo instance | Reply key/partition được gắn với instance sở hữu pending request | Phải bảo đảm partition được gán đúng instance |
| Fan-out reply cho mọi instance | Mỗi instance nhận bản sao và chỉ instance có correlation mới hoàn tất | Tốn broker/consumer work; cần group/subscription riêng |
| Pending registry phân tán | Mọi instance tra cùng store và dùng notification/stream để đánh thức owner | Phức tạp hơn; cần quản lý lease, expiry và race |

Với Kafka, không mặc định một shared reply topic cùng consumer group sẽ tự đưa reply về instance gửi request. Có thể dùng reply topic riêng theo instance, hoặc một thiết kế partition/consumer assignment rõ ràng. Với RabbitMQ, reply queue riêng hoặc direct reply-to có thể phù hợp tùy topology.

`replyTo` chỉ được ingress tạo từ cấu hình/instance identity đáng tin cậy; worker không được publish đến destination tùy ý do client cung cấp.

## 9. Hoàn tất gRPC RPC theo cách bất đồng bộ

Service implementation không nên block thread chờ `future.get()`. Khi future hoàn tất, callback chuyển kết quả thành protobuf response:

~~~java
@Override
public void submitOrder(
        SubmitOrderRequest request,
        StreamObserver<SubmitOrderReply> observer) {

    Context rpcContext = Context.current();
    String correlationId = ids.newCorrelationId();
    String operationId = idempotency.resolveOperationId(
            callerContext.current().tenantId(),
            request.getIdempotencyKey());

    CompletableFuture<OrderReply> replyFuture =
            pendingReplies.register(correlationId, Duration.ofSeconds(2));

    Context.CancellationListener cancellationListener =
            ignored -> replyFuture.cancel(false);
    rpcContext.addListener(cancellationListener, Runnable::run);

    replyFuture.whenComplete((reply, failure) ->
            rpcContext.run(() -> {
                rpcContext.removeListener(cancellationListener);
                if (rpcContext.isCancelled()) {
                    return;
                }
                if (failure != null) {
                    observer.onError(toGrpcStatus(failure));
                    return;
                }
                observer.onNext(toProto(reply));
                observer.onCompleted();
            }));

    if (rpcContext.isCancelled()) {
        return;
    }

    try {
        publisher.publish(
                mapper.toCommand(request, operationId),
                correlationId,
                replyDestinations.currentInstanceDestination())
            .whenComplete((metadata, failure) -> {
                if (failure != null) {
                    pendingReplies.fail(correlationId, failure);
                }
            });
    } catch (RuntimeException ex) {
        pendingReplies.fail(correlationId, ex);
    }
}
~~~

Đây là skeleton minh họa; cần bổ sung validation, authorization, giới hạn in-flight request, xử lý exception đồng bộ từ `publish`, và mapper status đầy đủ. Điểm quan trọng là đăng ký pending future trước khi publish, không block RPC thread và chỉ gửi một terminal signal.

`Context.CancellationListener` giúp dừng việc chờ khi client hủy hoặc deadline gRPC kết thúc. Nó chỉ hủy future ở ingress; không tự thu hồi command đã được broker nhận và không dừng worker. Nếu nghiệp vụ cần hủy xử lý, phải có command hủy riêng và kiểm tra trạng thái race.

## 10. Timeout và late reply

Có ít nhất hai timeout khác nhau:

- **gRPC deadline:** thời hạn client chờ RPC.
- **Reply timeout:** thời gian ingress giữ pending future để đợi consumer.

Reply timeout nên ngắn hơn hoặc bằng thời gian còn lại của gRPC deadline, sau khi trừ ngân sách cho validation, publish và trả response. Không kéo dài RPC vượt quá deadline của caller.

Khi timeout xảy ra:

1. Future hoàn tất với `TimeoutException`.
2. Registry xóa pending entry.
3. Adapter trả `DEADLINE_EXCEEDED` nếu RPC vẫn còn hoạt động.
4. Worker có thể vẫn tiếp tục xử lý command.
5. Reply đến sau timeout được ghi nhận là late/unmatched; không gửi vào observer đã kết thúc.

Timeout không chứng minh command chưa được xử lý. Nếu client retry, dùng cùng idempotency key/operation ID. Nếu cần biết kết quả đến muộn, lưu reply theo operation ID và cung cấp `GetOperationStatus`.

## 11. Ánh xạ reply và lỗi sang gRPC status

Reply message nên biểu đạt kết quả nghiệp vụ có kiểu, không gửi exception Java tùy ý:

| Kết quả từ worker | gRPC status gợi ý |
|---|---|
| Thành công và có response | `OK` cùng protobuf reply |
| Dữ liệu đầu vào không hợp lệ theo nghiệp vụ | `INVALID_ARGUMENT` hoặc status domain đã quy định |
| Tài nguyên không tồn tại | `NOT_FOUND` |
| Trạng thái hiện tại không cho phép | `FAILED_PRECONDITION` |
| Caller không có quyền | `PERMISSION_DENIED` |
| Worker/broker không phản hồi trong deadline | `DEADLINE_EXCEEDED` |
| Broker không khả dụng trước khi publish được xác nhận | `UNAVAILABLE` |
| Reply không đúng schema hoặc không thể giải mã | `INTERNAL` ở ingress; đồng thời log và xử lý message lỗi |

Không đưa stack trace, tên topic nội bộ, hostname, token hoặc dữ liệu nhạy cảm vào status description. Giữ `failureCode` ổn định trong reply contract và map sang status tại adapter.

## 12. Giới hạn tài nguyên và backpressure

Mỗi pending RPC chiếm một future, map entry, timer và có thể cả gRPC connection. Nếu broker chậm, số pending request có thể tăng nhanh.

Ingress nên:

- Đặt giới hạn số pending request toàn instance và theo tenant.
- Từ chối sớm bằng `RESOURCE_EXHAUSTED` khi đạt giới hạn.
- Dùng timeout hữu hạn và dọn entry trong mọi đường kết thúc.
- Dùng executor có giới hạn cho callback nếu việc mapping/serialization tốn CPU.
- Giới hạn kích thước request/reply và số message in-flight.
- Theo dõi broker latency, reply latency và pending count.
- Không tạo thread riêng cho từng RPC.

Nếu tỷ lệ reply chậm tăng, tăng timeout không phải giải pháp mặc định; việc đó có thể làm pending map phình lớn hơn. Cần kiểm tra consumer lag, downstream latency, partition skew và capacity.

## 13. Khi nào dùng Spring Kafka ReplyingKafkaTemplate?

Spring Kafka cung cấp `ReplyingKafkaTemplate` để hỗ trợ request/reply qua Kafka. Nó kết hợp producer với reply listener container và quản lý correlation giữa request và reply bằng future. Đây là lựa chọn phù hợp khi topology Kafka đáp ứng được yêu cầu reply routing.

Ví dụ khái niệm:

~~~java
ProducerRecord<String, SubmitOrderCommand> record =
        new ProducerRecord<>(
                "orders.commands",
                command.commandId(),
                command);

record.headers().add(new RecordHeader(
        KafkaHeaders.REPLY_TOPIC,
        replyTopic.getBytes(StandardCharsets.UTF_8)));

RequestReplyFuture<String, SubmitOrderCommand, OrderReplyMessage> future =
        replyingKafkaTemplate.sendAndReceive(record);

future.whenComplete((replyRecord, failure) -> {
    if (failure != null) {
        // Map lỗi vào pending gRPC call.
        return;
    }
    // Map replyRecord.value() thành protobuf response.
});
~~~

Đây là ví dụ định hướng API; cấu hình thực tế cần reply listener container, reply topic/partition, serializer/deserializer, timeout và correlation header tương ứng với phiên bản Spring Kafka. Khi chạy nhiều ingress instance, vẫn phải bảo đảm reply listener nhận đúng reply của instance đang giữ RPC; template không tự giải quyết mọi vấn đề định tuyến trong topology tùy ý.

Nếu cần kiểm soát correlation registry, timeout, cancellation hoặc dùng nhiều broker, có thể xây dựng registry riêng. Dù dùng template hay tự triển khai, các quy tắc về timeout, idempotency, late reply và multi-instance routing vẫn còn nguyên.

## 14. Kiểm thử asynchronous reply

Kiểm thử nên bao phủ các race và failure window:

| Kịch bản | Điều cần xác minh |
|---|---|
| Worker reply rất nhanh | Pending entry đã được tạo trước publish; RPC nhận đúng reply |
| Reply đến bình thường | Correlation ID ghép đúng future |
| Hai RPC đồng thời | Không ghép chéo response |
| Correlation ID trùng | Registry từ chối hoặc tạo ID mới theo policy |
| Publish thất bại | Future lỗi và RPC nhận status phù hợp |
| Reply timeout | Entry được dọn; RPC kết thúc với `DEADLINE_EXCEEDED` |
| Reply đến sau timeout | Không gọi observer đã kết thúc; late reply được ghi nhận |
| Client cancel | Pending future được dọn; command đã publish không bị coi là tự hủy |
| Reply duplicate | Chỉ một reply hoàn tất future; duplicate được metrics/log |
| Nhiều ingress instance | Reply được định tuyến đến instance sở hữu pending request |
| Ingress restart | RPC cũ kết thúc; operation status bền vững vẫn tra cứu được nếu đã lưu |
| Worker xử lý lỗi nghiệp vụ | Reply failure code map đúng sang gRPC status |
| Backpressure | Vượt pending limit thì từ chối sớm, không tăng bộ nhớ vô hạn |

Unit test registry cần kiểm tra cạnh tranh giữa `complete`, timeout, cancel và `fail`. Integration test với broker thật hoặc containerized broker mới xác minh reply topic, header, consumer group, routing và redelivery. Mock listener không thể chứng minh reply về đúng instance trong môi trường nhiều replica.

## 15. Metrics và chẩn đoán

Theo dõi:

- Số RPC đang chờ reply và số pending tối đa.
- Thời gian từ publish đến reply theo message type.
- Tỷ lệ reply timeout, publish failure, late reply và unmatched correlation.
- Số duplicate reply và correlation collision.
- Broker lag, consumer processing latency và reply publish latency.
- Số RPC bị cancel hoặc hết gRPC deadline.
- Số request bị từ chối vì pending capacity.
- Tỷ lệ worker hoàn tất trước reply deadline.

Dùng correlation ID/operation ID trong log và trace, không dùng chúng làm metric label có cardinality cao. Khi điều tra, nối log ingress, command publish, worker xử lý và reply listener bằng correlation ID; dùng trace context để xem các span kỹ thuật nếu sampling có giữ trace.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Publish trước khi đăng ký future | Reply nhanh đến trước và bị mất | Register pending trước publish |
| Block thread bằng `future.get()` | Giảm throughput, cạn worker/event loop | Dùng callback và future |
| Dùng chung reply topic/consumer group không có routing | Reply đến nhầm ingress instance | Reply destination/partition theo owner |
| Không timeout pending entry | Rò rỉ memory và giữ RPC vô hạn | Timeout hữu hạn và cleanup |
| Coi timeout là command chưa chạy | Retry có thể tạo side effect trùng | Dùng idempotency key và operation status |
| Coi gRPC cancellation là hủy broker message | Worker vẫn chạy nhưng caller tưởng đã dừng | Tách RPC cancellation khỏi business cancellation |
| Dùng correlation ID làm operation ID | Retry và nhiều attempt khó quản lý | Phân biệt correlation, operation và message ID |
| Không xử lý late/duplicate reply | Observer lỗi hoặc log khó điều tra | Complete atomically, đo unmatched/late reply |
| Chờ workflow dài trong cùng RPC | Pending state và connection tồn tại quá lâu | Chuyển sang `ACCEPTED` + operation status |

**Ghi nhớ:** Async reply từ message về gRPC dùng correlation ID để ghép reply message với RPC đang chờ. Đăng ký pending future trước khi publish, hoàn tất bằng reply listener và trả protobuf response qua callback không block. Đặt timeout, cleanup, cancellation và giới hạn pending capacity; định tuyến reply về đúng ingress instance khi scale nhiều replica. Timeout/cancel không tự hủy command đã publish, vì vậy cần idempotency và operation status cho kết quả đến muộn hoặc workflow dài.
