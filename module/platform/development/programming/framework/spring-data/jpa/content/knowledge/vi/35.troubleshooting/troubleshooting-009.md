# IncorrectResultSizeDataAccessException và dữ liệu không duy nhất

## 1. Lỗi này có nghĩa gì?

`IncorrectResultSizeDataAccessException` là exception của Spring DAO, báo rằng một thao tác truy vấn nhận được số kết quả khác với số lượng mà caller hoặc API yêu cầu. Trường hợp thường gặp trong Spring Data JPA là repository method được khai báo trả về một Entity hoặc `Optional<Entity>` nhưng query thực tế khớp với nhiều hàng.

Ví dụ nghiệp vụ cho rằng email là duy nhất:

```java
Optional<Customer> findByEmail(String email);
```

Nếu database có hai khách hàng cùng email, Spring Data không thể chọn một bản ghi tùy ý để trả về như một kết quả đơn. Tùy đường thực thi/provider, lỗi có thể xuất hiện dưới dạng `IncorrectResultSizeDataAccessException`, được dịch từ lỗi cardinality của JPA.

Thông điệp quan trọng: **kiểu trả về đơn biểu đạt kỳ vọng về số lượng kết quả, nhưng không tự tạo ra tính duy nhất trong database**. Nếu tính duy nhất là quy tắc nghiệp vụ, cần bảo vệ nó ở database và kiểm soát cả dữ liệu cũ lẫn đường ghi mới.

## 2. Phân biệt các exception liên quan

| Exception | Ý nghĩa thường gặp |
| --- | --- |
| `IncorrectResultSizeDataAccessException` | Spring DAO nhận số kết quả khác với số lượng mong đợi |
| `EmptyResultDataAccessException` | Một kết quả đơn được yêu cầu nhưng không có hàng; đây là subclass của `IncorrectResultSizeDataAccessException` |
| `jakarta.persistence.NonUniqueResultException` | JPA query yêu cầu một kết quả đơn nhưng có nhiều kết quả |
| `DataIntegrityViolationException` | Thao tác ghi vi phạm constraint/ràng buộc dữ liệu, ví dụ unique hoặc foreign key |

Không nhầm lỗi truy vấn trả nhiều hàng với lỗi ghi trùng unique key. Trường hợp đầu là cardinality của kết quả đọc; trường hợp sau là database từ chối một thay đổi vì vi phạm constraint.

Spring có thể dịch exception từ persistence provider sang hệ exception `DataAccessException`. Loại exception quan sát được phụ thuộc API được gọi, Spring Data/JPA provider và vị trí lỗi. Khi chẩn đoán, xem cả exception gốc (`cause`) và SQL được thực thi.

## 3. Kiểu trả về quyết định cardinality mong đợi

Spring Data repository hỗ trợ nhiều kiểu trả về với ý nghĩa khác nhau:

| Kiểu trả về | Ý nghĩa |
| --- | --- |
| `Optional<Customer>` | Không có kết quả hoặc một kết quả; nhiều kết quả là lỗi |
| `Customer` | Một kết quả đơn; nếu không có, thường trả null theo semantics query method; nhiều kết quả là lỗi |
| `List<Customer>` / `Collection<Customer>` | Có thể có không, một hoặc nhiều kết quả |
| `Page<Customer>` / `Slice<Customer>` | Tập kết quả phân trang |
| `boolean` từ `existsBy...` | Chỉ cần biết có ít nhất một kết quả |
| `long` từ `countBy...` | Số lượng kết quả |

