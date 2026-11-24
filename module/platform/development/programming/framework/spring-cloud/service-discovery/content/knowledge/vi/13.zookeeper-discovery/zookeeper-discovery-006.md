# Thiết lập tên dịch vụ, instanceId, địa chỉ và thư mục gốc

Spring Cloud Zookeeper Discovery đăng ký các service instance vào Apache ZooKeeper để consumer có thể tìm dịch vụ theo tên. Khi cấu hình một service, cần xác định bốn thông tin: tên dịch vụ logic, mã định danh instance, địa chỉ/port mà consumer sẽ gọi và thư mục gốc trong cây znode của ZooKeeper.

Bốn thông tin này có quan hệ với nhau nhưng không thể thay thế cho nhau. Tên dịch vụ gom các instance cùng cung cấp một chức năng; `instanceId` phân biệt từng bản chạy; địa chỉ và port xác định endpoint mạng; root path xác định namespace lưu các bản đăng ký. Nếu provider và consumer dùng root path khác nhau, hoặc provider công bố địa chỉ chỉ truy cập được từ chính máy nó, service discovery sẽ không hoạt động như mong đợi.

Trong module `SPRING_CLOUD_SERVICE_DISCOVERY`, Spring Cloud cung cấp abstraction `DiscoveryClient` và `ServiceRegistry`, còn Spring Cloud Zookeeper ánh xạ các abstraction này sang cơ chế đăng ký và khám phá dựa trên znode của ZooKeeper.

## 1. Cách Zookeeper Discovery tổ chức service registration

ZooKeeper lưu dữ liệu dưới dạng cây znode. Mỗi znode có một đường dẫn tuyệt đối, ví dụ `/services/production/payment-service/payment-01`. Spring Cloud Zookeeper Discovery dùng một root path để nhóm các service và tạo các node đại diện cho instance.

Với root path `/services`, tên dịch vụ `payment-service` và instance ID `payment-01`, có thể hình dung cấu trúc như sau:

```text
ZooKeeper ensemble
└── /services
    ├── payment-service
    │   ├── payment-01
    │   └── payment-02
    ├── order-service
    │   ├── order-01
    │   └── order-02
    └── inventory-service
        └── inventory-01
```

Đây là cấu trúc khái niệm của service discovery. Dữ liệu registration của từng instance được lưu tại znode tương ứng; implementation có thể lưu payload chứa host, port, scheme và metadata. Các instance thường được biểu diễn bằng ephemeral znode để vòng đời đăng ký gắn với ZooKeeper session của client.

Khi provider đăng ký, Spring Cloud Zookeeper tạo hoặc cập nhật znode của instance. Khi ứng dụng deregister hoặc session ZooKeeper hết hạn, ephemeral znode sẽ bị xóa. Consumer sử dụng discovery client để đọc các instance thuộc service name mà nó cần gọi.

## 2. Tên dịch vụ: `spring.application.name`

Tên dịch vụ logic thường được khai báo bằng `spring.application.name`:

```yaml
spring:
  application:
    name: payment-service
```

Spring Cloud Zookeeper sử dụng tên ứng dụng này làm service ID trong quá trình đăng ký và tra cứu, trừ khi ứng dụng cấu hình service name riêng bằng thuộc tính discovery tương ứng. Các instance của cùng một dịch vụ cần dùng cùng service name để consumer có thể tra cứu chúng như một nhóm.

Ví dụ, ba replica của `payment-service` có thể cùng đăng ký dưới service name `payment-service`, dù chạy trên ba máy hoặc container khác nhau. Khi consumer gọi `DiscoveryClient.getInstances("payment-service")`, discovery client trả về danh sách instance mà registry hiện có cho service ID đó.

### 2.1. Quy tắc đặt tên

- Dùng tên ổn định, có ý nghĩa theo chức năng, ví dụ `payment-service`, `order-service`.
- Tất cả replica của cùng một dịch vụ dùng cùng tên.
- Không đưa hostname, pod name hoặc IP vào service name; những giá trị đó thuộc về instance.
- Tránh dấu `/` trong service name vì tên này thường trở thành một thành phần của ZooKeeper path.
- Thống nhất cách viết giữa provider và consumer, bao gồm chữ hoa/chữ thường.
- Chỉ thay tên dịch vụ khi thay đổi ranh giới logic hoặc hợp đồng discovery, vì đổi tên sẽ ảnh hưởng các consumer đang tra cứu tên cũ.

Tên dịch vụ không phải địa chỉ mạng. `payment-service` là khóa tra cứu logic; hostname/IP và port của mỗi instance mới là thông tin kết nối.

