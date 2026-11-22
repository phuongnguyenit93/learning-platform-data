# DataAccessException và cơ chế chuyển đổi ngoại lệ của Spring

Spring cung cấp `DataAccessException` để ứng dụng xử lý lỗi truy cập dữ liệu theo một hệ phân cấp thống nhất, ít phụ thuộc vào JDBC driver hoặc JPA provider. Thay vì để service phải hiểu `SQLException`, `SQLIntegrityConstraintViolationException` hay exception riêng của Hibernate, Spring có thể chuyển các lỗi công nghệ cụ thể thành các loại exception thuộc Spring DAO.

Cơ chế này thường được gọi là *exception translation*. Nó giúp tầng nghiệp vụ nhận diện nhóm lỗi như vi phạm ràng buộc, sai cú pháp SQL, lỗi khóa đồng thời hoặc lỗi tài nguyên dữ liệu bằng các kiểu exception nhất quán.

Cần phân biệt ba việc: database/provider phát sinh lỗi gốc; Spring nhận diện và chuyển lỗi ở ranh giới truy cập dữ liệu; service quyết định phản hồi nghiệp vụ, rollback hoặc thử lại. Exception translation không tự sửa dữ liệu, không tự retry và cũng không bảo đảm mọi exception đều được chuyển đổi.

## 1. DataAccessException là gì?

`DataAccessException` thuộc package `org.springframework.dao`. Đây là lớp cơ sở cho các lỗi truy cập dữ liệu mà Spring chuẩn hóa. Nó là unchecked exception, kế thừa từ `NestedRuntimeException`, nên không buộc phương thức phải khai báo `throws` hoặc bắt exception.

Các lợi ích chính:

- Giảm sự phụ thuộc của service vào JDBC, JPA provider và database vendor.
- Cung cấp các loại lỗi có ý nghĩa như vi phạm dữ liệu, sai cách sử dụng API, lỗi tài nguyên và lỗi đồng thời.
- Giữ exception gốc làm cause để có thể điều tra chi tiết.
- Cho phép chính sách xử lý lỗi ở tầng service dựa trên loại lỗi thay vì phân tích thông báo SQL riêng của từng driver.

Ví dụ, một unique constraint có thể được báo bởi database bằng mã lỗi hoặc SQLState riêng. Spring có thể chuyển lỗi đó thành `DuplicateKeyException` hoặc một `DataIntegrityViolationException` phù hợp. Service có thể xử lý theo hợp đồng Spring mà không cần biết mã lỗi của PostgreSQL, MySQL hay một driver cụ thể.

Không nên hiểu `DataAccessException` là một loại lỗi duy nhất. Đây là một hệ phân cấp gồm nhiều nhóm con; cần chọn loại cụ thể phù hợp với chính sách xử lý.

## 2. Các nhóm exception thường gặp

Hệ phân cấp Spring DAO có nhiều lớp. Những nhóm dưới đây thường hữu ích khi làm việc với Spring Data JPA và JDBC.

| Nhóm hoặc kiểu | Ý nghĩa thường gặp | Cách xem xét xử lý |
|---|---|---|
| `DataIntegrityViolationException` | Vi phạm constraint, dữ liệu không hợp lệ theo schema | Kiểm tra dữ liệu đầu vào và quy tắc nghiệp vụ |
| `DuplicateKeyException` | Vi phạm khóa duy nhất hoặc khóa chính | Có thể chuyển thành kết quả trùng dữ liệu nếu nghiệp vụ cho phép |
| `BadSqlGrammarException` | SQL sai cú pháp hoặc tham chiếu đối tượng không hợp lệ | Sửa query, tên bảng/cột hoặc mapping |
| `InvalidDataAccessResourceUsageException` | Sử dụng tài nguyên dữ liệu hoặc câu lệnh không đúng | Kiểm tra query và cách gọi API |
| `EmptyResultDataAccessException` | Kết quả truy vấn không có hàng trong trường hợp API mong đợi có kết quả | Xem lại hợp đồng truy vấn và cách xử lý không tìm thấy |
| `IncorrectResultSizeDataAccessException` | Số kết quả khác số lượng mong đợi | Kiểm tra điều kiện lọc và tính duy nhất |
| `OptimisticLockingFailureException` | Cập nhật thất bại do xung đột optimistic locking | Đọc lại dữ liệu và xử lý xung đột theo nghiệp vụ |
| `PessimisticLockingFailureException` | Thao tác khóa bi quan thất bại | Xem xét lock timeout, deadlock và thứ tự khóa |
| `CannotAcquireLockException` | Không lấy được lock cần thiết | Có thể cần retry có giới hạn nếu thao tác an toàn |
| `QueryTimeoutException` | Truy vấn vượt thời gian cho phép | Kiểm tra query plan, tải database và timeout |
| `DataAccessResourceFailureException` | Không truy cập được tài nguyên dữ liệu | Kiểm tra kết nối, database và hạ tầng |

