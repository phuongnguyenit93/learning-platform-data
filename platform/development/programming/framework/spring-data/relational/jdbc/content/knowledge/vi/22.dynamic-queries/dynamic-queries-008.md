# Phân biệt Criteria của Spring Data Relational với JPA Criteria, Specification và Querydsl

Trong ứng dụng Java, có nhiều cách mô tả điều kiện truy vấn mà không phải nối chuỗi SQL thủ công. Tên gọi của chúng khá giống nhau, nhưng **Criteria của Spring Data Relational**, **JPA Criteria API**, **Spring Data JPA Specification** và **Querydsl** là các abstraction khác nhau, được thiết kế cho những mô hình persistence khác nhau.

Với **Spring Data JDBC**, Criteria thuộc Spring Data Relational và thường được dùng cùng **Query** và **JdbcAggregateTemplate** để tạo bộ lọc động trên aggregate. JPA Criteria và Specification dựa trên mô hình Jakarta Persistence (JPA), còn Querydsl là một thư viện DSL có thể tích hợp với nhiều backend khác nhau. Không thể lấy một ví dụ Specification hoặc Querydsl JPA rồi dùng nguyên xi với Spring Data JDBC.

Bài này so sánh mục đích, API, khả năng và cách lựa chọn từng công cụ; đồng thời đưa ra các ví dụ tương đương để thấy rõ sự khác nhau.

## 1. Bốn tên gọi, bốn vai trò

| Công cụ | Thuộc hệ sinh thái | Mục tiêu chính | Cách sử dụng thường gặp |
|---|---|---|---|
| **Spring Data Relational Criteria** | Spring Data Relational, dùng bởi Spring Data JDBC | Mô tả predicate có cấu trúc cho query/update trên dữ liệu relational được mapping | Tạo Criteria, bọc trong Query, gọi JdbcAggregateTemplate |
| **JPA Criteria API** | Jakarta Persistence / JPA | Xây dựng truy vấn JPA bằng object API, có Root, Path, Join, Predicate, subquery | EntityManager + CriteriaBuilder + CriteriaQuery |
| **Spring Data JPA Specification** | Spring Data JPA | Đóng gói predicate JPA thành thành phần có thể kết hợp và tái sử dụng | Specification<T> + JpaSpecificationExecutor |
| **Querydsl** | Thư viện query DSL độc lập | Xây dựng query bằng API fluent và kiểu Q được sinh từ model | Querydsl JPA hoặc Querydsl SQL, thường qua integration tương ứng |

Tên Criteria trong Spring Data Relational không có nghĩa nó là phiên bản rút gọn của JPA Criteria API với cùng interface. Hai API không dùng chung các kiểu như CriteriaBuilder, CriteriaQuery, Root hay EntityManager.

Tương tự, Specification không phải một tính năng chung của mọi Spring Data repository. Specification phổ biến trong Spring Data JPA vì nó dựa trên JPA Criteria API. Spring Data JDBC không cung cấp JpaSpecificationExecutor cho JdbcAggregateTemplate.

## 2. Spring Data Relational Criteria là gì?

Spring Data Relational cung cấp các lớp trong package org.springframework.data.relational.core.query, đặc biệt là Criteria và Query. Criteria mô tả điều kiện lọc; Query kết hợp điều kiện đó với sort, limit, offset và các thông tin truy vấn khác.

Ví dụ aggregate root:

~~~java
import java.math.BigDecimal;
import java.time.LocalDateTime;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        String status,
        BigDecimal total,
        LocalDateTime createdAt
) {}
~~~

Tạo Criteria:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Criteria criteria = Criteria.where("status").is("OPEN")
        .and("total").greaterThanOrEquals(new BigDecimal("100.00"));

Query query = Query.query(criteria);
~~~

Criteria trên biểu đạt điều kiện:

~~~sql
WHERE status = ?
  AND total >= ?
~~~

Giá trị điều kiện được bind qua cơ chế JDBC; không cần nối dữ liệu người dùng vào chuỗi SQL.

Để thực thi, inject JdbcAggregateTemplate:

~~~java
import java.util.List;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;

List<PurchaseOrder> orders =
        template.findAll(query, PurchaseOrder.class);
~~~

Template dùng metadata của Spring Data Relational để ánh xạ kết quả về aggregate root PurchaseOrder. Đây là điểm khác với một query SQL tùy chỉnh trả về một hàng phẳng hoặc DTO.

### Các predicate thường dùng

Tùy phiên bản Spring Data Relational, Criteria cung cấp các phép so sánh và kiểm tra phổ biến, chẳng hạn:

| Predicate | Ý nghĩa |
|---|---|
| is(value) | Bằng giá trị |
| not(value) | Khác giá trị |
| greaterThan(value) | Lớn hơn |
| greaterThanOrEquals(value) | Lớn hơn hoặc bằng |
| lessThan(value) | Nhỏ hơn |
| lessThanOrEquals(value) | Nhỏ hơn hoặc bằng |
| between(from, to) | Nằm trong khoảng |
| in(values) | Thuộc một tập giá trị |
| like(pattern) | So khớp mẫu LIKE |
| isNull() / isNotNull() | Kiểm tra NULL |
| and(...) / or(...) | Kết hợp điều kiện |

Ví dụ:

~~~java
Criteria criteria = Criteria.where("status").in(List.of("OPEN", "PENDING"))
        .and("createdAt").greaterThanOrEquals(from)
        .and("createdAt").lessThan(to);
~~~

Các tên property trong Criteria phải được phân giải theo mapping của aggregate. Với ví dụ trên, các property Java và tên cột vật lý khá gần nhau; nếu dự án có @Column hoặc naming strategy tùy chỉnh, hãy kiểm tra metadata và SQL được tạo để xác nhận tên được ánh xạ đúng.

## 3. Query, Sort và Pageable đi cùng Criteria như thế nào?

Criteria chỉ là phần điều kiện. Query đóng gói Criteria cùng thứ tự và giới hạn kết quả:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Query;

Criteria criteria = Criteria.where("status").is("OPEN");
Query baseQuery = Query.query(criteria);

Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
Query pageQuery = baseQuery.with(pageable);

List<PurchaseOrder> content =
        template.findAll(pageQuery, PurchaseOrder.class);
~~~

Query.with(pageable) áp dụng sort, offset và limit vào một Query mới. Query là immutable, vì vậy phải giữ object được trả về từ các lời gọi fluent.

Nếu cần tổng số phần tử để tạo Page, đếm trên query gốc chưa phân trang:

~~~java
long total = template.count(baseQuery, PurchaseOrder.class);
Page<PurchaseOrder> page = new PageImpl<>(content, pageable, total);
~~~

Không dùng pageQuery cho count nếu mục tiêu là tổng số bản ghi thỏa điều kiện, bởi pageQuery đã chứa giới hạn và độ lệch của trang.

### Xây dựng Criteria theo bộ lọc tùy chọn

Một màn hình tìm kiếm có thể gửi status, số tiền tối thiểu và thời điểm bắt đầu. Chỉ thêm predicate khi người dùng thực sự cung cấp giá trị:

~~~java
Criteria criteria = Criteria.empty();

if (status != null && !status.isBlank()) {
    criteria = criteria.and("status").is(status);
}

if (minimumTotal != null) {
    criteria = criteria.and("total")
            .greaterThanOrEquals(minimumTotal);
}

if (createdAfter != null) {
    criteria = criteria.and("createdAt")
            .greaterThanOrEquals(createdAfter);
}

Query query = Query.query(criteria);
~~~

Các thao tác xây dựng Criteria trả về một biểu thức mới; hãy gán kết quả trở lại biến. API cụ thể cho Criteria rỗng và cách ghép predicate đầu tiên có thể khác theo phiên bản; nếu dự án dùng phiên bản có giới hạn với Criteria.empty(), có thể thu thập các predicate rồi kết hợp bằng API Criteria phù hợp của phiên bản đó.

