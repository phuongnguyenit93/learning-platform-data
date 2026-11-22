# Tasklet đọc ExecutionContext

Trong Spring Batch, `ExecutionContext` là vùng lưu trữ key-value gắn với một lần thực thi của job hoặc step. Nó giúp lưu trạng thái runtime, checkpoint và một số dữ liệu nhỏ cần chuyển giữa các giai đoạn xử lý. Một `Tasklet` có thể đọc `ExecutionContext` để tiếp tục công việc dựa trên trạng thái đã lưu hoặc sử dụng thông tin do step trước tạo ra.

Ví dụ, step đầu tiên kiểm tra file đầu vào và lưu đường dẫn file đã xác nhận. Step tiếp theo dùng tasklet để đọc đường dẫn đó từ Job ExecutionContext rồi thực hiện thao tác tiếp theo. Cách này giúp các step trao đổi metadata mà không phải truyền một object lớn qua bộ nhớ hoặc gắn chặt với nhau bằng biến toàn cục.

## 1. ExecutionContext trong Spring Batch

`ExecutionContext` là một cấu trúc key-value được Spring Batch lưu cùng metadata thực thi. Nó thường được dùng cho:

- Lưu checkpoint của reader hoặc writer để hỗ trợ restart.
- Lưu trạng thái nhỏ cần thiết để tiếp tục một step.
- Chia sẻ metadata giữa các step trong cùng một JobExecution.
- Lưu thông tin runtime như đường dẫn file trung gian, số lượng bản ghi hoặc mã batch.

Có hai phạm vi ExecutionContext chính:

| Phạm vi | Gắn với | Vòng đời và mục đích |
|---|---|---|
| Step ExecutionContext | Một `StepExecution` | Lưu trạng thái riêng của step, ví dụ checkpoint reader, vị trí xử lý hoặc metadata nội bộ của step. |
| Job ExecutionContext | Một `JobExecution` | Lưu trạng thái ở phạm vi job, thường dùng để chia sẻ thông tin nhỏ giữa các step. |

Mỗi `StepExecution` có ExecutionContext riêng. Mỗi `JobExecution` cũng có ExecutionContext riêng. Khi một job chạy qua nhiều step, các step có thể truy cập cùng Job ExecutionContext thông qua JobExecution mà chúng thuộc về, trong khi mỗi step vẫn có Step ExecutionContext độc lập.

```text
JobExecution
  |
  +-- Job ExecutionContext
  |      +-- validatedFile
  |      +-- batchReference
  |
  +-- StepExecution: validateInputStep
  |      +-- Step ExecutionContext
  |             +-- scannedLine
  |             +-- validationCount
  |
  +-- StepExecution: importDataStep
         +-- Step ExecutionContext
                +-- readerCheckpoint
                +-- writtenCount
```

Job ExecutionContext có phạm vi rộng hơn và có thể được dùng bởi các step trong cùng một JobExecution. Step ExecutionContext thuộc riêng một step execution và thường chứa trạng thái phục vụ chính step đó.

## 2. Tasklet nhận ExecutionContext qua những đối tượng nào?

Trong Spring Batch, `Tasklet` có phương thức `execute` với hai tham số:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

`StepContribution` và `ChunkContext` cung cấp thông tin về lần thực thi hiện tại. Từ đó, tasklet có thể lấy `StepExecution`, `JobExecution` và hai ExecutionContext tương ứng.

Đường truy cập trực tiếp thường dùng là:

```java
StepExecution stepExecution = contribution.getStepExecution();

ExecutionContext stepContext = stepExecution.getExecutionContext();
ExecutionContext jobContext =
        stepExecution.getJobExecution().getExecutionContext();
```

Trong đó:

- `stepExecution.getExecutionContext()` trả về Step ExecutionContext.
- `stepExecution.getJobExecution().getExecutionContext()` trả về Job ExecutionContext.
- `chunkContext.getStepContext().getStepExecution()` cũng có thể được dùng để lấy StepExecution hiện tại.

