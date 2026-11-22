# Phân biệt API truy vấn thuận tiện với chi phí truy cập thực tế

## 1. Một dòng API có thể thực hiện bao nhiêu công việc?

Trong một ứng dụng Java, lập trình viên có thể đọc danh sách đơn hàng bằng một lời gọi ngắn:

~~~java
List<OrderEntity> orders = orderRepository.findAll();
~~~

Cú pháp này dễ hiểu và thuận tiện, nhưng **một dòng Java không đồng nghĩa với một thao tác rẻ**. Đằng sau lời gọi có thể là truy vấn SQL, truyền dữ liệu qua mạng, đọc trang dữ liệu và chỉ mục, tạo hàng nghìn entity, quản lý persistence context, rồi tiếp tục phát sinh truy vấn khi mã truy cập quan hệ lười tải (lazy relationship).

Ngược lại, một câu SQL dài với bộ lọc chính xác, phép chiếu (projection) vừa đủ và chỉ mục phù hợp có thể thực hiện ít công việc hơn một API ngắn trả toàn bộ bảng.

Bài này nằm trong chương **Truy vấn và phân trang** của học phần **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu của học phần là hiểu lưu trữ dữ liệu bền vững và thiết kế ranh giới persistence cho Java, từ lược đồ, truy vấn, chỉ mục đến giao dịch, cô lập, kiểm soát đồng thời và hiệu năng. Ở đây, trọng tâm là **phân biệt sự tiện lợi ở giao diện lập trình với chi phí truy cập dữ liệu thực sự**.

Sau bài học, người học có thể:

1. Nhìn một lời gọi JDBC, JPA hoặc Spring Data và xác định những thao tác dữ liệu *có thể* xảy ra.
2. Tách chi phí **số lượt gọi database**, **số hàng đọc/trả**, **số byte truyền**, **bộ nhớ Java** và **công việc của database**.
3. Nhận biết N+1, tải thừa cột, lọc trong bộ nhớ, đếm trang ngoài ý muốn và JOIN làm nhân hàng.
4. Chọn đúng API cho các nhu cầu đọc một bản ghi, danh sách nhỏ, danh sách phân trang, kiểm tra tồn tại và xử lý tập lớn.
5. Đọc SQL do ORM tạo ra, sử dụng **EXPLAIN (ANALYZE, BUFFERS)** và chỉ số vận hành để kiểm chứng giả thuyết.
6. Đề xuất cách sửa có thể đo lường, đồng thời giữ đúng tính nhất quán, quyền truy cập và ngữ nghĩa nghiệp vụ.

## 2. Ví dụ xuyên suốt: màn hình đơn hàng

Một hệ thống có bảng **purchase_order**, **customer** và **order_item**. Mỗi đơn thuộc một khách hàng và có thể có nhiều dòng sản phẩm. Màn hình quản lý chỉ cần hiển thị 20 đơn đã thanh toán gần nhất của một tenant, mỗi dòng gồm mã đơn, tên khách, tổng tiền và ngày tạo.

Lược đồ PostgreSQL giản lược:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    full_name   VARCHAR(200) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    UNIQUE (tenant_id, customer_id)
);

CREATE TABLE purchase_order (
    order_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(20) NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    internal_note TEXT,
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customer(tenant_id, customer_id)
);

