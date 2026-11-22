# Tách truy vấn phức tạp khỏi thao tác thay đổi miền khi thiết kế Repository với JPA

Trong ứng dụng dùng cơ sở dữ liệu quan hệ, một thực thể thường phục vụ hai nhu cầu rất khác nhau: **đọc dữ liệu để tìm kiếm, lọc, thống kê hoặc hiển thị** và **thay đổi trạng thái theo quy tắc nghiệp vụ**. Nếu dồn cả hai nhu cầu vào một Repository và cho mọi tầng tùy ý sửa Entity, hệ thống dễ gặp vấn đề về hiệu năng, giao dịch và tính nhất quán của miền.

Bài này trình bày cách tách hai luồng trong Java, Spring Data JPA và một cơ sở dữ liệu quan hệ chung. Đây là một dạng **tách trách nhiệm đọc/ghi ở mức ứng dụng** (thường gọi là *CQRS nhẹ*); không bắt buộc dùng hai database, message broker hay kiến trúc phân tán.

## 1. Nhận diện hai loại công việc

Giả sử ứng dụng bán hàng cần thực hiện:

- **Tác vụ đọc:** tìm đơn hàng theo khách hàng, trạng thái, khoảng thời gian và sản phẩm; phân trang danh sách; tổng hợp doanh thu theo khách hàng.
- **Tác vụ ghi:** xác nhận đơn hàng, thêm dòng hàng, hủy đơn; kiểm tra điều kiện chuyển trạng thái và bảo đảm toàn bộ thay đổi được thực hiện trong một giao dịch.

Hai loại tác vụ có yêu cầu khác nhau:

| Khía cạnh | Truy vấn đọc (query) | Thay đổi miền (command) |
| --- | --- | --- |
| Mục đích | Trả dữ liệu đúng hình dạng màn hình/báo cáo | Duy trì bất biến và chuyển trạng thái hợp lệ |
| Đầu ra thường gặp | DTO, projection, trang kết quả, thống kê | Kết quả lệnh hoặc mã định danh |
| Dữ liệu nạp | Chỉ các cột và quan hệ cần hiển thị | Aggregate/Entity cần để kiểm tra quy tắc |
| Giao dịch | Thường dùng giao dịch chỉ đọc | Giao dịch ghi, dirty checking hoặc lưu mới |
| Kiểu truy vấn | Lọc động, join, EXISTS, GROUP BY, phân trang | Tìm aggregate theo định danh, khóa hoặc phiên bản |
| Tiêu chí tối ưu | Tốc độ đọc, số dòng và dữ liệu truyền tải | Đúng nghiệp vụ, nhất quán, xử lý xung đột |

Một truy vấn tìm kiếm có thể kết hợp nhiều bảng và trả về một hàng DTO; không vì vậy mà cần nạp toàn bộ đồ thị Entity. Ngược lại, thay đổi trạng thái cần chạy qua phương thức miền, kể cả khi có thể thực hiện nhanh bằng một câu UPDATE.

## 2. Ranh giới trách nhiệm nên thiết kế

Một cách tổ chức thư mục:

~~~text
com.example.orders
├── domain
│   ├── Order.java                  # Aggregate và bất biến
│   ├── OrderLine.java
│   └── OrderStatus.java
├── command
│   ├── OrderRepository.java       # Nạp/lưu aggregate
│   └── OrderCommandService.java   # Điều phối giao dịch ghi
└── query
    ├── OrderSearchFilter.java     # Điều kiện tìm kiếm
    ├── OrderSummary.java          # DTO trả cho màn hình
    ├── OrderReadRepository.java   # JPQL/Criteria/SQL đọc
    └── OrderQueryService.java     # Điều phối tác vụ đọc
~~~

Luồng phụ thuộc chính:

~~~text
HTTP/API
  ├── Command endpoint → OrderCommandService → OrderRepository → Order (aggregate)
  └── Query endpoint   → OrderQueryService   → OrderReadRepository → OrderSummary
                                                        │
                                                  Cùng database
