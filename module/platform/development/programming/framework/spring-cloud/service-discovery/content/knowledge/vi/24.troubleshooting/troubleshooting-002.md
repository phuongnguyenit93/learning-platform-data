# Sai tên dịch vụ hoặc trùng instanceId giữa các bản sao

Khi consumer gọi một service bằng tên logic, chẳng hạn `inventory-service`, Spring Cloud phải tìm đúng nhóm instance đã đăng ký trong registry. Nếu provider đăng ký dưới tên khác, consumer có thể nhận danh sách rỗng dù ứng dụng vẫn chạy. Nếu nhiều bản sao dùng cùng một `instanceId`, registry có thể xem chúng như cùng một registration, làm mất instance, cập nhật nhầm địa chỉ hoặc khiến thao tác heartbeat/deregister tác động tới bản ghi của replica khác.

Hai lỗi này cần được phân biệt. **Service name** xác định nhóm dịch vụ; nhiều instance cùng chia sẻ một service name là hành vi bình thường. **Instance ID** định danh một bản chạy cụ thể trong phạm vi mà registry quy định; các bản sao đang hoạt động đồng thời phải có ID không xung đột trong phạm vi đó.

Bài học thuộc chương `Chẩn đoán sự cố` trong module `SPRING_CLOUD_SERVICE_DISCOVERY`. Module giúp người học hiểu cách tìm instance theo tên dịch vụ qua `DiscoveryClient`, `ServiceRegistry`, Eureka hoặc Consul, cùng vòng đời đăng ký, health check, load balancing, bảo mật và xử lý sai lệch registry. Nội dung này hướng dẫn chẩn đoán service ID sai, instance ID trùng và cách khắc phục trên Eureka, Consul và Zookeeper.

## 1. Phân biệt service name, service ID và instance ID

Trong service discovery có một số định danh gần giống nhau nhưng mang ý nghĩa khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Application name | Tên ứng dụng Spring Boot, thường khai báo bằng `spring.application.name`. | `inventory-service` |
| Service name / service ID | Tên logic mà consumer dùng để tìm một nhóm instance. | `inventory-service` |
| Instance ID | Định danh một bản chạy cụ thể trong registry. | `inventory-service:pod-7f2a` |
| Host/address | Địa chỉ mạng của instance. | `10.10.2.17` |
| Port | Cổng ứng dụng nhận traffic. | `8080` |
| Metadata | Thông tin bổ sung để lọc hoặc định tuyến. | `zone=zone-a`, `version=v2` |

`spring.application.name` thường được dùng làm service name mặc định, nhưng registry integration có thể cho phép override. Instance ID có phạm vi duy nhất khác nhau tùy registry:

| Registry | Service name | Phạm vi cần duy nhất của instance ID |
|---|---|---|
| Eureka | Application name (`appName`). | Trong phạm vi một `appName`. |
| Consul | Service name (`Name`). | Trong phạm vi một Consul agent/node; cùng service name được đăng ký trên nhiều node là bình thường. |
| Zookeeper / Curator | Service name nằm trong nhánh znode. | Trong phạm vi một service path, vì instance ID tạo thành tên znode con. |

Vì phạm vi uniqueness khác nhau, không nên áp dụng một giả định chung như “ID phải duy nhất toàn bộ cluster” cho mọi registry. Hãy hiểu quy tắc của integration đang dùng và thiết kế ID đủ duy nhất cho phạm vi đó.

## 2. Triệu chứng khi service name bị sai

Các dấu hiệu thường gặp:

- `DiscoveryClient.getInstances("inventory-service")` trả về danh sách rỗng.
- `DiscoveryClient.getServices()` không có service mà consumer đang tìm.
- Consumer báo không tìm thấy instance hoặc LoadBalancer không có server để chọn.
- Registry có một service tương tự nhưng tên khác, ví dụ `inventory`, `Inventory-Service` hoặc `inventory-service-v2`.
- Provider và consumer chạy ở profile hoặc môi trường khác nhau, khiến một bên dùng tên override.
- Một ứng dụng có nhiều DiscoveryClient và `CompositeDiscoveryClient` trả kết quả từ registry khác với dự kiến.

Ví dụ provider đăng ký:

