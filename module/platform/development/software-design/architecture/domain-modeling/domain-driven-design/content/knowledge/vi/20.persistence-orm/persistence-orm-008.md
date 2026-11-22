# N+1, kế hoạch nạp dữ liệu và chi phí của aggregate lớn

Trong Domain-Driven Design (DDD), Aggregate xác định ranh giới nhất quán của một nhóm đối tượng miền. Trong Java Persistence API (JPA) và các ORM như Hibernate, Aggregate thường được ánh xạ thành một object graph gồm Entity và các quan hệ. Tuy nhiên, việc một đối tượng có quan hệ với nhiều đối tượng khác không có nghĩa mọi truy vấn đều cần nạp toàn bộ graph đó.

Một truy vấn có thể trông đơn giản trong Java nhưng tạo ra rất nhiều câu SQL. Trường hợp điển hình là lỗi **N+1**: ứng dụng tải một danh sách bằng một truy vấn, sau đó ORM phát thêm một truy vấn cho từng phần tử khi code truy cập quan hệ lazy. Ở chiều ngược lại, nạp quá nhiều quan hệ cùng lúc có thể tạo ra kết quả join rất lớn, lặp dữ liệu và tiêu tốn bộ nhớ.

Bài học này giải thích cách nhận diện N+1, thiết kế fetch plan theo từng use case, lựa chọn giữa join fetch, EntityGraph, batch fetching và DTO projection, xử lý phân trang khi có collection, đồng thời đánh giá chi phí của Aggregate quá lớn. Mục tiêu là để mô hình miền giữ đúng ranh giới nghiệp vụ, còn truy vấn chỉ nạp lượng dữ liệu cần thiết cho từng thao tác.

## 1. Vì sao cần quan tâm đến kế hoạch nạp dữ liệu?

### 1.1. Object graph không đồng nghĩa với một lần truy vấn

Giả sử hệ thống bán hàng có Order và Customer. Một Order tham chiếu đến một Customer:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    // ...
}
~~~

Trong code, truy cập khách hàng có vẻ như chỉ là đọc một thuộc tính:

~~~java
List<Order> orders = orderRepository.findRecentOrders();

for (Order order : orders) {
    System.out.println(order.getCustomer().getName());
}
~~~

Nhưng ORM có thể thực hiện:

1. Một truy vấn tải danh sách Order.
2. Một truy vấn tải Customer cho Order thứ nhất.
3. Một truy vấn tải Customer cho Order thứ hai.
4. Tiếp tục cho đến khi mọi Customer cần thiết được nạp.

Nếu có 100 đơn hàng và mỗi đơn tham chiếu một khách hàng khác nhau, tổng số truy vấn có thể gần 101. Nếu nhiều đơn cùng tham chiếu một Customer và persistence context đang quản lý Customer đó, ORM có thể tái sử dụng instance đã nạp; vì vậy số truy vấn thực tế phụ thuộc dữ liệu và cache cấp một.

### 1.2. N+1 là vấn đề về số lần truy cập dữ liệu

N+1 mô tả một mẫu truy vấn:

- Nạp tập hợp gốc bằng một truy vấn.
- Với mỗi phần tử trong tập hợp, phát sinh thêm truy vấn để lấy dữ liệu liên quan.

Ví dụ:

~~~sql
-- Truy vấn đầu tiên: tải các đơn gần đây
SELECT id, customer_id, status, created_at
FROM orders
ORDER BY created_at DESC;

-- Sau đó ORM có thể chạy một truy vấn cho mỗi customer
SELECT id, name
FROM customers
WHERE id = ?;
~~~

Nếu N là số đơn hàng cần xử lý, tổng truy vấn có thể là 1 + N. Khi N tăng, độ trễ mạng, chi phí parse SQL, lập kế hoạch truy vấn và round trip tăng theo.

N+1 không nhất thiết chỉ liên quan đến quan hệ to-one. Nó cũng xuất hiện khi tải danh sách cha rồi lần lượt truy cập collection con, hoặc khi code gọi repository bên trong vòng lặp.

### 1.3. Một truy vấn ít hơn chưa chắc luôn nhanh hơn

Có thể sửa N+1 bằng cách join tất cả quan hệ trong một câu SQL. Nhưng nếu join nhiều collection, số dòng kết quả có thể tăng theo tích số phần tử của các collection.

Ví dụ một Order có 10 OrderLine và mỗi OrderLine có 4 Discount. Join cả hai collection có thể tạo khoảng 40 dòng cho một Order trước khi ORM tái dựng object graph. Nếu có nhiều Order, dữ liệu lặp càng lớn.

Vì vậy, mục tiêu không phải chỉ giảm số câu SQL. Cần cân bằng:

- Số round trip.
- Số dòng và số cột trả về.
- Dữ liệu bị lặp do join.
- Bộ nhớ cần để dựng object graph.
- Khả năng phân trang.
- Mức độ nhất quán cần thiết của use case.

## 2. N+1 hình thành như thế nào?

### 2.1. Ví dụ với quan hệ to-one

Giả sử Order có quan hệ ManyToOne đến Customer và được cấu hình LAZY.

