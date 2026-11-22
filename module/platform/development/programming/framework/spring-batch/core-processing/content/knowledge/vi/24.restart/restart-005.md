# Restart với reader state

Trong Spring Batch, restart cho phép một Job tiếp tục sau khi lần chạy trước bị dừng hoặc thất bại. Để tiếp tục đúng vị trí, reader cần lưu và khôi phục trạng thái đọc. Trạng thái này thường được lưu trong **Step ExecutionContext** thông qua hợp đồng **ItemStream**.

Một reader có khả năng restart không chỉ biết cách lấy item tiếp theo. Nó còn phải biết cách lưu vị trí hiện tại trước khi chunk được commit và khôi phục vị trí đó khi Step chạy lại.

Ví dụ Job đọc file 100.000 dòng với chunk size 500. Nếu Job thất bại sau khi 20 chunk đã commit, lần restart nên tiếp tục từ checkpoint của chunk đã commit gần nhất. Reader không nên đọc lại toàn bộ file từ đầu và cũng không được bỏ qua các dòng chưa commit.

Để làm được điều đó, cần phối hợp đúng ba phần:

- Reader quản lý vị trí đọc và triển khai ItemStream.
- Spring Batch gọi open, update và close theo lifecycle của Step.
- JobRepository lưu ExecutionContext để lần restart có thể khôi phục checkpoint.

## 1. Reader state là gì?

Reader state là thông tin cần thiết để xác định item tiếp theo sẽ được đọc. Tùy nguồn dữ liệu, trạng thái có thể là:

- Số dòng đã đọc trong file.
- Vị trí byte hoặc record offset trong một resource.
- Trang hiện tại và số item đã đọc trong trang.
- ID cuối cùng đã xử lý trong database.
- Cursor position hoặc một khóa tiếp tục.
- Tên partition và phạm vi dữ liệu đang xử lý.

Ví dụ reader file đã đọc tới dòng 2.000:

~~~text
File: customers.csv

Dòng 1 - 2.000  -> đã thuộc các chunk đã commit
Dòng 2.001      -> item tiếp theo khi restart
Dòng 2.002 ...
~~~

Nếu checkpoint đã commit lưu vị trí 2.000, reader có thể mở lại file và tiếp tục từ dòng 2.001.

Reader state không phải toàn bộ dữ liệu đã đọc. Thông thường chỉ cần lưu một vị trí hoặc khóa nhỏ đủ để tái tạo item tiếp theo.

## 2. ItemStream cung cấp lifecycle cho reader

Spring Batch dùng interface ItemStream để quản lý trạng thái và tài nguyên của thành phần xử lý.

Hợp đồng cơ bản:

~~~java
public interface ItemStream {

    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

Reader có thể triển khai ItemStreamReader, kết hợp ItemReader và ItemStream:

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}
~~~

Ba phương thức có vai trò khác nhau:

| Phương thức | Vai trò |
|---|---|
| open(context) | Khởi tạo reader và khôi phục state đã lưu |
| update(context) | Ghi state hiện tại vào ExecutionContext |
| close() | Đóng resource và giải phóng tài nguyên |

Spring Batch gọi open khi Step bắt đầu, gọi update tại các checkpoint trước khi commit chunk và gọi close khi Step kết thúc. Với reader hỗ trợ restart, đây là nơi lưu và khôi phục vị trí đọc.

Không cần tự gọi ba phương thức này từ processor hoặc writer. Khi reader được đăng ký đúng với Step, Spring Batch quản lý lifecycle.

## 3. Checkpoint được lưu ở đâu?

Reader checkpoint thông thường được lưu trong **StepExecution ExecutionContext**. Đây là context riêng của một StepExecution, phù hợp cho trạng thái đọc chỉ thuộc Step đó.

Phân biệt các loại dữ liệu:

| Dữ liệu | Nơi lưu phù hợp |
|---|---|
| Đường dẫn file đầu vào | JobParameters |
| Ngày nghiệp vụ hoặc mã lần nhập | JobParameters |
| Dòng cuối cùng đã đọc/commit | Step ExecutionContext |
| ID cuối cùng của reader database | Step ExecutionContext |
| Kết quả trung gian cần Step sau dùng | Job ExecutionContext |
| Toàn bộ nội dung file | File hoặc storage, không lưu vào context |

