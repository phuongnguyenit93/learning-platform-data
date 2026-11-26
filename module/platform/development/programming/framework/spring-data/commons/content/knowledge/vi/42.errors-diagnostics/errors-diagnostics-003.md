# Repository cơ sở thiếu @NoRepositoryBean

## Mục tiêu và phạm vi

Khi nhiều repository dùng chung các phương thức, ứng dụng thường tạo một interface cơ sở có tham số generic. Interface đó mô tả hợp đồng dùng lại, còn các repository con mới gắn với domain type cụ thể.

Nếu repository cơ sở bị phát hiện như một repository độc lập, framework có thể cố tạo bean cho một interface chưa có domain type cụ thể. Đây là một nguyên nhân thường gặp của lỗi khởi tạo liên quan đến generic hoặc kiểu không được store quản lý.

Spring Data Commons cung cấp `@NoRepositoryBean` để biểu đạt rằng một repository interface không phải đích tạo repository bean độc lập.

Sau bài học này, bạn có thể:

- Nhận diện interface cơ sở cần đánh dấu.
- Hiểu vì sao thiếu annotation có thể làm ứng dụng không khởi động.
- Phân biệt lỗi này với generic sai, entity mapping sai hoặc query method thiếu implementation.
- Sửa đúng interface và giữ các repository con hoạt động.
- Thiết kế kiểm thử hồi quy xác nhận quá trình scan và tạo repository thực.

Ví dụ JPA minh họa triệu chứng cụ thể của một store. Commons cung cấp annotation và abstraction repository; thông báo lỗi cuối cùng còn phụ thuộc module, cấu hình và phiên bản.

## 1. Phân biệt interface cơ sở với repository cụ thể

Xét hai vai trò:

```text
BaseRepository<T, ID>
    |
    +-- CustomerRepository
    |       T = Customer
    |       ID = Long
    |
    +-- ProductRepository
            T = Product
            ID = Long
```

BaseRepository chỉ là hợp đồng dùng chung. Nó chưa nói rằng T là Customer hay Product.

CustomerRepository là repository cụ thể, từ đó framework có thể xác định domain type và ID type để tạo implementation phù hợp.

| Interface | Vai trò | Có muốn tạo repository bean độc lập không? |
|---|---|---|
| BaseRepository<T, ID> | Hợp đồng cơ sở generic | Không |
| CustomerRepository | Truy cập Customer | Có |
| ProductRepository | Truy cập Product | Có |

Tên `BaseRepository`, `CommonRepository` hoặc `GenericRepository` không tự làm interface trở thành một tầng cơ sở được loại khỏi quá trình tạo bean.

Tính chất generic cũng không phải lời khai báo đủ rõ rằng interface không được dùng độc lập.

## 2. Ví dụ lỗi tối thiểu

Repository cơ sở chưa được đánh dấu:

```java
package example.customer.persistence;

import org.springframework.data.repository.CrudRepository;

public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Repository cụ thể:

```java
package example.customer.persistence;

import java.util.Optional;

public interface CustomerRepository
        extends BaseRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

Giả sử cả hai interface nằm trong phạm vi scan repository và ứng dụng dùng JPA.

Framework có thể phát hiện BaseRepository như một candidate riêng. Trong quá trình tạo repository cho candidate này, domain type chưa được gắn với entity cụ thể.

Một triệu chứng minh họa có thể là:

```text
BeanCreationException: lỗi tạo repository bean 'baseRepository'
Caused by: IllegalArgumentException:
Not a managed type: class java.lang.Object
```

Đây là dạng thông báo minh họa, không phải stack trace đã chạy trong bài. Ở cấu hình khác, có thể gặp thông báo không phân giải được domain type hoặc một lỗi khởi tạo liên quan khác.

Điều đáng chú ý là tên repository bean và domain type mà framework đang xử lý. Nếu bean lỗi là BaseRepository và kiểu domain là Object hoặc một generic chưa phân giải, cần kiểm tra interface cơ sở trước.

