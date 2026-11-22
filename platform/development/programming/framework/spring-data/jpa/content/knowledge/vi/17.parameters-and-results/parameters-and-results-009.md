# Xử lý kết quả rỗng và IncorrectResultSizeDataAccessException trong Spring Data JPA

Khi gọi repository, truy vấn có thể không tìm thấy dòng nào, tìm được đúng một dòng hoặc trả về nhiều dòng ngoài dự kiến. Cách Spring Data JPA biểu diễn từng trường hợp phụ thuộc kiểu trả về của method. Nếu method yêu cầu một kết quả duy nhất nhưng database trả nhiều kết quả, ứng dụng có thể nhận IncorrectResultSizeDataAccessException.

Hiểu rõ hợp đồng kết quả giúp phân biệt "không tìm thấy" với "dữ liệu không duy nhất", chọn đúng kiểu trả về, tránh bắt lỗi sai cách và thiết kế truy vấn có tính xác định. Bài học này giải thích hành vi của Optional, entity đơn, collection, Page/Slice, cách xử lý exception, nguyên nhân query trả trùng và cách kiểm thử các trường hợp biên.

## 1. Ba trường hợp kết quả của một truy vấn

Một truy vấn đọc thông thường có thể có ba số lượng kết quả:

| Số kết quả | Ý nghĩa | Cách ứng dụng nên xử lý |
|---:|---|---|
| 0 | Không có dòng phù hợp | Trả empty/null theo kiểu trả về hoặc xử lý nghiệp vụ "không tìm thấy" |
| 1 | Có đúng một dòng | Trả entity, Optional có giá trị hoặc một giá trị scalar |
| Nhiều hơn 1 | Có nhiều dòng phù hợp | Trả collection hoặc báo lỗi nếu method yêu cầu một kết quả duy nhất |

Kiểu trả về repository chính là một phần của hợp đồng. Nếu nghiệp vụ cho phép nhiều kết quả, hãy dùng List, Page hoặc Slice. Nếu nghiệp vụ yêu cầu duy nhất, hãy dùng Optional hoặc entity đơn và bảo đảm điều kiện truy vấn thực sự duy nhất.

Không nên chọn Optional chỉ vì muốn code gọn. Optional<T> biểu đạt 0 hoặc 1 kết quả; nó không có nghĩa "lấy một phần tử bất kỳ trong số nhiều kết quả".

## 2. Kết quả rỗng với Optional<T>

Optional<T> phù hợp khi truy vấn có thể không tìm thấy bản ghi và tối đa chỉ nên có một bản ghi.

Ví dụ:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
~~~

Sử dụng:

~~~java
Optional<Customer> result =
        repository.findByEmail("missing@example.com");

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.getDisplayName());
} else {
    System.out.println("Customer not found");
}
~~~

Kết quả nếu không có bản ghi:

~~~text
Customer not found
~~~

Có thể dùng ifPresent(), map(), orElse() hoặc orElseThrow():

~~~java
Customer customer = repository.findByEmail(email)
        .orElseThrow(() -> new CustomerNotFoundException(email));
~~~

Một số cách dùng thường gặp:

| Cách gọi | Ý nghĩa |
|---|---|
| isPresent() | Kiểm tra có giá trị |
| isEmpty() | Kiểm tra không có giá trị |
| orElse(value) | Trả giá trị mặc định nếu empty |
| orElseGet(supplier) | Tạo giá trị mặc định khi cần |
| orElseThrow() | Ném exception nếu empty |
| map(function) | Biến đổi giá trị nếu có |
| ifPresent(consumer) | Thực hiện hành động nếu có |

Lưu ý: Optional không cho phép chứa null. Nếu query trả một giá trị null hoặc không có kết quả, cách ánh xạ thành Optional có thể dẫn tới Optional.empty(). Nếu cần phân biệt "không có dòng" với "có dòng nhưng cột được SELECT là null", hãy truy vấn entity/DTO có thêm khóa chính hoặc một trường không null để giữ thông tin phân biệt.

## 3. Kết quả rỗng với entity đơn hoặc kiểu nullable

