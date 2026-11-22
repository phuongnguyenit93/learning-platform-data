# Tránh tạo instance mới ngoài ý muốn

Trong Spring Batch, JobInstance đại diện cho một lần xử lý logic của Job với một phạm vi dữ liệu xác định. Spring Batch nhận diện instance dựa trên **tên Job và các JobParameters được đánh dấu identifying**. Vì vậy, chỉ một thay đổi nhỏ trong tham số cũng có thể khiến framework hiểu rằng ứng dụng đang yêu cầu một công việc mới.

Điều này đặc biệt quan trọng khi restart. Nếu một Job thất bại nhưng lần khởi chạy tiếp theo vô tình truyền một timestamp hoặc UUID mới ở dạng identifying, Spring Batch sẽ tạo JobInstance khác. Instance mới không kế thừa lịch sử và checkpoint của instance thất bại, nên quy trình restart mong muốn không diễn ra.

Bài học này giải thích cách tránh tạo JobInstance mới ngoài ý muốn, cách phân biệt restart với một lần xử lý nghiệp vụ mới và cách kiểm soát JobParameters ở nơi khởi chạy Job.

## 1. JobInstance được xác định như thế nào?

Spring Batch dùng hai thành phần để xác định JobInstance:

~~~text
JobInstance = Job name + identifying JobParameters
~~~

Job name xác định định nghĩa Job. Identifying JobParameters xác định phạm vi công việc mà instance đại diện. Mỗi JobParameter có tên, giá trị, kiểu dữ liệu và cờ identifying:

- **identifying = true**: tham số tham gia xác định JobInstance.
- **identifying = false**: tham số được truyền cho JobExecution nhưng không làm thay đổi danh tính JobInstance.

Ví dụ Job nhập đơn hàng theo ngày có thể dùng businessDate làm tham số định danh. Mọi lần khởi chạy với cùng Job name và cùng businessDate sẽ trỏ đến cùng JobInstance, miễn là các identifying parameters khác cũng giống nhau.

~~~text
Job: dailyOrderImport
    |
    +-- JobInstance: businessDate=2026-11-15
    |       |
    |       +-- JobExecution #1: FAILED
    |       |
    |       +-- JobExecution #2: COMPLETED
    |
    +-- JobInstance: businessDate=2026-11-16
            |
            +-- JobExecution #1: COMPLETED
~~~

Trong sơ đồ, hai JobExecution đầu tiên thuộc cùng một JobInstance vì chúng xử lý cùng ngày nghiệp vụ. Instance của ngày 16/11/2026 là một instance khác vì businessDate đã thay đổi.

Đừng đồng nhất một lần gọi JobLauncher với một JobInstance. Nhiều JobExecution có thể thuộc cùng một JobInstance, chẳng hạn khi Job được restart sau thất bại. Ngược lại, hai lần gọi JobLauncher có thể tạo hai JobInstance khác nhau nếu các identifying parameters khác nhau.

## 2. Identifying và non-identifying parameters

Lựa chọn cờ identifying phải phản ánh ý nghĩa nghiệp vụ của tham số. Một tham số là identifying khi thay đổi giá trị của nó có nghĩa là Job đang xử lý một phạm vi dữ liệu hoặc một lần nghiệp vụ khác.

| Tham số | Cách đánh dấu thường dùng | Lý do |
| --- | --- | --- |
| businessDate | Identifying | Mỗi ngày là một phạm vi dữ liệu riêng |
| inputFileId | Identifying | Mỗi file đầu vào bất biến đại diện cho một tập dữ liệu |
| tenantId | Identifying | Dữ liệu của mỗi tenant là một phạm vi riêng |
| dataRevision | Identifying | Mỗi phiên bản dữ liệu cần được xử lý riêng |
| requestedBy | Non-identifying | Ghi nhận người yêu cầu chạy |
| requestId hoặc correlationId | Non-identifying | Theo dõi request và liên kết log |
| requestedAt | Non-identifying | Ghi nhận thời điểm yêu cầu |
| notificationEmail | Non-identifying | Chỉ phục vụ thông báo |

