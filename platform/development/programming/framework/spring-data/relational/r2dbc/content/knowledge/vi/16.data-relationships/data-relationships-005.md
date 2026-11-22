# Phân biệt join ở SQL với kết hợp nhiều Publisher

Trong Spring Data Relational R2DBC, có hai cách thường gặp để lấy dữ liệu từ nhiều nguồn: yêu cầu database kết hợp các bảng bằng SQL `JOIN`, hoặc chạy nhiều thao tác reactive rồi kết hợp kết quả bằng các toán tử Reactor. Hai cách đều có thể tạo ra một object hoặc response chứa dữ liệu từ nhiều nguồn, nhưng chúng giải quyết hai bài toán khác nhau.

SQL join kết hợp các hàng theo quan hệ khóa và điều kiện ngay trong database. Database có thể tối ưu việc lọc, join, sắp xếp và chỉ truyền những cột cần thiết về ứng dụng. Kết hợp Publisher diễn ra ở tầng ứng dụng: mỗi Publisher phát dữ liệu độc lập, sau đó Reactor ghép, ánh xạ, tuần tự hóa hoặc kết hợp chúng theo quy tắc của toán tử. Reactor không tự hiểu rằng hai object có cùng `customerId` là hai hàng cần join.

Chọn đúng cách giúp giảm round trip, tránh truy vấn N+1, giữ rõ tính nhất quán dữ liệu và kiểm soát số công việc đồng thời. SQL join thường phù hợp khi dữ liệu nằm trong cùng database và có quan hệ quan hệ rõ ràng. Publisher composition phù hợp khi cần kết hợp kết quả độc lập, dữ liệu từ nhiều database hoặc từ dịch vụ bên ngoài, hoặc khi mỗi nguồn có vòng đời riêng.

## 1. SQL JOIN là gì?

SQL join kết hợp các hàng từ hai hoặc nhiều bảng dựa trên một điều kiện liên kết. Ví dụ, bảng `customer` lưu khách hàng và bảng `orders` lưu đơn hàng:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

`orders.customer_id` tham chiếu đến `customer.id`. Nếu cần danh sách đơn hàng cùng tên khách hàng, database có thể thực hiện join:

```sql
SELECT
    o.id AS order_id,
    o.total_amount,
    o.status,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = 'PAID'
ORDER BY o.id;
```

Database tìm các hàng thỏa điều kiện liên kết, lọc theo trạng thái và trả về projection đã chọn. Ứng dụng chỉ nhận kết quả cần thiết thay vì tải toàn bộ hai bảng rồi tự ghép.

### 1.1. Các loại JOIN phổ biến

| Loại JOIN | Ý nghĩa |
|---|---|
| `INNER JOIN` | Chỉ trả các hàng có cặp khớp ở cả hai phía |
| `LEFT JOIN` | Trả mọi hàng bên trái; cột bên phải là NULL nếu không có hàng khớp |
| `RIGHT JOIN` | Trả mọi hàng bên phải; cột bên trái là NULL nếu không có hàng khớp |
| `FULL OUTER JOIN` | Trả các hàng khớp và cả hàng không khớp ở hai phía, nếu database hỗ trợ |
| `CROSS JOIN` | Tạo tích Descartes giữa hai tập hàng |

Ví dụ `INNER JOIN` chỉ trả khách hàng có đơn hàng:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customer c
INNER JOIN orders o ON o.customer_id = c.id;
```

`LEFT JOIN` giữ cả khách hàng chưa có đơn:

```sql
SELECT c.id, c.name, o.id AS order_id
FROM customer c
LEFT JOIN orders o ON o.customer_id = c.id;
```

Nếu một khách hàng có nhiều đơn hàng, `LEFT JOIN` trả nhiều hàng cho khách hàng đó. Đây là đặc tính của quan hệ một-nhiều, không phải lỗi trùng dữ liệu.

## 2. Dùng JOIN trong Spring Data R2DBC

Spring Data Relational R2DBC cung cấp các abstraction hướng entity như repository và `R2dbcEntityTemplate`, cùng API SQL mức thấp là `DatabaseClient`. Với truy vấn join nhiều bảng và cần projection riêng, `DatabaseClient` thường là cách trực tiếp, rõ ràng để viết SQL và ánh xạ kết quả.

Ví dụ DTO:

```java
public record OrderSummary(
    Long orderId,
    BigDecimal totalAmount,
    String status,
    Long customerId,
    String customerName
) {}
```

Repository hoặc service có thể dùng `DatabaseClient`:

```java
Flux<OrderSummary> findPaidOrderSummaries(DatabaseClient databaseClient) {
    return databaseClient.sql("""
            SELECT
                o.id AS order_id,
                o.total_amount AS total_amount,
                o.status AS order_status,
                c.id AS customer_id,
                c.name AS customer_name
            FROM orders o
            JOIN customer c ON c.id = o.customer_id
            WHERE o.status = :status
            ORDER BY o.id
            """)
        .bind("status", "PAID")
        .map((row, metadata) -> new OrderSummary(
            row.get("order_id", Long.class),
            row.get("total_amount", BigDecimal.class),
            row.get("order_status", String.class),
            row.get("customer_id", Long.class),
            row.get("customer_name", String.class)
        ))
        .all();
}
```

Alias cột giúp tránh nhầm lẫn khi các bảng có tên cột trùng nhau như `id`, `status` hoặc `created_at`. Mapper chuyển từng `Row` thành DTO ngay trong callback; không nên giữ `Row` để sử dụng sau khi callback kết thúc.

### 2.1. Dùng @Query cho SQL JOIN cố định

Nếu truy vấn ổn định và thuộc về một repository cụ thể, có thể khai báo SQL bằng `@Query`:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    @Query("""
        SELECT o.id, o.total_amount, o.status,
               c.id AS customer_id, c.name AS customer_name
        FROM orders o
        JOIN customer c ON c.id = o.customer_id
        WHERE o.status = :status
        ORDER BY o.id
        """)
    Flux<OrderSummary> findSummariesByStatus(String status);
}
```

