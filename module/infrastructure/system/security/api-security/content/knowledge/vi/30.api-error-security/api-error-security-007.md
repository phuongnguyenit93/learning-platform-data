# Client không được dùng lỗi để bỏ qua kiểm soát

API trả lỗi khi request không thể được xử lý, nhưng cách client phản ứng với lỗi cũng có thể tạo ra lỗ hổng. Ví dụ, một ứng dụng nhận `403 Forbidden` rồi tự gọi endpoint legacy ít bảo vệ hơn; nhận timeout từ authorization service rồi mặc định cho phép thao tác; hoặc nhận lỗi validation rồi gửi lại payload đã bỏ field kiểm soát. Khi hệ thống dựa vào việc client sẽ dừng đúng lúc, attacker có thể sửa client, gọi API trực tiếp hoặc giả lập một luồng xử lý khác để bỏ qua kiểm soát.

Nguyên tắc cốt lõi là **server phải tự thực thi mọi kiểm soát bảo mật ở mỗi request và mỗi side effect**. Client có thể hiển thị thông báo, yêu cầu đăng nhập lại, hướng dẫn sửa dữ liệu hoặc retry một thao tác an toàn. Client không phải ranh giới tin cậy để quyết định caller có quyền hay không. Một lỗi, một response bị thiếu hoặc một dependency không phản hồi không được biến thành lý do để server mặc định cho phép hành động.

Trong phạm vi `SECURITY_API_SECURITY`, lỗi API cần được thiết kế theo endpoint, object và luồng nghiệp vụ. Cần phân biệt lỗi authentication, authorization, validation, conflict, quota và lỗi hạ tầng; đồng thời bảo đảm mọi nhánh xử lý, fallback, retry và phục hồi đều giữ nguyên invariant bảo mật.

## 1. Vì sao error handling có thể trở thành đường bypass?

Lỗi thường xảy ra ở ranh giới giữa nhiều thành phần: frontend, API gateway, authentication service, authorization service, database, message broker và downstream API. Nếu một thành phần hiểu lỗi theo cách khác, hệ thống có thể chuyển sang một đường xử lý yếu hơn.

Các tình huống điển hình:

- Client nhận `403` rồi gọi endpoint cũ hoặc endpoint dự phòng không kiểm tra cùng permission.
- Authorization service timeout; API coi không có câu trả lời là không có lệnh cấm và cho phép request.
- Token introspection lỗi; gateway bỏ qua bước kiểm tra để giữ availability.
- Validation service không phản hồi; backend bỏ qua validation hoặc dùng dữ liệu mặc định quá rộng.
- Rate limiter lỗi; API tiếp tục cho phép mọi request và làm cạn tài nguyên.
- API trả `404` cho object ngoài tenant; client dùng endpoint search/export khác để tìm dữ liệu đó.
- Client hiểu `401` và `403` giống nhau, tự refresh token hoặc chuyển sang anonymous mode rồi tiếp tục thao tác.
- Lỗi parse response khiến client bỏ qua kiểm tra trạng thái và vẫn hiển thị hoặc thực hiện bước tiếp theo.
- Retry không giới hạn làm request có side effect được thực hiện nhiều lần.
- GraphQL trả HTTP `200` kèm `errors`; client chỉ nhìn status và xử lý partial data như thành công hoàn toàn.

Trong các trường hợp này, vấn đề không nằm ở việc có trả lỗi hay không. Vấn đề là một nhánh lỗi đã làm mất một kiểm soát mà nhánh thành công vẫn phải tuân thủ.

## 2. Server là nơi có thẩm quyền quyết định

Client không thể là điểm thực thi cuối cùng cho authentication, authorization, tenant isolation hoặc business invariant. Người dùng có thể sửa JavaScript, thay mobile binary, gửi request bằng curl, gọi API từ script hoặc bỏ qua giao diện hoàn toàn.

Server cần tự kiểm tra tối thiểu:

1. Credential có hợp lệ, đúng issuer/audience và chưa hết hạn hoặc bị thu hồi không?
2. Principal đã xác thực có được phép gọi function/action này không?
3. Object có thuộc tenant và phạm vi dữ liệu của principal không?
4. Field được đọc hoặc cập nhật có nằm trong quyền được cấp không?
5. Input có hợp lệ và thỏa business rule không?
6. Trạng thái hiện tại có cho phép side effect không?
7. Quota, concurrency và các giới hạn tài nguyên có còn đủ không?
8. Nếu dependency phục vụ quyết định bảo mật bị lỗi, hành động có được dừng an toàn không?

