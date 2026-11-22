# Thiết kế giao diện cơ sở bằng @NoRepositoryBean

## 1. Vì sao cần một repository interface cơ sở?

Trong ứng dụng Spring Data JDBC, mỗi aggregate thường có một repository riêng:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Khi số aggregate tăng lên, nhiều repository có thể lặp lại các thao tác dùng chung: tìm một bản ghi bắt buộc phải tồn tại, kiểm tra ID, hoặc một số phương thức tiện ích được chuẩn hóa trong dự án. Ta có thể khai báo một **repository interface cơ sở (base repository interface)** chứa phần hợp đồng chung, sau đó cho các repository cụ thể kế thừa.

Vấn đề là Spring Data tự động phát hiện repository interface trong phạm vi scan và tạo implementation/proxy cho những interface đủ điều kiện. Một interface cơ sở có generic type như `T` và `ID` chưa đại diện cho một aggregate cụ thể. Ta không muốn framework tạo một repository độc lập cho interface trung gian đó.

Annotation `@NoRepositoryBean` giải quyết đúng tình huống này: nó đánh dấu một repository interface là **giao diện cơ sở, không tạo repository bean trực tiếp cho chính interface đó**. Các repository cụ thể kế thừa nó vẫn được phát hiện và tạo bean bình thường.

Trong bài này, ta sẽ:

- Hiểu cơ chế repository scanning và lý do cần `@NoRepositoryBean`.
- Thiết kế generic base interface dùng chung cho Spring Data JDBC.
- Kế thừa base interface từ repository cụ thể của từng aggregate.
- Phân biệt phương thức mặc định, derived query, `@Query` và repository fragment.
- Nhận diện những lỗi phổ biến khi đặt annotation sai chỗ hoặc khai báo method không có implementation.

## 2. `@NoRepositoryBean` làm gì?

`@NoRepositoryBean` thuộc package:

```java
import org.springframework.data.repository.NoRepositoryBean;
```

Nó được đặt trên một repository interface để thông báo cho Spring Data:

> Interface này là một phần của hệ thống kế thừa repository. Không tạo repository bean riêng cho interface này.

Ví dụ:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

`BaseRepository` là generic. Chưa có loại aggregate cụ thể để Spring Data JDBC ánh xạ vào bảng nào. Ta chỉ dùng nó làm cha cho repository có kiểu cụ thể:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {
}
```

Lúc này Spring Data biết repository cụ thể quản lý `Customer` và ID kiểu `UUID`. Nó tạo bean cho `CustomerRepository`, còn `BaseRepository` chỉ cung cấp hợp đồng kế thừa.

### Annotation này không có nghĩa gì?

`@NoRepositoryBean`:

- Không tắt repository scanning cho toàn package.
- Không tắt repository của interface con.
- Không tự tạo implementation cho phương thức tùy chỉnh.
- Không thay thế `@Repository` trên một DAO viết tay.
- Không tạo SQL, không đổi cách ánh xạ aggregate và không thay đổi transaction.
- Không phải annotation đánh dấu entity hay aggregate root.

Nó chỉ điều khiển việc Spring Data có tạo repository instance cho **interface được đánh dấu** hay không.

## 3. Vì sao interface generic cần được loại khỏi repository scanning?

Spring Data JDBC tạo repository dựa trên domain type và ID type mà nó xác định được từ interface. Với repository cụ thể:

```java
public interface CustomerRepository
        extends CrudRepository<Customer, UUID> {
}
```

Framework có thể xác định:

```text
Domain type = Customer
ID type     = UUID
```

Nhưng với base interface:

```java
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
}
```

`T` và `ID` chưa được gắn với một aggregate cụ thể. Interface này không phải repository mà ứng dụng cần inject để thao tác dữ liệu. Nếu Spring Data cố tạo repository cho nó, framework không có một domain type cụ thể phù hợp để xây dựng repository.

`@NoRepositoryBean` loại interface trung gian đó khỏi việc tạo bean, đồng thời vẫn giữ quan hệ generic để interface con kế thừa được các phương thức.

### Cấu trúc kế thừa

```text
                 CrudRepository<T, ID>
                           |
                           v
             @NoRepositoryBean
                 BaseRepository<T, ID>
                    /          \
                   /            \
                  v              v
       CustomerRepository   PurchaseOrderRepository
          <Customer, UUID>       <PurchaseOrder, Long>
                  |              |
                  v              v
          Repository bean  Repository bean
