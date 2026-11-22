# Blue-green deployment cho API và function

Blue-green deployment là chiến lược phát hành trong đó hệ thống duy trì hai môi trường hoặc hai phiên bản có thể chạy độc lập: **blue** đang phục vụ traffic hiện tại và **green** chứa phiên bản mới. Nhóm triển khai, kiểm thử green trước, sau đó chuyển traffic sang green bằng một điểm điều phối ổn định. Nếu phát hiện lỗi, traffic có thể được chuyển về blue khi phiên bản cũ và dữ liệu vẫn tương thích.

Với serverless, blue và green thường là hai revision, version hoặc deployment của function/service. Nhà cung cấp quản lý compute và autoscaling, nhưng nhóm vẫn phải thiết kế cách định tuyến, cấu hình, quyền IAM, database migration, state, queue consumer và tác vụ định kỳ. Một lần deploy code thành công không bảo đảm rollback an toàn nếu phiên bản mới đã thay đổi schema hoặc tạo tác dụng phụ không thể đảo ngược.

Bài học tập trung vào cách áp dụng blue-green cho Java HTTP API và function xử lý event/message, cách chuyển traffic có kiểm soát, duy trì tương thích dữ liệu và xác định điều kiện rollback.

## 1. Blue-green deployment là gì?

Blue-green giữ hai môi trường có cấu hình tương đương. Trong trạng thái ban đầu, blue nhận toàn bộ traffic. Green được triển khai từ artifact mới và kiểm tra bằng smoke test hoặc traffic thử nghiệm. Khi green đạt tiêu chí, router hoặc nền tảng chuyển traffic sang green.

Luồng khái niệm:

~~~mermaid
flowchart TD
    Build[Build immutable artifact]
    DeployB[Deploy green version]
    Test[Smoke test / readiness / security checks]
    Router[Traffic router or stable alias]
    Blue[Blue: current version]
    Green[Green: new version]
    Observe[Observe metrics and errors]
    Rollback[Route traffic back to blue]

    Build --> DeployB
    DeployB --> Test
    Test -->|Pass| Router
    Test -->|Fail| Rollback
    Router --> Blue
    Router --> Green
    Blue --> Observe
    Green --> Observe
    Observe -->|Healthy| Complete[Promote green]
    Observe -->|Regression| Rollback
    Rollback --> Blue
~~~

Tên blue và green chỉ là nhãn cho hai phiên bản. Không bắt buộc phải có hai cụm máy chủ vật lý. Trong serverless, hai bên có thể là:

- Hai Lambda published versions và một alias ổn định.
- Hai Cloud Run revisions của cùng service.
- Hai deployment/slot của nền tảng serverless hỗ trợ slot swap.
- Hai function hoặc service độc lập đứng sau API gateway/load balancer.

### Các giai đoạn chính

1. **Build:** tạo artifact bất biến, gắn commit SHA hoặc release ID.
2. **Deploy green:** triển khai phiên bản mới với cấu hình và quyền cần thiết.
3. **Verify:** kiểm tra startup, health, contract API, dependency và bảo mật.
4. **Switch:** chuyển một phần hoặc toàn bộ traffic sang green.
5. **Observe:** theo dõi latency, lỗi, throttling, business metric và dependency.
6. **Promote hoặc rollback:** giữ green làm phiên bản chính hoặc quay lại blue theo tiêu chí đã định.

Blue-green giúp giảm thời gian gián đoạn và tạo đường quay lại nhanh. Nó không tự động bảo đảm zero downtime, dữ liệu không mất hoặc tác dụng phụ được đảo ngược.

## 2. Blue-green khác rolling và canary thế nào?

| Chiến lược | Cách phát hành | Ưu điểm | Rủi ro/đánh đổi |
|---|---|---|---|
| Rolling | Thay instance cũ dần bằng instance mới | Không cần giữ hai môi trường hoàn chỉnh | Trong thời gian rollout có nhiều phiên bản cùng phục vụ; rollback có thể chậm |
| Blue-green | Duy trì blue và green, chuyển traffic giữa hai bên | Cutover và rollback nhanh qua router/alias | Tốn tài nguyên trong thời gian chạy song song; cần tương thích dữ liệu |
| Canary | Gửi tỷ lệ traffic nhỏ đến bản mới rồi tăng dần | Phát hiện lỗi trên một phần traffic thật | Phải đo đủ mẫu; routing và phân tích phức tạp hơn |

