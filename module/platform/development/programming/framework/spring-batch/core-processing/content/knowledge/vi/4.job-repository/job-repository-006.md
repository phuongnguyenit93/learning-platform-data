# JobRepository trong môi trường single instance

Trong Spring Batch, `JobRepository` là thành phần quản lý metadata của các lần chạy batch. Nó lưu thông tin về JobInstance, JobExecution, StepExecution và ExecutionContext để framework biết một Job đã được khởi chạy khi nào, đang ở trạng thái nào, đã hoàn thành Step nào và có thể tiếp tục từ đâu sau khi gặp lỗi.

Trong môi trường **single instance** (ứng dụng chỉ chạy trên một instance hoặc một node), `JobRepository` vẫn giữ vai trò quan trọng. Việc chỉ có một tiến trình ứng dụng giúp kiến trúc triển khai đơn giản hơn, nhưng không làm mất nhu cầu lưu trạng thái bền vững, kiểm soát các lần khởi chạy trùng và hỗ trợ restart sau sự cố. Một ứng dụng đơn instance vẫn có thể chạy nhiều Job đồng thời, nhận nhiều yêu cầu khởi chạy hoặc bị dừng giữa chừng.

## 1. JobRepository làm nhiệm vụ gì?

`JobRepository` là nơi Spring Batch lưu và truy xuất metadata trong suốt vòng đời của Job. Khi một Job được khởi chạy, framework dùng repository để tạo hoặc tra cứu JobInstance, tạo JobExecution và ghi nhận các StepExecution. Trong quá trình chạy, trạng thái, bộ đếm và ExecutionContext tiếp tục được cập nhật.

Các loại thông tin chính gồm:

- **JobInstance:** định danh một lần chạy logic của Job, dựa trên tên Job và các identifying JobParameters.
- **JobExecution:** một lần thực thi cụ thể của JobInstance, gồm trạng thái như STARTED, COMPLETED, FAILED hoặc STOPPED, cùng thời điểm bắt đầu và kết thúc.
- **StepExecution:** thông tin thực thi của từng Step, bao gồm trạng thái, read count, write count, skip count, commit count và rollback count.
- **ExecutionContext:** dữ liệu trạng thái cần duy trì giữa các lần thực thi, thường dùng để lưu checkpoint giúp restart.
- **JobParameters:** các tham số đầu vào được lưu cùng execution; các tham số identifying tham gia xác định JobInstance.

Ví dụ, Job `dailySettlementJob` chạy cho ngày nghiệp vụ `2026-11-15`. Repository lưu JobInstance của ngày đó và từng JobExecution. Nếu lần chạy đầu tiên thất bại, lần restart có thể tạo JobExecution mới cho cùng JobInstance và tiếp tục dựa trên metadata, thay vì coi đó là một công việc hoàn toàn mới.

`JobRepository` không phải là repository chứa dữ liệu nghiệp vụ như khách hàng, đơn hàng hoặc giao dịch. Nó lưu metadata để điều phối và theo dõi xử lý batch. Dữ liệu nghiệp vụ vẫn được đọc và ghi qua các reader, writer, DAO hoặc service của ứng dụng.

## 2. Single instance không có nghĩa là không cần JobRepository

Giả sử một ứng dụng Spring Boot duy nhất chạy trên một máy chủ. Một scheduler khởi chạy Job vào nửa đêm, sau đó máy chủ mất điện khi Job mới xử lý được một phần dữ liệu.

Nếu metadata chỉ nằm trong bộ nhớ của tiến trình, khi ứng dụng khởi động lại, trạng thái của lần chạy trước có thể biến mất. Framework không còn biết Job đã tạo execution nào, Step nào đã hoàn thành và reader đã lưu checkpoint ở đâu. Một lần chạy mới có thể xử lý lại dữ liệu từ đầu và tạo tác dụng phụ trùng lặp.

Với `JobRepository` lưu metadata vào cơ sở dữ liệu bền vững, ứng dụng có thể đọc lại trạng thái sau khi khởi động. Nếu Job, Step và các thành phần đọc/ghi hỗ trợ restart, người vận hành có thể tiếp tục JobInstance đã thất bại từ trạng thái được lưu.

Single instance chỉ có nghĩa ứng dụng hiện được triển khai trên một node. Nó không đồng nghĩa với:

