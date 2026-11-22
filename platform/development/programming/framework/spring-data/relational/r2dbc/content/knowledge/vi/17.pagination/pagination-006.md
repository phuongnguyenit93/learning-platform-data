# Thiết kế kết quả phân trang khi không cần tổng số bản ghi

## 1. Vì sao không phải API phân trang nào cũng cần total count?

Nhiều màn hình chỉ cần hiển thị một nhóm bản ghi và cho phép người dùng bấm **Tiếp theo** hoặc **Tải thêm**. Chúng không cần biết toàn bộ bảng có bao nhiêu hàng, có bao nhiêu trang hoặc bản ghi hiện tại đang nằm ở vị trí nào trong toàn bộ tập dữ liệu.

Nếu API luôn tính tổng số bản ghi, mỗi request có thể phải chạy thêm một câu COUNT. Với bảng lớn hoặc filter phức tạp, truy vấn đếm có thể tốn tài nguyên đáng kể dù phần dữ liệu trả về chỉ có vài chục hàng. Count query còn có thể đọc một phạm vi dữ liệu lớn hơn nhiều so với query lấy trang.

Trong Spring Data Relational R2DBC, có thể thiết kế response phân trang không cần total bằng cách lấy nhiều hơn số hàng cần hiển thị một hàng. Ví dụ client yêu cầu 20 hàng, server truy vấn tối đa 21 hàng:

- Nếu nhận được 21 hàng, server trả 20 hàng đầu và đặt hasNext thành true.
- Nếu nhận được tối đa 20 hàng, server trả toàn bộ số hàng đó và đặt hasNext thành false.

Cách này tránh một truy vấn COUNT riêng chỉ để biết có trang kế tiếp hay không. Nó phù hợp với giao diện danh sách, feed, lịch sử, hoạt động gần đây và API dạng load more.

Bài này trình bày cách thiết kế response, triển khai với R2DBC, lựa chọn offset hoặc keyset pagination, xử lý dữ liệu thay đổi đồng thời và kiểm thử hành vi phân trang.

## 2. Page, Slice và kết quả phân trang tối giản

Các kiểu kết quả phân trang thường trả lời những câu hỏi khác nhau.

| Kiểu kết quả | Thông tin thường có | Có cần total count? | Phù hợp khi |
|---|---|---:|---|
| Page | Content, page number, size, total elements, total pages | Thường có | UI cần số trang hoặc tổng số kết quả |
| Slice | Content, thông tin trang và hasNext/hasPrevious | Không nhất thiết | UI chỉ cần biết còn dữ liệu để tải tiếp |
| Cursor page | Content, next cursor và có thể có previous cursor | Không | Tập dữ liệu lớn, phân trang liên tục |
| Infinite feed | Content và dấu hiệu còn dữ liệu | Không | Timeline, activity feed, load more |

Page có thể cần một count query để xác định tổng số phần tử và tổng số trang. Cách Spring Data thực thi count có thể được tối ưu trong một số trường hợp, nhưng nếu API không dùng total thì việc yêu cầu count ngay từ đầu là công việc không cần thiết.

Slice tập trung vào việc trả lời: "Sau phần dữ liệu này còn phần tử nào không?". Cursor page tập trung vào việc trả lời: "Tôi cần tiếp tục từ vị trí nào?".

Trong reactive repository, hãy chú ý kiểu trả về mà phiên bản Spring Data R2DBC đang sử dụng hỗ trợ. Reactive query thường trả Flux hoặc Mono; không nên giả định mọi repository method có thể trả Page hoặc tự tạo Slice với count semantics giống repository imperative. Khi cần hasNext một cách rõ ràng, có thể triển khai query giới hạn ở DatabaseClient hoặc R2dbcEntityTemplate rồi tự xây response DTO.

Điểm quan trọng là hợp đồng API chỉ chứa thông tin người tiêu dùng thực sự cần. Nếu client chỉ cần nút Next, không cần gửi totalElements và totalPages.

## 3. Kỹ thuật lấy thêm một hàng: limit + 1

Giả sử page size mà client yêu cầu là N. Server truy vấn N + 1 hàng.

~~~text
Client yêu cầu size = 5

Database trả:
[A, B, C, D, E, F]

Server:
- Trả content: [A, B, C, D, E]
- Bỏ hàng F khỏi content
- hasNext = true

Nếu database chỉ trả:
[A, B, C]

Server:
- Trả content: [A, B, C]
- hasNext = false
~~~

Hàng thứ N + 1 chỉ là bằng chứng có thêm dữ liệu. Không đưa hàng đó vào response hiện tại.

### 3.1. Thuật toán

1. Xác thực page size.
2. Tính fetch size bằng page size cộng một.
3. Đặt LIMIT trong query ở mức fetch size.
4. Đọc tối đa fetch size hàng.
5. Nếu số hàng đọc lớn hơn page size, đặt hasNext = true.
6. Loại hàng phụ khỏi content.
7. Tạo next position/cursor nếu có trang tiếp theo.
8. Trả response không chứa total count.

Độ phức tạp của phần xử lý trong ứng dụng chỉ phụ thuộc vào số hàng tối đa N + 1. Không cần đọc toàn bộ kết quả rồi mới cắt.

### 3.2. Vì sao không chỉ gọi take(N + 1)?

Toán tử Reactor như take có thể giới hạn số phần tử downstream nhận được, nhưng không phải lúc nào cũng bảo đảm database chỉ thực hiện công việc cho N + 1 hàng.

Giới hạn phải được đặt trong câu query bằng LIMIT, FETCH FIRST, TOP hoặc cơ chế tương ứng của database. Sau đó có thể dùng Reactor để xử lý publisher đã bị giới hạn ở database.

