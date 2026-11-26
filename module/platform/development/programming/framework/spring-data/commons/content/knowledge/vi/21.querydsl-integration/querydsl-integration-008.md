# Giới hạn Querydsl extension so với API truy vấn đầy đủ của store

Một repository có thể nhận `Predicate` của Querydsl mà vẫn không cho phép caller quyết định toàn bộ cấu trúc truy vấn. Phân biệt hai mức này giúp tránh cố biến một bộ lọc thành công cụ cho mọi yêu cầu về join, báo cáo, tải quan hệ hoặc thao tác dữ liệu hàng loạt.

Bài học thuộc chương **Tích hợp Querydsl** của **SPRING_DATA_COMMONS**. Trọng tâm là ranh giới giữa abstraction dùng chung của Spring Data và API truy vấn của module lưu trữ cụ thể. Các ví dụ thực thi chọn Spring Data JPA; với store khác, cần chọn integration và API tương ứng.

Sau bài học, bạn có thể:

- Giải thích những gì `QuerydslPredicateExecutor` cho phép cấu hình.
- Phân biệt predicate lọc bản ghi với cấu trúc SELECT, FROM, JOIN và GROUP BY.
- Nhận biết những khả năng có thể được mở rộng qua fluent query tùy phiên bản.
- Chuyển yêu cầu vượt phạm vi executor sang repository fragment.
- Kiểm tra đúng kết quả, số lượng, cách tải quan hệ và chi phí truy vấn.

## 1. “Querydsl extension” trong Spring Data là gì?

Trong bài, “Querydsl extension” chủ yếu chỉ khả năng repository triển khai `QuerydslPredicateExecutor<T>`.

Ví dụ với JPA:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

Giả định:

- `Customer` là entity JPA được ánh xạ hợp lệ.
- Q-type đã được sinh đúng và có thể được integration tìm thấy.
- Dependency Querydsl, processor và module Spring Data tương thích.
- Store và loại truy vấn hỗ trợ những biểu thức được sử dụng.

Caller có thể xây điều kiện:

~~~java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.active.isTrue()
    .and(customer.displayName.containsIgnoreCase("an"));
~~~

Sau đó yêu cầu repository thực thi:

~~~java
Page<Customer> result = repository.findAll(
    predicate,
    PageRequest.of(
        0,
        20,
        Sort.by("id").ascending()
    )
);
~~~

Đây là một cách dùng có giá trị: caller mô tả **điều kiện chọn khách hàng**, còn implementation xây truy vấn cho kiểu miền `Customer`.

Nhưng caller chưa cung cấp một đối tượng truy vấn hoàn chỉnh có thể tùy ý đổi nguồn dữ liệu, chọn biểu thức tổng hợp hoặc thêm fetch join.

### 1.1. Phân biệt ba lớp tên gọi

| Lớp | Vai trò |
|---|---|
| Querydsl core và Q-type | Tạo đường dẫn, biểu thức có kiểu và predicate |
| Spring Data Querydsl extension | Đưa predicate vào các thao tác repository đã được định nghĩa |
| API truy vấn của backend | Xây và thực thi cấu trúc truy vấn phù hợp công nghệ lưu trữ |

Trong một ứng dụng JPA, API truy vấn có thể là Querydsl JPA với `JPAQueryFactory`, JPA Criteria hoặc JPQL. Khi cần khả năng SQL đặc thù, có thể phải đi tới API SQL hoặc truy vấn native phù hợp.

Trong MongoDB, aggregation pipeline có mô hình khác với JPQL. Một repository nhận predicate không tự trở thành công cụ tạo mọi pipeline.

“API đầy đủ” vì vậy luôn phải hiểu trong phạm vi backend cụ thể. Querydsl JPA cung cấp nhiều quyền xây dựng truy vấn hơn executor, nhưng vẫn chịu giới hạn của JPQL, provider và cơ sở dữ liệu.

## 2. Executor cho phép làm gì?

Những thao tác phổ biến của `QuerydslPredicateExecutor` gồm:

| Thao tác | Hợp đồng chính |
|---|---|
| `findOne(predicate)` | Tìm kết quả duy nhất nếu có |
| `findAll(predicate)` | Lấy các entity gốc khớp điều kiện |
| `findAll(predicate, sort)` | Lọc và sắp xếp |
| `findAll(predicate, pageable)` | Lọc và phân trang |
| Các overload dùng `OrderSpecifier` | Sắp xếp qua biểu thức Querydsl theo API hỗ trợ |
| `count(predicate)` | Đếm entity gốc khớp điều kiện |
| `exists(predicate)` | Kiểm tra có kết quả khớp |

