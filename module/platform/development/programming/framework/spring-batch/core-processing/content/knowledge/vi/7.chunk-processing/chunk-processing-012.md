# Đảm bảo reader, processor và writer cùng hợp đồng

Trong chunk-oriented processing, `ItemReader`, `ItemProcessor` và `ItemWriter` tạo thành một pipeline xử lý dữ liệu. Ba thành phần phải thống nhất về kiểu dữ liệu và ý nghĩa của dữ liệu đi qua từng ranh giới. Reader cung cấp item đầu vào, processor nhận đúng kiểu đó và tạo item đầu ra, còn writer phải chấp nhận kiểu đầu ra của processor.

Có thể biểu diễn hợp đồng kiểu tổng quát như sau:

```text
ItemReader<I>
     | đọc một item kiểu I
     v
ItemProcessor<I, O>
     | chuyển I thành O, hoặc trả null để filter
     v
ItemWriter<O>
     | ghi một Chunk gồm các item kiểu O
     v
Dữ liệu đích
```

Điều cần thống nhất không chỉ là generic type. Các thành phần còn phải hiểu giống nhau về trường dữ liệu, đơn vị đo, định dạng, null, khóa định danh, thứ tự, lỗi và ranh giới transaction. Nếu một thành phần thay đổi ý nghĩa dữ liệu mà thành phần kế tiếp không biết, job có thể biên dịch thành công nhưng vẫn ghi sai dữ liệu.

## 1. Hợp đồng giữa ba thành phần

Ba interface chính trong Spring Batch có vai trò và kiểu dữ liệu riêng:

| Thành phần | Hợp đồng | Trách nhiệm |
|---|---|---|
| `ItemReader<I>` | `read()` trả về `I` hoặc `null` khi hết dữ liệu | Đọc từng item đầu vào |
| `ItemProcessor<I, O>` | Nhận `I`, trả về `O` hoặc `null` để loại item | Kiểm tra, lọc hoặc chuyển đổi dữ liệu |
| `ItemWriter<O>` | Nhận một `Chunk<? extends O>` | Ghi nhóm item đầu ra |

Trong Spring Batch 5, phương thức writer nhận `Chunk`:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}

public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}

public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Điểm nối kiểu dữ liệu phải khớp:

- Kiểu `I` của `ItemProcessor<I, O>` phải tương thích với kiểu item mà reader trả về.
- Kiểu `O` của processor phải tương thích với kiểu item mà writer nhận.
- Kiểu khai báo ở `chunk<I, O>(...)` của step phải mô tả đúng đầu vào và đầu ra của pipeline.

Các generic giúp compiler phát hiện nhiều lỗi kết nối ngay khi biên dịch. Tuy nhiên, generic không thể kiểm tra rằng `amount` đang là VND hay USD, timestamp là UTC hay giờ địa phương, hoặc `customerId` có thật sự là khóa nghiệp vụ duy nhất. Những quy tắc đó cần được mô tả và kiểm tra trong hợp đồng dữ liệu.

## 2. Khai báo chunk step với kiểu đầu vào và đầu ra

Trong Spring Batch 5, builder của step khai báo hai kiểu dữ liệu của pipeline bằng `.<I, O>chunk(size, transactionManager)`.

Ví dụ một job nhập dữ liệu khách hàng: reader đọc một dòng CSV thành `CustomerRow`, processor chuyển thành đối tượng `Customer` đã chuẩn hóa, writer ghi `Customer` vào database.

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerRow> customerReader,
        ItemProcessor<CustomerRow, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomers", jobRepository)
        .<CustomerRow, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .build();
}
```

Trong khai báo này:

- `CustomerRow` là kiểu reader trả về và processor nhận vào.
- `Customer` là kiểu processor trả về và writer nhận vào.
- `100` là commit interval: step xử lý theo các chunk và commit theo transaction được cấu hình.

Nếu không cần biến đổi kiểu dữ liệu, có thể dùng cùng một kiểu cho cả hai tham số, ví dụ `.<Customer, Customer>chunk(100, transactionManager)`. Khi có processor chuyển đổi dữ liệu, nên khai báo rõ hai kiểu để thể hiện hợp đồng đầu vào và đầu ra.

## 3. Ví dụ một pipeline có hợp đồng rõ ràng

Đầu tiên, xác định hai mô hình dữ liệu khác nhau:

```java
public record CustomerRow(
        String customerId,
        String name,
        String email) {
}

