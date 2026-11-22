# Flush ORM để phát hiện lỗi mà persistence context đang che

Trong ứng dụng dùng JPA/Hibernate, gọi repository.save() hoặc thay đổi một entity đã được quản lý chưa chắc khiến SQL được gửi xuống database ngay lập tức. ORM thường giữ entity trong persistence context và trì hoãn việc ghi dữ liệu cho đến một thời điểm phù hợp, chẳng hạn khi transaction commit hoặc khi cần đồng bộ trước một truy vấn.

Cơ chế trì hoãn này giúp ORM gom thay đổi, quản lý dirty checking và tối ưu thao tác database. Nhưng nó cũng tạo ra một rủi ro trong kiểm thử: test có thể đọc lại đúng giá trị từ object đang nằm trong bộ nhớ và kết luận rằng dữ liệu đã được lưu thành công, trong khi SQL chưa từng chạy. Những lỗi như vi phạm unique constraint, foreign key, kiểu dữ liệu, câu lệnh SQL hoặc mapping có thể chỉ xuất hiện khi ORM thực sự gửi lệnh xuống database.

Trong Spring Framework Testing, đặc biệt với @DataJpaTest và test chạy trong transaction, cần hiểu rõ **flush** để buộc persistence context đồng bộ với database tại thời điểm test muốn kiểm tra. Kết hợp flush với clear giúp tránh việc first-level cache trả lại chính object đang nằm trong bộ nhớ.

## 1. Persistence context và cơ chế write-behind

JPA quản lý các entity thông qua persistence context. Trong một persistence context, mỗi entity có identity tương ứng với kiểu và khóa chính; khi một entity đã được quản lý, EntityManager theo dõi trạng thái của nó.

Các trạng thái entity thường gặp:

- **New / transient**: object mới được tạo, chưa được persistence context quản lý.
- **Managed**: entity đang được quản lý; thay đổi trên object có thể được ORM phát hiện.
- **Detached**: entity từng được quản lý nhưng đã rời persistence context.
- **Removed**: entity được đánh dấu xóa và sẽ bị xóa khi persistence context đồng bộ.

Ví dụ:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
}
~~~

Khi gọi setName(), Hibernate thường không chạy UPDATE ngay tại dòng lệnh đó. Entity vẫn ở trạng thái managed, và Hibernate ghi nhận rằng thuộc tính name đã thay đổi. Trong quá trình flush, dirty checking phát hiện khác biệt và tạo SQL UPDATE tương ứng.

Đây là cơ chế thường được gọi là **write-behind**: thay đổi được giữ trong persistence context trước, sau đó được đồng bộ xuống database.

Luồng khái quát:

~~~text
entityManager.find(...)
        |
        v
Entity ở trạng thái managed
        |
        v
Thay đổi thuộc tính trên object
        |
        v
Persistence context ghi nhận state mới
        |
        | Chưa nhất thiết có SQL
        v
flush()
        |
        v
Hibernate kiểm tra dirty state
        |
        v
Tạo và gửi INSERT / UPDATE / DELETE
        |
        v
Database thực thi SQL và kiểm tra constraint
~~~

Vì vậy, một assertion trên object managed chỉ chứng minh object trong bộ nhớ có giá trị mong muốn. Nó chưa chứng minh database đã chấp nhận thay đổi đó.

## 2. Flush là gì?

Trong JPA, flush là thao tác đồng bộ trạng thái của persistence context với database. Với Hibernate, quá trình này thường bao gồm:

- Phát hiện entity mới cần INSERT.
- Phát hiện entity managed bị thay đổi và cần UPDATE.
- Phát hiện entity bị đánh dấu xóa và cần DELETE.
- Thực thi các câu SQL cần thiết theo thứ tự do ORM quản lý.
- Để database kiểm tra các constraint được áp dụng tại thời điểm thực thi.

Có thể gọi flush qua EntityManager:

~~~java
entityManager.flush();
~~~

Hoặc qua Spring Data JPA repository nếu repository kế thừa JpaRepository:

~~~java
customerRepository.flush();
~~~

Cả hai đều yêu cầu persistence context đồng bộ các thay đổi đang chờ. Khi gọi repository.flush(), thao tác không chỉ áp dụng cho entity vừa được save qua repository đó; nó có thể flush các thay đổi pending khác trong cùng persistence context.

Ví dụ:

~~~java
@Test
void shouldFlushPendingCustomerChanges() {
    Customer customer = new Customer("Lan", "lan@example.test");

    customerRepository.save(customer);

    entityManager.flush();

    assertNotNull(customer.getId());
}
~~~

Test chủ động yêu cầu ORM gửi SQL trước khi assertion tiếp tục. Nếu INSERT vi phạm constraint hoặc SQL không hợp lệ, lỗi có thể xuất hiện ngay tại flush thay vì đợi đến cuối transaction.

