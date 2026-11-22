# Item đã đọc trước rollback

Trong Spring Batch, reader thường đã lấy một nhóm item khỏi nguồn dữ liệu trước khi processor và writer hoàn tất chunk. Nếu transaction của chunk rollback, reader có thể đã tiến đến vị trí tiếp theo dù dữ liệu của chunk chưa được commit. Spring Batch cần giữ lại các item đã đọc để chúng không bị mất và có thể được xử lý lại.

Với reader thông thường, framework mặc định buffer các item của chunk trong bộ nhớ. Khi rollback xảy ra trong cùng process, các item đã đọc có thể được đưa lại vào quá trình xử lý mà không yêu cầu reader đọc lại ngay từ nguồn. Với reader dựa trên tài nguyên transactional như JMS queue, transaction rollback có thể trả message về queue; trường hợp này cần cấu hình reader là transactional queue để tránh framework buffer cùng những message sẽ được broker phát lại.

Cần phân biệt rollback trong lúc ứng dụng vẫn chạy với restart sau khi process bị dừng. Buffer trong bộ nhớ chỉ tồn tại trong process hiện tại. Khi ứng dụng khởi động lại, reader dựa vào checkpoint đã lưu ở lần commit trước để đọc lại phần chưa hoàn tất.

## 1. Vì sao item đã đọc vẫn cần được giữ sau rollback?

Trong chunk-oriented processing, Spring Batch đọc một nhóm item, xử lý rồi ghi kết quả trong transaction của chunk. Reader thường thay đổi vị trí nội bộ ngay khi trả item về từ `read()`.

Giả sử chunk size là 3 và nguồn có các item A, B, C, D:

```text
Reader đọc A, B, C
        |
        v
Processor xử lý A, B, C
        |
        v
Writer ghi kết quả
        |
        +--> Writer gặp lỗi
                 |
                 v
            Transaction rollback
```

Tại thời điểm writer gặp lỗi, reader có thể đã tiến đến item D. Nếu framework chỉ rollback transaction database mà không giữ lại A, B, C, lần đọc tiếp theo có thể bắt đầu ở D. Khi đó A, B, C chưa được commit nhưng đã bị bỏ qua trong lần chạy hiện tại.

Spring Batch cần bảo đảm các item thuộc chunk chưa commit được xử lý lại theo chính sách retry/rollback. Vì vậy, với reader không transactional, framework mặc định giữ các item đã đọc trong chunk để có thể phát lại cho processor/writer sau rollback.

Điểm quan trọng: rollback transaction của chunk không tự động đưa mọi `ItemReader` tùy ý về vị trí cũ. Framework buffer item để phục hồi luồng xử lý; nó không thể tự rewind mọi file stream, cursor hoặc API bên ngoài.

## 2. Luồng mặc định: buffer item đã đọc

Với reader thông thường, các item được đọc được giữ trong chunk hiện tại. Nếu writer hoặc một bước xử lý phía sau làm transaction rollback, Spring Batch có thể sử dụng lại các item đó trong lần thử tiếp theo.

```text
Lần thử đầu
  read A, B, C
  buffer [A, B, C]
  process A, B, C
  write -> exception
  rollback

Lần thử lại trong cùng process
  lấy lại [A, B, C] từ buffer
  process/write theo fault-tolerance policy
  commit khi thành công

Sau commit
  buffer của chunk hoàn tất được giải phóng
  reader tiếp tục đọc D, E, F
```

Buffer giúp framework giữ đúng tập item thuộc chunk chưa commit. Reader không cần tự lùi vị trí về A nếu framework có thể phát lại các item đã buffer.

Hành vi retry chi tiết còn phụ thuộc exception, retry/skip policy và loại processor/writer. Một số xử lý có thể được gọi lại; vì vậy processor và writer cần được thiết kế an toàn khi replay. Buffer không có nghĩa mọi method trong chunk chỉ chạy một lần.

## 3. Ví dụ chunk bị rollback rồi xử lý lại

