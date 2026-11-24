# Zookeeper mất session, lỗi đường dẫn hoặc quyền truy cập

## 1. Phạm vi sự cố

Spring Cloud Zookeeper Discovery dùng Apache Curator để đăng ký và tìm service trong ZooKeeper. Khi tích hợp này gặp lỗi, triệu chứng thường rơi vào ba nhóm:

- **Session hoặc kết nối:** client liên tục reconnect, báo SUSPENDED, LOST, SessionExpired hoặc không thể duy trì ephemeral registration.
- **Đường dẫn znode:** gặp NoNode, NodeExists, sai chroot, sai discovery root hoặc ứng dụng nhìn nhầm namespace.
- **Xác thực và ACL:** gặp AuthFailed, NoAuth hoặc Insufficient permission khi đọc, tạo, cập nhật hay xóa znode.

Ba nhóm lỗi có thể xuất hiện cùng lúc. Ví dụ, ứng dụng reconnect sau khi session hết hạn, tạo lại registration nhưng bị NoAuth vì credential mới không có quyền CREATE trên parent path. Cần xác định lỗi đầu tiên trong chuỗi thay vì chỉ xử lý exception cuối cùng.

Bài này tập trung vào cách chẩn đoán Spring Cloud Zookeeper trong service discovery: kiểm tra session, xác minh path, đọc ACL, xác thực client và phục hồi registration.

## 2. Cấu trúc registration và các path cần biết

Spring Cloud Zookeeper Discovery dùng Curator Service Discovery để đăng ký thông tin instance như service name, instance ID, host, port và metadata. Discovery root mặc định thường là /services.

Mô hình path khái quát:

~~~text
/services
  /payment-service
    /payment-instance-a
    /payment-instance-b
  /inventory-service
    /inventory-instance-a
~~~

Đây là cấu trúc minh họa để giải thích namespace. Tên instance cụ thể phụ thuộc instance-id, provider và phiên bản. Mặc định spring.cloud.zookeeper.discovery.instance-id có thể được tạo tự động; nếu cần đối chiếu registration sau restart, hãy kiểm tra ID thực tế trong cấu hình và dữ liệu.

Các property thường cần kiểm tra:

~~~yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181
      session-timeout: 30000
      connection-timeout: 15000
      discovery:
        enabled: true
        register: true
        root: /services
        instance-id: payment-instance-a
~~~

Các giá trị timeout ở trên chỉ là ví dụ để minh họa property tính bằng mili giây; hãy dùng giá trị phù hợp với phiên bản, mạng, tickTime và thời gian pause của JVM. Không áp dụng một session timeout tùy tiện cho mọi cluster.

ZooKeeper đàm phán session timeout với server. Trong cấu hình phổ biến, server giới hạn timeout theo tickTime; giá trị ứng dụng yêu cầu không nhất thiết là giá trị cuối cùng được cấp. Khi điều tra session expiration, hãy ghi nhận negotiated timeout thực tế từ client log/metric thay vì chỉ đọc YAML.

| Property | Vai trò khi chẩn đoán |
|---|---|
| spring.cloud.zookeeper.connect-string | Danh sách endpoint ZooKeeper client, có thể kèm chroot suffix |
| spring.cloud.zookeeper.session-timeout | Session timeout được yêu cầu/đàm phán với ZooKeeper |
| spring.cloud.zookeeper.connection-timeout | Thời gian chờ kết nối |
| spring.cloud.zookeeper.max-retries | Số lần retry tối đa theo cấu hình Spring Cloud Zookeeper |
| spring.cloud.zookeeper.base-sleep-time-ms | Khoảng nghỉ ban đầu giữa các lần retry |
| spring.cloud.zookeeper.max-sleep-ms | Giới hạn thời gian nghỉ giữa retry |
| spring.cloud.zookeeper.discovery.root | Root path chứa các registration; mặc định phổ biến là /services |
| spring.cloud.zookeeper.discovery.register | Bật/tắt việc ứng dụng tự đăng ký |
| spring.cloud.zookeeper.discovery.instance-id | ID dùng để định danh registration |

Property có thể khác giữa release train. Hãy xem Common application properties đúng phiên bản Spring Cloud Zookeeper đang dùng trước khi kết luận property bị bỏ hoặc có default cụ thể.