Lưu ý: flush không đồng nghĩa với commit. Nó gửi các câu lệnh cần thiết trong transaction hiện tại; transaction vẫn có thể rollback sau đó.

## 3. Phân biệt save(), flush() và commit()

Ba thao tác này có trách nhiệm khác nhau:

| Thao tác | Trách nhiệm | Có kết thúc transaction không? |
|---|---|---|
| repository.save(entity) | Yêu cầu Spring Data JPA persist hoặc merge entity | Không |
| entityManager.flush() / repository.flush() | Đồng bộ thay đổi pending trong persistence context xuống database | Không |
| transaction commit | Kết thúc transaction thành công và xác nhận các thay đổi theo transaction semantics | Có |

### 3.1. save() không đảm bảo SQL đã chạy

Spring Data JPA save() thường chọn EntityManager.persist() cho entity mới hoặc EntityManager.merge() cho entity được xem là đã tồn tại theo quy tắc của repository.

Cả persist() và merge() đều không có nghĩa rằng mọi SQL đã được gửi ngay tại thời điểm phương thức trả về.

~~~java
Customer customer = new Customer("Lan", "lan@example.test");

Customer saved = customerRepository.save(customer);

// Entity có thể đã được quản lý, nhưng INSERT có thể vẫn đang pending.
~~~

Với entity dùng sequence, Hibernate có thể lấy giá trị khóa chính sớm trước khi INSERT. Vì vậy, ID khác null cũng không chứng minh INSERT đã thành công.

Với IDENTITY generation, provider thường cần INSERT sớm hơn để lấy khóa chính do database sinh ra. Nhưng không nên dựa vào khác biệt chiến lược sinh ID để bỏ qua việc flush khi mục tiêu là kiểm tra SQL và constraint.

### 3.2. flush() không commit

~~~java
entityManager.flush();

// SQL đã được gửi trong transaction hiện tại.
// Transaction vẫn có thể rollback.
~~~

Nếu một test dùng @Transactional và mặc định rollback, dữ liệu có thể đã được INSERT hoặc UPDATE tại flush nhưng vẫn bị rollback khi test kết thúc.

Đây chính là điều ta muốn trong nhiều repository test: phát hiện lỗi SQL ngay trong test nhưng không để dữ liệu tồn tại sau đó.

### 3.3. Commit có thể phát hiện thêm lỗi

Flush thường phát hiện các lỗi xảy ra khi database thực thi SQL. Tuy nhiên, một số constraint hoặc thao tác có thể được database trì hoãn đến commit, ví dụ deferred constraint trên một số hệ quản trị.

Do đó:

- Flush giúp phát hiện sớm nhiều lỗi persistence.
- Flush không bảo đảm mọi điều kiện chỉ được kiểm tra tại commit đã được xác minh.
- Nếu yêu cầu cần kiểm tra hành vi commit thật, cần một test có transaction boundary phù hợp, thay vì giả định flush tương đương commit.

## 4. Vì sao persistence context có thể che lỗi?

Một test có thể thao tác trên cùng object đang được quản lý:

~~~java
@Test
void shouldUpdateCustomerName() {
    Customer customer = customerRepository.findById(1L).orElseThrow();

    customer.setName("Lan Nguyen");

    Customer loadedAgain =
            customerRepository.findById(1L).orElseThrow();

    assertEquals("Lan Nguyen", loadedAgain.getName());
}
~~~

Assertion có thể xanh ngay cả khi Hibernate chưa gửi UPDATE xuống database. Lần findById thứ hai có thể trả về cùng entity instance từ first-level cache của persistence context.

Trong cùng persistence context, JPA bảo đảm một entity identity được đại diện bởi cùng managed instance. Vì vậy, đọc lại bằng repository không nhất thiết tạo một SELECT mới.

Điều này có thể che các lỗi như:

- UPDATE không hợp lệ vì tên cột hoặc mapping sai.
- INSERT/UPDATE vi phạm unique constraint.
- Foreign key không tồn tại.
- Giá trị vượt quá độ dài cột.
- Kiểu dữ liệu không tương thích.
- SQL sinh ra không phù hợp dialect của database.
- Mapping quan hệ hoặc cascade khiến câu lệnh cần thiết không được thực thi như mong đợi.

Một test chỉ đọc lại managed entity có thể không chạm tới database ở thời điểm assertion. Muốn kiểm tra persistence thực sự, cần buộc flush và khi cần, loại entity khỏi persistence context trước khi đọc lại.

## 5. Mẫu kiểm thử cơ bản: save rồi flush

Một bài test repository có thể viết:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldInsertCustomerIntoDatabase() {
        Customer customer =
                new Customer("Lan", "lan@example.test");

        customerRepository.save(customer);

        entityManager.flush();

        assertNotNull(customer.getId());
    }
}
~~~

