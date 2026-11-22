# Truy vấn con, EXISTS và điều kiện tương quan

JPQL cho phép đặt một truy vấn con (subquery) bên trong điều kiện của truy vấn chính. Truy vấn con thường được dùng để kiểm tra sự tồn tại của dữ liệu liên quan, so sánh với một giá trị tổng hợp hoặc lọc Entity theo tập ID được tạo từ một truy vấn khác.

Hai cấu trúc quan trọng là EXISTS và NOT EXISTS. Chúng kiểm tra xem truy vấn con có trả về ít nhất một dòng hay không. Khi truy vấn con tham chiếu alias của truy vấn bên ngoài, đó là **truy vấn con tương quan (correlated subquery)**. Cách viết này rất hữu ích khi cần hỏi: khách hàng nào đã có đơn hàng, đơn hàng nào có ít nhất một dòng hàng đạt điều kiện, hoặc sản phẩm nào chưa từng được đặt.

## 1. Truy vấn con trong JPQL là gì?

Một subquery là câu SELECT nằm bên trong một biểu thức của truy vấn JPQL khác. Truy vấn bên ngoài quyết định Entity hoặc giá trị cần trả về; subquery cung cấp dữ liệu để kiểm tra hoặc so sánh.

Ví dụ về mặt ý tưởng:

~~~sql
SELECT c
FROM Customer c
WHERE EXISTS (
    SELECT o.id
    FROM PurchaseOrder o
    WHERE o.customer = c
)
~~~

Truy vấn bên ngoài chọn Customer. Truy vấn con kiểm tra xem có PurchaseOrder nào thuộc về Customer hiện tại hay không.

Trong JPQL chuẩn, subquery được phép trong mệnh đề WHERE và HAVING. JPQL chuẩn không hỗ trợ đặt subquery trong FROM như một derived table theo cách thường gặp ở SQL. Một số HQL hoặc extension của provider có thể hỗ trợ cú pháp rộng hơn, nhưng nếu muốn truy vấn portable giữa các JPA provider, hãy tuân theo phạm vi của JPQL chuẩn.

Subquery có thể trả về:

- Một giá trị đơn (scalar), ví dụ kết quả COUNT hoặc MAX.
- Một tập giá trị, ví dụ danh sách ID dùng với IN.
- Một tập dòng dùng với EXISTS hoặc NOT EXISTS, nơi nội dung SELECT không quan trọng bằng việc có dòng phù hợp hay không.

## 2. Mô hình dữ liệu dùng trong ví dụ

Giả sử hệ thống bán hàng có Customer, PurchaseOrder, OrderItem và Product:

~~~text
Customer 1 -------- N PurchaseOrder
PurchaseOrder 1 --- N OrderItem
Product 1 --------- N OrderItem
~~~

Một Customer có thể có nhiều đơn hàng. Mỗi PurchaseOrder có nhiều OrderItem. Mỗi OrderItem tham chiếu một Product.

Các thuộc tính liên quan trong Entity:

~~~java
@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    private String name;
}
~~~

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    private BigDecimal totalAmount;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
~~~

~~~java
@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "product_id")
    private Product product;

    private Integer quantity;
}
~~~

Các đoạn mã Entity là phần minh họa mapping; chúng cần được đặt trong dự án có đầy đủ import, constructor, getter và cấu hình JPA phù hợp. Trong JPQL, tên được dùng là tên Entity và thuộc tính Java, không phải tên bảng/cột SQL. Ví dụ PurchaseOrder là tên Entity, customer là thuộc tính quan hệ, còn purchase_orders và customer_id là tên vật lý trong database.

## 3. EXISTS: kiểm tra có ít nhất một dòng phù hợp

EXISTS trả về true khi truy vấn con trả về ít nhất một dòng, và false khi không có dòng nào.

Cú pháp khái quát:

~~~sql
SELECT ...
FROM Entity e
WHERE EXISTS (
    SELECT ...
    FROM OtherEntity x
    WHERE điều_kiện
)
~~~

