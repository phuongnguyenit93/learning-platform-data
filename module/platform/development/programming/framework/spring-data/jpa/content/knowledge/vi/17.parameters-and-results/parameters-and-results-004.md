# Phân biệt không truyền bộ lọc, lọc IS NULL và lọc bằng giá trị

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt ba ý nghĩa đầu vào: không áp dụng bộ lọc, chỉ lấy bản ghi có giá trị null và lọc theo một giá trị cụ thể.
- Giải thích vì sao SQL dùng IS NULL thay vì phép so sánh = NULL.
- Viết derived query method rõ ràng cho trường hợp null và không null.
- Nhận biết giới hạn của truy vấn @Query có điều kiện :parameter IS NULL OR ...
- Dùng Specification/Criteria API để chỉ thêm predicate khi bộ lọc được cung cấp.
- Thiết kế kiểu dữ liệu đầu vào có thể biểu diễn đủ ba trạng thái.
- Kiểm thử đúng hành vi với tham số bị thiếu, null, rỗng và có giá trị.

## 1. Ba trạng thái có ý nghĩa khác nhau

Khi xây dựng màn hình tìm kiếm hoặc API lọc dữ liệu, một field có thể mang ba ý nghĩa:

1. **Không truyền bộ lọc**: người gọi không muốn lọc theo field này. Mọi giá trị trong database đều có thể được trả về.
2. **Lọc IS NULL**: người gọi muốn lấy những bản ghi mà cột chưa có giá trị.
3. **Lọc theo giá trị**: người gọi muốn lấy những bản ghi có giá trị bằng một giá trị cụ thể.

Ví dụ với thuộc tính email:

| Đầu vào | Ý nghĩa | Điều kiện truy vấn |
|---|---|---|
| Không cung cấp filter | Không giới hạn theo email | Không thêm predicate email |
| Cung cấp filter với null | Chỉ lấy Customer chưa có email | email IS NULL |
| Cung cấp filter với an@example.com | Chỉ lấy Customer có email đó | email = :email |

Ba trạng thái này không thể được biểu diễn an toàn chỉ bằng một biến String email nullable nếu ứng dụng không biết liệu null có nghĩa là “không gửi filter” hay “lọc giá trị null”.

### Ví dụ dữ liệu

Giả sử bảng customers có:

| id | full_name | email |
|---:|---|---|
| 1 | An | an@example.com |
| 2 | Bình | NULL |
| 3 | Chi | chi@example.com |
| 4 | Dũng | NULL |

Kết quả mong muốn:

- Không truyền filter email: lấy cả 4 khách hàng.
- Filter email là null: lấy Bình và Dũng.
- Filter email là an@example.com: chỉ lấy An.

Nếu hệ thống coi cả hai trạng thái “không truyền” và “null” là giống nhau, người dùng sẽ không thể tìm riêng những bản ghi chưa có email.

## 2. SQL NULL và logic ba giá trị

Trong SQL, NULL biểu thị giá trị chưa biết hoặc không có. NULL không giống chuỗi rỗng '', số 0 hoặc giá trị boolean false.

SQL dùng logic ba giá trị:

- TRUE
- FALSE
- UNKNOWN

Phép so sánh thông thường với NULL tạo kết quả UNKNOWN:

~~~sql
SELECT *
FROM customers
WHERE email = NULL;
~~~

Câu truy vấn trên không trả về những dòng có email null, vì email = NULL không đánh giá thành TRUE. Phải dùng:

~~~sql
SELECT *
FROM customers
WHERE email IS NULL;
~~~

Và để lấy những dòng có giá trị:

~~~sql
SELECT *
FROM customers
WHERE email IS NOT NULL;
~~~

Nếu muốn lọc bằng một tham số, dùng phép so sánh bằng khi tham số chắc chắn khác null:

~~~sql
SELECT *
FROM customers
WHERE email = :email;
~~~

Khi :email được bind null, biểu thức email = NULL vẫn không đúng. Vì vậy, cần chọn điều kiện SQL dựa trên trạng thái filter trước khi thực thi.

### NULL khác chuỗi rỗng

| email | Ý nghĩa |
|---|---|
| NULL | Chưa có giá trị |
| '' | Chuỗi có độ dài 0 |
| '   ' | Chuỗi chứa khoảng trắng |
| 'an@example.com' | Chuỗi có giá trị |

