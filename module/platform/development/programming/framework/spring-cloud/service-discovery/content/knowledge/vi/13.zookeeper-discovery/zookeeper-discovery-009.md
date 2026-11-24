# Phân biệt mất kết nối tạm thời và hết hạn phiên

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt mất kết nối mạng tạm thời với việc ZooKeeper session thực sự hết hạn.
- Giải thích vai trò của heartbeat, session timeout và ephemeral znode trong đăng ký dịch vụ.
- Đọc và xử lý các trạng thái CONNECTED, SUSPENDED, RECONNECTED và LOST của Apache Curator.
- Hiểu ảnh hưởng của từng trạng thái đến service registration, watch, cache và service discovery.
- Thiết kế quy trình phục hồi an toàn khi ứng dụng kết nối lại hoặc phải tạo session mới.

## 1. Vì sao cần phân biệt hai tình huống?

Trong Spring Cloud Service Discovery, ứng dụng có thể đăng ký thông tin instance như tên dịch vụ, instance ID, host và port vào ZooKeeper. Spring Cloud Zookeeper sử dụng Apache Curator để thực hiện đăng ký và khám phá dịch vụ. Vì vậy, trạng thái kết nối ZooKeeper ảnh hưởng trực tiếp đến việc instance còn xuất hiện trong registry hay không.

Một ứng dụng mất kết nối đến ZooKeeper chưa chắc đã mất session. Nếu mạng được khôi phục trước khi session timeout, client có thể kết nối lại bằng session ID cũ. Những ephemeral znode thuộc session đó vẫn còn tồn tại.

Ngược lại, nếu ZooKeeper ensemble không nhận được heartbeat trong thời gian session timeout, server sẽ hết hạn session. Các ephemeral znode do session tạo ra sẽ bị xóa. Khi client kết nối lại, nó phải tạo session mới và đăng ký lại dữ liệu cần thiết.

Hai tình huống có thể xảy ra dù tiến trình ứng dụng vẫn đang chạy. Ví dụ, network partition, firewall, GC pause dài hoặc máy ảo bị suspend có thể làm client không gửi heartbeat đúng hạn. Vì thế, không thể chỉ dựa vào việc process còn sống để kết luận service registration còn hợp lệ.

## 2. ZooKeeper session và heartbeat

Khi ứng dụng tạo kết nối đến ZooKeeper, client library thiết lập một session. ZooKeeper gán cho session một session ID và thông tin xác thực tương ứng. Client duy trì session bằng các request và heartbeat định kỳ.

Session timeout là khoảng thời gian mà ZooKeeper dùng để xác định một session không còn hoạt động nếu server không nhận được heartbeat. Thời gian timeout được thương lượng giữa client và server: client gửi giá trị yêu cầu, server trả về giá trị được chấp nhận. Theo tài liệu ZooKeeper hiện hành, timeout được thương lượng có giới hạn tối thiểu bằng 2 lần tickTime và tối đa bằng 20 lần tickTime của server.

Khi client tạm thời mất đường truyền, thư viện ZooKeeper sẽ thử kết nối lại tới các server trong connection string. Nếu kết nối lại thành công trong thời hạn session, client có thể tiếp tục dùng session cũ. Nếu session đã hết hạn ở phía server, client không thể hồi sinh session đó bằng cách chỉ mở lại TCP connection.

Một số khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| TCP connection | Đường truyền mạng giữa client và một ZooKeeper server cụ thể. Có thể bị đóng hoặc mất mà session vẫn còn hiệu lực. |
| ZooKeeper session | Trạng thái logic được ensemble quản lý, có session ID và timeout. Có thể tồn tại qua việc client chuyển sang server khác. |
| Heartbeat | Tín hiệu giúp server biết client còn duy trì session. |
| Session timeout | Giới hạn thời gian server chờ heartbeat trước khi hết hạn session. |
| Ephemeral znode | Znode gắn với session tạo ra nó; ZooKeeper xóa node khi session kết thúc hoặc hết hạn. |
| Watch | Cơ chế thông báo thay đổi znode; không phải một kết nối độc lập và cần được khôi phục/đồng bộ theo vòng đời session. |

### Session timeout khác connection timeout