CREATE TABLE order_item (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id      BIGINT NOT NULL REFERENCES purchase_order(order_id),
    product_code  VARCHAR(64) NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Đây là lược đồ phục vụ minh họa; hệ thống thực tế cần thêm kiểm tra trạng thái, số tiền, chính sách xóa và ràng buộc tenant thích hợp. Những ví dụ trong bài giả định **order_id** là khóa duy nhất toàn cục do database sinh, còn **tenant_id** luôn được xác định từ danh tính đã được ủy quyền.

Yêu cầu màn hình có thể diễn đạt thành SQL:

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.total_amount,
    o.created_at
FROM purchase_order AS o
JOIN customer AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = ?
  AND o.status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

Câu SQL này cho database biết chính xác cần **lọc hàng**, **nối dữ liệu**, **sắp xếp** và **trả tối đa 20 bản ghi**. Với chỉ mục và phân bố dữ liệu phù hợp, database có thể thực thi hiệu quả. Tuy nhiên, từ câu SQL đơn thuần cũng chưa thể kết luận nhanh hay chậm: cần xem kế hoạch thực thi và dữ liệu thực.

## 3. Những lớp chi phí ẩn phía sau API

Một lời gọi repository có thể đi qua nhiều bước:

~~~mermaid
flowchart LR
    API["API / Service Java"] --> ORM["ORM hoặc JDBC"]
    ORM --> DRIVER["Driver / Connection"]
    DRIVER --> DB["Database Executor"]
    DB --> STORAGE["Bảng / Chỉ mục / Bộ nhớ đệm"]
    DB --> DRIVER
    DRIVER --> MAP["Ánh xạ DTO / Entity"]
    MAP --> RESPONSE["JSON / Kết quả API"]
~~~

Các loại chi phí cần phân biệt:

| Loại chi phí | Câu hỏi cần hỏi | Dấu hiệu đo lường |
| --- | --- | --- |
| **Round-trip** | Mỗi thao tác cần bao nhiêu lượt đi và về tới DB? | Số statement, số lần gửi lệnh, độ trễ mạng |
| **DB CPU** | DB phải lọc, nối, gom nhóm hoặc sắp xếp bao nhiêu? | Thời gian truy vấn, plan nodes, CPU |
| **I/O và bộ nhớ đệm** | DB phải đọc bao nhiêu trang/buffer? | EXPLAIN BUFFERS, cache hit, disk reads |
| **Số hàng xét** | Database cần quét bao nhiêu hàng trước khi có kết quả? | Actual rows, rows removed by filter |
| **Số hàng trả về** | Bao nhiêu bản ghi đi qua driver? | Row count, result size |
| **Kích thước mỗi hàng** | Có đọc các cột lớn hoặc nhạy cảm không cần thiết không? | Byte truyền, độ rộng hàng |
| **Ánh xạ Java** | Bao nhiêu đối tượng/collection được tạo? | Allocation, heap, GC |
| **Vòng đời tài nguyên** | Query/cursor/transaction giữ connection bao lâu? | Connection pool wait, active sessions |
| **Tác động đồng thời** | Truy vấn có khóa hoặc giữ snapshot lâu không? | Wait events, lock waits, long transactions |

**Độ dài câu SQL**, **số dòng mã Java** và **tên hàm repository** không trực tiếp cho biết các chi phí này. Chẳng hạn, một lời gọi có thể tạo **1 SQL query trả 200.000 hàng**, trong khi ba truy vấn nhỏ có thể đọc ít hơn rất nhiều. Cần xem cả số lượt gọi lẫn khối lượng công việc của từng lượt.

### 3.1. Chi phí đầu cuối không chỉ là thời gian chạy trong DB

Thời gian API phản hồi có thể được chia theo cách gần đúng:

~~~text
Tổng thời gian ≈ chờ connection
              + round-trip tới DB
              + thực thi và đọc dữ liệu tại DB
              + truyền kết quả qua mạng
              + ánh xạ Java
              + xử lý nghiệp vụ và tuần tự hóa JSON
~~~

Đây là mô hình phân tích, không phải công thức đo chính xác vì một số công đoạn có thể chồng lấn, đệm hoặc chạy bất đồng bộ. Vì vậy, **EXPLAIN** nhanh không chứng minh endpoint nhanh: endpoint còn có thể tải thêm quan hệ, serialize dữ liệu lớn hoặc chờ connection pool.

## 4. API thuận tiện thứ nhất: findAll() và lọc ở Java

Giả sử người lập trình viết:

~~~java
List<OrderEntity> paidOrders = orderRepository.findAll()
    .stream()
    .filter(o -> o.getTenantId().equals(authorizedTenantId))
    .filter(o -> o.getStatus() == OrderStatus.PAID)
    .sorted(
        Comparator.comparing(OrderEntity::getCreatedAt)
            .thenComparing(OrderEntity::getId)
            .reversed()
    )
    .limit(20)
    .toList();
~~~

Đoạn mã tạo cảm giác “lọc, sort, lấy 20” ngay trong Java. Nhưng **findAll() đã lấy các entity từ kho lưu trữ trước khi stream Java chạy**. Nếu bảng chứa 1 triệu đơn, ứng dụng có thể đã tải một lượng dữ liệu rất lớn để cuối cùng chỉ giữ 20.

Các hệ quả có thể gồm:

- Truyền nhiều hàng và cột qua mạng.
- Tạo nhiều entity, tăng heap và hoạt động của garbage collector.
- Persistence context quản lý nhiều object nếu đang trong phiên JPA.
- Thời gian endpoint và connection bị kéo dài.
- Dễ đọc dữ liệu của tenant khác vào bộ nhớ ứng dụng dù sau đó filter lại; đây là vấn đề về ranh giới bảo mật, không chỉ hiệu năng.

Giải pháp phù hợp cho use case là **đẩy lọc, sắp xếp và giới hạn xuống truy vấn**:

~~~sql
SELECT order_id, total_amount, created_at
FROM purchase_order
WHERE tenant_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Nếu cần tên khách, thêm JOIN có điều kiện tenant như ví dụ ở phần 2 và chỉ chọn những cột cần hiển thị.

**Ngoại lệ có thể chấp nhận:** khi tập dữ liệu đã được giới hạn nhỏ, ở trong bộ nhớ hợp lý, hoặc một bộ lọc đơn giản chỉ áp dụng trên kết quả 20 hàng đã lấy từ DB, stream Java có thể hoàn toàn phù hợp. Vấn đề là xác định **tập dữ liệu được tải trước khi stream chạy**.

## 5. API thuận tiện thứ hai: entity giàu quan hệ và lỗi N+1

### 5.1. Lazy loading giúp hoãn đọc, không làm chi phí biến mất

Giả sử một entity có quan hệ:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_order")
public class OrderEntity {
    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private CustomerEntity customer;

    // status, totalAmount, createdAt và các accessor được lược bỏ.
}
~~~

Đây là ví dụ rút gọn về cách ánh xạ; ứng dụng phải định nghĩa **CustomerEntity** tương ứng và cấu hình ranh giới tenant phù hợp. **FetchType.LAZY** biểu thị ý định trì hoãn lấy quan hệ theo khả năng của provider; nó không phải cam kết rằng sẽ không có truy vấn bổ sung.

Một đoạn xử lý:

~~~java
List<OrderEntity> orders = repository.findTop20ByTenantIdOrderByIdDesc(tenantId);

for (OrderEntity order : orders) {
    String name = order.getCustomer().getFullName();
    // Ghi tên khách vào DTO.
}
~~~

có thể khiến ORM phát:

~~~text
1 query đọc danh sách 20 đơn
+ nhiều query đọc khách hàng khi truy cập getCustomer()
= tình huống N+1 (hoặc gần N+1)
~~~

Số query bổ sung thực tế phụ thuộc cache cấp một/cấp hai, các đơn có chung khách hay không, batch fetching và fetch plan. Không được mặc định chính xác **21 truy vấn** cho mọi dữ liệu; điều cần nhận diện là **số lần lấy quan hệ có thể tăng theo số hàng cha**.

### 5.2. Những cách xử lý N+1

| Cách | Phù hợp khi | Điểm cần kiểm tra |
| --- | --- | --- |
| **DTO projection + JOIN** | Danh sách chỉ hiển thị vài trường từ hai bảng | Số hàng kết quả, chọn cột vừa đủ |
| **JOIN FETCH / EntityGraph** | Cần entity và một số quan hệ khi dùng ORM | Có nhân hàng không? Có tương thích phân trang không? |
| **Batch fetching** | Nhiều quan hệ lazy cần tải theo cụm | Số query thực tế, kích thước batch và bộ nhớ |
| **Đọc IDs rồi lấy liên quan theo lô** | Muốn quản lý riêng hai bước | Phải bảo đảm ghép đúng định danh và thứ tự |

Ví dụ SQL projection cho danh sách:

~~~sql
SELECT o.order_id, c.full_name, o.total_amount
FROM purchase_order AS o
JOIN customer AS c
  ON c.customer_id = o.customer_id
 AND c.tenant_id = o.tenant_id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

JOIN từ nhiều đơn tới **một khách** thường trả một hàng cho mỗi đơn khi FK hợp lệ. Tuy nhiên, **JOIN từ đơn tới collection order_item** sẽ nhân hàng theo số dòng chi tiết và cần phân tích khác.

### 5.3. Không nên sửa N+1 bằng cách tải mọi collection

Nếu một đơn có 10 dòng hàng, một khách có 5 địa chỉ, truy vấn JOIN FETCH cả hai collection có thể tạo số hàng trung gian lớn hơn nhiều so với số đơn gốc. Phân trang entity có collection fetch join đôi khi còn khiến ORM phân trang trong bộ nhớ hoặc cảnh báo tùy provider/cấu hình.

Chọn fetch plan theo **dữ liệu thực sự cần cho use case**. Màn hình chỉ đọc 20 đơn và tên khách không cần tự động tải toàn bộ dòng hàng, lịch sử trạng thái hoặc địa chỉ.

## 6. API thuận tiện thứ ba: Page có thể cần truy vấn COUNT

Trong Spring Data JPA, một repository có thể khai báo:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {
    Page<OrderEntity> findByTenantIdAndStatus(
        Long tenantId,
        OrderStatus status,
        Pageable pageable
    );
}
~~~

**Page<T>** thường phù hợp màn hình cần **tổng số bản ghi** và **tổng số trang**. Để cung cấp thông tin đó, framework **có thể thực thi thêm truy vấn COUNT** bên cạnh truy vấn lấy dữ liệu. Một số trường hợp có thể suy ra số lượng mà không cần COUNT tùy cách triển khai và tình huống; phải quan sát SQL thực tế.

Ví dụ hai câu SQL tương ứng về ý nghĩa:

~~~sql
-- Dữ liệu trang hiện tại
SELECT order_id, status, created_at, total_amount
FROM purchase_order
WHERE tenant_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;

-- Đếm mọi hàng thỏa bộ lọc
SELECT COUNT(*)
FROM purchase_order
WHERE tenant_id = ?
  AND status = 'PAID';
~~~

Một câu COUNT nhìn ngắn nhưng có thể phải xử lý rất nhiều hàng hoặc điều kiện JOIN phức tạp. Có chỉ mục phù hợp cũng không bảo đảm COUNT luôn là thao tác hằng số hay miễn phí.

### 6.1. Khi nào dùng Slice thay vì Page?

Nếu màn hình chỉ có nút **“Xem thêm”** và không cần tổng số trang, **Slice<T>** có thể phù hợp hơn:

~~~java
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Pageable;

Slice<OrderEntity> findSliceByTenantIdAndStatus(
    Long tenantId,
    OrderStatus status,
    Pageable pageable
);
~~~

Đây là minh họa về hình dạng phương thức trong Spring Data repository. **Slice** tập trung vào dữ liệu của đoạn hiện tại và thông tin còn trang tiếp, thường có thể lấy thêm một hàng để xác định **hasNext** mà không cần COUNT tổng. Hành vi SQL chi tiết tùy phiên bản và cách khai báo truy vấn.

| Nhu cầu UI | API gợi ý | Chi phí cần cân nhắc |
| --- | --- | --- |
| Hiển thị “Trang 3 / 120” | Page<T> | Có thể cần COUNT |
| Chỉ hiển thị “Xem thêm” | Slice<T> hoặc cursor riêng | Thường tránh COUNT tổng |
| Cuộn danh sách rất dài | Keyset/cursor | Cần khóa sort và điều kiện seek |
| Lấy tối đa 20 bản ghi cố định | List<T> có LIMIT | Không cần thông tin tổng số |

**Lưu ý:** chọn Slice không tự động biến truy vấn OFFSET sâu thành keyset. Nếu Pageable vẫn được thực thi bằng LIMIT/OFFSET, các nhược điểm OFFSET vẫn còn.

### 6.2. COUNT cũng có thể sai nghĩa vì JOIN

Giả sử mỗi đơn có nhiều dòng hàng. Câu:

~~~sql
SELECT COUNT(*)
FROM purchase_order AS o
JOIN order_item AS i ON i.order_id = o.order_id
WHERE o.tenant_id = ?;
~~~

đếm **số hàng sau JOIN**, thường là số dòng đơn hàng thỏa điều kiện, không phải số đơn phân biệt. Để đếm đơn có ít nhất một dòng, có thể dùng **EXISTS** hoặc **COUNT(DISTINCT o.order_id)** tùy ý nghĩa; mỗi cách có kế hoạch và chi phí khác nhau.

Khi một API Page dùng truy vấn JOIN tùy biến, cần kiểm tra **countQuery** và dữ liệu có đúng cùng bộ lọc hay không, không chỉ kiểm tra danh sách trang.

## 7. API thuận tiện thứ tư: đọc một bản ghi và kiểm tra tồn tại

### 7.1. findById không bảo đảm mỗi lần gọi đều tốn như nhau

Với JPA, **findById(id)** của repository thường dựa trên việc tìm theo khóa chính. Nếu entity đã nằm trong persistence context, có thể không cần SELECT mới; nếu chưa có, provider thường phải truy cập database. Cache, mapping và cấu hình provider ảnh hưởng số query thực tế.

Tương tự, một phương thức **getReferenceById(id)** có thể nhận về proxy/reference chưa khởi tạo đầy đủ. Khi truy cập thuộc tính không phải định danh, ORM có thể phải SELECT; trong một số trường hợp nó sẽ báo lỗi vì entity không tồn tại. **Lấy reference không đồng nghĩa đã tải và xác minh dữ liệu tồn tại.**

Vì vậy, khi review code cần xem **đoạn sử dụng giá trị trả về**, không dừng ở tên phương thức đầu tiên.

### 7.2. EXISTS thường hợp mục tiêu hơn việc tải entity

Nếu nghiệp vụ chỉ hỏi “Đơn này có tồn tại trong tenant của người gọi không?”, không nhất thiết tải toàn bộ entity:

~~~sql
SELECT EXISTS (
    SELECT 1
    FROM purchase_order
    WHERE tenant_id = ?
      AND order_id = ?
) AS present;
~~~

So sánh:

~~~java
// Có thể tải một entity chỉ để kiểm tra nó có tồn tại.
boolean present = repository.findById(orderId).isPresent();
~~~

Trong hệ thống đa tenant, **findById(orderId)** riêng lẻ còn thiếu điều kiện quyền; cần dùng query phù hợp với **authorizedTenantId**. Việc chọn EXISTS có thể giúp DB dừng sau khi thấy hàng phù hợp và tránh ánh xạ entity, nhưng hiệu năng vẫn cần được đo.

Trường hợp cần **chính bản ghi** ngay sau đó, đọc entity một lần có thể hợp lý hơn thực hiện EXISTS rồi SELECT lần nữa. Không tối ưu từng lời gọi riêng lẻ mà bỏ qua luồng nghiệp vụ tổng thể.

### 7.3. Đọc trước rồi ghi: số query và kiểm soát đồng thời

Một quy trình:

~~~text
SELECT xem mã đặt chỗ có tồn tại?
Nếu chưa, INSERT mã đặt chỗ mới.
~~~

không tự bảo đảm duy nhất dưới ghi đồng thời. Hai giao dịch có thể đều thấy “chưa tồn tại” rồi cùng INSERT. Cần **UNIQUE constraint** và xử lý xung đột phù hợp; một lệnh INSERT có kiểm soát lỗi có thể loại bỏ lượt đọc trước vốn không đủ an toàn.

Tối ưu hiệu năng của persistence phải giữ nguyên **tính đúng đắn giao dịch**, không chỉ giảm số statement.

## 8. Projection: một entity giàu dữ liệu và một DTO nhỏ khác chi phí ra sao?

Một entity thường chứa nhiều cột và quan hệ để phục vụ nhiều thao tác. Màn hình danh sách có thể chỉ cần mã đơn, tổng tiền và thời gian.

~~~sql
-- Tải toàn bộ cột của đơn:
SELECT *
FROM purchase_order
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

-- Chỉ tải dữ liệu phục vụ danh sách:
SELECT order_id, total_amount, created_at
FROM purchase_order
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Câu thứ hai không yêu cầu trả **internal_note**, có thể giảm lượng dữ liệu truyền, ánh xạ và nguy cơ lộ trường nhạy cảm qua DTO/log. Tùy chỉ mục, nó cũng có thể hỗ trợ kế hoạch đọc thuận lợi hơn.

Một DTO Java:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderListItem(
    long orderId,
    BigDecimal totalAmount,
    Instant createdAt
) {}
~~~

Mã repository có thể ánh xạ trực tiếp từng hàng vào DTO thay vì luôn tạo entity có đầy đủ trạng thái managed. Trong JPA có thể sử dụng **constructor projection**, interface-based projection của framework hoặc các query DTO phù hợp.

### 8.1. Projection không tự bảo đảm query nhẹ

Một câu SQL chỉ chọn ba cột vẫn có thể phải:

- Đọc và lọc hàng triệu hàng vì WHERE thiếu chỉ mục.
- Sắp xếp một tập lớn để lấy 20 hàng đầu.
- Thực thi JOIN nhiều bảng.
- Gọi một biểu thức hoặc hàm đắt tiền cho mỗi hàng.
- Đọc các trang bảng vì điều kiện MVCC chưa cho phép index-only scan.

Do đó **chọn ít cột là một tối ưu có mục đích**, nhưng vẫn phải kiểm tra kế hoạch thực thi. Không thể suy ra từ số cột rằng query luôn nhanh.

### 8.2. Vì sao SELECT * có thể phá hợp đồng API?

Nếu thêm cột mới vào bảng hoặc có cột chứa dữ liệu nhạy cảm, **SELECT \*** có thể đưa dữ liệu mới vào các tầng không được thiết kế để xử lý nó. Với JOIN, hai bảng có thể có cột cùng tên làm mapper nhận nhầm giá trị nếu không dùng alias.

Ở ranh giới persistence, một danh sách SELECT tường minh và DTO riêng cho use case giúp giảm phụ thuộc vào thay đổi schema và dễ kiểm soát quyền đọc theo vai trò.

## 9. JOIN và kích thước kết quả thực tế

Một truy vấn JOIN không chỉ có chi phí tính toán; nó còn có thể làm tăng **số hàng kết quả**.

Giả sử một trang có 20 đơn, mỗi đơn chứa 5 dòng order_item:

~~~sql
SELECT o.order_id, o.created_at, i.product_code
FROM purchase_order AS o
JOIN order_item AS i ON i.order_id = o.order_id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

**LIMIT 20** ở câu truy vấn này giới hạn tối đa **20 hàng sau JOIN**, không phải 20 đơn riêng biệt. Nếu mỗi đơn có 5 dòng, 20 hàng JOIN có thể chỉ chứa vài đơn. Đây là sai khác về **ngữ nghĩa phân trang**, không chỉ là hiệu năng.

Muốn phân trang 20 đơn trước rồi lấy chi tiết sau, có thể áp dụng cách hai bước:

~~~sql
-- Bước 1: chọn 20 đơn theo thứ tự xác định.
SELECT order_id, created_at
FROM purchase_order
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

-- Bước 2: lấy các dòng của những order_id đã chọn
-- (ứng dụng truyền danh sách ID an toàn qua tham số/array).
SELECT order_id, product_code, quantity
FROM order_item
WHERE order_id = ANY (?);
~~~

Ví dụ **ANY(?)** dành cho PostgreSQL với tham số được bind dưới dạng SQL array phù hợp; nó không phải cú pháp JDBC thuần tự động chấp nhận **List<Long>**. Khi triển khai, cần tạo **java.sql.Array** hoặc sử dụng cơ chế bind của framework/driver.

Cũng có thể dùng CTE để chọn đơn trước rồi JOIN, nhưng cần phân biệt **giới hạn trên hàng cha** và **giới hạn trên hàng kết quả**.

### 9.1. JOIN có thể làm phình dữ liệu ở các quan hệ độc lập

Một khách hàng có 3 địa chỉ và 5 đơn hàng; JOIN đồng thời cả hai collection có thể tạo **3 × 5 = 15 hàng** cho một khách. Nếu truy vấn còn thêm chi tiết của từng đơn, số hàng trung gian có thể tăng hơn nữa.

Khi màn hình chỉ cần số lượng địa chỉ và số đơn, có thể tính tổng hợp riêng, dùng subquery hoặc DTO phù hợp thay vì tải toàn bộ tích tổ hợp rồi gom trong Java.

## 10. OFFSET và keyset: API phân trang có cùng kiểu trả về nhưng chi phí khác

### 10.1. OFFSET dễ dùng

~~~sql
SELECT order_id, created_at, total_amount
FROM purchase_order
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 10000;
~~~

Với OFFSET lớn, database có thể phải đọc và bỏ qua rất nhiều hàng trước khi trả 20 hàng cuối. Chỉ số **pageNumber = 501** ở Java trông không đắt hơn **pageNumber = 2**, nhưng công việc tại DB có thể chênh lệch đáng kể tùy kế hoạch thực thi.

Bên cạnh hiệu năng, khi có INSERT/DELETE giữa các request, vị trí offset dịch chuyển khiến cùng bản ghi có thể xuất hiện lặp hoặc bị bỏ sót giữa các trang.

### 10.2. Keyset tiếp tục sau khóa của hàng cuối

Với thứ tự:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

truy vấn trang tiếp theo dùng cursor của hàng cuối trang trước:

~~~sql
SELECT order_id, created_at, total_amount
FROM purchase_order
WHERE tenant_id = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Trong PostgreSQL, hai cột được khai báo NOT NULL nên so sánh tuple trên phản ánh thứ tự DESC/DESC. **Cursor phải chứa cả created_at và order_id** vì nhiều hàng có thể cùng thời điểm. Khi dùng ASC hoặc chiều hỗn hợp, điều kiện seek phải đổi tương ứng; không được chỉ đổi ORDER BY.

Keyset thường hữu ích khi người dùng cuộn từ đầu tới cuối tập lớn. Đổi lại, nó không phù hợp tự nhiên với việc nhảy thẳng tới trang thứ 501 nếu không có thông tin bổ sung, và cần quản lý cursor, bộ lọc, sort cũng như quyền truy cập.

**Keyset không tự tạo snapshot bất biến** qua nhiều request; bản ghi mới hoặc cập nhật giá trị sort vẫn có thể ảnh hưởng kết quả. Nếu nghiệp vụ cần xuất báo cáo theo một thời điểm cố định, phải thiết kế snapshot hoặc phiên bản dữ liệu phù hợp.

## 11. JDBC: một ví dụ đọc đúng dữ liệu cần, tài nguyên cần

Đoạn mã sau dùng **Java 17+**, PostgreSQL và driver pgJDBC. Nó đọc tối đa **pageSize** đơn đã thanh toán của tenant được phép, chỉ trả ba trường. Cột **created_at** là **TIMESTAMPTZ**, được đọc thành **OffsetDateTime** rồi chuyển sang **Instant**.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class OrderListingQuery {
    public record OrderRow(long id, java.math.BigDecimal amount, Instant createdAt) {}

    public List<OrderRow> listPaid(
            Connection connection,
            long authorizedTenantId,
            int pageSize
    ) throws SQLException {
        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("pageSize must be 1..100");
        }

        String sql = """
            SELECT order_id, total_amount, created_at
            FROM purchase_order
            WHERE tenant_id = ?
              AND status = 'PAID'
            ORDER BY created_at DESC, order_id DESC
            LIMIT ?
            """;

        List<OrderRow> rows = new ArrayList<>();

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, authorizedTenantId);
            ps.setInt(2, pageSize);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    OffsetDateTime createdAt =
                            rs.getObject("created_at", OffsetDateTime.class);
                    rows.add(new OrderRow(
                        rs.getLong("order_id"),
                        rs.getBigDecimal("total_amount"),
                        createdAt.toInstant()
                    ));
                }
            }
        }

        return rows;
    }
}
~~~