## 3. Phân biệt mất kết nối và mất session

ZooKeeper client duy trì session với ensemble. Khi TCP connection bị đứt, client thường chuyển sang trạng thái disconnected và thử kết nối lại tới các server trong connect string. Nếu kết nối được khôi phục trước khi session timeout, session cũ có thể tiếp tục được sử dụng.

Nếu ensemble xác định session đã hết hạn, session đó không thể tiếp tục. ZooKeeper xóa các ephemeral znode thuộc session; client cần tạo session mới và những registration ephemeral phải được tạo lại theo lifecycle của ứng dụng/provider.

Điểm quan trọng:

- TCP disconnect không đồng nghĩa ephemeral znode bị xóa ngay.
- Session expiration do ZooKeeper ensemble quyết định, không chỉ do client thấy timeout cục bộ.
- Khi session hết hạn, ephemeral znode bị xóa ngay cả khi client chưa nhận được thông báo vì client vẫn đang mất kết nối.
- Sau khi reconnect, client có thể nhận thông báo session expired và phải xử lý như một session mới.
- Không tạo một ZooKeeper client/session mới chỉ vì vừa thấy disconnect; để Curator quản lý retry/reconnect và chỉ phục hồi registration khi session thực sự LOST/expired.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot / Curator
    participant ZK as ZooKeeper ensemble
    participant Watcher as Client khác đang watch
    App->>ZK: Tạo session và ephemeral registration
    ZK-->>App: CONNECTED
    Note over App,ZK: Mạng bị phân vùng
    App-xZK: Heartbeat / request
    App-->>App: SUSPENDED
    Note over ZK: Session còn hiệu lực trong timeout
    alt Kết nối lại trước khi session hết hạn
        App->>ZK: Reconnect với session cũ
        ZK-->>App: RECONNECTED
        Note over ZK: Ephemeral registration vẫn tồn tại
    else Session đã hết hạn
        ZK->>ZK: Expire session và xóa ephemeral znodes
        ZK-->>Watcher: Watch event: registration deleted
        App->>ZK: Reconnect
        ZK-->>App: LOST / session expired được báo
        App->>ZK: Tạo session mới và đăng ký lại
    end
~~~

## 4. Đọc trạng thái kết nối của Curator

Curator cung cấp ConnectionStateListener để theo dõi trạng thái kết nối. Các trạng thái phổ biến:

| Trạng thái | Ý nghĩa | Hành động an toàn |
|---|---|---|
| CONNECTED | Kết nối đầu tiên được thiết lập | Có thể bắt đầu thao tác sau khi ứng dụng sẵn sàng |
| SUSPENDED | Mất kết nối tạm thời | Tạm dừng thao tác phụ thuộc registry; không giả định lock/registration còn đáng tin cậy |
| RECONNECTED | Kết nối đã phục hồi sau gián đoạn | Kiểm tra lại dữ liệu/watch và trạng thái registration |
| LOST | Curator cho rằng session đã hết hạn | Xem session cũ không còn hợp lệ; tạo lại ephemeral registration và khôi phục watch cần thiết |
| READ_ONLY | Client đang ở chế độ chỉ đọc nếu cấu hình cho phép | Không thực hiện register, update hoặc deregister cần ghi |

Trong Curator, SUSPENDED nên được xem là mất kết nối hoàn toàn cho các quyết định an toàn như lock, leader hoặc registration cần bảo đảm tính duy nhất. RECONNECTED chỉ cho biết đường kết nối đã trở lại; nó không tự chứng minh mọi trạng thái ứng dụng đã đúng. LOST là tín hiệu cần phục hồi session và tài nguyên gắn với session.

Ví dụ listener dùng Curator:

~~~java
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.framework.state.ConnectionStateListener;

public class ZookeeperConnectionListener
        implements ConnectionStateListener {

    @Override
    public void stateChanged(
            CuratorFramework client,
            ConnectionState newState) {
        switch (newState) {
            case CONNECTED:
                // Kết nối ban đầu đã sẵn sàng.
                break;
            case SUSPENDED:
                // Tạm dừng các thao tác cần registry đáng tin cậy.
                break;
            case RECONNECTED:
                // Đối chiếu lại registration và dữ liệu cache.
                break;
            case LOST:
                // Session cũ đã mất; phục hồi ephemeral registration.
                break;
            case READ_ONLY:
                // Chỉ đọc; không coi thao tác ghi là thành công.
                break;
            default:
                break;
        }
    }
}
~~~

