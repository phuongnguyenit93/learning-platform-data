# Luân chuyển binding với predecessor_binding_id khi phiên bản hỗ trợ

Binding thường chứa credentials hoặc quyền truy cập mà một ứng dụng dùng để kết nối đến service instance. Các credentials này có thể hết hạn, bị lộ hoặc cần được thay mới theo chu kỳ bảo mật. Nếu chỉ xóa binding cũ rồi tạo binding mới, ứng dụng có thể mất kết nối trong khoảng chuyển tiếp; nền tảng cũng có thể không lưu lại toàn bộ parameters ban đầu để tạo lại binding tương đương.

Open Service Broker API (OSB API) v2.17 bổ sung cơ chế **binding rotation**. Nền tảng yêu cầu tạo một binding mới và gửi trường **predecessor_binding_id** để chỉ rõ binding cũ làm tiền nhiệm. Broker nhờ đó biết binding mới kế thừa ngữ cảnh và cấu hình từ binding nào. Hai binding phải có thể hoạt động song song cho đến khi binding cũ hết hạn hoặc bị xóa.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, cơ chế này giúp xây dựng quy trình đổi credentials có kiểm soát, giảm gián đoạn cho ứng dụng và giữ được quan hệ giữa các thế hệ binding. Tính năng chỉ được sử dụng khi cả nền tảng, phiên bản OSB API và phiên bản Spring Cloud Open Service Broker đều hỗ trợ. Bài học trình bày hợp đồng v2.17, cấu trúc catalog và request, vòng đời successor/predecessor, xử lý đồng bộ hoặc bất đồng bộ, idempotency, bảo mật và cách tổ chức triển khai trong Spring.

## 1. Vì sao cần binding rotation?

Giả sử một ứng dụng đang sử dụng binding có ID **binding-100**. Provider cấp cho binding này một database user và password. Sau một thời gian, password sắp hết hạn hoặc tổ chức yêu cầu xoay vòng credentials.

Cách đơn giản là unbind binding-100 rồi tạo binding mới. Cách này có thể gây ra một khoảng thời gian ứng dụng không có thông tin truy cập hợp lệ. Nếu tạo binding mới trước khi unbind cũ, nền tảng có thể phải gửi lại parameters mà nó đã không còn lưu. Broker cũng không biết binding mới có quan hệ gì với binding cũ để chuyển tiếp metadata hoặc cấu hình.

Binding rotation giải quyết vấn đề bằng cách tạo một binding mới có quan hệ rõ ràng với binding cũ:

- Binding cũ được gọi là **predecessor**.
- Binding mới được gọi là **successor**.
- Successor có một binding ID mới.
- Request tạo successor tham chiếu predecessor bằng predecessor_binding_id.
- Broker duy trì cả hai binding hoạt động song song trong giai đoạn chuyển tiếp.
- Sau khi ứng dụng hoặc nền tảng đã chuyển sang successor, predecessor có thể được unbind hoặc hết hạn theo chính sách.

Cơ chế này phù hợp với database credentials, access token, API key, tài khoản message broker hoặc các quyền truy cập có thời hạn. Broker có thể tạo danh tính mới, chuyển cấu hình quyền tương ứng và duy trì kết nối cũ trong khoảng thời gian chuyển đổi.

### Rotation khác với tạo thêm một binding độc lập

Một ứng dụng có thể tạo nhiều binding độc lập cho nhiều consumer. Các binding đó không nhất thiết có quan hệ với nhau.

Rotation là một thao tác tạo successor có tham chiếu predecessor. Broker biết rằng binding mới thay thế hoặc tiếp nối một binding đã tồn tại. Nhờ quan hệ này, broker có thể kế thừa parameters, quyền, metadata và trạng thái nghiệp vụ phù hợp.

Rotation cũng khác với việc cập nhật password ngay trên cùng một user. Nếu provider đổi password của user cũ tại chỗ, credentials cũ có thể mất hiệu lực ngay lập tức. Khi cần thời gian chuyển đổi không gián đoạn, nên tạo principal hoặc credential mới cho successor, giữ predecessor hoạt động cho đến khi quá trình chuyển đổi hoàn tất.

## 2. Điều kiện phiên bản: OSB API v2.17

Binding rotation được bổ sung trong OSB API v2.17. Các trường liên quan gồm:

| Thành phần | Trường | Ý nghĩa |
|---|---|---|
| Catalog, Service Plan | binding_rotatable | Công bố plan có hỗ trợ tạo successor binding hay không |
| Request tạo binding | predecessor_binding_id | Chỉ ra ID của binding tiền nhiệm |
| Binding response metadata | expires_at | Thời điểm binding hết hiệu lực |
| Binding response metadata | renew_before | Thời điểm nên bắt đầu tạo binding mới |

Các trường này là phần mở rộng cộng thêm của phiên bản v2.17. Broker và platform sử dụng phiên bản cũ có thể không hiểu hoặc không gửi chúng. Vì vậy:

1. Platform phải gửi header phiên bản OSB API phù hợp, ví dụ **X-Broker-API-Version: 2.17**.
2. Broker phải hỗ trợ v2.17 và nhận diện đúng các trường rotation.
3. Catalog chỉ khai báo binding_rotatable khi handler và provider thực sự triển khai được quy trình.
4. Nếu platform không hỗ trợ v2.17, không được giả định platform có thể yêu cầu rotation bằng predecessor_binding_id.
5. Nếu phiên bản Spring Cloud Open Service Broker đang dùng chưa ánh xạ các trường này, cần nâng lên phiên bản có hỗ trợ hoặc triển khai tương thích theo cơ chế được framework cho phép trước khi công bố capability.

Spring Cloud Open Service Broker 5.2.0 công bố hỗ trợ OSB API v2.17, trong đó có binding_rotatable, predecessor_binding_id và renew_before. Không nên suy ra phiên bản dependency của một dự án chỉ từ tên module; hãy kiểm tra dependency thực tế và tài liệu đúng phiên bản trước khi bật tính năng.

### Catalog phải công bố capability theo từng plan

Trong OSB API v2.17, binding_rotatable là trường của Service Plan. Giá trị mặc định là false. Nếu trường không có hoặc là false, platform MUST NOT yêu cầu rotation cho binding của plan đó.

Ví dụ catalog rút gọn:

~~~json
{
  "services": [
    {
      "id": "managed-postgres",
      "name": "managed-postgres",
      "description": "PostgreSQL được quản lý",
      "bindable": true,
      "plans": [
        {
          "id": "postgres-standard",
          "name": "standard",
          "description": "Database tiêu chuẩn",
          "binding_rotatable": true
        },
        {
          "id": "postgres-legacy",
          "name": "legacy",
          "description": "Database dùng cơ chế credentials cũ",
          "binding_rotatable": false
        }
      ]
    }
  ]
}
~~~

Catalog chỉ nên đặt binding_rotatable thành true khi broker có thể tạo successor, duy trì predecessor, xử lý unbind độc lập và phục hồi được các lỗi giữa chừng. Việc provider có API tạo user mới chưa đủ để công bố capability nếu broker chưa quản lý được quan hệ hai binding và thời gian overlap.

## 3. Request tạo successor với predecessor_binding_id

Platform sử dụng endpoint tạo binding hiện có, nhưng gửi binding ID mới trên URL và predecessor_binding_id trong request body.

~~~http
PUT /v2/service_instances/instance-42/service_bindings/binding-101
Content-Type: application/json
X-Broker-API-Version: 2.17
~~~

Request rotation minh họa:

~~~json
{
  "service_id": "managed-postgres",
  "plan_id": "postgres-standard",
  "predecessor_binding_id": "binding-100",
  "bind_resource": {
    "app_guid": "app-orders"
  },
  "context": {
    "platform": "cloud-foundry",
    "organization_guid": "org-commerce",
    "space_guid": "space-production"
  }
}
~~~

Ở ví dụ này:

- **instance-42** là service instance đã provision.
- **binding-101** là ID mới dành cho successor.
- **binding-100** là predecessor được tham chiếu.
- **predecessor_binding_id** phải trỏ đến một binding chưa hết hạn thuộc chính service instance đó.
- Request vẫn xác định service_id và plan_id theo hợp đồng tạo binding.
- Platform có thể không gửi lại các parameters cũ vì broker có thể lấy cấu hình từ predecessor đã lưu.

Binding ID mới phải là định danh không rỗng và duy nhất theo yêu cầu OSB API. Không dùng lại ID của predecessor cho successor, vì hai binding phải tồn tại riêng biệt để platform có thể unbind từng binding.

### predecessor_binding_id không phải binding ID cần cập nhật

Trường này không yêu cầu broker ghi đè predecessor. Nó chỉ định binding cũ làm nguồn tham chiếu cho quá trình tạo successor. Broker phải giữ bản ghi cũ và tạo một bản ghi binding mới có quan hệ rõ ràng.

Không được hiểu request rotation là lệnh thu hồi binding cũ. Việc unbind predecessor là một thao tác riêng do platform gửi sau khi chuyển đổi hoặc khi binding cũ hết hạn.

## 4. Điều kiện kiểm tra predecessor

Trước khi tạo successor, broker cần xác minh predecessor một cách đầy đủ.

| Điều kiện | Cách kiểm tra |
|---|---|
| Predecessor tồn tại | Tra cứu binding theo instance ID và predecessor_binding_id |
| Cùng service instance | predecessor.instanceId phải bằng instanceId trong URL |
| Chưa hết hạn | Kiểm tra expires_at và trạng thái hiệu lực tại thời điểm xử lý |
| Có thể sử dụng làm predecessor | Không ở trạng thái REVOKED, REVOKING hoặc FAILED không thể phục hồi |
| Plan hỗ trợ rotation | Catalog của plan đang dùng khai báo binding_rotatable=true |
| Successor ID mới | binding_id mới khác predecessor ID và chưa được dùng |
| Request được phép | Platform đã xác thực; tenant và consumer thuộc phạm vi instance |
| Không có rotation xung đột | Không có operation không tương thích đang chạy trên predecessor hoặc instance |