Repository có thể khai báo kiểu entity đơn:

~~~java
Customer findByEmail(String email);
~~~

Với truy vấn không có kết quả, Spring Data JPA thường trả null cho kiểu tham chiếu đơn. Nếu có nhiều hơn một kết quả, method không thể chọn một cách hợp lệ và sẽ phát sinh lỗi kích thước kết quả.

Kiểu trả về nullable có thể phù hợp với code Java cũ, nhưng Optional thường thể hiện ý định rõ hơn:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Nếu dùng kiểu trả về đơn có thể null, hãy chú thích nullability và kiểm tra null trước khi truy cập. Không nên để null lan sâu trong service rồi gây NullPointerException.

Ví dụ:

~~~java
Customer customer = repository.findByEmail(email);

if (customer == null) {
    throw new CustomerNotFoundException(email);
}

return customer.getDisplayName();
~~~

Không nhầm kết quả rỗng của query với giá trị null của một thuộc tính trong entity. Một entity có thể tồn tại nhưng một cột nullable của nó vẫn là null.

## 4. Collection trả về danh sách rỗng

Nếu truy vấn có thể trả nhiều bản ghi, hãy dùng List<T>, Set<T> hoặc collection phù hợp.

~~~java
List<Customer> findByDisplayNameContainingIgnoreCase(String keyword);
~~~

Khi không có dòng phù hợp, repository trả collection rỗng, thông thường không trả null:

~~~java
List<Customer> customers =
        repository.findByDisplayNameContainingIgnoreCase("unknown");

if (customers.isEmpty()) {
    System.out.println("No matching customers");
}
~~~

Không cần kiểm tra null trước khi gọi isEmpty() với collection result thông thường.

Các kiểu collection:

| Kiểu trả về | Không có kết quả | Nhiều kết quả |
|---|---|---|
| List<T> | List rỗng | Giữ thứ tự kết quả của query nếu có ORDER BY |
| Set<T> | Set rỗng | Không giữ duplicate theo equals/hashCode |
| Collection<T> | Collection rỗng | Chứa các phần tử phù hợp |
| Iterable<T> | Iterable rỗng | Duyệt được các phần tử |

Nếu thứ tự kết quả quan trọng, dùng List và khai báo ORDER BY. Không dựa vào thứ tự ngẫu nhiên của database.

## 5. Page, Slice và Stream khi không có kết quả

Các kiểu trả về hỗ trợ phân trang cũng có hợp đồng rõ ràng.

~~~java
Page<Customer> findByDisplayNameContaining(
        String keyword,
        Pageable pageable);

Slice<Customer> findByActiveTrue(Pageable pageable);
~~~

- Page có content rỗng khi không có bản ghi. totalElements bằng 0 và totalPages bằng 0.
- Slice có content rỗng và hasNext() bằng false khi không còn dữ liệu.
- Stream<T> có thể không có phần tử; cần đóng stream sau khi dùng và thường phải duy trì transaction trong lúc đọc.

Ví dụ Page:

~~~java
Page<Customer> page = repository.findByDisplayNameContaining(
        "unknown",
        PageRequest.of(0, 20)
);

if (page.isEmpty()) {
    System.out.println("No customers on this page");
}

System.out.println(page.getTotalElements());
~~~

Với kết quả rỗng, output có thể là:

~~~text
No customers on this page
0
~~~

Page có thể cần thêm truy vấn COUNT để tính tổng số phần tử. Slice thường chỉ cần biết có phần tử tiếp theo hay không. Nếu không cần tổng số bản ghi, Slice có thể giảm chi phí.

Ví dụ Stream:

~~~java
@Transactional(readOnly = true)
public void printCustomers() {
    try (Stream<Customer> customers = repository.streamAllByActiveTrue()) {
        customers.forEach(customer ->
                System.out.println(customer.getDisplayName()));
    }
}
~~~

Stream repository phải được đóng để giải phóng tài nguyên; cách lấy dữ liệu có thể phụ thuộc provider/driver. Không trả Stream ra khỏi transaction đã kết thúc.

