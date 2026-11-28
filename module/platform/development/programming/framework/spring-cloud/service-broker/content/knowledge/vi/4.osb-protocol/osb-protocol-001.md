# Đọc đặc tả OSB API: yêu cầu bắt buộc, tùy chọn và khả năng của nền tảng

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker được xây dựng theo Open Service Broker API (OSB API) bằng Spring Cloud. Để broker tích hợp đúng với Cloud Foundry, Kubernetes hoặc một nền tảng tương thích khác, nhóm phát triển cần đọc đặc tả OSB API như một hợp đồng giao tiếp có quy tắc rõ ràng. Hợp đồng này quy định endpoint, HTTP method, header, cấu trúc JSON, mã trạng thái, hành vi khi retry và cách phối hợp giữa broker với platform.

Một lỗi tích hợp thường không xuất phát từ thuật toán cấp phát database hay cache, mà từ việc hiểu sai điều gì là bắt buộc, điều gì chỉ là tùy chọn và điều gì phụ thuộc vào khả năng của platform. Ví dụ, broker có thể hỗ trợ provision bất đồng bộ, nhưng platform phải thể hiện rằng nó chấp nhận thao tác bất đồng bộ. Một service có thể bindable, nhưng platform chỉ gọi binding endpoint khi catalog công bố khả năng đó. Một broker có thể cung cấp endpoint truy vấn instance, nhưng chỉ khi khai báo capability tương ứng.

Bài học này hướng dẫn cách đọc đặc tả theo từng lớp: từ thuật ngữ chuẩn tắc, phiên bản API và header, đến catalog, endpoint vòng đời, capability, xử lý lỗi và cách chuyển hợp đồng đó thành thiết kế Spring Cloud có thể kiểm thử.

## 1. Đặc tả OSB API là hợp đồng giữa hai phía

OSB API định nghĩa giao tiếp giữa **platform** và **service broker**. Platform là bên điều phối vòng đời dịch vụ. Broker nhận yêu cầu, xác thực, kiểm tra catalog và thực hiện hoặc điều phối thao tác trên hệ thống cung cấp tài nguyên. Ứng dụng cuối cùng sử dụng endpoint dịch vụ được cấp phát thông qua thông tin binding.

Ba vai trò cần được phân biệt:

| Vai trò | Trách nhiệm chính |
|---|---|
| Platform | Hiển thị catalog, chọn service plan, gửi yêu cầu provision/bind/update/unbind/deprovision, theo dõi operation và cung cấp binding cho ứng dụng |
| Service broker | Công bố catalog, kiểm tra yêu cầu, điều phối vòng đời, trả binding credentials, lưu trạng thái và phản hồi theo hợp đồng OSB |
| Service provider | Cấp phát và vận hành tài nguyên thực tế như database, cache, message broker hoặc endpoint dịch vụ |

OSB API không chuẩn hóa cách broker tạo một database trên từng nhà cung cấp. Nó chuẩn hóa cách platform yêu cầu broker tạo service instance, binding instance đó, thay đổi hoặc thu hồi tài nguyên. Broker có thể dùng REST API của cloud provider, SDK, Kubernetes API hoặc công cụ nội bộ phía sau adapter riêng.

Vì vậy, khi đọc một mục trong đặc tả, hãy xác định nó đang ràng buộc platform, broker hay cả hai. Một yêu cầu platform phải gửi header không đồng nghĩa broker phải trả lại header đó. Một capability broker công bố trong catalog cũng không tự động có nghĩa mọi platform đều hỗ trợ capability ấy.

## 2. Hiểu đúng MUST, SHOULD và MAY

Đặc tả giao thức thường dùng các từ viết hoa để diễn đạt mức độ bắt buộc. Đây là thuật ngữ chuẩn tắc, không phải cách viết nhấn mạnh thông thường.

| Từ khóa | Ý nghĩa khi triển khai |
|---|---|
| **MUST** / **MUST NOT** | Yêu cầu bắt buộc. Vi phạm làm giao tiếp không tuân thủ hợp đồng. |
| **SHOULD** / **SHOULD NOT** | Khuyến nghị mạnh. Có thể có ngoại lệ, nhưng phải hiểu rõ tác động và lý do. |
| **MAY** | Tùy chọn được phép. Chỉ triển khai khi sản phẩm có nhu cầu và hai phía có thể phối hợp. |

Ví dụ, nếu platform MUST gửi header phiên bản API, broker có thể kiểm tra header đó ở lớp biên trước khi xử lý nghiệp vụ. Nếu một endpoint chỉ được yêu cầu khi service công bố **bindable: true**, broker không cần giả vờ hỗ trợ binding cho một dịch vụ không bindable. Nếu đặc tả MAY cho phép một trường metadata, broker có thể bỏ trường đó khi không có dữ liệu phù hợp.