Ví dụ:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Optional<Customer> findByEmail(String email);

    List<Customer> findAllByEmail(String email);

    boolean existsByEmail(String email);

    long countByEmail(String email);
}
```

Chọn kiểu trả về theo nghiệp vụ. Nếu email được phép trùng, dùng `List<Customer>` hoặc một kiểu tập hợp phù hợp. Nếu email phải duy nhất, giữ `Optional<Customer>` và bảo vệ unique constraint ở database.

`Optional` chỉ biểu diễn trường hợp không có kết quả. Nó không có nghĩa “lấy kết quả đầu tiên” và không tự xử lý nhiều hàng trùng.

## 4. Những repository method dễ gặp lỗi

### Derived query trả về một Entity

```java
Optional<Customer> findByExternalId(String externalId);
```

Method này giả định `externalId` xác định tối đa một Customer. Nếu có nhiều hàng cùng external ID, truy vấn không thể đáp ứng kiểu trả về.

### JPQL @Query trả về một kết quả

```java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findOneByEmail(@Param("email") String email);
```

JPQL không tự bảo đảm `email` duy nhất. Nếu dữ liệu có hai hàng khớp, lỗi cardinality vẫn xảy ra.

### findOne với Example hoặc Specification

`QueryByExampleExecutor.findOne(example)` và `JpaSpecificationExecutor.findOne(specification)` cũng yêu cầu tối đa một kết quả. Nếu điều kiện của probe/specification khớp nhiều Entity, không thể dùng `findOne` như cách tùy ý lấy một hàng; hãy dùng `findAll` hoặc bảo đảm predicate duy nhất.

### Querydsl findOne

`QuerydslPredicateExecutor.findOne(predicate)` cũng biểu đạt truy vấn đơn. Nếu predicate khớp nhiều Entity, Spring Data báo lỗi kích thước kết quả thay vì âm thầm chọn một hàng.

## 5. First/Top khác với bảo đảm duy nhất

Nếu nghiệp vụ thực sự muốn lấy một kết quả theo thứ tự, Spring Data có derived query `First` hoặc `Top`:

```java
Optional<Customer> findFirstByEmailOrderByCreatedAtDescIdDesc(String email);
```

Method trên giới hạn kết quả và chọn bản ghi mới nhất theo `createdAt`, dùng `id` làm tie-breaker. Nó không chứng minh email là duy nhất; các bản ghi còn lại vẫn tồn tại.

Chỉ dùng `First`/`Top` khi nghiệp vụ có quy tắc chọn bản ghi rõ ràng, ví dụ phiên bản mới nhất hoặc bản ghi ưu tiên cao nhất. Luôn chỉ định `OrderBy` ổn định; nếu không có thứ tự, “bản ghi đầu tiên” có thể không xác định.

Không dùng `findFirstBy...` để che dữ liệu trùng khi quy tắc đúng phải là duy nhất. Làm vậy có thể khiến lỗi dữ liệu kéo dài và một request khác nhận bản ghi khác.

## 6. Nguyên nhân phổ biến

**Dữ liệu đã trùng trong database.** Import cũ, migration, thao tác thủ công hoặc bug trước đây có thể đã tạo nhiều hàng cùng business key.

**Thiếu unique constraint.** Java method trả `Optional` nhưng schema chỉ có index thường, không có ràng buộc duy nhất.

**Unique constraint chỉ áp dụng sai phạm vi.** Ví dụ email phải duy nhất trong từng tenant, nhưng schema không có unique constraint ghép `(tenant_id, email)` hoặc query lại quên điều kiện tenant.

**Khác biệt hoa thường và chuẩn hóa.** `User@example.com` và `user@example.com` có thể được coi là giống hoặc khác tùy collation/database và quy tắc nghiệp vụ. Khoảng trắng, Unicode normalization hoặc định dạng số điện thoại cũng có thể tạo nhiều cách biểu diễn cùng một giá trị.

**Query JOIN làm nhân kết quả.** Join một root với nhiều dòng child có thể tạo nhiều hàng kết quả cho cùng root. Đây có thể là duplicate do query shape, không nhất thiết là hai Entity có cùng ID.

**Predicate không đủ cụ thể.** Tìm theo tên, trạng thái hoặc một thuộc tính không duy nhất nhưng method lại khai báo kết quả đơn.

**Concurrent insert.** Hai request đồng thời cùng kiểm tra “chưa có email” rồi cùng insert. Cả hai pre-check có thể thành công nếu chưa có unique constraint.

## 7. Phân biệt duplicate Entity với duplicate row do JOIN

Trước khi thêm constraint hoặc xóa dữ liệu, xác định nhiều kết quả là nhiều Entity khác nhau hay nhiều hàng SQL đại diện cùng một root.

Ví dụ query:

```java
@Query("""
    select c
    from Customer c
    join c.orders o
    where o.status = :status
    """)
List<Customer> findCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