~~~java
@Entity
@Table(name = "orders")
public class Order {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    public Customer getCustomer() {
        return customer;
    }
}
~~~

Repository:

~~~java
public interface OrderRepository
    extends JpaRepository<Order, Long> {

    List<Order> findTop100ByOrderByCreatedAtDesc();
}
~~~

Application service:

~~~java
public List<OrderSummary> recentOrderSummaries() {
    List<Order> orders =
        orderRepository.findTop100ByOrderByCreatedAtDesc();

    return orders.stream()
        .map(order -> new OrderSummary(
            order.getId(),
            order.getCustomer().getName()
        ))
        .toList();
}
~~~

Truy vấn repository tải 100 Order. Khi mapper gọi getCustomer().getName(), Hibernate có thể tải từng Customer riêng. Nếu 100 Order có 100 Customer khác nhau và chưa có trong persistence context, số câu SQL có thể là 101.

### 2.2. Ví dụ với collection

Order có thể có danh sách dòng hàng:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines = new ArrayList<>();
~~~

Code:

~~~java
List<Order> orders = orderRepository.findAll();

for (Order order : orders) {
    int lineCount = order.getLines().size();
    // ...
}
~~~

Truy vấn đầu tải các Order. Mỗi lần gọi getLines() có thể kích hoạt một truy vấn riêng để tải collection tương ứng. Với N Order, tổng số truy vấn có thể là 1 + N.

### 2.3. N+1 có thể bị che khuất bởi mapper và serializer

N+1 không nhất thiết xuất hiện ở dòng code truy vấn. Nó có thể bị kích hoạt sâu hơn trong:

- MapStruct hoặc mapper tự viết.
- DTO assembler.
- Template render.
- JSON serializer.
- Logging gọi toString() và vô tình duyệt quan hệ.
- Code tính toán hoặc kiểm tra collection.

Một endpoint có thể tải Order đúng cách, nhưng serializer truy cập customer.address và order.lines, khiến các truy vấn phát sinh muộn hơn.

Do đó, hãy quan sát toàn bộ luồng từ lúc vào use case đến khi dữ liệu được chuyển thành response, không chỉ nhìn repository method.

### 2.4. EAGER không phải cách sửa tổng quát

Đổi LAZY thành EAGER có thể làm truy vấn quan hệ được kích hoạt sớm hơn, nhưng không bảo đảm ORM sẽ dùng một join duy nhất. Với một số kế hoạch tải, ORM vẫn có thể phát thêm select cho từng association.

EAGER cũng có thể làm các use case không cần quan hệ đó phải tải dữ liệu dư thừa. Vì vậy, đừng sửa N+1 bằng cách chuyển mọi quan hệ sang EAGER. Hãy xác định dữ liệu cần cho từng use case và khai báo fetch plan tương ứng.

## 3. Fetch plan là gì?

### 3.1. Fetch plan mô tả dữ liệu cần nạp cho một use case

Fetch plan (kế hoạch nạp dữ liệu) xác định những association hoặc thuộc tính nào cần được tải khi thực hiện một thao tác cụ thể.

Ví dụ:

| Use case | Dữ liệu cần |
|---|---|
| Hiển thị danh sách đơn | Order ID, trạng thái, ngày tạo, tên Customer |
| Xem chi tiết đơn | Order, Customer, OrderLine |
| Hủy đơn | Order và các dữ liệu cần để kiểm tra chính sách hủy |
| Báo cáo doanh thu | Các cột tổng hợp, không cần dựng toàn bộ Entity |
| Xử lý đơn trong batch | Chỉ các quan hệ cần cho bước xử lý, theo từng lô |

Cùng một Aggregate có thể cần các fetch plan khác nhau. Không có một cấu hình tải tối ưu cho mọi use case.

### 3.2. Phân biệt mapping fetch và use case fetch

Mapping fetch mô tả mặc định của quan hệ trong ORM. Use case fetch mô tả dữ liệu cần cho một truy vấn cụ thể.

Trong JPA:

- **LAZY**: association được tải khi được truy cập, nếu provider có thể trì hoãn việc nạp.
- **EAGER**: association phải có sẵn khi Entity được nạp theo hợp đồng persistence; provider có thể dùng join hoặc select bổ sung.

FetchType là metadata của mapping. Nó không phải công cụ đầy đủ để tối ưu mọi truy vấn. Fetch plan cụ thể nên được thể hiện ở repository query, EntityGraph hoặc projection theo nhu cầu use case.

### 3.3. Nên bắt đầu với LAZY cho association

Với các association có thể làm tăng đáng kể object graph, LAZY thường giúp tránh nạp dữ liệu không cần thiết. JPA quy định mặc định:

- OneToMany và ManyToMany là LAZY.
- ManyToOne và OneToOne mặc định EAGER nếu không chỉ định.

Do đó, nhiều đội chủ động khai báo LAZY cho ManyToOne và OneToOne để tránh vô tình tải quan hệ trong các truy vấn không cần đến chúng.

Tuy nhiên, LAZY không tự giải quyết N+1. Nó chỉ trì hoãn việc tải. Nếu code truy cập association trong vòng lặp, N+1 vẫn có thể xảy ra. Cần kết hợp LAZY với fetch plan phù hợp.

