# Theo dõi client vượt quota hoặc gọi endpoint đắt

Một API có thể hoạt động bình thường ở mức trung bình nhưng vẫn bị một client, tenant hoặc integration tiêu thụ phần lớn tài nguyên. Một API key gọi liên tục endpoint export, một tenant gửi batch lớn, một worker lặp truy vấn tìm kiếm tốn kém hoặc một nhóm request làm phát sinh nhiều lời gọi downstream có thể đẩy CPU, database connection, queue và chi phí vận hành lên cao. Nếu chỉ nhìn tổng request mỗi giây, hệ thống khó xác định ai đang tạo tải, endpoint nào gây tốn kém và hành động nào cần được thực hiện.

Theo dõi client vượt quota hoặc gọi endpoint đắt là việc kết hợp **usage metering, resource-cost telemetry, rate-limit decision và cảnh báo theo actor/endpoint**. Mục tiêu là phát hiện hành vi bất thường đủ sớm, bảo vệ tính sẵn sàng và công bằng giữa các client, đồng thời tránh khóa nhầm người dùng hợp lệ dùng chung IP hoặc có đợt tải tăng theo mùa vụ.

Trong phạm vi `SECURITY_API_SECURITY`, giám sát phải gắn với endpoint, object và luồng nghiệp vụ. Một request `GET` đơn giản và một request tạo báo cáo lớn không có cùng chi phí; một tenant có quota riêng; một API key đại diện cho integration; và một user có thể tạo tải qua nhiều endpoint. Cần đo đúng đơn vị sử dụng và liên kết metric với danh tính đã xác thực, thay vì coi mọi request có trọng số như nhau.

## 1. Vì sao cần theo dõi quota và endpoint đắt?

Monitoring trả lời các câu hỏi:

- Client hoặc tenant nào đang dùng phần lớn request budget?
- Endpoint nào có chi phí CPU, database, storage hoặc downstream cao?
- Client đang vượt quota do traffic hợp lệ tăng, retry loop hay hành vi abuse?
- Request bị từ chối bởi giới hạn nào: user, API key, tenant, endpoint, IP hay global capacity?
- Một client đang gọi endpoint đắt nhiều hơn baseline của chính nó hay không?
- Hệ thống có còn đủ worker, connection, queue và ngân sách để phục vụ client khác?
- Khi quota bị vượt, response có đúng contract và có hướng dẫn retry phù hợp không?

Không phải mọi lần vượt quota đều là tấn công. Quota có thể được thiết kế để từ chối request bình thường khi client đã dùng hết ngân sách. Điều cần cảnh báo là pattern có nguy cơ gây hại: vượt lặp lại, chi phí tăng bất thường, phân bố tải mất cân bằng, retry storm, nhiều key được tạo để né giới hạn hoặc một endpoint đang làm suy giảm dịch vụ.

### 1.1. Phân biệt quota enforcement và incident

| Tình huống | Ý nghĩa | Phản ứng giám sát |
|---|---|---|
| Một client chạm quota theo hợp đồng | Hạn mức hoạt động đúng | Ghi usage và trả `429` theo contract; thường không cần page on-call |
| Nhiều client cùng chạm quota do traffic tăng | Có thể là đỉnh tải hợp lệ hoặc capacity không đủ | Kiểm tra baseline, capacity và tỷ lệ lỗi |
| Một client liên tục vượt quota sau khi đã nhận `429` | Có thể là retry loop hoặc cố tình gây tải | Cảnh báo theo client, kiểm tra retry behavior và áp policy phù hợp |
| Một endpoint đắt tăng mạnh cost/request | Có thể do query plan, payload hoặc abuse | Điều tra endpoint, request pattern và downstream |
| Một tenant chiếm phần lớn worker/queue | Có nguy cơ noisy neighbor | Kiểm tra tenant budget, concurrency và fairness |
| Rate limiter hoặc metering store lỗi | Hệ thống mất khả năng đo/enforce đáng tin | Cảnh báo hạ tầng; áp emergency cap hoặc fail-safe theo policy |

## 2. Xác định client và phạm vi quota đáng tin cậy

Muốn biết ai đang tiêu thụ tài nguyên, cần phân biệt các loại identity. Không dùng một trường `clientId` do request tự gửi làm căn cứ duy nhất.

| Identity/signal | Đại diện cho | Vai trò trong metering |
|---|---|---|
| API key ID | Một credential/integration đã xác thực | Theo dõi usage và quota của key |
| OAuth client ID | Ứng dụng hoặc workload được cấp quyền | Theo dõi traffic service/application |
| User/principal ID | Người dùng đã xác thực | Hạn mức theo tài khoản và hành vi cá nhân |
| Tenant/account ID | Khách hàng hoặc tổ chức | Quota tổng, fairness và chi phí ở cấp khách hàng |
| Service account/workload ID | Một service nội bộ | Quota và budget service-to-service |
| Session ID | Phiên hoạt động | Phát hiện burst và retry trong phiên |
| IP address | Điểm ra mạng quan sát được | Tín hiệu phụ cho anonymous traffic và burst |
| Endpoint/action | Chức năng được gọi | Phân bổ cost theo loại nghiệp vụ |

