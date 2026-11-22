# Trade-off giữa commit nhỏ và commit lớn

Trong Spring Batch, một chunk-oriented step thường gom nhiều item thành một chunk, đọc và xử lý chúng, gọi writer rồi commit transaction. Số item được gom trước mỗi lần commit thường được cấu hình bằng **chunk size** hay **commit interval**. Chọn commit nhỏ hay lớn ảnh hưởng trực tiếp đến thông lượng, thời gian giữ khóa, mức sử dụng bộ nhớ, chi phí transaction và khả năng phục hồi khi có lỗi.

Commit nhỏ giúp transaction ngắn và giới hạn số item phải rollback khi chunk thất bại. Đổi lại, ứng dụng phải thực hiện nhiều transaction và nhiều lần commit hơn. Commit lớn giảm số lần commit và có thể tận dụng batch write tốt hơn, nhưng transaction kéo dài, giữ tài nguyên lâu hơn và có thể phải xử lý lại một nhóm item lớn hơn khi lỗi xảy ra.

Không có một commit interval phù hợp cho mọi job. Giá trị nên được chọn dựa trên kích thước dữ liệu, đặc điểm reader/writer, database, yêu cầu phục hồi và kết quả đo trên workload đại diện.

## 1. Commit interval trong chunk-oriented processing

Với chunk-oriented step, Spring Batch đọc một nhóm item, chuyển từng item qua processor nếu có, rồi gửi các item đầu ra cho writer. Khi chunk hoàn tất thành công, transaction được commit và step bắt đầu chunk tiếp theo.

Ví dụ, cấu hình chunk size là 100:

1. Reader đọc tối đa 100 item cho chunk hiện tại.
2. Processor chuyển đổi hoặc lọc từng item.
3. Writer ghi các item đầu ra còn lại.
4. Nếu chunk thành công, transaction commit.
5. Step tiếp tục đọc nhóm tiếp theo.

Trong Spring Batch 5, có thể cấu hình bằng `StepBuilder`:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderRecord> processor,
        ItemWriter<OrderRecord> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, OrderRecord>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Đối số `100` là commit interval. Các phiên bản Spring Batch cũ có thể dùng API cấu hình step khác, nhưng ý nghĩa của commit interval vẫn là số item đầu vào được gom trong một chunk trước khi commit.

Chunk cuối có thể nhỏ hơn giá trị cấu hình khi reader hết dữ liệu. Ngoài ra, số item writer nhận có thể ít hơn số item reader đọc vì processor có thể trả về `null` để filter item hoặc một số item bị skip theo chính sách.

## 2. Commit nhỏ là gì?

Commit nhỏ nghĩa là mỗi transaction xử lý một nhóm item tương đối nhỏ, ví dụ 10, 25 hoặc 50 item. Nếu chunk size là 20 và job có 10.000 item đầu vào, trong trường hợp không có filter hoặc skip, step sẽ thực hiện khoảng 500 chunk và khoảng 500 lần commit thành công.

```text
Chunk size = 20

Transaction 1:  item 1  - 20    -> COMMIT
Transaction 2:  item 21 - 40    -> COMMIT
Transaction 3:  item 41 - 60    -> COMMIT
...
Transaction N:  nhóm item cuối -> COMMIT
```

Mỗi transaction giữ phạm vi công việc nhỏ. Khi một chunk lỗi và phải rollback, các thay đổi chưa commit trong chunk đó được hoàn tác nếu chúng thuộc cùng transaction. Các chunk trước đã commit vẫn được giữ.

### Lợi ích của commit nhỏ

**Transaction ngắn hơn.** Database giữ khóa và các tài nguyên transaction trong khoảng thời gian ngắn hơn. Điều này có thể giảm thời gian chờ khóa và giảm khả năng nhiều transaction lớn tranh chấp cùng dữ liệu.

**Giới hạn phạm vi rollback.** Nếu chunk hiện tại thất bại, chỉ nhóm thao tác chưa commit trong transaction đó bị rollback. Với chunk nhỏ, lượng dữ liệu phải thực hiện lại thường ít hơn.

