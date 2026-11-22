# Virtual thread và giới hạn theo workload

**Virtual thread** giúp xử lý nhiều tác vụ blocking đồng thời với chi phí thread thấp hơn platform thread. Trong Spring gRPC, có thể dùng virtual thread làm executor cho service implementation khi handler thường chờ JDBC, HTTP client hoặc blocking gRPC stub. Tuy nhiên, virtual thread không làm CPU nhanh hơn và không tăng số connection database, năng lực downstream hay giới hạn tài nguyên của hệ thống.

Thiết kế phù hợp gồm hai phần: dùng virtual thread để giảm chi phí chờ I/O, đồng thời đặt **giới hạn concurrency theo workload và tài nguyên thực**. Nếu thay một thread pool hữu hạn bằng virtual-thread-per-task rồi để request vào không giới hạn, hệ thống vẫn có thể cạn connection, bộ nhớ hoặc capacity của service downstream.

## 1. Virtual thread hoạt động như thế nào?

Platform thread thường gắn với một OS thread trong phần lớn vòng đời. Virtual thread là thread do JVM quản lý; khi nó chờ ở thao tác blocking được hỗ trợ, JVM có thể unmount virtual thread khỏi carrier thread để carrier chạy tác vụ khác. Khi thao tác sẵn sàng tiếp tục, virtual thread được mount lại.

~~~mermaid
flowchart TD
    A["RPC handler chạy trên virtual thread"] --> B{"Có thao tác blocking?"}
    B -->|"Không"| C["Tiếp tục chạy trên carrier"]
    B -->|"Có, hỗ trợ unmount"| D["Virtual thread tạm unmount"]
    D --> E["Carrier chạy virtual thread khác"]
    E --> F["I/O sẵn sàng"]
    F --> G["Virtual thread được mount lại"]
    G --> H["Handler tiếp tục"]
~~~

Điều này phù hợp với code kiểu tuần tự:

~~~java
Order order = orderRepository.findById(orderId);
Inventory inventory = inventoryClient.check(order);
return toResponse(order, inventory);
~~~

Handler có thể chờ database rồi chờ service tồn kho mà không cần giữ một platform thread riêng trong suốt thời gian chờ, miễn là các thư viện I/O và điểm blocking cho phép JVM unmount virtual thread.

Virtual thread không phải một OS thread nhẹ hơn được tạo trực tiếp. JVM lập lịch nhiều virtual thread lên một số carrier platform thread. CPU-bound work vẫn cần CPU; khi tất cả carrier bận tính toán, virtual thread khác không thể làm CPU chạy nhanh hơn.

## 2. Dùng virtual-thread-per-task làm server executor

Từ Java 21, tạo executor bằng Executors.newVirtualThreadPerTaskExecutor():

~~~java
ExecutorService grpcVirtualExecutor =
    Executors.newVirtualThreadPerTaskExecutor();

Server server = ServerBuilder.forPort(9090)
    .executor(grpcVirtualExecutor)
    .addService(new OrderServiceImpl())
    .build()
    .start();
~~~

ServerBuilder.executor(Executor) nhận executor để chạy application call. Với server được Spring starter tạo tự động, cần nối executor này qua customizer/configurer hoặc extension point mà đúng phiên bản starter hỗ trợ. Chỉ tạo bean executor mà không gắn nó vào server builder sẽ không thay đổi thread chạy service implementation.

Không tạo executor mới trong mỗi RPC. Một executor per-task được quản lý ở cấp application/server và tái sử dụng như một thành phần hạ tầng.

## 3. Quản lý vòng đời bằng Spring

Executor cần được đóng theo vòng đời server. Ví dụ khai báo bean:

~~~java
@Configuration
public class GrpcThreadConfiguration {

    @Bean(destroyMethod = "shutdown")
    ExecutorService grpcVirtualExecutor() {
        return Executors.newVirtualThreadPerTaskExecutor();
    }
}
~~~