Không nên diễn giải MAY thành "nên làm cho đầy đủ". Mỗi capability tùy chọn đều có chi phí: thêm trạng thái cần lưu, thêm endpoint cần bảo vệ, thêm tình huống retry và thêm kiểm thử tương thích. Chỉ công bố capability khi implementation thực sự đáp ứng hành vi được đặc tả.

Cũng không nên diễn giải SHOULD như một tùy chọn tùy ý. Nếu không tuân theo khuyến nghị, cần ghi rõ lý do kỹ thuật và kiểm tra xem platform có giả định hành vi đó hay không.

## 3. Bắt đầu bằng phiên bản API và header

### 3.1. Header phiên bản API

Platform gửi header **X-Broker-API-Version** trong request đến broker để chỉ ra phiên bản OSB API mà platform đang sử dụng. Giá trị có dạng phiên bản major/minor, ví dụ:

~~~http
X-Broker-API-Version: 2.17
~~~

Con số trên chỉ minh họa định dạng header. Khi triển khai, broker phải xác định rõ các phiên bản mà thư viện và logic nghiệp vụ thực sự hỗ trợ. Không nên suy ra khả năng tương thích chỉ từ việc endpoint có cùng đường dẫn **/v2**.

Broker cần kiểm tra header này trước khi chạy use case. Nếu phiên bản không được hỗ trợ, trả lỗi theo quy tắc phiên bản của OSB API, thường là **412 Precondition Failed**, kèm mô tả đủ rõ để platform biết yêu cầu không thể được xử lý theo phiên bản đã chọn. Không nên âm thầm hiểu request theo một phiên bản khác, vì cùng một payload có thể có ý nghĩa hoặc quy tắc validation khác nhau.

Một chiến lược triển khai thực tế là:

1. Phân tích giá trị header thành major và minor.
2. Kiểm tra major version có nằm trong nhóm được broker hỗ trợ.
3. Kiểm tra các hành vi phụ thuộc minor version, nhất là field hoặc operation được bổ sung ở các phiên bản sau.
4. Chọn bộ validation và serializer phù hợp.
5. Ghi phiên bản đã nhận vào log có correlation ID để hỗ trợ chẩn đoán.

Header phiên bản là một phần của hợp đồng trên từng request. Đừng chỉ kiểm tra nó ở endpoint catalog rồi bỏ qua các endpoint provision, binding hoặc deprovision.

### 3.2. Header danh tính người khởi tạo

**X-Broker-API-Originating-Identity** là header tùy chọn mà platform có thể gửi để truyền danh tính người hoặc tác nhân khởi tạo thao tác. Header này thường gồm định danh platform và payload JSON đã được Base64 encode theo định dạng OSB API.

Ví dụ về hình thức header:

~~~http
X-Broker-API-Originating-Identity: cloudfoundry eyJ1c2VyX2lkIjoiLi4uIn0=
~~~

Payload sau giải mã phụ thuộc platform. Với Cloud Foundry, nó có thể chứa user ID hoặc thông tin danh tính theo cấu trúc do platform quy định. Broker nên parse header bằng parser có kiểm soát, giới hạn kích thước, xác thực JSON và giữ nguyên ngữ cảnh platform để audit.

Header này hỗ trợ audit và authorization theo người khởi tạo, nhưng không thay thế xác thực caller. Broker vẫn phải xác thực platform đang gọi API bằng cơ chế bảo vệ endpoint đã cấu hình, chẳng hạn HTTP Basic Auth qua TLS hoặc cơ chế xác thực tương đương của môi trường. Không được tin payload originating identity chỉ vì nó có thể giải mã Base64; Base64 không phải mã hóa bảo mật hay chữ ký số.

### 3.3. Header và payload phải được kiểm tra ở biên

Các request OSB thường dùng JSON. Broker nên kiểm tra **Content-Type** đối với request có body, giải mã JSON, kiểm tra trường bắt buộc và từ chối dữ liệu sai định dạng bằng mã lỗi thích hợp. Các header có ý nghĩa bảo mật hoặc tương thích phải được xử lý trước khi gọi provider adapter.

Một lớp xử lý request có thể thực hiện theo thứ tự:

1. Xác thực platform client.
2. Kiểm tra TLS và chính sách mạng ở tầng triển khai.
3. Kiểm tra **X-Broker-API-Version**.
4. Parse originating identity nếu header được gửi.
5. Kiểm tra path parameter và query parameter.
6. Parse JSON và validate payload theo operation.
7. Kiểm tra quyền trên service instance hoặc binding.
8. Gọi application service tương ứng.

Cách sắp xếp này giúp lỗi giao thức được trả về nhất quán và tránh gọi nhà cung cấp khi request chưa đáp ứng hợp đồng.

## 4. Đọc catalog để biết broker thực sự công bố gì

