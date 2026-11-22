# Giới hạn kích thước truy vấn, số bản ghi và thời gian xử lý

## 1. Vì sao phải giới hạn tài nguyên khi truy cập dữ liệu?

Một API reactive có thể xử lý nhiều request đồng thời, nhưng điều đó không có nghĩa mỗi request nên được phép tạo truy vấn không giới hạn, đọc hàng triệu bản ghi hoặc giữ connection trong thời gian tùy ý.

Trong ứng dụng Spring WebFlux và Spring Data Relational R2DBC, một request có thể tiêu thụ nhiều loại tài nguyên:

- Bộ nhớ để nhận request body, tạo câu SQL và giữ kết quả.
- CPU để phân tích điều kiện tìm kiếm, sắp xếp, chuyển đổi và serialize dữ liệu.
- Connection từ R2DBC pool.
- Thời gian xử lý của database.
- Băng thông mạng để đọc dữ liệu và trả response.
- Worker và hàng đợi khi có tác vụ blocking hoặc xử lý đồng thời.
- Tài nguyên của các dịch vụ khác nếu request kéo theo side effect.

Nếu client có thể yêu cầu page size cực lớn, gửi danh sách ID không giới hạn, tạo filter phức tạp hoặc giữ request mở quá lâu, một số ít request cũng có thể làm cạn tài nguyên của ứng dụng và database.

Đây là một vấn đề bảo mật và độ sẵn sàng. Kẻ tấn công không nhất thiết phải gửi payload độc hại hay khai thác SQL injection. Chỉ cần gửi nhiều request hợp lệ nhưng quá nặng, hệ thống cũng có thể bị resource exhaustion hoặc denial of service.

Vì vậy, cần đặt giới hạn ở nhiều lớp:

1. Kích thước request và dữ liệu đầu vào.
2. Độ phức tạp của filter, sort và câu truy vấn.
3. Số bản ghi được đọc hoặc ghi trong một lần.
4. Kích thước response.
5. Thời gian chờ connection, thực thi SQL và transaction.
6. Số request hoặc tác vụ được chạy đồng thời.
7. Tần suất request theo người dùng, tenant hoặc API key.

Các giới hạn phải được áp dụng ở server. Không dựa vào giao diện client để giới hạn page size hoặc thời gian chờ, vì client có thể bị sửa hoặc bỏ qua hoàn toàn.

## 2. Bản đồ các giới hạn cần có

| Tài nguyên | Rủi ro khi không giới hạn | Cơ chế bảo vệ |
|---|---|---|
| Request body | Tốn bộ nhớ khi decode hoặc aggregate | Giới hạn kích thước body và multipart |
| Search keyword | Filter quá dài, tìm kiếm tốn CPU | Giới hạn độ dài, chuẩn hóa và kiểm tra định dạng |
| Số điều kiện filter | Query phức tạp, khó tối ưu | Allowlist filter và giới hạn số điều kiện |
| Sort field | Lạm dụng cột không có index hoặc SQL injection | Allowlist tên cột và hướng sort |
| Danh sách ID | Quá nhiều bind parameter và SQL lớn | Giới hạn số phần tử, chia batch |
| Page size | Đọc và serialize quá nhiều hàng | Max page size ở server |
| Offset | Query sâu có thể phải bỏ qua nhiều hàng | Keyset/cursor pagination |
| Batch ghi | Transaction và lock kéo dài | Giới hạn batch size |
| Query duration | Giữ connection và database worker lâu | Statement/query timeout theo driver/database |
| Acquire wait | Request chờ pool quá lâu | Pool acquire timeout và pending limit |
| Transaction duration | Giữ connection/lock lâu | Transaction ngắn và timeout |
| Concurrency | Quá nhiều query cùng lúc | Giới hạn concurrency, bulkhead và rate limit |
| Response size | Tốn heap và băng thông | Giới hạn số hàng, field và kích thước dữ liệu |

Không có một giới hạn duy nhất bảo vệ được toàn bộ hệ thống. Cần kết hợp các lớp để request nặng bị chặn trước khi chiếm nhiều tài nguyên.

## 3. Giới hạn kích thước request body

### 3.1. Giới hạn trước khi parse dữ liệu

WebFlux có thể nhận request body dưới dạng stream. Tuy nhiên, khi framework hoặc code cần gom dữ liệu vào bộ nhớ để deserialize một object, request body lớn có thể gây áp lực heap.

Với Spring Boot, có thể cấu hình giới hạn bộ nhớ của codec:

~~~yaml
spring:
  codec:
    max-in-memory-size: 1MB
~~~

Giá trị trên chỉ là ví dụ. Hãy chọn theo API contract, kích thước payload hợp lệ và cách ứng dụng decode body.

Giới hạn codec không phải lúc nào cũng đồng nghĩa với một giới hạn tổng request body cho mọi kiểu streaming. Với upload file hoặc multipart, cần cấu hình giới hạn riêng cho kích thước request, từng part, số part và nơi lưu tạm theo server/container và phiên bản Spring Boot.

### 3.2. Không aggregate stream lớn một cách tùy tiện

Không nên dùng **collectList()** hoặc gom toàn bộ DataBuffer vào bộ nhớ nếu payload có thể lớn.

Ví dụ, nếu API nhận một danh sách rất dài các ID để cập nhật, việc deserialize toàn bộ thành List có thể tạo một object lớn trước cả khi truy vấn database bắt đầu.

Hãy cân nhắc:
- Giới hạn số phần tử trong request.
- Nhận dữ liệu theo từng batch nhỏ.
- Dùng streaming khi định dạng và nghiệp vụ cho phép.
- Đưa tác vụ import lớn vào job bất đồng bộ thay vì giữ một HTTP request mở.
- Kiểm tra kích thước file trước khi parse nội dung.

### 3.3. Giới hạn số trường và cấu trúc lồng nhau

Payload nhỏ theo byte vẫn có thể gây tốn CPU nếu chứa cấu trúc lồng sâu hoặc số lượng phần tử quá lớn.

API nên giới hạn:
- Độ sâu object lồng nhau nếu dữ liệu có cấu trúc cây.
- Số phần tử trong collection.
- Số filter và sort field.
- Độ dài chuỗi.
- Số trường được phép cập nhật.
- Số phần tử trong mỗi batch.

