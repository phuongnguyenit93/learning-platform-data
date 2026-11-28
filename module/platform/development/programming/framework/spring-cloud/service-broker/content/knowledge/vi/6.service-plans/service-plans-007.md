# maintenance_info và yêu cầu bảo trì phụ thuộc phiên bản giao thức

## Bối cảnh

Một service broker theo Open Service Broker API (OSB API) công bố các service và service plan trong catalog. Plan mô tả gói dịch vụ mà Platform có thể cung cấp cho người dùng, chẳng hạn database tiêu chuẩn, database hiệu năng cao hoặc một cụm cache có dung lượng xác định. Sau khi instance được cấp phát, nhà cung cấp có thể cần đưa ra bản bảo trì mới: cập nhật hệ điều hành, vá lỗ hổng, nâng phiên bản engine hoặc thay đổi cấu hình vận hành.

OSB API có trường `maintenance_info` trong đối tượng service plan để broker công bố phiên bản bảo trì hiện có. Platform có thể dùng thông tin đó để nhận biết instance đang chạy phiên bản bảo trì cũ và điều phối thao tác cập nhật. Khi gửi yêu cầu cập nhật, Platform có thể cung cấp thông tin bảo trì trước đó trong `previous_values`, giúp broker xác định trạng thái mà instance đang có.

Tính năng này liên quan đến hai loại phiên bản độc lập:

- **Phiên bản bảo trì của plan** nằm trong `maintenance_info.version`, mô tả phiên bản phần mềm hoặc cấu hình dịch vụ mà broker đang cung cấp.
- **Phiên bản giao thức OSB API** nằm trong header `X-Broker-API-Version`, mô tả hợp đồng HTTP mà Platform dùng để gọi broker.

Broker phải xử lý cả hai thông tin một cách nhất quán. `maintenance_info.version` không thay thế `X-Broker-API-Version`; một giá trị là phiên bản dịch vụ, giá trị còn lại là phiên bản giao thức tích hợp.

## 1. `maintenance_info` trong service plan

`maintenance_info` là một đối tượng metadata tùy chọn trong service plan của catalog. Khi broker cung cấp thông tin bảo trì, đối tượng này mô tả phiên bản bảo trì hiện tại và có thể kèm mô tả thân thiện với người vận hành.

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa | Lưu ý |
|---|---|---|
| `version` | Định danh phiên bản bảo trì của plan | Là trường quan trọng để Platform nhận biết có bản bảo trì mới |
| `description` | Mô tả ngắn về nội dung hoặc mục đích của bản bảo trì | Dùng để hiển thị hoặc hỗ trợ người vận hành; không chứa bí mật |

Ví dụ catalog response rút gọn:

~~~json
{
  "services": [
    {
      "id": "postgres-service",
      "name": "postgres",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plans": [
        {
          "id": "postgres-standard",
          "name": "standard",
          "description": "PostgreSQL database for general workloads",
          "free": false,
          "maintenance_info": {
            "version": "14.8.2",
            "description": "Security and reliability maintenance release"
          }
        }
      ]
    }
  ]
}
~~~

Trong ví dụ, `14.8.2` là phiên bản bảo trì do broker công bố cho plan `postgres-standard`. Nó có thể biểu diễn phiên bản engine, bản phát hành image hoặc một mã phiên bản bảo trì được broker quản lý. Ý nghĩa cụ thể phải nhất quán trong toàn bộ vòng đời của plan.

Nếu broker không có thông tin bảo trì để công bố, không cần tự tạo một giá trị giả. Có thể bỏ trường `maintenance_info` theo schema của OSB API mà broker triển khai. Khi trường này được công bố, `version` phải có giá trị hợp lệ theo hợp đồng; `description` có thể được dùng để giải thích thay đổi.

### Quy tắc quản lý phiên bản bảo trì

Một giá trị `maintenance_info.version` nên nhận diện duy nhất một bản bảo trì có ý nghĩa. Khi có bản phát hành mới cần áp dụng cho các instance đang chạy, broker cập nhật giá trị trong catalog. Nên sử dụng quy ước phiên bản rõ ràng, có thứ tự và đáp ứng định dạng mà phiên bản OSB API đang hỗ trợ; Semantic Versioning là lựa chọn dễ hiểu khi bản phát hành có cấu trúc major/minor/patch.

