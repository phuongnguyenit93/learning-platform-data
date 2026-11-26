# Giới hạn của Page, tổng số trang và truy cập trang ngẫu nhiên

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **`Page<T>`**, **`Slice<T>`** và **cursor-based pagination**; giải thích vì sao mô hình trang 1, 2, 3, … không tương ứng trực tiếp với cách Cassandra duyệt dữ liệu.
- Giải thích sự khác nhau giữa **tổng bản ghi (`totalElements`)**, **tổng trang (`totalPages`)**, **số hàng mỗi trang (`pageSize`)** và **paging state** của Apache Cassandra Java Driver.
- Hiểu vì sao `COUNT(*)` và **truy cập trang ngẫu nhiên** thường đắt đỏ trên Cassandra; biết trường hợp cần đo, tránh hoặc thiết kế bảng phụ.
- Dùng `Slice` và `CassandraPageRequest` của Spring Data Cassandra cho trải nghiệm “tiếp theo” thay vì yêu cầu page number + offset như SQL quan hệ.
- Xây API cursor qua driver `AsyncResultSet`/`PagingState` hoặc seek/keyset theo clustering key, biết ưu/nhược của từng cách.
- Thiết kế bảng theo truy vấn với partition key, clustering order và time bucket để tối ưu đọc danh sách, đồng thời xử lý chuyển bucket, dữ liệu cập nhật đồng thời, consistency, timeout và giới hạn bộ nhớ.
- Đề xuất UI và hợp đồng API thực tế khi người dùng muốn thấy “trang cuối”, tổng trang, hoặc nhảy tới trang bất kỳ.
- Kiểm thử cursor, paging state, thay đổi filter, insert/delete giữa các lần đọc và các kịch bản lỗi trong cụm Cassandra phân tán.

Bài thuộc chương **Chiếu và phân trang** của **SPRING_DATA_CASSANDRA**. Mục tiêu của mô-đun là truy cập Apache Cassandra bằng Spring Data Cassandra với entity mapping, repository, `CassandraTemplate` và CQL; đồng thời thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng. Trong bài này, “chiếu” có nghĩa là chọn cột/kiểu dữ liệu cần trả (projection), còn “phân trang” nói về cách lấy một phần tập kết quả mà không buộc Cassandra quét hoặc tải tất cả.

> **Thông điệp trọng tâm:** Cassandra tối ưu cho **truy vấn biết partition key và duyệt theo clustering order**. Nó không có thao tác offset phổ thông tương đương `OFFSET 100000 LIMIT 20` trên toàn bộ tập dữ liệu. Vì thế, trong nhiều ứng dụng, **`Slice` + cursor/next token** là hợp đồng đáng tin cậy hơn `Page` với tổng số trang và nút “đến trang bất kỳ”.

## 1. Page trong Spring Data có ý nghĩa gì?

Với những hệ thống dùng Spring Data JPA/RDBMS, UI thường hiển thị:

~~~text
Kết quả tìm kiếm: 4.726 bản ghi
Trang 1 / 237      [1] [2] [3] ... [237]
Mỗi trang: 20      [Trang trước] [Trang tiếp]
~~~

Để đưa ra giao diện này một cách chính xác, ứng dụng cần ít nhất:

1. Tập các bản ghi tương ứng trang đang đọc.
2. **Tổng số bản ghi** thỏa điều kiện lọc (`totalElements`).
3. **Tổng số trang** dựa trên tổng và kích thước trang (`totalPages`).
4. Một cách truy cập trực tiếp phần tử bắt đầu tại offset của trang muốn xem.

Spring Data Commons có các interface khái niệm:

| Kiểu kết quả | Thường chứa | Giới hạn/chú ý |
| --- | --- | --- |
| `List<T>` | Danh sách bản ghi đọc được | Không tự có metadata “còn trang tiếp theo” |
| `Slice<T>` | Nội dung hiện tại + thông tin có trang tiếp theo | Không bắt buộc biết tổng số hàng hoặc tổng số trang |
| `Page<T>` | Nội dung slice + `totalElements` và `totalPages` | Cần có/cung cấp tổng số hàng; không tự giúp database nhảy đến offset |
| Cursor API | Nội dung + `nextCursor` / `hasMore` | Phục vụ duyệt tuần tự; không mặc định biết “trang 237” |

Trong Spring Data Commons, `Page<T>` kế thừa `Slice<T>` và bổ sung metadata tổng. API `Page.getTotalElements()` và `Page.getTotalPages()` chỉ có thể trả giá trị có ý nghĩa nếu tầng dữ liệu **thật sự biết** tổng.

### 1.1. Công thức tổng trang trông đơn giản nhưng đầu vào mới khó

Khi biết chính xác `N` phần tử và kích thước trang `S > 0`:

~~~text
totalPages = ceil(N / S)
~~~

Ví dụ: có 4.726 bản ghi, `S = 20` thì tổng trang là 237. Nhưng nếu `N` chỉ là ước lượng hoặc thay đổi liên tục, giá trị `totalPages` cũng chỉ là **ước lượng theo thời điểm**, không phải sự thật vĩnh viễn.

Đừng đánh đồng:

- **Page number** là một khái niệm của giao diện.
- **Offset** là vị trí phải bỏ qua `(pageNumber × pageSize)` bản ghi trước khi lấy phần đang đọc.
- **Paging state** là token nội bộ để Cassandra **tiếp tục cùng truy vấn** từ trạng thái đã dừng.
- **Clustering key cursor** là giá trị khóa cuối cùng dùng để seek tới phần dữ liệu tiếp theo theo điều kiện `WHERE`.

### 1.2. Sơ đồ từ UI đến Cassandra

~~~mermaid
flowchart TD
    A["UI muốn trang 100 / 237"] --> B{"Có tổng và offset? "}
    B -->|SQL quan hệ| C["COUNT + OFFSET / index"]
    B -->|Cassandra| D["Không có OFFSET tổng quát"]
    D --> E["Slice / paging state: next page"]
    D --> F["Keyset cursor theo clustering key"]
    D --> G["Bảng chỉ mục/checkpoint riêng nếu cần jump"]
    E --> H["UI: Xem thêm / Trang tiếp"]
    F --> H
    G --> I["UI: Nhảy đến mốc thời gian hoặc checkpoint"]
~~~

Không phải cứ API trả object Java `PageImpl<T>` là database đã hỗ trợ offset. Object `PageImpl` chỉ là một cách đóng gói dữ liệu và metadata trong Java; khả năng truy vấn và tính đúng đắn của metadata vẫn do **mô hình dữ liệu, thuật toán và cách đếm** quyết định.

## 2. Vì sao Cassandra không hỗ trợ truy cập trang số tùy ý?

Apache Cassandra phân phối partition theo token trên nhiều node. Bên trong **một partition**, các row được tổ chức theo thứ tự clustering columns; giữa các partition khác nhau, không có một thứ tự tuyến tính chung mà bạn có thể truy cập bằng offset toàn bảng.

Ví dụ bảng cho màn hình lịch sử đơn:

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Bảng này tối ưu cho câu hỏi:

