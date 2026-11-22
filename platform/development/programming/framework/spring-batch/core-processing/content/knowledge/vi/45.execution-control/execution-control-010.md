# Graceful stop tại checkpoint trong Spring Batch

## 1. Bài toán: dừng job an toàn khi đang xử lý dữ liệu

Trong vận hành Spring Batch, một job có thể xử lý hàng triệu bản ghi trong nhiều phút hoặc nhiều giờ. Người vận hành đôi khi phải dừng job vì cửa sổ bảo trì sắp bắt đầu, nguồn dữ liệu có vấn đề, downstream quá tải hoặc cần chuyển quyền xử lý sang một instance khác. Nếu tiến trình bị kết thúc đột ngột, phần output chưa commit, trạng thái reader và thông tin restart có thể không còn đồng bộ.

**Graceful stop tại checkpoint** là cách yêu cầu Spring Batch kết thúc có kiểm soát, để các đơn vị công việc đã được commit vẫn giữ nguyên, trạng thái khôi phục được lưu và job chuyển sang trạng thái **STOPPED** khi thực sự dừng. Khi có thể restart, job tiếp tục từ trạng thái đã được lưu thay vì bắt đầu lại toàn bộ.

Một luồng đơn giản:

~~~text
Input records
     |
     v
Chunk 1: read -> process -> write -> COMMIT + CHECKPOINT
     |
     v
Chunk 2: read -> process -> write -> COMMIT + CHECKPOINT
     |
     |    <-- nhận yêu cầu STOP
     v
Chunk đang chạy hoàn tất hoặc rollback theo tình huống lỗi
     |
     v
Spring Batch phát hiện yêu cầu dừng
     |
     v
JobExecution: STOPPING -> STOPPED
     |
     v
Khởi động lại cùng JobInstance theo checkpoint hợp lệ
~~~

Từ **graceful** ở đây mô tả việc job hợp tác với cơ chế dừng của framework. Nó không có nghĩa mọi thread sẽ ngắt tức thì tại thời điểm gửi yêu cầu, hoặc một thao tác ghi ra hệ thống ngoài sẽ tự động rollback.

### Tại sao checkpoint là ranh giới quan trọng?

Trong chunk-oriented processing, một **chunk** gồm một nhóm item được đọc, xử lý và ghi trong phạm vi một transaction thích hợp. Sau khi chunk commit thành công, Spring Batch lưu trạng thái cần thiết để khôi phục, điển hình là vị trí đọc trong **ExecutionContext** của Step.

Với cấu hình chunk size = 100:

- Chunk đầu tiên có thể ghi và commit các bản ghi 1–100.
- Chunk tiếp theo xử lý 101–200.
- Khi có lệnh stop trong lúc chunk thứ hai chạy, framework thường cần đến điểm kiểm tra ngắt trước khi Step kết thúc. Ranh giới checkpoint an toàn là trạng thái đã được ghi nhận qua commit.
- Khi restart, reader có khả năng khôi phục trạng thái được lưu và xử lý tiếp các bản ghi cần thiết.

Đừng mặc định rằng một lệnh stop sẽ bảo đảm chính xác số bản ghi đã xử lý bằng bội số của 100: chunk cuối có thể ngắn hơn, có filter/skip/retry, có commit bị rollback hoặc có xử lý đa luồng. Tập dữ liệu output đã commit mới là bằng chứng kết quả.

## 2. Phân biệt graceful stop, fail, shutdown và kill

| Cách kết thúc | Cách kích hoạt | Trạng thái thường gặp | Khả năng khôi phục |
|---|---|---|---|
| Graceful stop của Spring Batch | JobOperator.stop(executionId) hoặc Step được yêu cầu terminate hợp lệ | STOPPING rồi STOPPED | Restart từ checkpoint nếu Job/Step hỗ trợ |
| Lỗi trong Step | Exception không được xử lý hoặc vượt retry/skip limit | FAILED | Có thể restart nếu cấu hình cho phép |
| Job chạy thành công | Toàn bộ flow hoàn thành | COMPLETED | Không restart lại cùng JobInstance đã hoàn thành theo cách thông thường |
| Yêu cầu dừng sau Step hiện tại | Cấu hình flow hoặc JobOperator stop, tùy cách tổ chức | STOPPED khi dừng thành công | Resume theo flow và trạng thái Step |
| Kill tiến trình, SIGKILL, crash máy | Bên ngoài framework kết thúc đột ngột | Metadata có thể còn STARTED/STARTING | Có thể cần xử lý trạng thái và dữ liệu dở dang trước restart |

**STOPPING là trạng thái đang chuyển tiếp**, không phải bằng chứng đã dừng hoàn toàn. Hệ thống điều phối chỉ được phép khởi động công việc thay thế hoặc công bố kết quả theo chính sách khi xác nhận execution thực sự đã chuyển sang trạng thái kết thúc phù hợp.

**COMPLETED khác STOPPED.** Khi STOPPED, một phần dữ liệu có thể đã commit, nhưng chưa phải output đầy đủ của toàn job. Consumer không nên tự coi phần output đó là một batch đã hoàn thành.

## 3. Những thành phần tham gia vào quá trình dừng