Tên enum và trạng thái được hỗ trợ phụ thuộc phiên bản Curator. Hãy dùng API của Curator đang được Spring Cloud Zookeeper quản lý, không thêm một phiên bản Curator không tương thích chỉ để lấy enum mới hơn.

## 5. Lỗi session thường gặp

| Lỗi hoặc dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| SUSPENDED lặp lại | Mạng chập chờn, firewall idle timeout, JVM pause hoặc ZooKeeper server quá tải | Kiểm tra latency, packet loss, GC pause, server log và đường TCP hai chiều |
| SessionExpiredException / SESSIONEXPIRED | Session timeout đã hết trước khi client reconnect | Xem session là mới; đăng ký lại ephemeral node và thiết lập lại watch |
| ConnectionLossException | Mất kết nối trong lúc thao tác | Kết quả thao tác có thể chưa rõ; đọc lại trạng thái trước khi retry create/delete |
| OperationTimeoutException | Retry policy hoặc thao tác vượt thời gian chờ | Kiểm tra timeout, retry budget, latency và quorum |
| Registration biến mất sau một khoảng mất mạng | Session hết hạn nên ephemeral node bị xóa | Xác nhận LOST, tạo session mới và re-register |
| Registration cũ vẫn tồn tại sau khi app đã dừng | Session chưa hết hạn, deregister không tới server hoặc node không phải ephemeral | Kiểm tra stat, owner/session, ACL và loại znode |
| Reconnect thành công nhưng discovery không thấy instance | Registration chưa được tạo lại, sai root/instance ID hoặc client cache chưa cập nhật | Kiểm tra znode trên server và cấu hình discovery |

### 5.1. Không retry create một cách mù quáng

ConnectionLoss có thể xảy ra sau khi server đã xử lý lệnh nhưng response chưa về client. Nếu ứng dụng retry create ngay, lần thứ hai có thể nhận NodeExists. Điều đó không nhất thiết là lỗi dữ liệu; có thể lần đầu đã thành công.

Với registration, hãy:

1. Xác định path và instance ID dự kiến.
2. Sau lỗi không rõ kết quả, đọc lại path nếu client có thể truy vấn.
3. Nếu node đã tồn tại, kiểm tra data, ephemeral owner và metadata để xác nhận nó thuộc registration mong đợi.
4. Chỉ tạo lại khi node không tồn tại hoặc session cũ đã hết hạn và lifecycle yêu cầu registration mới.
5. Không xóa node chỉ vì nhận NodeExists; node có thể thuộc một instance khác.

## 6. Chẩn đoán lỗi đường dẫn: NoNode, NodeExists và chroot

ZooKeeper dùng path tuyệt đối, phân tách bằng dấu /. Path phải bắt đầu bằng /; ZooKeeper không hỗ trợ path tương đối kiểu . hoặc ...

Các lỗi thường gặp:

| Lỗi | Ý nghĩa | Nguyên nhân phổ biến |
|---|---|---|
| NoNode | Một znode trong path không tồn tại | Parent path chưa được tạo, sai discovery root hoặc sai chroot |
| NodeExists | Path đã tồn tại | Retry create sau ConnectionLoss, instance ID trùng hoặc registration cũ chưa được dọn |
| BadVersion | Version znode không khớp khi cập nhật có điều kiện | Client ghi dựa trên dữ liệu cũ hoặc có writer khác |
| InvalidPath | Path không hợp lệ | Path tương đối, ký tự bị cấm hoặc sai định dạng |
| NotEmpty | Không thể xóa node còn child | Xóa parent trước khi xóa các child |

### 6.1. Kiểm tra discovery root

Spring Cloud Zookeeper Discovery mặc định dùng root /services trong cấu hình phổ biến. Có thể cấu hình root riêng:

~~~yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: /platform/services
~~~

Nếu một service đăng ký ở /platform/services nhưng client khác đọc /services, hai bên dùng hai namespace khác nhau và sẽ không nhìn thấy nhau dù cùng connect đến một ensemble.

