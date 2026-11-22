# Xử lý RESOURCE_EXHAUSTED

## Mục tiêu bài học

Trong **SPRING_GRPC**, server cần giới hạn concurrency, queue, message size, connection và quota để bảo vệ process cũng như downstream dependencies. Khi một giới hạn bị chạm, gRPC có status RESOURCE_EXHAUSTED. Client cần hiểu nguyên nhân để quyết định chờ, giảm tải, giảm kích thước request hay dừng retry.

Bài học tập trung vào **xử lý RESOURCE_EXHAUSTED**: phân biệt quá tải tạm thời với quota và payload vượt giới hạn, phát status đúng semantics, áp dụng admission control và bounded queues, truyền retry guidance, thiết kế retry có ngân sách, xử lý streaming/backpressure, quan sát tỷ lệ từ chối và kiểm thử saturation/recovery.

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của gRPC status RESOURCE_EXHAUSTED.
2. Phân loại capacity exhaustion, quota exhaustion và message/resource limit.
3. Trả RESOURCE_EXHAUSTED tại service boundary khi không thể nhận thêm công việc.
4. Giới hạn concurrency, queue và payload size.
5. Truyền retry guidance an toàn bằng status details khi phù hợp.
6. Thiết kế client retry có backoff, jitter, deadline và idempotency.
7. Kết hợp streaming flow control với giới hạn tài nguyên.
8. Theo dõi overload và kiểm thử hệ thống khi chạm giới hạn.

> **Phạm vi:** Ví dụ dùng gRPC Java, Spring và protobuf. Một số ví dụ dùng google.rpc.Status/RetryInfo trong googleapis common protos. Tên property của Spring gRPC starter phụ thuộc phiên bản; các cấu hình app.grpc.* trong bài là namespace do ứng dụng tự định nghĩa.

## 1. RESOURCE_EXHAUSTED có nghĩa gì?

RESOURCE_EXHAUSTED là gRPC status code số 8. Nó cho biết operation không thể hoàn tất vì một tài nguyên hoặc quota đã cạn/vượt giới hạn. Status này không tự nói rằng lỗi sẽ tự phục hồi hay client nên retry ngay.

Các nguyên nhân thường gặp:

| Nguyên nhân | Ví dụ | Hướng xử lý thường phù hợp |
| --- | --- | --- |
| Capacity tạm thời | Worker pool đầy, semaphore hết permit, server đang quá tải | Từ chối sớm; có thể retry sau khoảng chờ nếu operation an toàn |
| Quota | Tenant vượt số request/phút hoặc giới hạn sử dụng | Chờ quota window/reset hoặc yêu cầu thay đổi quota; retry dồn dập không giúp |
| Payload vượt giới hạn | Message lớn hơn inbound message size limit | Giảm/chia nhỏ payload; gửi lại nguyên request thường vẫn thất bại |
| Tài nguyên downstream | Connection pool hoặc downstream capacity cạn | Giảm tải, timeout, circuit breaker và retry có kiểm soát |
| Tài nguyên hệ thống | Bộ nhớ, file descriptor hoặc giới hạn vận hành | Bảo vệ process, điều tra nguyên nhân và phục hồi capacity |

Không dùng RESOURCE_EXHAUSTED cho mọi lỗi server. Ví dụ request sai định dạng nên là INVALID_ARGUMENT; caller không có quyền là PERMISSION_DENIED; deadline đã hết là DEADLINE_EXCEEDED. Status chính xác giúp client và dashboard chọn hành vi phù hợp.

### 1.1. Phân biệt capacity, quota và payload

Ba nhóm này thường cần cách xử lý khác nhau:

- **Capacity exhaustion:** giới hạn đồng thời hoặc hàng đợi đang đầy. Có thể tạm thời nếu tải giảm.
- **Quota exhaustion:** caller/tenant đã dùng hết ngân sách được cấp. Chỉ retry sau reset hoặc khi quota được cấp thêm.
- **Payload/resource limit:** request vượt giới hạn cố định như message size. Cần thay đổi request hoặc cấu hình được phê duyệt.