- Chỉ có một Job trong toàn hệ thống.
- Mỗi Job chỉ chạy một lần trong suốt vòng đời ứng dụng.
- Không có hai yêu cầu khởi chạy đến gần như cùng lúc.
- Tiến trình không bao giờ bị dừng đột ngột.
- Metadata trong bộ nhớ có thể thay thế lịch sử thực thi bền vững.

Vì vậy, trong một môi trường production single instance, lựa chọn thông thường vẫn là một `JobRepository` dùng cơ sở dữ liệu quan hệ và được cấu hình với transaction manager phù hợp.

## 3. JobRepository được tổ chức như thế nào?

Với cấu hình JDBC, Spring Batch lưu metadata trong các bảng có tiền tố mặc định `BATCH_`. Tùy phiên bản và database, schema cụ thể có thể khác đôi chút, nhưng các bảng thường gặp gồm:

| Bảng metadata | Nội dung chính |
|---|---|
| `BATCH_JOB_INSTANCE` | Các JobInstance và định danh của chúng |
| `BATCH_JOB_EXECUTION` | Mỗi lần thực thi Job, trạng thái và thời gian chạy |
| `BATCH_JOB_EXECUTION_PARAMS` | JobParameters của lần thực thi |
| `BATCH_STEP_EXECUTION` | Trạng thái và bộ đếm của từng StepExecution |
| `BATCH_JOB_EXECUTION_CONTEXT` | ExecutionContext ở cấp JobExecution |
| `BATCH_STEP_EXECUTION_CONTEXT` | ExecutionContext ở cấp StepExecution |

Quan hệ giữa các bản ghi có thể hình dung như sau:

```text
JOB_INSTANCE
     |
     | một JobInstance có thể có nhiều lần thực thi
     v
JOB_EXECUTION
     |
     +--------------------+
     |                    |
     v                    v
STEP_EXECUTION       JOB_EXECUTION_CONTEXT
     |
     v
STEP_EXECUTION_CONTEXT
```

Một JobInstance có thể có nhiều JobExecution qua các lần restart. Một JobExecution có thể chứa nhiều StepExecution. ExecutionContext được lưu riêng theo phạm vi Job hoặc Step để framework khôi phục trạng thái thích hợp.

Các bảng này là cấu trúc nội bộ của Spring Batch. Ứng dụng nên truy vấn metadata thông qua API như `JobExplorer` hoặc các công cụ giám sát phù hợp, thay vì tự cập nhật trực tiếp các hàng metadata trong khi Job đang chạy.

## 4. Cấu hình JobRepository trong ứng dụng single instance

### Sử dụng cấu hình tự động của Spring Boot

Với ứng dụng Spring Boot có DataSource được cấu hình, Spring Boot có thể tự cấu hình hạ tầng Spring Batch và `JobRepository`. Trong trường hợp thông thường, chỉ cần cung cấp datasource, transaction manager và định nghĩa Job/Step; không cần tự tạo một repository khác.

Ví dụ cấu hình datasource và schema trong `application.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batch_app
    username: batch_user
    password: ${BATCH_DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
  batch:
    jdbc:
      initialize-schema: never
```

Ở môi trường production, `initialize-schema: never` phù hợp khi schema Spring Batch được quản lý bằng công cụ migration như Flyway hoặc Liquibase. Trong môi trường phát triển hoặc thử nghiệm, có thể cấu hình Spring Boot khởi tạo schema tự động nếu database và phiên bản Spring Batch hỗ trợ.

Ví dụ định nghĩa Job và Step sử dụng `JobRepository` được inject:

```java
@Bean
Job dailySettlementJob(JobRepository jobRepository, Step settlementStep) {
    return new JobBuilder("dailySettlementJob", jobRepository)
            .start(settlementStep)
            .build();
}

@Bean
Step settlementStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<SettlementInput> reader,
        ItemProcessor<SettlementInput, Settlement> processor,
        ItemWriter<Settlement> writer) {

    return new StepBuilder("settlementStep", jobRepository)
            .<SettlementInput, Settlement>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

JobBuilder và StepBuilder nhận `JobRepository` để lưu metadata của Job và Step. Với chunk size 200, Spring Batch xử lý một nhóm item trong một transaction chunk theo cấu hình transaction manager được cung cấp.

Không nên thêm `@EnableBatchProcessing` một cách máy móc vào ứng dụng Spring Boot đang dùng auto-configuration. Tùy phiên bản Spring Boot, annotation này có thể làm ứng dụng chuyển sang tự chịu trách nhiệm cấu hình hạ tầng Batch và ảnh hưởng đến các cơ chế tự động khác. Hãy chọn một cách cấu hình nhất quán theo phiên bản và cấu trúc ứng dụng.

### Khi cần cấu hình hạ tầng thủ công

Trong ứng dụng Spring không dùng auto-configuration, cần cấu hình `JobRepository` dựa trên DataSource và transaction manager. Có thể sử dụng cơ chế cấu hình hạ tầng Spring Batch hoặc `JobRepositoryFactoryBean`, tùy phiên bản framework.

Các điểm cần xác định rõ:

- DataSource dùng để lưu metadata và có thể được tách khỏi DataSource nghiệp vụ.
- Transaction manager mà repository sử dụng để quản lý các thao tác metadata.
- Database type và schema metadata tương ứng.
- Mức cô lập transaction cho thao tác tạo execution.
- Cách khởi tạo và nâng cấp schema khi triển khai phiên bản mới.

Nếu metadata và dữ liệu nghiệp vụ cùng nằm trong một database, có thể dùng chung DataSource nhưng cần hiểu rõ ranh giới transaction. Nếu dùng nhiều DataSource hoặc transaction manager, phải cấu hình sao cho thao tác metadata và xử lý dữ liệu nghiệp vụ có hành vi nhất quán theo yêu cầu của Job.

## 5. Kiểm soát các lần khởi chạy trong một instance

Một node ứng dụng vẫn có thể nhận nhiều yêu cầu khởi chạy Job gần như đồng thời. Ví dụ:

- Scheduler bắt đầu Job lúc 00:00.
- Người vận hành nhấn nút chạy thủ công đúng thời điểm đó.
- Một API khác cũng gửi lệnh khởi chạy cùng Job.
- Một lần retry từ hệ thống điều phối đến trong lúc execution trước chưa kết thúc.

`JobRepository` giúp Spring Batch kiểm tra JobInstance và các execution hiện có. JobInstance được xác định bởi tên Job và các identifying JobParameters. Nếu hai yêu cầu cùng khởi chạy một Job với cùng bộ identifying parameters, repository và các ràng buộc metadata giúp ngăn việc tạo hai JobInstance trùng định danh.

Kết quả phụ thuộc vào trạng thái hiện tại. Caller có thể gặp các tình huống như:

- `JobExecutionAlreadyRunningException` nếu JobInstance đã có execution đang chạy.
- `JobInstanceAlreadyCompleteException` nếu JobInstance đã hoàn tất.
- `JobRestartException` nếu instance không thể restart theo trạng thái hoặc cấu hình hiện tại.
- `JobParametersInvalidException` nếu tham số đầu vào không hợp lệ.

Ví dụ, ngày nghiệp vụ là identifying parameter:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.now(), true)
        .toJobParameters();

jobLauncher.run(dailySettlementJob, parameters);
```

Hai lần gọi trong cùng ngày sẽ nhắm đến cùng JobInstance nếu tên Job và các identifying parameters giống nhau. Nếu lần đầu đang chạy, lần gọi thứ hai không nên tạo thêm một lần xử lý độc lập cho cùng instance. Nếu lần đầu đã thất bại, cùng tham số có thể được dùng để restart theo quy tắc của Spring Batch.

Nếu mỗi lần gọi đều thêm một timestamp hoặc UUID identifying mới, Spring Batch sẽ coi đó là các JobInstance khác nhau. Điều này có thể phù hợp khi nghiệp vụ cho phép nhiều lần chạy độc lập, nhưng không phải cách chống chạy trùng cho một kỳ nghiệp vụ.

## 6. Transaction và tính nhất quán của metadata

`JobRepository` sử dụng transaction để ghi metadata. Các thao tác tạo JobExecution và StepExecution cần được bảo vệ để các lần khởi chạy đồng thời không tạo ra trạng thái metadata mâu thuẫn.

