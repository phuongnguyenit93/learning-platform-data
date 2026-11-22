# Giới hạn request body, truy vấn tốn tài nguyên và số yêu cầu trong Spring Data REST

## Mục tiêu

Spring Data REST giúp xuất bản repository nhanh chóng, nhưng một endpoint CRUD mở rộng có thể tiêu tốn nhiều tài nguyên nếu client gửi payload quá lớn, yêu cầu trang có kích thước không giới hạn, sắp xếp hoặc lọc theo trường tốn kém, hoặc gửi request với tần suất quá cao.

Cần bảo vệ API theo ba nhóm giới hạn:

- **Request body:** giới hạn số byte, số phần tử và độ phức tạp của dữ liệu đầu vào.
- **Query và response:** giới hạn page size, offset, sort/filter được hỗ trợ, thời gian truy vấn và kích thước kết quả.
- **Request rate và concurrency:** giới hạn số request theo user, API key, IP hoặc tenant; kiểm soát request đang chạy đồng thời.

Các giới hạn phải được thực thi ở server. Không dựa vào UI, JavaScript hoặc client tự giới hạn số lượng dữ liệu, vì người gọi có thể gửi request trực tiếp.

Bài này trình bày các điểm kiểm soát trong Spring Data REST, Spring MVC, Spring Security, gateway và database; cách chọn giới hạn hợp lý; cách trả lỗi 413/429; và cách kiểm thử để tránh API bị khai thác hoặc quá tải ngoài ý muốn.

## 1. Nhìn request như một ngân sách tài nguyên

Một request có thể tiêu tốn tài nguyên ở nhiều giai đoạn:

~~~text
Client
  |
  v
Gateway / reverse proxy
  |  body size, rate, connection limits
  v
Servlet container
  |  request size, header size, timeout
  v
Spring Security / MVC
  |  authentication, authorization, validation
  v
Spring Data REST
  |  binding, repository invocation, pagination
  v
Database
  |  query cost, sort, joins, locks, execution time
  v
Response serialization
     response bytes, nested associations, CPU
~~~

Giới hạn tại một tầng không thay thế giới hạn ở tầng khác. Ví dụ:

- Giới hạn page size không ngăn một POST có JSON body rất lớn.
- Giới hạn body size không ngăn một query nhỏ nhưng chạy nhiều phút.
- Rate limit không ngăn một request đơn lẻ yêu cầu hàng triệu bản ghi nếu page size không bị giới hạn.
- Giới hạn query không ngăn một client gửi hàng nghìn request đồng thời.

Nên xác định ngân sách cho từng loại endpoint: tối đa bao nhiêu byte input, bao nhiêu item mỗi trang, bao nhiêu điều kiện filter/sort, thời gian truy vấn tối đa, kích thước response và số request trong một khoảng thời gian.

## 2. Giới hạn page size của Spring Data REST

Pagination là một trong những lớp bảo vệ quan trọng nhất khi xuất bản collection. Spring Data REST cho phép cấu hình page size mặc định và tối đa:

~~~java
@Configuration
class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
    }
}
~~~

Trong ví dụ:

- Request không truyền size sẽ dùng page size mặc định 25.
- Request truyền size lớn hơn mức tối đa sẽ bị giới hạn theo cấu hình của exporter.
- Client không thể yêu cầu một trang có kích thước tùy ý chỉ bằng cách thay query parameter.

Giá trị 25 và 100 chỉ là ví dụ. Hãy chọn theo số trường được serialize, kích thước association, tải database, độ trễ và mục đích màn hình.

### Không chỉ nhìn số item

Một trang 100 item có thể nhỏ nếu mỗi item chỉ có vài trường, nhưng rất lớn nếu mỗi item chứa nhiều association hoặc nested representation. Projection có thể giảm dữ liệu trả về, nhưng không thay thế page size limit.

Khi chọn max page size, đo response bytes và thời gian serialize với dữ liệu gần thực tế. Không chọn giới hạn chỉ dựa trên số lượng item.

## 3. Giới hạn deep pagination và offset

Page size nhỏ vẫn có thể tạo truy vấn đắt nếu client yêu cầu page index rất lớn. Với offset pagination, database có thể phải bỏ qua nhiều hàng trước khi trả kết quả.

Ví dụ:

~~~http
GET /api/orders?page=500000&size=100
Accept: application/hal+json
~~~

