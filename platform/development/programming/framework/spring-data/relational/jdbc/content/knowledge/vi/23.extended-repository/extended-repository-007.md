# Tùy chỉnh lớp repository cơ sở khi có nhu cầu dùng chung trong Spring Data JDBC

## 1. Vì sao cần một lớp repository cơ sở tùy chỉnh?

Spring Data JDBC tạo implementation cho các repository interface dựa trên một lớp cơ sở mặc định. Lớp này cung cấp những thao tác CRUD như tìm theo ID, lưu aggregate, đếm và xóa. Khi nhiều repository trong ứng dụng cần cùng một hành vi bổ sung, việc lặp lại code ở từng repository sẽ làm tăng chi phí bảo trì.

Ví dụ, nhiều repository có thể cần:

- Một method lấy entity theo ID và ném exception rõ ràng nếu không tồn tại.
- Một quy ước xử lý hoặc ghi nhận thao tác dùng chung.
- Một method tiện ích có thể áp dụng cho mọi aggregate root.
- Một phần mở rộng thống nhất cho API repository của dự án.

Spring Data cho phép thay lớp implementation cơ sở bằng một lớp do ứng dụng cung cấp. Với Spring Data JDBC, cách thường dùng là kế thừa `SimpleJdbcRepository` rồi cấu hình `repositoryBaseClass` trong `@EnableJdbcRepositories`.

Đây là thay đổi ở **tầng repository infrastructure**. Lớp cơ sở mới được dùng làm implementation nền cho các repository thuộc phạm vi cấu hình đó. Vì vậy, chỉ nên đặt ở đây hành vi thật sự dùng chung và có ý nghĩa với nhiều aggregate.

## 2. Phân biệt base repository interface và base repository class

Hai thành phần thường được sử dụng cùng nhau nhưng có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| Base repository interface | Khai báo contract dùng chung mà repository cụ thể sẽ kế thừa |
| Base repository class | Cung cấp implementation cho các method dùng chung |
| Concrete repository | Repository dành cho một aggregate root cụ thể |
| Repository factory | Tạo proxy repository và gắn implementation cơ sở cùng các thành phần mở rộng |

Ví dụ, ứng dụng muốn mọi repository có method `getRequiredById(id)`. Interface khai báo method; implementation cơ sở cung cấp code; các repository cụ thể kế thừa interface đó.

~~~text
BaseRepository<T, ID>
        │
        ├── CustomerRepository
        ├── OrderRepository
        └── ProductRepository

BaseRepositoryImpl<T, ID>
        │
        └── SimpleJdbcRepository<T, ID>
~~~

Không nên nhầm base repository class với một abstract class domain chứa logic nghiệp vụ. Base class này thuộc tầng persistence và cần giữ đúng contract của Spring Data repository.

## 3. Tạo base repository interface với @NoRepositoryBean

Bắt đầu bằng interface generic:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    T getRequiredById(ID id);
}
~~~

`T` đại diện cho kiểu aggregate root; `ID` là kiểu identifier. Interface kế thừa `CrudRepository` nên các repository cụ thể vẫn có những method CRUD chuẩn.

### 3.1. Vì sao cần @NoRepositoryBean?

`@NoRepositoryBean` báo cho Spring Data rằng interface generic này là một base contract, không phải repository độc lập cần tạo proxy.

Nếu bỏ annotation, repository scanning có thể cố tạo repository cho interface generic mà chưa có kiểu domain cụ thể. Điều đó thường không có ý nghĩa vì `T` và `ID` chỉ được xác định khi một repository cụ thể kế thừa nó.

### 3.2. Repository cụ thể kế thừa base interface

~~~java
public interface CustomerRepository
        extends BaseRepository<Customer, Long> {
}
~~~

Một repository khác cũng có thể dùng chung contract:

~~~java
public interface OrderRepository
        extends BaseRepository<PurchaseOrder, UUID> {
}
~~~

Mỗi repository giữ kiểu domain và ID riêng. Method `getRequiredById` được kế thừa mà không cần khai báo lại.

Lưu ý: repository Spring Data JDBC thường đại diện cho **aggregate root**. Base repository generic nên được thiết kế quanh aggregate root, không phải một cách để tạo repository cho mọi object con nằm trong aggregate.

## 4. Viết implementation cơ sở bằng SimpleJdbcRepository

