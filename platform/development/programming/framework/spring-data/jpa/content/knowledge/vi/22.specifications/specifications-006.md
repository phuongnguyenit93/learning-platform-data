# Join quan hệ, truy vấn con và xử lý kết quả trùng

## 1. Vì sao Specification cần JOIN và subquery?

Spring Data JPA `Specification<T>` dựa trên JPA Criteria API để xây dựng điều kiện truy vấn theo kiểu động. Khi filter chỉ dùng thuộc tính của Entity gốc, có thể tạo predicate trực tiếp từ `Root<T>`. Khi điều kiện phụ thuộc Entity liên quan, cần đi theo association bằng JOIN hoặc kiểm tra sự tồn tại bằng subquery.

Hai kỹ thuật giải quyết hai nhu cầu khác nhau:

- **JOIN:** kết hợp Entity gốc với Entity liên quan để lọc, sắp xếp, group hoặc lấy dữ liệu liên quan.
- **Subquery:** tạo truy vấn lồng bên trong để kiểm tra sự tồn tại, không tồn tại, membership hoặc so sánh với một giá trị tổng hợp.

Join tới quan hệ to-many có thể tạo nhiều hàng SQL cho cùng một Entity gốc. Vì vậy, khi dùng Specification với `Page<T>` hoặc trả về danh sách root Entity, phải xử lý kết quả trùng và count đúng theo số root mà nghiệp vụ yêu cầu.

## 2. Mô hình ví dụ

Giả sử một khách hàng có nhiều đơn hàng:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String name;
    private CustomerStatus status;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}
```

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    private OrderStatus status;
    private BigDecimal totalAmount;
    private Instant createdAt;
}
```

Ví dụ cần tìm khách hàng có ít nhất một đơn hàng đã thanh toán, hoặc tìm khách hàng có đơn hàng với giá trị lớn hơn một ngưỡng. Đây là điều kiện đi qua quan hệ `Customer.orders`.

## 3. Cấu trúc cơ bản của Specification

Một Specification nhận `Root<T>`, `CriteriaQuery<?>` và `CriteriaBuilder`, rồi trả về `Predicate`:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

```java
Specification<Customer> activeCustomers = (root, query, cb) ->
    cb.equal(root.get("status"), CustomerStatus.ACTIVE);
```

`root` đại diện Entity gốc trong FROM; `query` là CriteriaQuery đang được xây dựng; `cb` tạo các biểu thức và predicate như `equal`, `and`, `or`, `exists`, `greaterThan`.

Property path trong Criteria API dùng tên thuộc tính Java (`status`, `orders`, `totalAmount`), không dùng tên cột vật lý (`order_status`, `total_amount`).

## 4. JOIN quan hệ to-one và to-many

Dùng `root.join(...)` để tạo join tới association. Có thể chỉ định loại join:

```java
Specification<Customer> hasPaidOrder = (root, query, cb) -> {
    Join<Customer, PurchaseOrder> order =
        root.join("orders", JoinType.INNER);

    return cb.equal(order.get("status"), OrderStatus.PAID);
};
```

`INNER` chỉ giữ customer có ít nhất một order phù hợp. Với association tùy chọn, `LEFT` giữ Entity gốc ngay cả khi không có Entity liên quan:

```java
Join<Customer, Address> address =
    root.join("address", JoinType.LEFT);
```

JPA Criteria thường dùng `JoinType.INNER` và `JoinType.LEFT`. Hỗ trợ RIGHT JOIN có thể khác nhau giữa provider/database và ít cần thiết trong mô hình Entity; ưu tiên thiết kế join từ phía Entity gốc phù hợp.

Với property nhúng như `address.city`, không nhất thiết tạo SQL JOIN nếu `address` là `@Embedded`; có thể đi theo path:

```java
Path<String> city = root.get("address").get("city");
return cb.equal(city, "Da Nang");
```

Chỉ dùng `join()` cho association có quan hệ persistent phù hợp; dùng `get()` để truy cập thuộc tính đơn hoặc embedded path.

## 5. JOIN to-many có thể làm Entity gốc bị lặp

Giả sử customer A có ba đơn hàng PAID. JOIN `Customer.orders` tạo ba hàng SQL cho customer A. Khi query chọn Customer, provider có thể trả cùng một root nhiều lần nếu query không yêu cầu distinct.

Trong Specification, có thể yêu cầu kết quả root duy nhất:

```java
Specification<Customer> hasPaidOrderDistinct = (root, query, cb) -> {
    Join<Customer, PurchaseOrder> order =
        root.join("orders", JoinType.INNER);

    query.distinct(true);
    return cb.equal(order.get("status"), OrderStatus.PAID);
};
```

