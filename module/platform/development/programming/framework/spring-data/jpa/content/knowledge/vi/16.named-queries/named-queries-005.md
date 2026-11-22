# Thứ tự lựa chọn giữa @Query, named query và truy vấn theo tên

Spring Data JPA có ba cách phổ biến để định nghĩa truy vấn cho một phương thức Repository: suy ra truy vấn từ tên phương thức (derived query), khai báo truy vấn bằng @Query, hoặc sử dụng named query đã được định nghĩa trước. Chúng không chỉ khác nhau về cú pháp mà còn có thứ tự ưu tiên khi Spring Data tìm cách thực thi một phương thức.

Với cấu hình mặc định CREATE_IF_NOT_FOUND, cách tra cứu thường là:

1. Nếu phương thức Repository có @Query, Spring Data sử dụng truy vấn được khai báo tại đó.
2. Nếu không có @Query, Spring Data tìm named query phù hợp với tên theo quy ước.
3. Nếu không tìm thấy named query, Spring Data cố gắng tạo truy vấn từ tên phương thức.

Có thể nhớ ngắn gọn: **@Query được ưu tiên trực tiếp; nếu không có, named query được tìm trước; derived query là phương án tạo từ tên phương thức khi không có declared query phù hợp.** Thứ tự fallback này còn phụ thuộc QueryLookupStrategy được cấu hình cho Repository.

## 1. Derived query là gì?