Spring Data JDBC cung cấp `SimpleJdbcRepository` làm implementation CRUD mặc định. Kế thừa lớp này giúp giữ các thao tác persistence mà framework đã triển khai, sau đó bổ sung method dùng chung.

~~~java
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.data.jdbc.repository.support.SimpleJdbcRepository;
import org.springframework.data.relational.repository.support.RelationalEntityInformation;
import org.springframework.transaction.annotation.Transactional;

public class BaseRepositoryImpl<T, ID>
        extends SimpleJdbcRepository<T, ID>
        implements BaseRepository<T, ID> {

    public BaseRepositoryImpl(
            JdbcAggregateOperations entityOperations,
            RelationalEntityInformation<T, ID> entityInformation
    ) {
        super(entityOperations, entityInformation);
    }

    @Override
    @Transactional(readOnly = true)
    public T getRequiredById(ID id) {
        return findById(id)
                .orElseThrow(() -> new EmptyResultDataAccessException(1));
    }
}
~~~

Method `getRequiredById` dùng lại `findById` có sẵn. Nếu có kết quả, trả về entity; nếu không có, ném `EmptyResultDataAccessException`. Quy tắc này được triển khai một lần và có thể dùng từ mọi repository kế thừa `BaseRepository`.

Constructor nhận các thành phần do repository factory cung cấp:

- `JdbcAggregateOperations` là abstraction thao tác với aggregate của Spring Data JDBC.
- `RelationalEntityInformation<T, ID>` chứa metadata của entity như kiểu domain và thông tin identifier.
- `super(...)` chuyển các dependency cần thiết cho `SimpleJdbcRepository` để các thao tác CRUD chuẩn tiếp tục hoạt động.

Tên package và constructor cần khớp phiên bản Spring Data JDBC trong dự án. Hãy dùng API của đúng phiên bản dependency khi triển khai.

### 4.1. Vì sao kế thừa SimpleJdbcRepository?

Nếu tự triển khai toàn bộ `CrudRepository`, ứng dụng phải tự xử lý nhiều chi tiết persistence như:

- Phát hiện entity mới và lựa chọn INSERT/UPDATE.
- Ánh xạ ID do database sinh.
- Mapping cột và kiểu dữ liệu.
- Lưu aggregate root cùng các thành phần con.
- Optimistic locking khi entity sử dụng `@Version`.
- Các quy tắc transaction và hành vi CRUD của Spring Data JDBC.

Kế thừa implementation mặc định giúp giữ lại những hành vi đó. Lớp tùy chỉnh chỉ bổ sung hoặc điều chỉnh phần thật sự cần thiết.

Không nên tự viết lại các method CRUD chỉ để thêm một tiện ích nhỏ. Nếu method mới có thể dùng method có sẵn, hãy tận dụng chúng trước.

## 5. Đăng ký lớp cơ sở qua @EnableJdbcRepositories

Sau khi có implementation, cấu hình repository scanning để Spring Data JDBC sử dụng lớp mới:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
        basePackages = "com.example.persistence",
        repositoryBaseClass = BaseRepositoryImpl.class
)
public class JdbcRepositoryConfiguration {
}
~~~

Thuộc tính `repositoryBaseClass` chỉ định implementation nền cho các repository được tạo trong phạm vi cấu hình này.

### 5.1. Phạm vi ảnh hưởng

Nếu `basePackages` là `com.example.persistence`, các repository được scan trong package đó sẽ dùng base class đã chỉ định, miễn là chúng tương thích với base interface và kiểu generic.

Nếu ứng dụng có nhiều vùng repository với cấu hình `@EnableJdbcRepositories` riêng, hãy quyết định rõ vùng nào cần dùng base class tùy chỉnh. Không giả định một cấu hình tự động áp dụng cho mọi repository ở mọi module.

Trong ứng dụng Spring Boot, hãy tích hợp thuộc tính này vào cấu hình repository scanning hiện có. Tránh khai báo thêm một cấu hình scan trùng package mà không kiểm tra vì có thể tạo xung đột hoặc làm thay đổi phạm vi auto-configuration.

### 5.2. Không cần tự tạo instance implementation

Repository factory của Spring Data tạo implementation và proxy dựa trên metadata cùng dependency của store. Thông thường không tự gọi constructor của `BaseRepositoryImpl` bằng tay và cũng không cần đăng ký một bean riêng cho từng entity.

