# Ký tự đại diện, escaping và khác biệt khi truyền null trong truy vấn Spring Data JPA

Khi tìm kiếm theo tên, ứng dụng thường cần hỗ trợ một phần chuỗi, ví dụ tìm tất cả khách hàng có tên chứa "An". Trong SQL và JPQL, toán tử LIKE dùng hai ký tự đại diện quan trọng: dấu phần trăm (%) khớp với không hoặc nhiều ký tự, còn dấu gạch dưới (_) khớp với đúng một ký tự. Người dùng có thể muốn tìm chính ký tự % hoặc _, trong khi database lại hiểu chúng là mẫu tìm kiếm.

Một vấn đề khác là giá trị null. Điều kiện so sánh với null trong SQL không giống so sánh bằng một giá trị thông thường. Spring Data JPA có quy tắc riêng cho derived query, còn truy vấn @Query cần thể hiện rõ cách xử lý null. Bài học này giải thích LIKE, escaping, null, chuỗi rỗng, cách viết repository an toàn và cách kiểm thử các trường hợp biên.

## 1. LIKE và hai ký tự đại diện chuẩn

LIKE dùng một mẫu để so khớp chuỗi:

- % khớp với không, một hoặc nhiều ký tự.
- _ khớp với đúng một ký tự.
- ESCAPE chỉ định một ký tự dùng để vô hiệu hóa ý nghĩa đại diện của % hoặc _ trong mẫu.

Ví dụ với cột name:

| Điều kiện | Giá trị khớp ví dụ | Giải thích |
|---|---|---|
| name LIKE 'An%' | An, Anh, Anna | Bắt đầu bằng An |
| name LIKE '%An' | An, Minh An | Kết thúc bằng An |
| name LIKE '%An%' | An, Thanh An, An Nguyen | Chứa An |
| name LIKE 'A_' | An, Ax | A và đúng một ký tự |
| name LIKE 'A__' | Anh, Amy | A và đúng hai ký tự |

Mẫu LIKE có thể chứa ký tự đại diện ở bất kỳ vị trí nào. Ví dụ '%a_b%' tìm chuỗi có chữ a, tiếp theo là một ký tự bất kỳ, rồi đến b.

LIKE không tự động có nghĩa là tìm kiếm không phân biệt hoa thường. Điều đó phụ thuộc collation của database hoặc cách truy vấn được viết. Spring Data JPA cung cấp hậu tố IgnoreCase cho derived query; với @Query, có thể dùng lower() hoặc upper() nếu cần quy tắc rõ ràng.

## 2. Escaping ký tự đại diện là gì?

Giả sử người dùng nhập tên tìm kiếm là "A%". Nếu truy vấn tạo mẫu '%A%%', dấu % do người dùng nhập được hiểu là wildcard và có thể khớp rất nhiều tên. Nếu mục tiêu là tìm chuỗi có đúng ký tự phần trăm, cần escape dấu %.

Ví dụ SQL dùng dấu chấm than làm ký tự escape:

~~~sql
SELECT *
FROM customers
WHERE name LIKE '%A!%%' ESCAPE '!';
~~~

Dấu ! trước dấu % khiến dấu % đó được hiểu là ký tự thông thường. Hai dấu % ở đầu và cuối vẫn là wildcard do ứng dụng thêm vào.

Tương tự, nếu muốn tìm dấu gạch dưới:

~~~sql
SELECT *
FROM customers
WHERE name LIKE '%A!_%' ESCAPE '!';
~~~

Cú pháp literal của ký tự escape có thể khác giữa SQL, Java string và cấu hình database. Ví dụ trên minh họa ý nghĩa SQL; khi viết trong Java cần chú ý thêm quy tắc escaping của chuỗi nguồn.

## 3. Derived query của Spring Data JPA và LIKE

Spring Data JPA hỗ trợ các từ khóa tạo truy vấn LIKE từ tên phương thức:

| Từ khóa | Ý nghĩa | Ví dụ |
|---|---|---|
| Containing / Contains | Tìm chuỗi con | findByNameContaining |
| StartingWith | Tìm chuỗi bắt đầu bằng giá trị | findByNameStartingWith |
| EndingWith | Tìm chuỗi kết thúc bằng giá trị | findByNameEndingWith |
| Like | Dùng mẫu LIKE được truyền vào | findByNameLike |
| NotLike | Phủ định mẫu LIKE | findByNameNotLike |
| IgnoreCase | So sánh không phân biệt hoa thường | findByNameContainingIgnoreCase |

Ví dụ repository:

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByName(String name);

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    List<Customer> findByNameLike(String pattern);
}
~~~

Với Containing, StartingWith và EndingWith, Spring Data tự thêm wildcard cần thiết vào tham số. Ví dụ:

~~~java
repository.findByNameContaining("Lan");
repository.findByNameStartingWith("Ng");
repository.findByNameEndingWith("Anh");
~~~

Framework tạo các mẫu LIKE có dạng chứa, bắt đầu bằng hoặc kết thúc bằng giá trị truyền vào. Bạn không cần tự thêm % vào tham số cho ba phương thức này.

Một đặc điểm quan trọng của derived query LIKE là Spring Data JPA escape các ký tự wildcard chuẩn do người dùng truyền vào trong tham số, để % và _ trong giá trị tìm kiếm được hiểu theo nghĩa literal. Ký tự escape được cấu hình cho repository. Vì vậy, phương thức Containing thường phù hợp khi người dùng muốn tìm một đoạn văn bản chính xác, kể cả khi đoạn đó chứa % hoặc _.

Ngược lại, phương thức có hậu tố Like nhận một mẫu LIKE. Khi dùng Like, ứng dụng đang chủ động truyền mẫu truy vấn; hãy xác định rõ liệu wildcard trong tham số được phép mang ý nghĩa tìm kiếm hay cần được escape.

## 4. Khác biệt giữa Containing và Like

Hai phương thức sau có ý nghĩa khác nhau:

~~~java
List<Customer> findByNameContaining(String text);

List<Customer> findByNameLike(String pattern);
~~~

Containing tự tạo mẫu tìm chuỗi con và escape wildcard chuẩn trong giá trị đầu vào. Ví dụ truyền "A%" có nghĩa tìm tên chứa hai ký tự A và % theo nghĩa literal.

Like dùng mẫu do ứng dụng truyền vào. Ví dụ:

~~~java
repository.findByNameLike("A%");
~~~

Mẫu "A%" có nghĩa tên bắt đầu bằng A và theo sau là không hoặc nhiều ký tự. Nếu muốn tìm đúng chuỗi có dấu %, cần tạo mẫu đã escape theo ký tự ESCAPE mà truy vấn sử dụng.

Đừng thêm % thủ công vào tham số Containing:

~~~java
// Không nên: Containing đã thêm wildcard hai phía.
repository.findByNameContaining("%Lan%");
~~~

Các dấu % do người dùng nhập được xử lý như ký tự literal theo quy tắc derived query, còn framework vẫn thêm wildcard ngoài. Nếu muốn truyền mẫu LIKE hoàn chỉnh, hãy dùng phương thức Like và kiểm soát escaping rõ ràng.

## 5. Cấu hình ký tự escape cho repository

Spring Data JPA cho phép cấu hình ký tự escape trong @EnableJpaRepositories thông qua thuộc tính escapeCharacter. Ký tự mặc định là dấu gạch chéo ngược.

Có thể cấu hình rõ ràng một ký tự khác, ví dụ dấu chấm than:

~~~java
package com.example.customer;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

@Configuration
@EnableJpaRepositories(escapeCharacter = '!')
public class RepositoryConfiguration {
}
~~~

