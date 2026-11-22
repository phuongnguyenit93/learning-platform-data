# JobStep execution context

Spring Batch cung cấp ExecutionContext để lưu trạng thái runtime của Job và Step. Context là một cấu trúc key/value được JobRepository persist cùng metadata execution, giúp các thành phần trong một quy trình chia sẻ thông tin và giúp reader hoặc writer khôi phục checkpoint khi Job được restart.

Có hai phạm vi context cần phân biệt: Job ExecutionContext và Step ExecutionContext. Job context dùng để chia sẻ một lượng metadata nhỏ giữa các Step trong cùng JobExecution. Step context giữ trạng thái riêng của một StepExecution, thường là vị trí đọc, trạng thái writer hoặc dữ liệu cần thiết để tiếp tục Step sau lỗi.

Hiểu đúng hai phạm vi này giúp chọn nơi lưu dữ liệu phù hợp, truyền thông tin giữa các Step, cấu hình scope expression và thiết kế restart đáng tin cậy.

## 1. ExecutionContext là gì?

ExecutionContext là vùng lưu trữ key/value gắn với một execution. Mỗi key là một chuỗi và value là dữ liệu mà serializer của Spring Batch có thể lưu và khôi phục.

Ví dụ:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("input.fileVersion", "orders-v4");
context.putLong("reader.lastCustomerId", 8500L);
context.putInt("reader.page", 12);
context.putBoolean("validation.completed", true);
~~~

Các giá trị này không chỉ tồn tại trong object Java. Khi Spring Batch cập nhật metadata qua JobRepository, context được serialize và lưu vào repository. Khi execution được nạp lại hoặc restart, framework khôi phục các giá trị đã lưu.

ExecutionContext phù hợp với metadata và checkpoint nhỏ. Không nên dùng nó làm kho chứa toàn bộ dữ liệu nghiệp vụ, danh sách item lớn hoặc nội dung file. Với dữ liệu lớn, hãy lưu trong database, file hoặc object storage rồi đưa ID hay đường dẫn vào context.

## 2. Hai phạm vi: Job context và Step context

Mỗi JobExecution có một Job ExecutionContext. Mỗi StepExecution có một Step ExecutionContext riêng.

| Đặc điểm | Job ExecutionContext | Step ExecutionContext |
|---|---|---|
| Phạm vi | Một JobExecution | Một StepExecution |
| Mục đích chính | Chia sẻ metadata giữa các Step | Lưu state riêng của Step |
| Ví dụ | Đường dẫn file đã chuẩn bị, mã batch, business date đã xác định | Vị trí reader, page number, writer checkpoint |
| Thời điểm persist thường gặp | Khi Step hoàn thành và JobExecution được cập nhật | Theo checkpoint/commit của Step và khi Step kết thúc |
| Khi restart | Context từ execution trước được dùng để khởi tạo execution mới theo cơ chế restart | State của Step trước được dùng để khôi phục Step cần chạy lại |

Job context được chia sẻ giữa các Step trong cùng lần thực thi Job. Step context được cô lập theo StepExecution để một Step không vô tình ghi đè checkpoint nội bộ của Step khác.

Ví dụ một Job nhập đơn hàng:

~~~text
JobExecution
  Job ExecutionContext
    businessDate = 2026-11-15
    validatedFile = /data/batch/validated.csv

  Step validateInput
    Step ExecutionContext
      sourceLine = 1200
      validationCount = 1200

  Step importOrders
    Step ExecutionContext
      reader.lastId = 9500
      writer.lastCommittedId = 9500

  Step createReport
    Step ExecutionContext
      reportPage = 4
~~~

Step importOrders có thể đọc validatedFile từ Job context, đồng thời giữ reader.lastId trong Step context của chính nó.

## 3. Truy cập Job ExecutionContext và Step ExecutionContext

Từ StepExecution, có thể truy cập cả hai phạm vi:

~~~java
JobExecution jobExecution =
        stepExecution.getJobExecution();

ExecutionContext jobContext =
        jobExecution.getExecutionContext();

ExecutionContext stepContext =
        stepExecution.getExecutionContext();
~~~

Ghi giá trị vào Job context:

~~~java
jobContext.putString(
        "validatedFile",
        "/data/batch/validated-orders.csv");
~~~

Ghi giá trị vào Step context:

~~~java
stepContext.putLong("reader.lastId", 9500L);
~~~