Ví dụ: tìm khách hàng đã từng có ít nhất một đơn hàng.

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """)
    List<Customer> findCustomersWithOrders();
}
~~~

Đọc truy vấn:

1. JPQL duyệt các Customer theo alias c.
2. Với mỗi Customer trong ngữ nghĩa của truy vấn, subquery kiểm tra PurchaseOrder có customer bằng c hay không.
3. Nếu tồn tại ít nhất một đơn hàng, EXISTS là true và Customer được chọn.
4. Nếu không có đơn hàng, Customer không nằm trong kết quả.

Trong subquery, SELECT o.id chỉ nhằm tạo một biểu thức hợp lệ. EXISTS không sử dụng giá trị ID để trả về cho truy vấn bên ngoài; nó chỉ quan tâm có dòng nào thỏa điều kiện hay không. Vì vậy, việc chọn một thuộc tính đơn giản như ID thường giúp ý định rõ ràng.

## 4. NOT EXISTS: tìm đối tượng không có dữ liệu liên quan

NOT EXISTS là phủ định của EXISTS. Nó đúng khi subquery không trả về dòng nào.

Ví dụ: tìm khách hàng chưa từng đặt đơn hàng.

~~~java
@Query("""
    select c
    from Customer c
    where not exists (
        select o.id
        from PurchaseOrder o
        where o.customer = c
    )
    """)
List<Customer> findCustomersWithoutOrders();
~~~

Đây là một dạng anti-join: lấy các Customer không có bản ghi PurchaseOrder liên quan.

Một số use case thường gặp:

- Người dùng chưa có giao dịch.
- Sản phẩm chưa từng được bán.
- Bài viết chưa có bình luận.
- Tài khoản chưa có lần đăng nhập.
- Đơn hàng chưa có bản ghi thanh toán.

NOT EXISTS thường diễn đạt trực tiếp ý nghĩa “không có bản ghi liên quan” và tránh một số vấn đề về NULL của NOT IN.

## 5. Điều kiện tương quan là gì?

Một subquery tương quan tham chiếu đến alias được khai báo ở truy vấn bên ngoài. Ví dụ:

~~~sql
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
~~~

Alias c được khai báo trong truy vấn ngoài nhưng được sử dụng bên trong subquery. Điều kiện o.customer = c kết nối subquery với Customer hiện tại.

Nếu không có tham chiếu đến alias bên ngoài, subquery là không tương quan (uncorrelated subquery). Ví dụ:

~~~sql
select o
from PurchaseOrder o
where o.totalAmount = (
    select max(o2.totalAmount)
    from PurchaseOrder o2
)
~~~

Subquery tìm giá trị tổng lớn nhất trong toàn bộ PurchaseOrder, không phụ thuộc vào alias o của truy vấn ngoài.

Có thể hiểu sự khác biệt như sau:

| Loại | Đặc điểm | Ví dụ |
|---|---|---|
| Không tương quan | Tính một tập hoặc giá trị độc lập với từng dòng ngoài | MAX(totalAmount) toàn bảng |
| Tương quan | Dùng alias ngoài để giới hạn dữ liệu theo dòng đang xét | PurchaseOrder thuộc Customer c |

Về mặt logic, subquery tương quan được diễn giải theo từng dòng của truy vấn ngoài. Tuy nhiên, không nên kết luận database chắc chắn chạy một truy vấn con riêng cho từng dòng. Optimizer có thể biến đổi nó thành semi-join, anti-join hoặc kế hoạch thực thi khác tương đương.

## 6. EXISTS với quan hệ nhiều tầng

Có thể nối nhiều quan hệ trong subquery. Ví dụ tìm các đơn hàng có ít nhất một OrderItem với số lượng từ một ngưỡng trở lên:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Query("""
        select o
        from PurchaseOrder o
        where exists (
            select i.id
            from OrderItem i
            where i.order = o
              and i.quantity >= :minimumQuantity
        )
        """)
    List<PurchaseOrder> findOrdersWithLargeItemQuantity(
            @Param("minimumQuantity") Integer minimumQuantity
    );
}
~~~

Điều kiện i.order = o là phần tương quan: chỉ xét OrderItem thuộc đơn hàng đang được kiểm tra. Điều kiện quantity giới hạn dòng hàng cần tồn tại.

Có thể nối đến Product:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where exists (
        select i.id
        from OrderItem i
        where i.order = o
          and i.product.name = :productName
    )
    """)