### 3.4. Fetch plan không thay đổi quyền sở hữu miền

Việc truy vấn Order cùng Customer không có nghĩa Order sở hữu vòng đời của Customer. ORM mapping thể hiện quan hệ lưu trữ và cách tải dữ liệu; nó không tự quyết định Aggregate boundary.

DDD xác định ranh giới dựa trên invariant và quyền sở hữu nghiệp vụ. Fetch plan phục vụ truy vấn của use case. Không nên gộp Aggregate chỉ để có thể join dữ liệu trong một câu SQL.

## 4. Dùng JOIN FETCH cho quan hệ cần đọc cùng

### 4.1. Join fetch quan hệ to-one

Nếu màn hình danh sách đơn luôn cần tên khách hàng, có thể nạp Order và Customer trong cùng truy vấn:

~~~java
public interface OrderRepository
    extends JpaRepository<Order, Long> {

    @Query("""
        select o
        from Order o
        join fetch o.customer
        where o.createdAt >= :from
        order by o.createdAt desc
        """)
    
    List<Order> findRecentWithCustomer(@Param("from") Instant from);
}
~~~

Hibernate có thể tạo SQL tương tự:

~~~sql
SELECT o.id, o.status, o.created_at,
       c.id, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.created_at >= ?
ORDER BY o.created_at DESC;
~~~

Một round trip lấy cả Order và Customer. Cách này phù hợp khi association cần thiết cho kết quả và số lượng dòng không bị nhân lên quá mức.

Dùng JOIN thay vì LEFT JOIN có nghĩa chỉ lấy Order có Customer phù hợp. Nếu quan hệ có thể null và vẫn muốn giữ Order không có Customer, hãy cân nhắc LEFT JOIN FETCH.

### 4.2. Join fetch collection

Nếu trang chi tiết luôn cần các dòng hàng, có thể fetch collection:

~~~java
@Query("""
    select distinct o
    from Order o
    left join fetch o.lines
    where o.id = :id
    """)
Optional<Order> findDetailById(Long id);
~~~

Một Order có nhiều OrderLine nên kết quả SQL có nhiều dòng cho cùng Order. Từ khóa DISTINCT giúp yêu cầu kết quả entity không trùng trong JPQL. Cách Hibernate xử lý distinct và khử trùng lặp có khác biệt theo phiên bản; cần xem SQL thực tế và hành vi provider đang dùng.

Join fetch collection thường phù hợp cho truy vấn chi tiết một Aggregate có kích thước vừa phải. Nó không mặc nhiên phù hợp cho danh sách nhiều Aggregate.

### 4.3. Tránh join nhiều collection lớn trong một truy vấn

Giả sử Order có lines và payments. Join fetch cả hai collection có thể tạo tích số dòng:

- 5 dòng hàng.
- 3 khoản thanh toán.
- Có thể tạo 15 dòng kết quả cho một Order.

Nếu mỗi Order có nhiều collection, dữ liệu bị nhân lên nhanh chóng. Hibernate cũng có thể từ chối fetch đồng thời nhiều bag collection tùy mapping và phiên bản.

Cân nhắc:

- Fetch join quan hệ to-one.
- Fetch một collection cần thiết.
- Dùng batch fetching cho collection khác.
- Chạy truy vấn thứ hai để tải dữ liệu liên quan.
- Dùng DTO projection nếu chỉ cần dữ liệu hiển thị.

Hai truy vấn có kế hoạch rõ ràng thường tốt hơn một truy vấn khổng lồ trả về rất nhiều dòng lặp.

## 5. Dùng EntityGraph để khai báo dữ liệu cần nạp

### 5.1. EntityGraph mô tả association cần fetch

JPA EntityGraph cho phép khai báo association cần tải cho một truy vấn mà không phải viết toàn bộ JPQL join fetch.

Với Spring Data JPA:

~~~java
@EntityGraph(attributePaths = {"customer"})
List<Order> findByStatus(OrderStatus status);
~~~

Để tải thêm lines:

~~~java
@EntityGraph(attributePaths = {"customer", "lines"})
Optional<Order> findDetailById(Long id);
~~~

EntityGraph hữu ích khi muốn tái sử dụng repository method nhưng thay đổi fetch plan. Provider quyết định cách thực thi cụ thể; hãy kiểm tra SQL để biết nó có join hay phát truy vấn bổ sung.

### 5.2. Fetch graph và load graph

JPA định nghĩa hai cách sử dụng EntityGraph qua hint:

- **fetchgraph**: các thuộc tính được chỉ định là cần fetch; những thuộc tính khác được xử lý theo quy tắc fetch graph, thường được xem như LAZY cho truy vấn đó.
- **loadgraph**: các thuộc tính được chỉ định là cần fetch; những thuộc tính khác giữ fetch behavior theo mapping.

Spring Data hỗ trợ @EntityGraph và có thể chỉ định type nếu cần. Phải hiểu semantics khi mapping có EAGER association, tránh giả định EntityGraph sẽ luôn tạo đúng một câu SQL.

### 5.3. EntityGraph không giải quyết mọi vấn đề