Nếu request là một DTO cố định, hãy dùng Bean Validation để kiểm tra các trường ngay ở biên HTTP.

## 4. Validate kích thước và phạm vi tham số tìm kiếm

Ví dụ DTO tìm kiếm đơn hàng:

~~~java
public record OrderSearchRequest(
    @Size(max = 80)
    String keyword,

    @Min(0)
    @Max(1000)
    int page,

    @Min(1)
    @Max(100)
    int size,

    @NotNull
    OrderSortField sortBy,

    @NotNull
    Sort.Direction direction
) {
}
~~~

Enum giới hạn cột được phép sắp xếp:

~~~java
public enum OrderSortField {
    CREATED_AT,
    ID,
    STATUS
}
~~~

Controller kích hoạt validation:

~~~java
@PostMapping("/search")
public Flux<OrderSummary> search(
        @Valid @RequestBody OrderSearchRequest request) {

    return orderService.search(request);
}
~~~

Tùy phiên bản Spring Boot và WebFlux, cần có validation starter và cấu hình method/bean validation tương ứng. Hãy xác nhận lỗi validation được ánh xạ thành response 400 theo API contract.

### 4.1. Không chỉ kiểm tra ở client

Client có thể gửi size=1000000 dù giao diện chỉ hiển thị 20, 50 hoặc 100. Server phải tự áp dụng giới hạn.

Có thể từ chối request vượt giới hạn với lỗi 400 hoặc 422. Một số API chọn clamp page size về giá trị tối đa, nhưng phải công bố rõ hành vi. Từ chối thường giúp client nhận ra lỗi sử dụng API thay vì âm thầm nhận ít dữ liệu hơn dự kiến.

### 4.2. Không dùng chuỗi tùy ý làm tên cột hoặc hướng sort

Bind parameter chỉ bảo vệ giá trị. Nó không thể thay thế tên cột hoặc từ khóa SQL.

Không viết:

~~~java
String sql = "SELECT * FROM orders ORDER BY " + request.sortBy();
~~~

Nếu sortBy đến từ client, nó có thể làm thay đổi cấu trúc câu SQL.

Hãy ánh xạ enum sang identifier đã được định nghĩa trong code:

~~~java
private String sortColumn(OrderSortField field) {
    return switch (field) {
        case CREATED_AT -> "created_at";
        case ID -> "id";
        case STATUS -> "status";
    };
}
~~~

Hướng sort cũng phải được giới hạn vào ASC hoặc DESC. Không nối một chuỗi bất kỳ từ request vào SQL.

Với R2dbcEntityTemplate, có thể tạo Sort từ enum đã được kiểm soát thay vì truyền tên cột tùy ý.

### 4.3. Giới hạn số filter

Một API tìm kiếm có thể cho phép nhiều filter. Nếu không giới hạn số filter hoặc độ phức tạp của biểu thức AND/OR, server có thể tạo query rất lớn và khó tối ưu.

Nên quy định:
- Số filter tối đa.
- Các field được lọc.
- Các operator được phép cho từng field.
- Số phần tử tối đa của mỗi điều kiện IN.
- Không cho client gửi biểu thức SQL hoặc tiêu chí query tùy ý.
- Giới hạn độ dài keyword và wildcard pattern.

Các quy tắc tìm kiếm cần được biểu diễn bằng DTO có cấu trúc, sau đó service chuyển thành Criteria/SQL được kiểm soát.

## 5. Giới hạn độ dài câu SQL và số bind parameter

### 5.1. Không nhận raw SQL từ client

Một API nghiệp vụ không nên cho client gửi câu SQL để server thực thi. Dù có giới hạn số ký tự, raw SQL vẫn mở ra khả năng truy cập dữ liệu ngoài phạm vi, tạo query tốn tài nguyên hoặc thực hiện thao tác không được phép.

Hãy nhận các tham số nghiệp vụ như status, khoảng ngày, keyword, page size và sort enum. Server tự tạo câu SQL từ các thành phần đã allowlist.

### 5.2. Bind parameter cho giá trị

Ví dụ an toàn hơn:

~~~java
return databaseClient.sql("""
        SELECT id, status, created_at
        FROM orders
        WHERE status = :status
          AND created_at >= :from
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        """)
    .bind("status", status)
    .bind("from", from)
    .bind("limit", limit)
    .map((row, metadata) -> new OrderSummary(
        row.get("id", Long.class),
        row.get("status", String.class),
        row.get("created_at", LocalDateTime.class)
    ))
    .all();
~~~

Bind parameter giúp tách giá trị dữ liệu khỏi cấu trúc SQL. Nó không làm cho tên bảng, tên cột, toán tử hoặc từ khóa ORDER BY trở thành giá trị có thể bind.

### 5.3. Giới hạn danh sách IN

Một request gửi hàng chục nghìn ID có thể tạo ra câu SQL với số lượng bind parameter rất lớn.

Ví dụ:

~~~sql
SELECT id, status
FROM orders
WHERE id IN (:id1, :id2, :id3, ...);
~~~

Số bind parameter tối đa phụ thuộc database và driver. Ngay cả khi hệ thống cho phép nhiều parameter, một danh sách lớn vẫn có thể làm tăng kích thước SQL, thời gian parse và chi phí lập kế hoạch.

Cách bảo vệ:

- Giới hạn số ID mỗi request.
- Từ chối danh sách rỗng hoặc quá lớn theo hợp đồng API.
- Chia batch có kích thước cố định cho tác vụ nội bộ.
- Dùng array/table-valued parameter hoặc temporary table nếu database hỗ trợ và nhu cầu thực sự cần danh sách lớn.
- Không tạo hàng nghìn placeholder chỉ vì client gửi nhiều phần tử.

Ví dụ kiểm tra:

~~~java
private static final int MAX_IDS_PER_REQUEST = 500;

public Flux<Order> findByIds(List<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return Flux.empty();
    }

    if (ids.size() > MAX_IDS_PER_REQUEST) {
        return Flux.error(
            new TooManyIdsException(MAX_IDS_PER_REQUEST)
        );
    }

    return orderRepository.findAllById(ids);
}
~~~