> “Lấy những đơn mới nhất của **khách hàng A trong tháng 11/2026**.”

Query phù hợp:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Vì đã biết đầy đủ `(customer_id, month_bucket)`, Cassandra tìm đúng partition và đọc theo clustering order. Nhưng nếu muốn “trang 100”, không có lệnh CQL tổng quát:

~~~sql
-- KHÔNG PHẢI cú pháp paging của Cassandra:
SELECT *
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
OFFSET 1980 LIMIT 20;
~~~

Cassandra không hiểu offset đó như SQL quan hệ. Cách thường gặp để tiến tới đoạn dữ liệu sâu là **duyệt theo paging state** qua các trang trước, hoặc dùng điều kiện **seek theo clustering key** nếu schema và đường truy vấn phù hợp.

### 2.1. Vì sao không có thứ tự toàn bảng?

~~~text
Partition A = (customer_id=A, month_bucket=2026-11)
  2026-11-25 10:00, order X
  2026-11-24 09:00, order Y
  ...

Partition B = (customer_id=A, month_bucket=2026-10)
  2026-10-31 20:00, order M
  2026-10-30 18:00, order N
  ...

Partition C = (customer_id=B, month_bucket=2026-11)
  2026-11-25 11:00, order P
  ...
~~~

Trong từng partition, Cassandra duy trì thứ tự clustering phù hợp. Nhưng nó **không tự hợp nhất** các partition A, B, C thành một danh sách toàn cụm với vị trí hàng 0, 1, 2, ... có thể nhảy đến được.

Do đó:

- `ORDER BY created_at DESC` không phải cách sắp xếp tùy ý mọi row trên toàn cluster.
- Partition key phải được ràng buộc theo luật CQL để dùng clustering order hiệu quả.
- Muốn duyệt nhiều bucket, service phải chọn bucket, điều phối thứ tự và quản lý cursor riêng.
- Thêm `pageSize=20` chỉ điều chỉnh mỗi lần fetch, không tạo chỉ mục thứ tự toàn bảng.

## 3. Page, Slice và giới hạn thực tế của Spring Data Cassandra

Trong Spring Data Commons, một phương thức có thể khai báo `Page<T>`, `Slice<T>` hoặc `List<T>` tùy store module. **Không được suy rằng mọi khả năng pagination của Spring Data JPA đều chuyển nguyên sang Cassandra**.

| Mong muốn | Cách nghĩ theo RDBMS | Thực tế với Cassandra |
| --- | --- | --- |
| “Cho tôi page 10” | `PageRequest.of(9, 20)` ⇒ offset 180 | Cassandra không có OFFSET tổng quát; cần cursor của các trang trước hoặc seek theo khóa |
| “Trả totalElements” | Query đếm có thể có kế hoạch/index | Query đếm lớn có thể scan nhiều row/partition, rất đắt |
| “Trả totalPages” | `ceil(totalElements / size)` | Không có tổng đủ tin cậy nếu chưa đếm/duy trì số tổng riêng |
| “Trang tiếp” | Offset mới hoặc keyset | Phù hợp với paging state/cursor |
| “Trang trước” | Offset lùi | Cần giữ stack cursor hoặc thiết kế seek ngược |
| “Trang cuối” | Tính offset cuối | Không có cách tổng quát/nhanh nếu chưa có mốc và tổng |
| “Xem thêm 20” | Query tuần tự | Phù hợp mô hình Cassandra hơn |

### 3.1. Vì sao ưu tiên Slice?

`Slice<T>` có các thuộc tính/hành vi hữu ích như:

- `getContent()`: dữ liệu trang hiện tại.
- `hasNext()`: có thể đọc tiếp không?
- `nextPageable()`: mô tả yêu cầu tiếp theo nếu module hỗ trợ.
- `getNumberOfElements()`: số row được đưa vào slice hiện tại.

Không có đòi hỏi phải tính `totalElements` hay `totalPages`. Điều này phù hợp với driver paging state.

Với Spring Data Cassandra, cơ chế được sử dụng để tiến trang là **`CassandraPageRequest`** thay vì offset số học tùy ý. Các API Spring Data về `Slice`, `Pageable` và tên factory cụ thể có thể khác theo phiên bản; cần đối chiếu dependency khi triển khai.

### 3.2. Ví dụ repository trả về Slice

Giả sử entity ánh xạ trực tiếp bốn trường primary key:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKeyColumn(
        name = "customer_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "month_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private String monthBucket;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private UUID orderId;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public OrderByCustomerMonth() {
    }

    // Getters, setters và constructors phù hợp...
}
~~~

Repository có thể khai báo một phương thức trả về `Slice`:

~~~java
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.core.mapping.MapId;
import org.springframework.data.repository.query.Param;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface CustomerOrderRepository
        extends CassandraRepository<OrderByCustomerMonth, MapId> {

    @Query(
        "SELECT * FROM orders_by_customer_month " +
        "WHERE customer_id = :customerId " +
        "AND month_bucket = :monthBucket"
    )
    Slice<OrderByCustomerMonth> findMonth(
        @Param("customerId") UUID customerId,
        @Param("monthBucket") String monthBucket,
        Pageable pageable
    );
}
~~~

**Lưu ý về khóa ghép:** ví dụ dùng `MapId` cho entity khai báo nhiều `@PrimaryKeyColumn` trực tiếp. Nếu thiết kế khóa bằng `@PrimaryKeyClass` và một field `@PrimaryKey`, hãy dùng chính class khóa đó làm kiểu ID của repository. Không thay toàn bộ primary key ghép bằng một `UUID` đơn; xác minh API và cách mapping phù hợp với phiên bản Spring Data Cassandra thực tế.

Ví dụ sử dụng dựa trên API `CassandraPageRequest`:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Pageable pageable = CassandraPageRequest.first(20);

Slice<OrderByCustomerMonth> slice =
    repository.findMonth(customerId, "2026-11", pageable);

List<OrderByCustomerMonth> content = slice.getContent();

if (slice.hasNext()) {
    Pageable nextPageable = slice.nextPageable();

    // Truy vấn tiếp bằng nextPageable và CÙNG bộ lọc ban đầu:
    Slice<OrderByCustomerMonth> nextSlice =
        repository.findMonth(customerId, "2026-11", nextPageable);
}
~~~

Ý tưởng chính là dùng **đầu trang (first)** rồi tiến bằng state do kết quả trả về, không lấy `PageRequest.of(50, 20)` để yêu cầu nhảy tới trang 51. API chính xác của `CassandraPageRequest`/query execution nên được kiểm tra khi viết code theo phiên bản Spring Data Cassandra đã chọn.

### 3.3. Không hứa hẹn Page<T> với tổng trang mặc định

Nhiều hướng dẫn JPA dùng:

~~~java
Page<Order> page = repository.findAll(PageRequest.of(9, 20));
int totalPages = page.getTotalPages();
long totalRows = page.getTotalElements();
~~~

**Không chuyển mẫu này sang Cassandra một cách máy móc.** Đa số đường truy vấn Cassandra không có cách truy cập trực tiếp offset tương ứng và cũng không có count được trả tự nhiên từ kết quả. Một số phiên bản/kiểu repository có thể không hỗ trợ `Page<T>` như người dùng kỳ vọng; ngay cả khi bạn tự dựng `PageImpl<T>`, tổng số trang chỉ đúng theo cách bạn **tự tính và tự bảo đảm**.