Trong Spring Batch có các thành phần chính:

| Thành phần | Vai trò trong graceful stop |
|---|---|
| JobOperator | Giao diện điều khiển job, nhận yêu cầu stop/restart |
| JobRepository | Lưu JobInstance, JobExecution, StepExecution và metadata |
| JobExplorer | Đọc các thông tin execution để giám sát trạng thái |
| JobExecution | Trạng thái của một lần chạy job, có thể chuyển STARTED → STOPPING → STOPPED |
| StepExecution | Trạng thái, counter, ExecutionContext của Step |
| ExecutionContext | Dữ liệu trạng thái được lưu để khôi phục reader/writer/processor khi cần |
| ItemStream | Hợp đồng open, update, close cho thành phần stateful |
| PlatformTransactionManager | Quản lý commit/rollback của chunk đối với tài nguyên tham gia transaction |
| ChunkListener | Hook trước/sau chunk, hữu ích khi muốn kiểm tra tín hiệu dừng sau commit |

**JobInstance** là một công việc logic được nhận diện bởi tên Job và identifying JobParameters. **JobExecution** là một lần thử chạy JobInstance. Nếu execution trước ở trạng thái STOPPED và job restartable, restart thường tạo **JobExecution mới thuộc cùng JobInstance**.

Để stop/restart hoạt động ổn định giữa tiến trình điều khiển và tiến trình batch, cả hai phải truy cập **cùng JobRepository**. Chỉ đọc một bản ghi local hoặc gửi lệnh tới một tiến trình dùng repository khác sẽ không điều khiển được job mục tiêu.

## 4. Gửi lệnh stop bằng JobOperator

Đối với job đang chạy, cơ chế chuẩn là gửi lệnh dừng theo **jobExecutionId**, không dùng jobName đơn thuần khi có nhiều lần chạy hoặc nhiều job đồng thời.

Ví dụ một service ứng dụng dùng Spring Batch:

~~~java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchExecutionControlService {

    private final JobOperator jobOperator;

    public BatchExecutionControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId) throws Exception {
        // Yêu cầu dừng, kết quả true không có nghĩa job đã STOPPED.
        return jobOperator.stop(executionId);
    }

    public Long restartStoppedExecution(long stoppedExecutionId)
            throws Exception {
        return jobOperator.restart(stoppedExecutionId);
    }
}
~~~

Ở đây chữ ký exception được đơn giản hóa để tập trung vào luồng điều khiển; trong ứng dụng nên xử lý các exception Spring Batch cụ thể như **NoSuchJobExecutionException**, **JobExecutionNotRunningException**, **JobRestartException** và các điều kiện restart khác.

Ví dụ điều khiển:

~~~text
POST /operations/batch-executions/831/stop

1. Xác nhận executionId 831 thuộc batch được phép điều khiển.
2. Gọi JobOperator.stop(831).
3. Ghi nhận yêu cầu dừng; trả trạng thái "stop requested".
4. Theo dõi JobExplorer/JobRepository.
5. Chỉ khi trạng thái thực tế STOPPED mới báo "stopped".
~~~

Không nên trả HTTP 200 với ý nghĩa “đã dừng xong” ngay sau lời gọi stop, vì stop là yêu cầu hợp tác. Endpoint quản trị cần xác thực và phân quyền riêng để tránh dừng nhầm job.

### Điều gì xảy ra sau lời gọi stop?

Khi được chấp nhận, yêu cầu stop được phản ánh trong trạng thái execution (thường là **STOPPING**); quá trình job đang chạy phát hiện trạng thái đó tại điểm kiểm tra ngắt của Spring Batch, kết thúc Step theo cơ chế dừng và cuối cùng ghi trạng thái **STOPPED** nếu không phát sinh tình huống khác.

Thời gian dừng phụ thuộc vào:

- Chunk hiện tại lớn hay nhỏ.
- Reader, processor và writer có đang chờ I/O hoặc gọi API ngoài.
- Transaction commit hoặc rollback có bị chậm.
- Tasklet có vòng lặp dài mà không kiểm tra tín hiệu dừng.
- Job có nhiều Step, partition hoặc worker từ xa cần phối hợp.

Nếu thread đang kẹt vô hạn trong một lời gọi mạng, JobOperator không thể bảo đảm dừng ngay; cần timeout ở tầng client và cơ chế hợp tác trong code.

## 5. Thiết kế Step có checkpoint khôi phục được

Ví dụ job đọc file CSV đơn hàng và ghi vào database. Mỗi bản ghi có mã và số tiền; job nhận **inputFile** và **batchId** làm identifying JobParameters.

File dữ liệu:

~~~csv
orderId,amount
O001,100.00
O002,45.50
O003,80.00
O004,25.00
O005,10.00
~~~

Bảng đích:

~~~sql
CREATE TABLE imported_order (
    batch_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);
~~~

Khóa (batch_id, order_id) giúp phát hiện hoặc ngăn duplicate theo phạm vi batch. Tuy nhiên, **unique constraint tự nó không làm writer idempotent**: nếu replay một bản ghi đã ghi, lệnh INSERT thông thường vẫn có thể thất bại. Cần quy tắc upsert hoặc kiểm tra idempotency khi hạ tầng có nguy cơ lặp thao tác.