Endpoint catalog là:

~~~http
GET /v2/catalog
~~~

Broker trả về danh sách service offering và plan mà platform có thể cung cấp cho người dùng. Catalog là hợp đồng công bố khả năng của broker; platform dựa vào nó để quyết định hiển thị dịch vụ nào, plan nào và thao tác nào được phép.

Một catalog rút gọn có thể trông như sau:

~~~json
{
  "services": [
    {
      "id": "service-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plan_updateable": false,
      "instances_retrievable": false,
      "bindings_retrievable": false,
      "plans": [
        {
          "id": "plan-small",
          "name": "small",
          "description": "Small database instance",
          "free": false
        }
      ]
    }
  ]
}
~~~

Các ID trong ví dụ là giá trị minh họa. Trong hệ thống thật, service ID và plan ID phải ổn định để platform có thể nhận diện cùng một offering qua nhiều lần tải catalog.

### 4.1. Service offering và service plan

Service offering mô tả một loại dịch vụ, chẳng hạn PostgreSQL, Redis hoặc RabbitMQ. Service plan mô tả một cấu hình hay cấp dịch vụ cụ thể của offering đó, ví dụ dung lượng, số kết nối, vùng triển khai hoặc chính sách backup.

Các trường thường gặp trong service object gồm:

| Trường | Vai trò |
|---|---|
| **id** | Định danh ổn định của service offering |
| **name** | Tên kỹ thuật của offering |
| **description** | Mô tả hiển thị |
| **bindable** | Cho biết instance của offering có thể được binding hay không |
| **plans** | Danh sách plan thuộc offering |
| **metadata** | Metadata bổ sung, thường phục vụ hiển thị hoặc tích hợp |
| **tags** | Nhãn để platform phân loại hoặc tìm kiếm |
| **requires** | Khai báo yêu cầu về tính năng của platform nếu có |
| **dashboard_client** | Thông tin tích hợp dashboard nếu broker cung cấp |
| **plan_updateable** | Cho biết việc thay đổi plan của instance có được hỗ trợ hay không |
| **instances_retrievable** | Cho biết broker hỗ trợ truy vấn thông tin service instance hay không |
| **bindings_retrievable** | Cho biết broker hỗ trợ truy vấn thông tin binding hay không |

Plan có các định danh, tên, mô tả và metadata riêng. Một số thuộc tính như **free**, **schemas** hoặc **maintenance_info** có thể được dùng tùy capability và phiên bản API. Không nên tự thêm field không thuộc hợp đồng chỉ vì ứng dụng Spring có thể serialize được object đó.

### 4.2. Capability phải phản ánh implementation

Một số field catalog là tuyên bố về khả năng của broker. Ví dụ:

- **bindable: true** nghĩa là broker hỗ trợ luồng binding cho offering đó.
- **plan_updateable: true** nghĩa là broker cho phép platform yêu cầu thay đổi plan theo quy tắc update của API.
- **instances_retrievable: true** nghĩa là broker cung cấp hành vi truy vấn instance được đặc tả.
- **bindings_retrievable: true** nghĩa là broker cung cấp hành vi truy vấn binding được đặc tả.

Không khai báo **true** chỉ để platform hiển thị nhiều tính năng hơn. Nếu capability được công bố nhưng endpoint hoặc hành vi thực tế không đáp ứng, platform có thể gọi vào một đường xử lý chưa hoàn thiện và tạo ra trạng thái không nhất quán.

### 4.3. Các trường tùy chọn trong catalog

**metadata**, **tags**, **dashboard_client**, **schemas** và **maintenance_info** có thể giúp platform hiển thị hoặc xác thực lựa chọn của người dùng. **requires** có thể khai báo dịch vụ cần một tính năng platform như syslog drain, route forwarding hoặc volume mount, tùy tập tính năng được OSB API định nghĩa.

Các trường này không thay thế validation trong broker. Ví dụ, JSON Schema trong catalog có thể giúp platform hiển thị form nhập tham số, nhưng broker vẫn phải kiểm tra **parameters** khi nhận provision hoặc update vì request có thể đến từ client khác hoặc dữ liệu có thể bị thay đổi.

## 5. Phân biệt endpoint bắt buộc và endpoint có điều kiện

Đặc tả OSB API có một tập endpoint vòng đời cốt lõi. Một số endpoint được dùng cho mọi broker, một số chỉ cần khi offering công bố capability tương ứng.