Thông thường không cần cấu hình lại nếu ký tự mặc định đáp ứng nhu cầu. Chỉ thay đổi khi dự án có quy ước escaping thống nhất hoặc cần tránh xung đột với dữ liệu đầu vào. Ký tự được chọn phải phù hợp với mệnh đề ESCAPE của database.

## 6. Viết @Query với LIKE và escaping an toàn

Khi dùng @Query, bạn tự định nghĩa mẫu LIKE. Nếu đặt wildcard mà không escape dữ liệu, ký tự % và _ trong tham số có thể thay đổi ý nghĩa tìm kiếm.

Spring Data JPA cung cấp hàm SpEL escape(String) trong query để escape hai wildcard chuẩn SQL/JPQL là % và _. Hàm escapeCharacter() trả về ký tự escape đang cấu hình cho repository.

Ví dụ tìm tên có chứa đoạn nhập vào theo nghĩa literal:

~~~java
@Query("""
       select c
       from Customer c
       where c.name like %?#{escape([0])}% escape ?#{escapeCharacter()}
       """)
List<Customer> findNameContainingLiteral(String fragment);
~~~

Cách hoạt động:

1. [0] là tham số thứ nhất của phương thức.
2. escape([0]) escape các wildcard chuẩn % và _ trong giá trị người dùng.
3. Hai dấu % nằm ngoài biểu thức SpEL do ứng dụng thêm để tìm chuỗi con.
4. escapeCharacter() cung cấp ký tự được dùng trong mệnh đề ESCAPE.

Hàm escape của Spring Data chỉ xử lý các wildcard chuẩn SQL/JPQL là % và _. Nó không xử lý mọi ký tự đặc biệt riêng của từng database. Nếu database có cú pháp pattern bổ sung, cần kiểm tra tài liệu database và thiết kế quy tắc phù hợp.

Có thể kết hợp IgnoreCase bằng lower():

~~~java
@Query("""
       select c
       from Customer c
       where lower(c.name)
             like lower(concat('%', ?#{escape([0])}, '%'))
             escape ?#{escapeCharacter()}
       """)
List<Customer> findNameContainingIgnoreCaseLiteral(String fragment);
~~~

Câu truy vấn dùng concat để thêm wildcard do ứng dụng kiểm soát; giá trị tham số đã được escape trước khi đưa vào mẫu.

Không nối dữ liệu người dùng trực tiếp vào JPQL hoặc SQL. Dùng bind parameter và cơ chế escaping phù hợp. Bind parameter giúp chống SQL injection; escaping wildcard giải quyết một vấn đề khác là ý nghĩa của mẫu LIKE. Cả hai đều cần được hiểu đúng.

Lưu ý thêm: hàm escape() được thiết kế để xử lý wildcard chuẩn % và _, không phải mọi ký tự đặc biệt riêng của database. Nếu người dùng có thể nhập chính ký tự escape đã chọn, hãy kiểm tra và định nghĩa cách xử lý ký tự đó; không giả định hàm escape() xử lý mọi trường hợp đặc biệt.

## 7. Null trong SQL và JPQL

SQL dùng logic ba giá trị: TRUE, FALSE và UNKNOWN. Khi so sánh một giá trị với NULL bằng toán tử = hoặc <>, kết quả là UNKNOWN, không phải TRUE hoặc FALSE.

Ví dụ:

~~~sql
SELECT *
FROM customers
WHERE name = NULL;
~~~

Truy vấn này không tìm được các dòng có name NULL. Cách đúng là:

~~~sql
SELECT *
FROM customers
WHERE name IS NULL;
~~~

Tương tự:

~~~sql
SELECT *
FROM customers
WHERE name IS NOT NULL;
~~~

Trong JPQL, quy tắc tương tự:

~~~java
select c from Customer c where c.name is null
~~~

~~~java
select c from Customer c where c.name is not null
~~~

Vì vậy, đừng viết điều kiện name = :name rồi kỳ vọng truyền null sẽ tự chuyển thành IS NULL trong mọi loại truy vấn. Cần phân biệt derived query do Spring Data tạo với JPQL bạn tự viết.