### 5.1. Reader lưu vị trí đọc

Ví dụ dùng Spring Batch theo phong cách builder hỗ trợ JobRepository và transaction manager:

~~~java
import java.math.BigDecimal;

public record OrderRow(String orderId, BigDecimal amount) {
}
~~~

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<OrderRow> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderRow>()
            .name("checkpointableOrderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderRow(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

**saveState(true)** cho phép reader tham gia cơ chế lưu trạng thái vào Step ExecutionContext khi chunk checkpoint. Tên reader phải ổn định để nhận diện các key trạng thái khi restart. **@StepScope** giúp tạo instance gắn với StepExecution và bind job parameter đúng thời điểm.

Nếu tắt lưu trạng thái hoặc sử dụng custom reader không hỗ trợ **ItemStream**, restart có thể đọc lại từ đầu hoặc không khôi phục được chính xác vị trí. Với reader delegate bị ẩn trong một composite, cần bảo đảm stream được đăng ký với Step để các callback open/update/close được gọi.

### 5.2. Writer tham gia transaction của Step

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
@StepScope
public ItemWriter<OrderRow> orderWriter(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return chunk -> {
        for (OrderRow order : chunk) {
            jdbcTemplate.update(
                    """
                    INSERT INTO imported_order (batch_id, order_id, amount)
                    VALUES (?, ?, ?)
                    """,
                    batchId,
                    order.orderId(),
                    order.amount());
        }
    };
}
~~~

Khi **JdbcTemplate** sử dụng datasource được quản lý bởi cùng transaction manager của chunk, các thao tác ghi của chunk sẽ commit hoặc rollback cùng transaction. Ví dụ dùng INSERT để dễ quan sát trạng thái commit; hệ thống thực tế cần bổ sung chính sách chống duplicate khi restart/retry.

### 5.3. Step và Job

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<OrderRow> orderReader,
        ItemWriter<OrderRow> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderRow, OrderRow>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}

@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .build();
}
~~~

Với file ví dụ chỉ có năm item và chunk size 100, job thường xử lý tất cả trong một chunk rồi kết thúc; **khó quan sát stop giữa nhiều checkpoint**. Trong bài kiểm thử checkpoint nên dùng nhiều item hơn hoặc chunk size nhỏ, chẳng hạn 2, để tạo nhiều commit thật.

### Khi nào checkpoint thực sự được lưu?

Một chunk thành công có các bước khái quát:

1. Reader trả các item của chunk.
2. Processor và writer xử lý các item theo cấu hình.
3. ItemStream cập nhật trạng thái cần khôi phục vào ExecutionContext.
4. Transaction commit, cùng metadata được cập nhật theo cấu hình repository/transaction.
5. Job tiếp tục chunk kế tiếp hoặc xử lý tín hiệu dừng.

Điểm mấu chốt là **khôi phục từ trạng thái bền vững gần nhất**, không phải từ vị trí chỉ đang giữ trong bộ nhớ. Nếu tài nguyên nghiệp vụ và JobRepository dùng các transaction riêng, cần xem xét rủi ro commit thành công ở một nơi nhưng checkpoint chưa bền vững ở nơi khác.

## 6. Cách dừng sau commit của một chunk có chủ đích

Khi cần một tín hiệu “dừng tại checkpoint gần nhất” do nghiệp vụ đặt ra, có thể kiểm tra stop flag sau một chunk commit thành công. **ChunkListener.afterChunk** là vị trí hữu ích vì callback này được gọi sau khi chunk commit thành công trong xử lý chunk tiêu chuẩn.

Ví dụ có một service dùng chung để tra cứu tín hiệu dừng:

~~~java
public interface StopSignal {
    boolean isStopRequested(String batchId);
}
~~~

Listener:

~~~java
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class CheckpointStopListener implements ChunkListener {

    private final StopSignal stopSignal;

    public CheckpointStopListener(StopSignal stopSignal) {
        this.stopSignal = stopSignal;
    }

    @Override
    public void afterChunk(ChunkContext context) {
        Object rawBatchId = context.getStepContext()
                .getJobParameters().get("batchId");

        if (rawBatchId instanceof String batchId
                && stopSignal.isStopRequested(batchId)) {
            context.getStepContext()
                    .getStepExecution()
                    .setTerminateOnly();
        }
    }
}
~~~

Đăng ký listener lên Step:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, OrderRow>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .listener(checkpointStopListener)
        .build();
~~~

Đoạn này thay phần tạo Step ở mục 5.3. Phương thức **setTerminateOnly()** đánh dấu StepExecution cần kết thúc; framework sẽ kiểm tra tại điểm xử lý ngắt của Step. Sử dụng cơ chế này khi ứng dụng đã có stop signal riêng, còn đối với yêu cầu quản trị từ bên ngoài, **JobOperator.stop(executionId)** thường là API điều khiển phù hợp hơn.

Một số lưu ý:

- Không chặn vô hạn trong afterChunk, vì listener cũng là một phần của vòng đời Step.
- Tín hiệu dừng phải gắn với **batchId/executionId** chính xác, tránh dừng nhầm job chạy đồng thời.
- Với **chunk size = 100**, stop flag có thể được bật trong lúc xử lý chunk; listener chỉ nhìn thấy ở ranh giới sau commit.
- Có khoảng thời gian nhỏ giữa các điểm kiểm tra ngắt; không nên cam kết dừng ngay một số thứ tự record tuyệt đối nếu luồng xử lý phức tạp.
- Với Step chạy đa luồng, nhiều partition hoặc remote worker, việc “dừng đồng thời mọi worker tại một checkpoint toàn cục” cần cơ chế phối hợp riêng. Mỗi partition có thể có checkpoint của chính nó.

**Không dùng Thread.stop(), System.exit(), kill -9 hoặc đóng thẳng datasource** làm cơ chế graceful stop. Chúng có thể làm gián đoạn commit hoặc bỏ qua quá trình cập nhật trạng thái restart.

## 7. Theo dõi STOPPING đến STOPPED

Lời gọi stop là yêu cầu điều khiển; hệ thống giám sát cần đọc trạng thái sau đó. Ví dụ code polling mang tính minh họa:

~~~java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public BatchStatus currentStatus(
        JobExplorer jobExplorer,
        long executionId) {

    JobExecution execution = jobExplorer.getJobExecution(executionId);
    if (execution == null) {
        throw new IllegalArgumentException(
                "Unknown job execution: " + executionId);
    }
    return execution.getStatus();
}
~~~

Một controller hoặc scheduler có thể gọi phương thức này định kỳ với timeout và chu kỳ polling có giới hạn. Tránh vòng lặp bận gọi JobRepository hàng nghìn lần mỗi giây. Cần xử lý trường hợp status chuyển sang FAILED do lỗi khác khi đang STOPPING.

| Trạng thái quan sát được | Cách diễn giải |
|---|---|
| STARTING / STARTED | Job chưa dừng; yêu cầu stop có thể chưa đến hoặc chưa được thực thi |
| STOPPING | Stop đã được yêu cầu/đang xử lý; không khởi chạy execution thay thế ngay |
| STOPPED | Đã dừng có kiểm soát; kiểm tra điều kiện restart trước khi gọi restart |
| FAILED | Job thất bại; điều tra lỗi trước khi quyết định restart |
| COMPLETED | Job đã kết thúc thành công; có thể hoàn tất trước khi stop được xử lý |
| UNKNOWN / ABANDONED | Cần xử lý vận hành theo trạng thái repository; không tự coi là resumable |

**ExitStatus** và **BatchStatus** là hai khái niệm khác nhau. Một flow có thể sử dụng exit code tùy chỉnh; khi quyết định job còn đang chạy hoặc có thể restart, cần dựa vào trạng thái execution và chính sách job, không chỉ nhìn một chuỗi exit code.

### Stop có phải lúc nào cũng được chấp nhận?

Không. ExecutionId có thể không tồn tại, job đã kết thúc, hoặc trạng thái hiện tại không cho phép stop. Cần xử lý lỗi và kiểm tra lại repository thay vì lặp yêu cầu stop vô hạn. Khi nhiều tác nhân điều khiển cùng một execution, có thể xảy ra race: job hoàn tất tự nhiên ngay trước khi lệnh stop được áp dụng.

## 8. Restart từ checkpoint sau STOPPED

Để tiếp tục một job đã stop, sử dụng cơ chế restart của Spring Batch với **cùng JobInstance**. Với JobOperator:

~~~java
long stoppedExecutionId = 831L;
Long newExecutionId = jobOperator.restart(stoppedExecutionId);
~~~

Hành vi mong đợi:

~~~text
JobInstance(importOrdersJob, identifying parameters)
        |
        +-- JobExecution #831: STOPPED
        |       StepExecution importOrdersStep
        |       ExecutionContext: reader position đã checkpoint
        |
        +-- JobExecution #844: STARTED ... COMPLETED
                importOrdersStep khôi phục vị trí đã lưu
                output cuối hoàn thiện
~~~

Điều kiện restart an toàn thường bao gồm:

1. Job được cấu hình **restartable**, không bị chặn bởi chính sách restart.
2. JobRepository và ExecutionContext từ lần chạy trước còn nguyên.
3. Reader/writer hoặc các thành phần stateful cần thiết hỗ trợ phục hồi.
4. Input không bị thay đổi nội dung hoặc thứ tự đối với reader sử dụng checkpoint vị trí.
5. Output đã commit trước đó còn nhất quán, và writer tránh ghi trùng khi replay.
6. Các Step downstream chưa hoàn tất và flow routing được định nghĩa rõ.

**Không tạo JobInstance mới bằng cách thêm tham số random rồi gọi đó là restart.** Một JobInstance mới có thể đọc lại từ đầu vì không kế thừa checkpoint của instance cũ.

### Mối quan hệ với allowStartIfComplete và startLimit