public record Customer(
        String customerId,
        String displayName,
        String normalizedEmail) {
}
```

`CustomerRow` biểu diễn cấu trúc đọc được từ nguồn. `Customer` biểu diễn dữ liệu đã được kiểm tra và chuẩn hóa để lưu vào hệ thống đích.

Processor nhận `CustomerRow` và trả về `Customer`:

```java
@Bean
ItemProcessor<CustomerRow, Customer> customerProcessor() {
    return row -> {
        if (row.email() == null || row.email().isBlank()) {
            return null; // Bỏ qua item theo quy tắc filter
        }

        if (row.customerId() == null || row.customerId().isBlank()) {
            throw new InvalidCustomerException("Missing customer ID");
        }

        return new Customer(
            row.customerId().trim(),
            row.name() == null ? "" : row.name().trim(),
            row.email().trim().toLowerCase(Locale.ROOT)
        );
    };
}
```

Writer nhận `Chunk` chứa các `Customer` và ghi vào database:

```java
@Bean
ItemWriter<Customer> customerWriter(JdbcTemplate jdbcTemplate) {
    return chunk -> jdbcTemplate.batchUpdate(
        """
        INSERT INTO CUSTOMER (CUSTOMER_ID, DISPLAY_NAME, EMAIL)
        VALUES (?, ?, ?)
        """,
        chunk.getItems(),
        chunk.size(),
        (statement, customer) -> {
            statement.setString(1, customer.customerId());
            statement.setString(2, customer.displayName());
            statement.setString(3, customer.normalizedEmail());
        }
    );
}
```

Ví dụ writer dùng `JdbcTemplate` và giả định transaction manager của step quản lý cùng datasource JDBC. Tùy chính sách dữ liệu, câu lệnh `INSERT` có thể được thay bằng upsert hoặc thao tác khác, nhưng quy tắc xử lý khóa trùng cần được xác định rõ.

Ba thành phần khớp với nhau theo chuỗi:

```text
CSV row / CustomerRow
        |
        v
customerProcessor(CustomerRow)
        |
        v
Customer
        |
        v
customerWriter(Chunk<Customer>)
        |
        v
