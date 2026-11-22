# Rollback mã, cấu hình và tài nguyên có trạng thái

Rollback là đưa một hệ thống đang gặp sự cố về một trạng thái vận hành đã được xác minh. Với Java serverless, việc này không chỉ là deploy lại JAR cũ. Một release có thể bao gồm mã function, cấu hình runtime, biến môi trường, IAM policy, trigger, database schema, queue, checkpoint, object storage và các thay đổi dữ liệu do function đã thực hiện.

Vì vậy, rollback cần phân biệt ba nhóm: **mã và cấu hình có thể đổi phiên bản**, **hạ tầng có thể tái tạo bằng IaC**, và **dữ liệu/trạng thái nghiệp vụ cần bảo toàn hoặc phục hồi có kiểm soát**. Đổi alias về function version cũ có thể khôi phục code nhanh, nhưng không tự đảo ngược một migration đã xóa cột, một message đã được xử lý hay một khoản thanh toán đã gửi đến hệ thống bên ngoài.

Trong phạm vi **CLOUD_SERVERLESS**, bài học tập trung vào phát triển và triển khai Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí. Bài này xây dựng cách lập kế hoạch rollback cho code, configuration và stateful resources, từ lúc đóng gói release đến khôi phục và xác minh sau sự cố.

## 1. Rollback là khôi phục hành vi, không chỉ khôi phục file

Một release serverless thường thay đổi nhiều thành phần cùng lúc:

| Thành phần | Ví dụ thay đổi | Câu hỏi khi rollback |
|---|---|---|
| Code artifact | JAR, ZIP hoặc container image mới | Có artifact cũ bất biến và đã xác minh không? |
| Function configuration | Runtime, memory, timeout, concurrency | Cấu hình cũ có tương thích với code và trigger hiện tại không? |
| Environment/configuration | Feature flag, endpoint, schema mode | Có snapshot cấu hình không chứa secret để phục hồi không? |
| Identity và permissions | Execution role, service account, resource policy | Code cũ có còn đủ quyền và có bị cấp quyền quá rộng không? |
| Trigger/integration | API route, queue mapping, event filter | Có thể chuyển traffic hoặc tạm dừng event an toàn không? |
| Database/schema | Thêm cột, index, bảng hoặc thay đổi kiểu dữ liệu | Code cũ có chạy được trên schema mới không? |
| Persistent data | Object, record, checkpoint, workflow state | Cần retain, replay, restore hay migration bù? |
| External side effects | Email, thanh toán, webhook, lệnh thiết bị | Có cần hành động bù trừ thay vì xóa lịch sử không? |

Mục tiêu của rollback là khôi phục service behavior và bảo toàn tính đúng đắn của dữ liệu. Không phải thay đổi nào cũng có thể đảo ngược theo chiều ngược lại. Một số thay đổi cần forward-fix hoặc compensating action.

## 2. Phân biệt rollback, roll-forward và compensation

Ba cách khôi phục thường dùng:

- **Rollback:** chuyển code, config hoặc traffic về một phiên bản đã chạy tốt trước đó.
- **Roll-forward:** phát hành bản sửa mới để khắc phục lỗi trong trạng thái hiện tại, thường cần khi schema/data đã tiến lên và không tương thích với code cũ.
- **Compensation:** thực hiện một nghiệp vụ bù để cân bằng side effect đã xảy ra, ví dụ hoàn tiền hoặc hủy đơn, thay vì giả vờ rằng hành động trước chưa từng diễn ra.

| Tình huống | Hướng xử lý thường phù hợp |
|---|---|
| Function mới lỗi do bug code, schema vẫn tương thích | Rollback alias/revision về artifact cũ |
| Biến môi trường mới sai | Khôi phục config version trước và xác minh secret reference |
| Migration chỉ thêm cột nullable | Có thể rollback code; giữ schema mở rộng cho đến khi an toàn |
| Migration đã xóa/biến đổi dữ liệu không thể đảo ngược | Restore có kiểm soát hoặc roll-forward |
| Message đã kích hoạt gửi email/charge payment | Idempotency và compensation theo nghiệp vụ |
| Event checkpoint bị tiến qua event lỗi | Replay có kiểm soát từ offset/checkpoint phù hợp |
| IAM policy mới chặn invocation | Khôi phục policy tối thiểu đã biết tốt và kiểm tra principal/source |

