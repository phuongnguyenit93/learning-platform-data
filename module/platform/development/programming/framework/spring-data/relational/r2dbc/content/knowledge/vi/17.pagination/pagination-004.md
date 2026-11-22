# Phân trang theo khóa tiếp nối và điều kiện áp dụng

Phân trang theo khóa tiếp nối (keyset pagination), còn được gọi là seek pagination, lấy trang tiếp theo dựa trên giá trị của bản ghi cuối cùng ở trang hiện tại. Thay vì yêu cầu database bỏ qua một số lượng hàng lớn bằng `OFFSET`, truy vấn dùng điều kiện so sánh với khóa sắp xếp cuối cùng rồi tiếp tục đọc từ vị trí đó.

Với Spring Data Relational R2DBC, có thể triển khai cách phân trang này bằng `Criteria` và `Query` qua `R2dbcEntityTemplate`, hoặc viết SQL tường minh bằng `DatabaseClient`. Cả hai cách đều trả dữ liệu theo `Flux`/`Mono`, phù hợp với xử lý reactive. Điều quan trọng là phải có thứ tự sắp xếp ổn định, một cursor chứa đủ các giá trị sắp xếp và một điều kiện tiếp nối tương ứng chính xác với thứ tự đó.

## 1. Vì sao cần keyset pagination?

Phân trang offset thường dùng `LIMIT` và `OFFSET`:

```sql
SELECT id, created_at, status
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
```

Database cần tìm và bỏ qua các hàng đứng trước vị trí được yêu cầu rồi mới trả về 20 hàng tiếp theo. Khi offset lớn, công việc bỏ qua có thể tăng theo độ sâu của trang. Các hàng mới được thêm hoặc bị xóa ở phía trước cũng có thể làm vị trí offset dịch chuyển giữa hai lần gọi, dẫn đến lặp hoặc bỏ sót kết quả khi người dùng duyệt các trang.

Keyset pagination dùng giá trị của hàng cuối trang trước làm mốc:

```sql
SELECT id, created_at, status
FROM orders
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Ví dụ trên dùng phép so sánh tuple theo cú pháp PostgreSQL. Với database khác, có thể phải viết điều kiện tương đương bằng `OR` và `AND`. Database có thể dùng index để tìm vị trí tiếp nối thay vì đếm và bỏ qua một lượng hàng lớn.

Keyset đặc biệt hữu ích khi:

- Bảng có nhiều bản ghi và người dùng thường đi sâu qua nhiều trang.
- API dùng nút “Xem thêm”, infinite scroll hoặc luồng tải tiếp theo.
- Dữ liệu được thêm liên tục và cần duyệt theo một thứ tự ổn định.
- Truy vấn có index phù hợp với các cột lọc và sắp xếp.
- Không cần nhảy trực tiếp tới một số trang bất kỳ.

Keyset không phải lựa chọn tốt nhất cho mọi màn hình. Nếu dữ liệu nhỏ, số trang ít hoặc người dùng cần nhảy tới trang số 30, offset pagination có thể đơn giản và phù hợp hơn.

## 2. Phân biệt offset pagination và keyset pagination

| Tiêu chí | Offset pagination | Keyset pagination |
| --- | --- | --- |
| Cách xác định trang | Số hàng cần bỏ qua (`OFFSET`) | Giá trị khóa sắp xếp của hàng cuối trang trước |
| Đi tới trang bất kỳ | Thuận tiện với số trang | Không tự nhiên; cần duyệt cursor tuần tự hoặc có mốc riêng |
| Trang sâu | Có thể tốn chi phí do phải bỏ qua nhiều hàng | Thường ổn định hơn nếu có index phù hợp |
| Dữ liệu thay đổi giữa các lần gọi | Offset có thể dịch chuyển khiến kết quả lặp hoặc bị bỏ qua | Ít bị ảnh hưởng bởi insert ở phía trước cursor, nhưng không phải snapshot nhất quán tuyệt đối |
| Cursor phía client | Không cần; thường gửi page/size | Cần cursor đại diện cho vị trí cuối cùng |
| Tổng số trang | Có thể kết hợp `COUNT` để tính | Không có tổng số trang tự nhiên; thường chỉ trả `hasNext` và cursor tiếp theo |
| Trường hợp phù hợp | Bảng nhỏ, trang số, báo cáo cần nhảy trang | Danh sách lớn, infinite scroll, feed và API tải tiếp |

Keyset thay đổi cách định vị dữ liệu, không thay đổi yêu cầu về authorization, validation, giới hạn kích thước trang hoặc kiểm soát tải database.

## 3. Điều kiện tiên quyết: thứ tự sắp xếp phải ổn định

Cursor chỉ có ý nghĩa khi truy vấn có thứ tự xác định. Không nên phân trang trên một truy vấn không có `ORDER BY`, vì database không bảo đảm thứ tự hàng trả về giữa các lần thực thi.

Giả sử đơn hàng được sắp xếp mới nhất trước:

```sql
ORDER BY created_at DESC
```

Nhiều đơn hàng có thể có cùng `created_at`. Nếu chỉ dùng timestamp làm cursor, những hàng có cùng thời điểm có thể bị lặp hoặc bỏ sót ở ranh giới trang. Hãy thêm một khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, id DESC
```

