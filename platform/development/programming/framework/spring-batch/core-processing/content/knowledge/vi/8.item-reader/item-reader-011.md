# Đọc theo thứ tự và ý nghĩa của order

Trong Spring Batch, `ItemReader` cung cấp từng item cho Step theo một trình tự. Trình tự này rất quan trọng vì nó quyết định item nào được đọc trước, item nào được đọc sau và thứ tự dữ liệu đi vào processor, writer. Với một số nghiệp vụ, thứ tự chỉ ảnh hưởng cách hiển thị hoặc xuất file; với nghiệp vụ khác, thứ tự có thể làm thay đổi kết quả tính toán, cách đối soát và khả năng restart.

`ItemReader` không tự áp đặt một quy tắc sắp xếp chung cho mọi nguồn dữ liệu. Reader trả về item theo thứ tự mà nguồn hoặc cách triển khai reader cung cấp. Vì vậy, khi thứ tự có ý nghĩa, ứng dụng phải xác định rõ quy tắc order ở nguồn dữ liệu hoặc reader và bảo đảm quy tắc đó ổn định qua các lần chạy.

## 1. `ItemReader` đọc item theo thứ tự nào?

Hợp đồng cơ bản của `ItemReader<T>` là trả về một item trong mỗi lần gọi `read()`, hoặc trả về `null` khi không còn item:

```java
public interface ItemReader<T> {
    T read() throws Exception;
}
```

Ví dụ, reader đọc một nguồn gồm các item A, B, C và D:

```text
Lần gọi read()     Item được trả về
----------------------------------
1                  A
2                  B
3                  C
4                  D
5                  null (hết input)
```

Thứ tự A → B → C → D là thứ tự reader cung cấp dữ liệu. Spring Batch gọi `read()` nhiều lần để tạo chunk; framework không tự sắp xếp lại toàn bộ item theo ID, thời gian hay một thuộc tính nào đó trước khi đưa chúng vào processor.

Nguồn tạo ra thứ tự có thể là:

- Vị trí vật lý của bản ghi trong file.
- Thứ tự do câu truy vấn SQL quy định.
- Khóa sắp xếp được cấu hình cho reader phân trang.
- Thứ tự các resource/file mà một reader nhiều resource duyệt qua.
- Quy tắc do reader tùy chỉnh tự triển khai.

Nếu thứ tự không được xác định rõ, ứng dụng không nên giả định rằng dữ liệu sẽ luôn xuất hiện theo cùng một trình tự ở mọi lần chạy.

## 2. Ý nghĩa của order trong xử lý batch

Order là quy tắc xác định trình tự các item được đọc và chuyển qua pipeline xử lý. Quy tắc đó có thể mang ý nghĩa kỹ thuật hoặc nghiệp vụ.

### Thứ tự kỹ thuật

Thứ tự kỹ thuật giúp quá trình đọc có thể dự đoán và khôi phục. Ví dụ, đọc bản ghi theo khóa chính tăng dần giúp reader có một trình tự xác định; khi restart, checkpoint có thể tham chiếu đến vị trí hoặc khóa đã xử lý.

### Thứ tự nghiệp vụ

Thứ tự nghiệp vụ phản ánh cách dữ liệu phải được xử lý theo quy tắc domain. Ví dụ:

- Giao dịch tài khoản cần được áp dụng theo thời điểm phát sinh.
- Sự kiện cần được xử lý theo sequence number do hệ thống nguồn cấp.
- Các phiên bản thay đổi của một hồ sơ cần được áp dụng theo thứ tự hiệu lực.
- Báo cáo cần sắp xếp theo ngày, nhóm và mã đối tượng để dễ đối chiếu.

Không phải lúc nào khóa ID cũng biểu diễn đúng thứ tự nghiệp vụ. Một ID tăng dần có thể phản ánh thứ tự tạo bản ghi trong database, nhưng không nhất thiết là thời điểm sự kiện thực sự xảy ra. Hãy chọn thuộc tính sắp xếp theo yêu cầu nghiệp vụ.

### Thứ tự có thể ảnh hưởng kết quả

