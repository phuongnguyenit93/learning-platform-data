# Trả response trước hoặc sau khi publish

## 1. Thời điểm response quyết định ý nghĩa cam kết của RPC

Trong **SPRING_GRPC**, client gọi RPC theo hợp đồng Protocol Buffers đến service Spring. RPC có thể thực hiện một use case rồi phát event hoặc command sang message broker để các consumer tiếp tục xử lý. Khi đó, thời điểm server trả response ảnh hưởng trực tiếp đến điều client được phép kết luận.

Có ba mốc cần phân biệt:

- **Đã ghi nhận bền vững:** command hoặc outbox record đã commit vào database.
- **Đã publish được broker xác nhận:** broker đã nhận message theo durability policy đã cấu hình.
- **Đã xử lý nghiệp vụ:** consumer đã thực hiện use case và commit kết quả.

Response trước khi publish có thể có nghĩa hệ thống đã ghi nhận command để dispatch. Response sau publish có thể có nghĩa broker đã xác nhận message. Cả hai đều không tự động có nghĩa consumer đã xử lý xong.

Hãy thiết kế response theo mốc mà API thực sự cam kết. Ví dụ:

| Response state | Ý nghĩa |
|---|---|
| `ACCEPTED` | Hệ thống đã nhận trách nhiệm xử lý theo durability contract được công bố |
| `PUBLISHED` | Broker đã xác nhận nhận message theo cấu hình producer/cluster |
| `COMPLETED` | Use case nghiệp vụ đã hoàn tất và kết quả đã commit |
| `REJECTED` | Request bị từ chối trước khi được nhận xử lý |

Không dùng một trạng thái `SUCCESS` chung cho mọi mốc. Client cần biết mình có thể hiển thị “đã tiếp nhận”, “đã gửi vào broker” hay “đã hoàn tất”.

## 2. Response trước khi publish: chỉ an toàn khi ý định đã được lưu bền vững

Nếu server trả response trước khi message được broker nhận, client có thể nhận kết quả nhanh hơn và RPC không phải chờ broker. Nhưng cần phân biệt hai cách:

1. **Trả response ngay rồi mới tìm cách publish:** không an toàn với command quan trọng. Process có thể crash sau response nhưng trước khi gửi message; hệ thống đã hứa nhận việc nhưng không còn dữ liệu để thực hiện.
2. **Commit command receipt và outbox trước, trả response, rồi relay publish:** an toàn hơn. Database đã lưu bền vững ý định dispatch trong cùng transaction; broker có thể nhận message sau đó.

Luồng outbox:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as Spring gRPC adapter
    participant U as Use case
    participant DB as Database
    participant R as Outbox relay
    participant B as Broker
    C->>G: SubmitCommand
    G->>U: execute(command)
    U->>DB: Save receipt + outbox
    DB-->>U: Commit
    U-->>G: Operation accepted
    G-->>C: OK / ACCEPTED + operationId
    R->>DB: Read pending outbox
    R->>B: Publish message
    B-->>R: Acknowledgement
    R->>DB: Mark published
~~~

Response được trả sau khi transaction commit, nhưng trước khi relay publish. Vì vậy, `ACCEPTED` phải được định nghĩa là “đã ghi nhận bền vững để dispatch”. Không được mô tả nó là “broker đã nhận” hoặc “consumer đã xử lý”.

Nếu database commit thất bại, outbox record cũng không tồn tại và ingress không được trả `ACCEPTED`. Nếu process crash sau commit, relay có thể tiếp tục từ outbox khi ứng dụng phục hồi.

## 3. Response trước publish mà không có outbox là fire-and-forget

Một cách triển khai tưởng như đơn giản:

~~~java
CompletableFuture<SendResult<String, CreateOrderCommand>> send =
        kafkaTemplate.send("orders.commands", command.commandId(), command);

observer.onNext(SubmitOrderReply.newBuilder()
        .setCommandId(command.commandId())
        .setState("ACCEPTED")
        .build());
observer.onCompleted();
~~~

Đoạn code trả response ngay khi `send(...)` trả future, không chờ broker acknowledgement. Future có thể thất bại sau khi RPC đã kết thúc. Nếu không có durable outbox hoặc một hàng đợi bền vững khác, command có thể bị mất mà client vẫn đã nhận `ACCEPTED`.

