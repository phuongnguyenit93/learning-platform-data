# Kiểm tra tồn tại trước khi ghi và cuộc đua dữ liệu đồng thời

Trong ứng dụng Spring Data JPA, một luồng thường gặp là kiểm tra bản ghi đã tồn tại hay chưa rồi mới insert. Ví dụ, đăng ký tài khoản bằng email: service gọi `existsByEmail(email)`; nếu chưa có thì tạo entity và gọi `save()`.

Cách làm này hữu ích để phản hồi sớm, nhưng không bảo đảm dữ liệu duy nhất khi có nhiều request chạy đồng thời. Giữa lần kiểm tra và lần ghi có một khoảng thời gian mà transaction khác có thể insert cùng dữ liệu. Đây là lỗi *time-of-check to time-of-use* (TOCTOU), thường gọi là race condition.

Quy tắc quan trọng là: kiểm tra trước khi ghi cải thiện trải nghiệm và tránh thao tác thừa; constraint ở database mới là hàng rào bảo đảm tính duy nhất. Service phải xử lý trường hợp hai request cùng vượt qua bước kiểm tra và một request bị database từ chối.

## 1. Luồng kiểm tra tồn tại thông thường

Spring Data JPA hỗ trợ derived query để kiểm tra một bản ghi có thỏa điều kiện hay không. Ví dụ:

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {
    boolean existsByEmail(String email);
}
~~~

Service có thể dùng phương thức đó trước khi lưu:

~~~java
@Service
@RequiredArgsConstructor
public class AccountService {
    private final AccountRepository accountRepository;

    @Transactional
    public Account register(String email) {
        if (accountRepository.existsByEmail(email)) {
            throw new EmailAlreadyRegisteredException(email);
        }

        return accountRepository.save(new Account(email));
    }
}
~~~

Cách này có ưu điểm:

- Có thể trả lỗi nghiệp vụ sớm khi dữ liệu đã tồn tại tại thời điểm kiểm tra.
- Không cần tạo entity hoặc gửi insert nếu đã biết chắc có bản ghi trùng.
- Ý định nghiệp vụ dễ đọc.
- Có thể dùng cùng unique constraint để xử lý trường hợp cạnh tranh.

Tuy nhiên, `existsByEmail()` chỉ trả lời câu hỏi tại thời điểm câu query được thực thi. Nó không giữ chỗ cho email đó và không khóa một bản ghi chưa tồn tại. Do đó, đoạn code trên vẫn có race condition.

## 2. Race condition xảy ra như thế nào?

Giả sử database hiện chưa có email `a@example.com`. Hai request A và B đến gần như cùng lúc:

~~~text
Request A                         Request B
---------                         ---------
existsByEmail() -> false
                                  existsByEmail() -> false
save(account A)
                                  save(account B)
commit thành công
                                  insert bị unique constraint từ chối
~~~

Cả hai request đều đọc được kết quả “chưa tồn tại”. Nếu database không có unique constraint, cả hai có thể commit và tạo hai tài khoản cùng email.

Nếu có unique constraint, database chỉ cho phép một transaction tạo giá trị đó. Transaction còn lại thất bại khi insert hoặc khi flush/commit. Đây là hành vi cần thiết để bảo vệ invariant dữ liệu ngay cả khi nhiều ứng dụng hoặc nhiều instance cùng ghi.

Khoảng thời gian từ lúc kiểm tra đến lúc sử dụng kết quả chính là TOCTOU:

1. Tại thời điểm kiểm tra, email chưa tồn tại.
2. Transaction khác insert email đó.
3. Request ban đầu vẫn tiếp tục dựa trên kết quả kiểm tra cũ.
4. Database quyết định thao tác ghi có hợp lệ hay không.

Không thể khắc phục race condition chỉ bằng cách gọi `existsByEmail()` nhiều lần. Một request khác vẫn có thể ghi ngay sau lần kiểm tra cuối cùng.

## 3. Đặt unique constraint ở database

Nếu email phải duy nhất, hãy khai báo invariant đó trong schema. Có thể dùng annotation JPA:

