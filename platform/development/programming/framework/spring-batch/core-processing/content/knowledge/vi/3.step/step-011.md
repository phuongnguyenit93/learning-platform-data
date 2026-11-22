# Giới hạn của việc nhồi quá nhiều logic vào một step

Trong Spring Batch, `Step` là một giai đoạn thực thi của `Job`. Một step có thể chứa nhiều thao tác nhỏ, nhưng điều đó không có nghĩa mọi công việc của một quy trình nên được đặt chung vào một step. Khi một step vừa đọc file, kiểm tra dữ liệu, cập nhật nhiều nhóm bảng, gọi dịch vụ bên ngoài, tạo báo cáo và gửi thông báo, nó dần trở thành một khối xử lý khó hiểu và khó vận hành.

Nhồi quá nhiều logic vào một step làm mờ ranh giới trách nhiệm, khiến việc kiểm soát giao dịch, restart, retry, theo dõi lỗi và kiểm thử trở nên khó khăn. Ngược lại, tách mọi thao tác nhỏ thành một step riêng cũng tạo ra nhiều metadata và làm flow phức tạp. Thiết kế tốt là chia job theo các giai đoạn nghiệp vụ có ranh giới rõ ràng, đồng thời giữ các thao tác có cùng mục đích và cùng cách phục hồi trong một step.

## 1. Vì sao một step không nên trở thành một quy trình thu nhỏ?

Một step có thể được triển khai bằng chunk processing hoặc tasklet. Trong chunk processing, step thường phối hợp `ItemReader`, `ItemProcessor` và `ItemWriter` để xử lý dữ liệu theo nhóm. Trong tasklet, ứng dụng tự định nghĩa một tác vụ qua phương thức `execute`.

Hai kiểu step này đều có thể chứa nhiều dòng code. Vấn đề xuất hiện khi step đảm nhiệm nhiều giai đoạn nghiệp vụ khác nhau, ví dụ:

1. Đọc file đầu vào và kiểm tra cấu trúc.
2. Chuẩn hóa và xác thực từng bản ghi.
3. Ghi dữ liệu khách hàng vào cơ sở dữ liệu.
4. Cập nhật số dư hoặc trạng thái giao dịch.
5. Gọi API của hệ thống khác.
6. Tạo file tổng hợp và gửi email thông báo.

Nếu tất cả nằm trong một tasklet lớn hoặc được điều khiển bởi một processor/writer quá phức tạp, framework chỉ nhìn thấy một step với trạng thái chung. Người vận hành khó biết giai đoạn nào đã hoàn thành, giai đoạn nào thất bại và cần khôi phục từ đâu.

```text
Một step ôm toàn bộ quy trình

Job
 |
 +-- processEverythingStep
       +-- đọc file
       +-- kiểm tra dữ liệu
       +-- ghi khách hàng
       +-- cập nhật giao dịch
       +-- gọi API ngoài
       +-- tạo báo cáo
       +-- gửi email
```

Đặt nhiều logic vào một step không tự động làm ứng dụng sai. Một step vẫn có thể là lựa chọn phù hợp nếu các thao tác tạo thành một đơn vị xử lý thống nhất, có cùng ranh giới giao dịch và cùng cách restart. Tuy nhiên, khi các thao tác có vòng đời hoặc yêu cầu vận hành khác nhau, việc gom chúng lại sẽ tạo ra những giới hạn rõ rệt.

## 2. Khó xác định chính xác vị trí xảy ra lỗi

Spring Batch lưu trạng thái thực thi ở cấp job và step. Với chunk-oriented step, framework còn ghi nhận các số liệu như số item đọc, ghi, filter hoặc skip. Nếu một step chứa nhiều giai đoạn không được mô hình hóa thành các step riêng, trạng thái `FAILED` chỉ cho biết step tổng thể thất bại.