Fire-and-forget chỉ phù hợp khi mất message được chấp nhận theo yêu cầu sản phẩm, hoặc khi một cơ chế bền vững khác đã nhận trách nhiệm lưu và retry. Không dùng việc “đã gọi hàm send” làm bằng chứng message đã được tiếp nhận.

## 4. Response sau khi publish: chờ broker acknowledgement

Nếu API cần cam kết broker đã nhận message, ingress có thể chờ producer future hoàn tất rồi mới trả response:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant G as gRPC ingress
    participant B as Message broker
    C->>G: SubmitCommand
    G->>B: Publish message
    B-->>G: Broker acknowledgement
    G-->>C: OK / PUBLISHED
~~~

Trong Spring Kafka 3.x, `KafkaTemplate.send(...)` trả về `CompletableFuture<SendResult<K,V>>`. Adapter có thể đăng ký callback thay vì block thread xử lý RPC:

~~~java
@Override
public void submitOrder(
        SubmitOrderRequest request,
        StreamObserver<SubmitOrderReply> observer) {

    CreateOrderCommand command = mapper.toCommand(request);
    Context rpcContext = Context.current();

    try {
        kafkaTemplate.send(
                "orders.commands",
                command.commandId(),
                command)
            .whenComplete((result, failure) ->
                rpcContext.run(() -> {
                    if (rpcContext.isCancelled()) {
                        return;
                    }
                    if (failure != null) {
                        observer.onError(Status.UNAVAILABLE
                                .withDescription("Broker publish was not confirmed")
                                .asRuntimeException());
                        return;
                    }

                    observer.onNext(SubmitOrderReply.newBuilder()
                            .setCommandId(command.commandId())
                            .setState("PUBLISHED")
                            .build());
                    observer.onCompleted();
                }));
    } catch (RuntimeException ex) {
        observer.onError(Status.UNAVAILABLE
                .withDescription("Unable to submit message")
                .asRuntimeException());
    }
}
~~~

Đây là skeleton minh họa. Cần cấu hình serializer, topic, producer timeout, acknowledgement, security và callback executor phù hợp. Callback phải phát đúng một terminal signal; không gọi `onNext` hoặc `onCompleted` sau `onError`.

Không block Netty/gRPC event loop bằng `future.get()`. Nếu dùng API blocking, chuyển việc chờ sang executor chuyên dụng có giới hạn. Khi callback cần chạy trên context gRPC, phải quản lý việc capture/restore context có chủ đích; không giả định mọi ThreadLocal tự truyền qua executor.

## 5. Broker acknowledgement không có nghĩa consumer đã xử lý

Response sau publish chỉ có thể cam kết điều mà producer/broker xác nhận:

- Producer gửi message và nhận acknowledgement theo cấu hình.
- Broker có thể đã ghi message theo replication/durability policy.
- Consumer có thể chưa nhận, chưa xử lý hoặc xử lý thất bại.

Với Kafka, độ bền phụ thuộc cấu hình như `acks=all`, replication factor và `min.insync.replicas`, cùng tình trạng cluster. Với RabbitMQ, cần xem publisher confirms, durable queue, persistent message và cấu hình replication tương ứng.

Tên state `PUBLISHED` nên có định nghĩa rõ trong API: broker đã xác nhận message, không phải consumer đã commit side effect. Nếu cần biết consumer hoàn tất, hãy cung cấp operation status, reply channel hoặc event kết quả riêng.

## 6. So sánh hai cách trả response

| Tiêu chí | Trả sau durable outbox commit, trước broker publish | Trả sau broker acknowledgement |
|---|---|---|
| Điều kiện trả response | Database transaction lưu receipt + outbox thành công | Producer nhận acknowledgement |
| Latency RPC | Thường thấp và ít phụ thuộc broker | Phụ thuộc latency broker |
| Broker tạm lỗi | Vẫn có thể trả `ACCEPTED`; outbox pending | Có thể trả lỗi/timeout |
| Mất message sau response | Outbox giữ ý định dispatch bền vững | Phụ thuộc durability và retry của broker/producer |
| Ý nghĩa response | Đã ghi nhận để dispatch | Broker đã xác nhận nhận message |
| Consumer đã xử lý? | Không được bảo đảm | Không được bảo đảm |
| Thành phần cần vận hành | Database, outbox relay, broker | Producer, broker và thường vẫn cần outbox nếu có DB state |