Sau authentication, lấy API key ID, client ID, principal và tenant từ security context hoặc mapping server-side đã xác minh. Không tin `X-Client-Id`, `X-Tenant-Id`, `userId` hoặc `plan` trong body/header nếu caller có thể tự đặt chúng.

### 2.1. Kết hợp nhiều chiều

Một request có thể được đo ở nhiều phạm vi:

```text
tenant:T15
  client:reporting-integration
    api_key:key-42
      principal:user-91
        endpoint:POST /v1/reports/export
          action:export-large-report
```

Mỗi tầng bảo vệ một mục tiêu khác nhau:

- Per-user giúp phát hiện một user tạo burst.
- Per-key/per-client giúp giới hạn integration có hành vi bất thường.
- Per-tenant ngăn chia nhỏ key hoặc user để vượt quota tổng.
- Per-endpoint phản ánh chi phí khác nhau giữa các chức năng.
- Global capacity bảo vệ toàn bộ service khi hạ tầng gần bão hòa.
- IP là tín hiệu tổng hợp, hữu ích trước authentication nhưng có thể đại diện cho nhiều người dùng qua NAT/CGNAT/VPN.

Không tự động block mọi người trên một IP chỉ vì tổng traffic cao. Với mạng chia sẻ, hãy ưu tiên quota theo principal/client/tenant và dùng IP để phát hiện burst, không coi IP là một người dùng.

### 2.2. Key rotation và identity continuity

Khi API key được rotate, hệ thống có thể nhìn thấy key ID cũ và mới. Cần quyết định quota thuộc về credential hay integration. Nếu quota thuộc integration, map cả key cũ/mới về cùng client identity trong giai đoạn overlap để rotation không tạo thêm ngân sách. Nếu quota thật sự theo từng key, phải tài liệu hóa rõ và tránh cho phép tạo key mới để né hạn mức tenant.

Không ghi API key secret vào log hoặc metric. Chỉ dùng key ID/credential ID không bí mật và có quyền truy cập phù hợp.

## 3. Phân biệt quota, rate limit, concurrency và budget

Các giới hạn thường được gọi chung là quota nhưng đo những thứ khác nhau.

| Cơ chế | Đo lường | Ví dụ |
|---|---|---|
| Rate limit | Số request trong một khoảng thời gian | 120 request/phút/client |
| Quota | Tổng lượng sử dụng trong chu kỳ | 50.000 cost unit/tháng/tenant |
| Concurrency limit | Số operation đang chạy cùng lúc | Tối đa 3 export job đồng thời/client |
| Resource budget | Chi phí hoặc tài nguyên được phép tiêu thụ | 10.000 CPU-ms hoặc 2 GB dữ liệu export/ngày |
| Payload/query limit | Kích thước hoặc độ phức tạp đầu vào | Body tối đa 1 MB, query depth tối đa 8 |
| Queue budget | Số job/message chờ xử lý | Tối đa 100 job pending/tenant |

Rate limit không thay quota dài hạn. Một client có thể gửi request thấp hơn giới hạn mỗi phút nhưng tiêu thụ hàng triệu cost unit trong tháng. Ngược lại, một burst ngắn có thể vượt rate limit nhưng tổng quota vẫn còn. Concurrency limit bảo vệ worker và connection pool khi operation kéo dài; quota không tự ngăn nhiều job chạy đồng thời.

## 4. Xác định endpoint đắt bằng cost model

Không nên giả định mỗi HTTP request có cùng chi phí. Một endpoint có thể rất đắt dù request rate thấp.

### 4.1. Các yếu tố tạo chi phí

- CPU và thời gian xử lý ứng dụng.
- Số query database, số row đọc/ghi và thời gian lock.
- Số lời gọi downstream, fan-out và retry.
- Số object hoặc record phải serialize.
- Kích thước response và dữ liệu truyền qua mạng.
- Dung lượng file upload/download, decompression và parser work.
- Số trang, độ sâu hoặc độ phức tạp của GraphQL query.
- Số report/export job và thời gian worker chiếm dụng.
- Chi phí provider bên ngoài như SMS, email, OCR, AI hoặc payment lookup.
- Storage, queue retention và chi phí xử lý bất đồng bộ.

Ví dụ:

| Endpoint | Chi phí tương đối | Vì sao |
|---|---|---|
| `GET /v1/profile` | Thấp | Đọc một record nhỏ, response ngắn |
| `GET /v1/orders?pageSize=20` | Trung bình | Query có pagination và mapping |
| `POST /v1/reports/export` | Cao | Đọc nhiều record, tổng hợp và tạo file |
| `POST /v1/search/advanced` | Biến động | Query phức tạp, filter và join tùy input |
| `POST /v1/documents/ocr` | Cao | Upload, parse, OCR và provider cost |
| `POST /v1/ai/summarize` | Rất biến động | Token/input length và model cost thay đổi |

### 4.2. Gán cost unit theo endpoint/action

Có thể tạo một đơn vị cost nội bộ để đo ngân sách tương đối. Ví dụ minh họa:

| Action | Cost unit tham khảo |
|---|---:|
| Đọc profile | 1 |
| Đọc trang danh sách nhỏ | 2 |
| Tìm kiếm nâng cao | 5–20 |
| Export báo cáo lớn | 50–500 |
| OCR một tài liệu | 100–1.000 |