~~~

**OrderRepository** phục vụ vòng đời aggregate và các thao tác thật sự cần Entity quản lý bởi persistence context. **OrderReadRepository** chỉ truy xuất dữ liệu, trả một read model rõ ràng cho bên gọi. Cả hai có thể dùng cùng EntityManagerFactory và datasource, nhưng có giao diện và trách nhiệm khác nhau.

Không nhất thiết mỗi lớp nghiệp vụ phải có cả hai loại Repository. Chỉ tách khi xuất hiện sự khác biệt rõ rệt giữa nhu cầu đọc và thay đổi miền.

## 3. Luồng ghi: bảo vệ quy tắc bằng aggregate

Ví dụ miền có đơn hàng và các dòng hàng. Đơn chỉ được xác nhận khi còn ở trạng thái chờ, có ít nhất một dòng hàng và tổng tiền dương.

**OrderStatus.java**

~~~java
package com.example.orders.domain;

public enum OrderStatus {
    PENDING, CONFIRMED, CANCELLED
}
~~~

**Order.java** (Java 17, Jakarta Persistence):

~~~java
package com.example.orders.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.PENDING;

    @Column(name = "total_amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    private long version;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    protected Order() { } // JPA

    public Order(Long customerId, Instant createdAt) {
        if (customerId == null || createdAt == null) {
            throw new IllegalArgumentException("Customer and time are required");
        }
        this.customerId = customerId;
        this.createdAt = createdAt;
    }

    public void addLine(Long productId, int quantity, BigDecimal unitPrice) {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Only pending orders can be edited");
        }
        if (productId == null || quantity <= 0
                || unitPrice == null || unitPrice.signum() <= 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
        lines.add(new OrderLine(this, productId, quantity, unitPrice));
        totalAmount = totalAmount.add(
            unitPrice.multiply(BigDecimal.valueOf(quantity))
        );
    }

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException("Invalid order transition");
        }
        if (lines.isEmpty() || totalAmount.signum() <= 0) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

**OrderLine.java**

~~~java
package com.example.orders.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private Order order;

    @Column(name = "product_id", nullable = false)
    private Long productId;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() { } // JPA

    OrderLine(Order order, Long productId, int quantity, BigDecimal unitPrice) {
        this.order = order;
        this.productId = productId;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }
}
~~~

Ở đây không có public setter cho trường **status**. Các thay đổi quan trọng đi qua phương thức **confirm()**, **addLine()** để quy tắc tập trung tại miền. Trong hệ thống thực tế, cần bổ sung quy tắc tiền tệ, làm tròn, tồn kho và quyền truy cập phù hợp với nghiệp vụ.

Repository phục vụ luồng ghi:

**OrderRepository.java**

~~~java
package com.example.orders.command;

import com.example.orders.domain.Order;
import java.util.Optional;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface OrderRepository extends JpaRepository<Order, Long> {
    @EntityGraph(attributePaths = "lines")
    @Query("select o from Order o where o.id = :id")
    Optional<Order> findForConfirmation(@Param("id") Long id);
}
~~~

**OrderCommandService.java**

~~~java
package com.example.orders.command;

import com.example.orders.domain.Order;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final OrderRepository orders;

    public OrderCommandService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void confirm(long orderId) {
        Order order = orders.findForConfirmation(orderId)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));
        order.confirm();
        // order đang được quản lý: JPA dirty checking sẽ ghi trạng thái khi flush.
    }
}
~~~

**Tại sao không UPDATE trạng thái trực tiếp?** Một lệnh như UPDATE orders SET status = 'CONFIRMED' WHERE id = ? có thể bỏ qua việc kiểm tra dòng hàng, trạng thái trước đó, các domain event và logic quản lý phiên bản. Với thao tác chuyển trạng thái mang ý nghĩa nghiệp vụ, hãy nạp aggregate, gọi hành vi miền và commit giao dịch. Bulk update trực tiếp chỉ thích hợp khi đã chứng minh thao tác đó không cần các quy tắc tương ứng và đã kiểm soát sự đồng bộ của persistence context.