Nếu processor xử lý mỗi item độc lập, thứ tự có thể không làm thay đổi giá trị của từng item. Tuy nhiên, thứ tự vẫn có thể ảnh hưởng đến thứ tự ghi, thứ tự log hoặc thứ tự xuất file.

Nếu xử lý có trạng thái hoặc tích lũy, thứ tự có thể thay đổi trực tiếp kết quả. Ví dụ, tính số dư tài khoản bằng cách áp dụng lần lượt các giao dịch thì giao dịch ghi nợ và ghi có phải được áp dụng theo đúng thứ tự nghiệp vụ. Nếu reader trả giao dịch sai trình tự, số dư trung gian và các quy tắc kiểm tra hạn mức có thể cho kết quả khác.

## 3. Với database, phải dùng `ORDER BY` khi thứ tự quan trọng

Database quan hệ không bảo đảm thứ tự kết quả truy vấn nếu câu SQL không có `ORDER BY`. Việc một truy vấn hiện tại tình cờ trả về dữ liệu theo thứ tự ID hoặc theo một index không tạo ra cam kết về thứ tự. Execution plan, index, thống kê, phiên bản database hoặc dữ liệu thay đổi có thể làm thứ tự kết quả thay đổi.

Ví dụ truy vấn không xác định thứ tự:

```sql
SELECT id, account_id, amount, created_at
FROM transactions
WHERE status = 'READY';
```

Nếu muốn đọc giao dịch theo thời gian tạo, hãy chỉ định rõ:

```sql
SELECT id, account_id, amount, created_at
FROM transactions
WHERE status = 'READY'
ORDER BY created_at ASC, id ASC;
```

Ở đây:

- `created_at ASC` sắp xếp theo thời gian tăng dần.
- `id ASC` là khóa phụ để phân biệt những bản ghi có cùng `created_at`.

Khóa phụ rất quan trọng. Nếu chỉ `ORDER BY created_at`, nhiều bản ghi có cùng timestamp có thể xuất hiện theo thứ tự không ổn định. Bổ sung một khóa duy nhất, chẳng hạn primary key, tạo ra một thứ tự tổng (total order) có thể xác định rõ ràng.

Chiều sắp xếp cũng cần thể hiện đúng nghiệp vụ:

```sql
-- Cũ trước, mới sau
ORDER BY created_at ASC, id ASC

-- Mới trước, cũ sau
ORDER BY created_at DESC, id DESC

-- Theo nhóm, sau đó theo thời gian và khóa duy nhất
ORDER BY department_id ASC, created_at ASC, id ASC
```

Không nên dựa vào thứ tự mặc định của database hoặc thứ tự vật lý của hàng trong bảng.

## 4. Cấu hình thứ tự cho database reader

### JDBC cursor reader

Với `JdbcCursorItemReader`, ứng dụng cung cấp câu SQL cho reader. Nếu thứ tự quan trọng, câu SQL cần có `ORDER BY`:

```java
@Bean
@StepScope
JdbcCursorItemReader<TransactionInput> transactionReader(DataSource dataSource) {
    return new JdbcCursorItemReaderBuilder<TransactionInput>()
            .name("transactionReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT id, account_id, amount, created_at
                    FROM transactions
                    WHERE status = 'READY'
                    ORDER BY created_at ASC, id ASC
                    """)
            .rowMapper((rs, rowNum) -> new TransactionInput(
                    rs.getLong("id"),
                    rs.getLong("account_id"),
                    rs.getBigDecimal("amount"),
                    rs.getTimestamp("created_at").toInstant()))
            .build();
}
```

Reader lấy kết quả theo thứ tự của cursor. Câu SQL quyết định thứ tự dữ liệu; `ItemReader` lần lượt trả các hàng theo trình tự đó.

### JDBC paging reader

Với `JdbcPagingItemReader`, reader lấy dữ liệu thành từng trang. Sort keys phải được cấu hình rõ ràng để các trang nối tiếp nhau theo một thứ tự ổn định. Ví dụ với Spring Batch 5:

```java
@Bean
@StepScope
JdbcPagingItemReader<CustomerInput> customerReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .build();
}
```

Query provider cần có sort keys, ví dụ `created_at` kết hợp `id`, theo API cấu hình tương ứng với database và phiên bản. Khi dùng builder hoặc query provider, hãy bảo đảm các khóa sắp xếp đủ để phân biệt duy nhất mỗi hàng trong tập kết quả.

