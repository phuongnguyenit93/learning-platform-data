# Cơ chế chuyển lỗi sang hệ phân cấp DataAccessException

Khi truy cập database bằng Spring Data Relational R2DBC, lỗi có thể bắt nguồn từ SQL sai, dữ liệu vi phạm constraint, mất kết nối, timeout, xung đột transaction hoặc cách gọi API không hợp lệ. Driver R2DBC thường biểu diễn các lỗi này bằng **R2dbcException** và những lớp con riêng. Nếu tầng service phụ thuộc trực tiếp vào từng exception của driver, code sẽ gắn chặt với database và khó thay đổi hoặc kiểm thử.

Spring cung cấp hệ phân cấp **DataAccessException** trong package **org.springframework.dao** để chuẩn hóa lỗi truy cập dữ liệu. Cơ chế exception translation chuyển lỗi cấp thấp từ driver thành các exception mang ý nghĩa chung như vi phạm toàn vẹn dữ liệu, cú pháp SQL sai, không lấy được tài nguyên, timeout hoặc xung đột đồng thời.

Mục tiêu của cơ chế này là để tầng nghiệp vụ xử lý theo loại sự cố thay vì phải hiểu mã lỗi riêng của từng driver. Tuy vậy, việc ánh xạ không phải lúc nào cũng xác định được nguyên nhân chi tiết: kết quả phụ thuộc SQLState, mã lỗi của database, loại exception mà driver phát ra và phiên bản Spring đang dùng.

Bài học này giải thích đường đi của lỗi từ R2DBC driver tới DataAccessException, các nhánh chính trong hệ phân cấp, cách Spring Data R2DBC áp dụng exception translation, cách xử lý lỗi trong reactive pipeline, khi nào retry có ý nghĩa và cách chuyển lỗi kỹ thuật thành lỗi nghiệp vụ/API.

## 1. Vì sao cần exception translation?

Mỗi database và driver có thể biểu diễn cùng một loại lỗi theo cách khác nhau. Ví dụ, hai database đều có thể từ chối một lệnh INSERT vì giá trị khóa ngoại không tồn tại, nhưng mã lỗi, SQLState và lớp exception cụ thể có thể khác nhau.

Nếu service phụ thuộc vào exception của một driver:

~~~java
try {
    // gọi driver cụ thể
} catch (SomeVendorConstraintException ex) {
    // xử lý theo database hiện tại
}
~~~

khi đổi driver hoặc database, tầng nghiệp vụ có thể phải thay đổi theo.

Spring chuẩn hóa lỗi thành một họ exception chung:

~~~text
Repository / R2dbcEntityTemplate / DatabaseClient
                       |
                       v
                  R2DBC driver
                       |
                       v
                 R2dbcException
                       |
                       v
            Spring exception translator
                       |
                       v
                DataAccessException
                       |
                       v
             Service / API error mapping
~~~

Ví dụ một lỗi vi phạm unique constraint có thể được chuyển thành **DuplicateKeyException** nếu translator nhận diện được; một lỗi toàn vẹn dữ liệu khác có thể được chuyển thành **DataIntegrityViolationException**. Lỗi SQL không hợp lệ có thể trở thành **BadSqlGrammarException**.

Tầng service có thể xử lý các kiểu Spring DAO exception này mà không cần import lớp exception riêng của PostgreSQL, MySQL hoặc một driver khác.

## 2. DataAccessException là gì?

**DataAccessException** là lớp cơ sở trong hệ phân cấp exception truy cập dữ liệu của Spring. Nó là unchecked exception (kế thừa RuntimeException thông qua hệ exception của Spring), nên phương thức repository/service không phải khai báo throws cho từng lỗi database.

Lớp này thể hiện một sự cố xảy ra trong quá trình truy cập hoặc thao tác dữ liệu. Các lớp con mô tả nhóm nguyên nhân ở mức khái quát, chẳng hạn:

- Dữ liệu vi phạm constraint.
- Câu SQL hoặc cách sử dụng tài nguyên truy cập dữ liệu không hợp lệ.
- Không đọc được dữ liệu hoặc kích thước kết quả không như mong đợi.
- Tài nguyên database tạm thời không sẵn sàng.
- Xung đột đồng thời hoặc không lấy được khóa.
- Truy vấn vượt quá thời gian cho phép.
- Lỗi không được translator phân loại cụ thể.

DataAccessException không phải exception nghiệp vụ. Nó mô tả lỗi ở tầng persistence. Service có thể chuyển một số lỗi đã hiểu thành domain exception, ví dụ email đã được đăng ký hoặc tài khoản đang được cập nhật bởi request khác.

### 2.1. Hệ phân cấp ở mức khái niệm

Các nhánh thường được dùng để phân loại lỗi:

~~~text
DataAccessException
|
+-- NonTransientDataAccessException
|   |
|   +-- DataIntegrityViolationException
|   |   |
|   |   +-- DuplicateKeyException
|   |
|   +-- InvalidDataAccessResourceUsageException
|   |   |
|   |   +-- BadSqlGrammarException (Spring R2DBC)
|   |
|   +-- InvalidDataAccessApiUsageException
|   +-- DataRetrievalFailureException
|   +-- UncategorizedDataAccessException
|
+-- TransientDataAccessException
|   |
|   +-- ConcurrencyFailureException
|   |   |
|   |   +-- PessimisticLockingFailureException
|   |   +-- OptimisticLockingFailureException
|   |
|   +-- QueryTimeoutException
|
+-- RecoverableDataAccessException
~~~