Đây là quy ước theo ngữ nghĩa, không phải danh sách cứng. Ví dụ, dryRun nên là identifying nếu chế độ này thay đổi kết quả hoặc cách xử lý và hai chế độ cần được quản lý như hai lần xử lý khác nhau. Nếu một tham số tưởng như chỉ để audit nhưng lại thay đổi dữ liệu được đọc hoặc ghi, nó cần tham gia danh tính instance.

### Khai báo cờ identifying tường minh

Hãy truyền cờ identifying rõ ràng khi tạo JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-file-2026-11-15", true)
        .addLong("tenantId", 42L, true)
        .addString("requestedBy", "scheduler", false)
        .addString("requestId", "request-8f31", false)
        .toJobParameters();
~~~

Trong ví dụ:

- businessDate, inputFileId và tenantId xác định JobInstance.
- requestedBy và requestId vẫn có thể được đọc trong Job hoặc Step, nhưng thay đổi các giá trị này không tạo instance mới.

Các overload của JobParametersBuilder có thể cung cấp giá trị mặc định cho cờ identifying. Để tránh dựa vào mặc định hoặc nhầm lẫn khi nâng cấp framework, nên dùng overload có tham số boolean và khai báo rõ true hoặc false cho từng giá trị.

## 3. Timestamp và UUID có thể vô tình tạo instance mới

Một lỗi thường gặp là thêm thời điểm hiện tại vào JobParameters để tiện theo dõi:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("startedAt", Instant.now().toString(), true)
        .toJobParameters();
~~~

Vì startedAt là identifying, mỗi lần gọi sẽ có một giá trị khác nhau. Spring Batch xem mỗi yêu cầu là một JobInstance mới, kể cả khi businessDate không đổi và Job đang được khởi động lại sau thất bại.

UUID hoặc random number cũng gây ra vấn đề tương tự nếu được đánh dấu identifying:

~~~java
// Mỗi lần gọi tạo một danh tính instance khác.
parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("runId", UUID.randomUUID().toString(), true)
        .toJobParameters();
~~~

Nếu timestamp hoặc UUID chỉ phục vụ trace, hãy để chúng non-identifying hoặc ghi vào hệ thống audit/log riêng:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("startedAt", Instant.now().toString(), false)
        .addString("requestId", UUID.randomUUID().toString(), false)
        .toJobParameters();
~~~

Chỉ đánh dấu một giá trị là identifying nếu thay đổi giá trị đó thực sự có nghĩa là một phạm vi nghiệp vụ mới. Không dùng timestamp hoặc UUID như một cách tiện lợi để buộc Spring Batch tạo instance mới.

Lưu ý: non-identifying không có nghĩa là tham số bị loại bỏ. Job vẫn có thể đọc nó. Vì vậy, không nên để logic nghiệp vụ phụ thuộc vào một giá trị non-identifying nếu thay đổi giá trị đó có thể làm kết quả xử lý khác đi. Nếu nó làm thay đổi dữ liệu được xử lý hoặc kết quả cần quản lý riêng, hãy xem xét đưa nó vào danh tính instance.

## 4. Dùng JobParameters ổn định khi khởi chạy và restart

Giả sử Job nhập dữ liệu theo ngày. Ứng dụng có thể tạo bộ tham số từ khóa nghiệp vụ ổn định:

~~~java
public JobParameters buildParameters(
        LocalDate businessDate,
        String inputFileId,
        String requestedBy) {

    return new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("inputFileId", inputFileId, true)
            .addString("requestedBy", requestedBy, false)
            .toJobParameters();
}
~~~

Khởi chạy Job:

~~~java
JobParameters parameters = buildParameters(
        LocalDate.of(2026, 11, 15),
        "orders-file-2026-11-15",
        "scheduler"
);

JobExecution execution = jobLauncher.run(dailyOrderImport, parameters);
~~~

Khi cần restart instance này, ứng dụng phải tái tạo cùng Job name và cùng các giá trị identifying:

~~~java
JobParameters restartParameters = buildParameters(
        LocalDate.of(2026, 11, 15),
        "orders-file-2026-11-15",
        "scheduler"
);

JobExecution restartedExecution =
        jobLauncher.run(dailyOrderImport, restartParameters);
~~~

