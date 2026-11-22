# Giới hạn executor và queue

## 1. Vì sao phải giới hạn executor và queue?

Trong Spring gRPC, mỗi RPC cần được dispatch tới callback hoặc service handler, sau đó có thể gọi database, HTTP client, broker hay một service khác. Nếu tất cả công việc dùng chung một executor không giới hạn, một đợt traffic tăng hoặc một dependency chậm có thể tạo ra rất nhiều task đang chờ. Bộ nhớ tăng, latency kéo dài và request mới tiếp tục được nhận dù hệ thống không còn khả năng xử lý.

Executor quyết định số task có thể chạy đồng thời và cách lập lịch. Queue giữ task chờ khi chưa có worker rảnh. Hai giới hạn cần được thiết kế cùng nhau:

- **Concurrency limit:** giới hạn số công việc chạy đồng thời.
- **Queue capacity:** giới hạn số công việc đang chờ.
- **Rejection policy:** quy định hành vi khi worker và queue đều đã đầy.
- **Deadline/cancellation:** ngăn task hết giá trị tiếp tục chiếm tài nguyên.
- **Backpressure:** điều tiết tốc độ nhận message khi producer nhanh hơn consumer.

Queue không giới hạn chỉ trì hoãn thời điểm quá tải lộ ra. Khi arrival rate vượt processing capacity trong thời gian đủ dài, queue sẽ tiếp tục tăng và làm cạn bộ nhớ.

## 2. Phân biệt các executor trong gRPC Java

Một ứng dụng gRPC có thể có nhiều nhóm công việc khác nhau:

| Executor/Thread group | Công việc | Rủi ro nếu bị block |
| --- | --- | --- |
| Netty event loop | I/O và transport events | Có thể làm chậm nhiều connection nếu chạy business logic blocking |
| gRPC server application executor | Dispatch listener/service callbacks | RPC khác phải chờ nếu callback bị block |
| gRPC client callback executor | Callback của client call | Response và completion callback bị trì hoãn |
| Business worker executor | Database, blocking HTTP, CPU work | Pool cạn làm queue tăng |
| Scheduled executor | Timeout, retry timer, housekeeping | Timer bị trễ nếu chạy tác vụ blocking |

Không dùng Netty event loop làm business executor. Không gọi database hoặc blocking HTTP trực tiếp trên event loop. Cũng không nên dùng một pool duy nhất cho callback gRPC, tác vụ blocking và công việc CPU nặng; một nhóm bị nghẽn có thể kéo theo toàn bộ hệ thống.

gRPC Java có thể nhận executor qua ServerBuilder/NettyServerBuilder và ManagedChannelBuilder. Nếu không cấu hình, runtime dùng executor mặc định theo implementation. Khi cần kiểm soát tải và thread naming, hãy cấu hình executor tường minh tại điểm tạo server/channel hoặc customizer mà Spring gRPC phiên bản dự án cung cấp.

Tránh dùng directExecutor() cho callback có thể block. Direct executor chạy callback trên thread gọi hoặc thread transport liên quan; một thao tác chậm có thể giữ thread cần thiết cho tiến trình RPC khác.

## 3. Core size, maximum size và queue capacity

Với ThreadPoolExecutor, thứ tự cấp worker thông thường là:

1. Tạo worker cho tới corePoolSize.
2. Khi core worker bận, đưa task vào queue.
3. Khi queue đầy, tăng worker vượt core tới maxPoolSize.
4. Khi đã đạt maxPoolSize và queue vẫn đầy, áp dụng rejection policy.

Điều này có nghĩa queue quá lớn có thể khiến pool không bao giờ tăng từ core lên maximum trong lúc latency đã tăng cao. Một queue nhỏ hơn giúp hệ thống phát hiện saturation sớm và mở rộng worker trong giới hạn đã đặt.

| Tham số | Ý nghĩa | Tác động |
| --- | --- | --- |
| corePoolSize | Số worker nền duy trì | Mức concurrency cơ sở |
| maxPoolSize | Số worker tối đa | Trần tài nguyên thread |
| queueCapacity | Số task chờ tối đa | Trần backlog và bộ nhớ |
| keepAliveSeconds | Thời gian worker vượt core được giữ khi idle | Điều chỉnh co giãn pool |
| rejection handler | Hành vi khi pool/queue đầy | Quyết định overload được phản hồi ra sao |