Đây là sơ đồ định hướng các nhóm quan trọng, không phải danh sách đầy đủ mọi lớp con hoặc mọi quan hệ kế thừa trong tất cả phiên bản Spring. Một số lớp cụ thể nằm trong package Spring R2DBC hoặc Spring DAO và tên/chi tiết có thể thay đổi theo phiên bản.

Điểm quan trọng nhất là phân biệt lỗi **transient** (có thể hết khi thử lại sau) với lỗi **non-transient** (thường cần sửa câu lệnh, dữ liệu, cấu hình hoặc logic trước khi thử lại).

## 3. NonTransientDataAccessException và TransientDataAccessException

Spring chia nhiều lỗi truy cập dữ liệu thành hai nhóm lớn.

### 3.1. NonTransientDataAccessException

Đây là các lỗi thường không tự biến mất nếu chạy lại cùng một thao tác với cùng câu lệnh và dữ liệu. Ví dụ:

- Câu SQL sai cú pháp.
- Dùng sai API hoặc tham số không hợp lệ.
- Vi phạm unique, foreign key, check constraint.
- Không đủ quyền truy cập bảng hoặc schema.
- Kết quả không đáp ứng hợp đồng của truy vấn.

Retry ngay thường chỉ tạo thêm tải và lặp lại lỗi.

Ví dụ: INSERT một email đã tồn tại sẽ tiếp tục thất bại nếu không thay đổi dữ liệu hoặc nghiệp vụ. Cách xử lý phù hợp là trả lỗi nghiệp vụ có ý nghĩa, hoặc yêu cầu client dùng giá trị khác.

### 3.2. TransientDataAccessException

Đây là các lỗi có khả năng biến mất nếu thử lại sau một khoảng thời gian hoặc sau khi trạng thái đồng thời thay đổi. Ví dụ:

- Tạm thời không lấy được connection hoặc tài nguyên.
- Xung đột khóa do transaction khác đang giữ lock.
- Một số timeout hoặc lỗi đồng thời.
- Một số optimistic/pessimistic locking conflict.

Transient không đồng nghĩa chắc chắn retry sẽ thành công. Retry cần giới hạn số lần, có backoff và chỉ áp dụng với thao tác an toàn để thực hiện lại.

Ví dụ: một thao tác cập nhật số dư bị optimistic locking failure thường cần đọc lại dữ liệu mới và tính toán lại. Chạy lại nguyên câu lệnh với entity cũ có thể tiếp tục thất bại hoặc làm sai logic.

### 3.3. RecoverableDataAccessException

Spring còn có nhánh **RecoverableDataAccessException** cho một số lỗi có thể phục hồi bằng cách thử lại hoặc thực hiện quy trình khôi phục thích hợp. Đây không phải nhãn cho mọi lỗi kết nối; hãy dựa vào exception thực tế và khả năng phục hồi của thao tác.

Không nên tự suy luận rằng mọi exception có chữ "resource" đều transient hoặc mọi lỗi driver đều có thể retry.

## 4. Các exception thường gặp trong ứng dụng R2DBC

Bảng dưới đây tập trung vào các lớp Spring thường hữu ích khi xử lý lỗi. Việc translator trả về lớp cụ thể nào còn phụ thuộc driver/database và thông tin lỗi mà driver cung cấp.

| Exception | Ý nghĩa | Hướng xử lý thường gặp |
|---|---|---|
| **DataIntegrityViolationException** | Dữ liệu vi phạm constraint hoặc quy tắc toàn vẹn | Chuyển thành lỗi nghiệp vụ phù hợp; không retry mù |
| **DuplicateKeyException** | Vi phạm khóa duy nhất/khóa chính được nhận diện cụ thể | Báo trùng mã, email hoặc tài nguyên |
| **BadSqlGrammarException** | Câu SQL không hợp lệ hoặc sai cú pháp | Sửa SQL, tên bảng/cột, placeholder |
| **InvalidDataAccessResourceUsageException** | Sử dụng tài nguyên hoặc câu lệnh database không hợp lệ | Kiểm tra query, kiểu tham số, schema và quyền |
| **InvalidDataAccessApiUsageException** | Gọi API truy cập dữ liệu sai hợp đồng | Sửa cách dùng API hoặc dữ liệu đầu vào |
| **DataAccessResourceFailureException** | Tài nguyên truy cập dữ liệu gặp sự cố | Kiểm tra connection, database và hạ tầng |
| **TransientDataAccessResourceException** | Lỗi tài nguyên có tính tạm thời | Có thể retry có giới hạn nếu thao tác an toàn |
| **QueryTimeoutException** | Truy vấn vượt quá thời gian cho phép | Kiểm tra query, tải database và timeout; cân nhắc retry có điều kiện |
| **ConcurrencyFailureException** | Xung đột do nhiều transaction đồng thời | Đọc lại, retry hoặc xử lý conflict theo nghiệp vụ |
| **OptimisticLockingFailureException** | Version của entity không còn khớp khi cập nhật | Đọc lại dữ liệu và yêu cầu tính toán/cập nhật lại |
| **PessimisticLockingFailureException** / **CannotAcquireLockException** | Không lấy được lock cần thiết | Chờ/retry có giới hạn hoặc trả conflict |
| **IncorrectResultSizeDataAccessException** | Số hàng trả về không phù hợp hợp đồng | Sửa điều kiện query hoặc dữ liệu/constraint |
| **UncategorizedR2dbcException** | Lỗi R2DBC không được phân loại cụ thể | Xem cause, SQLState, mã lỗi và log an toàn |