Ví dụ đọc cả hai phạm vi:

```java
@Bean
Step inspectContextStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet inspectTasklet = (contribution, chunkContext) -> {
        StepExecution stepExecution = contribution.getStepExecution();

        ExecutionContext stepContext = stepExecution.getExecutionContext();
        ExecutionContext jobContext =
                stepExecution.getJobExecution().getExecutionContext();

        // Đọc các giá trị đã được đặt trong context.
        if (stepContext.containsKey("validatedRecordCount")) {
            long count = stepContext.getLong("validatedRecordCount");
            System.out.println("Step count: " + count);
        }

        if (jobContext.containsKey("batchReference")) {
            String reference = jobContext.getString("batchReference");
            System.out.println("Batch reference: " + reference);
        }

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("inspectContextStep", jobRepository)
            .tasklet(inspectTasklet, transactionManager)
            .build();
}
```

Ví dụ này giả định các key đã được tạo trước đó. Trong ứng dụng thực tế, cần kiểm tra key tồn tại và giá trị có đúng kiểu dữ liệu mong đợi trước khi sử dụng.

## 3. Đọc giá trị an toàn từ ExecutionContext

ExecutionContext là một vùng key-value. Tasklet cần biết tên key và kiểu dữ liệu đã được lưu. Có thể dùng `containsKey` trước khi đọc để phân biệt trường hợp key chưa được tạo với trường hợp giá trị hợp lệ.

```java
ExecutionContext context =
        contribution.getStepExecution().getExecutionContext();

if (!context.containsKey("inputFile")) {
    throw new IllegalStateException(
            "ExecutionContext does not contain inputFile");
}

String inputFile = context.getString("inputFile");
```

Một số phương thức truy cập thường gặp:

| Phương thức | Mục đích |
|---|---|
| `putString(key, value)` | Lưu chuỗi. |
| `getString(key)` | Đọc chuỗi. |
| `putLong(key, value)` | Lưu số nguyên dài. |
| `getLong(key)` | Đọc số nguyên dài. |
| `putInt(key, value)` | Lưu số nguyên. |
| `getInt(key)` | Đọc số nguyên. |
| `put(key, value)` | Lưu một giá trị được serializer hỗ trợ. |
| `get(key)` | Đọc giá trị dạng object. |
| `containsKey(key)` | Kiểm tra key có tồn tại. |
| `remove(key)` | Xóa key khỏi context. |

Nên đặt tên key có ý nghĩa và tránh dùng chung tên cho các mục đích khác nhau. Ví dụ `validatedInputFile`, `importedRecordCount` hoặc `reportOutputPath` dễ hiểu hơn các tên chung như `value1` hay `data`.

Nếu một key có thể chưa tồn tại, hãy xử lý rõ ràng. Không nên mặc định rằng `getString`, `getLong` hoặc ép kiểu object luôn trả về giá trị hợp lệ. Kiểm tra key, kiểu và điều kiện nghiệp vụ trước khi thực hiện tác vụ tiếp theo.

### Kiểm tra kiểu dữ liệu

Khi dùng `put` và `get`, giá trị được lưu dưới dạng object. Cần bảo đảm kiểu ghi và kiểu đọc tương thích:

```java
context.put("recordCount", 125L);

Object value = context.get("recordCount");
if (!(value instanceof Long recordCount)) {
    throw new IllegalStateException("recordCount has an unexpected type");
}
```

Với các kiểu phổ biến như String, Long hoặc Integer, các phương thức chuyên biệt `putString`, `getString`, `putLong`, `getLong` giúp code dễ đọc hơn. Với object tùy chỉnh, cần bảo đảm serializer của ExecutionContext có thể lưu và khôi phục kiểu dữ liệu đó.

## 4. Tasklet đọc Step ExecutionContext

