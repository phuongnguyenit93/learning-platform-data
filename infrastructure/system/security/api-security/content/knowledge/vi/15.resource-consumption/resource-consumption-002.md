# Giới hạn request body, page size và batch size

Một API có thể xác thực và phân quyền đúng nhưng vẫn bị làm chậm hoặc ngừng hoạt động nếu cho phép client gửi request quá lớn, yêu cầu quá nhiều bản ghi trong một trang hoặc xử lý batch chứa hàng chục nghìn phần tử. Những request này có thể tiêu hao bộ nhớ, CPU, database connection, băng thông, thread và dung lượng lưu trữ. Kẻ tấn công không nhất thiết phải khai thác lỗ hổng code; chỉ cần lặp lại các request hợp lệ nhưng tốn tài nguyên là có thể gây từ chối dịch vụ (Denial of Service – DoS) hoặc làm tăng chi phí vận hành.

Giới hạn request body, page size và batch size là các kiểm soát cơ bản để bảo vệ tính sẵn sàng của API. Các giới hạn cần được xác định theo nghiệp vụ, áp dụng ở nhiều tầng, có thông báo lỗi nhất quán và được kiểm thử dưới tải. Không có một con số tối đa phù hợp cho mọi endpoint: upload file, tìm kiếm, xuất báo cáo và cập nhật hàng loạt có đặc tính tài nguyên khác nhau.

## 1. Vì sao API phải giới hạn tài nguyên?

Mỗi request sử dụng một phần tài nguyên hữu hạn:

- **Network:** băng thông, socket và thời gian truyền dữ liệu.
- **Memory:** buffer nhận body, object sau deserialize, danh sách kết quả và response đang chờ gửi.
- **CPU:** parse JSON/XML, validate, nén/giải nén, tính toán và serialize.
- **Database:** connection, query execution, sort, join, lock, transaction và temporary storage.
- **Thread/concurrency:** worker thread, event loop, task queue và connection pool.
- **Storage:** file upload, export, bản ghi batch, cache và dữ liệu trung gian.

Một request có body 100 MB có thể tạo ra object graph lớn hơn nhiều sau deserialize. Một truy vấn `pageSize=1000000` có thể buộc database đọc, sort và serialize hàng trăm nghìn bản ghi. Một batch gồm 50.000 lệnh cập nhật có thể giữ transaction và lock quá lâu, làm nghẽn các request khác.

### 1.1. Resource exhaustion và unrestricted resource consumption

Unrestricted Resource Consumption xảy ra khi API không giới hạn đủ việc sử dụng tài nguyên theo request, user, client hoặc tenant. Hậu quả có thể là:

- API chậm, timeout hoặc hết bộ nhớ.
- Database connection pool cạn, hàng đợi request tăng và các endpoint không liên quan cũng bị ảnh hưởng.
- CPU tăng do parse, validate, regex, nén hoặc xử lý nghiệp vụ tốn kém.
- Dung lượng lưu trữ bị lấp bởi file, batch hoặc export.
- Chi phí cloud, database, bandwidth hoặc dịch vụ bên thứ ba tăng bất thường.
- Một tenant hoặc client tiêu thụ phần lớn tài nguyên của hệ thống multi-tenant.

Rate limit chỉ giới hạn số lần gọi trong một khoảng thời gian. Nó không đủ nếu một request đơn lẻ có thể yêu cầu hàng triệu bản ghi hoặc gửi body rất lớn. Cần giới hạn cả tần suất, kích thước, số lượng phần tử, thời gian xử lý và concurrency.

## 2. Thiết kế giới hạn theo từng endpoint

Trước khi đặt con số, hãy xác định endpoint làm gì và tài nguyên nào chi phối chi phí. Ví dụ:

| Loại endpoint | Giới hạn cần cân nhắc |
|---|---|
| Tạo/cập nhật một object JSON | Body bytes, độ sâu JSON, số field, độ dài chuỗi |
| Upload tài liệu | Tổng request bytes, file bytes, số part, kích thước từng part, thời gian upload |
| Search/list | Page size, số filter, độ dài filter, độ sâu sort, thời gian query |
| Bulk update/import | Batch item count, tổng bytes, số lỗi, transaction duration, concurrency |
| Export/report | Số bản ghi, thời gian chạy, kích thước output, số job đang chạy, quota lưu trữ |
| Endpoint tính toán nặng | CPU budget, timeout, concurrency, request complexity |