Không vội thêm Object vào danh sách entity hoặc cố ánh xạ Object thành một bảng để làm thông báo biến mất.

## 3. Cách sửa đúng

Đánh dấu repository cơ sở bằng annotation của Commons:

```java
package example.customer.persistence;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Giữ repository cụ thể với generic đầy đủ:

```java
package example.customer.persistence;

import java.util.Optional;

public interface CustomerRepository
        extends BaseRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

Ý nghĩa:

```text
BaseRepository:
    vẫn là superinterface của CustomerRepository
    không phải đích tạo repository bean riêng

CustomerRepository:
    được scan theo cấu hình
    domain type là Customer
    ID type là Long
    được tạo repository implementation phù hợp store
```

Annotation không xóa hợp đồng CRUD mà repository con kế thừa. Nó cũng không tự loại các repository con khỏi quá trình tạo bean.

Không gắn `@NoRepositoryBean` lên CustomerRepository nếu ứng dụng cần inject chính repository đó. Làm vậy có thể khiến bean cần dùng không được tạo.

## 4. Annotation này điều khiển điều gì?

`@NoRepositoryBean` được dùng trong cơ chế phát hiện và tạo repository để nhận diện interface không cần tạo repository bean riêng.

Nó không phải:

- Annotation khai báo entity.
- Cơ chế chọn transaction manager.
- Cơ chế tự tạo implementation cho mọi method tùy biến.
- Cơ chế phân quyền.
- Cách chuyển repository thành chỉ đọc.
- Cách loại domain type khỏi mapping của store.
- Annotation chung để vô hiệu hóa mọi loại Spring bean.

Phân biệt với một số annotation khác:

| Annotation hoặc cơ chế | Trách nhiệm khác biệt |
|---|---|
| NoRepositoryBean | Đánh dấu repository interface không phải đích tạo repository bean riêng |
| Repository | Stereotype của Spring; không thay thế NoRepositoryBean trên tầng repository cơ sở |
| Entity trong JPA | Đánh dấu kiểu domain tham gia mapping JPA |
| Document của document store | Cung cấp mapping theo module tương ứng |
| Transactional | Mô tả ranh giới và thuộc tính giao dịch theo hạ tầng được cấu hình |
| NoRepositoryBean trên repository thật | Có thể làm thiếu bean mà ứng dụng cần |

Thêm `@Repository` lên BaseRepository không giải quyết việc nó đang bị coi là một repository độc lập.

Repository interface cũng thường được Spring Data đăng ký bằng repository scanning, không phải vì cần thêm stereotype lên mọi interface cụ thể.

## 5. Vì sao lỗi có thể khác nhau giữa các dự án?

Để lỗi xuất hiện, interface cơ sở phải thực sự nằm trong đường phát hiện hoặc tạo repository.

Các yếu tố ảnh hưởng gồm:

- Phạm vi package scan.
- Module Spring Data có mặt.
- Cách module xác định candidate thuộc store nào.
- Generic hierarchy.
- Mapping của domain.
- Thời điểm khởi tạo repository.
- Các filter hoặc cấu hình đăng ký riêng.

Trong dự án nhiều store, module có thể không nhận interface cơ sở là candidate của nó, hoặc ghi thông báo chưa xác định được store. Khi đó, lỗi có thể xuất hiện dưới dạng khác hoặc interface vô tình không được xử lý.

Không thấy lỗi ở một cấu hình không chứng minh interface cơ sở đã được khai báo đúng. Khi phạm vi scan hoặc classpath thay đổi, candidate trước đó bị bỏ qua có thể bắt đầu được xử lý.

Ngược lại, không phải mọi thông báo `Not a managed type` đều do thiếu NoRepositoryBean. Nếu bean lỗi là CustomerRepository với domain Customer, cần điều tra mapping Customer và cấu hình store.