Đoạn này minh họa truy vấn trang đầu; một API nhiều trang cần thêm cursor/offset và hợp đồng nhất quán. **Connection** do tầng gọi quản lý; try-with-resources chỉ đóng statement và result set do phương thức tạo.

Các quyết định có ảnh hưởng đến chi phí:

- Bộ lọc tenant và status được thực hiện **ở database**.
- **LIMIT** chặn số hàng trả về.
- **SELECT** chỉ chọn các trường DTO cần.
- **ORDER BY** có ID duy nhất để thứ tự xác định.
- **PreparedStatement** bind dữ liệu thay vì nối chuỗi người dùng vào SQL.
- **ResultSet** được duyệt ngay trong phạm vi tài nguyên còn mở.

Đây là cách tổ chức giúp chi phí dễ dự đoán hơn khi danh sách lớn; nó không bảo đảm query sẽ dùng index hay có độ trễ cụ thể. Cần đo trên dữ liệu và môi trường đại diện.

## 12. Streaming và fetch size: không phải lúc nào cũng rẻ hơn

Một API có thể trả **Stream<OrderEntity>** hoặc JDBC **ResultSet** để xử lý tuần tự thay vì tích tất cả hàng vào List. Điều này có thể giảm bộ nhớ **nếu driver thực sự lấy dữ liệu theo lô và consumer xử lý ngay**. Nhưng streaming có chi phí riêng:

- Connection có thể bị giữ suốt quá trình đọc.
- Một giao dịch đọc dài có thể giữ snapshot và ảnh hưởng việc dọn dẹp dữ liệu phiên bản (tùy DB).
- Consumer chậm khiến tài nguyên DB bị giữ lâu.
- Lỗi ở giữa luồng có thể xảy ra sau khi một phần dữ liệu đã được xử lý.
- Một số driver có thể đệm toàn bộ kết quả dù API có dạng stream.

Với pgJDBC, fetch theo cursor thường cần cấu hình đúng như **autoCommit = false**, ResultSet forward-only và fetch size dương; chi tiết phụ thuộc driver. Lời gọi **setFetchSize(500)** là gợi ý/thiết lập theo cơ chế driver, không bảo đảm mọi DB đều gửi đúng 500 hàng mỗi lần.

### 12.1. Khi nào dùng List, Slice, cursor hoặc stream?

| Dạng đọc | Ưu điểm | Nguy cơ hoặc chi phí |
| --- | --- | --- |
| List nhỏ có LIMIT | Đơn giản, tài nguyên đóng nhanh | Phải kiểm soát LIMIT |
| Page | Có thông tin tổng số trang | Có thể cần COUNT |
| Slice | Hợp “xem thêm” | Vẫn có thể dùng OFFSET |
| Keyset | Tiếp tục hiệu quả qua danh sách sâu với sort/index phù hợp | Không nhảy trang tùy ý; phải quản lý cursor |
| Stream/cursor DB | Không cần giữ toàn bộ hàng trong heap nếu dùng đúng | Giữ connection/transaction; cần đóng đúng |
| Xử lý theo lô | Giải phóng tài nguyên giữa các lô | Cần xử lý retry, bỏ sót/trùng và nhất quán |

