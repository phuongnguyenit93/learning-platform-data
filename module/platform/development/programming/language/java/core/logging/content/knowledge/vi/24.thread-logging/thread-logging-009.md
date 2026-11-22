# Định danh worker trong logging đa luồng Java

## 1. Định danh worker là gì?

Trong ứng dụng Java có nhiều công việc chạy đồng thời, log của các tác vụ thường xen kẽ nhau. Ví dụ một dịch vụ gửi email có hai worker xử lý các job khác nhau, trong khi các worker đó liên tục nhận công việc mới từ hàng đợi. Nếu log chỉ ghi “Bắt đầu xử lý” hay “Xử lý xong”, người vận hành khó biết dòng nào thuộc worker và job nào.

**Worker identity (định danh worker)** là tên hoặc mã dùng để nhận biết **một đơn vị đảm nhiệm xử lý công việc** theo mô hình của ứng dụng. Worker có thể là:

- Một **worker thread** trong Java thread pool.
- Một **consumer logic** nhận message từ Kafka, RabbitMQ hay queue nội bộ.
- Một **background worker process** hoặc một instance chạy batch job.
- Một **worker logic** có vòng đời độc lập với thread cụ thể đang thực thi.

Cần xác định chính xác ý nghĩa của trường **workerId** trong từng hệ thống. Trong một thread pool đơn giản, workerId có thể ánh xạ sang threadName. Trong ứng dụng phức tạp, một worker logic có thể được thực thi trên nhiều thread nên workerId phải do ứng dụng cấp riêng.

Ví dụ các dòng log minh họa:

~~~text
service=email instance=pod-a worker=email-worker-1 task=mail-101 attempt=1 event=start
service=email instance=pod-a worker=email-worker-2 task=mail-102 attempt=1 event=start
service=email instance=pod-a worker=email-worker-1 task=mail-101 attempt=1 event=done
~~~

Nhờ có nhiều trường, ta biết **worker nào** xử lý, **công việc nào** được xử lý và **lần thử thứ mấy**. Worker ID một mình không đủ để theo dõi toàn bộ vòng đời của một job.

## 2. Phân biệt worker ID, thread ID và task ID

| Trường | Nhận diện điều gì? | Phạm vi và ý nghĩa |
| --- | --- | --- |
| **serviceName** | Dịch vụ tạo log | Tên dịch vụ, chẳng hạn order-service |
| **instanceId** | Một JVM/container/pod đang chạy | Phân biệt các bản sao cùng dịch vụ |
| **workerId** | Một worker logic hoặc một worker thread | Phụ thuộc định nghĩa của ứng dụng; thường ổn định trong đời worker |
| **threadName** | Tên Java Thread hiện tại | Có thể tùy biến, có thể trùng hoặc đổi tên |
| **threadId** | ID của Java Thread | Chỉ phục vụ nhận diện thread trong phạm vi JVM, không bền qua restart |
| **taskId / jobId** | Một công việc logic | Giữ nguyên khi cùng job được retry nếu hợp đồng yêu cầu |
| **attemptId / attemptNo** | Một lần thực thi của công việc | Phân biệt lần thử đầu và các lần retry |
| **requestId / correlationId** | Một yêu cầu hoặc luồng nghiệp vụ | Dùng liên kết log qua nhiều thành phần |
| **traceId / spanId** | Trace phân tán và một span cụ thể | Phục vụ truy vết quan hệ giữa các thao tác khi có tracer |

Điểm cốt lõi: **workerId trả lời “ai xử lý?”, taskId trả lời “đang xử lý gì?”, traceId trả lời “thuộc chuỗi xử lý nào?”**.

Giả sử thread **worker-1** xử lý lần lượt job A và job B. Nếu chỉ tra theo threadName, kết quả chứa cả hai job. Nếu job A bị chuyển sang worker-2 để retry thì cùng một taskId có thể xuất hiện trên nhiều workerId. Đây là hành vi bình thường; không thể suy ra taskId từ workerId.

### Có phải Thread luôn là worker?

Không. Một chương trình Java đơn giản có thể coi thread trong pool là worker. Nhưng trong hệ thống consumer hoặc actor, một worker logic có thể tiếp tục tồn tại khi callback chuyển thread. Ngoài ra, với Java virtual threads, một thread thường được tạo cho từng tác vụ, còn “worker” nghiệp vụ có thể sống lâu hơn.

Do đó trước khi tạo schema log, phải xác định **vòng đời và trách nhiệm** của worker thay vì lấy tên thread làm quy tắc cho mọi loại ứng dụng.

