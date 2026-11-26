# Truy vấn suy diễn, truy vấn có annotation và named query

Một phương thức repository như `findByStatus(...)` chỉ mô tả thao tác ứng dụng muốn thực hiện. Để chạy được, Spring Data còn phải xác định truy vấn đến từ đâu, gắn tham số như thế nào và giao việc thực thi cho loại kho dữ liệu đang dùng. Trong chương **Chiến lược truy vấn** của **SPRING_DATA_COMMONS**, bài này phân biệt ba cách cung cấp truy vấn: suy diễn từ tên phương thức, khai báo bằng annotation và khai báo dưới một tên để repository tra cứu.

Mục tiêu là chọn được cách biểu đạt phù hợp, hiểu điều gì xảy ra khi một truy vấn khai báo bị thiếu và tránh áp dụng nhầm khả năng của JPA cho tất cả module Spring Data. Các ví dụ còn kết nối truy vấn với phân trang, sắp xếp và việc duy trì hợp đồng của repository.

## 1. Phân biệt abstraction chung và khả năng của từng kho dữ liệu

Spring Data Commons cung cấp các abstraction dùng chung như `Repository`, metadata của phương thức truy vấn, tham số, `Pageable`, `Sort` và `QueryLookupStrategy`. Module tích hợp với kho dữ liệu cụ thể quyết định ngôn ngữ truy vấn, annotation nào được hiểu và những chiến lược tra cứu nào được hỗ trợ.

| Cách cung cấp truy vấn | Nguồn mô tả điều kiện | Điểm mạnh | Giới hạn cần nhớ |
| --- | --- | --- | --- |
| Truy vấn suy diễn, hay derived query | Tên phương thức và tham số | Gọn với bộ lọc đơn giản, gắn trực tiếp với mô hình thuộc tính | Tên dài khi điều kiện phức tạp; toán tử thực tế phụ thuộc module |
| Truy vấn có annotation | Metadata ngay trên phương thức, chẳng hạn `@Query` của module đang dùng | Thấy phương thức và nội dung truy vấn cùng một chỗ | Cú pháp, khả năng binding, phân trang và truy vấn ghi phụ thuộc module |
| Named query | Khai báo truy vấn dưới một tên và tra cứu bằng tên đó | Tái sử dụng hoặc quản lý truy vấn ở vị trí riêng | Cần giữ tên khai báo và quy ước tra cứu khớp nhau; không phải mọi kho dữ liệu hỗ trợ cùng cơ chế |

Không tồn tại một annotation `@Query` trong Commons có thể dùng thay thế cho mọi kho dữ liệu. Ví dụ, `org.springframework.data.jpa.repository.Query` thuộc Spring Data JPA; annotation cùng tên của module khác không vì cùng tên mà có cùng ngữ nghĩa.

Tương tự, `@NamedQuery` là cơ chế của JPA, không phải một annotation repository phổ quát của Spring Data Commons. Các ví dụ JPQL, `@NamedQuery` và `@EnableJpaRepositories` bên dưới đều được đánh dấu là **ví dụ Spring Data JPA**. Khi dùng một module khác, cần đối chiếu khả năng và quy ước của module đó.

> Chuyển một interface sang module lưu trữ khác không tự chuyển đổi được chuỗi JPQL, SQL, tên trường vật lý hoặc cơ chế named query. Phần abstraction có thể giống nhau trong khi ngữ nghĩa truy vấn vẫn khác.

## 2. Một phương thức repository được giải quyết như thế nào?

Có thể hình dung quy trình cho một phương thức truy vấn như sau:

```text
Phương thức truy vấn trên repository
                |
                v
Chiến lược tìm truy vấn của module
                |
                +--> Tìm khai báo: annotation / named query / nguồn được hỗ trợ
                |
                +--> Phân tích tên phương thức, nếu chiến lược cho phép
                |
                v
Gắn các tham số điều kiện và xử lý Pageable / Sort
                |
                v
Thực thi qua công nghệ lưu trữ cụ thể
                |
                v
Chuyển kết quả về kiểu trả về của phương thức
```

Đây là mô hình khái niệm, không phải cam kết rằng mỗi bước chỉ xảy ra tại thời điểm gọi phương thức. Việc phân giải và kiểm tra truy vấn thường gắn với khởi tạo repository; thời điểm phát hiện lỗi còn phụ thuộc chế độ bootstrap, module và provider.