Việc ánh xạ projection phụ thuộc kiểu projection và khả năng mapping của phiên bản Spring Data R2DBC. Nếu DTO có cấu trúc phức tạp hoặc cần kiểm soát mapper rõ ràng, dùng `DatabaseClient` là lựa chọn dễ theo dõi hơn.

### 2.2. JOIN không được suy ra chỉ từ field tham chiếu

Spring Data Relational không hoạt động như một ORM JPA có cơ chế lazy loading quan hệ tự động. Một thuộc tính chứa ID của khách hàng không có nghĩa Spring Data tự join bảng `customer` khi đọc entity `Order`.

Ví dụ entity có thể lưu khóa ngoại:

```java
@Table("orders")
public class Order {

    @Id
    private Long id;

    private Long customerId;

    private BigDecimal totalAmount;
}
```

`customerId` chỉ là dữ liệu tham chiếu được ánh xạ từ cột. Nếu cần tên khách hàng, hãy viết join tường minh, chạy truy vấn thứ hai hoặc gọi một nguồn dữ liệu khác rồi kết hợp Publisher. Không nên giả định việc truy cập `order.getCustomer()` sẽ tự chạy truy vấn như lazy association trong JPA.

## 3. Cardinality: một-nhiều làm thay đổi hình dạng kết quả

Khi join một khách hàng với nhiều đơn hàng, một khách hàng có thể xuất hiện trên nhiều hàng kết quả:

```text
customer
+----+----------+
| id | name     |
+----+----------+
| 10 | An       |
+----+----------+

orders
+----+-------------+--------+
| id | customer_id | total  |
+----+-------------+--------+
| 1  | 10          | 100.00 |
| 2  | 10          | 250.00 |
+----+-------------+--------+

JOIN result
+----------+-------------+--------+
| cust_name| order_id    | total  |
+----------+-------------+--------+
| An       | 1           | 100.00 |
| An       | 2           | 250.00 |
+----------+-------------+--------+
```

Nếu ánh xạ từng hàng thành `Customer`, ứng dụng có thể nhận nhiều object Customer có cùng ID. Nếu cần một Customer chứa danh sách orders, phải nhóm các hàng hoặc dùng một truy vấn/aggregate phù hợp.

Với `LEFT JOIN`, các cột của bảng con có thể null:

```java
Long orderId = row.get("order_id", Long.class);
```

`orderId == null` có thể biểu thị khách hàng không có đơn hàng. DTO và mapper cần cho phép null ở những cột bên phải. Không dùng primitive `long` cho trường hợp cột có thể null.

## 4. Publisher composition là gì?

Trong Reactor, `Mono<T>` và `Flux<T>` là các Publisher. Chúng có thể được kết hợp bằng các toán tử để tạo luồng mới. Mỗi nguồn vẫn thực thi công việc riêng; Reactor điều phối tín hiệu và giá trị giữa các Publisher.

Ví dụ, một màn hình chi tiết khách hàng cần thông tin khách hàng và một danh sách đơn hàng. Có thể chạy hai truy vấn độc lập rồi kết hợp kết quả:

```java
public record CustomerDetail(
    Customer customer,
    List<Order> orders
) {}

Mono<CustomerDetail> findCustomerDetail(Long customerId) {
    Mono<Customer> customerMono = customerRepository.findById(customerId);

    Mono<List<Order>> ordersMono = orderRepository
        .findByCustomerIdOrderByCreatedAtDesc(customerId)
        .collectList();

    return Mono.zip(customerMono, ordersMono)
        .map(tuple -> new CustomerDetail(
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

`Mono.zip` đợi cả hai Mono phát ra giá trị rồi tạo một tuple. Sau đó `map` chuyển tuple thành `CustomerDetail`. Hai truy vấn có thể được subscribe như hai nguồn độc lập và được điều phối bởi Reactor.

Điểm quan trọng: `zip` ghép hai kết quả theo vị trí phát, không ghép theo `customerId` hoặc một khóa quan hệ. Trong ví dụ trên, hai Mono đều biểu diễn đúng một khách hàng cụ thể nên việc ghép vị trí là hợp lý. Nếu hai Flux chứa nhiều khách hàng và nhiều đơn hàng, `zip` không tự thực hiện relational join.

## 5. Các toán tử Reactor thường dùng khi kết hợp Publisher

Các toán tử composition có semantics khác nhau. Chọn sai toán tử có thể làm mất dữ liệu, ghép sai phần tử hoặc tạo concurrency quá lớn.

| Toán tử | Cách hoạt động | Có phải SQL-style join theo khóa không? |
|---|---|---|
| `Mono.zip(a, b)` | Đợi mỗi nguồn phát một giá trị rồi ghép tuple | Không; ghép các giá trị theo vị trí |
| `Flux.zip(a, b)` | Ghép phần tử thứ nhất với thứ nhất, thứ hai với thứ hai... | Không; ghép theo chỉ số phát |
| `combineLatest` | Sau khi mọi nguồn đã có giá trị, phát tổ hợp mới mỗi khi một nguồn cập nhật | Không; ghép trạng thái mới nhất |
| `flatMap` | Ánh xạ mỗi phần tử thành Publisher con rồi merge kết quả | Không; tạo công việc bất đồng bộ theo phần tử |
| `concatMap` | Giống flatMap nhưng xử lý Publisher con tuần tự và giữ thứ tự | Không; tuần tự hóa công việc |
| `merge` | Trộn tín hiệu từ nhiều nguồn theo thời điểm chúng phát | Không; không tạo cặp theo khóa |
| `concat` | Tiêu thụ nguồn lần lượt, nối kết quả | Không; chỉ nối luồng |
| `collectMap` / `collectMultimap` | Thu thập dữ liệu thành map theo khóa ở bộ nhớ | Có thể hỗ trợ ghép ở tầng ứng dụng, nhưng cần tự định nghĩa khóa và quản lý bộ nhớ |

### 5.1. Mono.zip: ghép các kết quả đơn

`Mono.zip` phù hợp khi mỗi nguồn trả về tối đa một giá trị và các giá trị cần được dùng cùng nhau:

```java
Mono<CustomerProfile> profileMono = profileRepository.findByCustomerId(id);
Mono<CreditScore> scoreMono = creditClient.findScore(id);

return Mono.zip(profileMono, scoreMono)
    .map(tuple -> new CustomerRiskView(
        tuple.getT1(),
        tuple.getT2()
    ));
```

Ví dụ kết hợp profile trong database với điểm tín dụng từ dịch vụ ngoài. Không có SQL join nào có thể trực tiếp nối một bảng local với Publisher từ HTTP service; composition ở ứng dụng phù hợp hơn.

Nếu một Mono hoàn tất rỗng, `Mono.zip` thông thường cũng có thể hoàn tất rỗng vì không thể tạo tuple đầy đủ. Nếu một nguồn có thể không có dữ liệu nhưng response vẫn cần được tạo, hãy quy định fallback rõ ràng:

```java
Mono<CreditScore> score = creditClient.findScore(id)
    .defaultIfEmpty(CreditScore.unknown());

return Mono.zip(profileMono, score)
    .map(tuple -> new CustomerRiskView(tuple.getT1(), tuple.getT2()));
```

Chỉ dùng giá trị mặc định khi nghiệp vụ cho phép. Không biến lỗi dịch vụ thành dữ liệu “unknown” nếu điều đó che giấu sự cố cần được báo cáo.

### 5.2. Flux.zip: ghép theo vị trí phát

`Flux.zip` ghép phần tử theo thứ tự phát, không theo ID:

```java
Flux<Tuple2<Customer, Order>> pairs = Flux.zip(
    customerRepository.findAll(),
    orderRepository.findAll()
);
```

Đây thường không phải cách ghép hai tập entity có quan hệ. Nếu nguồn khách hàng phát 10 phần tử và nguồn đơn hàng phát 25 phần tử, kết quả zip chỉ có thể ghép đến khi một nguồn không còn phần tử để tạo cặp. Khách hàng thứ nhất sẽ được ghép với đơn hàng thứ nhất dù chúng không có cùng khóa ngoại.

Chỉ dùng `zip` khi hai luồng được thiết kế để đồng bộ theo vị trí, ví dụ hai chuỗi mẫu đo được tạo theo cùng index. Không dùng nó thay cho `JOIN ... ON customer.id = orders.customer_id`.

### 5.3. combineLatest: ghép trạng thái mới nhất

`combineLatest` hữu ích khi các nguồn là luồng cập nhật trạng thái:

```java
Flux<DashboardState> dashboard = Flux.combineLatest(
    inventoryPublisher,
    pricePublisher,
    (inventory, price) -> new DashboardState(inventory, price)
);
```

Sau khi mỗi nguồn đã phát ít nhất một giá trị, mỗi lần một nguồn cập nhật thì kết quả mới được tạo từ giá trị mới nhất của tất cả nguồn. Đây là mô hình kết hợp trạng thái, phù hợp với dashboard hoặc stream sự kiện. Nó không thực hiện phép nối hàng theo khóa và có thể phát lại cùng một giá trị nguồn khi nguồn khác thay đổi.

### 5.4. merge và concat chỉ kết hợp luồng phát

`merge` trộn các phần tử từ nhiều nguồn theo thời điểm phát:

```java
Flux<Event> events = Flux.merge(orderEvents, paymentEvents);
```

Kết quả là một luồng event chung; không có tuple hoặc quan hệ join giữa event của hai nguồn.

`concat` tiêu thụ nguồn thứ nhất rồi mới đến nguồn tiếp theo:

```java
Flux<AuditEntry> history = Flux.concat(currentEntries, archivedEntries);
```

Nó nối hai luồng, không ghép các hàng tương ứng. Hãy chọn theo yêu cầu thứ tự và ngữ nghĩa dữ liệu.

### 5.5. flatMap và concatMap: gọi Publisher phụ thuộc mỗi phần tử

Nếu mỗi customer cần một truy vấn lấy hồ sơ phụ, có thể dùng `flatMap`:

```java
Flux<CustomerView> views = customerRepository.findByActiveTrue()
    .flatMap(customer -> profileRepository.findByCustomerId(customer.getId())
        .map(profile -> new CustomerView(customer, profile)));