Ví dụ chuỗi thay đổi:

| Thời điểm | `maintenance_info.version` | Mô tả |
|---|---|---|
| Ban đầu | `14.8.1` | Bản engine và image đang triển khai |
| Có bản vá | `14.8.2` | Vá lỗi bảo mật và cập nhật chứng thư |
| Có nâng cấp tương thích | `14.9.0` | Bổ sung bản vá và thay đổi cấu hình mặc định |

Không thay đổi `version` chỉ vì mô tả được viết lại hoặc catalog được triển khai lại. Ngược lại, khi nội dung bảo trì thực sự thay đổi và broker muốn Platform nhận biết một bản mới, cần cập nhật version theo quy ước đã thống nhất. Tránh tái sử dụng version cũ cho nội dung khác vì Platform có thể không phát hiện được bản phát hành mới.

`description` nên ngắn, có ý nghĩa với người vận hành và không tiết lộ chi tiết nhạy cảm như CVE chưa công bố, địa chỉ nội bộ, credential hoặc thông tin cấu hình bí mật. Nếu cần mô tả chi tiết, hãy dùng hệ thống quản lý thay đổi hoặc tài liệu phát hành có kiểm soát truy cập.

## 2. Platform nhận biết bản bảo trì mới như thế nào?

Platform đọc catalog từ endpoint `GET /v2/catalog`. Khi catalog được làm mới, Platform có thể so sánh `maintenance_info.version` của từng plan với phiên bản bảo trì mà nó ghi nhận cho các instance đã cấp phát. Nếu phiên bản plan mới hơn phiên bản instance đang chạy, Platform có thể đánh dấu instance có bản bảo trì sẵn sàng.

Quy trình khái quát:

~~~mermaid
sequenceDiagram
    participant B as Service Broker
    participant P as Platform
    participant O as Operator
    participant S as Service Instance

    B-->>P: GET /v2/catalog (maintenance_info.version mới)
    P->>P: So sánh phiên bản plan với instance
    P-->>O: Thông báo có bản bảo trì
    O->>P: Yêu cầu cập nhật instance
    P->>B: PATCH /v2/service_instances/{id}
    Note over P,B: previous_values.maintenance_info chứa phiên bản trước đó
    B->>S: Điều phối cập nhật theo policy của broker
    S-->>B: Kết quả bảo trì
    B-->>P: 200 OK hoặc 202 Accepted
~~~

Catalog chỉ công bố trạng thái phiên bản và khả năng của plan. Việc Platform tự động thông báo, yêu cầu người dùng xác nhận hay lên lịch bảo trì phụ thuộc vào nền tảng và chính sách vận hành. Broker không nên giả định rằng thay đổi catalog sẽ tự động nâng cấp mọi instance ngay lập tức.

Đối với broker, việc công bố version mới có nghĩa là có một bản bảo trì có thể được áp dụng. Nó không có nghĩa mọi instance đã được cập nhật. Broker cần lưu phiên bản thực tế của từng instance và cập nhật giá trị đó sau khi thao tác bảo trì thành công.

## 3. `previous_values.maintenance_info` trong yêu cầu update

Khi Platform gọi endpoint cập nhật service instance, phần `previous_values` có thể chứa thông tin trạng thái trước cập nhật. Với bảo trì, Platform có thể gửi `previous_values.maintenance_info` để cho broker biết phiên bản bảo trì mà Platform ghi nhận ở instance trước thao tác.

Ví dụ request:

~~~http
PATCH /v2/service_instances/db-instance-42?accepts_incomplete=true HTTP/1.1
Host: broker.example.internal
Authorization: Basic <broker-credentials>
X-Broker-API-Version: 2.17
Content-Type: application/json

{
  "service_id": "postgres-service",
  "plan_id": "postgres-standard",
  "previous_values": {
    "service_id": "postgres-service",
    "plan_id": "postgres-standard",
    "organization_id": "org-123",
    "space_id": "space-456",
    "maintenance_info": {
      "version": "14.8.1",
      "description": "Previous maintenance release"
    }
  },
  "parameters": {}
}
~~~

