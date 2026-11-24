# Trạng thái kết nối Zookeeper khác trạng thái sức khỏe nghiệp vụ

Trong hệ thống dùng ZooKeeper để service discovery, một service có thể vẫn giữ kết nối ZooKeeper nhưng không còn xử lý được yêu cầu nghiệp vụ. Ngược lại, ứng dụng có thể vẫn xử lý request hiện tại bình thường trong lúc kết nối đến ZooKeeper bị gián đoạn.

Hai trạng thái này mô tả hai khía cạnh khác nhau:

- **Trạng thái kết nối/session ZooKeeper** cho biết client còn giao tiếp được với ZooKeeper và session đăng ký còn hiệu lực hay không.
- **Trạng thái sức khỏe nghiệp vụ** cho biết ứng dụng có sẵn sàng nhận và xử lý request hay không, dựa trên khả năng hoạt động của chính ứng dụng và các dependency cần thiết.

Nếu chỉ dựa vào trạng thái kết nối ZooKeeper để quyết định service có khỏe hay không, registry có thể giữ một instance không còn phục vụ được. Nếu chỉ dựa vào health của ứng dụng, consumer lại có thể không tìm thấy instance sau khi session ZooKeeper hết hạn. Cần theo dõi hai tín hiệu riêng và kết hợp chúng theo chính sách readiness của hệ thống.

## 1. Phân biệt các tín hiệu trạng thái

Một ứng dụng có thể có nhiều trạng thái độc lập:

| Tín hiệu | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| ZooKeeper connection state | Client đang kết nối đến cụm ZooKeeper hay đang mất kết nối? | CONNECTED, SUSPENDED, RECONNECTED, LOST |
| ZooKeeper session state | Session hiện tại còn hiệu lực không? | Session còn hạn hoặc đã hết hạn |
| Registration state | Ephemeral znode đại diện instance có còn trong cây dữ liệu không? | Node tồn tại hoặc đã bị xóa khi session hết hạn |
| Business health | Ứng dụng và dependency nghiệp vụ có hoạt động không? | Database truy cập được, xử lý tồn kho thành công |
| Liveness | Tiến trình có còn sống và có thể tiếp tục chạy không? | JVM không deadlock, event loop còn hoạt động |
| Readiness | Ứng dụng có nên nhận request mới lúc này không? | Đã khởi tạo xong, dependency cần thiết sẵn sàng |

Các trạng thái có liên quan nhưng không đồng nghĩa. Ví dụ, CONNECTED chỉ cho biết client có kết nối với ZooKeeper; nó không chứng minh database của ứng dụng đang hoạt động. Một ephemeral znode còn tồn tại cho biết session sở hữu node chưa bị ZooKeeper loại bỏ; nó không chứng minh endpoint HTTP vẫn trả kết quả nghiệp vụ đúng.

Trong các client như Apache Curator, các trạng thái kết nối phổ biến gồm:

| Curator ConnectionState | Ý nghĩa | Điều cần lưu ý |
|---|---|---|
| CONNECTED | Client đã thiết lập kết nối ban đầu | Chưa đủ để kết luận ứng dụng sẵn sàng |
| SUSPENDED | Kết nối tạm thời bị gián đoạn | Session có thể vẫn còn hiệu lực trong thời gian chờ timeout |
| RECONNECTED | Client đã kết nối trở lại | Cần xác minh session và registration |
| LOST | Session đã hết hạn hoặc bị mất | Ephemeral nodes thuộc session cũ đã bị xóa |
| READ_ONLY | Client đang kết nối ở chế độ chỉ đọc nếu cấu hình cho phép | Có thể đọc dữ liệu nhưng không thể đăng ký/cập nhật node |

Tên và cách phát sự kiện cụ thể phụ thuộc thư viện client. Không nên giả định mọi ZooKeeper client đều có cùng enum hoặc cùng hành vi tự khôi phục.

## 2. Session ZooKeeper và vòng đời ephemeral znode

ZooKeeper duy trì session cho từng client. Client gửi heartbeat/ping để giữ session sống. Session timeout được thương lượng giữa client và server trong giới hạn cấu hình. Nếu client không thể kết nối lại trước khi timeout, ZooKeeper đánh dấu session đã hết hạn.

Service discovery thường dùng ephemeral znode để biểu diễn instance đang đăng ký. Ephemeral znode được tạo bởi một session và tự động bị xóa khi session đó kết thúc hoặc hết hạn.