OSB API yêu cầu predecessor là binding chưa hết hạn của cùng service instance. Các kiểm tra bổ sung như predecessor phải ở trạng thái ACTIVE, chỉ cho phép một successor đang chờ hoặc cấm rotation đồng thời là policy nội bộ nên broker cần tài liệu hóa.

Nếu predecessor không tồn tại, thuộc instance khác hoặc đã hết hạn, broker không được tạo successor dựa trên tham chiếu đó. Trả lỗi phù hợp với hợp đồng và không thực hiện side effect ở provider.

### Xác minh dữ liệu authoritative

Không chỉ dựa vào dữ liệu predecessor_binding_id trong request. Broker phải đọc bản ghi predecessor từ kho trạng thái của mình và đối chiếu với provider khi cần.

Các dữ liệu quan trọng gồm:

- service instance và provider resource ID.
- service ID, plan ID và consumer scope.
- parameters đã được chuẩn hóa.
- quyền hoặc role đã cấp.
- provider binding ID.
- secret reference.
- expires_at và renew_before.
- trạng thái binding và operation hiện tại.

Không cần trả secret của predecessor cho platform chỉ để tạo successor. Broker dùng dữ liệu nội bộ và provider adapter để cấp một credential mới.

## 5. Kế thừa cấu hình từ predecessor

Một mục đích quan trọng của predecessor_binding_id là giúp broker biết cần kế thừa cấu hình nào khi platform không lưu lại parameters ban đầu.

Ví dụ predecessor được tạo với:

~~~json
{
  "database_name": "orders",
  "role": "read-write",
  "connection_limit": 30,
  "tls_required": true
}
~~~

Khi rotation, platform có thể chỉ gửi predecessor_binding_id. Broker đọc cấu hình đã lưu và tạo successor với cùng database, role, giới hạn kết nối và chính sách TLS.

Kế thừa cấu hình cần tuân theo các nguyên tắc:

1. Chỉ kế thừa parameters thuộc binding và được phép dùng lại.
2. Kiểm tra lại cấu hình theo policy hiện tại của service và plan.
3. Không kế thừa password, access token hoặc private key cũ như một credential mới.
4. Sinh hoặc yêu cầu provider cấp secret mới.
5. Giữ nguyên consumer scope nếu request rotation vẫn dành cho consumer đó.
6. Ghi nhận rõ trường nào được kế thừa và trường nào thay đổi theo policy.
7. Nếu cấu hình cũ không còn hợp lệ, từ chối rotation có lý do hoặc yêu cầu quy trình migration riêng.

Không nên lưu nguyên request body chứa secret hoặc dữ liệu nhạy cảm chỉ để phục vụ kế thừa. Lưu cấu hình đã chuẩn hóa và tham chiếu secret riêng. Nếu parameters chứa dữ liệu không cần thiết sau khi tạo binding, có thể loại bỏ theo chính sách dữ liệu.

### Chuyển trạng thái gắn với binding

Một số provider có metadata hoặc trạng thái riêng cho từng binding, chẳng hạn quyền truy cập theo schema, subscription, role hoặc policy. Broker cần quyết định trạng thái nào được chuyển sang successor.

Ví dụ:

- Role và phạm vi quyền có thể được tái tạo tương đương.
- Consumer identity có thể được giữ nguyên.
- Credential phải được sinh mới.
- Thời hạn và thời điểm gia hạn được tính lại.
- Audit history của predecessor vẫn giữ nguyên.
- Provider binding ID của successor phải là ID mới.

Không chuyển quyền quản trị rộng hơn chỉ vì predecessor từng có quyền đó. Successor phải được đánh giá theo policy và quyền tối thiểu tại thời điểm rotation.

## 6. Hai binding phải hoạt động song song

Quy tắc cốt lõi của binding rotation là predecessor và successor đều phải hợp lệ song song cho đến khi chúng hết hạn hoặc bị xóa.

Luồng chuyển đổi:

~~~mermaid
sequenceDiagram
    participant Platform
    participant Broker
    participant Provider
    participant App as Application

    Platform->>Broker: PUT successor + predecessor_binding_id
    Broker->>Broker: Validate predecessor and reserve successor
    Broker->>Provider: Create new principal/credential
    Provider-->>Broker: New credential and provider binding ID
    Broker->>Broker: Persist successor and predecessor link
    Broker-->>Platform: 201 Created + successor credentials
    Platform->>App: Deliver successor credentials
    App->>Provider: Connect with successor credentials
    App-->>Platform: New connection verified
    Platform->>Broker: DELETE predecessor binding
    Broker->>Provider: Revoke predecessor principal
    Provider-->>Broker: Revocation confirmed
    Broker-->>Platform: 200 OK
~~~

Trình tự có thể thay đổi theo nền tảng và service, nhưng nguyên tắc overlap phải được giữ:

- Không thu hồi predecessor ngay khi tạo successor.
- Successor cần có credentials và endpoint đủ để consumer sử dụng.
- Platform hoặc ứng dụng có thời gian chuyển sang successor.
- Platform có thể kiểm tra kết nối mới trước khi unbind predecessor.
- Unbind predecessor chỉ thu hồi quyền thuộc predecessor.
- Successor tiếp tục hoạt động độc lập sau khi predecessor bị xóa.

Ví dụ với PostgreSQL, broker nên tạo role mới, cấp cùng phạm vi quyền cần thiết và trả password mới. Khi ứng dụng đã dùng role mới, platform gửi unbind cho binding cũ để broker xóa role cũ. Nếu broker đổi password trên cùng một role, credentials cũ có thể mất hiệu lực trước khi ứng dụng chuyển đổi xong, làm mất lợi ích của rotation.

### Không xóa predecessor khi successor vừa được tạo

Thời điểm tạo successor thành công không chứng minh ứng dụng đã chuyển sang credentials mới. Broker không thể tự suy luận platform đã cập nhật secret hoặc workload.

Hãy giữ predecessor cho đến khi nhận unbind hoặc đến thời điểm hết hạn theo metadata. Nếu platform gặp lỗi khi cập nhật consumer, credentials cũ vẫn còn hiệu lực và có thể duy trì hoạt động trong khoảng overlap đã cam kết.

## 7. expires_at và renew_before

OSB API v2.17 bổ sung hai trường metadata để hỗ trợ vòng đời binding:

- **expires_at**: thời điểm binding hết hiệu lực và không nên hoặc không thể tiếp tục sử dụng.
- **renew_before**: thời điểm nên bắt đầu tạo binding mới.

Ví dụ response metadata:

~~~json
{
  "metadata": {
    "expires_at": "2027-03-31T00:00:00.0Z",
    "renew_before": "2027-03-24T00:00:00.0Z"
  },
  "credentials": {
    "username": "orders_app_v2",
    "password": "new-secret-value",
    "host": "db.example.internal",
    "port": 5432,
    "database": "orders"
  }
}
~~~

Các timestamp phải tuân theo định dạng ISO 8601 mà OSB API quy định. Nếu cả hai trường có mặt, renew_before phải trước hoặc bằng expires_at. Broker nên chừa đủ thời gian giữa hai mốc để platform tạo successor, triển khai credentials mới và xử lý sự cố chuyển đổi.

Ví dụ, nếu binding hết hạn sau 30 ngày, broker có thể đề nghị rotation trước 7 ngày. Đây chỉ là chính sách minh họa; khoảng thời gian thực tế cần dựa vào SLA, thời gian triển khai ứng dụng và khả năng provider.

Platform có thể dùng renew_before để khởi động rotation tự động. Broker cần trả metadata nhất quán khi tạo hoặc fetch binding nếu có hỗ trợ. Khi successor được tạo, metadata của successor phải phản ánh thời hạn mới; không sao chép expires_at cũ nếu provider đã cấp credential mới với vòng đời khác.

Metadata phục vụ quản lý binding, không phải nơi chứa dữ liệu kết nối. Credentials vẫn nằm trong trường credentials của response.

## 8. Xử lý đồng bộ và bất đồng bộ khi rotation

Rotation dùng endpoint tạo binding, do đó tuân theo cơ chế phản hồi create binding của OSB API v2.17.

### Xử lý đồng bộ

Nếu provider tạo successor ngay:

1. Broker xác thực predecessor.
2. Broker reserve binding ID mới.
3. Provider tạo credential mới.
4. Broker lưu secret và liên kết predecessor/successor.
5. Broker trả HTTP 201 Created cùng response binding.

Nếu cùng binding ID và cùng yêu cầu đã hoàn tất trước đó, broker có thể trả HTTP 200 OK theo quy tắc request lặp đồng bộ. Nếu cùng ID nhưng parameters hoặc predecessor khác, trả HTTP 409 Conflict.

### Xử lý bất đồng bộ

OSB API v2.17 hỗ trợ asynchronous binding. Platform gửi query parameter accepts_incomplete=true nếu có thể xử lý thao tác bất đồng bộ.

Ví dụ:

~~~http
PUT /v2/service_instances/instance-42/service_bindings/binding-101?accepts_incomplete=true
X-Broker-API-Version: 2.17
~~~

Nếu provider cần thời gian để tạo user hoặc credential, broker có thể:

1. Reserve successor binding và tạo operation.
2. Ghi predecessor ID, successor ID và fingerprint.
3. Đưa công việc vào outbox hoặc worker.
4. Trả HTTP 202 Accepted cùng operation ID.
5. Worker tạo tài nguyên tại provider và lưu credentials.
6. Platform poll endpoint last operation của binding.
7. Khi operation thành công, platform có thể fetch binding nếu broker công bố bindings_retrievable, hoặc nhận dữ liệu binding theo cơ chế được đặc tả.

Endpoint polling có dạng:

~~~http
GET /v2/service_instances/instance-42/service_bindings/binding-101/last_operation?service_id=managed-postgres&plan_id=postgres-standard&operation=rotate-101
X-Broker-API-Version: 2.17
~~~

