# count và exists từ cùng một bộ điều kiện

Trong Spring Data JDBC, một màn hình tìm kiếm hoặc một use case nghiệp vụ thường cần biết hai điều về cùng một tập aggregate: có bao nhiêu aggregate thỏa điều kiện và có ít nhất một aggregate thỏa điều kiện hay không.

Ví dụ, trang quản lý đơn hàng có thể hiển thị tổng số đơn đang chờ xử lý, đồng thời cần biết có đơn nào cần nhân viên chú ý hay không. Nếu mỗi thao tác tự xây dựng một bộ điều kiện riêng, chúng có thể dần khác nhau khi nghiệp vụ thay đổi. Kết quả đếm và kết quả kiểm tra tồn tại khi đó không còn mô tả cùng một tập dữ liệu.

Spring Data JDBC cung cấp `JdbcAggregateTemplate.count(Query, Class<T>)` và `JdbcAggregateTemplate.exists(Query, Class<T>)`. Ta có thể xây dựng một đối tượng `Query` từ `Criteria`, sau đó truyền chính đối tượng đó vào cả hai phương thức. Cách này giữ cho hai thao tác dùng cùng một định nghĩa điều kiện.

## 1. count và exists giải quyết hai nhu cầu khác nhau

`count` trả về số lượng aggregate thỏa điều kiện. Kiểu trả về là `long`, phù hợp với số lượng có thể lớn hơn giới hạn của `int`.

`exists` trả về `boolean`:

- `true` nếu có ít nhất một aggregate thỏa điều kiện.
- `false` nếu không có aggregate nào thỏa điều kiện.

Hai phương thức làm việc trên aggregate type được truyền vào, không phải tự động đếm mọi hàng ở tất cả bảng thành viên của aggregate.

| Nhu cầu | Phương thức |
|---|---|
| Hiển thị tổng số đơn hàng phù hợp | `count(query, PurchaseOrder.class)` |
| Kiểm tra có đơn nào cần xử lý không | `exists(query, PurchaseOrder.class)` |
| Kiểm tra aggregate theo ID | `existsById(id, PurchaseOrder.class)` |
| Đếm tất cả aggregate của một kiểu | `count(PurchaseOrder.class)` |

Không nên gọi `count(...) > 0` khi chỉ cần biết có dữ liệu hay không. `exists(...)` diễn đạt đúng ý định và trả về kiểu boolean trực tiếp. Tương tự, nếu chỉ cần số lượng thì không cần tải toàn bộ aggregate bằng `findAll(...)` rồi đếm trong Java.

### 1.1. API thuộc JdbcAggregateTemplate

`JdbcAggregateTemplate` triển khai `JdbcAggregateOperations`. Hai phương thức truy vấn động có chữ ký tổng quát:

```java
<T> long count(Query query, Class<T> domainType);

<T> boolean exists(Query query, Class<T> domainType);
```

Cả hai nhận:

- `query`: đối tượng mô tả điều kiện truy vấn; không được null.
- `domainType`: kiểu aggregate root cần đếm hoặc kiểm tra; không được null.

Ví dụ:

```java
long count = aggregateTemplate.count(
    query,
    PurchaseOrder.class
);

boolean hasMatch = aggregateTemplate.exists(
    query,
    PurchaseOrder.class
);
```

Hai API này được giới thiệu từ **Spring Data Relational 3.0**. Nếu dự án đang dùng release train cũ hơn, hãy kiểm tra JavaDoc đúng phiên bản trước khi sử dụng.

## 2. Query và Criteria

`Criteria` biểu diễn các điều kiện trong mệnh đề WHERE. `Query` đóng gói Criteria cùng những thành phần khác có thể cần cho một truy vấn như cột projection, sort, limit và offset.

Ví dụ một điều kiện đơn giản:

```java
Criteria criteria = Criteria.where("status").is("PENDING");

Query query = Query.query(criteria);
```

Điều kiện trên tương ứng với ý nghĩa SQL:

```sql
WHERE status = 'PENDING'
```

Sau đó có thể dùng query cho cả hai thao tác:

```java
long pendingCount =
    aggregateTemplate.count(query, PurchaseOrder.class);

boolean hasPending =
    aggregateTemplate.exists(query, PurchaseOrder.class);
```

Khi cả hai nhận cùng một `Query`, điều kiện lọc được định nghĩa ở một nơi. Nếu sau này cần thêm điều kiện khách hàng hoặc ngày tạo, chỉ cần thay đổi phần xây dựng query.

### 2.1. Query và Criteria là API bất biến

Các API fluent của `Query` và `Criteria` tạo ra đối tượng mới khi nối thêm điều kiện hoặc tùy chọn. Chúng không sửa đối tượng ban đầu.

Ví dụ:

```java
Query baseQuery = Query.query(
    Criteria.where("status").is("PENDING")
);

Query limitedQuery = baseQuery.limit(20);
```

`baseQuery` vẫn là query ban đầu; `limitedQuery` là query mới có giới hạn. Vì vậy, khi thêm cấu hình, cần gán kết quả trả về:

```java
query = query.limit(20);
```

Cách viết sau không giữ lại thay đổi:

```java
query.limit(20); // Giá trị trả về bị bỏ qua.
```

Đối với mục tiêu dùng cùng điều kiện cho count và exists, hãy tạo một query lọc hoàn chỉnh rồi giữ lại reference đó để truyền cho cả hai phương thức.

## 3. Tạo một Query đơn giản rồi dùng lại

Giả sử bảng đơn hàng có các cột `status` và `customer_id`. Ta muốn đếm và kiểm tra đơn đang chờ của một khách hàng.

```java
Criteria criteria = Criteria.where("status").is("PENDING")
    .and("customer_id").is(customerId);

Query query = Query.query(criteria);

long count = aggregateTemplate.count(
    query,
    PurchaseOrder.class
);

boolean exists = aggregateTemplate.exists(
    query,
    PurchaseOrder.class
);
```

Cả hai phép gọi cùng sử dụng hai điều kiện:

1. Trạng thái là `PENDING`.
2. `customer_id` bằng ID khách hàng được truyền vào.

Không cần viết lại Criteria lần thứ hai cho exists.

### 3.1. Ví dụ trong application service

```java
@Service
public class OrderQueryService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public OrderQueryService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    public PendingOrderSummary summarizePendingOrders(Long customerId) {
        Query query = Query.query(
            Criteria.where("status").is(OrderStatus.PENDING)
                .and("customer_id").is(customerId)
        );

        long count = aggregateTemplate.count(
            query,
            PurchaseOrder.class
        );

        boolean exists = aggregateTemplate.exists(
            query,
            PurchaseOrder.class
        );

        return new PendingOrderSummary(count, exists);
    }
}

public record PendingOrderSummary(
    long count,
    boolean exists
) {}
```

Service tạo query một lần rồi tái sử dụng. Khi điều kiện lọc thay đổi, cả count và exists tiếp tục dùng cùng định nghĩa mới.

Ví dụ giả định entity ánh xạ `customerId` sang cột `customer_id` và có trường `status`. Hãy dùng tên cột/property phù hợp với mapping thực tế, nhất là khi có `@Column` hoặc naming strategy tùy chỉnh.

## 4. Xây dựng điều kiện động từ filter

Trong thực tế, filter tìm kiếm thường có nhiều trường tùy chọn. Người dùng có thể chỉ nhập trạng thái, hoặc kết hợp trạng thái, khách hàng, ngày tạo và tổng tiền tối thiểu.

Ta có thể xây dựng `Criteria` từng bước. Chỉ thêm điều kiện khi filter tương ứng có giá trị.

```java
public record OrderFilter(
    OrderStatus status,
    Long customerId,
    LocalDateTime createdFrom,
    BigDecimal minimumTotal
) {}
```

Hàm xây dựng query:

```java
private Query buildQuery(OrderFilter filter) {
    Criteria criteria = Criteria.empty();

    if (filter.status() != null) {
        criteria = criteria.and("status").is(filter.status());
    }

    if (filter.customerId() != null) {
        criteria = criteria.and("customer_id").is(filter.customerId());
    }

    if (filter.createdFrom() != null) {
        criteria = criteria.and("created_at")
            .greaterThanOrEquals(filter.createdFrom());
    }

    if (filter.minimumTotal() != null) {
        criteria = criteria.and("total")
            .greaterThanOrEquals(filter.minimumTotal());
    }

    return criteria.isEmpty()
        ? Query.empty()
        : Query.query(criteria);
}
```

Sau khi tạo query, service có thể dùng lại:

```java
public OrderSearchSummary summarize(OrderFilter filter) {
    Query query = buildQuery(filter);

    long count = aggregateTemplate.count(
        query,
        PurchaseOrder.class
    );

    boolean exists = aggregateTemplate.exists(
        query,
        PurchaseOrder.class
    );

    return new OrderSearchSummary(count, exists);
}
```

Khi filter không có trường nào được cung cấp, hàm trả về `Query.empty()`. Query rỗng không có điều kiện lọc, do đó các phép đếm/kiểm tra áp dụng cho toàn bộ aggregate type tương ứng. Nếu nghiệp vụ không cho phép tìm kiếm không có điều kiện, hãy kiểm tra filter trước khi tạo query và trả lỗi validation phù hợp.

### 4.1. Chỉ thêm điều kiện khi có giá trị

Không nên biến trường filter vắng mặt thành một điều kiện so sánh với null một cách vô tình.

Ví dụ:

```java
Criteria.where("customer_id").is(filter.customerId());
```

Nếu `customerId` là null vì người dùng không chọn khách hàng, điều kiện này không còn mang ý nghĩa “bỏ qua bộ lọc khách hàng”. Nó có thể trở thành điều kiện tìm giá trị NULL.

Thay vào đó:

```java
if (filter.customerId() != null) {
    criteria = criteria.and("customer_id").is(filter.customerId());
}
```

Nếu người dùng thực sự muốn tìm các hàng có cột NULL, hãy diễn đạt ý định đó bằng `isNull()`:

```java
Criteria criteria = Criteria.where("assigned_to").isNull();
```

Phân biệt rõ “không gửi filter” với “lọc các giá trị NULL”.

### 4.2. Điều kiện khoảng

Criteria hỗ trợ các phép so sánh như:

| Criteria | Ý nghĩa SQL |
|---|---|
| `is(value)` | `=` |
| `not(value)` | `<>` |
| `greaterThan(value)` | `>` |
| `greaterThanOrEquals(value)` | `>=` |
| `lessThan(value)` | `<` |
| `lessThanOrEquals(value)` | `<=` |
| `in(values)` | `IN (...)` |
| `notIn(values)` | `NOT IN (...)` |
| `isNull()` | `IS NULL` |
| `isNotNull()` | `IS NOT NULL` |
| `like(pattern)` | `LIKE` |

Ví dụ khoảng ngày:

```java
Criteria criteria = Criteria.where("created_at")
    .greaterThanOrEquals(from)
    .and("created_at")
    .lessThan(to);
```

Trong code thực tế, để dễ đọc và tránh nối nhầm điều kiện, có thể tạo hai Criteria riêng rồi kết hợp:

```java
Criteria criteria = Criteria.where("created_at")
    .greaterThanOrEquals(from)
    .and(Criteria.where("created_at").lessThan(to));
```

Cả count và exists sẽ nhận cùng Query được tạo từ Criteria này.

## 5. Kết hợp AND và OR

`Criteria` hỗ trợ kết hợp nhiều điều kiện bằng AND và OR. Khi có nhóm điều kiện, hãy tạo nhóm rõ ràng để tránh thay đổi ý nghĩa logic.

Ví dụ: tìm đơn của một khách hàng có trạng thái PAID hoặc SHIPPED.

```java
Criteria completedStatus = Criteria.where("status").is("PAID")
    .or(Criteria.where("status").is("SHIPPED"));

Criteria criteria = Criteria.where("customer_id").is(customerId)
    .and(completedStatus);

Query query = Query.query(criteria);
```

Ý nghĩa logic:

```sql
WHERE customer_id = :customerId
  AND (status = 'PAID' OR status = 'SHIPPED')
```