Mỗi endpoint nên có một ngân sách tài nguyên (*resource budget*) phù hợp. Giới hạn cần được công bố trong tài liệu API, đặt ở server và có thể khác nhau theo plan, client hoặc tenant nếu chính sách nghiệp vụ cho phép. Không để client tự chọn giới hạn bằng một tham số không được kiểm tra.

## 3. Giới hạn request body

Request body là nguồn tiêu hao bộ nhớ và CPU trực tiếp. Server cần giới hạn số byte được nhận trước khi parse, sau đó giới hạn cấu trúc và độ phức tạp của dữ liệu đã parse.

### 3.1. Giới hạn tổng số byte

Ví dụ endpoint tạo hồ sơ chỉ cần JSON nhỏ, có thể đặt giới hạn body 256 KB. Endpoint upload file có thể có giới hạn riêng, chẳng hạn 10 MB cho mỗi file và 12 MB cho toàn multipart request. Các con số này chỉ là ví dụ; cần đo theo dữ liệu hợp lệ và capacity của hệ thống.

Giới hạn phải được thực thi ở:

1. **CDN/load balancer/API gateway/reverse proxy:** chặn request vượt kích thước trước khi chuyển vào application.
2. **Web server/container:** giới hạn request và buffering theo khả năng của server.
3. **Application/framework:** kiểm soát body thực tế trước hoặc trong quá trình đọc, đặc biệt với endpoint có xử lý streaming.
4. **Business validation:** giới hạn số field, độ dài chuỗi, số phần tử và cấu trúc lồng nhau.

Không chỉ dựa vào `Content-Length`. Header này có thể vắng mặt, sai hoặc không phản ánh tổng dữ liệu được đọc trong mọi kiểu truyền. Với chunked transfer hoặc streaming, server/gateway phải đếm byte thực tế và dừng đọc khi vượt giới hạn. Không cấp phát một buffer theo giá trị `Content-Length` do client cung cấp trước khi xác minh giới hạn.

### 3.2. Giới hạn sau giải nén

Nếu API chấp nhận `Content-Encoding: gzip` hoặc một coding khác, body nhỏ sau nén có thể giải nén thành dữ liệu rất lớn (*decompression bomb*). Cần giới hạn cả:

- Số byte nhận trước giải nén.
- Số byte sau giải nén.
- Tỷ lệ nén tối đa nếu phù hợp.
- Thời gian và CPU cho giải nén.
- Số lớp/nhiều tầng nén được phép.

Chỉ hỗ trợ content coding thực sự cần thiết. Nếu endpoint không hỗ trợ coding, từ chối rõ ràng. Không giải nén nhiều lần hoặc không giới hạn chỉ vì một header được gửi đến.

### 3.3. Giới hạn cấu trúc JSON/XML

Giới hạn byte không ngăn được mọi payload độc hại. Một JSON nhỏ nhưng lồng rất sâu có thể làm parser hoặc validator tiêu tốn CPU/stack. Một object có hàng chục nghìn field, array lớn hoặc chuỗi cực dài cũng có thể gây áp lực bộ nhớ.

Đặt giới hạn phù hợp cho:

- Độ sâu lồng nhau tối đa.
- Số phần tử trong array và số field trong object.
- Độ dài từng chuỗi và tổng kích thước văn bản.
- Số lượng lỗi validation được thu thập/trả về.
- Số lượng phần tử tham chiếu cần tra cứu trong database.

Nếu hỗ trợ XML, cấu hình parser an toàn và tắt DTD/external entity khi không cần thiết; giới hạn độ sâu, số node và kích thước tài liệu. Nếu hỗ trợ JSON polymorphic deserialization, tránh cấu hình kiểu class tùy ý do payload điều khiển.

### 3.4. Giới hạn upload multipart

Multipart có thể chứa nhiều part, mỗi part có header và body riêng. Chỉ giới hạn tổng request size là chưa đủ nếu một request có hàng nghìn part nhỏ. Cần giới hạn tổng byte, kích thước mỗi file, số part, kích thước metadata, thời gian upload và dung lượng lưu trữ.