Dù chỉ trả tối đa 100 item, truy vấn có thể tốn kém do offset lớn, phụ thuộc database, query plan và index.

Các cách kiểm soát:

- Đặt giới hạn page size.
- Đánh giá page index hoặc offset tối đa cho endpoint có dữ liệu lớn.
- Giới hạn sort/filter để query sử dụng index phù hợp.
- Dùng query method có điều kiện rõ ràng thay vì cho phép truy vấn tổng quát không giới hạn.
- Với dữ liệu rất lớn hoặc thay đổi liên tục, cân nhắc cursor/keyset pagination nếu API và repository hỗ trợ.

Spring Data REST page size configuration không tự động giải quyết mọi vấn đề deep offset. Nếu cần giới hạn offset, hãy kiểm tra request trước khi query hoặc thiết kế endpoint chuyên biệt có giới hạn rõ ràng. Không giả định max page size cũng là max page number.

## 4. Giới hạn sort và filter tốn tài nguyên

Sort theo một cột không có index, sort qua association hoặc kết hợp nhiều điều kiện có thể tạo query plan tốn kém. Query parameter do client cung cấp cần được giới hạn theo allowlist.

Ví dụ client gửi:

~~~http
GET /api/orders?sort=createdAt,desc&page=0&size=25
~~~

Một API nên xác định các thuộc tính sort được phép:

- createdAt.
- orderNumber.
- status.
- totalAmount nếu truy vấn và index hỗ trợ.

Không nên cho client sort tùy ý theo mọi property, đặc biệt property nested hoặc association có chi phí join cao.

Có thể kiểm soát ở nhiều lớp:

- Chỉ công bố các query method có tham số được hỗ trợ.
- Dùng custom controller/service để parse và allowlist sort/filter.
- Dùng query builder có whitelist property thay vì ghép chuỗi query từ input.
- Tạo index phù hợp với truy vấn phổ biến.
- Giới hạn số điều kiện sort và filter.
- Dùng database statement timeout hoặc query timeout phù hợp.

Không coi tên property do client gửi là SQL. Tuy nhiên, cho phép mọi property có thể làm tăng chi phí truy vấn hoặc vô tình công bố khả năng tìm kiếm mà ứng dụng không muốn hỗ trợ.

## 5. Giới hạn request body theo byte

Một POST hoặc PATCH có thể gửi JSON rất lớn:

~~~http
POST /api/people
Content-Type: application/json

{
  "displayName": "Ada",
  "notes": "... very large content ...",
  "attachments": [ ... thousands of entries ... ]
}
~~~

Spring Data REST dùng Spring MVC message conversion để đọc body. Cần đặt giới hạn kích thước ở tầng phù hợp:

- Reverse proxy hoặc API gateway thường là lớp đầu tiên để từ chối body vượt giới hạn trước khi request tới ứng dụng.
- Servlet container có các giới hạn cho request/header và một số loại body theo cấu hình riêng.
- Với JSON body, có thể cần bounded request wrapper hoặc filter chuyên biệt nếu nền tảng không cung cấp giới hạn byte phù hợp.
- Với multipart upload, dùng giới hạn multipart riêng của Spring Boot/container.

Không nhầm cấu hình multipart với giới hạn JSON tổng quát. Ví dụ, các thuộc tính multipart như max-file-size hoặc max-request-size chủ yếu điều khiển multipart upload; chúng không phải chính sách đầy đủ cho mọi application/json request.

### Content-Length không phải bằng chứng duy nhất

Một số request có thể truyền theo chunked transfer hoặc không có Content-Length như mong đợi. Nếu tự kiểm tra header Content-Length, vẫn cần bảo đảm luồng đọc thực tế bị giới hạn để tránh body lớn vượt qua kiểm tra.

Gateway/proxy thường là vị trí tốt để đặt giới hạn byte tổng quát. Nếu triển khai trong ứng dụng, dùng giải pháp có thể đếm byte khi đọc stream và từ chối ngay khi vượt ngưỡng, không đọc toàn bộ body vào memory trước rồi mới kiểm tra.

### Trả lỗi khi body quá lớn

HTTP 413 Payload Too Large là status phù hợp khi request body vượt giới hạn. Error body nên ngắn gọn và không phản chiếu nội dung body quá lớn.

Ví dụ response theo Problem Details:

~~~json
{
  "type": "about:blank",
  "title": "Payload too large",
  "status": 413,
  "detail": "The request body exceeds the allowed size.",
  "code": "REQUEST_BODY_TOO_LARGE"
}
~~~

Client có thể giảm kích thước payload, chia batch hoặc dùng upload workflow chuyên biệt.

## 6. Giới hạn số phần tử và độ sâu của JSON

Giới hạn byte không phải lúc nào cũng đủ. Một JSON nhỏ nhưng có cấu trúc rất sâu hoặc chứa rất nhiều node có thể làm tăng CPU và memory khi parse/bind.

Ví dụ request tạo một collection lồng nhiều cấp hoặc một mảng có số lượng phần tử rất lớn.

Các biện pháp phù hợp:

- Giới hạn số phần tử trong collection input bằng validation.
- Giới hạn độ dài chuỗi và số trường được chấp nhận.
- Giới hạn nesting depth và parser constraints theo Jackson version.
- Tránh bind một object graph lớn nếu use case chỉ cần vài trường.
- Dùng DTO có allowlist để xác định hợp đồng input.
- Giới hạn số item được xử lý trong một batch.
- Tách upload file lớn khỏi JSON CRUD endpoint.

Ví dụ DTO:

~~~java
public record BulkStatusRequest(
    @NotEmpty
    @Size(max = 100)
    List<@NotNull Long> ids,

    @NotNull
    OrderStatus status
) {
}
~~~

DTO giới hạn danh sách ID tối đa 100 và yêu cầu status. Server vẫn phải xác minh quyền trên từng ID và kiểm tra nghiệp vụ trước khi lưu.

## 7. Tránh truy vấn và response quá lớn do association

Một collection page có thể trả response lớn nếu mỗi item nhúng nhiều association hoặc projection chứa nhiều thuộc tính.

Ví dụ:

- Person có nhiều Address.
- Order có nhiều OrderLine.
- Mỗi OrderLine lại có Product và Category.
- Projection lồng sâu làm tăng số lượng object được serialize.

Các cách giảm chi phí:

- Dùng projection gọn cho collection.
- Chỉ expose association thực sự cần thiết.
- Dùng link để client tải resource liên quan khi cần.
- Tránh nested representation quá sâu.
- Giới hạn collection con hoặc tạo endpoint chuyên biệt để truy vấn chúng.
- Kiểm tra N+1 query khi serialize HAL.
- Đo kích thước response và thời gian serialize.

Projection giúp chọn representation nhưng không tự bảo đảm query hiệu quả. Một projection gọi getter association có thể kích hoạt lazy loading và tạo nhiều truy vấn. Hãy kiểm tra SQL và query plan với dữ liệu thực tế.

## 8. Giới hạn thời gian truy vấn và tài nguyên database

Một request có thể nhỏ nhưng query rất đắt do thiếu index, join lớn, sort phức tạp hoặc lock chờ lâu.

Nên kết hợp:

- Index cho filter/sort phổ biến.
- Query timeout ở tầng JPA/provider hoặc database.
- Statement timeout ở database nếu được hỗ trợ.
- Giới hạn số bản ghi và số điều kiện truy vấn.
- Giới hạn connection pool và concurrency.
- Theo dõi slow query và execution plan.
- Dùng transaction boundary ngắn, tránh giữ transaction trong lúc xử lý mạng.
- Không cho phép client điều khiển query tự do ngoài hợp đồng API.

Ví dụ dùng timeout hint với JPA query:

~~~java
TypedQuery<Order> query = entityManager.createQuery(
    "select o from Order o where o.status = :status",
    Order.class
);

query.setParameter("status", OrderStatus.OPEN);
query.setHint("jakarta.persistence.query.timeout", 2000);
~~~

Giá trị timeout và cách provider thực thi phụ thuộc JPA provider/database. Hãy kiểm tra cấu hình thực tế, vì một hint không được hỗ trợ có thể bị bỏ qua hoặc xử lý khác nhau.

Nếu query timeout xảy ra, phân loại lỗi theo hợp đồng API. Không biến timeout database thành 400 nếu request của client hợp lệ nhưng hệ thống không thể hoàn thành trong thời gian cho phép.

## 9. Giới hạn số request và rate limiting

Một client có thể gửi nhiều request liên tục để tiêu tốn CPU, connection và database. Rate limit kiểm soát số request trong một khoảng thời gian.

