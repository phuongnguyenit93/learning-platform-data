# Tạo truy vấn động bằng EntityManager trong Spring Data JPA

Khi điều kiện tìm kiếm thay đổi theo dữ liệu người dùng nhập, một repository method cố định hoặc một derived query dài có thể không còn phù hợp. Ví dụ màn hình tìm khách hàng cho phép lọc tùy chọn theo tên, email, trạng thái và khoảng thời gian tạo. Mỗi request có thể chỉ cung cấp một vài điều kiện; ứng dụng cần tạo truy vấn chỉ gồm các predicate tương ứng.

JPA cung cấp EntityManager để tạo và thực thi JPQL động hoặc Criteria API. Trong Spring Data JPA, có thể đặt phần truy vấn này trong custom repository fragment, sau đó kết hợp với JpaRepository thông thường. Cách tổ chức này giữ logic tìm kiếm phức tạp gần tầng repository, hỗ trợ tham số an toàn, phân trang, sắp xếp và count query.

Bài học này trình bày hai cách xây dựng truy vấn động: ghép cấu trúc JPQL có kiểm soát và dùng Criteria API. Trọng tâm là cách bind giá trị, whitelist tên thuộc tính sắp xếp, tái sử dụng điều kiện cho content/count, quản lý transaction và kiểm thử kết quả.

## 1. Khi nào cần truy vấn động?

Derived query phù hợp với điều kiện cố định, ví dụ:

~~~java
List<Customer> findByStatusAndNameContainingIgnoreCase(
        CustomerStatus status,
        String name);
~~~

Nhưng nếu form có nhiều trường tùy chọn, số tổ hợp method tăng nhanh. Với bốn trường lọc, người dùng có thể gửi rất nhiều tổ hợp khác nhau. Không nên tạo một method riêng cho từng tổ hợp.

JPQL động hoặc Criteria API phù hợp khi:

- Một số điều kiện chỉ được thêm khi request có giá trị.
- Người dùng có thể kết hợp nhiều bộ lọc.
- Sort hoặc projection thay đổi theo use case.
- Cần tạo content query và count query từ cùng bộ lọc.
- Cần điều kiện EXISTS, join hoặc predicate phức tạp.
- Không thể diễn đạt query dễ đọc bằng tên method.

Không cần dùng EntityManager cho mọi truy vấn. Nếu điều kiện đơn giản và cố định, derived query hoặc @Query thường ngắn và dễ bảo trì hơn.

## 2. Entity và kiểu dữ liệu dùng trong ví dụ

Ví dụ tìm kiếm Customer theo tên, email, trạng thái và thời gian tạo. Tất cả code trong các phần mô hình này thuộc package com.example.customer.

Enum:

~~~java
package com.example.customer;

public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    BLOCKED
}
~~~

Entity:

~~~java
package com.example.customer;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, length = 200)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CustomerStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(
            String name,
            String email,
            CustomerStatus status,
            Instant createdAt) {
        this.name = name;
        this.email = email;
        this.status = status;
        this.createdAt = createdAt;
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

    public CustomerStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

Entity này được dùng nhất quán trong các ví dụ JPQL, Criteria API và test. Truy vấn JPQL tham chiếu tên entity Customer và thuộc tính Java như name, email, status, createdAt; không dùng tên bảng customers hoặc tên cột vật lý.

DTO tiêu chí tìm kiếm:

~~~java
package com.example.customer;

import java.time.Instant;

public record CustomerSearchCriteria(
        String nameContains,
        String emailEquals,
        CustomerStatus status,
        Instant createdFromInclusive,
        Instant createdBeforeExclusive
) {
}
~~~

Các trường null có nghĩa là không áp dụng bộ lọc tương ứng. Khoảng thời gian dùng mốc bắt đầu inclusive và mốc kết thúc exclusive để tránh nhập nhằng khi dữ liệu có phần giây hoặc nano giây. Ví dụ một ngày có thể được biểu diễn bằng khoảng từ đầu ngày đó đến đầu ngày kế tiếp.

Nếu request đến từ API, nên validate khoảng thời gian trước khi chạy query. Ví dụ createdFromInclusive phải nhỏ hơn createdBeforeExclusive khi cả hai cùng được cung cấp.

## 3. Tổ chức custom repository fragment

Spring Data JPA cho phép mở rộng repository bằng custom fragment. Tạo một interface mô tả khả năng tìm kiếm:

~~~java
package com.example.customer;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CustomerSearchRepository {

    Page<Customer> search(
            CustomerSearchCriteria criteria,
            Pageable pageable);
}
~~~

Repository chính kế thừa cả JpaRepository và fragment:

~~~java
package com.example.customer;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

Implementation fragment có tên theo quy ước interface cộng hậu tố Impl:

~~~text
CustomerSearchRepository
CustomerSearchRepositoryImpl
~~~

Spring Data ghép implementation fragment vào CustomerRepository. Cách này giữ các thao tác CRUD chuẩn trong JpaRepository, còn truy vấn tùy biến nằm trong lớp riêng.

Đặt implementation trong package được Spring Data repository scan tìm thấy, thường là cùng package hoặc package con phù hợp với cấu hình repository. Nếu dự án đổi repositoryImplementationPostfix, tên lớp implementation phải tuân theo hậu tố đã cấu hình.

## 4. EntityManager là gì và cách inject trong Spring

EntityManager là API JPA dùng để quản lý persistence context và thực thi truy vấn. Với Spring, có thể inject EntityManager bằng @PersistenceContext:

~~~java
@PersistenceContext
private EntityManager entityManager;
~~~

Spring cung cấp proxy phù hợp với transaction hiện tại. Không tự tạo EntityManager bằng EntityManagerFactory.createEntityManager() trong repository thông thường vì như vậy dễ tách khỏi transaction do Spring quản lý và khiến việc đóng tài nguyên trở thành trách nhiệm của ứng dụng.

Các API thường dùng:

| API | Mục đích |
|---|---|
| createQuery(jpql, resultType) | Tạo typed JPQL query |
| createQuery(criteriaQuery) | Tạo query từ Criteria API |
| setParameter(name, value) | Bind giá trị tham số |
| setFirstResult(offset) | Đặt vị trí bắt đầu |
| setMaxResults(limit) | Giới hạn số kết quả |
| getResultList() | Lấy danh sách, rỗng nếu không có dòng |
| getSingleResult() | Lấy một kết quả; có thể ném lỗi nếu 0 hoặc nhiều dòng theo API JPA |
| persist(entity) | Đưa entity mới vào persistence context |
| merge(entity) | Hợp nhất trạng thái detached vào managed entity |
| flush() | Đồng bộ thay đổi persistence context xuống database |
| clear() | Detach toàn bộ entity khỏi persistence context |

Trong bài này, EntityManager chủ yếu được dùng để tạo truy vấn đọc. Các truy vấn ghi dữ liệu vẫn có thể đi qua JpaRepository hoặc service transaction tùy thiết kế.

## 5. Xây dựng JPQL động bằng StringBuilder

JPQL động có thể được tạo bằng cách thêm từng predicate khi tiêu chí tương ứng có giá trị. Chỉ ghép phần cấu trúc query đã được ứng dụng kiểm soát; giá trị người dùng luôn phải bind bằng parameter.

Ví dụ ý tưởng:

~~~java
StringBuilder jpql = new StringBuilder(
        "select c from Customer c where 1 = 1");

if (criteria.status() != null) {
    jpql.append(" and c.status = :status");
}

if (criteria.emailEquals() != null) {
    jpql.append(" and lower(c.email) = :email");
}
~~~

Điều kiện 1 = 1 giúp nối các mệnh đề AND dễ dàng, nhưng không bắt buộc. Có thể dùng List<String> predicates rồi String.join(" and ", predicates) để tránh predicate giả.

Không nối giá trị trực tiếp vào JPQL:

~~~java
// Không an toàn: dữ liệu đầu vào làm thay đổi cấu trúc query.
String jpql = "select c from Customer c where c.email = '"
        + requestEmail + "'";
~~~

Cách đúng là đặt placeholder:

~~~java
String jpql =
        "select c from Customer c where c.email = :email";

TypedQuery<Customer> query =
        entityManager.createQuery(jpql, Customer.class);

query.setParameter("email", requestEmail);
~~~

Bind parameter bảo vệ cấu trúc câu lệnh khỏi SQL injection. Nó cũng giúp provider xử lý chuyển đổi kiểu dữ liệu và tái sử dụng query plan tốt hơn trong một số tình huống.

## 6. Phân biệt giá trị parameter với tên thuộc tính động

Parameter chỉ thay thế giá trị, không thay thế tên entity, tên thuộc tính hoặc từ khóa query.

Ví dụ này không hoạt động như mong muốn:

~~~java
String jpql = "select c from Customer c order by :sortField";
query.setParameter("sortField", "createdAt");
~~~

Database sẽ coi :sortField là một giá trị, không phải identifier để sắp xếp.

Nếu cần sort động, phải chọn tên thuộc tính từ một danh sách cho phép rồi ghép identifier đã được kiểm soát vào JPQL. Không bao giờ nối trực tiếp tên cột hoặc biểu thức sort tùy ý do client gửi.

Ví dụ whitelist:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
        "name", "c.name",
        "email", "c.email",
        "status", "c.status",
        "createdAt", "c.createdAt",
        "id", "c.id"
);
~~~

Khi nhận Sort.Order, kiểm tra property có trong map trước khi thêm vào ORDER BY. Nếu không hợp lệ, từ chối request bằng lỗi validation rõ ràng.

## 7. Viết helper tạo WHERE và parameter map

Để content query và count query dùng cùng điều kiện, tạo một helper chỉ chịu trách nhiệm xây dựng phần WHERE và tập parameter.

~~~java
private String buildWhere(
        CustomerSearchCriteria criteria,
        Map<String, Object> parameters) {

    List<String> predicates = new ArrayList<>();

    if (criteria.nameContains() != null
            && !criteria.nameContains().isBlank()) {
        predicates.add("lower(c.name) like :name escape '!'");
        String value = escapeLike(
                criteria.nameContains().trim().toLowerCase(Locale.ROOT));
        parameters.put("name", "%" + value + "%");
    }

    if (criteria.emailEquals() != null
            && !criteria.emailEquals().isBlank()) {
        predicates.add("lower(c.email) = :email");
        parameters.put(
                "email",
                criteria.emailEquals().trim().toLowerCase(Locale.ROOT));
    }

    if (criteria.status() != null) {
        predicates.add("c.status = :status");
        parameters.put("status", criteria.status());
    }

    if (criteria.createdFromInclusive() != null) {
        predicates.add("c.createdAt >= :createdFrom");
        parameters.put("createdFrom", criteria.createdFromInclusive());
    }

    if (criteria.createdBeforeExclusive() != null) {
        predicates.add("c.createdAt < :createdBefore");
        parameters.put("createdBefore", criteria.createdBeforeExclusive());
    }

    if (predicates.isEmpty()) {
        return "";
    }

    return " where " + String.join(" and ", predicates);
}
~~~

Helper escape wildcard:

~~~java
private String escapeLike(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
~~~

JPQL LIKE dùng % và _ làm wildcard. Trong ví dụ, dấu ! được chọn làm ký tự escape. Hàm escapeLike xử lý chính ký tự escape trước, rồi mới escape % và _, để dữ liệu người dùng có các ký tự đó được tìm theo nghĩa literal.

Nếu không escape, request tìm tên chứa ký tự % có thể vô tình tìm rất nhiều kết quả. Bind parameter vẫn ngăn SQL injection nhưng không thay đổi ngữ nghĩa wildcard của LIKE; escaping LIKE giải quyết vấn đề riêng đó.

Các predicate được kết hợp bằng AND. Nếu nghiệp vụ cần OR, nhóm ngoặc hoặc logic phức tạp, hãy tạo cấu trúc predicate rõ ràng thay vì nối chuỗi tùy tiện.

## 8. Bind toàn bộ parameter vào TypedQuery

Có thể dùng một helper generic:

~~~java
private <T> TypedQuery<T> bindParameters(
        TypedQuery<T> query,
        Map<String, Object> parameters) {

    parameters.forEach(query::setParameter);
    return query;
}
~~~

Cách gọi:

~~~java
Map<String, Object> parameters = new LinkedHashMap<>();
String where = buildWhere(criteria, parameters);

TypedQuery<Customer> contentQuery = entityManager.createQuery(
        "select c from Customer c" + where,
        Customer.class
);

bindParameters(contentQuery, parameters);
~~~

Map giúp cùng một tập giá trị được bind vào cả content query và count query. Tên parameter phải khớp chính xác với placeholder trong JPQL.

Dùng LinkedHashMap để giữ thứ tự thêm parameter ổn định khi debug, dù thứ tự bind named parameter không ảnh hưởng ngữ nghĩa.

Không cần ép kiểu thủ công nếu createQuery nhận result type rõ ràng. TypedQuery<Customer> giúp compiler và IDE phát hiện một số lỗi kiểu trả về sớm hơn API Query không generic.

## 9. Tạo ORDER BY động an toàn

Helper dưới đây chỉ cho phép sort theo các thuộc tính đã khai báo:

~~~java
private String buildOrderBy(Sort sort) {
    if (sort.isUnsorted()) {
        return " order by c.id asc";
    }

    List<String> orders = new ArrayList<>();
    boolean includesId = false;

    for (Sort.Order order : sort) {
        String expression = SORT_FIELDS.get(order.getProperty());

        if (expression == null) {
            throw new IllegalArgumentException(
                    "Unsupported sort property: " + order.getProperty());
        }

        if (order.isIgnoreCase()) {
            if (!order.getProperty().equals("name")
                    && !order.getProperty().equals("email")) {
                throw new IllegalArgumentException(
                        "Ignore-case sort is only supported for text fields");
            }
            expression = "lower(" + expression + ")";
        }

        orders.add(expression + (order.isAscending() ? " asc" : " desc"));

        if (order.getProperty().equals("id")) {
            includesId = true;
        }
    }

    if (!includesId) {
        orders.add("c.id asc");
    }

    return " order by " + String.join(", ", orders);
}
~~~

Các điểm quan trọng:

- Sort property được tra trong whitelist.
- Hướng ASC/DESC được chuyển thành từ enum, không lấy raw SQL từ client.
- IgnoreCase chỉ được chấp nhận cho trường chuỗi.
- ID được thêm làm tie-breaker nếu người dùng chưa sort theo ID.
- Nếu không có sort, query mặc định sắp xếp theo ID.

Thứ tự ổn định rất quan trọng khi phân trang. Nếu nhiều Customer có cùng createdAt, thêm id giúp thứ tự giữa các trang xác định hơn.

## 10. Cài đặt custom repository hoàn chỉnh

Ghép các helper vào implementation fragment:

~~~java
package com.example.customer;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private static final Map<String, String> SORT_FIELDS = Map.of(
            "name", "c.name",
            "email", "c.email",
            "status", "c.status",
            "createdAt", "c.createdAt",
            "id", "c.id"
    );

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public Page<Customer> search(
            CustomerSearchCriteria criteria,
            Pageable pageable) {

        validateCriteria(criteria);

        Map<String, Object> parameters = new LinkedHashMap<>();
        String where = buildWhere(criteria, parameters);
        String orderBy = buildOrderBy(pageable.getSort());

        String contentJpql =
                "select c from Customer c" + where + orderBy;

        TypedQuery<Customer> contentQuery =
                entityManager.createQuery(contentJpql, Customer.class);

        bindParameters(contentQuery, parameters);

        if (pageable.isPaged()) {
            contentQuery.setFirstResult(
                    Math.toIntExact(pageable.getOffset()));
            contentQuery.setMaxResults(pageable.getPageSize());
        }

        List<Customer> content = contentQuery.getResultList();

        String countJpql =
                "select count(c) from Customer c" + where;

        TypedQuery<Long> countQuery =
                entityManager.createQuery(countJpql, Long.class);

        bindParameters(countQuery, parameters);

        long total = countQuery.getSingleResult();

        return new PageImpl<>(content, pageable, total);
    }

    private void validateCriteria(CustomerSearchCriteria criteria) {
        if (criteria == null) {
            throw new IllegalArgumentException("criteria must not be null");
        }

        if (criteria.createdFromInclusive() != null
                && criteria.createdBeforeExclusive() != null
                && !criteria.createdFromInclusive()
                        .isBefore(criteria.createdBeforeExclusive())) {
            throw new IllegalArgumentException(
                    "createdFromInclusive must be before createdBeforeExclusive");
        }
    }

    private String buildWhere(
            CustomerSearchCriteria criteria,
            Map<String, Object> parameters) {

        List<String> predicates = new ArrayList<>();

        if (criteria.nameContains() != null
                && !criteria.nameContains().isBlank()) {
            predicates.add("lower(c.name) like :name escape '!'");
            String value = escapeLike(
                    criteria.nameContains().trim().toLowerCase(Locale.ROOT));
            parameters.put("name", "%" + value + "%");
        }

        if (criteria.emailEquals() != null
                && !criteria.emailEquals().isBlank()) {
            predicates.add("lower(c.email) = :email");
            parameters.put(
                    "email",
                    criteria.emailEquals().trim().toLowerCase(Locale.ROOT));
        }

        if (criteria.status() != null) {
            predicates.add("c.status = :status");
            parameters.put("status", criteria.status());
        }

        if (criteria.createdFromInclusive() != null) {
            predicates.add("c.createdAt >= :createdFrom");
            parameters.put("createdFrom", criteria.createdFromInclusive());
        }

        if (criteria.createdBeforeExclusive() != null) {
            predicates.add("c.createdAt < :createdBefore");
            parameters.put("createdBefore", criteria.createdBeforeExclusive());
        }

        return predicates.isEmpty()
                ? ""
                : " where " + String.join(" and ", predicates);
    }

    private String escapeLike(String value) {
        return value
                .replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
    }

    private String buildOrderBy(Sort sort) {
        if (sort.isUnsorted()) {
            return " order by c.id asc";
        }

        List<String> orders = new ArrayList<>();
        boolean includesId = false;

        for (Sort.Order order : sort) {
            String expression = SORT_FIELDS.get(order.getProperty());

            if (expression == null) {
                throw new IllegalArgumentException(
                        "Unsupported sort property: " + order.getProperty());
            }

            if (order.isIgnoreCase()) {
                if (!order.getProperty().equals("name")
                        && !order.getProperty().equals("email")) {
                    throw new IllegalArgumentException(
                            "Ignore-case sort is only supported for text fields");
                }
                expression = "lower(" + expression + ")";
            }

            orders.add(expression
                    + (order.isAscending() ? " asc" : " desc"));

            if (order.getProperty().equals("id")) {
                includesId = true;
            }
        }

        if (!includesId) {
            orders.add("c.id asc");
        }

        return " order by " + String.join(", ", orders);
    }

    private <T> TypedQuery<T> bindParameters(
            TypedQuery<T> query,
            Map<String, Object> parameters) {

        parameters.forEach(query::setParameter);
        return query;
    }
}
~~~