Trong job nhiều Step, Step đã **COMPLETED** ở execution trước thường được bỏ qua khi restart, trừ khi cấu hình như **allowStartIfComplete(true)** khiến Step đó chạy lại. **startLimit** có thể giới hạn số lần khởi động một Step. Nếu dùng Step kiểm tra hoặc cleanup bắt buộc chạy lại, cần thiết kế flow và các tùy chọn restart theo nghiệp vụ.

Không thay đổi tùy tiện cấu trúc Job hoặc tên Step giữa STOPPED và restart, vì metadata cũ được định danh bằng những tên này và có thể làm resume khó dự đoán.

## 9. Stateful reader/writer và ExecutionContext

**ExecutionContext** là nơi Spring Batch lưu các giá trị có thể tuần tự hóa cần cho việc restart. Nó có scope theo StepExecution và JobExecution. Trong chunk processing, thành phần triển khai **ItemStream** có thể cập nhật trạng thái vào context bằng **update(ExecutionContext)** trước checkpoint.

Ví dụ custom reader duy trì chỉ số:

~~~java
import java.util.List;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public class IndexedOrderReader implements ItemStreamReader<OrderRow> {

    private static final String POSITION = "indexedOrderReader.position";

    private final List<OrderRow> items;
    private int index;

    public IndexedOrderReader(List<OrderRow> items) {
        this.items = items;
    }

    @Override
    public OrderRow read() {
        if (index >= items.size()) {
            return null;
        }
        return items.get(index++);
    }

    @Override
    public void open(ExecutionContext executionContext) {
        index = executionContext.containsKey(POSITION)
                ? executionContext.getInt(POSITION)
                : 0;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(POSITION, index);
    }

    @Override
    public void close() {
        // Không có tài nguyên bên ngoài cần giải phóng.
    }
}
~~~

Reader ví dụ này giả định **List input bất biến và giữ nguyên thứ tự** giữa các lần restart; không phù hợp để trực tiếp lưu trạng thái cho nguồn dữ liệu thay đổi hoặc reader đa luồng. Trong ứng dụng thực tế, dùng reader có sẵn như FlatFileItemReader/JdbcPagingItemReader khi phù hợp và chỉ viết custom stream khi cần.

Checkpoint không tự lưu trạng thái nội bộ của mọi processor hoặc cache tùy chỉnh. Nếu logic dùng state bền vững giữa các chunk, thành phần đó cần có chiến lược lưu/khôi phục riêng hoặc triển khai ItemStream và được Step đăng ký đúng cách.

### Reader cursor và nguồn dữ liệu thay đổi

Với file, không thay đổi file đang được dùng bởi một JobInstance trước restart. Với database paging, cần sort key ổn định, điều kiện truy vấn nhất quán và chiến lược snapshot/watermark để tránh thiếu/trùng item khi nguồn bị thêm/xóa trong quá trình job dừng.

Nếu một reader khai báo **saveState(false)** để phục vụ một cách chạy không restartable, không thể mặc nhiên kỳ vọng nó resume đúng checkpoint sau graceful stop. Dừng có kiểm soát và khôi phục chính xác là hai thuộc tính khác nhau.

## 10. Giữ output nhất quán khi stop/restart

Đối với DB writer dùng transaction chung với chunk, dữ liệu đã commit trước khi stop thường vẫn còn ở bảng đích; phần chưa commit có thể rollback. Đối với REST API, message broker, email, file hoặc datasource khác, hiệu ứng ngoài không tự động tham gia transaction của Spring Batch.

Ví dụ:

~~~text
Chunk 1:
  DB insert O001..O100 -> commit
  ExecutionContext lưu vị trí 100

Chunk 2:
  Gọi API tạo giao dịch cho O101
  API đã xử lý thành công
  Kết nối timeout trước response
  Chunk rollback ở DB

Stop và restart:
  Có thể xử lý lại O101
  API có nguy cơ nhận lặp request
~~~

Do đó, cần thiết kế:

- **Idempotency key** ổn định, ví dụ (batchId, orderId) cho lời gọi có side effect.
- **Unique constraint** hoặc upsert được kiểm soát ở output database.
- **Staging/READY marker:** chỉ công bố batch sau khi toàn bộ các Step và đối soát output hoàn tất.
- **Transactional outbox** khi cần phối hợp database transaction với việc phát sự kiện ra ngoài.
- **Reconciliation** giữa đầu vào, trạng thái xử lý và phản hồi từ dịch vụ ngoài sau restart.
- **Không tái sử dụng cùng output file đang được consumer đọc:** viết theo batchId/version tạm rồi công bố khi COMPLETED.

Việc JobExecution chuyển sang STOPPED không chứng minh output hoàn chỉnh. Cần giữ trạng thái business batch như **PROCESSING**, **STOPPED**, **READY**, **FAILED** tách khỏi metadata vận hành khi downstream cần ra quyết định.

### Chunk size lớn và thời gian chờ stop

Chunk size lớn giảm số lần commit và cập nhật metadata nhưng làm tăng lượng công việc có thể cần hoàn tất trước điểm dừng. Chunk nhỏ tạo nhiều checkpoint hơn nhưng có chi phí transaction và I/O cao hơn.