## 6. findById(), getReferenceById() và kết quả không tồn tại

Hai phương thức này có ngữ nghĩa khác nhau:

~~~java
Optional<Customer> customer = repository.findById(id);
~~~

findById() truy vấn theo khóa chính và trả Optional.empty() nếu không có entity.

~~~java
Customer customer = repository.getReferenceById(id);
~~~

getReferenceById() thường trả về một reference/proxy mà không nhất thiết tải dữ liệu ngay. Nếu khóa không tồn tại, lỗi EntityNotFoundException có thể chỉ xuất hiện khi proxy được truy cập. Vì vậy, không dùng getReferenceById() như một cách kiểm tra tồn tại.

Khi cần xác định có hay không, dùng findById() hoặc existsById():

~~~java
if (!repository.existsById(id)) {
    throw new CustomerNotFoundException(id);
}
~~~

Nếu cần dữ liệu entity ngay, findById() thường là lựa chọn rõ ràng hơn.

## 7. IncorrectResultSizeDataAccessException là gì?

IncorrectResultSizeDataAccessException thuộc Spring DAO exception hierarchy. Exception này biểu thị thao tác truy vấn yêu cầu một số lượng kết quả nhất định nhưng thực tế trả về số lượng khác.

Trong Spring Data JPA, trường hợp thường gặp là method có kiểu trả về đơn hoặc Optional nhưng JPQL/derived query trả nhiều hơn một dòng. JPA provider có thể phát hiện NonUniqueResultException; Spring chuyển lỗi persistence tương ứng sang exception thuộc hệ thống DataAccessException, thường là IncorrectResultSizeDataAccessException.

Ví dụ repository:

~~~java
Optional<Customer> findByDisplayName(String displayName);
~~~

Nếu database có hai khách hàng cùng displayName là "Alex", gọi:

~~~java
repository.findByDisplayName("Alex");
~~~

có thể ném:

~~~text
org.springframework.dao.IncorrectResultSizeDataAccessException
~~~

Đây là lỗi hợp đồng dữ liệu/truy vấn: method yêu cầu tối đa một kết quả nhưng điều kiện thực tế không duy nhất. Nó không đồng nghĩa với "không tìm thấy".

## 8. Phân biệt các lỗi liên quan tới số lượng kết quả

| Trường hợp | Exception hoặc kết quả thường gặp | Ý nghĩa |
|---|---|---|
| Repository Optional không có dòng | Optional.empty() | Không tìm thấy |
| Repository entity đơn không có dòng | null theo hợp đồng nullable | Không tìm thấy |
| JPA EntityManager.getSingleResult() không có dòng | NoResultException | Không tìm thấy khi dùng API JPA trực tiếp |
| Query đơn trả nhiều dòng | IncorrectResultSizeDataAccessException ở tầng Spring | Không thỏa hợp đồng một kết quả |
| JPA getSingleResult() trả nhiều dòng | NonUniqueResultException | Có nhiều kết quả |
| getReferenceById() trỏ tới ID không tồn tại | EntityNotFoundException có thể xuất hiện khi proxy được truy cập | Reference không hợp lệ |
| Insert trùng unique constraint | DataIntegrityViolationException hoặc exception tương ứng | Vi phạm ràng buộc dữ liệu khi ghi |

Spring Data repository thường xử lý trường hợp không có kết quả cho Optional/entity đơn theo kiểu trả về. Nếu dùng EntityManager trực tiếp, API getSingleResult() có thể ném NoResultException khi không có dòng. Đừng áp dụng hành vi của API JPA trực tiếp cho mọi repository method.

## 9. Nguyên nhân query trả nhiều kết quả ngoài dự kiến

Có nhiều lý do khiến method tưởng là duy nhất nhưng database trả nhiều dòng:

1. Điều kiện tìm kiếm không phải khóa duy nhất. Ví dụ displayName có thể trùng.
2. Thiếu unique constraint ở database dù code giả định email là duy nhất.
3. Dữ liệu cũ đã có duplicate trước khi thêm constraint.
4. JOIN tới collection tạo nhiều dòng cho cùng entity.
5. Query thiếu DISTINCT khi join association.
6. Derived query chỉ lọc theo một thuộc tính không duy nhất.
7. Method trả Optional<T> nhưng nghiệp vụ thực tế cho phép nhiều bản ghi.

