# CriteriaBuilder, CriteriaQuery, Root, Path và Predicate

## 1. Criteria API là gì?

Jakarta Persistence Criteria API cho phép xây dựng truy vấn bằng Java object thay vì ghép chuỗi JPQL. Đây là lựa chọn hữu ích khi điều kiện tìm kiếm thay đổi theo input: người dùng có thể chọn trạng thái, khoảng ngày, tên, số tiền, quan hệ liên quan hoặc nhiều tiêu chí tùy chọn.

Trong Spring Data JPA, Criteria API thường xuất hiện trực tiếp khi viết `Specification<T>`. Spring Data truyền vào callback ba đối tượng quan trọng:

- `Root<T>`: đại diện entity gốc trong mệnh đề FROM.
- `CriteriaQuery<T>`: mô tả cấu trúc truy vấn, kiểu kết quả, điều kiện, nhóm và thứ tự.
- `CriteriaBuilder`: cung cấp các phép toán để tạo biểu thức và điều kiện.
- `Path<X>`: đường dẫn tới thuộc tính của entity hoặc association.
- `Predicate`: một điều kiện logic dùng trong WHERE hoặc HAVING.

Các thành phần này phối hợp với nhau để tạo một truy vấn có kiểu dữ liệu rõ ràng. Có thể hiểu quy trình như sau:

1. Lấy CriteriaBuilder từ EntityManager.
2. Tạo CriteriaQuery với kiểu kết quả mong muốn.
3. Khai báo Root cho entity cần truy vấn.
4. Dùng Path để truy cập thuộc tính, Join để đi qua quan hệ.
5. Dùng CriteriaBuilder tạo Predicate và Expression.
6. Gắn selection, where, group by, having và order by vào CriteriaQuery.
7. Tạo TypedQuery rồi thực thi.

Criteria API là API chuẩn của Jakarta Persistence. Với Spring Boot 3 trở lên, import thường nằm trong package `jakarta.persistence.criteria`; các dự án Spring Boot 2/JPA cũ sử dụng package `javax.persistence.criteria`. Không trộn hai namespace trong cùng ứng dụng.

## 2. Mối quan hệ giữa các thành phần

Một truy vấn Criteria thường có hình dạng:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

Path<String> name = customer.get(Customer_.name);

Predicate condition =
    cb.like(cb.lower(name), "%an%");

query.select(customer)
     .where(condition)
     .orderBy(cb.asc(name));

List<Customer> result =
    entityManager.createQuery(query).getResultList();
```

Trong ví dụ:

- `CriteriaBuilder` tạo truy vấn và các biểu thức.
- `CriteriaQuery<Customer>` khai báo kiểu kết quả là Customer.
- `Root<Customer>` đại diện bảng/entity Customer trong FROM.
- `Path<String>` trỏ tới thuộc tính name có kiểu String.
- `Predicate` biểu diễn điều kiện LIKE.
- `select`, `where` và `orderBy` hoàn thiện cấu trúc truy vấn.

Các object Criteria mô tả query; chúng chưa thực thi SQL. SQL chỉ được tạo và thực thi khi tạo TypedQuery rồi gọi `getResultList()`, `getSingleResult()` hoặc các API tương ứng.

## 3. CriteriaBuilder: tạo truy vấn và biểu thức

### 3.1. Lấy CriteriaBuilder và tạo CriteriaQuery

CriteriaBuilder được lấy từ EntityManager:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
```

Tạo query trả về entity:

```java
CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);
```

Tạo query trả về kiểu khác:

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

CriteriaQuery<Tuple> tupleQuery =
    cb.createTupleQuery();
```

Kiểu generic của CriteriaQuery mô tả kiểu kết quả mà query sẽ trả về. Điều này giúp compiler kiểm tra kiểu ở nhiều thao tác, giảm lỗi ép kiểu khi so với việc ghép chuỗi JPQL.

### 3.2. Các phép so sánh cơ bản

CriteriaBuilder có các phương thức như:

| Phương thức | Ý nghĩa |
|---|---|
| `equal(x, y)` | Bằng |
| `notEqual(x, y)` | Khác |
| `gt(x, y)` | Lớn hơn |
| `ge(x, y)` | Lớn hơn hoặc bằng |
| `lt(x, y)` | Nhỏ hơn |
| `le(x, y)` | Nhỏ hơn hoặc bằng |
| `between(x, a, b)` | Nằm trong khoảng |
| `like(x, pattern)` | Khớp pattern LIKE |
| `isNull(x)` | Giá trị null |
| `isNotNull(x)` | Giá trị khác null |
| `in(x)` | Thuộc tập giá trị |

Ví dụ:

```java
Predicate active =
    cb.equal(root.get(Customer_.status), CustomerStatus.ACTIVE);

Predicate minAge =
    cb.ge(root.get(Customer_.age), 18);

Predicate createdBetween =
    cb.between(
        root.get(Customer_.createdAt),
        from,
        to
    );