Sau đó:

```java
long count = aggregateTemplate.count(query, PurchaseOrder.class);
boolean exists = aggregateTemplate.exists(query, PurchaseOrder.class);
```

### 5.1. Vì sao cần nhóm điều kiện?

Giả sử điều kiện là:

```sql
customer_id = 42
AND (status = 'PAID' OR status = 'SHIPPED')
```

Nếu nối điều kiện không đúng nhóm, logic có thể thành:

```sql
(customer_id = 42 AND status = 'PAID')
OR status = 'SHIPPED'
```

Hai biểu thức không tương đương. Biểu thức thứ hai cho phép đơn SHIPPED của bất kỳ khách hàng nào.

Khi điều kiện có cả AND và OR, hãy chia thành các Criteria group rồi kết hợp. Điều này giúp cả count và exists áp dụng cùng một biểu thức logic đã được xác định rõ.

## 6. Tách phần xây dựng query khỏi phần thực thi

Khi ứng dụng có nhiều màn hình hoặc use case dùng cùng bộ điều kiện, nên đặt logic xây dựng query vào một phương thức riêng hoặc một component chuyên trách.

Ví dụ:

```java
@Component
public class OrderCriteriaFactory {

    public Query from(OrderFilter filter) {
        Criteria criteria = Criteria.empty();

        if (filter.status() != null) {
            criteria = criteria.and("status").is(filter.status());
        }

        if (filter.customerId() != null) {
            criteria = criteria.and("customer_id").is(filter.customerId());
        }

        if (filter.createdFrom() != null) {
            criteria = criteria.and("created_at")
                .greaterThanOrEquals(filter.createdFrom());
        }

        if (filter.createdTo() != null) {
            criteria = criteria.and("created_at")
                .lessThan(filter.createdTo());
        }

        return criteria.isEmpty()
            ? Query.empty()
            : Query.query(criteria);
    }
}
```

Service dùng factory:

```java
@Service
public class OrderQueryService {

    private final JdbcAggregateTemplate template;
    private final OrderCriteriaFactory criteriaFactory;

    public OrderQueryService(
            JdbcAggregateTemplate template,
            OrderCriteriaFactory criteriaFactory) {
        this.template = template;
        this.criteriaFactory = criteriaFactory;
    }

    public long count(OrderFilter filter) {
        Query query = criteriaFactory.from(filter);
        return template.count(query, PurchaseOrder.class);
    }

    public boolean exists(OrderFilter filter) {
        Query query = criteriaFactory.from(filter);
        return template.exists(query, PurchaseOrder.class);
    }

    public OrderSearchSummary summarize(OrderFilter filter) {
        Query query = criteriaFactory.from(filter);

        return new OrderSearchSummary(
            template.count(query, PurchaseOrder.class),
            template.exists(query, PurchaseOrder.class)
        );
    }
}
```

Cách tổ chức này có hai lợi ích:

- Các use case sử dụng cùng một định nghĩa điều kiện.
- Khi nghiệp vụ thay đổi, chỉ cần cập nhật logic tạo Criteria ở một nơi.

Nếu chỉ có một nơi sử dụng, một private method trong service có thể đủ. Không cần tạo thêm abstraction khi nó chưa giúp giảm lặp hoặc làm rõ trách nhiệm.

## 7. Dùng cùng Query cho findAll, count và exists

Ngoài count và exists, `JdbcAggregateTemplate` còn có phương thức `findAll(Query, Class<T>)` để tải aggregate phù hợp.

Một query lọc có thể được dùng làm nền cho cả ba nhu cầu:

```java
Query filterQuery = Query.query(
    Criteria.where("status").is(OrderStatus.PENDING)
        .and("customer_id").is(customerId)
);

long count = template.count(filterQuery, PurchaseOrder.class);

boolean exists = template.exists(filterQuery, PurchaseOrder.class);

List<PurchaseOrder> orders =
    template.findAll(filterQuery, PurchaseOrder.class);
```

Điểm quan trọng là ba thao tác cùng dùng điều kiện lọc. `findAll` tải aggregate, `count` trả số lượng và `exists` trả câu trả lời có/không.

