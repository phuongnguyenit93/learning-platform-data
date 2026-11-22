# Giới hạn của phân trang offset khi dữ liệu tăng lớn

Offset pagination là cách phân trang quen thuộc: ứng dụng gửi số trang và kích thước trang, Spring Data JPA chuyển chúng thành giới hạn và độ lệch trong truy vấn. Cách này đơn giản, hỗ trợ nhảy trực tiếp tới một trang bất kỳ và phù hợp với danh sách có quy mô vừa phải. Khi dữ liệu tăng lớn hoặc người dùng đi tới những trang rất sâu, chi phí có thể tăng đáng kể vì database phải tìm và bỏ qua nhiều hàng trước khi trả về trang cần thiết.

Vấn đề không chỉ là số hàng trả về. Với trang có offset lớn, database có thể phải duyệt, đọc hoặc sắp xếp một lượng hàng lớn rồi mới bỏ qua phần đầu. Nếu dữ liệu liên tục được thêm/xóa giữa các request, các trang offset cũng có thể bị lệch, dẫn tới hàng bị lặp hoặc bị bỏ qua. Bài này giải thích cách offset hoạt động, khi nào nó trở thành nút thắt và cách chuyển sang keyset/cursor pagination trong Spring Data JPA.

## 1. Offset pagination hoạt động như thế nào?

Offset pagination xác định:

- **Page number**: số thứ tự trang, thường bắt đầu từ 0 trong Spring Data.
- **Page size**: số hàng tối đa trên một trang.
- **Offset**: số hàng cần bỏ qua trước khi lấy trang hiện tại.

Công thức:

`offset = pageNumber × pageSize`

Ví dụ với page size là 20:

| Page number | Offset | Hàng được yêu cầu |
|---:|---:|---|
| 0 | 0 | 1–20 |
| 1 | 20 | 21–40 |
| 2 | 40 | 41–60 |
| 100 | 2.000 | 2.001–2.020 |
| 10.000 | 200.000 | 200.001–200.020 |

Ở SQL, database thường thực hiện ý tưởng tương đương:

```sql
select id, name, created_at
from product
where active = true
order by created_at desc, id desc
limit 20 offset 200000;
```

Cú pháp giới hạn hàng khác nhau theo database. PostgreSQL/MySQL hỗ trợ LIMIT/OFFSET; SQL Server thường dùng OFFSET/FETCH; Oracle có cú pháp riêng hoặc cú pháp chuẩn theo phiên bản.

Offset 200.000 không có nghĩa database nhảy tức thì tới hàng 200.001. Tùy execution plan, index và điều kiện lọc, database có thể phải đọc/duyệt các entry trước đó rồi bỏ qua chúng. Nếu phải sort, chi phí còn có thể bao gồm sắp xếp một tập kết quả lớn trước khi áp dụng offset/limit.

## 2. Dùng Pageable trong Spring Data JPA

Spring Data JPA hỗ trợ offset pagination qua `Pageable` và `PageRequest`.

Repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Page<Product> findByActiveTrue(Pageable pageable);
}
```

Service:

```java
@Service
public class ProductQueryService {

    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<Product> findActiveProducts(int page, int size) {
        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")
            )
        );

        return repository.findByActiveTrue(pageable);
    }
}
```

`PageRequest.of(0, 20)` yêu cầu trang đầu tiên với tối đa 20 hàng. `PageRequest.of(100, 20)` yêu cầu offset 2.000. Page index bắt đầu từ 0, còn page size phải là số dương.

Sort nên có thứ tự xác định. Trong ví dụ, `createdAt` là tiêu chí chính và `id` là tie-breaker duy nhất. Nếu chỉ sắp xếp theo createdAt, các hàng có cùng timestamp có thể đổi vị trí giữa các lần chạy.

Không nhận page size tùy ý từ client. Hãy đặt giới hạn tối đa để tránh request yêu cầu hàng chục nghìn hoặc hàng triệu kết quả trong một lần.

## 3. Vì sao offset sâu ngày càng đắt?

Giả sử truy vấn cần trả 20 hàng. Trang đầu chỉ cần tìm và trả khoảng 20 hàng phù hợp. Trang thứ 10.000 có offset 199.980; database vẫn cần xác định và bỏ qua phần lớn kết quả trước khi trả 20 hàng tiếp theo.

Các nguồn chi phí thường gặp:

1. **Duyệt index hoặc hàng trước offset:** index có thể giúp tìm theo thứ tự, nhưng database vẫn cần đi qua các entry trước vị trí cần lấy.
2. **Filter:** nếu điều kiện WHERE có độ chọn lọc thấp hoặc thiếu index, database có thể phải kiểm tra nhiều hàng để tìm đủ số hàng cần bỏ qua và trả về.
3. **Sort:** nếu index không đáp ứng ORDER BY, database có thể phải sort tập kết quả lớn. Chi phí sort có thể vượt xa chi phí trả trang cuối.
4. **JOIN:** query có nhiều JOIN, đặc biệt JOIN collection, có thể làm tăng số hàng trung gian trước khi phân trang.
5. **Count query:** kiểu trả về Page thường cần tổng số kết quả để tính totalElements/totalPages. Count có thể đắt dù trang dữ liệu chỉ có vài hàng.
6. **Tài nguyên database:** CPU, buffer/cache, I/O, memory cho sort và thời gian giữ connection đều có thể tăng.

Offset pagination không nhất thiết chậm chỉ vì số trang lớn. Nếu dữ liệu nhỏ, index phù hợp, filter chọn lọc và execution plan tốt, truy vấn vẫn có thể đáp ứng. Cần đo trên quy mô dữ liệu thực tế.

## 4. Index có giải quyết hoàn toàn offset sâu không?

Index phù hợp có thể giảm chi phí filter và sort, nhưng không xóa được bản chất phải bỏ qua một số lượng lớn kết quả trước offset.

Ví dụ truy vấn:

```sql
select id, created_at, name
from product
where tenant_id = ?
  and active = true