Tên exception chỉ mô tả loại lỗi được Spring nhận diện; cách xử lý vẫn phụ thuộc nguyên nhân và ngữ cảnh. Ví dụ, `DataIntegrityViolationException` có thể đến từ unique constraint, foreign key, not-null hoặc check constraint. Không nên tự động chuyển mọi trường hợp thành thông báo “dữ liệu đã tồn tại”.

### Transient và non-transient

Một cách phân loại quan trọng là lỗi có khả năng tạm thời hay không:

- `TransientDataAccessException`: lỗi có thể biến mất nếu thử lại sau một khoảng thời gian hoặc khi điều kiện hệ thống thay đổi.
- `NonTransientDataAccessException`: lỗi thường không thể khắc phục chỉ bằng cách lặp lại cùng thao tác với cùng dữ liệu.
- `RecoverableDataAccessException`: lỗi có thể phục hồi bằng cách thực hiện một số bước khôi phục phù hợp trước khi thử lại.

Ví dụ, deadlock hoặc lock contention có thể là lỗi tạm thời. Một câu SQL sai cú pháp hoặc dữ liệu vi phạm unique constraint thường không được giải quyết bằng retry nguyên trạng.

Đây là phân loại hướng dẫn, không phải lời hứa rằng mọi exception thuộc nhóm transient chắc chắn retry sẽ thành công. Trước khi retry, cần đánh giá tính idempotent, transaction boundary, trạng thái dữ liệu và khả năng database đã thực hiện một phần thao tác.

## 3. Vì sao Spring cần exception translation?

Mỗi công nghệ truy cập dữ liệu có cách biểu diễn lỗi riêng:

- JDBC sử dụng `SQLException` cùng SQLState, vendor error code và thông tin driver.
- JPA định nghĩa các exception như `PersistenceException`, `EntityExistsException`, `OptimisticLockException` và `LockTimeoutException`.
- Hibernate có các exception riêng cho constraint, stale state, query và session.
- Các thư viện truy cập dữ liệu khác cũng có hệ exception riêng.

Nếu service phụ thuộc trực tiếp vào tất cả các kiểu đó, việc thay provider hoặc database sẽ làm tăng chi phí thay đổi và tạo ra nhiều nhánh xử lý vendor-specific.

Spring chuẩn hóa lỗi ở ranh giới repository/DAO. Service có thể nhận một exception thuộc Spring DAO, xử lý theo chính sách chung và vẫn truy cập nguyên nhân gốc khi cần chẩn đoán.

Mô hình khái quát:

~~~text
Service
   |
   v
Repository / DAO
   |
   v
JDBC, JPA provider hoặc Hibernate
   |
   v
Database / JDBC driver
   |
   | lỗi gốc
   v
Exception translator của Spring
   |
   v
DataAccessException (nếu nhận diện và chuyển đổi được)
   |
   v
Service xử lý theo nghiệp vụ
~~~

Nếu Spring không có translator phù hợp hoặc exception không thuộc phạm vi được xử lý, exception gốc hoặc một exception khác có thể được truyền ra. Vì vậy, không nên giả định mọi lỗi phát sinh trong toàn bộ ứng dụng đều trở thành `DataAccessException`.