### 7.1. Tạo query phân trang riêng từ cùng Criteria

Nếu cần danh sách có phân trang, hãy giữ Criteria làm nguồn điều kiện rồi tạo Query khác có sort, limit và offset:

```java
Criteria criteria = Criteria.where("status").is("PENDING")
    .and("customer_id").is(customerId);

Query filterQuery = Query.query(criteria);

Query pageQuery = Query.query(criteria)
    .sort(Sort.by(Sort.Order.desc("created_at")))
    .limit(20)
    .offset(40);

long count = template.count(filterQuery, PurchaseOrder.class);
boolean exists = template.exists(filterQuery, PurchaseOrder.class);

List<PurchaseOrder> page =
    template.findAll(pageQuery, PurchaseOrder.class);
```

`filterQuery` giữ toàn bộ tập kết quả cần đếm/kiểm tra. `pageQuery` bổ sung thứ tự và giới hạn cho danh sách hiển thị.

Không nên vô tình dùng query có `limit` hoặc `offset` làm định nghĩa tổng số bản ghi của màn hình nếu mục tiêu là tổng số tất cả kết quả phù hợp. Hãy tách query lọc và query phân trang để ý định được rõ ràng.

### 7.2. Immutable Query và việc gán lại

Các phương thức `sort`, `limit`, `offset` trả về Query mới. Vì vậy:

```java
Query pageQuery = filterQuery
    .sort(Sort.by("created_at"))
    .limit(20)
    .offset(40);
```

Không gọi các phương thức này rồi bỏ qua giá trị trả về. Query gốc vẫn giữ nguyên, đúng với cách thiết kế bất biến của API.

## 8. Count và exists không tải toàn bộ aggregate

Nếu cần số lượng, `count` trả về một con số thay vì yêu cầu ứng dụng tải mọi aggregate rồi gọi `size()`.

Nếu cần kiểm tra tồn tại, `exists` trả về boolean thay vì tải một danh sách rồi kiểm tra danh sách rỗng.

Ví dụ không nên dùng:

```java
List<PurchaseOrder> orders =
    template.findAll(query, PurchaseOrder.class);

boolean exists = !orders.isEmpty();
long count = orders.size();
```

Cách này có thể tải nhiều dữ liệu hơn cần thiết, bao gồm các member của aggregate, rồi mới tính kết quả trong bộ nhớ.

Dùng API chuyên biệt:

```java
long count = template.count(query, PurchaseOrder.class);
boolean exists = template.exists(query, PurchaseOrder.class);
```

SQL cụ thể được Spring Data JDBC và dialect xử lý. Không nên giả định mọi database đều sinh chính xác cùng một câu SQL nội bộ; hãy dựa vào contract của API và kiểm tra log/plan nếu cần tối ưu hiệu năng.

### 8.1. Không gọi cả hai nếu use case chỉ cần một kết quả

Nếu trang chỉ cần hiển thị số lượng, gọi `count`.

Nếu một quy tắc chỉ cần biết có bản ghi nào tồn tại, gọi `exists`.

Chỉ gọi cả hai khi giao diện hoặc nghiệp vụ thực sự cần cả số lượng và trạng thái có/không. Việc tái sử dụng Query giúp tránh lặp điều kiện, nhưng không có nghĩa mọi use case đều phải thực hiện hai truy vấn.

## 9. count và exists với repository query methods

