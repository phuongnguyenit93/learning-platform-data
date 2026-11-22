# gRPC như ingress vào message flow

## 1. gRPC nhận lệnh, message broker tiếp tục xử lý

Trong **SPRING_GRPC**, client gửi RPC theo hợp đồng Protocol Buffers đến service chạy trong ứng dụng Spring. Một cách tổ chức phổ biến là dùng gRPC làm **ingress**: xác thực caller, kiểm tra request, chuyển request thành command và đưa command vào message broker để các consumer xử lý bất đồng bộ.

Luồng tổng quát:

~~~mermaid
flowchart LR
    C["gRPC client"] --> G["Spring gRPC ingress"]
    G --> V["Authenticate / validate"]
    V --> M["Map request to command"]
    M --> B["Message broker"]
    B --> W["Consumer / worker"]
    W --> D["Domain use case"]
    D --> E["Event / result store"]
    E --> Q["Query status / notification"]
    Q --> C
~~~

gRPC xử lý giao tiếp request/response ở biên hệ thống. Broker tách thời điểm tiếp nhận lệnh khỏi thời điểm thực thi nghiệp vụ. Nhờ đó, ingress có thể trả lời nhanh sau khi command được tiếp nhận bền vững, còn worker xử lý công việc dài hoặc cần retry độc lập.

Mô hình này phù hợp với các tác vụ như tạo đơn, xử lý thanh toán, tạo báo cáo, gửi thông báo hoặc chạy workflow nhiều bước. Nó không có nghĩa mọi RPC đều phải đi qua broker: truy vấn cần kết quả ngay và có thời gian xử lý ngắn vẫn có thể gọi use case đồng bộ.

## 2. Phân biệt command ingress với event publishing

Một request từ client thường biểu đạt **command**: yêu cầu hệ thống thực hiện một hành động. **Event** biểu đạt một sự kiện đã xảy ra sau khi hành động được xử lý.

| Message | Ý nghĩa | Thời điểm phát |
|---|---|---|
| `CreateOrderCommand` | Yêu cầu tạo đơn | Khi ingress chấp nhận yêu cầu |
| `OrderCreated` | Đơn hàng đã được tạo thành công | Sau khi use case tạo đơn hoàn tất |
| `PaymentRequested` | Yêu cầu khởi tạo xử lý thanh toán | Khi workflow quyết định cần thanh toán |
| `PaymentCaptured` | Thanh toán đã được ghi nhận | Sau khi hệ thống thanh toán xác nhận |

Không phát `OrderCreated` ngay khi mới nhận `CreateOrderRequest`. Tại thời điểm đó, đơn có thể chưa được tạo, tồn kho chưa được giữ và các kiểm tra nghiệp vụ chưa hoàn tất. Ingress nên publish command như `CreateOrderCommand`; worker chỉ phát `OrderCreated` sau khi giao dịch nghiệp vụ thành công.

Phân biệt này giúp consumer hiểu đúng trách nhiệm và tránh thông báo trạng thái thành công quá sớm cho các hệ thống khác.

## 3. Chọn kiểu phản hồi của gRPC ingress

Ingress thường có ba kiểu phản hồi:

| Kiểu | gRPC response có nghĩa gì? | Khi phù hợp |
|---|---|---|
| Accepted | Broker đã xác nhận tiếp nhận command theo durability policy | Công việc xử lý bất đồng bộ |
| Completed | Use case đã hoàn tất và có kết quả nghiệp vụ | Công việc ngắn, bounded, cần kết quả ngay |
| Request/reply | Ingress gửi command và chờ một reply message tương ứng | Consumer phản hồi nhanh, có timeout rõ ràng |

Với xử lý bất đồng bộ, response nên trả `command_id` hoặc `operation_id`, trạng thái `ACCEPTED` và thông tin để truy vấn tiến độ. Client có thể gọi `GetCommandStatus` hoặc đăng ký một RPC/notification riêng để nhận kết quả.

Không trả `SUCCESS` nếu mới chỉ đưa command vào broker. `ACCEPTED` nghĩa là hệ thống đã nhận trách nhiệm xử lý; nó không khẳng định command sẽ thành công về mặt nghiệp vụ.

Nếu dùng request/reply qua broker, cần correlation ID, reply destination, deadline và quy tắc xử lý response đến muộn. Không giữ một RPC mở vô thời hạn chỉ để đợi worker.