Ví dụ một step thực hiện tuần tự việc nhập dữ liệu, cập nhật bảng tổng hợp và xuất báo cáo. Nếu lỗi xảy ra trong lúc xuất báo cáo, step có thể thất bại dù phần nhập dữ liệu và cập nhật tổng hợp đã hoàn thành. Người vận hành phải đọc log hoặc tự kiểm tra dữ liệu để biết những công việc nào đã xảy ra.

Khi chia thành các step có ý nghĩa, trạng thái trở nên rõ ràng hơn:

```text
validateInputStep   -> COMPLETED
importCustomerStep  -> COMPLETED
updateBalanceStep   -> COMPLETED
exportReportStep    -> FAILED
notifyResultStep    -> chưa chạy
```

Nhìn vào metadata, có thể xác định giai đoạn thất bại và những giai đoạn chưa bắt đầu. Điều này giúp việc giám sát, phân tích nguyên nhân và xử lý sự cố dễ dàng hơn.

## 3. Khó restart đúng phần công việc cần tiếp tục

Restart trong Spring Batch dựa trên `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`. Khi một job được restart, step đã hoàn tất thường được bỏ qua; step thất bại hoặc chưa hoàn tất được thực thi theo quy tắc restart của step.

Nếu nhiều giai đoạn độc lập nằm trong cùng một step, Spring Batch không có trạng thái hoàn tất riêng cho từng giai đoạn bên trong đó. Khi step thất bại, phần logic của step có thể được gọi lại. Ứng dụng phải tự biết phần nào đã thực hiện và bảo đảm việc thực hiện lại không tạo tác dụng phụ trùng lặp.

Ví dụ:

```text
Một step duy nhất:
  1. ghi 10.000 khách hàng thành công
  2. cập nhật bảng thống kê thành công
  3. gọi API đối tác bị timeout
  4. step kết thúc FAILED

Restart:
  step chạy lại
  -> có nguy cơ ghi lại khách hàng
  -> có nguy cơ cập nhật thống kê lần nữa
  -> gọi lại API đối tác
```

Nếu tách thành các step phù hợp, các bước đã `COMPLETED` thường được bỏ qua khi restart cùng JobInstance. Step gọi API có thể được thực thi lại theo trạng thái của chính nó. Điều này tạo ra một ranh giới phục hồi dễ hiểu hơn.

Tách step không tự động bảo đảm dữ liệu không bị trùng. Một thao tác có thể đã tạo tác dụng phụ bên ngoài trước khi step ghi nhận hoàn tất hoặc trước khi metadata được commit. Vì vậy, writer và tích hợp bên ngoài vẫn cần idempotency, khóa nghiệp vụ hoặc cơ chế đối soát.

## 4. Ranh giới giao dịch trở nên khó kiểm soát

Giao dịch là một lý do quan trọng để thiết kế step có phạm vi hợp lý. Với chunk-oriented step, mỗi chunk thường được xử lý trong một giao dịch: đọc và xử lý item, ghi chunk rồi commit. Với tasklet step, Spring Batch quản lý giao dịch cho mỗi lần gọi tasklet theo cấu hình của step.

Một step quá lớn có thể kết hợp các thao tác cần những chính sách giao dịch khác nhau. Chẳng hạn, cập nhật dữ liệu trong database cần rollback khi ghi lỗi, trong khi gửi email hoặc gọi HTTP không thể tự động rollback cùng giao dịch database.

Nếu các thao tác đó được đặt chung trong một step, lập trình viên dễ vô tình giả định rằng một lỗi ở cuối quy trình sẽ hoàn tác mọi thứ trước đó. Thực tế, chỉ các tài nguyên tham gia cùng giao dịch mới được quản lý bởi transaction manager đó. Một email đã gửi hoặc một yêu cầu HTTP đã được đối tác xử lý thường không thể được thu hồi bằng rollback JDBC.

Chia step theo ranh giới nghiệp vụ giúp xác định rõ:

- Giai đoạn nào ghi dữ liệu trong một giao dịch database.
- Giai đoạn nào thực hiện tác dụng phụ bên ngoài.
- Giai đoạn nào có thể chạy lại an toàn.
- Giai đoạn nào cần retry hoặc xử lý lỗi riêng.

