# Tiêm EntityManager bằng @PersistenceContext

`EntityManager` là API trung tâm của Jakarta Persistence để làm việc với persistence context: tìm entity, tạo query, lưu entity mới, xóa entity, đồng bộ thay đổi và quản lý trạng thái managed/detached. Trong một custom repository hoặc DAO của Spring Data JPA, có thể tiêm `EntityManager` bằng annotation chuẩn `@PersistenceContext`.

Trong ứng dụng Spring, điểm quan trọng là đối tượng được tiêm thường là **shared EntityManager proxy**. Proxy này chuyển lời gọi tới EntityManager gắn với transaction hiện tại. Nhờ vậy, một DAO singleton có thể giữ tham chiếu proxy mà không chia sẻ cùng một EntityManager thật giữa các request đồng thời.

Bài này dùng Spring Boot 3.x, Spring Framework 6.x, Spring Data JPA 3.x, Jakarta Persistence và Java 17+. Với Spring Boot 2.x, import annotation thuộc namespace `javax.persistence`; từ Spring Boot 3.x chuyển sang `jakarta.persistence`. Không trộn hai namespace trong cùng ứng dụng.

## 1. EntityManager và persistence context

`EntityManager` cung cấp API để tương tác với persistence context. Persistence context theo dõi các entity đang được quản lý và trạng thái thay đổi của chúng.

Một entity thường ở một trong các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| New / transient | Object mới, chưa được persistence context quản lý và chưa có bản ghi tương ứng |
| Managed / persistent | Entity đang được persistence context quản lý; thay đổi có thể được dirty checking ghi xuống database |
| Detached | Entity có identity nhưng không còn thuộc persistence context hiện tại |
| Removed | Entity đang được đánh dấu xóa; lệnh DELETE được đồng bộ khi flush/commit |

Trong một persistence context, mỗi entity type và primary key chỉ có một instance managed tương ứng. Vì thế, hai lần `find()` cùng một ID trong cùng persistence context thường trả về cùng managed instance.

`EntityManager` không phải một DAO stateless đơn giản. Nó giữ trạng thái persistence context và không được chia sẻ trực tiếp giữa các luồng đồng thời. Jakarta Persistence yêu cầu mỗi EntityManager application-managed chỉ phục vụ một đơn vị công việc tại một thời điểm.

## 2. @PersistenceContext là gì?

`@PersistenceContext` là annotation của Jakarta Persistence dùng để khai báo điểm tiêm một EntityManager và persistence context tương ứng:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Repository
public class PersonDao {

    @PersistenceContext
    private EntityManager entityManager;
}
```

Các điểm cần nhớ:

- Import annotation từ `jakarta.persistence` trong Spring Boot 3.x.
- Annotation được đặt trên field hoặc method setter.
- Không đặt `@PersistenceContext` trực tiếp trên constructor; annotation này không phải constructor injection annotation.
- Nếu ứng dụng chỉ có một persistence unit, thường có thể bỏ qua `unitName`.
- Mặc định, persistence context có kiểu `TRANSACTION`.

Trong ứng dụng Spring Boot có starter JPA và cấu hình JPA thông thường, Spring tự xử lý annotation này. Với cấu hình Spring thuần, cần có `PersistenceAnnotationBeanPostProcessor` để xử lý các điểm tiêm `@PersistenceContext` và `@PersistenceUnit`.

## 3. Shared EntityManager proxy trong Spring

Một điểm quan trọng của Spring ORM là EntityManager được tiêm qua `@PersistenceContext` thường là proxy dùng chung, không phải một EntityManager thật được tạo một lần rồi chia sẻ cho mọi request.

Spring proxy chuyển lời gọi tới EntityManager gắn với transaction hiện tại. Khi một service mở transaction bằng `@Transactional`, `JpaTransactionManager` liên kết EntityManager phù hợp với transaction/thread đó. DAO sử dụng proxy sẽ tham gia cùng persistence context.

```java
@Repository
public class PersonDao {

    @PersistenceContext
    private EntityManager entityManager;

