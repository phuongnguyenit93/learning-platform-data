# Repository, CrudRepository và hợp đồng thao tác dữ liệu

## Mục tiêu

Repository là hợp đồng truy cập dữ liệu mà Spring Data cung cấp. Với Spring Data JPA, ứng dụng khai báo một interface dựa trên entity và kiểu khóa chính; Spring Data tạo implementation ở runtime, nối các lời gọi repository với JPA và Hibernate.

Bài này tập trung vào `Repository<T, ID>`, `CrudRepository<T, ID>` và cách thiết kế hợp đồng truy cập dữ liệu. Sau khi hoàn thành, bạn có thể:

- Phân biệt marker repository với các hợp đồng CRUD, phân trang và JPA.
- Chọn đúng interface nền cho một repository.
- Hiểu ý nghĩa, kiểu trả về và giới hạn của các thao tác trong `CrudRepository`.
- Khai báo truy vấn theo tên phương thức hoặc bằng `@Query`.
- Sử dụng repository trong service với transaction phù hợp.
- Kiểm thử repository và tránh những lỗi phổ biến.

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Data JPA và PostgreSQL. Các đoạn mã được đặt trong một dự án Spring Boot đã có dependency `spring-boot-starter-data-jpa` và cấu hình DataSource hợp lệ.

## 1. Repository là gì?

Trong kiến trúc ứng dụng, repository đại diện cho nơi truy cập và lưu trữ dữ liệu. Service gọi các phương thức có ý nghĩa như `findById`, `save` hoặc `findByEmail`, thay vì tự quản lý kết nối JDBC, câu SQL và vòng đời EntityManager trong từng nghiệp vụ.

Spring Data định nghĩa interface gốc:

```java
package org.springframework.data.repository;

public interface Repository<T, ID> {
}
```

Đây là một marker interface: bản thân nó không khai báo phương thức CRUD. Hai tham số generic có ý nghĩa:

- `T`: kiểu domain object/entity mà repository quản lý, ví dụ `Customer`.
- `ID`: kiểu định danh của entity, ví dụ `Long`, `UUID` hoặc `String`.

Khi khai báo:

```java
public interface CustomerRepository
        extends Repository<Customer, Long> {
}
```

ta đã đánh dấu `CustomerRepository` là repository Spring Data quản lý. Tuy nhiên, interface này chưa có phương thức truy cập dữ liệu. Ta có thể tự khai báo phương thức truy vấn hoặc kế thừa một hợp đồng cụ thể như `CrudRepository`.

Spring Data tìm các repository interface trong package được cấu hình, thường là package chứa class `@SpringBootApplication` và các package con. Framework tạo proxy implementation khi ứng dụng khởi động. Vì vậy, ứng dụng thông thường chỉ cần khai báo interface, không cần tự viết class triển khai từng phương thức CRUD.

Trong Spring Boot, auto-configuration thường tự tìm repository. Với cấu hình đặc biệt hoặc package nằm ngoài vùng quét mặc định, có thể dùng `@EnableJpaRepositories` để chỉ rõ package repository.

### Hợp đồng và implementation

Một hợp đồng mô tả phương thức được phép gọi, tham số đầu vào, kiểu kết quả và ý nghĩa của thao tác. Repository giúp service phụ thuộc vào API truy cập dữ liệu thay vì chi tiết triển khai.

Ví dụ, `CrudRepository` cam kết cung cấp các thao tác CRUD cơ bản. Spring Data JPA triển khai hợp đồng đó bằng JPA. Nếu dùng một module Spring Data khác, implementation có thể dựa trên công nghệ lưu trữ khác, trong khi phần lớn mã gọi repository vẫn giữ nguyên.

Một repository interface không phải class chứa logic truy vấn được viết thủ công. Khi ứng dụng chạy, Spring Data tạo proxy cho interface và ủy quyền các phương thức đã biết tới implementation phù hợp. Các query method do lập trình viên khai báo được phân tích hoặc liên kết với query đã định nghĩa.

## 2. Các interface repository thường gặp

Spring Data có nhiều hợp đồng với mức chức năng khác nhau. Những interface thường dùng trong Spring Data Commons và Spring Data JPA gồm:

| Interface | Vai trò |
|---|---|
| `Repository<T, ID>` | Marker interface gốc, chưa cung cấp CRUD |
| `CrudRepository<T, ID>` | Các thao tác tạo, đọc, cập nhật và xóa cơ bản |
| `ListCrudRepository<T, ID>` | Biến thể CRUD trả về `List` cho các thao tác danh sách |
| `PagingAndSortingRepository<T, ID>` | Truy vấn danh sách có sắp xếp hoặc phân trang |
| `ListPagingAndSortingRepository<T, ID>` | Biến thể phân trang/sắp xếp trả về `List` |
| `JpaRepository<T, ID>` | Hợp đồng mở rộng dành cho JPA, có CRUD, phân trang/sắp xếp và thao tác JPA bổ sung |
| `QueryByExampleExecutor<T>` | Thực thi truy vấn theo Example object |

### Lưu ý về hệ phân cấp từ Spring Data 3.x

Từ Spring Data 3.0, các hợp đồng CRUD và phân trang được tách rõ hơn. `PagingAndSortingRepository` kế thừa trực tiếp `Repository`, không còn kế thừa `CrudRepository` như trong các phiên bản Spring Data cũ.

Do đó, nếu một repository cần cả CRUD và phân trang/sắp xếp trong Spring Data 3.x, hãy kế thừa cả hai hợp đồng hoặc dùng `JpaRepository` khi làm việc với JPA. Ví dụ:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                PagingAndSortingRepository<Customer, Long> {
}
```

Với Spring Data JPA, lựa chọn phổ biến là:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

`JpaRepository` cung cấp API CRUD dạng danh sách, phân trang/sắp xếp và chức năng riêng của JPA. Nó cũng hỗ trợ các phương thức như `flush`, `saveAndFlush`, xóa theo batch và lấy reference tới entity. Chỉ sử dụng các API này khi nghiệp vụ thực sự cần.

Ở Spring Data 2.x, quan hệ kế thừa giữa `PagingAndSortingRepository` và `CrudRepository` khác với 3.x. Khi đọc tài liệu hoặc code cũ, hãy đối chiếu version Spring Data thực tế của dự án. Không suy ra interface nào có sẵn phương thức chỉ từ ví dụ của một version khác.

### Khi nào nên dùng interface nào?

- Dùng `Repository` khi muốn tự thiết kế một hợp đồng rất nhỏ, chỉ công khai các phương thức cần thiết.
- Dùng `CrudRepository` khi cần CRUD cơ bản và không cần API trả về `List` cho các thao tác danh sách.
- Dùng `PagingAndSortingRepository` khi cần phân trang/sắp xếp; với Spring Data 3.x, kết hợp thêm `CrudRepository` nếu cũng cần CRUD.
- Dùng `JpaRepository` cho phần lớn repository JPA thông thường. Đây là lựa chọn thuận tiện khi cần CRUD, phân trang và API JPA.
- Dùng interface trung gian khi nhiều repository cần chung một tập phương thức.

Một interface trung gian chỉ dùng làm cha cho các repository khác có thể được đánh dấu `@NoRepositoryBean` để Spring Data không cố tạo repository instance trực tiếp cho nó:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {

    boolean existsByIdAndArchivedFalse(ID id);
}
```

Repository cụ thể kế thừa `BaseRepository` và cung cấp entity cùng kiểu ID. Chỉ tạo base repository khi có quy tắc chung thực sự; tránh thêm tầng interface không mang lại lợi ích.

## 3. Hợp đồng của CrudRepository

`CrudRepository<T, ID>` khai báo các thao tác cơ bản sau. Đây là các tên và kiểu trả về quan trọng của hợp đồng Spring Data Commons:

| Phương thức | Ý nghĩa | Kiểu trả về |
|---|---|---|
| `save(entity)` | Lưu một entity mới hoặc cập nhật entity | `<S extends T> S` |
| `saveAll(entities)` | Lưu một nhóm entity | `Iterable<S>` |
| `findById(id)` | Tìm theo khóa chính | `Optional<T>` |
| `existsById(id)` | Kiểm tra khóa chính có tồn tại | `boolean` |
| `findAll()` | Lấy tất cả entity | `Iterable<T>` |
| `findAllById(ids)` | Lấy entity theo một tập ID | `Iterable<T>` |
| `count()` | Đếm số entity | `long` |
| `deleteById(id)` | Xóa theo ID | `void` |
| `delete(entity)` | Xóa entity được chỉ định | `void` |
| `deleteAllById(ids)` | Xóa theo nhiều ID | `void` |
| `deleteAll(entities)` | Xóa nhóm entity | `void` |
| `deleteAll()` | Xóa toàn bộ entity | `void` |