Cũng cần phân biệt **phương thức truy vấn** với các phương thức đã có implementation từ repository cơ sở hoặc repository fragment. Ví dụ, khi kế thừa `CrudRepository`, `findById(ID)` là thao tác có sẵn với ngữ nghĩa định danh, không nên xem nó như một tên tùy ý để suy diễn lại điều kiện.

## 3. Mô hình xuyên suốt bài học

Giả sử ứng dụng cần đọc đơn hàng với các thuộc tính Java sau:

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh đơn hàng |
| `customerEmail` | `String` | Email khách hàng |
| `status` | `OrderStatus` | Trạng thái nghiệp vụ |
| `createdAt` | `Instant` | Thời điểm tạo |
| `total` | `BigDecimal` | Tổng tiền |

```java
public enum OrderStatus {
    NEW, PAID, CANCELLED
}
```

Trong các ví dụ JPA, lớp domain có tên `PurchaseOrder`, entity cũng có tên `PurchaseOrder`, còn bảng vật lý là `purchase_orders`. Ví dụ phần mapping, đã lược bỏ constructor và accessor:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;

@Entity(name = "PurchaseOrder")
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "customer_email")
    private String customerEmail;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Column(name = "created_at")
    private Instant createdAt;

    private BigDecimal total;

    // Bổ sung constructor không tham số theo yêu cầu JPA và các accessor.
}
```

Ba lớp tên cần được giữ riêng:

- Tên thuộc tính Java, ví dụ `createdAt`, dùng khi suy diễn phương thức và khi truyền `Sort` theo thuộc tính.
- Tên entity và thuộc tính entity, ví dụ `PurchaseOrder` và `o.createdAt`, dùng trong JPQL.
- Tên bảng và cột, ví dụ `purchase_orders` và `created_at`, dùng trong SQL native.

Đây là nền tảng để đọc đúng các ví dụ sau; chúng là những phương án khai báo thay thế để minh họa, không yêu cầu đặt mọi phương án vào cùng một repository.

## 4. Truy vấn suy diễn: lấy tên phương thức làm mô tả

### 4.1. Ví dụ bộ lọc đơn giản

Ví dụ Spring Data JPA sử dụng interface `Repository` của Commons:

```java
import java.time.Instant;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    Page<PurchaseOrder> findByStatusAndCreatedAtGreaterThanEqual(
            OrderStatus status,
            Instant since,
            Pageable pageable);
}
```

Ý nghĩa của tên phương thức:

| Thành phần | Cách đọc |
| --- | --- |
| `find` | Thực hiện truy vấn đọc |
| `By` | Bắt đầu phần điều kiện |
| `Status` | So sánh thuộc tính `status` với tham số tương ứng |
| `And` | Kết hợp hai điều kiện bằng AND |
| `CreatedAtGreaterThanEqual` | So sánh `createdAt >= since` |

`Pageable` là tham số đặc biệt để điều khiển phân trang và sắp xếp; nó không phải giá trị thứ ba trong biểu thức lọc. Các tham số điều kiện thông thường phải khớp với thứ tự và số lượng đối số mà các toán tử trong tên cần dùng.

Ví dụ gọi:

```java
import java.time.Instant;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Sort sort = Sort.by(Sort.Direction.DESC, "createdAt")
        .and(Sort.by(Sort.Direction.DESC, "id"));
Pageable pageable = PageRequest.of(0, 20, sort);

Page<PurchaseOrder> page = repository
        .findByStatusAndCreatedAtGreaterThanEqual(
                OrderStatus.PAID,
                Instant.parse("2026-01-01T00:00:00Z"),
                pageable);
```

Chỉ số trang bắt đầu từ `0`. Điều kiện phụ `id` giúp thứ tự xác định hơn khi nhiều đơn hàng có cùng `createdAt`; nó không tạo ra snapshot dữ liệu. Khi dữ liệu thay đổi giữa các lần đọc trang, phân trang theo offset vẫn có thể bị dịch chuyển.

### 4.2. Những tên thường gặp

Các ví dụ dưới đây phù hợp để minh họa với Spring Data JPA và các thuộc tính đã nêu:

```java
List<PurchaseOrder> findByCustomerEmailIgnoreCase(String email);

boolean existsByStatus(OrderStatus status);

long countByStatus(OrderStatus status);

List<PurchaseOrder> findTop5ByStatusOrderByCreatedAtDescIdDesc(
        OrderStatus status);