List<PurchaseOrder> findOrdersContainingProduct(
        @Param("productName") String productName
);
~~~

JPQL cho phép điều hướng thuộc tính quan hệ bằng dấu chấm. Provider sẽ tạo join cần thiết để đánh giá điều kiện product.name. Nếu truy vấn có nhiều tầng quan hệ hoặc điều kiện phức tạp, hãy kiểm tra SQL sinh ra và execution plan.

## 7. Subquery tương quan với COUNT

Subquery có thể trả về một giá trị tổng hợp. Ví dụ, tìm khách hàng có ít nhất một số lượng đơn hàng nhất định:

~~~java
@Query("""
    select c
    from Customer c
    where (
        select count(o.id)
        from PurchaseOrder o
        where o.customer = c
    ) >= :minimumOrders
    """)
List<Customer> findCustomersWithAtLeastOrders(
        @Param("minimumOrders") Long minimumOrders
);
~~~

Subquery COUNT được tương quan với Customer c thông qua o.customer = c. Với mỗi Customer, truy vấn con tính số đơn hàng của khách đó rồi so sánh với tham số.

COUNT trả về Long trong JPQL. Vì vậy, tham số minimumOrders nên dùng Long để thể hiện đúng kiểu kết quả.

Có thể viết điều kiện tương tự bằng EXISTS nếu chỉ cần biết có ít nhất một đơn hàng:

~~~java
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
~~~

Nếu cần đếm số lượng và so sánh với ngưỡng lớn hơn một, COUNT phù hợp hơn. Nếu chỉ cần kiểm tra có hay không, EXISTS thường diễn đạt đúng mục tiêu và tránh phải yêu cầu kết quả đếm.

Lưu ý: COUNT trả về 0 khi không có dòng phù hợp. Các hàm tổng hợp như MAX, MIN, AVG và SUM có thể trả về NULL khi không có giá trị đầu vào; điều kiện so sánh với NULL sẽ không trở thành true.

## 8. Subquery với IN

IN kiểm tra một giá trị có nằm trong tập giá trị do subquery trả về hay không.

Ví dụ: tìm Product đã xuất hiện trong ít nhất một OrderItem có số lượng từ 10 trở lên.

