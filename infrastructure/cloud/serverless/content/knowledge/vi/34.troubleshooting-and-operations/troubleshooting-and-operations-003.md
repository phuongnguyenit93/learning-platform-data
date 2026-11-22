# Điều tra function không được kích hoạt hoặc thiếu quyền truy cập

Khi một serverless function không chạy sau HTTP request hoặc event, hoặc log xuất hiện lỗi AccessDenied, đừng vội sửa code handler. Lỗi có thể xảy ra trước khi function được gọi, ở lớp xác thực/ủy quyền của gateway, trong cấu hình trigger, ở quyền đọc event source, ở execution role của function, hoặc ở dịch vụ đích mà Java code đang truy cập.

Cách điều tra hiệu quả là lần theo toàn bộ đường đi của request/event và xác định **ranh giới cuối cùng đã hoạt động thành công**. Với HTTP, cần biết gateway đã nhận request chưa, authorizer đã cho phép chưa, integration có invoke function không và handler có bắt đầu chạy không. Với queue/event, cần biết event đã được publish, có nằm trong subscription/queue, có được event source mapping đọc, có vượt filter, có được invoke và có được acknowledge đúng cách không.

Bài học này xây dựng quy trình chẩn đoán cho Java serverless function, áp dụng cho HTTP trigger, queue consumer và event-driven function trên AWS Lambda, API Gateway, EventBridge, SQS, Google Cloud Run/Cloud Functions và Pub/Sub. Các ví dụ CLI chỉ đọc trạng thái hoặc mô phỏng quyền; hãy chạy trong đúng account/project, region và environment đang gặp lỗi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt function không được invoke, invoke bị từ chối và handler đã chạy nhưng thất bại.
- Lần theo request path từ producer/gateway đến function và downstream service.
- Kiểm tra HTTP route, stage, authorizer, integration và function invoke permission.
- Kiểm tra queue subscription, event source mapping, filter, batch, retry và DLQ.
- Phân biệt quyền invoke function, quyền đọc event source và quyền của execution role.
- Phân tích IAM policy, resource policy, service account, KMS và cross-account access.
- Nhận biết lỗi network thường bị nhầm với lỗi permission.
- Dùng request ID, correlation ID, metrics, logs và traces để khoanh vùng.
- Đọc lỗi Java SDK, Spring Security và credential chain trong runtime serverless.
- Khắc phục theo nguyên tắc least privilege và kiểm chứng bằng một request/event thật.
- Viết runbook, test permission và theo dõi lỗi sau khi triển khai.

## 1. Phân loại triệu chứng trước khi sửa

Cùng một biểu hiện “function không chạy” có thể chỉ đến những lỗi rất khác nhau. Hãy phân loại bằng evidence trước khi thay policy hoặc redeploy.

| Nhóm | Triệu chứng | Ranh giới có thể đang lỗi |
|---|---|---|
| Producer không phát event | Không thấy request/message/event ở nguồn | Client, publisher, network, publish permission |
| Trigger không chuyển tiếp | Event tồn tại ở queue/bus nhưng function không có invocation | Subscription, rule, mapping, filter, disabled trigger |
| Invoke bị từ chối | Gateway/event source báo 401/403 hoặc access denied | Authorizer, invoke permission, resource policy |
| Function được invoke nhưng handler lỗi | Invocation metric tăng, log có exception | Java code, deserialization, timeout, dependency |
| Function chạy nhưng không đọc được dữ liệu | Handler log có 403/AccessDenied | Execution role, resource policy, KMS, secret permission |
| Function không kết nối được dependency | Timeout, DNS error, connection refused | VPC, firewall, NAT, endpoint, DNS, routing |
| Function bị throttled | Throttles tăng, queue age tăng, request 429/5xx | Concurrency, quota, reserved capacity, downstream saturation |
| Function xử lý nhưng message quay lại | Duplicate invocation, visibility timeout, retry | Ack/delete timing, partial batch failure, idempotency |

Một quy tắc hữu ích:

- **Không có invocation**: kiểm tra producer, trigger, route, filter và quyền gọi function.
- **Có invocation nhưng handler không hoàn tất**: kiểm tra runtime, code, timeout, concurrency và dependency.
- **Handler chạy nhưng bị từ chối khi gọi dịch vụ khác**: kiểm tra identity mà function đang dùng và quyền trên resource đích.
- **Handler không kết nối được resource**: kiểm tra network path trước khi kết luận IAM.

### Đường đi tổng quát

~~~mermaid
flowchart LR
    P["HTTP client / Event producer"] --> S["Gateway / Queue / Event bus"]
    S --> A["Authentication and invoke authorization"]
    A --> T["Trigger routing / Event source mapping"]
    T --> F["Function invocation"]
    F --> R["Java handler and application logic"]
    R --> D["Database / Secret / Storage / API"]
    D --> O["Response / Ack / Result"]
~~~

Mỗi mũi tên là một ranh giới có thể thất bại. Điều tra từ trái sang phải và ghi lại evidence ở từng bước.

## 2. Thu thập evidence và giữ nguyên hiện trường

Trước khi đổi cấu hình, ghi lại thông tin đủ để tái hiện:

- Environment: development, staging hay production.
- Cloud account/project, region, function name và version/alias/revision.
- Trigger type: HTTP, queue, event bus, object storage hay scheduler.
- Thời điểm xảy ra lỗi kèm timezone.
- Request ID, trace ID, event ID, message ID hoặc correlation ID.
- HTTP method/path/status hoặc event source/partition/sequence.
- Tên principal gọi function và service account/execution role của function.
- Error code đầy đủ, không chỉ câu “permission denied”.
- Lần cuối trigger hoạt động và thay đổi gần nhất về deployment, IAM, secret, VPC hoặc resource policy.