Ví dụ join collection:

~~~java
@Query("""
       select c
       from Customer c
       join c.orders o
       where o.status = :status
       """)
List<Customer> findCustomersWithOrderStatus(
        @Param("status") OrderStatus status);
~~~

Một Customer có thể có nhiều Order cùng trạng thái, do đó join có thể tạo nhiều dòng kết quả cho cùng customer. Nếu muốn mỗi Customer chỉ xuất hiện một lần, dùng DISTINCT:

~~~java
@Query("""
       select distinct c
       from Customer c
       join c.orders o
       where o.status = :status
       """)
List<Customer> findDistinctCustomersWithOrderStatus(
        @Param("status") OrderStatus status);
~~~

Nếu query được khai báo trả Optional<Customer>, DISTINCT có thể loại duplicate của cùng entity nhưng vẫn có thể còn nhiều Customer khác nhau. DISTINCT không biến một truy vấn nhiều khách hàng thành truy vấn duy nhất.

## 10. Bảo đảm tính duy nhất ở database

Nếu nghiệp vụ quy định email là duy nhất, cần bảo vệ ở cả hai tầng:

- Java/domain: chuẩn hóa và kiểm tra định dạng.
- Database: unique constraint hoặc unique index.

Ví dụ entity:

~~~java
@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customers_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 200)
    private String email;

    @Column(nullable = false, length = 150)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Annotation mapping giúp mô tả constraint, nhưng schema production nên được quản lý bằng migration Flyway/Liquibase và xác minh constraint thực sự tồn tại.

Không chỉ kiểm tra trước khi insert:

~~~java
if (!repository.existsByEmail(email)) {
    repository.save(new Customer(email, name));
}
~~~

Đoạn code trên không bảo đảm duy nhất khi có hai request đồng thời: cả hai có thể cùng thấy email chưa tồn tại rồi cùng insert. Unique constraint ở database mới là lớp bảo vệ cuối cùng. Ứng dụng cần bắt lỗi vi phạm constraint và phản hồi phù hợp.

Nếu email không phân biệt hoa thường, cần xác định quy tắc chuẩn hóa/collation. Unique constraint trên cột thường có thể vẫn cho phép Alex@example.com và alex@example.com tùy database/collation. Có thể lưu giá trị chuẩn hóa hoặc tạo unique index trên biểu thức phù hợp với database.

## 11. Chọn đúng kiểu trả về cho nghiệp vụ

| Nhu cầu | Kiểu trả về / method phù hợp |
|---|---|
| Tìm theo khóa chính, có thể không tồn tại | Optional<T> với findById() |
| Tìm theo khóa nghiệp vụ đã bảo đảm duy nhất | Optional<T> |
| Tìm theo tên có thể trùng | List<T> |
| Chỉ cần biết có bản ghi hay không | boolean với existsBy... |
| Chỉ cần số lượng | long với countBy... |
| Muốn lấy một kết quả theo quy tắc rõ ràng | Optional<T> với First/Top và ORDER BY |
| Tải dữ liệu theo trang | Page<T> hoặc Slice<T> |
| Chỉ lấy vài trường | DTO/interface projection |

Ví dụ repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findAllByDisplayName(String displayName);

    Optional<Customer> findFirstByDisplayNameOrderByIdAsc(
            String displayName);

    boolean existsByEmail(String email);

    long countByDisplayName(String displayName);

    Page<Customer> findByDisplayNameContainingIgnoreCase(
            String keyword,
            Pageable pageable);
}
~~~

Không nên dùng findFirstBy... chỉ để che giấu duplicate ngoài dự kiến. Chỉ dùng First/Top khi nghiệp vụ thật sự cho phép chọn một phần tử theo thứ tự xác định, ví dụ bản ghi mới nhất hoặc bản ghi có ID nhỏ nhất.

