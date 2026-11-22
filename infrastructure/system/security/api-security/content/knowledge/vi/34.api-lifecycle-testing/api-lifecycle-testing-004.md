# Rate limit, quota và resource exhaustion test

API security không chỉ là kiểm tra một request có hợp lệ hay không. Một endpoint có thể xác thực và phân quyền đúng nhưng vẫn bị lạm dụng bằng cách gửi quá nhiều request, tạo request tốn CPU, giữ kết nối quá lâu, upload dữ liệu lớn, yêu cầu export liên tục hoặc kích hoạt nhiều lời gọi downstream. Hậu quả có thể là cạn thread, connection pool, memory, queue, storage, băng thông hoặc ngân sách của dịch vụ bên thứ ba.

Cần phân biệt ba nhóm kiểm soát:

- **Rate limit:** giới hạn tốc độ request hoặc chi phí request trong một khoảng thời gian.
- **Quota:** giới hạn tổng mức sử dụng trong một kỳ, chẳng hạn số lượt gọi, số bản ghi export hoặc dung lượng upload mỗi ngày/tháng.
- **Resource limit/admission control:** giới hạn công việc đang chạy, kích thước đầu vào, thời gian xử lý, độ sâu/độ phức tạp và tài nguyên được cấp cho request.

Kiểm thử phải chứng minh các giới hạn này hoạt động đúng ở từng endpoint, principal, client và tenant; đồng thời xác minh hệ thống vẫn phục vụ được người dùng hợp lệ khi có burst, tải kéo dài hoặc một nhóm client vượt ngưỡng. Không chỉ đếm status 429: cần quan sát latency, CPU, memory, database pool, queue depth, downstream calls và tính công bằng giữa tenant.

## 1. Phân biệt rate limit, quota và resource exhaustion

Các khái niệm liên quan nhưng không thay thế nhau:

| Kiểm soát | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Rate limit | Trong một đơn vị thời gian, client được gọi bao nhiêu lần? | 60 request/phút/client |
| Quota | Trong cả kỳ, client được sử dụng tổng cộng bao nhiêu? | 100.000 API units/tháng/tenant |
| Concurrency limit | Có bao nhiêu công việc được chạy đồng thời? | Tối đa 5 export đang chạy/tenant |
| Request size limit | Một request được mang bao nhiêu dữ liệu? | JSON body tối đa 1 MiB |
| Work/time budget | Một request được tiêu tốn bao nhiêu thời gian/CPU? | Deadline 3 giây, query cost tối đa 100 |
| Storage quota | Tổng dung lượng được lưu là bao nhiêu? | 10 GiB/file storage/tenant |
| Queue/admission limit | Có bao nhiêu công việc được xếp chờ? | Tối đa 200 job đang chờ |

Một endpoint có thể có rate limit nhưng vẫn bị resource exhaustion nếu mỗi request kích hoạt một query rất đắt. Ngược lại, một request lớn có thể bị giới hạn kích thước nhưng client vẫn gửi hàng nghìn request nhỏ. Cần nhiều lớp giới hạn phù hợp với chi phí và hành vi của từng operation.

### 1.1. Ví dụ về cách các giới hạn phối hợp

Một API export có thể áp dụng đồng thời:

- Tối đa 5 request tạo export mỗi phút cho mỗi user.
- Tối đa 20 export mỗi ngày cho mỗi tenant.
- Tối đa 2 export chạy đồng thời cho mỗi tenant.
- Tối đa 100.000 dòng mỗi export.
- Thời gian xử lý tối đa 60 giây.
- Tổng dung lượng file kết quả tối đa 500 MiB.
- Tối đa 10 job đang chờ trong queue của tenant.

Nếu chỉ có rate limit 5 request/phút, một client có thể gửi 5 export cực lớn mỗi phút và vẫn làm cạn worker. Nếu chỉ có concurrency limit, client có thể tạo vô hạn job chờ. Thiết kế phải kết hợp tốc độ, tổng lượng, kích thước và công việc đang hoạt động.

## 2. Xác định endpoint và đơn vị cần giới hạn

Không nên áp dụng cùng một ngưỡng cho mọi endpoint. Một request đọc cache có chi phí khác request tìm kiếm phức tạp, upload file, tạo báo cáo hoặc gọi dịch vụ thanh toán.

Phân loại endpoint theo đặc tính:

| Nhóm endpoint | Rủi ro chính | Giới hạn nên cân nhắc |
|---|---|---|
| Authentication/login | Credential stuffing, brute force | Theo account, IP/network, device/risk signal và global |
| OTP/password reset | Spam, chiếm dụng SMS/email | Theo account, destination, IP và ngân sách gửi |
| Read/list/search | Query tốn CPU/DB, enumeration | Request rate, page size, query cost, timeout |
| Write/mutation | Spam, duplicate side effect | Rate, idempotency, business quota |
| Bulk/export | CPU, memory, DB, storage, queue | Concurrency, row count, output size, job quota |
| File upload | Băng thông, storage, scan worker | File size, count, tenant storage quota, scan concurrency |
| URL fetch/integration | Outbound connection, SSRF, downstream cost | Host policy, request rate, bytes, timeout, concurrency |
| GraphQL | Query depth/complexity và batching | Depth, cost score, alias/batch count, execution time |
| Webhook | Retry storm, queue exhaustion | Per-source rate, concurrency, payload size, retry budget |
| Admin/maintenance | Tác động diện rộng | Role-specific rate, approval, global guardrail |

### 2.1. Chọn đúng rate-limit key

Có thể giới hạn theo một hoặc nhiều chiều:

- Principal/user ID đã xác thực.
- OAuth client ID hoặc API key ID.
- Tenant ID đã được xác minh.
- Endpoint hoặc route group.
- IP address/network cho request chưa xác thực.
- Workload identity cho service-to-service.
- Resource ID khi cần giới hạn thao tác trên một đối tượng.
- Global service budget để bảo vệ năng lực toàn hệ thống.

Một policy thực tế có thể yêu cầu đồng thời tất cả các bucket: per-user, per-tenant, per-endpoint và global. Request chỉ được chấp nhận nếu còn ngân sách ở mọi bucket cần thiết.

Không chỉ dựa vào IP cho user đã xác thực: nhiều người có thể dùng chung NAT/proxy, khiến người dùng hợp lệ bị ảnh hưởng. Ngược lại, không chỉ dựa vào user ID nếu attacker có thể tạo nhiều account. Chọn key theo threat model và khả năng nhận diện tin cậy.

### 2.2. Chỉ tin forwarded IP từ proxy đáng tin

Header như §X-Forwarded-For§ hoặc §Forwarded§ có thể bị client tự đặt. Chỉ dùng địa chỉ được proxy/load balancer nằm trong trust boundary ghi đè hoặc xác minh. Nếu backend có thể truy cập trực tiếp, phải ngăn client giả forwarded header để né rate limit hoặc gây block nhầm người khác.

Chuẩn hóa IPv4/IPv6 và cách biểu diễn địa chỉ nhất quán. Không coi header do client gửi là danh tính hoặc bằng chứng vị trí.

### 2.3. Tenant fairness

Giới hạn global đơn thuần có thể khiến một tenant lớn hoặc bị lạm dụng chiếm hết năng lực của service. Cần kiểm tra:

- Một tenant không thể tiêu hết quota của tenant khác.
- Một client vượt ngưỡng bị hạn chế mà tenant khác vẫn dùng được.
- Tenant có tier khác nhau nhận đúng quota đã công bố.
- Tạo nhiều API key trong cùng tenant không nhân quota nếu quota được tính theo tenant.
- User đổi token hoặc client ID không thể né quota gắn với tenant nếu policy yêu cầu.

## 3. Các thuật toán rate limiting

### 3.1. Fixed window counter

Đếm request trong từng cửa sổ cố định, ví dụ 60 giây. Khi bộ đếm đạt ngưỡng, từ chối đến cửa sổ kế tiếp.

Ưu điểm là đơn giản, rẻ và dễ phân phối. Nhược điểm là hiện tượng burst ở ranh giới: client có thể gửi gần hết quota ngay cuối cửa sổ rồi gửi tiếp ở đầu cửa sổ mới, tạo tải gấp đôi trong thời gian ngắn.

### 3.2. Sliding window log

Lưu timestamp của các request trong khoảng thời gian gần nhất và đếm số request còn nằm trong cửa sổ. Cách này chính xác hơn fixed window nhưng tốn bộ nhớ và thao tác lưu trữ hơn.

### 3.3. Sliding window counter

Kết hợp bộ đếm cửa sổ hiện tại và trước đó, có trọng số theo thời gian. Đây là cách xấp xỉ giúp giảm burst tại ranh giới mà không cần lưu timestamp từng request.

### 3.4. Token bucket

Bucket có dung lượng tối đa B token và được nạp lại với tốc độ r token/giây. Mỗi request tiêu thụ một hoặc nhiều token.

- Cho phép burst tối đa theo dung lượng bucket.
- Tốc độ dài hạn bị giới hạn theo refill rate.
- Có thể gán cost khác nhau cho từng operation.

Ví dụ bucket có 20 token, refill 2 token/giây: client có thể gửi burst tối đa 20 đơn vị chi phí khi bucket đầy, sau đó trung bình được cấp thêm 2 đơn vị mỗi giây.