Giá trị 500 chỉ là ví dụ. Hãy chọn theo giới hạn database, kích thước request và hiệu năng thực tế.

### 5.4. Chia batch không đồng nghĩa với một transaction vô hạn

Nếu cần xử lý 50.000 ID, chia thành nhiều batch có thể giảm kích thước mỗi query. Tuy nhiên, không nên mặc định giữ một transaction duy nhất cho toàn bộ 50.000 phần tử.

Một transaction lớn có thể:
- Giữ connection lâu.
- Giữ lock lâu.
- Tạo lượng undo/WAL lớn.
- Làm rollback tốn kém.
- Làm tăng nguy cơ timeout.

Hãy quyết định batch có cần atomic toàn bộ hay có thể xử lý từng batch độc lập với checkpoint và khả năng resume. Đây là quyết định nghiệp vụ, không chỉ là tối ưu kỹ thuật.

## 6. Giới hạn số bản ghi trả về

### 6.1. Không cho truy vấn không giới hạn ở endpoint tìm kiếm

Một endpoint tìm kiếm nên có page size mặc định và page size tối đa.

Ví dụ:

~~~java
private static final int DEFAULT_PAGE_SIZE = 20;
private static final int MAX_PAGE_SIZE = 100;

private int normalizePageSize(Integer requestedSize) {
    if (requestedSize == null) {
        return DEFAULT_PAGE_SIZE;
    }

    if (requestedSize < 1 || requestedSize > MAX_PAGE_SIZE) {
        throw new InvalidPageSizeException(MAX_PAGE_SIZE);
    }

    return requestedSize;
}
~~~

Không dùng page size trực tiếp từ request mà không validate. Giá trị âm, bằng 0 hoặc quá lớn phải được xử lý theo API contract.

### 6.2. Đặt LIMIT ở database

Giới hạn số bản ghi nên được thực thi ngay trong query, không chỉ gọi take() ở phía ứng dụng sau khi database đã đọc toàn bộ dữ liệu.

Ví dụ DatabaseClient:

~~~java
return databaseClient.sql("""
        SELECT id, status, created_at
        FROM orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        OFFSET :offset
        """)
    .bind("status", status)
    .bind("limit", pageSize)
    .bind("offset", offset)
    .map((row, metadata) -> mapOrder(row))
    .all();
~~~

Cú pháp LIMIT/OFFSET có thể khác giữa các hệ quản trị. Hãy dùng cú pháp được database và driver mục tiêu hỗ trợ.

Với R2dbcEntityTemplate, có thể đặt giới hạn trong Query:

~~~java
Query query = Query.query(
        Criteria.where("status").is(status)
    )
    .limit(pageSize)
    .offset(offset);

return template.select(query, Order.class).all();
~~~

Tên API có thể khác theo phiên bản Spring Data Relational. Hãy đối chiếu signature trong phiên bản dự án.

### 6.3. Không tải tất cả rồi mới giới hạn

Không phù hợp:

~~~java
return orderRepository.findAll()
    .collectList()
    .map(all -> all.stream()
        .limit(100)
        .toList()
    );
~~~

Database có thể đã gửi toàn bộ hàng và ứng dụng đã gom chúng vào bộ nhớ trước khi limit được áp dụng.

Hãy giới hạn query ở database, sau đó mới xử lý số hàng đã giới hạn.

### 6.4. Giới hạn cả số bản ghi và kích thước từng bản ghi

Một query trả 100 hàng vẫn có thể rất nặng nếu mỗi hàng chứa một cột TEXT/BLOB lớn.

Hãy cân nhắc:
- Chỉ SELECT các cột cần cho response.
- Không trả file/blob lớn trong endpoint danh sách.
- Tách nội dung lớn thành endpoint tải riêng có authorization.
- Giới hạn độ dài field do người dùng nhập.
- Giới hạn kích thước JSON response nếu API có payload lớn.

Số hàng không phải chỉ số duy nhất phản ánh chi phí response.

## 7. Pagination: offset và keyset

### 7.1. Offset pagination

Offset pagination phù hợp với các danh sách nhỏ hoặc khi client cần nhảy tới một trang cụ thể:

~~~sql
SELECT id, status, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT :pageSize
OFFSET :offset;
~~~

Cần giới hạn page và pageSize. Tính offset bằng số nguyên đủ lớn và kiểm tra tràn số trước khi bind:

~~~java
long offset = Math.multiplyExact((long) page, pageSize);
~~~

Nếu API cho phép page quá lớn, database có thể phải đọc/bỏ qua nhiều hàng trước khi trả trang cần thiết. Query ở offset sâu thường tốn kém hơn.

### 7.2. Sort phải ổn định

Pagination cần một thứ tự xác định. Nếu chỉ sort theo created_at và nhiều hàng có cùng timestamp, các trang có thể lặp hoặc bỏ sót hàng khi dữ liệu thay đổi.

Thêm một khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

Sort field và direction vẫn phải nằm trong allowlist.

### 7.3. Keyset pagination

Với tập dữ liệu lớn hoặc trang tiếp theo liên tục, keyset pagination thường hiệu quả hơn offset sâu.