## 4. Ranh giới xác nhận: broker đã nhận khác với consumer đã xử lý

Có nhiều mốc xác nhận khác nhau:

1. Ingress đã nhận request từ client.
2. Request đã qua authentication và validation.
3. Producer đã gửi message.
4. Broker đã xác nhận message theo cấu hình durability.
5. Consumer đã nhận message.
6. Use case đã commit kết quả nghiệp vụ.
7. Event kết quả đã được publish.

Một response `ACCEPTED` nên gắn với mốc 4, nếu hợp đồng cam kết command đã được broker tiếp nhận bền vững. Nó không đồng nghĩa mốc 6 hoặc 7 đã xảy ra.

Với Kafka, độ bền của acknowledgement phụ thuộc cấu hình producer và cluster, chẳng hạn `acks=all`, replication factor và `min.insync.replicas`. Chỉ chờ `KafkaTemplate.send(...)` trả future chưa đủ nếu producer đang dùng cấu hình acknowledgement yếu hơn mức cam kết của hệ thống. Với RabbitMQ hoặc broker khác, dùng publisher confirms và cấu hình durable queue/message tương ứng.

Nếu broker không xác nhận trước deadline, ingress không nên trả `ACCEPTED`. Có thể trả `UNAVAILABLE` hoặc status phù hợp với chính sách API. Tuy nhiên, khi kết nối bị đứt đúng lúc broker đã nhận message nhưng acknowledgement bị mất, ingress có thể không biết chắc message đã được lưu hay chưa. Đây là lý do idempotency cần thiết.

## 5. Hợp đồng message độc lập với protobuf request

Không nên mặc định serialize nguyên protobuf request rồi publish trực tiếp vào topic nội bộ. Request gRPC và message broker có thể có vòng đời, người tiêu thụ và yêu cầu tương thích khác nhau:

- Protobuf RPC contract được thiết kế cho client-server.
- Command message được thiết kế cho consumer và workflow.
- Message có thể cần command ID, tenant, correlation ID, causation ID, schema version và thời điểm tạo.
- Consumer có thể được triển khai bằng ngôn ngữ hoặc schema khác.

Ingress nên map request thành command envelope có schema được quản lý:

~~~json
{
  "messageId": "cmd-8f31",
  "messageType": "orders.create.v1",
  "schemaVersion": 1,
  "aggregateKey": "order-42",
  "correlationId": "req-7c20",
  "causationId": "api-call-91",
  "tenantId": "tenant-12",
  "occurredAt": "2026-11-19T10:15:30Z",
  "payload": {
    "customerId": "customer-9",
    "lines": [
      { "sku": "SKU-100", "quantity": 2 }
    ]
  }
}
~~~

Đây là ví dụ cấu trúc minh họa; payload thực tế có thể dùng Protobuf, Avro, JSON Schema hoặc định dạng đã được tổ chức chuẩn hóa. `messageId` nhận diện message, `correlationId` nối các bước của cùng một request/workflow, còn `causationId` chỉ ra message nào gây ra message hiện tại.

Đặt schema version và quy tắc tương thích rõ ràng. Không tái sử dụng field number protobuf đã xóa hoặc thay đổi ý nghĩa field hiện có. Consumer phải xử lý field mới theo cách tương thích với message cũ.

## 6. Mapping gRPC request thành command

Ví dụ protobuf ingress:

~~~proto
syntax = "proto3";

package orders.v1;

service OrdersIngress {
  rpc SubmitOrder(SubmitOrderRequest) returns (SubmitOrderReply);
  rpc GetCommandStatus(GetCommandStatusRequest)
      returns (GetCommandStatusReply);
}

message SubmitOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
}

message SubmitOrderReply {
  string command_id = 1;
  string state = 2;
}
~~~

Application command có thể độc lập với generated class:

~~~java
public record CreateOrderCommand(
        String commandId,
        String tenantId,
        String customerId,
        java.util.List<Line> lines,
        String idempotencyKey,
        String correlationId) {

    public record Line(String sku, int quantity) {}
}
~~~

Ingress mapper nên kiểm tra cấu trúc cần thiết như customer ID không rỗng, danh sách line có giới hạn và idempotency key hợp lệ. Quy tắc nghiệp vụ như khách hàng có được đặt hàng, SKU có bán hay quantity có nằm trong hạn mức phải được consumer/use case xác minh lại tại thời điểm thực thi.

