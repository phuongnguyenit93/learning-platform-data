# Hiển thị parameters trong metadata

Trong Spring Batch, `JobParameters` là tập giá trị đầu vào được truyền khi khởi chạy một Job. Các tham số này có thể xác định phạm vi dữ liệu cần xử lý, ví dụ ngày nghiệp vụ, tên tệp, mã khách hàng hoặc mã đợt import. Spring Batch lưu tham số vào metadata repository để có thể tra cứu lại một lần chạy, xác định `JobInstance` và hỗ trợ restart.

Với JDBC JobRepository, tham số của mỗi lần chạy được lưu trong bảng `BATCH_JOB_EXECUTION_PARAMS`. Bảng này gắn các tham số với `JobExecution`, do đó có thể xem một lần chạy đã nhận những giá trị nào, kiểu dữ liệu ra sao và tham số nào tham gia định danh JobInstance. Có thể đọc dữ liệu qua SQL hoặc dùng API `JobExplorer`/`JobExecution` của Spring Batch.

## 1. JobParameters là gì và được lưu ở đâu?

`JobParameters` là tập các tham số được truyền cho Job khi launch. Mỗi tham số có tên, giá trị, kiểu dữ liệu và thuộc tính identifying. Ví dụ một Job import đơn hàng có thể nhận:

| Tên tham số | Giá trị ví dụ | Identifying |
|---|---|---|
| `businessDate` | `2026-11-15` | Có |
| `inputFile` | `orders-2026-11-15.csv` | Có |
| `requestedBy` | `scheduler` | Không |
| `dryRun` | `false` | Không |

Khi `JobLauncher` khởi chạy Job, Spring Batch tạo hoặc tìm `JobInstance` dựa trên tên Job và các tham số identifying. Mỗi lần thực thi cụ thể được đại diện bởi `JobExecution`. Tham số được lưu theo `JobExecution`, vì vậy cùng một JobInstance có thể có nhiều JobExecution và mỗi execution có bản ghi tham số gắn với ID riêng.

Quan hệ khái quát:

```text
BATCH_JOB_INSTANCE
  JOB_INSTANCE_ID
       |
       | 1 - N
       v
BATCH_JOB_EXECUTION
  JOB_EXECUTION_ID
       |
       | 1 - N
       v
BATCH_JOB_EXECUTION_PARAMS
  JOB_EXECUTION_ID
  PARAMETER_NAME / KEY_NAME
  PARAMETER_VALUE / *_VAL
  IDENTIFYING
```

`BATCH_JOB_EXECUTION_PARAMS` là bảng cần xem khi muốn biết một execution đã được khởi chạy với tham số nào. Nó không phải bảng lưu checkpoint của Step; checkpoint và trạng thái thực thi nằm trong các bảng ExecutionContext tương ứng.

## 2. Identifying và non-identifying parameters

Mỗi `JobParameter` có thuộc tính identifying. Các tham số identifying tham gia tạo khóa định danh của JobInstance; các tham số non-identifying được lưu cùng execution nhưng không làm thay đổi định danh JobInstance.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "orders-2026-11-15.csv", true)
        .addString("requestedBy", "scheduler", false)
        .addString("dryRun", "false", false)
        .toJobParameters();