Canary là một cách chuyển traffic thường được kết hợp với blue-green. Ví dụ, blue nhận 95% và green nhận 5% trong giai đoạn quan sát; sau đó tăng green lên 25%, 50% và 100%.

Blue-green không nhất thiết phải chuyển 100% traffic trong một bước. Nếu nền tảng hỗ trợ weighted routing, có thể dùng tỷ lệ nhỏ để kiểm tra hành vi với traffic thực tế. Nếu chỉ có stable alias trỏ một version, có thể kiểm thử green bằng URL hoặc endpoint riêng trước rồi cutover toàn bộ.

## 3. Tổ chức phiên bản cho Java API và function

Một release nên có danh tính bất biến. Tránh deploy cùng một artifact tag có thể bị ghi đè, chẳng hạn latest. Dùng version hoặc digest cụ thể để biết chính xác code nào đang chạy.

Một release manifest có thể lưu:

~~~yaml
releaseId: order-api-2026.11.17-4
gitCommit: 8f31a9d
artifactDigest: sha256:...
runtime: java21
configRevision: order-api-config-18
databaseSchemaRange:
  minimum: 12
  maximum: 14
~~~

Manifest là metadata cho pipeline; không chứa secret. Các giá trị runtime, config và schema range giúp pipeline kiểm tra tương thích trước khi chuyển traffic.

### Phân biệt artifact, revision và alias

- **Artifact:** JAR, container image hoặc deployment package đã build.
- **Version/revision:** bản triển khai cụ thể của artifact và cấu hình liên quan.
- **Alias/stable URL:** điểm gọi ổn định mà client sử dụng.
- **Traffic policy:** quy tắc phân phối request giữa các version/revision.

Client nên gọi stable endpoint hoặc alias. Không nhúng version cụ thể vào từng client nếu mục tiêu là có thể đổi backend mà không cập nhật toàn bộ caller.

Với Java, cùng một artifact có thể được triển khai thành nhiều revision nhưng cấu hình khác nhau theo environment. Cần ghi lại digest và config revision của mỗi bên để khi rollback biết chính xác code và config nào được phục hồi.

## 4. Thiết kế blue-green cho HTTP API

HTTP API là trường hợp dễ áp dụng blue-green nhất vì request được định tuyến qua URL, gateway, alias hoặc load balancer.

Một kiến trúc:

~~~mermaid
flowchart LR
    Client[API clients]
    Gateway[API Gateway / Load Balancer]
    Blue[Blue API version]
    Green[Green API version]
    DB[(Shared compatible database)]
    Client --> Gateway
    Gateway -->|Current traffic| Blue
    Gateway -.->|Test or weighted traffic| Green
    Blue --> DB
    Green --> DB
~~~

Các nguyên tắc:

- Giữ một URL ổn định cho client.
- Deploy green với endpoint hoặc revision có thể kiểm thử riêng.
- Bảo đảm blue và green dùng schema database tương thích trong thời gian chuyển tiếp.
- Dùng contract API tương thích ngược khi có thể.
- Chuyển traffic ở gateway hoặc stable alias.
- Theo dõi theo version để so sánh lỗi và latency.
- Giữ blue đủ lâu để rollback trong cửa sổ quan sát.

### Kiểm thử green trước khi nhận traffic

Smoke test nên xác minh:

- Endpoint health trả kết quả mong đợi.
- Runtime Java khởi tạo thành công.
- Secret/config được đọc bằng đúng runtime identity.
- Kết nối database và dependency hoạt động.
- Authentication và authorization vẫn đúng.
- API contract không bị phá vỡ.
- Request lỗi được trả status code phù hợp.
- Log, metric và trace có release ID hoặc revision label.

Không chỉ kiểm tra một endpoint /health rồi kết luận release an toàn. Health check thường chỉ xác minh process sống; smoke test cần kiểm tra một số đường nghiệp vụ quan trọng với dữ liệu thử nghiệm an toàn.

## 5. Blue-green cho AWS Lambda bằng published versions và alias