Trong Tasklet, có thể lấy StepExecution qua contribution:

~~~java
@Bean
Tasklet prepareInputTasklet() {
    return (contribution, chunkContext) -> {
        StepExecution stepExecution = contribution.getStepExecution();
        JobExecution jobExecution = stepExecution.getJobExecution();

        jobExecution.getExecutionContext()
                .putString(
                        "validatedFile",
                        "/data/batch/validated-orders.csv");

        stepExecution.getExecutionContext()
                .putLong("validation.recordCount", 1200L);

        return RepeatStatus.FINISHED;
    };
}
~~~

Tasklet ghi đường dẫn file vào Job context để Step sau dùng. Số record kiểm tra được lưu trong Step context vì đó là state thuộc riêng Step chuẩn bị dữ liệu.

Không nên lấy Job context để lưu mọi state chỉ vì nó dễ truy cập. Hãy đặt mỗi key ở phạm vi nhỏ nhất đáp ứng nhu cầu sử dụng.

## 4. Chia sẻ dữ liệu nhỏ giữa các Step

Một trường hợp phổ biến là Step đầu tạo ra thông tin mà Step sau cần dùng.

Ví dụ:

~~~text
validateInputStep
      |
      | tạo file đã kiểm tra
      | lưu validatedFile vào Job context
      v
importOrdersStep
      |
      | đọc validatedFile
      v
createReportStep
~~~

Step đầu có thể ghi đường dẫn vào Job ExecutionContext:

~~~java
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String validatedFile =
                "/data/batch/validated-orders.csv";

        JobExecution jobExecution =
                contribution.getStepExecution().getJobExecution();

        jobExecution.getExecutionContext()
                .putString("validatedFile", validatedFile);

        return RepeatStatus.FINISHED;
    }
}
~~~

Step sau dùng Job context để nhận đường dẫn. Với bean có Step scope, có thể inject giá trị bằng expression:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> validatedOrderReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("validatedOrderReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper(orderLineMapper())
            .saveState(true)
            .build();
}
~~~

@StepScope trì hoãn việc tạo reader cho đến khi Step bắt đầu, lúc đó Job ExecutionContext đã có thể được phân giải. Reader chỉ nhận đường dẫn và đọc dữ liệu; nội dung file không được đưa vào context.

Đảm bảo Step tạo file hoàn tất thành công trước khi Step đọc bắt đầu. Nếu file có thể bị xóa hoặc thay đổi giữa các lần chạy, hãy lưu thêm mã phiên bản, checksum hoặc batch ID để xác nhận Step sau đang dùng đúng đầu ra.

## 5. Dùng Step ExecutionContext cho checkpoint

Reader và writer có state thường dùng Step context để lưu thông tin phục hồi. Ví dụ reader cần biết bản ghi tiếp theo sau một lần restart.

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private static final String LAST_ID =
            "customerReader.lastId";

    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
                ? context.getLong(LAST_ID)
                : 0L;
    }

    @Override
    public Customer read() {
        Customer next = loadCustomerAfter(lastId);

        if (next != null) {
            lastId = next.getId();
        }

        return next;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastId);
    }

    @Override
    public void close() {
        // Đóng resource nếu reader có mở.
    }
}
~~~

Đây là ví dụ minh họa; loadCustomerAfter cần được triển khai theo nguồn dữ liệu thực tế. Reader lưu ID cuối cùng đã đọc trong Step context. Khi Step restart, open() nhận context đã lưu và tiếp tục sau ID tương ứng.

Với chunk-oriented Step, Spring Batch gọi lifecycle của ItemStream để cập nhật state tại các checkpoint. Step context vì thế là nơi phù hợp cho vị trí đọc hoặc trạng thái writer cần phục hồi theo ranh giới commit.

Không dùng Job context làm nơi lưu vị trí đọc nội bộ của từng reader. Nếu Job có nhiều Step hoặc nhiều partition, state reader có thể bị lẫn giữa các execution nếu dùng chung key ở phạm vi quá rộng.

## 6. Đưa giá trị từ Step context lên Job context

Có trường hợp component nên ghi state vào Step context, nhưng Step sau cần dùng một số giá trị đó. Spring Batch cung cấp ExecutionContextPromotionListener để chọn các key cần promotion từ Step context lên Job context khi Step hoàn thành theo trạng thái được cấu hình.