Một Customer có ba order cùng trạng thái có thể tạo ba hàng join cho cùng Customer. Nếu mục tiêu là lấy Customer duy nhất, có thể dùng:

```java
@Query("""
    select distinct c
    from Customer c
    join c.orders o
    where o.status = :status
    """)
List<Customer> findDistinctCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

Nếu chỉ cần kiểm tra có order phù hợp, `EXISTS` thường tránh nhân hàng root:

```java
@Query("""
    select c
    from Customer c
    where exists (
        select o.id
        from PurchaseOrder o
        where o.customer = c
          and o.status = :status
    )
    """)
List<Customer> findCustomersHavingOrderStatus(
    @Param("status") OrderStatus status
);
```

`DISTINCT` giải quyết kết quả root bị lặp do join. Nó không sửa hai Customer khác nhau có cùng email. Ngược lại, unique constraint email không giải quyết việc join một Customer với nhiều order. Phải xử lý đúng nguyên nhân.

Với query trả scalar, tuple hoặc DTO, các dòng có cùng giá trị vẫn có thể là các kết quả riêng; `DISTINCT` chỉ gộp những projection giống nhau theo semantics của query.

## 8. Kiểm tra dữ liệu trùng bằng SQL

Để tìm email xuất hiện nhiều hơn một lần:

```sql
SELECT email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

Để tìm theo business key trong từng tenant:

```sql
SELECT tenant_id, email, COUNT(*) AS duplicate_count
FROM customer
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
```

Để xem ID và các hàng cụ thể cần điều tra:

```sql
SELECT c.id, c.tenant_id, c.email, c.created_at
FROM customer c
JOIN (
    SELECT tenant_id, email
    FROM customer
    GROUP BY tenant_id, email
    HAVING COUNT(*) > 1
) d
  ON d.tenant_id = c.tenant_id
 AND d.email = c.email
ORDER BY c.tenant_id, c.email, c.created_at, c.id;
```

Điều chỉnh truy vấn theo schema và null semantics của database. Nếu business key nullable, cần xác định có cho phép nhiều NULL hay không; quy tắc unique với NULL khác nhau giữa các database. Với phép so khớp không phân biệt hoa thường, nhóm theo biểu thức chuẩn hóa phù hợp với quy tắc của hệ thống, ví dụ `LOWER(email)` nếu database và collation hỗ trợ.

Không xóa hàng trùng ngay khi phát hiện. Trước tiên xác định bản ghi chuẩn, các foreign key tham chiếu, lịch sử nghiệp vụ và cách hợp nhất dữ liệu. Việc xóa nhầm có thể làm mất quan hệ hoặc audit trail.

## 9. Bảo vệ tính duy nhất bằng database constraint

Nếu email phải duy nhất toàn hệ thống, khai báo constraint ở schema:

```java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String email;
}
```

`@UniqueConstraint` mô tả constraint cho schema generation. Trong production dùng Flyway/Liquibase hoặc migration tool khác, cần tạo unique constraint thực tế bằng migration; annotation không tự sửa schema đã triển khai nếu DDL auto không được phép.

Nếu email chỉ cần duy nhất trong một tenant:

```java
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_email",
        columnNames = {"tenant_id", "email"}
    )
)
```

Đây là unique constraint ghép. Cả query tìm kiếm lẫn kiểm tra trùng phải dùng cùng business key `(tenant_id, email)`. Nếu chỉ lọc email mà bỏ tenant, repository method có thể hợp lệ trả nhiều khách hàng thuộc tenant khác nhau.

## 10. Chuẩn hóa dữ liệu trước khi áp dụng uniqueness

Unique constraint chỉ so sánh theo semantics database. Nếu nghiệp vụ coi email không phân biệt hoa thường, hãy chuẩn hóa nhất quán trước khi ghi và khi tìm:

```java
public static String normalizeEmail(String rawEmail) {
    return rawEmail == null
        ? null
        : rawEmail.trim().toLowerCase(Locale.ROOT);
}
```

Ví dụ trên là chính sách minh họa. Cần quyết định rõ cách xử lý Unicode, domain, local-part, khoảng trắng và email quốc tế theo quy tắc sản phẩm; không phải mọi email đều nên biến đổi tùy tiện. Một lựa chọn là lưu thêm cột normalized key và đặt unique constraint trên cột đó.