Đây là một implementation hoàn chỉnh cho mô hình Customer đã khai báo. Content query và count query dùng cùng chuỗi WHERE và cùng parameter map. Count query không chứa ORDER BY vì thứ tự không ảnh hưởng số lượng.

Math.toIntExact chuyển offset kiểu long của Pageable sang int mà JPA setFirstResult yêu cầu. Nếu offset vượt giới hạn int, phép chuyển đổi sẽ thất bại thay vì âm thầm tràn số. Ứng dụng nên giới hạn page number/page size để tránh offset quá lớn.

Nếu pageable là unpaged, implementation không gọi setFirstResult hoặc setMaxResults. PageImpl vẫn nhận pageable và total count. Với API công khai, thường nên yêu cầu pageable có phân trang và giới hạn page size để tránh trả về toàn bộ bảng.

## 11. Vì sao content và count phải dùng cùng WHERE?

Page<T> chứa content cùng totalElements. Nếu content query có điều kiện status và name nhưng count query chỉ lọc status, số trang sẽ lớn hơn thực tế.

Ví dụ:

~~~text
Content:
status = ACTIVE
AND name contains "an"

Count:
status = ACTIVE
~~~

Content chỉ chứa khách hàng có tên phù hợp, nhưng count lại đếm tất cả khách hàng active. totalElements và totalPages sai.

Trong implementation trên, helper buildWhere() chỉ được gọi một lần. Chuỗi WHERE và parameter map được tái sử dụng cho cả hai query. Điều này giảm nguy cơ hai truy vấn lệch predicate.

Nếu query có JOIN to-many, count(c) có thể đếm dòng join thay vì Customer duy nhất. Khi đó nên dùng EXISTS nếu chỉ cần kiểm tra có phần tử liên quan, hoặc dùng count(distinct c.id) khi JOIN là cần thiết. Count query phải phản ánh cardinality của root entity, không phải số dòng trung gian.

## 12. Tạo truy vấn bằng Criteria API

Ghép JPQL bằng StringBuilder thuận tiện khi cấu trúc query tương đối đơn giản. Với predicate động phức tạp, Criteria API cung cấp API có kiểu cho root, predicate, order và subquery.

Ví dụ xây dựng danh sách predicate:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Customer> cq = cb.createQuery(Customer.class);
Root<Customer> root = cq.from(Customer.class);

List<Predicate> predicates = new ArrayList<>();

if (criteria.status() != null) {
    predicates.add(cb.equal(
            root.get("status"),
            criteria.status()));
}

if (criteria.emailEquals() != null
        && !criteria.emailEquals().isBlank()) {
    predicates.add(cb.equal(
            cb.lower(root.get("email")),
            criteria.emailEquals().trim().toLowerCase(Locale.ROOT)));
}

if (criteria.createdFromInclusive() != null) {
    predicates.add(cb.greaterThanOrEqualTo(
            root.get("createdAt"),
            criteria.createdFromInclusive()));
}

if (criteria.createdBeforeExclusive() != null) {
    predicates.add(cb.lessThan(
            root.get("createdAt"),
            criteria.createdBeforeExclusive()));
}

cq.select(root)
        .where(cb.and(predicates.toArray(Predicate[]::new)))
        .orderBy(cb.asc(root.get("id")));