## 4. Chuyển đổi SQLException trong JDBC

Với `JdbcTemplate`, ứng dụng không cần tự viết vòng lặp bắt `SQLException` cho từng câu lệnh. `JdbcTemplate` quản lý tài nguyên JDBC, thực thi callback và chuyển lỗi SQL sang hệ exception của Spring.

Ví dụ repository:

~~~java
@Repository
@RequiredArgsConstructor
public class CustomerJdbcRepository {
    private final JdbcTemplate jdbcTemplate;

    public int insert(String email, String name) {
        String sql = """
            insert into customer(email, name)
            values (?, ?)
            """;

        return jdbcTemplate.update(sql, email, name);
    }
}
~~~

Nếu database từ chối insert vì unique constraint, `JdbcTemplate` sử dụng `SQLExceptionTranslator` để phân loại lỗi và ném một `DataAccessException` phù hợp. Service gọi repository có thể bắt `DuplicateKeyException` hoặc kiểu cha phù hợp.

### SQLExceptionTranslator hoạt động ra sao?

Spring JDBC cung cấp cơ chế dịch `SQLException` dựa trên thông tin database. Các translator có thể sử dụng:

- SQLState do driver cung cấp.
- Vendor error code của database.
- Quy tắc ánh xạ lỗi đã biết trong Spring.
- Nguyên nhân gốc và thông tin câu lệnh liên quan.

`SQLErrorCodeSQLExceptionTranslator` dùng bộ mã lỗi theo vendor để nhận diện nhiều trường hợp cụ thể. `SQLStateSQLExceptionTranslator` phân loại dựa trên SQLState. Cấu hình thực tế phụ thuộc phiên bản Spring, database metadata và translator được sử dụng.

Ví dụ minh họa xử lý:

~~~java
@Service
@RequiredArgsConstructor
public class RegistrationService {
    private final CustomerJdbcRepository customerRepository;

    public void register(String email, String name) {
        try {
            customerRepository.insert(email, name);
        } catch (DuplicateKeyException ex) {
            throw new EmailAlreadyRegisteredException(email, ex);
        }
    }
}
~~~

`EmailAlreadyRegisteredException` ở đây là exception nghiệp vụ do ứng dụng định nghĩa. Service chuyển lỗi persistence thành ý nghĩa mà API hoặc use case cần hiểu, đồng thời giữ cause để điều tra.

Không nên bắt `SQLException` ở tầng service khi repository đã dùng `JdbcTemplate`. Exception đó đã được Spring xử lý ở tầng JDBC và được chuyển thành unchecked exception.

## 5. Chuyển đổi exception trong JPA và Spring Data JPA

JPA provider có thể ném exception theo chuẩn Jakarta Persistence hoặc theo implementation như Hibernate. Spring cung cấp cơ chế persistence exception translation để chuyển các lỗi đã nhận diện thành exception thuộc `org.springframework.dao`.

### Vai trò của @Repository

`@Repository` là stereotype cho lớp truy cập dữ liệu. Ngoài vai trò component scanning, annotation này còn là điểm nhận diện cho cơ chế persistence exception translation của Spring.

Trong cấu hình Spring thông thường, `PersistenceExceptionTranslationPostProcessor` có thể tạo proxy/advisor cho bean `@Repository`. Advisor này dùng các `PersistenceExceptionTranslator` được cấu hình để chuyển exception của persistence provider sang hệ Spring DAO.

Với Spring Boot và Spring Data JPA, hạ tầng repository thường được tự động cấu hình. Spring Data repository proxy cũng tích hợp exception translation, nên ứng dụng thường nhận được các exception Spring DAO khi lỗi được nhận diện.

Ví dụ repository:

~~~java
@Repository
public interface AccountRepository extends JpaRepository<Account, Long> {
    Optional<Account> findByEmail(String email);
}
~~~

