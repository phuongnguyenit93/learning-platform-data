# Lỗi một flow ảnh hưởng job thế nào?

Trong Spring Batch, `split()` cho phép một job chạy nhiều flow độc lập song song. Mỗi flow có thể chứa một hoặc nhiều step và thực hiện một phần công việc riêng, chẳng hạn tạo báo cáo, cập nhật chỉ mục tìm kiếm hoặc đồng bộ dữ liệu sang hệ thống khác.

Khi một flow trong nhóm bị lỗi, trạng thái lỗi được truyền về flow cha và ảnh hưởng đến kết quả của split. Trong trường hợp thông thường, nếu một nhánh kết thúc với trạng thái `FAILED`, split flow cũng có kết quả thất bại và job không đi tiếp theo đường thành công đã khai báo. Tuy nhiên, các nhánh khác có thể đã hoàn thành hoặc vẫn tiếp tục chạy; Spring Batch không tự động rollback những transaction mà chúng đã commit.

Đây là điểm quan trọng khi thiết kế parallel flow: các nhánh chạy đồng thời nhưng không tạo thành một transaction phân tán duy nhất. Cần xác định rõ cách tổng hợp trạng thái, xử lý phần việc đã hoàn tất, restart và bù trừ khi một nhánh thất bại.

## 1. Parallel flow hoạt động như thế nào?

Một split flow gồm nhiều flow con được đưa cho `TaskExecutor` thực thi. Mỗi flow con có thể chứa một step hoặc một chuỗi step. Manager điều phối việc chạy song song và chờ kết quả của các flow để xác định trạng thái chung.

Ví dụ job cần chuẩn bị dữ liệu, sau đó tạo báo cáo và cập nhật chỉ mục tìm kiếm độc lập:

```text
                 prepareData
                      |
                      v
                    split
                  /       \
                 /         \
        generateReport   updateSearchIndex
                 \         /
                  \       /
                    join
                      |
                      v
                 publishResult
```

Khi cả hai flow hoàn tất bình thường, split trả về kết quả thành công và job có thể chuyển sang `publishResult`. Nếu một flow thất bại, kết quả của split phản ánh trạng thái lỗi và đường thành công phía sau không được thực hiện theo transition mặc định.

## 2. Khai báo split flow

Có thể tách các nhánh thành `Flow` riêng rồi ghép bằng `split(taskExecutor).add(...)`.

```java
@Bean
Flow reportFlow(Step generateReportStep) {
    return new FlowBuilder<SimpleFlow>("reportFlow")
        .start(generateReportStep)
        .build();
}

@Bean
Flow searchIndexFlow(Step updateSearchIndexStep) {
    return new FlowBuilder<SimpleFlow>("searchIndexFlow")
        .start(updateSearchIndexStep)
        .build();
}

@Bean
Flow parallelFlow(
        TaskExecutor taskExecutor,
        Flow reportFlow,
        Flow searchIndexFlow) {

    return new FlowBuilder<SimpleFlow>("parallelFlow")
        .split(taskExecutor)
        .add(reportFlow, searchIndexFlow)
        .build();
}
```

Job sử dụng split flow như một giai đoạn:

```java
@Bean
Job reportingJob(
        JobRepository jobRepository,
        Step prepareDataStep,
        Flow parallelFlow,
        Step publishResultStep) {

    return new JobBuilder("reportingJob", jobRepository)
        .start(prepareDataStep)
        .next(parallelFlow)
        .next(publishResultStep)
        .end()
        .build();
}
```

Ví dụ giả định hai flow sau `prepareDataStep` không phụ thuộc kết quả của nhau. `TaskExecutor` quyết định cách thực thi song song và số thread tối đa. Nếu không có executor bất đồng bộ phù hợp, các flow có thể không chạy song song như mong đợi.

## 3. Điều gì xảy ra khi một flow thất bại?

Giả sử split gồm hai flow:

- `reportFlow`: tạo file báo cáo.
- `searchIndexFlow`: cập nhật chỉ mục tìm kiếm.

Nếu `reportFlow` hoàn tất nhưng `searchIndexFlow` thất bại, kết quả thường thấy là:

```text
parallelFlow
  +-- reportFlow       -> COMPLETED
  +-- searchIndexFlow  -> FAILED

Kết quả split          -> FAILED
JobExecution           -> FAILED
publishResultStep      -> không chạy theo đường thành công mặc định
```