Việc client ẩn nút, disable form hoặc hiển thị “Access denied” chỉ cải thiện trải nghiệm. Endpoint vẫn phải kiểm tra quyền khi request đến. Tương tự, client không thể tự biến một response lỗi thành bằng chứng rằng thao tác đã được chấp nhận.

### 2.1. Kiểm tra tại mọi entry point

Nếu cùng một nghiệp vụ có REST endpoint, GraphQL resolver, message consumer, admin route và background job, mỗi entry point phải đi qua policy tương đương. Không được bảo vệ endpoint chính nhưng để endpoint export, batch, legacy hoặc worker tin rằng request đã được kiểm tra ở client.

Đối với service-to-service, caller identity và delegation context phải được xác minh ở service nhận. Không tin một header như `X-User-Role`, `X-Tenant-Id` hoặc `X-Authorization-Result` nếu nó không được tạo và bảo vệ qua một trust channel đã xác định.

## 3. Fail-open và fail-closed

Khi một thành phần cần thiết để ra quyết định bị lỗi, hệ thống phải có policy rõ ràng. Hai cách xử lý thường được gọi là fail-open và fail-closed.

| Cách xử lý | Hành vi | Rủi ro/chỗ dùng phù hợp |
|---|---|---|
| Fail-open | Cho phép tiếp tục khi dependency không trả lời | Có thể bỏ qua kiểm soát; chỉ cân nhắc cho chức năng không nhạy cảm với fallback giới hạn rõ |
| Fail-closed | Từ chối hoặc tạm dừng khi không thể xác minh | Bảo vệ quyền và dữ liệu; có thể giảm availability |
| Safe degraded mode | Chỉ cho phép tập hành động đã chứng minh an toàn khi dependency lỗi | Cần thiết kế và test kỹ; không được biến thành bypass tổng quát |

Với authorization, token verification, tenant isolation, signature verification và quyết định có side effect nhạy cảm, mặc định phải fail-closed. Nếu không thể xác định caller có quyền, không thực hiện hành động.

Ví dụ:

```java
AuthorizationDecision decision;
try {
    decision = authorizationService.check(actor, action, resource);
} catch (AuthorizationServiceUnavailableException ex) {
    throw new ServiceUnavailableException(
        "Authorization decision is temporarily unavailable");
}

if (!decision.isAllowed()) {
    throw new AccessDeniedException("Action is not permitted");
}

performSensitiveOperation();
```

Đoạn code chỉ minh họa nguyên tắc: dependency không trả quyết định không đồng nghĩa `allowed=true`. Tùy hợp đồng API, lỗi dependency có thể được trả dưới dạng `503 Service Unavailable`, còn quyết định deny rõ ràng thường là `403` hoặc `404` theo chính sách che giấu object.

### 3.1. Safe degraded mode cần có ranh giới

Một số chức năng có thể tiếp tục ở chế độ giới hạn khi dependency không khả dụng. Ví dụ, trang đọc dữ liệu public có thể dùng cache đã được xác định là public; dashboard không nhạy cảm có thể hiển thị dữ liệu stale kèm nhãn thời gian. Nhưng không dùng cache cũ để quyết định quyền trên dữ liệu riêng tư nếu cache không có cơ chế thu hồi và freshness phù hợp.

Một safe degraded mode phải nêu rõ:

- Action nào được tiếp tục và action nào bị dừng.
- Dữ liệu nào được dùng, độ cũ tối đa và cách cô lập tenant.
- Có cho phép side effect không.
- Khi nào quay lại chế độ bình thường.
- Ai có quyền bật/tắt và mọi thay đổi có được audit không.
- Giới hạn rate/concurrency trong lúc degraded.

Không dùng cờ cấu hình chung kiểu `ignoreAuthorizationErrors=true` hoặc `skipValidationOnFailure=true` để giữ toàn bộ API hoạt động.

## 4. Không dùng client fallback để né 401/403

`401 Unauthorized` và `403 Forbidden` có ý nghĩa khác nhau theo HTTP:

- `401` thường chỉ ra request thiếu credential hợp lệ hoặc credential không được chấp nhận; server thường kèm challenge phù hợp.
- `403` chỉ ra server hiểu request nhưng từ chối hành động theo policy hiện tại.
- `404` đôi khi được dùng thay cho `403` để không tiết lộ object có tồn tại hay không.