order by created_at desc, id desc
limit 20 offset 200000;
```

Một index ứng viên có thể bắt đầu bằng các cột equality filter rồi tới sort key, ví dụ:

```sql
create index ix_product_tenant_active_created_id
on product(tenant_id, active, created_at desc, id desc);
```

Index thực tế phải được thiết kế theo database, cardinality, tần suất cập nhật, filter và workload. Một số database có thể scan index ngược nên không nhất thiết cần khai báo DESC cho mọi trường hợp. Hãy dùng EXPLAIN/EXPLAIN ANALYZE để kiểm tra:

- Có dùng index đúng không?
- Có full table scan hoặc sort lớn không?
- Số hàng ước lượng và số hàng thực tế có chênh lệch không?
- Có nhiều hàng bị đọc để trả một trang nhỏ không?
- JOIN order và filter có phù hợp không?

Index có thể làm offset sâu tốt hơn nhiều, nhưng khi offset lên tới hàng trăm nghìn hoặc hàng triệu, database vẫn phải xử lý phần kết quả trước đó theo execution plan.

## 5. Page, Slice và List: khác nhau ở đâu?

Spring Data JPA có thể trả nhiều kiểu kết quả khi dùng Pageable:

| Kiểu | Nội dung | Thông tin tổng số | Count query |
|---|---|---|---|
| `Page<T>` | Dữ liệu trang hiện tại | Có totalElements và totalPages | Thường cần count query khi phải xác định tổng |
| `Slice<T>` | Dữ liệu trang hiện tại | Chỉ biết có trang tiếp theo hay không | Thường không cần count query; có thể đọc thêm một hàng để xác định hasNext |
| `List<T>` | Dữ liệu giới hạn theo Pageable | Không có metadata Page/Slice | Không cần count query |

Ví dụ Slice:

```java
Slice<Product> findByActiveTrue(Pageable pageable);
```

Dùng Slice có thể loại bỏ chi phí đếm tổng số bản ghi. Tuy nhiên, Slice vẫn dùng offset nếu Pageable là PageRequest. Vì vậy, Slice giúp giảm count query nhưng không giải quyết chi phí bỏ qua hàng ở offset sâu.

Nếu giao diện chỉ cần nút “Xem thêm” và không cần tổng số trang, Slice thường phù hợp hơn Page. Nếu cần số trang/tổng số kết quả, Page cung cấp metadata hữu ích nhưng cần cân nhắc count query.

## 6. Vấn đề dữ liệu thay đổi giữa các request

Offset pagination có thể không ổn định khi dữ liệu thay đổi giữa lần tải trang.

Giả sử trang đầu hiển thị các hàng A–J. Trước khi tải trang tiếp theo với offset 10, một hàng mới được thêm vào đầu danh sách. Khi đó offset 10 có thể bắt đầu từ J thay vì K, làm J xuất hiện lần thứ hai.

Ngược lại, nếu một hàng trước offset bị xóa, offset 10 có thể bỏ qua một hàng vốn thuộc trang tiếp theo.

Một ORDER BY ổn định với khóa unique giúp giải quyết sự không xác định khi nhiều hàng có cùng giá trị sort, nhưng **không ngăn hiện tượng dịch chuyển offset do insert/delete**.

Có thể giảm drift bằng:

- Dùng snapshot isolation hoặc một transaction snapshot cho toàn bộ quá trình đọc nếu workload và thời gian transaction cho phép.
- Gắn điều kiện cố định như `created_at <= :snapshotTime` để giới hạn dữ liệu mới hơn thời điểm bắt đầu.
- Dùng cursor/keyset thay vì offset khi người dùng chỉ đi tiếp trong danh sách.
- Chấp nhận semantics eventual/near-real-time nếu giao diện không yêu cầu snapshot nhất quán.

Giữ một transaction mở qua nhiều HTTP request thường không phù hợp vì giữ connection và tài nguyên quá lâu. Hãy chọn consistency model theo yêu cầu nghiệp vụ thay vì mặc định mở transaction dài.

## 7. Keyset pagination là gì?

Keyset pagination (còn gọi là seek pagination) xác định trang tiếp theo dựa trên **giá trị của hàng cuối cùng đã đọc**, thay vì đếm số hàng cần bỏ qua.

Giả sử sắp xếp:

```sql
order by created_at desc, id desc
```

Sau khi trang trước kết thúc ở:

```text
created_at = 2026-11-09T10:00:00Z
id = 500
```

Trang tiếp theo lấy các hàng đứng sau vị trí đó trong thứ tự giảm dần:

```sql
select id, name, created_at
from product
where active = true
  and (
       created_at < :lastCreatedAt
       or (created_at = :lastCreatedAt and id < :lastId)
  )
order by created_at desc, id desc
limit 20;
```

Database tìm từ keyset cuối cùng và lấy 20 hàng tiếp theo. Nó không phải bỏ qua 200.000 hàng như offset 200.000. Nếu có index phù hợp trên filter và sort key, keyset có thể duy trì hiệu năng ổn định hơn khi người dùng đi sâu trong tập dữ liệu.

Predicate phải khớp chính xác thứ tự sort:

- Với ASC, dùng toán tử `>` cho vị trí sau.
- Với DESC, dùng toán tử `<`.
- Với nhiều cột, so sánh theo thứ tự từ trái sang phải; khi cột trước bằng nhau mới xét cột tiếp theo.
- Cần một tie-breaker unique, thường là primary key.

## 8. Keyset với nhiều thuộc tính và direction hỗn hợp

Ví dụ sort:

```sql
order by priority desc, created_at asc, id asc
```

Cursor gồm `lastPriority`, `lastCreatedAt`, `lastId`. Predicate cho hàng đứng sau cursor là:

```sql
where priority < :lastPriority
   or (
       priority = :lastPriority
       and created_at > :lastCreatedAt
   )
   or (
       priority = :lastPriority
       and created_at = :lastCreatedAt
       and id > :lastId
   )