Ở các phiên bản hỗ trợ, còn có phương thức `findBy(predicate, queryFunction)` để cấu hình cách lấy kết quả qua fluent query.

Điểm chung là executor làm việc từ một kiểu miền gốc và một tập thao tác đã có sẵn. Nó không nhận trực tiếp một đối tượng `JPAQuery` với mọi cấu hình mà caller đã xây.

### 2.1. Không đồng nhất giới hạn executor với giới hạn Querydsl

Có thể viết:

~~~java
BooleanExpression adults = customer.age.goe(18);
~~~

Điều này chứng minh Querydsl biểu đạt được điều kiện tuổi.

Nó không chứng minh executor có một tham số để cấu hình:

~~~text
SELECT một biểu thức SUM
FROM nhiều nguồn
JOIN theo cấu trúc tùy chọn
GROUP BY khách hàng
HAVING tổng tiền vượt ngưỡng
~~~

`Predicate` là một phần của truy vấn, thường đóng vai trò điều kiện. Một truy vấn đầy đủ còn có nguồn dữ liệu, danh sách chọn, join, nhóm, tổng hợp, thứ tự và các tùy chọn thực thi.

## 3. Bản đồ khả năng và giới hạn

| Yêu cầu | Extension repository | Khi cần API truy vấn khác |
|---|---|---|
| Lọc theo thuộc tính entity gốc | Phù hợp | Khi biểu thức không được module hỗ trợ |
| Nhóm AND, OR, NOT | Predicate có thể diễn đạt | Khi cần thêm cấu trúc truy vấn ngoài điều kiện |
| Sắp xếp và phân trang | Có các thao tác tương ứng | Khi cần chiến lược phân trang hoặc count đặc thù |
| Trả entity gốc | Là đường dùng phổ biến | Khi kết quả là mô hình tổng hợp khác |
| Projection qua fluent query | Có thể có tùy phiên bản và module | Khi cần danh sách SELECT tùy ý hoặc aggregate |
| Duyệt đường dẫn quan hệ | Có thể làm phát sinh cách truy vấn tương ứng của backend | Khi cần kiểm soát join rõ ràng |
| Subquery bên trong predicate | Có thể dùng nếu backend và integration hỗ trợ | Khi toàn bộ truy vấn vượt khả năng executor |
| Fetch join | Không có tham số chung để caller cấu hình tùy ý | Query API hoặc cơ chế tải quan hệ riêng của module |
| GROUP BY, HAVING | Không có thao tác chung để thiết lập cấu trúc này | Query API hỗ trợ tổng hợp |
| Bulk UPDATE, DELETE qua biểu thức Querydsl | Không thuộc hợp đồng predicate executor | API cập nhật/xóa phù hợp |
| CTE, window function, cú pháp riêng của database | Không thuộc hợp đồng chung | API và backend hỗ trợ tính năng đó |

Bảng này tránh hai cách hiểu sai:

- “Có Querydsl extension thì có toàn bộ khả năng Querydsl.”
- “Executor không cho cấu hình join nên mọi predicate liên quan quan hệ hoặc subquery đều không dùng được.”

Cần xem chính xác điều gì đang nằm trong predicate và điều gì yêu cầu thay đổi cấu trúc truy vấn do implementation quản lý.

## 4. Quan hệ và subquery: ranh giới cần hiểu chính xác

### 4.1. Đường dẫn quan hệ không phải quyền điều khiển mọi join

Giả sử `Customer` có `address.city`:

~~~java
Predicate predicate = customer.address.city.eq("Ha Noi");
~~~

Nếu ánh xạ và backend hỗ trợ, điều kiện có thể được chuyển thành truy vấn tương ứng. Trong JPA, việc truy cập quan hệ có thể kéo theo ngữ nghĩa join của JPQL/provider.

Nhưng biểu thức trên không cho caller chỉ định đầy đủ:

- Join nào phải là LEFT JOIN hay INNER JOIN.
- Điều kiện nào phải nằm ở ON thay vì WHERE.
- Quan hệ nào phải được fetch cùng entity gốc.
- Cách tránh trùng root khi join quan hệ nhiều phần tử.

Do đó, không dùng sự tồn tại của đường dẫn lồng nhau để suy ra quyền kiểm soát toàn bộ chiến lược join.

### 4.2. Một predicate có thể chứa EXISTS

Giả sử `PurchaseOrder` có quan hệ `customer` và trạng thái `PAID`. Với Querydsl JPA và backend hỗ trợ truy vấn tương ứng:

~~~java
import com.querydsl.core.types.Predicate;
import com.querydsl.jpa.JPAExpressions;

QCustomer customer = QCustomer.customer;
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