### 3.5. Leaky bucket/GCRA

Leaky bucket hoặc Generic Cell Rate Algorithm (GCRA) kiểm soát tốc độ đầu ra theo nhịp ổn định, phù hợp khi muốn làm phẳng burst. Cần hiểu chính xác cách triển khai và dung sai burst trước khi viết test; không suy ra mọi thuật toán đều có cùng hành vi ở ranh giới.

### 3.6. Weighted rate limit

Không phải request nào cũng có cùng chi phí. Có thể tính cost:

| Operation | Cost minh họa |
|---|---:|
| GET metadata từ cache | 1 |
| Search với filter đơn giản | 2 |
| Search nhiều điều kiện | 5 |
| Export 10.000 dòng | 20 |
| Upload và scan file lớn | Theo byte/processing budget |

Client bị giới hạn theo tổng cost thay vì chỉ số request. Cost model cần được hiệu chỉnh từ profiling và đo đạc; không dùng con số minh họa làm ngưỡng production.

## 4. Thiết kế quota theo kỳ và nghiệp vụ

Quota thường có kỳ reset khác rate limit:

- Per minute/hour: chống burst và lạm dụng ngắn hạn.
- Daily/monthly: giới hạn tổng sản lượng hoặc chi phí.
- Lifetime/contract: giới hạn theo gói dịch vụ hoặc hợp đồng.
- Resource quota: tổng storage, số webhook, số API key hoặc số job.
- Budget: giới hạn tiền hoặc số đơn vị tính phí cho downstream provider.

### 4.1. Quota phải gắn với chủ thể nghiệp vụ

Nếu một tenant có nhiều user và API key, quota tenant thường phải cộng dồn trên tất cả user/key. Nếu quota gắn riêng từng API key, client có thể tạo nhiều key để nhân giới hạn. Quy định rõ quota thuộc user, client, subscription, tenant hay organization.

### 4.2. Xử lý reset và timezone

Dùng thời gian UTC và quy tắc kỳ rõ ràng. Tránh reset theo timezone do client gửi. Kiểm thử thời điểm cuối kỳ, leap day, tháng có số ngày khác nhau và thay đổi subscription/tier giữa kỳ.

Nếu quota được cấp lại khi nâng gói, cần định nghĩa phần đã dùng được giữ hay reset. Không để race condition khiến nhiều request đồng thời cùng tiêu quota âm hoặc vượt hạn mức.

### 4.3. Quota reservation và commit

Với thao tác tốn tài nguyên hoặc tính phí, có thể cần hai bước:

1. Reserve ngân sách trước khi bắt đầu công việc.
2. Commit theo mức sử dụng thực tế khi hoàn tất.
3. Release reservation khi request thất bại trước khi sử dụng tài nguyên.
4. Có reconciliation cho job timeout/crash để reservation không bị treo vô hạn.

Thiết kế idempotency cho retry. Một request được gửi lại do network timeout không nên tiêu quota hoặc tạo side effect hai lần nếu cùng idempotency key và cùng payload.

## 5. Response khi vượt giới hạn

Khi client vượt rate limit, HTTP thường dùng §429 Too Many Requests§. Có thể trả §Retry-After§ dưới dạng số giây hoặc HTTP-date khi biết thời điểm có thể thử lại.

Ví dụ:

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 10
RateLimit-Limit: 60
RateLimit-Remaining: 0
RateLimit-Reset: 10
Cache-Control: no-store
~~~

Các trường §RateLimit-Limit§, §RateLimit-Remaining§ và §RateLimit-Reset§ có thể được dùng theo RFC 9333 nếu triển khai theo đúng ngữ nghĩa của chuẩn. Cần thống nhất đơn vị và phạm vi bucket để client hiểu reset áp dụng cho policy nào.

### 5.1. Không tiết lộ nội bộ

Response nên cho biết client cần chờ bao lâu hoặc quota nào đã hết ở mức an toàn. Không trả cấu hình toàn hệ thống, số lượng request của tenant khác, Redis key, internal IP hoặc chi tiết thuật toán có thể hỗ trợ né giới hạn.

### 5.2. Phân biệt 429 và 503

- §429§: request bị từ chối do client/user/tenant vượt policy rate hoặc quota.
- §503§: service hiện không thể nhận thêm công việc do quá tải hoặc dependency unavailable, có thể kèm Retry-After nếu phù hợp.

Không dùng 429 để che mọi lỗi backend. Không trả 200 với body “rate limited” vì client, proxy và monitoring sẽ hiểu nhầm request thành công.

### 5.3. Cache và retry

Response 429 thường nên tránh bị shared cache lưu nhầm cho user khác. Dùng cache directive phù hợp, thường là §Cache-Control: no-store§ khi response chứa trạng thái giới hạn theo principal.

