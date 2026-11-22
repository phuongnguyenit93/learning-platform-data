# ItemReader đọc một item mỗi lần

Trong Spring Batch, ItemReader là thành phần cung cấp dữ liệu đầu vào cho một Step. Hợp đồng của nó rất đơn giản: mỗi lần framework gọi read(), reader trả về tối đa một item; khi không còn dữ liệu, reader trả về null.

Reader không quyết định kích thước chunk và không cần tự gom danh sách item để chuyển cho writer. Spring Batch gọi read() nhiều lần, gom các item thành chunk theo cấu hình của Step, sau đó mới chuyển chunk qua processor và writer.

## 1. Hợp đồng của ItemReader

Interface ItemReader<T> có một phương thức chính:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Mỗi lần gọi read():

- Trả về một object T đại diện cho một item vừa đọc được.
- Trả về null khi nguồn dữ liệu đã hết.
- Có thể ném exception nếu không thể đọc item do lỗi nguồn dữ liệu hoặc lỗi chuyển đổi.

Reader trả về một item logic, không nhất thiết là một dòng vật lý. Ví dụ, một item có thể là một Customer được ánh xạ từ một dòng CSV, một Order được tạo từ nhiều cột database, hoặc một message đã được chuyển thành object nghiệp vụ.

Nếu nguồn dữ liệu có 1.000 bản ghi và không có item nào bị lọc hay bỏ qua, framework có thể gọi read() để nhận lần lượt 1.000 item, sau đó nhận null ở lần đọc xác định kết thúc nguồn.

~~~text
read() lần 1  -> Customer A
read() lần 2  -> Customer B
read() lần 3  -> Customer C
...
read() lần N  -> Customer N
read() lần N+1 -> null (hết dữ liệu)
~~~

Đây là mô hình đọc tiến về phía trước. Reader thường giữ trạng thái nội bộ như vị trí dòng hiện tại, con trỏ kết quả hoặc trang dữ liệu tiếp theo để biết lần gọi sau cần trả về item nào.

### null có ý nghĩa đặc biệt

Giá trị null là tín hiệu kết thúc dữ liệu. Framework hiểu rằng reader không còn item nào để cung cấp trong lần chạy hiện tại.

Vì vậy, không dùng null để biểu diễn một bản ghi nghiệp vụ rỗng hoặc một giá trị null hợp lệ trong nguồn. Nếu dữ liệu đầu vào có thể chứa giá trị null, hãy ánh xạ nó sang một object bao bọc hoặc một kiểu dữ liệu có thể biểu diễn rõ trạng thái đó.

Ví dụ, thay vì trả null cho một dòng trống có ý nghĩa nghiệp vụ, có thể trả về một object InputRecord với trường value rỗng và trạng thái phù hợp. Khi đó, null vẫn được dành riêng cho tín hiệu EOF (end of file/end of input).

## 2. Spring Batch gọi read() và tạo chunk như thế nào?

Với chunk-oriented Step, framework lặp việc đọc cho đến khi đạt commit interval hoặc reader báo hết dữ liệu. Sau đó, các item đã đọc được xử lý và ghi trong một chunk.