Đảm bảo mọi service cần giao tiếp có cùng discovery root và cùng quy ước tên service ID. Kiểm tra cả profile, biến môi trường và config import vì cấu hình có thể bị override theo môi trường.

### 6.2. Chroot suffix trong connect string

Connect string có thể kèm chroot suffix:

~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zk1.internal:2181,zk2.internal:2181,zk3.internal:2181/platform
      discovery:
        root: /services
~~~

Với cấu hình này, client nhìn /platform trên server như root / riêng của nó. Khi ứng dụng truy cập /services, path thực trên ensemble là /platform/services.

Nếu chroot /platform chưa tồn tại, kết nối hoặc thao tác path có thể thất bại. Hãy tạo namespace này trước khi khởi động client. Nếu đã dùng chroot, không thêm /platform lần nữa vào discovery.root; nếu không, client có thể truy cập nhầm /platform/platform/services.

Chroot là namespace logic, không thay thế ACL. Quyền truy cập vẫn phải được cấu hình trên từng znode ở phía server.

### 6.3. Kiểm tra path bằng CLI

Kết nối vào ZooKeeper server không dùng chroot để quan sát path vật lý:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

Đọc các path:

~~~text
ls /
ls /platform
ls /platform/services
ls /platform/services/payment-service
~~~

Nếu ứng dụng không dùng chroot, kiểm tra /services và các child tương ứng. Nếu dùng chroot, hãy kiểm tra cả path vật lý từ CLI không chroot và path logic mà ứng dụng đang nhìn thấy.

## 7. Phân biệt lỗi authentication và authorization

ZooKeeper có hai lớp khác nhau:

- **Authentication:** client chứng minh danh tính bằng scheme như digest, sasl, x509 hoặc scheme tùy chỉnh.
- **Authorization:** ACL trên từng znode quyết định danh tính đã xác thực được phép thực hiện thao tác nào.

Vì vậy:

- AuthFailed thường chỉ ra quá trình xác thực không thành công, credential hoặc scheme không đúng, hoặc server không chấp nhận cơ chế xác thực.
- NoAuth / Insufficient permission thường cho biết client đã kết nối nhưng danh tính không có quyền cần thiết trên znode.

Thêm credential vào Curator không tự động cấp quyền trên các znode. Ngược lại, tạo ACL cho một digest identity cũng không giúp client nếu client không gửi đúng authentication info.

### 7.1. Các permission ACL

| Permission | Quyền |
|---|---|
| CREATE | Tạo child bên dưới znode hiện tại |
| READ | Đọc data và liệt kê child của znode hiện tại |
| WRITE | Ghi data của znode hiện tại |
| DELETE | Xóa child bên dưới znode hiện tại |
| ADMIN | Đọc/đặt ACL theo quy tắc quyền của ZooKeeper |

Một điểm rất dễ nhầm: CREATE và DELETE được kiểm tra trên **parent** của node được tạo/xóa. Ví dụ:

- Tạo /services/payment-service: cần CREATE trên /services.
- Tạo /services/payment-service/instance-a: cần CREATE trên /services/payment-service.
- Xóa instance-a: cần DELETE trên /services/payment-service.
- Liệt kê instance dưới /services/payment-service: cần READ trên /services/payment-service.
- Đọc metadata của instance: cần READ trên chính znode instance.
- Cập nhật data của instance: cần WRITE trên chính znode instance.

ACL của một znode **không tự kế thừa** xuống child. Có quyền trên /services không có nghĩa client có quyền đọc hoặc ghi mọi znode bên dưới. Phải kiểm tra ACL ở từng cấp path mà thao tác cần đi qua.

### 7.2. Scheme xác thực thường gặp

| Scheme | Cách nhận diện | Lưu ý |
|---|---|---|
| world | anyone | Thường dùng cho dữ liệu công khai; tránh cấp toàn quyền cho registry |
| auth | Danh tính đã xác thực | ACL tiện dụng cho creator/authenticated identity; cần có auth trước khi tạo |
| digest | Username/password | Phải gửi credential qua kết nối được bảo vệ; không ghi password vào source/log |
| sasl | SASL/Kerberos hoặc cơ chế được cấu hình | Cần đồng bộ principal, keytab và cấu hình server/client |
| x509 | X.509 principal qua TLS | Certificate và trust chain phải hợp lệ |
| ip | Địa chỉ IP client | Nhạy cảm với NAT, proxy và thay đổi địa chỉ |