```yaml
spring:
  application:
    name: inventory-api
```

Nhưng consumer gọi:

```java
webClient.get()
        .uri("http://inventory-service/api/items")
        .retrieve();
```

Hai tên không khớp. Nếu không có service ID `inventory-service`, LoadBalancer không thể tìm instance dù `inventory-api` đang khỏe.

Các override cần kiểm tra cùng với `spring.application.name`:

| Registry | Property có thể thay đổi tên đăng ký |
|---|---|
| Eureka | `eureka.instance.appname` (application name đăng ký). |
| Consul | `spring.cloud.consul.discovery.service-name`. |
| Zookeeper | Thông thường dùng `spring.application.name` làm service name; kiểm tra custom integration hoặc dependency mapping nếu có. |

Trong Spring Boot, environment variable hoặc command-line argument có thể ghi đè file YAML. Ví dụ `SPRING_APPLICATION_NAME`, `EUREKA_INSTANCE_APPNAME` và `SPRING_CLOUD_CONSUL_DISCOVERY_SERVICE_NAME` có thể khiến giá trị runtime khác với giá trị nhìn thấy trong `application.yml`.

### 2.1. Service name sai không giống lỗi kết nối instance

Phân biệt theo tầng:

| Kết quả kiểm tra | Khả năng cao |
|---|---|
| `getInstances(serviceId)` rỗng và registry không có service ID đó. | Sai tên, provider chưa đăng ký hoặc sai registry/namespace. |
| Registry có service nhưng discovery client không thấy. | Sai server, namespace, profile, cache hoặc quyền đọc registry. |
| Discovery trả instance nhưng host/port không truy cập được. | Địa chỉ đăng ký, network, DNS, firewall hoặc readiness sai. |
| Chỉ thấy một instance dù đang chạy nhiều replica. | Trùng instance ID, đăng ký thất bại hoặc các replica không cùng đăng ký vào registry đang xem. |
| Instance xuất hiện rồi biến mất hoặc đổi địa chỉ bất thường. | Hai process có thể đang ghi cùng một định danh, deregister nhầm hoặc lease/session thay đổi. |

Không đổi instance ID khi lỗi thực tế là host/port không thể truy cập; cũng không sửa network khi consumer đang hỏi sai service ID.

## 3. Triệu chứng khi instanceId bị trùng

Giả sử Deployment chạy ba replica của `inventory-service`:

| Replica | Host | Port | Instance ID |
|---|---|---:|---|
| Pod A | `10.10.1.11` | 8080 | `inventory-1` |
| Pod B | `10.10.1.12` | 8080 | `inventory-1` |
| Pod C | `10.10.1.13` | 8080 | `inventory-3` |

Pod A và Pod B dùng cùng ID. Tùy registry, chúng có thể va chạm vào cùng một registration slot, cùng service ID trên agent hoặc cùng znode path. Kết quả có thể là:

- Registry chỉ hiển thị hai instance thay vì ba.
- Bản ghi có host/port của Pod A rồi bị Pod B cập nhật, hoặc ngược lại.
- Heartbeat từ một replica làm mới lease của bản ghi đang đại diện replica khác.
- Khi một replica shutdown và deregister, registration mà replica còn lại đang dùng có thể bị xóa.
- Metadata hoặc status thay đổi qua lại theo thứ tự các thao tác đăng ký.
- Consumer thấy danh sách instance không ổn định và request lúc thành công lúc thất bại.

Đây là nhóm triệu chứng điển hình của identity collision. Tuy nhiên, số instance ít hơn số replica cũng có thể do provider chưa đăng ký, health check không passing hoặc consumer đọc nhầm registry. Cần xác minh ID trong registry trước khi kết luận.

## 4. Eureka: application name và instance ID

Với Spring Cloud Netflix Eureka, service ID mặc định được lấy từ `spring.application.name`. Instance ID được cấu hình bằng `eureka.instance.instance-id`.

Tài liệu Spring Cloud Netflix mô tả instance ID mặc định theo dạng:

```text
${spring.cloud.client.hostname}:${spring.application.name}:${spring.application.instance_id:${server.port}}
```

Ví dụ:

```text
node-a:inventory-service:8080
```

