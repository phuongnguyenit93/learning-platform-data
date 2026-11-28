# Binding không tồn tại và quy tắc phản hồi khi hủy lặp lại

## Bối cảnh

Trong Open Service Broker API (OSB API), service binding liên kết một service instance với ứng dụng hoặc consumer cần sử dụng tài nguyên đó. Khi Platform gửi yêu cầu unbind, broker phải thu hồi credential, principal, token, mapping hoặc tài nguyên phụ đã tạo cho binding. Sau khi thu hồi thành công, binding không còn tồn tại trong mô hình nghiệp vụ của broker.

Platform có thể gửi lại cùng một yêu cầu DELETE vì timeout, mất kết nối hoặc retry từ hàng đợi nội bộ. Broker cũng có thể nhận yêu cầu hủy sau khi binding đã được xóa bởi một lần gọi trước. Vì vậy, xử lý unbind phải phân biệt được:

- Binding đang tồn tại và được xóa bởi request hiện tại.
- Binding đã bị xóa trước đó hoặc chưa từng tồn tại.
- Binding đang được xóa bất đồng bộ.
- Binding đang bị một thao tác khác xử lý và chưa thể hủy.
- Broker chưa xác định được kết quả do provider hoặc mạng gặp lỗi.

OSB API quy định rõ phản hồi cho các trường hợp này. Với DELETE binding, broker trả 200 OK khi binding được xóa bởi request hiện tại; trả 202 Accepted nếu thao tác xóa vẫn đang chạy; và trả 410 Gone nếu binding không tồn tại. Nếu request DELETE được gửi lại trong khi lần xóa bất đồng bộ đầu tiên chưa hoàn tất, broker phải tiếp tục trả 202 Accepted với operation tương ứng. Khi binding đã bị xóa xong, một DELETE tiếp theo sẽ nhận 410 Gone.

Sự khác nhau giữa 200 và 410 là quan trọng đối với Platform. Cả hai đều cho biết không còn binding đang hoạt động, nhưng 200 xác nhận request hiện tại đã thực hiện việc xóa, còn 410 xác nhận binding đã không còn tồn tại khi broker xử lý request.

## 1. Hợp đồng HTTP của thao tác unbind

Platform yêu cầu thu hồi binding qua endpoint:

~~~http
DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}?service_id={service_id}&plan_id={plan_id}
X-Broker-API-Version: 2.17
Authorization: Basic <broker-credentials>
~~~

Trong đó:

- instance_id xác định service instance đã được provision.
- binding_id xác định binding cần thu hồi trong instance đó.
- service_id và plan_id là query parameter bắt buộc theo hợp đồng unbind.
- accepts_incomplete=true có thể được gửi nếu Platform chấp nhận thao tác bất đồng bộ.

Binding ID phải được tra cứu trong phạm vi Platform và service instance tương ứng. Không được chỉ tìm theo binding_id toàn cục rồi xóa bản ghi có cùng ID thuộc instance hoặc tenant khác. Khóa tra cứu nghiệp vụ thường gồm Platform ID, instance ID và binding ID.

### Các response status chính

| HTTP status | Điều kiện | Ý nghĩa với Platform |
|---|---|---|
| 200 OK | Binding được xóa do request hiện tại | Unbind đồng bộ hoàn tất |
| 202 Accepted | Unbind đang được xử lý | Platform tiếp tục polling last_operation |
| 400 Bad Request | Request sai định dạng hoặc thiếu dữ liệu bắt buộc | Request không hợp lệ |
| 401 Unauthorized | Authentication thất bại | Kiểm tra credential của Platform |
| 410 Gone | Binding không tồn tại | Platform có thể loại binding khỏi trạng thái quản lý |
| 422 Unprocessable Entity | AsyncRequired hoặc ConcurrencyError | Cần chấp thuận async hoặc chờ thao tác xung đột |
| 5xx | Broker/provider gặp lỗi thực thi | Platform phải coi thao tác chưa được xác nhận thành công |

Khi unbind thành công đồng bộ, response body theo OSB API là JSON object rỗng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{}
~~~

Khi binding không tồn tại:

~~~http
HTTP/1.1 410 Gone
Content-Type: application/json

{
  "error": "BindingDoesNotExist",
  "description": "The requested service binding does not exist."
}
~~~

BindingDoesNotExist là error code minh họa do broker lựa chọn; OSB API yêu cầu status 410 cho trường hợp binding không tồn tại, nhưng không bắt buộc broker dùng chính chuỗi error này. Nếu trả error body, trường error và description phải tuân theo cấu trúc lỗi OSB API, không tiết lộ thông tin của binding thuộc tenant khác.

## 2. Quy tắc khi hủy lặp lại

DELETE có tính idempotent ở mức hiệu ứng tài nguyên: gửi cùng một yêu cầu xóa nhiều lần không được tạo ra nhiều hiệu ứng xóa khác nhau. Tuy nhiên, response status có thể khác nhau theo trạng thái binding tại thời điểm xử lý từng request.

### Lần đầu xóa thành công, lần sau binding đã vắng mặt

Giả sử binding bind-api đang tồn tại:

1. Platform gửi DELETE bind-api.
2. Broker thu hồi credential và tài nguyên gắn với binding.
3. Broker xác minh credential không còn hiệu lực và cập nhật binding thành REVOKED/DELETED.
4. Broker trả 200 OK vì binding được xóa do request hiện tại.
5. Platform hoặc proxy gửi lại cùng DELETE sau khi lần đầu đã hoàn tất.
6. Broker xác định binding không còn tồn tại và trả 410 Gone.

Response 410 trong lần gọi sau không có nghĩa broker gặp lỗi. Nó biểu thị trạng thái mà Platform yêu cầu đã đạt được: binding không còn tồn tại.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Service Broker
    participant DB as Binding Repository
    participant I as Provider

    P->>B: DELETE binding bind-api
    B->>DB: Tìm binding đang hoạt động
    DB-->>B: Binding tồn tại
    B->>I: Revoke credential / delete principal
    I-->>B: Thu hồi thành công
    B->>DB: Đánh dấu binding đã xóa
    B-->>P: 200 OK {}
    Note over P,B: Platform gửi lại DELETE sau khi hoàn tất
    P->>B: DELETE binding bind-api
    B->>DB: Tra cứu binding
    DB-->>B: Không còn binding
    B-->>P: 410 Gone
~~~

Không nên trả 200 cho mọi DELETE lặp chỉ vì muốn làm cho response giống nhau. Hợp đồng OSB API phân biệt rõ trường hợp request hiện tại đã xóa binding với trường hợp binding không tồn tại; Platform dựa vào 410 để đồng bộ trạng thái đã mất khỏi cơ sở dữ liệu quản lý của nó.

### Lần xóa đầu tiên vẫn đang chạy

Nếu broker xử lý unbind bất đồng bộ và request đầu tiên đã trả 202 Accepted, Platform có thể gửi lại DELETE trước khi worker hoàn tất. Trong trường hợp đó, OSB API yêu cầu broker tiếp tục trả 202 Accepted, không được trả 200 OK.

Operation trong response lặp phải khớp với operation đã trả cho request ban đầu. Điều này giúp Platform polling đúng công việc đang chạy, tránh tạo operation thứ hai cho cùng binding.

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operation": "unbind-7f31a9"
}
~~~

Nếu Platform gửi lại DELETE trong lúc operation này còn pending, broker trả lại 202 cùng operation ID:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operation": "unbind-7f31a9"
}
~~~

Sau khi thao tác hoàn tất, một DELETE mới sẽ thấy binding không còn tồn tại và trả 410 Gone. Không trả 200 cho request lặp trong khi thao tác đầu tiên vẫn đang chạy, vì điều đó khiến Platform tin rằng việc xóa đã hoàn tất dù provider vẫn có thể đang giữ credential hoặc principal.

### Ma trận quyết định

