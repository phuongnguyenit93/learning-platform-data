# Chunk completion khi reader kết thúc trong Spring Batch

Trong chunk-oriented Step, Spring Batch gom item thành từng nhóm theo commit interval. Thông thường, một chunk được xử lý khi đã đọc đủ số item cấu hình. Nhưng nguồn dữ liệu có thể kết thúc trước khi đạt đến kích thước đó. Khi **ItemReader trả về null**, framework nhận biết đã hết đầu vào và hoàn tất chunk hiện tại với những item đã đọc được.

Điều này có nghĩa chunk cuối cùng không cần đủ commit interval mới được ghi. Nếu còn item trong chunk, Spring Batch vẫn chuyển chúng qua processor và writer, sau đó hoàn tất transaction của chunk. Nếu nguồn kết thúc ngay từ lần đọc đầu tiên, không có item nghiệp vụ nào để ghi và Step có thể hoàn tất bình thường với số lượng đọc bằng 0.

Hiểu rõ cách kết thúc chunk giúp tránh một giả định sai thường gặp: chunk size là số item tối đa được gom cho một lần commit, không phải điều kiện bắt buộc để dữ liệu được ghi. Bài học này trình bày cách xử lý chunk cuối, các trường hợp nguồn rỗng và số item chia hết hoặc không chia hết cho commit interval, ảnh hưởng đến transaction, checkpoint, metrics và kiểm thử.

## 1. Commit interval và điều kiện kết thúc chunk

Một chunk-oriented Step được cấu hình với commit interval:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .build();
}
~~~

Trong ví dụ, 100 là commit interval. Spring Batch đọc tối đa 100 item đầu vào để tạo một chunk. Khi đủ số item, framework xử lý và ghi chunk đó trong transaction tương ứng.

Chunk cũng có thể kết thúc sớm khi reader báo hết dữ liệu. Có hai điều kiện phổ biến làm cho framework hoàn tất phần đọc của chunk:

- Đã thu thập đủ số item theo commit interval.
- Reader trả về `null`, báo rằng nguồn không còn item tiếp theo.

Vì vậy, commit interval là giới hạn kích thước chunk, không phải yêu cầu rằng mỗi chunk phải có đủ số item đó.

~~~mermaid
flowchart TD
    A["Bắt đầu đọc chunk"] --> B["ItemReader.read()"]
    B --> C{"Kết quả đọc"}
    C -- "Có item" --> D["Thêm item vào chunk"]
    D --> E{"Đủ commit interval?"}
    E -- "Chưa" --> B
    E -- "Đủ" --> F["Xử lý và ghi chunk"]
    C -- "null / EOF" --> G["Kết thúc phần đọc"]
    G --> H["Xử lý và ghi các item còn lại"]
    H --> I["Hoàn tất transaction"]
    F --> I
    I --> J["Chunk tiếp theo hoặc kết thúc Step"]
~~~

Sơ đồ mô tả luồng khái niệm. Khi reader báo EOF, Spring Batch vẫn phải xử lý những item đã được đọc trong chunk hiện tại trước khi kết thúc Step.

## 2. Chunk cuối có thể nhỏ hơn commit interval

Giả sử commit interval là 3 và nguồn có 8 item: A, B, C, D, E, F, G, H.

Các chunk được hình thành như sau:

~~~text
Chunk 1: A, B, C  -> đủ 3 item -> write -> commit
Chunk 2: D, E, F  -> đủ 3 item -> write -> commit
Chunk 3: G, H     -> reader trả null -> write -> commit
~~~

Chunk cuối chỉ có 2 item. Spring Batch không bỏ hai item này chỉ vì chưa đạt kích thước 3. Reader trả `null` báo kết thúc nguồn; framework xử lý phần dữ liệu còn lại rồi hoàn tất transaction của chunk cuối.

Ví dụ cấu hình:

~~~java
new StepBuilder("importStep", jobRepository)
    .<Order, Order>chunk(3, transactionManager)
    .reader(orderReader)
    .writer(orderWriter)
    .build();
~~~

Nếu reader cung cấp 8 item, writer sẽ nhận các nhóm đầu ra tương ứng với các chunk được xử lý. Chunk cuối có ít item hơn commit interval nhưng vẫn được ghi theo luồng bình thường.

### Vì sao phải ghi chunk cuối?

Nếu framework chỉ ghi những chunk đủ 3 item, mọi nguồn có số lượng không chia hết cho 3 đều bị mất phần dư. Với 8 item, hai item cuối sẽ không được ghi. Với 101 item và commit interval 100, item thứ 101 sẽ bị bỏ lại.