## 12. First và Top: giới hạn kết quả có chủ đích

Spring Data hỗ trợ First và Top trong tên derived query:

~~~java
Optional<Customer> findFirstByDisplayNameOrderByIdAsc(
        String displayName);

List<Customer> findTop5ByActiveTrueOrderByCreatedAtDesc();
~~~

- First/Top giới hạn số dòng mà query trả về.
- Nếu không có kết quả, Optional rỗng hoặc List rỗng tùy kiểu trả về.
- Nếu nhiều dòng thỏa điều kiện, database chỉ trả số lượng giới hạn.
- Luôn thêm ORDER BY nếu cần biết bản ghi nào được chọn.

Không có ORDER BY, database không bảo đảm thứ tự dòng. Vì vậy, findFirstByDisplayName("Alex") không có quy tắc sắp xếp không thể bảo đảm luôn lấy cùng một khách hàng.

Top/First phù hợp với use case "lấy bản ghi mới nhất", "lấy 5 sản phẩm nổi bật theo điểm" hoặc "lấy một bản ghi theo thứ tự ưu tiên". Nó không thay thế unique constraint khi dữ liệu phải duy nhất.

## 13. Dùng existsBy và countBy thay vì tải entity

Nếu chỉ cần kiểm tra tồn tại, không cần tải toàn bộ entity:

~~~java
boolean existsByEmail(String email);
~~~

Nếu chỉ cần đếm:

~~~java
long countByDisplayName(String displayName);
~~~

Các query này thể hiện đúng ý định và thường hiệu quả hơn việc tải danh sách rồi gọi size(). Với tập dữ liệu lớn, tránh:

~~~java
List<Customer> customers = repository.findByActiveTrue();
long count = customers.size();
~~~

Hãy dùng countByActiveTrue() nếu chỉ cần số lượng.

Tuy nhiên, existsByEmail() không thay thế unique constraint trong thao tác ghi đồng thời. Nó chỉ trả lời trạng thái tại thời điểm truy vấn.

## 14. Scalar query, projection và giá trị null

Kết quả rỗng của một query trả entity khác với query chỉ chọn một cột nullable.

Ví dụ:

~~~java
@Query("select c.displayName from Customer c where c.email = :email")
Optional<String> findDisplayNameByEmail(@Param("email") String email);
~~~

Nếu không có Customer, Optional có thể empty. Nếu có Customer nhưng displayName là null, giá trị scalar cũng có thể được ánh xạ thành null/Optional.empty(). Vì vậy, Optional<String> có thể không phân biệt được hai trường hợp này.

Nếu cần phân biệt, trả DTO hoặc projection có cả ID và trường nullable:

~~~java
public record CustomerNameView(Long id, String displayName) {
}
~~~

~~~java
@Query("""
       select new com.example.customer.CustomerNameView(c.id, c.displayName)
       from Customer c
       where c.email = :email
       """)
Optional<CustomerNameView> findNameViewByEmail(
        @Param("email") String email);
~~~

ID không null cho biết entity tồn tại ngay cả khi displayName null.

## 15. Aggregate query khi không có dòng

Các hàm tổng hợp có quy tắc riêng:

| Hàm | Khi tập dữ liệu không có giá trị phù hợp |
|---|---|
| COUNT | Trả 0 |
| SUM | Thường trả null nếu không có giá trị để cộng |
| AVG | Thường trả null nếu không có giá trị để tính |
| MIN | Trả null nếu không có giá trị |
| MAX | Trả null nếu không có giá trị |

Ví dụ:

~~~java
@Query("select count(c) from Customer c where c.active = true")
long countActiveCustomers();

@Query("select coalesce(sum(o.total), 0) from PurchaseOrder o")
BigDecimal sumOrderTotalOrZero();
~~~

COUNT không cần COALESCE để đổi kết quả rỗng thành 0. SUM có thể cần COALESCE nếu hợp đồng nghiệp vụ muốn số 0 thay cho null.

Khi query có GROUP BY, nếu không có nhóm nào thì kết quả là collection rỗng; không nên nhầm với truy vấn aggregate không GROUP BY vốn có thể trả một dòng chứa null.

