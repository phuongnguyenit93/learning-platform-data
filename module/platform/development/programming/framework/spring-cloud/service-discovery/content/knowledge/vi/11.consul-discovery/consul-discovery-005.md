# Đăng ký service-name, instance-id, địa chỉ và cổng

Khi một ứng dụng đăng ký vào Consul, registry cần biết hai điều: instance thuộc dịch vụ logic nào và consumer phải kết nối tới endpoint nào để gọi instance đó. Spring Cloud Consul biểu diễn thông tin này bằng `service-name`, `instance-id`, `address` và `port`. Nếu các giá trị không đúng, record vẫn có thể xuất hiện trong Consul Catalog nhưng consumer gọi sai service ID, kết nối nhầm host hoặc không tới được cổng ứng dụng.

Trong Spring Cloud, `DiscoveryClient` tra cứu các instance theo service name. Consul lưu từng instance dưới dạng service registration gắn với Consul Agent. Tên service dùng để nhóm nhiều instance; instance ID phân biệt từng registration; address và port tạo thành endpoint mà consumer sử dụng.

## 1. Bốn trường cốt lõi trong một service registration

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| `Name` / service-name | Tên logic của dịch vụ; nhiều instance có thể cùng tên | `inventory-service` |
| `ID` / instance-id | Định danh duy nhất của một registration trên Consul Agent | `inventory-service:inventory-1` |
| `Address` | Hostname hoặc IP mà consumer có thể truy cập | `10.20.0.15` hoặc `inventory-1.internal` |
| `Port` | Cổng ứng dụng đang lắng nghe và có thể truy cập từ consumer | `8081` |

Ví dụ có ba instance của cùng một dịch vụ:

```text
service-name: inventory-service
  ├── instance-id: inventory-1  -> 10.20.0.15:8081
  ├── instance-id: inventory-2  -> 10.20.0.16:8081
  └── instance-id: inventory-3  -> 10.20.0.17:8081
```

Consumer tìm `inventory-service`; Consul trả danh sách các instance đã đăng ký cho tên đó. Load balancer sau đó chọn một instance để gửi request. Không dùng instance ID làm service name khi gọi `DiscoveryClient`, trừ khi ứng dụng chủ động thiết kế service ID theo cách đó.

## 2. service-name: tên logic để consumer tra cứu

Trong Spring Cloud Consul, `spring.cloud.consul.discovery.service-name` xác định tên service được đăng ký. Nếu không cấu hình, giá trị mặc định lấy từ `spring.application.name`.

Ví dụ:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        service-name: inventory-service
```

Trong cấu hình thông thường, có thể bỏ `service-name` vì `spring.application.name` đã cung cấp cùng giá trị. Khai báo tường minh hữu ích khi tên logic trong Consul cần khác tên ứng dụng Spring.

Quy tắc đặt tên nên ổn định, dễ đọc và nhất quán giữa producer với consumer. Ví dụ, nếu producer đăng ký `inventory-service` nhưng consumer tra cứu `inventory`, `getInstances("inventory")` sẽ không tìm được registration dù dashboard Consul đang hiển thị service.

Service name là tên nhóm, không phải địa chỉ mạng và không cần chứa host/port. Tất cả replica của cùng một service nên dùng cùng service name; không đặt `inventory-1`, `inventory-2` làm các service name riêng nếu mục tiêu là load balance qua các replica.

## 3. instance-id: phân biệt từng registration

`spring.cloud.consul.discovery.instance-id` xác định ID mà Spring Cloud Consul gửi cho Consul Agent. Mỗi service registration trên cùng một agent phải có ID riêng. Nếu hai process trên cùng node đăng ký cùng service ID, một registration có thể ghi đè hoặc xung đột với registration còn lại.

Nếu không khai báo, Spring Cloud Consul tạo instance ID mặc định dựa trên tên ứng dụng và thông tin nhận dạng instance; biểu thức mặc định thường có dạng:

```text
${spring.application.name}:${vcap.application.instance_id:${spring.application.instance_id:${random.value}}}
```

Trong môi trường container hoặc orchestrator, nên cân nhắc dùng hostname, pod name hoặc một instance identity được cấp riêng. Giá trị cần ổn định trong vòng đời của một instance và khác nhau giữa các replica đang chạy trên cùng agent.

Ví dụ:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        instance-id: ${spring.application.name}:${HOSTNAME:${random.value}}
```