Các phương thức có thể chia thành ba nhóm:

### 3.1. Create và Update: save, saveAll

`save` nhận entity và trả về entity đã được lưu. Trong Spring Data JPA, thao tác này thường dùng `EntityManager.persist` khi entity được xác định là mới và `EntityManager.merge` khi entity được xác định là đã tồn tại.

Điểm quan trọng: hãy dùng đối tượng được trả về từ `save`. Với thao tác merge, đối tượng được trả về có thể là instance managed khác với đối tượng đầu vào.

```java
Customer customer = new Customer("linh@example.com", "Linh Nguyen");

Customer saved = customerRepository.save(customer);

Long generatedId = saved.getId();
```

Spring Data JPA xác định entity mới theo chiến lược nhận diện trạng thái new. Thông thường framework kiểm tra trường version không phải kiểu primitive nếu có, sau đó kiểm tra ID. Nếu ID null, entity thường được xem là mới. Với entity dùng ID gán thủ công, việc nhận diện có thể cần điều chỉnh bằng `Persistable` hoặc chiến lược phù hợp; nếu không, entity mới có thể bị xử lý như entity cũ.

`saveAll` nhận một `Iterable` và trả về các entity đã lưu. Đây là API tiện lợi cho thao tác nhiều bản ghi. Không nên mặc định rằng nó luôn thực hiện một câu SQL bulk insert duy nhất; cách thực thi phụ thuộc JPA provider, cấu hình batch, chiến lược sinh ID và database.

### 3.2. Read: findById, findAll, findAllById

`findById` trả về `Optional<T>`, vì vậy kết quả không tồn tại được biểu diễn rõ ràng:

```java
Optional<Customer> result = customerRepository.findById(10L);

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.getEmail());
}
```

Có thể kết hợp với `orElseThrow` khi nghiệp vụ yêu cầu bản ghi phải tồn tại:

```java
Customer customer = customerRepository.findById(10L)
        .orElseThrow(() -> new IllegalArgumentException(
                "Customer not found: 10"
        ));
```

`findAll` và `findAllById` trả về `Iterable` trong `CrudRepository`. `findAllById` chỉ trả về các bản ghi thực sự tồn tại; không nên giả định kết quả có đủ mọi ID đầu vào hoặc giữ nguyên thứ tự ID yêu cầu. Nếu cần thứ tự cụ thể, hãy sắp xếp rõ ràng trong query hoặc ở tầng phù hợp.

Không nên dùng `findAll()` để tải bảng lớn chỉ nhằm hiển thị một trang dữ liệu. Hãy dùng phân trang để giới hạn lượng dữ liệu đọc.

### 3.3. Delete: deleteById, delete, deleteAll

Các phương thức delete thực hiện thao tác xóa theo ID, entity hoặc tập entity. Với hợp đồng CRUD chuẩn, yêu cầu xóa một ID không tồn tại được bỏ qua im lặng.

```java
customerRepository.deleteById(10L);
```

Nếu nghiệp vụ cần phân biệt “không tồn tại” với “đã xóa”, hãy kiểm tra trước bằng `findById` và xử lý rõ ràng ở service. Lưu ý rằng thao tác kiểm tra rồi xóa có thể gặp cạnh tranh đồng thời; constraint và transaction của database vẫn là lớp bảo vệ cuối cùng.

`deleteAll()` xóa toàn bộ dữ liệu của loại entity repository quản lý. Đây là thao tác có phạm vi lớn; chỉ gọi khi nghiệp vụ thực sự yêu cầu và đã xác định rõ tác động.

## 4. Ví dụ khai báo CustomerRepository

Giả sử entity `Customer` có ID kiểu `Long`, email và họ tên. Đoạn mã entity tối giản:

```java
package com.example.demo.customer;

import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {
        // JPA cần constructor không tham số.
    }

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
```

Repository tương ứng:

```java
package com.example.demo.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    boolean existsByEmailIgnoreCase(String email);

    List<Customer> findTop10ByFullNameContainingIgnoreCaseOrderByFullNameAsc(
            String keyword
    );

    Page<Customer> findByEmailContainingIgnoreCase(
            String keyword,
            Pageable pageable
    );
}
```

Spring Data tạo implementation cho `CustomerRepository` khi khởi động. Không cần viết class `CustomerRepositoryImpl` chỉ để triển khai các phương thức trên.

Một vài điểm cần chú ý:

- `Customer` là kiểu entity; `Long` là kiểu ID. Hai kiểu generic phải khớp với entity.
- `findByEmailIgnoreCase` là derived query: Spring Data phân tích tên phương thức để tạo truy vấn.
- `Optional<Customer>` biểu diễn khả năng không tìm thấy email.
- `List<Customer>` trả về danh sách giới hạn 10 bản ghi theo thứ tự tên.
- `Page<Customer>` mang dữ liệu của trang hiện tại cùng thông tin phân trang và tổng số phần tử/trang.

## 5. Derived query: tạo truy vấn từ tên phương thức

Spring Data có thể tạo query từ tên phương thức repository. Cấu trúc phổ biến:

```text
<subject><predicate><By><property><condition><OrderBy><property><Direction>
```

Ví dụ:

| Phương thức | Ý nghĩa |
|---|---|
| `findByEmail(String email)` | Tìm theo email |
| `findByFullName(String name)` | Tìm theo họ tên |
| `findByEmailAndFullName(String email, String name)` | Kết hợp hai điều kiện AND |
| `findByEmailOrFullName(String email, String name)` | Kết hợp hai điều kiện OR |
| `existsByEmail(String email)` | Kiểm tra có bản ghi phù hợp |
| `countByEmailContaining(String part)` | Đếm bản ghi có email chứa chuỗi |
| `findTop10ByFullNameOrderByIdDesc(String name)` | Lấy tối đa 10 bản ghi, sắp xếp ID giảm dần |
| `findByIdBetween(Long from, Long to)` | Lọc ID trong khoảng |

Một số keyword hay dùng:

- `And`, `Or`: kết hợp điều kiện.
- `Between`, `LessThan`, `GreaterThanEqual`: so sánh giá trị.
- `Containing`, `StartingWith`, `EndingWith`: tìm chuỗi con/tiền tố/hậu tố.
- `IgnoreCase`: so sánh chuỗi không phân biệt hoa thường khi kiểu dữ liệu và database hỗ trợ.
- `In`, `NotIn`: so sánh với tập giá trị.
- `IsNull`, `IsNotNull`: kiểm tra null.
- `OrderBy`: khai báo thứ tự sắp xếp.
- `Top` hoặc `First`: giới hạn số kết quả.

Tên phương thức phải dùng tên thuộc tính Java của entity, không nhất thiết là tên cột trong database. Ví dụ entity có thuộc tính `fullName` ánh xạ tới cột `full_name`; derived query dùng `FullName`.

Tên phương thức quá dài và chứa nhiều điều kiện có thể khó đọc. Khi query phức tạp, cần join đặc biệt hoặc cần kiểm soát rõ JPQL/SQL, hãy cân nhắc `@Query`.

### Property path và quan hệ entity

Spring Data có thể phân tích property path lồng nhau. Ví dụ entity `Customer` có quan hệ `address.city`, query có thể khai báo:

```java
List<Customer> findByAddress_City(String city);
```

Dấu gạch dưới giúp phân tách property path khi tên thuộc tính có thể gây mơ hồ. Hãy xác nhận tên thuộc tính và quan hệ thực tế trong entity. Query method chỉ hoạt động khi Spring Data phân giải được đường dẫn property.

## 6. Khai báo truy vấn bằng @Query

`@Query` cho phép viết truy vấn rõ ràng ngay trong repository. Mặc định với Spring Data JPA, chuỗi truy vấn là JPQL, dùng tên entity và thuộc tính Java thay cho tên bảng/cột.

Ví dụ tìm customer theo một phần email:

```java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("""
       select c
       from Customer c
       where lower(c.email) like lower(concat('%', :keyword, '%'))
       """)
List<Customer> searchByEmail(@Param("keyword") String keyword);
```

JPQL tham chiếu entity `Customer` và thuộc tính `email`. Nếu muốn viết SQL trực tiếp theo tên bảng/cột, dùng `nativeQuery = true`:

```java
@Query(
    value = "select * from customers where email = :email",
    nativeQuery = true
)
Optional<Customer> findByEmailNative(@Param("email") String email);
```

Native SQL phụ thuộc hệ quản trị cơ sở dữ liệu và schema thực tế; hãy cân nhắc khả năng chuyển database và kiểm tra cú pháp SQL bằng đúng database đích.

### Query thay đổi dữ liệu

Với câu JPQL update/delete, cần đánh dấu `@Modifying`. Ví dụ:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
       update Customer c
       set c.fullName = :name
       where c.id = :id
       """)
int updateFullName(
        @Param("id") Long id,
        @Param("name") String name
);
```

Phương thức trả về số dòng bị ảnh hưởng. Hãy gọi nó trong transaction, thường được mở ở service bằng `@Transactional`. Bulk update/delete chạy trực tiếp ở mức query và không đi qua vòng đời từng entity như khi sửa từng object managed. Các entity đã được nạp trước đó trong persistence context có thể không còn đồng bộ; tùy tình huống, `clearAutomatically` giúp xóa persistence context sau thao tác và `flushAutomatically` đẩy thay đổi đang chờ trước khi chạy query.

Không dùng `@Modifying` cho truy vấn SELECT thông thường.

## 7. Phân trang và sắp xếp

Khi bảng có nhiều dữ liệu, repository nên trả về một phần kết quả. `Pageable` mô tả trang cần lấy; `Page<T>` chứa nội dung cùng metadata trang.

Ví dụ gọi phương thức `findByEmailContainingIgnoreCase` đã khai báo:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Direction.ASC, "email")
);

Page<Customer> page =
        customerRepository.findByEmailContainingIgnoreCase(
                "example",
                pageable
        );

List<Customer> customers = page.getContent();
int currentPage = page.getNumber();
int pageSize = page.getSize();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Các lưu ý:

- Chỉ số trang bắt đầu từ 0: `PageRequest.of(0, 20)` là trang đầu, kích thước 20.
- Tên thuộc tính trong `Sort.by` là thuộc tính entity, ví dụ `email`.
- Nên có thứ tự ổn định, thường thêm khóa chính làm tiêu chí phụ nếu cột sắp xếp có thể trùng nhau.
- `Page<T>` thường cần thêm truy vấn đếm để tính tổng số kết quả. Với màn hình chỉ cần biết còn trang tiếp theo hay không, `Slice<T>` có thể giảm chi phí vì không cần tổng số trang.
- Không nên lấy tất cả bản ghi rồi phân trang bằng Java nếu database có thể thực hiện phân trang trực tiếp.

## 8. Hành vi save, entity state và persistence context

`save` không phải lúc nào cũng có nghĩa là chạy ngay một câu INSERT hoặc UPDATE. JPA quản lý entity qua các trạng thái:

- **New/transient:** entity mới, chưa được persistence context quản lý.
- **Managed:** entity đang được EntityManager quản lý; thay đổi có thể được đồng bộ khi flush/commit.
- **Detached:** entity từng được quản lý nhưng hiện không còn gắn với persistence context.
- **Removed:** entity được đánh dấu xóa trong persistence context.

Trong Spring Data JPA, `save` thường gọi `persist` cho entity mới hoặc `merge` cho entity được xem là đã tồn tại. `merge` sao chép trạng thái của object đầu vào sang một instance managed và trả về instance đó. Vì vậy, hãy sử dụng giá trị trả về của `save` nếu cần tiếp tục thao tác với entity sau khi merge.

Đối với entity đã managed trong transaction hiện tại, thay đổi field thường được JPA dirty checking phát hiện. Ví dụ:

```java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow();

    customer.setFullName(newName);
    // Khi transaction commit, JPA đồng bộ thay đổi.
}
```

Không nhất thiết phải gọi `save(customer)` sau khi sửa entity managed. Tuy nhiên, nếu entity detached hoặc logic không nằm trong persistence context như mong đợi, cần xử lý trạng thái entity rõ ràng.

## 9. Transaction và ranh giới service

Các phương thức CRUD kế thừa từ repository có transaction configuration mặc định trong implementation Spring Data JPA. Các query method do ứng dụng khai báo không nên được giả định là tự có transaction. Thực hành phổ biến là đặt transaction ở service để một nghiệp vụ có thể bao trùm nhiều lời gọi repository.

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email, String name) {
        if (repository.existsByEmailIgnoreCase(email)) {
            throw new IllegalArgumentException("Email already exists");
        }

        return repository.save(new Customer(email, name));
    }

    @Transactional(readOnly = true)
    public Customer getRequired(Long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found: " + id)
                );
    }
}
```

Các điểm cần nhớ:

- `@Transactional` ở service xác định ranh giới nghiệp vụ.
- Các lời gọi repository trong cùng transaction thường tham gia cùng transaction hiện tại.
- `readOnly = true` là gợi ý cho transaction chỉ đọc; không dùng nó cho nghiệp vụ cần ghi.
- Mặc định, Spring rollback với unchecked exception. Nếu cần rollback với checked exception, cấu hình `rollbackFor` phù hợp.
- Transactional proxy hoạt động qua lời gọi từ bên ngoài bean. Tự gọi một phương thức `@Transactional` khác trong cùng instance thường không đi qua proxy.
- Tránh giữ transaction mở trong lúc gọi API bên ngoài hoặc thực hiện công việc chậm không liên quan đến database.

## 10. Tùy chỉnh hợp đồng repository

Không phải lúc nào ứng dụng cũng muốn công khai toàn bộ API của `JpaRepository`. Có thể tạo interface cơ sở để giới hạn các thao tác hoặc cung cấp query chung.

Ví dụ, một base interface chỉ khai báo những phương thức cần thiết:

```java
@NoRepositoryBean
public interface ReadOnlyRepository<T, ID>
        extends Repository<T, ID> {

    Optional<T> findById(ID id);

    List<T> findAll();
}
```

Repository cụ thể có thể kế thừa interface này và khai báo thêm các truy vấn. Tuy nhiên, nếu cần implementation cho phương thức tùy chỉnh, phải cung cấp cơ chế triển khai phù hợp; marker interface không tự tạo implementation cho mọi method tùy ý.

Một lựa chọn khác là kế thừa `JpaRepository` nhưng chỉ inject và sử dụng API cần thiết trong service. Cách này đơn giản hơn, nhưng interface vẫn công khai toàn bộ hợp đồng cho nơi khác có thể gọi.

### Custom repository implementation

Khi query hoặc hành vi persistence không thể biểu diễn gọn bằng derived query hay `@Query`, có thể tạo custom repository fragment. Một fragment gồm interface mô tả phương thức và class triển khai. Repository chính kế thừa fragment đó cùng các interface Spring Data cần thiết.

Ví dụ:

```java
public interface CustomerSearchRepository {
    List<Customer> searchActiveCustomers(String keyword);
}
```

```java
@Repository
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<Customer> searchActiveCustomers(String keyword) {
        return entityManager.createQuery("""
                select c
                from Customer c
                where c.active = true
                  and lower(c.fullName) like lower(:keyword)
                """, Customer.class)
            .setParameter("keyword", "%" + keyword + "%")
            .getResultList();
    }
}
```

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchRepository {
}
```

Quy ước đặt tên và cách phát hiện custom implementation có thể thay đổi theo version/cấu hình Spring Data. Hãy theo convention của version dự án và kiểm tra class implementation được Spring Data nhận diện khi khởi động. Với query đơn giản, ưu tiên derived query hoặc `@Query` để giảm lượng code tự quản lý.

## 11. Kiểm thử repository

`@DataJpaTest` là test slice dành cho JPA. Nó cấu hình các thành phần persistence và repository cần thiết; thường dùng embedded database nếu dự án có dependency phù hợp. Nếu cần xác minh hành vi đặc thù của PostgreSQL, có thể cấu hình test dùng database thật hoặc Testcontainers.

Ví dụ:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsCustomerIgnoringEmailCase() {
        repository.save(new Customer("linh@example.com", "Linh Nguyen"));

        assertThat(repository.findByEmailIgnoreCase("LINH@example.com"))
                .isPresent()
                .get()
                .extracting(Customer::getFullName)
                .isEqualTo("Linh Nguyen");
    }
}
```

Test giả định entity, repository và dependency test đã được cấu hình. `@DataJpaTest` thường chạy test trong transaction và rollback sau mỗi test. Khi dùng PostgreSQL-specific query, kiểu dữ liệu đặc thù hoặc constraint khác biệt, cần kiểm thử với PostgreSQL để tránh kết quả khác embedded database.

Nên kiểm thử các tình huống:

- Lưu entity mới và xác nhận ID được tạo.
- Tìm thấy và không tìm thấy bản ghi.
- Derived query có điều kiện, ignore case, sort và pagination.
- JPQL/native query và query thay đổi dữ liệu.
- Unique constraint và hành vi khi dữ liệu không hợp lệ.
- Các quan hệ entity, lazy loading và fetch strategy có liên quan.

## 12. Những lỗi thiết kế thường gặp

**Repository chứa logic nghiệp vụ.** Repository nên tập trung truy vấn và persistence. Quy tắc đăng ký, phân quyền, kiểm tra trạng thái và phối hợp nhiều repository thuộc service hoặc domain layer.

**Dùng findAll cho dữ liệu lớn.** Tải toàn bộ bảng có thể làm tốn bộ nhớ và thời gian. Dùng Page/Slice/Scroll phù hợp với yêu cầu.

**Giả định save luôn insert.** `save` có thể gọi persist hoặc merge. Hãy hiểu trạng thái entity và dùng instance được trả về.

**Giả định saveAll là bulk insert.** API không cam kết một câu SQL duy nhất. Kiểm tra batch setting và ID strategy nếu cần tối ưu.

**Dùng Optional cho query có thể trả nhiều hàng.** Nếu query trả về nhiều kết quả nhưng method khai báo một entity hoặc Optional, Spring Data có thể ném lỗi kết quả không duy nhất. Dùng List/Page hoặc bảo đảm điều kiện duy nhất bằng constraint.

**Không xử lý trường hợp không tồn tại.** `findById` trả Optional; service nên quyết định trả 404, báo lỗi nghiệp vụ hoặc xử lý mặc định.

**Dựa vào exists trước save để đảm bảo unique.** Hai request đồng thời vẫn có thể cùng vượt qua bước kiểm tra. Dùng unique constraint ở database và xử lý lỗi vi phạm constraint.

**Không hiểu version Spring Data.** Ví dụ interface hierarchy trên mạng có thể thuộc Spring Data 2.x hoặc 3.x. Kiểm tra dependency management của Spring Boot trước khi chọn interface.

**Trả entity trực tiếp ra API.** Điều này có thể gây lộ field, vòng lặp JSON do quan hệ hai chiều hoặc lazy loading ngoài transaction. Cân nhắc DTO và ánh xạ dữ liệu ở service/web layer.

## 13. Checklist khi thiết kế repository

- [ ] Generic entity và ID khớp với mapping JPA.
- [ ] Chọn hợp đồng tối thiểu đáp ứng nhu cầu; hiểu hierarchy theo version.
- [ ] Dùng Optional cho truy vấn đơn có thể không có kết quả.
- [ ] Dùng List/Page/Slice phù hợp với số lượng dữ liệu.
- [ ] Derived query có tên dễ hiểu và dùng đúng property path.
- [ ] Query phức tạp được tách rõ bằng @Query hoặc custom fragment.
- [ ] Transaction bao trùm nghiệp vụ được đặt ở service.
- [ ] Quy tắc toàn vẹn quan trọng được bảo vệ bằng constraint database.
- [ ] Repository được kiểm thử với các trường hợp thành công và lỗi.
- [ ] Không đưa logic nghiệp vụ hoặc secret vào repository.

## Kết luận

`Repository<T, ID>` là marker interface xác định một repository; `CrudRepository<T, ID>` cung cấp hợp đồng CRUD chuẩn. Spring Data JPA tạo implementation cho các repository interface và ánh xạ thao tác sang JPA. Những hợp đồng mở rộng như `PagingAndSortingRepository` và `JpaRepository` bổ sung phân trang, sắp xếp và chức năng persistence phù hợp.

Một repository tốt công khai đúng các thao tác cần thiết, dùng đúng kiểu entity/ID và giữ query dễ đọc. Service điều phối nghiệp vụ cùng transaction; database bảo vệ tính toàn vẹn dữ liệu. Nắm rõ hợp đồng giúp ứng dụng ít phụ thuộc vào implementation và dễ kiểm thử hơn.