Không dùng world:anyone với quyền cdrwa cho registry production. Một ACL mở như vậy cho phép mọi client có thể đọc, ghi, tạo child, xóa child và thay đổi ACL.

## 8. Đọc và xác minh ACL

Kết nối CLI tới server bằng user có đủ quyền đọc ACL:

~~~bash
bin/zkCli.sh -server zk1.internal:2181
~~~

Nếu dùng digest, xác thực trong CLI:

~~~text
addauth digest service-reader:REDACTED
~~~

Không đặt password thật trong shell history, ticket, log hoặc tài liệu. Dùng secret của môi trường và chỉ nhập credential trong phiên quản trị được bảo vệ.

Đọc ACL ở từng cấp:

~~~text
getAcl /services
getAcl /services/payment-service
getAcl /services/payment-service/instance-a
~~~

Nếu getAcl cũng báo NoAuth, tài khoản hiện tại không có READ hoặc ADMIN phù hợp trên node. Dùng danh tính quản trị được cấp quyền đúng cách; không mở ACL rộng chỉ để đọc nhanh.

Kiểm tra danh tính và quyền theo từng thao tác:

1. Client có xác thực bằng đúng scheme không?
2. Parent có CREATE để tạo service/instance child không?
3. Service parent có READ để discovery liệt kê child không?
4. Instance node có READ để client đọc metadata không?
5. Instance node có WRITE nếu provider cần cập nhật data không?
6. Parent có DELETE để deregister child không?
7. Node có ADMIN nếu ứng dụng cần đổi ACL không?

## 9. Cấu hình authentication cho Spring Cloud Zookeeper

Spring Cloud Zookeeper dùng CuratorFramework. Tài liệu Spring Cloud mô tả việc thêm authentication information bằng addAuthInfo trên CuratorFramework bean trong giai đoạn bootstrap. Cấu hình thực tế cần tuân theo cách auto-configuration và bootstrap mechanism của release train đang dùng.

Ví dụ minh họa cách gửi digest authentication:

~~~java
import java.nio.charset.StandardCharsets;

import org.apache.curator.RetryPolicy;
import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.CuratorFrameworkFactory;
import org.apache.curator.retry.ExponentialBackoffRetry;

public final class CuratorAuthExample {
    public static CuratorFramework createClient(
            String connectString,
            String credential) {
        if (credential == null || credential.trim().isEmpty()) {
            throw new IllegalArgumentException("Digest credential is required");
        }
        RetryPolicy retryPolicy = new ExponentialBackoffRetry(1000, 3);
        CuratorFramework client = CuratorFrameworkFactory.builder()
                .connectString(connectString)
                .sessionTimeoutMs(30000)
                .connectionTimeoutMs(15000)
                .authorization(
                        "digest",
                        credential.getBytes(StandardCharsets.UTF_8))
                .retryPolicy(retryPolicy)
                .build();
        client.start();
        return client;
    }
}
~~~

Đây là ví dụ tạo một Curator client có authentication được cấu hình ngay trên builder, để thông tin xác thực gắn với client qua các lần kết nối lại. Trong ứng dụng Spring Cloud Zookeeper, hãy tích hợp phần authorization vào CuratorFramework bean mà discovery/config thực sự sử dụng. Không tạo thêm một client độc lập trong khi auto-configuration vẫn dùng client chưa được xác thực. Một số release train yêu cầu custom CuratorFramework bean hoặc BootstrapConfiguration; hãy làm theo tài liệu đúng phiên bản.

Nếu tự tạo CuratorFramework bean, cần giữ lại các cấu hình quan trọng mà Spring Cloud auto-configuration mặc định cung cấp như connect string, timeout, retry policy, namespace và lifecycle. Không tạo client thứ hai ngoài ý muốn rồi để discovery dùng client chưa được xác thực.

Credential nên được lấy từ secret manager hoặc secret mount, không hard-code. Nếu dùng digest, ZooKeeper xác thực theo cơ chế digest của scheme; TLS vẫn cần được cấu hình để bảo vệ credential trên đường truyền.

## 10. ACL của parent và child khi đăng ký service

Để đăng ký thành công, ứng dụng thường cần đi qua nhiều cấp path. Ví dụ:

~~~text
/services
/services/payment-service
/services/payment-service/payment-instance-a
~~~

Quyền tối thiểu phụ thuộc chính xác vào cách provider tạo path và cập nhật registration:

| Path | Thao tác | Quyền cần xem xét |
|---|---|---|
| /services | Tạo child service name; liệt kê service | CREATE, READ |
| /services/payment-service | Tạo/xóa instance child; liệt kê instance | CREATE, DELETE, READ |
| /services/payment-service/payment-instance-a | Đọc metadata; cập nhật data; đọc ACL nếu cần | READ, WRITE hoặc ADMIN tùy thao tác |

Bảng này là checklist phân tích quyền, không phải ACL policy cố định. Curator Service Discovery có thể tạo path parent, tạo ephemeral node và cập nhật metadata theo version cụ thể. Hãy xác minh thao tác thực tế trong log hoặc tài liệu provider trước khi cấp quyền tối thiểu.

ACL không đệ quy, nên cần tạo hoặc cập nhật ACL cho parent và child phù hợp. Nếu thay đổi policy, hãy lập kế hoạch migration cho các znode hiện có; thay ACL trên parent không tự sửa ACL của những child đã được tạo trước đó.

## 11. Lỗi ACL và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| AuthFailed ngay khi kết nối | Sai credential, sai scheme hoặc SASL/TLS không khớp | Kiểm tra auth scheme, secret, principal, certificate và server config |
| NoAuth khi ls /services | Thiếu READ trên /services hoặc namespace đang truy cập | Kiểm tra identity và ACL của đúng path |
| NoAuth khi tạo instance | Thiếu CREATE trên parent service znode | Kiểm tra ACL parent, không chỉ ACL của instance |
| NoAuth khi deregister | Thiếu DELETE trên parent | Kiểm tra quyền xóa child ở service parent |
| NoAuth khi cập nhật metadata | Thiếu WRITE trên instance znode | Kiểm tra ACL instance node |
| NoAuth khi getAcl | Thiếu READ hoặc ADMIN phù hợp | Dùng tài khoản quản trị được cấp quyền |
| Client có credential nhưng vẫn bị từ chối | Credential được thêm sau khi thao tác đã chạy hoặc discovery dùng Curator client khác | Kiểm tra bootstrap order và bean Curator thực tế |
| Một số service đăng ký được, service khác không | ACL khác nhau ở parent/child hoặc path cũ | So sánh ACL trên từng nhánh service |

## 12. Runbook chẩn đoán theo thứ tự

Khi service không đăng ký được hoặc DiscoveryClient không tìm thấy instance, làm theo trình tự:

### Bước 1: Xác định provider và cấu hình hiệu lực

- Xác nhận ứng dụng đang dùng Spring Cloud Zookeeper Discovery hay chỉ dùng ZooKeeper Config.
- Kiểm tra dependency starter, profile và cấu hình cuối cùng sau khi override.
- Ghi nhận connect-string, session timeout, connection timeout, discovery root, chroot và instance ID.
- Xác nhận mọi instance cùng namespace đang dùng một discovery root.

### Bước 2: Kiểm tra kết nối và session

- Kiểm tra DNS và TCP đến client port của từng server trong connect string.
- Đọc log Curator để tìm SUSPENDED, RECONNECTED, LOST, ConnectionLoss và SessionExpired.
- Kiểm tra ZooKeeper ensemble có leader/quorum và client port đang phục vụ.
- Đối chiếu thời điểm mất mạng với session timeout và JVM pause/GC pause.
- Không tạo session/client mới chỉ vì SUSPENDED; đợi Curator xử lý reconnect.

### Bước 3: Kiểm tra path

- Dùng CLI không chroot để kiểm tra path vật lý.
- Kiểm tra /services hoặc discovery root tùy chỉnh.
- Nếu connect string có chroot, ánh xạ path logic sang path vật lý.
- Xác nhận parent tồn tại và đúng service ID/instance ID.
- Nếu nhận NodeExists, đọc node và kiểm tra owner/data trước khi quyết định xóa hoặc tạo lại.

### Bước 4: Kiểm tra authentication và ACL

