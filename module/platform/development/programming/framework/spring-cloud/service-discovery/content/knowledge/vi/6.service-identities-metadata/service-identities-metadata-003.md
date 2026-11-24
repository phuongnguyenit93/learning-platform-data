# Tạo instanceId duy nhất khi chạy nhiều bản sao

Khi chạy nhiều bản sao của cùng một microservice, các bản sao phải có cùng tên service để consumer tìm chúng trong một nhóm, nhưng mỗi bản sao cần một định danh instance riêng. Nếu hai tiến trình đăng ký cùng một `instanceId`, registry có thể xem chúng là cùng một registration, ghi đè thông tin hoặc khiến việc cập nhật và hủy đăng ký trở nên khó đoán tùy implementation.

Spring Cloud biểu diễn thông tin một bản sao qua `ServiceInstance` và các abstraction đăng ký service. Với Consul, thuộc tính thường dùng là `spring.cloud.consul.discovery.instance-id`; với Eureka, thuộc tính tương ứng là `eureka.instance.instance-id`. Bài học này trình bày cách chọn ID, cấu hình cho từng registry, chạy nhiều tiến trình local và xác minh các instance đã được đăng ký riêng biệt.

## 1. Phân biệt service ID và instance ID

Một service có thể có nhiều instance cùng cung cấp một chức năng. Ví dụ, ba tiến trình `order-service` có thể chạy trên ba port hoặc ba máy khác nhau.

| Thuộc tính | Ví dụ | Mục đích |
| --- | --- | --- |
| Service ID / service name | `order-service` | Gom các bản sao vào cùng một dịch vụ logic để consumer tìm theo tên. |
| Instance ID | `order-service:node-a:8081` | Phân biệt một registration cụ thể với các bản sao khác. |
| Host / IP | `10.0.0.21` | Địa chỉ mà consumer hoặc health checker có thể truy cập. |
| Port | `8081` | Cổng của instance. |
| Metadata | `version=v2`, `zone=az-a` | Thông tin bổ sung để quan sát hoặc lọc instance khi implementation hỗ trợ. |

Nguyên tắc quan trọng là **cùng service name, khác instance ID**. Nếu mỗi bản sao tự đặt `spring.application.name` thành một tên khác, consumer tìm `order-service` sẽ không tự động gom các tên đó thành một nhóm.

Ví dụ ba instance:

```text
Service ID: order-service

Instance ID                     Host          Port
order-service:node-a:8081       10.0.0.21     8081
order-service:node-b:8081       10.0.0.22     8081
order-service:node-c:8081       10.0.0.23     8081
```

Registry dùng service ID để nhóm các instance và dùng instance ID để phân biệt từng registration. Phạm vi duy nhất cụ thể phụ thuộc registry: Consul yêu cầu service ID duy nhất trong phạm vi agent/node đăng ký; Eureka nhận diện instance trong một application theo instance ID. Vì vậy, khi thiết kế ID cho hệ thống nhiều node, hãy tạo giá trị duy nhất trong toàn bộ phạm vi mà registry dùng để tra cứu và cập nhật instance.

## 2. Chọn chiến lược tạo instance ID

Một instance ID tốt cần duy nhất trong phạm vi registry, dễ truy vết trong log và ổn định đủ lâu để quản lý vòng đời đăng ký. Có một số chiến lược phổ biến.

### 2.1. Kết hợp hostname và port

Đây là lựa chọn dễ hiểu cho ứng dụng chạy trực tiếp trên máy ảo hoặc máy vật lý:

```text
order-service:<hostname>:<port>
```

Ví dụ `order-service:app-node-02:8081`. Trên cùng một máy, các tiến trình có port khác nhau sẽ có ID khác nhau. Trên các máy khác nhau, hostname giúp phân biệt instance dù chúng dùng cùng port.

Chiến lược này phù hợp khi hostname được quản lý ổn định và duy nhất trong phạm vi triển khai. Nếu nhiều container dùng chung hostname hoặc chạy qua network mode chia sẻ, cần bổ sung một thành phần khác như container ID hoặc biến `INSTANCE_ID` riêng.

### 2.2. Dùng UUID

Có thể sinh UUID khi ứng dụng khởi động:

```text
order-service:550e8400-e29b-41d4-a716-446655440000
```

UUID gần như loại bỏ nguy cơ trùng lặp, kể cả khi nhiều instance chạy cùng host và port namespace. Tuy nhiên, nếu sinh UUID mới mỗi lần khởi động, ID sẽ thay đổi sau restart. Registration cũ có thể còn tồn tại trong một khoảng thời gian cho tới khi cơ chế deregistration, health check hoặc lease expiration dọn dẹp. Dùng UUID khi instance mang tính ephemeral và registry có cơ chế thu hồi registration phù hợp.