| Trạng thái broker khi nhận DELETE | Hành động | Response |
|---|---|---|
| ACTIVE, xóa hoàn tất ngay | Thu hồi và xác minh tài nguyên | 200 OK |
| ACTIVE, cần xử lý nền và Platform chấp thuận | Tạo operation và worker | 202 Accepted |
| REVOKING, cùng operation đang chạy | Trả operation hiện có | 202 Accepted |
| REVOKED/DELETED, không còn binding | Không tạo side effect mới | 410 Gone |
| Đang có operation khác và không thể nhận unbind | Không sửa trạng thái | 422 ConcurrencyError |
| Cần async nhưng request không chấp thuận | Không nhận công việc nền | 422 AsyncRequired |
| Provider/network không xác định được kết quả | Reconcile hoặc báo lỗi tạm thời | 5xx phù hợp |

## 3. Binding không tồn tại khác với lỗi provider

Một broker không nên coi mọi trường hợp không đọc được binding là binding đã bị xóa. Các nguyên nhân sau cần được phân biệt:

- **Không có bản ghi binding:** broker xác định binding không tồn tại trong phạm vi Platform/instance.
- **Provider xác nhận principal đã bị xóa:** bước thu hồi có thể được xem là đã hoàn tất nếu broker đã xác minh các tài nguyên liên quan đều không còn.
- **Provider timeout:** chưa biết lệnh xóa có được thực hiện hay không.
- **Provider trả lỗi quyền:** broker chưa có quyền thu hồi; binding có thể vẫn đang hoạt động.
- **Database broker tạm thời không truy cập được:** không thể xác định trạng thái nội bộ.
- **Binding ID thuộc instance khác:** request không được phép xóa binding đó; không tiết lộ thông tin cross-tenant.

Chỉ trả 410 khi broker có đủ căn cứ xác định binding không tồn tại. Nếu provider timeout hoặc trạng thái không rõ, không được suy diễn rằng tài nguyên đã biến mất. Hãy giữ trạng thái cần reconcile và trả lỗi phù hợp để Platform tiếp tục ghi nhận binding.

### Phân biệt các endpoint GET

OSB API có các ngữ cảnh khác nhau cho status 404 và 410:

| Endpoint | Binding không tồn tại | Ý nghĩa |
|---|---|---|
| DELETE binding | 410 Gone | Binding cần xóa đã không tồn tại |
| GET binding (nếu broker hỗ trợ fetch) | 404 Not Found | Không tìm thấy binding để đọc hoặc binding operation vẫn đang xử lý |
| GET binding last_operation | 404 Not Found | Binding được yêu cầu polling không tồn tại |
| GET binding last_operation cho async delete | Có thể trả 410 Gone | Chỉ dùng cho thao tác xóa bất đồng bộ; Platform phải coi là xóa thành công |

Không dùng status của GET fetch để thay thế status của DELETE. Đặc biệt, 404 ở endpoint retrieve không có cùng ý nghĩa hợp đồng với 410 ở endpoint unbind.

## 4. Hủy binding khi thao tác tạo binding đang chạy

Có một tình huống đặc biệt: Platform gửi DELETE trong lúc broker vẫn đang tạo binding. Ví dụ, provider đã bắt đầu tạo database role nhưng response PUT chưa được trả về, hoặc worker đang phát hành token và lưu binding record.

OSB API quy định rằng nếu broker chấp nhận yêu cầu xóa binding trong lúc binding đang được tạo, broker phải dừng quá trình tạo hiện tại và bắt đầu xóa các tài nguyên liên quan đến binding đó. Mục tiêu là tránh để binding xuất hiện sau khi Platform đã yêu cầu hủy.

Broker cần:

1. Đánh dấu binding hoặc operation hiện tại ở trạng thái cancellation requested.
2. Ngăn các bước tạo mới tiếp tục phát hành credential hoặc resource.
3. Chờ hoặc phối hợp với worker đang tạo để xác định side effect đã thực hiện.
4. Thu hồi mọi principal, token, mapping hoặc secret đã tạo.
5. Xác minh không còn khả năng sử dụng binding.
6. Hoàn tất thao tác hủy và lưu trạng thái cuối.

Nếu unbind được xử lý bất đồng bộ, last_operation của binding nên phản ánh trạng thái delete request, trừ khi broker trả operation ID khác theo hợp đồng. Nếu hủy đồng bộ trong khi create đang chạy, last_operation nên phản ánh create request đã thất bại.