Response 202 không được chứa credentials hoặc thông tin binding. Broker chỉ trả operation identifier. Khi thao tác hoàn tất, response last operation báo trạng thái succeeded hoặc failed theo hợp đồng.

Nếu broker chỉ có thể tạo binding bất đồng bộ nhưng request không có accepts_incomplete=true, broker phải trả HTTP 422 Unprocessable Entity với error code AsyncRequired.

### Retry trong lúc operation đang chạy

Nếu platform gửi lại cùng PUT trong khi successor vẫn đang tạo, broker phải trả HTTP 202 Accepted với cùng operation identifier. Không trả HTTP 200 như thể binding đã hoàn tất.

Nếu request lặp có cùng binding ID nhưng predecessor_binding_id hoặc parameters khác, broker trả HTTP 409 Conflict. Không tạo operation thứ hai cho cùng successor ID.

Predecessor phải tiếp tục hợp lệ trong toàn bộ thời gian successor đang được tạo. Nếu predecessor sắp hết hạn, broker cần có chính sách xử lý phù hợp, chẳng hạn ưu tiên hoàn tất rotation trong buffer thời gian đã công bố hoặc báo lỗi có thể xử lý. Không giả định rằng một operation đang chạy tự động kéo dài thời hạn của predecessor.

## 9. Idempotency và kiểm soát rotation đồng thời

Rotation tạo một binding mới, vì vậy broker phải bảo đảm request lặp không tạo ra nhiều successor hoặc nhiều credential.

Fingerprint của rotation nên bao gồm:

- instanceId.
- successor bindingId.
- predecessorBindingId.
- serviceId và planId.
- consumer identity hoặc bind_resource đã chuẩn hóa.
- parameters override nếu request có gửi.
- các context field thực sự ảnh hưởng đến cấu hình hoặc quyền.

Không đưa request timestamp, trace ID hoặc correlation ID thay đổi theo mỗi lần retry vào fingerprint.

Quy tắc:

| Tình huống | Hành vi |
|---|---|
| Successor ID chưa tồn tại, predecessor hợp lệ | Reserve và bắt đầu rotation |
| Successor đang tạo, cùng fingerprint | Trả cùng operation ID nếu bất đồng bộ |
| Successor đã ACTIVE, cùng request | Trả kết quả successor hiện có |
| Successor ID đã tồn tại, predecessor khác | Trả 409 Conflict |
| Predecessor không tồn tại hoặc đã hết hạn | Từ chối, không tạo provider resource |
| Hai successor khác nhau cùng tham chiếu một predecessor | Áp dụng policy chống fork; thường chỉ cho phép một rotation đang hoạt động |
| Unbind predecessor đang chạy khi rotation chưa hoàn tất | Xử lý concurrency theo policy, không làm successor mất nguồn cấu hình |
| Provider timeout sau khi tạo credential | Reconcile theo external reference trước khi tạo lại |

Dùng unique constraint trên cặp instanceId và successorBindingId. Có thể bổ sung ràng buộc nội bộ để ngăn nhiều successor đang chờ cùng một predecessor. Nếu cho phép nhiều successor, broker cần định nghĩa rõ use case và cách quản lý quyền, vì việc tạo nhiều credential cùng kế thừa một predecessor có thể mở rộng bề mặt truy cập ngoài ý muốn.

Không giữ database lock trong suốt lời gọi provider. Hãy reserve successor trong transaction ngắn, lưu operation bền vững và dùng version hoặc lease để ngăn worker xử lý trùng.

## 10. Xử lý lỗi và rollback an toàn

Rotation cần giữ predecessor hoạt động cho đến khi successor đã sẵn sàng. Nếu tạo successor thất bại, broker không được làm mất quyền truy cập đang được ứng dụng sử dụng.

| Lỗi | Cách xử lý |
|---|---|
| predecessor không tồn tại | Từ chối trước khi gọi provider |
| predecessor thuộc instance khác | Từ chối request |
| predecessor đã hết hạn hoặc bị revoke | Từ chối rotation |
| plan không khai báo binding_rotatable | Platform không được yêu cầu rotation; broker từ chối nếu nhận request trái capability |
| successor ID đã được dùng với request khác | Trả 409 Conflict |
| Provider từ chối tạo credential | Đánh dấu operation thất bại, giữ predecessor |
| Provider timeout, kết quả chưa rõ | Tra cứu theo external reference trước khi retry |
| Secret manager lỗi sau khi provider tạo credential | Khôi phục secret hoặc revoke successor vừa tạo theo quy trình bù trừ |
| Broker restart giữa operation | Worker phục hồi từ operation record |
| Platform chưa chuyển sang successor | Giữ predecessor hoạt động đến unbind hoặc hết hạn |
| Unbind predecessor thất bại | Giữ trạng thái thu hồi và retry; successor tiếp tục độc lập |

Rollback cần giới hạn vào successor mới. Không được xóa hoặc thay đổi predecessor chỉ vì successor thất bại.

