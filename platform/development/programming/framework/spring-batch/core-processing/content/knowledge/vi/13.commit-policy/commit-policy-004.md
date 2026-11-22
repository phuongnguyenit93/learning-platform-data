# Commit theo thời gian

Trong Spring Batch, chunk-oriented step thường gom nhiều item vào một chunk rồi ghi kết quả và commit transaction. Cách cấu hình phổ biến nhất là đặt số item tối đa cho mỗi chunk, ví dụ `chunk(500, transactionManager)`. Tuy nhiên, nếu thời gian xử lý mỗi item thay đổi nhiều, một chunk gồm 500 item có thể mất vài giây ở lần chạy này nhưng mất vài phút ở lần chạy khác.

Khi cần giới hạn thời gian xử lý của một chunk, Spring Batch cho phép dùng `CompletionPolicy` thay cho commit interval cố định. `TimeoutTerminationPolicy` là policy phổ biến để kết thúc chunk khi thời gian đã vượt ngưỡng cấu hình. Khi policy báo chunk hoàn tất, framework chuyển các output hiện có tới writer, cập nhật state/metadata và commit transaction của chunk.

Commit theo thời gian giúp kiểm soát gần đúng thời lượng một transaction và giảm nguy cơ giữ lock quá lâu khi thời gian xử lý mỗi item không đồng đều. Đây là ngưỡng kết thúc chunk, không phải một lịch hẹn có thể ngắt một item đang xử lý ngay đúng thời điểm. Thời gian thực tế từ lúc bắt đầu chunk tới lúc commit có thể dài hơn ngưỡng vì reader, processor, writer hoặc database có thể mất thêm thời gian.

## Commit interval theo số lượng và theo thời gian

Spring Batch cần một quy tắc để biết khi nào chunk hiện tại kết thúc. Có hai cách tiếp cận thường gặp:

| Cách xác định chunk | Cơ chế | Khi phù hợp |
| --- | --- | --- |
| Theo số item | `SimpleCompletionPolicy` hoặc `chunk(int, transactionManager)` | Mỗi item có thời gian xử lý tương đối ổn định và muốn kiểm soát số item mỗi transaction |
| Theo thời gian | `TimeoutTerminationPolicy` thông qua `CompletionPolicy` | Thời gian xử lý mỗi item biến động và muốn giới hạn gần đúng thời lượng chunk |