Trong nhiều dự án Spring Data JPA, có thể bỏ `@Repository` trên interface vì việc đăng ký repository đã được thực hiện bởi `@EnableJpaRepositories` hoặc auto-configuration. Annotation không phải điều kiện duy nhất để repository proxy được quản lý.

### Ví dụ với EntityManager

Một DAO tự viết có thể dùng `EntityManager`:

~~~java
@Repository
public class AccountDao {
    @PersistenceContext
    private EntityManager entityManager;

    public void persist(Account account) {
        entityManager.persist(account);
        entityManager.flush();
    }
}
~~~

Khi `flush()` buộc provider gửi SQL xuống database, lỗi constraint hoặc lỗi persistence có thể xuất hiện tại đây. Nếu DAO nằm trong phạm vi exception translation, Spring có thể chuyển exception provider thành `DataAccessException` tương ứng.

Việc gọi `flush()` trong ví dụ chỉ nhằm minh họa thời điểm lỗi có thể xuất hiện; không phải mọi thao tác persist đều cần flush ngay. JPA có thể trì hoãn SQL đến flush tự động hoặc commit transaction.

### Exception translation không đồng nghĩa với @Transactional

Hai cơ chế này có nhiệm vụ khác nhau:

- Exception translation chuẩn hóa loại exception phát sinh từ tầng truy cập dữ liệu.
- `@Transactional` xác định ranh giới và chính sách transaction như bắt đầu, tham gia, commit hoặc rollback.

Một phương thức có thể vừa được quản lý transaction vừa nằm trong repository exception translation, nhưng annotation transaction không tự chuyển mọi exception thành `DataAccessException`. Ngược lại, exception translation cũng không tự tạo transaction nếu không có cấu hình transaction phù hợp.

## 6. Thời điểm lỗi xuất hiện: persist, flush và commit

Một lỗi dữ liệu có thể không xuất hiện ngay tại dòng gọi `save()` hoặc `persist()`. JPA thường quản lý thay đổi trong persistence context rồi đồng bộ xuống database tại thời điểm flush.

Ví dụ:

~~~java
@Transactional
public void createAccount(Account account) {
    accountRepository.save(account);
    // Lỗi constraint có thể chỉ xuất hiện khi flush hoặc commit.
}
~~~

Nếu email bị trùng, lỗi có thể xuất hiện ở một trong các thời điểm:

1. Khi provider thực thi SQL ngay trong thao tác lưu, tùy chiến lược ID và provider.
2. Khi gọi `flush()` rõ ràng.
3. Khi transaction commit và persistence context được flush tự động.

Điều này ảnh hưởng đến nơi bắt exception. Một khối `try/catch` chỉ bao quanh lời gọi `save()` có thể không bắt được lỗi xảy ra sau đó ở commit của transaction interceptor.

Nếu cần xử lý lỗi tại service, phải hiểu transaction boundary và thời điểm flush/commit. Có thể chủ động flush ở vị trí cần xác nhận constraint sớm, nhưng flush không phải commit và không bảo đảm mọi lỗi commit đều xuất hiện trước đó.

## 7. Xử lý DataAccessException ở tầng service

Repository/DAO nên tập trung vào thao tác dữ liệu. Service hiểu ngữ cảnh nghiệp vụ và quyết định exception nào cần chuyển thành kết quả hoặc lỗi nghiệp vụ.

Ví dụ:

~~~java
@Service
@RequiredArgsConstructor
public class AccountRegistrationService {
    private final AccountRepository accountRepository;

    @Transactional
    public Account register(String email) {
        if (accountRepository.findByEmail(email).isPresent()) {
            throw new EmailAlreadyRegisteredException(email);
        }

        Account account = new Account(email);

        try {
            return accountRepository.saveAndFlush(account);
        } catch (DataIntegrityViolationException ex) {
            throw new EmailAlreadyRegisteredException(email, ex);
        }
    }
}
~~~

Ví dụ trên có hai lớp bảo vệ:

- Kiểm tra trước để trả phản hồi sớm cho trường hợp đã tồn tại.
- Dựa vào constraint ở database để xử lý trường hợp hai request cùng vượt qua bước kiểm tra rồi cùng insert.