Dùng UTC khi so sánh timestamp giữa gateway, broker, function và downstream. Đồng hồ giữa các hệ thống có thể lệch; ưu tiên request ID, event ID và trace context hơn việc so sánh timestamp đơn lẻ.

Không gửi token, cookie, private key, database password hoặc payload có PII vào ticket/log. Khi cần chia sẻ log, mask identifier và giữ lại error code, resource ARN/name, region và request ID.

### Xác định invocation có thực sự xảy ra không

Tìm đồng thời ba loại evidence:

1. **Trigger/gateway metrics:** request received, event matched, messages received, delivery attempts.
2. **Function metrics:** invocation count, error count, duration, throttle count, concurrent executions.
3. **Function logs/traces:** platform request ID, handler start, exception và downstream call.

Không có log không chứng minh function chưa chạy. Log có thể bị thiếu vì log group chưa tồn tại, execution role không ghi được log, sai region/account, log retention hoặc query sai time range. Metrics invocation của platform thường là bằng chứng độc lập hữu ích hơn log application.

## 3. Điều tra HTTP trigger: request có đến đúng function không?

Với HTTP API, lần theo chuỗi:

1. DNS/TLS và client gửi đúng host.
2. Gateway/load balancer nhận request.
3. Route/method/stage được deploy.
4. Authorizer hoặc IAM authentication chấp nhận caller.
5. Integration trỏ đúng function/alias và đúng region.
6. Gateway có quyền invoke function.
7. Function nhận event và runtime bắt đầu handler.
8. Handler xác thực/authorize nghiệp vụ và trả response.

### Kiểm tra route, stage và deployment

Các lỗi cấu hình thường gặp:

- Client gọi sai hostname, stage hoặc base path.
- Route chỉ cấu hình GET nhưng client gửi POST.
- Route được tạo nhưng stage chưa deploy.
- Gateway integration trỏ vào function khác, alias cũ hoặc region khác.
- Path parameter/query mapping làm thay đổi event payload.
- Request body không đúng payload format mà adapter mong đợi.
- Gateway timeout trước khi function hoàn tất.
- CORS preflight bị gateway xử lý riêng, nên không nhất thiết tạo invocation của business handler.

So sánh route đang hoạt động với API contract và deployment revision. Đừng chỉ kiểm tra cấu hình trong source/IaC; cần xem trạng thái thực tế đã deploy.

### Phân biệt 401 và 403

- **401 Unauthorized** thường có nghĩa token thiếu, sai chữ ký, hết hạn, issuer/audience không đúng hoặc chưa xác thực được principal.
- **403 Forbidden** thường có nghĩa principal đã được nhận diện nhưng policy không cho phép hành động; một số gateway cũng dùng 403 cho API key, resource policy hoặc WAF rule.
- **404** có thể được dùng để ẩn route/resource hoặc khi route không tồn tại.
- **429** thường báo rate/concurrency/quota throttling.
- **502/503/504** có thể là lỗi integration, function response không hợp lệ, upstream unavailable hoặc timeout; cần đọc gateway execution log và function metrics để phân biệt.

Status code không tự xác định chính xác lớp lỗi. Hãy xem error type, gateway request ID và invocation metric trong cùng khoảng thời gian.

### Authorizer và claim mapping

Với JWT/OIDC authorizer, kiểm tra:

- Issuer đúng và đang được tin cậy.
- Audience/client/resource server đúng.
- Token còn hạn và đã bắt đầu hiệu lực.
- Signing key/JWKS được cập nhật và có thể truy cập.
- Scope/role claim phù hợp route.
- Clock skew nằm trong giới hạn chấp nhận.
- Header Authorization không bị proxy xóa hoặc viết lại.
- Authorizer cache không giữ quyết định cũ sau khi quyền đã thay đổi.

Nếu gateway inject user/tenant headers cho function, chỉ tin các header được gateway tạo sau khi xác thực. Gateway phải loại bỏ header cùng tên do client gửi vào. Nếu function nhận trực tiếp request từ Internet, không tin X-User-Id, X-Tenant-Id hoặc X-Role chỉ vì chúng xuất hiện trong header.

### Gateway gọi function có được phép không?

Đây là quyền **invoke function** của gateway principal/service, không phải quyền của user cuối trong database.

Kiểm tra:
- Integration URI có đúng function, alias/version và region?
- Resource-based policy của function có cho phép gateway service principal invoke không?
- Policy có giới hạn đúng API/stage/account/source ARN không?
- Gateway có dùng alias nhưng permission chỉ cấp cho unqualified function hoặc alias khác không?
- Nếu integration dùng IAM role, role đó có quyền invoke function đích không?
- Function policy có explicit deny hoặc condition không khớp không?

Đừng cấp quyền invoke cho mọi principal hoặc mọi API chỉ để hết 403. Cấp đúng principal và source ARN của API/stage cần thiết.

## 4. Điều tra queue và event trigger

Queue/event trigger thường có hai kiểu:

- **Pull/polling:** platform hoặc event source mapping đọc message từ queue/stream rồi invoke function.
- **Push:** event provider gọi endpoint/function khi event xảy ra.

Cách kiểm tra quyền và delivery khác nhau. Với polling, function có thể không được gọi vì mapping disabled, không đọc được queue, filter loại event hoặc consumer bị throttled. Với push, resource policy hoặc invoker permission của endpoint có thể từ chối provider.

### Với queue polling

Kiểm tra theo thứ tự:

1. Producer publish thành công chưa?
2. Message có trong queue/subscription đúng không?
3. Message có nằm trong DLQ hoặc bị filter không?
4. Event source mapping/subscription có đang ENABLED không?
5. Mapping có trỏ đúng queue, topic, stream và function alias không?
6. Poller có quyền đọc/delete/ack message không?
7. Function có concurrency/quota để nhận invocation không?
8. Batch có bị một message lỗi làm retry toàn bộ không?
9. Visibility timeout/ack deadline có dài hơn thời gian xử lý không?
10. Có retry policy, redrive policy hoặc maximum age làm message hết hạn không?

