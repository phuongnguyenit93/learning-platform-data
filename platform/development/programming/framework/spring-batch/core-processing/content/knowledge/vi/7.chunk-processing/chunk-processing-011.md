# Khi chunk processing phù hợp hơn tasklet

Trong Spring Batch, cả chunk-oriented processing và Tasklet đều là cách xây dựng một `Step`. Điểm quyết định lựa chọn là bản chất của công việc. Chunk processing phù hợp hơn khi Step cần xử lý một luồng nhiều item theo chu trình đọc, xử lý và ghi, cần commit theo nhóm, theo dõi tiến độ theo item hoặc áp dụng chính sách skip/retry ở cấp bản ghi.

Tasklet phù hợp với một hành động hoặc quy trình độc lập như gọi stored procedure, dọn dữ liệu tạm, kiểm tra điều kiện, di chuyển tệp hoặc gọi một service một lần. Tasklet vẫn có thể lặp và tự quản lý checkpoint, nhưng nếu phải tự xây dựng vòng lặp đọc, xử lý, ghi, phân trang, retry, skip và khôi phục cho hàng nghìn hoặc hàng triệu bản ghi, chunk processing thường diễn đạt đúng mô hình hơn và tận dụng được cơ chế có sẵn của Spring Batch.

## 1. Nhận diện công việc phù hợp với chunk processing

Chunk processing chia dữ liệu thành các nhóm item. Trong mỗi chunk, Spring Batch thực hiện các bước chính:

1. `ItemReader` đọc item tiếp theo từ nguồn dữ liệu.
2. `ItemProcessor` xử lý từng item, chẳng hạn kiểm tra, chuẩn hóa, tính toán hoặc chuyển đổi dữ liệu.
3. `ItemWriter` nhận các item đã xử lý và ghi chúng theo nhóm.
4. Khi chunk hoàn tất, transaction được commit. Nếu xử lý gặp lỗi cần rollback, transaction hiện tại được hoàn tác theo chính sách đã cấu hình.
5. Step tiếp tục với chunk kế tiếp cho đến khi reader báo hết dữ liệu.

```text
Nguồn dữ liệu
     |
     v
  ItemReader
     |
     v
 ItemProcessor -- từng item
     |
     v
  ItemWriter -- cả chunk
     |
     v
 Commit transaction
     |
     +------> Chunk tiếp theo
```

Ví dụ, một Job nhập 500.000 giao dịch từ tệp CSV. Mỗi giao dịch cần được kiểm tra mã tài khoản, tính phí, chuẩn hóa ngày và lưu vào database. Đây là một luồng item rõ ràng: mỗi giao dịch đi qua cùng pipeline, nhưng nhiều giao dịch được ghi và commit cùng nhau. Chunk processing phù hợp hơn một Tasklet tự viết vòng lặp cho toàn bộ tệp.

## 2. Khi cần xử lý nhiều item theo cùng một pipeline

Đây là dấu hiệu quan trọng nhất để chọn chunk processing. Công việc thường có ba trách nhiệm có thể tách biệt:

- **Đọc:** lấy item từ CSV, database, message source hoặc một nguồn dữ liệu khác.
- **Xử lý:** áp dụng quy tắc cho từng item mà không phải điều phối toàn bộ Job.
- **Ghi:** lưu các item hợp lệ vào database, tệp hoặc hệ thống đích.

Các tình huống thường phù hợp:

- Import hàng nghìn dòng CSV và lưu thành các bản ghi nghiệp vụ.
- Đọc bảng staging, chuẩn hóa từng dòng và ghi vào bảng chính.
- Chuyển đổi dữ liệu từ định dạng cũ sang định dạng mới.
- Đồng bộ danh sách khách hàng hoặc sản phẩm giữa hai hệ thống.
- Tính thuế, phí hoặc số dư cho từng giao dịch.
- Xuất dữ liệu theo từng bản ghi sang tệp hoặc hệ thống đích.
- Gọi một dịch vụ cho từng item rồi lưu kết quả xử lý.