Nếu chỉ sắp xếp theo một cột không duy nhất, ranh giới trang có thể không ổn định. Bản ghi có cùng giá trị sort key có thể bị phân trang không nhất quán, dẫn đến đọc lặp hoặc bỏ sót khi dữ liệu thay đổi hoặc khi reader tiếp tục sang trang kế tiếp.

## 5. Thứ tự khi đọc file và nhiều resource

### FlatFileItemReader

`FlatFileItemReader` thường đọc file theo thứ tự dòng vật lý: dòng đầu, dòng tiếp theo, rồi tiếp tục đến EOF. Nếu file chứa các giao dịch đã được sắp xếp theo ngày, reader giữ trình tự đó.

Ví dụ file:

```csv
transactionId,createdAt,amount
T001,2026-11-15T08:00:00,100.00
T002,2026-11-15T08:05:00,50.00
T003,2026-11-15T08:10:00,25.00
```

Reader sẽ cung cấp T001, T002, T003 theo thứ tự dòng. Nếu file nguồn không được sắp xếp đúng, `FlatFileItemReader` không tự sắp xếp các dòng theo `createdAt`.

### MultiResourceItemReader

Khi đọc nhiều file bằng `MultiResourceItemReader`, cần xác định cả thứ tự file và thứ tự bản ghi bên trong từng file. Nếu thứ tự resource có ý nghĩa, hãy cấu hình comparator rõ ràng thay vì dựa vào thứ tự file hệ điều hành hoặc filesystem trả về.

Ví dụ, nếu cần đọc file theo ngày:

```text
transactions-2026-11-13.csv
transactions-2026-11-14.csv
transactions-2026-11-15.csv
```

Sau khi sắp xếp resource theo tên hoặc metadata ngày, reader đọc lần lượt từng file, rồi đọc từng dòng trong file đó. Cần bảo đảm quy tắc đặt tên hoặc metadata phản ánh đúng thứ tự nghiệp vụ mong muốn.

## 6. Order ảnh hưởng đến chunk và writer như thế nào?

Trong chunk processing, reader cung cấp item theo thứ tự; processor nhận từng item theo thứ tự đó; writer nhận danh sách item đã xử lý của chunk. Với Step tuần tự thông thường, thứ tự item trong chunk phản ánh thứ tự reader trả về, ngoại trừ item bị processor lọc bỏ hoặc cơ chế xử lý đặc biệt.

Ví dụ, reader trả về A, B, C, D, E với chunk size 3:

```text
Reader:      A -> B -> C -> D -> E -> null
                         |          |
                         v          v
Chunk 1:             [A, B, C]   [D, E]
                         |          |
Processor:             xử lý       xử lý
                         |          |
Writer:                 ghi        ghi
                         |          |
                      Commit     Commit
```

Nếu processor trả về `null` cho item B để lọc bỏ, B không được chuyển tới writer. Các item còn lại vẫn giữ thứ tự tương đối A, C, D, E trong luồng tuần tự.

Tuy nhiên, không nên mặc định mọi writer đều bảo toàn thứ tự quan sát được ở đích. Một writer có thể ghi vào database mà không có thứ tự truy vấn mặc định; database không cam kết thứ tự khi đọc lại nếu không có `ORDER BY`. Nếu đầu ra cần được sắp xếp, hãy quy định thứ tự ở truy vấn đọc hoặc tạo output theo một cơ chế bảo đảm thứ tự rõ ràng.

## 7. Order và restart: vì sao phải ổn định?

Spring Batch có thể lưu checkpoint của reader trong `ExecutionContext`. Khi Job thất bại và được restart, reader dùng trạng thái đã lưu để tiếp tục từ vị trí phù hợp. Khả năng này phụ thuộc reader hỗ trợ lưu/khôi phục trạng thái và dữ liệu đầu vào giữ được tính nhất quán.

Giả sử một reader đã xử lý đến bản ghi có `id=500` theo thứ tự `created_at, id`. Nếu giữa lần chạy và lần restart, dữ liệu nguồn bị thay đổi hoặc quy tắc order bị đổi, bản ghi tiếp theo có thể khác với bản ghi mà checkpoint ban đầu dự kiến.

