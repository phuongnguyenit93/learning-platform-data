# Unwrap EntityManager sang Session khi có nhu cầu cụ thể

## 1. Mục đích của unwrap

Spring Data JPA khuyến khích ứng dụng làm việc qua repository và Jakarta Persistence `EntityManager`. Các API này giữ code ít phụ thuộc Hibernate và giúp thay đổi persistence provider dễ hơn.

Tuy nhiên, có những nhu cầu mà JPA không có API tương ứng hoặc Hibernate cung cấp tính năng chuyên biệt hữu ích, chẳng hạn:

- Chạy JDBC work trên chính connection Hibernate đang quản lý.
- Bật Hibernate filter hoặc fetch profile theo từng Session.
- Đặt entity/query ở chế độ read-only theo cơ chế Hibernate.
- Dùng một số API HQL, loading, batch hoặc session-specific option.
- Truy cập tính năng Hibernate mà không tạo persistence context thứ hai.

Khi có nhu cầu như vậy, có thể lấy Hibernate `Session` từ `EntityManager`:

```java
Session session = entityManager.unwrap(Session.class);
```

Đây là cơ chế chuẩn của Jakarta Persistence để lấy native API của provider. Khi Hibernate là JPA provider, đối tượng được unwrap là Session đang đứng sau EntityManager đó.

Chỉ unwrap khi đã xác định một tính năng Hibernate-specific cần thiết. Nếu `EntityManager`, Spring Data repository hoặc `JdbcTemplate` giải quyết được yêu cầu, hãy giữ ở API đó để giảm phụ thuộc provider.

## 2. EntityManager và Session liên hệ thế nào?

### 2.1. EntityManager là API JPA

`jakarta.persistence.EntityManager` là API chuẩn để:
- Persist, merge, remove và find entity.
- Tạo JPQL, Criteria và native query.
- Flush, clear và refresh persistence context.
- Quản lý entity lifecycle.
- Tham gia transaction do JPA/Spring quản lý.

Ví dụ:

```java
Customer customer = entityManager.find(Customer.class, customerId);
customer.setName("New name");
entityManager.flush();
```

Code này không cần biết provider là Hibernate hay một implementation JPA khác.

### 2.2. Session là API native của Hibernate

`org.hibernate.Session` là API trung tâm của Hibernate. Nó biểu diễn persistence context và cung cấp các thao tác riêng của Hibernate.

Khi Hibernate là provider, Session và EntityManager cùng đại diện cho một persistence context. Unwrap không sao chép entity, không tạo persistence context mới và không tải lại toàn bộ dữ liệu.

```text
Spring @Transactional
       |
       v
Transaction-bound EntityManager
       |
       | entityManager.unwrap(Session.class)
       v
Hibernate Session
       |
       +---- Persistence Context / First-level Cache
       |
       +---- Hibernate-specific APIs
       |
       +---- Managed JDBC Connection
```

Entity đã load qua EntityManager vẫn là managed entity khi thao tác tiếp qua Session vừa unwrap. Dirty checking, identity map, lazy proxy và flush vẫn thuộc cùng persistence context.

### 2.3. unwrap là API của JPA

Phương thức `EntityManager.unwrap(Class<T>)` được Jakarta Persistence cung cấp để truy cập native API của provider:

```java
Session session = entityManager.unwrap(Session.class);
```

Nếu provider không hỗ trợ kiểu được yêu cầu, lời gọi có thể ném `PersistenceException`. Không nên bắt exception rồi âm thầm giả định provider khác cũng có hành vi Hibernate.

Nếu ứng dụng hỗ trợ nhiều JPA provider, hãy cô lập code Hibernate trong adapter/service riêng và chỉ gọi adapter đó ở các luồng đã xác định dùng Hibernate.

## 3. Unwrap Session trong Spring-managed transaction

### 3.1. Inject EntityManager

Trong ứng dụng Spring, thường inject EntityManager qua `@PersistenceContext`:

```java
@Service
public class CustomerMaintenanceService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void renameCustomer(Long customerId, String newName) {
        Session session = entityManager.unwrap(Session.class);

        Customer customer =
            session.find(Customer.class, customerId);

        if (customer == null) {
            throw new CustomerNotFoundException(customerId);
        }

        customer.setName(newName);
    }
}
```