```

Chỉ hai interface cụ thể phía dưới được tạo repository bean. Base interface đóng vai trò hợp đồng chung.

## 4. Thiết kế base repository tối giản

Với Spring Data JDBC, có thể bắt đầu từ `CrudRepository<T, ID>`:

```java
package com.example.shared;

import java.util.NoSuchElementException;

import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.NoRepositoryBean;

@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    default T getRequiredById(ID id) {
        return findById(id)
                .orElseThrow(() -> new NoSuchElementException(
                        "Entity not found: " + id));
    }
}
```

Giải thích:

1. `T` là kiểu aggregate mà repository cụ thể quản lý.
2. `ID` là kiểu khóa chính tương ứng; có thể là `Long`, `UUID` hoặc kiểu ID khác.
3. `extends CrudRepository<T, ID>` kế thừa các thao tác CRUD chuẩn.
4. `@NoRepositoryBean` ngăn Spring Data tạo bean cho chính `BaseRepository`.
5. `getRequiredById` là Java default method. Nó gọi `findById` đã được kế thừa và chuyển `Optional.empty()` thành exception nếu không tìm thấy.

Phương thức mặc định phù hợp cho logic tiện ích thực sự chung và có thể triển khai chỉ bằng các phương thức repository đã có. Không nên thêm hàng loạt method vào base interface chỉ để gom những thao tác tình cờ có tên giống nhau.

### Vì sao dùng default method?

Nếu khai báo:

```java
T getRequiredById(ID id);
```

đây là một method trừu tượng. Spring Data có thể xem nó như một query method và cố gắng tìm cách tạo truy vấn hoặc yêu cầu một implementation. Nó không tự biết rằng ta muốn gọi `findById` rồi ném exception.

Với `default`, phần thân phương thức đã có sẵn trong Java interface, nên không cần một query implementation riêng.

Nếu logic dùng chung phức tạp, phụ thuộc nhiều repository hoặc có quy tắc nghiệp vụ, hãy cân nhắc đặt nó trong application service/domain service thay vì biến base repository thành một lớp service tổng hợp.

## 5. Repository cụ thể kế thừa base interface

Giả sử có aggregate `Customer`:

```java
package com.example.customer;

import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id UUID id,
        String name,
        String email
) {
}
```

Repository cụ thể:

```java
package com.example.customer;

import java.util.Optional;
import java.util.UUID;

import com.example.shared.BaseRepository;

public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {

    Optional<Customer> findByEmail(String email);
}
```

`CustomerRepository` kế thừa:

- `save(Customer)`.
- `findById(UUID)`.
- `findAll()`.
- `existsById(UUID)`.
- `deleteById(UUID)`.
- `getRequiredById(UUID)` do base interface cung cấp.
- `findByEmail(String)` do Spring Data JDBC suy diễn từ tên method.

Một aggregate khác có ID kiểu `Long`:

```java
package com.example.orders;

import com.example.shared.BaseRepository;

public interface PurchaseOrderRepository
        extends BaseRepository<PurchaseOrder, Long> {
}
```

Cả hai repository dùng cùng hợp đồng chung, nhưng domain type và ID type vẫn được xác định tại interface con.

## 6. Spring Data JDBC tạo bean cho repository nào?

Trong cấu hình Spring Boot thông thường, repository scanning bắt đầu từ package của application class và các package con, hoặc từ phạm vi được chỉ định rõ bằng cấu hình repository. Spring Data tìm những interface repository phù hợp.

Với cấu trúc:

```text
com.example
├── Application.java
├── shared
│   └── BaseRepository.java
├── customer
│   ├── Customer.java
│   └── CustomerRepository.java
└── orders
    ├── PurchaseOrder.java
    └── PurchaseOrderRepository.java
