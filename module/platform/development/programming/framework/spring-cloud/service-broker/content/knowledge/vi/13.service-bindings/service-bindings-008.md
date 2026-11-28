# Liên kết cho log drain và volume mount theo khả năng nền tảng

Trong Open Service Broker API (OSB API), binding không chỉ dùng để cấp username, password hoặc URI kết nối cho ứng dụng. Một số nền tảng còn hỗ trợ các kiểu liên kết đặc biệt, chẳng hạn chuyển log của ứng dụng tới một dịch vụ log bên ngoài (log drain) hoặc gắn một volume vào filesystem của ứng dụng (volume mount).

Service broker có thể mô tả khả năng này trong catalog và trả về thông tin tương ứng khi platform gọi endpoint tạo binding. Với log drain, response có thể chứa URL nhận log. Với volume mount, response có thể chứa driver, thư mục mount, chế độ truy cập và thông tin thiết bị. Platform sử dụng dữ liệu đó để cấu hình việc chuyển log hoặc gắn volume theo cơ chế mà nó hỗ trợ.

Các khả năng này phụ thuộc nền tảng. Cloud Foundry có cơ chế tích hợp cho log drain và volume services. Kubernetes không tự động hiểu toàn bộ hợp đồng binding mở rộng này chỉ vì broker tuân thủ OSB API; cần một controller, operator hoặc integration layer chuyển thông tin binding thành cấu hình logging hoặc volume phù hợp với cluster.

Bài học trình bày cách công bố capability trong catalog, cách tạo binding cho log drain và volume mount, cấu trúc response, vòng đời bind/unbind, bảo mật và các điểm cần kiểm tra khi tích hợp Spring Cloud service broker với Cloud Foundry hoặc Kubernetes.

## 1. Binding có thể cấp nhiều loại khả năng

Binding là mối liên kết giữa một service instance và một consumer, thường là ứng dụng. Với kiểu binding thông thường, broker trả về credentials hoặc thông tin kết nối để ứng dụng truy cập backing service.

Ví dụ binding database có thể trả:

~~~json
{
  "credentials": {
    "hostname": "postgres.internal.example",
    "port": 5432,
    "database": "orders",
    "username": "orders_app",
    "password": "secret-value"
  }
}
~~~

Platform có thể cung cấp credentials cho ứng dụng dưới dạng biến môi trường hoặc một cơ chế cấu hình tương đương.

Với log drain và volume mount, ứng dụng không nhất thiết phải đọc một credential rồi tự gọi dịch vụ. Platform thực hiện phần tích hợp hạ tầng dựa trên metadata mà broker trả về:

- **Log drain:** platform lấy URL từ binding response và cấu hình luồng log của ứng dụng chuyển tới endpoint đó.
- **Volume mount:** platform lấy thông tin volume mount và cấu hình runtime để gắn storage vào đường dẫn trong container hoặc workload.
- **Credentials:** broker vẫn có thể trả credentials cùng với các metadata đặc biệt nếu backing service yêu cầu ứng dụng sử dụng thêm thông tin xác thực.

Những kiểu response này mở rộng cách platform tiêu thụ dịch vụ. Broker phải công bố đúng capability và chỉ trả metadata mà platform có thể hiểu, thực thi.

## 2. Khai báo capability trong catalog

Service definition trong catalog có thể dùng trường requires để cho biết service cần những capability đặc biệt của platform. Các giá trị thường gặp gồm:

| Capability | Ý nghĩa |
|---|---|
| syslog_drain | Service có thể nhận log do platform chuyển tiếp |
| volume_mount | Service có thể cung cấp volume để platform gắn vào ứng dụng |
| route_forwarding | Service có thể tham gia luồng chuyển tiếp route theo khả năng platform |

Ví dụ service log drain:

~~~json
{
  "id": "central-log-service-id",
  "name": "central-log-drain",
  "description": "Chuyển log ứng dụng tới hệ thống log tập trung",
  "bindable": true,
  "requires": [
    "syslog_drain"
  ],
  "plans": [
    {
      "id": "log-standard-plan-id",
      "name": "standard",
      "description": "Log retention theo chính sách tiêu chuẩn"
    }
  ]
}
~~~

Ví dụ service volume:

~~~json
{
  "id": "shared-volume-service-id",
  "name": "shared-volume",
  "description": "Cung cấp volume dùng chung cho ứng dụng",
  "bindable": true,
  "requires": [
    "volume_mount"
  ],
  "plans": [
    {
      "id": "volume-10g-plan-id",
      "name": "10g",
      "description": "Volume dung lượng 10 GiB"
    }
  ]
}
~~~