```

- `IgnoreCase` yêu cầu so sánh không phân biệt hoa thường trên thuộc tính chuỗi; chi tiết SQL, collation và khả năng tận dụng chỉ mục cần xem ở kho dữ liệu thực tế.
- `existsBy...` biểu đạt nhu cầu kiểm tra tồn tại, giúp caller không phải tải danh sách chỉ để gọi `isEmpty()`.
- `countBy...` biểu đạt phép đếm, không phải tải entity rồi đếm trong bộ nhớ.
- `Top5` giới hạn kết quả; `OrderByCreatedAtDescIdDesc` khai báo thứ tự tĩnh trong tên.

Không suy từ các ví dụ này rằng mọi module hỗ trợ mọi keyword. Một tên phương thức được parser nhận diện vẫn cần module lưu trữ có khả năng thực hiện toán tử tương ứng.

### 4.3. Giới hạn của cách đặt tên

Tên phương thức phản ánh cấu trúc thuộc tính, không phải văn bản mô tả nghiệp vụ tự do. Với truy vấn suy diễn, đổi tên `createdAt` thành `submittedAt` đòi hỏi cập nhật các phương thức tham chiếu đến thuộc tính đó. Java compiler có thể vẫn biên dịch interface cũ vì tên phương thức vốn là một chuỗi định danh hợp lệ; lỗi xuất hiện khi framework phân tích nó.

Tên dài không phải lỗi tự thân, nhưng những yêu cầu sau thường là dấu hiệu nên chọn truy vấn khai báo hoặc một abstraction truy vấn phù hợp khác:

- Nhiều nhóm AND/OR với cách đặt ngoặc cần thể hiện rõ.
- Join, aggregation, subquery hoặc phép tính không diễn đạt rõ bằng tên.
- Nhiều bộ lọc tùy chọn khiến số tổ hợp phương thức tăng nhanh.
- Người đọc phải giải mã một tên quá dài để hiểu điều kiện nghiệp vụ.

Với parser chuẩn của Spring Data, biểu thức dạng `AOrBAndC` được nhóm theo các phần OR, trong mỗi phần là các điều kiện AND: `A OR (B AND C)`. Tên phương thức không cung cấp dấu ngoặc tùy ý để yêu cầu `(A OR B) AND C`. Khi cách nhóm điều kiện quan trọng, một truy vấn có biểu thức rõ ràng sẽ dễ kiểm tra hơn.

Một tập bộ lọc động lớn cũng không tự biến thành bài toán nên viết một `@Query` khổng lồ. Tùy module, có thể cần repository fragment, Query by Example, Specification hoặc một API dựng truy vấn khác. Chúng là các hướng mở rộng, không phải tính năng có sẵn đồng nhất ở mọi repository.

## 5. Truy vấn bằng annotation: đặt nội dung truy vấn cạnh phương thức

### 5.1. Ví dụ JPQL trong Spring Data JPA

Khi cần thể hiện điều kiện trực tiếp, có thể dùng annotation `@Query` của JPA module:

```java
import java.time.Instant;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    @Query(
        value = """
            select o
            from PurchaseOrder o
            where o.status = :status
              and o.createdAt >= :since
            """,
        countQuery = """
            select count(o)
            from PurchaseOrder o
            where o.status = :status
              and o.createdAt >= :since
            """
    )
    Page<PurchaseOrder> searchOrders(
            @Param("status") OrderStatus status,
            @Param("since") Instant since,
            Pageable pageable);
}
```

Ở đây tên `searchOrders` không cần mã hóa các điều kiện lọc. Phần mô tả điều kiện nằm trong `@Query`; tên phương thức có thể diễn đạt vai trò nghiệp vụ ngắn gọn hơn.

`PurchaseOrder` là tên entity, còn `createdAt` là tên thuộc tính entity. Đây là JPQL, không phải câu SQL đọc trực tiếp bảng `purchase_orders`.

`@Param("status")` và `@Param("since")` nối tham số Java với placeholder có tên trong truy vấn. Cách viết tường minh này giúp người đọc không phải phụ thuộc vào việc build có giữ tên tham số Java hay không. Có thể có cơ chế suy ra tên tham số tùy cấu hình, nhưng không cần dựa vào nó trong ví dụ này.

`countQuery` được viết rõ để thể hiện việc tính tổng số bản ghi cho `Page`. Với một truy vấn đơn giản, Spring Data JPA có thể suy ra truy vấn đếm; khả năng đó không bảo đảm đúng cho mọi phép join, `distinct`, grouping hoặc SQL native.

### 5.2. Đừng nhầm truy vấn khai báo với ghép chuỗi

Giá trị do người dùng nhập cần đi qua binding tham số. Không nối email, trạng thái hay chuỗi tìm kiếm trực tiếp vào nội dung câu truy vấn.

```java
@Query("""
    select o
    from PurchaseOrder o
    where o.customerEmail = :email
    """)