## 16. Xử lý lỗi ở service và API

Không nên bắt IncorrectResultSizeDataAccessException rồi trả Optional.empty() hoặc HTTP 404. Exception này báo rằng query yêu cầu một kết quả duy nhất nhưng dữ liệu trả về nhiều kết quả; đó là lỗi dữ liệu hoặc thiết kế truy vấn.

Ví dụ service:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Customer getByEmail(String email) {
        return repository.findByEmail(email)
                .orElseThrow(() -> new CustomerNotFoundException(email));
    }
}
~~~

Nếu findByEmail trả Optional.empty(), service có thể chuyển thành CustomerNotFoundException và API trả HTTP 404 theo quy ước của ứng dụng.

Nếu repository ném IncorrectResultSizeDataAccessException, hãy để lỗi được ghi nhận và xử lý như lỗi dữ liệu/truy vấn. Trong môi trường production, có thể dùng @ControllerAdvice để ánh xạ thành phản hồi lỗi chung phù hợp, ghi log và cảnh báo nhóm vận hành. Không trả chi tiết SQL hoặc dữ liệu nhạy cảm ra client.

Không nên dùng try/catch rộng để nuốt mọi DataAccessException. Điều đó có thể che giấu lỗi kết nối, lỗi constraint, lỗi mapping và lỗi truy vấn.

## 17. Ví dụ entity, repository và test đầy đủ

Entity Customer:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 200)
    private String email;

    @Column(nullable = false, length = 150)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Repository:

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    Optional<Customer> findByDisplayName(String displayName);

    List<Customer> findAllByDisplayName(String displayName);

    Optional<Customer> findFirstByDisplayNameOrderByIdAsc(
            String displayName);

    boolean existsByEmail(String email);
}
~~~

Lưu ý: email là duy nhất theo entity mapping, còn displayName không duy nhất. Vì vậy findByEmail phù hợp với Optional; findByDisplayName chỉ phù hợp với Optional nếu dữ liệu thực tế bảo đảm duy nhất. Ví dụ test tiếp theo cố ý tạo hai displayName giống nhau để minh họa lỗi.

Kiểm thử:

~~~java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.IncorrectResultSizeDataAccessException;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void optionalIsEmptyWhenNoCustomerMatches() {
        assertThat(repository.findByEmail("missing@example.com"))
                .isEmpty();
    }

    @Test
    void collectionIsEmptyWhenNoCustomerMatches() {
        assertThat(repository.findAllByDisplayName("Unknown"))
                .isEmpty();
    }

    @Test
    void singleResultMethodFailsWhenMultipleRowsMatch() {
        repository.saveAndFlush(
                new Customer("alex1@example.com", "Alex"));
        repository.saveAndFlush(
                new Customer("alex2@example.com", "Alex"));

        assertThatThrownBy(() -> repository.findByDisplayName("Alex"))
                .isInstanceOf(IncorrectResultSizeDataAccessException.class);
    }

    @Test
    void firstQueryUsesExplicitOrdering() {
        repository.saveAndFlush(
                new Customer("alex1@example.com", "Alex"));
        repository.saveAndFlush(
                new Customer("alex2@example.com", "Alex"));

        var result = repository.findFirstByDisplayNameOrderByIdAsc("Alex");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getEmail())
                .isEqualTo("alex1@example.com");
    }
}
~~~

Test đầu xác nhận Optional rỗng khi không tìm thấy. Test thứ hai xác nhận collection rỗng. Test thứ ba chứng minh method yêu cầu một kết quả duy nhất sẽ thất bại nếu có nhiều dòng phù hợp. Test cuối cho thấy First chỉ an toàn khi có thứ tự rõ ràng.

@DataJpaTest thường chạy trong transaction và rollback sau mỗi test. saveAndFlush() buộc gửi INSERT để constraint/query được kiểm tra sớm. Nếu muốn xác minh hành vi unique constraint trên database production, hãy chạy integration test với đúng hệ quản trị.