```

Trong ví dụ, `businessDate` và `inputFile` tham gia xác định JobInstance. `requestedBy` và `dryRun` là thông tin bổ sung cho execution. Nếu cùng tên Job và cùng identifying parameters được gửi lại, Spring Batch xác định đó là cùng JobInstance, kể cả khi các tham số non-identifying khác nhau.

Việc chọn identifying parameter cần bám sát ý nghĩa nghiệp vụ:

- Ngày nghiệp vụ thường là identifying nếu mỗi ngày là một đợt xử lý riêng.
- Mã tệp hoặc mã batch có thể là identifying nếu nó xác định duy nhất tập dữ liệu cần xử lý.
- Người yêu cầu, nhãn log hoặc thông tin tương quan request thường là non-identifying.
- Một cờ thay đổi kết quả nghiệp vụ có thể cần identifying, tùy việc hai chế độ chạy có được xem là cùng một JobInstance hay không.

Không nên đánh dấu tất cả tham số là identifying một cách máy móc. Nếu một giá trị chỉ phục vụ ghi log nhưng được đánh dấu identifying, mỗi giá trị khác nhau có thể tạo JobInstance mới. Ngược lại, nếu tham số làm thay đổi tập dữ liệu nghiệp vụ nhưng không identifying, hai yêu cầu khác nhau có thể bị xem là cùng JobInstance.

## 3. Bảng BATCH_JOB_EXECUTION_PARAMS trong Spring Batch 5

Từ Spring Batch 5, schema chuẩn của bảng tham số dùng cấu trúc tổng quát hơn. Các cột thường gặp gồm:

| Cột | Ý nghĩa |
|---|---|
| `JOB_EXECUTION_ID` | ID của JobExecution sở hữu tham số. |
| `PARAMETER_NAME` | Tên tham số. |
| `PARAMETER_TYPE` | Tên lớp Java của kiểu dữ liệu tham số. |
| `PARAMETER_VALUE` | Giá trị tham số được biểu diễn dưới dạng chuỗi. |
| `IDENTIFYING` | Cờ cho biết tham số có tham gia định danh JobInstance hay không. |

Ví dụ dữ liệu minh họa:

| JOB_EXECUTION_ID | PARAMETER_NAME | PARAMETER_TYPE | PARAMETER_VALUE | IDENTIFYING |
|---:|---|---|---|---|
| 9002 | `businessDate` | `java.lang.String` | `2026-11-15` | `Y` |
| 9002 | `inputFile` | `java.lang.String` | `orders-2026-11-15.csv` | `Y` |
| 9002 | `requestedBy` | `java.lang.String` | `scheduler` | `N` |
| 9002 | `recordLimit` | `java.lang.Long` | `5000` | `N` |

Tên và kiểu cột cụ thể cần được đối chiếu với schema script đi kèm phiên bản Spring Batch đang chạy. Không nên giả định schema của mọi phiên bản đều giống bảng minh họa.

### Vì sao có PARAMETER_TYPE?

Spring Batch 5 hỗ trợ `JobParameter` với kiểu dữ liệu tổng quát. Vì vậy, metadata cần lưu thông tin kiểu để khi đọc lại có thể chuyển giá trị về đúng kiểu Java. Ví dụ, giá trị `5000` có thể là `String`, `Long` hoặc một kiểu khác; chỉ nhìn `PARAMETER_VALUE` thì không thể xác định chính xác kiểu.

Đối với kiểu dữ liệu tùy chỉnh, việc chuyển đổi sang và từ chuỗi cần có converter phù hợp. Nếu ứng dụng dùng kiểu tùy chỉnh trong JobParameters, hãy bảo đảm quá trình serialize/deserialize tương thích giữa các phiên bản ứng dụng có thể đọc cùng metadata.

## 4. Khác biệt với schema Spring Batch 4

Trong các phiên bản Spring Batch trước 5, `BATCH_JOB_EXECUTION_PARAMS` thường lưu giá trị theo các cột riêng cho từng nhóm kiểu dữ liệu. Các cột thường thấy gồm:

| Cột cũ | Ý nghĩa |
|---|---|
| `JOB_EXECUTION_ID` | ID của JobExecution. |
| `TYPE_CD` | Mã kiểu dữ liệu. |
| `KEY_NAME` | Tên tham số. |
| `STRING_VAL` | Giá trị kiểu String. |
| `DATE_VAL` | Giá trị kiểu Date. |
| `LONG_VAL` | Giá trị kiểu Long. |
| `DOUBLE_VAL` | Giá trị kiểu Double. |
| `IDENTIFYING` | Cờ identifying. |

Khi chuyển từ Spring Batch 4 sang Spring Batch 5, cấu trúc tham số thay đổi từ các cột giá trị theo kiểu sang bộ cột `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE` và `IDENTIFYING`. Vì vậy, câu SQL truy vấn bảng này cần được cập nhật theo schema mới.

Không chạy ứng dụng Spring Batch 5 trên schema cũ mà chưa migration. Framework có thể báo lỗi thiếu cột hoặc lỗi đọc/ghi tham số. Cũng không nên lấy DDL Spring Batch 5 áp dụng cho ứng dụng vẫn chạy Spring Batch 4. Luôn lấy schema script tương ứng với phiên bản thực tế.

## 5. Truy vấn parameters bằng SQL

SQL hữu ích khi cần kiểm tra metadata trực tiếp, tạo báo cáo vận hành hoặc điều tra một lần chạy cụ thể. Với schema Spring Batch 5, có thể truy vấn tham số theo `JOB_EXECUTION_ID`:

```sql
SELECT
    JOB_EXECUTION_ID,
    PARAMETER_NAME,
    PARAMETER_TYPE,
    PARAMETER_VALUE,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = 9002
