# Các khái niệm: dịch vụ, phiên bản chạy, sổ đăng ký và bên gọi

Khi một microservice cần gọi một microservice khác, ứng dụng gọi thường chỉ biết tên dịch vụ mà nó muốn sử dụng. Ví dụ, order-service cần tìm inventory-service để đọc thông tin hàng hóa. Trong môi trường triển khai thực tế, inventory-service có thể chạy thành nhiều tiến trình trên các máy hoặc container khác nhau. Các tiến trình này có địa chỉ mạng và trạng thái riêng, có thể thay đổi trong suốt vòng đời ứng dụng.

Để hiểu service discovery trong Spring Cloud, trước tiên cần phân biệt bốn khái niệm: **dịch vụ (service)** là khả năng logic mà hệ thống cung cấp; **instance** là một phiên bản đang chạy của dịch vụ; **service registry** lưu thông tin các instance đã đăng ký; và **consumer** là ứng dụng cần tìm, gọi dịch vụ. DiscoveryClient kết nối các khái niệm này bằng cách cho phép consumer tra cứu instance theo tên dịch vụ.

## 1. Dịch vụ (service): danh tính logic của một khả năng

Dịch vụ là một thành phần phần mềm cung cấp một nhóm chức năng qua một giao diện, thường là HTTP API, gRPC hoặc một giao thức giao tiếp khác. Trong kiến trúc microservice, mỗi dịch vụ thường chịu trách nhiệm cho một phạm vi nghiệp vụ tương đối rõ ràng.

Ví dụ:

- **inventory-service** quản lý tồn kho và cung cấp API tra cứu số lượng hàng.
- **order-service** tiếp nhận và quản lý đơn hàng.
- **payment-service** xử lý thanh toán.
- **shipping-service** quản lý việc giao hàng.

Tên dịch vụ là tên logic để các thành phần khác tham chiếu đến. Consumer có thể yêu cầu inventory-service mà không cần biết tiến trình nào đang thực hiện chức năng đó, đang chạy trên máy nào hoặc đang dùng port nào.

Trong Spring Cloud, tên dịch vụ thường được biểu diễn bằng **service ID**. Service ID là khóa tra cứu mà discovery client và registry sử dụng để nhóm các instance thuộc cùng một dịch vụ. Ví dụ, nhiều instance cùng đăng ký dưới service ID inventory-service.

Service ID cần nhất quán giữa nơi provider đăng ký và nơi consumer tra cứu. Nếu provider đăng ký với tên inventory-service nhưng consumer tìm product-inventory, consumer sẽ không nhận được nhóm instance mong muốn. Một số registry có quy tắc chuẩn hóa tên hoặc phân biệt chữ hoa, chữ thường; cần tuân theo quy tắc của nền tảng được tích hợp.

### Service không đồng nghĩa với một tiến trình

Một service có thể có một hoặc nhiều instance. Service là danh tính logic và phạm vi chức năng; instance là một tiến trình cụ thể đang thực thi chức năng đó.

~~~text
Service ID: inventory-service
  ├── Instance A: 10.0.2.15:8081
  ├── Instance B: 10.0.2.16:8081
  └── Instance C: 10.0.3.21:8081
~~~

Ba instance cùng cung cấp một dịch vụ logic, nhưng mỗi instance có địa chỉ và vòng đời riêng. Khi Instance B dừng, service inventory-service vẫn có thể tiếp tục hoạt động nhờ Instance A và C. Khi cần tăng năng lực xử lý, nền tảng có thể tạo thêm instance mà không cần đổi service ID.

## 2. Instance: một phiên bản đang chạy của dịch vụ

**Service instance** là một bản chạy cụ thể của service. Trong môi trường triển khai, instance có thể là một tiến trình Java, một container, một pod hoặc một đơn vị chạy khác tùy nền tảng. Từ góc nhìn service discovery, điều quan trọng là instance có thể được định vị và gọi qua thông tin kết nối.

Một bản ghi instance thường có các thông tin:

| Thuộc tính | Ý nghĩa |
|---|---|
| Service ID | Tên logic của dịch vụ mà instance thuộc về, ví dụ inventory-service. |
| Instance ID | Định danh một instance cụ thể trong nhóm instance của service. |
| Host | Tên máy hoặc địa chỉ IP mà consumer có thể truy cập. |
| Port | Cổng mà instance tiếp nhận request. |
| Scheme hoặc trạng thái secure | Cho biết cách tạo URI, ví dụ HTTP hoặc HTTPS tùy cấu hình. |
| Metadata | Thông tin bổ sung như zone, region, phiên bản ứng dụng hoặc nhóm triển khai. |