Các step đã hoàn tất trong nhánh báo cáo vẫn có trạng thái `COMPLETED`. Job thất bại không có nghĩa mọi step ở tất cả nhánh đều bị đánh dấu thất bại hoặc dữ liệu của chúng bị xóa.

Split phải thu thập kết quả của các flow con để xác định kết quả tổng hợp. Vì vậy, khi một flow lỗi, các flow anh em đã được gửi đi có thể vẫn chạy đến khi hoàn tất hoặc tự thất bại. Không nên thiết kế dựa trên giả định rằng lỗi ở một nhánh sẽ hủy tức thì mọi nhánh còn lại.

## 4. Trạng thái của split được tổng hợp từ các flow con

Mỗi flow con trả về một `FlowExecutionStatus`. Split tổng hợp các trạng thái đó để trả về trạng thái chung cho flow cha. Trong trường hợp thông thường, `COMPLETED` từ tất cả nhánh cho phép split hoàn tất thành công; trạng thái không thành công ở một nhánh sẽ ảnh hưởng đến kết quả chung.

| Kết quả các flow con | Kết quả split thường gặp | Ảnh hưởng tới job |
|---|---|---|
| Tất cả `COMPLETED` | `COMPLETED` | Có thể đi tiếp theo đường thành công |
| Một nhánh `FAILED`, nhánh khác `COMPLETED` | `FAILED` | Job thất bại nếu không có transition xử lý riêng |
| Nhiều nhánh `FAILED` | `FAILED` | Job thất bại; cần điều tra từng nhánh |
| Một nhánh `STOPPED`, các nhánh khác hoàn tất | Kết quả không thành công tương ứng được truyền lên | Job không được coi là hoàn tất bình thường |
| Có trạng thái không xác định hoặc custom status | Phụ thuộc quy tắc trạng thái và transition | Cần khai báo xử lý rõ ràng |

Không nên chỉ nhìn trạng thái cuối của JobExecution để kết luận nhánh nào gây lỗi. Hãy kiểm tra trạng thái `FlowExecution`, `StepExecution` và exception của từng nhánh trong metadata/log.

## 5. Job không nhất thiết dừng ngay khi một nhánh vừa lỗi

Các flow trong split được thực thi trên executor. Một flow có thể thất bại trong khi flow khác vẫn đang chạy. Split cần thu thập kết quả thực thi của các nhánh trước khi tiếp tục điều khiển flow cha.

Ví dụ:

```text
Thời gian ----->

reportFlow:       RUNNING -------- COMPLETED
searchIndexFlow:  RUNNING -- FAILED
archiveFlow:      RUNNING ---------------- COMPLETED
                                  |
                                  v
                     split tổng hợp kết quả
                                  |
                                  v
                              FAILED
```

Trong sơ đồ, `searchIndexFlow` thất bại trước nhưng `reportFlow` và `archiveFlow` vẫn có thể kết thúc. Job sau đó nhận kết quả split thất bại. Điều này có nghĩa một phần side effect có thể đã xảy ra trước khi job được đánh dấu `FAILED`.

Việc hủy task đang chạy phụ thuộc executor, handler và cơ chế điều phối cụ thể. Không nên coi trạng thái `FAILED` của một flow là cơ chế cancellation hay rollback cho các flow khác.

## 6. Step phía sau split có chạy không?

Với flow thông thường khai báo `.next(parallelFlow).next(publishResultStep)`, step phía sau chỉ chạy khi split hoàn tất theo trạng thái cho phép chuyển tiếp. Nếu split trả về `FAILED`, transition thành công mặc định không được chọn và `publishResultStep` không chạy.

Điều này thường là hành vi mong muốn: không công bố kết quả tổng hợp nếu một phần công việc song song chưa hoàn thành.

Nếu nghiệp vụ yêu cầu chạy bước ghi nhận lỗi hoặc bù trừ, cần khai báo conditional transition cho trạng thái split. Ví dụ về cấu trúc điều hướng:

```java
return new JobBuilder("reportingJob", jobRepository)
    .start(parallelFlow)
        .on("COMPLETED").to(publishResultStep)
    .from(parallelFlow)
        .on("FAILED").to(recordParallelFailureStep)
    .from(parallelFlow)
        .on("*").fail()
    .from(publishResultStep)
        .on("COMPLETED").end()
    .from(publishResultStep)
        .on("*").fail()
    .from(recordParallelFailureStep)
        .on("*").fail()
    .end()
    .build();
```

