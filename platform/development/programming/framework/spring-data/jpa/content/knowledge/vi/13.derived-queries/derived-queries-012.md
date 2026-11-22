# existsBy, countBy, deleteBy và removeBy

Spring Data JPA cho phép suy diễn các truy vấn kiểm tra tồn tại, đếm bản ghi và xóa entity từ tên method repository. Bốn nhóm thường gặp là **existsBy**, **countBy**, **deleteBy** và **removeBy**. Chúng giúp diễn đạt nghiệp vụ ngay trên repository mà không cần viết JPQL cho các điều kiện đơn giản.

Điểm cần hiểu là mỗi nhóm có mục đích và chi phí khác nhau: existsBy trả lời một điều kiện có thỏa mãn hay không; countBy trả về số lượng bản ghi phù hợp; deleteBy và removeBy xóa các entity thỏa điều kiện theo cơ chế derived delete của Spring Data JPA. Đặc biệt, derived delete có hành vi vòng đời khác với bulk JPQL DELETE.

Bài này dùng Spring Data JPA 3.x, Jakarta Persistence và Java 17+.

## 1. Cú pháp chung của derived query

Spring Data phân tích tên method để tạo query dựa trên entity và thuộc tính Java:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    boolean existsByEmail(String email);

    long countByActiveTrue();

    long deleteByActiveFalse();

    long removeByCreatedAtBefore(Instant cutoff);
}
```

Các phần chính:

- **existsBy**: kiểm tra có entity thỏa điều kiện hay không.
- **countBy**: đếm entity thỏa điều kiện.
- **deleteBy**: xóa entity thỏa điều kiện.
- **removeBy**: từ đồng nghĩa với deleteBy trong derived delete query.

Phần sau By là điều kiện dựa trên tên thuộc tính Java. Có thể kết hợp nhiều điều kiện bằng And, Or và các toán tử như GreaterThan, Before, Between, In, IsNull, Containing hoặc IgnoreCase.

Ví dụ, method này:

```java
boolean existsByEmailIgnoreCaseAndActiveTrue(String email);
```

có nghĩa là kiểm tra có Customer nào có email không phân biệt hoa/thường khớp giá trị truyền vào và active = true hay không.

Tên method phải khớp property path của entity, không phải tên table hoặc column trong database. Nếu property là customer.id, có thể dùng dấu gạch dưới để phân tách rõ đường dẫn:

```java
long countByCustomer_IdAndStatus(
    Long customerId,
    OrderStatus status
);
```

## 2. existsBy: kiểm tra sự tồn tại

existsBy trả về boolean hoặc Boolean, thể hiện có ít nhất một entity thỏa điều kiện hay không.

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    boolean existsByEmail(String email);

    boolean existsByEmailAndActiveTrue(String email);

    boolean existsByPhoneNumber(String phoneNumber);
}
```

Sử dụng trong service:

```java
@Service
public class RegistrationService {

    private final CustomerRepository customerRepository;

    public RegistrationService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional(readOnly = true)
    public boolean emailAlreadyRegistered(String email) {
        return customerRepository.existsByEmailIgnoreCase(email);
    }
}
```

Kết quả:

- true: có ít nhất một bản ghi phù hợp.
- false: không có bản ghi phù hợp.

Không cần tải toàn bộ danh sách Customer chỉ để kiểm tra tồn tại. Dùng existsBy diễn đạt đúng mục đích và cho provider cơ hội tạo truy vấn phù hợp. SQL thực tế có thể khác nhau theo Hibernate, dialect và phiên bản; không giả định mọi existsBy luôn được dịch thành một cú pháp SQL duy nhất.

### 2.1. existsBy không thay thế unique constraint

Một lỗi thiết kế thường gặp là kiểm tra existsByEmail rồi mới insert:

```java
if (repository.existsByEmail(email)) {
    throw new DuplicateEmailException();
}

repository.save(new Customer(email));
```