Client cần backoff có jitter và tôn trọng Retry-After. Server nên kiểm thử retry storm: nhiều client cùng retry đúng một thời điểm có thể tạo burst mới. Không khuyến khích retry ngay hoặc retry vô hạn.

## 6. Resource limits ngoài số lượng request

Rate limit không đủ để ngăn request ít nhưng quá đắt. Thiết kế resource budget theo từng vector:

| Tài nguyên | Giới hạn cần cân nhắc | Tín hiệu theo dõi |
|---|---|---|
| CPU | Query cost, parser complexity, execution budget | CPU time, utilization |
| Memory | Body size, decompression, result size, buffer | Heap/RSS, GC, OOM |
| Threads | Request concurrency, blocking calls | Active threads, queue wait |
| Database | Query timeout, connection pool, rows scanned | Pool saturation, slow query |
| Network | Upload/download bytes, outbound calls | Throughput, open connections |
| Storage | Per-file/per-tenant quota, temp disk | Used bytes, inode/temp space |
| Queue | Pending jobs, per-tenant backlog | Queue depth, age |
| Downstream | Call rate, concurrency, retry budget | Provider latency/errors/cost |
| Parser | Depth, item count, regex/format complexity | Parse time, failures |
| Streaming | Duration, idle timeout, max bytes | Active streams, bytes sent |

### 6.1. Giới hạn request body và decompression

Giới hạn cả body đã truyền và body sau giải nén. Một payload nén nhỏ có thể bung thành dữ liệu rất lớn. Đặt giới hạn cho:

- Content-Length nếu có và số bytes thực tế đọc được.
- Multipart total size và từng part.
- Số part, tên field và filename length.
- Decompressed size và compression ratio khi hỗ trợ nén.
- JSON nesting depth, array length và string length.
- Upload duration và tốc độ tối thiểu nếu cần chống slow upload.

Không chỉ tin Content-Length do client khai báo. Đọc stream có bộ đếm bytes và dừng khi vượt giới hạn.

### 6.2. Pagination và bulk operations

Bắt buộc giới hạn page size; không cho client gửi §limit=100000000§. Với bulk API:

- Giới hạn số phần tử mỗi batch.
- Validate từng phần tử.
- Giới hạn tổng cost và thời gian.
- Xử lý quyền trên từng object.
- Giới hạn số batch đồng thời.
- Dùng job bất đồng bộ cho công việc lớn và áp quota/expiry.
- Trả kết quả từng phần theo hợp đồng rõ ràng, không giữ request mở vô hạn.

### 6.3. Search và GraphQL complexity

Search có thể tạo query scan lớn hoặc tổ hợp filter tốn kém. Giới hạn filter count, sort fields, wildcard, date range, page size và execution timeout.

Với GraphQL, cần giới hạn query depth, complexity/cost, alias count, batch operations và số resolver fan-out. Giới hạn request rate đơn thuần không ngăn một query duy nhất kích hoạt hàng nghìn resolver.

### 6.4. Regex và parser

Tránh regex có thể gây catastrophic backtracking với input do client kiểm soát. Giới hạn độ dài input, chọn engine phù hợp, đặt timeout hoặc dùng thuật toán tuyến tính. Parser XML/JSON/document phải giới hạn depth, entity expansion, số node, kích thước và thời gian.

### 6.5. Outbound calls và retry amplification

Một request inbound có thể kích hoạt nhiều outbound calls. Giới hạn fan-out, timeout, concurrency và retry budget. Dùng circuit breaker/bulkhead để một dependency chậm không chiếm hết thread hoặc connection pool. Tránh retry lồng nhau ở nhiều service khiến một request tạo ra hàng chục lần gọi downstream.

## 7. Distributed rate limiting và các điểm dễ sai

Trong hệ thống nhiều instance, counter chỉ nằm trong memory của từng instance có thể cho phép tổng request vượt ngưỡng theo số replica. Cần xác định nơi thực thi policy:

- API gateway/edge cho giới hạn sớm và bảo vệ ingress.
- Application/service cho giới hạn theo principal, tenant, object hoặc cost nghiệp vụ.
- Shared store hoặc distributed limiter để đồng bộ counter giữa replicas.
- Database/transactional quota ledger cho quota cần tính đúng và có audit.
- Queue/admission controller cho giới hạn công việc bất đồng bộ.

### 7.1. Atomicity và race condition

Nhiều request đồng thời có thể cùng đọc số dư còn lại rồi cùng được chấp nhận. Bộ đếm hoặc token reservation cần thao tác atomic phù hợp. Kiểm thử song song tại ngưỡng để phát hiện overshoot.