JobParameters xác định yêu cầu chạy và các identifying parameter quyết định JobInstance. ExecutionContext lưu trạng thái thay đổi trong quá trình chạy. Reader state là checkpoint thực thi, vì vậy thường thuộc Step context.

ExecutionContext được lưu trong JobRepository. Muốn restart sau khi ứng dụng hoặc JVM khởi động lại, JobRepository phải lưu metadata bền vững, thường là database-backed repository. Repository chỉ tồn tại trong bộ nhớ không thể bảo đảm giữ checkpoint qua process restart.

## 4. Vòng đời checkpoint của một chunk

Với chunk-oriented Step, reader state được cập nhật theo ranh giới commit.

~~~text
Step bắt đầu
    |
    v
reader.open(savedContext)
    |
    v
Đọc và xử lý chunk
    |
    v
reader.update(executionContext)
    |
    v
Lưu ExecutionContext và metadata
    |
    v
Transaction commit
    |
    v
Chunk đã xác nhận
    |
    v
Chunk tiếp theo
~~~

Giả sử chunk size bằng 500:

| Chunk | Item | Trạng thái |
|---|---|---|
| 1 | 1–500 | Commit |
| 2 | 501–1.000 | Commit |
| 3 | 1.001–1.500 | Commit |
| 4 | 1.501–2.000 | Commit |
| 5 | 2.001–2.500 | Đang xử lý thì lỗi |

Nếu Job thất bại trong chunk 5 trước khi commit, checkpoint đã lưu gần nhất vẫn tương ứng với chunk 4. Khi restart, reader khôi phục vị trí sau item 2.000 và đọc lại phần chunk chưa commit.

Điểm cốt lõi là checkpoint chỉ đại diện cho tiến độ đã được lưu thành công. Việc reader đã gọi read() hoặc writer đã được gọi không đồng nghĩa checkpoint mới đã commit.

Tính atomic giữa dữ liệu nghiệp vụ và metadata phụ thuộc cách cấu hình transaction manager, JobRepository và tài nguyên. Với các tài nguyên độc lập, không nên mặc định một commit bao trùm tất cả.

## 5. Job restart sử dụng JobInstance cũ

Restart thông thường tiếp tục cùng một JobInstance. Spring Batch xác định JobInstance bằng tên Job và các identifying JobParameters.

~~~text
JobParameters
  inputFile=customers.csv
  businessDate=2026-11-15
        |
        v
JobInstance: customerImportJob
        |
        +--> JobExecution 1: FAILED
        |       |
        |       +--> StepExecution
        |               checkpoint: line 2000
        |
        +--> JobExecution 2: RESTART
                |
                +--> Cùng JobInstance
                |
                +--> Reader mở với checkpoint line 2000
                        |
                        v
                  Đọc từ line 2001
~~~

Khi restart:

1. JobLauncher nhận lại JobParameters của JobInstance cần tiếp tục.
2. JobRepository tìm JobInstance tương ứng.
3. Spring Batch tạo JobExecution mới cho lần chạy tiếp theo.
4. Step được restart dùng metadata và ExecutionContext đã lưu.
5. Reader mở lại với checkpoint đã commit gần nhất.

Nếu thay identifying parameter, ví dụ đổi inputFile sang file khác, yêu cầu có thể tạo JobInstance mới và không dùng checkpoint của instance cũ.

Nếu chỉ thay non-identifying parameter, danh tính JobInstance có thể không đổi. Tuy nhiên, các tham số không identifying vẫn cần ổn định nếu chúng làm thay đổi cách đọc hoặc xử lý dữ liệu.

## 6. Bật saveState cho reader dựng sẵn

Các reader chuẩn của Spring Batch thường hỗ trợ lưu trạng thái. Hãy đặt tên reader ổn định và bật saveState khi cần restart.

Ví dụ FlatFileItemReader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(inputFile)
            .linesToSkip(1)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

Các điểm quan trọng:

- name("customerReader") cung cấp tên ổn định cho reader và state key.
- resource lấy file từ JobParameters.
- saveState(true) yêu cầu reader lưu trạng thái đọc.
- StepScope cho phép resolve resource khi Step thực sự bắt đầu.
- Reader được đăng ký với Step để Spring Batch quản lý ItemStream lifecycle.

Không đổi tên reader tùy tiện khi còn JobInstance cũ cần restart. Tên reader được dùng để phân biệt state trong ExecutionContext; thay đổi tên có thể khiến reader không tìm được key cũ và bắt đầu từ vị trí mặc định.

## 7. saveState(false) có ý nghĩa gì?

Một số reader cho phép tắt lưu trạng thái:

~~~java
.saveState(false)
~~~

Khi saveState(false), reader không lưu checkpoint để khôi phục vị trí đọc. Điều đó có thể phù hợp khi:

- Reader không có state cần khôi phục.
- Step được thiết kế chạy lại từ đầu.
- Nguồn dữ liệu có thể được đọc lại và xử lý idempotent.
- Thành phần chạy song song không hỗ trợ chia sẻ state của reader.
- Ứng dụng tự quản lý checkpoint ở một cơ chế khác.

Nếu reader không lưu state mà Job restart, reader có thể bắt đầu lại từ đầu. Điều đó có thể làm dữ liệu đã commit bị đọc lại. Writer cần chống ghi trùng hoặc ứng dụng phải có cơ chế xác định phần dữ liệu đã xử lý.

Không nên tắt saveState chỉ để tránh lỗi khi chạy song song mà không đánh giá tác động restart. Tắt state là một quyết định về semantics của Job, không chỉ là tối ưu hiệu năng.

## 8. Tên reader phải ổn định và duy nhất trong Step

Reader dựng sẵn thường dùng tên để tạo key trong ExecutionContext. Vì vậy:

- Đặt tên rõ ràng và ổn định.
- Không dùng cùng tên cho nhiều reader có state khác nhau trong cùng phạm vi.
- Không tạo tên ngẫu nhiên mỗi lần khởi chạy.
- Khi đổi tên bean hoặc reader, đánh giá khả năng tương thích với JobInstance đang chờ restart.

Ví dụ:

~~~java
.name("customerFileReader")
~~~

Tên này giúp phân biệt state của reader file. Nếu Step có thêm reader phụ hoặc delegate reader khác cũng lưu state, mỗi thành phần cần key riêng để không ghi đè checkpoint của nhau.

Đổi tên reader có thể làm reader không tìm thấy state cũ. Trong tình huống đó, reader có thể đọc từ đầu hoặc khởi tạo state mới tùy implementation. Hãy quản lý thay đổi cấu hình và tên reader như một thay đổi có ảnh hưởng đến khả năng restart.

## 9. Ví dụ custom reader lưu checkpoint bằng ID

Reader tùy chỉnh cần triển khai ItemStreamReader và tự định nghĩa cách lưu/khôi phục state.

Ví dụ reader đọc lần lượt khách hàng theo ID tăng dần:

~~~java
public class CustomerReader
        implements ItemStreamReader<Customer> {

    private static final String LAST_ID_KEY =
            "customerReader.lastId";

    private final CustomerRepository repository;

    private long lastId;
    private boolean opened;

    public CustomerReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public void open(ExecutionContext context) {
        lastId = context.getLong(
                LAST_ID_KEY,
                Long.MIN_VALUE);
        opened = true;
    }

    @Override
    public Customer read() {
        if (!opened) {
            throw new IllegalStateException(
                    "Reader has not been opened");
        }

        Customer customer =
                repository.findFirstAfterId(lastId);

        if (customer == null) {
            return null;
        }

        lastId = customer.getId();
        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID_KEY, lastId);
    }

    @Override
    public void close() {
        opened = false;
    }
}
~~~

Repository cần truy vấn theo thứ tự ổn định, ví dụ:

~~~sql
SELECT id, name, email
FROM customer
WHERE id > :lastId
ORDER BY id
FETCH FIRST 1 ROW ONLY
~~~