List<PurchaseOrder> findForEmail(@Param("email") String email);
```

Binding truyền một giá trị theo cơ chế truy vấn. Nó không có nghĩa caller có thể truyền tên bảng, tên cột hoặc một đoạn `order by` bất kỳ vào placeholder giá trị. Với sắp xếp do người dùng lựa chọn, tầng ứng dụng nên ánh xạ các lựa chọn hợp lệ sang tên thuộc tính đã cho phép rồi tạo `Sort`.

### 5.3. SQL native là một lựa chọn riêng của JPA module

Ví dụ tối giản, trả danh sách và không phân trang:

```java
@Query(
    value = """
        select o.*
        from purchase_orders o
        where o.status = :status
        """,
    nativeQuery = true
)
List<PurchaseOrder> findUsingSql(@Param("status") String status);
```

Ví dụ giả định cột `status` lưu đúng tên enum dạng chuỗi và ánh xạ entity phù hợp với kết quả SQL. SQL dùng tên bảng/cột vật lý, còn JPQL dùng mô hình entity. Chọn SQL native đồng nghĩa phải xem xét cú pháp cơ sở dữ liệu, kiểu dữ liệu và việc ánh xạ kết quả.

Hỗ trợ phân trang, sắp xếp động và suy ra count query cho SQL native phụ thuộc khả năng phân tích truy vấn, phiên bản module và hình dạng câu SQL. Không nên chuyển một ví dụ JPQL sang `nativeQuery = true` rồi mặc định mọi hành vi vẫn giữ nguyên.

Annotation cũng không tự biến truy vấn đọc thành truy vấn cập nhật. Chẳng hạn, bulk update/delete trong Spring Data JPA có yêu cầu riêng về `@Modifying`, transaction và trạng thái persistence context. Đó là một loại thao tác khác với các ví dụ đọc trong bài.

## 6. Named query: khai báo một lần và tra cứu qua tên

### 6.1. Khai báo bằng cơ chế JPA

Named query là một truy vấn có định danh, không đơn thuần là một phương thức Java có tên dễ đọc. Ví dụ Spring Data JPA sử dụng `@NamedQuery` của Jakarta Persistence.

Đặt annotation sau lên lớp `PurchaseOrder` ở phần mô hình; những trường và mapping đã có vẫn giữ nguyên:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.NamedQuery;
import jakarta.persistence.Table;

@Entity(name = "PurchaseOrder")
@Table(name = "purchase_orders")
@NamedQuery(
    name = "PurchaseOrder.findForReview",
    query = """
        select o
        from PurchaseOrder o
        where o.status = :status
          and o.total >= :minTotal
        order by o.createdAt desc, o.id desc
        """
)
public class PurchaseOrder {
    // Giữ các trường, mapping, constructor và accessor của mô hình ở trên.
}
```

Đây là JPQL. Nếu khai báo named native query thì phải dùng cơ chế tương ứng của JPA và xử lý các yêu cầu ánh xạ SQL riêng.

Repository:

```java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, Long> {

    List<PurchaseOrder> findForReview(
            @Param("status") OrderStatus status,
            @Param("minTotal") BigDecimal minTotal);
}
```

Trong quy ước tra cứu thông thường của Spring Data JPA, tên được tìm là:

```text
<Tên lớp domain đơn giản>.<Tên phương thức repository>

PurchaseOrder.findForReview
```

Ở ví dụ này, lớp domain và entity có cùng tên nên dễ đối chiếu. Không thay tên lớp domain bằng tên bảng SQL trong định danh tra cứu. Nếu dùng tên entity tùy biến khác tên lớp, cũng cần phân biệt quy ước đặt tên named query với tên entity xuất hiện trong JPQL.

Spring Data JPA còn cho phép chỉ rõ tên truy vấn qua annotation của module:

```java
import org.springframework.data.jpa.repository.Query;

@Query(name = "PurchaseOrder.findForReview")
List<PurchaseOrder> findForReview(
        @Param("status") OrderStatus status,
        @Param("minTotal") BigDecimal minTotal);
```

