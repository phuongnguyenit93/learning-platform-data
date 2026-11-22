# Chọn policy theo latency, throughput và độ tin cậy

Trong Spring Batch, commit policy quyết định khi nào một nhóm item được kết thúc và transaction của chunk được commit. Với chunk-oriented Step, lựa chọn thường bắt đầu từ commit interval: mỗi chunk xử lý bao nhiêu item trước khi ghi và commit. Giá trị này ảnh hưởng trực tiếp đến thời gian phản hồi của từng phần dữ liệu, throughput, thời gian giữ lock, chi phí transaction và lượng công việc có thể phải làm lại khi lỗi.

Không có một commit interval tối ưu cho mọi Job. Job cần dữ liệu xuất hiện nhanh cho hệ thống downstream thường ưu tiên chunk nhỏ; Job xử lý khối lượng lớn trong cửa sổ batch có thể ưu tiên chunk lớn hơn để giảm overhead. Job cần restart và độ tin cậy cao phải cân bằng cả hai yếu tố, đồng thời thiết kế reader/writer có checkpoint và khả năng xử lý lặp an toàn.

## 1. Commit policy trong chunk processing

Trong chunk-oriented processing, Spring Batch đọc và xử lý item cho đến khi chunk đạt điều kiện kết thúc, sau đó gọi Writer và commit transaction. Với commit interval cố định, số item trong một chunk được xác định bằng cấu hình `chunk(size, transactionManager)`.

```text
Chunk 1: BEGIN -> read/process 500 items -> write -> COMMIT
Chunk 2: BEGIN -> read/process 500 items -> write -> COMMIT
Chunk 3: BEGIN -> read/process 500 items -> write -> COMMIT
```

Ví dụ, `chunk(500, transactionManager)` thường có nghĩa một chunk chứa tối đa 500 item được đọc và xử lý trước khi ghi. Chunk cuối có thể ít hơn nếu nguồn dữ liệu đã hết. Nếu transaction của chunk thất bại, các thay đổi thuộc transaction đó có thể rollback; những chunk đã commit trước đó vẫn được giữ.

Commit policy không phải là lịch chạy Job. Nó không quyết định Job bắt đầu lúc nào, cũng không quyết định Job có chạy đồng bộ hay bất đồng bộ. Policy xác định ranh giới giữa các đơn vị commit trong một Step.

## 2. Ba yếu tố cần cân bằng

### Latency

Latency trong batch có thể được nhìn ở nhiều cấp độ:

- Thời gian từ khi Job bắt đầu đến khi có kết quả đầu tiên được commit.
- Thời gian một chunk ở trạng thái đang xử lý trước khi dữ liệu được commit.
- Độ trễ từ khi dữ liệu nguồn xuất hiện đến khi kết quả có thể được hệ thống khác đọc.

Chunk nhỏ thường giúp dữ liệu được commit thành nhiều đợt nhỏ và sớm hơn. Điều này hữu ích khi downstream cần nhìn thấy kết quả từng phần hoặc khi Job phải chia sẻ database với giao dịch online. Chunk lớn có thể làm tăng thời gian chờ trước khi dữ liệu của chunk được commit.

### Throughput

Throughput là lượng công việc hoàn thành trong một đơn vị thời gian, ví dụ số bản ghi/giây. Chunk lớn có thể tăng throughput bằng cách giảm số lần commit, round trip và overhead quản lý transaction. Tuy nhiên, chunk quá lớn cũng có thể làm giảm throughput vì transaction giữ lock lâu, tăng bộ nhớ, gây áp lực cho database và làm các Job khác phải chờ.

Do đó, throughput không nhất thiết tăng tuyến tính theo commit interval. Cần đo trên workload thực tế và hệ thống database thực tế.

### Độ tin cậy

Độ tin cậy thể hiện khả năng giữ dữ liệu nhất quán, phát hiện lỗi, phục hồi và tiếp tục xử lý mà không mất hoặc nhân đôi dữ liệu.

- Chunk nhỏ giới hạn lượng dữ liệu chưa commit và thường giảm phạm vi rollback.
- Chunk lớn có thể khiến một lỗi làm phải thử lại nhiều item hơn và giữ transaction lâu hơn.
- Commit thường xuyên tạo checkpoint dày hơn, nhưng chỉ có ích khi reader lưu trạng thái và writer được thiết kế an toàn khi restart.
- Với retry, item trong chunk có thể được xử lý lại; processor và writer cần chịu được việc thử lại.