Đừng chọn rollback chỉ vì nó là thao tác nhanh nhất. Trước tiên xác định sự cố nằm ở code, config, infrastructure hay dữ liệu; sau đó chọn cách phục hồi không làm mất thêm trạng thái hợp lệ.

## 3. Đóng gói release có thể tái triển khai

Muốn rollback đáng tin cậy, mỗi release phải có artifact bất biến. Không build lại source tag cũ rồi giả định JAR hoặc image sẽ giống hệt lần trước.

Một release record nên lưu:

- Release ID và thời điểm build/deploy.
- Git commit, repository, branch/tag và người phê duyệt.
- JAR/ZIP URI hoặc container image digest.
- SHA-256 digest của artifact.
- Java runtime, framework và dependency lock/version.
- Build provenance, signature và SBOM nếu pipeline áp dụng.
- Function version, Cloud Run revision hoặc deployment slot tương ứng.
- Config revision/manifest và secret version reference, không ghi secret value.
- IaC commit/plan và database migration version.
- Trigger, alias/traffic mapping và các feature flag quan trọng.

Ví dụ release manifest không chứa bí mật:

```json
{
  "releaseId": "orders-2026.11.17.3",
  "sourceCommit": "8f4c2b1d...",
  "artifact": {
    "uri": "registry.example.com/orders@sha256:abc123...",
    "sha256": "abc123..."
  },
  "runtime": "java21",
  "configRevision": "orders-prod-config-42",
  "migrationVersion": "V018",
  "deployment": {
    "platform": "cloud-run",
    "revision": "orders-00042-xyz"
  }
}
```

Các giá trị digest và revision ở đây là minh họa. Trong release system thực tế, lưu giá trị đầy đủ và xác minh artifact trước khi triển khai. Không đưa password, access key, private key hoặc secret value vào manifest.

## 4. Dùng immutable artifact và promote cùng một bản build

Một pipeline nên build một lần rồi promote đúng artifact đó qua dev, staging và production. Khác biệt môi trường được truyền bằng config/secret/identity, không sửa nội dung JAR hoặc image sau khi ký.

Với container, deploy theo digest thay vì tag mutable. Với JAR/ZIP, lưu artifact theo version và digest trong registry hoặc object storage có retention. Bảo vệ quyền ghi/xóa và giữ lại đủ lâu cho rollback, audit và điều tra sự cố.

Artifact cũ cần tiếp tục có thể tải về khi:

- Một canary mới bị lỗi sau khi traffic đã chuyển một phần.
- Một thay đổi IAM hoặc config được phát hiện muộn.
- Cần tái tạo môi trường staging để điều tra.
- Cần khôi phục một function version sau nhiều lần release.

Nếu registry dọn artifact theo retention quá ngắn, thao tác rollback có thể thất bại dù function version hoặc revision cũ vẫn còn metadata.

## 5. Triển khai theo version và traffic shift

Các nền tảng serverless thường cung cấp cách giữ nhiều phiên bản hoặc revision song song. Đây là nền tảng cho rollback nhanh.

| Nền tảng | Cách giữ phiên bản | Cách chuyển traffic/rollback |
|---|---|---|
| AWS Lambda | Published versions và aliases | Trỏ alias production về version đã biết tốt |
| Google Cloud Run | Immutable revisions | Chuyển traffic về revision trước |
| Azure Functions | Deployment slots ở các plan hỗ trợ | Swap slot trở lại hoặc triển khai artifact trước đó |
| Nền tảng container/FaaS khác | Version/revision/deployment tùy nền tảng | Chuyển route hoặc redeploy digest đã xác minh |

Traffic shifting cho phép thử release mới với một phần request trước khi chuyển toàn bộ. Có thể dùng canary, linear rollout hoặc blue/green tùy năng lực nền tảng. Hãy kiểm tra điều kiện hỗ trợ của plan và loại function; không phải mọi nền tảng hoặc hosting plan đều có deployment slot/traffic split giống nhau.

