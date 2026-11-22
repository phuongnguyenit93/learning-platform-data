# Tối ưu số lượt truy vấn, N+1 và lựa chọn dữ liệu cần trả

Một endpoint REST trả đúng dữ liệu nhưng mất 1,5 giây vẫn có thể là một API kém chất lượng. Với hệ thống Java/Spring, nguyên nhân thường không nằm ở một câu SQL đặc biệt chậm mà là **một trang kết quả kéo theo hàng chục hoặc hàng trăm câu truy vấn**; hoặc server đọc cả đồ thị entity, tính tổng, serialize quá nhiều trường trong khi client chỉ cần vài thông tin. Muốn tối ưu đúng, phải xem toàn bộ đường đi: **hợp đồng HTTP → truy vấn dữ liệu → ánh xạ DTO → số byte phản hồi → hành vi client**.

Bài này thuộc chương **Hiệu năng** của module `INTEGRATION_API_REST`. Người học sẽ phân biệt N+1 với query chậm đơn lẻ, nhận biết các kiểu tải dữ liệu của JPA/Hibernate, dùng projection và fetch plan phù hợp, phân trang có giới hạn, quan sát query count/latency, kiểm thử hồi quy hiệu năng và bảo đảm rằng tối ưu không làm lộ dữ liệu hoặc đổi hợp đồng REST ngoài ý muốn.

**Thông điệp chính:** giảm số lượt round-trip tới database là quan trọng, nhưng **ít truy vấn hơn không đồng nghĩa luôn nhanh hơn**. Một câu `JOIN` trả hàng trăm nghìn dòng, giữ khóa lâu và truyền dữ liệu dư thừa có thể tệ hơn hai truy vấn hẹp. Mục tiêu là **đúng dữ liệu, đúng quyền, số hàng và số byte vừa đủ, trong giới hạn độ trễ đã xác định**.

## 1. Đặt bài toán bằng số liệu trước khi sửa code

Giả sử `GET /v1/orders?page=0&size=20` trả danh sách 20 đơn hàng. Frontend chỉ hiển thị mã đơn, thời điểm tạo, trạng thái và tổng tiền; khi người dùng mở chi tiết mới cần dòng hàng, địa chỉ, lịch sử thanh toán.

Một phiên bản chưa tối ưu có thể thực hiện:

~~~text
1 SQL SELECT danh sách 20 đơn hàng                  18 ms
20 SQL SELECT khách hàng cho từng đơn            20 × 7 ms
20 SQL SELECT dòng hàng cho từng đơn             20 × 8 ms
20 SQL SELECT chi tiết sản phẩm                   20 × 5 ms
Serialize entity + response body                     35 ms
Tổng gần đúng (nếu thực hiện tuần tự)                 453 ms
~~~

Đây là số đo **minh họa**, không phải benchmark tổng quát. Cùng code có thể nhanh khi DB rất gần và cache ấm, nhưng p95 tăng mạnh khi có mạng chéo vùng, connection pool chật hoặc dữ liệu nhiều. Nếu một trang 20 dòng làm 61 query thì khi tăng `size=100` có nguy cơ tạo khoảng 301 query. Tải tăng theo số phần tử trả về, dù endpoint nhìn bên ngoài vẫn chỉ là **một HTTP GET**.

### Phân rã latency từ góc nhìn người dùng

~~~mermaid
flowchart LR
    C[Client gửi GET] --> G[Gateway/Ingress]
    G --> A[Spring MVC + xác thực]
    A --> D[Repository / Database]
    D --> M[Map DTO + serialize]
    M --> R[Truyền HTTP response]
    R --> C
~~~

Thời gian response có thể chứa: chờ request vào server, lấy connection từ pool, truyền query tới DB, DB scan/sort/join, nhận từng row, lazy loading, map DTO, JSON serialization, nén và truyền qua mạng. Vì thế cần tối thiểu:

| Chỉ số | Đơn vị/cách phân nhóm | Dấu hiệu |
| --- | --- | --- |
| `http.server.request.duration` p50/p95/p99 | Route template, method, status | Endpoint có tail latency cao hay không |
| Số câu SQL mỗi HTTP request | Route, nhóm code/repository | Có N+1 hoặc truy vấn lặp không |
| DB query duration, rows read/returned | Query fingerprint | Một query đơn lẻ quá nặng |
| Connection acquisition/wait | Pool, application instance | Tắc tại pool chứ không phải SQL |
| Response body bytes + serialization time | Route, response shape | DTO quá rộng hoặc collection quá lớn |
| Heap/GC, CPU, concurrency | Process/container | Tải object/serialize lớn hoặc bị quá tải |

Một thay đổi chỉ được coi là tối ưu khi cải thiện **độ trễ và tài nguyên trong tải đại diện**, không chỉ khi số query giảm trong unit test.

## 2. N+1 query là gì và vì sao xuất hiện?

**N+1** là mẫu truy xuất trong đó có một query lấy `N` phần tử gốc, sau đó mỗi phần tử lại kích hoạt một query phụ (hoặc hơn). Đối với Hibernate/JPA, quan hệ lazy là nơi dễ thấy nhất.

Ví dụ mô hình tối giản:

~~~java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Column(nullable = false)
    private UUID tenantId;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private CustomerEntity customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    // getters và các thuộc tính khác được lược bớt
}
~~~

Code tạo N+1:

~~~java
List<OrderEntity> orders = repository.findAllByTenantId(tenantId);
List<String> customerNames = new ArrayList<>();
for (OrderEntity order : orders) {
    customerNames.add(order.getCustomer().getDisplayName());
}
~~~

Khi transaction/persistence context đang mở và các `CustomerEntity` chưa được tải, gọi `getDisplayName()` trên proxy có thể khiến Hibernate phát thêm SQL. Dạng SQL thường thấy:

~~~sql
-- Một câu truy vấn danh sách.
SELECT id, tenant_id, customer_id, status
FROM orders WHERE tenant_id = ?;

-- Sau đó là truy vấn lặp cho từng customer_id chưa có trong context.
SELECT id, display_name FROM customers WHERE id = ?;
SELECT id, display_name FROM customers WHERE id = ?;
-- ... tiếp tục với các khách hàng khác.
~~~

Với 50 order có 50 khách hàng khác nhau, ta có thể thấy **1 + 50 = 51 câu SQL**. Đây không phải con số bất biến: nếu nhiều order cùng khách hàng hoặc cache/persistence context đã có dữ liệu, số query phụ có thể thấp hơn. Không được “chứng minh đã hết N+1” chỉ vì chạy thử trên fixture mà mọi đơn cùng một customer.

**N+1 cũng có thể xảy ra khi:**

- Serialize entity JPA trực tiếp thành JSON: Jackson đi qua `getLines()`, `getCustomer()` rồi tự kích hoạt lazy load.
- Mapping DTO trong vòng lặp có `order.getLines().size()` hoặc `line.getProduct().getName()`.
- Gọi `repository.count...()` hoặc `findBy...()` riêng cho mỗi order để lấy tổng số phần tử.
- Service gọi HTTP API inventory/pricing từng SKU (`N` remote round-trip), dù không liên quan Hibernate.
- Resolver/mapper thực hiện truy vấn phụ cho từng đối tượng trong collection hoặc trang kết quả.

Không phải lỗi chỉ do `FetchType.LAZY`. Một quan hệ `EAGER` cũng có thể được ORM tải bằng **secondary selects** tùy kiểu query/fetch plan; việc chuyển mọi quan hệ thành EAGER thường làm tải dữ liệu thừa và tạo N+1 ở nơi khác.

### Nguy cơ của Open Session in View (OSIV)

Khi JPA persistence context còn mở trong lúc serialize response (ví dụ cấu hình OSIV), việc trả thẳng `List<OrderEntity>` có thể kích hoạt query **sau khi service kết thúc**, khiến query count khó kiểm soát, security/data exposure khó đánh giá và timeouts khó hiểu. Khi OSIV tắt, cùng code có thể nhận `LazyInitializationException`. Cách an toàn hơn là **quyết định fetch plan và ánh xạ DTO bên trong service transaction**, rồi trả một response object đã materialize đầy đủ.

Trong Spring Boot, có thể cân nhắc:

~~~yaml
spring:
  jpa:
    open-in-view: false
~~~

Tắt OSIV không tự sửa N+1; nó buộc ứng dụng xử lý việc tải dữ liệu một cách tường minh ở tầng repository/service. Cần kiểm tra các endpoint cũ trước khi đổi cấu hình.

## 3. Thiết kế response dựa trên use case, không dựa trên entity

**Câu hỏi đầu tiên không phải “làm thế nào join mọi bảng?” mà là “client thực sự cần dữ liệu nào?”**

Hai resource/representation khác nhau:

~~~http
GET /v1/orders?page=0&size=20 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-store

{
  "data": [
    {
      "id": "8a47aa2f-3c47-4b18-982e-4486bbac3e21",
      "createdAt": "2026-11-18T08:00:00Z",
      "status": "CONFIRMED",
      "totalMinorUnits": 350000,
      "currency": "VND"
    }
  ],
  "page": 0,
  "size": 20,
  "hasNext": true
}
~~~

Response của **list** không có `lineItems`, payment history hay customer profile. Khi mở chi tiết:

~~~http
GET /v1/orders/8a47aa2f-3c47-4b18-982e-4486bbac3e21 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "8a47aa2f-3c47-4b18-982e-4486bbac3e21",
  "status": "CONFIRMED",
  "totalMinorUnits": 350000,
  "currency": "VND",
  "lineItems": [
    {
      "sku": "BOOK-42",
      "quantity": 2,
      "unitMinorUnits": 175000
    }
  ]
}
~~~

Ở đây `totalMinorUnits` là một lựa chọn hợp đồng tiền tệ: dùng số nguyên đơn vị nhỏ nhất theo quy ước tiền tệ, tránh sai số nhị phân. Trường và đơn vị phải được định nghĩa rõ trong OpenAPI; ví dụ VND là đơn vị đồng nên cần nhất quán với quy ước lưu trữ. Dùng `BigDecimal` hoặc chuỗi decimal cũng được nếu schema và serializer được kiểm thử tương thích.

### Không serialize entity thẳng ra Internet

~~~java
// Anti-pattern: entity là model nội bộ, không phải hợp đồng API.
@GetMapping("/v1/orders")
public List<OrderEntity> list() {
    return orderRepository.findAll();
}
~~~

Đoạn code này có ít nhất năm nguy cơ: không lọc tenant, không phân trang, làm lộ field nội bộ, vòng tham chiếu JSON, và kích hoạt N+1 khi Jackson duyệt quan hệ. Dùng **response DTO/projection riêng**: API list trả ít field; API detail trả dữ liệu đã xác minh và cần thiết.

Những câu hỏi nên có khi thiết kế DTO:

1. Field nào cần để vẽ màn hình đầu tiên? Field nào chỉ cần khi mở chi tiết?
2. Field nào có thể nặng như blob, rich text, history hoặc collection rất lớn?
3. Có nên trả một link/ID tới resource phụ thay vì nhúng toàn bộ không?
4. Những trường nào thay đổi nhanh khiến cache bị invalidation liên tục?
5. Field nào thuộc phạm vi quyền khác (địa chỉ, email, số điện thoại, giá vốn)?

Chọn response hẹp **vừa giảm SQL/serialization vừa giảm bề mặt rò rỉ dữ liệu**, nhưng phải luôn kết hợp authorization ở tầng truy vấn/service.

## 4. DTO projection: chỉ đọc đúng cột cần thiết