Ví dụ lấy trang đầu:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Trang tiếp theo dùng cặp giá trị cuối trang trước:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE status = :status
  AND (
      created_at < :lastCreatedAt
      OR (
          created_at = :lastCreatedAt
          AND id < :lastId
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

Cursor cần chứa các giá trị sort cuối cùng và có thể được ký hoặc mã hóa nếu không muốn client tự sửa. Dù cursor được ký, service vẫn phải kiểm tra page size, filter và quyền truy cập.

Keyset pagination không tự tạo snapshot nhất quán cho mọi thay đổi dữ liệu. Nó giúp tiếp tục từ vị trí cuối cùng và tránh chi phí offset sâu; semantics khi dữ liệu thay đổi vẫn cần được xác định.

### 7.4. Cursor không phải quyền truy cập

Không coi việc client có cursor là bằng chứng client được phép đọc các hàng tiếp theo. Mọi query trang sau vẫn phải áp dụng tenant/user authorization và filter dữ liệu như trang đầu.

Nếu cursor chứa ID hoặc timestamp nhạy cảm, tránh để lộ thông tin không cần thiết. Có thể encode/sign cursor và đặt thời hạn nếu phù hợp với API.

## 8. Giới hạn truy vấn đếm và truy vấn tổng hợp

### 8.1. COUNT(*) có thể tốn kém

Một API trả total count cho mọi lần tìm kiếm có thể buộc database xử lý một tập dữ liệu lớn chỉ để tính tổng.

Với bảng lớn và filter phức tạp, COUNT(*) có thể tốn nhiều I/O hoặc CPU hơn phần query lấy trang.

Cân nhắc:
- Chỉ trả dữ liệu trang tiếp theo có tồn tại hay không.
- Giới hạn phạm vi ngày hoặc tenant.
- Cache kết quả đếm nếu semantics cho phép.
- Dùng thống kê xấp xỉ nếu nghiệp vụ chấp nhận.
- Chỉ thực hiện count khi client thực sự cần.
- Đặt timeout và theo dõi riêng query tổng hợp.

### 8.2. Giới hạn GROUP BY và khoảng thời gian

Query báo cáo có thể tạo kết quả nhỏ nhưng phải quét dữ liệu rất lớn. Giới hạn số hàng trả về không giới hạn được chi phí xử lý bên trong database.

Với báo cáo, hãy giới hạn:
- Khoảng thời gian tối đa.
- Số nhóm hoặc chiều phân nhóm.
- Số trường sort/group.
- Các filter được phép.
- Độ sâu truy vấn tổng hợp.
- Thời gian thực thi database.

Tác vụ báo cáo lớn nên chạy bất đồng bộ, lưu kết quả hoặc sử dụng read model chuyên biệt thay vì chiếm request và connection pool lâu.

## 9. Giới hạn số bản ghi ghi và batch size

### 9.1. Bulk insert/update

API bulk write cần giới hạn số phần tử mỗi request. Một request có thể chứa 100.000 item dù mỗi item rất nhỏ.

Hãy quy định:
- Số phần tử tối đa.
- Kích thước batch.
- Số bind parameter mỗi statement.
- Tổng thời gian cho một batch.
- Số batch chạy đồng thời.
- Cách tiếp tục sau lỗi giữa các batch.

Ví dụ chia danh sách thành batch:

~~~java
Flux.fromIterable(items)
    .buffer(200)
    .concatMap(batch -> saveBatch(batch));
~~~

concatMap xử lý từng batch tuần tự, giúp giới hạn số batch đồng thời. Con số 200 chỉ là ví dụ; cần dựa trên giới hạn parameter, kích thước row và database.

### 9.2. Chọn tính nguyên tử phù hợp

Có hai kiểu nghiệp vụ khác nhau:

- Toàn bộ import phải thành công hoặc thất bại: cần transaction lớn hoặc chiến lược staging/swap phù hợp, nhưng phải đánh giá lock và log.
- Mỗi batch có thể hoàn tất độc lập: dùng transaction ngắn cho từng batch, ghi checkpoint và hỗ trợ resume.

Không tự chia một giao dịch cần atomic thành nhiều transaction mà không có quy tắc phục hồi. Ngược lại, cũng không gom hàng chục nghìn thao tác vào một transaction nếu nghiệp vụ không yêu cầu.

### 9.3. Giới hạn concurrency của batch

Không chạy hàng trăm batch cùng lúc chỉ vì API reactive cho phép:

~~~java
Flux.fromIterable(batches)
    .flatMap(this::saveBatch, 4);
~~~

Tham số 4 giới hạn số batch được subscribe đồng thời. Hãy chọn dựa trên pool size, database capacity, lock contention và mức tải của các request khác.

Nếu mọi batch dùng cùng transaction connection, chạy song song có thể không phù hợp với driver. Khi cần transaction chung, ưu tiên trình tự rõ ràng và xác nhận connection semantics.

## 10. Giới hạn thời gian ở từng lớp

Một request truy cập database đi qua nhiều giai đoạn. Mỗi giai đoạn có loại timeout riêng.

| Lớp | Timeout bảo vệ điều gì? |
|---|---|
| Gateway/client | Thời gian tổng client chờ response |
| Web server/request | Thời gian request được phép tồn tại |
| Rate limiter/bulkhead | Thời gian hoặc số lượng chờ trước khi được xử lý |
| R2DBC pool acquire | Thời gian chờ lấy connection |
| Connection creation | Thời gian tạo connection mới |
| SQL statement/database | Thời gian database được phép thực thi query |
| Transaction | Thời gian transaction được phép tồn tại |
| Downstream client | Thời gian chờ dịch vụ bên ngoài |
| Reactor timeout | Deadline của publisher ở vị trí được áp dụng |

Không có một timeout chung thay thế tất cả. Nếu acquire timeout là 3 giây và client timeout là 2 giây, request có thể bị client hủy trước khi pool báo timeout. Nếu transaction timeout quá dài, connection vẫn có thể bị giữ sau khi API đã trở nên không hữu ích.

### 10.1. Acquire timeout

R2DBC Pool có thể giới hạn thời gian chờ connection:

~~~java
ConnectionPoolConfiguration configuration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .maxSize(20)
        .maxPendingAcquire(100)
        .maxAcquireTime(Duration.ofSeconds(2))
        .build();
~~~

API builder và giá trị mặc định phụ thuộc phiên bản R2DBC Pool. Hãy kiểm tra cấu hình thực tế của ứng dụng.

Acquire timeout bảo vệ thời gian chờ pool. Nó không giới hạn thời gian câu SQL sau khi connection đã được cấp.

### 10.2. Query hoặc statement timeout

Database và driver có thể cung cấp cách giới hạn thời gian thực thi SQL. Cơ chế này khác nhau theo hệ quản trị và phiên bản driver.

Ví dụ PostgreSQL có thể dùng statement_timeout ở phạm vi session hoặc transaction, chẳng hạn SET LOCAL statement_timeout trong transaction. Cần cấu hình đúng connection/transaction scope và tránh để session state rò rỉ sang request khác khi dùng pool.

Không giả định một thuộc tính R2DBC chung hoạt động giống nhau trên mọi driver. Hãy kiểm tra driver và database mục tiêu, rồi xác nhận query thực sự bị dừng khi hết thời gian.

### 10.3. Transaction timeout

Có thể đặt timeout ở service transaction:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    timeout = 5
)
public Mono<Order> confirm(Long orderId) {
    return performConfirmation(orderId);
}
~~~

Giá trị được tính bằng giây trong cấu hình annotation Spring. Khả năng thực thi timeout cụ thể phụ thuộc transaction manager, driver và resource.

Transaction timeout không phải query timeout. Một transaction có thể chứa nhiều thao tác và khoảng chờ; cần đặt cả giới hạn ở lớp phù hợp.

### 10.4. Reactor timeout

Có thể giới hạn thời gian của một publisher:

~~~java
public Mono<OrderSummary> loadSummary(Long orderId) {
    return orderRepository.findById(orderId)
        .map(OrderSummary::from)
        .timeout(Duration.ofSeconds(3));
}
~~~

timeout phát lỗi khi publisher không phát tín hiệu trong khoảng thời gian quy định. Cancellation được gửi tới upstream, nhưng việc database statement có dừng ngay hay không phụ thuộc driver và database.

Không coi Reactor timeout là bằng chứng chắc chắn query đã bị hủy ở server. Với query đắt tiền, cần thêm statement timeout phía database và quan sát query/session sau timeout.

### 10.5. Dùng deadline tổng thể

Giả sử API có deadline 4 giây. Ngân sách có thể được chia thành:

~~~text
Tổng deadline API: 4 giây
  |
  +-- chờ connection: tối đa 0.5 giây
  |
  +-- query và transaction: khoảng 2 giây
  |
  +-- xử lý/serialize response: khoảng 0.5 giây
  |
  +-- phần dự phòng network và scheduling: khoảng 1 giây
~~~

Đây chỉ là ví dụ phân bổ. Timeout từng lớp cần tương thích với deadline tổng thể. Nếu mỗi bước có timeout 10 giây, request có thể tồn tại lâu hơn mức client hoặc gateway chấp nhận.

## 11. Timeout, cancellation và tài nguyên được giải phóng

Khi Reactor timeout hoặc client hủy request, cancellation được truyền ngược theo reactive chain. Tuy nhiên, cancellation không phải lúc nào cũng dừng ngay tác vụ bên dưới.

Cần phân biệt:

- Publisher đã bị cancel.
- Driver đã hủy statement.
- Database server đã dừng query.
- Transaction đã rollback.
- Connection đã được release về pool.

Các sự kiện này có thể không xảy ra đồng thời. Một thư viện blocking hoặc driver không hỗ trợ cancellation tốt có thể tiếp tục giữ tài nguyên sau khi downstream không còn quan tâm.

Để bảo vệ hệ thống:
- Cấu hình timeout tại client/driver/database khi có hỗ trợ.
- Dùng transaction ngắn.
- Không gọi blocking trên event-loop.
- Đảm bảo connection cleanup ở complete, error và cancel.
- Theo dõi acquired sau timeout.
- Tránh retry ngay một side effect có kết quả không chắc chắn.

Nếu timeout xảy ra sau khi database đã commit nhưng trước khi client nhận response, client retry có thể tạo thao tác trùng. Với API ghi, hãy dùng idempotency key khi nghiệp vụ yêu cầu.

## 12. Giới hạn concurrency và rate

### 12.1. Concurrency trong Reactor

flatMap cho phép giới hạn số publisher con đang hoạt động:

~~~java
return Flux.fromIterable(orderIds)
    .flatMap(
        id -> orderRepository.findById(id),
        8
    );
~~~

Con số 8 là giới hạn concurrency trong ví dụ. Nó không phải giới hạn toàn hệ thống: mỗi request có thể tạo một pipeline như vậy, nên tổng concurrency còn phụ thuộc số request đồng thời.

Nếu mỗi request có concurrency 8 và có 100 request đồng thời, workload có thể lên tới khoảng 800 inner operations.

### 12.2. Rate limit theo người dùng hoặc tenant

Một client có thể gửi nhiều request nhỏ nhưng tổng thể tạo tải lớn. Cần giới hạn tần suất theo:
- User đã xác thực.
- Tenant.
- API key/client.
- Endpoint hoặc nhóm thao tác.
- IP ở các trường hợp phù hợp, nhưng không dùng IP làm danh tính duy nhất.

Rate limit có thể đặt ở API gateway hoặc tầng ứng dụng. Nếu dùng distributed rate limiter, hãy bảo đảm các instance chia sẻ trạng thái theo cách phù hợp.

### 12.3. Bulkhead

Bulkhead giới hạn số tác vụ có thể đồng thời tiêu thụ một nhóm tài nguyên. Ví dụ, tác vụ báo cáo nặng có thể có giới hạn concurrency riêng để không chiếm hết connection của luồng ghi đơn hàng.

Có thể tách pool, scheduler hoặc semaphore cho workload khác nhau, nhưng phải tính tổng connection và tài nguyên database. Tạo nhiều pool không làm tăng capacity của database.

### 12.4. Backpressure không thay thế mọi giới hạn

Reactive Streams backpressure giúp consumer điều khiển tốc độ phát dữ liệu trong một pipeline. Nó không tự giới hạn:
- Kích thước request body đã được aggregate.
- Số request HTTP đồng thời.
- Số connection pool.
- Số phần tử client gửi trong một JSON array.
- Độ phức tạp SQL.
- Thời gian query.
- Số request theo tenant.

Cần giới hạn riêng ở từng biên tài nguyên.

## 13. Thiết kế API tìm kiếm có giới hạn

Ví dụ service nhận DTO đã validate:

~~~java
public Flux<OrderSummary> search(OrderSearchRequest request) {
    int limit = normalizePageSize(request.size());
    long offset = Math.multiplyExact((long) request.page(), limit);

    String column = sortColumn(request.sortBy());
    String direction = request.direction() == Sort.Direction.ASC
        ? "ASC"
        : "DESC";

    String sql = """
        SELECT id, status, created_at
        FROM orders
        WHERE status = :status
        ORDER BY %s %s, id DESC
        LIMIT :limit
        OFFSET :offset
        """.formatted(column, direction);

    return databaseClient.sql(sql)
        .bind("status", request.status())
        .bind("limit", limit)
        .bind("offset", offset)
        .map((row, metadata) -> mapSummary(row))
        .all()
        .timeout(Duration.ofSeconds(2));
}
~~~

Trong ví dụ:

- Status được bind như giá trị.
- Sort field được ánh xạ từ enum allowlist.
- Direction chỉ nhận ASC hoặc DESC.
- Page size được validate và giới hạn.
- Offset được tính bằng long để giảm nguy cơ tràn số.
- SQL có LIMIT.
- Publisher có timeout.

Timeout 2 giây chỉ là ví dụ và cần được đồng bộ với acquire timeout, database statement timeout, transaction deadline và HTTP deadline.

Nếu API hỗ trợ nhiều filter, hãy xây câu query từ các predicate đã được kiểm soát. Không nối raw fragment từ client vào SQL.

## 14. Giới hạn response và xử lý kết quả

### 14.1. Trả DTO nhỏ thay vì entity đầy đủ

Endpoint danh sách thường chỉ cần một số trường. Không cần trả toàn bộ entity với blob, metadata lớn hoặc quan hệ không sử dụng.

Ví dụ:

~~~java
public record OrderSummary(
    Long id,
    String status,
    Instant createdAt
) {
}
~~~

Chỉ SELECT các cột cần thiết giúp giảm:
- Dữ liệu database gửi qua network.
- Chi phí mapping.
- Bộ nhớ trong ứng dụng.
- Kích thước JSON response.
- Thông tin nhạy cảm có thể vô tình bị lộ.

### 14.2. Không collectList trên tập dữ liệu không giới hạn

collectList gom toàn bộ phần tử phát ra vào một List. Nó phù hợp khi số phần tử đã được giới hạn rõ ràng, nhưng nguy hiểm với một Flux không có giới hạn.

Không dùng:

~~~java
return repository.findAll()
    .collectList()
    .map(this::buildResponse);
~~~

nếu findAll có thể trả hàng trăm nghìn bản ghi.

Hãy:
- Đặt LIMIT ở query.
- Trả Flux khi API có thể streaming.
- Phân trang.
- Dùng export job bất đồng bộ cho dữ liệu rất lớn.
- Giới hạn tổng bytes nếu response có field lớn.

### 14.3. Streaming cũng cần giới hạn

Streaming không có nghĩa tài nguyên miễn phí. Một stream kéo dài có thể giữ connection, request context và network resource lâu.

Đặt:
- Giới hạn số hàng tối đa cho một stream.
- Deadline hoặc thời gian sống tối đa.
- Giới hạn tốc độ và concurrency.
- Chính sách hủy và cleanup.
- Cơ chế resume/cursor nếu client cần tiếp tục.

Với export lớn, có thể tạo file theo job, lưu kết quả và cho client tải xuống theo quyền truy cập thay vì giữ database connection trong toàn bộ thời gian client tải file.

## 15. Giới hạn query theo quyền truy cập và tenant

Giới hạn số bản ghi không thay thế authorization.

Một request có LIMIT 20 vẫn có thể đọc dữ liệu của tenant khác nếu thiếu điều kiện phân vùng.

Mọi query cần áp dụng phạm vi quyền phù hợp:
- Tenant ID lấy từ security context đã xác thực, không tin tenant ID do client tự khai báo.
- User chỉ đọc tài nguyên được cấp quyền.
- Filter và sort không cho phép truy cập cột nội bộ ngoài phạm vi.
- Cursor không được coi là bằng chứng authorization.
- Count query cũng phải có cùng điều kiện tenant và quyền như query lấy dữ liệu.

Ví dụ:

~~~sql
SELECT id, status, created_at
FROM orders
WHERE tenant_id = :authenticatedTenantId
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT :limit;
~~~

authenticatedTenantId phải lấy từ principal/security context đã xác thực. Không chỉ bind giá trị tenantId trực tiếp từ request body mà không kiểm tra quyền.

## 16. Quan sát và cảnh báo các giới hạn

Một hệ thống có giới hạn tốt vẫn cần metrics để biết giới hạn có phù hợp không.

Các chỉ số nên theo dõi:

| Metric/measurement | Điều cần biết |
|---|---|
| Request body rejected | Có bao nhiêu request vượt kích thước |
| Validation failure | Client gửi page size/filter sai |
| Query duration | Query có vượt ngân sách thời gian |
| Rows returned | Một request đọc bao nhiêu hàng |
| Response bytes | Response có quá lớn |
| Acquire latency/timeout | Request có phải chờ connection |
| Pool acquired/idle/pending | Pool còn capacity hay bão hòa |
| Transaction duration | Transaction có giữ connection quá lâu |
| Rate limit rejected | Client/tenant nào vượt quota |
| Batch size and duration | Batch có quá lớn hoặc quá chậm |
| Cancellation/timeout count | Request bị hủy hoặc hết deadline |

Không đưa ID người dùng, email, SQL parameter hoặc cursor vào metric label nếu điều đó tạo cardinality cao hoặc lộ dữ liệu. Dùng trace/log có kiểm soát và masking khi cần điều tra từng request.

### 16.1. Ghi nhận lý do bị từ chối

Nên phân biệt các loại lỗi:
- Request body quá lớn.
- Page size vượt giới hạn.
- Quá nhiều ID/filter.
- Acquire timeout.
- Query timeout.
- Transaction timeout.
- Rate limit.
- Client cancellation.

Nếu tất cả đều trả một lỗi chung database error, vận hành sẽ khó xác định giới hạn nào đang bị chạm.

Không trả SQL, tên bảng nội bộ, stack trace hoặc thông tin connection trong response công khai. Ghi chi tiết ở log nội bộ với dữ liệu nhạy cảm được che.

### 16.2. Đặt alert theo tác động

Ví dụ:
- Tỷ lệ acquire timeout tăng.
- Query p95/p99 vượt ngưỡng.
- Transaction duration tăng bất thường.
- Tỷ lệ request bị giới hạn tăng đột biến.
- Response size vượt baseline.
- Pool pending tồn tại liên tục.

Một số request bị từ chối vì vượt giới hạn có thể là hành vi mong muốn. Alert nên phân biệt client misuse/bot traffic với lỗi hệ thống làm từ chối request hợp lệ.

## 17. Kiểm thử các giới hạn

### 17.1. Kiểm thử validation ở biên HTTP

Kiểm tra:
- Body đúng giới hạn được chấp nhận.
- Body vượt giới hạn bị từ chối.
- Keyword quá dài bị từ chối.
- Page size âm, bằng 0 hoặc quá lớn bị từ chối.
- Page vượt phạm vi bị từ chối.
- Sort field không nằm trong enum bị từ chối.
- Danh sách ID vượt giới hạn bị từ chối.
- Filter quá nhiều hoặc lồng quá sâu bị từ chối.

Test phải xác nhận service/repository không được gọi khi request bị chặn ở validation layer.

### 17.2. Kiểm thử query limit

Seed nhiều hơn max page size, gọi service và xác nhận:
- Số hàng trả về không vượt limit.
- Query thực sự có giới hạn phía database.
- Không có bước collect toàn bộ trước khi cắt kết quả.
- Sort ổn định với khóa tie-breaker.
- Cursor trang sau không lặp hàng.

### 17.3. Kiểm thử timeout

Có thể dùng publisher được điều khiển trong test để xác nhận timeout:

~~~java
StepVerifier.withVirtualTime(() ->
        service.loadSlowData()
            .timeout(Duration.ofSeconds(2))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectError(TimeoutException.class)
    .verify();
~~~

Virtual time phù hợp với publisher dựa trên scheduler hỗ trợ virtual time. Nó không chứng minh database server hoặc R2DBC driver đã hủy query thật. Cần integration test riêng cho statement timeout và connection cleanup.

### 17.4. Kiểm thử acquire timeout và pool exhaustion

Dùng pool test có max size nhỏ, giữ connection bằng publisher test và gửi thêm yêu cầu. Xác nhận:
- Pending tăng trong giới hạn.
- Acquire timeout phát lỗi khi hết thời gian.
- Connection được release sau complete/error/cancel.
- Request tiếp theo có thể lấy connection.
- Không có connection bị rò rỉ.

Không dùng Thread.sleep để tạo trạng thái cạnh tranh. Dùng barrier hoặc publisher điều khiển thời điểm release.

### 17.5. Kiểm thử tải và giới hạn tổng thể

Load test cần mô phỏng:
- Nhiều người dùng đồng thời.
- Request hợp lệ ở page size tối đa.
- Filter có chi phí cao.
- Burst request.
- Database chậm.
- Downstream chậm.
- Client cancel giữa chừng.
- Nhiều tenant cùng truy cập.

Quan sát p95/p99 latency, error rate, acquired/idle/pending, query duration và database session. Giới hạn cần bảo vệ hệ thống mà vẫn đáp ứng SLO của request hợp lệ.

## 18. Những lỗi thường gặp

| Lỗi hoặc nhầm lẫn | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ giới hạn page size ở UI | Client có thể gửi giá trị lớn trực tiếp | Validate ở server |
| Dùng LIMIT sau collectList | Database và ứng dụng đã đọc/gom tất cả hàng | Đặt LIMIT trong query |
| Cho client gửi raw SQL | Mất kiểm soát cấu trúc và chi phí query | Dùng DTO filter có allowlist |
| Nối sort field từ request vào SQL | Có thể thay đổi cấu trúc SQL | Map enum sang identifier cố định |
| Chỉ bind giá trị rồi nghĩ identifier cũng an toàn | Bind parameter không bind được tên cột | Allowlist table/column/operator |
| Cho IN list không giới hạn | SQL dài, nhiều bind parameter và tốn tài nguyên | Giới hạn phần tử hoặc batch |
| Offset không giới hạn | Query trang sâu có thể rất chậm | Giới hạn page hoặc dùng keyset |
| Sort không ổn định | Trang có thể lặp hoặc bỏ sót hàng | Thêm unique tie-breaker |
| Count mọi truy vấn | Tốn database CPU/I/O | Chỉ count khi cần và giới hạn phạm vi |
| Trả entity đầy đủ cho list | Response lớn và có thể lộ field nhạy cảm | Projection/DTO với cột cần thiết |
| collectList trên Flux không giới hạn | Heap có thể tăng mạnh | Giới hạn, phân trang hoặc streaming có kiểm soát |
| Chỉ đặt Reactor timeout | Driver/database có thể chưa dừng query | Thêm statement timeout và kiểm tra cancellation |
| Dùng một timeout cho mọi lớp | Request có thể chờ quá lâu hoặc bị cắt không đúng chỗ | Phân bổ deadline theo từng lớp |
| Giữ transaction khi gọi HTTP ngoài | Connection bị giữ, side effect không rollback | Tách transaction và dùng outbox/saga |
| flatMap không giới hạn | Quá nhiều query cùng lúc | Giới hạn concurrency |
| Tăng pool size thay vì giới hạn workload | Database có thể bị quá tải hơn | Điều tra query, hold time và tổng connection |
| Chỉ dựa vào backpressure | Không bảo vệ request body, query complexity hoặc rate | Thêm giới hạn tại từng biên |
| Cursor được coi là authorization | Người dùng có thể thử cursor của tài nguyên khác | Áp dụng authorization cho mọi query |

## 19. Quy trình thiết lập giới hạn an toàn

Khi xây dựng hoặc rà soát một endpoint truy cập R2DBC, hãy làm theo trình tự:

1. Xác định tài nguyên mà request có thể tiêu thụ: body, filter, query, rows, response, connection và thời gian.
2. Đặt giới hạn request body và multipart ở server.
3. Dùng DTO có validation cho keyword, page, page size, filter, sort và collection.
4. Chỉ cho phép field/operator nằm trong allowlist.
5. Bind mọi giá trị SQL; không nhận raw SQL từ client.
6. Giới hạn số bind parameter, số ID và số filter.
7. Đặt LIMIT trong query và sort ổn định.
8. Dùng keyset pagination cho tập dữ liệu lớn hoặc trang sâu.
9. Chỉ SELECT cột cần thiết và giới hạn kích thước response.
10. Chia batch ghi và giới hạn concurrency.
11. Cấu hình acquire timeout và pending limit cho pool.
12. Cấu hình statement timeout theo driver/database và transaction timeout phù hợp.
13. Đặt deadline tổng cho request và timeout cho downstream.
14. Đảm bảo cancellation và cleanup không làm rò connection.
15. Áp dụng authorization/tenant filter cho mọi query, kể cả count và trang tiếp theo.
16. Theo dõi rows returned, response bytes, query duration, pool wait và transaction duration.
17. Viết integration test cho boundary values, timeout, cancellation và pool exhaustion.
18. Chạy load test để xác nhận giới hạn bảo vệ database mà vẫn đáp ứng SLO.

## 20. Bài tập tự kiểm tra

### Bài 1: Page size

Một API cho phép client gửi pageSize. Giao diện chỉ hiển thị tối đa 100 nhưng client gửi 500.000. Server cần làm gì?

Gợi ý: Validate ở server và từ chối hoặc áp dụng mức tối đa theo hợp đồng. Đặt LIMIT trực tiếp trong query.

### Bài 2: Raw SQL

Một endpoint nhận field sortBy và nối trực tiếp vào ORDER BY. Vì sao bind parameter không giải quyết được vấn đề?

Gợi ý: Bind parameter chỉ đại diện cho giá trị, không phải identifier hoặc từ khóa SQL. Map enum sang tên cột allowlist.

### Bài 3: IN list

Một request chứa 20.000 ID. Những giới hạn nào cần xem xét?

Gợi ý: Kích thước body, số phần tử, bind parameter limit của database/driver, query size, batch size và thời gian xử lý.

### Bài 4: LIMIT

Vì sao repository.findAll().collectList().map(list -> list.subList(0, 100)) không phải cách giới hạn query?

Gợi ý: Toàn bộ dữ liệu đã được đọc và gom vào heap trước khi cắt. Hãy đặt LIMIT trong SQL hoặc Query.

### Bài 5: Offset pagination

Vì sao offset rất lớn có thể chậm?

Gợi ý: Database có thể phải duyệt/bỏ qua nhiều hàng trước khi trả trang cần thiết. Cân nhắc keyset pagination với thứ tự ổn định.

### Bài 6: Acquire timeout

Request bị acquire timeout có nghĩa SQL chạy quá thời gian không?

Gợi ý: Không. Request chưa lấy được connection nên câu SQL có thể chưa bắt đầu.

### Bài 7: Reactor timeout

Publisher timeout sau 2 giây. Có thể kết luận database query đã dừng ngay không?

Gợi ý: Không. Cancellation được gửi upstream nhưng khả năng dừng statement phụ thuộc driver/database. Cần statement timeout và kiểm chứng cleanup.

### Bài 8: Transaction duration

Một service mở transaction, gọi HTTP service 8 giây rồi cập nhật order. Tác động nào có thể xảy ra?

Gợi ý: Connection và transaction có thể bị giữ trong thời gian chờ; HTTP side effect không rollback theo R2DBC. Tách lời gọi ngoài transaction.

### Bài 9: Concurrency

Một request dùng flatMap concurrency 10 và có 100 request đồng thời. Có thể có bao nhiêu inner operation cùng hoạt động?

Gợi ý: Có thể xấp xỉ 1.000 nếu tất cả request đạt concurrency tối đa. Cần giới hạn tổng tải ở gateway/service/database.

### Bài 10: Response size

Một trang chỉ có 50 hàng nhưng mỗi hàng chứa trường BLOB 5 MB. Page size 50 có đủ bảo vệ response không?

Gợi ý: Không. Cần giới hạn cả kích thước từng bản ghi và response; tách tải nội dung lớn sang endpoint riêng.

## 21. Ghi nhớ

- Giới hạn kích thước truy vấn, số bản ghi và thời gian xử lý là một phần của bảo mật và availability.
- Luôn validate ở server; không dựa vào giới hạn ở UI/client.
- Giới hạn request body, độ dài chuỗi, số filter, số phần tử collection và độ sâu cấu trúc.
- Không nhận raw SQL từ client.
- Bind parameter cho giá trị; allowlist identifier, sort field và operator.
- Giới hạn số phần tử IN và số bind parameter; chia batch cho tác vụ lớn.
- Đặt LIMIT ngay trong SQL hoặc Query, không đọc tất cả rồi mới cắt.
- Giới hạn cả số hàng, kích thước từng hàng và tổng response bytes.
- Dùng sort ổn định; keyset pagination phù hợp với tập dữ liệu lớn và trang sâu.
- COUNT và GROUP BY cũng có thể tốn tài nguyên dù trả ít hàng.
- Giới hạn batch size và concurrency; không tạo quá nhiều query đồng thời.
- Acquire timeout, statement timeout, transaction timeout, downstream timeout và request deadline bảo vệ các lớp khác nhau.
- Reactor timeout gửi cancellation nhưng không bảo đảm database dừng query ngay.
- Transaction ngắn giúp giảm thời gian giữ connection và lock.
- Backpressure không thay thế giới hạn request body, query complexity, rate và connection pool.
- Áp dụng authorization và tenant filter cho mọi query, kể cả count và trang tiếp theo.
- Theo dõi query duration, rows returned, response bytes, acquire wait, pending và transaction duration.
- Kiểm thử boundary values, timeout, cancellation, pool exhaustion và load trên database/driver mục tiêu.

Một API R2DBC an toàn phải giới hạn lượng công việc mà mỗi request có thể yêu cầu, số tài nguyên được dùng đồng thời và thời gian những tài nguyên đó bị giữ. Hãy áp dụng giới hạn từ request body đến SQL, số hàng, response, connection pool và transaction; đồng thời kiểm tra quyền truy cập và đo lường thực tế. Khi mỗi lớp có một ngân sách rõ ràng, một request quá lớn hoặc quá chậm sẽ được kiểm soát trước khi ảnh hưởng tới toàn bộ ứng dụng.

