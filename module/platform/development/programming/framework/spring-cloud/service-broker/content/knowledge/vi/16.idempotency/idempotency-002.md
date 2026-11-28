# Cùng định danh và cùng tham số so với cùng định danh nhưng khác tham số

## Mục tiêu và bối cảnh

Trong service broker, platform có thể gửi lại một request vì timeout, mất kết nối hoặc không nhận được response. Worker cũng có thể nhận cùng một message nhiều lần do queue sử dụng cơ chế giao message at-least-once. Nếu mỗi lần nhận request broker đều tạo tài nguyên mới, một lần retry có thể tạo database, user, volume hoặc binding trùng lặp.

Idempotency giúp broker xử lý an toàn các lần gọi lặp. Tuy nhiên, chỉ so sánh định danh là chưa đủ. Cùng một instance ID có thể được gửi lại với đúng bộ tham số cũ, hoặc với một bộ tham số khác. Hai trường hợp này mang ý nghĩa khác nhau:

- **Cùng định danh, cùng tham số:** thường là request được gửi lại. Broker nên nhận diện lần thực thi đã có, trả lại kết quả hoặc operation hiện tại và không lặp side effect.
- **Cùng định danh, khác tham số:** request đang cố dùng lại một định danh cho nội dung khác. Broker cần phát hiện xung đột và xử lý theo hợp đồng của thao tác, không âm thầm coi đó là retry hợp lệ.

Bài học thuộc chương Tính lặp an toàn của module Spring Cloud Service Broker. Nội dung trình bày cách xác định request identity, chuẩn hóa và fingerprint parameters, lưu kết quả xử lý, xử lý request đồng thời và phối hợp idempotency giữa API, database, queue và backend.

Sau bài học, bạn có thể:

- Phân biệt retry hợp lệ với request xung đột.
- Xây dựng identity và request fingerprint cho provision, update, bind và deprovision.
- Chuẩn hóa JSON để so sánh parameters ổn định.
- Lưu idempotency record và operation trong database.
- Dùng unique constraint và atomic claim để xử lý request đồng thời.
- Bảo đảm backend side effect không bị lặp khi worker retry.
- Trả response nhất quán khi request giống nhau hoặc khác nhau.

## 1. Hai trường hợp có cùng định danh

Giả sử platform gửi yêu cầu tạo service instance với:

~~~http
PUT /v2/service_instances/instance-100?accepts_incomplete=true
X-Broker-API-Version: <supported-version>
Content-Type: application/json
~~~

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "organization_guid": "org-10",
  "space_guid": "space-20",
  "parameters": {
    "storage_gb": 100,
    "region": "ap-southeast-1",
    "backup_enabled": true
  }
}
~~~

Một lúc sau, do response đầu tiên bị mất, platform gửi lại request với cùng instance ID và cùng nội dung.

**Cùng identity + cùng parameters**

Broker nhận ra đây là cùng một yêu cầu về mặt nghiệp vụ. Nếu operation đang chạy, broker trả lại trạng thái/operation hiện tại theo hợp đồng OSB API. Nếu instance đã READY, broker không tạo database thứ hai.

Trường hợp khác: platform gửi lại cùng instance ID nhưng đổi storage_gb thành 300:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "organization_guid": "org-10",
  "space_guid": "space-20",
  "parameters": {
    "storage_gb": 300,
    "region": "ap-southeast-1",
    "backup_enabled": true
  }
}
~~~

**Cùng identity + khác parameters**

Đây không còn là bản sao giống hệt của request trước. Nếu broker trả success như thể request đã được xử lý, platform có thể tin rằng dung lượng đã đổi trong khi backend vẫn giữ 100 GB. Nếu broker tạo tài nguyên mới, instance ID lại trỏ đến hai tài nguyên. Broker phải phát hiện fingerprint khác và áp dụng chính sách xung đột hoặc yêu cầu client dùng thao tác update phù hợp.

## 2. Identity của một request gồm những gì?

Identity là tập giá trị dùng để xác định đối tượng nghiệp vụ mà request đang tác động. Nó không nhất thiết giống request ID của HTTP.

Với provision OSB API, các trường quan trọng thường gồm:

| Thành phần | Vai trò |
|---|---|
| platform_id | Phân biệt platform/registration đang gọi broker nếu broker phục vụ nhiều platform |
| instance_id | Định danh service instance |
| service_id | Xác định service definition |
| plan_id | Xác định plan được yêu cầu |
| tenant context | Phạm vi sở hữu như organization, space hoặc tenant |
| operation type | Provision, update, bind hoặc deprovision |