Điều quan trọng là constructor có các dependency mà factory cần cung cấp, và implementation có thể được dùng làm base class cho các kiểu repository được scan.

## 6. Luồng hoạt động khi gọi method dùng chung

Với cấu hình trên, khi ứng dụng gọi:

~~~java
Customer customer = customerRepository.getRequiredById(customerId);
~~~

luồng khái quát:

~~~mermaid
flowchart TD
    A["CustomerRepository proxy"] --> B["BaseRepositoryImpl.getRequiredById"]
    B --> C["SimpleJdbcRepository.findById"]
    C --> D["Spring Data JDBC aggregate operations"]
    D --> E["Database"]
    E --> F{"Có bản ghi?"}
    F -->|Có| G["Trả Customer"]
    F -->|Không| H["EmptyResultDataAccessException"]
~~~

Method tùy chỉnh nằm trong implementation cơ sở. Nó gọi lại method CRUD kế thừa từ `SimpleJdbcRepository`, do đó không cần tự viết SQL cho thao tác tìm theo ID.

Với repository khác như `OrderRepository`, cùng method được thực thi trên kiểu aggregate root tương ứng nhờ metadata mà repository factory cung cấp.

## 7. Thêm nhiều hành vi dùng chung

Base repository có thể khai báo thêm những method thực sự phù hợp với mọi aggregate. Ví dụ, một helper lấy entity hoặc trả về kết quả optional đã tồn tại sẵn dưới dạng `findById`, nên không cần tạo một alias trùng chức năng. Thay vào đó, chỉ thêm API khi nó biểu đạt một contract có giá trị rõ ràng.

Các nhóm hành vi có thể cân nhắc:

- **Convenience method:** cách gọi thống nhất cho thao tác thường gặp, ví dụ lấy entity bắt buộc phải tồn tại.
- **Persistence policy chung:** quy tắc kỹ thuật áp dụng cho tất cả aggregate, nếu không làm sai lệch semantics riêng của từng domain.
- **Instrumentation:** ghi nhận metric hoặc thời gian thực thi ở một điểm chung, khi cơ chế đo lường hiện tại chưa đáp ứng.
- **API dùng chung:** method generic thao tác qua metadata domain/ID mà mọi repository đều có thể thực hiện đúng.

Ví dụ một contract khác có thể là method trả về boolean khi kiểm tra tồn tại, nhưng `CrudRepository` đã có `existsById`. Không nên tạo thêm method chỉ đổi tên API chuẩn.

### 7.1. Hành vi nào không nên đặt ở base class?

Không phải mọi logic được dùng ở nhiều nơi đều thuộc repository base class. Tránh đưa vào đây:

- Quy tắc nghiệp vụ chỉ áp dụng cho một số aggregate.
- Kiểm tra quyền phụ thuộc user hoặc tenant cụ thể mà không có context rõ ràng.
- Quy trình gọi nhiều repository hoặc nhiều service.
- Gửi email, gọi HTTP hoặc phát side effect bên ngoài database.
- Quy tắc workflow như duyệt đơn, khóa tài khoản hoặc tính giá.

Các hành vi trên thường thuộc service/domain layer. Base repository nên tập trung vào persistence abstraction và các tiện ích dùng chung ở tầng này.

## 8. Override method CRUD khi thật sự cần

Có thể override một method kế thừa để bổ sung hành vi chung, nhưng đây là thay đổi có phạm vi rộng vì mọi repository trong vùng cấu hình đều có thể bị ảnh hưởng.

Ví dụ khung override:

~~~java
@Override
public <S extends T> S save(S entity) {
    // Chỉ đặt logic kỹ thuật thật sự dùng chung tại đây.
    return super.save(entity);
}
~~~

Đoạn code minh họa vị trí override; nó chưa thêm hành vi cụ thể. Khi triển khai thực tế, cần xác định rõ hành vi trước/sau khi lưu và xử lý exception.

Khi override CRUD, cần giữ các contract sau:

1. Trả đúng kiểu entity đã lưu, đặc biệt với ID sinh tự động và entity bất biến.
2. Không bỏ qua optimistic locking hoặc làm sai cách xử lý `@Version`.
3. Không thay đổi cách lưu aggregate root và child ngoài chủ đích.
4. Không nuốt exception persistence khiến caller tưởng thao tác thành công.
5. Giữ transaction semantics hoặc khai báo transaction rõ ràng.
6. Không tạo side effect lặp lại ngoài ý muốn khi framework gọi thao tác nhiều lần.