Ví dụ này ghi nhận sự cố qua `recordParallelFailureStep` rồi vẫn kết thúc job ở trạng thái thất bại. Như vậy hệ thống có thể lưu thông tin vận hành hoặc phát cảnh báo mà không biến một split thất bại thành kết quả thành công.

Transition phải khớp với trạng thái thực tế mà flow trả về. Nếu có custom `FlowExecutionStatus`, hãy khai báo pattern tương ứng và có nhánh dự phòng rõ ràng.

## 7. Phân biệt FlowExecutionStatus, ExitStatus và BatchStatus

Khi điều tra lỗi parallel flow, cần phân biệt ba loại trạng thái:

| Trạng thái | Phạm vi | Ý nghĩa |
|---|---|---|
| `FlowExecutionStatus` | Kết quả của một flow hoặc split flow | Điều khiển transition giữa các flow/step |
| `ExitStatus` | Kết quả thoát của một step hoặc job | Mã kết quả được dùng trong flow transition và báo cáo |
| `BatchStatus` | Vòng đời của JobExecution/StepExecution | Trạng thái như `STARTED`, `COMPLETED`, `FAILED`, `STOPPED` |

Một step trong nhánh có thể kết thúc với `BatchStatus.FAILED`; flow chứa step đó phản ánh kết quả thất bại. Split tổng hợp trạng thái flow con rồi trả về trạng thái cho flow cha. JobExecution cuối cùng được cập nhật theo kết quả điều phối và các trạng thái thực thi liên quan.

`FlowExecutionStatus` không phải một transaction status. Nó không quyết định commit hay rollback dữ liệu của các step đã chạy.

## 8. Transaction của các nhánh độc lập

Mỗi worker step trong các flow song song có transaction riêng theo transaction manager và chunk/tasklet của step đó. Không có một transaction tự động bao trùm tất cả nhánh của `split()`.

Ví dụ:

```text
reportFlow:
  write report metadata -> COMMIT
  write report file     -> hoàn tất

searchIndexFlow:
  update index batch 1  -> COMMIT
  update index batch 2  -> lỗi -> ROLLBACK batch 2

Kết quả:
  report metadata và file đã tạo vẫn tồn tại
  index batch 1 đã commit vẫn tồn tại
  index batch 2 được rollback nếu cùng transaction resource
  job kết thúc FAILED
```

Các chunk đã commit trong nhánh thất bại cũng không tự động bị rollback chỉ vì step sau đó thất bại. Tương tự, một flow khác đã hoàn thành không bị hoàn tác.

Nếu nghiệp vụ yêu cầu “tất cả nhánh cùng thành công hoặc không công bố kết quả nào”, hãy thiết kế thêm staging/publish hoặc cơ chế bù trừ. Không thể đạt atomicity toàn cục chỉ bằng cách dùng `split()`.

## 9. Side effect ngoài transaction có thể còn lại

Transaction database chỉ rollback được các thay đổi thuộc tài nguyên transaction đó. Nếu một nhánh gửi email, gọi HTTP API, tạo file trên filesystem hoặc publish message, side effect đó có thể đã xảy ra dù transaction database rollback.

Ví dụ, `reportFlow` đã gửi báo cáo qua email. Sau đó `searchIndexFlow` thất bại. Job tổng thể là `FAILED`, nhưng email đã gửi không thể được thu hồi bằng rollback của Spring Batch.

Các biện pháp bảo vệ:

- Dùng idempotency key cho API bên ngoài để lần chạy lại không tạo thao tác trùng.
- Ghi sự kiện vào outbox trong transaction và chỉ phát sau commit.
- Tạo file tạm theo execution ID, chỉ đổi tên/công bố file khi mọi nhánh hoàn tất.
- Lưu trạng thái hoàn thành từng nhánh để bước bù trừ biết việc nào đã xảy ra.
- Thiết kế thao tác bù trừ (compensation) nếu nghiệp vụ cần đảo ngược một phần công việc.

Không nên phát hành kết quả ra bên ngoài ngay trong nhánh song song nếu kết quả đó chỉ hợp lệ khi tất cả nhánh đều thành công. Hãy để các nhánh chuẩn bị dữ liệu riêng, sau đó dùng một step phía sau split để công bố.