Một broker có thể dùng cặp platform_id và instance_id làm khóa instance nếu instance ID được định danh trong phạm vi platform. Nếu broker cam kết instance ID là duy nhất toàn cục, instance_id có thể là khóa chính. Quyết định này phải nhất quán trong database, API lookup, audit và backend resource naming.

### 2.1. Identity và parameters là hai lớp khác nhau

Identity cho biết request đang nói về đối tượng nào. Parameters mô tả cấu hình mà caller muốn áp dụng cho đối tượng đó.

Ví dụ:

- (platform-A, instance-100) là identity của instance.
- service_id=service-postgresql và plan_id=plan-standard xác định loại dịch vụ và plan.
- parameters.storage_gb=100 cùng các trường khác mô tả cấu hình provision.

Broker cần lưu cả identity lẫn nội dung request đã chuẩn hóa. Nếu chỉ lưu instance_id, broker không thể phân biệt request retry với request dùng lại ID cho cấu hình khác.

### 2.2. Không nhầm request ID với idempotency identity

HTTP request ID hoặc trace ID thường thay đổi giữa các lần retry. Chúng hữu ích cho log và tracing, nhưng không nhất thiết nhận diện cùng một yêu cầu nghiệp vụ.

Nếu platform gửi cùng một provision request hai lần, mỗi lần có thể có request ID khác nhau. Broker vẫn cần nhận ra hai request cùng tác động đến một instance với cùng nội dung.

Nếu client có cung cấp một idempotency key riêng theo hợp đồng tích hợp, broker có thể lưu key đó. Tuy nhiên, OSB API không yêu cầu mọi client phải gửi một header idempotency key chung cho tất cả thao tác. Vì vậy broker vẫn cần dựa vào identity OSB và dữ liệu đã lưu để xử lý request lặp.

## 3. Fingerprint của parameters

Request fingerprint là dấu vân tay được tính từ dữ liệu có ý nghĩa nghiệp vụ. Broker dùng fingerprint để so sánh request mới với request đã được chấp nhận.

Một fingerprint cho provision có thể dựa trên:

- Platform và tenant scope đã xác thực.
- instance_id.
- service_id và plan_id.
- Parameters sau khi validate và chuẩn hóa.
- Những context field thực sự ảnh hưởng đến việc tạo tài nguyên.
- Phiên bản schema hoặc quy tắc chuẩn hóa nếu cần tái hiện quyết định cũ.

Không nên đưa các giá trị thay đổi theo từng lần gọi nhưng không ảnh hưởng nghiệp vụ vào fingerprint, ví dụ trace ID, timestamp nhận request hoặc địa chỉ IP của proxy. Tham số điều khiển giao thức như accepts_incomplete thường ảnh hưởng cách phản hồi HTTP, không phải cấu hình tài nguyên; nên lưu riêng thay vì coi đó là một thay đổi cấu hình instance.

### 3.1. Vì sao phải canonicalize JSON?

Hai JSON sau có cùng ý nghĩa dù thứ tự key khác nhau:

~~~json
{
  "storage_gb": 100,
  "backup_enabled": true,
  "region": "ap-southeast-1"
}
~~~

~~~json
{
  "region": "ap-southeast-1",
  "backup_enabled": true,
  "storage_gb": 100
}
~~~

Nếu hash trực tiếp chuỗi JSON gốc, hai chuỗi có thể tạo hash khác nhau chỉ vì thứ tự thuộc tính. Vì vậy, broker nên chuyển dữ liệu thành dạng canonical trước khi tính fingerprint.

Một quy trình canonicalization:

1. Parse JSON thành cấu trúc dữ liệu.
2. Validate kiểu dữ liệu theo schema của service/plan/operation.
3. Áp dụng default theo chính sách đã công bố.
4. Chuẩn hóa biểu diễn số và chuỗi theo quy tắc rõ ràng.
5. Sắp xếp key của object theo thứ tự xác định.
6. Giữ thứ tự array nếu thứ tự có ý nghĩa; chỉ sắp xếp array khi schema nghiệp vụ định nghĩa nó như một tập hợp không thứ tự.
7. Biểu diễn null, trường vắng mặt và default theo quy tắc đã thống nhất.
8. Serialize thành canonical JSON.
9. Tính hash hoặc HMAC trên canonical representation.

Ví dụ, nếu backup_enabled có default là true, request bỏ trường này có thể tương đương request gửi rõ backup_enabled=true, nhưng chỉ khi chính sách broker đã xác định default đó cho đúng plan và phiên bản schema. Không được tự coi mọi trường thiếu tương đương null hoặc default.

### 3.2. Thiếu trường, null và giá trị mặc định

Ba request sau có thể mang ý nghĩa khác nhau:

~~~json
{
  "storage_gb": 100
}
~~~

~~~json
{
  "storage_gb": 100,
  "backup_enabled": null
}
~~~

~~~json
{
  "storage_gb": 100,
  "backup_enabled": true
}
~~~

- Trường bị thiếu: broker có thể áp dụng default nếu schema quy định.
- Trường null: chỉ hợp lệ nếu schema cho phép null; nếu không thì phải từ chối.
- Trường có giá trị true: caller đã chỉ định rõ lựa chọn.

Canonicalization phải diễn ra sau khi broker xác định cách xử lý trường thiếu và null. Nếu không, fingerprint có thể phân loại sai hai request có ý nghĩa khác nhau.

### 3.3. Hash và bảo vệ dữ liệu nhạy cảm

Có thể tính SHA-256 trên canonical JSON để so sánh payload. Tuy nhiên, nếu parameters chứa password hoặc giá trị bí mật có entropy thấp, lưu hash không khóa vẫn có thể tạo điều kiện dò đoán offline.

Các nguyên tắc:

- Không lưu canonical JSON chứa secret ở dạng bản rõ nếu không cần thiết.
- Không ghi parameters đầy đủ vào log.
- Có thể dùng HMAC với secret quản lý an toàn để tạo fingerprint khó dò đoán từ dữ liệu nhạy cảm.
- Giữ secret HMAC và phiên bản key có quản lý vòng đời.
- Nếu cần lưu request để worker thực thi, mã hóa dữ liệu nhạy cảm hoặc lưu secret trong secret manager và chỉ giữ reference.
- So sánh fingerprint theo cách không làm lộ giá trị gốc.

Fingerprint chỉ dùng để phát hiện cùng nội dung hay khác nội dung. Nó không thay thế authentication, authorization hoặc kiểm tra quyền sở hữu instance.

## 4. Quy tắc xử lý cùng identity và cùng parameters

Khi broker tìm thấy một instance hoặc operation đã tồn tại, nó cần đọc trạng thái và fingerprint đã lưu.

| Trạng thái hiện tại | Request mới cùng fingerprint | Hành vi phù hợp |
|---|---|---|
| PROVISIONING | Có | Không tạo workflow mới; trả lại operation đang chạy theo hợp đồng |
| READY | Có | Trả kết quả hiện tại; không tạo backend resource lần nữa |
| RETRY_WAIT | Có | Giữ operation hiện tại và tiếp tục retry theo lịch |
| COMPENSATING | Có | Không tạo lại resource; tiếp tục xử lý compensation |
| FAILED | Có | Trả kết quả đã lưu hoặc áp dụng chính sách retry/recovery có kiểm soát |
| DEPROVISIONING | Có | Không bắt đầu provision song song; trả conflict/trạng thái theo policy |

Cùng fingerprint không có nghĩa luôn trả HTTP 200. Response còn phụ thuộc thao tác và trạng thái operation. Ví dụ, nếu provision đang chạy bất đồng bộ, broker có thể trả lại operation token hiện tại và trạng thái phù hợp theo OSB API. Nếu provision đã hoàn tất, broker trả response tương ứng với instance đã tồn tại theo hợp đồng API.

Điều broker phải bảo đảm là không tạo side effect mới chỉ vì cùng request được gửi lại.

### 4.1. Lưu response hoặc operation token

Để trả kết quả nhất quán, broker có thể lưu:

- Operation ID.
- Operation type.
- Request fingerprint.
- Trạng thái operation.
- Response metadata đã được phép lưu.
- Thời điểm chấp nhận và hoàn tất.
- Phiên bản API/schema dùng khi xử lý.

Nếu request lặp khi operation đang chạy, broker trả lại cùng operation ID. Không sinh token mới cho cùng một operation nghiệp vụ.

Không cần lưu toàn bộ HTTP response thô nếu có thể dựng lại response từ operation record. Tránh lưu header Authorization, secret hoặc thông tin nhạy cảm không cần thiết.

## 5. Quy tắc xử lý cùng identity nhưng khác parameters

Đây là trường hợp dễ gây sai lệch dữ liệu nhất. Broker đã có instance với identity cụ thể, nhưng request mới gửi nội dung khác.

| Dữ liệu đã lưu | Request mới | Kết quả |
|---|---|---|
| instance-100, plan-standard, storage 100 GB | Cùng ID, plan và storage 100 GB | Retry tương đương |
| instance-100, plan-standard, storage 100 GB | Cùng ID, storage 300 GB | Payload conflict |
| instance-100, plan-standard | Cùng ID, plan-premium | Plan mismatch hoặc request conflict theo hợp đồng |
| instance-100, service-postgresql | Cùng ID, service-redis | Service identity mismatch |