Hành vi đúng là xử lý chunk cuối khi reader kết thúc. Đây là một phần cơ bản của chunk-oriented processing, không cần viết thêm logic riêng để flush phần dư trong ItemWriter.

## 3. Điều gì xảy ra khi reader trả về null?

Hợp đồng của ItemReader là trả về một item hoặc `null`:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

- Trả về item: framework thêm item đó vào phần đầu vào của chunk.
- Trả về `null`: framework biết nguồn đã hết và không yêu cầu item tiếp theo cho Step này.
- Ném exception: framework xử lý lỗi theo transaction và chính sách skip/retry/fail của Step.

Giả sử chunk size là 5 nhưng reader chỉ còn hai item. Trình tự khái niệm:

~~~text
read() -> item 1
read() -> item 2
read() -> null
~~~

Sau khi nhận `null`, framework hoàn tất phần đọc của chunk. Hai item đã đọc được vẫn được chuyển qua processor nếu có, rồi các item đầu ra được ghi theo cấu hình writer. Khi các thao tác cần thiết thành công, transaction của chunk được commit.

`null` là tín hiệu kết thúc nguồn. Nó không phải một item rỗng, không phải giá trị thay thế cho một bản ghi lỗi và cũng không có nghĩa là bỏ chunk hiện tại.

### Không cần tự gọi writer để flush

Không nên thêm logic như:

~~~java
if (readerReturnedNull) {
    writer.write(remainingItems);
}
~~~

trong reader hoặc một thành phần bên ngoài Step. Spring Batch đã quản lý việc gom chunk và gọi writer. Nếu ứng dụng tự gọi writer ngoài luồng này, có thể ghi trùng, vượt qua transaction của chunk hoặc làm sai thống kê StepExecution.

Reader chỉ cần tuân thủ hợp đồng đọc. Writer chỉ cần xử lý chunk mà framework chuyển đến.

## 4. Các trường hợp nguồn kết thúc

Có thể chia thành ba trường hợp phổ biến: nguồn rỗng, nguồn có số item nhỏ hơn commit interval và nguồn có số item chia hết hoặc không chia hết cho commit interval.

### Trường hợp A: nguồn không có item

Giả sử reader trả `null` ngay lần đầu:

~~~text
read() -> null
~~~

Không có item nào được chuyển đến writer. Step có thể kết thúc bình thường nếu nguồn rỗng là đầu vào hợp lệ.

Các bộ đếm nghiệp vụ thường có giá trị:

- `readCount = 0`
- `writeCount = 0`
- `filterCount = 0`

Nếu Job bắt buộc phải có dữ liệu, cần kiểm tra điều kiện này và báo trạng thái nghiệp vụ phù hợp. Không nên mặc định một Step COMPLETED với 0 item luôn là thành công theo nghiệp vụ.

Ví dụ một file chỉ có header có thể là file rỗng hợp lệ hoặc là lỗi đầu vào tùy yêu cầu. Quyết định đó thuộc validation của Job hoặc Step, không phải lý do để reader trả về một item giả.

### Trường hợp B: nguồn nhỏ hơn commit interval

Commit interval là 100, nguồn có 25 item.

~~~text
read 25 item
read() -> null
process 25 item
write phần đầu ra
commit chunk cuối
~~~

Một chunk chứa 25 item được hoàn tất. Không cần chờ thêm 75 item.

### Trường hợp C: nguồn có số item chia hết cho commit interval

Commit interval là 100, nguồn có 200 item.

~~~text
Chunk 1: 100 item -> write -> commit
Chunk 2: 100 item -> write -> commit
Lần đọc tiếp theo: null -> kết thúc Step
~~~

Hai chunk dữ liệu đều đủ kích thước. Sau khi chunk thứ hai hoàn tất, framework cần xác định nguồn đã hết. Việc phát hiện EOF có thể diễn ra trong lượt đọc tiếp theo; không có item thứ 201 được thêm vào chunk.

Không nên suy luận số lần gọi reader chỉ từ số lượng chunk. Framework có thể cần thêm một lần gọi `read()` để nhận biết EOF sau một chunk vừa đủ commit interval.

### Trường hợp D: nguồn không chia hết cho commit interval

Commit interval là 100, nguồn có 235 item.

~~~text
Chunk 1: 100 item -> write -> commit
Chunk 2: 100 item -> write -> commit
Chunk 3:  35 item -> EOF -> write -> commit
~~~