- Xác nhận client gửi đúng auth scheme và credential.
- Đọc ACL ở root, service parent và instance node.
- Kiểm tra quyền CREATE/DELETE trên parent, READ/WRITE trên node.
- Kiểm tra ACL của child vì ACL không tự kế thừa.
- Đối chiếu credential được cấu hình trước khi Spring Cloud Discovery sử dụng Curator.

### Bước 5: Phục hồi và xác minh

- Nếu session đã LOST, xác nhận session mới và registration ephemeral được tạo lại.
- Nếu path sai, sửa đúng discovery root/chroot và thống nhất giữa các service.
- Nếu ACL sai, cấp quyền tối thiểu ở đúng cấp path.
- Kiểm tra DiscoveryClient trả đúng service ID và instance.
- Theo dõi log và registry một khoảng thời gian để chắc chắn lỗi không tái diễn.

~~~mermaid
flowchart TD
    A[Service không thấy registration] --> B{Curator connection state?}
    B -->|SUSPENDED / ConnectionLoss| C[Kiểm tra mạng, server và timeout]
    B -->|LOST / SessionExpired| D[Khôi phục session và ephemeral registration]
    B -->|CONNECTED / RECONNECTED| E[Kiểm tra path và namespace]
    E -->|NoNode / NodeExists| F[Đối chiếu root, chroot, parent và instance ID]
    E -->|Path hợp lệ| G[Kiểm tra authentication và ACL]
    G -->|AuthFailed / NoAuth| H[Kiểm tra scheme, credential và quyền parent/child]
    G -->|Quyền hợp lệ| I[Kiểm tra registration provider và DiscoveryClient]
    C --> J[Xác minh lại session và path]
    D --> J
    F --> J
    H --> J
    I --> K[Kiểm tra service instance xuất hiện và được truy vấn]
~~~

## 13. Phục hồi sau session expiration

Khi Curator báo LOST hoặc ZooKeeper báo session expired:

1. Đánh dấu registration/session cũ không còn đáng tin cậy.
2. Không cố dùng lại ephemeral owner hoặc session ID cũ.
3. Để Curator tạo kết nối/session mới theo lifecycle của framework.
4. Kiểm tra registration của service có được Spring Cloud Zookeeper/Curator Service Discovery tạo lại hay không.
5. Nếu ứng dụng tự quản lý registration, đăng ký lại bằng instance ID/path ổn định theo chính sách của ứng dụng.
6. Thiết lập lại các watch hoặc cache phụ thuộc session cũ.
7. Xác minh instance mới có ephemeral owner thuộc session mới và được DiscoveryClient nhìn thấy.

Không giả định mọi phiên bản/provider đều tự đăng ký lại giống nhau. Spring Cloud Zookeeper quản lý discovery qua Curator Service Discovery, nhưng logic phục hồi cụ thể phụ thuộc phiên bản và cách ứng dụng tùy biến Curator. Nếu đã thay CuratorFramework hoặc tự tạo registration, cần kiểm thử session-loss trong integration test.

Nếu ứng dụng có nhiều replica, mỗi replica phải có instance ID duy nhất. Dùng cùng một ID cho hai process có thể gây NodeExists, ghi đè hoặc tranh chấp registration tùy cách provider tạo node.

## 14. Phục hồi path và ACL an toàn

Khi gặp NoNode:

- Xác nhận chroot có tồn tại ở phía server.
- Xác nhận discovery root đúng và parent path được tạo trước khi đăng ký child.
- Kiểm tra service name có bị thay đổi bởi profile hoặc cấu hình môi trường không.
- Chỉ tạo parent path còn thiếu sau khi xác minh namespace đích.

Khi gặp NodeExists:

- Đọc stat và data của node.
- Kiểm tra ephemeral owner để biết node có thuộc session hiện tại không.
- So sánh instance ID và metadata.
- Không xóa node nếu chưa xác định chủ sở hữu hoặc node vẫn thuộc một process đang chạy.

Khi gặp NoAuth:

- Không chuyển toàn bộ registry sang OPEN_ACL_UNSAFE.
- Xác định thao tác thiếu quyền và path cụ thể.
- Cấp quyền tối thiểu ở parent và child cần thiết.
- Kiểm thử cả register, list, read, update và deregister bằng đúng service identity.

