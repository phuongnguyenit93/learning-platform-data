# Cài đặt getLastOperation() cho service instance

Trong Open Service Broker API (OSB API), một thao tác provision, update hoặc deprovision có thể cần nhiều thời gian hơn thời gian xử lý của một HTTP request thông thường. Khi broker không thể hoàn tất ngay, platform có thể chấp nhận xử lý bất đồng bộ, nhận phản hồi **202 Accepted** và tiếp tục hỏi trạng thái operation qua endpoint **GET /v2/service_instances/{instance_id}/last_operation**.

Trong Spring Cloud Open Service Broker (SCOSB), broker triển khai khả năng tra cứu này qua phương thức **getLastOperation()** của **ServiceInstanceService**. Phương thức đọc trạng thái operation đã được ghi nhận và trả về kết quả theo mô hình của framework. Nó không thực hiện lại thao tác provision hoặc gọi provider để bắt đầu một lần update mới.

Bài học thuộc module **SPRING_CLOUD_SERVICE_BROKER**, tập trung vào hợp đồng endpoint last_operation, cách lưu operation bền vững, ánh xạ trạng thái nội bộ sang trạng thái OSB API, triển khai getLastOperation() bằng Spring, xử lý polling và các tình huống lỗi, retry, restart hoặc request đồng thời.

## 1. Vì sao cần getLastOperation()?

Một yêu cầu tạo database có thể hoàn tất trong vài giây, nhưng cũng có thể cần vài phút để tạo máy chủ, cấu hình mạng, khởi tạo database và cấp quyền. Nếu broker giữ HTTP connection mở trong toàn bộ thời gian đó, request dễ gặp timeout ở load balancer, platform hoặc client.

OSB API giải quyết vấn đề bằng mô hình bất đồng bộ:

1. Platform gửi request provision, update hoặc deprovision.
2. Broker xác nhận request hợp lệ, ghi nhận operation và bắt đầu xử lý.
3. Nếu chưa thể hoàn tất đồng bộ, broker trả **202 Accepted**. Response có thể chứa mã operation để nhận diện công việc.
4. Platform gọi endpoint **last_operation** để hỏi trạng thái.
5. Broker đọc trạng thái operation đã lưu và trả về **in progress**, **succeeded** hoặc **failed**.
6. Platform tiếp tục polling cho đến khi operation đạt trạng thái kết thúc.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Service broker
    participant DB as Operation store
    participant W as Background worker
    participant S as Service provider

    P->>B: PUT /v2/service_instances/{instance_id}
    B->>DB: Persist operation = IN_PROGRESS
    B-->>P: 202 Accepted + operation ID
    B->>W: Enqueue operation
    W->>S: Create database
    P->>B: GET .../last_operation?operation=op-123
    B->>DB: Read operation state
    DB-->>B: IN_PROGRESS
    B-->>P: 200 OK - in progress
    S-->>W: Provider operation completed
    W->>DB: Persist SUCCEEDED
    P->>B: GET .../last_operation?operation=op-123
    B->>DB: Read operation state
    DB-->>B: SUCCEEDED
    B-->>P: 200 OK - succeeded
~~~

Endpoint last_operation cho phép platform biết khi nào có thể tiếp tục bước phụ thuộc, chẳng hạn bind ứng dụng sau khi database đã sẵn sàng. Nếu operation thất bại, platform có thể hiển thị lỗi hoặc yêu cầu người vận hành xử lý.

**getLastOperation() là thao tác đọc trạng thái.** Nó không được tạo lại tài nguyên, không enqueue lại công việc và không làm thay đổi trạng thái operation chỉ vì platform gọi polling nhiều lần.

## 2. Endpoint last_operation trong OSB API

Endpoint dành cho service instance:

~~~http
GET /v2/service_instances/{instance_id}/last_operation
~~~

Platform có thể truyền thêm query parameter **operation**:

~~~http
GET /v2/service_instances/instance-7f31/last_operation?operation=provision-op-123
~~~

| Thành phần | Ý nghĩa |
|---|---|
| **instance_id** | ID của service instance cần tra cứu trạng thái |
| **operation** | Mã operation do broker cung cấp hoặc sử dụng để nhận diện thao tác đang theo dõi |
| **GET** | Đọc trạng thái, không tạo side effect |
| Response 200 OK | Trả trạng thái operation theo hợp đồng OSB API |

