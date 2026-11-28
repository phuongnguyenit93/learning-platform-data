# Lưu kết quả cuối, thời hạn lưu và xử lý operation không còn hợp lệ

Khi một thao tác provision, update hoặc deprovision cần chạy lâu hơn thời gian xử lý HTTP, service broker có thể tiếp nhận yêu cầu rồi thực hiện ở background. Nền tảng nhận response chấp nhận xử lý và định kỳ gọi endpoint last operation để biết thao tác còn chạy, đã thành công hay thất bại. Để polling hoạt động đáng tin cậy, broker phải lưu kết quả cuối đủ lâu sau khi worker hoàn tất.

Một lỗi thiết kế phổ biến là xóa operation ngay khi đánh dấu thành công hoặc thất bại. Worker có thể đã hoàn tất, nhưng nền tảng vẫn đang chờ lần polling tiếp theo. Nếu record đã biến mất, broker không thể phân biệt thao tác đã hoàn tất với operation ID chưa từng tồn tại. Ngược lại, giữ mọi operation vĩnh viễn khiến state store tăng không giới hạn và làm lộ thêm dữ liệu vận hành không cần thiết.

Trong module SPRING_CLOUD_SERVICE_BROKER, cần xác định riêng vòng đời xử lý operation, thời gian lưu kết quả terminal và chính sách cho operation không còn hợp lệ. Thời hạn lưu kết quả phải đủ cho nền tảng nhận được kết quả cuối; việc dọn dẹp phải không ảnh hưởng operation đang chạy hoặc instance còn cần được quản lý.

## 1. Vì sao phải lưu kết quả cuối

Với thao tác bất đồng bộ, response ban đầu không chứa kết quả cuối cùng. Broker thường trả trạng thái accepted cùng operation key để nền tảng truy vấn sau:

~~~http
PUT /v2/service_instances/instance-123?accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json

{
  "service_id": "postgres-service",
  "plan_id": "standard-plan",
  "parameters": {
    "storageGb": 200
  }
}
~~~

Ví dụ response chấp nhận xử lý:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "operation": "op-8f31a6",
  "dashboard_url": "https://broker.example.test/operations/op-8f31a6"
}
~~~

Trường operation là khóa để nền tảng tham chiếu thao tác đang chạy nếu broker trả trường này. Khi polling, nền tảng gọi endpoint last operation với instance ID, service ID, plan ID và operation key theo hợp đồng OSB:

~~~http
GET /v2/service_instances/instance-123/last_operation?service_id=postgres-service&plan_id=standard-plan&operation=op-8f31a6
X-Broker-API-Version: 2.17
~~~

Kết quả cuối có thể là:

~~~json
{
  "state": "succeeded",
  "description": "Đã mở rộng database lên 200 GB"
}
~~~

Hoặc:

~~~json
{
  "state": "failed",
  "description": "Không thể mở rộng storage theo cấu hình yêu cầu"
}
~~~

Các giá trị trạng thái OSB thường được dùng cho last operation là in progress, succeeded và failed. Trạng thái nội bộ của broker có thể chi tiết hơn, nhưng response phải được ánh xạ về các giá trị mà phiên bản OSB công bố hỗ trợ.

Nếu broker xóa record ngay sau khi worker ghi SUCCEEDED, lần polling tiếp theo không thể nhận được trạng thái thành công. Vì thế, terminal result là một phần của hợp đồng bất đồng bộ, không chỉ là dữ liệu debug của worker.

## 2. Phân biệt vòng đời operation và thời gian lưu kết quả

Operation có hai mốc thời gian khác nhau:

- **Processing lifetime:** từ lúc broker chấp nhận yêu cầu đến khi thao tác đạt trạng thái terminal.
- **Result retention period:** khoảng thời gian broker tiếp tục giữ kết quả sau khi thao tác đã thành công hoặc thất bại.

Ví dụ, provision mất 4 phút và broker giữ kết quả cuối thêm 24 giờ. Operation tồn tại tổng cộng hơn 24 giờ tính từ lúc bắt đầu, nhưng retention chỉ bắt đầu khi operation hoàn tất.

Không nên dùng một TTL cố định tính từ created_at cho cả operation đang chạy lẫn operation đã hoàn tất. Nếu operation kéo dài hơn TTL, record có thể bị xóa trong khi worker vẫn đang tạo tài nguyên. Thay vào đó, chỉ đặt expires_at sau khi operation chuyển sang trạng thái terminal.