### 3.3. Có thể dùng collectList vì số hàng đã bị giới hạn

Trong reactive pipeline, collectList thường không phù hợp với Flux không giới hạn vì nó giữ toàn bộ kết quả trong bộ nhớ.

Với query đã đặt LIMIT bằng N + 1 và N có mức tối đa rõ ràng, collectList là hợp lý để tạo một response chứa content cùng hasNext. Bộ nhớ tối đa của bước này được kiểm soát bởi page size đã validate.

Nếu API cần streaming từng hàng thay vì một envelope JSON, có thể thiết kế contract khác. Nhưng để trả cả content và hasNext trong cùng response, server thường cần biết kết quả đã đọc đủ N + 1 hàng hay chưa trước khi gửi envelope.

## 4. Thiết kế response DTO

Một response offset đơn giản có thể là:

~~~java
public record OffsetSlice<T>(
    List<T> items,
    int page,
    int size,
    boolean hasNext,
    Integer nextPage
) {
}
~~~

Response JSON minh họa:

~~~json
{
  "items": [
    {
      "id": 501,
      "status": "OPEN"
    },
    {
      "id": 502,
      "status": "OPEN"
    }
  ],
  "page": 0,
  "size": 2,
  "hasNext": true,
  "nextPage": 1
}
~~~

Response không có totalElements và totalPages. Client chỉ cần kiểm tra hasNext để quyết định có hiển thị nút Next hoặc Load more hay không.

Một response cursor có thể là:

~~~java
public record CursorSlice<T>(
    List<T> items,
    int size,
    boolean hasNext,
    String nextCursor
) {
}
~~~

Nếu hasNext là false, nextCursor nên là null hoặc được bỏ khỏi JSON theo quy ước API. Không tạo cursor giả cho một trang cuối.

### 4.1. Không đặt tên trường gây hiểu nhầm

Nếu API không biết tổng số phần tử, không gửi:
- totalElements = 0.
- totalPages = 0.
- totalPages = -1.
- isLast được tính bằng cách đoán từ page size.

Những giá trị đó dễ khiến client hiểu nhầm là đã có count chính xác.

Dùng hasNext thể hiện đúng điều server biết tại thời điểm truy vấn.

### 4.2. Có cần hasPrevious không?

hasPrevious không tự suy ra từ hasNext. Với offset pagination, nếu page > 0 thì có thể cung cấp next/previous page number theo contract. Tuy nhiên, nếu dữ liệu bị xóa giữa các lần truy vấn, trang trước có thể không còn cùng nội dung.

Với cursor pagination, previous cursor cần được lưu hoặc được tạo bằng một query theo hướng ngược. Không nên gửi hasPrevious = true nếu server không có cách tiếp tục chính xác theo contract.

### 4.3. Metadata nên tối giản

Các trường thường đủ cho load more:

- items: dữ liệu của lần lấy hiện tại.
- size: số hàng thực tế hoặc kích thước tối đa theo quy ước đã công bố.
- hasNext: có thêm dữ liệu tại thời điểm query hay không.
- nextCursor hoặc nextPage: vị trí bắt đầu lần tiếp theo.

Nếu client cần biết số hàng thực tế, size có thể là items.size(). Nếu size biểu thị page size yêu cầu, cần tài liệu hóa rõ. Không dùng một trường size với hai ý nghĩa khác nhau.

## 5. Triển khai offset slice với DatabaseClient

Ví dụ sau dùng PostgreSQL-style LIMIT/OFFSET và một filter trạng thái. Cần điều chỉnh kiểu timestamp, tên cột và cú pháp theo database/driver của dự án.

DTO:

~~~java
public record OrderSummary(
    Long id,
    String status,
    LocalDateTime createdAt
) {
}

public record OffsetSlice<T>(
    List<T> items,
    int page,
    int size,
    boolean hasNext,
    Integer nextPage
) {
}
~~~

Service:

~~~java
@Service
public class OrderQueryService {

    private static final int MAX_PAGE_SIZE = 100;

    private final DatabaseClient databaseClient;

    public OrderQueryService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<OffsetSlice<OrderSummary>> search(
            String tenantId,
            String status,
            int page,
            int requestedSize) {

        int size = validatePageSize(requestedSize);
        validatePage(page);

        long offset = Math.multiplyExact((long) page, size);
        int fetchSize = size + 1;

        return databaseClient.sql("""
                SELECT id, status, created_at
                FROM orders
                WHERE tenant_id = :tenantId
                  AND status = :status
                ORDER BY created_at DESC, id DESC
                LIMIT :fetchSize
                OFFSET :offset
                """)
            .bind("tenantId", tenantId)
            .bind("status", status)
            .bind("fetchSize", fetchSize)
            .bind("offset", offset)
            .map((row, metadata) -> new OrderSummary(
                row.get("id", Long.class),
                row.get("status", String.class),
                row.get("created_at", LocalDateTime.class)
            ))
            .all()
            .collectList()
            .map(rows -> toSlice(rows, page, size));
    }

    private int validatePageSize(int requestedSize) {
        if (requestedSize < 1 || requestedSize > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "Page size must be between 1 and " + MAX_PAGE_SIZE
            );
        }
        return requestedSize;
    }

    private void validatePage(int page) {
        if (page < 0) {
            throw new IllegalArgumentException(
                "Page must be zero or greater"
            );
        }
    }

    private OffsetSlice<OrderSummary> toSlice(
            List<OrderSummary> rows,
            int page,
            int size) {

        boolean hasNext = rows.size() > size;

        List<OrderSummary> content = hasNext
            ? List.copyOf(rows.subList(0, size))
            : List.copyOf(rows);

        Integer nextPage = hasNext ? page + 1 : null;

        return new OffsetSlice<>(
            content,
            page,
            size,
            hasNext,
            nextPage
        );
    }
}
~~~