Với Spring Data JPA, nếu list chỉ cần 5 cột, không cần load cả `OrderEntity` rồi đi qua relationship graph. Có thể dùng **JPQL constructor projection**:

~~~java
package com.example.orders.api;

import java.time.Instant;
import java.util.UUID;

public record OrderSummary(
    UUID id,
    Instant createdAt,
    OrderStatus status,
    long totalMinorUnits,
    String currency
) {}
~~~

Tạo repository truy vấn theo tenant đã xác thực:

~~~java
package com.example.orders.persistence;

import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import com.example.orders.api.OrderSummary;

public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {
    @Query("""
        select new com.example.orders.api.OrderSummary(
            o.id, o.createdAt, o.status, o.totalMinorUnits, o.currency)
        from OrderEntity o
        where o.tenantId = :tenantId
        order by o.createdAt desc, o.id desc
        """)
    Slice<OrderSummary> findSummaries(
        @Param("tenantId") UUID tenantId,
        Pageable pageable
    );
}
~~~

Giả định `OrderEntity` có các field `createdAt` (`Instant`), `totalMinorUnits` (`long`), `currency` (`String`) và enum `OrderStatus`; chúng được lược bớt ở entity ví dụ mục 2 để bài tập trung vào fetch. Tên gói `com.example.orders.api` phải khớp record thực tế vì JPQL constructor expression sử dụng tên class đầy đủ.

**Lợi ích:** Hibernate chỉ chọn các cột cần thiết cho response, không khởi tạo toàn bộ entity và không cần tải `lines/customer`. Không phải toàn bộ hoạt động DB sẽ giảm xuống 0; với mỗi trang vẫn có truy vấn dữ liệu, nhưng loại bỏ một nguồn N+1 rất lớn.

**Cẩn trọng:** projection có expression hoặc join vẫn có thể tạo query nặng; việc gọi getter có điều kiện trên một entity bổ sung lại có thể kích hoạt lazy load. Interface-based projection cũng cần kiểm tra SQL thực sinh ra, đặc biệt khi truy cập nested property; không mặc định rằng projection lồng luôn hẹp.

### Service và controller có giới hạn trang

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

public record OrderListResponse(
    List<OrderSummary> data, int page, int size, boolean hasNext
) {}

@Service
public class OrderQueryService {
    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public OrderListResponse list(UUID trustedTenantId, int page, int size) {
        // Validate trước khi cấp phép cấp phát danh sách rất lớn.
        if (trustedTenantId == null || page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException("invalid paging");
        }
        Slice<OrderSummary> result =
            repository.findSummaries(trustedTenantId, PageRequest.of(page, size));
        return new OrderListResponse(
            result.getContent(), page, size, result.hasNext()
        );
    }
}
~~~

Controller HTTP tương ứng:

~~~java
@GetMapping("/v1/orders")
public ResponseEntity<OrderListResponse> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        Authentication authentication) {
    UUID tenantId = trustedTenantResolver.resolve(authentication);
    OrderListResponse result = orderQueryService.list(tenantId, page, size);
    return ResponseEntity.ok()
        .header("Cache-Control", "private, no-store")
        .body(result);
}
~~~

Đoạn controller chỉ minh họa luồng; `trustedTenantResolver` phải được hiện thực từ principal/JWT đã xác thực, **không** lấy từ header `X-Tenant-ID` hoặc query parameter do client tự khai. Cần ánh xạ lỗi page/size sang 400/422 theo Problem Details thay vì để `IllegalArgumentException` thành 500. Phải cấu hình authentication và authorization cho endpoint trước khi sử dụng code trong ứng dụng thật.

`@Transactional(readOnly = true)` chỉ là gợi ý tối ưu/semantics giao dịch cho tầng persistence, **không** có nghĩa DB sẽ chặn mọi thao tác ghi và **không thay authorization**.

### `Slice` và `Page` khác nhau về chi phí

- `Slice<T>` chỉ trả danh sách trang hiện tại và có trang tiếp hay không; triển khai thường lấy thêm **một row** để biết `hasNext`. Thường **không cần COUNT tổng số row**.
- `Page<T>` thêm `totalElements` và `totalPages`, nên có thể phát thêm câu `COUNT` đắt trên bảng lớn hoặc truy vấn có join/filter phức tạp. Spring Data có các tối ưu khi suy ra được tổng số, nhưng không nên hứa luôn có hoặc luôn không có `COUNT`.
- Chỉ trả total count khi sản phẩm thực sự cần. UI cuộn vô hạn thường dùng `Slice` hoặc cursor thay vì tính lại tổng số chính xác ở mọi request.

Nếu dùng `Page` với JPQL phức tạp, viết/kiểm thử `countQuery` rõ ràng. Đừng dùng `COUNT` trên join to-many rồi quên `DISTINCT` nếu business count là số đơn hàng, vì kết quả có thể bị nhân theo số dòng hàng.

## 5. Fetch join và `@EntityGraph`: dùng đúng quan hệ, đúng ngữ cảnh

Projection rất phù hợp cho list hẹp, nhưng **trang chi tiết một đơn** cần cả tập dòng hàng. Khi đó fetch join là lựa chọn hợp lý:

~~~java
@Query("""
    select distinct o
    from OrderEntity o
    left join fetch o.lines
    where o.id = :id and o.tenantId = :tenantId
    """)
Optional<OrderEntity> findDetail(
    @Param("tenantId") UUID tenantId,
    @Param("id") UUID id
);
~~~

Với **một đơn cụ thể**, fetch `o.lines` trong một lần query có thể tránh query lazy phụ. `distinct` trong JPQL giúp biểu đạt ý định loại kết quả entity gốc trùng; SQL thực tế và cách Hibernate xử lý duplicate phụ thuộc phiên bản/provider. Vẫn phải map sang DTO trong service, không trả entity ra HTTP.

