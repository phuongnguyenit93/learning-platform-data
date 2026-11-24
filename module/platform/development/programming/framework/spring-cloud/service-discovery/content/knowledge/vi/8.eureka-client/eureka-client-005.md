# Cấu hình instanceId, hostname và prefer-ip-address

Khi một ứng dụng Spring Cloud đăng ký với Eureka Server, registry cần phân biệt từng bản chạy và biết consumer phải kết nối đến địa chỉ nào. Ba thuộc tính thường được cấu hình cùng nhau là `eureka.instance.instance-id`, `eureka.instance.hostname` và `eureka.instance.prefer-ip-address`.

`instance-id` nhận diện một instance cụ thể. `hostname` cung cấp tên máy được công bố. `prefer-ip-address` quyết định Eureka ưu tiên dùng hostname hay địa chỉ IP trong thông tin instance được đăng ký. Cấu hình sai có thể khiến nhiều replica ghi đè bản ghi của nhau hoặc khiến Eureka hiển thị instance `UP` nhưng consumer không thể kết nối.

Trong module `SPRING_CLOUD_SERVICE_DISCOVERY`, các thuộc tính này thuộc phần cấu hình Eureka Client và gắn trực tiếp với mục tiêu khám phá instance theo tên dịch vụ. Cần phân biệt tên dịch vụ logic, mã instance và địa chỉ mạng: chúng giải quyết ba nhu cầu khác nhau.

## 1. Ba thông tin có vai trò khác nhau

Một service có thể chạy nhiều instance. Ví dụ `payment-service` có ba replica:

| Thông tin | Ví dụ | Mục đích |
|---|---|---|
| Service name | `payment-service` | Nhóm các instance cùng cung cấp một dịch vụ logic; thường lấy từ `spring.application.name`. |
| Instance ID | `payment-service:pay-02:8082` | Phân biệt một bản chạy cụ thể trong nhóm service. |
| Hostname/IP | `payment-02.internal.example` hoặc `10.20.0.22` | Địa chỉ host mà consumer dùng để kết nối. |
| Port | `8082` | Cổng mà instance phục vụ giao thức tương ứng. |

Trong Eureka, các instance cùng service name được nhóm trong một application. Mỗi instance có thông tin riêng, thường được biểu diễn bởi `InstanceInfo`, bao gồm instance ID, hostname, IP, port, trạng thái và metadata.

Consumer tra cứu theo service name, ví dụ `payment-service`. Eureka client cung cấp danh sách instance phù hợp; Spring Cloud LoadBalancer chọn một instance và sử dụng host/port để gửi request. `instance-id` giúp registry quản lý đúng bản ghi, nhưng không phải địa chỉ để consumer kết nối.

## 2. Cấu hình `eureka.instance.instance-id`

`eureka.instance.instance-id` là mã định danh của một instance trong Eureka. Mỗi replica đang chạy đồng thời của cùng một application cần có ID riêng để registry có thể phân biệt các bản ghi.

Ví dụ:

```yaml
spring:
  application:
    name: payment-service

server:
  port: 8082

eureka:
  instance:
    instance-id: payment-service:payment-02:8082
```

Trong ví dụ này:

- `payment-service` là tên application.
- `payment-02` là định danh của replica.
- `8082` là port ứng dụng sử dụng.

Định dạng ID không bị giới hạn ở ví dụ trên. Có thể tạo ID từ hostname, pod name, container ID, UID của workload hoặc một mã do pipeline triển khai cấp. Điều quan trọng là ID duy nhất trong phạm vi các instance cùng application đang hoạt động và ổn định trong vòng đời của một instance.

### 2.1. Vì sao instance ID phải duy nhất?

Eureka dùng kết hợp application name và instance ID để xác định bản ghi khi nhận đăng ký, heartbeat, cập nhật trạng thái và hủy đăng ký. Nếu nhiều replica cùng đăng ký một ID trong cùng application, các thao tác có thể tác động lên cùng một bản ghi. Dashboard có thể chỉ hiển thị một instance hoặc dữ liệu của instance này bị instance khác cập nhật.

Các lỗi thường gặp:

- Dùng cố định `payment-service` làm instance ID cho mọi replica.
- Chỉ dùng `server.port` trong khi nhiều container cùng chạy port nội bộ giống nhau.
- Đặt cùng một biến môi trường `INSTANCE_ID` cho tất cả pod.
- Tạo ID thay đổi liên tục trong một tiến trình khiến việc truy vết đăng ký khó khăn.

### 2.2. Tạo ID theo môi trường triển khai

Với VM hoặc máy chủ có hostname riêng, có thể tạo ID từ service name, hostname và port:

```yaml
eureka:
  instance:
    instance-id: "${spring.application.name}:${spring.cloud.client.hostname}:${server.port}"
```

Với container hoặc Kubernetes, có thể truyền một định danh riêng cho từng workload:

```yaml
eureka:
  instance:
    instance-id: "${spring.application.name}:${INSTANCE_ID:${HOSTNAME:local}}:${server.port}"
```

`INSTANCE_ID` nên được nền tảng triển khai cung cấp với giá trị riêng cho từng replica. `HOSTNAME` trong container thường là tên container hoặc pod; cần xác minh giá trị thực tế thay vì mặc định nó là một DNS name có thể truy cập từ consumer.

Nếu cùng một máy chạy nhiều instance có cùng hostname và port nội bộ, hãy thêm PID, container ID, pod UID hoặc mã replica vào ID. Tránh chỉ dựa vào hostname khi hostname đó được chia sẻ giữa nhiều tiến trình.

### 2.3. ID duy nhất nhưng vẫn có thể truy vết

Một ID ngẫu nhiên có thể giảm nguy cơ trùng, nhưng người vận hành sẽ khó liên hệ bản ghi với workload. Nên chọn cấu trúc ID đủ thông tin để tìm đúng instance, ví dụ:

```text
payment-service:payments-7f9c8d6b6f-k2m4p:8082
```

Không đưa password, token, thông tin cá nhân hoặc dữ liệu nhạy cảm vào instance ID. ID thường xuất hiện trong dashboard, log và API registry.

## 3. Cấu hình `eureka.instance.hostname`

`eureka.instance.hostname` đặt hostname mà Eureka client công bố cho instance. Nếu không cấu hình rõ, client thường suy ra hostname từ môi trường chạy. Giá trị tự phát hiện có thể không phù hợp khi máy có nhiều network interface, chạy trong container hoặc có DNS nội bộ riêng.

Ví dụ khai báo hostname:

```yaml
spring:
  application:
    name: payment-service

server:
  port: 8082

eureka:
  instance:
    hostname: payment-02.internal.example
    prefer-ip-address: false
    instance-id: "${spring.application.name}:payment-02:${server.port}"
```

Khi ưu tiên hostname, consumer nhận địa chỉ dạng DNS name trong thông tin instance. Consumer phải phân giải được tên này bằng DNS hoặc cơ chế phân giải tên tương ứng và phải có đường mạng đến IP mà tên đó trả về.

### 3.1. Hostname phải được nhìn thấy từ phía consumer

Hostname có thể hợp lệ trên máy provider nhưng không có nghĩa là consumer khác truy cập được. Ví dụ:

- `localhost` và `127.0.0.1` chỉ trỏ về chính máy hoặc container của consumer.
- Hostname chỉ tồn tại trong `/etc/hosts` của provider không tự động tồn tại trong consumer.
- Tên DNS của một subnet có thể không phân giải được từ VPC hoặc cluster khác.
- Hostname trỏ đến IP management có thể không mở port nghiệp vụ cho consumer.

Hãy kiểm tra phân giải DNS từ môi trường consumer thực tế. Nếu service chạy trong Kubernetes, hostname pod có thể chỉ ổn định và phân giải được khi dùng StatefulSet/headless Service hoặc DNS record được cấu hình phù hợp. Với Deployment thông thường, pod có thể được tạo lại với tên và IP mới.

### 3.2. Hostname và địa chỉ bind là hai việc riêng

`server.address` điều khiển interface mà web server Spring Boot lắng nghe. `eureka.instance.hostname` điều khiển hostname trong thông tin đăng ký. Ví dụ, ứng dụng có thể bind trên `0.0.0.0:8082` nhưng công bố `payment-02.internal.example` cho consumer.

