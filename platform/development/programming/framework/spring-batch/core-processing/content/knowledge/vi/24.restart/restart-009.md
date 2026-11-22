# startLimit của step

Trong Spring Batch, `startLimit` giới hạn số lần một Step được phép bắt đầu trong cùng một JobInstance. Mỗi lần Step được khởi chạy tạo một `StepExecution` mới. Khi số lần bắt đầu đã đạt giới hạn, lần chạy tiếp theo của Step bị từ chối và Spring Batch phát sinh `StartLimitExceededException`.

`startLimit` hữu ích với những Step có tác dụng phụ tốn kém hoặc không nên được thực hiện quá nhiều lần, chẳng hạn gọi một hệ thống bên ngoài, tạo file bàn giao, chạy thủ tục đối soát hoặc thực hiện thao tác chỉ được thử lại một số lần. Đây là giới hạn ở cấp Step execution; nó không thay thế retry policy của item và cũng không phải giới hạn số lần launch Job trên toàn hệ thống.

## 1. startLimit là gì?

Một Job có thể được restart sau khi thất bại. Trong mỗi JobExecution, một Step có thể được bắt đầu lại tùy theo trạng thái trước đó và chính sách restart. `startLimit(n)` đặt số lần tối đa Step được phép bắt đầu cho một JobInstance.

Ví dụ cấu hình:

```java
return new StepBuilder("reconcileStep", jobRepository)
        .tasklet(reconcileTasklet, transactionManager)
        .startLimit(3)
        .build();
```

Với `startLimit(3)`, Step có thể bắt đầu tối đa ba lần trong JobInstance đó. Nếu Step thất bại trong cả ba lần và người vận hành tiếp tục restart Job, lần bắt đầu thứ tư bị từ chối.

`startLimit` mặc định là `Integer.MAX_VALUE`, tức giới hạn rất lớn nếu không được cấu hình rõ. Không đặt `startLimit` không có nghĩa Step không thể restart; Job vẫn áp dụng cơ chế restart mặc định và có thể tiếp tục sau lỗi nếu các điều kiện khác cho phép.

## 2. startLimit được tính như thế nào?

Spring Batch theo dõi các lần thực thi Step thông qua `StepExecution` được lưu trong `JobRepository`. Khi một Step được bắt đầu, một StepExecution tương ứng được tạo và metadata được lưu. Bộ đếm số lần bắt đầu được xét trong phạm vi JobInstance và Step tương ứng.

Giả sử cấu hình `startLimit(2)`:

```text
JobInstance: dailyReconciliation / businessDate=2026-11-15
  |
  +--> JobExecution #1
  |       reconcileStep starts: lần 1
  |       reconcileStep = FAILED
  |
  +--> JobExecution #2 (restart cùng JobInstance)
  |       reconcileStep starts: lần 2
  |       reconcileStep = FAILED
  |
  +--> JobExecution #3 (restart cùng JobInstance)
          reconcileStep không được bắt đầu
          StartLimitExceededException
```

Điểm quan trọng:

- Giới hạn bao gồm lần bắt đầu đầu tiên, không phải số lần restart được cộng thêm sau lần đầu.
- Các lần bắt đầu thất bại hoặc dừng vẫn tiêu thụ giới hạn.
- Restart cùng JobInstance tiếp tục dùng bộ đếm lịch sử của Step.
- Một JobInstance mới có identifying JobParameters khác sẽ có lịch sử thực thi riêng và bộ đếm Step riêng.
- `startLimit` không đếm số item, số chunk hoặc số lần retry một item.

Vì vậy, `startLimit(1)` có nghĩa Step chỉ được bắt đầu một lần trong JobInstance. Nếu lần đầu thất bại, không thể restart Step đó thêm lần nữa trong cùng instance.

## 3. Cấu hình startLimit cho Tasklet Step