ORDER BY PARAMETER_NAME;
```

Kết quả cho biết toàn bộ tham số đã lưu cho execution 9002, gồm tên, kiểu, giá trị và cờ identifying. Thay ID minh họa bằng ID thực tế cần tra cứu.

### Hiển thị tham số cùng tên Job và trạng thái execution

Để xem tham số trong ngữ cảnh Job, có thể JOIN với hai bảng execution và instance:

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS p
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_EXECUTION_ID = p.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID = 9002
ORDER BY p.PARAMETER_NAME;
```

Truy vấn này giúp liên hệ một tham số với Job name, JobInstance, JobExecution và trạng thái lần chạy. Các tên cột thời gian có thể khác giữa các phiên bản schema; điều chỉnh theo DDL thực tế.

### Xem lịch sử tham số của nhiều lần chạy

Khi cần so sánh các lần chạy của cùng một Job, lọc theo tên Job và sắp xếp theo execution:

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    p.PARAMETER_NAME,
    p.PARAMETER_TYPE,
    p.PARAMETER_VALUE,
    p.IDENTIFYING
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
JOIN BATCH_JOB_EXECUTION_PARAMS p
    ON p.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
WHERE ji.JOB_NAME = 'importOrdersJob'
ORDER BY je.JOB_EXECUTION_ID DESC, p.PARAMETER_NAME;
```

Truy vấn có thể trả về nhiều dòng cho mỗi JobExecution vì mỗi tham số là một dòng riêng. Một JobInstance có thể có nhiều JobExecution; do đó, hãy dùng cả `JOB_INSTANCE_ID` và `JOB_EXECUTION_ID` khi cần phân biệt một lần nghiệp vụ với một lần thử chạy.

### Truy vấn schema Spring Batch 4

Nếu ứng dụng vẫn dùng schema cũ, câu SQL có dạng khác:

```sql
SELECT
    JOB_EXECUTION_ID,
    KEY_NAME,
    TYPE_CD,
    STRING_VAL,
    DATE_VAL,
    LONG_VAL,
    DOUBLE_VAL,
    IDENTIFYING
FROM BATCH_JOB_EXECUTION_PARAMS
WHERE JOB_EXECUTION_ID = 9002
ORDER BY KEY_NAME;
```

Trong schema cũ, thường chỉ một trong các cột giá trị theo kiểu chứa giá trị cho một tham số. Không nên áp dụng truy vấn này cho schema Spring Batch 5.

## 6. Hiển thị parameters bằng JobExplorer

Trong ứng dụng Java, nên ưu tiên API Spring Batch khi cần đọc metadata. `JobExplorer` cho phép tra cứu `JobExecution`; từ đó có thể lấy `JobParameters` mà execution đã sử dụng.

Ví dụ với Spring Batch 5:

```java
@Service
public class JobParameterQueryService {

    private final JobExplorer jobExplorer;

    public JobParameterQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printParameters(long jobExecutionId) {
        JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);
        if (execution == null) {
            System.out.println("JobExecution not found: " + jobExecutionId);
            return;
        }

        JobParameters parameters = execution.getJobParameters();