**DuplicateKeyException** là một trường hợp cụ thể của **DataIntegrityViolationException**. Khi bắt lỗi, có thể bắt lớp cụ thể trước rồi mới tới lớp cha.

**BadSqlGrammarException** trong Spring R2DBC thuộc package **org.springframework.r2dbc**; các lớp chung như **DataAccessException** và **DataIntegrityViolationException** thuộc **org.springframework.dao**.

Không phụ thuộc vào một exception cụ thể nếu translator của driver mục tiêu không phát ra lớp đó. Với lỗi constraint, có driver chỉ cung cấp một exception toàn vẹn dữ liệu chung thay vì phân biệt duplicate key.

## 5. Spring chuyển lỗi R2DBC như thế nào?

Ở tầng thấp, driver phát lỗi theo R2DBC SPI, thường là **R2dbcException** hoặc một lớp con. Exception có thể chứa thông tin như:

- Thông điệp lỗi từ database.
- SQLState nếu driver cung cấp.
- Vendor error code.
- Câu SQL liên quan nếu có.
- Exception gốc hoặc nguyên nhân lồng bên trong.

Spring sử dụng exception translator để chuyển lỗi driver thành hệ phân cấp **DataAccessException**. Việc phân loại có thể dựa trên loại exception R2DBC, SQLState, vendor code và quy tắc của translator.

Một số nhóm lỗi có thể được nhận diện khá rõ, chẳng hạn lỗi cú pháp hoặc lỗi toàn vẹn dữ liệu. Một số lỗi khác chỉ có thể được phân loại thành exception chung vì driver không cung cấp đủ thông tin.

### 5.1. SQLState và vendor code

SQLState là mã phân loại lỗi theo chuẩn SQL hoặc quy ước của hệ quản trị. Nhiều database dùng nhóm mã để biểu diễn loại lỗi, chẳng hạn nhóm integrity constraint violation.

Vendor code là mã riêng của hệ quản trị. Cùng một tình huống có thể có mã vendor khác nhau giữa các database.

Không nên viết business logic như sau:

~~~java
if (exception.getSqlState().equals("23505")) {
    // giả định mọi database đều dùng mã này cho duplicate key
}
~~~

Mã **23505** là mã thường gặp của PostgreSQL cho unique violation, nhưng không phải mã phổ quát của mọi database. Nếu phải xử lý mã riêng, cô lập logic đó trong adapter persistence dành cho database/driver tương ứng.

### 5.2. Lỗi không phân loại được

Khi translator không xác định được một nhóm cụ thể, Spring có thể bọc lỗi thành exception không phân loại như **UncategorizedR2dbcException** hoặc một lớp **UncategorizedDataAccessException** phù hợp.

Điều đó không có nghĩa lỗi vô hại. Cần xem cause và metadata để chẩn đoán, đồng thời giữ tầng service tránh phụ thuộc vào chi tiết vendor nếu không thực sự cần.

## 6. Exception translation ở repository, template và DatabaseClient

Spring Data R2DBC cung cấp nhiều entry point truy cập dữ liệu:

- Reactive repository.
- **R2dbcEntityTemplate**.
- **DatabaseClient**.
- R2DBC SPI trực tiếp.

Với repository, Spring Data quản lý việc thực thi query và mapping entity; lỗi driver được chuyển qua cơ chế exception translation của Spring Data/Spring R2DBC.

**R2dbcEntityTemplate** và **DatabaseClient** cũng là các abstraction của Spring giúp thực hiện truy vấn và chuyển lỗi sang hệ exception truy cập dữ liệu của Spring.

Ví dụ **DatabaseClient**:

~~~java
Mono<Long> insertCustomer(String email) {
    return databaseClient.sql("""
            INSERT INTO customer(email_address)
            VALUES (:email)
            """)
            .bind("email", email)
            .fetch()
            .rowsUpdated();
}
~~~

Nếu database từ chối insert do unique constraint, publisher sẽ phát lỗi. Ở tầng sử dụng Spring abstraction, lỗi thường đã được chuyển sang một **DataAccessException** tương ứng.

Khi dùng R2DBC SPI trực tiếp (**Connection**, **Statement**, **Result**), ứng dụng có thể nhận exception cấp driver mà không đi qua cùng đường dịch lỗi của **DatabaseClient** hoặc repository. Nếu muốn một contract thống nhất, cần chủ động dùng translator phù hợp hoặc cô lập việc xử lý exception driver ở adapter thấp nhất.

Không giả định mọi đường truy cập dữ liệu đều trả cùng một lớp exception. Hãy xác nhận bằng integration test trên entry point thực tế mà ứng dụng sử dụng.

## 7. Lỗi truy vấn không giống kết quả rỗng

Một điểm quan trọng trong reactive repository là không có dữ liệu thường được biểu diễn bằng publisher rỗng, không phải **DataAccessException**.

| Tình huống | Kết quả thường gặp |
|---|---|
| **findById(id)** không tìm thấy hàng | **Mono.empty()** |
| Derived query trả nhiều kết quả | **Flux<T>** có thể rỗng hoặc phát nhiều phần tử |
| **existsById(id)** không tìm thấy | Phát **false** |
| **count()** trên bảng rỗng | Phát **0** |
| Một hàng tồn tại nhưng cột nullable là SQL **NULL** | Phát entity với property tương ứng null |
| SQL sai cú pháp | Lỗi được dịch sang exception truy cập dữ liệu |
| Mất kết nối hoặc timeout | Lỗi truy cập tài nguyên/timeout |
| Vi phạm unique constraint | Lỗi toàn vẹn dữ liệu |