Lưu ý: mỗi step không phải là một giao dịch toàn cục bao trùm toàn bộ job. Khi tách thành nhiều step, các giao dịch của những step trước đã commit không tự động bị rollback nếu step sau thất bại. Việc chia step làm rõ ranh giới giao dịch; nó không tạo ra một giao dịch phân tán cho toàn bộ job.

## 5. Chính sách retry, skip và xử lý lỗi khó áp dụng chính xác

Spring Batch cho phép cấu hình retry và skip trong chunk processing. Những chính sách này thường được áp dụng ở cấp item hoặc thao tác đọc, xử lý, ghi của một step.

Giả sử một step vừa đọc file, xác thực dữ liệu, ghi database và gọi dịch vụ tính phí. Các lỗi có thể có bản chất rất khác nhau:

- Dòng CSV sai định dạng có thể cần skip và ghi nhận lỗi dữ liệu.
- Lỗi kết nối database có thể cần retry hoặc làm step thất bại.
- API tính phí timeout có thể cần retry với backoff và idempotency key.
- Quy tắc nghiệp vụ không hợp lệ có thể cần loại bản ghi hoặc đưa vào vùng cách ly.

Nếu tất cả logic nằm trong một processor hoặc writer lớn, exception có thể khó phân loại. Một retry policy rộng có thể lặp lại cả những thao tác không nên lặp; một skip policy rộng có thể bỏ qua lỗi hạ tầng nghiêm trọng như thể đó là lỗi dữ liệu.

Tách các giai đoạn có chính sách lỗi khác nhau thành các step riêng giúp đặt retry, skip, listener và giới hạn số lần chạy đúng nơi. Tuy vậy, retry và skip vẫn cần được thiết kế dựa trên loại lỗi thực tế; không nên tách step chỉ để né việc phân loại exception.

## 6. Khó theo dõi hiệu năng và tìm điểm nghẽn

Một step lớn có thể thực hiện nhiều loại công việc với đặc tính hiệu năng khác nhau. Đọc file thường bị giới hạn bởi tốc độ I/O; xử lý dữ liệu có thể bị giới hạn bởi CPU; ghi database có thể bị giới hạn bởi index hoặc lock; gọi API ngoài phụ thuộc độ trễ mạng.

Nếu gom tất cả vào một step, thời gian tổng thể của step không cho biết chính xác giai đoạn nào đang chậm. Các bộ đếm chunk cũng không thể hiện đầy đủ thời gian dành cho từng tác dụng phụ tùy chỉnh.

Khi tách theo giai đoạn, có thể quan sát thời lượng và trạng thái riêng của từng step, từ đó xác định nên tối ưu reader, processor, writer, truy vấn database hay tích hợp bên ngoài. Các step độc lập cũng có thể được cân nhắc về partitioning hoặc chạy theo cơ chế điều phối phù hợp khi kiến trúc cho phép.

Không nên chia step chỉ để có thêm số liệu. Nếu một giai đoạn nhỏ không có yêu cầu vận hành riêng, listener hoặc metric ở cấp thành phần có thể đủ để quan sát mà không làm flow phức tạp.

## 7. Step lớn làm code khó đọc và khó kiểm thử

Một step chứa quá nhiều trách nhiệm thường kéo theo nhiều dependency, điều kiện và trạng thái nội bộ. Ví dụ một tasklet có thể vừa đọc cấu hình, truy vấn nhiều repository, xử lý nghiệp vụ, gọi REST client, ghi file và gửi email.

Hệ quả thường gặp:

- Phương thức `execute` dài, có nhiều nhánh `if/else` và khó hiểu thứ tự xử lý.
- Một thay đổi nhỏ trong bước tạo báo cáo có thể ảnh hưởng đến bước nhập dữ liệu.
- Unit test phải mock quá nhiều dependency để kiểm tra một hành vi.
- Khó kiểm thử riêng tình huống restart hoặc lỗi của từng giai đoạn.
- Nhiều thành viên cùng sửa một lớp hoặc một cấu hình step, dễ tạo xung đột.