Spring thường inject một shared EntityManager proxy. Khi method chạy trong transaction do Spring quản lý, proxy ủy quyền tới EntityManager gắn với transaction hiện tại. Unwrap trong phạm vi đó lấy Session tương ứng với persistence context hiện tại.

Ví dụ dùng `session.find()` để minh họa native API. Nếu không cần Hibernate-specific behavior, dùng `entityManager.find()` ngay trong method.

### 3.2. Không mở Session thứ hai cho cùng công việc

Không nên mở thêm một Session độc lập bằng `SessionFactory.openSession()` trong khi EntityManager hiện tại đang được Spring quản lý:

```java
// Không dùng cách này cho cùng persistence context do Spring quản lý.
Session anotherSession = sessionFactory.openSession();
```

Session mới có persistence context và transaction/resource lifecycle riêng. Entity được load trong Session mới không tự trở thành managed entity của EntityManager ban đầu. Điều này có thể gây:
- Hai bản Java object cho cùng một database row.
- Lazy proxy thuộc persistence context khác.
- Giao dịch không cùng connection hoặc không cùng transaction.
- Dữ liệu trong memory và database lệch nhau.
- Phải tự quản lý commit, rollback và close.

Nếu mục tiêu là dùng API Hibernate trong transaction hiện tại, unwrap Session từ EntityManager đang được inject là lựa chọn phù hợp.

### 3.3. Không tự commit, rollback hoặc close Session đã unwrap

Session lấy từ EntityManager do Spring quản lý có lifecycle thuộc Spring/JPA transaction integration. Không gọi các thao tác sau trên Session được Spring quản lý:

```java
session.beginTransaction();
session.getTransaction().commit();
session.close();
```

Spring transaction manager chịu trách nhiệm bắt đầu, commit/rollback và giải phóng resource theo cấu hình. Tự đóng Session có thể làm persistence context đang được transaction sử dụng trở nên không hợp lệ.

Nếu viết chương trình Hibernate thuần, không có Spring quản lý EntityManager, lifecycle khác: ứng dụng có thể tự mở Session từ SessionFactory, bắt đầu transaction, commit/rollback và đóng Session. Không trộn hai mô hình quản lý trong cùng một luồng.

## 4. Dùng doWork và doReturningWork

### 4.1. Khi nào cần JDBC work qua Session?

Hibernate cung cấp `doWork()` và `doReturningWork()` để chạy JDBC trên connection do Session quản lý.

Dùng khi:
- Cần gọi JDBC API mà Hibernate chưa có abstraction phù hợp.
- Cần thao tác vendor-specific hoặc stored procedure bằng JDBC.
- Cần dùng chính connection/transaction của Session.
- Cần gọi một thư viện JDBC thấp hơn trong persistence context hiện tại.

Nếu chỉ cần query JDBC thông thường trong ứng dụng Spring, `JdbcTemplate` thường là lựa chọn đơn giản hơn. Nếu cần connection do Session quản lý trực tiếp hoặc phải phối hợp chặt với persistence context Hibernate, `doWork` phù hợp hơn.

### 4.2. doWork: thực thi JDBC không trả kết quả

Ví dụ cập nhật một cột do database quản lý:

```java
@Transactional
public void markCustomerForReindex(Long customerId) {
    Session session = entityManager.unwrap(Session.class);

    entityManager.flush();

    session.doWork(connection -> {
        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "update customer set reindex_required = ? where id = ?"
                 )) {

            statement.setBoolean(1, true);
            statement.setLong(2, customerId);
            statement.executeUpdate();
        }
    });

    entityManager.clear();
}
```

Giải thích:
- `entityManager.flush()` đẩy thay đổi JPA đang chờ xuống database trước khi JDBC đọc/ghi trực tiếp.
- `doWork` nhận connection do Session quản lý.
- `PreparedStatement` được đóng bằng try-with-resources.
- Không đóng connection, không tự commit và không tự rollback trong callback.
- JDBC update không tự cập nhật state của entity đang managed, nên ví dụ dùng `clear()` để loại entity managed khỏi persistence context.