## 18. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Optional.empty() nhưng ứng dụng mong có dữ liệu | Điều kiện tìm kiếm sai hoặc dữ liệu không tồn tại | Kiểm tra tham số, chuẩn hóa dữ liệu và hợp đồng nghiệp vụ |
| IncorrectResultSizeDataAccessException | Method đơn trả nhiều dòng | Dùng List hoặc bảo đảm query/constraint là duy nhất |
| Optional được dùng cho tên có thể trùng | Kiểu trả về không phản ánh cardinality | Dùng List hoặc First/Top với ORDER BY theo nghiệp vụ |
| Dùng getReferenceById để kiểm tra tồn tại | Reference có thể chưa tải dữ liệu | Dùng findById hoặc existsById |
| Query join trả duplicate entity | Một entity có nhiều dòng association khớp | Dùng DISTINCT nếu mục tiêu là entity duy nhất |
| Dùng DISTINCT nhưng vẫn có nhiều entity | Có nhiều entity khác nhau cùng thỏa điều kiện | Chọn List hoặc thiết kế điều kiện duy nhất |
| Bắt exception rồi trả empty | Che giấu dữ liệu duplicate | Sửa query/constraint và ghi nhận lỗi |
| existsBy trước insert vẫn bị trùng | Hai request đồng thời cùng kiểm tra | Dùng unique constraint và xử lý lỗi ghi |
| Scalar Optional không phân biệt row-null với no-row | Cột SELECT có thể null | Trả DTO có ID hoặc thêm trường không null |
| Page rỗng nhưng total không như mong đợi | Count query hoặc filter khác với query nội dung | Kiểm tra count query và predicate |
| Kết quả First thay đổi giữa lần chạy | Không có ORDER BY xác định | Thêm thứ tự sắp xếp ổn định |

## 19. Checklist tự đánh giá

- [ ] Phân biệt được 0, 1 và nhiều kết quả.
- [ ] Chọn Optional<T> cho query tối đa một kết quả.
- [ ] Hiểu entity đơn có thể trả null khi không có kết quả.
- [ ] Dùng List/Page/Slice cho query nhiều kết quả.
- [ ] Biết Page rỗng có totalElements bằng 0 và Slice rỗng không có trang tiếp theo.
- [ ] Phân biệt findById() với getReferenceById().
- [ ] Giải thích được IncorrectResultSizeDataAccessException.
- [ ] Phân biệt lỗi không tìm thấy với lỗi có nhiều kết quả.
- [ ] Xác định nguyên nhân duplicate do điều kiện không duy nhất hoặc join collection.
- [ ] Dùng DISTINCT đúng mục tiêu và hiểu nó không bảo đảm chỉ còn một entity.
- [ ] Dùng unique constraint để bảo vệ khóa nghiệp vụ.
- [ ] Không dựa vào existsBy để chống race condition khi insert.
- [ ] Dùng First/Top với ORDER BY xác định khi nghiệp vụ cho phép chọn một dòng.
- [ ] Phân biệt kết quả aggregate rỗng với collection rỗng.
- [ ] Kiểm thử 0, 1 và nhiều kết quả bằng @DataJpaTest.
- [ ] Không chuyển IncorrectResultSizeDataAccessException thành "not found".

## 20. Kết luận

Kết quả rỗng là một trường hợp bình thường của truy vấn và cần được biểu diễn theo kiểu trả về: Optional.empty(), null theo hợp đồng nullable, collection rỗng hoặc Page/Slice rỗng. Khi query yêu cầu một kết quả duy nhất nhưng database trả nhiều dòng, Spring Data JPA có thể ném IncorrectResultSizeDataAccessException.

Hãy chọn kiểu trả về theo cardinality thực tế, dùng unique constraint cho dữ liệu cần duy nhất, kiểm tra JOIN có tạo duplicate hay không và chỉ dùng First/Top khi có quy tắc sắp xếp rõ ràng. Xử lý đúng các trường hợp này giúp service phân biệt rõ "không tìm thấy" với "dữ liệu không nhất quán", từ đó API và hệ thống dễ dự đoán hơn.
