# Reader không được bỏ qua item ngoài ý muốn

Trong Spring Batch, **ItemReader** là thành phần đưa dữ liệu từ nguồn vào một Step. Reader có trách nhiệm cung cấp lần lượt các item cho framework. Một quy tắc rất quan trọng của hợp đồng này là: **chỉ trả về null khi nguồn đầu vào đã hết**.

Nếu reader trả về null vì gặp một dòng lỗi, một bản ghi không hợp lệ, một khoảng trống tạm thời hoặc một sự cố đọc dữ liệu, Spring Batch có thể hiểu rằng toàn bộ nguồn đã kết thúc. Các bản ghi phía sau sẽ không được đọc. Đây là một trong những nguyên nhân nguy hiểm khiến Job hoàn tất nhưng dữ liệu bị thiếu mà không có lỗi rõ ràng.

Bài học này giải thích hợp đồng của ItemReader, cách phân biệt kết thúc nguồn với lọc và bỏ qua bản ghi, những lỗi triển khai thường gặp, cách cấu hình reader để tránh mất item, cũng như cách theo dõi và kiểm thử tính đầy đủ của dữ liệu.

## 1. Hợp đồng của ItemReader

Giao diện cơ bản của ItemReader:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Mỗi lần Spring Batch gọi phương thức read(), reader phải trả về một trong hai kết quả:

- Một đối tượng kiểu T nếu đọc được item tiếp theo.
- null nếu không còn item nào trong nguồn đầu vào.

Nếu không thể đọc hoặc chuyển đổi dữ liệu, reader nên ném exception phù hợp để framework và chính sách lỗi của Step xử lý. Không nên biến lỗi thành null.

~~~mermaid
flowchart TD
    A["Spring Batch gọi read()"] --> B{"Còn item trong nguồn?"}
    B -- "Có" --> C["Trả về item"]
    C --> A
    B -- "Không" --> D["Trả về null"]
    B -- "Lỗi đọc / parse" --> E["Ném exception"]
    E --> F["Step xử lý theo skip / retry / fail"]
~~~

Spring Batch tiếp tục gọi read() cho đến khi reader trả về null. Giá trị null là tín hiệu kết thúc đầu vào của reader, không phải một item rỗng và cũng không phải cách biểu diễn một bản ghi không hợp lệ.

### Một lần đọc tương ứng với một item

Reader thường được gọi lặp lại trong một chunk-oriented Step. Framework quản lý số lần gọi và gom item theo commit interval. Ứng dụng không nên tự gọi read() thêm lần nữa bên ngoài luồng do Step quản lý, vì làm như vậy có thể tiêu thụ item trước khi framework nhận được chúng.

Ví dụ, nếu nguồn có năm bản ghi A, B, C, D và E, chuỗi kết quả bình thường phải là:

~~~text
read() -> A
read() -> B
read() -> C
read() -> D
read() -> E
read() -> null
~~~

Nếu reader trả về null ngay sau C, framework kết thúc việc đọc và D, E sẽ không được chuyển đến processor hoặc writer. Job có thể hoàn tất với số lượng dữ liệu ít hơn nguồn thực tế.

### Không dùng null để báo lỗi

Một số cách viết sai thường gặp:

~~~java
public Customer read() {
    try {
        return readNextCustomer();
    } catch (Exception ex) {
        return null; // Sai: lỗi bị hiểu thành hết dữ liệu.
    }
}
~~~

~~~java
public Customer read() {
    String line = readNextLine();

    if (line == null || line.isBlank()) {
        return null; // Sai nếu dòng trống không có nghĩa là EOF.
    }

    return map(line);
}
~~~

Trong ví dụ đầu, lỗi đọc bị che giấu. Trong ví dụ thứ hai, một dòng trống có thể làm reader kết thúc dù phía sau vẫn còn dữ liệu.

Cách đúng là phân biệt rõ:

- Nguồn thực sự hết dữ liệu: trả về null.
- Đọc được bản ghi: trả về item.
- Bản ghi sai định dạng hoặc không thể đọc: ném exception.
- Bản ghi cần loại bỏ theo nghiệp vụ: dùng cơ chế lọc được thiết kế rõ ràng.

## 2. Phân biệt kết thúc nguồn, lọc và skip

Ba khái niệm này có ý nghĩa khác nhau trong Spring Batch.

| Hành vi | Thành phần / cách thực hiện | Ý nghĩa |
|---|---|---|
| Kết thúc nguồn | ItemReader trả về null | Không còn item nào để đọc |
| Lọc item | ItemProcessor trả về null | Item đã đọc nhưng không chuyển sang writer |
| Skip item lỗi | Cấu hình fault-tolerant skip cho exception | Bỏ qua bản ghi hoặc thao tác lỗi theo chính sách đã khai báo |
| Đọc thành công | ItemReader trả về item | Item được chuyển vào luồng xử lý |