Nếu nghiệp vụ xem chuỗi rỗng hoặc chỉ có khoảng trắng là “chưa nhập”, hãy chuẩn hóa khi ghi hoặc viết điều kiện rõ ràng. Không giả định IS NULL cũng tìm được chuỗi rỗng.

## 3. Ánh xạ thuộc tính nullable trong Entity

Ví dụ entity Customer:

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

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @Column(name = "email", nullable = true, length = 254)
    private String email;

    protected Customer() {
    }

    public Customer(String fullName, String email) {
        this.fullName = fullName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }
}
~~~

nullable = true mô tả rằng cột email được phép nhận null khi schema được tạo từ mapping. Trong hệ thống production, migration database vẫn phải tạo cột nullable đúng như yêu cầu; annotation không tự bảo đảm schema hiện có đã đúng.

Không dùng primitive cho thuộc tính có thể null. Ví dụ, int không thể biểu diễn null; dùng Integer nếu giá trị đó có thể vắng mặt. Với email là String, Java null có thể biểu diễn trạng thái chưa có giá trị.

## 4. Derived query method cho IS NULL và IS NOT NULL

Spring Data JPA hỗ trợ từ khóa rõ ràng:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    List<Customer> findByEmailIsNull();

    List<Customer> findByEmailIsNotNull();

    List<Customer> findByEmail(String email);
}
~~~

Ý nghĩa:

- findByEmailIsNull(): lấy Customer có email null.
- findByEmailIsNotNull(): lấy Customer có email khác null.
- findByEmail(value): tìm Customer có email bằng giá trị truyền vào.

Với derived equality query, Spring Data JPA xử lý tham số null như điều kiện IS NULL. Vì vậy, gọi findByEmail(null) có thể được dùng để tìm các bản ghi có email null. Tuy nhiên, dùng tên method tường minh findByEmailIsNull() thường giúp ý định rõ ràng hơn và tránh việc người đọc nhầm với trường hợp bỏ filter.

Nếu muốn hỗ trợ cả ba trạng thái trong một API tìm kiếm, không nên chỉ gọi findByEmail(email) khi email nullable. Khi email null do request không gửi, method đó sẽ tìm các bản ghi email null thay vì bỏ qua điều kiện.

### Kết hợp với các điều kiện khác

~~~java
List<Customer> findByStatusAndEmailIsNull(CustomerStatus status);

List<Customer> findByStatusAndEmailIsNotNull(CustomerStatus status);

List<Customer> findByStatusAndEmail(
    CustomerStatus status,
    String email
);
~~~

Các method này phù hợp khi tập hợp truy vấn cố định và dễ diễn đạt. Nếu filter có nhiều trạng thái tùy chọn, việc khai báo mọi tổ hợp method sẽ nhanh chóng trở nên khó quản lý.

## 5. Vì sao :email IS NULL OR c.email = :email không biểu diễn đủ ba trạng thái?

Một cách viết thường gặp trong @Query:

~~~java
@Query("""
    select c
    from Customer c
    where (:email is null or c.email = :email)
    """)
List<Customer> searchByEmailOrAll(@Param("email") String email);
~~~

Logic của truy vấn là:

- Nếu :email null, vế đầu :email IS NULL đúng nên không lọc theo email.
- Nếu :email có giá trị, vế đầu sai và truy vấn so sánh c.email = :email.

Cách này biểu diễn được hai trạng thái:

1. Null nghĩa là bỏ qua filter.
2. Có giá trị nghĩa là lọc bằng giá trị.

Nó **không thể** biểu diễn trạng thái thứ ba là “lọc email IS NULL”. Khi truyền null, truy vấn trả tất cả bản ghi thay vì chỉ bản ghi có email null.

Đây không phải lỗi cú pháp; đây là giới hạn của cách thiết kế điều kiện. Một nullable parameter không mang đủ thông tin để phân biệt “không cung cấp” và “có cung cấp nhưng giá trị null”.

### Khi nào cách viết này phù hợp?

Dùng khi hợp đồng API quy định rõ null luôn có nghĩa là bỏ qua điều kiện. Ví dụ một màn hình tìm kiếm đơn giản, trong đó người dùng chỉ có thể nhập email hoặc để trống để không lọc.