Tách step theo giai đoạn nghiệp vụ giúp cấu hình và trạng thái của mỗi phần rõ ràng. Các lớp xử lý nghiệp vụ vẫn có thể được tách thành service nhỏ và được gọi từ reader, processor, writer hoặc tasklet. Không nhất thiết mọi phương thức helper đều trở thành một step.

## 8. Ví dụ: một step quá tải và cách tổ chức lại

Giả sử một job xử lý file thanh toán. Cách viết ban đầu đặt toàn bộ công việc trong một tasklet:

```java
@Bean
Step processPaymentFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PaymentFileService paymentFileService,
        PaymentRepository paymentRepository,
        PartnerClient partnerClient,
        ReportService reportService,
        NotificationService notificationService) {

    return new StepBuilder("processPaymentFileStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                var payments = paymentFileService.readAndValidate();
                paymentRepository.saveAll(payments);
                partnerClient.publishPayments(payments);
                reportService.createReport(payments);
                notificationService.sendCompletionNotice();
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Đoạn code ngắn nhưng chứa nhiều giai đoạn có đặc tính khác nhau. Nếu `sendCompletionNotice` thất bại sau khi dữ liệu đã được ghi và đối tác đã nhận thanh toán, step vẫn có thể kết thúc `FAILED`. Khi restart, tasklet có nguy cơ chạy lại toàn bộ các thao tác.

Có thể tổ chức lại job thành các step theo giai đoạn:

```text
validatePaymentFileStep
          |
          v
importPaymentsStep
          |
          v
publishPaymentsStep
          |
          v
createPaymentReportStep
          |
          v
sendCompletionNoticeStep
```

Ví dụ cấu hình job theo Spring Batch 5 trở lên:

```java
@Configuration
public class PaymentJobConfiguration {