Nếu mỗi item có thể được mô tả bằng một đầu vào, một bước xử lý và một kết quả, chunk processing tạo ra cấu trúc dễ hiểu. `ItemReader`, `ItemProcessor` và `ItemWriter` có thể được kiểm thử và thay đổi độc lập.

Tasklet vẫn có thể gọi service để xử lý danh sách item, nhưng khi logic bên trong đã trở thành một pipeline lặp theo từng bản ghi, ứng dụng phải tự điều phối vòng lặp và các cơ chế liên quan. Đó là dấu hiệu nên chuyển sang chunk processing.

## 3. Khi cần commit theo nhóm

Chunk processing phù hợp khi nghiệp vụ chấp nhận một nhóm item được xử lý trong cùng một transaction. Commit interval xác định số item trong một chunk, ví dụ:

```java
.<OrderInput, Order>chunk(500, transactionManager)
```

Với commit interval 500, Spring Batch gom tối đa 500 item trong một chunk trước khi commit. Chunk cuối có thể ít hơn nếu nguồn dữ liệu đã hết. Một lần commit không có nghĩa chắc chắn writer nhận đủ 500 item: processor có thể lọc item bằng cách trả về `null`, và chính sách skip có thể bỏ qua item lỗi.

Ví dụ, khi xử lý 10.000 giao dịch với chunk size 500, Step thường có khoảng 20 chunk nếu không có lọc, skip hoặc điều kiện đặc biệt. Mỗi chunk được commit riêng. Nếu chunk thứ 12 thất bại và transaction rollback, các chunk đã commit trước đó vẫn được giữ; chunk hiện tại được xử lý theo chính sách lỗi và restart của Step.

Ranh giới transaction này hữu ích khi:

- Muốn tránh một transaction duy nhất kéo dài suốt hàng trăm nghìn bản ghi.
- Cần giới hạn lượng dữ liệu có thể phải rollback trong một lần lỗi.
- Writer hỗ trợ batch insert/update và có thể ghi hiệu quả theo nhóm.
- Cần cân bằng chi phí commit với bộ nhớ, khóa database và thời gian xử lý.

Tasklet cũng chạy trong transaction được cấu hình cho lần gọi `execute`, nhưng nếu Tasklet tự xử lý một vòng lặp dài trong một lần gọi, nó có thể tạo một transaction dài. Tasklet có thể chia thành nhiều lần gọi bằng `RepeatStatus.CONTINUABLE`, nhưng khi đó ứng dụng phải tự xác định đơn vị công việc và checkpoint. Chunk processing cung cấp sẵn đơn vị commit theo nhóm item.

## 4. Khi cần skip và retry ở cấp item

Chunk processing đặc biệt hữu ích khi dữ liệu có thể chứa một số bản ghi lỗi nhưng Job vẫn cần xử lý các bản ghi còn lại theo chính sách đã xác định.

Ví dụ:

- Một dòng CSV thiếu trường bắt buộc có thể được skip và ghi nhận vào báo cáo lỗi.
- Một giao dịch gặp lỗi database tạm thời có thể được retry.
- Một bản ghi có định dạng không hợp lệ có thể bị loại khỏi pipeline mà không làm thất bại toàn bộ Job.