## 8. Truyền null vào derived query

Với derived query dùng phép so sánh bằng, Spring Data JPA diễn giải tham số null thành điều kiện IS NULL.

Ví dụ:

~~~java
Optional<Customer> findByName(String name);
~~~

Khi gọi:

~~~java
repository.findByName(null);
~~~

Điều kiện được tạo tương ứng với name IS NULL. Điều này khác với JPQL viết tay có name = :name, nơi bind null vẫn là phép so sánh bằng null theo logic SQL và không trả về các dòng null.

Để thể hiện ý định rõ ràng, có thể khai báo phương thức riêng:

~~~java
List<Customer> findByNameIsNull();

List<Customer> findByNameIsNotNull();
~~~

Các phương thức này dễ đọc và không phụ thuộc người gọi có nhớ truyền null hay không.

Không suy rộng quy tắc này cho mọi từ khóa truy vấn. LIKE, Containing, Between, so sánh lớn/nhỏ và truy vấn @Query có cách xử lý tham số khác nhau. Khi một tham số có thể null, hãy định nghĩa rõ hành vi và kiểm thử trên phiên bản Spring Data JPA đang sử dụng.

## 9. Truyền null vào @Query

Xét JPQL:

~~~java
@Query("select c from Customer c where c.name = :name")
List<Customer> searchExact(@Param("name") String name);
~~~

Nếu gọi searchExact(null), truy vấn vẫn có điều kiện bằng tham số null. Trong SQL, name = NULL cho kết quả UNKNOWN, nên không tìm được các dòng name IS NULL.

Nếu muốn tham số null có nghĩa là tìm bản ghi có name null, viết rõ hai nhánh:

~~~java
@Query("""
       select c
       from Customer c
       where (:name is null and c.name is null)
          or c.name = :name
       """)
List<Customer> searchExactOrNull(@Param("name") String name);
~~~

Nếu mục tiêu chỉ là "khi tham số null thì bỏ qua bộ lọc", dùng:

~~~java
@Query("""
       select c
       from Customer c
       where (:name is null or c.name = :name)
       """)
List<Customer> searchOptionalName(@Param("name") String name);
~~~

Hai query có ý nghĩa khác nhau:

- searchExactOrNull(null) chỉ lấy các dòng có name null.
- searchOptionalName(null) không áp dụng bộ lọc name và có thể trả tất cả khách hàng.

Đừng nhầm "null nghĩa là tìm giá trị null" với "null nghĩa là không lọc trường này". Đây là hai quy tắc nghiệp vụ riêng.

## 10. Null trong truy vấn LIKE

LIKE NULL không trả TRUE. Ví dụ:

~~~sql
SELECT *
FROM customers
WHERE name LIKE NULL;
~~~

Điều kiện trở thành UNKNOWN và không trả dòng nào.

Trong derived query như findByNameContaining(fragment), không nên giả định truyền null sẽ tự động tìm cột null hoặc bỏ bộ lọc. Hãy xử lý tham số null ở service hoặc dùng phương thức IsNull riêng nếu mục tiêu là tìm giá trị null.

Ví dụ service quyết định rõ:

~~~java
public List<Customer> searchByName(String fragment) {
    if (fragment == null) {
        return repository.findAll();
    }

    if (fragment.isBlank()) {
        return List.of();
    }

    return repository.findByNameContainingIgnoreCase(fragment.trim());
}
~~~

Đây chỉ là một chính sách minh họa. API khác có thể quy định null nghĩa là tìm tên null hoặc trả lỗi validation. Điều quan trọng là quyết định phải rõ ràng và nhất quán.

## 11. Null, chuỗi rỗng và chuỗi chỉ có khoảng trắng

Ba giá trị này khác nhau:

| Giá trị đầu vào | Ý nghĩa | Cách xử lý cần quyết định |
|---|---|---|
| null | Không có giá trị | Bỏ bộ lọc, tìm IS NULL hoặc báo lỗi |
| "" | Chuỗi có độ dài 0 | Tìm chuỗi rỗng hoặc coi như không nhập |
| "   " | Chuỗi chứa khoảng trắng | Giữ nguyên, trim hoặc từ chối |

Ví dụ:

- findByName(null) với derived equality có thể tìm name IS NULL.
- findByName("") tìm giá trị chuỗi rỗng.
- findByNameContaining("") tạo tìm kiếm chứa chuỗi rỗng; mẫu LIKE có thể khớp mọi giá trị name không null.
- findByNameContaining("   ") tìm đoạn có khoảng trắng, trừ khi service trim hoặc validation loại bỏ.

Không tự động coi null, empty và blank là một. Nếu UI gửi chuỗi rỗng khi người dùng bỏ trống ô tìm kiếm, service nên chuẩn hóa theo hợp đồng API.

Ví dụ chuẩn hóa:

~~~java
private String normalizeSearchText(String value) {
    if (value == null) {
        return null;
    }

    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
}
~~~

Sau đó service có thể hiểu null sau chuẩn hóa là "không có bộ lọc". Hãy ghi rõ chính sách này trong API contract và test.

## 12. Mẫu optional filter cho nhiều trường

Một màn hình tìm kiếm có thể có nhiều tham số tùy chọn. Có thể dùng điều kiện tham số null hoặc điều kiện so sánh:

~~~java
@Query("""
       select c
       from Customer c
       where (:name is null or lower(c.name) like lower(concat('%', :name, '%')))
         and (:email is null or lower(c.email) = lower(:email))
       """)
Page<Customer> search(
        @Param("name") String name,
        @Param("email") String email,
        Pageable pageable);
~~~

Cách này đơn giản khi số bộ lọc ít. Nhưng cần lưu ý:

- Nếu name có thể chứa % hoặc _, truy vấn LIKE phải escape chúng nếu muốn tìm literal.
- null ở đây có nghĩa bỏ qua điều kiện tương ứng.
- Chuỗi rỗng vẫn là giá trị khác null và có thể tạo mẫu %%.
- Nhiều nhánh OR có thể khiến database khó tận dụng index.
- Truy vấn đếm cho Page có thể tốn chi phí khi nhiều điều kiện tùy chọn.

Khi bộ lọc phức tạp, cân nhắc xây dựng query động bằng Specification, Criteria API hoặc Querydsl. Chỉ thêm predicate cho tham số thực sự có giá trị sẽ làm ý nghĩa rõ ràng và có thể tạo SQL phù hợp hơn.

## 13. Derived query so với @Query trong các trường hợp biên

| Nhu cầu | Derived query | @Query |
|---|---|---|
| Tìm chính xác tên | findByName | JPQL name = :name |
| Tìm tên null | findByNameIsNull | JPQL name is null |
| Tìm tên không null | findByNameIsNotNull | JPQL name is not null |
| Tìm chuỗi con literal | findByNameContaining | @Query với escape() |
| Tìm theo mẫu wildcard chủ động | findByNameLike | JPQL LIKE với pattern |
| Tham số null nghĩa là bỏ lọc | Xử lý ở service hoặc method riêng | (:name is null or ...) |
| Nhiều bộ lọc động | Nhiều method hoặc Specification | JPQL có nhiều điều kiện tùy chọn |

Derived query phù hợp với điều kiện đơn giản và tên method vẫn dễ hiểu. @Query phù hợp khi cần kiểm soát rõ biểu thức LIKE, escaping, phép nối, projection hoặc logic null.

Không nên tạo tên method quá dài để mô tả nhiều nhánh optional filter. Khi điều kiện trở nên phức tạp, dùng Specification hoặc query động.

## 14. Ví dụ entity và repository để thực hành