Cú pháp giới hạn số dòng thay đổi theo database. Ý tưởng là mỗi lần đọc, reader lấy bản ghi đầu tiên có ID lớn hơn lastId.

Với ví dụ này, ID cần có thứ tự ổn định và đủ duy nhất để làm checkpoint. Nếu ID có thể âm, giá trị mặc định Long.MIN_VALUE chỉ phù hợp khi mọi ID hợp lệ lớn hơn giá trị đó. Nếu dùng khóa khác, hãy thiết kế sentinel hoặc trạng thái khởi tạo riêng.

Trong ứng dụng thực tế, truy vấn một item mỗi lần có thể không hiệu quả. Có thể dùng cursor hoặc paging reader có sẵn, hoặc custom reader đọc theo batch nhưng vẫn lưu checkpoint chính xác.

## 10. Reader phải cập nhật state đúng thời điểm

Custom reader thường cập nhật field nội bộ mỗi khi trả về item. Phương thức update ghi vị trí hiện tại vào ExecutionContext.

Điều quan trọng là vị trí được lưu phải thể hiện đúng item tiếp theo sau checkpoint đã commit.

Ví dụ reader đọc ID 100, 101, 102 trong một chunk:

~~~text
read() -> 100
read() -> 101
read() -> 102
        |
        v
update(context)
        |
        v
context["lastId"] = 102
        |
        v
Commit chunk
~~~

Nếu transaction commit thành công, checkpoint 102 được lưu. Khi restart, reader tiếp tục với ID lớn hơn 102.

Nếu chunk rollback trước khi checkpoint được lưu, JobRepository vẫn giữ checkpoint của chunk commit trước. Reader cần khôi phục từ context đó khi Step được restart.

Không lưu checkpoint ngay sau mỗi lần read vào một kho độc lập nếu writer và checkpoint không có tính nhất quán cần thiết. Nếu reader tiến lên nhưng dữ liệu đầu ra chưa commit, restart có thể bỏ qua item chưa được ghi.

## 11. FlatFileItemReader khôi phục vị trí file

FlatFileItemReader là reader chuẩn cho file text. Khi bật saveState, reader có thể lưu vị trí đọc để tiếp tục khi restart.