Có thể giới hạn theo:

- IP address.
- User ID hoặc principal.
- API key/client ID.
- Tenant hoặc organization.
- Endpoint group.
- Kết hợp nhiều chiều, ví dụ IP limit và user limit.

Ví dụ policy minh họa:

| Nhóm API | Giới hạn ví dụ | Lý do |
|---|---:|---|
| GET collection | 60 request/phút/user | Đọc thường xuyên nhưng có thể cache. |
| GET search đắt | 20 request/phút/user | Query phức tạp hơn. |
| POST/PATCH | 30 request/phút/user | Giảm ghi lặp hoặc tự động hóa quá mức. |
| Bulk operation | 5 request/phút/admin | Tác động lớn và cần kiểm soát. |
| Login/token | Theo policy authentication riêng | Chống brute force và lạm dụng credential. |

Đây chỉ là ví dụ. Hãy đo lưu lượng thật, SLA, khả năng backend và nhu cầu client trước khi đặt ngưỡng.

### Rate limit ở đâu?

Thường đặt ở API gateway hoặc reverse proxy để từ chối request sớm. Có thể bổ sung rate limit trong ứng dụng khi cần chính sách theo principal hoặc nghiệp vụ.

Nếu chạy nhiều instance, bộ đếm rate limit cần được chia sẻ hoặc phối hợp giữa các instance. Một bộ đếm in-memory riêng trên từng node có thể khiến tổng giới hạn thực tế cao hơn dự kiến.

Dùng token bucket, leaky bucket hoặc sliding window theo khả năng của gateway. Chọn thuật toán có hành vi phù hợp với burst traffic.

### Trả 429 Too Many Requests

Khi vượt rate limit, trả HTTP 429. Nếu có thể, cung cấp Retry-After để client biết khi nào có thể thử lại:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json
~~~

~~~json
{
  "type": "about:blank",
  "title": "Too many requests",
  "status": 429,
  "detail": "The request limit has been reached. Try again later.",
  "code": "RATE_LIMIT_EXCEEDED"
}
~~~

Client nên tôn trọng Retry-After và dùng exponential backoff có jitter khi retry. Không retry liên tục ngay sau khi nhận 429.

## 10. Giới hạn request đồng thời và hàng đợi

Rate limit theo phút không ngăn một client gửi nhiều request cùng lúc trong một burst. Cần cân nhắc concurrency limit:

- Giới hạn số request đang chạy theo user/tenant.
- Giới hạn số query đồng thời tới database.
- Đặt timeout cho request và upstream call.
- Dùng bounded queue nếu có xử lý bất đồng bộ.
- Từ chối sớm khi hệ thống quá tải thay vì xếp hàng vô hạn.
- Giới hạn bulk operation để không chiếm hết worker thread.

Nếu một endpoint gọi nhiều service ngoài, tổng thời gian chờ có thể giữ servlet thread và connection lâu. Đặt timeout ở từng dependency và có cơ chế circuit breaker phù hợp.

Không tạo một queue không giới hạn để “không mất request”. Queue tăng vô hạn có thể chuyển overload thành memory exhaustion và latency rất lớn.

## 11. Giới hạn response size và số lượng dữ liệu trả về

Một request có thể hợp lệ nhưng response vẫn quá lớn. Giới hạn response bằng cách:

- Dùng pagination cho collection.
- Đặt max page size.
- Chọn projection phù hợp.
- Hạn chế nested association.
- Dùng endpoint export/download chuyên biệt cho dữ liệu lớn.
- Stream dữ liệu khi use case yêu cầu và hạ tầng hỗ trợ.
- Đặt response timeout và giới hạn dung lượng ở gateway nếu cần.

Không nên dùng collection endpoint thông thường để tải hàng trăm nghìn record trong một response. Nếu cần export lớn, thiết kế asynchronous export job: client gửi yêu cầu, server tạo file trong background, sau đó client tải kết quả qua resource có quyền truy cập.

## 12. Kết hợp Spring Data REST với gateway và Spring Security

Các lớp kiểm soát nên phối hợp:

| Lớp | Trách nhiệm |
|---|---|
| Reverse proxy/API gateway | Body byte limit, request rate, connection limit, timeout. |
| Servlet container | Header/request constraints và kết nối. |
| Spring Security | Authentication, authorization và quota theo principal nếu tích hợp. |
| Spring Data REST configurer | Default/max page size và exposure của resource. |
| Controller/service | Allowlist filter/sort, batch size, validation và business limits. |
| Database | Index, statement timeout, query plan và connection capacity. |