Nếu cần quan hệ *to-one* (ví dụ tên khách hàng cho một trang nhất định), có thể:

~~~java
@EntityGraph(attributePaths = {"customer"})
@Query("""
    select o from OrderEntity o
    where o.tenantId = :tenantId
    order by o.createdAt desc, o.id desc
    """)
Slice<OrderEntity> findWithCustomer(
    @Param("tenantId") UUID tenantId,
    Pageable pageable
);
~~~

Entity graph cho quan hệ *to-one* thường dễ kiểm soát cardinality hơn fetch một tập to-many. Tuy nhiên vẫn cần xem SQL, kích thước row và response mapping: có thể projection chọn cột của customer còn hẹp hơn. `@EntityGraph` không phải lời đảm bảo mọi quan hệ được tải bằng đúng một câu SQL trên mọi provider.

### Tại sao không fetch join collection rồi phân trang?

Ví dụ nguy hiểm:

~~~java
@Query("""
    select o from OrderEntity o
    left join fetch o.lines
    order by o.createdAt desc, o.id desc
    """)
Page<OrderEntity> findOrdersWithLines(Pageable pageable);
~~~

Giả sử một order có 100 lines và order kế tiếp có 1 line. SQL join trả **101 row** cho 2 order. Nếu áp `LIMIT 20` trực tiếp lên SQL đã join, có thể cắt giữa collection của order đầu tiên; ORM có thể phải tải rất nhiều row rồi phân trang **trong bộ nhớ**, hoặc ném lỗi tùy cấu hình/phiên bản Hibernate. Vừa tốn dữ liệu vừa có nguy cơ kết quả khó đoán.

Với Hibernate, cân nhắc bật kiểm tra fail-fast:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Điều này giúp phát hiện sớm một lớp anti-pattern trong test/CI. Đừng gộp nhiều quan hệ `List` to-many bằng fetch join chỉ vì muốn một SQL: có thể gây **cartesian product**, nhân số hàng theo tích kích thước collection, thậm chí lỗi fetch nhiều bag tùy mô hình Hibernate.

**Quy tắc thực hành:** Trang danh sách dùng projection; chi tiết một resource mới fetch collection có giới hạn; nếu cần “trang đơn hàng + các dòng hàng”, dùng **hai truy vấn batch** thay vì fetch collection với pagination.

## 6. Hai truy vấn batch thay cho một loạt truy vấn trong vòng lặp

Giả sử UI thật sự cần **20 order cùng tối đa vài dòng hàng mỗi order**. Thiết kế:

1. Truy vấn `Slice<OrderSummary>` lấy đúng **ID trang** và thông tin tổng quan.
2. Một câu `SELECT` lấy tất cả line item có `order_id IN (:ids)`, có lọc tenant.
3. Group by order ID, map DTO trong memory và trả response đã giới hạn.

~~~mermaid
flowchart TD
    Q[GET /v1/orders?include=lines] --> A[Query 1: 20 orders + ids]
    A --> B[Query 2: lines WHERE order_id IN ids]
    B --> M[Map groups by orderId]
    M --> R[JSON response bounded]
~~~

Projection cho dòng hàng:

~~~java
package com.example.orders.api;

import java.util.UUID;

public record OrderLineRow(
    UUID orderId, String sku, int quantity, long unitMinorUnits
) {}
~~~

Repository minh họa:

~~~java
@Query("""
    select new com.example.orders.api.OrderLineRow(
        l.order.id, l.sku, l.quantity, l.unitMinorUnits)
    from OrderLineEntity l
    where l.order.tenantId = :tenantId and l.order.id in :ids
    order by l.order.id, l.position
    """)
List<OrderLineRow> findLinesForPage(
    @Param("tenantId") UUID tenantId,
    @Param("ids") List<UUID> ids
);
~~~

Ánh xạ dữ liệu trong service sau khi đã kiểm tra pagination:

~~~java
Slice<OrderSummary> slice = orderRepository.findSummaries(
    tenantId, PageRequest.of(page, size)
);
List<OrderSummary> summaries = slice.getContent();
if (summaries.isEmpty()) {
    return List.of();
}

List<UUID> ids = summaries.stream().map(OrderSummary::id).toList();
List<OrderLineRow> rows = lineRepository.findLinesForPage(tenantId, ids);
Map<UUID, List<OrderLineRow>> byOrder =
    rows.stream().collect(Collectors.groupingBy(OrderLineRow::orderId));

return summaries.stream()
    .map(order -> new OrderWithLines(
        order, byOrder.getOrDefault(order.id(), List.of())
    ))
    .toList();
~~~

Trong ví dụ, `OrderWithLines` là DTO `record OrderWithLines(OrderSummary summary, List<OrderLineRow> lines) {}`; các import cần có `Map`, `Collectors` và các DTO/repository tương ứng. Đây là phác họa khối service, đặt trong transaction read-only; việc trả `List` chỉ để tập trung vào kỹ thuật batch, API đầy đủ vẫn cần metadata `hasNext`.

**Ưu điểm:** số câu truy vấn gần như **2** thay vì `1 + N` cho page size đã giới hạn. **Đánh đổi:** số lượng dòng hàng có thể rất lớn nếu mỗi order có hàng nghìn lines; lúc đó cần trần lines, route detail riêng hoặc pagination cho subresource. `IN` với hàng chục nghìn ID cũng có giới hạn tham số/chi phí kế hoạch; đừng bỏ trần `size`.

### Có thể dùng batch fetching thay vì tự viết IN query?

Hibernate hỗ trợ batch loading cho lazy associations (ví dụ cấu hình `hibernate.default_batch_fetch_size` hoặc `@BatchSize` theo phiên bản). Khi batch size 32, một trang 100 order có thể cần ít câu SQL hơn so với 100 câu phụ, nhưng vẫn phải đọc dữ liệu entity và có thể sinh nhiều query; số lượng còn tùy entity graph, cache và truy cập thực tế.