Flush giúp database thực thi INSERT trước khi test kết thúc. Tuy nhiên, assertion trên ID vẫn chưa phải bằng chứng mạnh nhất về việc đọc lại dữ liệu từ database. Để xác minh round-trip, hãy kết hợp clear và truy vấn lại.

## 6. Kết hợp flush() và clear() để kiểm tra database round-trip

EntityManager.clear() xóa toàn bộ entity khỏi persistence context và chuyển các entity managed thành detached. Sau đó, khi truy vấn lại, ORM không thể trả về cùng managed instance từ first-level cache của persistence context cũ.

Mẫu thường dùng:

~~~java
@Test
void shouldPersistAndReloadCustomer() {
    Customer customer =
            new Customer("Lan", "lan@example.test");

    customerRepository.save(customer);

    entityManager.flush();
    entityManager.clear();

    Customer reloaded = customerRepository
            .findById(customer.getId())
            .orElseThrow();

    assertEquals("Lan", reloaded.getName());
    assertEquals("lan@example.test", reloaded.getEmail());
}
~~~

Ý nghĩa của từng bước:

1. save() đưa entity vào quy trình persist/merge của JPA.
2. flush() buộc các thay đổi pending được gửi xuống database.
3. clear() loại entity managed khỏi persistence context.
4. findById() phải tải entity lại qua persistence layer.
5. Assertion xác minh dữ liệu được đọc lại có giá trị mong đợi.

Đây là cách kiểm tra mạnh hơn việc chỉ assert trên object vừa save.

Cần nhớ clear() tác động lên toàn bộ persistence context, không chỉ entity vừa lưu. Mọi entity đang managed đều trở thành detached. Nếu test còn cần các object đó, hãy lưu ID hoặc giá trị cần so sánh trước khi clear.

## 7. clear() khác refresh() như thế nào?

Hai phương thức đều giúp tránh dựa hoàn toàn vào trạng thái hiện tại của object, nhưng mục đích khác nhau.

**clear()**

- Detach tất cả entity trong persistence context.
- Không tự tải lại entity.
- Các truy vấn tiếp theo phải tìm entity qua persistence context trống hoặc database.
- Phù hợp khi muốn kiểm tra round-trip bằng cách truy vấn lại.

**refresh(entity)**

- Yêu cầu EntityManager tải lại state của một entity managed từ database.
- Ghi đè các thay đổi chưa flush đang nằm trong object bằng trạng thái database.
- Chỉ áp dụng cho entity đang managed.
- Phù hợp khi muốn đồng bộ lại một entity cụ thể với dữ liệu hiện có trong database.

Ví dụ dùng refresh:

~~~java
@Test
void shouldRefreshCustomerFromDatabase() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    customer.setName("Unsaved name");

    entityManager.refresh(customer);

    assertNotEquals("Unsaved name", customer.getName());
}
~~~

Ở đây, thay đổi chưa flush bị bỏ đi và state được đọc lại từ database. Nếu muốn kiểm tra một thay đổi đã được lưu, hãy flush trước khi refresh:

~~~java
customer.setName("Lan Nguyen");

entityManager.flush();
entityManager.refresh(customer);

assertEquals("Lan Nguyen", customer.getName());
~~~

refresh() không thay thế cho clear() trong mọi tình huống. Nếu muốn kiểm tra quy trình tải lại entity như một lần truy vấn thông thường, flush + clear + find thường thể hiện ý định rõ hơn.

## 8. Phát hiện unique constraint chỉ khi flush

Một trong những ví dụ quan trọng nhất là kiểm tra dữ liệu trùng.

Giả sử bảng customer có unique constraint trên email:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email)
);
~~~

Test tạo hai khách hàng có cùng email:

~~~java
@DataJpaTest
class CustomerConstraintTest {

    @Autowired
    private CustomerRepository customerRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldRejectDuplicateEmailWhenFlushed() {
        customerRepository.save(
                new Customer("Lan", "same@example.test")
        );

        customerRepository.save(
                new Customer("Minh", "same@example.test")
        );

        assertThrows(
                PersistenceException.class,
                entityManager::flush
        );
    }
}
~~~

Nếu bỏ flush, hai lệnh save có thể chỉ đăng ký các entity trong persistence context. Test method có thể đi đến cuối mà chưa thấy lỗi; lỗi chỉ xuất hiện khi transaction được flush trong quá trình hoàn tất.

Với flush tường minh, test xác định rõ thời điểm mong đợi database từ chối dữ liệu trùng.

Kiểu exception cụ thể có thể khác giữa JPA provider, Spring exception translation và database. Khi viết assertion, hãy chọn mức exception phù hợp với API đang gọi. Ví dụ trên gọi EntityManager trực tiếp và dùng PersistenceException theo hợp đồng JPA. Nếu test gọi repository method và dựa vào exception translation của Spring Data, có thể cần kiểm tra DataIntegrityViolationException hoặc exception tương ứng của dự án.