Các con số chỉ minh họa, không phải định mức chung. Cost unit nên được hiệu chỉnh bằng profiling, load test, query plan và chi phí provider thực tế. Nếu chi phí phụ thuộc input, dùng cost estimate theo số row, page, token, file size hoặc query complexity thay vì một trọng số cố định.

### 4.3. Ước tính trước và đối soát sau

Với operation đắt, có thể ước tính cost trước khi chạy để quyết định có đủ budget không. Sau khi hoàn tất, đo actual cost và đối soát:

1. Validate request và giới hạn input.
2. Ước tính cost dựa trên kích thước/độ phức tạp đã kiểm tra.
3. Reserve cost unit atomically trong quota store.
4. Thực hiện operation với CPU/time/row/byte limit.
5. Ghi actual cost và settle reservation.
6. Hoàn lại phần reservation chưa dùng nếu policy cho phép.
7. Nếu operation fail, áp quy tắc hoàn quota rõ ràng và audit.

Không reserve sau khi bắt đầu xử lý vì nhiều request đồng thời có thể cùng nhìn thấy quota còn trống rồi vượt tổng budget. Reservation cần idempotent theo operation ID để retry không tính hai lần.

### 4.4. Cost estimate không thay hard limit

Một query estimate có thể sai hoặc dữ liệu thay đổi trong lúc chạy. Vẫn cần giới hạn thực tế: timeout, max rows, max bytes, max tokens, max pages, concurrency và cancellation. Nếu actual cost vượt budget, dừng operation an toàn hoặc chuyển sang job có quota riêng; không để một estimate thấp biến thành đường chạy vô hạn.

## 5. Thiết kế telemetry cho usage và resource cost

Monitoring cần kết hợp metric, structured log, trace và usage ledger. Mỗi loại phục vụ câu hỏi khác nhau.

| Telemetry | Dùng để trả lời | Ví dụ |
|---|---|---|
| Metrics | Xu hướng, tỷ lệ, saturation và alert | Request rate, cost unit/sec, p95 latency, quota rejection |
| Structured logs | Ai đã gọi, operation nào và vì sao bị từ chối | Client ID, tenant ID, route, decision reason, operation ID |
| Distributed traces | Request tiêu tốn thời gian/chi phí ở dependency nào | DB span, downstream call, export worker span |
| Usage ledger | Tổng usage tính quota/billing và đối soát | Operation ID, meter type, units, period, adjustment |
| Audit events | Thay đổi policy/credential và thao tác quản trị | Quota update, key rotation, manual override |

Không cố nhét mọi định danh vào metric label. Metrics cần cardinality thấp và ổn định; logs/usage ledger phù hợp hơn để truy vấn một client hoặc operation cụ thể.

## 6. Metric nên thu thập

### 6.1. Request volume và outcome

```text
api_requests_total{route, method, status_class, client_tier}
api_request_duration_seconds_bucket{route, method}
api_request_body_bytes_bucket{route}
api_response_body_bytes_bucket{route}
```

`route` nên là route template như `/v1/orders/{orderId}`, không phải path thực chứa ID. `status_class` có thể là `2xx`, `4xx`, `5xx`; `client_tier` là nhóm ổn định như `free`, `standard`, `enterprise`, không phải client ID tùy ý.

Theo dõi request rate, error rate, p50/p95/p99 latency, request/response size và concurrency theo endpoint. Tổng request cao chưa chắc là vấn đề; cần xem tỷ lệ lỗi, cost và saturation.

### 6.2. Quota decision và usage

```text
api_quota_decisions_total{scope_type, decision, reason, route}
api_cost_units_total{route, client_tier}
api_quota_reservations_total{scope_type, outcome}
api_quota_reservation_units_total{route, outcome}
api_inflight_operations{route, client_tier}
```

`scope_type` có thể là `user`, `api_key`, `tenant`, `endpoint` hoặc `global`; `decision` là `allow`, `throttle`, `reject`; `reason` là mã ổn định như `rate_limit`, `monthly_quota`, `concurrency`, `cost_budget`. Không thêm raw user/tenant/key ID vào label nếu số lượng có thể lớn hoặc thay đổi liên tục.

### 6.3. Resource saturation

Với endpoint đắt, đo thêm:

- CPU time hoặc worker processing time.
- Database query count, duration và rows scanned/returned khi có thể đo an toàn.
- Downstream request count, duration, retry và error.
- Queue depth, oldest job age và worker utilization.
- Connection pool usage, lock wait và timeout.
- Bytes read/written, file size và decompressed size.
- AI/OCR token usage hoặc provider billing units nếu được phép.

Không cần instrument mọi chi tiết ở mọi request nếu overhead lớn. Chọn các chỉ số phản ánh bottleneck và có thể liên hệ với route/operation.

## 7. Tránh cardinality và rò rỉ dữ liệu trong metrics

Một lỗi phổ biến là tạo metric label như:

```text
api_requests_total{user_id="...", tenant_id="...", api_key="...", url="..."}
```

Nếu mỗi user, tenant, key hoặc URL tạo một time series riêng, cardinality tăng rất nhanh, làm tốn RAM/storage và khiến monitoring system khó hoạt động. URL còn có thể chứa ID, email, query token hoặc dữ liệu cá nhân.