## 3. Instance ID: phân biệt từng bản chạy

`spring.cloud.zookeeper.discovery.instance-id` xác định một instance cụ thể trong service. Với nhiều replica cùng service name, mỗi instance ID phải khác nhau để chúng có thể cùng tồn tại trong cây znode.

Ví dụ:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        instance-id: payment-01
```

Nếu có hai replica cùng đăng ký `payment-service` với `instance-id: payment-01`, chúng có thể cùng thao tác lên một đường dẫn znode. Một instance có thể ghi đè dữ liệu instance kia hoặc gặp lỗi tạo node đã tồn tại, tùy cách đăng ký và phiên bản implementation. Hãy bảo đảm ID duy nhất trong phạm vi một service name và root path.

### 3.1. Tạo instance ID theo môi trường

Có thể xây dựng ID từ hostname, port hoặc định danh workload:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        instance-id: "${INSTANCE_ID:${HOSTNAME:payment-local}}"
```

Với Kubernetes, có thể truyền Pod name hoặc Pod UID qua biến môi trường. Với VM, có thể dùng hostname đã được quản lý ổn định. Nếu một máy chạy nhiều tiến trình cùng service, cần thêm một thành phần phân biệt như port hoặc process identifier.

Ví dụ ID dễ truy vết:

```text
payment-service:payments-7f9c8d6b6f-k2m4p:8082
```

Định dạng ID là quy ước của ứng dụng. Giá trị cần ổn định trong vòng đời một instance, không chứa dấu `/` làm thay đổi cấu trúc path và không chứa password, token hay dữ liệu nhạy cảm.

### 3.2. Instance ID gắn với vòng đời ephemeral node

ZooKeeper ephemeral znode tồn tại trong thời gian session tạo ra nó còn hiệu lực. Khi client đóng session bình thường hoặc session hết hạn, ZooKeeper xóa ephemeral node. Nếu client chỉ tạm thời mất kết nối nhưng session vẫn còn hiệu lực, node có thể tiếp tục tồn tại trong thời gian ZooKeeper chờ client kết nối lại.

Vì vậy, không nên xem một lần mất TCP connection ngắn là bằng chứng instance đã bị xóa khỏi registry. Ngược lại, nếu session hết hạn, provider cần thiết lập session mới và đăng ký lại instance. Hãy kiểm tra trạng thái session và bản ghi znode khi điều tra lỗi đăng ký.

## 4. Địa chỉ và port được công bố

ZooKeeper lưu thông tin để consumer biết địa chỉ mạng của instance. Địa chỉ này phải có thể truy cập từ môi trường consumer, không chỉ từ tiến trình provider.

Spring Cloud Zookeeper Discovery có các thuộc tính thường dùng:

| Thuộc tính | Vai trò |
|---|---|
| `spring.cloud.zookeeper.discovery.instance-host` | Hostname hoặc địa chỉ host được công bố cho instance. |
| `spring.cloud.zookeeper.discovery.prefer-ip-address` | Ưu tiên công bố IP thay cho hostname khi tự xác định địa chỉ. |
| `spring.cloud.zookeeper.discovery.instance-port` | Port được công bố cho instance nếu cần chỉ định rõ. |
| `spring.cloud.zookeeper.discovery.instance-ssl-port` | Port SSL được công bố nếu service có endpoint bảo mật tương ứng. |

Nếu không chỉ định rõ, integration có thể suy ra host và port từ môi trường chạy. Trong máy có nhiều network interface hoặc container, giá trị tự phát hiện cần được kiểm tra kỹ.

### 4.1. Ưu tiên hostname

Nếu consumer có thể phân giải DNS nội bộ, có thể công bố hostname riêng cho instance:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        instance-host: payment-01.internal.example
        prefer-ip-address: false
        instance-port: 8082
```

Consumer cần phân giải được `payment-01.internal.example` và có đường mạng đến port `8082`. Một hostname chỉ có trong `/etc/hosts` của provider hoặc DNS zone riêng của một subnet sẽ không tự động dùng được từ các consumer khác.

### 4.2. Ưu tiên IP

Nếu consumer có thể định tuyến trực tiếp đến IP của instance, có thể bật:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        prefer-ip-address: true
        instance-port: 8082
```

Khi bật `prefer-ip-address`, client ưu tiên địa chỉ IP được phát hiện theo môi trường. Nếu máy có nhiều interface, hãy kiểm tra IP thực tế được công bố. Có thể dùng `instance-host` để chỉ định địa chỉ host tường minh nếu cần kiểm soát endpoint; sau khi thay đổi, phải xác minh record trong ZooKeeper hoặc qua discovery client.