`clear()` ảnh hưởng toàn bộ entity đang managed trong EntityManager, không chỉ Customer vừa cập nhật. Nếu chỉ một entity bị ảnh hưởng và cần tiếp tục dùng các entity khác trong transaction, có thể gọi `refresh(customer)` trên entity tương ứng sau JDBC update thay vì clear toàn bộ context.

### 4.3. doReturningWork: thực thi JDBC và trả kết quả

Ví dụ đếm đơn hàng:

```java
@Transactional(readOnly = true)
public long countOrders(Long customerId) {
    Session session = entityManager.unwrap(Session.class);

    return session.doReturningWork(connection -> {
        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "select count(*) from purchase_order where customer_id = ?"
                 )) {

            statement.setLong(1, customerId);

            try (ResultSet resultSet = statement.executeQuery()) {
                resultSet.next();
                return resultSet.getLong(1);
            }
        }
    });
}
```

`doReturningWork` trả kết quả từ callback về caller. Statement và ResultSet được đóng, còn connection vẫn do Hibernate quản lý.

### 4.4. Connection và transaction có được dùng chung không?

Khi Session đang tham gia transaction do Spring quản lý, JDBC work được thực thi trên connection của Session và phối hợp với transaction/resource integration đó. Không tạo connection mới bằng `DriverManager.getConnection()` nếu muốn cùng transaction.

Nếu mở connection độc lập, câu SQL đó có thể chạy ngoài transaction hiện tại và không nhìn thấy thay đổi chưa commit. Với JTA, connection handling và enlistment phụ thuộc cấu hình transaction manager/data source; hãy kiểm tra integration thực tế.

### 4.5. Lưu ý khi JDBC sửa dữ liệu

Hibernate không biết JDBC đã cập nhật những row nào. Sau direct JDBC write:
- Entity đang managed có thể chứa giá trị cũ.
- Collection đã load có thể không phản ánh dữ liệu mới.
- Second-level cache/query cache có thể cần xử lý nếu entity/query liên quan được cache.
- Bulk SQL không kích hoạt JPA entity lifecycle callback hoặc cascade như thao tác qua entity.

Hãy flush trước khi JDBC ghi nếu cần thứ tự nhất quán. Sau đó refresh entity bị ảnh hưởng, clear persistence context khi phù hợp và xử lý cache region theo chính sách của ứng dụng.

## 5. Hibernate Filter theo Session

### 5.1. Filter giải quyết nhu cầu gì?

Hibernate filter cho phép bật một điều kiện SQL có tham số trong phạm vi Session. Ví dụ một ứng dụng multi-tenant có thể lọc Customer theo tenant hiện tại.

Filter khác với điều kiện JPQL viết trực tiếp trong từng repository method: filter được bật trên Session và có thể tác động đến entity/collection được tải trong phạm vi đó theo mapping và version Hibernate.

### 5.2. Khai báo filter trên entity

Ví dụ Hibernate annotation:

```java
@Entity
@Table(name = "customer")
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(name = "tenantId", type = Long.class)
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
public class Customer {

    @Id
    private Long id;

    @Column(name = "tenant_id")
    private Long tenantId;

    private String name;
}
```

Các annotation `@FilterDef`, `@ParamDef` và `@Filter` thuộc Hibernate, không phải Jakarta Persistence. Condition dùng tên cột SQL của mapping, không phải tên field Java.

### 5.3. Bật và đặt parameter cho filter

Trong service:

```java
@Transactional(readOnly = true)
public List<Customer> findCustomersForTenant(Long tenantId) {
    Session session = entityManager.unwrap(Session.class);

    Filter filter = session.enableFilter("tenantFilter");
    filter.setParameter("tenantId", tenantId);

    try {
        return entityManager.createQuery(
            "select c from Customer c order by c.name",
            Customer.class
        ).getResultList();
    } finally {
        session.disableFilter("tenantFilter");
    }
}
```

Filter được bật trên Session hiện tại. Đặt parameter trước khi chạy query. Khối `finally` giúp tắt filter khi method kết thúc, tránh để phần code tiếp theo trong cùng Session vô tình chịu điều kiện cũ.