Client có thể xử lý `401` bằng cách yêu cầu đăng nhập hoặc thực hiện một lần refresh token theo flow đã thiết kế. Khi refresh thất bại, client phải dừng và yêu cầu người dùng xác thực lại. Client không được bỏ token rồi gửi lại cùng thao tác ở chế độ anonymous nếu thao tác đó cần xác thực.

Với `403`, refresh token thường không giải quyết vấn đề vì caller đã được xác thực nhưng thiếu quyền. Client nên hiển thị thông báo phù hợp hoặc hướng dẫn yêu cầu quyền. Không tự động gọi endpoint legacy, đổi user context, dùng API key dự phòng hoặc thử một role rộng hơn.

Ví dụ logic client an toàn:

```javascript
async function updateOrder(orderId, body) {
  const response = await api.patch(`/v2/orders/${orderId}`, body);

  if (response.status === 401) {
    await session.requireReauthentication();
    throw new Error("Authentication required");
  }

  if (response.status === 403 || response.status === 404) {
    throw new Error("You cannot perform this action");
  }

  if (!response.ok) {
    throw new Error("The order could not be updated");
  }

  return response.json();
}
```

Đây chỉ là xử lý trải nghiệm phía client. Server vẫn phải kiểm tra token, permission và object scope. Không đưa logic authorization vào client rồi coi đoạn code này là lớp bảo vệ.

## 5. Không biến lỗi dependency thành quyền mặc định

Các dependency có thể tham gia quyết định bảo mật:

- Authorization/policy decision point.
- Token introspection hoặc key/JWKS retrieval.
- Tenant/account status service.
- Fraud/risk engine.
- Consent/approval service.
- Signature/key registry cho webhook.
- Quota/rate-limit service.
- Schema/validation service hoặc service xác minh dữ liệu ngoài.

Với mỗi dependency, xác định lỗi nào là deny, lỗi nào có thể retry, lỗi nào được dùng cache và cache có thể stale tối đa bao lâu.

| Dependency | Khi không khả dụng | Hành vi an toàn tham khảo |
|---|---|---|
| Token verifier/introspection | Không xác minh được token | Không chấp nhận token chưa xác minh; có thể dùng local verification nếu trust/key còn hợp lệ |
| Authorization service | Không có quyết định quyền | Từ chối hoặc trả `503`; không mặc định allow |
| Tenant status/entitlement | Không biết tenant có bị khóa không | Dừng action nhạy cảm; cache chỉ dùng nếu policy freshness cho phép |
| Fraud/risk engine | Không có risk decision | Áp policy dự phòng đã phê duyệt; không tự động bỏ step-up cho giao dịch rủi ro cao |
| Rate limiter | Không kiểm tra được quota | Dùng emergency cap cục bộ hoặc từ chối action tốn chi phí; không mở vô hạn |
| Signature key registry | Không lấy được key cần xác minh | Không xử lý webhook/message chưa xác minh |
| Audit sink | Không ghi được audit event bắt buộc | Với action nhạy cảm, có thể dừng trước commit hoặc dùng durable local outbox |

Không phải mọi dependency đều cần fail-closed tuyệt đối. Điều quan trọng là phân loại theo tác động: nếu lỗi có thể làm lộ dữ liệu, cấp quyền hoặc tạo side effect không thể đảo ngược, phải dừng hoặc dùng cơ chế dự phòng đã chứng minh an toàn.

### 5.1. Cache authorization decision

Cache có thể giảm latency nhưng cũng làm quyết định cũ tiếp tục hiệu lực sau khi quyền bị thu hồi. Cần xác định key cache gồm principal, action, resource, tenant và policy version phù hợp; TTL ngắn theo rủi ro; invalidation khi role/permission thay đổi; và hành vi khi cache miss hoặc backend lỗi.

Không dùng một cache key chỉ gồm `userId` cho mọi object. Không để decision `ALLOW` của resource A được tái sử dụng cho resource B. Với action nhạy cảm, cần kiểm tra lại quyền gần thời điểm side effect và xử lý race condition khi quyền bị thu hồi.

### 5.2. Local token verification không phải bypass

Nếu introspection service tạm lỗi, một resource server có thể xác minh JWT cục bộ khi có signing key tin cậy, kiểm tra thuật toán, issuer, audience, expiry và các claim bắt buộc. Đây là một cơ chế xác minh khác đã được thiết kế trước, không phải bỏ qua authentication. Với opaque token không thể xác minh cục bộ, không tự coi token là hợp lệ chỉ vì introspection timeout.

## 6. Validation error không có nghĩa bỏ qua validation