`name` ở đây trỏ tới một khai báo đã tồn tại. Nó không tạo nội dung truy vấn thay cho khai báo `@NamedQuery`.

### 6.2. Chỗ đặt khai báo và phạm vi tái sử dụng

Trong JPA, named query có thể được khai báo bằng annotation trên entity hoặc bằng mapping XML được persistence unit nạp. Đó là cơ chế của JPA; những nguồn named query khác mà một module Spring Data hỗ trợ cần được xem theo module tương ứng.

Lợi ích của việc đặt tên là có thể tham chiếu cùng một khai báo từ nhiều chỗ theo cơ chế được hỗ trợ. Tuy nhiên, chuỗi tên và placeholder vẫn tạo ra một hợp đồng cần duy trì:

- Đổi tên phương thức có thể làm thay đổi tên tra cứu theo quy ước.
- Đổi tên khai báo cần cập nhật nơi tham chiếu tường minh.
- Đổi điều kiện hoặc kiểu tham số phải cập nhật mọi caller chịu ảnh hưởng.
- Named query của JPA có phạm vi theo persistence unit, nên không coi tên đó là tên riêng cục bộ của một interface repository.

Tách truy vấn khỏi repository giúp tổ chức khai báo, nhưng người đọc cần đi tới vị trí khai báo để hiểu toàn bộ hành vi. Với một câu truy vấn chỉ dùng ở một phương thức, đặt `@Query` ngay trên phương thức thường dễ theo dõi hơn.

### 6.3. Tránh đặt cùng một truy vấn ở hai nơi

Trong Spring Data JPA, chuỗi truy vấn khai báo trực tiếp bằng `@Query` trên phương thức được ưu tiên hơn named query tương ứng. Vì vậy, nếu thêm `@Query` nhưng vẫn giữ một named query cùng mục đích, việc sửa named query có thể không làm phương thức đó đổi hành vi như người bảo trì tưởng.

Đây là quy tắc của JPA module, không phải một thứ tự ưu tiên phổ quát cho mọi kho dữ liệu. Một phương thức nên có một nguồn mô tả điều kiện rõ ràng; chỉ giữ nhiều nguồn khi có lý do cụ thể và kiểm thử cho hành vi mong muốn.

## 7. Query lookup strategy: quyết định tìm khai báo hay tạo từ tên

Commons định nghĩa các lựa chọn trong `QueryLookupStrategy.Key`. Module repository quyết định việc triển khai và hỗ trợ các lựa chọn đó.

| Chiến lược | Hành vi khái niệm | Khi không tìm thấy truy vấn khai báo |
| --- | --- | --- |
| `CREATE` | Tạo truy vấn từ tên phương thức | Không dùng bước tìm khai báo làm nguồn giải quyết truy vấn; tên phải diễn đạt được truy vấn |
| `USE_DECLARED_QUERY` | Chỉ dùng truy vấn đã khai báo qua cơ chế được hỗ trợ | Thất bại thay vì chuyển sang suy diễn |
| `CREATE_IF_NOT_FOUND` | Tìm truy vấn khai báo trước, nếu không có thì tạo từ tên | Thử suy diễn; thất bại nếu tên không tạo được truy vấn hợp lệ |

Ở Spring Data JPA, `CREATE_IF_NOT_FOUND` là lựa chọn mặc định khi không cấu hình khác. Không lấy điều này để giả định mọi module và mọi cấu hình repository đều hành xử giống nhau.

Ví dụ cấu hình cho **Spring Data JPA**, với package của ứng dụng chỉ mang tính minh họa:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.data.repository.query.QueryLookupStrategy;

@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    queryLookupStrategy = QueryLookupStrategy.Key.CREATE_IF_NOT_FOUND
)
public class OrderRepositoryConfiguration {
}
```

Cấu hình này chỉ biểu đạt chiến lược của các repository được cấu hình quét ở đây; ứng dụng vẫn cần thiết lập hạ tầng JPA phù hợp. Nếu chọn `USE_DECLARED_QUERY`, những phương thức truy vấn thuộc phạm vi cấu hình phải có khai báo thích hợp. Những implementation đã được cung cấp bởi repository cơ sở hoặc fragment không biến thành derived query chỉ vì có cấu hình này.

### 7.1. Không tìm thấy khác với tìm thấy nhưng sai

Xét hai tình huống:

1. Không có named query cần tìm: `CREATE_IF_NOT_FOUND` có thể chuyển sang suy diễn tên phương thức.
2. Đã có truy vấn khai báo nhưng cú pháp, thuộc tính hoặc binding sai: không được xem fallback như cách tự bỏ qua khai báo lỗi để thử một truy vấn khác.

Fallback là chính sách lựa chọn nguồn truy vấn, không phải cơ chế phục hồi mọi lỗi truy vấn. Một số lỗi được phát hiện lúc tạo repository hoặc entity manager; một số lỗi phụ thuộc provider hoặc dữ liệu chỉ xuất hiện khi thực thi.

### 7.2. Fallback có thể che một khai báo bị thiếu

Giả sử dự định dùng named query cho phương thức:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);
```

