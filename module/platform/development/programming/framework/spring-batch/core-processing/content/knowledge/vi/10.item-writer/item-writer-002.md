# Write nhận danh sách item

Trong chunk-oriented processing, `ItemWriter` nhận một nhóm item đã được reader đọc và processor xử lý. Writer ghi nhóm item đó tới đích như database, file hoặc dịch vụ bên ngoài. Nó không được gọi riêng cho từng item theo cách thông thường; Spring Batch gom các item thành một chunk rồi chuyển chunk cho writer.

Vì vậy, khi đọc hoặc triển khai phương thức `write`, cần hiểu hai điểm: writer làm việc theo nhóm và kiểu tham số của phương thức phụ thuộc phiên bản Spring Batch. Trong Spring Batch 5, writer nhận `Chunk`; trong Spring Batch 4, API cũ nhận `List`.

## 1. ItemWriter nhận một nhóm item

Trong một step chunk-oriented, Spring Batch đọc item, chuyển từng item qua processor (nếu có), rồi gọi writer với các item đầu ra của chunk hiện tại.

```text
ItemReader
    |
    v
Đọc item 1, item 2, ... item N
    |
    v
ItemProcessor (từng item)
    |
    v
Nhóm item đầu ra của chunk
    |
    v
ItemWriter.write(chunk)
    |
    v
Ghi dữ liệu đích
    |
    v
Transaction commit
```

Ví dụ, nếu commit interval là 100, step thường gom tối đa 100 item đầu ra để ghi trong một chunk. Writer được gọi một lần cho nhóm đó, sau đó transaction của chunk được commit nếu các thao tác thành công. Khi tiếp tục xử lý nguồn, Spring Batch tạo các chunk tiếp theo và gọi writer nhiều lần.

Writer cần xử lý tất cả item có trong nhóm được truyền vào. Không nên giả định một lần gọi `write` tương ứng với toàn bộ dữ liệu của job.

## 2. Kiểu tham số write trong Spring Batch 5

Trong Spring Batch 5, interface `ItemWriter<T>` định nghĩa phương thức nhận `Chunk`:

```java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

`Chunk<? extends T>` chứa các item đầu ra mà writer cần ghi. Có thể duyệt trực tiếp chunk hoặc lấy danh sách item qua `getItems()`.

Ví dụ writer ghi đơn hàng:

```java
public class OrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public OrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                "INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL) VALUES (?, ?, ?)",
                order.id(),
                order.customerId(),
                order.total()
            );
        }
    }
}
```

Ví dụ trên minh họa cách duyệt từng item trong chunk. Trong ứng dụng có lượng dữ liệu lớn, có thể dùng JDBC batch operation hoặc writer có sẵn của Spring Batch để giảm số lần round-trip tới database. Dù cách ghi bên trong là từng câu lệnh hay batch SQL, hợp đồng bên ngoài vẫn là nhận cả chunk.

### Lấy danh sách item từ Chunk

Nếu API hoặc thư viện ghi dữ liệu cần một `List`, có thể dùng `chunk.getItems()`:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    List<? extends Order> orders = chunk.getItems();

    for (Order order : orders) {
        // Ánh xạ và ghi order
    }
}
```

`getItems()` trả về danh sách các item trong chunk hiện tại. Writer có thể truyền danh sách này cho một thư viện persistence hoặc dùng để xây dựng batch request. Hãy tránh sửa danh sách hoặc thay đổi item theo cách làm ảnh hưởng đến trạng thái mà các thành phần khác đang sử dụng.

## 3. Khác biệt với API Spring Batch 4

Trong Spring Batch 4, phương thức `ItemWriter` nhận `List` trực tiếp:

```java
// API cũ trong Spring Batch 4
public interface ItemWriter<T> {
    void write(List<? extends T> items) throws Exception;
}
```

Khi chuyển sang Spring Batch 5, chữ ký phương thức thay đổi sang `Chunk<? extends T>`:

```java
// API Spring Batch 5
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
```

Do đó, writer tự triển khai theo API cũ cần được cập nhật khi nâng phiên bản. Code triển khai `write(List<? extends T>)` không còn override phương thức của `ItemWriter` trong Spring Batch 5. Trong implementation mới, lấy danh sách bằng `chunk.getItems()` nếu logic hiện tại cần làm việc với List.