```

Mỗi customer tạo một truy vấn phụ. Đây là cách kết hợp reactive hợp lệ nhưng có thể gây N+1 query: một truy vấn lấy danh sách customer, sau đó thêm một truy vấn cho mỗi customer.

`flatMap` có thể chạy các Publisher con đồng thời. Nên giới hạn concurrency nếu số customer lớn:

```java
Flux<CustomerView> views = customerRepository.findByActiveTrue()
    .flatMap(customer -> profileRepository.findByCustomerId(customer.getId())
        .map(profile -> new CustomerView(customer, profile)), 8);
```

Giới hạn `8` có nghĩa tối đa tám Publisher con đang được subscribe đồng thời trong nhánh này. Nó giúp kiểm soát tải nhưng không loại bỏ số lượng tổng truy vấn N+1.

Nếu cần giữ thứ tự đầu vào và thực hiện từng truy vấn một, có thể dùng `concatMap`:

```java
Flux<CustomerView> views = customerRepository.findByActiveTrue()
    .concatMap(customer -> profileRepository.findByCustomerId(customer.getId())
        .map(profile -> new CustomerView(customer, profile)));
```

`concatMap` giữ thứ tự nhưng thường làm giảm throughput vì mỗi Publisher con phải hoàn tất trước khi xử lý phần tử tiếp theo.

## 6. JOIN ở database và composition ở ứng dụng khác nhau thế nào?

| Tiêu chí | SQL JOIN | Kết hợp Publisher |
|---|---|---|
| Nơi kết hợp | Database engine | Ứng dụng/Reactor pipeline |
| Cách ghép | Điều kiện SQL như khóa ngoại, khóa chính hoặc biểu thức | Theo vị trí, thời gian phát, luồng phụ thuộc hoặc khóa do ứng dụng tự quản lý |
| Round trip | Thường một câu truy vấn cho join | Thường nhiều thao tác/nguồn, trừ khi nguồn tự batch |
| Tối ưu hóa | Database có thể chọn join algorithm và dùng index/statistics | Ứng dụng điều phối, giữ map/buffer và giới hạn concurrency |
| Dữ liệu khác nguồn | Không thể join trực tiếp qua database nếu nguồn không nằm trong cùng truy vấn/database | Có thể kết hợp database, HTTP service, cache, message stream |
| Tính nhất quán | Một câu SQL thường được đánh giá theo snapshot/statement semantics của database | Nhiều thao tác có thể quan sát dữ liệu ở các thời điểm khác nhau |
| Bộ nhớ ứng dụng | Chỉ nhận projection kết quả cần thiết | Có thể phải giữ nhiều tập kết quả hoặc map để ghép |
| Xử lý quan hệ 1-N | Database trả nhiều hàng; cần nhóm nếu muốn object lồng nhau | Ứng dụng tự nhóm theo khóa hoặc phát từng view |

SQL join thường có lợi khi các bảng nằm trong cùng database. Database được thiết kế để thực hiện join, có thể tận dụng index, thống kê và bộ nhớ/temporary space phía server. Ứng dụng không phải tải hai tập dữ liệu lớn về rồi ghép thủ công.

Publisher composition hữu ích khi các nguồn không thể được truy vấn trong cùng một SQL statement, hoặc khi các thao tác độc lập có thể chạy song song. Tuy nhiên, composition không tự mang semantics relational. Ứng dụng phải định nghĩa rõ khóa ghép, cardinality, hành vi khi thiếu dữ liệu và giới hạn tài nguyên.

## 7. Tránh N+1 query khi kết hợp Publisher

Một lỗi phổ biến là lấy danh sách entity rồi gọi repository bên trong `flatMap` cho từng hàng:

```java
Flux<CustomerView> views = customerRepository.findAll()
    .flatMap(customer -> orderRepository
        .findByCustomerId(customer.getId())
        .collectList()
        .map(orders -> new CustomerView(customer, orders)));