| Chunk size | Tác động thường gặp |
|---|---|
| 10 | Nhiều checkpoint, phản ứng stop tương đối nhanh nhưng nhiều commit |
| 100 | Cân bằng throughput và độ hạt restart cho nhiều bài toán |
| 1.000 | Ít commit hơn nhưng có thể chờ chunk hiện tại lâu hơn |

Đây là ví dụ trực quan, không phải cấu hình tối ưu cố định. Chọn chunk size dựa trên thời gian một chunk, tài nguyên DB, độ lớn item, retry/skip, yêu cầu stop và khả năng rollback.

## 11. Tasklet dài cần hợp tác với tín hiệu dừng

Không phải mọi Step đều dùng chunk. Một **Tasklet** có thể lặp trên hàng nghìn object trong cùng một lần gọi execute. Nếu không kiểm tra trạng thái, JobOperator.stop không thể can thiệp ngay giữa vòng lặp dài đó.

Một cách thiết kế tốt hơn là chia công việc thành những đơn vị ngắn và lưu tiến độ. Ví dụ minh họa:

~~~java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public class IncrementalTasklet implements Tasklet {

    private final WorkService workService;

    public IncrementalTasklet(WorkService workService) {
        this.workService = workService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        boolean hasMore = workService.processOneUnit();

        // Mỗi lần execute kết thúc, framework có cơ hội quản lý
        // transaction, trạng thái Step và yêu cầu dừng.
        return hasMore ? RepeatStatus.CONTINUABLE : RepeatStatus.FINISHED;
    }
}
~~~

**WorkService** là interface minh họa. Nếu processOneUnit thay đổi trạng thái ngoài DB transaction, cần checkpoint riêng và idempotency. Việc trả CONTINUABLE không tự lưu một con trỏ nghiệp vụ: phải có cơ chế persisted progress nếu cần restart chính xác.

Nếu Tasklet buộc phải làm việc dài trong một lần execute, nên kiểm tra điều kiện dừng ở các đoạn ngắn có thể hủy an toàn, đặt timeout cho I/O, và dùng API tương thích với StepExecution khi cần báo terminate. Không bắt ngoại lệ ngắt rồi tiếp tục làm việc vô hạn.

## 12. Kiểm thử graceful stop tại checkpoint

Một test tích hợp có ích cần chạy **Spring Batch Step/Job thật** với JobRepository và output store trong môi trường test, sau đó chứng minh rằng stop được tiếp nhận, dữ liệu đã commit được giữ, restart tiếp tục đúng và output cuối không trùng.

Các điều kiện nên chuẩn bị:

1. File input bất biến gồm số lượng record lớn hơn hai chunk.
2. Chunk size nhỏ, ví dụ **2**, để dễ xác định checkpoint.
3. Database test riêng, có metadata schema và bảng output.
4. Cơ chế điều khiển stop có thể kích hoạt sau chunk đầu tiên (listener thử nghiệm hoặc JobOperator từ luồng khác).
5. Key nghiệp vụ để truy vấn chính xác tập output sau từng execution.
6. Tín hiệu đồng bộ bằng latch/barrier khi cần chờ một chunk, tránh dùng Thread.sleep với thời gian đoán trước.

### 12.1. Ví dụ stop sau chunk đầu tiên bằng listener test

Đây là cách tạo phép thử xác định của đường đi **terminateOnly tại checkpoint**. Bean listener chỉ dùng trong môi trường test và chỉ gửi tín hiệu dừng một lần:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.scope.context.ChunkContext;

public class StopOnceAfterChunkListener implements ChunkListener {

    private final AtomicBoolean shouldStop = new AtomicBoolean(true);

    @Override
    public void afterChunk(ChunkContext context) {
        if (shouldStop.compareAndSet(true, false)) {
            context.getStepContext()
                    .getStepExecution()
                    .setTerminateOnly();
        }
    }
}
~~~

Test cấu hình Step với **chunk(2, transactionManager)**, gắn listener và file có sáu đơn hợp lệ. Khi chunk đầu commit, callback đánh dấu terminateOnly; framework phát hiện yêu cầu và dừng Step. Kiểm thử có thể dựa trên trạng thái STOPPED và output đã commit, sau đó restart khi listener không còn gửi stop lần nữa.

Một skeleton kiểm thử JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;

class CheckpointStopIT {

    // Inject JobLauncherTestUtils, JobOperator, JdbcTemplate
    // và cấu hình test có StopOnceAfterChunkListener.

    @Test
    void stopAndRestartFromCommittedCheckpoint() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("batchId", "B-TEST-001")
                .addString("inputFile", "/test-data/orders-six.csv")
                .toJobParameters();

        JobExecution first = jobLauncherTestUtils.launchJob(params);
        assertEquals(BatchStatus.STOPPED, first.getStatus());

        // Kiểm tra output batch B-TEST-001 đã commit ở điểm dừng;
        // số lượng mong đợi được xác định theo fixture và chunk.

        Long resumedId = jobOperator.restart(first.getId());
        JobExecution resumed = jobExplorer.getJobExecution(resumedId);
        // Nếu launcher bất đồng bộ: chờ execution kết thúc theo timeout.
        // Assert BatchStatus.COMPLETED và output gồm đúng 6 order_id,
        // không có bản ghi trùng, giá trị đúng.
    }
}
~~~

