# IgnoreCase, AllIgnoreCase và tác động đến chỉ mục

Spring Data JPA hỗ trợ truy vấn không phân biệt chữ hoa/chữ thường thông qua các từ khóa IgnoreCase và AllIgnoreCase trong tên phương thức Repository. Chúng thường được dùng khi tìm tên, email hoặc mã văn bản mà người dùng có thể nhập với cách viết hoa/thường khác nhau.

Ví dụ:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);
~~~

Phương thức này yêu cầu so sánh email không phân biệt hoa thường theo cơ chế truy vấn của provider và database. Tuy nhiên, tính tiện lợi này có thể ảnh hưởng đến khả năng sử dụng index. Nếu SQL sinh ra áp dụng hàm như UPPER() hoặc LOWER() lên cột, index B-tree thông thường trên cột gốc có thể không được dùng hiệu quả. Vì vậy, cần hiểu cả cú pháp truy vấn, collation của database và kế hoạch thực thi.

## 1. IgnoreCase là gì?

IgnoreCase là từ khóa của Spring Data query derivation, cho phép yêu cầu so sánh một thuộc tính kiểu String không phân biệt chữ hoa/chữ thường.

Ví dụ Entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String firstName;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {
    }

    public Customer(String firstName, String email) {
        this.firstName = firstName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);
}
~~~

Với dữ liệu có email là User@example.com, truy vấn theo user@EXAMPLE.COM có thể tìm được cùng bản ghi khi database/provider thực thi phép so sánh không phân biệt hoa thường theo mapping đó.

IgnoreCase áp dụng cho thuộc tính văn bản phù hợp. Không có ý nghĩa khi áp dụng cho thuộc tính số, ngày giờ hoặc boolean. Tên thuộc tính trong phương thức vẫn phải đúng với thuộc tính Java của Entity.

## 2. Cách viết IgnoreCase trong tên phương thức

IgnoreCase có thể đặt sau thuộc tính cần so sánh:

~~~java
Optional<Customer> findByFirstNameIgnoreCase(String firstName);
~~~

Có thể kết hợp với các điều kiện khác:

~~~java
Optional<Customer> findByEmailIgnoreCaseAndId(
        String email,
        Long id
);
~~~

Trong ví dụ này, phép so sánh email không phân biệt hoa thường; phép so sánh id vẫn là so sánh số bình thường.

Có thể dùng IgnoreCase với các toán tử chuỗi như:

~~~java
List<Customer> findByFirstNameContainingIgnoreCase(String keyword);

List<Customer> findByFirstNameStartingWithIgnoreCase(String prefix);

List<Customer> findByFirstNameEndingWithIgnoreCase(String suffix);
~~~

Ý nghĩa:

- ContainingIgnoreCase: tìm chuỗi con không phân biệt hoa thường.
- StartingWithIgnoreCase: tìm giá trị bắt đầu bằng tiền tố không phân biệt hoa thường.
- EndingWithIgnoreCase: tìm giá trị kết thúc bằng hậu tố không phân biệt hoa thường.

Các phương thức này thường tương ứng với phép so sánh LIKE có wildcard. Cách biểu diễn SQL chính xác phụ thuộc phiên bản Spring Data, Hibernate và database.

## 3. AllIgnoreCase là gì?

AllIgnoreCase (còn có alias AllIgnoringCase) yêu cầu áp dụng so sánh không phân biệt hoa thường cho tất cả thuộc tính phù hợp trong predicate của phương thức truy vấn.

Ví dụ:

~~~java
List<Customer> findByFirstNameAndEmailAllIgnoreCase(
        String firstName,
        String email
);
~~~

Cả firstName và email đều được so sánh không phân biệt hoa thường.

So sánh với cách viết từng thuộc tính:

~~~java
List<Customer> findByFirstNameIgnoreCaseAndEmailIgnoreCase(
        String firstName,
        String email
);
~~~

Hai cách trên diễn đạt cùng mục đích đối với các thuộc tính String phù hợp.

### Khi nào dùng IgnoreCase, khi nào dùng AllIgnoreCase?