## 10. Xử lý lỗi bên trong từng flow

Không phải mọi lỗi đều cần làm cả split thất bại. Nếu một step có thể tự xử lý lỗi bằng retry hoặc skip, hãy cấu hình fault tolerance ngay trong step đó.

Ví dụ:

```java
return new StepBuilder("updateSearchIndex", jobRepository)
    .<IndexRow, IndexDocument>chunk(100, transactionManager)
    .reader(indexReader)
    .processor(indexProcessor)
    .writer(indexWriter)
    .faultTolerant()
    .retry(TransientDataAccessException.class)
    .retryLimit(3)
    .skip(InvalidIndexRowException.class)
    .skipLimit(20)
    .build();
```

Với cấu hình này, lỗi tạm thời có thể được retry và item lỗi được phép loại bỏ có thể được skip. Nếu lỗi không được xử lý, vượt retry/skip limit hoặc là lỗi nghiêm trọng, step vẫn thất bại và trạng thái đó truyền lên flow cha.

Chỉ skip những exception đại diện cho dữ liệu có thể loại bỏ. Không skip lỗi kết nối hoặc lỗi cấu hình diện rộng chỉ để giữ cho một nhánh có vẻ thành công.

## 11. Một flow thất bại không làm các nhánh khác rollback

Đây là khác biệt quan trọng giữa điều phối song song và transaction phân tán. Giả sử ba nhánh chạy độc lập:

| Flow | Kết quả | Dữ liệu có thể đã commit |
|---|---|---|
| `generateReportFlow` | `COMPLETED` | File báo cáo và metadata báo cáo |
| `updateIndexFlow` | `FAILED` | Các batch index đã commit trước lỗi |
| `refreshCacheFlow` | `COMPLETED` | Cache đã được làm mới |

Job có thể kết thúc `FAILED`, dù hai flow đã hoàn tất. Spring Batch lưu lịch sử từng step execution để người vận hành biết công việc nào đã thành công và công việc nào thất bại.

Vì vậy, bước phục hồi không nên chạy lại mù quáng tất cả side effect. Hãy dựa trên metadata và trạng thái nghiệp vụ để quyết định việc nào cần tiếp tục, việc nào cần kiểm tra hoặc bù trừ.

## 12. Restart job sau khi một flow thất bại

Khi restart cùng JobInstance, Spring Batch sử dụng `JobRepository` để xác định step nào đã hoàn thành và step nào cần chạy lại theo chính sách restart.

Ví dụ lần đầu:

```text
Execution #1
  prepareDataStep          -> COMPLETED
  reportFlow
    generateReportStep     -> COMPLETED
  searchIndexFlow
    updateSearchIndexStep  -> FAILED
```

Khi restart:

```text
Execution #2 (cùng JobInstance)
  prepareDataStep          -> bỏ qua nếu đã COMPLETED
  generateReportStep       -> bỏ qua nếu đã COMPLETED
  updateSearchIndexStep    -> restart theo checkpoint nếu hợp lệ
  publishResultStep        -> chỉ chạy khi split/flow đạt trạng thái cho phép
```

Đây là mô hình khái quát; hành vi chính xác phụ thuộc cấu trúc flow, step đã hoàn thành, restart policy, trạng thái execution và cấu hình `allowStartIfComplete`/`startLimit`. Không nên giả định mọi flow con luôn được khởi chạy lại toàn bộ.

### Điều kiện để restart an toàn

- JobInstance phải ở trạng thái có thể restart và job không bị cấu hình `preventRestart()`.
- Step name và cấu trúc flow cần ổn định để metadata cũ được đối chiếu đúng.
- Reader/Tasklet phải lưu checkpoint cần thiết trong `ExecutionContext`.
- Các nhánh đã hoàn thành phải an toàn khi được bỏ qua; side effect không nên bị tạo lại ngoài ý muốn.
- Partitions, file names và request IDs phải ổn định nếu chúng là định danh của công việc.
- Các thao tác ngoài transaction cần idempotency hoặc đối soát.

Restart không tự hoàn tác công việc đã commit ở nhánh thành công. Nó tiếp tục từ metadata và trạng thái đã lưu; nếu cần đảo ngược công việc cũ, phải thiết kế compensation riêng.

## 13. JobParameters và dữ liệu dùng chung giữa các nhánh