AWS Lambda hỗ trợ published versions và aliases. Một version đã publish là snapshot code và một số cấu hình version-specific. Alias là tên ổn định có thể trỏ đến version và hỗ trợ weighted routing giữa version chính và một version phụ trong các trường hợp được hỗ trợ.

Ví dụ:

- Version 41 là blue đang phục vụ.
- Version 42 là green mới.
- Alias live là điểm tích hợp mà API Gateway hoặc caller sử dụng.

Không gọi trực tiếp version ARN trong client nếu muốn giữ khả năng chuyển đổi qua alias.

### Tạo và kiểm tra version mới

Pipeline có thể cập nhật function code, chờ trạng thái update hoàn tất, sau đó publish version:

~~~bash
aws lambda update-function-code   --function-name order-api   --zip-file fileb://target/order-api.zip

aws lambda wait function-updated   --function-name order-api

aws lambda publish-version   --function-name order-api   --description "release-2026.11.17-4"
~~~

Lệnh minh họa dùng ZIP package. Nếu dùng container image, cập nhật image URI theo digest và publish version tương ứng. Pipeline cần lấy version number trả về từ lệnh publish và lưu trong release metadata.

### Chuyển alias sang green

Sau khi kiểm thử version mới, cập nhật alias:

~~~bash
aws lambda update-alias   --function-name order-api   --name live   --function-version 42
~~~

Nếu muốn canary, có thể giữ version 41 làm primary và gửi một tỷ lệ nhỏ đến version 42:

~~~bash
aws lambda update-alias   --function-name order-api   --name live   --function-version 41   --routing-config '{"AdditionalVersionWeights":{"42":0.05}}'
~~~

Trong ví dụ, alias phân phối phần lớn invocation đến version 41 và 5% đến version 42. Khi metric đạt tiêu chí, chuyển primary sang 42 và bỏ weighted routing. Cần kiểm tra giới hạn và điều kiện routing của Lambda tại thời điểm triển khai.

### Rollback alias

Nếu green lỗi, chuyển alias về version 41:

~~~bash
aws lambda update-alias   --function-name order-api   --name live   --function-version 41
~~~

Rollback alias có thể nhanh, nhưng chỉ phục hồi code routing. Nó không tự hoàn tác database migration, message đã publish, email đã gửi hoặc các tác dụng phụ do version 42 thực hiện.

### API Gateway và alias

API Gateway integration cần trỏ đến alias ARN thay vì version ARN nếu muốn traffic switch qua alias. Kiểm tra resource policy, Lambda permission và deployment stage để bảo đảm gateway vẫn gọi đúng alias sau khi release.

Với event source mapping, không giả định weighted alias routing hoạt động giống HTTP invocation. Mỗi mapping có thể có checkpoint riêng và việc bật song song hai consumer có thể làm cùng một record được xử lý hai lần. Phần event-driven bên dưới trình bày cách xử lý riêng.

## 6. Blue-green cho Cloud Run và Cloud Run functions

Cloud Run triển khai mỗi lần thay đổi thành một revision. Có thể giữ nhiều revision và phân phối traffic giữa chúng. Cloud Run functions thế hệ 2 chạy trên nền tảng Cloud Run; khi dùng traffic management, cần xác minh tài nguyên service và luồng triển khai đang được quản lý qua API nào.

Ví dụ, sau khi deploy revision mới, kiểm tra danh sách revision và chuyển traffic:

~~~bash
gcloud run services update-traffic order-api   --region=asia-southeast1   --to-revisions=order-api-00041-abc=90,order-api-00042-def=10
~~~

Sau khi quan sát green và quyết định promote:

~~~bash
gcloud run services update-traffic order-api   --region=asia-southeast1   --to-revisions=order-api-00042-def=100
~~~

Tên revision chỉ là ví dụ. Lấy đúng tên từ kết quả deploy hoặc danh sách revision. Có thể dùng tag cho revision để kiểm thử qua URL riêng trước khi chuyển traffic chính thức.

### Cấu hình và service identity

Mỗi revision có thể có environment variables, secret reference, service account, concurrency và resource settings. So sánh các cấu hình này trước cutover:

- Runtime service account có đúng quyền không?
- Secret version có sẵn và còn hiệu lực không?
- VPC egress, ingress và network route có giống yêu cầu không?
- CPU, memory, timeout và concurrency có phù hợp không?
- Min/max instances và startup probe có được cấu hình đúng không?