### 2.3. Dùng định danh từ nền tảng triển khai

Trong Docker hoặc Kubernetes, nền tảng có thể cung cấp hostname, container ID, pod name hoặc pod UID. Đây thường là nguồn định danh tốt vì giá trị được tạo theo từng bản sao.

- Với Docker, có thể truyền `INSTANCE_ID` từ tên container hoặc một giá trị riêng trong Compose.
- Với Kubernetes, pod UID là định danh duy nhất của một Pod trong vòng đời của cluster; có thể đưa giá trị này vào container qua Downward API.
- Với nền tảng máy ảo, có thể dùng hostname hoặc instance ID do cloud provider cấp.

Không nên chỉ dựa vào tên service hoặc một hostname chung của load balancer. Các instance sau load balancer cần registration riêng với địa chỉ có thể truy cập trực tiếp từ consumer/health checker.

### 2.4. Chọn ID ổn định hay ephemeral

| Chiến lược | Ưu điểm | Hạn chế | Trường hợp phù hợp |
| --- | --- | --- | --- |
| Hostname + port | Dễ đọc, ổn định khi tiến trình restart trên cùng host/port | Có thể trùng nếu hostname không duy nhất hoặc nhiều container chia sẻ network identity | VM, máy vật lý, nhiều tiến trình local |
| UUID mỗi lần khởi động | Xác suất trùng cực thấp | ID thay đổi sau restart; cần dọn registration cũ | Worker hoặc container ephemeral |
| Container ID / Pod UID | Gắn với vòng đời instance của nền tảng | ID thay đổi khi tạo container/Pod mới; cần truyền đúng vào ứng dụng | Docker, Kubernetes |
| Biến `INSTANCE_ID` do deployment cấp | Rõ ràng, dễ kiểm soát và kiểm thử | Pipeline hoặc manifest phải bảo đảm không cấp trùng | Môi trường có quy trình triển khai chuẩn hóa |

Với nhiều tiến trình chạy local, kết hợp service name và port là đủ nếu mỗi tiến trình có port riêng. Với production, nên để nền tảng triển khai cấp một ID rõ ràng và duy nhất, đồng thời quyết định có cần giữ ID qua lần restart hay không.

## 3. Cấu hình instance ID cho Consul

Spring Cloud Consul Discovery cho phép cấu hình ID registration qua `spring.cloud.consul.discovery.instance-id`. Ví dụ cấu hình chung trong `application.yml`:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
        health-check-path: /actuator/health
        health-check-interval: 10s

server:
  port: ${SERVER_PORT:8080}
```

Trong ví dụ này:

- `spring.application.name` luôn là `order-service` cho mọi bản sao.
- `instance-id` ưu tiên lấy từ biến môi trường `INSTANCE_ID` nếu được cung cấp.
- Nếu chưa có `INSTANCE_ID`, giá trị dự phòng ghép service name, `HOSTNAME` và port.
- `server.port` có thể được thay đổi theo từng tiến trình bằng `SERVER_PORT`.

Đảm bảo các giá trị fallback thực sự duy nhất trong môi trường của bạn. Trên một số máy local, `HOSTNAME` có thể không được đặt hoặc có giá trị chung; khi đó fallback `localhost` chỉ phân biệt được các tiến trình nếu port khác nhau. Nếu có khả năng chạy cùng port trên các network namespace riêng nhưng hostname giống nhau, hãy truyền `INSTANCE_ID` riêng.

`instance-id` chỉ định danh registration. Nó không thay thế địa chỉ host, port hoặc health check. Consul Agent vẫn phải truy cập được endpoint health của từng instance.

## 4. Cấu hình instance ID cho Eureka

Với Eureka Client, thuộc tính tương ứng là `eureka.instance.instance-id`. Có thể dùng cùng quy ước ID:

```yaml
spring:
  application:
    name: order-service

server:
  port: ${SERVER_PORT:8080}

eureka:
  instance:
    instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
    prefer-ip-address: true
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
```

`spring.application.name` xác định application/service name trong Eureka; `eureka.instance.instance-id` phân biệt instance trong application đó. `prefer-ip-address` ảnh hưởng thông tin host mà Eureka công bố cho client, không tạo ra instance ID duy nhất. Đảm bảo IP hoặc hostname được công bố có thể truy cập từ các consumer.

Nếu dùng cả Consul và Eureka trong cùng một ứng dụng, cần quyết định rõ có chủ ý đăng ký vào cả hai registry hay không. Không sao chép cấu hình của registry này sang registry kia rồi giả định mọi thuộc tính có cùng ý nghĩa.

## 5. Chạy hai instance local với ID khác nhau

Giả sử Consul đang chạy tại `localhost:8500` và JAR đã được build thành `target/order-service.jar`. Mở hai terminal PowerShell riêng.

Terminal thứ nhất:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8081"
$env:INSTANCE_ID = "order-service:local:8081"
java -jar target/order-service.jar
```