**Checkpoint thường xuyên hơn.** Khi chunk commit thành công, Spring Batch có thể lưu metadata và reader state tại ranh giới commit. Chunk nhỏ tạo ra nhiều điểm lưu tiến độ hơn, giúp khoảng công việc cần đọc lại sau sự cố thường ngắn hơn.

**Giảm dữ liệu tạm trong bộ nhớ.** Reader và processor thường chỉ cần giữ một nhóm item đang xử lý. Chunk nhỏ có thể giảm dung lượng object và dữ liệu tạm cần giữ trong heap.

**Phù hợp với thao tác ghi có độ trễ biến động.** Nếu writer có những lần ghi kéo dài hoặc dữ liệu có mức tranh chấp cao, chunk nhỏ có thể giới hạn thời gian một transaction giữ tài nguyên.

### Chi phí của commit nhỏ

**Nhiều lần commit hơn.** Mỗi transaction có chi phí bắt đầu, hoàn tất, đồng bộ trạng thái và giao tiếp với database. Với database từ xa, độ trễ mạng và thời gian commit có thể chiếm phần đáng kể trong tổng thời gian job.

**Nhiều lần cập nhật metadata hơn.** Spring Batch cần cập nhật trạng thái step và execution context tại các ranh giới chunk. Chunk quá nhỏ làm số lần cập nhật metadata tăng lên.

**Khó tận dụng batch write lớn.** Một số writer và database hoạt động hiệu quả hơn khi nhận một nhóm nhiều bản ghi. Nếu chunk quá nhỏ, lợi ích của batch insert/update có thể giảm.

**Tăng overhead điều phối.** Với cùng một số lượng item, chunk nhỏ làm framework phải đi qua vòng lặp transaction và xử lý chunk nhiều lần hơn.

Commit từng item là một trường hợp cực nhỏ. Nó có thể hữu ích khi mỗi item phải độc lập về transaction, nhưng thường tạo nhiều overhead nếu workload có thể ghi theo nhóm.

## 3. Commit lớn là gì?

Commit lớn nghĩa là mỗi transaction bao phủ một nhóm item tương đối lớn, ví dụ 500, 1.000 hoặc 5.000 item. Với 10.000 item và chunk size 1.000, nếu không có filter hoặc skip, step chỉ cần khoảng 10 chunk thay vì 500 chunk với size 20.

```text
Chunk size = 1,000

Transaction 1:  item 1      - 1,000  -> COMMIT
Transaction 2:  item 1,001  - 2,000  -> COMMIT
Transaction 3:  item 2,001  - 3,000  -> COMMIT
...
Transaction N:  nhóm item cuối       -> COMMIT
```

Mỗi lần commit hoàn tất một lượng công việc lớn hơn. Điều này có thể cải thiện thông lượng nếu chi phí commit đáng kể và hệ thống đích hỗ trợ ghi theo lô.

### Lợi ích của commit lớn

**Giảm số lần commit.** Chi phí cố định của transaction và round-trip tới database được phân bổ trên nhiều item hơn. Đây là lợi ích rõ nhất khi database ở xa hoặc mỗi lần commit có độ trễ đáng kể.

**Tận dụng batch write.** Writer có thể gửi một nhóm lớn bản ghi trong một lần batch insert/update. Giảm số lần gọi database có thể cải thiện thông lượng.

**Giảm số lần cập nhật metadata.** Ít chunk hơn đồng nghĩa với ít lần cập nhật trạng thái step và checkpoint hơn.

**Giảm overhead điều phối trên mỗi item.** Framework xử lý ít đơn vị chunk hơn cho cùng một tập dữ liệu.

### Chi phí của commit lớn

**Transaction kéo dài hơn.** Các khóa và tài nguyên database có thể được giữ lâu hơn. Transaction dài có thể làm tăng lock wait, deadlock hoặc ảnh hưởng tới các giao dịch trực tuyến dùng chung dữ liệu.

**Phạm vi rollback lớn hơn.** Nếu writer thất bại gần cuối chunk, toàn bộ thao tác thuộc transaction chunk có thể bị rollback. Một nhóm lớn item có thể phải được đọc và xử lý lại.

**Tăng mức dùng bộ nhớ.** Chunk giữ nhiều item hơn trước khi writer hoàn tất. Nếu mỗi item có object graph lớn hoặc processor tạo nhiều dữ liệu tạm, heap và áp lực garbage collection có thể tăng.