Đoạn trên là **skeleton**, cần inject các bean và cấu hình fixture thực tế để chạy. Nếu JobOperator.restart chạy theo launcher đồng bộ, trạng thái returned execution có thể đã là trạng thái cuối; nếu launcher bất đồng bộ, phải chờ có giới hạn trước assertion.

Để có một phép thử mạnh hơn, sau execution STOPPED cần kiểm tra:

| Điều kiện | Kết quả kỳ vọng trong ví dụ chunk = 2 |
|---|---|
| Chunk đầu hoàn tất | Hai đơn đầu đã commit |
| Yêu cầu terminateOnly sau commit đầu | Job chuyển STOPPED |
| Checkpoint của reader | Vị trí tương ứng hai record đã xử lý được lưu |
| Trước restart | Output chỉ chứa phần đã commit, không đánh dấu batch READY |
| Restart cùng JobInstance | Tạo JobExecution mới, tiếp tục các record còn lại |
| Sau restart | Output có đúng sáu khóa, không trùng, giá trị chính xác |
| Audit/counter | Có thể phân biệt số item của từng JobExecution với tổng output cả batch |

Không dùng riêng **writeCount của execution restart** để kết luận output cuối: execution mới chỉ ghi phần còn lại; số record đã commit từ execution trước vẫn nằm trong bảng đích.

### 12.2. Test đường đi JobOperator.stop từ luồng điều khiển

Listener test ở trên chứng minh cơ chế dừng tại checkpoint, nhưng **chưa kiểm tra API JobOperator.stop**. Cần một test riêng:

1. Khởi chạy Job bất đồng bộ hoặc trên luồng test khác.
2. Nhận chính xác executionId của job đang chạy qua callback/listener hoặc JobExplorer.
3. Sử dụng latch báo đã có ít nhất một chunk commit, đồng thời chặn các công việc tiếp theo ở một điểm an toàn để tránh race.
4. Gọi **jobOperator.stop(executionId)** từ luồng điều khiển.
5. Nhả latch, chờ execution chuyển sang trạng thái terminal với timeout.
6. Assert trạng thái STOPPED, checkpoint và output; sau đó restart và đối soát output cuối.

Tránh dùng vòng lặp chờ vô hạn hoặc sleep theo số mili giây cố định vì CI có tải khác nhau. Phải dùng database test và JobRepository không bị đóng sớm trước khi job hoàn tất dừng.

## 13. Những tình huống cần kiểm thử thêm

| Kịch bản | Điều cần quan sát |
|---|---|
| Stop trước chunk đầu | Có thể chưa có output; trạng thái và khả năng restart hợp lệ |
| Stop ngay sau commit | Checkpoint khớp phần dữ liệu đã commit |
| Stop khi writer đang thực hiện | Không làm output sai; dừng sau xử lý transaction thích hợp |
| Stop lúc gọi API ngoài bị chậm | Có timeout; không treo STOPPING vô hạn |
| Stop trong Tasklet dài | Tasklet có điểm hợp tác; nếu không, thời gian dừng tăng |
| Stop job đã COMPLETED | Không báo giả là dừng thành công; xử lý trạng thái hiện tại |
| Stop đồng thời với job hoàn tất | Xử lý race, lấy trạng thái cuối từ repository |
| Stop khi có retry/skip | Không dùng readCount làm checkpoint duy nhất; kiểm tra output |
| Restart cùng identifying parameters | Tiếp tục từ checkpoint thay vì tạo batch mới |
| Restart khi file input bị sửa | Phải chặn hoặc quản lý theo version vì checkpoint có thể không còn hợp lệ |
| Stop nhiều partition | Theo dõi trạng thái từng worker/partition và output cuối |
| Tiến trình bị kill đột ngột | Không nhầm crash với graceful stop; có runbook xử lý metadata |
| Ghi DB và gửi message cùng chunk | Kiểm tra outbox/idempotency, không có duplicate ngoài |
| Job có Step đã COMPLETED | Cấu hình restart flow đúng, tránh chạy lại Step hoàn tất ngoài ý muốn |

Một test tốt thường xác minh cả ba lớp: **trạng thái Spring Batch**, **checkpoint/restart behavior** và **tính nhất quán của output**. Chỉ assert STOPPED là chưa đủ nếu writer có side effect bên ngoài.

## 14. Giám sát và vận hành thực tế

Nên ghi lại những thông tin giúp đánh giá chính xác thao tác dừng:

~~~text
jobName             = importOrdersJob
jobInstanceId       = 410
jobExecutionId      = 831
batchId             = B20261116
action              = STOP_REQUESTED
requestTime         = 2026-11-16T09:30:00+07:00
lastStep            = importOrdersStep
lastCommittedChunk  = 15
currentBatchStatus  = STOPPING
eventualBatchStatus = STOPPED
restartExecutionId  = 844
~~~

Đây là ví dụ audit, không phải log thực tế. **lastCommittedChunk** chỉ nên ghi nếu ứng dụng thực sự theo dõi được giá trị đó. Đừng suy đoán checkpoint chỉ từ số record readCount, vì filter, skip, rollback và nhiều loại reader có thể thay đổi cách đếm.