EntityGraph vẫn có thể dẫn đến join collection lớn, nhân bản dòng hoặc giới hạn phân trang. Nó là cách mô tả fetch plan, không phải cam kết về một dạng SQL hoặc chi phí cụ thể.

Dùng EntityGraph khi nó làm rõ dữ liệu use case cần. Nếu cần kiểm soát chính xác câu SQL, projection hoặc JPQL query có thể phù hợp hơn.

## 6. Batch fetching và subselect fetching

### 6.1. Batch fetching giảm số truy vấn lazy

Batch fetching cho phép ORM nạp nhiều association hoặc collection trong một truy vấn theo nhóm thay vì một truy vấn cho từng Entity.

Ví dụ, thay vì:

~~~sql
SELECT * FROM customers WHERE id = 1;
SELECT * FROM customers WHERE id = 2;
SELECT * FROM customers WHERE id = 3;
SELECT * FROM customers WHERE id = 4;
~~~

Hibernate có thể gom các ID:

~~~sql
SELECT * FROM customers
WHERE id IN (1, 2, 3, 4);
~~~

Với batch size là 32, nếu có 100 association cần nạp, số truy vấn có thể giảm từ gần 100 xuống khoảng 4, tùy số ID thực tế, cache và cách ORM nhóm các proxy/collection.

### 6.2. Cấu hình @BatchSize

Hibernate cung cấp annotation:

~~~java
@Entity
@BatchSize(size = 32)
public class Customer {
    // ...
}
~~~

Hoặc đặt trên collection:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 32)
private List<OrderLine> lines = new ArrayList<>();
~~~

Có thể cấu hình default batch fetch size ở cấp SessionFactory. Batch size là tham số cần đo lường, không có một con số đúng cho mọi hệ thống.

### 6.3. Batch fetching phù hợp khi cần giữ LAZY

Batch fetching hữu ích khi:

- Danh sách gốc có nhiều Entity.
- Code có thể cần truy cập association của nhiều phần tử.
- Không muốn join toàn bộ collection vào một kết quả lớn.
- Có thể chấp nhận vài truy vấn theo lô thay vì một truy vấn duy nhất.

Nó đặc biệt hữu ích với association to-one hoặc collection lazy được truy cập trong một luồng xử lý. Tuy vậy, nếu use case chỉ cần một vài cột, DTO projection vẫn có thể tiết kiệm hơn việc tải Entity graph.

### 6.4. Subselect fetching

Hibernate có thể dùng subselect fetching để tải collection của nhiều Entity cha bằng một truy vấn dựa trên truy vấn cha ban đầu, thay vì một truy vấn cho từng cha.

Cơ chế này có thể hữu ích khi cùng một tập Entity cha được tải và collection của nhiều phần tử sẽ được truy cập. Nó phụ thuộc provider, mapping và truy vấn gốc; cần xem SQL và đo hiệu năng trong tình huống thật.

## 7. Dùng DTO Projection khi không cần Aggregate đầy đủ

### 7.1. Đọc dữ liệu không nhất thiết phải dựng Entity

Một màn hình danh sách có thể chỉ cần:

- Mã đơn.
- Trạng thái.
- Tên khách.
- Tổng tiền.
- Thời điểm tạo.

Nếu tải toàn bộ Order, Customer và OrderLine chỉ để hiển thị vài trường, ORM phải dựng object graph không cần thiết.

DTO projection cho phép truy vấn đúng các cột cần thiết:

~~~java
public record OrderSummary(
    Long orderId,
    String customerName,
    OrderStatus status,
    BigDecimal total,
    Instant createdAt
) {
}
~~~

Repository:

~~~java
@Query("""
    select new com.example.orders.OrderSummary(
        o.id,
        c.name,
        o.status,
        o.total,
        o.createdAt
    )
    from Order o
    join o.customer c
    where o.status = :status
    order by o.createdAt desc
    """)
List<OrderSummary> findSummariesByStatus(
    OrderStatus status
);
~~~

Đây là một truy vấn chiếu dữ liệu phục vụ đọc. Nó không cần tải toàn bộ Entity graph và không kích hoạt lazy loading từ DTO nếu DTO chỉ chứa scalar/value fields.

### 7.2. Projection phù hợp với query model

Trong DDD, mô hình ghi và mô hình đọc có thể có nhu cầu khác nhau:

- Command cần Aggregate để kiểm tra invariant và thay đổi trạng thái.
- Query thường chỉ cần dữ liệu đã định dạng cho màn hình hoặc báo cáo.

Không phải mọi truy vấn đều cần gọi repository để tải Aggregate rồi chuyển thành DTO. Có thể dùng projection, query service hoặc read model riêng nếu phù hợp.

### 7.3. Không dùng projection để thay thế Aggregate khi cần hành vi

Nếu use case cần xác nhận, hủy hoặc thay đổi một đơn, phải tải Aggregate có quyền thực hiện hành vi và bảo vệ invariant. Không nên lấy một DTO rồi cập nhật trực tiếp các bảng để né chi phí ORM.

Projection tối ưu cho đọc. Thay đổi nghiệp vụ vẫn cần đi qua mô hình sở hữu trạng thái.

## 8. Phân trang và fetch collection

### 8.1. Vì sao collection fetch join gây khó cho pagination?