Nhưng named query `PurchaseOrder.findByStatus` chưa được nạp. Với `CREATE_IF_NOT_FOUND`, phương thức vẫn có thể chạy bằng điều kiện suy diễn `status = ?`. Nếu named query dự định còn có một điều kiện nghiệp vụ khác, chẳng hạn `total > 0`, hành vi suy diễn không tương đương hành vi mong muốn.

Ngược lại, `findForReview(status, minTotal)` trong ví dụ named query không phải tên đã mã hóa đầy đủ điều kiện theo grammar suy diễn. Khi khai báo tương ứng bị thiếu, không có cơ sở để kỳ vọng fallback tự hiểu ý nghĩa “cần xem xét”.

Nếu yêu cầu của một nhóm repository là mọi truy vấn đều phải khai báo, `USE_DECLARED_QUERY` có thể giúp phát hiện thiếu khai báo. Quyết định này cần tính đến toàn bộ phương thức truy vấn trong phạm vi cấu hình, thay vì đổi chiến lược chỉ để chữa một phương thức đơn lẻ.

## 8. Những hợp đồng không thay đổi theo cách khai báo

### 8.1. Tham số và số lượng kết quả

Chọn derived query, `@Query` hay named query chỉ quyết định nguồn mô tả truy vấn. Kiểu trả về vẫn phải khớp số lượng kết quả và ý định của caller.

| Kiểu trả về tiêu biểu | Ý định | Điều cần kiểm tra |
| --- | --- | --- |
| `List<PurchaseOrder>` | Nhiều kết quả | Danh sách không giới hạn có thể tải lượng dữ liệu lớn |
| `Optional<PurchaseOrder>` | Không có hoặc một kết quả | Nếu dữ liệu khớp nhiều hàng, không tự chọn hàng đầu tiên |
| `Page<PurchaseOrder>` | Một trang và metadata tổng số | Có thể cần thêm truy vấn đếm |
| `Slice<PurchaseOrder>` | Một lát và thông tin còn lát tiếp hay không | Không cung cấp tổng số như `Page`; thường lấy thêm phần tử để xác định còn dữ liệu |
| `boolean` với truy vấn tồn tại | Chỉ cần biết có hay không | Cần chọn dạng truy vấn mà module hỗ trợ đúng ý định này |

`Optional` không áp đặt uniqueness lên cơ sở dữ liệu. Nếu email phải duy nhất theo nghiệp vụ, cần một ràng buộc thích hợp hoặc thiết kế dữ liệu bảo đảm điều đó. Khi mục tiêu thật sự là lấy đơn mới nhất, hãy diễn đạt giới hạn và thứ tự một cách tường minh, chẳng hạn một derived query dạng `findFirstBy...OrderBy...` được module hỗ trợ.

### 8.2. Phân trang và sắp xếp

`Pageable` đã chứa cả thông tin trang lẫn `Sort`. Không thiết kế một phương thức đồng thời nhận `Pageable` và một tham số `Sort` riêng để điều khiển cùng truy vấn.

Với truy vấn join quan hệ một-nhiều, một entity gốc có thể tạo nhiều dòng trung gian. Vì vậy:

- Kích thước kết quả không phải lúc nào cũng đồng nhất với số entity gốc theo cách đếm đơn giản.
- Count query phải đếm đúng đơn vị nghiệp vụ cần hiển thị.
- `distinct`, fetch join và phân trang có các tương tác riêng cần đánh giá theo module/provider.

Chuyển một phương thức từ derived query sang truy vấn viết tay không được làm mất bộ lọc ở count query hoặc thay đổi thứ tự trang ngoài ý định.

### 8.3. Projection và auditing vẫn là những vấn đề riêng

Thay entity bằng projection thay đổi hình dạng kết quả mà repository phải ánh xạ. Với truy vấn viết tay, cần bảo đảm cột, alias hoặc biểu thức constructor phù hợp kiểu projection và cơ chế ánh xạ của module; annotation không tự làm mọi kết quả trở nên tương thích với mọi projection.