Step ExecutionContext phù hợp với dữ liệu chỉ có ý nghĩa trong phạm vi step hiện tại. Ví dụ, một tasklet chia công việc thành nhiều lần gọi có thể lưu số lần xử lý hoặc checkpoint riêng của step.

Ví dụ tasklet đọc vị trí đã lưu:

```java
@Bean
Step resumeLocalWorkStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        ExecutionContext context = contribution.getStepExecution()
                .getExecutionContext();

        long lastProcessedId = context.containsKey("lastProcessedId")
                ? context.getLong("lastProcessedId")
                : 0L;

        // Tiếp tục công việc từ ID tiếp theo.
        long nextId = lastProcessedId + 1;
        System.out.println("Continue from ID: " + nextId);

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("resumeLocalWorkStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

Trong ví dụ, `lastProcessedId` thuộc riêng step này. Nếu job có một step khác, step đó không tự động nhìn thấy Step ExecutionContext của step hiện tại.

Nếu tasklet cần cập nhật trạng thái để lần gọi tiếp theo trong cùng step tiếp tục từ vị trí mới, có thể ghi giá trị vào context:

```java
context.putLong("lastProcessedId", nextId);
```

Việc lưu trạng thái cần gắn với transaction và vòng đời thực thi. Với tasklet step, mỗi lần gọi `execute` được điều phối trong transaction theo cấu hình step. Nếu tasklet trả `RepeatStatus.CONTINUABLE`, framework có thể gọi lại tasklet; cần thiết kế cập nhật context và thao tác nghiệp vụ nhất quán để lần gọi tiếp theo không lặp sai công việc.

## 5. Tasklet đọc Job ExecutionContext

Job ExecutionContext phù hợp với metadata cần được chia sẻ giữa các step thuộc cùng JobExecution. Ví dụ, step đầu tiên kiểm tra file và lưu đường dẫn đã xác nhận; step sau đọc đường dẫn đó để import.

Tasklet có thể lấy Job ExecutionContext qua StepExecution:

```java
ExecutionContext jobContext = contribution.getStepExecution()
        .getJobExecution()
        .getExecutionContext();

if (!jobContext.containsKey("validatedInputFile")) {
    throw new IllegalStateException("validatedInputFile is missing");
}

String inputFile = jobContext.getString("validatedInputFile");
```

Giá trị trong Job ExecutionContext tồn tại ở phạm vi JobExecution. Nếu job được restart và tạo JobExecution mới cho cùng JobInstance, Job ExecutionContext của execution trước không phải là một vùng trạng thái dùng chung vĩnh viễn cho mọi execution. Dữ liệu cần khôi phục phải được lưu và phục hồi theo cơ chế restart của Spring Batch, hoặc được tái tạo bởi các step trước theo flow.

Không nên dùng Job ExecutionContext như một kho lưu trữ toàn cục giữa các lần chạy job khác nhau. Nếu dữ liệu phải tồn tại độc lập với JobExecution, hãy lưu trong database nghiệp vụ hoặc hệ thống lưu trữ phù hợp rồi truyền một khóa tham chiếu qua parameters/context.

## 6. Chuyển dữ liệu từ Step ExecutionContext sang Job ExecutionContext

Một step thường ghi dữ liệu vào Step ExecutionContext. Để step tiếp theo đọc được dữ liệu đó ở phạm vi job, có thể dùng `ExecutionContextPromotionListener`.

Ví dụ, step kiểm tra file lưu đường dẫn đã xác nhận vào Step ExecutionContext:

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ExecutionContextPromotionListener promotionListener) {

    Tasklet validateTasklet = (contribution, chunkContext) -> {
        String validatedFile = "data/ready/orders.csv";

        contribution.getStepExecution()
                .getExecutionContext()
                .putString("validatedInputFile", validatedFile);

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(validateTasklet, transactionManager)
            .listener(promotionListener)
            .build();
}

@Bean
ExecutionContextPromotionListener promotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[]{"validatedInputFile"});
    return listener;
}
```

