# Mở rộng đăng ký với ServiceRegistry khi thật sự cần

Spring Cloud thường tự đăng ký một application instance với service registry khi ứng dụng khởi động. Trong phần lớn hệ thống, một registration cho mỗi instance là đủ: nó chứa serviceId, instanceId, địa chỉ, port và metadata để consumer tìm và gọi dịch vụ.

Có trường hợp một process thực sự cung cấp nhiều endpoint logic khác nhau, chẳng hạn HTTP và gRPC trên hai port, hoặc cần công bố một endpoint riêng cho một nhóm consumer. Khi đó có thể cần thêm registration thông qua ServiceRegistry. Tuy nhiên, thêm record không làm endpoint tự xuất hiện, không mở port và không tạo route mạng. Mỗi registration phải đại diện cho một endpoint có ý nghĩa, có vòng đời và địa chỉ truy cập rõ ràng.

Bài này giải thích vai trò của ServiceRegistry, cách quyết định khi nào nên mở rộng registration, cách quản lý nhiều record mà không trùng lặp với auto-registration, và cách kiểm tra hành vi trên Eureka, Consul hoặc ZooKeeper.

## 1. ServiceRegistry nằm ở đâu trong service discovery?

Spring Cloud Commons cung cấp các abstraction để provider đăng ký dịch vụ và consumer tìm instance:

| Thành phần | Vai trò | Hành động chính |
|---|---|---|
| Registration | Marker interface cho object đăng ký cụ thể của từng registry | serviceId, host, port, secure, metadata |
| ServiceRegistry | Abstraction để quản lý registration | register, deregister, getStatus, setStatus |
| DiscoveryClient | Abstraction để consumer truy vấn registry | getServices, getInstances |
| AutoServiceRegistration | Điều phối đăng ký tự động trong lifecycle ứng dụng | Đăng ký instance mặc định khi ứng dụng khởi động |
| ServiceInstance | Dữ liệu instance mà consumer nhận được | URI, host, port, metadata |

ServiceRegistry là SPI của Spring Cloud Commons. Nó không phải một registry server độc lập và cũng không phải API để consumer tìm instance. Implementation của registry cụ thể sẽ thực hiện thao tác ghi vào Eureka, Consul, ZooKeeper hoặc hệ thống tương ứng.

API có dạng generic vì mỗi registry có kiểu Registration riêng:

~~~java
public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    <T> T getStatus(R registration);

    void setStatus(R registration, String status);

    void close();
}
~~~

Đây là hình dạng khái quát của SPI; hãy kiểm tra source tương ứng với release train đang dùng khi viết code tích hợp. Không nên ép kiểu registration của Eureka sang registration của Consul hoặc dùng raw type để né kiểm tra kiểu.

SPI chỉ chuẩn hóa các thao tác cơ bản; nó không cam kết mọi implementation cho phép một bean/client duy nhất quản lý tùy ý nhiều serviceId độc lập. Một số integration gắn ServiceRegistry với một application instance hoặc một registration mặc định. Trước khi thiết kế nhiều record trong cùng process, hãy kiểm tra implementation cụ thể của starter và phiên bản đang dùng. Nếu adapter chỉ hỗ trợ một application instance, có thể cần một client/context riêng, một service/process riêng hoặc gateway; không thể suy ra khả năng multi-registration chỉ từ generic API.

getStatus() và setStatus() cũng không có một tập giá trị portable cho mọi registry. getStatus() dùng kiểu generic và ý nghĩa status phụ thuộc implementation. Không gửi chuỗi UP/DOWN tùy ý nếu adapter yêu cầu enum hoặc trạng thái riêng.

Spring Cloud Commons cũng có actuator endpoint /serviceregistry để đọc hoặc thay đổi status của Registration bean hiện tại. Endpoint này không phải công cụ tạo nhiều registration. Giá trị status hợp lệ phụ thuộc registry; ví dụ Eureka hỗ trợ UP, DOWN, OUT_OF_SERVICE và UNKNOWN. Chỉ expose endpoint này trên management interface được bảo vệ.