Predicate hasPaidOrder = JPAExpressions
    .selectOne()
    .from(order)
    .where(
        order.customer.eq(customer),
        order.status.eq(OrderStatus.PAID)
    )
    .exists();

Predicate predicate = customer.active.isTrue()
    .and(hasPaidOrder);

Iterable<Customer> customers = repository.findAll(predicate);
~~~

Ý định là chọn khách hàng đang hoạt động và có ít nhất một đơn đã thanh toán.

Đây là ví dụ một phần cấu trúc subquery được gói trong predicate. Nó không biến kết quả thành báo cáo tổng doanh thu, không thay đổi danh sách SELECT của truy vấn ngoài và không cho caller tùy ý cấu hình fetch join.

Các Q-type và root trong biểu thức phải khớp mô hình mà executor sử dụng. Biểu thức hợp lệ về kiểu vẫn cần được kiểm chứng trên adapter thực tế.

## 5. Fluent query mở rộng cách lấy kết quả nhưng có phạm vi

Nếu phiên bản `QuerydslPredicateExecutor` và module hỗ trợ:

~~~java
public interface CustomerView {
    Long getId();
    String getDisplayName();
}
~~~

~~~java
List<CustomerView> rows = repository.findBy(
    predicate,
    query -> query
        .as(CustomerView.class)
        .all()
);
~~~

Ví dụ giả định module hỗ trợ interface projection cho đường dùng này.

Điều đó cho thấy không nên khẳng định executor “chỉ có thể trả entity và không bao giờ có projection”. Khả năng còn phụ thuộc API fluent và implementation.

Tuy nhiên, chuyển sang một projection của thuộc tính entity khác với xây dựng:

~~~text
customerId, customerName, SUM(order.totalAmount)
GROUP BY customerId, customerName
HAVING SUM(order.totalAmount) >= ngưỡng
~~~

Các terminal operation và phương thức cấu hình cụ thể cần được kiểm tra theo phiên bản đang dùng. Có `findBy` không có nghĩa callback là một `JPAQueryFactory` thu nhỏ với mọi thao tác của Querydsl JPA.

## 6. Ví dụ vượt phạm vi executor: báo cáo doanh thu

Yêu cầu:

> Tìm các khách hàng đang hoạt động có đơn đã thanh toán trong một khoảng thời gian; tính tổng doanh thu mỗi khách; chỉ lấy các tổng đạt ngưỡng và sắp xếp giảm dần theo doanh thu.

Mô hình minh họa:

| Kiểu | Thuộc tính cần dùng |
|---|---|
| `Customer` | `id: Long`, `displayName: String`, `active: Boolean` |
| `PurchaseOrder` | `id: Long`, `customer: Customer`, `status: OrderStatus`, `totalAmount: BigDecimal`, `placedAt: Instant` |
| `OrderStatus` | Có giá trị `PAID` |

Giả định:

- `totalAmount` và `placedAt` không null.
- Toàn bộ số tiền được cộng trong cùng đơn vị tiền tệ.
- Khoảng thời gian có dạng `[fromInclusive, toExclusive)`.
- Báo cáo chỉ xét khách hàng có ít nhất một đơn PAID trong kỳ.
- Cấu hình Querydsl JPA có Q-type cho cả hai entity.

Một predicate có thể mô tả các điều kiện:

~~~text
customer.active = true
order.status = PAID
order.placedAt >= fromInclusive
order.placedAt < toExclusive
~~~

Nhưng để tạo báo cáo, còn cần:

~~~text
SELECT customer.id, customer.displayName, SUM(order.totalAmount)
FROM PurchaseOrder
JOIN customer
GROUP BY customer.id, customer.displayName
HAVING SUM(order.totalAmount) >= minimumRevenue
ORDER BY SUM(order.totalAmount) DESC, customer.id ASC
~~~

Đây là sự thay đổi về **hình dạng kết quả và cấu trúc truy vấn**, không chỉ là thêm điều kiện vào một lần `findAll` trả `Customer`.

## 7. Đóng gói truy vấn đầy đủ trong repository fragment

### 7.1. Khai báo kiểu kết quả

~~~java
import java.math.BigDecimal;

public final class CustomerRevenue {

    private final Long customerId;
    private final String customerName;
    private final BigDecimal revenue;

    public CustomerRevenue(
            Long customerId,
            String customerName,
            BigDecimal revenue) {
        this.customerId = customerId;
        this.customerName = customerName;
        this.revenue = revenue;
    }

    public Long getCustomerId() {
        return customerId;
    }

    public String getCustomerName() {
        return customerName;
    }