| Mốc | Ý nghĩa |
|---|---|
| created_at | Thời điểm broker chấp nhận operation |
| started_at | Thời điểm worker bắt đầu xử lý |
| updated_at | Lần gần nhất trạng thái/checkpoint thay đổi |
| completed_at | Thời điểm operation đạt trạng thái terminal |
| expires_at | Thời điểm kết quả được phép dọn theo retention policy |

expires_at không phải deadline để worker hoàn thành. Nếu operation vẫn PENDING hoặc IN_PROGRESS, không được xóa chỉ vì thời gian kể từ created_at đã dài. Operation chạy quá lâu cần được phát hiện bằng timeout/deadline và recovery policy riêng.

## 3. Mô hình dữ liệu operation

Một record operation nên lưu đủ dữ liệu để xử lý polling, retry, audit và dọn dẹp:

~~~java
public record OperationRecord(
        String operationId,
        String instanceId,
        String serviceId,
        String planId,
        String operationType,
        String status,
        String requestFingerprint,
        String resultCode,
        String resultDescription,
        Instant createdAt,
        Instant startedAt,
        Instant completedAt,
        Instant expiresAt,
        long version) {
}
~~~

Đây là mô hình nội bộ minh họa do ứng dụng định nghĩa, không phải DTO OSB. Có thể bổ sung attempt, leaseUntil, workerId, correlationId, previousPlanId, targetPlanId hoặc tham chiếu checkpoint tùy nhu cầu. Không nên lưu password, token hoặc toàn bộ request parameters trong operation nếu không cần thiết.

Các trường định danh cần được ràng buộc:

- operationId là khóa ổn định mà nền tảng có thể gửi lại trong polling.
- instanceId liên kết operation với service instance.
- serviceId và planId giúp xác minh ngữ cảnh request theo hợp đồng.
- operationType phân biệt provision, update và deprovision.
- requestFingerprint giúp phát hiện request retry cùng khóa nhưng payload khác.
- status điều khiển state machine nội bộ.
- resultCode và resultDescription lưu kết quả terminal đã chuẩn hóa, không lưu exception hoặc stack trace thô.
- completedAt và expiresAt hỗ trợ retention và cleanup.

Operation key nên khó đoán và không chứa secret. Không dùng operation key như một bearer credential thay cho xác thực endpoint; caller vẫn phải được xác thực theo cơ chế broker.

## 4. State machine và kết quả terminal

Một state machine nội bộ có thể gồm:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> IN_PROGRESS
    IN_PROGRESS --> IN_PROGRESS: checkpoint / retry
    IN_PROGRESS --> SUCCEEDED
    IN_PROGRESS --> FAILED
    PENDING --> CANCELLED
    SUCCEEDED --> RETAINED
    FAILED --> RETAINED
    CANCELLED --> RETAINED
    RETAINED --> EXPIRED
    EXPIRED --> PURGED
~~~

RETAINED, EXPIRED và PURGED có thể là trạng thái quản trị dữ liệu nội bộ; không nhất thiết trả chúng trực tiếp qua OSB. Khi trả last operation, broker ánh xạ:

| Trạng thái nội bộ | Trạng thái OSB |
|---|---|
| PENDING | in progress |
| IN_PROGRESS | in progress |
| SUCCEEDED | succeeded |
| FAILED | failed |
| CANCELLED | Theo kết quả thực tế và quy tắc OSB của broker; thường là failed nếu thao tác không đạt mục tiêu |
| EXPIRED/PURGED | Không còn terminal result để trả; xử lý như operation không còn hợp lệ theo policy và hợp đồng |

Khi operation chuyển sang terminal, kết quả phải trở nên bất biến. Không đổi một operation SUCCEEDED thành FAILED chỉ vì cleanup hoặc audit phụ chạy lỗi sau đó. Nếu cần xử lý bù, hãy tạo workflow/operation mới và liên kết nó với operation gốc.

## 5. Ghi kết quả cuối một cách nguyên tử

Worker có thể hoàn tất thay đổi backend nhưng gặp lỗi trước khi ghi kết quả vào state store. Ví dụ, database đã được mở rộng thành công nhưng broker mất kết nối database quản lý ngay trước khi cập nhật operation. Khi worker retry, broker phải xác minh trạng thái backend và tránh thực hiện một thay đổi thứ hai ngoài ý muốn.

Khi xác nhận operation hoàn tất, nên cập nhật trong một transaction:

1. Ghi trạng thái instance đã được xác nhận, ví dụ ACTIVE với plan/configuration mới.
2. Ghi operation thành SUCCEEDED hoặc FAILED.
3. Ghi completed_at, result_code và mô tả an toàn.
4. Tính expires_at = completed_at + retention_period.
5. Ghi audit/outbox event nếu cần.

Nếu instance state và operation state nằm cùng database, transaction có thể bảo đảm chúng nhất quán. Nếu chúng nằm ở các hệ thống khác nhau, cần outbox/inbox hoặc một quy trình reconcile có thể chạy lại. Không để instance thể hiện plan mới trong khi operation vẫn IN_PROGRESS vô thời hạn nếu backend đã hoàn tất.

Ví dụ pseudocode:

~~~java
@Transactional
public void completeSuccessfully(
        String operationId,
        InstanceSnapshot snapshot,
        Instant completedAt,
        Duration retention) {

    OperationRecord operation =
            operationRepository.findByIdForUpdate(operationId)
                    .orElseThrow(OperationNotFoundException::new);

    if (operation.isTerminal()) {
        return; // completion retry không ghi đè kết quả terminal
    }

    instanceRepository.save(snapshot);
    operationRepository.markSucceeded(
            operationId,
            completedAt,
            completedAt.plus(retention),
            "COMPLETED",
            "Thao tác đã hoàn tất");
}
~~~

Đây là pseudocode; các repository method và kiểu InstanceSnapshot thuộc ứng dụng. Cần kiểm tra version/lease để worker cũ không ghi kết quả sau worker mới. Nếu backend đã thay đổi nhưng transaction ghi state thất bại, lần chạy tiếp theo phải reconcile với backend trước khi quyết định terminal result.

## 6. Chọn thời hạn lưu kết quả

Retention period nên dựa trên thời gian nền tảng có thể tiếp tục polling, retry HTTP và khôi phục sau sự cố. Không có một con số phù hợp cho mọi broker. Cần chọn chính sách theo loại operation, đặc tính nền tảng và yêu cầu audit.

Ví dụ bảng cấu hình:

| Loại dữ liệu | Retention minh họa | Lý do |
|---|---:|---|
| Operation đang chạy | Không áp dụng TTL terminal | Phải giữ đến khi hoàn tất hoặc được xử lý recovery |
| Kết quả provision terminal | 24–72 giờ | Nền tảng có thời gian polling và retry sau gián đoạn |
| Kết quả update terminal | 24–72 giờ | Có thể cần polling lại sau timeout hoặc restart |
| Kết quả deprovision terminal | 24–72 giờ hoặc theo policy dài hơn | Nền tảng có thể cần xác nhận việc thu hồi |
| Tombstone instance | Theo chính sách vòng đời và chống request lặp | Giúp nhận diện instance đã bị xóa |
| Audit event tối thiểu | Theo chính sách kiểm toán riêng | Lưu dấu vết mà không giữ toàn bộ payload vận hành |

Các khoảng thời gian trên chỉ là ví dụ cấu hình, không phải giá trị bắt buộc của OSB. Broker cần đặt retention dài hơn khoảng polling/retry tối đa mà nền tảng có thể thực hiện, cộng thêm biên an toàn cho gián đoạn mạng, lịch bảo trì và khôi phục control plane.

Retention nên được cấu hình tập trung, có thể khác nhau theo operation type. Khi thay đổi chính sách, cần quyết định policy mới áp dụng cho operation được tạo từ thời điểm nào. Không nên thay đổi expires_at của mọi operation terminal một cách âm thầm nếu điều đó có thể xóa sớm kết quả mà nền tảng đang chờ.

## 7. Operation retention khác với worker lease và operation timeout

Ba khái niệm này giải quyết ba vấn đề khác nhau:

| Cơ chế | Mục đích | Áp dụng khi nào |
|---|---|---|
| Operation timeout/deadline | Giới hạn thời gian xử lý nghiệp vụ | Operation chạy lâu hơn SLA hoặc deadline đã định |
| Worker lease | Xác định worker nào đang giữ quyền xử lý operation | Worker nhận việc và cần gia hạn quyền xử lý |
| Terminal result retention | Giữ kết quả sau khi operation hoàn tất | Operation đã SUCCEEDED/FAILED/CANCELLED |