Khi step hoàn tất với trạng thái được listener cho phép (mặc định là `COMPLETED`), listener đưa các key đã cấu hình từ Step ExecutionContext sang Job ExecutionContext. Step sau có thể đọc `validatedInputFile` từ Job ExecutionContext.

```text
validateInputStep
       |
       | Step ExecutionContext:
       | validatedInputFile = data/ready/orders.csv
       |
       v
ExecutionContextPromotionListener
       |
       v
Job ExecutionContext:
  validatedInputFile = data/ready/orders.csv
       |
       v
importOrdersStep đọc giá trị
```

Chỉ nên promote những key cần thiết cho các step khác. Tránh đưa toàn bộ trạng thái nội bộ của step vào Job ExecutionContext vì sẽ làm phạm vi dữ liệu chia sẻ rộng hơn và dễ gây xung đột tên key.

### Cấu hình trạng thái promotion

Listener có thể được cấu hình để promote key khi step kết thúc với các `ExitStatus` nhất định. Mặc định listener thường áp dụng cho `COMPLETED`. Nếu thay đổi danh sách trạng thái, hãy bảo đảm chỉ promote khi dữ liệu đã được tạo đầy đủ và hợp lệ.

Nếu key không tồn tại trong Step ExecutionContext, hành vi có thể phụ thuộc cấu hình strict của listener. Khi dữ liệu là bắt buộc, nên bật kiểm tra nghiêm ngặt hoặc tự kiểm tra key trước khi step kết thúc để phát hiện lỗi sớm.

## 7. Tasklet đọc context qua late binding

Ngoài cách lấy `ExecutionContext` trực tiếp từ `StepContribution`, Spring Batch còn hỗ trợ late binding trong bean có `@StepScope`. Các giá trị context có thể được inject qua SpEL.

Một số biểu thức thường gặp:

| Biểu thức | Nguồn dữ liệu |
|---|---|
| `#{jobParameters['inputFile']}` | JobParameters của lần chạy. |
| `#{stepExecutionContext['checkpoint']}` | Step ExecutionContext của step hiện tại. |
| `#{jobExecutionContext['validatedInputFile']}` | Job ExecutionContext của JobExecution hiện tại. |

Ví dụ tasklet đọc giá trị đã được promote:

```java
@Bean
@StepScope
Tasklet importValidatedFileTasklet(
        @Value("#{jobExecutionContext['validatedInputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        if (inputFile == null || inputFile.isBlank()) {
            throw new IllegalStateException("No validated input file found");
        }

        // Thực hiện thao tác sử dụng inputFile.
        System.out.println("Importing: " + inputFile);
        return RepeatStatus.FINISHED;
    };
}
```

`@StepScope` rất quan trọng trong trường hợp này vì giá trị context chỉ có khi step execution bắt đầu. Nếu inject giá trị runtime vào singleton bean được tạo lúc application context khởi động, biểu thức có thể không được đánh giá trong đúng phạm vi thực thi.

Late binding phù hợp khi tasklet hoặc reader cần một giá trị đơn giản. Nếu cần kiểm tra nhiều key, xử lý kiểu phức tạp hoặc có logic fallback, đọc ExecutionContext trực tiếp qua StepExecution có thể rõ ràng hơn.

## 8. Ví dụ hoàn chỉnh: step đầu ghi context, tasklet sau đọc context

Giả sử job có hai step:

1. `prepareFileStep`: kiểm tra file đầu vào, lưu đường dẫn đã xác nhận trong Step ExecutionContext.
2. `importFileStep`: nhận đường dẫn đã được promote sang Job ExecutionContext và thực hiện thao tác import.