Giả sử Step dùng chunk size 3:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(3, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(2)
            .build();
}
```

Giả sử reader đọc ba đơn hàng `A`, `B`, `C`. Writer gặp lỗi transient khi ghi `B`:

| Thời điểm | Reader / chunk | Transaction |
|---|---|---|
| Bắt đầu chunk | Chưa đọc item | Mở transaction |
| Đọc | A, B, C được lấy và buffer | Đang hoạt động |
| Ghi | Writer bắt đầu ghi chunk | Đang hoạt động |
| Lỗi | Writer ném exception | Rollback |
| Retry | Các item đã buffer được sử dụng lại theo retry policy | Transaction thử lại |
| Thành công | A, B, C được ghi hoàn tất | Commit |
| Chunk kế tiếp | Reader tiếp tục với D | Transaction mới |

Nếu writer dùng cùng transaction manager và database resource, các thay đổi chưa commit từ lần ghi đầu được rollback. Khi writer được gọi lại, chunk có thể được ghi lại mà không để lại các thay đổi database của lần thất bại.

Nếu writer đã tạo side effect ngoài transaction, chẳng hạn gửi message hoặc gọi API, rollback database không thu hồi được side effect đó. Khi chunk được phát lại, side effect có thể xảy ra lần nữa; writer cần idempotency hoặc một cơ chế như outbox.

## 4. Buffer trong bộ nhớ khác với checkpoint trong ExecutionContext

Hai cơ chế này thường bị nhầm lẫn:

| Cơ chế | Phạm vi tồn tại | Mục đích |
|---|---|---|
| Buffer item của chunk | Trong process và lần xử lý chunk hiện tại | Phát lại item đã đọc khi transaction rollback trong lúc process còn chạy |
| Step `ExecutionContext` | Được lưu trong JobRepository | Lưu checkpoint để khôi phục reader khi Step/Job được restart |

Buffer là dữ liệu item đang chờ commit. ExecutionContext lưu trạng thái nhỏ như vị trí dòng, page, offset hoặc ID cuối cùng đã commit. Không nên đưa toàn bộ chunk vào ExecutionContext để thay thế buffer.

Ví dụ reader lưu checkpoint:

```java
private static final String LAST_ID_KEY = "ordersReader.lastCommittedId";
private long lastCommittedId;

@Override
public void open(ExecutionContext context) {
    lastCommittedId = context.getLong(LAST_ID_KEY, 0L);
    openSourceAfter(lastCommittedId);
}

@Override
public void update(ExecutionContext context) {
    context.putLong(LAST_ID_KEY, lastCommittedId);
}
```

Reader restartable cần triển khai `ItemStream` hoặc dùng reader tích hợp sẵn có hỗ trợ lưu state. Framework gọi `update()` tại các điểm lưu trạng thái của Step; checkpoint bền vững cần phản ánh tiến độ đã commit, không phải đơn thuần vị trí reader đã đọc trước khi chunk hoàn tất.

## 5. Rollback trong cùng process và restart sau process failure

Rollback và restart là hai tình huống khác nhau.

### Rollback khi process vẫn chạy

Khi transaction của chunk rollback nhưng ứng dụng vẫn hoạt động, buffer của chunk vẫn có thể tồn tại trong bộ nhớ. Framework dùng lại item đã đọc để thực hiện retry hoặc xử lý tiếp theo policy. Reader không nhất thiết phải đọc lại nguồn dữ liệu cho cùng item.

### Process bị dừng rồi Job được restart

Nếu JVM hoặc máy chủ bị dừng, buffer trong bộ nhớ biến mất. Khi Job được restart, Spring Batch tạo execution mới cho cùng JobInstance nếu identifying JobParameters được giữ nguyên và trạng thái cho phép restart.

Reader được mở lại với ExecutionContext đã lưu tại checkpoint trước đó. Phần dữ liệu thuộc chunk chưa commit sẽ được đọc lại từ nguồn, dựa trên checkpoint gần nhất đã lưu.

```text
Process cũ
  Chunk 1 -> commit, checkpoint 1
  Chunk 2 -> commit, checkpoint 2
  Chunk 3 -> đọc A, B, C; lỗi trước commit
  Process dừng; buffer mất