CUSTOMER table
```

## 4. Reader: thống nhất cấu trúc dữ liệu đầu vào

Reader chịu trách nhiệm đọc một item tại một thời điểm. Mỗi lần gọi `read()` trả về một item hoặc `null` khi không còn item nào.

Reader cần bảo đảm:

- Mỗi item trả về đúng kiểu mà processor khai báo nhận.
- Quy tắc ánh xạ cột, trường bắt buộc, encoding, delimiter và định dạng ngày/số phải rõ ràng.
- Khóa định danh của bản ghi cần được giữ nguyên để processor và writer có thể đối chiếu hoặc cập nhật đúng bản ghi.
- Quy tắc xử lý dòng lỗi phải nhất quán: ném exception, chuyển thành đối tượng lỗi hoặc bỏ qua theo chính sách đã chọn.
- Thứ tự đọc cần được xác định nếu thứ tự ảnh hưởng đến nghiệp vụ hoặc checkpoint.

Ví dụ, nếu reader ánh xạ cột `customer_code` thành `customerId`, tất cả thành phần sau phải dùng cùng ý nghĩa của trường này. Không nên để reader dùng mã nội bộ trong khi writer lại xem nó là mã khách hàng bên ngoài.

### Quy ước kết thúc và null

`null` từ `ItemReader.read()` là tín hiệu hết dữ liệu. Reader không nên trả về `null` để biểu thị một dòng dữ liệu không hợp lệ, vì Spring Batch sẽ hiểu rằng nguồn đã kết thúc và không đọc các dòng sau.

Với một bản ghi không hợp lệ, reader nên ném exception phù hợp hoặc trả về một kiểu dữ liệu đầu vào có thể biểu diễn lỗi để processor xử lý. Lựa chọn này phải được thống nhất với skip policy và yêu cầu audit.

## 5. Processor: thống nhất quy tắc biến đổi

Processor là ranh giới chuyển đổi từ kiểu đầu vào `I` sang kiểu đầu ra `O`. Processor có thể giữ nguyên kiểu, tạo kiểu mới, xác thực, làm giàu dữ liệu hoặc lọc item.

Các quy tắc cần thống nhất:

1. **Mapping:** xác định trường nguồn ánh xạ sang trường đích nào.
2. **Validation:** xác định dữ liệu nào hợp lệ và lỗi nào phải ném exception.
3. **Normalization:** thống nhất cách trim chuỗi, chuẩn hóa email, mã hóa, timezone và đơn vị.
4. **Filtering:** xác định điều kiện trả về `null` để bỏ qua item.
5. **Determinism:** với cùng một input và cùng context, kết quả nên ổn định nếu nghiệp vụ yêu cầu có thể retry/restart.
6. **Side effects:** tránh ghi database hoặc gọi dịch vụ ngoài trong processor nếu các thao tác đó có thể lặp khi retry.

### Phân biệt filter và skip

Processor trả về `null` có nghĩa item được filter có chủ đích. Đây không phải lỗi và không làm phát sinh skip exception.

Ngược lại, processor ném exception và exception đó được cấu hình trong skip policy thì item có thể được xem là skipped. Nếu exception không được phép skip, chunk có thể thất bại và transaction bị rollback.

| Hành vi processor | Ý nghĩa | Kết quả ở writer |
|---|---|---|
| Trả về một đối tượng `O` | Chấp nhận và chuyển đổi item | Writer nhận item đầu ra |
| Trả về `null` | Filter item | Writer không nhận item đó |
| Ném exception được skip policy chấp nhận | Bỏ qua item theo chính sách skip | Writer không nhận item lỗi |
| Ném exception không được skip | Xử lý chunk thất bại | Chunk không được ghi thành công |

Không dùng `null` để che giấu lỗi dữ liệu. Nếu cần biết bản ghi bị loại vì lý do gì, hãy ghi metric, audit hoặc một luồng reject riêng theo thiết kế.

## 6. Writer: thống nhất kiểu và ý nghĩa dữ liệu đầu ra

Writer nhận một `Chunk` gồm các item đã qua processor. Trong Spring Batch 5, `ItemWriter<T>.write` nhận `Chunk<? extends T>`. Writer cần hiểu chính xác kiểu và quy tắc dữ liệu mà processor tạo ra.

Ví dụ processor tạo `Customer` với email đã chuẩn hóa, writer phải ghi đúng `normalizedEmail` vào cột email đích. Nếu writer lại mong nhận `CustomerRow` hoặc giả định email chưa chuẩn hóa, hợp đồng giữa hai thành phần đã bị phá vỡ.

Writer cần quy định rõ:

- Ghi mới, cập nhật hay upsert khi khóa đã tồn tại.
- Có bảo đảm một item chỉ được ghi một lần hay không.
- Ràng buộc NOT NULL, unique key và foreign key nào phải thỏa mãn.
- Có bảo toàn thứ tự item trong chunk hay không.
- Exception nào khiến chunk rollback, exception nào có thể skip/retry.
- Những thao tác nào tham gia cùng transaction với JobRepository và những thao tác nào nằm ngoài transaction đó.

Writer không nên giả định chunk luôn có đúng số item bằng commit interval. Nếu processor filter một số item, số item writer nhận có thể ít hơn số item reader đã đọc trong chunk.

## 7. Chunk size và hợp đồng của pipeline

Chunk-oriented processing đọc, xử lý và ghi item theo nhóm. Khi đủ commit interval, Spring Batch gọi writer cho chunk hiện tại trong transaction của step. Sau khi ghi thành công, transaction được commit; nếu xảy ra lỗi, transaction có thể rollback theo cấu hình.

```text
Đọc item 1 -> Process item 1
Đọc item 2 -> Process item 2
Đọc item 3 -> Process item 3 (filter -> null)
...
Đọc item N -> Process item N
             |
             v
        ItemWriter
             |
             v
        Transaction commit