```

`Application` có thể đặt ở `com.example` để component scan và repository scan mặc định bao phủ các package con. `BaseRepository` được nhận diện là repository interface nhưng không được tạo bean do có `@NoRepositoryBean`. Hai interface cụ thể vẫn được đăng ký.

Ví dụ sử dụng trong service:

```java
package com.example.customer;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional(readOnly = true)
    public Customer get(UUID id) {
        return customers.getRequiredById(id);
    }
}
```

Ứng dụng inject `CustomerRepository`. Không inject `BaseRepository<Customer, UUID>` như một bean riêng trừ khi bạn đã tự thiết kế một bean/implementation khác; interface cơ sở có `@NoRepositoryBean` không phải một bean được Spring Data tạo.

## 7. Có thể đặt nhiều phương thức dùng chung trong base interface không?

Có, nhưng cần phân biệt các loại method.

### 7.1. Phương thức CRUD kế thừa

Đây là các method từ `CrudRepository`. Spring Data đã có implementation:

```java
save(entity);
findById(id);
findAll();
deleteById(id);
existsById(id);
```

Không cần khai báo lại trong base interface nếu không thay đổi hợp đồng.

### 7.2. Java default method

Phù hợp với logic đơn giản được xây dựng từ những method repository đã có:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    default boolean isMissing(ID id) {
        return !existsById(id);
    }
}
```

Đây là code Java thông thường. Nó không cần Spring Data suy diễn câu SQL mới.

Tuy nhiên, tránh dùng `existsById` rồi mới `save` để quyết định một nghiệp vụ ghi có tính cạnh tranh. Hai thao tác đó có thể bị một transaction khác xen vào; constraint của database hoặc một lệnh SQL nguyên tử phù hợp mới là cơ chế bảo vệ đáng tin cậy.

### 7.3. Derived query method

Method khai báo theo quy ước tên, ví dụ:

```java
Optional<Customer> findByEmail(String email);
```

Spring Data JDBC có thể phân tích tên method để tạo query tương ứng nếu thuộc tập tính năng query derivation được hỗ trợ. Đây là method thuộc repository cụ thể vì điều kiện email gắn với mô hình `Customer`, không phải mọi aggregate đều có email.

Không đặt `findByEmail` trong base interface generic chỉ vì nhiều bảng có cột tên tương tự; tên field và ý nghĩa miền phải thực sự phù hợp với tất cả kiểu T.

### 7.4. Method có `@Query`

Nếu truy vấn SQL đặc thù chỉ áp dụng cho một aggregate, đặt nó trên repository cụ thể:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {

    @Query("SELECT * FROM customers WHERE email = :email")
    Optional<Customer> lookupByEmail(String email);
}
```

Đây là ví dụ minh họa cho một query tĩnh. Cú pháp bind parameter, tên cột và cách ánh xạ kết quả cần phù hợp với Spring Data JDBC và database đang dùng. Không chuyển một câu SQL phụ thuộc bảng `customers` lên base interface generic.

## 8. Khi cần custom implementation: repository fragment

`@NoRepositoryBean` không tạo implementation cho method trừu tượng tùy chỉnh. Nếu một thao tác cần code riêng, Spring Data hỗ trợ mô hình repository fragment.

Ví dụ ta muốn thêm một thao tác tùy chỉnh cho khách hàng:

### 8.1. Khai báo fragment interface

```java
package com.example.customer;

public interface CustomerSearch {
    long countWithEmailDomain(String domain);
}
```

### 8.2. Viết implementation

```java
package com.example.customer;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

public class CustomerSearchImpl implements CustomerSearch {

    private final JdbcTemplate jdbcTemplate;

    public CustomerSearchImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public long countWithEmailDomain(String domain) {
        String sql = """
                SELECT COUNT(*)
                FROM customers
                WHERE email LIKE ?
                """;

        Long count = jdbcTemplate.queryForObject(
                sql,
                Long.class,
                "%@" + domain
        );
        return count == null ? 0 : count;
    }
}
```

Tên implementation theo quy ước fragment là `CustomerSearchImpl`. Tùy cấu hình repository implementation postfix và cách tổ chức module, cần bảo đảm Spring Data tìm được implementation fragment. Trong ví dụ này, fragment chỉ minh họa ý tưởng; dự án thực tế nên kiểm tra naming/configuration theo phiên bản Spring Data đang dùng.

### 8.3. Kết hợp fragment vào repository

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID>, CustomerSearch {
}
```