Không đưa `StreamObserver`, `Metadata`, `ServerCall` hoặc generated protobuf request vào consumer/domain layer. Các kiểu này thuộc ranh giới transport.

## 7. Ví dụ publish command bằng Spring Kafka

Ví dụ sau dùng Spring Kafka 3.x, trong đó `KafkaTemplate.send(...)` trả về `CompletableFuture`. Serializer cho `CreateOrderCommand` cần được cấu hình phù hợp với schema message của hệ thống:

~~~java
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.grpc.server.service.GrpcService;

import java.util.concurrent.CompletableFuture;

@GrpcService
public class OrdersIngressGrpcService
        extends OrdersIngressGrpc.OrdersIngressImplBase {

    private final KafkaTemplate<String, CreateOrderCommand> kafka;
    private final CommandMapper mapper;
    private final CommandIdentity identity;

    public OrdersIngressGrpcService(
            KafkaTemplate<String, CreateOrderCommand> kafka,
            CommandMapper mapper,
            CommandIdentity identity) {
        this.kafka = kafka;
        this.mapper = mapper;
        this.identity = identity;
    }

    @Override
    public void submitOrder(
            SubmitOrderRequest request,
            StreamObserver<SubmitOrderReply> observer) {

        final CreateOrderCommand command;
        try {
            command = mapper.toCommand(
                    request,
                    identity.commandIdFor(request.getIdempotencyKey()),
                    identity.tenantId(),
                    identity.correlationId());
        } catch (IllegalArgumentException ex) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("Invalid order request")
                    .asRuntimeException());
            return;
        }

        Context rpcContext = Context.current();
        try {
            CompletableFuture<?> publish =
                    kafka.send("orders.commands",
                            command.commandId(),
                            command);

            publish.whenComplete((result, failure) ->
                    rpcContext.run(() -> {
                        if (rpcContext.isCancelled()) {
                            return;
                        }
                        if (failure != null) {
                            observer.onError(Status.UNAVAILABLE
                                    .withDescription(
                                            "Command was not confirmed by the message broker")
                                    .asRuntimeException());
                            return;
                        }

                        observer.onNext(SubmitOrderReply.newBuilder()
                                .setCommandId(command.commandId())
                                .setState("ACCEPTED")
                                .build());
                        observer.onCompleted();
                    }));
        } catch (RuntimeException ex) {
            observer.onError(Status.UNAVAILABLE
                    .withDescription("Message broker is unavailable")
                    .asRuntimeException());
        }
    }
}
~~~

Đây là skeleton minh họa cho unary ingress. Cần cấu hình `KafkaTemplate` với serializer, topic, producer acknowledgement, timeout và security phù hợp. `identity` phải lấy tenant/principal từ context đã xác thực; không tin `tenantId` do caller tự khai báo.

Callback chỉ phát đúng một response hoặc một lỗi cho unary RPC. Nếu client hủy RPC trước khi callback chạy, kiểm tra cancellation để không gửi response muộn. Việc client hủy không đảm bảo message đã gửi đến broker sẽ bị thu hồi; khi broker đã chấp nhận command, workflow phải tiếp tục theo chính sách của hệ thống.

## 8. Idempotency xử lý retry ở ingress

Client có thể retry khi response bị mất hoặc nhận `UNAVAILABLE`. Nhưng lần gửi đầu có thể đã được broker xác nhận trong khi acknowledgement không đến được ingress. Nếu lần retry tạo command ID mới, cùng một yêu cầu nghiệp vụ có thể được xử lý hai lần.

Thiết kế idempotency:

1. Client tạo một idempotency key ổn định cho một ý định nghiệp vụ.
2. Mọi lần retry của cùng ý định gửi lại đúng key đó.
3. Ingress xác định tenant/principal và phạm vi của key.
4. Hệ thống ánh xạ cặp `(tenant, idempotencyKey)` thành một `commandId` ổn định.
5. Message consumer cũng deduplicate theo `commandId` hoặc business key trước side effect.

Idempotency store cần xử lý cạnh tranh khi hai request cùng key đến đồng thời. Nếu cùng key nhưng payload khác nhau, trả conflict hoặc lỗi nghiệp vụ rõ ràng; không âm thầm coi hai payload khác nhau là cùng một command.