Không có lựa chọn đúng cho mọi API. Chọn theo điều client cần biết và mức độ phụ thuộc mà RPC chấp nhận. Với command quan trọng có thay đổi database, outbox thường là nền tảng đáng tin cậy; việc response có chờ broker hay không là một quyết định hợp đồng bổ sung.

## 7. Failure window khi chờ publish acknowledgement

Chờ broker acknowledgement tăng độ chắc chắn về việc publish nhưng tạo ra các tình huống cần xử lý:

| Tình huống | Điều ingress biết | Cách xử lý |
|---|---|---|
| Broker ack thành công | Broker xác nhận nhận message | Có thể trả `PUBLISHED` |
| Broker từ chối rõ ràng trước khi nhận | Publish thất bại | Trả lỗi phù hợp hoặc retry theo policy |
| Timeout trước ack | Không biết chắc broker đã nhận hay chưa | Xem là kết quả không chắc chắn; retry bằng cùng idempotency key |
| Broker ack thành công, response bị mất | Message đã được nhận nhưng client không biết | Client retry cùng key hoặc truy vấn operation |
| Client cancel khi publish đang chờ | RPC không còn cần response | Không giả định message đã bị thu hồi; xác định trạng thái bằng idempotency/receipt |

Timeout không chứng minh broker chưa nhận message. Kết nối có thể bị ngắt sau khi broker ghi message nhưng trước khi acknowledgement đến producer. Trả `UNAVAILABLE` hoặc `DEADLINE_EXCEEDED` trong tình huống này không được khiến client tạo một ý định mới.

## 8. Database state và broker publish: tránh dual-write

Nếu use case commit dữ liệu nghiệp vụ rồi publish trực tiếp:

~~~text
Database commit
      |
      +---- process crash ----> event chưa được gửi
      |
      v
Publish broker
      |
      +---- broker ack bị mất --> producer không rõ kết quả
~~~

Chờ publish xong rồi mới trả gRPC response không loại bỏ khoảng trống dual-write. Database có thể commit thành công nhưng broker publish thất bại. Nếu trả lỗi, client có thể tưởng nghiệp vụ chưa xảy ra và gửi lại.

Transactional outbox ghi business state và event record trong cùng database transaction. Relay publish sau commit và đánh dấu record sau acknowledgement. Nếu relay crash sau broker ack nhưng trước khi mark published, message có thể được gửi lại; consumer cần idempotent.

Nếu API trả trước broker publish, response dựa trên outbox commit. Nếu API trả sau broker publish, có thể chờ relay/broker confirmation nhưng vẫn phải giữ operation receipt và idempotency để giải quyết kết quả không chắc chắn.

## 9. Idempotency là bắt buộc khi response có thể bị mất

Client chỉ nhìn thấy kết quả qua network. Server có thể đã commit outbox hoặc broker đã nhận message trong khi response không đến client. Retry vì vậy phải biểu đạt cùng một ý định:

1. Client tạo idempotency key cho thao tác nghiệp vụ.
2. Mọi retry gửi lại cùng key và cùng payload logic.
3. Ingress lưu mapping `(tenantId, idempotencyKey)` sang `operationId`/`commandId`.
4. Nếu request lặp cùng payload, trả lại operation đã có và trạng thái hiện tại.
5. Nếu key giống nhưng payload khác, trả conflict theo API contract.
6. Consumer deduplicate theo command/event ID trước side effect.

Không tạo `operationId` mới mỗi lần client retry. Cũng không chỉ dựa vào Kafka idempotent producer: tính năng đó không thay thế idempotency từ client qua ingress, database và consumer.

## 10. Thiết kế response contract có operation ID

Với xử lý bất đồng bộ, response nên cung cấp một ID ổn định để client truy vấn:

~~~proto
message SubmitOrderReply {
  string operation_id = 1;
  OperationState state = 2;
}

enum OperationState {
  OPERATION_STATE_UNSPECIFIED = 0;
  ACCEPTED = 1;
  PUBLISHED = 2;
  PROCESSING = 3;
  COMPLETED = 4;
  REJECTED = 5;
}

message GetOperationRequest {
  string operation_id = 1;
}

message GetOperationReply {
  OperationState state = 1;
  string result_reference = 2;
  string failure_code = 3;
}
~~~