Annotation **@Version** giúp phát hiện cập nhật cạnh tranh theo cơ chế optimistic locking: hai giao dịch cùng đọc phiên bản cũ thì một giao dịch có thể thất bại khi flush/commit sau giao dịch còn lại. Ứng dụng phải xử lý xung đột theo nghiệp vụ; không tự động retry mọi lệnh vì có lệnh tạo ra tác động ngoài database.

Ví dụ dùng **@EntityGraph** để lấy các dòng hàng cần cho điều kiện xác nhận. Không áp dụng eager fetching cho mọi truy vấn chỉ vì một command cần dữ liệu đó.

## 4. Luồng đọc: trả về DTO theo nhu cầu sử dụng

Màn hình quản lý đơn hàng cần hiển thị năm trường: ID, khách hàng, trạng thái, tổng tiền và ngày tạo. Nó không cần một Entity **Order** với toàn bộ **OrderLine** trong persistence context.

**OrderSummary.java**

~~~java
package com.example.orders.query;

import com.example.orders.domain.OrderStatus;
import java.math.BigDecimal;
import java.time.Instant;

public record OrderSummary(
    Long id,
    Long customerId,
    OrderStatus status,
    BigDecimal totalAmount,
    Instant createdAt
) { }
~~~

**OrderSearchFilter.java**

~~~java
package com.example.orders.query;

import com.example.orders.domain.OrderStatus;
import java.time.Instant;

public record OrderSearchFilter(
    Long customerId,
    OrderStatus status,
    Long productId,
    Instant fromInclusive,
    Instant toExclusive
) { }
~~~

Truy vấn dưới đây xử lý bộ lọc tùy chọn; riêng điều kiện sản phẩm dùng **EXISTS** để tránh nhân bản đơn hàng khi một đơn có nhiều dòng hàng thỏa mãn. Hai query dùng cùng một mệnh đề WHERE: một query lấy trang DTO, một query đếm tổng số đơn.

**OrderReadRepository.java**

~~~java
package com.example.orders.query;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadRepository {
    @PersistenceContext
    private EntityManager em;

    public Page<OrderSummary> search(OrderSearchFilter filter, Pageable pageable) {
        List<String> predicates = new ArrayList<>();
        Map<String, Object> params = new HashMap<>();

        if (filter.customerId() != null) {
            predicates.add("o.customerId = :customerId");
            params.put("customerId", filter.customerId());
        }
        if (filter.status() != null) {
            predicates.add("o.status = :status");
            params.put("status", filter.status());
        }
        if (filter.productId() != null) {
            predicates.add(
                "exists (select l.id from OrderLine l " +
                "where l.order = o and l.productId = :productId)"
            );
            params.put("productId", filter.productId());
        }
        if (filter.fromInclusive() != null) {
            predicates.add("o.createdAt >= :fromInclusive");
            params.put("fromInclusive", filter.fromInclusive());
        }
        if (filter.toExclusive() != null) {
            predicates.add("o.createdAt < :toExclusive");
            params.put("toExclusive", filter.toExclusive());
        }

        String where = predicates.isEmpty()
            ? ""
            : " where " + String.join(" and ", predicates);

        String select = "select new com.example.orders.query.OrderSummary(" +
            "o.id, o.customerId, o.status, o.totalAmount, o.createdAt) " +
            "from Order o";

        TypedQuery<OrderSummary> dataQuery = em.createQuery(
            select + where + " order by o.createdAt desc, o.id desc",
            OrderSummary.class
        );
        TypedQuery<Long> countQuery = em.createQuery(
            "select count(o.id) from Order o" + where,
            Long.class
        );

        params.forEach((name, value) -> {
            dataQuery.setParameter(name, value);
            countQuery.setParameter(name, value);
        });

        dataQuery.setFirstResult(Math.toIntExact(pageable.getOffset()));
        dataQuery.setMaxResults(pageable.getPageSize());

        return new PageImpl<>(
            dataQuery.getResultList(),
            pageable,
            countQuery.getSingleResult()
        );
    }
}
~~~