Pagination thường áp dụng LIMIT/OFFSET trên kết quả SQL. Khi join collection, một Entity cha có thể xuất hiện nhiều dòng.

Ví dụ một Order có 10 OrderLine sẽ chiếm 10 dòng SQL. Nếu database giới hạn 20 dòng, kết quả có thể chỉ chứa hai Order thay vì 20 Order như người dùng mong đợi.

Một số ORM có thể phải tải toàn bộ kết quả rồi phân trang trong bộ nhớ khi kết hợp collection fetch join. Điều đó gây tốn bộ nhớ và có thể tạo cảnh báo hoặc hành vi hiệu năng xấu.

### 8.2. Trang danh sách: fetch to-one hoặc dùng projection

Với trang danh sách, ưu tiên:

- DTO projection lấy đúng các cột.
- Join fetch các quan hệ to-one cần thiết.
- Batch fetch nếu cần truy cập collection của các Entity trong trang.
- Không join fetch collection lớn trên truy vấn phân trang.

### 8.3. Hai bước: lấy ID trang trước, rồi nạp chi tiết

Một cách phổ biến:

Bước 1: lấy ID của các Order thuộc trang:

~~~java
@Query("""
    select o.id
    from Order o
    where o.status = :status
    order by o.createdAt desc, o.id desc
    """)
Page<Long> findPageOfIds(
    OrderStatus status,
    Pageable pageable
);
~~~

Bước 2: nạp các Order cùng collection cần thiết:

~~~java
@Query("""
    select distinct o
    from Order o
    left join fetch o.lines
    where o.id in :ids
    """)
List<Order> findWithLinesByIdIn(
    Collection<Long> ids
);
~~~

Sau đó sắp xếp kết quả theo thứ tự ID của trang, vì IN không bảo đảm giữ thứ tự đầu vào.

Cách này tạo hai truy vấn có kiểm soát: một truy vấn phân trang ID và một truy vấn nạp dữ liệu cho tập ID đã chọn. Cần xử lý trường hợp trang rỗng và giới hạn kích thước IN phù hợp với database.

### 8.4. Keyset pagination cho tập dữ liệu lớn

Với dữ liệu lớn và phân trang sâu, OFFSET có thể ngày càng tốn kém. Keyset pagination dùng giá trị của bản ghi cuối trang trước làm điểm bắt đầu cho trang tiếp theo.

Ví dụ sắp xếp theo createdAt và id:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE status = ?
  AND (
      created_at < ?
      OR (created_at = ? AND id < ?)
  )
ORDER BY created_at DESC, id DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Cần có thứ tự ổn định và index phù hợp. Keyset pagination thường phù hợp với danh sách cuộn liên tục hoặc batch đọc tuần tự, nhưng không hỗ trợ nhảy đến một số trang tùy ý theo cách OFFSET làm được.

## 9. Chi phí của Aggregate lớn

### 9.1. Aggregate là ranh giới nhất quán, không phải toàn bộ cây đối tượng liên quan

Một sai lầm thường gặp là xem mọi đối tượng có quan hệ với nhau đều phải nằm trong một Aggregate. Điều này khiến Aggregate ngày càng lớn và ORM có thể phải tải nhiều dữ liệu để thực hiện một hành vi đơn giản.

Aggregate nên chứa những thành phần cần được bảo vệ cùng nhau bởi invariant. Những đối tượng chỉ liên quan qua tham chiếu hoặc quy trình có thể thuộc Aggregate khác.

Ví dụ Order có thể sở hữu OrderLine vì tổng tiền, trạng thái và các quy tắc chỉnh sửa dòng hàng cần được bảo vệ trong ranh giới đơn. Nhưng Customer, Product Catalog, Payment và Shipment thường có vòng đời và trách nhiệm độc lập; Order có thể lưu ID hoặc snapshot cần thiết thay vì nhúng toàn bộ object graph.

### 9.2. Aggregate lớn làm tăng chi phí tải

Một Aggregate có hàng nghìn child Entity có thể gây:

- Nhiều dòng SQL và nhiều dữ liệu truyền qua mạng.
- Tăng thời gian hydrate object graph.
- Tăng áp lực bộ nhớ và garbage collection.
- Tăng thời gian giữ persistence context.
- Dễ phát sinh N+1 nếu quan hệ sâu được truy cập.
- Khó phân trang hoặc xử lý từng phần collection.

Ngay cả khi chỉ thay đổi một thuộc tính nhỏ, ORM có thể phải tải nhiều dữ liệu nếu mapping hoặc hành vi truy cập yêu cầu toàn bộ collection.

### 9.3. Aggregate lớn làm tăng chi phí ghi

Một Aggregate lớn có thể:

- Tăng số bản ghi cần insert/update/delete.
- Tăng thời gian transaction.
- Tăng khả năng optimistic lock conflict nếu nhiều thao tác cùng sửa Root.
- Tăng lock contention ở database.
- Làm việc retry tốn kém vì phải tải và tính toán lại nhiều dữ liệu.

Nếu hai use case thay đổi hai phần độc lập của một Aggregate rất lớn nhưng cùng cập nhật version của Root, chúng có thể xung đột dù không sửa cùng child. Đây là tín hiệu cần xem lại ranh giới consistency hoặc cách cập nhật.