| Cú pháp | Phạm vi |
|---|---|
| findByEmailIgnoreCase | Chỉ email |
| findByFirstNameIgnoreCaseAndEmail | Chỉ firstName |
| findByFirstNameAndEmailAllIgnoreCase | Tất cả thuộc tính String phù hợp trong predicate |
| findByFirstNameIgnoreCaseAndEmailIgnoreCase | Cả hai trường được chỉ định rõ |

AllIgnoreCase không có nghĩa là chuyển mọi kiểu dữ liệu thành chuỗi hoặc bỏ qua phân biệt cho toàn bộ Entity. Nó áp dụng cho các thuộc tính phù hợp, chủ yếu là String. Các thuộc tính không hỗ trợ so sánh case-insensitive vẫn được xử lý theo kiểu và toán tử tương ứng.

Nếu phương thức có nhiều điều kiện, hãy đọc tên phương thức và kiểm tra query derivation để chắc chắn phạm vi IgnoreCase đúng như mong muốn. Khi tên phương thức trở nên dài và khó đọc, có thể dùng @Query để thể hiện rõ điều kiện.

## 4. Spring Data JPA có thể tạo SQL như thế nào?

Để thực hiện so sánh không phân biệt hoa thường, provider thường chuẩn hóa hai phía của phép so sánh bằng một hàm như UPPER() hoặc LOWER().

Ví dụ phương thức:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);
~~~

SQL minh họa có thể có dạng:

~~~sql
SELECT c.*
FROM customers c
WHERE UPPER(c.email) = UPPER(?);
~~~

Đây là dạng SQL minh họa, không phải cam kết chính xác về câu SQL của mọi phiên bản/provider. Hibernate có thể chọn UPPER hoặc cách biểu diễn khác dựa trên dialect và cấu hình.

Với truy vấn chứa chuỗi:

~~~java
List<Customer> findByFirstNameContainingIgnoreCase(String keyword);
~~~

SQL có thể tương tự:

~~~sql
SELECT c.*
FROM customers c
WHERE UPPER(c.first_name) LIKE UPPER(?);
~~~

Tham số được dùng cùng wildcard để tìm chuỗi con. Hãy bật SQL logging trong môi trường phát triển hoặc dùng datasource proxy để quan sát câu SQL và giá trị bind thực tế.

## 5. Vì sao IgnoreCase có thể ảnh hưởng đến index?

Giả sử bảng customers có index B-tree thông thường:

~~~sql
CREATE INDEX idx_customers_email
ON customers (email);
~~~

Một truy vấn so sánh trực tiếp:

~~~sql
SELECT *
FROM customers
WHERE email = ?;
~~~

có thể sử dụng index trên email nếu bộ tối ưu truy vấn thấy phù hợp.

Nhưng truy vấn IgnoreCase có thể được biểu diễn như:

~~~sql
WHERE UPPER(email) = UPPER(?)
~~~

Lúc này, database phải so sánh kết quả của biểu thức UPPER(email). Index trên giá trị email gốc không nhất thiết chứa các giá trị đã biến đổi bằng UPPER(). Do đó, index thông thường có thể không được dùng hoặc không hiệu quả cho điều kiện này.

Hệ quả có thể gặp:

- Database phải tính hàm trên nhiều dòng.
- Execution plan có thể chuyển sang scan nhiều dữ liệu.
- CPU và I/O tăng khi bảng lớn.
- Độ trễ truy vấn tăng khi số lượng bản ghi hoặc tần suất tìm kiếm tăng.

Tuy nhiên, không nên kết luận rằng mọi IgnoreCase luôn gây full table scan. Optimizer, collation, kiểu index, statistics và database engine có thể thay đổi lựa chọn. Cần xem execution plan thực tế.

## 6. Functional index hoặc expression index

Một giải pháp là tạo index trên đúng biểu thức được dùng trong điều kiện truy vấn.

Nếu SQL thực tế dùng UPPER(email), có thể tạo expression index trên UPPER(email) ở các database hỗ trợ:

~~~sql
CREATE INDEX idx_customers_email_upper
ON customers (UPPER(email));
~~~

Khi truy vấn có điều kiện tương thích:

~~~sql
WHERE UPPER(email) = UPPER(?)
~~~

database có thể sử dụng index biểu thức này.

Ví dụ trên là cú pháp phổ biến của PostgreSQL và một số hệ quản trị hỗ trợ function-based/expression index. Cú pháp và khả năng hỗ trợ khác nhau theo database. Cần kiểm tra tài liệu của engine đang dùng.

Điểm cần chú ý:

- Biểu thức trong index phải tương thích với biểu thức trong truy vấn.
- Nếu provider dùng LOWER(email) mà index chỉ tạo trên UPPER(email), database có thể không sử dụng index đó.
- Khi thay đổi dialect hoặc provider, SQL sinh ra có thể thay đổi.
- Index biểu thức làm tăng chi phí INSERT, UPDATE và DELETE vì database phải duy trì index.
- Nếu email thay đổi thường xuyên, cần cân nhắc chi phí ghi so với lợi ích tìm kiếm.

Không tạo index chỉ vì có phương thức IgnoreCase. Hãy đo execution plan và workload trước khi quyết định.

## 7. Collation không phân biệt hoa thường

Một cách khác là sử dụng collation hoặc kiểu cột có quy tắc so sánh không phân biệt hoa thường do database cung cấp.

Collation quyết định cách so sánh và sắp xếp chuỗi. Một số database hỗ trợ collation case-insensitive ở cấp database, cột hoặc biểu thức. Khi cột đã có collation phù hợp, phép so sánh trực tiếp có thể không cần bọc hàm UPPER/LOWER.

Tuy nhiên:

- Collation là đặc tính của database, không phải tính năng portable của JPA.
- Tên và cú pháp collation khác nhau giữa PostgreSQL, MySQL, SQL Server và các hệ quản trị khác.
- Một số collation còn ảnh hưởng đến dấu, ký tự Unicode và thứ tự sắp xếp.
- Index cần được tạo với collation tương thích với phép so sánh.
- Nếu đổi collation, cần kiểm tra unique constraint và dữ liệu hiện có.

Nếu database đã thực hiện so sánh case-insensitive theo collation, hãy xác định liệu IgnoreCase còn cần thiết không. Tránh vô tình áp dụng nhiều lớp chuẩn hóa làm query khó tận dụng index.

## 8. Chuẩn hóa giá trị trong một cột riêng

Một chiến lược khác là lưu giá trị gốc và một giá trị chuẩn hóa để tìm kiếm.

Ví dụ:

- email: giữ cách viết người dùng cung cấp.
- normalizedEmail: lưu email đã chuẩn hóa theo quy tắc nghiệp vụ.
- Tạo unique index hoặc index thường trên normalizedEmail.
- Khi ghi, cập nhật hai trường cùng một quy tắc.
- Khi tìm, so sánh trực tiếp normalizedEmail với giá trị đã chuẩn hóa từ đầu vào.

Entity:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String email;

    @Column(nullable = false, unique = true)
    private String normalizedEmail;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
        this.normalizedEmail = normalizeEmail(email);
    }

    private static String normalizeEmail(String value) {
        return value.trim().toLowerCase(Locale.ROOT);
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByNormalizedEmail(String normalizedEmail);
}
~~~

Service có thể chuẩn hóa đầu vào bằng cùng quy tắc trước khi gọi Repository.

Lưu ý: ví dụ này minh họa quy tắc chuẩn hóa đơn giản. Email có quy tắc so sánh riêng theo domain và phần local-part; không nên tự ý thay đổi mọi địa chỉ email bằng lowercase nếu hệ thống cần tuân thủ đầy đủ semantics của email. Hãy định nghĩa rõ quy tắc canonicalization cho dữ liệu nghiệp vụ, áp dụng thống nhất khi tạo, cập nhật, import và tìm kiếm.

Ưu điểm của cột chuẩn hóa:

- Truy vấn có thể dùng index B-tree thông thường trên cột normalized.
- Quy tắc chuẩn hóa được thể hiện rõ ở tầng ứng dụng.
- Có thể tạo unique constraint không phân biệt hoa thường theo quy tắc đã chọn.

Nhược điểm:

- Phải duy trì đồng bộ hai giá trị.
- Cần migration để backfill dữ liệu cũ.
- Cần bảo đảm mọi luồng ghi đều áp dụng cùng quy tắc.
- Tốn thêm dung lượng và có nguy cơ dữ liệu gốc với dữ liệu chuẩn hóa bị lệch.

## 9. IgnoreCase và tìm kiếm chứa chuỗi

Không phải mọi dạng tìm kiếm không phân biệt hoa thường đều có cùng chi phí index.

| Phương thức | Mẫu điều kiện thường gặp | Khả năng dùng B-tree thông thường |
|---|---|---|
| findByNameIgnoreCase | UPPER(name) = UPPER(?) | Cột gốc có thể không phù hợp; expression index có thể hữu ích |
| findByNameStartingWithIgnoreCase | UPPER(name) LIKE UPPER('abc%') | Có thể dùng index trong một số điều kiện/dialect |
| findByNameEndingWithIgnoreCase | UPPER(name) LIKE UPPER('%abc') | Thường khó dùng B-tree |
| findByNameContainingIgnoreCase | UPPER(name) LIKE UPPER('%abc%') | Thường không phù hợp với B-tree thông thường |

Wildcard đầu chuỗi như %abc hoặc %abc% làm cho việc tìm kiếm bằng B-tree khó hơn vì database không thể định vị một khoảng tiền tố liên tục theo cách thông thường.

Với PostgreSQL, tìm chuỗi con có thể cần extension/index chuyên biệt như pg_trgm và GIN/GiST. Với database khác, có thể dùng full-text search, computed column, collation hoặc cơ chế tìm kiếm riêng. Đây là lựa chọn đặc thù database, không được tự động tạo chỉ bằng IgnoreCase.

Nếu yêu cầu tìm kiếm phức tạp, cần xác định rõ:
- Tìm bằng chính xác hay tìm một phần?
- Có cần bỏ dấu tiếng Việt không?
- Có cần chuẩn hóa khoảng trắng hoặc ký tự Unicode không?
- Có cần tìm theo tiền tố hay chứa chuỗi ở bất kỳ vị trí nào?
- Khối lượng dữ liệu và số truy vấn đồng thời là bao nhiêu?

IgnoreCase chỉ giải quyết khác biệt chữ hoa/thường theo cách provider/database thực thi. Nó không tự bỏ dấu, bỏ dấu câu, chuẩn hóa khoảng trắng hay xử lý mọi biến thể Unicode.

## 10. Phân biệt case-insensitive search và uniqueness

Tìm kiếm không phân biệt hoa thường và bảo đảm duy nhất không phân biệt hoa thường là hai yêu cầu riêng.

Ví dụ ứng dụng có thể cho phép:

- Tìm customer bằng EMAIL@example.com và email@example.com như cùng một kết quả.
- Không cho phép hai tài khoản có cùng email theo quy tắc so sánh không phân biệt hoa thường.

Chỉ có phương thức:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);
~~~

không bảo đảm database ngăn dữ liệu trùng. Hai transaction đồng thời vẫn có thể cùng kiểm tra chưa tồn tại rồi cùng insert hai giá trị khác cách viết hoa/thường.

Muốn bảo đảm uniqueness, cần constraint/index ở database theo cùng quy tắc chuẩn hóa hoặc collation. Ví dụ nếu dùng cột normalizedEmail, có thể tạo unique index trên cột đó. Ứng dụng vẫn cần xử lý lỗi vi phạm unique constraint vì kiểm tra trước khi insert không loại bỏ race condition.

## 11. Kiểm tra execution plan và SQL thực tế

Khi bảng nhỏ, khác biệt hiệu năng có thể chưa rõ. Khi dữ liệu lớn, hãy kiểm tra query plan.

Quy trình:

1. Bật SQL logging ở môi trường phát triển để biết Hibernate sinh UPPER(), LOWER() hay collation expression nào.
2. Xác nhận giá trị bind và kiểu JDBC.
3. Chạy EXPLAIN hoặc công cụ execution plan của database.
4. Kiểm tra database dùng index hay scan.
5. Đo thời gian với dữ liệu có kích thước gần production.
6. So sánh trước và sau khi thêm expression index hoặc cột chuẩn hóa.
7. Kiểm tra cả chi phí ghi và dung lượng index.