## 6. Đọc chuỗi lỗi theo repository và domain type

Một lỗi ở tầng service có thể chỉ là hậu quả:

```text
Service không được tạo
    |
Không inject được CustomerRepository
    |
Một repository factory khởi tạo thất bại
    |
Domain type hoặc mapping không hợp lệ
```

Các exception ngoài cùng như UnsatisfiedDependencyException hoặc BeanCreationException chưa mô tả đủ nguyên nhân.

Quy trình chẩn đoán:

1. Xác định repository bean đầu tiên thất bại.
2. Đọc cause liên quan đến metadata, domain type hoặc query creation.
3. Xem candidate là interface cơ sở hay repository cụ thể.
4. Kiểm tra generic được gắn như thế nào ở interface đó.
5. Kiểm tra annotation trên các interface cơ sở bị scan.
6. Nếu domain đã cụ thể, kiểm tra mapping và module store.
7. Xác nhận cấu hình scan đang bao phủ những package nào.

Bảng định hướng:

| Triệu chứng | Giả thuyết cần kiểm tra |
|---|---|
| Bean lỗi là baseRepository, domain Object | Interface generic cơ sở bị tạo độc lập |
| Bean lỗi là customerRepository, domain Customer | Mapping hoặc cấu hình store của Customer |
| Không có bean CustomerRepository sau khi sửa | Repository cụ thể có bị đánh dấu NoRepositoryBean hoặc bị loại khỏi scan không? |
| Lỗi query creation cho method mới ở base | Method chưa có implementation hoặc không phải derived query hợp lệ |
| Có nhiều bean phù hợp kiểu BaseRepository | Các repository con đều gán được vào kiểu cơ sở |
| Module không xác định được store | Repository/mapping và phạm vi nhiều store chưa đủ rõ |

Ghi lại thông tin repository, domain và phase bị lỗi thường hữu ích hơn việc chỉ sao chép dòng exception cuối mà bỏ toàn bộ ngữ cảnh.

## 7. Nhiều tầng kế thừa cần biểu đạt vai trò rõ ràng

Một ứng dụng có thể có nhiều interface trung gian:

```java
import java.util.NoSuchElementException;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

```java
import java.util.NoSuchElementException;

import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface RequiredRepository<T, ID>
        extends BaseRepository<T, ID> {

    default T requireById(ID id) {
        return findById(id)
                .orElseThrow(() ->
                        new NoSuchElementException(
                                "Entity not found"));
    }
}
```

```java
public interface CustomerRepository
        extends RequiredRepository<Customer, Long> {
}
```

Trong ví dụ, hai tầng cơ sở đều không được dùng độc lập nên được đánh dấu rõ ràng.

Không giả định annotation trên một superinterface bất kỳ sẽ tự thay thế việc xem xét mọi interface cơ sở khác được scan. Đặc biệt, việc CrudRepository hoặc JpaRepository đã là abstraction của framework không làm mọi interface tự tạo kế thừa nó trở thành tầng cơ sở được loại đúng ý định.

Method default trong RequiredRepository đã có thân thực thi và gọi hợp đồng findById được kế thừa.

Tuy nhiên, annotation không tự thêm transaction cho method default, không quyết định exception đó được chuyển thành HTTP status nào và không thay đổi chính sách không tìm thấy ở toàn ứng dụng.

Nếu nghiệp vụ cần exception riêng, hãy định nghĩa hợp đồng đó một cách có chủ đích.

## 8. Generic của repository con vẫn phải đúng

Cách khai báo không nên dùng:

```java
@SuppressWarnings("rawtypes")
public interface CustomerRepository
        extends BaseRepository {
}
```

BaseRepository có NoRepositoryBean nhưng repository con vẫn dùng raw type. Annotation không thể tự suy ra Customer và Long từ tên interface.

Cách đúng:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, Long> {
}
```