Derived query là truy vấn được Spring Data tạo từ tên phương thức Repository. Nhà phát triển mô tả điều kiện bằng tên thuộc tính và từ khóa như And, Or, Between, In, Like, Containing, IgnoreCase, OrderBy.

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
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    private boolean active;

    protected Customer() {
    }

    public Customer(String name, String email, boolean active) {
        this.name = name;
        this.email = email;
        this.active = active;
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

    public boolean isActive() {
        return active;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByActiveTrueOrderByNameAsc();

    List<Customer> findByNameContainingIgnoreCase(String keyword);
}
~~~

Spring Data phân tích tên phương thức và tạo JPQL/SQL phù hợp. Ví dụ findByEmail tương ứng với điều kiện so sánh thuộc tính email; findByActiveTrueOrderByNameAsc lọc active = true và sắp xếp theo name tăng dần.

### Khi nào nên dùng derived query?

Phù hợp khi:
- Điều kiện truy vấn ngắn và dễ đọc.
- Chỉ lọc theo một số thuộc tính hoặc kết hợp And/Or đơn giản.
- Không cần phép tính hoặc cấu trúc SQL đặc thù.
- Tên phương thức vẫn diễn đạt được ý định mà không quá dài.

Không nên cố nhồi một truy vấn phức tạp vào tên phương thức. Tên quá dài thường khó đọc, khó review và dễ nhầm thứ tự điều kiện.

## 2. @Query là gì?

@Query cho phép khai báo truy vấn ngay trên phương thức Repository. Theo mặc định, nội dung là JPQL; có thể chuyển sang native SQL bằng nativeQuery = true.

Ví dụ:

~~~java
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where c.active = true
          and lower(c.name) like lower(concat('%', :keyword, '%'))
        order by c.name
        """)
    List<Customer> searchActiveCustomers(
            @Param("keyword") String keyword
    );
}
~~~

Truy vấn dùng Entity Customer và thuộc tính Java active, name. JPQL không dùng tên bảng customers hoặc tên cột SQL.

### Khi nào nên dùng @Query?

Phù hợp khi:
- Điều kiện có nhiều nhánh hoặc kết hợp phức tạp.
- Cần JOIN, subquery, EXISTS, GROUP BY hoặc HAVING.
- Cần projection hoặc DTO result.
- Muốn kiểm soát rõ JPQL được dùng cho một phương thức.
- Derived query trở nên dài và khó hiểu.

Ví dụ truy vấn tổng hợp:

~~~java
@Query("""
    select c.id as customerId,
           c.name as customerName,
           count(o.id) as orderCount
    from Customer c
    left join PurchaseOrder o on o.customer = c
    group by c.id, c.name
    having count(o.id) >= :minimumOrders
    """)
List<CustomerOrderSummary> findCustomerOrderSummaries(
        @Param("minimumOrders") Long minimumOrders
);
~~~

Projection:

~~~java
public interface CustomerOrderSummary {
    Long getCustomerId();
    String getCustomerName();
    Long getOrderCount();
}
~~~

Khi dùng interface projection, alias trong SELECT nên khớp tên accessor. Với truy vấn phức tạp, hãy kiểm thử mapping và kiểu kết quả trên JPA provider đang dùng.

### @Query có thể dùng native SQL

~~~java
@Query(value = """
    SELECT c.*
    FROM customers c
    WHERE c.active = true
      AND lower(c.email) = lower(?1)
    """, nativeQuery = true)
Optional<Customer> findActiveByEmailNative(String email);
~~~

Native SQL dùng tên bảng/cột thật. Chỉ chọn cách này khi cần cú pháp database, tích hợp schema legacy hoặc kiểm soát SQL đã được đo lường. Với truy vấn thông thường, JPQL thường dễ di chuyển và bảo trì hơn.

## 3. Named query là gì?

Named query là truy vấn được đặt tên và khai báo trước, thường ở trên Entity bằng @NamedQuery hoặc trong tệp orm.xml. Với JPA, named query thông thường là JPQL; nếu cần SQL trực tiếp, có thể dùng @NamedNativeQuery.

Ví dụ khai báo trên Entity Customer:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
@NamedQuery(
    name = "Customer.findByEmail",
    query = "select c from Customer c where c.email = ?1"
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false, unique = true)
    private String email;

    protected Customer() {
    }
}
~~~

Repository có phương thức cùng tên:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
~~~

Spring Data JPA tìm named query theo quy ước tên:

~~~text
Tên Entity đơn giản + "." + tên phương thức Repository
Customer.findByEmail
~~~

Khi tìm thấy named query có tên tương ứng, Spring Data sử dụng truy vấn đó thay cho việc tự suy ra truy vấn từ tên phương thức.

Tên named query là định danh toàn cục trong persistence unit, vì vậy cần đặt tên rõ ràng và tránh trùng tên. Có thể khai báo nhiều named query bằng @NamedQueries hoặc đặt chúng trong orm.xml để tách mapping khỏi mã Entity.

### Khi nào nên dùng named query?

Phù hợp khi:
- Muốn định nghĩa truy vấn tập trung cùng metadata của Entity hoặc trong orm.xml.
- Truy vấn tĩnh được dùng theo một quy ước rõ ràng.
- Muốn provider biết và kiểm tra named query trong quá trình khởi tạo persistence unit.
- Cần dùng cùng một named query từ nhiều nơi qua EntityManager hoặc repository method tương ứng.

Named query không tự động tốt hơn @Query. Nếu chỉ có một truy vấn đặc thù của một Repository, @Query thường dễ tìm và dễ đọc hơn vì câu truy vấn nằm ngay cạnh phương thức sử dụng nó.

## 4. Thứ tự ưu tiên khi Spring Data tìm truy vấn

Spring Data JPA có QueryLookupStrategy để xác định cách tìm truy vấn cho mỗi phương thức Repository.

Ba chiến lược chính:

| Chiến lược | Hành vi |
|---|---|
| CREATE | Luôn cố gắng tạo truy vấn từ tên phương thức |
| USE_DECLARED_QUERY | Yêu cầu có declared query; nếu không tìm thấy thì báo lỗi |
| CREATE_IF_NOT_FOUND | Tìm declared query trước; nếu không có thì tạo từ tên phương thức |

CREATE_IF_NOT_FOUND là chiến lược mặc định phổ biến của Spring Data JPA.

Trong quá trình tìm declared query:
- @Query trên phương thức Repository được ưu tiên.
- Nếu không có @Query, Spring Data có thể tìm named query theo quy ước tên.
- Nếu không có declared query phù hợp và chiến lược cho phép, Spring Data mới suy ra truy vấn từ tên phương thức.

Ví dụ:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("select c from Customer c where c.email = :email")
    Optional<Customer> findByEmail(@Param("email") String email);
}
~~~

Nếu Entity cũng khai báo named query Customer.findByEmail, @Query trên phương thức Repository vẫn là truy vấn được sử dụng. Điều này giúp Repository có thể ghi đè named query mà không cần đổi tên phương thức.

Nếu bỏ @Query, named query có tên Customer.findByEmail có thể được chọn trước derived query. Nếu không có named query, CREATE_IF_NOT_FOUND sẽ thử phân tích findByEmail thành derived query.

## 5. Bảng so sánh ba cách khai báo

| Tiêu chí | Derived query | @Query | Named query |
|---|---|---|---|
| Nơi khai báo logic | Tên phương thức | Trên phương thức Repository | Trên Entity hoặc orm.xml |
| Cách đọc | Đọc từ khóa trong tên | Đọc JPQL/SQL trực tiếp | Tra theo tên định danh |
| Độ phức tạp phù hợp | Đơn giản đến vừa | Vừa đến phức tạp | Truy vấn tĩnh cần khai báo tập trung |
| Tùy chỉnh SQL | Hạn chế | JPQL hoặc native SQL | JPQL hoặc named native query |
| Tái sử dụng | Thường gắn với phương thức | Thường gắn với phương thức | Có thể gọi bằng tên từ nhiều nơi |
| Bảo trì | Tên dài sẽ khó đọc | Query dài có thể nằm ngay trong Repository | Query tách khỏi Repository method |
| Thứ tự lookup | Fallback khi không có declared query theo chiến lược | Được ưu tiên trên phương thức | Được tìm trước derived query khi không có @Query và lookup cho phép |

Không có cách nào luôn tốt nhất. Hãy chọn dựa trên độ phức tạp, vị trí nên đặt logic truy vấn và nhu cầu tái sử dụng.

## 6. Ví dụ cùng một yêu cầu được viết bằng ba cách

Yêu cầu: tìm Customer theo email.

### Cách A: Derived query

~~~java
Optional<Customer> findByEmail(String email);
~~~

Spring Data suy ra điều kiện từ tên phương thức.

### Cách B: @Query

~~~java
@Query("select c from Customer c where c.email = :email")
Optional<Customer> findCustomerByEmail(
        @Param("email") String email
);
~~~

Câu JPQL được khai báo trực tiếp tại Repository method. Tên phương thức có thể khác vì @Query đã cung cấp nội dung truy vấn.

### Cách C: Named query

Trên Entity:

~~~java
@NamedQuery(
    name = "Customer.findByEmail",
    query = "select c from Customer c where c.email = ?1"
)
~~~

Trong Repository:

~~~java
Optional<Customer> findByEmail(String email);
~~~

Spring Data tìm Customer.findByEmail. Nếu named query tồn tại và lookup strategy cho phép dùng declared query, truy vấn đã khai báo sẽ được thực thi.

Cả ba cách có thể cho cùng kết quả nhưng cách tổ chức và mức độ ưu tiên khác nhau. Tránh khai báo cả ba cho cùng một method nếu không có lý do rõ ràng, vì người bảo trì sẽ khó xác định query nào đang thực sự chạy.

## 7. Cấu hình QueryLookupStrategy

Có thể chọn chiến lược khi bật Spring Data JPA repositories:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.query.QueryLookupStrategy;

@Configuration
@EnableJpaRepositories(
    queryLookupStrategy = QueryLookupStrategy.Key.CREATE_IF_NOT_FOUND
)
public class JpaRepositoryConfiguration {
}
~~~

Ý nghĩa:

- CREATE: tạo query từ method name.
- USE_DECLARED_QUERY: yêu cầu query được khai báo trước, ví dụ @Query hoặc named query.
- CREATE_IF_NOT_FOUND: ưu tiên declared query, sau đó mới derive.

CREATE_IF_NOT_FOUND phù hợp với đa số ứng dụng vì cho phép dùng cả ba kiểu. USE_DECLARED_QUERY hữu ích khi dự án muốn buộc mọi phương thức truy vấn phải khai báo rõ. CREATE phù hợp khi muốn dựa vào quy ước tên phương thức và không dùng declared query cho các method đó.

Nếu dự án có nhiều cấu hình repository, hãy bảo đảm cấu hình áp dụng đúng package. Không tạo nhiều @EnableJpaRepositories chồng lấn lên cùng một package nếu chưa hiểu rõ cách Spring đăng ký repository bean.

## 8. Named native query và @Query native khác nhau thế nào?

Named native query được khai báo ở Entity hoặc orm.xml bằng @NamedNativeQuery:

~~~java
@NamedNativeQuery(
    name = "Customer.findActiveCustomers",
    query = """
        SELECT *
        FROM customers
        WHERE active = true
        """,
    resultClass = Customer.class
)
~~~

Repository:

~~~java
List<Customer> findActiveCustomers();
~~~

Spring Data có thể tìm named query theo tên Customer.findActiveCustomers. Kết quả được ánh xạ thành Customer qua resultClass.

So với @Query(nativeQuery = true):

- @Query đặt SQL ngay tại Repository method.
- @NamedNativeQuery đặt SQL trong metadata JPA.
- Named native query có thể dùng resultClass hoặc @SqlResultSetMapping khi mapping phức tạp.
- Cả hai đều phụ thuộc schema và cú pháp database.

Nếu kết quả chỉ là một số cột, không nên khai báo resultClass là Entity đầy đủ khi câu SELECT không trả đủ cột. Dùng SqlResultSetMapping, projection hoặc chuyển đổi sang DTO rõ ràng.

## 9. Tham số, kiểu kết quả và phân trang

Dù dùng @Query hay named query, cần bind tham số an toàn và thống nhất kiểu dữ liệu.

Với @Query, named parameter:

~~~java
@Query("""
    select c
    from Customer c
    where c.active = :active
      and c.name like concat('%', :keyword, '%')
    """)
Page<Customer> search(
        @Param("active") boolean active,
        @Param("keyword") String keyword,
        Pageable pageable
);
~~~

Với native query phức tạp, khai báo countQuery để Spring Data đếm đúng tổng số kết quả:

~~~java
@Query(
    value = """
        SELECT c.*
        FROM customers c
        WHERE c.active = true
        """,
    countQuery = """
        SELECT COUNT(*)
        FROM customers c
        WHERE c.active = true
        """,
    nativeQuery = true
)
Page<Customer> findActiveCustomers(Pageable pageable);
~~~

Named query được định nghĩa theo JPA có thể dùng tham số vị trí hoặc tên theo cú pháp phù hợp. Hãy kiểm tra khả năng hỗ trợ của provider và cách Spring Data bind tham số cho loại query đó.

Không nối chuỗi đầu vào của người dùng vào JPQL/SQL. Dùng bind parameter cho giá trị. Nếu cần thay đổi tên cột hoặc hướng sắp xếp động, hãy dùng whitelist các lựa chọn hợp lệ thay vì bind identifier như một tham số thông thường.

## 10. Khi nào nên chọn từng cách?

### Chọn derived query nếu

- Truy vấn có vài điều kiện rõ ràng.
- Tên method vẫn ngắn và dễ hiểu.
- Không cần aggregate phức tạp hoặc cú pháp SQL đặc thù.
- Muốn giảm lượng JPQL phải viết và duy trì.

Ví dụ: findByEmailIgnoreCase, findByActiveTrueOrderByCreatedAtDesc, findByPriceBetween.

### Chọn @Query nếu

- Truy vấn có JOIN, EXISTS, subquery, GROUP BY hoặc projection.
- Cần kiểm soát JPQL/native SQL cho một phương thức cụ thể.
- Cần khai báo countQuery.
- Người đọc cần thấy câu truy vấn ngay cạnh method.

Ví dụ: tìm Customer có tổng số đơn hàng vượt ngưỡng, truy vấn báo cáo hoặc tìm Entity theo nhiều quan hệ.

### Chọn named query nếu

- Truy vấn tĩnh cần đặt trong metadata Entity hoặc orm.xml.
- Có quy ước đặt tên rõ ràng và cần tra cứu từ nhiều nơi.
- Muốn tách query definition khỏi Repository interface.
- Dự án có lý do quản lý query tập trung.

Không chọn named query chỉ vì muốn “tái sử dụng” một câu SQL đơn giản. Có thể tái sử dụng query logic bằng một repository/service method chung hoặc custom repository nếu phù hợp.

## 11. Trường hợp truy vấn động: không ép vào một trong ba cách

Nếu bộ lọc thay đổi theo đầu vào, ví dụ người dùng có thể chọn tên, trạng thái, ngày tạo, giá và danh mục theo bất kỳ tổ hợp nào, tên derived query có thể phình rất lớn. Một @Query tĩnh với nhiều điều kiện dạng tham số null cũng có thể khó tối ưu và khó đọc.

Các lựa chọn khác:

- Spring Data JPA Specification để ghép predicate động.
- Criteria API khi cần xây dựng truy vấn bằng API JPA.
- Querydsl nếu dự án đã dùng và muốn truy vấn type-safe.
- Custom repository với EntityManager cho logic đặc thù.

Ví dụ ý tưởng Specification:

~~~java
public static Specification<Customer> isActive(Boolean active) {
    return (root, query, cb) -> {
        if (active == null) {
            return cb.conjunction();
        }
        return cb.equal(root.get("active"), active);
    };
}
~~~

Các Specification có thể kết hợp bằng and() hoặc or(). Cách này phù hợp hơn việc tạo hàng loạt method cho từng tổ hợp bộ lọc.

## 12. Lỗi thường gặp khi có nhiều cách khai báo cùng một query

**Nghĩ rằng derived query luôn được chạy vì method có tên findBy...**

Nếu phương thức có @Query, query khai báo trong annotation được dùng. Nếu không có @Query nhưng có named query phù hợp, named query có thể được chọn trước derivation.

**Đặt sai tên named query**

Quy ước Spring Data thường là tên Entity đơn giản, dấu chấm, tên method Repository. Ví dụ Customer.findByEmail. Sai tên sẽ khiến Spring Data không tìm thấy declared query theo quy ước.

**Nhầm tên Entity với tên bảng**

JPQL và named JPQL dùng Entity/thuộc tính Java. Native query dùng bảng/cột vật lý.

**Định nghĩa named query trùng tên**

Tên named query phải duy nhất trong persistence unit. Trùng tên có thể gây lỗi khởi tạo hoặc làm việc tra cứu không rõ ràng.

**Đặt @Query nhưng tưởng named query sẽ chạy**

@Query trên method được ưu tiên. Nếu muốn dùng named query, hãy bỏ @Query tương ứng hoặc đổi thiết kế cho rõ ràng.

**Dùng USE_DECLARED_QUERY nhưng quên khai báo query**

Nếu không có declared query phù hợp, ứng dụng có thể thất bại khi khởi tạo Repository. Hãy kiểm tra toàn bộ query method trước khi chọn chiến lược này.

**Tên derived query quá dài**

Chuyển sang @Query, Specification hoặc custom repository khi tên method không còn dễ đọc.

**Không kiểm thử truy vấn thực tế**

Query có thể lỗi do sai tên thuộc tính, kiểu tham số, alias projection hoặc cú pháp database. Hãy khởi động context và chạy integration test với database mục tiêu.

## 13. Quy trình chọn và kiểm tra query method

Khi tạo một method mới trong Repository, có thể thực hiện:

1. Xác định yêu cầu là truy vấn đơn giản, truy vấn tĩnh phức tạp hay truy vấn động.
2. Nếu đơn giản, thử derived query và giữ tên method ngắn, dễ hiểu.
3. Nếu cần JOIN/subquery/aggregate hoặc projection, dùng @Query để thể hiện rõ logic.
4. Nếu query cần được quản lý trong metadata Entity hoặc orm.xml theo quy ước chung, dùng named query.
5. Xác định QueryLookupStrategy đang dùng để hiểu fallback và lỗi khi thiếu declared query.
6. Tránh khai báo nhiều nguồn query cạnh tranh cho cùng một method nếu không cần thiết.
7. Kiểm tra tên Entity, thuộc tính, kiểu tham số, kiểu trả về và mapping projection.
8. Với native SQL, kiểm tra schema, dialect, bind parameter, countQuery và tính di động.
9. Chạy integration test cho cả trường hợp có kết quả, không có kết quả và dữ liệu biên.

## 14. Kết luận

Trong Spring Data JPA, derived query phù hợp với điều kiện đơn giản, @Query phù hợp với truy vấn cần kiểm soát trực tiếp, còn named query phù hợp khi muốn định nghĩa truy vấn tĩnh trong metadata Entity hoặc orm.xml. Với QueryLookupStrategy mặc định CREATE_IF_NOT_FOUND, @Query trên method được ưu tiên; nếu không có, Spring Data tìm named query theo quy ước tên trước rồi mới suy ra truy vấn từ tên phương thức. Hiểu đúng thứ tự này giúp tránh query bị ghi đè ngoài dự kiến và chọn cách tổ chức Repository dễ bảo trì.