Với Spring transaction thông thường, Session kết thúc theo persistence context/transaction. Tuy nhiên, tắt filter rõ ràng làm phạm vi hiệu lực dễ hiểu hơn, nhất là khi method gọi nhiều thành phần cùng tham gia một transaction.

### 5.4. Filter không tự thay thế kiểm soát truy cập

Không dùng Hibernate filter như ranh giới bảo mật duy nhất cho multi-tenancy.

Cần kiểm tra:
- Filter có được bật ở mọi đường truy cập dữ liệu không?
- Có code dùng native JDBC hoặc stored procedure bỏ qua filter không?
- Có đường tải entity theo ID trực tiếp không?
- Background job, async task và batch job có mở Session riêng không?
- Có cache trả về entity mà không đi qua query chịu filter không?
- Có thể dùng database row-level security hoặc tenant predicate ở tầng repository để bổ sung bảo vệ không?

Tùy Hibernate version, filter thông thường không nhất thiết áp dụng cho direct identifier load. Các phiên bản mới có tùy chọn `applyToLoadByKey` trên `@FilterDef`; nếu dựa vào behavior đó, phải xác minh version Hibernate và test cả `find/get` theo ID. Không giả định filter đã bảo vệ mọi API chỉ vì JPQL query có kết quả đúng.

## 6. Fetch profile và chế độ read-only

### 6.1. Bật Fetch Profile theo use case

Hibernate Fetch Profile cho phép định nghĩa một fetch plan rồi bật trên Session khi cần. Ví dụ mapping:

```java
@FetchProfile(
    name = "customer-with-orders",
    fetchOverrides = {
        @FetchProfile.FetchOverride(
            entity = Customer.class,
            association = "orders",
            mode = FetchMode.JOIN
        )
    }
)
@Entity
public class Customer {
    // entity mapping
}
```

Khi cần profile:

```java
@Transactional(readOnly = true)
public Customer loadCustomerWithOrders(Long customerId) {
    Session session = entityManager.unwrap(Session.class);
    session.enableFetchProfile("customer-with-orders");

    return entityManager.find(Customer.class, customerId);
}
```

Fetch profile là tính năng Hibernate-specific. Nó phù hợp khi nhiều use case cần fetch plan khác nhau và muốn giữ mapping mặc định không tải quá nhiều association.

Nếu yêu cầu chỉ áp dụng cho một repository query, JPA EntityGraph hoặc JPQL fetch join có thể rõ ràng và portable hơn.

### 6.2. Read-only entity

Hibernate cho phép đánh dấu entity đã load là read-only hoặc đặt mặc định cho entity được load sau đó:

```java
Session session = entityManager.unwrap(Session.class);
session.setDefaultReadOnly(true);

Customer customer =
    session.find(Customer.class, customerId);
```

Read-only ở đây là behavior dirty checking của Hibernate, không phải database permission và không thay thế `@Transactional(readOnly = true)`. Entity đã được load trước khi đổi default có thể cần được đánh dấu riêng bằng API tương ứng như `session.setReadOnly(entity, true)`.

Chỉ dùng khi use case thực sự chỉ đọc và đã hiểu tác động tới flush/dirty checking. Không đặt default read-only trên một Session dùng chung cho cả luồng đọc và ghi nếu chưa kiểm soát phạm vi.

## 7. Những API Hibernate khác có thể cần

### 7.1. Flush, clear và detach

`Session` cung cấp API persistence-context tương ứng với JPA:

```java
Session session = entityManager.unwrap(Session.class);

session.flush();
session.clear();
```

Nếu code chỉ cần flush hoặc clear, `EntityManager` đã có sẵn method chuẩn. Không cần unwrap chỉ để gọi hai thao tác này.

Hibernate có `session.evict(entity)` để loại một entity cụ thể khỏi first-level cache:

```java
session.evict(customer);
```

API JPA tương đương là `entityManager.detach(customer)`. Nếu không có nhu cầu khác của Hibernate, hãy dùng `detach` để giữ portability.

### 7.2. HQL và query API

Hibernate có API query riêng và một số khả năng HQL mở rộng hơn JPQL. Nếu query chỉ dùng cú pháp JPQL chuẩn, tiếp tục dùng `EntityManager.createQuery()` hoặc Spring Data `@Query`.