**Tăng áp lực lên transaction log.** Một transaction lớn có thể tạo lượng thay đổi chưa commit lớn, làm tăng nhu cầu undo/redo hoặc write-ahead log và ảnh hưởng khả năng phục hồi của database. Chi tiết phụ thuộc hệ quản trị cơ sở dữ liệu.

**Dễ chạm giới hạn vận hành.** Transaction lớn có thể vượt timeout, giữ connection lâu, tăng thời gian chờ tài nguyên hoặc làm cho thao tác restart sau lỗi kéo dài hơn.

## 4. So sánh trực tiếp commit nhỏ và commit lớn

| Tiêu chí | Commit nhỏ | Commit lớn |
|---|---|---|
| Số lần commit | Nhiều | Ít |
| Chi phí transaction trên mỗi item | Có thể cao hơn | Thường thấp hơn khi overhead commit đáng kể |
| Thời gian giữ khóa | Thường ngắn hơn | Có thể dài hơn |
| Phạm vi rollback | Nhỏ hơn | Lớn hơn |
| Khoảng cách giữa checkpoint | Ngắn hơn | Dài hơn |
| Dữ liệu tạm trong bộ nhớ | Thường ít hơn | Có thể nhiều hơn |
| Khả năng tận dụng batch write | Có thể hạn chế nếu quá nhỏ | Có thể tốt hơn nếu writer/database hỗ trợ |
| Áp lực transaction log | Nhiều transaction nhỏ | Transaction ít hơn nhưng mỗi transaction có thể lớn |
| Khả năng ảnh hưởng workload khác | Có thể giảm lock duration | Có thể tăng contention nếu giữ khóa lâu |
| Phù hợp | Dữ liệu tranh chấp, item lớn, cần rollback nhỏ | Ghi theo lô, overhead commit cao, tài nguyên đủ |

Các nhận xét trên là xu hướng thường gặp, không phải bảo đảm cho mọi workload. Ví dụ, commit nhỏ không tự động làm job nhanh hơn nếu database bị giới hạn bởi số lần round-trip; commit lớn cũng không tự động tăng throughput nếu transaction gây lock contention hoặc GC pressure.

## 5. Ví dụ tính số lần commit

Giả sử job cần xử lý 100.000 item đầu vào và không có filter hoặc skip. Số chunk xấp xỉ bằng tổng số item chia cho chunk size, làm tròn lên.

| Chunk size | Số chunk/commit thành công ước tính |
|---:|---:|
| 10 | 10.000 |
| 50 | 2.000 |
| 100 | 1.000 |
| 500 | 200 |
| 1.000 | 100 |
| 5.000 | 20 |

Giảm chunk size từ 1.000 xuống 100 làm số transaction tăng khoảng 10 lần trong ví dụ này. Điều đó không có nghĩa thời gian chạy tăng đúng 10 lần, vì thời gian đọc, xử lý và ghi dữ liệu cũng chiếm một phần tổng thời gian. Nhưng nếu mỗi lần commit có chi phí cố định lớn, sự khác biệt có thể đáng kể.

Ngược lại, tăng chunk size từ 100 lên 5.000 giảm số lần commit nhưng mỗi transaction có lượng dữ liệu chưa commit lớn hơn 50 lần. Cần bảo đảm database, bộ nhớ và thời gian transaction chịu được mức đó.

Nếu processor filter item, số item writer nhận sẽ thấp hơn số item đầu vào. Tuy nhiên, commit interval thường dựa trên số item được đọc để tạo chunk, không phải số item writer ghi thành công. Vì vậy, không nên dùng `writeCount` đơn lẻ để suy ra chính xác số chunk đã chạy.

## 6. Trade-off về thông lượng

Thông lượng là số item được xử lý trong một đơn vị thời gian. Chunk size ảnh hưởng đến thông lượng qua hai nhóm chi phí:

1. **Chi phí theo item:** đọc dữ liệu, xử lý nghiệp vụ, chuyển đổi object và ghi từng bản ghi.
2. **Chi phí theo chunk/transaction:** bắt đầu transaction, commit, cập nhật metadata, gọi writer và đồng bộ trạng thái.