```

Các phương thức so sánh số dùng kiểu `Number`; các phép so sánh khoảng ngày/giờ dùng kiểu Comparable tương ứng. Cần truyền kiểu Java tương thích với kiểu thuộc tính entity.

### 3.3. Kết hợp AND, OR và NOT

CriteriaBuilder hỗ trợ kết hợp điều kiện:

```java
Predicate active = cb.equal(
    root.get(Customer_.status),
    CustomerStatus.ACTIVE
);

Predicate adult = cb.ge(root.get(Customer_.age), 18);

Predicate activeAdult = cb.and(active, adult);

Predicate namedAn = cb.like(
    cb.lower(root.get(Customer_.name)),
    "%an%"
);

Predicate result = cb.or(activeAdult, namedAn);
```

Các phép toán tương ứng:

- `cb.and(p1, p2)`: cả hai điều kiện đúng.
- `cb.or(p1, p2)`: ít nhất một điều kiện đúng.
- `cb.not(p)`: phủ định điều kiện.
- `cb.conjunction()`: điều kiện luôn đúng, hữu ích khi danh sách filter rỗng.
- `cb.disjunction()`: điều kiện luôn sai.

Có thể tạo Predicate từ một danh sách:

```java
List<Predicate> predicates = new ArrayList<>();

predicates.add(cb.equal(
    root.get(Customer_.status),
    CustomerStatus.ACTIVE
));

predicates.add(cb.ge(root.get(Customer_.age), 18));

query.where(cb.and(predicates.toArray(Predicate[]::new)));
```

Cách này phù hợp với filter động. Chỉ thêm predicate khi input tương ứng thực sự được cung cấp.

### 3.4. Expression và hàm tính toán

CriteriaBuilder còn tạo Expression để biểu diễn giá trị được tính trong query:

```java
Expression<String> normalizedName =
    cb.lower(root.get(Customer_.name));

Expression<Integer> nameLength =
    cb.length(root.get(Customer_.name));

Expression<BigDecimal> discountedPrice =
    cb.prod(
        root.get(Product_.price),
        new BigDecimal("0.9")
    );
```

Expression có thể được dùng trong select, where, order by, group by hoặc phép tính khác tùy kiểu và ngữ cảnh. Không phải mọi database function đều portable; nếu cần hàm riêng của database, có thể dùng `cb.function(...)` nhưng phải kiểm thử trên dialect thực tế.

## 4. CriteriaQuery: mô tả cấu trúc truy vấn

### 4.1. Khai báo kiểu kết quả và selection

`CriteriaQuery<T>` đại diện một truy vấn có kiểu kết quả T. Với entity:

```java
CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

query.select(customer);
```

Với một scalar:

```java
CriteriaQuery<Long> query =
    cb.createQuery(Long.class);

Root<Customer> customer = query.from(Customer.class);

query.select(cb.count(customer));
```

Với nhiều giá trị, có thể dùng Tuple:

```java
CriteriaQuery<Tuple> query = cb.createTupleQuery();

Root<Customer> customer = query.from(Customer.class);

query.multiselect(
    customer.get(Customer_.id).alias("id"),
    customer.get(Customer_.name).alias("name")
);
```

Sau khi chạy Tuple query, lấy giá trị theo alias:

```java
Tuple row = entityManager.createQuery(query)
    .getSingleResult();