### 8.1. Không thay save bằng JDBC UPDATE tùy tiện

Một override `save` viết SQL trực tiếp có thể bỏ qua entity state detection, generated ID, aggregate mapping, custom conversion và optimistic locking. Nếu muốn thay đổi cách lưu, phải hiểu đầy đủ contract của repository và kiểm thử các trường hợp INSERT, UPDATE, entity bất biến, version và child collection.

Trong phần lớn trường hợp, gọi `super.save(entity)` là cách giữ lại persistence behavior chuẩn. Chỉ thay thế hoàn toàn khi có lý do kỹ thuật rõ ràng và một thiết kế persistence đã được kiểm chứng.

### 8.2. Không biến base class thành nơi áp dụng quy tắc riêng cho một entity

Ví dụ chỉ `Customer` có quy tắc chuẩn hóa mã khách hàng, trong khi `Order` và `Product` không có. Đặt quy tắc này trong `BaseRepositoryImpl<T, ID>` sẽ khiến base class phải kiểm tra kiểu domain hoặc ép mọi entity tuân theo một giả định riêng.

Hãy đặt quy tắc chuẩn hóa ở domain/service hoặc custom repository fragment của `CustomerRepository`. Base class chỉ nên chứa hành vi có ý nghĩa đồng nhất với mọi kiểu `T` trong phạm vi áp dụng.

## 9. Transaction cho method tùy chỉnh

Các CRUD method kế thừa có transaction behavior do Spring Data repository cung cấp. Với method mới trong base implementation, hãy khai báo transaction theo nhu cầu của method.

Ví dụ method chỉ đọc:

~~~java
@Override
@Transactional(readOnly = true)
public T getRequiredById(ID id) {
    return findById(id)
            .orElseThrow(() -> new EmptyResultDataAccessException(1));
}
~~~

Với method thay đổi dữ liệu, có thể dùng `@Transactional` mà không đặt `readOnly = true`. Nếu một nghiệp vụ gồm nhiều repository, thường nên đặt transaction ở service để transaction boundary bao phủ toàn bộ use case.

Lưu ý:

- `@Transactional` hoạt động qua Spring proxy trong cấu hình proxy thông thường.
- Tự gọi một method khác trên cùng instance bằng `this` không đi qua proxy như một lời gọi từ bean bên ngoài; không dựa vào self-invocation để mở transaction mới.
- Nếu bắt exception rồi không ném lại, transaction có thể không rollback theo mong muốn.
- Mặc định Spring rollback với `RuntimeException` và `Error`; checked exception cần cấu hình rollback phù hợp nếu nghiệp vụ yêu cầu.

Một method repository cơ sở không nên tự mở transaction riêng cho từng thao tác nhỏ nếu nó phải tham gia transaction đang được service quản lý. Hãy để propagation mặc định phù hợp hoặc cấu hình rõ ràng khi có yêu cầu đặc biệt.

## 10. Khi nên dùng custom repository fragment thay vì base class?

Base class là lựa chọn mạnh và có phạm vi ảnh hưởng rộng. Nếu chỉ một hoặc vài repository cần tính năng riêng, **custom repository fragment** thường phù hợp hơn.

Ví dụ, chỉ cần tìm khách hàng theo bộ lọc tùy chỉnh:

~~~java
public interface CustomerSearchRepository {
    List<Customer> search(CustomerSearchFilter filter);
}
~~~

Implementation:

~~~java
@Repository
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public CustomerSearchRepositoryImpl(
            NamedParameterJdbcTemplate jdbc
    ) {
        this.jdbc = jdbc;
    }

    @Override
    public List<Customer> search(CustomerSearchFilter filter) {
        // Xây dựng và thực thi truy vấn dành riêng cho Customer.
        return List.of();
    }
}
~~~

Repository cụ thể kết hợp fragment:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

So sánh:

| Nhu cầu | Cách phù hợp |
|---|---|
| Một method tiện ích dùng cho hầu hết repository | Base repository interface + base class |
| Thay đổi hành vi nền của repository trong một vùng scan | Custom base class |
| Chỉ một aggregate cần truy vấn đặc biệt | Custom repository fragment |
| Chỉ cần tổ hợp vài method repository có sẵn | Default method hoặc service |
| Nghiệp vụ phối hợp nhiều repository | Service layer |
| SQL riêng cho một bảng hoặc use case | Fragment hoặc DAO dùng JDBC template |