| Phiên bản | Chữ ký writer |
|---|---|
| Spring Batch 4.x | `write(List<? extends T> items)` |
| Spring Batch 5.x | `write(Chunk<? extends T> chunk)` |

Không nên nhầm kiểu `List` mà ứng dụng lấy từ `Chunk` với chữ ký interface. Việc writer nội bộ sử dụng List không làm thay đổi hợp đồng API của Spring Batch 5.

## 4. Khai báo writer trong một chunk step

Writer được gắn vào step thông qua builder. Generic đầu ra của chunk phải khớp với kiểu writer nhận.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> orderReader,
        ItemProcessor<OrderRow, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
}
```

Trong ví dụ này, reader cung cấp `OrderRow`, processor chuyển thành `Order`, và writer nhận chunk gồm `Order`. Nếu không dùng processor, kiểu đầu vào và đầu ra có thể giống nhau.

Khai báo generic rõ ràng giúp compiler phát hiện trường hợp writer nhận sai kiểu. Tránh raw type hoặc ép kiểu thủ công chỉ để làm code biên dịch, vì chúng che khuất lỗi hợp đồng.

## 5. Kích thước danh sách writer nhận được

Writer nhận các item còn lại sau khi processor hoàn tất. Số item trong chunk có thể nhỏ hơn commit interval vì:

- Đây là chunk cuối cùng và nguồn dữ liệu đã hết.
- Processor trả về `null` để filter một số item.
- Một số item bị skip theo fault-tolerance policy.
- Nguồn dữ liệu không đủ item để lấp đầy chunk.

Ví dụ commit interval là 5, reader đọc năm item nhưng processor filter một item. Writer có thể nhận bốn item đầu ra. Với chunk cuối, nếu nguồn chỉ còn hai item hợp lệ, writer nhận nhóm nhỏ hơn.

| Tình huống | Item reader đọc | Item processor chuyển tới writer |
|---|---:|---:|
| Chunk đầy, không filter/skip | 5 | 5 |
| Một item được filter bằng `null` | 5 | 4 |
| Hai item được filter bằng `null` | 5 | 3 |
| Chunk cuối chỉ còn hai item hợp lệ | 2 | 2 |

Vì vậy, không viết code phụ thuộc vào `chunk.size()` luôn bằng commit interval. Hãy xử lý đúng số item thực tế trong lần gọi.

## 6. Duyệt chunk và xử lý danh sách an toàn

Có hai cách thường dùng để truy cập các item:

```java
// Duyệt trực tiếp Chunk
for (Order order : chunk) {
    process(order);
}