Long id = row.get("id", Long.class);
String name = row.get("name", String.class);
```

Alias phải nhất quán và không trùng nhau trong cùng selection.

### 4.2. WHERE và lưu ý khi gọi nhiều lần

Có thể đặt điều kiện:

```java
query.where(
    cb.equal(customer.get(Customer_.status), CustomerStatus.ACTIVE)
);
```

Một lỗi phổ biến là gọi `where()` nhiều lần với suy nghĩ các điều kiện sẽ tự cộng dồn:

```java
query.where(activePredicate);
query.where(agePredicate);
```

Lời gọi sau thay thế restriction trước đó. Nếu muốn kết hợp, hãy tạo một Predicate tổng:

```java
query.where(cb.and(activePredicate, agePredicate));
```

Hoặc thu thập điều kiện vào List rồi gọi `where()` một lần. Nguyên tắc tương tự áp dụng cho các phương thức thiết lập selection và order: khi cần nhiều thành phần, hãy xây dựng tập hợp hoàn chỉnh trước khi gắn vào query.

### 4.3. DISTINCT

JOIN collection có thể tạo nhiều hàng SQL cho cùng một entity gốc. Nếu mục tiêu là lấy mỗi Customer một lần, có thể dùng:

```java
query.select(customer).distinct(true);
```

DISTINCT loại kết quả trùng theo semantics của query. Khi phân trang hoặc đếm tổng, count query cũng phải đếm đúng số entity duy nhất, thường cần `countDistinct(root)` hoặc một cách viết tránh nhân bản dòng.

### 4.4. ORDER BY

CriteriaQuery nhận danh sách Order:

```java
query.orderBy(
    cb.asc(customer.get(Customer_.name)),
    cb.desc(customer.get(Customer_.createdAt)),
    cb.asc(customer.get(Customer_.id))
);
```

Các order được áp dụng theo thứ tự ưu tiên. Khi phân trang, nên thêm một thuộc tính duy nhất như ID làm tie-breaker. Nếu chỉ sắp xếp theo tên và nhiều hàng có cùng tên, thứ tự giữa các hàng đó không được bảo đảm.

## 5. Root: entity gốc trong FROM

### 5.1. Root đại diện entity nào?

Root được tạo bằng `from()`:

```java
Root<Customer> customer = query.from(Customer.class);
```

Nó đại diện Customer trong mệnh đề FROM và là điểm bắt đầu để truy cập thuộc tính, join quan hệ hoặc tạo biểu thức.

Một query có thể có nhiều Root:

```java
Root<Customer> customer = query.from(Customer.class);
Root<Order> order = query.from(Order.class);
```

Hai Root độc lập có thể tạo tích Descartes nếu không có điều kiện liên kết phù hợp. Khi entity có association mapping, thường dùng join qua quan hệ thay vì khai báo thêm Root không cần thiết.

### 5.2. Truy cập thuộc tính từ Root

Root kế thừa khả năng truy cập Path:

```java
Path<Long> id = customer.get(Customer_.id);
Path<String> name = customer.get(Customer_.name);
Path<CustomerStatus> status = customer.get(Customer_.status);
```

Có thể dùng tên chuỗi:

```java
Path<String> name = customer.get("name");
```

Cách dùng string ngắn gọn nhưng lỗi tên property chỉ xuất hiện lúc chạy. Static metamodel giúp compiler phát hiện nhiều lỗi tên/kiểu ngay khi biên dịch.

## 6. Path: đường dẫn tới thuộc tính

### 6.1. Path là gì?

`Path<X>` biểu diễn đường dẫn có kiểu tới một thuộc tính hoặc thành phần của entity. Root cũng là một Path, nhưng Root có thêm vai trò entity gốc và khả năng tạo join.

Ví dụ:

```java
Path<String> name = customer.get(Customer_.name);
Path<Integer> age = customer.get(Customer_.age);
Path<LocalDate> birthDate = customer.get(Customer_.birthDate);
```

Kiểu generic giúp CriteriaBuilder biết biểu thức là String, Integer hay LocalDate và chọn phép so sánh tương ứng.

### 6.2. Đi qua thuộc tính nhúng hoặc thuộc tính đơn

Nếu Customer có Address là `@Embedded`, có thể truy cập thuộc tính con:

```java
Path<String> city =
    customer.get(Customer_.address).get(Address_.city);
```

Đường dẫn này đi qua thuộc tính embedded. Với quan hệ entity như Customer có nhiều Order, nên dùng Join để biểu đạt association và điều khiển loại join.

### 6.3. Path và Join khác nhau

Path dùng để đi tới thuộc tính. Join dùng để kết nối entity qua association trong query.

Ví dụ:

```java
Path<String> customerName =
    customer.get(Customer_.name);

Join<Customer, Order> orders =
    customer.join(Customer_.orders);
```

Không thể coi collection association như một scalar Path để truy cập thuộc tính của phần tử. Cần join collection rồi mới lấy thuộc tính của entity liên quan.

## 7. Static Metamodel và type-safe query

### 7.1. Vì sao nên dùng metamodel?

Static metamodel là các class được sinh từ entity, thường có hậu tố gạch dưới, ví dụ `Customer_`. Chúng cung cấp thuộc tính có kiểu để dùng trong Criteria API.

Ví dụ entity:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    private String name;

    private Integer age;
}
```

Metamodel được sinh có dạng khái quát:

```java
@StaticMetamodel(Customer.class)
public class Customer_ {
    public static volatile SingularAttribute<Customer, Long> id;
    public static volatile SingularAttribute<Customer, String> name;
    public static volatile SingularAttribute<Customer, Integer> age;
}
```

Đây là dạng minh họa của mã do annotation processor sinh; thông thường không tự viết class metamodel bằng tay.

Dùng metamodel:

```java
Path<String> name = customer.get(Customer_.name);
Predicate condition = cb.equal(name, "An");
```

Nếu đổi tên property và metamodel được sinh lại, compiler có thể phát hiện nơi dùng thuộc tính cũ. Với string path `get("nam")`, lỗi chỉ xuất hiện lúc chạy.

### 7.2. Cấu hình annotation processor

Dự án cần annotation processor tương ứng với phiên bản Jakarta Persistence và build tool. Tên artifact/phương thức cấu hình phụ thuộc phiên bản Hibernate/JPA metamodel generator. Hãy dùng phiên bản tương thích với Spring Boot/Jakarta Persistence đang chạy và cấu hình nó ở annotation processor path, không thêm như dependency runtime một cách tùy tiện.

Sau khi build, kiểm tra class metamodel được sinh trong thư mục generated sources và IDE đã nhận thư mục đó như source root. Nếu metamodel không được sinh, query dùng `Customer_.name` sẽ không biên dịch.

Với dự án nhỏ, string path có thể đủ; với codebase lớn hoặc nhiều refactor entity, static metamodel giúp an toàn kiểu tốt hơn.