Chunk thứ ba chứa 35 item và vẫn được xử lý bình thường.

| Số item nguồn | Commit interval | Các chunk dữ liệu |
|---:|---:|---|
| 0 | 100 | Không có chunk chứa item |
| 25 | 100 | 25 |
| 100 | 100 | 100 |
| 200 | 100 | 100, 100 |
| 235 | 100 | 100, 100, 35 |
| 301 | 100 | 100, 100, 100, 1 |

Bảng mô tả nhóm item đầu vào theo commit interval, trước khi xét processor filter và các lỗi skip.

## 5. Chu trình xử lý chunk cuối

Khi nguồn kết thúc trước khi đạt commit interval, chunk cuối đi qua cùng các giai đoạn xử lý như những chunk trước.

Giả sử commit interval là 4 và nguồn chỉ còn hai item:

~~~mermaid
sequenceDiagram
    participant S as Spring Batch
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant TM as TransactionManager

    S->>TM: Bắt đầu transaction
    S->>R: read()
    R-->>S: Item A
    S->>R: read()
    R-->>S: Item B
    S->>R: read()
    R-->>S: null (EOF)
    S->>P: process(A)
    P-->>S: Output A
    S->>P: process(B)
    P-->>S: Output B
    S->>W: write(chunk có 2 output)
    W-->>S: Hoàn tất
    S->>TM: Commit chunk cuối
~~~

Thứ tự cụ thể của các thao tác nội bộ và cập nhật metadata phụ thuộc cấu hình Step, reader và transaction manager. Về mặt hành vi, điều cần nhớ là item đã đọc trong chunk cuối vẫn được xử lý và ghi trước khi Step kết thúc.

### Processor có thể lọc item trong chunk cuối

Nếu processor trả `null` cho một item, item đó được tính là đã đọc nhưng không tạo output cho writer.

Ví dụ nguồn còn ba item, processor lọc một item:

~~~text
Reader:      A, B, C, null
Processor:   A -> A'
             B -> null (lọc)
             C -> C'
Writer:      A', C'
~~~

Chunk cuối vẫn được hoàn tất. Số item writer nhận có thể ít hơn số item reader đã đọc vì filter là một quy tắc riêng, không liên quan đến EOF.

Nếu tất cả item của chunk cuối bị lọc, không có dữ liệu đầu ra để ghi. Framework vẫn phải hoàn tất việc xử lý chunk và cập nhật trạng thái thống kê theo luồng xử lý.

## 6. Chunk cuối và transaction commit

Chunk cuối có transaction giống các chunk khác. Nếu writer ghi thành công và transaction commit, dữ liệu của chunk cuối được lưu bền vững.

Ví dụ:

- Chunk 1 có 100 item và commit thành công.
- Chunk 2 có 100 item và commit thành công.
- Chunk 3 có 35 item vì reader kết thúc.
- Writer ghi 35 item thành công.
- Transaction của chunk 3 commit.
- Step hoàn tất.

~~~mermaid
flowchart TD
    A["Chunk 1: 100 item"] --> B["Commit 1"]
    B --> C["Chunk 2: 100 item"]
    C --> D["Commit 2"]
    D --> E["Chunk cuối: 35 item"]
    E --> F{"Writer thành công?"}
    F -- "Có" --> G["Commit 3"]
    G --> H["Step COMPLETED"]
    F -- "Không" --> I["Rollback chunk 3"]
    I --> J["Step FAILED hoặc retry"]
~~~

### EOF không tự commit chunk

Reader trả `null` chỉ báo kết thúc nguồn. Nó không trực tiếp gọi `commit()` và không thể tự quyết định transaction thành công.

Commit chỉ xảy ra khi framework hoàn tất xử lý chunk và transaction manager kết thúc transaction thành công. Nếu processor hoặc writer phát sinh lỗi, transaction có thể rollback thay vì commit.

Do đó, cần phân biệt:

- EOF: kết thúc việc lấy thêm item.
- Chunk completion: hoàn tất xử lý nhóm item hiện tại.
- Commit: transaction của nhóm đó được xác nhận thành công.
- Step completion: toàn bộ Step kết thúc theo trạng thái và flow đã định nghĩa.

Đây là bốn sự kiện có liên quan nhưng không đồng nghĩa.

## 7. Điều gì xảy ra nếu chunk cuối ghi thất bại?

Giả sử nguồn có 235 item và commit interval là 100. Hai chunk đầu đã commit; chunk cuối có 35 item.