Khi chunk quá nhỏ, chi phí theo chunk được lặp lại nhiều lần. Khi chunk lớn dần, chi phí này được chia đều cho nhiều item hơn. Vì vậy, thông lượng thường cải thiện khi tăng chunk size từ một giá trị quá nhỏ lên mức hợp lý.

Tuy nhiên, sau một điểm, lợi ích có thể chững lại hoặc giảm. Database có thể bị giới hạn bởi I/O, lock contention, transaction log hoặc khả năng batch statement. JVM có thể tăng GC pause do giữ nhiều object hơn. Khi đó, tăng chunk size không còn mang lại lợi ích.

Có thể hình dung xu hướng thường gặp:

```text
Thông lượng
   ^
   |                 _________
   |              __/         \_
   |           __/               \_
   |        __/
   |     __/
   |____/____________________________> Chunk size
       quá nhỏ     phù hợp       quá lớn
```

Đây chỉ là hình minh họa. Đường cong thực tế có thể tăng đều, đạt plateau hoặc giảm ở các ngưỡng khác nhau tùy workload và database.

## 7. Trade-off về lock và concurrency

Một transaction lớn có thể giữ khóa lâu hơn vì nhiều thao tác ghi cùng nằm trong một transaction. Nếu job cập nhật các bản ghi mà ứng dụng trực tuyến cũng thường xuyên truy cập, thời gian giữ khóa dài có thể làm tăng thời gian chờ của request.

Với nhiều worker hoặc partition chạy đồng thời, tác động có thể rõ hơn:

- Chunk lớn làm mỗi worker giữ transaction lâu hơn.
- Các worker có thể tranh chấp cùng bảng hoặc cùng dải khóa.
- Deadlock có thể xảy ra nếu các transaction khóa tài nguyên theo thứ tự khác nhau.
- Chunk nhỏ có thể giải phóng khóa thường xuyên hơn nhưng làm số transaction đồng thời tăng.

Vì vậy, cần xem cả chunk size và concurrency. Không nên tăng số worker và chunk size cùng lúc mà không đo, vì rất khó xác định yếu tố nào gây contention.

Nếu có thể, hãy phân vùng dữ liệu để mỗi worker ghi một phạm vi không giao nhau, chẳng hạn theo tenant, ngày nghiệp vụ hoặc dải ID. Dù vậy, các bảng tổng hợp hoặc khóa dùng chung vẫn có thể trở thành điểm tranh chấp.

## 8. Trade-off về rollback và restart

Giả sử job xử lý 1 triệu giao dịch. Sau khi 900.000 item đã được commit, chunk tiếp theo thất bại.

- Với chunk size 100, phạm vi transaction hiện tại chỉ khoảng 100 item.
- Với chunk size 5.000, phạm vi transaction hiện tại có thể lên tới 5.000 item.

Nếu writer dùng transaction database đúng cách, các thao tác chưa commit của chunk thất bại được rollback. Các chunk trước đã commit vẫn còn. Khi restart, Spring Batch dùng `JobRepository` và `ExecutionContext` để tiếp tục từ checkpoint phù hợp nếu reader hỗ trợ lưu state.

Chunk nhỏ tạo checkpoint thường xuyên hơn nên lượng công việc chưa được checkpoint thường ít hơn. Chunk lớn làm khoảng cách giữa checkpoint xa hơn, do đó có thể cần đọc và xử lý lại nhiều item hơn sau crash.

Tuy nhiên, restart không có nghĩa mọi thao tác chỉ xảy ra một lần. Reader có thể đọc lại item của chunk chưa commit. Writer có thể được gọi lại. Nếu writer gửi request tới hệ thống ngoài transaction, cần idempotency key, unique business key hoặc transactional outbox để tránh tác dụng phụ trùng.

Một job có nhiều chunk commit không phải là một transaction duy nhất bao trùm toàn bộ job. Nếu job thất bại ở chunk thứ 900, các chunk đã commit trước đó vẫn được giữ. Nếu nghiệp vụ yêu cầu chỉ công bố toàn bộ kết quả khi mọi dữ liệu đã xử lý xong, có thể ghi vào bảng staging rồi thực hiện bước publish/swap sau khi job hoàn tất.