## 8. Predicate: điều kiện logic của query

### 8.1. Predicate là gì?

Predicate là một biểu thức Boolean. Nó thường được đặt trong WHERE hoặc HAVING:

```java
Predicate active = cb.equal(
    customer.get(Customer_.status),
    CustomerStatus.ACTIVE
);

Predicate nameContains = cb.like(
    cb.lower(customer.get(Customer_.name)),
    "%an%"
);

query.where(cb.and(active, nameContains));
```

Predicate không thực thi ngay khi được tạo. Nó là một phần của cấu trúc query mà provider sẽ chuyển thành SQL.

### 8.2. Filter động

Một use case tìm kiếm thường có nhiều input tùy chọn. Không nên tạo query khác nhau bằng cách nối chuỗi SQL. Hãy thêm Predicate khi có giá trị:

```java
List<Predicate> predicates = new ArrayList<>();

if (status != null) {
    predicates.add(cb.equal(
        customer.get(Customer_.status),
        status
    ));
}

if (minAge != null) {
    predicates.add(cb.ge(
        customer.get(Customer_.age),
        minAge
    ));
}

if (keyword != null && !keyword.isBlank()) {
    String pattern = "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

    predicates.add(cb.like(
        cb.lower(customer.get(Customer_.name)),
        pattern
    ));
}

query.where(cb.and(predicates.toArray(Predicate[]::new)));
```

Nếu danh sách rỗng, `cb.and()` với zero predicate có semantics true theo Criteria API. Có thể dùng `cb.conjunction()` để biểu đạt điều kiện luôn đúng một cách rõ ràng.

Đoạn LIKE trên minh họa tìm chuỗi con; nếu người dùng nhập `%` hoặc `_`, chúng vẫn có ý nghĩa wildcard. Nếu cần tìm literal text, phải escape hai ký tự này và truyền escape character vào overload phù hợp của `cb.like()`.

### 8.3. Xử lý null

Không nên dùng `cb.equal(path, null)` như cách biểu đạt điều kiện SQL IS NULL. Hãy dùng:

```java
Predicate noEmail =
    cb.isNull(customer.get(Customer_.email));

Predicate hasEmail =
    cb.isNotNull(customer.get(Customer_.email));
```

Nếu filter null nghĩa là “không áp dụng điều kiện”, bỏ qua Predicate. Nếu null nghĩa là “tìm những hàng có giá trị null”, dùng `isNull()`. Hai ý nghĩa này cần được phân biệt ở API/service.

### 8.4. IN và NOT IN

Tìm entity thuộc một tập giá trị:

```java
Predicate selectedStatuses =
    customer.get(Customer_.status)
        .in(CustomerStatus.ACTIVE, CustomerStatus.PENDING);
```

Có thể dùng CriteriaBuilder:

```java
Predicate selectedIds =
    cb.in(customer.get(Customer_.id))
      .value(10L)
      .value(20L)
      .value(30L);
```

Nếu danh sách đầu vào rỗng, hãy xác định rõ nghiệp vụ: không lọc, trả về rỗng hay từ chối request. Không nên để semantics của danh sách rỗng quyết định ngầm kết quả API.

## 9. JOIN và JoinType

### 9.1. Join qua association

Giả sử Customer có quan hệ `@OneToMany` tới Order:

```java
@OneToMany(mappedBy = "customer")
private List<Order> orders = new ArrayList<>();
```

Có thể join:

```java
Join<Customer, Order> order =
    customer.join(Customer_.orders, JoinType.INNER);

Predicate paid = cb.equal(
    order.get(Order_.status),
    OrderStatus.PAID
);

query.select(customer)
     .where(paid)
     .distinct(true);
```

Các loại join thường dùng:

- `JoinType.INNER`: chỉ lấy root có phần tử liên quan phù hợp.
- `JoinType.LEFT`: giữ root ngay cả khi không có phần tử liên quan.
- `JoinType.RIGHT`: ít dùng hơn và mức hỗ trợ phụ thuộc provider/database.

JOIN collection có thể nhân số dòng root. Nếu một Customer có ba Order phù hợp, SQL join có thể tạo ba hàng cho Customer đó. Dùng `distinct(true)` khi kết quả cần mỗi Customer một lần; đồng thời xem lại count query nếu phân trang.

### 9.2. Điều kiện ở ON và WHERE khác nhau

Với LEFT JOIN, đặt điều kiện của bảng bên phải trong WHERE có thể loại các hàng không có phần tử liên quan, khiến kết quả thực tế giống INNER JOIN.

Ví dụ:

```java
Join<Customer, Order> orders =
    customer.join(Customer_.orders, JoinType.LEFT);

orders.on(
    cb.equal(orders.get(Order_.status), OrderStatus.PAID)
);
```

Điều kiện `on()` giới hạn những hàng Order được nối mà vẫn giữ Customer không có Order PAID. Nếu thay bằng `query.where(cb.equal(orders.get(...), PAID))`, các hàng mà Order null sẽ không thỏa điều kiện.

Chọn ON hay WHERE theo ý nghĩa nghiệp vụ, không chỉ theo cú pháp.