Trong ví dụ này:

- `created_at` xác định thứ tự nghiệp vụ chính.
- `id` phân định thứ tự giữa các hàng có cùng `created_at`.
- Tổ hợp `(created_at, id)` xác định một vị trí duy nhất trong thứ tự kết quả.

Nếu sắp xếp theo một cột duy nhất đã là khóa chính hoặc unique key, có thể không cần thêm tie-breaker. Với mọi thứ tự không duy nhất, hãy bổ sung một khóa duy nhất ở cuối.

Các cột dùng làm cursor nên ổn định trong suốt quá trình duyệt. Nếu `created_at` hoặc trường sắp xếp bị thay đổi sau khi một hàng đã xuất hiện, hàng có thể di chuyển qua vị trí cursor và bị lặp hoặc bỏ sót. Ưu tiên trường bất biến hoặc ít thay đổi, chẳng hạn thời điểm tạo và ID.

## 4. Quy tắc tạo điều kiện tiếp nối

Với thứ tự giảm dần:

```sql
ORDER BY created_at DESC, id DESC
```

Giả sử hàng cuối trang hiện tại có:

```text
created_at = 2026-05-20T10:30:00
id         = 850
```

Trang kế tiếp phải chứa những hàng đứng sau hàng này trong thứ tự giảm dần. Điều kiện là:

```sql
WHERE created_at < :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id < :lastId)
```

Hai nhánh có ý nghĩa:

1. Lấy các hàng có `created_at` cũ hơn mốc.
2. Nếu `created_at` bằng mốc, lấy các hàng có `id` nhỏ hơn ID cuối trang.

Tổ hợp này tương đương so sánh từ điển (lexicographic comparison) trên cặp `(created_at, id)` theo thứ tự giảm dần. Không được chỉ dùng `created_at < :lastCreatedAt`, vì những hàng có cùng timestamp nhưng ID nhỏ hơn sẽ bị bỏ sót.

Với thứ tự tăng dần:

```sql
ORDER BY created_at ASC, id ASC
```

Điều kiện tiếp nối đổi chiều:

```sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND id > :lastId)
```

Quy tắc tổng quát: với thứ tự tăng dần, lấy giá trị lớn hơn cursor; với thứ tự giảm dần, lấy giá trị nhỏ hơn cursor. Nếu có nhiều cột sắp xếp, phải tạo điều kiện theo từng mức ưu tiên và giữ các cột trước bằng giá trị cursor khi xét cột kế tiếp.

## 5. Thứ tự hỗn hợp giữa ASC và DESC

Không phải truy vấn nào cũng sắp xếp tất cả cột cùng chiều. Ví dụ:

```sql
ORDER BY priority ASC, created_at DESC, id DESC
```

Điều kiện tiếp nối sau cursor `(priority, created_at, id)` là:

```sql
WHERE priority > :lastPriority
   OR (
       priority = :lastPriority
       AND created_at < :lastCreatedAt
   )
   OR (
       priority = :lastPriority
       AND created_at = :lastCreatedAt
       AND id < :lastId
   )
```

Mỗi nhánh xét cột tiếp theo sau khi tất cả cột có độ ưu tiên cao hơn đã bằng cursor. Phép so sánh tại cột hiện tại phụ thuộc hướng sắp xếp của chính cột đó.

Với nhiều cột, có thể xây dựng điều kiện theo mẫu:

```text
key1 after cursor
OR (key1 equal cursor AND key2 after cursor)
OR (key1 equal cursor AND key2 equal cursor AND key3 after cursor)
...
```

Trong đó “after cursor” là `>` nếu cột sắp xếp ASC và `<` nếu cột sắp xếp DESC. Đây là cách tránh nhầm dấu so sánh khi thứ tự có nhiều chiều khác nhau.

## 6. Ví dụ với `R2dbcEntityTemplate` và `Criteria`

Giả sử entity:

```java
@Table("orders")
public class Order {

    @Id
    private Long id;

    @Column("tenant_id")
    private Long tenantId;

    @Column("created_at")
    private LocalDateTime createdAt;

    private String status;

    // Constructor, getters và setters.
}
```