## 9. Trade-off về bộ nhớ và garbage collection

Chunk size ảnh hưởng đến số lượng object được giữ đồng thời. Nếu mỗi input item chiếm trung bình 4 KB trong heap và processor tạo thêm output object tương đương, một chunk 100 item có thể giữ lượng dữ liệu nhỏ hơn đáng kể so với chunk 5.000 item.

Đây chỉ là ước lượng trực giác: object header, collection, tham chiếu, buffer của reader/writer, dữ liệu tạm và cache có thể làm footprint thực tế lớn hơn nhiều. Cũng cần xem processor có giữ tham chiếu tới item sau khi xử lý hay không.

Chunk lớn có thể làm tăng:

- Số object input/output tồn tại cùng lúc.
- Dung lượng collection mà writer nhận.
- Buffer của JDBC batch hoặc serializer.
- Tần suất và thời gian garbage collection nếu heap chịu áp lực.

Nếu item có payload lớn, một chunk 1.000 item có thể tốn bộ nhớ hơn nhiều so với 1.000 ID nhỏ. Hãy đo heap và GC trên dữ liệu đại diện, không chọn chunk size chỉ dựa vào số lượng item.

## 10. Transaction log và giới hạn database

Database cần theo dõi thay đổi của transaction để hỗ trợ commit, rollback và phục hồi sau sự cố. Tùy hệ quản trị, transaction lớn có thể tạo lượng undo/redo hoặc write-ahead log đáng kể và giữ các phiên bản dữ liệu lâu hơn.

Một transaction quá lớn có thể:

- Tăng lượng log chưa được giải phóng cho tới khi transaction kết thúc.
- Làm rollback mất nhiều thời gian.
- Gây áp lực lên vùng lưu trữ log hoặc cơ chế replication.
- Giữ khóa và phiên bản dữ liệu lâu hơn.
- Tạo thời gian phục hồi dài hơn sau lỗi.

Commit nhỏ hơn phân tán thay đổi thành nhiều transaction, nhưng tăng số lần commit và số record transaction metadata. Cần đo theo database cụ thể, vì mỗi hệ quản trị có cách quản lý log và tối ưu transaction khác nhau.

## 11. Chọn chunk size theo đặc điểm writer

Không phải writer nào cũng có cùng đặc tính.

| Loại writer | Điều cần cân nhắc |
|---|---|
| `JdbcBatchItemWriter` | Có thể hưởng lợi từ nhóm ghi đủ lớn; cân bằng với transaction duration và batch size của driver |
| Writer gọi stored procedure | Thời gian mỗi lần gọi, lượng dữ liệu procedure xử lý và khả năng rollback |
| Writer tạo tệp | Buffer, kích thước output và việc ghi tệp có tham gia transaction hay không |
| Writer gọi REST API | Độ trễ mạng, giới hạn rate, timeout và idempotency; transaction database không rollback được request đã nhận |
| Writer gửi message | Cơ chế transaction của broker, outbox và khả năng gửi lặp |

Với writer JDBC, chunk size và batch size của driver có thể tương tác với nhau. Ví dụ, chunk size 1.000 không bảo đảm driver gửi đúng một batch duy nhất; writer hoặc driver có thể chia nhỏ batch theo cấu hình riêng.

Với writer gọi API từ xa, không nên chọn chunk lớn chỉ để giảm số lần commit nếu mỗi item vẫn tạo một request riêng và transaction bị giữ trong lúc chờ mạng. Cân nhắc gom request theo batch API, tách bước gửi thông điệp hoặc dùng outbox.

## 12. Một quy trình chọn commit interval

Có thể chọn chunk size theo quy trình thực nghiệm sau:

### Bước 1: Xác định yêu cầu vận hành

Làm rõ thời gian hoàn thành mong muốn, lượng dữ liệu tối đa, giới hạn bộ nhớ, transaction timeout, mức ảnh hưởng cho hệ thống trực tuyến và yêu cầu restart.

### Bước 2: Chọn giá trị khởi đầu vừa phải

Chọn một giá trị như 100 hoặc 500 làm baseline. Đây chỉ là điểm bắt đầu để đo, không phải giá trị mặc định đúng cho mọi hệ thống.

### Bước 3: Chạy trên dữ liệu đại diện