    public Person findById(Long id) {
        return entityManager.find(Person.class, id);
    }
}
```

Nếu nhiều request gọi cùng một bean PersonDao, mỗi request có thể tham gia transaction và persistence context riêng. Tham chiếu proxy là đối tượng dùng chung; EntityManager thật phía sau được Spring lựa chọn theo transaction hiện hành.

Không được suy luận rằng EntityManager thật có thể được chia sẻ giữa các thread chỉ vì field được tiêm vào singleton. Sự an toàn đến từ proxy và cơ chế transaction-bound của Spring.

### 3.1. Khi không có transaction hiện hành

Với shared EntityManager proxy của Spring, nếu không có EntityManager gắn với transaction hiện tại, proxy có thể tạo một EntityManager tạm cho từng thao tác và đóng nó sau thao tác. Những entity trả về trong trường hợp đó có thể nhanh chóng trở thành detached.

Các thao tác cần transaction như `persist()`, `remove()` hoặc `flush()` không thể được thực hiện tùy tiện ngoài transaction và có thể phát sinh `TransactionRequiredException`.

Vì vậy, với nghiệp vụ đọc/ghi nhiều bước, nên đặt transaction ở service hoặc phương thức custom repository phù hợp thay vì dựa vào các thao tác đơn lẻ ngoài transaction.

## 4. Tích hợp với custom repository fragment

Một tình huống phổ biến là Spring Data query method không đủ linh hoạt, ví dụ cần Criteria API, query động hoặc xử lý đặc thù. Có thể tạo custom repository fragment rồi tiêm EntityManager vào implementation.

Interface fragment:

```java
public interface PersonSearchRepository {

    List<Person> searchByNamePrefix(String prefix);
}
```

Implementation theo quy ước hậu tố `Impl`:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import java.util.List;
import java.util.Locale;

public class PersonSearchRepositoryImpl
        implements PersonSearchRepository {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<Person> searchByNamePrefix(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            return List.of();
        }

        String normalized = prefix.trim().toLowerCase(Locale.ROOT);

        TypedQuery<Person> query = entityManager.createQuery(
            """
            select p
            from Person p
            where lower(p.name) like :prefix
            order by p.name asc, p.id asc
            """,
            Person.class
        );

        return query
            .setParameter("prefix", normalized + "%")
            .getResultList();
    }
}
```

Repository chính kết hợp fragment:

```java
public interface PersonRepository
        extends JpaRepository<Person, Long>, PersonSearchRepository {
}
```

Spring Data ghép implementation fragment vào repository dựa trên tên interface và quy ước tên implementation. Với interface `PersonSearchRepository`, class mặc định là `PersonSearchRepositoryImpl`. Nếu dự án đổi postfix hoặc cấu hình fragment khác, hãy tuân theo cấu hình repository hiện tại.

