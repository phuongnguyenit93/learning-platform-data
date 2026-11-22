# Reader xử lý input rỗng

Trong Spring Batch, một reader có thể gặp nguồn dữ liệu không có bản ghi: file CSV chỉ có header, truy vấn database không trả về dòng nào, thư mục đầu vào chưa có file hoặc một partition không có dữ liệu. Đây là tình huống bình thường trong nhiều batch pipeline. Tuy nhiên, **input rỗng có được xem là thành công hay lỗi nghiệp vụ hay không phụ thuộc vào hợp đồng của job**.

Về mặt kỹ thuật, quy ước của Spring Batch rất rõ: khi không còn item để đọc, phương thức `ItemReader.read()` trả về `null`. Một chunk step đọc hết nguồn dữ liệu mà không nhận được item nào thường hoàn tất bình thường với số lượng đọc và ghi bằng 0. Điều đó không tự nói lên rằng dữ liệu đầu vào hợp lệ hay không hợp lệ.

Bài này giải thích quy ước EOF của reader, cách các reader phổ biến xử lý nguồn rỗng, cách phân biệt file rỗng với file thiếu hoặc dữ liệu bị lọc hết, và cách thiết kế job để chấp nhận, bỏ qua hoặc từ chối input rỗng theo yêu cầu nghiệp vụ.

## 1. Quy ước cốt lõi: read() trả về null khi hết dữ liệu

Interface `ItemReader<T>` có một phương thức đọc item. Mỗi lần được gọi, reader trả về:

- Một object khác `null` nếu có item tiếp theo.
- `null` nếu đã hết input và không còn item nào để đọc.

Ví dụ reader đơn giản:

```java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
```

Nếu danh sách đầu vào rỗng, lần gọi đầu tiên trả về `null`. Spring Batch hiểu rằng reader đã hết dữ liệu và kết thúc phần đọc của step.

Điểm quan trọng là `null` có ý nghĩa điều khiển luồng: nó đánh dấu EOF (end of input). Không dùng `null` để biểu diễn một dòng sai định dạng, một bản ghi bị bỏ qua hoặc một giá trị nghiệp vụ rỗng. Nếu reader trả về `null` giữa nguồn dữ liệu, framework sẽ hiểu rằng không còn item phía sau và có thể kết thúc step sớm.

### Phân biệt EOF với item có nội dung rỗng

Giả sử reader có kiểu `ItemReader<String>`:

- Trả về `""` là một item chuỗi rỗng hợp lệ; framework vẫn xem đó là một item.
- Trả về một object có các trường đều rỗng vẫn là một item.
- Trả về `null` có nghĩa không còn item nào nữa.

Tương tự, nếu kiểu item là `ItemReader<List<Record>>`, một list rỗng vẫn là một object khác `null`. Nó có thể là một item hợp lệ nếu hợp đồng dữ liệu định nghĩa như vậy. Lần gọi `read()` tiếp theo mới trả về `null` khi nguồn thực sự kết thúc.

## 2. Điều gì xảy ra khi chunk step đọc input rỗng?

Chunk-oriented step thực hiện chu trình đọc, xử lý và ghi. Khi reader trả về `null` ngay ở lần đọc đầu tiên, Spring Batch nhận biết nguồn đã kết thúc:

```mermaid
flowchart TD
    A[Step bắt đầu] --> B[Reader.read()]
    B --> C{Có item?}
    C -->|Không, trả null| D[Đánh dấu EOF]
    D --> E[Không có chunk để ghi]
    E --> F[Step kết thúc]
    C -->|Có item| G[Processor]
    G --> H[Chunk đủ kích thước hoặc EOF]
    H --> I[Writer]
    I --> B
```

Với một step đọc không có item nào, hành vi thường thấy là:

- Step được khởi chạy bình thường.
- Reader được mở và được gọi đọc.
- Reader trả về `null` ngay lần đầu.
- Processor không được gọi.
- Writer không được gọi vì không có chunk item nào.
- Step hoàn tất với `BatchStatus.COMPLETED`, nếu không có lỗi khác.

Các bộ đếm của step thường cho thấy `READ_COUNT = 0`, `WRITE_COUNT = 0`, `FILTER_COUNT = 0` và các skip count bằng 0. Job có thể tiếp tục sang step kế tiếp theo flow đã khai báo.