Với quota tính phí, cần transaction/idempotency/reconciliation phù hợp; cache counter eventual consistency có thể không đủ nếu yêu cầu không vượt hạn mức dù chỉ một đơn vị.

### 7.2. Store unavailable: fail-open hay fail-closed?

Nếu Redis hoặc quota service không hoạt động, hệ thống cần chính sách rõ:

- Fail-open có thể duy trì availability nhưng làm mất giới hạn và mở nguy cơ chi phí/DoS.
- Fail-closed bảo vệ tài nguyên nhưng có thể từ chối cả người dùng hợp lệ.
- Hybrid có thể dùng local emergency limit thấp, circuit breaker và giới hạn endpoint nhạy cảm chặt hơn.

Không có lựa chọn đúng cho mọi API. Quyết định theo rủi ro, chi phí và mức độ quan trọng; kiểm thử cả tình huống store chậm, timeout, failover và dữ liệu counter bị mất.

### 7.3. Đảm bảo mọi đường vào đều được giới hạn

Kiểm tra direct service address, alternate hostname, API version cũ, internal ingress, gateway route và endpoint admin. Nếu chỉ giới hạn ở gateway nhưng upstream vẫn public, client có thể đi vòng. Nếu giới hạn chỉ ở một route, alias hoặc method khác có thể không bị bảo vệ.

## 8. Quy trình kiểm thử có kiểm soát

Kiểm thử rate limit và resource exhaustion phải có phạm vi rõ ràng. Dùng local hoặc staging được cấu hình riêng, dữ liệu giả, account/tenant test và ngưỡng có thể quan sát. Không tạo tải lên production hoặc dịch vụ bên thứ ba nếu chưa có kế hoạch kiểm thử tải được phê duyệt và cửa sổ thực hiện.

### 8.1. Chuẩn bị trước khi chạy

1. Ghi lại policy mong đợi: key, limit, window, burst, quota period, concurrency và response.
2. Xác định endpoint, version, tenant, client và credential test.
3. Đặt giới hạn cho chính công cụ test: request rate, duration, VU, số bytes và stop condition.
4. Chạy baseline ở tải thấp để đo latency và tài nguyên bình thường.
5. Bật dashboard/metrics cho API, gateway, database, queue, cache và downstream.
6. Xác định người có thể dừng test và cách rollback/reset quota fixture.
7. Kiểm tra test không gửi email/SMS thật, không tạo payment thật và không gọi provider tính phí.

### 8.2. Tăng tải theo nấc

Không bắt đầu bằng tải cực lớn. Tăng từng nấc có kiểm soát:

- Baseline: dưới ngưỡng để xác minh luồng bình thường.
- Boundary: đúng ngưỡng và thêm một request.
- Burst: gửi nhanh trong dung lượng burst đã thiết kế.
- Sustained: giữ tốc độ gần/vượt ngưỡng trong thời gian ngắn được định trước.
- Recovery: dừng request và kiểm tra hệ thống phục hồi, quota reset và Retry-After.

Mỗi bước cần có tiêu chí dừng: latency vượt ngưỡng an toàn, error rate tăng mạnh, CPU/memory/DB pool gần bão hòa, queue tăng không giảm hoặc dependency bắt đầu trả lỗi.

## 9. Các nhóm test rate limit

### 9.1. Boundary test

Với policy 10 request trong 60 giây, xác minh:

- Các request đầu trong giới hạn được chấp nhận.
- Request tiếp theo bị từ chối theo thuật toán và semantics đã công bố.
- Reset/refill xảy ra đúng thời điểm.
- Retry-After phù hợp với thời gian chờ.
- Request bị từ chối không tiêu thêm tài nguyên nghiệp vụ hoặc tạo side effect.

Với token bucket, cần kiểm tra burst capacity và refill rate; không áp quy tắc fixed-window vào thuật toán khác.

### 9.2. Burst và sustained load

Burst test xác minh hệ thống cho phép burst đúng dung lượng và từ chối phần vượt ngưỡng. Sustained test xác minh throughput dài hạn không vượt refill/average rate. Đo cả request được nhận, request bị từ chối, latency và tài nguyên.

### 9.3. Parallel/concurrency test

Gửi nhiều request đồng thời quanh ngưỡng để kiểm tra atomicity. Với concurrency limit, giữ một số request/job đang chạy rồi thử thêm request; hệ thống phải áp dụng queue/reject policy đã định nghĩa và giải phóng slot khi job hoàn tất hoặc timeout.

### 9.4. Key isolation và fairness

Dùng hai user, hai API key và hai tenant:

- User A vượt limit không làm user B bị block nếu policy tách biệt.
- Hai API key cùng tenant không nhân đôi tenant quota.
- Một tenant vượt quota không làm tenant khác mất capacity ngoài global protection dự kiến.
- Anonymous traffic không thể giả mạo IP trusted để né hoặc gây block.
- Token refresh hoặc đổi credential không reset quota nếu quota thuộc cùng principal/tenant.

### 9.5. Method, route và version bypass

Thử các biến thể đã được thiết kế trong phạm vi test:

- GET/POST/PATCH/DELETE trên cùng resource.
- Route alias hoặc trailing slash nếu router hỗ trợ.
- API version cũ và mới.
- Batch endpoint thay cho request đơn.
- GraphQL batching/alias nếu có.
- Alternate hostname/ingress được quản lý.

Mục tiêu là xác minh policy gắn đúng operation/cost, không dựa vào một chuỗi URL duy nhất dễ bị né.

### 9.6. Spoofing rate-limit identity

Gửi các header như §X-Forwarded-For§ hoặc custom client ID giả từ test client. Kiểm tra gateway chỉ tin forwarded metadata từ proxy đáng tin, và principal/tenant được lấy từ credential đã xác minh. Thay đổi header không được giúp một client vượt ngưỡng hoặc làm user khác bị block.

## 10. Các nhóm test quota và concurrency

| Nhóm test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Daily/monthly quota | Dùng tới ngưỡng rồi thêm một đơn vị | Vượt quota bị từ chối theo policy |
| Tenant aggregation | Nhiều user/key trong cùng tenant cùng sử dụng | Tổng được tính theo tenant nếu quota tenant |
| Reset boundary | Gọi ngay trước/sau thời điểm reset UTC | Kỳ quota được tính nhất quán |
| Tier change | Đổi gói khi đã dùng một phần quota | Áp dụng quy tắc nâng/hạ gói đã công bố |
| Concurrent reservation | Nhiều request cùng lấy đơn vị quota cuối | Không cấp vượt do race |
| Failed job | Job lỗi trước khi tiêu tài nguyên | Reservation được release đúng policy |
| Retry/idempotency | Gửi lại cùng request sau timeout | Không double charge hoặc tạo duplicate side effect |
| Concurrent jobs | Đã đạt concurrency cap, gửi thêm job | Reject hoặc queue theo policy |
| Queue cap | Queue đạt giới hạn | Không tăng vô hạn; trả trạng thái phù hợp |
| Revoked client | Client/API key bị thu hồi | Không tiếp tục tiêu quota bằng credential cũ |
| Shared IP | Nhiều user hợp lệ sau NAT | Không block nhầm nếu policy không chủ ý giới hạn chung |
| New account/key | Tạo identity mới để né limit | Các quota cấp tenant/global vẫn giữ hiệu lực |

## 11. Resource exhaustion test theo từng vector

Rate limit test cần kết hợp test tài nguyên. Dùng input nhỏ và tăng dần, theo dõi resource; không cố làm sập service.

### 11.1. Body size và decompression

- Gửi body ngay dưới, đúng bằng và vượt giới hạn.
- Kiểm tra Content-Length giả hoặc thiếu nhưng stream bytes vượt mức.
- Kiểm tra multipart nhiều part và một part quá lớn.
- Kiểm tra compressed body sau giải nén vượt giới hạn.
- Xác minh request bị dừng sớm, không giữ toàn bộ body trong memory và không tạo file tạm vô hạn.

### 11.2. Pagination, search và query cost

- Page size ngay dưới/trên max.
- Filter/sort combinations phức tạp.
- Date range quá rộng.
- Wildcard hoặc prefix search có chi phí cao.
- GraphQL depth/alias/batch vượt budget.
- Query timeout và cancellation có thực sự dừng database work không?

Kiểm tra cả số rows scanned, query duration, DB connections và cache hit rate. Một response timeout ở API nhưng query vẫn chạy trong database có thể tiếp tục làm cạn pool.

### 11.3. Upload, scan và storage

- File ngay dưới/trên size limit.
- Nhiều file đồng thời và nhiều part.
- Tenant chạm storage quota.
- Scanner chậm hoặc queue scan đầy.
- Upload bị ngắt giữa chừng.
- Temp file và incomplete multipart upload được cleanup.
- Một file bị retry không tạo nhiều object hoặc charge trùng.

### 11.4. Export và background job

- Giới hạn số dòng, số file và output bytes.
- Concurrency per-user/per-tenant/global.
- Job timeout và cancellation.
- Queue cap, worker saturation và retry budget.
- Requester bị revoke quyền trước khi job hoàn tất.
- Output expiry và cleanup.
- Không tạo nhiều job khi client retry cùng idempotency key.

### 11.5. Slow request và connection exhaustion