Client không được diễn giải lỗi validation như chỉ dẫn để bỏ field bảo vệ hoặc gửi payload rộng hơn. Server phải validate mọi request độc lập với frontend.

Các lỗi dễ tạo bypass:

- Validation thất bại ở một field nên client bỏ toàn bộ field đó rồi gửi lại; field đó thực chất là `tenantId`, `ownerId` hoặc `role` do server quản lý.
- Backend không parse được request nên fallback sang DTO/entity khác ít ràng buộc hơn.
- Một version cũ chấp nhận field bị cấm trong version mới.
- Lỗi kiểm tra object reference khiến code bỏ qua object authorization để tiếp tục cập nhật.
- Validation service lỗi nên API nhận dữ liệu nguyên bản.

Server nên dùng DTO allowlist, reject unknown/sensitive fields theo contract và kiểm tra business rule trước side effect. Nếu field không hợp lệ, trả public error code ổn định; không tự xóa field rồi tiếp tục thao tác nhạy cảm.

Ví dụ không an toàn:

```java
try {
    validator.validate(request);
} catch (ValidationException ex) {
    // Unsafe: keep processing with unvalidated input.
}
service.update(request);
```

Ví dụ an toàn hơn:

```java
Set<ConstraintViolation<UpdateRequest>> violations =
    validator.validate(request);

if (!violations.isEmpty()) {
    throw new RequestValidationException("VALIDATION_FAILED");
}

authorization.requireCanUpdate(actor, resource);
service.update(request);
```

Thứ tự cụ thể giữa validation và authorization có thể được điều chỉnh để tránh tiết lộ object ngoài quyền, nhưng cả hai phải hoàn tất trước side effect. Không được bắt exception rồi tiếp tục bằng input chưa được kiểm tra.

## 7. Error response không được trở thành oracle

Khác biệt về lỗi có thể tiết lộ account, object, tenant, permission hoặc trạng thái nội bộ. Attacker có thể dùng endpoint lỗi để dò dữ liệu rồi chọn đường bypass phù hợp.

Ví dụ:

- `404 Order not found` cho ID không tồn tại nhưng `403 Order belongs to another tenant` cho ID có thật.
- `EMAIL_NOT_REGISTERED` cho email chưa có account và `INVALID_PASSWORD` cho email tồn tại.
- `API_KEY_REVOKED` khác `API_KEY_UNKNOWN`, giúp dò key prefix.
- `Validation failed: internal field isAdmin is supported` tiết lộ model và field quyền.
- Error response trả tên policy rule hoặc tên role khiến attacker điều chỉnh request.

Theo threat model, có thể dùng response masking để các trường hợp không nên phân biệt trả cùng status/code/message. Ví dụ object ngoài tenant có thể trả `404` giống object không tồn tại. Tuy nhiên, vẫn ghi reason chi tiết trong audit/log nội bộ có kiểm soát.

Không chỉ so sánh body. Timing, response size, header, retry behavior và side effect khác nhau cũng có thể tạo oracle. Không cần làm mọi nhánh có thời gian tuyệt đối bằng nhau, nhưng tránh khác biệt lớn không cần thiết làm lộ trạng thái.

### 7.1. Không trả implementation detail

Không đưa stack trace, SQL, table/column name, filesystem path, framework exception, rejected value, token hoặc raw upstream body vào response. Client cần `code` ổn định và thông tin có thể hành động; đội vận hành cần correlation ID để tra log nội bộ đã redact.

Ví dụ:

```json
{
  "type": "https://api.example.com/problems/access-denied",
  "title": "Request cannot be completed",
  "status": 404,
  "code": "RESOURCE_NOT_AVAILABLE",
  "traceId": "01J..."
}
```

Thông điệp public có thể chung hơn reason nội bộ. Không dùng trace ID làm token truy cập log hoặc tài nguyên.

## 8. Retry không được lặp side effect hoặc vượt quota

Client và service thường retry khi gặp timeout, `429`, `502`, `503` hoặc `504`. Retry sai có thể biến một lỗi tạm thời thành nhiều side effect hoặc làm quá tải dependency.

### 8.1. Chỉ retry lỗi phù hợp

- Lỗi validation `400/422`: sửa request trước khi gửi lại; không retry cùng payload liên tục.
- `401`: thực hiện flow refresh/re-authentication đã thiết kế, giới hạn số lần; không chuyển sang anonymous fallback.
- `403`: không retry bằng credential/endpoint rộng hơn; cần permission phù hợp.
- `404`: không suy luận object có thể được truy cập qua endpoint khác.
- `409`: đọc trạng thái mới hoặc giải quyết conflict theo contract; không lặp thao tác mù quáng.
- `429`: tôn trọng `Retry-After`, backoff và quota; không xoay IP/key để né giới hạn.
- `5xx`/timeout: chỉ retry thao tác có semantics an toàn hoặc có idempotency key.