Cursor chứa tất cả các giá trị cần để tiếp tục thứ tự:

```java
public record OrderCursor(
        LocalDateTime createdAt,
        Long id
) {
}
```

Với trang đầu, không có điều kiện cursor. Với các trang tiếp theo, thêm nhóm điều kiện tiếp nối:

```java
public Flux<Order> findNextOrders(
        Long tenantId,
        OrderCursor cursor,
        int pageSize) {

    Criteria criteria = where("tenantId").is(tenantId);

    if (cursor != null) {
        Criteria afterCursor = where("createdAt").lessThan(cursor.createdAt())
                .or(where("createdAt").is(cursor.createdAt())
                        .and("id").lessThan(cursor.id()));

        criteria = criteria.and(afterCursor);
    }

    Query query = Query.query(criteria)
            .sort(Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")
            ))
            .limit(pageSize + 1);

    return template.select(Order.class)
            .matching(query)
            .all();
}
```

`tenantId` luôn được áp dụng ngoài nhóm cursor để mọi trang chỉ chứa dữ liệu thuộc tenant hiện tại. `afterCursor` biểu diễn đúng ngoặc của điều kiện SQL: `created_at < cursorTime OR (created_at = cursorTime AND id < cursorId)`. `limit(pageSize + 1)` lấy thêm một hàng để xác định có trang tiếp theo hay không.

Ví dụ dùng tên property Java trong `Criteria` và `Sort`; Spring Data ánh xạ sang cột theo metadata entity. API fluent của `Query` có thể có khác biệt nhỏ giữa các phiên bản Spring Data Relational, vì vậy hãy đối chiếu Javadoc đúng phiên bản dự án.

## 7. Vì sao lấy `pageSize + 1` hàng?

Nếu chỉ lấy đúng `pageSize` hàng, ứng dụng không biết còn hàng tiếp theo hay không nếu không chạy thêm truy vấn `EXISTS` hoặc `COUNT`. Một kỹ thuật phổ biến là lấy dư một hàng:

1. Client yêu cầu `pageSize = 20`.
2. Truy vấn lấy tối đa 21 hàng.
3. Nếu có 21 hàng, trang hiện tại có 20 hàng và `hasNext = true`.
4. Nếu chỉ có tối đa 20 hàng, `hasNext = false`.
5. Nếu có hàng dư, bỏ hàng thứ 21 khỏi nội dung trang.
6. Cursor tiếp theo được tạo từ hàng thứ 20, tức hàng cuối cùng thực sự trả cho client.

Không tạo cursor từ hàng dư. Nếu dùng hàng dư làm mốc, trang tiếp theo sẽ bắt đầu sau hàng đó và bỏ mất chính hàng chưa được trả về.

Giới hạn `pageSize` ở server, ví dụ tối thiểu 1 và tối đa 100, để client không thể yêu cầu một lượng dữ liệu tùy ý. Khi tính `pageSize + 1`, dùng kiểu số phù hợp và kiểm tra giới hạn để tránh overflow hoặc giá trị bất thường.

## 8. Tạo kết quả trang và cursor kế tiếp

Một response có thể chứa danh sách phần tử, cờ `hasNext` và cursor tiếp theo:

```java
public record CursorPage<T>(
        List<T> items,
        boolean hasNext,
        String nextCursor
) {
}
```

Ví dụ service gom số hàng đã giới hạn:

```java
public Mono<CursorPage<Order>> getOrders(
        Long tenantId,
        OrderCursor cursor,
        int requestedSize) {

    int pageSize = Math.max(1, Math.min(requestedSize, 100));

    return findNextOrders(tenantId, cursor, pageSize)
            .collectList()
            .map(rows -> {
                boolean hasNext = rows.size() > pageSize;
                List<Order> items = hasNext
                        ? List.copyOf(rows.subList(0, pageSize))
                        : List.copyOf(rows);

                String nextCursor = null;
                if (hasNext && !items.isEmpty()) {
                    Order last = items.get(items.size() - 1);
                    nextCursor = encodeCursor(
                            new OrderCursor(last.getCreatedAt(), last.getId()));
                }

                return new CursorPage<>(items, hasNext, nextCursor);
            });
}
```

`encodeCursor` là hàm thuộc tầng API của ứng dụng, được triển khai để tuần tự hóa cursor thành token. Ví dụ trên dùng `collectList()` vì truy vấn đã bị giới hạn tối đa 101 hàng; không nên thu toàn bộ bảng vào bộ nhớ chỉ để phân trang.

Nếu không có hàng dư, `hasNext` là false và `nextCursor` có thể để null. Nếu API muốn luôn trả cursor khi có dữ liệu, có thể thiết kế khác, nhưng client vẫn cần biết liệu có trang tiếp theo hay không.