## 6. Rollback AWS Lambda bằng published version và alias

Lambda published version là snapshot bất biến của code và phần cấu hình versioned tại thời điểm publish. Alias là con trỏ có thể cập nhật để trỏ đến một published version. Production integration nên gọi alias thay vì gọi trực tiếp `$LATEST` nếu cần chuyển version nhanh.

Ví dụ alias `prod` hiện trỏ version `42`. Nếu version `43` gặp lỗi, có thể chuyển alias về version `42`:

```bash
aws lambda update-alias \
  --function-name orders-handler \
  --name prod \
  --function-version 42
```

Kiểm tra alias sau khi cập nhật:

```bash
aws lambda get-alias \
  --function-name orders-handler \
  --name prod
```

Các trigger/API integration cần gọi alias ARN tương ứng để traffic thực sự đi qua alias. Nếu trigger gọi function ARN không qualified hoặc `$LATEST`, cập nhật alias có thể không ảnh hưởng đường gọi đó.

Lambda alias cũng hỗ trợ routing một phần traffic đến version khác trong một số cấu hình. Khi dùng canary, cần xác định alarm và điều kiện tự động dừng/chuyển lại version. Việc đổi alias không tự đảo ngược database migration, message đã xử lý hoặc external side effect.

## 7. Rollback Cloud Run bằng revision

Mỗi lần deploy Cloud Run service tạo revision mới. Revision giữ cấu hình và image tương ứng với lần triển khai đó. Nếu revision mới có lỗi, có thể chuyển traffic về revision cũ.

Ví dụ:

```bash
gcloud run services update-traffic orders-service \
  --region=asia-southeast1 \
  --to-revisions=orders-service-00041-abc=100
```

Thay revision name bằng revision đã biết tốt trong service. Kiểm tra traffic mapping sau khi cập nhật và xác nhận revision cũ vẫn sẵn sàng phục vụ.

Cloud Run revision rollback chỉ đổi traffic. Nếu config mới nằm ở Secret Manager, database schema hoặc resource khác ngoài revision, cần xử lý riêng. Ngoài ra, nếu revision cũ dùng secret version đã bị disable/xóa hoặc service account đã bị thu hồi quyền, chuyển traffic về revision cũ vẫn có thể lỗi.

## 8. Rollback Azure Functions bằng deployment slot hoặc artifact cũ

Với Azure Functions trên các hosting plan hỗ trợ deployment slots, có thể triển khai bản mới vào slot staging, kiểm tra rồi swap với production. Khi phát hiện lỗi sau swap, có thể swap lại nếu trạng thái slot và cấu hình còn phù hợp.

Một số application settings có thể được đánh dấu là slot-specific (deployment slot setting). Cần xác định setting nào đi theo slot và setting nào đi cùng nội dung swap. Nếu connection string, storage account hoặc secret reference bị hoán đổi ngoài ý muốn, function có thể truy cập nhầm môi trường.

Deployment slots không có trên mọi plan hoặc mọi cấu hình Functions. Khi không có slot, giữ artifact version cũ và triển khai lại đúng package đã phát hành. Dù dùng slot hay redeploy, vẫn phải kiểm tra trigger, managed identity, host storage, app settings và quyền truy cập sau rollback.

## 9. Quản lý configuration như một phần của release

Code cũ có thể không chạy được nếu cấu hình hiện tại đã thay đổi. Một release manifest nên tham chiếu đến config revision hoặc version của các giá trị quan trọng.

Nhóm cấu hình thường cần quản lý:

- Feature flags và business rule toggles.
- Endpoint của database, queue, API hoặc object storage.
- Timeout, retry count, batch size, concurrency và memory.
- Event filter, queue/topic/subscription name và consumer group.
- Log level, tracing sampling và metric dimensions.
- Secret reference/version, certificate và encryption key reference.

Lưu cấu hình không bí mật trong source control hoặc config store có versioning. Với secret, chỉ lưu reference và version ID trong release record; không sao chép secret value vào Git, artifact, log hoặc manifest.