Ưu tiên:

- **DTO projection + explicit batch** khi muốn hợp đồng và SQL rõ ràng, dễ đo.
- **EntityGraph/fetch join** cho to-one hoặc chi tiết một resource có collection hợp lý.
- **Batch fetching** khi đã có domain model cần lazy association và đo chứng minh hiệu quả.
- **Không dùng cache như cách che N+1**: cache ấm có thể che lỗi trong test; cold cache hoặc tenant mới vẫn gặp query storm.

## 7. Phân trang, sort ổn định và index

**Giảm query count nhưng trả `findAll()` vài triệu row không phải tối ưu.** List endpoint phải có giới hạn kích thước, điều kiện lọc và thứ tự ổn định.

Ví dụ với PostgreSQL:

~~~sql
SELECT id, created_at, status, total_minor_units, currency
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT 21 OFFSET 0;
~~~

Để trả size=20 và tính `hasNext`, có thể lấy 21 row. Khi filter trạng thái:

~~~sql
SELECT id, created_at, status, total_minor_units, currency
FROM orders
WHERE tenant_id = :tenant_id AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT 21 OFFSET 0;
~~~

Các index **ứng viên**:

~~~sql
CREATE INDEX idx_orders_tenant_created_id
    ON orders (tenant_id, created_at DESC, id DESC);

CREATE INDEX idx_orders_tenant_status_created_id
    ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Không tạo index theo “công thức chung” cho mọi bảng. Index làm tăng chi phí ghi và dung lượng; selectivity, thống kê bảng, loại workload và thứ tự điều kiện quyết định index nào có ích. Index thứ hai phục vụ query **có filter status**, nhưng không nhất thiết thay thế index thứ nhất cho query **không filter status**. Chọn từ `EXPLAIN`, query log và dữ liệu thật đã ẩn danh.

### Offset pagination và vấn đề trang sâu

`OFFSET 100000 LIMIT 20` có thể buộc DB đi qua nhiều row trước khi lấy 20 row cần thiết. Đồng thời khi dữ liệu được thêm/xóa giữa các lần request, offset có thể làm **trùng hoặc thiếu** một số item.

Với bảng lớn/luồng cuộn dài, cân nhắc **keyset/cursor pagination** theo sort ổn định:

~~~sql
-- PostgreSQL: cursor chứa (created_at, id) cuối trang trước.
SELECT id, created_at, status, total_minor_units, currency
FROM orders
WHERE tenant_id = :tenant_id
  AND (
       created_at < :cursor_created_at
       OR (created_at = :cursor_created_at AND id < :cursor_id)
  )
ORDER BY created_at DESC, id DESC
LIMIT :page_size_plus_one;
~~~

Điều kiện `id < :cursor_id` trong ví dụ sử dụng thứ tự UUID được PostgreSQL hỗ trợ; nếu database hoặc kiểu ID khác không hỗ trợ so sánh như vậy, dùng khóa sắp xếp thích hợp. Cursor API nên là token opaque có kiểm tra toàn vẹn, gắn với **tenant/filter/sort/page size** của request và thời hạn nếu cần; không tin một cursor cho phép vượt filter hoặc quyền của người dùng.

Keyset giảm chi phí bỏ qua row ở trang sâu khi có index phù hợp, nhưng không tự đem lại một **snapshot nhất quán tuyệt đối**: cập nhật sort key hoặc xóa row giữa những lần đọc vẫn ảnh hưởng luồng. Nên dùng khóa sort bất biến (ví dụ createdAt + ID) và xác định rõ hợp đồng về snapshot/consistency khi cần.

### Filter cũng là quyết định hiệu năng và bảo mật

Tránh API cho phép filter/sort theo **bất kỳ field do client tự truyền** rồi nối trực tiếp vào SQL: vừa có thể gây SQL injection vừa phá index. Whitelist filter/sort, giới hạn số điều kiện và dùng parameterized query. Tất cả query phải áp điều kiện **tenant và quyền truy cập resource** server-side, không dựa vào UI chỉ gửi “đơn của tôi”.

## 8. Chỉ gửi dữ liệu cần thiết: sparse fields, include và payload budget

Một số API muốn cho client quyết định biểu diễn:

~~~http
GET /v1/orders?fields=id,status,totalMinorUnits&size=20 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
~~~

Hoặc mở rộng quan hệ có chủ đích:

~~~http
GET /v1/orders?include=lines&size=20 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
~~~

Đây là **tùy chọn thiết kế**, không phải REST buộc phải có. Nếu sử dụng:

| Vấn đề | Thiết kế an toàn |
| --- | --- |
| Field list do client đưa | Chỉ chấp nhận tập tên field được định nghĩa; từ chối unknown/unauthorized field |
| `include=lines` | Có trần số quan hệ, số cấp lồng, số item và chi phí; query batch |
| Truy vấn linh hoạt | Ánh xạ whitelist vào projection/query cố định; không ghép SQL identifier thô |
| Response cache | Query parameter là phần của cache key URI; không dùng cache chung cho dữ liệu riêng |
| Client compatibility | Cấu trúc default ổn định, contract mô tả field tùy chọn và nghĩa của field vắng |
| Tính toán server | Field đắt có thể cần endpoint riêng hoặc tác vụ async; không để client gọi unlimited |

**Không phải cứ trả ít JSON là DB đã làm ít việc.** Nếu repository vẫn tải toàn bộ entity và collection rồi Jackson chỉ loại field lúc serialize, bandwidth giảm nhưng query/heap/CPU có thể không giảm. Hãy kiểm chứng SQL và object mapping. Ngược lại, thêm nhiều lựa chọn fieldset có thể làm số loại truy vấn tăng, khó cache và khó tối ưu plan; khi chỉ có vài màn hình ổn định, **DTO riêng theo use case** thường đơn giản hơn.