## 9. Triển khai bằng `DatabaseClient`

Với truy vấn phức tạp hoặc khi muốn kiểm soát SQL chính xác, có thể viết hai câu SQL: một cho trang đầu và một cho trang tiếp theo. Ví dụ PostgreSQL với thứ tự giảm dần:

```java
private static final String FIRST_PAGE_SQL = """
        SELECT id, created_at, status
        FROM orders
        WHERE tenant_id = :tenantId
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """;

private static final String NEXT_PAGE_SQL = """
        SELECT id, created_at, status
        FROM orders
        WHERE tenant_id = :tenantId
          AND (
              created_at < :lastCreatedAt
              OR (created_at = :lastCreatedAt AND id < :lastId)
          )
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """;
```

Repository đọc:

```java
public Flux<OrderRow> findPage(
        Long tenantId,
        OrderCursor cursor,
        int limit) {

    String sql = cursor == null ? FIRST_PAGE_SQL : NEXT_PAGE_SQL;
    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql)
            .bind("tenantId", tenantId);

    if (cursor != null) {
        spec = spec.bind("lastCreatedAt", cursor.createdAt())
                .bind("lastId", cursor.id());
    }

    return spec.bind("limit", limit)
            .map((row, metadata) -> new OrderRow(
                    row.get("id", Long.class),
                    row.get("created_at", LocalDateTime.class),
                    row.get("status", String.class)
            ))
            .all();
}
```

`OrderRow` là DTO đọc phẳng. Tên cột trong `row.get(...)` phải khớp tên cột/alias mà SQL trả về. Kiểu Java phải tương thích với kiểu thực tế do driver cung cấp. Tên tham số được bind bằng API thay vì ghép giá trị vào chuỗi SQL.

Hai câu SQL được chọn bằng nhánh trong code cố định. Không nhận toàn bộ SQL hoặc tên cột sắp xếp từ client. Nếu API cho phép chọn thứ tự, ánh xạ lựa chọn đó qua danh sách sort key đã được server cho phép và tạo điều kiện tiếp nối tương ứng.

## 10. Cursor là gì và nên chứa những gì?

Cursor là thông tin đủ để xác định vị trí của trang hiện tại trong một thứ tự đã chọn. Với `ORDER BY created_at DESC, id DESC`, cursor cần ít nhất `created_at` và `id` của hàng cuối trang.

Một cursor tổng quát có thể chứa:

```java
public record OrderPageCursor(
        int version,
        LocalDateTime createdAt,
        Long id,
        String sort,
        String filterFingerprint
) {
}
```

Các trường có ý nghĩa:

- `version`: cho phép thay đổi định dạng cursor có kiểm soát.
- `createdAt`, `id`: các giá trị sắp xếp của hàng cuối trang.
- `sort`: xác định hướng/thứ tự mà cursor được tạo ra.
- `filterFingerprint`: giúp phát hiện cursor được dùng lại với bộ lọc khác.

Cursor thực tế có thể cần thêm tenant hoặc phạm vi truy vấn, nhưng tenant dùng để phân quyền vẫn phải lấy từ ngữ cảnh xác thực phía server. Không coi cursor do client gửi là bằng chứng người dùng có quyền truy cập dữ liệu.

## 11. Mã hóa và xác thực cursor

API thường trả cursor dưới dạng token opaque để client không cần hiểu cấu trúc bên trong. Một cách đơn giản là tuần tự hóa JSON rồi Base64 URL-safe. Base64 chỉ là mã hóa biểu diễn, không bảo vệ tính toàn vẹn và không che giấu dữ liệu.

Nếu cursor có thể bị sửa để thay đổi giá trị mốc hoặc filter, có thể ký token bằng HMAC hoặc dùng cơ chế bảo vệ tương đương. Server xác minh chữ ký trước khi sử dụng các giá trị. Nếu cursor chứa thông tin nhạy cảm, cần mã hóa bằng cơ chế phù hợp; chữ ký không phải mã hóa.

Khi giải mã, cần kiểm tra:

- Phiên bản token có được hỗ trợ không.
- Kiểu và phạm vi của mọi trường có hợp lệ không.
- Cursor có thuộc đúng loại truy vấn và thứ tự sắp xếp hiện tại không.
- Filter có tương ứng với filter của request hiện tại không.
- Token có chữ ký hợp lệ và chưa hết hạn nếu hệ thống đặt thời hạn không.
- Giá trị cursor có phù hợp với tenant/phạm vi quyền của người dùng hiện tại không.

Cursor không nên được xem là bí mật xác thực hay thay thế kiểm tra authorization. Mỗi request vẫn phải kiểm tra quyền và thêm điều kiện tenant/ownership vào truy vấn.