Không có API nào luôn tốt nhất. Cần xuất phát từ kích thước dữ liệu, mục tiêu nghiệp vụ và ngân sách tài nguyên.

## 13. Đọc EXPLAIN để thấy công việc thật

Với PostgreSQL, xem kế hoạch truy vấn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount, created_at
FROM purchase_order
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

**EXPLAIN (ANALYZE, BUFFERS)** thực thi truy vấn để đo, nên chọn môi trường và thời điểm phù hợp, tránh làm tăng tải ngoài dự kiến. Các dấu hiệu nên chú ý:

1. **Scan type:** Sequential Scan, Index Scan hay Index Only Scan? Sự hiện diện của index không có nghĩa planner buộc phải chọn nó.
2. **Rows ước tính và thực tế:** nếu lệch lớn, thống kê hoặc phân bố dữ liệu có thể không được mô hình hóa đúng.
3. **Rows Removed by Filter:** bao nhiêu hàng đọc ra rồi mới bị loại?
4. **Sort:** có sắp xếp tập lớn hay đã đọc theo thứ tự index?
5. **Buffers:** số trang được truy cập qua cache hoặc phải đọc thêm từ I/O.
6. **Join nodes:** số hàng đầu vào/đầu ra mỗi phép nối; có bị nhân hàng không?
7. **Timing:** thời gian của từng bước và toàn truy vấn trong điều kiện đo cụ thể.

