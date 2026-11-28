# Phản hồi HTTP 202, trường operation và định danh tác vụ

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker thực hiện các thao tác vòng đời theo Open Service Broker API (OSB API): cấp phát service instance, cập nhật cấu hình hoặc plan và thu hồi tài nguyên. Những thao tác này có thể kéo dài vì broker phải gọi API của nhà cung cấp, chờ database khởi tạo, cấu hình mạng, thực hiện migration hoặc xác nhận tài nguyên sẵn sàng. Khi không thể hoàn tất trong một request HTTP, broker có thể dùng cơ chế bất đồng bộ của OSB API.

Cơ chế này có ba thành phần cần hiểu cùng nhau:

- **HTTP 202 Accepted** cho biết broker đã chấp nhận yêu cầu để tiếp tục xử lý; nó không có nghĩa thao tác đã hoàn tất.
- **Trường operation** trong response cung cấp một định danh để platform tham chiếu đến lần xử lý đang diễn ra.
- **Endpoint last_operation** cho phép platform truy vấn trạng thái của thao tác đó cho đến khi đạt trạng thái kết thúc.

Định danh operation là cầu nối giữa request ban đầu và các lần polling sau đó. Nếu broker trả 202 nhưng không lưu trạng thái bền vững, không thể xác định operation nào đang chạy hoặc không thể phục hồi sau restart, platform sẽ không biết tài nguyên đã được tạo hay chưa. Vì vậy, thiết kế response, operation record, worker và endpoint truy vấn phải nhất quán.

## 1. Vì sao cần phản hồi bất đồng bộ?

Một request provision có thể kích hoạt nhiều công việc:

1. Kiểm tra service offering, plan, context và quyền của tenant.
2. Đặt trước quota hoặc dung lượng.
3. Gọi provider để tạo database hoặc cụm dịch vụ.
4. Chờ provider hoàn tất khởi tạo.
5. Tạo user, database, firewall rule hoặc endpoint.
6. Lưu metadata tài nguyên và cập nhật trạng thái instance.
7. Xác nhận tài nguyên đủ điều kiện sử dụng.

Nếu toàn bộ quy trình diễn ra trong một HTTP request, kết nối có thể bị giữ lâu, timeout ở gateway hoặc platform, và client có thể gửi lại request dù thao tác phía broker vẫn tiếp tục. Việc này đặc biệt rủi ro khi provider đã tạo tài nguyên nhưng broker chưa nhận được response.

OSB API cho phép broker chấp nhận request và xử lý tiếp ở background. Platform nhận một phản hồi sớm, sau đó hỏi trạng thái qua last operation. Broker có thể dùng queue, worker, scheduler hoặc cơ chế orchestration nội bộ; platform chỉ cần nhìn thấy hợp đồng HTTP mà OSB API quy định.

Một ví dụ điển hình là tạo PostgreSQL instance trên cloud provider. Broker nhận yêu cầu, lưu operation, đưa job vào queue và trả 202. Worker gọi provider. Trong thời gian chờ, platform poll last operation. Khi database sẵn sàng và metadata được lưu đầy đủ, broker trả trạng thái succeeded.

## 2. Phân biệt 202 Accepted với kết quả hoàn tất

HTTP 202 có nghĩa server đã chấp nhận request để xử lý, nhưng xử lý có thể chưa hoàn tất. Trong OSB API, đây là phản hồi được dùng khi broker thực hiện một thao tác bất đồng bộ mà platform đã cho phép.

| Phản hồi | Ý nghĩa | Hành động tiếp theo của platform |
|---|---|---|
| Response đồng bộ thành công | Thao tác đã hoàn tất theo hợp đồng endpoint | Tiếp tục workflow, chẳng hạn cung cấp binding hoặc cập nhật trạng thái |
| **202 Accepted** | Broker đã nhận operation và đang xử lý | Poll endpoint last operation |
| Response lỗi | Request không được chấp nhận hoặc không thể xử lý | Xử lý lỗi theo mã và error body; không giả định có operation thành công |