Đây là ví dụ minh họa cho luồng update cùng plan để áp dụng maintenance release. `previous_values.maintenance_info.version` là thông tin phiên bản trước đó mà Platform gửi; nó không phải phiên bản đích. Broker xác định phiên bản đích từ trạng thái catalog hiện tại và chính sách bảo trì của mình.

Broker nên thực hiện các bước sau:

1. Xác thực request và kiểm tra phiên bản OSB API.
2. Tải instance theo `instance_id` cùng phạm vi tenant/platform; xác minh quyền sở hữu.
3. Đọc service và plan hiện tại từ mô hình catalog của broker.
4. Đối chiếu `previous_values.maintenance_info` với phiên bản broker đã lưu cho instance.
5. Xác định bản bảo trì đích hiện đang được công bố và có thể áp dụng cho instance.
6. Kiểm tra điều kiện tương thích, cửa sổ bảo trì, backup, quota và chính sách downtime.
7. Tạo operation và điều phối cập nhật đồng bộ hoặc bất đồng bộ.
8. Chỉ ghi phiên bản bảo trì mới vào instance sau khi quá trình cập nhật đã thành công.

`previous_values` là dữ liệu mô tả trạng thái trước đó, không phải nguồn dữ liệu đáng tin cậy duy nhất. Broker cần đối chiếu với bản ghi nội bộ của instance để phát hiện request cũ, retry hoặc dữ liệu không còn đồng bộ. Không được chỉ tin version do caller gửi để quyết định rằng instance đã chạy một bản phát hành nào đó.

## 4. Phân biệt maintenance update và plan update

Một service instance có thể được cập nhật vì nhiều lý do: đổi plan, thay đổi tham số cấu hình hoặc áp dụng bản bảo trì mới trong cùng plan. Các trường hợp này dùng chung endpoint update nhưng mang ý nghĩa nghiệp vụ khác nhau.

| Trường hợp | `plan_id` | `maintenance_info.version` | Mục tiêu |
|---|---|---|---|
| Đổi plan | Có thể thay đổi | Có thể thay đổi theo plan đích | Chuyển instance sang gói dịch vụ khác |
| Đổi tham số | Thường giữ nguyên | Thường giữ nguyên | Thay đổi cấu hình instance |
| Bảo trì trong cùng plan | Giữ nguyên | Chuyển từ bản cũ sang bản mới | Vá lỗi hoặc nâng cấp thành phần vận hành |

Thuộc tính `plan_updateable` trong catalog mô tả khả năng cập nhật plan theo hợp đồng OSB API. Nó không phải phiên bản bảo trì và không nên được dùng để lưu trạng thái bảo trì của instance. Khi thiết kế broker, cần tách policy đổi plan khỏi policy áp dụng maintenance release, dù cả hai có thể đi qua cùng service update.

Ví dụ: instance `db-instance-42` đang dùng plan `postgres-standard`, maintenance version `14.8.1`. Broker công bố `14.8.2`. Khi Platform yêu cầu bảo trì, `plan_id` vẫn là `postgres-standard`; broker tạo backup, nâng image hoặc engine, chạy kiểm tra sau nâng cấp rồi ghi version mới `14.8.2`. Đây không phải thao tác chuyển sang plan `postgres-premium`.

## 5. Yêu cầu phiên bản giao thức OSB API

Không phải mọi Platform đều hiểu mọi trường hoặc hành vi được bổ sung trong các minor version của OSB API. Vì vậy, broker cần xác định tính năng giao thức mà mình sử dụng và phiên bản tối thiểu mà tính năng đó yêu cầu.

Header `X-Broker-API-Version` cho biết phiên bản API Platform đang sử dụng. Broker cần đọc và xác thực header trên request OSB API trước khi gọi service nghiệp vụ. Khi triển khai tính năng phụ thuộc vào một minor version mới, policy cần xác minh Platform khai báo phiên bản đủ mới theo đặc tả OSB API tương ứng.

Quy tắc quan trọng:

- Không suy ra phiên bản OSB API từ phiên bản Spring Boot hoặc phiên bản dependency `spring-cloud-open-service-broker`.
- Không so sánh `maintenance_info.version` với `X-Broker-API-Version`; hai giá trị có miền ý nghĩa khác nhau.
- Không yêu cầu Platform dùng đúng một minor version nếu request vẫn tương thích với hợp đồng mà broker triển khai.
- Chỉ đặt mức phiên bản tối thiểu khi broker thật sự cần một trường hoặc hành vi giao thức được bổ sung ở phiên bản đó.
- Kiểm tra phiên bản trước khi ghi operation, cập nhật instance hoặc gọi provider.