Chính sách an toàn:

1. Không ghi đè cấu hình đã lưu bằng parameters mới của request provision lặp.
2. Không tạo tài nguyên thứ hai với cùng instance identity.
3. Không trả success như thể payload mới đã được áp dụng.
4. Trả lỗi conflict phù hợp với hợp đồng OSB API hoặc policy của broker.
5. Hướng caller sử dụng thao tác update nếu muốn thay đổi cấu hình và service hỗ trợ update.
6. Ghi audit về identity, fingerprint cũ/mới và kết quả xử lý, không ghi secret.

OSB API có quy tắc riêng về instance identity và việc service/plan được gửi trong request. Fingerprint parameters là cơ chế nội bộ bổ sung để broker phân biệt retry giống hệt với việc tái sử dụng ID cho cấu hình khác. Không nên tuyên bố rằng một hash cụ thể là yêu cầu bắt buộc của OSB API.

### 5.1. Khi nào khác parameters là một update hợp lệ?

Provision và update là hai ý định nghiệp vụ khác nhau:

- Provision tạo instance mới.
- Update thay đổi một instance đã tồn tại theo capability và schema update được công bố.

Nếu instance đã READY và caller muốn tăng storage từ 100 lên 300 GB, broker nên yêu cầu thao tác update hợp lệ. Update cần có schema riêng, kiểm tra capability tương ứng, kiểm tra previous values nếu có, xác minh quota và tạo operation update độc lập.

Không dùng một request provision lặp với payload khác để ngầm thực hiện update. Điều này làm mất ranh giới giữa tạo mới và thay đổi tài nguyên, gây khó kiểm toán và retry.

## 6. Lưu idempotency record trong database

Broker nên lưu thông tin đủ để nhận diện request đã được chấp nhận và kết quả tương ứng. Một bảng tham khảo:

~~~sql
CREATE TABLE idempotency_record (
    record_id VARCHAR(128) PRIMARY KEY,
    platform_id VARCHAR(128) NOT NULL,
    resource_type VARCHAR(32) NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    operation_type VARCHAR(32) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    operation_id VARCHAR(128),
    response_state VARCHAR(32) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_resource_operation
        UNIQUE (
            platform_id,
            resource_type,
            resource_id,
            operation_type
        )
);
~~~

Schema trên là mô hình minh họa. Một số broker cần lưu nhiều operation lịch sử cho cùng instance; khi đó unique key có thể áp dụng cho active operation hoặc idempotency key cụ thể, còn lịch sử lưu ở bảng riêng. Không đặt unique constraint trên toàn bộ lịch sử theo cách ngăn instance có nhiều update hợp lệ.

### 6.1. Lưu fingerprint cùng operation trong một transaction

Khi tiếp nhận request:

1. Xác thực platform và tenant.
2. Validate service, plan và parameters.
3. Chuẩn hóa parameters và tính fingerprint.
4. Tạo hoặc tìm idempotency record theo resource identity và operation type.
5. Nếu record chưa có, tạo instance/operation và outbox trong cùng transaction.
6. Nếu record đã có, so sánh fingerprint và state.
7. Commit trước khi trả response.

Ví dụ pseudocode:

~~~java
@Transactional
public AcceptedOperation acceptProvision(ProvisionCommand command) {
    CanonicalRequest canonical = canonicalizer.normalize(command);
    String fingerprint = fingerprintService.calculate(canonical);

    Optional<IdempotencyRecord> existing =
            idempotencyRepository.findProvision(
                    command.platformId(),
                    command.instanceId()
            );

    if (existing.isPresent()) {
        return resolveExisting(existing.get(), fingerprint);
    }

    ServiceInstance instance =
            instanceRepository.save(
                    ServiceInstance.provisioning(canonical)
            );

    BrokerOperation operation =
            operationRepository.save(
                    BrokerOperation.pendingProvision(instance.id())
            );

    idempotencyRepository.save(
            IdempotencyRecord.accepted(
                    command.platformId(),
                    command.instanceId(),
                    fingerprint,
                    operation.id()
            )
    );

    outboxRepository.save(
            OutboxEvent.provisionRequested(operation.id())
    );

    return new AcceptedOperation(operation.id());
}
~~~

Đây là pseudocode để minh họa luồng nghiệp vụ. Trong triển khai thực tế, SELECT rồi INSERT vẫn có race condition. Unique constraint phải bảo vệ lần tạo đầu tiên; nếu insert bị duplicate, transaction thua cuộc cần rollback và đọc lại record đã được transaction thắng tạo ra.

