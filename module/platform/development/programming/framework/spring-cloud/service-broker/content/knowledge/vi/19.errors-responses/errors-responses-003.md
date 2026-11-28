# Lỗi yêu cầu 400, xung đột 409 và điều kiện phiên bản 412

Trong module **SPRING_CLOUD_SERVICE_BROKER**, broker tiếp nhận request từ platform để đọc catalog, provision service instance, update cấu hình, tạo binding hoặc thu hồi tài nguyên. Khi request không thể xử lý, HTTP status và error body phải cho platform biết vấn đề thuộc dữ liệu đầu vào, trạng thái tài nguyên hay điều kiện giao thức. Phân loại sai khiến platform retry một lỗi vĩnh viễn, bỏ qua một xung đột cần xử lý hoặc gửi request theo phiên bản API mà broker không hỗ trợ.

Ba mã trong bài này có vai trò khác nhau:

- **400 Bad Request:** request không hợp lệ về cú pháp hoặc cấu trúc, thiếu dữ liệu bắt buộc hay chứa giá trị không đáp ứng hợp đồng đầu vào.
- **409 Conflict:** request có thể hợp lệ về cấu trúc nhưng không thể áp dụng vào trạng thái tài nguyên hiện tại, hoặc định danh đã được dùng cho một ý định khác.
- **412 Precondition Failed:** điều kiện tiên quyết của request không được đáp ứng. Trong OSB API, trường hợp quan trọng là phiên bản broker API được platform gửi qua header không được broker hỗ trợ.

Các mã này không phải nhãn tùy chọn. Broker cần ánh xạ chúng từ lỗi ở tầng HTTP, domain, persistence và provider theo một chính sách nhất quán. Error response phải đủ rõ để platform hoặc operator khắc phục, đồng thời không tiết lộ credential, dữ liệu tenant khác hoặc chi tiết nội bộ nhạy cảm.

## 1. Đọc status code theo nguyên nhân

Status code mô tả kết quả của request ở góc nhìn HTTP. Error body bổ sung thông tin có thể đọc được. Broker nên xác định nguyên nhân trước rồi mới chọn status.

| Status | Nhóm nguyên nhân | Ví dụ trong service broker |
|---|---|---|
| **400 Bad Request** | Request không đáp ứng cú pháp hoặc schema | JSON lỗi, thiếu service_id, parameters sai kiểu |
| **409 Conflict** | Trạng thái hiện tại không cho phép áp dụng request | Instance ID đã gắn với plan khác, binding đang được tạo, update xung đột |
| **412 Precondition Failed** | Điều kiện tiên quyết của request không thỏa | X-Broker-API-Version không nằm trong dải broker hỗ trợ |
| 401 Unauthorized | Caller chưa được xác thực | Thiếu hoặc sai thông tin xác thực platform |
| 403 Forbidden | Caller đã xác thực nhưng không có quyền | Tenant không được phép thao tác instance |
| 404 Not Found | Resource hoặc route không tồn tại theo hợp đồng | Instance/binding không được tìm thấy |
| 422 Unprocessable Entity | Request hợp lệ nhưng không thể xử lý theo quy tắc nghiệp vụ/giao thức | Async bắt buộc nhưng platform không gửi accepts_incomplete |
| 500 Internal Server Error | Lỗi không dự kiến trong broker | Bug, lỗi dữ liệu nội bộ |
| 502/503/504 | Lỗi giao tiếp hoặc khả năng phục vụ phụ thuộc hạ tầng | Provider gateway lỗi, broker/service phụ thuộc không sẵn sàng, timeout |

Bảng trên là định hướng phân loại. Endpoint cụ thể và phiên bản OSB API có thể quy định response chi tiết hơn. Broker cần đối chiếu hợp đồng của từng endpoint, tránh dùng một status duy nhất cho mọi exception.

Một quy tắc hữu ích:

- Nếu sửa request là đủ để gửi lại, thường xem xét 400.
- Nếu cần giải quyết trạng thái hoặc yêu cầu đang tồn tại, xem xét 409.
- Nếu caller phải đáp ứng một precondition của giao thức trước khi request được chấp nhận, xem xét 412.

Không dùng 400 cho mọi lỗi chỉ vì request thất bại. Không dùng 409 để báo mọi retry. Không dùng 412 cho mọi xung đột version nội bộ nếu hợp đồng endpoint không định nghĩa precondition đó.