Ví dụ:

~~~java
Mono<Customer> customer =
        customerRepository.findById(customerId);
~~~

Nếu ID không tồn tại, publisher có thể hoàn tất rỗng. Không nên bắt **DataAccessException** để xử lý trường hợp này. Dùng **switchIfEmpty** khi use case yêu cầu bản ghi phải có:

~~~java
return customerRepository.findById(customerId)
        .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(customerId)));
~~~

Tương tự, **Flux.empty()** thường là kết quả hợp lệ của tìm kiếm không có hàng phù hợp. Đừng biến mọi kết quả rỗng thành lỗi database.

## 8. Xử lý DataAccessException trong reactive pipeline

Vì **Mono** và **Flux** thực thi khi được subscribe, lỗi truy cập dữ liệu thường được phát như **onError** trong reactive stream. Một **try/catch** bao quanh lời gọi tạo publisher không bắt được lỗi phát ra sau đó.

Không nên:

~~~java
public Mono<Customer> findCustomer(Long id) {
    try {
        return customerRepository.findById(id);
    } catch (DataAccessException ex) {
        // thường không bắt được lỗi xảy ra khi publisher thực thi
        return Mono.empty();
    }
}
~~~

Dùng các toán tử reactive để quan sát, chuyển đổi hoặc phục hồi lỗi.

### 8.1. doOnError: quan sát lỗi

**doOnError** thực hiện side effect như ghi log hoặc tăng metric nhưng giữ nguyên tín hiệu lỗi:

~~~java
return customerRepository.findById(id)
        .doOnError(DataAccessException.class, error ->
                log.error("Database access failed for customer lookup", error));
~~~

Sau **doOnError**, lỗi vẫn tiếp tục tới subscriber. Không dùng **doOnError** nếu mục tiêu là chuyển lỗi thành kết quả khác.

Log cần tránh chứa password, token, thông tin cá nhân hoặc bind parameter nhạy cảm. Thông điệp SQL của driver đôi khi chứa dữ liệu đầu vào hoặc tên schema/table nội bộ; chỉ ghi khi chính sách log của ứng dụng cho phép.

### 8.2. onErrorMap: chuyển lỗi kỹ thuật thành lỗi domain

Dùng **onErrorMap** khi muốn chuyển một exception thành loại lỗi có ý nghĩa hơn ở tầng service:

~~~java
return customerRepository.save(customer)
        .onErrorMap(
                DuplicateKeyException.class,
                error -> new EmailAlreadyRegisteredException(
                        customer.getEmail(), error));
~~~

Ví dụ này giả định translator nhận diện duplicate key bằng **DuplicateKeyException**. Nếu driver chỉ phát **DataIntegrityViolationException**, cần xử lý lớp đó và xác định constraint cụ thể trước khi kết luận đây là email trùng.

Domain exception nên giữ cause để hỗ trợ chẩn đoán:

~~~java
public class EmailAlreadyRegisteredException extends RuntimeException {

    public EmailAlreadyRegisteredException(String email, Throwable cause) {
        super("Email is already registered: " + email, cause);
    }
}
~~~

Trong ứng dụng thực tế, cân nhắc không đưa email đầy đủ vào log hoặc response nếu đó là dữ liệu cá nhân.

### 8.3. onErrorResume: phục hồi có chủ đích

**onErrorResume** thay publisher lỗi bằng một publisher khác:

~~~java
return configurationRepository.findById(key)
        .onErrorResume(
                DataAccessResourceFailureException.class,
                error -> cachedConfiguration(key));
~~~

Cách này có thể phù hợp khi đọc cấu hình từ cache là fallback được nghiệp vụ chấp nhận. Không nên dùng fallback cho mọi **DataAccessException**, vì lỗi SQL hoặc vi phạm dữ liệu không được giải quyết bằng cache.

Không biến lỗi database thành **Mono.empty()** chỉ để endpoint không báo lỗi:

~~~java
// Không nên: che lỗi truy cập dữ liệu thành trạng thái "không có bản ghi".
return repository.findById(id)
        .onErrorResume(error -> Mono.empty());
~~~

Nếu lỗi bị đổi thành empty, tầng API có thể trả 404 hoặc danh sách rỗng và che giấu sự cố thật.

## 9. Bắt exception cụ thể trước exception tổng quát

Do hệ phân cấp có quan hệ kế thừa, thứ tự xử lý rất quan trọng.

Ví dụ:

~~~java
return repository.save(customer)
        .onErrorResume(DuplicateKeyException.class, error ->
                Mono.error(new EmailAlreadyRegisteredException(
                        customer.getEmail(), error)))
        .onErrorResume(DataIntegrityViolationException.class, error ->
                Mono.error(new InvalidCustomerDataException(error)))
        .onErrorResume(DataAccessException.class, error ->
                Mono.error(new CustomerPersistenceException(error)));
~~~

**DuplicateKeyException** là subtype của **DataIntegrityViolationException**, vì vậy nhánh cụ thể phải đứng trước nhánh tổng quát.

Không cần bắt tất cả exception ở mọi repository method. Nên đặt mapping tại service boundary nơi ứng dụng hiểu ý nghĩa nghiệp vụ của lỗi. Một lớp persistence adapter cũng có thể thực hiện chuyển đổi nếu muốn cô lập hoàn toàn chi tiết Spring DAO khỏi domain.