Khi rollback config:

1. Xác định setting nào thay đổi cùng release.
2. Xác minh code cũ có tương thích với giá trị cũ và tài nguyên hiện tại.
3. Khôi phục config revision đã biết tốt hoặc cập nhật đúng setting cần thiết.
4. Giữ lại các thay đổi bảo mật khẩn cấp như credential đã bị thu hồi; không phục hồi một secret bị nghi lộ chỉ để làm code cũ chạy.
5. Kiểm tra function đã nhận config mới và không còn instance dùng giá trị cũ ngoài dự kiến.

## 10. Rollback secret và credential rotation

Secret có vòng đời riêng. Nếu một secret bị rotate vì hết hạn hoặc bị lộ, không nên rollback về secret cũ chỉ vì release trước đang dùng nó.

Ví dụ an toàn hơn:

- Code mới và code cũ đều đọc secret qua stable reference.
- Secret manager giữ version hiện tại và có thể giữ version trước trong thời gian chuyển tiếp.
- Khi rotate, hệ thống cập nhật credential ở phía server trước hoặc hỗ trợ overlap hai credential trong thời gian ngắn.
- Sau khi mọi consumer dùng credential mới, thu hồi credential cũ.

Nếu release cũ hard-code hoặc chỉ hiểu credential cũ, cần sửa code hoặc config adapter để hỗ trợ rotation trước khi thu hồi. Khôi phục credential đã bị compromise là hành động nguy hiểm và có thể mở lại quyền cho attacker.

## 11. Database migration phải tương thích ngược

Database thường là phần khó rollback nhất vì code mới có thể đã ghi dữ liệu theo schema mới. Một migration phá hủy như xóa cột, đổi kiểu dữ liệu hoặc đổi ý nghĩa field có thể khiến code cũ không còn chạy được.

Một chiến lược phổ biến là **expand–migrate–contract**:

1. **Expand:** thêm cột/bảng/index mới theo cách không phá vỡ code cũ, thường cho phép giá trị null hoặc có default an toàn.
2. **Migrate:** deploy code có thể đọc cả schema cũ và mới; backfill dữ liệu theo batch; có thể dual-write trong thời gian chuyển tiếp nếu thiết kế bảo đảm nhất quán.
3. **Switch:** chuyển toàn bộ consumer sang field/schema mới và quan sát.
4. **Contract:** chỉ ở release sau, khi không còn code cũ hoặc consumer cũ, mới xóa field/bảng cũ.

Ví dụ thêm cột mới:

```sql
ALTER TABLE orders
ADD COLUMN fulfillment_status_v2 VARCHAR(32);
```

Code mới có thể ghi cả `fulfillment_status` và `fulfillment_status_v2` trong giai đoạn chuyển tiếp. Code cũ vẫn đọc cột cũ. Sau khi backfill và mọi consumer đã chuyển sang field mới, có thể ngừng ghi field cũ; việc xóa cột cũ nên là một migration riêng sau khi rollback window đã kết thúc.

Không thực hiện expand và contract trong cùng một release nếu cần khả năng rollback code nhanh. Rollback binary chỉ an toàn khi schema vẫn tương thích với binary đó.

## 12. Khi nào cần restore database thay vì rollback code?

Restore database là thao tác phục hồi dữ liệu từ snapshot hoặc point-in-time recovery (PITR). Chỉ dùng khi dữ liệu bị hỏng, xóa nhầm hoặc migration làm sai dữ liệu và không thể sửa bằng migration bù.

Restore có rủi ro:

- Dữ liệu hợp lệ được ghi sau thời điểm snapshot/PITR có thể bị mất.
- Endpoint/hostname của database restore có thể khác; function cần cập nhật config.
- Secret, security group, network route và IAM database authentication cần được kiểm tra.
- Database restore có thể mất thời gian và làm gián đoạn xử lý.
- Queue/event đã được ack sau thời điểm restore có thể không tự xuất hiện lại trong database.