Kiểm tra upload chậm, client đọc response chậm, keep-alive và streaming kéo dài. Đặt read/write/idle timeout và giới hạn concurrent connections/streams. Đảm bảo một client không giữ thread hoặc connection vô thời hạn.

### 11.6. Downstream dependency

Dùng mock/stub trong staging để mô phỏng dependency chậm, lỗi hoặc trả retryable status. Xác minh timeout, circuit breaker, bulkhead, retry budget và queue không tạo amplification. Không dùng provider thật có tính phí làm đối tượng stress test.

## 12. Ví dụ k6 cho rate-limit test có giới hạn

Đoạn script dưới đây minh họa một bài test ngắn, cố định tốc độ và thời gian. Cấu hình ví dụ phát 20 iteration/giây trong 30 giây, tổng khoảng 600 request. Hãy chỉnh rate thấp hơn nếu staging nhỏ; chỉ chạy khi policy test được cấu hình rõ và endpoint là fixture an toàn.

~~~javascript
import http from 'k6/http';
import { Counter } from 'k6/metrics';

const limited = new Counter('rate_limited');
const accepted = new Counter('accepted');
const unexpected = new Counter('unexpected_status');

export const options = {
  scenarios: {
    controlled_rate_test: {
      executor: 'constant-arrival-rate',
      rate: 20,
      timeUnit: '1s',
      duration: '30s',
      preAllocatedVUs: 10,
      maxVUs: 20
    }
  },
  thresholds: {
    rate_limited: ['count>0'],
    unexpected_status: ['count==0']
  }
};

const baseUrl = __ENV.BASE_URL;
const token = __ENV.TEST_TOKEN;

if (!baseUrl || !token) {
  throw new Error('BASE_URL and TEST_TOKEN must be provided by the test environment');
}

export default function () {
  const response = http.get(baseUrl + '/api/test/rate-limited-resource', {
    headers: {
      Authorization: 'Bearer ' + token
    },
    tags: {
      test: 'controlled-rate-limit'
    }
  });

  if (response.status === 429) {
    limited.add(1);
  } else if (response.status >= 200 && response.status < 300) {
    accepted.add(1);
  } else {
    unexpected.add(1);
  }
}
~~~

Script cần được điều chỉnh theo policy thật. Nếu server cho phép 20 request/giây, việc không thấy 429 không phải lỗi; hãy đặt tốc độ test cao hơn ngưỡng một cách có kiểm soát. Không đặt token thật trong source hoặc log; CI nên inject secret qua secret environment. Không chạy lặp vô hạn hoặc bỏ giới hạn duration/VU.

Ví dụ cách chạy, với BASE_URL và TEST_TOKEN đã được cấp an toàn trong môi trường test:

~~~bash
k6 run rate-limit-test.js
~~~

Kiểm tra thêm response headers Retry-After/RateLimit, status phân bố theo thời gian, số request thực tế, dropped iterations và dashboard tài nguyên. Một bài test đạt ngưỡng 429 nhưng làm database pool cạn hoặc queue không hồi phục vẫn là thất bại.

## 13. Metrics và tiêu chí đánh giá

Thu thập tối thiểu:

| Nhóm | Metrics |
|---|---|
| Traffic | Requests/sec, accepted/rejected, route/client/tenant |
| Limiter | Remaining tokens, quota usage, reset time, limiter errors |
| Latency | p50/p95/p99, time-to-first-byte, queue wait |
| Application | CPU, heap/RSS, GC pause, active threads |
| Database | Active/idle pool, wait time, query duration, timeout |
| Queue | Depth, oldest age, enqueue/dequeue rate, retry/dead-letter |
| Storage | Bytes, temp usage, incomplete upload count |
| Network | Active connections, bandwidth, outbound call count |
| Downstream | Latency, error, retry, circuit state and cost |
| Fairness | Accepted/rejected rate theo tenant/client/tier |

### 13.1. Tiêu chí pass/fail

Một policy test nên có tiêu chí rõ:

- Request trong giới hạn được phục vụ theo SLO.
- Request vượt rate/quota bị từ chối với status và Retry-After đúng.
- Không có overshoot vượt dung sai đã định nghĩa.
- Một tenant không chiếm quota của tenant khác.
- Concurrency và queue không vượt cap.
- Memory, CPU, DB pool và connection không tăng không kiểm soát.
- Khi tải dừng, hệ thống hồi phục trong thời gian mục tiêu.
- Không có duplicate side effect hoặc double charge.
- Limiter store lỗi được xử lý theo fail-open/fail-closed policy.
- Metrics/log không chứa credential hoặc dữ liệu nhạy cảm.

Không chỉ dùng số 429 làm tiêu chí pass. Một limiter có thể trả 429 đúng nhưng vẫn thực thi request phía sau, hoặc từ chối nhầm tất cả client vì key sai.