TypedQuery<Customer> query = entityManager.createQuery(cq);
query.setFirstResult(0);
query.setMaxResults(20);

List<Customer> result = query.getResultList();
~~~

Đây là một đoạn minh họa nằm bên trong method có các biến criteria và entityManager đã được khai báo. Cần import CriteriaBuilder, CriteriaQuery, Root, Predicate, TypedQuery và các collection Java tương ứng.

Criteria API không cần tự nối JPQL string. Predicate được tạo bằng cb.equal(), cb.like(), cb.greaterThanOrEqualTo(), cb.and(), cb.or() và các hàm khác.

### So sánh hai cách

| Tiêu chí | Ghép JPQL | Criteria API |
|---|---|---|
| Cách biểu diễn | Chuỗi query | Object/query tree |
| Dễ đọc query đơn giản | Thường dễ đọc | Nhiều mã hơn |
| Predicate động | Nối các đoạn JPQL | Thêm Predicate vào List |
| Tên thuộc tính | String trong JPQL | Có thể dùng metamodel typed |
| Query phức tạp | Có thể khó quản lý chuỗi | Có API cho join/subquery/group |
| Bind giá trị | setParameter | ParameterExpression hoặc literal bind theo query |
| Kiểm tra cú pháp | Thường khi tạo/thực thi query | Một phần cấu trúc được kiểm tra bởi compiler/API |

Criteria API không tự bảo đảm query đúng nghiệp vụ hoặc hiệu quả. Nó chỉ giúp xây dựng cấu trúc truy vấn bằng Java API thay vì ghép chuỗi.

## 13. Tái sử dụng predicate cho Criteria count query

Nếu dùng Criteria API cho Page, cần tạo count query với cùng predicate.

Ví dụ helper tạo predicate cho root:

~~~java
private List<Predicate> buildPredicates(
        CustomerSearchCriteria criteria,
        CriteriaBuilder cb,
        Root<Customer> root) {

    List<Predicate> predicates = new ArrayList<>();

    if (criteria.status() != null) {
        predicates.add(cb.equal(root.get("status"), criteria.status()));
    }

    if (criteria.nameContains() != null
            && !criteria.nameContains().isBlank()) {
        String escaped = escapeLike(
                criteria.nameContains().trim().toLowerCase(Locale.ROOT));

        predicates.add(cb.like(
                cb.lower(root.get("name")),
                "%" + escaped + "%",
                '!'));
    }

    if (criteria.emailEquals() != null
            && !criteria.emailEquals().isBlank()) {
        predicates.add(cb.equal(
                cb.lower(root.get("email")),
                criteria.emailEquals().trim().toLowerCase(Locale.ROOT)));
    }

    if (criteria.createdFromInclusive() != null) {
        predicates.add(cb.greaterThanOrEqualTo(
                root.get("createdAt"),
                criteria.createdFromInclusive()));
    }

    if (criteria.createdBeforeExclusive() != null) {
        predicates.add(cb.lessThan(
                root.get("createdAt"),
                criteria.createdBeforeExclusive()));
    }

    return predicates;
}
~~~

Content query:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<Customer> contentCq =
        cb.createQuery(Customer.class);
Root<Customer> contentRoot = contentCq.from(Customer.class);

List<Predicate> contentPredicates =
        buildPredicates(criteria, cb, contentRoot);

contentCq.select(contentRoot)
        .where(cb.and(contentPredicates.toArray(Predicate[]::new)))
        .orderBy(cb.asc(contentRoot.get("createdAt")),
                 cb.asc(contentRoot.get("id")));

TypedQuery<Customer> contentQuery =
        entityManager.createQuery(contentCq);

contentQuery.setFirstResult(Math.toIntExact(pageable.getOffset()));
contentQuery.setMaxResults(pageable.getPageSize());

List<Customer> content = contentQuery.getResultList();
~~~

Count query:

~~~java
CriteriaQuery<Long> countCq = cb.createQuery(Long.class);
Root<Customer> countRoot = countCq.from(Customer.class);

List<Predicate> countPredicates =
        buildPredicates(criteria, cb, countRoot);

countCq.select(cb.count(countRoot))
        .where(cb.and(countPredicates.toArray(Predicate[]::new)));

long total = entityManager.createQuery(countCq).getSingleResult();
~~~

Mỗi query có Root riêng, vì vậy phải tạo lại Predicate cho root tương ứng. Không tái sử dụng Predicate của content root trong count query.

Nếu predicate có JOIN to-many, count query cần kiểm soát duplicate root bằng EXISTS hoặc countDistinct(countRoot.get("id")). Với query chỉ lọc thuộc tính Customer như ví dụ, cb.count(countRoot) là phù hợp.

## 14. Criteria API với OR và nhóm điều kiện

Criteria API có thể tạo nhóm AND/OR rõ ràng. Ví dụ tìm khách hàng:

- status ACTIVE
- và (tên chứa "an" hoặc email kết thúc bằng "@example.com")

~~~java
Predicate active = cb.equal(
        root.get("status"),
        CustomerStatus.ACTIVE);

Predicate nameMatches = cb.like(
        cb.lower(root.get("name")),
        "%an%",
        '!');

Predicate emailMatches = cb.like(
        cb.lower(root.get("email")),
        "%@example.com");

Predicate contactMatches = cb.or(nameMatches, emailMatches);

cq.where(cb.and(active, contactMatches));
~~~

Kết quả tương đương:

~~~sql
WHERE status = 'ACTIVE'
  AND (
      lower(name) LIKE '%an%'
      OR lower(email) LIKE '%@example.com'
  )
~~~

Dùng cb.and() và cb.or() để giữ nhóm điều kiện chính xác. Không nối các predicate bằng chuỗi nếu query có nhiều nhóm ngoặc.