```java
@Configuration
public class FileImportJobConfiguration {

    @Bean
    ExecutionContextPromotionListener filePromotionListener() {
        ExecutionContextPromotionListener listener =
                new ExecutionContextPromotionListener();
        listener.setKeys(new String[]{"validatedInputFile"});
        return listener;
    }

    @Bean
    Step prepareFileStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ExecutionContextPromotionListener filePromotionListener) {

        Tasklet prepareTasklet = (contribution, chunkContext) -> {
            String file = "data/ready/orders.csv";

            // Có thể kiểm tra file tồn tại, quyền đọc và metadata tại đây.
            contribution.getStepExecution()
                    .getExecutionContext()
                    .putString("validatedInputFile", file);

            return RepeatStatus.FINISHED;
        };

        return new StepBuilder("prepareFileStep", jobRepository)
                .tasklet(prepareTasklet, transactionManager)
                .listener(filePromotionListener)
                .build();
    }

    @Bean
    @StepScope
    Tasklet importFileTasklet(
            @Value("#{jobExecutionContext['validatedInputFile']}") String inputFile) {

        return (contribution, chunkContext) -> {
            if (inputFile == null || inputFile.isBlank()) {
                throw new IllegalStateException("validatedInputFile is missing");
            }

            // Thực hiện công việc import bằng inputFile.
            System.out.println("Import file: " + inputFile);
            return RepeatStatus.FINISHED;
        };
    }

    @Bean
    Step importFileStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet importFileTasklet) {

        return new StepBuilder("importFileStep", jobRepository)
                .tasklet(importFileTasklet, transactionManager)
                .build();
    }

    @Bean
    Job fileImportJob(
            JobRepository jobRepository,
            Step prepareFileStep,
            Step importFileStep) {

        return new JobBuilder("fileImportJob", jobRepository)
                .start(prepareFileStep)
                .next(importFileStep)
                .build();
    }
}
```

Ví dụ minh họa cơ chế trao đổi metadata. Trong ứng dụng thực tế, step chuẩn bị phải kiểm tra file thật và nên lưu một định danh bất biến hoặc đường dẫn đã chốt cho batch. Step import cần xử lý file theo logic nghiệp vụ phù hợp, có thể dùng chunk-oriented step nếu cần đọc và ghi nhiều item.

## 9. ExecutionContext và JobParameters khác nhau như thế nào?

Hai thành phần này đều cung cấp dữ liệu cho job nhưng có nguồn gốc và mục đích khác nhau.

| Tiêu chí | JobParameters | ExecutionContext |
|---|---|---|
| Nguồn tạo | Được cung cấp khi khởi chạy job. | Được cập nhật trong quá trình thực thi bởi job, step hoặc thành phần stream. |
| Vai trò | Đầu vào xác định đơn vị xử lý; identifying parameters góp phần xác định JobInstance. | Lưu trạng thái runtime, checkpoint và metadata giữa các bước. |
| Thời điểm có dữ liệu | Có trước khi job bắt đầu. | Có thể được tạo hoặc cập nhật khi job/step chạy. |
| Phạm vi | Gắn với JobExecution và JobInstance identity qua identifying values. | Có phạm vi JobExecution hoặc StepExecution. |
| Ví dụ | `businessDate`, `inputFile`, `sourceSystem`. | `validatedInputFile`, `lastProcessedId`, `readerCheckpoint`. |

Nếu người gọi cung cấp ngày nghiệp vụ, đó thường là JobParameter. Nếu step kiểm tra file rồi mới xác định đường dẫn đã được chấp nhận, đường dẫn đó có thể được ghi vào ExecutionContext. Không nên dùng ExecutionContext thay cho tham số định danh ban đầu của job.

## 10. ExecutionContext và restart

ExecutionContext hỗ trợ restart vì trạng thái được lưu trong JobRepository cùng metadata thực thi. Tuy nhiên, cần hiểu rõ context thuộc execution nào và khi nào trạng thái được lưu.

### Step ExecutionContext

Step ExecutionContext thường chứa checkpoint riêng của step. Với chunk-oriented step, Spring Batch cập nhật trạng thái stream tại ranh giới commit. Với tasklet step, mỗi lần gọi tasklet được quản lý trong transaction theo cấu hình; trạng thái step được lưu theo vòng đời thực thi tương ứng.

