# Flush khác commit như thế nào?

Trong JPA, **flush** đồng bộ những thay đổi đang được quản lý trong persistence context xuống database bằng các câu SQL cần thiết. **Commit** kết thúc transaction ở database và xác nhận các thay đổi của transaction. Flush có thể gửi INSERT, UPDATE hoặc DELETE nhưng dữ liệu vẫn chưa được commit; transaction vẫn có thể rollback sau đó.

Đây là khác biệt quan trọng khi làm việc với Spring Data JPA. Gọi save(), flush() hoặc saveAndFlush() không đồng nghĩa dữ liệu đã được commit. Muốn hiểu thời điểm dữ liệu thực sự được xác nhận, cần theo dõi cả persistence context, transaction manager và ranh giới @Transactional.

## 1. Phân biệt persistence context, flush và commit

Persistence context là vùng làm việc của EntityManager. Nó quản lý các entity đang được theo dõi, identity của entity và những thay đổi phát sinh trong vòng đời entity.

Khi đọc một entity vào persistence context, entity thường ở trạng thái managed. Nếu thay đổi thuộc tính của entity managed, JPA provider ghi nhận thay đổi bằng dirty checking. SQL có thể chưa chạy ngay tại thời điểm setter được gọi.

Có thể hình dung:

```text
Java code thay đổi entity managed
             |
             v
     Persistence context
     (dirty checking)
             |
             | flush
             v
   INSERT / UPDATE / DELETE
             |
             v
       Database transaction
             |
             | commit
             v
     Transaction được xác nhận
```

Ba bước có ý nghĩa khác nhau:

- **Thay đổi trong persistence context:** trạng thái Java được cập nhật và provider theo dõi.
- **Flush:** provider đồng bộ thay đổi cần ghi xuống database bằng SQL trong transaction hiện tại.
- **Commit:** transaction manager/database xác nhận transaction; các thay đổi đã ghi trở thành dữ liệu đã commit theo quy tắc transaction và isolation của database.

Flush không xóa persistence context, không kết thúc transaction và không làm entity chuyển sang detached. Sau flush, entity vẫn managed và có thể tiếp tục thay đổi; lần flush tiếp theo có thể phát sinh SQL bổ sung.

## 2. Ví dụ: thay đổi entity nhưng chưa flush