        parameters.getParameters().forEach((name, parameter) -> {
            System.out.printf(
                    "%s=%s (type=%s, identifying=%s)%n",
                    name,
                    parameter.getValue(),
                    parameter.getType().getName(),
                    parameter.isIdentifying());
        });
    }
}
```

Trong Spring Batch 5, `JobParameters.getParameters()` trả về map các `JobParameter<?>`. Mỗi tham số cung cấp giá trị, kiểu và identifying flag. Cách đọc này tránh phải tự giải mã cấu trúc lưu trữ SQL và phù hợp hơn khi schema thay đổi giữa các phiên bản.

Khi JobExecution đang chạy, dữ liệu đọc từ repository phản ánh metadata đã được lưu tại thời điểm truy vấn. Nó không nhất thiết phản ánh thay đổi chưa commit hoặc trạng thái tạm thời trong bộ nhớ của tiến trình đang chạy.

### Đọc một tham số cụ thể

Nếu biết tên tham số, có thể lấy trực tiếp từ `JobParameters`:

```java
JobExecution execution = jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    JobParameters parameters = execution.getJobParameters();
    String inputFile = parameters.getString("inputFile");
    Long recordLimit = parameters.getLong("recordLimit");
}
```

Các phương thức lấy theo kiểu cần phù hợp với kiểu thực tế đã lưu. Nếu tham số có kiểu tùy chỉnh, hãy dùng API tham số tổng quát và converter tương ứng thay vì ép kiểu tùy tiện.

## 7. Hiển thị parameters trong listener và log

Trong lúc Job chạy, listener có thể đọc JobParameters từ `JobExecution` để ghi nhận ngữ cảnh của execution. Ví dụ, `JobExecutionListener` có thể log những thông tin không nhạy cảm trước khi Job bắt đầu:

```java
public class JobParameterLoggingListener implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution jobExecution) {
        JobParameters parameters = jobExecution.getJobParameters();

        String businessDate = parameters.getString("businessDate");
        String inputFile = parameters.getString("inputFile");