```

Mỗi cấp so sánh dùng toán tử theo direction của thuộc tính đó. Đây là lỗi thường gặp: dùng cùng một dấu `<` hoặc `>` cho mọi property dù ORDER BY có direction hỗn hợp.

Với keyset nhiều thuộc tính:

1. Thứ tự sort phải xác định và có tie-breaker unique.
2. Cursor phải chứa mọi giá trị sort cần thiết.
3. Predicate phải phản ánh đúng thứ tự ASC/DESC.
4. Các điều kiện filter phải giữ nguyên giữa các request.
5. Cần xử lý NULL rõ ràng; keyset scrolling chuẩn của Spring Data yêu cầu các thuộc tính sort dùng làm keyset có giá trị không NULL.
6. Kiểm thử các trường hợp nhiều hàng trùng sort key và các biên đầu/cuối.

Một số database hỗ trợ row-value comparison như `(created_at, id) < (?, ?)`, nhưng cú pháp và khả năng tối ưu khác nhau. Predicate mở rộng bằng AND/OR như trên dễ diễn đạt hơn trong JPQL portable.

## 9. Keyset pagination bằng JPQL trong Spring Data JPA

Có thể tự xây dựng truy vấn seek cho một sort cố định.

Ví dụ repository:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Query("""
        select p
        from Product p
        where p.active = true
          and (
              p.createdAt < :lastCreatedAt
              or (
                  p.createdAt = :lastCreatedAt
                  and p.id < :lastId
              )
          )
        order by p.createdAt desc, p.id desc
        """)
    List<Product> findNextActiveProducts(
        @Param("lastCreatedAt") Instant lastCreatedAt,
        @Param("lastId") Long lastId,
        Pageable limit
    );
}
```

Đây là minh họa cho các trang tiếp theo khi đã có cursor. Truy vấn trang đầu cần một query riêng không có predicate cursor:

```java
@Query("""
    select p
    from Product p
    where p.active = true
    order by p.createdAt desc, p.id desc
    """)
List<Product> findFirstActiveProducts(Pageable limit);
```

Service chỉ truyền Pageable để giới hạn số hàng; nên dùng page number 0 và page size cố định cho query đầu, hoặc dùng custom repository với `setMaxResults(limit)` để biểu đạt rõ đây là giới hạn chứ không phải offset sâu.

Khi nhận trang cuối, lưu `createdAt` và `id` của hàng cuối làm cursor cho request tiếp theo. Không lấy cursor từ hàng đầu nếu đang đi về phía sau trong thứ tự đã định.

Ví dụ trên giả định `createdAt` không NULL và thứ tự DESC cho cả createdAt/id. Nếu createdAt nullable hoặc sort direction khác, predicate cần được điều chỉnh theo quy tắc NULL và direction. Hãy bảo đảm giá trị timestamp trong cursor giữ đúng precision của database.

## 10. Spring Data Scroll API và Window

Các phiên bản Spring Data hỗ trợ Scroll API cung cấp abstraction `Window<T>`, `ScrollPosition` và các phương thức repository trả về Window. API này cho phép đọc từng cửa sổ kết quả và lấy vị trí tiếp tục từ phần tử cuối.

Ví dụ derived query:

```java
public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Window<Product>
    findFirst100ByActiveTrueOrderByCreatedAtDescIdDesc(
        ScrollPosition position
    );
}
```

Lấy cửa sổ đầu theo keyset:

```java
Window<Product> window =
    repository.findFirst100ByActiveTrueOrderByCreatedAtDescIdDesc(
        ScrollPosition.keyset()
    );
```

Lấy vị trí tiếp tục từ phần tử cuối:

```java
if (window.hasNext() && !window.isEmpty()) {
    ScrollPosition nextPosition =
        window.positionAt(window.size() - 1);

    Window<Product> nextWindow =
        repository.findFirst100ByActiveTrueOrderByCreatedAtDescIdDesc(
            nextPosition
        );
}
```