```

Nếu có 500 customer, cách này có thể tạo một truy vấn ban đầu và 500 truy vấn lấy orders. Đây là N+1 query. Dù mỗi truy vấn non-blocking, số round trip và áp lực lên database vẫn tăng.

### 7.1. Batch fetch bằng IN

Nếu tập customer được giới hạn ở một kích thước hợp lý, có thể lấy customer một lần, lấy toàn bộ orders theo tập ID trong một truy vấn rồi nhóm ở ứng dụng:

```java
Flux<CustomerView> findCustomerViews() {
    return customerRepository.findTop100ByActiveTrueOrderByIdAsc()
        .collectList()
        .flatMapMany(customers -> {
            if (customers.isEmpty()) {
                return Flux.empty();
            }

            List<Long> customerIds = customers.stream()
                .map(Customer::getId)
                .toList();

            return orderRepository.findByCustomerIdIn(customerIds)
                .collectMultimap(Order::getCustomerId)
                .flatMapMany(ordersByCustomer ->
                    Flux.fromIterable(customers)
                        .map(customer -> new CustomerView(
                            customer,
                            List.copyOf(ordersByCustomer.getOrDefault(
                                customer.getId(), List.of()))
                        ))
                );
        });
}
```

Ý tưởng của ví dụ:

1. Lấy tối đa 100 customer theo một thứ tự ổn định.
2. Trích danh sách ID.
3. Thực hiện một truy vấn `IN` để lấy orders của tất cả customer trong batch.
4. Gom orders theo `customerId` bằng `collectMultimap`.
5. Duyệt customer và tạo `CustomerView`, dùng danh sách rỗng nếu customer chưa có đơn.

Đây là batch composition ở ứng dụng, không phải SQL join. Nó giảm số truy vấn xuống còn hai trong trường hợp này, nhưng giữ danh sách customer và orders trong bộ nhớ. Cần giới hạn batch size và xử lý giới hạn bind parameter của database. Với dữ liệu lớn, xử lý theo nhiều batch thay vì `findAll().collectList()`.

### 7.2. Khi nào batch composition phù hợp?

Phương án này có thể phù hợp khi:

- Cần giữ entity customer và danh sách orders thành một cấu trúc response.
- Repository hiện có API `findByCustomerIdIn` thuận tiện.
- Kích thước mỗi batch có giới hạn rõ ràng.
- Cần ghép thêm dữ liệu ở tầng ứng dụng mà SQL join không thuận tiện.
- Dữ liệu cần kết hợp đến từ nhiều nguồn hoặc nhiều database.

Nếu cả hai bảng nằm trong cùng database và chỉ cần một projection, SQL join thường đơn giản hơn và có thể hiệu quả hơn.

## 8. Ghép nhiều nguồn dữ liệu theo khóa

Reactor không có toán tử mặc định hiểu khóa quan hệ của hai Flux rồi tự thực hiện hash join. Nếu muốn ghép theo khóa ở ứng dụng, cần xây dựng cấu trúc tra cứu hoặc xử lý theo batch.

Ví dụ hai nguồn phát `Customer` và `Profile`, có thể thu thập profile thành map theo customer ID rồi tra cứu:

```java
Mono<List<CustomerView>> combineCustomersAndProfiles(
        Flux<Customer> customers,
        Flux<Profile> profiles) {

    Mono<List<Customer>> customerList = customers.collectList();
    Mono<Map<Long, Profile>> profileMap = profiles
        .collectMap(Profile::getCustomerId);

    return Mono.zip(customerList, profileMap)
        .map(tuple -> tuple.getT1().stream()
            .map(customer -> new CustomerView(
                customer,
                tuple.getT2().get(customer.getId())
            ))
            .toList());
}
```

Đoạn code minh họa việc ghép theo khóa bằng map. Cần xác định hành vi khi profile thiếu, có nhiều profile cho một customer hoặc ID trùng lặp. `collectMap` chỉ giữ một giá trị cho mỗi khóa theo quy tắc của toán tử; nếu một khóa có nhiều giá trị, hãy dùng `collectMultimap` hoặc tự định nghĩa cách chọn.

Ví dụ trên cũng materialize toàn bộ hai nguồn. Chỉ dùng khi kích thước bị giới hạn. Với tập lớn, chia batch, dùng cursor hoặc đẩy join về database.

## 9. Khi cần kết hợp dữ liệu từ nhiều database hoặc dịch vụ

SQL join không thể trực tiếp kết hợp một bảng PostgreSQL với response của một HTTP service hoặc một Publisher từ message broker. Publisher composition là lựa chọn tự nhiên ở tầng ứng dụng.

Ví dụ lấy đơn hàng từ database và thông tin giao hàng từ service ngoài:

```java
Mono<OrderTrackingView> findTracking(Long orderId) {
    Mono<Order> order = orderRepository.findById(orderId);

    return order.flatMap(value ->
        shippingClient.findTracking(value.getId())
            .map(tracking -> new OrderTrackingView(value, tracking))
    );
}
```

Ở đây, yêu cầu tracking phụ thuộc vào ID của đơn hàng, vì vậy `flatMap` là cách composition hợp lý. Nếu shipping service không tìm thấy dữ liệu, cần quyết định response rỗng, trạng thái chưa có tracking hay lỗi nghiệp vụ.

Nếu có nhiều đơn hàng, gọi dịch vụ ngoài cho từng hàng có thể tạo N+1 HTTP calls. Hãy ưu tiên API batch của service ngoài nếu có, hoặc giới hạn concurrency và đặt timeout:

```java
Flux<OrderTrackingView> findTrackings() {
    return orderRepository.findByStatus("SHIPPED")
        .flatMap(order -> shippingClient.findTracking(order.getId())
            .map(tracking -> new OrderTrackingView(order, tracking)), 8);
}
```

Concurrency hữu hạn giúp giới hạn số request đồng thời, nhưng vẫn có một request cho mỗi đơn hàng. Nếu service hỗ trợ batch tracking theo danh sách ID, batch API thường giảm round trip tốt hơn.

## 10. Tính nhất quán khi chạy nhiều Publisher

Một SQL join thường được thực hiện như một statement trên database. Tập kết quả tuân theo semantics snapshot/isolation của database cho statement đó. Ngược lại, khi chạy hai truy vấn độc lập rồi ghép Publisher, hai truy vấn có thể quan sát dữ liệu ở các thời điểm khác nhau.

Ví dụ:

1. Truy vấn thứ nhất đọc thông tin customer.
2. Một transaction khác cập nhật customer hoặc thêm order.
3. Truy vấn thứ hai đọc danh sách order.
4. Ứng dụng ghép hai kết quả thành một response.

Response có thể chứa customer ở trạng thái trước cập nhật nhưng orders ở trạng thái sau cập nhật. Điều này có thể chấp nhận với màn hình tổng quan, nhưng không phù hợp với một nghiệp vụ yêu cầu snapshot nhất quán.

### 10.1. Dùng reactive transaction khi cần

Nếu các Publisher đều truy cập cùng một database và cần cùng transaction, có thể compose chúng trong một reactive transaction do Spring quản lý:

```java
@Transactional(readOnly = true)
public Mono<CustomerDetail> findConsistentDetail(Long customerId) {
    Mono<Customer> customer = customerRepository.findById(customerId);

    Mono<List<Order>> orders = orderRepository
        .findByCustomerId(customerId)
        .collectList();

    return Mono.zip(customer, orders)
        .map(tuple -> new CustomerDetail(tuple.getT1(), tuple.getT2()));
}
```

Transaction manager và các repository phải dùng cùng `ConnectionFactory` để tham gia cùng reactive transaction. Mức isolation của database quyết định mức nhất quán thực tế; `readOnly = true` không tự đồng nghĩa với snapshot isolation.

Không phải lúc nào hai thao tác song song trong `Mono.zip` cũng phù hợp với mọi transaction manager/driver. Nếu cần bảo đảm thứ tự hoặc driver có giới hạn về sử dụng một connection trong transaction, hãy cân nhắc compose tuần tự bằng `flatMap`/`then` và kiểm thử trên driver thực tế.

### 10.2. Không thể tạo một transaction ACID chung cho HTTP service

Một reactive transaction R2DBC không bao trùm một HTTP request đến service khác. Nếu một use case cập nhật database rồi gọi dịch vụ bên ngoài, cần thiết kế tính nhất quán bằng các mẫu như outbox, saga hoặc quy trình bù trừ tùy nghiệp vụ. `Mono.zip` chỉ kết hợp tín hiệu; nó không tạo transaction phân tán.

## 11. Backpressure, concurrency và thời gian giữ tài nguyên

Kết hợp Publisher vẫn tuân theo Reactive Streams demand, nhưng các toán tử có thể tạo buffer hoặc nhiều công việc đồng thời.

- `zip` điều phối demand từ các nguồn để tạo tuple; tốc độ của kết quả bị ảnh hưởng bởi nguồn chậm nhất.
- `flatMap` có thể subscribe nhiều Publisher con cùng lúc. Đặt concurrency để giới hạn tải.
- `concatMap` xử lý lần lượt, giảm concurrency nhưng có thể tăng latency.
- `collectList`, `collectMap` và `collectMultimap` giữ dữ liệu trong bộ nhớ cho đến khi nguồn hoàn tất.
- `merge` có thể phát kết quả từ nguồn nhanh hơn trước nguồn chậm hơn.

Nếu Publisher đang giữ connection database, việc downstream đọc chậm có thể kéo dài thời gian giữ connection. Nếu một Flux lớn được ghép với nhiều truy vấn con, pool có thể bị bão hòa. Hãy giới hạn số hàng, batch size, concurrency và thời gian xử lý.

Ví dụ concurrency hữu hạn:

```java
customerRepository.findByActiveTrue()
    .flatMap(this::enrichCustomer, 8);
