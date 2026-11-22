# Đảm bảo operation quản trị có timeout và phản hồi rõ trong Spring Framework JMX

## Mục tiêu học tập

Trong Java Management Extensions (JMX), một operation quản trị có thể được gọi từ JConsole, VisualVM, một JMX client tự viết hoặc hệ thống giám sát tự động. Một operation như \`clearCache()\`, \`reloadConfiguration()\`, \`rebuildIndex()\` hay \`triggerMaintenance()\` có thể chậm, bị chặn bởi tài nguyên bên ngoài hoặc gây tác dụng phụ. Nếu không thiết kế giới hạn thời gian và kết quả rõ ràng, công cụ quản trị có thể treo, người vận hành có thể gọi lại không an toàn và trạng thái hệ thống trở nên khó xác định.

Sau bài học này, bạn có thể:

- Phân biệt timeout tại **JMX client**, timeout ở **lời gọi nghiệp vụ**, deadline toàn tác vụ và thời gian chờ trên queue.
- Hiểu rằng \`@ManagedOperation\` chỉ công bố method; nó **không tự áp một timeout** cho quá trình thực thi.
- Thiết kế operation quản trị trả kết quả nhanh, có \`requestId\`/job ID và trạng thái có thể theo dõi.
- Áp dụng \`ExecutorService\`, \`Future\`, \`CompletableFuture\` và hủy tác vụ có kiểm soát, không giả định \`cancel(true)\` luôn dừng được công việc.
- Định nghĩa contract phản hồi gồm trạng thái, thông điệp lỗi, thời điểm, deadline và ngữ nghĩa retry.
- Kiểm thử trường hợp thành công, quá hạn, lỗi phụ thuộc, tác vụ trùng và shutdown.
- Bảo vệ server khỏi tình trạng operation bị gọi đồng thời không giới hạn.

## 1. JMX operation là lời gọi quản trị, không phải hàng đợi tác vụ

JMX cho phép một MBean công bố operation dưới dạng Java method. Ví dụ Spring JMX annotation:

\`\`\`java
@ManagedOperation(description = "Reload application rules")
public void reloadRules() {
    ruleService.reload();
}
\`\`\`

Khi client gọi qua \`MBeanServerConnection.invoke\`, việc thực thi operation thường diễn ra đồng bộ theo đường gọi JMX: client phải chờ invocation trả về hoặc xảy ra exception. Nếu \`ruleService.reload()\` chạy một phút, call có thể giữ luồng đang gọi trong một phút hoặc lâu hơn.

\`\`\`text
JConsole / JMX Client
        |
        | invoke(ObjectName, "reloadRules", ...)
        v
MBeanServer
        |
        | gọi management operation
        v
Spring-managed bean / ModelMBean
        |
        | truy cập DB, file, network...
        v
Phụ thuộc bên ngoài (có thể chậm hoặc treo)
\`\`\`

Không có quy tắc JMX chung rằng mọi operation sẽ tự bị ngắt sau một số giây. \`@ManagedOperation\`, \`MBeanExporter\` và \`@EnableMBeanExport\` chỉ liên quan việc xuất hợp đồng quản lý, không biến lời gọi bất kỳ thành một tác vụ có deadline.

**Nguyên tắc:** Một operation JMX được thiết kế cho vận hành nên có thời gian phản hồi dự đoán được, giới hạn tác động và trạng thái đủ rõ để người vận hành biết chuyện gì đã xảy ra.

## 2. Bốn loại thời gian thường bị nhầm

| Loại | Đối tượng bị giới hạn | Hệ quả khi hết hạn |
| --- | --- | --- |
| Client-side timeout | Thời gian client chờ response hoặc transport | Client bỏ chờ; server-side operation có thể vẫn chạy |
| Business-operation timeout | Bước gọi DB/HTTP/lock hoặc tác vụ cụ thể | Có thể báo lỗi, trả về, ngắt hoặc cần cơ chế cleanup |
| Queue wait timeout | Thời gian task đợi tới lượt thực thi | Từ chối/chuyển trạng thái trước khi task bắt đầu |
| End-to-end deadline | Tổng thời gian cho cả queue, xử lý và các bước phụ | Cần truyền phần thời gian còn lại qua các lớp |

Ví dụ một công cụ gọi \`rebuildIndex()\` từ xa đặt socket timeout 5 giây. Sau 5 giây, client báo timeout **không chứng minh** \`rebuildIndex()\` đã bị dừng. Tác vụ có thể tiếp tục thay đổi index và hoàn thành sau đó.

Tương tự, \`Future.get(5, TimeUnit.SECONDS)\` giới hạn thời gian **chờ kết quả** của thread gọi, chứ không áp đặt một giới hạn cưỡng chế lên worker thread. Muốn xử lý tác vụ quá hạn, phải cân nhắc cancellation và cơ chế deadline trong công việc.

Một chiến lược vững chắc cần giải quyết riêng:

1. Lúc nào chấp nhận yêu cầu?
2. Khi nào bắt đầu thực thi?
3. Thời điểm nào coi yêu cầu quá hạn?
4. Có thể thực sự hủy công việc không?
5. Người gọi nhận được response hay job ID nào?
6. Sau khi caller hết thời gian chờ, kết quả cuối được truy vấn bằng cách nào?

## 3. Phản hồi rõ: đừng chỉ trả void

Một operation quản trị chỉ trả \`void\` dễ gây mơ hồ: có thể client không nhận được response, method ném exception hoặc tác vụ còn chạy ở nền. Với các thao tác có side effect, một response rõ giúp giảm rủi ro người vận hành gọi lặp.

Một số kiểu trả về thích hợp cho JMX:

- \`String\`: mã kết quả ngắn, thông báo trạng thái hoặc job ID.
- \`boolean\`: chỉ phù hợp cho thao tác đơn giản, khi trạng thái true/false được định nghĩa rõ.
- \`long\`: ví dụ số lần xử lý, timestamp hoặc ID dạng số.
- \`CompositeData\`/MXBean-compatible value: dùng khi cần phản hồi có cấu trúc và client hỗ trợ.
- Một attribute đọc trạng thái: dành cho tác vụ chạy bất đồng bộ, tách khỏi operation bắt đầu tác vụ.

Ví dụ hợp đồng:

\`\`\`text
startReindex()  -> "ACCEPTED:job-1729"
getJobStatus(id) -> "RUNNING"
getJobStatus(id) -> "SUCCEEDED"
getJobStatus(id) -> "TIMED_OUT"
getJobStatus(id) -> "FAILED:network"
\`\`\`

Không nhầm \`ACCEPTED\` với \`SUCCEEDED\`. Phản hồi đầu chỉ cho biết yêu cầu đã được tiếp nhận và có thể đang chờ/được chạy; không khẳng định đã hoàn thành.

## 4. Mẫu operation chạy nhanh: nhận yêu cầu, trả job ID

Khi thao tác có thể mất nhiều giây hoặc nhiều phút, cách thường phù hợp nhất là biến operation đồng bộ thành một **lệnh gửi tác vụ** trả nhanh. Client sau đó đọc trạng thái thông qua attribute hoặc một operation khác.

\`\`\`text
JMX client
   |
   | startMaintenance()
   v
JMX MBean
   |
   | Kiểm tra input + khả năng nhận task
   | Tạo job ID
   | Enqueue task
   v
Response: "ACCEPTED:<job-id>"  <-- nhanh
   |
   |                         Worker thread
   |                            |
   |                            +-- thực thi maintenance
   |                            +-- ghi trạng thái + kết quả
   v
Client gọi getStatus(jobId) / getLastResult()
\`\`\`

Thiết kế này tránh để một JMX call phải chờ tới khi công việc dài hoàn tất. Tuy nhiên hệ thống phải quản lý queue, số lượng jobs, TTL của trạng thái và quá trình shutdown. Không biến task dài thành \`new Thread(...).start()\` không giới hạn vì cách đó khó kiểm soát tài nguyên.

## 5. Ví dụ Spring JMX: service quản lý job trạng thái đơn giản

Ví dụ dưới đây dùng \`ThreadPoolTaskExecutor\` của Spring để chạy tác vụ với pool có giới hạn, nhưng vẫn giữ một status model dễ thao tác từ JConsole.

**MaintenanceStatus.java**

\`\`\`java
package com.example.jmx;

public enum MaintenanceStatus {
    ACCEPTED, RUNNING, SUCCEEDED, FAILED, TIMED_OUT, CANCELLED
}
\`\`\`

**MaintenanceJob.java**

\`\`\`java
package com.example.jmx;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

public final class MaintenanceJob {
    private final String id;
    private final Instant acceptedAt = Instant.now();
    private final AtomicReference<MaintenanceStatus> status =
            new AtomicReference<>(MaintenanceStatus.ACCEPTED);
    private volatile String message = "Accepted";

    public MaintenanceJob(String id) {
        this.id = id;
    }

    public String getId() {
        return id;
    }

    public Instant getAcceptedAt() {
        return acceptedAt;
    }

    public MaintenanceStatus getStatus() {
        return status.get();
    }

    public void setStatus(MaintenanceStatus newStatus, String newMessage) {
        status.set(newStatus);
        message = newMessage;
    }

    public String getMessage() {
        return message;
    }
}
\`\`\`

Ở đây \`MaintenanceJob\` lưu trạng thái trong bộ nhớ của một JVM. Ví dụ không có persistent job store, nên khi JVM khởi động lại sẽ mất status. Với tác vụ thật cần khả năng phục hồi, nên lưu trạng thái bền vững trong DB hoặc hệ thống quản lý job.

Ngoài ra, state update trong ví dụ đơn giản không phải state machine có kiểm soát chuyển tiếp. Với hệ thống đồng thời hoặc có cancellation, nên dùng \`compareAndSet\` hoặc một transition mechanism bảo đảm \`SUCCEEDED\` không bị ghi sau \`TIMED_OUT\` nếu job đã quá hạn.

## 6. Cấu hình bounded executor trong Spring

\`\`\`java
package com.example.jmx;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class MaintenanceExecutorConfiguration {

    @Bean(name = "maintenanceExecutor")
    public ThreadPoolTaskExecutor maintenanceExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("jmx-maintenance-");
        executor.setWaitForTasksToCompleteOnShutdown(false);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
\`\`\`

Giới hạn worker = 2 và queue = 16 giúp kiểm soát tải ở mức tài nguyên pool. Đây chỉ là thông số minh họa; giá trị production phụ thuộc chi phí công việc và ngân sách tài nguyên.

\`ThreadPoolTaskExecutor\` có các chính sách shutdown tùy phiên bản Spring. Việc chờ tối đa khi shutdown không phải deadline cứng cho mọi task. Nếu worker không đáp ứng interrupt hoặc mắc kẹt trong I/O không có timeout, context có thể vẫn gặp vấn đề. Phải cấu hình timeouts ở tầng phụ thuộc và xử lý graceful shutdown có giới hạn.

Mỗi task bị từ chối khi pool/queue đầy cần một phản hồi rõ ràng thay vì im lặng bỏ yêu cầu.

## 7. MBean quản trị với phản hồi ACCEPTED, REJECTED và status

\`\`\`java
package com.example.jmx;

import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.RejectedExecutionException;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@ManagedResource(
    objectName = "com.example.ops:type=MaintenanceAdmin,name=primary",
    description = "Long-running administration tasks")
public class MaintenanceAdmin {

    private final ThreadPoolTaskExecutor executor;
    private final ConcurrentMap<String, MaintenanceJob> jobs =
            new ConcurrentHashMap<>();

    public MaintenanceAdmin(ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    @ManagedOperation(
        description = "Submit maintenance; returns ACCEPTED:ID or REJECTED")
    public String startMaintenance() {
        String id = UUID.randomUUID().toString();
        MaintenanceJob job = new MaintenanceJob(id);

        try {
            executor.execute(() -> runMaintenance(job));
            jobs.put(id, job);
            return "ACCEPTED:" + id;
        } catch (RejectedExecutionException e) {
            return "REJECTED:MAINTENANCE_CAPACITY_EXCEEDED";
        }
    }

    private void runMaintenance(MaintenanceJob job) {
        job.setStatus(MaintenanceStatus.RUNNING, "Started");
        try {
            // Gọi service thực tế và thực thi với deadline ở bên trong.
            performMaintenance();
            job.setStatus(MaintenanceStatus.SUCCEEDED, "Completed");
        } catch (Exception e) {
            job.setStatus(MaintenanceStatus.FAILED,
                    "Failure: " + e.getClass().getSimpleName());
        }
    }

    private void performMaintenance() {
        // Ví dụ placeholder cho công việc thật.
        // Trong production cần cancellation/deadline ở từng bước.
    }

    @ManagedOperation(description = "Read status by job ID")
    @ManagedOperationParameter(
        name = "jobId", description = "ID returned from startMaintenance")
    public String getJobStatus(String jobId) {
        MaintenanceJob job = jobs.get(jobId);
        if (job == null) {
            return "NOT_FOUND";
        }
        return job.getStatus().name() + ":" + job.getMessage();
    }

    @ManagedAttribute(description = "Number of retained job records")
    public int getRetainedJobCount() {
        return jobs.size();
    }
}
\`\`\`

**Điểm thiết kế cần lưu ý:** mã minh họa đặt \`jobs.put(id, job)\` sau \`executor.execute(...)\`. Trong một executor có thể bắt đầu worker ngay, công việc có thể hoàn tất trước khi map được cập nhật, nhưng vì worker chỉ dùng \`job\` trực tiếp, status vẫn được ghi trên object. Tuy nhiên client có thể truy vấn ID ngay trước khi map có entry. Để loại bỏ race đó trong production, nên **ghi job vào map trước khi enqueue**, và nếu enqueue bị từ chối thì xóa entry (hoặc đánh dấu REJECTED):

\`\`\`java
jobs.put(id, job);
try {
    executor.execute(() -> runMaintenance(job));
    return "ACCEPTED:" + id;
} catch (RejectedExecutionException e) {
    jobs.remove(id);
    return "REJECTED:MAINTENANCE_CAPACITY_EXCEEDED";
}
\`\`\`

Cách này vẫn cần kiểm soát tổng số job records: \`ConcurrentHashMap\` có thể tăng không giới hạn nếu không có TTL/eviction. Một operation quản trị không nên biến status store thành memory leak.

## 8. Gắn MBean vào Spring ApplicationContext

Dùng annotation-based JMX exporting:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableMBeanExport(server = "platformMBeanServer")
public class MaintenanceJmxConfiguration {

    @Bean
    public MBeanServer platformMBeanServer() {
        return ManagementFactory.getPlatformMBeanServer();
    }

    @Bean
    public MaintenanceAdmin maintenanceAdmin(
            @Qualifier("maintenanceExecutor")
            ThreadPoolTaskExecutor maintenanceExecutor) {
        return new MaintenanceAdmin(maintenanceExecutor);
    }
}
\`\`\`

Cấu hình này giả định \`MaintenanceExecutorConfiguration\` cũng được đăng ký/import trong context, để có bean \`maintenanceExecutor\`.

Ví dụ main:

\`\`\`java
try (var context = new AnnotationConfigApplicationContext(
        MaintenanceExecutorConfiguration.class,
        MaintenanceJmxConfiguration.class)) {

    MBeanServer server = context.getBean(MBeanServer.class);
    ObjectName name = new ObjectName(
            "com.example.ops:type=MaintenanceAdmin,name=primary");

    System.out.println(server.isRegistered(name));
    System.in.read();
}
\`\`\`

Khi context đóng, exporter thường unregister MBean do nó quản lý. Nhưng các background tasks có thể còn đang chạy tùy shutdown policy; cần quản lý executor lifecycle và trạng thái tác vụ riêng.

## 9. Deadline thực sự cho công việc chậm

Một câu trả lời \`ACCEPTED\` nhanh chưa có nghĩa job có deadline. Với các operation quản trị, nên xác định ngân sách thời gian tối đa cho **toàn bộ tác vụ**, ví dụ 30 giây hoặc 2 phút.

Hãy dùng \`Instant deadline\` hoặc tốt hơn là đồng hồ đơn điệu (\`System.nanoTime\`) cho các phép đo thời lượng. Mốc thời gian ISO để hiển thị vẫn hữu ích, nhưng timeouts nên dựa trên elapsed time để tránh đồng hồ hệ thống bị chỉnh làm sai số.

Ví dụ thiết kế:

\`\`\`java
long deadlineNanos = System.nanoTime()
        + TimeUnit.SECONDS.toNanos(30);

long remainingNanos = deadlineNanos - System.nanoTime();

if (remainingNanos <= 0) {
    throw new TimeoutException("Maintenance deadline exceeded");
}
\`\`\`

Trong hệ thống thật, tác vụ cần nhận \`deadlineNanos\` và truyền ngân sách còn lại tới từng bước:

\`\`\`text
Total deadline = 30 s
    |
    +-- queue wait <= 5 s
    +-- DB operation <= 10 s
    +-- HTTP dependency <= 8 s
    +-- cleanup/finalization <= remaining
\`\`\`

Không thiết kế từng bước có timeout 30 giây rồi thực thi 5 bước nối tiếp, vì tổng thời gian khi đó có thể lên tới nhiều lần deadline.

Một số I/O libraries có timeout riêng: HTTP connect/read/request timeout; JDBC \`setQueryTimeout\`, transaction timeout, connection pool acquisition timeout; lock acquisition timeout. Chọn timeout phù hợp với API và kiểm tra behavior runtime của thư viện đang dùng.

## 10. Future.get(timeout): giới hạn chờ, không ép dừng task

Một mẫu Java dễ gặp:

\`\`\`java
Future<String> future =
        executorService.submit(this::longRunningWork);

try {
    String result = future.get(5, TimeUnit.SECONDS);
    return "SUCCEEDED:" + result;
} catch (TimeoutException e) {
    future.cancel(true);
    return "TIMED_OUT";
}
\`\`\`

\`future.get(5, SECONDS)\` chỉ đợi tối đa 5 giây. Khi timeout, \`future.cancel(true)\` **yêu cầu interrupt** nếu task đang chạy, nhưng không bảo đảm worker dừng ngay. Code gọi network API không có timeout, chờ trên native call hoặc bỏ qua interruption có thể tiếp tục làm việc.

Cũng cần xử lý \`InterruptedException\`: thường nên khôi phục cờ interrupt bằng \`Thread.currentThread().interrupt()\` và đưa ra kết quả phù hợp thay vì nuốt lỗi.

\`ExecutionException\` chứa exception của task, cần bóc cause để phân loại lỗi. \`CancellationException\` cũng có thể xuất hiện nếu task đã bị hủy.

Nếu cần cam kết “task không bao giờ vượt 5 giây”, thread interrupt không đủ. Phải thiết kế các bước có timeout/hủy hợp tác, và trong trường hợp tác vụ khó kiểm soát có thể cần chạy trong process/container riêng để có khả năng terminate cứng theo chính sách vận hành.

## 11. CompletableFuture.orTimeout và completeOnTimeout

Với Java hiện đại:

\`\`\`java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> performRemoteCheck(), executor);

CompletableFuture<String> timed =
        future.orTimeout(5, TimeUnit.SECONDS);
\`\`\`

\`orTimeout\` làm \`CompletableFuture\` hoàn tất exceptional nếu quá hạn; **nó không bảo đảm hủy underlying computation**. \`completeOnTimeout(value, ...)\` đặt một kết quả fallback nếu quá hạn, nhưng phép tính nền cũng có thể tiếp tục.

Với operation có side effect, đừng trả \`SUCCEEDED\` dưới dạng fallback chỉ vì client hết thời gian chờ. Nên trả trạng thái \`TIMED_OUT\`/ \`UNKNOWN\` đúng ngữ nghĩa và có cơ chế reconciliation: xác nhận tác vụ đã dừng hay còn đang tiếp tục.

Trong Java \`CompletableFuture\`, việc xử lý cancellation có nhiều khác biệt với \`FutureTask\`; khi cần interrupt worker thread, hãy kiểm soát bằng \`Future\` từ \`ExecutorService\` hoặc cơ chế cancellation token riêng.

## 12. Timeouts của JMX client từ xa

Một client dùng \`JMXConnector\` và \`MBeanServerConnection\` có thể kết nối tới JVM khác:

\`\`\`java
JMXServiceURL url = new JMXServiceURL(
        "service:jmx:rmi:///jndi/rmi://host.example:9010/jmxrmi");

try (JMXConnector connector =
        JMXConnectorFactory.connect(url, environment)) {
    MBeanServerConnection connection =
            connector.getMBeanServerConnection();

    connection.invoke(
            objectName,
            "startMaintenance",
            new Object[0],
            new String[0]);
}
\`\`\`

Không có một cài đặt timeout transport portable duy nhất cho mọi JMX connector/provider. Một số tham số timeout của RMI/JMX là provider-specific; tài liệu version JDK và connector cần được kiểm tra trước khi dựa vào chúng trong production.

Nếu áp một client-side timeout, hãy nhớ:

- Kết nối có thể bị lỗi/đóng sau thời gian chờ nhưng server-side invocation có thể vẫn thực hiện.
- Client không nên tự động retry một operation không idempotent khi không biết kết quả lần trước.
- \`ObjectName\`, job ID hoặc idempotency key cần đủ để tra cứu/tái đối chiếu trạng thái.
- Client nên log rõ “chưa nhận được response” khác với “server từ chối” và “task thất bại”.

Một wrapper client chạy \`invoke\` trong thread riêng rồi chờ \`Future.get(timeout)\` chỉ giới hạn luồng caller chờ; nó có thể để lại các thread/connection bị kẹt nếu I/O không hỗ trợ hủy. Không coi đó là một giải pháp timeout transport hoàn chỉnh.

## 13. Thiết kế contract có trạng thái rõ ràng

Một state model tối thiểu cho job quản trị:

\`\`\`text
             +-----------+
             | ACCEPTED  |
             +-----+-----+
                   |
                   v
             +-----------+
             | RUNNING   |
             +-----+-----+
                   |
            +------+------+------+
            |             |      |
            v             v      v
       SUCCEEDED        FAILED  TIMED_OUT
                              / CANCELLED
\`\`\`

Các trạng thái terminal thường gồm \`SUCCEEDED\`, \`FAILED\`, \`TIMED_OUT\`, \`CANCELLED\`, nhưng cần định nghĩa cẩn thận \`TIMED_OUT\`: nếu worker vẫn chạy sau khi caller hết thời gian chờ, đó có thể là \`UNKNOWN\` hoặc \`TIMEOUT_REQUESTED\`, không phải kết luận rằng công việc đã ngừng.

Một phản hồi có thể biểu diễn:

\`\`\`text
jobId       = "f3d8..."
state       = "RUNNING"
acceptedAt  = "2026-11-11T10:00:00Z"
startedAt   = "2026-11-11T10:00:02Z"
deadlineAt  = "2026-11-11T10:00:32Z"
finishedAt  = ""
errorCode   = ""
message     = "Rebuilding 8 of 20 partitions"
\`\`\`

Trong JMX cơ bản, bạn có thể trả một chuỗi định dạng cố định. Nếu cần dữ liệu có cấu trúc cho client máy, hãy cân nhắc MXBean-compatible types hoặc \`CompositeData\`. Không đưa stack traces đầy đủ, token hay bí mật vào MBean attributes/trả về.

Thời điểm/tỷ lệ tiến độ chỉ nên báo nếu có cơ sở; không suy diễn “80% complete” từ thời gian đã trôi nếu công việc không hỗ trợ đo progress.

## 14. Đồng bộ hóa, giới hạn concurrency và idempotency

Một MBean là điểm quản trị có thể bị nhiều client gọi đồng thời. Ví dụ hai operator cùng nhấn \`rebuildIndex\` hoặc hệ thống tự động gửi lại request do timeout.

Các biện pháp:

1. Giới hạn số tác vụ đồng thời và độ sâu queue.
2. Dùng \`Semaphore\` hoặc state flag để từ chối thao tác trùng loại khi cần.
3. Cung cấp idempotency key cho các operation có thể được retry.
4. Trả \`ALREADY_RUNNING:jobId\` thay vì tạo job mới khi thao tác tương đương đang chạy.
5. Không giữ lock lớn khi chờ I/O hoặc đồng bộ với code nghiệp vụ.
6. Phân biệt \`REJECTED_BUSY\`, \`REJECTED_INVALID_ARGUMENT\` và \`REJECTED_CAPACITY\`.

Ví dụ operation chỉ cho phép một maintenance job tại một thời điểm:

\`\`\`java
private final AtomicBoolean maintenanceRunning =
        new AtomicBoolean();

@ManagedOperation
public String requestMaintenance() {
    if (!maintenanceRunning.compareAndSet(false, true)) {
        return "REJECTED:ALREADY_RUNNING";
    }

    try {
        executor.execute(() -> {
            try {
                performMaintenance();
            } finally {
                maintenanceRunning.set(false);
            }
        });
        return "ACCEPTED";
    } catch (RejectedExecutionException e) {
        maintenanceRunning.set(false);
        return "REJECTED:CAPACITY";
    }
}
\`\`\`

Đây chỉ là pattern kiểm soát concurrency. Nếu process bị dừng đột ngột hoặc task bị mắc kẹt, trạng thái \`maintenanceRunning\` có thể không phản ánh toàn hệ thống; cần chiến lược khôi phục nếu công việc có ảnh hưởng bền vững.

Trong hệ thống nhiều JVM, \`AtomicBoolean\` chỉ chặn trùng **trong một JVM**. Nếu cùng một thao tác quản trị có thể được gọi trên nhiều replicas, cần distributed lock, shared job registry hoặc một coordinator thích hợp.

## 15. Operation đồng bộ ngắn với validation và thời hạn rõ

Không phải operation nào cũng cần background job. Với thao tác rất ngắn, deterministic, có thể giữ synchronous API:

\`\`\`java
@ManagedOperation(description = "Set maximum queue size")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "size", description = "New maximum queue size")
})
public String setMaxQueueSize(int size) {
    if (size < 1 || size > 10000) {
        return "REJECTED:SIZE_OUT_OF_RANGE";
    }

    queueController.setMaxSize(size);
    return "SUCCEEDED:MAX_QUEUE_SIZE=" + size;
}
\`\`\`

Đây là operation có thời gian thực thi kỳ vọng nhỏ, không gọi network chậm. Nếu \`queueController.setMaxSize\` cần lock hoặc I/O có thể bị chặn vô hạn, phải bổ sung kiểm soát riêng. Description không tự giới hạn thời gian hoặc xác thực argument; validation phải nằm trong implementation.

Nếu operation trả \`SUCCEEDED\`, kết quả đó nên phản ánh trạng thái đã được áp dụng hoặc được xác nhận theo contract. Không trả \`SUCCEEDED\` ngay khi mới enqueue một thay đổi có thể thất bại về sau.

## 16. Phân biệt timeout, thất bại và không rõ kết quả

| Trường hợp | Trạng thái nên phản ánh | Hành động client |
| --- | --- | --- |
| Validation không đạt trước khi thực hiện | \`REJECTED_INVALID_ARGUMENT\` | Sửa input, không retry mù |
| Executor/queue đầy | \`REJECTED_CAPACITY\` | Retry có backoff khi thích hợp |
| Tác vụ đã được nhận | \`ACCEPTED:jobId\` | Poll/subscribe trạng thái |
| Tác vụ đang chạy | \`RUNNING\` | Chờ deadline/progress |
| Tác vụ hoàn thành và commit thành công | \`SUCCEEDED\` | Xác nhận trạng thái |
| Tác vụ thất bại có nguyên nhân | \`FAILED:errorCode\` | Chẩn đoán, xử lý theo lỗi |
| Deadline được xử lý, tác vụ đã dừng/hủy được xác nhận | \`TIMED_OUT\` hoặc \`CANCELLED\` | Xem ngữ nghĩa cleanup |
| Client mất response trong khi server có thể đã thực hiện | \`UNKNOWN\` phía client | Tra cứu theo request ID trước khi retry |

Cần hiểu rõ “timeout” không phải một giá trị duy nhất. Hết thời gian client chờ có thể chỉ là **outcome unknown**, nhất là với operation không idempotent như xóa dữ liệu hoặc chuyển trạng thái nghiệp vụ.

## 17. Tránh exception mơ hồ trong JMX

Một method được export qua JMX có thể ném exception nghiệp vụ. Tùy dạng MBean/adapter, người gọi có thể thấy \`MBeanException\`, \`RuntimeMBeanException\`, \`ReflectionException\` hoặc exception được Spring JMX access layer bao gói.

Thay vì trả stack trace dài như message, nên:

- Dùng mã lỗi ổn định như \`INVALID_ARGUMENT\`, \`DEPENDENCY_UNAVAILABLE\`, \`BUSY\`, \`TIME_BUDGET_EXCEEDED\`.
- Gắn \`requestId\`/job ID để đối chiếu log.
- Ghi chi tiết lỗi ở server log với chính sách bảo vệ dữ liệu.
- Trả thông điệp ngắn cho JMX client, đủ để quyết định hành động.
- Phân biệt lỗi trước khi nhận task với lỗi sau khi task bắt đầu.

Ví dụ:

\`\`\`text
REJECTED:INVALID_ARGUMENT:limit must be 1..10000
ACCEPTED:jobId=8eac...
FAILED:jobId=8eac...:DEPENDENCY_UNAVAILABLE
UNKNOWN:jobId=8eac...:CHECK_STATUS
\`\`\`

Khi có nhiều JMX clients, hợp đồng phản hồi ổn định giúp automation không phải parse thông điệp tự nhiên thay đổi theo phiên bản.

## 18. Bảo mật khi cung cấp operation quản trị

Một operation JMX có thể tác động mạnh lên runtime: reset thống kê, reload cấu hình, clear cache, kích hoạt backup, xóa dữ liệu hoặc shutdown. Nếu mở remote JMX không đúng cách, một client không được phép có thể gây gián đoạn dịch vụ.

Cần:

- Chỉ công bố operation thực sự cần thiết.
- Giới hạn remote JMX theo network, authentication, authorization và encryption phù hợp.
- Không để \`@ManagedOperation\` trên các method nguy hiểm chỉ vì muốn debug tiện.
- Dùng role/permission phù hợp ở transport và hệ thống quản trị, không coi annotation là cơ chế phân quyền.
- Kiểm tra side effects và concurrency trước khi áp dụng thao tác.
- Ghi audit record (ai gọi, operation, request ID, thời điểm, outcome) ở nơi có thể xác thực danh tính caller.
- Không chứa dữ liệu nhạy cảm trong \`ObjectName\`, response string hoặc notification \`userData\`.

Timeout giúp giảm treo, nhưng **không thay thế security**. Một operation có giới hạn thời gian vẫn có thể gây tác hại nếu bị gọi lặp với tần suất cao hoặc nhận input không được kiểm tra.

## 19. Vòng đời executor khi Spring context dừng

Nếu một JMX operation enqueue background task, vòng đời \`ThreadPoolTaskExecutor\` cần được quản lý:

\`\`\`text
ApplicationContext đang chạy
    |
    +-- JMX MBean
    +-- Executor
    +-- Job status store
    |
Context đóng
    |
    +-- Ngừng nhận yêu cầu quản trị mới
    +-- Xác định các job đang chạy
    +-- Hủy/đợi theo shutdown budget
    +-- Lưu/truyền terminal outcome nếu có
    +-- Exporter unregister MBean
    +-- Executor shutdown
\`\`\`

Tùy dependency và Spring version, thứ tự destroy có thể khác; dùng dependency injection/\`@DependsOn\` hoặc lifecycle bean thích hợp để đảm bảo operation quản trị không enqueue task khi executor đã shutdown. Khi shutdown, \`RejectedExecutionException\` cần được trả thành \`REJECTED_SHUTTING_DOWN\` hoặc trạng thái tương đương, không rò rỉ lỗi khó hiểu tới client.

Nếu job cần tiếp tục sau khi context đóng, một in-process executor trong chính context đó có thể không phù hợp. Cân nhắc external job queue hoặc worker service với persistent state.

## 20. Kiểm thử thời gian và kết quả trong Spring JMX

Một integration test cần xác minh:

1. MBean được đăng ký trong \`MBeanServer\`.
2. \`startMaintenance()\` trả \`ACCEPTED:jobId\` hoặc \`REJECTED\` nhanh.
3. Có thể truy vấn \`getJobStatus(jobId)\`.
4. Job chuyển từ \`ACCEPTED\`/\`RUNNING\` sang terminal state.
5. Tác vụ bị chặn/quá hạn không khiến JMX invocation sync chờ vô hạn.
6. Tác vụ đồng thời vượt capacity bị từ chối có kiểm soát.
7. Context shutdown xử lý executor và jobs đúng hợp đồng.

Ví dụ skeleton JUnit:

\`\`\`java
@Test
void returnsJobIdAndTracksCompletion() throws Exception {
    try (var context = new AnnotationConfigApplicationContext(
            MaintenanceExecutorConfiguration.class,
            MaintenanceJmxConfiguration.class)) {

        MBeanServer server = context.getBean(MBeanServer.class);
        ObjectName name = new ObjectName(
                "com.example.ops:type=MaintenanceAdmin,name=primary");

        assertTrue(server.isRegistered(name));

        String accepted = (String) server.invoke(
                name, "startMaintenance",
                new Object[0], new String[0]);

        assertTrue(accepted.startsWith("ACCEPTED:"));

        String id = accepted.substring("ACCEPTED:".length());

        String status = (String) server.invoke(
                name, "getJobStatus",
                new Object[]{id},
                new String[]{"java.lang.String"});

        assertTrue(status.startsWith("ACCEPTED:")
                || status.startsWith("RUNNING:")
                || status.startsWith("SUCCEEDED:"));
    }
}
\`\`\`

Test trên chỉ minh họa contract. Với asynchronous job, không nên assert chính xác một trạng thái trung gian tại thời điểm tùy ý, vì worker có thể chạy nhanh hoặc chậm. Để test terminal outcome, dùng \`CountDownLatch\`, fake clock hoặc một polling utility có **deadline hữu hạn**, thay vì \`Thread.sleep\` mù.

Khi chạy suite song song, một platform \`MBeanServer\` chung với cùng \`ObjectName\` có thể khiến tests xung đột. Nên dùng server riêng hoặc tên riêng cho từng fixture.

## 21. Kiểm thử timeout và hủy hợp tác

Thiết kế một fake maintenance service có thể nhận cancellation token hoặc kiểm tra \`Thread.interrupted()\`:

\`\`\`java
void cooperativeWork(long deadlineNanos) throws Exception {
    while (moreWork()) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Interrupted");
        }

        long remaining =
                deadlineNanos - System.nanoTime();
        if (remaining <= 0) {
            throw new TimeoutException("Deadline exceeded");
        }

        doOneBoundedStep(remaining);
    }
}
\`\`\`

Mỗi bước \`doOneBoundedStep\` phải có timeout riêng theo ngân sách còn lại. Nếu đó là JDBC, HTTP hoặc external process, sử dụng API tương ứng để đặt timeout/cancel thay vì chỉ kiểm tra deadline giữa các bước.

Test cần bao phủ:

- Deadline hết trước khi task bắt đầu.
- Deadline hết giữa quá trình chạy.
- Task nhận interrupt và cleanup.
- Task không thể hủy ngay: outcome phải phản ánh chưa xác minh, không đánh dấu completed.
- Caller timeout nhưng task hoàn tất sau đó: có thể truy vấn đúng kết quả cuối.
- Shutdown khi job đang chạy.

## 22. Giám sát chính operation quản trị

Để vận hành đáng tin cậy, nên đo các chỉ số:

| Metric | Ý nghĩa |
| --- | --- |
| \`admin_operation_requests_total\` | Tổng số yêu cầu theo loại operation |
| \`admin_operation_rejected_total\` | Số yêu cầu bị từ chối theo lý do |
| \`admin_operation_duration_seconds\` | Thời gian thực thi job |
| \`admin_operation_queue_wait_seconds\` | Thời gian đợi trong queue |
| \`admin_operation_timeouts_total\` | Số trường hợp deadline hết |
| \`admin_operation_running\` | Số job đang chạy |
| \`admin_operation_queue_depth\` | Số job chờ |
| \`admin_operation_last_result\` | Outcome gần nhất để operator kiểm tra |

Tên metric chỉ là gợi ý; có thể triển khai bằng Micrometer, JMX attributes hoặc hệ thống telemetry đang dùng. Tránh tạo nhãn metric theo job ID duy nhất cho mỗi request vì sẽ gây high-cardinality.

Đừng chỉ theo dõi số timeout. Theo dõi cả thời gian xếp hàng, số task bị từ chối và số task chạy lâu sau client timeout để nhận diện nghẽn thực sự.

## 23. Checklist thiết kế cho operation quản trị

Trước khi công bố một operation qua JMX, trả lời:

- Operation có side effect không? Có thể gọi lại an toàn không?
- Thời gian kỳ vọng và worst-case là bao nhiêu?
- Có external I/O nào chưa có timeout không?
- Thời gian chờ client và deadline server được định nghĩa riêng chưa?
- Request có được phản hồi nhanh bằng \`ACCEPTED\`/job ID nếu tác vụ dài không?
- Có thể tra cứu trạng thái cuối bằng ID không?
- Có giới hạn queue, concurrency và số status records không?
- Khi quá hạn, hệ thống biết chắc task đã dừng hay chỉ biết caller ngừng chờ?
- Khi lỗi, response có mã lỗi và correlation ID không?
- Khi shutdown/restart, kết quả và công việc đang chạy được xử lý thế nào?
- MBean chỉ được truy cập bởi các operator/service có quyền phù hợp chưa?
- Integration tests có cover timeout, partial failure, retry và cancellation không?

## 24. Bài tập thực hành

**Bài 1 — Operation sync có giới hạn.** Tạo \`CacheAdmin.setLimit(int)\` trả \`SUCCEEDED\` hoặc \`REJECTED_INVALID_ARGUMENT\`. Gọi qua \`MBeanServer.invoke\` và xác nhận attribute \`Limit\`.

**Bài 2 — Background job.** Tạo \`IndexAdmin.startRebuild()\` trả job ID, \`getRebuildStatus(String id)\` trả trạng thái. Dùng executor có giới hạn, kiểm tra operation nhận lệnh không chờ rebuild hoàn tất.

**Bài 3 — Tác vụ chậm.** Giả lập HTTP dependency bị delay hơn 5 giây, áp deadline 2 giây. So sánh caller timeout với trạng thái thực của worker; giải thích vì sao không thể kết luận worker bị ngắt chỉ từ client response.

**Bài 4 — Capacity.** Cho phép tối đa 2 workers và queue 4. Gửi nhiều requests liên tiếp; xác nhận các requests vượt capacity trả \`REJECTED_CAPACITY\` và không tạo thêm thread không giới hạn.

**Bài 5 — Idempotency.** Thêm tham số \`requestKey\` cho operation khởi tạo backup. Gọi cùng key hai lần rồi xác minh trả cùng job ID hoặc trạng thái \`ALREADY_RUNNING\` thay vì chạy trùng backup.

**Bài 6 — Shutdown.** Đóng \`ApplicationContext\` trong lúc job đang chạy, xác nhận operation mới bị từ chối, worker được xử lý theo shutdown budget và status store không bị giữ vô thời hạn.

## Kết luận

Để **operation quản trị có timeout và phản hồi rõ** trong Spring Framework JMX, không thể chỉ thêm \`@ManagedOperation\` hoặc đặt timeout cho client. Cần thiết kế toàn bộ contract: validate input, giới hạn đồng thời và queue, phản hồi nhanh bằng job ID đối với tác vụ dài, theo dõi trạng thái, truyền deadline xuống I/O, hỗ trợ cancellation hợp tác và phân biệt rõ **timeout của người chờ** với **việc công việc thực sự đã dừng**. Khi kết hợp JMX metadata, bounded executors, error codes, lifecycle cleanup và integration tests, các operation quản trị trở nên dự đoán được, ít gây treo và an toàn hơn cho hệ thống đang vận hành.