`CustomerRepository` kết hợp:

- CRUD chung từ `BaseRepository`.
- Hành vi tìm kiếm tùy chỉnh từ `CustomerSearch`.
- Query method hoặc `@Query` riêng của Customer nếu cần.

Không đưa implementation phụ thuộc `JdbcTemplate` vào base interface. Interface cơ sở nên giữ hợp đồng chung; phần triển khai đặc thù thuộc fragment hoặc adapter riêng.

## 9. Phân biệt base repository interface và custom repository base class

Hai cơ chế này có tên gần nhau nhưng giải quyết vấn đề khác nhau:

| Cơ chế | Vai trò | Cách sử dụng |
| --- | --- | --- |
| `@NoRepositoryBean` + generic interface | Chia sẻ hợp đồng và default method giữa nhiều repository | Repository cụ thể kế thừa interface generic |
| Repository fragment | Bổ sung implementation tùy chỉnh cho một nhóm repository | Repository cụ thể kế thừa fragment interface và Spring ghép implementation |
| Custom repository base class | Thay đổi lớp implementation nền mà Spring Data dùng để tạo repository proxy | Cấu hình repository factory/base class theo extension point phù hợp |

`@NoRepositoryBean` không biến interface thành custom base class. Nó cũng không cho phép override toàn bộ cách Spring Data thực hiện `save` hoặc `findById`. Nếu mục tiêu là thay đổi thuật toán của các phương thức repository lõi, hãy nghiên cứu custom repository base class và cấu hình factory tương ứng; đó là một chủ đề khác với việc tạo generic base interface.

## 10. Những nguyên tắc thiết kế để base interface không trở thành “God Repository”

