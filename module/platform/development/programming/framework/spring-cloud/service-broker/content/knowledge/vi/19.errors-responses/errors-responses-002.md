# Ý nghĩa HTTP 200, 201, 202, 204 và 410 theo từng endpoint

Trong Open Service Broker API (OSB API), HTTP status code là một phần của hợp đồng giữa nền tảng và service broker. Cùng một mã có thể mang ý nghĩa khác nhau tùy endpoint và trạng thái thao tác. Ví dụ, `200 OK` có thể có nghĩa catalog đã được trả về, update đã hoàn tất, hoặc một DELETE đã xóa tài nguyên; `201 Created` dùng khi provision hoặc bind tạo ra tài nguyên mới; `202 Accepted` cho biết thao tác đang được xử lý bất đồng bộ; `410 Gone` được dùng trong những trường hợp tài nguyên cần xóa không còn tồn tại.

Một điểm dễ gây nhầm lẫn là `204 No Content`. Mã này hợp lệ trong HTTP nói chung khi thao tác thành công và không có response body, nhưng không phải mã thành công được OSB API v2.17 quy định cho các endpoint vòng đời được trình bày ở đây. Nền tảng OSB có thể xem các mã 2xx khác ngoài mã được đặc tả là thất bại. Vì vậy, broker cần chọn status theo đúng endpoint và trạng thái thực tế, không chỉ dựa vào ý nghĩa chung của HTTP.

Bài học này đặt các mã `200`, `201`, `202`, `204` và `410` vào từng endpoint của `SPRING_CLOUD_SERVICE_BROKER`, đồng thời giải thích cách trả response, xử lý retry, polling và tránh tạo tài nguyên mồ côi.

## 1. Vì sao phải hiểu status code theo endpoint?

Nền tảng là client của OSB API. Nó không suy luận ý định của broker từ nội dung log hoặc trạng thái nội bộ; nó quyết định bước tiếp theo dựa trên HTTP response và body theo hợp đồng giao thức.

Ví dụ:

- Khi `GET /v2/catalog` trả `200 OK`, nền tảng đọc danh sách service và plan.
- Khi `PUT /v2/service_instances/{instance_id}` trả `201 Created`, nền tảng hiểu instance mới đã được tạo.
- Khi `PATCH /v2/service_instances/{instance_id}` trả `200 OK`, nền tảng hiểu thay đổi đã được áp dụng đồng bộ.
- Khi `PUT` tạo binding trả `202 Accepted`, nền tảng bắt đầu polling endpoint `last_operation` của binding.
- Khi `DELETE` service instance trả `410 Gone`, nền tảng hiểu instance không còn tồn tại và có thể quên resource đó.

Nếu broker trả một mã không đúng hợp đồng, nền tảng có thể đánh dấu thao tác thất bại, thử lại, giữ lại resource record hoặc thực hiện orphan mitigation. Một thao tác đã thành công ở provider vẫn có thể bị nền tảng xem là thất bại nếu broker trả sai HTTP status.

## 2. Bảng ý nghĩa nhanh của năm mã

| Mã | Ý nghĩa trong OSB API | Cách hiểu vận hành |
|---|---|---|
| `200 OK` | Request được xử lý thành công theo endpoint; thường là thao tác đồng bộ hoặc kết quả đọc | Kết quả đã sẵn sàng để nền tảng sử dụng |
| `201 Created` | Provision hoặc binding mới được tạo thành công | Resource mới đã được tạo; response có thể chứa metadata, dashboard URL hoặc credentials theo endpoint |
| `202 Accepted` | Thao tác được chấp nhận và đang diễn ra bất đồng bộ | Chưa được coi là hoàn tất; nền tảng cần polling `last_operation` |
| `204 No Content` | HTTP chung: request thành công nhưng không có body | Không phải mã thành công OSB được quy định cho các endpoint trong bài; không dùng thay `200` hoặc `201` |
| `410 Gone` | Resource cần xóa không còn tồn tại; hoặc kết quả polling của một thao tác xóa bất đồng bộ đã đạt trạng thái được quên resource | Nền tảng có thể bỏ resource khỏi registry theo đúng ngữ cảnh delete |