## 12. Bộ lọc phải được giữ nhất quán qua các trang

Điều kiện tiếp nối chỉ xác định vị trí trong thứ tự. Các bộ lọc nghiệp vụ phải được áp dụng lại ở mọi request:

```sql
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
```

Nếu trang đầu lọc `status = 'OPEN'` nhưng trang sau bỏ điều kiện này, kết quả có thể chứa trạng thái khác. Tương tự, tenant, quyền truy cập, phạm vi thời gian và các filter khác phải giữ nguyên.

Có thể đưa một fingerprint của filter vào cursor để từ chối token được dùng với bộ lọc khác. Fingerprint nên được tạo từ biểu diễn chuẩn hóa của các filter có ý nghĩa; không dựa vào thứ tự key tùy ý trong JSON hoặc chuỗi query chưa chuẩn hóa.

Không lấy filter fingerprint làm cơ chế bảo mật. Truy vấn vẫn phải bind giá trị và áp dụng điều kiện authorization độc lập.

## 13. Keyset pagination với cột nullable

Điều kiện tiếp nối đơn giản nhất giả định các cột sắp xếp không null. Nếu một cột có thể null, SQL comparison với `NULL` cho kết quả `UNKNOWN`; điều kiện `column < :cursorValue` không tự bao phủ các hàng null.

Có ba hướng thiết kế:

1. **Ưu tiên cột `NOT NULL`:** chọn các khóa sắp xếp có giá trị luôn tồn tại, chẳng hạn timestamp tạo và ID.
2. **Định nghĩa null ordering rõ ràng:** quy định `NULLS FIRST` hoặc `NULLS LAST` theo khả năng database, rồi mở rộng cursor predicate để phân biệt cursor null và không null.
3. **Dùng giá trị chuẩn hóa:** nếu phù hợp nghiệp vụ, tạo cột sort key không null hoặc generated column có quy tắc rõ ràng.

Ví dụ PostgreSQL:

```sql
ORDER BY published_at DESC NULLS LAST, id DESC
```

Khi đó predicate tiếp nối phải xử lý riêng trường hợp `published_at` của cursor là null và trường hợp không null. Không thể chỉ thay dấu `<` rồi mong SQL tự xử lý đúng thứ tự null.

Với truy vấn quan trọng, tránh nullable sort key nếu không có nhu cầu nghiệp vụ rõ ràng. Một cursor đơn giản trên các cột `NOT NULL` dễ triển khai và kiểm thử hơn.

## 14. Điều gì xảy ra khi dữ liệu thay đổi giữa các trang?

Keyset giảm hiện tượng dịch chuyển vị trí do insert ở đầu danh sách, nhưng không tự tạo một snapshot database xuyên suốt nhiều HTTP request.

Giả sử trang đầu đã trả các hàng mới nhất tới cursor C:

- Một hàng mới hơn C được insert sau đó thường nằm trước cursor và không xuất hiện ở các trang tiếp theo. Đây thường là hành vi mong muốn khi duyệt tiếp lịch sử.
- Một hàng mới có khóa sắp xếp nhỏ hơn C có thể xuất hiện ở trang tiếp theo nếu nó thỏa điều kiện cursor và filter.
- Một hàng bị xóa trước khi được đọc sẽ không còn xuất hiện.
- Một hàng đã đọc nhưng bị sửa trường sắp xếp để chuyển xuống sau cursor có thể xuất hiện lần nữa.
- Một hàng chưa đọc nhưng bị sửa để chuyển lên trước cursor có thể bị bỏ qua.
- Thay đổi trạng thái hoặc filter membership có thể làm hàng đi vào hoặc ra khỏi tập kết quả giữa các trang.

Vì vậy, keyset phù hợp cho duyệt tuần tự ổn định khi khóa sắp xếp ít thay đổi, nhưng không tương đương một snapshot nhất quán tuyệt đối. Nếu nghiệp vụ cần snapshot, có thể cần một cutoff cố định, version/snapshot ID, bảng kết quả tạm hoặc cơ chế transaction snapshot phù hợp. Giữ transaction database mở giữa nhiều request thường không phải lựa chọn phù hợp cho API thông thường.

## 15. Dùng cutoff để ổn định tập dữ liệu

Với feed mới nhất trước, có thể cố định thời điểm bắt đầu duyệt bằng `asOf`:

```sql
WHERE tenant_id = :tenantId
  AND created_at <= :asOf
  AND (
      created_at < :lastCreatedAt
      OR (created_at = :lastCreatedAt AND id < :lastId)
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit
```