## 2. Cấu trúc error response trong OSB API

OSB API dùng JSON error response với trường mô tả lỗi. Một response thường có dạng:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

~~~json
{
  "description": "The parameters.storage_gb value must be an integer."
}
~~~

Trường description nên ngắn gọn, có thể hành động và không chứa dữ liệu nhạy cảm. Platform có thể hiển thị mô tả cho operator hoặc ghi vào log. Vì vậy, nội dung phải tránh:

- Password, token, private key hoặc connection string.
- Raw provider response có thể chứa thông tin hạ tầng.
- SQL statement, stack trace hoặc tên class nội bộ.
- Dữ liệu cá nhân hoặc metadata của tenant khác.
- Thông tin xác thực trong query string.

Broker có thể lưu error code nội bộ, correlation ID và nguyên nhân chi tiết trong log có kiểm soát. Error body công khai chỉ nên chứa phần mô tả phù hợp với contract OSB API.

Không tự ý thêm nhiều field tùy chỉnh vào response nếu platform không hỗ trợ. Nếu cần mã lỗi ổn định cho quan sát nội bộ, có thể lưu trong structured log hoặc error catalog. Khi response contract chỉ quy định description, hãy trả đúng cấu trúc đó.

## 3. HTTP 400: request không hợp lệ

400 phù hợp khi broker không thể hiểu hoặc chấp nhận request do nội dung đầu vào không đáp ứng hợp đồng.

Các trường hợp thường gặp:

- Body không phải JSON hợp lệ.
- Content-Type không phù hợp với endpoint.
- Thiếu field bắt buộc theo request schema.
- Field có kiểu dữ liệu sai, ví dụ storage_gb là chuỗi thay vì integer.
- Giá trị nằm ngoài giới hạn schema.
- Query parameter có định dạng sai.
- Path parameter rỗng hoặc không đáp ứng quy tắc định danh.
- Request body có cấu trúc không được hỗ trợ theo phiên bản API.

Ví dụ JSON sai cú pháp:

~~~http
PUT /v2/service_instances/instance-7f3a
Content-Type: application/json
~~~

~~~text
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
~~~

Broker không parse được body nên trả 400. Không nên cố đoán ý định hoặc tự sửa JSON không hợp lệ.

### 3.1. Thiếu field bắt buộc

Ví dụ request provision thiếu plan_id:

~~~json
{
  "service_id": "service-postgresql",
  "parameters": {
    "storage_gb": 100
  }
}
~~~

Nếu endpoint và phiên bản OSB API yêu cầu plan_id, broker trả 400 với mô tả rõ field bị thiếu. Không tự chọn plan mặc định trừ khi contract sản phẩm đã định nghĩa hành vi đó và request hợp lệ theo đặc tả.

### 3.2. Sai kiểu hoặc vượt schema

Giả sử schema yêu cầu storage_gb là integer từ 10 đến 500:

~~~json
{
  "storage_gb": "100"
}
~~~

Giá trị là string, không phải integer. Broker không nên âm thầm ép kiểu nếu việc đó làm thay đổi contract hoặc khiến client không phát hiện lỗi serialization.

Một ví dụ khác:

~~~json
{
  "storage_gb": 900
}
~~~

Kiểu dữ liệu đúng nhưng vượt maximum. Đây vẫn là lỗi đầu vào theo schema và có thể được biểu diễn bằng 400 theo contract endpoint. Nếu lỗi liên quan đến quota động của tenant hoặc capacity hiện tại, cần phân biệt với schema maximum cố định; đó có thể là lỗi nghiệp vụ hoặc xung đột trạng thái khác.

### 3.3. Lỗi cú pháp khác lỗi nghiệp vụ

Cần phân biệt:

- JSON không parse được: lỗi cú pháp.
- JSON parse được nhưng sai schema: lỗi cấu trúc đầu vào.
- Schema hợp lệ nhưng tenant hết quota: lỗi chính sách động.
- Schema hợp lệ nhưng instance đang migration: lỗi trạng thái.
- Schema hợp lệ nhưng provider tạm thời không sẵn sàng: lỗi phụ thuộc hạ tầng.