Một revision mới chạy được code nhưng dùng nhầm service account hoặc secret version vẫn là release lỗi.

## 7. Blue-green cho Azure Functions và nền tảng có deployment slots

Một số hosting plan của Azure App Service/Azure Functions hỗ trợ deployment slots. Slot staging có thể được triển khai và kiểm thử trước khi swap với production slot. Khả năng hỗ trợ slot phụ thuộc hosting plan và loại ứng dụng; không giả định mọi plan đều có tính năng này.

Với nền tảng có slot swap:

1. Deploy artifact mới vào staging slot.
2. Đặt slot-specific settings và secret references đúng.
3. Kiểm thử URL staging.
4. Warm-up instance và xác minh dependency.
5. Swap staging với production.
6. Theo dõi metric production.
7. Swap ngược nếu cần rollback.

Cần kiểm tra setting nào được đánh dấu slot-sticky và setting nào đi cùng deployment. Nếu connection string hoặc secret bị hoán đổi sai, code có thể chạy với môi trường dữ liệu không đúng.

Các nền tảng khác có thể cung cấp traffic split, deployment slot hoặc revision routing với tên gọi khác. Hãy dùng cơ chế stable endpoint tương đương và xác minh semantics cụ thể của provider.

## 8. Blue-green cho event-driven function

Function xử lý message hoặc event khác HTTP API. Không có một router đơn giản chia request theo tỷ lệ mà không ảnh hưởng checkpoint, retry và thứ tự.

Ví dụ, hai Lambda event source mappings cùng đọc một stream hoặc queue có thể cùng nhận một record. Hai consumer độc lập có thể tạo hai checkpoint và chạy cùng tác dụng phụ. Vì vậy, bật green consumer song song không tương đương canary HTTP.

### Các cách triển khai an toàn hơn

**Cách 1: Chuyển consumer tại một điểm điều phối**

- Deploy green nhưng chưa bật trigger hoặc chưa cho phép nhận message.
- Kiểm tra function bằng test event hoặc dữ liệu replay trong môi trường cô lập.
- Dừng hoặc disable blue consumer theo quy trình.
- Bật green consumer.
- Theo dõi lag, lỗi, retry và DLQ.
- Nếu rollback, chuyển quyền xử lý về blue sau khi kiểm soát message đang in-flight.

Cách này tạo cutover rõ ràng nhưng cần tính đến message đang được xử lý và thời gian visibility/lease.

**Cách 2: Shadow consumer không có tác dụng phụ**

Green đọc bản sao hoặc replay event nhưng chỉ validate và tính kết quả, không gửi email, trừ tiền, ghi dữ liệu nghiệp vụ hoặc gọi API có side effect. So sánh output với blue. Khi green đạt yêu cầu, mới chuyển consumer thực.

**Cách 3: Router hoặc dispatcher có kiểm soát**

Một dispatcher duy nhất nhận message và quyết định gửi đến blue hoặc green theo tenant, partition key hoặc release cohort. Dispatcher cần giữ thứ tự nếu nghiệp vụ yêu cầu, và phải có idempotency ở các bước downstream.

Không nên để cả hai consumer cùng xử lý message thật chỉ vì muốn thử 10% traffic. Nếu cần split, phải xác định rõ semantics của partitioning, checkpoint, retry và side effect.

## 9. Idempotency và duplicate khi chuyển phiên bản

Trong serverless, message/event thường có delivery semantics at-least-once. Retry, timeout hoặc cutover có thể làm cùng event được giao lại. Blue và green có thể cùng nhìn thấy event nếu pipeline được cấu hình sai.

Dùng idempotency key ổn định:

- event ID do producer tạo.
- message ID hoặc stream sequence key kết hợp nguồn.
- business operation ID như paymentId hoặc orderVersion.

Ví dụ bảng deduplication:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL,
    release_id VARCHAR(128)
);
~~~

Khi xử lý event, ghi idempotency marker và cập nhật nghiệp vụ trong cùng transaction nếu cùng database. Nếu event đã được xử lý, consumer không thực hiện tác dụng phụ lần nữa.