Dùng dữ liệu có kích thước item, phân bố lỗi và mức tranh chấp gần production. Một tập dữ liệu quá nhỏ hoặc hoàn toàn sạch có thể không bộc lộ chi phí thực tế.

### Bước 4: Đo các chỉ số

Ghi nhận:

- Tổng thời gian job và item/giây.
- Thời gian trung bình và percentile của mỗi chunk.
- Thời gian commit và số lần commit.
- Heap usage, allocation rate và GC pause.
- Lock wait, deadlock, connection pool usage.
- Transaction log growth và tải database.
- `rollbackCount`, retry count, skip count và thời gian phục hồi khi thử nghiệm lỗi.

### Bước 5: Thử các mức tăng/giảm có kiểm soát

Thử lần lượt 50, 100, 250, 500, 1.000 hoặc các mức phù hợp với workload. Mỗi lần chỉ thay đổi một yếu tố để biết nguyên nhân tác động. Không nhất thiết phải thử mọi giá trị.

### Bước 6: Chọn theo giới hạn thực tế

Chọn giá trị đạt throughput cần thiết mà vẫn nằm trong giới hạn memory, transaction duration, lock wait và khả năng phục hồi. Nếu hai giá trị có thông lượng gần nhau, thường nên ưu tiên giá trị có transaction ngắn và vận hành dễ dự đoán hơn.

### Bước 7: Kiểm tra với lỗi có kiểm soát

Trong môi trường test, mô phỏng lỗi writer giữa một chunk và xác nhận rollback, checkpoint, restart và idempotency hoạt động đúng. Hiệu năng tốt khi không có lỗi chưa đủ để chứng minh commit interval phù hợp.

## 13. Ví dụ điều chỉnh cho hai workload

### Workload A: nhập dữ liệu ít tranh chấp bằng JDBC batch

Một job nhập 500.000 bản ghi vào bảng staging. Database chủ yếu dành cho batch, writer dùng batch insert và item nhỏ.

Chunk size 500 hoặc 1.000 có thể là điểm thử hợp lý vì giảm số lần commit và tận dụng batch write. Nếu tăng lên 5.000 mà throughput không cải thiện nhưng transaction duration, heap hoặc log growth tăng, nên giữ giá trị nhỏ hơn.

### Workload B: cập nhật số dư tài khoản dùng chung với hệ thống trực tuyến

Một job cập nhật số dư cho các tài khoản mà request trực tuyến cũng có thể cập nhật. Lock contention là rủi ro chính.

Chunk size 50 hoặc 100 có thể là điểm thử ban đầu để giới hạn thời gian giữ khóa. Tuy nhiên, nếu mỗi chunk quá nhỏ làm commit overhead cao, cần đo và thử mức lớn hơn. Có thể cần phân vùng theo tài khoản hoặc sắp xếp thứ tự ghi ổn định để giảm tranh chấp.

Hai ví dụ cho thấy cùng một framework nhưng chính sách commit phụ thuộc bản chất workload và hệ thống đích.

## 14. Commit policy và transaction timeout

Chunk size không phải giới hạn thời gian transaction. Một chunk 100 item có thể mất vài mili giây nếu writer nhanh, nhưng cũng có thể mất nhiều phút nếu processor hoặc writer chờ dịch vụ ngoài.

Transaction timeout là một cấu hình riêng của transaction manager/transaction attribute. Cần bảo đảm thời gian xử lý chunk bình thường nằm trong giới hạn timeout có dự phòng, đồng thời xử lý được trường hợp một chunk bị treo do I/O.

Nếu chunk thường xuyên chạm timeout:

- Đo riêng thời gian reader, processor và writer.
- Xác định có gọi API hoặc query chậm bên trong transaction hay không.
- Giảm chunk size nếu một nhóm quá lớn.
- Tối ưu query và batch write.
- Cấu hình timeout phù hợp với yêu cầu vận hành, không chỉ tăng timeout để che nghẽn.

Tăng transaction timeout mà không hiểu nguyên nhân có thể làm transaction giữ khóa lâu hơn và khiến sự cố khó phục hồi hơn.

## 15. Commit nhỏ hay lớn khi có retry và skip?

Retry và skip làm thay đổi chi phí thực tế của một chunk.