Consumer thường không gọi ServiceRegistry.register(). Consumer dùng DiscoveryClient.getInstances(serviceId) hoặc Spring Cloud LoadBalancer để lấy instance. Provider hoặc lifecycle component mới là phía chịu trách nhiệm đăng ký và hủy đăng ký.

## 2. Mặc định một instance thường chỉ cần một registration

Giả sử inventory-service chạy một replica trên host 10.20.1.11, lắng nghe HTTP cổng 8080. Registration có thể chứa:

~~~yaml
serviceId: inventory-service
instanceId: inventory-node-a
host: 10.20.1.11
port: 8080
secure: false
metadata:
  app.version: "2.4.0"
  routing.zone: "zone-a"
~~~

Consumer tra cứu inventory-service và nhận một ServiceInstance. Khi service có ba replica, mỗi replica đăng ký một instance riêng với cùng serviceId nhưng instanceId khác nhau.

~~~mermaid
flowchart TD
    R["Registry: inventory-service"]
    R --> A["inventory-node-a<br/>10.20.1.11:8080"]
    R --> B["inventory-node-b<br/>10.20.1.12:8080"]
    R --> C["inventory-node-c<br/>10.20.1.13:8080"]
    D["Consumer / LoadBalancer"] --> R
    D --> A
    D --> B
    D --> C
~~~

Đây là mô hình scale ngang thông thường. Không cần gọi ServiceRegistry thủ công cho từng consumer hoặc từng request. Cơ chế auto-registration của starter đã đăng ký instance của ứng dụng.

Nếu chỉ cần thêm version, zone, weight hoặc một vài thuộc tính định tuyến, hãy bổ sung metadata vào registration hiện có. Không tạo thêm registration chỉ để lưu một giá trị metadata.

## 3. Khi nào thật sự cần nhiều registration?

Chỉ mở rộng khi có nhiều endpoint logic cần được discovery độc lập.

| Nhu cầu | Cách biểu diễn phù hợp | Vì sao |
|---|---|---|
| Nhiều replica của cùng API | Cùng serviceId, mỗi replica một instanceId | LoadBalancer chọn giữa các replica tương đương |
| Một process cung cấp HTTP và gRPC trên port khác nhau | Hai serviceId logic, ví dụ inventory-http và inventory-grpc | Consumer cần chọn đúng protocol và port |
| API nghiệp vụ và management endpoint | Chỉ đăng ký API nghiệp vụ; management dùng kênh quản trị riêng | Tránh consumer vô tình gọi actuator |
| Cùng endpoint nhưng có version/zone/canary | Một registration với metadata | Metadata mô tả thuộc tính của cùng endpoint |
| Endpoint nội bộ và endpoint public có trust boundary khác nhau | ServiceId/registry scope hoặc gateway riêng | Consumer không được nhận nhầm địa chỉ theo network |
| Một process có hai endpoint độc lập, có chính sách traffic khác nhau | Registration riêng cho từng endpoint | Có thể rollout, health check và phân quyền riêng |
| Nhiều network nhưng cùng một endpoint logic | Ưu tiên DNS/gateway hoặc discovery scope theo network | Một địa chỉ quảng bá có thể không truy cập được từ mọi caller |

Ví dụ, inventory-service cung cấp HTTP API ở cổng 8080 và gRPC ở cổng 9090. Nếu hai protocol có consumer và health check riêng, có thể đăng ký:

- inventory-http → host:8080
- inventory-grpc → host:9090

Không đăng ký cả hai port dưới cùng serviceId nếu consumer không có cơ chế phân biệt protocol. Nếu LoadBalancer nhận cả instance HTTP lẫn gRPC trong cùng một danh sách, nó có thể chọn sai port và tạo lỗi khó chẩn đoán.

Một process có thể có nhiều registration, nhưng mỗi registration phải có instanceId riêng trong phạm vi quy tắc của registry và phải mô tả đúng endpoint.

## 4. Khi nào không nên mở rộng registration?

Các trường hợp sau thường không cần thêm record:

- Chỉ muốn thêm metadata như version, zone, canary hoặc weight.
- Muốn đăng ký mỗi replica một lần nữa để tăng độ tin cậy.
- Muốn đăng ký một record cho từng consumer.
- Muốn công bố từng URL path hoặc controller method.
- Muốn đưa cổng Actuator vào danh sách service nghiệp vụ.
- Muốn thêm record cho mỗi lần retry hoặc reconnect.
- Muốn sửa lỗi network bằng cách tạo thêm registration với cùng địa chỉ không truy cập được.

Registration chỉ lưu thông tin định tuyến và metadata. Nó không tự mở firewall, tạo Docker port mapping, cấp DNS, thiết lập TLS hoặc làm cho Pod IP có thể truy cập từ bên ngoài cluster.

Nếu endpoint hiện tại đã đúng, hãy cập nhật metadata hoặc cấu hình địa chỉ. Nếu hai endpoint có protocol hoặc vòng đời khác nhau, hãy xem xét serviceId riêng.

## 5. Phân biệt serviceId và instanceId

Hai trường này giải quyết hai bài toán khác nhau:

- **serviceId** là tên logic mà consumer tra cứu.
- **instanceId** phân biệt một registration cụ thể trong service.

Ví dụ:

| serviceId | instanceId | Endpoint |
|---|---|---|
| inventory-http | inventory-http-node-a | 10.20.1.11:8080 |
| inventory-http | inventory-http-node-b | 10.20.1.12:8080 |
| inventory-grpc | inventory-grpc-node-a | 10.20.1.11:9090 |

Nếu hai registration cùng process dùng chung instanceId trong khi registry yêu cầu ID duy nhất, thao tác đăng ký sau có thể ghi đè hoặc xung đột với record trước. Cần chọn ID ổn định, duy nhất theo serviceId và endpoint.

Không tạo instanceId ngẫu nhiên mới mỗi lần retry. Nếu một lần register timeout nhưng server đã ghi record, retry với ID mới có thể tạo registration trùng. Dùng ID xác định từ serviceId, hostname/pod identity và port hoặc một định danh ổn định khác.

## 6. ServiceRegistry và auto-registration

Các starter Spring Cloud thường tích hợp AutoServiceRegistration để đăng ký application instance mặc định trong lifecycle khởi động. Cơ chế này giúp ứng dụng không cần tự gọi register() trong mỗi dự án.

Khi muốn thêm một registration, hãy xác định rõ:

1. Auto-registration hiện đang đăng ký endpoint nào?
2. Registration bổ sung đại diện endpoint nào?
3. Ai sở hữu vòng đời của record bổ sung?
4. Khi shutdown, thành phần nào gọi deregister?
5. Khi reconnect hoặc session mất, record được tạo lại như thế nào?
6. Có nguy cơ hai cơ chế cùng đăng ký một endpoint hay không?

Nếu chỉ cần thêm endpoint thứ hai, thông thường giữ auto-registration cho endpoint chính và quản lý riêng registration bổ sung. Không tắt auto-registration toàn ứng dụng nếu vẫn cần registration mặc định.

Property chung thường dùng để điều khiển auto-registration là:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true
~~~

Nếu cần tắt auto-registration để tự quản lý registration mặc định, cấu hình có thể là:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Chỉ dùng cấu hình này khi lifecycle thủ công đã thay thế đầy đủ registration mặc định và đã kiểm thử deregistration, reconnect, health và readiness. Nếu chỉ thêm một endpoint phụ, thường giữ auto-registration của endpoint chính.

Nếu ứng dụng tự quản lý toàn bộ registration, có thể cần tắt auto-registration theo property được hỗ trợ trong phiên bản Spring Cloud đang dùng. Hãy xác minh cấu hình của release train và starter cụ thể; không giả định mọi phiên bản hoặc mọi registry có lifecycle giống nhau.

Một lựa chọn khác được Spring Cloud Commons hỗ trợ là @EnableDiscoveryClient(autoRegister=false). Không cần dùng đồng thời cả annotation và property nếu một cách đã thể hiện rõ cấu hình của ứng dụng.

Không bật auto-registration và đồng thời gọi register() thủ công cho cùng một serviceId/instanceId nếu chưa có thiết kế idempotent. Điều đó có thể tạo race, cập nhật metadata không nhất quán hoặc deregister nhầm record khi shutdown.