Một chỉ mục có thể được cân nhắc cho đường đọc phổ biến:

~~~sql
CREATE INDEX idx_order_tenant_status_time_id
ON purchase_order (tenant_id, status, created_at DESC, order_id DESC);
~~~

Nếu truy vấn thường lọc bằng **tenant_id** và **status**, rồi sắp theo **created_at, order_id**, chỉ mục này có thể giúp database tìm vùng phù hợp và đọc theo thứ tự. Tuy nhiên, nó cũng làm tăng chi phí ghi và dung lượng; một truy vấn không lọc status có thể cần chiến lược chỉ mục khác.

Để hỗ trợ projection, PostgreSQL có thể dùng **INCLUDE (total_amount)** trong chỉ mục:

~~~sql
CREATE INDEX idx_order_listing_cover
ON purchase_order (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount);
~~~

Chỉ mục bao phủ **có thể** hỗ trợ Index Only Scan khi điều kiện MVCC/visibility map cho phép; không bảo đảm luôn tránh đọc bảng chính. Hai CREATE INDEX trên là **phương án minh họa để so sánh**, không phải khuyến nghị tạo cả hai chỉ mục cùng lúc.

### 13.1. Một lần EXPLAIN chưa phải kết luận cuối

Một query có thể có kế hoạch khác khi:

- Tenant có 100 đơn so với tenant có 10 triệu đơn.
- status = PAID chiếm phần lớn dữ liệu, status = CANCELLED rất ít.
- Cache vừa được làm nóng hoặc dữ liệu vừa được nạp.
- Các thông số database, statistics, chỉ mục và phiên bản engine thay đổi.
- Có nhiều giao dịch đồng thời hoặc tài nguyên hệ thống bị chia sẻ.

Cần đo **trên các bộ tham số đại diện**, kể cả tenant lớn và tenant nhỏ, rồi liên hệ kết quả với độ trễ endpoint thực.

## 14. Quan sát SQL ORM và đo ở tầng Java

Với JPA/Spring Data, bước đầu để hiểu chi phí là **biết chính xác SQL nào được phát ra**. Bật log SQL và thống kê trong môi trường phát triển/kiểm thử phù hợp; tránh log dữ liệu nhạy cảm hoặc tham số bí mật vào hệ thống logging không được phép.

Các chỉ số hữu ích:

| Chỉ số | Phát hiện vấn đề gì? |
| --- | --- |
| **Số SELECT cho một request** | N+1, COUNT phát sinh, truy vấn lặp |
| **Số hàng trả cho một request** | Over-fetching, JOIN làm nhân hàng |
| **p50 / p95 / p99 latency** | Độ trễ thường gặp và đuôi dài khi tải tăng |
| **Connection pool wait time** | Thiếu connection hoặc giữ connection quá lâu |
| **Query execution time** | SQL/chỉ mục/DB chậm |
| **Heap allocation và GC** | Quá nhiều entity/DTO hoặc List quá lớn |
| **Rows examined / buffer reads** | Database đọc thừa so với số hàng trả |
| **Lỗi timeout và retry** | Truy vấn không ổn định, có thể làm tải tăng thêm |