    public BigDecimal getRevenue() {
        return revenue;
    }
}
~~~

Đây là DTO của một dòng báo cáo, không phải một entity khách hàng được thêm tạm thuộc tính tổng tiền.

### 7.2. Định nghĩa hợp đồng fragment

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public interface CustomerReportRepository {

    List<CustomerRevenue> findTopRevenue(
        Instant fromInclusive,
        Instant toExclusive,
        BigDecimal minimumRevenue,
        int limit
    );
}
~~~

Repository chính kết hợp cả thao tác chung lẫn truy vấn riêng:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                CustomerReportRepository {
}
~~~

Các ví dụ là những đoạn mã ở các file riêng trong cùng package ứng dụng phù hợp. Các import repository đã được giới thiệu ở phần trước.

### 7.3. Triển khai bằng Querydsl JPA

Ví dụ dưới đây dùng hệ annotation/API `jakarta.persistence`. Dự án dùng hệ persistence khác phải chọn cấu hình dependency tương thích; không trộn hai hệ chỉ bằng cách đổi một import.

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import jakarta.persistence.EntityManager;

import org.springframework.transaction.annotation.Transactional;

import com.querydsl.core.types.Projections;
import com.querydsl.core.types.dsl.NumberExpression;
import com.querydsl.jpa.impl.JPAQueryFactory;

public class CustomerReportRepositoryImpl
        implements CustomerReportRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerReportRepositoryImpl(
            EntityManager entityManager) {
        this.queryFactory = new JPAQueryFactory(entityManager);
    }

    @Override
    @Transactional(readOnly = true)
    public List<CustomerRevenue> findTopRevenue(
            Instant fromInclusive,
            Instant toExclusive,
            BigDecimal minimumRevenue,
            int limit) {

        if (fromInclusive == null || toExclusive == null
                || !fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException(
                "Khoảng thời gian phải có đầu nhỏ hơn cuối"
            );
        }

        if (minimumRevenue == null
                || minimumRevenue.signum() < 0) {
            throw new IllegalArgumentException(
                "Ngưỡng doanh thu phải là số không âm"
            );
        }

        if (limit < 1 || limit > 1000) {
            throw new IllegalArgumentException(
                "Giới hạn phải nằm trong khoảng 1 đến 1000"
            );
        }

        QCustomer customer = QCustomer.customer;
        QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

        NumberExpression<BigDecimal> revenue =
            order.totalAmount.sum();

        return queryFactory
            .select(Projections.constructor(
                CustomerRevenue.class,
                customer.id,
                customer.displayName,
                revenue
            ))
            .from(order)
            .join(order.customer, customer)
            .where(
                customer.active.isTrue(),
                order.status.eq(OrderStatus.PAID),
                order.placedAt.goe(fromInclusive),
                order.placedAt.lt(toExclusive)
            )
            .groupBy(
                customer.id,
                customer.displayName
            )
            .having(revenue.goe(minimumRevenue))
            .orderBy(
                revenue.desc(),
                customer.id.asc()
            )
            .limit(limit)
            .fetch();
    }
}
~~~

Tên implementation theo quy ước fragment `CustomerReportRepository` cộng hậu tố `Impl`. Việc phát hiện fragment còn phụ thuộc package scanning và cấu hình repository của ứng dụng.

Truy vấn này cho caller một hợp đồng nghiệp vụ hẹp: lấy báo cáo doanh thu với tham số đã kiểm tra. Các chi tiết join, aggregate và projection nằm trong implementation.

### 7.4. Những quyết định cần đọc trong ví dụ

| Thành phần | Quyết định |
|---|---|
| `from(order)` | Bắt đầu từ các đơn hàng, không bắt đầu từ danh sách khách không có đơn |
| `join(order.customer, customer)` | Liên kết đơn với khách để lọc và lấy thông tin |
| `where(...)` | Loại đơn ngoài kỳ, sai trạng thái hoặc thuộc khách không hoạt động |
| `groupBy(...)` | Một nhóm cho mỗi khách hàng |
| `having(...)` | Lọc sau khi đã cộng doanh thu |
| `orderBy(...)` | Xếp theo doanh thu, thêm id để phân biệt trường hợp bằng nhau |
| `limit(limit)` | Giới hạn số dòng báo cáo trả về |
| `Projections.constructor` | Tạo DTO từ các biểu thức SELECT |

Nếu cần hiển thị cả khách không có đơn với doanh thu bằng 0, hợp đồng và truy vấn phải thay đổi. Không chỉ bỏ một điều kiện trong WHERE rồi giả định kết quả sẽ tự có những khách đó.

### 7.5. Constructor projection cũng có giới hạn kiểm tra kiểu