## 7. Mở rộng bằng ServiceRegistry theo kiểu an toàn

ServiceRegistry có generic type R extends Registration. Khi inject registry, dùng đúng kiểu registration mà implementation cung cấp. Không ép kiểu một Registration tùy ý thành registration cụ thể của Eureka hoặc Consul.

Một wrapper dùng chung có thể giữ thao tác register/deregister, còn factory tạo registration cụ thể do adapter của registry đảm nhiệm:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public final class AdditionalRegistrationPublisher<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;

    public AdditionalRegistrationPublisher(ServiceRegistry<R> serviceRegistry) {
        this.serviceRegistry = serviceRegistry;
    }

    public void register(R registration) {
        serviceRegistry.register(registration);
    }

    public void deregister(R registration) {
        serviceRegistry.deregister(registration);
    }
}
~~~

Đây là lớp điều phối generic; R phải là kiểu Registration phù hợp với ServiceRegistry đang được inject. Nó không tự tạo ra EurekaRegistration hoặc ConsulRegistration. Hãy dùng factory, builder hoặc integration API được starter hỗ trợ để tạo object registration.

Không khởi tạo registration bằng cách tự đoán implementation class nội bộ của starter. Các implementation có thể cần client, configuration, health check, metadata hoặc instance info do auto-configuration chuẩn bị.

Không gọi serviceRegistry.close() từ handle của một registration bổ sung. close() thuộc vòng đời của registry/client và có thể ảnh hưởng đến registration mặc định hoặc các handle khác đang dùng chung bean. Để component sở hữu ServiceRegistry hoặc Spring lifecycle của starter đóng client đúng thời điểm.

Một số implementation AutoServiceRegistration gọi ServiceRegistry.close() khi dừng. Nếu handle bổ sung dùng chung registry bean, phase/order phải bảo đảm handle deregister xong trước khi auto-registration đóng registry client. Xác minh thứ tự này trên implementation và phiên bản thực tế.

## 8. Quản lý vòng đời của registration bổ sung

Registration chỉ nên xuất hiện khi endpoint đã sẵn sàng nhận kết nối. Khi shutdown, nên gỡ registration trước khi endpoint ngừng phục vụ để consumer có thời gian cập nhật danh sách.

Vòng đời tổng quát:

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> EndpointReady: Server đã bind và port đã xác định
    EndpointReady --> Registered: ServiceRegistry.register()
    Registered --> Serving: Readiness UP
    Serving --> Draining: Shutdown bắt đầu
    Draining --> Deregistered: ServiceRegistry.deregister()
    Deregistered --> Stopped: Server đóng
    Registered --> Retry: Register lỗi tạm thời
    Retry --> Registered: Backoff và retry thành công
    Stopped --> [*]
~~~

Một lifecycle manager có thể dùng SmartLifecycle để gắn thao tác register/deregister với vòng đời ApplicationContext:

~~~java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;
import org.springframework.context.SmartLifecycle;

import java.util.function.Supplier;

public final class AdditionalRegistrationLifecycle<R extends Registration>
        implements SmartLifecycle {

    private final ServiceRegistry<R> serviceRegistry;
    private final Supplier<R> registrationFactory;

    private R registration;
    private volatile boolean running;

    public AdditionalRegistrationLifecycle(
            ServiceRegistry<R> serviceRegistry,
            Supplier<R> registrationFactory) {
        this.serviceRegistry = serviceRegistry;
        this.registrationFactory = registrationFactory;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }

        R candidate = registrationFactory.get();
        serviceRegistry.register(candidate);

        this.registration = candidate;
        this.running = true;
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }

        serviceRegistry.deregister(registration);
        running = false;
        registration = null;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

Đây là khung minh họa. Trong ứng dụng thật, cần bảo đảm registrationFactory chỉ tạo record sau khi endpoint đã có host/port chính xác. Nếu port được cấp động, đừng tạo Registration quá sớm khi port vẫn chưa biết.

Cần cấu hình phase và thứ tự lifecycle phù hợp để deregister xảy ra trước khi endpoint đóng. Nếu deregister thất bại, ghi nhận lỗi và có chính sách retry/cleanup; không đánh dấu thành công giả tạo. Khi start thất bại, không đặt running=true.