Spring Cloud Zookeeper có hai cấu hình riêng:

~~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      connection-timeout: 10000
      session-timeout: 30000
~~~~

- `spring.cloud.zookeeper.connection-timeout` là thời gian chờ thiết lập kết nối, tính bằng millisecond.
- `spring.cloud.zookeeper.session-timeout` là session timeout được cấu hình/thương lượng, tính bằng millisecond.

Các giá trị trong ví dụ chỉ để minh họa. Server có thể thương lượng một session timeout khác theo tickTime và giới hạn của ensemble. Hãy kiểm tra giá trị thực tế mà client nhận được, không giả định rằng giá trị yêu cầu luôn được chấp nhận nguyên vẹn.

Các thuộc tính retry như `spring.cloud.zookeeper.max-retries`, `spring.cloud.zookeeper.base-sleep-time-ms` và `spring.cloud.zookeeper.max-sleep-ms` điều khiển số lần và khoảng chờ retry cho những thao tác được cấu hình retry. Chúng không thay thế session timeout và không thể làm session cũ sống lại sau khi server đã hết hạn.

## 3. Điều gì xảy ra khi kết nối bị gián đoạn?

Giả sử service inventory-service đã đăng ký instance vào ZooKeeper bằng một ephemeral znode.

1. Ứng dụng kết nối thành công và tạo session.
2. Curator đăng ký instance; ZooKeeper lưu znode gắn với session.
3. Mạng giữa ứng dụng và ZooKeeper bị gián đoạn. Client không gửi được heartbeat.
4. Curator thông báo trạng thái mất kết nối là SUSPENDED.
5. ZooKeeper tiếp tục theo dõi session ở phía server. Trong khoảng timeout, ephemeral znode chưa nhất thiết bị xóa.
6. Nếu client kết nối lại kịp thời, session cũ tiếp tục hoạt động và Curator phát RECONNECTED.
7. Nếu server đã hết hạn session, ephemeral znode bị xóa. Khi kết nối được khôi phục, client nhận biết session đã mất và cần tạo session mới, đăng ký lại instance.

Sơ đồ vòng đời:

~~~~mermaid
sequenceDiagram
    participant App as Spring Boot service
    participant Curator
    participant ZK as ZooKeeper ensemble
    participant Consumer as Service consumer

    App->>Curator: Khởi tạo client
    Curator->>ZK: Tạo session và heartbeat
    Curator->>ZK: Đăng ký ephemeral znode
    ZK-->>Consumer: Instance xuất hiện trong registry

    Note over App,ZK: Network partition
    ZK--xCurator: Mất kết nối
    Curator-->>App: SUSPENDED

    alt Kết nối lại trước khi session hết hạn
        Curator->>ZK: Reconnect bằng session ID cũ
        ZK-->>Curator: Session còn hiệu lực
        Curator-->>App: RECONNECTED
        Note over ZK: Ephemeral znode vẫn thuộc session cũ
    else Session đã hết hạn
        ZK->>ZK: Xóa ephemeral znode
        ZK-->>Consumer: Watch báo instance bị xóa
        Curator->>ZK: Kết nối lại và phát hiện session expired
        Curator-->>App: LOST
        App->>Curator: Tạo session mới và đăng ký lại
        Curator->>ZK: Tạo ephemeral znode mới
        ZK-->>Consumer: Instance được công bố lại
    end
~~~~

Điểm quan trọng là thời điểm server xóa ephemeral znode và thời điểm client nhận được thông báo hết hạn có thể khác nhau. Khi client đang mất kết nối, nó không thể nhận ngay thông báo từ server. Các consumer đã kết nối vẫn có thể nhận được sự kiện xóa znode khi session hết hạn, trong khi chính client bị hết hạn chỉ biết điều đó sau khi kết nối lại.

## 4. Ephemeral znode ảnh hưởng thế nào đến service discovery?

Curator Service Discovery lưu ServiceInstance dưới một cây znode theo base path và tên dịch vụ. Một instance chứa thông tin như service name, instance ID, address, port và payload metadata. Spring Cloud Zookeeper dùng Curator Service Discovery extension cho quá trình đăng ký và khám phá.