Ví dụ listener:

~~~java
@Bean
ExecutionContextPromotionListener promoteValidatedFile() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] { "validatedFile" });
    return listener;
}
~~~

Đăng ký listener trên Step tạo ra giá trị:

~~~java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateInputTasklet,
        ExecutionContextPromotionListener promoteValidatedFile) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateInputTasklet, transactionManager)
            .listener(promoteValidatedFile)
            .build();
}
~~~

Tasklet ghi key vào Step context:

~~~java
contribution.getStepExecution()
        .getExecutionContext()
        .putString(
                "validatedFile",
                "/data/batch/validated-orders.csv");
~~~

Khi Step kết thúc với trạng thái được promotion listener chấp nhận, key validatedFile được chuyển lên Job context. Step sau có thể truy cập bằng jobExecutionContext.

Mặc định listener thường promotion theo trạng thái COMPLETED; có thể cấu hình danh sách trạng thái bằng setStatuses nếu nghiệp vụ cần điều kiện khác. Chỉ promotion những key cần chia sẻ, không sao chép toàn bộ Step context lên Job context.

Promotion giúp tách state nội bộ khỏi thông tin công bố cho các Step khác. Reader có thể giữ checkpoint trong Step context trong khi chỉ đường dẫn file đầu ra được đưa lên Job context.

## 7. JobParameters khác ExecutionContext như thế nào?

JobParameters và ExecutionContext đều có thể chứa giá trị mà Step sử dụng, nhưng mục đích khác nhau.

| Thuộc tính | JobParameters | ExecutionContext |
|---|---|---|
| Vai trò | Đầu vào của JobInstance/JobExecution | Trạng thái phát sinh trong quá trình chạy |
| Ai thường cung cấp | JobLauncher, scheduler hoặc caller | Reader, writer, Step hoặc Job logic |
| Dùng xác định JobInstance | Identifying parameters có tham gia | Không |
| Thay đổi trong lúc chạy | Không dùng để cập nhật checkpoint | Có thể cập nhật qua API context |
| Ví dụ | businessDate, sourceFileId, tenant | validatedFile, lastReadId, pageNumber |

Ví dụ:

~~~text
JobParameters
  businessDate = 2026-11-15
  sourceFileId = file-8421

Job ExecutionContext
  validatedFile = /data/batch/validated-orders.csv

Step ExecutionContext
  customerReader.lastId = 9500
~~~

JobParameters mô tả công việc được yêu cầu. Job context lưu metadata runtime cần chia sẻ. Step context lưu checkpoint nội bộ của Step.

Không đưa password hoặc token vào JobParameters hay ExecutionContext. Non-identifying parameter vẫn có thể được lưu trong metadata; cờ identifying không phải cơ chế bảo mật.

## 8. Truy cập context bằng scope expression

Spring Batch cung cấp các scope expression cho bean có Step scope hoặc Job scope.

Một số expression thường gặp:

| Expression | Giá trị được truy cập |
|---|---|
| jobParameters['inputFile'] | JobParameter có key inputFile |
| jobExecutionContext['validatedFile'] | Key trong Job ExecutionContext |
| stepExecutionContext['reader.lastId'] | Key trong Step ExecutionContext |

Ví dụ reader nhận đường dẫn từ Job context:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String inputFile) {
    // Tạo reader từ file đã được Step trước chuẩn bị.
}
~~~

Ví dụ Tasklet nhận giá trị checkpoint hoặc cấu hình riêng của Step:

~~~java
@Bean
@StepScope
Tasklet processPartitionTasklet(
        @Value("#{stepExecutionContext['partitionStart']}")
        Long startId,
        @Value("#{stepExecutionContext['partitionEnd']}")
        Long endId) {
    // Xử lý phạm vi ID của partition hiện tại.
}
~~~

Các giá trị runtime chỉ có sẵn khi scope tương ứng được mở. Nếu inject trực tiếp vào singleton bean khi ứng dụng khởi động, expression có thể chưa được phân giải vì chưa có StepExecution hoặc JobExecution hiện hành.

## 9. Thời điểm persist và tính nhất quán

Gọi put() cập nhật ExecutionContext trong bộ nhớ. Nó không có nghĩa giá trị được ghi xuống database ngay tại dòng code đó.