### Xác định minimum API version

Mỗi tính năng được sử dụng cần có một bản ghi trong ma trận tương thích nội bộ:

| Tính năng | Nguồn hợp đồng | Cách kiểm tra |
|---|---|---|
| `maintenance_info` trong catalog plan | Schema catalog của OSB API | Xác định minor version đầu tiên định nghĩa trường và schema của phiên bản broker hỗ trợ |
| `previous_values.maintenance_info` trong update request | Schema update service instance | Xác định minor version đầu tiên cho phép Platform gửi dữ liệu này |
| Async update và `last_operation` | Hợp đồng async operation | Xác minh Platform chấp nhận incomplete operation và broker triển khai polling |
| Trường hoặc hành vi bổ sung khác | Đúng phần tương ứng trong OSB API specification | Ghi rõ phiên bản tối thiểu và endpoint chịu ảnh hưởng |

Các giá trị phiên bản tối thiểu phải được lấy từ revision chính thức của OSB API mà dự án chọn làm chuẩn. Không đoán mốc phiên bản dựa trên số phiên bản thư viện Java. Khi nâng cấp thư viện, cần kiểm tra release note và schema để xác định khả năng giao thức thực tế.

Nếu request thiếu `X-Broker-API-Version` hoặc giá trị sai định dạng, broker có thể trả `400 Bad Request` theo hợp đồng. Nếu request có định dạng hợp lệ nhưng Platform dùng phiên bản thấp hơn mức tối thiểu bắt buộc cho tính năng mà broker cần, broker có thể trả `412 Precondition Failed` với thông báo yêu cầu nâng cấp. Response nên giúp Platform operator xác định phiên bản cần thiết.

Ví dụ lỗi phiên bản:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/json

{
  "error": "UnsupportedApiVersion",
  "description": "This maintenance workflow requires a newer OSB API version. Upgrade the Platform API version and retry."
}
~~~

`UnsupportedApiVersion` là mã lỗi minh họa do broker định nghĩa. Khi áp dụng thực tế, mô tả nên nêu phiên bản tối thiểu cụ thể đã được xác minh từ hợp đồng mà broker triển khai.

### Kiểm tra phiên bản theo tính năng

Broker có thể tổ chức policy tập trung thay vì rải các điều kiện so sánh header trong từng service:

~~~java
record OsbApiVersion(int major, int minor)
        implements Comparable<OsbApiVersion> {

    @Override
    public int compareTo(OsbApiVersion other) {
        int majorResult = Integer.compare(major, other.major);
        return majorResult != 0
                ? majorResult
                : Integer.compare(minor, other.minor);
    }
}

enum OsbFeature {
    MAINTENANCE_INFO_IN_CATALOG,
    MAINTENANCE_INFO_IN_PREVIOUS_VALUES,
    ASYNC_UPDATE
}

void requireFeatureVersion(
        OsbApiVersion platformVersion,
        OsbApiVersion minimumVersion) {
    if (platformVersion.compareTo(minimumVersion) < 0) {
        throw new UnsupportedApiVersionException(minimumVersion);
    }
}
~~~

Đây là mã mô hình hóa, không phải class có sẵn của Spring Cloud Open Service Broker. Bảng `OsbFeature` giúp gắn yêu cầu phiên bản với tính năng; cấu hình `minimumVersion` phải lấy từ OSB API specification đã chọn. Parser thực tế cần kiểm tra định dạng `MAJOR.MINOR`, giới hạn số nguyên và xử lý major version riêng.

## 6. Thiết kế dữ liệu maintenance trong broker

Để xử lý update đáng tin cậy, broker nên lưu cả phiên bản bảo trì mà catalog đang công bố và phiên bản thực tế đã áp dụng trên từng instance.

Một mô hình dữ liệu rút gọn:

~~~text
ServicePlan
  serviceId
  planId
  maintenanceVersion
  maintenanceDescription

ServiceInstance
  platformInstanceId
  instanceId
  serviceId
  planId
  appliedMaintenanceVersion
  lifecycleState
  currentOperationId