Nếu writer ném exception trong chunk cuối:

1. Các thao tác ghi của chunk cuối được thực hiện trong transaction.
2. Writer phát sinh lỗi.
3. Transaction chunk cuối rollback nếu exception và rollback policy yêu cầu.
4. Các chunk trước vẫn tồn tại vì đã commit.
5. Step có thể retry, skip theo policy hoặc thất bại.
6. Khi restart, reader khôi phục trạng thái phù hợp để xử lý lại phần chưa commit nếu reader hỗ trợ restart.

~~~text
Chunk 1: 100 item -> COMMIT
Chunk 2: 100 item -> COMMIT
Chunk 3:  35 item -> WRITE ERROR -> ROLLBACK

Kết quả:
  - 200 item của hai chunk đầu đã commit.
  - 35 item của chunk cuối chưa được commit.
  - Job có thể restart theo checkpoint.
~~~

Nếu writer ghi sang tài nguyên ngoài transaction database, rollback không nhất thiết hoàn tác tác động đó. Ví dụ API có thể đã nhận 35 item nhưng database rollback. Khi restart, writer có thể gửi lại dữ liệu; cần idempotency hoặc cơ chế đối soát.

### Lỗi xảy ra trong lúc reader đang đọc chunk cuối

Nếu reader ném exception trước khi trả `null`, đó không phải EOF. Framework xử lý lỗi đọc theo chính sách transaction và skip/retry của Step.

Ví dụ nguồn có A, B, C, sau đó việc đọc item tiếp theo gặp lỗi:

~~~text
read() -> A
read() -> B
read() -> C
read() -> IOException
~~~

Framework không được coi IOException là tín hiệu nguồn đã hết. Tùy cấu hình, Step có thể retry, skip lỗi đọc hoặc thất bại. Nếu reader bắt exception rồi trả `null`, A, B, C có thể bị xử lý như một chunk cuối bình thường và lỗi thật bị che giấu.

## 8. Skip và retry ở chunk cuối

Chunk cuối tuân theo chính sách fault-tolerant của Step như các chunk khác.

Ví dụ cấu hình retry cho lỗi database tạm thời:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(reader)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
~~~

Nếu writer gặp lỗi tạm thời trong chunk cuối, Spring Batch có thể thực hiện retry theo policy. Chunk cuối không bị loại khỏi cơ chế retry chỉ vì nó nhỏ hơn commit interval.

Ví dụ skip lỗi parse:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(FlatFileParseException.class)
    .skipLimit(10)
    .build();
~~~

Nếu một lỗi đọc thuộc loại được phép skip, framework có thể bỏ qua item lỗi theo cơ chế fault-tolerant và tiếp tục đọc phần còn lại. Nếu reader sau đó trả `null`, phần item hợp lệ còn lại của chunk vẫn được hoàn tất.

Không nên coi EOF là một loại lỗi để skip. EOF là điều kiện kết thúc bình thường của reader.

### Không tăng skip limit để xử lý EOF

Một lỗi thiết kế là bắt exception cuối nguồn hoặc lỗi parse rồi chuyển thành một loại skip nhằm tránh Step thất bại. Cách này làm sai ý nghĩa của các bộ đếm và che giấu dữ liệu bị thiếu.

Hãy để reader trả `null` đúng lúc hết dữ liệu; với lỗi đọc, ném exception phù hợp và để policy xử lý.

## 9. Reader phải xác định đúng thời điểm kết thúc

Để chunk cuối được xử lý chính xác, reader phải tuân thủ hợp đồng của nó.

Một reader tùy chỉnh cho danh sách cố định:

~~~java
public class ListOrderReader implements ItemReader<Order> {

    private final Iterator<Order> iterator;

    public ListOrderReader(List<Order> orders) {
        this.iterator = orders.iterator();
    }

    @Override
    public Order read() {
        if (!iterator.hasNext()) {
            return null;
        }

        return iterator.next();
    }
}
~~~

Reader trả từng item cho đến khi iterator hết. Lần đọc sau item cuối cùng mới trả `null`, nhờ đó framework biết lúc nào cần hoàn tất chunk cuối.

### Không trả null vì chưa có dữ liệu tạm thời

Với nguồn có thể phát sinh dữ liệu liên tục như message broker, một lần polling không có message chưa chắc có nghĩa là nguồn đã kết thúc. Nếu reader trả `null`, Spring Batch hiểu Step đã hết input.