Những thay đổi có thể gây vấn đề:

- Bản ghi mới được chèn vào trước vị trí đã đọc.
- Bản ghi đã đọc bị xóa hoặc thay đổi sort key.
- File nguồn bị thay thế hoặc sắp xếp lại.
- Câu SQL đổi từ `ORDER BY created_at, id` sang `ORDER BY id`.
- Cột sắp xếp không duy nhất khiến thứ tự giữa các bản ghi đồng hạng thay đổi.

Kết quả có thể là đọc lặp, bỏ sót item hoặc xử lý dữ liệu theo trình tự khác với lần chạy ban đầu. Vì vậy:

1. Giữ câu SQL và sort keys ổn định qua các lần restart.
2. Dùng khóa sắp xếp duy nhất hoặc thêm tie-breaker duy nhất.
3. Nếu có thể, xử lý một snapshot dữ liệu bất biến hoặc một tập dữ liệu được giới hạn bằng cutoff/watermark.
4. Không thay thế file đầu vào giữa các lần chạy; có thể lưu file theo version hoặc checksum.
5. Thiết kế writer idempotent để giảm tác hại nếu item cần được đọc lại.

Với paging reader, việc dữ liệu thay đổi trong khi phân trang đặc biệt cần chú ý. Offset/page number có thể bị dịch chuyển khi bản ghi được thêm hoặc xóa. Dùng snapshot hoặc điều kiện phạm vi ổn định giúp kết quả phân trang nhất quán hơn. Với nguồn lớn thay đổi liên tục, có thể cân nhắc keyset-based paging theo khóa sắp xếp ổn định, tùy reader và query provider được sử dụng.

## 8. Order và xử lý song song

Trong Step tuần tự, reader trả item theo thứ tự và chunk được xử lý theo trình tự đó. Khi chuyển sang multi-threaded Step, partitioning hoặc remote chunking, thứ tự hoàn thành có thể khác thứ tự đọc ban đầu.

Ví dụ, hai worker nhận hai phần dữ liệu:

```text
Nguồn theo thứ tự: 1 2 3 4 5 6
                     |       |
                     v       v
                  Worker A Worker B
                  1 2 3     4 5 6
                     |       |
                     v       v
                  Hoàn tất  Hoàn tất
                  sau  B    trước A

Thứ tự hoàn tất có thể là: 4 5 6 1 2 3
```

Nếu writer hoặc hệ thống đích nhận dữ liệu ngay khi từng worker hoàn tất, thứ tự output toàn cục có thể không còn giống thứ tự nguồn. Điều này bình thường trong xử lý song song.

Nếu nghiệp vụ bắt buộc giữ thứ tự toàn cục:

- Có thể giữ Step tuần tự nếu throughput đáp ứng yêu cầu.
- Có thể gắn sequence number vào item và sắp xếp/merge kết quả ở bước sau.
- Có thể partition theo phạm vi không chồng lấn nhưng vẫn cần bước hợp nhất theo khóa thứ tự.
- Tránh dùng một reader không thread-safe từ nhiều thread nếu reader không hỗ trợ mô hình đó.

Không nên dựa vào thời gian worker hoàn tất để suy ra thứ tự nghiệp vụ. Thứ tự cần được thể hiện bằng khóa hoặc metadata rõ ràng.

## 9. Phân biệt thứ tự item với `@Order` và thứ tự Step

Trong Spring, từ “order” có thể xuất hiện ở nhiều ngữ cảnh. Cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Thứ tự item trong ItemReader | Trình tự reader trả về từng bản ghi |
| SQL `ORDER BY` | Quy tắc sắp xếp các hàng trong kết quả truy vấn |
| Sort keys của paging reader | Khóa xác định thứ tự và phân trang kết quả |
| Thứ tự Step trong Job | Trình tự hoặc flow mà Job điều khiển các Step |
| Spring `@Order` / `Ordered` | Thứ tự ưu tiên khi Spring sắp xếp một số bean hoặc thành phần được hỗ trợ |

`@Order` trên một bean không tự động sắp xếp các item do `ItemReader` trả về. Tương tự, thứ tự Step trong Job không quyết định thứ tự bản ghi bên trong một Step. Muốn sắp xếp item, phải cấu hình nguồn dữ liệu hoặc logic reader phù hợp.