Ví dụ cấu hình Spring Boot cho multipart:

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB
```

Các thuộc tính này áp dụng cho multipart trong Servlet stack; chúng không phải giới hạn chung cho mọi JSON request. Cần cấu hình thêm ở reverse proxy/container và kiểm tra đúng phiên bản Spring Boot đang sử dụng. Không để file tạm được lưu vô hạn; dọn file thất bại/hết hạn và giới hạn quota theo tenant.

### 3.5. Streaming thay vì đọc toàn bộ vào memory

Với file lớn hoặc dữ liệu tuần tự, streaming có thể giảm bộ nhớ đỉnh bằng cách xử lý từng chunk. Tuy nhiên, streaming không thay thế giới hạn tổng bytes, thời gian, tốc độ tối thiểu, số kết nối và dung lượng đích. Nếu consumer chậm, cần backpressure để producer không tạo queue vô hạn.

Không dùng `readAllBytes()` hoặc deserialize toàn bộ file lớn vào memory nếu nghiệp vụ có thể xử lý theo luồng. Đặt giới hạn và kiểm tra trước khi ghi file cuối cùng; dùng file tạm an toàn và chỉ publish khi upload hoàn tất, kiểm tra thành công.

### 3.6. Mã trạng thái khi body vượt giới hạn

`413 Content Too Large` (trước đây thường được gọi là Payload Too Large) là phản hồi phù hợp khi request content vượt giới hạn được server cho phép. Lỗi nên có định dạng thống nhất, không trả stack trace hoặc cấu hình nội bộ.

Ví dụ:

```http
HTTP/1.1 413 Content Too Large
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/request-too-large",
  "title": "Content Too Large",
  "status": 413,
  "detail": "Request body vượt giới hạn 256 KB của endpoint này."
}
```

Nếu body có kích thước hợp lệ nhưng JSON sai cú pháp, thường trả `400 Bad Request`. Nếu media type không được hỗ trợ, trả `415 Unsupported Media Type`. Không dùng cùng một mã lỗi cho mọi nguyên nhân nếu client cần biết cách sửa request.

## 4. Giới hạn page size và pagination

Pagination giúp client lấy dữ liệu theo từng phần, nhưng API vẫn phải giới hạn kích thước mỗi trang. Nếu cho phép page size tùy ý, client có thể yêu cầu quá nhiều bản ghi trong một lần gọi.

### 4.1. Đặt default và maximum page size

Ví dụ endpoint có default page size 20 và maximum 100:

```http
GET /api/orders?page=0&size=20 HTTP/1.1
Authorization: Bearer <access-token>
```

Nếu client gửi `size=100000`, server cần từ chối hoặc clamp về 100 theo hợp đồng API. Cần chọn một hành vi rõ ràng:

- **Clamp:** giới hạn giá trị về mức tối đa và trả page size thực tế trong response metadata.
- **Reject:** trả `400 Bad Request` khi size vượt maximum, giúp client biết phải sửa request.

Không nên im lặng xử lý một page size khác xa giá trị client yêu cầu mà không thể hiện trong response.

Ví dụ response:

```json
{
  "items": [],
  "page": 0,
  "size": 100,
  "totalElements": 2450,
  "totalPages": 25
}
```

Metadata cần phản ánh page size thực tế được áp dụng, không phải giá trị ban đầu chưa kiểm tra.

### 4.2. Kiểm tra page, size và số học tràn

Không chỉ kiểm tra `size`. Cần kiểm tra:

- Page index không âm.
- Page size dương và không vượt maximum.
- Tính toán offset không bị integer overflow.
- Sort field nằm trong allowlist; không ghép trực tiếp chuỗi sort do client gửi vào SQL.
- Filter có số lượng và độ dài giới hạn.
- Tổng số trang hoặc `COUNT(*)` không tạo query quá tốn kém nếu dataset lớn.

Ví dụ `page=2147483647` và `size=100` có thể gây tràn khi tính `page * size` nếu dùng kiểu integer. Dùng kiểu số phù hợp, kiểm tra trước phép nhân và từ chối giá trị không hợp lệ.

### 4.3. Offset pagination và deep pagination

Offset pagination đơn giản:

```sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, id DESC
LIMIT :page_size OFFSET :offset;
```

Khi offset rất lớn, database có thể phải duyệt hoặc bỏ qua nhiều dòng trước khi trả kết quả. Điều này tốn CPU/I/O và có thể làm chậm cả hệ thống. Cần giới hạn maximum page/offset, tạo index theo filter và sort thường dùng, và kiểm soát query plan.

Với dữ liệu lớn hoặc cần phân trang ổn định, cân nhắc cursor/keyset pagination:

```sql
SELECT id, created_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND (created_at, id) < (:cursor_created_at, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT :page_size;
```

Cursor cần dựa trên thứ tự ổn định, có tie-breaker duy nhất và được kiểm tra ở server. Nếu cursor được ký hoặc mã hóa để chống sửa đổi, vẫn phải xác minh tenant, filter và quyền; cursor không phải credential cấp quyền truy cập. Cần quyết định cursor có hết hạn không và xử lý khi dữ liệu thay đổi giữa các trang.

### 4.4. Tránh lộ dữ liệu qua total count và sort/filter

`totalElements` có thể tiết lộ quy mô dữ liệu tenant khác nếu query count thiếu tenant filter. Một số filter hoặc sort field có thể tạo query cực tốn kém. Chỉ cho phép field được index/hỗ trợ, giới hạn số điều kiện, độ sâu filter và khoảng thời gian tìm kiếm. Với tập dữ liệu lớn, cân nhắc không trả tổng số bản ghi chính xác hoặc dùng count có cache/ước lượng nếu nghiệp vụ cho phép.

### 4.5. Ví dụ clamp page size trong Java

```java
public record PageRequestSpec(int page, int size) {
    public static PageRequestSpec of(int page, int requestedSize) {
        if (page < 0) {
            throw new IllegalArgumentException("page must be non-negative");
        }
        if (requestedSize <= 0) {
            throw new IllegalArgumentException("size must be positive");
        }

        int maxSize = 100;
        int actualSize = Math.min(requestedSize, maxSize);
        return new PageRequestSpec(page, actualSize);
    }
}
```

Ví dụ này clamp size về 100. Trong ứng dụng thực tế, có thể chọn reject thay vì clamp và cần kiểm tra offset bằng phép toán an toàn trước khi tạo `PageRequest` hoặc query. Tenant filter và authorization object vẫn phải được áp dụng trong query.

## 5. Giới hạn batch size

Batch API cho phép gửi nhiều thao tác trong một request để giảm round trip. Tuy nhiên, batch quá lớn làm tăng bộ nhớ, thời gian xử lý, lock, transaction log và phạm vi ảnh hưởng khi lỗi.

Ví dụ:

```http
POST /api/orders/batch-update HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "items": [
    {"id": "O-100", "status": "CANCELLED"},
    {"id": "O-101", "status": "CANCELLED"}
  ]
}
```

Nếu API không giới hạn số item, một request có thể chứa hàng chục nghìn thao tác. Server phải đặt maximum item count, tổng byte, kích thước từng item và chi phí tối đa.

### 5.1. Các giới hạn cần có cho batch

- Số item tối đa trong một batch.
- Tổng request bytes và kích thước mỗi item.
- Số lượng field và độ dài chuỗi trong từng item.
- Số lượng thao tác database hoặc dịch vụ bên ngoài được gọi.
- Thời gian xử lý tối đa và số batch đang chạy đồng thời.
- Số lượng lỗi chi tiết được trả về để tránh response quá lớn.
- Số batch theo user/client/tenant trong một khoảng thời gian.

Maximum batch size nên dựa trên đo tải và đặc tính thao tác. Batch cập nhật một field có chi phí khác batch tạo giao dịch hoặc gọi nhiều dịch vụ bên ngoài. Có thể dùng giới hạn riêng theo loại endpoint và plan, nhưng server phải quyết định và kiểm tra.

### 5.2. Validation từng item và tổng thể

Không chỉ validate array không rỗng. Cần kiểm tra:

- `items` không vượt maximum và không chứa null.
- Mỗi item đúng schema, có ID hợp lệ và chỉ có field được phép thay đổi.
- Không có ID trùng nếu nghiệp vụ không cho phép.
- Mỗi object thuộc tenant và phạm vi principal được phép truy cập.
- Tổng số thao tác và dependency nằm trong budget.
- Các item có tương thích với trạng thái nghiệp vụ hiện tại không.

Ví dụ DTO:

```java
public record BatchUpdateRequest(
        @NotEmpty
        @Size(max = 100)
        List<@NotNull @Valid OrderUpdateItem> items) {
}