Có thể giữ cùng gRPC code RESOURCE_EXHAUSTED nhưng phân loại reason nội bộ thành tập giá trị hữu hạn như capacity, quota, message_size. Không nhúng tenant ID hoặc request ID vào metric label để mô tả nguyên nhân.

## 2. Xác định giới hạn cần bảo vệ

Trước khi trả status, xác định tài nguyên nào cần giới hạn và ở tầng nào:

| Tài nguyên | Cơ chế giới hạn |
| --- | --- |
| RPC đang xử lý đồng thời | Semaphore/admission control hoặc server concurrency policy |
| Worker threads | Bounded executor với max threads |
| Task chờ | Queue capacity hữu hạn |
| Message inbound | max inbound message size |
| Request rate | Rate limiter/token bucket |
| Quota tenant/API key | Quota store hoặc policy service |
| Downstream connections | Connection pool và concurrency limit |
| Streaming messages | Flow control, bounded buffer và giới hạn in-flight |
| Thời gian xử lý | Deadline, timeout và cancellation |

Giới hạn phải được chọn theo capacity của downstream và latency budget, không chỉ theo số CPU của service. Nếu gRPC server nhận 500 RPC đồng thời nhưng database chỉ chịu 50 query đồng thời, cần giới hạn admission hoặc pool ở mức phù hợp trước khi database bị quá tải.

Không dùng queue vô hạn để hấp thụ traffic burst. Queue vô hạn chỉ trì hoãn thất bại, tăng memory pressure và khiến request chờ tới khi deadline hết.

## 3. Phát RESOURCE_EXHAUSTED khi admission control từ chối

Admission control quyết định có nhận thêm một operation hay không trước khi bắt đầu công việc tốn tài nguyên. Một semaphore giới hạn số operation đang chạy:

```java
@GrpcService
public class InventoryGrpcService
        extends InventoryGrpc.InventoryImplBase {

    private final Semaphore permits = new Semaphore(64);
    private final InventoryRepository repository;

    public InventoryGrpcService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public void getStock(
            GetStockRequest request,
            StreamObserver<GetStockResponse> observer) {

        if (!permits.tryAcquire()) {
            observer.onError(
                    Status.RESOURCE_EXHAUSTED
                            .withDescription("Server đang quá tải")
                            .asRuntimeException());
            return;
        }

        try {
            Stock stock = repository.load(request.getSku());

            observer.onNext(
                    GetStockResponse.newBuilder()
                            .setAvailable(stock.available())
                            .build());
            observer.onCompleted();
        } catch (Exception ex) {
            observer.onError(
                    Status.INTERNAL
                            .withDescription("Không thể đọc tồn kho")
                            .asRuntimeException());
        } finally {
            permits.release();
        }
    }
}
```

Ví dụ dùng xử lý đồng bộ để minh họa admission control; trong service blocking thật, không nên giữ gRPC callback thread quá lâu. Nếu offload sang worker pool, chỉ release permit khi operation thực sự kết thúc/cancel, không release ngay sau khi submit task. Với async callback, bảo đảm release đúng một lần bằng operation lifecycle/atomic guard.

Permit phải được release trong mọi đường success, exception và cancellation. Nếu permit bị leak, service sẽ tiếp tục trả RESOURCE_EXHAUSTED dù tải đã giảm.

### 3.1. Admission control trước khi submit worker

Khi service dùng bounded worker executor:

1. Kiểm tra deadline/cancellation.
2. Thử nhận permit hoặc kiểm tra capacity.
3. Submit task vào bounded executor.
4. Nếu executor từ chối, trả RESOURCE_EXHAUSTED.
5. Khi task kết thúc hoặc bị hủy, release permit.
6. Đảm bảo terminal callback chỉ được gửi một lần.