### 9.4. Không tách Aggregate chỉ vì số lượng thuộc tính nhiều

Một Aggregate có nhiều field không nhất thiết quá lớn. Điều cần quan tâm là số đối tượng liên quan, invariant, khối lượng dữ liệu phải tải và mức độ tranh chấp cập nhật.

Ngược lại, một Aggregate có ít field nhưng một collection không giới hạn có thể rất tốn kém. Cần đánh giá kích thước dữ liệu và hành vi theo thời gian, không chỉ nhìn số thuộc tính của class.

## 10. Khi nào nên tách một Aggregate lớn?

### 10.1. Kiểm tra invariant trước khi tách

Hãy hỏi:

- Những child nào phải được thay đổi cùng Root để giữ invariant?
- Có hành vi nào cần đọc hoặc cập nhật toàn bộ collection không?
- Một child có vòng đời độc lập không?
- Có thể tham chiếu child bằng ID thay vì object không?
- Nếu cập nhật bất đồng bộ, nghiệp vụ có chấp nhận trạng thái chờ không?

Nếu hai nhóm dữ liệu không cần thay đổi nguyên tử cùng nhau và có quyền sở hữu riêng, chúng có thể là hai Aggregate.

### 10.2. Chuyển quan hệ object thành tham chiếu ID

Thay vì Order giữ tham chiếu trực tiếp đến một Customer object lớn, có thể lưu CustomerId:

~~~java
public class Order {

    private OrderId id;
    private CustomerId customerId;

    // ...
}
~~~

Khi cần hiển thị tên khách, query service lấy thông tin Customer qua projection hoặc truy vấn riêng. Khi xác nhận đơn, Order chỉ dùng dữ liệu snapshot hoặc thông tin cần thiết theo chính sách.

Tham chiếu ID làm rõ Aggregate boundary và tránh tải cả object graph chỉ vì có quan hệ ở mức khái niệm.

### 10.3. Dùng snapshot khi lịch sử cần giữ giá trị tại thời điểm giao dịch

Một OrderLine có thể cần giữ tên sản phẩm, đơn giá và mô tả tại thời điểm đặt hàng. Nếu chỉ tham chiếu ProductId rồi luôn đọc dữ liệu hiện tại, lịch sử đơn có thể thay đổi khi catalog đổi tên hoặc giá.

Snapshot là dữ liệu được sao chép có chủ đích để bảo toàn ý nghĩa lịch sử. Nó không phải lý do để nhúng toàn bộ Product Aggregate vào Order.

### 10.4. Chấp nhận eventual consistency khi phù hợp

Sau khi tách Aggregate, các thay đổi có thể không còn nằm trong cùng transaction. Một quy trình có thể dùng Domain Event, Process Manager hoặc Saga để phối hợp.

Ví dụ Order được xác nhận trước, sau đó phát OrderConfirmed để hệ thống Fulfillment tạo công việc. Nếu Fulfillment từ chối, quy trình cần trạng thái xử lý và hành động bù trừ theo chính sách.

Không nên tách nếu invariant bắt buộc phải được bảo đảm nguyên tử mà chưa có cách thiết kế phù hợp. Ngược lại, không nên giữ một Aggregate khổng lồ chỉ để mọi thay đổi đều nằm trong một transaction.

## 11. Chọn chiến lược nạp theo từng loại use case

| Nhu cầu | Chiến lược thường phù hợp | Điểm cần chú ý |
|---|---|---|
| Chi tiết một Order với một collection vừa phải | JOIN FETCH hoặc EntityGraph | Theo dõi số dòng sau join |
| Danh sách Order có Customer | Join fetch to-one hoặc DTO projection | Tránh tải collection không cần |
| Danh sách Order có nhiều dòng hàng | DTO projection hoặc batch fetch | Không join collection lớn khi phân trang |
| Xử lý batch nhiều Aggregate | Batch size, chunking, projection | Giới hạn persistence context và transaction |
| Báo cáo tổng hợp | SQL/JPQL aggregate hoặc projection | Không hydrate toàn bộ Entity |
| Command thay đổi trạng thái | Tải Aggregate đủ để bảo vệ invariant | Kiểm soát transaction và version |
| Màn hình cần nhiều nguồn dữ liệu | Query service/read model | Không ép một Aggregate sở hữu tất cả dữ liệu |

Đây là các lựa chọn khởi đầu. Cần đo truy vấn và kiểm tra dữ liệu thật trước khi quyết định cuối cùng.

## 12. Phát hiện và chẩn đoán N+1

### 12.1. Bật SQL logging trong môi trường phát triển

Với Hibernate, có thể bật SQL log và bind parameter log trong profile phát triển hoặc test. Ví dụ cấu hình Spring Boot:

~~~properties
spring.jpa.show-sql=false
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên logger có thể khác theo phiên bản Hibernate. Bind parameter log có thể chứa dữ liệu nhạy cảm; không bật tùy tiện trong production hoặc chia sẻ log chưa được làm sạch.

### 12.2. Quan sát số câu SQL theo use case

Khi gọi một endpoint hoặc use case, kiểm tra:

- Có bao nhiêu câu select được thực thi?
- Câu nào lặp lại với ID khác nhau?
- Có truy vấn phát sinh bên trong vòng lặp không?
- Có quan hệ nào được tải nhưng response không dùng?
- Số dòng trả về có lớn bất thường không?

Một chuỗi truy vấn giống nhau chỉ khác tham số ID là dấu hiệu đáng chú ý của N+1.

### 12.3. Dùng Hibernate Statistics hoặc công cụ quan sát

Hibernate Statistics có thể cung cấp số entity load, collection fetch, query execution và cache hit. Các công cụ như datasource proxy hoặc APM cũng giúp quan sát query count và thời gian.

Không chỉ đo số query. Một truy vấn join có thể chạy lâu hơn nhiều truy vấn nhỏ nếu nó tạo quá nhiều dòng hoặc thiếu index.

### 12.4. Kiểm tra execution plan và index

Khi đã xác định câu SQL chậm, xem execution plan của database:

- Có dùng index phù hợp không?
- Join có tạo cardinality lớn không?
- Điều kiện lọc có chọn lọc tốt không?
- Có sort hoặc scan tốn kém không?
- Số dòng ước tính có khác xa số dòng thực tế không?

N+1 là vấn đề ở tầng truy cập dữ liệu, nhưng index và execution plan vẫn quyết định chi phí của từng truy vấn.

### 12.5. Cẩn thận khi assert query count trong test

Integration test có thể kiểm tra query count để phát hiện hồi quy N+1. Tuy nhiên, số query có thể thay đổi do cache, flush, phiên bản ORM hoặc cách setup test.

Nếu assert query count, hãy:

- Dùng database và cấu hình gần production.
- Xóa hoặc kiểm soát persistence context trước khi đo.
- Tắt hoặc kiểm soát cache nếu mục tiêu là đo truy vấn thật.
- Tách truy vấn setup khỏi truy vấn cần kiểm tra.
- Kiểm tra xu hướng tăng theo số phần tử, không chỉ một con số cứng thiếu ngữ cảnh.

Một test có thể chạy với N=1 và không phát hiện N+1. Nên dùng nhiều phần tử và xác nhận số query không tăng tuyến tính theo N đối với fetch plan đã chọn.

## 13. Quy trình tối ưu một use case có N+1

Có thể thực hiện theo các bước:

1. Xác định use case và dữ liệu thực sự cần trả về.
2. Tái hiện với tập dữ liệu đủ lớn để nhìn thấy số query tăng.
3. Bật SQL logging hoặc query metrics để tìm truy vấn lặp.
4. Xác định association bị truy cập muộn.
5. Chọn chiến lược: join fetch, EntityGraph, batch fetching hoặc DTO projection.
6. Kiểm tra phân trang và số dòng kết quả sau join.
7. Đo lại query count, thời gian, dữ liệu truyền và bộ nhớ.
8. Chạy test hành vi để bảo đảm kết quả nghiệp vụ không đổi.
9. Ghi nhận fetch plan tại repository/use case để tránh phụ thuộc vào truy cập ngầm.

Không tối ưu dựa trên suy đoán rằng một câu query luôn nhanh hơn nhiều câu query. Hãy dùng số đo và dữ liệu đại diện.

## 14. Những sai lầm thường gặp

### Đổi mọi quan hệ sang EAGER

Điều này có thể làm tải dữ liệu thừa và vẫn không ngăn provider phát nhiều select. Hãy dùng fetch plan theo use case.

### Join fetch tất cả collection

Join nhiều collection tạo tích số dòng, dữ liệu lặp và có thể gặp giới hạn bag của Hibernate. Hãy chọn collection cần thiết và cân nhắc batch hoặc query riêng.

### Dùng collection fetch join với pagination

Phân trang trên dòng join có thể không tương ứng với số Aggregate mong muốn. Hãy dùng projection, phân trang ID trước rồi fetch dữ liệu ở truy vấn sau, hoặc chiến lược batch.

### Dùng một repository method cho mọi màn hình

Một truy vấn tải chi tiết có thể không phù hợp với danh sách. Tách query theo nhu cầu và tên gọi rõ ràng.

### Tải Aggregate chỉ để hiển thị vài cột

DTO projection thường tiết kiệm hơn khi không cần hành vi hoặc invariant của Aggregate.

### Tách Aggregate chỉ vì muốn giảm số query

Ranh giới Aggregate phải dựa trên invariant và quyền sở hữu nghiệp vụ. Tối ưu query không được làm mất khả năng bảo vệ quy tắc.

### Giữ Aggregate lớn để tránh eventual consistency

Aggregate quá lớn có thể gây lock contention và tải dữ liệu nặng. Nếu các phần có thể thay đổi độc lập, hãy xem xét tách và điều phối theo chính sách.

### Truy cập lazy association ngoài transaction

Lazy loading có thể thất bại khi persistence context đã đóng. Không nên dựa vào Open Session in View để che giấu fetch plan thiếu rõ ràng. Hãy tải dữ liệu cần thiết trong use case rồi chuyển thành DTO.

### Chỉ đo số query

Một câu query khổng lồ vẫn có thể rất chậm. Theo dõi số dòng, thời gian, execution plan, bộ nhớ và dữ liệu truyền.