Nếu tasklet cập nhật context rồi transaction rollback, không nên giả định thay đổi đó đã được lưu bền vững. Việc cập nhật context và các thao tác nghiệp vụ liên quan cần nằm trong một thiết kế transaction nhất quán.

### Job ExecutionContext

Job ExecutionContext lưu trạng thái dùng chung trong một JobExecution. Dữ liệu cần cho step sau có thể được promote từ step trước. Khi job restart, Spring Batch tạo JobExecution mới cho cùng JobInstance; context của execution mới được khôi phục hoặc xây dựng theo cơ chế restart của framework và các step chạy lại. Không nên xem Job ExecutionContext như một biến dùng chung giữa mọi JobExecution của một JobInstance.

Ví dụ, nếu `prepareFileStep` đã hoàn tất và `importFileStep` thất bại, khi restart cùng JobInstance, step đã hoàn tất thường được bỏ qua. Job ExecutionContext của execution mới được khởi tạo theo metadata/restart state của framework. Nếu dữ liệu đã promote cần được dùng lại, phải bảo đảm cơ chế restart và dữ liệu context tương ứng được lưu/khôi phục đúng; nếu không, thiết kế flow để step chuẩn bị chạy lại hoặc tái tạo metadata cần thiết.

Với dữ liệu quan trọng, không nên chỉ dựa vào một key context mà không kiểm tra sự tồn tại và tính hợp lệ của resource được tham chiếu. Hãy kiểm tra file, batch ID hoặc version trước khi sử dụng.

## 11. Chọn phạm vi context phù hợp

Không phải mọi giá trị đều nên đưa vào Job ExecutionContext. Hãy chọn phạm vi dựa trên nơi sử dụng và vòng đời dữ liệu.

| Dữ liệu | Nơi lưu thường phù hợp | Lý do |
|---|---|---|
| Vị trí dòng hiện tại của reader | Step ExecutionContext | Trạng thái riêng của reader/step. |
| Số item đã xử lý trong step | Step ExecutionContext hoặc StepExecution counters | Chỉ có ý nghĩa trong step đó. |
| File đã kiểm tra cần dùng ở step tiếp theo | Step ExecutionContext rồi promote sang Job ExecutionContext | Metadata cần chia sẻ trong cùng JobExecution. |
| Ngày nghiệp vụ do scheduler truyền vào | JobParameters | Là đầu vào của lần xử lý và có thể tham gia identity. |
| Payload lớn hoặc danh sách hàng trăm nghìn bản ghi | Database, file hoặc object storage | ExecutionContext chỉ nên chứa metadata nhỏ. |
| Trạng thái cần tồn tại qua nhiều JobExecution hoặc nhiều job | Database nghiệp vụ hoặc hệ thống lưu trữ riêng | Context gắn với execution, không phải kho dữ liệu lâu dài. |

Job ExecutionContext nên chứa những giá trị nhỏ như file path, batch reference, snapshot version hoặc số lượng tổng hợp. Nếu cần chia sẻ tập dữ liệu lớn, hãy lưu dữ liệu ở nơi phù hợp và chỉ đưa khóa hoặc đường dẫn tham chiếu vào context.

## 12. Quy tắc đặt key và quản lý dữ liệu context

ExecutionContext là một map dùng chung trong phạm vi của nó. Nếu nhiều step ghi các key trùng tên, giá trị có thể bị ghi đè hoặc gây nhầm lẫn.

Một số quy tắc hữu ích:

- Dùng tên key mô tả rõ ý nghĩa, ví dụ `validatedInputFile` thay vì `file`.
- Có thể thêm tiền tố theo step hoặc miền nghiệp vụ, ví dụ `validation.outputFile` hoặc `orders.batchReference`.
- Thống nhất kiểu dữ liệu giữa nơi ghi và nơi đọc.
- Kiểm tra key bắt buộc trước khi sử dụng.
- Chỉ lưu dữ liệu nhỏ cần thiết cho điều phối hoặc restart.
- Xóa key khi không còn cần thiết nếu việc giữ lại gây nhầm lẫn hoặc tăng dữ liệu metadata.
- Không lưu password, token hoặc thông tin bí mật vào ExecutionContext nếu không có cơ chế bảo vệ phù hợp.

Ví dụ ghi nhiều giá trị:

```java
ExecutionContext context = contribution.getStepExecution()
        .getExecutionContext();

context.putString("validation.outputFile", "data/ready/orders.csv");
context.putLong("validation.recordCount", 1200L);
context.putString("validation.batchReference", "BATCH-20261115-01");
```

Khi đọc, dùng đúng key và kiểu:

```java
ExecutionContext context = contribution.getStepExecution()
        .getExecutionContext();

String outputFile = context.getString("validation.outputFile");
long recordCount = context.getLong("validation.recordCount");
String batchReference = context.getString("validation.batchReference");
```

Nếu các key có thể không tồn tại trong một nhánh flow, hãy kiểm tra trước khi đọc và xác định rõ hành vi khi thiếu dữ liệu.

## 13. Serialization và kiểu dữ liệu được lưu

ExecutionContext được lưu qua JobRepository, vì vậy giá trị phải có thể được serializer của Spring Batch ghi và đọc lại. Các kiểu dữ liệu đơn giản như String, số nguyên, Boolean thường thuận tiện. Với object tùy chỉnh, cần chú ý serializer và khả năng tương thích khi triển khai phiên bản ứng dụng mới.

Không nên lưu trực tiếp các object phụ thuộc tài nguyên đang mở như `InputStream`, `ResultSet`, `EntityManager` hoặc service bean. Những đối tượng này không phải trạng thái có thể phục hồi an toàn sau khi process kết thúc.

Thay vào đó, lưu thông tin đủ để mở lại tài nguyên:

```java
context.putString("inputFilePath", "/data/batch/orders.csv");
context.putLong("lastProcessedId", 98765L);
context.putString("snapshotVersion", "CUSTOMER-2026-11-15");
```

Khi restart, tasklet hoặc reader dùng các giá trị này để mở lại file, xây dựng truy vấn hoặc chọn đúng snapshot. Nếu dùng object tùy chỉnh, hãy bảo đảm schema/kiểu dữ liệu không thay đổi theo cách làm metadata cũ không thể deserialize.

## 14. Lỗi thường gặp khi Tasklet đọc ExecutionContext

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy key | Step trước chưa ghi key, flow rẽ nhánh hoặc promotion chưa chạy. | Kiểm tra step tạo dữ liệu, listener promotion và nhánh flow. |
| Đọc nhầm Step ExecutionContext | Key được lưu ở Job ExecutionContext hoặc ngược lại. | Xác định đúng phạm vi khi ghi và đọc. |
| Step sau không thấy dữ liệu step trước | Chỉ ghi vào Step ExecutionContext nhưng không promote. | Dùng `ExecutionContextPromotionListener` hoặc cơ chế truyền dữ liệu phù hợp. |
| Giá trị sai kiểu | Nơi ghi và nơi đọc dùng kiểu khác nhau. | Dùng key có quy ước kiểu rõ ràng và kiểm tra trước khi ép kiểu. |
| Giá trị không còn đúng sau restart | File hoặc resource đã bị thay đổi; context chỉ lưu đường dẫn cũ. | Giữ resource bất biến và lưu batch ID/version/checksum. |
| Context chứa quá nhiều dữ liệu | Dùng ExecutionContext như kho dữ liệu. | Lưu dữ liệu lớn ở database/file/object storage, chỉ lưu tham chiếu. |
| Context update không được lưu như mong đợi | Transaction rollback hoặc cập nhật ngoài vòng đời quản lý của framework. | Cập nhật trong transaction và hiểu thời điểm checkpoint/persist. |
| Dữ liệu cũ bị ghi đè | Nhiều step dùng chung key hoặc đặt tên quá chung. | Dùng key có namespace và xác định rõ quyền sở hữu. |
| Lỗi deserialize sau khi nâng cấp | Lưu object tùy chỉnh không tương thích với phiên bản mới. | Ưu tiên kiểu dữ liệu ổn định, quản lý version và có kế hoạch tương thích metadata. |