Với database hỗ trợ functional unique index hoặc collation phù hợp, có thể áp dụng quy tắc uniqueness ở schema. Cú pháp phụ thuộc database; ghi rõ migration và kiểm thử trên đúng engine production.

## 11. Kiểm tra trước khi insert không thay thế unique constraint

Service có thể kiểm tra để trả thông báo thân thiện:

```java
if (repository.existsByEmail(normalizedEmail)) {
    throw new EmailAlreadyRegisteredException(normalizedEmail);
}

repository.save(newCustomer);
```

Nhưng đây là pre-check phục vụ trải nghiệm, không phải bảo vệ concurrency. Hai transaction có thể cùng nhận `false` từ `existsByEmail` rồi cùng insert. Unique constraint database mới là lớp bảo vệ cuối cùng.

Hãy bắt lỗi vi phạm constraint ở ranh giới service phù hợp và chuyển thành kết quả nghiệp vụ rõ ràng, ví dụ HTTP 409 Conflict cho request tạo tài nguyên đã tồn tại. Cần xác định constraint cụ thể; không biến mọi `DataIntegrityViolationException` thành lỗi duplicate email vì exception này còn có thể biểu thị lỗi foreign key, NOT NULL hoặc constraint khác.

## 12. Xử lý race condition và exception khi ghi

Luồng an toàn thường là:

1. Chuẩn hóa business key.
2. Có thể kiểm tra `existsBy...` để phản hồi sớm.
3. Thực hiện INSERT trong transaction.
4. Để unique constraint xử lý cạnh tranh.
5. Bắt/translate lỗi đúng constraint sau khi transaction thất bại.

Ví dụ minh họa service:

```java
@Transactional
public Customer createCustomer(String rawEmail) {
    String email = normalizeEmail(rawEmail);

    if (repository.existsByEmail(email)) {
        throw new EmailAlreadyRegisteredException(email);
    }

    try {
        return repository.saveAndFlush(new Customer(email));
    } catch (DataIntegrityViolationException ex) {
        if (isEmailUniqueConstraintViolation(ex)) {
            throw new EmailAlreadyRegisteredException(email, ex);
        }
        throw ex;
    }
}
```

`isEmailUniqueConstraintViolation` là phần phụ thuộc database/driver và cần được triển khai bằng cách kiểm tra constraint name hoặc SQLState/error code phù hợp. Không phân tích chuỗi message chung chung nếu có thể kiểm tra metadata lỗi đáng tin cậy.

`saveAndFlush()` giúp constraint thường được phát hiện tại vị trí này thay vì chờ flush cuối transaction. Nếu exception đánh dấu transaction rollback-only, không tiếp tục dùng transaction đó như thể insert đã thành công. Việc chuyển lỗi ra HTTP nên diễn ra sau khi transaction đã rollback đúng cách.

## 13. Chọn đúng query khi dữ liệu không duy nhất

Nếu business key không duy nhất, hãy thay đổi query/API để phản ánh đúng cardinality:

```java
List<Customer> findAllByLastName(String lastName);
```

Nếu chỉ cần kiểm tra tồn tại:

```java
boolean existsByLastName(String lastName);
```

Nếu chỉ cần số lượng:

```java
long countByLastName(String lastName);
```

Nếu muốn lấy bản ghi mới nhất theo một quy tắc xác định:

```java
Optional<Customer> findFirstByLastNameOrderByCreatedAtDescIdDesc(
    String lastName
);
```

Không đổi từ `Optional` sang `List` chỉ để làm exception biến mất nếu nghiệp vụ vẫn đòi một bản ghi duy nhất. Hãy sửa dữ liệu hoặc schema nếu key phải duy nhất.

## 14. Xử lý dữ liệu trùng đã tồn tại

Khi thêm unique constraint vào bảng đã có dữ liệu, migration có thể thất bại nếu key trùng. Cần có quy trình làm sạch trước:

1. Chạy truy vấn GROUP BY/HAVING để lập danh sách business key trùng.
2. Xác định bản ghi canonical theo quy tắc nghiệp vụ; không chỉ chọn ID nhỏ nhất một cách máy móc.
3. Xác định foreign key, bảng phụ, audit log và lịch sử cần hợp nhất/chuyển tham chiếu.
4. Backup hoặc tạo bảng lưu vết trước khi sửa dữ liệu quan trọng.
5. Hợp nhất/cập nhật tham chiếu trong transaction hoặc migration có kiểm soát.
6. Chạy lại truy vấn duplicate để xác nhận không còn vi phạm.
7. Tạo unique constraint trong migration.
8. Triển khai code mới dựa trên constraint và kiểm thử concurrent insert.

Với bảng lớn, tạo index/constraint có thể khóa bảng hoặc cần chiến lược online riêng tùy database. Lập kế hoạch migration theo engine production, kích thước bảng và yêu cầu uptime.

## 15. Kiểm thử lỗi kích thước kết quả

Integration test cần kiểm tra cả trường hợp đúng một, không có và nhiều kết quả:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void listQueryCanReturnMultipleCustomers() {
        repository.save(new Customer("same@example.com"));
        repository.save(new Customer("same@example.com"));

        assertEquals(2, repository.findAllByEmail("same@example.com").size());
    }

    @Test
    void singularQueryRejectsMultipleMatches() {
        repository.save(new Customer("duplicate@example.com"));
        repository.save(new Customer("duplicate@example.com"));

        assertThrows(
            IncorrectResultSizeDataAccessException.class,
            () -> repository.findByEmail("duplicate@example.com")
        );
    }
}
```

Test thứ hai minh họa dữ liệu trùng để kiểm tra repository method đơn; nó chỉ chạy được nếu test schema chưa áp unique constraint cho email. Sau khi thêm constraint, hãy test riêng rằng lần insert thứ hai bị database từ chối và Spring dịch lỗi thành loại phù hợp. Không thể vừa bật unique constraint vừa mong insert hai hàng trùng thành công trong cùng test.

Với test `@DataJpaTest`, gọi `flush()` để buộc INSERT/constraint chạy và `clear()` khi cần đọc lại qua persistence context mới. Test slice thường rollback transaction khi kết thúc; flush không đồng nghĩa commit.

## 16. Kiểm thử unique constraint và concurrent insert

Test unique constraint nên lưu bản ghi đầu, flush, rồi thử lưu bản ghi thứ hai cùng key:

```java
@Test
void databaseRejectsDuplicateEmail() {
    repository.saveAndFlush(new Customer("unique@example.com"));

    assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(new Customer("unique@example.com"))
    );
}
```

Đây là ví dụ phụ thuộc schema đã có unique constraint và exception translation của cấu hình test. Sau lỗi constraint, transaction có thể rollback-only; nên để test framework rollback toàn bộ test thay vì tiếp tục query trong transaction đã lỗi.

Để kiểm tra race condition thực sự, cần hai transaction/connection độc lập đồng thời insert cùng business key. Một transaction phải thắng; transaction còn lại phải nhận unique violation. Test concurrency cần đồng bộ barrier và database thật hoặc engine tương thích, không chỉ chạy hai lời gọi tuần tự trong một transaction.

## 17. Xử lý ở REST API

Không nên trả stack trace hoặc SQL message cho client. Có thể map lỗi nghiệp vụ duplicate key sang HTTP 409:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(EmailAlreadyRegisteredException.class)
    ResponseEntity<ProblemDetail> handleDuplicateEmail(
            EmailAlreadyRegisteredException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.CONFLICT);
        problem.setTitle("Email already registered");
        problem.setDetail("An account with this email already exists.");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }
}
```

Đây là xử lý lỗi nghiệp vụ do service translate từ đúng unique constraint. `IncorrectResultSizeDataAccessException` thường cho thấy query hoặc dữ liệu đang vi phạm kỳ vọng cardinality của code; không nên tự động biến nó thành 404 hoặc trả một bản ghi tùy ý. Ghi log có context an toàn, điều tra query và dữ liệu, rồi trả lỗi server phù hợp nếu đó là lỗi toàn vẹn dữ liệu nội bộ.

Không đưa email, SQL, tên bảng hoặc dữ liệu nhạy cảm vào response lỗi nếu không cần thiết.

## 18. Quy trình chẩn đoán khi gặp lỗi