Thường nên restore sang instance/database mới, xác minh dữ liệu, sau đó chuyển traffic hoặc endpoint theo runbook. Nếu cần phục hồi một phần, cân nhắc export/reconcile record thay vì thay toàn bộ database. Luôn thử restore định kỳ; một snapshot chưa từng restore thành công chưa phải bằng chứng đủ về khả năng phục hồi.

## 13. Rollback dữ liệu object storage

Object storage có thể hỗ trợ versioning hoặc retention. Với S3 versioning, một lần ghi đè tạo object version mới; có thể đọc version cũ nếu version ID còn tồn tại và quyền truy cập cho phép.

Điều cần lưu ý:

- Xóa object trong bucket versioned có thể tạo delete marker thay vì xóa mọi version.
- Lifecycle policy có thể xóa version cũ sau thời gian retention.
- Object Lock/retention/legal hold có thể ngăn xóa hoặc sửa object.
- KMS key cần tiếp tục tồn tại và được phép giải mã version cũ.
- Event notification có thể phát sinh event mới khi phục hồi/copy object; cần tránh kích hoạt lại pipeline ngoài ý muốn.

Nếu function tạo file đầu ra sai, có thể tạo bản sửa mới hoặc copy lại version đúng sang key đích. Trước khi phục hồi, xác định consumer nào đang đọc key đó và có cần cập nhật metadata/index/cache tương ứng không.

## 14. Rollback queue, message và event stream

Message đã được xử lý không thể tự động “unprocess” chỉ bằng cách deploy code cũ. Cần phân biệt message còn chờ, message đang in-flight, message đã ack/complete và event có thể replay từ retention.

| Nguồn | Trạng thái cần xem | Hướng phục hồi |
|---|---|---|
| SQS/queue | Visible, in-flight, DLQ, retention | Dừng consumer, giữ message, redrive DLQ hoặc phát lại có kiểm soát |
| Service Bus | Active, locked, deferred, dead-letter | Dừng consumer, kiểm tra lock/delivery count, replay DLQ theo quy trình |
| Pub/Sub | Unacked message, ack deadline, subscription retention | Điều chỉnh consumer, seek/replay theo khả năng subscription và retention |
| Event Hubs/Kafka-like stream | Offset/checkpoint, partition, retention | Dùng consumer group/replay offset phù hợp; chấp nhận event có thể chạy lại |
| S3 event | Object version và notification | Phát lại event hoặc chạy reconciliation theo danh sách object |

Trước khi dừng consumer, xác định liệu backlog có tiếp tục tăng hay không. Nếu release lỗi dữ liệu nhưng vẫn ack message, cần biết message nào đã xử lý và lưu event ID/idempotency key để có thể replay có chọn lọc.

Khi reset checkpoint hoặc redrive DLQ, event có thể được xử lý lại. Consumer phải idempotent; nếu không, replay có thể tạo đơn hàng, gửi email hoặc charge payment lần thứ hai.

## 15. External side effects cần compensation

Một function có thể gọi dịch vụ thanh toán, gửi email, tạo ticket hoặc gửi webhook. Những hành động này đã xảy ra bên ngoài hệ thống và không thể được hoàn tác bằng cách khôi phục database snapshot.

Ví dụ:

- Nếu payment đã được capture, gọi API refund/void theo quy tắc nghiệp vụ.
- Nếu email đã gửi, không thể thu hồi; có thể gửi thông báo đính chính nếu cần.
- Nếu webhook đã gửi đến partner, dùng idempotency key và reconciliation API để xác định kết quả.
- Nếu đơn hàng đã được chuyển kho, cần lệnh hủy/return workflow.

Đây là compensation trong saga, không phải rollback vật lý. Lưu business event, external request ID, idempotency key và kết quả để điều tra. Không xóa audit trail nhằm làm trạng thái trông như chưa từng xảy ra.

## 16. Idempotency giúp rollback và replay an toàn

Rollback thường đi kèm retry, redrive hoặc replay. Nếu một event có thể được xử lý nhiều lần, side effect cần idempotent.

Một mẫu đơn giản:

```java
public void handle(OrderSubmitted event) {
    String key = "order-submitted:" + event.eventId();

    idempotencyStore.executeOnce(key, () -> {
        orderService.submit(event.orderId());
        return null;
    });
}
```

`executeOnce` là port minh họa. Triển khai thực tế cần lưu key bằng database/shared store có conditional write hoặc transaction. Không dùng `static Set` trong function instance vì instance có thể restart, scale-out hoặc chạy song song.

Với external API, truyền idempotency key xuống provider nếu họ hỗ trợ. Nếu một invocation ghi database rồi timeout trước khi ack message, lần retry cần nhận biết thao tác đã hoàn tất. Outbox pattern có thể giúp commit trạng thái nghiệp vụ và event cần phát trong cùng transaction, sau đó relay event theo cơ chế retry an toàn.

## 17. Rollback Infrastructure as Code

IaC quản lý function, IAM, trigger, queue, bucket, database và network. Một lần `apply` hoặc stack update có thể tạo, sửa, replace hoặc xóa tài nguyên.

Trước khi rollback infrastructure:

1. Lưu lại IaC commit và plan/change set đã triển khai.
2. Xác định resource nào bị thay đổi tại chỗ, resource nào bị replacement hoặc deletion.
3. Kiểm tra `DeletionPolicy`, `UpdateReplacePolicy`, `prevent_destroy`, snapshot và retention.
4. Kiểm tra dependency giữa stack/module và resource được shared bởi ứng dụng khác.
5. Khôi phục cấu hình IaC trước đó hoặc tạo một change set/plan mới đã review.
6. Xác minh drift và dữ liệu thực tế trước khi apply.

Không chạy `terraform apply` trên một commit cũ một cách mù quáng. State hiện tại có thể đã thay đổi, resource đã được thay thế hoặc dữ liệu đã được tạo sau release. Tạo plan mới từ state hiện tại và review mọi thao tác destroy/replace.

CloudFormation rollback có thể khôi phục một số thay đổi resource theo template trước, nhưng không thể hoàn tác side effect bên ngoài như message đã gửi, API call hoặc database migration không được quản lý bởi stack.

## 18. IAM, trigger và network khi rollback

Một function version cũ có thể phụ thuộc vào IAM policy hoặc endpoint đã thay đổi. Khi rollback code, cần kiểm tra:

- Execution role/service account còn được gắn và có đúng quyền tối thiểu không.
- Resource-based policy còn cho phép API gateway, queue, event bus hoặc storage gọi function không.
- Secret/KMS key version còn truy cập được không.
- Security group, VPC connector, private endpoint và DNS có còn đúng không.
- Event filter, batch size, timeout và concurrency có phù hợp với code cũ không.
- API schema và event schema mà producer phát ra có tương thích với consumer cũ không.

Không rollback IAM policy về một cấu hình quá rộng chỉ để khôi phục nhanh. Nếu permission mới vô tình chặn function, sửa đúng statement/condition và kiểm tra cả allow lẫn deny path.

## 19. Canary, blue/green và tiêu chí tự động rollback

Thay vì chuyển 100% traffic ngay, có thể rollout theo từng bước:

1. Deploy release mới nhưng chưa nhận traffic production.
2. Smoke test bằng test route hoặc synthetic event.
3. Chuyển một tỷ lệ traffic nhỏ sang release mới.
4. Theo dõi error rate, latency, throttling, business metric và downstream health.
5. Tăng traffic theo từng bước nếu các ngưỡng đạt.
6. Nếu vượt ngưỡng, dừng rollout và chuyển traffic về revision/version cũ.

Các tín hiệu có thể kích hoạt rollback:

- HTTP 5xx hoặc function error rate tăng vượt baseline.
- p95/p99 latency vượt SLO trong một khoảng thời gian.
- Queue backlog, consumer lag hoặc DLQ tăng nhanh.
- Database connection pool cạn hoặc query latency tăng.
- Tỷ lệ nghiệp vụ thất bại tăng, ví dụ payment decline do bug hoặc order không chuyển trạng thái.
- Metric bảo mật cho thấy access denied bất thường hoặc request trái phép tăng.