Ephemeral znode phù hợp với dữ liệu đăng ký của một instance đang chạy vì vòng đời node gắn với session tạo nó:

- Session còn hiệu lực: znode vẫn tồn tại, kể cả khi TCP connection tạm thời bị mất.
- Session hết hạn: ZooKeeper xóa các ephemeral znode thuộc session.
- Ứng dụng đóng bình thường: Spring Cloud ServiceRegistry có thể deregister instance trong quá trình shutdown; nếu không thể deregister vì lỗi mạng, session expiration vẫn là cơ chế dọn dẹp cuối cùng cho ephemeral node.

Khi session bị mất, consumer có thể thấy instance biến mất khỏi danh sách dịch vụ. Khi provider đăng ký lại bằng session mới, instance có thể xuất hiện trở lại. Khoảng thời gian biến mất và xuất hiện phụ thuộc session timeout, quá trình phát hiện trạng thái, retry và thời gian đăng ký lại.

Không nên coi việc instance còn trong registry trong lúc SUSPENDED là bằng chứng rằng instance đang phục vụ request khỏe mạnh. Registry chỉ phản ánh trạng thái đăng ký tại thời điểm consumer quan sát được. Network partition có thể khiến provider không truy cập được ZooKeeper trong khi consumer vẫn nhìn thấy thông tin cũ.

## 5. Các trạng thái kết nối của Curator

Curator cung cấp ConnectionStateListener để ứng dụng theo dõi trạng thái kết nối. Những trạng thái quan trọng gồm:

| Trạng thái | Ý nghĩa | Cách hiểu khi vận hành |
| --- | --- | --- |
| CONNECTED | Kết nối thành công lần đầu với ZooKeeper. | Client đã có session và bắt đầu thao tác bình thường. |
| SUSPENDED | Curator phát hiện kết nối bị gián đoạn. | Chưa thể kết luận session đã hết hạn; nhưng không nên tin rằng lock, leadership hoặc quyền điều phối vẫn an toàn. |
| RECONNECTED | Kết nối được thiết lập lại sau SUSPENDED hoặc LOST. | Kiểm tra lại dữ liệu discovery, watch, cache và các tài nguyên phụ thuộc session. |
| LOST | Curator tin rằng session đã hết hạn hoặc session nội bộ đã bị đóng. | Xem session cũ là không còn hợp lệ; tạo session mới và phục hồi registration/coordination state. |
| READ_ONLY | Client chuyển sang chế độ chỉ đọc nếu được cấu hình cho phép. | Không thực hiện các thao tác cần ghi hoặc đăng ký trong trạng thái chỉ đọc. |

### SUSPENDED không đồng nghĩa LOST

SUSPENDED là tín hiệu mất kết nối. Nó xuất hiện trước khi có thể xác định session đã hết hạn hay chưa. Nếu mạng khôi phục trong thời gian session còn hiệu lực, Curator có thể chuyển sang RECONNECTED mà không cần tạo session mới.

Tuy nhiên, Curator khuyến nghị xử lý SUSPENDED như một tình trạng mất kết nối hoàn toàn đối với các tác vụ cần tính đúng đắn phân tán. Ví dụ, một tiến trình đang giữ distributed lock không thể chắc chắn rằng nó vẫn có quyền giữ lock trong lúc mất kết nối. Tiến trình nên ngừng hành động phụ thuộc lock cho đến khi kết nối được xác minh lại.

### LOST có ý nghĩa khác nhau theo phiên bản Curator

Cần kiểm tra phiên bản Curator mà Spring Cloud release train đang quản lý:

- Trước Curator 3.0.0, LOST có thể chỉ có nghĩa retry policy đã hết số lần thử. Nó không nhất thiết chứng minh ZooKeeper server đã hết hạn session.
- Từ Curator 3.x, Curator mô phỏng session expiration ở phía client bằng timer bắt đầu khi nhận SUSPENDED. Timer mặc định dùng toàn bộ negotiated session timeout; nếu timer hết trước khi kết nối được khôi phục, Curator chuyển sang LOST.
- Curator có thể phát RECONNECTED sau LOST trong một số luồng phục hồi. Dù kết nối đã hoạt động trở lại, ứng dụng vẫn phải xem lock, leader state và tài nguyên gắn với session cũ là không còn đáng tin.