Với nguồn dạng streaming hoặc queue, cần định nghĩa rõ cửa sổ xử lý, điều kiện kết thúc, timeout hoặc cách polling. Nếu cần chờ thêm dữ liệu, reader phải sử dụng cơ chế phù hợp thay vì dùng `null` để biểu thị "chưa có item lúc này".

### Nguồn nhiều file hoặc nhiều delegate

Nếu một reader điều phối nhiều file, EOF của file thứ nhất chỉ có nghĩa file đó đã hết. Reader tổng hợp phải chuyển sang file tiếp theo và chỉ trả `null` khi tất cả resource đã hết.

~~~java
public Order read() throws Exception {
    while (currentReader != null) {
        Order item = currentReader.read();

        if (item != null) {
            return item;
        }

        currentReader = nextReader();
    }

    return null;
}
~~~

Ví dụ trên mô tả logic chuyển nguồn. Reader thực tế cần lưu trạng thái file hiện tại và vị trí đọc trong ExecutionContext nếu Job phải restart.

Nếu reader tổng hợp trả `null` ngay khi file đầu tiên hết, các file sau sẽ không được xử lý và chunk cuối của toàn bộ Step sẽ bị kết thúc sớm.

## 10. Checkpoint và restart ở chunk cuối

Spring Batch dùng ExecutionContext để lưu trạng thái reader hoặc writer hỗ trợ restart. Với chunk-oriented Step, checkpoint thường được cập nhật ở ranh giới chunk theo cấu hình.

Giả sử nguồn có 235 item, commit interval 100:

~~~text
Chunk 1: item 1-100    -> commit + checkpoint
Chunk 2: item 101-200  -> commit + checkpoint
Chunk 3: item 201-235  -> writer lỗi -> rollback
~~~

Khi Job restart, reader cần khôi phục trạng thái để xử lý lại phần chưa commit. Với reader hỗ trợ ItemStream, framework gọi các phương thức vòng đời để lưu và khôi phục trạng thái.

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

- `open(...)` khôi phục vị trí đọc.
- `update(...)` lưu trạng thái tại checkpoint.
- `close()` đóng tài nguyên khi Step kết thúc.

Với FlatFileItemReader hoặc paging reader chuẩn, trạng thái đọc có thể được lưu theo cấu hình. Với custom reader, cần tự triển khai việc lưu và khôi phục vị trí phù hợp.

### Không lưu checkpoint khi chỉ mới đọc hết nguồn

EOF không có nghĩa toàn bộ dữ liệu đã commit. Reader có thể đã đọc đến cuối file nhưng writer của chunk cuối vẫn thất bại. Trạng thái reader phải được phối hợp với transaction và checkpoint để lần restart không bỏ qua dữ liệu chưa commit.

Không nên tự lưu vị trí đọc cuối cùng vào một nơi độc lập ngay khi reader thấy EOF. Checkpoint phải phản ánh phần công việc đã được xác nhận theo ranh giới commit.

### Nguồn phải ổn định khi restart

Nếu file đầu vào bị thay đổi sau lần chạy đầu, vị trí dòng đã lưu có thể trỏ đến nội dung khác. Với database paging, nếu tập dữ liệu hoặc sort key thay đổi, restart có thể bỏ sót hoặc đọc trùng.

Một số cách bảo vệ:

- Dùng file bất biến theo batch ID.
- Lưu kích thước, checksum hoặc phiên bản file đầu vào.
- Dùng phạm vi dữ liệu cố định theo batch ID hoặc ngày nghiệp vụ.
- Dùng sort key duy nhất và ổn định cho paging.
- Thiết kế writer idempotent nếu dữ liệu có thể được đọc lại.

## 11. Chunk cuối với FlatFileItemReader

FlatFileItemReader đọc từng dòng và trả `null` khi đã đọc hết resource. Khi số dòng dữ liệu không chia hết cho commit interval, phần cuối file tạo ra một chunk nhỏ hơn.

Ví dụ file có 12 dòng dữ liệu, commit interval 5:

~~~text
Chunk 1: 5 dòng
Chunk 2: 5 dòng
Chunk 3: 2 dòng
EOF
~~~

Cấu hình reader:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .delimited()
        .names("customerId", "fullName", "email")
        .fieldSetMapper(fields -> new CustomerInput(
            fields.readString("customerId"),
            fields.readString("fullName"),
            fields.readString("email")
        ))
        .build();
}
~~~

`linesToSkip(1)` bỏ dòng header, không phải dữ liệu item. Reader vẫn trả từng dòng dữ liệu và kết thúc bằng `null` khi EOF. Chunk cuối chứa số dòng dữ liệu còn lại.