Với AWS Lambda + SQS, execution role của function cần các quyền đọc queue tương ứng như sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes; nếu queue dùng KMS customer-managed key, principal cần quyền decrypt phù hợp và key policy phải cho phép. Queue cross-account còn cần resource policy ở queue. Quyền poll queue khác quyền function gọi database hoặc S3.

### Với event bus push

Ví dụ EventBridge gọi Lambda:
- Rule có ENABLED không?
- Event pattern có khớp event thực tế không?
- Target có đúng function/alias không?
- Target invocation permission có cho phép EventBridge service principal với source rule ARN không?
- Retry policy và dead-letter queue có được cấu hình không?
- Event bị archive/filter hoặc rule bị thay đổi gần đây không?

Với Pub/Sub push đến Cloud Run/HTTP function:
- Subscription push endpoint đúng URL/revision không?
- Push authentication service account có hợp lệ không?
- Service account đó có quyền invoke service (ví dụ Cloud Run Invoker) không?
- OIDC audience có khớp service URL/audience được cấu hình không?
- Subscription có backlog, delivery attempt hoặc dead-letter policy không?

### Filter và schema mismatch

Event có thể được publish thành công nhưng không match event pattern/filter. So sánh một event thật với filter đang deploy:
- Tên event/type có đúng case?
- Field nằm ở đúng cấp JSON?
- Value là string, number hay array?
- Có filter theo account/region/source không?
- Schema version mới có đổi tên field hoặc cấu trúc không?

Tạm thời không bỏ filter toàn bộ ở production chỉ để kiểm tra nếu điều đó có thể kích hoạt nhiều event không mong muốn. Hãy dùng test event có kiểm soát hoặc môi trường staging.

## 5. Phân biệt ba loại quyền quan trọng

Trong hệ thống serverless, từ “function role” thường bị dùng chung cho nhiều quyền khác nhau. Hãy tách chúng:

| Quyền | Principal | Resource | Ví dụ |
|---|---|---|---|
| Invoke permission | API Gateway, EventBridge, Pub/Sub push identity hoặc caller | Function/HTTP service | Được phép gọi function |
| Event source access | Poller/function execution role | Queue, stream, topic, KMS key | Được phép đọc/ack message |
| Runtime execution permission | Function service account/execution role | Database, object storage, secret, API | Được phép truy cập dependency |

Một function có thể invoke thành công nhưng bị AccessDenied khi đọc secret. Một function role có thể đọc S3 tốt nhưng API Gateway vẫn không có quyền invoke function. Sửa nhầm policy ở lớp khác sẽ không giải quyết lỗi.

### Identity của Java function

Ở runtime, Java SDK nên lấy credential từ provider chain hoặc workload identity do nền tảng cấp. Không nhúng access key/secret key trong code, image, environment variable hoặc file cấu hình được commit.

Ghi nhận principal thực tế bằng cơ chế identity API của cloud provider trong môi trường chẩn đoán được kiểm soát. So sánh principal đó với role/service account mà bạn nghĩ function đang chạy. Alias, revision, deployment account hoặc service account binding sai có thể khiến function dùng identity khác dự kiến.

## 6. Đọc IAM decision: identity policy và resource policy

Một request được cho phép hay từ chối có thể phụ thuộc nhiều lớp policy:

- Identity-based policy gắn vào user/role/service account.
- Resource-based policy gắn vào function, queue, bucket, secret hoặc key.
- Trust policy xác định ai được assume role/service account.
- Permission boundary hoặc session policy giới hạn quyền tối đa.
- Organization policy/SCP hoặc folder/project policy.
- Explicit deny trong bất kỳ policy áp dụng nào.
- Condition như source ARN, source account, principal tag, VPC endpoint hoặc encryption context.
- KMS key policy và grant.
- VPC endpoint policy hoặc service perimeter.

**Explicit deny luôn cần được điều tra trước.** Một Allow trong identity policy không vượt qua explicit deny ở resource policy, SCP hoặc boundary.

### Quy trình phân tích một AccessDenied

1. Lấy nguyên văn error code/message và service request ID.
2. Xác định principal thật đang gọi.
3. Xác định action cụ thể bị từ chối, ví dụ secretsmanager:GetSecretValue.
4. Xác định resource chính xác, gồm account/project, region và ARN/name.
5. Kiểm tra identity policy của principal.
6. Kiểm tra resource policy và trust relationship.
7. Kiểm tra explicit deny, boundary, SCP/session policy.
8. Nếu mã hóa bằng KMS, kiểm tra cả quyền service và key policy/grant.
9. Kiểm tra conditions, tags, source identity và region.
10. Thay đổi tối thiểu, sau đó chạy lại đúng thao tác đã thất bại.

Không chẩn đoán chỉ từ tên role. Một role có nhiều policy, permission boundary, session policy và resource policy tương tác.

### Ví dụ: quyền đọc secret

Function cần đọc secret orders/db-password. Lỗi có thể là:
- Role thiếu action đọc secret.
- Secret ARN sai account hoặc region.
- Secret có resource policy explicit deny.
- Secret dùng customer-managed KMS key nhưng role thiếu decrypt.
- KMS key policy không cho role hoặc Secrets Manager service path dùng key.
- Function đang chạy bằng role của deployment khác.
- Secret rotation đã đổi reference/config và code vẫn đọc secret cũ.

Chỉ thêm quyền đọc secret chưa chắc đủ nếu lỗi thực tế là KMS decrypt hoặc resource policy.

## 7. Chẩn đoán theo nền tảng AWS

Phần này minh họa AWS Lambda, API Gateway, SQS và EventBridge. Tên resource/ARN phải lấy từ environment thật; các lệnh dưới đây là ví dụ read-only, cần AWS CLI và quyền xem cấu hình.