Nếu binding đang bị một operation khác xử lý và broker không thể chấp nhận unbind ở thời điểm đó, broker trả 422 với error ConcurrencyError. Đây là điều kiện xung đột, khác với AsyncRequired:

| Error | Nguyên nhân | Hành động Platform |
|---|---|---|
| AsyncRequired | Broker chỉ có thể unbind bất đồng bộ nhưng request không có accepts_incomplete=true | Gửi lại request với accepts_incomplete=true nếu Platform hỗ trợ |
| ConcurrencyError | Binding đang được operation khác xử lý và broker không thể nhận unbind lúc này | Chờ operation hiện tại kết thúc rồi thử lại |

Không dùng ConcurrencyError để thay thế việc hủy create đang chạy nếu broker đã chấp nhận khả năng dừng create và thu hồi tài nguyên theo yêu cầu OSB API.

## 5. Xử lý unbind bất đồng bộ và polling

Nếu thao tác thu hồi cần thời gian, Platform gửi accepts_incomplete=true. Broker ghi operation bền vững và trả 202 Accepted. Response có thể chứa operation ID:

~~~http
DELETE /v2/service_instances/db-42/service_bindings/app-17?service_id=postgres&plan_id=standard&accepts_incomplete=true HTTP/1.1
X-Broker-API-Version: 2.17

HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operation": "unbind-7f31a9"
}
~~~

Platform polling endpoint:

~~~http
GET /v2/service_instances/db-42/service_bindings/app-17/last_operation?service_id=postgres&plan_id=standard&operation=unbind-7f31a9 HTTP/1.1
X-Broker-API-Version: 2.17
~~~

Response đang chạy:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Retry-After: 5

{
  "state": "in progress",
  "description": "Revoking credentials for the service binding"
}
~~~

Response kết thúc:

~~~json
{
  "state": "succeeded",
  "description": "The service binding has been removed"
}
~~~

Last operation của binding có thể trả 410 Gone cho thao tác xóa bất đồng bộ. Trên endpoint polling này, 410 chỉ phù hợp với async delete; Platform phải coi response đó là thành công và xóa binding khỏi database quản lý. Không trả 410 cho polling của thao tác create binding, vì Platform có thể hiểu sai rằng binding đã bị xóa.

Phân biệt:

- DELETE trả 410: binding không tồn tại tại thời điểm nhận yêu cầu xóa.
- GET last_operation trả 410: broker dùng tín hiệu hoàn tất dành riêng cho async delete; Platform phải coi việc xóa là thành công.
- GET last_operation trả 200 với state succeeded: operation hoàn tất và Platform dừng polling.
- GET last_operation trả 200 với state in progress: Platform tiếp tục polling theo chính sách.
- GET last_operation trả 200 với state failed: Platform dừng polling và có thể cần orphan mitigation.

Nếu broker trả operation ID trong response 202, Platform phải gửi lại đúng operation trong query parameter của last_operation. Nếu broker không trả operation ID, chỉ một async operation được hỗ trợ tại một thời điểm cho binding theo quy tắc của OSB API. Vì vậy, trả ID ổn định thường giúp quản lý retry và polling rõ ràng hơn.

## 6. Thiết kế trạng thái binding và tombstone

Để xử lý request lặp, broker cần lưu vòng đời binding bền vững. Không nên xóa ngay mọi dấu vết trong database khi provider đã thu hồi credential, vì Platform có thể gửi lại DELETE hoặc polling operation sau đó.

Mô hình tham khảo:

~~~text
ServiceBinding
  platformId
  instanceId
  bindingId
  providerPrincipalId
  secretReference
  state
  currentOperationId
  requestFingerprint
  createdAt
  revocationStartedAt
  revokedAt
  lastErrorCode

BindingOperation
  operationId
  platformId
  instanceId
  bindingId
  operationType
  state
  phase
  providerRequestId
  retryCount
  createdAt
  completedAt
~~~

Các trạng thái có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| CREATING | Đang tạo principal hoặc credential |
| ACTIVE | Binding đã sẵn sàng sử dụng |
| REVOKING | Đang thu hồi tài nguyên |
| REVOKED | Credential và tài nguyên binding đã được thu hồi |
| FAILED | Có lỗi chưa thể tự phục hồi |
| RECONCILING | Đang đối chiếu trạng thái broker với provider |

