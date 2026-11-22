# Kiểm thử JMX cùng AOP, transaction và async trong Spring Framework

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả mối quan hệ giữa **JMX MBean**, **Spring AOP proxy**, **transaction interceptor** và **asynchronous method invocation**.
- Phân biệt lời gọi đi qua **Spring proxy** với lời gọi trực tiếp vào target object, đặc biệt khi MBean được export bằng \`MBeanExporter\`.
- Thiết kế integration test xác nhận JMX operation thực sự kích hoạt \`@Transactional\` hoặc \`@Async\` theo cấu hình, không chỉ kiểm tra annotation tồn tại.
- Phát hiện lỗi do **self-invocation**, JDK dynamic proxy, CGLIB class proxy, interface exposure và metadata assembler.
- Biết cách tránh giả định một operation trả về \`void\` hoặc \`Future\` đồng nghĩa đã hoàn thành thành công nghiệp vụ.
- Kiểm tra trạng thái transaction qua \`TransactionSynchronizationManager\`, kiểm tra async qua thread và kết quả có kiểm soát.
- Tổ chức test an toàn với \`MBeanServer\`, \`ObjectName\` duy nhất, lifecycle cleanup và isolation.
- Hiểu các giới hạn của test có \`@Transactional\` trên test method, thread khác và fake transaction manager.
- Xử lý exception, logging, timeout và quan sát để operation JMX không tạo side effect khó kiểm soát.

## 2. Bối cảnh: tại sao JMX + AOP cần được kiểm thử riêng?

Spring JMX cung cấp cách xuất các Java/Spring beans thành MBean. Spring AOP cung cấp cơ chế advice và interceptor để áp dụng transaction, async, logging, authorization, caching hoặc nhiều cross-cutting concerns khác.

Trong code Java thông thường:

\`\`\`java
service.processBatch();
\`\`\`

có thể đi qua Spring proxy nếu \`service\` là một Spring bean đã được proxy. Nhưng trong JMX, lời gọi đi qua một lớp khác:

\`\`\`text
JConsole / JMX client
          |
          v
     MBeanServer.invoke(...)
          |
          v
 MBean được Spring exporter đăng ký
          |
          v
 ModelMBean / JMX adapter hoặc Standard MBean
          |
          v
 Spring bean / Spring proxy / target object
          |
          v
 AOP interceptors:
    - TransactionInterceptor
    - AsyncExecutionInterceptor
    - custom aspects
          |
          v
 Business logic
\`\`\`

**Điểm mấu chốt:** AOP chỉ có hiệu lực khi invocation đi qua proxy/advice phù hợp. Không thể kết luận “method có \`@Transactional\` thì mọi cách gọi method đó đều có transaction”, hoặc “method có \`@Async\` thì JMX invoke chắc chắn chạy trong thread khác”.

JMX exporter có thể được cấu hình đăng ký một object proxy, target object, Standard MBean hoặc Model MBean wrapper. Mỗi phương án có đường đi khác nhau. Do đó phải **quan sát kết quả runtime** thông qua MBeanServer và các dấu hiệu transaction/async, thay vì chỉ tin vào cấu hình.

## 3. Những thành phần cần phân biệt

| Thành phần | Trách nhiệm | Điểm cần kiểm tra |
| --- | --- | --- |
| \`MBeanExporter\` | Chọn và đăng ký bean vào MBeanServer. | Export đúng object, ObjectName và metadata chưa? |
| \`MBeanInfoAssembler\` | Xác định attributes và operations được công bố. | Operation mong đợi xuất hiện, signature đúng không? |
| \`MBeanServer\` | Registry và dispatcher JMX. | \`isRegistered\`, \`getMBeanInfo\`, \`invoke\`. |
| Spring AOP proxy | Áp dụng advice/interceptor khi lời gọi đi qua proxy. | JMX đang gọi proxy hay target? |
| \`@Transactional\` | Chỉ dẫn transaction advice theo chính sách và transaction manager. | Trong code thực thi có transaction active không? |
| \`@Async\` | Chỉ dẫn async advice chuyển execution qua executor. | Body chạy trên thread nào, hoàn thành khi nào? |
| \`TransactionSynchronizationManager\` | Giữ trạng thái transaction gắn với thread Spring. | Chứng minh transaction thực sự active. |
| \`@EnableTransactionManagement\` | Kích hoạt cấu hình transaction interception. | Transaction advice có được tạo không? |
| \`@EnableAsync\` | Kích hoạt cấu hình async invocation. | Executor/advice đã áp dụng chưa? |

Cần phân biệt **MBean export** là một khía cạnh quản trị, còn **AOP proxy** là một khía cạnh lời gọi. Annotation của cả hai không thay thế nhau.

## 4. Ví dụ sai phổ biến: self-invocation

Giả sử:

\`\`\`java
@Service
public class ImportService {

    public void requestRun() {
        runInTransaction();
    }

    @Transactional
    public void runInTransaction() {
        // Update database.
    }
}
\`\`\`

Trong Spring AOP proxy mode thông thường, lời gọi từ \`requestRun()\` tới \`runInTransaction()\` bằng \`this\` không đi qua proxy. Transaction interceptor có thể **không chạy** dù method đích có \`@Transactional\`.

Nếu JMX công bố:

\`\`\`java
@ManagedOperation
public void requestRun() {
    importService.requestRun();
}
\`\`\`

thì kết quả còn phụ thuộc cách \`importService\` được inject và method nào gọi tiếp. Khi \`requestRun()\` của service lại tự gọi \`runInTransaction()\`, tự gọi vẫn là vấn đề.

Một cấu trúc tách trách nhiệm rõ hơn:

\`\`\`text
JMX admin adapter
      |
      v
ImportOrchestrator (proxy)
      |
      v
TransactionalWorkerService (proxy)
      |
      v
Database transaction
\`\`\`

Trong đó **JMX adapter inject service** và gọi method public được quản lý bởi Spring proxy. Với \`@Async\`, tách method async vào bean khác cũng giúp tránh self-invocation.

## 5. Ví dụ cấu trúc đề xuất cho ứng dụng

### 5.1. Service transaction

\`\`\`java
package example.jmx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class TransactionalJobService {

    @Transactional
    public boolean runTransactionalStep() {
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }
}
\`\`\`

Đây là ví dụ để xác nhận trạng thái transaction trong body. Để có transaction thực, application context cần transaction management enabled và \`PlatformTransactionManager\` phù hợp. Nếu không có transaction manager, method có thể không hoạt động như dự kiến hoặc startup/invocation thất bại.

### 5.2. Service async

\`\`\`java
package example.jmx;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncJobService {

    @Async("managementTaskExecutor")
    public CompletableFuture<String> runAsyncStep() {
        return CompletableFuture.completedFuture(
            Thread.currentThread().getName()
        );
    }
}
\`\`\`

\`@Async\` cần \`@EnableAsync\` (hoặc cấu hình tương đương) và executor có bean name đúng. Bản thân \`CompletableFuture.completedFuture(...)\` trong method chưa chứng minh bất đồng bộ; dấu hiệu cần kiểm tra là **body có được thực thi trên thread của executor hay không**.

### 5.3. Adapter quản trị JMX

\`\`\`java
package example.jmx;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Probe,name=Aop",
    description = "JMX and AOP integration probe"
)
public class JmxAopProbe {

    private final TransactionalJobService transactionalJob;
    private final AsyncJobService asyncJob;

    public JmxAopProbe(
            TransactionalJobService transactionalJob,
            AsyncJobService asyncJob) {
        this.transactionalJob = transactionalJob;
        this.asyncJob = asyncJob;
    }

    @ManagedOperation(
        description = "Return whether a transactional service call is active"
    )
    public boolean probeTransaction() {
        return transactionalJob.runTransactionalStep();
    }

    @ManagedOperation(
        description = "Return worker thread used by the async service"
    )
    public String probeAsyncThread() throws Exception {
        CompletableFuture<String> future =
            asyncJob.runAsyncStep();

        return future.get(5, TimeUnit.SECONDS);
    }

    @ManagedAttribute(
        description = "Management adapter is available"
    )
    public boolean isAvailable() {
        return true;
    }
}
\`\`\`

Hai operation trả về kiểu đơn giản cho JMX client. \`probeAsyncThread()\` dùng \`future.get(...)\` để minh họa quan sát, nhưng **nó block caller** trong tối đa thời gian chờ; trong hệ thống thực nên cân nhắc pattern request/status cho tác vụ dài.

**Đây là probe cho môi trường lab/test**, không phải một API quản trị nên công bố ở production mà không xem xét quyền truy cập.

## 6. Cấu hình transaction, async và exporter

Ví dụ Java configuration:

\`\`\`java
package example.jmx;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMBeanExport
@EnableAsync
@EnableTransactionManagement
public class JmxAopTestConfiguration {

    @Bean(name = "managementTaskExecutor")
    public Executor managementTaskExecutor() {
        ThreadPoolTaskExecutor executor =
            new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("management-async-");
        executor.initialize();
        return executor;
    }
}
\`\`\`

Cần cấu hình một **transaction manager** phù hợp với môi trường. Trong integration test thật, có thể dùng \`DataSourceTransactionManager\` với database embedded hoặc transaction manager của JPA. Chỉ gắn \`@EnableTransactionManagement\` chưa tạo transaction manager nếu không có bean đáp ứng.

Nếu ứng dụng đã dùng Spring Boot, một phần transaction/async/JMX config có thể được auto-configured hoặc do project định nghĩa. Không tạo thêm exporter trùng \`ObjectName\` khi Boot đã export các MBeans tương ứng.

### 6.1. Lưu ý về Spring profile trong test

\`\`\`java
@Profile("test")
@EnableMBeanExport
@Configuration
public class TestOnlyJmxConfig {
}
\`\`\`

Profile giúp giới hạn probe vào môi trường test. Tuy nhiên nó **không phải security boundary** nếu một exporter khác vẫn xuất bean này. Nên chỉ đăng ký bean probe trong test ApplicationContext, thay vì giữ nó trong application component scan của production khi không cần.

## 7. Kiểm tra trước khi invoke: MBeanInfo

Một integration test nên kiểm tra operation tồn tại đúng signature trước khi thực thi:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "com.example.jobs:type=Probe,name=Aop"
);

if (!server.isRegistered(name)) {
    throw new AssertionError("JMX probe is not registered");
}

MBeanInfo info = server.getMBeanInfo(name);

boolean hasTransactionProbe = false;
boolean hasAsyncProbe = false;

for (MBeanOperationInfo operation : info.getOperations()) {
    if ("probeTransaction".equals(operation.getName())
            && operation.getSignature().length == 0
            && "boolean".equals(operation.getReturnType())) {
        hasTransactionProbe = true;
    }

    if ("probeAsyncThread".equals(operation.getName())
            && operation.getSignature().length == 0
            && "java.lang.String".equals(
                operation.getReturnType())) {
        hasAsyncProbe = true;
    }
}

if (!hasTransactionProbe || !hasAsyncProbe) {
    throw new AssertionError(
        "Missing expected JMX AOP operations"
    );
}
\`\`\`

Kiểm tra metadata là bước không có tác dụng nghiệp vụ trực tiếp, còn \`invoke\` thì có thể chạy code. Phải phân biệt hai loại test, nhất là trong môi trường có side effect.

## 8. Kiểm thử transaction thực sự active qua JMX

Giả sử integration test đã tạo Spring context với JMX exporter, \`TransactionalJobService\` và một transaction manager phù hợp. Thực hiện:

\`\`\`java
Object value = server.invoke(
    name,
    "probeTransaction",
    new Object[0],
    new String[0]
);

if (!Boolean.TRUE.equals(value)) {
    throw new AssertionError(
        "Transaction advice was not applied"
    );
}
\`\`\`

Điểm quan trọng:

1. **Không chỉ assert \`@Transactional\` có trên method.** Cần chứng minh transaction active trong body.
2. **Đảm bảo service là Spring-managed proxy.** Nếu tự \`new TransactionalJobService()\`, annotation không được xử lý bởi Spring AOP.
3. **Test method bản thân không nên mở transaction theo cách che lỗi.** Nếu JUnit test có \`@Transactional\`, một lời gọi local đồng thread có thể kế thừa transaction sẵn có, khiến probe trả true dù transaction advice của service không hoạt động.
4. **Kiểm tra đúng transaction manager.** Một transaction active theo Spring không đồng nghĩa thao tác database thực tế có commit/rollback đúng nếu cấu hình sai.
5. **Kiểm tra đường đi qua JMX.** Gọi trực tiếp service trong test không chứng minh MBean exporter đang dispatch qua proxy như dự kiến.

### 8.1. Tránh false positive do transactional test

Ví dụ dễ gây hiểu lầm:

\`\`\`java
@Transactional
@Test
void jmxOperationUsesTransaction() {
    boolean active = (Boolean) server.invoke(
        name,
        "probeTransaction",
        new Object[0],
        new String[0]
    );
    assertTrue(active);
}
\`\`\`

Test trên có thể trả true vì **transaction do test framework mở sẵn**, không phải vì \`TransactionalJobService\` được advice. Cách tốt hơn là test không \`@Transactional\` trên test method, để service tự mở transaction theo proxy khi được gọi.

Nếu cần kiểm tra rollback, hãy sử dụng một repository/database thật trong test với tình huống rollback có kiểm soát, sau đó đọc dữ liệu sau transaction để xác nhận. Chỉ kiểm tra \`isActualTransactionActive()\` là bước tối thiểu, không thay thế bài kiểm tra transaction semantics.

## 9. Kiểm thử async thực sự chuyển thread qua JMX

Giả sử test chạy trên thread:

\`\`\`text
Test thread: main
\`\`\`

Trong \`AsyncJobService.runAsyncStep()\`, trả lại tên thread đã chạy body. JMX operation gọi:

\`\`\`java
Object value = server.invoke(
    name,
    "probeAsyncThread",
    new Object[0],
    new String[0]
);

String workerThread = (String) value;

if (!workerThread.startsWith("management-async-")) {
    throw new AssertionError(
        "Expected async executor thread, got: "
            + workerThread
    );
}
\`\`\`

Điều này minh họa chứng cứ mạnh hơn so với việc chỉ thấy method trả \`CompletableFuture\`.

Tuy nhiên cần hiểu:

- \`probeAsyncThread()\` trong adapter vẫn có thể chạy đồng bộ trên thread caller rồi **block đợi** service async.
- \`@Async\` có hiệu lực ở method của service nếu lời gọi đi qua proxy async và executor đúng.
- Nếu executor là \`SyncTaskExecutor\`, một số lời gọi async có thể thực thi ngay trên thread caller theo chính sách executor, nên kỳ vọng “khác thread” cần gắn với executor đã chọn.
- Việc đọc tên thread là kỹ thuật test minh họa; khi production cần cơ chế quan sát ổn định hơn như ID/counter/status.
- Một operation trả về \`Future\` trực tiếp qua JMX có thể khó tương thích với các JMX open types/client. Với API quản trị, thường nên trả ID của tác vụ rồi đọc trạng thái qua một attribute/operation riêng.

## 10. Mẫu production: request/status thay vì chờ async

Một operation JMX nên có hợp đồng rõ về việc **nhận yêu cầu** và **hoàn thành tác vụ**.

Ví dụ:

\`\`\`java
public interface ReindexAdminMBean {
    String requestReindex();
    String getRequestStatus(String requestId);
}
\`\`\`

Implementation có thể:

1. Kiểm tra quyền và trạng thái hệ thống.
2. Tạo request ID duy nhất, giới hạn số task đồng thời.
3. Đẩy công việc sang executor/queue có giám sát.
4. Trả request ID ngay cho JMX client.
5. Cung cấp trạng thái \`QUEUED\`, \`RUNNING\`, \`SUCCEEDED\`, \`FAILED\`.
6. Lưu exception đã sanitize và thời điểm bắt đầu/kết thúc.
7. Cho phép truy vấn trạng thái thay vì retry operation tạo task mới.

\`\`\`text
JMX invoke requestReindex()
          |
          v
Return requestId
          |
          +----> async execution
                     |
                     v
               transactional service
                     |
                     v
               persistent state / result

JMX getRequestStatus(id) -> trạng thái quan sát
\`\`\`

Mẫu này tránh timeout giả do JConsole phải đợi một task dài; vẫn cần xử lý task đã chạy nhưng client mất kết nối trước khi nhận ID.

## 11. Proxy type: JDK dynamic proxy và CGLIB

Spring AOP có thể tạo:

- **JDK dynamic proxy:** proxy theo interface.
- **CGLIB subclass proxy:** proxy bằng subclass của target class, khi cấu hình cho phép.

Các kiểu proxy này khác nhau về những method có thể được truy cập từ proxy và cách introspection thấy annotation.

Ví dụ service:

\`\`\`java
public interface ImportOperations {
    boolean execute();
}

@Service
public class ImportOperationsImpl
        implements ImportOperations {

    @Override
    @Transactional
    public boolean execute() {
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }

    public void internalOnly() {
        // Not part of the JDK proxy interface.
    }
}
\`\`\`

Nếu sử dụng JDK proxy, bean injected theo \`ImportOperations\` thường cung cấp method \`execute()\`, không mặc nhiên cho phép gọi \`internalOnly()\` qua interface proxy. Với CGLIB, class proxy có thể hiện diện thêm public methods nhưng điều đó không tự quyết định JMX exporter nên công bố những gì.

### 11.1. Vì sao có thể thiếu operation?

Khi exporter hoặc assembler introspect **proxy class** thay vì **target class**, annotation hoặc interface quản trị có thể được phát hiện khác đi. Cần kiểm tra:

- Bean thực tế có phải AOP proxy không.
- \`AopUtils.isAopProxy(bean)\` và \`AopUtils.getTargetClass(bean)\`.
- Exporter chọn object proxy hay target.
- \`MBeanInfo\` thực tế có đúng operation không.
- JMX operation được dispatch tới đúng proxy đã có advice không.

Một cách giảm phức tạp: **tách JMX management adapter thành bean riêng, không áp advice phức tạp lên adapter; adapter inject transactional/async service proxies**. Như vậy operation JMX có interface rõ, còn transaction/async ở service boundary.

## 12. Self-invocation và @Async

Ví dụ:

\`\`\`java
@Service
public class BatchService {

    public void submit() {
        runAsync();
    }

    @Async
    public void runAsync() {
        // Intended async work.
    }
}
\`\`\`

Khi \`submit()\` và \`runAsync()\` ở cùng object, \`this.runAsync()\` có thể bypass Spring proxy, làm \`runAsync()\` chạy đồng bộ.

Để sửa theo thiết kế:

\`\`\`java
@Service
public class BatchSubmissionService {

    private final BatchWorker batchWorker;

    public BatchSubmissionService(BatchWorker batchWorker) {
        this.batchWorker = batchWorker;
    }

    public void submit() {
        batchWorker.runAsync();
    }
}

@Service
public class BatchWorker {

    @Async
    public void runAsync() {
        // Executed through Spring async proxy.
    }
}
\`\`\`

Đường đi qua bean khác rõ ràng hơn và dễ test.

**Không dùng \`AopContext.currentProxy()\` tùy tiện để “sửa” self-invocation**; nó phụ thuộc cấu hình expose proxy và tăng kết dính với Spring AOP.

## 13. @Transactional và @Async kết hợp: transaction thuộc thread nào?

Spring transaction truyền thống thường gắn với **thread** hiện tại. Khi một method \`@Async\` được thực thi trên thread khác, nó không tự mang theo transaction context của caller.

\`\`\`text
Thread A (JMX caller)
    |
    | MBean invoke
    v
Management adapter
    |
    +--> @Async service proxy
               |
               v
         Thread B (executor)
               |
               +--> @Transactional method/proxy
                         |
                         v
                    Transaction active
                    trong Thread B
\`\`\`

Nếu method \`@Transactional\` nằm trên service được gọi **từ trong async worker thread qua Spring proxy**, transaction của worker có thể bắt đầu trên thread B.

Ngược lại, một transaction mở trên thread A **không được tự động truyền** sang B. Do đó test phải kiểm tra transaction trong **worker thread**, không chỉ trong caller thread.

### 13.1. Ví dụ tách async và transaction bằng hai bean

\`\`\`java
@Service
public class AsyncCoordinator {

    private final TransactionalWorker worker;

    public AsyncCoordinator(TransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("managementTaskExecutor")
    public CompletableFuture<Boolean> run() {
        boolean inTx = worker.executeInTransaction();
        return CompletableFuture.completedFuture(inTx);
    }
}

@Service
public class TransactionalWorker {

    @Transactional
    public boolean executeInTransaction() {
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }
}
\`\`\`

JMX adapter gọi \`asyncCoordinator.run()\` qua injected Spring proxy và đợi kết quả trong test. Nếu trả \`true\`, điều đó hỗ trợ xác nhận transaction đang hoạt động ở worker execution path; cần thêm database assertions nếu mục tiêu là xác nhận commit/rollback.

## 14. Kiểm thử cả việc async và transaction xảy ra trong cùng workflow

Định nghĩa DTO kết quả dành riêng cho test nội bộ:

\`\`\`java
public record ExecutionProbeResult(
    String callerThread,
    String workerThread,
    boolean transactionActive
) {}
\`\`\`

Với JMX API, không nên trả DTO tùy ý qua một MBean thông thường nếu client không có class tương ứng. Một cách là dùng \`CompositeData\`, MXBean/OpenType hoặc **chuyển DTO thành String** trong một operation chỉ dùng cho test.

Ví dụ JMX operation trong lab có thể trả:

\`\`\`text
callerThread=main;
workerThread=management-async-1;
transactionActive=true
\`\`\`

Nhưng test code nên phân tích dữ liệu có cấu trúc thay vì kiểm tra substring tùy tiện. Nếu test trực tiếp service layer, DTO Java bình thường có thể phù hợp hơn.

Điều quan trọng là đừng chỉ kiểm tra:

\`\`\`java
assertTrue(future.isDone());
\`\`\`

vì một \`Future\` hoàn thành ngay vẫn có thể được tạo bởi code chạy đồng bộ. Phải xác nhận **thread execution** và **transaction activity** tại đúng điểm.

## 15. MBeanServer.invoke là lời gọi đồng bộ tại tầng JMX

Một điểm dễ gây hiểu nhầm: dù logic bên dưới có \`@Async\`, bản thân:

\`\`\`java
server.invoke(name, "run", new Object[0], new String[0]);
\`\`\`

vẫn là lời gọi JMX đồng bộ cho đến khi operation MBean trả kết quả/exception. Nếu operation chỉ gửi task sang async executor rồi trả nhanh, JMX invoke nhanh. Nếu operation gọi \`future.get()\`, JMX invoke vẫn block đợi.

Điều đó ảnh hưởng tới:

- Timeout của JConsole/client.
- Thread phục vụ JMX request và nguy cơ cạn tài nguyên.
- Retry sau lỗi không chắc task đã chạy hay chưa.
- Cách hiển thị kết quả và trạng thái.
- Khả năng đóng ứng dụng trong lúc task còn chạy.

Vì thế operation có side effect nên cung cấp ranh giới rõ giữa “yêu cầu đã được chấp nhận” và “nghiệp vụ đã hoàn tất”.

## 16. Xử lý exception khi gọi operation qua JMX

Khi operation được invoke, JMX có thể bọc exception trong các loại:

- \`MBeanException\`: lỗi checked exception từ managed resource hoặc wrapper tương ứng.
- \`RuntimeMBeanException\`: runtime exception từ MBean.
- \`ReflectionException\`: lỗi khi tìm/gọi method hoặc signature.
- \`InstanceNotFoundException\`: ObjectName chưa đăng ký hoặc đã bị unregister.
- \`RuntimeErrorException\`: \`Error\` nghiêm trọng từ MBean.
- \`SecurityException\`: lỗi quyền.

Ví dụ:

\`\`\`java
import javax.management.MBeanException;
import javax.management.RuntimeMBeanException;

try {
    Object value = server.invoke(
        name,
        "probeTransaction",
        new Object[0],
        new String[0]
    );
    System.out.println(value);

} catch (MBeanException ex) {
    Exception target = ex.getTargetException();
    System.err.println("Managed operation failed: " + target);

} catch (RuntimeMBeanException ex) {
    RuntimeException target = ex.getTargetException();
    System.err.println("Managed runtime error: " + target);
}
\`\`\`

Nếu exception phát sinh trong thread async **sau khi** JMX operation đã trả kết quả, client JMX không nhất thiết nhận được exception ấy trực tiếp. Cần trạng thái task, log/audit hoặc kết quả \`Future\` mà caller thực sự đợi.

### 16.1. Lỗi transaction

Lỗi transaction manager, datasource hoặc rollback có thể xuất hiện trong cause chain. Với proxy, các lỗi này có thể được wrap thêm bởi Spring transaction/AOP/JMX layers.

Không nên viết test chỉ so sánh một exception message cố định; nên assert loại lỗi và trạng thái dữ liệu sau rollback.

### 16.2. Lỗi async

Nếu method \`@Async\` trả \`CompletableFuture\`, exception có thể được thể hiện qua future khi \`join()\` hoặc \`get()\`. Nếu method \`@Async\` trả \`void\`, lỗi xảy ra sau khi gửi task có thể được chuyển tới \`AsyncUncaughtExceptionHandler\` nếu được cấu hình.

Không mặc định rằng JMX invoke trả thành công nghĩa là async task đã thành công.

## 17. Kiểm thử rollback thật với database

Một phép thử “transaction active” là cần nhưng chưa đủ. Để kiểm tra transaction semantics:

1. Dùng embedded/test database như H2 hoặc Testcontainers theo yêu cầu dự án.
2. Service \`@Transactional\` ghi một row mới vào bảng test.
3. Trong cùng method, cố ý ném runtime exception sau khi ghi.
4. Gọi workflow qua JMX operation.
5. Sau khi bắt exception, truy vấn database bằng một transaction/kết nối độc lập.
6. Xác nhận row không tồn tại (rollback).
7. So sánh với một control path nếu cần.

Ví dụ ý tưởng:

\`\`\`java
@Transactional
public void writeThenFail(long taskId) {
    repository.insert(taskId);
    throw new IllegalStateException("rollback probe");
}
\`\`\`

JMX adapter gọi service này qua proxy. Nếu chưa có transaction advice, insert có thể commit ngay tùy datasource/autocommit; test sẽ phát hiện row không được rollback.

**Quan trọng:** nếu JUnit test method cũng có \`@Transactional\`, test có thể rollback dữ liệu theo transaction bên ngoài, tạo false positive. Hãy kiểm tra rollback trong một test không bị transaction của test framework che mất và kiểm tra bằng kết nối độc lập.

## 18. Kiểm thử concurrency và propagation

Transaction behavior có thể phụ thuộc \`propagation\`:

- \`REQUIRED\`: tham gia transaction hiện có hoặc tạo transaction mới.
- \`REQUIRES_NEW\`: tạm đình chỉ transaction hiện tại (nếu có) và tạo transaction riêng khi proxy/advice áp dụng.
- \`SUPPORTS\`: sử dụng transaction nếu đã tồn tại; không nhất thiết tạo transaction mới.
- \`NOT_SUPPORTED\`: thực thi không trong transaction theo semantics cấu hình.
- \`MANDATORY\`: yêu cầu transaction hiện có.

Khi kiểm thử JMX, nếu không kiểm soát transaction của caller, \`SUPPORTS\` có thể cho ra kết quả khác nhau giữa test có transaction và invocation từ JConsole không có transaction sẵn.

Với \`@Async\`, kiểm tra transaction trong thread worker theo đúng propagation và transaction manager. Một test chỉ dùng \`TransactionSynchronizationManager.isActualTransactionActive()\` không mô tả toàn bộ isolation/commit behavior; thêm database assertions nếu cần.

### 18.1. ThreadLocal và security context

AOP transaction thường dựa trên thread-bound resources; async chuyển thread làm thay đổi context. Các giá trị \`ThreadLocal\` như transaction context, request context, logging MDC và security context không tự động được truyền nguyên vẹn sang executor.

Nếu một JMX operation dựa vào \`RequestContextHolder\` của HTTP request, nó có thể không hoạt động vì lời gọi JMX không phải HTTP request. Nếu ứng dụng cần truyền security principal hoặc correlation context sang async task, phải cấu hình cơ chế propagation an toàn và được kiểm thử; không nên copy toàn bộ context chứa dữ liệu nhạy cảm một cách vô điều kiện.

## 19. Tách JMX adapter khỏi AOP service: thiết kế dễ test

Một cấu trúc có thể duy trì:

\`\`\`text
MBeanServer
    |
    v
@ManagedResource ManagementAdapter
    |
    +--> Read-only attributes
    |
    +--> Controlled operations
              |
              v
       Business service interface
              |
              v
       Spring AOP proxy
          /       \
         /         \
 Transaction      Async
    advice        advice
         \         /
          \       /
           v     v
        Target service
\`\`\`

Các lợi ích:

- Management interface được công bố tối thiểu.
- Logic transaction nằm trong service phù hợp, tránh đưa logic DB vào JMX getter.
- Async được điều phối bởi executor có tên và lifecycle rõ.
- Test có thể mock service ở mức unit test, rồi dùng real proxy/DB trong integration test.
- Thay đổi Spring AOP target class ít ảnh hưởng metadata JMX của adapter.
- Không cần phơi bày toàn bộ service methods cho JMX client.

JMX adapter cần tránh method cho phép thực thi arbitrary SQL, shell command, đổi file path hoặc tùy tiện sửa dữ liệu quan trọng; nếu có nghiệp vụ quản trị cần thiết, phải có authorization, validation và audit.

## 20. Integration test Spring Boot end-to-end

Một test định hướng với \`@SpringBootTest\`:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    properties = {
        "spring.jmx.enabled=true"
    }
)
class JmxAopIntegrationTest {

    @Test
    void jmxOperationRunsTransactionalService() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Probe,name=Aop"
        );

        assertTrue(server.isRegistered(name));

        Object result = server.invoke(
            name,
            "probeTransaction",
            new Object[0],
            new String[0]
        );

        assertEquals(Boolean.TRUE, result);
    }

    @Test
    void jmxOperationCallsAsyncExecutor() throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.jobs:type=Probe,name=Aop"
        );

        Object result = server.invoke(
            name,
            "probeAsyncThread",
            new Object[0],
            new String[0]
        );

        String thread = (String) result;
        assertTrue(thread.startsWith("management-async-"));
    }
}
\`\`\`

Bài test cần project có \`JmxAopProbe\`, \`TransactionalJobService\`, \`AsyncJobService\`, transaction manager và executor được cấu hình như các phần trước. Với Spring Boot, tùy version, JMX auto-configuration có thể cần property để bật như ví dụ.

**Không chạy song song nhiều context sử dụng cùng \`ObjectName\`** trong platform MBeanServer mà không có chiến lược isolation; có thể gây \`InstanceAlreadyExistsException\`.

## 21. Một số lỗi thường gặp và hướng xử lý

| Biểu hiện | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| \`@Transactional\` không active | Self-invocation, object không phải proxy, transaction manager thiếu hoặc cấu hình advice sai. | Tách service, inject Spring bean, xác minh transaction manager. |
| \`@Async\` chạy trên caller thread | Self-invocation, thiếu \`@EnableAsync\`, executor synchronous hoặc proxy không áp dụng. | Kiểm tra đường gọi qua proxy và executor. |
| JMX operation không xuất hiện | Bean không export, sai assembler, proxy metadata khác target. | \`getMBeanInfo\`, \`ObjectName\`, exporter. |
| JMX invoke báo \`ReflectionException\` | Sai operation/signature, method không được công bố. | Đọc signature runtime. |
| \`InstanceNotFoundException\` | MBean chưa register hoặc đã unregister. | Kiểm tra lifecycle và đúng MBeanServer. |
| Test transaction pass nhưng production fail | Test method có transaction sẵn, không tái hiện đường gọi JMX thực. | Bỏ \`@Transactional\` trên test, dùng DB assertions. |
| JMX invoke trả thành công nhưng task async fail | Task hoàn thành sau khi method trả, exception không chuyển tới client. | Dùng request/status và kiểm tra future/log. |
| Async task vẫn chạy sau shutdown | Executor lifecycle chưa được quản lý đúng. | Cấu hình graceful shutdown, cancel, status. |
| MBean bị đăng ký trùng | Boot exporter và custom exporter hoặc test contexts dùng chung server. | Một owner cho ObjectName, cleanup đúng. |
| Operation block lâu trong JConsole | \`future.get\` hoặc DB transaction dài trong operation. | Thiết kế async request/observe, timeout phù hợp. |
| SecurityContext không có ở worker | Context không tự truyền qua thread. | Dùng propagation strategy có chủ đích, không copy secrets. |

## 22. Quy trình kiểm thử từng tầng

Để chẩn đoán một lỗi JMX + AOP, đi theo thứ tự:

\`\`\`text
1. Spring bean có tồn tại?
          |
          v
2. Bean được proxy không?
          |
          v
3. Exporter đăng ký MBean đúng ObjectName?
          |
          v
4. MBeanInfo có operation/signature đúng?
          |
          v
5. MBeanServer.invoke gọi được không?
          |
          v
6. Advice transaction/async thực sự kích hoạt?
          |
          v
7. Business state / DB / Future kết quả đúng?
          |
          v
8. Exception, audit, cleanup được xử lý?
\`\`\`

Mỗi tầng có công cụ quan sát riêng. Khi một operation không có trong MBeanInfo, kiểm tra exporter/assembler trước; khi operation có nhưng transaction không active, kiểm tra proxy/self-invocation/transaction manager; khi async chạy sai thread, kiểm tra executor và lời gọi qua proxy.

## 23. Kiểm thử hợp đồng và bảo mật

Trong môi trường có dữ liệu thật, nên:

1. **Chỉ export operation quản trị cần thiết.** Không phơi toàn bộ business service qua reflection.
2. **Đọc MBeanInfo trước khi invoke.** Đây là inspection không chạy operation.
3. **Giới hạn side effect.** Test mutation dùng database/test environment cô lập.
4. **Xác thực và phân quyền.** Remote JMX phải có TLS, authentication và quyền phù hợp.
5. **Không retry mù.** Timeout có thể xảy ra sau khi operation đã bắt đầu.
6. **Log có cấu trúc.** Ghi ObjectName, operation, loại lỗi, không ghi secret.
7. **Quan sát async tasks.** Không suy luận thành công chỉ từ việc request được nhận.
8. **Kiểm tra rollback và trạng thái cuối.** Đọc kết quả qua đường độc lập khi test transaction.
9. **Dọn MBean sau test.** Close ApplicationContext, tránh registry leak.
10. **Không dùng production để thực nghiệm destructive operation.**

Một bài test security có thể khẳng định operation nội bộ như \`deleteAllRecords\` không xuất hiện trong \`MBeanInfo.getOperations()\`. Với DynamicMBean, còn cần bảo đảm code \`invoke\` từ chối tên không được phép dù metadata không công bố.

## 24. Bài tập thực hành

### Bài tập 1 — Xác minh transaction qua JMX

Tạo \`TransactionalJobService\` và \`JmxAopProbe\`. Kết nối MBeanServer local, gọi \`probeTransaction()\` và kiểm tra trả \`true\` khi transaction manager cấu hình đúng.

**Mục tiêu:** chứng minh JMX invocation đi qua transaction proxy.

### Bài tập 2 — Self-invocation

Đặt \`@Transactional\` trên method nội bộ được một method cùng class gọi qua \`this\`. So sánh kết quả với thiết kế tách service bean.

**Mục tiêu:** nhận diện vì sao advice bị bypass.

### Bài tập 3 — Async executor

Cấu hình \`managementTaskExecutor\` với thread prefix riêng. Gọi operation \`probeAsyncThread()\` và assert thread name thuộc executor.

**Mục tiêu:** chứng minh method body thực sự chuyển thread.

### Bài tập 4 — Transaction trong async thread

Tạo \`AsyncCoordinator\` gọi \`TransactionalWorker\`. Trả về kết quả chứa thread name và transaction active, kiểm tra cả hai trong test.

**Mục tiêu:** không nhầm transaction của caller với worker.

### Bài tập 5 — Rollback bằng database

Tạo table test, viết trong transaction rồi ném runtime exception. Gọi workflow qua JMX, sau đó dùng kết nối độc lập kiểm tra row không tồn tại.

**Mục tiêu:** kiểm tra transaction behavior thật, không chỉ annotation.

### Bài tập 6 — Proxy và MBeanInfo

Thử JDK proxy và class proxy trong môi trường test. So sánh \`MBeanInfo\` và danh sách operation; kiểm tra không có method nội bộ bị phơi bày.

**Mục tiêu:** hiểu tác động proxy lên JMX metadata.

### Bài tập 7 — Async lỗi sau khi JMX đã trả

Tạo task async ném exception sau delay. JMX operation chỉ trả request ID. Theo dõi status để quan sát failure.

**Mục tiêu:** hiểu lỗi bất đồng bộ không tự trở thành lỗi JMX invoke.

## 25. Câu hỏi ôn tập

**1. Vì sao có \`@Transactional\` trên method vẫn chưa đủ?** Vì transaction advice phải được cấu hình và lời gọi phải đi qua Spring proxy phù hợp.

**2. Self-invocation ảnh hưởng JMX thế nào?** JMX có thể gọi một method ngoài, nhưng method đó tự gọi method transaction/async trong cùng object khiến advice bị bypass.

**3. \`MBeanServer.invoke\` có tự khởi tạo transaction không?** Không. Nó dispatch JMX operation; transaction do Spring advice/transaction manager áp dụng nếu đường gọi phù hợp.

**4. \`@Async\` có làm \`MBeanServer.invoke\` luôn trả ngay không?** Không. JMX operation có thể block đợi \`Future\` hoặc thực hiện logic đồng bộ trước khi trả.

**5. Làm sao biết \`@Async\` thực sự chạy trên worker thread?** Ghi nhận thread thực thi trong method body và so sánh với executor đã cấu hình.

**6. Transaction mở ở caller thread có tự truyền sang async thread không?** Không, Spring transaction thông thường gắn với thread; cần transaction trong worker theo đường advice riêng.

**7. Tại sao test method \`@Transactional\` có thể gây false positive?** Vì transaction test framework mở sẵn có thể làm probe trả true dù service advice không hoạt động.

**8. Vì sao không nên xuất \`Future\` trực tiếp qua JMX operation?** Tính tương thích kiểu dữ liệu/serializable/open types có thể không phù hợp client; request ID/status thường dễ quản lý hơn.

**9. Nếu JMX invoke trả thành công, async task chắc chắn thành công chưa?** Chưa. Task có thể thất bại sau khi operation trả.

**10. Cách nào kiểm tra hợp đồng JMX?** Dùng \`MBeanServer.getMBeanInfo\` để xem operation/signature, thuộc tính và những API không được phép xuất.

## 26. Tổng kết

Kiểm thử **JMX cùng Spring AOP, transaction và async** cần kiểm tra cả **đường dispatch JMX** lẫn **đường proxy/advice**. Annotation trên source code không chứng minh hành vi runtime. Một phép kiểm tra tốt đọc MBeanInfo, invoke operation qua MBeanServer trong môi trường cô lập, xác nhận transaction active tại đúng method và async chạy trên executor mong đợi.

Khi kết hợp transaction và async, cần nhớ transaction thông thường gắn với thread; async không tự kế thừa transaction của caller. Đối với production, giữ JMX adapter nhỏ, gọi transactional/async services qua Spring proxy, thiết kế operation dạng request/status khi cần, kiểm soát quyền và kiểm thử cả commit/rollback, exception và lifecycle cleanup.

## Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework Reference — Transaction Declarative Annotations: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Javadoc — \`EnableAsync\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html
- Spring Framework Javadoc — \`EnableTransactionManagement\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html
- Java SE 21 — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html