Không dùng release ID làm idempotency key vì blue và green sẽ có key khác nhau cho cùng một event. Release ID chỉ hữu ích cho trace/audit.

### Tác dụng phụ bên ngoài database

Nếu function gửi email, thanh toán hoặc gọi API đối tác, transaction database không thể bao trùm toàn bộ side effect. Dùng outbox pattern, idempotency key của provider hoặc workflow state machine để quản lý trạng thái. Khi rollback code, không thể giả định email hoặc khoản thanh toán đã thực hiện sẽ tự biến mất.

## 10. Database migration phải tương thích hai phiên bản

Đây là điều kiện quan trọng nhất để blue-green rollback an toàn. Trong giai đoạn blue và green cùng hoạt động, cả hai có thể truy cập cùng database. Nếu green thay schema theo cách blue không hiểu, rollback code về blue sẽ khiến ứng dụng cũ lỗi.

Dùng chiến lược **expand-contract**:

1. **Expand:** thêm bảng/cột/index mới mà code cũ vẫn chạy được.
2. **Deploy compatible code:** code mới có thể đọc schema cũ và mới.
3. **Backfill:** chuyển dữ liệu theo batch có thể resume.
4. **Switch:** chuyển traffic sang green và xác minh.
5. **Contract:** chỉ xóa cột hoặc cấu trúc cũ sau khi blue không còn cần và rollback window kết thúc.

Ví dụ:

- Release A đọc cột full_name.
- Migration expand thêm first_name và last_name.
- Release B ghi cả full_name và hai cột mới, hoặc có cơ chế dual-read/dual-write có kiểm soát.
- Backfill dữ liệu cũ.
- Chuyển traffic sang B.
- Sau thời gian an toàn, release sau mới ngừng dùng full_name và xóa cột.

Không thực hiện destructive migration ngay trước khi chuyển traffic. Rollback ứng dụng không thể khôi phục schema hoặc dữ liệu đã xóa nếu không có backup/restore plan.

### Tương thích API và event schema

Tương tự database, event schema cần tương thích ngược trong thời gian consumer cũ và mới cùng tồn tại. Thêm field tùy chọn thường dễ hơn đổi nghĩa hoặc xóa field bắt buộc. Dùng schema version và quy trình rollout producer/consumer theo thứ tự an toàn.

## 11. State, session và cache trong blue-green

Không lưu state quan trọng chỉ trong memory của blue hoặc green. Hai phiên bản có thể có instance khác nhau và không chia sẻ heap.

Các vấn đề cần kiểm tra:

- Session được giữ trong memory có thể mất khi traffic chuyển sang green.
- Cache của blue và green có thể khác version.
- Static singleton có thể giữ cấu hình cũ.
- Token hoặc credential có thể được cache theo revision.
- Scheduled task có thể chạy đồng thời ở hai bên.
- WebSocket hoặc long-lived connection có thể tiếp tục gắn với phiên bản cũ.

Giải pháp:

- Lưu session ở shared store hoặc dùng token stateless có thời hạn phù hợp.
- Cache phải có version, TTL và invalidation.
- Tạo cache key tương thích giữa hai version hoặc dùng namespace có kế hoạch chuyển đổi.
- Đưa workflow state vào database/queue/state store.
- Dùng leader lease hoặc scheduler lock để chỉ một phiên bản thực hiện job độc quyền.
- Xử lý request đang chạy và connection dài theo drain policy.

Nếu cache format thay đổi, dùng versioned key hoặc dual-read trong giai đoạn chuyển tiếp. Không xóa cache toàn bộ một cách mù quáng nếu điều đó có thể gây cache stampede vào database.

## 12. Scheduled function, cron và job độc quyền

Một scheduled function có thể được triển khai ở cả blue và green. Nếu hai scheduler cùng hoạt động, một công việc có thể chạy hai lần.

Trước cutover:

- Chỉ bật schedule ở một bên.
- Hoặc dùng distributed lock/lease với owner và expiration.
- Gắn idempotency key cho mỗi scheduled run, ví dụ job name + scheduled timestamp.
- Đảm bảo job có thể resume hoặc chạy lại an toàn.
- Khi rollback, kiểm tra lease và invocation đang chạy trước khi bật scheduler cũ.

Không dùng static boolean trong Java để khóa job trên toàn hệ thống. Biến static chỉ có phạm vi một process và không phối hợp được giữa nhiều instance.

