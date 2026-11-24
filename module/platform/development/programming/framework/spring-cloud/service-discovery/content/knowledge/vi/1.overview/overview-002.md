# Vì sao địa chỉ cố định không phù hợp với dịch vụ co giãn

Trong một ứng dụng nhỏ, việc cấu hình một địa chỉ IP và port cho dịch vụ mà ứng dụng cần gọi có vẻ đơn giản. Ví dụ, order-service có thể gửi request đến inventory-service tại **10.0.2.15:8081**. Cách làm này hoạt động khi máy chủ ít thay đổi và số lượng instance gần như cố định.

Microservice thường được triển khai trong môi trường có container, máy ảo hoặc nền tảng điều phối. Instance có thể được tạo thêm khi tải tăng, bị thay thế khi lỗi, chuyển sang máy khác khi triển khai, hoặc bị thu hẹp khi nhu cầu giảm. Địa chỉ IP và port của từng instance vì thế không phải lúc nào cũng ổn định. Nếu consumer phụ thuộc vào một địa chỉ cụ thể, mỗi lần topology thay đổi đều có thể kéo theo việc sửa cấu hình và triển khai lại.

Đây là lý do service discovery trở thành một thành phần quan trọng trong kiến trúc microservice. Thay vì buộc consumer biết địa chỉ của từng instance, hệ thống dùng một tên dịch vụ logic để tìm các instance hiện có. Trong Spring Cloud, việc này được hỗ trợ thông qua các abstraction như **DiscoveryClient**, **ServiceRegistry**, registry như Eureka hoặc Consul, và cơ chế lựa chọn instance như Spring Cloud LoadBalancer.

## 1. Địa chỉ cố định tạo ra sự phụ thuộc vào hạ tầng

Một địa chỉ IP và port mô tả nơi một tiến trình đang lắng nghe tại một thời điểm. Nó không nhất thiết là danh tính lâu dài của dịch vụ.

Giả sử inventory-service đang chạy trên một máy có địa chỉ **10.0.2.15:8081**. order-service lưu địa chỉ này trong file cấu hình và gọi trực tiếp. Nếu inventory-service được triển khai lại trên máy khác, địa chỉ mới có thể là **10.0.3.22:8081**. Consumer vẫn gọi địa chỉ cũ cho đến khi cấu hình được cập nhật.

Khi có nhiều dịch vụ và nhiều môi trường, việc gắn cấu hình vào địa chỉ từng máy khiến ứng dụng phụ thuộc chặt vào cách bố trí hạ tầng. Một thay đổi triển khai tưởng như chỉ liên quan đến provider có thể buộc nhiều consumer phải thay đổi theo.

Sự phụ thuộc này thể hiện rõ ở một số tình huống phổ biến:

- **Thay đổi hạ tầng:** máy ảo hoặc container được tạo lại có thể nhận địa chỉ mới.
- **Triển khai phiên bản mới:** instance cũ bị dừng và instance mới được khởi tạo ở nơi khác.
- **Thay đổi mạng:** subnet, port mapping, NAT hoặc cấu hình mạng có thể làm địa chỉ mà consumer nhìn thấy thay đổi.
- **Nhiều môi trường:** địa chỉ của cùng một dịch vụ khác nhau giữa máy phát triển, kiểm thử, staging và production.

Vấn đề không nằm ở việc IP không thể dùng được, mà ở chỗ consumer phải biết và quản lý những chi tiết hạ tầng vốn có thể thay đổi độc lập với chức năng của dịch vụ.

## 2. Co giãn số lượng instance làm cấu hình tĩnh nhanh chóng lỗi thời

Một dịch vụ thường cần nhiều instance để phục vụ tải và tăng khả năng sẵn sàng. Khi lưu lượng tăng, nền tảng có thể tạo thêm instance; khi lưu lượng giảm, hệ thống có thể loại bỏ bớt instance.

Giả sử inventory-service ban đầu có hai instance:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.2.16:8081
~~~

Khi tải tăng, hệ thống bổ sung hai instance:

~~~text
inventory-service
  10.0.2.15:8081
  10.0.2.16:8081
  10.0.2.17:8081
  10.0.2.18:8081
~~~

Nếu order-service chỉ được cấu hình với hai địa chỉ ban đầu, nó không tự biết các instance mới đã xuất hiện. Một phần năng lực xử lý mới có thể không được sử dụng. Nếu hệ thống thu hẹp và loại bỏ **10.0.2.16:8081**, consumer vẫn có thể tiếp tục gửi request đến một địa chỉ không còn hoạt động.

Khi phải quản lý địa chỉ thủ công, mỗi lần tăng hoặc giảm số lượng instance đều đòi hỏi đồng bộ cấu hình giữa provider và các consumer. Càng nhiều consumer, nguy cơ cấu hình không đồng nhất càng lớn.

~~~mermaid
flowchart TD
    subgraph Static["Cấu hình địa chỉ tĩnh"]
      C["Order Service"] --> A["IP A"]
      C --> B["IP B"]
      N["Instance mới IP C"] -.->|"Consumer chưa biết"| C
    end
    subgraph Discovery["Tra cứu theo tên dịch vụ"]
      C2["Order Service"] -->|"inventory-service"| R[("Service Registry")]
      R --> A2["Instance A"]
      R --> B2["Instance B"]
      R --> C3["Instance C"]
    end
~~~

Với service discovery, provider đăng ký thông tin instance khi tham gia hệ thống. Consumer tra cứu theo service ID, chẳng hạn **inventory-service**, để nhận danh sách instance mà discovery client hiện biết. Khi danh sách được cập nhật, cơ chế gọi dịch vụ có thể lựa chọn instance mới mà không cần consumer ghi lại từng IP.

## 3. Một địa chỉ có thể không còn đại diện cho instance khỏe mạnh

Địa chỉ đúng về mặt cấu hình không đồng nghĩa tiến trình ở địa chỉ đó vẫn đang phục vụ request. Instance có thể bị crash, hết tài nguyên, mất kết nối mạng hoặc không còn sẵn sàng xử lý nghiệp vụ.

Nếu consumer lưu địa chỉ cố định, nó có thể tiếp tục gửi request đến instance đã hỏng. Để tránh điều này, consumer phải tự kiểm tra trạng thái, theo dõi lỗi kết nối và cập nhật danh sách địa chỉ. Khi có nhiều consumer, việc tự triển khai cơ chế này ở từng nơi trở nên khó đồng bộ.

Service registry giúp tập trung thông tin đăng ký và trạng thái mà hệ thống discovery quan sát được. Tùy nền tảng, instance có thể gửi heartbeat, được health check, hoặc bị loại khỏi registry sau một khoảng timeout. Consumer và bộ định tuyến có thể sử dụng thông tin đó để hạn chế chọn instance không còn phù hợp.

Tuy nhiên, registry không phải nguồn sự thật tức thời tuyệt đối. Một instance vừa lỗi có thể vẫn xuất hiện trong cache trong một khoảng thời gian; một instance vừa khởi động có thể chưa được nhìn thấy ở mọi consumer. Vì vậy, ứng dụng vẫn cần timeout, xử lý lỗi kết nối và các chính sách resilience phù hợp. Discovery giảm sự phụ thuộc vào địa chỉ thủ công, nhưng không loại bỏ mọi lỗi mạng hoặc lỗi ứng dụng.

## 4. Cấu hình địa chỉ từng instance làm tăng chi phí vận hành

Hãy hình dung một hệ thống có các dịch vụ order, inventory, payment và shipping. Mỗi dịch vụ có thể có nhiều consumer. Nếu mỗi consumer lưu danh sách IP và port của provider, đội vận hành phải đảm bảo tất cả cấu hình đều phản ánh đúng topology hiện tại.