Nguyên tắc:

- Label chỉ dùng nhóm có số lượng nhỏ và ổn định: route template, method, status class, client tier, region, service.
- Không dùng API key secret, access token, email, raw IP, object ID hoặc raw URL làm label.
- Client/tenant ID chi tiết dùng trong structured logs, usage ledger hoặc hệ thống analytics có kiểm soát quyền.
- Nếu cần truy vấn top client, dùng log analytics hoặc aggregation store, không tạo label không giới hạn.
- Pseudonymize ID khi cần giảm lộ danh tính; lưu ý pseudonymized ID vẫn có cardinality cao.
- Giới hạn độ dài và chuẩn hóa mọi field do client cung cấp trước khi log.

Không dùng hash của user ID để giả định metric cardinality đã thấp. Hash che nội dung nhưng vẫn tạo một time series cho mỗi user.

## 8. Structured logging để điều tra client vượt quota

Log cần đủ context để trả lời ai gọi, endpoint nào, cost bao nhiêu và decision nào được đưa ra. Một event log có thể gồm:

```json
{
  "timestamp": "2026-11-18T12:30:15.123Z",
  "event": "api.quota.decision",
  "requestId": "req-01J...",
  "operationId": "op-01J...",
  "route": "/v1/reports/export",
  "method": "POST",
  "clientId": "client-42",
  "apiKeyId": "key-17",
  "tenantId": "tenant-15",
  "principalId": "user-91",
  "quotaScope": "tenant",
  "decision": "reject",
  "reason": "cost_budget_exceeded",
  "estimatedCostUnits": 400,
  "remainingUnits": 120,
  "httpStatus": 429
}
```

Đây là ví dụ dữ liệu log nội bộ. Các ID phải lấy từ security context đã xác minh; không ghi secret hoặc token. Cần đánh giá liệu tenant/user ID có phải dữ liệu cá nhân hoặc dữ liệu nhạy cảm trong môi trường cụ thể, áp dụng pseudonymization, access control và retention phù hợp.

### 8.1. Không log raw request để tìm nguyên nhân

Không ghi toàn bộ request body, Authorization header, Cookie, API key, signed URL hoặc nội dung file chỉ để điều tra cost. Thay vào đó, ghi các đặc trưng đã chuẩn hóa như page size, filter count, query complexity score, file size bucket, token count hoặc operation type.

### 8.2. Gắn correlation và operation ID

Một request có thể tạo async job, worker gọi downstream rồi phát event. Dùng `requestId`, `operationId`, `traceId` và `causationId` phù hợp để liên kết chuỗi xử lý. Correlation ID không phải credential và không được dùng làm bằng chứng authorization.

## 9. Distributed tracing cho endpoint đắt

Metrics cho biết endpoint chậm hoặc tốn cost; trace giúp xác định phần nào tạo ra chi phí. Một trace của export job có thể gồm:

```text
HTTP POST /v1/reports/export
  ├─ authentication / authorization
  ├─ quota estimate + reservation
  ├─ database query (multiple pages)
  ├─ aggregation / serialization
  ├─ object storage upload
  └─ usage settlement + audit
```

Instrument span cho các bước quan trọng, ghi duration, outcome và kích thước/đơn vị ở dạng an toàn. Không đưa token, raw query, PII hoặc nội dung file vào span attribute. Trace sampling cần đủ để giữ các request lỗi/đắt hoặc tail-based sampling theo latency/cost; không chỉ sample ngẫu nhiên khiến operation hiếm nhưng rất đắt luôn bị bỏ qua.

Với async job, truyền trace context qua queue theo chuẩn đã chọn và tạo span mới cho worker. Không tin trace context như identity hoặc permission. Tracing giúp điều tra, còn authorization phải dựa trên credential/context đã xác minh.

## 10. Theo dõi quota utilization và mức vượt

Một quota có thể có nhiều chu kỳ và scope. Cần đo:

- Usage hiện tại và limit.
- Tỷ lệ utilization: `used / limit`.
- Remaining units.
- Tốc độ tiêu thụ gần đây.
- Dự báo thời điểm hết quota nếu tốc độ tiếp tục.
- Số lần reservation/settlement/adjustment.
- Số request bị từ chối theo scope và reason.

Ví dụ:

```text
tenant T15 monthly budget: 80,000 units
used:                       72,000 units
utilization:                    90%
recent burn rate:             4,000 units/hour
estimated remaining time:       2 hours
```

Đây là ví dụ minh họa. Forecast chỉ hữu ích khi chu kỳ còn đủ dữ liệu và usage không có biến động lớn. Không cảnh báo chỉ vì một tenant sắp hết quota nếu đây là hành vi bình thường theo hợp đồng; có thể gửi usage notification hoặc cảnh báo cho owner thay vì page on-call.

### 10.1. Đếm usage đúng khi có retry

Nếu request bị timeout sau khi operation đã commit, client có thể retry. Metering phải liên kết với operation ID/idempotency key để tránh tính hai lần cùng một logical action nếu contract yêu cầu. Nếu mỗi attempt thực sự tiêu tốn tài nguyên, có thể đo cả attempt cost và billable operation cost thành hai meter khác nhau.