Nếu nghiệp vụ cần tìm các bản ghi có email null, hãy dùng method riêng hoặc một biểu diễn filter có trạng thái rõ ràng.

## 6. Dùng Specification để biểu diễn đủ ba trạng thái

Với bộ lọc động, Spring Data JPA Specification là một lựa chọn rõ ràng. Specification cho phép thêm predicate có điều kiện.

### Kiểu filter có trạng thái

Tạo một kiểu dữ liệu biểu diễn việc filter có được cung cấp hay không và giá trị của nó:

~~~java
package com.example.customer;

public record NullableFilter<T>(boolean supplied, T value) {

    public NullableFilter {
        if (!supplied && value != null) {
            throw new IllegalArgumentException(
                "An omitted filter cannot carry a value"
            );
        }
    }

    public static <T> NullableFilter<T> omitted() {
        return new NullableFilter<>(false, null);
    }

    public static <T> NullableFilter<T> isNull() {
        return new NullableFilter<>(true, null);
    }

    public static <T> NullableFilter<T> equalTo(T value) {
        if (value == null) {
            throw new IllegalArgumentException(
                "Use isNull() to filter for null"
            );
        }
        return new NullableFilter<>(true, value);
    }
}
~~~

Ba cách khởi tạo:

~~~java
NullableFilter<String> anyEmail = NullableFilter.omitted();
NullableFilter<String> missingEmail = NullableFilter.isNull();
NullableFilter<String> exactEmail =
        NullableFilter.equalTo("an@example.com");
~~~

Ở đây:

- supplied = false: không thêm predicate.
- supplied = true và value = null: thêm IS NULL.
- supplied = true và value khác null: thêm equality.

### Specification cho Customer

~~~java
package com.example.customer;

import java.util.Objects;

import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> emailMatches(
            NullableFilter<String> filter) {

        Objects.requireNonNull(filter, "filter must not be null");

        return (root, query, criteriaBuilder) -> {
            if (!filter.supplied()) {
                return criteriaBuilder.conjunction();
            }

            if (filter.value() == null) {
                return criteriaBuilder.isNull(root.get("email"));
            }

            return criteriaBuilder.equal(
                root.get("email"),
                filter.value()
            );
        };
    }
}
~~~

criteriaBuilder.conjunction() tạo điều kiện TRUE, tương đương không giới hạn kết quả bởi email. Khi filter có null, isNull() tạo predicate IS NULL. Khi có giá trị, equal() tạo equality predicate.

### Repository và service

Repository cần triển khai JpaSpecificationExecutor:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

Service:

~~~java
@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Customer> searchByEmail(NullableFilter<String> emailFilter) {
        return repository.findAll(
            CustomerSpecifications.emailMatches(emailFilter)
        );
    }
}
~~~

Ví dụ gọi:

~~~java
service.searchByEmail(NullableFilter.omitted()); // Không lọc email
service.searchByEmail(NullableFilter.isNull());  // Email IS NULL
service.searchByEmail(
    NullableFilter.equalTo("an@example.com")
); // Email = giá trị
~~~

Cách này dễ mở rộng cho nhiều filter vì mỗi filter có thể tạo một predicate độc lập rồi kết hợp bằng AND/OR theo yêu cầu nghiệp vụ.

## 7. Kết hợp nhiều bộ lọc

Giả sử màn hình tìm kiếm Customer có:

- Email: không lọc, IS NULL hoặc bằng giá trị.
- Status: không lọc hoặc bằng một enum.
- Enabled: không lọc hoặc bằng true/false.

Có thể xây dựng Specification:

~~~java
public static Specification<Customer> search(
        NullableFilter<String> emailFilter,
        NullableFilter<CustomerStatus> statusFilter,
        NullableFilter<Boolean> enabledFilter) {

    return (root, query, cb) -> {
        List<Predicate> predicates = new ArrayList<>();

        if (emailFilter.supplied()) {
            if (emailFilter.value() == null) {
                predicates.add(cb.isNull(root.get("email")));
            } else {
                predicates.add(
                    cb.equal(root.get("email"), emailFilter.value())
                );
            }
        }

        if (statusFilter.supplied()) {
            if (statusFilter.value() == null) {
                predicates.add(cb.isNull(root.get("status")));
            } else {
                predicates.add(
                    cb.equal(root.get("status"), statusFilter.value())
                );
            }
        }

        if (enabledFilter.supplied()) {
            if (enabledFilter.value() == null) {
                predicates.add(cb.isNull(root.get("enabled")));
            } else {
                predicates.add(
                    cb.equal(root.get("enabled"), enabledFilter.value())
                );
            }
        }

        return cb.and(predicates.toArray(Predicate[]::new));
    };
}
~~~

Ví dụ này giả định các field status và enabled cho phép null. Nếu chúng được khai báo NOT NULL trong entity/schema, nhánh IS NULL không có kết quả nhưng cấu trúc filter vẫn thể hiện đúng semantics. Có thể trừu tượng hóa việc tạo predicate để tránh lặp code khi số lượng filter tăng.

Với truy vấn có nhiều quan hệ, sort hoặc join, hãy kiểm soát duplicate row và dùng query.distinct(true) khi cần. Nếu có phân trang, kiểm tra count query và kết quả thực tế.

## 8. Dùng @Query với cờ trạng thái riêng

Nếu muốn giữ một câu JPQL cố định, có thể truyền thêm hai cờ:

- filterEmail: có áp dụng filter email hay không.
- emailIsNull: nếu filter được áp dụng, có phải tìm null không.
- email: giá trị cụ thể khi không phải null.

Ví dụ:

~~~java
@Query("""
    select c
    from Customer c
    where
        :filterEmail = false
        or (
            :filterEmail = true
            and :emailIsNull = true
            and c.email is null
        )
        or (
            :filterEmail = true
            and :emailIsNull = false
            and c.email = :email
        )
    """)
List<Customer> search(
    @Param("filterEmail") boolean filterEmail,
    @Param("emailIsNull") boolean emailIsNull,
    @Param("email") String email
);
~~~

Cách gọi:

| Trường hợp | filterEmail | emailIsNull | email |
|---|---:|---:|---|
| Không lọc | false | false | null |
| Email IS NULL | true | true | null |
| Email bằng giá trị | true | false | an@example.com |

Cần bảo đảm tổ hợp tham số nhất quán. Ví dụ khi filterEmail = true và emailIsNull = false, email phải khác null. Có thể validate ở service trước khi gọi repository.

Cách này có thể dùng được nhưng câu query dài và có nhiều tham số điều khiển. Specification thường dễ đọc hơn khi số filter tăng hoặc logic có nhiều trạng thái.

## 9. Không nhầm absent, null và chuỗi rỗng ở tầng API

Một nguồn lỗi phổ biến nằm ở việc chuyển HTTP request/JSON thành Java object.

### Query parameter

Ví dụ:

- GET /customers: email không được gửi.
- GET /customers?email=an%40example.com: email có giá trị.
- GET /customers?email=: email là chuỗi rỗng sau khi giải mã, không tự động là null.

HTTP query string không có một cú pháp chuẩn chung để biểu diễn JSON null. Nếu muốn tìm email null, API có thể cung cấp tham số riêng như emailNull=true, hoặc endpoint/filter syntax rõ ràng.

Đừng tự động biến chuỗi rỗng thành null trừ khi hợp đồng API quy định rõ. Việc đó có thể làm người dùng không thể tìm các giá trị chuỗi rỗng nếu chúng hợp lệ.

### JSON request body

Với JSON:

~~~json
{}
~~~

Field email không xuất hiện.

~~~json
{"email": null}
~~~

Field email xuất hiện với giá trị null.

~~~json
{"email": "an@example.com"}
~~~

Field email xuất hiện với giá trị cụ thể.

Một DTO Java thông thường chỉ có String email có thể không phân biệt được field bị thiếu với field có null sau khi deserialize. Nếu API cần semantics ba trạng thái, hãy dùng một kiểu có thể biểu diễn field presence, ví dụ:

- Một boolean riêng như emailProvided.
- Một wrapper tri-state như NullableFilter<String>.
- Jackson JsonNode và kiểm tra has("email") cùng isNull().
- Một thư viện wrapper hỗ trợ JSON field presence như JsonNullable<T>, nếu dự án đã sử dụng.