`ScrollPosition.keyset()` khởi tạo keyset scrolling. `ScrollPosition.offset()` khởi tạo offset-based scrolling qua cùng abstraction. Mỗi lần tiếp tục, lấy position ở phần tử cuối của Window hiện tại.

Scroll API phụ thuộc phiên bản Spring Data Commons/Spring Data JPA. Khả năng hỗ trợ khác nhau theo kiểu query; tài liệu Spring Data JPA hiện hành nêu giới hạn với string-based query methods như `@Query`. Hãy kiểm tra tài liệu đúng phiên bản trước khi thiết kế repository dựa trên Scroll API. Derived query methods và các kiểu query được hỗ trợ là lựa chọn an toàn hơn cho ví dụ này.

### 10.1. Điều kiện cho keyset scrolling

Để keyset hoạt động đáng tin cậy:

- Sort phải xác định và unique; nếu property sort không unique, thêm ID làm tie-breaker.
- Các property sort phải có trong kết quả/projection để Spring Data tạo keyset.
- Các giá trị sort dùng làm keyset cần không NULL theo yêu cầu của keyset scrolling.
- Dùng property path hợp lệ và kiểu dữ liệu có thể so sánh.
- Giữ filter và sort nhất quán giữa các lần gọi.
- Tạo index hỗ trợ filter và thứ tự sort.

Nếu query chỉ trả DTO/projection, bảo đảm projection chứa các property cần để tạo keyset. Nếu property sort không được chọn, framework có thể không tạo được vị trí tiếp tục.

## 11. Offset scrolling vẫn có chỗ dùng

Offset không phải lúc nào cũng sai. Nó phù hợp khi:

- Người dùng cần nhảy trực tiếp tới trang 1, 5, 20 hoặc một số trang cụ thể.
- Tập dữ liệu không quá lớn.
- Offset thường nhỏ và có giới hạn.
- Số lượng kết quả cần đếm để hiển thị tổng trang.
- Dữ liệu ít thay đổi trong thời gian người dùng duyệt.
- Query có index tốt và đã đo hiệu năng đạt yêu cầu.

Keyset phù hợp hơn khi:

- Người dùng chỉ cần tải tiếp.
- Có feed, activity stream, lịch sử hoặc danh sách mới nhất.
- Batch job phải xử lý hàng triệu bản ghi theo từng chunk.
- Tập dữ liệu rất lớn và người dùng thường đi sâu.
- Muốn tránh chi phí bỏ qua các hàng trước cursor.

Điểm đánh đổi: keyset thường không hỗ trợ nhảy trực tiếp tới trang số 10.000 nếu không có một cơ chế định vị riêng. Nó dựa trên cursor của vị trí đã đọc, không dựa trên số trang tuyệt đối.

## 12. Cursor API cho ứng dụng web

Thay vì client gửi `page=10000`, API cursor có thể trả:

```json
{
  "items": [
    {"id": 500, "name": "Product A"}
  ],
  "nextCursor": "opaque-cursor-token",
  "hasNext": true
}
```

Client gửi cursor ở request tiếp theo:

```http
GET /api/products?limit=20&cursor=opaque-cursor-token
```

Cursor nên chứa đủ thông tin để tiếp tục đúng thứ tự:

- Giá trị sort key cuối cùng, ví dụ createdAt.
- Tie-breaker unique, ví dụ ID.
- Phiên bản sort/filter nếu API cần phát hiện cursor cũ.
- Snapshot cutoff nếu nghiệp vụ yêu cầu cố định tập dữ liệu.

Không nên tin nội dung cursor do client tùy ý sửa. Có thể serialize rồi ký (HMAC) hoặc mã hóa nếu cần bảo mật dữ liệu trong cursor. Base64 chỉ là encoding, không phải encryption hay chữ ký. Cursor cũng không nên chứa thông tin nhạy cảm nếu không cần thiết.