Với cron do cloud provider quản lý, kiểm tra trigger đang trỏ đến revision/alias nào. Chuyển traffic HTTP không tự động chuyển scheduler hoặc event source mapping.

## 13. Secrets, environment và IAM trong quá trình chuyển đổi

Blue và green có thể cùng chạy trong thời gian rollout. Cả hai cần quyền và cấu hình phù hợp trong cửa sổ này.

Checklist:

- Secret mới được tạo và cấp quyền trước khi deploy green.
- Runtime identity của green chỉ có quyền cần thiết.
- Credential rotation có thời gian overlap nếu blue vẫn cần secret cũ.
- Config schema tương thích với cả hai revision.
- Network egress, VPC connector và firewall rules không bị thay đổi ngoài dự kiến.
- IAM permission không bị thu hồi quá sớm.
- Khi promote green, xác minh quyền cũ có thể được thu hẹp sau khi blue ngừng chạy.

Không xóa secret hoặc thu hồi IAM của blue ngay sau khi chuyển traffic nếu còn invocation in-flight, rollback window hoặc tác vụ đang chạy. Nhưng cũng không để quyền cũ tồn tại vô thời hạn; đặt thời điểm cleanup rõ ràng.

## 14. Readiness, warm-up và cold start

Green cần được kiểm tra trước khi nhận traffic thật. Readiness không chỉ là process đang chạy.

Một readiness check tốt có thể xác minh:

- Runtime đã khởi tạo.
- Cấu hình bắt buộc hợp lệ.
- Dependency quan trọng có thể truy cập trong timeout.
- Database schema tương thích.
- Secret đã sẵn sàng.
- Function có thể xử lý một request thử nghiệm.

Không nên làm health endpoint quá nặng hoặc phụ thuộc vào mọi dịch vụ tùy chọn. Phân biệt liveness (process còn sống) và readiness (đủ điều kiện nhận traffic).

Với Java, cold start có thể tăng do JVM, class loading, dependency injection, framework và connection pool. Warm-up cần được kiểm soát để không tạo request nghiệp vụ thật hoặc làm tăng tải dependency. Nếu nền tảng có minimum instances, provisioned concurrency hoặc snapshot/restore, cân nhắc theo latency requirement và chi phí.

Warm-up không thay thế kiểm thử cold start. Đo cả request đầu tiên trên instance mới và steady-state latency.

## 15. Quan sát và tiêu chí chuyển traffic

Đặt tiêu chí trước khi bắt đầu rollout. Không quyết định chỉ dựa trên cảm giác hoặc một lần gọi thành công.

Các metric nên so sánh theo release/revision:

- Request count và tỷ lệ 4xx/5xx.
- Latency p50, p95 và p99.
- Cold start/startup latency.
- CPU, memory và concurrency.
- Timeout, throttling và retry.
- Database connection, query latency và error rate.
- Queue age, event lag và DLQ count.
- Business success rate, ví dụ tỷ lệ tạo đơn hàng thành công.
- Chi phí trên mỗi request hoặc mỗi job.

Ví dụ policy minh họa:

| Giai đoạn | Traffic green | Điều kiện |
|---|---:|---|
| Smoke test | 0% production | Test endpoint riêng, auth, dependency và contract |
| Canary 1 | 5% | Không tăng lỗi nghiêm trọng; theo dõi đủ request |
| Canary 2 | 25% | Latency và business metric nằm trong ngưỡng |
| Canary 3 | 50% | Không có regression theo tenant/region |
| Promote | 100% | Đủ cửa sổ quan sát và rollback plan còn khả dụng |

Các tỷ lệ và ngưỡng phải dựa trên traffic, SLA và baseline của hệ thống. Với traffic thấp, 5% có thể chỉ là vài request và không đủ mẫu để kết luận.

### Correlation và release metadata

Log và trace nên chứa release ID hoặc revision. Khi một request lỗi, cần biết nó được xử lý bởi blue hay green. Không dùng release ID làm metric label nếu tạo cardinality quá cao; có thể dùng dimension giới hạn hoặc log/tracing.

## 16. Rollback plan

Rollback cần được chuẩn bị trước khi deploy. Một kế hoạch tối thiểu xác định:

- Phiên bản blue còn hoạt động và có thể nhận traffic không?
- Alias/router có thể chuyển lại trong bao lâu?
- Database schema có còn tương thích với blue không?
- Config và secret của blue còn hiệu lực không?
- Queue consumer nào đang sở hữu message?
- Có tác dụng phụ nào green đã thực hiện không thể đảo ngược?
- Ai có quyền rollback và quy trình kích hoạt?
- Metric nào tự động hoặc thủ công kích hoạt rollback?

### Khi nào rollback?

Ví dụ các trigger:

- Tỷ lệ 5xx vượt ngưỡng trong cửa sổ liên tục.
- p95/p99 tăng mạnh so với baseline.
- Function timeout hoặc throttling tăng.
- Database connection pool cạn hoặc query error tăng.
- Business success rate giảm.
- Security check hoặc authorization regression.
- Queue age/DLQ tăng vượt ngưỡng.

Không rollback chỉ vì một spike ngắn do mẫu nhỏ nếu chưa phân tích, nhưng cũng không giữ green chỉ để tránh thất bại release. Với lỗi bảo mật hoặc rò dữ liệu, dừng traffic ngay và xử lý incident theo quy trình.

### Rollback không phải data rollback

Chuyển alias về blue chỉ đổi code được gọi. Nếu green đã ghi dữ liệu theo semantics mới, cần migration tương thích hoặc remediation riêng. Tránh tự động chạy migration ngược có thể làm mất dữ liệu hợp lệ.

## 17. Pipeline CI/CD tham khảo

Một pipeline blue-green cho Java API có thể gồm:

~~~mermaid
flowchart TD
    Commit[Commit / Pull request]
    Build[Compile and package]
    Test[Unit, integration, contract tests]
    Scan[Dependency and security scan]
    Publish[Publish immutable artifact]
    Deploy[Deploy green revision]
    Verify[Smoke and readiness checks]
    Canary[Shift small traffic]
    Monitor[Compare release metrics]
    Promote[Promote green to 100%]
    Rollback[Route traffic back to blue]

    Commit --> Build --> Test --> Scan --> Publish
    Publish --> Deploy --> Verify
    Verify -->|Fail| Rollback
    Verify -->|Pass| Canary --> Monitor
    Monitor -->|Healthy| Promote
    Monitor -->|Regression| Rollback
~~~

Pipeline nên tự động hóa phần có thể lặp lại, nhưng production promotion cần dựa trên tiêu chí được định nghĩa. Với hệ thống nhạy cảm, có thể cần approval trước bước chuyển traffic 100%.

### Các artifact cần lưu

- JAR/container image digest.
- Git commit và build provenance.
- Release manifest.
- Test và scan report.
- Version/revision ID của blue và green.
- Database migration version.
- Config revision và secret reference version.
- Traffic change record.
- Smoke test result và metric snapshot.
- Rollback action/audit log.

Không lưu plaintext secret trong artifact hoặc pipeline log.

## 18. Kiểm thử blue-green

Test cần bao phủ cả routing và hành vi sau cutover:

| Tình huống | Kết quả mong đợi |
|---|---|
| Deploy green thành công | Revision/version mới sẵn sàng |
| Green thiếu secret hoặc IAM | Smoke test thất bại, không chuyển traffic |
| Green không tương thích schema | Pipeline chặn promote |
| 5% traffic đến green | Metric phân biệt được blue và green |
| Green tăng 5xx | Router có thể quay lại blue |
| Rollback sau database expand | Blue vẫn đọc/ghi schema tương thích |
| Event source mapping bị bật trùng | Test phát hiện duplicate consumer/side effect |
| Message được retry khi cutover | Idempotency ngăn xử lý lặp |
| Scheduled job chạy ở hai revision | Lock/idempotency ngăn chạy hai lần |
| Cache format thay đổi | Blue và green đọc được dữ liệu trong giai đoạn overlap |
| Request dài đang chạy | Drain/timeout policy không làm mất kết quả |
| IAM/secret rotation | Cả hai phiên bản hoạt động trong overlap window |
| Rollback code | Không tự động đảo dữ liệu hoặc side effect ngoài ý muốn |