Bean phải được truyền vào nơi cấu hình server builder của starter. Khi ứng dụng dừng, nên ngừng nhận RPC mới, cho server hoàn tất các call đang chạy trong grace period, rồi shutdown executor. Nếu executor bị shutdown trước khi server ngừng dispatch callback, request mới có thể bị reject trong giai đoạn shutdown.

Với cấu hình server tự tạo, có thể thể hiện quan hệ phụ thuộc bằng constructor injection:

~~~java
@Bean
Server grpcServer(
        ExecutorService grpcVirtualExecutor,
        OrderServiceImpl orderService) throws IOException {
    return ServerBuilder.forPort(9090)
        .executor(grpcVirtualExecutor)
        .addService(orderService)
        .build()
        .start();
}
~~~

Ví dụ này minh họa server gRPC Java thuần được quản lý bởi Spring. Nếu starter đã quản lý server lifecycle, hãy dùng extension point của starter thay vì tạo thêm một server thứ hai.

## 4. Workload nào phù hợp với virtual thread?

Virtual thread phát huy tác dụng nhất khi nhiều request đồng thời dành phần lớn thời gian chờ I/O:

| Workload | Mức phù hợp | Lý do và giới hạn |
| --- | --- | --- |
| JDBC hoặc repository blocking | Phù hợp | Thread chờ có thể unmount; số connection vẫn bị giới hạn bởi pool database |
| HTTP client blocking | Phù hợp | Có thể giữ code tuần tự dễ đọc; cần connection/request timeout và giới hạn concurrency |
| Blocking gRPC stub | Phù hợp | Caller virtual thread có thể chờ response; downstream vẫn có capacity hữu hạn |
| CPU-bound transform | Không tăng throughput chỉ nhờ virtual thread | CPU và carrier vẫn hữu hạn; nên dùng bounded CPU executor |
| Stream xử lý liên tục | Phụ thuộc cách triển khai | Tránh giữ virtual thread trong vòng chờ vô hạn; dùng callback, backpressure và giới hạn phiên |
| Tác vụ nền dài | Cần tách biệt | Có queue, admission control và lifecycle riêng để không chiếm capacity của RPC tương tác |

Đừng chuyển toàn bộ code sang virtual thread chỉ vì có thể. Đo workload trước, sau đó chọn executor cho phần blocking và executor giới hạn cho phần CPU-bound hoặc công việc cần điều tiết tải.

## 5. Virtual thread không thay thế giới hạn tài nguyên

Executors.newVirtualThreadPerTaskExecutor() tạo virtual thread mới cho mỗi task được submit và không áp một giới hạn concurrency nghiệp vụ. Virtual thread rẻ hơn platform thread nhưng vẫn dùng heap, stack state, object và tài nguyên bên ngoài.

Ví dụ, nếu 5.000 RPC cùng chờ database trong khi connection pool chỉ có 40 connection, phần lớn request vẫn phải xếp hàng ở pool. Virtual thread giúp chi phí thread chờ thấp hơn; nó không làm database xử lý 5.000 query đồng thời.

Giới hạn phải đặt tại nơi tài nguyên thực sự hữu hạn:

- Database connection pool và số query đồng thời.
- HTTP connection pool, rate limit và downstream capacity.
- Số tác vụ CPU chạy đồng thời.
- Số stream/subscription và queue dữ liệu.
- Số RPC được phép admission vào service theo tenant hoặc method.

## 6. Dùng bulkhead để giới hạn workload blocking

Có thể dùng Semaphore để giới hạn số request cùng lúc truy cập một tài nguyên đắt:

~~~java
private final Semaphore databasePermits = new Semaphore(32);

public Order loadOrder(String orderId) {
    if (!databasePermits.tryAcquire()) {
        throw Status.RESOURCE_EXHAUSTED
            .withDescription("database concurrency limit reached")
            .asRuntimeException();
    }

    try {
        return orderRepository.findRequired(orderId);
    } finally {
        databasePermits.release();
    }
}
~~~

32 chỉ là giá trị minh họa. Chọn giới hạn dựa trên connection pool, số instance, tải nền và năng lực database. Nếu mỗi instance cho phép 32 query nhưng có 10 instance, database có thể nhận tới 320 query đồng thời; cần tính capacity ở phạm vi toàn hệ thống.