Các điểm cần kiểm tra:

- Domain type cuối cùng đã được gắn với một class cụ thể chưa?
- ID type có phù hợp mô hình lưu trữ không?
- Có tầng generic trung gian làm mất thông tin type không?
- Có import nhầm một class cùng tên từ package khác không?

Một lỗi ID type không khớp không nhất thiết luôn xuất hiện cùng một thông báo hoặc ở startup. Nó có thể bộc lộ ở binding, conversion hoặc khi thực thi method.

Không dùng NoRepositoryBean như cách che một khai báo generic sai ở repository cụ thể.

## 9. Phân biệt với lỗi entity chưa được store quản lý

Ví dụ JPA cần domain được đăng ký đúng trong persistence unit.

Entity tối thiểu cho các ví dụ:

```java
package example.customer.persistence;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customer_record")
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
```

Ứng dụng còn cần schema, datasource, mapping scan và transaction infrastructure phù hợp. NoRepositoryBean không cung cấp các cấu hình đó.

Nếu lỗi nói Customer không phải managed type, hãy xem:

- Customer có đúng annotation của module không?
- Entity có thuộc persistence unit mà repository dùng không?
- Có nhiều EntityManagerFactory và repository đang nối nhầm không?
- Có nhầm model dùng cho API với entity lưu trữ không?
- Có cấu hình entity scan bị thiếu không?

Trong dự án nhiều store, cùng tên class hoặc cùng abstraction Repository không đồng nghĩa mọi module đều quản lý được domain đó.

Không gắn NoRepositoryBean lên CustomerRepository để “sửa” lỗi mapping. Cách đó chỉ có thể làm repository biến mất, còn nguyên nhân mapping chưa được xử lý.

## 10. Không tự tạo implementation cho method tùy biến

Xét base repository sau:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    void softDelete(ID id);
}
```

NoRepositoryBean giúp BaseRepository không được tạo độc lập. Nhưng CustomerRepository kế thừa nó vẫn có method softDelete.

Framework cần biết method đó được thực hiện bằng cách nào:

- Implementation cơ sở có hỗ trợ không?
- Có repository fragment tương ứng không?
- Có method default không?
- Có query khai báo hợp lệ theo module không?
- Có thể phân tích như derived query không?

Nếu không có đường thực thi phù hợp, repository cụ thể vẫn có thể khởi tạo thất bại, chẳng hạn khi framework cố tạo query từ method không có ý nghĩa theo mô hình domain.

Đó là vấn đề khác với việc base repository bị scan độc lập.

Các hướng thiết kế có thể gồm:

| Nhu cầu | Cơ chế cần xem xét |
|---|---|
| Kết hợp các method repository đã có bằng logic ngắn | Default method khi phù hợp |
| Tác vụ tùy biến cho một nhóm repository | Repository fragment |
| Thay đổi implementation cơ sở theo module | Custom repository base class và cấu hình factory tương ứng |
| Query được store hỗ trợ | Derived query hoặc query khai báo hợp lệ |

Không chỉ thêm NoRepositoryBean rồi giả định một method mới sẽ tự có hành vi.

Cũng không đặt tên method giống một nghiệp vụ rồi bỏ qua việc nó được route vào fragment hay parser. Khi có lỗi query creation, hãy kiểm tra phương thức nào thực sự được framework coi là query method.

## 11. Base repository chọn lọc phương thức

Có trường hợp muốn chỉ công khai một phần API đọc:

```java
import java.util.Optional;

import org.springframework.data.repository.NoRepositoryBean;
import org.springframework.data.repository.Repository;