Giữa hai thao tác có thể xảy ra race condition:

1. Transaction A kiểm tra email chưa tồn tại.
2. Transaction B cũng kiểm tra email chưa tồn tại.
3. A insert.
4. B insert cùng email.

Cả hai lần kiểm tra đều có thể trả false, nhưng database nhận hai thao tác insert cạnh tranh. Vì vậy, nếu email phải duy nhất, cần unique constraint/index ở database. existsBy giúp kiểm tra sớm và tạo thông báo thân thiện; unique constraint mới là hàng rào bảo vệ cuối cùng.

Ví dụ mapping:

```java
@Column(name = "email", nullable = false, unique = true, length = 254)
private String email;
```

Nếu schema được quản lý bằng Flyway hoặc Liquibase, hãy tạo unique constraint trong migration tương ứng. Ở service, vẫn cần xử lý lỗi vi phạm unique constraint vì kiểm tra trước không loại bỏ được cạnh tranh đồng thời.

### 2.2. existsBy với nhiều điều kiện

Có thể dùng các keyword kết hợp:

```java
boolean existsByEmailIgnoreCase(String email);

boolean existsByStatusAndCreatedAtAfter(
    OrderStatus status,
    Instant createdAt
);

boolean existsByCustomer_IdAndStatus(
    Long customerId,
    OrderStatus status
);

boolean existsByActiveTrueAndDeletedAtIsNull();
```

Tên method dài có thể làm repository khó đọc. Khi điều kiện phức tạp, có nhiều nhánh OR hoặc cần biểu đạt join đặc biệt, hãy cân nhắc @Query hoặc Specification.

## 3. countBy: đếm số entity phù hợp

countBy trả về số lượng bản ghi thỏa điều kiện. Nên dùng long để tránh giới hạn số nguyên 32 bit khi bảng lớn.

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    long countByStatus(OrderStatus status);

    long countByCustomer_Id(Long customerId);

    long countByStatusAndCreatedAtAfter(
        OrderStatus status,
        Instant createdAt
    );

    long countByTotalAmountGreaterThan(BigDecimal amount);
}
```

Ví dụ service:

```java
@Transactional(readOnly = true)
public long countPendingOrders() {
    return orderRepository.countByStatus(OrderStatus.PENDING);
}
```

countBy thường được dùng cho:

- Đếm đơn hàng theo trạng thái.
- Đếm sản phẩm đang hoạt động.
- Đếm bản ghi của một khách hàng.
- Đếm giao dịch trong khoảng thời gian.
- Kiểm tra số lượng trước khi cho phép thao tác nghiệp vụ.

### 3.1. countBy không tải toàn bộ entity

Khác với findBy trả về danh sách entity, countBy trả về một giá trị số. Provider tạo truy vấn đếm phù hợp, thường dựa trên COUNT trong SQL. Điều đó tránh tạo object graph cho toàn bộ entity chỉ để lấy số lượng.

Tuy nhiên, count không phải lúc nào cũng rẻ. Nếu điều kiện lọc không có index phù hợp hoặc bảng rất lớn, database vẫn có thể phải đọc nhiều dòng/index entry để tính kết quả. Hãy xem execution plan và thiết kế index theo điều kiện truy vấn thực tế.

Ví dụ, nếu thường xuyên đếm đơn theo customer_id và status:

```sql
CREATE INDEX idx_orders_customer_status
    ON purchase_orders (customer_id, status);
```

Thứ tự cột index cần dựa trên bộ lọc, độ chọn lọc và truy vấn thực tế. Không tạo index chỉ vì thấy một method countBy xuất hiện trong code.

### 3.2. Cẩn thận với distinct

Spring Data có hỗ trợ tên method chứa Distinct, nhưng cần hiểu distinct đang áp dụng cho kết quả nào. Ví dụ:

```java
long countDistinctByLastname(String lastname);
```

Với entity User có ID duy nhất, truy vấn count distinct entity thường có thể tương đương đếm số User phù hợp. Nó không nhất thiết có nghĩa là đếm số giá trị lastname khác nhau.

Nếu yêu cầu là đếm số họ khác nhau trong một nhóm, hãy viết JPQL rõ ràng:

```java
@Query("""
    select count(distinct c.lastname)
    from Customer c
    where c.active = true
    """)