Khi dùng cú pháp Hibernate-specific, ghi rõ dependency/provider requirement và kiểm tra query trên đúng Hibernate version. HQL có thể thay đổi theo major version; tránh sao chép ví dụ từ tài liệu 5.x vào dự án 6.x/7.x mà không kiểm tra migration guide.

### 7.3. Không nhầm Session với StatelessSession

`StatelessSession` là API Hibernate riêng cho xử lý dữ liệu khối lượng lớn với semantics khác Session thông thường:
- Không có persistence context/first-level cache theo cách Session thông thường.
- Không dùng dirty checking như managed entity.
- Không có cùng cascade/lifecycle semantics.
- Cần quản lý transaction và resource theo API của nó.

Không thể thay `Session` bằng `StatelessSession` chỉ bằng cast hoặc unwrap. Đây là lựa chọn kiến trúc riêng và phải kiểm tra semantics trước khi dùng.

## 8. Khi nào nên unwrap và khi nào không?

| Nhu cầu | API nên ưu tiên | Lý do |
|---|---|---|
| CRUD, find, persist, merge, remove | EntityManager/Repository | API JPA chuẩn |
| JPQL/Criteria query | EntityManager | Portable giữa JPA provider |
| Phân trang/sắp xếp | Spring Data Pageable/Sort | Hợp đồng repository rõ ràng |
| JDBC query thông thường | JdbcTemplate | Spring quản lý connection/exception translation |
| JDBC trên connection của Session | Session.doWork/doReturningWork | Dùng connection do Hibernate quản lý |
| Hibernate filter | Session.enableFilter | Không có API JPA tương đương |
| Hibernate fetch profile | Session.enableFetchProfile | Tính năng riêng của Hibernate |
| Hibernate read-only mode | Session.setDefaultReadOnly/setReadOnly | Tùy chỉnh dirty checking |
| Flush/clear/detach cơ bản | EntityManager | Không cần unwrap |

Quy tắc thực tế: bắt đầu từ repository/JPA. Chỉ unwrap tại ranh giới nhỏ nơi cần tính năng Hibernate; không truyền Session xuyên toàn bộ application layer nếu chỉ một adapter cần nó.

## 9. Transaction, exception và lifecycle

### 9.1. Session chỉ sống trong persistence context tương ứng

Hibernate Session là object ngắn hạn, chứa trạng thái mutable của persistence context. Với Spring-managed EntityManager, Session được lấy qua unwrap chỉ hợp lệ trong lifecycle do provider/Spring quản lý.

Không lưu Session vào:
- Field static.
- Singleton cache.
- Object được giữ sau khi transaction kết thúc.
- Message gửi sang thread khác.
- Task async chạy sau khi method transaction kết thúc.

Hãy unwrap lại trong transaction của từng luồng công việc.

### 9.2. Session không thread-safe

Không dùng cùng một Session từ nhiều thread đồng thời. EntityManager cũng không thread-safe theo JPA contract.

Ví dụ không an toàn:

```java
Session session = entityManager.unwrap(Session.class);

executor.submit(() -> session.find(Customer.class, 1L));
executor.submit(() -> session.find(Customer.class, 2L));
```

Hai task có thể truy cập đồng thời persistence context và connection state. Mỗi thread/transaction phải có persistence context riêng do Spring tạo cho thread đó; không truyền Session từ thread gọi sang.

### 9.3. Xử lý exception

Nếu Session phát sinh exception trong khi truy cập database, không nên tiếp tục dùng persistence context như thể chưa có lỗi. Hibernate khuyến nghị rollback transaction và loại bỏ Session sau exception vì trạng thái nội bộ có thể không còn nhất quán với database.

Trong Spring:
- Để exception phù hợp truyền ra khỏi transactional boundary.
- Cấu hình rollback cho checked exception nếu nghiệp vụ yêu cầu.
- Không bắt exception rồi tiếp tục ghi bằng cùng Session.
- Không tự commit/rollback Session được Spring quản lý.

### 9.4. Lazy loading và Session đã đóng