ServiceOperation
  operationId
  instanceId
  operationType
  sourceMaintenanceVersion
  targetMaintenanceVersion
  state
  startedAt
  completedAt
  errorCode
~~~

`ServicePlan.maintenanceVersion` là phiên bản broker công bố trong catalog. `ServiceInstance.appliedMaintenanceVersion` là phiên bản đã được áp dụng thành công cho instance. `ServiceOperation` lưu nguồn, đích và tiến trình để có thể retry, polling và audit.

Không cập nhật `appliedMaintenanceVersion` ngay khi nhận request. Nếu broker ghi phiên bản mới trước khi provider nâng cấp xong, Platform và broker có thể tin rằng instance đã được bảo trì trong khi tài nguyên thực tế vẫn ở phiên bản cũ. Chỉ cập nhật trường này sau khi mọi bước bắt buộc hoàn tất và kết quả đã được xác minh.

### Instance cũ chưa có maintenance version

Trong quá trình đưa `maintenance_info` vào broker đang vận hành, nhiều instance có thể được tạo trước khi broker lưu phiên bản bảo trì. Giá trị null khi đó có nghĩa là chưa biết hoặc chưa được ghi nhận, không nhất thiết là `0.0.0`.

Broker cần có chính sách chuyển đổi:

- Đối chiếu dữ liệu provider hoặc metadata đã lưu để xác định phiên bản thực tế.
- Nếu không thể xác định, đánh dấu trạng thái `UNKNOWN` hoặc cần reconcile.
- Chỉ áp dụng maintenance update sau khi đã xác định điểm xuất phát an toàn.
- Có thể thực hiện một lần đồng bộ metadata riêng nếu không cần thay đổi tài nguyên.
- Ghi audit về nguồn dữ liệu và kết quả reconcile.

Không tự động coi mọi instance thiếu version là đang chạy phiên bản cũ nhất. Điều đó có thể làm broker chạy lại migration không cần thiết hoặc bỏ qua bước chuẩn bị quan trọng.

## 7. Quy trình bảo trì đồng bộ và bất đồng bộ

Một bản bảo trì có thể yêu cầu restart, backup, chuyển dữ liệu hoặc rolling update. Nếu thao tác hoàn tất nhanh và nằm trong timeout request, broker có thể xử lý đồng bộ. Nếu công việc kéo dài, broker nên dùng asynchronous operation khi Platform cho phép.

### Luồng đồng bộ

1. Nhận update request và xác thực API version.
2. Kiểm tra quyền, trạng thái instance và version nguồn.
3. Tính version đích từ plan hiện tại.
4. Thực hiện backup hoặc pre-check.
5. Gọi provider để nâng cấp tài nguyên.
6. Chạy health check và kiểm tra tương thích.
7. Lưu `appliedMaintenanceVersion` mới và kết thúc operation.
8. Trả response thành công theo hợp đồng OSB API.

### Luồng bất đồng bộ

Nếu cần xử lý nền, broker tạo operation bền vững và trả `202 Accepted` khi request được chấp nhận. Worker thực hiện backup, nâng cấp, kiểm tra và cập nhật trạng thái. Platform gọi endpoint `last_operation` để đọc tiến độ cho đến khi operation kết thúc.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker API
    participant DB as Database
    participant Q as Outbox/Queue
    participant W as Maintenance Worker
    participant I as Infrastructure Provider

    P->>B: PATCH instance + previous_values.maintenance_info
    B->>B: Validate X-Broker-API-Version
    B->>DB: Check instance and source version
    B->>DB: Save operation and outbox event
    B-->>P: 202 Accepted + operation reference
    DB-->>Q: Publish maintenance command
    Q-->>W: Deliver command
    W->>I: Backup and apply target release
    I-->>W: Upgrade result
    W->>I: Run health checks
    I-->>W: Health status
    W->>DB: Save applied version and operation result
    P->>B: GET last_operation
    B->>DB: Read operation state
    B-->>P: in progress / succeeded / failed
~~~

Khi sử dụng hàng đợi, nên ghi operation và outbox event trong cùng transaction để tránh mất lệnh bảo trì sau khi database commit. Worker cần xử lý thông điệp theo cơ chế at-least-once một cách idempotent. Nếu worker bị dừng giữa chừng, broker phải có thể xác định bước cuối cùng đã hoàn tất và tiếp tục hoặc reconcile an toàn.