Trường bindable cho biết service hỗ trợ tạo binding. Trường requires mô tả capability mà service cần platform hỗ trợ để sử dụng đúng cách. Khai báo requires không tự tạo log drain hoặc volume; broker vẫn phải triển khai logic provision, bind, unbind và tích hợp provider.

Chỉ công bố capability khi platform mục tiêu thực sự hỗ trợ. Nếu service cần cả log drain và volume mount, có thể khai báo cả hai nếu đặc tả và platform hỗ trợ cách kết hợp đó. Cần kiểm tra catalog thực tế và hành vi của từng platform thay vì suy ra chỉ từ việc framework serialize được trường requires.

## 3. Luồng binding với platform

Một luồng binding tổng quát:

1. Người dùng hoặc platform chọn service instance đã được provision.
2. Platform gửi yêu cầu bind với service instance ID và binding ID.
3. Request có thể mang context hoặc bind_resource mô tả consumer, tùy platform.
4. Broker xác thực request, kiểm tra instance, plan, tenant và capability.
5. Broker tạo cấu hình hoặc tài nguyên binding ở hệ thống phía sau.
6. Broker trả binding response gồm credentials, syslog_drain_url, volume_mounts hoặc các trường phù hợp.
7. Platform sử dụng response để cấu hình ứng dụng hoặc runtime.
8. Khi không còn sử dụng, platform gọi unbind và broker thu hồi liên kết tương ứng.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Service Broker
    participant S as Backing Service
    participant A as Application
    P->>B: PUT service_bindings
    B->>B: Kiểm tra instance, tenant, capability
    B->>S: Tạo endpoint log hoặc volume attachment
    S-->>B: Binding metadata
    B-->>P: Binding response
    P->>A: Cấu hình log drain hoặc volume mount
    A-->>P: Log stream hoặc truy cập filesystem
    P->>B: DELETE service_bindings
    B->>S: Thu hồi binding
    S-->>B: Xác nhận
    B-->>P: Unbind hoàn tất
~~~

Platform là thành phần thực thi tích hợp ở runtime. Broker cung cấp metadata và quản lý tài nguyên phía sau. Vì vậy, binding response cần đúng cấu trúc và có đủ thông tin để platform thực hiện cấu hình.

## 4. Request bind và bind_resource

Endpoint binding của OSB API có dạng:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
Content-Type: application/json
X-Broker-API-Version: <phiên-bản-OSB-API-được-hỗ-trợ>
~~~

Request có thể chứa service ID, plan ID, context, bind_resource và parameters. Ví dụ rút gọn:

~~~json
{
  "service_id": "central-log-service-id",
  "plan_id": "log-standard-plan-id",
  "context": {
    "platform": "cloud-foundry",
    "organization_guid": "org-123",
    "space_guid": "space-456"
  },
  "bind_resource": {
    "app_guid": "app-789"
  },
  "parameters": {
    "source": "orders-api"
  }
}
~~~

Trong Cloud Foundry, bind_resource có thể cung cấp app_guid để xác định ứng dụng được bind. Các trường cụ thể phụ thuộc loại binding và platform. Broker nên đọc đúng những trường đã được định nghĩa trong hợp đồng, kiểm tra tính hợp lệ và không mặc định request nào cũng có app_guid.

Context và bind_resource hỗ trợ broker xác định consumer và môi trường triển khai. Chúng không thay thế xác thực. Broker phải xác minh platform client, tenant ownership và quyền thao tác trước khi tạo endpoint log hoặc volume attachment.

Binding ID là định danh của liên kết. Nếu một instance được bind với nhiều ứng dụng, mỗi binding cần được quản lý riêng để unbind một consumer không ảnh hưởng các consumer còn lại.

## 5. Log drain là gì?

Log drain là cơ chế chuyển log do ứng dụng phát ra tới một hệ thống nhận log bên ngoài. Ví dụ, ứng dụng ghi log ra stdout/stderr; platform thu thập log từ runtime rồi chuyển tiếp tới endpoint của dịch vụ log.

Một service broker cung cấp log drain thường tạo hoặc xác định một đích nhận log, sau đó trả URL để platform cấu hình việc chuyển tiếp.

Các thành phần:

- Ứng dụng tạo log.
- Platform thu thập log từ container hoặc runtime.
- Platform gửi log tới endpoint được chỉ định.
- Dịch vụ log tiếp nhận, phân loại, lưu trữ và lập chỉ mục.
- Người vận hành truy vấn log qua hệ thống quan sát.

Broker không nhất thiết nằm trên đường truyền của từng bản ghi log. Broker thường tạo, quản lý endpoint, credential hoặc cấu hình đích nhận. Luồng log thực tế được platform chuyển trực tiếp tới endpoint.