Không bắt mọi RuntimeException rồi đổi thành RESOURCE_EXHAUSTED. Chỉ map lỗi admission/rejection đã xác định; lỗi nghiệp vụ và lỗi lập trình cần status tương ứng.

## 4. Bounded executor và queue

Spring ThreadPoolTaskExecutor có thể cấu hình số worker và queue hữu hạn:

```java
@Bean
ThreadPoolTaskExecutor grpcBusinessExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(16);
    executor.setMaxPoolSize(48);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("grpc-business-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(20);
    return executor;
}
```

Các giá trị trên chỉ là ví dụ. Chọn chúng theo throughput, thời gian blocking, database connection pool, downstream limits và latency budget. Một queue 100 không có nghĩa hệ thống luôn có thể xử lý thêm 100 request; đó là 100 task đang chờ, và thời gian chờ có thể khiến deadline hết trước khi task bắt đầu.

Bắt rejection ở đúng ranh giới submit:

```java
try {
    grpcBusinessExecutor.execute(task);
} catch (RejectedExecutionException ex) {
    observer.onError(
            Status.RESOURCE_EXHAUSTED
                    .withDescription("Capacity tạm thời đã đạt giới hạn")
                    .asRuntimeException());
}
```

Trong thực tế, ThreadPoolTaskExecutor của Spring có thể bọc rejection thành TaskRejectedException, một loại RejectedExecutionException. Bắt RejectedExecutionException bao phủ cả hai trường hợp; nếu dùng abstraction khác, kiểm tra hierarchy của exception trước khi chọn catch type. Một handler có thể chuyển rejection thành domain exception rồi map tập trung ở service boundary.

Không dùng CallerRunsPolicy tùy tiện. Nếu caller là gRPC transport/callback thread, task blocking có thể chiếm thread xử lý RPC khác và làm nghẽn server. Không dùng DiscardPolicy vì nó có thể làm mất task mà không báo client.

## 5. Giới hạn message size và payload

gRPC Java cho phép cấu hình inbound message size ở server/channel builder. Ví dụ:

```java
ServerBuilder<?> serverBuilder = obtainServerBuilder();
serverBuilder.maxInboundMessageSize(4 * 1024 * 1024);
```

Đây là giới hạn 4 MiB minh họa. Cần đặt nhất quán với client, proxy, gateway và các service downstream. Không tăng giới hạn chỉ để một request lớn hoạt động nếu payload có thể được phân trang, chia batch hoặc chuyển sang object storage.

Khi request vượt giới hạn transport, gRPC có thể từ chối trước khi service method được gọi. Vì vậy, không phải mọi lỗi message size đều có thể được map bằng try/catch trong service. Hãy kiểm thử behavior của đúng transport/version và quan sát status phía client.

Đối với payload lớn:

- Ưu tiên pagination hoặc batch có giới hạn.
- Đặt maximum item count và tổng byte size.
- Dùng streaming khi semantics phù hợp, kèm flow control.
- Cân nhắc upload trực tiếp tới object storage thay vì chuyển blob lớn qua RPC.
- Validate kích thước ở gateway/client nếu có thể, nhưng server vẫn phải enforce giới hạn.

## 6. Truyền retry guidance bằng google.rpc.RetryInfo

Với capacity exhaustion có khả năng phục hồi, server có thể đính kèm RetryInfo để gợi ý thời gian chờ. Đây là status detail chuẩn trong Google RPC error model; client chỉ dùng được khi cả hai phía hỗ trợ status details.

Ví dụ tạo status detail:

```java
RetryInfo retryInfo = RetryInfo.newBuilder()
        .setRetryDelay(
                com.google.protobuf.Duration.newBuilder()
                        .setSeconds(2)
                        .build())
        .build();

com.google.rpc.Status rpcStatus =
        com.google.rpc.Status.newBuilder()
                .setCode(Code.RESOURCE_EXHAUSTED.getNumber())
                .setMessage("Capacity tạm thời đã đạt giới hạn")
                .addDetails(Any.pack(retryInfo))
                .build();

observer.onError(
        StatusProto.toStatusRuntimeException(rpcStatus));
```

Cần dependency googleapis common protos và grpc-protobuf tương thích. Không phải mọi client language hoặc proxy đều expose status details giống nhau; luôn có fallback an toàn nếu client không đọc được RetryInfo.

Không gửi RetryInfo cho quota exhaustion nếu retry sau hai giây vẫn chắc chắn thất bại. Với quota, thông tin hữu ích có thể là reset time theo contract riêng hoặc QuotaFailure detail; tránh để client hiểu nhầm mọi RESOURCE_EXHAUSTED đều là transient.

### 6.1. Client đọc RetryInfo

Client có thể extract google.rpc.Status từ throwable:

```java
com.google.rpc.Status details = StatusProto.fromThrowable(error);

if (details != null) {
    for (Any detail : details.getDetailsList()) {
        if (detail.is(RetryInfo.class)) {
            RetryInfo retryInfo = detail.unpack(RetryInfo.class);
            Duration delay = retryInfo.getRetryDelay();
            // Chuyển delay sang retry policy có giới hạn.
        }
    }
}
```

Xử lý InvalidProtocolBufferException khi unpack detail. Không tin thời gian chờ từ server một cách vô điều kiện: áp dụng minimum/maximum, deadline còn lại và client retry budget. Nếu detail thiếu hoặc sai định dạng, dùng policy mặc định có giới hạn hoặc trả lỗi cho caller.

## 7. Retry có kiểm soát ở client

RESOURCE_EXHAUSTED không tự động có nghĩa là retry an toàn. Trước khi retry, client phải biết:

- Operation có idempotent không?
- Lỗi là capacity tạm thời hay quota/payload cố định?
- Deadline còn đủ không?
- Server có cung cấp RetryInfo không?
- Số attempt còn trong retry budget không?
- Có circuit breaker hoặc rate limiter đang mở không?

Một policy thường dùng cho capacity tạm thời:

1. Tôn trọng RetryInfo nếu có, sau khi áp dụng min/max.
2. Nếu không có hint, dùng exponential backoff với full jitter.
3. Giới hạn max attempts và tổng retry time.
4. Không retry khi deadline gần hết.
5. Không retry operation không idempotent nếu không có idempotency key/deduplication.
6. Khi nhận quota exhaustion, chờ quota reset hoặc trả lỗi lên caller.
7. Khi payload quá lớn, yêu cầu client giảm payload; không retry cùng payload.

Công thức backoff có giới hạn:

```text
delay(attempt) = random(0, min(maxDelay, baseDelay × 2^attempt))
```

Jitter giúp nhiều client không cùng retry tại một thời điểm. Retry storm có thể làm capacity vừa phục hồi lại cạn ngay lập tức. Client cần phối hợp retry budget, rate limit và circuit breaker.

### 7.1. Không retry ở nhiều tầng cùng lúc

Nếu gRPC service config, application gateway và business client đều retry, tổng số request có thể nhân lên. Chọn một tầng sở hữu retry policy cho mỗi downstream operation; các tầng khác phải tôn trọng deadline và không lặp retry ngầm.

Đặt retry count vào metrics/trace attributes có cardinality thấp. Không log toàn bộ request mỗi lần retry.

## 8. Streaming RPC và backpressure

Flow control của gRPC giúp receiver điều tiết lượng message mà sender được phép gửi. Nó khác với RESOURCE_EXHAUSTED:

- **Backpressure/flow control:** receiver tạm thời chưa sẵn sàng nhận thêm message; sender giảm tốc theo protocol.
- **RESOURCE_EXHAUSTED:** ứng dụng hoặc transport đã chạm một giới hạn và không thể nhận thêm resource/work.
- **Quota exhaustion:** caller đã vượt ngân sách được cấp; giảm tốc trong vài millisecond có thể không giải quyết.

Với async streaming, chỉ request thêm message khi application capacity cho phép. Ở phía server response stream, kiểm tra readiness và gửi tiếp khi observer báo sẵn sàng theo API phù hợp. Không tích lũy toàn bộ stream trong unbounded queue.

Giới hạn:

- Số message đang xử lý đồng thời.
- Số message/byte đang chờ trong buffer.
- Tổng byte của stream nếu contract cần giới hạn.
- Thời gian stream và idle timeout.
- Số stream đồng thời trên mỗi client/tenant.

Khi stream vượt policy, trả status phù hợp và kết thúc stream rõ ràng. Đừng dùng RESOURCE_EXHAUSTED để biểu diễn một lần flow-control pause bình thường.

## 9. Quota theo tenant hoặc caller

Quota cần định nghĩa rõ dimension và cửa sổ tính:

- Requests per second/minute.
- Concurrent RPCs.
- Bytes uploaded/downloaded.
- Số record hoặc operation tiêu thụ.
- Quota theo API key, tenant, project hoặc plan.

Quota enforcement phải dựa trên identity đã xác thực, không dựa trên tenant ID tùy ý trong metadata. Với distributed service, quota store cần xử lý concurrency/atomicity; cache local có thể dùng để giảm latency nhưng phải hiểu sai số và consistency.

Khi quota bị vượt:

- Trả RESOURCE_EXHAUSTED.
- Có thể đính kèm quota reason/reset guidance theo contract.
- Không retry nhanh trước khi quota reset.
- Không tiết lộ quota của tenant khác.
- Ghi metric theo quota class hoặc policy name có cardinality hữu hạn.

Không đưa tenant ID, user ID hoặc API key vào metric labels. Nếu cần điều tra một tenant, dùng log/trace có access control và retention phù hợp.

## 10. Mapping lỗi nội bộ sang gRPC status

Tập trung mapping lỗi capacity/quota tại service boundary:

| Lỗi nội bộ | gRPC status | Ghi chú |
| --- | --- | --- |
| Admission permit unavailable | RESOURCE_EXHAUSTED | Capacity tạm thời |
| Bounded executor rejected task | RESOURCE_EXHAUSTED | Chỉ khi đúng là capacity exhaustion |
| Quota exceeded | RESOURCE_EXHAUSTED | Thường không retry trước reset |
| Message vượt transport limit | RESOURCE_EXHAUSTED hoặc transport-specific status | Có thể bị từ chối trước service |
| Request sai field/format | INVALID_ARGUMENT | Client phải sửa request |
| Không có quyền | PERMISSION_DENIED | Không retry |
| Dependency tạm thời unavailable | UNAVAILABLE | Retry chỉ khi policy cho phép |
| Deadline hết | DEADLINE_EXCEEDED | Kiểm tra ngân sách thời gian |
| Lỗi không dự kiến | INTERNAL | Không che bằng RESOURCE_EXHAUSTED |

Không expose stack trace hoặc tên class nội bộ trong Status description. Có thể ghi exception chi tiết ở log đã redaction kèm trace ID; client nhận message ổn định, không nhạy cảm.

## 11. Metrics và alert cho resource exhaustion

Theo dõi tối thiểu:

| Metric | Mục đích |
| --- | --- |
| RPC count theo status | Tỷ lệ RESOURCE_EXHAUSTED |
| Admission rejected count | Số request bị từ chối trước xử lý |
| Active permits / concurrency | Mức sử dụng giới hạn đồng thời |
| Executor active threads | Mức sử dụng worker pool |
| Queue size / wait duration | Backlog và thời gian chờ |
| Rejected task count | Mức saturation của executor |
| Message size distribution | Phát hiện payload gần ngưỡng |
| Quota exceeded count | Phân biệt quota với capacity |
| Retry attempts / retry delay | Phát hiện retry storm |
| Downstream pool utilization | Xác định bottleneck ở dependency |