Không gom các trường hợp này vào một exception chung. Việc phân loại rõ giúp platform biết có nên yêu cầu người dùng sửa input, chờ operation hay retry sau.

## 4. HTTP 409: xung đột với trạng thái hiện tại

409 phù hợp khi request không thể được áp dụng vì trạng thái tài nguyên hoặc một thao tác khác đang tồn tại tạo ra xung đột.

Ví dụ:

- Instance ID đã được dùng cho service hoặc plan khác.
- Binding ID đã được liên kết với consumer hoặc parameters khác.
- Instance đang có update/deprovision operation chưa hoàn tất.
- Một thao tác không tương thích đang chạy trên cùng resource.
- Bản ghi đã thay đổi sau khi client đọc trạng thái trước đó.
- Quy tắc lifecycle không cho phép chuyển từ trạng thái hiện tại sang trạng thái đích.

409 không có nghĩa request JSON sai. Request có thể hoàn toàn hợp lệ nhưng thời điểm hoặc trạng thái áp dụng không phù hợp.

### 4.1. Cùng resource ID nhưng ý định khác

Giả sử instance-7f3a đã được provision với plan-standard. Một request mới dùng cùng instance ID nhưng yêu cầu service khác hoặc plan khác. Đây không phải retry của cùng request.

Broker cần so sánh service ID, plan ID và các dữ liệu có ý nghĩa với reservation đã lưu. Nếu ý định khác với resource đã tồn tại, trả conflict thay vì ghi đè hoặc tạo provider resource thứ hai.

Ví dụ error response:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/json
~~~

~~~json
{
  "description": "The instance identifier is already associated with a different service plan."
}
~~~

Không đưa tenant ID nội bộ hoặc cấu hình nhạy cảm của instance hiện có vào mô tả.

### 4.2. Operation đang chạy

Một instance có thể đang PROVISIONING, UPDATING hoặc DEPROVISIONING. Request mới có thể xung đột với operation hiện tại.

Ví dụ, platform gửi update plan trong lúc deprovision đang chạy. Nếu broker cho phép cả hai operation chạy song song, provider có thể nhận lệnh thay đổi và xóa cùng một tài nguyên. Broker nên kiểm tra state machine và trả conflict hoặc xếp hàng theo policy.

Nếu request là retry cùng operation đang chạy và broker có thể nhận diện đúng fingerprint, hãy tiếp tục/trả lại operation hiện có theo contract. Không trả 409 cho một retry hợp lệ chỉ vì resource đang có operation; 409 phù hợp hơn khi request mới xung đột với ý định hoặc trạng thái hiện tại.

### 4.3. Binding ID đã tồn tại

Khi PUT binding được retry với cùng instance ID, binding ID và cùng nội dung, broker nên xử lý idempotently. Nếu cùng binding ID được tái sử dụng cho một consumer hoặc permission profile khác, broker cần phát hiện xung đột.

Ví dụ, billing-binding đã được tạo với role read_write. Request mới dùng lại binding ID nhưng yêu cầu role admin. Đây là thay đổi ý định và không được âm thầm ghi đè credential. Platform cần dùng quy trình phù hợp để thay đổi binding hoặc tạo binding mới.

## 5. Phân biệt retry idempotent với conflict

Một hệ thống broker cần phân biệt ba tình huống:

| Tình huống | Resource ID | Request intent | Hành vi |
|---|---|---|---|
| Retry cùng request | Giống | Giống | Trả/tiếp tục kết quả hiện có, không tạo side effect trùng |
| Request mới hợp lệ | Mới hoặc endpoint update phù hợp | Khác nhưng được phép | Thực hiện theo lifecycle và policy |
| Xung đột | Giống | Khác hoặc trạng thái không tương thích | Trả 409 hoặc lỗi phù hợp |

Ví dụ:

- PUT provision cùng instance ID, service ID, plan ID và parameters: có thể là retry.
- PUT provision cùng instance ID nhưng plan khác: conflict.
- PUT binding cùng instance ID + binding ID và cùng permission profile: retry.
- PUT binding cùng ID nhưng parameters khác: conflict.
- DELETE binding đã revoke: xử lý idempotently theo contract, không báo lỗi nội bộ chỉ vì resource đã absent nếu semantics yêu cầu coi trạng thái đích đã đạt.