## 3. Nhận diện và đặt tên thread trong Java

Trong Java 17, có thể xem thông tin thread đang chạy:

~~~java
Thread thread = Thread.currentThread();
String name = thread.getName();
long id = thread.getId();
~~~

**getName()** trả về tên có thể cấu hình. **getId()** trả về ID thread do JVM cấp, hữu ích để chẩn đoán trong tiến trình nhưng không phải khóa toàn cục giữa nhiều JVM hoặc qua khởi động lại. Java 21+ có API **threadId()**; nó cũng nhận diện thread, không tạo định danh nghiệp vụ cho worker.

Khi tạo thread pool do ứng dụng sở hữu, nên dùng **ThreadFactory** để đặt tên có ý nghĩa như **invoice-worker-1**, **invoice-worker-2**. Tên mặc định của framework có thể đủ cho debug nhưng thường không chứa ngữ cảnh nghiệp vụ. Tuy nhiên tên tự đặt chỉ duy nhất trong phạm vi bạn thiết kế: hai JVM cùng đặt tên **invoice-worker-1** vẫn là hai worker khác nhau.

Nếu cần nhận diện chính xác worker xuyên instance, hãy sử dụng **serviceName + instanceId + workerId** hoặc cấp ID duy nhất toàn hệ thống. Tránh dùng threadName như khóa bản ghi nghiệp vụ.

## 4. Ví dụ Java 17 chạy độc lập: một worker xử lý nhiều task

Ví dụ sau minh họa đồng thời ba điều:

1. **ThreadFactory** đặt tên worker thread.
2. **ThreadLocal** chứa taskId gắn với lần xử lý hiện tại.
3. **finally** dọn context để worker thread được tái sử dụng an toàn.