        System.out.printf(
                "Starting job=%s, executionId=%d, businessDate=%s, inputFile=%s%n",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId(),
                businessDate,
                inputFile);
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        System.out.printf(
                "Finished executionId=%d, status=%s, exitCode=%s%n",
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());
    }
}
```

Đăng ký listener với Job bằng `.listener(jobParameterLoggingListener)`. Trong hệ thống thực tế, cần lọc hoặc che các tham số nhạy cảm trước khi log. Không nên log toàn bộ `JobParameters` theo cách gọi `toString()` nếu không kiểm soát nội dung có thể xuất hiện.

Listener phù hợp để ghi nhận thông tin lúc bắt đầu/kết thúc. Nếu cần hiển thị lịch sử execution trên màn hình quản trị, nên dùng service truy vấn `JobExplorer` thay vì dựa vào log ứng dụng.

## 8. JobParameters khác ExecutionContext như thế nào?

Hai cơ chế đều có thể lưu dữ liệu liên quan đến execution nhưng mục đích khác nhau:

| Tiêu chí | JobParameters | ExecutionContext |
|---|---|---|
| Thời điểm cung cấp | Được truyền khi launch Job. | Được cập nhật trong quá trình thực thi. |
| Mục đích | Mô tả đầu vào và định danh lần nghiệp vụ. | Lưu trạng thái, checkpoint và dữ liệu cần khôi phục/chia sẻ. |
| Phạm vi | Gắn với JobExecution. | Có phạm vi JobExecution hoặc StepExecution. |
| Identifying | Có cờ identifying để xác định JobInstance. | Không dùng để xác định JobInstance. |
| Bảng metadata | `BATCH_JOB_EXECUTION_PARAMS`. | `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT`. |

Ví dụ, `businessDate` và `inputFile` là đầu vào của Job nên thường là JobParameters. Vị trí dòng cuối cùng đã đọc trong tệp là trạng thái tiến độ nên thuộc Step ExecutionContext. Không nên lưu checkpoint thay đổi liên tục như JobParameter vì JobParameters mô tả đầu vào của lần chạy, còn ExecutionContext được thiết kế cho trạng thái trong quá trình chạy.

## 9. Parameters và restart

Khi một Job thất bại và được restart, Spring Batch dùng identifying parameters để xác định JobInstance tương ứng. Lần chạy tiếp theo tạo một JobExecution mới cho cùng JobInstance nếu các điều kiện restart được đáp ứng.

Điều này có một số hệ quả:

- Khi muốn restart, phải giữ đúng định danh JobInstance bằng identifying parameters.
- Nếu thay identifying parameter, Spring Batch có thể xem đó là JobInstance mới thay vì restart.
- Non-identifying parameters không tham gia định danh, nhưng vẫn được lưu cho từng JobExecution.
- Các tham số được dùng trong lần execution cụ thể có thể được xem lại qua metadata của chính execution đó.

Ví dụ, `businessDate` xác định đợt nghiệp vụ; `requestedBy` chỉ ghi nhận ai gửi yêu cầu. Nếu Job thất bại, việc đổi `businessDate` có thể tạo một JobInstance khác. Nếu chỉ thay `requestedBy`, định danh JobInstance vẫn dựa trên các tham số identifying.

Không nên tự động thêm timestamp vào identifying parameters mỗi lần caller retry request. Nếu request trước đã được JobRepository tiếp nhận nhưng response bị mất, một timestamp mới sẽ tạo định danh mới và có thể khiến dữ liệu được xử lý lần nữa. Dùng idempotency key hoặc business key để caller nhận diện yêu cầu trước.

## 10. Hiển thị parameters trên màn hình quản trị

Một màn hình theo dõi Batch thường cần hiển thị đủ thông tin để người vận hành nhận biết lần chạy và hiểu phạm vi dữ liệu:

- Tên Job và JobInstance ID.
- JobExecution ID và trạng thái hiện tại.
- Thời điểm bắt đầu, kết thúc và thời gian chạy.
- Tên tham số, giá trị đã được che nếu cần, kiểu dữ liệu và identifying flag.
- Exit code/message và thông tin lỗi đã được kiểm soát.

Nên nhóm tham số theo JobExecution. Nếu hiển thị lịch sử nhiều lần chạy, cần cho phép người dùng phân biệt các execution của cùng một JobInstance. Một bảng minh họa:

| JobExecution | Status | Parameter | Value | Identifying |
|---:|---|---|---|---|
| 9002 | `COMPLETED` | `businessDate` | `2026-11-15` | Yes |
| 9002 | `COMPLETED` | `inputFile` | `orders-2026-11-15.csv` | Yes |
| 9002 | `COMPLETED` | `requestedBy` | `scheduler` | No |

Nếu hiển thị nhiều JobExecution, không gộp tham số chỉ theo JobInstance mà bỏ mất execution ID. Việc đó có thể làm người vận hành hiểu nhầm giá trị đã dùng trong một lần chạy cụ thể.

Đối với kiểu tùy chỉnh, có thể hiển thị tên kiểu và biểu diễn an toàn của giá trị. Không nên giả định mọi giá trị đều là chuỗi có thể đưa trực tiếp lên HTML hoặc log; cần encode output và giới hạn độ dài.

## 11. Bảo mật khi lưu và hiển thị parameters

JobParameters được lưu trong metadata repository, thường tồn tại lâu hơn request ban đầu. Vì vậy, không nên truyền bí mật chỉ để một Step có thể đọc được.

Tránh lưu trực tiếp:

- Mật khẩu database hoặc mật khẩu dịch vụ.
- Access token, refresh token, API key hoặc private key.
- URL có chứa thông tin đăng nhập.
- Nội dung dữ liệu cá nhân hoặc payload lớn không cần thiết cho định danh Job.

Thay vào đó, lưu một tham chiếu an toàn như mã cấu hình, secret alias hoặc ID tài nguyên; Step lấy bí mật từ secret manager hoặc cấu hình bảo mật phù hợp khi thực thi.

Nếu tham số có chứa dữ liệu nhạy cảm do yêu cầu nghiệp vụ, cần đánh giá quyền đọc bảng metadata, quyền truy cập màn hình quản trị, chính sách mã hóa, retention và log masking. `PARAMETER_VALUE` có thể được đọc bởi người có quyền truy vấn database; việc ẩn giá trị trên UI không tự bảo vệ dữ liệu ở database.

Khi ghi log, chỉ ghi tên tham số hoặc các giá trị đã được cho phép. Có thể dùng danh sách cho phép để log một số trường như `businessDate` và che các trường khác. Tránh ghi nguyên exception message nếu nó có thể chứa toàn bộ tham số.

## 12. Giới hạn và lưu ý khi truy vấn metadata trực tiếp

SQL rất hữu ích cho điều tra, nhưng cấu trúc bảng là chi tiết triển khai của JDBC JobRepository và có thể thay đổi theo phiên bản, database hoặc table prefix.

Một số nguyên tắc:

- Dùng đúng schema script theo phiên bản Spring Batch.
- Xác định table prefix nếu ứng dụng không dùng `BATCH_` mặc định.
- Không giả định kiểu dữ liệu và cách lưu tham số giống nhau giữa Batch 4 và Batch 5.
- Chỉ dùng câu lệnh `SELECT` cho nhu cầu hiển thị và báo cáo thông thường.
- Không cập nhật hoặc xóa trực tiếp tham số của execution đang chạy.
- Khi cần đọc metadata trong ứng dụng, ưu tiên `JobExplorer` và `JobExecution`.
- Khi cần migration, dùng quy trình có phiên bản và kiểm thử trên bản sao dữ liệu.

Nếu ứng dụng dùng repository tùy chỉnh hoặc không dùng JDBC JobRepository, cách lưu metadata có thể khác. Không nên giả định luôn tồn tại bảng `BATCH_JOB_EXECUTION_PARAMS` trong mọi loại repository.

## 13. Những lỗi thường gặp

### Không tìm thấy bảng BATCH_JOB_EXECUTION_PARAMS

Schema có thể chưa được khởi tạo, datasource trỏ nhầm database hoặc repository dùng table prefix khác. Kiểm tra cấu hình datasource, `spring.batch.jdbc.initialize-schema`, schema owner và prefix.

### Câu SQL dùng cột PARAMETER_NAME nhưng database chỉ có KEY_NAME

Đây thường là dấu hiệu đang dùng schema cũ của Spring Batch 4 trong khi câu SQL được viết cho Spring Batch 5, hoặc ngược lại. Xác định phiên bản framework và DDL đang chạy rồi điều chỉnh truy vấn.

### Giá trị hiển thị không đúng kiểu mong đợi

Trong schema Batch 5, `PARAMETER_VALUE` là biểu diễn chuỗi và `PARAMETER_TYPE` cho biết kiểu cần khôi phục. Đừng tự parse mọi giá trị thành String hoặc Long. Dùng API JobParameters hoặc converter phù hợp.

### Không thấy tham số trong lần chạy dự kiến

Có thể đang tra cứu nhầm `JOB_EXECUTION_ID`, nhầm JobExecution của cùng JobInstance hoặc dùng nhầm database/schema. JOIN qua JobExecution và JobInstance để xác nhận đúng lần chạy.

### Nhầm tham số với checkpoint

`BATCH_JOB_EXECUTION_PARAMS` lưu đầu vào của JobExecution. Checkpoint trong quá trình xử lý nằm trong ExecutionContext. Hãy tra cứu đúng bảng theo mục đích.

### Lộ thông tin nhạy cảm trên UI hoặc log

JobParameters có thể lưu lâu dài. Kiểm tra nội dung tham số trước khi hiển thị hoặc ghi log; mask giá trị nhạy cảm và hạn chế quyền đọc metadata.

## 14. Quy trình tra cứu parameters của một lần chạy

Khi cần biết Job đã chạy với tham số nào, có thể thực hiện theo trình tự:

1. Xác định tên Job và `JOB_EXECUTION_ID` cần tra cứu.
2. Kiểm tra `BATCH_JOB_EXECUTION` để xác nhận trạng thái và thời điểm chạy.
3. Truy vấn `BATCH_JOB_EXECUTION_PARAMS` theo execution ID hoặc dùng `JobExplorer`.
4. Đọc tên, kiểu, giá trị và identifying flag của từng tham số.
5. Đối chiếu identifying parameters với JobInstance để hiểu vì sao Spring Batch xem lần chạy là cùng hay khác instance.
6. Nếu cần kiểm tra tiến độ hoặc vị trí restart, xem thêm Job/Step ExecutionContext tương ứng.
7. Che hoặc loại bỏ giá trị nhạy cảm trước khi đưa kết quả lên màn hình quản trị hay log.

## Kết luận

Spring Batch lưu `JobParameters` của từng lần chạy trong `BATCH_JOB_EXECUTION_PARAMS`. Với Spring Batch 5, bảng thường có các cột `PARAMETER_NAME`, `PARAMETER_TYPE`, `PARAMETER_VALUE` và `IDENTIFYING`; schema Spring Batch 4 dùng cấu trúc cột khác. Có thể hiển thị tham số bằng SQL để điều tra hoặc dùng `JobExplorer` và `JobExecution.getJobParameters()` trong ứng dụng. Khi trình bày metadata, cần phân biệt identifying với non-identifying parameters, phân biệt JobParameters với ExecutionContext, và bảo vệ các giá trị nhạy cảm đã được lưu lâu dài.