Một số database hỗ trợ deferred unique constraint. Nếu constraint được cấu hình chỉ kiểm tra ở commit, flush có thể chưa phát hiện lỗi. Hãy kiểm tra semantics của hệ quản trị database đang dùng.

## 9. Phát hiện lỗi foreign key

Giả sử order phải tham chiếu đến customer tồn tại:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
~~~

Nếu tạo order với customer_id không tồn tại, lỗi có thể xuất hiện khi INSERT thực thi:

~~~java
@Test
void shouldRejectOrderWithMissingCustomer() {
    Order order = new Order(999999L, new BigDecimal("250000"));

    orderRepository.save(order);

    assertThrows(
            PersistenceException.class,
            entityManager::flush
    );
}
~~~

Nếu quan hệ được ánh xạ bằng @ManyToOne và code gán một object customer không tồn tại, kết quả còn phụ thuộc cách tạo reference, cascade và mapping. Để kiểm tra foreign key ở database, cần chắc chắn SQL INSERT thực sự được gửi và database có constraint tương ứng.

Flush giúp buộc INSERT/UPDATE xảy ra trước assertion, nhờ đó test không chỉ kiểm tra object graph trong bộ nhớ.

## 10. Phát hiện lỗi độ dài cột và kiểu dữ liệu

Giả sử cột name có giới hạn VARCHAR(100), nhưng test lưu một chuỗi dài hơn giới hạn thực tế. JPA có thể vẫn giữ chuỗi đó trong object mà chưa gửi SQL.

~~~java
@Test
void shouldExposeColumnLengthViolationOnFlush() {
    String longName = "A".repeat(500);

    customerRepository.save(
            new Customer(longName, "long@example.test")
    );

    assertThrows(
            PersistenceException.class,
            entityManager::flush
    );
}
~~~

Khả năng database từ chối chuỗi dài phụ thuộc hệ quản trị và chế độ SQL. Một số hệ thống có thể báo lỗi, một số có thể cắt dữ liệu hoặc áp dụng quy tắc khác. Hãy chạy test trên database tương thích với production nếu giới hạn cột là rủi ro quan trọng.

Tương tự, flush có thể phát hiện lỗi chuyển đổi kiểu dữ liệu, precision/scale của decimal, NOT NULL, check constraint và các ràng buộc khác khi database thực thi SQL.

Không nên giả định Hibernate sẽ luôn kiểm tra mọi constraint ở Java trước khi gửi SQL. Một số validation có thể chạy trước, nhưng database vẫn là nơi thực thi các constraint thực tế.

## 11. Kiểm tra dirty checking bằng flush và clear

Dirty checking là cơ chế ORM phát hiện thay đổi trên entity managed mà không cần gọi save() lần nữa.

Ví dụ:

~~~java
@Test
void shouldPersistManagedEntityChanges() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    customer.setName("Updated name");

    entityManager.flush();
    entityManager.clear();

    Customer reloaded =
            customerRepository.findById(1L).orElseThrow();

    assertEquals("Updated name", reloaded.getName());
}
~~~

Test này xác minh:

- Entity được tải ở trạng thái managed.
- Thay đổi thuộc tính được Hibernate phát hiện.
- Flush tạo và gửi UPDATE.
- Clear loại object cũ khỏi persistence context.
- Truy vấn mới đọc state đã lưu.

Trong JPA, nếu entity đang managed, thông thường không cần gọi repository.save() sau khi thay đổi thuộc tính. Dirty checking sẽ ghi nhận thay đổi khi flush.

Test có thể dùng mẫu này để kiểm tra update mà không gọi save(), qua đó xác minh hành vi managed entity.

## 12. Flush trước khi chạy query để kiểm tra trạng thái nhất quán

JPA có FlushModeType.AUTO và FlushModeType.COMMIT. Với AUTO, provider phải bảo đảm các thay đổi có thể ảnh hưởng đến kết quả query được đồng bộ trước khi query thực thi theo quy tắc của JPA. Hibernate có thể tự động flush trước một số truy vấn.

Tuy nhiên, không nên dựa vào auto-flush để thay thế ý định kiểm thử rõ ràng khi mục tiêu là phát hiện lỗi SQL tại một dòng cụ thể.

Ví dụ:

~~~java
@Test
void shouldFindNewCustomerWithQuery() {
    customerRepository.save(
            new Customer("Lan", "lan@example.test")
    );

    entityManager.flush();

    List<Customer> results = entityManager.createQuery(
            "select c from Customer c where c.email = :email",
            Customer.class
    )
    .setParameter("email", "lan@example.test")
    .getResultList();

    assertEquals(1, results.size());
}
~~~

Explicit flush giúp người đọc biết test yêu cầu INSERT được gửi trước query.

Nếu query chạy trong cùng persistence context và trả về entity đã managed, nó vẫn có thể tham chiếu object đang được quản lý. Nếu mục tiêu là kiểm tra round-trip qua database, dùng clear trước query hoặc trước find để tránh first-level cache.

