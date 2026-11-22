# Repository, CrudRepository và hợp đồng thao tác dữ liệu

## Mục tiêu

Repository là lớp trừu tượng mà Spring Data cung cấp để ứng dụng thao tác dữ liệu thông qua một hợp đồng Java. Với Spring Data JPA, ta khai báo interface repository dựa trên entity và kiểu khóa chính; Spring Data tạo implementation lúc chạy, kết nối các lời gọi repository với JPA và Hibernate.

Bài này tập trung vào `Repository<T, ID>`, `CrudRepository<T, ID>` và cách thiết kế hợp đồng truy cập dữ liệu. Sau khi hoàn thành, bạn có thể:

- Phân biệt repository marker interface với các hợp đồng CRUD, phân trang và JPA.
- Chọn đúng interface nền cho một repository.
- Hiểu ý nghĩa và kiểu trả về của các thao tác trong `CrudRepository`.
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

Spring Data tìm các repository interface trong package được cấu hình, thường là package chứa class `@SpringBootApplication` và các package con. Framework tạo proxy implementation khi ứng dụng khởi động. Vì vậy, ứng dụng thường chỉ cần khai báo interface, không cần tự viết class triển khai từng phương thức CRUD.

Trong Spring Boot, auto-configuration thường tự tìm repository. Với cấu hình đặc biệt hoặc package nằm ngoài vùng quét mặc định, có thể dùng `@EnableJpaRepositories` để chỉ rõ package repository.

### Hợp đồng và implementation

Một hợp đồng mô tả:

- Phương thức nào được phép gọi.
- Tham số đầu vào và kiểu kết quả.
- Ý nghĩa của thao tác ở mức nghiệp vụ/dữ liệu.
- Các điều kiện và hành vi mà bên triển khai phải tuân thủ.

Ví dụ, `CrudRepository` cam kết cung cấp các thao tác CRUD cơ bản. Spring Data JPA triển khai hợp đồng đó bằng JPA. Nếu dùng một module Spring Data khác, implementation có thể dựa trên công nghệ lưu trữ khác, trong khi phần lớn mã gọi repository vẫn giữ nguyên.

Điều này giảm phụ thuộc của service vào chi tiết truy cập dữ liệu. Service phụ thuộc vào interface; Spring Data cung cấp proxy phù hợp ở runtime.

## 2. Các interface repository thường gặp

Spring Data có nhiều hợp đồng với mức chức năng tăng dần. Những interface thường dùng trong Spring Data Commons và Spring Data JPA gồm:

| Interface | Vai trò |
|---|---|
| `Repository<T, ID>` | Marker interface gốc, chưa cung cấp CRUD |
| `CrudRepository<T, ID>` | Các thao tác tạo, đọc, cập nhật và xóa cơ bản |
| `ListCrudRepository<T, ID>` | CRUD với các phương thức trả về `List` thay cho `Iterable` ở một số thao tác danh sách |
| `PagingAndSortingRepository<T, ID>` | Truy vấn danh sách có sắp xếp hoặc phân trang |
| `ListPagingAndSortingRepository<T, ID>` | Biến thể trả về `List` cho các thao tác sắp xếp/phân trang |
| `JpaRepository<T, ID>` | Hợp đồng mở rộng dành cho JPA, bao gồm CRUD, phân trang/sắp xếp và các thao tác JPA bổ sung |
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

`JpaRepository` cung cấp các thao tác CRUD dạng danh sách, phân trang/sắp xếp và chức năng riêng của JPA. Trong Spring Data 3.x, nó kế thừa các hợp đồng danh sách tương ứng cùng `QueryByExampleExecutor`.

Ở Spring Data 2.x, quan hệ kế thừa giữa `PagingAndSortingRepository` và `CrudRepository` khác với 3.x. Khi đọc tài liệu hoặc code cũ, hãy đối chiếu version Spring Data thực tế của dự án. Không nên suy ra interface nào có sẵn phương thức chỉ từ ví dụ của một version khác.

