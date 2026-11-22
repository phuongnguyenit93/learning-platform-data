# Không dùng 404 để tạo enumeration không chủ ý

API thường trả `404 Not Found` khi resource không tồn tại. Trong một số hệ thống, server cũng trả `404` khi resource có tồn tại nhưng caller không được phép biết về nó. Cách che giấu này có thể giảm khả năng dò tìm dữ liệu giữa user hoặc tenant. Tuy nhiên, nếu API dùng `404` không nhất quán hoặc để lộ khác biệt qua body, header, thời gian phản hồi, cache hay endpoint khác, response vẫn trở thành một oracle giúp attacker xác định resource nào tồn tại.

Enumeration là việc thu thập hoặc suy ra danh sách tài khoản, resource, mã đơn hàng, tenant hay định danh hợp lệ bằng cách thử nhiều giá trị và quan sát phản hồi. Mục tiêu không chỉ là tránh trả `200` cho người không có quyền. API cần tránh tạo ra tín hiệu phân biệt giữa “không tồn tại” và “có tồn tại nhưng không được xem” khi chính sách yêu cầu che giấu sự tồn tại.

`404` là một mã HTTP hợp lệ và đôi khi là lựa chọn phù hợp để che resource. Nhưng nó không tự tạo ra bảo mật. Chỉ dùng `404` ở một endpoint trong khi endpoint khác trả `403`, thông báo khác, kích thước body khác hoặc thời gian xử lý khác có thể làm lộ chính thông tin mà server muốn che.

## 1. Enumeration qua response của API

Giả sử API cung cấp:

```http
GET /api/orders/ORD-1042
Authorization: Bearer <user-token>
```

Attacker thử nhiều mã đơn hàng. Nếu server phản hồi:

| Trường hợp | Response |
|---|---|
| `ORD-1042` tồn tại và thuộc user | `200 OK` |
| `ORD-1043` tồn tại nhưng thuộc tenant khác | `403 Forbidden` |
| `ORD-1044` không tồn tại | `404 Not Found` |

Attacker có thể xác định `ORD-1043` là một đơn hàng có thật dù không đọc được nội dung. Từ đó họ có thể lập danh sách resource, suy ra hoạt động của tenant khác hoặc kết hợp với các lỗ hổng khác.

Một chính sách che giấu có thể trả cùng một kết quả cho hai trường hợp cuối:

| Trường hợp | Response khi áp dụng concealment |
|---|---|
| Resource tồn tại nhưng caller không được biết | `404 Not Found` |
| Resource không tồn tại | `404 Not Found` |

Điều quan trọng là mọi tín hiệu quan sát được phải nhất quán theo cùng một chính sách, không chỉ status code.

### 1.1. Enumeration không chỉ dựa vào mã trạng thái

Attacker có thể so sánh:

- Status code: `403`, `404`, `200`, `409` hoặc `204`.
- Error code, `title`, `detail` hoặc tên exception trong response body.
- Kích thước response, số field, thứ tự field hoặc cấu trúc JSON.
- Header như `ETag`, `Last-Modified`, `Location`, `Content-Range` hoặc cache metadata.
- Thời gian phản hồi và số lần truy vấn downstream.
- Redirect, hành vi `HEAD`, `OPTIONS` hoặc conditional request.
- Số lượng phần tử, pagination total, facet, aggregate và kết quả bulk operation.
- Khác biệt khi resource được gọi qua API version, alias hoặc service khác.

Ví dụ, cả hai trường hợp đều trả `404`, nhưng body của resource bị che là `{"code":"ACCESS_DENIED"}` còn resource không tồn tại là `{"code":"NOT_FOUND"}`. Attacker vẫn phân biệt được. Tương tự, một response `404` có `ETag` hoặc `Last-Modified` trong khi response còn lại không có có thể làm lộ sự tồn tại.

### 1.2. ID khó đoán không thay thế kiểm soát enumeration

UUID hoặc public ID có entropy cao làm giảm khả năng đoán ID tuần tự, nhưng không loại bỏ enumeration. ID có thể xuất hiện trong URL, log phía client, email, webhook, tài liệu hoặc bị rò qua một endpoint khác. Khi attacker đã có một tập ID, API vẫn phải bảo vệ resource.

