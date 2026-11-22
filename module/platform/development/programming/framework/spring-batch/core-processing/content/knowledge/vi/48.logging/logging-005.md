# Gắn job execution ID vào log trong Spring Batch

## 1. Vì sao log của batch cần job execution ID?

Một ứng dụng Spring Batch thường chạy cùng một job nhiều lần: theo lịch hằng ngày, theo yêu cầu của người vận hành, khi restart sau lỗi hoặc khi nhiều nhóm dữ liệu được xử lý song song. Nếu log chỉ có tên job, chẳng hạn \`importOrdersJob\`, rất khó biết một dòng log thuộc lần chạy nào.

Ví dụ không có mã nhận diện execution:

~~~text
02:00:01 INFO  Import started
02:00:03 INFO  Loaded 1000 orders
02:00:05 WARN  Risk service timeout
02:00:06 INFO  Import started
02:00:09 INFO  Loaded 1000 orders
02:00:12 INFO  Import finished
02:00:13 ERROR Import failed
~~~

Trong ví dụ này, hai lần chạy xen kẽ; không thể xác định chính xác dòng \`Import finished\` và \`Import failed\` thuộc execution nào nếu chỉ nhìn nội dung thông báo.

Sau khi gắn **job execution ID**:

~~~text
02:00:01 INFO  jobExecutionId=801 jobName=importOrdersJob event=job.started
02:00:03 INFO  jobExecutionId=801 jobName=importOrdersJob event=orders.loaded count=1000
02:00:05 WARN  jobExecutionId=801 jobName=importOrdersJob event=risk.timeout
02:00:06 INFO  jobExecutionId=802 jobName=importOrdersJob event=job.started
02:00:09 INFO  jobExecutionId=802 jobName=importOrdersJob event=orders.loaded count=1000
02:00:12 INFO  jobExecutionId=802 jobName=importOrdersJob event=job.finished
02:00:13 ERROR jobExecutionId=801 jobName=importOrdersJob event=job.failed
~~~

Bây giờ có thể lọc toàn bộ log theo \`jobExecutionId=801\`, ghép với metadata của Spring Batch và điều tra những Step, chunk, lần retry hoặc lời gọi dịch vụ đã góp phần gây lỗi.

Trong bối cảnh **Spring Batch Core Processing → Logging**, gắn ID vào log nhằm:

- **Truy vết chính xác một lần thực thi** dù có nhiều job cùng tên hoặc chạy đồng thời.
- **Liên kết log với JobRepository** qua khóa \`BATCH_JOB_EXECUTION.JOB_EXECUTION_ID\`.
- **Khoanh vùng lỗi theo Step**, chunk, item hoặc nguồn dữ liệu mà không trộn hai lần chạy.
- **Phân biệt restart**: một JobInstance có thể có nhiều JobExecution.
- **Hỗ trợ vận hành**: từ một cảnh báo, truy ra log, trạng thái, counter, exception và bản output của execution liên quan.

Job execution ID là **metadata kỹ thuật do Spring Batch cấp**, không phải khóa dữ liệu nghiệp vụ. Không nên tự sinh UUID rồi gọi đó là \`jobExecutionId\` nếu giá trị không tương ứng với JobRepository.

## 2. Phân biệt các loại ID thường xuất hiện

Spring Batch cung cấp nhiều cấp độ nhận diện:

| Trường | Ý nghĩa | Có thay đổi khi restart? | Ví dụ |
|---|---|---|---|
| \`jobName\` | Tên định nghĩa của job | Thường không | \`importOrdersJob\` |
| \`jobInstanceId\` | Công việc logic với tên job và bộ identifying JobParameters | Thường **không** khi restart cùng instance | \`200\` |
| \`jobExecutionId\` | Khóa của **một lần chạy** JobInstance | **Có**: restart tạo execution mới | \`801\`, sau đó \`805\` |
| \`stepName\` | Tên Step trong job | Thường không | \`loadOrdersStep\` |
| \`stepExecutionId\` | Khóa của **một lần chạy Step** | Có thể thay đổi ở lần chạy/restart tiếp theo | \`3401\` |
| \`batchId\` | Khóa lô nghiệp vụ do ứng dụng định nghĩa | Phụ thuộc nghiệp vụ; thường giữ nguyên khi restart cùng lô | \`ORD-20261116\` |
| \`traceId\` / \`correlationId\` | Liên kết request, message và lời gọi dịch vụ | Phụ thuộc cơ chế tracing | \`trace-...\` |

Ví dụ một JobInstance xử lý lô đơn hàng \`ORD-20261116\`:

~~~text
JobInstance 200: importOrdersJob
identifying JobParameters: batchId=ORD-20261116
       |
       +-- JobExecution 801
       |       StepExecution 3401: loadOrdersStep
       |       Status: FAILED
       |
       +-- JobExecution 805 (restart)
               StepExecution 3419: loadOrdersStep
               Status: COMPLETED
~~~

Hai lần chạy có cùng \`jobInstanceId=200\` nhưng \`jobExecutionId\` khác nhau. Vì vậy:

- Dùng **jobExecutionId** khi phân tích một lần chạy và exception của nó.
- Dùng **jobInstanceId** hoặc **batchId** khi nối lịch sử các lần thử của cùng một công việc.
- Dùng **stepExecutionId** khi nhiều Step hoặc partition có cùng tên nhưng nhiều execution.
- Dùng **traceId** cho lời gọi giữa các dịch vụ; nó có thể tồn tại đồng thời với các ID của Spring Batch.

Không đưa \`jobExecutionId\` vào \`JobParameters\` để nhận diện instance: framework tạo ID này khi đăng ký JobExecution. Nếu tự thêm một tham số identifying mới vào lần chạy lại, bạn có thể vô tình tạo **JobInstance khác** và không còn restart đúng checkpoint cũ.

## 3. Job execution ID có từ thời điểm nào?

Spring Batch lưu JobExecution trong **JobRepository** và cấp khóa nhận diện execution. Khi một job thực sự được bắt đầu qua hạ tầng chuẩn, \`JobExecution.getId()\` thường đã có giá trị trong các callback của \`JobExecutionListener\`.

Quy trình khái quát:

~~~text
Scheduler / REST endpoint / CLI
             |
             v
       JobLauncher.run(...)
             |
             v
JobRepository tạo JobExecution
  - gắn jobExecutionId
  - liên kết JobInstance
             |
             v
JobExecutionListener.beforeJob(...)
             |
             v
        StepExecution
             |
             v
      Reader -> Processor -> Writer
             |
             v
JobExecutionListener.afterJob(...)
             |
             v
       JobRepository lưu trạng thái
~~~

Có thể có log ở **trước khi JobExecution được tạo**, ví dụ khi ứng dụng nhận yêu cầu chạy batch hoặc kiểm tra tham số. Các log đó chưa có \`jobExecutionId\`; hãy dùng một **requestId/correlationId** để nối tới log \`job.created\` sau khi JobRepository trả về ID.

Ví dụ:

~~~text
event=batch.launch.requested requestId=req-27 jobName=importOrdersJob
event=batch.launch.accepted  requestId=req-27 jobExecutionId=801
event=job.started             jobExecutionId=801
~~~

Nếu launcher hoạt động bất đồng bộ, lời gọi \`run(...)\` có thể trả về trước khi job hoàn tất. Giá trị ID và trạng thái nhận được tại thời điểm đó không đảm bảo là kết quả cuối cùng. ID vẫn là chìa khóa để theo dõi execution về sau qua JobExplorer.

## 4. Cách cơ bản: ghi ID trực tiếp trong thông báo

Trong callback có sẵn đối tượng \`JobExecution\`, cách đơn giản nhất là đưa ID vào tham số logger:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class SimpleJobLogListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(SimpleJobLogListener.class);

    @Override
    public void beforeJob(JobExecution execution) {
        log.info("event=job.started jobExecutionId={} jobName={}",
                execution.getId(),
                execution.getJobInstance().getJobName());
    }

    @Override
    public void afterJob(JobExecution execution) {
        log.info("event=job.finished jobExecutionId={} status={}",
                execution.getId(),
                execution.getStatus());
    }
}
~~~

Ưu điểm là dễ hiểu, không phụ thuộc cấu hình MDC, dùng được cả khi test logger đơn giản. Nhược điểm: mỗi lệnh \`log.info(...)\` trong reader, processor, writer và nhiều lớp dịch vụ đều phải nhận/truyền ID một cách tường minh. Dễ quên gắn ID ở một số nơi, khiến log khó lọc.

Khi muốn ID tự động xuất hiện trong mọi log trên một luồng xử lý, có thể sử dụng **Mapped Diagnostic Context (MDC)** của SLF4J với backend logging hỗ trợ, điển hình là Logback.

## 5. MDC là gì và cách nó hoạt động?

**MDC** là một tập khóa/giá trị gắn với ngữ cảnh logging của thread hiện tại. Khi log được ghi, pattern hoặc JSON encoder có thể lấy các giá trị này để thêm vào log record mà code không cần truyền lại ở mọi thông báo.

Ví dụ:

~~~java
import org.slf4j.MDC;

MDC.put("jobExecutionId", "801");
MDC.put("jobName", "importOrdersJob");

log.info("Reading input file");
log.info("Writing approved orders");

MDC.remove("jobExecutionId");
MDC.remove("jobName");
~~~

Nếu Logback pattern có \`%X{jobExecutionId}\`, hai dòng log trên đều có \`jobExecutionId=801\`.

**Điểm quan trọng:** MDC thông thường gắn với **thread**, không phải tự động gắn với một JobInstance hay JobExecution. Từ đó phát sinh ba yêu cầu:

1. **Đặt đúng giá trị** khi thread bắt đầu xử lý một execution.
2. **Dọn giá trị trong \`finally\` hoặc callback kết thúc** để thread được tái sử dụng không mang ID cũ sang job mới.
3. **Truyền MDC sang thread khác** nếu Step, task executor, async processor hoặc worker dùng thread pool.

MDC cũng không tự biến JobRepository thành log store. Nó chỉ giúp logger thêm ngữ cảnh; dữ liệu trạng thái thực tế vẫn thuộc metadata Spring Batch.

### Tại sao không dùng biến static để giữ ID?

~~~java
// Không nên dùng:
static Long currentJobExecutionId;
~~~

Trong một JVM có thể có nhiều JobExecution cùng lúc. Biến global bị ghi đè và khiến log của job A mang ID của job B. MDC theo thread hoặc tham số truyền qua các thành phần được thiết kế rõ ràng tránh lỗi này.

## 6. Gắn MDC bằng JobExecutionListener và StepExecutionListener

Trong ứng dụng batch, **JobExecutionListener** phù hợp để ghi các sự kiện bắt đầu/kết thúc job; **StepExecutionListener** phù hợp để gắn ngữ cảnh khi logic của một Step chạy.

Ví dụ dưới đây dùng một listener thực hiện cả hai interface:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchExecutionMdcListener
        implements JobExecutionListener, StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchExecutionMdcListener.class);

    private static String value(Object object) {
        return object == null ? "unknown" : object.toString();
    }

    @Override
    public void beforeJob(JobExecution execution) {
        logJobEvent("job.started", execution);
    }

    @Override
    public void afterJob(JobExecution execution) {
        logJobEvent("job.finished", execution);
    }

    private void logJobEvent(String event, JobExecution execution) {
        // Chỉ đặt MDC trong phạm vi callback này.
        // MDC.MDCCloseable tự remove khi ra khỏi try.
        try (MDC.MDCCloseable id =
                     MDC.putCloseable("jobExecutionId",
                             value(execution.getId()));
             MDC.MDCCloseable name =
                     MDC.putCloseable("jobName",
                             execution.getJobInstance().getJobName())) {

            log.info("event={} status={}", event, execution.getStatus());
        }
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        JobExecution jobExecution = stepExecution.getJobExecution();

        MDC.put("jobExecutionId", value(jobExecution.getId()));
        MDC.put("jobInstanceId",
                value(jobExecution.getJobInstance().getId()));
        MDC.put("jobName",
                jobExecution.getJobInstance().getJobName());
        MDC.put("stepExecutionId", value(stepExecution.getId()));
        MDC.put("stepName", stepExecution.getStepName());

        log.info("event=step.started");
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        try {
            log.info(
                    "event=step.finished status={} read={} write={} skip={}",
                    stepExecution.getStatus(),
                    stepExecution.getReadCount(),
                    stepExecution.getWriteCount(),
                    stepExecution.getSkipCount());
        } finally {
            // Chỉ xóa những key mà listener này quản lý.
            MDC.remove("stepName");
            MDC.remove("stepExecutionId");
            MDC.remove("jobName");
            MDC.remove("jobInstanceId");
            MDC.remove("jobExecutionId");
        }
        return null; // Không thay đổi ExitStatus của Step.
    }
}
~~~

Hai callback job đặt MDC **chỉ trong khoảng thời gian ghi log sự kiện job**. Hai callback Step đặt MDC cho thời gian thực thi Step theo mô hình xử lý tuần tự thông thường. Vì vậy, log của reader, processor và writer chạy **cùng thread** với Step có thể nhận \`jobExecutionId\`, \`stepExecutionId\` từ MDC.

Thiết kế này chủ động tránh giả định rằng \`beforeJob\` và các Step luôn được chạy trên cùng thread. Với job flow bất đồng bộ, partition hoặc thread pool, cần xem cách truyền MDC ở các phần tiếp theo.

**Lưu ý về vòng đời:** \`afterStep\` là nơi dọn MDC thông thường, nhưng nếu tiến trình bị kill hoặc framework không gọi được callback vì lỗi đặc biệt, sẽ không có cơ hội dọn theo đường đi đó. Đối với code tự tạo thread/task, cần dùng \`try/finally\` để dọn hoặc khôi phục MDC tại ranh giới task. Không gọi \`MDC.clear()\` bừa bãi nếu cùng thread còn có traceId hoặc context của thư viện observability khác.

### Đăng ký listener vào Job và Step

Giả sử các bean \`orderReader\`, \`orderProcessor\`, \`orderWriter\`, \`jobRepository\` và \`transactionManager\` đã được cấu hình:

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, ImportedOrder> orderProcessor,
        ItemWriter<ImportedOrder> orderWriter,
        BatchExecutionMdcListener batchLoggingListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, ImportedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .listener((StepExecutionListener) batchLoggingListener)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        BatchExecutionMdcListener batchLoggingListener) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .listener((JobExecutionListener) batchLoggingListener)
            .build();
}
~~~

\`OrderRow\` và \`ImportedOrder\` là các kiểu dữ liệu nghiệp vụ minh họa; đoạn cấu hình trên cần đặt trong class \`@Configuration\` phù hợp. Cách dựng builder minh họa API Spring Batch 5+.

Việc ép kiểu sang \`JobExecutionListener\` và \`StepExecutionListener\` giúp chọn rõ overload \`.listener(...)\` khi một class triển khai cả hai interface. Nếu mỗi Step dùng listener khác hoặc dự án đã có convention riêng, giữ một quy tắc đặt tên MDC thống nhất.

## 7. Hiển thị job execution ID bằng Logback

Đặt MDC vào thread mới là một nửa công việc; logger phải được cấu hình để **đưa key MDC ra log**. Với Spring Boot dùng Logback, có thể khai báo pattern tùy chỉnh trong \`logback-spring.xml\`:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>
                %d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX}
                %-5level
                [thread=%thread]
                [jobExecutionId=%X{jobExecutionId:-none}]
                [stepExecutionId=%X{stepExecutionId:-none}]
                [jobName=%X{jobName:-none}]
                %logger{36} - %msg%n
            </pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Ví dụ cố ý dùng XML độc lập để chỉ ra trường MDC; trong dự án có sẵn \`logback-spring.xml\`, nên tích hợp pattern vào appender thực tế, giữ cấu hình profile, async appender và chính sách rotation đã có.

Ký pháp \`%X{jobExecutionId:-none}\` đọc key trong MDC; nếu key chưa có, hiển thị \`none\`. Một log dự kiến:

~~~text
2026-11-16T02:00:03.120+07:00 INFO
[thread=main] [jobExecutionId=801]
[stepExecutionId=3401] [jobName=importOrdersJob]
c.example.OrderProcessor - Reading order O001
~~~

Giá trị \`none\` là bình thường với log khởi động ứng dụng hoặc request đến trước khi JobExecution được tạo. Đừng gán một ID giả cho các sự kiện chưa thuộc execution nào.

### Structured JSON logging

Trong hệ thống thu thập log tập trung, **JSON log** thuận tiện vì \`jobExecutionId\` có thể trở thành field có thể query. Ví dụ hình thức log mong muốn:

~~~json
{
  "timestamp": "2026-11-16T02:00:03.120+07:00",
  "level": "INFO",
  "logger": "com.example.batch.OrderProcessor",
  "message": "order processed",
  "jobName": "importOrdersJob",
  "jobExecutionId": "801",
  "jobInstanceId": "200",
  "stepName": "importOrdersStep",
  "stepExecutionId": "3401",
  "orderId": "O001"
}
~~~

Đây là ví dụ cấu trúc log mong muốn, **không phải output mặc định của mọi phiên bản Spring Boot**. Với JSON encoder hoặc structured logging được dự án hỗ trợ, hãy cấu hình inclusion của MDC fields và kiểm tra log thực tế. Một số encoder tự đưa toàn bộ MDC vào object, một số yêu cầu khai báo field được phép; một số dùng MDC trong object lồng nhau.

Quy ước tên field, định dạng ID và timezone cần thống nhất giữa ứng dụng, log pipeline và truy vấn dashboard. Nếu \`jobExecutionId\` được xuất là chuỗi, truy vấn cũng nên coi nó là chuỗi, tránh kiểu dữ liệu thay đổi tùy collector.

## 8. Lấy ID trong code khi đang ở Step

Trong \`StepExecutionListener\`, ta đã nhận trực tiếp \`StepExecution\`. Trong các bean được tạo theo scope của Step, Spring Batch cũng cung cấp **StepContext** cho những tác vụ cần truy cập metadata.

Ví dụ khi code đang chạy trong thread có **StepContext** của Spring Batch:

~~~java
import java.util.Optional;

import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.core.scope.context.StepSynchronizationManager;

public final class BatchExecutionIds {

    private BatchExecutionIds() {
    }

    public static Optional<Long> currentJobExecutionId() {
        StepContext context = StepSynchronizationManager.getContext();
        if (context == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(
                context.getStepExecution()
                        .getJobExecution()
                        .getId());
    }
}
~~~

Phương thức trên hữu ích trong thành phần có ngữ cảnh Step hợp lệ, nhưng không nên được dùng tùy tiện từ scheduler, background callback hay thread được tạo thủ công: **StepSynchronizationManager là context gắn với luồng thực thi**, không phải kho toàn cục.

Trong các thành phần cần ID thường xuyên, tốt hơn là truyền ID qua tham số request hoặc inject đối tượng scoped phù hợp thay vì đọc context bất kỳ lúc nào. Cũng không nên để singleton processor giữ một biến \`currentExecutionId\` mutable khi nhiều execution có thể chạy cùng lúc.

### Gắn thêm khóa item cho một đoạn log

Với item cần điều tra, có thể đặt một MDC key trong phạm vi ngắn:

~~~java
import org.slf4j.MDC;

public ImportedOrder process(OrderRow order) {
    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("orderId", order.orderId())) {

        log.debug("event=order.processing");
        return transform(order);
    }
}
~~~

\`transform\` là hàm nghiệp vụ minh họa. Khi thoát khối \`try\`, MDC key \`orderId\` được xóa kể cả khi processor ném exception. Phương thức mẫu giả định không có context trước đó dùng **cùng key** \`orderId\`; nếu có nested scope với cùng tên key, cần lưu và phục hồi giá trị trước thay vì chỉ remove.

Không gắn nguyên nội dung item, số thẻ thanh toán, token hoặc dữ liệu cá nhân vào MDC. Ngay cả các khóa nghiệp vụ cũng nên được xem xét theo mức độ nhạy cảm và chính sách log của hệ thống.

## 9. MDC và các thread khác nhau trong Spring Batch

Một nhầm lẫn phổ biến là nghĩ \`MDC.put(...)\` trong \`beforeJob\` sẽ tự xuất hiện trong mọi Step, partition và request async. Thực tế, MDC phổ biến dựa vào **ThreadLocal**: thread khác thường không nhận được context mới trừ khi có cơ chế truyền phù hợp.

Ví dụ:

~~~text
JobLauncher thread A
  JobExecution 801
  MDC(jobExecutionId=801)
      |
      +-- Step chạy ở thread A
      |     --> Log thường nhìn thấy ID
      |
      +-- Worker thread B (task executor)
      |     --> Không mặc nhiên có MDC của thread A
      |
      +-- Remote worker process C
            --> Cần truyền correlation/context qua giao thức
~~~

Với một Step dùng \`taskExecutor\` để chạy các chunk song song, một cách phổ biến là dùng **TaskDecorator** sao chép MDC tại thời điểm tạo task, rồi **khôi phục MDC cũ của worker thread** sau khi task kết thúc.

### TaskDecorator truyền và phục hồi MDC

~~~java
import java.util.Map;

import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable delegate) {
        // Snapshot từ thread tạo task.
        Map<String, String> callingContext =
                MDC.getCopyOfContextMap();

        return () -> {
            // Worker thread có thể đã được pool tái sử dụng.
            Map<String, String> previousContext =
                    MDC.getCopyOfContextMap();

            try {
                if (callingContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(callingContext);
                }

                delegate.run();
            } finally {
                // Không để ID của batch này rò sang task tiếp theo.
                if (previousContext == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    }
}
~~~

Điểm quan trọng là snapshot \`callingContext\` được lấy **trước khi task chạy** và restore context trước đó trong \`finally\`. Chỉ gọi \`MDC.setContextMap()\` mà không khôi phục sẽ làm thread pool lưu ID cũ cho một task thuộc job khác.

Đăng ký decorator trên một \`ThreadPoolTaskExecutor\`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean
public TaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

Đối với Step đa luồng, cấu hình \`taskExecutor\` vào builder tương ứng và bảo đảm reader/writer cùng các thành phần stateful đủ an toàn cho truy cập đồng thời. **TaskDecorator chỉ giải quyết ngữ cảnh logging**, không làm reader trở thành thread-safe hay bảo đảm transaction/checkpoint an toàn.

Nếu ứng dụng dùng executor khác cho \`@Async\`, \`CompletableFuture\`, AsyncItemProcessor hoặc thư viện HTTP async, cần kiểm tra nơi task thực sự được submit và áp dụng cơ chế truyền context ở **executor đó**. Decorator trên một executor không tự áp dụng cho mọi executor khác.

### Khi sao chép MDC vẫn chưa đủ

Nếu task được submit **trước khi** ID được đặt vào MDC hoặc một callback được thực thi trên thread không đi qua executor có decorator, snapshot sẽ thiếu ID. Khi đó nên:

1. Truyền ID như trường dữ liệu trong command/request nội bộ.
2. Thiết lập MDC tại điểm vào của worker/task dựa trên trường đó.
3. Chạy logic trong \`try/finally\` để dọn context.
4. Kết hợp với trace context propagation nếu ứng dụng đã dùng OpenTelemetry/Micrometer Tracing.

Không sao chép bừa bãi toàn bộ MDC qua ranh giới hệ thống: chỉ truyền những trường được phép, có ý nghĩa và có kích thước kiểm soát được.

## 10. Multi-threaded Step, partitioning và remote chunking

Spring Batch có nhiều kiểu song song, và mỗi kiểu cần xác định ID chính xác theo ranh giới execution.

| Kiểu chạy | Điểm đặt logging context | ID nên có |
|---|---|---|
| Step tuần tự | StepExecutionListener trên thread thực thi Step | jobExecutionId, stepExecutionId, stepName |
| Chunk đa luồng qua TaskExecutor | Step listener + TaskDecorator ở executor chunk | ID của JobExecution và StepExecution hiện tại |
| Parallel flows | Listener trên từng Step được chạy ở thread tương ứng | Một jobExecutionId, nhiều stepExecutionId |
| Local partitioning | Context ở các worker Step/partition | jobExecutionId và stepExecutionId riêng của partition |
| Remote partitioning | Truyền metadata cho worker hoặc đọc StepExecution ở repository chung | ID đúng với execution được phân công |
| Remote chunking | Message headers/correlation của chunk và JobExecution | jobExecutionId, stepExecutionId và messageId nếu phù hợp |

### Ví dụ log phân vùng

~~~text
jobExecutionId=801 stepExecutionId=3401 stepName=load:partition0 read=5000
jobExecutionId=801 stepExecutionId=3402 stepName=load:partition1 read=5000
jobExecutionId=801 stepExecutionId=3403 stepName=load:partition2 read=5000
~~~

Tất cả thuộc cùng JobExecution nhưng mỗi partition có StepExecution riêng. Nếu chỉ gắn \`stepName=load\`, các log có thể trộn nhau và không còn biết partition nào gặp lỗi.

### Truyền context qua message

Với remote chunking, worker nhận message có thể chạy trên JVM/process khác. MDC ở manager không tự đi theo message. Một envelope minh họa:

~~~json
{
  "headers": {
    "correlationId": "req-27",
    "jobExecutionId": "801",
    "stepExecutionId": "3401",
    "chunkId": "chunk-18"
  },
  "payload": {
    "orders": ["O100", "O101"]
  }
}
~~~

Worker chỉ dùng những header đã được xác thực và phù hợp với công việc được giao. Nếu worker dùng chung JobRepository, có thể xác minh execution ID qua metadata; nếu hệ thống tách biệt repository, cần duy trì correlation rõ ràng và không giả định khóa số ở hai database có cùng ý nghĩa.

Worker nhận request, tạo MDC ở phạm vi xử lý message, ghi log, rồi khôi phục MDC trước đó. Khi trả response, giữ \`correlationId\` và mã chunk để manager nối kết quả với yêu cầu ban đầu.

**Không dùng jobExecutionId làm khóa duy nhất cho một message**: một JobExecution có thể phát nhiều chunk/message. Message ID hoặc chunk ID vẫn cần thiết để phân biệt và hỗ trợ idempotency.

## 11. Gắn ID cho sự kiện chunk, retry, skip và lỗi

Job execution ID có giá trị nhất khi các log quan trọng cùng giữ cấu trúc trường:

~~~text
event=chunk.completed jobExecutionId=801 stepExecutionId=3401 read=100 write=98
event=item.skipped jobExecutionId=801 stepExecutionId=3401 reason=INVALID_AMOUNT
event=api.retry jobExecutionId=801 stepExecutionId=3401 attempt=2 dependency=risk-service
event=step.failed jobExecutionId=801 stepExecutionId=3401 errorCode=DB_TIMEOUT
~~~

Với Step listener và MDC đã cấu hình, các lệnh log có thể chỉ ghi thông tin **sự kiện và kết quả**, vì jobExecutionId được log encoder thêm tự động.

Ví dụ dùng \`ChunkListener\` để ghi checkpoint/chunk event:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public class BatchChunkLoggingListener implements ChunkListener {

    private static final Logger log =
            LoggerFactory.getLogger(BatchChunkLoggingListener.class);

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("event=chunk.committed stepName={}",
                context.getStepContext().getStepName());
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("event=chunk.failed stepName={}",
                context.getStepContext().getStepName());
    }
}
~~~

Theo mô hình Step tuần tự và MDC listener đã đăng ký, hai thông báo sẽ có \`jobExecutionId\`. Trong Step đa luồng, cần decorator hoặc thiết lập context trên worker thread để đạt cùng kết quả.

Không nhất thiết ghi INFO sau **mọi chunk**: job có hàng triệu chunk có thể tạo volume log lớn. Có thể ghi DEBUG cho chunk bình thường, INFO cho milestone theo số lượng record, WARN/ERROR khi skip hoặc rollback vượt ngưỡng. Metrics thường phù hợp hơn log dày đặc để đếm throughput.

### Phân biệt retry với nhiều lần thực thi

Khi retry một item trong cùng JobExecution, \`jobExecutionId\` **không thay đổi**. \`attempt=1/2/3\` là số thử của logic retry, không phải một JobExecution khác.

Khi restart sau FAILED/STOPPED, JobExecution mới có ID khác, dù cùng dữ liệu nghiệp vụ. Vì vậy, khi phân tích duplicate hoặc side effect từ API, cần giữ cả \`batchId\`/idempotency key và \`jobExecutionId\`.

### Lỗi xảy ra trước callback afterStep

Không chỉ dựa vào log \`step.finished\` để biết Step có hoàn tất hay không. Nếu process crash, callback không chạy và log cuối cùng có thể mất. Giám sát phải kết hợp metadata JobRepository, heartbeat và trạng thái process; log là bằng chứng hỗ trợ điều tra.

## 12. Truy vết restart từ JobRepository và log

Giả sử lần đầu chạy thất bại và được restart:

~~~text
jobInstanceId=200 jobExecutionId=801 event=job.started
jobInstanceId=200 jobExecutionId=801 event=step.failed
jobInstanceId=200 jobExecutionId=801 event=job.finished status=FAILED

jobInstanceId=200 jobExecutionId=805 event=job.started
jobInstanceId=200 jobExecutionId=805 event=job.finished status=COMPLETED
~~~

Để xem các execution của một JobInstance, có thể truy vấn các bảng metadata mặc định:

~~~sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE ji.JOB_INSTANCE_ID = :jobInstanceId
ORDER BY je.JOB_EXECUTION_ID;
~~~

Kết quả ví dụ:

| JOB_INSTANCE_ID | JOB_EXECUTION_ID | STATUS |
|---:|---:|---|
| 200 | 801 | FAILED |
| 200 | 805 | COMPLETED |

Đây là truy vấn reporting read-only; bảng và cú pháp tham số phải phù hợp với database thực tế. Nếu muốn khoanh vùng Step lỗi:

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Sau khi tìm ra \`JOB_EXECUTION_ID\` và \`STEP_EXECUTION_ID\`, lọc các bản ghi log tương ứng. Không dùng tên job làm điều kiện duy nhất nếu nhiều execution cùng tên chạy đồng thời.

### Thao tác điều tra thực tế

1. Nhận cảnh báo có \`jobName\`, \`jobExecutionId\` và status.
2. Tra JobExecution trong JobRepository bằng \`jobExecutionId\`.
3. Lấy StepExecution gây lỗi và các counter/exception liên quan.
4. Lọc log theo \`jobExecutionId\`, sau đó thu hẹp theo \`stepExecutionId\`.
5. Nếu lỗi liên quan HTTP/Kafka, dùng \`traceId\`, \`correlationId\` hoặc messageId để truy vết xuyên dịch vụ.
6. Đối soát output theo batchId sau khi khắc phục; chỉ log hoàn tất không chứng minh dữ liệu hoàn chỉnh.

## 13. Phân biệt MDC với tracing và metric labels

Ba loại ngữ cảnh thường được dùng cùng nhau nhưng có mục tiêu khác nhau:

| Công cụ | Chức năng chính | ID phù hợp |
|---|---|---|
| **Structured logs/MDC** | Tìm sự kiện chi tiết và liên kết đến execution | jobExecutionId, stepExecutionId, traceId, batchId được phép |
| **Distributed tracing** | Quan sát chuỗi hoạt động xuyên thread/service | traceId, spanId; có thể thêm Batch IDs làm span attributes được kiểm soát |
| **Metrics** | Tổng hợp số lượng, latency, tỷ lệ lỗi | jobName, stepName, status và nhãn ít biến thiên |

**Không đưa jobExecutionId/stepExecutionId làm label của Prometheus metric theo mặc định.** Mỗi execution sinh thêm time series, tạo vấn đề cardinality và retention. ID động phù hợp hơn với log, trace hoặc audit detail.

Nếu ứng dụng đã dùng Micrometer Tracing/OpenTelemetry, MDC có thể đang chứa \`traceId\` và \`spanId\`. Listener ở ví dụ chỉ remove những key riêng của batch; không xóa toàn bộ MDC hoặc ghi đè tên trường tracing.

Khi qua API ngoài, \`jobExecutionId\` không thay thế \`traceparent\` hoặc cơ chế propagation của tracing. Có thể log cùng hai ID, nhưng việc chuyển trace context phải dùng cách mà thư viện tracing hỗ trợ để giữ liên kết span chính xác.

## 14. Cách giữ log có cấu trúc mà không tiết lộ dữ liệu

Các trường nên giữ:

| Trường | Ví dụ | Mức độ phù hợp |
|---|---|---|
| \`jobExecutionId\` | \`801\` | Gần như luôn hữu ích |
| \`jobInstanceId\` | \`200\` | Hữu ích cho restart |
| \`jobName\` | \`importOrdersJob\` | Phục vụ lọc và dashboard |
| \`stepExecutionId\` | \`3401\` | Hữu ích khi Step/partition song song |
| \`stepName\` | \`validateOrderStep\` | Giải thích vị trí xử lý |
| \`batchId\` | \`ORD-20261116\` | Chỉ dùng nếu không chứa thông tin nhạy cảm |
| \`event\` | \`chunk.committed\` | Dễ lập bộ lọc và thống kê |
| \`reasonCode\` | \`INVALID_AMOUNT\` | Tốt hơn log thẳng dữ liệu sai |
| \`traceId\` | ID của trace | Truy vết dịch vụ |

Không đưa toàn bộ JobParameters, raw record, access token, secret, password hoặc PII vào MDC. MDC thường được tự động gắn với **mọi log trên thread**, nên chỉ cần đặt nhầm một giá trị nhạy cảm là nhiều sự kiện có thể bị lộ.

Với thông báo exception:

~~~java
log.error("event=order.import.failed reasonCode={} recordKey={}",
        reasonCode, safeRecordKey, exception);
~~~

Ở đây \`safeRecordKey\` phải là khóa được phép xuất log. Thông báo exception và stack trace vẫn có thể chứa URL, query hoặc payload nhạy cảm do thư viện sinh ra; cần xem xét cách redaction và logging policy.

Không cần log mọi item thành công ở mức INFO nếu batch xử lý hàng triệu bản ghi. Dùng log sự kiện khởi động, kết thúc, milestone, skip có kiểm soát và lỗi; các số đếm nên xuất ra metrics hoặc audit.

## 15. Kiểm thử việc gắn và dọn MDC

Để tránh log mang sai ID, cần kiểm tra việc **set đúng ngữ cảnh** và **dọn sau khi Step kết thúc**. Có thể kiểm thử listener ở mức unit mà không khởi chạy toàn bộ Spring Batch:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.StepExecution;

class BatchExecutionMdcListenerTest {

    private final BatchExecutionMdcListener listener =
            new BatchExecutionMdcListener();

    @AfterEach
    void cleanup() {
        MDC.clear();
    }

    @Test
    void attachesIdsDuringStepAndRemovesThemAfterward() {
        JobInstance jobInstance = mock(JobInstance.class);
        when(jobInstance.getId()).thenReturn(200L);
        when(jobInstance.getJobName()).thenReturn("importOrdersJob");

        JobExecution jobExecution = mock(JobExecution.class);
        when(jobExecution.getId()).thenReturn(801L);
        when(jobExecution.getJobInstance()).thenReturn(jobInstance);

        StepExecution stepExecution = mock(StepExecution.class);
        when(stepExecution.getId()).thenReturn(3401L);
        when(stepExecution.getStepName()).thenReturn("importOrdersStep");
        when(stepExecution.getJobExecution()).thenReturn(jobExecution);

        listener.beforeStep(stepExecution);

        assertEquals("801", MDC.get("jobExecutionId"));
        assertEquals("200", MDC.get("jobInstanceId"));
        assertEquals("3401", MDC.get("stepExecutionId"));
        assertEquals("importOrdersStep", MDC.get("stepName"));

        listener.afterStep(stepExecution);

        assertNull(MDC.get("jobExecutionId"));
        assertNull(MDC.get("jobInstanceId"));
        assertNull(MDC.get("stepExecutionId"));
        assertNull(MDC.get("stepName"));
    }
}
~~~

Ví dụ dùng Mockito/JUnit 5 và giả định backend logging trong test có MDC hoạt động, như Logback. Nó kiểm tra logic listener, **không chứng minh Logback pattern hoặc JSON encoder đã xuất các field**. Cần một test riêng đọc log event hoặc output của logging backend khi muốn xác nhận định dạng log.

### Kiểm thử truyền context qua TaskDecorator

Một unit test có thể đặt \`MDC.put("jobExecutionId","801")\` ở thread tạo task, gọi \`decorate(...)\`, chạy Runnable trên thread khác, xác nhận Runnable thấy \`801\`; sau khi Runnable kết thúc, xác nhận worker thread được khôi phục MDC trước đó.

Các trường hợp nên bao gồm:

- Thread tạo task có MDC và worker chưa có MDC.
- Worker đang có MDC khác; decorator phải restore đúng sau task.
- Runnable ném exception; \`finally\` vẫn dọn context.
- Thread tạo task không có MDC; worker không được giữ ID cũ.
- Hai task liên tiếp thuộc JobExecution 801 và 802 trên cùng worker thread không bị lẫn ID.

Khi dùng executor thật, kiểm thử bằng cơ chế đồng bộ như \`CountDownLatch\` hoặc \`Future.get\` có timeout. Tránh dùng \`Thread.sleep\` để đoán lúc task đã chạy.

### Integration test trong Spring Batch

Với \`spring-batch-test\` và môi trường database test riêng, có thể chạy Job nhỏ qua \`JobLauncherTestUtils\`, sau đó:

1. Kiểm tra \`JobExecution.getId()\` đã được cấp.
2. Lấy \`StepExecution.getId()\` từ execution tương ứng.
3. Thu log phát sinh trong processor/writer hoặc listener, kiểm tra field \`jobExecutionId\` khớp với ID thực.
4. Chạy thêm một JobExecution và xác nhận log không dùng lại ID cũ.
5. Với Step đa luồng, xác nhận log từ worker thực sự chứa ID đúng.
6. Với restart cùng JobInstance, xác nhận JobExecution mới có ID khác và log truy ra được hai attempt.

Đối với Logback, một appender test có thể **chụp MDC map ngay khi sự kiện được ghi**. Nếu lưu raw logging event để kiểm tra về sau, cần biết encoder/appender có thể tính MDC một cách lazy; đừng để việc dọn MDC trước assertion khiến kết quả test hiểu sai.

## 16. Các lỗi thường gặp khi gắn job execution ID

**Chỉ ghi tên job.** Nhiều execution cùng tên có thể chạy chồng nhau. Thêm \`jobExecutionId\` và khi cần \`stepExecutionId\`.

**Dùng jobInstanceId thay jobExecutionId.** Các lần restart cùng JobInstance có thể bị trộn log. Nên giữ cả hai trường nếu cần điều tra lịch sử.

**Tạo jobExecutionId thủ công.** ID không đối chiếu được JobRepository. Sử dụng ID do \`JobExecution.getId()\` cung cấp.

**Gắn ID bằng biến static mutable.** Job chạy đồng thời có thể ghi đè nhau. Dùng MDC theo thread, scoped context hoặc truyền ID qua tham số.

**Đặt MDC nhưng không sửa logging pattern.** Log vẫn không hiện ID. Cấu hình \`%X{jobExecutionId}\` hoặc structured encoder có hỗ trợ MDC.

**Chỉ đặt MDC ở beforeJob rồi cho rằng mọi worker thread đều thấy.** MDC thường không tự truyền qua executor và JVM khác. Cần TaskDecorator hoặc thông điệp correlation.

**Không dọn MDC sau xử lý.** Thread pool tái sử dụng có thể gây log của execution mới mang ID cũ. Dọn hoặc restore trong \`finally\`.

**Gọi MDC.clear() trong shared execution context.** Có thể xóa traceId/spanId từ thư viện observability. Chỉ dọn các key do ứng dụng sở hữu hoặc restore snapshot gốc.

**Đổi identifying JobParameters khi restart chỉ để có ID khác.** Spring Batch tự tạo JobExecution ID mới. Đổi tham số nhận diện có thể tạo JobInstance khác và không resume checkpoint.

**Gắn jobExecutionId làm metric label.** Số lượng time series tăng theo mỗi lần chạy; chỉ giữ ID động trong log/traces/audit.

**Đưa toàn bộ item hoặc JobParameters vào MDC.** Có thể rò rỉ PII, secret và làm log phình lớn. Chọn các trường an toàn, cần thiết.

**Tin rằng log kết thúc luôn tồn tại.** Process crash có thể ngăn afterJob/afterStep chạy. Phải đối chiếu JobRepository và cơ chế liveness khi cần kết luận.

**Không phân biệt partition và StepExecution.** Một job có nhiều StepExecution; \`stepExecutionId\` giúp xác định worker chính xác.

## 17. Quy trình triển khai thực tế

Để chuẩn hóa logging cho một ứng dụng Spring Batch:

1. **Đặt quy ước trường:** \`jobExecutionId\`, \`jobInstanceId\`, \`jobName\`, \`stepExecutionId\`, \`stepName\`; dùng một kiểu và một cách đặt tên xuyên hệ thống.
2. **Gắn listener:** log sự kiện job, thiết lập MDC ở Step và dọn sau Step.
3. **Cấu hình backend logging:** Logback pattern hoặc JSON encoder thực sự xuất các MDC field.
4. **Kiểm tra luồng song song:** TaskExecutor, AsyncItemProcessor, partition, remote chunking và callback cần context propagation tại đúng ranh giới.
5. **Duy trì liên kết restart:** ghi cả jobInstanceId và jobExecutionId; giữ batchId nghiệp vụ nếu an toàn.
6. **Ghi log có mục đích:** start, finish, milestone, skip, retry, rollback và exception với reason code; tránh spam mỗi item.
7. **Liên kết với JobRepository:** từ ID trong log tìm đúng JobExecution, StepExecution, counters và trạng thái.
8. **Bổ sung test:** set/remove MDC, task thread reuse, log pattern, hai execution đồng thời, restart và trạng thái lỗi.
9. **Kiểm soát dữ liệu:** tránh PII/secret và high-cardinality labels trong metrics.
10. **Định nghĩa thao tác điều tra:** từ alert hoặc mã batch, lọc log theo execution và step, rồi nối trace của dịch vụ ngoài khi cần.

Điểm then chốt của việc **gắn job execution ID** là mọi log quan trọng phải có thể truy ngược về **một lần chạy thật trong JobRepository**. Với Spring Batch, kết hợp listener, MDC, cấu hình logger và context propagation phù hợp giúp truy vết chính xác cả Step tuần tự, Step đa luồng và các lần restart, đồng thời giữ được ranh giới giữa metadata kỹ thuật, khóa nghiệp vụ và tracing xuyên dịch vụ.