### Khi nào nên dùng interface nào?

- Dùng `Repository` khi muốn tự thiết kế một hợp đồng rất nhỏ, chỉ công khai các phương thức cần thiết.
- Dùng `CrudRepository` khi cần CRUD cơ bản và không cần API trả về `List` cho các thao tác danh sách.
- Dùng `PagingAndSortingRepository` khi cần phân trang/sắp xếp; với Spring Data 3.x, kết hợp thêm `CrudRepository` nếu cũng cần CRUD.
- Dùng `JpaRepository` cho phần lớn repository JPA thông thường. Nó cung cấp API phong phú, nhưng không cần thiết phải dùng mọi phương thức.
- Dùng interface trung gian khi nhiều repository cần chung một tập phương thức.

Một interface trung gian chỉ dùng làm cha cho các repository khác có thể được đánh dấu `@NoRepositoryBean` để Spring Data không cố tạo repository instance trực tiếp cho nó:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends JpaRepository<T, ID> {

    boolean existsByIdAndArchivedFalse(ID id);
}
```

Các repository cụ thể kế thừa `BaseRepository` và cung cấp entity cùng kiểu ID. Chỉ tạo base repository khi có quy tắc chung thực sự; tránh thêm tầng interface không mang lại lợi ích.

## 3. Hợp đồng của CrudRepository

`CrudRepository<T, ID>` khai báo các thao tác cơ bản sau. Kiểu trả về được trình bày theo hợp đồng Spring Data Commons:

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

Các phương thức có thể được mô tả theo nhóm:

### 3.1. Create và Update: save, saveAll

`save` nhận entity và trả về entity đã được lưu. Trong Spring Data JPA, thao tác này thường dùng `EntityManager.persist` khi entity được xác định là mới và `EntityManager.merge` khi entity được xác định là đã tồn tại.

Điểm quan trọng: hãy dùng đối tượng được trả về từ `save`. Với thao tác merge, đối tượng được trả về có thể là instance managed khác với đối tượng đầu vào.

```java
Customer customer = new Customer("linh@example.com", "Linh Nguyen");

Customer saved = customerRepository.save(customer);