Idempotent producer của Kafka giúp xử lý duplicate ở tầng producer/broker trong phạm vi cấu hình và session của producer. Nó không thay thế idempotency xuyên suốt từ client, ingress, consumer đến database.

## 9. Dual-write và transactional outbox

Nếu ingress vừa ghi command/receipt vào database vừa publish message, có nguy cơ dual-write:

~~~text
Database commit thành công
        |
        v
Process crash trước khi publish
        |
        v
Receipt tồn tại nhưng worker không nhận command
~~~

Chiều ngược lại cũng có thể xảy ra: broker nhận message nhưng database rollback, khiến worker xử lý một command mà ingress không có receipt tương ứng.

**Transactional outbox** giải quyết vấn đề bằng cách ghi trạng thái command và outbox record trong cùng một transaction database:

~~~mermaid
flowchart TD
    A["gRPC ingress"] --> B["Database transaction"]
    B --> C["Command receipt"]
    B --> D["Outbox record"]
    D --> E["Outbox relay"]
    E --> F["Message broker"]
    F --> G["Consumer"]
    G --> H["Use case + idempotency"]
~~~

Relay đọc outbox và publish message; sau khi broker xác nhận, record được đánh dấu đã gửi hoặc chuyển trạng thái. Relay có thể publish lại sau crash, vì vậy consumer vẫn phải idempotent.

Nếu ingress chỉ publish message và không ghi business state/receipt vào database, có thể không cần outbox. Nhưng khi cần lưu trạng thái operation, deduplication hoặc audit trong database cùng với việc phát message, hãy thiết kế transaction boundary rõ ràng.

Với kiến trúc outbox, API có thể định nghĩa `ACCEPTED` tại thời điểm transaction database commit thành công vì command và outbox record đã được lưu bền vững để relay phát đi. Khi đó, `ACCEPTED` có nghĩa **đã ghi nhận để dispatch**, chưa nhất thiết broker đã xác nhận. Nếu API cần cam kết broker đã nhận, phải theo dõi trạng thái relay và chỉ trả response sau acknowledgement tương ứng. Hãy ghi rõ mốc này trong hợp đồng và cung cấp trạng thái operation nhất quán.

## 10. Delivery semantics, ordering và retry ở consumer

Trong hệ thống message phổ biến, consumer có thể nhận lại message khi xử lý thành công nhưng acknowledgement/offset commit bị mất. Vì vậy, thiết kế mặc định nên chịu được **at-least-once delivery**:

- Consumer kiểm tra `commandId` đã xử lý chưa.
- Ghi kết quả và deduplication marker trong transaction phù hợp.
- Chỉ commit offset/ack sau khi xử lý đạt mốc an toàn.
- Retry lỗi tạm thời với backoff và giới hạn số lần.
- Đưa message lỗi không thể phục hồi vào dead-letter flow để điều tra.

Với Kafka, thứ tự được đảm bảo trong một partition, không phải toàn bộ topic. Chọn message key theo aggregate cần giữ thứ tự, ví dụ `orderId`; các command của cùng đơn sẽ được đưa về cùng partition theo partitioner tương ứng.

Thứ tự trong log partition không tự bảo đảm side effect hoàn tất theo thứ tự nếu consumer tự xử lý song song các record của cùng partition. Cấu hình consumer để giữ thứ tự xử lý cho aggregate đó, hoặc dùng version/sequence và optimistic concurrency ở use case.

Không giả định các command cùng tenant luôn được xử lý tuần tự nếu chúng nằm ở các partition khác nhau. Nếu cần thứ tự nghiệp vụ, xác định aggregate key, partitioning và cách xử lý concurrency ở consumer.

Exactly-once ở một tầng broker không tự tạo exactly-once end-to-end. Side effect trong database hoặc hệ thống ngoài vẫn cần transaction, idempotency hoặc cơ chế phối hợp phù hợp.

## 11. Deadline, cancellation và phản hồi gRPC

Deadline của gRPC giới hạn thời gian client chờ ingress. Nó không tự giới hạn toàn bộ thời gian command nằm trong broker hoặc consumer xử lý:

~~~text
Client deadline: 800 ms
  Authentication + validation: 20 ms
  Publish + broker confirmation: 100 ms
  gRPC response: ACCEPTED