### Lọc bằng ItemProcessor

Nếu một bản ghi hợp lệ về cấu trúc nhưng không cần xuất ra kết quả theo quy tắc nghiệp vụ, ItemProcessor có thể trả về null.

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if ("CANCELLED".equalsIgnoreCase(input.status())) {
            return null; // Lọc có chủ đích.
        }

        return new Order(
            input.orderId(),
            input.customerId(),
            input.amount()
        );
    };
}
~~~

Trong ví dụ, reader vẫn đọc bản ghi đơn hàng đã hủy và processor quyết định lọc nó. Đây là cách thể hiện rõ ràng hơn so với việc reader âm thầm bỏ bản ghi.

Spring Batch có thể ghi nhận số item bị lọc trong filterCount của StepExecution. Nhờ đó, nhóm vận hành có thể phân biệt số item đã đọc với số item được chuyển đến writer.

### Skip khi có exception

Nếu một dòng file không thể parse hoặc một item gặp lỗi được phép bỏ qua, có thể dùng cơ chế skip của Step:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
}
~~~

Cấu hình này cho phép bỏ qua exception thuộc loại FlatFileParseException trong giới hạn đã khai báo. Khi vượt quá skip limit, Step thất bại.

Skip phải là quyết định nghiệp vụ có chủ đích. Nếu dữ liệu lỗi cần được điều tra, hãy ghi lại thông tin về dòng, nguồn, nguyên nhân và mã lô bằng listener hoặc cơ chế audit phù hợp. Không nên chỉ tăng skip limit để Job chạy qua lỗi mà không biết dữ liệu nào đã bị bỏ.

### Vì sao không lọc trong reader?

Reader có thể đọc từ một truy vấn SQL chỉ lấy các bản ghi đáp ứng điều kiện nghiệp vụ. Đây là một lựa chọn hợp lệ khi điều kiện đó là định nghĩa của tập đầu vào. Tuy nhiên, reader tùy chỉnh không nên âm thầm bỏ item sau khi đã đọc mà không có quy tắc và thống kê rõ ràng.

Hãy phân biệt hai trường hợp:

- **Chọn nguồn đầu vào:** câu SQL có WHERE clause hoặc cấu hình nguồn xác định rõ những bản ghi thuộc lô cần xử lý.
- **Lọc item đã đọc:** processor quyết định item có được chuyển sang writer hay không.

Khi dùng bộ lọc ở nguồn, cần ghi nhận điều kiện truy vấn và số lượng bản ghi nguồn dự kiến. Nếu không, việc thiếu dữ liệu do WHERE clause quá rộng hoặc điều kiện sai có thể bị nhầm với reader kết thúc bình thường.

## 3. Lỗi thường gặp khiến reader bỏ qua item

### Trả về null khi gặp dòng trống

Dòng trống không nhất thiết là EOF. File có thể chứa dòng trống ở giữa và còn nhiều bản ghi phía sau.

Nếu định dạng nghiệp vụ cho phép dòng trống, hãy xử lý nó theo quy tắc đã xác định: coi là bản ghi lỗi, bỏ qua có ghi nhận, hoặc xem là dòng không mang dữ liệu. Đừng tự động coi mọi dòng trống là hết file.

### Bắt exception rồi trả về null

Đây là lỗi nghiêm trọng vì exception bị che giấu và Spring Batch không biết reader đã gặp lỗi. Job có thể kết thúc với trạng thái COMPLETED dù mới đọc được một phần nguồn.

Hãy để exception được truyền ra, hoặc chuyển nó thành exception phù hợp với chính sách skip/retry của Step. Chỉ bắt exception khi có thể xử lý đúng và vẫn bảo toàn hợp đồng đọc.

### Bỏ qua bản ghi không hợp lệ ngay trong vòng lặp

Một custom reader có thể có vòng lặp tìm item tiếp theo:

~~~java
public OrderInput read() {
    while (iterator.hasNext()) {
        String line = iterator.next();

        if (isValid(line)) {
            return map(line);
        }
    }

    return null;
}
~~~

Đoạn mã này âm thầm loại mọi dòng không hợp lệ. Nếu yêu cầu là kiểm tra và ghi nhận lỗi dữ liệu, cách làm này khiến các bản ghi lỗi biến mất mà không có số liệu skip hoặc thông tin để đối soát.

Nếu cần lọc ở reader theo thiết kế, phải ghi rõ lý do, điều kiện lọc và số lượng bị loại. Với các quy tắc nghiệp vụ thông thường, hãy trả về raw item rồi để processor kiểm tra và quyết định.

### Nhầm nguồn tạm thời chưa có dữ liệu với EOF