Ví dụ cấu hình ban đầu cho một nhóm tác vụ blocking có thể là 8 worker cơ sở, tối đa 24 worker và queue 128 task. Đây chỉ là điểm xuất phát; phải đo thời gian xử lý, số core, giới hạn connection pool và tải thực tế trước khi chốt.

## 4. Ước lượng capacity bằng tải và thời gian chờ

Một cách ước lượng concurrency là dùng định luật Little:

\[
L = \lambda W
\]

Trong đó:

- L là số request trung bình đang ở trong hệ thống.
- λ là throughput trung bình (request/giây).
- W là thời gian trung bình một request ở trong hệ thống (giây).

Ví dụ, nếu một dependency xử lý 200 request/giây và mỗi request mất trung bình 0,05 giây, số request đang xử lý trung bình xấp xỉ 10. Con số này giúp hình dung concurrency, không phải công thức trực tiếp để chọn corePoolSize vì còn phụ thuộc CPU, blocking, burst và phân phối latency.

Queue capacity nên gắn với thời gian chờ tối đa có thể chấp nhận. Một ước lượng ban đầu là:

\[
queueCapacity \approx arrivalRate \times maxQueueWait
\]

Nếu hệ thống nhận 400 task/giây và chỉ chấp nhận tối đa 0,1 giây chờ trước khi bắt đầu xử lý, queue khoảng 40 task là điểm thử ban đầu. Sau đó cần load test và điều chỉnh theo burst, memory footprint và deadline của RPC.

Không đặt queue hàng chục nghìn phần tử chỉ để tránh rejection. Một task chờ lâu có thể đã hết deadline trước khi được chạy; giữ nó trong queue chỉ làm tốn bộ nhớ và tăng độ trễ cho task còn hữu ích.

## 5. Cấu hình bounded executor trong Spring