## 3. Chunk nhỏ và chunk lớn: trade-off

| Tiêu chí | Chunk nhỏ | Chunk lớn |
|---|---|---|
| Thời điểm commit | Commit thường xuyên hơn | Chờ nhiều item hơn mới commit |
| Transaction duration | Thường ngắn hơn | Thường dài hơn |
| Commit overhead | Nhiều lần commit, overhead cao hơn | Ít lần commit, overhead thấp hơn |
| Bộ nhớ | Thường giữ ít item hơn | Giữ nhiều item trong chunk hơn |
| Lock và tranh chấp | Thường giảm thời gian giữ lock | Có thể giữ lock lâu hơn |
| Phạm vi rollback | Ít item hơn trong một chunk | Nhiều item hơn có thể phải xử lý lại |
| Checkpoint | Có nhiều điểm commit hơn | Ít điểm commit hơn |
| Throughput | Có thể thấp nếu overhead chiếm tỷ lệ lớn | Có thể cao hơn đến một ngưỡng phù hợp |
| Độ trễ dữ liệu từng phần | Thường thấp hơn | Thường cao hơn |

Không nên kết luận chunk nhỏ luôn đáng tin cậy hơn hoặc chunk lớn luôn nhanh hơn. Một writer ghi từng item bằng nhiều câu lệnh SQL có thể hưởng lợi từ batch insert và chunk lớn hơn. Một Job cập nhật các bảng đang được giao dịch online sử dụng có thể cần chunk nhỏ để giảm lock contention.

## 4. Chọn commit interval theo đặc điểm workload

Một số tình huống thường gặp:

| Đặc điểm Job | Hướng chọn ban đầu | Lý do |
|---|---|---|
| Dữ liệu cần xuất hiện nhanh cho downstream | Chunk nhỏ hoặc vừa | Commit kết quả theo đợt ngắn, giảm độ trễ quan sát. |
| Import số lượng lớn, writer hỗ trợ batch insert | Chunk vừa hoặc lớn | Giảm số lần round trip và commit. |
| Database dùng chung với ứng dụng online | Chunk nhỏ hoặc vừa | Giảm thời gian giữ lock và ảnh hưởng đến request. |
| Xử lý item nặng, thời gian mỗi item không đồng đều | Chunk vừa hoặc policy có giới hạn thời gian | Tránh transaction kéo dài chỉ vì một nhóm item quá lớn. |
| Yêu cầu restart nhanh sau lỗi | Chunk nhỏ hoặc vừa, reader có checkpoint | Giới hạn phạm vi làm lại sau rollback. |
| Item có tác dụng phụ ngoài database | Chunk theo lô nghiệp vụ, kèm idempotency/outbox | Kiểm soát việc gửi hoặc ghi lặp khi retry. |

Các giá trị cụ thể phải được benchmark. Có thể bắt đầu bằng một giá trị vừa phải, chẳng hạn 100 hoặc 500 item, sau đó so sánh với mức nhỏ hơn và lớn hơn. Đây chỉ là điểm bắt đầu để thử nghiệm, không phải quy tắc chung cho mọi database hoặc loại item.

## 5. Cấu hình commit interval cố định

Với Spring Batch 5 trở lên, cấu hình commit interval trực tiếp trong `StepBuilder`:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportJobConfig {

    @Bean
    public Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<InputRecord> reader,
            ItemProcessor<InputRecord, OutputRecord> processor,
            ItemWriter<OutputRecord> writer) {

        return new StepBuilder("importStep", jobRepository)
                .<InputRecord, OutputRecord>chunk(500, transactionManager)
                .reader(reader)
                .processor(processor)
                .writer(writer)
                .build();
    }
}
```

Ở đây, 500 là commit interval. Mỗi chunk thành công sẽ được commit riêng. Để thử một policy khác, có thể thay 500 bằng 100 hoặc 1.000 rồi đo throughput, chunk duration, lock wait và tỷ lệ rollback trên cùng một tập dữ liệu.

## 6. Dùng CompletionPolicy khi chỉ đếm item là chưa đủ

Commit interval cố định dựa trên số item. Trong một số Job, thời gian xử lý mỗi item khác nhau đáng kể. Ví dụ, một item có thể xử lý trong vài mili giây, còn item khác cần gọi nhiều bước tính toán hoặc truy cập dữ liệu bổ sung. Khi đó, 500 item có thể tạo chunk rất ngắn ở một phần dữ liệu nhưng lại tạo transaction kéo dài ở phần khác.

Spring Batch hỗ trợ `CompletionPolicy` để xác định khi nào chunk kết thúc. `SimpleCompletionPolicy` là policy theo số lượng item:

```java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.SimpleCompletionPolicy;