Với Spring Batch 5 trở lên, có thể đặt `startLimit()` trực tiếp trên builder của Step:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step externalReconciliationStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet reconciliationTasklet) {

    return new StepBuilder("externalReconciliationStep", jobRepository)
            .tasklet(reconciliationTasklet, transactionManager)
            .startLimit(3)
            .build();
}
```

Trong ví dụ, Tasklet có thể gọi một hệ thống đối soát bên ngoài. Giới hạn ba lần ngăn cùng Step được bắt đầu không giới hạn khi JobInstance liên tục bị restart.

Nếu Tasklet thực hiện một thao tác có thể đã hoàn tất trước khi ứng dụng dừng, cần có idempotency key hoặc cơ chế kiểm tra trạng thái. `startLimit` chỉ chặn số lần bắt đầu; nó không xác định thao tác bên ngoài đã thành công hay chưa.

## 4. Cấu hình startLimit cho chunk-oriented Step

`startLimit` cũng áp dụng cho chunk Step. Nó giới hạn số lần Step được khởi chạy, không giới hạn số chunk bên trong mỗi lần chạy:

```java
import org.springframework.batch.core.Step;
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
        ItemReader<Order> reader,
        ItemProcessor<Order, ProcessedOrder> processor,
        ItemWriter<ProcessedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .startLimit(2)
            .build();
}
```

Step trên có thể xử lý nhiều chunk trong mỗi lần bắt đầu. Nếu xử lý 100.000 item với commit interval 500, Step có thể commit 200 chunk trong một lần start. `startLimit(2)` không giới hạn số chunk là 2; nó giới hạn Step chỉ được bắt đầu tối đa hai lần trong JobInstance.

## 5. Khi vượt giới hạn xảy ra điều gì?

Khi Step đã đạt số lần bắt đầu tối đa, Spring Batch không thực hiện Step thêm lần nữa và phát sinh `StartLimitExceededException`. Lỗi này được ghi nhận trong quá trình thực thi Job; Job thường kết thúc `FAILED` nếu flow không có cách xử lý kết quả lỗi riêng.

Ví dụ cấu hình giới hạn một lần:

```java
return new JobBuilder("oneAttemptJob", jobRepository)
        .start(externalCallStep)
        .build();
```

Step:

```java
return new StepBuilder("externalCallStep", jobRepository)
        .tasklet(externalCallTasklet, transactionManager)
        .startLimit(1)
        .build();