Một cách đo hữu ích là đặt một request cố định, ghi nhận **SQL count + số hàng + thời gian**, sau đó thay đổi một thiết kế và chạy lại dưới dữ liệu/tải tương đương. Ví dụ:

~~~text
Trước: lấy entity và truy cập customer lazy cho từng đơn
Sau:  DTO projection bằng JOIN customer
Đo:   số SELECT, số hàng, p95 latency, memory allocation
~~~

Không nên báo “tối ưu thành công” chỉ vì mã ngắn hơn hoặc số SELECT giảm nếu endpoint trở nên chậm hơn do JOIN khổng lồ. Mục tiêu là **chi phí và kết quả đầu cuối**.

### 14.1. Cẩn trọng với cache

Cache cấp một của JPA có thể khiến nhiều lần đọc cùng entity trong một persistence context không sinh SELECT mới. Cache cấp hai hoặc application cache cũng có thể làm giảm lượt DB; nhưng nó tạo các câu hỏi về **staleness**, invalidation, memory và bảo mật tenant.

Khi benchmark, cần phân biệt cold cache và warm cache. Nếu một test chỉ chạy trong cùng transaction với dữ liệu đã nạp, có thể không phản ánh tình huống request thực tế trong môi trường production.

### 14.2. Dùng test đúng mục đích

Kiểm thử có thể khẳng định ngữ nghĩa **đúng số hàng, đúng thứ tự, đúng tenant**, đồng thời kiểm tra những dấu hiệu chi phí quan trọng như số query không tăng tuyến tính theo số bản ghi. Không nên đóng đinh một số query tuyệt đối nếu nó phụ thuộc quá sâu vào phiên bản ORM/cấu hình, trừ khi đó là hợp đồng hiệu năng được quản lý rõ.

Một bài test dùng 3 đơn hàng chưa chắc phát hiện vấn đề xuất hiện khi bảng có hàng triệu hàng. Để đánh giá performance, cần dữ liệu và phân bố đại diện, kiểm soát các biến như cache, tải đồng thời và vùng dữ liệu.

## 15. Phân quyền, giao dịch và độ tin cậy cũng nằm trong chi phí thực tế

Một “tối ưu” chỉ đáng chấp nhận khi vẫn giữ đúng ranh giới nghiệp vụ.

### 15.1. Phải lọc quyền ngay trong truy vấn

~~~sql
-- Sai nếu API chỉ được đọc tenant của người gọi:
SELECT *
FROM purchase_order
WHERE status = 'PAID';

-- Phù hợp hơn với phạm vi đã xác thực:
SELECT order_id, status, total_amount
FROM purchase_order
WHERE tenant_id = ?
  AND status = 'PAID';
~~~

Nếu đọc hàng của mọi tenant vào Java rồi mới lọc, dữ liệu không được phép đã đi qua kết nối, bộ nhớ, có thể qua cache/log và các lớp serialization. Việc trả JSON cuối cùng đúng tenant không xóa bỏ rủi ro ở những tầng trước.

**PreparedStatement** giúp tránh SQL injection khi truyền giá trị, nhưng nó không tự xác minh tenant_id do client gửi có được ủy quyền hay không.

### 15.2. Cắt nhỏ truy vấn có thể thay đổi tính nhất quán

Giả sử dùng hai bước để tải 20 đơn rồi tải dòng hàng. Giao dịch khác có thể thay đổi đơn hoặc dòng hàng giữa hai SELECT. Nếu use case cần một snapshot nhất quán, cần thiết kế ranh giới giao dịch/isolation phù hợp hoặc một chiến lược đọc khác.

Ở PostgreSQL mặc định **READ COMMITTED**, hai statement trong cùng giao dịch thông thường vẫn có thể thấy các snapshot khác nhau. Mức cô lập cao hơn có thể thay đổi điều đó nhưng cũng có chi phí và hành vi retry riêng. Không tối ưu round-trip bằng cách ngầm thay đổi bảo đảm nhất quán của use case.

### 15.3. Timeout và retry có giá

Một query chậm giữ connection lâu làm tăng thời gian chờ trong pool. Retry không giới hạn có thể nhân tải database khi hệ thống đang quá tải. Nên có timeout, retry có giới hạn cho lỗi tạm thời phù hợp và đo tỷ lệ thất bại.

Nếu thao tác đọc còn có tác dụng phụ như ghi audit hay gọi dịch vụ khác, không được mặc định retry cả thao tác là vô hại. Phân biệt **retry một SELECT an toàn** với **retry toàn bộ workflow** có thay đổi trạng thái.

## 16. Quy trình chọn API theo nhu cầu thật

Có thể dùng một chuỗi câu hỏi trước khi chọn repository method:

1. **Hợp đồng dữ liệu:** cần 0/1 bản ghi, danh sách nhỏ, Page có tổng số hay stream rất lớn?
2. **Bộ lọc quyền:** tenant, user, vai trò được áp dụng ở đâu và có đủ trong SQL không?
3. **Projection:** mỗi hàng thật sự cần những cột nào và có phải tải entity managed không?
4. **Quan hệ:** có truy cập lazy sau khi lấy danh sách không? JOIN sẽ trả một hay nhiều hàng trên mỗi thực thể?
5. **Sắp xếp:** có ORDER BY xác định, khóa phụ duy nhất và phù hợp cursor/offset không?
6. **Giới hạn:** SQL có LIMIT phù hợp không, hay Java mới cắt danh sách?
7. **Chi phí phụ:** có COUNT, batch query, flush, cache miss hoặc truy vấn do serialization phát sinh không?
8. **Đo lường:** log SQL, EXPLAIN, số row, buffer, round-trip, độ trễ và bộ nhớ đang cho biết điều gì?
9. **Nhất quán:** có yêu cầu snapshot, giao dịch, quyền truy cập hay xử lý đồng thời đặc biệt không?

Ví dụ lựa chọn:

| Mục đích | API / dạng truy vấn đề xuất | Kiểm tra trước khi dùng |
| --- | --- | --- |
| Tìm đơn theo khóa và tenant | Query theo ID + tenant, Optional/DTO | Scope quyền, index, cache |
| Chỉ cần biết có đơn không | EXISTS / existsBy... phù hợp | Không đọc entity thừa |
| Danh sách 20 đơn gần nhất | DTO + WHERE + ORDER BY + LIMIT | Index, sort tie-breaker |
| UI có tổng số trang | Page / dữ liệu + COUNT | Chi phí count, JOIN, đồng nhất filter |
| UI chỉ cần “Xem thêm” | Slice hoặc keyset | Không COUNT nếu không cần; kiểm tra OFFSET |
| Hiển thị tên khách | Projection JOIN customer | Số hàng và round-trip |
| Hiển thị 20 đơn và từng dòng hàng | Chọn cha trước, rồi tải con theo lô | Nhân hàng, giao dịch, cache |
| Xuất hàng triệu đơn | Chunking hoặc streaming đúng cấu hình | Connection lâu, snapshot, lỗi giữa chừng |

Tên hàm **findTop20...** hoặc **findAllBy...** có thể diễn tả ý định tốt; nó vẫn cần được kiểm tra bằng SQL thực tế và kế hoạch thực thi.

## 17. Tình huống thực hành

### Tình huống A: một câu lệnh đẹp nhưng tải quá nhiều

~~~java
List<OrderEntity> recent = repository.findAll().stream()
    .filter(o -> o.getStatus() == OrderStatus.PAID)
    .limit(20)
    .toList();
~~~

**Câu hỏi:** Vì sao một câu Java có thể chậm dù chỉ trả 20 đơn?

**Gợi ý:** **findAll()** lấy toàn bộ entity trước khi stream Java chạy, và **limit(20)** chỉ giới hạn stream trong bộ nhớ. Cần chuyển lọc và LIMIT xuống SQL, bổ sung ORDER BY nếu “recent” thực sự nghĩa là đơn mới nhất, và giới hạn theo tenant được ủy quyền.

### Tình huống B: một trang 20 đơn nhưng có hàng chục SELECT

Endpoint gọi **findTop20...** rồi trong vòng lặp truy cập **order.getCustomer().getFullName()**.

**Câu hỏi:** Có thể xuất hiện vấn đề gì và kiểm chứng bằng cách nào?

**Gợi ý:** Có thể phát sinh N+1 do lazy loading. Ghi nhận SQL cho một request, số SELECT, số khách phân biệt và cache; sau đó thử projection JOIN, EntityGraph hoặc batch fetching thích hợp, kiểm tra số hàng và độ trễ.

### Tình huống C: Page mất nhiều thời gian dù LIMIT 20

Một repository trả **Page<OrderEntity>** cho màn hình chỉ có “Xem thêm”.

**Câu hỏi:** Chi phí nào có thể không cần thiết?

**Gợi ý:** Truy vấn COUNT để biết tổng số bản ghi/tổng số trang có thể tốn kém. Cân nhắc **Slice** hoặc keyset nếu UI không cần totalCount. Nhưng nếu vẫn dùng OFFSET sâu, cần xử lý riêng vấn đề phân trang.

### Tình huống D: JOIN rồi LIMIT 20 trả chỉ 4 đơn

Một câu truy vấn JOIN purchase_order và order_item, mỗi đơn có 5 dòng, áp dụng LIMIT 20.

**Giải thích:** LIMIT giới hạn 20 **hàng JOIN**, không phải 20 **đơn**. Chọn 20 đơn trước rồi lấy dòng hàng theo lô, hoặc viết query với ngữ nghĩa phân trang hàng cha phù hợp.

### Tình huống E: chỉ mục có rồi nhưng SQL vẫn chậm

Truy vấn lọc **tenant_id + status**, sort **created_at**, LIMIT 20; bảng đã có index trên **created_at** riêng.

**Gợi ý:** Index chỉ trên thời gian có thể không phù hợp với lọc tenant/status; database có thể đọc nhiều hàng rồi loại hoặc sort. Xem **EXPLAIN (ANALYZE, BUFFERS)** và cân nhắc index ghép theo truy vấn thực tế; xác minh trên tenant nhỏ và tenant lớn.

### Tình huống F: benchmark báo “0 query”

Một test JPA đọc cùng entity nhiều lần trong một transaction sau khi entity đã được persist.

**Giải thích:** Persistence context có thể đã giữ entity, khiến lần đọc không cần SELECT mới. Đây là hành vi hợp lệ nhưng không chứng minh một request khác với persistence context mới cũng không truy cập database. Cần kiểm tra warm/cold cache và request đại diện.

### Tình huống G: tối ưu làm sai quyền truy cập

Để giảm số query, lập trình viên tải danh sách tất cả đơn rồi cache, sau đó lọc tenant theo người dùng ở service.

**Giải thích:** Dữ liệu của tenant khác đã được đọc và đưa vào cache chung. Cần đẩy điều kiện quyền vào DB, phân vùng hoặc kiểm soát cache theo scope, và đánh giá quyền ở từng thao tác. Giảm round-trip không đáng đổi lấy sai lệch phân quyền.

## 18. Ghi nhớ

**API truy vấn thuận tiện diễn đạt cách lập trình viên muốn sử dụng dữ liệu; nó không tự công bố mọi SQL, số hàng, lượt gọi, byte truyền hay bộ nhớ cần thiết.** Một lời gọi ngắn có thể tải quá nhiều entity, tạo N+1 hoặc truy vấn COUNT; một truy vấn SQL dài hơn với bộ lọc, projection và LIMIT đúng lại có thể rẻ hơn.

Khi thiết kế tầng persistence Java, hãy bắt đầu từ nhu cầu nghiệp vụ và **hợp đồng kết quả**. Chỉ đọc những hàng, cột và quan hệ cần thiết; giữ quyền truy cập trong điều kiện SQL; chọn Page, Slice, keyset hoặc streaming theo cách sử dụng thực tế; đo bằng SQL do driver/ORM phát ra, kế hoạch **EXPLAIN** và chỉ số endpoint. Tối ưu hiệu năng cần đồng thời bảo vệ ràng buộc dữ liệu, giao dịch và tính nhất quán khi hệ thống hoạt động đồng thời.