Spring ThreadPoolTaskExecutor cho phép đặt core size, maximum size, queue capacity, tên thread và rejection handler. Ví dụ:

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class RpcExecutorConfiguration {

    @Bean
    ThreadPoolTaskExecutor grpcCallbackExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(16);
        executor.setQueueCapacity(128);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("grpc-callback-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean
    ThreadPoolTaskExecutor blockingWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(12);
        executor.setMaxPoolSize(24);
        executor.setQueueCapacity(96);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("grpc-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Spring quản lý lifecycle của ThreadPoolTaskExecutor bean và khởi tạo nó trong application context. Hai pool tách biệt để callback gRPC không bị chiếm hết worker bởi các thao tác blocking.

Không copy nguyên các con số trên vào production. Cần tính tới số replica, số CPU được cấp, giới hạn database connection, giới hạn downstream HTTP connection và số request đồng thời tối đa mà service có thể chịu.

## 6. Gắn executor vào gRPC server và channel

Với gRPC Java Netty transport, có thể gắn executor khi tạo server:

~~~java
import io.grpc.Server;
import io.grpc.netty.NettyServerBuilder;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class GrpcTransportConfiguration {

    @Bean(destroyMethod = "shutdown")
    Server catalogGrpcServer(
            @Qualifier("grpcCallbackExecutor")
            ThreadPoolTaskExecutor grpcCallbackExecutor,
            CatalogServiceImpl catalogService) throws IOException {
        return NettyServerBuilder.forPort(9090)
                .executor(grpcCallbackExecutor)
                .addService(catalogService)
                .build()
                .start();
    }
}
~~~

Đây là ví dụ khi ứng dụng tự quản lý Netty gRPC server. Nếu Spring gRPC đã tự tạo server, không tạo thêm server thứ hai; chuyển executor vào server builder/customizer mà phiên bản Spring gRPC đang dùng hỗ trợ. Cách đăng ký customizer và tên property có thể thay đổi theo phiên bản.

Client channel cũng có thể nhận executor cho callback:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress("catalog.internal", 9090)
        .useTransportSecurity()
        .executor(clientCallbackExecutor)
        .build();
~~~

Hãy quản lý channel và executor theo lifecycle của ứng dụng. Khi shutdown, dừng nhận RPC mới, chờ call đang chạy trong giới hạn thời gian, sau đó đóng channel/server và executor. Không tạo một pool hoặc channel mới cho từng RPC.

## 7. Không block gRPC callback: dispatch công việc có giới hạn

Nếu service cần gọi dependency blocking, có thể chuyển phần đó sang business worker executor. Phải capture gRPC Context trước khi rời callback thread để deadline, cancellation và các context value cần thiết vẫn có thể truy cập.

~~~java
import io.grpc.Context;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class CatalogServiceImpl
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final CatalogRepository repository;
    private final ThreadPoolTaskExecutor blockingWorkerExecutor;

    public CatalogServiceImpl(
            CatalogRepository repository,
            @Qualifier("blockingWorkerExecutor")
            ThreadPoolTaskExecutor blockingWorkerExecutor) {
        this.repository = repository;
        this.blockingWorkerExecutor = blockingWorkerExecutor;
    }

    @Override
    public void getItem(
            GetItemRequest request,
            StreamObserver<GetItemResponse> responseObserver) {

        Context rpcContext = Context.current();
        try {
            blockingWorkerExecutor.execute(rpcContext.wrap(() -> {
                if (rpcContext.isCancelled()) {
                    return;
                }
                try {
                    Item item = repository.findById(request.getItemId())
                            .orElseThrow(() ->
                                    Status.NOT_FOUND.asRuntimeException());

                    if (rpcContext.isCancelled()) {
                        return;
                    }

                    responseObserver.onNext(toResponse(item));
                    responseObserver.onCompleted();
                } catch (RuntimeException error) {
                    if (!rpcContext.isCancelled()) {
                        responseObserver.onError(error);
                    }
                }
            }));
        } catch (TaskRejectedException rejected) {
            responseObserver.onError(Status.RESOURCE_EXHAUSTED
                    .withDescription("Server is busy; retry later")
                    .asRuntimeException());
        }
    }
}
~~~

Ví dụ minh họa dispatch một unary operation. Trong ứng dụng thật, cần phân loại exception repository thành gRPC status phù hợp thay vì trả mọi lỗi dưới dạng INTERNAL/UNKNOWN; cũng cần xác định cancellation policy cho từng dependency. Context.wrap() giữ gRPC Context khi task chạy trên worker.

Khi queue đầy, AbortPolicy làm execute ném TaskRejectedException ở Spring. Service trả RESOURCE_EXHAUSTED để biểu thị server hiện không nhận thêm công việc. Client chỉ nên retry status này khi policy, backoff, deadline và semantics của method cho phép; retry đồng loạt không có giới hạn sẽ làm overload nặng hơn.

Không dùng CallerRunsPolicy một cách tùy tiện. Khi pool đầy, policy này chạy task ngay trên thread submit. Thread đó có thể là gRPC callback thread; nếu task blocking, callback và các RPC khác có thể bị nghẽn.

## 8. Queue đầy và rejection policy

Một bounded queue cần chính sách overload rõ ràng:

| Policy | Hành vi | Đánh giá cho RPC |
| --- | --- | --- |
| AbortPolicy | Ném rejection exception | Thường phù hợp để service chuyển thành RESOURCE_EXHAUSTED |
| CallerRunsPolicy | Thread submit tự chạy task | Có thể block gRPC callback/transport-related thread; chỉ dùng khi đã chứng minh an toàn |
| DiscardPolicy | Bỏ task mới | Không phù hợp với RPC vì request biến mất mà không có kết quả rõ |
| DiscardOldestPolicy | Bỏ task cũ nhất trong queue | Không phù hợp với request cần phản hồi; có thể làm mất thao tác đang chờ |

Với RPC, không âm thầm drop task. Nếu server từ chối vì quá tải, trả status rõ ràng, ghi metric và để client áp dụng backoff. Nếu task đã được nhận và đang xử lý, cancellation/deadline cần dừng công việc khi có thể.

Rejection không phải lỗi validation của caller. RESOURCE_EXHAUSTED phù hợp khi server hết capacity hoặc quota; UNAVAILABLE có thể được dùng theo contract cho một số tình huống service tạm thời không thể phục vụ. Chọn status nhất quán với API và retry policy.

## 9. Deadline và queue wait

Deadline của RPC bao gồm cả thời gian chờ trong queue, thời gian xử lý và thời gian truyền response. Nếu deadline còn 100 ms nhưng task phải chờ 500 ms trong queue, task đã hết giá trị trước khi bắt đầu.

Khi task được lấy khỏi queue:

1. Kiểm tra gRPC Context đã bị cancel hoặc deadline đã hết chưa.
2. Nếu đã hết, bỏ qua công việc và không gọi dependency.
3. Nếu còn thời gian, truyền deadline còn lại tới downstream call.
4. Khi dependency trả kết quả, kiểm tra cancellation trước khi phát response.

Không cấp một timeout đầy đủ mới cho mỗi dependency. Ngân sách thời gian của downstream phải nằm trong deadline còn lại của RPC cha.

Đối với tác vụ blocking không thể tự dừng ngay, đặt timeout ở database/HTTP client và dùng cancellation token hoặc interrupt hợp tác. Context cancellation không tự động giết thread đang block trong driver.

## 10. Queue không thay thế backpressure cho streaming

Với server-streaming hoặc bidirectional streaming, một producer có thể phát message nhanh hơn tốc độ client nhận. Nếu server đưa mọi message vào queue vô hạn, bộ nhớ tăng không giới hạn dù executor đã được giới hạn.

Cần kết hợp:

- Bounded queue cho dữ liệu chờ xử lý.
- gRPC flow control để giới hạn message được gửi/nhận.
- Kiểm tra ServerCallStreamObserver.isReady() trước khi phát outbound message.
- Đăng ký setOnReadyHandler() để tiếp tục drain khi transport sẵn sàng.
- Dừng producer và đóng subscription khi call bị cancel.

Ví dụ khung outbound server stream:

~~~java
ServerCallStreamObserver<OrderEvent> call =
        (ServerCallStreamObserver<OrderEvent>) responseObserver;

call.setOnReadyHandler(() -> {
    while (call.isReady() && !call.isCancelled()) {
        OrderEvent next = boundedEventQueue.poll();
        if (next == null) {
            break;
        }
        call.onNext(next);
    }
});
~~~

Đoạn code là khung minh họa; callback onReady và producer có thể chạy trên các thread khác nhau. Cần serialize việc drain, bảo đảm chỉ một writer gọi onNext và không phát sau terminal signal. Queue phải có capacity hữu hạn; khi đầy, producer cần dừng, chờ hoặc áp dụng chính sách overflow được contract cho phép.

Ở inbound streaming, server có thể tắt auto inbound flow control bằng disableAutoInboundFlowControl() trên ServerCallStreamObserver và gọi request(n) khi đã có capacity xử lý thêm message. Khi consumer hoàn tất một message, mới yêu cầu message tiếp theo. API cụ thể cần được đối chiếu với phiên bản gRPC Java đang dùng.

Queue capacity chỉ giới hạn backlog cục bộ; flow control mới điều tiết lượng message được phép chuyển qua stream. Hai cơ chế bổ sung cho nhau.

## 11. Bulkhead: tách pool theo loại công việc

Không nên để một dependency chậm chiếm hết worker phục vụ mọi RPC. Tách executor theo đặc tính tải:

| Pool | Công việc | Giới hạn bổ sung |
| --- | --- | --- |
| grpc-callback | Callback/dispatch RPC | Task ngắn, không blocking |
| database-worker | Truy vấn database blocking | Không vượt connection pool và DB capacity |
| http-worker | HTTP client blocking | Không vượt max connection và downstream quota |
| cpu-worker | Mã hóa, nén hoặc tính toán | Gần với số CPU khả dụng |
| stream-worker | Xử lý event stream | Queue nhỏ, flow control và cancellation |

Bulkhead ngăn sự cố một dependency lan sang toàn bộ RPC server. Tuy nhiên, mỗi pool vẫn cần bounded queue, rejection policy, deadline và metric riêng. Tách pool không làm tăng tổng capacity của database hoặc downstream.

## 12. Quan sát executor và queue

Các metric nên theo dõi theo từng pool:

| Metric | Ý nghĩa |
| --- | --- |
| active workers | Số worker đang chạy task |
| pool size / max pool size | Kích thước hiện tại và giới hạn |
| queue size | Số task đang chờ |
| queue remaining capacity | Dung lượng queue còn lại |
| task rejected | Số task bị từ chối |
| task wait duration | Thời gian từ submit tới lúc bắt đầu chạy |
| task execution duration | Thời gian thực thi |
| deadline expired before start | Task hết deadline khi còn ở queue |
| cancelled queued/running tasks | Task bị hủy trước hoặc trong khi xử lý |

Đặt tên pool làm label vì số pool hữu hạn. Không dùng request ID, tenant ID hoặc user ID làm metric label.

Một dashboard cần hiển thị queue depth cùng latency và rejection. Queue tăng liên tục, wait duration tăng và active worker chạm max là dấu hiệu saturation. Nếu queue thấp nhưng rejection cao, kiểm tra burst, queue capacity, executor sharing và thời gian xử lý.

## 13. Kiểm thử saturation và overload

Không chỉ test throughput khi tải thấp. Hãy chủ động đưa executor tới giới hạn:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Tải thấp, dependency phản hồi nhanh | Latency ổn định, queue gần rỗng |
| Tải tăng vượt core pool | Queue tăng nhưng vẫn trong capacity |
| Queue đầy, pool tăng tới max | Không tạo thêm worker vượt giới hạn |
| Queue và pool đều đầy | Request mới nhận status overload rõ ràng |
| Task hết deadline khi đang chờ | Không gọi dependency sau khi task được dequeue |
| Caller cancel task đang chạy | Công việc dừng hợp tác, không phát response muộn |
| Dependency chậm | Pool dependency bị giới hạn, pool callback vẫn phục vụ RPC khác |
| Streaming producer nhanh hơn client | Flow control/bounded queue giữ memory trong giới hạn |
| Shutdown ứng dụng | Không còn task hoặc thread ngoài lifecycle dự kiến |

Trong test, dùng latch để giữ worker bận và lấp queue có kiểm soát; không dùng sleep cố định làm đồng bộ. Assert số task active, queue size, rejection count và gRPC status. Chạy load test với latency distribution và burst gần với production.

## 14. Sai lầm thường gặp

1. **Dùng queue không giới hạn.** Backlog có thể làm cạn bộ nhớ và kéo dài latency.
2. **Tăng queue để che giấu thiếu capacity.** Request có thể hết deadline trước khi được xử lý.
3. **Chỉ đặt corePoolSize mà bỏ qua maxPoolSize/queueCapacity.** Không hiểu đúng thứ tự queue và mở rộng worker.
4. **Dùng directExecutor cho service blocking.** Có thể block thread cần cho RPC/transport.
5. **Dùng CallerRunsPolicy không đánh giá thread submit.** Callback thread có thể bị kéo vào tác vụ chậm.
6. **Âm thầm discard request.** Caller không nhận kết quả rõ ràng và không thể reconciliation.
7. **Dùng một pool cho mọi dependency.** Một downstream chậm có thể chiếm hết worker.
8. **Coi bounded queue là backpressure.** Streaming vẫn cần gRPC flow control và kiểm soát producer.
9. **Không kiểm tra deadline/cancellation trước khi xử lý task chờ.** Công việc đã hết giá trị vẫn tiêu thụ tài nguyên.
10. **Không đo queue wait và rejection.** Chỉ nhìn CPU có thể bỏ lỡ saturation.

## 15. Bài tập vận dụng

Với CatalogService trong Spring gRPC:

1. Tạo callback executor và blocking worker executor riêng, cả hai đều có queue capacity hữu hạn.
2. Gắn callback executor vào gRPC server/channel builder theo cơ chế của phiên bản Spring gRPC dự án.
3. Dispatch truy vấn blocking sang worker pool bằng gRPC Context wrap.
4. Dùng AbortPolicy và chuyển rejection thành RESOURCE_EXHAUSTED.
5. Tạo tải vượt core size, lấp queue và xác minh pool không vượt max size.
6. Đặt deadline ngắn, để task chờ trong queue rồi xác minh task hết hạn không gọi database.
7. Với server-streaming, dùng bounded queue và onReady flow để không phát nhanh hơn transport.
8. Thu thập queue depth, wait duration, execution duration và rejection count; xác định ngưỡng cảnh báo.

**Tiêu chí hoàn thành:** người học cấu hình được executor và queue có giới hạn, giải thích được core/max/queue/rejection, không block callback/transport thread, truyền deadline/cancellation sang worker, áp dụng backpressure cho streaming và kiểm thử được hành vi khi saturation.

### Tài liệu tham khảo

- [gRPC Java ServerBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): cấu hình executor cho server.
- [gRPC Java ManagedChannelBuilder API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): cấu hình executor cho client channel.
- [Java ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/): worker, queue và rejection policy.
- [Spring ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): cấu hình executor trong Spring.
- [gRPC Flow Control](https://grpc.io/docs/guides/flow-control/): điều tiết message trong streaming RPC.
- [gRPC Deadlines](https://grpc.io/docs/guides/deadlines/): deadline và ngân sách thời gian của RPC.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