@NoRepositoryBean
public interface ReadOnlyRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    Iterable<T> findAll();
}
```

Repository cụ thể:

```java
public interface CustomerReadRepository
        extends ReadOnlyRepository<Customer, Long> {
}
```

Các chữ ký trên tương ứng các thao tác đọc quen thuộc. Module store cần hỗ trợ việc thực hiện chúng theo hợp đồng repository.

Tên ReadOnlyRepository mô tả cách ứng dụng chọn API công khai. Nó không tự làm database chỉ đọc, không cấu hình transaction readOnly và không thay thế phân quyền.

NoRepositoryBean trong ví dụ chỉ kiểm soát việc ReadOnlyRepository không được tạo độc lập.

Nếu ứng dụng đồng thời có CustomerReadRepository và CustomerRepository, đó là hai repository cụ thể cần được cấu hình rõ ràng. Không ghép mọi phương án minh họa trong bài thành cùng một ứng dụng nếu chúng không cần thiết.

## 12. Inject kiểu cơ sở có thể dẫn tới nhiều bean

Sau khi sửa đúng, ứng dụng có thể có:

```text
CustomerRepository extends BaseRepository<Customer, Long>
ProductRepository extends BaseRepository<Product, Long>
```

Các bean repository con đều gán được vào superinterface BaseRepository ở mức hệ thống kiểu.

Vì vậy, đoạn inject quá rộng có thể gây mơ hồ:

```java
public GenericService(BaseRepository<?, ?> repository) {
    // Có thể có nhiều candidate repository cụ thể.
}
```

Không suy rằng NoRepositoryBean có nghĩa `getBeansOfType(BaseRepository.class)` luôn rỗng. Bean của repository con vẫn có thể là một instance gán được vào kiểu đó.

Trong service dùng Customer, thường nên phụ thuộc vào hợp đồng cụ thể:

```java
public CustomerService(CustomerRepository customers) {
    this.customers = customers;
}
```

Nếu thiết kế thật sự cần thu thập hoặc chọn nhiều repository, hãy có cơ chế chọn rõ ràng. Không đánh dấu các repository cụ thể bằng NoRepositoryBean chỉ để giảm số candidate inject.

## 13. Repository cơ sở trung lập và repository cơ sở theo store

Một interface cơ sở có thể dùng abstraction Commons:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

Hoặc dùng abstraction riêng của một module:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface JpaBaseRepository<T, ID>
        extends JpaRepository<T, ID> {
}
```

JpaBaseRepository biểu đạt rõ sự phụ thuộc vào JPA. Không nên dùng nó làm cơ sở cho repository MongoDB hoặc R2DBC chỉ vì các store đều có thao tác CRUD.

Với dự án nhiều module:

- Giữ phạm vi repository scan rõ ràng.
- Nối từng nhóm repository với đúng hạ tầng store.
- Đánh dấu các interface cơ sở không được tạo độc lập.
- Đảm bảo repository cụ thể có domain và store đủ rõ.
- Không dùng annotation để che tình trạng một repository bị nhiều nhóm cấu hình xử lý sai.

NoRepositoryBean giải quyết vai trò của interface cơ sở. Nó không phải cơ chế điều phối nhiều store hoặc đồng bộ dữ liệu xuyên hệ thống.

## 14. Vì sao chỉ thu hẹp scan có thể chưa đủ?

Nếu chuyển BaseRepository ra ngoài phạm vi scan, lỗi tạo bean độc lập có thể biến mất. Đó có thể là một phần tổ chức package hợp lý, nhưng vẫn nên biểu đạt đúng vai trò của interface cơ sở bằng annotation.

Nếu không, một lần mở rộng scan sau này có thể làm lỗi quay lại.

Cẩn thận với filter quá rộng. Một filter theo quan hệ assignable tới BaseRepository có thể loại cả CustomerRepository và ProductRepository vì chúng đều kế thừa BaseRepository.

Điều cần đạt là:

```text
Loại đúng interface cơ sở khỏi đích tạo bean riêng.
Giữ các repository cụ thể cần sử dụng.
```

Không dùng một thay đổi scan diện rộng để làm lỗi biến mất mà không kiểm tra những repository nào đã bị mất.