Cách thiết kế tốt hơn: giao diện “xem thêm” hoặc “trang tiếp” có `Slice`/cursor; nếu business thật sự cần tổng, xây cơ chế đếm riêng và công khai ý nghĩa/độ chính xác của nó.

## 4. Vì sao COUNT(*) và tổng số trang đắt đỏ?

CQL có cú pháp đếm:

~~~sql
SELECT COUNT(*)
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?;
~~~

Đối với **một partition có đầy đủ partition key**, Cassandra có thể đếm các row phù hợp bằng cách đọc/quét phần dữ liệu tương ứng; nhưng thao tác vẫn có chi phí phụ thuộc lượng dữ liệu cần duyệt, tombstone, I/O và trạng thái replica. Đây không phải metadata count miễn phí được cập nhật tự động cho mọi bộ lọc.

Còn câu đếm toàn bảng:

~~~sql
-- Có thể cực kỳ tốn kém và dễ timeout khi bảng lớn:
SELECT COUNT(*) FROM orders_by_customer_month;
~~~

có thể phải duyệt dữ liệu trên nhiều partition/nodes và trở nên rất chậm hoặc tạo áp lực vận hành. Không đưa đếm toàn bảng lớn vào mỗi request hiển thị danh sách.

### 4.1. COUNT và Page có thể làm mỗi màn hình đắt gấp nhiều lần

Giả sử endpoint được gọi 1.000 lần/giây và mỗi lần:

1. Chạy query lấy 20 row cho trang hiện tại.
2. Chạy thêm `COUNT(*)` trên cùng điều kiện.
3. Tính `totalPages`.
4. Trả JSON cho UI.

Ngay cả khi truy vấn lấy 20 row đã tối ưu, câu `COUNT(*)` có thể phải đọc nhiều hàng hơn rất nhiều. Nó còn có thể chạy lại cho mọi lần chuyển trang. Vì thế một UI “Trang 1/237” có thể làm database tốn tài nguyên đáng kể so với danh sách “Xem thêm”.

### 4.2. Tổng có thể thay đổi giữa lúc lấy dữ liệu và lúc đếm

Nếu hệ thống đang có ghi/xóa đồng thời:

~~~text
T0: SELECT lấy 20 row
T1: Có thêm 5 đơn mới
T2: COUNT(*) trả tổng tại thời điểm đọc khác
T3: API trả Page với content và total không cùng snapshot
~~~

Cassandra không tự cung cấp isolation/snapshot giao dịch đa câu SELECT cho toàn bộ workflow đọc như một database quan hệ có isolation cao. Consistency level như `LOCAL_QUORUM` điều khiển replica phản hồi chứ không tự ghép hai truy vấn độc lập thành một snapshot atomic.

Do đó, ngay cả một câu đếm chạy thành công cũng không chắc phản ánh **cùng thời điểm logic** với nội dung trang đã đọc. Giá trị total còn phụ thuộc replication lag, các write cạnh tranh và thời điểm yêu cầu.

### 4.3. Giữ tổng riêng khi thật sự cần

Nếu sản phẩm cần hiển thị “Khoảng 12.000 đơn”, các lựa chọn thực tế:

| Chiến lược | Điểm mạnh | Hạn chế |
| --- | --- | --- |
| Không trả total | Nhanh, đơn giản, phù hợp infinite scroll | Không có nút trang cuối/tổng chính xác |
| Đếm từng partition khi nhỏ | Có thể đơn giản trong phạm vi hẹp | Đắt khi partition lớn, còn lệch snapshot |
| Duy trì bảng aggregate `orders_count_by_customer_month` | Đọc tổng nhanh hơn | Phải cập nhật, deduplicate, backfill, reconcile |
| Tổng ước lượng/làm mới định kỳ | Thích hợp dashboard ít yêu cầu chính xác | Độ trễ, phải gắn nhãn estimated/as-of |
| Counter CQL | Phép tăng/giảm được tối ưu riêng | Retry không idempotent, có nguy cơ đếm đôi |
| Analytics/search system riêng | Phù hợp tổng hợp/lọc đa chiều | Độ phức tạp đồng bộ và consistency contract |

Nếu tự duy trì tổng, không được coi `INSERT`/`UPDATE` thông thường luôn có nghĩa một row mới được thêm. Upsert cùng primary key có thể chỉ ghi lại row đã có. Counter `+1` cho mọi retry có nguy cơ **đếm trùng**. Cần thiết kế sự kiện, idempotency key, reconciliation và định nghĩa tổng (tính row đã xóa? trạng thái? toàn DC?) trước.

### 4.4. TotalPages có thể chỉ là metadata ước lượng

Nếu báo cáo ước lượng `estimatedTotal=4726` với `pageSize=20`, có thể hiển thị “khoảng 237 trang” nhưng **không** hứa người dùng nhảy thẳng tới trang 237 mà không cần quét/seek. Một con số tổng không tự tạo cơ chế tìm offset.

Nên đặt tên API minh bạch:

~~~json
{
  "items": [],
  "pageSize": 20,
  "hasMore": true,
  "nextCursor": "opaque-token",
  "estimatedTotal": 4726,
  "totalAsOf": "2026-11-25T00:00:00Z"
}
~~~

Đây là JSON minh họa **hợp đồng**, không phải kết quả chạy thật. Nếu không có quy trình cập nhật tổng ước lượng, nên bỏ cả `estimatedTotal` và `totalAsOf`.

## 5. Driver paging state: đi tiếp, không nhảy ngẫu nhiên

Java Driver cho phép Cassandra trả kết quả theo từng trang; các trang sau được truy xuất qua state do server/driver cung cấp.

~~~mermaid
sequenceDiagram
    participant Client as HTTP Client
    participant API as Spring Boot API
    participant D as Java Driver
    participant C as Cassandra

    Client->>API: GET /orders?month=2026-11
    API->>D: Query đủ partition key, pageSize=20
    D->>C: SELECT ...
    C-->>D: rows + paging state
    D-->>API: Trang hiện tại
    API-->>Client: items + nextCursor
    Client->>API: GET /orders?cursor=...
    API->>D: Tiếp tục cùng query với state
    D->>C: Fetch trang kế tiếp
    C-->>D: rows + paging state tiếp
    API-->>Client: items + nextCursor mới
~~~

### 5.1. Page size không phải tổng hàng hay số trang API

Ví dụ Java Driver:

~~~java
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement prepared = session.prepare(
    "SELECT order_id, created_at, status " +
    "FROM orders_by_customer_month " +
    "WHERE customer_id = ? AND month_bucket = ?"
);

BoundStatement bound = prepared
    .bind(customerId, "2026-11")
    .setPageSize(20)
    .setIdempotent(true);
~~~

Nếu query có 1.000 row, `pageSize=20` **không** làm kết quả chỉ còn 20 row. Nó là mục tiêu cho số hàng trong một lần fetch. Khi code duyệt hết `ResultSet` đồng bộ, driver có thể tự tải thêm trang:

~~~java
for (Row row : session.execute(bound)) {
    // Có thể kích hoạt fetch tiếp các trang kế tiếp.
    process(row);
}
~~~

Vì vậy, đừng nhận `ResultSet` rồi chuyển thành `List` tất cả hàng nếu API chỉ cần 20 item.

### 5.2. AsyncResultSet thể hiện một trang rõ ràng

Java Driver 4.x hỗ trợ `AsyncResultSet` để xử lý từng trang:

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

session.executeAsync(bound).thenAccept(page -> {
    for (Row row : page.currentPage()) {
        UUID orderId = row.getUuid("order_id");
        // Ánh xạ row thuộc trang hiện tại.
    }

    if (page.hasMorePages()) {
        // Khi được phép tải tiếp, gọi page.fetchNextPage()
        // và xử lý CompletionStage cùng các lỗi bất đồng bộ.
    }
});
~~~

Điều này giúp bạn phân biệt:

- `currentPage()`: hàng **đang có sẵn** của trang hiện tại.
- `hasMorePages()`: còn có thể fetch thêm trang không.
- `fetchNextPage()`: yêu cầu trang kế tiếp theo state.

Không fetch liên tục trong vòng lặp không giới hạn khi downstream chưa xử lý xong. Cần backpressure, giới hạn đồng thời, timeout và cancellation.

### 5.3. Paging state là token mờ đục

**Paging state không phải “số thứ tự trang”** và không nên được sửa/giải mã tùy tiện trong ứng dụng. Để tiếp tục đúng, cần dùng state với **cùng query, bind values, và các option liên quan** theo hợp đồng driver.

Khi phát cursor ra client:

- Không để client tự chỉnh token/partition key để truy cập dữ liệu người khác.
- Nên ký/bảo vệ cursor bằng cơ chế server hoặc lưu state phía server để ngăn giả mạo; xem xét cả ràng buộc tenant/authorization.
- Đặt tuổi thọ của cursor và chính sách xử lý khi schema/query hoặc quyền truy cập thay đổi.
- Không nhầm token paging state với cơ chế snapshot: dữ liệu vẫn có thể bị thêm/xóa/cập nhật giữa hai request.
- Tránh log token cùng PII ở mức không cần thiết.

### 5.4. Vì sao không thể lấy “page 100” từ paging state đầu tiên?

Paging state là kết quả của một trang trước đó; để có state dẫn đến trang 100, thông thường phải **đi qua các trạng thái trung gian** hoặc lưu trước checkpoint hợp lệ. Cassandra không cung cấp hàm tính “state của trang N” chỉ từ `N` và `pageSize`.

Nếu UI phải hỗ trợ Back/Next, cách đơn giản là giữ **stack các cursor** trong client/server cho phiên duyệt: cursor trang 1, trang 2, ... Khi quay lại trang đã từng đi qua, ứng dụng có thể dùng cursor đã lưu hoặc điều kiện seek tương ứng. Khi dữ liệu thay đổi, việc phát lại cursor cũ vẫn cần xem xét tính nhất quán và trạng thái hết hạn.

## 6. Seek/keyset pagination theo clustering columns

Nếu ứng dụng cần cursor **có thể được giải thích bằng khóa** và trang tiếp theo trong một partition đã sắp xếp, có thể sử dụng **keyset pagination**, tức truy vấn với điều kiện “khóa nhỏ hơn/lớn hơn khóa cuối trang trước” thay vì dùng offset.

Với bảng đã khai báo:

~~~sql
PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC)
~~~

trang đầu:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 21;
~~~

Nếu giao diện chỉ hiển thị 20 hàng, ứng dụng có thể đọc **21 hàng** để xác định `hasMore`, hiển thị 20 và giữ khóa của **hàng thứ 20** làm vị trí tiếp tục.

Trang tiếp theo có thể biểu diễn bằng một điều kiện range trên tuple clustering:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
  AND (created_at, order_id) < (?, ?)
LIMIT 21;
~~~

Vì cả hai clustering columns đều `DESC`, tuple `(created_at, order_id)` **nhỏ hơn** mốc cuối tương ứng với các hàng xuất hiện sau mốc theo thứ tự trên. Khi thiết kế mixed ASC/DESC hoặc dùng kiểu dữ liệu khác, phải kiểm tra cụ thể cú pháp tuple restriction và hướng so sánh mà phiên bản Cassandra hỗ trợ; không sao chép toán tử `<` một cách máy móc.

### 6.1. Vì sao cần khóa sắp xếp duy nhất?

Giả sử chỉ dùng `created_at` và hai đơn có cùng timestamp:

~~~text
2026-11-25T10:00:00Z | order A
2026-11-25T10:00:00Z | order B
2026-11-25T09:59:59Z | order C
~~~

Nếu cursor chỉ mang `created_at`, điều kiện `created_at < lastCreatedAt` có thể **bỏ qua một đơn** cùng timestamp chưa được hiển thị. Thêm `order_id` vào clustering key và cursor giúp tạo thứ tự xác định của các hàng.

Ở bảng ví dụ, cursor nên chứa:

~~~json
{
  "customerId": "11111111-1111-4111-8111-111111111111",
  "monthBucket": "2026-11",
  "lastCreatedAt": "2026-11-25T10:00:00Z",
  "lastOrderId": "22222222-2222-4222-8222-222222222222",
  "pageSize": 20
}
~~~

Đây mới là **payload logic**. Khi gửi cho client, nên đóng gói thành **cursor opaque có chữ ký** hoặc lưu state ở server. Các giá trị `customerId` và `monthBucket` còn phải được đối chiếu với quyền của người dùng; chữ ký token không thay thế authorization.

### 6.2. Phân trang bằng LIMIT + 1

Mẫu thuật toán cho page size `S = 20`:

1. Truy vấn tối đa `S+1` hàng trong partition đúng.
2. Nếu nhận tối đa 20 hàng, hiển thị tất cả, `hasMore=false` theo snapshot/truy vấn hiện tại.
3. Nếu nhận 21 hàng, chỉ trả 20, `hasMore=true`.
4. Lấy khóa của **hàng cuối được trả**, không phải khóa của hàng lookahead thứ 21.
5. Trang sau dùng điều kiện seek **strict** theo khóa đó để tránh trả lại hàng cuối.
6. Không dùng một số offset để “bỏ qua” các hàng trước mốc.

Bước 4 rất quan trọng: nếu cursor lấy từ hàng thứ 21 nhưng hàng đó **chưa** được trả cho client, lần sau query bắt đầu sau nó sẽ **bỏ mất hàng**.

### 6.3. Khi nào keyset tốt hơn paging state?