Đây là hoàn tất kỹ thuật bình thường. Nếu nghiệp vụ yêu cầu phải có ít nhất một bản ghi, ứng dụng phải bổ sung quy tắc kiểm tra hoặc điều hướng riêng.

## 3. Phân biệt các tình huống input rỗng

Không phải mọi tình huống “không có dữ liệu” đều giống nhau. Cần xác định chính xác điều gì đã xảy ra trước khi chọn cách xử lý.

| Tình huống | Ví dụ | Cách hiểu |
|---|---|---|
| File không tồn tại | Đường dẫn chưa có file | Lỗi đầu vào hoặc chờ file, tùy hợp đồng |
| File có kích thước 0 | File hoàn toàn trống | Có nguồn nhưng không có nội dung |
| File chỉ có header | Có tên cột nhưng không có record | Cấu trúc có thể hợp lệ, số record bằng 0 |
| Query không trả dòng | Không có giao dịch trong khoảng | Có thể là ngày không phát sinh dữ liệu |
| Partition không có record | Một vùng dữ liệu không có item | Thường có thể chấp nhận |
| Dòng trống | Một dòng không có ký tự | Phải áp dụng quy tắc blank-line riêng |
| Dữ liệu sai định dạng | Thiếu cột hoặc sai kiểu số | Lỗi parse/validation, không phải EOF |
| Tất cả item bị lọc | Processor trả về `null` cho mọi item | Input không rỗng nhưng output rỗng |
| Tất cả item bị skip | Mọi item đều bị bỏ qua theo skip policy | Có input nhưng không có item được ghi |

Sự phân biệt này quan trọng cho báo cáo. Ví dụ, “không có giao dịch trong ngày” có thể là kết quả tốt, trong khi “file nguồn không tồn tại” có thể là lỗi nghiêm trọng.

## 4. FlatFileItemReader với file rỗng hoặc chỉ có header

`FlatFileItemReader` thường được dùng để đọc CSV hoặc file văn bản theo dòng. Ví dụ:

```java
@Bean
@StepScope
FlatFileItemReader<Invoice> invoiceReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Invoice>()
            .name("invoiceReader")
            .resource(new FileSystemResource(inputFile))
            .strict(true)
            .linesToSkip(1)
            .delimited()
            .names("invoiceId", "customerId", "amount")
            .fieldSetMapper(fields -> new Invoice(
                    fields.readString("invoiceId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

Trong ví dụ, reader bỏ qua dòng đầu tiên vì đó là header. Sau đó, các dòng còn lại được ánh xạ thành `Invoice`.

### File có kích thước 0

Nếu resource tồn tại, đọc được và không có dòng nào, reader sẽ không tạo ra item. Lần đọc trả về `null`, do đó chunk step có thể hoàn tất với `READ_COUNT = 0`.

### File chỉ có header

Nếu file có đúng một dòng header và cấu hình `linesToSkip(1)`, không còn dòng dữ liệu nào để ánh xạ. Kết quả cũng là zero item. Đây thường là file có cấu trúc nhưng không có record.

### File không tồn tại

File không tồn tại khác với file rỗng. `FlatFileItemReader` có chế độ strict; mặc định thường là strict. Khi resource không tồn tại hoặc không đọc được, reader báo lỗi khi mở thay vì coi đó là EOF. Nếu cố tình đặt `strict(false)`, reader có thể bỏ qua resource thiếu và tiếp tục như nguồn không có item. Chỉ dùng cách này nếu thiếu file thực sự được định nghĩa là input rỗng hợp lệ.

### Header sai hoặc bị thiếu

Nếu file không có header nhưng cấu hình bỏ qua một dòng, reader có thể bỏ qua luôn dòng dữ liệu đầu tiên. Ngược lại, file rỗng hoàn toàn có thể không cung cấp dòng nào để kiểm tra header. Vì vậy, nếu header là bắt buộc, cần kiểm tra nó một cách tường minh.

Có thể dùng một bước validate input trước step import để kiểm tra:

- Resource có tồn tại và đọc được không.
- File có dòng header không.
- Tên cột có đúng thứ tự hoặc đúng tập tên được yêu cầu không.
- Encoding và delimiter có đúng hợp đồng không.
- File có dữ liệu hay chỉ có header.

Nếu bước validate tự đọc file, hãy giữ input bất biến và bảo đảm reader import đọc cùng một phiên bản file. Có thể kiểm tra checksum hoặc chuyển file vào thư mục batch đã chốt trước khi chạy.

### Dòng trống không đồng nghĩa với EOF

Một dòng trắng trong file vẫn là một dòng vật lý. Nó không tự động có nghĩa là reader đã hết file. Dòng đó có thể được tokenizer/line mapper xử lý, tạo item rỗng hoặc gây lỗi parse tùy cấu hình. Hãy định nghĩa rõ dòng trắng được bỏ qua, xem là dữ liệu lỗi hay được ánh xạ thành một giá trị hợp lệ.

Không viết custom reader trả về `null` khi gặp một dòng trắng nếu vẫn còn dữ liệu ở các dòng sau. Cách đó sẽ kết thúc quá trình đọc sớm.

## 5. JdbcCursorItemReader và truy vấn không có dòng

Với database reader, query có thể hợp lệ nhưng không tìm thấy bản ghi:

```java
@Bean
@StepScope
JdbcCursorItemReader<Invoice> invoiceReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcCursorItemReaderBuilder<Invoice>()
            .name("invoiceReader")
            .dataSource(dataSource)
            .sql("""
                    SELECT invoice_id, customer_id, amount
                    FROM invoice
                    WHERE business_date = ?
                    ORDER BY invoice_id
                    """)
            .preparedStatementSetter(statement ->
                    statement.setDate(
                            1,
                            java.sql.Date.valueOf(businessDate)))
            .rowMapper((resultSet, rowNum) -> new Invoice(
                    resultSet.getString("invoice_id"),
                    resultSet.getString("customer_id"),
                    resultSet.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

Nếu query không trả về dòng nào, reader trả về `null` khi được gọi đọc. Step hoàn tất bình thường với zero read. Đây không phải lỗi SQL; nó chỉ cho biết kết quả truy vấn rỗng.

Không nhất thiết phải chạy thêm một câu `SELECT COUNT(*)` trước reader để biết query có dữ liệu hay không. Với bảng lớn, count có thể tốn tài nguyên; hơn nữa, dữ liệu có thể thay đổi giữa truy vấn count và truy vấn reader. Nếu mục tiêu chỉ là biết step đã đọc được item nào hay không, `StepExecution` đã có bộ đếm để kiểm tra sau khi đọc.

Nếu nghiệp vụ cần một snapshot ổn định, hãy chọn transaction isolation hoặc watermark phù hợp. Việc chạy count trước không tạo ra snapshot nhất quán nếu hai truy vấn không cùng một snapshot transaction.

## 6. Phân biệt input rỗng với processor lọc hết dữ liệu

Đây là một khác biệt thường bị bỏ qua.

Reader trả về item nghĩa là nguồn có dữ liệu. Sau đó processor có thể trả về `null` để lọc item đó khỏi output. Trả về `null` từ processor không có nghĩa reader đã hết input.

Ví dụ:

```java
@Bean
ItemProcessor<Invoice, Invoice> validInvoiceProcessor() {
    return invoice -> {
        if (invoice.amount().signum() <= 0) {
            return null; // Lọc item, không phải EOF
        }
        return invoice;
    };
}
```

Nếu reader đọc 100 item và processor lọc tất cả, step không phải là input rỗng. Các bộ đếm có thể phản ánh `READ_COUNT = 100`, `FILTER_COUNT = 100`, `WRITE_COUNT = 0`.

So sánh:

| Trường hợp | READ_COUNT | FILTER_COUNT | WRITE_COUNT |
|---|---:|---:|---:|
| Reader không có item | 0 | 0 | 0 |
| Có 100 item, tất cả bị filter | 100 | 100 | 0 |
| Có 100 item, filter 10 | 100 | 10 | 90 |
| Có 100 item, một số bị skip | 100 hoặc số đã đọc trước lỗi | Theo filter thực tế | Phụ thuộc số item ghi và skip |

Khi theo dõi production, đừng dùng riêng `WRITE_COUNT = 0` để kết luận nguồn rỗng. Hãy xem cả read, filter và skip count.

## 7. Thiết kế chính sách khi không có dữ liệu

Trước khi triển khai, hãy thống nhất input rỗng thuộc trường hợp nào:

### Trường hợp A: Input rỗng là kết quả hợp lệ

Ví dụ: ngày nghỉ không có giao dịch, một vùng dữ liệu không có bản ghi hoặc một báo cáo không có dòng phát sinh.

Có thể để chunk step hoàn tất bình thường. Job nên ghi nhận số lượng bằng 0 và các step sau phải chấp nhận tình huống đó. Nếu cần thông báo, có thể phát thông điệp “không có dữ liệu” ở bước tổng hợp.

### Trường hợp B: Input rỗng là một nhánh riêng của workflow

Ví dụ: job không cần chạy bước tổng hợp nặng khi không có item, nhưng vẫn cần ghi nhận rằng batch đã kiểm tra nguồn thành công.

Có thể dùng `StepExecutionListener` để đặt exit code riêng khi `readCount` bằng 0:

```java
public class EmptyInputExitStatusListener
        implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getReadCount() == 0) {
            return new ExitStatus("NO_INPUT");
        }
        return null;
    }
}
```

Gắn listener vào step:

```java
return new StepBuilder("importInvoicesStep", jobRepository)
        .<Invoice, ProcessedInvoice>chunk(500, transactionManager)
        .reader(invoiceReader)
        .processor(invoiceProcessor)
        .writer(invoiceWriter)
        .listener(new EmptyInputExitStatusListener())
        .build();
```

Sau đó điều hướng flow theo exit code:

```java
return new JobBuilder("invoiceImportJob", jobRepository)
        .start(importInvoicesStep)
            .on("NO_INPUT").to(noInputStep)
        .from(importInvoicesStep)
            .on("*").to(reconcileStep)
        .end()
        .build();
```

`NO_INPUT` là exit code tùy chỉnh do ứng dụng định nghĩa. `BatchStatus` của step vẫn có thể là `COMPLETED`; flow dùng `ExitStatus` để chọn nhánh. Step `noInputStep` có thể ghi nhận kết quả zero-record, gửi thông báo hoặc kết thúc quy trình theo chính sách.

Trong ví dụ, `readCount == 0` xác định reader không phát ra item nào. Nếu processor lọc hết, read count vẫn lớn hơn 0 nên không đi vào nhánh `NO_INPUT`.

### Trường hợp C: Input rỗng là lỗi nghiệp vụ

Ví dụ: file settlement bắt buộc phải có giao dịch, hoặc job phải nhận ít nhất một bản ghi đối soát.

Có thể validate trước khi import và fail với thông điệp cụ thể. Với file, bước validate có thể kiểm tra file, header và số dòng dữ liệu. Với database, có thể để chính step đọc dữ liệu xác định zero read rồi điều hướng sang một step báo lỗi; hoặc thiết kế một reader/step kiểm tra phù hợp với yêu cầu snapshot.

Không nên giả vờ rằng step chunk tự thất bại khi reader trả về `null`. Hành vi mặc định là hết dữ liệu, không phải lỗi. Nếu zero record không hợp lệ, hãy biến quy tắc đó thành một bước nghiệp vụ tường minh.

### Trường hợp D: Chờ input đến

Nếu file thường đến muộn, có thể để scheduler hoặc hệ thống điều phối chờ đến deadline trước khi launch. Job không nên chạy lặp liên tục chỉ để kiểm tra file mà không có backoff và giới hạn thời gian. Khi đến deadline, quy trình phải quyết định chờ tiếp, đánh dấu thiếu input hay chạy với zero record.

## 8. Ví dụ validate file trước khi import

Một Tasklet có thể xác nhận resource tồn tại, đọc được và không rỗng về mặt vật lý:

```java
@Bean
@StepScope
Tasklet validateInputFile(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        Resource resource = new FileSystemResource(inputFile);

        if (!resource.exists()) {
            throw new IllegalStateException(
                    "Input file does not exist: " + inputFile);
        }

        if (!resource.isReadable()) {
            throw new IllegalStateException(
                    "Input file is not readable: " + inputFile);
        }

        if (resource.contentLength() == 0) {
            throw new IllegalStateException(
                    "Input file is empty: " + inputFile);
        }

        return RepeatStatus.FINISHED;
    };
}
```

Đoạn code này minh họa chính sách “file rỗng vật lý là lỗi”. Nếu file chỉ có header được xem là hợp lệ, kiểm tra `contentLength()` không đủ để xác nhận có record. Cần đọc và xác minh header, rồi xác định có dòng dữ liệu sau header hay không.

Validation trước và reader import có thể tạo ra race condition nếu file bị thay đổi giữa hai bước. Trong production, nên nhận file vào vùng lưu trữ bất biến, đổi tên/di chuyển nguyên tử sang thư mục batch đã chốt, hoặc ghi nhận checksum và kiểm tra lại trước khi xử lý.

Với file lớn, không đọc toàn bộ file chỉ để đếm dòng rồi lại đọc lần thứ hai nếu không cần thiết. Có thể để reader xử lý dữ liệu và dùng step listener dựa trên `readCount`, trong khi validation chỉ xác nhận các điều kiện cấu trúc cần thiết.

## 9. Custom ItemReader phải xử lý empty input đúng cách

Khi tự viết reader, cần bảo đảm ba quy tắc:

1. Trả về item khác `null` khi có dữ liệu.
2. Trả về `null` khi nguồn thực sự kết thúc.
3. Không trả `null` để biểu diễn lỗi hoặc bỏ qua một item.

Ví dụ reader đọc từ iterator:

```java
public class SafeIteratorItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public SafeIteratorItemReader(Collection<T> source) {
        this.iterator = source.iterator();
    }

    @Override
    public T read() {
        if (!iterator.hasNext()) {
            return null;
        }

        T item = iterator.next();
        if (item == null) {
            throw new IllegalStateException(
                    "Source contains a null item");
        }
        return item;
    }
}
```

Reader này trả `null` ngay lần đầu nếu collection rỗng. Nếu collection có phần tử `null`, nó báo lỗi thay vì vô tình kết thúc stream tại vị trí đó.

Trong reader thực tế, nếu nguồn có thể được mở/đóng, hỗ trợ restart hoặc phân trang, nên triển khai các lifecycle interface thích hợp như `ItemStream` và lưu state trong `ExecutionContext`. Đối với reader có state, tên reader phải ổn định và state phải được cập nhật tại ranh giới commit.

### Không dùng Optional.empty() làm tín hiệu EOF

Nếu kiểu reader là `ItemReader<Optional<Invoice>>`, một `Optional.empty()` là object khác `null`, vì vậy Spring Batch xem nó như một item. Điều đó chỉ đúng nếu nghiệp vụ thực sự cần một item biểu diễn “không có invoice”. Nếu mục đích là kết thúc stream, hãy trả về `null` theo contract của `ItemReader`.

## 10. Empty input trong partitioning và parallel processing

Với partitioned step, một số partition có thể không nhận bản ghi nào trong khi partition khác có dữ liệu. Đây không nhất thiết là lỗi. Reader của partition rỗng có thể trả về `null` ngay lần đầu và worker step hoàn tất với zero read.

Tuy nhiên, cần kiểm tra:

- Các partition có được chia không chồng lấn và không bỏ sót không.
- Tổng số record giữa các partition có khớp với tập nguồn dự kiến không.
- Một partition rỗng có hợp lệ theo cách chia dữ liệu hay chỉ ra lỗi phân vùng.
- Job có xử lý đúng khi tất cả partition đều rỗng không.
- Báo cáo tổng hợp có phân biệt partition rỗng với partition thất bại không.

Không fail toàn job chỉ vì một partition rỗng nếu partition rỗng là kết quả tự nhiên của cách chia. Ngược lại, nếu một partition bắt buộc phải có dữ liệu, hãy thể hiện điều kiện đó rõ ràng trong bước validate hoặc kết quả partition.

## 11. Empty input, skip và retry là ba khái niệm khác nhau

| Hành vi | Nguyên nhân | Kết quả |
|---|---|---|
| EOF | Reader không còn item | `read()` trả `null`, step kết thúc đọc |
| Filter | Processor quyết định không đưa item vào output | Processor trả `null`, filter count tăng |
| Skip | Lỗi được cho phép bỏ qua theo fault-tolerant policy | Item lỗi được bỏ qua và skip count tăng |
| Retry | Lỗi được xem là tạm thời | Framework thử lại thao tác theo cấu hình |
| Fail | Lỗi không được phép tiếp tục | Step/job thất bại |

Không cấu hình skip policy để “bỏ qua input rỗng”. EOF không phải exception và không cần skip. Nếu nguồn không có item, chính sách phải được thể hiện ở flow hoặc validation.

Nếu reader gặp lỗi parse ở dòng đầu tiên, đó là lỗi đọc dữ liệu. Có thể fail hoặc skip theo chính sách lỗi dữ liệu, nhưng không nên chuyển lỗi đó thành `null`; làm như vậy sẽ che giấu lỗi và có thể bỏ qua phần còn lại của file.

## 12. Quan sát và báo cáo khi input rỗng

Khi job hoàn tất với zero item, log và metric nên giải thích rõ điều đó. Nên ghi nhận:

- Job name, job execution ID, step name và batch ID.
- Input resource hoặc cửa sổ dữ liệu đã xử lý.
- Số item đọc, ghi, filter và skip.
- Lý do không có dữ liệu nếu có thể xác định.
- Chính sách đã áp dụng: accepted, routed hoặc rejected.
- Thời điểm kiểm tra và thời gian chạy.

Ví dụ log:

```text
job=invoiceImportJob
jobExecutionId=108
step=importInvoicesStep
batchId=daily-20261115
readCount=0
writeCount=0
exitCode=NO_INPUT
message=No invoice records found for business date
```

Không ghi toàn bộ nội dung file hoặc dữ liệu cá nhân vào log chỉ để chứng minh file rỗng. Dùng mã batch, checksum, tên resource đã được làm sạch và số lượng bản ghi.

Dashboard có thể phân biệt các kết quả:

- `COMPLETED` với record count lớn hơn 0: xử lý có dữ liệu.
- `NO_INPUT`: nguồn hợp lệ nhưng không có record.
- `FAILED`: input thiếu, sai cấu trúc hoặc lỗi hệ thống.
- `COMPLETED` với read count lớn hơn 0 nhưng write count bằng 0: cần kiểm tra filter/skip policy.

Nếu dùng custom exit code, hãy chuẩn hóa cách dashboard và alert đọc cả `BatchStatus` lẫn `ExitStatus`.

## 13. Restart khi lần chạy trước không có dữ liệu

Nếu một step đọc zero item và hoàn tất, `JobInstance` thường được xem là đã hoàn thành nếu toàn bộ job cũng hoàn tất. Launch lại cùng identifying parameters thường không tạo một lần chạy mới; Spring Batch sẽ báo instance đã hoàn tất.

Điều này có ý nghĩa nếu input đến muộn:

- Nếu job chạy lúc 01:00 và nguồn chưa có dữ liệu, job hoàn tất với zero item.
- File hoặc bản ghi đến lúc 01:15.
- Launch lại cùng identifying parameters có thể bị từ chối vì instance đã hoàn tất.

Hãy quyết định trước cách xử lý late-arriving input:

1. Chờ đến deadline trước khi launch.
2. Chỉ đánh dấu batch hoàn tất sau khi xác nhận nguồn đã chốt.
3. Tạo một yêu cầu reprocess có ID/version mới theo chính sách nghiệp vụ.
4. Dùng cơ chế điều phối để giữ trạng thái “chờ input” trước khi tạo JobInstance.

Không thêm timestamp ngẫu nhiên chỉ để chạy lại cùng dữ liệu. Nếu reprocess tạo instance mới, writer vẫn phải idempotent hoặc có cơ chế ghi phiên bản.

Nếu zero input được xem là kết quả hoàn tất hợp lệ, việc không thể restart cùng instance sau đó là hành vi phù hợp. Nếu job phải chờ dữ liệu đến, hãy biểu diễn trạng thái chờ ở tầng điều phối hoặc giữ job chưa hoàn tất theo thiết kế rõ ràng; đừng coi EOF là một trạng thái chờ tự động.

## 14. Kiểm thử reader với nguồn rỗng

Kiểm thử nên bao phủ từng loại nguồn rỗng và từng chính sách nghiệp vụ.

| Trường hợp | Điều cần xác nhận |
|---|---|
| Collection rỗng | Lần đọc đầu trả `null` |
| File 0 byte | Reader không phát item; validation theo đúng chính sách |
| File chỉ có header | Header được bỏ qua và không có data item |
| File không tồn tại | Strict reader hoặc validation báo lỗi nếu file bắt buộc |
| Query không có dòng | Step hoàn tất với read count bằng 0 |
| Dòng trắng | Được xử lý theo blank-line policy |
| Dòng sai định dạng | Fail hoặc skip theo exception policy |
| Processor lọc mọi item | Read count lớn hơn 0 và filter count phản ánh số bị lọc |
| Partition rỗng | Worker step hoàn tất đúng chính sách |

Ví dụ unit test cho reader dùng collection:

```java
class SafeIteratorItemReaderTest {

    @Test
    void returnsNullWhenSourceIsEmpty() throws Exception {
        ItemReader<String> reader =
                new SafeIteratorItemReader<>(List.of());

        assertNull(reader.read());
    }

    @Test
    void returnsItemsThenNullAtEnd() throws Exception {
        ItemReader<String> reader =
                new SafeIteratorItemReader<>(List.of("A", "B"));

        assertEquals("A", reader.read());
        assertEquals("B", reader.read());
        assertNull(reader.read());
    }
}
```

Ngoài unit test, nên có integration test cho step với database metadata và nguồn dữ liệu kiểm thử. Test xác nhận trạng thái step, bộ đếm và exit code. Nếu dùng flow `NO_INPUT`, cần kiểm tra job đi đúng nhánh và step downstream có hoặc không được chạy theo yêu cầu.

## 15. Những lỗi thiết kế thường gặp

**Coi zero read là lỗi tự động.** Spring Batch coi `null` là EOF. Nếu zero record không hợp lệ, cần thêm validation hoặc flow policy.

**Coi file không tồn tại giống file rỗng.** File thiếu có thể là lỗi delivery; file rỗng có thể là một input hợp lệ. Dùng strict resource validation và chính sách riêng.

**Dùng null để bỏ qua dòng lỗi.** Null kết thúc stream. Dùng exception/skip policy hoặc processor filter theo đúng ý nghĩa.

**Chỉ nhìn write count.** Zero write có thể do nguồn rỗng, filter hết hoặc skip hết. Đọc cả read/filter/skip count.

**Giả định file chỉ có header là file sai.** Một số hệ thống cho phép file header-only để biểu diễn ngày không có record. Hãy xác định quy tắc nghiệp vụ.

**Chạy lại job sau khi input đến muộn bằng timestamp mới.** Cách đó tạo instance mới và có thể xử lý trùng. Cần late-data/reprocess policy cùng idempotent writer.

**Validate file rồi để file thay đổi trước khi reader chạy.** Hai bước có thể đọc hai nội dung khác nhau. Chốt file bất biến hoặc kiểm tra checksum.

## 16. Quy trình quyết định khi reader gặp input rỗng

Khi thiết kế một reader, hãy lần theo các câu hỏi:

1. Nguồn có tồn tại và đọc được không?
2. Cấu trúc nguồn có hợp lệ không, ví dụ header và encoding?
3. Nguồn hợp lệ nhưng không có record, hay dữ liệu bị lọc/skip hết?
4. Zero record có được nghiệp vụ cho phép không?
5. Nếu được phép, job nên hoàn tất bình thường hay đi qua nhánh `NO_INPUT`?
6. Nếu không được phép, bước nào sẽ fail và ghi lý do gì?
7. Nếu dữ liệu đến muộn, có cơ chế chờ hoặc reprocess nào?
8. Khi restart, nguồn dữ liệu có giữ nguyên không?

Một quyết định rõ ràng ở các điểm này giúp job tránh trạng thái “xanh nhưng thiếu dữ liệu” và cũng tránh báo lỗi cho những ngày không có phát sinh hợp lệ.

## 17. Kết luận thực hành

Reader xử lý input rỗng theo contract đơn giản: trả về `null` khi hết dữ liệu. Với chunk step, zero item thường dẫn đến step hoàn tất với read/write count bằng 0; processor và writer không có item để xử lý. Đây là hành vi kỹ thuật bình thường.

Phần cần thiết kế là ý nghĩa nghiệp vụ của zero item. Có thể chấp nhận, điều hướng sang nhánh `NO_INPUT`, hoặc fail qua validation. Hãy phân biệt file thiếu, file rỗng, file chỉ có header, query không có dòng, dữ liệu bị filter và dữ liệu bị skip. Đặc biệt, đừng dùng `null` để bỏ qua một item khi vẫn còn dữ liệu phía sau.

Một reader production tốt không chỉ đọc đúng khi có dữ liệu. Nó còn biểu đạt rõ EOF, giữ được trạng thái restart, xử lý lỗi theo chính sách và cung cấp đủ metadata để người vận hành hiểu vì sao một batch không tạo ra output.