Với nhiều registration, quản lý từng handle độc lập. Nếu một endpoint bổ sung không khởi động được, quyết định rõ ứng dụng có thể tiếp tục phục vụ endpoint chính hay toàn bộ ứng dụng phải readiness DOWN.

## 9. Không để registration bổ sung bị trùng hoặc ghi đè

Khi thêm registration, hãy xác định khóa nhận diện của registry. Thường cần quan tâm serviceId, instanceId, node ID hoặc service ID cụ thể của provider.

Ví dụ bảng quản lý nội bộ:

| Logical endpoint | serviceId | instanceId | Host | Port |
|---|---|---|---|---:|
| HTTP API | inventory-http | inventory-http-node-a | 10.20.1.11 | 8080 |
| gRPC API | inventory-grpc | inventory-grpc-node-a | 10.20.1.11 | 9090 |

Các bất biến cần giữ:

- Một endpoint không có hai registration do auto và manual cùng tạo.
- Retry dùng lại cùng instanceId cho cùng endpoint.
- Hai endpoint khác nhau không dùng chung instanceId nếu registry yêu cầu duy nhất.
- Deregister đúng registration đã tạo, không chỉ dựa trên serviceId chung.
- Không deregister record của replica khác.
- Sau restart, record cũ phải được dọn theo cơ chế lease/session hoặc deregistration.

Đặc biệt khi có nhiều registration trong cùng process, không lưu một biến registration duy nhất rồi ghi đè nó mỗi lần tạo endpoint mới. Dùng map theo logical endpoint hoặc danh sách handle có định danh rõ ràng.

## 10. Metadata có thể giải quyết nhu cầu mà không cần thêm registration

Nếu các endpoint dùng chung protocol, host và port, nhưng khác version hoặc zone, metadata thường là lựa chọn phù hợp.

Ví dụ Eureka:

~~~yaml
eureka:
  instance:
    metadata-map:
      app.version: "2.4.0"
      routing.zone: "zone-a"
      routing.canary: "false"
~~~

Ví dụ Consul:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        metadata:
          app.version: "2.4.0"
          routing.zone: "zone-a"
          routing.canary: "false"
~~~

Tên property và cách ánh xạ phụ thuộc phiên bản starter. Consul có tags và metadata là hai khái niệm khác nhau; đừng giả định tag tự động trở thành metadata map của ServiceInstance.

Metadata không tự làm LoadBalancer lọc instance. Nếu consumer muốn chọn zone hoặc version, phải có ServiceInstanceListSupplier hoặc policy tương ứng và test riêng. Nếu không có consumer nào đọc metadata, thêm metadata chỉ tăng dữ liệu mà không thay đổi routing.

## 11. Những khác biệt khi dùng Eureka

Eureka ServiceRegistry thao tác với registration theo mô hình Eureka instance. Auto-registration của starter thường tạo registration cho application instance dựa trên cấu hình Eureka client.

Cần thận trọng: ServiceRegistry của Eureka thường gắn với EurekaRegistration/ApplicationInfoManager của application hiện tại. Không giả định chỉ cần tạo nhiều object registration tùy ý là một Eureka client sẽ công bố nhiều application/serviceId độc lập. Hãy kiểm tra cách implementation trong đúng phiên bản tạo ApplicationInfoManager và instance info; nếu nó chỉ mô tả một application instance, dùng một ứng dụng/client riêng hoặc kiến trúc endpoint/gateway phù hợp.

Khi cần endpoint bổ sung:

- Xác định endpoint có nên là application/serviceId riêng hay không.
- Dùng instance ID riêng và ổn định.
- Xác minh host/port được công bố có thể truy cập từ consumer.
- Không đưa management port vào cùng serviceId API nếu consumer có thể chọn nhầm.
- Kiểm tra auto-registration và custom registration không cùng ghi một record.
- Khi deregister, xác minh đúng instance được gỡ khỏi Eureka registry.

Nếu chỉ cần metadata, ưu tiên cấu hình metadata map của Eureka instance hiện tại. Nếu cần HTTP và gRPC với port khác nhau, cân nhắc hai logical serviceId và client adapter tương ứng.