### 6.2. Unique constraint và xử lý race condition

Hai request giống nhau có thể cùng đến trước khi idempotency record tồn tại. Cả hai đều đọc không có record. Nếu không có unique constraint, cả hai có thể tạo operation.

Database cần bảo đảm chỉ một record cho resource identity/operation key. Khi một transaction nhận unique violation:

- Rollback transaction hiện tại.
- Đọc record đã được tạo bởi transaction thắng.
- So sánh fingerprint.
- Nếu fingerprint giống, trả operation/kết quả hiện tại.
- Nếu fingerprint khác, trả conflict.
- Không gọi backend từ transaction đã thua.

Không dựa vào synchronized trong Java để giải quyết race condition vì nhiều pod hoặc worker process không chia sẻ monitor.

## 7. Phân biệt idempotency theo từng thao tác OSB

Không phải mọi thao tác dùng cùng một identity key hoặc cùng quy tắc fingerprint.

| Thao tác | Identity chính | Payload cần so sánh | Hành vi khi retry |
|---|---|---|---|
| Provision | platform + instance_id | service_id, plan_id, parameters đã chuẩn hóa, tenant context liên quan | Trả operation/instance hiện có nếu giống; conflict nếu nội dung mâu thuẫn |
| Update | instance_id + operation identity/version | plan đích, parameters update, previous values liên quan | Nhận diện cùng update; không ghi đè update mới hơn |
| Bind | instance_id + binding_id | service/plan và binding parameters | Không tạo principal thứ hai |
| Unbind | instance_id + binding_id | service_id, plan_id và binding identity | Revoke an toàn một lần; request lặp không ảnh hưởng binding khác |
| Deprovision | instance_id | service_id, plan_id và owner scope | Không xóa tài nguyên lặp hoặc xóa nhầm tenant |

### 7.1. Provision

Provision dùng instance ID để nhận diện service instance. Broker cần giữ service_id và plan_id đã dùng, cùng cấu hình đã chuẩn hóa. Request cùng instance ID nhưng service hoặc plan không khớp phải được phát hiện trước khi backend bị tác động.

Nếu parameters khác, không coi đó là retry giống hệt. Nếu instance đã tồn tại, dùng update path được hỗ trợ để thay đổi cấu hình.

### 7.2. Update

Update là một thao tác hợp lệ có thể thay đổi parameters. Vì vậy, không thể áp dụng quy tắc "một instance chỉ có một fingerprint tồn tại mãi mãi". Broker cần phân biệt từng update operation.

Có thể dùng:

- operation_id riêng.
- expected instance version hoặc revision.
- request fingerprint của payload update.
- idempotency key nếu client có cung cấp.
- trạng thái operation và kết quả đã lưu.

Cùng update key và cùng fingerprint thì trả operation hiện tại. Cùng key nhưng khác fingerprint thì conflict. Một update mới có key/revision mới chỉ được nhận khi state machine cho phép.

### 7.3. Bind và unbind

Binding có identity riêng, thường là binding_id trong phạm vi instance. Hai request bind cùng binding ID và cùng nội dung không được tạo hai backend principal. Nếu cùng binding ID nhưng consumer hoặc parameters khác, broker cần từ chối hoặc áp dụng quy tắc sửa binding được thiết kế rõ ràng.

Unbind phải thu hồi quyền của đúng binding. Request lặp không được xóa principal thuộc binding khác hoặc deprovision toàn bộ instance.

### 7.4. Deprovision

Deprovision lặp có thể xảy ra khi platform không nhận được response DELETE. Broker cần nhận diện instance đã DEPROVISIONING hoặc DELETED, trả trạng thái phù hợp và không khởi tạo hai cleanup workflow cạnh tranh.

Nếu cleanup trước đó thất bại, request lặp có thể tiếp tục cùng operation hoặc tạo retry được kiểm soát. Không xóa record cần thiết để đối chiếu owner và backend reference trước khi cleanup thực sự hoàn tất.

## 8. Backend idempotency: database broker chưa đủ

Ngay cả khi database chỉ có một operation record, worker có thể gọi backend thành công rồi bị crash trước khi lưu kết quả. Khi worker chạy lại, nó không biết side effect đã xảy ra hay chưa.

Ví dụ:

1. Worker gửi yêu cầu tạo database.
2. Backend tạo database thành công.
3. Response bị mất hoặc worker restart.
4. Operation vẫn ở RUNNING/UNKNOWN trong database.
5. Worker nhận lại message.

Nếu backend hỗ trợ idempotency key, gửi cùng key cho lần retry. Nếu không, dùng resource name ổn định, tag owner và API lookup để xác định tài nguyên đã được tạo.