Nếu provider tạo credential nhưng broker chưa lưu được kết quả, trạng thái phải được đánh dấu UNKNOWN hoặc NEEDS_RECONCILIATION. Worker tra cứu provider bằng external reference gắn với successor ID. Nếu resource tồn tại, tiếp tục lưu secret; nếu không tồn tại, có thể retry bằng idempotency key ổn định. Nếu không thể khôi phục credentials, revoke successor đã tạo và giữ predecessor.

## 11. Mô hình dữ liệu predecessor và successor

Một bản ghi binding nên có các trường để truy vết quan hệ:

| Thuộc tính | Mục đích |
|---|---|
| bindingId | ID của binding hiện tại |
| instanceId | Service instance sở hữu binding |
| predecessorBindingId | ID binding tiền nhiệm, có thể rỗng với binding đầu tiên |
| successorBindingId | ID successor gần nhất nếu đã tạo |
| rotationSequence | Số thứ tự thế hệ trong chuỗi rotation |
| state | RESERVED, CREATING, ACTIVE, REVOKING, REVOKED, EXPIRED hoặc trạng thái nội bộ |
| providerBindingId | ID principal/resource tại provider |
| credentialSecretRef | Tham chiếu secret riêng |
| expiresAt | Thời điểm hết hạn |
| renewBefore | Thời điểm nên bắt đầu rotation |
| requestFingerprint | Dùng nhận diện retry |
| operationId | Operation tạo successor nếu chạy bất đồng bộ |
| createdAt, updatedAt | Thời điểm cập nhật |

Quan hệ có thể hình dung:

~~~mermaid
flowchart LR
    B1["binding-100<br/>predecessor"] --> B2["binding-101<br/>successor"]
    B2 --> B3["binding-205<br/>successor tiếp theo"]
    B1 -. "unbound/expired" .-> X1["REVOKED hoặc EXPIRED"]
    B2 -. "unbound/expired" .-> X2["REVOKED hoặc EXPIRED"]
~~~

Mỗi binding giữ lịch sử riêng. Không xóa record predecessor ngay khi successor hoạt động, vì broker vẫn cần xử lý unbind, retry, audit và đối soát.

Nếu một binding đã có successor, broker nên lưu quan hệ để tránh tạo chuỗi hoặc nhánh không mong muốn. Một policy phổ biến là chỉ cho phép một successor đang hoạt động hoặc đang tạo tại một thời điểm cho mỗi predecessor. Policy này giúp quá trình rotation dễ kiểm soát hơn.

## 12. Thiết kế BindingRotationCoordinator trong Spring

Trong ứng dụng Spring Cloud Open Service Broker, handler create binding tiếp nhận request và chuyển phần nghiệp vụ sang coordinator. Coordinator chịu trách nhiệm kiểm tra predecessor, reserve successor, kế thừa cấu hình, gọi provider và tạo response.

Một command nội bộ có thể mô hình hóa:

~~~java
public record BindingRotationCommand(
    String instanceId,
    String successorBindingId,
    String predecessorBindingId,
    String serviceId,
    String planId,
    String consumerId,
    Map<String, Object> parameterOverrides,
    String idempotencyKey
) {}
~~~

Một kết quả nội bộ:

~~~java
public record BindingRotationResult(
    boolean asynchronous,
    String operationId,
    Map<String, Object> credentials,
    Instant expiresAt,
    Instant renewBefore
) {}
~~~

Các model trên là abstraction của ứng dụng, không phải kiểu dữ liệu chuẩn bắt buộc của framework.

Coordinator có thể triển khai theo luồng khái niệm:

~~~java
@Service
public class BindingRotationCoordinator {

    private final BindingRepository bindings;
    private final RotationPolicy rotationPolicy;
    private final BindingConfigurationResolver configurationResolver;
    private final ProviderBindingAdapter provider;
    private final SecretStore secretStore;
    private final OperationRepository operations;

    public Mono<BindingRotationResult> rotate(
            BindingRotationCommand command) {

        return bindings.findPredecessor(
                    command.instanceId(),
                    command.predecessorBindingId())
            .switchIfEmpty(Mono.error(
                new PredecessorBindingNotFoundException()))
            .flatMap(predecessor ->
                rotationPolicy.validate(command, predecessor)
                    .then(configurationResolver.resolve(
                        predecessor,
                        command.parameterOverrides()))
                    .flatMap(configuration ->
                        bindings.reserveSuccessor(
                                command, predecessor, configuration)
                            .flatMap(reservation ->
                                executeOrReplay(
                                    reservation, configuration))
                    )
            );
    }

    private Mono<BindingRotationResult> executeOrReplay(
            RotationReservation reservation,
            BindingConfiguration configuration) {
        if (reservation.isExisting()) {
            return replayExisting(reservation);
        }

        return provider.createSuccessor(
                reservation.command(),
                configuration)
            .flatMap(providerBinding ->
                secretStore.store(
                        reservation.successorBindingId(),
                        providerBinding.credentials())
                    .flatMap(secretRef ->
                        bindings.markActive(
                            reservation,
                            providerBinding.providerBindingId(),
                            secretRef,
                            providerBinding.expiresAt(),
                            providerBinding.renewBefore())
                    )
                    .thenReturn(
                        resultFrom(providerBinding))
            );
    }
}
~~~