Không xem “ID không tuần tự” hoặc “URL khó đoán” là authorization. Mọi request vẫn cần xác minh quyền truy cập trên resource cụ thể.

## 2. Hiểu đúng 403 và 404

Theo semantics HTTP thông dụng:

- `403 Forbidden`: server hiểu request nhưng từ chối thực hiện. Caller có thể đã xác thực nhưng không có quyền.
- `404 Not Found`: server không tìm thấy representation hiện tại cho target resource, hoặc không muốn tiết lộ rằng resource đó tồn tại.

Vì vậy, dùng `404` để che resource có thể phù hợp. Tuy nhiên, không nên biến mọi lỗi authorization thành `404` một cách máy móc. Một số API cần trả `403` để client biết họ đã xác thực nhưng thiếu permission chức năng, trong khi vẫn che sự tồn tại của resource cụ thể ở bước object-level authorization.

### 2.1. Chọn chính sách theo loại quyết định

| Tình huống | Response thường phù hợp | Ghi chú bảo mật |
|---|---|---|
| Thiếu hoặc token không hợp lệ | `401 Unauthorized` | Không tiết lộ thông tin về resource phía sau |
| Thiếu permission chức năng trên endpoint | `403 Forbidden` | Có thể dùng `403` vì không nhất thiết tiết lộ resource cụ thể |
| Resource không tồn tại | `404 Not Found` | Phản hồi theo hợp đồng API |
| Resource tồn tại nhưng caller không được biết | `404` hoặc `403` theo threat model | Nếu cần che existence, phải nhất quán với trường hợp không tồn tại |
| Request sai cú pháp hoặc ID sai định dạng | `400 Bad Request` hoặc `404` theo hợp đồng | Không để validation phản ánh sự tồn tại của ID |
| Method không được hỗ trợ | `405 Method Not Allowed` | Không nhầm với thiếu permission trên method được hỗ trợ |
| Trạng thái nghiệp vụ xung đột | `409 Conflict` | Tránh trả thông tin trạng thái riêng tư cho caller không có quyền |

Không có một bảng status áp dụng cứng cho mọi API. Cần xác định threat model, thông tin mà client được phép biết và semantics hợp đồng. Quan trọng nhất là cùng một quyết định phải có hành vi nhất quán trên mọi đường truy cập.

### 2.2. Phân biệt function authorization và object authorization

Có thể trả `403` khi caller thiếu quyền gọi chức năng nói chung, nhưng trả `404` khi resource cụ thể không tồn tại hoặc nằm ngoài phạm vi được biết.

Ví dụ:

1. User không có `orders:read` gọi endpoint danh sách đơn: trả `403`.
2. User có `orders:read` nhưng yêu cầu một ID ngoài tenant: trả `404` theo concealment policy.
3. User có `orders:read` và resource thuộc tenant: trả `200` nếu các kiểm tra khác đạt.

Cách phân lớp này giữ thông tin permission chức năng rõ ràng cho client, đồng thời tránh xác nhận sự tồn tại của resource ngoài phạm vi. Hãy áp dụng thống nhất cho GET, PATCH, DELETE, export, nested resource và các API khác cùng dữ liệu.

## 3. Thiết kế concealment policy rõ ràng

Trước khi triển khai `404` cho resource bị cấm truy cập, hãy quyết định:

- Loại resource nào cần che giấu sự tồn tại?
- Những principal nào được biết resource tồn tại?
- Có vai trò hỗ trợ hoặc kiểm toán được phép nhận `403`/metadata chi tiết không?
- Policy áp dụng cho endpoint nào, method nào và API version nào?
- Có endpoint phụ nào trả cùng resource hoặc metadata theo cách khác không?
- Client có cần phân biệt “không tồn tại” và “không được phép” cho một use case hợp lệ không?
- Những tín hiệu nào được phép công bố, ví dụ mã lỗi chung hoặc correlation ID?

Chính sách nên được ghi trong contract/API design và triển khai gần nơi quyết định object authorization. Tránh để từng controller tự chọn `403` hoặc `404` theo cách riêng.

### 3.1. Không dùng concealment để thay authorization