Consumer xử lý:
  có thể mất vài giây hoặc vài phút
  -> cập nhật command status
  -> phát OrderCreated hoặc OrderRejected
~~~

Nếu broker không xác nhận trong deadline, ingress có thể hết thời gian dù message đã được lưu. Client retry phải dùng cùng idempotency key để tránh tạo command trùng.

Nếu client hủy RPC sau khi broker đã nhận message, cancellation chỉ kết thúc tương tác gRPC; nó không có nghĩa command bị hủy. Nếu nghiệp vụ cần hủy command, thiết kế một command riêng như `CancelOrderProcessing` hoặc một operation cancellation có trạng thái và kiểm tra race condition.

Với request/reply, deadline phải bao gồm thời gian publish, chờ consumer, reply routing và trả response. Chỉ dùng mô hình này khi thời gian xử lý có giới hạn và việc giữ RPC mở là hợp lý.

## 12. Status code tại ingress

Ingress nên ánh xạ lỗi theo mốc thất bại:

| Tình huống | gRPC status gợi ý |
|---|---|
| Request sai định dạng hoặc thiếu field bắt buộc | `INVALID_ARGUMENT` |
| Caller chưa xác thực | `UNAUTHENTICATED` |
| Caller không được phép gửi command | `PERMISSION_DENIED` |
| Idempotency key trùng nhưng payload khác | `ALREADY_EXISTS` hoặc status conflict theo API contract |
| Broker không khả dụng hoặc không xác nhận được | `UNAVAILABLE` |
| Hạn mức nhận command bị vượt | `RESOURCE_EXHAUSTED` |
| Deadline ingress hết trước khi xác nhận | `DEADLINE_EXCEEDED` |
| Command đã được tiếp nhận | Response thành công với state `ACCEPTED` |

Không trả `OK/ACCEPTED` trước khi đạt mốc xác nhận mà API cam kết. Đồng thời, đừng trả `INTERNAL` cho lỗi broker tạm thời nếu client có thể retry an toàn.

## 13. Security và context propagation

Ingress là ranh giới tin cậy. Trước khi publish command:

- Xác thực credential qua interceptor hoặc security integration.
- Lấy principal và tenant từ danh tính đã xác minh.
- Kiểm tra quyền gửi loại command và quyền thao tác trên tài nguyên.
- Giới hạn kích thước payload, số line, tần suất request và tenant quota.
- Không publish access token, refresh token hoặc metadata nhạy cảm vào broker.
- Chỉ đưa các claim tối thiểu cần cho consumer vào message; bảo vệ integrity và quyền truy cập topic.

Correlation ID, trace context, tenant ID và actor ID nên được truyền qua message headers/envelope theo quy ước. Nếu dùng W3C Trace Context, truyền `traceparent`/`tracestate` phù hợp; không chỉ dựa vào ThreadLocal vì consumer chạy trên thread/process khác.

Consumer không nên tin một `tenantId` tùy ý trong payload nếu message có thể được gửi từ producer khác. Dùng broker ACL, chữ ký hoặc nguồn phát đáng tin cậy và kiểm tra quyền truy cập dữ liệu ở tầng consumer.

## 14. Backpressure và bảo vệ ingress

Broker có thể hấp thụ burst trong một khoảng thời gian, nhưng không có nghĩa hệ thống có năng lực xử lý vô hạn. Nếu ingress nhận nhanh hơn consumer xử lý, backlog sẽ tăng, thời gian hoàn thành command kéo dài và dữ liệu có thể chiếm hết dung lượng.

Các biện pháp:

- Giới hạn số RPC đồng thời và số message publish đang chờ acknowledgement.
- Đặt deadline cho publish và timeout của producer.
- Giới hạn kích thước message và request rate theo tenant.
- Dùng quota/admission control khi backlog hoặc broker latency vượt ngưỡng.
- Trả `RESOURCE_EXHAUSTED` khi ingress chủ động từ chối vì quá tải.
- Theo dõi consumer lag và thời gian xử lý để điều chỉnh throughput.
- Không giữ một RPC mở chỉ để chờ backlog được xử lý hết.

Nếu callback publish chậm, không tạo thêm thread không giới hạn. Dùng producer client và executor có giới hạn; tránh block event loop của server.