Các đường dẫn như `order.totalAmount` có kiểu. Nhưng `Projections.constructor` không biến mọi sai lệch giữa danh sách biểu thức và constructor DTO thành lỗi biên dịch.

Cần xác nhận constructor khớp kiểu và thứ tự đối số. Những lựa chọn projection có sinh metadata riêng có thể tăng mức kiểm tra, nhưng cần thêm cấu hình sinh mã và đánh đổi về phụ thuộc. Với mọi cách, vẫn phải kiểm tra kết quả ánh xạ.

## 8. Count của báo cáo khác count của entity gốc

Giả sử trong kỳ có:

| Khách | Các đơn PAID | Tổng |
|---|---|---|
| C01 | 80 và 70 | 150 |
| C02 | 200 | 200 |
| C03 | 90 | 90 |

Với ngưỡng 100:

- Có 4 dòng đơn hàng.
- Có 3 khách hàng có đơn PAID.
- Có 2 nhóm doanh thu đạt ngưỡng.

Nếu phân trang báo cáo, tổng số phần tử hợp lệ là **2 nhóm**, không phải 4 đơn hoặc 3 khách.

Một lời gọi `repository.count(predicate)` trên repository `Customer` đếm theo hợp đồng entity gốc. Nó không tự biết cần đếm số nhóm còn lại sau HAVING trong truy vấn báo cáo riêng.

Tương tự, `countDistinct(customer.id)` chỉ theo điều kiện trước tổng hợp chưa chắc bằng số nhóm sau HAVING.

Với truy vấn grouped phức tạp, cần thiết kế truy vấn count đúng cùng ngữ nghĩa. Một số cách đếm qua bảng dẫn xuất hoặc CTE có thể không diễn đạt được bằng JPQL chuẩn; khi đó phải chọn phương án phù hợp backend thay vì ép vào một API không hỗ trợ.

Nếu sản phẩm chỉ cần danh sách top N và không cần tổng số nhóm, hợp đồng trả `List<CustomerRevenue>` có giới hạn có thể đã đủ. Đừng tạo `Page` với một tổng số suy đoán từ truy vấn count không tương đương.

## 9. Join để lọc không đồng nghĩa fetch quan hệ

Một truy vấn chọn `Customer` theo điều kiện liên quan tới đơn hàng không tự bảo đảm collection đơn hàng đã được tải.

Cần phân biệt:

| Mục đích | Câu hỏi |
|---|---|
| Join hoặc EXISTS để lọc | Khách hàng nào thỏa điều kiện? |
| Fetch quan hệ | Những dữ liệu liên quan nào được tải cùng kết quả? |
| Projection DTO | Cần các giá trị nào để dựng dòng kết quả? |

Trả entity rồi truy cập quan hệ lazy có thể tạo thêm truy vấn. Predicate đúng chưa đủ để chứng minh đường đọc đã tránh N+1.

Hợp đồng chung của executor không có tham số để caller tùy ý thêm fetch join. Module JPA có thể cung cấp cơ chế riêng như entity graph, metadata phương thức hoặc query API tùy chỉnh. Cần kiểm tra cách áp dụng của integration, không suy rằng annotation hoặc graph sẽ có hiệu lực trong mọi đường gọi.

### 9.1. Fetch collection cùng phân trang cần thiết kế riêng

Join một customer với nhiều orders có thể tạo nhiều dòng cho một customer. Áp dụng giới hạn trên các dòng join không nhất thiết tạo đúng một trang customer hoàn chỉnh.

Tùy provider và cấu hình, phân trang kết hợp fetch collection có thể dẫn tới cảnh báo, giới hạn trong bộ nhớ hoặc lỗi. Thêm DISTINCT không tự giải quyết toàn bộ mâu thuẫn giữa số dòng join và số entity gốc.

Một chiến lược thường cần đánh giá:

1. Chọn trang định danh customer theo bộ lọc và thứ tự xác định.
2. Tải dữ liệu liên quan cho tập định danh đó bằng truy vấn riêng.
3. Khôi phục thứ tự của trang, vì điều kiện IN không bảo đảm giữ thứ tự đầu vào.
4. Xác định yêu cầu nhất quán nếu dữ liệu thay đổi giữa hai lượt đọc.

Đây là thiết kế của một đường truy vấn cụ thể. Executor không thể suy ra đầy đủ chiến lược đó chỉ từ một predicate.

## 10. API của backend cũng có ranh giới riêng

### 10.1. Querydsl JPA không phải API cho mọi cú pháp SQL