Trả `404` không có nghĩa server có thể bỏ qua việc kiểm tra quyền. Server vẫn phải xác minh principal, permission chức năng, tenant, quan hệ sở hữu và điều kiện nghiệp vụ trước khi đọc hoặc thay đổi dữ liệu.

Không thực hiện thao tác rồi mới trả `404`. Ví dụ, không cập nhật một đơn hàng ngoài tenant rồi che kết quả bằng response `404`. Quyết định truy cập phải xảy ra trước mọi side effect.

### 3.2. Không che mọi lỗi thành 404

Nếu mọi lỗi đều trở thành `404`, client có thể không biết request sai cú pháp, token hết hạn, thiếu scope hay server đang lỗi. Điều này làm khó vận hành và có thể che giấu lỗi cấu hình nghiêm trọng.

Giữ các lớp lỗi có ý nghĩa khi chúng không tiết lộ thông tin cần che. Có thể trả `401` cho authentication, `403` cho thiếu function permission và `404` cho resource không được phép biết. Lỗi hệ thống như database unavailable vẫn cần được xử lý theo error contract, thường là `5xx`, mà không làm lộ chi tiết nội bộ.

## 4. Thực hiện truy vấn theo tenant và quyền truy cập

Một cách giảm cả rủi ro BOLA lẫn enumeration là truy vấn resource trong phạm vi caller được phép thay vì tải bản ghi toàn cục rồi trả các lỗi khác nhau.

Ví dụ truy vấn an toàn hơn:

```java
public OrderView getOrder(UUID orderId, AuthenticatedActor actor) {
    authorization.requirePermission(actor, "orders:read");

    Order order = orderRepository
            .findByIdAndTenantId(orderId, actor.tenantId())
            .orElseThrow(ResourceNotFoundException::new);

    authorization.requireCanReadOrder(actor, order);
    return orderMapper.toView(order, actor);
}
```

Truy vấn minh họa:

```sql
SELECT id, tenant_id, status, total_amount, created_at
FROM orders
WHERE id = :order_id
  AND tenant_id = :tenant_id;
```

Nếu ID không tồn tại hoặc thuộc tenant khác, truy vấn scoped trả cùng kết quả rỗng. Điều này giúp tránh nhánh code dễ làm lộ existence. Tuy nhiên, nếu hệ thống có quyền chia sẻ chéo tenant, vai trò hỗ trợ hoặc quan hệ phức tạp, cần áp dụng policy tương ứng và bảo đảm mọi nhánh vẫn tuân thủ concealment policy.

Không truy vấn unrestricted trước rồi trả `403` cho tenant khác nếu chính sách yêu cầu che existence. Cũng không nhận `tenantId` từ query/body làm phạm vi truy vấn duy nhất; tenant phải lấy từ principal hoặc context đã được xác minh.

## 5. Chuẩn hóa response lỗi