Nếu điều kiện cố định và đơn giản, Spring Data JDBC repository có thể cung cấp query methods như:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    long countByStatus(OrderStatus status);

    boolean existsByStatus(OrderStatus status);

    long countByCustomerIdAndStatus(
        Long customerId,
        OrderStatus status
    );

    boolean existsByCustomerIdAndStatus(
        Long customerId,
        OrderStatus status
    );
}
```

Đây là cách ngắn gọn khi bộ điều kiện đã biết trước trong tên phương thức.

Tuy nhiên, khi filter có nhiều trường tùy chọn, việc tạo nhiều cặp `countBy...` và `existsBy...` có thể làm repository phình to. `Query` và `Criteria` cho phép xây dựng điều kiện động tại runtime rồi dùng chung cho các phép thao tác.

| Trường hợp | Cách phù hợp |
|---|---|
| Điều kiện cố định, ít trường | Derived repository query method |
| Filter tùy chọn thay đổi theo request | `Query` + `Criteria` |
| Cần count và exists cùng predicate động | Một `Query` dùng cho cả hai |
| Cần SQL đặc thù hoặc phép tổng hợp phức tạp | `@Query` hoặc JDBC query chuyên biệt |
| Chỉ kiểm tra một ID cụ thể | `existsById(id, domainType)` hoặc repository `existsById(id)` |

## 10. Những lưu ý về tính nhất quán dữ liệu

Tái sử dụng một `Query` bảo đảm hai thao tác có cùng định nghĩa điều kiện lọc. Nó không có nghĩa hai lần truy vấn luôn quan sát cùng một trạng thái database.

Ví dụ:

1. `count(query, PurchaseOrder.class)` trả về 5.
2. Một transaction khác thêm một đơn phù hợp.
3. `exists(query, PurchaseOrder.class)` chạy sau đó và trả về true.

Trong ví dụ này, hai kết quả vẫn tương thích. Nhưng nếu có thao tác xóa hoặc cập nhật đồng thời, kết quả của hai lần gọi có thể phản ánh trạng thái database ở hai thời điểm khác nhau.

Nếu nghiệp vụ cần các kết quả được quan sát trong cùng một snapshot nhất quán, cần xem xét transaction boundary và isolation level mà database hỗ trợ. Chỉ dùng cùng một object Query không tạo ra snapshot transaction.

### 10.1. Cùng Query không đồng nghĩa cùng transaction

Có thể gọi count và exists trong cùng một service method. Nếu cần transaction, đặt `@Transactional` ở application service theo yêu cầu nghiệp vụ:

```java
@Transactional(readOnly = true)
public OrderSearchSummary summarize(OrderFilter filter) {
    Query query = criteriaFactory.from(filter);

    return new OrderSearchSummary(
        template.count(query, PurchaseOrder.class),
        template.exists(query, PurchaseOrder.class)
    );
}
```

`readOnly = true` là hint cho transaction infrastructure; mức độ thực thi phụ thuộc database/driver. Nó không tự bảo đảm mọi database sử dụng snapshot isolation.

## 11. Kiểm thử việc dùng cùng bộ điều kiện

Nên kiểm thử ít nhất ba tình huống:

1. Có nhiều aggregate phù hợp: count trả đúng số và exists là true.
2. Không có aggregate phù hợp: count bằng 0 và exists là false.
3. Filter tùy chọn: mỗi trường được thêm vào Criteria khi có giá trị và được bỏ qua khi không có giá trị.

Ví dụ repository/integration test với database:

```java
@DataJdbcTest
class OrderCountAndExistsTest {

    @Autowired
    JdbcAggregateTemplate template;

    @Test
    void countAndExistsUseTheSameCriteria() {
        insertOrder("ORD-1", "PENDING", 42L);
        insertOrder("ORD-2", "PENDING", 42L);
        insertOrder("ORD-3", "PAID", 42L);
        insertOrder("ORD-4", "PENDING", 99L);

        Query query = Query.query(
            Criteria.where("status").is("PENDING")
                .and("customer_id").is(42L)
        );

        long count = template.count(query, PurchaseOrder.class);
        boolean exists = template.exists(query, PurchaseOrder.class);

        assertThat(count).isEqualTo(2L);
        assertThat(exists).isTrue();
    }