~~~mermaid
flowchart LR
    A[Application] -->|stdout / stderr| P[Platform log agent]
    P -->|Syslog stream| D[syslog_drain_url]
    D --> L[Log ingestion service]
    L --> I[(Log storage and index)]
    B[Service Broker] -->|Tạo và quản lý log destination| L
    B -->|Trả URL trong binding| P
~~~

Cách tách control plane và data plane giúp broker quản lý vòng đời đích nhận log mà không cần proxy mọi log event.

## 6. Response binding cho log drain

Khi tạo binding cho service có capability syslog_drain, broker có thể trả trường syslog_drain_url.

Ví dụ:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
~~~

~~~json
{
  "syslog_drain_url": "syslog-tls://logs.example.net:6514"
}
~~~

Platform dùng URL này để chuyển tiếp log theo cơ chế mà nó hỗ trợ. Scheme, hostname, port và yêu cầu TLS phải phù hợp với log receiver cũng như platform. Ví dụ trên chỉ minh họa một endpoint Syslog TLS; không phải mọi platform đều hỗ trợ mọi scheme hoặc cấu hình giống nhau.

Broker có thể trả credentials bổ sung nếu contract và platform hỗ trợ cách sử dụng đó. Tuy nhiên, cần tránh đặt secret trực tiếp trong URL nếu URL có thể xuất hiện trong log hoặc thông tin chẩn đoán. Nếu cần token, nên dùng cơ chế xác thực an toàn phù hợp với platform và receiver.

Một URL log drain cần:

- Có thể truy cập từ mạng của platform.
- Dùng giao thức mà platform hỗ trợ.
- Có TLS khi log chứa dữ liệu nhạy cảm hoặc chính sách yêu cầu.
- Ánh xạ được về đúng tenant, instance hoặc binding.
- Có khả năng thu hồi hoặc vô hiệu hóa khi unbind.
- Có giới hạn lưu lượng và cơ chế chống lạm dụng.

Không nên trả URL chỉ tồn tại trong mạng nội bộ của broker nếu log agent của platform không thể truy cập.

## 7. Thiết kế log destination theo binding

Một service instance log có thể phục vụ nhiều ứng dụng. Broker cần quyết định đích log được tạo ở cấp instance hay cấp binding.

Ví dụ:

- Provision tạo một log tenant hoặc một namespace lưu trữ.
- Bind tạo một endpoint hoặc token riêng cho từng ứng dụng.
- Mỗi binding có thể gắn nhãn source/app để phân biệt log.
- Unbind thu hồi token hoặc xóa route của ứng dụng đó.
- Deprovision xóa cấu hình log instance và xử lý dữ liệu theo chính sách retention.

Tạo endpoint hoặc credential riêng cho mỗi binding giúp cô lập quyền truy cập và thu hồi độc lập. Nếu dùng một URL chung cho tất cả binding, broker cần có cách xác định nguồn log và kiểm soát việc một ứng dụng không thể giả mạo danh tính ứng dụng khác.

Nên gắn metadata như tenant ID, service instance ID và binding ID vào cấu hình phía log receiver. Không nên tin cậy các nhãn do ứng dụng tự gửi nếu chúng được dùng làm cơ sở phân quyền hoặc tính phí; broker và receiver cần xác minh nguồn.

### 7.1. Phân biệt log drain với credentials binding

Credentials thường được ứng dụng dùng để chủ động kết nối tới một dịch vụ. Log drain lại là luồng do platform chuyển tiếp. Nếu broker chỉ trả một URL trong credentials, platform có thể không hiểu đó là đích log.

Với OSB, trường syslog_drain_url thể hiện rõ semantics log drain. Hãy dùng đúng trường response khi platform hỗ trợ capability này.

## 8. Volume mount là gì?

Volume mount cho phép platform gắn một vùng lưu trữ vào một đường dẫn bên trong container hoặc môi trường chạy ứng dụng. Ứng dụng thao tác với file qua filesystem path, trong khi platform và volume driver xử lý việc kết nối storage phía dưới.

Ví dụ, ứng dụng cần lưu file tải lên tại /var/app/uploads. Broker cung cấp volume 10 GiB. Khi binding, broker trả thông tin mount; platform cấu hình runtime để volume xuất hiện tại đường dẫn mà ứng dụng yêu cầu.

~~~mermaid
flowchart LR
    A[Application container] -->|Read / write files| M[Container mount path]
    M --> D[Volume driver]
    D --> V[(Persistent storage)]
    B[Service Broker] -->|Provision / binding metadata| D
    B -->|volume_mounts response| P[Platform]
    P -->|Configure mount| M
~~~

Khác với credentials binding, ứng dụng không nhất thiết phải gọi API của storage provider. Ứng dụng có thể đọc/ghi file như thao tác filesystem thông thường.