Với JDBC repository, Spring Batch cấu hình mức cô lập cho một số thao tác tạo execution; mức mặc định cho thao tác tạo thường là `SERIALIZABLE`. Cơ chế cụ thể còn phụ thuộc database, transaction manager và cấu hình repository. Các ràng buộc khóa chính/duy nhất trong schema metadata cũng là lớp bảo vệ quan trọng.

Trong môi trường single instance, không cần triển khai một hệ thống điều phối phân tán chỉ để bảo vệ metadata giữa nhiều node, vì hiện tại chỉ có một node ứng dụng. Tuy nhiên, vẫn cần giữ transaction và schema repository đúng chuẩn để xử lý các lần khởi chạy đồng thời trong cùng tiến trình và bảo vệ trạng thái qua sự cố.

Đối với chunk-oriented processing, transaction của chunk thường bao gồm các thao tác đọc/ghi theo cấu hình và cập nhật checkpoint. Khi chunk commit, tiến độ tương ứng được lưu. Nếu transaction rollback, các thay đổi thuộc transaction đó được hoàn tác; những chunk đã commit trước đó vẫn được giữ lại.

Không nên hiểu điều này là mọi tác dụng phụ đều được rollback cùng metadata. Gọi API bên ngoài, gửi email, ghi file hoặc publish message có thể xảy ra ngoài transaction database. Nếu tiến trình dừng sau khi tác dụng phụ đã xảy ra nhưng trước khi metadata được commit, khi restart thao tác đó có thể bị thực hiện lại. Vì vậy, Job vẫn cần idempotency key, unique constraint, transactional outbox hoặc cơ chế đối soát phù hợp.

## 7. Theo dõi JobRepository bằng JobExplorer

`JobRepository` phục vụ ghi và quản lý metadata trong quá trình thực thi. Để đọc thông tin execution phục vụ màn hình quản trị hoặc giám sát, Spring Batch cung cấp `JobExplorer`.

Ví dụ, có thể truy vấn các lần thực thi của một JobInstance:

```java
@Service
public class BatchStatusService {

    private final JobExplorer jobExplorer;

    public BatchStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public List<JobExecution> executionsFor(
            String jobName, JobParameters parameters) {

        JobInstance instance = jobExplorer.getJobInstance(
                jobName, parameters);

        if (instance == null) {
            return List.of();
        }

        return jobExplorer.getJobExecutions(instance);
    }
}
```

Đoạn mã minh họa việc đọc metadata; tùy API cụ thể của phiên bản Spring Batch, cách tạo JobParameters và truy vấn có thể cần điều chỉnh theo overload đang được cung cấp. Khi xây dựng endpoint quản trị, chỉ nên cho phép người có quyền xem trạng thái và tránh để client sửa trực tiếp metadata.

Các thông tin thường cần hiển thị gồm:

- Tên Job, JobInstance ID và JobExecution ID.
- Identifying parameters của lần chạy.
- Trạng thái hiện tại và thời điểm bắt đầu/kết thúc.
- Danh sách StepExecution cùng trạng thái từng Step.
- Read count, write count, filter count và skip count.
- Thông tin lỗi để hỗ trợ điều tra.

Với single instance, màn hình theo dõi có thể chạy ngay trong ứng dụng đó. Tuy nhiên, metadata vẫn nên được lưu ở database để lịch sử còn tồn tại sau khi tiến trình ứng dụng khởi động lại.

## 8. Vận hành schema và dữ liệu metadata

Schema Spring Batch là một phần của hạ tầng ứng dụng. Khi triển khai, cần bảo đảm schema tương ứng với phiên bản Spring Batch đang dùng và được cập nhật có kiểm soát.

Một số nguyên tắc thực tế:

1. **Khởi tạo schema một lần có kiểm soát:** môi trường phát triển có thể dùng script schema đi kèm Spring Batch; production nên dùng migration đã được kiểm soát.
2. **Không xóa metadata đang được sử dụng:** xóa bảng hoặc hàng metadata có thể làm mất trạng thái JobExecution và checkpoint cần cho restart.
3. **Có chính sách lưu trữ:** metadata có thể tăng theo số lần chạy. Xác định thời hạn giữ lịch sử, cách archive và thời điểm dọn dẹp sau khi Job đã kết thúc và không còn cần restart.
4. **Sao lưu database metadata:** nếu khả năng restart và lịch sử chạy quan trọng, cần đưa metadata vào kế hoạch backup/restore.
5. **Kiểm tra quyền database:** tài khoản ứng dụng cần quyền phù hợp để đọc, ghi và cập nhật các bảng metadata.
6. **Theo dõi dung lượng và hiệu năng:** số lượng execution, context lớn và tần suất cập nhật có thể làm tăng dung lượng hoặc ảnh hưởng truy vấn.