| Thay đổi | Hệ quả khi dùng địa chỉ từng instance |
|---|---|
| Thêm instance | Cần cập nhật danh sách ở các consumer nếu muốn dùng instance mới. |
| Xóa instance | Phải loại địa chỉ cũ khỏi mọi cấu hình liên quan. |
| Thay máy hoặc container | Địa chỉ cũ có thể mất hiệu lực; consumer cần được cập nhật. |
| Triển khai nhiều môi trường | Cần duy trì bộ địa chỉ riêng cho từng môi trường. |
| Provider tạm thời không khỏe | Consumer có thể tiếp tục gọi đích lỗi nếu không có cơ chế phát hiện và loại bỏ. |

Các thay đổi này làm tăng số lần chỉnh sửa cấu hình, triển khai lại và kiểm tra sau triển khai. Cấu hình tĩnh cũng dễ dẫn đến sai lệch giữa các môi trường: một consumer có thể gọi đúng provider ở staging nhưng vẫn giữ địa chỉ của production hoặc một instance cũ.

Khi dùng tên dịch vụ logic, consumer phụ thuộc vào **service ID** thay vì từng địa chỉ instance. Danh sách địa chỉ được quản lý bởi registry và discovery client. Việc thêm hoặc thay thế instance vì thế có thể được xử lý trong cơ chế đăng ký và cập nhật discovery, thay vì sửa từng consumer.

## 5. Tên dịch vụ logic tách consumer khỏi địa chỉ vật lý

Tên dịch vụ logic mô tả dịch vụ mà consumer muốn sử dụng, ví dụ **inventory-service**. Registry ánh xạ tên này đến một hoặc nhiều instance đang được đăng ký.

~~~mermaid
flowchart LR
    C["Order Service"] -->|"Tìm inventory-service"| D["Discovery Client"]
    D <--> R[("Registry")]
    D -->|"Danh sách instance"| L["Load Balancer"]
    L --> I1["Inventory instance A"]
    L -.-> I2["Inventory instance B"]
~~~

Quá trình thường diễn ra như sau:

1. Mỗi instance provider đăng ký service ID và thông tin kết nối vào registry.
2. Consumer yêu cầu discovery client tìm instance theo service ID.
3. Discovery client trả về các instance đã biết, có thể từ registry hoặc dữ liệu cache.
4. Bộ cân bằng tải chọn một instance phù hợp cho request.
5. Consumer gửi request đến địa chỉ của instance được chọn.

Nhờ đó, consumer chỉ cần biết tên dịch vụ cần gọi. Provider có thể được triển khai lại, chuyển máy hoặc tăng giảm số lượng instance mà không yêu cầu consumer lưu danh sách địa chỉ cụ thể.

Điều này tạo ra một ranh giới rõ ràng giữa hai loại thông tin:

- **Danh tính logic:** service ID, chẳng hạn **inventory-service**. Đây là tên mà consumer dùng để yêu cầu một khả năng.
- **Địa chỉ instance:** host, port và thông tin kết nối của một tiến trình cụ thể. Đây là dữ liệu có thể thay đổi trong quá trình vận hành.

Tách hai loại thông tin giúp thay đổi hạ tầng ít tác động đến mã nghiệp vụ của consumer.

## 6. Ví dụ trong Spring Cloud

Một cách gọi phụ thuộc vào địa chỉ cố định có thể được cấu hình như sau:

~~~yaml
inventory:
  base-url: http://10.0.2.15:8081
~~~

Consumer sử dụng cấu hình này để gọi provider:

~~~java
String url = inventoryBaseUrl + "/api/items/" + itemId;
ItemDto item = restTemplate.getForObject(url, ItemDto.class);
~~~

Khi địa chỉ instance thay đổi, cấu hình **inventory.base-url** phải được cập nhật. Nếu provider có nhiều instance, ứng dụng còn cần một cách quản lý danh sách và lựa chọn đích đến.

Với Spring Cloud LoadBalancer, consumer có thể dùng service ID trong URL:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

~~~java
@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public ItemDto getItem(String itemId) {
        return restTemplate.getForObject(
            "http://inventory-service/api/items/{id}",
            ItemDto.class,
            itemId
        );
    }
}
~~~