public record OrderUpdateItem(
        @NotNull UUID id,
        @NotNull OrderStatus status) {
}
```

`@Size(max = 100)` giới hạn số item sau khi body được parse. Nó không thay thế giới hạn request bytes ở gateway/server vì application đã phải nhận và parse body để chạy Bean Validation. Cần áp dụng cả hai lớp.

### 5.3. Atomic batch hay partial success?

API phải công bố rõ semantics khi một item lỗi:

- **Atomic:** tất cả thao tác thành công hoặc rollback toàn bộ. Phù hợp khi các thay đổi phải nhất quán cùng nhau, nhưng batch lớn có thể giữ transaction/lock lâu.
- **Partial success:** xử lý từng item độc lập và trả kết quả thành công/thất bại theo item. Phù hợp với import hoặc cập nhật độc lập, nhưng client cần xử lý retry và kết quả không đồng nhất.
- **Asynchronous job:** nhận yêu cầu, kiểm tra sơ bộ, tạo job rồi xử lý nền. Phù hợp tác vụ dài hoặc lớn; cần trạng thái job, quota, cancellation, retry và thời hạn lưu kết quả.

Không giữ một transaction database dài cho hàng chục nghìn item nếu không thực sự cần atomicity. Có thể chia thành chunk nhỏ, commit theo chunk và lưu tiến độ. Nếu nghiệp vụ yêu cầu atomic, cần giới hạn batch đủ nhỏ để transaction có thể hoàn tất trong budget.

### 5.4. Idempotency và retry

Client có thể retry khi timeout dù server đã xử lý một phần hoặc toàn bộ batch. Với thao tác tạo giao dịch hoặc side effect, cần idempotency key hoặc định danh thao tác duy nhất. Server lưu kết quả xử lý theo principal/client, endpoint và idempotency key trong thời hạn phù hợp; request lặp lại phải trả kết quả tương ứng thay vì tạo side effect lần nữa.

Đối với partial success, mỗi item có thể cần item ID hoặc idempotency key riêng. Không retry mù toàn bộ batch nếu một phần đã thành công. Response phải chỉ rõ item nào đã xử lý và item nào có thể retry an toàn.

### 5.5. Kiểm soát concurrency và backpressure

Batch nhỏ nhưng hàng nghìn batch chạy đồng thời vẫn có thể làm cạn tài nguyên. Giới hạn số job đồng thời theo tenant/client, độ dài hàng đợi, worker count và số database connection. Dùng backpressure hoặc từ chối sớm khi hệ thống quá tải; không đưa request vào queue vô hạn.

Với job nền, giới hạn số job đang chờ và tổng dung lượng input. Đặt timeout, retry có backoff và giới hạn số lần retry. Dead-letter queue cần có quota và quy trình dọn dữ liệu; retry liên tục một payload lỗi có thể tạo vòng lặp tiêu hao tài nguyên.

## 6. Kết hợp giới hạn kích thước, số lượng và thời gian

Một giới hạn riêng lẻ không đủ. Ví dụ body 1 MB có thể chứa một array gồm hàng nghìn phần tử nhỏ; batch 100 item có thể khiến mỗi item gọi một API bên ngoài chậm; page size 100 có thể chạy query không có index và timeout.

Nên đặt nhiều lớp:

| Tầng | Kiểm soát | Mục tiêu |
|---|---|---|
| Gateway/proxy | Request bytes, header bytes, connection, timeout, rate limit | Chặn request lớn hoặc chậm trước application |
| HTTP server | Read timeout, max connections, request limits | Bảo vệ socket, thread và buffer |
| Parser/validation | Depth, field count, array count, string length | Giới hạn chi phí parse và object graph |
| API contract | Page size, batch size, file size, filter count | Giới hạn công việc mỗi request |
| Service | Business budget, dependency calls, concurrency | Ngăn thao tác nghiệp vụ quá tốn kém |
| Database | Query timeout, index, connection pool, row limit | Bảo vệ database và lock |
| Background worker | Queue capacity, job concurrency, retry budget | Tránh backlog và retry storm |
| Tenant/client policy | Quota, rate limit, storage budget | Ngăn một chủ thể chiếm tài nguyên chung |

### 6.1. Timeout và deadline

Đặt timeout riêng cho đọc request, query database, gọi dịch vụ bên ngoài và toàn bộ request. Timeout của từng tầng cần phối hợp để request không bị giữ vô hạn. Dùng deadline tổng để các bước con không tiếp tục chạy sau khi request đã hết thời gian. Hủy công việc khi client disconnect nếu có thể và an toàn.

### 6.2. Rate limit, quota và concurrency limit

- **Rate limit:** số request trong một cửa sổ thời gian.
- **Quota:** tổng mức sử dụng trong ngày/tháng hoặc theo gói dịch vụ.
- **Concurrency limit:** số request/job đang chạy đồng thời.
- **Resource budget:** tổng bytes, rows, CPU time, dependency calls hoặc chi phí được phép.

Áp dụng theo principal, API client, tenant và IP tùy loại endpoint. Không chỉ giới hạn theo IP vì nhiều người có thể dùng chung NAT; cũng không chỉ giới hạn theo user nếu một key/service account có thể chạy nhiều user. Cần có global protection để bảo vệ hệ thống khi nhiều client cùng tăng tải.

### 6.3. Giới hạn công bằng giữa tenant

Trong multi-tenant, một tenant có thể gửi lượng lớn request hợp lệ và chiếm database connection hoặc worker. Dùng quota/concurrency riêng theo tenant, giới hạn job export và storage, cùng global capacity limit. Khi tenant chạm quota, phản hồi rõ ràng và cho biết thời điểm có thể thử lại nếu xác định được.

Không để tenant ID do client tự gửi quyết định quota bucket. Bucket phải gắn với tenant context đã xác minh; nếu không, người gọi có thể thay ID để né giới hạn hoặc làm cạn quota của tenant khác.

## 7. Triển khai với Spring Boot/Spring MVC

Spring cung cấp một số lớp kiểm soát, nhưng không có một thuộc tính duy nhất áp dụng cho mọi loại request body. Cần kết hợp cấu hình proxy/container, multipart, validation và logic endpoint.

### 7.1. Multipart configuration

Ví dụ:

```yaml
spring:
  servlet:
    multipart:
      max-file-size: 10MB
      max-request-size: 12MB