Không công bố `0.0.0.0` như địa chỉ đích. Đây là địa chỉ wildcard dùng để bind trên mọi IPv4 interface, không phải host mà consumer nên gọi.

## 4. Cấu hình `eureka.instance.prefer-ip-address`

`eureka.instance.prefer-ip-address` quyết định Eureka client ưu tiên công bố IP thay cho hostname trong thông tin instance.

| Giá trị | Hành vi khái quát |
|---|---|
| `false` | Ưu tiên hostname được cấu hình hoặc được phát hiện. Đây là giá trị mặc định thường dùng. |
| `true` | Ưu tiên địa chỉ IP của instance. Nếu có `eureka.instance.ip-address`, giá trị được cấu hình rõ ràng có thể được sử dụng; nếu không, client dựa trên địa chỉ IP được phát hiện. |

Ví dụ:

```yaml
eureka:
  instance:
    prefer-ip-address: true
```

Khi bật cờ này, cần bảo đảm IP được chọn có thể định tuyến từ consumer. Một máy có thể có nhiều interface như management, storage, public và application network. Nếu client chọn nhầm interface, registry có thể chứa IP hợp lệ trên máy provider nhưng không truy cập được từ các service khác.

### 4.1. Chỉ định IP rõ ràng bằng `eureka.instance.ip-address`

Nếu biết chính xác địa chỉ mà consumer có thể truy cập, có thể cấu hình IP tường minh:

```yaml
eureka:
  instance:
    ip-address: 10.20.0.22
    prefer-ip-address: true
```

Khi dùng biến môi trường:

```yaml
eureka:
  instance:
    ip-address: ${EUREKA_INSTANCE_IP:10.20.0.22}
    prefer-ip-address: true
```

Không nên ghi cứng IP của một máy vào cấu hình dùng chung cho mọi replica. Nếu mỗi pod có IP riêng, nền tảng triển khai phải truyền IP phù hợp cho từng pod hoặc để client phát hiện theo cơ chế đã được kiểm soát.

### 4.2. Tự phát hiện IP và chọn network interface

Nếu không đặt `eureka.instance.ip-address`, Spring Cloud có thể dùng thông tin mạng được phát hiện từ môi trường. Trong máy có nhiều interface, có thể cấu hình `spring.cloud.inetutils` để giới hạn địa chỉ được ưu tiên hoặc bỏ qua interface không mong muốn.

Ví dụ minh họa:

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '10\.20\..*'
      ignored-interfaces:
        - 'docker0'
        - 'veth.*'

eureka:
  instance:
    prefer-ip-address: true
```

`preferred-networks` và `ignored-interfaces` sử dụng biểu thức chính quy để chọn hoặc bỏ qua network tương ứng. Cấu hình cụ thể cần khớp tên interface và dải IP trong môi trường thực tế. Sau khi thay đổi, hãy kiểm tra IP được công bố trên registry; không suy luận rằng cấu hình đã có hiệu lực chỉ từ việc ứng dụng khởi động thành công.

## 5. Kết hợp ba thuộc tính trong một cấu hình

Ví dụ dưới đây cấu hình một instance `payment-service` dùng hostname:

```yaml
spring:
  application:
    name: payment-service

server:
  port: 8082

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
  instance:
    hostname: ${EUREKA_INSTANCE_HOSTNAME:payment-01.internal.example}
    prefer-ip-address: false
    instance-id: "${spring.application.name}:${INSTANCE_ID:payment-01}:${server.port}"
```

Nếu consumer cần kết nối trực tiếp bằng IP, có thể thay phần instance bằng:

```yaml
eureka:
  instance:
    ip-address: ${EUREKA_INSTANCE_IP:10.20.0.21}
    prefer-ip-address: true
    instance-id: "${spring.application.name}:${INSTANCE_ID:payment-01}:${server.port}"