### Xem cấu hình function và alias

~~~bash
aws lambda get-function-configuration \
  --function-name orders-api \
  --qualifier prod \
  --region ap-southeast-1
~~~

Kiểm tra:
- State và LastUpdateStatus.
- Runtime, handler, timeout và memory.
- Role ARN.
- Environment/config version.
- VPC config.
- Function ARN/qualifier và revision.
- LastUpdateStatusReason nếu deployment chưa hoàn tất.

Nếu không dùng alias, bỏ --qualifier. Đảm bảo đang xem đúng account và region bằng aws sts get-caller-identity và cấu hình CLI.

### Xem resource-based invoke policy

~~~bash
aws lambda get-policy \
  --function-name orders-api \
  --qualifier prod \
  --region ap-southeast-1
~~~

Kiểm tra statement có:
- Principal đúng, ví dụ apigateway.amazonaws.com hoặc events.amazonaws.com.
- Action lambda:InvokeFunction.
- Resource/qualifier đúng.
- Condition AWS:SourceArn và AWS:SourceAccount khớp nguồn thật.

Nếu function alias được invoke, policy cần áp dụng đúng resource qualifier mà integration đang gọi.

### Kiểm tra event source mapping

~~~bash
aws lambda list-event-source-mappings \
  --function-name orders-worker \
  --region ap-southeast-1
~~~

Sau khi có UUID:

~~~bash
aws lambda get-event-source-mapping \
  --uuid 11111111-2222-3333-4444-555555555555 \
  --region ap-southeast-1
~~~

Kiểm tra:
- State/StateTransitionReason.
- EventSourceArn.
- FunctionArn.
- BatchSize và MaximumBatchingWindowInSeconds.
- FilterCriteria.
- FunctionResponseTypes, nhất là ReportBatchItemFailures.
- MaximumRetryAttempts, MaximumRecordAgeInSeconds và DestinationConfig.
- LastProcessingResult nếu có.

Với SQS, kiểm tra queue attributes, redrive policy, visibility timeout và encryption. Nếu function xử lý lâu hơn visibility timeout, message có thể được giao lại trong khi lần trước vẫn chạy.

### Kiểm tra concurrency và throttling

~~~bash
aws lambda get-function-concurrency \
  --function-name orders-worker \
  --region ap-southeast-1
~~~

Kiểm tra reserved concurrency, account concurrency và concurrent execution metrics. Reserved concurrency bằng 0 có thể chặn mọi invocation. Function đạt concurrency limit có thể bị throttled dù trigger và permission đúng.

### Mô phỏng IAM policy

~~~bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::123456789012:role/orders-worker-role \
  --action-names secretsmanager:GetSecretValue \
  --resource-arns arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:orders/db-password
~~~

Simulation giúp phát hiện identity policy evaluation nhưng không nhất thiết mô phỏng đầy đủ resource policy, KMS key policy, SCP, session policy, VPC endpoint policy hoặc mọi condition runtime. Dùng kết quả như một bằng chứng, không coi nó là kết luận cuối cùng.

### CloudWatch log và metrics

Kiểm tra đúng log group/function/region và time range. Với Lambda, invocation metric có thể tăng dù Java handler log chưa có dòng đầu tiên; lỗi có thể xảy ra trong init, class loading hoặc runtime startup. Ngược lại, log có thể không xuất hiện nếu role thiếu quyền CloudWatch Logs hoặc log group sai.

Nếu cần kiểm tra log group/stream, dùng AWS Console hoặc lệnh đọc log phù hợp với quyền hiện tại. Không bật payload logging rộng trong production nếu payload chứa dữ liệu nhạy cảm.

## 8. Chẩn đoán Google Cloud Run và Cloud Functions

Trên Google Cloud, cần phân biệt identity gọi service với service account mà function dùng khi thực thi.

### Xem service và cấu hình runtime

~~~bash
gcloud run services describe orders-api \
  --region=asia-southeast1 \
  --project=my-project
~~~

Kiểm tra:
- URL và ingress.
- Service account của revision.
- Traffic split và revision đang nhận traffic.
- Container image/version.
- Environment/secret references.
- CPU/memory/concurrency/timeout.
- VPC connector hoặc network egress settings.

Với Cloud Functions gen2, function chạy trên nền Cloud Run; kiểm tra cả cấu hình function và service/revision được tạo. Đừng nhầm function source name với Cloud Run service/revision đang nhận request.

### Xem Invoker IAM policy

~~~bash
gcloud run services get-iam-policy orders-api \
  --region=asia-southeast1 \
  --project=my-project
~~~

Caller cần role invoker phù hợp (ví dụ roles/run.invoker) khi service yêu cầu IAM authentication. Nếu Pub/Sub push gọi Cloud Run, service account dùng để xác thực push phải được cấp quyền invoke service, và OIDC audience phải khớp.

Không cấp allUsers invoker chỉ để hết 403 nếu service cần private access. Nếu muốn public HTTP, đó phải là quyết định kiến trúc và cần bảo vệ ở lớp ứng dụng.

### Kiểm tra service account runtime

Service account của Cloud Run/function là principal được dùng khi code gọi Google Cloud APIs. Nó cần quyền riêng trên Secret Manager, Cloud Storage, Pub/Sub, database hoặc dịch vụ khác. Quyền roles/run.invoker của caller không tự cấp quyền cho runtime service account đọc dữ liệu.

Kiểm tra:
- Revision thực tế dùng service account nào.
- Service account có được gắn đúng project không.
- IAM binding ở resource đích có principal đúng không.
- Organization policy có giới hạn service account hoặc token không.
- Secret version có enabled và service account có quyền access không.
- Resource nằm ở project/region khác hay không.

### Kiểm tra Pub/Sub delivery