Nếu worker chết, lease có thể hết hạn để worker khác nhận lại operation. Điều đó không làm operation trở thành expired và không xóa kết quả cuối. Ngược lại, một operation đã thành công có thể vẫn được giữ nhiều giờ dù không còn worker nào xử lý nó.

Không dùng expires_at của terminal result để điều khiển lease. Cũng không dùng lease expiry làm bằng chứng backend chưa thực hiện tác vụ. Worker mới phải đọc checkpoint và reconcile trước khi gửi lại lệnh có tác dụng phụ.

## 8. Xử lý operation key không còn hợp lệ

Một operation key có thể không còn dùng được vì nhiều nguyên nhân:

| Trường hợp | Ý nghĩa | Cách xử lý |
|---|---|---|
| Operation ID chưa từng tồn tại | Request có key sai hoặc không thuộc broker | Không đoán operation khác; trả lỗi theo hợp đồng |
| Operation đã hết retention và bị purge | Kết quả cuối không còn được lưu | Xử lý như operation hết hạn/không còn hợp lệ theo response mapping đã công bố |
| Operation thuộc instance khác | ID bị dùng sai ngữ cảnh hoặc caller gửi nhầm | Từ chối; không trả thông tin operation khác |
| Service/plan ID không khớp | Request polling không tương ứng với operation đã lưu | Xử lý theo validation của OSB; không trả kết quả của operation khác |
| Operation key cũ sau khi instance có operation mới | Polling tham chiếu thao tác trước | Trả kết quả của operation cũ nếu còn retention; không tự chuyển sang operation mới |
| Operation đang chạy nhưng worker lease hết hạn | Có thể cần worker khác tiếp tục | Giữ operation, thực hiện recovery/reconcile; không coi là terminal |
| Instance đã deprovision | Resource lifecycle đã kết thúc | Ánh xạ theo semantics last operation và instance của OSB |

Đặc biệt, không được lấy operation mới nhất của instance rồi trả cho mọi request last operation bất kể operation key được gửi là gì. Nếu nền tảng đang polling operation A nhưng broker trả kết quả của operation B, nền tảng có thể kết luận sai về provision/update/deprovision.

Nếu operation key không được gửi trong request, broker cần áp dụng đúng quy tắc last operation của phiên bản OSB/framework đang hỗ trợ, chẳng hạn xác định operation liên quan theo instance và ngữ cảnh service/plan. Nếu operation key được gửi, phải xác minh nó thuộc đúng instance và loại thao tác.

## 9. Phân biệt unknown, expired, failed và in progress

Các trạng thái này không thể thay thế cho nhau:

- **Unknown:** broker không có record hoặc tombstone chứng minh operation từng tồn tại.
- **Expired:** broker biết operation từng tồn tại nhưng terminal result đã hết retention.
- **Failed:** operation đã chạy và kết thúc với kết quả thất bại; đây là một terminal result hợp lệ cần được giữ trong retention.
- **In progress:** operation vẫn đang được xử lý hoặc đang chờ worker/recovery.

Không trả failed chỉ vì record không tìm thấy; như vậy sẽ biến lỗi tra cứu thành kết quả nghiệp vụ. Không trả in progress vô thời hạn cho operation đã bị purge; nền tảng sẽ polling mãi. Không trả succeeded chỉ vì instance hiện tại có vẻ đã tồn tại; phải liên kết kết quả với đúng operation.

Để phân biệt unknown và expired, broker có thể giữ một tombstone operation tối thiểu lâu hơn payload kết quả:

~~~java
public record OperationTombstone(
        String operationId,
        String instanceId,
        String operationType,
        Instant completedAt,
        Instant resultPurgedAt) {
}
~~~

Tombstone không cần chứa response description đầy đủ hoặc parameters. Nó chỉ giúp broker biết operation từng tồn tại và kết quả đã bị dọn. Nếu cả record và tombstone đều hết hạn, request cũ trở thành unknown theo khả năng thông tin còn lại.

## 10. Response mapping cho last operation

Endpoint last operation cần trả đúng trạng thái OSB và không để lộ lỗi nội bộ:

| Kết quả nội bộ | Nội dung response phù hợp |
|---|---|
| PENDING/IN_PROGRESS | state: in progress; mô tả tiến độ ngắn nếu có ích |
| SUCCEEDED | state: succeeded; mô tả kết quả đã xác nhận |
| FAILED | state: failed; mô tả lỗi đã chuẩn hóa, đủ để hiểu thao tác không thành công |
| Operation unknown/expired | Trả lỗi theo response code và semantics của phiên bản OSB/framework; không giả làm một trạng thái terminal |
| Caller không được phép truy vấn | Từ chối theo authorization policy; không tiết lộ operation của tenant khác |
| State store tạm thời lỗi | Trả lỗi phụ thuộc phù hợp; không suy đoán operation đã thành công hay thất bại |

