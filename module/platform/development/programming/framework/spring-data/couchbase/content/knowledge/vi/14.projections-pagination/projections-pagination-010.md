# Phân trang trong luồng phản ứng mà không giả định có Page tự động

Trong **Spring Data Couchbase**, một repository đồng bộ thường có thể trả `Page<T>` để ứng dụng nhận nội dung trang, tổng số phần tử và tổng số trang. Khi chuyển sang **reactive API**, không nên máy móc đổi kiểu trả về thành `Mono<Page<T>>` rồi cho rằng framework sẽ tự phân trang, tự chạy `COUNT` và tự điền đầy đủ metadata.

Reactive thay đổi cách thực thi và tiêu thụ thao tác bất đồng bộ, **không tự sinh ý nghĩa nghiệp vụ của một trang dữ liệu**. Một `Flux<Customer>` có thể được giới hạn bằng `Pageable`, nhưng bản thân `Flux` không nói được tổng số khách hàng đang khớp điều kiện, cũng không tự chứng minh có trang kế tiếp.

Bài thuộc chương **Chiếu và phân trang** của module **SPRING_DATA_COUCHBASE**. Chúng ta sẽ kết nối Spring Data repository, `ReactiveCouchbaseTemplate`, Couchbase Java SDK reactive, SQL++, index, CAS, TTL và consistency để tạo những API phân trang **đúng hợp đồng**, tránh đánh đồng backpressure với `LIMIT` hoặc nhầm `Pageable` với một `Page` đã được tạo sẵn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Pageable` (yêu cầu), `Page<T>`/`Slice<T>` (kết quả), `Flux<T>` và `Mono<T>` (publisher).
2. Viết phương thức reactive repository dùng `Pageable` mà không giả định nhận được `Page` tự động.
3. Tạo trang kiểu “Tải thêm” với `LIMIT pageSize + 1`, xác định `hasNext` và trả về một DTO cửa sổ.
4. Chạy truy vấn đếm `COUNT` **riêng** khi sản phẩm cần `totalElements`/`totalPages`.
5. Dùng `ReactiveCluster.query(...)` và ánh xạ SQL++ result rows không chặn event-loop.
6. Phân biệt phân trang bằng `OFFSET` với keyset/cursor trong một reactive pipeline.
7. Xử lý validation, backpressure, cancellation, lỗi query, consistency và index.
8. Viết integration test xác minh dữ liệu, số query, thứ tự và hành vi khi có mutation đồng thời.

> **Thông điệp chính:** `Pageable` chỉ diễn đạt yêu cầu lấy một phạm vi; `Flux` chỉ phát các phần tử. Nếu API cần metadata như `hasNext` hoặc tổng số bản ghi, phải xác định nó được tính từ **truy vấn nào** và được **đóng gói ở đâu**.

## 2. Ví dụ xuyên suốt: danh sách khách hàng

Giả sử document nằm trong bucket `shop`, scope `crm`, collection `customers`:

~~~json
{
  "fullName": "Trần Minh",
  "email": "minh@example.test",
  "tenantId": "tenant-01",
  "active": true,
  "createdAt": "2026-11-20T08:15:00.000Z"
}
~~~

Document key `customer::42` nằm trong Couchbase metadata, không nhất thiết là field của body JSON.

Sản phẩm có ba màn hình:

| Màn hình | Cần nội dung? | Cần biết còn trang tiếp? | Cần biết tổng? |
| --- | --- | --- | --- |
| Autocomplete 10 khách hàng | Có | Không | Không |
| Feed khách hàng, nút “Tải thêm” | Có | Có | Không |
| Bảng quản trị “Trang 1/250” | Có | Có | Có |

Không nên ép cả ba vào một kiểu `Page` và chạy count cho mọi lượt đọc. Trong hệ thống có nhiều yêu cầu đồng thời, mỗi truy vấn tổng không cần thiết đều tạo thêm công việc cho Query/Index Service.

## 3. Bốn khái niệm dễ bị nhầm

### `Pageable`: tham số của một yêu cầu

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable request = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
~~~

`PageRequest.of(0, 20, sort)` yêu cầu trang số 0, kích thước 20, có thứ tự. Số trang trong Spring Data bắt đầu từ **0**. `getOffset()` bằng `pageNumber × pageSize` và có kiểu `long`.

### `Flux<T>`: publisher nhiều phần tử

~~~java
Flux<Customer> customers = repository.findByActiveTrue(request);
~~~

`Flux<Customer>` phát các customer khi có subscriber. Nó không tự có `getTotalElements()`, `getTotalPages()` hoặc `hasNext()`.

### `Mono<T>`: publisher có tối đa một giá trị

~~~java
Mono<Long> total = countActiveCustomers();
~~~

Một `Mono<Long>` có thể chứa kết quả count. Nhưng đặt dữ liệu vào `Mono<Page<Customer>>` chỉ **có nghĩa một publisher phát một Page**; không chứng minh framework đã tự chạy count hay tạo Page.

### `Page<T>`/`Slice<T>`: cấu trúc kết quả nghiệp vụ

- `Page<T>` có content và tổng số phần tử/trang.
- `Slice<T>` có content và `hasNext`, không yêu cầu tổng toàn tập.
- Đối tượng tương đương có thể tự xây từ data query/COUNT/`pageSize+1` nếu API mong muốn.

| Khái niệm | Diễn tả | Không tự bảo đảm |
| --- | --- | --- |
| `Pageable` | Trang số, kích thước, sort | Không phải một kết quả |
| `Flux<T>` | Luồng phần tử bất đồng bộ | Không có total/hasNext mặc định |
| `Mono<T>` | Publisher một kết quả | Không có ngữ nghĩa Page mặc định |
| `Page<T>` | Nội dung + total metadata | Không tự đảm bảo snapshot nhiều query |
| `Slice<T>` | Nội dung + hasNext | Không cung cấp total |
| Keyset cursor | Vị trí theo giá trị khóa sort | Không phải snapshot |

## 4. Reactive repository: truyền `Pageable` nhưng không giả định Page tự động

Một entity được mapping cho Couchbase:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    private String fullName;
    private String email;
    private String tenantId;
    private boolean active;
    private String createdAt;

    // Constructor/getter/setter theo quy tắc mapping của dự án.
}
~~~

Repository reactive có thể khai báo phương thức query derivation nhận `Pageable` và phát `Flux`:

~~~java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.domain.Pageable;
import reactor.core.publisher.Flux;

public interface ReactiveCustomerRepository
        extends ReactiveCouchbaseRepository<Customer, String> {

    Flux<Customer> findByActiveTrue(Pageable pageable);
}
~~~

Sử dụng:

~~~java
Pageable request = PageRequest.of(
        0, 20, Sort.by("createdAt").descending());

Flux<Customer> rows = repository.findByActiveTrue(request);
~~~

Ở đây `Pageable` có thể được Spring Data Couchbase dùng để tạo sort/limit/offset theo đường repository được hỗ trợ. Tuy nhiên:

1. Kiểu trả về của method là `Flux<Customer>`, **không phải `Page<Customer>`**.
2. Không có `totalElements`, `totalPages` hay `hasNext` tự xuất hiện trên publisher này.
3. Không nên giả định `Mono<Page<Customer>>` hoặc `Mono<Slice<Customer>>` là query return type được module/phiên bản hiện tại hỗ trợ như `Page` đồng bộ.
4. Nếu cần metadata, phải **xây dựng rõ logic** hoặc sử dụng một API chính thức mà phiên bản đã được xác nhận hỗ trợ.
5. Bật log SQL++ hoặc kiểm tra plan để xác nhận thực tế `Pageable` sinh điều kiện nào, nhất là cách Spring Data mapping `@Id` vào sort theo document key.

**Lưu ý quan trọng:** API repository reactive, tên interface, phương thức query và khả năng return type thay đổi theo thế hệ Spring Data. Không sao chép hợp đồng `Page` từ synchronous repository sang reactive rồi coi đó là bảo đảm chung.

## 5. Vì sao `collectList()` không tự tạo Page?

Giả sử:

~~~java
Mono<List<Customer>> result = repository
        .findByActiveTrue(request)
        .collectList();
~~~

`collectList()` thu toàn bộ những phần tử **mà publisher trên thực tế phát ra** vào một `List`. Nó **không**:

- Chạy `COUNT(*)` để tính tổng dataset.
- Biết các document nào nằm sau trang đã được giới hạn.
- Tự suy ra `hasNext` từ một trang có đúng 20 phần tử.
- Chuyển một `Flux` không giới hạn thành truy vấn SQL++ an toàn về tài nguyên.
- Cố định snapshot giữa các request.

Nếu query chỉ lấy tối đa 20 row và nhận đúng 20 row, chưa thể biết có row thứ 21 hay không. Để biết `hasNext`, cần một cơ chế **look-ahead** hoặc truy vấn riêng.

**Cẩn trọng về bộ nhớ:** `collectList()` trên một `Flux` không giới hạn có thể gom rất nhiều document vào RAM. Chỉ nên thu danh sách sau khi **có giới hạn ở tầng truy vấn**, không phải chỉ giới hạn kích thước collection ở Java.

## 6. Thiết kế API reactive không cần total

Với “Tải thêm”, thay vì `Mono<Page<Customer>>`, có thể thiết kế một read model:

~~~java
import java.util.List;

public record CustomerSummary(
        String id,
        String fullName,
        String email,
        String createdAt) {}

public record CustomerWindow(
        List<CustomerSummary> items,
        int page,
        int size,
        boolean hasNext) {}
~~~

Service trả:

~~~java
Mono<CustomerWindow> findWindow(
        int page, int size, String tenantId);
~~~

Một publisher `Mono<CustomerWindow>` thể hiện **một response gồm nhiều item và metadata**. Metadata được tính ở service; không phụ thuộc một giả định “reactive repository sẽ tự tạo Page”.

Với trang số, SQL++ có thể là:

~~~sql
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email,
       c.createdAt AS createdAt
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT $limit OFFSET $offset;
~~~

Khi `size=20`, truy vấn lấy `limit=21` và `offset=page × 20`. Nếu có 21 row, chỉ đưa 20 row đầu vào response và đặt `hasNext=true`.

### Cạm bẫy: `PageRequest.of(page, size + 1)` không phải cách look-ahead đúng

Giả sử muốn `page=3`, `size=20`, offset phải là `60`.

- `PageRequest.of(3, 20)` có offset `60`.
- `PageRequest.of(3, 21)` có offset **63**, không còn là ranh giới đúng.

Vì vậy **không** được chỉ tăng page size trong `PageRequest.of(page, size+1)` rồi nghĩ rằng đã lấy thêm một hàng ở cùng offset. Có thể dùng custom SQL++ với `LIMIT = size+1` và `OFFSET = page×size`, hoặc một API query hỗ trợ limit/offset độc lập, hoặc chiến lược khác đã kiểm chứng.

Đây là một trong những lỗi off-by-one dễ bị che khuất khi đổi từ `Page` sang tự dựng `Slice` trong reactive flow.

## 7. Ví dụ reactive Java SDK: truy vấn trang có look-ahead

Couchbase Java SDK cung cấp đối tượng reactive, chẳng hạn qua `cluster.reactive()`. Với SDK 3.x, một query reactive phát `ReactiveQueryResult` rồi có thể giải mã result rows bằng `rowsAsObject()`.

Ví dụ dưới đây minh họa **một method service**, không phải toàn bộ class. Dự án phải có `Cluster`/`ReactiveCluster` được cấu hình, quản lý lifecycle và kết nối tới Couchbase.

~~~java
import com.couchbase.client.java.ReactiveCluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryScanConsistency;
import reactor.core.publisher.Mono;

import java.util.List;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public Mono<CustomerWindow> loadCustomerWindow(
        ReactiveCluster cluster,
        String tenantId,
        int page,
        int size) {

    if (tenantId == null || tenantId.isBlank()) {
        return Mono.error(
                new IllegalArgumentException("tenantId is required"));
    }
    if (page < 0 || size < 1 || size > 100) {
        return Mono.error(
                new IllegalArgumentException("Invalid pagination"));
    }

    long offset = (long) page * size;

    if (offset > 10_000) {
        return Mono.error(new IllegalArgumentException(
                "Page too deep; use cursor pagination"));
    }

    String sql = """
        SELECT META(c).id AS id,
               c.fullName AS fullName,
               c.email AS email,
               c.createdAt AS createdAt
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.tenantId = $tenantId
          AND c.active = TRUE
        ORDER BY c.createdAt DESC, META(c).id DESC
        LIMIT $limit OFFSET $offset
        """;

    JsonObject parameters = JsonObject.create()
            .put("tenantId", tenantId)
            .put("limit", size + 1)
            .put("offset", offset);

    return cluster.query(
            sql,
            queryOptions().parameters(parameters))
        .flatMapMany(result -> result.rowsAsObject())
        .map(row -> new CustomerSummary(
                row.getString("id"),
                row.getString("fullName"),
                row.getString("email"),
                row.getString("createdAt")))
        .collectList()
        .map(fetched -> {
            boolean hasNext = fetched.size() > size;
            List<CustomerSummary> visible = hasNext
                    ? fetched.subList(0, size)
                    : fetched;

            return new CustomerWindow(
                    List.copyOf(visible),
                    page,
                    size,
                    hasNext);
        });
}
~~~

**Điểm phải nhận ra:**

- `ReactiveCluster.query` khởi tạo một truy vấn SQL++ reactive thay vì dùng `Cluster.query` blocking trên event-loop.
- `flatMapMany(result -> result.rowsAsObject())` biến một reactive query result thành luồng JSON row.
- `map(...)` ánh xạ row sang DTO; `META(c).id AS id` cung cấp document key.
- `collectList()` chỉ gom **tối đa `size+1` hàng** vì server query có `LIMIT` tương ứng.
- `hasNext` được tính từ hàng dư, không cần `COUNT`.
- `OFFSET` vẫn có thể đắt ở trang sâu, vì vậy method đặt giới hạn offset **ví dụ**.
- `Mono.error(...)` cung cấp lỗi trong pipeline thay vì block hoặc throw từ thao tác IO bất đồng bộ.
- Có thể thêm `queryOptions().scanConsistency(...)` khi hợp đồng nghiệp vụ cần đọc dữ liệu index mới hơn; phải cân nhắc độ trễ.

Các class/package, chữ ký method và tùy chọn `QueryOptions` cần được đối chiếu với bản **Couchbase Java SDK** của dự án. Ví dụ tập trung vào cách xây metadata, không bao gồm logging, tracing, timeout hay tất cả exception handling cần thiết trong production.

### Vì sao không gọi `block()`?

Không viết:

~~~java
// Không sử dụng trong luồng xử lý WebFlux/event-loop.
List<CustomerSummary> rows = loadReactiveRows()
        .collectList()
        .block();
~~~

`block()` chờ bất đồng bộ theo kiểu đồng bộ, có thể chiếm thread, vi phạm kỳ vọng xử lý non-blocking và gây vấn đề hiệu năng hoặc lỗi khi chạy trong event-loop không cho phép block.

Với WebFlux, trả trực tiếp `Mono<CustomerWindow>` cho controller hoặc tiếp tục kết hợp publisher bằng operator Reactor.

## 8. Cung cấp tổng chính xác: một query `COUNT` độc lập

Nếu UI cần “Trang 3/500”, `hasNext` chưa đủ. Phải xác định tổng số phần tử theo filter:

~~~sql
SELECT COUNT(1) AS total
FROM `shop`.`crm`.`customers` AS c
WHERE c.active = TRUE
  AND c.tenantId = $tenantId;
~~~

Phải giữ **cùng predicate nghiệp vụ** trong query dữ liệu và query count. Không bỏ `tenantId`, discriminator, trạng thái hoặc điều kiện quyền, vì sẽ khiến total sai và có thể tiết lộ số lượng dữ liệu của tenant khác.

Ví dụ service method lấy total qua reactive SDK:

~~~java
import com.couchbase.client.java.ReactiveCluster;
import com.couchbase.client.java.json.JsonObject;
import reactor.core.publisher.Mono;

import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public Mono<Long> countActiveCustomers(
        ReactiveCluster cluster,
        String tenantId) {

    String sql = """
        SELECT COUNT(1) AS total
        FROM `shop`.`crm`.`customers` AS c
        WHERE c.active = TRUE
          AND c.tenantId = $tenantId
        """;

    return cluster.query(
            sql,
            queryOptions().parameters(
                    JsonObject.create().put("tenantId", tenantId)))
        .flatMapMany(result -> result.rowsAsObject())
        .single()
        .map(row -> row.getLong("total"));
}
~~~

Trong SQL++, `COUNT(1)` đếm các hàng khớp filter. `COUNT(c.email)` sẽ có ngữ nghĩa khác nếu field `email` thiếu hoặc `NULL`; đừng thay thế tùy tiện.

### Thiết kế response có total

~~~java
public record CustomerPageResponse(
        List<CustomerSummary> items,
        int page,
        int size,
        long totalElements,
        long totalPages) {}
~~~

Có thể ghép hai publisher:

~~~java
Mono<CustomerWindow> rowsMono =
        loadCustomerWindow(cluster, tenantId, page, size);

Mono<Long> totalMono =
        countActiveCustomers(cluster, tenantId);

Mono<CustomerPageResponse> result = Mono.zip(rowsMono, totalMono)
        .map(tuple -> {
            CustomerWindow rows = tuple.getT1();
            long total = tuple.getT2();
            long totalPages = total / size
                    + (total % size == 0 ? 0 : 1);

            return new CustomerPageResponse(
                    rows.items(),
                    page,
                    size,
                    total,
                    totalPages);
        });
~~~

Ví dụ này nhằm làm rõ **trách nhiệm**: service phải cung cấp `totalMono`; reactive không tự đếm. `totalPages` được tính theo phép chia nguyên làm tròn lên, tránh cast total lớn về `int`.

**Cảnh báo nhất quán:** `Mono.zip` có thể khiến data query và count query chạy đồng thời, nhưng chúng vẫn là **hai truy vấn riêng**. Insert/delete/TTL hoặc index consistency có thể khiến `items` và `totalElements` phản ánh trạng thái khác nhau. Nếu nghiệp vụ cần snapshot mạnh, cách ghép hai publisher **không giải quyết** yêu cầu đó.

**Cảnh báo tài nguyên:** chạy count trên mọi request có thể tăng tải Query/Index Service. Nếu UI chỉ hiển thị “Tải thêm”, ưu tiên cửa sổ có `hasNext` thay vì total.

## 9. Khi nào nên dùng `PageImpl` hoặc `SliceImpl`?

Nếu một tầng ứng dụng khác đã yêu cầu kiểu Spring Data, bạn có thể **tự dựng** `PageImpl<T>` sau khi đã có content và total:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable pageable = PageRequest.of(page, size);

Page<CustomerSummary> pageResult =
        new PageImpl<>(content, pageable, totalElements);
~~~

Đây là việc **tạo đối tượng kết quả**. Nó không tự gọi Couchbase, không tự chạy count, không tạo snapshot và không thay thế việc validate total.

Nếu chỉ cần metadata `hasNext` theo offset, bạn có thể tự dựng `SliceImpl`:

~~~java
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.SliceImpl;

Slice<CustomerSummary> sliceResult =
        new SliceImpl<>(visibleItems, pageable, hasNext);
~~~

Nhưng `SliceImpl.nextPageable()` vẫn diễn tả bước đi dựa trên `Pageable` số trang. Với API **keyset/cursor**, không nên dùng `nextPageable()` làm thay thế cho cursor chứa bộ khóa sort; đó là hai mô hình điều hướng khác nhau.

Một reactive service hoàn toàn có thể trả `Mono<Page<CustomerSummary>>` **do chính service dựng**. Điều không nên giả định là Spring Data Couchbase tự động hỗ trợ mọi kiểu reactive repository return type hoặc tự cấp content/COUNT phù hợp cho bất kỳ truy vấn nào.

## 10. Keyset/cursor trong reactive flow

Offset có thể tăng sâu:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21 OFFSET 200000;
~~~

Ngay cả khi query reactive, server có thể vẫn phải xử lý nhiều hàng trước khi bỏ qua phần đầu. Reactive **không làm `OFFSET 200000` trở thành thao tác hằng số**.

Nếu UI chỉ cần đọc tiếp, dùng **keyset pagination**:

~~~sql
-- Trang đầu: không có cursor.
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT $limit;
~~~

Sau khi hiển thị 20 hàng, tạo cursor từ **hàng thứ 20**:

~~~json
{
  "createdAt": "2026-11-20T08:15:00.000Z",
  "id": "customer::42"
}
~~~

Query trang sau:

~~~sql
SELECT META(c).id AS id,
       c.createdAt AS createdAt,
       c.fullName AS fullName,
       c.email AS email
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = $tenantId
  AND c.active = TRUE
  AND c.createdAt IS NOT MISSING
  AND c.createdAt IS NOT NULL
  AND (
      c.createdAt < $afterCreatedAt
      OR (
          c.createdAt = $afterCreatedAt
          AND META(c).id < $afterId
      )
  )
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT $limit;
~~~

Với `ORDER BY createdAt DESC, id DESC`, dấu `<` nghĩa là “đứng sau cursor”. Khi sort khác hướng, cần sửa đúng dấu cho từng khóa. Nếu chỉ lưu `createdAt` mà bỏ ID, nhiều document cùng timestamp có thể bị bỏ sót.

### DTO kết quả cursor

~~~java
public record CustomerCursor(
        String createdAt,
        String id) {}

public record CustomerCursorWindow(
        List<CustomerSummary> items,
        boolean hasNext,
        CustomerCursor nextCursor) {}
~~~

Một pipeline sau khi đã query và map tối đa `size+1` row:

~~~java
return queryAndMapRowsReactive(sql, parameters)
        .collectList()
        .map(fetched -> {
            boolean hasNext = fetched.size() > size;
            List<CustomerSummary> visible = hasNext
                    ? fetched.subList(0, size)
                    : fetched;

            CustomerCursor cursor = hasNext
                    ? new CustomerCursor(
                            visible.get(visible.size() - 1).createdAt(),
                            visible.get(visible.size() - 1).id())
                    : null;

            return new CustomerCursorWindow(
                    List.copyOf(visible),
                    hasNext,
                    cursor);
        });
~~~

`queryAndMapRowsReactive(sql, parameters)` là **hàm ứng dụng minh họa**, không phải API sẵn của Spring Data Couchbase. Nó phải trả `Flux<CustomerSummary>` từ query SQL++ đã có `LIMIT size+1`. Nếu `hasNext=true`, `visible` có đúng `size` hàng nên lấy phần tử cuối là an toàn.

**Không được lấy cursor từ hàng thứ `size+1`** chỉ dùng để look-ahead; nếu làm vậy, hàng dư đó sẽ bị bỏ qua vĩnh viễn ở lần truy vấn sau.

## 11. Reactor backpressure không tương đương SQL++ pagination

Một số cách viết trông hợp lý nhưng chưa đủ:

~~~java
Flux<Customer> rows = repository.findAll()
        .take(20);
~~~

~~~java
Flux<Customer> rows = repository.findAll()
        .skip(200000)
        .take(20);
~~~

~~~java
Flux<Customer> rows = repository.findAll()
        .limitRate(20);
~~~

Ba operator có ý nghĩa khác nhau:

- `take(20)`: downstream chỉ tiêu thụ tối đa 20 phần tử. Nó **không chứng minh** Couchbase SQL++ được tối ưu thành `LIMIT 20` ngay từ đầu; upstream có thể đã lập kế hoạch hoặc thực hiện công việc lớn.
- `skip(200000)`: bỏ phần tử trong reactive stream. Nếu upstream không được phân trang ở server, hệ thống vẫn phải tạo/phát nhiều phần tử để bỏ qua.
- `limitRate(20)`: điều tiết nhu cầu/request ở Reactor, **không phải** SQL++ `LIMIT 20` và không xác định có tổng cộng chỉ 20 hàng.

Trong production, hãy **đẩy filter, sort và limit xuống query SQL++** hoặc API repository/template phù hợp. Sau đó dùng Reactor để map, ghép metadata và xử lý lỗi.

Backpressure giúp quản lý lượng phần tử luân chuyển qua publisher/subscriber trong nhiều trường hợp, nhưng không thay thế việc thiết kế index, query plan hoặc giới hạn kích thước kết quả tại server.

### `collectList()` và khả năng giữ bộ nhớ

~~~java
// Hợp lý khi SQL++ đã LIMIT 21.
Mono<List<CustomerSummary>> bounded =
        queryAtMostTwentyOneRows()
                .collectList();
~~~

~~~java
// Nguy hiểm nếu query trả cả triệu rows mà không có giới hạn.
Mono<List<CustomerSummary>> unbounded =
        queryEveryCustomer()
                .collectList();
~~~

Không dựa vào giả định “reactive nên tự ít tốn RAM”. `collectList()` vẫn giữ một danh sách phần tử trong bộ nhớ trước khi phát một kết quả.

## 12. Thứ tự dữ liệu: `ORDER BY` và operator Reactor

Phân trang chính xác đòi hỏi thứ tự **toàn phần**:

~~~sql
ORDER BY c.createdAt DESC, META(c).id DESC
~~~

`createdAt` có thể trùng; `META(c).id` làm khóa phân xử duy nhất trong collection đơn nguồn. Nếu query dùng `JOIN`/`UNNEST` tạo nhiều row từ cùng document, document ID không còn đủ làm khóa phân xử duy nhất cho row kết quả; cần thiết kế lại tổ hợp khóa.

Sau khi SQL++ trả các row có thứ tự, toán tử Reactor cũng cần giữ thứ tự nếu các bước map bất đồng bộ:

~~~java
// map đồng bộ giữ thứ tự phát phần tử.
Flux<CustomerSummary> summaries =
        jsonRows.map(this::toSummary);
~~~

~~~java
// Nếu mỗi row cần một thao tác async và thứ tự quan trọng:
Flux<CustomerSummary> ordered =
        jsonRows.concatMap(this::enrichAsync);
~~~

`concatMap` tuần tự hóa việc ánh xạ bất đồng bộ để giữ thứ tự. `flatMap` có thể đan xen kết quả các tác vụ async, khiến thứ tự phát đầu ra khác thứ tự SQL++, nếu các tác vụ hoàn thành không theo thứ tự. Có thể xem xét `flatMapSequential` khi cần concurrency nhưng phải giữ thứ tự kết quả và kiểm soát bộ đệm.

Ngoài ra, nếu frontend gửi đồng thời yêu cầu trang 1, 2, 3, phản hồi HTTP có thể về không đúng thứ tự. UI phải gắn kết quả với đúng cursor/page request; **không nối các response theo thứ tự đến mạng**.

## 13. `NULL`, `MISSING`, schema và cursor

Couchbase là document database nên trường `createdAt` có thể:

- Có chuỗi timestamp hợp lệ.
- Có mặt nhưng giá trị `null`.
- Không tồn tại trong body (`MISSING`).
- Có kiểu khác như number hoặc chuỗi không chuẩn.

Ví dụ keyset ở trên **loại** các document có `NULL`/`MISSING` để điều kiện so sánh range hoạt động trên tập có khóa phù hợp. Điều này chỉ đúng khi hợp đồng nghiệp vụ cho phép loại chúng.

Nếu mọi customer phải xuất hiện trong feed, cần thiết kế khóa sort chuẩn hóa hoặc biểu thức phù hợp, cùng quy tắc so sánh trong:

1. `SELECT` giá trị dùng để tạo cursor.
2. `ORDER BY` xác định thứ tự.
3. `WHERE` keyset của trang tiếp theo.
4. Index phục vụ query.
5. Validation/migration dữ liệu cũ.

Với chuỗi ngày giờ, định dạng ISO-8601 UTC phải thống nhất precision và timezone để so sánh chuỗi tương ứng thứ tự thời gian. Đối với tên tiếng Việt, thứ tự ký tự SQL++ không mặc nhiên đúng collation ngôn ngữ tự nhiên mà UI mong đợi.

## 14. Index và chi phí của query reactive

Lệnh SQL++ reactive vẫn chạy trên Couchbase Query Service, dùng secondary index và thực hiện các operator như trong đường blocking.

Một index ứng viên:

~~~sql
CREATE INDEX ix_customer_tenant_active_created
ON `shop`.`crm`.`customers` (
    tenantId,
    active,
    createdAt DESC
);
~~~

Kiểm tra query bằng `EXPLAIN`:

~~~sql
EXPLAIN
SELECT META(c).id AS id,
       c.fullName AS fullName,
       c.email AS email,
       c.createdAt AS createdAt
FROM `shop`.`crm`.`customers` AS c
WHERE c.tenantId = "tenant-01"
  AND c.active = TRUE
ORDER BY c.createdAt DESC, META(c).id DESC
LIMIT 21;
~~~

Khi đọc kế hoạch:

- Index có được dùng cho predicate `tenantId`/`active`/`createdAt` không?
- Có `Fetch` body vì field `fullName` và `email` không được index cover không?
- Có bước `Order` tại Query Service không?
- `LIMIT` có được áp dụng sớm/push down phù hợp không?
- Thứ tự theo `META(c).id` có thật sự được index hỗ trợ không?
- `COUNT` (nếu API cần total) có kế hoạch riêng đắt như thế nào?
- Khi offset sâu, số index entries scanned và latency tăng bao nhiêu?
- Query có `OR` cho keyset có tạo được range scan hiệu quả không?

Index ứng viên trên **không phải lời hứa covering index hay index-order pushdown**. Optimizer còn xét những biểu thức khác, thống kê, điều kiện lọc và phiên bản Couchbase Server. Đo bằng query profiling thực tế, không chỉ nhìn kích thước `Flux`.

### Đừng nhầm “trả 21 hàng” với “quét 21 entries”

`LIMIT 21` chỉ giới hạn kết quả sau các bước query phù hợp. Truy vấn có thể cần xử lý nhiều entries hơn nếu sort, filter hoặc index không tối ưu. Reactive không thay đổi điều đó.

## 15. Query scan consistency và dữ liệu động

Sau mutation, các secondary index có thể phản ánh thay đổi với độ trễ tùy chính sách scan consistency. Trong SDK có các lựa chọn như `NOT_BOUNDED` và `REQUEST_PLUS` ở những đường query được hỗ trợ.

~~~java
import com.couchbase.client.java.query.QueryScanConsistency;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

// Ví dụ chọn consistency khi nghiệp vụ cần query
// có thể nhìn thấy các mutation đã hoàn tất gần đây.
var options = queryOptions()
        .scanConsistency(QueryScanConsistency.REQUEST_PLUS);
~~~

`REQUEST_PLUS` có thể chờ index bắt kịp tới thời điểm request theo semantics của Query Service, nhưng có thể tăng độ trễ.

Không nên kết luận:

- “Query reactive luôn thấy dữ liệu mới nhất.”
- “Có `REQUEST_PLUS` nên hai trang đọc cách nhau một phút là cùng snapshot.”
- “`Page` hoặc count và data query là nguyên tử nếu dùng `Mono.zip`.”

Mỗi truy vấn là một lần đọc có chính sách riêng. Với dữ liệu thêm/xóa/TTL/update giữa request, page metadata và content vẫn có thể đổi.

### CAS không giải quyết snapshot phân trang

CAS là token phiên bản cho **một document**. Spring Data `@Version`/Couchbase SDK mutation dùng CAS để phát hiện cập nhật cạnh tranh. Nó không phải token thứ tự toàn collection và không thể thay cursor (`createdAt`, `id`).

Nếu danh sách có nút “Sửa”, nên tách **đường đọc danh sách** (projection/page/cursor) và **đường chỉnh sửa** (đọc đầy đủ/giữ CAS/conditional mutation). Không gọi `save` với một DTO projection thiếu field chỉ vì nó đã được trả từ feed.

## 16. TTL, transaction và cách hiểu snapshot

Một document có TTL có thể hết hạn giữa trang đầu và trang sau; ID/row biến mất khỏi tập query. Một document đổi trạng thái `active` cũng có thể vào/ra tập kết quả. Keyset giảm rủi ro dịch trang do vị trí offset nhưng **không tái tạo document đã xóa** hay đóng băng body đã sửa.

Giao diện thường có thể chọn semantics **live feed**. Nhưng nếu nghiệp vụ cần export đúng một tập document tại T0:

- Phải xác định rõ tập mục tiêu và giá trị dữ liệu tại mốc T0.
- Có thể cần vật hóa ID hoặc cả nội dung/version của tập.
- Nếu chỉ lưu ID, document sau đó bị sửa/xóa thì không tự lấy lại giá trị cũ.
- Cần checkpoint, retry/idempotency và chiến lược tạo snapshot nhất quán.
- Transaction nhiều document chỉ phù hợp trong những phạm vi và giới hạn thực tế, không phải mặc định để giữ một transaction sống qua nhiều HTTP request.

Không đưa ra lời hứa “reactive + keyset = duyệt chính xác mỗi document đúng một lần khi có writer đồng thời”. Đây là một yêu cầu nghiệp vụ phức tạp hơn lựa chọn publisher.

## 17. Xử lý lỗi trong pipeline phân trang

Một reactive endpoint cần phân biệt:

1. **Validation:** `page` âm, `size` bằng 0 hoặc quá lớn, sort ngoài allowlist, cursor sai/hết hạn.
2. **Query/cấu hình:** SQL++ sai, index chưa tồn tại, mapping field không hợp lệ.
3. **Timeout/mạng:** Query Service không phản hồi trong giới hạn, SDK timeout hoặc kết nối bị ngắt.
4. **Dữ liệu:** field thiếu/null/sai kiểu JSON, DTO mapping thất bại.
5. **Quyền truy cập:** tenant hoặc collection ngoài phạm vi người dùng, không để cursor vượt quyền.
6. **Concurrent changes:** dữ liệu biến đổi giữa các query; không coi mọi thay đổi của `total` là exception.

Ví dụ ánh xạ lỗi validation ở service:

~~~java
public Mono<CustomerWindow> listCustomers(
        String tenantId, int page, int size) {

    if (page < 0 || size < 1 || size > 100) {
        return Mono.error(
            new IllegalArgumentException("Invalid page/size"));
    }

    return loadCustomerWindow(cluster, tenantId, page, size)
            .doOnError(error -> logQueryFailure(error));
}
~~~

`logQueryFailure(...)` là **hàm ứng dụng minh họa**, không phải method SDK. Khi triển khai, nên cấu hình structured logs, metrics và correlation IDs. Không log toàn bộ token cursor, dữ liệu PII hoặc câu query kèm tham số nhạy cảm nếu không cần thiết.

Không viết `onErrorResume(error -> Mono.just(emptyPage))` cho mọi lỗi chỉ để “UI không bị crash”: một query thất bại không tương đương với một trang rỗng hợp lệ. Hãy map lỗi sang response phù hợp và giữ tín hiệu monitoring.

### Retry có chọn lọc

Không tự động retry vô hạn mọi query; retry có thể làm tăng tải khi cụm Couchbase đang suy giảm. Với một query đọc, retry có thể hợp lý trong một số lỗi tạm thời, nhưng cần giới hạn số lần, timeout và backoff, đồng thời hiểu rằng **kết quả sau retry có thể thấy dataset mới hơn**.

Nếu query phục vụ một job xử lý có side effect, idempotency phải được thiết kế ở luồng ghi, không dựa vào retry của Flux.

## 18. Hủy subscription và áp lực tài nguyên

Trong WebFlux, client có thể đóng kết nối trong lúc query đang chạy. Cancellation từ subscriber có thể lan ngược qua reactive pipeline, nhưng không nên khẳng định mọi hoạt động đã bắt đầu ở server đều lập tức dừng hoặc hoàn trả toàn bộ tài nguyên.

Ứng dụng nên:

- Cấu hình timeout ở tầng HTTP/service/SDK theo yêu cầu thực tế.
- Hạn chế page size và số truy vấn song song.
- Tránh chủ động `subscribe()` bên trong service rồi trả một publisher khác: như vậy lifecycle/cancellation/error không còn nằm trong pipeline do controller trả.
- Dùng `Mono.zip`/`flatMap`/`concatMap` đúng ngữ nghĩa và tránh tạo các truy vấn nền không cần thiết.
- Theo dõi số query đang chạy, timeout, cancellation và request chậm.

Ví dụ không nên:

~~~java
// Sai hướng thiết kế: subscription bị tách khỏi response HTTP.
loadCustomerWindow(cluster, tenant, page, size)
        .subscribe(window -> sendSomewhere(window));
return Mono.just("request accepted");
~~~

Trừ khi nghiệp vụ **chủ ý** tạo job độc lập có cơ chế lifecycle riêng, service trả trực tiếp publisher để framework quản lý backpressure và lỗi.

## 19. Chọn giữa offset, keyset và snapshot

| Nhu cầu | Hợp đồng reactive phù hợp | Cần lưu ý |
| --- | --- | --- |
| Autocomplete tối đa 10 kết quả | `Flux<Summary>` đã có query limit hoặc `Mono<List<Summary>>` | Không cần total |
| “Tải thêm” 20 hàng | `Mono<Window>` từ `LIMIT 21` | `hasNext` tính từ row dư |
| Bảng có tổng số trang | `Mono<CustomPage>` và `Mono<Long> COUNT` | Count đắt, hai query không cùng snapshot mặc định |
| Duyệt trang số nhỏ | `Pageable`/SQL++ `OFFSET` | Kiểm tra sort, độ sâu, mapping |
| Feed rất dài | `Mono<CursorWindow>` từ keyset | Cursor theo giá trị sort, có index phù hợp |
| Export hàng triệu hàng | Batch/cursor job, checkpoint | Quản lý bộ nhớ, retry, idempotency, snapshot |
| Sửa một document từ danh sách | Read model + KV/repository mutation có CAS | Không dùng cursor như version |
| Tổng hợp trên nhiều document | Aggregation query riêng | Không cần đếm mọi trang để lấy tổng |

Không có một “kiểu reactive Page” có thể thay thế mọi lựa chọn này. Chọn theo **hợp đồng UI**, rồi triển khai câu query và metadata tương ứng.

## 20. Checklist kiểm thử tích hợp

### Kiểu trả về và metadata

1. Repository method nhận `Pageable` trả `Flux<Customer>` hoạt động trên bản Spring Data Couchbase đang dùng.
2. Không giả định `Mono<Page<T>>` được repository tự sinh; nếu có `Mono<CustomPage>`, xác minh service tự dựng đầy đủ.
3. Query SQL++ thực sự có `LIMIT`, `OFFSET`, `ORDER BY` phù hợp; không chỉ kiểm tra Java code.
4. Với `size=3`: dữ liệu 0, 1, 3, 4, 7 hàng cho các trường hợp `hasNext` đúng.
5. Với `page=2, size=3`: `OFFSET` phải là **6**, kể cả khi query lấy `LIMIT 4` để look-ahead.
6. Không dùng `PageRequest.of(2, 4)` như thay thế cho `page=2, size=3`.

### Count và consistency

7. API không cần total không phát sinh `COUNT`.
8. API cần total có count query đúng tenant/filter/discriminator.
9. Count trả `long` phù hợp dữ liệu lớn; tránh tính `totalPages` bằng cách ép về `int` quá sớm.
10. Insert/delete/TTL giữa data query và count không khiến ứng dụng ngầm hứa snapshot.
11. Query ngay sau ghi với scan consistency thực tế; so sánh `NOT_BOUNDED` và `REQUEST_PLUS` nếu hệ thống hỗ trợ.

### Dữ liệu động, thứ tự và cursor

12. Nhiều hàng trùng `createdAt` vẫn được phân xử bằng document key.
13. Trang keyset đầu/tiếp theo dùng cùng filter, sort và dấu so sánh.
14. Cursor từ hàng cuối hiển thị, không từ hàng look-ahead.
15. Với document đổi sort key, xác nhận giới hạn của cursor và quy tắc UI.
16. Kiểm thử `NULL`/`MISSING`/timestamp sai kiểu theo chính sách dữ liệu.
17. Cursor sai tenant, sai sort, quá hạn hoặc bị chỉnh sửa phải bị từ chối.

### Reactive pipeline và hiệu năng

18. Không có `block()` trong đường request WebFlux.
19. Không gọi `collectList()` trên truy vấn không giới hạn.
20. Không dùng `Flux.skip(...)` để mô phỏng offset trang sâu ở client.
21. Các phép map async không làm mất thứ tự hàng SQL++.
22. Cancellation/timeout/query exception được chuyển đúng vào pipeline và monitoring.
23. `EXPLAIN`/query profile được xem cho offset sâu, keyset, count và projection.
24. Benchmark p50/p95 latency, index entries scanned, số `Fetch`, response bytes và số query/request.

### Bảng kỳ vọng với `size = 3`

| Tổng row hiện có, dữ liệu đứng yên | Query `LIMIT 4` nhận | API trả | `hasNext` |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | false |
| 1 | 1 | 1 | false |
| 3 | 3 | 3 | false |
| 4 | 4 | 3 | true |
| 7 (trang đầu) | 4 | 3 | true |
| 7 (trang thứ ba, offset 6) | 1 | 1 | false |

Không suy ra `totalElements = 7` từ riêng cửa sổ thứ ba nếu không có một nguồn total đáng tin cậy; data query giới hạn thông thường không tự cung cấp tổng.

## 21. Bài tập thực hành

Xây ba endpoint reactive trên collection `customers`.

**A. Danh sách giới hạn**

~~~http
GET /customers/suggestions?limit=10
~~~

Yêu cầu: query có `LIMIT` tại Couchbase; chỉ trả DTO các field hiển thị. Không gọi `COUNT`. Không query toàn collection rồi dùng `Flux.take(10)` làm lớp giới hạn duy nhất.

**B. Feed có `hasNext`**

~~~http
GET /customers/feed?page=2&size=20
~~~

Yêu cầu:

- Validate `page >= 0` và `1 <= size <= 100`.
- Sắp theo `createdAt DESC, META(c).id DESC`.
- SQL++ `OFFSET = page × size` và `LIMIT = size + 1`.
- Trả `Mono<CustomerWindow>`.
- Không chạy `COUNT`.
- Dùng dữ liệu ít hơn, đúng bằng hoặc nhiều hơn `size` để test `hasNext`.

**C. Bảng có total**

~~~http
GET /customers/table?page=0&size=20
~~~

Yêu cầu:

- Trả nội dung trang, `totalElements` và `totalPages`.
- Dùng một reactive data query và một reactive count query **có cùng predicate**.
- Thử `Mono.zip` và quan sát tổng số query.
- Chèn/xóa document giữa hai truy vấn để mô tả giới hạn snapshot.
- Dùng `EXPLAIN` đánh giá chi phí count riêng.

**D. Mở rộng keyset**

~~~http
GET /customers/stream?limit=20&cursor=...
~~~

Chuyển feed từ offset sang SQL++ keyset trên (`createdAt DESC`, `META(c).id DESC`), trả cursor opaque, không trả `nextPageable` như thể cursor là trang số. Thử token sai/đổi filter, dữ liệu trùng timestamp và cập nhật sort key.

### Câu hỏi tự kiểm tra

1. Một `Flux<Customer>` có tự mang `totalElements` hay `totalPages` không?
2. Vì sao `Mono<Page<Customer>>` do service dựng khác với `Page` do repository tự tạo?
3. `Pageable` dùng trong reactive repository có thể tạo giới hạn query nhưng không có metadata nào mặc định?
4. Vì sao `collectList()` không chạy `COUNT`?
5. Muốn `hasNext` với `size = 20`, tại sao query thường lấy 21 row?
6. Vì sao `PageRequest.of(3, 21)` sai nếu UI thực sự muốn `page=3, size=20`?
7. `Flux.take(20)` có bảo đảm SQL++ chỉ scan 20 index entries không?
8. `limitRate(20)` có đồng nghĩa với SQL++ `LIMIT 20` không?
9. Vì sao `Mono.zip(data, count)` không tạo một snapshot?
10. Với `ORDER BY createdAt DESC, id DESC`, điều kiện keyset sau cursor dùng dấu gì?
11. Vì sao không nên dùng `flatMap` async tùy ý nếu cần giữ thứ tự row?
12. Khi nào nên dùng cursor thay vì offset, và khi nào cần một snapshot/export riêng?

## 22. Tài liệu chính thức và lưu ý theo phiên bản

- [Spring Data Commons — Reactive Repositories](https://docs.spring.io/spring-data/commons/reference/repositories/reactive-repositories.html): kiểu publisher và hợp đồng repository reactive.
- [Spring Data — Defining Query Methods](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-methods-details.html): `Pageable`, `Sort`, `Page`/`Slice` và chi phí count.
- [Spring Data — Repository Query Return Types](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-return-types-reference.html): kiểu kết quả được hỗ trợ và các giới hạn.
- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): repository query, Couchbase mapping, `@Query`, `Pageable`.
- [Couchbase Java SDK — Reactive APIs](https://docs.couchbase.com/java-sdk/current/howtos/concurrent-async-apis.html): reactive API, threading và Reactor.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): named parameters, query results và consistency.
- [Couchbase Server — ORDER BY](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/orderby.html), [LIMIT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/limit.html), [OFFSET](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/offset.html): cú pháp và ngữ nghĩa cắt trang.
- [Couchbase Server — EXPLAIN](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/explain.html): phân tích query plan.

**Lưu ý:** tài liệu trình bày mô hình thiết kế và ví dụ cho các API phổ biến, nhưng **kiểu trả về reactive repository, converter/template, chữ ký SDK và tối ưu SQL++ cần kiểm chứng với phiên bản Spring Data Couchbase, Java SDK và Couchbase Server được khóa trong dự án**. Đặc biệt không suy luận rằng hỗ trợ `Pageable` ở một phương thức reactive đồng nghĩa tự hỗ trợ mọi biến thể `Mono<Page<T>>`.

> **Ghi nhớ:** Trong reactive data access, **pagination là hợp đồng query và kết quả**, không phải phép biến đổi tự động của `Flux`. Đặt `LIMIT/OFFSET` hoặc seek predicate ở Couchbase; dùng look-ahead để tạo `hasNext`; chạy `COUNT` riêng chỉ khi cần total; bảo toàn thứ tự trong Reactor và kiểm thử trên dữ liệu thực. `Pageable` là yêu cầu đầu vào, còn `Page`/`Slice` hoặc cursor window là kết quả mà ứng dụng phải tạo một cách có chủ đích.