```

Giới hạn 8 áp dụng cho số inner Publisher đồng thời trong toán tử này. Nó không giới hạn tổng số customer được phát ra. Nếu cần giới hạn tổng số hàng, hãy đặt điều kiện/limit ở SQL hoặc dùng API phân trang.

## 12. Cancellation và xử lý lỗi khi ghép Publisher

Khi một Publisher trong composition phát lỗi, các toán tử như `zip` hoặc `flatMap` thường truyền lỗi xuống downstream và hủy các subscription liên quan theo semantics của Reactor. Khi downstream hủy toàn bộ pipeline, cancellation được truyền ngược tới nguồn trong phạm vi các thành phần hỗ trợ.

Điều này có ý nghĩa với truy vấn database:

- Không nuốt lỗi database thành kết quả rỗng nếu đó là sự cố cần báo cáo.
- Đặt timeout cho nguồn bên ngoài có thể treo.
- Khi fallback, chỉ dùng giá trị mặc định nếu nghiệp vụ cho phép.
- Bảo đảm tài nguyên được release khi complete, error hoặc cancel.
- Không gọi `subscribe()` thủ công bên trong service để chạy một nhánh tách rời khỏi pipeline; làm vậy khiến caller khó điều khiển cancellation và lỗi.

Ví dụ fallback có chủ đích cho profile tùy chọn:

```java
Mono<Profile> profile = profileClient.findByCustomerId(customerId)
    .onErrorResume(ProfileNotFoundException.class, error -> Mono.empty());