Eureka xác định một registration bằng cặp application name và instance ID. `instanceId` cần duy nhất trong phạm vi `appName`. Nếu hai replica cùng `appName` dùng cùng `instanceId`, chúng có thể ghi lên cùng một registration.

### 4.1. Cấu hình Eureka với ID riêng cho từng replica

Trong môi trường nhiều replica, nên đưa một định danh riêng của process/container vào instance ID. Với Kubernetes, có thể lấy Pod UID qua Downward API:

```yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

Khai báo biến môi trường trong Deployment:

```yaml
env:
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
```

Pod UID là định danh duy nhất của Pod trong cluster. Mỗi replica vì vậy có instance ID riêng; khi Pod được tạo lại, UID mới cũng tạo registration ID mới. Nếu không chạy trên Kubernetes, có thể dùng instance ID do nền tảng cấp, hostname thực sự duy nhất hoặc một biến môi trường riêng cho từng process.

### 4.2. Kiểm tra Eureka registry

Mở Eureka Dashboard và tìm application name. Kiểm tra số instance, instance ID, hostname, IP, port và status. Có thể dùng REST API:

```bash
curl -H "Accept: application/json" \
  http://eureka-server:8761/eureka/apps/INVENTORY-SERVICE
```

Tên application trên Eureka Dashboard/API thường được hiển thị ở dạng chữ hoa. Hãy đối chiếu tên service thực tế với giá trị mà consumer tra cứu và các normalization rule của integration.

Đọc log của từng replica để xác nhận mỗi process đăng ký với instance ID nào. Nếu hai process log cùng application name và instance ID, cần sửa cấu hình trước khi xóa bản ghi cũ.

## 5. Consul: service name và service ID

Trong Consul, một service registration có `Name`, `ID`, address, port, tags và checks. Spring Cloud Consul mặc định lấy service name từ `spring.application.name`; có thể override bằng `spring.cloud.consul.discovery.service-name`.

Spring Cloud Consul mặc định dùng Spring Application Context ID làm instance ID. Có thể đặt tường minh bằng `spring.cloud.consul.discovery.instance-id`.

Consul yêu cầu service ID duy nhất trên cùng agent. Nhiều node/agent có thể đăng ký cùng service name để tạo một nhóm service instances; đây là cách hoạt động bình thường. Vì vậy, cần phân biệt trùng `Name` (thường mong muốn) với trùng `ID` trên cùng agent (xung đột).

### 5.1. Cấu hình Consul

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        service-name: inventory-service
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

Khi chạy trên Kubernetes, có thể dùng cùng biến `POD_UID` được khai báo qua Downward API. Nếu mỗi Pod có một Consul Agent sidecar riêng, ID vẫn nên ổn định và duy nhất trong agent đó; nếu nhiều instance đăng ký vào cùng một agent, cần bảo đảm ID không trùng trong agent.

### 5.2. Kiểm tra Consul Catalog và health

Đọc service theo tên:

```bash
curl http://consul:8500/v1/catalog/service/inventory-service
```

Đọc các instance cùng health checks:

```bash
curl "http://consul:8500/v1/health/service/inventory-service?passing=false"
```

Kiểm tra các trường `ServiceName`, `ServiceID`, `Address`, `Port`, `Node` và `Checks`. Hai registration cùng service name trên hai node khác nhau là bình thường; hai registration cùng service ID trên một agent cần được điều tra.

Nếu dùng ACL, cần token có quyền đọc Catalog/Health API. Không đưa ACL token thật vào command history hoặc log chia sẻ.

## 6. Zookeeper: service path và instance ID

Spring Cloud Zookeeper thường dùng `spring.application.name` làm service name và lưu các instance dưới root path, mặc định phổ biến là `/services`. Có thể cấu hình `spring.cloud.zookeeper.discovery.root` và `spring.cloud.zookeeper.discovery.instance-id`.

Cấu trúc znode khái quát:

```text
/services
  /inventory-service
    /inventory-pod-a
    /inventory-pod-b
    /inventory-pod-c