Không được trả 202 chỉ vì request đã được ghi vào database hoặc đã được gửi vào queue nếu broker chưa bảo đảm có thể theo dõi và tiếp tục công việc. Trước khi gửi response, broker cần có một operation record bền vững và cơ chế đảm bảo worker sẽ nhận được công việc.

Cũng không được xem 202 là bằng chứng rằng provider đã tạo tài nguyên. Tại thời điểm trả 202, operation có thể mới ở trạng thái accepted hoặc queued. Platform phải đợi trạng thái terminal từ last operation.

## 3. Platform cho phép bất đồng bộ bằng accepts_incomplete

Trong các thao tác OSB hỗ trợ asynchronous completion, platform gửi query parameter **accepts_incomplete=true** để cho broker biết nó chấp nhận quy trình bất đồng bộ.

Ví dụ provision:

~~~http
PUT /v2/service_instances/instance-7f3a?accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Ví dụ update:

~~~http
PATCH /v2/service_instances/instance-7f3a?accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Ví dụ deprovision:

~~~http
DELETE /v2/service_instances/instance-7f3a?accepts_incomplete=true
X-Broker-API-Version: 2.17
~~~

Broker phải xem đây là một phần của hợp đồng request. Nếu thao tác cần xử lý bất đồng bộ nhưng platform không gửi tín hiệu chấp nhận, broker phải trả lỗi phù hợp theo OSB API, thay vì âm thầm trả 202. Lỗi thường được biểu diễn bằng mã **AsyncRequired** với HTTP 422 Unprocessable Entity theo quy tắc của giao thức.

Ngược lại, khi platform gửi **accepts_incomplete=true**, broker vẫn có thể hoàn tất đồng bộ nếu thao tác kết thúc nhanh. Tham số này cho phép broker dùng async khi cần; nó không bắt buộc mọi request phải trả 202.

Các thao tác vòng đời thường được xử lý theo cơ chế này gồm provision, update và deprovision. Không tự áp dụng cùng cơ chế cho binding hoặc unbinding nếu phiên bản OSB API và contract của endpoint không cho phép.

## 4. Response 202 và trường operation

Một response bất đồng bộ có thể có dạng:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "op-7f3a-provision-001"
}
~~~

Giá trị **operation** là định danh do broker tạo để platform tham chiếu đến operation đang chạy. Nó không phải tên thao tác HTTP, không phải service instance ID và cũng không nhất thiết là ID của message trong queue.

Trong OSB API, trường operation có thể được dùng để phân biệt một thao tác cụ thể khi platform truy vấn last operation. Broker cần tuân theo quy tắc của phiên bản API đang hỗ trợ; nếu response không cung cấp operation, platform có thể truy vấn last operation mà không có giá trị operation. Cách bỏ trường này chỉ phù hợp khi broker có thể xác định duy nhất operation cần trả về theo quy tắc giao thức và thiết kế tuần tự của mình.

Một số nguyên tắc khi tạo operation token:

- Định danh phải ổn định trong suốt vòng đời của operation.
- Platform phải có thể gửi lại nguyên giá trị đó trong query parameter operation.
- Token không nên chứa password, credential, access token hoặc dữ liệu nhạy cảm.
- Không nên nhúng thông tin nội bộ của provider mà platform không cần biết.
- Không tái sử dụng một token cho hai operation khác nhau.
- Token cần được liên kết với đúng service instance và loại thao tác.
- Broker phải lưu mapping giữa operation token bên ngoài và operation record nội bộ.

Có thể dùng UUID hoặc một mã opaque ngẫu nhiên. Nếu dùng ID nội bộ tuần tự, cần cân nhắc việc lộ thông tin về số lượng hoặc thứ tự tài nguyên. Operation token không phải cơ chế xác thực; endpoint vẫn phải được bảo vệ và caller vẫn phải được phân quyền.

## 5. Operation khác instance ID, job ID và correlation ID

Một hệ thống có thể có nhiều loại định danh. Dùng lẫn chúng dễ dẫn đến truy vấn sai hoặc rò rỉ chi tiết triển khai.