Ví dụ minh họa một bản ghi:

~~~yaml
serviceId: inventory-service
instanceId: inventory-7f8c9d
host: 10.0.2.15
port: 8081
metadata:
  zone: zone-a
  version: v2
~~~

Đây là cấu trúc minh họa để giải thích dữ liệu, không phải định dạng cấu hình chung bắt buộc của mọi registry. Eureka và Consul có cách lưu, biểu diễn và bổ sung thuộc tính riêng.

### Instance ID và service ID giải quyết hai nhu cầu khác nhau

Service ID gom các instance cùng cung cấp một dịch vụ. Instance ID phân biệt từng bản chạy trong nhóm đó. Nếu có ba instance inventory-service, cả ba cùng có service ID inventory-service nhưng cần có định danh riêng để registry theo dõi đăng ký, cập nhật và hủy đăng ký.

Instance ID cần đủ ổn định trong vòng đời mà registry quản lý, đồng thời không gây trùng lặp giữa các instance cùng service. Cách tạo ID phụ thuộc nền tảng: có thể dựa trên hostname, port, container ID, pod identity hoặc một giá trị do ứng dụng cấu hình.

### Phiên bản ứng dụng và instance không phải một khái niệm

Một phiên bản ứng dụng là bản phát hành phần mềm, ví dụ v1.4.0 hoặc v2.0.0. Instance là một lần chạy cụ thể của một phiên bản phần mềm. Một phiên bản có thể chạy thành nhiều instance; trong giai đoạn triển khai cuốn chiếu, nhiều phiên bản có thể cùng tồn tại trong một service.

~~~text
inventory-service
  ├── Instance A — application version v1.4
  ├── Instance B — application version v1.4
  └── Instance C — application version v2.0
~~~

Thông tin version có thể được đưa vào metadata để hỗ trợ quan sát, định tuyến hoặc kiểm soát tương thích. Tuy nhiên, service discovery không tự quyết định rằng phiên bản mới tương thích với mọi consumer. Chính sách chọn phiên bản, triển khai canary, chia lưu lượng hoặc loại bỏ phiên bản cũ cần được thiết kế riêng.

## 3. Service registry: sổ đăng ký các instance

**Service registry** là nơi lưu thông tin đăng ký của các service instance. Provider đăng ký khi instance tham gia hệ thống và hủy đăng ký khi dừng có kiểm soát. Registry cung cấp dữ liệu để consumer hoặc thành phần định tuyến tìm được các instance theo service ID.

~~~mermaid
flowchart TD
    P1["Inventory instance A"] -->|"Đăng ký"| R[("Service Registry")]
    P2["Inventory instance B"] -->|"Đăng ký"| R
    P3["Inventory instance C"] -->|"Đăng ký"| R
    C["Order Service"] -->|"Tra cứu inventory-service"| R
    R -->|"Danh sách instance"| C
~~~

Registry thường hỗ trợ các thao tác hoặc cơ chế tương đương:

- **Register:** thêm bản ghi instance khi provider tham gia hệ thống.
- **Renew hoặc heartbeat:** cập nhật tín hiệu tồn tại theo chu kỳ, nếu registry sử dụng cơ chế lease hoặc heartbeat.
- **Update:** thay đổi thuộc tính đăng ký khi thông tin instance thay đổi.
- **Deregister:** xóa bản ghi khi instance dừng có kiểm soát.
- **Health check và expiration:** phát hiện instance không còn khỏe mạnh hoặc không còn gia hạn đăng ký theo chính sách của registry.
- **Query:** trả về danh sách instance theo service ID.

Không phải registry nào cũng triển khai các thao tác này theo cùng một cách. Ví dụ, Eureka thường sử dụng cơ chế lease và heartbeat để theo dõi client; Consul có thể kết hợp đăng ký service với health check. Cấu hình và hành vi cụ thể cần theo phiên bản và tích hợp đang sử dụng.

### Registry không phải nơi thực thi nghiệp vụ

Registry giữ thông tin định vị và trạng thái đăng ký. Nó không xử lý nghiệp vụ tra cứu tồn kho, tạo đơn hàng hoặc thanh toán. Khi consumer tìm được địa chỉ instance, request nghiệp vụ vẫn được gửi đến ứng dụng provider.