CompletionPolicy completionPolicy = new SimpleCompletionPolicy(500);

return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(completionPolicy, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
```

Với workload có thời gian xử lý không đồng đều, có thể dùng policy theo thời gian hoặc policy kết hợp để kết thúc chunk theo giới hạn phù hợp. Ví dụ `TimeoutTerminationPolicy` có thể giới hạn thời gian lặp của một chunk:

```java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.TimeoutTerminationPolicy;

CompletionPolicy completionPolicy = new TimeoutTerminationPolicy(5_000);

return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(completionPolicy, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
```

Giá trị `5_000` là 5 giây. Khi dùng policy theo thời gian, cần hiểu rằng nó quyết định thời điểm kết thúc vòng lặp; nó không nhất thiết ngắt cưỡng bức một lần `read()`, `process()` hoặc `write()` đang bị treo. Nếu item xử lý rất nhanh, chỉ giới hạn thời gian có thể gom nhiều item vào một chunk; có thể kết hợp điều kiện số lượng và thời gian để giới hạn cả hai chiều.

Policy theo thời gian cũng không thay thế transaction timeout. Một policy kết thúc chunk sau một khoảng thời gian và transaction timeout là hai cơ chế khác nhau: một cơ chế quyết định chunk dừng nhận thêm item, cơ chế kia đặt giới hạn thời gian cho transaction. Cần thiết kế và kiểm tra cả hai nếu Job có yêu cầu thời gian nghiêm ngặt.

## 7. Transaction timeout và isolation level

Commit interval quyết định số lượng item trong chunk; transaction attribute quyết định các thuộc tính của transaction như timeout và isolation level.

Ví dụ cấu hình timeout và isolation cho chunk Step:

```java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.interceptor.DefaultTransactionAttribute;

DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
transactionAttribute.setTimeout(60);
transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);

return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .transactionAttribute(transactionAttribute)
        .build();
```

Ví dụ đặt timeout 60 giây và isolation `READ_COMMITTED`; giá trị cần được điều chỉnh theo database, transaction manager và SLA thực tế. Có thể khai báo biến là `DefaultTransactionAttribute` ngay từ đầu để tránh ép kiểu:

```java
DefaultTransactionAttribute transactionAttribute =
        new DefaultTransactionAttribute();
transactionAttribute.setTimeout(60);
transactionAttribute.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
```

Một số lưu ý:

- Timeout không phải là thời gian mục tiêu để chunk hoàn thành. Đây là giới hạn transaction; cách thực thi timeout phụ thuộc transaction manager và resource.
- Timeout transaction không đảm bảo hủy một lời gọi HTTP hoặc đoạn xử lý CPU đang chạy.
- Isolation level cao hơn có thể tăng tính cô lập nhưng cũng tăng lock hoặc chi phí database. Chỉ dùng mức nghiêm ngặt hơn khi quy tắc nghiệp vụ yêu cầu.
- Không tăng timeout để che việc chunk quá lớn hoặc một transaction đang chờ dịch vụ ngoài quá lâu.

## 8. Kết hợp commit policy với retry và skip

Commit policy ảnh hưởng đến cách phục hồi khi một item gặp lỗi. Với fault-tolerant Step, Spring Batch có thể rollback chunk rồi retry thao tác hoặc skip item theo cấu hình.

```java
return new StepBuilder("importStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(300, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidRecordException.class)
        .skipLimit(20)
        .build();
```

Trong ví dụ, lỗi truy cập dữ liệu tạm thời có thể được retry tối đa theo giới hạn cấu hình; bản ghi sai nghiệp vụ có thể được skip trong giới hạn cho phép. Nếu hết retry hoặc gặp lỗi không được xử lý, Step có thể thất bại.

Khi chọn chunk size, cần tính đến số lần item có thể được thử lại và chi phí làm lại chunk. Chunk quá lớn có thể khiến một lỗi tạm thời làm phát sinh nhiều công việc lặp lại. Chunk quá nhỏ lại tăng overhead khi retry và commit. Processor nên hạn chế tác dụng phụ, còn writer cần idempotent hoặc có cơ chế chống ghi trùng khi phù hợp.

Filter và skip cũng cần được phân biệt: processor trả `null` làm tăng `filterCount`; exception được cấu hình skip làm tăng bộ đếm skip tương ứng. Không nên tăng skip limit chỉ để Job luôn hoàn tất nếu dữ liệu sai cần được điều tra.

## 9. Độ tin cậy và khả năng restart

Mỗi lần commit thành công là một mốc dữ liệu bền vững. Nếu Job thất bại ở chunk tiếp theo, những chunk đã commit vẫn còn. Khi restart cùng JobInstance, Spring Batch có thể sử dụng `ExecutionContext` để khôi phục trạng thái reader và tiếp tục từ checkpoint phù hợp.

```text
JobExecution #1: FAILED
  Chunk 1: COMMITTED
  Chunk 2: COMMITTED
  Chunk 3: ROLLED BACK
  Chunk 4: chưa chạy

Restart cùng identifying JobParameters
  |
  v
JobExecution #2
  Khôi phục từ checkpoint đã lưu
  Tiếp tục phần công việc còn lại
```

Để commit policy hỗ trợ độ tin cậy thực sự:

1. Reader phải hỗ trợ lưu trạng thái nếu muốn tiếp tục từ checkpoint.
2. Writer phải chịu được việc item được xử lý lại khi retry hoặc restart.
3. Identifying JobParameters phải đại diện ổn định cho đơn vị công việc.
4. Các tác dụng phụ ngoài transaction phải có idempotency key, outbox hoặc cơ chế bù trừ.
5. Không đặt transaction bao trùm toàn Job khiến các chunk tưởng đã commit nhưng thực tế chưa commit độc lập.

Chunk nhỏ hơn có thể giới hạn số item cần làm lại, nhưng nếu reader không lưu state hoặc writer không an toàn khi chạy lại, việc commit thường xuyên không tự bảo đảm restart chính xác.

## 10. Ví dụ chọn policy cho ba loại Job

### Job nhập file lớn trong cửa sổ ban đêm

Mục tiêu chính là throughput. File có hàng triệu dòng, writer ghi batch vào database và ít có giao dịch online cạnh tranh. Có thể bắt đầu thử nghiệm với chunk 500 hoặc 1.000, sau đó đo thời gian ghi, commit latency, bộ nhớ và lock. Nếu chunk lớn hơn tiếp tục cải thiện throughput mà không làm tăng lỗi hoặc thời gian rollback đáng kể, có thể giữ giá trị lớn hơn.

### Job đồng bộ dữ liệu gần thời gian thực

Mục tiêu là latency thấp. Downstream cần nhìn thấy kết quả sớm sau khi item được xử lý. Chunk 10, 25 hoặc 50 có thể là điểm bắt đầu thử nghiệm, tùy chi phí commit và lượng dữ liệu. Nên ưu tiên thời gian từ khi đọc đến khi commit và tránh transaction giữ lock lâu.

### Job cập nhật bảng dùng chung với hệ thống online

Mục tiêu là độ tin cậy và giảm ảnh hưởng đến giao dịch online. Chunk vừa hoặc nhỏ giúp giảm thời gian giữ lock và giới hạn phạm vi rollback. Cần theo dõi lock wait, deadlock, transaction duration và connection pool. Nếu hệ thống online bị ảnh hưởng, có thể giảm chunk size, giới hạn concurrency hoặc chạy batch ngoài giờ cao điểm.

| Loại Job | Ưu tiên | Hướng cấu hình ban đầu để benchmark |
|---|---|---|
| Import lớn, ít cạnh tranh | Throughput | Chunk 500–1.000, writer batch-enabled |
| Đồng bộ cần kết quả sớm | Latency | Chunk 10–50 |
| Cập nhật database dùng chung | Reliability và isolation | Chunk 50–200, theo dõi lock và rollback |

Các khoảng trên chỉ là ví dụ khởi đầu. Kích thước item, loại database, chỉ mục, câu SQL, network, processor và concurrency có thể làm kết quả khác nhau đáng kể.

## 11. Đo lường để tinh chỉnh commit policy

Không nên chọn chunk size chỉ dựa vào cảm giác hoặc một lần chạy. Hãy dùng cùng dữ liệu đầu vào, cùng cấu hình môi trường và so sánh một số giá trị.

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa | Dùng để quyết định |
|---|---|---|
| Throughput (items/second) | Số item hoàn thành trong một giây | Chunk lớn có cải thiện hiệu suất thực tế không? |
| Chunk duration p50/p95 | Thời gian xử lý chunk điển hình và ở nhóm chậm | Chunk có quá dài hoặc biến động lớn không? |
| Commit latency | Thời gian commit transaction | Database có đang chịu overhead hoặc chậm ghi không? |
| Rollback/retry count | Số lần rollback và thử lại | Chunk lớn có làm tăng chi phí phục hồi không? |
| Lock wait/deadlock | Mức tranh chấp database | Batch có ảnh hưởng giao dịch khác không? |
| Connection pool usage | Số connection đang hoạt động và chờ | Transaction có giữ connection quá lâu không? |
| Heap/GC | Bộ nhớ và chi phí garbage collection | Chunk có giữ quá nhiều item trong memory không? |
| End-to-end lag | Độ trễ từ nguồn đến kết quả được commit | Có đáp ứng yêu cầu latency không? |

Một quy trình benchmark thực tế:

1. Chọn một tập dữ liệu đại diện, bao gồm cả item bình thường và item có thời gian xử lý dài.
2. Chạy với chunk nhỏ, ví dụ 100, ghi nhận throughput, latency, lock và memory.
3. Chạy với chunk vừa và lớn, ví dụ 500 và 1.000, trong cùng điều kiện.
4. Thử một lần có lỗi có kiểm soát để quan sát rollback và thời gian restart.
5. So sánh kết quả với SLA của Job và mức ảnh hưởng đến database dùng chung.
6. Chọn cấu hình đạt yêu cầu latency và reliability, sau đó mới tối ưu throughput trong giới hạn đó.

## 12. Những lỗi thường gặp khi chọn commit policy

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chọn chunk size lớn nhất có thể | Transaction dài, nhiều memory, lock và phạm vi rollback lớn. | Benchmark theo workload; tăng dần đến khi lợi ích không còn đáng kể. |
| Chọn chunk quá nhỏ | Commit overhead cao và throughput thấp. | Đo commit latency và thử tăng interval nếu database còn dư tài nguyên. |
| Chỉ đo tổng thời gian Job | Không thấy chunk chậm, lock wait hoặc rollback tăng. | Thu thập chunk duration, commit latency và database metrics. |
| Nhầm transaction timeout với chunk completion policy | Timeout không nhất thiết kết thúc chunk theo cách mong muốn. | Phân biệt điều kiện kết thúc chunk với giới hạn transaction. |
| Retry nhưng writer không idempotent | Dữ liệu có thể bị ghi trùng sau khi rollback/retry. | Dùng khóa nghiệp vụ, upsert có kiểm soát hoặc cơ chế chống trùng. |
| Tăng skip limit để tránh FAILED | Dữ liệu sai có thể bị bỏ qua mà không được điều tra. | Xác định exception nào được skip và lưu lại bản ghi lỗi. |
| Giữ transaction mở khi gọi HTTP | Connection và lock bị giữ trong lúc chờ mạng; request ngoài không rollback cùng DB. | Dùng outbox hoặc tách tác vụ gửi sang Step riêng. |

## Kết luận

Chọn commit policy là bài toán cân bằng giữa latency, throughput và độ tin cậy. Chunk nhỏ thường commit sớm, giữ transaction ngắn và giới hạn phạm vi rollback; chunk lớn giảm overhead commit nhưng có thể giữ lock lâu, tốn bộ nhớ và làm tăng lượng công việc phải thử lại. Bắt đầu bằng một commit interval hợp lý, đo throughput, chunk duration, commit latency, lock wait, memory và hành vi restart trên dữ liệu thực tế. Kết hợp commit interval với transaction timeout, retry/skip và checkpoint phù hợp sẽ giúp Step đáp ứng SLA mà vẫn giữ dữ liệu nhất quán.