Các mã này không thể hoán đổi tùy ý. Đặc biệt, `202` không có nghĩa tài nguyên đã sẵn sàng; `201` không phải mã cho update; `410` không phải cách trả lời chung cho mọi GET không tìm thấy; và `204` không thể thay thế response body rỗng `{}` với status `200` khi OSB yêu cầu như vậy.

## 3. `200 OK`: kết quả thành công đồng bộ hoặc đọc dữ liệu

`200 OK` thường được dùng khi broker đã hoàn tất xử lý trong thời gian của HTTP request hoặc khi endpoint trả về dữ liệu hiện có. Trong OSB API, response body phụ thuộc endpoint.

Các trường hợp tiêu biểu:

- `GET /v2/catalog`: trả catalog JSON.
- `GET /v2/service_instances/{instance_id}`: trả thông tin instance nếu catalog khai báo `instances_retrievable=true`.
- `GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}`: trả binding nếu catalog khai báo `bindings_retrievable=true`.
- `GET .../last_operation`: trả trạng thái operation như `in progress`, `succeeded` hoặc `failed`.
- `PATCH` update instance: trả `200` khi thay đổi đã được áp dụng hoặc request không tạo ra thay đổi nào.
- `DELETE` deprovision hoặc unbind: trả `200` khi tài nguyên đã được xóa đồng bộ.

Với provision và bind, `200` có ý nghĩa hẹp hơn: nó có thể được dùng cho request lặp mà resource đã tồn tại, hoàn tất và có cùng attributes/parameters như request hiện tại. Nó không thay thế `201 Created` khi broker vừa tạo resource mới.

### Response body của `200`

Không có quy tắc “mọi `200` đều phải có JSON” hoặc “mọi `200` đều body rỗng”. Ví dụ:

- Catalog và GET resource cần body chứa dữ liệu.
- Update đồng bộ và DELETE đồng bộ thường dùng body object rỗng `{}` theo đặc tả endpoint.
- `last_operation` cần body có `state`.
- Provision lặp không thay đổi có thể trả response model provision.
- Bind lặp với cùng parameters trả binding response tương ứng, bao gồm credentials nếu broker hỗ trợ tạo credentials.

Vì vậy, khi cài đặt controller hoặc response adapter, hãy xem cả status và schema body của endpoint.

## 4. `201 Created`: provision hoặc bind tạo resource mới

`201 Created` cho nền tảng biết broker đã tạo resource mới do request hiện tại. Trong OSB API v2.17, hai luồng vòng đời chính dùng mã này là provision service instance và tạo service binding.

### Provision service instance

Request:

```http
PUT /v2/service_instances/instance-42?service_id=postgres-service&plan_id=standard HTTP/1.1
X-Broker-API-Version: 2.17
Content-Type: application/json
```

```json
{
  "service_id": "postgres-service",
  "plan_id": "standard",
  "organization_guid": "org-7",
  "space_guid": "space-3",
  "parameters": {
    "storage_gb": 100
  }
}
```

Nếu database được tạo và broker đã xác nhận tài nguyên sẵn sàng đồng bộ, response là:

```http
HTTP/1.1 201 Created
Content-Type: application/json
```

```json
{
  "dashboard_url": "https://console.example.net/databases/db-42"
}
```

`201` phải phản ánh rằng instance đã được provision. Nếu provider mới chỉ tiếp nhận job hoặc tài nguyên vẫn đang khởi tạo, broker không được giả vờ hoàn tất bằng `201`; cần dùng `202` nếu request chấp nhận async và broker có hỗ trợ.

### Tạo service binding

Khi broker tạo credential mới cho một binding, response thành công đồng bộ dùng `201 Created`:

```http
HTTP/1.1 201 Created
Content-Type: application/json
```

