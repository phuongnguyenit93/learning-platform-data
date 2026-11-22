# Commit lớn giảm transaction overhead trong Spring Batch

Trong chunk-oriented processing, Spring Batch gom nhiều item vào một chunk rồi xử lý và commit chúng trong cùng một transaction. Giá trị chunk size (thường được gọi là commit interval) quyết định bao nhiêu item đầu vào được xử lý trước mỗi lần commit. Khi tăng giá trị này, job thường cần ít transaction hơn để xử lý cùng một lượng dữ liệu, nhờ đó giảm chi phí bắt đầu, hoàn tất và ghi nhận transaction.

Tuy nhiên, chunk lớn không phải lúc nào cũng nhanh hơn. Transaction kéo dài hơn, giữ lock và connection lâu hơn, dùng nhiều bộ nhớ hơn, và khi lỗi xảy ra thì phạm vi rollback hoặc phần việc phải xử lý lại có thể lớn hơn. Cần chọn commit interval dựa trên phép đo thực tế và đặc điểm của reader, processor, writer, database cùng yêu cầu phục hồi.

## 1. Commit interval và kích thước chunk

Một chunk là nhóm item được đọc, xử lý và ghi như một đơn vị transaction. Với Spring Batch 5, có thể cấu hình kích thước chunk bằng `chunk(size, transactionManager)`:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(1000, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Trong ví dụ, `1000` là số item đầu vào tối đa được gom vào một chunk trước khi commit. Spring Batch đọc và xử lý các item của chunk, chuyển output còn lại cho writer rồi commit transaction. Nếu nguồn kết thúc trước khi đủ 1000 item, chunk cuối vẫn được xử lý với số item còn lại.

Commit interval không phải số transaction cho toàn job. Với chunk step thông thường, mỗi chunk có transaction riêng. Job có nhiều step và mỗi step có thể có nhiều chunk transaction.

```text
Chunk 1: item 1..1000       -> transaction 1 -> COMMIT
Chunk 2: item 1001..2000   -> transaction 2 -> COMMIT
Chunk 3: item 2001..3000   -> transaction 3 -> COMMIT
...
```

## 2. Vì sao transaction tạo ra overhead?

Một transaction có chi phí ngoài thời gian thực hiện câu lệnh nghiệp vụ. Tùy database và transaction manager, các chi phí có thể gồm:

- Bắt đầu transaction và thiết lập trạng thái làm việc.
- Thực hiện các thao tác quản lý transaction và đồng bộ resource.
- Flush thay đổi từ ORM hoặc persistence context xuống database.
- Ghi log transaction/redo log và bảo đảm durability khi commit.
- Gửi commit request qua driver và chờ database xác nhận.
- Cập nhật metadata của step và execution context trong Spring Batch.
- Giải phóng lock, connection hoặc tài nguyên transaction sau commit.

Một số chi phí là cố định hoặc gần cố định cho mỗi transaction, không phụ thuộc tuyến tính vào số item trong chunk. Khi mỗi chunk chỉ có một hoặc vài item, các chi phí này xuất hiện thường xuyên. Nếu gom nhiều item hơn vào cùng transaction, chi phí theo transaction được phân bổ cho nhiều item hơn.

Ví dụ, giả sử một job xử lý một triệu item và không có retry:

| Commit interval | Số chunk/transaction xấp xỉ |
| ---: | ---: |
| 10 | 100.000 |
| 100 | 10.000 |
| 1.000 | 1.000 |
| 5.000 | 200 |

Số liệu trên chỉ là phép tính `ceil(totalItems / chunkSize)` cho một lượt chạy thành công. Retry, skip, partitioning, flow hoặc các lần restart có thể làm số lần thực tế khác đi.

Nếu transaction overhead là nút thắt, tăng chunk size có thể giảm đáng kể số lần commit và metadata update. Nhưng nếu thời gian xử lý từng item hoặc truy vấn bên trong writer chiếm gần hết thời gian, giảm số transaction có thể chỉ cải thiện tổng thời gian một phần nhỏ.

## 3. Mô hình chi phí đơn giản

Có thể hình dung thời gian chạy của một job như tổng thời gian xử lý item và chi phí phát sinh theo chunk:

\[
T(C) \approx N \cdot t_{item} + \left\lceil\frac{N}{C}\right\rceil \cdot t_{tx} + T_{other}
\]

Trong đó:

- `N` là tổng số item.
- `C` là commit interval/chunk size.
- `t_item` là thời gian xử lý trung bình cho một item.
- `t_tx` là chi phí trung bình gắn với một transaction chunk.
- `T_other` gồm chi phí đọc/ghi, truy vấn, network, scheduling và các phần khác.

Khi tăng `C`, số hạng transaction giảm vì số chunk ít đi. Mô hình này giúp giải thích xu hướng, không phải công thức dự đoán chính xác. Trên thực tế, `t_tx` có thể tăng khi transaction lớn hơn do lock duration, flush nhiều entity, log volume, index maintenance hoặc contention. `T_other` cũng có thể thay đổi theo kích thước batch mà writer gửi xuống database.

Vì vậy, không nên chọn chunk size chỉ bằng cách tìm số lớn nhất. Mục tiêu là tìm vùng mà throughput tăng đáng kể trong khi transaction vẫn nằm trong giới hạn tài nguyên và khả năng phục hồi.

## 4. So sánh chunk nhỏ và chunk lớn

| Khía cạnh | Chunk nhỏ | Chunk lớn |
| --- | --- | --- |
| Số transaction | Nhiều | Ít hơn |
| Commit/metadata overhead | Cao hơn do commit thường xuyên | Được phân bổ trên nhiều item hơn |
| Thời gian giữ lock | Thường ngắn hơn | Có thể dài hơn |
| Connection và transaction resource | Được giải phóng thường xuyên hơn | Có thể bị giữ lâu hơn trong chunk |
| Bộ nhớ cho item đang xử lý | Thường ít hơn | Thường nhiều hơn |
| Phạm vi rollback | Ít item hơn | Có thể nhiều item hơn |
| Tần suất checkpoint | Thường xuyên hơn | Thưa hơn |
| Thời gian phục hồi sau lỗi | Có thể ít việc phải đọc lại hơn | Có thể phải xử lý lại phần lớn chunk chưa commit |
| Throughput | Có thể bị giới hạn bởi overhead commit | Có thể tốt hơn nếu overhead là nút thắt và tài nguyên đủ |

Chunk nhỏ hữu ích khi item lớn, transaction cần ngắn, hoặc yêu cầu phục hồi sát. Chunk lớn hữu ích khi chi phí commit đáng kể, writer hỗ trợ ghi theo lô và database có thể xử lý transaction lớn mà không gây lock contention hoặc áp lực log quá mức.

## 5. Ví dụ tăng commit interval

Giả sử step nhập 500.000 đơn hàng. Ban đầu, commit interval là 50:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(50, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .build();
```

Trong một lượt chạy thành công, số chunk xấp xỉ:

\[
500.000 / 50 = 10.000\text{ chunks}
\]

Nếu tăng lên 500:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(500, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .build();
```

Số chunk xấp xỉ còn 1.000. Nếu mỗi transaction có overhead đáng kể, thay đổi này có thể giảm thời gian tổng thể. Kết quả thực tế còn phụ thuộc writer có dùng batch insert/update, thời gian xử lý từng đơn hàng, index, constraint và tải đồng thời trên database.

Khi thay đổi chunk size, hãy kiểm tra dữ liệu đầu ra và các bộ đếm `readCount`, `writeCount`, `filterCount`, `skipCount` để xác nhận số item xử lý không thay đổi ngoài dự kiến.

## 6. Tăng chunk size có thể cải thiện batching của writer

Một số writer ghi dữ liệu hiệu quả hơn khi nhận nhiều item trong một lần gọi. Ví dụ, writer JDBC có thể gửi batch statement thay vì thực hiện một round trip cho từng item. Khi chunk lớn hơn, một lần gọi writer có thể chứa nhiều item hơn và tận dụng batching tốt hơn.

Tuy nhiên, cần phân biệt hai khái niệm:

- **Chunk size/commit interval:** số item được gom trong một transaction chunk.
- **Database/JDBC batch size:** số statement hoặc parameter set mà driver/database thực thi theo một batch.

Hai giá trị có liên quan nhưng không nhất thiết giống nhau. Một chunk 2.000 item không đảm bảo driver gửi đúng một batch duy nhất; writer, ORM, driver hoặc cấu hình batch có thể chia thành nhiều đợt nhỏ. Ngược lại, một writer tùy chỉnh có thể tự gom dữ liệu theo lô độc lập với cách Spring Batch chia transaction.

Ví dụ với `JdbcBatchItemWriter`:

```java
@Bean
JdbcBatchItemWriter<OrderEntity> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderEntity>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order(order_id, amount)
            values (:id, :amount)
            """)
        .beanMapped()
        .build();
}
```

Writer nhận các item trong chunk và thực hiện batch update theo cách implementation hỗ trợ. Việc tăng chunk size có thể giảm số lần gọi writer, nhưng cần đo với driver/database thực tế. Cũng cần bảo đảm writer dùng cùng datasource và transaction manager của step nếu muốn thao tác ghi tham gia transaction chunk.

## 7. Đánh đổi về bộ nhớ

Trong quá trình xử lý chunk, framework phải giữ các item đang được gom và các output tương ứng cho đến khi writer hoàn tất. Chunk càng lớn, lượng object cần giữ trong bộ nhớ thường càng nhiều.

Nếu mỗi item chỉ chứa vài trường nhỏ, tăng từ 100 lên 500 có thể không đáng kể. Nhưng nếu item chứa payload lớn, danh sách lồng nhau, nội dung file hoặc object graph JPA phức tạp, chunk 10.000 có thể tạo áp lực heap đáng kể.

Các dấu hiệu cần theo dõi:

- Heap usage tăng theo kích thước chunk.
- Garbage collection thường xuyên hoặc pause dài.
- OutOfMemoryError khi xử lý các chunk lớn.
- Persistence context giữ quá nhiều entity chưa flush/clear.
- Writer tạo thêm bản sao collection hoặc object làm bộ nhớ tăng gấp nhiều lần.

Với JPA writer, cần xem xét persistence context và cách flush/clear entity. Tăng chunk size mà không kiểm soát số entity được quản lý có thể khiến bộ nhớ tăng mạnh. Nếu writer dùng JDBC batch, footprint có thể khác; hãy đo bằng dữ liệu có kích thước gần production.

## 8. Đánh đổi về lock, connection và transaction log

Transaction lớn có thể giữ lock lâu hơn vì các thay đổi được giữ đến khi commit. Điều này có thể làm tăng:

- Thời gian các transaction khác phải chờ lock.
- Khả năng deadlock khi nhiều job hoặc request cập nhật cùng dữ liệu.
- Dung lượng undo/redo hoặc transaction log cần giữ trước khi commit.
- Thời gian flush index và constraint ở cuối chunk.
- Thời gian giữ connection trong pool và áp lực lên connection pool.

Vì vậy, một job đơn lẻ có thể nhanh hơn với chunk lớn nhưng toàn hệ thống lại chậm hơn do các request trực tuyến phải chờ lock hoặc thiếu connection. Cần đánh giá trong bối cảnh tải đồng thời, không chỉ đo thời gian chạy batch khi database rảnh.

Nếu transaction gần chạm timeout, tăng chunk size có thể làm lỗi timeout xuất hiện thường xuyên hơn. Điều chỉnh timeout chỉ nên thực hiện sau khi hiểu thời gian xử lý và lock; tăng timeout không giải quyết được deadlock, contention hoặc transaction không giới hạn.

## 9. Đánh đổi về rollback và khả năng restart

Spring Batch thường lưu metadata và execution context tại ranh giới commit. Khi chunk lớn hơn, số lần checkpoint ít hơn. Nếu lỗi xảy ra giữa chunk, chunk hiện tại chưa commit và reader có thể phải tiếp tục từ checkpoint của chunk trước.

Ví dụ, với 1.000 item mỗi chunk:

```text
Chunk 1: item 1..1000      -> COMMIT
Chunk 2: item 1001..2000   -> lỗi tại item 1900

Restart từ checkpoint:
  Tiếp tục từ vị trí đã commit sau chunk 1
  Có thể đọc/xử lý lại phần thuộc chunk 2
```

Nếu chunk size là 100, phạm vi item chưa commit thường nhỏ hơn. Điều này không có nghĩa toàn bộ 1.000 item chắc chắn sẽ được thực hiện lại theo mọi reader và fault-tolerance configuration; hành vi cụ thể phụ thuộc buffering, reader state, retry và điểm lỗi. Nhưng checkpoint thưa hơn có thể làm tăng lượng công việc cần phục hồi.

Writer và các thao tác nghiệp vụ cần chịu được việc thực hiện lại. Các thay đổi cùng transaction database sẽ rollback nếu chunk chưa commit; side effect ngoài transaction như gửi email, gọi API hoặc publish message có thể đã xảy ra và cần idempotency/outbox.

## 10. Chunk lớn không thay thế thiết kế writer tốt

Nếu writer thực hiện một câu SQL riêng cho từng item, tăng chunk size có thể giảm số lần commit nhưng vẫn giữ nguyên số lần round trip SQL. Để cải thiện throughput, cần xem writer có thể dùng batch insert/update, bulk load hoặc thao tác set-based hay không.

Ví dụ, thay vì thực hiện nhiều truy vấn tìm kiếm cùng một loại dữ liệu trong processor, có thể:

- Đọc dữ liệu tham chiếu theo lô.
- Dùng join hoặc truy vấn set-based khi phù hợp.
- Dùng JDBC batch hoặc bulk loading cho phần ghi.
- Tránh N+1 query trong processor.
- Chỉ giữ các trường cần thiết trong item thay vì tải toàn bộ object graph.

Chunk size chỉ là một trong các nút điều chỉnh hiệu năng. Nó không tự làm cho truy vấn chậm, thuật toán O(n²), network call theo từng item hoặc writer không có batching trở nên hiệu quả.

## 11. Commit policy và cách xác định ranh giới chunk

Trong trường hợp thông thường, ứng dụng dùng commit interval dạng số item thông qua `.chunk(size, transactionManager)`. Spring Batch cũng có khái niệm `CompletionPolicy` để xác định khi nào một chunk hoàn tất theo chính sách khác, ví dụ dựa trên số item hoặc điều kiện kết hợp.

Khi dùng completion policy tùy chỉnh, cần xác định rõ điều kiện kết thúc chunk và kiểm tra cách nó tương tác với transaction timeout, nguồn dữ liệu và writer. Một policy theo thời gian có thể giúp giới hạn độ dài chunk khi tốc độ đọc thay đổi, nhưng cũng làm số item trong từng chunk không cố định.

Không nên chọn policy phức tạp nếu commit interval cố định đáp ứng được yêu cầu. Cấu hình đơn giản dễ đo, dễ giải thích và dễ dự đoán khi restart hơn.

## 12. Đo lường trước và sau khi tăng chunk size

Hãy đo một baseline trước khi thay đổi. Những số liệu hữu ích gồm:

| Chỉ số | Điều cần quan sát |
| --- | --- |
| Tổng thời gian job/step | Thời gian từ lúc bắt đầu đến lúc hoàn tất. |
| Throughput | Số item xử lý mỗi giây hoặc mỗi phút. |
| Commit count | Số lần commit của step. |
| Thời gian transaction | Thời gian trung bình, p95/p99 và transaction dài nhất nếu có thể đo. |
| Database CPU/I/O | Mức tải database khi job chạy. |
| Lock wait/deadlock | Tác động đến job khác và workload trực tuyến. |
| Connection pool | Số connection đang dùng, chờ và timeout. |
| Heap/GC | Bộ nhớ tăng thêm do chunk và object buffering. |
| Rollback/retry/skip | Tần suất lỗi và chi phí phục hồi. |
| Writer throughput | Thời gian ghi và số statement/round trip. |

So sánh cùng một tập dữ liệu, cùng cấu hình database, cùng tải đồng thời và cùng phiên bản ứng dụng. Chạy lặp lại đủ lần để tránh kết luận từ một lần đo bị ảnh hưởng bởi cache, warm-up hoặc tải nền.

## 13. Quy trình tuning commit interval

Một quy trình thực tế có thể thực hiện theo từng bước:

1. **Đo baseline:** ghi lại chunk size hiện tại, tổng item, số commit, thời gian step, throughput, heap, lock wait và connection usage.
2. **Xác định nút thắt:** kiểm tra thời gian nằm ở commit, đọc, xử lý, ghi, network hay truy vấn. Nếu processor gọi API chậm theo từng item, tăng chunk size có thể không giải quyết được.
3. **Tăng từng nấc:** ví dụ thử 100, 250, 500 rồi 1.000 thay vì nhảy ngay lên một giá trị rất lớn.
4. **Đo lại:** so sánh throughput và tài nguyên sau mỗi thay đổi.
5. **Kiểm tra lỗi và restart:** mô phỏng lỗi giữa chunk, xác nhận rollback, checkpoint và khả năng xử lý lại.
6. **Thử dưới tải đồng thời:** quan sát lock, deadlock và ảnh hưởng đến workload khác.
7. **Chọn vùng ổn định:** ưu tiên giá trị đạt throughput tốt mà vẫn giữ transaction duration, heap và khả năng phục hồi trong giới hạn vận hành.

Ví dụ bảng benchmark (số liệu minh họa, không phải kết quả mặc định của Spring Batch):

| Chunk size | Thời gian job | Throughput | Heap đỉnh | Transaction p95 |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 12 phút | 694 item/s | 450 MB | 180 ms |
| 250 | 9 phút | 926 item/s | 510 MB | 310 ms |
| 500 | 8 phút | 1.042 item/s | 620 MB | 560 ms |
| 1.000 | 7,8 phút | 1.068 item/s | 880 MB | 1.050 ms |
| 2.000 | 8,5 phút | 980 item/s | 1.400 MB | 2.200 ms |

Trong ví dụ giả định này, tăng từ 100 lên 500 cải thiện throughput rõ rệt. Từ 500 lên 1.000 chỉ tăng nhẹ nhưng heap và thời gian transaction tăng mạnh. Ở 2.000, hiệu năng giảm do chi phí transaction lớn và áp lực tài nguyên. Giá trị phù hợp có thể là 500 hoặc 1.000 tùy giới hạn vận hành và yêu cầu phục hồi.

## 14. Ví dụ ghi nhận commit count và thời gian xử lý

`StepExecution` cung cấp các bộ đếm như `readCount`, `writeCount`, `commitCount` và `rollbackCount`. Có thể dùng listener hoặc metrics để ghi lại thời gian step/chunk và kết hợp với số liệu database.

Ví dụ đọc bộ đếm sau khi step kết thúc:

```java
public class StepMetricsListener implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(StepMetricsListener.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "step={}, read={}, write={}, commits={}, rollbacks={}, status={}",
            stepExecution.getStepName(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount(),
            stepExecution.getStatus()
        );
        return null;
    }
}
```

Đăng ký listener với step:

```java
.listener(new StepMetricsListener())
```

`commitCount` là chỉ số hữu ích để so sánh số lần commit giữa các cấu hình. Nó không thay thế việc đo thời gian commit hoặc truy vấn database. Nếu muốn biết transaction nào chậm, cần metrics từ transaction manager, database monitoring, tracing hoặc instrumentation phù hợp.

## 15. Các tình huống nên giữ chunk nhỏ

Chunk lớn không phải lựa chọn tốt khi:

- Mỗi item có object graph lớn hoặc giữ nhiều tài nguyên.
- Writer cập nhật các hàng có tranh chấp cao với giao dịch trực tuyến.
- Transaction có thể vượt timeout hoặc giữ lock quá lâu.
- Job cần checkpoint thường xuyên vì nguồn khó đọc lại.
- Lỗi thường xuyên xảy ra và việc xử lý lại chunk lớn quá tốn kém.
- Yêu cầu nghiệp vụ cần commit từng item hoặc từng nhóm nhỏ.
- Nguồn bên ngoài có offset/ack khó đồng bộ với transaction database.

Trong những trường hợp này, chunk nhỏ hơn có thể đem lại tính ổn định và khả năng phục hồi tốt hơn, dù số lần commit tăng.

## 16. Những lỗi thường gặp khi tăng commit interval

**Tăng quá nhanh mà không benchmark:** có thể làm transaction dài, tăng lock wait hoặc heap. Hãy tăng từng nấc và đo.

**Chỉ nhìn tổng thời gian job:** job có thể nhanh hơn nhưng làm database hoặc API trực tuyến chậm đi. Cần đo dưới tải đồng thời.

**Nhầm chunk size với JDBC batch size:** hai cấu hình khác nhau. Kiểm tra writer và driver thực sự gửi bao nhiêu statement trong mỗi batch.

**Bỏ qua transaction timeout:** chunk lớn có thể xử lý lâu hơn giới hạn timeout. Xem xét thời gian xử lý thực tế và transaction attribute.

**Không kiểm tra heap:** chunk lớn giữ nhiều item/output hơn và có thể gây áp lực GC hoặc OOM.

**Không thử restart:** checkpoint thưa hơn có thể làm nhiều item chưa commit phải được đọc/xử lý lại. Kiểm tra reader state và writer idempotency.

**Cho rằng mọi thao tác đều rollback:** HTTP, email, file và broker không tự tham gia transaction database. Dùng outbox hoặc cơ chế bù trừ/idempotency.

**Tăng chunk size để che giấu writer kém hiệu quả:** N+1 query hoặc một API call cho mỗi item vẫn là nút thắt. Tối ưu thuật toán và batching riêng.

## 17. Cách chọn commit interval cho production

Hãy bắt đầu từ yêu cầu nghiệp vụ và giới hạn tài nguyên. Nếu job chủ yếu bị giới hạn bởi commit overhead, thử tăng chunk size để giảm số transaction. Nếu job bị giới hạn bởi truy vấn, network hoặc CPU của processor, hãy xử lý nút thắt đó trước. Với writer có thể ghi batch, chọn chunk size tương thích với khả năng batch và giới hạn payload của database.

Sau mỗi lần thay đổi, kiểm tra throughput, transaction duration, lock wait, heap, connection pool và số lần commit. Mô phỏng lỗi để xác nhận rollback và restart vẫn hoạt động; đảm bảo writer có thể xử lý lại an toàn nếu chunk chưa commit. Đặt giới hạn trên để transaction không vượt timeout hoặc làm ảnh hưởng đến workload khác.

Commit lớn giúp giảm transaction overhead vì cùng một lượng item được xử lý qua ít transaction và ít lần commit hơn. Hiệu quả chỉ bền vững khi chunk size phù hợp với khả năng của database, bộ nhớ, writer và yêu cầu phục hồi. Đo lường theo từng nấc và chọn giá trị ổn định sẽ giúp tăng throughput mà vẫn giữ được tính nhất quán và khả năng vận hành của job Spring Batch.