LOST của Curator là tín hiệu quản lý vòng đời session của thư viện. Nó không phải đồng hồ đo chính xác thời điểm ZooKeeper server xóa ephemeral node. Curator Tech Note 14 giải thích rằng server có thể đóng kết nối khi đã tiêu thụ khoảng 2/3 session timeout tính từ heartbeat cuối; nhưng Curator chỉ bắt đầu timer mô phỏng khi nhận SUSPENDED. Ngoài ra, kết nối cũng có thể mất do server crash hoặc lỗi TCP. Client không luôn biết chính xác nguyên nhân khi connection bị đóng, nên timer phía client không thể tái tạo chính xác đồng hồ session ở server.

Error policy mặc định của Curator xử lý SUSPENDED và LOST đều như trạng thái lỗi đối với các recipe, nhằm ưu tiên an toàn. Curator có SessionConnectionStateErrorPolicy nếu ứng dụng muốn chỉ coi LOST là lỗi session thực sự. Chỉ thay đổi policy này khi đã hiểu rủi ro của việc tiếp tục dựa vào trạng thái cũ trong thời gian SUSPENDED.

## 6. Watch và cache khi reconnect

ZooKeeper watch thông thường là one-shot: sau khi một thay đổi kích hoạt watch, client phải đăng ký lại nếu muốn nhận sự kiện tiếp theo. Java client tự động đăng ký lại các watch hiện có khi reconnect theo mặc định. Tuy nhiên, trong thời gian disconnect, client không nhận được watch event.

Có một trường hợp có thể bỏ lỡ thay đổi: watch được đặt để theo dõi sự tồn tại của một znode chưa được tạo; trong lúc client disconnected, znode được tạo rồi xóa trước khi client kết nối lại. Client có thể không nhận được sự kiện trung gian đó.

Curator ServiceCache duy trì danh sách instance trong bộ nhớ và cập nhật qua watch. Danh sách cache chỉ là trạng thái gần nhất mà client biết, không phải cam kết luôn mới tức thời. Sau reconnect, cần chờ cache đồng bộ lại và xử lý các sự kiện thay đổi được phát ra.

Nguyên tắc vận hành:

- Khi SUSPENDED, đánh dấu dữ liệu discovery/cache là có thể đã cũ.
- Khi RECONNECTED, chờ quá trình watch/cache đồng bộ và đọc lại trạng thái cần thiết.
- Không dựa vào một event đơn lẻ để suy ra toàn bộ thay đổi xảy ra trong thời gian mất kết nối.
- Khi LOST, tạo lại session và xác minh registration, watch, cache cùng các recipe đã khởi tạo.
- Nếu ứng dụng dùng watch trực tiếp, đăng ký lại watch theo đúng API và phiên bản ZooKeeper đang sử dụng.

## 7. Cấu hình Spring Cloud Zookeeper

Spring Cloud Zookeeper kích hoạt discovery qua dependency:

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~~

Ứng dụng cần kết nối tới ZooKeeper ensemble và có thể đăng ký instance theo cấu hình:

~~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      connection-timeout: 10000
      session-timeout: 30000
      discovery:
        enabled: true
        register: true
        root: /services
~~~~

Trong cấu hình trên:

- connect-string liệt kê các server mà client có thể thử kết nối.
- connection-timeout giới hạn thời gian thiết lập kết nối.
- session-timeout là thời gian session được cấu hình/thương lượng, tính bằng millisecond.
- discovery.register bật đăng ký service; giá trị mặc định trong tài liệu Spring Cloud Zookeeper hiện hành là true.
- discovery.root là thư mục gốc lưu đăng ký; giá trị mặc định là /services.

Giá trị session-timeout trong ví dụ chỉ mang tính minh họa. ZooKeeper server có thể điều chỉnh theo tickTime. Đừng hạ session timeout quá thấp chỉ để registry xóa instance nhanh hơn: GC pause, tải cao hoặc network jitter có thể làm session hết hạn ngoài ý muốn.