Nếu execution trước thất bại hoặc dừng và Job cho phép restart, Spring Batch có thể tạo JobExecution mới cho cùng JobInstance. Metadata và checkpoint đã lưu được dùng theo cơ chế restart của Job và các thành phần Step.

Trong thực tế, không nhất thiết phải tự gọi lại JobLauncher để restart. Có thể dùng JobOperator hoặc công cụ vận hành được ứng dụng cung cấp. Dù dùng API nào, cần giữ đúng ý định: restart execution cũ với cùng định danh instance, thay vì tạo một bộ identifying parameters mới.

## 5. Cùng và khác tham số ảnh hưởng ra sao?

Giả sử Job có tên dailyOrderImport và chỉ dùng businessDate làm identifying parameter:

| Lần gọi | businessDate (identifying) | requestedBy (non-identifying) | Danh tính |
| --- | --- | --- | --- |
| A | 2026-11-15 | scheduler | Instance A |
| B | 2026-11-15 | operator | Vẫn là instance A |
| C | 2026-11-16 | scheduler | Instance mới |
| D | 2026-11-15 | scheduler, kèm startedAt mới nhưng non-identifying | Vẫn là instance A |

Các trường hợp trên cho thấy:

- Thay đổi identifying parameter tạo ra danh tính instance khác.
- Thay đổi non-identifying parameter không làm thay đổi danh tính.
- Giữ nguyên toàn bộ identifying parameters không đồng nghĩa lần gọi luôn được phép chạy. Kết quả còn phụ thuộc trạng thái hiện tại của JobInstance và khả năng restart của Job.

Ví dụ, nếu instance A đã COMPLETED, khởi chạy lại với cùng identifying parameters thường bị từ chối bằng JobInstanceAlreadyCompleteException. Nếu execution trước đang chạy, yêu cầu trùng thường bị từ chối bằng JobExecutionAlreadyRunningException. Nếu execution trước FAILED hoặc STOPPED và Job cho phép restart, Spring Batch có thể tạo JobExecution tiếp theo cho cùng instance.

Nếu thay đổi một identifying parameter để né JobInstanceAlreadyCompleteException, framework sẽ tạo một JobInstance mới. Điều đó có thể làm Job xử lý lại cùng dữ liệu mà không có checkpoint của instance cũ. Chỉ thực hiện việc này khi nghiệp vụ thực sự yêu cầu một lần xử lý logic mới và đã có chiến lược chống ghi trùng phù hợp.

## 6. Job name cũng tham gia xác định instance

JobParameters không phải yếu tố duy nhất quyết định danh tính. Job name cũng là một phần của định danh.

Ví dụ, hai lần khởi chạy có cùng businessDate và inputFileId nhưng dùng Job name khác nhau sẽ tạo hai JobInstance khác nhau:

~~~text
Job name: dailyOrderImport
businessDate: 2026-11-15
inputFileId: orders-2026-11-15
        |
        v
JobInstance A

Job name: dailyOrderReconciliation
businessDate: 2026-11-15
inputFileId: orders-2026-11-15
        |
        v
JobInstance B
~~~

Không nên tạo Job name động bằng cách nối timestamp, UUID, hostname hoặc tên người chạy nếu ý định là restart cùng một Job. Hãy giữ tên Job ổn định theo định nghĩa quy trình. Việc đổi tên Job có thể khiến repository xem đó là một định nghĩa khác và không tìm thấy instance cũ.

Khi đổi tên Job trong quá trình triển khai, cần xem xét lịch sử metadata và chiến lược restart của các execution cũ. Không nên đổi tên chỉ để chạy lại một instance đã hoàn tất.

## 7. Giá trị và kiểu dữ liệu phải được chuẩn hóa

Hai tham số nhìn giống nhau về mặt con người vẫn có thể không được xem là cùng một identifying parameter nếu kiểu hoặc giá trị lưu trữ khác nhau.

Ví dụ:

| Lần gọi | Tên tham số | Kiểu | Giá trị hiển thị |
| --- | --- | --- | --- |
| A | tenantId | Long | 42 |
| B | tenantId | String | "42" |

Kiểu dữ liệu là một phần của JobParameter. Không nên lúc truyền một mã dưới dạng số, lúc khác truyền dưới dạng chuỗi nếu hai lần chạy phải trỏ đến cùng instance.