Process mới / restart
  Khôi phục checkpoint 2
  Reader đọc lại A, B, C
  Xử lý và commit chunk 3
```

Vì vậy, reader cần có nguồn dữ liệu ổn định và khả năng khôi phục checkpoint. Nếu reader không lưu state hoặc nguồn đầu vào đã thay đổi, restart có thể bắt đầu từ đầu hoặc đọc sai phạm vi dữ liệu.

## 6. Reader transactional: trường hợp JMS queue

Một số reader lấy dữ liệu từ tài nguyên transactional. Ví dụ, khi đọc một message từ JMS queue trong transaction, thao tác nhận message có thể tham gia transaction. Nếu transaction rollback, broker có thể đưa message trở lại queue để được nhận lại.

Trong trường hợp đó, nếu Spring Batch vừa buffer message vừa để transaction rollback trả message về queue, cùng message có thể xuất hiện hai lần: một lần từ buffer và một lần được broker phát lại.

Đây là lý do có tùy chọn reader transactional queue trong fault-tolerant Step. Tùy chọn này thông báo cho framework rằng reader lấy item từ một queue có transaction và việc rollback sẽ trả item về nguồn; framework không cần áp dụng cơ chế buffer thông thường cho các item đó.

Ví dụ cấu hình theo API Java của các phiên bản Spring Batch hỗ trợ:

```java
@Bean
public Step consumeMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Message> messageReader,
        ItemProcessor<Message, ProcessedMessage> processor,
        ItemWriter<ProcessedMessage> writer) {

    return new StepBuilder("consumeMessagesStep", jobRepository)
            .<Message, ProcessedMessage>chunk(10, transactionManager)
            .reader(messageReader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .readerIsTransactionalQueue()
            .build();
}
```

Tên và cách cấu hình tùy chọn có thể thay đổi theo phiên bản Spring Batch. Hãy dùng API tương ứng với phiên bản dependency của dự án. Chỉ bật tùy chọn này khi reader thực sự đọc từ transactional queue và transaction rollback bảo đảm message được trả về nguồn.

Không bật tùy chọn transactional queue cho reader file hoặc database thông thường chỉ vì muốn tránh buffer. Những reader đó thường không tự trả item về vị trí cũ khi transaction rollback.

## 7. Transaction của queue phải thực sự bao phủ thao tác nhận message

Tùy chọn reader transactional queue chỉ đúng khi việc nhận message thực sự tham gia transaction mà Step rollback. Nếu reader nhận message bằng auto-acknowledge hoặc session không transactional, rollback transaction database không làm message quay lại queue.

Khi tích hợp JMS, cần xác định:

- JMS session/consumer có dùng transaction hay không.
- Transaction manager của Step có quản lý việc nhận message hay không.
- Message được acknowledge vào thời điểm nào.
- Nếu writer ghi database, database và JMS có dùng chung transaction phối hợp hay không.
- Broker xử lý redelivery và delivery count ra sao sau rollback.

Nếu chỉ có JMS transaction mà database transaction riêng, rollback của một resource không nhất thiết rollback resource còn lại. Muốn atomic giữa nhiều resource cần cơ chế phối hợp transaction phù hợp, hoặc thiết kế xử lý theo hướng idempotent/outbox/inbox.

Không nên giả định việc đặt `readerIsTransactionalQueue()` tự tạo transaction cho queue. Reader, connection factory, session và transaction manager phải được cấu hình nhất quán.

## 8. Retry và skip ảnh hưởng đến item đã đọc

Khi exception xảy ra trong processor hoặc writer, transaction chunk có thể rollback. Các item đã đọc vẫn phải được xử lý theo retry/skip policy.

- **Retry:** framework thử lại thao tác hoặc chunk theo policy. Với reader thông thường, các item đã buffer có thể được sử dụng lại.
- **Skip:** nếu exception thuộc skip policy và giới hạn cho phép, item lỗi được loại khỏi kết quả; các item còn lại tiếp tục xử lý.
- **Retry hết giới hạn:** nếu exception không được skip, Step thất bại. Khi restart sau đó, reader dựa vào checkpoint đã commit để đọc lại phần chưa hoàn tất.

Đặc biệt với write-skip, writer có thể được gọi lại với tập item nhỏ hơn để cô lập item lỗi. Không nên giả định một item chỉ đi qua writer một lần.

Nếu reader là transactional queue, message có thể được broker redeliver sau rollback. Nếu reader không transactional, framework thường sử dụng buffer. Hiểu đúng loại reader giúp tránh cả việc mất item lẫn xử lý trùng.

## 9. Reader đã đọc item không có nghĩa item đã được xử lý thành công

Một item có thể đã được `read()` nhưng chưa được ghi thành công. Các khái niệm cần phân biệt:

| Mốc | Ý nghĩa |
|---|---|
| Đã đọc | Reader đã trả item cho framework |
| Đã process | Processor đã trả output hoặc filter item |
| Đã write | Writer đã hoàn tất lời gọi ghi cho item/chunk |
| Đã commit | Transaction của chunk đã commit thành công |
| Đã checkpoint | Trạng thái reader/stream tương ứng đã được lưu để restart |

`read()` trả item không có nghĩa dữ liệu đã được commit. Tương tự, writer kết thúc bình thường không nhất thiết có nghĩa toàn bộ side effect ngoài transaction đã được xác nhận bền vững cùng transaction của Step.

Khi quan sát `StepExecution` counters, không nên coi `readCount` là số bản ghi nghiệp vụ đã hoàn tất. Cần xem thêm `writeCount`, filter/skip, commit/rollback và trạng thái cuối cùng của Step.

## 10. Processor và writer có thể được gọi lại

Buffer bảo vệ item đầu vào khỏi bị mất sau rollback, nhưng nó không làm các thành phần xử lý trở nên idempotent. Processor hoặc writer có thể được gọi lại trong các lần retry/recovery tùy fault-tolerance configuration.

Stateless processor thường dễ replay hơn vì cùng input và cùng quy tắc tạo cùng output. Processor có mutable state phụ thuộc lịch sử item cần xử lý rollback và concurrency cẩn thận.

Writer ghi database trong cùng transaction có thể được rollback cùng chunk. Writer gọi API, gửi email, ghi file hoặc publish message cần idempotency key, outbox hoặc cơ chế staging vì side effect có thể tồn tại sau rollback.

Không nên đặt side effect không thể lặp an toàn trong `ItemReader.read()`. Reader nên tập trung lấy item và quản lý vị trí đọc; nếu việc đọc cũng tiêu thụ một tài nguyên transactional như queue, cần cấu hình transaction đúng thay vì tự tạo side effect ngoài transaction.

## 11. Lưu ý với reader có trạng thái và saveState

Với file reader hoặc paging reader có hỗ trợ `ItemStream`, hãy bật lưu state nếu cần restart. Tên reader và key trong ExecutionContext cần ổn định:

```java
return new FlatFileItemReaderBuilder<Order>()
        .name("ordersFileReader")
        .resource(resource)
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(Order.class)
        .saveState(true)
        .build();
```

`saveState(true)` phục vụ khôi phục qua restart, còn buffer phục vụ rollback trong process hiện tại. Hai cơ chế bổ sung cho nhau:

- Buffer giữ item của chunk đang xử lý khi rollback.
- ExecutionContext lưu checkpoint để process mới mở reader tại vị trí đã commit.

Nếu đặt `saveState(false)`, reader không lưu checkpoint riêng. Khi process bị dừng, reader có thể không tiếp tục đúng vị trí đã commit và có thể phải đọc lại từ đầu hoặc phụ thuộc vào cơ chế riêng của nguồn.

Với nguồn dữ liệu thay đổi, checkpoint cũ chỉ đúng nếu file, query, sort order hoặc snapshot vẫn tương thích. Ví dụ, file bị thay thế sau khi Job thất bại có thể khiến vị trí dòng cũ trỏ đến bản ghi khác.

## 12. Những nhầm lẫn thường gặp

**Cho rằng rollback tự rewind mọi reader.** Transaction rollback không thể tự tua ngược file, cursor hoặc API tùy ý. Với reader không transactional, framework buffer item để phát lại.

**Cho rằng item đã đọc là item đã commit.** Reader có thể đã tiến lên trong khi chunk vẫn chưa ghi thành công. Chỉ transaction commit mới xác nhận thay đổi thuộc chunk.

**Nhầm buffer với ExecutionContext.** Buffer là dữ liệu item trong bộ nhớ của chunk; ExecutionContext là metadata checkpoint được lưu để restart.

**Bật transactional queue cho mọi reader.** Tùy chọn này chỉ phù hợp khi rollback transaction thực sự trả item về queue. Với file hoặc reader thông thường, tắt buffer có thể làm mất item sau rollback.

**Cho rằng restart sau khi process chết vẫn dùng buffer cũ.** Buffer mất khi process kết thúc. Reader phải khôi phục từ checkpoint đã lưu và đọc lại phần chưa commit.

**Cho rằng reader transactional queue tự tạo transaction cho JMS.** Queue session và transaction manager phải được cấu hình đúng. Tùy chọn chỉ mô tả hành vi reader với framework.

**Cho rằng writer chỉ được gọi một lần.** Retry và skip có thể khiến writer được gọi lại. Side effect ngoài transaction cần idempotency.

## 13. Kiểm thử hành vi rollback và phát lại item

Để kiểm tra reader xử lý đúng item đã đọc trước rollback, nên mô phỏng cả reader thông thường và reader transactional:

1. Dùng reader trả A, B, C, D với chunk size 3.
2. Làm writer thất bại ở lần ghi đầu tiên.
3. Xác nhận transaction chunk rollback.
4. Xác nhận A, B, C được xử lý lại và không bị bỏ qua; sau khi commit, reader tiếp tục với D.
5. Kiểm tra processor/writer không tạo side effect trùng khi được gọi lại.
6. Dừng process sau một chunk đã commit và một chunk chưa commit; restart cùng JobInstance để xác nhận reader khôi phục từ checkpoint gần nhất.
7. Với transactional queue, làm rollback việc nhận message và xác nhận broker redeliver message; kiểm tra framework không đồng thời phát lại cùng message từ buffer.

Các test cần dùng transaction manager và resource có hành vi rollback thực tế. Với JMS, nên kiểm tra trên broker hoặc test container phù hợp; mock đơn thuần có thể không mô phỏng chính xác redelivery và acknowledgement.

## 14. Cách thiết kế an toàn cho item đã đọc trước rollback

Trước tiên, xác định reader có transactional hay không. Với file, database cursor/paging hoặc reader thông thường, giữ cơ chế buffer mặc định để framework phát lại item của chunk khi rollback. Bật `saveState` và dùng ExecutionContext nếu cần khôi phục sau khi process bị dừng. Với JMS hoặc transactional queue, bảo đảm thao tác nhận message tham gia transaction rollback và cấu hình reader transactional queue đúng với phiên bản Spring Batch.

Sau đó, thiết kế processor và writer để chịu được việc xử lý lại. Dùng transaction chung cho dữ liệu database khi có thể; dùng idempotency key, outbox hoặc staging cho side effect ngoài transaction. Cuối cùng, kiểm thử cả rollback trong cùng process lẫn restart sau process failure. Khi phân biệt đúng buffer, checkpoint và transaction của nguồn đọc, các item đã được đọc trước rollback sẽ không bị mất và cũng không bị xử lý trùng ngoài ý muốn.