| Định danh | Đại diện cho | Phạm vi và vòng đời |
|---|---|---|
| **service instance ID** | Tài nguyên dịch vụ theo định danh platform | Tồn tại theo vòng đời service instance |
| **binding ID** | Một quan hệ binding giữa instance và consumer | Tồn tại theo vòng đời binding |
| **operation** | Một lần provision, update hoặc deprovision đang được theo dõi | Tồn tại theo vòng đời của lần xử lý |
| **internal job ID** | Công việc trong queue hoặc worker framework | Phụ thuộc hệ thống xử lý nền |
| **provider resource ID** | Tài nguyên thực tế tại nhà cung cấp | Tồn tại theo vòng đời tài nguyên provider |
| **correlation ID** | Nhóm log/trace của một request hoặc chuỗi xử lý | Dùng cho observability và chẩn đoán |

Service instance ID trả lời câu hỏi "đang quản lý tài nguyên nào?". Operation trả lời "đang theo dõi lần thay đổi nào của tài nguyên đó?". Internal job ID phục vụ worker; correlation ID giúp liên kết log và trace. Các giá trị này có thể được liên kết trong database nhưng không cần có cùng một chuỗi.

Ví dụ, một instance có thể được provision một lần, update nhiều lần và deprovision một lần. Mỗi lần xử lý bất đồng bộ có operation token riêng, trong khi service instance ID không đổi. Nếu broker dùng instance ID làm operation token, hai lần update liên tiếp sẽ không thể được phân biệt rõ khi platform poll.

## 6. Trường operation được platform sử dụng như thế nào?

Sau khi nhận response 202, platform lấy giá trị operation và đưa nó vào query parameter của endpoint last operation.

~~~http
GET /v2/service_instances/instance-7f3a/last_operation?operation=op-7f3a-provision-001
X-Broker-API-Version: 2.17
~~~

Nếu broker không cung cấp operation token trong response, platform có thể gọi endpoint mà không có query parameter operation theo quy tắc OSB API. Khi đó broker phải có cách xác định operation hiện tại một cách không mơ hồ, thường bằng cách chỉ cho phép một operation đang hoạt động trên một instance tại một thời điểm.

Endpoint last operation trả về trạng thái hiện tại của operation:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "state": "in progress",
  "description": "Database is being initialized."
}
~~~

Các trạng thái OSB API thường dùng:

| State | Ý nghĩa | Platform nên làm gì |
|---|---|---|
| **in progress** | Operation vẫn đang chạy hoặc chờ bước tiếp theo | Tiếp tục polling theo chính sách platform |
| **succeeded** | Operation hoàn tất thành công | Tiếp tục workflow |
| **failed** | Operation kết thúc với lỗi | Hiển thị hoặc xử lý lỗi; không tiếp tục như thành công |

Trường description có thể cung cấp thông tin tiến trình hoặc lỗi ở mức an toàn. Không nên trả stack trace, SQL, endpoint quản trị, credential hoặc response thô của provider. Platform cần biết operation đang chạy, thành công hay thất bại; nó không cần biết toàn bộ cấu trúc queue hoặc API nội bộ của broker.

## 7. Luồng end-to-end từ request đến terminal state

Sơ đồ dưới đây mô tả provision bất đồng bộ:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Spring Cloud Broker
    participant DB as Operation Store
    participant Q as Queue / Outbox
    participant W as Worker
    participant R as Resource Provider

    P->>B: PUT service_instances?accepts_incomplete=true
    B->>B: Authenticate, validate và authorize
    B->>DB: Tạo operation record
    B->>Q: Ghi ProvisionRequested
    B-->>P: 202 Accepted + operation token
    P->>B: GET last_operation?operation=token
    B->>DB: Đọc operation state
    DB-->>B: in progress
    B-->>P: 200 OK, state=in progress
    Q->>W: Giao provision job
    W->>R: Tạo database
    R-->>W: Resource ready
    W->>DB: Lưu provider ID và succeeded
    P->>B: GET last_operation?operation=token
    B->>DB: Đọc operation state
    DB-->>B: succeeded
    B-->>P: 200 OK, state=succeeded
~~~

Các điểm quan trọng:

1. Broker xác thực và validate request trước khi tạo operation.
2. Operation record phải được lưu bền vững trước khi trả 202.
3. Việc lưu operation và phát job cần tránh khoảng trống mất message.
4. Worker thực hiện side effect tại provider.
5. Kết quả provider và trạng thái operation phải được lưu trước khi báo succeeded.
6. Last operation đọc trạng thái đã lưu, không tự suy đoán từ việc worker còn chạy hay không.
7. Platform có thể gọi last operation nhiều lần; các lần đọc không được làm thay đổi trạng thái operation.

## 8. Operation record cần lưu những gì?

Broker cần lưu đủ dữ liệu để trả lời last operation sau khi process restart, worker đổi máy hoặc queue giao lại message.

Một mô hình record minh họa:

| Field | Mục đích |
|---|---|
| **operation_token** | Giá trị opaque trả về trong trường operation |
| **instance_id** | Service instance liên quan |
| **operation_type** | Provision, update hoặc deprovision |
| **state** | Trạng thái nội bộ hiện tại |
| **description** | Thông tin tiến trình đã làm sạch |
| **request_fingerprint** | Nhận diện request retry hoặc nội dung xung đột |
| **provider_resource_id** | ID tài nguyên tại provider nếu đã có |
| **attempt_count** | Số lần worker thực hiện |
| **next_retry_at** | Thời điểm retry tiếp theo nếu có |
| **correlation_id** | Liên kết log và trace |
| **created_at**, **updated_at** | Mốc thời gian |
| **completed_at** | Thời điểm terminal state |
| **failure_code** | Mã lỗi nội bộ đã chuẩn hóa |

Không nhất thiết trả tất cả field này cho platform. Đây là dữ liệu nội bộ để broker phục hồi và quan sát operation. Response last operation chỉ nên chứa các field OSB API quy định, chẳng hạn state và description.

Operation token nên có unique constraint trong database. Có thể thêm ràng buộc cho cặp instance ID và operation token để truy vấn đúng phạm vi. Khi endpoint last operation nhận token, broker cần kiểm tra token đó thuộc instance trong URL và caller được phép truy vấn instance.

## 9. Không để mất operation giữa database và queue

Một lỗi thường gặp là broker thực hiện hai hành động tách rời:

1. Ghi operation vào database.
2. Gửi message vào queue.

Nếu database commit thành công nhưng gửi queue thất bại, operation bị kẹt ở trạng thái accepted. Nếu gửi queue trước rồi database rollback, worker có thể chạy một job mà broker không có record để theo dõi.

Transactional outbox giúp xử lý khoảng trống này. Broker ghi operation và outbox event trong cùng một transaction database. Một publisher đọc outbox và gửi message đến queue; sau khi gửi thành công, event được đánh dấu đã publish.

~~~mermaid
flowchart TD
    A["Nhận request async"] --> B["Transaction database"]
    B --> C["Insert operation"]
    B --> D["Insert outbox event"]
    C --> E["Commit"]
    D --> E
    E --> F["Outbox publisher"]
    F --> G["Message queue"]
    G --> H["Worker"]
    H --> I["Provider adapter"]
    I --> J["Cập nhật operation"]
    J --> K["Last operation trả state"]
~~~

Outbox publisher có thể gửi lại event nếu không nhận được xác nhận. Vì vậy worker phải idempotent hoặc có cơ chế claim/lease để tránh side effect lặp. Việc queue giao message nhiều lần là tình huống bình thường trong hệ thống phân tán.

Nếu không dùng outbox, broker cần một cơ chế tương đương có khả năng phục hồi và đối soát. Chỉ dùng một lệnh gửi queue sau transaction mà không có recovery sẽ để lại operation mồ côi khi hệ thống gặp sự cố.

## 10. State machine và ánh xạ sang OSB

Trạng thái nội bộ có thể chi tiết hơn trạng thái mà platform nhìn thấy.

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> QUEUED
    QUEUED --> RUNNING
    RUNNING --> WAITING_PROVIDER
    WAITING_PROVIDER --> RUNNING
    RUNNING --> RETRY_WAIT
    RETRY_WAIT --> RUNNING
    RUNNING --> COMPENSATING
    COMPENSATING --> FAILED
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Bảng ánh xạ:

| Trạng thái nội bộ | OSB state |
|---|---|
| ACCEPTED | in progress |
| QUEUED | in progress |
| RUNNING | in progress |
| WAITING_PROVIDER | in progress |
| RETRY_WAIT | in progress |
| COMPENSATING | in progress |
| SUCCEEDED | succeeded |
| FAILED | failed |

Không trả một trạng thái terminal quá sớm. Ví dụ, worker đã gửi lệnh tạo database nhưng provider vẫn đang khởi tạo thì operation còn in progress. Khi provider trả thành công nhưng broker chưa lưu endpoint hoặc metadata bắt buộc, operation cũng chưa nên là succeeded.

Terminal state nên bất biến. Một operation đã succeeded không được chuyển lại in progress vì một retry đến muộn. Nếu cần sửa chữa sau thành công, tạo operation mới hoặc workflow bù trừ riêng và lưu quan hệ giữa chúng.

## 11. Operation token, retry và idempotency

Platform có thể gửi lại request ban đầu khi timeout. Broker cần nhận ra request đó có phải retry của cùng một thao tác hay là một yêu cầu update mới.

Một chiến lược là dùng service instance ID cùng loại operation và fingerprint của nội dung có ý nghĩa. Fingerprint có thể được tạo từ service ID, plan ID, parameters đã chuẩn hóa và context liên quan. Không đưa secret thô vào fingerprint log; nếu input chứa dữ liệu nhạy cảm, dùng hash an toàn và kiểm soát quyền truy cập.

Khi nhận request lặp:

- Nếu cùng instance, cùng loại operation và cùng nội dung trong khi operation còn chạy, trả lại kết quả/operation hiện có theo quy tắc idempotency.
- Nếu operation đã hoàn tất, trả kết quả phù hợp với trạng thái hiện có; không tạo tài nguyên mới.
- Nếu cùng instance nhưng request có nội dung khác trong khi operation trước đang chạy, xử lý conflict hoặc tuần tự hóa theo policy.
- Nếu provider đã hoàn thành nhưng broker chưa lưu được kết quả, tra cứu provider theo idempotency key hoặc tên tài nguyên ổn định trước khi gọi tạo lần nữa.

Operation token không tự làm request idempotent. Token chỉ định danh một operation đã được chấp nhận. Idempotency phải được bảo đảm ở request handler, operation store, worker và provider adapter.

## 12. Nhiều operation trên cùng một service instance

Một instance có thể nhận nhiều yêu cầu trong suốt vòng đời: provision, update, update lần hai và deprovision. Broker phải quyết định có cho phép nhiều operation cùng chạy hay không.

### 12.1. Chỉ một operation đang hoạt động

Thiết kế đơn giản là chỉ cho phép một operation vòng đời đang hoạt động trên mỗi instance. Request mới trong lúc operation trước chưa kết thúc có thể bị từ chối bằng conflict hoặc được xếp hàng theo chính sách.

Ưu điểm là endpoint last operation có thể xác định operation hiện tại mà không cần token riêng trong mọi response. Đổi lại, broker cần kiểm soát khóa theo instance và không được để hai worker cùng xử lý một instance đồng thời.

### 12.2. Nhiều operation có định danh riêng

Nếu broker cho phép nhiều operation cùng tồn tại hoặc cần phân biệt operation đã kết thúc với operation mới, trường operation giúp platform truy vấn đúng tác vụ. Mỗi token phải ánh xạ duy nhất đến một record và không bị tái sử dụng.

Khi platform gửi token cũ, broker phải trả trạng thái của operation đó, không trả trạng thái của operation mới nhất chỉ vì cùng instance ID. Nếu token không thuộc instance trong URL hoặc không tồn tại, broker trả lỗi phù hợp theo hợp đồng và chính sách bảo mật.

### 12.3. Tuần tự hóa các thay đổi có phụ thuộc

Ngay cả khi broker tạo token riêng, điều đó không có nghĩa provider có thể chạy mọi thao tác song song. Ví dụ, không nên vừa migration plan vừa deprovision cùng một database. Broker có thể lưu operation queue theo instance, kiểm tra dependency và chỉ bắt đầu thao tác tiếp theo khi thao tác trước đạt terminal state.