```json
{
  "credentials": {
    "hostname": "postgres.internal.example",
    "port": 5432,
    "database": "orders",
    "username": "orders_app",
    "password": "<generated-secret>"
  }
}
```

Nền tảng dùng thông tin này để cung cấp service binding cho consumer. Broker phải bảo vệ credentials và chỉ trả chúng trong response phù hợp.

### Khi nào không dùng `201`?

- Update instance không tạo instance mới, nên dùng `200` khi đồng bộ hoặc `202` khi đang xử lý nền.
- Deprovision và unbind là thao tác xóa, dùng `200` khi hoàn tất đồng bộ hoặc `202` khi đang xóa bất đồng bộ.
- Request provision/bind lặp với cùng attributes và resource đã tồn tại có thể dùng `200` theo điều kiện đặc tả, không tạo mới lần nữa.

## 5. `202 Accepted`: request được tiếp nhận, thao tác chưa hoàn tất

`202 Accepted` là response thành công ban đầu cho thao tác bất đồng bộ. Nó có nghĩa broker đã nhận và ghi nhận công việc, không có nghĩa tài nguyên đã sẵn sàng hoặc credential đã được cấp.

OSB API yêu cầu query parameter `accepts_incomplete=true` trong request trước khi broker trả response bất đồng bộ. Nếu broker chỉ có thể xử lý một thao tác theo kiểu async nhưng request không chấp nhận async, broker phải trả `422 Unprocessable Entity` với error code `AsyncRequired`.

Ví dụ request:

```http
PUT /v2/service_instances/instance-42?service_id=postgres-service&plan_id=production&accepts_incomplete=true HTTP/1.1
X-Broker-API-Version: 2.17
Content-Type: application/json
```