Request fingerprint có thể giúp phân biệt intent. Fingerprint cần được tạo từ payload đã canonicalize, bỏ các field không ảnh hưởng nghiệp vụ như trace ID hoặc timestamp. Không đưa secret thô vào log.

## 6. HTTP 412: precondition của phiên bản OSB API

OSB API sử dụng header **X-Broker-API-Version** để platform cho biết phiên bản giao thức mà nó gửi request. Broker cần kiểm tra phiên bản đó trước khi xử lý body hoặc thực hiện side effect.

Ví dụ:

~~~http
PUT /v2/service_instances/instance-7f3a
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Nếu broker không hỗ trợ phiên bản được yêu cầu, response có thể là:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json
~~~

~~~json
{
  "description": "The requested Open Service Broker API version is not supported."
}
~~~

Đây là điều kiện tiên quyết của giao thức: platform yêu cầu broker xử lý theo một API version cụ thể nhưng broker không thể đáp ứng. Broker không nên tiếp tục xử lý request bằng cách tự hạ phiên bản hoặc bỏ qua header, vì semantics của request/response có thể khác.

### 6.1. Kiểm tra major và minor version

Broker cần parse header theo định dạng phiên bản được OSB API quy định và kiểm tra dải hỗ trợ. Không so sánh chuỗi đơn giản theo thứ tự từ điển.

Ví dụ, chuỗi "2.9" và "2.10" nếu so sánh lexical có thể cho kết quả sai. Hãy parse major/minor thành số và dùng một policy hỗ trợ rõ ràng.

Một policy có thể là:

- Chỉ hỗ trợ một tập minor version đã được kiểm thử.
- Hỗ trợ từ một minimum minor đến một maximum minor trong cùng major.
- Từ chối major version không được hỗ trợ.
- Không giả định minor version mới hơn luôn tương thích ngược nếu chưa đánh giá contract.

### 6.2. Header thiếu hoặc sai định dạng

Thiếu header và header sai định dạng cần được xử lý theo đúng contract OSB API version mà broker hỗ trợ. Không tự động coi header thiếu là phiên bản mới nhất nếu đặc tả yêu cầu platform gửi header.

Cần phân biệt:

- Header không có: request thiếu thông tin phiên bản.
- Header sai định dạng: không thể parse version.
- Header hợp lệ nhưng version không hỗ trợ: precondition không thỏa.
- Header hợp lệ và được hỗ trợ: tiếp tục validate request.

Status cụ thể cho header thiếu hoặc malformed phải theo phiên bản đặc tả và chính sách tương thích của broker; không suy luận mọi lỗi header đều là 412.

## 7. 412 không đồng nghĩa với mọi optimistic locking conflict

Trong ứng dụng, developer có thể dùng version column hoặc ETag để ngăn ghi đè dữ liệu cũ. Đây là cơ chế concurrency control của resource. Nó khác với OSB API version header.

Ví dụ một API nội bộ có thể dùng:

~~~http
PATCH /internal/instances/instance-7f3a
If-Match: "version-12"
Content-Type: application/json
~~~

Nếu resource hiện tại đã lên version 13, precondition If-Match không còn đúng. HTTP 412 có thể phù hợp cho endpoint hỗ trợ conditional request theo semantics HTTP.

Tuy nhiên, không được tự thêm If-Match vào OSB endpoint hoặc trả 412 cho mọi optimistic lock failure nếu contract OSB API không quy định. Với OSB request thông thường, xung đột trạng thái có thể cần được biểu diễn bằng 409 theo semantics của endpoint.

Cần tách ba version:

| Loại version | Mục đích | Ví dụ |
|---|---|---|
| OSB API version | Phiên bản giao thức giữa platform và broker | X-Broker-API-Version: 2.17 |
| Resource version | Phiên bản bản ghi instance/binding để concurrency control | version = 13 |
| Provider API version | Phiên bản API mà adapter gọi ở hạ tầng | Provider SDK/API release |

Không so sánh hoặc dùng một loại version thay cho loại khác.

## 8. Quy trình xử lý lỗi tại lớp HTTP

Một request nên đi qua pipeline có thứ tự:

1. Nhận request và xác định route.
2. Kiểm tra header giao thức và API version.
3. Xác thực caller.
4. Parse body/query/path.
5. Validate schema và các field bắt buộc.
6. Tải resource và kiểm tra ownership.
7. Kiểm tra state machine, idempotency và concurrency.
8. Thực hiện nghiệp vụ hoặc tạo async operation.
9. Map kết quả sang HTTP response và error body.