## 13. Flush mode và ảnh hưởng trong test

JPA định nghĩa hai flush mode chính:

| Flush mode | Hành vi tổng quát |
|---|---|
| AUTO | Provider phải đồng bộ thay đổi có thể ảnh hưởng đến kết quả query trước khi query thực thi |
| COMMIT | Provider được phép trì hoãn đồng bộ cho đến khi transaction commit; query có thể không thấy mọi thay đổi pending |

Có thể đặt mode trên EntityManager:

~~~java
entityManager.setFlushMode(FlushModeType.COMMIT);
~~~

Hoặc trên query:

~~~java
query.setFlushMode(FlushModeType.COMMIT);
~~~

Hibernate còn có các chế độ riêng như MANUAL, ALWAYS và các tùy chỉnh flush mode khác. Chúng không thuộc enum chuẩn JPA và cần được phân biệt khi code phụ thuộc Hibernate.

Trong test thông thường, nên giữ mặc định trừ khi đang kiểm tra chính sách flush. Nếu test đặt COMMIT hoặc chế độ riêng, hãy hiểu rằng query có thể không tự flush thay đổi pending.

Explicit entityManager.flush() vẫn là cách trực tiếp để yêu cầu đồng bộ persistence context trong phạm vi transaction.

## 14. saveAndFlush() của Spring Data JPA

Spring Data JPA cung cấp saveAndFlush() trên JpaRepository:

~~~java
Customer saved = customerRepository.saveAndFlush(customer);
~~~

Phương thức này thực hiện save rồi flush. Nó hữu ích khi muốn thao tác gọn trong test hoặc code cần buộc đồng bộ ngay.

So sánh:

~~~java
customerRepository.save(customer);
entityManager.flush();
~~~

và:

~~~java
customerRepository.saveAndFlush(customer);
~~~

Cả hai đều có thể dùng để yêu cầu lưu entity rồi flush persistence context. Điểm khác là cách thể hiện dependency API:

- save() cộng EntityManager.flush() thể hiện rõ ranh giới JPA.
- saveAndFlush() gọn khi đã làm việc qua JpaRepository.
- saveAndFlush() có thể flush cả thay đổi pending khác trong persistence context, không chỉ entity truyền vào.
- Không phương thức nào tự commit transaction đang hoạt động.

Nếu repository chỉ kế thừa CrudRepository hoặc một interface không cung cấp flush(), cần dùng EntityManager hoặc mở rộng JpaRepository phù hợp.

## 15. Flush và clear trong @DataJpaTest

@DataJpaTest thường tạo test slice cho JPA, cấu hình DataSource và repository, đồng thời chạy mỗi test method trong transaction được rollback sau khi kết thúc.

Đây là môi trường thuận tiện để kiểm tra persistence:

~~~java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void shouldPersistAndReloadProduct() {
        Product product = new Product("BOOK-1", "Spring Testing");

        productRepository.save(product);

        entityManager.flush();
        entityManager.clear();

        Product reloaded = productRepository
                .findBySku("BOOK-1")
                .orElseThrow();

        assertEquals("Spring Testing", reloaded.getName());
    }
}
~~~

Test transaction vẫn đang hoạt động sau flush và clear. Query sau clear đọc dữ liệu từ database trong cùng transaction, nên có thể thấy các thay đổi chưa commit của chính transaction đó.

Khi test kết thúc, Spring rollback transaction theo mặc định của @DataJpaTest. Vì vậy, test có thể xác minh SQL mà không để dữ liệu tồn tại sau test.

Nếu test cần xác minh hành vi commit thật, @DataJpaTest mặc định rollback không cung cấp bằng chứng đó. Cần thiết kế transaction test riêng hoặc kiểm tra ở integration/system test với transaction boundary phù hợp.

## 16. Vì sao @DataJpaTest xanh nhưng production vẫn có thể lỗi?

Một số database nhúng có thể khác database production về:

- SQL dialect.
- Constraint và kiểu dữ liệu.
- Identity/sequence behavior.
- Precision và scale.
- Cách xử lý timestamp/timezone.
- Locking và isolation.
- Transaction semantics.
- Deferred constraint.
- Câu SQL native.

Flush giúp phát hiện lỗi khi SQL được gửi, nhưng không loại bỏ khác biệt giữa các database. Nếu production dùng PostgreSQL, MySQL hoặc Oracle, hãy cân nhắc Testcontainers với đúng hệ quản trị đó cho các test có rủi ro dialect hoặc constraint.

Ví dụ với PostgreSQL container, DataSource của test có thể được cấu hình bằng @DynamicPropertySource. Khi đó, flush sẽ gửi SQL tới PostgreSQL thật trong container thay vì database nhúng.

Điều này đặc biệt quan trọng khi test:

- Unique constraint có điều kiện.
- JSON hoặc array column.
- Sequence và generated identity.
- Native query.
- Stored procedure.
- Locking hoặc transaction isolation.
- DDL và migration.