Entity Customer tối giản:

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

    @Column(name = "name", length = 150)
    private String name;

    @Column(name = "email", length = 200)
    private String email;

    protected Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository kết hợp equality, null, LIKE và @Query:

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByName(String name);

    List<Customer> findByNameIsNull();

    List<Customer> findByNameIsNotNull();

    List<Customer> findByNameContaining(String fragment);

    List<Customer> findByNameStartingWith(String prefix);

    List<Customer> findByNameEndingWith(String suffix);

    List<Customer> findByNameContainingIgnoreCase(String fragment);

    List<Customer> findByNameLike(String pattern);

    @Query("""
           select c
           from Customer c
           where c.name like %?#{escape([0])}% escape ?#{escapeCharacter()}
           """)
    List<Customer> findNameContainingLiteral(String fragment);

    @Query("""
           select c
           from Customer c
           where (:name is null or c.name = :name)
           """)
    List<Customer> findByOptionalName(@Param("name") String name);
}
~~~

Các method này minh họa các ý nghĩa khác nhau. Trong dự án thật, chỉ giữ các phương thức cần cho use case để repository không trở thành danh sách truy vấn không được sử dụng.

## 15. Kiểm thử wildcard và null với @DataJpaTest

Kiểm thử các giá trị đặc biệt để chắc chắn hành vi của framework và database đúng như hợp đồng.

~~~java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void containingTreatsWildcardsAsLiteralCharacters() {
        repository.save(new Customer("A%lice", "percent@example.com"));
        repository.save(new Customer("Alice", "alice@example.com"));
        repository.save(new Customer("A_lice", "underscore@example.com"));

        var percentMatches = repository.findByNameContaining("%");
        var underscoreMatches = repository.findByNameContaining("_");

        assertThat(percentMatches)
                .extracting(Customer::getName)
                .containsExactly("A%lice");

        assertThat(underscoreMatches)
                .extracting(Customer::getName)
                .containsExactly("A_lice");
    }

    @Test
    void equalityDerivedQueryWithNullFindsNullName() {
        repository.save(new Customer(null, "missing-name@example.com"));
        repository.save(new Customer("An", "an@example.com"));

        var result = repository.findByName(null);

        assertThat(result).isPresent();
        assertThat(result.get().getEmail())
                .isEqualTo("missing-name@example.com");
    }

    @Test
    void explicitNullQueryCanMeanNoFilter() {
        repository.save(new Customer(null, "null@example.com"));
        repository.save(new Customer("An", "an@example.com"));

        var result = repository.findByOptionalName(null);

        assertThat(result).hasSize(2);
    }
}
~~~

Test đầu tiên kiểm tra derived Containing escape wildcard chuẩn. Test thứ hai kiểm tra null trong derived equality. Test thứ ba thể hiện hợp đồng @Query mà null có nghĩa bỏ bộ lọc.

Nếu database collation hoặc cấu hình LIKE khác nhau, kết quả có thể khác về hoa thường hoặc quy tắc ký tự. Hãy chạy integration test trên database production khi ứng dụng phụ thuộc hành vi cụ thể.

## 16. Lưu ý hiệu năng và bảo mật

LIKE với wildcard ở đầu mẫu, ví dụ '%term%', thường khó tận dụng B-tree index thông thường. Nếu bảng lớn, cân nhắc full-text search, trigram index hoặc cơ chế tìm kiếm phù hợp với database.

Một số nguyên tắc:

- Tìm tiền tố với 'term%' thường thân thiện với index hơn '%term%'.
- lower(column) có thể làm index thường không được sử dụng nếu không có functional index phù hợp.
- IgnoreCase có thể sinh biểu thức lower() hoặc cách xử lý tùy provider.
- Chọn collation phù hợp nếu muốn quy tắc so sánh không phân biệt hoa thường ở database.
- Dùng bind parameter; không nối chuỗi đầu vào vào JPQL/SQL.
- Escape wildcard khi người dùng muốn tìm literal.
- Chỉ cho phép wildcard chủ động khi tính năng tìm kiếm yêu cầu điều đó.
- Giới hạn độ dài chuỗi tìm kiếm và phân trang kết quả.
- Kiểm tra execution plan trên dữ liệu có kích thước gần production.