Ngày và thời gian cũng cần định dạng nhất quán:

- Dùng một định dạng ngày chuẩn, chẳng hạn ISO-8601 cho ngày nghiệp vụ.
- Xác định rõ múi giờ nếu định danh dựa trên thời điểm.
- Chuẩn hóa chữ hoa/chữ thường nếu mã nghiệp vụ không phân biệt hoa thường.
- Tránh khi dùng đường dẫn tuyệt đối, khi dùng đường dẫn tương đối cho cùng một file.
- Dùng ID file bất biến hoặc version thay vì chỉ dựa vào tên file có thể bị thay thế.

Spring Batch không tự đọc nội dung file để xác định danh tính JobInstance. Nếu file tại cùng một đường dẫn bị thay nội dung, nhưng JobParameters không đổi, repository vẫn nhận diện cùng instance. Nếu nội dung thay đổi có nghĩa là một lần nhập mới, hãy truyền file ID, revision hoặc checksum phù hợp với quy trình nghiệp vụ.

## 8. RunIdIncrementer và startNextInstance

RunIdIncrementer được dùng khi ứng dụng chủ động muốn tạo một JobInstance mới cho lần chạy kế tiếp. Incrementer thường tăng tham số identifying run.id dựa trên bộ tham số trước đó.

Ví dụ cấu hình Job:

~~~java
@Bean
public Job dailyOrderImport(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("dailyOrderImport", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(importOrdersStep)
            .build();
}
~~~

Khi dùng JobOperator.startNextInstance với Job đã cấu hình incrementer, Spring Batch yêu cầu incrementer tạo bộ JobParameters cho instance kế tiếp. Giá trị run.id mới làm thay đổi danh tính instance.

Điều này phù hợp khi nghiệp vụ muốn mỗi lần chạy kế tiếp là một lần xử lý logic mới. Tuy nhiên, nó không phải cơ chế restart execution đã thất bại. Nếu dùng startNextInstance để thay cho restart, ứng dụng có thể tạo instance mới và bỏ qua checkpoint của instance cũ.

Phân biệt hai ý định:

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Tiếp tục JobInstance đang FAILED hoặc STOPPED | Restart execution cũ với cùng identifying parameters, qua JobOperator.restart hoặc luồng restart tương ứng |
| Chạy một phạm vi nghiệp vụ mới | Tạo identifying parameters mới phản ánh phạm vi mới |
| Chủ động chạy instance kế tiếp theo số thứ tự | Dùng incrementer và startNextInstance khi đó là quy tắc nghiệp vụ |
| Chỉ ghi nhận ai yêu cầu hoặc thời điểm yêu cầu | Dùng non-identifying parameters hoặc audit/log |

JobLauncher.run(job, parameters) sử dụng bộ tham số mà ứng dụng truyền vào. Không nên giả định rằng việc cấu hình RunIdIncrementer sẽ tự tăng run.id mỗi khi gọi JobLauncher.run. Incrementer được sử dụng trong các luồng yêu cầu instance kế tiếp có áp dụng incrementer, chẳng hạn startNextInstance.

## 9. Khi nào nên tạo instance mới một cách có chủ đích?

Có những trường hợp nghiệp vụ thực sự cần chạy lại cùng một loại Job trên cùng một ngày hoặc cùng một tập dữ liệu. Ví dụ:

- File đầu vào được sửa và phát hành thành một revision mới.
- Dữ liệu của tenant được yêu cầu tái xử lý sau khi quy tắc chuyển đổi thay đổi.
- Người vận hành yêu cầu một lần đối soát lại độc lập sau khi xử lý sự cố.
- Một kỳ dữ liệu có nhiều phiên bản được phê duyệt và cần lưu lịch sử riêng.

Trong các trường hợp đó, hãy bổ sung một identifying parameter mang ý nghĩa nghiệp vụ, chẳng hạn dataRevision hoặc reprocessVersion:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-2026-11-15", true)
        .addLong("reprocessVersion", 2L, true)
        .addString("requestedBy", "operations", false)
        .toJobParameters();
~~~

Giá trị reprocessVersion phải được quản lý có chủ đích, có thể tra cứu và giải thích được. Tránh tạo UUID ngẫu nhiên chỉ để né trạng thái COMPLETED. Mỗi instance mới có thể thực hiện lại side effect như ghi dữ liệu, gửi thông điệp hoặc gọi API; do đó writer và service nghiệp vụ cần có chính sách idempotency, khóa nghiệp vụ hoặc cơ chế đối soát.

Nếu mục tiêu chỉ là khôi phục một lần chạy lỗi, không tạo revision mới. Hãy restart instance cũ để tận dụng trạng thái và checkpoint đã lưu.

## 10. JobParametersValidator không quyết định danh tính instance

JobParametersValidator kiểm tra tham số có hợp lệ trước khi Job chạy hay không. Ví dụ, validator có thể yêu cầu businessDate và inputFileId phải có mặt, hoặc kiểm tra định dạng ngày.

Validator không quyết định tham số nào là identifying. Cờ identifying nằm trên từng JobParameter và được JobRepository dùng để nhận diện JobInstance.

Ví dụ kiểm tra tham số bắt buộc:

~~~java
public class OrderImportParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String businessDate = parameters.getString("businessDate");
        String inputFileId = parameters.getString("inputFileId");

        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        if (inputFileId == null || inputFileId.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFileId is required");
        }
    }
}
~~~