**operation** là query parameter tùy chọn. Khi platform gửi mã operation, broker cần trả trạng thái đúng operation đó. Khi không có mã operation, broker trả trạng thái operation mới nhất phù hợp với service instance theo quy tắc và dữ liệu mà broker quản lý.

Mã operation nên được xem là định danh opaque. Platform không cần hiểu mã đó chứa thông tin gì. Broker có thể dùng UUID, mã nội bộ hoặc một định danh khác miễn là ổn định, không nhầm lẫn và có thể tra cứu trong suốt vòng đời operation.

Không dùng riêng **instance_id** để lưu trạng thái nếu một instance có thể thực hiện nhiều operation theo thời gian. Cần có định danh operation riêng để phân biệt lần provision, update hoặc deprovision đang được theo dõi.

### Phân biệt endpoint service instance và service binding

OSB API có endpoint last_operation riêng cho service binding:

~~~http
GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}/last_operation
~~~

Endpoint này theo dõi thao tác bất đồng bộ của binding hoặc unbinding. Bài học này tập trung vào **service instance**, tức các operation provision, update và deprovision. Không dùng endpoint instance để thay thế endpoint binding.

## 3. Các trạng thái operation chuẩn

OSB API định nghĩa ba giá trị trạng thái mà broker trả về trong response last_operation:

| Trạng thái | Ý nghĩa | Platform nên làm gì |
|---|---|---|
| **in progress** | Operation đang được thực hiện hoặc chưa có kết quả cuối cùng | Tiếp tục polling |
| **succeeded** | Operation đã hoàn thành thành công | Cho phép bước tiếp theo của vòng đời |
| **failed** | Operation đã kết thúc với lỗi | Dừng polling thông thường và xử lý lỗi |

Response JSON ví dụ:

~~~json
{
  "state": "in progress",
  "description": "Creating PostgreSQL database"
}
~~~

Khi hoàn thành:

~~~json
{
  "state": "succeeded",
  "description": "Database is ready"
}
~~~

Khi thất bại:

~~~json
{
  "state": "failed",
  "description": "Provider could not allocate the requested storage"
}
~~~

Trường **state** là thông tin cốt lõi để platform quyết định có tiếp tục chờ hay không. **description** có thể cung cấp thêm thông tin dễ hiểu về tiến độ hoặc kết quả; không nên đưa stack trace, password, token hoặc chi tiết nội bộ của provider vào trường này.

Broker có thể sử dụng nhiều trạng thái nội bộ hơn, chẳng hạn **QUEUED**, **VALIDATING**, **PROVISIONING**, **WAITING_FOR_PROVIDER**, **PERSISTING**, **SUCCEEDED** hoặc **FAILED**. Khi trả response OSB API, các trạng thái nội bộ chưa kết thúc được ánh xạ thành **in progress**.

Ví dụ bảng ánh xạ:

| Trạng thái nội bộ | Trạng thái OSB API |
|---|---|
| QUEUED | in progress |
| VALIDATING | in progress |
| PROVISIONING | in progress |
| WAITING_FOR_PROVIDER | in progress |
| UPDATING | in progress |
| DEPROVISIONING | in progress |
| SUCCEEDED | succeeded |
| FAILED | failed |

Không trả một trạng thái nội bộ tùy ý như **PROVISIONING** vào field **state** nếu hợp đồng OSB API chỉ chấp nhận ba giá trị chuẩn.

## 4. Operation cần được lưu bền vững

Không nên chỉ lưu trạng thái operation trong biến Java hoặc collection trong bộ nhớ. Broker có thể restart, chạy nhiều replica hoặc được triển khai lại trong khi platform vẫn tiếp tục polling.

Một operation record có thể chứa:

| Trường | Mục đích |
|---|---|
| operation_id | ID ổn định mà platform có thể dùng khi polling |
| instance_id | Service instance sở hữu operation |
| operation_type | PROVISION, UPDATE hoặc DEPROVISION |
| state | Trạng thái nội bộ của operation |
| description | Mô tả công khai, không chứa bí mật |
| service_id | Offering liên quan |
| source_plan_id | Plan hiện tại trước update nếu cần |
| target_plan_id | Plan đích nếu operation có thay đổi plan |
| provider_operation_id | ID thao tác do provider trả về, nếu có |
| created_at | Thời điểm ghi nhận operation |
| updated_at | Lần cập nhật trạng thái gần nhất |
| completed_at | Thời điểm kết thúc |
| version | Phiên bản bản ghi để kiểm soát cập nhật đồng thời |