Một key cho step có thể được tạo từ:

~~~text
provision:{platform_id}:{instance_id}:{step_key}
~~~

Không dùng random UUID mới mỗi lần retry. Key phải ổn định cho cùng một bước nghiệp vụ.

### 8.1. Tạo tài nguyên với tên ổn định

Ví dụ backend resource name có thể được suy ra từ instance ID đã chuẩn hóa và một suffix loại tài nguyên:

~~~text
broker-pg-instance-100
broker-pg-instance-100-backup
broker-pg-instance-100-network
~~~

Tên cần tránh lộ dữ liệu nhạy cảm, tuân thủ giới hạn ký tự backend và không thể bị caller khác chiếm dụng. Khi lookup, broker phải kiểm tra metadata owner và tenant, không chỉ so sánh tên.

### 8.2. Xử lý kết quả UNKNOWN

Nếu backend timeout, broker không được giả định lệnh thất bại. Hãy chuyển step sang UNKNOWN, tra cứu theo idempotency key hoặc resource tag, rồi:

- Nếu resource tồn tại và owner khớp, lưu external ID và tiếp tục.
- Nếu resource chưa tồn tại, retry create bằng cùng key.
- Nếu resource tồn tại nhưng owner không khớp, dừng và cảnh báo.
- Nếu không thể xác minh, giữ operation ở trạng thái cần reconciliation.

Idempotency là phối hợp giữa broker và backend. Unique constraint trong database không thể tự ngăn side effect trùng ở một hệ thống bên ngoài.

## 9. Kết hợp idempotency với operation và transactional outbox

Khi chấp nhận request bất đồng bộ, broker cần ghi request fingerprint, operation và outbox event trong cùng transaction.

~~~mermaid
flowchart TD
    A[Nhận OSB Request] --> B[Validate + Canonicalize]
    B --> C[Calculate Fingerprint]
    C --> D{Identity đã tồn tại?}
    D -->|Chưa| E[Insert Instance + Idempotency Record]
    E --> F[Insert Operation + Outbox]
    F --> G[Commit]
    G --> H[Publish Message]
    H --> I[Worker gọi Backend với key ổn định]
    D -->|Có| J{Fingerprint giống?}
    J -->|Có| K[Trả operation/kết quả hiện tại]
    J -->|Không| L[Conflict]
~~~

Outbox publisher có thể gửi message nhiều lần. Consumer phải dùng operation_id hoặc event_id để xử lý idempotent. Worker không nên tin payload queue đầy đủ; hãy tải operation và request đã lưu từ database.

### 9.1. ACK và retry

Consumer chỉ ACK message sau khi:

- Operation đã hoàn tất và trạng thái được lưu; hoặc
- Retry đã được ghi bền vững vào database với next_attempt_at; hoặc
- Lỗi cuối cùng đã được ghi nhận và message được xử lý theo dead-letter policy.

Nếu worker ACK trước khi lưu trạng thái, process crash có thể làm mất công việc. Nếu worker không ACK dù đã lưu thành công, message có thể lặp; idempotency phải khiến lần lặp an toàn.

## 10. Cập nhật cấu hình và fingerprint versioning

Schema parameters và default có thể thay đổi theo thời gian. Nếu broker tính lại fingerprint của một request cũ bằng schema mới, cùng payload có thể tạo kết quả khác.

Để giữ khả năng so sánh lâu dài, lưu thêm:

- schema_version hoặc catalog revision.
- canonicalization_version.
- fingerprint_algorithm.
- fingerprint_key_version nếu dùng HMAC.
- normalized parameters reference hoặc bản snapshot cần thiết.
- service_id và plan_id tại thời điểm chấp nhận.

Khi request lặp đến, broker nên dùng quy tắc đã áp dụng cho operation ban đầu hoặc so sánh với normalized snapshot đã lưu. Không tự áp dụng default mới cho request cũ rồi kết luận payload khác.

Nếu thay đổi cách canonicalize, cần có version mới và chiến lược đọc fingerprint cũ. Không xoay HMAC key mà mất khả năng xác minh record đang hoạt động; phải lưu key version và duy trì khả năng kiểm tra trong thời gian lưu record.

## 11. Bảo mật khi so sánh request

Parameters có thể chứa secret, endpoint nội bộ hoặc thông tin tenant. Idempotency không được tạo thêm đường rò rỉ dữ liệu.

Các nguyên tắc:

- Không log canonical JSON đầy đủ.
- Không trả fingerprint hoặc hash secret cho client nếu không cần.
- Dùng HMAC khi fingerprint có thể tiết lộ dữ liệu đầu vào.
- Mã hóa snapshot parameters nhạy cảm khi lưu.
- Giữ secret trong secret manager và lưu reference.
- Xác thực và authorize trước khi tra cứu hoặc trả operation hiện có.
- Không để một tenant dò fingerprint hoặc operation của tenant khác.
- Không dùng fingerprint làm bằng chứng quyền sở hữu.
- Giới hạn kích thước request, độ sâu object và số phần tử array trước khi canonicalize.

Một request có fingerprint giống với request cũ nhưng đến từ platform khác vẫn không được nhận kết quả của instance cũ. Identity phải chứa đúng platform/tenant scope và quyền sở hữu vẫn phải được xác minh độc lập.

## 12. Kiểm thử cùng identity/cùng parameters và cùng identity/khác parameters

Bộ test cần bao phủ hai nhánh chính và các tình huống đồng thời.

| Kịch bản | Kết quả mong đợi | Backend side effect |
|---|---|---|
| Provision lần đầu | Tạo operation và instance | Một lần tạo |
| Retry cùng ID, cùng parameters | Trả operation/kết quả hiện có | Không tạo thêm |
| Cùng ID, JSON đổi thứ tự key | Fingerprint vẫn giống sau canonicalization | Không tạo thêm |
| Cùng ID, bỏ trường có default so với gửi rõ default | Giống nếu chính sách normalization xác định tương đương | Không tạo thêm |
| Cùng ID, đổi storage_gb | Conflict hoặc yêu cầu update | Không tạo thêm |
| Cùng ID, đổi plan_id | Identity/plan mismatch | Không tạo thêm |
| Cùng ID, đổi tenant/platform | Từ chối theo ownership | Không truy cập resource |
| Hai request giống nhau đồng thời | Một operation được tạo; request còn lại nhận kết quả đó | Một side effect |
| Hai request khác parameters đồng thời | Một request thắng; request kia conflict | Không tạo resource thứ hai |
| Worker nhận message lặp | Step đã hoàn tất được bỏ qua | Không lặp side effect |
| Backend timeout sau khi tạo resource | Tra cứu resource trước khi retry | Không tạo trùng |
| Update mới sau provision | Dùng update operation riêng | Chỉ thay đổi theo update |
| Request lặp sau khi instance READY | Trả trạng thái hiện tại | Không tạo lại |

### 12.1. Unit test cho fingerprint

Ví dụ:

~~~java
@Test
void canonicalFingerprintIgnoresObjectKeyOrder() {
    Map<String, Object> first = Map.of(
            "storage_gb", 100,
            "region", "ap-southeast-1"
    );

    Map<String, Object> second = new LinkedHashMap<>();
    second.put("region", "ap-southeast-1");
    second.put("storage_gb", 100);

    assertThat(fingerprintService.calculate(first))
            .isEqualTo(fingerprintService.calculate(second));
}
~~~

~~~java
@Test
void differentParametersProduceDifferentFingerprint() {
    Map<String, Object> first = Map.of("storage_gb", 100);
    Map<String, Object> second = Map.of("storage_gb", 300);

    assertThat(fingerprintService.calculate(first))
            .isNotEqualTo(fingerprintService.calculate(second));
}
~~~

Đây là test minh họa. Test thực tế cần bao gồm nested object, array, số thập phân, missing/default, null, Unicode và secret handling.

### 12.2. Test cùng identity nhưng payload conflict

~~~java
@Test
void rejectsSameInstanceWithDifferentProvisionParameters() {
    provisionService.accept(command(
            "instance-100",
            Map.of("storage_gb", 100)
    ));

    assertThatThrownBy(() ->
            provisionService.accept(command(
                    "instance-100",
                    Map.of("storage_gb", 300)
            )))
            .isInstanceOf(IdempotencyConflictException.class);

    verify(backendProvisioner, times(1)).create(any());
}
~~~

Test cần xác nhận request thứ hai không gọi backend và không ghi đè cấu hình instance đã lưu. Exception và response mapping là chi tiết nội bộ cần được ánh xạ theo OSB API version.

### 12.3. Test concurrency với database thật

Chạy hai request trong hai transaction độc lập cùng lúc:

- Cùng identity, cùng fingerprint.
- Cùng identity, fingerprint khác nhau.
- Cùng binding ID, consumer khác nhau.
- Hai update cùng expected version.

Sau khi test kết thúc, xác nhận unique constraint chỉ cho phép một identity record, chỉ có operation hợp lệ, không có outbox event mồ côi và backend fake chỉ nhận đúng số side effect dự kiến.

Dùng database thật hoặc Testcontainers để kiểm tra unique constraint và transaction isolation. Mock repository không thể chứng minh race condition đã được database ngăn chặn.