```

Curator Service Discovery lưu instance theo cấu trúc `base path / service name / instance id`. Vì vậy, nếu hai replica cùng service name và instance ID, chúng nhắm tới cùng một znode path.

Spring Cloud Zookeeper hiện có property `spring.cloud.zookeeper.discovery.instance-id`; tài liệu cấu hình mô tả mặc định là UUID ngẫu nhiên trong một số phiên bản. Tài liệu discovery cũng mô tả instance ID theo Spring Context ID. Hãy xác minh default của release train đang dùng thay vì dựa vào giả định giữa các phiên bản. Dù dùng default, cần bảo đảm ID thực tế của các replica đang chạy không trùng.

Ví dụ cấu hình tường minh:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1:2181,zk-2:2181,zk-3:2181
      discovery:
        root: /services/production
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

Kiểm tra znode:

```text
ls /services/production
ls /services/production/inventory-service
get /services/production/inventory-service/<instance-id>
```

Nếu hai process cùng ghi một service path và instance ID, chúng có thể va chạm ở cùng node. Cách xử lý cụ thể phụ thuộc registration mode và Curator/Spring Cloud Zookeeper version; không giả định hai process sẽ được lưu thành hai instance độc lập.

## 7. Thiết kế instance ID đúng

Một instance ID tốt cần đáp ứng:

1. **Duy nhất trong phạm vi registry yêu cầu:** Eureka theo appName, Consul theo agent, Zookeeper theo service path.
2. **Ổn định trong vòng đời process:** heartbeat, update và deregistration phải tham chiếu cùng một ID.
3. **Khác nhau giữa replica đồng thời:** không chỉ dùng service name hoặc một giá trị cấu hình chung cho mọi Pod.
4. **Có thể truy vết:** từ ID có thể tìm ra Pod, container hoặc node tương ứng.
5. **Không chứa bí mật:** ID có thể xuất hiện trong Dashboard, log và API registry.

Các nguồn ID thường dùng:

| Nguồn | Ưu điểm | Lưu ý |
|---|---|---|
| Kubernetes Pod UID | Duy nhất cho mỗi Pod và có thể truy vết qua Kubernetes API. | Pod mới sau rollout có UID mới; cần truyền qua Downward API. |
| Hostname + port | Dễ cấu hình, hữu ích trên VM hoặc bare metal. | Hostname có thể trùng hoặc không ổn định; nhiều process trên cùng host cần port khác nhau. |
| Container ID | Phân biệt container trên cùng host. | ID thay đổi khi container được tạo lại; có thể dài, cần chuẩn hóa. |
| Platform instance ID | Phù hợp PaaS/Cloud Foundry/Kubernetes operator. | Phải bảo đảm giá trị được inject khác nhau cho từng replica. |
| UUID ngẫu nhiên lúc startup | Dễ tạo uniqueness khi không có ID nền tảng. | Khó truy vết và thay đổi sau restart; cần xử lý stale registration theo lifecycle/lease. |

Không nên dùng riêng `spring.application.name` làm instance ID vì tất cả replica của cùng service sẽ có cùng giá trị. Cũng không nên dùng một biến `INSTANCE_ID` tĩnh được copy giống nhau trong manifest cho mọi replica.

### 7.1. Phân biệt instance ID và metadata

Không đưa mọi thông tin vào ID. Dùng metadata cho dữ liệu có thể thay đổi hoặc cần lọc:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
      version: v2
      pod-name: ${HOSTNAME}
```

Instance ID nên định danh một bản chạy; metadata mô tả bản chạy đó. Nếu version hoặc zone thay đổi, không nhất thiết phải thay ID nếu process vẫn là cùng instance theo lifecycle của registry.

## 8. Kiểm tra service name ở provider và consumer

Khi consumer không tìm thấy service, kiểm tra theo thứ tự:

1. **Provider config:** đọc `spring.application.name` và các override của registry integration.
2. **Consumer target:** kiểm tra service ID trong URL `http://<service-id>` hoặc tham số `getInstances(serviceId)`.
3. **Environment/profile:** so sánh `application.yml`, profile file, environment variables, command-line arguments và config server.
4. **Registry endpoint:** xác nhận provider và consumer đang dùng cùng Eureka cluster, Consul datacenter/namespace hoặc Zookeeper root/ensemble.
5. **Danh sách services:** gọi `DiscoveryClient.getServices()` để xem tên mà client thực sự biết.
6. **Instance list:** gọi `getInstances()` với đúng service ID và kiểm tra host, port, metadata.
7. **Health state:** kiểm tra registry có lọc instance không passing hoặc không `UP` không.
8. **Cache/refresh:** kiểm tra thời điểm provider đăng ký và lần consumer refresh gần nhất.