Long generatedId = saved.getId();
```

`saveAll` nhận một `Iterable` và trả về các entity đã lưu. Đây là API tiện lợi cho thao tác nhiều bản ghi. Không nên mặc định rằng nó luôn thực hiện một câu SQL bulk insert duy nhất; cách thực thi phụ thuộc JPA provider, cấu hình batch, ID generation strategy và database.

Nếu ID được gán thủ công, Spring Data có thể cần thêm thông tin để xác định entity mới hay cũ. Khi cơ chế nhận diện mặc định không phù hợp, có thể dùng trường `@Version` hoặc triển khai `Persistable` với `isNew()` theo hướng dẫn Spring Data JPA.

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

`findAll` và `findAllById` trả về `Iterable` trong `CrudRepository`. `findAllById` chỉ trả về các bản ghi thực sự tồn tại; không nên giả định kết quả có đủ mọi ID đầu vào hoặc giữ nguyên thứ tự ID yêu cầu. Nếu cần thứ tự cụ thể, hãy sắp xếp rõ ràng ở query hoặc trong logic phù hợp.

Không nên dùng `findAll()` để tải bảng lớn chỉ nhằm hiển thị một trang dữ liệu. Hãy dùng phân trang để giới hạn lượng dữ liệu đọc.

### 3.3. Delete: deleteById, delete, deleteAll

Các phương thức delete thực hiện thao tác xóa theo ID, entity hoặc tập entity. Hành vi chi tiết phụ thuộc implementation và hợp đồng của module; với CRUD repository chuẩn, yêu cầu xóa một ID không tồn tại được bỏ qua một cách im lặng.

Xóa một entity theo ID:

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

`PagingAndSortingRepository` cung cấp hợp đồng phân trang/sắp xếp; `JpaRepository` đã cung cấp sẵn các phương thức này cho repository JPA.

## 8. Dùng repository trong service và transaction

Repository là ranh giới truy cập dữ liệu. Service điều phối nghiệp vụ và thường là nơi đặt transaction bao trùm nhiều thao tác repository.

Ví dụ:

```java
package com.example.demo.customer;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer register(String email, String fullName) {
        if (repository.existsByEmailIgnoreCase(email)) {
            throw new IllegalArgumentException("Email already exists");
        }

        return repository.save(new Customer(email, fullName));
    }

    @Transactional(readOnly = true)
    public Customer getRequired(Long id) {
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found: " + id)
                );
    }

    @Transactional
    public Customer rename(Long id, String newName) {
        Customer customer = repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found: " + id)
                );

        customer.setFullName(newName);
        return customer;
    }
}
```

Trong `rename`, entity được nạp trong transaction và đang managed bởi persistence context. Khi transaction commit, JPA dirty checking phát hiện thay đổi và ghi xuống database; không bắt buộc gọi `save` lần nữa cho entity managed này.

Các nguyên tắc transaction:

- Các phương thức CRUD kế thừa từ repository có transaction configuration mặc định của Spring Data. Read methods thường được cấu hình read-only; các thao tác ghi có transaction.
- Query method do ứng dụng tự khai báo không nên được giả định là tự có transaction. Hãy đặt transaction ở service hoặc cấu hình rõ cho query method.
- Nếu một nghiệp vụ gọi nhiều repository, đặt `@Transactional` ở service giúp các thao tác cùng tham gia một transaction.
- `readOnly = true` là gợi ý tối ưu cho transaction chỉ đọc; không dùng nó cho nghiệp vụ cần ghi dữ liệu.
- Mặc định, transaction của Spring rollback với unchecked exception. Nếu cần rollback với checked exception, khai báo `rollbackFor` phù hợp.
- Transactional proxy hoạt động qua lời gọi từ bên ngoài bean. Tự gọi một phương thức `@Transactional` khác trong cùng instance (self-invocation) thường không đi qua proxy và có thể không áp dụng transaction như mong đợi.

Không đặt logic nghiệp vụ phức tạp vào repository. Repository tập trung vào truy vấn và thao tác persistence; service quyết định khi nào đọc, ghi, kiểm tra điều kiện và phối hợp nhiều nguồn dữ liệu.

## 9. Kiểm thử repository

`@DataJpaTest` là test slice dành cho JPA. Nó cấu hình các thành phần persistence cần thiết, tạo repository và thường dùng embedded database nếu dự án có dependency phù hợp. Test có thể dùng database thật/Testcontainers khi cần xác minh hành vi theo đúng hệ quản trị đích.

Ví dụ kiểm tra derived query:

```java
package com.example.demo.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

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

Test này giả định entity và repository đã được đặt trong package được Spring Boot quét, và project đã có dependency test như `spring-boot-starter-test`. `@DataJpaTest` thường rollback transaction của từng test sau khi chạy, giúp các test độc lập hơn.

Nên kiểm thử:

- Lưu entity và xác nhận ID được tạo.
- Tìm entity có tồn tại và không tồn tại.
- Kiểm tra derived query, query có điều kiện và thứ tự sắp xếp.
- Kiểm tra phân trang với dữ liệu đủ nhiều.
- Kiểm tra update/delete query và số dòng bị ảnh hưởng.
- Kiểm tra constraint như unique email trên database thực tế nếu đó là yêu cầu quan trọng.