Giả sử có entity Customer:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public void rename(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

Một service thay đổi entity:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void renameCustomer(Long id) {
        Customer customer = repository.findById(id).orElseThrow();

        customer.rename("An Nguyen");

        // Tại đây entity đã thay đổi trong persistence context.
        // SQL UPDATE có thể chưa được gửi xuống database.
    }
}
```

Khi gọi rename(), JPA không bắt buộc phải gửi UPDATE ngay. Entity đang managed nên dirty checking ghi nhận thuộc tính name đã thay đổi. Khi transaction flush, provider phát SQL UPDATE. Khi transaction commit, database xác nhận thay đổi.

Nếu method kết thúc bình thường, Spring transaction interceptor thường thực hiện commit sau khi thân method trả về. Vì vậy, dù code không gọi flush() hoặc commit(), thay đổi vẫn được ghi khi transaction kết thúc thành công.

Nếu method phát sinh exception thuộc chính sách rollback, transaction có thể bị rollback và thay đổi trong persistence context cùng SQL chưa commit sẽ không được xác nhận.

## 3. Flush không phải commit

Xét một transaction có các bước:

```java
@Transactional
public void updateCustomer(Long id) {
    Customer customer = repository.findById(id).orElseThrow();

    customer.rename("An Nguyen");

    entityManager.flush();

    // SQL UPDATE đã được gửi xuống database.
    // Transaction vẫn đang mở.

    customer.rename("An Tran");

    // Lần thay đổi thứ hai vẫn đang được theo dõi.
    // Có thể phát sinh UPDATE khác ở lần flush tiếp theo.
}
```

Sau lần flush đầu tiên, database đã nhận SQL UPDATE cho tên "An Nguyen", nhưng transaction chưa commit. Khi đổi tiếp thành "An Tran", persistence context ghi nhận trạng thái mới. Lúc commit, provider có thể flush thay đổi còn lại rồi commit transaction.

Nếu sau lần flush đầu tiên có lỗi và transaction rollback, cả câu UPDATE đã gửi trong transaction cũng bị rollback theo cơ chế của database. Việc SQL đã chạy không đồng nghĩa dữ liệu đã được xác nhận.

Flush thường dùng để buộc lỗi SQL xuất hiện sớm tại một điểm trong luồng xử lý, ví dụ kiểm tra unique constraint hoặc optimistic locking trước khi tiếp tục một bước nghiệp vụ khác. Tuy nhiên, lỗi deferred constraint hoặc lỗi chỉ được database phát hiện lúc commit vẫn có thể xuất hiện muộn hơn.

## 4. Commit thường tự flush trước khi xác nhận transaction

Khi transaction JPA được commit, provider phải đồng bộ các thay đổi cần thiết của persistence context trước khi transaction hoàn tất. Vì vậy, trong luồng thông thường, ứng dụng không cần gọi entityManager.flush() ngay trước mỗi commit.

Ví dụ:

```java
@Transactional
public void createCustomer() {
    Customer customer = new Customer("An");
    repository.save(customer);

    // Không cần gọi flush() chỉ để bảo đảm transaction
    // được ghi khi method kết thúc bình thường.
}
```

Khi method trả về bình thường, Spring transaction manager xử lý commit. Trong quá trình đó, JPA provider flush các thay đổi còn pending rồi database commit transaction.

Trình tự khái quát:

1. Service method chạy trong transaction.
2. Entity được persist hoặc thay đổi trong persistence context.
3. Method kết thúc bình thường.
4. Transaction manager yêu cầu commit.
5. JPA provider flush thay đổi cần thiết.
6. Database hoàn tất commit.
7. Transaction kết thúc; các tài nguyên transaction được giải phóng theo quản lý của Spring/provider.

Commit có thể thất bại dù các câu SQL đã chạy ở lần flush trước. Ví dụ database có deferred constraint, lỗi serialization, deadlock hoặc mất kết nối trong lúc commit. Ứng dụng phải xử lý lỗi tại ranh giới transaction, không chỉ dựa vào việc flush trước đó đã thành công.

## 5. SQL đã flush có được transaction khác nhìn thấy không?

Thông thường, dữ liệu chưa commit không hiển thị cho transaction khác khi dùng isolation READ COMMITTED. Tuy nhiên, transaction khác có thể bị chặn bởi khóa hoặc có hành vi phụ thuộc isolation level và database.

Trong cùng transaction, các câu query tiếp theo có thể nhìn thấy thay đổi đã flush của chính transaction đó. Điều này cho phép một nghiệp vụ ghi dữ liệu rồi truy vấn lại trong cùng transaction.

Ví dụ:

```java
@Transactional
public Customer createAndReadBack() {
    Customer customer = new Customer("An");
    repository.save(customer);

    entityManager.flush();

    return repository.findById(customer.getId()).orElseThrow();
}
```

Sau flush, câu query chạy trong cùng transaction có thể đọc bản ghi vừa insert. Một transaction khác thông thường chưa nhìn thấy bản ghi cho tới khi transaction hiện tại commit, tùy isolation level.

Cần phân biệt ba khái niệm:

- **Persistence context visibility:** entity managed và trạng thái trong bộ nhớ của transaction hiện tại.
- **Database transaction visibility:** dữ liệu mà các câu SQL trong transaction hiện tại nhìn thấy.
- **Cross-transaction visibility:** dữ liệu mà transaction khác được phép đọc theo isolation level.

Không dùng flush để thay thế commit khi cần công bố dữ liệu cho transaction khác hoặc hệ thống bên ngoài.

## 6. Khi nào JPA tự động flush?

JPA định nghĩa FlushModeType với hai chế độ chính: AUTO và COMMIT. Trong môi trường Spring Data JPA thông thường, AUTO là chế độ mặc định.

### 6.1. FlushModeType.AUTO

Với AUTO, provider phải bảo đảm các thay đổi trong persistence context có thể ảnh hưởng đến kết quả query được phản ánh khi query thực thi. Provider thường flush trước query liên quan, hoặc có thể dùng cách triển khai khác để bảo đảm kết quả theo hợp đồng JPA.

Ví dụ:

```java
@Transactional
public List<Customer> findCustomersAfterRename() {
    Customer customer = repository.findById(1L).orElseThrow();
    customer.rename("An Nguyen");

    return entityManager.createQuery("""
        select c
        from Customer c
        where c.name = :name
        """, Customer.class)
        .setParameter("name", "An Nguyen")
        .getResultList();
}
```

Nếu thay đổi name có thể ảnh hưởng đến kết quả query, provider phải bảo đảm query có kết quả phù hợp với trạng thái persistence context theo AUTO. Hibernate thường thực hiện flush trước query khi query space liên quan tới các bảng có thay đổi pending.

Không nên suy ra rằng mọi SELECT luôn làm flush toàn bộ persistence context. Hành vi cụ thể có thể phụ thuộc query, provider và các bảng mà query sử dụng.

### 6.2. FlushModeType.COMMIT

COMMIT yêu cầu provider flush trước khi transaction commit. Theo hợp đồng JPA, ảnh hưởng của các thay đổi chưa flush trong persistence context lên kết quả query là không xác định nếu query chạy trước commit.

```java
entityManager.setFlushMode(FlushModeType.COMMIT);
```

Chế độ này có thể giảm flush sớm trong một số luồng, nhưng cần thận trọng nếu query phải phản ánh ngay các thay đổi pending. Hibernate còn có các FlushMode riêng như MANUAL; đó là API/provider behavior riêng, không đồng nhất với hai mode chuẩn JPA.

Không thay đổi flush mode chỉ để chữa một vấn đề hiệu năng chưa được đo. Hãy kiểm tra SQL và xác định query nào thực sự kích hoạt flush.

## 7. entityManager.flush() làm gì?

Gọi:

```java
entityManager.flush();
```

yêu cầu provider đồng bộ thay đổi của persistence context hiện tại xuống database. Tùy trạng thái entity, SQL có thể gồm:

- INSERT cho entity mới được persist.
- UPDATE cho entity managed đã thay đổi.
- DELETE cho entity đã bị remove.
- Các câu SQL liên quan tới quan hệ, collection hoặc bảng trung gian.

Flush áp dụng cho persistence context được EntityManager quản lý, không chỉ một entity mà người gọi đang quan tâm. Nếu có nhiều entity pending trong cùng persistence context, provider có thể đồng bộ tất cả thay đổi cần thiết.

Flush không:

- Commit transaction.
- Rollback transaction.
- Clear persistence context.
- Detach entity.
- Bắt buộc đóng EntityManager.
- Bảo đảm transaction khác nhìn thấy dữ liệu chưa commit.
- Bảo đảm mọi constraint deferred đã được kiểm tra.

Gọi flush khi không có transaction phù hợp thường dẫn tới TransactionRequiredException. Với EntityManager do Spring quản lý, hãy để transaction manager điều khiển vòng đời transaction; không tự gọi commit() trên EntityManager được inject qua @PersistenceContext.

## 8. save(), saveAndFlush() và flush() trong Spring Data JPA

Ba method này thường bị hiểu nhầm:

| Method | Ý nghĩa |
|---|---|
| save(entity) | Yêu cầu repository persist entity mới hoặc merge entity hiện có theo cơ chế Spring Data |
| saveAndFlush(entity) | Save entity rồi yêu cầu flush persistence context |
| flush() | Yêu cầu flush các thay đổi pending trong persistence context |

Ví dụ:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void saveCustomer() {
        Customer customer = new Customer("An");

        Customer saved = repository.save(customer);

        // Save đã được yêu cầu; SQL có thể vẫn chưa chạy.
        repository.flush();

        // Thay đổi sau flush vẫn thuộc transaction hiện tại.
        saved.rename("An Nguyen");
    }
}
```