`query.distinct(true)` đánh dấu query là distinct. Với truy vấn chọn root Entity, điều này yêu cầu loại kết quả root trùng theo semantics của JPA. Tuy nhiên, database vẫn có thể phải xử lý các hàng join; DISTINCT không tự làm join to-many trở nên rẻ.

Không bật distinct theo thói quen cho mọi Specification. Với join to-one thường không nhân root; với subquery EXISTS, query ngoài cũng không nhân root. Chỉ dùng khi join thực sự có thể tạo trùng hoặc khi hợp đồng kết quả yêu cầu.

## 6. Count đúng khi dùng Page

`Page<T>` cần tổng số phần tử. Nếu query join to-many, `count(*)` trên các hàng join có thể đếm một customer nhiều lần. Ví dụ một customer có ba order phù hợp sẽ đóng góp ba hàng join, dù chỉ là một customer.

Về mặt logic, tổng số customer duy nhất cần được tính bằng `count(distinct customer.id)` hoặc bằng một query không nhân hàng root, chẳng hạn EXISTS.

Khi dùng `JpaSpecificationExecutor`, Spring Data xây count query từ Specification. Nếu Specification đã đặt `query.distinct(true)`, count query cần đếm distinct root theo semantics của provider/framework. Hãy kiểm tra `totalElements` bằng integration test khi có join to-many; không mặc định rằng số hàng join và số root là như nhau.

Với query phức tạp có `GROUP BY`, `HAVING`, nhiều join hoặc projection tùy chỉnh, count tự sinh có thể không phản ánh đúng ý nghĩa tổng số. Khi đó dùng custom repository hoặc query riêng để định nghĩa rõ phép đếm, rồi kiểm thử cả nội dung trang và count.

## 7. Dùng EXISTS để kiểm tra có Entity liên quan

Nếu chỉ cần biết customer có ít nhất một đơn hàng PAID, không cần lấy cột order và không cần sắp xếp theo order, EXISTS thường diễn đạt đúng ý hơn JOIN:

```java
Specification<Customer> hasPaidOrder = (root, query, cb) -> {
    Subquery<Integer> subquery = query.subquery(Integer.class);
    Root<Customer> correlatedCustomer = subquery.correlate(root);
    Join<Customer, PurchaseOrder> order =
        correlatedCustomer.join("orders", JoinType.INNER);

    subquery.select(cb.literal(1))
        .where(cb.equal(order.get("status"), OrderStatus.PAID));

    return cb.exists(subquery);
};
```

`subquery.correlate(root)` liên kết subquery với customer hiện tại của query ngoài. Subquery chỉ trả về giá trị hằng khi tìm được order phù hợp; `cb.exists(subquery)` kiểm tra có ít nhất một hàng. Query ngoài vẫn có một hàng logic cho mỗi customer, nên không cần `query.distinct(true)` chỉ để khử trùng do quan hệ order.

Database optimizer có thể thực hiện EXISTS bằng semi-join hoặc kế hoạch tương đương. Hiệu năng vẫn phụ thuộc index, dữ liệu và optimizer; hãy xem execution plan khi query quan trọng.

## 8. NOT EXISTS để tìm Entity không có quan hệ phù hợp

Để tìm customer chưa từng có order bị hủy, dùng `NOT EXISTS`:

```java
Specification<Customer> hasNoCancelledOrder = (root, query, cb) -> {
    Subquery<Integer> subquery = query.subquery(Integer.class);
    Root<Customer> correlatedCustomer = subquery.correlate(root);
    Join<Customer, PurchaseOrder> order =
        correlatedCustomer.join("orders", JoinType.INNER);

    subquery.select(cb.literal(1))
        .where(cb.equal(order.get("status"), OrderStatus.CANCELLED));

    return cb.not(cb.exists(subquery));
};
```

Customer không có order nào cũng thỏa `NOT EXISTS`, vì không tồn tại hàng order CANCELLED. Đây là semantics thường mong muốn khi câu hỏi nghiệp vụ là “không có đơn hàng bị hủy”. Nếu yêu cầu là “có ít nhất một order và tất cả đều không bị hủy”, cần thêm điều kiện EXISTS cho bất kỳ order nào hoặc diễn đạt bằng logic phù hợp; hai yêu cầu này khác nhau.