Không công bố `127.0.0.1`, `localhost` hoặc `0.0.0.0` làm địa chỉ cho consumer ở máy khác. `0.0.0.0` là địa chỉ wildcard dùng khi bind server, còn loopback chỉ trỏ về chính máy/container đang thực hiện kết nối.

### 4.3. Port phải khớp endpoint thực tế

Nếu ứng dụng chạy trên port `8082` nhưng registry công bố `8080`, consumer sẽ gọi sai endpoint. Trong container, port nội bộ và port publish ra host có thể khác nhau; cần xác định consumer kết nối trực tiếp vào container network hay qua host/gateway.

Nếu sử dụng HTTPS, cần công bố SSL port phù hợp và bảo đảm scheme, certificate SAN, hostname/IP mà consumer dùng là tương thích. Địa chỉ có thể phân giải được nhưng TLS vẫn thất bại nếu certificate không khớp.

## 5. Thư mục gốc ZooKeeper: `spring.cloud.zookeeper.discovery.root`

Thuộc tính `spring.cloud.zookeeper.discovery.root` xác định znode gốc mà Spring Cloud Zookeeper Discovery sử dụng để lưu service registration. Giá trị mặc định thường dùng là `/services`.

Ví dụ:

```yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: /services
```

Với root `/services`, service name `payment-service` và instance ID `payment-01`, đường dẫn khái niệm là:

```text
/services/payment-service/payment-01
```

Có thể đổi root để tách namespace theo môi trường hoặc theo nhóm ứng dụng:

```yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: /services/production
```

Khi đó, các instance của `payment-service` được nhóm dưới:

```text
/services/production/payment-service/payment-01
```

### 5.1. Provider và consumer phải dùng cùng root

Nếu provider đăng ký dưới `/services/production` nhưng consumer tra cứu dưới `/services/staging`, consumer sẽ không thấy service dù cả hai kết nối đến cùng ZooKeeper ensemble.

Vì vậy, root path là một phần của hợp đồng discovery giữa provider và consumer. Cần quản lý nó bằng cấu hình môi trường nhất quán, ví dụ:

```yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: ${ZK_DISCOVERY_ROOT:/services/production}
```

Tất cả service trong cùng môi trường phải nhận cùng giá trị `ZK_DISCOVERY_ROOT`. Nếu cố ý tách môi trường, cần bảo đảm consumer chỉ tra cứu namespace của môi trường tương ứng.

### 5.2. Quy tắc đặt root path

- Dùng path tuyệt đối, bắt đầu bằng `/`, ví dụ `/services` hoặc `/services/production`.
- Không dùng dấu `/` ở cuối nếu không cần thiết.
- Không đặt service name hoặc instance ID chứa dấu `/` làm thay đổi cấu trúc cây.
- Chọn namespace ổn định; đổi root làm các consumer không còn nhìn thấy các bản đăng ký ở root cũ.
- Quy định ACL trên root và các node con để provider có quyền đăng ký, consumer có quyền đọc theo đúng nhu cầu.
- Không chia sẻ cùng root giữa môi trường production và development nếu không có chủ đích rõ ràng.

Việc root znode đã tồn tại hay được tạo tự động phụ thuộc cấu hình và phiên bản integration. Trong môi trường có ACL chặt, hãy chuẩn bị path và cấp quyền cần thiết theo quy trình quản trị ZooKeeper thay vì cấp quyền rộng cho ứng dụng.

## 6. Cấu hình hoàn chỉnh cho provider

Ví dụ một `payment-service` đăng ký vào ZooKeeper ensemble với hostname và root riêng cho production:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: true
        root: /services/production
        instance-id: "${INSTANCE_ID:${HOSTNAME:payment-01}}"
        instance-host: "${SERVICE_ADVERTISE_HOST:payment-01.internal.example}"
        prefer-ip-address: false
        instance-port: 8082

server:
  port: 8082
```

Trong ví dụ này:

- `spring.application.name` đặt service ID `payment-service`.
- `connect-string` là danh sách endpoint của ZooKeeper ensemble mà ứng dụng kết nối để đăng ký và tra cứu.
- `root` đặt namespace discovery cho môi trường production.
- `instance-id` phân biệt bản chạy cụ thể.
- `instance-host` công bố hostname mà consumer có thể truy cập.
- `instance-port` công bố port nghiệp vụ.
- `register: true` cho phép ứng dụng đăng ký chính nó.
- `enabled: true` bật tích hợp discovery.

`connect-string` và `instance-host` phục vụ hai luồng kết nối khác nhau. `connect-string` trỏ đến ZooKeeper để client thao tác znode; `instance-host` là địa chỉ consumer sẽ gọi sau khi tra cứu service.

## 7. Cấu hình provider dùng IP

Nếu các consumer nằm trong cùng mạng có thể định tuyến đến IP của instance, có thể dùng cấu hình:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: true
        root: /services/production
        instance-id: "${INSTANCE_ID:${HOSTNAME:payment-01}}"
        prefer-ip-address: true
        instance-port: 8082

server:
  port: 8082
```