## 10. Cách thiết kế thứ tự đọc đáng tin cậy

Khi xây dựng một Job, hãy bắt đầu bằng việc xác định thứ tự có ý nghĩa gì đối với nghiệp vụ:

1. **Chọn trường sắp xếp đúng:** dùng thời điểm hiệu lực, sequence number, mã kỳ hoặc khóa phù hợp với domain.
2. **Tạo thứ tự xác định:** nếu trường chính không duy nhất, thêm khóa phụ duy nhất để phá hòa.
3. **Đưa order vào nguồn đọc:** SQL `ORDER BY`, sort keys của paging reader, comparator cho danh sách file hoặc quy tắc rõ ràng trong custom reader.
4. **Giữ quy tắc ổn định:** không thay đổi thứ tự giữa lần chạy đầu và restart.
5. **Kiểm soát dữ liệu nguồn:** dùng snapshot, cutoff hoặc file version nếu nguồn có thể thay đổi trong lúc Job chạy.
6. **Đánh giá ảnh hưởng của song song:** nếu cần thứ tự toàn cục, thiết kế partition và bước merge rõ ràng.
7. **Xác định thứ tự đầu ra:** nếu kết quả được đọc lại từ database hoặc object storage, quy định order ở bước xuất/đọc kết quả thay vì giả định writer đã giữ thứ tự.

Ví dụ, với Job áp dụng giao dịch tài khoản theo thời gian phát sinh, quy tắc có thể là:

```sql
SELECT id, account_id, event_time, sequence_no, amount
FROM account_events
WHERE batch_id = :batchId
ORDER BY event_time ASC, sequence_no ASC, id ASC;
```

Trong đó `event_time` xác định thứ tự thời gian, `sequence_no` phản ánh thứ tự do hệ thống nguồn cấp và `id` là tie-breaker cuối cùng để bảo đảm thứ tự duy nhất. Điều kiện `batch_id` giúp giới hạn vào một lô dữ liệu ổn định.

## 11. Các lỗi thường gặp

**Cho rằng database tự trả hàng theo ID:** nếu không có `ORDER BY`, thứ tự kết quả không được bảo đảm.

**Chỉ sắp xếp theo cột không duy nhất:** các hàng có cùng giá trị sort key có thể đổi vị trí giữa các lần đọc hoặc các trang. Hãy thêm tie-breaker duy nhất.

**Dùng ID thay cho thứ tự nghiệp vụ mà không kiểm tra:** ID có thể không phản ánh thời điểm hiệu lực hoặc thứ tự sự kiện.

**Đổi sort key giữa các lần restart:** checkpoint cũ có thể không còn trỏ đến vị trí đúng trong trình tự mới.

**Nghĩ rằng `ItemReader` tự sort:** reader thường cung cấp dữ liệu theo nguồn hoặc cấu hình; nó không tự sắp xếp mọi loại input.

**Nhầm `@Order` với order của item:** `@Order` điều khiển thứ tự bean trong những ngữ cảnh Spring hỗ trợ, không thay thế `ORDER BY` hay sort keys của reader.

**Mong thứ tự toàn cục khi chạy song song:** worker có thể hoàn tất không theo thứ tự phân công. Nếu cần thứ tự cuối cùng, phải thiết kế cơ chế merge hoặc sort.

## Kết luận

Thứ tự đọc là trình tự `ItemReader` cung cấp item cho Step. `ItemReader` không tự định nghĩa một quy tắc order chung; thứ tự đến từ file, truy vấn database, sort keys của paging reader hoặc logic custom reader. Khi thứ tự quan trọng, hãy xác định rõ ý nghĩa nghiệp vụ, dùng `ORDER BY` hoặc comparator phù hợp và thêm khóa phụ duy nhất để tạo thứ tự ổn định. Giữ nguyên thứ tự nguồn qua restart, kiểm soát thay đổi dữ liệu và lưu ý xử lý song song có thể làm thay đổi thứ tự hoàn tất. `@Order` của Spring và thứ tự Step là những khái niệm riêng, không tự sắp xếp item trong reader.