Không đưa stack trace, SQL, tên secret, token hoặc raw exception message vào description. Có thể lưu resultCode nội bộ để support tra cứu, còn response chỉ dùng thông báo đã được chuẩn hóa.

Mã HTTP cho operation không tồn tại, hết hạn hoặc instance đã mất cần được ánh xạ theo đúng phiên bản OSB và contract mà broker triển khai. Không tự coi mọi trường hợp là 404 hoặc 410; hai mã có ngữ nghĩa khác nhau và có thể làm nền tảng xử lý vòng đời khác nhau. Contract test phải khóa hành vi cụ thể của broker.

## 11. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp extension point để ứng dụng triển khai truy vấn last operation trong luồng service instance. Tùy phiên bản, handler nhận request model có các định danh instance/service/plan và operation key, sau đó trả model trạng thái operation của framework.

Nên giữ phân lớp:

1. **OSB handler:** đọc request model và chuyển thành LastOperationQuery.
2. **Application service:** xác minh caller, instance, operation key và trạng thái.
3. **Operation repository:** đọc record terminal hoặc record đang chạy.
4. **Retention policy:** xác định record còn trong thời gian công bố hay đã hết hạn.
5. **Response mapper:** ánh xạ trạng thái nội bộ sang in progress, succeeded hoặc failed.

Ví dụ pseudocode:

~~~java
public Mono<LastOperationResult> getLastOperation(
        LastOperationQuery query) {

    return accessPolicy.verify(query.caller(), query.instanceId())
            .then(operationRepository.findForPolling(
                    query.instanceId(),
                    query.operationId(),
                    query.serviceId(),
                    query.planId()))
            .switchIfEmpty(Mono.error(new OperationNotFoundException()))
            .flatMap(operation -> {
                if (operation.isResultExpired(clock.instant())) {
                    return Mono.error(new OperationExpiredException());
                }
                return Mono.just(responseMapper.toOsbResult(operation));
            });
}
~~~

Đây là pseudocode minh họa; LastOperationQuery, LastOperationResult và repository thuộc ứng dụng. Chữ ký method thực tế phải theo phiên bản Spring Cloud Open Service Broker đang dùng. Không tự tạo HTTP response trong repository hoặc infrastructure adapter.

Nếu repository truy vấn blocking, không chạy trực tiếp trên event loop của ứng dụng reactive. Có thể dùng reactive data access hoặc scheduler phù hợp. Thời gian đọc state store cần ngắn; endpoint polling không nên gọi lại toàn bộ workflow provision chỉ để xác định kết quả.

## 12. Job dọn dẹp operation hết hạn

Cleanup job có thể chạy định kỳ để tìm operation terminal đã quá expires_at. Job phải an toàn khi chạy nhiều replica và có thể retry:

1. Chọn batch operation có trạng thái terminal và expires_at <= now.
2. Bỏ qua record đang có lease hoặc không ở trạng thái terminal.
3. Tạo tombstone tối thiểu nếu policy cần phân biệt expired với unknown.
4. Xóa payload/result fields không còn cần thiết hoặc chuyển sang kho archive phù hợp.
5. Cập nhật trạng thái purge và thời điểm purge.
6. Ghi metric số record đã dọn, lỗi và thời gian xử lý.

Không tải toàn bộ operation table vào bộ nhớ. Dùng index trên status và expires_at, xử lý theo batch và kiểm soát số lượng bản ghi mỗi lượt. Nếu nhiều worker cleanup cùng chạy, dùng row locking/skip locked, claim token hoặc optimistic version để tránh xóa lặp gây lỗi.

Ví dụ truy vấn tối giản:

~~~sql
DELETE FROM broker_operation
WHERE status IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
  AND expires_at <= :now;
~~~

Đây chỉ là ví dụ truy vấn tối giản. Hệ thống cần thêm bước tạo tombstone, kiểm tra quan hệ với instance, xử lý audit và concurrency trước khi xóa thật. Không áp dụng câu lệnh này cho operation đang PENDING hoặc IN_PROGRESS.