**OrderQueryService.java**

~~~java
package com.example.orders.query;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderQueryService {
    private final OrderReadRepository orders;

    public OrderQueryService(OrderReadRepository orders) {
        this.orders = orders;
    }

    @Transactional(readOnly = true)
    public Page<OrderSummary> search(OrderSearchFilter filter, Pageable pageable) {
        if (pageable.getPageSize() > 100) {
            throw new IllegalArgumentException("Page size exceeds 100");
        }
        if (filter.fromInclusive() != null && filter.toExclusive() != null
                && !filter.fromInclusive().isBefore(filter.toExclusive())) {
            throw new IllegalArgumentException("Invalid date range");
        }
        return orders.search(filter, pageable);
    }
}
~~~

Các điểm đáng chú ý:

1. **DTO projection** chỉ lấy các cột đã khai báo; phía gọi không giữ Entity có thể bị thay đổi ngoài ý muốn hoặc kích hoạt lazy loading.
2. **Tham số hóa** bằng setParameter() giúp dữ liệu đầu vào không trở thành đoạn JPQL. Phần WHERE được ghép từ các mảnh cố định do lập trình viên kiểm soát.
3. **Phân trang ổn định** sắp xếp theo createdAt và thêm id để phá hòa. Ví dụ cố định thứ tự; nếu API nhận sort động, phải lập danh sách trường/hướng sắp xếp được phép thay vì nối thẳng chuỗi người dùng vào JPQL.
4. **@Transactional(readOnly = true)** nêu rõ ý định của luồng đọc và có thể tạo tối ưu tùy Spring/JPA provider. Đây không phải cơ chế phân quyền cấm ghi của database.
5. **Count query** cần phản ánh đúng điều kiện lọc và không bị ảnh hưởng bởi phép join làm nhân bản dữ liệu. Với API cuộn vô hạn, có thể dùng Slice hoặc cursor để tránh đếm tổng số hàng nếu giao diện không cần total count.

Truy vấn minh họa dùng JPQL động để dễ nhìn. Khi điều kiện phức tạp hơn, có thể chuyển phần dựng điều kiện sang **Criteria API**, **Specification**, **Querydsl** hoặc dùng **jOOQ/JdbcTemplate** cho truy vấn SQL đặc thù. Việc chọn công cụ đọc không buộc phải thay đổi miền ghi.

## 5. Khi nào truy vấn nên ở read repository chuyên dụng?

Một truy vấn báo cáo có thể tổng hợp doanh thu theo khách hàng:

~~~jpql
select o.customerId, count(o.id), sum(o.totalAmount)
from Order o
where o.status = :confirmedStatus
  and o.createdAt >= :fromInclusive
  and o.createdAt < :toExclusive
group by o.customerId
order by sum(o.totalAmount) desc
~~~

Truy vấn này là đọc số liệu tổng hợp, không phải yêu cầu chỉnh sửa một **Order**. Nó nên được đóng gói trong read repository và ánh xạ sang DTO báo cáo có các trường customerId, orderCount, totalRevenue. Cần xác định rõ đơn vị tiền, thời điểm hạch toán và việc doanh thu có trừ hoàn tiền hay không theo chính sách nghiệp vụ, thay vì coi phép SUM là định nghĩa doanh thu mặc định.

Các trường hợp nên ưu tiên lớp truy vấn riêng:

- Màn hình có nhiều bộ lọc, phân trang, thống kê hoặc sắp xếp cần kế hoạch SQL tối ưu.
- Câu truy vấn kết hợp dữ liệu từ nhiều aggregate để dựng một view.
- Kết quả đọc khác đáng kể so với cấu trúc Entity, như bảng tổng hợp và biểu đồ.
- Một tuyến API cần tải nhanh số lượng lớn dữ liệu mà không cần dirty checking từng Entity.