Đây là skeleton minh họa luồng xử lý; tên getter, repository và API cụ thể cần được điều chỉnh theo phiên bản dependency. Trong production cần bổ sung xử lý lỗi, transaction reserve, provider timeout, operation bất đồng bộ, retry và reconciliation.

### Handler không nên tự quản lý toàn bộ rotation

Handler của ServiceInstanceBindingService chỉ nên:

1. Nhận CreateServiceInstanceBindingRequest.
2. Ánh xạ các trường chuẩn sang command nội bộ, bao gồm predecessorBindingId nếu phiên bản framework hỗ trợ.
3. Gọi BindingRotationCoordinator khi request có predecessor.
4. Gọi luồng create binding thông thường khi không có predecessor.
5. Ánh xạ kết quả sang response theo hợp đồng OSB API.

Nếu phiên bản framework chưa có model field predecessorBindingId, không nên giả định builder hoặc getter đã tồn tại. Cần nâng phiên bản Spring Cloud Open Service Broker có hỗ trợ v2.17 hoặc dùng cơ chế mở rộng tương thích được tài liệu hóa. Không tự parse JSON rồi bỏ qua version header hoặc contract validation của framework.

## 13. Provider adapter và chiến lược cấp credentials mới

Provider adapter cần hiểu loại service và cách tạo successor an toàn.

### Với database

Một chiến lược phổ biến:

1. Tạo database role mới cho successor.
2. Cấp cùng quyền cần thiết trên database hoặc schema.
3. Sinh password mới bằng nguồn ngẫu nhiên mật mã.
4. Lưu credential mới trong secret manager.
5. Giữ role cũ cho predecessor.
6. Sau khi nhận unbind predecessor, thu hồi role cũ.

Không đổi password của role cũ ngay khi tạo successor nếu điều đó làm predecessor mất hiệu lực.

### Với message broker

Có thể tạo user mới, cấp quyền trên cùng vhost hoặc topic scope, kiểm tra kết nối mới rồi thu hồi user cũ khi unbind. Không dùng chung admin user cho cả hai binding.

### Với object storage hoặc API token

Provider có thể tạo access key hoặc token mới, giới hạn bucket/action/resource tương ứng và đặt expiration. Khi predecessor bị unbind, revoke key cũ. Nếu provider hỗ trợ hai key đồng thời, hãy dùng khoảng overlap để consumer cập nhật an toàn.

### Adapter cần trả metadata rõ ràng

ProviderBindingResult có thể chứa:

- providerBindingId mới.
- credentials mới hoặc secret reference.
- expiresAt và renewBefore.
- endpoint liên quan.
- operation ID của provider nếu cần theo dõi.
- trạng thái xác nhận tạo principal.

Không log credentials. Nếu provider chỉ hiển thị secret một lần, phải lưu secret an toàn trước khi đánh dấu successor ACTIVE hoặc trả response đầu tiên.

## 14. Bảo mật trong thời gian overlap

Trong thời gian hai binding cùng hợp lệ, số credentials có thể sử dụng để truy cập service tăng lên. Broker cần kiểm soát khoảng overlap và quyền của từng binding.

- Mỗi binding có principal hoặc token riêng nếu provider hỗ trợ.
- Successor chỉ nhận quyền cần thiết, không tự động được nâng quyền.
- Predecessor vẫn hoạt động nhưng không được kéo dài quá thời hạn policy.
- Ghi nhận expires_at và renew_before chính xác.
- Giới hạn thời gian overlap theo SLA và khả năng triển khai của ứng dụng.
- Khi unbind predecessor, revoke ở provider và xác nhận kết quả.
- Không xóa secret cũ trước khi quyền cũ được thu hồi nếu cần dùng để đối soát.
- Không trả credentials predecessor trong response successor.
- Audit sự kiện tạo successor, đọc secret, unbind và revoke.

Nếu predecessor bị lộ hoặc cần thu hồi khẩn cấp, policy có thể yêu cầu revoke ngay thay vì duy trì overlap. Tuy nhiên, đó là quy trình khẩn cấp riêng và có thể gây gián đoạn cho consumer. Không nên nhầm xử lý khẩn cấp với rotation thông thường.

## 15. Kiểm thử binding rotation

Kiểm thử cần xác nhận hợp đồng v2.17, quan hệ predecessor/successor và side effect thực tế tại provider.