~~~java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.id in (
            select i.product.id
            from OrderItem i
            where i.quantity >= :minimumQuantity
        )
        """)
    List<Product> findProductsInLargeOrders(
            @Param("minimumQuantity") Integer minimumQuantity
    );
}
~~~

Subquery trả về tập ID sản phẩm. Truy vấn ngoài chọn Product có ID nằm trong tập đó.

IN phù hợp khi cần so sánh một thuộc tính với tập kết quả của subquery. Tuy nhiên, nếu ý nghĩa nghiệp vụ là “có ít nhất một bản ghi liên quan”, EXISTS thường thể hiện rõ hơn quan hệ tương quan.

## 9. So sánh với giá trị tổng hợp bằng subquery

Subquery không nhất thiết phải tương quan. Ví dụ tìm đơn hàng có tổng tiền bằng giá trị lớn nhất trong hệ thống:

~~~java
@Query("""
    select o
    from PurchaseOrder o
    where o.totalAmount = (
        select max(o2.totalAmount)
        from PurchaseOrder o2
    )
    """)
List<PurchaseOrder> findOrdersWithMaximumAmount();
~~~

Subquery MAX trả về một giá trị đơn. Truy vấn ngoài chọn mọi đơn hàng có totalAmount bằng giá trị đó. Dùng List vì có thể có nhiều đơn hàng cùng tổng tiền lớn nhất.

Có thể dùng các toán tử so sánh với subquery scalar:

- = để bằng giá trị subquery.
- > hoặc >= để lớn hơn hoặc lớn hơn/bằng.
- < hoặc <= để nhỏ hơn hoặc nhỏ hơn/bằng.
- <> để khác giá trị.

Kết quả subquery dùng trong ngữ cảnh scalar phải phù hợp với một giá trị. Nếu subquery trả nhiều dòng trong khi biểu thức yêu cầu một giá trị đơn, database/provider sẽ báo lỗi truy vấn.

## 10. EXISTS, IN và JOIN khác nhau thế nào?

Ba cách có thể diễn đạt các yêu cầu gần nhau nhưng ngữ nghĩa và hình dạng kết quả khác nhau.

| Cấu trúc | Mục đích | Đặc điểm |
|---|---|---|
| EXISTS | Kiểm tra có bản ghi liên quan | Không cần trả dữ liệu của phía liên quan |
| IN | Kiểm tra giá trị thuộc tập kết quả | Phù hợp với tập ID/giá trị từ subquery |
| JOIN | Kết hợp dữ liệu của các Entity | Có thể trả thuộc tính từ cả hai phía; có thể tạo dòng lặp |

Ví dụ tìm Customer có đơn hàng bằng JOIN:

~~~sql
select c
from Customer c
join c.orders o
~~~

Nếu một Customer có nhiều đơn hàng, phép join có thể tạo nhiều dòng cho cùng Customer. Khi chỉ cần Customer duy nhất có ít nhất một đơn hàng, có thể cần DISTINCT:

~~~sql
select distinct c
from Customer c
join c.orders o
~~~

Trong khi đó:

~~~sql
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
~~~

EXISTS diễn đạt trực tiếp điều kiện tồn tại và không làm nhân bản dòng Customer ở kết quả ngoài do có nhiều đơn hàng phù hợp.

Chọn JOIN khi cần đọc dữ liệu liên quan hoặc kết hợp nhiều thuộc tính. Chọn EXISTS khi chỉ cần kiểm tra sự tồn tại. Không có quy tắc rằng EXISTS luôn nhanh hơn JOIN; database optimizer và index quyết định kế hoạch thực thi cuối cùng.

## 11. Vì sao NOT EXISTS thường an toàn hơn NOT IN?

NOT IN có thể cho kết quả bất ngờ nếu tập subquery chứa NULL. Theo logic ba giá trị của SQL, phép so sánh với NULL tạo ra UNKNOWN; khi đó điều kiện NOT IN có thể không trả true như người viết mong muốn.

Ví dụ SQL minh họa:

~~~sql
SELECT c.*
FROM customers c
WHERE c.id NOT IN (
    SELECT o.customer_id
    FROM purchase_orders o
);
~~~

Nếu customer_id trong tập con có NULL, kết quả của NOT IN có thể bị ảnh hưởng.

Với NOT EXISTS:

~~~sql
SELECT c.*
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM purchase_orders o
    WHERE o.customer_id = c.id
);
~~~

Điều kiện được đánh giá theo từng Customer và kiểm tra có dòng nào khớp hay không. NULL ở các dòng không khớp không làm toàn bộ phép kiểm tra trở thành UNKNOWN theo cách của NOT IN.

Trong JPQL, khi mục tiêu là tìm Entity không có bản ghi liên quan, NOT EXISTS thường là lựa chọn dễ hiểu và an toàn hơn. Nếu vẫn dùng NOT IN, hãy bảo đảm subquery không thể trả NULL hoặc xử lý NULL tường minh.

## 12. Đặt subquery trong @Query của Spring Data JPA

Subquery thường được viết trực tiếp trong @Query trên Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select c
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
              and o.status = :status
        )
        """)
    List<Customer> findCustomersWithOrderStatus(
            @Param("status") OrderStatus status
    );

    @Query("""
        select c
        from Customer c
        where not exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """)
    List<Customer> findCustomersWithoutOrders();
}
~~~

Spring Data bind tham số qua @Param. Dùng tham số thay cho nối chuỗi đầu vào để tránh lỗi cú pháp và rủi ro injection.

Với JPQL, tên Entity và thuộc tính Java phải chính xác. Nếu Entity có quan hệ customer, viết o.customer; nếu có thuộc tính customerId riêng thì mới viết o.customerId. Không dùng tên bảng hoặc cột SQL trong JPQL trừ khi viết native query.