Nếu dữ liệu đầu vào được dùng trong LIKE, vẫn cần escape wildcard theo ký tự escape đã chọn. Criteria API không tự biến % và _ do người dùng nhập thành ký tự literal.

## 15. JOIN, EXISTS và count khi truy vấn association

Giả sử Customer có nhiều PurchaseOrder và muốn tìm khách hàng có ít nhất một đơn hàng trạng thái PAID.

Có thể dùng JPQL EXISTS:

~~~java
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
      and o.status = :orderStatus
)
~~~

Cách này giữ mỗi Customer một lần trong kết quả ngoài. Count query có thể dùng count(c) với cùng EXISTS.

Nếu dùng JOIN:

~~~java
select c
from Customer c
join c.orders o
where o.status = :orderStatus
~~~

một Customer có nhiều đơn PAID có thể xuất hiện nhiều lần. Nếu content cần mỗi Customer một lần, dùng DISTINCT; count query cần count(distinct c.id) hoặc đổi sang EXISTS.

Khi chỉ cần kiểm tra có association thỏa điều kiện, EXISTS thường diễn đạt ý nghĩa trực tiếp hơn và tránh nhân dòng root. Khi cần lấy dữ liệu từ association, JOIN hoặc fetch plan riêng có thể phù hợp.

Không đưa collection fetch vào content query Page chỉ để lọc. Hãy tách predicate khỏi fetch plan và kiểm tra count query riêng.

## 16. Projection để chỉ lấy trường cần thiết

Nếu màn hình chỉ cần tên, email và trạng thái, không nhất thiết tải toàn bộ entity.

DTO:

~~~java
package com.example.customer;

public record CustomerSummary(
        Long id,
        String name,
        String email,
        CustomerStatus status
) {
}
~~~

JPQL constructor expression:

~~~java
String jpql = """
        select new com.example.customer.CustomerSummary(
            c.id, c.name, c.email, c.status
        )
        from Customer c
        """ + where + orderBy;

TypedQuery<CustomerSummary> query =
        entityManager.createQuery(jpql, CustomerSummary.class);
~~~

Các parameter của WHERE được bind giống content query entity. Count query vẫn dùng:

~~~java
String countJpql = "select count(c) from Customer c" + where;
~~~

DTO projection giảm số cột tải từ database và tránh khởi tạo entity/association không cần thiết. Constructor expression phải dùng fully qualified class name và kiểu/thứ tự tham số phải khớp record constructor.

Nếu query có GROUP BY hoặc aggregate, thiết kế count query theo số nhóm kết quả chứ không mặc định đếm root entity.

## 17. Phân trang và giới hạn dữ liệu

EntityManager cung cấp setFirstResult() và setMaxResults():

~~~java
TypedQuery<Customer> query =
        entityManager.createQuery(jpql, Customer.class);

query.setFirstResult(0);
query.setMaxResults(20);

List<Customer> firstPage = query.getResultList();
~~~

Offset là vị trí bắt đầu từ 0. Page đầu tiên có offset 0; page thứ hai với page size 20 có offset 20.

Khi nhận Pageable:

~~~java
if (pageable.isPaged()) {
    query.setFirstResult(Math.toIntExact(pageable.getOffset()));
    query.setMaxResults(pageable.getPageSize());
}
~~~

JPA nhận offset dưới dạng int. Với bảng lớn, offset cao có thể tốn kém vì database vẫn phải đi qua nhiều dòng trước vị trí cần lấy. Với luồng đọc rất lớn hoặc dữ liệu thay đổi liên tục, cân nhắc keyset/cursor pagination.

Luôn đặt page size tối đa ở tầng API/service. Không để client gửi page size vô hạn hoặc offset cực lớn.

## 18. Sort động và an toàn

Sort property là identifier, không phải giá trị bind parameter. Vì vậy, chỉ chấp nhận các property đã whitelist.

Ví dụ:

~~~java
Map<String, String> allowed = Map.of(
        "name", "c.name",
        "email", "c.email",
        "createdAt", "c.createdAt",
        "id", "c.id"
);

String expression = allowed.get(requestedSort);