| Trường hợp | Kết quả mong đợi |
|---|---|
| Plan có binding_rotatable=true | Platform có thể gửi yêu cầu rotation |
| Plan không có field hoặc false | Không công bố hỗ trợ rotation |
| predecessor tồn tại, chưa hết hạn, cùng instance | Cho phép tạo successor |
| predecessor thuộc instance khác | Từ chối trước side effect |
| predecessor đã hết hạn hoặc revoked | Từ chối |
| Successor có binding ID mới | Tạo record riêng và liên kết predecessor |
| Parameters không được gửi lại | Broker kế thừa cấu hình hợp lệ từ predecessor |
| Credential successor | Được sinh mới, không tái sử dụng secret cũ |
| Successor tạo thành công | Cả predecessor và successor đều còn hợp lệ |
| Unbind predecessor | Chỉ thu hồi predecessor, successor vẫn hoạt động |
| Request lặp cùng successor ID | Trả kết quả hoặc operation hiện có |
| Cùng successor ID nhưng predecessor khác | Trả 409 Conflict |
| Hai rotation cùng predecessor | Policy concurrency ngăn nhánh successor không mong muốn |
| Provider timeout | Reconcile trước khi tạo lại |
| Provider tạo credential nhưng secret store lỗi | Khôi phục hoặc revoke successor bù trừ |
| Async rotation với accepts_incomplete=true | Trả 202 và operation ID; không trả credentials trong response 202 |
| Retry khi operation đang chạy | Trả 202 cùng operation ID |
| Async rotation không được client chấp nhận | Trả 422 AsyncRequired nếu chỉ có thể xử lý async |
| renew_before và expires_at | Đúng định dạng, renew_before không sau expires_at |
| Log và trace | Không chứa credentials hoặc token |

Nên có contract test kiểm tra catalog serialization, X-Broker-API-Version, request body predecessor_binding_id, status code và last-operation polling. Integration test cần mô phỏng provider tạo hai principal đồng thời, xác nhận cả hai hoạt động trong overlap và chỉ principal cũ bị revoke khi unbind predecessor.

## 16. Những lỗi triển khai thường gặp

**Bật binding_rotatable khi provider chưa hỗ trợ overlap.** Nếu tạo successor làm credential cũ mất hiệu lực ngay, ứng dụng có thể bị gián đoạn. Hãy kiểm tra khả năng tạo principal độc lập hoặc nhiều key đồng thời.

**Dùng lại binding ID cũ.** Successor phải có ID mới để platform quản lý hai binding riêng biệt.

**Xem predecessor_binding_id là lệnh unbind.** Trường này chỉ xác định binding tiền nhiệm. Unbind là request riêng.

**Không kiểm tra predecessor thuộc cùng instance.** Điều này có thể tạo quan hệ binding sai tenant hoặc sai tài nguyên. Luôn tra cứu theo cả instanceId và predecessorBindingId.

**Yêu cầu platform gửi lại toàn bộ parameters cũ.** Một mục đích của rotation là broker có thể lấy cấu hình từ predecessor. Hãy lưu cấu hình cần thiết một cách an toàn và có thể truy xuất.

**Sao chép credentials cũ sang successor.** Rotation phải cấp credential mới; nếu chỉ trả lại secret cũ thì không đạt mục đích thay thế credentials.

**Thu hồi predecessor ngay sau khi tạo successor.** Platform và ứng dụng có thể chưa cập nhật xong. Duy trì overlap theo hợp đồng.

**Không xử lý async binding đúng OSB API.** Nếu binding tạo lâu, dùng accepts_incomplete, operation ID và last-operation endpoint theo phiên bản hỗ trợ. Không trả credentials trong response 202.

**Không giữ lịch sử quan hệ.** Xóa predecessor record quá sớm làm mất khả năng xử lý unbind, retry, audit và đối soát.

## 17. Nguyên tắc triển khai trong Spring Cloud Service Broker

Trong Spring Cloud Open Service Broker, chỉ công bố binding_rotatable khi dependency và nền tảng cùng hỗ trợ OSB API v2.17. Catalog phải phản ánh đúng khả năng của từng Service Plan. Khi request có predecessor_binding_id, handler chuyển sang BindingRotationCoordinator để xác minh predecessor, kế thừa cấu hình, reserve successor, tạo credentials mới và lưu quan hệ hai binding.

Broker cần giữ predecessor và successor hoạt động song song cho đến khi binding cũ hết hạn hoặc bị xóa. Việc unbind predecessor phải thu hồi đúng provider principal cũ, không ảnh hưởng successor. Metadata expires_at và renew_before giúp platform lập lịch rotation trước khi credentials hết hạn. Với thao tác dài, dùng cơ chế asynchronous binding của OSB API v2.17 và lưu operation bền vững.

Idempotency, unique constraint, provider adapter và secret manager là các phần cần có để xử lý retry và sự cố giữa chừng. Khi successor thất bại, giữ predecessor hoạt động và reconcile tài nguyên mới trước khi thử lại. Cách triển khai này tạo ra một chuỗi binding có thể truy vết, chuyển đổi credentials có kiểm soát và giảm nguy cơ gián đoạn cho ứng dụng.

## Tài liệu đối chiếu

- [Open Service Broker API specification – Binding Rotation](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#binding-rotation)
- [Spring Cloud Open Service Broker releases – v5.2.0, OSB API v2.17 support](https://github.com/spring-cloud/spring-cloud-open-service-broker/releases)

