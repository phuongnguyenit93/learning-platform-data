# JdbcBatchItemWriter

JdbcBatchItemWriter là một ItemWriter có sẵn của Spring Batch, dùng để ghi một nhóm item vào database bằng JDBC batch update. Thay vì thực hiện một câu lệnh ghi riêng cho từng item theo cách thủ công, writer nhận cả Chunk và gửi các tham số tương ứng thành một batch thông qua NamedParameterJdbcTemplate.

Thành phần này phù hợp với các Job import, đồng bộ hoặc chuyển đổi dữ liệu khi mỗi item cần được insert hoặc update vào database quan hệ. Nó hỗ trợ named parameter, ánh xạ tham số từ JavaBean hoặc Map, và cho phép cung cấp cơ chế tạo SqlParameterSource tùy chỉnh.

JdbcBatchItemWriter chỉ đảm nhiệm thao tác ghi. Spring Batch quản lý chunk, transaction, retry, skip và checkpoint xung quanh writer. Vì vậy, cần hiểu cách writer tương tác với transaction manager, số lượng update được database báo về và hành vi khi một item trong batch gây lỗi.

## 1. JdbcBatchItemWriter trong chunk-oriented processing

Một chunk-oriented Step đọc và xử lý một nhóm item rồi chuyển nhóm kết quả cho writer. JdbcBatchItemWriter nhận chunk đó và thực thi câu SQL cho từng item bằng JDBC batch update.

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
Chunk<T>
    |
    v
JdbcBatchItemWriter
    |
    v
NamedParameterJdbcTemplate
    |
    v
JDBC batchUpdate
    |
    v
Relational database
~~~

Ví dụ, với chunk size 100:

1. Reader đọc tối đa 100 bản ghi.
2. Processor chuyển đổi hoặc xác thực các bản ghi.
3. Spring Batch gom các output hợp lệ thành một chunk.
4. Writer tạo một SqlParameterSource cho mỗi item.
5. NamedParameterJdbcTemplate thực thi batch SQL.
6. Nếu chunk thành công, transaction được commit theo cấu hình Step.

Nếu processor trả null cho một item, item đó được filter và không đi tới writer. Nếu writer ném exception, transaction của chunk được xử lý theo rollback, retry hoặc skip policy đã cấu hình.

## 2. Vì sao dùng JdbcBatchItemWriter?

Một ứng dụng có thể tự viết ItemWriter và gọi JdbcTemplate.update() trong vòng lặp. Tuy nhiên, JdbcBatchItemWriter cung cấp sẵn cách chuyển một chunk thành batch update và tích hợp với lifecycle của Step.

Các lợi ích chính:

- Ghi nhiều item trong một lần gọi writer.
- Sử dụng named parameter để câu SQL dễ đọc.
- Ánh xạ tham số từ JavaBean, Map hoặc provider tùy chỉnh.
- Tham gia transaction của chunk khi dùng đúng transaction manager.
- Có tùy chọn xác nhận mỗi câu lệnh đã tác động ít nhất một dòng.
- Giảm lượng mã JDBC lặp lại trong writer tùy chỉnh.

Writer phù hợp khi thao tác có thể diễn đạt bằng một câu SQL áp dụng cho từng item, chẳng hạn insert một dòng hoặc update một bản ghi theo khóa. Nếu mỗi item cần nhiều câu lệnh phức tạp, cần gọi nhiều hệ thống hoặc phải xử lý generated key theo từng item, có thể cần writer tùy chỉnh.

## 3. Cấu hình cơ bản bằng JdbcBatchItemWriterBuilder