Nếu dự án có factory hoặc cơ chế đăng ký repository tùy biến, cần kiểm tra chính đường đăng ký đó. Không mặc định mọi đăng ký thủ công đều xử lý annotation y hệt cấu hình scan thông thường.

## 15. Kiểm thử hồi quy bằng context và repository thực

Một test chỉ mock CustomerRepository không chạy repository scanning nên không thể phát hiện đầy đủ lỗi thiếu NoRepositoryBean.

Kiểm thử hồi quy nên xác nhận:

1. Context có cấu hình repository thật khởi tạo thành công.
2. Repository cụ thể được tạo.
3. Domain và query method hoạt động với store kiểm thử.
4. Interface cơ sở không trở thành repository bean riêng.

Ví dụ dùng Spring Boot, JPA, JUnit Jupiter và AssertJ:

```java
import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("repository-test")
@Transactional
class CustomerRepositoryBootstrapTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    CustomerRepository customers;

    @Autowired
    EntityManager entityManager;

    @Test
    void concreteRepositoryIsCreatedAndCanQuery() {
        Customer saved = customers.save(
                new Customer("repository-test@example.invalid"));

        entityManager.flush();
        entityManager.clear();

        assertThat(saved.getId()).isNotNull();

        assertThat(customers.findByEmail(
                "repository-test@example.invalid"))
                .hasValueSatisfying(customer ->
                        assertThat(customer.getId())
                                .isEqualTo(saved.getId()));

        assertThat(context.getBean(CustomerRepository.class))
                .isSameAs(customers);
    }

    @Test
    void genericBaseHasNoStandaloneBean() {
        assertThat(context.containsBean("baseRepository"))
                .isFalse();
    }
}
```

Ví dụ giả định:

- Profile repository-test dùng database kiểm thử riêng.
- Customer và repository được scan đúng.
- Email fixture chưa tồn tại theo cơ chế cô lập dữ liệu của test.
- Tên bean mặc định của BaseRepository, nếu được tạo, là baseRepository.
- Không có bean ứng dụng không liên quan được đặt cùng tên.

Nếu dự án có bean name generator tùy biến, assertion về tên phải theo cấu hình đó. Không sao chép một tên bean giả định sang mọi dự án.

Test truy vấn xác nhận repository con vẫn hoạt động sau khi loại base interface khỏi đích tạo bean. Assertion âm về base bean bổ sung cho việc kiểm tra context, không thay thế nó.

Không viết assertion rằng mọi bean gán được vào BaseRepository đều không tồn tại: repository con hợp lệ có thể nằm trong tập đó.

### Kiểm tra tình huống lỗi trong fixture riêng

Nếu cần minh họa hồi quy trước và sau sửa, có thể tạo hai cấu hình kiểm thử được cô lập:

- Một cấu hình phát hiện interface cơ sở chưa đánh dấu.
- Một cấu hình với interface cơ sở đã đánh dấu và domain hợp lệ.

Không đặt fixture lỗi trong phạm vi scan chung của các test khác, vì nó có thể làm mọi context thất bại.

Assertion lỗi nên tập trung vào candidate và nguyên nhân liên quan. Không phụ thuộc toàn bộ stack trace hoặc một thông báo provider duy nhất nếu mục tiêu là kiểm tra vai trò của base interface.

## 16. Các cách sửa sai thường gặp