Volume mount đặc biệt phụ thuộc platform và runtime. Platform cần có cơ chế gọi driver, gắn thiết bị hoặc mount filesystem, kiểm soát quyền và xử lý vòng đời storage.

## 9. Response binding cho volume mount

OSB API có trường volume_mounts trong binding response. Một phần tử volume mount thường mô tả driver, container directory, mode, device type và device-specific data.

Ví dụ minh họa:

~~~json
{
  "volume_mounts": [
    {
      "driver": "nfs",
      "container_dir": "/var/app/uploads",
      "mode": "rw",
      "device_type": "shared",
      "device": {
        "volume_id": "volume-789",
        "mount_config": {
          "server": "storage.internal.example",
          "export": "/exports/orders"
        }
      }
    }
  ]
}
~~~

Ý nghĩa các trường:

| Trường | Ý nghĩa |
|---|---|
| driver | Tên driver volume mà platform có thể sử dụng |
| container_dir | Đường dẫn mount bên trong container |
| mode | Quyền truy cập, ví dụ read-only hoặc read-write theo contract platform |
| device_type | Loại thiết bị theo semantics mà platform/driver hỗ trợ |
| device | Thông tin riêng của thiết bị hoặc driver |

Cấu trúc device có thể chứa metadata riêng của driver, chẳng hạn volume ID hoặc mount configuration. Nội dung cụ thể phải khớp với driver và platform. Không nên đưa password, private key hoặc credential dạng rõ vào device object nếu response có thể được lưu hoặc hiển thị rộng rãi.

Ví dụ trên chỉ mang tính minh họa. Giá trị hợp lệ của driver, device_type, mode và các trường device phụ thuộc hợp đồng OSB, platform và volume driver đang dùng. Cần kiểm tra tài liệu tích hợp cụ thể trước khi công bố plan.

## 10. Thiết kế volume theo instance và binding

Cần xác định rõ tài nguyên storage được tạo ở bước nào và binding tạo ra điều gì.

Một cách thiết kế thường gặp:

- Provision tạo volume hoặc storage allocation theo plan.
- Broker lưu provider volume ID và các thuộc tính dung lượng, region, driver.
- Bind tạo attachment hoặc thông tin mount cho consumer.
- Binding response mô tả cách platform gắn volume vào container.
- Unbind tháo attachment hoặc thu hồi quyền sử dụng của consumer.
- Deprovision xóa volume theo chính sách lưu giữ dữ liệu.

Có thể có nhiều binding cùng truy cập một volume nếu driver và plan cho phép. Nhưng việc chia sẻ cần được thiết kế rõ ràng: filesystem có hỗ trợ nhiều writer không, có cơ chế locking không, dữ liệu có thể bị ghi đè không, và platform có hỗ trợ mount đồng thời hay không.

Nếu mỗi ứng dụng cần volume riêng, broker có thể tạo volume hoặc attachment riêng cho từng binding. Nếu nhiều ứng dụng cần cùng một vùng dữ liệu, broker phải kiểm soát quyền truy cập và tính nhất quán dữ liệu.

### 10.1. Read-only và read-write

Mode xác định kiểu truy cập mà platform yêu cầu hoặc được broker công bố trong response theo contract hỗ trợ. Ví dụ:

- Read-only: ứng dụng có thể đọc file nhưng không được ghi.
- Read-write: ứng dụng có thể đọc và ghi file.

Không nên chỉ dựa vào mode trong response để bảo đảm bảo mật. Provider và driver cần thực thi quyền tương ứng ở filesystem, volume attachment hoặc storage policy. Nếu chỉ platform che nút ghi nhưng backend vẫn cho phép ghi, dữ liệu chưa được bảo vệ đúng cách.

### 10.2. Persistent và shared semantics

Một volume có thể tồn tại qua lần restart hoặc reschedule của ứng dụng, nhưng khả năng đó phụ thuộc loại storage và platform. Volume dùng chung giữa nhiều consumer cũng có semantics riêng.

Broker cần mô tả đúng:

- Dữ liệu có tồn tại sau khi ứng dụng restart hay không.
- Volume có thể được gắn trên nhiều instance đồng thời hay không.
- Có giới hạn region/zone hoặc node affinity hay không.
- Có hỗ trợ read-only, read-write hoặc multi-writer hay không.
- Điều gì xảy ra với volume khi unbind hoặc deprovision.
- Có snapshot, backup hoặc retention policy nào không.

Không nên suy ra volume persistent chỉ vì service plan có dung lượng storage. Cần xác minh backing service và driver thực sự hỗ trợ persistence.