Một sơ đồ:

~~~mermaid
flowchart TD
    A["OSB HTTP request"] --> B["Check API version"]
    B --> C{"Version supported?"}
    C -->|No| P["412 Precondition Failed"]
    C -->|Yes| D["Authenticate caller"]
    D --> E["Parse and validate request"]
    E --> F{"Input valid?"}
    F -->|No| Q["400 Bad Request"]
    F -->|Yes| G["Load resource and check ownership"]
    G --> H["Check lifecycle state and intent"]
    H --> I{"State conflict?"}
    I -->|Yes| R["409 Conflict"]
    I -->|No| J["Execute use case"]
    J --> K["Map result or downstream failure"]
~~~

Thứ tự chi tiết có thể thay đổi theo yêu cầu bảo mật và framework, nhưng API version phải được kiểm tra trước khi diễn giải semantics của body. Không thực hiện side effect trước khi xác nhận version, authorization và request validity.

Nếu cần tránh tiết lộ sự tồn tại của resource cho caller không có quyền, có thể trả 404 thay vì phân biệt 403/409 tùy policy bảo mật. Điều này cần được áp dụng nhất quán để không tạo side channel.

## 9. Ánh xạ exception nội bộ sang HTTP status

Không nên để provider adapter tự quyết định HTTP status. Adapter nên trả lỗi có kiểu hoặc mã nguyên nhân; API boundary map chúng sang OSB response.

Một error catalog nội bộ có thể gồm:

| Exception/domain error | Nguyên nhân | Mapping gợi ý |
|---|---|---|
| MalformedRequestException | Body/query/path không parse được | 400 |
| RequestValidationException | Thiếu field hoặc sai schema | 400 |
| UnsupportedApiVersionException | OSB API version không hỗ trợ | 412 |
| InstanceRequestConflictException | Instance ID gắn với intent khác | 409 |
| BindingRequestConflictException | Binding ID gắn với cấu hình khác | 409 |
| LifecycleConflictException | Operation mới xung đột với state hiện tại | 409 |
| ResourceNotFoundException | Instance/binding không tồn tại theo contract | 404 |
| AuthorizationException | Caller không có quyền | 403 |
| AsyncRequiredException | Thao tác cần async nhưng platform không chấp nhận | 422 theo OSB contract |
| ProviderUnavailableException | Provider tạm thời không phục vụ | 502/503 tùy adapter và contract |
| UnexpectedBrokerException | Lỗi không dự kiến | 500 |

Các mapping này là policy của API boundary; cần xác minh từng trường hợp với contract endpoint OSB và phiên bản đang hỗ trợ. Không trả nguyên exception message từ provider cho platform.

## 10. Thiết kế error object có thể hành động

Một error description tốt nên trả lời:

- Field hoặc điều kiện nào không đáp ứng?
- Caller cần sửa request, chờ operation hay dùng phiên bản API khác?
- Có thể retry cùng request hay cần tạo request mới?

Ví dụ 400:

~~~json
{
  "description": "The parameters.storage_gb field must be an integer between 10 and 500."
}
~~~

Ví dụ 409:

~~~json
{
  "description": "The service instance has an update operation in progress. Retry after the current operation completes."
}
~~~

Ví dụ 412:

~~~json
{
  "description": "The requested API version is outside the broker's supported range."
}
~~~

Không nên đưa internal operation ID, database key hoặc provider host vào description nếu platform không cần. Nếu cần trace, broker có thể log correlation ID và cung cấp qua kênh hỗ trợ/observability được bảo vệ.

Tránh mô tả mơ hồ như "Invalid request", "Something went wrong" hoặc "Conflict occurred" nếu có thể đưa ra hướng khắc phục an toàn hơn.

## 11. Retry policy theo từng status

Platform và broker cần biết lỗi nào có thể retry và điều kiện retry.