### 9.3. Fetch khác Join

`join()` tham gia điều kiện và cấu trúc query. `fetch()` yêu cầu provider tải association cùng entity gốc để giảm lazy loading/N+1. Fetch trả về `Fetch`, không phải `Join`, nên không dùng trực tiếp như Path để tạo predicate trong mọi trường hợp.

Đặc biệt, collection fetch join kết hợp phân trang có thể làm nhân dòng và khiến pagination khó dự đoán. Không thêm fetch join vào mọi Specification; hãy chọn fetch plan theo use case và kiểm tra count query.

## 10. Subquery và EXISTS

Criteria API hỗ trợ subquery bên trong CriteriaQuery:

```java
CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

Subquery<Integer> paidOrderExists =
    query.subquery(Integer.class);

Root<Order> order = paidOrderExists.from(Order.class);

paidOrderExists.select(cb.literal(1));
paidOrderExists.where(
    cb.equal(order.get(Order_.customer), customer),
    cb.equal(order.get(Order_.status), OrderStatus.PAID)
);

query.select(customer)
     .where(cb.exists(paidOrderExists));
```

Ý nghĩa: tìm Customer có ít nhất một Order ở trạng thái PAID.

EXISTS thường hữu ích khi chỉ cần kiểm tra sự tồn tại của bản ghi liên quan. Nó tránh nhân bản root rows như một số kiểu join collection. Optimizer có thể chuyển đổi cách thực thi; hiệu năng cuối cùng phụ thuộc index và database.

Có thể dùng `cb.not(cb.exists(subquery))` để tìm Customer không có Order phù hợp. Cần kiểm tra điều kiện tương quan giữa subquery và root ngoài để tránh tạo subquery không liên quan ngoài ý muốn.

## 11. GROUP BY, HAVING và hàm tổng hợp

Criteria API hỗ trợ các hàm như `count`, `countDistinct`, `sum`, `avg`, `min` và `max`.

Ví dụ đếm số đơn hàng theo khách hàng:

```java
CriteriaQuery<Tuple> query = cb.createTupleQuery();

Root<Customer> customer = query.from(Customer.class);

Join<Customer, Order> order =
    customer.join(Customer_.orders, JoinType.LEFT);

Expression<Long> orderCount = cb.count(order);

query.multiselect(
    customer.get(Customer_.id).alias("customerId"),
    customer.get(Customer_.name).alias("customerName"),
    orderCount.alias("orderCount")
);

query.groupBy(
    customer.get(Customer_.id),
    customer.get(Customer_.name)
);

query.having(cb.ge(orderCount, 3L));
```

Query trả các Customer có ít nhất ba Order. Với LEFT JOIN, `count(order)` đếm phần tử Order khác null; `count(customer)` sẽ đếm hàng Customer được join và không biểu đạt cùng ý nghĩa.

Phân biệt:

- WHERE lọc hàng trước khi nhóm.
- GROUP BY xác định nhóm.
- HAVING lọc kết quả sau khi nhóm.
- COUNT/DISTINCT/SUM là các biểu thức tổng hợp.

Khi query có GROUP BY, count query cho Page phải đếm số nhóm kết quả, không phải tổng số hàng nguồn. Có thể cần một truy vấn count riêng hoặc subquery phù hợp.

## 12. DTO projection với CriteriaBuilder.construct

Criteria API có thể tạo DTO trực tiếp bằng constructor:

```java
public record CustomerSummary(Long id, String name) {
}
```

Tạo query:

```java
CriteriaQuery<CustomerSummary> query =
    cb.createQuery(CustomerSummary.class);

Root<Customer> customer = query.from(Customer.class);

query.select(
    cb.construct(
        CustomerSummary.class,
        customer.get(Customer_.id),
        customer.get(Customer_.name)
    )
);
```

Constructor DTO phải khớp số lượng, thứ tự và kiểu của các Expression được truyền vào. Khác với interface projection, class-based projection dựa trên constructor. DTO không phải entity managed; thay đổi object kết quả không tự persist xuống database.

Với DTO constructor nhiều tham số, hãy giữ thứ tự rõ ràng và test mapping. Nếu constructor không tương thích, lỗi thường xuất hiện khi provider tạo hoặc phân tích query.

## 13. Phân trang và đếm kết quả bằng Criteria API

Criteria API tự nó không nhận Pageable như repository method. Khi tự xây query bằng EntityManager, cần áp dụng offset và limit thủ công:

```java
TypedQuery<Customer> typedQuery =
    entityManager.createQuery(query);

typedQuery.setFirstResult(
    Math.toIntExact(pageable.getOffset())
);
typedQuery.setMaxResults(pageable.getPageSize());

List<Customer> content = typedQuery.getResultList();
```

`setFirstResult()` nhận int. Offset của Pageable là long; `Math.toIntExact` giúp phát hiện overflow thay vì âm thầm cắt giá trị. API nên giới hạn page size và page index hợp lý.

Để tạo Page, cần count query riêng:

```java
CriteriaQuery<Long> countCriteria =
    cb.createQuery(Long.class);

Root<Customer> countRoot =
    countCriteria.from(Customer.class);

List<Predicate> countPredicates =
    buildPredicates(cb, countRoot, filter);

countCriteria.select(cb.count(countRoot))
             .where(cb.and(
                 countPredicates.toArray(Predicate[]::new)
             ));

long total = entityManager.createQuery(countCriteria)
    .getSingleResult();

return new PageImpl<>(content, pageable, total);
```

Hàm `buildPredicates` phải xây predicate mới từ `countRoot`. Không tái sử dụng Predicate tạo từ Root của content query vì Path/Root gắn với query đã tạo chúng.

Nếu content query join collection và có thể tạo duplicate Customer, count query cần `cb.countDistinct(countRoot)` hoặc dùng EXISTS để đếm đúng số Customer. Content và count phải áp dụng cùng điều kiện lọc, cùng phạm vi tenant/quyền truy cập và cùng ý nghĩa nghiệp vụ.

Với Specification và repository hỗ trợ paging, Spring Data có thể tự tạo count query. Tuy vậy, nếu Specification thêm fetch join hoặc distinct phức tạp, cần kiểm tra SQL count thực tế.

## 14. CriteriaUpdate và CriteriaDelete

Criteria API không chỉ dùng để SELECT. Jakarta Persistence còn có bulk update và delete.

### 14.1. CriteriaUpdate

Ví dụ cập nhật trạng thái Customer không hoạt động:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaUpdate<Customer> update =
    cb.createCriteriaUpdate(Customer.class);

Root<Customer> customer = update.from(Customer.class);

update.set(
    Customer_.status,
    CustomerStatus.INACTIVE
);

update.where(
    cb.lessThan(
        customer.get(Customer_.lastLoginAt),
        cutoff
    )
);

int affected = entityManager.createQuery(update)
    .executeUpdate();
```

Giá trị trả về là số hàng bị ảnh hưởng theo báo cáo của database/provider. Bulk update thực thi trực tiếp theo tập hợp, không tải từng Customer thành entity rồi dirty-check từng object.

### 14.2. CriteriaDelete

```java
CriteriaDelete<Customer> delete =
    cb.createCriteriaDelete(Customer.class);

Root<Customer> customer = delete.from(Customer.class);

delete.where(
    cb.equal(
        customer.get(Customer_.status),
        CustomerStatus.DELETED
    )
);

int affected = entityManager.createQuery(delete)
    .executeUpdate();
```

Bulk update/delete có các giới hạn quan trọng:

- Không thực hiện cascade remove như thao tác remove từng entity.
- Không gọi lifecycle callback như `@PreUpdate` hoặc `@PreRemove` cho từng entity.
- Không đồng bộ trạng thái các entity đang managed trong persistence context.
- Có thể khiến first-level/second-level cache chứa dữ liệu cũ.
- Ràng buộc foreign key của database vẫn được áp dụng.

Trước bulk operation, thường cần flush thay đổi đang chờ. Sau đó, cân nhắc clear persistence context hoặc refresh entity liên quan để tránh đọc trạng thái cũ. Thực hiện trong transaction và xác định rõ các quan hệ phụ thuộc cần xử lý.

## 15. Dùng Criteria API bên trong Spring Data Specification

### 15.1. Specification chính là cầu nối

Spring Data JPA định nghĩa Specification với callback:

```java
public interface Specification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder
    );
}
```

Đây là chữ ký khái quát; interface thực tế có thêm default method để kết hợp Specification. Ba đối tượng được truyền vào chính là các thành phần Criteria API đã trình bày.

Repository cần mở rộng `JpaSpecificationExecutor`:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

### 15.2. Tạo Specification đơn giản

```java
public static Specification<Customer> hasStatus(
        CustomerStatus status) {

    return (root, query, cb) -> {
        if (status == null) {
            return cb.conjunction();
        }

        return cb.equal(
            root.get(Customer_.status),
            status
        );
    };
}
```

Specification trả về Predicate; nó không thực thi query. Spring Data kết hợp Predicate vào query mà repository tạo.

### 15.3. Kết hợp các điều kiện

```java
public static Specification<Customer> nameContains(String keyword) {
    return (root, query, cb) -> {
        if (keyword == null || keyword.isBlank()) {
            return cb.conjunction();
        }

        String pattern =
            "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

        return cb.like(
            cb.lower(root.get(Customer_.name)),
            pattern
        );
    };
}

public static Specification<Customer> ageAtLeast(Integer age) {
    return (root, query, cb) -> age == null
        ? cb.conjunction()
        : cb.ge(root.get(Customer_.age), age);
}
```

Service kết hợp:

```java
Specification<Customer> specification =
    hasStatus(CustomerStatus.ACTIVE)
        .and(nameContains("an"))
        .and(ageAtLeast(18));

Page<Customer> page =
    customerRepository.findAll(
        specification,
        PageRequest.of(0, 20, Sort.by("name").ascending())
    );