```

Vì processor có thể filter item, chunk đầu ra có thể nhỏ hơn chunk đầu vào. Writer chỉ nhận các item đã được processor chấp nhận.

Chunk size cũng ảnh hưởng đến tài nguyên và hành vi lỗi. Chunk lớn giảm số lần commit nhưng giữ nhiều item trong bộ nhớ và có thể kéo dài transaction. Chunk nhỏ thường commit thường xuyên hơn nhưng tăng overhead. Reader, processor và writer phải được thiết kế để hoạt động đúng với kích thước chunk được chọn.

## 8. Transaction, retry và idempotency

Khi writer ghi vào database được quản lý bởi transaction manager của step, lỗi trong chunk có thể khiến các thay đổi của chunk rollback. Khi retry, reader hoặc processor có thể được gọi lại tùy cơ chế fault tolerance và trạng thái đã lưu.

Do đó:

- Processor nên tránh side effect không thể rollback như gửi email, gọi thanh toán hoặc ghi sang hệ thống không tham gia transaction.
- Writer nên dùng transaction resource đúng với transaction manager của step.
- Nếu ghi ra hệ thống ngoài, cần idempotency key hoặc cơ chế outbox/đối soát để xử lý việc gọi lại.
- Quy tắc unique key và upsert phải nhất quán với cách restart/retry.
- Không giả định mỗi item chỉ được processor hoặc writer gọi đúng một lần trong mọi tình huống lỗi.

Ví dụ, nếu writer gọi API thanh toán rồi chunk rollback do lỗi database, lần retry có thể gọi API thanh toán lần nữa. Hãy dùng idempotency key dựa trên định danh giao dịch nghiệp vụ để dịch vụ nhận ra request lặp.

## 9. Skip và retry phải khớp với hợp đồng dữ liệu

Fault tolerance cho phép cấu hình exception được retry hoặc skip. Tuy nhiên, chính sách phải phản ánh ý nghĩa của lỗi:

- Lỗi tạm thời như timeout có thể phù hợp với retry có giới hạn.
- Dữ liệu không hợp lệ có thể phù hợp với skip và ghi nhận lý do.
- Lỗi vi phạm hợp đồng như sai schema hoặc sai kiểu dữ liệu diện rộng thường nên làm job dừng để tránh ghi sai hàng loạt.
- Lỗi writer do constraint có thể chỉ ra processor chưa chuẩn hóa hoặc validate đủ dữ liệu.

Ví dụ cấu hình skip trong Spring Batch 5:

```java
return new StepBuilder("importCustomers", jobRepository)
    .<CustomerRow, Customer>chunk(100, transactionManager)
    .reader(customerReader)
    .processor(customerProcessor)
    .writer(customerWriter)
    .faultTolerant()
    .skip(InvalidCustomerException.class)
    .skipLimit(50)
    .build();
```

Đoạn cấu hình chỉ minh họa chính sách skip cho loại exception đã chọn. Cần bảo đảm `InvalidCustomerException` thực sự đại diện cho lỗi có thể bỏ qua, và dữ liệu bị bỏ qua được ghi nhận đủ để xử lý sau. Không nên skip mọi `Exception` vì có thể che giấu lỗi hạ tầng hoặc lỗi hợp đồng.

## 10. Hợp đồng khi ghép nhiều processor

Khi pipeline có nhiều bước chuyển đổi, kiểu đầu ra của processor trước phải tương thích với kiểu đầu vào của processor kế tiếp.

```text
CustomerRow
    |
    v
ItemProcessor<CustomerRow, ValidatedCustomer>
    |
    v
ItemProcessor<ValidatedCustomer, EnrichedCustomer>
    |
    v
ItemProcessor<EnrichedCustomer, CustomerEntity>
    |
    v