Nếu chỉ ghi log rồi ném lại cùng exception, dùng **doOnError** thường rõ hơn **onErrorResume(error -> Mono.error(error))**.

## 10. Xử lý lỗi toàn vẹn dữ liệu

Các constraint database bảo vệ dữ liệu ngay cả khi nhiều request chạy đồng thời hoặc có một đường ghi không đi qua service hiện tại.

Những lỗi phổ biến:

- Unique constraint: khóa hoặc giá trị duy nhất bị trùng.
- Foreign key constraint: tham chiếu tới hàng không tồn tại hoặc xóa hàng đang được tham chiếu.
- NOT NULL constraint: thiếu giá trị bắt buộc.
- Check constraint: giá trị không đáp ứng điều kiện.
- Data type/length constraint: kiểu hoặc độ dài dữ liệu không hợp lệ.

Spring thường chuyển các lỗi này thành **DataIntegrityViolationException** hoặc subtype cụ thể nếu translator nhận diện được.

Ví dụ xử lý lỗi duplicate:

~~~java
Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
            .onErrorMap(
                    DuplicateKeyException.class,
                    ex -> new EmailAlreadyRegisteredException(
                            customer.getEmail(), ex));
}
~~~

Đừng chỉ kiểm tra **existsByEmail** trước khi insert rồi cho rằng đã ngăn được duplicate. Hai request đồng thời đều có thể nhận false và cùng insert. Unique constraint vẫn là cơ chế bảo vệ cuối cùng; service chuyển lỗi constraint thành phản hồi nghiệp vụ phù hợp.

### 10.1. Xác định constraint nào bị vi phạm

Một **DataIntegrityViolationException** có thể đại diện cho nhiều constraint khác nhau. Không nên chuyển tất cả thành "email đã tồn tại".

Cách nhận diện có thể dựa trên:

- Exception subtype như **DuplicateKeyException**.
- SQLState/vendor code nếu được driver cung cấp.
- Tên constraint trong thông tin lỗi nếu database/driver cung cấp ổn định.
- Context của thao tác: câu lệnh đang ghi email, mã đơn hàng hay quan hệ foreign key.

Nếu phải phân tích vendor code hoặc constraint name, đặt logic đó trong adapter phụ thuộc database. Đừng để service domain rải rác mã SQLState riêng của nhiều database.

## 11. Xử lý lỗi SQL và lỗi sử dụng API

**BadSqlGrammarException** thường cho biết câu SQL sai cú pháp hoặc tham chiếu sai cấu trúc mà database không thể thực thi.

Nguyên nhân thường gặp:

- Tên bảng hoặc cột sai.
- Alias không khớp.
- Placeholder hoặc cách bind parameter không đúng dialect.
- Cú pháp SQL chỉ được hỗ trợ trên database khác.
- Câu lệnh được tạo động không hợp lệ.
- Truy vấn tham chiếu schema chưa tồn tại.

Đây thường là lỗi cần sửa code/query, không phải retry.

**InvalidDataAccessApiUsageException** có thể chỉ ra ứng dụng gọi API persistence sai hợp đồng, ví dụ truyền tham số không hợp lệ hoặc dùng một operation không hỗ trợ kiểu dữ liệu đó. Hãy xem cause và stack trace để xác định lỗi nằm ở query, mapping hay cách gọi API.

Không trả nguyên SQL hoặc thông tin schema nội bộ cho client cuối. Response API nên dùng thông điệp an toàn; chi tiết kỹ thuật chỉ dành cho log có kiểm soát.

## 12. Lỗi tài nguyên, timeout và tính transient

**DataAccessResourceFailureException**, **TransientDataAccessResourceException** hoặc **QueryTimeoutException** có thể liên quan tới:

- Database tạm thời không sẵn sàng.
- Connection pool hết connection.
- Mạng bị gián đoạn.
- Database quá tải.
- Statement hoặc transaction vượt timeout.
- Một số sự cố driver hoặc server tạm thời.

Không phải mọi lỗi trong nhóm này đều nên retry ngay. Trước khi retry, cần biết:

1. Lỗi có thực sự transient không?
2. Câu lệnh đã được database thực thi hay chưa?
3. Nếu client không nhận được kết quả, thao tác có thể đã commit hay chưa?
4. Retry có thể tạo tác dụng phụ trùng lặp không?
5. Database đang quá tải hay chỉ gặp một xung đột ngắn?

Ví dụ, một INSERT có thể đã commit ở database nhưng connection bị mất trước khi ứng dụng nhận xác nhận. Retry mù có thể tạo bản ghi trùng hoặc thực hiện nghiệp vụ hai lần. Dùng unique/idempotency key để bảo vệ các thao tác cần retry an toàn.

## 13. Retry lỗi transient trong reactive pipeline

Reactor cung cấp **retryWhen** để thử lại publisher khi lỗi thỏa điều kiện.

Ví dụ minh họa:

~~~java
return repository.findById(id)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isRetryableDataAccessFailure));
~~~

Hàm lọc nên nhận diện đúng nhóm lỗi có thể phục hồi:

~~~java
private boolean isRetryableDataAccessFailure(Throwable error) {
    return error instanceof TransientDataAccessException
            || error instanceof RecoverableDataAccessException;
}
~~~

Đây chỉ là ví dụ khung. Cần xác định những lỗi cụ thể có thể retry trong database và workload thực tế. **QueryTimeoutException** có thể là transient theo phân loại nhưng retry liên tục khi database đang quá tải có thể làm tình trạng tệ hơn.