Xem subscription, push endpoint, authentication config, backlog, ack deadline, retry policy và dead-letter topic. Nếu push endpoint trả 401/403, kiểm tra push auth service account và audience. Nếu function được invoke nhưng xử lý lỗi rồi trả non-2xx, Pub/Sub sẽ retry theo subscription policy; điều này khác với việc Pub/Sub không thể invoke service.

## 9. Java runtime: phân biệt lỗi xác thực và lỗi quyền

Java code có thể gọi cloud SDK, database, secret manager hoặc API bên ngoài. Đọc exception đầy đủ và xác định service/action/resource.

| Exception/response | Hướng điều tra |
|---|---|
| AccessDeniedException, AccessDenied | IAM/resource policy/KMS/explicit deny |
| UnrecognizedClientException, invalid security token | Credential chain, expired/invalid credential, wrong account |
| SdkClientException do connect timeout | DNS/network/TLS/endpoint |
| HTTP 401 từ downstream | Token/API key thiếu, sai issuer/audience/expiry |
| HTTP 403 từ downstream | Principal nhận diện được nhưng policy từ chối |
| UnknownHostException | DNS resolver, private zone, VPC DNS |
| ConnectException: Connection refused | Host reachable nhưng port/service không accept |
| SocketTimeoutException | Network path, downstream overload hoặc timeout quá ngắn |
| SSLHandshakeException | Truststore, certificate chain, TLS/SNI/clock |

Đừng bắt mọi exception rồi log một dòng “failed”. Giữ error code, service request ID, resource identifier đã mask và correlation ID.

### Dùng default credential provider

AWS SDK for Java hoặc Google Cloud Java client nên lấy identity từ execution role/service account/workload identity. Không cấu hình access key cố định trong source code.

Ví dụ AWS SDK v2:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.services.sts.StsClient;

try (StsClient sts = StsClient.builder()
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build()) {
    var identity = sts.getCallerIdentity();
    // Chỉ log account/ARN đã được cho phép; không log credential.
}
~~~

Ví dụ này giúp xác nhận principal mà SDK resolve trong runtime. Hạn chế output identity trong production log theo chính sách; không log session token hoặc credential.

Với Google Cloud client, dùng Application Default Credentials từ service account/workload identity được nền tảng cấp. Tránh đưa service account key JSON vào container image hoặc repository.

### Log tại boundary, không log bí mật

Trong handler, log:
- Function name/revision.
- Platform request ID.
- Correlation/trace ID.
- Operation đang thực hiện.
- Downstream service và error category.
- Duration và retry attempt nếu có.

Không log Authorization header, raw JWT, API key, secret value, private key, database URL có password hoặc full request body. Nếu exception message chứa resource name hoặc user data, mask trước khi ghi.

## 10. Access denied hay network failure?

Nhiều lỗi bị gọi chung là “không có quyền” dù nguyên nhân là network.

| Dấu hiệu | Khả năng cao | Cách phân biệt |
|---|---|---|
| HTTP 403 từ service | Policy/authorization | Có response từ endpoint; kiểm tra principal và policy |
| HTTP 401 | Authentication | Kiểm tra token/credential, issuer/audience/expiry |
| DNS lookup failure | DNS/network | Không resolve được host |
| Connection timeout | Route/firewall/NAT/endpoint hoặc overload | Không có HTTP response; kiểm tra VPC path |
| Connection refused | Port/service listener | Host reachable nhưng từ chối TCP |
| TLS handshake failure | Certificate/TLS/SNI | Kết nối TCP có thể đã thành công |
| KMS AccessDenied | Key policy/permission | Service reachable nhưng decrypt bị từ chối |
| Database login failed | DB credential/DB grants | Network tới DB được nhưng authentication/authorization DB fail |

Với function trong private subnet/VPC, kiểm tra:
- Route table và NAT gateway nếu cần Internet egress.
- Security group/firewall outbound và inbound.
- Network ACL.
- Private service endpoint/PrivateLink/Private Service Connect.
- DNS resolver và private hosted zone.
- VPC connector/egress mode.
- Database endpoint, port và TLS certificate.

Nếu function gọi cloud API qua private endpoint, endpoint policy cũng có thể từ chối request dù IAM role cho phép. Kiểm tra cả policy endpoint lẫn policy resource.

## 11. Logs, metrics và traces: dựng lại một invocation

Một trace tốt liên kết được:
- Gateway request ID.
- Function platform request ID.
- Application trace/span ID.
- Event/message ID.
- Downstream request ID.

Với HTTP, truyền W3C Trace Context hoặc correlation ID qua gateway nếu nền tảng hỗ trợ. Với queue/event, đưa event ID và trace context vào message attributes/envelope; không dùng user token làm correlation ID.

### Các metric nên xem cùng nhau

| Metric | Diễn giải |
|---|---|
| Gateway requests | Request đã đến gateway chưa? |
| Authorizer 4xx | Authn/authz có chặn trước invoke không? |
| Integration errors/latency | Gateway có gọi function thành công không? |
| Function invocations | Function có được invoke không? |
| Function errors | Handler/runtime có lỗi không? |
| Throttles/concurrency | Function có bị giới hạn capacity không? |
| Queue visible messages | Message còn chờ không? |
| Oldest message age | Backlog đang già đi không? |
| DLQ depth | Message đã vượt retry policy không? |
| Downstream 4xx/5xx/timeout | Lỗi ở resource mà function gọi? |

Đọc metric trong cùng time window và cùng region/account. So sánh baseline trước/sau deployment để tìm thay đổi.

### Log startup và handler start

Trong Java, có thể log một marker ở application initialization và một marker ngay đầu handler. Hai marker giúp phân biệt:
- Function được invoke nhưng JVM/class initialization lỗi.
- Spring context startup thất bại.
- Handler đã bắt đầu và lỗi trong application service.
- Request bị chặn ở gateway nên function không được gọi.