Ví dụ cấu hình chunk size bằng 3:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(3, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

Giả sử nguồn có 8 item và không có lỗi hoặc item bị lọc:

~~~text
Chunk 1:
  read() -> A
  read() -> B
  read() -> C
  process A, B, C
  write [A, B, C]
  commit

Chunk 2:
  read() -> D
  read() -> E
  read() -> F
  process D, E, F
  write [D, E, F]
  commit

Chunk 3:
  read() -> G
  read() -> H
  read() -> null
  process G, H
  write [G, H]
  commit
~~~

Chunk cuối có thể nhỏ hơn commit interval vì nguồn đã hết. Writer nhận hai item trong chunk cuối, không cần chờ đủ ba item.

Điểm quan trọng:

- Một lần gọi read() trả về một item.
- Một chunk có thể gồm nhiều item.
- Commit interval xác định số item tối đa framework gom vào chunk theo cấu hình.
- Framework điều phối thời điểm gọi reader, processor, writer và commit transaction.
- Reader không cần biết chunk hiện tại có bao nhiêu item.

Nếu processor lọc item hoặc skip policy bỏ qua item lỗi, số item writer nhận được có thể ít hơn số item reader đã cung cấp. Điều này không làm thay đổi hợp đồng đọc một item mỗi lần.

## 3. Phân biệt hết dữ liệu, filter và skip

Ba tình huống này có ý nghĩa khác nhau và cần được xử lý đúng ở đúng thành phần.

### Hết dữ liệu: reader trả null

Khi read() trả null, framework hiểu nguồn đầu vào đã kết thúc. Step có thể hoàn tất sau khi ghi chunk cuối còn lại.

~~~java
@Override
public Customer read() {
    if (!iterator.hasNext()) {
        return null;
    }

    return iterator.next();
}
~~~

### Filter: processor trả null

Khi reader trả về một item hợp lệ nhưng processor quyết định không đưa item đó xuống writer, processor trả về null.

~~~java
@Bean
ItemProcessor<Customer, Customer> activeCustomerProcessor() {
    return customer -> {
        if (!customer.isActive()) {
            return null;
        }

        return customer;
    };
}
~~~

Trong trường hợp này, reader vẫn đã đọc item. Processor chủ động lọc item và writer không nhận item đó. Framework phân biệt việc lọc này với việc reader hết dữ liệu.

### Skip: một lỗi được chính sách cho phép bỏ qua

Nếu reader hoặc processor gặp lỗi thuộc loại được cấu hình skip, Spring Batch có thể bỏ qua item lỗi và tiếp tục xử lý trong giới hạn skip đã đặt.

~~~java
return new StepBuilder("importCustomersStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .processor(customerProcessor)
        .writer(customerWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
~~~

Trong ví dụ, Step có thể bỏ qua tối đa 10 lỗi FlatFileParseException theo cấu hình skip. Nếu vượt giới hạn, Step thất bại. Chính sách thực tế cần chọn loại exception phù hợp; không nên skip lỗi khiến dữ liệu nghiệp vụ sai mà không có cơ chế ghi nhận và xử lý.

| Tình huống | Thành phần phát tín hiệu | Ý nghĩa |
|---|---|---|
| Reader trả null | ItemReader | Không còn item để đọc |
| Processor trả null | ItemProcessor | Item được lọc, không ghi |
| Reader/processor ném lỗi được skip | ItemReader hoặc ItemProcessor | Bỏ qua item lỗi theo skip policy |
| Reader ném lỗi không được xử lý | ItemReader | Step có thể thất bại hoặc retry theo cấu hình |

Không trả null khi gặp lỗi parse hoặc lỗi truy cập nguồn chỉ để Step kết thúc bình thường. Làm vậy có thể khiến framework hiểu nhầm rằng nguồn đã hết và âm thầm bỏ sót phần dữ liệu còn lại.

## 4. Viết một ItemReader tùy chỉnh đơn giản

Khi nguồn dữ liệu không có reader dựng sẵn phù hợp, có thể triển khai ItemReader<T>.

Ví dụ dưới đây đọc lần lượt các Customer từ một danh sách trong bộ nhớ:

~~~java
public class CustomerListReader implements ItemReader<Customer> {

    private final Iterator<Customer> customers;

    public CustomerListReader(List<Customer> customers) {
        this.customers = customers.iterator();
    }

    @Override
    public Customer read() {
        if (customers.hasNext()) {
            return customers.next();
        }

        return null;
    }
}
~~~

Reader này khởi tạo iterator từ danh sách, mỗi lần read() lấy một Customer và khi iterator không còn phần tử thì trả về null. Nó không tạo sẵn một chunk hoặc trả về cả danh sách.

Đây là ví dụ minh họa hợp đồng ItemReader. Nó giữ iterator trong bộ nhớ, không lưu checkpoint và không phù hợp với danh sách rất lớn hoặc yêu cầu restart sau khi ứng dụng khởi động lại. Trong ứng dụng thật, nên dùng reader có cơ chế state phù hợp với nguồn dữ liệu.

Nếu dùng reader tùy chỉnh trong Spring, hãy cân nhắc scope của bean. Một reader có trạng thái đọc thường nên được tạo cho từng StepExecution, chẳng hạn dùng @StepScope, để tránh nhiều lần chạy dùng chung iterator hoặc con trỏ.

## 5. Dùng reader có sẵn của Spring Batch

Spring Batch cung cấp nhiều reader để làm việc với các nguồn phổ biến. Chúng vẫn tuân thủ nguyên tắc mỗi lần read() trả về một item.

| Reader | Nguồn dữ liệu / cách đọc | Khi phù hợp |
|---|---|---|
| FlatFileItemReader | File văn bản như CSV hoặc fixed-width | Nhập dữ liệu từ file |
| JsonItemReader | JSON theo cấu hình token/object | Đọc file JSON |
| JdbcCursorItemReader | JDBC ResultSet theo cursor | Đọc tuần tự một truy vấn lớn |
| JdbcPagingItemReader | Đọc theo từng trang database | Khi paging phù hợp với database |
| JpaPagingItemReader | Đọc entity theo trang qua JPA | Xử lý dữ liệu JPA theo từng nhóm |
| RepositoryItemReader | Gọi Spring Data repository theo trang | Tận dụng repository có sẵn |
| StaxEventItemReader | XML theo event và fragment | Đọc XML có cấu trúc |

Lựa chọn reader phụ thuộc vào kích thước dữ liệu, khả năng restart, cách sắp xếp dữ liệu, tài nguyên database và yêu cầu nhất quán của nguồn.

### Ví dụ FlatFileItemReader

Giả sử file CSV chứa mỗi khách hàng trên một dòng. FlatFileItemReader có thể đọc từng dòng và ánh xạ thành một String hoặc object.

Ví dụ đơn giản trả về từng dòng thô:

~~~java
@Bean
@StepScope
FlatFileItemReader<String> customerLineReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<String>()
            .name("customerLineReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper((line, lineNumber) -> line)
            .saveState(true)
            .build();
}
~~~

Spring Batch gọi read() để lấy dòng tiếp theo. Reader quản lý việc mở file, đọc từng dòng, phát hiện EOF và đóng resource theo vòng đời Step.

Nếu cần ánh xạ CSV thành Customer, có thể cấu hình tokenizer và FieldSetMapper hoặc một LineMapper phù hợp. Khi đó, mỗi lần read() trả về một Customer thay vì String.

### Ví dụ JDBC cursor reader

JdbcCursorItemReader phù hợp với cách đọc tuần tự qua ResultSet:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerCursorReader")
            .dataSource(dataSource)
            .sql("select id, name, email from customer order by id")
            .rowMapper((rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getString("email")))
            .saveState(true)
            .build();
}
~~~

Reader mở cursor và mỗi lần read() ánh xạ hàng tiếp theo thành một Customer. Khi không còn hàng, nó trả null. Dùng ORDER BY với khóa ổn định giúp thứ tự dữ liệu rõ ràng.

Cursor có thể giữ kết nối và tài nguyên database trong thời gian Step chạy. Cần cân nhắc timeout, giới hạn cursor, transaction và khả năng database hỗ trợ cursor trong môi trường triển khai.

### Paging reader

JdbcPagingItemReader và các reader paging khác truy vấn dữ liệu theo từng trang. Framework vẫn nhìn thấy từng item một qua read(), mặc dù reader có thể lấy một trang nhiều hàng từ database rồi lần lượt trả từng hàng trong trang đó.

Với paging, cần có sort key ổn định và duy nhất hoặc một thứ tự đủ xác định. Nếu thứ tự không ổn định, bản ghi có thể bị lặp hoặc bỏ sót giữa các trang, nhất là khi dữ liệu nguồn thay đổi trong lúc job đang chạy.

Paging có thể phù hợp khi không muốn giữ một cursor database mở trong toàn bộ Step, nhưng số truy vấn và hiệu năng phụ thuộc vào kích thước page, index, truy vấn và mức thay đổi dữ liệu.

## 6. Vòng đời tài nguyên với ItemStream

Nhiều reader làm việc với tài nguyên cần mở và đóng như file, cursor hoặc kết nối. Spring Batch hỗ trợ vòng đời này qua interface ItemStream.

ItemStream có ba callback chính:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Một reader cần quản lý trạng thái có thể triển khai ItemStreamReader<T>, kết hợp ItemReader<T> và ItemStream.

- **open:** mở tài nguyên và khôi phục trạng thái từ ExecutionContext nếu đây là lần restart.
- **update:** ghi trạng thái hiện tại vào ExecutionContext khi framework chuẩn bị lưu checkpoint.
- **close:** đóng resource và giải phóng tài nguyên khi Step kết thúc.

Các reader dựng sẵn như FlatFileItemReader và JdbcCursorItemReader đã tích hợp cơ chế quản lý resource và state. Khi dùng chúng, hãy đặt tên reader ổn định và bật saveState nếu cần restart.

Nếu bọc một reader ItemStream bên trong một delegate hoặc composite reader, cần bảo đảm delegate được đăng ký để callback open, update và close được gọi. Việc một object nằm bên trong reader khác không phải lúc nào cũng tự động làm cho lifecycle của nó được quản lý.

### saveState

Với builder của nhiều reader dựng sẵn, saveState(true) bật lưu trạng thái phục vụ restart. Nếu tắt saveState hoặc dùng reader không hỗ trợ ItemStream, framework có thể không khôi phục được vị trí đọc sau khi Step thất bại.

Không phải mọi reader đều cần lưu trạng thái. Ví dụ, một reader đọc dữ liệu bất biến từ đầu mỗi lần và được thiết kế để xử lý lại an toàn có thể không cần checkpoint. Nhưng cần quyết định điều này có chủ đích vì nó ảnh hưởng thời gian chạy lại và khả năng tránh trùng dữ liệu.

## 7. Reader và checkpoint khi restart

Một reader restartable phải lưu đủ trạng thái để biết item tiếp theo cần cung cấp sau khi Job được restart.

Với file, trạng thái có thể bao gồm vị trí đọc hoặc số dòng. Với database paging, trạng thái có thể bao gồm page và vị trí trong page hoặc thông tin cần thiết để tiếp tục truy vấn. Chi tiết phụ thuộc implementation của reader.

Ví dụ luồng restart:

~~~text
Lần chạy đầu:
  read item 1 ... 100
  write chunk 1
  commit checkpoint tại item 100

  read item 101 ... 200
  writer gặp lỗi
  rollback chunk 2
  Step FAILED

Restart cùng JobInstance:
  reader mở lại từ checkpoint đã commit
  tiếp tục xử lý từ vị trí phù hợp
~~~

Checkpoint được lưu trong Step ExecutionContext và metadata của JobRepository. Khi restart cùng JobInstance, Spring Batch sử dụng trạng thái đã lưu nếu reader hỗ trợ restart.

Cần giữ nguyên dữ liệu nguồn hoặc bảo đảm nó có định danh phiên bản rõ ràng. Nếu file bị thay thế, dòng bị chèn hoặc database thay đổi thứ tự giữa hai lần chạy, vị trí checkpoint cũ có thể không còn tương ứng với cùng bản ghi.

Với dữ liệu thay đổi thường xuyên, hãy cân nhắc snapshot, staging table, watermark hoặc khóa phân trang ổn định. Ví dụ, có thể giới hạn truy vấn theo một mốc ID tối đa được chụp tại thời điểm bắt đầu Job để những bản ghi mới thêm vào không làm thay đổi phạm vi xử lý giữa các lần restart.

## 8. Reader không nên quản lý chunk hoặc ghi dữ liệu

Trách nhiệm của ItemReader là lấy item tiếp theo từ nguồn dữ liệu. Reader không nên tự gọi ItemWriter, tự commit transaction hoặc tự quyết định khi nào kết thúc chunk.

Các trách nhiệm được phân tách:

~~~text
ItemReader
  |
  | một item mỗi lần read()
  v
ItemProcessor (tùy chọn)
  |
  | biến đổi hoặc filter
  v
Chunk
  |
  | đạt commit interval hoặc EOF
  v
ItemWriter
  |
  v
Commit transaction
~~~

Sự phân tách này cho phép thay reader mà không phải thay đổi logic ghi, hoặc thay writer mà không thay đổi cách đọc.

Ví dụ, cùng một ItemProcessor và ItemWriter có thể được tái sử dụng cho dữ liệu đến từ file, database hoặc API, miễn là các reader trả về cùng kiểu item và đáp ứng cùng quy tắc nghiệp vụ.

Reader cũng không nên giữ toàn bộ dữ liệu nguồn trong bộ nhớ nếu nguồn rất lớn. Đọc tuần tự hoặc paging giúp giới hạn bộ nhớ. Nếu một item là aggregate lớn, hãy cân nhắc kích thước object và cách nạp dữ liệu liên quan.

## 9. Xử lý lỗi trong read()

read() có thể thất bại vì nhiều nguyên nhân:

- File không tồn tại hoặc không thể đọc.
- Dòng CSV sai định dạng.
- Database mất kết nối hoặc truy vấn thất bại.
- API timeout hoặc trả về response không hợp lệ.
- Dữ liệu nguồn vi phạm quy tắc chuyển đổi.

Không nên biến mọi lỗi thành null. Trả null có nghĩa hết dữ liệu, nên nếu reader gặp lỗi giữa file và trả null, Step có thể kết thúc thành công dù phần dữ liệu phía sau chưa được xử lý.

Hãy để exception truyền ra và cấu hình retry/skip phù hợp khi cần. Ví dụ, lỗi kết nối tạm thời có thể phù hợp với retry; một số lỗi parse có thể được skip nếu nghiệp vụ cho phép và có ghi nhận dữ liệu lỗi. Lỗi cấu hình như file không tồn tại thường nên làm Step thất bại để người vận hành xử lý.

Khi cần chẩn đoán, log vị trí hoặc số dòng, mã bản ghi và loại lỗi không nhạy cảm. Tránh log toàn bộ nội dung bản ghi nếu có dữ liệu cá nhân, token hoặc thông tin bảo mật.

## 10. Thread safety và nhiều reader execution

Một ItemReader có trạng thái nội bộ như iterator, con trỏ hoặc page index. Nếu nhiều thread gọi cùng một instance đồng thời, các lần đọc có thể tranh chấp trạng thái và dẫn đến item bị lặp hoặc bị bỏ qua.

Khi dùng multi-threaded Step hoặc partitioning:

- Xác định reader instance được chia sẻ hay tạo riêng cho từng thread/partition.
- Chọn reader có hỗ trợ concurrency phù hợp.
- Nếu cần, dùng reader được đồng bộ hóa hoặc phân chia nguồn thành các phạm vi độc lập.
- Không chia sẻ một iterator mutable cho nhiều StepExecution.
- Lưu checkpoint riêng cho từng partition khi mô hình partition yêu cầu.

@StepScope giúp tạo bean theo phạm vi StepExecution, hữu ích khi reader nhận JobParameters hoặc cần trạng thái riêng. Tuy nhiên, Step scope không tự làm cho một reader thread-safe nếu cùng instance vẫn được nhiều thread trong cùng Step gọi đồng thời.

Với partitioning, thường nên để mỗi partition có phạm vi dữ liệu riêng, ví dụ ID từ A đến B, và mỗi partition có reader/state riêng. Cách phân vùng cần bảo đảm các phạm vi không chồng lấn và bao phủ đầy đủ dữ liệu mục tiêu.

## 11. Kiểm thử ItemReader

Reader nên được kiểm thử độc lập để xác nhận hợp đồng đọc từng item và hành vi khi kết thúc nguồn.

Với một reader đơn giản, có thể kiểm tra:

~~~java
@Test
void readReturnsOneItemAtATimeThenNull() throws Exception {
    Customer first = new Customer(1L, "An", "an@example.test");
    Customer second = new Customer(2L, "Binh", "binh@example.test");

    ItemReader<Customer> reader =
            new CustomerListReader(List.of(first, second));

    assertEquals(first, reader.read());
    assertEquals(second, reader.read());
    assertNull(reader.read());
    assertNull(reader.read());
}
~~~

Test này xác nhận mỗi lần read() trả một item, sau đó trả null khi iterator đã hết. Nó không kiểm tra restart vì reader trong ví dụ chỉ dùng iterator trong bộ nhớ.

Với reader có ItemStream, cần kiểm tra thêm:

- open với ExecutionContext rỗng bắt đầu từ đầu.
- update ghi trạng thái cần thiết.
- open với ExecutionContext đã lưu khôi phục vị trí đọc.
- close giải phóng resource.
- Sau khi Step restart, không bỏ sót hoặc đọc trùng dữ liệu đã commit.
- Lỗi nguồn dữ liệu được truyền ra theo loại exception mong muốn.

Với FlatFileItemReader, nên kiểm tra file có header, dòng trống, ký tự đặc biệt, encoding, lỗi parse và trường hợp file rỗng. Với JDBC reader, cần kiểm tra thứ tự kết quả, paging/cursor, kết nối và dữ liệu thay đổi trong lúc chạy.

## 12. Những lỗi thường gặp khi triển khai ItemReader

**Trả null khi gặp lỗi.** Framework hiểu đây là EOF và có thể kết thúc Step sớm. Hãy ném exception phù hợp.

**Tự trả về cả danh sách.** ItemReader có hợp đồng một item mỗi lần. Hãy để framework gom chunk.

**Nhầm filter với EOF.** Nếu muốn bỏ một item nhưng tiếp tục đọc các item sau, dùng ItemProcessor trả null hoặc skip policy phù hợp, không trả null từ reader.

**Dùng reader stateful dạng singleton cho nhiều lần chạy.** Iterator hoặc con trỏ có thể đã ở cuối khi Job khác bắt đầu. Dùng scope phù hợp hoặc tạo instance mới cho mỗi StepExecution.

**Không lưu trạng thái khi cần restart.** Nếu reader không hỗ trợ ItemStream hoặc saveState bị tắt, Step có thể phải đọc lại từ đầu hoặc không thể tiếp tục như mong muốn.

**Nguồn dữ liệu không có thứ tự ổn định.** Paging hoặc checkpoint dựa trên vị trí có thể lặp hoặc bỏ sót item nếu thứ tự thay đổi. Dùng sort key ổn định và phạm vi dữ liệu được xác định rõ.

**Không đóng resource.** Cursor hoặc file có thể giữ tài nguyên sau khi Step kết thúc nếu lifecycle không được quản lý đúng. Ưu tiên reader dựng sẵn hoặc triển khai đầy đủ ItemStream.

## 13. Cách chọn và cấu hình reader

Khi bắt đầu một Step, hãy xác định rõ:

1. Một item nghiệp vụ là gì: dòng file, hàng database, message hay object tổng hợp?
2. Nguồn dữ liệu có thể đọc tuần tự, theo cursor hay theo page?
3. Kích thước dữ liệu và giới hạn bộ nhớ ra sao?
4. Có cần restart từ checkpoint không?
5. Dữ liệu nguồn có thể thay đổi trong lúc chạy hoặc giữa các lần restart không?
6. Reader có cần chạy đồng thời ở nhiều thread hoặc partition không?
7. Loại lỗi nào có thể retry, loại nào được phép skip và loại nào phải làm Step thất bại?
8. Ai chịu trách nhiệm mở/đóng tài nguyên và lưu trạng thái?

Với file văn bản ổn định, FlatFileItemReader thường là lựa chọn tự nhiên. Với truy vấn database lớn, chọn cursor hoặc paging dựa trên đặc tính database và yêu cầu vận hành. Với API hoặc nguồn tùy chỉnh, triển khai ItemReader riêng và bổ sung ItemStream nếu cần lưu trạng thái.

Dù chọn implementation nào, nguyên tắc không thay đổi: mỗi lần read() cung cấp một item; null đánh dấu hết dữ liệu; Spring Batch điều phối việc gom item thành chunk, xử lý, ghi và commit. Khi reader thực hiện đúng hợp đồng đó và quản lý state/resource phù hợp, Step có thể xử lý dữ liệu tuần tự, theo dõi tiến độ và phục hồi đáng tin cậy khi cần restart.