```

Đây là giới hạn cho multipart file và tổng multipart request trong Servlet stack. Với JSON body, cần cấu hình giới hạn tại gateway/web server hoặc bộ đọc request có khả năng đếm bytes; không giả định hai thuộc tính multipart trên giới hạn mọi body.

### 7.2. Giới hạn page size

Nếu dùng Spring Data `Pageable`, có thể cấu hình resolver để đặt maximum page size. Ví dụ khung cấu hình MVC:

```java
@Configuration
class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addArgumentResolvers(
            List<HandlerMethodArgumentResolver> resolvers) {
        PageableHandlerMethodArgumentResolver resolver =
                new PageableHandlerMethodArgumentResolver();
        resolver.setMaxPageSize(100);
        resolver.setFallbackPageable(PageRequest.of(0, 20));
        resolvers.add(resolver);
    }
}
```

Đây là ví dụ cấu hình resolver; cần kiểm tra cách ứng dụng đăng ký resolver mặc định và tránh đăng ký trùng hoặc vô tình bỏ qua các resolver khác. Dù framework đã giới hạn page size, service/repository vẫn phải áp tenant scope, allowlist sort/filter và kiểm soát deep offset.

### 7.3. Giới hạn batch bằng validation

```java
public record BatchCancelRequest(
        @NotEmpty
        @Size(max = 100)
        List<@NotNull UUID> orderIds) {
}
```

Controller có thể nhận DTO đã validate:

```java
@PostMapping("/api/orders/batch-cancel")
ResponseEntity<BatchResult> cancelBatch(
        @Valid @RequestBody BatchCancelRequest request,
        AuthenticatedPrincipal principal) {

    BatchResult result = orderService.cancelBatch(
            principal, request.orderIds());
    return ResponseEntity.ok(result);
}
```

Service vẫn phải kiểm tra tenant/object authorization, trạng thái đơn và giới hạn nghiệp vụ. Annotation validation không thực thi rate limit, body byte limit, timeout hoặc concurrency limit.

### 7.4. Không dùng async để né giới hạn

Chuyển công việc sang `@Async` hoặc queue không làm biến mất chi phí. Cần giới hạn executor queue capacity, worker threads, job concurrency, thời hạn job và số lần retry. Dùng hàng đợi không giới hạn chỉ chuyển sự cố từ HTTP request sang backlog nền.

## 8. Mã trạng thái và phản hồi lỗi

Chọn status code theo nguyên nhân:

| Status | Khi nào dùng |
|---|---|
| `400 Bad Request` | Page/size/batch parameter sai định dạng hoặc vi phạm quy tắc API khi chính sách chọn reject |
| `413 Content Too Large` | Request body/file vượt giới hạn bytes |
| `414 URI Too Long` | URI vượt giới hạn server/proxy |
| `415 Unsupported Media Type` | Media type hoặc content coding không được hỗ trợ |
| `422 Unprocessable Content` | Payload parse được nhưng không hợp lệ theo schema/nghiệp vụ |
| `429 Too Many Requests` | Vượt rate limit hoặc quota theo chính sách; có thể kèm `Retry-After` |
| `503 Service Unavailable` | Hệ thống tạm thời quá tải hoặc không thể nhận thêm công việc; có thể kèm `Retry-After` |
| `504 Gateway Timeout` | Gateway không nhận được phản hồi kịp thời từ upstream |

Không dùng `413` cho page size hoặc batch item count nếu body bytes không vượt giới hạn; những trường hợp này thường là lỗi tham số/hợp đồng và có thể trả `400` hoặc `422` theo quy ước API. Nếu rate limit bị vượt, `429` phù hợp hơn `503`; nếu hệ thống quá tải toàn cục và tạm thời không thể phục vụ, có thể dùng `503`.

Response lỗi nên có mã lỗi ổn định, giới hạn thông tin và gợi ý cách sửa:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/rate-limit-exceeded",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Đã vượt giới hạn batch đang xử lý đồng thời.",
  "retryAfterSeconds": 30
}
```