Có thể gắn validator vào Job:

~~~java
return new JobBuilder("dailyOrderImport", jobRepository)
        .validator(new OrderImportParametersValidator())
        .start(importOrdersStep)
        .build();
~~~

Validation giúp phát hiện tham số thiếu hoặc sai định dạng sớm. Việc đánh dấu identifying vẫn phải được thiết kế ở nơi tạo JobParameters. Hai trách nhiệm này bổ sung cho nhau nhưng không thay thế nhau.

## 11. Kiểm tra nguyên nhân khi xuất hiện JobInstance ngoài ý muốn

Khi thấy nhiều JobInstance cho cùng một phạm vi nghiệp vụ, hãy lần theo dữ liệu thực tế đã truyền vào JobLauncher hoặc JobOperator.

### Ghi nhận danh tính trước khi launch

Ở lớp điều phối, có thể ghi log tên Job cùng các identifying parameters đã chọn:

~~~java
log.info(
        "Launching job={}, businessDate={}, inputFileId={}, tenantId={}",
        job.getName(),
        parameters.getString("businessDate"),
        parameters.getString("inputFileId"),
        parameters.getLong("tenantId")
);

JobExecution execution = jobLauncher.run(job, parameters);
~~~

Không ghi password, access token hoặc dữ liệu nhạy cảm vào log. Chỉ ghi các giá trị định danh cần thiết để giải thích vì sao repository chọn instance đó.

### Đối chiếu metadata

JobExplorer có thể được dùng để tra cứu các JobInstance theo tên Job và xem các JobExecution thuộc từng instance. Ví dụ:

~~~java
List<JobInstance> instances =
        jobExplorer.getJobInstances("dailyOrderImport", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions =
            jobExplorer.getJobExecutions(instance);

    log.info(
            "instanceId={}, jobName={}, executionCount={}",
            instance.getInstanceId(),
            instance.getJobName(),
            executions.size()
    );
}
~~~

Khi điều tra, hãy so sánh Job name, tên tham số, giá trị và kiểu identifying giữa các execution. Có thể dùng truy vấn SQL metadata để hỗ trợ điều tra, nhưng nên ưu tiên JobExplorer trong code ứng dụng để tránh phụ thuộc trực tiếp vào cấu trúc bảng nội bộ.

Một JobInstance có nhiều JobExecution thường cho thấy đã có các lần thực thi hoặc restart trên cùng phạm vi. Nhiều JobInstance cho cùng ngày nghiệp vụ có thể xuất phát từ timestamp identifying, UUID, run.id, Job name động hoặc một giá trị định danh khác thay đổi.

## 12. Những lỗi thường gặp

### Thêm timestamp vào identifying parameters

Mỗi lần gọi có timestamp mới sẽ tạo instance mới. Nếu timestamp chỉ để audit, hãy đánh dấu non-identifying hoặc ghi vào log.

### Tạo UUID mới cho mọi lần launch