Ví dụ endpoint chẩn đoán trong ứng dụng:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class DiscoveryDiagnostics {

    private final DiscoveryClient discoveryClient;

    public DiscoveryDiagnostics(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> services() {
        return discoveryClient.getServices();
    }

    public List<ServiceInstance> instances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
```

Chỉ expose endpoint chẩn đoán này trong môi trường quản trị có xác thực; danh sách service và host/port là thông tin hạ tầng nội bộ.

## 9. Kiểm tra trùng instance ID ở từng registry

### 9.1. Eureka

- Mở application trong Dashboard và đếm instance.
- So sánh `instanceId` của từng replica.
- Kiểm tra `eureka.instance.instance-id` và giá trị placeholder sau khi resolve.
- Đối chiếu appName; cùng ID ở hai appName khác nhau không phải cùng một Eureka registration.
- Kiểm tra log register, heartbeat và cancel của từng process.
- Dùng REST API để xác nhận server đang lưu host/port nào cho ID đó.

Eureka dùng cặp appName/instanceId để đăng ký, renew và cancel. Vì vậy, khi hai process dùng cùng cặp này, một process có thể ghi đè thông tin của process kia; khi một process cancel, bản ghi chung có thể bị xóa dù process còn lại vẫn chạy.

### 9.2. Consul

- Kiểm tra `ServiceName`, `ServiceID` và `Node` trong Catalog.
- Xác định các registration có cùng Service ID nằm trên cùng Consul agent hay không.
- So sánh cấu hình `spring.cloud.consul.discovery.instance-id` trên từng replica.
- Kiểm tra local agent logs để xem service registration bị update hoặc deregister.
- Đối chiếu health checks để phân biệt ID collision với service `critical`.

Consul cho phép cùng service name xuất hiện trên nhiều node; service ID cần duy nhất trên mỗi agent. Nếu hai process đăng ký cùng ID vào một agent, registration cục bộ có thể được cập nhật/thay thế thay vì tạo hai service độc lập.

### 9.3. Zookeeper

- Xác nhận `spring.cloud.zookeeper.discovery.root` giống nhau ở provider và consumer.
- Liệt kê child nodes dưới service path.
- So sánh instance ID trong log từng replica với tên znode.
- Kiểm tra payload của znode để xác định host/port đang được công bố.
- Kiểm tra session, ephemeral node và deregistration khi process dừng.

Curator dùng service name và instance ID để xác định path registration. Cùng cặp name/ID dẫn tới cùng path, vì vậy không thể đại diện cho hai instance độc lập cùng lúc.

## 10. Khắc phục khi phát hiện sai tên hoặc ID trùng

Thực hiện theo thứ tự để tránh xóa nhầm registration đang hoạt động:

**Bước 1 – Ghi nhận trạng thái hiện tại.** Lưu service name, instance ID, host, port, node/Pod, status và timestamp từ registry.

**Bước 2 – Xác định process sở hữu ID.** Đối chiếu log từng replica, hostname, Pod UID và deployment metadata. Không suy luận chỉ từ một dòng Dashboard.

**Bước 3 – Sửa nguồn cấu hình.** Sửa `spring.application.name` hoặc registry-specific service name nếu provider đăng ký sai; sửa instance ID nếu nhiều replica dùng cùng ID.

**Bước 4 – Deploy cấu hình mới.** Bảo đảm mỗi replica nhận giá trị ID riêng sau khi placeholder/environment được resolve. Kiểm tra ít nhất hai replica đồng thời.

**Bước 5 – Xác nhận registration mới.** Registry phải hiển thị đủ số instance, mỗi ID khác nhau trong phạm vi cần thiết và host/port đúng.

**Bước 6 – Xóa bản ghi cũ có kiểm soát.** Chỉ deregister registration stale sau khi xác minh process tương ứng đã dừng hoặc ID cũ không còn được dùng. Không xóa bằng tay ID đang được một replica khỏe sử dụng.

**Bước 7 – Xác minh consumer.** Gọi `getServices()` và `getInstances(serviceId)`, sau đó gửi request qua LoadBalancer để kiểm tra nhiều replica có thể được chọn.

**Bước 8 – Theo dõi sau deploy.** Quan sát heartbeat, health checks, số instance, lỗi request và thời gian hội tụ cache.

## 11. Bảng lỗi và hướng xử lý nhanh

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer không tìm thấy service | `spring.application.name` hoặc service override sai. | Chuẩn hóa service name ở provider/consumer và kiểm tra `getServices()`. |
| Service xuất hiện dưới hai tên | Profile hoặc environment override khác nhau. | So sánh cấu hình đã resolve trên từng replica. |
| Eureka chỉ có một instance dù nhiều replica | Trùng appName/instanceId. | Tạo instance ID riêng trong phạm vi appName. |
| Consul chỉ giữ một registration trên cùng agent | Trùng service ID trên agent. | Đặt ID riêng cho mỗi process đăng ký vào agent đó. |
| Zookeeper chỉ có một child node cho hai replica | Trùng service name/instance ID tạo cùng znode path. | Tạo instance ID riêng theo replica. |
| Registry có instance nhưng consumer không thấy | Consumer dùng sai registry, namespace/root hoặc cache cũ. | Kiểm tra endpoint, namespace, refresh và DiscoveryClient. |
| Instance hiển thị đúng nhưng gọi không được | Host/port sai hoặc network không thông. | Kiểm tra address, port, DNS, firewall và readiness. |
| Instance biến mất khi một replica shutdown | Hai replica dùng chung ID và một replica deregister registration chung. | Sửa ID trước, sau đó đăng ký lại và dọn stale record. |
| Instance cũ còn sau rollout | Deregistration/lease/session chưa kết thúc hoặc cache chưa refresh. | Kiểm tra lifecycle, lease/session và cache; dọn stale entry có kiểm soát. |
| ID thay đổi mỗi lần restart và khó truy vết | Dùng UUID ngẫu nhiên mà không ghi metadata nhận diện. | Dùng platform ID hoặc ghi hostname/Pod UID trong metadata. |

## 12. Kiểm thử nhiều replica trước khi triển khai

Một kiểm thử đơn giản nên chạy ít nhất hai replica cùng service name:

1. Khởi động replica A và B đồng thời.
2. Xác nhận cả hai đăng ký cùng service name.
3. Xác nhận instance ID khác nhau theo uniqueness scope của registry.
4. Kiểm tra host/port của mỗi registration trỏ đúng replica.
5. Dừng replica A một cách graceful.
6. Xác nhận chỉ registration của A bị gỡ; B vẫn tồn tại và healthy.
7. Khởi động lại A hoặc tạo replica C.
8. Xác nhận registration mới không ghi đè B.
9. Gọi consumer qua LoadBalancer và quan sát các instance có thể được chọn.

Trong test tự động, có thể kiểm tra số instance và tập ID:

```java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class DiscoveryRegistrationTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void replicasHaveUniqueIds() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("inventory-service");

        Set<String> instanceIds = instances.stream()
                .map(ServiceInstance::getInstanceId)
                .collect(Collectors.toSet());

        assertThat(instances).hasSize(2);
        assertThat(instanceIds).hasSize(2);
    }
}
```

Đoạn test giả định registry implementation cung cấp `instanceId` qua `ServiceInstance` và cả hai replica đã đăng ký/health-passing. Nếu một integration không cung cấp instance ID theo cách đó, hãy kiểm tra trường ID native trong registry response.

## 13. Quan sát và phòng ngừa

Nên ghi nhận các trường sau trong log đăng ký khi khởi động:

- Service name/service ID sau khi resolve.
- Instance ID sau khi resolve.
- Host/IP và port công bố.
- Active profile và namespace/datacenter/root path.
- Registry endpoint hoặc agent mà client kết nối.
- Registration success/failure và timestamp.

Không ghi credential hoặc token registry. Với metric, theo dõi số instance theo service, tỷ lệ discovery rỗng, số registration/deregistration, health state và lỗi heartbeat.

Các biện pháp phòng ngừa:

1. Dùng một service name chuẩn, dạng DNS label chữ thường và thống nhất giữa provider, consumer, deployment và tài liệu.
2. Chỉ override service name khi có lý do rõ ràng; ghi lại override để consumer dùng đúng ID.
3. Tạo instance ID từ định danh riêng của replica, chẳng hạn Pod UID hoặc platform instance ID.
4. Không dùng `spring.application.name` đơn lẻ làm instance ID.
5. Kiểm tra uniqueness scope riêng của Eureka, Consul và Zookeeper.
6. Không hardcode một instance ID giống nhau trong manifest được nhân bản.
7. Kiểm thử scale lên ít nhất hai replica và shutdown từng replica.
8. Theo dõi registration, heartbeat, health check và deregistration.
9. Dọn stale record chỉ sau khi xác minh process sở hữu đã dừng.
10. Bảo vệ endpoint chẩn đoán vì service catalog tiết lộ topology nội bộ.

## 14. Checklist chẩn đoán

| Câu hỏi | Kết quả mong đợi |
|---|---|
| Provider đăng ký service name nào? | Tên đã resolve khớp tên consumer tìm. |
| Consumer gọi service ID nào? | Khớp chính xác registry integration và namespace. |
| `getServices()` có service đó không? | Có tên service mong đợi. |
| `getInstances(serviceId)` trả bao nhiêu instance? | Phù hợp số replica khỏe đang chạy. |
| Mỗi replica có instance ID nào? | Khác nhau trong phạm vi registry yêu cầu. |
| Host/port có đúng không? | Mỗi ID trỏ tới đúng replica. |
| Registry nào đang được dùng? | Provider và consumer đọc/ghi đúng cluster, datacenter hoặc root. |
| Health có passing/UP không? | Instance đủ điều kiện được discovery/load balance. |
| Có stale registration không? | Bản ghi cũ được nhận diện và xử lý sau xác minh. |
| Khi một replica dừng, replica còn lại có tồn tại không? | Deregistration không xóa nhầm registration khác. |

## Kết luận

Service name xác định nhóm dịch vụ; instance ID định danh từng bản chạy trong phạm vi registry. Nhiều replica dùng chung service name là đúng thiết kế, nhưng chúng phải có instance ID không xung đột: Eureka yêu cầu duy nhất trong phạm vi application name, Consul yêu cầu service ID duy nhất trên mỗi agent, còn Zookeeper dùng cặp service name/instance ID để tạo đường dẫn znode.

Khi consumer không tìm thấy service, hãy so sánh service name đã resolve ở provider và consumer, kiểm tra danh sách `DiscoveryClient.getServices()` và xác nhận registry/namespace đang dùng. Khi số instance ít hơn số replica hoặc bản ghi đổi địa chỉ bất thường, kiểm tra instance ID, host/port, log register/heartbeat/deregister và quy tắc uniqueness của registry. Dùng định danh riêng theo replica như Kubernetes Pod UID, kiểm thử ít nhất hai replica và chỉ xóa stale registration sau khi xác minh process sở hữu đã dừng.

## Tài liệu tham khảo

- [Spring Cloud Netflix – Changing the Eureka Instance ID](https://docs.spring.io/spring-cloud-netflix/docs/current/reference/html/index.html): service ID mặc định, instance ID mặc định và cách cấu hình ID duy nhất theo appName.
- [Spring Cloud Netflix – Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html): `eureka.instance.instance-id` và phạm vi duy nhất trong appName.
- [Spring Cloud Consul – Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html): service name, instance ID mặc định và cấu hình `service-name`/`instance-id`.
- [Consul Agent Service API](https://developer.hashicorp.com/consul/api-docs/agent/service): service ID phải duy nhất trên mỗi agent.
- [Consul Service Definition](https://developer.hashicorp.com/consul/docs/reference/service): service name và ID, phạm vi ID theo node.
- [Spring Cloud Zookeeper – Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html): service name, instance ID và port mặc định.
- [Spring Cloud Zookeeper – Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html): `spring.cloud.zookeeper.discovery.instance-id` và root path.
- [Apache Curator – Service Discovery](https://curator.apache.org/docs/service-discovery/): cấu trúc base path/service/instance ID và API đăng ký, hủy đăng ký.