| Tiêu chí | Driver paging state | Seek/keyset theo clustering key |
| --- | --- | --- |
| Mục tiêu | Tiếp tục một truy vấn CQL bằng state nội bộ | Tiếp tục theo vị trí khóa sắp xếp |
| Thiết kế cursor | Mờ đục, do driver/server tạo | Payload có khóa/timestamps, ứng dụng quản lý |
| Cần khóa sắp xếp riêng? | Vẫn cần schema/query phù hợp | Cần khóa ổn định, đủ phân biệt và restriction hợp lệ |
| Nhảy đến thời điểm cụ thể | Không tự có | Có thể dùng time/clustering range phù hợp |
| Qua nhiều bucket | Cần logic thêm | Cần điều phối bucket + seek |
| Thay query/filter | State thường không còn phù hợp | Cursor cũng phải ràng buộc filter/contract |
| Khả năng dùng lại lâu dài | Phụ thuộc driver/schema/state, không nên hứa | Có thể ổn định hơn nếu khóa và contract không đổi, nhưng vẫn chịu dữ liệu biến động |
| Bảo mật | Không cho client sửa token | Ký payload, kiểm tra tenant/quyền |

Keyset không phải thuốc chữa cho một truy vấn không có partition key. Cả hai cách đều cần bảng theo truy vấn và đánh giá dữ liệu cập nhật đồng thời.

## 7. “Nhảy đến trang bất kỳ” khác “đi tới thời điểm bất kỳ”

Người dùng có thể yêu cầu:

> “Cho tôi xem **trang 100** của lịch sử đơn.”

Trước khi triển khai, phải xác định họ thực sự muốn:

- Một vị trí thứ tự không đổi trong tập bản ghi rất lớn?
- Những đơn quanh một **ngày cụ thể**?
- Những đơn có `order_id`, `created_at` hoặc trạng thái nhất định?
- Một báo cáo đã đóng băng dữ liệu với số hàng cố định?

Nếu nhu cầu là “tìm đơn tháng 3 năm ngoái”, UI **lọc theo ngày/tháng** thường tốt hơn một nút trang 100. Query theo `month_bucket` hoặc clustering range có thể trực tiếp định vị vùng dữ liệu cần đọc.

### 7.1. Bốn chiến lược truy cập ngẫu nhiên

| Cách làm | Phù hợp với | Đánh đổi |
| --- | --- | --- |
| Không hỗ trợ jump; chỉ Next/Back | Feed, timeline, danh sách động | UI không có số trang tùy ý |
| Jump tới mốc thời gian/bucket | Lịch sử theo thời gian | Cần sắp xếp/clustering đúng và chọn mốc |
| Lưu checkpoint/mốc khóa định kỳ | Dataset tương đối ổn định, cần jump tới vùng gần trang N | Phải xây/chăm sóc index phụ, stale khi dữ liệu thay đổi |
| Tạo snapshot/report materialized | Export, báo cáo cần tổng/chỉ số hàng cố định | Chi phí tạo snapshot và lưu trữ, SLA “as-of” riêng |

Không nên triển khai jump-to-page bằng cách:

~~~text
for (int i = 0; i < targetPage; i++) {
    fetchNextPage();
}
~~~

trên mỗi request rồi coi đó là giải pháp hiệu quả. Độ phức tạp tăng theo độ sâu trang, gây nhiều round-trip và chi phí server. Cơ chế này có thể dùng cho thao tác offline nhỏ, nhưng không phù hợp cho API tương tác phải nhảy đến trang rất sâu thường xuyên.

### 7.2. Checkpoint không tự giải quyết dữ liệu đang thay đổi

Giả sử bạn lưu “khóa đầu trang 100” lúc 09:00. Tới 10:00 có 200 hàng mới được chèn trước nó; checkpoint vẫn trỏ đến **một mốc khóa**, nhưng không còn đúng **trang số 100** nếu người dùng tính từ dữ liệu mới nhất.

Nếu bắt buộc có số trang ổn định, cần định nghĩa **snapshot/as-of**, cập nhật checkpoint theo phiên bản dataset, hoặc chấp nhận rằng số trang là tương đối. Đây là yêu cầu nghiệp vụ, không phải lỗi của `CassandraPageRequest`.

## 8. Chèn/xóa dữ liệu giữa các lần đọc: điều gì có thể sai?

### 8.1. Dữ liệu mới chen vào đầu danh sách

Trang 1 lúc 10:00:

~~~text
T100, T099, T098, T097, T096
Cursor = T096
~~~

Tới 10:01 có đơn `T101` mới. Nếu request trang 2 dùng cursor seek `created_at < T096`, nó tiếp tục sau mốc cũ. Điều này giữ tương đối ổn định quá trình duyệt về phía cũ, nhưng **sẽ không bao gồm T101** trong lượt duyệt đã bắt đầu. Đó có thể là hành vi đúng của infinite scroll.

Nếu dùng offset, trang 2 có thể bị **lặp** hàng từ trang trước vì một hàng mới chèn lên đầu làm dịch vị trí offset.

### 8.2. Hàng bị xóa sau trang trước

Khi row trước mốc bị xóa, offset có thể khiến một số hàng bị **bỏ qua** do số thứ tự thay đổi. Seek theo khóa thường ít nhạy với sự thay đổi **trước mốc**, nhưng không cung cấp snapshot/transaction: dữ liệu mới, xóa, TTL hoặc sửa khóa ở vùng chưa duyệt vẫn có thể ảnh hưởng nội dung.

### 8.3. Sửa clustering key là thay row logic

Nếu `created_at` hoặc `order_id` nằm trong primary key, việc đổi chúng không phải cập nhật field thường. Cassandra coi một primary key mới là địa chỉ row khác; phải xử lý row cũ và read model khác có kiểm soát.

Do đó:

- Dùng khóa tạo sự kiện ổn định khi có thể.
- Đừng đặt một trạng thái thường thay đổi như `status` làm clustering key của timeline chỉ vì muốn sort theo nó.
- Nếu phải di chuyển row giữa các bảng/bucket, cần quy trình cập nhật/xóa và đối soát.
- Xác định cách xử lý trùng/thiếu trong cursor khi data contract cho phép dữ liệu thay đổi.

### 8.4. Consistency level không tạo snapshot xuyên nhiều trang

`LOCAL_QUORUM` yêu cầu quorum replica trong DC cục bộ; nó không tạo snapshot xuyên toàn bộ sequence `page1 → page2 → page3`. Với nhiều request cách nhau vài giây, trạng thái dữ liệu có thể khác nhau.

Nếu nghiệp vụ cần một báo cáo chính xác “dữ liệu tại 00:00 ngày 25/11”, dùng một quy trình snapshot/materialization riêng với contract rõ ràng, thay vì kỳ vọng phân trang thông thường của Cassandra cố định toàn bộ tập kết quả.

## 9. Phân trang qua nhiều bucket hoặc nhiều partition

Bảng `orders_by_customer_month` dùng `month_bucket` trong partition key để giới hạn kích thước partition:

~~~text
(customer A, 2026-11) -> các đơn tháng 11, sort DESC
(customer A, 2026-10) -> các đơn tháng 10, sort DESC
(customer A, 2026-09) -> các đơn tháng 09, sort DESC
~~~

Nếu UI hiển thị lịch sử theo thời gian trên nhiều tháng, có hai cách:

**Duyệt bucket tuần tự:** Đọc hết tháng mới nhất theo cursor, sau đó chuyển sang tháng trước. Cursor ứng dụng lưu `month_bucket` và state/lastKey trong bucket. Cách này đơn giản nếu thời gian của các bucket không chồng nhau và quy tắc bucket chính xác.