Registry cũng không nhất thiết nằm trên đường đi của mọi request. Trong mô hình client-side discovery, consumer có thể lấy danh sách instance rồi gọi trực tiếp provider. Danh sách có thể được cache hoặc cập nhật định kỳ. Trong mô hình server-side discovery, load balancer hoặc gateway có thể tra cứu registry hoặc nhận danh sách đã đồng bộ để chuyển tiếp request.

### Registry có thể chứa dữ liệu chậm hơn thực tế

Một bản ghi trong registry phản ánh điều mà registry biết tại thời điểm cập nhật gần nhất. Nếu một instance bị dừng đột ngột, bản ghi có thể còn tồn tại cho đến khi heartbeat hết hạn hoặc health check phát hiện lỗi. Ngược lại, instance mới có thể mất một khoảng thời gian để đăng ký và xuất hiện trong kết quả tra cứu.

Vì vậy, danh sách instance không phải cam kết rằng mọi địa chỉ đều có thể kết nối thành công ngay lúc consumer gửi request. Consumer vẫn cần timeout, xử lý lỗi kết nối và chính sách retry phù hợp. Thời gian heartbeat, health check, cache và refresh ảnh hưởng đến độ trễ phát hiện thay đổi.

## 4. Provider: thành phần đăng ký instance

**Service provider** là ứng dụng cung cấp chức năng cho consumer. Khi khởi động, provider thường tham gia quy trình đăng ký để registry biết service ID và địa chỉ có thể dùng để truy cập instance.

Ví dụ, một instance inventory-service khởi động trên host 10.0.2.15, port 8081. Nó đăng ký service ID inventory-service cùng thông tin định vị tương ứng. Khi instance dừng có kiểm soát, nó có thể hủy đăng ký để registry không tiếp tục cung cấp địa chỉ đó cho consumer.

Trong Spring Cloud, abstraction **ServiceRegistry** mô tả thao tác đăng ký và hủy đăng ký một registration. Registration chứa thông tin mà implementation cụ thể cần để đăng ký instance. Starter của Eureka, Consul hoặc nền tảng khác có thể tự động hóa phần lớn vòng đời này theo cấu hình. Ứng dụng không nên giả định mọi registry có cùng kiểu registration hoặc cùng quy trình nội bộ.

Các trách nhiệm vận hành của provider thường gồm:

1. Khởi động ứng dụng và xác định service ID, instance ID cùng thông tin địa chỉ.
2. Đăng ký instance với registry hoặc để tích hợp tự động thực hiện việc này.
3. Duy trì heartbeat hoặc đáp ứng health check theo yêu cầu của registry.
4. Cập nhật thông tin đăng ký nếu địa chỉ hoặc metadata cần thay đổi.
5. Hủy đăng ký khi shutdown có kiểm soát; đồng thời hoàn tất hoặc từ chối request mới theo chính sách graceful shutdown.

Địa chỉ đăng ký phải có thể truy cập từ consumer hoặc từ thành phần định tuyến sẽ gọi provider. Một container có thể nhìn thấy địa chỉ nội bộ khác với địa chỉ mà consumer bên ngoài mạng container có thể truy cập. Cần cấu hình địa chỉ quảng bá, port mapping, DNS và firewall đúng với topology triển khai.

## 5. Consumer: bên cần tìm và gọi dịch vụ

**Service consumer** là ứng dụng cần sử dụng chức năng do provider cung cấp. Consumer không cần biết instance cụ thể ngay từ lúc viết mã. Nó có thể tham chiếu đến service ID, sau đó dùng discovery để lấy danh sách instance hiện tại.

Ví dụ, order-service cần kiểm tra tồn kho trước khi xác nhận đơn. Nó tra cứu inventory-service và nhận được một hoặc nhiều instance. Sau đó, cơ chế load balancing có thể chọn một instance để gửi request.

~~~mermaid
sequenceDiagram
    participant O as Order Service (Consumer)
    participant D as DiscoveryClient
    participant R as Service Registry
    participant I as Inventory Instance
    O->>D: getInstances(inventory-service)
    D->>R: Tra cứu service ID
    R-->>D: Danh sách instance đã đăng ký
    D-->>O: Danh sách ServiceInstance
    O->>I: Gọi API inventory tại instance được chọn
    I-->>O: Kết quả nghiệp vụ