Trong ví dụ này, biến `HOSTNAME` giúp mỗi container/pod có ID riêng; `${random.value}` là fallback khi biến môi trường không có. Nếu nhiều process cùng chạy trên một host và cùng dùng hostname, hãy cấp thêm biến `INSTANCE_ID` riêng cho từng process:

```yaml
spring:
  cloud:
    consul:
      discovery:
        instance-id: ${spring.application.name}:${INSTANCE_ID:${HOSTNAME:${random.value}}}
```

Không gán cùng một instance ID cố định cho mọi replica. Ngược lại, không tạo ID ngẫu nhiên mới mỗi lần restart nếu quy trình vận hành cần nhận diện một replica ổn định và việc deregister khi shutdown không được bảo đảm. Với container có danh tính riêng, hostname/pod name thường là lựa chọn dễ truy vết.

Consul định danh service theo agent/node. Vì vậy, ID cần duy nhất trên agent nơi service được đăng ký. Trong hệ thống nhiều node, vẫn nên thiết kế ID dễ phân biệt toàn cụm để log, dashboard và công cụ vận hành không gây nhầm lẫn.

## 4. address: địa chỉ mà consumer thật sự truy cập

`spring.cloud.consul.discovery.address` là địa chỉ được đăng ký cho service instance. Có thể cấu hình hostname hoặc IP. Khi không đặt address rõ ràng, Spring Cloud Consul sử dụng thông tin host/interface mà ứng dụng phát hiện được theo cấu hình.

Các thuộc tính liên quan:

| Thuộc tính | Vai trò |
|---|---|
| `spring.cloud.consul.discovery.hostname` | Hostname được dùng khi đăng ký service |
| `spring.cloud.consul.discovery.ip-address` | IP address được dùng khi đăng ký service |
| `spring.cloud.consul.discovery.prefer-ip-address` | Ưu tiên đăng ký IP thay vì hostname khi lựa chọn địa chỉ |

Ví dụ đăng ký IP quảng bá:

```yaml
spring:
  cloud:
    consul:
      discovery:
        prefer-ip-address: true
        ip-address: 10.20.0.15
```

IP `10.20.0.15` chỉ là địa chỉ minh họa trong mạng private. Hãy thay bằng địa chỉ thực sự có thể định tuyến từ consumer. Nếu hạ tầng dùng DNS ổn định, có thể đăng ký hostname thay cho IP:

```yaml
spring:
  cloud:
    consul:
      discovery:
        prefer-ip-address: false
        hostname: inventory-1.internal
```

Điều quan trọng là địa chỉ đăng ký phải được nhìn thấy từ góc mạng của consumer. Một địa chỉ có thể đúng bên trong container nhưng sai với consumer ở mạng khác. Những lỗi phổ biến:

- Đăng ký `127.0.0.1` hoặc `localhost`: consumer sẽ kết nối tới chính máy của nó.
- Đăng ký IP bridge nội bộ chỉ có thể truy cập từ cùng Docker host, trong khi consumer ở node khác.
- Đăng ký hostname chỉ phân giải được bên trong container nhưng consumer không có cùng DNS search domain.
- Đăng ký IP của interface quản trị hoặc interface không nhận traffic ứng dụng.