## 13. Phân trang kết quả có subquery

Subquery có thể kết hợp với Pageable:

~~~java
@Query(
    value = """
        select c
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """,
    countQuery = """
        select count(c.id)
        from Customer c
        where exists (
            select o.id
            from PurchaseOrder o
            where o.customer = c
        )
        """
)
Page<Customer> findCustomersWithOrders(Pageable pageable);
~~~

countQuery đếm số Customer thỏa điều kiện để Spring Data tính tổng số trang. Điều kiện trong countQuery phải tương ứng với truy vấn dữ liệu. Với truy vấn phức tạp, nên khai báo countQuery tường minh và kiểm thử cả nội dung trang lẫn tổng số phần tử.

Subquery trong countQuery vẫn là JPQL, nên tuân thủ cùng quy tắc về Entity, thuộc tính và vị trí subquery.

## 14. Hiệu năng và index cho correlated subquery

Correlated subquery thường tham chiếu khóa ngoại. Với mô hình ví dụ, các cột quan trọng gồm:

- purchase_orders.customer_id để tìm đơn hàng theo Customer.
- order_items.order_id để tìm dòng hàng theo PurchaseOrder.
- order_items.product_id để tìm dòng hàng theo Product.
- Các cột lọc như status hoặc quantity tùy điều kiện và workload.

Index trên khóa ngoại có thể giúp database tìm bản ghi liên quan nhanh hơn. Tuy nhiên, việc chọn index cần dựa vào truy vấn thực tế, số lượng dữ liệu, độ chọn lọc và chi phí ghi.

Ví dụ index cơ bản:

~~~sql
CREATE INDEX idx_purchase_orders_customer
ON purchase_orders (customer_id);

CREATE INDEX idx_order_items_order
ON order_items (order_id);
~~~

Nếu truy vấn thường lọc theo customer_id và status cùng lúc, có thể xem xét composite index theo thứ tự phù hợp với workload:

~~~sql
CREATE INDEX idx_purchase_orders_customer_status
ON purchase_orders (customer_id, status);
~~~

Không nên tạo mọi index theo từng cột một cách máy móc. Index chiếm dung lượng và làm tăng chi phí INSERT/UPDATE/DELETE. Hãy dùng EXPLAIN hoặc EXPLAIN ANALYZE theo database để xem optimizer chọn index, semi-join, anti-join hay scan.

Một correlated subquery trong JPQL thường được gửi như một câu SQL duy nhất. Nó không đồng nghĩa với N+1 truy vấn ở tầng ứng dụng. N+1 thường xuất hiện khi code tải danh sách Entity rồi truy cập từng quan hệ lazy gây thêm truy vấn riêng. Subquery được database xử lý trong kế hoạch của câu SQL đó, dù kế hoạch nội bộ có thể có nhiều bước.

## 15. Giới hạn và lưu ý của JPQL subquery

- JPQL chuẩn cho phép subquery trong WHERE và HAVING; không dùng FROM (subquery) theo cú pháp SQL thông thường.
- Subquery scalar phải trả về giá trị phù hợp với biểu thức so sánh.
- EXISTS chỉ kiểm tra sự tồn tại; danh sách SELECT trong subquery không được đưa ra kết quả ngoài.
- Subquery tương quan phải tham chiếu alias hợp lệ của truy vấn ngoài.
- Không dùng tên bảng/cột SQL thay cho tên Entity/thuộc tính Java trong JPQL.
- Cần chú ý NULL khi dùng NOT IN.
- Aggregate như MAX, MIN, AVG và SUM có thể trả NULL khi không có dữ liệu; COUNT trả 0.
- Không giả định EXISTS luôn nhanh hơn JOIN; hãy đo trên database thực tế.
- Nếu cần truy vấn phức tạp vượt khả năng JPQL chuẩn, cân nhắc Criteria API, native SQL hoặc query chuyên biệt, đồng thời ghi nhận mức phụ thuộc database.

## 16. Kiểm thử truy vấn con