Spring Batch cung cấp JdbcBatchItemWriterBuilder<T> để tạo writer. Với model JavaBean, có thể dùng beanMapped():

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customer
                        (customer_id, full_name, email)
                    VALUES
                        (:customerId, :fullName, :email)
                    """)
            .beanMapped()
            .build();
}
~~~

Các phần cấu hình:

- dataSource(dataSource): cung cấp DataSource để tạo NamedParameterJdbcTemplate.
- sql(...): câu SQL dùng cho mỗi item trong chunk.
- beanMapped(): lấy giá trị named parameter từ property của JavaBean.
- build(): tạo writer đã cấu hình.

Có thể truyền một NamedParameterJdbcTemplate đã được tạo sẵn thay cho DataSource bằng jdbcTemplate(...). Chọn một cách cung cấp JDBC template phù hợp với cấu hình ứng dụng và tránh tạo nhiều template không cần thiết.

## 4. Model JavaBean và beanMapped()

beanMapped() dùng BeanPropertyItemSqlParameterSourceProvider để ánh xạ property của item thành named parameter. Tên placeholder trong SQL phải khớp với tên property JavaBean.

Ví dụ model:

~~~java
public class Customer {

    private String customerId;
    private String fullName;
    private String email;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Với model này, SQL có thể dùng:

~~~sql
INSERT INTO customer(customer_id, full_name, email)
VALUES (:customerId, :fullName, :email)
~~~

Spring đọc property customerId, fullName và email từ từng item. Nếu SQL dùng :customer_id trong khi bean chỉ có property customerId, provider không tự suy luận quy tắc đổi snake_case thành camelCase. Placeholder và property phải được đặt tên nhất quán.

beanMapped() thuận tiện khi item là DTO hoặc JavaBean có getter phù hợp. Với model có cấu trúc lồng nhau, tên property hoặc quy tắc chuyển đổi phức tạp, cân nhắc provider tùy chỉnh để tránh phụ thuộc vào cách introspection mặc định.

## 5. Ánh xạ từ Map bằng columnMapped()

Nếu reader hoặc processor tạo item dưới dạng Map<String, Object>, có thể dùng columnMapped():

~~~java
@Bean
JdbcBatchItemWriter<Map<String, Object>> mapWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Map<String, Object>>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO imported_record
                        (record_id, record_name, record_status)
                    VALUES
                        (:record_id, :record_name, :record_status)
                    """)
            .columnMapped()
            .build();
}
~~~

Item cần có các key tương ứng:

~~~java
Map<String, Object> row = new HashMap<>();
row.put("record_id", "R-100");
row.put("record_name", "Sample");
row.put("record_status", "READY");
~~~

columnMapped() dùng ColumnMapItemSqlParameterSourceProvider để lấy giá trị theo tên key. Key của map phải khớp placeholder SQL. Nên dùng một quy ước chữ hoa/chữ thường thống nhất vì hành vi map key có thể phụ thuộc loại Map và cách tạo map.

Map hữu ích khi cấu trúc dữ liệu thay đổi hoặc được tạo từ kết quả truy vấn động. Tuy nhiên, JavaBean hoặc DTO thường dễ kiểm tra kiểu dữ liệu hơn và giảm lỗi do key viết sai.

## 6. Dùng ItemSqlParameterSourceProvider tùy chỉnh

Khi item không phải JavaBean thông thường hoặc cần đổi tên/biến đổi giá trị trước khi bind, có thể cung cấp ItemSqlParameterSourceProvider<T>:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO order_import
                        (order_id, customer_id, total_amount, imported_at)
                    VALUES
                        (:orderId, :customerId, :totalAmount, :importedAt)
                    """)
            .itemSqlParameterSourceProvider(order ->
                    new MapSqlParameterSource()
                            .addValue("orderId", order.getId())
                            .addValue("customerId", order.getCustomer().getId())
                            .addValue("totalAmount", order.getAmount())
                            .addValue("importedAt", Timestamp.from(order.getImportedAt())))
            .build();
}
~~~

Provider trả về một SqlParameterSource cho từng item. Có thể dùng MapSqlParameterSource, BeanPropertySqlParameterSource hoặc implementation riêng.

Đây là cách phù hợp khi:

- Tên property Java khác tên placeholder SQL.
- Item có cấu trúc lồng nhau.
- Cần chuẩn hóa hoặc chuyển đổi giá trị trước khi ghi.
- Cần thêm một giá trị được tính từ item.
- Cần bind kiểu SQL hoặc giá trị null theo cách tường minh.

Provider nên là hàm xác định và không tạo tác dụng phụ. Nó có thể được gọi lại nếu writer được thực thi lại do retry hoặc cơ chế cô lập item lỗi.

## 7. Named parameter trong SQL

JdbcBatchItemWriter sử dụng NamedParameterJdbcTemplate, vì vậy câu SQL dùng placeholder có tên bắt đầu bằng dấu hai chấm:

~~~sql
INSERT INTO customer(customer_id, full_name)
VALUES (:customerId, :fullName)
~~~

Tên placeholder không phải tên cột bắt buộc. Chúng là tên tham số được map tới giá trị trong item.

Ví dụ update:

~~~sql
UPDATE customer
SET full_name = :fullName,
    email = :email
WHERE customer_id = :customerId
~~~

Ví dụ delete:

~~~sql
DELETE FROM customer_staging
WHERE batch_id = :batchId
  AND customer_id = :customerId
~~~

Named parameter giúp đọc SQL dễ hơn so với vị trí ? của PreparedStatement. Giá trị được bind qua JDBC thay vì nối trực tiếp vào chuỗi SQL.

Không đặt dấu nháy quanh placeholder:

~~~sql
-- Đúng
WHERE customer_id = :customerId

-- Sai: biến placeholder thành literal string
WHERE customer_id = ':customerId'
~~~

Không thể dùng bind parameter để thay thế tên bảng, tên cột hoặc từ khóa SQL. Nếu cấu trúc SQL cần thay đổi theo tham số, hãy chọn từ allowlist đã định nghĩa trước và tạo câu SQL từ các identifier được kiểm soát. Không nối trực tiếp identifier do người dùng gửi vào SQL.

## 8. Ghi dữ liệu bằng INSERT

Một trường hợp phổ biến là import item mới vào bảng đích:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerInsertWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customer
                        (customer_id, full_name, email)
                    VALUES
                        (:customerId, :fullName, :email)
                    """)
            .beanMapped()
            .build();
}
~~~