## 8. Idempotency, retry và an toàn dữ liệu

Platform có thể gửi lại PATCH khi không nhận được response. Worker cũng có thể nhận lại cùng một sự kiện khi hàng đợi retry. Broker cần nhận diện cùng một yêu cầu bảo trì để không chạy migration hoặc restart lặp gây hỏng dữ liệu.

Một khóa idempotency nội bộ có thể kết hợp:

- Phạm vi Platform và `instance_id`.
- Loại operation (maintenance update).
- Version nguồn và version đích.
- Request identity hoặc operation ID nếu có.

Khi nhận lại request:

- Nếu cùng version đích đã hoàn tất, trả kết quả hiện có theo hợp đồng.
- Nếu operation cùng mục tiêu đang chạy, trả thông tin operation hiện có.
- Nếu instance đang chạy operation khác, áp dụng chính sách xung đột hoặc tuần tự hóa.
- Nếu version nguồn trong `previous_values` không khớp bản ghi nội bộ, kiểm tra trạng thái và trả lỗi phù hợp thay vì ghi đè dữ liệu.
- Nếu provider đã nâng cấp nhưng broker chưa lưu kết quả, thực hiện reconcile trước khi gọi lại thao tác có side effect.

Trước bảo trì có ảnh hưởng dữ liệu, broker nên kiểm tra backup, khả năng phục hồi và giới hạn downtime. Với migration không thể rollback, cần thiết kế forward recovery hoặc quy trình phục hồi riêng. Không đánh dấu operation thành công chỉ vì API provider trả về HTTP 2xx; cần kiểm tra tài nguyên thực tế đạt trạng thái mong muốn.

## 9. Bảo mật và kiểm soát vận hành

`maintenance_info.description` có thể được hiển thị cho operator hoặc người dùng cuối, do đó không chứa dữ liệu bí mật. Request update cần được xác thực và kiểm tra quyền sở hữu instance. Broker phải bảo vệ credential provider, dữ liệu backup, connection string và log thao tác.

Các kiểm soát nên có:

- Chỉ Platform/caller được ủy quyền mới được yêu cầu maintenance update.
- Kiểm tra tenant, service instance và plan trước khi thực hiện.
- Dùng TLS giữa Platform và broker, cũng như giữa broker và provider.
- Không ghi token, password, connection string hoặc nội dung backup vào log.
- Có giới hạn concurrency để tránh bảo trì đồng thời quá nhiều instance.
- Hỗ trợ maintenance window hoặc policy tránh giờ cao điểm nếu sản phẩm yêu cầu.
- Ghi audit ai/Platform nào yêu cầu, version nguồn, version đích, operation ID và kết quả.
- Giám sát tỷ lệ thất bại, thời gian nâng cấp và số instance còn ở version cũ.

Một broker phục vụ nhiều Platform cần lưu đúng phạm vi instance. Cùng một `instance_id` có thể tồn tại ở các Platform khác nhau; khóa dữ liệu và idempotency nên bao gồm định danh Platform để không áp dụng nhầm bản bảo trì cho tenant khác.

## 10. Tích hợp với Spring Cloud Open Service Broker

Trong ứng dụng Spring Cloud Open Service Broker, framework cung cấp các endpoint và request/response model của OSB API. Ứng dụng triển khai service quản lý service instance để xử lý update. Cấu hình catalog cần cung cấp plan có `maintenance_info` theo mô hình và API của đúng phiên bản thư viện đang dùng.

Một cách tổ chức lớp ứng dụng:

| Thành phần | Trách nhiệm |
|---|---|
| Catalog configuration/service | Công bố service plan và `maintenance_info` hiện tại |
| OSB protocol boundary | Kiểm tra `X-Broker-API-Version` và schema request |
| Service instance update handler | Nhận update request, đọc `previous_values`, kiểm tra policy |
| Maintenance application service | Điều phối backup, migration, version state và operation |
| Repository | Lưu version của plan, version đã áp dụng và lịch sử operation |
| Infrastructure adapter | Thực hiện nâng cấp trên database engine, Kubernetes hoặc cloud provider |