return Mono.zip(customerRepository.findById(customerId),
                profile.defaultIfEmpty(Profile.empty()))
    .map(tuple -> new CustomerView(tuple.getT1(), tuple.getT2()));
```

Ví dụ chỉ chuyển lỗi “không tìm thấy profile” thành giá trị mặc định. Lỗi timeout hoặc database unavailable vẫn được truyền xuống để xử lý ở tầng phù hợp.

## 13. Chọn cách nào trong từng tình huống?

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Hai bảng trong cùng database, có khóa liên kết | SQL `JOIN` | Database tối ưu join và giảm round trip |
| Cần projection báo cáo từ nhiều bảng | `DatabaseClient` hoặc `@Query` với JOIN | Chỉ lấy cột cần thiết và ánh xạ DTO |
| Cần một customer và danh sách orders của customer | JOIN rồi nhóm, hoặc hai truy vấn + `Mono.zip` | Chọn theo cardinality, dữ liệu và yêu cầu nhất quán |
| Kết hợp dữ liệu database với HTTP service | Publisher composition | Nguồn không cùng nằm trong một SQL statement |
| Kết hợp hai Mono độc lập, mỗi nguồn một giá trị | `Mono.zip` | Tạo tuple từ hai kết quả đơn |
| Kết hợp hai Flux theo index phát | `Flux.zip` | Chỉ phù hợp khi hai luồng đồng bộ theo vị trí |
| Theo dõi trạng thái mới nhất từ nhiều nguồn | `combineLatest` | Tạo state mới khi bất kỳ nguồn nào cập nhật |
| Gọi một Publisher phụ thuộc mỗi phần tử | `flatMap` hoặc `concatMap` | Chọn concurrency và thứ tự phù hợp |
| Gộp event từ nhiều nguồn | `merge` | Trộn luồng, không ghép theo khóa |
| Tập dữ liệu lớn cần liên kết theo khóa | SQL JOIN hoặc batch query có giới hạn | Tránh materialize toàn bộ hai tập trong heap |

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `Flux.zip` để ghép customer và orders | Ghép theo vị trí, có thể ghép sai khóa | Dùng SQL JOIN hoặc tự ghép theo khóa |
| Cho rằng Reactor tự hiểu quan hệ entity | Dữ liệu liên quan không được tải tự động | Viết JOIN hoặc truy vấn bổ sung rõ ràng |
| Dùng `flatMap` truy vấn phụ cho mọi hàng | N+1 query hoặc HTTP calls | Dùng JOIN, batch fetch hoặc API batch |
| `flatMap` không giới hạn trên nguồn lớn | Quá nhiều truy vấn đồng thời | Đặt concurrency phù hợp pool và downstream |
| Dùng `collectList()` cho dữ liệu không giới hạn | Heap tăng theo toàn bộ tập kết quả | Phân trang hoặc batch có giới hạn |
| Bỏ `ORDER BY` trong truy vấn chọn First | Hàng được chọn không xác định | Thêm thứ tự ổn định và khóa tie-breaker |
| Dùng INNER JOIN khi cần giữ hàng không có quan hệ | Hàng bên trái không có cặp khớp bị mất | Dùng LEFT JOIN |
| Ánh xạ LEFT JOIN vào primitive cho cột bên phải | Không biểu diễn được SQL NULL | Dùng wrapper hoặc DTO nullable |
| Không đặt alias khi các bảng có cột trùng tên | Mapper đọc nhầm cột | Đặt alias riêng cho từng cột |
| Ghép hai truy vấn riêng mà giả định cùng snapshot | Response có thể chứa dữ liệu ở hai thời điểm khác nhau | Dùng transaction/isolation phù hợp khi cần |
| Nghĩ Mono.zip tạo transaction chung | Không có bảo đảm transaction chỉ từ zip | Cấu hình reactive transaction manager và cùng ConnectionFactory |
| Gọi `subscribe()` bên trong service | Mất kiểm soát lỗi và cancellation | Trả Publisher và compose trong pipeline |
| Dùng `merge`/`concat` như phép join | Kết quả chỉ được trộn hoặc nối | Chọn operator đúng semantics |

## 15. Kiểm thử SQL JOIN và Publisher composition

Hai cách tiếp cận cần được kiểm thử theo các khía cạnh khác nhau.

### 15.1. Kiểm thử JOIN

Chuẩn bị dữ liệu bao gồm:

- Customer có nhiều orders.
- Customer không có order.
- Order có trạng thái khác nhau.
- Giá trị nullable ở phía bảng được LEFT JOIN.
- Nhiều bảng có cột trùng tên như `id` và `status`.

Xác nhận số hàng trả về, alias, mapping DTO, hành vi INNER/LEFT JOIN và thứ tự kết quả. Với quan hệ 1-N, xác nhận ứng dụng không vô tình xem mỗi hàng join là một customer duy nhất.

### 15.2. Kiểm thử composition

Với `Mono.zip`, kiểm tra:

- Cả hai nguồn phát giá trị.
- Một nguồn hoàn tất rỗng.
- Một nguồn phát lỗi.
- Một nguồn chậm hoặc timeout.
- Fallback chỉ áp dụng cho loại lỗi được phép.

Với `flatMap`, kiểm tra concurrency, thứ tự phát khi cần, lỗi từ Publisher con và cancellation. Với batch composition, kiểm tra tập rỗng, ID không tồn tại, ID trùng và giới hạn kích thước.

Ví dụ kiểm tra kết quả `Mono.zip`:

```java
StepVerifier.create(customerService.findCustomerDetail(10L))
    .assertNext(detail -> {
        assertEquals(10L, detail.customer().getId());
        assertNotNull(detail.orders());
    })
    .verifyComplete();