## 13. Deprovision bất đồng bộ và vòng đời bản ghi

Deprovision là trường hợp dễ xử lý sai vì broker có thể muốn xóa metadata ngay khi nhận DELETE. Nếu xóa luôn bản ghi instance, endpoint last operation có thể không còn dữ liệu để trả trạng thái cho platform.

Một cách thiết kế an toàn:

1. Đánh dấu instance đang ở trạng thái DEPROVISIONING.
2. Tạo operation record và lưu outbox event.
3. Trả 202 cùng operation token khi platform chấp nhận async.
4. Worker giải phóng tài nguyên tại provider.
5. Ghi nhận kết quả provider và cập nhật operation thành succeeded hoặc failed.
6. Giữ tombstone hoặc metadata tối thiểu đủ để trả last operation trong khoảng thời gian cần thiết.
7. Chỉ xóa metadata theo chính sách retention sau khi workflow kết thúc và platform không còn cần truy vấn.

Nếu provider xóa tài nguyên thành công nhưng broker chưa commit, reconciliation phải có thể xác định tài nguyên đã bị xóa. Nếu provider từ chối do resource còn phụ thuộc, operation phải chuyển failed với mô tả đã làm sạch; không báo succeeded chỉ vì request DELETE đã được chấp nhận.

## 14. Bảo mật endpoint last operation

Last operation có thể tiết lộ thông tin về tài nguyên, tên provider hoặc lỗi nội bộ. Endpoint cần được bảo vệ tương tự các endpoint vòng đời khác.

- Xác thực platform client trên mỗi request polling.
- Kiểm tra quyền truy vấn đối với service instance trong path.
- Xác minh operation token thuộc đúng instance.
- Không dùng operation token như bearer credential.
- Không trả raw provider response hoặc stack trace.
- Giới hạn kích thước và định dạng query parameter.
- Không đưa token hoặc dữ liệu nhạy cảm vào log ở dạng không cần thiết.
- Dùng TLS và audit/correlation ID để truy vết request.

Operation token nên là opaque identifier. Dù token khó đoán, broker vẫn phải xác thực và authorization. Nếu chỉ dựa vào việc token đủ dài để bảo vệ trạng thái, người có được token có thể truy vấn thông tin ngoài quyền của họ.

## 15. Ánh xạ vào Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction để xử lý request OSB trong ứng dụng Spring. Ở tầng service, broker nhận yêu cầu create/update/delete service instance, quyết định hoàn tất đồng bộ hay bất đồng bộ và trả response theo model của thư viện.

Một thiết kế có thể chia thành:

| Thành phần | Trách nhiệm |
|---|---|
| OSB service handler | Nhận request và trả response tương ứng |
| Lifecycle coordinator | Kiểm tra state, policy và tạo operation |
| Operation repository | Lưu operation token, state và metadata |
| Outbox publisher | Phát sự kiện sau transaction |
| Worker | Thực hiện công việc dài |
| Provider adapter | Gọi API của nhà cung cấp |
| Last operation service | Tìm operation và map state sang OSB response |

Pseudocode minh họa response async:

~~~java
public CreateServiceInstanceResponse provision(
        CreateServiceInstanceRequest request) {

    Operation operation = lifecycleCoordinator.acceptProvision(request);

    return CreateServiceInstanceResponse.builder()
        .async(true)
        .operation(operation.publicToken())
        .build();
}
~~~

Đây là pseudocode về ý tưởng response; tên builder method và kiểu trả về cụ thể phải đối chiếu phiên bản Spring Cloud Open Service Broker đang dùng. Điểm quan trọng là response phải biểu diễn rõ operation bất đồng bộ và token được lưu bền vững.

Handler last operation có thể có dạng khái niệm:

~~~java
public GetLastServiceOperationResponse lastOperation(
        LastOperationRequest request) {

    Operation operation = operationRepository.requireForInstance(
        request.getServiceInstanceId(),
        request.getOperation()
    );

    return GetLastServiceOperationResponse.builder()
        .state(mapToOsbState(operation.state()))
        .description(safeDescription(operation))
        .build();
}
~~~