## 13. Quan sát và vận hành

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| idempotency_replay_total | Số request được nhận diện là retry giống hệt |
| idempotency_conflict_total | Số request cùng identity nhưng khác fingerprint |
| idempotency_record_lookup_total | Số lần tra cứu record |
| duplicate_key_conflict_total | Số lần database unique constraint ngăn insert trùng |
| backend_duplicate_prevented_total | Số lần backend lookup/idempotency ngăn tạo trùng |
| operation_replay_total | Số lần trả lại operation hiện tại |
| idempotency_record_age_seconds | Tuổi record còn được giữ |

Log và trace nên có platform ID, resource ID, operation ID, operation type, fingerprint version và quyết định REPLAY, CONFLICT hoặc NEW. Không ghi raw parameters, secret hoặc canonical JSON.

Khi điều tra conflict, cần xác định:

- Identity nào được dùng?
- Fingerprint cũ và mới có cùng canonicalization version không?
- Khác biệt nằm ở service, plan, tenant hay parameters?
- Request cũ đang ở trạng thái nào?
- Backend side effect đã xảy ra chưa?
- Có operation hoặc worker khác đang xử lý cùng resource không?

## 14. Những lỗi thiết kế thường gặp

- **Chỉ so sánh instance_id:** không phát hiện cùng ID nhưng service, plan hoặc parameters khác.
- **Hash raw JSON:** thứ tự key khác nhau tạo fingerprint khác dù ý nghĩa giống nhau.
- **Bỏ qua default:** request thiếu trường và request gửi rõ default bị phân loại sai.
- **Coi null giống missing:** làm thay đổi ý nghĩa dữ liệu.
- **Dùng fingerprint làm authorization:** tenant khác có thể truy cập operation không thuộc quyền.
- **Không có unique constraint:** hai request đồng thời tạo hai idempotency record.
- **Trả success cho payload conflict:** platform nghĩ cấu hình mới đã được áp dụng dù backend không thay đổi.
- **Dùng provision để ngầm update:** làm mờ ranh giới vòng đời và khó retry.
- **Chỉ idempotent trong database:** backend vẫn có thể tạo tài nguyên trùng sau timeout.
- **Tạo operation token mới mỗi lần retry:** platform theo dõi nhiều operation cho cùng một yêu cầu.
- **Không version hóa canonicalization:** thay đổi default/schema làm request cũ bị phân loại khác.
- **Log toàn bộ parameters:** có thể làm lộ credentials hoặc dữ liệu nhạy cảm.

## 15. Quy trình triển khai idempotency

Khi thêm idempotency cho một thao tác broker, hãy thực hiện:

1. Xác định resource identity và phạm vi platform/tenant.
2. Xác định các field làm thay đổi ý nghĩa nghiệp vụ.
3. Chọn schema và quy tắc default cho đúng operation.
4. Validate rồi canonicalize parameters.
5. Tính fingerprint có version; dùng HMAC nếu dữ liệu nhạy cảm cần bảo vệ.
6. Tạo unique constraint cho identity/idempotency record.
7. Trong transaction, ghi instance, operation, fingerprint và outbox.
8. Nếu record đã tồn tại, so sánh fingerprint và state.
9. Cùng fingerprint thì trả kết quả/operation hiện có; khác fingerprint thì conflict hoặc chuyển sang thao tác update được hỗ trợ.
10. Dùng backend idempotency key hoặc resource lookup cho side effect.
11. Xử lý message lặp và worker restart bằng operation/step state.
12. Viết test payload giống, payload khác, request đồng thời và backend timeout.
13. Theo dõi replay, conflict và duplicate prevention.

## Kết luận

Idempotency cần phân biệt rõ hai trường hợp: cùng định danh với cùng tham số là một lần retry có thể trả lại kết quả đã có; cùng định danh nhưng khác tham số là xung đột về ý nghĩa request và không được âm thầm coi như retry thành công. Fingerprint phải được tính từ dữ liệu đã validate và canonicalize để không phụ thuộc thứ tự key JSON, đồng thời phải giữ đúng khác biệt giữa missing, null và default.

Trong Spring Cloud Service Broker, hãy kết hợp identity theo platform/tenant, request fingerprint, unique constraint, operation record, transactional outbox và backend idempotency key. Khi request lặp đến, broker xác minh quyền sở hữu, so sánh fingerprint và trạng thái operation trước khi quyết định replay hay conflict. Cách làm này ngăn tạo tài nguyên trùng, tránh ghi đè cấu hình và giữ hành vi nhất quán khi platform retry hoặc worker xử lý message nhiều lần.