### 8.2. Idempotency cho thao tác có side effect

Với tạo payment, refund, gửi thông báo, tạo export job hoặc thay đổi trạng thái, dùng idempotency key/operation ID ổn định qua retry. Server phải lưu kết quả hoặc trạng thái operation để cùng key không tạo side effect lần nữa. Key cần scope theo principal/tenant và action; cùng key nhưng payload khác phải bị từ chối theo contract.

Timeout không chứng minh thao tác chưa xảy ra. Server có thể đã commit database hoặc gọi provider trước khi response bị mất. Client nên truy vấn operation status hoặc retry cùng idempotency key, không tạo request mới với key khác để “thử lại”.

### 8.3. Không retry bằng endpoint yếu hơn

Một số client có fallback như:

```text
POST /v2/payments/{id}/refund -> 403
POST /v1/payments/{id}/cancel -> 200
```

Nếu v1 không kiểm tra permission tương đương, fallback đã trở thành bypass. Provider phải bảo đảm policy trên mọi version; client phải dừng khi bị từ chối thay vì tự dò endpoint khác.

## 9. Circuit breaker và fallback an toàn

Circuit breaker có thể mở khi dependency lỗi liên tục. Nó ngăn request tiếp tục làm quá tải dependency, nhưng không quyết định rằng nghiệp vụ được phép bỏ qua dependency.

Ví dụ:

- Authorization circuit mở: trả `503` hoặc từ chối action nhạy cảm.
- Recommendation service circuit mở: có thể trả nội dung không cá nhân hóa nếu không ảnh hưởng quyền hoặc dữ liệu riêng tư.
- Fraud engine circuit mở: áp policy dự phòng đã phê duyệt, ví dụ yêu cầu step-up hoặc giữ giao dịch ở trạng thái pending; không tự động bỏ kiểm tra với mọi giao dịch.
- Audit sink circuit mở: dùng durable outbox/local buffer có giới hạn nếu policy cho phép; không âm thầm bỏ audit bắt buộc.

Fallback cần được review như một nhánh bảo mật riêng. Kiểm tra rằng fallback không thay đổi tenant, actor, permission, dữ liệu được trả về hoặc side effect. Ghi metric mỗi lần fallback được kích hoạt và alert khi vượt ngưỡng.

## 10. Lỗi giữa các service và propagation của security context

Trong hệ thống nhiều service, service A có thể gọi service B để kiểm tra hoặc thực hiện action. Nếu B trả lỗi, A không được tự giả định request đã được B chấp thuận.

Các nguyên tắc:

- Truyền identity/delegation context đã được ký hoặc xác minh qua trust channel.
- Mỗi service xác minh audience, issuer, expiry và scope phù hợp.
- Không tin header role/tenant do caller bên ngoài tự khai.
- Propagate correlation ID để điều tra, nhưng correlation ID không cấp quyền.
- Nếu downstream authorization từ chối, upstream không được đổi sang service account rộng hơn để thực hiện thay caller.
- Nếu downstream timeout, không ghi nhận action thành công hoặc phát event “completed” khi chưa có kết quả xác nhận.
- Với thao tác bất đồng bộ, message consumer vẫn kiểm tra producer, tenant, authorization và business state.

Một service account có quyền rộng có thể làm mất attribution nếu dùng thay user mà không có delegation. Nếu service được phép thực hiện action thay mặt user, phải ghi rõ `actor`, `subject`, `caller` và delegation proof theo audit model.

## 11. GraphQL, batch API và partial errors

Một số giao thức không thể hiện lỗi giống REST. GraphQL thường có thể trả HTTP `200` cùng trường `errors`, và `data` có thể là partial result. Client chỉ kiểm tra `response.ok` rồi dùng `data` có thể bỏ qua lỗi ở resolver nhạy cảm.

Server phải áp dụng authorization tại từng resolver/field và object, không dựa vào client có đọc `errors` hay không. Nếu một field bị cấm, resolver không trả dữ liệu nhạy cảm dù client bỏ qua lỗi.

Với batch API:

- Mỗi item phải được authorize và validate độc lập.
- Không để lỗi một item làm hệ thống bỏ kiểm tra cho các item còn lại.
- Response phải phân biệt item thành công, bị từ chối và chưa xử lý.
- Retry batch cần operation/item ID để tránh lặp side effect của item đã thành công.
- Không trả partial success nếu trạng thái transaction thực tế là unknown.

Với gRPC, message queue hoặc RPC khác, status code có thể khác HTTP nhưng nguyên tắc giữ nguyên: status `UNAVAILABLE` không có nghĩa authorization được cho phép; `PERMISSION_DENIED` không được xử lý bằng fallback quyền rộng hơn; retry cần idempotency.

## 12. Error handling ở frontend: trách nhiệm đúng phạm vi

Client nên xử lý lỗi để hướng dẫn người dùng và giữ trải nghiệm nhất quán:

| Error | Hành vi client phù hợp | Điều client không được làm |
|---|---|---|
| `400/422` | Hiển thị field error, yêu cầu sửa input | Bỏ field bị cấm rồi gửi tiếp request nhạy cảm |
| `401` | Refresh token theo flow giới hạn hoặc yêu cầu login lại | Bỏ credential rồi tiếp tục action cần auth |
| `403` | Hiển thị không đủ quyền, cung cấp đường yêu cầu access | Dò endpoint legacy hoặc role rộng hơn |
| `404` | Hiển thị không tìm thấy/không khả dụng theo contract | Thử ID/tenant khác để enumerate |
| `409` | Hiển thị conflict và tải lại state nếu phù hợp | Lặp side effect mù quáng |
| `429` | Backoff và tôn trọng `Retry-After` | Xoay IP, API key hoặc account để né quota |
| `5xx`/timeout | Báo lỗi tạm thời, retry có giới hạn khi an toàn | Giả định thao tác thất bại và tạo operation mới |

Không lưu error response nhạy cảm vào analytics hoặc client log công khai. Không hiển thị raw `detail` nếu server contract không đảm bảo nội dung an toàn; ưu tiên map `code` sang thông điệp đã kiểm soát ở client.

## 13. Không để error path bỏ qua audit và data protection

Một request bị từ chối cũng có thể cần audit, đặc biệt với action nhạy cảm hoặc pattern abuse. Tuy nhiên, audit log phải có giới hạn và không ghi secret.

Ghi nhận phù hợp:

- Principal/service identity, tenant và endpoint/action.
- Object reference đã được chuẩn hóa hoặc pseudonymized khi cần.
- Decision: allow, deny, unavailable, validation failure hoặc fallback.
- Public error code và internal reason code riêng.
- Correlation/operation ID và thời điểm.
- Dependency/circuit breaker state nếu liên quan.
- Có thực hiện side effect hay không và trạng thái transaction.

Không ghi password, token, API key, cookie, private key, full request body hoặc rejected value nhạy cảm. Dùng structured logging, redaction, access control và retention rõ ràng. Tránh log injection từ chuỗi lỗi hoặc dữ liệu client.

Nếu audit bắt buộc là một phần của kiểm soát, không được bỏ audit chỉ vì audit service lỗi. Có thể dùng transactional outbox hoặc durable local queue có giới hạn; nếu không thể bảo đảm ghi nhận, dừng action có rủi ro cao theo policy.

## 14. Thiết kế error contract nhất quán

Error response nên có public code ổn định, HTTP status đúng semantics và trace ID để support tra cứu. Ví dụ:

```json
{
  "type": "https://api.example.com/problems/authorization-unavailable",
  "title": "Service temporarily unavailable",
  "status": 503,
  "detail": "The request cannot be completed right now.",
  "code": "AUTHORIZATION_UNAVAILABLE",
  "traceId": "01J..."
}
```

Không trả `ALLOW` hoặc `DENY` giả định khi policy engine không có kết quả. Không dùng HTTP `200` cho một thao tác thất bại nếu client có thể hiểu nhầm là đã hoàn thành. Nếu API có async operation, trả trạng thái `PENDING` chỉ khi operation thực sự đã được ghi bền vững và có operation ID để truy vấn.

### 14.1. Phân biệt public code và internal reason

Ví dụ:

| Internal reason | Public code/status có thể dùng |
|---|---|
| Token expired/invalid | `AUTHENTICATION_REQUIRED` / `401` |
| Permission denied | `ACCESS_DENIED` / `403` |
| Object ngoài tenant và policy che giấu | `RESOURCE_NOT_AVAILABLE` / `404` |
| Policy service timeout | `AUTHORIZATION_UNAVAILABLE` / `503` |
| Validation rule fail | `VALIDATION_FAILED` / `400` hoặc `422` |
| State transition không hợp lệ | `STATE_CONFLICT` / `409` |
| Quota vượt | `RATE_LIMITED` / `429` |
| Dependency lỗi không liên quan quyền | `UPSTREAM_UNAVAILABLE` / `503` hoặc status phù hợp |