Repository save() không có nghĩa database đã commit. Với entity mới, Spring Data thường dùng persist; với entity được xem là đã tồn tại, nó có thể dùng merge. merge trả về một instance managed; caller nên dùng instance được trả về vì object truyền vào có thể vẫn detached.

saveAndFlush():

```java
@Transactional
public Customer saveImmediately() {
    Customer customer = new Customer("An");
    return repository.saveAndFlush(customer);
}
```

saveAndFlush() thực hiện save rồi flush. Nó không tự commit một transaction bao ngoài. Nếu method service đang chạy trong @Transactional, transaction tiếp tục mở sau khi saveAndFlush trả về và có thể rollback sau đó.

Nếu gọi một repository method độc lập mà không có transaction bao ngoài, transaction mặc định của repository method có thể kết thúc khi method trả về. Khi ấy commit diễn ra ở ranh giới transaction do Spring Data/Spring quản lý. Đó là lý do phải phân biệt tác dụng của flush với transaction boundary thực tế.

## 9. Flush giúp phát hiện lỗi sớm

Một số lỗi chỉ xuất hiện khi SQL được gửi xuống database:

- Vi phạm unique constraint.
- Vi phạm foreign key hoặc NOT NULL.
- Giá trị vượt độ dài column.
- Kiểu dữ liệu không tương thích.
- Optimistic locking conflict do version không còn khớp.
- Lỗi SQL hoặc constraint khác từ database.