Không nên kết luận rằng một test H2 xanh chứng minh câu SQL production chắc chắn hợp lệ.

## 17. Flush trong kiểm thử quan hệ và cascade

JPA có thể cascade thao tác từ entity cha sang entity con tùy mapping.

Ví dụ:

~~~java
@Entity
class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
            mappedBy = "purchaseOrder",
            cascade = CascadeType.PERSIST
    )
    private List<OrderItem> items = new ArrayList<>();

    void addItem(OrderItem item) {
        items.add(item);
        item.setPurchaseOrder(this);
    }
}
~~~

Test:

~~~java
@Test
void shouldPersistOrderAndItemsThroughCascade() {
    PurchaseOrder order = new PurchaseOrder();
    order.addItem(new OrderItem("BOOK-1", 2));
    order.addItem(new OrderItem("PEN-1", 5));

    entityManager.persist(order);
    entityManager.flush();
    entityManager.clear();

    PurchaseOrder reloaded =
            entityManager.find(PurchaseOrder.class, order.getId());

    assertEquals(2, reloaded.getItems().size());
}
~~~

Flush buộc ORM xử lý INSERT cho entity cha và các entity con theo cascade. Nếu mapping quan hệ, khóa ngoại hoặc cascade sai, lỗi có thể xuất hiện trong lúc flush.

Clear rồi find giúp test tải lại object graph thay vì chỉ kiểm tra collection đang nằm trong bộ nhớ.

Tuy nhiên, việc tải collection có thể là lazy. Nếu assertion truy cập collection sau khi persistence context đã đóng, có thể gặp LazyInitializationException. Trong test này context vẫn còn hoạt động, nhưng ở service boundary thực tế cần xác định rõ dữ liệu nào được fetch trước khi transaction kết thúc.

## 18. Flush trước khi kiểm tra xóa entity

Khi gọi delete(), entity có thể được đánh dấu removed trong persistence context. SQL DELETE có thể chưa chạy ngay.

~~~java
@Test
void shouldDeleteCustomerFromDatabase() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    customerRepository.delete(customer);

    entityManager.flush();
    entityManager.clear();

    assertFalse(customerRepository.findById(1L).isPresent());
}
~~~

Nếu chỉ kiểm tra entity sau khi gọi delete, test có thể đang quan sát state trong persistence context. Flush buộc DELETE xuống database; clear đảm bảo lần find tiếp theo không trả lại object cũ từ first-level cache.

Nếu entity có quan hệ foreign key hoặc cascade delete, flush giúp phát hiện lỗi thứ tự xóa hoặc constraint còn tham chiếu đến bản ghi.

## 19. Bulk update/delete và persistence context stale

JPQL bulk update hoặc delete hoạt động trực tiếp trên database, không cập nhật từng entity managed trong persistence context.

Ví dụ:

~~~java
@Modifying
@Query("""
       update Customer c
       set c.active = false
       where c.lastLogin < :cutoff
       """)
int deactivateInactiveCustomers(Instant cutoff);
~~~

Sau khi chạy bulk update, entity Customer đã được load trước đó có thể vẫn giữ giá trị active cũ trong persistence context.

Một test nên làm rõ thứ tự:

~~~java
@Test
void shouldDeactivateInactiveCustomers() {
    Customer customer =
            customerRepository.findById(1L).orElseThrow();

    int updated = customerRepository
            .deactivateInactiveCustomers(cutoff());

    entityManager.clear();

    Customer reloaded =
            customerRepository.findById(customer.getId()).orElseThrow();

    assertEquals(1, updated);
    assertFalse(reloaded.isActive());
}
~~~

Với bulk query, có thể cấu hình @Modifying(flushAutomatically = true, clearAutomatically = true) để Spring Data JPA flush trước khi chạy và clear persistence context sau khi chạy.

~~~java
@Modifying(
        flushAutomatically = true,
        clearAutomatically = true
)
@Query("""
       update Customer c
       set c.active = false
       where c.lastLogin < :cutoff
       """)
int deactivateInactiveCustomers(Instant cutoff);
~~~

Hai tùy chọn này có ý nghĩa khác nhau:

- flushAutomatically yêu cầu flush các thay đổi pending trước khi thực thi bulk query.
- clearAutomatically xóa persistence context sau khi query để tránh dùng entity state cũ.

Không nên bật clearAutomatically mà không hiểu rằng mọi entity đang managed sẽ bị detach. Nếu caller còn giữ các object đó, chúng không tự đồng bộ với database.

## 20. Flush và lỗi xảy ra tại thời điểm nào?

Một lỗi persistence có thể xuất hiện ở nhiều thời điểm:

- Khi gọi persist hoặc merge, nếu provider cần xử lý một điều kiện ngay lập tức.
- Khi flush tường minh.
- Khi query kích hoạt auto-flush.
- Khi transaction commit và provider flush các thay đổi còn pending.
- Khi database kiểm tra deferred constraint tại commit.