// Hoặc lấy List
List<? extends Order> orders = chunk.getItems();
for (Order order : orders) {
    process(order);
}
```

Chọn cách phù hợp với API mà writer cần sử dụng. Nếu thư viện đích nhận `Collection`, `List` hoặc một batch request, có thể lấy `getItems()` và truyền vào. Nếu chỉ cần duyệt, dùng trực tiếp chunk sẽ tránh tạo thêm biến tham chiếu.

Không nên lưu chunk hoặc danh sách item vào một field để xử lý sau khi phương thức kết thúc. Chunk thuộc một lần xử lý cụ thể; giữ lại tham chiếu có thể làm tăng bộ nhớ, gây rò rỉ dữ liệu hoặc tạo race condition nếu step chạy đa luồng.

## 7. Ghi batch vào database

Khi ghi vào database, batch operation thường hiệu quả hơn gửi một câu lệnh riêng cho từng item. Spring JDBC hỗ trợ batch update; writer có thể ánh xạ từng phần tử trong danh sách vào prepared statement.

```java
public class JdbcOrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        List<? extends Order> orders = chunk.getItems();
        if (orders.isEmpty()) {
            return;
        }

        jdbcTemplate.batchUpdate(
            "INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL) VALUES (?, ?, ?)",
            new BatchPreparedStatementSetter() {
                @Override
                public int getBatchSize() {
                    return orders.size();
                }

                @Override
                public void setValues(PreparedStatement ps, int index) throws SQLException {
                    Order order = orders.get(index);
                    ps.setString(1, order.id());
                    ps.setString(2, order.customerId());
                    ps.setBigDecimal(3, order.total());
                }
            }
        );
    }
}
```

Đoạn code giả định `JdbcTemplate` sử dụng cùng datasource được transaction manager của step quản lý. Trong thực tế, cần xử lý khóa trùng theo chính sách nghiệp vụ, ví dụ insert mới, update hoặc upsert. Nếu writer gặp lỗi SQL, exception cần được truyền ra để Spring Batch quyết định rollback, retry hoặc skip theo cấu hình.

## 8. Writer có sẵn của Spring Batch

Không phải lúc nào cũng cần tự viết `ItemWriter`. Spring Batch cung cấp nhiều writer chuyên dụng, ví dụ:

- `JdbcBatchItemWriter`: ghi item vào database bằng JDBC batch update.
- `FlatFileItemWriter`: ghi dữ liệu ra file văn bản.
- `StaxEventItemWriter`: ghi dữ liệu XML theo sự kiện StAX.
- `CompositeItemWriter`: chuyển cùng chunk tới nhiều writer delegate.

Các writer có sẵn giúp chuẩn hóa xử lý tài nguyên, transaction hoặc state tùy loại writer. Hãy cấu hình kiểu item, SQL/field mapping, encoding, append/overwrite và lifecycle theo yêu cầu dữ liệu đích.

Ví dụ khai báo `JdbcBatchItemWriter` theo kiểu builder:

```java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL)
            VALUES (:id, :customerId, :total)
            """)
        .beanMapped()
        .build();
}
```

Ví dụ này giả định `Order` có các property `id`, `customerId` và `total` tương ứng. Nếu dùng record hoặc kiểu dữ liệu không phù hợp với property mapping, hãy chọn `itemPreparedStatementSetter` hoặc cách ánh xạ được writer hỗ trợ. Không dùng `.beanMapped()` nếu tên property không khớp placeholder.

## 9. Transaction và rollback khi write lỗi

Trong chunk-oriented step, writer thường được gọi trong transaction của chunk. Nếu writer ghi vào database cùng transaction resource với transaction manager của step, các thay đổi có thể được commit cùng chunk khi toàn bộ xử lý thành công.

Nếu writer ném exception trước commit, transaction có thể rollback. Spring Batch sau đó áp dụng chính sách fault tolerance đã cấu hình. Tùy loại lỗi, chunk có thể được retry, item có thể bị skip hoặc step kết thúc thất bại.

```text
Writer ghi item A
Writer ghi item B
Writer gặp lỗi ở item C
        |
        v
Transaction rollback
        |
        v
Chunk được recovery theo retry/skip policy
```

Điều này không có nghĩa mọi tác động của writer đều tự rollback. Nếu writer gọi HTTP API, gửi email hoặc ghi sang database khác không tham gia transaction, side effect có thể đã xảy ra dù transaction của chunk rollback. Những thao tác này cần idempotency key, outbox hoặc cơ chế đối soát để tránh thực hiện trùng khi retry/restart.

## 10. Không giả định writer chỉ được gọi một lần

Writer có thể được gọi lại khi chunk được retry hoặc recovery sau lỗi. Một lần ghi có thể đã tạo side effect bên ngoài trước khi lỗi xảy ra ở bước tiếp theo. Vì thế, writer cần có hành vi an toàn khi nhận lại cùng item.

Các cách giảm rủi ro:

1. Dùng khóa nghiệp vụ duy nhất để ngăn tạo bản ghi trùng.
2. Dùng upsert hoặc câu lệnh cập nhật có điều kiện khi phù hợp.
3. Dùng idempotency key cho request gửi sang hệ thống ngoài.
4. Ghi outbox trong cùng transaction database, sau đó xử lý thông điệp riêng.
5. Lưu trạng thái xử lý và thiết kế đối soát để phát hiện dữ liệu thiếu hoặc trùng.

Không nên tự bắt mọi exception trong `write` rồi bỏ qua. Nếu writer nuốt exception, Spring Batch có thể coi chunk là thành công và commit checkpoint dù dữ liệu chưa được ghi đầy đủ.

## 11. Thứ tự item và tính nhất quán

Thông thường, writer nhận item theo thứ tự mà pipeline tạo ra. Nếu thứ tự có ý nghĩa nghiệp vụ, ví dụ sự kiện theo thời gian hoặc các bản ghi phụ thuộc nhau, writer cần giữ thứ tự khi ghi hoặc xác định rõ cách sắp xếp.

Khi writer gửi chunk tới một hệ thống có API nhận batch, cần bảo đảm thứ tự response hoặc lỗi có thể ánh xạ lại đúng item. Nếu API chỉ trả về một kết quả chung cho cả batch, hãy hiểu rõ cơ chế partial success: một số item có thể đã ghi thành công dù request tổng thể báo lỗi.

Với database, ràng buộc unique key và foreign key thường là lớp bảo vệ quan trọng. Tuy nhiên, không nên dựa vào thứ tự thực thi SQL nếu database không cam kết thứ tự đó; hãy mô hình hóa quan hệ và transaction một cách rõ ràng.

## 12. Writer trong xử lý đa luồng và partitioning

Khi step chạy đa luồng hoặc partitioning, nhiều luồng có thể gọi writer tùy cách cấu hình. Writer có state mutable hoặc dùng tài nguyên không thread-safe cần được bảo vệ.

- Dùng writer stateless nếu có thể.
- Không giữ danh sách item của chunk vào state dùng chung.
- Đảm bảo JDBC connection được quản lý qua transaction manager, không chia sẻ một connection thủ công giữa các thread.
- Kiểm tra thứ tự ghi và ràng buộc dữ liệu khi nhiều partition cùng ghi một bảng.
- Nếu mỗi partition dùng writer riêng, bảo đảm tài nguyên được mở/đóng theo lifecycle tương ứng.

`SynchronizedItemStreamWriter` có thể giúp đồng bộ một số writer không thread-safe khi chạy đa luồng, nhưng đồng bộ có thể làm giảm throughput. Hãy ưu tiên thiết kế state và phân vùng dữ liệu phù hợp.

## 13. Các lỗi thường gặp khi triển khai write

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Triển khai `write(List)` trong Spring Batch 5 | Không override đúng API `ItemWriter` | Dùng `write(Chunk<? extends T>)` và `chunk.getItems()` khi cần List |
| Giả định mỗi lần write nhận đủ commit interval | Lỗi ở chunk cuối hoặc khi processor filter item | Dùng kích thước thực tế của chunk |
| Ghi từng item qua kết nối mới | Tăng overhead và giảm throughput | Dùng transaction manager và batch JDBC writer phù hợp |
| Nuốt exception khi ghi lỗi | Metadata có thể commit dù dữ liệu chưa ghi đủ | Ném exception để step recovery xử lý |
| Gọi API ngoài không idempotent | Retry có thể tạo side effect trùng | Dùng idempotency key hoặc outbox |
| Chia sẻ writer mutable giữa nhiều thread | Race condition hoặc dữ liệu sai | Dùng writer thread-safe hoặc state riêng |
| Mapping sai tên property hoặc cột | Ghi nhầm hoặc thiếu dữ liệu | Kiểm tra contract và test mapping |

## 14. Kiểm thử ItemWriter

Writer nên được kiểm thử độc lập với các tình huống đại diện:

1. Chunk chứa nhiều item hợp lệ và tất cả được ghi.
2. Chunk có ít item hơn commit interval.
3. Chunk cuối nhỏ hơn kích thước cấu hình.
4. Item có giá trị null hoặc vi phạm constraint theo hợp đồng.
5. Database phát sinh lỗi giữa batch write và transaction rollback đúng.
6. Cùng item được gửi lại do retry/restart và không tạo dữ liệu trùng ngoài dự kiến.
7. Nhiều thread/partition ghi đồng thời nếu job có cấu hình song song.

Integration test nên dùng database hoặc môi trường test tương thích transaction thực tế. Kiểm tra không chỉ số dòng được ghi mà còn trạng thái commit/rollback và tính idempotent của thao tác ghi.

## Kết luận

`ItemWriter` nhận một nhóm item đã qua processor và ghi nhóm đó tới đích. Với Spring Batch 5, phương thức `write` nhận `Chunk<? extends T>`; có thể duyệt trực tiếp chunk hoặc lấy danh sách bằng `chunk.getItems()`. API Spring Batch 4 cũ nhận `List<? extends T>`, vì vậy cần cập nhật chữ ký khi nâng phiên bản.

Writer phải xử lý đúng số item thực tế, giữ hợp đồng kiểu dữ liệu, tham gia transaction phù hợp và truyền lỗi ra ngoài khi không thể ghi thành công. Với side effect ngoài transaction hoặc xử lý đa luồng, cần thêm idempotency và kiểm soát state để retry/restart không tạo dữ liệu sai hoặc trùng.