| Endpoint | Mục đích | Khi nào cần hỗ trợ |
|---|---|---|
| **GET /v2/catalog** | Công bố offering và plan | Luồng catalog cốt lõi |
| **PUT /v2/service_instances/{instance_id}** | Provision service instance | Luồng cấp phát instance |
| **DELETE /v2/service_instances/{instance_id}** | Deprovision instance | Luồng thu hồi instance |
| **PATCH /v2/service_instances/{instance_id}** | Update instance hoặc plan | Khi broker công bố hỗ trợ update theo catalog và phiên bản API |
| **PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}** | Tạo binding | Khi service offering bindable |
| **DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id}** | Thu hồi binding | Khi service offering bindable |
| **GET /v2/service_instances/{instance_id}/last_operation** | Truy vấn tiến trình operation | Khi broker xử lý bất đồng bộ |
| **GET /v2/service_instances/{instance_id}** | Truy vấn instance | Khi **instances_retrievable** được công bố |
| **GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}** | Truy vấn binding | Khi **bindings_retrievable** được công bố |

Bảng này giúp định hướng khi đọc spec; từng endpoint vẫn phải được đối chiếu với phiên bản OSB API broker tuyên bố hỗ trợ. Một số capability có điều kiện theo service offering, một số phụ thuộc vào việc platform gửi tham số hoặc header cụ thể.

### 5.1. Provision

Platform gửi yêu cầu tạo instance bằng **PUT**:

~~~http
PUT /v2/service_instances/{instance_id}
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

Payload thường chứa **service_id**, **plan_id**, context của platform và các tham số người dùng cung cấp. Các field định danh giúp broker biết offering và plan được chọn; context cho biết phạm vi tổ chức hoặc môi trường mà instance thuộc về.

Ví dụ payload:

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-small",
  "context": {
    "platform": "kubernetes",
    "namespace": "payments"
  },
  "parameters": {
    "storage_gb": 20
  }
}
~~~

Broker cần kiểm tra service ID và plan ID có tồn tại trong catalog, tham số có hợp lệ với plan và caller có quyền tạo tài nguyên trong context đó hay không. Instance ID trong URL là định danh platform dùng cho tài nguyên; broker nên lưu quan hệ giữa ID này với ID tài nguyên thực tế tại provider.

### 5.2. Update

Update service instance sử dụng **PATCH /v2/service_instances/{instance_id}**. Payload có thể mô tả plan mới, tham số thay đổi và các giá trị trước đó theo hợp đồng của phiên bản API.

Update có thể thay đổi dung lượng, cấu hình, phiên bản hoặc cấp dịch vụ. Broker phải kiểm tra capability đã công bố, giới hạn tương thích và khả năng thực hiện thay đổi tại provider. Một thay đổi có thể hoàn tất đồng bộ hoặc cần xử lý bất đồng bộ.

Không nên coi mọi field trong payload là yêu cầu phải ghi đè toàn bộ cấu hình. PATCH mang ý nghĩa cập nhật một phần theo hợp đồng; application service phải phân biệt field bị bỏ qua với field được gửi có giá trị rỗng hoặc giá trị mặc định.

### 5.3. Deprovision

Platform gửi **DELETE /v2/service_instances/{instance_id}** khi instance không còn cần thiết. Broker xác minh instance thuộc phạm vi caller, kiểm tra trạng thái và điều phối việc giải phóng tài nguyên tại provider.

Deprovision cần được thiết kế idempotent. Một request lặp lại do platform retry không được tạo thêm tác động phá hoại. Nếu tài nguyên đã được giải phóng, broker cần trả kết quả phù hợp với quy tắc của OSB API và trạng thái đã lưu.

### 5.4. Binding và unbinding

Khi offering có **bindable: true**, platform có thể gửi:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
~~~

Broker tạo danh tính hoặc credential cho consumer, lưu binding metadata và trả các thông tin kết nối. Ví dụ:

~~~json
{
  "credentials": {
    "hostname": "db.internal",
    "port": 5432,
    "database": "app",
    "username": "app_user",
    "password": "example-secret"
  }
}
~~~

Giá trị password ở trên chỉ là minh họa. Không ghi credential thật vào log, trace, exception hoặc tài liệu hướng dẫn. Khi unbind, platform gọi **DELETE** trên cùng resource path. Broker thu hồi đúng credential của binding đó và cập nhật trạng thái.

Binding có thể cần phân biệt consumer theo app GUID, namespace, workload hoặc context. Cùng một service instance có thể có nhiều binding độc lập. Vì vậy, không nên dùng một credential quản trị chung cho tất cả ứng dụng.

## 6. Bất đồng bộ là một thỏa thuận giữa platform và broker

Provision, update hoặc deprovision có thể mất nhiều thời gian vì phải chờ provider tạo tài nguyên, cấu hình mạng, cấp DNS hoặc thực hiện migration. OSB API cho phép broker xử lý những operation này bất đồng bộ.

Platform thể hiện khả năng chấp nhận bất đồng bộ bằng query parameter:

~~~http
PUT /v2/service_instances/{instance_id}?accepts_incomplete=true
~~~