Tạo file **WorkerLoggingDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public class WorkerLoggingDemo {
    private static final ThreadLocal<String> TASK_ID = new ThreadLocal<>();

    private static ThreadFactory namedWorkers(String prefix) {
        AtomicInteger sequence = new AtomicInteger(1);
        return action -> new Thread(
                action, prefix + sequence.getAndIncrement());
    }

    private static void log(String event) {
        System.out.printf(
                "worker=%s task=%s event=%s%n",
                Thread.currentThread().getName(),
                TASK_ID.get(),
                event);
    }

    private static void process(String taskId) {
        TASK_ID.set(taskId);
        try {
            log("start");
            // Vi tri xu ly nghiep vu thuc te.
            log("done");
        } finally {
            TASK_ID.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor =
                Executors.newSingleThreadExecutor(
                        namedWorkers("email-worker-"));
        try {
            executor.submit(() -> process("mail-101")).get();
            executor.submit(() -> process("mail-102")).get();
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac WorkerLoggingDemo.java
java WorkerLoggingDemo
~~~

Stdout chính xác khi chương trình thành công:

~~~text
worker=email-worker-1 task=mail-101 event=start
worker=email-worker-1 task=mail-101 event=done
worker=email-worker-1 task=mail-102 event=start
worker=email-worker-1 task=mail-102 event=done
~~~

Vì chương trình dùng **newSingleThreadExecutor** và chờ **Future.get()** sau mỗi lần submit, các dòng log xuất hiện theo thứ tự trên. Worker thread **email-worker-1** được tái sử dụng; task ID đổi từ **mail-101** sang **mail-102**.

Trong hệ thống thực, **done** chỉ được ghi khi tác vụ hoàn tất thành công. Nếu lỗi, log exception và thông tin task tương ứng rồi cho ngoại lệ được xử lý theo hợp đồng job. **TASK_ID.remove()** trong finally vẫn phải chạy dù thành công hay thất bại.

Nếu đổi sang **newFixedThreadPool(2, namedWorkers("email-worker-"))**, tối đa hai worker thread có thể chạy đồng thời; thứ tự dòng log có thể khác giữa các lần chạy. Đừng xây dựng test dựa vào thứ tự log của các task song song. **ThreadFactory** giữ quy tắc đặt tên, còn **taskId** là chìa khóa để tìm log của từng công việc.

## 5. Khi worker là thực thể logic, không phải thread

Xét một consumer logic có workerId **orders-consumer-3**. Consumer nhận message và chuyển việc thực thi sang executor. Lúc đó log có thể gồm:

~~~text
workerId=orders-consumer-3 threadName=broker-io-4 taskId=order-582 attempt=1
workerId=orders-consumer-3 threadName=orders-pool-2 taskId=order-582 attempt=1
~~~

Worker logic không đổi, nhưng thread khác. Nếu hệ thống đặt **workerId = Thread.currentThread().getName()** tại từng thời điểm, sẽ vô tình coi hai thread là hai worker khác nhau.

Cách quản lý đúng:

- **Tạo worker logic:** cấp workerId lúc khởi tạo và giữ nó trong trạng thái của worker, object hoặc context được quản lý.
- **Nhận task:** trích xuất taskId từ job/message; nếu có retry thì xác định attemptId hoặc attemptNo.
- **Bắt đầu xử lý:** đặt workerId và taskId vào logging context của luồng thực thi hiện tại.
- **Chuyển sang callback/executor:** truyền thông tin logic cần thiết một cách tường minh hoặc qua cơ chế propagation của framework.
- **Kết thúc:** khôi phục hoặc xóa context của task; tránh để workerId/taskId từ công việc cũ lây sang công việc mới.

Một worker logic có thể bị thay thế khi deployment, restart hoặc rebalance consumer group. Nếu yêu cầu theo dõi vòng đời từng thực thể, workerId mới nên thể hiện đời worker mới; nếu cần một ID ổn định cho một vai trò logic, dùng thêm trường **workerRole** hoặc **consumerGroup**. Không bắt một field đại diện cả danh tính thực thể lẫn vai trò bền vững.

## 6. Ghi worker ID qua SLF4J MDC và Logback

Trong Java application sử dụng SLF4J với logging provider hỗ trợ MDC, **Mapped Diagnostic Context (MDC)** là kho các cặp key/value gắn với phạm vi log hiện tại. Thay vì ghép workerId và taskId vào từng message, ứng dụng đặt chúng vào MDC, sau đó logger đưa các trường vào log.

Đây là **trích đoạn tích hợp** cần SLF4J; không phải chương trình JDK chạy độc lập:

~~~java
import java.util.Map;
import org.slf4j.MDC;

static void withWorkerContext(
        String workerId, String taskId, Runnable work) {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        MDC.put("workerId", workerId);
        MDC.put("taskId", taskId);
        work.run();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
}
~~~

Ví dụ lời gọi trong phần xử lý worker:

~~~java
withWorkerContext("orders-consumer-3", "order-582", () -> {
    logger.info("Processing started");
    handleOrder();
    logger.info("Processing succeeded");
});
~~~

Một pattern Logback có thể gồm:

~~~text
%d{ISO8601} %-5level [%thread] worker=%X{workerId} task=%X{taskId} trace=%X{traceId} %logger - %msg%n
~~~

**MDC không phải worker ID generator.** Nó chỉ giúp các log trong cùng scope đọc được context đã đặt. WorkerId cần được tạo hoặc cung cấp từ mô hình thực thi của hệ thống trước khi đưa vào MDC.

Ví dụ đã lưu **previous** trước khi sửa MDC, nên khôi phục trạng thái cũ trong finally. Nếu chỉ gọi **MDC.clear()** mà không kiểm tra context đã tồn tại, một thư viện hoặc callback lồng nhau có thể xóa nhầm các trường do bên gọi sở hữu. Nếu thư viện chỉ quản lý một số key, có thể bảo toàn và khôi phục riêng các key đó.

Ứng dụng có thể ghi log JSON với thuộc tính **workerId**, **instanceId**, **taskId**, **attemptNo**, **traceId**, **event**; đây là lựa chọn thuận tiện cho truy vấn theo field. Thống nhất tên khóa giữa các service và giữa các môi trường.

## 7. Executor và nguy cơ mất context hoặc nhiễm log

**ThreadLocal** và nhiều triển khai MDC gắn với thread đang chạy. Khi thread HTTP gọi **executor.submit()**, các trường trong thread gửi không tự động chuyển sang thread pool. Nếu worker nhận task A rồi task B trên cùng thread, một context không được dọn sau A sẽ gây **context leakage**: log B nhầm ID của A.

Cơ chế nền tảng là **capture → activate → restore**. Ví dụ chỉ truyền **requestId** qua ranh giới executor:

~~~java
String capturedRequestId = MDC.get("requestId");

executor.execute(() -> {
    String previousRequestId = MDC.get("requestId");
    try {
        if (capturedRequestId == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", capturedRequestId);
        }
        processTask();
    } finally {
        if (previousRequestId == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previousRequestId);
        }
    }
});
~~~

Đây là **mã minh họa tích hợp**, giả sử **executor** và **processTask()** đã được khai báo và có thư viện SLF4J. Nó truyền đúng một field requestId; **không truyền toàn bộ trace context**, **không tạo span**, và **không tạo workerId**.

Trong ứng dụng thực, nên sử dụng **TaskDecorator**, wrapper Executor hoặc thư viện context propagation tương thích với stack hiện có. Với distributed tracing, dùng propagator/tracer chính thức để mang đúng trace/span context và quản lý scope. Không coi việc copy một chuỗi traceId vào MDC là đã triển khai distributed tracing.

**InheritableThreadLocal** không phải giải pháp chung cho thread pool: worker thread thường được tạo trước rồi sống lâu, vì vậy giá trị kế thừa khi tạo thread không tự thay đổi theo từng task sau đó.

## 8. Định danh worker khi xử lý đồng thời và virtual threads

Ở **fixed thread pool**, cùng một worker thread có thể xử lý nhiều task tuần tự. Nhiều worker thread chạy song song sẽ khiến thứ tự dòng log không cố định. Khi phân tích, lọc theo taskId hoặc traceId thay vì dựa hoàn toàn timestamp.

Ở **ForkJoinPool**, callback hoặc **CompletableFuture**, tác vụ có thể chuyển sang thread khác, và tên thread có thể là tên worker chung của framework. WorkerId logic chỉ đáng tin nếu được mang theo task/consumer.

Với **Java 21+ virtual threads**, thường có một virtual thread cho một task. Tên và ID virtual thread không phải định danh của worker logic hoặc job tồn tại lâu dài. Java 21 hỗ trợ tạo thread factory có tên:

~~~java
ThreadFactory virtualFactory =
        Thread.ofVirtual().name("email-vt-", 1).factory();

try (var executor =
             Executors.newThreadPerTaskExecutor(virtualFactory)) {
    executor.submit(() -> processMail("mail-101")).get();
}
~~~

Trích đoạn này cần Java 21+, import các class concurrent và phương thức **processMail()** của ứng dụng. **email-vt-1** nhận diện virtual thread của lần thực thi; nếu xử lý message sau đó chuyển thread, vẫn phải truyền taskId và workerId logic.

Virtual thread có ThreadLocal riêng, không đồng nghĩa dùng ThreadLocal của carrier platform thread. Nhưng khi một tác vụ khởi chạy một virtual thread khác, không nên giả định mọi context cần thiết tự động đi theo; vẫn phải áp dụng chính sách propagation.

## 9. Worker ID khi nhận message, chạy scheduler và retry

Một job logic có thể chạy nhiều lần:

~~~text
task=order-582 -> worker=consumer-3 attempt=1 -> failed
               -> worker=consumer-5 attempt=2 -> succeeded
~~~

Hai lần thử thuộc cùng task nhưng có worker khác và attempt khác. Log cần giữ được cả ba trường để điều tra nguyên nhân retry, redelivery hay mất kết nối. Không nên tự suy ra số lần retry bằng cách đếm log, vì log có thể bị sampling, mất dữ liệu hoặc được gửi lại.

Với **message broker**, thường cần phân biệt **broker message ID**, **business task ID**, **consumer ID**, **delivery attempt** và **trace/correlation ID**. Các ID này có thể khác nhau. Khi xử lý message theo batch, mỗi message vẫn cần identity riêng dù chúng dùng chung consumer worker.

Với **scheduler**, một job definition như **daily-invoice** có thể được kích hoạt mỗi ngày. Hãy dùng **jobName** để nhận diện loại công việc và **jobExecutionId** để nhận diện lần chạy cụ thể. **WorkerId** cho biết nơi thực thi; nó không thay thế execution ID.

Với **retry hoặc requeue**, giữ taskId của cùng công việc logic theo hợp đồng, tạo attemptId/attemptNo phù hợp, và phản ánh worker mới nếu công việc chuyển sang worker khác. Đừng ghi thành công cho attempt cũ khi thành công thuộc attempt mới.

## 10. Worker identity và trace context liên hệ thế nào?

Định danh worker thuộc **logging trong thread** nhưng nhiều yêu cầu bắt nguồn từ HTTP và đi qua nhiều service. Một schema hữu ích có thể gồm:

~~~text
service=order instance=pod-a worker=worker-2 task=order-582
requestId=req-23 traceId=4bf92f3577b34da6a3ce929d0e0e4736 event=processed
~~~

Các trường trả lời các câu hỏi khác nhau:

- **workerId + instanceId:** tìm hoạt động, lỗi hoặc tải của một worker cụ thể.
- **taskId / jobExecutionId:** theo dõi vòng đời một công việc.
- **requestId / correlationId:** gom log của một luồng yêu cầu theo quy ước ứng dụng.
- **traceId / spanId:** liên kết log với trace phân tán và các span khi có instrumentations.

Khi đi qua HTTP/gRPC/message broker, trace/correlation context cần được inject vào headers/metadata, rồi extract ở bên nhận. **ThreadLocal/MDC không tự lan truyền qua mạng**. WorkerId cục bộ thường không nên truyền cho mọi service như thể đó là danh tính của worker ở service đích; service đích có workerId riêng.

## 11. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Khắc phục |
| --- | --- | --- |
| Hai task khác nhau có cùng workerId | Pool tái sử dụng worker; có thể là đúng | Bổ sung taskId, attemptId |
| Log có taskId của job trước | Không dọn ThreadLocal/MDC | Scope cho từng task, restore trong finally |
| Worker log mất requestId | Không propagate context sang executor | Capture bên gửi, activate bên nhận |
| Log đổi workerId mỗi lần callback đổi thread | Nhầm worker logic với threadName | WorkerId logic phải đi cùng callback/task |
| Hai pod có cùng workerId=worker-1 | ID chỉ duy nhất bên trong JVM | Ghi thêm instanceId và serviceName |
| Nhiều lần retry không phân biệt được | Không có attemptId hoặc jobExecutionId | Ghi từng attempt tách biệt |
| Mọi log có traceId nhưng không thấy cây span | Chỉ copy chuỗi traceId, thiếu tracing SDK | Dùng tracer và propagator thích hợp |
| Thứ tự log chập chờn | Concurrency, buffering hoặc nhiều nguồn đồng hồ | Dùng task/trace identity và event sequence |
| Dùng workerId làm metric label gây quá tải | Cardinality tăng theo số worker/job | Dùng nhãn metric ổn định; log/trace lưu ID chi tiết |

## 12. Bảo mật, chi phí và kiểm chứng

**Định danh không phải quyền truy cập.** WorkerId/taskId do bên ngoài gửi có thể bị giả mạo. Không dùng chúng để xác thực hoặc quyết định cho phép thực thi. Với ID từ message/request không đáng tin, cần giới hạn chiều dài, xác thực ký tự, tránh xuống dòng điều khiển và các trường dữ liệu gây log injection.

Không lưu mật khẩu, token, thông tin cá nhân hay toàn bộ payload trong các ID hoặc MDC. Dữ liệu nhạy cảm phải được loại bỏ trước khi đi vào logging pipeline.

Đối với metrics, tránh dùng **taskId**, **traceId** hoặc worker ID sinh liên tục làm nhãn ở counter/histogram vì số chuỗi thời gian sẽ tăng mạnh. Dùng log/trace để truy vấn theo từng ID, dùng các metric label có tập giá trị giới hạn như queue, service và loại công việc.

Một bộ kiểm thử hữu ích nên bao gồm:

1. **Worker reuse:** hai task liên tiếp dùng chung thread, nhưng taskId khác và không nhiễm context.
2. **Concurrency:** nhiều task ghi log xen kẽ nhưng vẫn tra được đủ dòng theo từng taskId.
3. **Cross-thread:** context được truyền qua ExecutorService, CompletableFuture hoặc framework scheduler đúng theo hợp đồng.
4. **Failure & retry:** exception/timeout không làm rò MDC; lần thử sau có attemptId mới và giữ job ID khi thích hợp.
5. **Multi-instance:** hai worker cùng tên ở hai JVM được phân biệt qua instanceId.
6. **Virtual threads nếu sử dụng:** thread identity không bị nhầm với worker identity; context vẫn đúng trong từng task.
7. **Observability:** chọn một taskId, tìm được mọi event start/success/error; chọn workerId + instanceId, tìm được các job mà worker đó xử lý.

**Ghi nhớ:** tên và ID Java Thread chỉ mô tả luồng đang thực thi. **WorkerId** cần phản ánh thực thể worker theo thiết kế ứng dụng; **taskId** nhận diện công việc; **attemptId** phân biệt các lần thực thi; **traceId/correlationId** giúp liên kết hoạt động xuyên thành phần. Ghi các trường riêng biệt và quản lý scope cẩn thận để log đáng tin trong môi trường đa luồng.