Ví dụ dùng JPQL nên tham chiếu entity name và property Java (`Person`, `name`, `id)), không dùng tên bảng/cột vật lý. Giá trị prefix được bind bằng named parameter; không nối chuỗi đầu vào trực tiếp vào JPQL.

Nếu custom DAO là một Spring bean độc lập thay vì repository fragment, có thể đánh dấu class bằng `@Repository` để đăng ký bean và tham gia cơ chế exception translation của Spring.

## 5. Transaction cho custom repository

Nên đặt transaction ở service bao quanh một use case:

```java
@Service
public class PersonSearchService {

    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Person> search(String prefix) {
        return repository.searchByNamePrefix(prefix);
    }
}
```

Trong luồng này:

1. Caller gọi service qua Spring proxy.
2. Transaction interceptor mở hoặc tham gia transaction.
3. `JpaTransactionManager` gắn EntityManager với transaction hiện tại.
4. Custom repository dùng shared EntityManager proxy.
5. Lời gọi query được chuyển tới EntityManager đang gắn với transaction.
6. Transaction kết thúc khi service method hoàn thành hoặc phát sinh lỗi cần rollback.

Có thể đặt `@Transactional` trên method implementation của custom repository nếu đó là ranh giới phù hợp. Tuy nhiên, transaction ở service thường thể hiện rõ hơn một use case có nhiều thao tác repository.

### 5.1. Self-invocation và transaction proxy

Trong proxy mode mặc định của Spring, lời gọi nội bộ từ một method sang method khác trong cùng object không đi qua proxy. Ví dụ method A gọi trực tiếp method B cùng class thì annotation `@Transactional` trên B có thể không được áp dụng như mong đợi.

Để transaction hoạt động theo thiết kế, gọi method transactional qua Spring-managed bean/proxy, hoặc tổ chức lại ranh giới service. Không tự tạo DAO bằng `new` vì object đó không được Spring quản lý và các annotation injection/transaction có thể không được xử lý.

## 6. Các thao tác EntityManager thường dùng

### 6.1. find(): tìm theo primary key

```java
Person person = entityManager.find(Person.class, 10L);
```

`find()` trả entity nếu tìm thấy hoặc null nếu không có. Entity được trả về sẽ managed trong persistence context hiện tại.

### 6.2. getReference(): lấy reference theo ID

```java
Person reference = entityManager.getReference(Person.class, 10L);
```

`getReference()` có thể trả về proxy/reference mà chưa cần tải đầy đủ dữ liệu ngay. Nếu entity không tồn tại, lỗi có thể chỉ xuất hiện khi proxy được truy cập hoặc khi provider cần xác thực sự tồn tại. Dùng nó khi cần tham chiếu entity theo ID, chẳng hạn gán quan hệ, và không cần đọc các field của entity ngay lập tức.

Không dùng `getReference()` như cách kiểm tra chắc chắn rằng ID tồn tại.

### 6.3. persist(): đưa entity mới vào persistence context

```java
Person person = new Person();
person.setName("Lan");

entityManager.persist(person);
```

`persist()` dành cho entity mới. Entity được quản lý; INSERT được đồng bộ khi flush hoặc commit theo chiến lược provider/ID generation. Không dùng persist để cập nhật một entity detached.

### 6.4. merge(): hợp nhất trạng thái detached

```java
Person managed = entityManager.merge(detachedPerson);
```

`merge()` sao chép trạng thái của object truyền vào sang một instance managed có cùng identity hoặc tạo instance managed tương ứng. Giá trị trả về mới là instance managed cần tiếp tục sử dụng.

Object truyền vào không tự động trở thành managed chỉ vì gọi merge. Vì vậy, hãy viết:

```java
Person managed = entityManager.merge(detachedPerson);
managed.setName("Tên mới");
```

Không giả định object `detachedPerson` đã được attach lại.

### 6.5. remove(): đánh dấu entity để xóa

```java
Person managed = entityManager.find(Person.class, id);

if (managed != null) {
    entityManager.remove(managed);
}
```

`remove()` yêu cầu entity managed. Nếu đang có entity detached, hãy tìm lại entity managed hoặc hợp nhất theo đúng nghiệp vụ rồi xóa instance managed. Lệnh DELETE được đồng bộ khi flush/commit.

### 6.6. refresh(): tải lại trạng thái từ database

```java
entityManager.refresh(person);
```

`refresh()` ghi đè trạng thái hiện tại của entity managed bằng trạng thái từ database. Các thay đổi chưa flush trên object có thể bị mất. Chỉ dùng khi thực sự cần đọc lại trạng thái mới từ database.

### 6.7. detach() và clear()

```java
entityManager.detach(person); // Bỏ quản lý một entity
entityManager.clear();        // Bỏ quản lý tất cả entity trong context
```

Sau khi detach/clear, thay đổi trên object Java không còn được dirty checking tự động đồng bộ. `clear()` tác động tới tất cả entity đang managed trong persistence context hiện tại, nên cần thận trọng nếu service còn dùng những entity khác.

## 7. Dirty checking: không có method update()

JPA không yêu cầu gọi `update()` cho entity managed. Khi thay đổi thuộc tính của entity đang được quản lý, provider theo dõi trạng thái và đồng bộ thay đổi khi flush/commit.

```java
@Transactional
public void renamePerson(Long id, String newName) {
    Person person = entityManager.find(Person.class, id);

    if (person == null) {
        throw new PersonNotFoundException(id);
    }

    person.setName(newName);
    // Dirty checking phát hiện thay đổi và ghi UPDATE khi flush/commit.
}
```

Không cần gọi `merge(person)` trong ví dụ này vì person đã managed. Gọi merge dư thừa có thể làm code khó hiểu và tạo thêm chi phí.

Nếu entity được tải ở transaction khác hoặc nhận từ request dưới dạng detached object, cần xác định rõ cách cập nhật. Không nên merge trực tiếp toàn bộ entity do client gửi lên nếu có thể ghi đè field nhạy cảm hoặc trạng thái mà client không được quyền thay đổi. Thường nên tải entity managed rồi áp dụng các field được phép từ DTO.

## 8. flush() không phải commit()

`flush()` yêu cầu persistence provider đồng bộ các thay đổi đang chờ trong persistence context xuống database:

```java
entityManager.persist(person);
entityManager.flush();
```

Sau flush, SQL có thể đã được gửi và constraint có thể được kiểm tra, nhưng transaction vẫn chưa commit. Một transaction có thể flush nhiều lần trước khi commit hoặc rollback.

Phân biệt:

| Thao tác | Ý nghĩa |
|---|---|
| Thay đổi entity managed | Cập nhật trạng thái trong persistence context |
| flush() | Đồng bộ thay đổi pending với database trong transaction hiện tại |
| commit | Xác nhận transaction theo transaction manager |
| rollback | Hủy các thay đổi thuộc transaction chưa commit |

Không gọi `entityManager.getTransaction().begin()` hoặc `commit()` trong ứng dụng Spring đang dùng `@Transactional` và `JpaTransactionManager`. Hãy để Spring quản lý transaction. `getTransaction()` là cách quản lý resource-local transaction thủ công cho EntityManager application-managed trong những trường hợp riêng.

## 9. Tạo JPQL query bằng EntityManager

Khi repository method khai báo sẵn không đủ linh hoạt, có thể tạo typed JPQL query:

```java
TypedQuery<Person> query = entityManager.createQuery(
    """
    select p
    from Person p
    where p.active = :active
      and p.city = :city
    order by p.name asc, p.id asc
    """,
    Person.class
);

List<Person> people = query
    .setParameter("active", true)
    .setParameter("city", "Da Nang")
    .getResultList();
```

JPQL dùng entity và property Java. Dùng `TypedQuery<T>` để nhận kiểu kết quả rõ ràng, tránh ép kiểu từ `Query`/Object.

Nếu cần tối đa một kết quả, có thể dùng `getSingleResult()` nhưng cần xử lý `NoResultException` và `NonUniqueResultException`. Với truy vấn tìm kiếm có thể không có dữ liệu, `getResultList()` thường dễ xử lý hơn vì trả list rỗng.

### 9.1. Bind parameter, không nối chuỗi

An toàn:

```java
query.setParameter("city", city);
```

Không an toàn:

```java
String jpql = "select p from Person p where p.city = '"
        + city + "'";
```

Bind parameter tránh việc dữ liệu đầu vào bị diễn giải thành cú pháp truy vấn. Tên entity/property trong JPQL phải do code kiểm soát; parameter chỉ dùng cho giá trị.

## 10. Pagination với EntityManager

Có thể phân trang một TypedQuery bằng `setFirstResult()` và `setMaxResults()`:

```java
TypedQuery<Person> query = entityManager.createQuery(
    """
    select p
    from Person p
    where p.active = :active
    order by p.id asc
    """,
    Person.class
);

List<Person> page = query
    .setParameter("active", true)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

`setFirstResult` nhận offset bắt đầu từ 0; `setMaxResults` đặt số hàng tối đa. Với page number và page size, offset thường được tính bằng `pageNumber * pageSize`. Cần kiểm soát page size và offset ở tầng API/service, đặc biệt với trang rất sâu.

Nếu cần trả về Page có tổng số bản ghi, phải thực hiện count query tương ứng hoặc dùng Spring Data repository pagination. EntityManager không tự tạo total count chỉ từ truy vấn lấy nội dung.

## 11. Multi-persistence-unit và unitName

Một ứng dụng có thể có nhiều persistence unit, ví dụ dữ liệu đơn hàng và dữ liệu báo cáo nằm ở hai database khác nhau. Khi đó, cần chỉ rõ persistence unit:

```java
@PersistenceContext(unitName = "ordersPU")
private EntityManager ordersEntityManager;

@PersistenceContext(unitName = "reportingPU")
private EntityManager reportingEntityManager;
```

`unitName` là tên persistence unit mà EntityManagerFactory được cấu hình cung cấp; nó không mặc nhiên là tên field, tên repository hoặc tên bean Spring. Nếu chỉ có một persistence unit, thường có thể bỏ thuộc tính này.

Với Spring Boot/Spring Data JPA, mỗi persistence unit thường cần EntityManagerFactory và transaction manager phù hợp. Repository tương ứng cần được cấu hình dùng đúng factory/transaction manager, chẳng hạn qua `entityManagerFactoryRef` và `transactionManagerRef` trong `@EnableJpaRepositories`.

Không tiêm nhầm EntityManager của database A rồi thao tác entity thuộc persistence unit B. Mỗi EntityManager chỉ quản lý entity thuộc persistence unit gắn với factory của nó.

## 12. @PersistenceContext và @PersistenceUnit khác nhau

Hai annotation có mục đích khác nhau:

| Annotation | Tiêm đối tượng | Khi dùng |
|---|---|---|
| `@PersistenceContext` | EntityManager | Truy vấn và quản lý entity trong persistence context |
| `@PersistenceUnit` | EntityManagerFactory | Khi cần tạo EntityManager application-managed hoặc truy cập factory |

Ví dụ:

```java
@PersistenceUnit
private EntityManagerFactory entityManagerFactory;
```

Trong ứng dụng Spring thông thường, ưu tiên `@PersistenceContext` cho DAO/custom repository để tham gia transaction do Spring quản lý. Tự gọi `entityManagerFactory.createEntityManager()` tạo EntityManager application-managed; caller phải quản lý transaction và đóng EntityManager đúng cách.

Ví dụ quản lý thủ công chỉ để hiểu vòng đời:

```java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    EntityTransaction transaction = em.getTransaction();
    transaction.begin();

    // Thực hiện công việc với em.

    transaction.commit();
} catch (RuntimeException exception) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw exception;
} finally {
    em.close();
}
```

Không áp dụng mẫu này cho EntityManager proxy được tiêm bằng `@PersistenceContext`. Không gọi `close()` trên shared EntityManager proxy và không tự quản lý transaction của Spring.

## 13. Field injection và setter injection

Field injection ngắn gọn:

```java
@PersistenceContext
private EntityManager entityManager;
```

Setter injection:

```java
private EntityManager entityManager;

@PersistenceContext
public void setEntityManager(EntityManager entityManager) {
    this.entityManager = entityManager;
}
```

Setter injection hữu ích nếu cần xử lý thêm khi dependency được gán, nhưng phần lớn DAO chỉ cần field injection. `@PersistenceContext` không có constructor target; nếu muốn constructor injection, có thể đăng ký shared proxy như một bean Spring.

Ví dụ tạo bean proxy:

```java
@Configuration
public class JpaSharedEntityManagerConfiguration {

    @Bean
    public EntityManager sharedEntityManager(EntityManagerFactory emf) {
        return SharedEntityManagerCreator.createSharedEntityManager(emf);
    }
}
```

Sau đó có thể inject bean này qua constructor theo type/qualifier. Với nhiều persistence unit, tạo proxy tương ứng cho từng EntityManagerFactory và dùng `@Qualifier` rõ ràng. Chỉ làm vậy khi dự án thực sự cần constructor injection cho EntityManager; `@PersistenceContext` vẫn là cách chuẩn và đơn giản cho DAO JPA.

## 14. PersistenceContextType.TRANSACTION và EXTENDED

Mặc định:

```java
@PersistenceContext(type = PersistenceContextType.TRANSACTION)
private EntityManager entityManager;
```

Transaction-scoped persistence context gắn với transaction hiện tại. Khi transaction kết thúc, entity thuộc context đó trở thành detached.

`PersistenceContextType.EXTENDED` có vòng đời dài hơn transaction:

```java
@PersistenceContext(type = PersistenceContextType.EXTENDED)
private EntityManager entityManager;
```

Extended persistence context không phải lựa chọn mặc định cho Spring singleton service/DAO. Nó giữ trạng thái qua nhiều transaction và không thread-safe; dùng trong component có lifecycle và concurrency được kiểm soát chặt, chẳng hạn một stateful conversation phù hợp. Không đặt extended EntityManager vào bean singleton được nhiều request truy cập đồng thời.

Với ứng dụng web stateless thông thường, dùng kiểu TRANSACTION mặc định.

## 15. Synchronization và properties

Jakarta Persistence còn cho phép cấu hình:

- `synchronization`: persistence context tham gia đồng bộ với transaction tự động hay cần gọi `joinTransaction()` trong những trường hợp phù hợp.
- `properties`: thuộc tính cấu hình cho container/provider.
- `unitName`: chọn persistence unit.
- `type`: chọn transaction-scoped hay extended.

Ví dụ dạng khai báo:

```java
@PersistenceContext(
    unitName = "ordersPU",
    type = PersistenceContextType.TRANSACTION
)
private EntityManager entityManager;
```

Trong ứng dụng Spring Boot thông thường, để mặc định synchronization và properties thường là đủ. Chỉ thay đổi khi hiểu rõ transaction type, JTA/resource-local, provider và cách Spring cấu hình EntityManagerFactory. Không dùng annotation properties để thay thế cấu hình chung của datasource hoặc transaction manager.

## 16. Lỗi thường gặp khi tiêm EntityManager

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| EntityManager là null | Class được tạo bằng new hoặc không nằm trong Spring container | Để Spring tạo bean và xử lý injection |
| Không tìm thấy EntityManagerFactory | Thiếu dependency/config JPA hoặc datasource | Kiểm tra starter, DataSource và JPA auto-configuration |
| Không nhận diện @PersistenceContext | Thiếu persistence annotation post-processor trong cấu hình Spring thủ công | Đăng ký PersistenceAnnotationBeanPostProcessor hoặc dùng cấu hình JPA phù hợp |
| ClassNotFoundException javax.persistence | Dùng namespace cũ trong Spring Boot 3 | Đổi sang jakarta.persistence |
| Không inject được constructor | @PersistenceContext chỉ hỗ trợ field/method | Dùng field/setter hoặc đăng ký SharedEntityManagerCreator bean |
| No qualifying EntityManagerFactory khi có nhiều DB | Không xác định persistence unit phù hợp | Dùng unitName và cấu hình factory/transaction manager tương ứng |
| TransactionRequiredException khi persist/remove/flush | Không có transaction đang hoạt động | Đặt @Transactional ở service/repository và kiểm tra transaction manager |
| LazyInitializationException | Truy cập association lazy sau khi persistence context đóng | Đọc dữ liệu trong transaction hoặc dùng fetch plan/DTO |
| Entity trả về đã detached | Entity được tải ngoài transaction hoặc transaction đã kết thúc | Hoàn tất thao tác trong transaction; trả DTO nếu cần dữ liệu độc lập |
| Dữ liệu cũ sau native/bulk DML | Persistence context vẫn giữ entity đã load trước đó | Flush trước khi cần, sau đó clear/refresh có chủ đích |
| ConcurrentModification hoặc trạng thái khó đoán | Chia sẻ EntityManager thật giữa các thread | Dùng shared proxy của Spring, không chia sẻ EM application-managed |
| Đóng EntityManager làm lỗi thao tác tiếp theo | Gọi close() trên proxy được tiêm | Không tự đóng EntityManager từ @PersistenceContext |
| Thay đổi entity không được lưu | Entity detached hoặc không có transaction/dirty checking phù hợp | Tải entity managed trong transaction hoặc merge và dùng instance trả về |

## 17. Kiểm thử custom repository có EntityManager

Có thể dùng `@DataJpaTest` để kiểm tra custom fragment và query:

```java
@DataJpaTest
class PersonSearchRepositoryTest {

    @Autowired
    PersonRepository repository;

    @Test
    void searchesPeopleByNamePrefix() {
        Person lan = new Person();
        lan.setName("Lan");

        Person linh = new Person();
        linh.setName("Linh");

        Person minh = new Person();
        minh.setName("Minh");

        repository.saveAll(List.of(lan, linh, minh));
        repository.flush();

        List<Person> result =
            repository.searchByNamePrefix("L");

        assertThat(result)
            .extracting(Person::getName)
            .containsExactly("Lan", "Linh");
    }
}
```

Đây là khung test minh họa; entity Person cần constructor/accessor và các constraint phù hợp. Test xác nhận fragment được Spring Data ghép vào repository và custom query chạy qua EntityManager được tiêm.

Nên bổ sung test cho:

- Prefix null hoặc blank theo chính sách API.
- Parameter chứa ký tự đặc biệt để xác nhận bind parameter hoạt động.
- Không có kết quả trả list rỗng.
- Sort ổn định nếu kết quả có thể trùng tên.
- Transaction rollback khi use case thất bại.
- Nhiều persistence unit nếu ứng dụng có nhiều database.
- Database thật/Testcontainers khi query dùng function hoặc dialect riêng.

## 18. Checklist triển khai

Trước khi đưa custom repository vào ứng dụng:

1. Dùng đúng namespace `jakarta.persistence` hoặc `javax.persistence` theo phiên bản Spring Boot.
2. Đặt `@PersistenceContext` trên field hoặc setter của Spring-managed bean.
3. Đảm bảo persistence unit và EntityManagerFactory được cấu hình.
4. Dùng transaction-scoped persistence context mặc định.
5. Đặt `@Transactional` ở ranh giới use case phù hợp.
6. Dùng JPQL với entity/property Java hoặc native SQL khi có lý do rõ ràng.
7. Bind mọi giá trị đầu vào bằng parameter.
8. Không gọi close/begin/commit trên shared EntityManager proxy.
9. Không chia sẻ EntityManager thật giữa các thread.
10. Với nhiều persistence unit, chỉ rõ unitName và transaction manager.
11. Trả DTO khi dữ liệu cần sống ngoài transaction hoặc không muốn lộ entity graph.
12. Kiểm thử custom fragment và transaction trên database phù hợp.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework — JPA](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html): shared EntityManager, @PersistenceContext, @PersistenceUnit, transaction integration và multiple persistence units.
- [Jakarta Persistence — PersistenceContext API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/persistencecontext): các thuộc tính unitName, type, synchronization, properties và phạm vi annotation.
- [Jakarta Persistence — EntityManager API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager): các thao tác quản lý entity, query, flush, clear, detach và vòng đời persistence context.
- [Spring Framework — JpaTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html): transaction manager gắn EntityManager với thread và hỗ trợ shared EntityManager proxy.

**Nguyên tắc xuyên suốt:** dùng `@PersistenceContext` để tiêm shared EntityManager proxy vào custom repository/DAO do Spring quản lý. Proxy tham gia persistence context của transaction hiện tại, trong khi EntityManager thật vẫn giữ quy tắc không chia sẻ giữa các thread. Để Spring quản lý transaction, không tự đóng proxy hoặc gọi begin/commit; chỉ dùng EntityManagerFactory và EntityManager application-managed khi có nhu cầu vòng đời riêng, được quản lý đầy đủ.