Ví dụ kiểm tra mã khách hàng trùng:

```java
@Transactional
public void registerCustomer(String name, String email) {
    Customer customer = new Customer(name, email);

    repository.save(customer);
    entityManager.flush();

    // Nếu unique constraint được kiểm tra ở INSERT,
    // lỗi có thể xuất hiện ngay tại flush().
    sendRegistrationNotification(customer);
}
```

Ví dụ này cần cân nhắc ranh giới nghiệp vụ: gửi notification trước khi transaction commit có thể thông báo thành công dù transaction sau đó rollback. Trong hệ thống thực tế, nên gửi sự kiện sau commit hoặc dùng transactional outbox nếu cần bảo đảm nhất quán giữa database và message delivery.

Flush sớm giúp lỗi persistence xuất hiện trước khi thực hiện thêm công việc. Nhưng nó không biến transaction thành công ngay lập tức. Nếu flush ném lỗi, transaction thường cần rollback. Không bắt exception rồi tiếp tục ghi trong một transaction đã bị đánh dấu rollback-only hoặc database transaction đã ở trạng thái lỗi.

## 10. Optimistic locking có thể lỗi ở flush hoặc commit

Với entity có @Version:

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    protected Product() {
    }
}
```

Provider dùng version trong câu UPDATE để phát hiện một transaction khác đã sửa bản ghi:

```sql
UPDATE products
SET name = ?, version = ?
WHERE id = ? AND version = ?;
```

Nếu không có dòng nào được cập nhật do version đã đổi, provider phát hiện optimistic locking conflict. Lỗi thường xuất hiện khi flush thực thi UPDATE, hoặc có thể được báo ở commit tùy thời điểm provider đồng bộ thay đổi.

Không nên giả định setter hoặc save() sẽ phát hiện xung đột ngay. Nếu nghiệp vụ cần bắt lỗi trước khi thực hiện bước tiếp theo, có thể flush có chủ đích, nhưng vẫn phải xử lý transaction rollback.

## 11. Flush và batching khi ghi nhiều entity

Flush quá thường xuyên có thể làm mất lợi ích batching. Ví dụ vòng lặp gọi saveAndFlush cho từng bản ghi sẽ yêu cầu đồng bộ liên tục:

```java
// Không phù hợp cho batch lớn nếu mỗi lần đều flush.
for (Customer customer : customers) {
    repository.saveAndFlush(customer);
}
```

Cách thường dùng là ghi theo từng lô, flush rồi clear persistence context:

```java
@Transactional
public void importCustomers(List<Customer> customers) {
    int batchSize = 50;

    for (int i = 0; i < customers.size(); i++) {
        entityManager.persist(customers.get(i));

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

flush gửi các thay đổi của lô hiện tại xuống database. clear detach tất cả entity khỏi persistence context để giảm bộ nhớ khi xử lý dữ liệu lớn. Sau clear, các object cũ không còn managed; nếu cần sửa tiếp, phải đọc lại hoặc merge phù hợp.

Batch size 50 chỉ là ví dụ. Cần điều chỉnh theo Hibernate jdbc.batch_size, JDBC driver, database và kích thước entity graph. Nếu dùng IDENTITY, Hibernate thường không batch insert entity theo cơ chế JDBC batching thông thường. Sequence có thể thuận lợi hơn khi cấp ID trước insert.

Không clear trước khi flush nếu muốn giữ các thay đổi pending: clear detach entity và có thể khiến các thay đổi chưa được đồng bộ bị mất khỏi persistence context.

## 12. Flush, bulk update và persistence context

JPQL bulk update/delete thao tác trực tiếp trên database và bỏ qua dirty checking của từng entity. Vì thế, entity đã được load trước đó có thể vẫn giữ giá trị cũ trong persistence context.

Ví dụ:

```java
@Transactional
public void deactivateAllCustomers() {
    Customer customer = entityManager.find(Customer.class, 1L);

    entityManager.createQuery("""
        update Customer c
        set c.active = false
        where c.active = true
        """).executeUpdate();

    // customer có thể vẫn giữ active=true trong bộ nhớ.
}
```

Có thể dùng flush và clear để đồng bộ thay đổi pending trước bulk query rồi loại entity managed khỏi persistence context sau bulk query:

```java
@Transactional
public void deactivateAllCustomers() {
    entityManager.flush();

    entityManager.createQuery("""
        update Customer c
        set c.active = false
        where c.active = true
        """).executeUpdate();

    entityManager.clear();
}
```

Spring Data @Modifying có các thuộc tính flushAutomatically và clearAutomatically để điều khiển flush/clear quanh bulk query. Chỉ bật clearAutomatically khi hiểu rằng các entity đang managed sẽ bị detach; caller không thể tiếp tục dựa vào trạng thái managed cũ.

## 13. Rollback sau flush

Một transaction có thể flush thành công rồi vẫn rollback:

```java
@Transactional
public void createThenReject() {
    Customer customer = new Customer("An");
    repository.save(customer);

    entityManager.flush();

    throw new IllegalStateException("Business rule rejected");
}
```

Nếu exception kích hoạt rollback theo chính sách Spring, database rollback transaction. INSERT đã flush nhưng chưa commit sẽ không còn là dữ liệu đã xác nhận.

Tuy nhiên, một số bộ cấp ID như sequence hoặc identity có thể đã tiêu thụ giá trị trước rollback. Việc rollback transaction không nhất thiết đưa sequence/counter trở về giá trị cũ. Do đó, ID kỹ thuật có thể có khoảng trống; không dùng ID sinh tự động làm số chứng từ bắt buộc liên tục.

Nếu exception bị bắt bên trong method và không được ném ra ngoài, transaction có thể vẫn commit nếu chưa bị đánh dấu rollback-only. Nhưng lỗi SQL trong lúc flush thường khiến transaction không thể tiếp tục an toàn. Hãy rollback khi persistence operation thất bại, rồi xử lý ở transaction mới nếu cần.

## 14. Transaction boundary trong Spring

Với @Transactional, Spring transaction interceptor bắt đầu hoặc tham gia transaction trước khi gọi method, sau đó commit/rollback khi method kết thúc theo propagation và rollback rules.

```java
@Service
public class OrderService {

    @Transactional
    public void confirmOrder(Long id) {
        // Load entity.
        // Thay đổi trạng thái.
        // Có thể flush khi cần phát hiện lỗi sớm.
    }
}
```

Không gọi entityManager.getTransaction().commit() trên EntityManager được Spring quản lý qua @PersistenceContext. Với transaction do Spring quản lý, hãy dùng @Transactional hoặc TransactionTemplate. Việc tự commit có thể gây lỗi hoặc phá vỡ quản lý transaction của Spring.

Một method transactional được gọi qua Spring proxy sẽ có transaction boundary. Gọi một method khác cùng class bằng this.method() thường không đi qua proxy, nên annotation ở method được gọi nội bộ có thể không được áp dụng như mong đợi.

Propagation cũng ảnh hưởng transaction boundary. REQUIRED thường tham gia transaction hiện tại hoặc tạo transaction mới nếu chưa có. REQUIRES_NEW tạm dừng transaction ngoài và tạo transaction riêng; transaction mới có thể commit độc lập dù transaction ngoài rollback. Flush trong transaction ngoài vẫn chưa làm nó commit.

## 15. Kiểm thử flush và commit

Trong test persistence, save() có thể chưa gửi SQL. Nếu muốn kiểm tra constraint hoặc SQL mapping ngay tại test, hãy gọi flush:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void persistsCustomer() {
        Customer customer = new Customer("An");

        repository.save(customer);
        repository.flush();

        assertThat(customer.getId()).isNotNull();
    }
}
```

Test này xác nhận thao tác flush thực hiện thành công trong transaction test. Nhưng nhiều test của Spring Boot chạy trong transaction được rollback khi kết thúc. Do đó, nó không chứng minh transaction đã commit thành công.

Để kiểm tra commit behavior, cần tạo transaction boundary thực tế, ví dụ dùng TransactionTemplate hoặc một integration test không tự động rollback, đồng thời xác nhận dữ liệu từ transaction mới sau khi transaction đầu tiên commit.

Khi kiểm thử lỗi constraint, flush thường giúp lỗi xuất hiện tại dòng test dễ xác định hơn. Tuy nhiên, với deferred constraint hoặc lỗi chỉ phát sinh khi commit, vẫn cần kiểm thử commit thật.

## 16. Bảng so sánh nhanh

| Tiêu chí | Flush | Commit |
|---|---|---|
| Mục đích | Đồng bộ persistence context xuống database | Kết thúc transaction và xác nhận thay đổi |
| Gửi SQL | Có thể gửi INSERT/UPDATE/DELETE | Thường flush pending changes trước khi commit |
| Kết thúc transaction | Không | Có |
| Có thể rollback sau đó | Có | Transaction đã commit thì không thể rollback lại |
| Persistence context | Vẫn hoạt động, entity vẫn managed | Transaction kết thúc; entity không tự động trở thành detached chỉ vì commit, nhưng phạm vi quản lý transaction đã kết thúc |
| Transaction khác nhìn thấy | Thông thường chưa, tùy isolation | Có thể nhìn thấy theo isolation/commit visibility |
| Phát hiện lỗi constraint | Nhiều lỗi xuất hiện tại flush | Một số lỗi vẫn chỉ xuất hiện tại commit |

## 17. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi save() nhưng SQL chưa chạy | Thay đổi đang nằm trong persistence context | Flush khi cần đồng bộ sớm; transaction commit sẽ flush pending changes |
| Nghĩ saveAndFlush() đã commit | Nhầm flush với commit | Kiểm tra transaction boundary của service/repository |
| Transaction khác chưa thấy dữ liệu | SQL đã flush nhưng transaction chưa commit | Commit transaction và xem isolation level |
| Lỗi unique xuất hiện cuối method | Constraint chỉ được kiểm tra khi flush/commit | Flush tại điểm cần phát hiện lỗi sớm; vẫn xử lý lỗi commit |
| Test pass nhưng production commit lỗi | Test chỉ flush rồi rollback, không kiểm tra commit | Thêm integration test commit thật |
| Gọi flush ngoài transaction bị lỗi | Không có transaction phù hợp | Chạy trong @Transactional hoặc transaction manager phù hợp |
| Bắt lỗi flush rồi tiếp tục ghi | Transaction có thể đã rollback-only hoặc database transaction bị abort | Rollback và xử lý trong transaction mới |
| Batch insert chậm | Flush quá thường xuyên hoặc IDENTITY hạn chế batching | Flush theo lô, đo JDBC batching và cân nhắc sequence |
| Entity cũ sau bulk update | Bulk query bỏ qua trạng thái managed | Flush trước, clear/refresh sau theo nhu cầu |

## 18. Bài tập thực hành

1. Tạo Customer mới bằng repository.save() và quan sát thời điểm SQL INSERT được gửi.
2. Gọi entityManager.flush() giữa transaction, sau đó kiểm tra transaction vẫn đang hoạt động.
3. Sau flush, đổi tiếp một thuộc tính và xác nhận lần flush/commit sau ghi thay đổi mới.
4. Tạo unique constraint và thử insert trùng; so sánh thời điểm lỗi khi không flush và khi flush tường minh.
5. Flush thành công rồi ném RuntimeException; xác nhận transaction rollback và bản ghi không được commit.
6. Chạy hai transaction để quan sát transaction thứ hai chưa thấy dữ liệu chưa commit theo READ COMMITTED.
7. Dùng FlushModeType.COMMIT và so sánh query behavior với AUTO trên provider đang dùng.
8. So sánh save(), saveAndFlush() và flush() trong một service có @Transactional.
9. Import nhiều entity theo lô bằng flush/clear và quan sát memory cùng số lượng SQL batch.
10. Viết test có commit thật để phân biệt lỗi flush và lỗi commit.

**Nguyên tắc xuyên suốt:** flush gửi các thay đổi pending của persistence context xuống database trong transaction hiện tại; commit xác nhận transaction. Sau flush, transaction vẫn có thể rollback và transaction khác thường chưa nhìn thấy dữ liệu. Dùng flush khi cần đồng bộ sớm hoặc phát hiện lỗi persistence tại một điểm cụ thể; để Spring transaction manager điều khiển commit/rollback ở ranh giới @Transactional.