Một luồng đơn giản:

1. Ứng dụng tạo ZooKeeper client và kết nối đến ensemble.
2. Client tạo ephemeral znode chứa service name, instance ID, host, port và metadata.
3. Consumer theo dõi hoặc đọc các node con để tìm instance.
4. Nếu ứng dụng đóng session có kiểm soát, hoặc session hết hạn, ZooKeeper xóa ephemeral znode thuộc session đó.
5. Nếu ứng dụng kết nối lại bằng một session mới, nó phải đăng ký lại ephemeral znode.

Ví dụ cây dữ liệu:

~~~text
/services
  /inventory-service
    /instances
      /inventory-node-a
      /inventory-node-b
  /payment-service
    /instances
      /payment-node-a
~~~

Mỗi node instance có thể lưu thông tin như:

~~~json
{
  "service": "inventory-service",
  "instanceId": "inventory-node-a",
  "host": "10.20.1.11",
  "port": 8081,
  "version": "v2"
}
~~~

Đây là dữ liệu đăng ký và định tuyến. Việc node tồn tại chỉ phản ánh vòng đời session hoặc cơ chế đăng ký của client. Nếu ứng dụng bị lỗi nghiệp vụ nhưng vẫn duy trì session, node có thể tiếp tục tồn tại cho đến khi ứng dụng chủ động gỡ đăng ký hoặc session hết hạn.

Cũng cần phân biệt ephemeral node với persistent node. Persistent node không tự bị xóa khi session client kết thúc. Nếu dùng persistent node cho registration mà không có cơ chế dọn dẹp, node cũ có thể tồn tại sau khi tiến trình đã dừng. Với ephemeral node, việc mất session sẽ tự dọn registration, nhưng không thay thế health check nghiệp vụ.

## 3. Trạng thái kết nối không phải trạng thái sức khỏe nghiệp vụ

Xét dịch vụ inventory có các thành phần:

- Ứng dụng Spring Boot nhận HTTP request.
- ZooKeeper lưu registration để consumer tìm instance.
- Database lưu số lượng tồn kho.
- Một dịch vụ pricing cung cấp giá sản phẩm.

Nếu ZooKeeper báo CONNECTED nhưng database bị lỗi, ứng dụng có thể vẫn giữ ephemeral znode. Consumer đọc registry vẫn nhìn thấy instance đó và có thể gửi request đến một API không thể hoàn thành nghiệp vụ.

Ngược lại, nếu database và pricing vẫn hoạt động nhưng mạng đến ZooKeeper bị gián đoạn, ứng dụng có thể xử lý những request hiện tại hoặc request đến qua một kết nối đã có. Tuy nhiên, ứng dụng không thể chắc chắn cập nhật registration, tạo node mới hoặc nhận thay đổi discovery từ ZooKeeper.

Sơ đồ thể hiện hai luồng kiểm tra độc lập:

~~~mermaid
flowchart TB
    App["Ứng dụng inventory"]
    ZKClient["ZooKeeper client"]
    ZK["ZooKeeper ensemble"]
    Registry["Ephemeral registration"]
    Health["Business health / readiness"]
    DB["Inventory database"]
    Pricing["Pricing service"]
    Consumer["Service consumer"]

    App --> ZKClient
    ZKClient -->|"Session và heartbeat"| ZK
    ZKClient -->|"Tạo / cập nhật node"| Registry
    App -->|"Kiểm tra dependency"| DB
    App -->|"Kiểm tra dependency"| Pricing
    DB --> Health
    Pricing --> Health
    Health -->|"Readiness của ứng dụng"| App
    Consumer -->|"Đọc instance"| Registry
    Consumer -->|"HTTP request"| App
~~~

ZooKeeper cung cấp cơ chế phối hợp và discovery. Health indicator của ứng dụng phải kiểm tra các điều kiện nghiệp vụ cần thiết để nhận request. Không dùng trạng thái session để thay thế các phép kiểm tra này.

## 4. Bảng kết hợp giữa session và business health

Bốn tình huống cơ bản cần được xử lý riêng:

| ZooKeeper session | Business health | Diễn giải | Hành động thường phù hợp |
|---|---|---|---|
| CONNECTED | UP | Có kết nối discovery và ứng dụng đang khỏe | Có thể nhận request nếu readiness cũng UP |
| CONNECTED | DOWN | Registry vẫn biết instance nhưng ứng dụng không khỏe | Đánh dấu không sẵn sàng hoặc gỡ registration theo chính sách |
| SUSPENDED/LOST | UP | Ứng dụng có thể còn xử lý request nhưng discovery đang không chắc chắn hoặc đã mất session | Theo dõi session, tránh khẳng định registration còn mới; phục hồi và đăng ký lại khi cần |
| SUSPENDED/LOST | DOWN | Cả discovery lẫn nghiệp vụ đều có vấn đề | Không nhận request mới; khôi phục từng thành phần và xác minh lại trước khi công bố |

Có một khác biệt quan trọng giữa SUSPENDED và LOST:

- SUSPENDED báo hiệu kết nối bị gián đoạn. Session có thể vẫn tồn tại trong thời gian timeout; ephemeral znode chưa nhất thiết bị xóa.
- LOST báo hiệu session cũ đã hết hạn. Các ephemeral znode thuộc session cũ đã bị xóa; client cần tạo session mới và khôi phục registration.

Trong thời gian SUSPENDED, client không thể chắc chắn server đã nhận được thao tác ghi gần nhất hay chưa. Không nên tự kết luận node đã mất ngay lập tức. Khi LOST được phát ra, client mới có tín hiệu rõ ràng rằng session cũ không còn sử dụng được.

READ_ONLY cũng cần được xử lý riêng: ứng dụng có thể đọc trạng thái registry nhưng không thể tạo hoặc cập nhật ephemeral registration. Một consumer có thể tiếp tục tra cứu dữ liệu cũ, nhưng provider không thể bảo đảm đăng ký mới được ghi thành công.

## 5. Business health nên kiểm tra điều gì?

Business health cần phản ánh khả năng thực hiện công việc mà service cam kết. Không phải mọi dependency đều phải được đưa vào readiness; chỉ kiểm tra những dependency thiết yếu cho request cần phục vụ.

Ví dụ với inventory-service:

| Thành phần | Câu hỏi kiểm tra | Có thể ảnh hưởng readiness? |
|---|---|---|
| Database tồn kho | Có kết nối và đọc/ghi được dữ liệu cần thiết không? | Có, nếu API cần database để xử lý |
| Pricing service | Có truy cập được khi request cần tính giá không? | Tùy API và khả năng fallback |
| Cache | Có hoạt động không? | Tùy cache là bắt buộc hay có thể đọc trực tiếp database |
| ZooKeeper | Có kết nối và cập nhật discovery được không? | Có thể ảnh hưởng readiness theo chính sách triển khai, nhưng không thay thế business health |
| HTTP server | Có nhận request và xử lý thread/event loop không? | Có |
| Bộ xử lý nền | Có hoạt động nếu service cần nó để hoàn tất nghiệp vụ không? | Tùy vai trò |

Nên tách ba loại kiểm tra:

- **Liveness:** tiến trình còn sống và không bị kẹt đến mức cần khởi động lại.
- **Readiness:** instance có thể nhận request mới một cách an toàn.
- **Dependency/business health:** các thành phần cần thiết cho nghiệp vụ có đang hoạt động không.

Ví dụ, database tạm thời mất kết nối có thể làm readiness DOWN nhưng không nhất thiết làm liveness DOWN. Nếu liveness cũng DOWN và orchestrator liên tục restart ứng dụng, hệ thống có thể tạo vòng lặp restart trong khi lỗi thực sự nằm ở database bên ngoài.