Giới hạn `limit` ở server và kiểm tra cursor hợp lệ trước khi tạo query. Không cho client gửi trực tiếp tên cột, fragment WHERE hoặc SQL.

## 13. Ảnh hưởng của concurrent insert/update/delete với keyset

Keyset giảm hiện tượng dịch chuyển vị trí do insert/delete ở trước offset, vì trang tiếp theo bắt đầu từ giá trị cursor chứ không phải vị trí đếm.

Tuy nhiên, keyset không tự tạo snapshot nhất quán:

- Một hàng mới được thêm trước cursor có thể không xuất hiện trong luồng đang duyệt theo chiều hiện tại.
- Một hàng được cập nhật sort key có thể di chuyển từ phía sau cursor lên phía trước hoặc ngược lại.
- Hàng bị xóa trước khi tới lượt sẽ không còn được trả.
- Thay đổi filter membership có thể khiến một hàng xuất hiện hoặc biến mất giữa các request.

Nếu cần export nhất quán tại một thời điểm, cần thiết kế snapshot/cutoff hoặc cơ chế lưu tập ID/version. Keyset giải quyết hiệu quả định vị trang, không thay thế transaction isolation hay snapshot semantics.

## 14. Batch processing và dữ liệu rất lớn

Với batch job xử lý hàng triệu hàng, không nên tải tất cả entity vào một List hoặc dùng offset tăng dần không giới hạn.

Một vòng xử lý theo cursor có thể:

1. Lấy chunk đầu theo sort key.
2. Xử lý từng hàng hoặc chuyển thành DTO.
3. Lưu cursor của hàng cuối.
4. Lấy chunk kế tiếp bằng predicate keyset.
5. Lặp cho tới khi không còn hàng.

Ví dụ minh họa:

```java
Instant lastCreatedAt = null;
Long lastId = null;

while (true) {
    List<Product> batch;

    if (lastCreatedAt == null) {
        batch = repository.findFirstActiveProducts(
            PageRequest.of(0, 500)
        );
    } else {
        batch = repository.findNextActiveProducts(
            lastCreatedAt,
            lastId,
            PageRequest.of(0, 500)
        );
    }

    if (batch.isEmpty()) {
        break;
    }

    process(batch);

    Product last = batch.get(batch.size() - 1);
    lastCreatedAt = last.getCreatedAt();
    lastId = last.getId();
}
```

Đây là skeleton minh họa; cần bảo đảm query đầu và query tiếp theo dùng cùng filter/sort, createdAt không NULL và việc xử lý batch có transaction/retry/idempotency phù hợp. Nếu xử lý có thể thất bại giữa chừng, lưu cursor sau khi batch đã được xử lý và commit thành công để tránh bỏ sót.

Với entity lớn, cân nhắc DTO projection để giảm memory và persistence context. Nếu dùng Stream từ repository, phải quản lý transaction và đóng stream đúng cách; Stream không tự động đồng nghĩa keyset pagination và có thể giữ connection/cursor mở trong suốt quá trình duyệt.

## 15. Native query, JOIN và count query

Offset pagination có thể được dùng với native SQL, nhưng phải chú ý:

- Database có thể có cú pháp LIMIT/OFFSET khác nhau.
- Native query trả Page thường cần countQuery riêng để đếm đúng.
- JOIN collection có thể tạo nhiều hàng SQL cho một entity cha; phân trang trực tiếp có thể làm số entity thực tế ít hơn page size hoặc tạo trùng.
- DISTINCT và GROUP BY làm count query phức tạp hơn.
- Dynamic Sort trên native query có giới hạn theo parser và phiên bản Spring Data.

Với keyset, native SQL có thể viết predicate rất rõ và tận dụng row-value comparison nếu database hỗ trợ. Đổi lại, query và cursor gắn chặt hơn với database. Hãy kiểm thử cả query dữ liệu và count query trên engine production.

## 16. Thiết kế index cho keyset

Giả sử query:

```sql
select id, created_at, name
from product
where tenant_id = ?
  and active = true
  and (
      created_at < ?
      or (created_at = ? and id < ?)
  )
order by created_at desc, id desc
limit 50;
```

Một index ứng viên:

```sql
create index ix_product_tenant_active_created_id
on product(tenant_id, active, created_at desc, id desc);
```

Nguyên tắc:

- Đưa các điều kiện equality có tính chọn lọc vào đầu index khi phù hợp.
- Tiếp theo là các cột sort/keyset.
- Có tie-breaker unique ở cuối.
- Kiểm tra kiểu index và chiều scan database hỗ trợ.
- Tránh index quá rộng nếu chi phí ghi và dung lượng lớn.
- Đo với phân bố dữ liệu thật; thứ tự index tối ưu không thể suy ra chỉ từ câu SQL.

Với keyset nhiều thuộc tính và filter động, có thể cần nhiều index cho các query shape khác nhau. Không cố tạo một index duy nhất phục vụ mọi tổ hợp filter/sort.

## 17. So sánh Offset, Slice và Keyset

| Tiêu chí | Page + Offset | Slice + Offset | Keyset/Cursor |
|---|---|---|---|
| Định vị trang | Số trang | Số trang | Giá trị cursor |
| Nhảy tới trang bất kỳ | Có | Có | Không trực tiếp |
| Count tổng | Có thể có | Không cần | Thường không có sẵn |
| Chi phí trang rất sâu | Có thể tăng mạnh | Vẫn tăng do offset | Thường ổn định hơn nếu index phù hợp |
| Dữ liệu thay đổi giữa request | Có thể drift | Có thể drift | Ít dịch chuyển do offset, nhưng không phải snapshot |
| Sort ổn định | Cần | Cần | Bắt buộc, gồm tie-breaker unique |
| API phù hợp | Bảng có số trang | “Xem thêm” đơn giản | Feed, scroll, batch lớn |
| Độ phức tạp triển khai | Thấp | Thấp | Cao hơn; cần cursor/predicate |
| Hỗ trợ random access | Tốt | Tốt | Hạn chế |

Slice giảm count query nhưng không đổi cách database bỏ qua offset. Keyset thay đổi cách định vị trang, vì vậy giải quyết được một phần cốt lõi của offset sâu.

## 18. Quy trình chuyển từ offset sang keyset

Không nên chuyển chỉ vì nghe nói keyset nhanh hơn. Hãy làm theo các bước:

1. Đo query hiện tại ở trang đầu, trang giữa và trang rất sâu.
2. Kiểm tra SQL, count query và execution plan.
3. Xác định thứ tự sort ổn định; thêm primary key làm tie-breaker.
4. Kiểm tra sort key có NULL không và xác định quy tắc xử lý.
5. Thiết kế cursor chứa đủ giá trị sort key.
6. Viết predicate keyset đúng với từng direction.
7. Tạo/điều chỉnh index theo filter và sort.
8. Kiểm thử trường hợp trùng sort key, insert/delete/update đồng thời và cursor hết hạn.
9. So sánh độ trễ, số hàng đọc, CPU, I/O và connection usage.
10. Chuyển API từ page number sang nextCursor nếu UX không cần nhảy trang.

Nếu sản phẩm cần cả random access lẫn tải tiếp, có thể giữ offset cho các trang đầu và dùng keyset cho luồng “load more”, nhưng phải thống nhất semantics và tránh để client đổi qua lại gây trùng/mất hàng.