Ví dụ bảng dữ liệu:

~~~sql
CREATE TABLE service_instance_operation (
    operation_id VARCHAR(100) PRIMARY KEY,
    instance_id VARCHAR(100) NOT NULL,
    operation_type VARCHAR(30) NOT NULL,
    state VARCHAR(30) NOT NULL,
    description VARCHAR(500),
    service_id VARCHAR(100) NOT NULL,
    source_plan_id VARCHAR(100),
    target_plan_id VARCHAR(100),
    provider_operation_id VARCHAR(200),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_operation_instance_created
    ON service_instance_operation(instance_id, created_at);
~~~

Schema trên là ví dụ tối giản. Ứng dụng thực tế có thể bổ sung tenant ID, correlation ID, mã lỗi đã chuẩn hóa, thời hạn lưu operation và thông tin retry. Nếu operation cần lưu tham số có chứa secret để worker tiếp tục thực hiện, phải dùng kho lưu trữ được bảo vệ và mã hóa phù hợp; không đưa secret vào description hoặc log.

### Vì sao phải có operation_id?

Một service instance có thể có nhiều thao tác trong suốt vòng đời:

- provision-op-123: tạo database.
- update-op-456: mở rộng dung lượng.
- deprovision-op-789: xóa database.

Nếu chỉ lưu một field last_operation_state trên instance, một operation mới có thể ghi đè kết quả của operation cũ trong khi platform vẫn đang polling mã cũ. Bảng operation riêng giúp broker tra cứu chính xác và giữ lịch sử cần thiết.

Có thể lưu thêm current_operation_id trên bản ghi service instance để xác định operation đang chạy. Khi operation kết thúc, cập nhật con trỏ này theo transaction hoặc optimistic locking để không vô tình thay thế operation mới hơn.

## 5. Cài đặt getLastOperation() trong Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp interface **ServiceInstanceService** để xử lý vòng đời service instance. Trong interface này, phương thức **getLastOperation()** nhận request model của framework và trả về publisher chứa response trạng thái.

Về mặt cấu trúc, implementation có dạng:

~~~java
Mono<GetLastServiceOperationResponse> getLastOperation(
        GetLastServiceOperationRequest request);
~~~

Hai model cần chú ý:

- **GetLastServiceOperationRequest**: chứa thông tin service instance và mã operation platform muốn tra cứu.
- **GetLastServiceOperationResponse**: chứa trạng thái operation và mô tả trả về platform.

Các model nằm trong package instance của Spring Cloud Open Service Broker. Tên package, accessor và builder cần được đối chiếu với phiên bản SCOSB đang dùng.

### Ví dụ implementation

Giả sử broker đã có reactive repository để đọc operation:

~~~java
import org.springframework.stereotype.Service;

import org.springframework.cloud.servicebroker.model.instance.GetLastServiceOperationRequest;
import org.springframework.cloud.servicebroker.model.instance.GetLastServiceOperationResponse;
import org.springframework.cloud.servicebroker.model.instance.OperationState;
import reactor.core.publisher.Mono;

@Service
public class LastOperationLookup {

    private final OperationRepository operationRepository;

    public LastOperationLookup(
            OperationRepository operationRepository) {
        this.operationRepository = operationRepository;
    }

    public Mono<GetLastServiceOperationResponse> getLastOperation(
            GetLastServiceOperationRequest request) {

        String instanceId = request.getServiceInstanceId();
        String operationId = request.getOperation();

        Mono<OperationRecord> operation;

        if (operationId != null && !operationId.isBlank()) {
            operation = operationRepository
                    .findByInstanceIdAndOperationId(instanceId, operationId);
        } else {
            operation = operationRepository
                    .findLatestByInstanceId(instanceId);
        }

        return operation
                .switchIfEmpty(Mono.error(
                        new OperationNotFoundException(instanceId, operationId)))
                .map(record -> GetLastServiceOperationResponse.builder()
                        .operationState(toOsbState(record.state()))
                        .description(record.description())
                        .build());
    }

    private OperationState toOsbState(OperationStatus state) {
        return switch (state) {
            case QUEUED, VALIDATING, PROVISIONING,
                 UPDATING, DEPROVISIONING, WAITING_FOR_PROVIDER ->
                    OperationState.IN_PROGRESS;
            case SUCCEEDED -> OperationState.SUCCEEDED;
            case FAILED -> OperationState.FAILED;
        };
    }
}
~~~

Đây là component minh họa phần tra cứu trạng thái. Trong implementation đầy đủ, phương thức **getLastOperation()** của class triển khai **ServiceInstanceService** có thể ủy quyền cho component này; các phương thức lifecycle còn lại của interface vẫn cần được triển khai theo phiên bản SCOSB đang dùng. Kiểu enum, constructor, accessor và phương thức builder cụ thể có thể thay đổi theo phiên bản SCOSB; cần đối chiếu Javadoc của dependency trong dự án trước khi dùng nguyên mã.

Điểm quan trọng trong implementation:

1. Lấy **instanceId** từ request của framework.
2. Nếu có **operationId**, tra cứu đúng operation thuộc instance đó.
3. Nếu không có operation ID, lấy operation mới nhất theo quy tắc của broker.
4. Chuyển trạng thái nội bộ sang một trong ba trạng thái OSB API.
5. Trả response mà không gọi provider hoặc tạo operation mới.

Repository nên trả về **Mono<OperationRecord>** để phù hợp với reactive service. Nếu dùng JDBC/JPA blocking, cần bọc thao tác đọc trong **Mono.fromCallable()** và chạy trên **Schedulers.boundedElastic()**; không thực thi blocking query trực tiếp trên event loop của WebFlux.

## 6. Thiết kế truy vấn operation đúng instance

Một lỗi nghiêm trọng là tra cứu operation chỉ theo operation ID mà không kiểm tra instance ID. Điều đó có thể khiến caller truy vấn operation thuộc tài nguyên khác nếu đoán hoặc biết được mã operation.

Repository nên hỗ trợ truy vấn kết hợp:

~~~java
public interface OperationRepository {

    Mono<OperationRecord> findByInstanceIdAndOperationId(
            String instanceId,
            String operationId);

    Mono<OperationRecord> findLatestByInstanceId(
            String instanceId);
}
~~~

Khi platform gửi cả instance ID và operation, điều kiện truy vấn phải khớp cả hai. Khi không có operation ID, repository có thể lấy operation mới nhất của instance theo timestamp hoặc theo thứ tự version đã được lưu.

Cần xác định rõ quy tắc operation nào được xem là mới nhất. Ví dụ, một instance vừa có operation update thành công nhưng một polling request cũ vẫn đang hỏi operation provision. Nếu request có mã provision, broker phải trả kết quả của provision; không được trả trạng thái update chỉ vì update là operation mới hơn.

Trước khi trả kết quả, broker cũng phải xác minh caller/platform được phép truy cập instance theo cơ chế xác thực và phân quyền của môi trường triển khai. Operation ID khó đoán không thay thế authorization.

## 7. Lưu trạng thái và xử lý worker bất đồng bộ

Một thiết kế thường dùng là ghi operation trước rồi để worker thực hiện provider call:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu provision/update/delete"] --> B["Validate và kiểm tra quyền"]
    B --> C["Tạo operation ID"]
    C --> D["Transaction: lưu operation + outbox event"]
    D --> E["Trả 202 Accepted"]
    D --> F["Outbox publisher"]
    F --> G["Background worker"]
    G --> H["Gọi provider"]
    H --> I{"Kết quả provider"}
    I -->|"Đang chạy"| J["Lưu IN_PROGRESS"]
    I -->|"Thành công"| K["Lưu SUCCEEDED"]
    I -->|"Thất bại"| L["Lưu FAILED"]
    J --> G
    M["Platform polling"] --> N["getLastOperation()"]
    N --> O["Đọc operation store"]
    O --> P["Trả state theo OSB API"]
~~~

Nếu broker ghi operation vào database nhưng enqueue message thất bại, công việc có thể bị mất. Ngược lại, nếu message được gửi đi nhưng transaction lưu operation rollback, worker có thể chạy một operation mà broker không thể tra cứu. Mẫu **transactional outbox** giúp giảm rủi ro này bằng cách ghi operation và outbox event trong cùng transaction; một publisher riêng đọc outbox rồi gửi công việc đến queue.

Worker cần cập nhật trạng thái theo thứ tự hợp lý:

1. Đọc operation và xác nhận operation vẫn được phép chạy.
2. Đánh dấu trạng thái đang thực hiện hoặc giữ trạng thái IN_PROGRESS.
3. Gọi provider với idempotency key hoặc provider operation ID nếu hỗ trợ.
4. Nếu provider trả kết quả đang xử lý, lưu provider operation ID và tiếp tục theo dõi.
5. Nếu provider hoàn tất, cập nhật trạng thái cuối cùng cùng thông tin tài nguyên.
6. Nếu có lỗi, phân loại lỗi và lưu trạng thái FAILED hoặc trạng thái cần reconciliation theo thiết kế.

**getLastOperation()** chỉ đọc dữ liệu đã được worker ghi nhận. Không nên để endpoint polling tự gọi provider mỗi lần platform hỏi, vì số request polling có thể lớn và gây áp lực lên provider.

## 8. Vòng đời operation của provision, update và deprovision

Cùng endpoint last_operation có thể phục vụ nhiều loại operation. Bản ghi cần có operation type để broker biết trạng thái đó thuộc nghiệp vụ nào.

| Loại operation | Bắt đầu khi | Điều kiện thành công |
|---|---|---|
| PROVISION | Platform yêu cầu tạo service instance | Provider đã tạo tài nguyên và broker đã lưu provider resource ID cùng cấu hình cần thiết |
| UPDATE | Platform yêu cầu đổi cấu hình hoặc plan | Provider xác nhận thay đổi và broker đã lưu plan/cấu hình mới |
| DEPROVISION | Platform yêu cầu xóa service instance | Tài nguyên được giải phóng hoặc trạng thái xóa được xác nhận theo hợp đồng provider |

Một operation chỉ được đánh dấu **SUCCEEDED** khi các bước cần thiết của nghiệp vụ đã hoàn tất. Ví dụ, provider đã tạo database nhưng broker chưa lưu được resource ID thì broker chưa nên báo thành công. Nếu báo thành công quá sớm, platform có thể gọi bind trong khi broker không thể tìm lại tài nguyên.

Tương tự, deprovision chỉ thành công sau khi broker xác định tài nguyên đã được giải phóng theo chính sách. Nếu provider báo đang xóa hoặc còn tài nguyên phụ thuộc, operation cần tiếp tục ở trạng thái IN_PROGRESS hoặc đi theo quy trình xử lý lỗi đã thiết kế.

### Sơ đồ trạng thái operation

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> IN_PROGRESS: Worker claims operation
    IN_PROGRESS --> IN_PROGRESS: Provider still processing
    IN_PROGRESS --> SUCCEEDED: Provider and broker state committed
    IN_PROGRESS --> FAILED: Terminal error
    IN_PROGRESS --> RECONCILIATION_REQUIRED: Outcome is uncertain
    RECONCILIATION_REQUIRED --> IN_PROGRESS: Reconcile and resume
    RECONCILIATION_REQUIRED --> SUCCEEDED: Provider confirms completion
    RECONCILIATION_REQUIRED --> FAILED: Confirmed unrecoverable failure
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

**RECONCILIATION_REQUIRED** là trạng thái nội bộ minh họa. Khi trả về platform, broker phải ánh xạ trạng thái này thành **in progress** nếu chưa có kết quả cuối cùng và vẫn đang xử lý khôi phục. Không trả giá trị nội bộ này trực tiếp vào response OSB.

## 9. Xử lý polling khi operation đang chạy

Platform có thể gọi last_operation nhiều lần trong khi worker đang xử lý. Vì vậy, implementation cần có các đặc tính:

- Truy vấn nhanh, chỉ đọc operation store hoặc cache phù hợp.
- Không khóa lâu transaction đang cập nhật tài nguyên.
- Không gọi provider hoặc thực hiện side effect trong mỗi lần polling.
- Trả cùng trạng thái nếu operation chưa thay đổi.
- Khi operation chuyển sang terminal state, các lần polling tiếp theo trả lại kết quả cuối cùng của operation đó.
- Khi request có operation ID, luôn trả đúng operation được hỏi.

Một chu kỳ polling có thể diễn ra như sau:

~~~text
t0: Platform gửi provision
t1: Broker trả 202 Accepted, operation=op-123
t2: GET last_operation?operation=op-123 -> in progress
t3: GET last_operation?operation=op-123 -> in progress
t4: Provider hoàn tất, worker lưu SUCCEEDED
t5: GET last_operation?operation=op-123 -> succeeded
t6: Platform tiếp tục bind ứng dụng
~~~

Khoảng thời gian giữa các lần polling do platform điều phối theo chính sách của nó. Broker cần phục vụ polling ổn định và có thể áp dụng giới hạn tốc độ hợp lý ở gateway, nhưng không nên giả định mọi platform đều polling với cùng một chu kỳ.

Nếu polling tăng đột biến, có thể cache response trạng thái trong một khoảng thời gian rất ngắn hoặc dùng read replica phù hợp. Tuy nhiên, cache không được khiến platform tiếp tục nhìn thấy trạng thái **in progress** quá lâu sau khi operation đã hoàn tất. Với terminal state, dữ liệu cần nhất quán đủ để các request tiếp theo nhìn thấy kết quả cuối cùng.

## 10. Xử lý operation không tồn tại hoặc instance không tồn tại

Có một số trường hợp cần phân biệt:

- **instance_id** không tồn tại trong broker store.
- Instance tồn tại nhưng operation ID được yêu cầu không thuộc instance đó.
- Request không truyền operation ID và instance chưa có operation nào.
- Operation đã được lưu trữ lạnh hoặc hết thời hạn giữ lịch sử.
- Caller không có quyền truy cập instance.

Không nên trả một trạng thái mặc định **succeeded** khi không tìm thấy operation. Điều đó có thể khiến platform hiểu nhầm rằng provision hoặc update đã hoàn thành.

Broker cần ánh xạ trường hợp không tìm thấy và không đủ quyền sang lỗi phù hợp với OSB API, phiên bản API và cơ chế exception mapping của SCOSB. Không tự tạo operation rỗng hoặc trả mô tả giả. Đặc biệt, không tiết lộ rằng instance thuộc tenant khác chỉ vì caller gửi đúng ID.

Chính sách lưu lịch sử operation cần được xác định rõ. Có thể giữ operation gần nhất trong thời gian dài hơn các bản ghi cũ, hoặc lưu metadata tối thiểu để trả kết quả cho các request polling đến muộn. Không xóa operation đang chạy. Nếu xóa terminal operation, phải cân nhắc thời gian platform còn có thể polling và khả năng hỗ trợ điều tra.

## 11. Đồng bộ trạng thái và xử lý lỗi

Một operation có thể gặp lỗi ở nhiều thời điểm:

| Tình huống | Cách xử lý |
|---|---|
| Worker chưa nhận message | Giữ QUEUED/IN_PROGRESS, publisher tiếp tục xử lý outbox |
| Provider đang thực hiện | Giữ IN_PROGRESS, lưu provider operation ID |
| Provider timeout | Không kết luận thất bại ngay; kiểm tra trạng thái provider trước khi retry |
| Provider báo lỗi không thể khôi phục | Lưu FAILED và mô tả đã chuẩn hóa |
| Provider thành công nhưng broker chưa lưu kết quả | Reconcile dựa trên provider resource/operation ID |
| Broker restart | Đọc operation đang chạy từ database và phục hồi worker |
| Hai worker cùng nhận một operation | Dùng claim/lease hoặc optimistic locking để chỉ một worker sở hữu tại một thời điểm |
| Platform polling liên tục | Trả dữ liệu đọc nhanh, áp dụng rate limit phù hợp |
| Operation đã terminal | Giữ trạng thái cuối cùng ổn định |

Không nên chuyển operation từ FAILED về IN_PROGRESS chỉ vì platform tiếp tục polling. Retry nghiệp vụ là một quyết định của worker hoặc quy trình vận hành, không phải side effect của GET last_operation.

### Timeout không đồng nghĩa provider chưa thực hiện

Giả sử broker gửi lệnh tăng storage tới provider. Provider áp dụng thay đổi thành công nhưng response bị mất trên mạng. Broker thấy timeout và không biết chắc kết quả. Nếu worker gửi lại lệnh mà provider không hỗ trợ idempotency, tài nguyên có thể bị thay đổi lặp hoặc phát sinh thao tác ngoài dự kiến.

Cách xử lý an toàn:

1. Lưu provider operation ID hoặc idempotency key khi gửi request.
2. Khi timeout, truy vấn trạng thái provider bằng mã đã lưu.
3. Nếu provider đã hoàn tất, cập nhật operation broker thành SUCCEEDED.
4. Nếu provider vẫn đang chạy, tiếp tục theo dõi.
5. Nếu provider xác nhận chưa thực hiện, mới cân nhắc retry.
6. Nếu không thể xác định, giữ trạng thái nội bộ cần reconciliation và không báo thành công giả.

## 12. Idempotency và request lặp

Platform có thể gửi lại request provision/update/delete khi không nhận được response ban đầu. Broker phải đảm bảo retry không tạo operation hoặc tài nguyên trùng ngoài ý muốn.

Nên lưu các thông tin:

- instance ID.
- operation ID.
- operation type.
- service ID và plan ID.
- fingerprint của request đã chuẩn hóa.
- provider operation ID.
- trạng thái và kết quả.

Khi nhận retry, broker kiểm tra operation đang tồn tại. Nếu request có cùng nội dung và operation đang chạy, broker có thể trả lại phản hồi/operation hiện có theo hợp đồng. Nếu operation đã thành công, broker trả kết quả tương ứng thay vì thực hiện lại side effect.

**getLastOperation() không phải endpoint retry.** Platform gọi nó chỉ để đọc tiến độ. Nếu operation FAILED, việc tạo operation mới hoặc retry cần đi qua quy trình nghiệp vụ phù hợp, có kiểm tra trạng thái và quyền.

## 13. Ví dụ kiểm thử getLastOperation()

Nên kiểm thử lớp service với các tình huống operation đang chạy, thành công, thất bại, không tồn tại và truy vấn sai instance. Ví dụ sau minh họa bằng JUnit, Mockito và Reactor StepVerifier:

~~~java
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.cloud.servicebroker.model.instance.GetLastServiceOperationRequest;
import org.springframework.cloud.servicebroker.model.instance.OperationState;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class BrokerServiceInstanceServiceTest {

    private final OperationRepository repository =
            Mockito.mock(OperationRepository.class);

    private final LastOperationLookup service =
            new LastOperationLookup(repository);

    @Test
    void returnsInProgressForRunningOperation() {
        var request = GetLastServiceOperationRequest.builder()
                .serviceInstanceId("instance-7f31")
                .operation("op-123")
                .build();

        when(repository.findByInstanceIdAndOperationId(
                "instance-7f31", "op-123"))
                .thenReturn(Mono.just(OperationRecord.inProgress(
                        "instance-7f31", "op-123")));

        StepVerifier.create(service.getLastOperation(request))
                .expectNextMatches(response ->
                        response.getOperationState()
                                == OperationState.IN_PROGRESS)
                .verifyComplete();
    }

    @Test
    void returnsSucceededForCompletedOperation() {
        var request = GetLastServiceOperationRequest.builder()
                .serviceInstanceId("instance-7f31")
                .operation("op-123")
                .build();

        when(repository.findByInstanceIdAndOperationId(
                "instance-7f31", "op-123"))
                .thenReturn(Mono.just(OperationRecord.succeeded(
                        "instance-7f31", "op-123")));

        StepVerifier.create(service.getLastOperation(request))
                .expectNextMatches(response ->
                        response.getOperationState()
                                == OperationState.SUCCEEDED)
                .verifyComplete();
    }
}
~~~

Đây là ví dụ minh họa, trong đó **OperationRecord.inProgress()** và **OperationRecord.succeeded()** là factory method của mô hình nội bộ giả định. Request builder và accessor của response cần kiểm tra theo phiên bản SCOSB mà dự án sử dụng.

Bộ test nên mở rộng để xác minh:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Operation đang QUEUED | Response state là in progress |
| Operation đang chạy | Response state là in progress |
| Operation thành công | Response state là succeeded |
| Operation thất bại | Response state là failed |
| Có operation ID | Repository truy vấn đúng instance và operation |
| Không có operation ID | Repository lấy operation mới nhất theo quy tắc |
| Operation thuộc instance khác | Không trả dữ liệu operation đó |
| Instance không tồn tại | Trả lỗi theo mapping OSB API |
| Polling nhiều lần | Không tạo side effect hoặc enqueue worker |
| Worker cập nhật trạng thái đồng thời với polling | Response phản ánh một snapshot nhất quán |
| Provider timeout | Operation không bị đánh dấu FAILED khi kết quả chưa rõ |
| Broker restart | Operation đang chạy vẫn có thể tiếp tục polling |

Ngoài unit test, nên có HTTP integration test cho endpoint last_operation. Gửi request qua controller SCOSB để xác minh path, query parameter operation, status HTTP, JSON response và cơ chế exception mapping.

## 14. Bảo mật và vận hành endpoint polling

Endpoint last_operation có thể bị gọi thường xuyên và chứa thông tin về trạng thái tài nguyên. Broker cần áp dụng:

- Xác thực platform theo cơ chế đã cấu hình.
- Kiểm tra quyền truy cập instance và operation.
- Truy vấn theo cặp instance ID và operation ID.
- Không đưa provider credentials, secret hoặc raw exception vào description.
- Giới hạn tốc độ polling để tránh gây quá tải operation store.
- Ghi correlation ID, operation ID và kết quả tra cứu vào log theo chính sách bảo mật.
- Theo dõi số operation đang chạy, tuổi operation, số operation quá hạn và tỷ lệ FAILED.
- Có cảnh báo khi operation ở IN_PROGRESS lâu hơn ngưỡng dự kiến.
- Giữ lịch sử operation đủ lâu cho polling và điều tra.

Các metric có thể theo dõi:

| Metric | Ý nghĩa |
|---|---|
| broker_operations_in_progress | Số operation đang chạy |
| broker_operation_duration_seconds | Thời gian từ lúc bắt đầu đến lúc kết thúc |
| broker_operation_failures_total | Tổng số operation thất bại |
| broker_last_operation_requests_total | Số request polling |
| broker_operation_stale_total | Số operation vượt thời gian xử lý dự kiến |

Tên metric là gợi ý cho hệ thống observability của broker, không phải tên bắt buộc trong OSB API.

## 15. Quy trình triển khai thực tế

Khi bổ sung getLastOperation() cho broker, có thể thực hiện theo trình tự:

1. Xác định những nghiệp vụ nào cần bất đồng bộ: provision, update hoặc deprovision.
2. Định nghĩa operation ID ổn định và operation type.
3. Thiết kế operation store với trạng thái, timestamp, instance ID và provider operation ID.
4. Tạo repository hỗ trợ truy vấn theo instance và operation.
5. Xây dựng state mapping từ trạng thái nội bộ sang ba giá trị OSB API.
6. Implement **getLastOperation()** trong **ServiceInstanceService**.
7. Đảm bảo thao tác ghi operation và enqueue worker có tính nhất quán, ưu tiên transactional outbox.
8. Cập nhật worker để ghi trạng thái và kết quả cuối cùng.
9. Kiểm thử polling, lỗi, restart, retry và request đồng thời.
10. Kiểm tra HTTP integration với platform đích và theo dõi metric khi vận hành.

Không cần gọi provider trong mỗi lần polling. Việc tra cứu trạng thái phải dựa trên operation store đã được worker cập nhật; provider call thuộc trách nhiệm của worker hoặc tiến trình reconciliation.

## Kết luận

**getLastOperation()** là điểm nối giữa xử lý bất đồng bộ của broker và cơ chế polling của platform. Platform gửi request tạo, cập nhật hoặc thu hồi service instance; broker ghi nhận operation, xử lý provider ở background và cung cấp trạng thái qua **GET /v2/service_instances/{instance_id}/last_operation**. Trong Spring Cloud Open Service Broker, triển khai phương thức này qua **ServiceInstanceService**, đọc operation theo instance ID và operation ID, rồi ánh xạ trạng thái nội bộ thành **in progress**, **succeeded** hoặc **failed**. Khi operation được lưu bền vững, có idempotency, xử lý restart và kiểm soát truy cập, platform có thể theo dõi tiến độ đáng tin cậy mà không phải giữ HTTP connection trong suốt quá trình provider làm việc.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md) — endpoint last_operation, query parameter operation và trạng thái operation.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — ServiceInstanceService và các model request/response.
- [Spring Cloud Open Service Broker — ServiceInstanceService API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/ServiceInstanceService.html) — contract xử lý vòng đời service instance.
- [Spring Cloud Open Service Broker — GetLastServiceOperationResponse API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/model/instance/GetLastServiceOperationResponse.html) — response trạng thái operation.