### 13.1. Retry transaction ở đúng ranh giới

Nếu một use case gồm nhiều thao tác trong transaction, thường cần retry **toàn bộ transaction** để lần thử mới bắt đầu từ trạng thái database mới.

~~~java
Mono<TransferReceipt> work = performTransfer(command);

return transactionalOperator.transactional(work)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isRetryableDataAccessFailure));
~~~

Ở cách bố trí này, mỗi lần resubscribe có thể tạo một lần thực thi transaction mới qua **TransactionalOperator**. Tránh đặt retry bên trong transaction đã bị đánh dấu rollback-only rồi tiếp tục chạy lại một phần thao tác trong cùng transaction.

Retry toàn bộ work có nghĩa mọi thao tác bên trong publisher được thực thi lại. Vì vậy, các tác dụng phụ ngoài database như gửi email, gọi payment gateway hoặc phát message không nên được thực hiện trực tiếp trong transaction nếu không có cơ chế idempotency/outbox phù hợp.

### 13.2. Backoff, jitter và giới hạn retry

Một chiến lược retry cần:

- Số lần retry hữu hạn.
- Backoff để tránh dồn request trở lại cùng lúc.
- Jitter khi có nhiều client cạnh tranh cùng tài nguyên.
- Timeout tổng thể.
- Metric về số lần retry và nguyên nhân.
- Circuit breaker hoặc load shedding nếu hệ thống downstream đang mất khả năng phục vụ.

Không retry **BadSqlGrammarException**, **InvalidDataAccessApiUsageException** hoặc lỗi constraint không được xử lý. Các lỗi đó cần sửa query, code hoặc dữ liệu.

## 14. Optimistic locking và ConcurrencyFailureException

Spring Data Relational hỗ trợ optimistic locking thông qua property **@Version** trên entity. Khi hai transaction cùng đọc một entity, transaction đầu cập nhật version. Transaction sau cố lưu version cũ có thể nhận optimistic locking failure.

Ví dụ:

~~~java
@Table("inventory")
public class Inventory {

    @Id
    private Long id;

    private Integer available;

    @Version
    private Long version;
}
~~~

Khi lưu entity, Spring Data dùng version để phát hiện dữ liệu đã thay đổi. Nếu version không còn khớp, thao tác có thể phát **OptimisticLockingFailureException**, thuộc nhánh **ConcurrencyFailureException**.

Đây là xung đột nghiệp vụ có thể cần đọc lại dữ liệu và tính toán lại. Không nên bắt lỗi rồi gọi **save** lại cùng object cũ mà không tải version mới.

Ví dụ xử lý ở service:

~~~java
return inventoryRepository.findById(productId)
        .switchIfEmpty(Mono.error(
                new ProductNotFoundException(productId)))
        .flatMap(inventory -> {
            if (inventory.getAvailable() < quantity) {
                return Mono.error(new InsufficientStockException());
            }

            inventory.setAvailable(inventory.getAvailable() - quantity);
            return inventoryRepository.save(inventory);
        })
        .onErrorMap(
                OptimisticLockingFailureException.class,
                ex -> new InventoryChangedException(productId, ex));
~~~

Service có thể yêu cầu client thử lại với trạng thái mới hoặc tự thực hiện một vòng đọc-tính toán-ghi lại có giới hạn nếu nghiệp vụ cho phép.

## 15. Phân biệt lỗi truy cập dữ liệu và lỗi nghiệp vụ

Không nên để domain phụ thuộc toàn bộ vào **DataAccessException**. Đây là exception thuộc tầng Spring persistence.

Ví dụ chuyển lỗi:

| Lỗi persistence | Ý nghĩa nghiệp vụ có thể ánh xạ |
|---|---|
| **DuplicateKeyException** trên constraint email | Email đã được đăng ký |
| **DataIntegrityViolationException** do FK đơn hàng | Khách hàng hoặc sản phẩm không hợp lệ |
| **OptimisticLockingFailureException** | Dữ liệu đã được người khác cập nhật |
| **CannotAcquireLockException** | Tài nguyên đang bận; có thể yêu cầu thử lại |
| **QueryTimeoutException** | Hệ thống đang xử lý chậm; yêu cầu thử lại sau |
| **BadSqlGrammarException** | Lỗi triển khai; thường không ánh xạ thành lỗi người dùng cụ thể |
| **DataAccessResourceFailureException** | Database tạm thời không sẵn sàng |

Domain exception nên diễn đạt điều mà caller có thể hành động:

~~~java
public class InventoryChangedException extends RuntimeException {
    public InventoryChangedException(Long productId, Throwable cause) {
        super("Inventory changed; reload the latest quantity for product "
                + productId, cause);
    }
}
~~~

Không chuyển mọi lỗi database thành **IllegalArgumentException** hoặc HTTP 400. Lỗi SQL sai là lỗi hệ thống; client không thể sửa bằng cách đổi payload.

## 16. Ánh xạ exception thành HTTP response

Trong ứng dụng WebFlux, có thể dùng **@RestControllerAdvice** để ánh xạ domain exception thành status HTTP.