Thay đổi ACL cần có tài khoản ADMIN phù hợp. Trước khi sửa trên production, ghi nhận ACL hiện tại, kiểm tra các client đang dùng và có kế hoạch rollback. Việc sửa ACL parent không tự áp dụng xuống child.

## 15. Kiểm thử phòng ngừa

Nên có integration test với ZooKeeper test container hoặc ensemble thử nghiệm để xác minh các tình huống:

- Kết nối bình thường và đăng ký service.
- Ngắt mạng ngắn hơn session timeout rồi reconnect; session và ephemeral node còn được duy trì.
- Ngắt mạng đủ lâu để session hết hạn; registration cũ bị xóa và ứng dụng tạo lại registration theo thiết kế.
- Sai chroot hoặc discovery root; ứng dụng báo path error có thể chẩn đoán.
- Parent path chưa tồn tại; quy trình bootstrap tạo đúng namespace.
- Credential sai; client nhận lỗi authentication rõ ràng.
- Thiếu CREATE, READ, WRITE hoặc DELETE ở đúng cấp; test xác nhận thao tác tương ứng thất bại.
- Dùng ACL đúng; registration, discovery và deregistration đều hoạt động.
- Nhiều replica có instance ID khác nhau; không xung đột registration.

Unit test có thể mock Curator hoặc ServiceRegistry để kiểm tra logic xử lý lỗi. Nhưng chỉ integration test mới xác nhận session expiration, ephemeral znode, ACL và path semantics thực tế của ZooKeeper.

## 16. Những lỗi thiết kế nên tránh

- Tạo ZooKeeper client mới mỗi lần nhận SUSPENDED, làm tăng session và kết nối không cần thiết.
- Xem RECONNECTED là bằng chứng registration đã tồn tại.
- Xóa znode khi thấy NodeExists mà chưa kiểm tra ephemeral owner.
- Nhầm path logic sau chroot với path vật lý trên server.
- Cấp world:anyone toàn quyền để chữa nhanh NoAuth.
- Chỉ sửa ACL parent nhưng quên child znode.
- Thêm credential sau khi DiscoveryClient đã bắt đầu đăng ký.
- Dùng instance ID giống nhau cho nhiều replica.
- Retry vô hạn khi NoAuth hoặc NoNode; đây là lỗi cấu hình/quyền/path cần sửa, không phải lỗi mạng tạm thời.
- Đưa password digest vào source code, log hoặc shell history.

## 17. Tài liệu tham khảo

- [Apache ZooKeeper Programmer's Guide — Sessions, Watches, ACLs và Error Handling](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Apache ZooKeeper Administrator's Guide](https://zookeeper.apache.org/doc/current/zookeeperAdmin.html)
- [Apache Curator — Error Handling và ConnectionStateListener](https://curator.apache.org/docs/errors/)
- [Apache Curator — Tech Note 12: Connection Semantics](https://curator.apache.org/docs/tech-note-12/)
- [Apache Curator — Tech Note 14: Session Expiration](https://curator.apache.org/docs/tech-note-14/)
- [Spring Cloud Zookeeper — Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper — Common Application Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
- [Spring Cloud Zookeeper — Access Control Lists](https://docs.spring.io/spring-cloud-zookeeper/reference/config.html)

Hãy chọn tài liệu có version khớp với ZooKeeper, Curator, Spring Boot và Spring Cloud release train của ứng dụng.

## 18. Tổng kết

Khi ZooKeeper gặp lỗi trong Spring Cloud Discovery, hãy phân biệt ba lớp: session/kết nối, path/chroot và authentication/ACL. Mất TCP chỉ đưa client vào trạng thái gián đoạn; ephemeral registration chỉ bị xóa khi session hết hạn. Curator dùng SUSPENDED, RECONNECTED và LOST để thông báo trạng thái, trong đó LOST yêu cầu phục hồi session và registration.

NoNode thường liên quan tới parent path, discovery root hoặc chroot; NodeExists cần kiểm tra kết quả thao tác trước đó và owner; NoAuth cần kiểm tra quyền ở đúng znode và parent; AuthFailed cần kiểm tra credential/scheme. ACL không kế thừa xuống child, vì vậy phải xác minh quyền trên từng cấp path. Sau phục hồi, kiểm tra registration thực tế, DiscoveryClient và khả năng deregister thay vì chỉ dựa vào việc Curator đã reconnect.