Mapping phải nhất quán và được tài liệu hóa. Không gộp mọi lỗi thành `500`, vì client sẽ khó xử lý; cũng không biến lỗi nội bộ thành `4xx` để tránh phải điều tra server.

## 15. Kiểm thử error path như một phần của security test

Happy-path test không đủ. Với mỗi kiểm soát quan trọng, cần kiểm thử cả khi nó từ chối, timeout, trả dữ liệu không hợp lệ hoặc bị bypass ở client.

| Kịch bản | Kết quả mong đợi |
|---|---|
| User thiếu permission nhận `403` | Không có side effect; endpoint khác cũng kiểm tra cùng policy |
| Client bỏ qua UI và gọi API trực tiếp | Server vẫn từ chối theo authorization |
| Authorization service timeout | Action nhạy cảm fail-closed hoặc safe degraded theo policy đã duyệt |
| Token introspection lỗi | Không chấp nhận token chưa xác minh |
| Authorization cache stale sau revoke | Quyền bị thu hồi có hiệu lực theo SLA/policy; không dùng cache vô hạn |
| Validation service lỗi | Input không được xử lý như hợp lệ mặc định |
| Client thử endpoint legacy sau `403` | Legacy endpoint cũng từ chối theo policy hiện hành |
| Client đổi tenant/header sau `404` | Không đọc được object ngoài tenant |
| Rate limiter unavailable | Emergency cap hoặc reject; không mở quota vô hạn |
| `429` được retry | Backoff, tôn trọng `Retry-After`, không tạo request storm |
| Timeout sau khi payment đã commit | Cùng idempotency key không capture/refund lần hai |
| Retry `401` | Refresh flow giới hạn; không fallback anonymous |
| Retry `403` | Không dùng role/API key rộng hơn |
| GraphQL partial error | Field nhạy cảm không bị trả; client xử lý errors/data đúng contract |
| Batch có một item bị cấm | Item bị cấm không side effect; item khác theo policy độc lập |
| Audit sink lỗi | Durable audit fallback hoặc action nhạy cảm bị dừng |
| Error body có internal exception | Response không lộ stack trace/SQL/secret |
| Object tồn tại khác tenant và không tồn tại | Response masking theo policy, không có enumeration oracle rõ ràng |
| Fallback/circuit breaker kích hoạt | Không thay đổi actor, tenant, permission hoặc data scope |
| Message consumer gặp authorization error | Message bị quarantine/DLQ theo policy; không áp dụng side effect |

### 15.1. Fault injection

Trong môi trường test, chủ động làm authorization service, token introspection, rate limiter, audit sink và downstream provider timeout hoặc trả lỗi. Xác minh API không chuyển sang allow mặc định. Kiểm tra cả crash window trước/sau transaction commit và retry của client.

### 15.2. Test mọi phiên bản và entry point

Chạy negative authorization tests cho REST v1/v2, GraphQL, batch, webhook, message consumer và admin API. Đảm bảo không có một phiên bản hoặc đường xử lý lỗi cũ hơn bỏ qua kiểm soát mới.

### 15.3. Kiểm tra side effect

Không chỉ assert status code. Kiểm tra database, outbox, queue, payment sandbox, email sink hoặc audit record để xác minh request bị từ chối không thay đổi dữ liệu. Với timeout, xác minh operation state để biết đã commit hay chưa.

## 16. Giám sát và xử lý sự cố

Theo dõi:

- Tỷ lệ `401`, `403`, `404`, `409`, `429` và `5xx` theo endpoint/client/tenant.
- Authorization dependency timeout, error và circuit breaker state.
- Số lần fail-closed, safe degraded và fallback activation.
- Client retry count, refresh-token loop và request trùng.
- Idempotency hit/conflict và duplicate side effect bị ngăn.
- Request gọi legacy endpoint sau khi version mới trả deny.
- Error response có kích thước bất thường hoặc internal reason lặp lại.
- Audit write failure và outbox backlog.
- GraphQL partial errors và batch partial success.

Alert khi một dependency bảo mật bị lỗi kéo dài, fallback tăng đột biến, một client liên tục thử endpoint khác sau `403`, retry storm xuất hiện hoặc có side effect sau một quyết định deny. Dashboard nên phân biệt public code và internal reason để điều tra mà không lộ reason chi tiết cho caller.