Tách rõ:

- Request attempts: mọi lần gọi HTTP/RPC.
- Accepted operations: operation được chấp nhận để xử lý.
- Completed operations: operation hoàn tất.
- Resource cost: CPU/DB/bytes/provider usage thực tế.
- Billable units: đơn vị tính quota hoặc thương mại theo hợp đồng.

Không dùng một counter duy nhất cho tất cả các khái niệm. Một request bị từ chối trước khi xử lý vẫn có thể tiêu thụ một ít gateway CPU, nhưng không nhất thiết tiêu thụ cùng quota nghiệp vụ như một export thành công.

## 11. Phát hiện endpoint đắt và hành vi bất thường

Kết hợp baseline, cost model và tín hiệu bảo mật.

### 11.1. Request rate bất thường

So sánh request rate theo client/tenant với baseline lịch sử và quota. Một client tăng từ 10 lên 500 request/phút có thể đáng chú ý ngay cả khi chưa vượt giới hạn cứng. Ngược lại, client lớn có thể thường xuyên xử lý hàng nghìn request/phút một cách hợp lệ.

### 11.2. Cost/request tăng

Theo dõi average và percentile cost theo route/client tier. Nếu cùng endpoint nhưng cost/request tăng mạnh, có thể do:

- Query plan xấu hoặc thiếu index.
- Page size, filter hoặc query complexity lớn.
- Nhiều downstream call hơn bình thường.
- Retry trong service mesh/client.
- Payload lớn hoặc decompression.
- Một tenant tạo report trên tập dữ liệu bất thường.

### 11.3. Denied ratio và retry loop

Một client liên tục nhận `429` nhưng vẫn tiếp tục gửi có thể đang retry sai hoặc cố ý gây tải. Theo dõi tỷ lệ request bị reject trên tổng request, số lần retry sau `Retry-After` và số request cùng operation ID. Một vài `429` không nhất thiết là incident; tỷ lệ cao kéo dài hoặc retry tăng nhanh mới đáng cảnh báo.

### 11.4. Noisy neighbor

Theo dõi tỷ trọng cost/worker/queue của từng tenant. Nếu một tenant chiếm phần lớn worker hoặc DB connection, tenant khác có thể bị chậm dù mỗi tenant chưa vượt quota riêng. Dùng per-tenant concurrency, queue partition/fair scheduling và budget để hạn chế noisy neighbor.

### 11.5. Abuse phân tán

Attacker có thể dùng nhiều API key hoặc account để né per-key quota. Cần theo dõi tổng theo tenant, integration owner, destination/resource và operation pattern. Không chỉ dựa vào IP; nhiều người dùng hợp lệ có thể cùng NAT/CGNAT.

## 12. Alert design: cảnh báo đúng mức và đúng owner

Không page on-call cho mọi request bị từ chối bởi quota. Alert cần phản ánh rủi ro cho hệ thống hoặc khách hàng.

### 12.1. Nhóm cảnh báo

| Nhóm | Ví dụ điều kiện | Đối tượng nhận |
|---|---|---|
| Usage warning | Tenant tiến gần budget theo burn rate | Customer success/owner hoặc usage automation |
| Client abuse suspicion | Một client có denied ratio cao, retry liên tục hoặc cost tăng bất thường | API security/on-call theo mức độ |
| Endpoint saturation | p95/p99 latency, queue depth hoặc DB pool vượt baseline | Service owner/on-call |
| Global capacity risk | Nhiều route cùng timeout/5xx, worker/connection gần cạn | Incident/on-call |
| Metering/limiter failure | Không ghi được usage hoặc limiter store unavailable | Platform/SRE và security |
| Policy drift | Quota bị thay đổi bất thường hoặc enforcement bị disable | Security/platform owner |

### 12.2. Threshold và baseline

Threshold cần được hiệu chỉnh theo:

- Quota hợp đồng và plan của client.
- Baseline theo giờ/ngày/mùa vụ.
- Cost unit của endpoint.
- Số client/tenant bị ảnh hưởng.
- Thời gian duy trì vượt ngưỡng.
- Mức độ bão hòa tài nguyên.
- Tỷ lệ request bị từ chối và hành vi retry.

Có thể dùng nhiều mức: warning khi utilization gần limit; critical khi hệ thống bị bão hòa hoặc có pattern abuse rõ. Không có một tỷ lệ phần trăm hoặc số request/phút đúng cho mọi service. Chọn threshold bằng dữ liệu production, load test và error budget.

### 12.3. Tránh alert fatigue

- Gộp alert theo client/tenant/endpoint trong một cửa sổ thời gian.
- Dùng `for` duration để bỏ qua spike rất ngắn nếu không nguy hiểm.
- Suppress alert con khi đã có incident global cùng nguyên nhân.
- Deduplicate theo operation/actor/reason.
- Định tuyến cảnh báo usage đến owner phù hợp thay vì tất cả on-call.
- Tự động đóng hoặc resolve khi usage trở lại bình thường.
- Đưa runbook và dashboard link vào alert.

## 13. Ví dụ Prometheus và PromQL

Metric cần dùng label có cardinality kiểm soát. Ví dụ:

```text
api_requests_total{
  route="/v1/reports/export",
  method="POST",
  status_class="4xx",
  client_tier="standard"
}

api_cost_units_total{
  route="/v1/reports/export",
  client_tier="standard"
}

api_quota_decisions_total{
  scope_type="tenant",
  decision="reject",
  reason="cost_budget",
  route="/v1/reports/export"
}
```

Request rate theo route:

```promql
sum by (route) (
  rate(api_requests_total[5m])
)
```

Cost unit rate theo route:

```promql
sum by (route) (
  rate(api_cost_units_total[5m])
)
```

Tỷ lệ quota rejection theo route:

```promql
sum by (route) (
  rate(api_quota_decisions_total{decision="reject"}[5m])
)
/
clamp_min(
  sum by (route) (rate(api_quota_decisions_total[5m])),
  1
)
```

Ví dụ alert cho cost rate cao hơn baseline được cấu hình:

```yaml
groups:
  - name: api-cost
    rules:
      - alert: ApiEndpointCostRateHigh
        expr: sum by (route) (rate(api_cost_units_total[5m])) > 100
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: API endpoint cost rate is unusually high
          description: Review route cost, request mix and downstream usage.
```

Con số `100` và thời gian `10m` chỉ là giá trị minh họa. Alert production cần baseline/threshold theo route, plan và capacity; không sao chép một ngưỡng chung cho mọi endpoint. Nếu metric `api_quota_decisions_total` không tăng cho request được allow, cần một metric denominator riêng hoặc dùng request counter cùng semantics rõ ràng.

Không tạo label `client_id` cho hàng triệu client chỉ để viết alert per-client. Dùng usage ledger/log analytics để tìm top client, sau đó tạo alert event hoặc metric tổng hợp cho các client được chọn theo cơ chế có giới hạn.

## 14. Dashboard cho API security và cost

Một dashboard hữu ích nên có nhiều lớp:

### 14.1. Tổng quan service

- Request rate, error rate và latency p50/p95/p99.
- CPU, memory, connection pool, worker utilization.
- Queue depth, oldest job age và downstream health.
- Cost unit rate toàn service và theo route.
- Số request bị throttle/reject và lý do.

### 14.2. Theo endpoint

- Route template, method và client tier.
- Request volume, success/deny/error rate.
- Cost unit/request và total cost.
- DB query duration/rows, downstream calls và response bytes.
- Concurrency, queue wait và worker time.
- Endpoint nào đang tăng cost so với baseline.

### 14.3. Theo client/tenant

- Top client/tenant theo request volume.
- Top client/tenant theo cost units.
- Quota utilization và burn rate.
- Số lần vượt quota, retry sau `429` và denied ratio.
- Phân bố usage theo endpoint.
- Key rotation, credential status và client tier.

Chi tiết client/tenant nên lấy từ log/usage analytics có kiểm soát quyền. Dashboard không nên hiển thị secret hoặc dữ liệu cá nhân không cần thiết. Nếu dùng pseudonymous ID, cần có chức năng drill-down chỉ cho role được phép.

### 14.4. Theo dõi fairness và noisy neighbor

- Tỷ trọng CPU/worker/queue của top tenant.
- Queue wait theo tenant tier.
- Số job đang chạy và pending theo tenant.
- Tỷ lệ timeout/429 của tenant khác khi một tenant tăng tải.
- Sự chênh lệch giữa usage thực tế và budget được cấp.

## 15. Tích hợp monitoring với rate limiter và quota enforcement

Monitoring quan sát; rate limiter/quota engine thực thi. Hai thành phần cần chia sẻ cùng semantics nhưng không nên phụ thuộc vào dashboard để bảo vệ hệ thống.

### 15.1. Decision event

Mỗi quyết định quota có thể tạo một event nội bộ gồm:

```text
request_id
operation_id
principal_id / client_id / tenant_id (verified context)
route_template / action
scope_type
decision: allow | throttle | reject
reason_code
estimated_units
reserved_units
remaining_units
window_start / window_end
policy_version
```

Event này có thể dùng để audit và analytics. Cần tránh log token/secret và hạn chế quyền truy cập dữ liệu định danh. Nếu decision event được ghi bất đồng bộ, không để việc ghi telemetry làm chậm request quá mức; nhưng usage ledger phục vụ quota/billing cần durability và semantics riêng.

### 15.2. Atomic quota accounting

Khi nhiều request đồng thời cùng tiêu thụ một quota, thao tác check-then-increment không atomic có thể cho phép vượt hạn mức:

```text
if used + cost <= limit:
    used = used + cost
    allow
```

Hai worker có thể cùng đọc `used=90`, `limit=100`, `cost=8` rồi đều allow. Cần atomic reservation qua transaction, compare-and-set, Redis Lua script hoặc cơ chế tương đương. Phải xử lý timeout/retry sao cho cùng operation ID không reserve hai lần.

### 15.3. Metering và quota store lỗi

Nếu quota store unavailable, quyết định fail-open có thể làm một endpoint đắt tiêu thụ tài nguyên không giới hạn. Có thể dùng local emergency cap, cached budget có TTL ngắn hoặc từ chối action tốn kém cho đến khi phục hồi. Policy phụ thuộc rủi ro và consistency; phải được thiết kế, test và giám sát trước.