**Merge nhiều partition:** Khi dữ liệu thuộc nhiều partition/shard có thể xen kẽ nhau theo thời gian, service phải fetch các dòng đầu của mỗi nguồn và merge bằng thứ tự chung. Cursor cần lưu tiến độ cho **từng nguồn**, giới hạn số nguồn song song, byte và thời gian xử lý.

Không có một driver paging state tự biến các truy vấn của nhiều bucket thành global merge có thứ tự. Lập trình viên phải quản lý phần đó.

### 9.1. Thiết kế bucket dựa trên tải

| Lựa chọn | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| `customer_id` đơn lẻ | Query đơn giản | Partition có thể tăng vô hạn/hot |
| `(customer_id, month_bucket)` | Giới hạn partition theo tháng | Lịch sử nhiều tháng cần điều phối |
| `(customer_id, day_bucket)` | Partition nhỏ hơn | Nhiều request/partitions cho lịch sử dài |
| Thêm shard | Phân tán tải cao | Cursor/merge phức tạp hơn |

Chọn bucket theo độ lớn partition, tốc độ ghi, độ rộng row, request rate và yêu cầu UI, không chỉ dựa vào lịch biểu. Một user rất lớn có thể cần bucket theo ngày/shard; một user ít hoạt động có thể chấp nhận bucket tháng.

### 9.2. Projection và giới hạn kích thước payload

Với danh sách, chỉ lấy những cột UI cần:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Tránh `SELECT *` nếu row chứa UDT/collection hoặc payload lớn không cần thiết. Interface projection/DTO của Spring Data có thể giúp tổ chức kiểu trả về, nhưng **không tự bảo đảm Cassandra chỉ đọc đúng vài cột** trong mọi API/phiên bản. Kiểm tra CQL thực tế và sử dụng column selection tường minh khi cần tối ưu.

Nếu kết quả mỗi row quá rộng, giảm page size có thể giảm đỉnh memory nhưng số round-trip tăng. Cần đo p95/p99, page count, bytes và độ trễ server.

## 10. Thiết kế hợp đồng REST phù hợp Cassandra

### 10.1. Endpoint đề xuất

~~~http
GET /customers/{customerId}/orders?month=2026-11&limit=20
~~~

Trả:

~~~json
{
  "items": [
    {
      "orderId": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      "createdAt": "2026-11-25T10:00:00Z",
      "status": "PAID",
      "totalAmount": "150000.00"
    }
  ],
  "limit": 20,
  "hasMore": true,
  "nextCursor": "opaque-signed-token"
}
~~~

Request tiếp:

~~~http
GET /customers/{customerId}/orders?month=2026-11&limit=20&cursor=opaque-signed-token
~~~

Giải thích contract:

- `limit` được server giới hạn trong dải hợp lệ (ví dụ 1–100, tùy đo đạc).
- `cursor` gắn với `customerId`, `month`, sort, filter, page size và quyền truy cập.
- `nextCursor` chỉ xuất hiện nếu còn dữ liệu có thể đọc tiếp.
- Không hứa có `totalPages` nếu không có cơ chế duy trì tổng riêng.
- API trả 400 cho cursor sai định dạng/không hợp lệ, 403 khi không được phép truy cập partition, hoặc mã lỗi thích hợp theo hợp đồng.
- Không chấp nhận caller thay cursor sang customer ID khác mà không xác thực.

### 10.2. Vì sao nên dùng “Xem thêm”/infinite scroll?

Một timeline đơn hàng, thông báo hoặc sự kiện thường được xem từ mới đến cũ. Người dùng có nhu cầu tìm **mốc thời gian** hơn là “trang số 845”. UI có thể:

- Hiển thị các dòng mới nhất và nút **Xem thêm**.
- Cho phép lọc theo tháng/năm.
- Hiển thị “Đang hiển thị 20 đơn gần nhất” thay vì “Trang 1/237”.
- Nếu cần thống kê, hiển thị một con số **ước lượng có mốc thời gian** riêng với danh sách.
- Cho phép quay lại các trang đã xem bằng history của cursor.

Đây không phải hạ cấp chức năng; đây là giao diện phù hợp với mô hình dữ liệu phân tán và giúp giảm đòi hỏi count/offset tốn kém.

### 10.3. Khi business thật sự đòi Page

Giả sử back-office bắt buộc có “Tổng 12.473 kết quả” và “đến trang 300”. Có thể kiến trúc riêng:

1. Người dùng gửi bộ lọc, tạo **report job** có định danh và thời điểm as-of.
2. Job materialize kết quả theo thứ tự ổn định, cùng snapshot logic/cơ chế đối soát được định nghĩa.
3. Lưu manifest, tổng số bản ghi, checkpoint theo từng block/trang hoặc định dạng tệp tải xuống.
4. Back-office truy cập trang theo checkpoint của **report**, không trực tiếp bằng offset Cassandra.
5. Hết hạn report và dọn dữ liệu; nêu rõ tổng trang thuộc **phiên bản báo cáo**, không phải trạng thái live.

Phương án này tốn tài nguyên nhưng có contract rõ ràng. Nếu người dùng chỉ cần tìm một đơn, thêm bộ lọc theo ID/time/status thường ít tốn kém hơn việc dựng một hệ thống trang số lớn.

## 11. Lưu ý về bảo mật cursor và phiên bản dữ liệu

Cursor có thể vô tình trở thành cơ chế vượt quyền nếu người dùng sửa/đổi `customerId` hoặc `tenantId`. Cần lưu ít nhất:

- Phiên bản schema/query/cursor để từ chối token cũ khi thay logic.
- Partition identity, filter và sort order.
- Khóa cuối hoặc paging state (opaque), cùng page size.
- Thời điểm phát hành/hết hạn nếu contract cần.
- Chữ ký/HMAC hoặc state server-side, không để sửa token tự do.
- Authorization kiểm tra lại ở **mỗi request**, không chỉ ở trang đầu.

Một cursor được ký vẫn có thể chứa dữ liệu đọc được nếu chỉ base64-encode. Nếu token chứa thông tin nhạy cảm, mã hóa hoặc lưu server-side thay vì chỉ ký. Không log nguyên văn cursor nhạy cảm vào hệ thống quan sát nếu không cần.

Khi thay đổi CQL/filter/sort hoặc deployment làm metadata driver/schema không tương thích, nên báo cursor đã hết hạn và yêu cầu client quay lại trang đầu. Không cố sử dụng paging state cũ với một câu query mới.

## 12. Vận hành: hiệu năng, consistency và giới hạn tài nguyên

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| p50/p95/p99 cho mỗi page | Page nào chậm, đầu hay sâu trong partition? |
| Request timeout, unavailable | Thiếu replica, server chậm hay query quá rộng? |
| Số page được fetch trong một API call | Có vô tình duyệt toàn ResultSet không? |
| Kích thước payload và số row/page | Page size phù hợp row width/UDT/collection chưa? |
| Partition size/hot keys | Có partition quá lớn hoặc ghi/đọc tập trung? |
| Tombstone/compaction | TTL/xóa làm đọc nhiều dấu xóa? |
| Pool in-flight/retry/speculative attempts | Driver có thêm request làm quá tải? |
| Cursor invalid/expired rate | API thay filter/token, schema deploy hay token quá hạn? |
| Projection lag giữa các bảng | Đọc danh sách có trễ so với bảng chi tiết? |
| Chi phí COUNT / aggregate freshness | Tổng có quá đắt hoặc quá stale? |