Runbook xử lý:

1. Xác định endpoint, actor, tenant, operation ID và dependency lỗi.
2. Kiểm tra action có được thực hiện hay không, dựa trên transaction/audit state.
3. Giữ fail-closed cho action nhạy cảm; không bật bypass chung để khôi phục availability.
4. Nếu cần degraded mode, giới hạn rõ action, tenant, thời gian và người phê duyệt.
5. Đối soát các request timeout có thể đã commit side effect.
6. Khôi phục dependency, kiểm tra retry backlog và replay an toàn.
7. Thu hồi mọi credential hoặc cấu hình tạm thời được dùng trong incident.
8. Ghi audit, root cause và regression test để ngăn tái diễn.

## 17. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Client là nơi duy nhất kiểm tra quyền | Gọi API trực tiếp bỏ qua UI | Server-side authorization ở mọi endpoint |
| Authorization timeout thì allow | Dependency outage thành quyền truy cập | Fail-closed hoặc safe degraded có giới hạn |
| `403` thì gọi endpoint legacy | Bypass policy mới | Áp policy nhất quán qua mọi version |
| `401` thì bỏ token và tiếp tục | Anonymous fallback thực hiện action cần auth | Re-authenticate hoặc dừng |
| Validation exception bị catch rồi tiếp tục | Input chưa kiểm tra vẫn tạo side effect | Reject request và dừng flow |
| Rate limiter lỗi thì bỏ giới hạn | Abuse và chi phí tăng không kiểm soát | Emergency cap hoặc reject |
| Retry timeout với operation ID mới | Side effect bị thực hiện nhiều lần | Stable idempotency key và operation status |
| GraphQL HTTP 200 bị coi là thành công toàn phần | Partial error che giấu field thất bại | Kiểm tra `errors` và authorize ở resolver |
| Audit lỗi thì bỏ audit | Mất dấu vết action nhạy cảm | Durable outbox hoặc fail-closed theo policy |
| Error body tiết lộ object/permission | Enumeration và policy discovery | Public code masking, internal reason trong log |
| Fallback dùng service account rộng | Mất user attribution và privilege escalation | Verified delegation và least privilege |

## 18. Checklist review: client không được dùng lỗi để bỏ qua kiểm soát

- [ ] Authentication, authorization và tenant isolation được thực thi tại server cho mọi request.
- [ ] UI/client validation chỉ là hỗ trợ trải nghiệm, không phải security boundary.
- [ ] Dependency phục vụ quyết định quyền/token/signature không thể lỗi rồi mặc định allow.
- [ ] Safe degraded mode có action scope, data scope, TTL, owner, audit và test.
- [ ] `401`, `403`, `404`, `409`, `429` và `5xx` có semantics/documentation rõ.
- [ ] Client không fallback sang endpoint/version/credential yếu hơn sau lỗi bảo mật.
- [ ] Validation failure không bị catch rồi tiếp tục xử lý input chưa được kiểm tra.
- [ ] Retry có budget, backoff, `Retry-After` và idempotency cho side effect.
- [ ] Timeout được xem là trạng thái operation chưa chắc chắn; có operation status/reconciliation.
- [ ] Authorization cache có key theo principal/action/resource/tenant, TTL và invalidation.
- [ ] Error response không tạo account/object/permission oracle và không lộ implementation detail.
- [ ] GraphQL, batch, message consumer, webhook và admin path có kiểm soát tương đương.
- [ ] Audit failure có durable fallback hoặc policy dừng action nhạy cảm.
- [ ] Test fault injection, direct API call, legacy fallback, cross-tenant và side effect state.
- [ ] Monitoring phát hiện fail-open, fallback, retry storm, deny bypass và audit backlog.

Client có thể dùng lỗi để quyết định nên hiển thị thông báo gì, yêu cầu đăng nhập lại hay thử lại một operation an toàn. Client không được dùng lỗi làm lý do bỏ authentication, authorization, validation, quota hoặc business invariant. Server phải giữ các kiểm soát đó trên mọi endpoint và mọi nhánh thực thi, kể cả khi dependency timeout, response không đầy đủ, client retry hoặc hệ thống đang ở chế độ phục hồi. Khi error contract rõ ràng, fallback có giới hạn và side effect được kiểm tra transactionally, lỗi sẽ giúp hệ thống phục hồi mà không trở thành đường vòng để vượt qua bảo mật.