Không chỉ dùng CPU hoặc invocation success làm tiêu chí. Một function có thể trả HTTP 200 nhưng ghi sai dữ liệu. Cần metric nghiệp vụ và kiểm tra consistency sau deploy.

## 20. Runbook rollback theo thứ tự

Khi có sự cố production, một runbook rõ ràng giúp giảm quyết định tùy hứng.

### Giai đoạn A — Đánh giá và giới hạn tác động

1. Ghi nhận release ID, function version/revision, thời điểm bắt đầu lỗi và phạm vi ảnh hưởng.
2. Xác định lỗi thuộc code, config, IAM, trigger, dependency hay dữ liệu.
3. Nếu function đang tạo thêm dữ liệu sai, tạm dừng trigger/traffic theo cách có kiểm soát.
4. Giữ queue/event chưa xử lý; không xóa message hoặc checkpoint để làm sạch dashboard.
5. Bảo toàn log, trace, request ID, event ID và release manifest.

### Giai đoạn B — Chọn phương án khôi phục

1. Kiểm tra artifact cũ và chữ ký/digest.
2. Xác minh schema hiện tại tương thích với code cũ.
3. Kiểm tra config/secret/permission cần cho code cũ.
4. Quyết định rollback code, rollback config, roll-forward migration hay compensation.
5. Nếu cần restore dữ liệu, ước lượng data loss window và chọn điểm phục hồi được phê duyệt.

### Giai đoạn C — Thực hiện

1. Chuyển alias/traffic/slot về release đã biết tốt hoặc deploy lại artifact đã xác minh.
2. Khôi phục config revision phù hợp.
3. Chỉ thay đổi IAM/trigger/network ở phần gây lỗi và review quyền.
4. Thực hiện migration bù hoặc compensation nếu nghiệp vụ cần.
5. Bật lại consumer/trigger theo từng bước sau khi smoke test.

### Giai đoạn D — Xác minh và đóng sự cố

1. Gửi HTTP request và event test đại diện cho luồng thật.
2. Xác minh invocation, log, trace, response và side effect.
3. Theo dõi queue backlog, retry, DLQ, database và business metrics.
4. Đối soát các event đã xử lý trong khoảng sự cố.
5. Ghi release ID/digest đã phục hồi, thao tác compensation và dữ liệu cần reconcile.
6. Lập follow-up để sửa nguyên nhân gốc và cập nhật runbook.

## 21. Ví dụ rollback một Java order processor

Giả sử release `orders-v43` bổ sung một trường `fulfillmentStatusV2`, nhưng code mới ghi giá trị không hợp lệ khiến consumer downstream từ chối đơn hàng. Release `orders-v42` vẫn đọc được schema cũ và cột mới được thêm theo kiểu nullable.

Một trình tự xử lý hợp lý:

1. Dừng rollout và chuyển alias/revision về `orders-v42`.
2. Giữ nguyên cột `fulfillmentStatusV2`; không drop cột trong lúc sự cố.
3. Tạm dừng hoặc điều tiết consumer tạo ra dữ liệu lỗi nếu cần.
4. Xác định event ID và order ID bị ảnh hưởng từ log/trace.
5. Sửa dữ liệu sai bằng migration bù hoặc job reconciliation có idempotency.
6. Replay các message bị cách ly sau khi dữ liệu đã được sửa.
7. Build `orders-v44` với validation và mapping đúng; test trên staging trước khi canary.
8. Chỉ xóa cột cũ trong một release sau khi mọi consumer đã chuyển và rollback window đã đóng.

Ví dụ này cho thấy rollback code có thể nhanh, trong khi schema và dữ liệu cần giữ nguyên để tránh làm mất thông tin hoặc khiến code cũ không chạy được.