Eureka heartbeat/lease áp dụng cho instance registration của nó. Không giả định thêm một registration tùy chỉnh sẽ tự có heartbeat/lifecycle giống registration mặc định nếu adapter không quản lý điều đó. Kiểm tra cách starter cập nhật lease và trạng thái cho registration bổ sung.

## 12. Những khác biệt khi dùng Consul

Consul registration thường có service name, service ID, address, port, tags, metadata và health checks. Service ID thường phân biệt một registration cụ thể trên agent/node.

Consul agent API có thể quản lý nhiều service registration với service ID khác nhau trên cùng node. Tuy vậy, adapter Spring Cloud và lifecycle auto-registration cụ thể vẫn quyết định cách tạo/deregister record; hãy xác minh service ID, agent sở hữu record và quyền cleanup.

Khi thêm registration:

- Tạo service ID riêng cho từng logical endpoint.
- Chọn address/port mà consumer có thể truy cập.
- Tạo health check phù hợp với chính endpoint đó.
- Không dùng cùng check URL cho HTTP và gRPC nếu protocol khác nhau.
- Xác định agent nào sở hữu registration và ai deregister.
- Kiểm tra service passing/critical qua Health API và record trong Catalog.

Ví dụ hai endpoint:

~~~json
{
  "service": {
    "name": "inventory-http",
    "id": "inventory-http-node-a",
    "address": "10.20.1.11",
    "port": 8080,
    "checks": [
      {
        "http": "http://10.20.1.11:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

~~~json
{
  "service": {
    "name": "inventory-grpc",
    "id": "inventory-grpc-node-a",
    "address": "10.20.1.11",
    "port": 9090,
    "checks": [
      {
        "grpc": "10.20.1.11:9090",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

Đây là ví dụ Consul agent registration minh họa; cú pháp gRPC check, TLS và các trường tùy chọn cần đối chiếu phiên bản Consul đang chạy. Check passing chỉ chứng minh agent gọi được endpoint check. Consumer vẫn phải truy cập được service address và port.

## 13. Những khác biệt khi dùng ZooKeeper

Spring Cloud Zookeeper hoặc Curator Service Discovery thường lưu thông tin instance trong znode. Registration có thể gắn với ephemeral node và ZooKeeper session.

Khả năng đăng ký nhiều endpoint phụ thuộc cách thư viện tạo service path và payload. SPI chung không tự tạo path riêng; cần dùng service name/path và instance identity khác nhau, đồng thời kiểm tra client/session có thể quản lý đồng thời các node đó hay không.

Nếu một process cung cấp hai logical endpoint, payload hoặc path registration phải phân biệt được service name và instance identity. Không ghi hai endpoint vào cùng một znode path rồi ghi đè payload của nhau.

Khi tạo registration bổ sung:

- Dùng path/service name riêng cho logical endpoint.
- Mỗi endpoint có instance identity rõ ràng.
- Xác định session nào sở hữu ephemeral node.
- Khi session LOST, tạo lại registration cho từng endpoint.
- Khi shutdown, xóa đúng node hoặc đóng session theo lifecycle của client.
- Consumer cần watch/resync đúng path.

Không tự tạo persistent znode để thay cho registration ephemeral nếu chưa có cơ chế cleanup. Persistent node có thể tồn tại sau khi process chết và làm consumer nhận endpoint cũ.

Nếu sử dụng auto-registration của Spring Cloud Zookeeper, kiểm tra cách thư viện tạo service instance và lifecycle. Tránh vừa bật auto-registration vừa tự tạo một znode có cùng path cho endpoint mặc định.

## 14. Quản lý health và readiness riêng cho từng endpoint

Nếu process cung cấp nhiều endpoint, một health check duy nhất có thể không phản ánh chính xác từng endpoint.

Ví dụ:
- HTTP API hoạt động nhưng gRPC server chưa bind.
- gRPC hoạt động nhưng HTTP server lỗi.
- Management endpoint hoạt động nhưng API nghiệp vụ không nhận request.
- Registry connection mất nhưng endpoint hiện tại vẫn có thể phục vụ từ cache.

Cần chọn phạm vi health check theo logical endpoint. Với hai registration độc lập, mỗi registration có thể có check riêng. Nếu endpoint nào bắt buộc để ứng dụng phục vụ, readiness tổng thể cần phản ánh điều kiện đó.

Không đăng ký một endpoint khi server chưa bind hoặc health check chưa thể thực hiện. Không để health check chỉ kiểm tra một port rồi đánh dấu cả hai registration passing.

Khi shutdown:
1. Hạ readiness cho endpoint sắp dừng.
2. Ngừng nhận request mới hoặc bắt đầu drain.
3. Deregister endpoint tương ứng.
4. Chờ consumer cập nhật discovery trong giới hạn cho phép.
5. Đóng server và resource.
6. Xác minh record cũ đã được loại bỏ hoặc chuyển trạng thái theo cơ chế registry.

## 15. Kiểm thử registration bổ sung

Cần kiểm thử cả dữ liệu đăng ký và vòng đời.

| Test | Kỳ vọng |
|---|---|
| Register lần đầu | Registry có đúng serviceId/instanceId/host/port |
| Register lặp cùng ID | Không tạo record trùng; hành vi idempotent theo adapter |
| Hai endpoint trong cùng process | Hai registration không ghi đè nhau |
| Metadata mapping | Consumer nhận đúng khóa và giá trị |
| Host/port sai | Contract test phát hiện endpoint không hợp lệ |
| Health check lỗi | Endpoint tương ứng chuyển critical/không ready |
| Deregister một endpoint | Endpoint còn lại vẫn đăng ký |
| Shutdown toàn process | Mọi registration do process sở hữu được gỡ |
| Reconnect/session LOST | Registration được phục hồi với identity phù hợp |
| Consumer lookup | serviceId riêng chỉ trả đúng protocol/endpoint |

Unit test có thể mock ServiceRegistry để xác minh số lần gọi register/deregister và thứ tự lifecycle. Integration test cần registry thật hoặc container test để xác minh record và metadata sau khi DiscoveryClient đọc lại.

Không chỉ kiểm tra rằng mock registry nhận một lần register. Cần kiểm tra endpoint được công bố có thể truy cập từ network consumer và deregistration không xóa nhầm registration khác.

Ví dụ test đơn giản cho lifecycle manager có thể xác minh:
- start hai lần chỉ register một lần;
- stop hai lần chỉ deregister một lần;
- register thất bại không đặt running thành true;
- deregister endpoint A không ảnh hưởng endpoint B.

## 16. Quan sát registration và phát hiện record thừa

Khi mở rộng registration, số lượng record tăng là điều có chủ đích. Nhưng record thừa do retry hoặc shutdown lỗi cần được phát hiện.

Các chỉ số nên theo dõi:

| Metric/log | Ý nghĩa |
|---|---|
| registration_count theo serviceId | Số instance đang được công bố |
| registration_attempt_total | Số lần thử đăng ký |
| registration_failure_total | Số lần đăng ký thất bại |
| deregistration_total | Số lần hủy đăng ký |
| duplicate_instance_id | Xung đột định danh |
| registration_age | Thời gian record tồn tại |
| health_status theo endpoint | Trạng thái từng logical endpoint |
| discovery_lookup_result | Consumer có nhận đúng endpoint không |

Không dùng instanceId hoặc hostname không giới hạn làm metric label nếu gây high cardinality. Dùng log có cấu trúc và metric tổng hợp theo serviceId/endpoint type.

Khi phát hiện record thừa:
1. Xác định process hoặc agent sở hữu record.
2. Đối chiếu instanceId, host, port và thời gian cập nhật.
3. Xác nhận record không còn endpoint sống.
4. Dùng deregistration API hoặc cleanup chính thức của registry.
5. Kiểm tra consumer đã bỏ record cũ khỏi cache chưa.

Không xóa hàng loạt record chỉ dựa trên tên service. Có thể đang có replica khỏe cùng serviceId.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Một endpoint xuất hiện hai lần | Auto-registration và manual registration cùng hoạt động | Chỉ một lifecycle sở hữu mỗi record |
| HTTP consumer chọn nhầm port gRPC | Hai protocol dùng chung serviceId và LoadBalancer list | Tách serviceId logic hoặc filter rõ ràng |
| Registration mới ghi đè registration cũ | Dùng trùng instanceId/service ID | Định danh riêng theo endpoint |
| Dashboard có record nhưng port không mở | Register trước khi server bind hoặc port mapping sai | Chỉ register sau khi endpoint sẵn sàng |
| Record còn sau shutdown | Không deregister hoặc session chưa hết hạn | Lifecycle cleanup và lease/session phù hợp |
| Thêm metadata nhưng routing không đổi | LoadBalancer không đọc metadata | Cấu hình supplier/policy và test |
| Consumer nhận địa chỉ nội bộ không truy cập được | Advertised address sai network | Công bố endpoint/gateway phù hợp |
| Consul check passing nhưng consumer lỗi | Agent check URL khác service address | Test hai đường mạng riêng |
| ZooKeeper có znode cũ | Persistent node hoặc session/cache chưa cập nhật | Kiểm tra ephemeral/session/watcher |
| Một registration lỗi làm cả ứng dụng DOWN | Readiness tổng hợp không phân biệt endpoint bắt buộc | Thiết kế health policy theo khả năng phục vụ |

## 18. Quy trình mở rộng registration an toàn

Trước khi viết code, hãy làm rõ:

1. Endpoint bổ sung có thực sự khác endpoint hiện tại về protocol, port, network hoặc lifecycle không?
2. Có thể giải quyết bằng metadata hoặc gateway hay không?
3. Consumer cần serviceId riêng nào?
4. Mỗi registration sẽ có instanceId duy nhất ra sao?
5. Registration nào do auto-registration quản lý?
6. Registration nào do custom lifecycle quản lý?
7. Registration được tạo sau khi server bind ở thời điểm nào?
8. Health check của endpoint dùng địa chỉ và protocol nào?
9. Khi shutdown, registration được deregister trước khi server dừng như thế nào?
10. Khi retry/reconnect, làm sao tránh tạo record trùng?
11. Consumer có filter đúng serviceId và metadata không?
12. Có integration test kiểm tra lookup và network reachability không?

Triển khai theo từng bước:
- Định nghĩa serviceId và schema metadata.
- Tạo registration bằng integration API phù hợp.
- Gắn lifecycle register/deregister.
- Kiểm thử idempotency và cleanup.
- Kiểm tra consumer lookup và endpoint reachability.
- Theo dõi số lượng record, health và lỗi trước khi triển khai rộng.

## 19. Checklist hoàn tất

Trước khi đưa registration bổ sung vào production, xác nhận:

1. Có lý do rõ ràng cho mỗi registration bổ sung.
2. Không tạo record mới chỉ để lặp metadata hoặc scale replica.
3. serviceId phân biệt đúng logical endpoint và protocol.
4. instanceId duy nhất, ổn định qua retry.
5. Host/port là endpoint consumer có thể truy cập.
6. Registration được tạo sau khi endpoint đã bind.
7. Auto-registration và manual registration không sở hữu cùng một record.
8. Mỗi registration có health check phù hợp.
9. Deregistration chạy trước khi endpoint dừng.
10. Retry không tạo record trùng.
11. Consumer chỉ truy vấn serviceId phù hợp.
12. Metadata có schema và không chứa secret.
13. Integration test xác minh record và ServiceInstance thực tế.
14. Có metric/log để phát hiện registration thừa hoặc stale.

Điểm cốt lõi là: **ServiceRegistry cho phép quản lý registration ở mức abstraction, nhưng không phải lý do để tạo thêm record tùy ý.** Chỉ mở rộng khi có endpoint logic độc lập cần discovery riêng; giữ identity, metadata, health check và lifecycle nhất quán để consumer luôn nhận đúng địa chỉ.

## 20. Tài liệu tham khảo

- Spring Cloud Commons — Common Abstractions, ServiceRegistry và auto-registration: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Commons — ServiceRegistry source: https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/ServiceRegistry.java
- Spring Cloud Commons — AbstractAutoServiceRegistration lifecycle: https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/AbstractAutoServiceRegistration.java