Terminal thứ hai:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8082"
$env:INSTANCE_ID = "order-service:local:8082"
java -jar target/order-service.jar
```

Hai tiến trình có cùng `spring.application.name`, cùng kết nối tới Consul, nhưng port và instance ID khác nhau. Khi khởi động thành công, registry phải hiển thị hai registration của `order-service`.

Trên Linux hoặc macOS, có thể truyền biến riêng theo từng lệnh:

```bash
SPRING_PROFILES_ACTIVE=local SERVER_PORT=8081 \
INSTANCE_ID=order-service:local:8081 \
java -jar target/order-service.jar

SPRING_PROFILES_ACTIVE=local SERVER_PORT=8082 \
INSTANCE_ID=order-service:local:8082 \
java -jar target/order-service.jar
```

Nếu chạy nhiều instance bằng IDE, tạo hai Run Configuration với cùng main class và profile, nhưng mỗi cấu hình có `SERVER_PORT` và `INSTANCE_ID` riêng. Tránh để biến môi trường cũ trong terminal hoặc IDE ghi đè giá trị bạn vừa đặt.

## 6. Cấp instance ID trong Docker và Kubernetes

### 6.1. Docker Compose

Mỗi container có thể nhận một ID riêng qua biến môi trường. Ví dụ:

```yaml
services:
  order-a:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: docker
      SERVER_PORT: 8080
      INSTANCE_ID: order-service:order-a
      CONSUL_HOST: consul

  order-b:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: docker
      SERVER_PORT: 8080
      INSTANCE_ID: order-service:order-b
      CONSUL_HOST: consul
```

Hai container có thể cùng lắng nghe port `8080` vì mỗi container có network namespace riêng. Instance ID vẫn phải khác nhau. Consul phải truy cập được địa chỉ/port của từng container; cấu hình network và địa chỉ đăng ký cần phù hợp với topology thực tế.

### 6.2. Kubernetes

Kubernetes có thể truyền Pod UID vào biến môi trường bằng Downward API:

```yaml
env:
  - name: INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

Sau đó, cấu hình Spring dùng:

```yaml
spring:
  cloud:
    consul:
      discovery:
        instance-id: ${INSTANCE_ID}
```

Pod UID phù hợp để phân biệt các Pod đang tồn tại trong cluster. Khi Pod được tạo lại, UID thay đổi; registry cần dọn registration cũ thông qua deregistration, health check hoặc cơ chế đồng bộ phù hợp. Nếu cần ID dễ đọc cho vận hành, có thể kết hợp service name và Pod name, nhưng cần hiểu Pod name có thể được tái sử dụng theo thời gian; Pod UID vẫn là thành phần bảo đảm tính duy nhất trong vòng đời cluster.

## 7. Kiểm tra instance ID đã đăng ký

Sau khi khởi động nhiều bản sao, cần kiểm tra cả service name, instance ID, địa chỉ, port và health status.

### 7.1. Kiểm tra Consul

Lấy danh sách instance của service qua Catalog API:

```bash
curl http://localhost:8500/v1/catalog/service/order-service
```

Kết quả gồm các registration của `order-service`; kiểm tra trường `ServiceID`, `ServiceName`, `Address` và `ServicePort`. Với cấu hình health check, xem trạng thái từng registration qua:

```bash
curl http://localhost:8500/v1/health/service/order-service
```

Đối chiếu `ServiceID` giữa các bản sao để chắc chắn chúng không trùng. Catalog cho biết registration hiện diện; Health API cho biết tình trạng check tại thời điểm truy vấn.

### 7.2. Kiểm tra Eureka

Trong Eureka Dashboard, mở application `ORDER-SERVICE` và xem danh sách instance. Có thể truy vấn REST API:

```bash
curl http://localhost:8761/eureka/apps/ORDER-SERVICE
```

Kiểm tra `instanceId`, hostname/IP, port và trạng thái instance. Nếu hai tiến trình có cùng application name nhưng chỉ một instance xuất hiện hoặc thông tin instance liên tục thay đổi, hãy kiểm tra cấu hình `eureka.instance.instance-id` và log đăng ký.

### 7.3. Kiểm tra từ ứng dụng consumer

Consumer có thể gọi `DiscoveryClient` để xem danh sách instance:

```java
List<ServiceInstance> instances =
    discoveryClient.getInstances("order-service");

instances.forEach(instance -> System.out.printf(
    "service=%s host=%s port=%d uri=%s%n",
    instance.getServiceId(),
    instance.getHost(),
    instance.getPort(),
    instance.getUri()
));
```

`ServiceInstance` cung cấp địa chỉ để gọi instance; không phải mọi implementation đều đưa instance ID vào cùng một thuộc tính chuẩn. Nếu cần quan sát ID, hãy kiểm tra metadata hoặc API riêng của registry, thay vì giả định `getServiceId()` chính là instance ID.

## 8. Xử lý registration trùng và instance cũ

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy một bản sao dù chạy hai tiến trình | Hai tiến trình dùng cùng instance ID hoặc một registration thay thế registration kia | Cấp ID riêng và kiểm tra trường ID trực tiếp trong registry. |
| Hai instance có cùng service name nhưng cùng port | Cấu hình port bị dùng chung trong cùng network namespace hoặc địa chỉ đăng ký không đúng | Cấp port riêng khi chạy cùng host; trong container, xác minh port và địa chỉ mà registry công bố. |
| Instance cũ vẫn xuất hiện sau khi dừng tiến trình | Shutdown không deregister, agent mất kết nối hoặc lease/health check chưa hết hạn | Kiểm tra deregistration, health check, TTL và thời gian dọn registration theo registry. |
| ID đổi sau mỗi lần restart | Dùng UUID hoặc giá trị random làm ID | Chấp nhận nếu instance ephemeral và cleanup hoạt động; nếu cần ổn định, dùng hostname/port hoặc ID do nền tảng cấp. |
| Consumer gọi nhầm địa chỉ | Host/IP công bố không thể truy cập từ consumer | Kiểm tra `ServiceInstance` và cấu hình hostname/IP, port, network của registry client. |
| Instance được đăng ký nhưng không được chọn | Health check không passing hoặc consumer lọc instance theo trạng thái | Kiểm tra health API và chính sách discovery/load balancing. |

Định danh duy nhất không thay thế health check. Một ID khác nhau chỉ giúp registry phân biệt các registration; instance vẫn có thể ở trạng thái unhealthy và bị consumer loại khỏi danh sách phù hợp.

Khi ứng dụng tắt bình thường, registry client thường có cơ chế deregistration theo vòng đời Spring. Với process bị kill đột ngột hoặc node mất mạng, cơ chế health check, lease hoặc TTL giúp phát hiện registration cũ. Hãy cấu hình thời gian phát hiện phù hợp với khả năng chịu lỗi và yêu cầu phục hồi của hệ thống.

## 9. Quy tắc thiết kế instance ID

1. Giữ `spring.application.name` giống nhau cho tất cả bản sao của cùng service.
2. Tạo instance ID duy nhất trong phạm vi registry bằng hostname + port, container/Pod identity hoặc ID do deployment cấp.
3. Không dùng một chuỗi cố định giống nhau cho mọi replica.
4. Quyết định rõ ID có cần ổn định qua restart hay chỉ cần duy nhất trong vòng đời process.
5. Không đưa password, token, thông tin cá nhân hoặc secret vào ID hay metadata.
6. Giữ ID ngắn, dễ đọc và dùng ký tự đơn giản như chữ, số, dấu gạch ngang hoặc dấu hai chấm để thuận tiện cho log và API.
7. Xác minh địa chỉ host/port được công bố có thể truy cập từ health checker và consumer.
8. Kiểm tra cả đăng ký, health status và deregistration; đừng chỉ xác nhận ứng dụng đã khởi động.

## 10. Ghi nhớ

- Service ID xác định nhóm dịch vụ; instance ID phân biệt từng bản sao trong nhóm.
- Consul dùng `spring.cloud.consul.discovery.instance-id`; Eureka dùng `eureka.instance.instance-id`.
- Hostname + port phù hợp cho nhiều tiến trình local/VM; container ID hoặc Pod UID phù hợp với môi trường ephemeral; UUID dễ duy nhất nhưng thay đổi qua restart.
- Mọi bản sao của cùng service nên dùng chung `spring.application.name` và có instance ID riêng.
- Kiểm tra registration qua Consul Catalog/Health API hoặc Eureka Dashboard/REST API, sau đó xác minh consumer nhìn thấy đúng các instance.
- Instance ID duy nhất không bảo đảm instance khỏe; health check và deregistration vẫn cần được cấu hình đúng.

Khi mỗi bản sao có định danh riêng và địa chỉ truy cập chính xác, registry có thể quản lý vòng đời từng instance rõ ràng hơn, còn `DiscoveryClient` và Spring Cloud LoadBalancer có đủ thông tin để tìm và chọn bản sao phù hợp.