long countDistinctActiveLastnames();
```

Đọc tên method thôi chưa đủ để suy ra ngữ nghĩa SQL mong muốn. Với distinct trên thuộc tính cụ thể, nên dùng @Query để thể hiện rõ biểu thức count(distinct ...).

### 3.3. countBy trên quan hệ nhiều

Khi điều kiện đi qua quan hệ OneToMany hoặc ManyToMany, join có thể tạo nhiều hàng SQL cho cùng một entity gốc. Nếu cần đếm entity gốc duy nhất, hãy xác định rõ count distinct theo ID hoặc viết JPQL phù hợp.

Ví dụ đếm khách hàng có đơn đã xác nhận:

```java
@Query("""
    select count(distinct c.id)
    from Customer c
    join c.orders o
    where o.status = :status
    """)
long countCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

Cách này làm rõ rằng cần đếm Customer duy nhất, kể cả khi một Customer có nhiều đơn thỏa điều kiện.

## 4. deleteBy: xóa entity theo điều kiện

Derived delete query bắt đầu bằng deleteBy:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    long deleteByActiveFalse();

    long deleteByCreatedAtBefore(Instant cutoff);

    void deleteByEmail(String email);
}
```

Method có thể trả void hoặc số lượng entity đã xóa, thường dùng long. Ví dụ:

```java
@Transactional
public long deleteInactiveCustomers(Instant cutoff) {
    return customerRepository.deleteByCreatedAtBefore(cutoff);
}
```

Cần đọc đúng ngữ nghĩa của derived delete: Spring Data JPA thường tìm các entity phù hợp rồi xóa từng entity thông qua EntityManager.remove. Cách này cho phép áp dụng vòng đời entity, callback và cascade của JPA.

Điều đó có nghĩa deleteBy không nhất thiết chỉ phát một câu SQL DELETE duy nhất. Provider có thể SELECT các entity phù hợp rồi phát DELETE cho từng entity, hoặc dùng batching tùy cấu hình. Khi số lượng bản ghi rất lớn, chi phí tải entity và persistence context có thể đáng kể.

### 4.1. Vì sao derived delete khác bulk DELETE?

Với derived delete:

1. Spring Data thực thi query để lấy các entity phù hợp.
2. Các entity được quản lý trong persistence context.
3. EntityManager.remove được gọi cho từng entity.
4. @PreRemove và entity lifecycle callback có thể được thực thi.
5. Cascade REMOVE và orphan removal được áp dụng theo mapping.
6. SQL DELETE được đồng bộ khi flush/commit.

Cơ chế này phù hợp khi thao tác xóa cần tuân thủ vòng đời entity và logic liên quan.

Với số lượng rất lớn, việc nạp mọi entity có thể tốn bộ nhớ. Nếu mục tiêu chỉ là xóa hàng loạt theo điều kiện và không cần callback/cascade JPA từng entity, có thể dùng bulk JPQL DELETE qua @Modifying. Hai cách có hành vi khác nhau và cần lựa chọn theo nghiệp vụ.

### 4.2. Xóa theo trạng thái

Ví dụ xóa các đơn hàng nháp đã quá hạn:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    long deleteByStatusAndCreatedAtBefore(
        OrderStatus status,
        Instant cutoff
    );
}
```

Service:

```java
@Transactional
public long removeExpiredDrafts(Instant cutoff) {
    return orderRepository.deleteByStatusAndCreatedAtBefore(
        OrderStatus.DRAFT,
        cutoff
    );
}
```