Ví dụ:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderFileReader(
        @Value("#{jobParameters['inputFile']}") Resource resource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(resource)
            .linesToSkip(1)
            .delimited()
            .names("id", "orderNumber", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Khi chạy lần đầu, reader mở file và đọc theo thứ tự. Tại checkpoint, reader lưu trạng thái cần thiết. Khi restart cùng JobInstance và cùng nguồn file, reader có thể khôi phục vị trí tương ứng.

Điều kiện quan trọng là nguồn phải giữ nguyên nội dung và thứ tự. Nếu file bị thay thế hoặc chỉnh sửa trong lúc Job chờ restart, vị trí dòng cũ có thể trỏ tới bản ghi khác.

Ví dụ file cũ có 10.000 dòng nhưng file mới được ghi đè với nội dung khác. Checkpoint dòng 5.000 không còn đảm bảo reader tiếp tục đúng bản ghi nghiệp vụ đã xử lý trước đó.

## 12. Đảm bảo input file không thay đổi giữa restart

Chỉ lưu đường dẫn file là chưa đủ để xác định nội dung nguồn. Một file cùng tên có thể bị thay thế.

Các cách quản lý nguồn:

- Đưa file vào thư mục archive bất biến theo batch ID.
- Dùng tên file duy nhất theo ngày hoặc mã import.
- Lưu checksum hoặc version của file.
- Lưu kích thước, thời gian tạo và fingerprint để xác minh nguồn.
- Không cho hệ thống khác ghi đè file trong khi Job đang chạy hoặc chờ restart.

Có thể truyền checksum như một identifying JobParameter nếu checksum xác định một đơn vị đầu vào độc lập:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", archivedPath, true)
        .addString("fileChecksum", checksum, true)
        .toJobParameters();
~~~

Nếu file thay đổi nhưng Job vẫn dùng cùng identifying parameters, Spring Batch có thể xem đó là cùng JobInstance. Reader sẽ khôi phục vị trí cũ trên nội dung mới và kết quả có thể sai.

Nên xác minh fingerprint của nguồn khi Step mở lại. Nếu fingerprint khác, fail rõ ràng và yêu cầu tạo JobInstance mới hoặc khôi phục đúng file gốc.

## 13. JdbcPagingItemReader và checkpoint theo trang

JdbcPagingItemReader đọc dữ liệu theo từng trang thay vì tải toàn bộ kết quả vào bộ nhớ.

Ví dụ cấu hình khái niệm:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Customer> customerPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider) {

    return new JdbcPagingItemReaderBuilder<Customer>()
            .name("customerPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .saveState(true)
            .build();
}
~~~

Reader cần một thứ tự ổn định. Sort key nên là khóa duy nhất hoặc tập khóa tạo ra thứ tự duy nhất. Nếu sort key không duy nhất, bản ghi có cùng giá trị có thể bị lặp hoặc bỏ sót khi reader chuyển trang và restart.

Page size và chunk size là hai cấu hình khác nhau:

| Cấu hình | Điều khiển |
|---|---|
| pageSize | Số item reader lấy trong một lần truy vấn trang |
| chunk size | Số item trong đơn vị transaction của Step |
| saveState | Có lưu checkpoint reader hay không |

Có thể dùng page size bằng hoặc khác chunk size. Hãy đo memory, số lần query và hiệu năng database. Dù page size là bao nhiêu, reader vẫn cần lưu đủ state để khôi phục đúng vị trí sau restart.

## 14. JdbcCursorItemReader và restart

JdbcCursorItemReader đọc kết quả qua cursor. Khi bật saveState, reader có thể lưu vị trí đọc để mở lại và tiếp tục sau checkpoint.

Ví dụ:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Customer> customerCursorReader(
        DataSource dataSource) {

    return new JdbcCursorItemReaderBuilder<Customer>()
            .name("customerCursorReader")
            .dataSource(dataSource)
            .sql("""
                SELECT id, name, email
                FROM customer
                ORDER BY id
                """)
            .rowMapper(customerRowMapper())
            .saveState(true)
            .build();
}
~~~

Khi restart, cursor thường phải được mở lại; connection và ResultSet cũ không thể được lưu như object sống qua process restart. Reader sử dụng checkpoint để định vị lại vị trí trong kết quả truy vấn.

Cần chú ý:

- Query phải có ORDER BY ổn định.
- Dataset cần có tính nhất quán phù hợp giữa lần chạy và restart.
- Driver/database có thể có hành vi fetch và cursor khác nhau.
- Cursor và connection có thể được giữ trong thời gian Step chạy.
- Với dữ liệu thay đổi, vị trí dòng trong result set có thể không còn tương ứng cùng bản ghi.

Nếu dữ liệu nguồn có thể thay đổi, keyset paging dựa trên khóa duy nhất hoặc snapshot/watermark có thể dễ kiểm soát hơn việc chỉ dựa vào vị trí dòng.

## 15. Dữ liệu database thay đổi trong lúc Job dừng

Giả sử reader đã commit đến ID 5.000. Job bị dừng. Trước khi restart, một hệ thống khác:

- Xóa bản ghi ID 4.500.
- Chèn bản ghi ID 4.800.
- Thay đổi thứ tự hoặc giá trị dùng trong truy vấn.
- Cập nhật trạng thái làm bản ghi không còn thỏa điều kiện WHERE.

Checkpoint chỉ cho biết vị trí reader đã lưu. Nó không tự tạo snapshot của toàn bộ bảng.

Để restart nhất quán, hãy xác định tập dữ liệu của Job:

- Chụp upper bound hoặc watermark lúc bắt đầu.
- Lọc theo ngày/kỳ nghiệp vụ bất biến.
- Dùng snapshot isolation nếu yêu cầu đọc nhất quán và database hỗ trợ.
- Dùng bảng staging hoặc snapshot ID.
- Dùng khóa sắp xếp duy nhất và điều kiện tiếp tục ổn định.

Ví dụ reader có thể dùng điều kiện ID lớn hơn lastId và không vượt quá maxId đã chốt:

~~~sql
SELECT id, status
FROM orders
WHERE id > :lastId
  AND id <= :upperBound
ORDER BY id
~~~

upperBound nên được giữ ổn định qua restart, ví dụ trong JobParameters hoặc Job ExecutionContext tùy ý nghĩa của nó. Không tự tính lại upperBound theo dữ liệu mới nếu muốn tiếp tục cùng một tập dữ liệu.

## 16. Reader state phải được đăng ký với Step

Spring Batch cần biết reader là ItemStream để gọi open, update và close.

Khi reader được truyền trực tiếp vào builder qua reader(...), các thành phần ItemStream thường được Step đăng ký tự động. Với delegate hoặc stream lồng bên trong custom composite, cần bảo đảm delegate cũng được đăng ký.

Ví dụ về mặt cấu hình:

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemProcessor<Customer, Customer> processor,
        ItemWriter<Customer> writer,
        ItemStream auditStream) {

    return new StepBuilder("importStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .stream(auditStream)
            .build();
}
~~~

Nếu một custom delegate triển khai ItemStream nhưng không được đăng ký, Spring Batch có thể không gọi lifecycle của nó. Khi đó checkpoint không được cập nhật hoặc resource không được mở/đóng đúng cách.

Với composite reader/writer, hãy xem implementation có tự quản lý delegate stream hay cần đăng ký từng stream riêng. Tránh đăng ký trùng cùng một stream nếu framework hoặc wrapper đã quản lý nó.

## 17. Reader state và StepScope

Trong partitioning, mỗi worker có StepExecution và ExecutionContext riêng. Reader cần nhận checkpoint và partition parameters của worker tương ứng.

Ví dụ:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    return buildOrderReader(dataSource, fromId, toId);
}
~~~

StepScope tạo reader trong phạm vi StepExecution, nhờ đó mỗi partition có state riêng. Reader không nên là singleton mutable dùng chung giữa nhiều worker nếu state của nó thay đổi theo từng item.

Khi restart partition:

- Partition name và phạm vi dữ liệu cần ổn định.
- Worker dùng lại StepExecution context tương ứng.
- Reader mở lại với checkpoint của partition đó.
- Partition đã hoàn thành thường được bỏ qua theo restart semantics của Step.

Không chia sẻ một reader stateful cho nhiều thread nếu reader không được thiết kế thread-safe. Nếu cần xử lý song song, hãy dùng partitioning với reader riêng cho mỗi worker hoặc cơ chế reader được thiết kế rõ cho concurrency.

## 18. Reader không có state và cách restart từ đầu

Không phải reader nào cũng cần checkpoint. Một reader đọc danh sách cấu hình nhỏ, nguồn bất biến hoặc dữ liệu có thể tái tạo có thể được thiết kế chạy lại từ đầu.

Tuy nhiên, restart từ đầu có thể đọc lại những item đã được ghi ở các chunk commit trước. Nếu writer không idempotent, dữ liệu trùng có thể xuất hiện.

Các lựa chọn:

- Bật saveState và khôi phục checkpoint.
- Dùng writer upsert theo business key.
- Ghi trạng thái xử lý riêng trong database.
- Chia dữ liệu theo partition hoặc watermark ổn định.
- Thiết kế Step chạy lại toàn bộ một cách idempotent.

Đừng nhầm “reader không lưu state” với “Job không thể restart”. Job vẫn có thể được khởi động lại, nhưng reader có thể bắt đầu lại từ đầu và ứng dụng phải tự bảo đảm kết quả đúng.

## 19. JobRepository phải lưu metadata bền vững

Reader state chỉ hữu ích nếu ExecutionContext được lưu và đọc lại.

Một JobRepository database-backed lưu:

- JobInstance và JobExecution.
- StepExecution.
- Job ExecutionContext.
- Step ExecutionContext.
- Các counter và trạng thái thực thi.

Nếu ứng dụng dùng repository in-memory, checkpoint có thể biến mất khi process dừng. Khi đó không thể dựa vào metadata cũ để restart qua lần khởi động mới.

Cũng cần kiểm tra cấu hình transaction giữa JobRepository và dữ liệu nghiệp vụ. Nếu checkpoint và output nằm ở hai tài nguyên transaction độc lập, có thể xảy ra tình huống một bên commit còn bên kia không. Khi đó cần idempotency, outbox hoặc cơ chế đối soát phù hợp.

## 20. Restart Step đã hoàn thành khác với restart Step thất bại

Khi restart một JobInstance:

- Step đã thất bại hoặc dừng có thể được chạy tiếp từ trạng thái đã lưu.
- Step đã hoàn thành thường được bỏ qua.
- Step được cấu hình allowStartIfComplete(true) có thể chạy lại dù đã hoàn thành, theo flow và semantics của Job.

Ví dụ:

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> reader,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<Customer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .allowStartIfComplete(false)
            .build();
}
~~~