```

Nếu lần chạy đầu của `externalCallStep` thất bại, restart Job với cùng identifying parameters sẽ không thể bắt đầu lại Step. Lần chạy tiếp theo có thể kết thúc với lỗi `StartLimitExceededException` trước khi Tasklet được gọi.

Không nên nhầm `StartLimitExceededException` với exception do item trong Reader, Processor hoặc Writer. Đây là lỗi chính sách ở cấp Step start. Retry item không thể làm tăng giới hạn Step hoặc xóa lịch sử StepExecution.

## 6. Phân biệt startLimit với retryLimit và skipLimit

Ba giới hạn này hoạt động ở các cấp khác nhau:

| Cấu hình | Phạm vi | Đếm điều gì? | Khi vượt giới hạn |
|---|---|---|---|
| `startLimit(n)` | Step trong một JobInstance | Số lần Step được bắt đầu | Step không được bắt đầu thêm; phát sinh `StartLimitExceededException`. |
| `retryLimit(n)` | Fault-tolerant chunk processing | Số lần thử lại thao tác/item theo retry policy | Exception được xử lý tiếp theo skip policy nếu phù hợp, nếu không Step thất bại. |
| `skipLimit(n)` | Step execution | Tổng số item lỗi được phép bỏ qua ở read/process/write | Step thất bại khi skip tiếp theo vượt giới hạn. |

Ví dụ một Step có thể có:

```java
return new StepBuilder("importStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .startLimit(4)
        .build();
```

Trong cấu hình này:

- Mỗi item hoặc thao tác phù hợp có thể được retry theo giới hạn retry.
- Các item có lỗi nghiệp vụ thuộc nhóm skippable có thể bị bỏ qua, tối đa 20 skip.
- Toàn bộ Step chỉ được bắt đầu tối đa bốn lần trong cùng JobInstance.

Retry và skip xử lý lỗi bên trong một lần chạy Step. `startLimit` kiểm soát việc Step có được phép bắt đầu một lần thực thi mới hay không.

## 7. Phân biệt startLimit với giới hạn chạy của Job

`startLimit` không giới hạn số lần Job được launch trên toàn hệ thống. Nó áp dụng cho một Step cụ thể trong một JobInstance.

Ví dụ:

- JobInstance A có `businessDate=2026-11-15`; Step có thể bắt đầu tối đa ba lần.
- JobInstance B có `businessDate=2026-11-16`; đây là instance khác và có bộ đếm Step riêng.
- Nếu scheduler launch lại cùng JobParameters của instance A, Spring Batch xem đó là restart/launch cùng instance và áp dụng lịch sử startLimit của instance A.
- Nếu thêm một identifying parameter mới, JobInstance mới có thể được tạo và Step có lịch sử start riêng.

Nếu yêu cầu là giới hạn một Step chỉ được chạy ba lần mỗi ngày trên tất cả JobInstance, `startLimit` không đủ. Cần tạo bộ đếm nghiệp vụ hoặc bảng điều phối dùng khóa theo Step và ngày, với transaction/unique constraint phù hợp.

Không nên thêm timestamp vào identifying JobParameters chỉ để vượt startLimit. Điều đó tạo một JobInstance mới và có thể làm lại dữ liệu nghiệp vụ, thay vì xử lý đúng lần chạy đã bị giới hạn.

## 8. Quan hệ giữa startLimit và allowStartIfComplete

Mặc định, khi restart Job, Step đã `COMPLETED` thường được bỏ qua. `allowStartIfComplete(true)` yêu cầu Spring Batch chạy lại Step đó ngay cả khi Step đã hoàn tất ở JobExecution trước.

Hai cấu hình có vai trò riêng:

- `startLimit(n)` giới hạn tổng số lần Step được bắt đầu.
- `allowStartIfComplete(true)` cho phép Step đã hoàn thành được bắt đầu lại khi Job restart.

Ví dụ:

```java
return new StepBuilder("refreshReferenceStep", jobRepository)
        .tasklet(refreshReferenceTasklet, transactionManager)
        .allowStartIfComplete(true)
        .startLimit(3)
        .build();
```

Giả sử Step hoàn thành ở lần chạy đầu, nhưng một Step sau đó thất bại. Khi restart Job:

1. Nếu `allowStartIfComplete(false)` (mặc định), Step đã hoàn thành thường bị bỏ qua và không tiêu thụ thêm lần bắt đầu.
2. Nếu `allowStartIfComplete(true)`, Step được chạy lại và lần bắt đầu đó được tính vào giới hạn.
3. Nếu Step đã đạt `startLimit`, nó không được chạy lại dù `allowStartIfComplete(true)`.

Vì vậy, hai thuộc tính phải được cân nhắc cùng nhau. Không bật `allowStartIfComplete(true)` cho Step có side effect không idempotent chỉ để đảm bảo nó luôn chạy lại.

## 9. startLimit và restart của Job

Để Step được restart, Job phải cho phép restart. Job mặc định có thể restart nếu không cấu hình `preventRestart()`. Nếu Job được cấu hình không restartable, việc restart bị chặn ở cấp Job trước khi chính sách startLimit của Step có thể được áp dụng như mong đợi.

```java
return new JobBuilder("dailyJob", jobRepository)
        .start(importStep)
        .next(reconcileStep)
        .build();
```

Job không gọi `.preventRestart()`, nên vẫn có thể restart theo trạng thái và metadata. Mỗi Step có thể đặt startLimit khác nhau:

```java
importStep:      startLimit(5)
reconcileStep:   startLimit(2)
publishStep:     startLimit(1)
```

Điều này hữu ích khi các Step có chi phí hoặc tác dụng phụ khác nhau. Step import có thể cần nhiều lần phục hồi; Step publish có thể chỉ được phép bắt đầu một lần vì gửi thông báo hoặc bàn giao dữ liệu cần kiểm soát nghiêm ngặt.

Nếu Job đã `COMPLETED`, launch lại cùng identifying parameters thường bị từ chối vì JobInstance đã hoàn tất. `startLimit` không cho phép chạy lại một JobInstance đã hoàn tất. Muốn xử lý lại nghiệp vụ, cần một JobInstance mới với identifying parameter thể hiện yêu cầu reprocess có chủ đích.

## 10. Tình huống thực tế: Step gọi hệ thống bên ngoài

Giả sử Step gọi dịch vụ đối soát thanh toán. Mỗi lần gọi có thể tạo một yêu cầu xử lý tại hệ thống ngoài. Để giới hạn số lần bắt đầu Step trong cùng JobInstance, cấu hình:

```java
return new StepBuilder("paymentReconciliationStep", jobRepository)
        .tasklet(paymentReconciliationTasklet, transactionManager)
        .startLimit(2)
        .build();
```

Với giới hạn hai lần, Step được bắt đầu tối đa hai lần trong cùng JobInstance. Nhưng nếu lần đầu gọi API đã thành công rồi ứng dụng dừng trước khi Spring Batch ghi nhận Step hoàn tất, restart có thể gọi API lại. `startLimit(2)` chỉ cho phép tối đa hai lần bắt đầu; nó không biết lần gọi đầu đã thành công ở hệ thống ngoài hay chưa.

Để an toàn, hãy gửi một idempotency key ổn định, ví dụ `reconcile:<businessDate>:<accountGroup>`, cho mọi lần gọi. Hệ thống nhận cần lưu key và trả lại kết quả cũ nếu key đã được xử lý. Khi đó, lần gọi lại không tạo thêm một yêu cầu đối soát mới.

Nếu hệ thống ngoài không hỗ trợ idempotency key, có thể lưu request ID và trạng thái vào database/outbox, sau đó tra cứu kết quả trước khi gửi lại. Cần phân biệt timeout do không nhận phản hồi với thất bại chắc chắn; timeout không chứng minh hệ thống ngoài chưa thực hiện thao tác.

## 11. Tình huống thực tế: Step đã hoàn thành nhưng Job thất bại ở Step sau

Giả sử Job gồm ba Step:

```text
dailyImportJob
   |
   v
importStep (startLimit=3)
   |
   v
publishStep (startLimit=1)
```

`importStep` hoàn tất, nhưng `publishStep` thất bại. Khi restart Job:

- Mặc định, `importStep` đã hoàn thành sẽ được bỏ qua.
- `publishStep` có thể được bắt đầu lại nếu còn trong giới hạn.
- Nếu `importStep` có `allowStartIfComplete(true)`, nó sẽ chạy lại và tiêu thụ thêm một lần start.
- Nếu `publishStep` có `startLimit(1)` và lần đầu đã bắt đầu rồi thất bại, lần restart không thể bắt đầu Step này lần nữa.

Đây là lý do cần đặt giới hạn theo rủi ro và khả năng phục hồi của từng Step, không sao chép một giá trị startLimit cho tất cả Step.

## 12. Cách theo dõi số lần Step đã bắt đầu

`JobRepository` lưu các `StepExecution` thuộc từng JobInstance. Có thể dùng `JobExplorer` để tra cứu JobInstance và các JobExecution, rồi đọc các StepExecution theo tên Step để xem lịch sử.

Ví dụ khái quát:

```java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

public long countStepExecutions(
        JobExplorer jobExplorer,
        JobInstance jobInstance,
        String stepName) {

    long count = 0;
    for (JobExecution jobExecution :
            jobExplorer.getJobExecutions(jobInstance)) {
        count += jobExecution.getStepExecutions().stream()
                .filter(step -> step.getStepName().equals(stepName))
                .count();
    }
    return count;
}
```

Đây là ví dụ minh họa việc tổng hợp lịch sử StepExecution của JobInstance. Khi cần kiểm tra số lần start trong ứng dụng thực tế, hãy dùng đúng API `JobExplorer` của phiên bản Spring Batch đang sử dụng và tính cả các execution lịch sử liên quan. Không nên tự sửa các bảng `BATCH_STEP_EXECUTION` để đặt lại bộ đếm.

Các thông tin hữu ích để log hoặc giám sát:

- JobInstance ID và identifying JobParameters.
- JobExecution ID hiện tại.
- Step name và StepExecution ID.
- Trạng thái, thời gian bắt đầu/kết thúc và exception.
- Start limit cấu hình cho Step.
- Số StepExecution lịch sử của Step trong JobInstance.

Nếu cần báo cáo giới hạn qua nhiều JobInstance, hãy lưu metric nghiệp vụ riêng vì `startLimit` được áp dụng theo từng JobInstance.

## 13. Kiểm thử startLimit

Nên dùng integration test với JobRepository bền vững trong test context để xác nhận Spring Batch thực sự chặn lần bắt đầu vượt giới hạn. Unit test chỉ gọi Tasklet trực tiếp sẽ không kiểm tra được bộ đếm StepExecution và metadata restart.

Một kịch bản kiểm thử với `startLimit(2)`:

1. Tạo JobParameters có identifying key cố định, ví dụ `businessDate=2026-11-15`.
2. Launch Job lần đầu; làm Tasklet thất bại có kiểm soát và xác nhận Step đã bắt đầu lần thứ nhất.
3. Restart cùng JobInstance bằng cùng identifying parameters; làm Tasklet thất bại lần nữa và xác nhận Step đã bắt đầu lần thứ hai.
4. Restart lần thứ ba với cùng JobInstance.
5. Xác nhận Step không được gọi lại, JobExecution mới thất bại và failure exception có `StartLimitExceededException`.

Có thể dùng `JobLauncherTestUtils` để launch Job và `JobExplorer` để tra cứu lịch sử. Nên dùng một service giả lập có thể điều khiển kết quả để tạo hai lần thất bại, nhưng không thay đổi identifying JobParameters giữa các lần restart.

Ví dụ assertion về loại exception sau khi lấy JobExecution tương ứng:

```java
assertTrue(jobExecution.getAllFailureExceptions().stream()
        .anyMatch(StartLimitExceededException.class::isInstance));
```

Tùy launcher và cách test khởi chạy Job, JobExecution có thể được trả về với trạng thái `FAILED` thay vì ném exception trực tiếp cho test caller. Hãy kiểm tra metadata qua JobRepository/JobExplorer để xác nhận lỗi và số lần Tasklet thực sự được gọi.

### Kiểm thử allowStartIfComplete

Một test khác nên xác nhận Step hoàn thành có chạy lại hay không:

- Cấu hình Step A hoàn tất và Step B thất bại.
- Restart cùng JobInstance.
- Với Step A mặc định, xác nhận Tasklet/Writer của A không được gọi lần nữa.
- Với `allowStartIfComplete(true)`, xác nhận A được gọi lại nếu chưa đạt startLimit.
- Khi số lần bắt đầu đã đạt startLimit, xác nhận A không được gọi thêm.

## 14. Cách chọn giá trị startLimit

Không nên đặt cùng một giới hạn cho mọi Step. Giá trị phù hợp phụ thuộc khả năng phục hồi và tác dụng phụ của Step:

| Loại Step | Hướng cân nhắc |
|---|---|
| Đọc và import file có checkpoint tốt | Có thể cho phép nhiều lần restart; đặt giới hạn đủ cho vận hành. |
| Tính toán thuần, không side effect | Có thể dùng giới hạn cao hoặc mặc định nếu chi phí chạy lại chấp nhận được. |
| Gọi API ngoài có idempotency key | Có thể cho phép một số lần restart, song song với retry/backoff ở mức request. |
| Gửi file hoặc thông điệp không có cơ chế chống trùng | Giới hạn thấp hơn và bổ sung trạng thái bàn giao/idempotency trước khi cho phép chạy lại. |
| Tác vụ chỉ được thực hiện một lần theo nghiệp vụ | Có thể đặt `startLimit(1)`, nhưng cần quy trình xử lý thủ công nếu lần đầu thất bại. |

Giới hạn thấp có thể ngăn việc lặp vô hạn nhưng cũng có thể khiến Job không thể tự phục hồi sau một lỗi hạ tầng tạm thời. Hãy xem startLimit như một hàng rào vận hành, không phải biện pháp thay thế cho retry, timeout, idempotency hoặc sửa nguyên nhân lỗi.

## 15. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ `startLimit(3)` cho phép ba lần restart sau lần đầu | Thực tế giới hạn bao gồm cả lần bắt đầu đầu tiên. | Tính tổng số lần Step được bắt đầu, gồm lần đầu và các lần restart. |
| Dùng startLimit để giới hạn retry từng item | Không kiểm soát số lần retry trong chunk. | Dùng `retryLimit()` cho retry policy. |
| Đổi identifying JobParameters để vượt giới hạn | Tạo JobInstance mới và có thể xử lý dữ liệu lại. | Giữ cùng parameters khi restart; tạo instance mới chỉ khi có yêu cầu reprocess rõ ràng. |
| Cho rằng startLimit biết API ngoài đã thành công hay chưa | Side effect có thể đã xảy ra trước khi Step ghi nhận hoàn tất. | Dùng idempotency key hoặc trạng thái request bền vững. |
| Bật allowStartIfComplete mà không xét startLimit | Step đã hoàn thành có thể chạy lại đến khi chạm giới hạn. | Đánh giá hai cấu hình cùng nhau và kiểm thử restart. |
| Dùng startLimit như giới hạn toàn hệ thống | Mỗi JobInstance có lịch sử Step riêng. | Dùng bảng điều phối/unique constraint cho giới hạn toàn cục hoặc theo ngày. |
| Đặt startLimit quá thấp | Lỗi tạm thời có thể làm Job không thể restart. | Chọn giá trị dựa trên SLA, vận hành và khả năng phục hồi. |
| Tự sửa bảng BATCH_* để reset giới hạn | Metadata có thể mất nhất quán và làm hỏng restart. | Dùng API Spring Batch và quy trình vận hành được kiểm soát. |

## Kết luận

`startLimit` giới hạn số lần một Step được phép bắt đầu trong cùng một JobInstance. Giới hạn tính cả lần chạy đầu tiên và các lần restart; khi vượt ngưỡng, Spring Batch từ chối bắt đầu Step và phát sinh `StartLimitExceededException`. Nó khác `retryLimit` và `skipLimit`: hai giới hạn kia xử lý lỗi item bên trong Step, còn startLimit kiểm soát số lần StepExecution được khởi chạy. Cần cân nhắc `allowStartIfComplete(true)`, chính sách restart của Job, idempotency của side effect và cách vận hành khi hết giới hạn. Hãy kiểm thử bằng nhiều lần launch/restart cùng identifying JobParameters và xác nhận Step không chạy vượt số lần đã cấu hình.