Một base interface quá lớn có thể khiến mọi repository phải mang theo method không phù hợp với aggregate của nó. Ví dụ:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {

    Optional<T> findByEmail(String email);
    List<T> findByStatus(String status);
    BigDecimal calculateRevenue();
    void archiveAll();
}
```

Các method trên không thể có cùng ý nghĩa với mọi kiểu T:

- Không phải aggregate nào cũng có email.
- Không phải aggregate nào cũng có status.
- Tính doanh thu không phải trách nhiệm chung của mọi repository.
- Archive hàng loạt có thể vi phạm quy tắc aggregate và transaction.

Một số nguyên tắc thực tế:

1. Chỉ đưa vào base interface những thao tác thực sự có ý nghĩa với mọi aggregate tham gia.
2. Ưu tiên method mặc định ngắn, dễ hiểu và được xây dựng từ contract CRUD có sẵn.
3. Query theo thuộc tính riêng của entity nên nằm ở repository cụ thể.
4. Truy vấn SQL phức tạp hoặc thao tác đặc thù nên dùng `@Query`, fragment hoặc adapter chuyên trách.
5. Không biến repository thành application service; repository không nên điều phối nhiều aggregate và hệ thống ngoài.
6. Không thêm method chỉ để giảm số dòng khai báo nếu nó làm API khó hiểu hơn.

Base interface tốt giúp giảm lặp lại mà không che giấu trách nhiệm riêng của từng aggregate.

## 11. Lỗi thường gặp khi dùng @NoRepositoryBean

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Ứng dụng cố tạo repository cho interface generic | Quên `@NoRepositoryBean` trên base interface | Thêm annotation đúng package vào interface trung gian. |
| Không inject được repository cụ thể | Interface con nằm ngoài phạm vi repository scan hoặc generic type không được khai báo đúng | Kiểm tra package scan và khai báo `BaseRepository<Customer, UUID>` rõ ràng. |
| Method tùy chỉnh không có implementation | Khai báo method trừu tượng trong base interface nhưng không phải query method hợp lệ hoặc fragment | Dùng default method, query method, `@Query` hoặc fragment implementation. |
| Tất cả repository có method không liên quan | Đưa query riêng của một aggregate lên base interface | Di chuyển method về repository cụ thể. |
| Import sai `NoRepositoryBean` | Dùng nhầm package hoặc annotation khác tên | Dùng `org.springframework.data.repository.NoRepositoryBean`. |
| Nghĩ annotation ngăn repository con được tạo | Hiểu annotation như tắt toàn bộ scanning | Chỉ interface được đánh dấu không có bean riêng; repository con vẫn được đăng ký. |
| Nghĩ base interface có thể thay đổi SQL lõi | Nhầm interface với custom base implementation class | Dùng repository fragment hoặc custom base class theo đúng nhu cầu. |
| Generic type bị mất | Repository con kế thừa raw type hoặc khai báo generic không cụ thể | Luôn truyền domain type và ID type cụ thể ở repository con. |

Khi ứng dụng khởi động lỗi, hãy xem interface nào Spring Data đang cố tạo repository cho nó. Nếu tên interface là base generic, kiểm tra `@NoRepositoryBean`; nếu là repository cụ thể, kiểm tra domain class có mapping hợp lệ và generic type có được xác định rõ không.

## 12. Bài tập thực hành

**Bài tập 1 — Tạo base interface.** Tạo `BaseRepository<T, ID>` kế thừa `CrudRepository<T, ID>` và đánh dấu `@NoRepositoryBean`. Thêm default method `getRequiredById`.

**Bài tập 2 — Hai repository cụ thể.** Tạo `CustomerRepository extends BaseRepository<Customer, UUID>` và `PurchaseOrderRepository extends BaseRepository<PurchaseOrder, Long>`. Inject từng repository vào service và gọi method chung.

**Bài tập 3 — Cố ý bỏ annotation.** Tạm bỏ `@NoRepositoryBean` rồi khởi động ứng dụng. Quan sát Spring Data xử lý interface generic như thế nào trong phiên bản dự án. Khôi phục annotation và so sánh.

**Bài tập 4 — Tách query riêng.** Đặt `findByEmail` trên `CustomerRepository`. Giải thích vì sao method này không thuộc `BaseRepository`.

**Bài tập 5 — Default method và abstract method.** Khai báo một method tiện ích dưới dạng abstract rồi chuyển thành default method có gọi `findById`. So sánh hành vi repository startup và giải thích sự khác biệt giữa Java implementation với query derivation.

**Bài tập 6 — Repository fragment.** Tạo một fragment interface cho truy vấn thống kê riêng của Customer, viết implementation dùng `JdbcTemplate` và kết hợp vào `CustomerRepository`. Quan sát cách Spring ghép fragment với repository CRUD.

**Bài tập 7 — Ranh giới trách nhiệm.** Chọn một thao tác đang nằm trong base repository nhưng chỉ có ý nghĩa với một aggregate. Di chuyển nó về repository cụ thể hoặc application service và giải thích vì sao API trở nên rõ hơn.

## 13. Ghi nhớ

`@NoRepositoryBean` đánh dấu một repository interface trung gian để Spring Data **không tạo bean cho chính interface đó**. Nó thường được dùng cùng generic base interface:

```java
@NoRepositoryBean
public interface BaseRepository<T, ID>
        extends CrudRepository<T, ID> {
    // Hợp đồng và default method dùng chung
}
```

Repository cụ thể cung cấp domain type và ID type:

```java
public interface CustomerRepository
        extends BaseRepository<Customer, UUID> {
}
```

Spring Data JDBC vẫn tạo bean cho `CustomerRepository`. Hãy giữ base interface nhỏ, chỉ chứa hành vi thật sự dùng chung; query riêng thuộc repository cụ thể, còn implementation tùy chỉnh thuộc repository fragment hoặc custom base class. `@NoRepositoryBean` điều khiển việc tạo repository bean, **không tự triển khai method, không thay đổi SQL và không thay thế application service**.

### Tài liệu tham khảo

- [Spring Data Commons – NoRepositoryBean API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/NoRepositoryBean.html)
- [Spring Data Relational – JDBC Repositories](https://docs.spring.io/spring-data/relational/reference/jdbc/repositories.html)
- [Spring Data Commons – Custom Repository Implementations](https://docs.spring.io/spring-data/commons/reference/repositories/custom-implementations.html)