1. Đọc stack trace và xác định repository method/API nào yêu cầu một kết quả đơn.
2. Ghi nhận query JPQL/SQL, bind parameter và kiểu trả về.
3. Chạy query tương đương để xác định có nhiều Entity khác nhau hay duplicate row do JOIN.
4. Nếu là JOIN fan-out, xem xét `DISTINCT` hoặc EXISTS; kiểm tra projection và count.
5. Nếu là duplicate business key, chạy GROUP BY/HAVING theo đúng phạm vi tenant và quy tắc chuẩn hóa.
6. Xác định unique constraint hiện có trong database, không chỉ dựa vào annotation Entity.
7. Kiểm tra các đường ghi: API, batch, import, native SQL và service khác.
8. Nếu có race condition, thêm database unique constraint và xử lý lỗi constraint.
9. Viết integration test cho cardinality và constraint; kiểm thử concurrency khi cần.

## 19. Lỗi thường gặp và cách xử lý

**`Optional<T>` vẫn ném lỗi khi có hai hàng.** Optional chỉ biểu diễn zero-or-one; bảo đảm unique key hoặc đổi sang collection nếu nhiều kết quả là hợp lệ.

**Đổi sang `findFirstBy...` làm lỗi biến mất nhưng dữ liệu vẫn trùng.** Chỉ giữ cách này khi có quy tắc chọn bản ghi và sort ổn định; nếu key phải duy nhất, sửa dữ liệu và schema.

**Thêm `@Column(unique = true)` nhưng production vẫn nhận duplicate.** Kiểm tra migration đã tạo constraint thật chưa; annotation không tự thay schema production.

**`DISTINCT` không giải quyết duplicate email.** DISTINCT loại kết quả trùng theo query; unique constraint mới bảo vệ business key.

**Unique constraint vẫn cho phép một số giá trị NULL trùng.** Kiểm tra semantics NULL của database và xác định cột có cần NOT NULL hoặc partial/filtered unique index không.

**Pre-check exists vẫn bị duplicate khi có hai request đồng thời.** Đây là race condition; database constraint phải là lớp bảo vệ cuối cùng.

**`DataIntegrityViolationException` bị đổi thành duplicate email dù lỗi thực là foreign key.** Chỉ translate khi xác định đúng constraint; giữ nguyên lỗi khác.

**Query trả nhiều kết quả do join collection.** Kiểm tra cardinality và dùng `distinct`/EXISTS phù hợp; đừng xóa dữ liệu Entity.

**Test không tái hiện lỗi vì dữ liệu chưa flush.** Dùng `saveAndFlush()` hoặc `entityManager.flush()` để buộc SQL/constraint chạy.

## 20. Checklist phòng tránh

- Kiểu trả về đơn chỉ dùng khi query thực sự có cardinality tối đa một.
- Dùng `List`/`Page` nếu nhiều kết quả là hợp lệ; dùng `exists`/`count` nếu chỉ cần kiểm tra hoặc đếm.
- Dùng `First`/`Top` chỉ khi nghiệp vụ có quy tắc chọn bản ghi và ORDER BY ổn định.
- Phân biệt duplicate Entity với duplicate row do JOIN.
- Bảo vệ business key bằng unique constraint thật trong database.
- Với uniqueness theo tenant, tạo composite unique constraint và luôn lọc đúng tenant.
- Chuẩn hóa key theo cùng một chính sách khi ghi, tìm và tạo constraint.
- Xử lý dữ liệu cũ trùng trước khi thêm constraint.
- Không dựa vào exists pre-check để chống concurrent insert.
- Translate đúng unique constraint thành lỗi nghiệp vụ; không nuốt các lỗi integrity khác.
- Dùng flush/clear trong integration test khi cần xác minh database thay vì first-level cache.
- Kiểm thử zero/one/multiple result, JOIN fan-out, unique violation và concurrent writes.

`IncorrectResultSizeDataAccessException` báo rằng số kết quả thực tế không khớp kỳ vọng của truy vấn đơn. Hãy xác định lỗi đến từ dữ liệu trùng hay JOIN tạo hàng lặp, chọn kiểu trả về đúng cardinality và bảo vệ business key bằng constraint database. `Optional`, pre-check và `First` không thay thế được tính duy nhất khi đó là quy tắc nghiệp vụ.