## 13. Giữ kết quả cuối nhưng giảm dữ liệu nhạy cảm

Terminal result nên đủ để trả polling và hỗ trợ vận hành, nhưng không cần giữ toàn bộ request/response. Một record tối thiểu có thể gồm:

- Operation ID, instance ID và operation type.
- Trạng thái cuối, mã kết quả và mô tả đã chuẩn hóa.
- Thời điểm tạo, hoàn tất và hết hạn.
- Service/plan ID cần thiết để xác minh ngữ cảnh.
- Correlation ID hoặc audit reference nếu cần điều tra.

Không lưu trong terminal result:

- Password, access token, private key hoặc credentials binding.
- Toàn bộ payload parameters nếu không cần cho audit.
- Raw stack trace hoặc nội dung exception có thể chứa dữ liệu nhạy cảm.
- Thông tin của tenant khác hoặc chi tiết backend không cần thiết cho caller.

Quyền đọc operation record cần được giới hạn. Endpoint last operation phải xác thực caller và xác minh phạm vi instance; operation ID khó đoán không thay thế authorization. Log và metric nên dùng mã operation/correlation đã chuẩn hóa, tránh ghi nguyên response có dữ liệu khách hàng.

## 14. Kiểm thử retention và operation không còn hợp lệ

Kiểm thử cần xác minh cả state machine, polling và cleanup:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Operation đang IN_PROGRESS vượt thời gian retention cấu hình | Không bị cleanup chỉ vì tuổi record |
| Worker hoàn tất thành công | Lưu terminal result và tính expires_at từ completed_at |
| Nền tảng polling sau khi operation thành công | Vẫn nhận succeeded trong retention window |
| Operation thất bại | Giữ failed cùng mô tả an toàn trong retention window |
| Operation key unknown | Không trả kết quả của operation khác |
| Operation key expired | Trả lỗi theo contract đã định nghĩa; không giả làm in progress hoặc succeeded |
| Operation key thuộc instance khác | Từ chối và không tiết lộ dữ liệu |
| Instance có operation mới | Polling operation cũ vẫn tham chiếu đúng operation cũ nếu còn retention |
| Worker lease hết hạn | Operation được recovery, không bị đánh dấu expired |
| Hai cleanup worker cùng chạy | Chỉ một worker purge mỗi record; không xóa operation active |
| State store tạm thời unavailable | Không suy đoán kết quả cuối |
| Terminal result có secret trong exception | Secret không xuất hiện trong description, log hoặc audit summary |

Nên dùng clock có thể điều khiển trong unit test để kiểm tra completed_at, expires_at và ranh giới thời gian. Integration test cần kiểm tra transaction giữa instance state và operation state, job cleanup theo batch, tombstone và request polling ngay trước/sau khi hết retention.

## 15. Những sai lầm thường gặp

- Xóa operation ngay khi worker ghi thành công hoặc thất bại.
- Tính retention từ lúc tạo operation khiến operation chạy lâu bị xóa trước khi hoàn tất.
- Dùng cùng một TTL cho operation processing, worker lease và terminal result.
- Trả operation mới nhất thay cho operation key mà nền tảng đang polling.
- Coi operation unknown là failed hoặc succeeded.
- Trả in progress mãi khi terminal result đã bị purge.
- Xóa terminal result mà không có policy hoặc tombstone để xử lý request cũ.
- Giữ raw exception, credentials hoặc toàn bộ request parameters trong record kết quả.
- Cleanup job xóa record đang chạy hoặc operation đang được worker lease.
- Không kiểm tra caller/tenant khi truy vấn last operation.

## Kết luận

Kết quả cuối của asynchronous operation phải được lưu đủ lâu để nền tảng có thể polling và nhận được trạng thái succeeded hoặc failed sau khi worker hoàn tất. Retention bắt đầu từ completed_at, chỉ áp dụng cho terminal result; operation đang chạy được quản lý bằng deadline, lease và recovery riêng. Khi operation key unknown, expired, stale hoặc không khớp instance, broker phải phân biệt đúng nguyên nhân và ánh xạ lỗi theo hợp đồng OSB, tuyệt đối không trả kết quả của một operation khác. Kết hợp lưu terminal result nguyên tử, retention policy có cấu hình, tombstone tối thiểu và cleanup job idempotent giúp service broker Spring Cloud duy trì polling đáng tin cậy mà vẫn kiểm soát được dung lượng state store và dữ liệu nhạy cảm.