Metrics labels nên là service, method, status và reason class có tập giá trị hữu hạn. Không gắn request ID, user ID, tenant ID hoặc raw target vào metric label.

Alert nên dựa trên tỷ lệ và thời gian kéo dài, không chỉ một lỗi đơn lẻ. Một số RESOURCE_EXHAUSTED có thể là admission control đang bảo vệ hệ thống đúng cách; tỷ lệ tăng đột biến kèm latency, queue wait hoặc downstream saturation mới cho biết cần điều tra capacity.

## 12. Kiểm thử saturation và recovery

Test phải tái hiện được capacity exhaustion một cách deterministic. Dùng semaphore nhỏ, executor có một worker/queue nhỏ, CountDownLatch và timeout; tránh sleep dài.

Các trường hợp cần có:

1. **Admission full:** chiếm hết permits rồi gửi thêm RPC; request mới nhận RESOURCE_EXHAUSTED.
2. **Permit release:** hoàn tất/cancel request; permit được trả và RPC mới có thể chạy.
3. **Executor rejection:** làm worker bận và queue đầy; rejection được map đúng status.
4. **No task loss:** không có task bị discard im lặng hoặc RPC bị treo.
5. **RetryInfo:** server trả RetryInfo; client đọc delay và áp dụng giới hạn.
6. **Quota:** vượt quota; client không retry nhanh trước reset.
7. **Payload limit:** request quá lớn bị từ chối; client không lặp lại cùng payload.
8. **Deadline:** retry budget không vượt deadline tổng.
9. **Idempotency:** operation không idempotent không được retry mù.
10. **Streaming:** buffer/in-flight bị giới hạn; flow control không tạo unbounded queue.
11. **Recovery:** sau khi tải giảm, permit/queue trở lại bình thường và RPC thành công.
12. **Concurrency:** nhiều request đồng thời không làm leak permit hoặc gửi terminal callback hai lần.

### 12.1. Ví dụ test admission control

Tạo service test với một permit. Request đầu giữ permit bằng latch; request thứ hai phải nhận RESOURCE_EXHAUSTED; sau khi nhả latch, request thứ ba phải thành công. Assert permit count cuối cùng trở về giá trị ban đầu.

Không assert thời gian tuyệt đối quá chặt vì scheduler khác nhau; dùng latch để đồng bộ và timeout để test không treo.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client retry liên tục và tải tăng | Retry mọi RESOURCE_EXHAUSTED không phân loại | Phân biệt capacity, quota và payload; backoff/jitter/budget |
| Server hết permits dù tải đã giảm | Permit không release ở exception/cancel path | Quản lý lifecycle và release exactly once |
| RPC bị treo khi executor đầy | Rejection bị nuốt hoặc task bị discard | Dùng rejection policy rõ và trả status |
| Queue tăng dù throughput không tăng | Downstream chậm hoặc queue quá lớn | Giới hạn queue, đo queue wait và capacity dependency |
| Payload hợp lệ ở client nhưng fail server | Message size limit khác nhau | Đồng bộ giới hạn và kiểm tra proxy/transport |
| RESOURCE_EXHAUSTED bị dùng cho validation | Mapping status quá rộng | Dùng INVALID_ARGUMENT cho request sai |
| Quota client bị retry trước reset | Không phân biệt quota với overload | Truyền quota guidance và không retry sớm |
| Streaming memory tăng liên tục | Buffer/unbounded queue hoặc request message không điều tiết | Áp dụng flow control và giới hạn in-flight |
| Retry vượt deadline | Mỗi attempt dùng timeout mới không xét deadline cha | Tính ngân sách còn lại và dừng retry |
| Nhiều tầng cùng retry | Retry policy bị nhân lên | Chọn một tầng sở hữu retry |
| Dashboard không phân biệt nguyên nhân | Chỉ đếm status tổng | Thêm reason class cardinality thấp |
| Recovery vẫn trả RESOURCE_EXHAUSTED | Worker/permit leak hoặc downstream chưa phục hồi | Kiểm tra active count, queue, permit và dependency |