~~~java
@Entity
@Table(
    name = "account",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_account_email",
            columnNames = "email"
        )
    }
)
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 320)
    private String email;

    protected Account() {
    }

    public Account(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Annotation `@UniqueConstraint` mô tả constraint trong schema được tạo từ mapping. Với hệ thống production dùng Flyway hoặc Liquibase, cần tạo và quản lý unique constraint bằng migration để schema thực tế được bảo đảm.

Ví dụ migration SQL:

~~~sql
ALTER TABLE account
    ADD CONSTRAINT uk_account_email UNIQUE (email);
~~~

Tên cú pháp migration và cách xử lý dữ liệu trùng hiện có phụ thuộc database. Trước khi thêm constraint, cần tìm và xử lý các hàng trùng; nếu không, migration có thể thất bại.

Một unique constraint có thể bao gồm nhiều cột. Ví dụ email chỉ cần duy nhất trong từng tenant:

~~~sql
ALTER TABLE account
    ADD CONSTRAINT uk_account_tenant_email
    UNIQUE (tenant_id, email);
~~~

Khi đó, cùng một email có thể xuất hiện ở hai tenant khác nhau nhưng không được trùng trong cùng tenant. Quy tắc constraint phải phản ánh chính xác phạm vi duy nhất của nghiệp vụ.

### Unique constraint và unique index

Nhiều database triển khai unique constraint bằng một unique index. Về thiết kế, hãy khai báo invariant dưới dạng constraint trong schema/migration để ý định dữ liệu được thể hiện rõ. Unique index cũng có thể được dùng trong một số tình huống đặc thù, nhưng cần hiểu semantics của engine.

Không nên chỉ dùng kiểm tra Java hoặc một index không unique để bảo vệ dữ liệu duy nhất. Kiểm tra ở ứng dụng không thể điều phối mọi tiến trình, worker, batch job và service cùng ghi vào database.

## 4. Chuẩn hóa dữ liệu trước khi kiểm tra và ghi

Một nguyên nhân khác làm kiểm tra tồn tại không khớp với constraint là ứng dụng dùng các cách biểu diễn khác nhau cho cùng một giá trị.

Ví dụ, nghiệp vụ coi `Alice@Example.com` và `alice@example.com` là cùng một email. Nếu ứng dụng kiểm tra bằng một dạng nhưng database lưu dạng khác, kết quả có thể không nhất quán.

Hãy xác định quy tắc canonicalization trước khi query và lưu:

~~~java
public final class EmailNormalizer {

    private EmailNormalizer() {
    }

    public static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Service sử dụng cùng giá trị chuẩn hóa:

~~~java
@Transactional
public Account register(String rawEmail) {
    String email = EmailNormalizer.normalize(rawEmail);

    if (accountRepository.existsByEmail(email)) {
        throw new EmailAlreadyRegisteredException(email);
    }

    return accountRepository.save(new Account(email));
}
~~~

Ví dụ trên giả định chính sách nghiệp vụ coi toàn bộ email không phân biệt hoa thường. Quy tắc email thực tế cần được thống nhất với hệ thống xác thực và dữ liệu hiện có; không nên tùy tiện thay đổi chữ hoa/thường nếu domain có quy tắc khác.

Các trường hợp cần chú ý:

- Trim khoảng trắng ở đầu/cuối.
- Chuẩn hóa chữ hoa/thường theo quy tắc nghiệp vụ.
- Chuẩn hóa số điện thoại về một định dạng thống nhất.
- Unicode normalization nếu dữ liệu có thể được nhập bằng nhiều dạng ký tự tương đương.
- Tenant ID, trạng thái xóa mềm và các cột tham gia phạm vi duy nhất.
- Collation và quy tắc so sánh chuỗi của database.

Nếu quy tắc chuẩn hóa phải được bảo đảm cho mọi writer, hãy cân nhắc lưu giá trị canonical riêng hoặc dùng cơ chế phù hợp ở database. Chỉ chuẩn hóa trong một service sẽ không bảo vệ được khi một batch job khác ghi trực tiếp giá trị chưa chuẩn hóa.

## 5. Xử lý unique constraint violation trong Spring Data JPA

Khi hai request cùng vượt qua bước kiểm tra, database sẽ từ chối một insert. Với Spring Data JPA, lỗi từ JPA provider có thể được Spring chuyển thành exception thuộc hệ Spring DAO, thường là `DataIntegrityViolationException` hoặc một kiểu con phù hợp.

Ví dụ service dùng `saveAndFlush()` để buộc câu insert được gửi xuống database ngay trong lời gọi:

~~~java
@Service
@RequiredArgsConstructor
public class AccountService {
    private final AccountRepository accountRepository;

    @Transactional
    public Account register(String rawEmail) {
        String email = EmailNormalizer.normalize(rawEmail);

        if (accountRepository.existsByEmail(email)) {
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

Đoạn code minh họa việc chuyển lỗi persistence thành lỗi nghiệp vụ. Trong ứng dụng thực tế, cần chắc chắn constraint gây lỗi là constraint email. `DataIntegrityViolationException` cũng có thể biểu thị vi phạm foreign key, not-null hoặc check constraint; không nên chuyển mọi lỗi loại này thành “email đã tồn tại”.

Có thể kiểm tra tên constraint hoặc cause chain theo database/provider đang dùng. Nếu muốn giữ service ít phụ thuộc vendor, hãy đóng gói việc nhận diện constraint trong một thành phần persistence riêng và kiểm thử trên database production-compatible.

### Lưu ý về transaction đã bị rollback-only

Không nên bắt lỗi constraint rồi tiếp tục thực hiện thêm thao tác ghi trong cùng transaction như thể transaction vẫn khỏe mạnh. Sau lỗi SQL, JPA provider hoặc database có thể đã đánh dấu transaction rollback-only hoặc transaction không còn dùng được.

Một cách thiết kế rõ ràng là để lỗi persistence thoát khỏi phương thức transactional, sau đó chuyển đổi ở ranh giới bên ngoài transaction. Ví dụ, một facade không có transaction gọi service bean transactional và bắt exception sau khi proxy đã hoàn tất rollback:

~~~java
@Service
@RequiredArgsConstructor
public class AccountRegistrationFacade {
    private final AccountWriter accountWriter;

    public Account register(String email) {
        try {
            return accountWriter.registerInTransaction(email);
        } catch (DataIntegrityViolationException ex) {
            if (ConstraintErrors.isEmailUniqueViolation(ex)) {
                throw new EmailAlreadyRegisteredException(email, ex);
            }
            throw ex;
        }
    }
}

@Service
@RequiredArgsConstructor
class AccountWriter {
    private final AccountRepository accountRepository;

    @Transactional
    public Account registerInTransaction(String email) {
        return accountRepository.saveAndFlush(new Account(email));
    }
}
~~~

Ví dụ này giả định `ConstraintErrors.isEmailUniqueViolation()` được triển khai theo database/provider của dự án và hai class là hai Spring bean riêng để lời gọi đi qua proxy. Khi exception thoát khỏi `AccountWriter`, transaction interceptor rollback trước khi facade nhận exception.

Một lựa chọn khác là để `@RestControllerAdvice` xử lý exception sau khi service transaction đã kết thúc. Cách nào phù hợp tùy API boundary và kiến trúc ứng dụng.

## 6. Kiểm tra tồn tại không thay thế unique constraint

Hai cơ chế có mục tiêu khác nhau:

| Cơ chế | Vai trò | Có ngăn được hai request đồng thời tạo dữ liệu trùng không? |
|---|---|---|
| `existsByEmail()` | Kiểm tra sớm, phản hồi thân thiện | Không |
| Kiểm tra bằng `findByEmail()` | Lấy bản ghi hiện có và kiểm tra nghiệp vụ | Không |
| Unique constraint | Bảo vệ invariant trong database | Có |
| Bắt lỗi constraint | Chuyển kết quả ghi thất bại thành phản hồi nghiệp vụ | Không tự bảo vệ dữ liệu; xử lý hậu quả |
| Distributed lock | Điều phối writer theo một khóa logic | Có thể giảm cạnh tranh nếu triển khai đúng, nhưng không thay constraint |

Có thể bỏ bước kiểm tra trước nếu nghiệp vụ chấp nhận thử insert và chuyển lỗi constraint thành kết quả trùng dữ liệu. Việc này giảm một query đọc cho mỗi lần đăng ký mới, nhưng phản hồi trùng dữ liệu chỉ xuất hiện sau thao tác ghi.

Nếu dùng bước kiểm tra trước, hãy xem nó là tối ưu trải nghiệm. Constraint vẫn phải tồn tại và exception vẫn phải được xử lý.

## 7. Có thể dùng pessimistic locking để giải quyết không?

JPA hỗ trợ khóa bi quan qua `@Lock`, ví dụ:

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findByIdForUpdate(@Param("id") Long id);
}
~~~

Cách này khóa một hàng đã tồn tại để ngăn transaction khác sửa/xóa theo cách xung đột trong thời gian khóa. Nhưng khi email chưa tồn tại, truy vấn không trả về hàng nào để khóa. Vì vậy, `SELECT ... FOR UPDATE` trên truy vấn tìm email chưa có không phải giải pháp portable để khóa “khoảng trống” đó.

Một số database có gap lock, predicate lock hoặc cơ chế khóa đặc thù tùy isolation level và query plan. Không nên dựa vào chúng nếu chưa xác minh trên engine triển khai.

Các phương án nâng cao gồm:

- Khóa một hàng cha hoặc hàng điều phối luôn tồn tại, ví dụ tenant row, trước khi kiểm tra và insert.
- Dùng advisory lock theo khóa logic nếu database hỗ trợ và kiến trúc chấp nhận phụ thuộc engine.
- Dùng transaction isolation SERIALIZABLE và retry toàn bộ transaction khi database báo serialization failure.
- Dùng câu lệnh atomic insert/upsert đặc thù database.

Các cách này có chi phí về throughput, contention, deadlock và khả năng portability. Unique constraint vẫn nên được giữ làm hàng rào cuối cùng.

### SERIALIZABLE không phải bật lên là hết mọi lỗi

Isolation SERIALIZABLE yêu cầu database bảo đảm kết quả tương đương một thứ tự tuần tự hợp lệ. Database có thể từ chối một transaction bằng serialization failure thay vì cho cả hai transaction commit.

Ứng dụng cần retry toàn bộ transaction với transaction mới khi gặp lỗi serialization có thể retry. Không được tiếp tục dùng transaction đã thất bại. Việc triển khai và exception cụ thể phụ thuộc database, driver và transaction manager.

## 8. Upsert và insert-if-absent

Nếu nghiệp vụ yêu cầu “tạo nếu chưa có, nếu có thì cập nhật”, một câu lệnh atomic upsert có thể phù hợp hơn mô hình check-then-act. Cú pháp phụ thuộc database.

Ví dụ PostgreSQL:

~~~sql
INSERT INTO account(email, display_name)
VALUES (:email, :displayName)
ON CONFLICT (email)
DO UPDATE SET display_name = EXCLUDED.display_name;
~~~

Ví dụ MySQL:

~~~sql
INSERT INTO account(email, display_name)
VALUES (?, ?)
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name);
~~~

Đây là SQL đặc thù database, không phải cú pháp JPQL portable. Cần kiểm tra semantics khi conflict: cột nào được cập nhật, có thay đổi version/audit không, trigger nào chạy, giá trị trả về là gì và liệu update có được phép theo nghiệp vụ hay không.

Nếu nghiệp vụ chỉ muốn “insert nếu chưa có, nếu đã có thì giữ nguyên”, câu lệnh atomic có thể dùng nhánh do nothing hoặc tương đương của engine. Cần xác định rõ kết quả API muốn trả về là “đã tạo”, “đã tồn tại” hay “đã cập nhật”.

Không dùng upsert chỉ để né exception nếu điều đó làm thay đổi ý nghĩa nghiệp vụ. Ví dụ, đăng ký tài khoản trùng email có thể phải báo conflict thay vì âm thầm ghi đè tên hiển thị hoặc mật khẩu.

## 9. Dữ liệu duy nhất trong hệ thống nhiều instance

Một ứng dụng có thể chạy nhiều pod, VM hoặc process. Mỗi instance có thể thực hiện `existsByEmail()` cùng lúc và không biết trạng thái kiểm tra của instance khác.

Các giải pháp chỉ ở bộ nhớ process như `synchronized`, `ReentrantLock` hoặc một map cục bộ không điều phối được các instance khác. Chúng cũng không bảo vệ dữ liệu khi có batch job, script quản trị hoặc service khác ghi trực tiếp vào cùng database.

Với dữ liệu duy nhất dùng chung, database constraint là cơ chế có thẩm quyền. Distributed lock có thể giúp giảm số lần cùng tranh chấp, nhưng cần xử lý lease expiration, mất kết nối, fencing token, retry và deadlock. Không nên coi distributed lock là thay thế cho constraint.

Nếu cần bảo vệ idempotency của API hoặc xử lý message lặp, có thể lưu idempotency key với unique constraint. Khi cùng một key được gửi lại, ứng dụng trả kết quả đã lưu thay vì thực hiện nghiệp vụ lần nữa. Key cần có phạm vi, thời hạn lưu và quy tắc xử lý payload khác nhau rõ ràng.

## 10. Kiểm thử race condition đúng cách

Một test tuần tự chỉ chứng minh hai lần gọi nối tiếp phát hiện được bản ghi đã tạo. Nó không chứng minh hai transaction đồng thời được xử lý đúng.

Integration test cần dùng hai transaction/connection độc lập và đồng bộ để cả hai cùng kiểm tra trước khi insert. Sau đó xác nhận chỉ một bản ghi được commit.

Một kịch bản test:

1. Tạo database trống và bảo đảm unique constraint đã được áp dụng.
2. Khởi chạy hai task độc lập, mỗi task có transaction riêng.
3. Dùng barrier hoặc latch để hai task hoàn tất bước kiểm tra tồn tại gần cùng thời điểm.
4. Cho cả hai thử insert cùng email.
5. Chờ cả hai transaction kết thúc.
6. Xác nhận chỉ có một hàng với email đó.
7. Xác nhận một request thành công và request còn lại nhận lỗi conflict theo hợp đồng ứng dụng.

Không nên dùng một transaction test bao trùm cả hai task vì chúng có thể không còn là hai transaction độc lập như tình huống production. Dùng database thật qua Testcontainers khi cần xác minh locking, unique constraint và isolation của engine triển khai.

Ví dụ kiểm tra invariant sau khi hai task hoàn tất:

~~~java
assertThat(accountRepository.countByEmail(email)).isEqualTo(1);
~~~

Phương thức `countByEmail` có thể được khai báo:

~~~java
long countByEmail(String email);
~~~

Ngoài số hàng, test cần xác nhận response của cả hai request và trạng thái transaction. Nếu dùng PostgreSQL, MySQL hoặc engine khác, hãy chạy test trên cùng engine/version để kết quả phản ánh đúng production.

## 11. Những trường hợp nghiệp vụ cần định nghĩa rõ

“Đã tồn tại” không phải lúc nào cũng chỉ là so sánh một cột.

Hãy xác định rõ:

- Duy nhất toàn hệ thống hay theo tenant/organization?
- Bản ghi soft-delete có được xem là đã tồn tại không?
- Có cho phép tái sử dụng email sau khi tài khoản bị xóa không?
- Giá trị so sánh đã chuẩn hóa chưa?
- Hai request cùng tạo một tài nguyên có nên trả cùng resource ID không?
- Nếu bản ghi đã tồn tại, trả HTTP 409, trả tài nguyên hiện có hay cập nhật?
- Khi conflict do constraint khác, có được phép trả thông báo “đã tồn tại” không?

Ví dụ, nếu chỉ bản ghi chưa bị xóa mềm mới tham gia phạm vi duy nhất, cần thiết kế constraint phù hợp với khả năng của database. Partial unique index là tính năng riêng của một số engine; một unique constraint đơn giản trên email có thể vẫn chặn việc tái sử dụng email dù bản ghi cũ đã soft-delete.

Hãy để quy tắc trong database, query kiểm tra và xử lý exception cùng phản ánh một định nghĩa duy nhất.

## 12. Checklist triển khai an toàn

Trước khi hoàn thiện luồng kiểm tra tồn tại rồi ghi, hãy xác nhận:

1. Đã xác định chính xác khóa nghiệp vụ phải duy nhất chưa?
2. Database có unique constraint hoặc cơ chế tương đương chưa?
3. Migration xử lý dữ liệu trùng hiện có trước khi thêm constraint chưa?
4. Giá trị đã được chuẩn hóa nhất quán trước khi query và lưu chưa?
5. `existsBy...` chỉ được dùng như kiểm tra sớm, không phải bảo đảm concurrency?
6. Service xử lý đúng unique violation và phân biệt với constraint khác chưa?
7. Lỗi xuất hiện khi flush/commit có được xử lý đúng transaction boundary không?
8. Có tránh tiếp tục ghi trong transaction đã bị đánh dấu rollback-only không?
9. Nếu dùng retry hoặc SERIALIZABLE, mỗi lần thử có transaction mới và giới hạn phù hợp không?
10. Integration test đã tạo hai transaction đồng thời trên database production-compatible chưa?
11. Nếu dùng upsert, semantics insert/update/conflict có đúng nghiệp vụ không?
12. Test đã bao phủ tenant, soft-delete, normalization và idempotency nếu có không?

## Kết luận

`existsBy...` giúp kiểm tra sớm và phản hồi thân thiện, nhưng không ngăn được race condition giữa hai request đồng thời. Để bảo đảm dữ liệu duy nhất, hãy đặt unique constraint trong database, chuẩn hóa giá trị theo cùng một quy tắc và xử lý unique violation ở ranh giới phù hợp sau khi transaction rollback. Pessimistic lock, SERIALIZABLE, upsert hoặc distributed lock có thể giải quyết những nhu cầu cụ thể, nhưng cần hiểu semantics của database và chi phí vận hành. Cuối cùng, hãy kiểm thử bằng hai transaction độc lập trên engine gần production để chứng minh chỉ một thao tác có thể tạo bản ghi duy nhất.