Trang đầu ghi nhận `asOf` và mọi trang sau dùng lại. Cách này ngăn các hàng được tạo sau thời điểm bắt đầu chen vào tập kết quả, với điều kiện `created_at` phản ánh đúng thời điểm và không bị sửa. Nó không ngăn xóa hàng, thay đổi các filter khác hoặc sửa dữ liệu đã tồn tại.

Nếu cần một snapshot thực sự của nhiều bảng hoặc báo cáo tài chính, cutoff đơn giản có thể chưa đủ. Cần xác định rõ yêu cầu nhất quán và chọn isolation, snapshot/version hoặc mô hình dữ liệu phù hợp.

## 16. Chỉ mục cho keyset pagination

Keyset có lợi thế hiệu năng khi database có index phù hợp với filter và thứ tự sắp xếp. Với truy vấn:

```sql
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :limit
```

Một index cần xem xét là:

```sql
CREATE INDEX ix_orders_tenant_created_id
    ON orders (tenant_id, created_at DESC, id DESC);
```

`tenant_id` đứng đầu vì truy vấn lọc theo tenant; các cột tiếp theo hỗ trợ thứ tự duyệt. Nếu truy vấn thường lọc thêm `status` bằng equality, có thể đánh giá index `(tenant_id, status, created_at DESC, id DESC)`. Thứ tự index thực tế phải dựa trên workload và execution plan.

Các nguyên tắc:

- Cột equality filter thường đứng trước nhóm cột sắp xếp trong composite index.
- Thứ tự và hướng các cột trong index cần phù hợp với `ORDER BY` và cách database có thể scan ngược.
- Tie-breaker nên nằm trong index nếu nó là một phần của thứ tự keyset.
- Không tạo nhiều index gần giống nhau nếu chưa đo lợi ích và chi phí ghi.
- Dùng `EXPLAIN`/`EXPLAIN ANALYZE` trên dữ liệu gần thực tế để xác minh database có seek theo index hay không.

Index không làm truy vấn nhanh một cách tự động. Nếu filter không chọn lọc, sort không khớp index hoặc query planner chọn kế hoạch khác, keyset vẫn có thể phải đọc nhiều hàng.

## 17. Phân trang ngược

Nhiều API chỉ cần “next page”. Nếu cần “previous page”, có thể truy vấn theo chiều ngược so với thứ tự hiển thị:

1. Dùng cursor của hàng đầu trang hiện tại.
2. Tạo điều kiện tìm các hàng đứng trước hàng đó trong thứ tự hiển thị.
3. Đảo chiều `ORDER BY` để database lấy các hàng gần cursor nhất.
4. Giới hạn số hàng cần lấy.
5. Đảo danh sách trong ứng dụng để trả lại đúng thứ tự hiển thị ban đầu.

Ví dụ thứ tự hiển thị là `created_at DESC, id DESC`. Để lấy các hàng ngay trước trang hiện tại, truy vấn có thể dùng `created_at > cursorTime OR (created_at = cursorTime AND id > cursorId)`, sắp xếp `created_at ASC, id ASC`, lấy giới hạn rồi đảo kết quả. Điều kiện cụ thể phải khớp với cách cursor đầu trang được xác định.

Nếu API không cần quay lại, không cần triển khai chiều ngược chỉ để bắt chước giao diện page number. Hãy giữ hợp đồng đơn giản theo nhu cầu thực tế.

## 18. So sánh keyset với scrolling API của Spring Data

Spring Data Commons có các abstraction về scrolling như `ScrollPosition`, `Window` và keyset-based scrolling trong một số loại repository/store. Tuy nhiên, hỗ trợ phụ thuộc store module, loại repository và phiên bản Spring Data; không nên giả định mọi API scrolling trong Spring Data JPA đều có mặt hoặc hoạt động giống hệt trong reactive R2DBC.

Trước khi dùng API scrolling dựng sẵn, hãy kiểm tra tài liệu đúng phiên bản Spring Data Relational/R2DBC và chữ ký repository đang dùng. Nếu reactive repository hoặc query cụ thể chưa hỗ trợ kiểu scrolling cần thiết, có thể triển khai seek pagination tường minh bằng `Criteria`/`Query` hoặc `DatabaseClient` như các ví dụ trong bài.

Triển khai thủ công cũng giúp nhìn rõ cursor predicate, tenant filter, sort order và cách tạo token. Đổi lại, ứng dụng phải tự chịu trách nhiệm bảo đảm mọi nhánh truy vấn dùng cùng thứ tự, cùng filter và cùng quy tắc cursor.