Với thao tác tìm một aggregate đơn giản để thực hiện command, phương thức **findById()** của Repository ghi vẫn phù hợp. Không cần tạo thêm một tầng đọc chỉ để đổi tên phương thức.

## 6. Những sai lầm thường gặp

| Cách làm dễ gây vấn đề | Hậu quả | Cách xử lý |
| --- | --- | --- |
| findAll() rồi lọc bằng Java Stream | Đưa dữ liệu không cần thiết lên bộ nhớ, khó phân trang | Lọc tại database, trả DTO theo trang |
| Trả Entity trực tiếp cho controller/UI | Dễ làm lộ cấu trúc miền, lazy loading ngoài giao dịch | Dùng read DTO/projection |
| JOIN FETCH collection rồi phân trang ngay | Có thể tạo nhiều hàng SQL cho một aggregate, phân trang sai hoặc bị xử lý trong bộ nhớ | Dùng projection; hoặc phân trang ID rồi nạp chi tiết trong bước riêng |
| Đưa tìm kiếm đa điều kiện vào Repository ghi | Repository phình to, khó tìm ranh giới nghiệp vụ | Tách read repository và search filter |
| Dùng @Modifying UPDATE cho chuyển trạng thái miền | Bỏ qua hành vi aggregate và có thể làm lệch persistence context | Đưa lệnh qua phương thức miền trong giao dịch |
| Nạp cả đồ thị quan hệ chỉ để hiển thị vài trường | Tốn I/O, tăng nguy cơ N+1 | Chọn đúng cột, dùng EXISTS/DTO, đo SQL phát sinh |
| Nối thẳng sort/filter do client gửi vào JPQL/SQL | Rủi ro injection hoặc truy vấn ngoài ý muốn | Bind giá trị; whitelist tên cột và chiều sort |

Đặc biệt, không nên coi **Repository** là nơi chứa mọi SQL của hệ thống và mọi quy tắc nghiệp vụ. Repository ghi giúp truy cập aggregate; hành vi như xác nhận/hủy đơn thuộc về miền, còn service điều phối transaction, phân quyền và các phụ thuộc cần thiết.

## 7. Giao dịch, đồng thời và nhất quán dữ liệu

**Đối với command:** mở một giao dịch cho một thao tác nghiệp vụ có tính nguyên tử; đọc trạng thái cần thiết; gọi phương thức miền; để JPA flush khi commit. Dùng **@Version** hoặc khóa bi quan khi quy tắc cạnh tranh yêu cầu. Constraint ở database (foreign key, unique, check phù hợp) vẫn là lớp bảo vệ quan trọng bên cạnh validation của miền.

**Đối với query:** đọc trong ranh giới giao dịch rõ ràng, trả DTO trước khi giao dịch kết thúc. Nếu nhiều query phải nhìn cùng một snapshot, cần xét isolation level và khả năng của database; annotation readOnly đơn thuần không bảo đảm snapshot nhất quán giữa nhiều lần đọc.

**Đối với truy cập đa tenant:** cả luồng đọc và ghi phải giới hạn dữ liệu theo tenant/quyền của người dùng đã xác thực. Không coi customerId/tenantId do client tự gửi là đủ để cấp quyền. Khi tải aggregate ghi theo ID, cần xác minh người dùng có quyền thao tác với aggregate đó.

**Đối với hai database đọc/ghi:** nếu sau này bổ sung read replica, cache hoặc projection xử lý bất đồng bộ, kết quả đọc có thể chậm hơn commit ở luồng ghi. Khi đó phải thiết kế rõ độ trễ chấp nhận được, read-after-write và cơ chế xử lý retry/idempotency. Với ví dụ trong bài dùng cùng database và truy vấn trực tiếp, không mặc nhiên tồn tại độ trễ đồng bộ kiểu CQRS phân tán.