Nếu file chỉ có header, reader không trả item dữ liệu nào. Step có thể hoàn tất với 0 item; nếu nghiệp vụ yêu cầu ít nhất một dòng, cần kiểm tra điều kiện đó riêng.

## 12. Chunk cuối với JdbcPagingItemReader

Paging reader lấy dữ liệu theo từng trang. Page size và commit interval là hai cấu hình liên quan nhưng không nhất thiết phải bằng nhau.

Ví dụ:

~~~java
@Bean
JdbcPagingItemReader<Order> orderReader(DataSource dataSource) {
    return new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("SELECT order_id, amount")
        .fromClause("FROM source_order")
        .whereClause("WHERE batch_id = :batchId")
        .parameterValues(Map.of("batchId", "BATCH-20261115"))
        .sortKeys(Map.of("order_id", Order.ASCENDING))
        .pageSize(500)
        .rowMapper((rs, rowNum) -> new Order(
            rs.getLong("order_id"),
            rs.getBigDecimal("amount")
        ))
        .build();
}
~~~

Nếu tổng số bản ghi là 1.230, page size là 500 và commit interval là 200, reader và Step có thể phối hợp thành nhiều chunk 200 item, còn page được lấy theo kích thước 500. Chunk cuối cùng có 30 item.

Cần dùng sort key ổn định và duy nhất. Page size điều khiển số dòng lấy mỗi lần truy vấn; commit interval điều khiển số item được gom cho một transaction chunk. Không nên nhầm hai giá trị này.

## 13. Chunk cuối khi processor lọc nhiều item

Commit interval thường được tính dựa trên số item đầu vào được đọc, trong khi writer nhận các item đầu ra sau processor. Vì vậy, số lượng item writer nhận có thể nhỏ hơn commit interval.

Ví dụ commit interval 5, nguồn có 7 item:

~~~text
Chunk 1 input: A, B, C, D, E
Processor:     A -> A'
               B -> null (lọc)
               C -> C'
               D -> null (lọc)
               E -> E'
Writer output: A', C', E'

Chunk 2 input: F, G, null (EOF)
Processor:     F -> F'
               G -> null
Writer output: F'
~~~

Chunk thứ hai có hai item đầu vào trước EOF, nhưng chỉ một item đầu ra. Chunk vẫn được hoàn tất theo ranh giới EOF.

Các bộ đếm cần được hiểu riêng:

- `readCount`: số item reader đã cung cấp.
- `filterCount`: số item processor lọc.
- `writeCount`: số item được ghi.
- Skip counts: số item hoặc thao tác bị bỏ qua theo chính sách lỗi.

Không nên cho rằng writer luôn nhận đúng số item bằng commit interval hoặc số item cuối luôn bằng phần dư của writeCount.

## 14. Commit count và cách đọc metrics

StepExecution lưu các bộ đếm như:

| Thuộc tính | Ý nghĩa |
|---|---|
| `readCount` | Số item reader trả về |
| `writeCount` | Số item được writer ghi |
| `filterCount` | Số item bị processor lọc |
| `readSkipCount` | Số lỗi đọc được skip |
| `processSkipCount` | Số lỗi xử lý được skip |
| `writeSkipCount` | Số lỗi ghi được skip |
| `commitCount` | Số lần commit của Step |
| `rollbackCount` | Số lần rollback |

Với nguồn 235 item, commit interval 100 và không có filter hoặc skip, có ba chunk chứa item: 100, 100 và 35. Đây là cách tính nhóm item đầu vào.

Không nên dùng một công thức đơn giản để khẳng định `commitCount` luôn bằng `ceil(readCount / commitInterval)` trong mọi tình huống. Retry, skip, rollback, Tasklet execution, transaction metadata và lượt đọc xác nhận EOF có thể ảnh hưởng số liệu thực tế. Hãy dùng commitCount để quan sát transaction của Step và đối chiếu cùng các bộ đếm khác.

### Phát hiện chunk cuối không được ghi

Với Job quan trọng, nên đối chiếu số lượng nguồn độc lập với readCount, filterCount, skip counts và writeCount.

Ví dụ nguồn có 235 bản ghi:

~~~text
Expected source count = 235
readCount             = 235
filterCount           = 5
readSkipCount         = 0
processSkipCount      = 0
writeSkipCount        = 0
writeCount            = 230
~~~