Ví dụ:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(EmailAlreadyRegisteredException.class)
    ResponseEntity<ApiError> handleDuplicateEmail(
            EmailAlreadyRegisteredException ex) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "EMAIL_ALREADY_REGISTERED",
                        "Email is already registered"));
    }

    @ExceptionHandler(CustomerNotFoundException.class)
    ResponseEntity<ApiError> handleNotFound(
            CustomerNotFoundException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "CUSTOMER_NOT_FOUND",
                        "Customer was not found"));
    }

    @ExceptionHandler(DataAccessResourceFailureException.class)
    ResponseEntity<ApiError> handleDatabaseUnavailable(
            DataAccessResourceFailureException ex) {

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ApiError(
                        "DATA_STORE_UNAVAILABLE",
                        "The data service is temporarily unavailable"));
    }
}
~~~

Đây là mẫu minh họa; kiểu **ApiError** và cách trả response có thể khác theo API. Trong nhiều ứng dụng, service đã chuyển exception persistence thành domain exception trước khi tới controller advice. Handler chỉ cần biết lỗi domain.

Không trả **ex.getMessage()** hoặc stack trace của lỗi database cho client. Những thông tin đó có thể chứa SQL, tên bảng, constraint, địa chỉ server hoặc dữ liệu đầu vào.

## 17. Exception translation khi dùng R2DBC SPI trực tiếp

Nếu code làm việc trực tiếp với **ConnectionFactory**, **Connection**, **Statement** và **Result**, lỗi có thể vẫn là exception từ R2DBC driver.

Ở tầng SPI trực tiếp, không giả định exception đã được dịch thành **DataAccessException** như khi dùng abstraction Spring. Cần quyết định một trong hai cách:

1. Để adapter persistence giữ nguyên lỗi driver và chuyển nó thành domain/persistence exception của ứng dụng.
2. Sử dụng exception translator của Spring R2DBC phù hợp với phiên bản đang dùng để chuẩn hóa lỗi.

Không tự viết một bảng ánh xạ vendor code rải rác trong service. Nếu cần xử lý SQLState hoặc mã lỗi riêng, cô lập trong một adapter theo driver/database.

Khi dùng SPI trực tiếp, vẫn phải quản lý connection cleanup trên success, error và cancellation. Exception translation không thay thế nghĩa vụ giải phóng tài nguyên.

## 18. Logging và quan sát lỗi

Một exception có thể chứa thông tin hữu ích để chẩn đoán:

- Exception class.
- Cause chain.
- SQLState hoặc vendor code.
- Tên constraint nếu database cung cấp.
- Tên operation/service.
- Trace ID hoặc request correlation ID.

Không nên log mọi bind value hoặc toàn bộ dữ liệu entity. Một số query có thể chứa email, số điện thoại, thông tin thanh toán hoặc token.

Nên ghi log ở một ranh giới có đủ ngữ cảnh để tránh cùng một lỗi bị log nhiều lần tại repository, service, controller và global handler.

Metric có thể phân loại theo nhóm exception ổn định, ví dụ:

- **data_integrity_violation**
- **query_timeout**
- **resource_failure**
- **concurrency_failure**
- **bad_sql_grammar**
- **uncategorized_r2dbc**

Tránh dùng message hoặc SQL động làm metric label vì cardinality cao và có thể làm lộ dữ liệu.

## 19. Các lỗi thường gặp khi dùng DataAccessException

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Bắt exception của một vendor ở service | Tầng nghiệp vụ phụ thuộc driver/database | Xử lý **DataAccessException** hoặc domain exception |
| Cho rằng mọi lỗi unique đều là **DuplicateKeyException** | Một số driver chỉ được dịch thành **DataIntegrityViolationException** | Kiểm tra exception thực tế trên driver mục tiêu |
| Coi **Mono.empty()** là database error | Trả sai trạng thái khi không có hàng | Dùng **switchIfEmpty** cho quy tắc not-found |
| Dùng try/catch quanh lời gọi tạo **Mono** | Không bắt được lỗi phát ra khi subscribe | Dùng **onErrorMap**, **onErrorResume**, **doOnError** |
| Chuyển mọi **DataAccessException** thành empty | Che mất lỗi SQL, kết nối và constraint | Chỉ phục hồi loại lỗi được hiểu rõ |
| Retry mọi exception | Lặp lỗi vĩnh viễn và tăng tải database | Retry có filter, backoff và giới hạn |
| Retry stale entity sau optimistic locking failure | Tiếp tục xung đột hoặc ghi sai nghiệp vụ | Đọc lại và tính toán lại |
| Nuốt lỗi bằng **onErrorResume** trong transaction | Transaction có thể commit nếu không rollback-only | Để lỗi truyền hoặc đánh dấu rollback-only |
| Dùng SQLState của một database như mã phổ quát | Sai khi đổi database/driver | Cô lập vendor-specific mapping |
| Trả thông điệp exception database cho client | Lộ SQL, schema hoặc thông tin nội bộ | Ánh xạ sang mã lỗi an toàn |
| Log bind parameter nhạy cảm | Rò rỉ dữ liệu cá nhân hoặc bí mật | Redact và log metadata cần thiết |
| Cho rằng SPI trực tiếp tự dịch exception | Tầng service nhận lỗi driver không đồng nhất | Dùng Spring abstraction hoặc translator/adaptor riêng |

## 20. Quy trình xử lý lỗi truy cập dữ liệu

Khi một publisher database phát lỗi, có thể đi theo trình tự:

1. Xác định exception thực tế và cause chain.
2. Xác định lỗi đã được Spring dịch thành **DataAccessException** hay vẫn là **R2dbcException** từ driver.
3. Phân loại lỗi là toàn vẹn dữ liệu, SQL/API usage, tài nguyên, timeout hay concurrency.
4. Kiểm tra lỗi có transient thật sự và thao tác có an toàn để retry không.
5. Nếu lỗi mang ý nghĩa nghiệp vụ, chuyển thành domain exception tại service boundary.
6. Nếu lỗi là sự cố hạ tầng, giữ tín hiệu lỗi để API/global handler trả status phù hợp.
7. Nếu đang trong transaction, bảo đảm lỗi không bị nuốt khiến transaction commit ngoài ý muốn.
8. Ghi log an toàn, giữ cause và correlation ID.
9. Kiểm thử trên đúng database/driver, vì translator có thể phân loại khác nhau.

Bảng quyết định tham khảo:

| Loại kết quả | Hành động |
|---|---|
| Publisher rỗng | Xử lý theo contract của use case |
| **DuplicateKeyException** | Chuyển thành lỗi domain về trùng dữ liệu |
| **DataIntegrityViolationException** | Xác định constraint và dữ liệu liên quan |
| **BadSqlGrammarException** | Sửa SQL hoặc mapping; không retry |
| **InvalidDataAccessApiUsageException** | Sửa cách gọi API hoặc tham số |
| **TransientDataAccessException** | Chỉ retry nếu operation idempotent và lỗi được chọn |
| **OptimisticLockingFailureException** | Đọc lại và tính toán lại hoặc trả conflict |
| **DataAccessResourceFailureException** | Kiểm tra database, network và connection pool |
| **UncategorizedR2dbcException** | Dùng cause/SQLState/vendor code để chẩn đoán, tránh đoán loại lỗi |

## 21. Kiểm thử exception translation

Unit test có thể xác nhận service chuyển exception Spring thành lỗi domain như mong muốn. Tuy nhiên, unit test mock **DuplicateKeyException** không chứng minh driver thực tế sẽ phát đúng exception đó.

Integration test nên chạy với database/driver mà ứng dụng sử dụng và kiểm tra:

- Insert duplicate unique key.
- Vi phạm foreign key.
- Vi phạm NOT NULL hoặc CHECK constraint.
- SQL sai cú pháp hoặc tên cột.
- Không tìm thấy hàng.
- Timeout hoặc lỗi kết nối nếu môi trường test hỗ trợ mô phỏng.
- Optimistic locking conflict với hai lần đọc/cập nhật cạnh tranh.

Ví dụ kiểm tra domain mapping:

~~~java
StepVerifier.create(customerService.register(customer))
        .expectError(EmailAlreadyRegisteredException.class)
        .verify();
~~~

Ví dụ kiểm tra repository thực tế:

~~~java
StepVerifier.create(customerRepository.save(duplicateCustomer))
        .expectError(DataIntegrityViolationException.class)
        .verify();
~~~

Loại exception chính xác trong integration test cần dựa trên hành vi thực tế của Spring, driver và database đang dùng. Nếu translator trả về subtype cụ thể, có thể kiểm tra subtype đó; nếu không, kiểm tra lớp cha phù hợp và xác nhận cause/SQLState khi cần.

Không viết test chỉ khẳng định mọi lỗi đều là **DataAccessException**. Cần kiểm tra những contract quan trọng mà service dựa vào, đặc biệt là sự phân biệt giữa empty, lỗi dữ liệu và lỗi hạ tầng.

## 22. Ghi nhớ

- **DataAccessException** là hệ exception unchecked của Spring để chuẩn hóa lỗi truy cập dữ liệu.
- Spring dịch nhiều lỗi **R2dbcException** của driver thành các nhóm **DataAccessException** có ý nghĩa chung.
- **NonTransientDataAccessException** thường cần sửa SQL, dữ liệu, quyền hoặc code; retry cùng thao tác hiếm khi giải quyết được.
- **TransientDataAccessException** có thể phục hồi, nhưng retry phải có filter, backoff, giới hạn và bảo đảm idempotency.
- **DataIntegrityViolationException** bao quát lỗi toàn vẹn; **DuplicateKeyException** là subtype cụ thể khi translator nhận diện duplicate.
- **BadSqlGrammarException**, **QueryTimeoutException**, **ConcurrencyFailureException** và **OptimisticLockingFailureException** mô tả các nhóm lỗi khác nhau và cần cách xử lý riêng.
- Mã SQLState/vendor code và exception subtype phụ thuộc database/driver; không dùng mã riêng của một database như chuẩn chung.
- Repository, **R2dbcEntityTemplate** và **DatabaseClient** có cơ chế Spring exception translation; R2DBC SPI trực tiếp có thể để lộ exception driver.
- **Mono.empty()** và **Flux.empty()** là kết quả không có dữ liệu, không phải **DataAccessException**.
- Lỗi reactive thường xuất hiện khi subscribe; dùng **doOnError**, **onErrorMap** và **onErrorResume** thay cho try/catch quanh lời gọi tạo publisher.
- Bắt subtype cụ thể trước lớp cha; chỉ chuyển lỗi persistence thành domain exception khi tầng nghiệp vụ hiểu được ý nghĩa.
- Không nuốt lỗi trong transaction nếu chưa quyết định rõ commit hay rollback.
- Retry toàn bộ transaction ở ranh giới phù hợp; không lặp tác dụng phụ ngoài database nếu thiếu idempotency hoặc outbox.
- Không trả SQL, stack trace, vendor code hoặc bind value nhạy cảm cho client.
- Dùng integration test trên đúng database/driver để xác nhận exception translation và hành vi thực tế.