    @Test
    void returnsZeroAndFalseWhenNoAggregateMatches() {
        Query query = Query.query(
            Criteria.where("status").is("CANCELLED")
        );

        assertThat(template.count(query, PurchaseOrder.class))
            .isZero();

        assertThat(template.exists(query, PurchaseOrder.class))
            .isFalse();
    }
}
```

Ví dụ giả định helper `insertOrder` tạo dữ liệu phù hợp với schema test và entity `PurchaseOrder` ánh xạ đúng các cột. Nếu test dùng `@DataJdbcTest`, dữ liệu thường nằm trong transaction test và được rollback sau mỗi test.

### 11.1. Kiểm tra filter động

Với builder, có thể kiểm tra bằng integration test:

- Chỉ truyền status thì kết quả không bị giới hạn theo customer.
- Truyền customer ID thì chỉ lấy đơn của customer đó.
- Truyền ngày bắt đầu/kết thúc thì biên thời gian đúng.
- Không truyền trường tùy chọn không vô tình tạo điều kiện `IS NULL`.
- Filter rỗng được xử lý theo chính sách nghiệp vụ đã chọn.

### 11.2. Kiểm tra cùng predicate, không kiểm tra chi tiết SQL nội bộ

Mục tiêu của test là xác nhận count và exists dùng cùng bộ lọc và trả kết quả đúng trên database. Tránh khóa test vào chuỗi SQL nội bộ nếu đó không phải contract của ứng dụng; SQL có thể khác theo dialect hoặc phiên bản Spring Data.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Count và exists cho kết quả khác nhau | Hai nơi tự xây dựng điều kiện riêng hoặc dữ liệu đổi giữa hai lần gọi | Tạo một Query dùng chung; dùng transaction/isolation nếu cần snapshot |
| Bộ lọc tùy chọn tìm các giá trị NULL | Luôn thêm điều kiện dù filter không có giá trị | Chỉ thêm Criteria khi filter được cung cấp |
| Query phân trang làm sai tổng số hiển thị | Dùng nhầm query có limit/offset để biểu diễn toàn bộ tập kết quả | Tạo filter Query riêng và page Query riêng |
| Gọi limit() nhưng không thấy giới hạn | Bỏ qua Query mới được trả về | Gán lại kết quả của API fluent |
| Chỉ cần boolean nhưng tải nhiều aggregate | Dùng findAll rồi kiểm tra danh sách | Dùng exists(query, type) |
| Chỉ cần số lượng nhưng tải toàn bộ aggregate | Dùng findAll rồi lấy size | Dùng count(query, type) |
| Criteria AND/OR lọc sai khách hàng | Không nhóm biểu thức OR | Tạo Criteria group rõ ràng |
| Điều kiện không khớp cột đã ánh xạ | Dùng tên cột/property không tương ứng với mapping | Kiểm tra naming strategy và @Column |
| Count bị giới hạn ở kiểu int | Dùng int để lưu số lượng | Dùng long |
| Không biên dịch được phương thức count/exists có Query | Spring Data Relational quá cũ | Kiểm tra phiên bản; API có từ 3.0 |
| Filter rỗng trả toàn bộ dữ liệu ngoài ý muốn | Không định nghĩa chính sách cho query không có điều kiện | Validate filter hoặc chủ động cho phép Query.empty() |

## 13. Quy trình áp dụng

Khi cần đếm và kiểm tra tồn tại từ cùng bộ điều kiện, hãy thực hiện theo thứ tự:

1. Xác định aggregate root cần truy vấn.
2. Xác định các trường filter và trường nào là tùy chọn.
3. Xây dựng `Criteria` từ các điều kiện thực sự được cung cấp.
4. Tạo một `Query` từ Criteria đó.
5. Dùng cùng Query cho `count(query, DomainType.class)` và `exists(query, DomainType.class)`.
6. Nếu cần danh sách phân trang, tạo Query mới từ cùng Criteria rồi thêm sort/limit/offset.
7. Viết test cho trường hợp có kết quả, không có kết quả và filter tùy chọn.
8. Nếu yêu cầu kết quả nhất quán qua nhiều câu SQL, xác định transaction và isolation level cần thiết.

## 14. Bài thực hành

**Bài 1.** `count(Query, Class<T>)` trả về kiểu gì?

*Đáp án:* `long`, biểu diễn số aggregate thỏa query.

**Bài 2.** `exists(Query, Class<T>)` trả về kiểu gì?

*Đáp án:* `boolean`, true khi có ít nhất một aggregate thỏa query và false nếu không có.

**Bài 3.** Hai phương thức count và exists có thể nhận cùng một đối tượng Query không?

*Đáp án:* Có. Đây là cách tái sử dụng cùng bộ điều kiện lọc để hai thao tác không phải tự xây dựng predicate riêng.

**Bài 4.** `Query` và `Criteria` có thay đổi tại chỗ khi gọi and, limit hoặc sort không?

*Đáp án:* Không. Đây là API fluent bất biến; các phương thức trả về đối tượng mới. Cần giữ giá trị trả về.

**Bài 5.** Nếu filter `customerId` là null vì người dùng không chọn khách hàng, có nên thêm `customer_id IS NULL` không?

*Đáp án:* Không, trừ khi người dùng thực sự yêu cầu tìm các hàng có customer ID NULL. Nếu filter vắng mặt, bỏ qua điều kiện đó.

**Bài 6.** Khi chỉ cần biết có đơn hàng nào không, nên gọi `count(...) > 0` hay `exists(...)`?

*Đáp án:* Dùng `exists(...)` vì kiểu trả về và mục đích API khớp trực tiếp với nhu cầu.

**Bài 7.** Có thể dùng Query có limit 20 để đếm tổng số kết quả tìm kiếm không?

*Đáp án:* Nên tạo filter Query không có phân trang để biểu diễn toàn bộ tập kết quả, rồi tạo page Query riêng cho danh sách.

**Bài 8.** Dùng cùng Query có bảo đảm count và exists nhìn thấy cùng một snapshot dữ liệu không?

*Đáp án:* Không. Cùng Query bảo đảm cùng định nghĩa điều kiện; snapshot nhất quán phụ thuộc transaction và isolation level của database.

**Bài 9.** Hai điều kiện status PAID hoặc SHIPPED cần kết hợp với customer ID bằng cách nào?

*Đáp án:* Tạo một Criteria group OR cho hai trạng thái, sau đó AND group đó với điều kiện customer ID.

**Bài 10.** `count(Query, Class<T>)` và `exists(Query, Class<T>)` có từ phiên bản nào?

*Đáp án:* Spring Data Relational 3.0.

## 15. Điều cần ghi nhớ

- `JdbcAggregateTemplate.count(Query, Class<T>)` trả về `long`; `exists(Query, Class<T>)` trả về `boolean`.
- Hai phương thức nhận cùng một `Query`, nhờ đó count và exists dùng chung điều kiện động.
- `Query.query(criteria)` tạo Query từ `Criteria`; cả hai API fluent đều bất biến.
- Chỉ thêm Criteria cho các filter được cung cấp; phân biệt filter vắng mặt với điều kiện tìm NULL.
- Dùng AND/OR group rõ ràng để tránh thay đổi ý nghĩa logic.
- Giữ Query lọc riêng; tạo Query mới có sort/limit/offset cho danh sách phân trang.
- Dùng `exists` khi chỉ cần câu trả lời có/không; dùng `count` khi cần số lượng.
- Query dùng với `domainType` đếm hoặc kiểm tra aggregate của kiểu đó.
- Tái sử dụng Query giữ cùng predicate nhưng không tự tạo snapshot database chung cho hai lần gọi.
- Nếu cần nhất quán khi có ghi đồng thời, xem xét transaction boundary và isolation level.
- Hai phương thức count/exists có Query được giới thiệu từ Spring Data Relational 3.0.

### Tài liệu tham khảo chính thức

- [Spring Data Relational — JdbcAggregateOperations API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): chữ ký, kiểu trả về và mốc Since 3.0 của count(Query, Class<T>) và exists(Query, Class<T>).
- [Spring Data Relational — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html): implementation của các aggregate operations.
- [Spring Data Relational — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html): Query, Criteria, sort, limit và offset; API fluent bất biến.
- [Spring Data Relational — Criteria API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Criteria.html): tạo và kết hợp các điều kiện AND/OR.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): các thao tác persistence và truy vấn bằng JdbcAggregateTemplate.

Khi cần đếm và kiểm tra tồn tại cho cùng một bộ lọc, hãy xây dựng Criteria một lần, tạo Query một lần và truyền cùng Query vào hai API. Cách này giữ cho định nghĩa điều kiện tập trung, dễ thay đổi và dễ kiểm thử.