Tên enum và trạng thái là ví dụ cho API. Chỉ công bố trạng thái mà hệ thống có thể xác định đáng tin cậy. `PUBLISHED` cần được cập nhật sau broker acknowledgement; `COMPLETED` cần dựa trên kết quả consumer đã commit. Không chuyển sang `COMPLETED` chỉ vì consumer bắt đầu xử lý.

Operation status có thể được lưu trong database hoặc dựng từ event/status store. Phải xác định thời gian lưu, quyền truy cập theo tenant và cách xử lý operation không tồn tại.

## 11. Deadline và thời gian chờ của client

Deadline gRPC giới hạn thời gian RPC, nhưng không tự giới hạn thời gian command xử lý trong broker/consumer. Ví dụ:

~~~text
Deadline RPC: 700 ms
  Authentication + validation: 20 ms
  Persist outbox: 15 ms
  Return ACCEPTED

Sau response:
  Relay publish: 40-500 ms (có thể retry)
  Consumer processing: vài giây
  Operation status: COMPLETED hoặc REJECTED
~~~

Nếu API chọn trả sau broker acknowledgement, thời gian chờ producer phải nằm trong ngân sách deadline. Không đặt producer timeout dài hơn nhiều so với deadline còn lại của RPC.

Khi client deadline hết, server có thể nhận cancellation, nhưng transaction đã commit hoặc message đã được broker nhận không tự rollback. Nếu công việc cần hủy, thiết kế command hủy riêng và kiểm tra trạng thái/race condition. Cancellation của RPC chỉ kết thúc tương tác hiện tại.

## 12. Chờ consumer hoàn tất: request/reply là hợp đồng khác

Một số API cần trả kết quả nghiệp vụ cuối cùng trong cùng RPC. Khi đó ingress có thể:

1. Publish command kèm correlation ID và reply destination.
2. Consumer xử lý command.
3. Consumer gửi reply chứa correlation ID và kết quả.
4. Ingress ghép reply với RPC đang chờ và trả response.

Mô hình này có thể phù hợp với xử lý ngắn, có giới hạn thời gian và throughput vừa phải. Tuy nhiên:

- RPC connection bị giữ trong thời gian consumer xử lý.
- Deadline phải bao gồm broker, queue wait, consumer và reply.
- Ingress cần quản lý pending request, timeout, cancellation và reply đến muộn.
- Nếu ingress restart, pending correlation state có thể mất trừ khi được lưu bền vững.
- Consumer vẫn cần idempotency khi command bị gửi lại.

Với workflow dài, trả `ACCEPTED` kèm operation ID rồi cho client truy vấn trạng thái thường dễ vận hành hơn việc giữ một RPC mở hàng chục giây hoặc vài phút.

## 13. Ánh xạ lỗi theo mốc response

Status code phải phù hợp với điều server biết:

| Tình huống | Phản hồi gợi ý |
|---|---|
| Request không hợp lệ | `INVALID_ARGUMENT` |
| Caller không được phép gửi command | `PERMISSION_DENIED` |
| Không đủ quota/in-flight capacity | `RESOURCE_EXHAUSTED` |
| Outbox transaction rollback | `INTERNAL` hoặc status lỗi persistence theo API policy; không trả `ACCEPTED` |
| Outbox commit thành công | Response `OK` với state `ACCEPTED` |
| Broker ack thành công | Response `OK` với state `PUBLISHED` |
| Broker từ chối rõ ràng | `UNAVAILABLE` hoặc status được định nghĩa |
| Publish timeout, kết quả không chắc chắn | `DEADLINE_EXCEEDED`/`UNAVAILABLE` kèm operation/idempotency để tra cứu |
| Consumer xử lý nghiệp vụ thất bại sau acceptance | Cập nhật operation thành `REJECTED` hoặc failure state; không đổi lịch sử acceptance thành chưa từng nhận |

Không dùng gRPC status để biểu đạt mọi trạng thái workflow kéo dài. RPC status mô tả kết quả của lần gọi; operation state mô tả tiến trình nghiệp vụ sau khi request đã được nhận.

## 14. Kiểm thử response trước và sau publish

Test phải xác minh đúng mốc mà response cam kết:

| Kịch bản | Response trước publish với outbox | Response sau broker ack |
|---|---|---|
| Database commit thành công | Trả `ACCEPTED` | Chưa trả cho đến khi publish được xác nhận |
| Database rollback | Không trả `ACCEPTED` | Không trả `PUBLISHED` |
| Broker tạm ngừng | Vẫn có thể trả `ACCEPTED`; outbox pending | Trả lỗi/timeout theo policy |
| Broker ack thành công | Operation chuyển `PUBLISHED` sau đó | Trả `PUBLISHED` |
| Ack bị mất sau khi broker nhận | Relay retry; consumer idempotent | Client retry cùng key; không tạo operation mới |
| Response bị mất sau commit/ack | Retry trả cùng operation ID | Retry trả cùng operation ID |
| Client cancel trước response | Durable intent vẫn theo policy nếu đã commit | Publish có thể đã thành công; không giả định cancel thu hồi message |
| Consumer xử lý lỗi | Operation chuyển failure/rejected | Operation chuyển failure/rejected |
| Consumer xử lý xong | Operation chuyển `COMPLETED` | Operation chuyển `COMPLETED` |

Integration test nên dùng database và broker thật hoặc containerized broker để kiểm tra commit, acknowledgement, retry và redelivery. Mock producer chỉ xác minh code gọi `send`, không xác minh durability hay kết quả broker.

## 15. Metrics và chẩn đoán

Theo dõi riêng từng mốc:

- RPC latency và status code theo method.
- Thời gian transaction commit và số outbox record pending.
- Tuổi record outbox cũ nhất và relay retry count.
- Producer acknowledgement latency, timeout và send failure.
- Số operation ở `ACCEPTED`, `PUBLISHED`, `PROCESSING`, `COMPLETED`, `REJECTED`.
- Khoảng thời gian từ acceptance đến publish và từ publish đến completion.
- Số retry/idempotency hit, duplicate consumer và dead-letter.
- Client cancellation và deadline exceeded.

Nếu client nhận `ACCEPTED` nhưng chưa thấy event, kiểm tra outbox pending, relay và broker. Nếu client nhận `PUBLISHED` nhưng operation chưa hoàn tất, kiểm tra consumer lag, consumer group, retry và dead-letter. Hai trạng thái này chỉ ra hai giai đoạn khác nhau.

Không dùng operation ID hoặc customer ID làm metric label có cardinality cao. Đưa các ID vào log/trace; metrics nên nhóm theo method, event type, topic, status và consumer.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Trả `ACCEPTED` ngay sau khi gọi `send` | Future có thể thất bại sau response | Chờ durable outbox commit hoặc broker ack |
| Gọi `PUBLISHED` khi consumer chưa xử lý | Client hiểu sai trạng thái nghiệp vụ | Tách `PUBLISHED` và `COMPLETED` |
| Chờ broker nhưng không có idempotency | Ack có thể mất và retry tạo duplicate | Dùng operation ID/idempotency key ổn định |
| Chờ publish trên event loop | Chặn xử lý RPC khác | Dùng callback hoặc bounded executor |
| Publish trực tiếp sau DB commit | Dual-write có thể làm mất event | Dùng transactional outbox |
| Coi timeout là bằng chứng broker chưa nhận | Retry có thể tạo command mới | Xử lý kết quả không chắc chắn bằng cùng key |
| Coi gRPC cancellation là rollback | Message đã commit vẫn được consumer xử lý | Tách RPC cancellation khỏi command cancellation |
| Giữ RPC mở cho workflow dài | Giữ tài nguyên và dễ vượt deadline | Trả operation ID, cung cấp status API |
| Không lưu trạng thái operation | Client không biết kết quả sau response mất | Lưu receipt và trạng thái có thời hạn |

**Ghi nhớ:** Trả response trước broker publish chỉ an toàn khi command/outbox đã được ghi bền vững; khi đó `ACCEPTED` có nghĩa đã ghi nhận để dispatch. Trả response sau publish acknowledgement cho phép cam kết broker đã nhận, nhưng không chứng minh consumer hoàn tất và có thể tăng latency RPC. Dùng operation ID và idempotency để xử lý response mất hoặc acknowledgement không chắc chắn; dùng outbox khi database state và message phải nhất quán. Tách `ACCEPTED`, `PUBLISHED` và `COMPLETED` thành các mốc rõ ràng trong hợp đồng.