if (expression == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String direction = ascending ? "asc" : "desc";
String orderBy = " order by " + expression + " " + direction;
~~~

Không dùng:

~~~java
String orderBy = " order by c." + requestedSort;
~~~

vì client có thể gửi chuỗi không hợp lệ hoặc cố thay đổi cấu trúc query.

Với Sort của Spring Data, vẫn cần whitelist từng Sort.Order property. Chỉ ghép expression đã tra trong map và direction lấy từ isAscending(). Thêm ID làm tie-breaker để thứ tự phân trang ổn định.

## 19. Transaction và persistence context

Truy vấn đọc bằng EntityManager nên chạy trong transaction phù hợp. Có thể đặt @Transactional(readOnly = true) ở service hoặc custom repository method.

~~~java
@Transactional(readOnly = true)
public Page<Customer> search(
        CustomerSearchCriteria criteria,
        Pageable pageable) {
    return repository.search(criteria, pageable);
}
~~~

Transaction giúp EntityManager tham gia persistence context do Spring quản lý và giữ lazy association có thể truy cập trong phạm vi transaction.

readOnly = true là metadata/gợi ý cho transaction manager và provider; không phải cơ chế bảo đảm database không thể ghi trong mọi cấu hình.

Với truy vấn hai giai đoạn hoặc cần đọc association LAZY, giữ các bước trong cùng transaction. Không trả Stream hoặc entity có lazy association ra ngoài transaction rồi mới truy cập nếu persistence context đã đóng.

## 20. Xử lý null, chuỗi rỗng và khoảng trắng

Truy vấn động cần quy định rõ ý nghĩa đầu vào:

| Giá trị | Chính sách ví dụ |
|---|---|
| null | Không thêm predicate |
| Chuỗi rỗng | Không thêm predicate |
| Chuỗi chỉ có khoảng trắng | Trim rồi coi như không nhập |
| Giá trị cụ thể | Thêm predicate và bind parameter |
| Khoảng ngày không hợp lệ | Từ chối request bằng validation |

Trong code mẫu, nameContains và emailEquals chỉ được thêm khi không null và không blank. Chuỗi được trim trước khi bind.

Không tự động áp dụng cùng chính sách cho mọi trường. Ví dụ null status có thể nghĩa là không lọc trạng thái; một use case khác có thể yêu cầu tìm Customer chưa có status. Nếu cần tìm giá trị null, thêm predicate IS NULL một cách tường minh.

Với date range, mốc kết thúc exclusive thường giúp biểu diễn ngày trọn vẹn rõ ràng. Ví dụ muốn tìm trong ngày 2026-01-10, dùng từ đầu ngày 10 inclusive đến đầu ngày 11 exclusive theo timezone nghiệp vụ.

## 21. Tránh SQL injection và các lỗi ghép query

Các nguyên tắc quan trọng:

- Bind mọi giá trị dữ liệu bằng setParameter().
- Không nối trực tiếp input vào literal JPQL.
- Không bind parameter để thay tên entity, property hoặc keyword.
- Whitelist field sort và hướng sắp xếp.
- Escape wildcard LIKE nếu người dùng cần tìm ký tự literal.
- Validate page size, offset, khoảng ngày và enum.
- Không nhận một đoạn WHERE/ORDER BY thô từ client.
- Dùng Criteria API khi cấu trúc predicate phức tạp hoặc dễ sai khi ghép chuỗi.

Ví dụ không an toàn:

~~~java
String jpql = "select c from Customer c where c.name like '%"
        + request.name() + "%'";
~~~

Ví dụ an toàn hơn:

~~~java
String jpql =
        "select c from Customer c where c.name like :name";

TypedQuery<Customer> query =
        entityManager.createQuery(jpql, Customer.class);

query.setParameter("name", "%" + escapedName + "%");
~~~

Bind parameter ngăn dữ liệu đầu vào trở thành cú pháp query. Việc escape LIKE vẫn cần thiết nếu % và _ phải mang nghĩa literal.

## 22. Kiểm thử custom repository với @DataJpaTest

Test nên xác nhận nhiều tổ hợp filter, count, sort, paging và wildcard. Ví dụ:

~~~java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class CustomerSearchRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void combinesOptionalFiltersAndCountsMatchingRows() {
        repository.saveAll(List.of(
                new Customer(
                        "An Nguyen",
                        "an@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-03T10:00:00Z")),
                new Customer(
                        "Anna Tran",
                        "anna@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-02T10:00:00Z")),
                new Customer(
                        "Binh Le",
                        "binh@example.com",
                        CustomerStatus.INACTIVE,
                        Instant.parse("2026-01-01T10:00:00Z"))
        ));

        CustomerSearchCriteria criteria = new CustomerSearchCriteria(
                "an",
                null,
                CustomerStatus.ACTIVE,
                null,
                null
        );

        Page<Customer> page = repository.search(
                criteria,
                PageRequest.of(
                        0,
                        1,
                        Sort.by(Sort.Direction.DESC, "createdAt")
                )
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getContent().getFirst().getName())
                .isEqualTo("An Nguyen");
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }

    @Test
    void treatsLikeWildcardsAsLiteralCharacters() {
        repository.saveAll(List.of(
                new Customer(
                        "100% Real",
                        "percent@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-03T10:00:00Z")),
                new Customer(
                        "100X Real",
                        "other@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-02T10:00:00Z"))
        ));

        CustomerSearchCriteria criteria = new CustomerSearchCriteria(
                "100%",
                null,
                null,
                null,
                null
        );

        Page<Customer> page = repository.search(
                criteria,
                PageRequest.of(0, 10)
        );

        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getContent())
                .extracting(Customer::getName)
                .containsExactly("100% Real");
    }
}
~~~

Ví dụ dùng List.getFirst(), có từ Java 21. Nếu dự án chạy Java 17, thay bằng page.getContent().get(0). Các API Spring Data và Hibernate cũng cần tương thích với phiên bản dự án.

@DataJpaTest thường cấu hình persistence layer và rollback transaction sau từng test. Nếu custom fragment không được phát hiện trong test slice do cấu trúc package hoặc cấu hình riêng, kiểm tra repository scan và import cấu hình cần thiết thay vì thay đổi implementation tùy tiện.

Nên bổ sung test cho:

- Không có filter, trả tất cả kết quả theo giới hạn trang.
- Mỗi filter riêng lẻ.
- Nhiều filter kết hợp bằng AND.
- Khoảng thời gian inclusive/exclusive.
- Tên/email chứa wildcard %, _ và ký tự escape !.
- Sort property không được whitelist bị từ chối.
- Sort có ID tie-breaker.
- Count query khớp chính xác content filter.
- Offset và page size biên.

## 23. Hiệu năng và quan sát SQL

Truy vấn động có thể tạo nhiều dạng SQL khác nhau tùy tổ hợp predicate. Cần đo với dữ liệu gần production.

Các điểm nên kiểm tra:

- Index trên cột thường dùng trong WHERE, ví dụ status, email hoặc createdAt.
- LOWER(column) có thể không dùng index thông thường nếu database không có functional index phù hợp.
- LIKE '%term%' thường khó tận dụng B-tree index.
- Page query có ORDER BY cần index phù hợp với filter/sort khi workload yêu cầu.
- Count query có thể tốn chi phí riêng; không gọi Page nếu UI không cần tổng số.
- Offset lớn có thể chậm; cân nhắc keyset pagination.
- Predicate JOIN to-many có thể nhân dòng; dùng EXISTS hoặc count distinct khi phù hợp.
- Không tải entity/association nếu DTO projection đáp ứng nhu cầu.

Trong môi trường phát triển có thể bật SQL log:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Log bind parameter có thể chứa email hoặc dữ liệu cá nhân. Chỉ bật khi cần debug ở môi trường kiểm soát, tránh ghi dữ liệu nhạy cảm vào log production.

## 24. Khi nào chọn JPQL động, Criteria API hay Specification?

| Cách tiếp cận | Phù hợp khi |
|---|---|
| Derived query | Điều kiện cố định, ngắn, dễ đọc |
| @Query | Một JPQL cố định cần kiểm soát rõ |
| JPQL động với EntityManager | Cấu trúc query thay đổi theo request nhưng vẫn muốn query string dễ đọc |
| Criteria API với EntityManager | Predicate động phức tạp, join/subquery/grouping nhiều |
| Specification | Muốn tái sử dụng predicate và kết hợp điều kiện động qua JpaSpecificationExecutor |
| Querydsl | Dự án cần API truy vấn type-safe và query phong phú |

JPQL động thường ngắn và dễ debug nếu chỉ có vài predicate. Criteria API phù hợp hơn khi query được xây dựng từ nhiều nhánh logic. Specification là một cách đóng gói predicate Criteria để tích hợp trực tiếp với repository. Đây không phải các lựa chọn loại trừ nhau; hãy chọn theo độ phức tạp và quy ước của dự án.

## 25. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| SQL injection qua filter | Nối giá trị người dùng vào JPQL | Dùng named parameter |
| Sort không hoạt động khi bind tên field | Parameter chỉ thay giá trị, không thay identifier | Whitelist và ghép property đã kiểm soát |
| Content đúng nhưng totalElements sai | Count query có predicate khác content | Tái sử dụng cùng WHERE và parameter map |
| Count lớn hơn số entity | JOIN to-many tạo duplicate root | Dùng EXISTS hoặc COUNT DISTINCT |
| Tìm ký tự % trả quá nhiều | LIKE hiểu % là wildcard | Escape %, _ và ký tự escape |
| Null vô tình lọc IS NULL | Dùng include-null logic hoặc predicate sai | Chỉ thêm predicate khi tiêu chí được cung cấp |
| Chuỗi rỗng tạo LIKE %% | Không chuẩn hóa blank | Trim/validate theo hợp đồng API |
| Query không tìm thấy entity/property | Dùng tên bảng/cột SQL trong JPQL | Dùng entity name và Java property |
| Sort gây lỗi khi client gửi field lạ | Không có whitelist | Từ chối property ngoài danh sách cho phép |
| Offset tràn int | Pageable offset lớn hơn giới hạn JPA | Giới hạn page/offset hoặc dùng keyset |
| LazyInitializationException | Truy cập association sau transaction | Tải trong transaction hoặc dùng DTO |
| N+1 khi duyệt collection | Truy vấn root không có fetch plan phù hợp | Batch fetch hoặc query association riêng |
| Criteria Predicate dùng nhầm Root | Tái sử dụng predicate giữa content và count root | Tạo predicate mới cho từng query root |
| EntityManager không tham gia transaction | Tự tạo EntityManager ngoài Spring | Dùng @PersistenceContext và transaction Spring |

## 26. Checklist tự đánh giá

- [ ] Biết khi nào truy vấn động cần EntityManager.
- [ ] Tổ chức custom repository fragment đúng tên interface và implementation.
- [ ] Inject EntityManager bằng @PersistenceContext.
- [ ] Dùng createQuery() với TypedQuery.
- [ ] Ghép predicate mà không nối giá trị đầu vào vào JPQL.
- [ ] Bind named parameter bằng setParameter().
- [ ] Phân biệt parameter value với identifier/sort field.
- [ ] Whitelist thuộc tính và hướng sort.
- [ ] Escape wildcard LIKE khi cần tìm literal.
- [ ] Chuẩn hóa null, empty và blank theo hợp đồng API.
- [ ] Tái sử dụng cùng filter cho content và count query.
- [ ] Dùng EXISTS hoặc count distinct khi lọc qua collection.
- [ ] Dùng CriteriaBuilder khi predicate động phức tạp.
- [ ] Tạo Predicate mới cho mỗi Criteria Root.
- [ ] Áp dụng setFirstResult và setMaxResults đúng cách.
- [ ] Giới hạn page size và xử lý offset lớn.
- [ ] Dùng transaction phù hợp với EntityManager và lazy association.
- [ ] Kiểm thử filter, count, sort, paging và wildcard.
- [ ] Quan sát SQL và execution plan trên database mục tiêu.

## 27. Kết luận

EntityManager cho phép xây dựng truy vấn động bằng JPQL hoặc Criteria API. Với JPQL, hãy ghép các đoạn cấu trúc đã kiểm soát, bind mọi giá trị và whitelist sort identifier. Với Criteria API, tạo Predicate theo từng tiêu chí rồi kết hợp bằng AND/OR.

Trong Spring Data JPA, custom repository fragment là nơi phù hợp để đóng gói logic này. Content query và count query cần dùng cùng filter predicate; nếu JOIN collection có thể nhân dòng, hãy cân nhắc EXISTS hoặc COUNT DISTINCT. Quản lý transaction, giới hạn phân trang, kiểm thử các tổ hợp filter và quan sát SQL sẽ giúp truy vấn động an toàn và dễ bảo trì.