Spring Boot Actuator có thể công bố các endpoint health và trạng thái readiness/liveness. Một health indicator tùy chỉnh có thể kiểm tra dependency nghiệp vụ:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class InventoryDatabaseHealthIndicator implements HealthIndicator {

    private final InventoryRepository repository;

    public InventoryDatabaseHealthIndicator(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public Health health() {
        try {
            repository.ping();
            return Health.up().build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("dependency", "inventory-database")
                    .build();
        }
    }
}
~~~

InventoryRepository và phương thức ping() là ví dụ minh họa; triển khai thực tế cần dùng thao tác kiểm tra nhẹ, có timeout và không tạo tải lớn lên database. Không trả stack trace, thông tin kết nối hoặc secret ra health endpoint.

Để endpoint readiness tổng hợp health indicator này, cần bật các probe và đưa contributor nghiệp vụ vào readiness group theo tên mà Actuator công bố. Ví dụ cấu hình minh họa:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,inventoryDatabase
~~~

Tên contributor trong group phải khớp tên health component thực tế. Nếu không đưa inventoryDatabase vào readiness group, indicator có thể xuất hiện ở health tổng hợp nhưng chưa chắc ảnh hưởng endpoint readiness.

## 6. Kết hợp ZooKeeper session với readiness

Không có một chính sách duy nhất phù hợp cho mọi service. Quyết định readiness cần dựa trên cách ứng dụng sử dụng ZooKeeper.

### Trường hợp ZooKeeper chỉ phục vụ discovery

Nếu ứng dụng có thể tiếp tục xử lý request đã nhận mà không cần ZooKeeper, mất kết nối tạm thời không nhất thiết làm business health DOWN. Tuy nhiên, ứng dụng có thể không nhận được thay đổi registry và không thể đăng ký instance mới.

Có thể áp dụng chính sách:

- Giữ liveness UP.
- Đánh dấu discovery connectivity là DEGRADED hoặc UNKNOWN khi SUSPENDED.
- Không tuyên bố registration đã được cập nhật trong thời gian mất kết nối.
- Nếu session LOST, chờ tạo session mới và xác minh registration đã được phục hồi.
- Quyết định readiness theo khả năng consumer tìm thấy instance và yêu cầu của hệ thống.

### Trường hợp request phụ thuộc trực tiếp vào ZooKeeper

Nếu mỗi request cần đọc hoặc ghi dữ liệu điều phối từ ZooKeeper, mất session có thể khiến ứng dụng không thể thực hiện nghiệp vụ. Khi đó readiness nên DOWN cho đến khi kết nối và thao tác cần thiết hoạt động trở lại.

### Trường hợp ZooKeeper giữ khóa hoặc quyền sở hữu tài nguyên

Nếu service dùng ephemeral node để giữ leader lock, distributed lock hoặc quyền sở hữu một tài nguyên, mất session có thể đồng nghĩa ứng dụng đã mất quyền sở hữu. Ứng dụng phải ngừng thao tác yêu cầu quyền đó ngay khi không còn chắc chắn session còn hiệu lực. Không được tiếp tục ghi dữ liệu chỉ vì process vẫn sống hoặc business health check cục bộ vẫn trả UP.

Trong trường hợp này, readiness và business health cần phản ánh quyền sở hữu hiện tại. Khi kết nối lại, không tự giả định quyền cũ vẫn còn; phải tham gia lại quy trình bầu chọn hoặc lấy khóa theo cơ chế của hệ thống.

## 7. Theo dõi connection state bằng Apache Curator

Curator cung cấp ConnectionStateListener để ứng dụng nhận sự kiện kết nối. Ví dụ sau minh họa cách tách trạng thái kết nối khỏi business health và đánh dấu registration cần phục hồi sau khi session bị mất.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.framework.state.ConnectionStateListener;

public class ZooKeeperConnectionMonitor {

    private final AtomicBoolean registrationWritable = new AtomicBoolean(false);
    private final AtomicBoolean sessionLost = new AtomicBoolean(false);
    private final ServiceRegistration registration;

    public ZooKeeperConnectionMonitor(ServiceRegistration registration) {
        this.registration = registration;
    }

    public void attach(CuratorFramework client) {
        client.getConnectionStateListenable().addListener(
                new ConnectionStateListener() {
                    @Override
                    public void stateChanged(
                            CuratorFramework ignored,
                            ConnectionState state) {

                        switch (state) {
                            case CONNECTED:
                                registrationWritable.set(true);
                                break;

                            case SUSPENDED:
                                registrationWritable.set(false);
                                // Session có thể vẫn còn trong thời gian timeout.
                                break;

                            case READ_ONLY:
                                registrationWritable.set(false);
                                // Có thể đọc nhưng không thể ghi registration.
                                break;

                            case LOST:
                                registrationWritable.set(false);
                                sessionLost.set(true);
                                // Ephemeral nodes của session cũ đã bị xóa.
                                break;

                            case RECONNECTED:
                                registrationWritable.set(true);
                                if (sessionLost.getAndSet(false)) {
                                    registration.scheduleEnsureRegistered();
                                }
                                break;
                        }
                    }
                });
    }

    public boolean canWriteRegistration() {
        return registrationWritable.get();
    }
}
~~~

ServiceRegistration là abstraction của ứng dụng, không phải class có sẵn trong Curator. Phương thức scheduleEnsureRegistered() nên đẩy công việc sang executor riêng; tác vụ đó thực hiện đăng ký an toàn khi được gọi lại: tạo lại ephemeral node với session hiện tại, xác minh dữ liệu và xử lý trường hợp node đã tồn tại. Tên canWriteRegistration() thể hiện rõ đây là khả năng ghi registration; READ_ONLY vẫn là một kết nối nhưng không thể cập nhật node.

Một số lưu ý khi dùng listener:

- SUSPENDED không đồng nghĩa session đã hết hạn. Không xóa registration hoặc tự tạo session mới chỉ vì sự kiện này.
- LOST có nghĩa session cũ đã mất; các ephemeral node thuộc session đó không còn.
- Sau RECONNECTED, cần xác minh registration. Nếu client library hoặc service discovery recipe đã tự phục hồi, tránh tạo node trùng.
- READ_ONLY không cho phép ghi registration; trạng thái này không nên được xem như kết nối đầy đủ cho provider.
- Callback cần xử lý nhanh, không chạy tác vụ mạng dài hoặc block event thread. Có thể gửi công việc phục hồi sang executor riêng.
- Tùy phiên bản Curator và cách cấu hình, trạng thái ban đầu hoặc chuỗi event có thể khác. Kiểm tra tài liệu của phiên bản đang sử dụng.

Ví dụ trên chỉ quản lý tín hiệu kết nối và gọi một abstraction phục hồi registration. Nó không tự tính business health. Health indicator nghiệp vụ vẫn cần kiểm tra database, API phụ thuộc và điều kiện phục vụ thực tế.

## 8. Đăng ký service chỉ khi instance sẵn sàng

Một thiết kế đơn giản là chỉ tạo ephemeral registration sau khi ứng dụng đã khởi tạo và vượt qua readiness check ban đầu.

Luồng khởi động:

1. JVM và HTTP server khởi động.
2. Ứng dụng khởi tạo cấu hình và dependency.
3. Health check nghiệp vụ xác nhận các dependency bắt buộc hoạt động.
4. Ứng dụng kết nối ZooKeeper và tạo ephemeral registration.
5. Consumer nhìn thấy instance và có thể gửi request.

Nếu health chuyển DOWN trong khi session vẫn CONNECTED, cần có cơ chế cập nhật trạng thái discovery. Một số lựa chọn:

- Gỡ ephemeral registration khi instance không còn phục vụ và tạo lại khi readiness UP.
- Dùng một node trạng thái riêng hoặc metadata được cập nhật, sau đó yêu cầu consumer lọc instance theo trạng thái.
- Dùng health check độc lập ở tầng load balancer/service mesh để loại instance khỏi traffic.
- Giữ registration nhưng để consumer kiểm tra readiness endpoint trước khi gửi request, nếu kiến trúc hỗ trợ.

Không nên chỉ đổi dữ liệu trong znode mà giả định mọi consumer sẽ tự lọc theo nội dung đó. Consumer phải thực sự đọc, theo dõi và áp dụng quy tắc lọc. Nếu dùng Curator Service Discovery hoặc Spring Cloud Zookeeper, hãy kiểm tra cách thư viện đăng ký, cập nhật và deregister service trước khi thêm cơ chế thủ công.

Trong Spring Cloud Zookeeper, DiscoveryClient cung cấp danh sách instance cho consumer, còn ServiceRegistry là abstraction cho đăng ký và hủy đăng ký service. Hai API này quản lý thông tin discovery; chúng không tự kiểm tra database hoặc sức khỏe nghiệp vụ. Nếu bật auto-registration, cần xác định thời điểm thư viện đăng ký trong vòng đời ứng dụng và cách tích hợp readiness. Tránh vừa để auto-registration tạo node vừa tạo một registration thủ công thứ hai cho cùng instance.

Khi gỡ ephemeral node, thao tác phải được thực hiện bởi client/session có quyền phù hợp. Nếu session đã LOST, node cũ thường đã bị ZooKeeper xóa; client mới chỉ cần đăng ký lại sau khi ứng dụng sẵn sàng.

## 9. Watcher và health check là hai cơ chế khác nhau

ZooKeeper watcher thông báo cho client rằng một phần dữ liệu đã thay đổi. Watcher không phải health check và không chủ động gọi endpoint HTTP của ứng dụng.

Một watcher có thể báo rằng:

- Một instance node được tạo.
- Một instance node bị xóa.
- Dữ liệu của một node thay đổi.
- Children của một path thay đổi.

Watcher giúp consumer cập nhật danh sách instance. Health check nghiệp vụ lại đánh giá ứng dụng có thể phục vụ request hay không.

Với watcher truyền thống, một số loại watcher chỉ được kích hoạt một lần cho thay đổi tiếp theo; client cần đăng ký lại watcher sau khi xử lý event. Các recipe hoặc cache của Curator có thể quản lý việc này. Dù dùng watcher hay cache, consumer vẫn cần xử lý mất kết nối, dữ liệu cũ và session expiration.

Không suy luận rằng watcher không báo lỗi nghĩa là instance đang khỏe. Watcher không kiểm tra database, không gọi API nghiệp vụ và không đo khả năng xử lý request.

## 10. Ma trận sự cố và cách xử lý

| Tình huống | Điều đang xảy ra | Hành động kiểm tra/xử lý |
|---|---|---|
| ZooKeeper CONNECTED, business health DOWN | Session còn sống nên ephemeral node có thể vẫn tồn tại | Kiểm tra dependency; đánh dấu readiness DOWN và gỡ/loại registration theo chính sách |
| ZooKeeper SUSPENDED, business health UP | Mất kết nối tạm thời; session có thể chưa hết hạn | Theo dõi session timeout, không kết luận node đã bị xóa; áp dụng chính sách readiness phù hợp |
| ZooKeeper LOST, business health UP | Session cũ hết hạn, ephemeral node bị xóa | Tạo session mới, xác minh dependency rồi đăng ký lại |
| ZooKeeper RECONNECTED, node không tồn tại | Ứng dụng đã có kết nối mới nhưng registration chưa được khôi phục | Chạy quy trình ensureRegistered và xác minh node trong registry |
| ZooKeeper CONNECTED, consumer thấy node nhưng HTTP timeout | Registration còn đó nhưng địa chỉ, port hoặc ứng dụng có vấn đề | Kiểm tra service address, network và readiness endpoint |
| ZooKeeper READ_ONLY, business health UP | Có thể đọc registry nhưng không ghi được node | Không coi provider đã đăng ký thành công; chờ writable connection |
| Session vẫn sống, watcher không cập nhật | Watcher chưa được đăng ký lại hoặc consumer cache lỗi thời | Kiểm tra watcher lifecycle, cache và event log |
| Server trả lời probe đơn giản nhưng client không có quorum ổn định | Một node ZooKeeper phản hồi không chứng minh ensemble sẵn sàng | Kiểm tra quorum, leader/follower, latency và client session |

Khi ứng dụng khỏe nhưng discovery mất kết nối, có thể cần tiếp tục phục vụ request hiện tại. Khi ứng dụng không khỏe nhưng session còn sống, phải ngăn instance nhận thêm traffic. Đây là lý do readiness nên được tính từ các điều kiện phục vụ, còn connection state được theo dõi riêng.

## 11. Kiểm tra ZooKeeper server và client session

Không nhầm sức khỏe của ZooKeeper server với trạng thái session của ứng dụng.

- Server process có thể đang chạy nhưng ensemble không có quorum để chấp nhận thao tác ghi.
- Một client có thể còn giữ session trong lúc chuyển kết nối giữa các server.
- Một client có thể bị session expiration dù một server vẫn phản hồi probe đơn giản.
- Một server trả lời lệnh kiểm tra cơ bản không chứng minh mọi thao tác ghi ephemeral node sẽ thành công.

Lệnh bốn chữ cái như ruok thường chỉ xác nhận tiến trình server phản hồi với probe tương ứng. Muốn đánh giá ensemble, cần kiểm tra trạng thái quorum, vai trò leader/follower, số node đang tham gia, latency và lỗi client. Các lệnh quản trị chỉ hoạt động khi được cho phép trong cấu hình của ZooKeeper; không mở rộng whitelist tùy tiện trong production.

Ở phía ứng dụng, nên quan sát:

- Connection state hiện tại và số lần SUSPENDED/LOST.
- Số session expiration và thời gian phục hồi registration.
- Số ephemeral registration dự kiến so với số node thực tế.
- Tuổi dữ liệu discovery trong cache consumer.
- Readiness, liveness và business dependency health.
- Request lỗi do không tìm thấy instance hoặc gọi vào instance không sẵn sàng.

Không chỉ theo dõi số lượng node trong ZooKeeper. Một node có thể tồn tại nhưng chứa địa chỉ cũ, port sai hoặc instance không còn khỏe.

## 12. Bảo mật và độ tin cậy

Registration trong ZooKeeper ảnh hưởng trực tiếp đến việc consumer định tuyến request. Một client không được phép ghi node vào path của dịch vụ khác có thể làm sai lệch discovery hoặc giả mạo instance.

Cần áp dụng:

- Dùng ACL để giới hạn quyền đọc, tạo, sửa và xóa znode theo service/path.
- Dùng xác thực client và TLS theo yêu cầu bảo mật của ensemble.
- Không lưu token, password hoặc dữ liệu cá nhân trong znode metadata.
- Không cấp quyền xóa toàn bộ cây service cho mọi client.
- Kiểm tra owner/session của ephemeral node khi điều tra registration cũ.
- Đặt timeout cho health check nghiệp vụ và các thao tác dependency.
- Có retry với backoff và giới hạn; không tạo vòng lặp đăng ký liên tục khi ZooKeeper mất kết nối.
- Bảo đảm quy trình phục hồi registration có tính idempotent và không tạo node trùng.
- Giám sát readiness và discovery connectivity riêng để phân biệt nguyên nhân sự cố.

Nếu một instance bị mất session, không được tiếp tục giả định nó còn giữ distributed lock hoặc quyền lãnh đạo. Với nghiệp vụ cần quyền sở hữu duy nhất, cần dùng fencing token hoặc cơ chế bảo vệ tương đương để ngăn tiến trình cũ tiếp tục ghi sau khi quyền đã được chuyển sang tiến trình khác.

## 13. Quy trình thực hành

Có thể thực hành với inventory-service theo các bước:

1. Khởi động ZooKeeper ensemble và xác nhận có quorum.
2. Khởi động hai instance inventory-service; mỗi instance tạo ephemeral node với ID riêng.
3. Kiểm tra các node instance trong cây /services/inventory-service/instances.
4. Gọi endpoint health nghiệp vụ và xác nhận readiness UP.
5. Làm database test hoặc dependency bắt buộc ngừng hoạt động trong môi trường lab; quan sát business health chuyển DOWN trong khi session ZooKeeper có thể vẫn CONNECTED.
6. Khôi phục dependency; xác nhận readiness UP và registration được đưa trở lại nếu đã gỡ.
7. Tạm ngắt mạng giữa một client và ZooKeeper; quan sát SUSPENDED và thời gian chờ session timeout.
8. Để session hết hạn; xác nhận ephemeral node cũ bị xóa.
9. Khôi phục mạng; quan sát LOST rồi RECONNECTED theo client library và xác nhận ứng dụng tạo registration mới.
10. Gửi request qua consumer; kiểm tra consumer không tiếp tục gọi instance đã bị loại khỏi danh sách sẵn sàng.

Không thử nghiệm làm mất quorum trên môi trường production. Các thao tác ngắt mạng hoặc dừng server chỉ thực hiện trong môi trường lab được kiểm soát.

## 14. Checklist thiết kế

Trước khi triển khai service discovery với ZooKeeper, xác nhận:

1. Ứng dụng phân biệt connection state, session state và business health.
2. Ephemeral node đại diện registration có owner/session và instance ID rõ ràng.
3. Readiness phản ánh dependency cần thiết cho request nghiệp vụ.
4. Khi business health DOWN, instance được loại khỏi traffic theo chính sách cụ thể.
5. Khi session LOST, registration cũ được coi là đã mất và được tạo lại sau khi kết nối phục hồi.
6. Khi SUSPENDED, hệ thống không vội kết luận session đã hết hạn.
7. Consumer xử lý watcher/cache lỗi thời và không dùng địa chỉ cũ vô thời hạn.
8. Liveness không bị kéo xuống chỉ vì dependency từ xa tạm thời mất kết nối.
9. Distributed lock hoặc leader ownership có fencing/kiểm tra quyền trước khi ghi.
10. ACL, xác thực, TLS, timeout, retry và metrics được cấu hình phù hợp.

Điểm cốt lõi là: **ZooKeeper connection state cho biết client có thể giao tiếp với ensemble và giữ session hay không; business health cho biết ứng dụng có xử lý được nghiệp vụ hay không; ephemeral znode biểu diễn registration gắn với session chứ không phải lời cam kết rằng service đang khỏe.** Hãy kết hợp các tín hiệu này để điều khiển readiness và định tuyến an toàn.