Unwrap không kéo dài lifecycle của persistence context. Nếu transaction kết thúc và Session đóng, lazy proxy chưa khởi tạo vẫn có thể ném `LazyInitializationException`.

Hãy tải dữ liệu cần thiết trong transaction bằng fetch plan/DTO phù hợp. Không giữ Session mở lâu chỉ để serializer hoặc view layer truy cập association sau đó.

## 10. Kiểm thử code có unwrap

### 10.1. Kiểm tra provider thật

Test dùng Hibernate phải chạy với Hibernate dependency thực tế, không chỉ mock EntityManager:

```java
@DataJpaTest
class HibernateSessionIntegrationTest {

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void unwrapsTheHibernateSession() {
        Session session = entityManager.unwrap(Session.class);

        assertThat(session).isNotNull();
        assertThat(session.isOpen()).isTrue();
    }
}
```

Ví dụ cần dependency Hibernate và AssertJ từ test stack của dự án. Nếu test slice dùng provider khác hoặc mock EntityManager, unwrap có thể không hoạt động như production.

### 10.2. Test JDBC work trong cùng transaction

Một integration test nên xác minh:
- Entity đã persist và flush có thể được JDBC work đọc thấy.
- JDBC write được rollback khi transaction test rollback.
- Entity managed được refresh/clear sau direct JDBC update.
- Connection không bị đóng bởi callback.
- Exception từ JDBC work làm transaction xử lý đúng.

Với database-specific SQL, dùng Testcontainers chạy đúng PostgreSQL/MySQL production. H2 không đủ để xác nhận mọi behavior của dialect hoặc stored procedure.

### 10.3. Test filter và fetch profile

Với filter:
- Tạo dữ liệu cho ít nhất hai tenant.
- Bật filter với tenant A và xác minh chỉ dữ liệu A xuất hiện.
- Tắt filter và xác minh behavior mặc định.
- Kiểm tra query theo ID/direct load theo đúng Hibernate version.
- Kiểm tra native JDBC path không bị filter tự động áp dụng.

Với fetch profile:
- Xác nhận association được tải theo profile.
- Dùng SQL capture hoặc Hibernate statistics để quan sát query.
- Xác minh dữ liệu trả về giống nhau khi profile bật/tắt.
- Kiểm tra profile không bị giữ ngoài phạm vi use case.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `unwrap(Session.class)` ném PersistenceException | Provider hiện tại không phải Hibernate hoặc không expose kiểu được yêu cầu | Kiểm tra JPA provider và cô lập code Hibernate |
| Session đã đóng khi gọi method | Dùng Session ngoài transaction/persistence context | Unwrap bên trong transactional method |
| Entity load hai lần hoặc có hai object cùng ID | Mở SessionFactory.openSession() thứ hai | Dùng Session unwrap từ EntityManager hiện tại |
| Connection đóng bất ngờ | Code tự đóng connection nhận trong doWork | Chỉ đóng Statement/ResultSet; để Hibernate quản lý connection |
| JDBC không thấy thay đổi JPA vừa set | Persistence context chưa flush | Gọi flush trước JDBC work |
| Entity trong memory giữ dữ liệu cũ sau JDBC update | Hibernate không biết direct JDBC đã sửa row | Refresh entity hoặc clear persistence context |
| Transaction bị lệch | JDBC tự mở connection riêng | Dùng doWork hoặc JdbcTemplate cùng DataSource transaction |
| Filter không áp dụng cho truy vấn theo ID | Behavior của filter với direct load khác query thông thường | Kiểm tra applyToLoadByKey và version Hibernate |
| Dữ liệu tenant lọt qua native SQL | Hibernate filter không tự lọc JDBC SQL tùy ý | Thêm tenant predicate/DB row-level security |
| LazyInitializationException | Session đã kết thúc trước khi load association | Fetch dữ liệu trong transaction |
| Lỗi session ngẫu nhiên khi chạy song song | Dùng Session từ nhiều thread | Mỗi thread/transaction có persistence context riêng |
| Session không nhất quán sau exception | Tiếp tục dùng Session sau lỗi database | Rollback và kết thúc persistence context |

## 12. Quy trình quyết định trước khi unwrap