`JPAQueryFactory` cung cấp cách xây truy vấn cho mô hình JPA. Nó có thể cho phép kiểm soát SELECT, FROM, JOIN, WHERE, GROUP BY và HAVING rõ hơn executor.

Tuy nhiên, nó vẫn chịu giới hạn của JPQL và provider. Không suy ra rằng có thể dùng mọi CTE, window function, toán tử JSON hoặc cú pháp riêng của database bằng Querydsl JPA tiêu chuẩn.

Khi yêu cầu dựa vào tính năng SQL cụ thể, hãy đánh giá API SQL hoặc truy vấn native phù hợp và xác nhận cách ánh xạ kết quả.

### 10.2. Querydsl SQL dùng mô hình metadata khác

Metadata truy vấn bảng trong Querydsl SQL không đồng nhất với Q-type entity của Querydsl JPA.

Một Q-type JPA đại diện đường dẫn entity; metadata SQL cần thể hiện bảng, cột và các thông tin quan hệ ở cấp SQL. Vì vậy, không lấy một `QCustomer` được sinh cho JPA rồi mặc định coi nó là metadata bảng dùng được ở mọi backend.

Nếu chuyển từ truy vấn entity sang truy vấn SQL trực tiếp, cần xem lại:

- Metadata và cách sinh mã.
- Ánh xạ kiểu dữ liệu.
- Cách tham gia giao dịch.
- Cách dựng kết quả.
- Những quy tắc trước đây do JPA provider xử lý.

### 10.3. MongoDB có mô hình truy vấn và aggregation riêng

Ở một module có tích hợp Querydsl cho MongoDB, predicate vẫn là abstraction có phạm vi.

Những yêu cầu như pipeline gồm nhiều bước, `unwind`, nhóm dữ liệu, tính toán trường hoặc lookup cần được diễn đạt bằng API mà module MongoDB hỗ trợ, chẳng hạn các abstraction aggregation phù hợp của `MongoTemplate`.

Không chuyển khái niệm “fetch join JPA” nguyên vẹn sang MongoDB. Cũng không suy rằng một predicate repository có thể thay thế toàn bộ aggregation pipeline.

### 10.4. Tùy chọn thực thi là khả năng của module

Lock, hint, timeout, fetch size, collation và các tùy chọn tương tự không nằm trong một hợp đồng predicate chung áp dụng đồng nhất cho mọi store.

Module có thể cung cấp annotation, metadata hoặc API riêng cho một số lựa chọn. Khi cần chúng, phải kiểm tra đường gọi cụ thể có tiếp nhận và thực thi cấu hình không.

## 11. Predicate executor không phải API bulk DML

`QuerydslPredicateExecutor` cung cấp thao tác truy vấn theo predicate. Nó không có hợp đồng chung để caller thực hiện mọi biểu thức UPDATE hoặc DELETE của Querydsl.

Ví dụ ý định bulk update trong Querydsl JPA:

~~~java
// Minh họa bên trong một thao tác cập nhật có giao dịch phù hợp.
long changed = queryFactory
    .update(customer)
    .set(customer.active, false)
    .where(customer.status.eq(CustomerStatus.CLOSED))
    .execute();
~~~

Đoạn mã dùng query API trực tiếp, không phải một phương thức của predicate executor.

Với JPA, bulk DML có ngữ nghĩa khác việc tải từng entity rồi sửa qua vòng đời entity:

- Persistence context có thể còn giữ trạng thái cũ.
- Callback và cơ chế auditing dựa trên vòng đời entity không tự được áp dụng như khi cập nhật từng entity.
- Những yêu cầu về phiên bản, đồng bộ dữ liệu và giao dịch cần được thiết kế riêng.

Không chuyển sang bulk update chỉ vì nó nhận cùng một loại predicate mà bỏ qua các khác biệt đó.

## 12. Web binding không mở rộng cấu trúc truy vấn

Spring Data có thể cung cấp tích hợp web chuyển tham số request thành predicate và cho phép tùy chỉnh binding.

Nếu dùng cơ chế đó, cần phân biệt:

| Thành phần | Điều nó làm |
|---|---|
| Web binding | Chuyển giá trị đầu vào thành điều kiện trên các đường dẫn được cấu hình |
| Predicate executor | Thực thi thao tác repository với predicate |
| Query API của store | Quyết định cấu trúc truy vấn trong phạm vi backend |

Tùy chỉnh cách bind một trường thành `containsIgnoreCase` hoặc giới hạn những thuộc tính tham gia bộ lọc không tự bổ sung GROUP BY, fetch join hoặc aggregation pipeline.

Một endpoint báo cáo thường nên nhận một DTO tham số rõ ràng rồi gọi fragment có hợp đồng nghiệp vụ, thay vì cố diễn đạt cả báo cáo qua các tham số binding của một endpoint tìm entity.