Khi writer thất bại và retry toàn chunk, chunk lớn có thể phải thực hiện lại nhiều công việc hơn. Khi fault-tolerant step cần cô lập item lỗi trong một chunk, framework có thể rollback rồi gọi writer nhiều lần với các nhóm nhỏ hơn. Nếu chunk ban đầu lớn, quá trình xác định item lỗi có thể tốn nhiều lần ghi thử.

Chunk nhỏ thường giới hạn số item bị ảnh hưởng trong một lỗi, nhưng nếu lỗi xuất hiện thường xuyên thì số lần retry và transaction cũng tăng. Vì vậy, không nên chỉ tối ưu commit interval dựa trên luồng thành công; hãy đo với tỷ lệ lỗi thực tế.

Skip policy cũng cần được thiết kế theo loại lỗi. Không dùng skip để che lỗi database hoặc lỗi cấu hình. Với dữ liệu không hợp lệ có thể bỏ qua, cần ghi nhận item lỗi và theo dõi skip count để bảo đảm kết quả nghiệp vụ chấp nhận được.

## 16. Mỗi chunk commit không có nghĩa toàn bộ job nguyên tử

Một hiểu nhầm thường gặp là nếu mỗi chunk được transaction bảo vệ, toàn bộ job sẽ có tính all-or-nothing. Thực tế, mỗi chunk là một transaction riêng. Khi chunk thứ 100 thất bại, các chunk 1 đến 99 đã commit vẫn còn.

Nếu nghiệp vụ chấp nhận kết quả từng phần và có thể restart, đây là mô hình phù hợp. Nếu nghiệp vụ yêu cầu chỉ công bố toàn bộ dữ liệu khi tất cả bước hoàn tất, có thể dùng:

- **Staging table:** ghi dữ liệu vào vùng tạm, kiểm tra đầy đủ rồi publish sang bảng chính.
- **Versioned data:** ghi một phiên bản mới và chuyển con trỏ phiên bản khi job hoàn tất.
- **Swap/rename:** tạo output mới rồi thay thế output đang được sử dụng sau khi xác nhận thành công.
- **Compensation:** nếu không thể rollback nhiều hệ thống, thiết kế thao tác bù để khôi phục trạng thái nghiệp vụ.

Không nên cố giữ một transaction duy nhất cho hàng triệu item chỉ để đạt all-or-nothing nếu điều đó làm database và ứng dụng không thể vận hành ổn định.

## 17. Những nguyên tắc cần nhớ

- Commit interval là số item đầu vào được gom trong một chunk trước khi transaction commit.
- Commit nhỏ tạo nhiều transaction và checkpoint hơn, giảm phạm vi rollback và thường giảm thời gian giữ khóa; đổi lại tăng commit overhead và metadata updates.
- Commit lớn giảm số lần commit, có thể tăng throughput và tận dụng batch write; đổi lại transaction dài, dùng nhiều bộ nhớ và rollback nhiều item hơn.
- Chunk size không nhất thiết bằng số item writer ghi vì processor có thể filter và step có thể skip item.
- Chunk cuối có thể nhỏ hơn commit interval khi reader hết dữ liệu.
- Các chunk đã commit vẫn tồn tại nếu chunk sau thất bại; chunk-oriented job không phải một transaction nguyên tử duy nhất.
- Transaction timeout là cấu hình riêng; chunk nhỏ vẫn có thể chạy lâu nếu một item thực hiện I/O chậm.
- Writer ngoài transaction cần idempotency hoặc cơ chế phối hợp như outbox để tránh tác dụng phụ trùng khi retry/restart.
- Đo throughput, chunk latency, commit time, heap/GC, lock wait, transaction log và rollback trước khi chọn giá trị.
- Thử nghiệm với dữ liệu đại diện và mô phỏng lỗi để xác nhận cả hiệu năng lẫn khả năng phục hồi.

Chọn commit interval là bài toán cân bằng giữa chi phí transaction và chi phí giữ một transaction lớn. Giá trị phù hợp là giá trị đáp ứng throughput cần thiết trong giới hạn bộ nhớ, database và thời gian phục hồi, đồng thời giữ hành vi rollback/restart có thể dự đoán được.