1. Xác định yêu cầu có thật sự cần tính năng Hibernate-specific không.
2. Kiểm tra EntityManager, Spring Data repository hoặc JdbcTemplate có đáp ứng được không.
3. Đảm bảo method đang chạy trong transaction/persistence context phù hợp.
4. Gọi `entityManager.unwrap(Session.class)` tại đúng ranh giới cần dùng.
5. Không mở, đóng hoặc tự commit Session do Spring quản lý.
6. Với JDBC, dùng connection callback và đóng statement/result set.
7. Flush trước khi JDBC cần đọc thay đổi đang chờ; refresh/clear sau JDBC write.
8. Với filter/fetch profile, bật trong phạm vi Session rõ ràng và tắt khi hoàn tất nếu cần.
9. Không chia sẻ Session giữa thread hoặc giữ sau transaction.
10. Viết integration test trên Hibernate/database thực và kiểm tra transaction, SQL, cache, filter.

## 13. Checklist review code

- [ ] Có lý do cụ thể để dùng Hibernate Session thay cho JPA API.
- [ ] Session được lấy bằng `EntityManager.unwrap(Session.class)`.
- [ ] Unwrap diễn ra trong Spring-managed transaction/persistence context phù hợp.
- [ ] Không tạo Session thứ hai bằng `SessionFactory.openSession()` cho cùng use case.
- [ ] Không tự gọi beginTransaction/commit/rollback/close trên Session do Spring quản lý.
- [ ] Không lưu Session vào field/static hoặc truyền qua thread.
- [ ] JDBC work dùng connection do Session quản lý.
- [ ] Statement và ResultSet được đóng; connection không bị đóng thủ công.
- [ ] Flush trước direct JDBC khi cần đồng bộ dữ liệu.
- [ ] Refresh/clear/cache handling sau direct JDBC write.
- [ ] Filter không bị coi là ranh giới bảo mật duy nhất.
- [ ] Fetch profile/filter được bật trong phạm vi rõ ràng.
- [ ] Exception dẫn tới rollback và kết thúc persistence context phù hợp.
- [ ] Có integration test với đúng Hibernate version và database mục tiêu.
- [ ] Code Hibernate-specific được cô lập để dễ nâng cấp provider/version.

## 14. Tài liệu tham khảo chính thức

- [Hibernate ORM — Session Javadoc](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/Session.html): Session, unwrap, lifecycle, thread-safety và JDBC work.
- [Hibernate ORM User Guide](https://docs.hibernate.org/stable/orm/userguide/html_single/): persistence context, filters, fetch profiles, read-only state và Session behavior.
- [Spring Framework — JPA](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html): EntityManagerFactory, EntityManager proxy và tích hợp transaction trong Spring.
- [Jakarta Persistence — EntityManager API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager): hợp đồng `unwrap(Class<T>)` của JPA.
- [Hibernate ORM — Integrations Guide](https://docs.hibernate.org/stable/orm/integrationguide/html_single/): tích hợp Hibernate với transaction manager và resource lifecycle.

## 15. Kết luận

`EntityManager.unwrap(Session.class)` là cầu nối từ API JPA portable sang API native của Hibernate. Nó hữu ích khi cần tính năng cụ thể như JDBC work trên connection do Session quản lý, Hibernate filter, fetch profile hoặc read-only behavior. Unwrap không tạo persistence context mới; Session nhận được đại diện cho persistence context của EntityManager hiện tại.

Trong ứng dụng Spring, hãy unwrap bên trong transactional method và để Spring quản lý lifecycle. Không tự mở/đóng/commit Session, không chia sẻ Session giữa thread và không giữ nó sau transaction. Khi chạy JDBC trực tiếp, phải chú ý flush trước khi đọc, refresh/clear sau khi ghi và đóng các JDBC statement/result set nhưng để Hibernate quản lý connection.

Giữ code JPA ở repository/service thông thường và cô lập phần Hibernate-specific tại nơi thực sự cần. Kiểm thử với Hibernate/database thật, đặc biệt cho filter, fetch profile, transaction và direct JDBC, để bảo đảm việc dùng Session không làm sai semantics dữ liệu hoặc lifecycle.