```

Trong cấu hình thực tế, các giá trị `INSTANCE_ID`, `EUREKA_INSTANCE_HOSTNAME` hoặc `EUREKA_INSTANCE_IP` phải được cấp theo từng replica. Cùng một file cấu hình có thể được tái sử dụng, nhưng dữ liệu môi trường không được giống nhau ở những trường cần phân biệt từng instance.

`defaultZone` trong ví dụ là địa chỉ Eureka Server mà client kết nối để đăng ký và tải registry. Nó khác với hostname/IP được công bố trong `eureka.instance`: một giá trị xác định registry endpoint, giá trị còn lại xác định service endpoint.

## 6. Chọn cấu hình theo môi trường

| Môi trường | Cách cấu hình thường phù hợp | Lưu ý |
|---|---|---|
| VM có DNS nội bộ | Đặt `hostname`, `prefer-ip-address: false`. | DNS phải phân giải được từ mọi consumer. |
| VM có IP private ổn định | Đặt `ip-address`, `prefer-ip-address: true`. | IP phải được định tuyến và mở port giữa các subnet. |
| Máy có nhiều network interface | Dùng `preferred-networks`/`ignored-interfaces` hoặc đặt IP rõ ràng. | Tránh chọn nhầm management/storage interface. |
| Docker Compose cùng network | Dùng hostname/container DNS phù hợp hoặc IP trong network chung. | Không công bố `localhost` hoặc bridge IP chỉ host truy cập được. |
| Kubernetes Deployment | Dùng Pod IP nếu registry quản lý từng pod; tạo ID riêng theo pod. | Pod IP và hostname có thể đổi khi pod được thay thế. |
| Kubernetes StatefulSet | Có thể dùng DNS ổn định theo ordinal/headless Service. | Đảm bảo consumer phân giải được FQDN trong cluster. |
| Consumer ở mạng khác | Dùng DNS hoặc IP routable qua network liên kết/gateway. | Kiểm tra firewall, routing và TLS. |

Không có một giá trị `prefer-ip-address` phù hợp cho tất cả hệ thống. Cần chọn dựa trên cách consumer kết nối đến provider và cách hạ tầng quản lý địa chỉ.

## 7. Những sai lầm thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Eureka chỉ hiển thị một instance dù chạy nhiều replica | Các replica dùng cùng `instance-id` trong một application. | Tạo ID riêng cho mỗi pod/container/tiến trình. |
| Instance xuất hiện nhưng consumer không gọi được | Hostname không phân giải được hoặc IP không routable từ consumer. | Kiểm tra DNS, route và port từ môi trường consumer. |
| Eureka công bố `localhost` hoặc `127.0.0.1` | Client phát hiện loopback hoặc cấu hình hostname sai. | Đặt hostname/IP được consumer truy cập. |
| Eureka công bố `0.0.0.0` | Nhầm bind address với advertised address. | Cấu hình hostname/IP riêng; giữ wildcard chỉ cho bind nếu cần. |
| IP công bố thuộc interface management | Client tự phát hiện nhầm interface. | Đặt `ip-address` rõ ràng hoặc cấu hình `spring.cloud.inetutils`. |
| Instance ID thay đổi không cần thiết sau mỗi lần khởi động | Dùng giá trị ngẫu nhiên hoặc nguồn định danh không ổn định. | Dùng pod UID/container ID/hostname phù hợp với vòng đời triển khai. |
| Hai pod có cùng hostname và port nhưng khác workload | ID chỉ gồm hostname và port. | Thêm pod UID, container ID hoặc một mã replica duy nhất. |
| HTTPS lỗi xác thực chứng thư | Consumer kết nối bằng hostname/IP không khớp SAN trong certificate. | Cấp chứng thư phù hợp với địa chỉ được công bố; giữ hostname verification bật. |

## 8. Kiểm tra thông tin Eureka đã nhận

Sau khi cấu hình, cần kiểm tra cả thông tin trên registry và khả năng kết nối từ consumer.

### 8.1. Kiểm tra trên Eureka Dashboard

Mở Eureka Dashboard trong mạng quản trị và tìm application tương ứng, ví dụ `PAYMENT-SERVICE`. Kiểm tra từng instance:

- Instance ID có khác nhau giữa các replica hay không.
- Hostname hoặc IP được công bố có đúng như dự kiến không.
- Port có khớp với port mà ứng dụng thực sự phục vụ không.
- Trạng thái instance có phù hợp với tình trạng health không.

Nếu dashboard chỉ hiển thị một replica, kiểm tra `instance-id` trước khi điều tra load balancer. Nếu dashboard hiển thị nhiều replica nhưng request thất bại, kiểm tra host/port và mạng.

### 8.2. Kiểm tra bằng API registry

Trong môi trường được phép truy cập, Eureka REST API có thể trả về thông tin application:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/PAYMENT-SERVICE
```