### Kích thước response và nén

Theo dõi `response.size`/bytes, thời gian JSON serialization, CPU nén và network transfer. Với JSON có nhiều field lặp, HTTP compression như gzip/br có thể giảm số byte truyền, nhưng **không giảm số query** và tiêu tốn CPU. Đừng nén mọi payload rất nhỏ một cách máy móc; đo p95 theo thiết bị/network thật. Hợp đồng nên giới hạn cả request `size` lẫn số đối tượng lồng; trường hợp trả file lớn cân nhắc streaming/async download với authorization phù hợp.

## 9. Đo truy vấn bằng `EXPLAIN` thay vì chỉ đếm query

Sau khi sửa N+1 từ 61 query xuống 2 query, hãy kiểm tra hai query mới có quá nặng không:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, status, total_minor_units, currency
FROM orders
WHERE tenant_id = '00000000-0000-0000-0000-000000000001'
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

Trên PostgreSQL, `EXPLAIN` cho kế hoạch ước lượng; `EXPLAIN ANALYZE` **thực sự chạy câu SQL** và bổ sung số liệu thời gian thực. Dùng trên môi trường/fixture phù hợp, tránh chạy mutation có side effect trong production khi không kiểm soát. `BUFFERS` giúp thấy block cache/disk; so sánh với dữ liệu thật và thống kê mới, không chỉ đọc `cost` là milliseconds.

Những dấu hiệu cần xem:

- `Seq Scan` trên bảng lớn thay vì index scan phù hợp (không phải Seq Scan luôn sai; với bảng nhỏ có thể tốt).
- `Sort` lớn, spill ra disk, lượng row thực đọc lớn so với row trả về.
- Ước lượng row lệch xa actual; thống kê phân phối tenant/status có thể không phù hợp.
- Nhiều nested loop với tập lớn; lookup lặp đi lặp lại.
- Điều kiện tenant/filter được áp sớm hay quá muộn; thực sự scan bao nhiêu row.
- Truy vấn `COUNT(*)` trên nhiều join dù UI không cần tổng.

**Tổng thời gian chờ của API không bằng mỗi “execution time” trong DB.** Query JDBC còn gồm chờ connection pool, round-trip, row transfer và mapping. Với workload concurrent, phải đo cả contention, lock waits và p95/p99, không chỉ một lệnh chạy đơn độc trên laptop.

### Khi nào tăng index chưa phải giải pháp?

Nếu query đã dùng index nhưng vẫn trả 50.000 row để phục vụ 20 item, trước hết phải sửa pagination/selectivity. Nếu 100 query giống nhau được gọi trong vòng lặp, trước hết sửa N+1/batching. Nếu gateway mất 500 ms chờ connection, thêm index có thể không cải thiện. **Đo đúng tầng gây chậm**, rồi mới chọn thay đổi.

## 10. Bảo đảm tính đúng đắn và security khi tối ưu

Tối ưu dữ liệu dễ gây lỗi nghiệp vụ khi rút bỏ một bước kiểm tra hoặc ghép dữ liệu sai. Các bất biến phải được giữ:

1. **Tenant isolation:** mọi truy vấn list/detail/batch phải lọc tenant từ principal đã xác thực; đừng lấy tenant từ header tự khai hoặc quên filter trên query thứ hai.
2. **Object-level authorization:** người dùng chỉ được đọc những order họ có quyền; chỉ có `where tenant_id = ...` chưa đủ nếu cùng tenant còn quyền theo role/owner.
3. **Field-level authorization:** projection không được tự thêm `customerEmail`, giá vốn, token, địa chỉ chi tiết hay dữ liệu thanh toán nếu client không có quyền.
4. **Không suy ra dữ liệu nhạy cảm qua metadata:** `totalElements`, pagination count hoặc thời gian phản hồi cũng có thể tiết lộ số lượng resource ngoài quyền; count phải theo cùng phạm vi filter/authorization.
5. **Nhất quán bản đọc:** nếu dùng replica/search projection bất đồng bộ, phân trang có thể trả dữ liệu cũ. Response DTO không tự tạo read-your-writes; cần contract về consistency token, replica lag hoặc đọc từ primary cho luồng cần nhất quán.
6. **Không thay hành vi API ngoài ý muốn:** thêm projection có thể làm mất field cũ; sửa sort có thể khiến client nhận thứ tự khác. Cập nhật OpenAPI, contract tests và versioning phù hợp.
7. **Không đưa dữ liệu nhạy cảm vào quan sát:** log query templates/metrics nhưng tránh SQL parameters có email, token, PII; metric label dùng route template thay vì resource ID.

Tạo payload nhỏ hơn không phải lý do trả `200 OK` khi filter không hợp lệ hoặc trả `404` cho resource vẫn tồn tại nhưng query thiếu điều kiện. HTTP status, phân trang, cache và Problem Details phải tiếp tục nhất quán với hợp đồng.

### Cache để giảm truy vấn: chỉ khi có chiến lược invalidation

Cache ở service/CDN hoặc second-level Hibernate cache có thể giúp endpoint đọc nhiều, nhưng phải phân biệt:

- **Response cache:** gắn `Cache-Control`/ETag phù hợp; dữ liệu riêng cần `private`/`no-store` hoặc khóa cache đảm bảo không lẫn tenant/user. Cấu hình `Vary` đúng khi nội dung thay đổi theo request header.
- **Application cache:** key chứa tenant và các filter/page/sort/fieldset liên quan; có TTL/invalidation rõ khi order được cập nhật.
- **DB/ORM cache:** có thể che N+1 trên cache ấm, nhưng không sửa cách truy vấn; đo cả cold/warm cache và hit ratio.