Response:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json
```

```json
{
  "operation": "provision-op-42"
}
```

Nền tảng dùng operation ID để gọi `last_operation`. Broker cần lưu operation state bền vững trước khi trả `202`, vì kết nối HTTP sẽ kết thúc trong khi worker tiếp tục xử lý.

### Các thao tác có thể dùng `202`

Theo OSB API v2.17, provision, update và deprovision có cơ chế async; binding và unbinding cũng có cơ chế async khi nền tảng gửi `accepts_incomplete=true` và broker triển khai hỗ trợ tương ứng. Do đó không nên mặc định rằng binding hoặc unbinding luôn phải đồng bộ.

| Endpoint | Điều kiện async | Endpoint polling |
|---|---|---|
| `PUT /v2/service_instances/{id}` | `accepts_incomplete=true` | `/v2/service_instances/{id}/last_operation` |
| `PATCH /v2/service_instances/{id}` | `accepts_incomplete=true` | `/v2/service_instances/{id}/last_operation` |
| `DELETE /v2/service_instances/{id}` | `accepts_incomplete=true` | `/v2/service_instances/{id}/last_operation` |
| `PUT /v2/service_instances/{id}/service_bindings/{binding_id}` | `accepts_incomplete=true` | `.../service_bindings/{binding_id}/last_operation` |
| `DELETE /v2/service_instances/{id}/service_bindings/{binding_id}` | `accepts_incomplete=true` | `.../service_bindings/{binding_id}/last_operation` |

Với response `202` cho bind, broker không trả credentials trong response ban đầu. Nền tảng đợi operation thành công rồi lấy binding information theo endpoint fetch binding nếu được hỗ trợ, hoặc theo cơ chế mà phiên bản API và nền tảng sử dụng.

## 6. `204 No Content`: vì sao không dùng thay `200` trong OSB?

Theo ngữ nghĩa HTTP chung, `204 No Content` biểu thị request đã được xử lý thành công và response không có body. Điều đó có vẻ phù hợp với một số thao tác DELETE hoặc update không cần trả dữ liệu.

Tuy nhiên, OSB API quy định status code cụ thể cho từng endpoint. Bảng diễn giải phản hồi của nền tảng nêu rõ các mã thành công được hỗ trợ: `200`, `201` và `202` theo loại thao tác. Các mã 2xx khác, bao gồm `204`, được xem là response không hợp lệ/thất bại cho provision, deprovision, binding, unbinding và update.

Ví dụ không đúng:

```http
DELETE /v2/service_instances/instance-42?service_id=postgres-service&plan_id=standard HTTP/1.1
```

```http
HTTP/1.1 204 No Content
```

Dù provider đã xóa database, nền tảng OSB có thể xem response `204` là thất bại và tiếp tục giữ service instance trong registry hoặc thực hiện xử lý orphan. Cách đúng khi xóa đồng bộ là:

```http
HTTP/1.1 200 OK
Content-Type: application/json
```

```json
{}
```

Không nên chọn `204` chỉ vì body rỗng. Hãy tuân thủ status code và response body mà endpoint OSB quy định.

## 7. `410 Gone`: resource không còn tồn tại trong thao tác xóa

`410 Gone` được OSB API dùng để báo rằng service instance hoặc service binding cần xóa không tồn tại. Đây là tình huống khác với một lỗi provider tạm thời hoặc request sai cấu trúc.

### DELETE service binding

```http
DELETE /v2/service_instances/instance-42/service_bindings/binding-7?service_id=postgres-service&plan_id=standard HTTP/1.1
X-Broker-API-Version: 2.17
```

Nếu binding không tồn tại, broker trả:

```http
HTTP/1.1 410 Gone
Content-Type: application/json
```

```json
{
  "description": "Service Binding does not exist."
}
```

### DELETE service instance

Nếu instance không tồn tại:

```http
HTTP/1.1 410 Gone
Content-Type: application/json
```

```json
{
  "description": "Service Instance does not exist."
}
```

Trong cả hai trường hợp, nền tảng có thể xem mục tiêu xóa đã đạt được và quên resource đó. Đây là tính chất quan trọng giúp retry DELETE có thể kết thúc an toàn khi resource đã được xóa bởi lần gọi trước hoặc đã bị loại bỏ ngoài luồng.

### Không dùng `410` thay cho `404` ở mọi endpoint

`GET` service instance hoặc `GET` service binding khi không tìm thấy thường phải trả `404 Not Found` theo endpoint. `410` dành cho các trường hợp xóa được đặc tả và polling của thao tác xóa bất đồng bộ. Không nên dùng `410` cho catalog, update hoặc fetch chỉ vì dữ liệu không có.

## 8. `410 Gone` trên endpoint `last_operation`

`last_operation` có quy tắc riêng. Khi nền tảng polling một thao tác delete bất đồng bộ, broker có thể trả `410 Gone` để nói rằng resource đã bị xóa và nền tảng nên quên resource.

Ví dụ deprovision đang chạy:

1. Nền tảng gửi `DELETE /v2/service_instances/instance-42?...&accepts_incomplete=true`.
2. Broker trả `202 Accepted` cùng operation ID.
3. Nền tảng gọi `GET /v2/service_instances/instance-42/last_operation`.
4. Khi tài nguyên đã được thu hồi, broker có thể trả `410 Gone` theo quy tắc polling async delete.

Đối với thao tác create hoặc update, `410 Gone` trên `last_operation` không phải response hợp lệ để báo hoàn tất. Nền tảng có thể coi đó là response không hợp lệ và tiếp tục polling đến khi nhận trạng thái đúng hoặc hết thời gian polling.

Đối với binding, endpoint polling là `/v2/service_instances/{instance_id}/service_bindings/{binding_id}/last_operation`. `410` chỉ phù hợp trong ngữ cảnh unbind bất đồng bộ, không phải binding đang được tạo.

## 9. Bảng status code theo endpoint

Bảng dưới đây tóm tắt các status quan trọng trong OSB API v2.17. Những mã ngoài năm mã chính cũng được nêu khi cần để hiểu đầy đủ quyết định của broker.

| Endpoint | Thành công đồng bộ | Thành công bất đồng bộ | `410 Gone` | Ghi chú |
|---|---|---|---|---|
| `GET /v2/catalog` | `200` | Không áp dụng | Không dùng | Body là catalog |
| `PUT /v2/service_instances/{id}` provision | `201` khi tạo mới; `200` khi resource đã provision và parameters giống hệt trong điều kiện đặc tả | `202` | Không dùng cho provision | `409` nếu cùng ID nhưng attributes khác |
| `PATCH /v2/service_instances/{id}` update | `200` | `202` | Không dùng | `422` nếu thay đổi không hỗ trợ hoặc trạng thái không cho phép |
| `DELETE /v2/service_instances/{id}` deprovision | `200` | `202` | `410` nếu instance không tồn tại | `200` body `{}`; `202` có operation tùy chọn |
| `PUT /v2/service_instances/{id}/service_bindings/{binding_id}` bind | `201` khi tạo mới; `200` khi binding đã tồn tại và parameters giống hệt | `202` | Không dùng cho bind | `409` nếu cùng ID nhưng parameters khác |
| `DELETE /v2/service_instances/{id}/service_bindings/{binding_id}` unbind | `200` | `202` | `410` nếu binding không tồn tại | `200` body `{}` |
| `GET .../last_operation` instance | `200` | Không áp dụng | Chỉ cho async delete | Body có `state` |
| `GET .../service_bindings/{id}/last_operation` | `200` | Không áp dụng | Chỉ cho async unbind | Body có `state` |
| `GET /v2/service_instances/{id}` | `200` | Không áp dụng | Không dùng | `404` nếu không tồn tại hoặc provision còn chạy |
| `GET /v2/service_instances/{id}/service_bindings/{binding_id}` | `200` | Không áp dụng | Không dùng | `404` nếu binding không tồn tại hoặc bind còn chạy |

`204` không xuất hiện trong cột thành công vì OSB API không định nghĩa nó là response thành công cho các endpoint này.

## 10. Provision: phân biệt `200`, `201`, `202` và `409`

Provision dùng `PUT` vì nền tảng định danh trước service instance. Broker cần xử lý idempotency theo `instance_id` và nội dung yêu cầu.

| Tình huống | Response |
|---|---|
| Instance được tạo mới và hoàn tất đồng bộ | `201 Created` |
| Instance đã tồn tại, provision hoàn tất và parameters giống hệt request | `200 OK` trong synchronous mode theo điều kiện đặc tả |
| Instance đang được provision | `202 Accepted`, cùng operation ban đầu khi request được gửi lại |
| Cùng instance ID nhưng attributes khác | `409 Conflict` |
| Broker chỉ hỗ trợ async nhưng request không có `accepts_incomplete=true` | `422 Unprocessable Entity`, `error=AsyncRequired` |

Không trả `201` cho request retry nếu instance đã được tạo từ lần trước. Cũng không trả `200` khi instance vẫn đang provision. Nếu request lặp trong lúc operation chưa hoàn tất, trả `202` và giữ operation ID ban đầu.

## 11. Update: `200` khi thay đổi đã áp dụng, `202` khi đang chạy

Update dùng `PATCH /v2/service_instances/{instance_id}`. Khi broker đã áp dụng thay đổi hoặc request không làm thay đổi trạng thái, response đồng bộ là `200 OK` với body `{}`.

Nếu resize database, migrate dữ liệu hoặc thay đổi plan đang được thực hiện, broker trả `202 Accepted` khi request có `accepts_incomplete=true`. Nền tảng tiếp tục polling instance `last_operation`.

Update không dùng `201 Created` vì không tạo một service instance mới. Nó cũng không dùng `204` chỉ vì response không có dữ liệu. Nếu request không thể được thực hiện theo trạng thái hiện tại hoặc plan không hỗ trợ chuyển đổi, trả lỗi theo đặc tả như `422 Unprocessable Entity`, không giả vờ thành công.

Khi update bất đồng bộ thất bại, `last_operation` trả `200 OK` với body state `failed`; status `200` ở đây có nghĩa truy vấn trạng thái thành công, không có nghĩa update nghiệp vụ thành công. Sự khác biệt giữa HTTP status và trường `state` là rất quan trọng.

## 12. Bind: `201` tạo mới, `200` tái sử dụng, `202` chờ hoàn tất

Binding có thể tạo credential hoặc cấp quyền truy cập. Vì vậy response `201` hoặc `200` thường chứa `credentials` và các trường đặc thù phù hợp với service.

- Dùng `201 Created` nếu binding mới được tạo bởi request hiện tại.
- Dùng `200 OK` nếu binding đã tồn tại, đã hoàn tất và parameters giống hệt request; trường hợp này chỉ hợp lệ cho thao tác đồng bộ.
- Dùng `202 Accepted` nếu binding đang được tạo bất đồng bộ; response phải chứa cùng operation ID khi request được gửi lại và không trả credentials trước khi hoàn tất.
- Dùng `409 Conflict` nếu binding ID đã tồn tại hoặc đang được tạo nhưng parameters khác.

Sau khi async binding thành công, nền tảng có thể fetch binding nếu broker công bố `bindings_retrievable=true`; credentials phải được cung cấp theo hợp đồng để consumer sử dụng service.

## 13. Unbind và deprovision: `200`, `202`, `410`

Hai thao tác DELETE đều có thể hoàn tất đồng bộ hoặc bất đồng bộ.

### Unbind

- `200 OK`: binding đã được xóa và quyền/credential gắn với binding đã được thu hồi.
- `202 Accepted`: unbind đang chạy; nền tảng polling binding `last_operation`.
- `410 Gone`: binding không tồn tại.

### Deprovision

- `200 OK`: service instance đã được xóa và tài nguyên broker tạo trong provision đã được thu hồi.
- `202 Accepted`: deprovision đang chạy; nền tảng polling instance `last_operation`.
- `410 Gone`: instance không tồn tại.

Với cả hai DELETE, không trả `200` khi provider mới tiếp nhận lệnh xóa nhưng chưa hoàn tất nếu broker không thể bảo đảm kết quả đồng bộ. Khi đó phải dùng `202` nếu nền tảng chấp nhận async. Không trả `204` thay cho `200`.

## 14. Polling `last_operation`: HTTP `200` không có nghĩa operation succeeded

Đây là nguồn nhầm lẫn thường gặp nhất. Endpoint polling có thể trả `200 OK` trong cả ba trạng thái:

```json
{
  "state": "in progress",
  "description": "Đang khởi tạo database"
}
```

```json
{
  "state": "succeeded",
  "description": "Database đã sẵn sàng"
}
```

```json
{
  "state": "failed",
  "description": "Provider từ chối do hết quota"
}
```

HTTP `200` ở đây chỉ xác nhận broker đã xử lý thành công request đọc trạng thái. Nền tảng quyết định operation thành công hay thất bại dựa trên JSON `state`.

| HTTP response | Body `state` | Ý nghĩa |
|---|---|---|
| `200` | `in progress` | Tiếp tục polling |
| `200` | `succeeded` | Dừng polling, operation thành công |
| `200` | `failed` | Dừng polling, operation thất bại; có thể cần orphan mitigation |
| `410` | Không có body trạng thái | Chỉ dùng trong polling async delete theo điều kiện đặc tả |
| `404` | Error | Instance/binding được poll không tồn tại |

Broker nên giữ operation state đủ lâu để nền tảng có thể hỏi lại sau khi nhận `succeeded` hoặc `failed`. Có thể dùng `Retry-After` để hướng dẫn khoảng thời gian polling khi state còn `in progress`.

## 15. Error response và các mã không phải thành công

Ngoài các mã trong tiêu đề bài, một số mã lỗi thường gặp:

| HTTP status | Tình huống | Ý nghĩa |
|---|---|---|
| `400 Bad Request` | Thiếu field bắt buộc, body malformed hoặc request không hợp lệ | Nền tảng cần sửa request |
| `401 Unauthorized` | Authentication không hợp lệ | Kiểm tra thông tin xác thực broker/platform |
| `404 Not Found` | GET resource hoặc polling resource không tồn tại theo endpoint | Không tìm thấy đối tượng được truy vấn |
| `409 Conflict` | Provision/bind cùng ID nhưng attributes khác hoặc trạng thái xung đột theo endpoint | Không thể áp dụng request với trạng thái hiện tại |
| `422 Unprocessable Entity` | AsyncRequired, ConcurrencyError, plan/parameters không hỗ trợ | Request hiểu được nhưng không thể xử lý theo điều kiện hiện tại |
| `5xx` | Provider hoặc broker gặp lỗi server | Lỗi phía server; cần phân loại khả năng retry và tác động tài nguyên |

Error body có thể gồm `error` và `description`. Một số trường như `instance_usable` và `update_repeatable` chỉ áp dụng cho lỗi update/deprovision theo đặc tả; không thêm chúng vào error response của thao tác khác.

## 16. Idempotency và request được gửi lại

Status code phải phản ánh trạng thái thật khi nền tảng retry. Cùng một request có thể được gửi lại vì timeout, mất response hoặc retry ở tầng client.

Các nguyên tắc:

- Provision mới thành công lần đầu: `201`.
- Provision gửi lại khi instance đã hoàn tất và parameters giống hệt: `200` theo điều kiện đặc tả.
- Provision gửi lại khi instance vẫn đang chạy: `202` và cùng operation ID.
- Bind gửi lại khi binding đã hoàn tất với parameters giống hệt: `200`.
- Bind gửi lại khi binding còn đang tạo: `202` và cùng operation ID.
- Unbind/deprovision gửi lại khi resource không còn tồn tại: `410` theo endpoint DELETE.
- Không tạo credential hoặc tài nguyên provider lần thứ hai chỉ vì request HTTP được gửi lại.

Broker cần lưu request fingerprint, provider resource ID, binding principal và operation state. Status code không thể thay thế logic idempotency; nó chỉ công bố kết quả của logic đó cho nền tảng.

## 17. Orphan mitigation khi response không đúng

OSB API có cơ chế orphan mitigation để nền tảng xử lý tài nguyên có thể đã được tạo ở broker nhưng request bị xem là thất bại. Điều này có thể xảy ra khi broker trả status không hợp lệ, response body malformed, request timeout hoặc operation async kết thúc với `failed`.

Ví dụ broker đã tạo database nhưng trả `204 No Content` cho provision. Nền tảng có thể xem response là thất bại và cố gắng xóa resource mà nó không chắc đã tạo thành công. Nếu broker không xử lý idempotent và không lưu mapping, tài nguyên có thể bị bỏ sót.

Để hạn chế:

- Trả status code đúng endpoint.
- Với `202`, trả body hợp lệ và operation ID nhất quán khi request lặp.
- Không trả success trước khi provider đạt trạng thái cần thiết.
- Lưu mapping instance/binding với provider resource ngay khi có thể.
- Khi operation failed, lưu trạng thái và thông tin `instance_usable`/`update_repeatable` đúng nơi đặc tả cho phép.
- Đảm bảo DELETE có thể được retry và xử lý trường hợp resource đã biến mất.

## 18. Ví dụ ánh xạ response trong Spring

Trong Spring Cloud Open Service Broker, framework thường ánh xạ response model của service implementation thành HTTP status và body của OSB API. Cần dùng đúng model và builder của phiên bản dependency đang cài; không tự tạo response status ngoài hợp đồng chỉ để body trống.

Ví dụ ở mức khái niệm cho kết quả provision:

```java
public Mono<CreateServiceInstanceResponse> provision(
        CreateServiceInstanceRequest request) {
    return provisionUseCase.execute(request)
            .map(result -> {
                if (result.inProgress()) {
                    return CreateServiceInstanceResponse.builder()
                            .async(true)
                            .operation(result.operationId())
                            .build();
                }

                return CreateServiceInstanceResponse.builder()
                        .dashboardUrl(result.dashboardUrl())
                        .build();
            });
}
```

Ví dụ trên minh họa lựa chọn response model sync/async. Framework và model response sẽ quyết định status tương ứng theo phiên bản thư viện. Không đặt HTTP 204 bằng một controller tùy chỉnh để bỏ qua quy tắc response OSB.

Với update đồng bộ, tạo response update thành công rỗng; với async, đặt `async=true` và operation ID theo model. Với DELETE thành công đồng bộ, trả response delete thành công tương ứng để framework tạo `200`, không dùng response rỗng generic của HTTP `204`.

## 19. Checklist chọn status code

Trước khi hoàn tất một handler, hãy trả lời:

1. Endpoint hiện tại là GET catalog, provision, update, bind, unbind, deprovision hay polling?
2. Resource mới được tạo, đã tồn tại cùng nội dung, đã thay đổi, đang xử lý hay đã bị xóa?
3. Request có `accepts_incomplete=true` không và broker có hỗ trợ async cho plan/thao tác này không?
4. Nếu trả `202`, operation record đã được lưu bền vững và response có đúng operation ID chưa?
5. Nếu trả `200`, body có đúng schema của endpoint không? Với DELETE/update, body `{}` có được dùng khi đặc tả yêu cầu không?
6. Nếu trả `201`, resource mới đã thực sự được tạo và response chứa dữ liệu cần thiết chưa?
7. Nếu trả `410`, đây có phải endpoint DELETE hoặc polling async delete đúng ngữ cảnh không?
8. Có đang định trả `204` chỉ vì không cần body không? Nếu có, đổi sang status OSB quy định.
9. Request retry có thể tạo side effect trùng hoặc trả operation ID khác không?
10. Nền tảng sẽ giữ, quên hay polling resource sau response này?

## 20. Trình tự triển khai cho service broker

Khi triển khai các endpoint của `SPRING_CLOUD_SERVICE_BROKER`, có thể đi theo trình tự:

1. Chốt phiên bản OSB API hỗ trợ và lập bảng response status cho từng endpoint.
2. Tách kết quả nghiệp vụ thành `created`, `unchanged`, `updated`, `in progress`, `deleted`, `not found` và `failed`.
3. Ánh xạ kết quả đó sang status/body đúng hợp đồng, không dùng một response chung cho mọi thao tác.
4. Triển khai `accepts_incomplete` và operation polling cho các thao tác async được hỗ trợ.
5. Bảo đảm request lặp trả đúng `200`, `201`, `202` hoặc `410` theo trạng thái resource và điều kiện đặc tả.
6. Kiểm tra GET endpoint dùng `404` khi không tìm thấy; không dùng `410` thay thế tùy tiện.
7. Không phát `204 No Content` cho endpoint OSB trong các luồng đã nêu.
8. Kiểm thử response body cùng HTTP status, không chỉ kiểm tra status đơn lẻ.
9. Kiểm thử retry, timeout, provider failure, orphan mitigation và polling async.
10. Dùng contract test với nền tảng hoặc test suite OSB API để phát hiện response không tương thích.

Status code là tín hiệu điều khiển vòng đời chứ không chỉ là chi tiết HTTP. Khi broker dùng đúng `200`, `201`, `202` và `410` theo từng endpoint, đồng thời tránh `204` ngoài hợp đồng, nền tảng có thể biết khi nào resource đã tạo, khi nào cần chờ, khi nào thao tác xóa đã đạt mục tiêu và khi nào phải xử lý lỗi. Điều đó giúp service broker tương tác nhất quán, retry an toàn và hạn chế tài nguyên mồ côi.

## Tài liệu tham chiếu

- [Open Service Broker API Specification — v2.17](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md): các phần Catalog Management, Synchronous and Asynchronous Operations, Provisioning, Updating a Service Instance, Binding, Unbinding, Deprovisioning và Orphan Mitigation.
- [Spring Cloud Open Service Broker Reference](https://docs.spring.io/spring-cloud-open-service-broker/docs/3.3.0/reference/): cách framework ánh xạ endpoint OSB API vào service implementation và response model.