Với Step context, Spring Batch lưu state theo lifecycle của Step và các checkpoint chunk. Với Job context, thay đổi trong một Step thường được persist khi Step hoàn thành và JobExecution được cập nhật. Vì vậy, không nên dùng Job context làm cơ chế checkpoint theo từng chunk.

Luồng khái quát:

~~~text
Step đang chạy
   |
   +--> cập nhật Step ExecutionContext
   |       |
   |       +--> checkpoint theo chunk
   |               |
   |               v
   |           JobRepository
   |
   +--> cập nhật Job ExecutionContext
           |
           +--> Step hoàn thành
                   |
                   v
               JobRepository
~~~

Nếu Job context được cập nhật giữa Step, Step sau trong cùng JobExecution có thể sử dụng giá trị đó sau khi Step hiện tại hoàn tất và flow chuyển tiếp. Nếu process bị dừng trước khi context được persist, thay đổi chưa lưu có thể không còn khi restart.

Nếu cần state được lưu đều đặn theo từng chunk để restart, hãy dùng Step ExecutionContext và ItemStream lifecycle. Không dựa vào một key trong Job context như thể nó được checkpoint cùng mỗi chunk.

## 10. Restart và khôi phục context

Khi một JobExecution thất bại và JobInstance được restart, Spring Batch tạo JobExecution mới cho cùng JobInstance nếu trạng thái và cấu hình cho phép. Context đã lưu từ execution trước được dùng để khởi tạo execution mới theo cơ chế restart.

Với Step đã hoàn thành, flow thường bỏ qua Step đó. Với Step cần chạy lại, framework khôi phục Step context từ trạng thái đã lưu nếu Step và các component hỗ trợ restart.

Ví dụ:

~~~text
JobInstance: importOrders, businessDate=2026-11-15

JobExecution 101:
  validateInputStep -> COMPLETED
  importOrdersStep  -> FAILED
      reader.lastId = 9500
  createReportStep  -> NOT STARTED

JobExecution 108 (restart):
  validateInputStep -> skipped (đã hoàn thành)
  importOrdersStep  -> khôi phục checkpoint
      reader tiếp tục sau ID 9500
  createReportStep  -> chạy sau khi importOrdersStep hoàn tất
~~~

Để restart hoạt động đúng:

- Giữ nguyên identifying JobParameters để tiếp tục cùng JobInstance.
- Giữ tên Step ổn định khi metadata cũ còn cần dùng.
- Giữ key context và ý nghĩa của chúng tương thích giữa các phiên bản.
- Bảo đảm file hoặc dữ liệu nguồn/đích được tham chiếu vẫn tồn tại.
- Reader và writer phải hỗ trợ ItemStream nếu cần khôi phục state.
- Không thay đổi dữ liệu nguồn theo cách khiến checkpoint cũ trỏ đến bản ghi khác.

Nếu Step trước đã hoàn thành và tạo file cho Step sau, file đó cần còn tồn tại khi restart. Checkpoint metadata không tự khôi phục nội dung file đã bị xóa.

## 11. Job context không thay thế kho dữ liệu nghiệp vụ

ExecutionContext được thiết kế cho metadata nhỏ, không phải để truyền toàn bộ dataset giữa các Step.

Không nên lưu:

- Danh sách hàng nghìn hoặc hàng triệu entity.
- Toàn bộ JSON/XML payload.
- Nội dung file lớn hoặc binary data.
- JPA entity graph có quan hệ lazy.
- JDBC Connection, stream, thread hoặc resource đang mở.

Thay vào đó, lưu tham chiếu:

~~~java
jobExecution.getExecutionContext()
        .putLong("staging.batchId", 8421L);

jobExecution.getExecutionContext()
        .putString(
                "staging.file",
                "/data/batch/staging/orders-8421.csv");
~~~

Step sau dùng batch ID để truy vấn staging table hoặc dùng đường dẫn để mở file. Cách này giúp context nhỏ, dễ serialize và dễ khôi phục.

Nếu Step sau cần nhiều dữ liệu do Step trước tạo, hãy lưu dữ liệu vào staging table hoặc file bền vững rồi chỉ truyền ID, tên file, version hoặc checksum qua context.

## 12. Serialization và kiểu dữ liệu trong context

JobRepository phải serialize context để lưu metadata. Kiểu dữ liệu đưa vào context cần được serializer đang cấu hình hỗ trợ.