## 19. Khi nào nên dùng keyset và khi nào không?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Danh sách hàng triệu bản ghi, duyệt tiếp tuần tự | Keyset | Tránh offset sâu và dùng index để seek |
| Infinite scroll hoặc nút “Load more” | Keyset | Cursor tự nhiên cho lần tải kế tiếp |
| Feed theo thời gian, thứ tự có ID tie-breaker | Keyset | Có thể tiếp tục từ mốc cuối ổn định |
| Bảng nhỏ, chỉ vài trang | Offset | Dễ triển khai, chi phí bỏ qua thấp |
| Người dùng cần nhảy trực tiếp đến trang số 50 | Offset hoặc chiến lược mốc trang riêng | Keyset không có vị trí số trang tự nhiên |
| Cần tổng số trang và số trang hiện tại | Offset kết hợp count, hoặc thiết kế API khác | Keyset thường không tính tổng số trang |
| Thứ tự sắp xếp thay đổi tùy ý và không có tie-breaker | Chưa nên dùng keyset | Cursor không xác định được vị trí ổn định |
| Cần snapshot tuyệt đối trong thời gian duyệt dài | Snapshot/version hoặc cơ chế chuyên biệt | Cursor không tự giữ snapshot giữa các request |

Keyset không nhất thiết thay thế offset trên toàn hệ thống. Có thể dùng hai kiểu phân trang cho hai use case khác nhau.

## 20. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Không có `ORDER BY` ổn định | Thứ tự hàng thay đổi giữa các request | Sắp xếp tường minh và thêm khóa duy nhất |
| Cursor chỉ chứa cột sort không duy nhất | Bỏ sót hoặc lặp hàng có cùng giá trị sort | Thêm tie-breaker và lưu toàn bộ sort key trong cursor |
| Dùng sai dấu so sánh | Trang kế tiếp lặp lại dữ liệu hoặc bỏ qua hàng | Đối chiếu `ASC` với `>` và `DESC` với `<` |
| Trộn nhiều chiều sort nhưng dùng một dấu so sánh | Điều kiện tiếp nối sai thứ tự từ điển | Xây dựng từng nhánh theo từng cột và hướng riêng |
| Quên nhóm ngoặc trong predicate | Điều kiện tenant/filter có thể bị nới lỏng | Đặt nhóm cursor trong `AND (...)` và kiểm thử dữ liệu khác tenant |
| Tạo cursor từ hàng dư `pageSize + 1` | Bỏ mất hàng chưa trả về | Cursor lấy từ hàng cuối thực sự được trả |
| Bỏ filter ở các trang sau | Kết quả trang sau không cùng tập dữ liệu | Áp dụng lại toàn bộ filter và authorization |
| Dùng sort key nullable mà không xử lý null | Hàng null bị bỏ qua hoặc thứ tự sai | Dùng key không null hoặc định nghĩa null ordering và predicate đầy đủ |
| Sort key bị thay đổi giữa các request | Hàng có thể bị lặp hoặc bỏ sót | Ưu tiên khóa bất biến hoặc dùng snapshot/version khi cần |
| Không giới hạn page size | Request có thể tải quá nhiều dữ liệu | Áp dụng min/max ở server và lấy thêm một hàng để xác định `hasNext` |
| Dùng cursor thay cho authorization | Người dùng có thể thử truy cập phạm vi dữ liệu khác | Xác thực và áp dụng quyền ở mọi request |
| Không có index phù hợp | Keyset vẫn có thể quét nhiều hàng hoặc sort tốn kém | Thiết kế composite index và xem execution plan |

## 21. Kiểm thử keyset pagination

Kiểm thử cần chứng minh các trang nối tiếp nhau không lặp và không bỏ sót trong một tập dữ liệu ổn định. Nên tạo nhiều hàng có cùng giá trị sort chính để buộc tie-breaker hoạt động.

Ví dụ dữ liệu:

| ID | `created_at` | Thứ tự giảm dần |
| ---: | --- | ---: |
| 105 | 10:00 | 1 |
| 104 | 10:00 | 2 |
| 103 | 10:00 | 3 |
| 102 | 09:00 | 4 |
| 101 | 08:00 | 5 |

Với page size 2 và `ORDER BY created_at DESC, id DESC`, kết quả mong đợi:

- Trang 1: ID 105, 104; cursor `(10:00, 104)`.
- Trang 2: ID 103, 102; cursor `(09:00, 102)`.
- Trang 3: ID 101; không còn cursor tiếp theo.

Các trường hợp cần kiểm tra:

1. Trang đầu không có cursor và trả các hàng đầu theo thứ tự.
2. Trang tiếp theo dùng đúng cả hai giá trị cursor.
3. Nhiều hàng trùng timestamp vẫn được phân trang đầy đủ nhờ ID tie-breaker.
4. Không có hàng nào lặp lại hoặc bị bỏ qua trong tập dữ liệu không thay đổi.
5. Hàng dư chỉ dùng để tính `hasNext`, không bị bỏ khỏi mọi trang.
6. Filter tenant, status và khoảng thời gian được áp dụng trên mọi trang.
7. Cursor sai định dạng, hết hạn hoặc có chữ ký sai bị từ chối.
8. Page size bằng 0, âm hoặc vượt giới hạn được xử lý theo hợp đồng API.
9. Cột nullable và các hướng sort hỗn hợp được kiểm thử nếu use case hỗ trợ.
10. Hành vi khi có insert, delete hoặc cập nhật sort key giữa các trang được xác định rõ.

Với reactive code, có thể dùng `StepVerifier` để xác minh publisher. Với toàn bộ chuỗi phân trang, integration test nên gọi liên tiếp bằng `nextCursor`, nối các ID nhận được và so sánh với thứ tự kỳ vọng trong database.

## 22. Quy trình triển khai

Khi thiết kế một endpoint keyset pagination, có thể thực hiện theo trình tự:

1. Xác định use case có cần tải tiếp tuần tự hay cần nhảy tới số trang.
2. Chọn thứ tự sắp xếp có ý nghĩa nghiệp vụ và ổn định.
3. Bổ sung khóa duy nhất làm tie-breaker nếu sort key chính có thể trùng.
4. Xác định chiều ASC/DESC của từng cột và viết predicate tiếp nối theo đúng thứ tự từ điển.
5. Chọn `Criteria`/`Query` hoặc `DatabaseClient` theo độ phức tạp và nhu cầu kiểm soát SQL.
6. Áp dụng lại mọi filter, tenant scope và authorization ở từng request.
7. Lấy `pageSize + 1`, cắt phần tử dư và tạo cursor từ hàng cuối đã trả.
8. Mã hóa/kiểm tra cursor ở ranh giới API; không dùng cursor thay quyền truy cập.
9. Tạo composite index phù hợp và xác minh bằng execution plan.
10. Kiểm thử dữ liệu trùng sort key, trang cuối, dữ liệu thay đổi và cursor không hợp lệ.
11. Theo dõi query latency, số hàng đọc, kích thước trang và tỷ lệ request lỗi.

## 23. Nguyên tắc thực hành

- Dùng keyset cho danh sách lớn, infinite scroll và các luồng cần duyệt tiếp tuần tự.
- Chọn `ORDER BY` xác định và thêm unique tie-breaker ở cuối.
- Lưu trong cursor tất cả giá trị cần thiết để tái tạo vị trí trong thứ tự.
- Với ASC, điều kiện tiếp nối dùng `>`; với DESC, dùng `<`; xử lý riêng từng cột khi sort hỗn hợp.
- Giữ nhóm cursor trong ngoặc và kết hợp với tenant/filter bằng `AND`.
- Lấy dư một hàng để xác định `hasNext`; tạo cursor từ hàng cuối đã thực sự trả về.
- Áp dụng lại filter và authorization ở mọi trang.
- Dùng cột sort không null và ít thay đổi; nếu không, định nghĩa rõ null ordering và hành vi khi dữ liệu thay đổi.
- Giới hạn page size, bind mọi giá trị và xác thực cursor.
- Tạo index khớp với equality filters và thứ tự sắp xếp; xác minh bằng query plan.
- Không giả định cursor tạo snapshot nhất quán tuyệt đối hoặc cung cấp tổng số trang.
- Kiểm tra khả năng scrolling dựng sẵn của đúng phiên bản Spring Data R2DBC trước khi sử dụng; nếu không phù hợp, triển khai seek query tường minh.

## 24. Kết luận

Keyset pagination xác định trang tiếp theo bằng khóa sắp xếp của hàng cuối trang trước. Với thứ tự `created_at DESC, id DESC`, điều kiện tiếp nối là `created_at` nhỏ hơn cursor hoặc timestamp bằng nhau và ID nhỏ hơn cursor. Khóa tie-breaker duy nhất, predicate có nhóm đúng và index phù hợp là các yếu tố cần thiết để phân trang ổn định và hiệu quả.

Trong Spring Data Relational R2DBC, có thể xây dựng điều kiện bằng `Criteria`/`Query` hoặc SQL qua `DatabaseClient`, sau đó tiếp tục xử lý bằng publisher reactive. Keyset phù hợp với danh sách lớn và tải tiếp tuần tự; offset vẫn phù hợp khi cần nhảy trang hoặc dữ liệu nhỏ. Cursor giúp định vị kết quả nhưng không thay thế authorization và cũng không bảo đảm snapshot tuyệt đối khi dữ liệu đang thay đổi. Hãy chọn phương pháp theo nhu cầu thực tế, xác định rõ thứ tự và kiểm thử các trường hợp biên trước khi đưa vào API.
