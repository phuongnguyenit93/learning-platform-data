# DISTINCT, giá trị null và kết quả trùng do join trong JPQL

JPQL truy vấn entity và thuộc tính Java thông qua mô hình persistence. Khi một entity được JOIN với collection, một hàng ở phía entity gốc có thể khớp với nhiều hàng liên quan. Vì vậy, cùng một entity gốc có thể xuất hiện nhiều lần trong kết quả truy vấn. JPQL có từ khóa **DISTINCT** để loại bỏ kết quả trùng; đồng thời, JPQL tuân theo logic ba giá trị của SQL đối với **NULL**, nên phép so sánh với NULL không hoạt động như phép so sánh thông thường trong Java.

Bài học này giải thích vì sao JOIN tạo kết quả trùng, cách dùng DISTINCT cho entity và giá trị scalar, cách đếm entity duy nhất, cách xử lý NULL, sự khác nhau giữa điều kiện ON và WHERE của LEFT JOIN, và các lưu ý khi kết hợp DISTINCT với phân trang hoặc fetch join.

## 1. JPQL làm việc với entity và quan hệ

JPQL sử dụng tên entity và tên thuộc tính Java, không dùng trực tiếp tên bảng và tên cột SQL.

Ví dụ có hai entity Customer và PurchaseOrder:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String city;

    private String phone;

    @OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Customer(String name, String city, String phone) {
        this.name = name;
        this.city = city;
        this.phone = phone;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCity() {
        return city;
    }

    public String getPhone() {
        return phone;
    }
}
~~~

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(nullable = false)
    private String status;

    private BigDecimal total;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer, String status, BigDecimal total) {
        this.customer = customer;
        this.status = status;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public Customer getCustomer() {
        return customer;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Một Customer có thể có nhiều PurchaseOrder. Quan hệ được ánh xạ thành:

- Customer.orders là phía inverse với @OneToMany(mappedBy = "customer").
- PurchaseOrder.customer là owning side với @ManyToOne và @JoinColumn.
- Mỗi PurchaseOrder thuộc về một Customer; một Customer có thể có không, một hoặc nhiều đơn hàng.

Các ví dụ JPQL bên dưới dùng tên entity Customer, PurchaseOrder và các property id, city, status, total, orders.

## 2. Vì sao JOIN có thể tạo kết quả trùng?

Giả sử dữ liệu có:

| Customer | PurchaseOrder |
|---|---|
| An | Order 101, PAID |
| An | Order 102, PAID |
| An | Order 103, CANCELLED |
| Bình | Order 104, PAID |
| Chi | Không có đơn hàng |

Truy vấn:

~~~jpql
select c
from Customer c
join c.orders o
where o.status = 'PAID'
~~~

JOIN tạo một kết quả cho mỗi cặp Customer–PurchaseOrder khớp điều kiện. Customer An có hai đơn PAID nên hàng Customer An khớp hai lần. Kết quả logic có thể chứa:

~~~text
An
An
Bình
~~~

Điều này không có nghĩa database lưu hai Customer An. Một Customer được lặp trong kết quả vì có hai hàng PurchaseOrder thỏa điều kiện JOIN.

Có thể hình dung:

~~~text
Customer An
    |--- Order 101 (PAID)  ---> một hàng kết quả
    |--- Order 102 (PAID)  ---> một hàng kết quả

Customer Bình
    |--- Order 104 (PAID) ---> một hàng kết quả
~~~

JOIN làm tăng số hàng trung gian theo số quan hệ khớp. Đây là hành vi bình thường của phép nối quan hệ.

## 3. Dùng SELECT DISTINCT để lấy entity duy nhất

Nếu mục tiêu là lấy mỗi Customer một lần, hãy viết:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = :status
~~~

Repository:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select distinct c
        from Customer c
        join c.orders o
        where o.status = :status
        """)
    List<Customer> findDistinctByOrderStatus(
        @Param("status") String status
    );
}
~~~

DISTINCT yêu cầu kết quả truy vấn không chứa các giá trị entity trùng lặp. Với truy vấn trên, Customer An chỉ xuất hiện một lần dù có nhiều đơn PAID.

Nếu không cần trả entity mà chỉ cần tên khách hàng, có thể truy vấn scalar:

~~~jpql
select distinct c.name
from Customer c
join c.orders o
where o.status = :status
~~~

DISTINCT lúc này áp dụng cho giá trị được chọn là c.name. Nếu hai Customer khác nhau cùng tên An, kết quả scalar chỉ có một giá trị An. Điều đó khác với DISTINCT trên entity, vì hai entity có ID khác nhau vẫn là hai entity riêng biệt dù cùng tên.

Hãy xác định rõ bạn muốn loại trùng entity hay loại trùng giá trị được chiếu ra kết quả.

## 4. DISTINCT trên nhiều cột hoặc nhiều biểu thức

Nếu truy vấn chọn nhiều biểu thức:

~~~jpql
select distinct c.city, o.status
from Customer c
join c.orders o
~~~

DISTINCT áp dụng cho tổ hợp giá trị được chọn. Hai hàng chỉ được xem là trùng nếu toàn bộ các giá trị trong kết quả tương ứng trùng nhau.

Ví dụ:

| city | status |
|---|---|
| Hà Nội | PAID |
| Hà Nội | CANCELLED |
| TP HCM | PAID |

Hai hàng cùng city nhưng khác status vẫn là hai kết quả khác nhau.

Nếu dùng constructor expression hoặc projection, hãy xác định tổ hợp trường nào cần duy nhất. DISTINCT không có nghĩa là chỉ một trường bất kỳ trong projection phải duy nhất.

## 5. COUNT và COUNT(DISTINCT ...)

Khi cần đếm Customer có đơn hàng PAID, không nên đếm trực tiếp các hàng JOIN nếu mục tiêu là số khách hàng duy nhất.

Truy vấn:

~~~jpql
select count(c)
from Customer c
join c.orders o
where o.status = :status
~~~

sẽ đếm số kết quả sau JOIN. Nếu An có hai đơn PAID, An được đếm hai lần.

Dùng:

~~~jpql
select count(distinct c.id)
from Customer c
join c.orders o
where o.status = :status
~~~

Repository:

~~~java
@Query("""
    select count(distinct c.id)
    from Customer c
    join c.orders o
    where o.status = :status
    """)
long countCustomersWithOrderStatus(
    @Param("status") String status
);
~~~

COUNT(DISTINCT c.id) đếm số khóa Customer khác nhau. Vì ID là non-null primary key, đây là cách rõ ràng để đếm entity duy nhất sau JOIN.

Các dạng COUNT thường gặp:

| JPQL | Ý nghĩa |
|---|---|
| count(c) | Đếm các giá trị entity không null trong kết quả |
| count(o.id) | Đếm các order có id không null |
| count(distinct c.id) | Đếm số Customer duy nhất |
| count(c.phone) | Đếm các phone khác null |
| count(distinct c.city) | Đếm các giá trị city khác null và khác nhau |

COUNT(expression) bỏ qua giá trị NULL. COUNT(DISTINCT expression) cũng không đếm NULL. Nếu cần đếm số hàng, kể cả khi một thuộc tính có thể null, hãy chọn biểu thức không null như primary key.

JPQL dùng COUNT(expression), không dùng cú pháp COUNT(*) như SQL thông thường.

## 6. DISTINCT không thay đổi điều kiện JOIN

DISTINCT chỉ loại kết quả trùng sau khi truy vấn xác định những hàng thỏa JOIN và WHERE. Nó không làm thay đổi quan hệ hoặc số bản ghi trong database.

Ví dụ:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = 'PAID'
~~~

có nghĩa là:

1. Nối Customer với các PurchaseOrder liên quan.
2. Giữ các cặp có status PAID.
3. Trả về Customer duy nhất trong kết quả.

Nếu một Customer không có đơn PAID, Customer đó không xuất hiện vì đây là INNER JOIN.

Không dùng DISTINCT để che giấu một JOIN sai. Nếu kết quả trùng xuất hiện vì điều kiện JOIN thiếu hoặc quan hệ mapping sai, hãy sửa nguyên nhân ở JOIN trước. DISTINCT chỉ phù hợp khi việc nhân bản entity là hệ quả tự nhiên của quan hệ một-nhiều hoặc nhiều-nhiều và mục tiêu nghiệp vụ cần entity duy nhất.

## 7. INNER JOIN và LEFT JOIN khi có dữ liệu liên quan bị thiếu

INNER JOIN chỉ trả về Customer có ít nhất một PurchaseOrder khớp.

~~~jpql
select c
from Customer c
join c.orders o
~~~

Customer Chi không có đơn hàng nên bị loại khỏi kết quả.

LEFT JOIN giữ Customer ở phía trái ngay cả khi không có PurchaseOrder tương ứng:

~~~jpql
select c
from Customer c
left join c.orders o
~~~

Kết quả có thể gồm An, Bình và Chi. Với Chi, các thuộc tính của o được xem là NULL trong hàng kết quả nối.

Nếu Customer có nhiều order, LEFT JOIN vẫn có thể tạo nhiều hàng cho cùng Customer. Muốn mỗi Customer xuất hiện một lần:

~~~jpql
select distinct c
from Customer c
left join c.orders o
~~~

LEFT JOIN không tự loại kết quả trùng; nó chỉ giữ hàng phía trái khi không có hàng phía phải khớp.

## 8. Khác biệt quan trọng giữa điều kiện ON và WHERE với LEFT JOIN

Hai truy vấn dưới đây không tương đương.

**Điều kiện trong ON:**

~~~jpql
select c
from Customer c
left join c.orders o on o.status = :status
~~~

Điều kiện status được áp dụng trong quá trình nối. Mọi Customer vẫn được giữ lại; Customer không có order mang status được chọn sẽ có phía o là NULL.

**Điều kiện trong WHERE:**

~~~jpql
select c
from Customer c
left join c.orders o
where o.status = :status
~~~

WHERE lọc sau khi JOIN. Với Customer không có order, o.status là NULL; điều kiện o.status = :status không đúng. Các hàng đó bị loại. Kết quả vì thế có hành vi gần như INNER JOIN đối với điều kiện này.

Ví dụ muốn lấy tất cả Customer và ghép các đơn PAID nếu có, hãy đặt điều kiện trong ON:

~~~jpql
select c, o
from Customer c
left join c.orders o on o.status = 'PAID'
~~~

Muốn chỉ lấy Customer có ít nhất một đơn PAID, dùng INNER JOIN hoặc LEFT JOIN kèm WHERE:

~~~jpql
select distinct c
from Customer c
join c.orders o
where o.status = 'PAID'
~~~

Muốn lấy Customer không có đơn PAID, có thể dùng LEFT JOIN với ON và kiểm tra khóa phía phải:

~~~jpql
select c
from Customer c
left join c.orders o on o.status = 'PAID'
where o.id is null
~~~

Hoặc dùng NOT EXISTS, thường thể hiện ý định rõ ràng:

~~~jpql
select c
from Customer c
where not exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
      and o.status = 'PAID'
)
~~~

## 9. NULL trong JPQL: logic ba giá trị

Trong Java, bạn thường kiểm tra null bằng:

~~~java
value == null
~~~

Trong JPQL và SQL, NULL có nghĩa là không biết hoặc không có giá trị. Khi so sánh với NULL bằng toán tử thông thường, kết quả là UNKNOWN thay vì TRUE hoặc FALSE.

Ví dụ:

~~~jpql
where c.phone = null
~~~

không phải cách kiểm tra đúng.

Hãy viết:

~~~jpql
where c.phone is null
~~~

Và:

~~~jpql
where c.phone is not null
~~~

Ba giá trị logic:

| Biểu thức | Kết quả |
|---|---|
| NULL = NULL | UNKNOWN |
| NULL <> 'A' | UNKNOWN |
| NULL > 10 | UNKNOWN |
| NULL LIKE 'A%' | UNKNOWN |
| NULL IS NULL | TRUE |
| NULL IS NOT NULL | FALSE |

WHERE chỉ giữ hàng mà điều kiện là TRUE. Hàng có điều kiện FALSE hoặc UNKNOWN đều bị loại.

Điều này giải thích vì sao phép so sánh với NULL không trả về các hàng như mong đợi.

## 10. Kết hợp AND, OR và NOT khi có NULL

Logic ba giá trị cũng ảnh hưởng đến các biểu thức phức hợp.

Một số quy tắc:

| A | B | A AND B | A OR B |
|---|---|---|---|
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Ví dụ:

~~~jpql
where c.phone is null or c.city = :city
~~~

Nếu phone là NULL thì vế đầu TRUE và cả biểu thức OR là TRUE, bất kể vế còn lại là UNKNOWN.

Ngược lại:

~~~jpql
where not (c.phone = :phone)
~~~

không chọn hàng có phone NULL, vì phép so sánh đã cho UNKNOWN và NOT UNKNOWN vẫn là UNKNOWN.

Nếu muốn lấy các hàng có phone khác một giá trị hoặc không có phone, phải diễn đạt rõ:

~~~jpql
where c.phone <> :phone or c.phone is null
~~~

Hãy thiết kế điều kiện theo ý nghĩa nghiệp vụ và nhớ rằng UNKNOWN không giống FALSE trong mọi biểu thức kết hợp.

## 11. Tham số truy vấn có giá trị NULL

Giả sử repository có method:

~~~java
@Query("""
    select c
    from Customer c
    where c.city = :city
    """)
List<Customer> findByCity(@Param("city") String city);
~~~

Nếu truyền city = null, điều kiện trở thành phép so sánh với NULL và không trả về các hàng có city NULL như một phép tìm kiếm null thông thường.

Nếu cần tìm các hàng có city NULL, dùng điều kiện rõ ràng:

~~~jpql
where c.city is null
~~~

Nếu tham số là tùy chọn, một mẫu đơn giản là:

~~~java
@Query("""
    select c
    from Customer c
    where (:city is null or c.city = :city)
    """)
List<Customer> searchByOptionalCity(@Param("city") String city);
~~~

- Khi city là NULL, vế đầu TRUE và không áp dụng bộ lọc city.
- Khi city có giá trị, vế đầu FALSE và truy vấn lọc theo c.city.

Mẫu này phù hợp với bộ lọc đơn giản. Khi có nhiều bộ lọc tùy chọn, nên cân nhắc Specification, Criteria API hoặc xây dựng query động để tránh một câu JPQL quá dài và điều kiện OR làm giảm khả năng sử dụng index trong một số execution plan.

Nếu cần phân biệt ba trạng thái: không truyền bộ lọc, tìm giá trị NULL, và tìm một giá trị cụ thể, một tham số nullable đơn lẻ chưa đủ để biểu diễn cả ba. Hãy dùng một cờ bổ sung hoặc xây dựng query động theo lựa chọn của người gọi.

## 12. COALESCE và NULLIF

JPQL có các hàm xử lý NULL hữu ích.

**COALESCE** trả về biểu thức đầu tiên khác NULL:

~~~jpql
select c.id, coalesce(c.city, 'Chưa cập nhật')
from Customer c
~~~

Nếu city là NULL, kết quả biểu thức là Chưa cập nhật.

**NULLIF(a, b)** trả về NULL nếu a bằng b; nếu không, trả về a:

~~~jpql
select nullif(c.city, '')
from Customer c
~~~

Nếu city là chuỗi rỗng, biểu thức trả về NULL. Nếu không, nó trả lại city.

Có thể dùng COALESCE trong lọc hoặc projection, nhưng cần chú ý kiểu dữ liệu của các biểu thức. Các đối số nên có kiểu tương thích theo quy tắc JPQL/provider.

Không nên dùng COALESCE để che giấu sự khác nhau giữa NULL và chuỗi rỗng nếu nghiệp vụ xem hai trạng thái này khác nhau.

## 13. NULL trong IN và NOT IN

JPQL hỗ trợ IN và NOT IN:

~~~jpql
where c.city in :cities
~~~

hoặc:

~~~jpql
where c.city not in :cities
~~~

Khi danh sách tham số chứa NULL, logic ba giá trị có thể làm kết quả khó đoán. Ví dụ, một giá trị không khớp bất kỳ phần tử nào nhưng danh sách có NULL có thể khiến phép IN cho UNKNOWN; NOT IN cũng có thể không trả về hàng bạn mong muốn.

Không đưa NULL vào danh sách IN/NOT IN nếu chưa định nghĩa rõ ý nghĩa. Hãy tách xử lý null thành điều kiện riêng:

~~~jpql
where c.city in :cities
   or c.city is null
~~~

Nếu danh sách có thể rỗng, hãy xử lý trước ở tầng service hoặc xây dựng query động. Hành vi của collection parameter rỗng có thể khác giữa provider/database; không nên phụ thuộc vào cách một hệ thống cụ thể diễn giải IN ().

Ngoài ra, cần lọc bỏ phần tử null khỏi collection truyền vào nếu mục tiêu là so sánh các giá trị không null.

## 14. NULL trong quan hệ và collection

Nếu Customer không có order, quan hệ collection orders thường là collection rỗng trong mô hình object khi được khởi tạo/tải phù hợp. Trong JPQL, có thể kiểm tra collection rỗng bằng IS EMPTY:

~~~jpql
select c
from Customer c
where c.orders is empty
~~~

Kiểm tra có ít nhất một phần tử:

~~~jpql
select c
from Customer c
where c.orders is not empty
~~~

IS EMPTY dành cho collection-valued path expression. Không dùng IS NULL để kiểm tra collection không có phần tử. Một collection relationship không có phần tử khác với một thuộc tính basic có giá trị NULL.

Để kiểm tra một quan hệ to-one chưa được gán, có thể dùng:

~~~jpql
where c.primaryAddress is null
~~~

Điều kiện này áp dụng khi property quan hệ được phép null. Nếu quan hệ được khai báo optional = false và cột khóa ngoại NOT NULL, dữ liệu hợp lệ không nên có trạng thái đó.

## 15. JOIN nhiều collection có thể nhân số hàng

Giả sử Customer có nhiều PurchaseOrder và nhiều Tag. Nếu JOIN cả hai collection:

~~~jpql
select c
from Customer c
join c.orders o
join c.tags t
~~~

Một Customer có 3 order và 4 tag có thể tạo 12 hàng kết quả trung gian (3 × 4). Đây là tích các tổ hợp khớp của hai quan hệ.

DISTINCT có thể loại kết quả Customer trùng:

~~~jpql
select distinct c
from Customer c
join c.orders o
join c.tags t
~~~

Nhưng database vẫn phải xử lý phép nối và số hàng trung gian. DISTINCT có thể cần sort hoặc hash để loại trùng, tùy execution plan.

Nếu chỉ cần xác nhận có ít nhất một order và ít nhất một tag, hai điều kiện EXISTS có thể rõ nghĩa và tránh nhân số hàng:

~~~jpql
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
)
and exists (
    select t.id
    from CustomerTag t
    where t.customer = c
)
~~~

Chọn JOIN khi cần dữ liệu của entity liên quan trong kết quả hoặc điều kiện. Chọn EXISTS khi chỉ cần kiểm tra sự tồn tại. Luôn xem xét SQL thực tế và execution plan với dữ liệu có quy mô gần production.

## 16. DISTINCT, fetch join và lazy loading

Khi cần tải Customer cùng collection orders, có thể viết:

~~~jpql
select distinct c
from Customer c
left join fetch c.orders
where c.city = :city
~~~

Fetch join tải quan hệ trong cùng truy vấn để tránh việc truy cập từng collection gây N+1. Vì một Customer có thể có nhiều order, phần JOIN vẫn tạo nhiều hàng SQL cho cùng Customer.

DISTINCT diễn đạt mong muốn kết quả entity Customer không trùng. Hành vi SQL và xử lý trùng ở bộ nhớ có thể phụ thuộc JPA provider và phiên bản. Hibernate 6 tự loại entity trùng phát sinh từ collection fetch join ở kết quả entity; provider hoặc phiên bản khác có thể có cách xử lý khác. Hãy kiểm tra kết quả thực tế của provider đang dùng.

Fetch join collection kết hợp phân trang cần đặc biệt cẩn thận. Database phân trang trên các hàng JOIN, trong khi ứng dụng muốn phân trang trên Customer. Việc này có thể làm số Customer mỗi trang không đúng hoặc buộc provider tải nhiều dữ liệu rồi phân trang trong bộ nhớ. Hibernate có thể cảnh báo hoặc cấu hình để ném lỗi với collection fetch pagination.

Một cách an toàn hơn:

1. Truy vấn trang ID Customer theo điều kiện nghiệp vụ.
2. Truy vấn Customer cùng orders bằng fetch join với danh sách ID của trang đó.
3. Giữ thứ tự trang từ truy vấn ID đầu tiên khi dựng kết quả.

Ví dụ truy vấn bước hai:

~~~jpql
select distinct c
from Customer c
left join fetch c.orders
where c.id in :ids
~~~

Nếu dùng Page, count query cần đếm số Customer duy nhất và không fetch collection:

~~~java
@Query(
    value = """
        select distinct c
        from Customer c
        join c.orders o
        where o.status = :status
        """,
    countQuery = """
        select count(distinct c.id)
        from Customer c
        join c.orders o
        where o.status = :status
        """
)
Page<Customer> findDistinctCustomersByOrderStatus(
    @Param("status") String status,
    Pageable pageable
);
~~~

Count query phải phản ánh đúng số entity duy nhất của trang nội dung. Nếu đếm hàng JOIN, tổng số trang có thể lớn hơn số Customer thực tế.

## 17. DISTINCT và hiệu năng

DISTINCT có thể làm tăng chi phí truy vấn vì database phải loại bỏ kết quả trùng. Mức chi phí phụ thuộc số hàng trung gian, index, kiểu JOIN và execution plan.

Trước khi thêm DISTINCT, hãy tự hỏi:

- Có thật sự cần entity duy nhất không?
- JOIN có đang nối đúng quan hệ không?
- Có thể dùng EXISTS thay cho JOIN không?
- Có thể truy vấn DTO hoặc scalar thay vì tải toàn bộ entity không?
- Có cần JOIN tất cả collection không?
- Count query có đang đếm hàng JOIN thay vì entity duy nhất không?
- Có index hỗ trợ điều kiện JOIN và WHERE không?

DISTINCT không thay thế index và cũng không sửa được mô hình quan hệ sai. Nó là một phần của ngữ nghĩa kết quả truy vấn.

## 18. Ví dụ repository tổng hợp

Một repository có thể cung cấp nhiều kiểu truy vấn cho các tình huống khác nhau:

~~~java
package example.repository;

import example.domain.Customer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    @Query("""
        select distinct c
        from Customer c
        join c.orders o
        where o.status = :status
        """)
    List<Customer> findDistinctByOrderStatus(
        @Param("status") String status
    );

    @Query("""
        select count(distinct c.id)
        from Customer c
        join c.orders o
        where o.status = :status
        """)
    long countDistinctByOrderStatus(
        @Param("status") String status
    );

    @Query("""
        select c
        from Customer c
        where c.phone is null
        """)
    List<Customer> findWithoutPhone();

    @Query("""
        select c
        from Customer c
        where (:city is null or c.city = :city)
        """)
    List<Customer> searchByOptionalCity(
        @Param("city") String city
    );

    @Query("""
        select c
        from Customer c
        left join c.orders o on o.status = :status
        where o.id is null
        """)
    List<Customer> findWithoutOrderStatus(
        @Param("status") String status
    );

    @Query(
        value = """
            select distinct c
            from Customer c
            join c.orders o
            where o.status = :status
            """,
        countQuery = """
            select count(distinct c.id)
            from Customer c
            join c.orders o
            where o.status = :status
            """
    )
    Page<Customer> pageDistinctByOrderStatus(
        @Param("status") String status,
        Pageable pageable
    );
}
~~~

Các method minh họa những mục đích khác nhau:

- findDistinctByOrderStatus lấy Customer duy nhất.
- countDistinctByOrderStatus đếm Customer duy nhất sau JOIN.
- findWithoutPhone dùng IS NULL.
- searchByOptionalCity bỏ bộ lọc khi city null.
- findWithoutOrderStatus dùng LEFT JOIN ON và kiểm tra phía phải null.
- pageDistinctByOrderStatus cung cấp count query phù hợp với kết quả distinct.

Nếu tên method bắt đầu bằng find... và có @Query, Spring Data dùng JPQL được khai báo trong annotation. Phần tên method không làm thay đổi nội dung truy vấn tường minh.

## 19. Kiểm thử kết quả DISTINCT và NULL

Đừng chỉ kiểm tra truy vấn có chạy mà hãy xác minh số lượng và danh tính kết quả.

Dữ liệu test nên có:

- Customer An có hai đơn PAID và một đơn CANCELLED.
- Customer Bình có một đơn PAID.
- Customer Chi không có đơn.
- Một Customer có phone NULL.
- Một Customer có city NULL.
- Hai Customer khác nhau có cùng city hoặc cùng name.

Các assertion cần xác minh:

1. JOIN không DISTINCT trả An hai lần khi có hai order PAID.
2. SELECT DISTINCT Customer chỉ trả An một lần.
3. COUNT(DISTINCT c.id) trả số Customer duy nhất.
4. DISTINCT c.city gộp các city trùng nhau và xử lý NULL theo ngữ nghĩa distinct của database/provider.
5. IS NULL trả đúng Customer không có phone.
6. c.phone = :phone với phone null không được dùng thay cho IS NULL.
7. LEFT JOIN ... ON giữ Customer không có order phù hợp.
8. Đặt điều kiện của phía phải vào WHERE có thể loại Customer không có order.
9. Count query của Page trả đúng tổng số Customer duy nhất.
10. Collection fetch join và phân trang được kiểm tra với provider thực tế.

Ví dụ test đơn giản với repository:

~~~java
@Test
void distinctQueryReturnsEachCustomerOnce() {
    List<Customer> customers =
        customerRepository.findDistinctByOrderStatus("PAID");

    assertEquals(2, customers.size());
}

@Test
void countDistinctCountsCustomersRatherThanOrders() {
    long count =
        customerRepository.countDistinctByOrderStatus("PAID");

    assertEquals(2L, count);
}
~~~

Các đoạn test trên giả định dữ liệu test đã được chuẩn bị đúng như mô tả và repository được inject trong integration test. Nếu dùng @DataJpaTest, hãy flush dữ liệu trước khi truy vấn để tránh nhầm lẫn giữa trạng thái trong bộ nhớ và database.

Nên chạy test trên cùng loại database với production khi truy vấn phụ thuộc vào NULL, collation, kiểu dữ liệu, pagination hoặc tối ưu SQL. H2 hữu ích cho kiểm thử nhanh nhưng không bảo đảm mọi hành vi giống PostgreSQL, MySQL hay SQL Server.

## 20. Lỗi thường gặp và cách khắc phục

**1. Một Customer xuất hiện nhiều lần sau JOIN**

Đây thường là kết quả của một Customer có nhiều bản ghi liên quan. Dùng SELECT DISTINCT nếu mục tiêu là entity duy nhất; nếu chỉ cần kiểm tra tồn tại, cân nhắc EXISTS.

**2. COUNT trả số lớn hơn số entity**

COUNT(c) đang đếm kết quả sau JOIN. Dùng COUNT(DISTINCT c.id) khi cần đếm entity duy nhất.

**3. WHERE field = NULL không trả kết quả**

Dùng IS NULL. So sánh với NULL bằng = hoặc <> tạo UNKNOWN.

**4. LEFT JOIN nhưng entity không có quan hệ vẫn bị loại**

Kiểm tra điều kiện phía phải có đặt trong WHERE hay không. Nếu cần giữ hàng phía trái, đặt điều kiện phù hợp trong ON.

**5. DISTINCT trên tên làm mất các entity khác nhau**

DISTINCT áp dụng trên biểu thức được SELECT. Nếu chọn c.name, hai Customer cùng tên được gộp thành một giá trị. Chọn entity c hoặc ID nếu cần phân biệt entity.

**6. NOT IN cho kết quả bất ngờ**

Kiểm tra danh sách có chứa NULL hay không. NULL có thể làm biểu thức thành UNKNOWN. Loại NULL hoặc dùng NOT EXISTS.

**7. Page có totalElements không đúng**

Count query có thể đang đếm hàng JOIN. Dùng COUNT(DISTINCT c.id) và giữ điều kiện lọc tương đương với query nội dung.

**8. Fetch join collection cùng phân trang chậm hoặc trả sai số hàng**

Phân trang trên hàng JOIN có thể khác phân trang trên entity gốc. Dùng truy vấn hai bước hoặc projection phù hợp.

**9. Thêm DISTINCT nhưng truy vấn vẫn chậm**

DISTINCT có chi phí loại trùng. Kiểm tra số hàng trung gian, JOIN, index và execution plan; cân nhắc EXISTS hoặc DTO projection.

## 21. Quy trình chọn cách viết truy vấn

Khi truy vấn qua quan hệ, hãy đi theo các bước:

1. Xác định kết quả cần là entity, scalar, DTO hay số đếm.
2. Xác định quan hệ JOIN có thể tạo nhiều hàng cho một entity gốc hay không.
3. Nếu cần entity duy nhất, dùng SELECT DISTINCT entity.
4. Nếu cần giá trị duy nhất, đặt DISTINCT trên đúng biểu thức scalar hoặc projection.
5. Nếu cần đếm entity duy nhất, dùng COUNT(DISTINCT primaryKey).
6. Nếu chỉ cần kiểm tra có dữ liệu liên quan, cân nhắc EXISTS.
7. Nếu cần giữ entity phía trái khi thiếu quan hệ, dùng LEFT JOIN và đặt điều kiện đúng vị trí ON/WHERE.
8. Với NULL, dùng IS NULL/IS NOT NULL và nhớ logic UNKNOWN.
9. Nếu tham số nullable là bộ lọc tùy chọn, biểu diễn rõ trường hợp bỏ lọc; nếu cần phân biệt tìm NULL và bỏ lọc, dùng trạng thái đầu vào riêng.
10. Nếu phân trang, kiểm tra count query và tránh collection fetch join pagination.
11. Kiểm tra SQL thực tế và execution plan với dữ liệu đủ đại diện.
12. Viết integration test xác minh số lượng, entity identity và trường hợp NULL.

## 22. Checklist tự đánh giá

- [ ] Tôi giải thích được vì sao JOIN một-nhiều có thể lặp entity gốc trong kết quả.
- [ ] Tôi biết dùng SELECT DISTINCT để lấy entity duy nhất.
- [ ] Tôi phân biệt DISTINCT trên entity với DISTINCT trên scalar.
- [ ] Tôi biết dùng COUNT(DISTINCT c.id) để đếm entity duy nhất.
- [ ] Tôi hiểu DISTINCT không sửa điều kiện JOIN sai.
- [ ] Tôi phân biệt INNER JOIN và LEFT JOIN.
- [ ] Tôi hiểu điều kiện ON và WHERE có ý nghĩa khác nhau với LEFT JOIN.
- [ ] Tôi giải thích được NULL tạo kết quả UNKNOWN trong phép so sánh.
- [ ] Tôi biết dùng IS NULL và IS NOT NULL.
- [ ] Tôi hiểu tham số null không tương đương với điều kiện IS NULL.
- [ ] Tôi biết COALESCE, NULLIF, IN và NOT IN có liên quan đến NULL.
- [ ] Tôi biết kiểm tra collection bằng IS EMPTY.
- [ ] Tôi hiểu nhiều collection JOIN có thể nhân số hàng.
- [ ] Tôi biết dùng EXISTS khi chỉ cần kiểm tra sự tồn tại.
- [ ] Tôi biết kiểm tra count query và pagination khi dùng DISTINCT.
- [ ] Tôi có integration test cho kết quả trùng, NULL và LEFT JOIN.

## 23. Câu hỏi ôn tập

**1. Vì sao JOIN Customer với orders có thể trả Customer An hai lần?**

Vì mỗi order khớp tạo một hàng kết quả JOIN. Nếu An có hai order thỏa điều kiện, An xuất hiện trong hai hàng.

**2. SELECT DISTINCT c khác SELECT DISTINCT c.name thế nào?**

SELECT DISTINCT c loại entity trùng theo kết quả entity. SELECT DISTINCT c.name loại các giá trị tên trùng nhau, kể cả khi chúng thuộc các Customer khác nhau.

**3. Khi nào cần COUNT(DISTINCT c.id)?**

Khi đếm Customer sau JOIN một quan hệ có thể tạo nhiều hàng cho cùng Customer.

**4. Vì sao c.phone = NULL không đúng?**

Vì so sánh với NULL tạo UNKNOWN. Dùng c.phone IS NULL để tìm giá trị không có.

**5. Vì sao LEFT JOIN với điều kiện ở WHERE có thể hoạt động như INNER JOIN?**

Hàng không có phía phải nhận giá trị NULL; điều kiện WHERE trên thuộc tính phía phải không thành TRUE nên hàng bị loại.

**6. Khi nào nên dùng EXISTS thay vì JOIN DISTINCT?**

Khi chỉ cần xác định có ít nhất một bản ghi liên quan thỏa điều kiện và không cần lấy dữ liệu từ bản ghi đó. EXISTS thể hiện mục đích và tránh nhân số hàng ở kết quả chính.

**7. Vì sao cần countQuery riêng cho Page có JOIN?**

Để tổng số phần tử phản ánh số entity duy nhất sau điều kiện lọc, không phải số hàng JOIN. Thường dùng COUNT(DISTINCT primaryKey).

**8. Có thể luôn dùng DISTINCT để tránh kết quả trùng không?**

Không. DISTINCT có chi phí và có thể gộp các giá trị scalar mà nghiệp vụ muốn giữ riêng. Trước hết hãy xác định kiểu kết quả và lý do có hàng trùng; sau đó chọn DISTINCT, EXISTS hoặc sửa JOIN phù hợp.

Khi hiểu DISTINCT và logic NULL, bạn có thể đọc đúng kết quả JPQL sau JOIN, đếm chính xác entity, giữ được các hàng cần thiết với LEFT JOIN và tránh các lỗi lọc dữ liệu khó phát hiện.