Ví dụ theo số lượng:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
```

Với cấu hình này, chunk thường kết thúc sau khi đã xử lý đủ 500 item đầu vào hoặc khi nguồn dữ liệu kết thúc. Nếu mỗi item mất 10 ms, thời gian xử lý phần reader/processor có thể xấp xỉ 5 giây; nếu mỗi item mất 500 ms, cùng chunk size có thể kéo dài khoảng 250 giây, chưa tính writer và commit.

Commit theo thời gian xác định chunk dựa trên thời gian đã trôi qua kể từ lúc bắt đầu chunk. Điều này hữu ích khi thời gian mỗi item không ổn định, nhưng số item trong mỗi chunk sẽ thay đổi theo tải và độ phức tạp dữ liệu.

## CompletionPolicy và TimeoutTerminationPolicy

`CompletionPolicy` là abstraction của Spring Batch để xác định khi nào một lần lặp hoặc một chunk nên kết thúc. Thay vì chỉ đếm số item, policy có thể dựa vào thời gian hoặc một điều kiện khác.

`TimeoutTerminationPolicy` triển khai quy tắc kết thúc theo thời gian. Constructor của nó nhận timeout tính bằng milliseconds. Ví dụ `30_000` tương ứng khoảng 30 giây.

Với Spring Batch 5, có thể truyền policy trực tiếp vào `StepBuilder.chunk(...)`:

```java
@Bean
Step importOrdersByTimeStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    CompletionPolicy completionPolicy =
            new TimeoutTerminationPolicy(30_000);

    return new StepBuilder("importOrdersByTimeStep", jobRepository)
            .<OrderInput, Order>chunk(completionPolicy, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Trong ví dụ:

- `TimeoutTerminationPolicy(30_000)` đặt ngưỡng thời gian khoảng 30 giây cho một chunk.
- `chunk(completionPolicy, transactionManager)` yêu cầu step dùng policy này để xác định thời điểm kết thúc chunk.
- Reader và processor tiếp tục xử lý item trong chunk cho tới khi policy hoàn tất hoặc reader báo hết dữ liệu.
- Writer ghi các output đã thu thập; Spring Batch cập nhật metadata và commit transaction theo lifecycle của chunk.

Các import thường dùng trong Spring Batch 5:

```java
import org.springframework.batch.repeat.CompletionPolicy;
import org.springframework.batch.repeat.policy.TimeoutTerminationPolicy;
```

API builder và package cần được đối chiếu với phiên bản framework của dự án. Ở các phiên bản cũ, cách tạo step có thể thông qua `StepBuilderFactory`; ý tưởng vẫn là cung cấp một `CompletionPolicy` cho chunk thay vì chỉ truyền số item.

## Chunk kết thúc theo thời gian như thế nào?

Một chunk transaction bắt đầu, sau đó Spring Batch đọc và xử lý từng item. Policy theo dõi thời gian của lần lặp. Khi điều kiện timeout đã đạt tại điểm kiểm tra của repeat operation, chunk được xem là hoàn tất và framework chuyển sang giai đoạn ghi.

```text
Bắt đầu chunk và transaction
          |
          v
     Đọc item 1
          |
          v
     Process item 1
          |
          v
     Kiểm tra policy
          |
          v
     Đọc / process item tiếp
          |
          v
   Timeout đã đạt chưa?
       /          \
     Chưa          Rồi
      |             |
      +--- lặp      v
               ItemWriter
                   |
                   v
          Cập nhật state/metadata
                   |
                   v
                COMMIT
```

Policy không ngắt ngang một lần gọi `read()` hoặc `process()` đang chạy. Nếu một processor bắt đầu ngay trước ngưỡng 30 giây nhưng mất thêm 20 giây mới hoàn tất, chunk chỉ có thể kết thúc sau khi thao tác đó trả về và framework kiểm tra policy ở điểm tiếp theo. Writer và commit cũng cần thời gian riêng.

Do đó, timeout policy tạo ra một ngưỡng vận hành gần đúng cho chunk duration, chứ không bảo đảm mọi transaction đều được commit trong đúng 30 giây.

## Ví dụ với thời gian xử lý không đồng đều

Giả sử một job xử lý hồ sơ khách hàng. Một số hồ sơ chỉ cần chuẩn hóa chuỗi và mất vài millisecond; một số hồ sơ cần gọi dịch vụ tra cứu và mất vài trăm millisecond.

Nếu dùng `chunk(500, transactionManager)`, chunk luôn gom số item gần cố định. Thời gian transaction có thể biến động lớn:

| Tình huống | Thời gian trung bình mỗi item | 500 item (ước lượng phần xử lý) |
| --- | ---: | ---: |
| Dữ liệu đơn giản | 5 ms | 2,5 giây |
| Dữ liệu thông thường | 40 ms | 20 giây |
| Dữ liệu cần tra cứu | 250 ms | 125 giây |

Nếu mục tiêu là giữ transaction ở khoảng 20–30 giây trong điều kiện tải bình thường, có thể dùng `TimeoutTerminationPolicy(30_000)`. Khi item xử lý nhanh, chunk có thể chứa nhiều item. Khi item xử lý chậm, chunk có thể chứa ít item hơn.

Số item trong mỗi chunk vì vậy không cố định. Điều này ảnh hưởng đến số lần gọi writer, số lần commit và throughput. Cần đo trên dữ liệu gần thực tế để chọn timeout phù hợp.

## Timeout của chunk khác transaction timeout

Đây là hai cấu hình khác nhau và không nên nhầm lẫn.

**Chunk timeout** qua `TimeoutTerminationPolicy` xác định khi nào framework nên kết thúc việc gom item vào chunk và chuyển sang writer/commit. Nó điều khiển kích thước chunk theo thời gian.

**Transaction timeout** là giới hạn thời gian của transaction do transaction manager quản lý. Nếu transaction vượt quá giới hạn này, thao tác database có thể thất bại hoặc transaction bị đánh dấu rollback-only tùy transaction manager và resource.

| Tiêu chí | TimeoutTerminationPolicy | Transaction timeout |
| --- | --- | --- |
| Mục đích | Kết thúc chunk theo thời gian | Giới hạn thời gian transaction được phép tồn tại |
| Ảnh hưởng | Quyết định khi ngừng đọc/process item cho chunk hiện tại | Có thể làm transaction thất bại nếu vượt giới hạn |
| Thời điểm có hiệu lực | Được kiểm tra trong repeat/chunk processing | Do transaction manager/database áp dụng |
| Có ngắt một processor đang chạy không? | Không | Không nhất thiết; phụ thuộc thao tác và resource |
| Đơn vị cấu hình | Milliseconds trong `TimeoutTerminationPolicy` | Thường là seconds hoặc cấu hình riêng của transaction manager |

Ví dụ, chunk timeout đặt 30 giây nhưng transaction timeout đặt 20 giây. Nếu reader/processor vẫn đang làm việc sau 20 giây, transaction manager có thể khiến transaction thất bại trước khi chunk policy có cơ hội kết thúc bình thường. Ngược lại, transaction timeout 5 phút nhưng chunk timeout 30 giây thường cho phép chunk kết thúc sớm hơn, miễn là writer và commit hoàn thành trong giới hạn transaction.

Khi đặt hai ngưỡng, cần chừa thời gian cho writer, cập nhật metadata và commit. Không nên đặt transaction timeout bằng đúng chunk timeout nếu writer có thể mất thêm thời gian đáng kể.

## Chọn timeout cho chunk

Không có một giá trị timeout tối ưu cho mọi job. Giá trị phù hợp phụ thuộc vào thời gian xử lý item, thời gian writer, tải database, lock contention, connection pool và yêu cầu restart.

Các yếu tố nên xem xét:

- **Thời gian reader/processor:** nếu mỗi item có latency lớn hoặc phân bố không đồng đều, chunk theo thời gian có thể tránh gom quá nhiều item vào một transaction.
- **Thời gian writer:** writer có thể mất thời gian đáng kể để ghi batch lớn; cần tính phần này vào transaction duration.
- **Khả năng chịu lock:** chunk dài giữ lock lâu hơn, có thể làm các giao dịch khác chờ.
- **Chi phí commit:** timeout quá ngắn tạo nhiều chunk và nhiều lần commit, tăng tải database và metadata repository.
- **Khả năng restart:** chunk nhỏ hơn thường giảm lượng công việc phải xử lý lại khi transaction rollback, nhưng tăng số checkpoint.
- **Throughput:** chunk lớn có thể tăng hiệu quả batch write; chunk nhỏ có thể giảm lock duration nhưng tăng overhead.

Một cách bắt đầu là đo thời gian xử lý và ghi của một số chunk đại diện, sau đó chọn timeout thấp hơn ngưỡng mà database có thể giữ transaction ổn định. Tiếp tục quan sát p95/p99 chunk duration thay vì chỉ nhìn thời gian trung bình.

## Kết hợp giới hạn thời gian và số item

Một số job cần cả hai giới hạn:

- Không để chunk kéo dài quá lâu khi item xử lý chậm.
- Không để chunk chứa quá nhiều item khi item xử lý rất nhanh.

Trong trường hợp này, có thể kết hợp các `CompletionPolicy` hoặc triển khai policy tùy chỉnh dựa trên cả thời gian và số lượng. Spring Batch có các policy composition trong package repeat; cách kết hợp cụ thể cần kiểm tra API phiên bản đang dùng và quy tắc hoàn tất của composite policy.

Về mặt thiết kế, điều kiện thường mong muốn là kết thúc chunk khi **một trong hai ngưỡng** đạt trước: số item tối đa hoặc thời gian tối đa. Ví dụ giới hạn tối đa 1.000 item hoặc khoảng 30 giây, tùy điều kiện nào tới trước.

Không nên giả định việc truyền cả `chunk(1000, transactionManager)` và `TimeoutTerminationPolicy` ở hai vị trí khác nhau sẽ tự động kết hợp. Step cần một `CompletionPolicy` được cấu hình rõ ràng để biểu diễn logic kết hợp.

## Custom CompletionPolicy

Nếu quy tắc commit phức tạp hơn timeout thuần, có thể triển khai `CompletionPolicy` tùy chỉnh. Ví dụ, một policy có thể kết thúc chunk khi đạt thời gian tối đa, đạt số item tối đa hoặc một điều kiện nghiệp vụ khác.

Một policy tùy chỉnh cần quản lý trạng thái của từng chunk thông qua `RepeatContext`, xác định lúc bắt đầu một lần lặp, cập nhật trạng thái sau mỗi lần xử lý và trả lời liệu policy đã hoàn tất hay chưa. Không nên lưu bộ đếm hoặc timestamp của chunk trong field dùng chung giữa nhiều execution nếu object policy có thể được chia sẻ; state nên gắn với repeat context của lần thực thi.

Trước khi tự viết policy, hãy cân nhắc dùng policy có sẵn. Custom policy cần được kiểm thử với trường hợp item xử lý nhanh, item xử lý lâu, reader hết dữ liệu, exception, retry và restart. Đặc biệt, cần xác định rõ điều kiện kết thúc là OR hay AND khi kết hợp nhiều ngưỡng.

## Tác động tới transaction và restart

Khi chunk kết thúc theo thời gian, Spring Batch vẫn dùng transaction semantics của chunk-oriented processing. Writer và các cập nhật checkpoint được điều phối trong transaction của chunk theo cấu hình step.

Nếu chunk commit thành công, dữ liệu nghiệp vụ và metadata checkpoint tham gia cùng transaction resource có thể được lưu cùng nhau. Nếu chunk rollback, các thay đổi tham gia transaction bị rollback và các item của chunk có thể được đọc/process lại khi restart.

Timeout policy không làm cho dữ liệu tự động được commit giữa lúc processor đang chạy. Nếu một item mất 90 giây và chunk timeout là 30 giây, item đó vẫn cần hoàn tất hoặc ném lỗi trước khi framework có thể kết thúc chunk theo policy. Nếu item quá lâu, hãy xử lý timeout ở chính thao tác reader/processor, HTTP client hoặc database query, thay vì chỉ giảm chunk timeout.

Khi restart, `ExecutionContext` của reader/writer vẫn là cơ chế lưu state. Việc chunk được kết thúc theo thời gian hay số item không thay đổi nguyên tắc identifying parameters: restart cùng logical job cần dùng lại cùng identifying parameters.

## Ảnh hưởng tới hiệu năng

Commit theo thời gian có thể cải thiện khả năng dự đoán thời lượng transaction, nhưng không phải lúc nào cũng tăng throughput.

### Timeout quá ngắn

Nếu đặt timeout rất nhỏ, mỗi chunk chỉ chứa vài item. Hệ quả có thể gồm:

- Tăng số lần gọi writer và số lần thực thi batch SQL.
- Tăng số transaction begin/commit/rollback.
- Tăng số lần cập nhật metadata và execution context.
- Tăng overhead đọc/ghi và contention ở `JobRepository`.
- Giảm hiệu quả batch insert hoặc batch message.

### Timeout quá dài

Nếu timeout quá lớn, chunk có thể giữ transaction lâu:

- Database lock tồn tại lâu và làm tăng thời gian chờ của transaction khác.
- Một lỗi cuối chunk có thể khiến nhiều item phải xử lý lại.
- Connection pool bị chiếm lâu hơn.
- Writer nhận lượng output lớn, làm tăng bộ nhớ và thời gian ghi.
- Shutdown hoặc timeout của hệ thống có thể xảy ra khi transaction vẫn còn mở.

### Đo lường

Nên theo dõi ít nhất:

- Chunk duration trung bình và percentile cao như p95/p99.
- Số item đọc, xử lý, filter, skip và ghi mỗi chunk.
- Thời gian reader, processor và writer.
- Số lần commit, rollback và retry.
- Lock wait, deadlock, connection pool usage và database latency.
- Throughput item/giây và thời gian hoàn thành toàn job.

Chọn timeout dựa trên dữ liệu đo và yêu cầu nghiệp vụ. Một con số cố định không thể tối ưu cho mọi loại dữ liệu và mọi thời điểm tải.

## Timeout policy không phải scheduler hay job timeout

Commit theo thời gian thường bị nhầm với các cơ chế timeout khác:

| Cơ chế | Kiểm soát điều gì? |
| --- | --- |
| `TimeoutTerminationPolicy` | Thời gian gom item cho một chunk |
| Transaction timeout | Thời gian tối đa của transaction |
| HTTP/client timeout | Thời gian chờ một request tới hệ thống ngoài |
| Job execution timeout do ứng dụng quản lý | Thời gian chạy tổng thể của job theo chính sách ứng dụng |
| Scheduler interval/cron | Thời điểm bắt đầu job |

Ví dụ, scheduler chạy job mỗi giờ không có nghĩa chunk sẽ commit mỗi giờ. Ngược lại, timeout chunk 30 giây không có nghĩa job tự dừng sau 30 giây; job có thể chạy nhiều chunk liên tiếp trong nhiều giờ.

Nếu processor gọi HTTP, hãy cấu hình connect/read/request timeout cho HTTP client. Nếu query database có thể bị treo, hãy cấu hình query timeout phù hợp. `TimeoutTerminationPolicy` chỉ quyết định chunk nên kết thúc ở điểm kiểm tra tiếp theo; nó không thay thế timeout ở từng thao tác I/O.

## Khi reader hoặc processor bị chặn lâu

Một điểm giới hạn quan trọng: time-based completion policy không thể ngắt an toàn một lời gọi Java đang chạy. Nếu `ItemReader.read()` đang chờ một API 2 phút, hoặc `ItemProcessor.process()` đang chờ lock, policy không thể tự cắt ngang để commit chunk ở giây thứ 30.

Để kiểm soát các thao tác có thể bị chặn, cần cấu hình timeout ở đúng tầng:

- JDBC query timeout hoặc timeout của database statement.
- HTTP connect timeout, response/read timeout và overall request timeout.
- Timeout khi nhận message từ broker.
- Timeout cho lock hoặc semaphore trong ứng dụng.
- Cancellation và interrupt handling nếu API được sử dụng hỗ trợ an toàn.

Không nên dùng `Thread.interrupt()` tùy tiện để cắt một item đang cập nhật dữ liệu. Việc ngắt giữa thao tác có thể để lại side effect ngoài transaction hoặc trạng thái không rõ ràng.

## Lỗi thường gặp khi dùng commit theo thời gian

### Nghĩ rằng commit xảy ra đúng mỗi 30 giây

Policy được kiểm tra trong repeat/chunk loop. Item đang chạy không bị ngắt tại ngưỡng; writer và commit cũng cần thời gian. Hãy xem timeout là ngưỡng kết thúc gần đúng, không phải lịch commit chính xác.

### Nhầm chunk timeout với transaction timeout

Một policy kết thúc chunk không đồng nghĩa transaction manager cho phép transaction kéo dài vô hạn. Cấu hình hai ngưỡng phối hợp và chừa thời gian cho writer/commit.

### Chọn timeout quá ngắn

Nhiều chunk nhỏ làm tăng overhead và giảm lợi ích batch write. Đo thời gian xử lý và chi phí commit trước khi hạ timeout.

### Chọn timeout quá dài

Transaction dài có thể giữ lock và connection lâu, tăng phạm vi rollback. Chọn ngưỡng dựa trên khả năng database và yêu cầu restart.

### Mong policy ngắt processor đang chạy

Policy không preempt một lời gọi reader/processor. Cấu hình timeout cho I/O hoặc chia nhỏ thao tác xử lý dài.

### Cho rằng timeout policy giới hạn tổng thời gian job

Timeout chỉ điều khiển một chunk. Job vẫn có thể chạy nhiều chunk liên tiếp cho đến khi reader hết dữ liệu hoặc flow kết thúc.

### Dùng thời gian hiện tại làm identifying parameter để tránh chạy trùng

Timestamp identifying mới có thể tạo `JobInstance` mới và làm mất liên kết restart với instance cũ. Dùng parameter nghiệp vụ ổn định; commit policy không quyết định danh tính job.

## Kiểm thử time-based commit policy

Nên kiểm thử hành vi policy với thời gian giả lập hoặc các processor có độ trễ kiểm soát trong môi trường test. Không nên viết test phụ thuộc quá chặt vào thời gian wall-clock thực tế vì máy chạy test có tải khác nhau.

Các trường hợp nên kiểm tra:

- Nhiều item nhanh được gom vào cùng chunk cho tới khi đạt timeout.
- Item chậm làm chunk vượt ngưỡng trước khi policy có thể kết thúc.
- Reader hết dữ liệu trước khi timeout; chunk cuối vẫn được hoàn tất đúng.
- Writer thất bại sau khi policy kết thúc; transaction rollback theo cấu hình.
- Chunk trước commit thành công, chunk sau thất bại; restart bắt đầu từ checkpoint đã commit.
- Transaction timeout nhỏ hơn thời gian cần thiết; step xử lý lỗi đúng như cấu hình.
- Policy kết hợp thời gian và số item kết thúc khi điều kiện mong muốn đầu tiên đạt.

Để kiểm tra chính sách, nên ghi lại thời điểm bắt đầu chunk, thời điểm writer được gọi và thời điểm transaction hoàn tất. So sánh các số liệu này để hiểu phần thời gian nằm trong reader/processor, writer và commit.

## Khi nào nên dùng commit theo thời gian?

Commit theo thời gian phù hợp khi thời gian xử lý item biến động mạnh và muốn giới hạn gần đúng thời lượng một transaction. Một số tình huống:

- Processor gọi dịch vụ tra cứu có latency không ổn định.
- Item có kích thước hoặc độ phức tạp khác nhau đáng kể.
- Writer cần tránh nhận một batch quá lớn khi tải tăng.
- Database có yêu cầu vận hành về thời gian giữ transaction hoặc lock.
- Muốn cân bằng số lần commit với phạm vi rollback trong các workload không đồng đều.

Commit theo số lượng thường phù hợp khi thời gian xử lý item ổn định, writer tối ưu theo batch size và muốn giới hạn chính xác số item mỗi chunk. Nếu cả thời gian và số item đều có giới hạn quan trọng, hãy cấu hình một `CompletionPolicy` kết hợp rõ ràng.

Không nên chọn time-based policy chỉ vì tên gọi có vẻ linh hoạt hơn. Hãy xác định vấn đề cần giải quyết: transaction quá dài, chunk output quá lớn, latency item không đồng đều hay chi phí commit quá cao. Sau đó đo lường và chọn policy tương ứng.

## Ghi nhớ

Spring Batch hỗ trợ commit theo thời gian thông qua `CompletionPolicy`, phổ biến là `TimeoutTerminationPolicy`. Policy kết thúc việc gom item cho chunk khi thời gian đã vượt ngưỡng, sau đó framework gọi writer, cập nhật state/metadata và commit transaction. Ngưỡng này được kiểm tra tại các điểm trong repeat loop nên không ngắt một reader hoặc processor đang chạy và không bảo đảm commit đúng từng mili giây. Chunk timeout khác transaction timeout, job timeout và scheduler interval. Hãy chừa thời gian cho writer/commit, cấu hình timeout ở từng thao tác I/O, đo chunk duration và chọn ngưỡng phù hợp với lock, connection pool, throughput và yêu cầu restart.