| Status | Có nên retry tự động? | Điều kiện |
|---|---|---|
| 400 | Thường không | Phải sửa body hoặc query trước |
| 409 | Không retry ngay theo cùng cách | Chờ operation hiện tại hoặc giải quyết xung đột; sau đó đọc lại state |
| 412 | Không retry với cùng version | Nâng cấp/downgrade client hoặc broker để dùng version được hỗ trợ |
| 429 | Có thể | Tuân theo Retry-After/backoff nếu endpoint hỗ trợ |
| 500 | Có thể có điều kiện | Cần idempotency và xác định side effect trước khi retry |
| 502/503/504 | Thường có thể | Exponential backoff, jitter và idempotency |

Không dùng status code đơn lẻ để quyết định retry cho side effect đã bắt đầu. Ví dụ, client timeout không phải status response. Broker có thể đã tạo provider resource dù platform không nhận được response. Vì vậy request retry phải đi qua idempotency check.

Với 409 do operation đang chạy, platform có thể poll last operation thay vì gửi lại một request mới. Với 412 do API version, retry cùng header không giải quyết được nguyên nhân.

## 12. 400, 409 và 412 trong từng endpoint OSB

Cùng một status có thể xuất hiện ở nhiều endpoint, nhưng nguyên nhân phải phù hợp với semantics của endpoint.

| Endpoint/use case | 400 | 409 | 412 |
|---|---|---|---|
| GET catalog | Query/header format không hợp lệ theo contract | Hiếm; chỉ khi có state-specific contract | API version không hỗ trợ |
| PUT provision | Body thiếu/sai field hoặc parameters sai schema | Instance ID gắn với intent khác hoặc state conflict | API version không hỗ trợ |
| PATCH update | Parameters sai schema hoặc request không hợp lệ | Update xung đột operation/state hiện tại | API version không hỗ trợ |
| DELETE deprovision | Query/path không hợp lệ | Resource đang có lifecycle operation không tương thích | API version không hỗ trợ |
| PUT binding | Binding parameters sai schema | Binding ID đã tồn tại với intent khác | API version không hỗ trợ |
| DELETE unbinding | Request không hợp lệ theo contract | Binding đang có thao tác revoke khác hoặc state conflict | API version không hỗ trợ |
| GET last operation | Query operation sai định dạng | Hiếm; token/state conflict theo policy | API version không hỗ trợ |

Đây là ma trận hướng dẫn thiết kế. Không phải mọi endpoint bắt buộc phải phát cả ba status. Nếu một status không có ý nghĩa trong contract của endpoint, không tạo lỗi giả chỉ để đồng nhất bảng.

## 13. Spring Cloud Open Service Broker: phân tầng xử lý lỗi

Trong ứng dụng Spring, nên chia trách nhiệm:

| Thành phần | Trách nhiệm |
|---|---|
| HTTP/API layer | Đọc header, path, query và request body |
| Version policy | Kiểm tra X-Broker-API-Version |
| Authentication/authorization | Xác thực platform và quyền tenant/resource |
| Request validator | Kiểm tra cấu trúc và schema |
| Application service | Kiểm tra lifecycle, idempotency và domain policy |
| Repository | Phát hiện unique constraint và optimistic locking |
| Provider adapter | Gọi hạ tầng, phân loại lỗi downstream |
| Error mapper | Map exception nội bộ sang status và OSB error body |

Không nên đặt logic map status rải rác trong từng controller hoặc provider adapter. Một exception mapper tại API boundary giúp giữ response nhất quán.

Pseudocode kiểm tra API version:

~~~java
public void requireSupportedVersion(String header) {
    OsbApiVersion requested = OsbApiVersion.parse(header);

    if (!versionPolicy.supports(requested)) {
        throw new UnsupportedApiVersionException(requested);
    }
}
~~~

Pseudocode phân loại conflict:

~~~java
public ProvisionResult provision(ProvisionCommand command) {
    InstanceReservation reservation =
        instanceRepository.findById(command.instanceId());

    if (reservation != null) {
        if (!reservation.matchesIntent(command.fingerprint())) {
            throw new InstanceRequestConflictException(command.instanceId());
        }

        return provisionResultForExisting(reservation);
    }

    return provisionCoordinator.start(command);
}
~~~

Pseudocode error mapping:

~~~java
public ResponseEntity<OsbErrorResponse> map(Exception exception) {
    if (exception instanceof UnsupportedApiVersionException) {
        return response(412, "The requested API version is not supported.");
    }

    if (exception instanceof InstanceRequestConflictException) {
        return response(409, "The instance identifier conflicts with existing state.");
    }

    if (exception instanceof RequestValidationException) {
        return response(400, safeValidationMessage(exception));
    }

    return response(500, "An unexpected broker error occurred.");
}
~~~