Không trả stack trace, query SQL, giới hạn nội bộ nhạy cảm hoặc thông tin về tenant/client khác. Nếu có clamp page size, response metadata phải thể hiện page size thực tế.

## 9. Giám sát và cảnh báo

Để biết giới hạn có phù hợp hay không, cần đo cả mức sử dụng và tác động lên hệ thống.

Các metric hữu ích:

- Request body bytes: p50/p95/p99, số request bị từ chối, số request streaming lâu.
- Page size, offset/cursor depth, số rows đọc/trả, thời gian query và count query.
- Batch item count, tổng bytes, thời gian xử lý, tỷ lệ item lỗi và số lần retry.
- CPU, heap/memory, GC pause, thread pool, queue depth và connection pool saturation.
- Upload bytes, file tạm, storage quota và thời gian giữ file.
- Rate limit/quota theo principal/client/tenant và số request bị `429`/`503`.
- Dependency latency, timeout, query cancellation và lỗi serialization.

Đặt cảnh báo khi request lớn hoặc page/batch size thường xuyên chạm maximum, query p95/p99 tăng, queue backlog tăng, database pool gần cạn hoặc một tenant chiếm tỷ lệ tài nguyên bất thường. Cần phân biệt giới hạn bị chạm thường xuyên do client hợp lệ với hành vi lạm dụng; có thể điều chỉnh contract hoặc quota sau khi đo dữ liệu thực tế.