Ví dụ với JsonNode:

~~~java
JsonNode body = objectMapper.readTree(requestBody);

if (!body.has("email")) {
    // Không truyền filter
} else if (body.get("email").isNull()) {
    // Lọc email IS NULL
} else {
    String email = body.get("email").asText();
    // Lọc email bằng giá trị
}
~~~

Nếu API là PATCH cập nhật entity, ba trạng thái có ý nghĩa khác:

- Field vắng mặt: giữ nguyên giá trị hiện tại.
- Field có null: xóa giá trị hiện tại.
- Field có giá trị: cập nhật thành giá trị mới.

Đây là semantics của cập nhật partial, không nên tự động dùng chung với semantics của màn hình tìm kiếm.

## 10. Optional<T> có giải quyết được ba trạng thái không?

Không. Optional<T> chỉ biểu diễn có giá trị hoặc không có giá trị. Optional.empty() không cho biết người gọi muốn bỏ qua filter hay muốn tìm cột null.

Ví dụ:

~~~java
Optional<String> email = Optional.empty();
~~~

Không thể biết từ biến này liệu ý định là:

- Không lọc email.
- Lọc email IS NULL.

Optional.ofNullable(value) cũng gộp null và không có giá trị thành cùng một trạng thái. Nếu cần ba trạng thái, dùng kiểu filter có cờ presence hoặc một sealed type/enum rõ ràng.

Một mô hình dễ hiểu khác:

~~~java
public sealed interface EmailFilter
        permits AnyEmail, EmailIsNull, EmailEquals {
}

public record AnyEmail() implements EmailFilter {
}

public record EmailIsNull() implements EmailFilter {
}

public record EmailEquals(String value) implements EmailFilter {
    public EmailEquals {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
    }
}
~~~

Mô hình này diễn đạt ý định ngay trong type system. Có thể dùng khi muốn tránh các tổ hợp boolean không hợp lệ.

## 11. Kiểm thử ba trạng thái

Repository/service cần test đủ ba trường hợp:

~~~java
@DataJpaTest
class CustomerSearchTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void omittedFilterReturnsAllCustomers() {
        CustomerSearchService service =
                new CustomerSearchService(repository);

        List<Customer> result = service.searchByEmail(
            NullableFilter.omitted()
        );

        assertEquals(4, result.size());
    }

    @Test
    void explicitNullReturnsOnlyCustomersWithoutEmail() {
        CustomerSearchService service =
                new CustomerSearchService(repository);

        List<Customer> result = service.searchByEmail(
            NullableFilter.isNull()
        );

        assertEquals(2, result.size());
        assertTrue(result.stream().allMatch(c -> c.getEmail() == null));
    }

    @Test
    void concreteValueReturnsExactMatch() {
        CustomerSearchService service =
                new CustomerSearchService(repository);

        List<Customer> result = service.searchByEmail(
            NullableFilter.equalTo("an@example.com")
        );

        assertEquals(1, result.size());
        assertEquals("An", result.get(0).getFullName());
    }
}
~~~

Test giả định database test đã seed bốn Customer như bảng dữ liệu ở phần 1. Trong ứng dụng thật, nên inject service qua Spring context thay vì tự khởi tạo service nếu service có transaction hoặc dependency khác.

Bổ sung các test biên:

- Chuỗi rỗng có được xem là giá trị hợp lệ hay cần normalize?
- Chuỗi chỉ chứa khoảng trắng được xử lý thế nào?
- Filter có giá trị nhưng sai định dạng có bị từ chối ở tầng validation?
- Cột null có được phép theo schema không?
- Nhiều filter kết hợp AND/OR có tạo đúng tập kết quả không?
- Phân trang có giữ đúng total và sort không?

## 12. Hiệu năng và khả năng dùng index

Một query dạng:

~~~jpql
where (:email is null or c.email = :email)
~~~

có thể tiện lợi vì chỉ cần một method, nhưng biểu thức OR có thể làm database khó chọn index plan tối ưu trong một số workload. Hiệu quả phụ thuộc database, thống kê, tham số và query planner.

Dynamic Specification chỉ thêm predicate cần thiết có thể tạo SQL rõ ràng hơn:

- Không có filter: không có điều kiện email.
- Null filter: email IS NULL.
- Value filter: email = ?

Database có thể tận dụng index phù hợp với từng truy vấn. Với filter IS NULL, khả năng dùng index phụ thuộc database và loại index. Hãy xem execution plan và đo trên dữ liệu gần với production; không mặc định rằng một cách viết luôn nhanh hơn.

Nếu email được dùng để tra cứu chính xác thường xuyên, cân nhắc index phù hợp. Nếu so sánh không phân biệt hoa thường, expression index/collation và cách normalize phải thống nhất giữa query và schema.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không truyền email nhưng chỉ nhận bản ghi email null | Gọi findByEmail(null) khi null thực chất là absent filter | Phân biệt presence; không gọi predicate khi filter vắng mặt |
| Truyền null nhưng nhận tất cả bản ghi | Dùng (:email IS NULL OR ...) với null mang nghĩa bỏ filter | Dùng IS NULL riêng hoặc tri-state filter |
| email = NULL không trả kết quả | SQL dùng logic ba giá trị | Dùng IS NULL |
| Không tìm thấy chuỗi rỗng bằng IS NULL | Chuỗi rỗng khác database NULL | Quy định normalize hoặc lọc email = '' |
| Optional.empty không phân biệt được ý định | Optional chỉ có hai trạng thái | Dùng wrapper/enum ba trạng thái |
| DTO JSON không phân biệt field thiếu và null | Deserializer đặt cả hai thành Java null | Theo dõi field presence hoặc dùng JsonNode/wrapper |
| Query có nhiều OR khó tối ưu | Dùng một câu query cho nhiều trạng thái | Dùng Specification và đo execution plan |
| Filter có giá trị null nhưng service bỏ qua | Service kiểm tra value == null rồi không thêm predicate | Kiểm tra cả cờ supplied/presence |
| PATCH xóa dữ liệu ngoài ý muốn | Field vắng mặt và field null bị gộp | Dùng semantics field presence cho partial update |

## Quy trình chọn cách triển khai

1. Xác định hợp đồng: null nghĩa là bỏ qua hay tìm cột null?
2. Nếu chỉ cần một điều kiện cố định, dùng derived method như findByEmailIsNull() hoặc findByEmailIsNotNull().
3. Nếu nullable parameter chỉ có nghĩa “không lọc khi null”, @Query với :email IS NULL OR ... có thể phù hợp.
4. Nếu cần cả absent, null và value, dùng Specification/Criteria API hoặc filter object tri-state.
5. Ở tầng API, bảo toàn thông tin field presence trước khi chuyển thành filter.
6. Kiểm thử cả ba trạng thái, chuỗi rỗng, nhiều filter và phân trang.
7. Kiểm tra execution plan nếu truy vấn chạy trên bảng lớn.

## Checklist trước khi merge

- [ ] Đã định nghĩa rõ ý nghĩa của absent, null và empty string.
- [ ] SQL dùng IS NULL/IS NOT NULL thay vì so sánh = NULL.
- [ ] Derived query method có tên tường minh cho null.
- [ ] Không dùng một nullable parameter để đại diện ba trạng thái.
- [ ] Query optional filter được dùng đúng khi null mang nghĩa bỏ qua.
- [ ] Specification chỉ thêm predicate khi filter thực sự được cung cấp.
- [ ] API giữ được khác biệt giữa field thiếu và field null khi cần.
- [ ] Optional.empty không bị dùng như tri-state filter.
- [ ] Integration test xác nhận đủ ba trạng thái.
- [ ] Index và execution plan được đánh giá theo workload thực tế.

## Kết luận

Không truyền bộ lọc, lọc IS NULL và lọc bằng một giá trị là ba ý định khác nhau. SQL cần IS NULL để kiểm tra null; = NULL không trả về TRUE. Derived query có thể biểu diễn rõ null bằng findByEmailIsNull(), nhưng một câu @Query dạng (:email IS NULL OR c.email = :email) dùng null với nghĩa bỏ qua filter. Khi cần đủ ba trạng thái, hãy giữ thông tin field presence bằng filter object và xây dựng predicate động qua Specification/Criteria API. Kiểm thử riêng absent, null, giá trị và chuỗi rỗng để tránh lọc sai dữ liệu.