Nếu phiên bản thư viện dùng tên request/response hoặc getter khác, hãy dùng đúng model tương ứng. Không nên tự định nghĩa một endpoint HTTP song song nếu thư viện đã cung cấp extension point cho last operation.

### 15.1. Lưu operation và outbox trong transaction

Một application service có thể lưu operation cùng outbox event:

~~~java
@Transactional
public Operation acceptProvision(ProvisionCommand command) {
    Operation operation = operationRepository
        .findByRequestFingerprint(command.fingerprint())
        .orElseGet(() -> operationRepository.createAccepted(command));

    outboxRepository.appendIfAbsent(
        operation.getId(),
        new ProvisionRequested(operation.getId(), command.instanceId())
    );

    return operation;
}
~~~

Transaction bảo đảm operation và sự kiện được ghi cùng nhau. Worker không chạy trực tiếp trong transaction request; nó đọc sự kiện, gọi provider và cập nhật kết quả trong transaction riêng. Repository cần unique constraint hoặc cơ chế chống tạo trùng khi hai request retry đến đồng thời.

### 15.2. Worker cập nhật operation

Worker có thể thực hiện theo trình tự:

1. Claim job với lease hoặc cơ chế khóa phù hợp.
2. Đọc operation và kiểm tra state hiện tại.
3. Gọi provider adapter với idempotency key ổn định.
4. Lưu provider resource ID và kết quả.
5. Cập nhật operation thành succeeded hoặc trạng thái retry/failed.
6. Xác nhận message sau khi trạng thái đã được commit.

Không giữ transaction database mở trong toàn bộ thời gian chờ provider. Timeout, retry và lỗi mạng cần được phân loại. Nếu provider hỗ trợ truy vấn trạng thái theo request ID, dùng nó để khôi phục sau khi broker mất response.

## 16. Polling và hiệu năng

Platform quyết định lịch polling theo cách tích hợp và quy tắc vận hành của nó. Broker nên thiết kế endpoint last operation nhẹ, chỉ đọc dữ liệu trạng thái cần thiết từ operation store.

Một số nguyên tắc:

- Dùng index theo instance ID và operation token.
- Tránh gọi provider ở mỗi lần polling; trạng thái provider nên được worker đồng bộ vào store.
- Không tạo side effect trong GET last operation.
- Trả cùng state khi không có thay đổi.
- Giữ response nhỏ và không truy vấn nhiều bảng không cần thiết.
- Ghi metric về số operation in progress, tuổi operation và tỷ lệ failed.
- Có cảnh báo khi operation vượt thời gian dự kiến hoặc không có worker cập nhật.
- Dùng retention policy để dọn operation cũ sau khi không còn cần truy vấn.

Không nên giả định mọi platform có cùng chu kỳ polling. Broker cần chịu được các GET lặp và tránh biến endpoint trạng thái thành một điểm tải lớn lên provider.

## 17. Kiểm thử hợp đồng 202 và operation

Kiểm thử cần xác minh cả response ban đầu lẫn các lần truy vấn sau đó.

| Nhóm kiểm thử | Trường hợp cần xác minh |
|---|---|
| Async handshake | Có accepts_incomplete=true thì broker có thể trả 202 |
| AsyncRequired | Thao tác cần async nhưng platform không chấp nhận thì trả lỗi theo OSB |
| Response body | Operation token được trả đúng và ổn định |
| Token mapping | Token ánh xạ đúng instance và operation |
| Polling | Last operation trả in progress, succeeded và failed đúng lúc |
| Token cũ | Poll token cũ trả đúng operation cũ, không nhầm operation mới |
| Token sai | Token không thuộc instance bị từ chối |
| Retry request | Request lặp không tạo operation hoặc tài nguyên trùng |
| Worker redelivery | Message giao lặp không tạo side effect lặp |
| Crash recovery | Restart broker/worker vẫn tiếp tục operation |
| Outbox | Không mất event giữa commit database và gửi queue |
| Deprovision | Instance metadata đủ để poll trong khi đang xóa |
| Security | Không thể truy vấn operation của tenant khác |
| Polling load | GET last operation không gọi provider mỗi lần poll |