Một nguồn có thể tạm thời chưa trả về dữ liệu nhưng vẫn còn dữ liệu sẽ đến sau. Nếu reader trả về null, Spring Batch xem nguồn đã kết thúc và Step có thể hoàn tất.

ItemReader phù hợp với nguồn có thể xác định thời điểm kết thúc. Với hàng đợi hoặc luồng dữ liệu liên tục, cần thiết kế cách polling, timeout, cửa sổ lấy dữ liệu hoặc cơ chế điều khiển vòng lặp rõ ràng. Không dùng null làm tín hiệu "hiện chưa có message" nếu nguồn vẫn còn khả năng phát sinh message cho cùng lần xử lý.

### Đọc trước hoặc tiêu thụ iterator nhiều lần

Một reader tùy chỉnh có thể gọi next() trong một hàm kiểm tra, sau đó lại gọi next() trong hàm map. Điều này làm mất một item giữa hai lần đọc.

Hãy bảo đảm mỗi item nguồn chỉ được tiêu thụ đúng một lần cho mỗi lần read() và không có đoạn code khác đọc chung iterator hoặc cursor ngoài reader.

### Thay đổi dữ liệu nguồn trong khi phân trang

Với reader phân trang từ database, nếu thứ tự sắp xếp không ổn định hoặc dữ liệu bị thêm/xóa trong lúc Job chạy, một bản ghi có thể bị lặp hoặc bỏ sót giữa các trang.

Hãy dùng thứ tự xác định, ưu tiên khóa duy nhất, và xem xét snapshot hoặc điều kiện phạm vi dữ liệu phù hợp với nghiệp vụ.

## 4. Cấu hình FlatFileItemReader để không kết thúc sớm

FlatFileItemReader đọc file văn bản theo từng dòng và ánh xạ mỗi dòng thành item. Cấu hình cần thể hiện rõ resource, encoding, header, cách tách trường và cách ánh xạ.

Ví dụ:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .strict(true)
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

Một số điểm cần chú ý:

- **name:** đặt tên ổn định cho reader, giúp định danh trạng thái trong ExecutionContext.
- **resource:** xác định đúng file cần đọc.
- **encoding:** dùng encoding đúng với file, ví dụ UTF-8.
- **strict(true):** báo lỗi nếu resource không tồn tại hoặc không thể mở theo cấu hình strict.
- **linesToSkip(1):** chỉ bỏ dòng header đã được xác định, không bỏ các dòng dữ liệu tùy ý.
- **names(...):** ánh xạ đúng thứ tự cột.
- **fieldSetMapper:** chuyển các trường thành kiểu dữ liệu ứng dụng.

### Cẩn thận với strict(false)

Nếu cấu hình reader không strict, file không tồn tại có thể được xử lý như nguồn không có dữ liệu thay vì lỗi mở file. Khi file đầu vào là bắt buộc, điều này rất nguy hiểm: Job có thể hoàn tất với 0 item mà không báo lỗi như mong đợi.

Chỉ dùng chế độ không strict khi nghiệp vụ xác định file thiếu đồng nghĩa với không có dữ liệu và hành vi đó đã được kiểm soát. Với file bắt buộc, giữ strict mode và kiểm tra file trước khi bắt đầu nhập.

### Chỉ bỏ qua header đã định nghĩa

linesToSkip được dùng để bỏ qua số dòng đầu file, thường là header. Không tăng giá trị này để né các dòng lỗi ở đầu file. Nếu file có nhiều loại dòng như header, trailer hoặc comment, hãy dùng cơ chế parsing phù hợp để nhận diện từng loại và ghi nhận rõ dòng nào được loại.

Có thể dùng skippedLinesCallback để đọc nội dung các dòng header bị bỏ qua, ví dụ xác nhận tên cột hoặc phiên bản định dạng file. Nếu header không đúng, callback có thể ném exception để dừng Job sớm.

## 5. Xử lý dòng sai định dạng thay vì làm mất dữ liệu

FlatFileItemReader sử dụng LineMapper để chuyển dòng văn bản thành item. Nếu dòng không đúng cấu trúc, mapper hoặc FieldSetMapper có thể ném exception.

Ví dụ:

~~~java
@Bean
LineMapper<CustomerInput> customerLineMapper() {
    DefaultLineMapper<CustomerInput> mapper =
        new DefaultLineMapper<>();

    DelimitedLineTokenizer tokenizer =
        new DelimitedLineTokenizer();

    tokenizer.setNames("customerId", "fullName", "email");

    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new CustomerInput(
        fields.readString("customerId"),
        fields.readString("fullName"),
        fields.readString("email")
    ));

    return mapper;
}
~~~

Nếu một dòng có thiếu cột hoặc giá trị không thể chuyển đổi, hãy quyết định rõ:

- Dừng Job để yêu cầu sửa file.
- Skip dòng trong giới hạn cho phép và ghi lại thông tin lỗi.
- Đưa bản ghi lỗi vào file reject hoặc bảng quarantine để xử lý sau.

Không nên trả về null từ mapper hoặc reader để che giấu lỗi. Null trong hợp đồng ItemReader có nghĩa là không còn item tiếp theo.

### Ví dụ ghi nhận dòng bị skip

Có thể dùng SkipListener để ghi nhận lỗi đọc:

~~~java
@Bean
SkipListener<CustomerInput, Customer> customerSkipListener(
        RejectedRecordService rejectedRecordService) {

    return new SkipListener<>() {
        @Override
        public void onSkipInRead(Throwable throwable) {
            if (throwable instanceof FlatFileParseException ex) {
                rejectedRecordService.record(
                    ex.getInput(),
                    ex.getLineNumber(),
                    ex.getMessage()
                );
            }
        }

        @Override
        public void onSkipInProcess(
                CustomerInput item,
                Throwable throwable) {
            rejectedRecordService.record(
                item,
                throwable.getMessage()
            );
        }

        @Override
        public void onSkipInWrite(
                Customer item,
                Throwable throwable) {
            rejectedRecordService.record(
                item,
                throwable.getMessage()
            );
        }
    };
}
~~~

Listener minh họa cách ghi lại lỗi đọc, xử lý và ghi. Trong ứng dụng thực tế, cần triển khai service lưu dữ liệu reject và xác định transaction boundary phù hợp để thông tin lỗi không bị mất khi chunk rollback.

## 6. Reader cho database và phân trang

Với dữ liệu database, reader thường dùng cursor hoặc paging. Hai loại này có hành vi khác nhau nhưng đều phải trả về từng item cho đến khi kết quả đã đọc hết.

### JdbcCursorItemReader

Cursor reader mở một ResultSet và đọc lần lượt các dòng. Ví dụ:

~~~java
@Bean
JdbcCursorItemReader<CustomerInput> customerCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<CustomerInput>()
        .name("customerCursorReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name, email
            FROM customer_import_source
            ORDER BY customer_id
            """)
        .rowMapper((rs, rowNum) -> new CustomerInput(
            rs.getString("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ))
        .fetchSize(500)
        .build();
}
~~~

Một số điểm quan trọng:

- Truy vấn cần trả về toàn bộ tập dữ liệu mong muốn.
- ORDER BY nên ổn định để kết quả có thứ tự xác định.
- RowMapper không nên trả về null để loại một dòng.
- Nếu chuyển đổi một cột thất bại, hãy để lỗi được báo hoặc xử lý bằng chính sách phù hợp.
- Cần hiểu transaction, connection và cursor lifecycle của datasource.

### JdbcPagingItemReader

Paging reader thực hiện truy vấn theo từng trang. Cấu hình phải có sort key xác định thứ tự:

~~~java
@Bean
JdbcPagingItemReader<CustomerInput> customerPagingReader(
        DataSource dataSource) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
        .name("customerPagingReader")
        .dataSource(dataSource)
        .selectClause("SELECT customer_id, full_name, email")
        .fromClause("FROM customer_import_source")
        .whereClause("WHERE active = true")
        .sortKeys(Map.of("customer_id", Order.ASCENDING))
        .rowMapper((rs, rowNum) -> new CustomerInput(
            rs.getString("customer_id"),
            rs.getString("full_name"),
            rs.getString("email")
        ))
        .pageSize(500)
        .build();
}
~~~

Trong ví dụ, điều kiện WHERE là một phần định nghĩa tập nguồn: chỉ những khách hàng có active = true thuộc lô nhập. Sort key customer_id giúp thứ tự trang ổn định nếu khóa này là duy nhất và không thay đổi trong lúc Job chạy.

Nếu sort key không duy nhất, các dòng có cùng giá trị có thể bị phân trang không ổn định. Hãy bổ sung khóa duy nhất hoặc dùng bộ sort key xác định toàn bộ thứ tự.

### Dữ liệu thay đổi trong lúc đọc

Nếu bảng nguồn được cập nhật trong khi Job đang phân trang, kết quả có thể không còn là một snapshot nhất quán. Tùy database và transaction isolation, việc thêm, xóa hoặc thay đổi sort key có thể khiến bản ghi xuất hiện ở trang khác hoặc bị bỏ qua.

Một số cách kiểm soát:

- Chọn một phạm vi lô cố định, ví dụ batch_id hoặc business_date.
- Dùng snapshot isolation khi phù hợp.
- Dùng khóa tăng dần không thay đổi làm sort key.
- Không thay đổi tập dữ liệu đầu vào trong khi Job đang xử lý nếu yêu cầu tính nhất quán nghiêm ngặt.
- Ghi lại tiêu chí truy vấn để có thể đối soát số lượng nguồn.

## 7. Reader tùy chỉnh: quản lý trạng thái iterator chính xác

Khi triển khai custom ItemReader, cần bảo đảm mỗi lần read() tiêu thụ đúng một item và chỉ trả về null khi iterator đã hết.

Ví dụ reader đơn giản cho một danh sách cố định:

~~~java
public class ListItemReader<T> implements ItemReader<T> {

    private final Iterator<T> iterator;

    public ListItemReader(List<T> items) {
        this.iterator = items.iterator();
    }

    @Override
    public T read() {
        if (!iterator.hasNext()) {
            return null;
        }

        return iterator.next();
    }
}
~~~

Reader này phù hợp với tập dữ liệu nhỏ, cố định trong bộ nhớ. Nó không tự hỗ trợ restart vì vị trí iterator chưa được lưu trong ExecutionContext.

### Không dùng vòng lặp để âm thầm bỏ item

Nếu reader cần lọc dữ liệu, đoạn mã như sau có thể gây mất dấu bản ghi:

~~~java
public Customer read() {
    while (iterator.hasNext()) {
        Customer item = iterator.next();

        if (item.isEligible()) {
            return item;
        }
    }

    return null;
}
~~~

Trong trường hợp này, các item không eligible bị loại trong reader và không được ghi nhận trong filterCount. Nếu đó là quy tắc nghiệp vụ, hãy chuyển kiểm tra sang processor hoặc tạo thống kê loại bỏ riêng.

Cách minh bạch hơn:

~~~java
public CustomerInput read() {
    if (!iterator.hasNext()) {
        return null;
    }

    return iterator.next();
}
~~~

Sau đó processor quyết định item có được giữ lại hay không.

### Không gọi read() để kiểm tra trước

Đừng gọi reader.read() trong một hàm kiểm tra dữ liệu rồi bỏ kết quả, sau đó để Spring Batch gọi read() lần nữa. Cách này tiêu thụ item đầu tiên và khiến framework không bao giờ nhận được item đó.

Nếu cần kiểm tra nguồn trước khi chạy, hãy dùng một bước preflight riêng hoặc kiểm tra metadata của nguồn mà không tiêu thụ nội dung.

## 8. Restart và trạng thái của reader

Một reader có thể đọc đúng trong lần chạy đầu nhưng mất item hoặc đọc lặp khi Job restart nếu không lưu và khôi phục vị trí đọc.

Nhiều reader có hỗ trợ ItemStream để lưu trạng thái:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Với reader hỗ trợ ItemStream:

- open() khôi phục vị trí đọc từ ExecutionContext.
- update() lưu trạng thái hiện tại tại checkpoint.
- close() đóng tài nguyên khi Step kết thúc.

Ví dụ FlatFileItemReader có thể lưu vị trí dòng đã đọc. Khi Job restart, reader sử dụng ExecutionContext để tiếp tục ở vị trí tương ứng với chunk đã commit.

### saveState

Các reader được xây dựng bằng builder thường hỗ trợ cấu hình saveState. Khi cần restart, không nên tắt lưu trạng thái mà không có thiết kế thay thế.

Nếu saveState bị tắt hoặc reader tùy chỉnh không lưu vị trí:

- Restart có thể bắt đầu đọc lại từ đầu.
- Item đã ghi ở chunk trước có thể được đọc và ghi lại.
- Nếu nguồn thay đổi, thứ tự và tập item có thể khác lần chạy đầu.
- Đối soát số lượng có thể không khớp.

Không lưu trạng thái không đồng nghĩa reader sẽ trả null sớm trong lần chạy hiện tại, nhưng có thể khiến lần restart không tiếp tục từ đúng vị trí.

### Tự triển khai ItemStreamReader

Một reader tùy chỉnh cần restart có thể triển khai ItemStreamReader và lưu index:

~~~java
public class RestartableListReader
        implements ItemStreamReader<String> {

    private final List<String> items;
    private int currentIndex;

    public RestartableListReader(List<String> items) {
        this.items = items;
    }

    @Override
    public String read() {
        if (currentIndex >= items.size()) {
            return null;
        }

        return items.get(currentIndex++);
    }

    @Override
    public void open(ExecutionContext context) {
        currentIndex = context.getInt("current.index", 0);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt("current.index", currentIndex);
    }

    @Override
    public void close() {
        // Đóng tài nguyên nếu reader có sử dụng.
    }
}
~~~

Đây là ví dụ minh họa cho nguồn danh sách cố định. Trong thực tế, nguồn cần ổn định giữa lần chạy đầu và restart. Nếu danh sách bị sắp xếp lại hoặc thay đổi nội dung, lưu index đơn thuần có thể làm reader bỏ qua hoặc đọc lặp item. Với nguồn database, thường nên lưu khóa hoặc vị trí truy vấn theo cơ chế phù hợp.

## 9. Rollback và việc đọc lại item

Trong chunk-oriented Step, reader có thể đã đọc một số item trước khi writer thất bại. Khi transaction rollback, Spring Batch cần xử lý việc đọc lại các item thuộc chunk chưa commit.

Nhiều reader chuẩn hỗ trợ cơ chế buffering và checkpoint để framework có thể khôi phục dữ liệu đọc. Tuy nhiên, reader tùy chỉnh cần hiểu rõ cách nó tương tác với transaction và rollback.

Một số lưu ý:

- Không xóa hoặc xác nhận item khỏi nguồn ngoài trước khi chunk commit nếu không có cơ chế phục hồi.
- Với message queue, cần hiểu acknowledgment và transaction của broker.
- Với reader có side effect, rollback database không tự hoàn tác side effect đó.
- Reader tùy chỉnh nên hỗ trợ ItemStream nếu cần lưu checkpoint.
- Kiểm thử tình huống writer thất bại để xác nhận item chưa commit không bị mất.

Nếu nguồn là queue, việc lấy message có thể làm message biến mất khỏi hàng đợi hoặc chuyển sang trạng thái in-flight. Cần cấu hình acknowledgment, transaction hoặc redelivery phù hợp để message được giao lại khi chunk thất bại. Không thể dựa vào rollback của database để đảm bảo message được đưa trở lại queue.

## 10. Quan sát số lượng item để phát hiện mất dữ liệu

Reader âm thầm bỏ item có thể khiến Job hoàn tất mà không có exception. Vì vậy, cần đối chiếu số liệu giữa nguồn, reader, processor và writer.

Một số bộ đếm trong StepExecution:

| Bộ đếm | Ý nghĩa |
|---|---|
| readCount | Số item reader trả về thành công |
| writeCount | Số item writer ghi thành công |
| filterCount | Số item processor lọc bằng cách trả về null |
| readSkipCount | Số lỗi đọc được skip |
| processSkipCount | Số lỗi xử lý được skip |
| writeSkipCount | Số lỗi ghi được skip |
| commitCount | Số lần commit |
| rollbackCount | Số lần rollback |

Ví dụ:

- Nguồn có 1.000 dòng dữ liệu.
- Reader trả về 1.000 item.
- Processor lọc 20 item.
- Writer ghi 980 item.

Kết quả có thể đối soát như sau:

~~~text
readCount   = 1000
filterCount = 20
writeCount  = 980
~~~

Nếu reader âm thầm bỏ 20 dòng, readCount có thể chỉ là 980 và filterCount bằng 0. Khi không có số liệu nguồn độc lập để so sánh, Job có thể trông như đã xử lý thành công.

Do đó, với các Job quan trọng, nên ghi nhận số lượng bản ghi đầu vào từ nguồn hoặc từ manifest của lô. Sau khi Step hoàn tất, so sánh số lượng dự kiến với readCount, filterCount, skip count và writeCount theo công thức đối soát phù hợp với nghiệp vụ.

Không phải lúc nào readCount cũng phải bằng writeCount. Processor có thể lọc item và chính sách skip có thể bỏ qua bản ghi lỗi. Điều cần thiết là mọi chênh lệch đều được giải thích bằng số liệu và quy tắc đã định nghĩa.

### ItemReadListener

ItemReadListener cung cấp callback để quan sát quá trình đọc:

~~~java
public interface ItemReadListener<T> {
    void beforeRead();
    void afterRead(T item);
    void onReadError(Exception ex);
}
~~~

Có thể dùng listener để ghi log hoặc metrics:

~~~java
@Bean
ItemReadListener<CustomerInput> customerReadListener() {
    return new ItemReadListener<>() {
        @Override
        public void beforeRead() {
            // Có thể tăng metric số lần gọi reader.
        }

        @Override
        public void afterRead(CustomerInput item) {
            // Ghi nhận một item đã được đọc thành công.
        }

        @Override
        public void onReadError(Exception ex) {
            // Ghi nhận lỗi đọc để theo dõi.
        }
    };
}
~~~

Listener không được gọi như một callback đọc thành công cho tín hiệu EOF null. onReadError được gọi khi reader ném exception. Nếu reader tự trả null để che giấu lỗi, listener không thể nhận biết đó là lỗi; vì vậy việc giữ đúng hợp đồng của read() rất quan trọng.

## 11. Reader có nhiều nguồn hoặc nhiều delegate

Một Job có thể đọc từ nhiều nguồn: nhiều file, nhiều bảng hoặc nhiều API. Khi dùng CompositeItemReader hoặc custom reader điều phối nhiều delegate, cần quản lý chính xác thời điểm chuyển nguồn.

Ví dụ một reader nối hai nguồn theo thứ tự:

~~~java
public class TwoSourceReader implements ItemReader<CustomerInput> {

    private final ItemReader<CustomerInput> first;
    private final ItemReader<CustomerInput> second;
    private boolean firstFinished;

    public TwoSourceReader(
            ItemReader<CustomerInput> first,
            ItemReader<CustomerInput> second) {
        this.first = first;
        this.second = second;
    }

    @Override
    public CustomerInput read() throws Exception {
        if (!firstFinished) {
            CustomerInput item = first.read();

            if (item != null) {
                return item;
            }

            firstFinished = true;
        }

        return second.read();
    }
}
~~~

Trong ví dụ, null từ reader thứ nhất chỉ đánh dấu nguồn thứ nhất đã hết. Reader điều phối chuyển sang nguồn thứ hai; chỉ khi reader thứ hai cũng trả null thì toàn bộ reader mới kết thúc.

Nếu custom reader trả null ngay khi nguồn thứ nhất hết, framework sẽ không biết còn nguồn thứ hai và sẽ kết thúc Step sớm.

Với nhiều delegate, cần lưu trạng thái delegate hiện tại vào ExecutionContext để restart không quay lại sai nguồn hoặc bỏ qua phần dữ liệu chưa xử lý. Nếu delegate có ItemStream, cần bảo đảm các delegate được mở, cập nhật và đóng đúng vòng đời.

## 12. Thread safety và đọc song song

Khi Step xử lý song song, nhiều thread có thể truy cập reader cùng lúc tùy cấu hình. Không phải mọi ItemReader đều thread-safe.

Một reader dựa trên iterator hoặc con trỏ dùng chung có thể bị:

- Hai thread đọc cùng một item.
- Một item bị bỏ qua do cập nhật index không đồng bộ.
- Thứ tự item thay đổi ngoài dự kiến.
- Trạng thái checkpoint không nhất quán.

Một số hướng thiết kế:

- Dùng partitioning để mỗi worker có nguồn hoặc phạm vi dữ liệu riêng.
- Dùng reader thread-safe hoặc wrapper đồng bộ khi phù hợp.
- Tránh chia sẻ một iterator không đồng bộ giữa nhiều thread.
- Với paging, chia phạm vi theo khóa hoặc partition key không chồng lấn.
- Kiểm thử với concurrency thực tế thay vì chỉ chạy đơn luồng.

Nếu thứ tự xử lý quan trọng, cần xác định rõ liệu mô hình chạy song song có bảo đảm thứ tự hay không. Không nên giả định reader trả item theo thứ tự nguồn thì writer cũng hoàn tất theo đúng thứ tự đó khi nhiều thread cùng xử lý.

## 13. Kiểm thử để phát hiện reader bỏ qua item

Một reader cần được kiểm thử với nguồn có thể xác định số item và thứ tự. Các trường hợp nên bao gồm:

| Dữ liệu nguồn | Hành vi mong đợi |
|---|---|
| Nguồn có nhiều item hợp lệ | Trả từng item đúng một lần, sau đó null |
| Nguồn rỗng | Trả null ngay lần đọc đầu |
| Dòng trống ở giữa file | Xử lý theo quy tắc đã định nghĩa, không kết thúc sớm |
| Dòng sai định dạng | Ném exception hoặc được skip theo policy |
| File không tồn tại | Báo lỗi nếu file là bắt buộc |
| File chỉ có header | Kết thúc bình thường với 0 item nếu đó là input hợp lệ |
| Reader có nhiều delegate | Chỉ trả null khi tất cả nguồn đã hết |
| Writer thất bại giữa chunk | Item chưa commit được xử lý lại đúng theo cơ chế restart |
| Job restart | Reader khôi phục đúng vị trí checkpoint |

Ví dụ kiểm thử reader đơn giản:

~~~java
@Test
void returnsEveryItemBeforeEndOfInput() throws Exception {
    ListItemReader<String> reader =
        new ListItemReader<>(List.of("A", "B", "C"));

    assertEquals("A", reader.read());
    assertEquals("B", reader.read());
    assertEquals("C", reader.read());
    assertNull(reader.read());
    assertNull(reader.read());
}
~~~

Kiểm thử này xác nhận reader trả đủ item và chỉ báo EOF sau item cuối. Với reader file hoặc database, nên dùng nguồn test có số lượng và thứ tự xác định để đối chiếu kết quả.

### Kiểm thử dòng lỗi không làm kết thúc sớm

Một bài kiểm thử tích hợp nên có file chứa một dòng lỗi ở giữa các dòng hợp lệ:

~~~text
customer_id,full_name,email
C001,An,an@example.test
C002,Binh
C003,Chi,chi@example.test
~~~

Nếu dòng C002 sai cấu trúc, Job phải có hành vi đã định nghĩa: thất bại hoặc skip có ghi nhận. Dòng C003 phía sau không được âm thầm biến mất chỉ vì reader đã trả null khi gặp C002.

Nếu cấu hình skip cho lỗi parse, hãy xác nhận C001 và C003 được xử lý, C002 được ghi vào reject log hoặc bảng lỗi, và skip count tăng đúng.

## 14. Thiết kế reader dễ kiểm soát

Một reader dễ vận hành nên có các đặc điểm:

- Chỉ chịu trách nhiệm lấy và ánh xạ item từ nguồn.
- Chỉ trả null khi đã xác định hết nguồn.
- Không nuốt exception rồi coi lỗi là EOF.
- Không tự lọc item nghiệp vụ mà không có chính sách và thống kê.
- Dùng thứ tự ổn định khi phân trang.
- Xử lý rõ header, comment, dòng trống và định dạng sai.
- Có checkpoint nếu Job cần restart.
- Không chia sẻ trạng thái đọc không an toàn giữa các thread.
- Có số liệu nguồn để đối chiếu với readCount và các bộ đếm khác.

Khi cần loại bỏ dữ liệu, hãy xác định đó là lọc nghiệp vụ, skip lỗi hay điều kiện chọn nguồn. Mỗi cách cần được thể hiện ở đúng thành phần để Job có thể giải thích vì sao một item không xuất hiện ở đầu ra.

## 15. Quy trình xử lý khi phát hiện thiếu item

Nếu Job hoàn tất nhưng số lượng đầu ra thấp hơn dự kiến, có thể điều tra theo trình tự:

1. **Xác định số lượng nguồn:** lấy số dòng hoặc số bản ghi theo cùng điều kiện lô.
2. **Kiểm tra readCount:** xác định reader đã trả về bao nhiêu item.
3. **Kiểm tra filterCount:** xem processor đã lọc bao nhiêu item.
4. **Kiểm tra skip count:** xem lỗi đọc, xử lý hoặc ghi nào đã bị skip.
5. **Kiểm tra reader configuration:** resource, WHERE clause, header, encoding, strict mode, page size và sort key.
6. **Kiểm tra exception/log:** tìm lỗi parse hoặc lỗi nguồn bị xử lý không đúng.
7. **Kiểm tra custom reader:** tìm các nhánh trả null, vòng lặp bỏ item, iterator bị tiêu thụ nhiều lần hoặc trạng thái index sai.
8. **Kiểm tra restart:** xác nhận ExecutionContext và checkpoint khôi phục đúng.
9. **Đối soát đầu ra:** so sánh dữ liệu đã ghi với tập item đầu vào sau lọc và skip.
10. **Sửa nguyên nhân:** bổ sung kiểm tra và metrics để lần chạy sau có thể phát hiện chênh lệch sớm.

Không nên chạy lại ngay một Job có writer không idempotent trước khi xác định các chunk nào đã commit. Chạy lại sai cách có thể tạo dữ liệu trùng và làm cho việc điều tra khó hơn.

## 16. Những điểm cần nhớ

- ItemReader trả về một item ở mỗi lần đọc; null chỉ có nghĩa là nguồn đã hết.
- Một dòng trống, bản ghi lỗi hoặc nguồn tạm thời chưa có dữ liệu không tự động đồng nghĩa với EOF.
- Không bắt exception rồi trả null, vì cách này biến lỗi thành kết thúc bình thường.
- Dùng ItemProcessor trả null để lọc item theo nghiệp vụ.
- Dùng skip policy khi cần bỏ qua exception đã được phân loại và giới hạn rõ.
- Cấu hình FlatFileItemReader đúng resource, encoding, header và strict mode.
- Với paging reader, dùng sort key ổn định và phạm vi dữ liệu nhất quán.
- Custom reader phải tiêu thụ mỗi item đúng một lần và quản lý trạng thái restart.
- Reader điều phối nhiều nguồn chỉ kết thúc khi tất cả delegate đã hết.
- Đối chiếu số lượng nguồn với readCount, filterCount, skip count và writeCount.
- Kiểm thử lỗi ở giữa nguồn, EOF, restart và chạy song song để phát hiện mất item.

Giữ đúng hợp đồng của ItemReader giúp Spring Batch phân biệt rõ dữ liệu đã đọc, dữ liệu bị lọc, dữ liệu lỗi và thời điểm nguồn thực sự kết thúc. Nhờ đó, Job tránh được tình trạng hoàn tất nhưng âm thầm bỏ sót bản ghi.