Đây là pseudocode minh họa; Spring Cloud Open Service Broker có extension point và model response cụ thể theo phiên bản thư viện. Hãy sử dụng cơ chế exception handling/response của dependency đang dùng, không giả định các method hoặc class trong ví dụ là API cố định.

### 13.1. Không biến mọi persistence exception thành 409

Unique constraint violation có thể là conflict, nhưng cũng có thể là retry race của cùng một request. Sau khi nhận duplicate-key exception, broker nên đọc lại bản ghi trong transaction phù hợp:

- Nếu bản ghi có cùng fingerprint và trạng thái tương thích, xử lý như retry idempotent.
- Nếu bản ghi có fingerprint khác, trả conflict.
- Nếu transaction bị deadlock hoặc serialization failure, có thể retry transaction theo policy.
- Nếu database unavailable, đây là lỗi hạ tầng nội bộ, không phải 409.

Tương tự, optimistic locking exception không tự động có nghĩa client đã gửi request sai. Hãy đọc lại state và xác định đó là conflict nghiệp vụ hay lỗi concurrency có thể retry nội bộ.

## 14. Version compatibility và triển khai theo giai đoạn

Khi broker nâng cấp thư viện hoặc hỗ trợ thêm OSB API version, cần bảo đảm các instance broker trong cùng deployment có chính sách version nhất quán.

Một quy trình:

1. Xác định dải API version broker dự định hỗ trợ.
2. Kiểm tra model và endpoint của Spring dependency có đáp ứng các semantics đó không.
3. Viết contract tests cho từng version được hỗ trợ.
4. Triển khai version policy đồng nhất trên mọi replica.
5. Theo dõi request bị từ chối bằng 412 theo version và platform.
6. Chỉ bỏ hỗ trợ version cũ sau khi có kế hoạch tương thích với platform đang kết nối.

Nếu load balancer phân phối request tới các replica có dải version khác nhau, cùng một request có thể thành công ở replica này nhưng nhận 412 ở replica khác. Điều đó gây lỗi khó chẩn đoán. Version policy nên được cấu hình tập trung hoặc phát hành đồng bộ.

Không tự động nhận phiên bản chưa kiểm thử chỉ vì cấu trúc request hiện tại trông tương thích. Minor version mới có thể bổ sung field hoặc thay đổi semantics mà broker chưa hiểu.

## 15. Bảo mật trong error handling

Error response là một kênh thông tin ra bên ngoài. Cần kiểm soát nội dung để tránh lộ dữ liệu.

- Dùng message đã chuẩn hóa, không trả nguyên exception message từ provider.
- Che token, password, connection string và private key.
- Không tiết lộ resource ID hoặc tenant metadata ngoài phạm vi caller.
- Không trả stack trace hoặc SQL.
- Không dùng khác biệt message để xác nhận sự tồn tại của resource cho caller không có quyền.
- Gắn correlation ID trong log nội bộ để operator tra cứu.
- Rate limit các request sai lặp lại nếu cần bảo vệ broker.
- Ghi metric theo error category và endpoint nhưng không đưa payload nhạy cảm vào label metric.

Với 400, chỉ rõ field sai mà không phản chiếu toàn bộ giá trị nhạy cảm. Với 409, mô tả trạng thái xung đột ở mức đủ hiểu nhưng không lộ operation của tenant khác. Với 412, mô tả version được yêu cầu không được hỗ trợ và hướng dẫn platform dùng version tương thích nếu chính sách cho phép công bố dải hỗ trợ.

## 16. Kiểm thử contract cho 400, 409 và 412

Kiểm thử phải xác nhận cả status, body, side effect và khả năng retry.