Không nên tự ý chỉnh sửa trạng thái trong `BATCH_JOB_EXECUTION` hoặc `BATCH_STEP_EXECUTION` bằng SQL để ép một Job chạy lại. Nếu metadata không nhất quán, hãy dùng quy trình vận hành đã được kiểm chứng, đối chiếu dữ liệu nghiệp vụ và bảo toàn lịch sử cần thiết.

## 9. Giới hạn và lưu ý riêng của single instance

Mô hình một node giúp triển khai đơn giản nhưng có một số giới hạn vận hành:

- Nếu node ngừng hoạt động, không có node khác tự tiếp quản Job đang chạy. Cần khởi động lại ứng dụng và xử lý execution dở dang theo quy trình restart.
- Nhiều Job trong cùng JVM có thể tranh chấp CPU, bộ nhớ, connection pool và tài nguyên database.
- Một scheduler có thể kích hoạt Job mới khi lần trước vẫn đang chạy, nhất là khi thời gian xử lý thay đổi.
- Nếu ứng dụng dùng bộ nhớ làm nơi lưu trạng thái, restart tiến trình có thể làm mất lịch sử và checkpoint.
- Một lỗi hoặc bảo trì trên node có thể ảnh hưởng đồng thời cả API trực tuyến và batch job nếu chúng cùng chạy trong ứng dụng.

Để giảm rủi ro, hãy kiểm soát lịch chạy và mức song song, đặt timeout hợp lý cho các phụ thuộc, giới hạn kích thước chunk theo tải thực tế và giám sát trạng thái JobExecution. Nếu một Job không được phép chồng lấn với chính nó, có thể dùng identifying parameters ổn định theo kỳ nghiệp vụ kết hợp kiểm tra trạng thái execution trước khi cho phép chạy.

Khi hệ thống phát triển sang nhiều instance, cùng một JobRepository bền vững dùng chung giữa các node sẽ trở nên quan trọng hơn để các node nhìn thấy cùng metadata. Tuy nhiên, mở rộng sang nhiều node còn cần đánh giá scheduler, phân phối công việc, transaction, tài nguyên dùng chung và hành vi idempotent. Chỉ có một JobRepository không tự giải quyết toàn bộ bài toán điều phối phân tán.

## 10. Checklist thiết kế cho ứng dụng single instance

Trước khi đưa Job vào production, hãy xác nhận:

- `JobRepository` dùng metadata store bền vững, thường là database.
- Schema Spring Batch được khởi tạo và nâng cấp theo đúng phiên bản.
- JobParameters identifying phản ánh đúng một lần chạy nghiệp vụ.
- Job có thể restart nếu yêu cầu nghiệp vụ cần khôi phục sau lỗi.
- Reader lưu checkpoint phù hợp và dữ liệu đầu vào ổn định giữa các lần chạy.
- Writer và các tác dụng phụ bên ngoài an toàn khi retry hoặc chạy lại.
- Scheduler và API không vô tình tạo các execution chồng lấn ngoài ý muốn.
- JobExplorer hoặc cơ chế giám sát tương đương có thể cung cấp trạng thái và bộ đếm cần thiết.
- Metadata được backup và có chính sách lưu trữ/dọn dẹp rõ ràng.

## Kết luận

Trong môi trường single instance, `JobRepository` vẫn là trung tâm lưu metadata và quản lý vòng đời thực thi của Spring Batch. Một node duy nhất giúp giảm độ phức tạp triển khai, nhưng không loại bỏ nhu cầu về persistence, transaction, kiểm soát khởi chạy đồng thời và restart sau sự cố. Với ứng dụng production, nên dùng JDBC JobRepository lưu metadata trong database, quản lý schema theo phiên bản, xác định JobParameters rõ ràng và thiết kế reader/writer an toàn khi chạy lại. `JobExplorer` giúp đọc metadata để giám sát, còn dữ liệu nghiệp vụ vẫn được quản lý qua các thành phần truy cập dữ liệu riêng của ứng dụng.