Trước khi xóa, hãy xác định rõ quy tắc nghiệp vụ: đơn nháp có được phép xóa không, có liên quan tới payment hoặc audit record không, có cần lưu lịch sử hay không. Nếu cần lưu dấu vết nghiệp vụ, soft delete hoặc chuyển trạng thái có thể phù hợp hơn xóa vật lý.

## 5. removeBy: alias của deleteBy

Spring Data JPA hỗ trợ removeBy như một cách đặt tên tương đương deleteBy:

```java
long removeByStatus(OrderStatus status);

long deleteByStatus(OrderStatus status);
```

Hai method đều diễn đạt xóa entity theo điều kiện. Nên thống nhất một quy ước đặt tên trong dự án để repository dễ đọc. deleteBy thường trực quan hơn khi người đọc muốn nhận diện ngay hành vi xóa.

Không hiểu removeBy là một cơ chế xóa khác, cũng không nhầm nó với EntityManager.remove(entity). Trong derived query, removeBy là tiền tố để Spring Data nhận diện delete query theo tên method.

## 6. Bulk delete bằng @Modifying và @Query

Nếu cần xóa rất nhiều dòng và không cần gọi callback/cascade JPA cho từng entity, có thể dùng bulk JPQL DELETE:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Modifying
    @Query("""
        delete from Customer c
        where c.active = false
          and c.createdAt < :cutoff
        """)
    int bulkDeleteInactiveBefore(
        @Param("cutoff") Instant cutoff
    );
}
```

Service:

```java
@Transactional
public int bulkDeleteInactive(Instant cutoff) {
    return customerRepository.bulkDeleteInactiveBefore(cutoff);
}
```

@Modifying báo cho Spring Data rằng @Query là thao tác thay đổi dữ liệu. Nó được dùng với query method khai báo bằng @Query; derived deleteBy không cần thêm @Modifying.

Bulk JPQL DELETE được thực hiện trực tiếp trên database. Nó không tải từng entity và không gọi EntityManager.remove cho từng entity. Vì vậy:

- @PreRemove và entity listener không được gọi cho từng entity.
- Cascade REMOVE của JPA không được thực hiện như khi xóa từng entity.
- orphanRemoval không tự chạy như thao tác thay đổi quan hệ entity.
- Persistence context có thể vẫn giữ entity đã bị xóa trong database.
- Database foreign key vẫn được áp dụng; nếu còn bản ghi con tham chiếu, câu DELETE có thể thất bại.
- Trigger và constraint ở database vẫn hoạt động theo quy tắc của hệ quản trị.

Bulk delete thường nhanh hơn khi số lượng bản ghi lớn, nhưng phải tự quản lý các hệ quả về quan hệ và trạng thái trong bộ nhớ.

### 6.1. flushAutomatically và clearAutomatically

@Modifying có hai thuộc tính hữu ích:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    delete from Customer c
    where c.active = false
    """)
int bulkDeleteInactive();
```

- **flushAutomatically = true** yêu cầu flush persistence context trước khi thực hiện query sửa dữ liệu, giúp đồng bộ các thay đổi pending.
- **clearAutomatically = true** yêu cầu clear persistence context sau khi query thực thi, tránh tiếp tục dùng các entity managed có thể đã lỗi thời.

clear() detach tất cả entity trong persistence context hiện tại, không chỉ những Customer đã bị xóa. Những object Java đang giữ vẫn tồn tại trong bộ nhớ nhưng không còn managed. Nếu cần tiếp tục sửa entity, hãy đọc lại hoặc merge theo đúng luồng.

Không bật clearAutomatically một cách máy móc nếu service đang dựa vào nhiều entity managed khác. Hãy xem xét ảnh hưởng tới toàn bộ persistence context.

## 7. Transaction khi dùng deleteBy và bulk delete