## 10. Lỗi thường gặp và cách tránh

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy bean repository | Package repository nằm ngoài vùng component/repository scan | Đặt package phù hợp hoặc cấu hình `@EnableJpaRepositories` |
| Sai kiểu ID | Generic ID không khớp kiểu trường `@Id` | Khai báo đúng kiểu, ví dụ `JpaRepository<Customer, Long>` |
| Spring báo không phân tích được tên query | Derived method tham chiếu sai tên thuộc tính hoặc keyword | Đối chiếu property của entity và cú pháp Spring Data |
| Không có phương thức CRUD khi chỉ kế thừa PagingAndSortingRepository | Hệ phân cấp thay đổi từ Spring Data 3.0 | Kế thừa thêm CrudRepository hoặc dùng JpaRepository |
| Truy vấn trả về nhiều kết quả nhưng khai báo Optional | Query không bảo đảm duy nhất một kết quả | Dùng List/Page hoặc bảo đảm unique constraint phù hợp |
| Không có thứ tự ổn định khi gọi findAll | Không khai báo Sort/OrderBy | Định nghĩa thứ tự trong query hoặc truyền Sort |
| LazyInitializationException | Truy cập lazy relationship sau khi persistence context đóng | Tải dữ liệu trong transaction, dùng fetch query/entity graph hoặc ánh xạ DTO phù hợp |
| Thay đổi entity nhưng không lưu | Entity detached hoặc transaction/persistence context không còn hoạt động | Đảm bảo entity managed trong transaction; dùng save khi cần merge entity detached |
| Bulk update nhưng entity đang nạp vẫn có dữ liệu cũ | Bulk query bỏ qua trạng thái entity trong persistence context | Flush/clear phù hợp hoặc tải lại entity |
| saveAll không nhanh như mong đợi | Không đồng nghĩa với một bulk SQL insert | Kiểm tra batch JDBC, ID strategy, Hibernate settings và số round trip |
| Hai request cùng đăng ký một email | Kiểm tra exists trước khi insert không chống được race condition | Dùng unique constraint trong database và xử lý lỗi vi phạm constraint |

Một quy tắc quan trọng: kiểm tra bằng `existsByEmail` trước khi `save` có ích cho thông báo thân thiện, nhưng không đảm bảo duy nhất khi nhiều request đồng thời. Constraint `UNIQUE` trong database mới là cơ chế bảo vệ cuối cùng.

## 11. Checklist chọn và thiết kế repository

- [ ] Chọn entity và kiểu ID đúng cho generic repository.
- [ ] Chỉ kế thừa những hợp đồng mà service thực sự cần.
- [ ] Hiểu sự khác nhau giữa `CrudRepository`, `PagingAndSortingRepository` và `JpaRepository` theo version Spring Data đang dùng.
- [ ] Dùng `Optional` cho truy vấn đơn có thể không tìm thấy.
- [ ] Dùng `Pageable` hoặc `Sort` khi cần giới hạn và sắp xếp kết quả.
- [ ] Dùng derived query cho điều kiện đơn giản, `@Query` cho truy vấn cần kiểm soát rõ.
- [ ] Đặt transaction ở service cho một nghiệp vụ gồm nhiều thao tác dữ liệu.
- [ ] Dùng unique/foreign key/check constraint ở database cho quy tắc toàn vẹn quan trọng.
- [ ] Kiểm thử cả trường hợp có dữ liệu, không có dữ liệu và dữ liệu vi phạm constraint.
- [ ] Không đưa mật khẩu, thông tin nhạy cảm hoặc logic nghiệp vụ vào repository.

## Kết luận

`Repository<T, ID>` đánh dấu một interface truy cập dữ liệu; `CrudRepository<T, ID>` bổ sung hợp đồng CRUD chuẩn. Spring Data JPA tạo implementation cho repository và ánh xạ các phương thức sang thao tác JPA. Khi cần phân trang, sắp xếp hoặc API JPA phong phú, có thể chọn các interface mở rộng như `JpaRepository`.

Thiết kế repository tốt bắt đầu từ hợp đồng nhỏ, kiểu entity/ID chính xác và các query dễ hiểu. Service chịu trách nhiệm điều phối nghiệp vụ và transaction; database tiếp tục bảo vệ tính toàn vẹn bằng constraint. Nắm vững các ranh giới này giúp code truy cập dữ liệu dễ kiểm thử, thay đổi và bảo trì.