| Cách làm | Vì sao không giải quyết đúng vấn đề? |
|---|---|
| Gắn Entity lên Object hoặc kiểu generic | Không biến hợp đồng cơ sở thành domain cụ thể hợp lệ |
| Gắn NoRepositoryBean lên repository cần inject | Có thể làm thiếu bean thật |
| Thêm Repository lên base interface | Không khai báo rằng base không được tạo độc lập |
| Dùng raw type ở repository con | Làm mất thông tin domain và ID |
| Loại toàn bộ subtype của BaseRepository khỏi scan | Có thể loại cả repository cụ thể |
| Đổi sang lazy để ứng dụng khởi động | Có thể chỉ dời lỗi tới lần dùng đầu |
| Bỏ query method gây lỗi mà không hiểu routing | Có thể làm mất chức năng và chưa sửa cấu trúc repository |
| Chỉ kiểm tra bằng mock | Không chạy factory và scan thực |
| Kỳ vọng NoRepositoryBean tự thực hiện softDelete | Annotation không cung cấp implementation tùy biến |
| Đổi cấu hình entity scan dù bean lỗi là generic base | Có thể không đúng nguyên nhân |

Cách sửa nên khớp với bằng chứng: interface cơ sở bị tạo độc lập thì đánh dấu đúng interface đó; domain cụ thể chưa được quản lý thì sửa mapping; method chưa có implementation thì sửa đường thực thi method.

## 17. Quy trình xử lý một sự cố thực tế

Có thể thực hiện theo thứ tự:

1. Xác định thời điểm lỗi: context refresh, repository initialization hay lần dùng đầu.
2. Tìm repository candidate đầu tiên thất bại.
3. Đọc domain type và method liên quan trong chuỗi cause.
4. Vẽ ngắn hierarchy của repository.
5. Đánh dấu interface nào chỉ để dùng lại hợp đồng.
6. Kiểm tra NoRepositoryBean trên các interface đó.
7. Xác nhận repository cụ thể giữ generic đầy đủ.
8. Kiểm tra riêng mapping và custom method nếu còn lỗi.
9. Khởi tạo context kiểm thử với cấu hình store thật.
10. Xác nhận repository cần dùng vẫn có bean và truy vấn được.

Nếu thay đổi bootstrap hoặc scan làm lỗi không còn xuất hiện, vẫn cần xác minh repository có thực sự được tạo và sử dụng. “Không còn thấy lỗi” chưa đủ nếu chức năng đã vô tình bị loại khỏi cấu hình.

## 18. Bài thực hành

Với một dự án kiểm thử có store được cấu hình:

1. Tạo BaseRepository<T, ID> kế thừa CrudRepository.
2. Tạo hai repository cụ thể gắn với hai domain type.
3. Xác định interface nào cần NoRepositoryBean.
4. Quan sát candidate và cause khi base interface chưa được đánh dấu trong cấu hình tái hiện lỗi.
5. Thêm annotation đúng chỗ và xác nhận hai repository con vẫn hoạt động.
6. Tạo một tầng generic trung gian và biểu đạt rõ vai trò cơ sở của nó.
7. Thử một khai báo raw type trong fixture riêng và phân biệt lỗi generic.
8. Thêm một method tùy biến chưa có implementation rồi phân biệt lỗi query creation.
9. Viết kiểm thử context cùng một thao tác lưu và đọc trên repository cụ thể.
10. Giải thích vì sao bean repository con vẫn gán được vào kiểu interface cơ sở.

Các bước tái hiện lỗi phải được cô lập khỏi cấu hình dùng cho hoạt động bình thường. Mục tiêu là hiểu đường tạo repository, không chỉ ghi nhớ một annotation.

## 19. Những điều cần nắm vững

NoRepositoryBean biểu đạt rằng một repository interface không phải đích tạo repository bean độc lập. Đây là khai báo quan trọng đối với các tầng cơ sở generic được dùng để chia sẻ hợp đồng.

Annotation giữ nguyên khả năng kế thừa của repository con, nhưng không sửa generic sai, entity mapping sai, method tùy biến thiếu implementation hoặc cấu hình nhiều store chưa rõ.

Khi chẩn đoán, hãy bắt đầu từ repository candidate và domain type thực sự gây lỗi. Sau khi sửa, xác nhận cả việc base interface không có bean riêng lẫn việc repository cụ thể vẫn hoạt động với store được cấu hình.
