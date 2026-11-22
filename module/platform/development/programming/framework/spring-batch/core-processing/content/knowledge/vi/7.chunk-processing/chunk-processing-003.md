# Commit interval và kích thước chunk

Trong Spring Batch, chunk-oriented processing chia dữ liệu thành những nhóm item nhỏ để đọc, xử lý và ghi theo từng lượt. **Commit interval** xác định số item được xử lý trong một chunk trước khi transaction của chunk được commit. Giá trị này thường được gọi là **chunk size**.

Ví dụ, nếu cấu hình `chunk(500, transactionManager)`, Step xử lý tối đa 500 item trong một chunk rồi ghi kết quả và commit transaction. Với một Job xử lý 100.000 item, nếu tất cả item được đọc đầy đủ và không có lỗi làm thay đổi luồng xử lý, có thể hình dung khoảng 200 chunk được commit. Chunk cuối cùng có thể nhỏ hơn nếu dữ liệu không chia hết cho 500.

Chọn kích thước chunk ảnh hưởng trực tiếp đến hiệu năng, mức sử dụng bộ nhớ, thời gian giữ transaction, khóa database và lượng công việc cần xử lý lại khi có lỗi. Không có một con số tối ưu cho mọi Job; cần dựa trên đặc điểm dữ liệu, writer, database và yêu cầu vận hành.

## 1. Chunk-oriented processing hoạt động như thế nào?

Một Step xử lý theo chunk thường có ba thành phần:

- **ItemReader:** đọc từng item từ nguồn dữ liệu như file, database hoặc message queue.
- **ItemProcessor:** tùy chọn, kiểm tra, chuyển đổi hoặc lọc từng item.
- **ItemWriter:** ghi một nhóm item đã xử lý vào đích như database hoặc file.

Luồng xử lý tổng quát:

```text
                Bắt đầu transaction
                         |
                         v
                   ItemReader
                  đọc từng item
                         |
                         v
                 ItemProcessor
                 xử lý từng item
                         |
                         v
              Đủ commit interval?
                    /       \
                  Chưa       Đủ
                   |          |
                   +-- đọc ---+
                              v
                         ItemWriter
                    ghi các item của chunk
                              |
                              v
                         Commit
                              |
                              v
                    Bắt đầu chunk tiếp theo
```

Spring Batch đọc và xử lý các item để tạo một chunk. Khi đạt commit interval hoặc nguồn dữ liệu kết thúc, framework gọi writer cho chunk đó và commit transaction nếu mọi thao tác hoàn tất thành công. Sau đó, Step tiếp tục với chunk kế tiếp cho đến khi reader báo hết dữ liệu.

Transaction thường bao quanh một chunk: các thao tác ghi thuộc chunk được commit cùng nhau. Nếu một lỗi làm transaction rollback, những thay đổi thuộc transaction đó được hoàn tác theo khả năng của transaction manager và resource tham gia. Các chunk đã commit trước đó vẫn được giữ lại.

## 2. Commit interval và chunk size có ý nghĩa gì?

Trong cấu hình Java hiện đại của Spring Batch, kích thước chunk được đặt trên `StepBuilder`:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Với `chunk(500, transactionManager)`, Spring Batch gom tối đa 500 item đầu vào cho một chunk trước khi gọi writer và commit transaction. Nếu processor lọc item bằng cách trả về `null`, writer sẽ nhận ít item hơn số item đã đọc. Nếu nguồn dữ liệu chỉ còn 120 item, chunk cuối cùng chỉ chứa 120 item thay vì chờ đủ 500.

Trong tài liệu và cấu hình cũ, khái niệm này thường được gọi là `commit-interval`. Dù tên API có khác nhau giữa cấu hình XML cũ và Java configuration, ý nghĩa vận hành vẫn là số item được xử lý trong một transaction chunk.

### Ví dụ số lượng chunk và commit

Giả sử reader cung cấp 2.350 item và chunk size là 500:

| Chunk | Item trong chunk | Kết quả |
|---|---:|---|
| 1 | 500 | Ghi và commit |
| 2 | 500 | Ghi và commit |
| 3 | 500 | Ghi và commit |
| 4 | 500 | Ghi và commit |
| 5 | 350 | Ghi và commit chunk cuối |
| **Tổng** | **2.350** | **5 lần commit chunk thành công** |

Đây là cách tính đơn giản khi không có lỗi, retry hoặc cơ chế xử lý đặc biệt. Số lần commit thực tế có thể thay đổi khi có rollback, retry, skip hoặc khi Step dừng giữa chừng.

## 3. Kích thước chunk ảnh hưởng đến transaction như thế nào?

Chunk size chính là kích thước đơn vị transaction của Step theo mô hình chunk processing. Một chunk lớn hơn thường có nghĩa transaction giữ mở lâu hơn vì cần đọc và xử lý nhiều item trước khi ghi và commit.