Với allowStartIfComplete(false), Step đã hoàn thành sẽ không tự chạy lại chỉ vì Job được restart. Nếu muốn chủ động xử lý lại toàn bộ dữ liệu, hãy cân nhắc tạo JobInstance mới bằng identifying parameter phù hợp hoặc cấu hình Step chạy lại theo yêu cầu nghiệp vụ.

Không dùng allowStartIfComplete(true) chỉ để khắc phục reader checkpoint sai. Nó có thể khiến Step chạy lại và tạo tác động trùng nếu writer không idempotent.

## 21. Các lỗi thường gặp với reader state

### Reader không triển khai ItemStream

Nếu reader có state nhưng không cung cấp ItemStream lifecycle, framework không biết cách lưu và khôi phục vị trí. Hãy dùng reader chuẩn hỗ trợ restart hoặc triển khai ItemStreamReader.

### Quên bật saveState

Reader có thể đọc được trong lần chạy đầu nhưng không lưu checkpoint. Khi restart, nó có thể bắt đầu lại từ đầu.

### Reader không có tên ổn định

State key có thể không được tìm thấy sau khi đổi tên reader. Hãy giữ tên reader ổn định cho JobInstance cần restart.

### Lưu state sau khi item đã đọc nhưng trước khi output commit

Nếu checkpoint tiến lên nhưng output chưa commit, restart có thể bỏ qua item chưa được ghi. Hãy để ItemStream update và transaction của Step quản lý checkpoint đúng lifecycle.