## 15. Cách đọc code Tasklet có sử dụng ExecutionContext

Khi gặp một tasklet đọc context, hãy lần theo các bước sau:

1. **Tìm nguồn key:** tìm nơi gọi `putString`, `putLong`, `put` hoặc nơi reader/writer lưu checkpoint.
2. **Xác định phạm vi:** key nằm trong Step ExecutionContext hay Job ExecutionContext?
3. **Kiểm tra promotion:** nếu step khác cần dùng key của step hiện tại, có listener hoặc cơ chế promotion nào không?
4. **Kiểm tra kiểu dữ liệu:** nơi ghi và nơi đọc có dùng cùng kiểu không?
5. **Kiểm tra thời điểm lưu:** context được cập nhật trong transaction nào và ở ranh giới commit nào?
6. **Kiểm tra restart:** khi step chạy lại, key được khôi phục, tạo lại hay cần step trước chạy lại?
7. **Kiểm tra resource được tham chiếu:** file, snapshot hoặc batch ID có còn hợp lệ không?
8. **Kiểm tra xử lý thiếu key:** tasklet báo lỗi rõ ràng hay vô tình dùng giá trị null/mặc định không an toàn?

Đặc biệt, nếu tasklet lấy giá trị bằng `@Value("#{jobExecutionContext['...']}")`, hãy tìm step trước đã ghi và promote key đó. Nếu tasklet đọc trực tiếp từ `contribution.getStepExecution()`, hãy xác định context thuộc đúng StepExecution hiện tại.

## 16. Những điểm cần ghi nhớ

- `ExecutionContext` là vùng key-value được lưu cùng metadata của Spring Batch.
- Step ExecutionContext thuộc một StepExecution; Job ExecutionContext thuộc một JobExecution.
- Tasklet có thể lấy StepExecution từ `StepContribution` hoặc `ChunkContext` rồi đọc hai phạm vi context tương ứng.
- Dùng `containsKey` và kiểm tra kiểu dữ liệu trước khi sử dụng key bắt buộc.
- Dữ liệu trong Step ExecutionContext không tự động xuất hiện trong Job ExecutionContext.
- Dùng `ExecutionContextPromotionListener` để promote những key cần chia sẻ sang các step sau.
- `@StepScope` kết hợp SpEL như `#{stepExecutionContext['key']}` hoặc `#{jobExecutionContext['key']}` hỗ trợ late binding.
- JobParameters là đầu vào lúc khởi chạy; ExecutionContext lưu trạng thái phát sinh trong quá trình thực thi.
- Context chỉ nên chứa metadata nhỏ và kiểu dữ liệu có thể serialize/deserialize an toàn.
- Không xem Job ExecutionContext là kho lưu trữ lâu dài dùng chung giữa mọi JobExecution.
- Khi restart, phải hiểu rõ execution nào sở hữu context và bảo đảm resource được tham chiếu vẫn nhất quán.

Khi tasklet đọc ExecutionContext, hãy xác định đúng phạm vi context, key được tạo ở đâu, kiểu dữ liệu và thời điểm trạng thái được lưu. Nếu cần chuyển metadata từ step này sang step khác, hãy promote có chủ đích sang Job ExecutionContext. Cách làm đó giúp job trao đổi dữ liệu nhỏ rõ ràng và có thể theo dõi, khôi phục trong vòng đời thực thi của Spring Batch.