## 22. Các lỗi thường gặp khi rollback

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Deploy code cũ nhưng function vẫn lỗi | Config, IAM, secret hoặc network đã thay đổi | So sánh release manifest và kiểm tra dependency ngoài code |
| Alias trỏ version cũ nhưng request vẫn vào bản mới | Trigger/API gọi `$LATEST` hoặc ARN không qualified | Kiểm tra integration target và alias ARN |
| Revision cũ nhận traffic nhưng không khởi động | Secret version, service account hoặc dependency đã bị thu hồi | Khôi phục dependency an toàn, không phục hồi secret bị compromise |
| Code cũ lỗi với database hiện tại | Migration phá vỡ backward compatibility | Roll-forward hoặc migration bù; không xóa dữ liệu tùy tiện |
| Message được xử lý hai lần sau replay | Consumer không idempotent | Dùng idempotency key và reconciliation |
| Queue mất message sau rollback | Queue/retention bị xóa hoặc message đã ack | Kiểm tra DLQ, archive và nguồn event có thể replay |
| Restore database làm mất giao dịch mới | Chọn điểm PITR quá cũ | Restore song song và reconcile dữ liệu sau điểm phục hồi |
| Terraform rollback muốn xóa database | IaC commit cũ chứa destroy/replace | Review plan, bảo vệ resource và snapshot trước apply |
| Secret cũ hoạt động nhưng không an toàn | Rollback đã khôi phục credential bị lộ | Giữ rotation, cập nhật code/config để dùng credential mới |
| Rollback xong nhưng business metric vẫn sai | Side effect đã xảy ra trước khi đổi code | Chạy compensation và đối soát dữ liệu |

## 23. Checklist thiết kế release có thể rollback

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Artifact có bất biến? | JAR/ZIP/image digest, signature và provenance |
| Có giữ release trước? | Registry retention và quyền đọc artifact cũ |
| Có biết version/revision đang chạy? | Release manifest, alias/revision mapping |
| Config có version? | Config revision và secret version reference |
| Schema có backward-compatible? | Expand–migrate–contract và kiểm thử code N/N-1 |
| Dữ liệu có thể phục hồi? | Backup/PITR, object versioning và restore test |
| Event có thể replay? | Retention, DLQ, checkpoint/offset và idempotency |
| External side effect có compensation? | Business workflow, provider request ID và audit record |
| IaC có thể rollback an toàn? | Plan/change set, dependency graph và deletion protection |
| Có tiêu chí rollback? | SLO, business metric, alarm và người chịu trách nhiệm |
| Runbook có được thử? | Diễn tập rollback/restore trong staging |
| Có thể xác minh sau phục hồi? | Smoke test, reconciliation và quan sát backlog/error |

## 24. Diễn tập rollback và cải thiện thời gian phục hồi

Rollback cần được thử trước khi xảy ra incident. Trong staging, thực hiện các bài diễn tập:

- Deploy release mới rồi cố ý tạo lỗi HTTP để kiểm tra chuyển traffic về revision cũ.
- Thay đổi một setting rồi khôi phục config revision trước.
- Thêm schema mới và xác minh code cũ vẫn hoạt động.
- Tạo message lỗi, chuyển vào DLQ và replay sau khi sửa consumer.
- Restore database snapshot/PITR sang môi trường mới và kiểm tra dữ liệu.
- Tạo object version mới rồi phục hồi version trước.
- Thử apply IaC có replacement trong môi trường test và kiểm tra resource retention.
- Giả lập secret rotation rồi rollback code mà không bật lại credential cũ.

Đo thời gian phát hiện, thời gian quyết định, thời gian chuyển traffic và thời gian đối soát dữ liệu. Các chỉ số này giúp xác định rollback nào có thể tự động, rollback nào cần approval và tài nguyên nào cần chuẩn bị trước.

Rollback tốt không chỉ đưa request về code cũ. Nó phải giữ cho code, cấu hình, quyền, trigger và dữ liệu cùng ở trạng thái tương thích. Với Java serverless, hãy giữ artifact bất biến, triển khai theo version/revision, thiết kế schema tương thích ngược, lưu trạng thái có thể phục hồi, xử lý replay bằng idempotency và dùng compensation cho side effect bên ngoài. Khi những điều kiện này được chuẩn bị từ lúc thiết kế release, rollback trở thành một thao tác vận hành có thể kiểm soát thay vì một lần thử may rủi trong sự cố.