Không log toàn bộ event JSON. Chỉ log field cần thiết và đã được phép.

## 12. Quy trình chẩn đoán từng bước

Dùng quy trình này khi on-call nhận báo cáo “function không chạy”:

~~~mermaid
flowchart TD
    A["Ghi request/event ID và thời điểm"] --> B{"Có evidence producer/gateway nhận request?"}
    B -->|Không| C["Kiểm tra client, DNS, publish và network"]
    B -->|Có| D{"Có evidence invoke/trigger delivery?"}
    D -->|Không| E["Kiểm tra route, filter, mapping, disabled trigger và invoke permission"]
    D -->|Có| F{"Function invocation metric tăng?"}
    F -->|Không| G["Kiểm tra integration error, quota và provider delivery"]
    F -->|Có| H{"Handler bắt đầu?"}
    H -->|Không| I["Kiểm tra init, runtime, handler config và log permissions"]
    H -->|Có| J{"Lỗi AccessDenied?"}
    J -->|Có| K["Xác định principal, action, resource và policy chain"]
    J -->|Không| L["Kiểm tra code, payload, timeout và dependency"]
    K --> M["Áp dụng least-privilege fix"]
    L --> N["Sửa nguyên nhân và kiểm thử"]
    M --> O["Replay/canary và xác minh metrics"]
    N --> O
~~~

### Bước 1: tái hiện bằng một request/event có kiểm soát

Dùng một request ID hoặc event ID riêng. Ghi lại timestamp UTC và payload tối thiểu. Tránh gửi hàng loạt event vào production để thử permission.

### Bước 2: tìm ranh giới cuối cùng thành công

Ví dụ:
- Gateway nhận request nhưng authorizer trả 403: chưa đến function.
- Event có trong queue nhưng mapping Disabled: chưa invoke.
- Function invocation tăng và log có handler start: trigger đã hoạt động.
- Handler log cho thấy GetSecretValue AccessDenied: lỗi nằm ở runtime identity/resource policy.

### Bước 3: xác định principal và action

Không ghi “role thiếu quyền”. Viết rõ:
- Principal: role/service account nào?
- Action: API operation nào?
- Resource: ARN/name nào?
- Context: account/project, region, source identity, encryption key?
- Policy decision: explicit deny, no matching allow, condition mismatch hay trust failure?

### Bước 4: thay đổi nhỏ nhất

Chỉ cấp action cần thiết trên resource cần thiết. Nếu cần cho một API Gateway invoke function, cấp invoke permission cho đúng source ARN. Nếu function cần đọc một secret, cấp quyền đọc/decrypt tối thiểu cho đúng secret và key. Không gắn AdministratorAccess/Owner/Editor toàn project để xử lý sự cố.

### Bước 5: xác minh sau khi sửa

- Gửi lại cùng loại request/event có kiểm soát.
- Xác nhận invocation metric và handler start.
- Xác nhận downstream operation thành công.
- Xác nhận queue ack/visibility/DLQ behavior đúng.
- Kiểm tra không có quyền rộng ngoài dự kiến.
- Theo dõi error/throttle/backlog trong một khoảng quan sát đủ dài.

## 13. Ma trận triệu chứng và hướng xử lý

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| HTTP 401 | Token, issuer, audience, expiry, JWKS | Sửa cấu hình identity/client/token |
| HTTP 403 trước invocation | Authorizer, gateway policy, invoke permission, WAF | Cấp đúng quyền caller/source |
| Gateway 502/504, invocation không tăng | Integration URI, invoke permission, timeout, region | Sửa integration hoặc permission |
| Queue có backlog, invocation bằng 0 | Mapping state, event source permissions, filter, concurrency | Enable/fix mapping và poller access |
| Event bus nhận event nhưng không gọi function | Rule pattern, target, target permission | Sửa pattern/target resource policy |
| Invocation tăng, Java log không có | Init error, runtime/handler config, log permission | Kiểm tra platform init logs và role logging |
| Java log có AccessDenied đọc secret | Runtime identity, secret policy, KMS key | Cấp quyền đọc/decrypt tối thiểu |
| Java log có 403 từ downstream API | Token/service identity và resource policy | Sửa authn/authz ở downstream |
| Timeout khi kết nối DB | VPC, route, firewall, DNS, pool | Sửa network/capacity, không cấp IAM rộng |
| Message bị giao lại nhiều lần | Handler error, ack/delete, visibility, batch response | Sửa retry/ack và idempotency |
| Function throttled | Reserved/account concurrency, downstream capacity | Điều chỉnh concurrency và backpressure |
| Chỉ một tenant/user lỗi | Membership/policy/claim/cache | Kiểm tra tenant mapping và authorization data |

## 14. Các tình huống thực tế

### Tình huống A: API Gateway trả 403 và Lambda không có invocation

Dấu hiệu:
- Client nhận 403.
- Gateway access log có request.
- Lambda invocation metric không tăng.
- Không có application log cho request.

Điều tra:
1. Xác định 403 đến từ JWT authorizer, IAM auth, API resource policy hay WAF.
2. Kiểm tra issuer/audience/scope và principal.
3. Nếu authorizer cho phép nhưng gateway không invoke Lambda, kiểm tra Lambda resource policy/integration role.
4. Kiểm tra SourceArn có khớp API ID, stage và method/path cần gọi không.
5. Gửi một request hợp lệ và so gateway request ID với Lambda request ID.

Kết luận chỉ khi xác định đúng lớp trả 403. Thêm role vào Java execution role không giúp gateway vượt qua invoke permission.

### Tình huống B: SQS có message nhưng Java worker không chạy

Dấu hiệu:
- Queue visible message count tăng.
- Lambda invocation không tăng.
- Message chưa chuyển DLQ.