Log cần ghi request ID, endpoint, principal/client/tenant ID đã xác minh, kích thước và số phần tử, kết quả limit, thời gian xử lý và mã lỗi. Không ghi toàn bộ body, token, cookie hoặc dữ liệu nhạy cảm chỉ để điều tra resource consumption.

## 10. Kiểm thử giới hạn tài nguyên

Kiểm thử phải bao gồm cả trường hợp ngay dưới, đúng bằng và vượt giới hạn. Đồng thời kiểm tra hệ thống phục hồi sau khi từ chối request.

| Nhóm | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Body bytes | Body nhỏ hơn, bằng và lớn hơn maximum | Request hợp lệ được xử lý; body vượt ngưỡng nhận `413` |
| Không có Content-Length | Gửi chunked/streaming body vượt giới hạn | Server đếm bytes thực tế và dừng khi vượt ngưỡng |
| Decompression | Body nén nhỏ nhưng giải nén vượt ngưỡng | Từ chối trước khi cạn memory/CPU |
| JSON depth | Nested object vượt độ sâu cho phép | Parse/validation bị từ chối có kiểm soát |
| Array/field count | Array hoặc số field quá lớn | Bị từ chối theo schema/resource limit |
| Multipart | Quá nhiều part hoặc file vượt max-file-size | Bị từ chối và file tạm được dọn |
| Page size | `size=0`, âm, bằng max và lớn hơn max | Hành vi clamp/reject đúng hợp đồng |
| Page offset | Page index cực lớn gây overflow/deep pagination | Bị từ chối hoặc cursor flow vẫn có chi phí giới hạn |
| Sort/filter | Field lạ, quá nhiều filter hoặc sort phức tạp | Chỉ allowlist được chấp nhận |
| Batch count | 0, 1, max và max+1 item | Đúng validation và maximum |
| Duplicate item | Một ID lặp nhiều lần trong batch | Xử lý theo semantics được công bố, không gây side effect ngoài ý muốn |
| Partial failure | Một số item lỗi giữa batch | Kết quả từng item rõ ràng; retry an toàn |
| Atomic failure | Một item lỗi trong atomic batch | Rollback toàn bộ nếu contract yêu cầu atomic |
| Concurrency | Nhiều batch lớn chạy đồng thời | Concurrency/queue limit hoạt động, không backlog vô hạn |
| Tenant fairness | Một tenant gửi tải cao liên tục | Quota tenant được áp dụng, tenant khác vẫn có tài nguyên |
| Recovery | Sau khi request vượt giới hạn hoặc timeout | Connection, thread, temp file và transaction được giải phóng |