### 12.1. Chọn consistency phù hợp

Trong keyspace RF=3 ở một DC, `LOCAL_QUORUM` thường đòi hai replica phản hồi; `LOCAL_ONE` cần một và có thể đọc dữ liệu cũ hơn. Nhưng **cả hai** không bảo đảm count và các trang đọc cách nhau nhiều giây là một snapshot giao dịch.

Nếu `orders_by_id` cập nhật ngay nhưng `orders_by_customer_month` được projector cập nhật chậm, danh sách có thể trễ dù truy vấn nó ở `LOCAL_QUORUM`. Đó là vấn đề **đồng bộ read model**, khác với replica consistency.

### 12.2. Giới hạn page size và backpressure

Không để client tự yêu cầu `limit=1000000` rồi đọc hết partition. Nên giới hạn:

- Page size tối đa phù hợp row width và p99.
- Thời gian request và số trang/byte cho công việc tổng.
- Số export/long scan đồng thời.
- Mức retry và speculative execution cho truy vấn idempotent.
- Số partition được fan-out trong một request.
- Bộ nhớ khi chuyển row thành entity/DTO và khi serialize JSON.

Nếu API cần xuất hàng triệu row, sử dụng job/stream có backpressure, không `List` tất cả vào RAM và trả JSON trong một request HTTP.

## 13. Thực hành: thiết kế một API phân trang đúng

### 13.1. Đề bài

Một ứng dụng thương mại có yêu cầu:

- Xem lịch sử đơn theo khách hàng, mới nhất trước.
- Mỗi lần trả tối đa 20 đơn.
- Có nút “Xem thêm” và có thể quay lại phần đã đọc.
- Có thể lọc theo tháng.
- Không yêu cầu tổng số đơn chính xác theo thời gian thực.
- Khi cần, dashboard riêng hiển thị số đơn ước lượng theo ngày.

### 13.2. Bước 1 — Dùng bảng theo truy vấn

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
~~~

Đảm bảo `created_at` và `order_id` ổn định, `month_bucket` được tính nhất quán theo múi giờ/chính sách nghiệp vụ. Nếu dữ liệu quá lớn trong tháng, đánh giá bucket theo ngày hoặc thêm shard có kiểm soát.

### 13.3. Bước 2 — Query đầu

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 21;
~~~

Đọc tối đa 21 row để trả 20 và xác định `hasMore`. Nếu code chỉ dùng Spring Data `Slice`, ưu tiên cơ chế hasNext/cursor do module cung cấp; không cần tự truy vấn 21 row nếu framework đã quản lý phần lookahead/paging.

### 13.4. Bước 3 — Cursor theo key

Lấy khóa `(lastCreatedAt, lastOrderId)` của row cuối **đã được trả**, rồi trang sau:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
  AND (created_at, order_id) < (?, ?)
LIMIT 21;
~~~

Kiểm tra với dữ liệu có timestamp trùng; không dùng mốc chỉ chứa `created_at`. Nếu dùng Java Driver paging state thay vì keyset, giữ query và values nguyên vẹn và chuyển state theo API phù hợp.

### 13.5. Bước 4 — Đặt hạn mức và hợp đồng lỗi

- `limit` do server giới hạn.
- Cursor được ký hoặc lưu server-side, có thời hạn/phiên bản.
- Từ chối cursor khác customer/tháng/filter.
- Nếu cursor không còn hợp lệ sau deployment, trả lỗi cụ thể và đề nghị tải lại từ đầu.
- Tránh phát lại dữ liệu nhạy cảm của tenant khác khi user đổi URL.

### 13.6. Bước 5 — Kiểm tra các tình huống

| Ca kiểm thử | Điều cần quan sát |
| --- | --- |
| Khách có 0 đơn | `items=[]`, `hasMore=false` |
| Khách có đúng 20 đơn | Không trả cursor giả khi hết |
| Khách có 21 đơn | Trang 1 có 20, trang 2 có một |
| Nhiều đơn cùng timestamp | Không bỏ sót/trùng vì có `order_id` phân biệt |
| Thêm đơn mới sau trang 1 | Cursor seek tiếp từ khóa cũ; xác định policy với đơn mới |
| Xóa một đơn trước khóa cursor | Tránh lỗi offset dịch vị trí; kiểm tra kết quả |
| Thay month/filter rồi dùng cursor cũ | Từ chối hoặc yêu cầu bắt đầu lại |
| Dùng cursor customer A cho customer B | Từ chối vì ràng buộc auth/partition |
| Truy vấn qua hai bucket | Có logic chuyển bucket, không dùng cùng paging state |
| Mất replica ở RF3/LOCAL_QUORUM | Kiểm tra availability, p99 và retry |
| Partition rất lớn | Đo latency/tombstone; cân nhắc bucketing khác |
| UI yêu cầu page 100 trực tiếp | Trả UX thích hợp hoặc dùng report/checkpoint riêng, không quét sâu trong request |