Chỉ kiểm tra `findByEmail()` trước insert không đủ bảo đảm uniqueness khi có concurrency. Unique constraint ở database mới là lớp bảo vệ cuối cùng. Khi vi phạm constraint, Spring có thể chuyển lỗi thành `DataIntegrityViolationException`; service chuyển nó thành exception nghiệp vụ phù hợp.

Trong ví dụ, `saveAndFlush()` giúp lỗi constraint xuất hiện ngay trong khối `try` trong nhiều tình huống. Tuy vậy, cần kiểm tra chính sách transaction của ứng dụng: transaction có thể đã bị đánh dấu rollback-only và không thể tiếp tục ghi thêm dữ liệu sau lỗi.

### Không bắt DataAccessException một cách mù quáng

Tránh viết:

~~~java
try {
    repository.save(entity);
} catch (DataAccessException ex) {
    return null;
}
~~~

Cách này làm mất thông tin lỗi và có thể khiến caller tưởng thao tác thành công. Nếu không thể xử lý tại chỗ, hãy để exception truyền lên nơi có đủ ngữ cảnh. Nếu cần chuyển đổi, giữ nguyên cause:

~~~java
catch (DataAccessException ex) {
    throw new OrderPersistenceException("Không thể lưu đơn hàng", ex);
}
~~~

Không nên bắt `Exception` hoặc `RuntimeException` quá rộng rồi chuyển tất cả thành một lỗi “database unavailable”. Lỗi cú pháp query, vi phạm dữ liệu, deadlock và mất kết nối có nguyên nhân cũng như chính sách xử lý khác nhau.

## 8. DataAccessException và rollback transaction

`DataAccessException` là unchecked exception. Theo quy tắc mặc định của Spring transaction, khi một `RuntimeException` hoặc `Error` thoát khỏi phương thức được quản lý transaction, Spring đánh dấu rollback và rollback transaction phù hợp.

Điều đó có nghĩa lỗi truy cập dữ liệu được Spring chuyển thành `DataAccessException` thường kích hoạt rollback mặc định nếu nó thoát khỏi ranh giới transaction.

Tuy nhiên:

- Nếu service bắt exception rồi trả về bình thường, interceptor bên ngoài có thể không nhìn thấy exception để áp dụng rollback rule.
- Provider hoặc database có thể đã đánh dấu transaction rollback-only trước khi exception bị bắt; việc nuốt exception không làm transaction trở lại trạng thái có thể commit.
- Nếu transaction bên trong tham gia transaction bên ngoài và đánh dấu rollback-only, transaction ngoài có thể gặp `UnexpectedRollbackException` khi commit.
- Nếu exception được chuyển thành checked exception, cần xem lại rollback rule; checked exception không rollback mặc định trừ khi được cấu hình.

Ví dụ không nên nuốt lỗi khi dữ liệu cần được rollback:

~~~java
@Transactional
public void transfer(Long fromId, Long toId, BigDecimal amount) {
    try {
        accountRepository.debit(fromId, amount);
        accountRepository.credit(toId, amount);
    } catch (DataAccessException ex) {
        log.error("Không thể hoàn tất chuyển tiền", ex);
        throw ex;
    }
}
~~~

Việc ném lại exception cho transaction interceptor biết thao tác thất bại. Nếu cần chuyển sang exception nghiệp vụ, hãy bảo đảm exception mới vẫn kích hoạt rollback theo chính sách đã cấu hình, hoặc khai báo `rollbackFor` nếu exception mới là checked.

## 9. Có nên retry DataAccessException không?

Không phải mọi `DataAccessException` đều có thể giải quyết bằng retry.

**Có thể xem xét retry** khi lỗi được phân loại là tạm thời, chẳng hạn deadlock, lock contention hoặc một số lỗi kết nối có thể phục hồi. Cần dùng số lần thử giới hạn, khoảng chờ tăng dần và jitter khi thích hợp.

**Không nên retry nguyên trạng** khi lỗi là:

- SQL sai cú pháp hoặc mapping sai.
- Vi phạm unique, foreign key, not-null hoặc check constraint do dữ liệu đầu vào.
- Dùng sai API truy cập dữ liệu.
- Kết quả truy vấn không đúng số lượng mong đợi.
- Optimistic locking conflict mà nghiệp vụ chưa đọc lại và hợp nhất thay đổi.

Khi retry, cần chú ý:

1. Thao tác có idempotent không? Nếu lần đầu đã ghi thành công nhưng response bị mất, retry có thể tạo bản ghi hoặc giao dịch trùng.
2. Transaction trước đã rollback hoàn toàn chưa? Không tiếp tục sử dụng transaction đã bị đánh dấu rollback-only.
3. Mỗi lần thử có transaction mới phù hợp không? Retry nên bao quanh lời gọi tạo transaction, thay vì lặp lại bên trong cùng một transaction đã hỏng.
4. Có giới hạn số lần thử và tổng thời gian chờ không?
5. Có log đủ cause, SQLState/vendor code và correlation ID mà không làm lộ dữ liệu nhạy cảm không?

Nếu dùng Spring Retry hoặc `RetryTemplate`, hãy cấu hình retry theo loại lỗi cụ thể và bảo đảm transaction boundary được tạo lại cho từng lần thử. Không nên gắn `@Retryable` cho toàn bộ `DataAccessException` mà không phân loại.

## 10. Giữ nguyên nguyên nhân gốc để chẩn đoán

Khi exception translation xảy ra, exception Spring thường giữ exception gốc trong cause chain. Thông tin này rất quan trọng vì `DataAccessException` cung cấp ngữ nghĩa chung, còn cause có thể chứa SQLState, vendor error code, constraint name hoặc thông tin driver.

Khi ghi log, nên giữ toàn bộ exception:

~~~java
try {
    repository.saveAndFlush(entity);
} catch (DataAccessException ex) {
    log.error("Lưu entity thất bại, entityId={}", entity.getId(), ex);
    throw ex;
}
~~~

Không nên chỉ ghi `ex.getMessage()` rồi bỏ cause. Thông báo có thể không đủ để xác định lỗi đến từ constraint, kết nối, timeout hay query.

Khi cần chẩn đoán sâu hơn, có thể xem:

- Kiểu `DataAccessException` cụ thể.
- `ex.getCause()` và chuỗi cause lồng nhau.
- SQLState hoặc vendor error code nếu cause là `SQLException`.
- Tên constraint hoặc đối tượng database liên quan.
- Query/operation, transaction boundary và thời điểm lỗi xuất hiện.
- Correlation ID và ngữ cảnh request phù hợp.

Không ghi mật khẩu, token, dữ liệu cá nhân hoặc toàn bộ giá trị bind nhạy cảm vào log. Việc bật log SQL/bind parameter cần được cân nhắc theo môi trường và chính sách bảo vệ dữ liệu.

## 11. Kiểm thử exception translation

Test nên kiểm tra loại exception ở đúng ranh giới ứng dụng. Có thể dùng integration test với database kiểm thử để tạo lỗi thật, thay vì chỉ mock repository và tự ném một exception.

Ví dụ kiểm tra unique constraint:

~~~java
@DataJpaTest
class AccountRepositoryExceptionTest {

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void duplicateEmailIsRejected() {
        accountRepository.saveAndFlush(new Account("a@example.com"));

        assertThatThrownBy(() ->
                accountRepository.saveAndFlush(new Account("a@example.com")))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
~~~

Ví dụ giả định entity có constructor nhận email và database schema có unique constraint trên cột email. Loại exception chính xác phụ thuộc database, provider và cấu hình translator; vì vậy hãy xác nhận kiểu mà ứng dụng thực tế nhận được trong môi trường kiểm thử đã chọn.

Các hướng kiểm thử hữu ích:

- Tạo dữ liệu vi phạm unique hoặc foreign key để kiểm tra exception translation.
- Gọi `flush()` khi muốn buộc lỗi constraint xuất hiện trong test.
- Kiểm tra cause chain nếu cần bảo đảm thông tin gốc được giữ.
- Kiểm tra transaction rollback bằng cách đọc lại database sau khi transaction kết thúc.
- Kiểm tra exception nghiệp vụ do service chuyển đổi có giữ cause và đúng API contract.
- Với lỗi phụ thuộc engine, chạy test trên database production-compatible bằng Testcontainers.

H2 có thể phù hợp cho test nhanh, nhưng mapping lỗi cụ thể và vendor error code có thể khác database triển khai. Với native SQL, constraint hoặc hành vi cần khớp production, hãy chạy test trên cùng engine và phiên bản tương ứng.

## 12. Các lỗi thiết kế thường gặp

| Cách làm chưa tốt | Rủi ro | Cách xử lý |
|---|---|---|
| Bắt `SQLException` ở service dùng `JdbcTemplate` | Service phụ thuộc JDBC driver và bỏ qua lớp dịch của Spring | Bắt `DataAccessException` phù hợp |
| Bắt mọi `DataAccessException` rồi trả `null` | Mất thông tin thất bại, caller khó phân biệt | Ném lại hoặc chuyển thành lỗi nghiệp vụ có cause |
| Chỉ kiểm tra tồn tại trước khi insert | Hai request đồng thời vẫn có thể tạo dữ liệu trùng | Dùng unique constraint và xử lý lỗi khi insert |
| Retry mọi lỗi database | Lặp lại lỗi vĩnh viễn và tăng tải database | Chỉ retry lỗi transient đã xác định |
| Bắt lỗi quanh `save()` nhưng không tính đến flush/commit | Bỏ sót lỗi xuất hiện muộn | Hiểu transaction boundary và cân nhắc flush |
| Dùng exception message để phân loại | Message phụ thuộc vendor, locale và phiên bản | Dựa vào kiểu exception, cause, SQLState hoặc mã lỗi |
| Chuyển lỗi sang exception nghiệp vụ nhưng bỏ cause | Mất bằng chứng điều tra | Giữ cause trong constructor exception |
| Dùng H2 để khẳng định mapping lỗi production | Mã lỗi và translator có thể khác | Test trên database triển khai |

## 13. Checklist khi xử lý lỗi truy cập dữ liệu

Trước khi hoàn thiện luồng xử lý, hãy kiểm tra:

1. Lỗi xuất phát từ JDBC, JPA provider, Hibernate hay transaction manager?
2. Spring đã chuyển lỗi thành `DataAccessException` chưa? Kiểu cụ thể là gì?
3. Cause chain có giữ SQLState, vendor code hoặc tên constraint cần thiết không?
4. Lỗi là transient, non-transient hay recoverable?
5. Service có cần chuyển lỗi thành exception nghiệp vụ hoặc HTTP response không?
6. Exception có đi qua transaction boundary để rollback đúng chính sách không?
7. Nếu retry, thao tác có idempotent và mỗi lần thử có transaction phù hợp không?
8. Lỗi có chỉ xuất hiện ở flush hoặc commit không?
9. Test đã xác nhận cả exception, trạng thái dữ liệu và engine cần hỗ trợ chưa?
10. Log có đủ thông tin chẩn đoán nhưng không làm lộ dữ liệu nhạy cảm không?

## Kết luận

`DataAccessException` là abstraction unchecked của Spring giúp chuẩn hóa lỗi truy cập dữ liệu từ JDBC, JPA và các persistence provider. JDBC template dùng `SQLExceptionTranslator`; Spring repository/DAO có thể dùng persistence exception translation để chuyển lỗi provider thành các kiểu Spring DAO. Service nên xử lý theo loại lỗi và ngữ cảnh nghiệp vụ, giữ cause khi chuyển đổi, chỉ retry lỗi tạm thời có thể phục hồi và hiểu rõ tác động đến transaction. Khi kiểm thử các lỗi phụ thuộc database, hãy xác minh trên đúng engine triển khai thay vì dựa hoàn toàn vào H2.