Tombstone là bản ghi tối thiểu cho binding đã xóa. Nó giữ binding ID, phạm vi Platform/instance, thời điểm xóa và operation cuối trong thời hạn phù hợp. Tombstone giúp:

- Phân biệt binding đã bị xóa với bản ghi chưa từng được tạo.
- Nhận diện request DELETE lặp.
- Trả trạng thái nhất quán cho polling sau khi provider resource đã biến mất.
- Ngăn một worker cũ tạo lại binding sau khi yêu cầu hủy đã được chấp nhận.
- Hỗ trợ audit và điều tra sự cố.

Tombstone không được giữ secret đã thu hồi. Secret reference có thể được xóa hoặc vô hiệu hóa sau khi các bước audit/retention bắt buộc hoàn tất. Thời gian giữ tombstone phải đủ để xử lý retry và polling muộn, nhưng cũng cần giới hạn để tránh tăng dữ liệu vô hạn.

## 7. Idempotency và xử lý đồng thời

Idempotency của unbind không chỉ là kiểm tra xem bản ghi có tồn tại hay không. Broker phải bảo đảm nhiều request đồng thời hoặc nhiều worker retry không cùng thu hồi, xóa hoặc ghi trạng thái mâu thuẫn.

### Khóa nghiệp vụ

Khóa duy nhất nên bao gồm:

- Platform ID.
- Service instance ID.
- Binding ID.

Ràng buộc unique ở database ngăn hai binding record trùng trong cùng phạm vi. Mọi thao tác đọc, thu hồi và ghi trạng thái phải dùng cùng khóa này.

### Quy tắc theo trạng thái

~~~text
unbind(platform, instance, binding):
    record = findByCompositeKey(platform, instance, binding)

    if record is absent:
        reconcile any provider resource tagged for this binding
        if provider outcome is unknown:
            return RETRYABLE_ERROR
        return GONE

    if record.state == REVOKED:
        return GONE

    if record.state == REVOKING:
        return ACCEPTED(existingOperationId)

    if record has incompatible active operation:
        return CONCURRENCY_ERROR

    reserve revocation with compare-and-set
    revoke provider credentials and resources
    verify access is no longer possible
    mark REVOKED and write tombstone
    return OK
~~~

Đây là pseudocode mô tả chính sách; triển khai thực tế phải xử lý riêng nhánh provider timeout và kết quả không xác định. Không được chuyển sang REVOKED chỉ vì worker đã gửi request tới provider.

### Compare-and-set và lease

Khi nhiều replica broker nhận cùng DELETE, chỉ một replica nên được quyền chuyển binding từ ACTIVE sang REVOKING. Có thể dùng optimistic locking với version column, row-level lock hoặc thao tác update có điều kiện:

~~~sql
UPDATE service_binding
SET state = 'REVOKING',
    version = version + 1
WHERE platform_id = :platform_id
  AND instance_id = :instance_id
  AND binding_id = :binding_id
  AND state = 'ACTIVE'
  AND version = :expected_version;
~~~

Nếu số hàng được cập nhật bằng 0, replica phải đọc lại trạng thái. Có thể binding đã bị xóa, đang được replica khác xử lý hoặc đã chuyển sang operation khác. Không gọi provider trước khi giành được quyền xử lý.

Nếu dùng distributed lock có lease, nên có fencing token hoặc generation để worker cũ không thể ghi đè trạng thái sau khi lease hết hạn và worker mới đã tiếp quản.

## 8. Thu hồi tài nguyên provider an toàn

Một binding có thể tạo nhiều tài nguyên: database login, role, token, secret, network rule, service account hoặc mapping ở gateway. Unbind phải thu hồi toàn bộ tài nguyên mà broker đã tạo cho binding.

Thứ tự có thể là:

1. Đánh dấu binding REVOKING để ngăn cấp phát hoặc sử dụng thêm.
2. Vô hiệu hóa credential/token để ngăn kết nối mới.
3. Thu hồi mapping, role, user hoặc service account.
4. Kết thúc session đang hoạt động nếu provider yêu cầu.
5. Xóa network rule hoặc tài nguyên phụ thuộc.
6. Xác minh credential không còn được chấp nhận.
7. Xóa secret material hoặc vô hiệu hóa secret reference.
8. Ghi tombstone và kết thúc operation.

Thứ tự chính xác tùy provider. Với database, có thể cần revoke login trước, terminate session, chuyển ownership object rồi mới drop role. Với Kubernetes, có thể xóa Secret, RoleBinding, ServiceAccount hoặc custom resource theo dependency. Với gateway, có thể revoke token mapping trước khi thu hồi backend identity.

### Provider trả “not found”

Nếu provider trả 404/NotFound cho principal mà broker định xóa, broker có thể xem bước xóa đó đã đạt trạng thái mong muốn sau khi xác minh đúng resource identity. Đây là tính idempotent của bước cleanup: xóa một principal đã không còn tồn tại không cần tạo ra lỗi vĩnh viễn.

Tuy nhiên, không được coi mọi lỗi 404 từ provider là thành công. Cần xác minh:

- Đúng provider account/cluster/project.
- Đúng resource tag gắn với Platform, instance và binding.
- Không có một principal khác cùng tên thuộc binding khác.
- Không còn credential hoặc token phụ vẫn có hiệu lực.

### Provider timeout

Nếu request xóa timeout, broker không biết provider đã xóa principal hay chưa. Hãy giữ REVOKING hoặc chuyển RECONCILING, sau đó truy vấn trạng thái provider. Nếu principal đã biến mất, hoàn tất tombstone. Nếu vẫn tồn tại, retry thao tác xóa theo idempotency policy. Nếu không xác định được trạng thái, không trả 410 chỉ để kết thúc retry.

## 9. Binding không tồn tại và ranh giới bảo mật

Broker thường phục vụ nhiều Platform và tenant. Một binding ID có thể trùng giữa hai Platform hoặc hai instance khác nhau. Vì vậy, phản hồi 410 phải dựa trên lookup trong đúng phạm vi.

Các nguyên tắc:

- Xác thực caller trước khi tra cứu binding.
- Kiểm tra Platform/tenant scope và quyền thao tác trên instance.
- Dùng composite key khi tra cứu binding.
- Không trả thông tin về principal, username hoặc consumer thuộc binding khác.
- Không xóa tài nguyên chỉ dựa trên binding ID do request gửi nếu chưa xác minh owner tag.
- Không đưa secret hoặc provider response thô vào error description.
- Ghi audit request identity, binding ID đã che phù hợp, operation ID và kết quả thu hồi.

Nếu caller đã xác thực nhưng binding không tồn tại trong phạm vi được phép, trả 410 theo hợp đồng unbind mà không tiết lộ liệu một binding cùng ID có tồn tại ở tenant khác hay không.

## 10. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction cho binding lifecycle. Ứng dụng triển khai service xử lý delete binding, nhận request model và điều phối application service. Tên method, exception và response type cần đối chiếu với phiên bản dependency đang dùng.

Nên phân lớp:

| Thành phần | Trách nhiệm |
|---|---|
| OSB binding service | Nhận delete request và chuyển dữ liệu sang use case |
| Binding application service | Kiểm tra binding state, owner và operation hiện tại |
| Revocation policy | Chọn thứ tự thu hồi và xử lý retry |
| Binding repository | Lưu trạng thái, version và tombstone |
| Operation repository/outbox | Lưu tiến trình bất đồng bộ bền vững |
| Provider adapter | Revoke credential, principal và resource phụ |
| Last operation service | Trả tiến trình unbind cho Platform |

Ví dụ pseudocode:

~~~java
DeleteBindingResult unbind(UnbindCommand command) {
    var binding = repository.find(
            command.platformId(),
            command.instanceId(),
            command.bindingId());

    if (binding == null) {
        providerAdapter.reconcileByBindingTag(command);
        if (providerAdapter.hasUnknownOutcome(command)) {
            throw new RetryableProviderException();
        }
        return DeleteBindingResult.gone();
    }

    if (binding.isRevoked()) {
        return DeleteBindingResult.gone();
    }

    if (binding.isRevoking() && binding.currentOperationId() != null) {
        return DeleteBindingResult.accepted(
                binding.currentOperationId());
    }

    if (binding.isRevoking() || binding.hasIncompatibleOperation()) {
        throw new ConcurrencyErrorException();
    }

    var reservation = repository.reserveRevocation(binding.id());
    if (!reservation.acquired()) {
        return resolveCurrentState(command);
    }

    if (revocationPolicy.requiresAsync(binding)) {
        if (!command.acceptsIncomplete()) {
            repository.releaseReservation(reservation);
            throw new AsyncRequiredException();
        }

        var operation = operationService.enqueueUnbind(binding);
        return DeleteBindingResult.accepted(operation.id());
    }

    providerAdapter.revoke(binding.providerPrincipalId());
    providerAdapter.verifyRevoked(binding);
    repository.markRevoked(binding.id());
    return DeleteBindingResult.deleted();
}
~~~

Đây là pseudocode mô tả quyết định nghiệp vụ, không phải chữ ký API chính xác của Spring Cloud Open Service Broker. Việc reserve và kiểm tra accepts_incomplete phải được tổ chức trong transaction để tránh hai request cùng tạo operation. Nếu async không được chấp thuận, rollback reservation và không để lại outbox event hay side effect.

### Ánh xạ lỗi

- Binding không tồn tại: ánh xạ sang HTTP 410 Gone theo hợp đồng unbind.
- Đã xóa trước đó: vẫn là binding không tồn tại, trả 410.
- Cùng operation đang chạy: trả 202 và cùng operation ID.
- Chỉ hỗ trợ async nhưng request không chấp thuận: 422 với error AsyncRequired.
- Operation khác khiến không thể unbind: 422 với error ConcurrencyError.
- Provider timeout hoặc lỗi không xác định: trả lỗi thực thi phù hợp, giữ trạng thái để reconcile.

Không nên tự tạo controller trùng endpoint mà framework đã đăng ký. Dùng exception mapping hoặc response handling được hỗ trợ bởi phiên bản framework để status code và JSON error body tuân thủ OSB API.

## 11. Kiểm thử các trường hợp hủy lặp lại

Kiểm thử cần bao phủ status code, operation ID, trạng thái database và provider resource. Chỉ kiểm tra response HTTP là chưa đủ.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Xóa binding đang ACTIVE, provider thành công | 200 OK, body {} và binding được đánh dấu REVOKED |
| Xóa binding không tồn tại | 410 Gone |
| DELETE lần hai sau khi xóa đồng bộ hoàn tất | 410 Gone, không gọi provider lần nữa |
| DELETE lặp trong khi async unbind đang chạy | 202 Accepted với cùng operation ID |
| DELETE sau khi async unbind hoàn tất | 410 Gone |
| Async unbind nhưng thiếu accepts_incomplete=true | 422 AsyncRequired, không tạo operation hoặc side effect |
| Binding đang có operation không tương thích | 422 ConcurrencyError |
| Provider trả NotFound cho principal đã được xác minh | Cleanup step được coi là hoàn tất |
| Provider timeout sau lệnh revoke | Giữ trạng thái chưa xác định và reconcile |
| Broker restart khi REVOKING | Worker tiếp tục từ operation/checkpoint |
| Hai replica nhận DELETE đồng thời | Chỉ một replica giành reservation và thực hiện cleanup |
| Binding ID trùng ở hai tenant | Chỉ binding trong đúng scope bị ảnh hưởng |
| GET last_operation cho async delete trả 410 | Platform coi là thành công và loại binding |
| GET last_operation cho create trả 410 | Không dùng như tín hiệu thành công; xử lý theo contract |
| Unbind trong lúc create đang chạy | Create bị dừng và tài nguyên đã tạo được thu hồi |

### Kiểm thử không xóa nhầm binding

Tạo hai binding có cùng binding ID nhưng khác Platform hoặc instance scope. Gửi DELETE cho một binding và xác nhận:

1. Chỉ principal có owner tag đúng bị thu hồi.
2. Binding còn lại vẫn hoạt động.
3. Response không tiết lộ dữ liệu của binding còn lại.
4. Tombstone được ghi dưới đúng composite key.

### Kiểm thử provider timeout

Giả lập provider đã thực hiện revoke nhưng response bị mất. Khi worker retry, adapter phải đọc trạng thái provider, nhận diện principal đã biến mất và hoàn tất cleanup mà không tạo principal mới hoặc báo lỗi sai. Cũng cần kiểm thử trường hợp provider chưa thực hiện revoke để worker tiếp tục thử lại.

## 12. Quan sát và vận hành

Các metric và log nên giúp đội vận hành phân biệt binding đã xóa, binding đang chờ và binding bị kẹt:

- Số lượng DELETE theo status 200, 202, 410, 422 và 5xx.
- Số operation unbind đang REVOKING hoặc RECONCILING.
- Thời gian từ lúc nhận DELETE đến lúc xác minh credential đã bị thu hồi.
- Số retry provider và số principal mồ côi được phát hiện.
- Số binding tombstone đang được giữ theo retention policy.
- Tỷ lệ operation unbind thất bại theo provider/plan.

Log có cấu trúc nên chứa request ID, operation ID, Platform scope, instance ID, binding ID đã bảo vệ phù hợp, provider resource reference và trạng thái trước/sau. Không log password, token, credential hoặc binding response đầy đủ.

Nếu một binding ở REVOKING quá lâu, hệ thống cần cảnh báo và chạy reconciliation. Không tự động xóa tombstone hoặc đánh dấu REVOKED chỉ để giảm số operation pending; phải xác minh provider không còn cho phép truy cập.

## 13. Checklist triển khai

- [ ] DELETE binding dùng đúng endpoint và yêu cầu service_id/plan_id.
- [ ] Binding lookup được giới hạn theo Platform, instance và binding ID.
- [ ] 200 chỉ trả khi request hiện tại đã xóa binding.
- [ ] 410 trả khi binding không tồn tại, kể cả DELETE lặp sau khi đã xóa xong.
- [ ] DELETE lặp khi async operation còn chạy trả 202 với cùng operation ID.
- [ ] 422 AsyncRequired được dùng khi cần async nhưng request không chấp thuận.
- [ ] 422 ConcurrencyError được dùng khi operation khác ngăn unbind.
- [ ] Không nhầm 410 của DELETE với 404 của GET binding hoặc GET last_operation.
- [ ] 410 trên last_operation chỉ dùng cho async delete và Platform phải coi là thành công.
- [ ] Unbind trong lúc create được điều phối để dừng create và thu hồi tài nguyên nếu broker chấp nhận.
- [ ] Provider timeout được xử lý bằng reconcile, không suy diễn binding đã biến mất.
- [ ] Binding state, operation và tombstone được lưu bền vững.
- [ ] Compare-and-set/locking ngăn hai replica thu hồi cùng binding đồng thời.
- [ ] Secret và credential bị vô hiệu hóa, không còn truy cập được sau khi báo thành công.
- [ ] Có integration test cho 200, 202, 410, 422 và các tình huống retry.

## Kết luận

Khi unbind, broker phải phản ánh chính xác trạng thái binding tại thời điểm xử lý request. Nếu request hiện tại xóa binding thành công, trả 200 OK; nếu binding đã không còn tồn tại, trả 410 Gone; nếu thao tác vẫn đang chạy, trả 202 Accepted và giữ nguyên operation ID khi nhận DELETE lặp. Sau khi async delete hoàn tất, Platform có thể polling last_operation và nhận 200 với state cuối hoặc 410 Gone theo quy tắc riêng của endpoint polling. Thiết kế binding state, tombstone, idempotency và reconciliation giúp broker xử lý retry an toàn, thu hồi credential đúng phạm vi và giữ trạng thái giữa Platform, Spring Cloud và provider nhất quán.

## Tài liệu tham khảo

- [Open Service Broker API specification — Unbinding](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#unbinding)
- [Open Service Broker API specification — Polling Last Operation for Service Bindings](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#polling-last-operation-for-service-bindings)