### File bị thay thế giữa hai lần chạy

Checkpoint theo dòng cũ không còn tương ứng với nội dung file mới. Dùng file bất biến, checksum hoặc version.

### Query database không có ORDER BY ổn định

Thứ tự kết quả có thể thay đổi giữa lần chạy và restart, dẫn đến thiếu hoặc trùng item. Dùng khóa sắp xếp duy nhất và điều kiện tiếp tục rõ ràng.

### Sort key không duy nhất

Nếu paging dựa trên khóa trùng, reader có thể không xác định được ranh giới trang chính xác. Thêm tie-breaker duy nhất.

### Reader singleton dùng chung giữa nhiều partition

Các worker có thể ghi đè vị trí đọc của nhau. Dùng StepScope và state riêng cho từng worker.

### ExecutionContext chứa object lớn hoặc không serialize được

Metadata phình to hoặc không thể lưu. Chỉ lưu checkpoint nhỏ như ID, số dòng, page hoặc fingerprint.

### JobRepository không bền vững

Process restart làm mất metadata và reader state. Dùng repository lưu trữ bền vững nếu cần restart qua lần khởi động ứng dụng.

## 22. Kiểm thử reader restart

Một bài test restart có giá trị nên chạy cùng một JobInstance qua hai lần JobExecution.

Ví dụ kịch bản:

~~~text
Input: 10 item
Chunk size: 3

Lần chạy 1:
  Chunk 1: item 1-3 -> COMMIT
  Chunk 2: item 4-6 -> COMMIT
  Chunk 3: item 7-9 -> FAIL trước commit

Restart:
  Reader mở với checkpoint item 6
  Đọc lại item 7-9
  Chunk cuối: item 10 -> COMMIT

Kết quả:
  Mỗi item được ghi đúng một lần
~~~

Test cần xác nhận:

- Lần chạy đầu có trạng thái FAILED hoặc STOPPED phù hợp.
- Step ExecutionContext chứa checkpoint của chunk đã commit gần nhất.
- Lần restart dùng cùng identifying JobParameters.
- Reader bắt đầu ở item tiếp theo sau checkpoint.
- Item trong chunk chưa commit được xử lý lại.
- Item của chunk đã commit không bị ghi trùng.
- Kết quả cuối cùng chứa đủ dữ liệu mục tiêu.

Không chỉ kiểm tra readCount. Hãy kiểm tra tập business key ở bảng đích để phát hiện item bị thiếu hoặc trùng.

## 23. Ví dụ kiểm thử custom reader state

Có thể kiểm thử riêng lifecycle của custom reader:

~~~java
@Test
void restoresLastIdFromExecutionContext() throws Exception {
    CustomerRepository repository = mock(CustomerRepository.class);

    ExecutionContext saved = new ExecutionContext();
    saved.putLong("customerReader.lastId", 100L);

    Customer next = new Customer(101L, "Alice", "alice@example.com");
    when(repository.findFirstAfterId(100L)).thenReturn(next);

    CustomerReader reader = new CustomerReader(repository);

    reader.open(saved);

    assertEquals(next, reader.read());

    ExecutionContext updated = new ExecutionContext();
    reader.update(updated);

    assertEquals(
            101L,
            updated.getLong("customerReader.lastId"));

    reader.close();
}
~~~

Test này xác nhận reader khôi phục lastId và ghi lại state sau khi đọc item tiếp theo. Đây chỉ là unit test cho reader lifecycle.

Cần có thêm Step integration test với JobRepository và transaction manager để xác nhận checkpoint được lưu đúng khi chunk commit và không tiến lên khi chunk rollback.

## 24. Kiểm thử nguồn dữ liệu thay đổi

Restart test cũng nên xác minh ứng dụng phát hiện nguồn đầu vào đã thay đổi.

Ví dụ:

1. Chạy Job với file A và lưu checksum.
2. Cho Step thất bại sau một số chunk.
3. Thay nội dung file nhưng giữ nguyên đường dẫn.
4. Restart cùng JobInstance.
5. Reader hoặc bước kiểm tra nguồn phát hiện checksum không khớp.
6. Job dừng với lỗi rõ ràng thay vì tiếp tục trên file khác.

Với database, kiểm thử khi bản ghi được chèn hoặc cập nhật sau watermark. Xác nhận Job chỉ xử lý tập dữ liệu đã định nghĩa cho lần chạy đó hoặc phát hiện thay đổi theo chính sách.

## 25. Quy trình thiết kế reader có thể restart

Khi xây dựng một Step cần restart, hãy lần lượt xác định:

1. Reader có state cần khôi phục không?
2. Reader đã triển khai ItemStream hoặc dùng implementation hỗ trợ ItemStream chưa?
3. open() có khôi phục state từ ExecutionContext không?
4. update() có lưu vị trí đọc đúng trước checkpoint không?
5. close() có giải phóng resource an toàn không?
6. saveState có được bật không?
7. Reader có tên ổn định và duy nhất trong phạm vi phù hợp không?
8. Step có đăng ký reader và mọi delegate ItemStream không?
9. JobRepository có lưu metadata bền vững không?
10. Nguồn file/database có giữ cùng nội dung hoặc snapshot qua restart không?
11. Query có thứ tự ổn định và khóa tiếp tục duy nhất không?
12. Reader có state riêng cho mỗi partition/worker không?
13. Job restart dùng đúng identifying JobParameters không?
14. Test có xác nhận chunk đã commit không bị đọc/ghi lại và chunk chưa commit được xử lý lại không?

Reader state là nền tảng để Spring Batch biết phải tiếp tục đọc từ đâu sau khi Step bị dừng hoặc thất bại. ItemStream định nghĩa cách mở, cập nhật và đóng reader; Step ExecutionContext lưu checkpoint; JobRepository giữ checkpoint qua các lần thực thi. Khi reader có state ổn định, nguồn dữ liệu không bị thay đổi ngoài dự kiến và transaction lưu checkpoint đúng ranh giới commit, Job có thể restart mà không bỏ sót hoặc xử lý trùng dữ liệu.