Một kịch bản integration test điển hình:

1. Gửi provision với accepts_incomplete=true.
2. Xác nhận HTTP 202 và đọc operation token.
3. Gọi last operation bằng token đó; ban đầu nhận in progress.
4. Cho worker xử lý xong job.
5. Gọi last operation lại; nhận succeeded.
6. Gửi lại request provision với cùng instance ID và cùng nội dung.
7. Xác nhận broker không tạo database thứ hai và trả kết quả theo quy tắc idempotency.
8. Khởi động lại worker giữa một operation khác và xác nhận operation vẫn có thể phục hồi.

## 18. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi 202 là hoàn tất | Platform tiếp tục workflow khi tài nguyên chưa sẵn sàng | Chỉ terminal state mới xác nhận hoàn tất |
| Trả 202 trước khi lưu operation | Platform không thể truy vấn hoặc broker mất trạng thái khi restart | Persist operation trước response |
| Dùng instance ID làm operation token | Không phân biệt được nhiều lần update | Tạo token riêng cho mỗi operation |
| Dùng queue message ID làm token công khai | Lộ chi tiết nội bộ và phụ thuộc queue | Ánh xạ token opaque sang job nội bộ |
| Tạo operation nhưng không phát job bền vững | Operation bị kẹt ở accepted | Transactional outbox hoặc cơ chế tương đương |
| Không có idempotency trong worker | Message giao lặp tạo tài nguyên trùng | Provider idempotency và reconciliation |
| Polling gọi provider trực tiếp | Tăng tải, latency và lỗi phụ thuộc | Poll state store đã được worker cập nhật |
| Xóa instance record ngay khi nhận deprovision | Last operation không còn dữ liệu để trả | Giữ tombstone/operation metadata |
| Cho nhiều migration cùng chạy trên instance | Xung đột và hỏng trạng thái | Serialize operation theo instance |
| Dùng operation token thay xác thực | Lộ token có thể dẫn tới truy vấn trái phép | Authenticate và authorize mọi request |

## 19. Checklist triển khai

Trước khi phát hành asynchronous operation, hãy xác nhận:

- [ ] Endpoint hỗ trợ async đúng theo phiên bản OSB API.
- [ ] Platform gửi accepts_incomplete=true khi chấp nhận xử lý bất đồng bộ.
- [ ] Broker trả 202 chỉ sau khi operation được ghi bền vững và có thể tiếp tục.
- [ ] Response operation token là opaque, ổn định và không chứa secret.
- [ ] Token được ánh xạ duy nhất đến instance và operation record.
- [ ] Last operation nhận và xử lý query operation đúng quy tắc.
- [ ] Nếu không có operation token, broker vẫn xác định được operation duy nhất theo policy.
- [ ] State nội bộ được ánh xạ đúng sang in progress, succeeded hoặc failed.
- [ ] Terminal state không bị thay đổi bởi retry hoặc worker đến muộn.
- [ ] Database operation và outbox event được ghi nhất quán.
- [ ] Worker có retry, timeout, lease/claim và xử lý message giao lặp.
- [ ] Provider side effect có idempotency hoặc cơ chế tra cứu/reconciliation.
- [ ] Deprovision giữ đủ metadata để platform poll đến terminal state.
- [ ] Last operation không tạo side effect và không gọi provider cho mỗi lần poll.
- [ ] Endpoint polling được xác thực, phân quyền và không tiết lộ dữ liệu nhạy cảm.
- [ ] Có metric, alert và test cho operation bị kẹt, failed, retry và recovery.

Khi HTTP 202, trường operation và endpoint last operation được thiết kế như một hợp đồng thống nhất, platform có thể theo dõi một thao tác dài mà không phải giữ request ban đầu mở. Broker vẫn kiểm soát trạng thái và khả năng phục hồi thông qua operation store, outbox, worker và provider adapter. Đây là nền tảng để Spring Cloud Service Broker thực hiện provision, update và deprovision đáng tin cậy trong môi trường phân tán.