## 11. Spring Cloud broker xử lý binding như thế nào?

Spring Cloud Open Service Broker cung cấp abstraction cho service binding. Ứng dụng thường triển khai handler hoặc service tương ứng để tạo binding response. Cấu trúc model và builder cụ thể phụ thuộc phiên bản framework.

Có thể tách nghiệp vụ theo các thành phần:

- Binding handler nhận request OSB và chuyển thành command.
- Binding service xác minh service instance, tenant và consumer.
- Log destination service tạo endpoint hoặc token nhận log.
- Volume service tạo attachment hoặc lấy thông tin mount.
- Binding repository lưu trạng thái liên kết.
- Provider adapter gọi hệ thống log hoặc storage.
- Response mapper chuyển kết quả thành model binding của framework.

Luồng xử lý khái niệm:

~~~java
public Mono<BindingResult> createBinding(BindCommand command) {
    return instanceRegistry.requireActive(
                    command.serviceInstanceId(),
                    command.tenantId())
            .flatMap(instance ->
                    bindingService.create(instance, command))
            .flatMap(binding ->
                    providerAdapter.createBinding(binding))
            .map(bindingMapper::toResponse);
}
~~~

Đây là ví dụ kiến trúc ở tầng nghiệp vụ, không phải chữ ký handler có thể dùng nguyên trạng cho mọi release. Cần đối chiếu interface, request model và response model của phiên bản Spring Cloud Open Service Broker đang sử dụng.

Khi tạo response:

- Log drain phải được ánh xạ vào trường syslog drain tương ứng.
- Volume mount phải được ánh xạ vào danh sách volume mounts.
- Credentials chỉ được trả khi cần thiết và theo đúng contract.
- Không trả trường đặc biệt nếu service hoặc platform không hỗ trợ capability đó.

Không nên gộp toàn bộ logic tạo log endpoint, mount volume và lưu binding vào một method dài. Tách provider adapter giúp dễ thay đổi hệ thống log hoặc storage mà không thay đổi phần nhận request OSB.

## 12. Lưu trạng thái binding bền vững

Một binding cần được lưu để broker có thể xử lý retry và unbind sau khi restart. Bản ghi binding có thể gồm:

| Trường | Mục đích |
|---|---|
| binding_id | ID do platform gửi |
| service_instance_id | Instance được bind |
| tenant_id | Chủ sở hữu liên kết |
| consumer_id | Consumer hoặc app được bind nếu có |
| binding_type | CREDENTIALS, LOG_DRAIN hoặc VOLUME_MOUNT |
| provider_binding_id | ID liên kết phía provider nếu có |
| endpoint_reference | Tham chiếu tới endpoint log hoặc cấu hình mount |
| secret_reference | Tham chiếu tới secret store, không phải secret dạng rõ |
| state | Trạng thái binding |
| created_at / updated_at | Thời điểm tạo và cập nhật |

Ví dụ SQL:

~~~sql
CREATE TABLE service_binding (
    binding_id VARCHAR(255) PRIMARY KEY,
    service_instance_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    consumer_id VARCHAR(255),
    binding_type VARCHAR(40) NOT NULL,
    provider_binding_id VARCHAR(512),
    endpoint_reference VARCHAR(512),
    secret_reference VARCHAR(512),
    state VARCHAR(40) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (service_instance_id)
        REFERENCES service_instance(service_instance_id)
);
~~~

Endpoint reference có thể là ID cấu hình phía log receiver hoặc volume attachment. Secret reference là khóa tham chiếu tới secret manager. Không nên lưu log token, password hoặc private key dạng rõ trong bảng binding.

Nếu service hỗ trợ nhiều loại binding, có thể dùng binding_type hoặc một bảng metadata chuyên biệt. Thiết kế cần bảo đảm mỗi binding được tra cứu và thu hồi độc lập.

## 13. Unbind log drain

Khi platform gọi DELETE service binding, broker cần thu hồi liên kết tương ứng.

Với log drain, thao tác unbind có thể gồm:

1. Tra cứu binding theo binding ID và service instance ID.
2. Xác minh tenant và trạng thái.
3. Ngăn nhận thêm log qua endpoint hoặc token của binding nếu chính sách yêu cầu.
4. Thu hồi token, route hoặc subscription phía log receiver.
5. Lưu trạng thái UNBOUND hoặc REVOKED.
6. Trả kết quả theo hợp đồng OSB.

Nếu log receiver dùng endpoint chung cho nhiều ứng dụng, unbind chỉ nên xóa route hoặc credential thuộc binding đó. Không xóa toàn bộ log destination nếu các binding khác vẫn sử dụng.