Các thao tác xóa phải chạy trong transaction phù hợp. Cách rõ ràng là đặt @Transactional ở service để bao quanh nghiệp vụ:

```java
@Service
public class CustomerCleanupService {

    private final CustomerRepository repository;

    public CustomerCleanupService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long deleteExpiredCustomers(Instant cutoff) {
        return repository.deleteByCreatedAtBefore(cutoff);
    }

    @Transactional(readOnly = true)
    public long countExpiredCustomers(Instant cutoff) {
        return repository.countByCreatedAtBefore(cutoff);
    }
}
```

Các CRUD methods kế thừa từ SimpleJpaRepository có transaction configuration mặc định. Query methods do ứng dụng tự khai báo không tự động nhận transaction configuration theo mặc định; hãy khai báo @Transactional ở service hoặc repository khi cần.

Nếu derived delete được gọi ngoài transaction phù hợp, thao tác có thể thất bại với TransactionRequiredException hoặc lỗi transaction tùy ngữ cảnh. Với bulk query có @Modifying, cũng cần transaction để thực thi UPDATE/DELETE.

Transaction bao quanh cả kiểm tra và xóa giúp nghiệp vụ có ranh giới rõ ràng, nhưng không tự giải quyết mọi race condition. Nếu dữ liệu có thể bị thay đổi đồng thời, hãy xác định isolation, locking hoặc constraint cần thiết.

## 8. Xóa entity và cascade

Giả sử Customer có các Order:

```java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.REMOVE,
    orphanRemoval = true
)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Khi derived deleteBy xóa từng Customer bằng EntityManager.remove, cascade REMOVE có thể xóa các Order theo mapping.

Khi bulk JPQL DELETE xóa Customer trực tiếp, JPA không duyệt từng Customer và không cascade REMOVE qua quan hệ như thao tác remove entity. Database có thể từ chối xóa vì foreign key hoặc thực hiện ON DELETE CASCADE nếu schema được thiết kế như vậy.

Không đặt cascade REMOVE chỉ để làm cho deleteBy chạy được. Hãy xác định entity nào thực sự phụ thuộc vòng đời vào entity nào. Với dữ liệu giao dịch như đơn hàng, hóa đơn và thanh toán, xóa vật lý có thể làm mất lịch sử; thường cần quy tắc lưu trữ và audit riêng.

## 9. Null, boolean và các toán tử trong tên method

Derived query hỗ trợ nhiều toán tử trong điều kiện:

```java
boolean existsByEmailIsNull();

boolean existsByEmailIsNotNull();

long countByStatusIn(Collection<OrderStatus> statuses);

long countByCreatedAtBetween(Instant from, Instant to);

long countByTotalAmountGreaterThanEqual(BigDecimal amount);

long deleteByStatusIn(Collection<OrderStatus> statuses);

long deleteByCreatedAtBefore(Instant cutoff);
```

Các từ khóa thường dùng:

| Keyword | Ý nghĩa |
|---|---|
| IsNull / Is | Kiểm tra NULL hoặc bằng giá trị |
| IsNotNull / NotNull | Kiểm tra khác NULL |
| True / False | Giá trị boolean |
| In / NotIn | Thuộc hoặc không thuộc tập giá trị |
| Between | Nằm trong khoảng |
| Before / After | Trước hoặc sau thời điểm/giá trị |
| LessThan / GreaterThan | So sánh nhỏ hơn/lớn hơn |
| LessThanEqual / GreaterThanEqual | So sánh có tính cả biên |
| IgnoreCase | So sánh không phân biệt hoa/thường cho kiểu phù hợp |
| And / Or | Kết hợp điều kiện |

Khi truyền null cho một equality predicate, Spring Data có thể diễn giải thành IS NULL; với Not và null, có thể thành IS NOT NULL. Tuy nhiên, đừng dựa vào null parameter để biểu diễn mọi bộ lọc tùy chọn. Nếu điều kiện phải bỏ qua khi tham số null, hãy xây dựng query động bằng Specification hoặc cách phù hợp.

## 10. countBy và existsBy trên dữ liệu lớn

existsBy và countBy không tải toàn bộ entity, nhưng vẫn cần database thực thi truy vấn. Hiệu năng phụ thuộc:

- Số lượng bản ghi và độ chọn lọc của điều kiện.
- Index có hỗ trợ cột lọc không.
- Join có đi qua quan hệ một-nhiều hay nhiều-nhiều không.
- Database optimizer và statistics.
- Transaction isolation và mức độ cập nhật đồng thời.

Ví dụ, kiểm tra tồn tại theo email thường cần index:

```sql
CREATE UNIQUE INDEX uk_customers_email
    ON customers (email);