## 14. Bài tập thực hành

1. Tạo bounded business executor với core/max threads và queue hữu hạn.
2. Thêm admission control giới hạn số RPC đang chạy đồng thời.
3. Map permit exhaustion và executor rejection sang RESOURCE_EXHAUSTED.
4. Đảm bảo permit release khi success, exception và cancellation.
5. Cấu hình inbound message size và kiểm thử payload vượt ngưỡng.
6. Tạo google.rpc.RetryInfo cho capacity exhaustion có thể phục hồi.
7. Viết client parser đọc RetryInfo và áp dụng exponential backoff với jitter, max attempts và deadline budget.
8. Tạo quota policy theo authenticated principal; xác minh quota không dựa trên metadata chưa tin cậy.
9. Tạo streaming workload với bounded buffer và flow control.
10. Ghi metrics phân biệt capacity, quota và payload limit.
11. Viết saturation test với semaphore/executor nhỏ và xác minh recovery.
12. Kiểm thử retry storm, idempotency và cancellation trước khi đưa policy vào production.

### Câu hỏi tự kiểm tra

- RESOURCE_EXHAUSTED có luôn là lỗi transient không?
- Capacity exhaustion khác quota exhaustion và payload limit thế nào?
- Vì sao admission control nên từ chối sớm trước khi submit task?
- Khi nào permit cần được release trong async RPC?
- Vì sao CallerRunsPolicy có thể gây nghẽn gRPC callback thread?
- RetryInfo giúp client điều chỉnh retry ra sao?
- Vì sao quota exhaustion thường không nên retry ngay?
- Exponential backoff và jitter giúp tránh retry storm như thế nào?
- Khi nào một RPC không an toàn để retry?
- Flow control khác RESOURCE_EXHAUSTED ra sao?
- Vì sao message size có thể bị từ chối trước khi service method chạy?
- Cần metric nào để phân biệt capacity bottleneck với quota?
- Làm thế nào kiểm thử permit leak và recovery?

## Tài liệu tham khảo

- [gRPC — Status Codes](https://grpc.io/docs/guides/status-codes/): semantics của RESOURCE_EXHAUSTED và các status khác.
- [gRPC — Error Handling](https://grpc.io/docs/guides/error/): truyền lỗi và status details.
- [gRPC — Retry](https://grpc.io/docs/guides/retry/): retry policy, attempts và backoff.
- [gRPC — Flow Control](https://grpc.io/docs/guides/flow-control/): điều tiết streaming message.
- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): cấu hình server và inbound message size.
- [gRPC Java — Status](https://grpc.github.io/grpc-java/javadoc/io/grpc/Status.html): status code và RuntimeException mapping.
- [Google RPC — Error Details](https://cloud.google.com/apis/design/errors): google.rpc.Status và error details như RetryInfo/QuotaFailure.
- [Spring Framework — Task Execution](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): ThreadPoolTaskExecutor và task rejection.
- [OpenTelemetry — Metrics](https://opentelemetry.io/docs/concepts/signals/metrics/): theo dõi saturation, latency và error rate.

**Kết quả mong đợi:** Người học xử lý được RESOURCE_EXHAUSTED tại Spring gRPC service một cách nhất quán, phân biệt capacity/quota/payload limits, giới hạn concurrency và queue, truyền retry guidance phù hợp, tránh retry storm, áp dụng backpressure cho streaming, đồng thời đo lường và kiểm thử được saturation, permit cleanup và recovery.