## 15. Bài tập thực hành: tối ưu màn hình đơn hàng

Một hệ thống bán hàng có:

- Order tham chiếu Customer.
- Order có collection OrderLine.
- Mỗi OrderLine tham chiếu Product.
- Order có collection Payment.
- Màn hình danh sách hiển thị mã đơn, tên khách, trạng thái, tổng tiền và số dòng hàng.
- Màn hình chi tiết hiển thị từng dòng hàng, tên sản phẩm và lịch sử thanh toán.

Hãy thực hiện:

1. Viết query hiện tại và quan sát SQL khi tải danh sách 50 đơn.
2. Xác định quan hệ nào gây N+1.
3. Đề xuất DTO projection cho màn hình danh sách.
4. Đề xuất fetch plan cho màn hình chi tiết một Order.
5. Giải thích vì sao không nên join fetch đồng thời lines và payments cho danh sách.
6. Thiết kế phân trang ID trước rồi nạp collection nếu cần.
7. Đo số query, số dòng và thời gian trước/sau.
8. Đánh giá Order Aggregate có đang chứa những đối tượng cần vòng đời độc lập hay không.

### 15.1. Gợi ý cho màn hình danh sách

Một projection có thể gồm:

~~~java
public record OrderListItem(
    Long id,
    String customerName,
    OrderStatus status,
    BigDecimal total,
    Instant createdAt,
    Long lineCount
) {
}
~~~

Truy vấn có thể dùng join to-one và phép đếm:

~~~java
@Query(
    value = """
    select new com.example.orders.OrderListItem(
        o.id,
        c.name,
        o.status,
        o.total,
        o.createdAt,
        count(line)
    )
    from Order o
    join o.customer c
    left join o.lines line
    where o.status = :status
    group by o.id, c.name, o.status, o.total, o.createdAt
    order by o.createdAt desc
    """,
    countQuery = "select count(o) from Order o where o.status = :status"
)
Page<OrderListItem> findOrderList(
    OrderStatus status,
    Pageable pageable
);
~~~

Tùy database và JPA provider, truy vấn phân trang có thể cần count query riêng hoặc tối ưu lại. Cần kiểm tra SQL thực tế và bảo đảm phép đếm không bị nhân bản nếu truy vấn thêm collection khác.

### 15.2. Gợi ý cho màn hình chi tiết

Với một Order ID, có thể tải Customer và Lines trong một fetch plan, rồi tải Payments bằng truy vấn thứ hai nếu cần. Cách này tránh tích số dòng giữa hai collection.

Nếu Product chỉ cần tên hiển thị, có thể dùng projection riêng cho các Product ID thuộc OrderLine. Nếu cần snapshot tên sản phẩm tại thời điểm đặt hàng, hãy lưu snapshot trong OrderLine theo chính sách lịch sử thay vì phụ thuộc tên hiện tại của Catalog.

## 16. Checklist thiết kế fetch plan và Aggregate

Trước khi hoàn thành một use case persistence, hãy kiểm tra:

- Đã xác định chính xác dữ liệu use case cần.
- Đã hiểu mapping LAZY/EAGER của các association liên quan.
- Không có truy vấn N+1 khi xử lý tập dữ liệu đại diện.
- Fetch join chỉ dùng cho association phù hợp và có cardinality kiểm soát được.
- Không join nhiều collection lớn một cách thiếu cân nhắc.
- EntityGraph được xác minh bằng SQL thực tế.
- Batch fetching có batch size được đo lường.
- DTO projection được dùng cho query chỉ cần dữ liệu đọc.
- Pagination không bị sai do collection join.
- Persistence context không bị giữ quá lâu trong batch.
- Aggregate boundary dựa trên invariant và quyền sở hữu, không chỉ dựa trên quan hệ ORM.
- Aggregate không tải collection không giới hạn cho mọi hành vi.
- Các đối tượng có vòng đời độc lập được tham chiếu bằng ID khi phù hợp.
- Snapshot được dùng khi cần giữ dữ liệu lịch sử.
- Query count, row count, latency và execution plan đã được xem xét.
- Có test tích hợp hoặc kiểm tra hiệu năng phù hợp để phát hiện hồi quy.

## Kết luận

N+1 xuất hiện khi ứng dụng tải một tập hợp rồi vô tình phát sinh truy vấn bổ sung cho từng phần tử khi truy cập association. Fetch plan giúp xác định dữ liệu nào cần được nạp cho từng use case. JOIN FETCH, EntityGraph, batch fetching và DTO projection là những lựa chọn khác nhau, mỗi cách có chi phí và giới hạn riêng.

Aggregate trong DDD là ranh giới bảo vệ invariant, không phải lời yêu cầu ORM tải toàn bộ cây đối tượng liên quan. Aggregate quá lớn làm tăng chi phí đọc, ghi, bộ nhớ và cạnh tranh cập nhật. Khi tối ưu, hãy giữ quyền sở hữu và quy tắc nghiệp vụ rõ ràng, chọn chiến lược truy vấn theo nhu cầu thực tế và đo cả số truy vấn lẫn lượng dữ liệu được xử lý.