```

### 15.3. Kiểm thử nhất quán và hiệu năng

Nếu nghiệp vụ yêu cầu cùng snapshot, kiểm thử transaction trên database thật hoặc database tương thích với isolation level được triển khai. Đo số câu SQL, số round trip, query latency, connection hold time, heap và pending acquire để so sánh JOIN với batch composition.

Không chỉ so sánh thời gian một lần chạy với vài hàng. Hãy dùng dữ liệu có quy mô gần thực tế và mô phỏng số request đồng thời.

## 16. Quy trình quyết định

Khi cần dữ liệu từ nhiều nguồn, hãy xác định theo trình tự:

1. Các nguồn có nằm trong cùng database và cùng một câu SQL truy cập được không?
2. Có khóa hoặc điều kiện quan hệ rõ ràng để JOIN không?
3. Cần một projection theo từng cặp hàng hay một object cha chứa danh sách con?
4. Nếu dùng nhiều Publisher, mỗi nguồn trả một giá trị hay nhiều giá trị?
5. Có cần ghép theo khóa không, hay chỉ ghép theo vị trí/trạng thái mới nhất?
6. Có nguy cơ N+1 query hoặc N+1 HTTP request không?
7. Có cần snapshot nhất quán giữa các nguồn không?
8. Cần giới hạn batch size, concurrency, timeout và bộ nhớ như thế nào?
9. Hành vi khi một nguồn rỗng hoặc lỗi có phù hợp nghiệp vụ không?
10. Đã kiểm thử cancellation và cleanup tài nguyên chưa?

## 17. Nguyên tắc cần nhớ

- SQL `JOIN` kết hợp hàng theo điều kiện quan hệ ở database; Reactor composition kết hợp các Publisher ở tầng ứng dụng.
- `Mono.zip` và `Flux.zip` ghép theo vị trí phát, không tự ghép theo khóa ngoại.
- `combineLatest` kết hợp trạng thái mới nhất; `merge` trộn luồng; `concat` nối luồng.
- `flatMap` gọi Publisher phụ thuộc từng phần tử; đặt concurrency để kiểm soát tải và chú ý N+1.
- `concatMap` giữ thứ tự xử lý tuần tự, thường đổi lại bằng throughput thấp hơn.
- Với các bảng trong cùng database, ưu tiên SQL JOIN khi đó là phép liên kết dữ liệu tự nhiên và có thể được database tối ưu.
- Dùng Publisher composition khi nguồn độc lập, khác database hoặc là dịch vụ ngoài, hoặc khi workflow cần điều phối nhiều thao tác.
- Với quan hệ một-nhiều, xác định rõ cách nhóm hàng và cách xử lý phía bảng có thể null.
- Batch fetch có thể giảm N+1 nhưng phải giới hạn kích thước và bộ nhớ.
- Nhiều truy vấn riêng có thể nhìn thấy dữ liệu ở các thời điểm khác nhau; dùng reactive transaction/isolation khi cần tính nhất quán.
- `Mono.zip` không tự tạo transaction phân tán và không thể bao trùm HTTP service.
- Trả Publisher về caller, không gọi `subscribe()` hoặc `block()` tùy tiện trong service.
- Kiểm thử số round trip, cardinality, lỗi, cancellation, thứ tự và tài nguyên trên driver/database thực tế.

SQL join và kết hợp Publisher đều có vai trò trong Spring Data Relational R2DBC, nhưng không thể thay thế lẫn nhau. Join để database kết hợp các hàng quan hệ trong cùng nguồn dữ liệu; Publisher composition để ứng dụng điều phối các kết quả độc lập và các nguồn khác nhau. Khi chọn đúng semantics, kiểm soát N+1, cardinality, transaction và concurrency, lớp truy cập dữ liệu sẽ rõ ràng hơn và tránh được nhiều chi phí không cần thiết.