Cần xác định chính sách retention sau unbind. Log đã nhận trước đó có thể cần được giữ theo quy định lưu trữ, audit hoặc compliance. Unbind thường dừng luồng log mới; không nhất thiết xóa dữ liệu log đã được lưu.

## 14. Unbind volume mount

Với volume mount, unbind thường thu hồi attachment hoặc quyền truy cập của consumer. Nó không nhất thiết xóa volume và dữ liệu bên trong.

Quy trình có thể gồm:

1. Tra cứu binding và volume attachment.
2. Xác minh consumer không còn sử dụng hoặc platform đã tháo mount theo quy trình.
3. Gọi provider/driver để detach volume hoặc thu hồi access.
4. Xác nhận attachment đã được giải phóng.
5. Cập nhật trạng thái binding.
6. Giữ volume nếu service instance còn tồn tại và chính sách cho phép tái bind.

Nếu volume được chia sẻ giữa nhiều ứng dụng, broker phải kiểm tra các attachment khác trước khi thay đổi hoặc xóa tài nguyên. Deprovision service instance mới là bước xử lý vòng đời volume gốc theo chính sách của broker.

Không nên xóa volume ngay khi nhận DELETE binding nếu volume có thể chứa dữ liệu dùng chung hoặc cần tồn tại để một ứng dụng khác bind lại.

## 15. Phân biệt unbind và deprovision

| Thao tác | Log drain | Volume mount |
|---|---|---|
| Bind | Tạo endpoint/token hoặc route nhận log | Tạo attachment hoặc metadata mount |
| Unbind | Dừng luồng log của consumer và thu hồi quyền | Detach volume hoặc thu hồi attachment |
| Deprovision | Xóa cấu hình log instance, áp dụng retention | Xóa volume hoặc giải phóng allocation theo chính sách |
| Dữ liệu sau unbind | Log đã lưu có thể vẫn được giữ | Dữ liệu volume thường vẫn tồn tại nếu volume chưa bị xóa |

Ranh giới này rất quan trọng. Nếu broker xóa tài nguyên gốc trong unbind, một service instance có nhiều consumer có thể bị hỏng khi chỉ một ứng dụng ngừng sử dụng dịch vụ.

Deprovision cần xử lý cả các binding còn tồn tại theo quy tắc của platform và OSB API. Broker nên có chính sách rõ ràng cho binding còn hoạt động, volume đang được mount hoặc log receiver đang nhận dữ liệu.

## 16. Cloud Foundry và capability log drain

Cloud Foundry có cơ chế service binding dành cho log drain. Khi service được công bố với capability syslog_drain và binding response chứa syslog_drain_url, Cloud Foundry có thể cấu hình việc chuyển log của ứng dụng tới endpoint đó.

Các điểm cần kiểm tra khi triển khai:

- Service definition có khai báo requires chứa syslog_drain.
- Service có bindable phù hợp.
- Broker trả syslog_drain_url hợp lệ trong binding response.
- URL có thể truy cập từ mạng log agent của Cloud Foundry.
- Giao thức và TLS phù hợp với phiên bản, cấu hình platform.
- Unbind thu hồi đúng endpoint hoặc token của ứng dụng.
- Log receiver có khả năng phân tách tenant, app và binding.

Không phải mọi loại service binding trong Cloud Foundry đều có cùng semantics. Cần kiểm tra phiên bản Cloud Foundry và cấu hình operator thực tế, đặc biệt khi sử dụng log drain qua mạng riêng hoặc endpoint yêu cầu TLS.

## 17. Cloud Foundry và volume services

Cloud Foundry hỗ trợ tích hợp volume services thông qua volume service broker và driver phù hợp. Khi service công bố capability volume_mount, broker có thể trả volume_mounts để platform biết driver và cấu hình mount cần áp dụng.

Một số điều kiện:

- Platform phải bật và cấu hình hỗ trợ volume services.
- Volume driver phải được cài đặt, đăng ký và có thể truy cập.
- Driver name trong response phải khớp với driver platform nhận diện.
- Container directory phải là đường dẫn hợp lệ trong ứng dụng.
- Mode và device data phải khớp contract của driver.
- Provider storage phải đáp ứng khả năng attach/detach, persistence và sharing mà plan mô tả.

Broker chỉ trả mount metadata không có nghĩa volume đã được gắn thành công. Việc mount là trách nhiệm của platform và driver. Nếu driver không có hoặc không hoạt động, ứng dụng có thể không khởi động hoặc không truy cập được dữ liệu.

## 18. Kubernetes: cần lớp tích hợp cho log và volume

Kubernetes cung cấp các primitive như PersistentVolumeClaim, PersistentVolume, StorageClass, CSI driver, Pod volume và hệ thống logging. Tuy nhiên, một Kubernetes cluster tiêu chuẩn không tự động tiêu thụ OSB binding response chứa syslog_drain_url hoặc volume_mounts.