Spring Cloud Zookeeper sử dụng Curator cho service registration và discovery. Tùy phiên bản Spring Cloud và Curator, cách quản lý connection state, cache và đăng ký lại có thể khác nhau. Hãy kiểm tra dependency tree để biết Curator version thực tế trước khi áp dụng listener hoặc policy cụ thể.

## 8. Theo dõi trạng thái bằng ConnectionStateListener

Có thể gắn listener vào CuratorFramework để ghi log và kích hoạt hành động phù hợp với từng trạng thái:

~~~~java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.framework.state.ConnectionStateListener;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class ZooKeeperConnectionMonitor {

    private static final Logger log =
            LoggerFactory.getLogger(ZooKeeperConnectionMonitor.class);

    private final CuratorFramework curator;

    private final ConnectionStateListener listener = (client, state) -> {
        if (state == ConnectionState.CONNECTED) {
            log.info("Connected to ZooKeeper");
        } else if (state == ConnectionState.SUSPENDED) {
            log.warn("ZooKeeper connection suspended; enter safe mode");
            // Tạm dừng tác vụ cần lock hoặc coordination guarantee.
        } else if (state == ConnectionState.RECONNECTED) {
            log.info("ZooKeeper connection re-established; verify state");
            // Đồng bộ lại cache và kiểm tra registration.
        } else if (state == ConnectionState.LOST) {
            log.error("ZooKeeper session lost; rebuild session-bound state");
            // Tạo lại tài nguyên gắn với session theo lifecycle của ứng dụng.
        }
    };

    public ZooKeeperConnectionMonitor(CuratorFramework curator) {
        this.curator = curator;
    }

    public void start() {
        curator.getConnectionStateListenable().addListener(listener);
    }

    public void stop() {
        curator.getConnectionStateListenable().removeListener(listener);
    }
}
~~~~

Ví dụ chỉ minh họa cách nhận sự kiện. Trong ứng dụng thật, hãy gắn listener theo lifecycle bean, bảo đảm chỉ đăng ký một lần và gỡ listener khi bean bị hủy. Các hành động safe mode, đồng bộ cache hoặc đăng ký lại cần được triển khai theo service registry và Curator recipe mà ứng dụng đang dùng; tránh tự tạo một session thứ hai song song với client được Spring quản lý.

Không thực hiện công việc dài, gọi mạng đồng bộ hoặc chờ retry lâu ngay bên trong callback của listener. Hãy chuyển tác vụ phục hồi sang executor phù hợp và bảo đảm việc xử lý sự kiện có thể lặp lại an toàn.

## 9. Quy trình phục hồi an toàn

### Trường hợp A: SUSPENDED rồi RECONNECTED

Khi client mất kết nối nhưng phục hồi trước khi session hết hạn:

1. Đánh dấu discovery state là degraded hoặc uncertain.
2. Tạm dừng thao tác yêu cầu lock, leadership hoặc quyền sở hữu session.
3. Đợi Curator phát RECONNECTED.
4. Đồng bộ lại ServiceCache hoặc đọc lại các znode cần thiết.
5. Xác minh instance registration vẫn tồn tại và metadata còn đúng.
6. Chỉ mở lại tác vụ phụ thuộc ZooKeeper sau khi trạng thái cần thiết đã được xác minh.

Session cũ có thể vẫn còn hiệu lực nên ephemeral znode không bị xóa. Không tạo session mới chỉ vì nhận được SUSPENDED.

### Trường hợp B: LOST rồi RECONNECTED

Khi Curator báo LOST:

1. Đánh dấu mọi trạng thái gắn với session cũ là không còn hợp lệ.
2. Không tiếp tục dùng lock, leader token, ephemeral node hoặc giả định ownership cũ.
3. Cho Curator/ZooKeeper client quản lý việc tạo session mới theo lifecycle của client.
4. Khởi tạo lại registration bằng service discovery component được quản lý bởi Spring.
5. Đăng ký lại watch và đồng bộ cache.
6. Lấy lại distributed lock hoặc tham gia leader election như một thành viên mới.
7. Chỉ tiếp tục nghiệp vụ sau khi xác minh instance đã được công bố và các quyền điều phối đã được cấp lại.