Không dùng CORS làm rate limit hoặc authorization. CORS chỉ điều khiển browser cross-origin behavior. API vẫn phải xác thực, phân quyền và giới hạn tài nguyên cho mọi request trực tiếp.

Với endpoint ghi, kiểm soát cả số lượng item trong body, quyền trên từng entity, transaction size và số lần gọi. Một batch 100 item có thể phù hợp, trong khi batch 100.000 item cần workflow riêng.

## 13. Quan sát và đo lường

Không thể chọn giới hạn tốt nếu không biết request tiêu tốn bao nhiêu tài nguyên.

Theo dõi ít nhất:

- Request count theo endpoint, status và principal/tenant ở mức không lộ dữ liệu nhạy cảm.
- Request body size và response size.
- Page size, offset và sort/filter được sử dụng.
- Thời gian ở gateway, ứng dụng và database.
- Số query mỗi request và slow query.
- Số request đang chạy và độ dài queue.
- Tỷ lệ 413, 429, 503 và timeout.
- CPU, heap, garbage collection, connection pool và thread pool.

Dùng metrics và tracing để xác định endpoint nào cần giới hạn chặt hơn. Tránh ghi toàn bộ request body vào log; body có thể chứa thông tin cá nhân, credential hoặc dữ liệu nhạy cảm.

## 14. Ví dụ cấu hình page size và validation

Cấu hình Spring Data REST:

~~~java
@Configuration
class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
    }
}
~~~

DTO cho batch operation:

~~~java
public record BulkUpdateRequest(
    @NotEmpty
    @Size(max = 100)
    List<@NotNull Long> ids,

    @NotNull
    OrderStatus status
) {
}
~~~

Service cần kiểm tra quyền trên toàn bộ tập ID trước khi cập nhật:

~~~java
@Transactional
public void updateStatuses(
        BulkUpdateRequest request,
        CurrentUser user) {

    List<Order> orders = repository.findAllById(request.ids());

    if (orders.size() != request.ids().stream().distinct().count()) {
        throw new EntityNotFoundException();
    }

    authorizationService.requireCanUpdateAll(user, orders);

    for (Order order : orders) {
        order.changeStatus(request.status());
    }

    repository.saveAll(orders);
}
~~~

Đây là ví dụ minh họa. Cần xử lý ID trùng, tenant scope, trạng thái workflow và giới hạn batch theo nghiệp vụ thực tế. Không chỉ kiểm tra tổng số ID; phải xác minh mọi entity thuộc phạm vi principal được phép thao tác.

## 15. Kiểm thử giới hạn

Nên có integration test cho các biên:

1. Request body nhỏ hơn giới hạn được chấp nhận.
2. Request body vượt giới hạn bị từ chối bằng 413.
3. JSON có quá nhiều phần tử bị validation từ chối.
4. JSON lồng quá sâu bị parser/validation xử lý theo chính sách.
5. Request page size không truyền dùng default.
6. Request page size vượt max bị giới hạn hoặc từ chối theo cấu hình đã chọn.
7. Page index/offset vượt ngưỡng bị xử lý đúng nếu API có giới hạn.
8. Sort property không nằm trong allowlist bị từ chối.
9. Query timeout không giữ request vô hạn và trả lỗi theo contract.
10. Rate limit cho phép request trong quota.
11. Request vượt quota nhận 429 và Retry-After phù hợp.
12. Concurrency limit không tạo queue vô hạn.
13. Bulk operation vượt số item tối đa bị từ chối.
14. Response collection không vượt page size và projection đã định.
15. Principal khác nhau có quota và quyền đúng theo policy.

Ví dụ kiểm thử page size:

~~~java
mockMvc.perform(get("/api/people")
        .param("size", "10000")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.page.size").value(100));
~~~

Test này giả định max page size đã cấu hình là 100 và phiên bản Spring Data REST đang dùng giới hạn request size theo cấu hình đó. Hãy xác nhận hành vi thực tế bằng integration test của dự án.

## 16. Những lỗi thường gặp

1. **Chỉ giới hạn page size.** Body, query cost, request rate và concurrency vẫn có thể không giới hạn.
2. **Nhầm multipart limit với JSON body limit.** Cấu hình upload file không phải giới hạn tổng quát cho application/json.
3. **Chỉ kiểm tra Content-Length.** Request chunked hoặc thiếu header có thể cần giới hạn khi đọc stream.
4. **Đặt page size rất lớn để giảm số request.** Điều đó có thể tăng memory, query cost và response serialization.
5. **Bỏ qua deep offset.** Page size nhỏ không làm page index rất lớn trở nên rẻ.
6. **Cho sort theo mọi property.** Có thể tạo query plan đắt hoặc expose trường không nên tìm kiếm.
7. **Không giới hạn nested association.** Một trang nhỏ vẫn có thể tạo response lớn và N+1 query.
8. **Chỉ rate limit theo IP.** User sau proxy hoặc nhiều user chung IP có thể bị áp quota sai; cân nhắc principal/API key/tenant.
9. **Dùng bộ đếm in-memory trên nhiều instance.** Mỗi node có thể áp giới hạn riêng và tổng quota bị vượt.
10. **Retry ngay sau 429.** Có thể tạo thêm burst; hãy tôn trọng Retry-After và backoff.
11. **Queue request không giới hạn.** Queue lớn làm tăng memory và latency.
12. **Dùng validation thay cho authorization.** Một ID hợp lệ vẫn có thể thuộc tenant khác.
13. **Ghi toàn bộ request body vào log.** Có thể làm lộ dữ liệu nhạy cảm và tăng chi phí lưu trữ.
14. **Không đo response size.** Projection và association có thể làm response lớn hơn dự kiến.
15. **Không phân biệt lỗi 413, 429 và timeout.** Client cần biết nên giảm payload, chờ quota hay xử lý lỗi hệ thống.
16. **Dùng một giới hạn cho mọi endpoint.** Search, CRUD, upload và bulk operation có đặc tính tài nguyên khác nhau.

## 17. Checklist triển khai

- Đặt default và max page size cho Spring Data REST.
- Đánh giá giới hạn deep offset hoặc dùng cursor/keyset khi phù hợp.
- Allowlist sort/filter và giới hạn số điều kiện query.
- Đặt body byte limit tại gateway/proxy và kiểm soát stream nếu cần.
- Phân biệt giới hạn JSON với multipart upload.
- Giới hạn số phần tử, chuỗi và độ sâu JSON.
- Dùng DTO allowlist cho batch input.
- Giới hạn nested association và response size.
- Đặt query/statement timeout và theo dõi slow query.
- Thiết kế index cho filter/sort phổ biến.
- Áp rate limit theo principal/API key/tenant và IP phù hợp.
- Chia sẻ rate-limit state giữa các application instance.
- Giới hạn request đồng thời và queue.
- Trả 413 cho payload quá lớn và 429 cho vượt quota.
- Cung cấp Retry-After khi phù hợp.
- Theo dõi request/response bytes, latency, query count và error rate.
- Kiểm thử các ngưỡng ngay dưới, bằng và vượt giới hạn.
- Không log payload nhạy cảm hoặc dựa vào UI để bảo vệ tài nguyên.

## Tóm tắt

Bảo vệ hiệu năng của Spring Data REST cần giới hạn cả input, query, response và tốc độ request. Dùng default/max page size để kiểm soát collection; giới hạn deep offset, sort/filter và thời gian query để tránh truy vấn đắt; đặt body byte limit và giới hạn cấu trúc JSON; dùng rate limit và concurrency limit để bảo vệ hệ thống khỏi burst traffic.

Spring Data REST configurer chỉ giải quyết một phần, ví dụ page size và exposure. Body limit thường cần gateway, proxy, container hoặc bounded request handling; query cost cần service/repository/database controls; rate limit cần gateway hoặc cơ chế chia sẻ giữa các instance. Trả 413 khi payload quá lớn, 429 khi vượt quota và giữ status/error contract rõ ràng.

Hãy đo request/response size, query time, query count và concurrency trước khi chọn ngưỡng. Kiểm thử các giá trị sát giới hạn và xác nhận request bị từ chối không tạo side effect hoặc tiêu tốn tài nguyên không kiểm soát.

## Tài liệu tham khảo

- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Servlet Web Server](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Cloud Gateway — Request Rate Limiting](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html)
- [RFC 9110 — HTTP Semantics: 413 and 429](https://www.rfc-editor.org/rfc/rfc9110)