Trong ví dụ này, **inventory-service** là service ID. RestTemplate được đánh dấu **@LoadBalanced** để Spring Cloud LoadBalancer xử lý việc tìm và chọn instance thông qua tích hợp discovery tương ứng. Provider vẫn phải được đăng ký vào registry, và ứng dụng phải có dependency cũng như cấu hình phù hợp với registry đang sử dụng.

Nếu cần truy vấn danh sách instance cho một mục đích riêng, Spring Cloud cung cấp **DiscoveryClient**:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");
~~~

Danh sách này cho biết discovery client đang biết những instance nào. Việc lựa chọn instance để gọi dịch vụ thường nên giao cho Spring Cloud LoadBalancer để chính sách cân bằng tải được áp dụng nhất quán.

## 7. Địa chỉ cố định có phải lúc nào cũng sai?

Không phải mọi địa chỉ cố định đều không phù hợp. Cần phân biệt **địa chỉ của từng instance** với **địa chỉ ổn định đại diện cho cả dịch vụ**.

Một virtual IP, DNS name hoặc địa chỉ load balancer có thể được thiết kế để ổn định trong khi các instance phía sau liên tục thay đổi. Consumer gọi địa chỉ ổn định đó; load balancer hoặc proxy chịu trách nhiệm phân phối request đến instance đang hoạt động. Đây là một cách triển khai hợp lệ của khám phá phía máy chủ.

| Loại địa chỉ | Đặc điểm | Cách sử dụng |
|---|---|---|
| IP và port của một instance | Gắn với một tiến trình cụ thể, có thể thay đổi | Chỉ phù hợp khi vòng đời instance thực sự ổn định hoặc có lý do vận hành rõ ràng |
| Tên dịch vụ logic | Đại diện cho nhóm instance của một dịch vụ | Phù hợp với discovery phía client khi client có tích hợp discovery và load balancing |
| Địa chỉ ổn định của load balancer hoặc gateway | Đại diện cho điểm truy cập chung; đích phía sau có thể thay đổi | Phù hợp với discovery phía máy chủ |

DNS cũng có thể cung cấp tên ổn định cho dịch vụ. Tuy vậy, cần xem xét cách DNS cập nhật bản ghi, thời gian cache, khả năng loại bỏ đích không khỏe mạnh và cách phân phối tải. Một tên DNS đơn giản không mặc nhiên cung cấp đầy đủ mọi chức năng của registry và load balancer.

Vì vậy, điều cần tránh là để mỗi consumer phụ thuộc trực tiếp vào địa chỉ riêng của từng instance có vòng đời ngắn. Một địa chỉ ổn định được quản lý bởi load balancer hoặc một tên logic được quản lý bởi service discovery vẫn có thể là điểm truy cập phù hợp.

## 8. Khi nào nên dùng service discovery?

Service discovery đặc biệt hữu ích khi hệ thống có một hoặc nhiều đặc điểm sau:

- Số lượng instance thay đổi theo tải hoặc chính sách autoscaling.
- Container hoặc máy ảo thường xuyên được tạo mới, thay thế và di chuyển.
- Nhiều consumer cần gọi cùng một provider.
- Ứng dụng chạy ở nhiều môi trường với topology khác nhau.
- Hệ thống cần cập nhật danh sách instance và loại bỏ đích không còn hợp lệ.
- Consumer cần chọn một instance từ nhiều instance để phân phối request.

Khi thiết kế, hãy xác định rõ nơi đăng ký instance, nơi tra cứu service ID, nơi thực hiện lựa chọn instance và cách cập nhật trạng thái sức khỏe. Trong Spring Cloud, các vai trò này thường được phối hợp qua **ServiceRegistry**, **DiscoveryClient**, Eureka hoặc Consul và Spring Cloud LoadBalancer.

Service discovery không làm cho địa chỉ mạng biến mất. Mỗi request cuối cùng vẫn phải đến một host và port cụ thể. Giá trị của discovery là quản lý việc ánh xạ từ tên dịch vụ logic sang các địa chỉ instance hiện tại, để consumer không phải tự duy trì danh sách địa chỉ có thể thay đổi theo hạ tầng.