Đừng nhầm địa chỉ Consul Agent với địa chỉ service. Ứng dụng thường gửi đăng ký tới Consul Agent cục bộ, nhưng `Address` trong registration phải là địa chỉ của ứng dụng mà consumer sẽ gọi, không phải địa chỉ agent trừ khi agent cũng chính là endpoint proxy cho service.

## 5. port: cổng của ứng dụng

`spring.cloud.consul.discovery.port` xác định cổng được ghi vào service registration. Nếu không cấu hình, Spring Cloud Consul lấy cổng server của ứng dụng khi có thể xác định được.

Ví dụ:

```yaml
server:
  port: 8081

spring:
  cloud:
    consul:
      discovery:
        port: 8081
```

Trong nhiều ứng dụng Spring Boot, có thể bỏ thuộc tính `port` vì `server.port` đã là cổng ứng dụng. Đặt tường minh hữu ích khi cổng đăng ký khác cổng HTTP mặc định hoặc khi cần cấu hình endpoint riêng.

Với Docker/Kubernetes, phân biệt cổng bên trong workload và cổng publish qua host:

| Mô hình | Address/Port nên đăng ký |
|---|---|
| Các service giao tiếp trong cùng Docker network | DNS service/container có thể truy cập và cổng container |
| Consumer gọi qua Kubernetes Service | DNS/địa chỉ service và cổng service phù hợp với đường gọi |
| Consumer truy cập trực tiếp pod | Pod IP và container port nếu chính sách mạng cho phép |
| Consumer ở ngoài cluster qua node port/load balancer | Địa chỉ và cổng external mà consumer thực sự gọi được |

Ví dụ: ứng dụng lắng nghe cổng `8081` trong container, còn Docker publish `18081:8081`. Consumer cùng Docker network thường gọi container DNS ở cổng `8081`; consumer bên ngoài host có thể cần host address ở cổng `18081`. Đăng ký sai cặp address/port sẽ khiến Consul trả một endpoint có record hợp lệ nhưng không thể kết nối.

## 6. Cấu hình đầy đủ trong Spring Boot

Ví dụ dưới đây đăng ký một instance `inventory-service` vào Consul Agent tại `localhost:8500`. Địa chỉ service quảng bá được cấu hình qua biến môi trường để mỗi môi trường cung cấp đúng endpoint:

```yaml
server:
  port: ${SERVER_PORT:8081}

spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        deregister: true
        service-name: ${spring.application.name}
        instance-id: ${spring.application.name}:${INSTANCE_ID:${HOSTNAME:${random.value}}}
        prefer-ip-address: true
        ip-address: ${SERVICE_ADVERTISE_IP:10.20.0.15}
        port: ${SERVER_PORT:8081}
        tags:
          - version=v1
          - zone=ap-southeast-1a
        metadata:
          team: inventory
          environment: development
        health-check-path: /actuator/health
        health-check-interval: 10s
```

Trong ví dụ:

- `register: true` cho phép ứng dụng tự đăng ký với Consul khi discovery auto-registration hoạt động.
- `deregister: true` cho phép hủy đăng ký khi ứng dụng shutdown có kiểm soát.
- `service-name` lấy từ `spring.application.name`, giữ tên logic nhất quán.
- `instance-id` dùng biến riêng cho replica; nếu không có, dùng hostname rồi mới fallback sang random value.
- `ip-address` là địa chỉ quảng bá của service, không phải địa chỉ Consul Agent.
- `port` là cổng mà consumer kết nối tới.
- `tags` là danh sách nhãn dạng chuỗi; `metadata` là các cặp key/value bổ sung.
- Health check gọi endpoint Actuator để Consul Agent đánh giá trạng thái instance.

Thay `10.20.0.15` bằng địa chỉ thực tế của môi trường chạy. Trong local, có thể dùng `localhost` nếu consumer chạy cùng máy; trong container, nên dùng DNS/IP trên network chung. Đảm bảo endpoint `/actuator/health` đã được tạo, truy cập được từ Consul Agent và có dependency Actuator phù hợp.