Nếu muốn dùng OSB broker với Kubernetes, cần một lớp tích hợp có trách nhiệm chuyển đổi:

**Với log drain:**

- Controller nhận thông tin binding từ broker.
- Tạo hoặc cập nhật cấu hình cho logging agent, sidecar hoặc collector.
- Cấu hình endpoint syslog hoặc sink tương ứng.
- Bảo vệ token và TLS secret.
- Thu hồi cấu hình khi unbind.

**Với volume mount:**

- Controller chuyển thông tin storage thành PVC hoặc resource phù hợp.
- StorageClass/CSI driver thực hiện cấp phát và attach volume.
- Pod spec tham chiếu volume và mountPath.
- Controller xử lý detach, retain hoặc delete theo vòng đời binding và instance.

~~~mermaid
flowchart TD
    P[OSB client / Kubernetes controller] --> B[Service Broker]
    B --> R[Binding response]
    R --> C[Integration controller]
    C --> L[Logging agent configuration]
    C --> V[PVC / CSI / Pod volume]
    L --> A[Application logs]
    V --> A
~~~

Kubernetes có nhiều lựa chọn logging và storage. Không có một cách chuyển đổi duy nhất phù hợp mọi cluster. Adapter cần xác định rõ driver, namespace, security context, access mode, storage class, logging backend và chính sách dữ liệu.

Không nên đưa các trường volume_mounts vào broker rồi cho rằng Kubernetes sẽ tự tạo PVC. Cần có controller hoặc operator đọc binding metadata và thực hiện tài nguyên Kubernetes tương ứng.

## 19. Bảo mật log drain và volume mount

Log có thể chứa dữ liệu cá nhân, token hoặc thông tin nghiệp vụ. Volume có thể chứa dữ liệu lâu dài của ứng dụng. Binding đặc biệt vì vậy cần chính sách bảo mật rõ ràng.

Với log drain:

- Dùng TLS khi truyền log qua mạng không tin cậy.
- Cấp endpoint hoặc token riêng theo binding khi cần cô lập.
- Giới hạn nguồn gửi log và tốc độ nhận.
- Tránh ghi credential vào URL hoặc log ứng dụng.
- Phân quyền truy vấn log theo tenant và retention policy.
- Thu hồi endpoint/token khi unbind hoặc khi credential bị lộ.

Với volume mount:

- Chỉ cấp mount path và quyền truy cập cần thiết.
- Dùng read-only khi ứng dụng không cần ghi.
- Kiểm tra quyền filesystem, UID/GID và security context.
- Không để nhiều tenant mount nhầm cùng volume.
- Mã hóa dữ liệu khi lưu nếu yêu cầu.
- Kiểm soát snapshot, backup, retention và xóa dữ liệu.
- Thu hồi attachment khi unbind và xác minh volume không còn được sử dụng trước khi xóa.

Thông tin trả về trong binding response có thể được lưu trong platform hoặc chuyển tới runtime. Vì vậy, chỉ trả các trường cần thiết và tránh để lộ thông tin quản trị provider.

## 20. Idempotency và xử lý lỗi binding

Platform có thể retry bind hoặc unbind khi timeout. Broker cần xử lý lặp an toàn.

Với bind:

- Cùng binding ID và cùng instance nên trả lại binding đã tạo hoặc tiếp tục operation hiện tại.
- Không tạo endpoint log hoặc volume attachment trùng lặp khi retry.
- Nếu binding ID đã tồn tại nhưng request thuộc instance hoặc tenant khác, từ chối xung đột.
- Lưu provider binding ID hoặc resource reference trước khi trả response.

Với unbind:

- Nếu binding đã được thu hồi, retry không được xóa nhầm tài nguyên khác.
- Nếu provider detach hoặc revoke timeout, tra cứu trạng thái trước khi gọi lại.
- Nếu endpoint hoặc volume đã bị xóa ngoài hệ thống, hoàn tất trạng thái nội bộ theo chính sách idempotency.
- Không giải phóng volume gốc khi chỉ một binding được unbind nếu các consumer khác còn sử dụng.