Fragment có thể được ghép vào đúng repository cần nó. Nhờ đó, repository khác không phải mang thêm method hoặc phụ thuộc không liên quan.

## 11. Default method trên repository interface

Nếu method chỉ kết hợp các method repository đã có, Java interface default method có thể đủ:

~~~java
public interface CustomerRepository
        extends BaseRepository<Customer, Long> {

    Optional<Customer> findByCustomerCode(String code);

    default Customer getByCodeOrThrow(String code) {
        return findByCustomerCode(code)
                .orElseThrow(() -> new CustomerNotFoundException(code));
    }
}
~~~

Default method phù hợp với logic ngắn gọn, gắn với một repository cụ thể. Nếu hành vi cần được chia sẻ cho nhiều repository, base interface có thể khai báo contract chung. Nếu cần truy cập sâu vào persistence infrastructure hoặc override CRUD, base implementation class phù hợp hơn.

Nếu logic có nhiều bước nghiệp vụ, phụ thuộc nhiều service hoặc cần transaction orchestration, hãy chuyển lên service thay vì nhồi vào interface.

## 12. Kiểm thử custom base repository

Khi đã thay đổi implementation dùng chung, lỗi có thể ảnh hưởng nhiều repository cùng lúc. Nên kiểm thử ở mức integration với database phù hợp để xác nhận repository factory và mapping hoạt động như mong đợi.

Các trường hợp nên có:

| Trường hợp | Điều cần xác nhận |
|---|---|
| Repository cụ thể kế thừa base interface | Spring tạo proxy thành công |
| Entity tồn tại | `getRequiredById` trả đúng aggregate |
| ID không tồn tại | Method ném exception theo contract |
| Nhiều kiểu ID khác nhau | Generic base class hoạt động với các ID type |
| INSERT entity mới | CRUD mặc định vẫn tạo và trả ID đúng |
| UPDATE entity đã tồn tại | CRUD mặc định vẫn cập nhật đúng |
| Entity có `@Version` | Optimistic locking vẫn hoạt động |
| Aggregate có child collection | Quan hệ child vẫn được lưu/xóa theo mapping |
| Repository ngoài package scan | Không bị thay implementation ngoài dự kiến |
| Method có transaction | Rollback/commit đúng với transaction boundary |

Ví dụ integration test ở mức khái niệm:

~~~java
@DataJdbcTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void returnsCustomerWhenIdExists() {
        Customer saved = customers.save(
                new Customer("C-001", "An")
        );

        Customer loaded = customers.getRequiredById(saved.getId());

        assertThat(loaded.getCustomerCode()).isEqualTo("C-001");
    }

    @Test
    void throwsWhenIdDoesNotExist() {
        assertThatThrownBy(() -> customers.getRequiredById(999L))
                .isInstanceOf(EmptyResultDataAccessException.class);
    }
}
~~~

Đây là ví dụ minh họa; constructor và factory method của entity phải khớp model thực tế. Nếu dự án dùng database cụ thể, nên chạy integration test trên cùng loại database hoặc Testcontainers để xác nhận dialect, constraint và transaction behavior.

## 13. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Spring cố tạo repository cho interface generic | Thiếu `@NoRepositoryBean` | Đánh dấu base interface |
| Method custom không xuất hiện trên repository cụ thể | Repository không kế thừa base interface | Cho repository cụ thể extends base contract |
| Custom implementation không được dùng | Chưa cấu hình `repositoryBaseClass` hoặc sai package scan | Kiểm tra `@EnableJdbcRepositories` |
| Repository không khởi tạo được | Constructor không khớp dependency factory hoặc sai API version | Kiểm tra constructor và Spring Data JDBC version |
| CRUD mặc định hỏng sau khi tùy chỉnh | Tự triển khai hoặc override sai persistence behavior | Kế thừa `SimpleJdbcRepository` và giữ contract |
| Method custom không có transaction như mong muốn | Chưa khai báo transaction hoặc gọi qua self-invocation | Đặt `@Transactional` và gọi qua proxy |
| Mọi repository đều nhận logic không phù hợp | Base class chứa quy tắc riêng cho một domain | Chuyển logic sang fragment/service |
| SQL trực tiếp bỏ qua child collection | Nhầm direct SQL với aggregate persistence | Dùng aggregate operations hoặc xử lý child/FK tường minh |
| Entity bất biến không nhận ID mới | Bỏ qua entity trả về từ save | Sử dụng instance mà `save` trả về |
| Override save làm mất optimistic locking | Bỏ qua version và persistence delegate | Giữ `super.save` hoặc triển khai đầy đủ contract |
| Repository ở module khác cũng bị ảnh hưởng | Phạm vi scan rộng hơn dự kiến | Thu hẹp basePackages và kiểm tra cấu hình |
| Có hai cấu hình repository scan xung đột | Khai báo nhiều cấu hình cho cùng package | Hợp nhất hoặc phân vùng package rõ ràng |