## 13. Chọn điểm dừng abstraction theo yêu cầu

Có thể phân loại một yêu cầu mới bằng các câu hỏi sau:

1. **Kết quả có còn là entity gốc hoặc projection được executor hỗ trợ không?**
2. **Yêu cầu chỉ thay đổi điều kiện lọc, sort và cách lấy kết quả, hay thay đổi cả nguồn dữ liệu và nhóm tổng hợp?**
3. **Có cần kiểm soát join, fetch, hint hoặc thao tác dữ liệu riêng không?**
4. **Backend có thực sự hỗ trợ cấu trúc muốn dùng không?**
5. **Nếu cần tổng số, phép đếm có còn là count entity gốc không?**

Ví dụ:

| Yêu cầu | Hướng triển khai |
|---|---|
| Tìm khách active theo tuổi và từ khóa | Predicate executor |
| Tìm khách có ít nhất một đơn PAID | Có thể dùng predicate chứa EXISTS nếu integration hỗ trợ |
| Trả vài thuộc tính khách qua fluent projection | Dùng khi phiên bản và module hỗ trợ |
| Tổng doanh thu mỗi khách đạt ngưỡng | Fragment với query API hỗ trợ aggregate |
| Tải một trang khách kèm collection đơn hàng | Thiết kế đường đọc và chiến lược fetch riêng |
| Báo cáo dùng hàm riêng của database | API phù hợp backend, có thể cần native SQL |
| Aggregation nhiều bước trên tài liệu | API aggregation của module |
| Cập nhật hàng loạt theo điều kiện | API DML hoặc thao tác cập nhật phù hợp |

Nên giữ những bộ lọc đơn giản ở abstraction sẵn có, rồi tạo fragment cho yêu cầu thực sự cần quyền kiểm soát lớn hơn.

Fragment vẫn là một phần của mô hình repository Spring Data. Nó cho phép caller tiếp tục làm việc với một hợp đồng rõ ràng mà không phải nhận trực tiếp `EntityManager` hoặc công cụ truy vấn.

### 13.1. Có thể tái sử dụng điều kiện nhưng không tái sử dụng mù quáng

Một số biểu thức lọc có thể được dùng ở cả executor và truy vấn riêng. Tuy nhiên, phải kiểm tra:

- Chúng đang dùng root và alias nào.
- Chúng cần những join hoặc subquery nào.
- Chúng có đặt điều kiện trước hay sau aggregate.
- Chúng có giữ nguyên ngữ nghĩa khi đổi nguồn truy vấn không.

Điều kiện trên một dòng đơn hàng không tự tương đương điều kiện trên tổng doanh thu của nhóm. WHERE và HAVING không thay thế lẫn nhau.

## 14. Kiểm chứng đúng lớp trách nhiệm

Một truy vấn tùy chỉnh cần được xác nhận ở nhiều mặt:

| Mặt cần xác nhận | Câu hỏi |
|---|---|
| Điều kiện lọc | Có đúng khách, trạng thái và khoảng thời gian không? |
| Hình dạng kết quả | Mỗi dòng đại diện entity, nhóm hay tổ hợp nào? |
| Aggregate | Có cộng trùng do join nhiều phía không? |
| Count | Tổng số có cùng ngữ nghĩa với nội dung không? |
| Fetch | Những quan hệ nào thực sự đã được tải? |
| Thứ tự | Có khóa phân biệt khi giá trị sort chính bằng nhau không? |
| Hiệu năng | Có đọc thừa, count tốn kém, N+1 hoặc giới hạn trong bộ nhớ không? |

Đặc biệt, nếu báo cáo join thêm một collection thứ hai, mỗi đơn có thể bị nhân thành nhiều dòng trước khi SUM. Querydsl vẫn có thể tạo ra mã hợp lệ về kiểu, nhưng tổng doanh thu sai.

Không dùng `sumDistinct(totalAmount)` như cách sửa chung: hai đơn khác nhau có cùng số tiền vẫn là hai khoản doanh thu phải cộng. Cần sửa cấu trúc join hoặc cách tổng hợp theo đúng đơn vị dữ liệu.

Các bằng chứng hữu ích gồm truy vấn sinh ra, tham số, dữ liệu mẫu có quan hệ một-nhiều và tập kết quả kỳ vọng. Một mock trả sẵn DTO không chứng minh GROUP BY, HAVING hoặc fetch strategy hoạt động đúng trên store.

## 15. Những kết luận sai thường gặp