Spring Batch hỗ trợ fault tolerance trong chunk step thông qua skip và retry:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(500, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Trong ví dụ, lỗi dữ liệu thuộc `InvalidOrderException` có thể được skip trong giới hạn 100 lần; lỗi truy cập dữ liệu tạm thời có thể được retry tối đa theo giới hạn cấu hình. Cần chọn exception và giới hạn phù hợp với nghiệp vụ. Không nên skip lỗi hệ thống nghiêm trọng chỉ để Job có thể kết thúc với trạng thái thành công.

Processor cũng có thể chủ động lọc một item bằng cách trả về `null`:

```java
@Override
public Order process(OrderInput item) {
    if (item.isCancelled()) {
        return null;
    }
    return convertToOrder(item);
}
```

Item bị lọc không được chuyển đến writer và được tính trong `filterCount`. Đây là quyết định nghiệp vụ có chủ đích, khác với exception bị skip. Cả hai cần được thống kê riêng để người vận hành hiểu số bản ghi đã đọc nhưng không được ghi.

Tasklet có thể tự bắt exception, retry một thao tác hoặc ghi nhận item lỗi. Tuy nhiên, nếu cần chính sách skip/retry chuẩn hóa cho từng item, chunk step cung cấp cấu trúc rõ ràng và ít phải tự xây dựng hơn.

## 5. Khi cần restart từ checkpoint trên tập dữ liệu lớn

Một Job xử lý nhiều item có thể bị dừng do mất kết nối, timeout, máy chủ khởi động lại hoặc lỗi writer. Chunk processing phối hợp với `ExecutionContext` và các thành phần `ItemStream` để lưu trạng thái đọc/ghi và hỗ trợ restart.

Ví dụ reader đọc tệp có thể lưu vị trí hiện tại. Khi Step được restart, reader khôi phục vị trí từ ExecutionContext thay vì phải tự đọc lại toàn bộ tệp. Các reader/writer của Spring Batch có hỗ trợ lưu trạng thái cần được cấu hình và sử dụng đúng vòng đời stream.

Khả năng restart có giá trị khi:

- Tập dữ liệu lớn và thời gian chạy dài.
- Không muốn bắt đầu lại từ đầu sau khi một chunk thất bại.
- Cần biết phần dữ liệu nào đã commit.
- Nguồn dữ liệu có thứ tự ổn định hoặc có khóa để tiếp tục đọc chính xác.
- Writer có thể thực hiện lại an toàn hoặc có khóa nghiệp vụ để tránh ghi trùng.

Tasklet cũng có thể restart, nhưng thường phải tự lưu checkpoint, ví dụ trang tiếp theo, khóa cuối cùng đã xử lý hoặc offset trong tệp. Nếu Tasklet chỉ thực hiện một thao tác đơn giản và có thể chạy lại an toàn, cách đó là hợp lý. Nếu Tasklet đang tự triển khai checkpoint cho từng bản ghi, chunk processing thường là lựa chọn tự nhiên hơn.

Không nên hiểu rằng chunk tự động bảo đảm exactly-once cho mọi tác dụng phụ. Transaction database có thể rollback thay đổi trong database tham gia transaction, nhưng không thể tự hoàn tác HTTP request, email hoặc thao tác hệ thống tệp. Reader, processor và writer vẫn cần được thiết kế để chạy lại an toàn.

## 6. Khi cần theo dõi tiến độ theo item

Với chunk step, `StepExecution` ghi nhận các bộ đếm như:

| Bộ đếm | Ý nghĩa |
|---|---|
| `readCount` | Số item đọc thành công. |
| `writeCount` | Số item writer đã ghi. |
| `filterCount` | Số item processor chủ động lọc. |
| `readSkipCount` | Số item bị skip khi đọc. |
| `processSkipCount` | Số item bị skip khi xử lý. |
| `writeSkipCount` | Số item bị skip khi ghi. |
| `commitCount` | Số lần transaction commit. |
| `rollbackCount` | Số lần transaction rollback. |

Các bộ đếm này giúp theo dõi tốc độ xử lý, tỷ lệ lọc/skip và vấn đề transaction. Ví dụ, `readCount` tăng đều nhưng `writeCount` không tăng có thể cho thấy processor lọc nhiều item, writer bị chặn hoặc lỗi ghi đang được xử lý theo chính sách. Cần xem log và kết quả nghiệp vụ để hiểu đúng nguyên nhân.

Tasklet có thể tự ghi metric và tiến độ, nhưng phải tự xác định và cập nhật các số liệu đó. Nếu cần quan sát theo item, skip/retry và commit interval, chunk step có sẵn mô hình metadata phù hợp.

## 7. Ví dụ đầy đủ: import đơn hàng bằng chunk processing

Giả sử ứng dụng nhận tệp đơn hàng. Mỗi dòng có mã đơn hàng, mã khách hàng, số tiền và ngày tạo. Yêu cầu gồm:

- Đọc từng dòng trong tệp.
- Kiểm tra mã đơn hàng, mã khách hàng và số tiền.
- Chuyển dữ liệu đầu vào thành entity `Order`.
- Ghi nhiều đơn hàng vào database trong một transaction theo chunk.
- Skip một số dòng dữ liệu sai định dạng trong giới hạn cho phép.
- Có thể restart khi lỗi hạ tầng.

Đây là trường hợp chunk processing phù hợp hơn Tasklet vì công việc xoay quanh một luồng item và cần quản lý commit, skip, thống kê và checkpoint.

### Cấu hình Step

Ví dụ cấu hình theo Spring Batch 5:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(500, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(100)
            .build();
}
```

Các bean reader, processor và writer được cấu hình riêng theo nguồn dữ liệu. Với Spring Batch 5, API `ItemWriter` nhận một `Chunk` item; các writer chuẩn của framework xử lý giao diện này. Khi dùng ví dụ với Spring Batch 4, cần điều chỉnh API writer theo phiên bản.

### Processor kiểm tra và chuyển đổi dữ liệu

```java
@Component
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new Order(
                input.orderId(),
                input.customerId(),
                input.amount(),
                input.createdAt());
    }
}
```

Ví dụ dùng record `OrderInput` và constructor `Order` để minh họa. Mô hình dữ liệu thực tế có thể là class hoặc record tùy dự án. Processor không cần tự quản lý transaction của toàn bộ Job; transaction chunk do Step điều phối.

### Writer ghi theo nhóm

Writer nhận các item đã xử lý trong chunk. Có thể dùng `JdbcBatchItemWriter`, `JpaItemWriter` hoặc một writer tùy chỉnh phù hợp với database. Ví dụ cấu trúc khai báo writer:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders
                        (order_id, customer_id, amount, created_at)
                    VALUES
                        (:orderId, :customerId, :amount, :createdAt)
                    """)
            .beanMapped()
            .build();
}
```