## 14. Quy trình triển khai

1. Xác định hành vi thật sự dùng chung và lý do cần đặt ở tầng repository.
2. Tạo generic base interface kế thừa repository interface phù hợp.
3. Thêm `@NoRepositoryBean` để Spring không khởi tạo interface generic.
4. Tạo implementation generic kế thừa `SimpleJdbcRepository`.
5. Khai báo constructor nhận dependency/metadata cần thiết và gọi constructor lớp cha.
6. Implement các method chung dựa trên API persistence hiện có.
7. Cho repository cụ thể kế thừa base interface.
8. Cấu hình `repositoryBaseClass` trong `@EnableJdbcRepositories` hiện có.
9. Kiểm thử repository factory, CRUD, ID, version, child mapping và transaction.
10. Xác nhận phạm vi package scan để tránh tác động ngoài dự kiến.

## 15. Bài tập thực hành

### Bài 1 — Base interface

Tạo `BaseRepository<T, ID>` kế thừa `CrudRepository<T, ID>`. Thêm `getRequiredById` và đánh dấu `@NoRepositoryBean`.

### Bài 2 — Base implementation

Tạo `BaseRepositoryImpl<T, ID>` kế thừa `SimpleJdbcRepository`. Implement `getRequiredById` bằng `findById` và exception khi không tìm thấy.

### Bài 3 — Cấu hình repository factory

Cấu hình `@EnableJdbcRepositories(repositoryBaseClass = BaseRepositoryImpl.class)`. Cho `CustomerRepository` và `OrderRepository` kế thừa base interface, sau đó gọi method chung từ cả hai.

### Bài 4 — Kiểm tra CRUD mặc định

Sau khi thay base class, thử INSERT, UPDATE, findById, deleteById và saveAll. Xác nhận ID sinh tự động vẫn được trả về và các aggregate có child vẫn được lưu đúng.

### Bài 5 — Transaction

Đánh dấu một method custom là read-only và một method ghi dữ liệu là transactional. Kiểm tra method được gọi qua repository proxy và thử tình huống exception.

### Bài 6 — So sánh với fragment

Tạo một method tìm kiếm chỉ dành cho Customer bằng custom repository fragment. So sánh phạm vi ảnh hưởng với việc đưa method đó vào base repository.

### Bài 7 — Override save có kiểm soát

Tạo một override chỉ bổ sung instrumentation rồi gọi `super.save`. Kiểm tra entity mutable, immutable, generated ID và `@Version` để xác nhận contract không thay đổi.

## 16. Ghi nhớ

- Custom base repository class dùng khi nhiều repository cần chung một hành vi ở tầng persistence.
- Base interface khai báo method; base class triển khai method; concrete repository kế thừa contract chung.
- Đánh dấu generic base interface bằng `@NoRepositoryBean` để Spring Data không tạo repository độc lập cho nó.
- Với Spring Data JDBC, có thể kế thừa `SimpleJdbcRepository<T, ID>` để giữ CRUD implementation mặc định.
- Cấu hình `repositoryBaseClass` trong `@EnableJdbcRepositories` để repository factory sử dụng implementation tùy chỉnh.
- Chỉ method được khai báo trên interface repository mới được gọi qua kiểu repository proxy; thêm method chỉ vào class implementation là chưa đủ.
- Method custom cần transaction semantics rõ ràng; không mặc định mọi method mới đều có cùng cấu hình như CRUD method kế thừa.
- Khi override CRUD, giữ generated ID, immutable entity, aggregate mapping, optimistic locking và exception contract.
- Nếu tính năng chỉ dành cho một số repository, custom fragment thường có phạm vi phù hợp hơn.
- Quy tắc nghiệp vụ và orchestration nhiều repository nên nằm ở service/domain layer, không nên đưa tất cả vào base class.