Trong cấu hình này, IP được phát hiện từ môi trường sẽ được ưu tiên. Nếu host có nhiều interface, cần xác minh IP thực tế và chọn cơ chế chỉ định địa chỉ tường minh phù hợp với phiên bản đang dùng. Không ghi cứng một IP dùng chung cho mọi replica.

## 8. Consumer tra cứu service

Consumer cần kết nối đến cùng ZooKeeper ensemble và dùng cùng root path với provider. Ví dụ:

```yaml
spring:
  application:
    name: order-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: false
        root: /services/production
```

`register: false` phù hợp khi ứng dụng chỉ cần tra cứu service và không muốn đăng ký chính nó. Nếu `order-service` cũng cần được các service khác tìm thấy, bật đăng ký và cấu hình instance ID/địa chỉ tương ứng.

Có thể sử dụng `DiscoveryClient` để lấy instance:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentServiceLookup {

    private final DiscoveryClient discoveryClient;

    public PaymentServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findPaymentInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
```

Kết quả là danh sách instance có host, port, URI và metadata. Consumer có thể dùng Spring Cloud LoadBalancer để chọn một instance thay vì tự chọn thủ công. Nếu danh sách rỗng, cần xử lý trường hợp service chưa đăng ký, root path sai, instance chưa sẵn sàng hoặc session/registry đang phục hồi.

## 9. Kiểm tra cây znode và bản ghi đăng ký

Sau khi provider khởi động, có thể dùng ZooKeeper CLI trong môi trường quản trị để kiểm tra cây path:

```text
ls /services/production
ls /services/production/payment-service
get /services/production/payment-service/payment-01
```

Lệnh `ls` đầu tiên cho biết các service name đã được đăng ký dưới root. Lệnh thứ hai liệt kê các instance ID của `payment-service`. Lệnh `get` đọc dữ liệu của znode instance; nội dung phụ thuộc định dạng serialization của phiên bản Spring Cloud Zookeeper.

Có thể kiểm tra bằng API discovery ở phía consumer:

```java
for (ServiceInstance instance :
        discoveryClient.getInstances("payment-service")) {
    System.out.println(instance.getInstanceId());
    System.out.println(instance.getHost());
    System.out.println(instance.getPort());
    System.out.println(instance.getUri());
}
```

Kiểm tra từ consumer có giá trị thực tế vì nó cho thấy địa chỉ mà ứng dụng gọi dịch vụ nhận được sau khi discovery xử lý dữ liệu ZooKeeper.

## 10. Session, ephemeral node và quá trình deregistration

Đăng ký service trong ZooKeeper thường dựa trên ephemeral znode. Khác với persistent znode, ephemeral znode gắn với session tạo ra nó và được ZooKeeper xóa khi session hết hạn hoặc client đóng session.

Điều này tạo ra các hành vi quan trọng:

- Khi provider shutdown có kiểm soát, client có thể đóng session và node đăng ký được xóa.
- Khi provider bị kill đột ngột, ephemeral node chưa chắc biến mất ngay; ZooKeeper cần xác định session đã hết hạn.
- Khi mạng tạm thời gián đoạn nhưng session còn hiệu lực, znode có thể vẫn tồn tại.
- Khi session hết hạn, provider phải tạo session mới và đăng ký lại instance.
- Consumer có thể cần thời gian để nhận thay đổi qua watcher hoặc làm mới dữ liệu discovery.

Do đó, một khoảng trễ tồn tại giữa thời điểm tiến trình chết và thời điểm instance biến mất khỏi mọi consumer. Consumer vẫn cần timeout, retry có giới hạn và xử lý kết nối thất bại.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Consumer không tìm thấy service | Provider và consumer dùng root path khác nhau. | Đối chiếu `spring.cloud.zookeeper.discovery.root` trên hai phía. |
| Không có znode của service | `register` hoặc `enabled` bị tắt, ứng dụng không kết nối được ZooKeeper. | Kiểm tra cấu hình, log startup và quyền ghi trên root. |
| Chỉ thấy một instance dù có nhiều replica | Các replica dùng cùng `instance-id`. | Tạo ID duy nhất theo pod, container, hostname hoặc port. |
| Znode tồn tại nhưng consumer không gọi được | Hostname/IP hoặc port công bố không truy cập được từ consumer. | Kiểm tra DNS, route, firewall và endpoint từ đúng môi trường consumer. |
| Consumer tra cứu nhầm môi trường | Root path dùng chung hoặc cấu hình namespace sai. | Tách root theo môi trường và cấp cấu hình nhất quán. |
| Instance còn xuất hiện sau khi process bị kill | ZooKeeper session chưa hết hạn. | Kiểm tra session state và thời gian timeout; không chỉ dựa vào TCP disconnect. |
| Instance biến mất khi mạng chập chờn | Session hết hạn do mất kết nối kéo dài hoặc timeout quá ngắn. | Kiểm tra session timeout, mạng giữa client và ensemble, sau đó theo dõi đăng ký lại. |
| Lỗi `NodeExists` khi đăng ký | Znode instance ID đã tồn tại hoặc có xung đột vòng đời đăng ký. | Kiểm tra instance ID, session cũ và quy trình deregistration. |
| Lỗi `NoAuth` hoặc `NoNode` | ACL thiếu quyền hoặc root/parent path chưa được chuẩn bị. | Kiểm tra ACL và thứ tự tạo path theo chính sách quản trị. |

## 12. Bảo mật và vận hành root path

ZooKeeper là hạ tầng điều phối dùng chung, vì vậy không nên cấp quyền rộng cho mọi ứng dụng.

- Cấp quyền đọc discovery path cho consumer cần tra cứu.
- Cấp quyền tạo, cập nhật và xóa instance node cho provider trong namespace của nó.
- Dùng ACL và cơ chế xác thực của ZooKeeper theo chính sách nền tảng.
- Bảo vệ kết nối client đến ensemble bằng cấu hình bảo mật phù hợp, bao gồm TLS/SASL nếu môi trường yêu cầu.
- Không đưa thông tin bí mật vào service name, instance ID hoặc metadata.
- Tách root path theo môi trường hoặc tenant nếu cần cô lập registry.
- Theo dõi session expiration, số lượng ephemeral node, lỗi ACL và thời gian phản hồi của ensemble.
- Tránh thao tác xóa thủ công cả root path trong khi service đang hoạt động vì có thể làm mất đăng ký của nhiều instance.

Việc cấu hình ACL, TLS và SASL có thể khác nhau theo phiên bản ZooKeeper, Curator và Spring Cloud Zookeeper. Cần đối chiếu phiên bản thư viện đang dùng và chính sách của cluster trước khi triển khai.

## 13. Checklist cấu hình production

- `spring.application.name` ổn định và thống nhất giữa các replica của cùng service.
- `instance-id` duy nhất trong phạm vi service name và root path.
- Hostname/IP được công bố có thể truy cập từ mọi consumer cần gọi instance.
- Port và SSL port khớp với endpoint thật.
- `root` là path tuyệt đối, ổn định và giống nhau giữa provider/consumer cùng môi trường.
- `connect-string` trỏ đến đúng ZooKeeper ensemble; không nhầm với địa chỉ service instance.
- Provider có quyền tạo/đăng ký ephemeral node; consumer có quyền đọc path cần thiết.
- Session timeout phù hợp với độ ổn định mạng và yêu cầu phát hiện instance lỗi.
- Có xử lý danh sách instance rỗng, session expiration và kết nối tạm thời thất bại.
- Đã kiểm tra znode và `ServiceInstance` từ góc nhìn consumer sau khi triển khai.
- Không xóa root path hoặc thay namespace trong giờ hoạt động nếu chưa có kế hoạch chuyển đổi registration.

## Kết luận

Trong Spring Cloud Zookeeper Discovery, `spring.application.name` xác định tên dịch vụ logic, `spring.cloud.zookeeper.discovery.instance-id` phân biệt từng bản chạy, `instance-host`/`prefer-ip-address` cùng port xác định địa chỉ consumer sẽ gọi, còn `root` xác định namespace znode chứa registration. `connect-string` chỉ định ZooKeeper ensemble mà ứng dụng kết nối để thao tác registry.

Đăng ký thường được biểu diễn bằng ephemeral znode gắn với ZooKeeper session. Vì vậy, cần tạo instance ID duy nhất, công bố địa chỉ có thể truy cập, dùng cùng root path trên provider và consumer, đồng thời xử lý session expiration và quá trình đăng ký lại. Kiểm tra cả cây znode lẫn kết quả `DiscoveryClient` từ consumer giúp xác nhận cấu hình discovery hoạt động đúng.