Điều tra:
1. Xem event source mapping có ENABLED không.
2. Xác minh EventSourceArn và FunctionArn.
3. Kiểm tra execution role có ReceiveMessage/DeleteMessage/GetQueueAttributes không.
4. Nếu queue dùng CMK, kiểm tra decrypt và key policy.
5. Kiểm tra reserved concurrency có bằng 0 hoặc function bị throttled không.
6. Kiểm tra filter criteria có loại message không.
7. Kiểm tra queue/region/account có đúng environment không.

Khi mapping được bật lại, message cũ có thể bắt đầu được xử lý. Trước khi làm vậy, đánh giá backlog, downstream capacity và khả năng replay duplicate.

### Tình huống C: Function chạy nhưng không đọc được secret

Dấu hiệu:
- Invocation metric tăng.
- Handler log có AccessDenied khi gọi secret service.
- Database connection chưa được mở.

Điều tra:
1. Xác nhận runtime principal qua identity API hoặc platform revision config.
2. Xác định action và secret ARN/version.
3. Kiểm tra role identity policy và secret resource policy.
4. Nếu dùng KMS CMK, kiểm tra decrypt và key policy/grant.
5. Kiểm tra region và secret reference.
6. Cấp quyền tối thiểu rồi retry.

Đừng cấp quyền secret cho user gọi HTTP; principal cần quyền là workload identity của function.

### Tình huống D: Cloud Run trả 403 khi Pub/Sub push

Dấu hiệu:
- Subscription backlog tăng.
- Pub/Sub delivery attempts tăng.
- Cloud Run request log trả 403.
- Application log có thể không xuất hiện nếu request bị chặn trước container.

Điều tra:
1. Xem push endpoint có đúng URL service/revision không.
2. Xác định service account dùng để ký OIDC token.
3. Kiểm tra service account có quyền invoke service không.
4. Kiểm tra audience trong token khớp audience mà Cloud Run chấp nhận.
5. Kiểm tra ingress và service IAM policy.
6. Gửi test event từ subscription hoặc một test publisher có kiểm soát.

Quyền của service account dùng cho Pub/Sub push khác service account mà container dùng để gọi database/Secret Manager.

### Tình huống E: Function bị timeout khi truy cập database

Dấu hiệu:
- Function invocation tăng.
- Java log có connection timeout hoặc DNS failure.
- Không có HTTP 403 từ database.
- Có thể xảy ra sau khi bật VPC connector hoặc đổi subnet.

Điều tra:
1. Kiểm tra hostname/port và DNS resolution.
2. Kiểm tra route, subnet, security group/firewall và network ACL.
3. Kiểm tra NAT hoặc private endpoint.
4. Kiểm tra database connection limit và pool.
5. Kiểm tra TLS/certificate.
6. Chỉ xem xét IAM database authentication nếu đã có kết nối và lỗi cho thấy authentication/authorization.

Không chữa network timeout bằng cách cấp thêm IAM permission không liên quan.

## 15. Khắc phục an toàn và quản lý thay đổi IAM

Khi đã xác định nguyên nhân, sửa theo thứ tự:

1. Chọn đúng principal đang thực hiện action.
2. Chọn đúng action/API operation.
3. Chọn đúng resource ARN/name.
4. Thêm condition cần thiết như source account, source ARN, encryption context hoặc principal tag.
5. Kiểm tra trust policy nếu principal cần assume role.
6. Kiểm tra resource policy, KMS và endpoint policy.
7. Triển khai qua IaC/change review nếu hệ thống quản lý policy bằng code.
8. Xác minh effective permission và chạy test thực tế.

Không:
- Gắn quyền admin rộng tạm thời rồi quên thu hồi.
- Dùng wildcard resource khi chỉ cần một secret/bucket/queue.
- Cho phép public invoke để tránh cấu hình identity.
- Đưa credential vào code hoặc log.
- Sửa trực tiếp production policy mà không ghi nhận change/rollback.
- Thay đồng thời nhiều policy khi chưa biết policy nào gây lỗi.

Nếu phải dùng quyền tạm thời để khôi phục dịch vụ, cần có owner, thời hạn hết hiệu lực, audit và task thu hồi cụ thể. Ưu tiên sửa policy bằng source of truth IaC để tránh drift.

## 16. Kiểm thử trigger và permission trước production

Một test function trực tiếp không chứng minh trigger thật hoạt động. Cần test từng ranh giới:

| Test | Điều cần chứng minh |
|---|---|
| Direct invoke test | Runtime và handler khởi động |
| HTTP integration test | Route, authorizer, integration và response mapping |
| Negative auth test | Token sai/hết hạn/audience sai bị chặn |
| Invoke permission test | Gateway/event provider được phép gọi đúng function |
| Queue delivery test | Message từ queue được nhận, xử lý và ack |
| Filter test | Event match được nhận; event không match bị bỏ qua đúng chủ đích |
| Runtime IAM test | Function đọc đúng secret/object/database |
| KMS test | Encrypted resource decrypt được với runtime principal |
| Network test | DNS/TCP/TLS đến dependency hoạt động |
| Retry/DLQ test | Failure retry theo policy và cuối cùng được quan sát trong DLQ |
| Concurrency test | Function không vượt database/downstream capacity |

### Negative test rất quan trọng

Kiểm tra cả những điều phải bị từ chối:
- Principal không đúng không invoke được private function.
- API Gateway từ API khác không được invoke function.
- Function role không đọc secret ngoài phạm vi.
- Queue consumer không đọc queue khác.
- User không có tenant membership không được gọi business operation.
- Token audience sai không được chấp nhận.

Một policy test chỉ có positive case có thể bỏ sót việc cấp quyền quá rộng.

## 17. Runbook on-call mẫu

Khi nhận alert “function not triggered / AccessDenied”, điền runbook sau:

~~~text
Incident:
Environment:
Cloud account/project:
Region:
Function / alias / revision:
Trigger type:
Source resource:
First failure time (UTC):
Request ID / event ID:
Observed status / error code:

1. Producer/gateway accepted?       YES / NO / UNKNOWN
2. Trigger matched/delivery started? YES / NO / UNKNOWN
3. Invoke permission passed?        YES / NO / UNKNOWN
4. Function invocation observed?    YES / NO / UNKNOWN
5. Handler start observed?          YES / NO / UNKNOWN
6. Downstream call started?         YES / NO / UNKNOWN
7. Exact principal:
8. Exact action:
9. Exact resource:
10. Explicit deny / missing allow / condition mismatch:
11. Network path result:
12. Change made and reviewer:
13. Retest request/event ID:
14. Invocation/result verified:
15. Backlog/DLQ/throttle after fix:
16. Follow-up owner:
~~~

Đừng đánh dấu incident resolved chỉ vì HTTP request nhận 200 hoặc function invocation metric tăng. Xác nhận business effect đúng, message đã ack hoặc operation đã hoàn tất, không có duplicate side effect và backlog không tiếp tục tăng.

## 18. Observability và cảnh báo chủ động

Các alert có ích:

- HTTP 401/403 rate tăng theo route/authorizer.
- Gateway integration errors hoặc latency vượt ngưỡng.
- Function invocation giảm bất thường trong khi request/event volume tăng.
- Function errors, init errors hoặc throttles tăng.
- Queue oldest message age và visible backlog tăng.
- DLQ depth lớn hơn 0 hoặc tăng nhanh.
- Event source mapping không ở trạng thái enabled.
- AccessDenied từ secret, storage, KMS hoặc database tăng.
- Database connection acquisition/timeout tăng.
- Retry count và duplicate processing tăng.

Metric labels nên giới hạn theo function, route template, trigger type, outcome và error category. Không đưa user ID, token, message payload hoặc raw resource ID có cardinality cao vào labels.

Alert cần có:
- Threshold và evaluation window.
- Owner/on-call route.
- Dashboard/runbook liên quan.
- Điều kiện escalation.
- Hướng dẫn rollback hoặc disable trigger nếu replay có thể gây hại.

## 19. Checklist điều tra function không được trigger hoặc AccessDenied

- [ ] Ghi environment, account/project, region, function alias/revision và thời điểm UTC.
- [ ] Có request ID/event ID/correlation ID để truy vết.
- [ ] Xác nhận producer đã publish hoặc gateway đã nhận request.
- [ ] Xác nhận route/stage/deployment và integration đúng.
- [ ] Xác nhận authorizer, issuer, audience, scope và token expiry.
- [ ] Xác nhận trigger/rule/subscription/mapping đang enabled.
- [ ] Kiểm tra filter/event pattern và schema thực tế.
- [ ] Xác nhận invoke permission của gateway/provider.
- [ ] Với polling trigger, kiểm tra quyền đọc/ack queue/stream và KMS.
- [ ] Kiểm tra function invocation, error, throttle và concurrency metrics.
- [ ] Xác định runtime principal thật.
- [ ] Xác định chính xác action và resource bị từ chối.
- [ ] Kiểm tra identity policy, resource policy, trust, boundary và explicit deny.
- [ ] Kiểm tra KMS key policy, endpoint policy và cross-account conditions.
- [ ] Phân biệt 401/403 với DNS/TCP/TLS/timeout.
- [ ] Kiểm tra log permissions và runtime initialization.
- [ ] Áp dụng least-privilege change qua quy trình quản lý policy.
- [ ] Retest bằng một request/event có kiểm soát.
- [ ] Xác nhận business effect, acknowledgement, retry và DLQ.
- [ ] Theo dõi error rate, throttle và backlog sau khi khôi phục.
- [ ] Ghi lại nguyên nhân gốc, change và biện pháp phòng ngừa.

## Tự kiểm tra

1. Khác biệt giữa function không được invoke và handler đã chạy nhưng thất bại là gì?
2. Vì sao không có application log chưa đủ chứng minh function không được gọi?
3. HTTP 403 có thể xuất phát từ những lớp nào trước khi request đến handler?
4. Quyền invoke function khác quyền execution role ra sao?
5. Với SQS polling, những quyền đọc/ack nào cần được kiểm tra?
6. Vì sao EventBridge hoặc API Gateway cần resource-based invoke permission?
7. Nếu function có quyền đọc secret nhưng KMS key policy từ chối, kết quả sẽ thế nào?
8. Explicit deny, permission boundary và SCP ảnh hưởng effective permission ra sao?
9. Làm thế nào phân biệt AccessDenied với DNS hoặc connection timeout?
10. Vì sao Cloud Run invoker của Pub/Sub push khác runtime service account?
11. Những metric nào giúp xác định event đã đến trigger nhưng chưa invoke function?
12. Vì sao direct invoke test không đủ chứng minh HTTP/queue trigger hoạt động?
13. Khi nào cần kiểm tra reserved concurrency hoặc event source mapping state?
14. Vì sao không nên giải quyết incident bằng AdministratorAccess hoặc public invoke?
15. Sau khi sửa quyền, cần xác nhận những gì trước khi đóng incident?

Điều tra serverless hiệu quả bắt đầu bằng việc xác định request/event đã đi đến đâu, principal nào đang thực hiện action nào trên resource nào, và evidence cuối cùng chứng minh bước nào thành công. Tách quyền invoke, quyền đọc event source và runtime execution permission; phân biệt IAM denial với network failure; sửa policy theo least privilege rồi kiểm chứng bằng đúng trigger thật. Với Java function, request ID, structured logs, platform metrics, workload identity và integration tests giúp biến một lỗi “không chạy” mơ hồ thành nguyên nhân có thể xác minh và ngăn tái diễn.