Trong Spring Cloud, không nên gọi ServiceRegistry.register() một cách tùy tiện trong mọi callback RECONNECTED nếu auto-registration hoặc Curator ServiceDiscovery đã quản lý việc đăng ký lại. Việc đăng ký hai lần có thể gây trùng instance hoặc lỗi node đã tồn tại. Trước tiên hãy kiểm tra hành vi của phiên bản Curator/Spring Cloud đang dùng, sau đó chọn đúng một nơi chịu trách nhiệm phục hồi registration.

## 10. Xử lý thao tác có kết quả chưa xác định

Một lỗi kết nối có thể xảy ra sau khi server đã thực hiện thao tác nhưng trước khi client nhận được response. Ví dụ, client gửi lệnh tạo znode, ZooKeeper ghi thành công, nhưng gói phản hồi bị mất. Client nhìn thấy connection loss và không biết chắc thao tác đã thành công hay chưa.

Không nên retry mù quáng một thao tác tạo node với tên cố định vì có thể nhận NODEEXISTS. Với thao tác đăng ký, nên:

- Dùng instance ID ổn định trong phạm vi vòng đời đăng ký.
- Đọc lại node hoặc trạng thái registration trước khi quyết định tạo lại.
- Xử lý NODEEXISTS và NONODE theo ngữ cảnh, không xem mọi lỗi là lỗi fatal.
- Dùng operation có tính idempotent hoặc kiểm tra ownership/session trước khi retry.
- Không tái sử dụng session ID đã hết hạn.
- Đảm bảo một instance cũ không thể ghi đè registration của instance mới chỉ vì hai tiến trình dùng trùng ID.

Curator có retry policy cho nhiều thao tác và recipe, nhưng retry không thay thế thiết kế idempotent của ứng dụng. Hãy xác định rõ thao tác nào được Curator tự retry và thao tác nào cần logic nghiệp vụ kiểm tra kết quả.

## 11. Tình huống gây session expiration ngoài ý muốn

| Nguyên nhân | Cơ chế tác động | Cách giảm rủi ro |
| --- | --- | --- |
| Network partition kéo dài | Client không gửi heartbeat đến ensemble trong thời hạn session. | Dùng connection string có đủ peer, kiểm tra network path và firewall. |
| JVM stop-the-world GC quá lâu | Thread heartbeat không chạy kịp trong khoảng timeout. | Theo dõi GC pause, heap pressure và đặt session timeout phù hợp. |
| CPU starvation hoặc thread scheduling chậm | I/O thread của ZooKeeper/Curator không được chạy đúng hạn. | Theo dõi CPU throttling và tránh chặn thread callback. |
| ZooKeeper ensemble quá tải | Heartbeat và request bị xử lý trễ, client có thể mất kết nối. | Theo dõi latency, outstanding requests và tải server. |
| DNS hoặc routing lỗi | Client không thể chuyển sang peer khác hoặc kết nối lại. | Dùng DNS ổn định, kiểm tra connection string và route giữa các zone. |
| Session timeout quá ngắn | Các gián đoạn ngắn cũng có thể vượt ngưỡng. | Chọn timeout dựa trên GC, mạng, tickTime và yêu cầu phát hiện instance. |
| Client bị đóng hoặc process restart | Session kết thúc; ephemeral nodes bị xóa. | Thực hiện graceful shutdown và xác minh đăng ký mới sau startup. |

Session timeout quá dài làm thời gian phát hiện instance mất khả năng kết nối tăng lên. Session timeout quá ngắn làm instance khỏe mạnh có thể bị xóa khỏi registry khi gặp pause hoặc mạng chập chờn. Cần cân bằng giữa thời gian phát hiện lỗi và độ ổn định của hệ thống.

## 12. Kiểm thử hai tình huống

Một bài kiểm thử nên chứng minh rằng ứng dụng xử lý đúng cả reconnect cùng session và session expiration.