Auditing ghi metadata như người tạo hoặc thời điểm tạo khi hạ tầng và mapping được cấu hình thích hợp. Nó không tự thêm điều kiện lọc người dùng, tenant, quyền truy cập hay trạng thái xóa mềm vào mọi truy vấn. Nếu một điều kiện như vậy là bắt buộc, phải thể hiện hoặc cấu hình nó bằng cơ chế có hiệu lực với loại truy vấn đang dùng.

## 9. Chọn cách khai báo theo tình huống

| Tình huống | Điểm bắt đầu hợp lý | Lý do |
| --- | --- | --- |
| Tìm theo email hoặc trạng thái với ít điều kiện | Derived query | Tên ngắn, đọc được trực tiếp |
| Điều kiện có nhóm logic hoặc join cần viết rõ | Annotation truy vấn của module | Câu truy vấn nằm cạnh hợp đồng phương thức |
| Hệ thống JPA đã quản lý truy vấn theo tên trong entity/XML | Named query | Phù hợp cách quản lý khai báo sẵn có |
| Nhiều nơi cần tham chiếu một khai báo JPA theo tên | Named query | Có định danh chung để tham chiếu và bảo trì |
| Bộ lọc động có nhiều tổ hợp tùy chọn | API dựng truy vấn hoặc fragment được module hỗ trợ | Tránh bùng nổ tên phương thức và chuỗi điều kiện khó bảo trì |
| Cần cú pháp đặc thù cơ sở dữ liệu | Cơ chế truy vấn native của module | Cho phép thể hiện yêu cầu đặc thù, đồng thời phải xử lý tính phụ thuộc kho dữ liệu |
| Nhóm repository bắt buộc có khai báo truy vấn | Xem xét `USE_DECLARED_QUERY` trong phạm vi phù hợp | Thiếu khai báo cần bị phát hiện, không tự suy diễn sang hành vi khác |

Không có cơ sở để kết luận named query luôn nhanh hơn `@Query`, hoặc derived query luôn tạo truy vấn kém hơn viết tay. Chi phí thực tế đến từ truy vấn được tạo, dữ liệu, chỉ mục, cách tải quan hệ, số lượt truy cập và kế hoạch thực thi của hệ quản trị. Cách khai báo là một quyết định về diễn đạt và quản lý truy vấn; hiệu năng phải được đánh giá trên truy vấn thực tế.

## 10. Các lỗi dễ gặp và hướng kiểm tra

| Biểu hiện | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy thuộc tính trong derived query | Gõ sai hoặc dùng tên cột SQL trong tên phương thức | So với thuộc tính Java và đường dẫn thuộc tính thực tế |
| `@Query` không có tác dụng như dự kiến | Import annotation không thuộc module đang dùng | Xem đầy đủ package import và loại repository |
| JPQL báo entity hoặc thuộc tính không tồn tại | Dùng tên bảng/cột vật lý trong JPQL | Phân biệt `PurchaseOrder.createdAt` với `purchase_orders.created_at` |
| Tham số không được bind | Placeholder và `@Param` lệch tên hoặc thiếu đối số | Đối chiếu từng placeholder với chữ ký phương thức |
| Named query không được tìm thấy | Sai tên, sai quy ước hoặc khai báo chưa được persistence unit nạp | Đối chiếu tên domain, tên phương thức và nguồn khai báo |
| Thêm named query nhưng hành vi không đổi | Có `@Query` trực tiếp đang được ưu tiên trong JPA | Xác định nguồn truy vấn thực sự được sử dụng |
| Repository vẫn chạy dù thiếu named query | `CREATE_IF_NOT_FOUND` suy diễn thành công | Kiểm tra chiến lược tra cứu và tính tương đương của điều kiện |
| `Page` có tổng số sai | Count query thiếu điều kiện hoặc đếm sai do join | So sánh bộ lọc và đơn vị đếm với truy vấn lấy dữ liệu |
| Truy vấn dự kiến một kết quả nhưng bị lỗi | Dữ liệu thực tế khớp nhiều hàng | Xem lại uniqueness hoặc cách giới hạn có thứ tự |

Cách cô lập vấn đề nên đi từ hợp đồng của phương thức: đang dùng module nào, truy vấn lấy từ nguồn nào, tham số nào được bind, kỳ vọng bao nhiêu kết quả và framework thực sự gửi gì tới kho dữ liệu. Chỉ đọc tên phương thức sẽ không đủ để chẩn đoán một phương thức có khai báo riêng.