## 19. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trang đầu nhanh nhưng trang sâu chậm | Offset lớn khiến database phải bỏ qua nhiều hàng | Chuyển sang keyset hoặc giới hạn độ sâu |
| Slice vẫn chậm ở trang sâu | Slice bỏ count nhưng vẫn dùng offset | Dùng keyset/cursor |
| Hàng bị lặp giữa hai trang | Insert/delete trước offset hoặc ORDER BY không unique | Thêm tie-breaker; dùng cursor nếu phù hợp |
| Hàng bị bỏ qua | Offset dịch chuyển khi dữ liệu bị xóa/thêm | Keyset hoặc snapshot/cutoff theo nghiệp vụ |
| Thứ tự không ổn định | Sort key có giá trị trùng và không có unique tie-breaker | Thêm ID/unique key cuối ORDER BY |
| Keyset bỏ sót hàng cùng timestamp | Predicate chỉ so sánh timestamp, thiếu điều kiện ID | Dùng predicate lexicographic gồm mọi sort key |
| Keyset trả hàng sai khi direction hỗn hợp | Dùng cùng dấu so sánh cho mọi thuộc tính | Xây predicate theo từng ASC/DESC |
| Keyset không hoạt động với NULL | Sort key nullable | Chuẩn hóa/định nghĩa NULL hoặc dùng chiến lược query khác |
| Count query chậm | Page cần tổng số kết quả | Dùng Slice nếu không cần tổng hoặc tối ưu count riêng |
| Query có JOIN trả thiếu entity | JOIN collection làm nhân bản hàng trước khi phân trang | Phân trang ID trước rồi tải association; kiểm tra DISTINCT |
| Batch job tốn memory | Tải quá nhiều entity cùng lúc | Chunk nhỏ, DTO và kiểm soát PersistenceContext |
| Cursor bị sửa từ client | Tin dữ liệu cursor không được xác thực | Ký/validate token và whitelist filter/sort |
| Keyset vẫn chậm | Index không hỗ trợ filter/sort hoặc predicate phức tạp | Kiểm tra execution plan và index |

## 20. Checklist lựa chọn pagination

- [ ] Người dùng có cần nhảy trực tiếp tới trang bất kỳ không?
- [ ] Dữ liệu dự kiến lớn đến mức nào và độ sâu trang thường gặp?
- [ ] Page count có thực sự cần cho UI không?
- [ ] Slice có đủ nếu chỉ cần biết còn dữ liệu tiếp theo?
- [ ] ORDER BY có tie-breaker unique?
- [ ] Dữ liệu có thể thay đổi giữa các request không?
- [ ] Có yêu cầu snapshot nhất quán cho export/batch không?
- [ ] Keyset sort properties có không NULL?
- [ ] Cursor chứa đủ sort key và được xác thực?
- [ ] Index có hỗ trợ filter + ORDER BY + keyset predicate?
- [ ] Query có JOIN collection làm nhân bản hàng?
- [ ] Đã đo trang đầu/trang sâu và kiểm tra EXPLAIN?
- [ ] Page, Slice, Window và Scroll API có được hỗ trợ bởi phiên bản Spring Data JPA hiện tại?

## 21. Kết luận

Offset pagination đơn giản và hữu ích khi cần số trang, nhảy trang trực tiếp và tập dữ liệu không quá lớn. Nhưng offset sâu có thể khiến database phải duyệt hoặc bỏ qua rất nhiều hàng trước khi trả trang nhỏ; Page còn có thể phát sinh count query tốn kém. Slice bỏ count query nhưng vẫn giữ chi phí offset.

Khi dữ liệu lớn và luồng sử dụng chủ yếu là đi tiếp, keyset/cursor pagination thường phù hợp hơn. Nó dựa trên giá trị sort key cuối cùng, dùng predicate để tìm phần tử tiếp theo và có thể tận dụng index. Để đúng, cần ORDER BY xác định với tie-breaker unique, cursor đầy đủ, predicate khớp từng direction và index phù hợp. Keyset cải thiện định vị trang nhưng không tự tạo snapshot nhất quán; nếu dữ liệu thay đổi mạnh hoặc export cần trạng thái tại một thời điểm, hãy thiết kế consistency riêng.

Hãy đo query thực tế trước khi chuyển đổi. Giữ offset cho nhu cầu random access có quy mô hợp lý; dùng keyset cho feed, tải tiếp và batch lớn khi nó phù hợp với UX và yêu cầu nhất quán.