```

Với email không phân biệt hoa/thường, cần thống nhất cách chuẩn hóa dữ liệu và index. Một index thông thường trên email có thể không hỗ trợ hiệu quả biểu thức lower(email) tùy database. Có thể dùng cột chuẩn hóa hoặc functional index nếu database hỗ trợ.

countBy thường phải đếm toàn bộ số bản ghi phù hợp. Nếu chỉ cần biết có ít nhất một bản ghi hay không, dùng existsBy thay vì countBy > 0 để thể hiện đúng ý định. Provider/database có thể tối ưu truy vấn exists theo cách riêng.

Không chạy existsBy rồi countBy ngay sau đó chỉ để kiểm tra cùng một điều kiện nếu không có nhu cầu nghiệp vụ riêng; hai query làm tăng round trip và kết quả vẫn có thể thay đổi giữa hai lần đọc.

## 11. Khi nào nên dùng @Query hoặc Specification?

Tên method phù hợp khi điều kiện đơn giản và có thể diễn đạt rõ bằng property path. Khi method trở nên dài, lồng nhiều And/Or, cần join đặc biệt, subquery, group by hoặc count distinct theo một thuộc tính cụ thể, hãy dùng @Query.

Ví dụ đếm số khách hàng có ít nhất một đơn đã xác nhận:

```java
@Query("""
    select count(c)
    from Customer c
    where exists (
        select o.id
        from PurchaseOrder o
        where o.customer = c
          and o.status = :status
    )
    """)
long countCustomersWithOrderStatus(
    @Param("status") OrderStatus status
);
```

Nếu bộ lọc thay đổi theo nhiều tham số tùy chọn, Specification/Criteria có thể dễ bảo trì hơn việc tạo hàng loạt method. Chọn cách truy vấn dựa trên ý nghĩa nghiệp vụ và SQL cần sinh ra, không cố ép mọi trường hợp vào derived query.

## 12. Kiểm thử repository methods

Nên kiểm tra cả giá trị trả về và dữ liệu thực tế sau thao tác. Với Spring Boot, @DataJpaTest phù hợp để kiểm tra mapping và repository query.

Ví dụ:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void existsCountAndDeleteUseTheExpectedPredicate() {
        repository.save(new Customer("a@example.com", true));
        repository.save(new Customer("b@example.com", false));
        repository.flush();

        assertThat(repository.existsByEmail("a@example.com")).isTrue();
        assertThat(repository.existsByEmail("missing@example.com")).isFalse();
        assertThat(repository.countByActiveTrue()).isEqualTo(1);

        long deleted = repository.deleteByActiveFalse();

        assertThat(deleted).isEqualTo(1);
        assertThat(repository.count()).isEqualTo(1);
    }
}
```

Đây là khung minh họa; constructor, getter và field bắt buộc cần được bổ sung theo entity thực tế. Nếu dùng entity có quan hệ, hãy tạo dữ liệu hợp lệ theo constraint trước khi kiểm tra.

Với derived delete, có thể kiểm thử @PreRemove hoặc cascade để xác nhận callback/lifecycle được thực thi. Với bulk delete, viết test riêng để xác nhận callback không được gọi và persistence context được clear/refresh đúng như cấu hình.