Kiểm thử rollback trong staging hoặc môi trường tương đương production. Một release pipeline chưa từng thử rollback chỉ chứng minh đường deploy hoạt động, chưa chứng minh hệ thống có thể phục hồi.

## 19. Những lỗi triển khai thường gặp

- **Deploy green rồi chuyển traffic ngay:** bỏ qua smoke test và quan sát; kiểm tra green trước.
- **Không giữ blue hoạt động:** mất đường rollback nhanh; duy trì blue trong rollback window.
- **Dùng artifact mutable:** không biết chính xác version nào đang chạy; dùng digest/version bất biến.
- **Chỉ rollback code:** schema hoặc side effect đã thay đổi có thể khiến blue lỗi; dùng expand-contract.
- **Bật hai stream consumer cùng lúc:** có thể xử lý trùng event; quản lý một consumer owner hoặc thiết kế shadow không side effect.
- **Chia traffic event như HTTP:** bỏ qua checkpoint và ordering; dùng cutover/dispatcher phù hợp.
- **Không có idempotency:** retry và duplicate gây tác dụng phụ lặp.
- **Hai scheduler cùng chạy:** job bị thực hiện hai lần; dùng lease hoặc một schedule owner.
- **Xóa secret/IAM cũ quá sớm:** invocation đang chạy hoặc rollback bị lỗi; có overlap và cleanup window.
- **Không phân biệt metric theo revision:** khó biết phiên bản nào gây lỗi; gắn release metadata.
- **Canary quá nhỏ hoặc quá ngắn:** không đủ dữ liệu để đánh giá; chọn mẫu và thời gian theo traffic.
- **Tin health check đơn giản:** process sống không có nghĩa nghiệp vụ hoạt động; dùng smoke/contract tests.
- **Giữ cache/session trong memory:** cutover làm mất hoặc lệch state; dùng shared store và versioned cache.
- **Không kiểm thử rollback:** quy trình phục hồi có thể thất bại đúng lúc incident.

## 20. Quy trình blue-green cho Java serverless

Có thể dùng trình tự sau cho một release:

1. Build artifact bất biến và gắn commit/release ID.
2. Chạy unit, integration, contract, security và dependency tests.
3. Kiểm tra database migration theo chiến lược expand-contract.
4. Tạo config revision và secret reference cần thiết cho green.
5. Deploy green mà chưa nhận production traffic.
6. Xác minh runtime, IAM, network, database và dependency.
7. Chạy smoke test và synthetic transaction an toàn.
8. Chuyển một phần traffic nếu nền tảng hỗ trợ; nếu không, chuẩn bị cutover toàn bộ.
9. So sánh latency, error rate, business metric và dependency theo revision.
10. Promote green khi đạt tiêu chí đã định.
11. Giữ blue và rollback window trong thời gian quy định.
12. Sau khi hết rollback window, dọn version cũ, secret và quyền không còn cần.
13. Chỉ thực hiện contract migration khi không còn code cũ phụ thuộc schema.
14. Ghi release result và rollback evidence vào audit trail.

Với event-driven function, bổ sung bước xác định consumer owner, checkpoint, retry, DLQ, idempotency và cách xử lý message in-flight trước khi chuyển trigger.

## 21. Ghi nhớ

Blue-green deployment giữ phiên bản đang phục vụ và phiên bản mới trong thời gian chuyển đổi, cho phép kiểm thử green trước khi chuyển traffic và quay lại blue nhanh khi có regression. Với HTTP API, stable URL, alias hoặc revision traffic split giúp điều phối request. Với event-driven function, cần xử lý riêng checkpoint, retry, ordering và duplicate; bật hai consumer cùng lúc có thể tạo tác dụng phụ lặp.

Rollback chỉ an toàn khi database schema, event contract, config, secret và state tương thích với cả hai phiên bản. Dùng expand-contract migration, idempotency, shared state store và scheduler lock cho những thành phần cần phối hợp.

Hãy xác định trước tiêu chí smoke test, canary, promote và rollback; quan sát metric theo release; giữ artifact bất biến và thử rollback trước production. Serverless giảm công việc quản lý compute, nhưng quy trình phát hành vẫn cần kiểm soát traffic, dữ liệu và tác dụng phụ để bảo đảm hệ thống phục hồi được khi phiên bản mới gặp lỗi.