| Kết luận sai | Cách hiểu đúng |
|---|---|
| Có predicate là mô tả được toàn bộ query | Predicate là biểu thức điều kiện, query còn nhiều thành phần |
| Executor không hỗ trợ bất kỳ quan hệ nào | Một số đường dẫn và subquery có thể dùng được; quyền cấu hình join vẫn có giới hạn |
| Executor luôn chỉ trả entity | Một số phiên bản/module hỗ trợ fluent projection |
| Có projection là có báo cáo SUM/GROUP BY tùy ý | Projection của entity và truy vấn tổng hợp có cấu trúc khác nhau |
| Count cùng predicate luôn đúng cho mọi báo cáo | Count phải tương ứng đúng đơn vị kết quả và HAVING |
| Join để lọc đã tránh N+1 | Lọc và tải quan hệ là hai quyết định khác nhau |
| Fetch collection rồi thêm DISTINCT là phân trang đúng | Cần xử lý số dòng join, entity gốc và cách provider giới hạn |
| Querydsl JPA dùng được mọi SQL của database | Nó còn chịu giới hạn JPQL và provider |
| Q-type có kiểu bảo đảm truy vấn đúng nghiệp vụ | Kiểu không phát hiện sai nhóm, sai aggregate hoặc cộng trùng |
| Chuyển sang custom query là bỏ Spring Data | Repository fragment là một cách mở rộng repository |

## 16. Bài thực hành

### 16.1. Phân loại yêu cầu

Với từng yêu cầu, chỉ ra phần nào là predicate và phần nào cần cấu trúc truy vấn khác:

1. Khách active có tên chứa từ khóa.
2. Khách active có ít nhất một đơn PAID trong tháng.
3. Tổng doanh thu mỗi khách trong tháng, chỉ lấy tổng từ 100 trở lên.
4. Mười khách có doanh thu cao nhất.
5. Một trang khách kèm đầy đủ danh sách đơn của mỗi người.
6. Số nhóm báo cáo thỏa HAVING.
7. Một pipeline nhóm tài liệu và tính trường trong MongoDB.

Không chỉ trả lời “dùng Querydsl”. Hãy nêu rõ dùng executor, fluent query, fragment với Querydsl JPA hay API backend khác.

### 16.2. Kiểm tra truy vấn báo cáo

Tạo ba khách active với các đơn PAID trong kỳ:

| Khách | Giá trị đơn |
|---|---|
| C01 | 80, 70 |
| C02 | 200 |
| C03 | 90 |

Sau đó thêm:

- Một đơn chưa PAID có giá trị lớn.
- Một đơn PAID nằm ngoài khoảng thời gian.
- Một đơn PAID đúng tại `toExclusive`.
- Một khách không hoạt động có đơn PAID trong kỳ.

Với ngưỡng 100, kỳ vọng C02 có doanh thu 200 và C01 có doanh thu 150. Những đơn bổ sung không được làm tăng doanh thu báo cáo.

Kiểm tra thêm hai khách có cùng doanh thu để quan sát thứ tự phụ theo id.

### 16.3. Kiểm tra sai lệch count và join

- So sánh số dòng đơn trước nhóm với số nhóm đạt HAVING.
- Xác nhận count theo khách trước HAVING không bị dùng thay tổng số nhóm.
- Thêm một quan hệ nhiều phần tử vào truy vấn thử nghiệm và kiểm tra nguy cơ nhân doanh thu.
- Dùng dữ liệu có hai đơn bằng tiền nhau để phát hiện cách sửa sai bằng SUM DISTINCT.

### 16.4. Ghi lại quyết định thiết kế

Hoàn thành bảng:

| Yêu cầu | Abstraction được chọn | Lý do | Bằng chứng xác nhận |
|---|---|---|---|
| Tìm entity theo nhiều bộ lọc | Executor hoặc phương án phù hợp | Chỉ cần thay đổi điều kiện | Tập entity kết quả |
| Báo cáo tổng hợp | Fragment/query API | Cần SELECT, GROUP BY, HAVING | DTO và tổng doanh thu |
| Tải quan hệ | Cơ chế fetch của module | Cần hợp đồng tải dữ liệu rõ | Truy vấn và dữ liệu được tải |
| Tính năng đặc thù store | API backend thích hợp | Vượt hợp đồng chung | Hành vi trên store thực |

Giữ ranh giới rõ giúp mỗi abstraction làm đúng phần việc của nó: predicate diễn đạt điều kiện, extension thực thi các thao tác repository đã định nghĩa, còn query API của backend tạo cấu trúc truy vấn vượt phạm vi đó. Repository fragment là nơi nối các khả năng ấy với một hợp đồng nghiệp vụ cụ thể và có thể kiểm chứng.