```

Các Specification có thể được tái sử dụng và kết hợp theo nhu cầu. Nếu cần OR, dùng `.or(...)`; nếu cần phủ định, có thể dùng `.not(...)` theo API của phiên bản Spring Data đang dùng.

### 15.4. Tránh side effect nguy hiểm trong Specification

Specification thường được dùng cho cả content query và count query khi phân trang. Vì vậy, không nên tùy tiện thêm fetch join, selection, order hoặc group vào mọi Specification mà không xét loại query đang được tạo.

Ví dụ fetch collection có thể gây lỗi hoặc kết quả sai khi Spring Data tạo count query. Nếu cần fetch plan riêng, hãy tách query hoặc dùng EntityGraph/custom repository. Predicate nên tập trung mô tả điều kiện lọc; những thay đổi cấu trúc query đặc biệt cần được kiểm soát rõ.

## 16. Một ví dụ Criteria API hoàn chỉnh ở tầng repository tùy chỉnh

Ví dụ sau minh họa cách gom filter, sort và phân trang trong custom repository. Các class Customer, CustomerFilter và Customer_ cần được khai báo/sinh trong dự án.

```java
@Repository
public class CustomerSearchRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public Page<Customer> search(
            CustomerFilter filter,
            Pageable pageable) {

        CriteriaBuilder cb =
            entityManager.getCriteriaBuilder();

        CriteriaQuery<Customer> criteria =
            cb.createQuery(Customer.class);

        Root<Customer> root =
            criteria.from(Customer.class);

        List<Predicate> predicates =
            buildPredicates(cb, root, filter);

        criteria.select(root)
                .where(cb.and(
                    predicates.toArray(Predicate[]::new)
                ));

        List<jakarta.persistence.criteria.Order> orders =
            new ArrayList<>();

        orders.add(cb.asc(root.get(Customer_.name)));
        orders.add(cb.asc(root.get(Customer_.id)));

        criteria.orderBy(orders);

        TypedQuery<Customer> typedQuery =
            entityManager.createQuery(criteria);

        typedQuery.setFirstResult(
            Math.toIntExact(pageable.getOffset())
        );
        typedQuery.setMaxResults(pageable.getPageSize());

        List<Customer> content = typedQuery.getResultList();

        CriteriaQuery<Long> countCriteria =
            cb.createQuery(Long.class);

        Root<Customer> countRoot =
            countCriteria.from(Customer.class);

        List<Predicate> countPredicates =
            buildPredicates(cb, countRoot, filter);

        countCriteria.select(cb.count(countRoot))
                     .where(cb.and(
                         countPredicates.toArray(Predicate[]::new)
                     ));

        long total = entityManager.createQuery(countCriteria)
            .getSingleResult();

        return new PageImpl<>(content, pageable, total);
    }

    private List<Predicate> buildPredicates(
            CriteriaBuilder cb,
            Root<Customer> root,
            CustomerFilter filter) {

        List<Predicate> predicates = new ArrayList<>();

        if (filter.status() != null) {
            predicates.add(cb.equal(
                root.get(Customer_.status),
                filter.status()
            ));
        }

        if (filter.keyword() != null
                && !filter.keyword().isBlank()) {
            String pattern = "%"
                + filter.keyword().trim().toLowerCase(Locale.ROOT)
                + "%";

            predicates.add(cb.like(
                cb.lower(root.get(Customer_.name)),
                pattern
            ));
        }

        if (filter.minAge() != null) {
            predicates.add(cb.ge(
                root.get(Customer_.age),
                filter.minAge()
            ));
        }

        return predicates;
    }
}
```

Đây là ví dụ khung cho custom repository, không phải chương trình độc lập. Cần có các import Jakarta Persistence, Spring Data, collection, DTO/filter và entity tương ứng.

Ví dụ dùng sort cố định theo name rồi id để bảo đảm thứ tự ổn định. Nếu cho client chọn sort, phải map property qua allowlist; không dùng trực tiếp tên property tùy ý từ request. Nếu filter có JOIN collection, hãy điều chỉnh count query để tránh đếm trùng root.

## 17. Lỗi thường gặp khi dùng Criteria API

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Điều kiện trước biến mất | Gọi `where()` nhiều lần | Gom Predicate rồi gọi where một lần |
| Không tìm thấy property | Sai tên trong `get("...")` | Dùng static metamodel |
| Query trả entity trùng | JOIN collection tạo nhiều hàng root | Dùng distinct hoặc EXISTS |
| Count lớn hơn content logic | Count(*) sau JOIN một-nhiều | Count distinct root hoặc viết count bằng EXISTS |
| LEFT JOIN biến thành INNER JOIN | Đặt điều kiện phía phải trong WHERE | Đưa điều kiện phù hợp vào Join.on() |
| Predicate dùng sai Root | Tái sử dụng Predicate từ query khác | Tạo Path/Predicate mới cho từng Root |
| Null filter không đúng | Nhầm null là bỏ lọc hoặc IS NULL | Bỏ predicate hoặc dùng isNull rõ ràng |
| LIKE tìm quá rộng | Không escape % và _ từ input | Escape wildcard khi cần literal search |
| Phân trang không ổn định | ORDER BY thiếu tie-breaker | Thêm thuộc tính duy nhất như ID |
| Count query lỗi với fetch join | Specification áp dụng fetch cả ở count | Tách fetch plan khỏi predicate dùng chung |
| Bulk update đọc dữ liệu cũ | Persistence context không tự đồng bộ | Flush và clear/refresh phù hợp |
| Query phụ thuộc database | Dùng function riêng hoặc kiểu dữ liệu khác nhau | Integration test trên database mục tiêu |

## 18. Kiểm thử và tối ưu

Criteria API tạo query động nên test cần bao phủ các tổ hợp filter, không chỉ trường hợp mặc định.

Nên kiểm thử:

- Không có filter nào.
- Mỗi filter riêng lẻ.
- Nhiều filter kết hợp AND và OR.
- Giá trị null, chuỗi rỗng và danh sách rỗng.
- Join không có dữ liệu liên quan.
- Một root có nhiều child phù hợp.
- EXISTS và NOT EXISTS.
- DISTINCT, GROUP BY và HAVING.
- Count query và page content có cùng điều kiện.
- Sort nhiều trường và tie-breaker.
- Bulk update/delete với entity đang managed.

Dùng `@DataJpaTest` cho kiểm thử repository và persistence layer. Nếu query dùng function, collation, kiểu dữ liệu hoặc execution plan riêng database, hãy chạy integration test trên cùng loại database với production.

Để tối ưu, kiểm tra SQL thực tế và execution plan. Criteria API không tự làm truy vấn nhanh hơn JPQL; cả hai thường được provider chuyển thành SQL. Hiệu năng phụ thuộc cấu trúc query, index, số hàng, join, selectivity và cách database tối ưu.

Không xây một query quá tổng quát với hàng chục predicate tùy chọn nếu nhiều nhánh làm SQL khó tối ưu. Có thể chia use case thành các query rõ ràng khi điều kiện và access pattern khác nhau đáng kể.

## 19. Khi nào nên dùng Criteria API?

Criteria API phù hợp khi:

- Bộ lọc thay đổi theo nhiều input tùy chọn.
- Cần kết hợp AND/OR lồng nhau.
- Có join/subquery động.
- Muốn tái sử dụng predicate trong nhiều truy vấn.
- Cần xây projection, aggregate hoặc query có kiểu trả về khác nhau.
- Muốn dùng Spring Data Specification cho search API.

JPQL hoặc derived query thường dễ đọc hơn khi query cố định và đơn giản. Native SQL phù hợp khi cần tính năng đặc thù database hoặc kiểm soát SQL chi tiết. Không cần dùng Criteria API cho mọi truy vấn chỉ vì nó có nhiều khả năng.

## 20. Checklist trước khi đưa query Criteria vào ứng dụng

- [ ] Kiểu kết quả của CriteriaQuery đúng với entity/DTO/scalar cần trả về.
- [ ] Root đại diện đúng entity nguồn.
- [ ] Path trỏ đúng property và đúng kiểu.
- [ ] Static metamodel được sinh từ entity đúng phiên bản.
- [ ] Predicate được kết hợp đầy đủ, không bị where() ghi đè.
- [ ] Null và chuỗi rỗng có semantics rõ ràng.
- [ ] Wildcard LIKE được escape nếu cần tìm literal.
- [ ] JOIN collection không làm trùng root ngoài ý muốn.
- [ ] LEFT JOIN dùng ON/WHERE theo đúng semantics.
- [ ] Count query đếm đúng đơn vị kết quả.
- [ ] Pageable có page size/offset hợp lệ và sort ổn định.
- [ ] Specification không tạo fetch/count query xung đột.
- [ ] Bulk operation đã xử lý cascade, callback và persistence context.
- [ ] SQL và execution plan đã được kiểm tra trên database mục tiêu.

## 21. Kết luận

Criteria API là cách xây dựng truy vấn JPA bằng object có kiểu. `CriteriaBuilder` tạo biểu thức và phép toán; `CriteriaQuery` mô tả SELECT, WHERE, GROUP BY, HAVING và ORDER BY; `Root` đại diện entity trong FROM; `Path` truy cập thuộc tính; `Predicate` biểu diễn điều kiện logic. Join và Subquery mở rộng khả năng truy vấn quan hệ và điều kiện phức tạp.

Trong Spring Data JPA, Specification dùng chính Root, CriteriaQuery và CriteriaBuilder để tạo Predicate có thể kết hợp và tái sử dụng. Với query động, hãy gom điều kiện rồi áp dụng một lần, dùng static metamodel khi có thể, kiểm soát duplicate do JOIN và tạo count query đúng khi phân trang. Bulk update/delete có semantics khác thao tác entity thông thường nên cần quản lý transaction và persistence context cẩn thận.

Chọn Criteria API khi query thực sự cần tính động và khả năng tổ hợp. Với truy vấn cố định, JPQL hoặc derived query thường dễ đọc hơn. Dù chọn cách nào, hãy kiểm thử kết quả, kiểm tra SQL và execution plan trên database mà ứng dụng triển khai.