| Kịch bản | Cách tạo tình huống | Kết quả cần quan sát |
| --- | --- | --- |
| Mất kết nối ngắn | Chặn tạm thời đường mạng từ client đến ZooKeeper rồi mở lại trước session timeout. | Curator phát SUSPENDED rồi RECONNECTED; registration ephemeral vẫn tồn tại. |
| Mất kết nối dài | Chặn mạng lâu hơn session timeout đã thương lượng. | ZooKeeper xóa ephemeral znode; client nhận LOST khi kết nối lại và phải phục hồi registration. |
| JVM pause | Tạo pause có kiểm soát vượt session timeout trong môi trường thử nghiệm. | Quan sát SUSPENDED/LOST, znode bị xóa và quá trình đăng ký lại. |
| Một peer ngừng hoạt động | Tắt một ZooKeeper server nhưng giữ quorum và các peer khác hoạt động. | Client chuyển peer, có thể reconnect bằng cùng session nếu session còn hiệu lực. |
| Server ensemble mất quorum | Mô phỏng mất quorum trong môi trường thử nghiệm. | Client không thể thực hiện thao tác ghi bình thường; theo dõi thời gian phục hồi và session state. |

Khi kiểm tra registry, dùng ZooKeeper CLI hoặc công cụ giám sát để xem path dịch vụ và ephemeral node. Ghi lại session state, session ID, thời điểm SUSPENDED/LOST/RECONNECTED, thời điểm node biến mất và thời điểm node được tạo lại.

Không chỉ kiểm tra log của provider. Hãy kiểm tra từ góc nhìn consumer: instance có biến mất khỏi danh sách discovery không, cache cập nhật khi nào và request có bị gửi đến địa chỉ đã mất kết nối hay không.

## 13. Checklist vận hành

- [ ] Biết session timeout được thương lượng thực tế, không chỉ giá trị cấu hình yêu cầu.
- [ ] Phân biệt connection-timeout, session-timeout và retry policy.
- [ ] Theo dõi riêng SUSPENDED, LOST và RECONNECTED.
- [ ] Khi SUSPENDED, chuyển các tác vụ cần coordination guarantee sang safe mode.
- [ ] Khi LOST, bỏ trạng thái gắn với session cũ và tạo lại tài nguyên cần thiết.
- [ ] Xác minh ephemeral registration và instance metadata sau reconnect.
- [ ] Đồng bộ lại watch/cache; không chỉ dựa vào event trong thời gian disconnect.
- [ ] Không tạo session mới cho một lần mất TCP connection tạm thời.
- [ ] Không retry thao tác tạo node một cách mù quáng khi kết quả trước đó chưa xác định.
- [ ] Kiểm tra Curator version vì ý nghĩa LOST đã thay đổi từ Curator 3.0.0.
- [ ] Kiểm thử network partition, GC pause, peer failover và session expiration trong môi trường riêng.
- [ ] Theo dõi registry từ cả phía provider và consumer.

## Ghi nhớ

- Mất TCP connection không đồng nghĩa session đã hết hạn.
- Nếu reconnect trước session timeout, client có thể tiếp tục dùng session cũ và ephemeral znode vẫn còn.
- Khi session hết hạn, ZooKeeper xóa ephemeral znode do session sở hữu; client phải tạo session mới và phục hồi registration.
- Curator phát SUSPENDED khi mất kết nối; LOST thể hiện Curator tin rằng session đã hết hạn.
- Ý nghĩa LOST thay đổi từ Curator 3.0.0, vì vậy cần kiểm tra phiên bản dependency thực tế.
- RECONNECTED sau LOST không làm cho lock, leadership hoặc registration gắn với session cũ trở nên hợp lệ.
- Watch và cache cần được đồng bộ lại sau reconnect; registry view có thể cũ trong lúc mất kết nối.
- Session timeout, connection timeout và retry policy giải quyết các vấn đề khác nhau.

## Tài liệu tham khảo chính thức

- [Apache ZooKeeper – Programmer's Guide: ZooKeeper Sessions](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html#ch_zkSessions)
- [Apache ZooKeeper – Programmer's Guide: Ephemeral Nodes and Watches](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Apache Curator – Error Handling](https://curator.apache.org/docs/errors/)
- [Apache Curator – Tech Note 12: Connection Semantics](https://curator.apache.org/docs/tech-note-12/)
- [Apache Curator – Tech Note 14: Session Expiration](https://curator.apache.org/docs/tech-note-14/)
- [Apache Curator – Service Discovery](https://curator.apache.org/docs/service-discovery/)
- [Spring Cloud Zookeeper – Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper 4.3 – Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/4.3/appendix.html)