ItemWriter<CustomerEntity>
```

Có thể dùng `CompositeItemProcessor` để ghép chuỗi processor. Cần khai báo delegate theo thứ tự và bảo đảm generic type giữa từng cặp nối tiếp khớp nhau. Nếu một delegate trả về `null`, item bị filter và các delegate tiếp theo không xử lý item đó.

Với writer có nhiều đích, có thể dùng `CompositeItemWriter` hoặc writer tùy chỉnh. Các delegate phải nhận cùng kiểu đầu ra `O`. Nếu nhiều writer ghi vào nhiều tài nguyên khác nhau, cần hiểu rõ transaction manager có quản lý được tất cả hay không; việc gọi nhiều writer không tự bảo đảm một transaction nguyên tử xuyên nhiều database.

## 11. Hợp đồng trạng thái và restart

Reader hoặc writer có trạng thái cần triển khai `ItemStream` hoặc dùng component có sẵn hỗ trợ lưu trạng thái. Spring Batch gọi các phương thức vòng đời như `open`, `update` và `close` để khôi phục hoặc lưu `ExecutionContext`.

Khi restart, reader có thể tiếp tục từ vị trí checkpoint đã commit. Vì vậy, hợp đồng dữ liệu cần ổn định qua các lần chạy: thứ tự nguồn, khóa bản ghi, định dạng dữ liệu và cách diễn giải checkpoint không nên thay đổi bất ngờ.

Nếu phiên bản mới thay đổi cấu trúc item hoặc ý nghĩa của trường nhưng vẫn dùng lại checkpoint cũ, processor/writer có thể nhận dữ liệu không còn đúng với giả định ban đầu. Khi thay đổi schema nguồn hoặc cấu trúc checkpoint, hãy có chiến lược tương thích, migration hoặc hoàn tất các JobInstance cũ trước khi triển khai.

## 12. Thread safety và tài nguyên dùng chung

Khi step chạy đa luồng hoặc dùng partitioning, reader, processor và writer có thể được gọi đồng thời tùy cách cấu hình. Không nên mặc định mọi implementation đều thread-safe.

- Reader giữ con trỏ hoặc trạng thái mutable cần được bảo vệ hoặc dùng một instance riêng cho từng partition.
- Processor nên tránh mutable shared state; nếu cần cache hoặc counter, phải có đồng bộ phù hợp.
- Writer cần kiểm tra khả năng concurrent write, unique key và thứ tự commit.
- Các delegate dùng chung giữa partition cần được đánh giá về thread safety và vòng đời.

Với reader không thread-safe, có thể cần partitioning với state riêng hoặc decorator đồng bộ phù hợp. Đồng bộ hóa một reader có thể làm giảm song song, vì vậy nên chọn mô hình dựa trên tính chất nguồn dữ liệu và yêu cầu throughput.

## 13. Các lỗi hợp đồng thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Reader trả `A` nhưng processor khai báo nhận `B` | Không biên dịch hoặc phải ép kiểu không an toàn | Khai báo generic `ItemProcessor<A, O>` đúng với reader |
| Processor trả `O` nhưng writer nhận kiểu khác | Không biên dịch hoặc mapping sai ở runtime nếu dùng raw type | Dùng `ItemWriter<O>` và tránh raw type |
| Dùng `null` từ reader để biểu diễn dòng lỗi | Reader bị hiểu là đã hết dữ liệu | Ném exception hoặc biểu diễn lỗi bằng kiểu dữ liệu rõ ràng |
| Dùng `null` từ processor để biểu diễn lỗi | Item bị filter âm thầm | Ném exception và cấu hình skip/retry nếu phù hợp |
| Writer giả định chunk luôn đầy | Xử lý sai khi item bị filter hoặc cuối nguồn | Duyệt đúng các item thực tế trong chunk |
| Processor thay đổi timezone hoặc đơn vị mà không quy định | Dữ liệu đầu ra sai nhưng vẫn hợp lệ về kiểu | Định nghĩa rõ format, timezone và đơn vị trong hợp đồng |
| Processor hoặc writer tạo side effect không idempotent | Retry/restart có thể tạo thao tác trùng | Dùng transaction, idempotency key hoặc outbox |
| Nhiều component dùng chung state không thread-safe | Race condition và dữ liệu sai | Dùng state riêng, đồng bộ hoặc partitioning phù hợp |

## 14. Cách kiểm tra hợp đồng giữa các thành phần

Có thể kiểm tra pipeline ở nhiều mức:

1. **Compile-time:** dùng generic cụ thể cho reader, processor, writer và step; tránh raw type hoặc ép kiểu không cần thiết.
2. **Unit test reader:** xác nhận mapping, encoding, thứ tự, dữ liệu cuối nguồn và cách báo lỗi.
3. **Unit test processor:** xác nhận mapping đầu ra, normalization, validation, filter bằng `null` và exception.
4. **Unit test writer:** xác nhận writer nhận đúng kiểu, ghi đủ item, xử lý khóa trùng và phản ứng khi persistence lỗi.
5. **Integration test step:** chạy với JobRepository và transaction manager phù hợp, xác nhận chunk commit/rollback, skip, retry và restart.
6. **Contract test dữ liệu:** kiểm tra schema, kiểu cột, nullability, đơn vị đo, timezone và khóa nghiệp vụ giữa nguồn và đích.

Một bộ test hữu ích nên có item hợp lệ, item bị filter, item lỗi validation, chunk cuối không đủ kích thước, lỗi ghi giữa chunk và trường hợp restart từ checkpoint.

## Kết luận

Reader, processor và writer cần nối với nhau bằng một hợp đồng rõ ràng: `ItemReader<I>` cung cấp kiểu đầu vào, `ItemProcessor<I, O>` chuyển đổi sang kiểu đầu ra, và `ItemWriter<O>` ghi các item đầu ra theo chunk. Generic type phải khớp, còn quy tắc về schema, null, validation, định danh, transaction, retry và restart phải được thống nhất về mặt nghiệp vụ.

Khi hợp đồng được xác định rõ, compiler có thể bắt lỗi kiểu dữ liệu sớm, test có thể xác nhận từng ranh giới, và job có thể xử lý lỗi hoặc restart mà không làm sai ý nghĩa dữ liệu.