Không nên để catalog service tự sửa trạng thái instance hoặc để adapter Kubernetes quyết định chính sách tương thích OSB. Catalog công bố phiên bản đích; application service quyết định cách áp dụng; adapter chỉ thực thi thao tác hạ tầng theo lệnh đã được chuẩn hóa.

Tên builder hoặc constructor để gắn `maintenance_info` có thể thay đổi theo phiên bản Spring Cloud Open Service Broker. Hãy dùng API được tài liệu của dependency đang cài đặt hỗ trợ. Các ví dụ JSON và mô hình dữ liệu trong bài mô tả hợp đồng OSB và kiến trúc ứng dụng, không phải chữ ký Java cụ thể của mọi phiên bản thư viện.

## 11. Kiểm thử

Kiểm thử nên bao phủ catalog, protocol compatibility và vòng đời maintenance update:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Catalog có `maintenance_info` | Version và description được serialize đúng schema |
| Không có maintenance release | Broker không công bố version giả |
| Version plan tăng | Platform có thể nhận biết phiên bản mới sau khi refresh catalog |
| Update request có previous maintenance version | Broker đối chiếu được version nguồn với bản ghi instance |
| API version thiếu hoặc sai định dạng | Request bị từ chối trước nghiệp vụ |
| API version thấp hơn mức tính năng yêu cầu | Trả lỗi phiên bản phù hợp, không tạo operation hoặc side effect |
| Update đồng bộ thành công | Instance lưu version đích sau khi provider được xác minh |
| Update bất đồng bộ | Trả `202`, polling phản ánh trạng thái operation |
| Provider thất bại | Instance không bị đánh dấu đã áp dụng version mới |
| Request hoặc queue message bị lặp | Không chạy migration hai lần |
| Instance thiếu version lịch sử | Reconcile theo policy, không tự giả định version nguồn |
| Hai Platform có cùng instance ID | Không trộn trạng thái hoặc operation giữa hai phạm vi |

Nên có contract test cho request/response OSB API, unit test cho version policy và state transition, integration test cho repository/outbox, cùng adapter test cho provider. Với async workflow, kiểm thử worker restart ở giữa từng bước để xác nhận operation có thể tiếp tục hoặc reconcile mà không làm hỏng instance.

## 12. Checklist triển khai

- [ ] Plan catalog công bố `maintenance_info.version` hợp lệ khi có maintenance release.
- [ ] `description` dễ hiểu và không chứa thông tin bí mật.
- [ ] Version bảo trì được quản lý nhất quán, không tái sử dụng cho nội dung khác.
- [ ] Broker lưu riêng version trong catalog và version đã áp dụng trên từng instance.
- [ ] `previous_values.maintenance_info` được đọc như dữ liệu trạng thái trước đó và đối chiếu với repository.
- [ ] `X-Broker-API-Version` được kiểm tra trước khi gọi use case update.
- [ ] Minimum API version của từng tính năng được lấy từ OSB API specification đã chọn.
- [ ] Phân biệt maintenance update với đổi plan và đổi parameters.
- [ ] Update đồng bộ/bất đồng bộ có trạng thái và operation rõ ràng.
- [ ] Worker và provider adapter xử lý retry idempotent, có reconcile khi kết quả không chắc chắn.
- [ ] Chỉ ghi version mới sau khi provider và health check xác nhận thành công.
- [ ] Có audit, metric và policy cho maintenance window/concurrency.

## Kết luận

`maintenance_info` cho phép broker công bố phiên bản bảo trì của từng service plan để Platform nhận biết khi có bản cập nhật mới. Khi Platform yêu cầu update, `previous_values.maintenance_info` giúp broker hiểu phiên bản trước đó mà Platform ghi nhận; broker cần đối chiếu dữ liệu này với trạng thái nội bộ, xác định phiên bản đích và thực hiện bảo trì có kiểm soát. Luồng này phải tuân theo phiên bản OSB API mà Platform khai báo qua `X-Broker-API-Version`, đồng thời giữ riêng version giao thức và version bảo trì. Với dữ liệu trạng thái bền vững, idempotency, operation bất đồng bộ và kiểm tra sau nâng cấp, broker có thể cung cấp maintenance update an toàn trên nhiều nền tảng.