Không dùng metrics store làm nguồn sự thật cho quota nếu metrics có sampling, eventual aggregation hoặc retention ngắn. Quota enforcement cần storage có atomicity và durability phù hợp; monitoring metrics có thể được tổng hợp sau.

## 16. Response khi client vượt quota

Với rate limit hoặc quota tạm thời, HTTP `429 Too Many Requests` thường phù hợp. Có thể trả `Retry-After` nếu biết khi nào client nên thử lại:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 60
Cache-Control: no-store
```

```json
{
  "type": "https://api.example.com/problems/quota-exceeded",
  "title": "Usage limit exceeded",
  "status": 429,
  "detail": "The current request budget is exhausted. Try again later.",
  "code": "QUOTA_EXCEEDED",
  "traceId": "01J..."
}
```

Không nhất thiết trả usage chi tiết, limit nội bộ hoặc thông tin về quota của tenant khác. Nếu contract công bố quota, có thể trả header/field như remaining/reset theo chuẩn và policy đã tài liệu hóa. Không tiết lộ threshold phát hiện abuse hoặc risk score.

### 16.1. Phân biệt quota với service overload

- `429` thường chỉ ra caller vượt rate/quota policy.
- `503 Service Unavailable` phù hợp khi service không thể phục vụ do capacity hoặc dependency tạm thời.
- `413 Content Too Large` dùng khi request body vượt giới hạn kích thước.
- `408` hoặc timeout ở tầng gateway/client có semantics riêng; không dùng để che quota decision.

Không trả `429` cho mọi lỗi server vì client có thể retry theo cách không phù hợp. Cũng không trả `503` cho một client bị giới hạn theo hợp đồng nếu hệ thống vẫn phục vụ các client khác bình thường.

## 17. Runbook khi phát hiện client vượt quota hoặc endpoint đắt

Một cảnh báo cần dẫn đến quy trình điều tra cụ thể.

1. **Xác định phạm vi:** service, route, method, client, tenant, thời điểm và policy version.
2. **Kiểm tra impact:** latency, 5xx, queue, DB pool, CPU, downstream cost và số tenant bị ảnh hưởng.
3. **Xác minh identity:** client/key/tenant lấy từ security context hay metadata do caller tự khai.
4. **Phân loại pattern:** traffic hợp lệ, retry loop, client bug, query đắt, abuse có chủ đích hay capacity issue.
5. **Kiểm tra quota decision:** scope nào bị chạm, request nào được allow/reject, reservation có bị tính trùng không.
6. **Giảm blast radius:** áp per-client/tenant/action throttle, concurrency cap hoặc pause job đắt theo policy.
7. **Bảo vệ khách hàng khác:** xác minh fairness, queue isolation và global capacity.
8. **Liên hệ owner:** cung cấp request/operation ID và hướng dẫn sửa retry/query nếu là integration hợp lệ.
9. **Khôi phục và đối soát:** kiểm tra reservation, actual cost, job state và billing/usage ledger.
10. **Phòng ngừa tái diễn:** điều chỉnh cost model, query limit, alert threshold, SDK retry hoặc quota policy.

Không block toàn bộ IP ngay khi một client vượt quota, nhất là khi IP có thể là NAT/CGNAT/VPN dùng chung. Ưu tiên actor/action xác định được. Nếu có volumetric attack hoặc hạ tầng đang bị đe dọa, edge protection có thể áp giới hạn rộng hơn theo incident policy, có TTL và theo dõi collateral impact.

## 18. Kiểm thử monitoring, metering và quota

Không chỉ test rằng rate limiter trả `429`. Cần xác minh usage được ghi đúng, alert phát đúng và một client không thể làm cạn ngân sách của client khác.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Client dùng quota bình thường | Usage counter/ledger tăng đúng scope |
| Client vượt per-key quota | Chỉ key/integration bị giới hạn theo policy |
| Nhiều key cùng tenant | Tenant aggregate quota vẫn ngăn chia nhỏ key để né limit |
| Nhiều user chung IP/NAT | Quota theo principal/tenant vẫn tách biệt; không block cả nhóm chỉ vì tổng IP |
| Endpoint đắt có input nhỏ/lớn | Cost estimate và actual metering phản ánh khác biệt |
| Request bị retry cùng operation ID | Reservation/usage không bị tính trùng ngoài semantics đã định |
| Hai request đồng thời chạm quota | Atomic reservation không cho vượt do race condition |
| Quota store timeout | Emergency policy được áp dụng; không mở budget vô hạn |
| Export job vượt concurrency | Job mới bị từ chối/queue theo contract; worker hiện tại được bảo vệ |
| Query quá phức tạp | Complexity/row/time limit dừng request an toàn |
| Một tenant tạo noisy neighbor | Fair scheduling/concurrency cap bảo vệ tenant khác |
| Cost tăng bất thường nhưng request rate thấp | Cost alert phát hiện được endpoint đắt |
| Client retry liên tục sau `429` | Denied ratio/retry alert phát hiện pattern |
| Label có client ID rất lớn | Metrics cardinality không tăng không kiểm soát |
| Log chứa API key/token giả | Secret sentinel không xuất hiện trong log |
| Usage ledger và metrics lệch | Reconciliation phát hiện và phân loại sai khác |
| Client bị rotate API key | Usage continuity theo integration/tenant đúng policy |
| Alert threshold chạm ngắn | Không tạo page noise nếu chưa đủ điều kiện duy trì |

### 18.1. Load test theo cost, không chỉ request rate

Tạo workload có request count tương tự nhưng cost khác nhau: nhiều GET nhỏ so với một export lớn; query đơn giản so với query phức tạp; file nhỏ so với file lớn; một request AI ngắn so với input dài. Xác minh cost unit, concurrency và alert phản ánh mức tiêu thụ thực tế.

### 18.2. Test fairness giữa tenant

Cho một tenant tạo tải cao trong khi tenant khác gửi request bình thường. Xác minh tenant tải cao bị giới hạn theo budget của nó và tenant còn lại vẫn có latency/availability trong mục tiêu dịch vụ. Kiểm tra cả queue, connection pool và worker, không chỉ HTTP response.

### 18.3. Test alert end-to-end

Tạo synthetic usage vượt threshold trong môi trường test, xác minh alert có route, severity, context và runbook đúng. Kiểm tra deduplication, resolve, suppression và không đưa secret/PII vào nội dung alert.

## 19. Những lỗi triển khai thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Đếm mọi request như nhau | Endpoint đắt bị đánh giá thấp | Cost unit theo route/action và input |
| Chỉ theo dõi tổng RPS | Không biết client/tenant nào gây tải | Metering đa chiều và usage ledger |
| Dùng client ID do caller gửi | Có thể giả mạo attribution/quota | Identity từ authenticated context |
| Chỉ quota theo API key | Tạo nhiều key để né quota tổng | Tenant aggregate budget |
| Chỉ quota theo IP | NAT/CGNAT làm ảnh hưởng nhiều user | Principal/client/tenant limits; IP là signal |
| Check rồi increment không atomic | Request đồng thời vượt quota | Atomic reservation/idempotency |
| Tính quota sau khi chạy | Tài nguyên đã bị tiêu thụ trước khi từ chối | Reserve trước, settle sau |
| Dùng metrics làm nguồn quota | Sampling/eventual aggregation gây sai usage | Dedicated quota store/ledger |
| Đưa raw client ID vào metric label | Cardinality và storage tăng mạnh | Low-cardinality labels, log analytics |
| Alert mỗi lần có `429` | Alert fatigue | Alert theo sustained pattern/impact |
| Chỉ theo dõi request count | Bỏ sót request ít nhưng rất đắt | Cost, concurrency, rows, bytes và downstream metrics |
| Retry không idempotent | Double charge hoặc duplicate job | Stable operation ID và idempotency |
| Không có runbook | Alert không dẫn đến hành động nhất quán | Owner, scope, action và rollback rõ |

## 20. Checklist review monitoring quota và endpoint đắt

- [ ] Identity client/key/user/tenant được lấy từ context đã xác minh.
- [ ] Quota được phân biệt với rate limit, concurrency và resource budget.
- [ ] Có cost model cho endpoint đắt và các input làm chi phí biến động.
- [ ] Request được estimate/reserve trước operation đắt; actual cost được settle sau.
- [ ] Reservation và metering có atomicity/idempotency phù hợp.
- [ ] Metrics bao gồm request rate, latency, error, cost unit, quota decision và saturation.
- [ ] Route label dùng route template; metric labels có cardinality thấp.
- [ ] Không log token, API key secret, raw body, signed URL hoặc PII không cần thiết.
- [ ] Structured logs, traces, usage ledger và audit có vai trò riêng.
- [ ] Dashboard hiển thị service, endpoint, client/tenant usage và fairness.
- [ ] Alert phân biệt usage warning, client abuse, endpoint saturation, global capacity và limiter failure.
- [ ] Threshold dựa trên quota, baseline, cost và impact; không alert mọi `429`.
- [ ] Response `429`, `503`, `413` có semantics đúng và `Retry-After` khi phù hợp.
- [ ] Có runbook điều tra client, tenant, endpoint, retry và cost.
- [ ] Có test NAT/shared IP, multi-key tenant, concurrency race, endpoint cost và alert end-to-end.
- [ ] Có reconciliation giữa usage ledger, reservation, actual cost và metrics.
- [ ] Có policy emergency khi quota store/metering unavailable.
- [ ] Có cơ chế fairness để một tenant không chiếm hết worker/queue/connection.

Theo dõi quota hiệu quả cần trả lời đồng thời “ai đang gọi”, “đang gọi chức năng nào” và “mỗi thao tác tiêu tốn bao nhiêu tài nguyên”. Khi identity được xác minh, cost được đo theo endpoint/action, quota được reserve atomically và telemetry được phân tầng giữa metrics, logs, traces và usage ledger, đội vận hành có thể phát hiện client vượt hạn mức hoặc endpoint đắt trước khi nó làm suy giảm toàn hệ thống. Cảnh báo nên tập trung vào pattern và tác động thực tế, còn enforcement phải nhắm vào principal, tenant hoặc action phù hợp để bảo vệ capacity mà không gây ảnh hưởng dây chuyền cho người dùng hợp lệ.