## 9. JOIN hay EXISTS: chọn theo ý nghĩa

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Lọc root theo thuộc tính của một association to-one | JOIN hoặc path phù hợp |
| Lấy dữ liệu association trong projection | JOIN |
| Sắp xếp/group theo thuộc tính association | JOIN, kèm định nghĩa rõ cardinality |
| Chỉ kiểm tra có ít nhất một child thỏa điều kiện | EXISTS |
| Chỉ kiểm tra không có child thỏa điều kiện | NOT EXISTS |
| Tránh root bị nhân hàng khi child chỉ phục vụ filter | EXISTS |

JOIN không sai khi lọc to-many; chỉ cần quản lý distinct và count. EXISTS thường tự nhiên hơn khi điều kiện là một mệnh đề tồn tại và query ngoài chỉ cần root Entity.

## 10. Subquery với điều kiện IN

Subquery cũng có thể tạo tập giá trị để dùng với `IN`. Ví dụ tìm customer có ID thuộc tập khách hàng có order lớn hơn một ngưỡng:

```java
Specification<Customer> hasLargeOrder = (root, query, cb) -> {
    Subquery<Long> subquery = query.subquery(Long.class);
    Root<PurchaseOrder> order = subquery.from(PurchaseOrder.class);

    subquery.select(order.get("customer").get("id"))
        .where(cb.greaterThan(order.get("totalAmount"), new BigDecimal("1000")));

    return root.get("id").in(subquery);
};
```

Subquery trả về ID customer của các order đủ điều kiện. Query ngoài kiểm tra ID hiện tại có thuộc tập đó không. Nếu cần liên kết rõ với root và tránh tập ID lớn, có thể dùng correlated EXISTS như ví dụ trước.

Không dùng `IN`/subquery chỉ vì cú pháp trông ngắn hơn. Chọn cấu trúc giúp thể hiện đúng cardinality, null semantics và cách database có thể tối ưu.

## 11. Subquery với giá trị tổng hợp

Criteria subquery có thể trả về một giá trị tổng hợp để so sánh. Ví dụ tìm customer có một order với giá trị lớn hơn giá trị trung bình của tất cả order:

```java
Specification<Customer> hasOrderAboveAverage = (root, query, cb) -> {
    Subquery<Double> averageQuery = query.subquery(Double.class);
    Root<PurchaseOrder> orderForAverage =
        averageQuery.from(PurchaseOrder.class);

    averageQuery.select(cb.avg(orderForAverage.get("totalAmount")));

    Subquery<Integer> existsQuery = query.subquery(Integer.class);
    Root<Customer> correlatedCustomer = existsQuery.correlate(root);
    Join<Customer, PurchaseOrder> order =
        correlatedCustomer.join("orders", JoinType.INNER);

    existsQuery.select(cb.literal(1))
        .where(cb.greaterThan(order.get("totalAmount"), averageQuery));

    return cb.exists(existsQuery);
};
```

Ví dụ minh họa ý tưởng so sánh với aggregate subquery; kiểu số trả về cần khớp với kiểu thuộc tính và chữ ký Criteria API của dự án. Với `BigDecimal`, có thể dùng `BigDecimal` trong generic và expression tương ứng thay vì chuyển tùy tiện sang Double. Nếu query aggregate phức tạp hoặc cần group theo từng customer, JPQL/Querydsl/custom repository có thể dễ đọc và dễ kiểm soát hơn.

## 12. LEFT JOIN: điều kiện trong ON và WHERE

LEFT JOIN giữ root không có association phù hợp, nhưng đặt predicate trong WHERE có thể loại các root đó.

Ví dụ:

```java
Join<Customer, PurchaseOrder> order =
    root.join("orders", JoinType.LEFT);
return cb.equal(order.get("status"), OrderStatus.PAID);
```

Mặc dù dùng LEFT JOIN, predicate WHERE yêu cầu `order.status = PAID`; các hàng không có order có giá trị liên quan null và không thỏa điều kiện. Kết quả gần với INNER JOIN.

Nếu muốn giữ customer kể cả khi không có order PAID, có thể đặt điều kiện vào ON:

```java
Join<Customer, PurchaseOrder> order =
    root.join("orders", JoinType.LEFT);
order.on(cb.equal(order.get("status"), OrderStatus.PAID));
return cb.conjunction();
```

Ở đây điều kiện giới hạn các order được ghép, còn predicate ngoài luôn đúng nên customer vẫn được giữ. Nếu mục tiêu là tìm customer có order PAID thì đặt predicate trong WHERE hoặc dùng EXISTS. Nếu mục tiêu là lấy tất cả customer và chỉ ghép order PAID khi có, ON là semantics phù hợp.

## 13. Kết hợp nhiều Specification và vấn đề join bị tạo lặp

Spring Data cho phép ghép Specification bằng `.and()` và `.or()`:

```java
Specification<Customer> active = (root, query, cb) ->
    cb.equal(root.get("status"), CustomerStatus.ACTIVE);

Specification<Customer> hasPaid = hasPaidOrder;

Specification<Customer> search = active.and(hasPaid);
List<Customer> result = customerRepository.findAll(search);
```

Khi các Specification cùng gọi `root.join("orders")`, mỗi specification có thể tạo một join riêng. Điều này có thể làm SQL dư join và quan trọng hơn, thay đổi ý nghĩa logic.

Ví dụ:

- `hasPaidOrder.and(hasLargeOrder)` với hai join riêng có thể có nghĩa customer có một order PAID **và** có thể có một order khác lớn hơn 1000.
- Nếu nghiệp vụ yêu cầu cùng một order vừa PAID vừa lớn hơn 1000, hai predicate phải dùng cùng một join hoặc cùng một EXISTS subquery chứa cả hai điều kiện.

Ví dụ gom điều kiện trên cùng một child:

```java
Specification<Customer> hasPaidLargeOrder = (root, query, cb) -> {
    Subquery<Integer> subquery = query.subquery(Integer.class);
    Root<Customer> correlated = subquery.correlate(root);
    Join<Customer, PurchaseOrder> order = correlated.join("orders");

    subquery.select(cb.literal(1)).where(
        cb.equal(order.get("status"), OrderStatus.PAID),
        cb.greaterThan(order.get("totalAmount"), new BigDecimal("1000"))
    );

    return cb.exists(subquery);
};
```

Đặt các predicate trong cùng một subquery đảm bảo cùng một order phải thỏa tất cả điều kiện. Khi tách Specification để tái sử dụng, cần ghi rõ chúng nói về cùng một association row hay chỉ cần mỗi điều kiện tồn tại một row riêng.

## 14. Tránh side effect khó đoán trong Specification

Specification có thể được dùng cho query lấy dữ liệu và query đếm khi Spring Data xử lý `Page<T>`. Vì vậy nên tập trung tạo predicate và tránh thay đổi cấu trúc query ngoài phạm vi cần thiết.

Các lưu ý:

- Không tùy tiện gọi `query.orderBy(...)` trong Specification dùng chung nếu repository còn nhận Sort/Pageable; thứ tự có thể bị ghi đè hoặc ảnh hưởng count query.
- Không đặt `query.multiselect(...)` hoặc `groupBy(...)` trong Specification dùng chung cho root Entity nếu cùng Specification sẽ được dùng trong count query.
- `query.distinct(true)` có thể cần thiết khi join to-many, nhưng phải kiểm tra cả nội dung trang và count.
- Không thêm fetch join collection trong Specification dùng cho phân trang nếu chưa xử lý giới hạn collection fetch pagination.
- Nếu cần projection, grouping, aggregate hoặc query result đặc biệt, custom repository thường phù hợp hơn một Specification cố làm mọi việc.

## 15. JOIN để lọc khác JOIN FETCH để tải association

`root.join("orders")` tạo join phục vụ điều kiện truy vấn. Nó không có nghĩa collection `Customer.orders` đã được tải đầy đủ vào Entity graph.

Fetch join hoặc EntityGraph là cơ chế fetch plan riêng. Trong Criteria API, `root.fetch("orders", JoinType.LEFT)` có thể yêu cầu tải collection, nhưng kết hợp fetch collection với `Pageable` dễ gây nhân hàng và pagination trong bộ nhớ. Với trang root và collection lớn, cân nhắc hai bước: lấy trang ID trước, sau đó fetch association theo danh sách ID; hoặc dùng batch fetching/DTO projection.

Không dùng join phục vụ lọc rồi giả định association đã initialized. Kiểm tra SQL và trạng thái fetch thực tế khi cần.

## 16. Sort và pagination khi join to-many

Sort theo thuộc tính child có thể mơ hồ nếu một customer có nhiều order. “Sắp xếp customer theo order.createdAt” cần quy định rõ là theo order mới nhất, cũ nhất, lớn nhất hay một order thỏa filter nào.

Không dựa vào thứ tự ngẫu nhiên của các hàng sau join. Nếu cần sort root theo ngày order mới nhất, dùng aggregate `MAX(createdAt)` với query phù hợp, correlated subquery hoặc custom repository. Khi dùng Page, count phải đếm root duy nhất.

Thêm khóa duy nhất của root làm tie-breaker cho sort phân trang, ví dụ `createdAt DESC, id DESC`, để tránh thứ tự không ổn định khi nhiều root có cùng giá trị sort.