Các kiểu đơn giản như String, Long, Integer và Boolean thường dễ quản lý. Object tùy chỉnh có thể tạo phụ thuộc vào class và cấu trúc object khi ứng dụng nâng cấp.

Ví dụ nên ưu tiên:

~~~java
context.putLong("lastProcessedId", 9500L);
context.putString("source.version", "v4");
context.putBoolean("validation.completed", true);
~~~

Hạn chế lưu object nghiệp vụ lớn hoặc resource không thể serialize:

~~~java
// Không nên lưu resource đang mở hoặc object graph lớn.
context.put("connection", connection);
context.put("bufferedReader", bufferedReader);
context.put("customerAggregate", customerAggregate);
~~~

Nếu serializer không thể lưu giá trị, lỗi có thể xuất hiện lúc framework persist context tại checkpoint hoặc khi Step kết thúc, không nhất thiết ngay tại lệnh put(). Khi thiết kế context, hãy kiểm tra khả năng round-trip bằng serializer thực tế và giữ key/value ổn định qua các phiên bản.

## 13. Đặt tên key và quản lý version

Một Job có thể có nhiều reader, writer và Step cùng ghi context. Key nên có namespace để tránh xung đột:

~~~text
validateInput.outputFile
customerReader.lastId
customerReader.page
orderWriter.lastCommittedId
reportWriter.currentPage
~~~

Tránh dùng key quá chung như status, count hoặc position nếu nhiều component cùng sử dụng.

Khi thay đổi cấu trúc state, cân nhắc version hóa:

~~~java
private static final String STATE_VERSION =
        "customerReader.stateVersion";

private static final String LAST_ID =
        "customerReader.lastId";

void saveState(ExecutionContext context, long lastId) {
    context.putInt(STATE_VERSION, 2);
    context.putLong(LAST_ID, lastId);
}
~~~

Khi mở reader, code có thể kiểm tra version và hỗ trợ các định dạng state còn tồn tại. Không xóa key cũ hoặc đổi tên key tùy tiện khi vẫn còn execution cần restart từ metadata được tạo bởi phiên bản ứng dụng trước.

## 14. Context trong partitioning và chạy song song

Với partitioned Step, mỗi partition có StepExecution và Step ExecutionContext riêng. Đây là nơi phù hợp để lưu phạm vi dữ liệu của partition, chẳng hạn ID bắt đầu và kết thúc.

~~~text
Master Step
   |
   +--> Partition 1
   |      Step context: startId=1, endId=1000
   |
   +--> Partition 2
   |      Step context: startId=1001, endId=2000
   |
   +--> Partition 3
          Step context: startId=2001, endId=3000
~~~

Worker Step có thể đọc các giá trị này bằng stepExecutionContext expression. Mỗi partition giữ state riêng để restart độc lập theo mô hình partitioning.

Job ExecutionContext là vùng chia sẻ trong phạm vi JobExecution. Nếu nhiều nhánh hoặc worker cùng cập nhật một key trong Job context, có thể xảy ra ghi đè hoặc mất cập nhật tùy cách đồng bộ và persist. Không dùng Job context như một vùng chia sẻ mutable giữa nhiều worker thread. Hãy dùng Step context riêng, database hoặc cơ chế đồng bộ phù hợp cho dữ liệu cần chia sẻ đồng thời.

## 15. Bảo mật dữ liệu trong ExecutionContext

Context được lưu trong metadata repository. Serialization không đồng nghĩa với mã hóa. Nếu đưa password, API token, private key hoặc credential vào context, giá trị đó có thể được lưu và truy vấn cùng metadata.

Không lưu secret trong Job context hoặc Step context. Hãy dùng secret manager và chỉ lưu một reference không nhạy cảm nếu Step cần biết secret nào phải truy xuất.

Cũng cần kiểm soát dữ liệu cá nhân trong context. Chỉ lưu thông tin thực sự cần cho restart và giới hạn quyền đọc JobRepository theo vai trò. Mã hóa database at rest là lớp bảo vệ bổ sung, không thay thế việc tránh lưu dữ liệu nhạy cảm không cần thiết.

## 16. Những lỗi thường gặp

**Dùng nhầm phạm vi context.** Lưu checkpoint reader vào Job context khiến state nội bộ của Step bị chia sẻ quá rộng. Dùng Step context cho state riêng, Job context cho metadata cần chia sẻ giữa Step.