## 14. Những lỗi thường gặp khi kiểm thử

| Quan sát | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Mỗi replica cho phép đủ quota | Counter local, không chia sẻ | Test qua nhiều instance |
| Thỉnh thoảng vượt limit khi đồng thời | Counter/reservation không atomic | Parallel boundary test |
| Đổi API key là có quota mới | Quota gắn sai identity | Test nhiều key cùng tenant |
| Header IP giả giúp né limit | Tin forwarded header từ client | Gửi spoofed header qua public edge |
| 429 nhưng DB vẫn chạy query | Limiter đặt quá muộn hoặc xử lý async đã bắt đầu | Trace request tới DB/worker |
| Rate limit đúng nhưng export làm đầy queue | Thiếu concurrency/queue cap | Job exhaustion test |
| Retry tạo nhiều giao dịch | Thiếu idempotency | Replay cùng idempotency key |
| Request gzip nhỏ làm tăng memory | Chỉ giới hạn compressed bytes | Test decompressed size |
| Timeout API nhưng DB query tiếp tục | Không cancel downstream work | Theo dõi query sau timeout |
| Tenant A bị ảnh hưởng bởi tenant B | Chỉ có global quota hoặc key collision | Tenant fairness test |
| Store limiter lỗi thì mọi request được phép | Fail-open không có emergency cap | Chaos test limiter dependency |
| Store limiter lỗi thì toàn API ngừng | Fail-closed quá rộng | Test policy theo endpoint/risk tier |

## 15. Kiểm thử sau thay đổi và trong vòng đời API

Rate limit và quota là một phần của API contract. Thay đổi endpoint, version, auth model, pricing, tier hoặc backend có thể làm policy cũ không còn đúng.

Mỗi lần release nên kiểm tra:

- Route mới có policy mặc định hay bị bỏ sót?
- Version cũ và alias có cùng giới hạn cần thiết?
- Thay đổi auth principal có làm thay key limiter?
- Thay đổi cost của query/export có cần điều chỉnh weight?
- Gateway và application có cùng định nghĩa client/tenant không?
- Quota migration có giữ usage hiện tại không?
- Policy mới có phá client retry/backoff hoặc SDK không?
- Response 429 và header reset có tương thích với client?
- Feature flag hoặc rollback có khôi phục đúng limiter state?
- Metrics/dashboard và alert có được cập nhật?

Không âm thầm thay limit hoặc reset quota trong kỳ đang chạy nếu hợp đồng với consumer yêu cầu thông báo. Có versioning hoặc policy ID để truy vết quyết định và giải thích vì sao một request bị giới hạn.

## 16. Checklist trước khi phát hành

- [ ] Mỗi endpoint được phân loại theo chi phí và mức độ nhạy cảm.
- [ ] Có rate limit theo principal/client/tenant/route và global guardrail phù hợp.
- [ ] Quota gắn với đúng chủ thể nghiệp vụ; nhiều key không nhân quota ngoài ý muốn.
- [ ] Burst, sustained rate, concurrency và queue có giới hạn riêng.
- [ ] Counter/reservation phân tán có atomicity phù hợp.
- [ ] Forwarded IP chỉ được tin từ proxy đã xác minh.
- [ ] Response 429, Retry-After và RateLimit metadata có semantics nhất quán.
- [ ] Request size, decompression, page size, batch count và query complexity có cap.
- [ ] CPU/time, DB pool, thread, stream, storage và downstream calls có budget.
- [ ] Upload, scan, export và background job có concurrency/queue/expiry limit.
- [ ] Retry có backoff budget và idempotency cho side effect.
- [ ] Limiter store unavailable có fail-open/closed hoặc emergency policy đã kiểm thử.
- [ ] Có boundary, burst, sustained, parallel, fairness, spoofing và bypass tests.
- [ ] Có metrics cho latency, rejection, CPU, memory, DB, queue và downstream.
- [ ] Có stop condition, recovery test và không tạo side effect/tính phí thật trong test.
- [ ] API contract, SDK và consumer được đánh giá khi limit/quota thay đổi.

Rate limit giới hạn tốc độ, quota giới hạn tổng mức sử dụng, còn resource budget giới hạn chi phí và công việc đang hoạt động. Một API cần phối hợp các lớp này theo principal, tenant, endpoint và cost; kiểm thử boundary, burst, concurrency, phân tán, fairness và từng vector tài nguyên. Kết quả tốt phải chứng minh request vượt ngưỡng bị chặn trước khi gây side effect, người dùng khác vẫn được phục vụ công bằng và service phục hồi sau tải, chứ không chỉ chứng minh đã xuất hiện status 429.