## 14. Sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`Page<T>` có sẵn thì Cassandra cũng có OFFSET.” | Interface Java không tạo khả năng nhảy offset trong database |
| “`totalPages` là metadata miễn phí.” | Cần biết tổng số hàng, có thể phải đếm đắt hoặc duy trì aggregate |
| “`COUNT(*)` nhanh như đọc một giá trị.” | Có thể quét nhiều row/partition, rất đắt khi dữ liệu lớn |
| “`pageSize=20` nghĩa là chỉ lấy tổng cộng 20 row.” | Page size là số mục tiêu mỗi lần fetch; tổng được giới hạn bởi CQL `LIMIT` hoặc logic ứng dụng |
| “`LIMIT 20` là đủ để lấy trang 2.” | Cần cursor/state hoặc điều kiện seek; LIMIT chỉ giới hạn số hàng |
| “Paging state chứa số trang có thể tự tính.” | Token opaque dùng để tiếp tục query, không phải offset |
| “Chỉ cần `PageRequest.of(100,20)` là nhảy đến trang 101.” | Cassandra không có truy cập ngẫu nhiên bằng offset tổng quát |
| “Cursor theo timestamp đủ rồi.” | Timestamp trùng có thể khiến bỏ sót; cần tie-breaker ổn định |
| “Trang 100 hôm nay là cùng dữ liệu với ngày mai.” | Ghi/xóa làm thay đổi vị trí; cần định nghĩa as-of |
| “`LOCAL_QUORUM` bảo đảm page 1–10 một snapshot.” | CL không cung cấp transaction xuyên nhiều request |
| “Trang từ hai tháng cùng dùng một paging state.” | Mỗi query/bucket cần tiến độ riêng và logic ghép |
| “Projection nhỏ tự bảo đảm Cassandra đọc ít cột.” | Cần xác minh CQL/column selection |
| “Counter tăng một lần cho mọi upsert sẽ là total chính xác.” | Retry/upsert không đồng nghĩa thêm row mới; counter có thể đếm trùng |
| “Cursor base64 là đủ bảo mật.” | Base64 chỉ là biểu diễn; cần bảo vệ token và kiểm tra quyền |
| “Muốn nhảy trang sâu thì fetch qua các trang trước trong HTTP request.” | Chi phí tăng theo độ sâu, gây timeout/tải không dự báo |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Page.getTotalPages()` không thể suy trực tiếp từ một `Slice` Cassandra?

*Gợi ý:* `Slice` chỉ biết nội dung hiện tại và khả năng còn trang tiếp; không chứa tổng số hàng.

**Câu 2.** Cassandra có hỗ trợ tổng quát `OFFSET 1000 LIMIT 20` như SQL quan hệ không?

*Đáp án:* Không. Dùng paging state/cursor hoặc seek theo khóa được thiết kế phù hợp.

**Câu 3.** Vì sao `SELECT COUNT(*)` trên một bảng lớn có thể ảnh hưởng mạnh tới p99?

*Gợi ý:* Đếm có thể phải quét rất nhiều dữ liệu và tombstone, không phải metadata miễn phí.

**Câu 4.** Khác nhau giữa `LIMIT 20`, `pageSize=20` và `hasMore` là gì?

*Gợi ý:* Tổng hàng tối đa của query, mục tiêu mỗi lần fetch và việc còn dữ liệu để tiếp tục.

**Câu 5.** Tại sao cursor chỉ chứa `created_at` có thể làm mất row khi các đơn có cùng thời điểm?

*Gợi ý:* Cần tie-breaker clustering key đủ phân biệt, như `order_id`.

**Câu 6.** Khi seek trong clustering order `created_at DESC, order_id DESC`, vì sao phải ghi nhớ **hàng cuối đã trả** chứ không phải hàng lookahead?

*Gợi ý:* Nếu dùng lookahead làm mốc, hàng đó chưa hiển thị có thể bị bỏ qua.

**Câu 7.** `CassandraPageRequest` giúp hỗ trợ thao tác gì?

*Gợi ý:* Tiếp tục trang theo state, không nhảy đến offset bất kỳ.

**Câu 8.** Nếu bảng danh sách được cập nhật chậm hơn bảng chi tiết, nâng CL có làm đồng bộ hai bảng không?

*Gợi ý:* Không; đó là projection lag ở tầng ứng dụng.

**Câu 9.** Khi UI thực sự cần tổng số chính xác ở một mốc thời gian, nên cân nhắc kiến trúc gì?

*Gợi ý:* Snapshot/materialization/report job với version và checkpoint rõ ràng.

**Câu 10.** Vì sao không nên tin tổng trang khi có ghi/xóa đồng thời?

*Gợi ý:* Đếm và đọc nội dung có thể ở những thời điểm khác nhau, không có snapshot giao dịch xuyên request.

**Câu 11.** Nếu cursor chứa customer ID và bucket, chỉ ký token đã đủ để ngăn đọc chéo tenant chưa?

*Gợi ý:* Chưa. Phải kiểm tra authorization ở mỗi request.

**Câu 12.** Vì sao tăng page size từ 20 lên 10.000 có thể làm API chậm hơn?

*Gợi ý:* Payload/memory/giải mã tăng, chưa kể tombstone, partition nóng và network.

## 16. Checklist áp dụng vào production

- **Đúng access pattern:** bảng, partition key và clustering order phục vụ đúng danh sách cần đọc.
- **Chọn hợp đồng API:** ưu tiên Next/Back/hasMore với Slice/cursor; chỉ thêm total khi có nguồn số liệu rõ.
- **Không giả định offset:** page number là UI metadata, không phải một địa chỉ ngẫu nhiên trong Cassandra.
- **Có cursor ổn định:** dùng paging state với cùng query hoặc keyset có đủ tie-breaker.
- **Bảo vệ token:** ký/mã hóa hoặc lưu server-side; xác thực tenant và filter ở mỗi request.
- **Kiểm soát thay đổi:** cursor có phiên bản/hạn sử dụng, hợp đồng rõ khi dữ liệu chèn/xóa hoặc schema thay đổi.
- **Giới hạn tài nguyên:** page size, byte, concurrency, fan-out bucket, deadline, retry/speculation.
- **Projection tối thiểu:** chỉ chọn các cột cần cho danh sách, xác minh CQL thật.
- **Tổng số bản ghi:** nếu phải đếm, đo chi phí; aggregate/counter cần idempotency và đối soát.
- **Nhiều partition:** có quy tắc đi qua/merge bucket, không kỳ vọng global order tự động.
- **Quan sát:** p95/p99, số page/fetch, timeout, unavailable, tombstone, partition size và projection lag.
- **Kiểm thử biên:** 0/20/21 hàng, timestamp trùng, cursor sai, insert/delete cạnh tranh, read model trễ, multi-DC.
- **Tài liệu UX:** nêu rõ danh sách có tính live hay as-of, tổng là estimated hay exact, quyền hạn “nhảy trang” thực sự đến đâu.

## Tài liệu tham khảo

- [Spring Data Cassandra Reference](https://docs.spring.io/spring-data/cassandra/reference/): paging, `CassandraPageRequest`, repository và query operations.
- [Spring Data Commons – Paging and Sorting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): ý nghĩa `Page`, `Slice`, `Pageable` và metadata.
- [Apache Cassandra Java Driver 4.x – Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): `ResultSet`, `AsyncResultSet`, paging state và fetch-next-page.
- [Apache Cassandra CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): `SELECT`, `LIMIT`, primary keys, clustering order và restrictions.
- [Apache Cassandra Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html): thiết kế bảng theo truy vấn, partition/bucketing và giới hạn hệ thống phân tán.

## Kết luận

**`Page<T>`, tổng số trang và truy cập trang ngẫu nhiên** là những tiện ích quen thuộc ở cơ sở dữ liệu quan hệ, nhưng chúng không miễn phí và không tương ứng trực tiếp với mô hình truy cập của Cassandra. Một `Slice<T>` hoặc cursor cho biết cách **đọc tiếp**, trong khi `Page<T>` còn đòi hỏi tổng số hàng, và nút nhảy trang cần khả năng định vị offset mà Cassandra không cung cấp tổng quát.

Trong **SPRING_DATA_CASSANDRA**, hãy ưu tiên **query theo partition key, clustering order ổn định, `CassandraPageRequest`/paging state hoặc seek theo khóa** và API “Xem thêm”. Nếu nghiệp vụ thật sự cần tổng và nhảy trang, hãy thiết kế aggregate, checkpoint hoặc snapshot/report có SLA và phiên bản dữ liệu riêng. Cuối cùng, phải kiểm soát consistency, paging, projection, cursor security, đồng thời theo dõi hiệu năng và thử nghiệm với dữ liệu đổi liên tục để bảo đảm API phân trang hoạt động đúng trong hệ thống Cassandra phân tán.