Không dựa vào log SQL duy nhất để kết luận hiệu năng. Cùng một câu SQL có thể có execution plan khác nhau theo statistics, dữ liệu, parameter, phiên bản database và cấu hình optimizer.

## 12. Kiểm thử hành vi IgnoreCase trên database mục tiêu

Một repository test cơ bản:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void findsEmailIgnoringCase() {
        repository.save(
                new Customer("User@example.com")
        );

        Optional<Customer> result =
                repository.findByEmailIgnoreCase(
                        "user@EXAMPLE.COM"
                );

        assertTrue(result.isPresent());
    }
}
~~~

Test trên minh họa mong muốn về chức năng, nhưng để xác nhận đúng hành vi production, nên chạy với cùng database engine và collation như môi trường triển khai. H2 có thể khác PostgreSQL hoặc MySQL về collation, Unicode và cách tối ưu biểu thức.

Nếu ứng dụng dùng expression index hoặc cột normalized, integration test nên xác nhận cả:
- Truy vấn trả đúng kết quả với các biến thể chữ hoa/thường.
- Unique constraint từ chối giá trị trùng theo quy tắc.
- Migration tạo index/column đúng.
- Query plan sử dụng index khi workload đủ lớn và optimizer thấy có lợi.

## 13. Những lỗi thường gặp

**Dùng IgnoreCase rồi kỳ vọng index thường vẫn được dùng**

Nếu SQL bọc cột bằng UPPER/LOWER, index trên giá trị gốc có thể không khớp. Hãy xem query plan và cân nhắc expression index, collation hoặc cột chuẩn hóa.

**Nhầm AllIgnoreCase với mọi thuộc tính đều bỏ qua phân biệt**

AllIgnoreCase áp dụng cho các thuộc tính phù hợp, chủ yếu là String trong predicate; nó không biến số, ngày giờ hoặc boolean thành so sánh không phân biệt hoa thường.

**Chỉ kiểm tra trùng ở tầng ứng dụng**

Hai transaction đồng thời có thể vượt qua bước kiểm tra trước khi insert. Dùng unique constraint/index ở database theo cùng quy tắc chuẩn hóa.

**Chuẩn hóa không thống nhất**

Nếu lúc ghi dùng lowercase nhưng lúc tìm dùng trim hoặc Unicode normalization khác, có thể bỏ sót bản ghi. Tạo một hàm chuẩn hóa duy nhất và dùng ở mọi đường ghi/đọc.

**Bỏ qua Unicode và collation**

String.toLowerCase() theo locale mặc định có thể cho kết quả khác theo môi trường. Nếu dùng quy tắc chuẩn hóa ở Java, cần xác định locale và semantics rõ ràng; Locale.ROOT thường phù hợp hơn cho quy tắc kỹ thuật không phụ thuộc ngôn ngữ, nhưng không thay thế đầy đủ collation của database.

**Dùng ContainingIgnoreCase cho bảng rất lớn mà không có chiến lược tìm kiếm**

Tìm chuỗi con với wildcard hai phía thường không tận dụng B-tree thông thường. Cần chọn full-text, trigram hoặc cơ chế tìm kiếm chuyên biệt theo database.

## 14. Kết luận

IgnoreCase và AllIgnoreCase giúp Spring Data JPA tạo truy vấn so sánh văn bản không phân biệt hoa/thường. IgnoreCase áp dụng cho thuộc tính được chỉ định; AllIgnoreCase áp dụng cho các thuộc tính phù hợp trong predicate. Cách triển khai thường dùng UPPER/LOWER hoặc phụ thuộc collation, vì vậy có thể ảnh hưởng đến index. Với bảng lớn, hãy kiểm tra SQL và execution plan, rồi cân nhắc expression index, collation case-insensitive hoặc cột chuẩn hóa có unique constraint. IgnoreCase không tự giải quyết tìm kiếm bỏ dấu, chuẩn hóa Unicode hay bảo đảm dữ liệu duy nhất.