Criteria phù hợp với những bộ lọc relational mà QueryMapper và dialect hỗ trợ. Nó không phải một API tổng quát để mô tả mọi SQL có thể viết.

## 4. Spring Data Relational Criteria khác JPA Criteria API ở đâu?

JPA Criteria API là API truy vấn hướng object của Jakarta Persistence. Nó thao tác trên entity, thuộc tính, association và các thành phần của câu truy vấn JPA.

Ví dụ JPA entity:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrderEntity {
    @Id
    private Long id;

    private String status;

    private BigDecimal total;
}
~~~

Một truy vấn JPA Criteria có thể viết:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<PurchaseOrderEntity> cq =
        cb.createQuery(PurchaseOrderEntity.class);

Root<PurchaseOrderEntity> root = cq.from(PurchaseOrderEntity.class);

Predicate statusIsOpen =
        cb.equal(root.get("status"), "OPEN");

Predicate totalAtLeast =
        cb.greaterThanOrEqualTo(
                root.get("total"),
                new BigDecimal("100.00")
        );

cq.select(root).where(cb.and(statusIsOpen, totalAtLeast));

List<PurchaseOrderEntity> result =
        entityManager.createQuery(cq).getResultList();
~~~

Trong JPA Criteria:

- EntityManager cung cấp CriteriaBuilder.
- CriteriaBuilder tạo predicate và biểu thức.
- Root đại diện entity gốc trong truy vấn.
- Path truy cập thuộc tính entity.
- Join mô tả liên kết entity.
- CriteriaQuery mô tả select, where, group by, order by và các phần của query.
- Có thể tạo subquery và các biểu thức phức tạp hơn.

Spring Data Relational Criteria có mục tiêu hẹp hơn. Nó thường bắt đầu bằng tên property dạng chuỗi, tạo predicate cho Query, rồi Query được JdbcAggregateTemplate dùng để đọc aggregate. Không có EntityManager, CriteriaBuilder, Root hoặc persistence context JPA trong đường thực thi đó.

| Khía cạnh | Spring Data Relational Criteria | JPA Criteria API |
|---|---|---|
| Đối tượng được truy vấn | Aggregate mapping của Spring Data Relational | Entity JPA |
| Điểm vào | Criteria.where(...), Query.query(...) | EntityManager, CriteriaBuilder |
| Định danh property | Thường khai báo bằng tên property dạng chuỗi | Path từ Root/Join, có thể dùng static metamodel |
| Join entity | Không phải API join tổng quát tương đương JPA | Hỗ trợ Root.join(...) |
| Subquery | Không phải mục tiêu chính của Criteria relational | Hỗ trợ subquery |
| Tích hợp | JdbcAggregateTemplate và Spring Data JDBC | JPA provider và EntityManager |
| Persistence context | Không có persistence context kiểu JPA | Entity được quản lý trong persistence context |

Không nên import kiểu jakarta.persistence.criteria.CriteriaBuilder trong code Spring Data JDBC chỉ vì cả hai API đều có từ Criteria. Chúng không tương thích kiểu và không thay thế nhau.

## 5. JPA Specification là gì?

Spring Data JPA Specification là abstraction để đóng gói một predicate JPA thành một đơn vị có thể kết hợp và tái sử dụng. Nó thuộc package org.springframework.data.jpa.domain và sử dụng JPA Criteria API ở bên trong.

Ví dụ:

~~~java
import org.springframework.data.jpa.domain.Specification;

public final class PurchaseOrderSpecifications {