**Cho rằng put() ghi ngay xuống repository.** Giá trị được persist theo lifecycle và transaction của Spring Batch. Không truy vấn database ngay sau put() với giả định nó đã được lưu.

**Dùng Job context cho checkpoint từng chunk.** Job context thường được cập nhật khi Step hoàn thành; state theo chunk nên nằm trong Step context qua ItemStream.

**Lưu dataset lớn.** Context phình to làm tăng chi phí serialize, database, backup và restore. Lưu ID hoặc tham chiếu đến kho dữ liệu.

**Không promotion key cần chia sẻ.** Nếu state chỉ nằm trong Step context, Step sau không tự động nhìn thấy nó qua Job context. Dùng ExecutionContextPromotionListener hoặc ghi trực tiếp vào Job context theo thiết kế.

**Dùng key chung chung.** Các component có thể ghi đè giá trị của nhau. Dùng namespace theo tên Step hoặc component.

**Thay đổi key hoặc kiểu dữ liệu khi restart.** Execution cũ có thể không khôi phục được. Duy trì tương thích hoặc có chiến lược versioning.

**Dùng context như cơ chế đồng bộ thread.** Context không thay thế khóa, queue hoặc database coordination khi nhiều worker cùng cập nhật state.

**Lưu secret hoặc resource.** Credential và object như Connection/stream không phù hợp để persist. Dùng secret manager và mở lại resource qua lifecycle.

## 17. Kiểm thử Job và Step ExecutionContext

Cần kiểm thử cả giá trị được ghi, thời điểm persist và khả năng khôi phục.

Các kịch bản nên có:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Step ghi Job context | Step sau đọc được key sau khi Step trước hoàn thành |
| Step ghi Step context | Checkpoint được lưu trong phạm vi đúng StepExecution |
| Promotion listener | Chỉ key được chọn được đưa lên Job context |
| Restart sau lỗi | Reader/writer khôi phục state đã commit |
| Job có nhiều Step | Key không bị lẫn giữa các Step |
| Partitioning | Mỗi partition có context và phạm vi riêng |
| Dữ liệu không serialize được | Lỗi được phát hiện và chẩn đoán đúng |
| Context lớn | Thiết kế dùng reference thay vì payload |
| Nâng cấp ứng dụng | Key và kiểu dữ liệu cũ vẫn đọc được khi cần restart |

Một integration test có thể chạy Job lần đầu, cố ý làm một Step thất bại sau checkpoint, rồi restart cùng JobInstance và xác nhận Step tiếp tục đúng vị trí. Có thể dùng JobRepository thật trong môi trường test để kiểm tra context được persist và nạp lại.

Không chỉ kiểm tra object context trong bộ nhớ. Cần xác nhận repository đã lưu state ở thời điểm phù hợp và execution mới thực sự khôi phục được các key cần thiết.

## 18. Quy trình chọn nơi lưu context

Khi một Step cần giữ hoặc chia sẻ giá trị, hãy tự hỏi:

1. Giá trị này có phải đầu vào cố định của Job không? Nếu có, cân nhắc JobParameters.
2. Giá trị chỉ phục vụ checkpoint nội bộ của một Step? Dùng Step ExecutionContext.
3. Step sau cần dùng giá trị do Step trước tạo? Dùng Job ExecutionContext hoặc promotion listener.
4. Giá trị có phải dữ liệu nghiệp vụ lớn? Lưu trong database/file/object storage, chỉ đưa ID hoặc reference vào context.
5. Giá trị có cần tồn tại qua restart? Bảo đảm context được persist và kiểu dữ liệu tương thích.
6. Giá trị có nhạy cảm? Không lưu secret hoặc dữ liệu cá nhân không cần thiết.
7. Có nhiều partition hoặc worker cùng cập nhật? Dùng state riêng theo StepExecution hoặc một cơ chế lưu trữ đồng bộ.

Job ExecutionContext và Step ExecutionContext là hai công cụ bổ trợ nhau. Job context giúp các Step phối hợp bằng metadata nhỏ; Step context giữ checkpoint riêng để reader, writer và Step có thể tiếp tục sau lỗi. Khi đặt dữ liệu đúng phạm vi, dùng lifecycle để persist và giữ context gọn, Job có thể chia sẻ thông tin và restart mà không làm metadata trở thành kho dữ liệu nghiệp vụ.