Vì vậy, nếu một test thất bại ở cuối method hoặc khi transaction kết thúc, không nên mặc định rằng assertion cuối cùng gây ra lỗi. SQL có thể chỉ được gửi ở giai đoạn cleanup/commit.

Explicit flush giúp gắn lỗi với đoạn test đang kiểm tra:

~~~java
repository.save(entity);

assertThatThrownBy(entityManager::flush)
        .isInstanceOf(PersistenceException.class);
~~~

Khi cần kiểm tra lỗi constraint, hãy đặt assertion quanh flush để test diễn đạt đúng thời điểm database từ chối thao tác.

Nếu exception được Spring translate, kiểu exception bên ngoài có thể là DataIntegrityViolationException. Nếu gọi EntityManager trực tiếp, exception thường đến từ JPA provider. Không nên phụ thuộc vào một lớp exception Hibernate cụ thể nếu test không có chủ đích gắn chặt với Hibernate.

## 21. Flush không bảo đảm tất cả SQL theo đúng thứ tự gọi Java

Hibernate quản lý các thao tác pending trong action queue và có thể sắp xếp câu lệnh theo dependency và chiến lược thực thi. Vì vậy, thứ tự gọi save() trong Java không nhất thiết là thứ tự SQL được gửi.

Ví dụ:

~~~java
repository.save(orderItem);
repository.save(order);
entityManager.flush();
~~~

Nếu OrderItem có foreign key tới Order, Hibernate có thể cần xử lý theo thứ tự phù hợp với mapping và dependency. Nhưng nếu object graph hoặc cascade được thiết kế sai, database vẫn có thể từ chối câu lệnh.

Đừng viết test chỉ để khẳng định một chuỗi SQL nội bộ cố định nếu thứ tự đó không phải hợp đồng nghiệp vụ. Hãy kiểm tra kết quả, constraint và state cuối cùng. Nếu một thứ tự thao tác thực sự quan trọng, thiết kế mapping và transaction để thể hiện rõ điều đó.

## 22. Những trường hợp flush có thể chưa đủ

Flush là công cụ quan trọng nhưng không phải ranh giới kiểm thử duy nhất.

**Deferred constraint**

Một số constraint được cấu hình kiểm tra tại commit. Flush có thể gửi SQL nhưng database chưa báo lỗi. Cần test transaction commit thật nếu muốn kiểm tra loại constraint này.

**Side effect ngoài database**

Flush không gửi email, không bảo đảm message broker đã nhận event và không hoàn tác API bên ngoài. Những side effect đó cần kiểm tra qua integration test riêng.

**Database khác production**

Flush trên H2 không chứng minh SQL tương thích với PostgreSQL. Dùng database tương thích khi cần kiểm tra dialect.

**Bulk SQL và persistence context**

Bulk query có thể làm object managed stale. Cần clear hoặc refresh trước khi assertion.

**Transaction khác hoặc thread khác**

Request qua HTTP server thật có transaction riêng. Flush của transaction test không đồng bộ transaction của thread server.

**Constraint được kiểm tra ở tầng ứng dụng**

Nếu validation chỉ chạy ở service hoặc Bean Validation, flush database không thay thế test validation. Cần kiểm tra cả lớp validation và database constraint theo mục tiêu.

## 23. Các lỗi thường gặp khi viết test có flush

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test xanh nhưng dữ liệu không được ghi đúng | Chỉ assert trên managed entity | Gọi flush, clear và truy vấn lại |
| Lỗi unique constraint chỉ xuất hiện sau test | SQL chưa chạy trước assertion | Flush ngay trong test |
| ID đã có nhưng INSERT vẫn lỗi | ID được cấp trước khi INSERT thực thi | Flush để buộc SQL chạy |
| findById trả object vừa sửa dù chưa flush | First-level cache trả managed instance | Flush rồi clear trước khi truy vấn lại |
| Test vẫn không phát hiện deferred constraint | Database chỉ kiểm tra constraint tại commit | Dùng test có commit boundary phù hợp |
| Dữ liệu biến mất sau test | @DataJpaTest rollback transaction | Đây là hành vi mặc định; kiểm tra trong transaction hoặc thiết kế test commit riêng |
| Bulk update chạy nhưng entity vẫn có giá trị cũ | Persistence context chưa được đồng bộ | Clear hoặc refresh entity |
| Flush gây lỗi ở entity không liên quan | Flush đồng bộ mọi thay đổi pending trong context | Tách setup hoặc flush tại ranh giới rõ ràng |
| Test dùng H2 xanh nhưng production lỗi | Khác dialect hoặc constraint semantics | Dùng Testcontainers với database tương thích |
| Exception type khác dự kiến | JPA provider hoặc Spring exception translation khác nhau | Assert ở abstraction phù hợp với API được gọi |