Nếu broker cần thực hiện bất đồng bộ mà request không cho phép, broker phải từ chối theo quy tắc của API thay vì âm thầm trả thành công. Trong trường hợp platform cho phép, broker có thể trả **202 Accepted** cùng operation identifier:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "provision-001"
}
~~~

Platform dùng operation identifier để truy vấn:

~~~http
GET /v2/service_instances/{instance_id}/last_operation?operation=provision-001
~~~

Broker trả trạng thái như **in progress**, **succeeded** hoặc **failed**, kèm mô tả nếu cần. Platform tiếp tục poll theo chính sách của mình cho đến khi operation kết thúc.

Cần phân biệt hai ý:

- **accepts_incomplete=true** là tín hiệu của platform rằng nó chấp nhận operation bất đồng bộ cho request đó.
- Việc broker thực sự trả **202 Accepted** là quyết định dựa trên khả năng và trạng thái thực hiện operation.

Bất đồng bộ trong OSB API là hợp đồng ở mức vòng đời service instance. Nó không đồng nghĩa với việc ứng dụng Spring sử dụng reactive programming. WebFlux, Reactor hoặc queue là lựa chọn triển khai bên trong broker; platform chỉ quan sát response HTTP và operation state theo OSB API.

Không phải mọi thao tác đều được chuyển thành operation nền. Đặc tả quy định phạm vi async cụ thể; các thao tác binding/unbinding thường được xử lý đồng bộ. Khi triển khai, phải kiểm tra đúng phiên bản spec và không tự mở rộng async sang endpoint mà platform không có quy trình theo dõi tương ứng.

## 7. Các khả năng platform và cách broker công bố

OSB API được thiết kế để nhiều platform có thể tích hợp cùng một broker, nhưng không có nghĩa mọi platform hỗ trợ mọi tính năng giống nhau.

| Khả năng | Cách thể hiện trong hợp đồng | Cách broker cần xử lý |
|---|---|---|
| Cung cấp catalog | **GET /v2/catalog** | Trả offering và plan nhất quán |
| Binding | **bindable** trong service | Chỉ nhận binding khi offering hỗ trợ |
| Update plan | **plan_updateable** | Kiểm tra thay đổi plan và giới hạn tương thích |
| Truy vấn instance | **instances_retrievable** | Cung cấp endpoint retrieval tương ứng |
| Truy vấn binding | **bindings_retrievable** | Cung cấp endpoint retrieval tương ứng |
| Operation bất đồng bộ | **accepts_incomplete=true** theo request | Chỉ trả async response khi request và broker đều cho phép |
| Context platform | **context** trong request | Lưu và sử dụng đúng ngữ cảnh tenant/platform |
| Tính năng phụ thuộc platform | **requires** trong service metadata | Công bố yêu cầu đúng khả năng mà dịch vụ cần |
| Tham số cấu hình | **parameters** và schema nếu công bố | Validate độc lập ở broker |
| Maintenance | **maintenance_info** khi được hỗ trợ | Kiểm tra thay đổi bảo trì và điều kiện nâng cấp |

### 7.1. context và phạm vi sở hữu

Platform có thể gửi **context** để broker hiểu môi trường mà service instance hoặc binding được tạo. Ví dụ, Cloud Foundry có thể truyền thông tin organization và space; Kubernetes integration có thể truyền cluster, namespace hoặc thông tin tenant theo cách tích hợp đã chọn.

Broker nên lưu context cần thiết cùng service instance. Khi nhận update, bind hoặc deprovision, broker kiểm tra caller có quyền thao tác trên context đã lưu. Không nên chỉ tin context mới trong request mà bỏ qua việc so sánh với quyền sở hữu ban đầu.

Các field lịch sử như **organization_guid** và **space_guid** có thể xuất hiện trong một số tích hợp cũ. Khi hỗ trợ nhiều platform, cần có lớp adapter chuyển cấu trúc platform-specific thành mô hình context nội bộ thống nhất.

### 7.2. requires và tính năng platform

Một service có thể phụ thuộc vào khả năng do platform cung cấp, chẳng hạn syslog drain, route forwarding hoặc volume mount. Broker khai báo các yêu cầu này trong catalog để platform biết liệu nó có thể cung cấp offering hay không.

Đây là điểm cần đọc từ cả hai phía: broker mô tả yêu cầu, platform quyết định khả năng đáp ứng. Không nên công bố một service yêu cầu volume mount rồi giả định mọi platform đều có cơ chế mount tương đương.

### 7.3. Schema và tham số

Một plan có thể công bố schema cho tham số provision, update hoặc binding để platform xây dựng form hoặc validate đầu vào. Tuy vậy, schema công bố không thay thế validation server-side. Broker cần kiểm tra:

- Trường bắt buộc có hiện diện hay không.
- Kiểu dữ liệu có đúng hay không.
- Giá trị có nằm trong giới hạn plan hay không.
- Tham số có bị cấm với plan hoặc phiên bản hiện tại hay không.
- Tham số nhạy cảm có được xử lý và lưu trữ an toàn hay không.

Nếu broker không hỗ trợ một tham số, nên trả lỗi có mô tả rõ theo hợp đồng thay vì âm thầm bỏ qua và tạo cấu hình khác với điều người dùng yêu cầu.

## 8. Mã HTTP và cấu trúc lỗi

HTTP status code là một phần của giao thức. Platform thường dùng status để quyết định có retry, poll, báo lỗi người dùng hay tiếp tục workflow.

| Mã trạng thái | Ý nghĩa thường gặp trong giao tiếp broker |
|---|---|
| **200 OK** | Operation đồng bộ hoàn tất hoặc request đọc thành công |
| **201 Created** | Tài nguyên như service instance hoặc binding đã được tạo |
| **202 Accepted** | Operation được chấp nhận để xử lý bất đồng bộ |
| **400 Bad Request** | Request sai định dạng hoặc thiếu dữ liệu hợp lệ |
| **401 Unauthorized** | Caller chưa xác thực hợp lệ |
| **403 Forbidden** | Caller không có quyền thực hiện thao tác |
| **404 Not Found** | Không tìm thấy tài nguyên theo định danh được yêu cầu |
| **409 Conflict** | Trạng thái hoặc định danh xung đột với tài nguyên hiện có |
| **412 Precondition Failed** | Điều kiện phiên bản hoặc điều kiện tiên quyết không được đáp ứng |
| **422 Unprocessable Entity** | Payload có cấu trúc hợp lệ nhưng yêu cầu không thể được xử lý theo điều kiện/capability hiện tại |
| **5xx** | Lỗi phía broker hoặc phụ thuộc phía sau |

Mã cụ thể phải tuân theo endpoint và phiên bản OSB API, không áp dụng bảng này như quy tắc thay thế toàn bộ đặc tả. Ví dụ, **202** chỉ phù hợp khi operation thực sự được chấp nhận bất đồng bộ; không dùng nó như một response chung cho mọi request đã được ghi vào database.

Error response thường có trường **description** giúp platform hoặc người vận hành hiểu vấn đề. Mô tả lỗi cần đủ hữu ích nhưng không tiết lộ password, token, connection string, nội dung request nhạy cảm hoặc chi tiết nội bộ có thể bị khai thác.

Ví dụ:

~~~json
{
  "description": "The requested service plan is not available for this instance."
}
~~~

Broker nên chuẩn hóa lỗi từ provider adapter thành lỗi nghiệp vụ và HTTP response theo OSB. Lỗi timeout của nhà cung cấp có thể được retry nội bộ; lỗi plan không tồn tại thường là lỗi request cần người dùng sửa. Không nên chuyển mọi exception thành **500** vì platform sẽ khó phân biệt lỗi có thể retry với lỗi vĩnh viễn.

## 9. Đọc đặc tả theo quy trình thay vì chỉ đọc endpoint

Một cách đọc có hệ thống giúp phát hiện các ràng buộc nằm rải rác giữa phần endpoint, header, catalog và response.

### Bước 1: Chốt phiên bản

Ghi lại phiên bản OSB API broker tuyên bố hỗ trợ và kiểm tra header phiên bản trong mọi request. Đánh dấu những endpoint hoặc field chỉ có ở minor version cụ thể.

### Bước 2: Đọc mô hình dữ liệu

Tìm định nghĩa của service, plan, service instance, service binding, context và operation. Với mỗi field, ghi nhận:

- Có bắt buộc không?
- Kiểu dữ liệu là gì?
- Ai tạo giá trị?
- Giá trị có ổn định qua retry không?
- Có chứa dữ liệu nhạy cảm không?
- Có phụ thuộc capability hoặc phiên bản không?

### Bước 3: Lập ma trận endpoint

Với mỗi endpoint, ghi HTTP method, path, query parameter, header, request body, response body, status code và điều kiện gọi. Đừng chỉ ghi path; **accepts_incomplete**, operation key và capability có thể thay đổi hoàn toàn cách xử lý.

### Bước 4: Đánh dấu capability

Tách capability thành ba nhóm:

1. Broker luôn hỗ trợ theo baseline.
2. Broker chỉ hỗ trợ khi offering hoặc plan công bố điều kiện tương ứng.
3. Platform phải gửi tín hiệu hoặc phải hỗ trợ một tính năng để workflow có thể thực hiện.

### Bước 5: Đọc cả trường hợp lỗi

Với từng endpoint, đọc response thành công, response bất đồng bộ và các mã lỗi. Xác định trường hợp nào platform được retry, trường hợp nào cần sửa request và trường hợp nào cần kiểm tra trạng thái operation trước khi gửi lại.