Đường dẫn và cơ chế xác thực có thể thay đổi theo context path và cấu hình bảo mật. Hãy kiểm tra các trường `instanceId`, `hostName`, `ipAddr`, `port` và `status` trong dữ liệu trả về. Không công khai API registry ra Internet nếu không có lớp bảo vệ phù hợp.

### 8.3. Kiểm tra từ consumer

Consumer có thể dùng `DiscoveryClient` để xem địa chỉ mà ứng dụng thực sự nhận được:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentDiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    public PaymentDiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void printInstances() {
        for (ServiceInstance instance :
                discoveryClient.getInstances("payment-service")) {
            System.out.printf(
                    "serviceId=%s, instanceId=%s, host=%s, port=%d, uri=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.getUri()
            );
        }
    }
}
```

`ServiceInstance#getHost()` cho biết host mà discovery client trả về cho consumer. Sau đó hãy kiểm tra DNS và kết nối đến port từ đúng container, VM hoặc pod đang chạy consumer. Kiểm tra từ provider có thể cho kết quả khác vì hai bên có network namespace và DNS resolver khác nhau.

## 9. Quan hệ với load balancing và bảo mật

`instance-id` không phải khóa lựa chọn của load balancer theo nghĩa địa chỉ mạng. Load balancer sử dụng danh sách `ServiceInstance` và host/port để gửi request. Nếu ID bị trùng, registry có thể mất một số bản ghi; nếu host/port sai, request sẽ thất bại dù ID là duy nhất.

Địa chỉ được công bố cũng ảnh hưởng đến TLS:

- Nếu consumer gọi bằng hostname, certificate cần có DNS SAN phù hợp.
- Nếu consumer gọi bằng IP, certificate cần có IP SAN tương ứng.
- Không tắt xác thực hostname chỉ để né lỗi do cấu hình địa chỉ sai.
- Không lưu token hoặc password trong instance ID hay metadata.
- Chỉ mở port ứng dụng cho các consumer cần thiết; bảo vệ Dashboard và REST API của Eureka.

Khi triển khai qua NAT hoặc port mapping, phải bảo đảm cả host và port công bố đều là endpoint mà consumer truy cập được. Việc chỉ đặt đúng `hostname` hoặc `prefer-ip-address` sẽ không giải quyết được port mapping sai.

## 10. Checklist cấu hình production

- `spring.application.name` ổn định và giống nhau giữa các replica cùng dịch vụ.
- `eureka.instance.instance-id` duy nhất trong số instance đang chạy đồng thời và truy vết được về workload.
- `hostname` là DNS name có thể phân giải từ consumer, hoặc `ip-address` là địa chỉ có route phù hợp.
- `prefer-ip-address` phản ánh đúng lựa chọn hostname/IP của kiến trúc mạng.
- Nếu có nhiều network interface, cấu hình IP/interface được ưu tiên một cách tường minh.
- Port HTTP/HTTPS được công bố khớp với endpoint consumer thực sự gọi.
- Mỗi replica nhận giá trị môi trường riêng cho các trường cần duy nhất.
- Đã kiểm tra bản ghi trong Eureka Dashboard hoặc REST API sau khi khởi động.
- Đã kiểm tra kết nối từ môi trường consumer, gồm DNS, route, firewall và TLS.
- Không công khai registry và metadata nội bộ ngoài phạm vi quản trị.

## Kết luận

`eureka.instance.instance-id` nhận diện từng bản chạy; `eureka.instance.hostname` xác định hostname được công bố; `eureka.instance.prefer-ip-address` quyết định ưu tiên IP hay hostname trong thông tin instance. Ba thuộc tính cần được cấu hình theo topology mạng và vòng đời triển khai thực tế.

Hãy bảo đảm instance ID không trùng giữa các replica, địa chỉ được công bố truy cập được từ consumer và port/TLS khớp với endpoint thật. Sau khi cấu hình, kiểm tra dữ liệu trong Eureka và thử kết nối từ phía consumer để xác nhận discovery hoạt động đúng.