Đoạn SQL và tên thuộc tính cần khớp với schema và model của ứng dụng. Nếu database có unique key cho `order_id`, cần xác định hành vi khi restart hoặc khi cùng tệp được gửi lại: bỏ qua, cập nhật hay báo lỗi theo quy tắc nghiệp vụ.

## 8. Khi Tasklet vẫn là lựa chọn phù hợp

Chunk processing không phải lựa chọn mặc định cho mọi Step. Tasklet thường phù hợp hơn nếu công việc không phải một pipeline item:

- Gọi một stored procedure để cập nhật bảng tổng hợp theo tập hợp.
- Xóa dữ liệu tạm trước khi import.
- Kiểm tra điều kiện tồn tại của tệp đầu vào.
- Tạo thư mục hoặc chuẩn bị tài nguyên.
- Di chuyển tệp đã xử lý sang thư mục archive.
- Gửi một thông báo tổng kết sau khi Job hoàn tất.
- Gọi một service một lần để bắt đầu hoặc chốt đợt nghiệp vụ.

Ví dụ Tasklet gọi một thủ tục cơ sở dữ liệu:

```java
@Bean
Step refreshSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("refreshSummaryStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                jdbcTemplate.update("call refresh_daily_summary()");
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Nếu database có thể xử lý toàn bộ dữ liệu bằng một câu SQL set-based hoặc stored procedure hiệu quả, Tasklet có thể phù hợp hơn việc đọc từng dòng qua Java chỉ để cập nhật một tập dữ liệu. Việc chọn Tasklet hay chunk cần dựa vào khả năng của hệ thống đích và yêu cầu theo dõi lỗi, không chỉ dựa trên số lượng dòng.

## 9. Những tình huống cần cân nhắc trước khi chọn chunk

### Một thao tác set-based có thể giải quyết toàn bộ công việc

Nếu chỉ cần chạy `UPDATE`, `DELETE` hoặc stored procedure trên một tập dữ liệu và database có thể xử lý hiệu quả, Tasklet thường đơn giản hơn. Chunk phù hợp khi từng item cần logic Java riêng, xử lý lỗi theo item hoặc cần checkpoint theo lô.

### Dữ liệu ít và thao tác đơn giản

Nếu Step chỉ đọc một giá trị cấu hình, kiểm tra một điều kiện rồi gọi một service, Tasklet có thể rõ ràng hơn. Dùng reader/processor/writer chỉ để bọc một thao tác có thể tạo thêm cấu hình không cần thiết.

### Tác dụng phụ không tham gia transaction

Nếu processor hoặc writer gọi API bên ngoài, transaction database không thể rollback lời gọi HTTP. Khi chunk rollback và retry, request ngoài có thể được gửi lại. Cần idempotency key, outbox hoặc cơ chế đối soát. Chunk vẫn có thể là lựa chọn đúng cho pipeline item, nhưng không tự giải quyết tính nhất quán xuyên hệ thống.

### Chunk size quá lớn

Chunk size lớn có thể làm tăng bộ nhớ, thời gian giữ transaction, số item phải xử lý lại khi rollback và tải lên hệ thống đích. Hãy đo hiệu năng với dữ liệu thực tế và chọn commit interval phù hợp.

### Item không có ranh giới xử lý độc lập

Nếu một thao tác cần toàn bộ tập dữ liệu cùng lúc để đưa ra kết quả, việc chia thành item có thể làm phức tạp logic hoặc phá vỡ yêu cầu nghiệp vụ. Tasklet hoặc một thao tác set-based có thể phù hợp hơn.

## 10. Chọn chunk size phù hợp

Sau khi quyết định dùng chunk processing, cần chọn commit interval. Không có một giá trị tối ưu cho mọi Job. Chunk size ảnh hưởng đến bộ nhớ, transaction, tốc độ ghi và lượng công việc phải phục hồi khi lỗi.

Các yếu tố cần xem xét:

- **Kích thước item:** item lớn làm chunk tiêu thụ nhiều bộ nhớ hơn.
- **Chi phí ghi:** writer hỗ trợ batch insert/update có thể hoạt động hiệu quả với nhóm item đủ lớn.
- **Thời gian transaction:** chunk lớn có thể giữ khóa lâu và làm tăng cạnh tranh database.
- **Chi phí rollback:** khi một chunk thất bại, số item trong chunk có thể phải đọc/xử lý lại theo chính sách.
- **Giới hạn hệ thống đích:** database, API hoặc dịch vụ có thể giới hạn kích thước batch.
- **Tần suất checkpoint:** commit thường xuyên hơn có thể giảm lượng công việc đã thực hiện nhưng chưa commit.

Có thể bắt đầu bằng một giá trị vừa phải, đo throughput, bộ nhớ, thời gian transaction và tải database, rồi điều chỉnh. Không nên tăng chunk size chỉ để giảm số lần commit nếu transaction trở nên quá dài hoặc rủi ro restart tăng.

## 11. Transaction, retry và tính idempotent

Trong chunk processing, mỗi chunk thường được thực hiện trong transaction của Step. Khi writer gặp lỗi khiến transaction rollback, thay đổi trong transaction hiện tại được hoàn tác nếu tài nguyên tham gia transaction đó. Những chunk đã commit trước đó vẫn được giữ lại.

Tuy nhiên, một số thao tác có thể được thực hiện lại khi rollback/retry. Reader có thể đọc lại item; processor có thể được gọi lại; writer có thể thử ghi lại. Vì vậy:

- Processor nên tránh tác dụng phụ không thể hoàn tác.
- Writer nên dùng khóa duy nhất hoặc cơ chế upsert phù hợp khi có thể ghi lại cùng item.
- API ngoài nên hỗ trợ idempotency key nếu một item có thể kích hoạt request nhiều lần.
- Không giả định email, HTTP call hoặc thao tác tệp được rollback cùng transaction database.
- Ghi nhận item lỗi và kết quả skip để có thể đối soát.

Nếu cần phát sự kiện cùng với transaction database, có thể cân nhắc transactional outbox. Writer ghi dữ liệu và outbox trong cùng transaction; một tiến trình khác phát sự kiện từ outbox theo cơ chế retry an toàn.

## 12. Kết hợp Tasklet và chunk trong cùng Job

Một Job không cần chỉ dùng một kiểu Step. Có thể dùng Tasklet cho các thao tác chuẩn bị và kết thúc, còn chunk processing đảm nhiệm phần xử lý từng item:

```text
Job: import-orders
  |
  v