Nếu nghiệp vụ cần trả dữ liệu hiện tại sau write, cache/replica phải có hợp đồng stale/read-after-write rõ. **Dữ liệu nhanh nhưng sai hoặc lộ quyền là thất bại**, không phải tối ưu.

## 11. Kiểm thử hồi quy N+1 và response contract

Một bộ kiểm thử tốt phải bắt được cả “query count tăng theo N” lẫn “response không còn đúng”:

| Ca test | Input / cách dựng | Kết quả cần chứng minh |
| --- | --- | --- |
| Trang 1 order | 1 order, 1 customer, 3 lines | DTO list đúng, không fetch lines |
| Trang 20 order | 20 order, 20 customer khác nhau, mỗi order nhiều lines | Query count gần hằng số; không tăng theo số order |
| Batch lines | 20 order, nhiều line và một order không có line | Dữ liệu lines đúng nhóm, không thiếu/nhân dòng |
| Order nhiều lines | Một order có hàng trăm lines | Detail được giới hạn; list không vô tình trả tất cả |
| Không có quyền | Order thuộc tenant/owner khác | 403/404 theo hợp đồng, không rò body hoặc count |
| Page ranh giới | page âm, size 0/101, page rỗng | 400/422 phù hợp, không tạo truy vấn không giới hạn |
| Trang sâu | Offset lớn so với cursor | Thời gian/rows examined theo kế hoạch; không có dữ liệu trùng ngoài contract |
| Update xen giữa page | Ghi/xóa order trong lúc phân trang | Hành vi phù hợp semantics đã công bố |
| Quan hệ lazy/OSIV tắt | Tắt OSIV, serialize DTO | Không `LazyInitializationException`, không SQL khi serialize |
| Count đắt | Tải cao trên bảng có nhiều row | `Slice` không phát `COUNT` nếu không cần |
| Cold cache | Xóa cache ORM đã cô lập trong test | N+1 không bị che bởi cache ấm |
| Response shape | So sánh OpenAPI và payload | Chỉ field cho phép, đúng kiểu, đúng phân trang |

### 11.1. Ví dụ integration test với Hibernate Statistics

Với Hibernate 6 và Spring Data JPA, có thể dùng thống kê số prepared statement. **Đây là test phác họa**, giả định đã tạo dữ liệu riêng, dependency test JPA, entity/repository như phần trước:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.UUID;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.PageRequest;

@DataJpaTest(properties =
    "spring.jpa.properties.hibernate.generate_statistics=true")
class OrderSummaryQueryTest {

    @Autowired OrderRepository repository;
    @Autowired EntityManager entityManager;
    @Autowired EntityManagerFactory entityManagerFactory;

    @Test
    void listOfTwentyOrdersUsesOnePageQuery() {
        UUID tenantId = seedTwentyOrdersWithDistinctCustomers();
        entityManager.flush();
        entityManager.clear(); // Không để persistence context che query phụ.

        Statistics statistics =
            entityManagerFactory.unwrap(SessionFactory.class).getStatistics();
        statistics.clear();

        var result = repository.findSummaries(
            tenantId, PageRequest.of(0, 20)
        );
        assertThat(result.getContent()).hasSize(20);
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1L);
    }

    private UUID seedTwentyOrdersWithDistinctCustomers() {
        // Tạo 20 order có customer khác nhau và nhiều line mỗi order;
        // triển khai helper theo entity mapping thực tế của project.
        throw new UnsupportedOperationException("Provide test fixtures");
    }
}
~~~

Để test chạy thực sự, phải hiện thực helper seed fixture và cấu hình entity/repository; ví dụ này cố ý không giả định schema đầy đủ ngoài phạm vi bài học. `Statistics` là bộ đếm **cấp SessionFactory**, có thể bị test khác cùng context làm nhiễu; chạy trong context cô lập/tuần tự hoặc dùng SQL query-count proxy gắn **theo request**. Test này đo prepared statements, không chứng minh query thực hiện tốt trên DB lớn; kết hợp với Testcontainers PostgreSQL và `EXPLAIN`/load test khi phù hợp.

Để bắt N+1 vững hơn, thêm test với `1, 10, 50` phần tử; nếu query count có dạng `Q(N) = 1 + N` thì báo regression. Tránh assertion cố định tổng số câu SQL của toàn ứng dụng khi authentication, auditing hoặc transaction setup cũng truy vấn DB; cô lập đoạn đo và dùng ngưỡng gắn với mục tiêu.

### 11.2. MockMvc và kiểm tra JSON chỉ có trường cần thiết

Một test HTTP cho list nên xác minh contract và bảo mật:

~~~java
@Test
void listReturnsBoundedSummaryNotInternalEntity() throws Exception {
    mockMvc.perform(get("/v1/orders")
            .param("page", "0")
            .param("size", "20")
            .with(jwt().jwt(jwt -> jwt.claim("tenant_id", "tenant-a"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data[0].id").exists())
        .andExpect(jsonPath("$.data[0].status").exists())
        .andExpect(jsonPath("$.data[0].customerEmail").doesNotExist())
        .andExpect(jsonPath("$.data[0].paymentToken").doesNotExist())
        .andExpect(jsonPath("$.data[0].lines").doesNotExist())
        .andExpect(jsonPath("$.hasNext").isBoolean());
}
~~~

Test trên giả định đã cấu hình Spring Security Test JWT principal, controller/service mock hoặc fixture trả ít nhất một order, và các import `MockMvcRequestBuilders.get`, `MockMvcResultMatchers.*`, `SecurityMockMvcRequestPostProcessors.jwt`. Đừng dùng một test này làm bằng chứng authorization: phải có test tenant A/B riêng và xác minh query batch cũng áp filter. Với dữ liệu thật cần bảo vệ, kiểm tra response không có field nhạy cảm ở mọi endpoint và đường lỗi.

### 11.3. Benchmark và kiểm thử tải

Đo trước và sau với cùng số order, số lines, tỷ lệ cache hit, DB size, concurrency, network và cấu hình JVM. Thu ít nhất:

~~~text
Trước:
  p95 GET /v1/orders:       1.35 s
  SQL statements/request:     61
  response size p95:        180 KB
  DB pool pending:           12

Sau (giá trị mục tiêu minh họa, không phải kết quả đo):
  p95 GET /v1/orders:       0.20 s
  SQL statements/request:      1
  response size p95:         12 KB
  DB pool pending:            0
~~~

**Các số “sau” phải được đo mới được công bố là kết quả thực tế.** Kiểm tra throughput, tỷ lệ lỗi, GC, CPU và DB utilization; một tối ưu giúp p50 nhưng làm p99 tăng dưới tải không nên triển khai vội. Khi query count không đổi nhưng latency tăng, xem kế hoạch SQL, pool, lock và serialization.

## 12. Các anti-pattern và cách thay đúng

| Anti-pattern | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| `findAll()` không giới hạn | Quá nhiều row/heap/bytes | Page hoặc cursor có size cap |
| Trả entity JPA trực tiếp | N+1 lúc serialize, lộ field, vòng lặp JSON | DTO theo use case, map trong service |
| `for (order) repository.find...()` | 1+N query và nhiều round-trip | Query batch `IN` hoặc projection |
| `EAGER` mọi quan hệ | Tải dữ liệu dù không cần, secondary select | Fetch plan theo endpoint |
| Fetch join collection + `Pageable` | Phân trang trong memory/row explosion | Hai query: page IDs + batch lines |
| Join nhiều collection to-many | Cartesian product, duplicate, quá nhiều rows | Batch theo collection, tách endpoint |
| `Page` luôn tính total | Count query đắt | `Slice`/cursor khi chỉ cần hasNext |
| `OFFSET` rất sâu | Scan/bỏ qua nhiều row | Keyset và index theo sort |
| `fields=*` hoặc `include=*` không giới hạn | Chi phí và rò dữ liệu | Whitelist field/includes, cap depth/size |
| Dựa vào cache ấm để “hết N+1” | Cache miss làm tải tăng đột biến | Sửa SQL/fetch plan, rồi cache có chiến lược |
| Chỉ nhìn số query | Bỏ qua truy vấn quá nặng/serialization | Đo DB rows/time, p95, bytes, CPU |
| Bỏ filter tenant trong query batch | Rò dữ liệu giữa người dùng | Propagate trusted tenant/authorization mọi tầng |

**Nguyên tắc chọn giải pháp:** (1) loại dữ liệu không cần từ hợp đồng; (2) query projection theo đúng use case; (3) batch các quan hệ cần thiết với page cap; (4) chọn index và pagination theo kế hoạch; (5) đo lại với request/thời gian thực và kiểm thử security/contract.

## 13. Bài tập thực hành

**Bài 1 — Đếm N+1.** Một list lấy 40 orders; sau đó mỗi order lazy load một customer khác nhau và 3 lần gọi repository để lấy dữ liệu phụ. Giả sử không có cache và mọi lời gọi đều phát đúng một câu SQL, hãy tính số SQL; nếu thời gian network round-trip trung bình 6 ms và các query chạy tuần tự, ước lượng riêng overhead round-trip. Thiết kế một DTO list chỉ gồm `id, createdAt, status, totalMinorUnits` và dự đoán query count sau tối ưu.

**Bài 2 — Trang có lines.** Endpoint cần trả 50 orders cùng dòng hàng, mỗi order có 5 lines. So sánh (a) lazy load lines trong vòng lặp, (b) `JOIN FETCH` collection + `Pageable`, (c) query lấy page IDs rồi batch `IN`. Lập bảng query count, số SQL rows, rủi ro pagination và memory. Nêu vì sao lựa chọn (c) thường dễ kiểm soát hơn.

**Bài 3 — Query plan.** Với bảng 10 triệu order phân theo tenant, endpoint thường query theo `tenant_id`, có thể lọc `status` và sort `created_at DESC, id DESC`. Đề xuất index ứng viên, thử `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu kiểm thử và so sánh offset ở trang 1 với trang 100.000. Đề xuất cursor payload hợp lệ và cách chống cursor dùng sang tenant khác.

**Bài 4 — Bảo mật dữ liệu.** Một dev tối ưu response list bằng `fields=id,status,customerEmail,internalCost`. Hãy thiết kế whitelist field có phân quyền, test HTTP cho client không được đọc `customerEmail/internalCost`, và test repository chứng minh mọi query đều lọc tenant. Giải thích tại sao `@JsonIgnore` không thay thế authorization.

**Bài 5 — Kiểm chứng hiệu quả.** Tạo fixture với 1/20/100 orders và nhiều customer, lines khác nhau; viết integration test đo Hibernate statements hoặc datasource-proxy theo request, assertion response contract khi OSIV tắt, đo response bytes, p95 dưới tải. Nêu một trường hợp query count giảm nhưng p95 vẫn không tốt, và cách dùng tracing/metrics/EXPLAIN để tìm nguyên nhân.

**Gợi ý tự kiểm tra:** Bài 1: `1 + 40 + 3×40 = 161 SQL`; overhead lý thuyết `161×6 = 966 ms`, chưa kể DB execution; projection list có thể chỉ còn 1 query nếu không cần count. Bài 2: lazy load dễ thành `1+50`, fetch join collection có nguy cơ row explosion và pagination sai, hai bước thường khoảng 2 query với `IN` đã giới hạn. Bài 3: index theo tenant, filter và sort; cursor cần tie-breaker và liên kết filter/tenant. Bài 4: chỉ server quyết định field/row được phép, `@JsonIgnore` chỉ ảnh hưởng serialization. Bài 5: tối ưu phải xác nhận bằng latency và chi phí thực, không dừng ở số prepared statements.