    public static Specification<PurchaseOrderEntity> hasStatus(String status) {
        return (root, query, cb) ->
                status == null ? cb.conjunction()
                        : cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrderEntity> totalAtLeast(
            BigDecimal minimum) {
        return (root, query, cb) ->
                minimum == null ? cb.conjunction()
                        : cb.greaterThanOrEqualTo(root.get("total"), minimum);
    }
}
~~~

Repository JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface PurchaseOrderJpaRepository
        extends JpaRepository<PurchaseOrderEntity, Long>,
                JpaSpecificationExecutor<PurchaseOrderEntity> {
}
~~~

Ghép specification:

~~~java
Specification<PurchaseOrderEntity> spec =
        Specification.where(
                PurchaseOrderSpecifications.hasStatus("OPEN"))
        .and(PurchaseOrderSpecifications.totalAtLeast(
                new BigDecimal("100.00")));

List<PurchaseOrderEntity> result =
        purchaseOrderJpaRepository.findAll(spec);
~~~

Specification giúp tách predicate thành hàm có thể kết hợp bằng and, or và not. Nó đặc biệt hữu ích khi nhiều bộ lọc được tái sử dụng giữa nhiều truy vấn JPA.

### Vì sao không thể truyền Specification vào JdbcAggregateTemplate?

Specification có chữ ký dựa trên các kiểu JPA như Root, CriteriaQuery, CriteriaBuilder và Predicate. JdbcAggregateTemplate nhận Query của Spring Data Relational. Hai API có mô hình và kiểu dữ liệu khác nhau.

Do đó, không thể làm như sau:

~~~java
Specification<PurchaseOrderEntity> spec = ...;
template.findAll(spec, PurchaseOrder.class); // Không có API tương ứng
~~~

Nếu ứng dụng dùng Spring Data JDBC, hãy xây Criteria/Query của Spring Data Relational hoặc triển khai một custom repository/SQL query phù hợp. Nếu ứng dụng dùng Spring Data JPA, Specification là lựa chọn tự nhiên khi cần ghép các predicate JPA.

## 6. Querydsl: DSL truy vấn fluent và kiểu Q được sinh

Querydsl là thư viện độc lập cung cấp API truy vấn fluent. Trong các tích hợp phổ biến, annotation processor tạo ra các lớp Q đại diện cho model, ví dụ QPurchaseOrderEntity. Thay vì viết tên property dưới dạng chuỗi, code tham chiếu property qua các trường kiểu hóa.

Ví dụ minh họa Querydsl JPA:

~~~java
QPurchaseOrderEntity order =
        QPurchaseOrderEntity.purchaseOrderEntity;

BooleanBuilder predicate = new BooleanBuilder();

if (status != null) {
    predicate.and(order.status.eq(status));
}

if (minimumTotal != null) {
    predicate.and(order.total.goe(minimumTotal));
}

List<PurchaseOrderEntity> result =
        queryFactory.selectFrom(order)
                .where(predicate)
                .fetch();
~~~

QPurchaseOrderEntity được sinh từ entity/model bởi Querydsl annotation processing. IDE và compiler có thể phát hiện nhiều lỗi sai tên property hoặc sai kiểu sớm hơn so với Criteria DSL dùng chuỗi.

Querydsl có nhiều backend, trong đó cần phân biệt:

- **Querydsl JPA** xây truy vấn qua mô hình JPA và dùng entity manager/provider.
- **Querydsl SQL** xây SQL trực tiếp qua metadata bảng/cột và JDBC connection/SQL templates.

Hai backend này không có cùng contract. Có Q-type của JPA entity không đồng nghĩa có thể dùng nó với Querydsl SQL hoặc Spring Data JDBC mà không cấu hình tương ứng.

## 7. Querydsl có được Spring Data JDBC hỗ trợ sẵn như Spring Data JPA không?

Spring Data JPA có integration quen thuộc qua QuerydslPredicateExecutor và các cơ chế repository liên quan. Không nên mặc định Spring Data JDBC có cùng integration hoặc JdbcAggregateTemplate có overload nhận Querydsl Predicate.

Nếu muốn dùng Querydsl trong ứng dụng Spring Data JDBC, có thể xem xét Querydsl SQL như một thư viện SQL riêng và kết nối qua custom repository fragment/JDBC access. Khi làm vậy, ứng dụng phải tự chịu trách nhiệm về:

- Ánh xạ kết quả SQL sang DTO hoặc domain object.
- Tên bảng/cột và dialect.
- Transaction manager và việc tham gia transaction hiện có.
- Chuyển đổi kiểu dữ liệu và nullability.
- Optimistic locking nếu câu lệnh cập nhật cần version.
- Quan hệ child và quy tắc lưu aggregate.

Querydsl SQL không tự động trở thành một đường ghi aggregate của Spring Data JDBC. Một truy vấn SQL trực tiếp không tự gọi lifecycle của JdbcAggregateTemplate hoặc áp dụng mọi quy tắc mapping/aggregate.

Vì vậy, chỉ chọn Querydsl SQL khi lợi ích về biểu thức truy vấn, type safety hoặc độ phức tạp SQL đủ lớn để chấp nhận phần tích hợp và mapping bổ sung.

## 8. So sánh khả năng và mức độ type safety

| Tiêu chí | Relational Criteria | JPA Criteria / Specification | Querydsl |
|---|---|---|---|
| API fluent | Có | Có | Có |
| Type safety của property | Hạn chế hơn vì thường dùng tên property dạng chuỗi | Có thể dùng static metamodel; API Root/Path kiểm tra kiểu ở mức biểu thức | Mạnh khi Q-type được sinh đúng |
| Ghép điều kiện động | Có, với predicate được hỗ trợ | Có, Specification và Predicate | Có, BooleanBuilder/Predicate |
| Join tùy ý | Không phải mục tiêu chính của aggregate Criteria | Có qua Root/Join | Có, tùy backend |
| Subquery | Không phải API tổng quát | Có | Có, tùy backend |
| Ánh xạ aggregate Spring Data JDBC | Có qua JdbcAggregateTemplate | Không | Không tự động |
| Repository integration | Spring Data JDBC/Relational template | JpaSpecificationExecutor, JPA repositories | Phụ thuộc backend và integration |
| Sinh code | Không cần Q-type | Có thể dùng JPA static metamodel generator | Q-type được sinh bởi annotation processor |
| SQL tùy biến phức tạp | Dùng @Query/custom JDBC khi cần | Provider tạo SQL từ Criteria | Querydsl SQL tạo SQL qua backend SQL |

Không có một công cụ thắng trong mọi trường hợp. Lựa chọn đúng phụ thuộc persistence model và độ phức tạp của query.

## 9. Khi nào dùng Spring Data Relational Criteria?

Chọn Criteria của Spring Data Relational khi:

- Ứng dụng đang dùng Spring Data JDBC.
- Truy vấn chủ yếu lọc trên property của aggregate root.
- Điều kiện có thể xây dựng động từ các tham số tùy chọn.
- Cần kết hợp Query với Sort, limit, offset hoặc Pageable.
- Kết quả mong muốn là aggregate được Spring Data JDBC ánh xạ theo metadata.
- Không cần một biểu thức JOIN/subquery SQL tổng quát.

Ví dụ:

~~~java
Criteria criteria = Criteria.where("status").is(status)
        .and("total").between(minimum, maximum);

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")));

List<PurchaseOrder> orders =
        template.findAll(query, PurchaseOrder.class);
~~~

Đây là lựa chọn tự nhiên cho một bộ lọc aggregate vừa phải và cần query động.

## 10. Khi nào dùng JPA Criteria và Specification?

Chọn JPA Criteria/Specification khi ứng dụng thực sự dùng Spring Data JPA và cần:

- Ghép nhiều predicate tái sử dụng qua nhiều use case.
- Join entity và association.
- Subquery, group by, having hoặc biểu thức JPA phức tạp.
- Tận dụng JpaSpecificationExecutor với Page, Sort hoặc query JPA.
- Làm việc trên entity được quản lý bởi persistence context JPA.

Ví dụ một màn hình tìm kiếm có nhiều bộ lọc tùy chọn:

~~~java
Specification<PurchaseOrderEntity> spec =
        Specification.where(hasStatus(status))
                .and(totalAtLeast(minimumTotal))
                .and(createdAfter(from));

Page<PurchaseOrderEntity> page =
        repository.findAll(spec, pageable);
~~~

Không nên đưa Specification vào module Spring Data JDBC chỉ vì nó có tên “Specification”. Nó là abstraction JPA và phụ thuộc vào JPA Criteria types.

## 11. Khi nào dùng Querydsl?

Querydsl phù hợp khi:

- Query có nhiều nhánh điều kiện động và muốn code type-safe hơn chuỗi property.
- Ứng dụng cần biểu thức JOIN, subquery, projection hoặc SQL động phức tạp.
- Backend Querydsl đã được lựa chọn rõ: JPA hay SQL.
- Dự án chấp nhận cấu hình annotation processor và generated Q-types.
- Có thể quản lý mapping, transaction và lifecycle tương ứng với backend.

Nếu ứng dụng đang dùng Spring Data JDBC, Querydsl SQL có thể là một lựa chọn custom cho read/report query phức tạp. Nhưng nếu query chỉ lọc một vài property của aggregate root, thêm Querydsl có thể tạo nhiều cấu hình hơn lợi ích nhận được.

## 12. Cách lựa chọn cho một use case cụ thể

Giả sử màn hình tìm đơn hàng có các bộ lọc status, khoảng tổng tiền, thời gian tạo, sort và page:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Spring Data JDBC, lọc vài property của root | Criteria + Query + JdbcAggregateTemplate |
| Spring Data JDBC, method cố định, dễ đọc | Derived repository query |
| Spring Data JDBC, SQL JOIN/report phức tạp | @Query hoặc custom repository fragment/JdbcTemplate |
| Spring Data JPA, predicate tái sử dụng | Specification + JpaSpecificationExecutor |
| Spring Data JPA, query động phức tạp và type-safe | Querydsl JPA |
| SQL trực tiếp, query DSL type-safe và custom mapping được chấp nhận | Querydsl SQL/custom repository |

Quy tắc thực tế:

1. Dùng repository derived method cho điều kiện ổn định, ngắn và dễ hiểu.
2. Dùng Relational Criteria cho bộ lọc động vừa phải trên aggregate trong Spring Data JDBC.
3. Dùng @Query hoặc custom JDBC fragment khi cần SQL cụ thể, JOIN hoặc projection.
4. Dùng Specification khi persistence layer là JPA.
5. Dùng Querydsl khi lợi ích của DSL/type safety xứng đáng với cấu hình và backend integration.

## 13. Không trộn các abstraction trong cùng một method

Những kiểu sau thuộc các package và mô hình khác nhau:

~~~java
org.springframework.data.relational.core.query.Criteria
org.springframework.data.relational.core.query.Query

jakarta.persistence.criteria.CriteriaBuilder
jakarta.persistence.criteria.CriteriaQuery
org.springframework.data.jpa.domain.Specification

com.querydsl.core.types.Predicate
com.querydsl.core.BooleanBuilder
~~~

Một method nhận Spring Data Relational Query không thể nhận JPA Specification hoặc Querydsl Predicate nếu không có adapter tự viết. Cũng không thể truyền JPA Root vào Criteria.where của Spring Data Relational.

Nếu codebase có cả Spring Data JDBC và Spring Data JPA, hãy đặt abstraction ở đúng module/repository. Tránh tạo một interface dùng tên chung Criteria rồi trả các kiểu không tương thích, vì người dùng API khó biết query được thực thi bởi persistence technology nào.

## 14. Các giới hạn cần nhớ của Relational Criteria

Criteria của Spring Data Relational có chủ đích nhỏ hơn một query language tổng quát:

- Nó mô tả predicate và các thuộc tính query mà Spring Data Relational hỗ trợ.
- QueryMapper chuyển metadata và Criteria thành SQL theo dialect.
- Nó phù hợp với truy vấn aggregate đã được mapping, không phải API dựng tùy ý nhiều root và JOIN như JPA Criteria.
- Không có persistence context, dirty checking hoặc JPA association traversal.
- Không tự cung cấp toàn bộ khả năng Specification hoặc Querydsl.
- Khi cần projection hoặc SQL phức tạp, có thể dùng @Query, custom fragment, JdbcTemplate hoặc một SQL DSL riêng.

Đừng nhầm giới hạn này với việc Spring Data JDBC không thể chạy SQL JOIN. JDBC có thể thực thi JOIN qua @Query hoặc custom JDBC code; điều khác biệt là Criteria/Query của aggregate template không phải một DSL tổng quát để mô tả mọi kiểu JOIN và ánh xạ tùy ý.

## 15. Kiểm soát tên property, kiểu dữ liệu và giá trị đầu vào

Criteria thường nhận tên property dưới dạng String. Điều này thuận tiện nhưng compiler không thể phát hiện mọi lỗi gõ sai tên ngay tại thời điểm biên dịch:

~~~java
Criteria.where("stauts").is("OPEN"); // Sai chính tả, có thể chỉ phát hiện lúc thực thi
~~~

Hãy dùng hằng số hoặc helper khi tên property xuất hiện ở nhiều nơi, nhưng vẫn cần kiểm tra metadata và query thực tế. Với các property có @Column, embedded prefix hoặc naming strategy tùy chỉnh, cần hiểu tên được phân giải trong mapping.

Giá trị đầu vào nên được kiểm tra trước khi tạo Criteria:

~~~java
if (minimumTotal != null && minimumTotal.signum() < 0) {
    throw new IllegalArgumentException("minimumTotal không được âm");
}
~~~

Không nhận tên property hoặc biểu thức sort tùy ý từ request rồi đưa trực tiếp vào Criteria/Sort. Hãy dùng whitelist các trường cho phép. Giá trị điều kiện được bind an toàn, nhưng tên property là metadata truy vấn và cần được kiểm soát riêng.

## 16. Ví dụ hoàn chỉnh: service tìm kiếm bằng Criteria

Ví dụ dưới đây kết hợp điều kiện tùy chọn, sort và phân trang. Nó dùng Criteria của Spring Data Relational, không dùng JPA Specification:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderSearchService {
    private final JdbcAggregateTemplate template;

    public PurchaseOrderSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional(readOnly = true)
    public Page<PurchaseOrder> search(
            String status,
            BigDecimal minimumTotal,
            Pageable pageable
    ) {
        Criteria criteria = Criteria.empty();

        if (status != null && !status.isBlank()) {
            criteria = criteria.and("status").is(status);
        }

        if (minimumTotal != null) {
            criteria = criteria.and("total")
                    .greaterThanOrEquals(minimumTotal);
        }

        Query baseQuery = Query.query(criteria);
        List<PurchaseOrder> content = template.findAll(
                baseQuery.with(pageable),
                PurchaseOrder.class
        );
        long total = template.count(baseQuery, PurchaseOrder.class);

        return new PageImpl<>(content, pageable, total);
    }
}
~~~

Đây là cách triển khai có chủ đích cho trường hợp Spring Data JDBC cần một Page. Cần kiểm tra API Criteria.empty() và cách ghép predicate theo đúng phiên bản Spring Data Relational của dự án; nếu version đó không hỗ trợ cách khởi tạo/ghép trên, khởi tạo Criteria từ predicate đầu tiên rồi thêm các điều kiện còn lại.

## 17. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Relational Criteria chính là JPA Criteria API | Hai API độc lập, package và mô hình thực thi khác nhau |
| Specification dùng được với mọi Spring Data repository | Specification chuẩn thuộc Spring Data JPA và dựa trên JPA Criteria |
| JdbcAggregateTemplate nhận Specification | Template nhận Query/Criteria của Spring Data Relational |
| Querydsl luôn tích hợp sẵn với mọi module Spring Data | Integration phụ thuộc module/backend; không mặc định có QuerydslPredicateExecutor cho Spring Data JDBC |
| Querydsl SQL tự ánh xạ aggregate Spring Data JDBC | Querydsl SQL là đường SQL riêng; mapping và lifecycle cần xử lý riêng |
| Relational Criteria có thể dựng mọi JOIN như JPA | Criteria aggregate có phạm vi nhỏ hơn; dùng SQL/custom fragment cho JOIN phức tạp |
| Criteria type-safe như Q-type Querydsl | Tên property thường là String, nên có thể có lỗi tên chỉ lộ ra khi chạy |
| Dùng Querydsl luôn tốt hơn Criteria | DSL mạnh hơn có chi phí cấu hình và tích hợp; chọn theo độ phức tạp thực tế |

## 18. Bài thực hành so sánh ba cách viết

Với use case tìm đơn hàng đang mở có tổng tiền từ 100 trở lên:

**A. Spring Data JDBC Relational Criteria**

~~~java
Criteria criteria = Criteria.where("status").is("OPEN")
        .and("total").greaterThanOrEquals(new BigDecimal("100.00"));

List<PurchaseOrder> result = template.findAll(
        Query.query(criteria),
        PurchaseOrder.class
);
~~~

**B. Spring Data JPA Specification**

~~~java
Specification<PurchaseOrderEntity> spec =
        Specification.where(hasStatus("OPEN"))
                .and(totalAtLeast(new BigDecimal("100.00")));

List<PurchaseOrderEntity> result = jpaRepository.findAll(spec);
~~~

**C. Querydsl JPA**

~~~java
QPurchaseOrderEntity order =
        QPurchaseOrderEntity.purchaseOrderEntity;

List<PurchaseOrderEntity> result = queryFactory.selectFrom(order)
        .where(
                order.status.eq("OPEN"),
                order.total.goe(new BigDecimal("100.00"))
        )
        .fetch();
~~~

So sánh:

- A trả aggregate Spring Data JDBC qua JdbcAggregateTemplate.
- B tạo predicate JPA có thể tái sử dụng và thực thi qua JpaSpecificationExecutor.
- C dùng Q-type và Querydsl JPA để xây predicate type-safe.

Không ghép ba đoạn code thành một repository method. Mỗi đoạn thuộc một persistence stack và cần cấu hình tương ứng.

## 19. Nguyên tắc ghi nhớ

- Spring Data Relational Criteria là DSL nhỏ để xây điều kiện cho Query và các thao tác Spring Data JDBC.
- Query kết hợp Criteria với sort, limit, offset và các thành phần truy vấn khác; JdbcAggregateTemplate thực thi query trên aggregate.
- JPA Criteria API dùng CriteriaBuilder, CriteriaQuery, Root, Path, Join và Predicate qua EntityManager.
- Spring Data JPA Specification đóng gói và kết hợp predicate JPA; nó không phải abstraction chung cho Spring Data JDBC.
- Querydsl cung cấp DSL fluent và Q-type được sinh; cần phân biệt Querydsl JPA với Querydsl SQL.
- Spring Data JDBC không mặc định cung cấp cùng QuerydslPredicateExecutor integration như Spring Data JPA.
- Relational Criteria không phải query builder tổng quát cho mọi JOIN/subquery; dùng @Query hoặc custom JDBC khi cần SQL phức tạp.
- Chọn công cụ theo persistence model, độ phức tạp truy vấn, nhu cầu type safety và chi phí tích hợp.

Khi làm việc với Spring Data JDBC, hãy bắt đầu bằng Criteria/Query của Spring Data Relational cho bộ lọc động vừa phải trên aggregate. Nếu ứng dụng dùng JPA và cần predicate tái sử dụng, Specification là lựa chọn phù hợp; nếu cần DSL type-safe mạnh và đã chọn backend tương ứng, cân nhắc Querydsl. Việc phân biệt đúng các abstraction giúp tránh ghép nhầm API và giữ cho truy vấn, mapping cùng ranh giới aggregate nhất quán với persistence technology đang sử dụng.

## Tài liệu tham khảo

- [Spring Data Relational — Querying](https://docs.spring.io/spring-data/relational/reference/jdbc/querying.html)
- [Spring Data Relational API — Criteria](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/query/Criteria.html)
- [Spring Data Relational API — Query](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/query/Query.html)
- [Spring Data JDBC API — JdbcAggregateTemplate](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Jakarta Persistence — Criteria API](https://jakarta.ee/specifications/persistence/)
- [Querydsl Reference](https://querydsl.com/static/querydsl/latest/reference/html_single/)