## 24. Thực hành viết repository test có bằng chứng rõ ràng

Một test tốt nên thể hiện rõ điều nó đang kiểm tra. Có thể áp dụng các mẫu sau:

### Kiểm tra INSERT và đọc lại

~~~java
repository.save(entity);
entityManager.flush();
entityManager.clear();

Entity reloaded = repository.findById(entity.getId()).orElseThrow();
assertEquals(expected, reloaded.getValue());
~~~

### Kiểm tra UPDATE qua dirty checking

~~~java
Entity entity = repository.findById(id).orElseThrow();
entity.setValue(expected);

entityManager.flush();
entityManager.clear();

Entity reloaded = repository.findById(id).orElseThrow();
assertEquals(expected, reloaded.getValue());
~~~

### Kiểm tra DELETE

~~~java
Entity entity = repository.findById(id).orElseThrow();
repository.delete(entity);

entityManager.flush();
entityManager.clear();

assertFalse(repository.findById(id).isPresent());
~~~

### Kiểm tra constraint

~~~java
repository.save(invalidEntity);

assertThrows(
        PersistenceException.class,
        entityManager::flush
);
~~~

### Kiểm tra bulk update

~~~java
int affected = repository.bulkUpdate(...);

entityManager.clear();

assertEquals(expectedCount, affected);
assertEquals(expectedState, repository.findById(id).orElseThrow().getState());
~~~

Không phải mọi test đều cần cả flush và clear. Chọn đúng bước theo câu hỏi:

- Chỉ cần phát hiện lỗi SQL/constraint: flush.
- Cần tải lại state từ database, tránh first-level cache: flush rồi clear.
- Cần tải lại một entity cụ thể đang managed: flush rồi refresh.
- Cần kiểm tra commit/deferred constraint: thiết kế transaction test có commit thực tế.

## 25. Chiến lược dùng flush trong Spring Framework Testing

Khi viết test tầng dữ liệu, hãy xác định rõ bằng chứng cần có:

| Mục tiêu | Thao tác phù hợp |
|---|---|
| Kiểm tra logic trên object managed | Assertion trực tiếp có thể đủ |
| Phát hiện lỗi INSERT/UPDATE/DELETE | Gọi flush |
| Xác minh dữ liệu đã đi qua database và đọc lại | flush + clear + query/find |
| Làm mới một entity cụ thể từ database | flush + refresh |
| Kiểm tra unique/foreign key/NOT NULL constraint | Flush trong assertion mong đợi lỗi |
| Kiểm tra deferred constraint tại commit | Commit transaction trong test có kiểm soát |
| Kiểm tra bulk update/delete | Flush trước nếu cần, clear sau, rồi đọc lại |
| Kiểm tra dialect production | Chạy test với database tương thích |
| Kiểm tra dữ liệu được rollback | Dùng test transaction và xác minh ranh giới rollback |

Một quy trình thực tế:

1. Tạo dữ liệu test với key xác định.
2. Thực hiện thao tác qua repository hoặc entity manager.
3. Gọi flush tại điểm muốn database thực thi SQL.
4. Nếu cần xác minh round-trip, gọi clear rồi truy vấn lại.
5. Assertion trên state được đọc lại hoặc xác nhận exception tại flush.
6. Để transaction test rollback nếu đó là chiến lược cô lập dữ liệu.
7. Nếu cần kiểm tra commit hoặc deferred constraint, dùng một transaction boundary riêng có chủ đích.
8. Chạy trên database tương thích với production cho các rủi ro liên quan dialect và constraint.

## 26. Kết luận

Persistence context giúp JPA/Hibernate quản lý entity và trì hoãn SQL cho đến thời điểm thích hợp. Cơ chế này hiệu quả trong ứng dụng, nhưng có thể khiến test chỉ kiểm tra object trong bộ nhớ mà chưa kiểm tra database.

Hãy nhớ ba điểm:

- **save()** đưa entity vào quy trình persist/merge; nó không bảo đảm SQL đã được thực thi.
- **flush()** đồng bộ thay đổi pending xuống database trong transaction hiện tại, giúp phát hiện sớm nhiều lỗi SQL và constraint; nó không commit transaction.
- **clear()** loại entity khỏi persistence context. Kết hợp flush + clear + query giúp xác minh dữ liệu được đọc lại qua database thay vì nhận lại object từ first-level cache.

Dùng flush khi cần phát hiện lỗi persistence tại một điểm rõ ràng. Dùng clear khi cần kiểm tra round-trip. Dùng refresh khi chỉ cần tải lại một entity cụ thể. Với deferred constraint, transaction commit, database dialect hoặc side effect ngoài database, hãy chọn thêm loại kiểm thử phù hợp.

Khi test tạo được bằng chứng rằng SQL đã chạy và dữ liệu được đọc lại từ database, nó sẽ phát hiện được nhiều lỗi mà một assertion trên managed entity không thể nhìn thấy.