Test @DataJpaTest thường chạy trong transaction và rollback khi kết thúc. Nếu cần xác minh commit behavior hoặc tương tác giữa nhiều transaction, hãy tạo integration test có transaction boundary thật và database cùng loại production.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Method không được tạo khi khởi động | Tên property sai hoặc đường dẫn property mơ hồ | Đối chiếu entity field/getter và dùng dấu gạch dưới khi cần |
| existsBy trả false dù dữ liệu có | Sai điều kiện, khác hoa/thường hoặc dữ liệu đã chuẩn hóa khác | Kiểm tra SQL, parameter và collation |
| Hai request cùng đăng ký email | existsBy check-then-insert có race condition | Unique constraint ở database và xử lý duplicate key |
| countBy quá chậm | Thiếu index, join lớn hoặc count toàn bộ kết quả | Xem execution plan, index và cân nhắc query khác |
| countDistinctBy đếm không như mong đợi | Distinct áp dụng lên entity ID thay vì property cần đếm | Viết JPQL count(distinct property) |
| deleteBy xóa chậm với nhiều bản ghi | Derived delete tải entity và xóa từng entity | Cân nhắc bulk JPQL DELETE nếu không cần lifecycle |
| Bulk delete không gọi @PreRemove | Bulk query bỏ qua lifecycle entity | Dùng derived delete nếu callback là yêu cầu |
| Bulk delete vi phạm FK | Còn bản ghi con tham chiếu hoặc thiếu quy tắc xóa | Xóa child theo thứ tự, cascade DB có chủ đích hoặc đổi nghiệp vụ |
| Entity trong bộ nhớ vẫn tồn tại sau bulk delete | Persistence context chưa được clear | Dùng clearAutomatically hoặc clear/refresh có chủ đích |
| TransactionRequiredException | Thao tác xóa/ghi chạy ngoài transaction | Đặt @Transactional ở service hoặc repository |
| removeBy bị hiểu là API khác deleteBy | Nhầm hai tiền tố | Chúng là hai cách đặt tên cho derived delete |

## 14. Bài tập thực hành

1. Viết existsByEmail và existsByEmailIgnoreCase; kiểm tra dữ liệu khác hoa/thường.
2. Viết existsByCustomer_IdAndStatus để kiểm tra khách có đơn theo trạng thái.
3. Viết countByStatus và countByCreatedAtBetween; kiểm tra kết quả với dữ liệu mẫu.
4. Viết countDistinctByLastname rồi so sánh với JPQL count(distinct c.lastname).
5. Viết deleteByActiveFalse trả về long và xác nhận số entity bị xóa.
6. Viết removeByCreatedAtBefore và so sánh hành vi với deleteBy tương đương.
7. Tạo @PreRemove callback; xác nhận derived delete gọi callback.
8. Tạo bulk JPQL DELETE với @Modifying; xác nhận callback không được gọi.
9. Kiểm tra persistence context sau bulk delete và thử clearAutomatically.
10. Tạo hai transaction cùng đăng ký một email; chứng minh unique constraint bảo vệ dữ liệu.
11. Đo query countBy trên bảng lớn trước và sau khi thêm index.
12. Viết test integration để kiểm tra transaction rollback khi delete query thất bại.

**Nguyên tắc xuyên suốt:** existsBy trả lời có hay không; countBy trả về số lượng; deleteBy và removeBy xóa entity theo điều kiện. Derived delete thường tải entity rồi xóa từng entity nên giữ được lifecycle và cascade JPA nhưng có thể tốn bộ nhớ. Bulk JPQL DELETE nhanh hơn cho tập lớn nhưng bỏ qua lifecycle/cascade của entity và có thể làm persistence context lỗi thời. Hãy chọn theo quy tắc nghiệp vụ, transaction và kích thước dữ liệu.