Các lỗi có thể xuất hiện:

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Platform không cấu hình log drain | Thiếu requires syslog_drain hoặc thiếu syslog_drain_url | Kiểm tra catalog và binding response |
| Log agent không truy cập endpoint | DNS, firewall, TLS hoặc route không đúng | Kiểm tra connectivity từ platform tới receiver |
| Log của nhiều app bị trộn | Endpoint chung không có định danh binding hoặc tenant | Tách endpoint/token hoặc gắn metadata đã xác minh |
| Volume không mount được | Driver chưa cài hoặc driver name sai | Đối chiếu driver với platform |
| Container không thấy mount path | container_dir hoặc Pod mountPath không khớp | Kiểm tra binding response và runtime config |
| Ứng dụng không ghi được file | Mode, filesystem permission hoặc UID/GID sai | Kiểm tra quyền thực tế trên volume |
| Unbind làm mất dữ liệu | Xóa volume gốc cùng lúc detach | Tách attachment lifecycle khỏi volume lifecycle |
| Retry bind tạo nhiều attachment | Không lưu binding state hoặc không idempotent | Dùng binding ID làm khóa và đối chiếu provider |
| Kubernetes không tạo PVC từ volume_mounts | Không có OSB integration controller | Xây dựng controller chuyển đổi metadata sang PVC/CSI |
| Unbind không dừng log | Receiver token/route chưa được thu hồi | Thu hồi binding-specific configuration |

## 21. Ví dụ thiết kế hai service riêng

Một broker có thể cung cấp hai service độc lập: central-log-drain và shared-volume. Cả hai đều có binding nhưng dùng capability và response khác nhau.

### 21.1. Service log drain

Catalog:

~~~json
{
  "id": "central-log-service-id",
  "name": "central-log-drain",
  "description": "Log service",
  "bindable": true,
  "requires": ["syslog_drain"],
  "plans": [
    {
      "id": "log-standard-plan-id",
      "name": "standard",
      "description": "Retention 30 ngày"
    }
  ]
}
~~~

Binding response:

~~~json
{
  "syslog_drain_url": "syslog-tls://logs.example.net:6514"
}
~~~

Broker lưu binding ID, tenant, app reference và log endpoint/token reference. Khi unbind, broker thu hồi route hoặc token của binding.

### 21.2. Service volume mount

Catalog:

~~~json
{
  "id": "shared-volume-service-id",
  "name": "shared-volume",
  "description": "Volume service",
  "bindable": true,
  "requires": ["volume_mount"],
  "plans": [
    {
      "id": "volume-10g-plan-id",
      "name": "10g",
      "description": "Volume 10 GiB"
    }
  ]
}
~~~

Binding response:

~~~json
{
  "volume_mounts": [
    {
      "driver": "nfs",
      "container_dir": "/var/app/uploads",
      "mode": "rw",
      "device_type": "shared",
      "device": {
        "volume_id": "volume-789"
      }
    }
  ]
}
~~~

Broker lưu binding và attachment reference. Khi unbind, broker tháo attachment theo contract. Khi deprovision, broker mới áp dụng chính sách xóa hoặc giữ volume gốc.

Hai service có thể dùng chung một database lưu mapping, nhưng provider adapter và lifecycle policy nên tách biệt vì log destination và volume có semantics khác nhau.

## 22. Checklist trước khi công bố capability

- [ ] Service definition có bindable phù hợp.
- [ ] requires chỉ khai báo capability mà platform mục tiêu thực sự hỗ trợ.
- [ ] Log drain trả syslog_drain_url theo đúng response contract.
- [ ] Volume service trả volume_mounts với driver, container_dir, mode, device_type và device phù hợp.
- [ ] Đã xác minh URL log receiver có thể truy cập từ platform.
- [ ] Đã xác minh volume driver có mặt và hoạt động trên platform.
- [ ] Binding ID được lưu bền vững và gắn đúng service instance/tenant.
- [ ] Consumer/app context được xác minh trước khi tạo binding.
- [ ] Log endpoint và volume attachment được cô lập theo binding khi cần.
- [ ] Unbind thu hồi đúng liên kết và không xóa tài nguyên gốc ngoài ý muốn.
- [ ] Deprovision có chính sách retention và xử lý dữ liệu rõ ràng.
- [ ] Retry bind/unbind không tạo endpoint hoặc attachment trùng lặp.
- [ ] Secret và credential không bị lộ trong URL, response không cần thiết hoặc log.
- [ ] Đã kiểm thử trên đúng phiên bản Cloud Foundry hoặc integration layer Kubernetes.
- [ ] Đã kiểm thử trường hợp platform không hỗ trợ capability và cách broker phản hồi.

Log drain và volume mount mở rộng mô hình binding của OSB API để platform có thể tích hợp dịch vụ với luồng log hoặc filesystem của ứng dụng. Broker công bố capability trong catalog, tạo binding và trả đúng metadata; platform cùng driver hoặc integration controller thực hiện phần cấu hình runtime. Việc triển khai cần bám sát khả năng của nền tảng, tách vòng đời binding khỏi tài nguyên gốc, đồng thời bảo đảm bảo mật, idempotency và xử lý unbind đúng cách.