Với mỗi item trong chunk, writer tạo parameter source và batch SQL insert. Nếu một customer_id vi phạm unique constraint, database có thể ném lỗi duplicate key hoặc data integrity exception.

Nếu nghiệp vụ yêu cầu duplicate là lỗi, hãy để exception làm Step thất bại hoặc cấu hình skip/retry cụ thể theo yêu cầu. Nếu duplicate được xem là bản ghi đã tồn tại hợp lệ, cân nhắc upsert hoặc kiểm tra idempotency trước khi ghi. Không nên bỏ qua mọi DataIntegrityViolationException vì nó còn có thể biểu thị lỗi constraint khác ngoài duplicate key.

## 9. Ghi dữ liệu bằng UPDATE

Writer cũng có thể thực hiện update theo khóa:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerUpdateWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    UPDATE customer
                    SET full_name = :fullName,
                        email = :email
                    WHERE customer_id = :customerId
                    """)
            .beanMapped()
            .build();
}
~~~

Với update, cần quyết định điều gì xảy ra khi không có dòng nào khớp customerId. Theo mặc định, assertUpdates được bật. Khi JDBC báo số dòng cập nhật bằng 0 cho một item, writer báo lỗi thay vì âm thầm chấp nhận rằng không có bản ghi nào được thay đổi.

Đây là hành vi hữu ích nếu mỗi item bắt buộc phải cập nhật đúng một bản ghi. Nếu update zero row là hợp lệ theo nghiệp vụ, có thể tắt assertion sau khi đã quyết định rõ cách theo dõi trường hợp đó.

## 10. assertUpdates và số dòng được cập nhật

JdbcBatchItemWriterBuilder có tùy chọn assertUpdates(boolean). Mặc định là true.

~~~java
return new JdbcBatchItemWriterBuilder<Customer>()
        .dataSource(dataSource)
        .sql("""
                UPDATE customer
                SET email = :email
                WHERE customer_id = :customerId
                """)
        .beanMapped()
        .assertUpdates(true)
        .build();
~~~

Khi assertion bật, writer kiểm tra update count mà JDBC driver trả về. Nếu một item không làm thay đổi dòng nào (update count bằng 0), writer ném exception để báo rằng câu lệnh không cập nhật bản ghi như mong đợi.

Có thể tắt assertion:

~~~java
.assertUpdates(false)
~~~

Điều này phù hợp khi câu lệnh có thể hợp lệ dù update count bằng 0, ví dụ:

- Update chỉ thay đổi dữ liệu khi giá trị khác hiện tại.
- Một bản ghi có thể đã bị xóa bởi quy trình khác.
- SQL có điều kiện khiến một số item không cần cập nhật.
- Stored procedure hoặc driver có quy ước update count đặc biệt.

Chỉ tắt assertion nếu zero update là kết quả nghiệp vụ được chấp nhận. Nếu bản ghi bắt buộc phải tồn tại, tắt assertion có thể che giấu lỗi khóa ngoại, sai ID hoặc dữ liệu nguồn không khớp.

Một số JDBC driver có thể trả về SUCCESS_NO_INFO thay vì số dòng chính xác cho một batch element. Vì vậy, không nên giả định mọi database/driver luôn báo cùng một update count. Hãy kiểm thử với driver được dùng ở production.

## 11. Cấu hình Step với JdbcBatchItemWriter

Ví dụ Step hoàn chỉnh trong Spring Batch 5:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        JdbcBatchItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
~~~

chunk(500, transactionManager) đặt kích thước chunk là 500 item và cung cấp transaction manager cho Step. Writer được gọi với output chunk sau khi reader và processor hoàn tất phần xử lý tương ứng.

Kích thước chunk ảnh hưởng đến số item trong một lần batch update, bộ nhớ, thời lượng transaction và lượng công việc phải làm lại khi rollback. Chunk lớn có thể giảm số lần commit nhưng tăng thời gian giữ lock và lượng dữ liệu cần retry. Chunk nhỏ giảm phạm vi transaction nhưng tăng overhead commit và round trip.

Chunk size không bảo đảm database driver thực hiện mọi lệnh trong một gói mạng duy nhất. JDBC driver và database có thể chia hoặc xử lý batch theo cách riêng. Cần đo hiệu năng với driver, schema và workload thực tế.

## 12. Transaction và rollback

JdbcBatchItemWriter không tự mở hoặc commit một transaction độc lập cho mỗi item. Nó thực hiện batch update trong transaction do Step quản lý nếu DataSource của writer tham gia cùng transaction manager.

Khi writer ném exception và transaction của chunk rollback:

- Các thay đổi database chưa commit trong transaction đó được hoàn tác.
- Các chunk trước đã commit vẫn tồn tại.
- Spring Batch có thể retry hoặc skip theo cấu hình fault tolerance.
- Checkpoint và metadata được cập nhật theo transaction/repository configuration.

Ví dụ cấu hình transaction:

~~~java
@Bean
Step writeCustomersStep(
        JobRepository jobRepository,
        @Qualifier("batchTransactionManager")
        PlatformTransactionManager transactionManager,
        JdbcBatchItemWriter<Customer> writer,
        ItemReader<Customer> reader) {

    return new StepBuilder("writeCustomersStep", jobRepository)
            .<Customer, Customer>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Transaction manager cần quản lý đúng DataSource mà writer dùng. Nếu writer ghi vào một database/resource khác với transaction manager của Step, không thể mặc định các thao tác đó rollback cùng nhau. Với nhiều resource, cần thiết kế transaction coordination hoặc cơ chế bù trừ phù hợp.

Không gọi commit() hoặc rollback() thủ công bên trong writer. Làm vậy có thể phá vỡ ranh giới transaction do Spring Batch quản lý.

## 13. Skip và retry khi batch write thất bại

Writer có thể gặp các lỗi như:

- Duplicate key.
- Foreign key hoặc check constraint violation.
- Deadlock hoặc lock timeout.
- Database connection failure.
- SQL syntax hoặc mapping error.

Không phải mọi lỗi đều phù hợp với cùng một policy. Deadlock tạm thời có thể retry; một bản ghi vi phạm quy tắc nghiệp vụ có thể skip nếu nghiệp vụ cho phép; lỗi SQL do cấu hình sai thường cần làm Step thất bại.

Ví dụ cấu hình retry và skip:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(DuplicateKeyException.class)
        .skipLimit(20)
        .listener(orderSkipListener)
        .build();
~~~

Ví dụ trên chỉ phù hợp nếu duplicate key thực sự là item có thể bỏ qua. Nếu duplicate phản ánh lỗi dữ liệu cần điều tra, không nên skip. Cũng cần kiểm tra exception translation của driver để xác định loại exception thực tế được ném.

Khi fault tolerance cần xác định item gây lỗi trong một batch writer, Spring Batch có thể gọi lại writer với các nhóm item nhỏ hơn hoặc từng item để cô lập lỗi. Vì vậy, writer phải an toàn khi được gọi nhiều lần trong quá trình xử lý lỗi. Các thao tác database cần nằm trong transaction và các tác dụng phụ ngoài database phải có idempotency.

## 14. Idempotency và ghi trùng

Restart hoặc retry có thể khiến cùng một item được gửi tới writer nhiều hơn một lần. Nếu SQL luôn insert, lần chạy lại có thể vi phạm unique constraint hoặc tạo dữ liệu trùng nếu bảng không có khóa duy nhất phù hợp.

Các cách giảm rủi ro:

- Dùng business key ổn định và unique constraint trong database.
- Dùng upsert theo cú pháp database nếu nghiệp vụ cho phép.
- Ghi batch ID/source version để phân biệt lần import.
- Dùng staging table rồi merge dữ liệu theo quy tắc xác định.
- Đối soát kết quả trước khi replay một chunk đã thất bại.

Ví dụ upsert là cú pháp riêng của database. Với PostgreSQL:

~~~sql
INSERT INTO customer(customer_id, full_name, email)
VALUES (:customerId, :fullName, :email)
ON CONFLICT (customer_id)
DO UPDATE SET
    full_name = EXCLUDED.full_name,
    email = EXCLUDED.email
~~~

Với database khác, cú pháp có thể là MERGE hoặc dạng upsert riêng. Không nên đưa SQL upsert của một database vào ứng dụng cần portability mà không có abstraction hoặc kiểm thử tương ứng.

Idempotency không có nghĩa luôn phải update. Nó có nghĩa lặp cùng một business operation không tạo ra kết quả sai hoặc tác dụng phụ trùng. Quy tắc insert-only, update-only hay upsert phụ thuộc yêu cầu nghiệp vụ.

## 15. Ghi nhiều bảng hoặc nhiều câu lệnh

JdbcBatchItemWriter thực hiện một câu SQL template cho từng item trong batch. Nếu một item cần ghi vào nhiều bảng, có thể:

- Dùng một writer tùy chỉnh gọi nhiều batch writer trong cùng transaction.
- Dùng composite writer nếu các writer có thể được ghép và lifecycle được quản lý đúng.
- Chuyển đổi dữ liệu thành các luồng Step riêng nếu các thao tác có vòng đời hoặc transaction khác nhau.
- Dùng stored procedure nếu logic nhiều câu lệnh được quản lý tại database.

Ví dụ writer điều phối hai writer:

~~~java
public class CustomerAndAuditWriter implements ItemWriter<Customer> {

    private final JdbcBatchItemWriter<Customer> customerWriter;
    private final JdbcBatchItemWriter<CustomerAudit> auditWriter;

    public CustomerAndAuditWriter(
            JdbcBatchItemWriter<Customer> customerWriter,
            JdbcBatchItemWriter<CustomerAudit> auditWriter) {
        this.customerWriter = customerWriter;
        this.auditWriter = auditWriter;
    }

    @Override
    public void write(Chunk<? extends Customer> chunk) throws Exception {
        customerWriter.write(chunk);

        Chunk<CustomerAudit> auditChunk = new Chunk<>();
        for (Customer customer : chunk) {
            auditChunk.add(CustomerAudit.from(customer));
        }
        auditWriter.write(auditChunk);
    }
}
~~~

Đây là ý tưởng minh họa; kiểu Chunk và cách chuyển đổi cần khớp với API của phiên bản đang dùng. Hai writer phải dùng cùng transaction manager/DataSource nếu yêu cầu cả hai thao tác commit hoặc rollback cùng nhau. Nếu writer thứ hai thất bại sau khi writer thứ nhất đã chạy, transaction chunk phải rollback các thay đổi database của cả hai.

Nếu hai writer dùng hai database khác nhau, một transaction local thông thường không bảo đảm atomicity xuyên hai resource. Khi đó cần distributed transaction hoặc thiết kế outbox/saga/compensation.

## 16. Generated keys và giá trị trả về

JdbcBatchItemWriter tập trung thực hiện batch update và không tự động map generated key của từng câu insert ngược trở lại object đầu vào. JDBC batch update thường trả về mảng update count; đó không phải danh sách generated key theo từng item.

Nếu bước sau cần ID database vừa được tạo, có thể:

- Dùng business key ổn định đã có từ nguồn.
- Dùng sequence/ID được cấp trước khi ghi.
- Truy vấn lại theo business key và batch ID.
- Viết custom ItemWriter sử dụng JDBC API hỗ trợ generated keys theo nhu cầu và driver.
- Thiết kế Step sau đọc kết quả đã ghi từ database.

Không nên giả định JdbcBatchItemWriter sẽ cập nhật field ID trong DTO sau khi insert. Nếu yêu cầu generated key là trọng tâm, hãy chọn API ghi dữ liệu phù hợp và kiểm thử với database/driver thực tế.

## 17. Null, kiểu SQL và dữ liệu ngày giờ

Named parameter provider lấy giá trị từ object nhưng database vẫn cần kiểu SQL phù hợp. Với giá trị null, kiểu dữ liệu có thể cần được chỉ định tường minh, đặc biệt khi driver không suy luận được kiểu từ null.

MapSqlParameterSource cho phép thêm giá trị cùng kiểu SQL:

~~~java
new MapSqlParameterSource()
        .addValue("customerId", customer.getCustomerId())
        .addValue("birthDate", customer.getBirthDate(), Types.DATE)
        .addValue("middleName", customer.getMiddleName(), Types.VARCHAR);
~~~

Với LocalDate, LocalDateTime, BigDecimal hoặc enum, hãy xác nhận conversion và kiểu cột database tương thích. Tiền tệ nên dùng BigDecimal thay vì float/double để tránh sai số nhị phân.

Nếu giá trị cần chuẩn hóa múi giờ, hãy thống nhất quy ước UTC hoặc timezone nghiệp vụ trước khi ghi. Không dựa vào timezone mặc định của máy chạy Job.

## 18. Hiệu năng và lựa chọn chunk size

JdbcBatchItemWriter giảm overhead so với gọi update riêng lẻ, nhưng hiệu năng tổng thể còn phụ thuộc:

- Chunk size.
- Số cột và kích thước payload mỗi item.
- Index, constraint, trigger và foreign key của bảng.
- Connection pool và transaction isolation.
- JDBC driver có hỗ trợ batch hiệu quả hay không.
- Lock contention khi nhiều Job cùng ghi một bảng.
- Kích thước batch mà database có thể xử lý hiệu quả.

Chunk lớn:

- Giảm số lần commit.
- Có thể tăng throughput khi database xử lý batch tốt.
- Giữ transaction và lock lâu hơn.
- Dùng nhiều bộ nhớ hơn.
- Làm phạm vi rollback/retry lớn hơn.

Chunk nhỏ:

- Commit thường xuyên hơn.
- Giảm lượng item phải làm lại sau rollback.
- Có thể tăng overhead transaction và round trip.

Hãy benchmark bằng dữ liệu đại diện. Bắt đầu với chunk size vừa phải, theo dõi throughput, thời gian transaction, lock wait và memory. Không nên tăng chunk size chỉ dựa vào số item trung bình mà không quan sát database.

## 19. Thread safety và nhiều worker

JdbcBatchItemWriter được thiết kế để dùng trong môi trường Spring Batch và có thể dùng chung sau khi cấu hình hoàn tất. Không thay đổi SQL, DataSource hoặc parameter provider trong khi Step đang chạy.

Khi nhiều thread hoặc partition dùng writer:

- Các item phải được bind độc lập, không dùng mutable shared parameter map bị ghi đè.
- DataSource/connection pool phải đáp ứng concurrency.
- Phạm vi dữ liệu cần tránh xung đột ghi nếu có thể.
- Unique constraint và locking phải bảo vệ tính nhất quán ở database.
- Provider tùy chỉnh không được giữ state theo item trong field dùng chung.

NamedParameterJdbcTemplate là thành phần dùng chung an toàn sau khi cấu hình. Tuy nhiên, service hoặc object mà provider gọi tới vẫn cần được đánh giá thread safety.

Nếu nhiều partition cùng insert/update một khóa, database có thể gặp deadlock hoặc lock contention. Hãy phân vùng dữ liệu hợp lý, sắp xếp thứ tự ghi nhất quán hoặc giảm mức concurrency nếu cần.

## 20. Kiểm thử JdbcBatchItemWriter

Nên kiểm thử writer với database test tương thích với SQL thực tế. H2 phù hợp cho nhiều test cơ bản, nhưng nếu ứng dụng dựa vào cú pháp upsert, kiểu dữ liệu hoặc locking riêng của PostgreSQL/MySQL/Oracle/SQL Server, hãy dùng Testcontainers hoặc môi trường integration tương ứng.

Các tình huống nên kiểm tra:

1. Ghi một item thành công.
2. Ghi nhiều item trong một chunk.
3. Bean property hoặc map key được bind đúng.
4. Provider tùy chỉnh chuyển đổi đúng giá trị.
5. Giá trị null và kiểu SQL được xử lý đúng.
6. Update không tìm thấy bản ghi khi assertUpdates(true).
7. Zero update được chấp nhận khi assertion tắt và nghiệp vụ cho phép.
8. Constraint violation làm transaction rollback đúng.
9. Retry sau deadlock hoặc lỗi tạm thời không tạo bản ghi trùng.
10. Restart không ghi trùng chunk đã commit.
11. Nhiều partition ghi đồng thời không làm sai dữ liệu.

Ví dụ integration test đơn giản:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchWriterTestConfiguration.class)
class JdbcBatchItemWriterTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void writesAllItemsInTheChunk() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRun", "writer-basic-01", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM customer",
                Integer.class);
        assertEquals(3, count);
    }
}
~~~

Ví dụ giả định test configuration cung cấp ba item đầu vào, schema đã được tạo và bảng customer được làm sạch trước test. Khi chạy nhiều test, hãy cô lập database hoặc xóa dữ liệu theo test ID để kết quả không phụ thuộc thứ tự thực thi.

## 21. Các lỗi thường gặp

**Placeholder không khớp property hoặc map key:** :customerId cần property customerId hoặc key tương ứng trong parameter source. Kiểm tra chính tả và quy ước tên.

**Dùng sai provider:** beanMapped() phù hợp JavaBean; columnMapped() phù hợp Map; item có cấu trúc riêng nên dùng provider tùy chỉnh.

**Quên DataSource hoặc SQL:** builder cần JDBC template/DataSource và câu SQL hợp lệ trước khi build.

**Tắt assertUpdates quá sớm:** update zero row có thể che giấu ID không tồn tại hoặc lỗi dữ liệu. Chỉ tắt khi zero update là hợp lệ.

**Nối giá trị vào SQL:** tạo nguy cơ SQL injection và lỗi escaping. Dùng named parameter cho giá trị dữ liệu.

**Cho rằng writer tự commit:** transaction thuộc Step/transaction manager. Không commit thủ công trong writer.

**DataSource không tham gia transaction của Step:** lỗi có thể không rollback cùng metadata hoặc các thao tác khác. Cấu hình đúng transaction manager và resource.

**Bỏ qua mọi DataIntegrityViolationException:** exception này có thể biểu thị nhiều loại constraint violation. Chỉ skip lỗi cụ thể được nghiệp vụ chấp nhận.

**Writer có tác dụng phụ không idempotent:** retry/restart có thể gửi thông báo hoặc gọi API nhiều lần. Dùng outbox hoặc idempotency key.

**Giả định có generated key trong item:** JdbcBatchItemWriter không tự cập nhật generated key theo từng item. Chọn writer/API khác nếu cần.

**Chunk quá lớn:** transaction kéo dài, lock contention và chi phí rollback tăng. Benchmark và điều chỉnh theo workload.

## Kết luận

JdbcBatchItemWriter ghi một chunk item vào database bằng JDBC batch update và named parameter. Dùng beanMapped() cho JavaBean, columnMapped() cho Map hoặc itemSqlParameterSourceProvider() khi cần ánh xạ tùy chỉnh. Cấu hình SQL với placeholder khớp dữ liệu item, chọn assertUpdates theo kỳ vọng số dòng bị tác động và dùng transaction manager quản lý đúng DataSource của writer. Khi vận hành, phân loại rõ lỗi duplicate, constraint, deadlock và lỗi hạ tầng; thiết kế idempotency cho retry/restart, benchmark chunk size và kiểm thử với database/driver thực tế. Writer là phần ghi dữ liệu của chunk, còn transaction, skip, retry và restart vẫn do cấu hình Step cùng Spring Batch quản lý.