### Bước 6: Viết contract test

Chuyển từng yêu cầu MUST thành ít nhất một kiểm thử. Với SHOULD, ghi rõ hành vi được chọn và lý do nếu không thực hiện. Với MAY, chỉ tạo test nếu broker tuyên bố hỗ trợ capability đó.

## 10. Ánh xạ hợp đồng OSB vào Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp các abstraction để ứng dụng Spring triển khai API broker. Khi áp dụng thư viện, nên giữ một ranh giới rõ:

- Lớp tích hợp OSB nhận request, map payload và trả response đúng hợp đồng.
- Application service xử lý quy tắc nghiệp vụ của catalog, instance, binding và operation.
- Repository lưu trạng thái bền vững.
- Provider adapter gọi API hoặc SDK của hệ thống cấp phát thật.
- Security layer xác thực platform, kiểm tra quyền và bảo vệ credential.

Không nên đưa toàn bộ logic tạo database vào controller hoặc handler HTTP. Nếu API của provider thay đổi, chỉ adapter liên quan nên thay đổi; hợp đồng OSB và application service vẫn giữ ổn định.

Một bảng ánh xạ trách nhiệm có thể dùng khi thiết kế:

| Hành vi OSB | Thành phần Spring đề xuất |
|---|---|
| **GET /v2/catalog** | Catalog service |
| Provision instance | Service instance service và lifecycle coordinator |
| Update instance | Update use case và provider adapter |
| Deprovision instance | Deprovision use case |
| Create binding | Binding service và credential provider |
| Delete binding | Unbind use case |
| Last operation | Operation query service và operation repository |
| Version/header validation | API filter hoặc security/interceptor layer |
| Originating identity | Identity parser và audit context |

Ví dụ một bộ kiểm tra header phiên bản ở lớp biên có thể được mô hình hóa như sau:

~~~java
public record OsbApiVersion(int major, int minor) {
    public static OsbApiVersion parse(String value) {
        if (value == null || !value.matches("\\d+\\.\\d+")) {
            throw new IllegalArgumentException("Invalid OSB API version");
        }

        String[] parts = value.split("\\.");
        return new OsbApiVersion(
            Integer.parseInt(parts[0]),
            Integer.parseInt(parts[1])
        );
    }
}

public void validateSupportedVersion(String headerValue) {
    OsbApiVersion requested = OsbApiVersion.parse(headerValue);

    if (requested.major() != 2 || requested.minor() > MAX_SUPPORTED_MINOR) {
        throw new UnsupportedOsbApiVersionException(headerValue);
    }
}
~~~

Đây là ví dụ minh họa cho bước parse và kiểm tra chính sách phiên bản, không phải implementation hoàn chỉnh của thư viện. Chính sách hỗ trợ phiên bản phải dựa trên compatibility matrix thực tế; nếu hỗ trợ nhiều minor version, cần kiểm tra khả năng tương thích theo từng field và operation thay vì chỉ so sánh một con số.

Một ví dụ khác là kiểm tra capability trước khi nhận binding:

~~~java
public BindingDetails bind(BindCommand command) {
    ServiceDefinition service = catalog.requireService(command.serviceId());

    if (!service.bindable()) {
        throw new ServiceNotBindableException(command.serviceId());
    }

    ServiceInstance instance =
        instanceRepository.requireOwnedInstance(command.instanceId(), command.context());

    return bindingCoordinator.createBinding(instance, command);
}
~~~

Trong code thực tế, exception cần được ánh xạ sang status code và error body đúng OSB API. Kiểm tra capability trong catalog và kiểm tra quyền trên instance là hai bước riêng biệt: bindable cho biết service hỗ trợ binding; authorization xác định caller có quyền tạo binding trên instance cụ thể hay không.

## 11. Ví dụ đọc một yêu cầu provision từ đầu đến cuối

Giả sử platform muốn tạo một PostgreSQL instance theo plan nhỏ.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Spring Cloud Broker
    participant C as Catalog/Policy
    participant S as State Store
    participant Q as Worker Queue
    participant R as Resource Provider

    P->>B: PUT /v2/service_instances/{id}
    Note over P,B: X-Broker-API-Version và accepts_incomplete
    B->>B: Authenticate và validate protocol
    B->>C: Kiểm tra service_id, plan_id, context
    C-->>B: Catalog capability và policy
    B->>S: Tạo instance/operation idempotently
    B->>Q: Gửi provision command
    B-->>P: 202 Accepted + operation
    Q->>R: Tạo PostgreSQL resource
    R-->>Q: Resource endpoint và kết quả
    Q->>S: Cập nhật trạng thái succeeded
    P->>B: GET last_operation
    B->>S: Đọc operation state
    S-->>B: succeeded
    B-->>P: 200 OK + state
~~~

Ở mỗi bước, có một nhóm yêu cầu giao thức cần được xác minh:

1. Request có header phiên bản đúng và query parameter cho phép async không?
2. Service ID và plan ID có tồn tại trong catalog không?
3. Platform context có hợp lệ và caller có quyền tạo instance không?
4. Request lặp lại có trả về cùng operation hoặc kết quả phù hợp không?
5. Nếu trả **202**, broker có operation ID để platform poll không?
6. Worker có thể retry sau timeout mà không tạo tài nguyên trùng không?
7. Last operation có phản ánh đúng trạng thái thực tế không?
8. Error body có đủ thông tin chẩn đoán nhưng không lộ bí mật không?

Nếu platform không chấp nhận async, broker phải hoàn thành đồng bộ trong giới hạn phù hợp hoặc trả lỗi theo hợp đồng. Nếu provider đã tạo tài nguyên nhưng broker chưa lưu được kết quả, reconciliation và idempotency phải giúp broker tìm lại tài nguyên thay vì provision thêm một bản khác.

## 12. Những lỗi thường gặp khi đọc và triển khai OSB API

| Cách hiểu sai | Hậu quả | Cách xử lý |
|---|---|---|
| Coi MUST, SHOULD và MAY như nhau | Bỏ sót yêu cầu bắt buộc hoặc triển khai thừa | Phân loại normative keyword trong checklist |
| Chỉ kiểm tra phiên bản ở catalog | Endpoint khác xử lý request theo phiên bản không phù hợp | Validate header trên mọi request |
| Công bố **bindable: true** nhưng chưa có binding flow | Platform gọi bind và nhận lỗi runtime | Chỉ công bố capability sau khi hoàn thiện và kiểm thử |
| Công bố retrieval capability nhưng không có endpoint | Platform không thể đồng bộ trạng thái | Đồng bộ catalog capability với endpoint thật |
| Trả **202** ngay khi lưu job nhưng không có operation state bền vững | Platform poll vô hạn hoặc nhận trạng thái sai | Lưu operation trước khi trả response |
| Dùng Base64 originating identity như bằng chứng xác thực | Có thể tin dữ liệu giả mạo | Xác thực platform độc lập và coi header là dữ liệu cần kiểm tra |
| Trả mọi lỗi thành **500** | Platform retry sai hoặc không thể hướng dẫn người dùng | Map lỗi validation, authorization, conflict và provider riêng |
| Bỏ qua request lặp | Tạo tài nguyên hoặc credential trùng | Dùng instance ID, binding ID và idempotency |
| Dựa hoàn toàn vào schema trong catalog | Request ngoài platform có thể vượt validation | Validate lại tại broker |
| Trộn API contract với SDK provider | Thay provider làm thay đổi handler OSB | Giữ provider adapter sau application service |

## 13. Checklist tuân thủ trước khi tích hợp platform

Trước khi đăng ký broker vào Cloud Foundry, Kubernetes integration hoặc một platform khác, hãy kiểm tra:

- [ ] Broker công bố phiên bản OSB API được hỗ trợ và kiểm tra **X-Broker-API-Version** trên mọi request.
- [ ] Catalog trả service ID và plan ID ổn định, không trùng và mô tả đúng capability.
- [ ] Mỗi capability được khai báo đều có implementation và contract test tương ứng.
- [ ] **bindable** phản ánh chính xác việc hỗ trợ create binding và unbinding.
- [ ] Plan update chỉ được công bố khi broker có thể xử lý thay đổi theo quy tắc API.
- [ ] Retrieval endpoint chỉ được công bố khi broker có thể trả dữ liệu nhất quán.
- [ ] Async response chỉ được trả khi request cho phép và operation state có thể truy vấn.
- [ ] Binding credentials có phạm vi quyền tối thiểu và được bảo vệ trong suốt vòng đời.
- [ ] Originating identity được parse an toàn, gắn với audit và không dùng thay xác thực.
- [ ] Context được lưu cùng tài nguyên và được kiểm tra khi update, bind hoặc deprovision.
- [ ] Mã HTTP và error body phù hợp với loại lỗi và endpoint.
- [ ] Retry không tạo tài nguyên hoặc credential trùng.
- [ ] Log và trace có correlation ID nhưng không chứa secret.
- [ ] Có kiểm thử contract cho cả success, async, retry, conflict và lỗi xác thực.

Đọc đặc tả OSB API đúng cách giúp nhóm phát triển xác định rõ ranh giới giữa baseline bắt buộc và capability tùy chọn. Khi catalog chỉ công bố những gì broker thực sự hỗ trợ, header và phiên bản được kiểm tra nhất quán, operation tuân thủ response contract và lỗi được ánh xạ đúng, broker Spring Cloud có thể tích hợp đáng tin cậy với nhiều platform mà không làm logic provider-specific rò rỉ vào giao thức chuẩn.