~~~

Consumer thường có các trách nhiệm:

- Xác định đúng service ID cần gọi.
- Lấy danh sách instance qua discovery client hoặc tích hợp định tuyến.
- Chọn instance bằng load balancer nếu có nhiều lựa chọn.
- Gửi request đến địa chỉ instance.
- Xử lý timeout, lỗi kết nối, lỗi nghiệp vụ và trường hợp không tìm thấy instance.

Consumer có thể là một service Spring Cloud khác, ứng dụng chạy bằng ngôn ngữ khác, API Gateway hoặc một thành phần hạ tầng. Cách tích hợp phụ thuộc mô hình discovery và khả năng truy cập registry của từng loại consumer.

## 6. Các abstraction Spring Cloud liên kết những khái niệm này

Spring Cloud cung cấp abstraction để ứng dụng sử dụng service discovery mà không phải phụ thuộc trực tiếp vào API của một registry cụ thể.

| Abstraction | Vai trò | Liên hệ với khái niệm |
|---|---|---|
| DiscoveryClient | Truy vấn danh sách service và instance theo service ID | Consumer tìm provider |
| ServiceInstance | Mô tả một instance đã được phát hiện | Địa chỉ và metadata của phiên bản chạy |
| ServiceRegistry | Đăng ký và hủy đăng ký một registration | Provider đưa instance vào hoặc rời registry |
| Registration | Mang dữ liệu đăng ký mà registry implementation cần | Thông tin của instance khi đăng ký |
| Spring Cloud LoadBalancer | Chọn instance phù hợp cho request | Consumer quyết định gửi request đến instance nào |

### Tra cứu bằng DiscoveryClient

DiscoveryClient cung cấp API để liệt kê các service ID mà client biết và lấy instance theo service ID. Ví dụ:

~~~java
@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Kết quả là danh sách ServiceInstance. Mỗi phần tử mô tả một instance được discovery client biết, bao gồm thông tin như service ID, host, port, URI và metadata tùy implementation.

Một số cách sử dụng khác:

~~~java
List<String> serviceIds = discoveryClient.getServices();
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");
~~~

Danh sách service ID và instance phản ánh dữ liệu mà client có thể truy cập tại thời điểm gọi. Nếu danh sách rỗng, cần kiểm tra service ID, trạng thái đăng ký, cấu hình registry, kết nối mạng và quyền truy cập.

### Đăng ký bằng ServiceRegistry

ServiceRegistry biểu diễn thao tác đăng ký một Registration và hủy đăng ký registration đó. Kiểu Registration cụ thể phụ thuộc registry được tích hợp. Trong nhiều ứng dụng Spring Cloud, starter tự động đăng ký instance dựa trên cấu hình; chỉ nên gọi API đăng ký thủ công khi có nhu cầu và đã hiểu vòng đời của registration.

Điểm quan trọng là ServiceRegistry phục vụ phía provider, còn DiscoveryClient thường được consumer dùng để tra cứu. Hai abstraction có liên quan nhưng đảm nhiệm hai hướng thao tác khác nhau.

### Load balancing là bước lựa chọn

Discovery cho biết những instance nào được biết đến. Load balancing chọn instance nào sẽ nhận request hiện tại. Khi có nhiều instance, Spring Cloud LoadBalancer có thể thực hiện lựa chọn theo cấu hình và chiến lược của ứng dụng.

Ví dụ, một RestTemplate được đánh dấu @LoadBalanced có thể gọi bằng service ID:

~~~java
@Bean
@LoadBalanced
RestTemplate restTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

~~~java
restTemplate.getForObject(
    "http://inventory-service/api/items/{id}",
    ItemDto.class,
    itemId
);
~~~

Tên inventory-service được phân giải thông qua tích hợp discovery và Spring Cloud LoadBalancer. Provider phải có instance được đăng ký và consumer phải có dependency/configuration tương ứng. Đoạn mã này minh họa cách sử dụng; các import, DTO, dependency và cấu hình registry cần được bổ sung trong ứng dụng thực tế.

## 7. Ghép các khái niệm thành một luồng hoàn chỉnh

Giả sử hệ thống có order-service và inventory-service. Inventory service đang chạy ba instance. Khi order-service cần kiểm tra tồn kho, các thành phần phối hợp như sau:

1. **Service:** inventory-service là tên logic của chức năng kiểm tra tồn kho.
2. **Instance:** ba tiến trình inventory-service đang chạy có ba địa chỉ và instance ID riêng.
3. **Provider:** mỗi tiến trình đăng ký thông tin của mình vào registry.
4. **Registry:** lưu các bản ghi và trạng thái mà nó quan sát được.
5. **Consumer:** order-service yêu cầu tìm inventory-service theo service ID.
6. **DiscoveryClient:** truy vấn registry hoặc dữ liệu discovery mà client đang duy trì và trả về danh sách ServiceInstance.
7. **Load balancer:** chọn một instance phù hợp cho request.
8. **Request:** order-service gọi trực tiếp địa chỉ instance được chọn, hoặc gửi qua một thành phần trung gian tùy kiến trúc.

~~~mermaid
flowchart TB
    S["Service: inventory-service"]
    S --> A["Instance A"]
    S --> B["Instance B"]
    S --> C["Instance C"]
    A -->|"Register / heartbeat"| R[("Registry")]
    B -->|"Register / heartbeat"| R
    C -->|"Register / heartbeat"| R
    O["Consumer: order-service"] -->|"Service ID"| D["DiscoveryClient"]
    D -->|"Query"| R
    R -->|"ServiceInstance list"| D
    D --> L["Load Balancer"]
    L -->|"Request đến instance được chọn"| A
~~~

Khi Instance B dừng, provider có thể hủy đăng ký hoặc registry phát hiện bản ghi hết hạn/không khỏe mạnh theo cơ chế của nó. Khi consumer nhận được danh sách cập nhật, load balancer có thể chọn A hoặc C. Trong khoảng thời gian registry hoặc cache chưa cập nhật, consumer vẫn có thể gặp lỗi khi gọi B; do đó timeout và xử lý lỗi vẫn cần thiết.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Service và instance là một | Service là danh tính logic; instance là một bản chạy cụ thể của service. |
| Instance ID và service ID giống nhau | Service ID gom các instance; instance ID phân biệt từng bản chạy. |
| Registry xử lý request nghiệp vụ | Registry lưu thông tin đăng ký; provider mới xử lý nghiệp vụ. |
| Có bản ghi trong registry nghĩa là instance chắc chắn khỏe | Bản ghi có thể chậm hơn thực tế; cần health check, timeout và xử lý lỗi. |
| DiscoveryClient tự chọn instance cho mọi request | DiscoveryClient truy vấn instance; load balancer đảm nhiệm lựa chọn khi được tích hợp. |
| Phiên bản ứng dụng chính là instance | Một phiên bản có thể có nhiều instance; nhiều phiên bản cũng có thể chạy đồng thời. |
| Consumer luôn phải gọi registry trên mỗi request | Tùy implementation, discovery client hoặc proxy có thể cache hay đồng bộ danh sách. |

Khi phân tích một sự cố discovery, hãy xác định lỗi nằm ở bước nào: provider chưa đăng ký, service ID không khớp, registry chưa cập nhật, consumer không truy vấn được, danh sách instance bị cũ, load balancer chọn đích không phù hợp hay địa chỉ instance không thể truy cập từ mạng của consumer. Phân loại theo từng bước giúp khoanh vùng nguyên nhân rõ ràng hơn.

## 9. Ghi nhớ khi thiết kế

- Đặt service ID ổn định và thống nhất giữa provider với consumer.
- Đảm bảo mỗi instance có định danh riêng và địa chỉ mà consumer có thể truy cập.
- Hiểu cơ chế đăng ký, heartbeat, health check và hủy đăng ký của registry đang dùng.
- Dùng DiscoveryClient để tra cứu và ServiceRegistry cho thao tác đăng ký theo abstraction Spring Cloud phù hợp.
- Tách việc tìm danh sách instance khỏi việc chọn instance để gửi request.
- Theo dõi metadata như zone hoặc version khi có nhu cầu định tuyến, nhưng xác định rõ chính sách sử dụng metadata.
- Thiết kế timeout, retry có giới hạn và graceful shutdown để xử lý khoảng trễ khi trạng thái registry thay đổi.

Nắm vững service, instance, registry và consumer là nền tảng để học sâu hơn về DiscoveryClient, ServiceRegistry, Eureka, Consul, health check và load balancing. Các thành phần này cùng tạo nên cơ chế ánh xạ từ tên dịch vụ logic đến một instance có thể nhận request trong môi trường microservice luôn thay đổi.