| Nhóm | Test | Kết quả mong đợi |
|---|---|---|
| 400 syntax | JSON body lỗi | 400, không tạo resource/operation |
| 400 schema | Thiếu field bắt buộc | 400, description an toàn |
| 400 type | String gửi vào integer | 400, không âm thầm ép kiểu |
| 400 range | Parameters vượt schema | 400 theo contract endpoint |
| 409 provision | Cùng instance ID, fingerprint khác | 409, không tạo provider resource thứ hai |
| 409 binding | Cùng binding ID, permission profile khác | 409, không tạo credential mới |
| 409 lifecycle | Update trong lúc deprovision không tương thích | 409 hoặc hành vi tuần tự hóa đã định nghĩa |
| 409 retry | Cùng ID và cùng intent | Idempotent result, không conflict giả |
| 412 version | Header version không hỗ trợ | 412, không chạy business side effect |
| Version parse | Header sai định dạng | Error theo contract version validation |
| Provider failure | Provider timeout sau side effect | Không map mù quáng thành 400 |
| Security | Error không chứa secret/stack trace | Response đã làm sạch |
| Concurrency | Hai request cùng resource đồng thời | Một reservation; request còn lại được phân loại theo fingerprint |
| Regression | Các version được hỗ trợ | Response tương thích với từng version |

Một test integration hữu ích là gửi request provision với version không hỗ trợ rồi xác minh database không có reservation, operation hoặc provider call nào được tạo. Với 400, xác minh request bị chặn trước side effect. Với 409, xác minh resource hiện có không bị ghi đè.

## 17. Quan sát và vận hành lỗi

Broker nên theo dõi lỗi theo endpoint, status, version và nguyên nhân nội bộ.

Một số metric hữu ích:

- Số lượng 400 theo endpoint và validation category.
- Số lượng 409 theo resource state hoặc conflict category.
- Số lượng 412 theo OSB API version và platform client.
- Tỷ lệ request lỗi trên tổng request.
- Tỷ lệ retry sau 409/5xx.
- Số operation bị kẹt hoặc conflict với operation đang chạy.
- Số provider error được map thành 502/503/504.
- Số request bị từ chối do version header thiếu hoặc không hợp lệ.

Không dùng instance ID, tenant ID, binding ID hoặc error description tự do làm metric label có cardinality cao. Đưa các định danh đó vào structured log có quyền truy cập phù hợp và dùng correlation ID để nối request.

Dashboard vận hành cần phân biệt lỗi do client/platform, lỗi do state conflict và lỗi do broker/provider. Nếu tỷ lệ 400 tăng, có thể platform đang gửi payload không đúng schema. Nếu 409 tăng đột biến, có thể worker bị kẹt hoặc platform retry sai cách. Nếu 412 tăng, có thể platform nâng version trước khi broker được nâng cấp đồng bộ.

## 18. Checklist triển khai

Trước khi phát hành error handling, hãy xác nhận:

- [ ] 400 được dùng cho request syntax/schema/field không hợp lệ theo contract.
- [ ] 409 được dùng cho xung đột resource state hoặc intent, không dùng cho retry idempotent hợp lệ.
- [ ] 412 được dùng đúng cho precondition không thỏa, đặc biệt OSB API version không được hỗ trợ.
- [ ] X-Broker-API-Version được parse và kiểm tra theo major/minor, không so sánh lexical.
- [ ] Header thiếu, malformed và version unsupported được phân biệt theo contract.
- [ ] Resource version, OSB API version và provider API version không bị trộn lẫn.
- [ ] Error body theo cấu trúc OSB API và description có thể hành động.
- [ ] Error response không chứa secret, stack trace hoặc raw provider response.
- [ ] Persistence duplicate được phân biệt giữa retry cùng fingerprint và request xung đột.
- [ ] State conflict được kiểm tra trước provider side effect.
- [ ] Retry policy phù hợp từng status và có idempotency bảo vệ.
- [ ] Có contract tests cho 400, 409, 412 và các lỗi liên quan.
- [ ] Có metric/log để phân biệt client error, conflict, version mismatch và provider failure.
- [ ] Mọi replica dùng cùng version policy.
- [ ] Error mapping được tập trung tại API boundary và có tài liệu.

400, 409 và 412 đại diện cho ba câu hỏi khác nhau: request có hợp lệ không, trạng thái hiện tại có cho phép áp dụng không và điều kiện giao thức có được đáp ứng không. Khi broker phân loại lỗi theo nguyên nhân, kiểm tra API version trước side effect, phân biệt retry với conflict và trả error body an toàn, platform có thể khắc phục hoặc retry đúng cách. Đây là nền tảng để Spring Cloud Service Broker duy trì contract rõ ràng trong các workflow provision, update, binding và deprovision.