Để đăng ký health check HTTP qua Actuator, thêm dependency Actuator vào ứng dụng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Không expose chi tiết health nhạy cảm ra mạng công khai. Nếu endpoint cần xác thực, cấu hình health-check headers hoặc cơ chế truy cập được hỗ trợ trong phiên bản Spring Cloud Consul đang dùng; bảo đảm agent có thể thực hiện check.

## 7. Consul Agent nhận registration như thế nào?

Spring Cloud Consul giao tiếp với Consul Agent thông qua HTTP API. Agent lưu service registration gắn với node của nó và tham gia đồng bộ dữ liệu vào Consul Catalog.

Một payload API rút gọn có thể trông như sau:

```json
{
  "ID": "inventory-service:inventory-1",
  "Name": "inventory-service",
  "Address": "10.20.0.15",
  "Port": 8081,
  "Tags": ["version=v1", "zone=ap-southeast-1a"],
  "Meta": {
    "team": "inventory",
    "environment": "development"
  },
  "Check": {
    "HTTP": "http://10.20.0.15:8081/actuator/health",
    "Interval": "10s"
  }
}
```

Consul Agent nhận payload này qua endpoint local agent service registration, ví dụ `PUT /v1/agent/service/register`. Spring Cloud Consul tạo payload tương đương từ các thuộc tính đã cấu hình; ứng dụng thông thường không cần tự gọi API này.

Để kiểm tra những service đang được agent cục bộ quản lý:

```bash
curl http://localhost:8500/v1/agent/services
```

Để tra cứu service trong Catalog:

```bash
curl http://localhost:8500/v1/catalog/service/inventory-service
```

Để chỉ lấy instance đang passing health checks:

```bash
curl "http://localhost:8500/v1/health/service/inventory-service?passing=true"
```

`/v1/agent/services` phản ánh các service mà agent cục bộ quản lý. `/v1/catalog/service/{name}` truy vấn catalog theo service name. `/v1/health/service/{name}?passing=true` kết hợp trạng thái health check để lọc endpoint. Ba API này phục vụ các mục đích kiểm tra khác nhau.

## 8. tags và metadata: gắn thông tin cho instance

Service name và instance ID dùng để định danh; tags và metadata bổ sung thông tin để vận hành hoặc lọc instance.

- `tags`: danh sách chuỗi nhãn, thường dùng cho phiên bản, vai trò hoặc nhóm triển khai.
- `metadata`: map key/value; hữu ích cho thông tin như team, environment, build hoặc zone.

Ví dụ:

```yaml
spring:
  cloud:
    consul:
      discovery:
        tags:
          - version=v2
          - canary
        metadata:
          team: inventory
          release: 2026.11
```

Không dùng tag làm nơi lưu secret, token hoặc thông tin cá nhân. Tags/metadata không tự tạo quy tắc routing trong mọi consumer; ứng dụng hoặc Consul query cần chủ động sử dụng chúng. Nếu muốn consumer chỉ chọn canary hoặc một zone, hãy triển khai tiêu chí lọc rõ ràng và kiểm thử danh sách instance đầu vào của LoadBalancer.

## 9. Dùng DiscoveryClient để tra cứu theo service-name