    @Bean
    Job paymentJob(
            JobRepository jobRepository,
            Step validatePaymentFileStep,
            Step importPaymentsStep,
            Step publishPaymentsStep,
            Step createPaymentReportStep,
            Step sendCompletionNoticeStep) {

        return new JobBuilder("paymentJob", jobRepository)
                .start(validatePaymentFileStep)
                .next(importPaymentsStep)
                .next(publishPaymentsStep)
                .next(createPaymentReportStep)
                .next(sendCompletionNoticeStep)
                .build();
    }
}
```

Các bean `Step` được khai báo riêng với reader, processor, writer hoặc tasklet phù hợp. Ví dụ, `importPaymentsStep` có thể là chunk-oriented step để đọc và ghi nhiều khoản thanh toán theo nhóm; `createPaymentReportStep` có thể là tasklet vì nó tạo một file tổng hợp.

Sau khi tổ chức lại, nếu bước tạo báo cáo thất bại, metadata thể hiện rõ các bước nhập và công bố thanh toán đã hoàn tất. Khi restart cùng JobInstance, các step đã hoàn tất thường được bỏ qua và step cần tiếp tục được thực thi theo cấu hình.

Đối với `publishPaymentsStep`, cần bảo đảm đối tác hỗ trợ idempotency key hoặc có cách tra cứu trạng thái đã nhận. Nếu đối tác đã nhận yêu cầu nhưng client bị timeout trước khi nhận phản hồi, việc gửi lại có thể tạo tác dụng phụ lặp. Tách step làm rõ nơi xử lý tình huống này, nhưng không tự giải quyết tính nhất quán với hệ thống ngoài.

## 9. Không phải mọi thao tác đều cần một step riêng

Tách step quá mức cũng có chi phí. Mỗi step tạo thêm metadata thực thi, trạng thái, cấu hình, listener và quan hệ trong flow. Một job có hàng chục hoặc hàng trăm step rất nhỏ có thể khó đọc, khó điều phối và khó bảo trì.

Ví dụ, nếu một quy trình cần trim chuỗi, chuẩn hóa chữ hoa/thường và kiểm tra một trường bắt buộc cho từng item, không cần tạo ba step chỉ cho ba phép biến đổi đó. Đây là chuỗi thao tác trên cùng một item, nên có thể đặt trong một `ItemProcessor` hoặc một service được processor gọi.

Tương tự, nếu một tasklet cần tạo thư mục rồi tạo một file marker trong cùng một thao tác chuẩn bị, hai hành động có thể nằm chung step nếu chúng có cùng mục đích, cùng cách xử lý lỗi và cùng chính sách restart.

Tách step thường hợp lý khi một hoặc nhiều điều kiện sau xuất hiện:

- Giai đoạn có ý nghĩa nghiệp vụ riêng và cần trạng thái hoàn tất riêng.
- Giai đoạn có thể thất bại độc lập và cần restart độc lập.
- Giai đoạn có transaction manager, tài nguyên hoặc ranh giới commit khác nhau.
- Giai đoạn cần retry, skip hoặc giới hạn số lần chạy khác nhau.
- Giai đoạn có yêu cầu vận hành, lịch chạy hoặc theo dõi riêng.
- Giai đoạn cần chạy có điều kiện hoặc có thể được bỏ qua theo kết quả trước đó.
- Giai đoạn có thể được partition hoặc phân phối xử lý theo cách riêng.

Giữ chung trong một step khi các thao tác là một phần của cùng một đơn vị xử lý, có cùng vòng đời và cùng cách phục hồi, đồng thời việc tách ra không tạo thêm giá trị vận hành rõ ràng.

## 10. Chọn chunk hay tasklet theo bản chất công việc

Việc nhồi logic đôi khi bắt nguồn từ việc chọn sai kiểu step. Một tasklet có thể chứa vòng lặp lớn tự đọc từng bản ghi, xử lý và ghi dữ liệu. Khi đó ứng dụng phải tự quản lý nhiều vấn đề mà chunk processing đã cung cấp sẵn.

| Nhu cầu | Cách triển khai thường phù hợp |
|---|---|
| Đọc nhiều item, xử lý từng item và ghi theo nhóm | Chunk-oriented step với `ItemReader`, `ItemProcessor`, `ItemWriter`. |
| Thực hiện một thao tác có phạm vi rõ như dọn file hoặc gọi stored procedure | Tasklet step. |
| Kiểm tra hoặc chuẩn bị dữ liệu đầu vào trước khi import | Một tasklet hoặc step riêng nếu cần trạng thái và khả năng restart riêng. |
| Chuyển đổi từng bản ghi theo quy tắc nghiệp vụ | `ItemProcessor` hoặc service được processor gọi. |
| Ghi dữ liệu hàng loạt vào một đích | `ItemWriter` trong chunk-oriented step. |
| Tạo báo cáo sau khi import hoàn tất | Step riêng nếu báo cáo là giai đoạn nghiệp vụ có thể theo dõi hoặc restart độc lập. |

Không nên biến tasklet thành một framework xử lý batch tự viết nếu yêu cầu thực tế phù hợp với chunk. Ngược lại, không cần dùng chunk chỉ để thực hiện một lệnh SQL hoặc một thao tác chuẩn bị đơn giản.

## 11. Dữ liệu cần chuyển giữa các step

Khi tách job thành nhiều step, có thể cần truyền kết quả từ step trước sang step sau. Spring Batch cung cấp `ExecutionContext` ở phạm vi step và job. Một step có thể lưu một giá trị nhỏ, chẳng hạn tên file đầu ra, số lượng bản ghi hoặc mã batch, để step sau sử dụng.

Ví dụ, step kiểm tra file có thể lưu đường dẫn file đã chuẩn hóa vào job execution context; step import đọc giá trị đó qua late binding hoặc một thành phần điều phối phù hợp.

```java
@Bean
Step prepareInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("prepareInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                String normalizedPath = "data/ready/orders.csv";
                chunkContext.getStepContext()
                        .getStepExecution()
                        .getJobExecution()
                        .getExecutionContext()
                        .putString("normalizedInput", normalizedPath);
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

ExecutionContext phù hợp với metadata nhỏ cần cho việc điều phối và restart. Không nên dùng nó để chuyển hàng trăm nghìn đối tượng hoặc payload lớn giữa các step. Với dữ liệu lớn, hãy ghi ra database, file hoặc object storage và truyền khóa hay đường dẫn tham chiếu.

Khi thiết kế dữ liệu giữa các step, cần xác định rõ ai tạo, ai đọc, thời điểm dữ liệu được commit và liệu step sau có thể chạy lại an toàn hay không. Nếu một step sau phụ thuộc vào dữ liệu chưa được commit hoặc file chưa được đóng hoàn chỉnh, restart có thể đọc phải dữ liệu không đầy đủ.

## 12. Tách step và điều khiển flow có điều kiện

Một lợi ích khác của việc có các step riêng là job có thể chọn nhánh dựa trên kết quả của một giai đoạn. Spring Batch hỗ trợ flow transition dựa trên `ExitStatus` và các cơ chế điều phối như `JobExecutionDecider`.

Ví dụ, sau khi kiểm tra file:

- Nếu có dữ liệu hợp lệ, tiếp tục import.
- Nếu file rỗng, chuyển sang step ghi nhận kết quả rỗng.
- Nếu dữ liệu không hợp lệ, kết thúc job theo nhánh lỗi nghiệp vụ.

Nếu tất cả logic nằm trong một step lớn, các nhánh này thường trở thành nhiều câu lệnh điều kiện lồng nhau bên trong tasklet. Khi tách thành các step và flow transition, đường đi của job được thể hiện trực tiếp trong cấu hình.

Không cần tách step chỉ vì có một câu lệnh `if`. Hãy tách khi nhánh đại diện cho một giai đoạn có trạng thái, hành vi hoặc chính sách vận hành riêng.

## 13. Cách refactor một step đang quá lớn

Khi gặp một step có quá nhiều logic, có thể cải thiện theo từng bước:

1. **Liệt kê các hành động hiện tại:** ghi lại đầu vào, đầu ra, thao tác database, lời gọi bên ngoài, file được tạo và các nhánh lỗi.
2. **Nhóm theo giai đoạn nghiệp vụ:** ví dụ chuẩn bị dữ liệu, import, đồng bộ hệ thống ngoài và tạo báo cáo.
3. **Xác định ranh giới commit:** làm rõ thao tác nào cùng giao dịch, thao tác nào đã tạo tác dụng phụ không thể rollback.
4. **Xác định cách phục hồi:** giai đoạn nào cần restart, retry, skip hoặc có thể chạy lại an toàn.
5. **Chọn loại step:** dùng chunk cho xử lý item theo nhóm; dùng tasklet cho tác vụ đơn lẻ hoặc do ứng dụng điều khiển.
6. **Tách service nghiệp vụ:** giữ logic tính toán và quy tắc trong các lớp có trách nhiệm rõ, được gọi từ processor, writer hoặc tasklet.
7. **Khai báo flow:** nối các step theo thứ tự hoặc nhánh điều kiện cần thiết.
8. **Thiết kế dữ liệu chuyển tiếp:** chỉ đưa khóa hoặc metadata nhỏ vào ExecutionContext; lưu dữ liệu lớn ở nơi phù hợp.
9. **Xem lại idempotency:** bảo đảm việc chạy lại một step không tạo bản ghi, giao dịch hoặc yêu cầu bên ngoài trùng lặp.
10. **Kiểm tra các tình huống vận hành:** thành công, thất bại ở từng giai đoạn, restart, dữ liệu rỗng và lỗi dịch vụ ngoài.

Không nên tách một step lớn bằng cách di chuyển nguyên khối code sang nhiều lớp mà không xác định lại ranh giới giao dịch và restart. Mục tiêu là làm rõ trách nhiệm và cách phục hồi, không chỉ làm ngắn phương thức `execute`.

## 14. Một số dấu hiệu cho thấy step đã quá tải

Bạn có thể xem xét thiết kế lại khi gặp các dấu hiệu sau:

- Một step có nhiều dependency thuộc các hệ thống hoặc miền nghiệp vụ không liên quan.
- Phương thức `execute`, processor hoặc writer có nhiều giai đoạn tuần tự và nhiều nhánh lỗi.
- Khi step thất bại, phải kiểm tra thủ công nhiều bảng hoặc file để biết phần nào đã hoàn thành.
- Restart có nguy cơ lặp lại những tác dụng phụ đã xảy ra ở giai đoạn trước.
- Cùng một step cần các chính sách retry/skip khác nhau cho nhiều loại công việc.
- Log của step không đủ để tìm ra giai đoạn chậm hoặc gây lỗi.
- Một thay đổi trong một giai đoạn thường buộc phải sửa hoặc kiểm thử lại toàn bộ step.

Các dấu hiệu này không phải quy tắc cứng. Một step có nhiều dependency chưa chắc đã sai nếu chúng cùng phục vụ một đơn vị xử lý. Hãy đánh giá theo ranh giới nghiệp vụ, giao dịch và phục hồi thay vì chỉ đếm số dòng code hoặc số dependency.

## 15. Những giới hạn cần cân nhắc khi tách quá nhiều step

Tách step mang lại trạng thái và khả năng vận hành riêng, nhưng cũng làm tăng độ phức tạp:

- Mỗi step bổ sung metadata và một `StepExecution` cần được lưu trữ.
- Job flow có nhiều cạnh và nhánh hơn, khó theo dõi nếu tên step hoặc transition không rõ nghĩa.
- Cần truyền dữ liệu giữa step và quản lý vòng đời của file hoặc tài nguyên trung gian.
- Có thể phát sinh thêm thao tác khởi tạo, đóng tài nguyên và commit metadata.
- Việc triển khai một thay đổi xuyên nhiều step có thể cần cập nhật nhiều cấu hình.
- Các step trước đã commit không tự động rollback khi step sau thất bại; cần có quy trình bù trừ nếu nghiệp vụ yêu cầu.

Vì vậy, không có một số lượng step tối ưu áp dụng cho mọi job. Một job nhập dữ liệu có thể chỉ cần một step chunk-oriented nếu toàn bộ công việc là một luồng read-process-write thống nhất. Một job đối soát nhiều hệ thống có thể cần nhiều step vì mỗi giai đoạn có trạng thái, giao dịch và chính sách phục hồi riêng.

## 16. Nguyên tắc thiết kế thực tế

Khi quyết định có nên đưa thêm logic vào một step hay tách thành step mới, hãy tự hỏi:

1. Công việc mới có cùng mục tiêu nghiệp vụ với step hiện tại không?
2. Nó có cùng đầu vào, đầu ra và ranh giới giao dịch không?
3. Nếu công việc mới thất bại, có cần giữ trạng thái hoàn tất của phần trước không?
4. Nó có cần retry, skip, giới hạn số lần chạy hoặc giám sát riêng không?
5. Khi restart, có thể chạy lại toàn bộ step một cách an toàn không?
6. Tách riêng có giúp người vận hành hiểu rõ hơn trạng thái job không?
7. Chi phí metadata và điều phối bổ sung có tương xứng với lợi ích không?

Nếu hai phần việc có vòng đời và cách phục hồi khác nhau, hãy cân nhắc tách chúng thành các step riêng. Nếu chúng chỉ là các thao tác nhỏ trong cùng một chu trình xử lý item, giữ chúng trong processor hoặc service thường dễ quản lý hơn.

Một step tốt có phạm vi đủ nhỏ để có thể hiểu, theo dõi và phục hồi, nhưng đủ lớn để tránh biến job thành một chuỗi dài các thao tác vụn vặt. Khi thiết kế theo ranh giới nghiệp vụ, Spring Batch có thể phát huy tốt các khả năng quản lý giao dịch, restart, retry, skip và theo dõi trạng thái mà không làm flow trở nên rối rắm.