### Chunk nhỏ

Ví dụ `chunk(50, transactionManager)`:

- Transaction thường ngắn hơn.
- Mỗi lần rollback ảnh hưởng đến một nhóm item nhỏ hơn.
- Tần suất commit cao hơn, do đó có thêm chi phí quản lý transaction và ghi metadata.
- Writer có thể nhận các nhóm nhỏ, làm tăng số lần gọi database hoặc dịch vụ đích.

Chunk nhỏ phù hợp khi mỗi item tốn nhiều thời gian xử lý, transaction cần ngắn hoặc hệ thống đích nhạy cảm với lượng dữ liệu ghi trong một lần. Tuy nhiên, nếu chunk quá nhỏ, chi phí commit và round trip có thể chiếm tỷ lệ lớn trong tổng thời gian.

### Chunk lớn

Ví dụ `chunk(2_000, transactionManager)`:

- Số lần commit giảm nếu khối lượng dữ liệu không đổi.
- Writer có thể ghi theo nhóm lớn và tận dụng batch operation của database.
- Transaction có thể giữ connection và khóa lâu hơn.
- Chunk cần giữ nhiều item hơn trong bộ nhớ.
- Khi lỗi xảy ra trước commit, lượng công việc của chunk có thể phải thực hiện lại lớn hơn.

Chunk lớn có thể cải thiện throughput nếu writer và database xử lý tốt các lệnh theo lô. Nhưng nếu transaction quá dài, database có thể giữ khóa lâu, log transaction tăng, timeout dễ xảy ra hoặc các request trực tuyến bị ảnh hưởng.

## 4. Mối quan hệ giữa chunk size, bộ nhớ và throughput

Trong một chunk, Spring Batch cần giữ các item đang được xử lý cho đến khi writer thực hiện. Vì vậy, chunk size lớn hơn thường làm tăng lượng dữ liệu tạm thời trong bộ nhớ. Mức tăng còn phụ thuộc kích thước từng item, dữ liệu trung gian do processor tạo ra và cách reader triển khai.

Ví dụ, nếu mỗi item sau khi chuyển đổi chiếm trung bình 4 KB trong bộ nhớ, một chunk 500 item cần khoảng 2 MB dữ liệu item thô. Chunk 5.000 item có thể cần khoảng 20 MB, chưa tính object overhead, buffer, collection và tài nguyên khác. Đây chỉ là ước lượng để hình dung; kích thước thực tế của object trong JVM có thể lớn hơn đáng kể.

Throughput là số item được xử lý trong một đơn vị thời gian. Chunk size có thể tác động đến throughput theo cách sau:

- Khi chunk quá nhỏ, thời gian commit, gọi writer và round trip có thể chiếm tỷ lệ lớn.
- Khi tăng chunk, chi phí cố định trên mỗi item có thể giảm và writer có cơ hội ghi hiệu quả hơn.
- Sau một ngưỡng, throughput có thể không tăng thêm vì giới hạn chuyển sang CPU, I/O, database, mạng hoặc hệ thống đích.
- Nếu chunk quá lớn, transaction dài và áp lực bộ nhớ có thể làm hiệu năng giảm hoặc tăng nguy cơ timeout.

Do đó, không nên mặc định rằng chunk càng lớn thì Job càng nhanh. Mục tiêu là tìm vùng kích thước đạt throughput tốt trong giới hạn bộ nhớ, thời gian transaction và tải database cho phép.

## 5. Ảnh hưởng đến rollback, retry và skip

Chunk size còn quyết định phạm vi công việc được bảo vệ bởi transaction. Giả sử Step xử lý chunk 500 item. Sau khi reader và processor đã xử lý 500 item, writer bắt đầu ghi nhưng gặp lỗi khiến transaction rollback.

Các thay đổi database thuộc transaction chunk đó sẽ bị rollback. Các chunk đã commit trước đó vẫn được giữ lại. Tùy cấu hình retry/skip và loại lỗi, Spring Batch có thể thử lại chunk hoặc item, bỏ qua item lỗi nếu được phép, hoặc đánh dấu Step thất bại.

```text
Chunk 1: 500 item -> COMMIT
Chunk 2: 500 item -> COMMIT
Chunk 3: 500 item -> WRITER ERROR -> ROLLBACK
                                      |
                                      v
                           Retry / Skip / Fail
```

Chunk size 5.000 có thể khiến một lần rollback liên quan đến nhóm item lớn hơn chunk size 100. Điều này không có nghĩa toàn bộ item của chunk chắc chắn bị đọc lại trong mọi cấu hình, vì reader buffering, retry policy và checkpoint có thể ảnh hưởng hành vi. Tuy nhiên, khi thiết kế cần giả định item trong chunk lỗi có thể được xử lý lại.