## 8. Tối ưu hiệu năng theo từng luồng

Đối với luồng đọc, hãy quan sát SQL thực tế thay vì chỉ nhìn JPQL:

1. Đo số truy vấn, thời gian thực thi và số dòng trả về; kiểm tra tình huống **N+1**.
2. Dùng EXPLAIN/EXPLAIN ANALYZE theo hệ quản trị để xem kế hoạch thực thi và chỉ mục được sử dụng.
3. Đánh giá chỉ mục phù hợp với bộ lọc thực tế, ví dụ trên **orders(customer_id, created_at, id)** và **order_lines(product_id, order_id)**. Cấu hình chỉ mục phụ thuộc thống kê dữ liệu, độ chọn lọc và database; không nên tạo mọi tổ hợp cột.
4. Với trang có offset rất lớn, cân nhắc **keyset pagination** dựa trên cặp (createdAt, id) và điều kiện con trỏ tương ứng; đảm bảo thứ tự duy nhất và truyền con trỏ an toàn.
5. Nếu báo cáo GROUP BY quá nặng, cân nhắc bảng tổng hợp/materialized view và quy tắc cập nhật dữ liệu, sau khi đo được nhu cầu thực tế.

Đối với luồng ghi, hãy đo thời gian giao dịch, số entity bị nạp và số phép cập nhật. Giữ transaction ở phạm vi một command; tránh gọi dịch vụ mạng chậm khi đang giữ khóa database. Tối ưu nạp quan hệ theo **trường hợp sử dụng**, chẳng hạn EntityGraph cho xác nhận đơn nhưng không áp dụng rộng cho tất cả API tìm kiếm.

## 9. Kiểm thử theo trách nhiệm

**Kiểm thử command** nên xác nhận các bất biến: đơn rỗng không thể xác nhận, đơn đã xác nhận không thêm dòng hàng, không chuyển trạng thái trái phép, lệnh hợp lệ được lưu sau flush/commit. Kiểm tra thêm xung đột **@Version** với hai giao dịch khi hệ thống có cập nhật đồng thời.

**Kiểm thử query** nên dùng dữ liệu có nhiều đơn, nhiều dòng hàng và nhiều trạng thái để xác nhận: bộ lọc tùy chọn, biên thời gian [fromInclusive, toExclusive), EXISTS không tạo dòng trùng, tổng count khớp và thứ tự trang ổn định. Test integration với database tương thích môi trường chạy giúp phát hiện khác biệt JPQL/SQL, kiểu dữ liệu ngày giờ và phân trang.

**Kiểm thử kiến trúc** nên xem xét những quy ước sau: controller đọc chỉ phụ thuộc QueryService; command không cập nhật trạng thái bằng setter từ bên ngoài miền; DTO đọc không đưa Entity JPA ra API. Đây là các quy ước thiết kế có thể kiểm tra bằng review hoặc công cụ kiểm thử kiến trúc khi dự án đủ lớn.

## 10. Tiêu chí chọn mức độ tách

Đầu tiên, giữ một Repository JPA đơn giản nếu hệ thống chỉ cần CRUD nhỏ và các truy vấn không khác biệt nhiều. Khi màn hình tìm kiếm hoặc báo cáo bắt đầu tạo yêu cầu riêng về lọc, projection và hiệu năng, tạo **read repository** cùng DTO/query service. Chỉ cân nhắc database đọc riêng, event-driven projection hoặc CQRS đầy đủ khi có nhu cầu thực tế về tải đọc, triển khai, độ trễ hoặc mở rộng độc lập.

Điểm mấu chốt của thiết kế là **các lệnh thay đổi trạng thái bảo vệ bất biến của miền, còn truy vấn đọc được tự do tối ưu theo hình dạng dữ liệu cần trả về**. Ranh giới này giúp mã JPA dễ hiểu hơn, tránh nạp Entity không cần thiết, đồng thời giữ logic nghiệp vụ trong nơi thích hợp.