Trong ví dụ, 5 item bị lọc và 230 item được ghi. Đây có thể là kết quả hợp lệ nếu chính sách nghiệp vụ cho phép lọc 5 item.

Nếu `readCount = 200` nhưng nguồn xác nhận có 235 bản ghi, cần điều tra reader, điều kiện truy vấn, EOF và cấu hình nguồn. Không thể kết luận chunk cuối tự động được ghi chỉ từ trạng thái Step COMPLETED.

## 15. Kiểm thử hành vi chunk completion khi reader kết thúc

Nên kiểm thử ít nhất các trường hợp:

| Số item nguồn | Commit interval | Điều cần xác nhận |
|---:|---:|---|
| 0 | 5 | Step hoàn tất với 0 item nếu đầu vào rỗng hợp lệ |
| 2 | 5 | Hai item cuối vẫn được ghi |
| 5 | 5 | Chunk đầy được ghi, EOF kết thúc Step |
| 7 | 5 | Chunk 5 và chunk cuối 2 đều được ghi |
| 10 | 5 | Hai chunk đầy được ghi |
| 12 | 5 | Hai chunk đầy và chunk cuối 2 được ghi |
| 7 | 5, processor lọc 2 | read, filter và write count phản ánh đúng |
| 7 | 5, writer lỗi ở chunk cuối | Chunk cuối rollback hoặc retry theo policy |

### Kiểm thử reader và writer bằng danh sách cố định

Ví dụ một Step dùng nguồn có 7 item và commit interval 5:

~~~java
@Bean
ItemReader<Integer> numberReader() {
    return new ListItemReader<>(List.of(1, 2, 3, 4, 5, 6, 7));
}
~~~

Một writer test có thể thu thập kích thước chunk nhận được:

~~~java
@Bean
List<Integer> writtenItems() {
    return new CopyOnWriteArrayList<>();
}

@Bean
ItemWriter<Integer> collectingWriter(List<Integer> writtenItems) {
    return chunk -> writtenItems.addAll(chunk.getItems());
}
~~~

Sau khi Job hoàn tất, xác nhận danh sách ghi ra có đủ 7 item và đúng thứ tự nếu Step được cấu hình đơn luồng. Nếu cần xác nhận ranh giới chunk, dùng một writer test ghi nhận riêng kích thước từng lần gọi.

Kết quả mong đợi về nhóm item:

~~~text
write call 1: [1, 2, 3, 4, 5]
write call 2: [6, 7]
~~~

Ví dụ này minh họa trường hợp không filter, không skip và không retry. Trong kiểm thử thực tế, cần dùng test context và JobRepository phù hợp với phiên bản Spring Batch của ứng dụng.

### Kiểm thử nguồn rỗng

Nguồn rỗng cần được kiểm thử riêng:

~~~java
@Bean
ItemReader<Integer> emptyReader() {
    return new ListItemReader<>(List.of());
}
~~~

Xác nhận Step kết thúc đúng trạng thái, không có item được ghi và Job xử lý kết quả 0 item theo yêu cầu nghiệp vụ.

### Kiểm thử lỗi ở chunk cuối

Đặt writer phát sinh exception khi nhận chunk cuối. Sau khi Step thất bại, xác nhận:

- Các chunk trước đã commit vẫn tồn tại.
- Thay đổi của chunk cuối được rollback nếu tham gia transaction.
- Step có trạng thái lỗi phù hợp.
- Khi restart, reader khôi phục phần chưa commit.
- Writer không tạo dữ liệu trùng khi xử lý lại.

## 16. Những lỗi hiểu nhầm thường gặp

### Nghĩ rằng chunk cuối phải đủ commit interval

Chunk size là giới hạn số item gom cho một chunk. EOF có thể kết thúc chunk sớm; phần item còn lại vẫn được xử lý.

### Tự bỏ phần dư trong reader

Không nên giữ item cuối trong buffer rồi bỏ khi số lượng chưa đạt commit interval. Spring Batch sẽ xử lý phần chunk còn lại khi reader trả `null`.

### Coi null là lỗi

`null` là kết thúc nguồn bình thường. Lỗi đọc phải được biểu diễn bằng exception để skip/retry/fail policy xử lý.

### Tự gọi writer để ghi phần còn lại

Writer được gọi bởi framework trong luồng chunk. Tự gọi writer từ reader hoặc listener có thể phá transaction và thống kê.

### Nhầm page size với commit interval

Page size điều khiển lượng dữ liệu truy vấn theo trang; commit interval điều khiển nhóm item của transaction chunk. Hai giá trị có thể khác nhau.