Một số lưu ý:

- **Retry:** chỉ retry lỗi có khả năng tự hết, chẳng hạn lỗi kết nối tạm thời. Retry không nên tạo tác dụng phụ lặp.
- **Skip:** chỉ bỏ qua item khi nghiệp vụ cho phép; cần lưu lại item lỗi và lý do để có thể xử lý sau.
- **Rollback:** hiểu rõ resource nào tham gia transaction. Gọi API ngoài, gửi email hoặc ghi file có thể không được rollback cùng database.
- **Idempotency:** writer và các tác vụ bên ngoài nên có khóa xử lý duy nhất hoặc cơ chế chống trùng nếu item có thể được thử lại.
- **Checkpoint:** với reader hỗ trợ lưu trạng thái, Spring Batch có thể tiếp tục từ checkpoint đã commit sau khi restart.

Đặc biệt, nếu processor thực hiện tác dụng phụ như gọi dịch vụ thanh toán hoặc gửi thông báo, retry chunk có thể lặp hành động đó. Nên giữ processor thuần chuyển đổi dữ liệu nếu có thể và thực hiện tác dụng phụ ở bước ghi có cơ chế idempotent hoặc qua transactional outbox.

## 6. Chunk size không giống fetch size hoặc JDBC batch size

Một số cấu hình khác cũng có giá trị số lượng bản ghi, nhưng chúng kiểm soát các tầng khác nhau:

| Khái niệm | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| Chunk size / commit interval | Số item được xử lý trong một transaction chunk | `chunk(500, transactionManager)` |
| JDBC fetch size | Gợi ý số dòng driver lấy từ database mỗi lần fetch | `fetchSize=1_000` |
| Reader page size | Số bản ghi reader lấy trong một trang truy vấn | `pageSize=1_000` |
| JDBC batch size | Số câu lệnh ghi được gom để gửi theo batch tới database | `JdbcBatchItemWriter` hoặc cấu hình driver/framework |
| Partition size | Phạm vi dữ liệu giao cho một partition xử lý | Các khoảng ID hoặc phân đoạn file |

Các giá trị này có thể được phối hợp nhưng không cần bằng nhau. Ví dụ, chunk size là 500, reader page size là 1.000 và JDBC batch writer gom lệnh theo cách riêng. Reader có thể fetch nhiều item hơn một chunk để buffer; điều đó không làm thay đổi ranh giới commit của chunk.

Chunk size cũng không phải kích thước file, số thread hay số partition. Mỗi khái niệm giải quyết một vấn đề hiệu năng khác nhau.

## 7. Chọn chunk size như thế nào?

Không có một giá trị chuẩn cho mọi hệ thống. Có thể bắt đầu với một giá trị vừa phải, sau đó đo và điều chỉnh theo dữ liệu thực tế.

### Bước 1: Hiểu đặc điểm item và xử lý

Xác định mỗi item lớn đến đâu, processor tiêu tốn bao nhiêu CPU và writer thực hiện bao nhiêu thao tác. Nếu item chứa nhiều dữ liệu hoặc xử lý phức tạp, chunk quá lớn có thể gây áp lực bộ nhớ.

### Bước 2: Xác định giới hạn transaction

Xem database có giới hạn timeout, lock duration, transaction log hoặc connection hay không. Nếu một chunk mất quá lâu để hoàn thành, cần giảm kích thước hoặc tối ưu truy vấn và writer.

### Bước 3: Đo hiệu năng với nhiều kích thước

Có thể thử lần lượt các giá trị như 100, 250, 500 và 1.000 trên dữ liệu đại diện. Với mỗi lần chạy, ghi lại:

- Tổng thời gian hoàn thành Job.
- Số item đọc, xử lý, ghi, lọc và skip.
- Throughput (item/giây).
- Thời gian trung bình và dài nhất của một chunk.
- Số lần commit, rollback và retry.
- Heap usage, garbage collection và CPU.
- Database CPU, I/O, lock wait, connection usage và transaction duration.

Không nên chỉ đo thời gian trên một dataset rất nhỏ. Cần dùng khối lượng và phân bố dữ liệu gần với production, bao gồm cả bản ghi lớn hoặc trường hợp writer chậm.

### Bước 4: Cân bằng hiệu năng và khả năng khôi phục

Nếu chunk lớn hơn làm throughput tăng ít nhưng thời gian rollback và bộ nhớ tăng đáng kể, hãy chọn chunk nhỏ hơn. Nếu chunk nhỏ tạo quá nhiều commit và writer round trip, hãy tăng dần để tìm mức phù hợp.

### Bước 5: Đặt cấu hình theo loại Job