## 11. Bài tập thực hành

### Bài 1: Chọn cách biểu đạt

Với từng yêu cầu, chọn một điểm bắt đầu và giải thích:

1. Tìm đơn hàng theo `customerEmail`, không phân biệt hoa thường.
2. Tìm đơn có trạng thái `PAID`, tổng tiền từ một ngưỡng cho trước, đồng thời thỏa `(email = :email OR createdAt >= :since)`.
3. Một persistence unit JPA đã có truy vấn `PurchaseOrder.findForReview`; cần đưa truy vấn này qua repository.

Gợi ý đáp án:

- Yêu cầu 1 phù hợp với `findByCustomerEmailIgnoreCase`, sau khi xác nhận ngữ nghĩa so sánh và khả năng hỗ trợ của module.
- Yêu cầu 2 nên thể hiện rõ dấu ngoặc bằng truy vấn khai báo hoặc một API dựng điều kiện phù hợp. Nếu dùng JPQL, `OrderStatus.PAID` có thể được truyền thành tham số enum thay vì ghép chuỗi.
- Yêu cầu 3 phù hợp với named query theo quy ước hoặc một tham chiếu tên tường minh. Cần giữ đúng hợp đồng tham số của khai báo hiện có.

### Bài 2: Dự đoán chiến lược tra cứu

Giả sử một phương thức truy vấn không có implementation riêng và module hỗ trợ cả ba chiến lược. Điền kết quả cho các trường hợp sau:

| Tình huống | Kết quả cần dự đoán |
| --- | --- |
| `CREATE`, tên phương thức suy diễn hợp lệ | Tạo truy vấn từ tên |
| `USE_DECLARED_QUERY`, không có khai báo | Thất bại khi phân giải truy vấn |
| `CREATE_IF_NOT_FOUND`, không có khai báo nhưng tên hợp lệ | Chuyển sang tạo từ tên |
| `CREATE_IF_NOT_FOUND`, tìm thấy khai báo có lỗi | Không xem fallback là cơ chế bỏ qua lỗi khai báo |
| `CREATE_IF_NOT_FOUND`, thiếu khai báo và tên không suy diễn được | Thất bại; framework không hiểu ý nghiệp vụ từ tên tự do |

### Bài 3: Xác định hành vi cần kiểm thử khi chuyển cách khai báo

Chuyển phương thức suy diễn theo trạng thái và thời điểm tạo ở phần 4 sang `@Query` ở phần 5. Khi tích hợp vào một ứng dụng JPA, các kiểm thử có ý nghĩa cần chứng minh:

1. Đơn khác trạng thái không lọt vào kết quả.
2. Đơn có `createdAt` bằng đúng `since` được lấy, đơn sớm hơn thì không.
3. Thứ tự theo `createdAt`, rồi `id`, vẫn đúng khi nhiều đơn trùng thời điểm.
4. `totalElements` phản ánh cùng bộ lọc với nội dung trang.
5. Một trang không có kết quả trả nội dung rỗng và metadata phù hợp.

Nếu hệ thống chọn named query để thêm điều kiện nghiệp vụ, cần thêm trường hợp chứng minh điều kiện riêng đó thật sự được áp dụng. Chỉ kiểm tra repository khởi tạo thành công không đủ để phát hiện một fallback hợp lệ về kỹ thuật nhưng sai ý định.

## 12. Các điểm cần nhớ

- Derived query diễn đạt truy vấn qua tên phương thức; sự hỗ trợ toán tử vẫn thuộc module lưu trữ cụ thể.
- Annotation truy vấn đặt nội dung gần phương thức; cần dùng đúng annotation và ngôn ngữ của module.
- Named query dùng một định danh để tra cứu khai báo; tên, tham số và nguồn nạp khai báo là một phần của hợp đồng.
- `CREATE`, `USE_DECLARED_QUERY` và `CREATE_IF_NOT_FOUND` quyết định cách tìm nguồn truy vấn, không tự sửa một khai báo sai.
- Phân trang, sắp xếp, cardinality, projection và các điều kiện nghiệp vụ bắt buộc phải giữ đúng khi thay đổi cách khai báo.
- Commons cung cấp nền tảng chung; JPQL, named query JPA và khả năng native là những chi tiết phải xét theo module và kho dữ liệu thực tế.