Những metric hữu ích:

- Thời gian từ **STOP_REQUESTED** đến **STOPPED**.
- Số execution ở STOPPING lâu hơn ngưỡng vận hành.
- Vị trí checkpoint hoặc số chunk đã commit gần nhất, nếu có dữ liệu tin cậy.
- Tần suất restart và tỷ lệ thành công sau restart.
- Số record output thiếu/trùng sau restart.
- Số timeout I/O và số request ngoài trùng idempotency key.

Trong dashboard, phân biệt rõ **stop đã yêu cầu**, **đã dừng**, **đang restart** và **đã hoàn tất**. Một scheduler không nên kích hoạt job thay thế chỉ vì có sự kiện “stop requested”; phải đợi trạng thái cuối cùng và kiểm tra lock/ownership của nguồn dữ liệu.

### Runbook dừng và khởi động lại

1. Xác định đúng jobExecutionId, batchId, các Step/partition đang chạy.
2. Gửi yêu cầu stop qua JobOperator hoặc cơ chế điều khiển được hỗ trợ.
3. Theo dõi đến STOPPED; nếu kéo dài, kiểm tra I/O timeout, thread dump, transaction và trạng thái worker.
4. Xác nhận output tạm và checkpoint; không công bố dữ liệu chưa đủ.
5. Đánh giá nguyên nhân dừng đã được giải quyết, nguồn input và repository còn nhất quán.
6. Restart cùng JobInstance nếu phù hợp; ghi nhận new JobExecutionId.
7. Đối soát toàn bộ output theo batchId, sau đó mới công bố READY.

Nếu tiến trình chết trong lúc STOPPING, không tự chỉnh các status trong bảng metadata bằng SQL khi chưa có quy trình khôi phục được kiểm soát. Cần đánh giá lock, transaction đang mở, side effect và state thực tế trước khi quyết định điều chỉnh metadata hoặc chạy lại.

## 15. Những sai lầm thường gặp

**Tưởng JobOperator.stop sẽ ngắt thread lập tức.** Đây là yêu cầu dừng hợp tác; thời gian phản ứng phụ thuộc chunk, tasklet và I/O. Cần điểm kiểm soát và timeout thích hợp.

**Gọi stop rồi coi job đã STOPPED.** STOPPING là trạng thái chuyển tiếp; phải giám sát trạng thái terminal trước khi hành động tiếp.

**Nhầm checkpoint với readCount.** Reader có thể prefetch, retry hoặc rollback; đối soát output đã commit và trạng thái ItemStream mới là cơ sở khôi phục.

**Cho rằng mọi reader tự restart được.** Reader stateful phải lưu trạng thái cần thiết; custom delegate cần tham gia ItemStream và ExecutionContext.

**Dùng job parameter mới để restart.** Việc này tạo JobInstance mới và có thể chạy lại từ đầu; cần dùng cơ chế restart đúng theo execution đã dừng.

**Đổi file nguồn giữa stop và restart.** Vị trí checkpoint có thể trỏ sai record. Cần giữ file bất biến hoặc xử lý một batch/version mới.

**Chỉ lưu trạng thái ở bộ nhớ.** Sau crash hay restart ở tiến trình khác, state sẽ mất. Dùng JobRepository và các store bền vững.

**Chỉ kiểm tra BatchStatus, bỏ qua output.** Một phần writer có thể đã gửi API hoặc ghi file dù transaction DB rollback. Cần đối soát và idempotency.

**Coi STOPPED là đồng nghĩa với FAILED hoặc COMPLETED.** STOPPED là kết thúc có kiểm soát nhưng công việc chưa xong, và có thể restart theo chính sách.

**Giả định mọi partition dừng cùng một checkpoint toàn cục.** Mỗi worker có transaction/checkpoint riêng; cần cơ chế điều phối và tập output cuối để đối soát.

**Tự ép trạng thái repository thành STOPPED khi job còn chạy.** Can thiệp trực tiếp metadata có thể tạo trạng thái giả, dẫn đến hai execution cùng ghi dữ liệu. Luôn ưu tiên API điều khiển và quy trình recovery được định nghĩa.

## 16. Nguyên tắc thiết kế

Graceful stop tại checkpoint trong Spring Batch là sự phối hợp giữa **cơ chế điều khiển execution**, **ranh giới transaction của chunk**, **ExecutionContext có thể khôi phục** và **output có tính idempotent**. JobOperator giúp phát yêu cầu dừng, nhưng chất lượng thiết kế reader/writer, thời gian thực hiện chunk và cách hệ thống công bố kết quả mới quyết định một lần stop/restart có an toàn hay không.

Khi xây dựng job chạy lâu, hãy ưu tiên chunk đủ ngắn để có điểm dừng phù hợp, stateful component được đăng ký đúng với Step, input bất biến theo JobInstance, cơ chế giám sát STOPPING → STOPPED và đối soát output sau restart. Nhờ đó, job có thể tạm dừng vì nhu cầu vận hành mà không phải đánh đổi tính đầy đủ, chính xác hoặc khả năng truy vết của dữ liệu.