Tasklet Step: kiểm tra tệp và chuẩn bị staging
  |
  v
Chunk Step: đọc, validate, chuyển đổi và ghi đơn hàng
  |
  v
Tasklet Step: lưu báo cáo và archive tệp
```

Ví dụ:

- Tasklet đầu tiên kiểm tra tệp đầu vào, tạo batch record và chuẩn bị bảng staging.
- Chunk Step đọc từng dòng, validate, chuyển đổi và ghi dữ liệu.
- Tasklet cuối cùng tạo báo cáo tổng kết, di chuyển tệp đã xử lý và cập nhật trạng thái batch.

Cách tổ chức này giữ cho mỗi Step có một trách nhiệm rõ ràng. Nếu phần xử lý dữ liệu cần commit theo nhóm, skip/retry và checkpoint, hãy đặt nó trong chunk step. Nếu một thao tác chỉ cần chạy một lần như chuẩn bị hoặc archive, Tasklet thường phù hợp hơn.

## 13. Quy trình ra quyết định

Khi thiết kế Step, có thể dùng các câu hỏi sau:

1. Công việc có xử lý nhiều item từ một nguồn dữ liệu không? Nếu có, cân nhắc chunk processing.
2. Mỗi item có cần đọc, kiểm tra/chuyển đổi và ghi theo cùng một pipeline không? Nếu có, chunk thường phù hợp.
3. Cần commit theo nhóm và giới hạn transaction không? Nếu có, chunk cung cấp commit interval.
4. Cần skip/retry một số item lỗi mà vẫn xử lý các item còn lại không? Nếu có, chunk có cơ chế fault tolerance ở cấp item.
5. Cần checkpoint và theo dõi tiến độ trên tập dữ liệu lớn không? Nếu có, chunk cùng ItemStream/ExecutionContext là lựa chọn tự nhiên.
6. Công việc chỉ là một thao tác độc lập hoặc một câu SQL set-based? Nếu có, Tasklet thường phù hợp hơn.
7. Một Step có nhiều giai đoạn khác bản chất không? Nếu có, tách thành các Step và kết hợp Tasklet với chunk processing.

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Đọc tệp lớn, validate từng dòng và lưu database | Chunk processing |
| Chuyển đổi từng bản ghi từ bảng staging sang bảng đích | Chunk processing |
| Skip bản ghi sai định dạng và retry lỗi ghi tạm thời | Chunk processing |
| Cần commit mỗi nhóm item và restart theo checkpoint | Chunk processing |
| Tính toán riêng cho từng giao dịch rồi ghi kết quả | Chunk processing |
| Gọi một stored procedure tổng hợp toàn bộ dữ liệu | Tasklet |
| Dọn bảng tạm hoặc kiểm tra một điều kiện trước Job | Tasklet |
| Di chuyển tệp sau khi import thành công | Tasklet |

## Kết luận

Chunk processing phù hợp hơn Tasklet khi công việc có một luồng nhiều item cần đọc, xử lý và ghi theo nhóm; cần ranh giới transaction rõ ràng, skip/retry ở cấp item, thống kê tiến độ hoặc restart bằng checkpoint. Tasklet phù hợp với hành động độc lập hoặc thao tác cấp hệ thống không cần pipeline item. Một Job có thể kết hợp hai loại Step để phần xử lý dữ liệu tận dụng chunk processing, còn các thao tác chuẩn bị và hoàn tất được tổ chức bằng Tasklet.