Khi dùng `404` cho cả resource không tồn tại và resource bị che, response nên có cùng cấu trúc và mã lỗi công khai. Ví dụ:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/not-found",
  "title": "Resource not found",
  "status": 404,
  "code": "RESOURCE_NOT_FOUND",
  "correlationId": "req_7f3a"
}
```

Không trả `RESOURCE_EXISTS_BUT_FORBIDDEN`, `TENANT_MISMATCH`, owner ID hoặc tenant ID trong response công khai nếu những chi tiết đó cần được che.

### 5.1. Dùng một error mapper chung

Nên ánh xạ exception/domain result sang error response ở một lớp tập trung để tránh controller trả thông tin khác nhau.

```java
@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound(ResourceNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Resource not found");
        problem.setDetail("The requested resource was not found.");
        problem.setProperty("code", "RESOURCE_NOT_FOUND");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
```

Nếu cả trường hợp nonexistent và concealed đều ném cùng loại exception, handler sẽ tạo cùng response. Chi tiết nội bộ về nguyên nhân có thể ghi vào audit log được bảo vệ, nhưng không nên ghi secret hoặc dữ liệu nhạy cảm không cần thiết.

Không để message từ ORM, database hoặc exception upstream đi thẳng vào `detail`. Không tạo mã lỗi khác nhau cho hai trường hợp nếu mục tiêu là không xác nhận sự tồn tại.

## 6. Kiểm soát side channel ngoài body

Ngay cả khi status và body giống nhau, những khác biệt khác có thể làm lộ thông tin.

### 6.1. Thời gian phản hồi

Nếu resource tồn tại, server tải bản ghi, kiểm tra owner và sau đó trả `404`; nếu không tồn tại, server trả ngay sau một truy vấn index. Attacker có thể gửi nhiều lần và so sánh latency để suy ra resource có tồn tại hay không.

Không phải lúc nào cũng cần cố làm thời gian tuyệt đối giống nhau; điều đó thường khó trong hệ thống phân tán. Nhưng cần tránh khác biệt lớn và ổn định do nhánh xử lý riêng. Truy vấn scoped, response mapper chung và tránh gọi downstream không cần thiết giúp giảm tín hiệu.

Không thêm delay ngẫu nhiên tùy tiện cho mọi response như một giải pháp duy nhất. Delay có thể làm tăng nguy cơ DoS và không loại bỏ được thống kê timing qua nhiều mẫu.

### 6.2. Header và metadata

Kiểm tra `ETag`, `Last-Modified`, `Content-Length`, `Location`, `Content-Range`, cache status và custom header. Không phát hành ETag hoặc timestamp chỉ khi resource thực sự tồn tại nếu response đang cố che existence.

`HEAD` phải tuân theo cùng quyền và concealment policy với `GET`; việc không trả body không có nghĩa request an toàn. Conditional request dùng `If-None-Match` hoặc `If-Modified-Since` cũng không được trở thành oracle xác nhận resource.

### 6.3. Cache và shared proxy

Response phụ thuộc principal hoặc tenant không được cache theo URL đơn thuần ở shared cache. Với response `404` có thể khác theo quyền của caller, cấu hình cache phải tránh việc một user nhận kết quả đã được tạo trong ngữ cảnh user khác.

Với response nhạy cảm hoặc phụ thuộc authorization, cân nhắc `Cache-Control: private` hoặc `no-store` theo nhu cầu. Một số cache có thể lưu `404` theo heuristic; hãy cấu hình rõ TTL hoặc cấm cache cho response cần concealment. Không dựa vào cache mặc định để bảo vệ thông tin.

## 7. Enumeration qua collection, search và pagination

Không chỉ endpoint lấy một resource theo ID mới có nguy cơ enumeration. Endpoint danh sách có thể làm lộ số lượng hoặc sự tồn tại của dữ liệu ngoài tenant qua:

- `totalElements`, `totalCount` hoặc tổng số trang.
- Facet/filter count và aggregation.
- Search suggestion hoặc autocomplete.
- Export file, báo cáo và analytics.
- Cursor token có thể đoán hoặc sửa.
- Bulk lookup trả từng ID với trạng thái tồn tại khác nhau.
- Thông báo “email đã đăng ký” hoặc “username chưa tồn tại” trong flow tài khoản.

Mọi query phải áp dụng tenant/authorization filter trước khi tính count, aggregation hoặc pagination. Không lấy tổng số toàn hệ thống rồi chỉ lọc các phần tử trong response; metadata tổng vẫn có thể làm lộ dữ liệu.

Với bulk endpoint, cần quyết định có cho caller biết kết quả từng ID hay không. Nếu không, dùng kết quả tổng quát cho item không tồn tại hoặc ngoài phạm vi. Nếu nghiệp vụ cần báo lỗi từng item cho operator có quyền, policy phải xác định rõ role và phạm vi được phép nhận thông tin đó.

### 7.1. Tránh account enumeration

Các endpoint đăng nhập, đăng ký, reset password, mời thành viên và xác minh email thường vô tình tiết lộ tài khoản tồn tại.

Ví dụ response không an toàn:

```json
{"message":"Email này đã được đăng ký"}
```

Trong khi email chưa tồn tại trả:

```json
{"message":"Có thể sử dụng email này"}
```

Kẻ tấn công có thể thu thập danh sách tài khoản. Với flow phù hợp, dùng thông báo trung tính như “Nếu địa chỉ này hợp lệ, chúng tôi sẽ gửi hướng dẫn tiếp theo”. Các bước xác minh tiếp theo được thực hiện qua kênh riêng.

Không phải mọi API đều phải che trạng thái tài khoản. Một operator hoặc user có quyền quản trị có thể cần thông tin cụ thể. Khi đó, cung cấp qua endpoint được bảo vệ với authorization rõ ràng thay vì làm lộ cho mọi caller.

## 8. Đồng bộ concealment trên mọi method và API version

Nếu `GET /orders/{id}` che resource ngoài tenant nhưng `PATCH /orders/{id}` trả `403`, attacker vẫn có thể dùng method ghi để kiểm tra existence. Cần áp dụng policy nhất quán cho:

- `GET`, `HEAD`, `PATCH`, `PUT`, `DELETE` và command endpoint.
- Nested route như `/orders/{id}/payments` hoặc `/users/{id}/roles`.
- API version cũ và mới.
- GraphQL resolver, gRPC method và message consumer.
- Export, search, report, webhook callback và internal API.

Không nhất thiết mọi endpoint phải trả cùng status code. Function permission có thể trả `403`; object-level concealment có thể trả `404`. Nhưng cùng một loại quyết định phải được xử lý nhất quán trên các method và đường truy cập.

Với GraphQL, không chỉ kiểm tra HTTP status vì lỗi authorization có thể xuất hiện trong `errors` hoặc field trả `null`. Resolver cần tránh khác biệt có thể tiết lộ resource. Với gRPC, `NOT_FOUND` và `PERMISSION_DENIED` cũng cần được chọn theo cùng threat model.

## 9. Rate limit và phát hiện enumeration

Rate limit không thay thế concealment hoặc authorization, nhưng giúp giảm tốc độ dò tìm và tăng khả năng phát hiện.

Có thể kết hợp:

- Giới hạn theo principal, API key, client, tenant và IP.
- Giới hạn riêng cho endpoint lookup, login, reset password và bulk query.
- Giới hạn số ID trong một batch và độ rộng search.
- Giới hạn concurrency và query cost.
- Backoff hoặc challenge khi có hành vi bất thường.
- Alert khi một principal thử nhiều ID không liên quan hoặc có tỷ lệ not-found tăng đột biến.

Không chỉ rate limit theo IP vì nhiều user có thể dùng chung NAT/proxy và attacker có thể phân tán request qua nhiều IP. Cũng không khóa tài khoản ngay khi có nhiều `404`, vì attacker có thể dùng điều đó để gây từ chối dịch vụ cho user khác.

Metric nên dùng route template và mã kết quả tổng quát, không đưa raw resource ID hoặc email vào label có cardinality cao. Log chi tiết cần giới hạn quyền truy cập và retention.

## 10. Audit mà không làm lộ thêm thông tin

Server có thể cần phân biệt nội bộ giữa:

- Resource không tồn tại.
- Resource tồn tại nhưng nằm ngoài tenant.
- Caller thiếu quyền trên object.
- ID sai định dạng hoặc bị từ chối bởi policy.

Thông tin này hữu ích cho điều tra và vận hành nhưng không nên đưa nguyên vẹn vào response công khai. Ghi audit event với principal, route, action, tenant context đã xác minh, resource reference ở dạng được phép, decision code và correlation ID.

Không ghi toàn bộ dữ liệu resource, token hoặc secret chỉ để điều tra enumeration. Với dữ liệu cá nhân, có thể dùng identifier nội bộ hoặc hash có kiểm soát theo chính sách log.

Theo dõi:

- Tỷ lệ `404` theo principal/route và mức tăng đột biến.
- Nhiều ID liên tiếp hoặc ID có pattern tuần tự.
- Một client thử resource trên nhiều tenant.
- Khác biệt bất thường giữa `GET`, `HEAD`, `PATCH` và `DELETE`.
- Nhiều request reset password hoặc lookup account.
- Tỷ lệ batch item không tìm thấy hoặc ngoài phạm vi.

## 11. Ma trận kiểm thử chống enumeration

Test phải so sánh phản hồi của resource không tồn tại với resource tồn tại nhưng caller không được biết. Không chỉ assert status code; cần kiểm tra body, header, cache, timing ở mức thống kê và side effect.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Resource thuộc caller | Được truy cập theo permission và business rule |
| Resource không tồn tại | `404` theo contract |
| Resource thuộc tenant khác, concealment bật | Response quan sát được tương đương trường hợp không tồn tại |
| Resource thuộc tenant khác, policy cho phép tiết lộ | `403` nhất quán theo contract và chỉ với caller phù hợp |
| Thiếu function permission | `403` hoặc policy đã công bố; không truy vấn resource ngoài phạm vi không cần thiết |
| ID sai định dạng | Response không cho biết ID tương ứng có tồn tại |
| GET so với HEAD | Không có khác biệt metadata làm lộ existence |
| GET so với PATCH/DELETE | Không thể dùng method khác để dò existence |
| Conditional request | ETag/304 không tiết lộ resource bị che |
| Error body | Cùng code/title/detail cho hai trường hợp cần conceal |
| Response headers | Không có ETag, Last-Modified hoặc header riêng chỉ xuất hiện khi tồn tại |
| Timing | Không có chênh lệch lớn, ổn định tạo oracle dễ khai thác |
| Collection count/facet | Chỉ tính trên dữ liệu caller được phép thấy |
| Bulk lookup | Không trả existence từng ID ngoài phạm vi nếu policy cấm |
| Account reset/register | Response trung tính không xác nhận email có tài khoản |
| Cache/shared proxy | Không rò response giữa principal hoặc tenant |
| API version/alias | Cùng concealment policy trên mọi version và route |
| GraphQL/gRPC | Field/error/status không làm lộ existence ngoài policy |
| Rate limit | Hành vi dò nhiều ID bị giới hạn và ghi nhận |

Một test integration hữu ích tạo hai resource: một resource không tồn tại và một resource tồn tại ở tenant khác. Gửi request bằng cùng principal, cùng method và cùng cấu hình; so sánh status, body schema, header và cache directive. Có thể đo nhiều lần để phát hiện chênh lệch timing đáng kể, nhưng không yêu cầu thời gian tuyệt đối bằng nhau.

## 12. Checklist thiết kế response chống enumeration

- [ ] Đã xác định resource/identity nào cần che giấu sự tồn tại.
- [ ] Có chính sách rõ ràng khi dùng `403` và khi dùng `404`.
- [ ] Resource ngoài phạm vi và resource không tồn tại có response tương đương khi concealment được yêu cầu.
- [ ] Function authorization và object authorization được tách biệt.
- [ ] Query được giới hạn theo tenant/owner trước khi đọc dữ liệu.
- [ ] Không trả error code, message hoặc field tiết lộ owner/tenant/resource existence.
- [ ] Header, ETag, Last-Modified, redirect và `HEAD` tuân thủ cùng policy.
- [ ] Timing và số lần gọi downstream không tạo side channel rõ ràng.
- [ ] Collection, count, facet, search, export và bulk API chỉ xử lý dữ liệu được phép.
- [ ] Account lookup/reset/register dùng response trung tính khi cần chống account enumeration.
- [ ] Cache không chia sẻ response phụ thuộc quyền giữa principal/tenant.
- [ ] Policy nhất quán trên mọi method, nested route, version và giao thức.
- [ ] Rate limit và monitoring hỗ trợ phát hiện hành vi dò tìm.
- [ ] Audit phân biệt nguyên nhân nội bộ mà không làm lộ thông tin qua response.
- [ ] Có test so sánh resource nonexistent với resource concealed.

## 13. Nguyên tắc thiết kế

`404` có thể được dùng để che giấu resource mà caller không được biết, nhưng chỉ hiệu quả khi được áp dụng nhất quán. Nếu resource không tồn tại trả `404` còn resource tồn tại nhưng bị cấm trả `403`, khác biệt đó tạo ra một oracle. Nếu status giống nhau nhưng body, header, timing, cache hoặc endpoint phụ khác nhau, enumeration vẫn có thể xảy ra.

Hãy xác định rõ khi nào cần `403` và khi nào cần concealment bằng `404`; truy vấn resource trong tenant scope; dùng error mapper thống nhất; kiểm soát metadata, cache, collection và bulk response; áp dụng rate limit và audit. Không biến mọi lỗi thành `404` để che vấn đề vận hành, và không dùng ID khó đoán thay cho authorization. **Mục tiêu là để caller chỉ biết resource tồn tại khi policy cho phép họ biết, trên mọi đường truy cập của API.**