Bulkhead nên nằm quanh tài nguyên cần bảo vệ và phải release permit trong finally. Nếu muốn chờ permit, hãy giới hạn thời gian chờ theo deadline còn lại; không để virtual thread chờ semaphore vô hạn. Khi không thể nhận thêm việc, trả status overload phù hợp hoặc áp dụng admission control ở tầng trước.

## 7. Giới hạn CPU-bound bằng executor riêng

CPU-bound work như tính toán báo cáo, nén dữ liệu hoặc xử lý ảnh không trở nên nhanh hơn chỉ vì chạy trên virtual thread. Có thể chuyển phần tính toán sang pool platform thread hữu hạn:

~~~java
@Bean(destroyMethod = "shutdown")
ExecutorService cpuExecutor() {
    int cores = Runtime.getRuntime().availableProcessors();
    return Executors.newFixedThreadPool(Math.max(1, cores));
}
~~~

Khi handler cần chạy CPU task, submit vào executor riêng và giới hạn số task đang chờ. Không tạo queue không giới hạn cho CPU work; queue dài sẽ làm latency tăng và deadline hết trước khi task được chạy. Nếu công việc có thể chia chunk, kiểm tra cancellation giữa các chunk để dừng sớm.

## 8. Truyền gRPC Context khi offload tác vụ

gRPC gắn context của RPC với callback service. Khi code chủ động submit công việc sang executor khác, cần capture context để deadline và cancellation tiếp tục có hiệu lực:

~~~java
Context rpcContext = Context.current();

Future<Report> task = cpuExecutor.submit(
    rpcContext.wrap(() -> buildReport(request)));

rpcContext.addListener(
    ignored -> task.cancel(true),
    cleanupExecutor);
~~~

Context.wrap(...) gắn context đã capture khi task chạy. Listener nối cancellation với Future.cancel(true), nhưng tác vụ CPU cũng nên kiểm tra interrupt hoặc trạng thái context tại các điểm an toàn. Không giả định deadline hết sẽ tự interrupt mọi virtual thread.

Với downstream gRPC call được tạo từ task offload, context đúng giúp deadline cha tiếp tục giới hạn call con. Nếu tác vụ nền độc lập cần sống sau RPC, hãy tạo workflow riêng với deadline/lifecycle riêng thay vì giữ context của request đã kết thúc.

## 9. Pinning và thư viện blocking

Virtual thread cần carrier thread để chạy. Một số thao tác blocking có thể giữ carrier thay vì unmount virtual thread; hiện tượng này gọi là **pinning**.

- Trên JDK 21–23, blocking khi giữ monitor synchronized có thể pin carrier trong một số tình huống.
- Từ JDK 24, thay đổi trong JVM đã loại bỏ phần lớn pinning do monitor synchronized; tuy nhiên native/foreign calls và một số tình huống runtime vẫn có thể giữ carrier.
- Thư viện cũ, driver hoặc native code có thể có hành vi blocking không tối ưu cho virtual thread.

Không nên thay mọi synchronized bằng lock khác một cách máy móc. Trước hết đo bằng JFR và kiểm tra stack trace. Nếu một vùng critical section thực hiện I/O blocking, hãy xem lại phạm vi lock và tránh giữ lock trong suốt thời gian chờ.

Có thể dùng Java Flight Recorder để quan sát sự kiện jdk.VirtualThreadPinned và các khoảng chờ. Kiểm thử bằng đúng JDK production đang chạy; hành vi virtual thread có thể khác giữa các phiên bản Java.

## 10. ThreadLocal, logging và context propagation

Virtual thread hỗ trợ ThreadLocal, nhưng mô hình per-task khác thread pool truyền thống:

- Không dựa vào việc một thread được tái sử dụng giữa nhiều request.
- Tránh lưu object lớn hoặc tài nguyên cần đóng trong ThreadLocal.
- Dọn dữ liệu ThreadLocal do ứng dụng đặt khi task kết thúc nếu vòng đời có thể kéo dài hoặc tài nguyên cần giải phóng.
- MDC và trace context dựa trên ThreadLocal cần được tích hợp với cơ chế context propagation của logging/tracing.
- gRPC Context là cơ chế riêng; đừng giả định MDC, Spring Security context và gRPC Context tự truyền qua mọi executor.

Đặt trace ID, tenant và thông tin request trong context phù hợp; dùng wrapper/decorator khi chuyển executor. Không dùng tên thread làm định danh request hoặc giả định thread identity ổn định qua callback.

## 11. Deadline và cancellation với virtual thread

Virtual thread giúp chờ blocking rẻ hơn nhưng không làm request được phép chờ vô hạn. Vẫn cần deadline hữu hạn trên client và propagation qua nested call. Khi context bị cancelled:

1. Dừng bắt đầu bước downstream mới.
2. Hủy future hoặc call handle nếu API hỗ trợ.
3. Đặt query timeout hoặc gọi cancel trên JDBC statement nếu driver hỗ trợ.
4. Đóng HTTP request, stream hoặc subscription phù hợp.
5. Giải phóng semaphore permit và tài nguyên trong finally.

Future.cancel(true) có thể interrupt virtual thread đang chạy, nhưng tác vụ chỉ dừng nhanh nếu code và thư viện phản ứng với interrupt. Cancellation không rollback transaction đã commit; command có side effect vẫn cần idempotency key hoặc operation ID.

## 12. Kiểm thử và quan sát theo workload

Kiểm thử nên bao gồm:

- Nhiều RPC blocking đồng thời: virtual thread tăng nhưng database concurrency vẫn nằm trong giới hạn.
- CPU load cao: CPU executor không vượt số worker đã định.
- Downstream chậm: deadline/cancellation dừng task và giải phóng permit.
- Queue/admission limit đầy: service trả overload có kiểm soát thay vì tạo task vô hạn.
- Context offload: deadline và cancellation vẫn hiện diện trong task.
- Shutdown Spring: server ngừng nhận RPC trước khi executor đóng.
- JDK production: không có pinning kéo dài hoặc native call giữ carrier bất thường.

Theo dõi:

- Số virtual thread đang sống và số RPC đang hoạt động.
- Số permit đang dùng, thời gian chờ permit và số request bị từ chối.
- Database/HTTP pool utilization và thời gian chờ connection.
- CPU, carrier utilization, GC và heap.
- JFR pinning events, stack trace của virtual thread bị block.
- Deadline status, cancellation và task còn chạy sau khi RPC kết thúc.

Đánh giá theo từng workload. Nếu virtual thread tăng nhưng throughput không tăng, nút thắt có thể là database, downstream, CPU hoặc giới hạn admission; tăng số virtual thread không giải quyết được nút thắt đó.

## 13. Ghi nhớ và tự kiểm tra

**Virtual thread phù hợp với handler blocking I/O có concurrency cao; giới hạn workload vẫn phải dựa trên tài nguyên thực.** Dùng virtual-thread-per-task cho service executor khi phù hợp, quản lý lifecycle bằng Spring, tách CPU-bound work sang pool hữu hạn, đặt bulkhead cho database/downstream, truyền gRPC Context khi offload và quan sát pinning trên JDK production.

Tự kiểm tra:

1. Vì sao virtual thread giúp giảm chi phí chờ I/O nhưng không tăng tốc CPU-bound work?
2. Điều gì có thể xảy ra nếu dùng virtual-thread-per-task mà không có admission control?
3. Vì sao số virtual thread đồng thời không được dùng làm giới hạn thay cho database connection pool?
4. Khi offload task sang executor khác, cần làm gì để giữ deadline và cancellation?
5. Pinning là gì, và cần quan sát điều gì trên JDK đang triển khai?

Kết hợp virtual thread với bulkhead, giới hạn concurrency và deadline giúp Spring gRPC xử lý nhiều request blocking mà vẫn bảo vệ database, downstream và độ ổn định của toàn hệ thống.