UUID ngẫu nhiên ở dạng identifying khiến mỗi lần gọi có danh tính khác, làm mất ý nghĩa restart. Chỉ dùng một ID identifying khi nó đại diện cho một yêu cầu nghiệp vụ độc lập và cần được xử lý như một instance riêng.

### Dùng RunIdIncrementer cho luồng restart

Incrementer được thiết kế để yêu cầu instance kế tiếp. Khi cần restart instance đã thất bại, hãy dùng luồng restart với identifying parameters ban đầu.

### Nghĩ rằng đổi requestedBy sẽ tạo instance mới

Nếu requestedBy là non-identifying, thay đổi giá trị không tạo instance mới. Nếu thay đổi người yêu cầu đồng nghĩa một quy trình nghiệp vụ mới, cần xác định lại ý nghĩa tham số và mô hình danh tính.

### Dùng tham số mặc định không ổn định

Một lớp launch có thể tự thêm thời gian, số thứ tự hoặc giá trị ngẫu nhiên mà người gọi không nhận ra. Hãy tập trung việc tạo JobParameters vào một nơi có quy ước rõ ràng và log các giá trị identifying trước khi launch.

### Thay đổi định dạng hoặc kiểu dữ liệu

Một lần gọi dùng tenantId dạng Long, lần khác dùng String; hoặc ngày có định dạng khác nhau có thể tạo danh tính khác. Chuẩn hóa kiểu và biểu diễn giá trị ở ranh giới khởi chạy.

### Dùng Job name động

Tên Job thay đổi theo ngày, hostname hoặc người chạy sẽ làm thay đổi danh tính instance. Giữ Job name ổn định và đặt thông tin biến đổi vào JobParameters với cờ phù hợp.

### Xóa metadata để chạy lại

Xóa trực tiếp các hàng BATCH_JOB_INSTANCE hoặc BATCH_JOB_EXECUTION có thể phá vỡ quan hệ khóa ngoại, checkpoint và lịch sử vận hành. Hãy dùng API restart hoặc quy trình reprocessing có kiểm soát thay vì sửa metadata thủ công.

## 13. Quy trình thiết kế JobParameters an toàn

Khi xây dựng luồng khởi chạy Job, hãy xác định danh tính instance trước khi viết code:

1. **Xác định phạm vi nghiệp vụ:** một instance đại diện cho ngày, file, tenant, kỳ dữ liệu hay revision nào?
2. **Chọn identifying parameters:** chỉ đưa vào đây những giá trị làm thay đổi phạm vi xử lý.
3. **Đánh dấu rõ ràng:** dùng overload có boolean để khai báo identifying true hoặc false.
4. **Chuẩn hóa kiểu và giá trị:** thống nhất định dạng ngày, kiểu ID, chữ hoa/chữ thường và cách biểu diễn file.
5. **Tách dữ liệu vận hành:** requestedBy, requestId và requestedAt thường là non-identifying nếu không làm thay đổi nghiệp vụ.
6. **Tạo tham số ở một nơi:** tránh nhiều lớp tự thêm timestamp hoặc UUID vào bộ tham số.
7. **Giữ bộ tham số khi restart:** lưu hoặc tái tạo chính xác các identifying values của lần chạy ban đầu.
8. **Chỉ tạo instance mới có chủ đích:** dùng business revision hoặc khóa nghiệp vụ mới khi thực sự cần một lần xử lý riêng.
9. **Bảo vệ side effect:** thiết kế writer và service có tính idempotent để việc reprocessing không tạo dữ liệu trùng.
10. **Theo dõi metadata:** dùng JobExplorer và log để giải thích danh tính và lịch sử execution.

## Kết luận

Tránh tạo JobInstance mới ngoài ý muốn bằng cách kiểm soát Job name và các identifying JobParameters. Dùng khóa nghiệp vụ ổn định để xác định phạm vi xử lý, đánh dấu timestamp và UUID là non-identifying khi chúng chỉ phục vụ audit, chuẩn hóa kiểu dữ liệu và giữ nguyên identifying parameters khi restart. Chỉ tạo instance mới khi có một yêu cầu nghiệp vụ mới được xác định rõ, đồng thời bảo vệ dữ liệu khỏi side effect trùng lặp.