Các flow trong cùng một JobExecution thường dùng chung ngữ cảnh job và có thể đọc cùng JobParameters. Tuy nhiên, không nên để nhiều nhánh đồng thời ghi các key giống nhau vào `JobExecution` `ExecutionContext` mà không có quy tắc đồng bộ.

Mỗi step có `StepExecution` và step `ExecutionContext` riêng. Hãy dùng step context cho trạng thái nội bộ của từng nhánh. Nếu cần trao đổi kết quả giữa các nhánh, hãy dùng key riêng, dữ liệu bất biến hoặc kho lưu trữ có cơ chế đồng bộ rõ ràng.

Không dùng biến static hoặc mutable singleton để chia sẻ kết quả giữa các flow. Các nhánh có thể chạy trên thread khác nhau và cùng sửa một object, gây race condition hoặc mất cập nhật.

## 14. Dùng bước tổng hợp sau split

Một thiết kế thường dễ vận hành là để các nhánh chỉ tạo kết quả riêng, rồi dùng một step sau split để xác nhận và công bố khi tất cả nhánh cần thiết đã hoàn tất.

```text
prepareData
    |
    v
   split
   /   \
  /     \
createReport   updateIndex
  \             /
   \           /
    +-- join --+
         |
         v
   verifyOutputs
         |
         v
   publishResults
```

`verifyOutputs` có thể kiểm tra file báo cáo tồn tại, chỉ mục đã cập nhật đến watermark cần thiết và các số liệu đối chiếu khớp nhau. Chỉ khi kiểm tra thành công mới chạy `publishResults`.

Nếu một nhánh thất bại, split không đi theo đường thành công nên bước publish không chạy. Các output trung gian vẫn có thể còn lại; bước phục hồi có thể tiếp tục nhánh lỗi hoặc dọn dữ liệu tạm theo chính sách.

## 15. Compensation khi không thể rollback toàn bộ

Với các side effect không thể rollback, có thể cần một quy trình bù trừ. Compensation là thao tác nghiệp vụ mới nhằm đưa hệ thống về trạng thái chấp nhận được, chẳng hạn hủy một yêu cầu đã tạo hoặc đánh dấu một báo cáo là không hợp lệ.

Ví dụ:

1. `generateReportFlow` tạo file tạm và ghi metadata trạng thái `PREPARED`.
2. `updateIndexFlow` cập nhật chỉ mục nhưng thất bại.
3. Job ghi nhận split thất bại.
4. Step xử lý lỗi đánh dấu file báo cáo là `NOT_PUBLISHED` hoặc xóa file tạm nếu an toàn.
5. Sau khi sửa lỗi, restart nhánh chỉ mục và xác minh lại output.
6. Chỉ publish báo cáo khi toàn bộ điều kiện hoàn tất.

Compensation không phải rollback database tự động. Nó là một phần của quy trình nghiệp vụ và cần idempotency, audit, retry cùng chính sách xử lý khi chính thao tác bù trừ cũng thất bại.

## 16. Quan sát và chẩn đoán lỗi theo từng nhánh

Khi job thất bại ở split, hãy tìm đúng flow và step gây lỗi thay vì chỉ nhìn trạng thái JobExecution cuối cùng.

Thông tin nên theo dõi:

- Job name, JobInstance ID và JobExecution ID.
- Tên flow và tên step trong từng nhánh.
- `BatchStatus` và `ExitStatus` của mỗi StepExecution.
- Exception gốc, thời điểm bắt đầu/kết thúc và số lần retry.
- Read/write/skip count và checkpoint của worker.
- Side effect đã commit hoặc đã phát ra hệ thống ngoài.

Log nên có correlation ID để liên kết thông tin từ manager và worker. Tránh ghi toàn bộ payload hoặc secret trong context. Với flow chạy song song, timestamp và thread name cũng hữu ích để hiểu thứ tự sự kiện.