Với repository dùng subquery, nên kiểm tra cả trường hợp có và không có bản ghi liên quan.

Ví dụ test cho EXISTS và NOT EXISTS:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private PurchaseOrderRepository orderRepository;

    @Test
    void findsCustomerThatHasAnOrder() {
        Customer customer =
                customerRepository.save(new Customer("An"));

        orderRepository.save(new PurchaseOrder(customer));

        List<Customer> result =
                customerRepository.findCustomersWithOrders();

        assertTrue(result.stream()
                .anyMatch(c -> c.getId().equals(customer.getId())));
    }

    @Test
    void findsCustomerWithoutOrders() {
        Customer customer =
                customerRepository.save(new Customer("Binh"));

        List<Customer> result =
                customerRepository.findCustomersWithoutOrders();

        assertTrue(result.stream()
                .anyMatch(c -> c.getId().equals(customer.getId())));
    }
}
~~~

Đây là cấu trúc minh họa; constructor và mapping của PurchaseOrder cần phù hợp với Entity thực tế. Trong test, có thể gọi flush nếu cần xác nhận SQL và ràng buộc đã được thực thi trước khi truy vấn.

Nên bổ sung các trường hợp:

1. Một Customer có nhiều đơn hàng nhưng chỉ xuất hiện một lần trong kết quả EXISTS.
2. Customer không có đơn hàng xuất hiện trong NOT EXISTS.
3. Đơn hàng có nhiều OrderItem, chỉ cần một item đạt điều kiện thì EXISTS đúng.
4. Không có dòng hàng phù hợp thì EXISTS sai.
5. Tham số ngưỡng bằng 0, bằng giá trị biên và lớn hơn mọi dữ liệu.
6. Dữ liệu có NULL ở cột tham gia subquery, đặc biệt nếu dùng NOT IN.
7. Phân trang trả đúng tổng số kết quả và không lặp Entity.

Nếu production dùng PostgreSQL hoặc MySQL, integration test nên chạy trên cùng database engine hoặc phiên bản tương thích. H2 có thể khác về SQL dialect, optimizer, collation và cách xử lý NULL ở các trường hợp đặc thù.

## 17. Quy trình chọn cấu trúc truy vấn

Khi viết một truy vấn có điều kiện dựa trên dữ liệu liên quan, hãy xác định trước câu hỏi nghiệp vụ:

- Cần lấy dữ liệu của cả hai Entity? Dùng JOIN.
- Chỉ cần biết có ít nhất một bản ghi liên quan? Dùng EXISTS.
- Cần biết hoàn toàn không có bản ghi liên quan? Dùng NOT EXISTS.
- Cần kiểm tra một giá trị thuộc tập kết quả? Dùng IN.
- Cần so sánh với một giá trị tổng hợp? Dùng subquery scalar như COUNT, MAX hoặc MIN.
- Cần đếm số bản ghi liên quan theo từng Entity ngoài? Dùng correlated COUNT subquery hoặc GROUP BY/HAVING nếu phù hợp.

Sau đó kiểm tra alias, kiểu dữ liệu, NULL semantics, số lượng kết quả, SQL sinh ra và execution plan. Chỉ tối ưu bằng index hoặc đổi cấu trúc truy vấn sau khi đã xác định nút thắt bằng dữ liệu thực tế.

## 18. Kết luận

Subquery trong JPQL giúp lọc Entity theo một giá trị hoặc tập kết quả khác. EXISTS và NOT EXISTS phù hợp để kiểm tra có hoặc không có dữ liệu liên quan; correlated subquery tham chiếu alias của truy vấn ngoài để ràng buộc điều kiện theo từng Entity đang xét. IN phù hợp với tập giá trị, còn subquery tổng hợp hỗ trợ so sánh COUNT, MAX hoặc MIN. Hãy chọn JOIN khi cần dữ liệu từ nhiều Entity, dùng NOT EXISTS để tránh vấn đề NULL của NOT IN, và kiểm tra SQL cùng execution plan trên database mục tiêu để bảo đảm truy vấn đúng và hiệu quả.