## 15. Kiểm thử gRPC ingress và message flow

Kiểm thử phải xác minh cả phản hồi gRPC lẫn message thực sự được đưa vào flow:

| Kịch bản | Điều cần xác minh |
|---|---|
| Request hợp lệ | Command đúng schema, key và correlation ID được publish |
| Request không hợp lệ | Trả `INVALID_ARGUMENT`, không publish |
| Caller thiếu quyền | Trả `PERMISSION_DENIED`, không tạo command |
| Broker xác nhận | Trả `ACCEPTED` cùng command ID |
| Broker từ chối hoặc timeout | Không trả `ACCEPTED`; status phù hợp |
| Broker đã nhận nhưng ack bị mất | Retry cùng idempotency key không tạo operation trùng |
| Hai request cùng idempotency key | Cùng command ID hoặc conflict nếu payload khác |
| Consumer nhận lại message | Side effect không lặp |
| Consumer xử lý thành công | Status chuyển hoàn tất và event kết quả được phát đúng |
| Consumer lỗi tạm thời | Retry/backoff không làm mất message |
| Consumer lỗi vĩnh viễn | Dead-letter flow có thể điều tra |
| Client hủy sau broker ack | Command vẫn theo chính sách đã chấp nhận; không gửi response muộn |
| Tenant khác nhau | Không rò rỉ dữ liệu và partition/key policy đúng |

Dùng test broker hoặc containerized broker cho integration test. Mock `KafkaTemplate` chỉ xác minh adapter gọi producer; nó không chứng minh durability, publisher acknowledgement, partition ordering hoặc redelivery.

## 16. Metrics và chẩn đoán

Theo dõi riêng ingress và consumer:

- RPC request rate, status code và latency tại ingress.
- Thời gian từ nhận request đến broker acknowledgement.
- Số publish đang pending, timeout và send failure.
- Message rate, broker error và producer retry.
- Consumer lag, backlog age và processing latency.
- Số command accepted, completed, rejected và dead-lettered.
- Tỷ lệ duplicate/idempotency hit.
- Thời gian từ `ACCEPTED` đến kết quả cuối.
- Trace/correlation ID xuyên suốt gRPC → broker → consumer.

Nếu client nhận `ACCEPTED` nhưng không có kết quả, kiểm tra broker acknowledgement, topic/partition, consumer group, lag, dead-letter queue và trạng thái command. Không suy ra consumer đã xử lý chỉ từ việc ingress trả thành công.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Trả `ACCEPTED` ngay khi gọi producer | Message có thể chưa được broker xác nhận | Chờ publisher acknowledgement theo durability policy |
| Phát event hoàn tất trước khi use case chạy | Hệ thống khác tin nghiệp vụ đã thành công quá sớm | Publish command lúc ingress; event sau commit |
| Serialize nguyên gRPC request vào topic | Consumer phụ thuộc transport contract | Map sang message schema riêng |
| Tạo command ID mới mỗi lần retry | Một ý định có thể chạy nhiều lần | Idempotency key ổn định |
| Cho rằng broker exactly-once bảo vệ database side effect | Consumer vẫn có thể thực hiện trùng | Deduplicate và transaction ở consumer |
| Ghi database và publish riêng rẽ | Dual-write làm mất hoặc phát message mồ côi | Transactional outbox |
| Chờ consumer vô hạn trong RPC | Giữ connection/thread và vượt deadline | Trả receipt rồi cung cấp status API |
| Tin tenant ID do client gửi | Có thể truy cập chéo tenant | Dẫn xuất tenant từ principal đã xác thực |
| Không giới hạn backlog hoặc in-flight publish | Bộ nhớ và broker bị quá tải | Admission control, quota và backpressure |

**Ghi nhớ:** Dùng gRPC làm ingress để xác thực, validate và chuyển request thành command; chỉ trả `ACCEPTED` sau mốc ghi nhận bền vững đã công bố: broker acknowledgement hoặc transaction outbox commit. Consumer thực hiện use case và phát event kết quả sau khi nghiệp vụ hoàn tất. Giữ message contract độc lập với protobuf request, dùng idempotency xuyên suốt, transactional outbox khi cần dual-write, truyền correlation/trace context và giới hạn backlog. Deadline/cancellation của RPC không tự hủy command đã được broker tiếp nhận hoặc outbox ghi nhận.