Consumer tra cứu bằng tên logic đã đăng ký. Ví dụ:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class InventoryLocator {

    private final DiscoveryClient discoveryClient;

    InventoryLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

Mỗi `ServiceInstance` chứa thông tin endpoint, service ID và metadata. Consumer có thể đọc host/port hoặc URI:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

for (ServiceInstance instance : instances) {
    System.out.println("service=" + instance.getServiceId());
    System.out.println("host=" + instance.getHost());
    System.out.println("port=" + instance.getPort());
    System.out.println("uri=" + instance.getUri());
    System.out.println("metadata=" + instance.getMetadata());
}
```

Trong ứng dụng thực tế, dùng Spring Cloud LoadBalancer để chọn một instance thay vì tự chọn phần tử đầu tiên. `DiscoveryClient` cung cấp dữ liệu đăng ký; LoadBalancer quyết định instance nào được dùng cho request.

## 10. Các lỗi đăng ký thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Consul có service nhưng consumer tra cứu không thấy | `service-name` ở producer khác với ID consumer truy vấn | Kiểm tra `spring.application.name`, `service-name` và `getServices()` |
| Nhiều replica bị ghi đè hoặc thiếu instance | Các process trên cùng agent dùng trùng `instance-id` | Kiểm tra `/v1/agent/services`; tạo ID riêng cho mỗi replica |
| Service hiện trên Catalog nhưng request timeout | `address` không thể truy cập hoặc `port` sai | Thử kết nối từ chính network namespace của consumer tới `address:port` |
| Consumer gọi nhầm localhost | Registration quảng bá `127.0.0.1`/`localhost` | Đặt hostname/IP có thể định tuyến từ consumer |
| Service đăng ký sai cổng sau khi đổi server port | `spring.cloud.consul.discovery.port` ghi đè hoặc không đồng bộ với `server.port` | So sánh cấu hình hiệu lực với payload Catalog |
| Health check chuyển critical | Path, port, scheme, auth hoặc endpoint Actuator sai | Thử URL từ Consul Agent; xem check output và log ứng dụng |
| Restart tạo registration cũ | Shutdown không deregister hoặc ID thay đổi mỗi lần chạy | Kiểm tra `deregister`, instance ID và critical timeout cleanup |
| Service chỉ có trên một Consul Agent | Producer đăng ký tới agent khác hoặc agent không hoạt động | Kiểm tra `spring.cloud.consul.host`, port và agent local của từng node |

### 10.1. Kiểm tra cấu hình hiệu lực

Spring Boot cho phép profile hoặc biến môi trường ghi đè giá trị trong YAML. Nếu registration không đúng, kiểm tra các biến như `SPRING_APPLICATION_NAME`, `SERVER_PORT`, `CONSUL_HOST`, `SERVICE_ADVERTISE_IP`, `INSTANCE_ID` và `SPRING_CLOUD_CONSUL_DISCOVERY_*`. Không in secret hoặc ACL token vào log.

Actuator có thể hỗ trợ xem configuration properties trong môi trường development nếu endpoint phù hợp được bật và bảo vệ. Không expose `/actuator/env` hoặc `/actuator/configprops` công khai ở production.

## 11. Checklist trước khi đưa service vào Consul

- [ ] `spring.application.name` hoặc `service-name` đúng tên logic mà consumer tra cứu.
- [ ] `instance-id` duy nhất cho từng replica trên cùng Consul Agent.
- [ ] `address` là hostname/IP mà consumer thực sự truy cập được.
- [ ] `port` đúng cổng ứng dụng từ góc mạng của consumer.
- [ ] Đã phân biệt địa chỉ service với địa chỉ Consul Agent.
- [ ] `register` và `deregister` phù hợp với vòng đời ứng dụng.
- [ ] Health check trỏ đúng endpoint, scheme, port và có quyền truy cập.
- [ ] Tags/metadata chỉ chứa thông tin cần thiết, không có secret.
- [ ] Đã kiểm tra agent services, Consul Catalog và health API.
- [ ] Consumer dùng đúng service name và LoadBalancer nhận được danh sách mong đợi.
- [ ] Đã thử nhiều replica, restart, shutdown và tình huống instance mất kết nối.

## Tài liệu tham khảo

- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Configuration Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Consul — Register a Service](https://developer.hashicorp.com/consul/docs/services/usage/register-services)
- [Consul Agent HTTP API — Service Registration](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul HTTP API — Catalog](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul HTTP API — Health](https://developer.hashicorp.com/consul/api-docs/health)