### Cho rằng Job COMPLETED đồng nghĩa không mất dữ liệu

Job có thể hoàn tất với ít item hơn dự kiến do điều kiện nguồn, filter, skip hoặc reader trả EOF sớm. Cần đối chiếu số lượng nguồn và các bộ đếm StepExecution.

### Xóa nguồn ngay khi reader trả EOF

Reader đã đọc hết nguồn không có nghĩa chunk cuối đã được writer ghi và commit. Chỉ dọn nguồn sau khi Step hoàn tất và các bước cần thiết đã xác nhận kết quả.

### Chỉ kiểm thử số lượng chia hết cho chunk size

Nếu chỉ thử 100, 200 hoặc 300 item với commit interval 100, bài kiểm thử không bao phủ chunk cuối không đầy. Cần có trường hợp 1, 99, 101 hoặc 235 item.

## 17. Quy trình kiểm tra khi dữ liệu cuối nguồn bị thiếu

Nếu số lượng output thấp hơn dự kiến, hãy xác định phần chênh lệch nằm ở reader, processor, writer hay transaction:

1. **Đếm nguồn:** xác định số item thuộc đúng batch hoặc phạm vi đầu vào.
2. **Kiểm tra readCount:** xác nhận reader đã cung cấp đủ item chưa.
3. **Kiểm tra EOF:** tìm logic trả `null` trong reader tùy chỉnh, multi-resource reader hoặc điều kiện truy vấn.
4. **Kiểm tra filterCount:** xác định item bị processor lọc.
5. **Kiểm tra skip counts:** xem lỗi đọc, xử lý hoặc ghi nào đã được skip.
6. **Kiểm tra writeCount:** xác nhận số item được ghi thành công.
7. **Kiểm tra transaction:** xem rollbackCount, log writer và trạng thái chunk cuối.
8. **Kiểm tra restart:** xác nhận checkpoint có phản ánh đúng chunk đã commit.
9. **Kiểm tra nguồn phân trang:** xác nhận sort key, page size và dữ liệu nguồn có ổn định.
10. **Đối soát dữ liệu đích:** tìm item cuối cùng đã ghi và item đầu tiên bị thiếu.

Nếu reader trả EOF quá sớm, kiểm tra các điều kiện như dòng trống, lỗi parse bị nuốt, resource list, giới hạn truy vấn và trạng thái iterator. Nếu readCount đầy đủ nhưng writeCount thấp, xem filter, skip và writer transaction.

Không nên chạy lại ngay một Job có writer không idempotent trước khi xác định các chunk đã commit. Restart sai cách có thể tạo dữ liệu trùng hoặc làm cho số liệu đối soát khó hiểu hơn.

## 18. Những điểm cần nhớ

- Commit interval là kích thước tối đa của chunk, không phải số item tối thiểu bắt buộc.
- Khi ItemReader trả `null`, Spring Batch kết thúc việc đọc và xử lý chunk hiện tại.
- Chunk cuối có thể nhỏ hơn commit interval và vẫn được ghi, commit bình thường.
- Nếu nguồn rỗng, không có item nghiệp vụ để ghi; Step có thể hoàn tất với 0 item nếu được phép.
- Nếu số item chia hết cho commit interval, các chunk đầy được xử lý trước khi framework xác nhận EOF.
- Processor có thể lọc item trong chunk cuối; writer nhận các item đầu ra còn lại.
- EOF không trực tiếp commit transaction; transaction manager commit sau khi chunk được xử lý thành công.
- Exception khi đọc khác EOF và phải được xử lý theo skip/retry/fail policy.
- Chunk cuối có thể rollback nếu writer thất bại; các chunk trước đã commit vẫn được giữ.
- Reader và checkpoint cần hỗ trợ restart để xử lý lại phần chưa commit.
- Page size và commit interval điều khiển hai khía cạnh khác nhau.
- Dùng readCount, filterCount, skip counts và writeCount để đối soát dữ liệu, không dựa riêng vào trạng thái COMPLETED.
- Kiểm thử cả nguồn rỗng, nguồn nhỏ hơn chunk size, số lượng chia hết và không chia hết cho commit interval.

Khi reader kết thúc, Spring Batch vẫn hoàn tất phần dữ liệu đã đọc trong chunk cuối. Thiết kế reader đúng hợp đồng, writer tham gia transaction phù hợp và kiểm thử với số lượng không chia hết cho commit interval giúp tránh mất phần dữ liệu cuối nguồn.