Trong ví dụ, tenantId phải đến từ security context đã xác thực hoặc một nguồn đã được kiểm tra quyền. Không tin tenantId tùy ý từ query parameter.

### 5.1. Vì sao query dùng ORDER BY hai cột?

Query sắp xếp theo created_at DESC và id DESC. Nếu nhiều order có cùng timestamp, id tạo thứ tự phụ ổn định.

Nếu chỉ ORDER BY created_at, database có thể trả các hàng cùng timestamp theo thứ tự khác nhau giữa các lần chạy. Khi dùng OFFSET, điều đó có thể khiến một hàng xuất hiện ở hai trang hoặc bị bỏ qua.

Mọi phân trang cần một thứ tự xác định, tốt nhất kết thúc bằng một khóa duy nhất.

### 5.2. Vì sao offset được tính bằng long?

Phép nhân page × size có thể tràn số nguyên 32-bit nếu page quá lớn. Dùng Math.multiplyExact với long giúp phát hiện overflow thay vì tạo offset âm hoặc sai.

Ngoài kiểm tra overflow, API vẫn cần giới hạn page tối đa hoặc chuyển sang cursor pagination cho tập dữ liệu lớn. Một offset hợp lệ về kiểu số vẫn có thể quá đắt với database.

### 5.3. Vì sao collectList an toàn trong ví dụ?

SQL đặt LIMIT bằng fetchSize, trong đó fetchSize tối đa bằng MAX_PAGE_SIZE + 1. Service không thu thập toàn bộ bảng.

Nếu query bỏ LIMIT hoặc page size không có giới hạn, collectList có thể làm heap tăng theo kích thước dữ liệu và phá vỡ mục tiêu bảo vệ tài nguyên.

## 6. Triển khai với R2dbcEntityTemplate

Khi query phù hợp với Criteria API, có thể dùng R2dbcEntityTemplate thay cho SQL viết tay.

Ví dụ khái niệm:

~~~java
public Mono<OffsetSlice<Order>> findOpenOrders(
        int page,
        int requestedSize) {

    int size = validatePageSize(requestedSize);
    long offset = Math.multiplyExact((long) page, size);

    Query query = Query.query(
            Criteria.where("status").is("OPEN")
        )
        .sort(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(size + 1)
        .offset(offset);

    return template.select(query, Order.class)
        .all()
        .collectList()
        .map(rows -> {
            boolean hasNext = rows.size() > size;

            List<Order> content = hasNext
                ? List.copyOf(rows.subList(0, size))
                : List.copyOf(rows);

            return new OffsetSlice<>(
                content,
                page,
                size,
                hasNext,
                hasNext ? page + 1 : null
            );
        });
}
~~~

Đây là ví dụ theo API Spring Data Relational phổ biến; hãy kiểm tra signature Query, limit, offset và sort theo phiên bản đang dùng. Nếu phiên bản không hỗ trợ một API cụ thể, có thể dùng DatabaseClient để kiểm soát SQL trực tiếp.

Điều quan trọng vẫn là query thực thi ở database có giới hạn size + 1, sort ổn định và filter authorization đầy đủ.

## 7. Repository reactive và giới hạn của Page

Trong ứng dụng reactive, repository method thường phát Flux hoặc Mono. Không nên thiết kế một API yêu cầu total count rồi cố bọc kết quả vào Mono chỉ để có cảm giác reactive.

Một số lưu ý:

- Page thường mang total elements và total pages, nên cần thông tin count.
- Reactive repository không nhất thiết hỗ trợ Page theo cùng cách repository imperative.
- Pageable có thể được hỗ trợ như tham số giới hạn/sort trong một số query method và phiên bản, nhưng không đồng nghĩa repository tự cung cấp một Slice hoàn chỉnh.
- Nếu cần hasNext chính xác theo limit + 1, hãy kiểm soát fetch size và xây response ở service.
- Hãy kiểm tra tài liệu của đúng Spring Data R2DBC version thay vì dựa vào behavior của Spring Data JPA.

Một repository có thể cung cấp dữ liệu Flux, còn service chịu trách nhiệm tạo envelope phân trang. Cách này làm rõ nơi áp dụng page size, hasNext và cursor.

Không trả Page giả với totalElements được đoán. Nếu client cần tổng số chính xác, hãy coi count là một yêu cầu riêng có chi phí và semantics rõ ràng.

## 8. Offset pagination khi không cần total

Offset pagination vẫn có thể hữu ích nếu người dùng cần số trang hiện tại hoặc quay lại trang trước.

Ví dụ:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize
OFFSET :offset;
~~~

Mỗi trang dùng fetchSize = pageSize + 1. Nếu có hàng phụ, trả hasNext = true và nextPage = page + 1.

### 8.1. Ưu điểm

- Dễ hiểu và dễ triển khai.
- Client có thể yêu cầu một trang cụ thể.
- Dễ hỗ trợ Previous/Next bằng số trang.
- Dễ kiểm thử với dataset nhỏ.
- Phù hợp với bảng dữ liệu vừa phải và index/query phù hợp.

### 8.2. Nhược điểm

Offset lớn có thể khiến database phải duyệt hoặc bỏ qua nhiều hàng trước khi trả kết quả. Chi phí có thể tăng theo độ sâu trang, tùy execution plan và database.

Nếu người dùng liên tục bấm Next qua hàng nghìn trang, keyset pagination thường là lựa chọn phù hợp hơn.

### 8.3. Giới hạn page sâu

Nếu vẫn dùng offset:
- Đặt max page hoặc max offset.
- Đặt page size tối đa.
- Có index hỗ trợ filter và sort.
- Theo dõi query latency theo page depth.
- Trả lỗi có ý nghĩa khi client yêu cầu trang quá sâu.
- Cân nhắc chuyển sang cursor cho feed lớn.

Không dùng total count để suy ra rằng offset sâu là rẻ. Count và lấy trang là hai chi phí khác nhau.

## 9. Keyset pagination khi không cần total

Keyset pagination tiếp tục từ giá trị sort của hàng cuối trang trước thay vì bỏ qua một số lượng hàng bằng offset.

Giả sử dữ liệu được sắp xếp:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Cursor của trang trước chứa created_at và id của hàng cuối cùng đã trả.

Trang tiếp theo:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :fetchSize;
~~~

Vẫn lấy pageSize + 1 để xác định hasNext.

### 9.1. Vì sao cần cả khóa phụ?

Nếu chỉ dùng created_at làm cursor và có nhiều hàng cùng timestamp, điều kiện created_at < lastCreatedAt có thể bỏ qua những hàng còn lại có cùng timestamp.

Kết hợp id tạo thứ tự duy nhất:

- created_at nhỏ hơn timestamp cuối.
- Hoặc created_at bằng timestamp cuối và id nhỏ hơn id cuối.

Đây là phép so sánh từ điển cho cặp sort key theo hướng giảm dần.

### 9.2. Cursor phải khớp với ORDER BY

Nếu sort theo created_at DESC, id DESC thì predicate phải sử dụng cùng thứ tự và hướng.

Nếu sort theo amount ASC, created_at DESC, id DESC, predicate sẽ phức tạp hơn vì mỗi trường có hướng khác nhau. Hãy xây logic keyset tương ứng với từng tổ hợp sort đã allowlist, hoặc giới hạn API vào một số thứ tự cố định.

Không tạo cursor từ một trường nhưng query lại sắp xếp theo trường khác.

### 9.3. Chọn sort key ổn định

Ưu tiên trường:
- Có giá trị không null hoặc có null ordering được xác định.
- Có index hỗ trợ.
- Ít thay đổi sau khi bản ghi được tạo.
- Kết hợp được với khóa duy nhất.

created_at thường ổn định hơn updated_at. Nếu dùng updated_at làm cursor và một hàng được cập nhật, nó có thể di chuyển qua vị trí cursor và xuất hiện lặp hoặc bị bỏ qua.

### 9.4. Index cho keyset query

Ví dụ query lọc tenant và status, sort created_at DESC, id DESC. Có thể cần index phù hợp với thứ tự predicate và sort:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Index cụ thể phụ thuộc database, selectivity, filter và workload. Hãy dùng EXPLAIN/EXPLAIN ANALYZE trên dữ liệu đại diện để xác nhận database có thể tận dụng index.

Không tạo index chỉ dựa vào hình dạng SQL mà không đo write overhead và storage.

## 10. Triển khai cursor slice với DatabaseClient

DTO cursor:

~~~java
public record OrderCursor(
    LocalDateTime createdAt,
    long id
) {
}

public record CursorSlice<T>(
    List<T> items,
    int size,
    boolean hasNext,
    String nextCursor
) {
}
~~~

Ví dụ service đơn giản với cursor đã được giải mã và kiểm tra:

~~~java
public Mono<CursorSlice<OrderSummary>> nextOrders(
        String tenantId,
        String status,
        String encodedCursor,
        int requestedSize) {

    int size = validatePageSize(requestedSize);
    int fetchSize = size + 1;

    Mono<List<OrderSummary>> rows;

    if (encodedCursor == null) {
        rows = firstPage(tenantId, status, fetchSize);
    } else {
        OrderCursor cursor = cursorCodec.decodeAndVerify(encodedCursor);

        rows = nextPage(
            tenantId,
            status,
            cursor,
            fetchSize
        );
    }

    return rows.map(result -> {
        boolean hasNext = result.size() > size;

        List<OrderSummary> content = hasNext
            ? List.copyOf(result.subList(0, size))
            : List.copyOf(result);

        String nextCursor = hasNext
            ? cursorCodec.encode(content.get(content.size() - 1))
            : null;

        return new CursorSlice<>(
            content,
            content.size(),
            hasNext,
            nextCursor
        );
    });
}
~~~

Các phương thức firstPage và nextPage cần đặt LIMIT bằng fetchSize ở database. Không lấy toàn bộ dữ liệu rồi dùng subList để giả lập keyset.

### 10.1. Query trang đầu

~~~java
private Mono<List<OrderSummary>> firstPage(
        String tenantId,
        String status,
        int fetchSize) {

    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE tenant_id = :tenantId
              AND status = :status
            ORDER BY created_at DESC, id DESC
            LIMIT :fetchSize
            """)
        .bind("tenantId", tenantId)
        .bind("status", status)
        .bind("fetchSize", fetchSize)
        .map((row, metadata) -> mapOrderSummary(row))
        .all()
        .collectList();
}
~~~

### 10.2. Query trang tiếp theo

~~~java
private Mono<List<OrderSummary>> nextPage(
        String tenantId,
        String status,
        OrderCursor cursor,
        int fetchSize) {

    return databaseClient.sql("""
            SELECT id, status, created_at
            FROM orders
            WHERE tenant_id = :tenantId
              AND status = :status
              AND (
                  created_at < :lastCreatedAt
                  OR (
                      created_at = :lastCreatedAt
                      AND id < :lastId
                  )
              )
            ORDER BY created_at DESC, id DESC
            LIMIT :fetchSize
            """)
        .bind("tenantId", tenantId)
        .bind("status", status)
        .bind("lastCreatedAt", cursor.createdAt())
        .bind("lastId", cursor.id())
        .bind("fetchSize", fetchSize)
        .map((row, metadata) -> mapOrderSummary(row))
        .all()
        .collectList();
}
~~~

Cần điều chỉnh kiểu LocalDateTime/Instant theo kiểu cột và R2DBC driver. Không parse timestamp từ chuỗi client một cách tùy tiện.

### 10.3. Cursor phải được tạo từ hàng cuối cùng đã trả

Giả sử query lấy 21 hàng cho page size 20. Hàng thứ 21 chỉ xác nhận có trang tiếp theo.

Cursor tiếp theo phải dựa trên hàng thứ 20, tức hàng cuối trong content được gửi cho client. Nếu tạo cursor từ hàng thứ 21, trang tiếp theo sẽ bắt đầu sau hàng phụ và bỏ qua bản ghi đó.

Đây là lỗi phổ biến làm mất một hàng ở ranh giới trang.

## 11. Mã hóa, ký và kiểm tra cursor

Cursor là dữ liệu điều khiển query do client gửi lại. Không nên tin cursor chưa được kiểm tra.

Một cursor có thể chứa:
- Phiên bản định dạng.
- Sort key cuối cùng.
- Sort direction.
- Filter fingerprint.
- Thời điểm hết hạn.
- Snapshot/watermark nếu API có semantics đó.

Có thể serialize payload rồi ký HMAC để phát hiện sửa đổi. Nếu payload chứa thông tin nhạy cảm, dùng mã hóa thay vì chỉ Base64. Base64 không phải bảo mật.

### 11.1. Cursor phải gắn với filter

Nếu trang đầu lọc status = OPEN nhưng trang sau dùng lại cursor với status = CANCELLED, kết quả có thể không còn ý nghĩa.

Có thể lưu fingerprint của filter và sort trong cursor, sau đó so sánh với request tiếp theo. Nếu khác, trả lỗi cursor không hợp lệ hoặc yêu cầu client bắt đầu lại.

### 11.2. Cursor không thay thế authorization

Dù cursor đã ký, mọi request vẫn phải:
- Xác thực người dùng.
- Lấy tenant từ security context.
- Áp dụng quyền truy cập.
- Áp dụng filter dữ liệu.
- Kiểm tra cursor thuộc đúng loại query.

Không xem cursor như token cấp quyền truy cập vào dữ liệu.

### 11.3. Đặt giới hạn và thời hạn

Cursor cần có:
- Kích thước tối đa.
- Định dạng/version được hỗ trợ.
- Thời hạn nếu nghiệp vụ cần.
- Xử lý lỗi decode rõ ràng.
- Không chứa SQL tùy ý.
- Không chứa thông tin bí mật không cần thiết.

Một cursor quá lớn có thể trở thành request payload không cần thiết. Không cho client gửi trực tiếp câu predicate hoặc tên cột tùy ý.

## 12. Dữ liệu thay đổi trong lúc người dùng phân trang

Không có total count không có nghĩa dữ liệu bất biến. Trong lúc client đang xem trang đầu, request khác có thể insert, update hoặc delete hàng.

### 12.1. Offset có thể lặp hoặc bỏ qua hàng

Ví dụ ban đầu:

~~~text
Trang 1, size 3:
[100, 99, 98]

Trang 2 dự kiến:
[97, 96, 95]
~~~

Nếu một hàng mới được insert vào đầu danh sách trước khi client lấy trang 2, vị trí offset dịch chuyển. Client có thể nhận lại 98 hoặc bỏ qua một hàng khác tùy query và sort.

Nếu một hàng trước offset bị xóa, trang tiếp theo cũng có thể dịch chuyển theo hướng ngược lại.

### 12.2. Keyset ổn định hơn với insert ở phía trước cursor

Nếu sort key không thay đổi và cursor chỉ tiếp tục từ cặp giá trị cuối, việc insert hàng mới trước vị trí cursor thường không làm các hàng đã đi qua bị dịch chuyển như offset.

Tuy vậy, keyset không tạo snapshot tuyệt đối:
- Hàng bị xóa sẽ không còn xuất hiện.
- Hàng mới được chèn sau cursor có thể xuất hiện ở trang sau.
- Hàng có sort key thay đổi có thể di chuyển qua cursor.
- Filter membership thay đổi có thể làm hàng vào hoặc ra khỏi tập kết quả.

Hãy mô tả semantics của API: danh sách phản ánh dữ liệu mới nhất ở mỗi request hay một snapshot cố định.

### 12.3. Snapshot consistency cho export

Nếu nghiệp vụ yêu cầu export chính xác toàn bộ tập dữ liệu tại một thời điểm, không nên giả định nhiều request cursor độc lập tự động dùng chung snapshot database.

Có thể dùng:
- Một watermark/as-of timestamp có ý nghĩa với dữ liệu.
- Một bảng snapshot hoặc danh sách ID đã materialize.
- Một export job đọc theo transaction/snapshot được quản lý phù hợp.
- Một read model bất biến cho quá trình export.

Không giữ một transaction database mở trong nhiều phút chỉ để người dùng tải từng trang qua HTTP. Điều đó có thể giữ connection và snapshot lâu, gây áp lực lên pool và database.

## 13. Khi nào vẫn cần COUNT?

Không phải mọi API đều nên bỏ total. Một số giao diện hoặc nghiệp vụ thật sự cần số lượng chính xác:

- UI phải hiển thị "1–20 trên 3.450".
- Người dùng cần nhảy tới trang cuối.
- Báo cáo cần tổng số chính xác.
- Nghiệp vụ cần đối soát số lượng.
- Export cần xác nhận quy mô dữ liệu trước khi chạy.

Trong trường hợp đó, hãy xem count là một phần riêng của hợp đồng và đo chi phí.

Có thể cân nhắc:
- Count chỉ khi client yêu cầu.
- Count có filter/index phù hợp.
- Cache count nếu độ trễ cập nhật được chấp nhận.
- Trả count xấp xỉ nếu product chấp nhận rõ ràng.
- Chạy count bất đồng bộ cho báo cáo lớn.
- Dùng query khác để trả total theo read model đã tổng hợp.

Không trả một số xấp xỉ trong trường totalElements mà không công bố semantics. Client có thể coi đó là con số chính xác.

### 13.1. Count và dữ liệu trang có thể không cùng snapshot

Nếu count query và content query chạy riêng, dữ liệu có thể thay đổi giữa hai câu lệnh. Ví dụ count trả 100 nhưng trước khi query content chạy, một số hàng bị xóa.

Nếu cần count và content nhất quán chính xác, cần xem transaction isolation/snapshot semantics của database. Điều này có thể làm tăng chi phí và thời gian giữ transaction.

Nếu client chỉ cần biết còn trang tiếp theo, limit + 1 thường đơn giản hơn nhiều.

## 14. Thiết kế endpoint và trải nghiệm client

### 14.1. Endpoint offset

Ví dụ:

~~~http
GET /orders?status=OPEN&page=0&size=20
~~~

Response:

~~~json
{
  "items": [],
  "page": 0,
  "size": 20,
  "hasNext": true,
  "nextPage": 1
}
~~~

Client tiếp tục:

~~~http
GET /orders?status=OPEN&page=1&size=20
~~~

Server cần validate page và size ở mọi request. Không tin client giữ nguyên filter hoặc sort giữa các trang nếu contract yêu cầu cố định; có thể đưa query fingerprint vào token hoặc xác nhận lại tham số.

### 14.2. Endpoint cursor

Ví dụ:

~~~http
GET /orders?status=OPEN&limit=20
~~~

Response:

~~~json
{
  "items": [],
  "hasNext": true,
  "nextCursor": "eyJ2IjoxLCJrZXkiOi4uLn0.signature"
}
~~~

Client tiếp tục:

~~~http
GET /orders?status=OPEN&limit=20&cursor=eyJ2IjoxLCJrZXkiOi4uLn0.signature
~~~

Giá trị cursor trên chỉ minh họa. Không dùng cursor cố định hoặc cursor chưa được ký trong production.

### 14.3. Thay đổi filter phải bắt đầu lại

Khi người dùng đổi status, keyword, sort hoặc tenant context, client nên bỏ cursor cũ và bắt đầu từ trang đầu. Cursor gắn với query trước đó không nên được dùng cho filter mới.

Server cũng cần kiểm tra filter fingerprint để tránh trả dữ liệu theo một thứ tự không còn tương thích.

### 14.4. Hành vi khi trang cuối rỗng

Nếu client yêu cầu một trang sau khi dữ liệu đã bị xóa, server có thể trả:
- items rỗng.
- hasNext = false.
- nextCursor = null.

Đây là kết quả hợp lệ. Không cần phát lỗi 404 chỉ vì trang không có hàng, trừ khi API có một semantics khác được công bố.

## 15. Bảo vệ truy vấn phân trang

Phân trang không tự động làm query an toàn hoặc rẻ.

Cần:
- Giới hạn page size ở server.
- Giới hạn page depth nếu dùng offset.
- Allowlist sort field và direction.
- Bind mọi giá trị filter.
- Giới hạn số filter và số phần tử IN.
- Áp dụng tenant/security predicate.
- Đặt timeout query và acquire.
- Chỉ select cột cần thiết.
- Có index phù hợp.
- Theo dõi rows scanned và rows returned.

Một query LIMIT 20 vẫn có thể quét hàng triệu hàng nếu filter không có index. LIMIT giới hạn kết quả trả về, không bảo đảm giới hạn công việc database phải thực hiện.

Không nhận raw ORDER BY hoặc predicate từ client. Sort key của cursor phải được ánh xạ từ một tập lựa chọn cố định.

## 16. Kiểm thử kết quả phân trang không count

### 16.1. Kiểm tra trang đầy đủ có hasNext

Seed 6 hàng, yêu cầu size 5:
- Response chứa 5 hàng.
- hasNext = true.
- Hàng thứ 6 không xuất hiện trong content.
- next position được tạo từ hàng thứ 5.

### 16.2. Kiểm tra đúng bằng page size

Seed đúng 5 hàng, yêu cầu size 5:
- Response chứa 5 hàng.
- hasNext = false.
- nextCursor/nextPage là null hoặc bị bỏ theo contract.

Đây là test quan trọng vì nếu implementation dùng điều kiện rows.size() >= size thì sẽ báo sai hasNext.

### 16.3. Kiểm tra trang cuối ít hơn page size

Seed 7 hàng, yêu cầu size 5:
- Trang đầu có 5 hàng, hasNext = true.
- Trang sau có 2 hàng, hasNext = false.

### 16.4. Kiểm tra tập rỗng

Không có hàng phù hợp:
- items rỗng.
- hasNext = false.
- Không tạo cursor.

### 16.5. Kiểm tra thứ tự trùng sort key

Seed nhiều hàng có cùng created_at nhưng ID khác nhau. Xác nhận thứ tự ổn định và không lặp/bỏ sót khi đi qua ranh giới trang.

### 16.6. Kiểm tra count không được gọi

Nếu mục tiêu là bỏ count query, test integration hoặc instrumentation nên xác nhận request phân trang không phát sinh câu COUNT không cần thiết.

Không chỉ mock một repository method rồi kết luận database không chạy count nếu implementation thật có thể tự tạo query khác.

### 16.7. Kiểm tra concurrent insert/delete

Với offset:
- Insert hàng ở đầu giữa hai trang.
- Delete hàng trước offset.
- Ghi nhận hành vi lặp/bỏ qua theo semantics đã chọn.

Với keyset:
- Insert hàng trước cursor.
- Insert hàng sau cursor.
- Update sort key.
- Delete hàng ở ranh giới.
- Xác nhận behavior đúng với contract.

### 16.8. Kiểm tra cursor

- Cursor hợp lệ.
- Cursor bị sửa chữ ký.
- Cursor hết hạn.
- Cursor từ filter khác.
- Cursor có version format không hỗ trợ.
- Cursor có tenant/query scope không phù hợp.
- Cursor rỗng hoặc quá dài.

### 16.9. Kiểm tra giới hạn tài nguyên

Xác nhận:
- page size vượt max bị từ chối.
- Query chỉ lấy tối đa size + 1.
- Không collect toàn bộ bảng.
- Timeout được áp dụng.
- Không tạo connection leak khi client cancel.

## 17. Ví dụ test bằng StepVerifier

Giả sử service trả OffsetSlice:

~~~java
@Test
void shouldReturnHasNextWhenExtraRowExists() {
    StepVerifier.create(
            orderQueryService.search("tenant-a", "OPEN", 0, 2)
        )
        .assertNext(slice -> {
            assertThat(slice.items()).hasSize(2);
            assertThat(slice.hasNext()).isTrue();
            assertThat(slice.nextPage()).isEqualTo(1);
        })
        .verifyComplete();
}

@Test
void shouldNotReportNextWhenResultEqualsPageSize() {
    StepVerifier.create(
            orderQueryService.search("tenant-a", "OPEN", 0, 2)
        )
        .assertNext(slice -> {
            assertThat(slice.items()).hasSize(2);
            assertThat(slice.hasNext()).isFalse();
            assertThat(slice.nextPage()).isNull();
        })
        .verifyComplete();
}
~~~

Test thứ hai giả định database fixture có đúng hai hàng phù hợp. Cần reset/seed fixture rõ ràng để hai test không dùng cùng một trạng thái dữ liệu ngoài ý muốn.

Với cursor, test cần xác nhận cursor tiếp theo được tạo từ phần tử cuối đã trả, không phải hàng phụ N + 1.

## 18. Những lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Luôn chạy COUNT dù client không dùng total | Tăng database work và latency | Dùng limit + 1 để xác định hasNext |
| Lấy đúng N hàng rồi đặt hasNext = true khi đủ N | Trang cuối có đúng N hàng vẫn báo còn trang | Lấy N + 1 và kiểm tra rows.size() > N |
| Dùng rows.size() >= N để tính hasNext | Báo sai ở trang cuối có đúng N hàng | Chỉ true khi có hàng phụ thứ N + 1 |
| Đặt take(N + 1) nhưng query không có LIMIT | Database có thể vẫn làm nhiều công việc hơn cần thiết | Đặt limit tại database |
| collectList trên Flux không giới hạn | Tốn heap theo toàn bộ tập dữ liệu | Giới hạn query bằng N + 1 trước |
| ORDER BY không có khóa duy nhất | Trang có thể lặp hoặc bỏ hàng | Thêm tie-breaker duy nhất |
| Cursor dùng sort key khác ORDER BY | Có thể bỏ sót hoặc lặp hàng | Đồng bộ predicate, cursor và sort |
| Tạo cursor từ hàng N + 1 | Bỏ qua hàng phụ ở trang sau | Tạo cursor từ hàng N đã trả |
| Dùng offset sâu không giới hạn | Query chậm khi page tăng | Giới hạn offset hoặc dùng keyset |
| Dùng updated_at làm cursor mà không xét thay đổi | Hàng có thể di chuyển qua cursor | Ưu tiên sort key ổn định hoặc xác định semantics |
| Nghĩ keyset tạo snapshot | Vẫn có thể thấy insert/update/delete giữa các trang | Dùng watermark/snapshot/job nếu cần consistency |
| Cursor được xem như authorization | Có nguy cơ truy cập ngoài tenant | Kiểm tra auth ở mọi request |
| Cursor không gắn với filter | Trang sau có thể dùng sai điều kiện | Ký filter fingerprint và kiểm tra |
| Gửi totalElements giả | Client hiểu nhầm count chính xác | Bỏ trường total khỏi contract |
| Giả định reactive repository luôn trả Slice | Không tương thích API của phiên bản đang dùng | Kiểm tra support; tự tạo response DTO khi cần |
| Dùng một transaction dài cho toàn bộ quá trình người dùng bấm Next | Giữ connection và snapshot quá lâu | Mỗi request là query độc lập hoặc dùng snapshot/export job |
| Không giới hạn page size | Client có thể yêu cầu quá nhiều hàng | Validate và đặt max size ở server |

## 19. Quy trình thiết kế một API phân trang không count

1. Xác định client cần Next/Load more hay thật sự cần tổng số trang.
2. Nếu không cần total, loại totalElements và totalPages khỏi response.
3. Chọn offset khi cần nhảy trang và tập dữ liệu có giới hạn phù hợp.
4. Chọn keyset khi dữ liệu lớn hoặc client đi tuần tự qua nhiều trang.
5. Đặt page size mặc định và tối đa ở server.
6. Xác định thứ tự sort ổn định, kết thúc bằng khóa duy nhất.
7. Tạo query với LIMIT bằng page size + 1.
8. Thu thập tối đa N + 1 hàng và xác định hasNext.
9. Chỉ trả N hàng đầu.
10. Tạo nextPage hoặc nextCursor từ hàng cuối đã trả.
11. Với cursor, ký/kiểm tra cursor và gắn nó với filter/sort.
12. Áp dụng tenant authorization ở mọi trang.
13. Đặt index hỗ trợ filter và sort.
14. Kiểm thử đúng N, N + 1, ít hơn N, rỗng và sort key trùng.
15. Kiểm thử dữ liệu thay đổi giữa các lần request.
16. Theo dõi query duration, rows scanned, rows returned và p95/p99.
17. Chỉ thêm COUNT nếu product thực sự cần tổng chính xác.

## 20. Bài tập tự kiểm tra

### Bài 1: Tính hasNext

Client yêu cầu 10 hàng. Database trả về 10 hàng. Có thể kết luận còn trang tiếp theo không?

Gợi ý: Chưa thể. Cần lấy tối đa 11 hàng. Nếu chỉ có đúng 10 hàng thì hasNext = false.

### Bài 2: Hàng phụ

Page size là 20 và query trả 21 hàng. Hàng thứ 21 nên được xử lý thế nào?

Gợi ý: Chỉ dùng để đặt hasNext = true. Không đưa nó vào content và không tạo cursor từ hàng này.

### Bài 3: COUNT query

Một màn hình chỉ có nút Load more. Có cần totalElements và totalPages không?

Gợi ý: Không. Response chỉ cần items, hasNext và next position/cursor.

### Bài 4: collectList

Vì sao collectList phù hợp trong ví dụ limit + 1 nhưng nguy hiểm với findAll không giới hạn?

Gợi ý: Trường hợp đầu chỉ thu thập tối đa N + 1 hàng đã giới hạn ở database; trường hợp sau có thể gom toàn bộ bảng vào heap.

### Bài 5: Thứ tự ổn định

Query chỉ ORDER BY created_at nhưng nhiều hàng có cùng timestamp. Có thể xảy ra vấn đề gì?

Gợi ý: Thứ tự giữa các hàng đồng timestamp không được xác định; thêm khóa duy nhất như id làm tie-breaker.

### Bài 6: Offset và insert

Một hàng mới được chèn ở đầu danh sách sau khi client lấy trang 1 bằng offset. Trang 2 có thể bị ảnh hưởng ra sao?

Gợi ý: Vị trí offset dịch chuyển, có thể lặp hoặc bỏ qua hàng. Keyset giảm vấn đề dịch chuyển do insert trước cursor.

### Bài 7: Keyset cursor

Nếu sort là created_at DESC, id DESC thì cursor cần chứa thông tin nào?

Gợi ý: Giá trị created_at và id của hàng cuối cùng đã trả, cùng metadata cần thiết để xác định filter/sort tương ứng.

### Bài 8: Cursor tampering

Client sửa id trong cursor đã ký. Server nên làm gì?

Gợi ý: Xác minh chữ ký trước khi dùng cursor; từ chối cursor không hợp lệ.

### Bài 9: Snapshot

Keyset pagination có bảo đảm toàn bộ các trang là một snapshot dữ liệu tại cùng thời điểm không?

Gợi ý: Không. Cần watermark/snapshot hoặc export job nếu nghiệp vụ yêu cầu snapshot consistency.

### Bài 10: Quyết định Page hay Slice

Một báo cáo cần hiển thị chính xác "1–20 trên 10.532 kết quả". Nên bỏ count hoàn toàn không?

Gợi ý: Không. Count là yêu cầu sản phẩm. Hãy đo và thiết kế count query phù hợp, hoặc dùng số liệu tổng hợp/cache nếu contract cho phép.

## 21. Ghi nhớ

- Không phải API phân trang nào cũng cần tổng số bản ghi.
- Page thường cung cấp total count; Slice tập trung vào hasNext/hasPrevious; cursor page tiếp tục từ vị trí sort key.
- Với reactive R2DBC, hãy kiểm tra support Page/Slice theo phiên bản; có thể tự xây response DTO từ Flux/Mono.
- Kỹ thuật limit + 1 cho biết có trang tiếp theo mà không cần COUNT riêng.
- Query phải đặt LIMIT ở database bằng pageSize + 1.
- hasNext chỉ true khi số hàng nhận được lớn hơn pageSize.
- Chỉ trả pageSize hàng đầu; hàng phụ chỉ dùng làm dấu hiệu.
- collectList an toàn khi query đã giới hạn N + 1 và N có max rõ ràng.
- Offset dễ hiểu nhưng trang sâu có thể tốn kém và dễ bị ảnh hưởng khi dữ liệu thay đổi.
- Keyset phù hợp với tập dữ liệu lớn và điều hướng tuần tự.
- Sort phải ổn định và kết thúc bằng khóa duy nhất.
- Cursor phải khớp với ORDER BY, filter và sort direction; tạo từ hàng cuối đã trả.
- Cursor cần được kiểm tra tính toàn vẹn và không thay thế authorization.
- Keyset giảm dịch chuyển vị trí nhưng không tạo snapshot tuyệt đối.
- Nếu cần count chính xác, hãy xem count là một yêu cầu riêng và đo chi phí.
- Kiểm thử các trường hợp đúng N, N + 1, ít hơn N, rỗng, sort key trùng và dữ liệu thay đổi giữa các trang.
- Theo dõi query latency, rows scanned/returned và hiệu năng theo page depth.

Khi client chỉ cần biết có thể tải tiếp hay không, hãy để database trả tối đa pageSize + 1 hàng rồi suy ra hasNext. Thiết kế này loại bỏ công việc đếm tổng không cần thiết, giữ response đơn giản và phù hợp với reactive pipeline. Với dữ liệu lớn, kết hợp cursor/keyset pagination, sort ổn định, index phù hợp và kiểm tra cursor sẽ giúp việc tiếp tục qua nhiều trang có chi phí dễ dự đoán hơn.