SQL injection và wildcard injection là hai vấn đề khác nhau. Bind parameter bảo vệ cấu trúc câu lệnh; escape LIKE bảo vệ ý nghĩa ký tự đại diện trong giá trị tìm kiếm.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tìm '%' trả về quá nhiều dòng | % được hiểu là wildcard | Dùng derived Containing hoặc escape trong @Query |
| Tìm '_' trả về nhiều ký tự bất kỳ | _ khớp đúng một ký tự | Escape _ nếu muốn tìm ký tự literal |
| Like và Containing cho kết quả khác | Like nhận pattern; Containing tự thêm wildcard và escape tham số | Chọn đúng method theo ý định |
| Truyền null vào name = :name không tìm thấy dòng null | SQL so sánh bằng NULL cho kết quả UNKNOWN | Dùng IS NULL hoặc nhánh điều kiện rõ ràng |
| Null làm bỏ qua filter ngoài ý muốn | Query dùng (:param is null or ...) | Quy định rõ null là bỏ lọc hay tìm null |
| Chuỗi rỗng trả về quá nhiều kết quả | Mẫu chứa chuỗi rỗng có thể thành %% | Chuẩn hóa blank hoặc validation trước truy vấn |
| IgnoreCase vẫn có khác biệt dấu/locale | lower() và collation có quy tắc riêng | Kiểm tra collation và chuẩn hóa dữ liệu |
| Query chậm với %term% | Wildcard đầu chuỗi làm index thường kém hiệu quả | Dùng full-text/trigram hoặc thiết kế index phù hợp |
| SpEL escape không xử lý wildcard riêng của DB | escape() chỉ xử lý % và _ chuẩn | Kiểm tra tài liệu database và bổ sung quy tắc riêng |

## 18. Checklist tự đánh giá

- [ ] Giải thích được % và _ trong LIKE.
- [ ] Biết mệnh đề ESCAPE dùng để tìm ký tự wildcard theo nghĩa literal.
- [ ] Phân biệt Containing, StartingWith, EndingWith và Like.
- [ ] Hiểu derived query LIKE của Spring Data escape wildcard chuẩn trong tham số.
- [ ] Biết cấu hình escapeCharacter khi cần.
- [ ] Dùng SpEL escape() và escapeCharacter() trong @Query.
- [ ] Phân biệt bind parameter với escaping wildcard.
- [ ] Giải thích được vì sao column = NULL không tương đương column IS NULL.
- [ ] Biết null trong derived equality được xử lý như IS NULL.
- [ ] Không suy rộng quy tắc null cho LIKE và mọi @Query.
- [ ] Phân biệt null, chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- [ ] Thiết kế được optional filter với ý nghĩa null rõ ràng.
- [ ] Viết test cho %, _, null và chuỗi rỗng.
- [ ] Biết đánh giá index và hiệu năng của tìm kiếm LIKE.

## 19. Kết luận

LIKE dùng % và _ như ký tự đại diện. Khi người dùng muốn tìm chính các ký tự này, phải escape chúng. Derived query như Containing của Spring Data JPA tự xử lý wildcard chuẩn trong tham số; với @Query, dùng bind parameter cùng hàm escape() và escapeCharacter() hoặc tự xây dựng quy tắc ESCAPE đã được kiểm thử.

Null cũng cần được định nghĩa theo mục đích. Derived equality có thể chuyển tham số null thành IS NULL, trong khi JPQL field = :value không tự đổi thành IS NULL. Với bộ lọc tùy chọn, hãy quyết định null có nghĩa bỏ lọc, tìm giá trị null hay báo lỗi. Phân biệt rõ null, empty và blank giúp truy vấn dễ dự đoán, an toàn và đúng nghiệp vụ.