Với collection join và fetch pagination, tránh áp dụng `Pageable` trực tiếp trên fetch join. Nếu query join thường cũng nhân root, xác nhận DISTINCT được áp dụng đúng trước pagination trên database mục tiêu hoặc dùng EXISTS/two-phase ID pagination.

## 17. Kiểm thử JOIN và subquery

Integration test nên tạo dữ liệu có cardinality khác nhau:

1. Customer không có order.
2. Customer có một order PAID.
3. Customer có nhiều order PAID để kiểm tra root trùng.
4. Customer có một order PAID và một order CANCELLED.
5. Customer có một order PAID nhỏ và một order PENDING lớn để kiểm tra điều kiện có phải cùng một child.
6. Customer có order nhưng không có order nào thỏa predicate.

Kiểm tra:

- Kết quả JOIN có đúng root duy nhất hay cần distinct.
- EXISTS/NOT EXISTS xử lý đúng customer không có child.
- Các điều kiện AND trên cùng child có thực sự áp dụng trên cùng một hàng.
- LEFT JOIN ON/WHERE giữ hoặc loại root đúng yêu cầu.
- `Page.getTotalElements()` đếm root, không đếm hàng join.
- Sort theo child có semantics rõ và thứ tự phân trang ổn định.
- SQL và execution plan có sử dụng index phù hợp.

Không chỉ mock repository; cần integration test với JPA provider và database tương thích môi trường chạy.

## 18. Lỗi thường gặp và cách xử lý

**Customer xuất hiện nhiều lần.** JOIN to-many tạo nhiều hàng. Dùng `query.distinct(true)` nếu cần root duy nhất hoặc đổi sang EXISTS khi child chỉ dùng để lọc.

**`totalElements` lớn hơn số customer.** Count đang đếm hàng join. Kiểm tra distinct count hoặc dùng subquery EXISTS để không nhân root.

**Hai filter trên order vô tình thỏa bởi hai order khác nhau.** Hai Specification tạo hai join độc lập. Gom predicate trên cùng join/subquery nếu cần cùng một child thỏa tất cả điều kiện.

**LEFT JOIN nhưng customer không có association vẫn biến mất.** Predicate liên quan được đặt trong WHERE. Đưa điều kiện phù hợp vào ON hoặc thay đổi semantics query.

**Specification chạy được với List nhưng Page có count sai.** Kiểm tra `distinct`, group, join và count query được tạo; dùng custom count query nếu query quá phức tạp.

**Collection vẫn LAZY sau JOIN.** JOIN phục vụ lọc không phải fetch join. Dùng EntityGraph/fetch plan hoặc query tải association riêng.

**Pagination chậm sau khi thêm fetch collection.** Tránh collection fetch join trực tiếp với Pageable; dùng ID pagination hai bước, batch fetching hoặc DTO.

**Sort theo child trả thứ tự không rõ.** Xác định aggregate/child nào quyết định thứ tự và thêm tie-breaker root duy nhất.

## 19. Checklist chọn JOIN, EXISTS và DISTINCT

- Dùng JOIN khi cần thuộc tính association trong filter, projection, sort hoặc aggregate.
- Dùng EXISTS khi chỉ cần kiểm tra có child phù hợp và muốn giữ một hàng logic cho mỗi root.
- Dùng NOT EXISTS khi cần tìm root không có child thỏa điều kiện; xác định rõ có cho phép root không có child nào hay không.
- Dùng `query.distinct(true)` khi join to-many có thể làm root lặp và kết quả cần Entity duy nhất.
- Kiểm tra count query của Page; đếm distinct root hoặc đổi cấu trúc query để không nhân hàng.
- Khi ghép Specification, xác định các predicate phải cùng thỏa trên một child hay có thể thỏa trên các child khác nhau.
- Đặt điều kiện LEFT JOIN ở ON hay WHERE theo đúng semantics giữ/loại root.
- Không nhầm JOIN với FETCH; tránh collection fetch join trong pagination.
- Với sort theo to-many, định nghĩa rõ aggregate hoặc child đại diện và thêm tie-breaker.
- Dùng integration test và execution plan để xác nhận kết quả lẫn hiệu năng.

JOIN, EXISTS và subquery đều là công cụ xây predicate cho Specification, nhưng chúng biểu đạt cardinality khác nhau. JOIN kết hợp hàng liên quan và có thể nhân root; EXISTS kiểm tra điều kiện tồn tại mà không làm query ngoài nhân hàng; DISTINCT xử lý root trùng khi thật sự cần. Chọn cấu trúc theo ý nghĩa nghiệp vụ, rồi xác minh count, pagination và SQL trên database thực tế.