## 17. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng một nhánh fail sẽ rollback mọi nhánh | Dữ liệu đã commit ở nhánh khác vẫn còn | Thiết kế idempotency, staging hoặc compensation |
| Cho rằng lỗi một nhánh hủy ngay các nhánh còn lại | Nhánh anh em có thể vẫn chạy và tạo side effect | Thiết kế nhánh an toàn khi chạy đồng thời; không dựa vào cancellation ngầm |
| Công bố kết quả ngay trong từng nhánh | Người dùng có thể thấy kết quả một phần khi nhánh khác thất bại | Dùng bước verify/publish sau split |
| Bỏ qua trạng thái từng StepExecution | Khó xác định nhánh nào đã hoàn tất | Theo dõi metadata của từng flow/step |
| Dùng chung mutable state giữa các nhánh | Race condition và dữ liệu không nhất quán | Dùng step context riêng hoặc kho đồng bộ phù hợp |
| Không cấu hình retry/skip phù hợp trong worker | Lỗi item có thể làm cả flow thất bại không cần thiết | Phân loại lỗi và cấu hình fault tolerance ở cấp step |
| Restart nhưng thay đổi phạm vi công việc | Step cũ có thể chạy với dữ liệu khác hoặc tạo side effect trùng | Giữ JobParameters, step names và định danh output ổn định |
| Dùng transition wildcard để biến mọi lỗi thành thành công | Job có thể báo hoàn tất dù nhánh thất bại | Định nghĩa rõ chính sách thất bại và compensation |

## 18. Kiểm thử hành vi lỗi của parallel flow

Integration test nên mô phỏng ít nhất các trường hợp sau:

1. Tất cả flow hoàn tất: xác nhận split thành công và step sau split chạy.
2. Một flow thất bại ngay lập tức: xác nhận kết quả split và JobExecution phản ánh lỗi.
3. Một flow thất bại trong khi nhánh khác hoàn tất chậm: xác nhận nhánh còn lại có thể tiếp tục và side effect được ghi nhận.
4. Một flow có retry thành công: xác nhận split chỉ nhận kết quả cuối cùng của flow sau recovery.
5. Một flow bị skip item nhưng hoàn tất step: xác nhận chính sách nghiệp vụ quyết định có coi flow là thành công hay không.
6. Restart sau khi một flow thất bại: xác nhận step đã hoàn thành không bị chạy lại ngoài ý muốn và nhánh lỗi tiếp tục đúng checkpoint.
7. Lỗi trong bước compensation hoặc record failure: xác nhận job vẫn có trạng thái và audit rõ ràng.
8. Chạy song song thực tế: xác nhận không có race condition trong reader, writer, listener và dữ liệu context dùng chung.

Test cần kiểm tra cả trạng thái metadata lẫn dữ liệu đã commit. Chỉ assert `JobExecution` là `FAILED` chưa đủ để chứng minh các nhánh khác không tạo side effect.

## 19. Quy trình xử lý khi một flow lỗi trong production

Khi nhận cảnh báo job thất bại ở parallel flow, có thể xử lý theo trình tự:

1. Xác định flow và step có `FAILED` hoặc trạng thái bất thường từ metadata.
2. Kiểm tra các flow anh em đã hoàn thành, còn chạy hay cũng thất bại.
3. Xác định chunk/transaction nào đã commit và side effect ngoài nào đã xảy ra.
4. Khắc phục nguyên nhân ở nhánh lỗi và xác nhận JobInstance có thể restart.
5. Kiểm tra checkpoint, input range và output đã tạo để tránh xử lý trùng.
6. Thực hiện compensation hoặc dọn dữ liệu tạm nếu quy trình yêu cầu.
7. Restart cùng JobInstance khi mục tiêu là tiếp tục công việc đang dang dở.
8. Chỉ chạy bước verify/publish khi tất cả điều kiện nghiệp vụ đã thỏa mãn.

Không tạo JobInstance mới chỉ để né trạng thái `FAILED` nếu mục tiêu thực tế là tiếp tục cùng một công việc. Tạo instance mới có thể khiến toàn bộ nhánh chạy lại và lặp side effect.

## Kết luận

Trong parallel flow, lỗi của một flow được tổng hợp vào trạng thái của split và thường làm job thất bại, khiến các step phía sau đường thành công không chạy. Các flow anh em có thể vẫn tiếp tục hoặc đã hoàn tất; transaction và side effect đã commit của chúng không tự động bị rollback.

Muốn xử lý an toàn, hãy theo dõi trạng thái từng nhánh, đặt retry/skip ở đúng step, giữ output trung gian chưa công bố, dùng idempotency cho side effect ngoài transaction và thiết kế compensation khi cần. Restart cùng JobInstance dựa trên metadata và checkpoint của từng step; chỉ công bố kết quả sau khi mọi nhánh bắt buộc đã hoàn tất và bước xác minh thành công.