Không cần buộc mọi Step dùng chung một chunk size. Step import file, Step ghi database và Step gọi hệ thống ngoài có thể có đặc tính khác nhau. Chọn giá trị riêng cho từng Step dựa trên resource và transaction mà Step sử dụng.

## 8. Ví dụ so sánh hai cấu hình

Giả sử Job import 100.000 khách hàng. Writer ghi vào database và mỗi lần commit có chi phí cố định đáng kể.

| Thuộc tính | Chunk 100 | Chunk 1.000 |
|---|---:|---:|
| Số item đầu vào | 100.000 | 100.000 |
| Số chunk lý thuyết nếu chạy hết | 1.000 | 100 |
| Số lần commit chunk thành công trong trường hợp lý tưởng | 1.000 | 100 |
| Số item tối đa theo cấu hình mỗi chunk | 100 | 1.000 |
| Áp lực bộ nhớ cho item đang nằm trong chunk | Thấp hơn | Cao hơn |
| Thời gian transaction mỗi chunk | Thường ngắn hơn | Thường dài hơn |
| Phạm vi item có thể phải xử lý lại khi chunk rollback | Nhỏ hơn | Lớn hơn |

Chunk 1.000 có thể giảm số lần commit và tăng hiệu quả ghi theo lô. Tuy nhiên, nếu mỗi item xử lý chậm hoặc database giữ khóa lâu, chunk 100 có thể ổn định hơn. Kết quả thực tế phải được đo; bảng chỉ mô tả xu hướng thường gặp.

## 9. Những lưu ý khi chạy song song hoặc partitioning

Trong một Step tuần tự, các chunk thường được xử lý lần lượt. Khi bật multi-threading hoặc partitioning, nhiều chunk hoặc partition có thể được xử lý đồng thời tùy cách cấu hình và phiên bản Spring Batch.

Khi tăng mức song song:

- Mỗi chunk vẫn có ranh giới transaction riêng theo cấu hình.
- Tổng số item đang nằm trong các chunk đồng thời có thể tăng đáng kể.
- Nhiều transaction cùng ghi database có thể tranh chấp khóa và connection.
- Reader, processor và writer cần đáp ứng yêu cầu thread safety của mô hình thực thi.
- Chunk size lớn kết hợp nhiều thread có thể tạo tải đột biến lên database.

Ví dụ, nếu có 4 worker xử lý đồng thời và mỗi worker có chunk size 1.000, có thể có hàng nghìn item đang được giữ trong các chunk cùng lúc. Vì vậy, cần điều chỉnh cả chunk size, số worker, connection pool và giới hạn tài nguyên của hệ thống đích.

Partitioning chia tập dữ liệu thành các phạm vi độc lập; chunk size bên trong mỗi partition vẫn quyết định số item của từng transaction. Không nên nhầm partition size với commit interval.

## 10. Các lỗi thường gặp khi chọn commit interval

**Chọn chunk size quá lớn chỉ để giảm commit:** transaction dài, tăng bộ nhớ, lock duration và phạm vi retry có thể khiến Job chậm hoặc khó khôi phục hơn.

**Chọn chunk size quá nhỏ:** số lần commit và số lần gọi writer tăng, làm chi phí quản lý transaction chiếm tỷ lệ lớn.

**Cho rằng chunk size bằng JDBC fetch size:** hai cấu hình phục vụ hai tầng khác nhau. Reader có thể fetch theo trang lớn hơn hoặc nhỏ hơn chunk.

**Cho rằng một chunk luôn ghi đúng số item đã đọc:** processor có thể lọc item, skip có thể xảy ra và chunk cuối cùng có thể nhỏ hơn commit interval.

**Bỏ qua tác dụng phụ bên ngoài transaction:** rollback database không tự thu hồi email đã gửi hoặc request HTTP đã hoàn thành.

**Chỉ đo bằng thời gian tổng:** cần quan sát cả throughput, heap, GC, transaction duration, lock wait, rollback và lỗi writer.

**Dùng một chunk size cho tất cả Step:** các nguồn dữ liệu và writer khác nhau có đặc tính khác nhau; cấu hình nên dựa trên từng Step.

## Kết luận

Commit interval, hay chunk size, xác định số item được gom vào một chunk trước khi writer ghi và transaction được commit. Chunk nhỏ giúp transaction ngắn và giới hạn lượng công việc trong mỗi lần rollback, nhưng làm tăng số lần commit. Chunk lớn có thể cải thiện throughput và ghi theo lô, nhưng tăng áp lực bộ nhớ, thời gian giữ transaction và lượng dữ liệu có thể phải xử lý lại. Hãy bắt đầu với một kích thước hợp lý, đo trên dữ liệu đại diện và cân bằng hiệu năng với khả năng khôi phục, tải database và yêu cầu nghiệp vụ của từng Step.