Load test cần dùng dữ liệu và query gần với production, có cả tenant lớn và nhỏ, object graph phức tạp, batch lỗi và dependency chậm. Kiểm tra không chỉ throughput mà cả memory, GC, database pool, queue depth và thời gian phục hồi sau spike.

## 11. Checklist thiết kế trước khi phát hành

- [ ] Mỗi endpoint có body byte limit rõ ràng ở gateway/proxy và application phù hợp.
- [ ] Body được đếm theo bytes thực tế; không chỉ tin `Content-Length`.
- [ ] Có giới hạn sau giải nén, parser depth, field count, array count và string length.
- [ ] Multipart giới hạn tổng request, từng file, số part, thời gian upload và storage quota.
- [ ] File lớn được stream/backpressure phù hợp; file tạm được dọn.
- [ ] Pagination có default/max page size, page index hợp lệ và xử lý offset overflow/deep pagination.
- [ ] Sort/filter field nằm trong allowlist và query có index/timeout phù hợp.
- [ ] Batch có maximum item count, bytes, validation từng item và semantics atomic/partial rõ ràng.
- [ ] Batch/job có idempotency, retry budget, concurrency limit và queue capacity.
- [ ] Quota/rate limit/concurrency được áp dụng theo principal, client, tenant và global capacity.
- [ ] Có timeout/deadline cho request, query và dependency call.
- [ ] `400`, `413`, `422`, `429`, `503` được dùng nhất quán và response không lộ nội bộ.
- [ ] Có metric cho body/page/batch, query latency, memory, queue và database pool.
- [ ] Có kiểm thử boundary, vượt giới hạn, concurrency, tenant fairness và recovery.

Giới hạn request body bảo vệ việc nhận và parse dữ liệu; page size giới hạn khối lượng truy vấn và response; batch size giới hạn số thao tác trong một lần xử lý. Kết hợp chúng với timeout, quota, concurrency control, backpressure và giám sát sẽ giúp API giữ được tính sẵn sàng ngay cả khi client gửi request lớn, chạy truy vấn tốn kém hoặc tạo tải đồng thời cao.
