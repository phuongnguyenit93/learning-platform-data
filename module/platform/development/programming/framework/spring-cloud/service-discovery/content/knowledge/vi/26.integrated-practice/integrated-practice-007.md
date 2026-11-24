# Dựng ZooKeeper và quan sát mất kết nối cùng hết hạn phiên

Bài thực hành này dựng một ZooKeeper server cục bộ, kết nối một client Curator, tạo ephemeral node và quan sát node đó khi client mất mạng. Hai kịch bản được thử riêng: khôi phục kết nối trước khi session timeout hết hạn và khôi phục sau khi session đã hết hạn.

Mục tiêu là hiểu vòng đời session trong ZooKeeper và tác động của nó tới service discovery trong Spring Cloud. ZooKeeper lưu thông tin đăng ký của instance dưới dạng znode; các znode ephemeral gắn với session của client. Khi session hết hạn, server xóa các ephemeral node do session đó sở hữu. Consumer đang theo dõi registry sẽ nhận biết instance đã rời hệ thống.

## 1. Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Dựng ZooKeeper bằng Docker Compose và kiểm tra server đang hoạt động.
- Tạo znode persistent và ephemeral bằng ZooKeeper CLI.
- Kết nối ứng dụng Java bằng Apache Curator.
- Quan sát các trạng thái `CONNECTED`, `SUSPENDED`, `RECONNECTED`, `LOST` và `READ_ONLY`.
- Phân biệt mất TCP tạm thời với session expiration.
- Xác minh ephemeral node bị xóa sau khi session hết hạn.
- Khôi phục registration sau khi client nhận session mới.
- Cấu hình Spring Cloud Zookeeper Discovery và kiểm tra service instance từ `DiscoveryClient`.

## 2. Hiểu session trước khi thử nghiệm

ZooKeeper không xem một TCP connection là danh tính lâu dài của client. Client làm việc với server thông qua một **session** có session ID và timeout đã được thương lượng.

Khi client tạo ephemeral node, ZooKeeper gắn node đó với session hiện tại. Node sẽ bị xóa khi session kết thúc hoặc hết hạn. Một client có thể mất kết nối TCP trong chốc lát mà session vẫn còn hiệu lực; nếu kết nối trở lại trước khi server hết hạn session, client tiếp tục dùng session cũ và ephemeral node vẫn còn.

### 2.1. Phân biệt các trạng thái

| Trạng thái | Ý nghĩa | Hành động phù hợp |
|---|---|---|
| `CONNECTED` | Curator kết nối thành công lần đầu | Đăng ký instance và bắt đầu công việc |
| `SUSPENDED` | Kết nối tới ZooKeeper bị gián đoạn | Tạm dừng thao tác cần bảo đảm coordination; không giả định write đã thành công |
| `RECONNECTED` | Kết nối được khôi phục | Kiểm tra trạng thái và tiếp tục nếu session cũ còn hiệu lực |
| `LOST` | Curator cho rằng session đã hết hạn hoặc không còn dùng được | Xem session cũ là mất; đăng ký lại ephemeral node, lấy lại lock và tham gia leader election lại |
| `READ_ONLY` | Client vào chế độ chỉ đọc khi cấu hình cho phép | Không thực hiện thao tác ghi hoặc coi instance là đã đăng ký đầy đủ |

`SUSPENDED` không đồng nghĩa `LOST`. Một đợt mất mạng ngắn có thể tạo chuỗi `SUSPENDED` rồi `RECONNECTED`; session cũ vẫn hợp lệ. Nếu gián đoạn kéo dài vượt session timeout, client đi vào `LOST`; sau khi kết nối lại, Curator có thể tạo session mới và phát `RECONNECTED`.

Curator khuyến nghị coi `SUSPENDED` là mất kết nối đối với các recipe cần an toàn như lock và leader election. Trong thời gian suspended, ứng dụng nên dừng công việc phụ thuộc vào quyền sở hữu lock hoặc vai trò leader. Khi `LOST`, không được tái sử dụng giả định về lock, leadership hay ephemeral registration cũ.

### 2.2. Server quyết định thời điểm hết hạn

Khi tạo session, client gửi thời gian timeout mong muốn. ZooKeeper server thương lượng timeout trong giới hạn cấu hình của server.

Với cấu hình mặc định:

- `tickTime` thường là 2.000 ms.
- `minSessionTimeout` mặc định bằng `2 × tickTime`.
- `maxSessionTimeout` mặc định bằng `20 × tickTime`.

Nếu `tickTime=2000`, server thường chấp nhận session timeout trong khoảng 4.000–40.000 ms. Client yêu cầu ngoài giới hạn có thể nhận timeout đã được server điều chỉnh. Vì vậy, phải quan sát timeout thực tế/đã thương lượng, không chỉ nhìn giá trị cấu hình phía client.

Session expiration được quản lý bởi ZooKeeper server. Khi server không nhận heartbeat hoặc request hợp lệ trong thời gian timeout, server hết hạn session và xóa các ephemeral node thuộc session đó. Client đang mất kết nối không thể nhận thông báo ngay tại thời điểm server xóa node; nó thường chỉ biết session đã hết hạn khi kết nối lại.

~~~mermaid
sequenceDiagram
    participant C as Curator client
    participant Z as ZooKeeper server
    participant O as Observer client

    C->>Z: Open session S1
    C->>Z: Create ephemeral node
    Z-->>O: Node appears
    Note over C,Z: Network partition
    C--xZ: Heartbeat / request unavailable
    Note over Z: Session timeout elapses
    Z-->>O: Ephemeral node deleted
    Note over C: Client still disconnected
    C->>Z: Network restored, reconnect with S1
    Z-->>C: Session S1 expired
    Note over C: Curator reports LOST
    C->>Z: Establish new session S2
    C->>Z: Re-create ephemeral node
    Z-->>O: New registration appears
~~~

Một observer client vẫn kết nối được sẽ nhìn thấy ephemeral node biến mất khi server hết hạn session, dù owner client còn đang disconnected và chưa nhận được event `LOST`.

## 3. Dựng ZooKeeper bằng Docker Compose

Tạo file `compose.yaml` trong thư mục lab:

~~~yaml
services:
  zookeeper:
    image: zookeeper:3.9.7
    container_name: zk-lab
    hostname: zookeeper
    ports:
      - "127.0.0.1:2181:2181"
    environment:
      ZOO_TICK_TIME: "2000"
      ZOO_4LW_COMMANDS_WHITELIST: "ruok,stat,srvr,mntr"
    volumes:
      - zk-data:/data
      - zk-datalog:/datalog
    networks:
      - lab

volumes:
  zk-data:
  zk-datalog:

networks:
  lab:
    name: zk-discovery-lab
~~~

Cấu hình này dành cho môi trường học tập một node:

- `2181` là client port.
- `ZOO_TICK_TIME` đặt tick time bằng 2 giây.
- `ZOO_4LW_COMMANDS_WHITELIST` chỉ bật một số lệnh chẩn đoán cần dùng trong lab.
- `/data` và `/datalog` được lưu trong named volume để dữ liệu không mất khi container được tạo lại.
- Port được bind vào `127.0.0.1`, tránh mở client port ra mọi interface của máy.

ZooKeeper 3.9.7 là một bản phát hành hiện hành của nhánh 3.9 tại thời điểm viết bài. Trong CI và môi trường triển khai, nên pin image digest sau khi chọn phiên bản đã được kiểm thử.

Khởi động:

~~~bash
docker compose up -d
docker compose ps
docker compose logs -f zookeeper
~~~

Trên Windows PowerShell, kiểm tra port từ host:

~~~powershell
Test-NetConnection 127.0.0.1 -Port 2181
~~~

Kết quả `TcpTestSucceeded: True` chỉ chứng minh TCP port có thể kết nối. Nó chưa xác minh trạng thái quorum hay khả năng thực hiện thao tác ZooKeeper.

### 3.1. Kiểm tra server bằng CLI

Mở ZooKeeper CLI trong container:

~~~bash
docker compose exec zookeeper zkCli.sh -server 127.0.0.1:2181
~~~

Trong CLI, kiểm tra cây znode:

~~~text
ls /
create /lab "root"
create /lab/sessions "sessions"
create -e /lab/sessions/manual "owner=cli"
ls /lab/sessions
stat /lab/sessions/manual
~~~

Trong output của `stat`, trường `ephemeralOwner` khác 0 cho biết node thuộc về một session. Với node persistent, `ephemeralOwner` bằng 0.

Mở một CLI thứ hai để quan sát node:

~~~text
ls /lab/sessions
stat /lab/sessions/manual
~~~

Thoát CLI đã tạo node bằng `quit` hoặc đóng phiên terminal. Khi session đóng bình thường, node ephemeral sẽ biến mất. Đây là kiểm tra vòng đời cơ bản; các phần sau sẽ giữ client chạy và chỉ làm gián đoạn mạng để phân biệt `SUSPENDED` với `LOST`.

### 3.2. Lệnh chẩn đoán Four Letter Words

Có thể kiểm tra nhanh bằng các lệnh:

- `ruok`: server trả `imok` khi process đang hoạt động và client port được bind.
- `stat`: trạng thái server và thông tin kết nối.
- `srvr`: thông tin server.
- `mntr`: các metric giám sát dạng key/value.

`ruok` không chứng minh server đã tham gia quorum. Với ensemble nhiều node, dùng `stat` hoặc `mntr` để xem mode/role và trạng thái đồng bộ. Các lệnh `cons` và `dump` có thể tiết lộ session, connection và ephemeral node; chỉ bật trong lab có kiểm soát và không mở endpoint chẩn đoán ra mạng công khai.

Trong production, ưu tiên AdminServer/metrics endpoint được bảo vệ và chỉ bật những giao diện chẩn đoán thực sự cần thiết.

## 4. Kết nối Spring Cloud Zookeeper Discovery

Spring Cloud Zookeeper dùng Apache Curator và service-discovery extension để đăng ký metadata instance như host, port, ID và tên service. Khi có dependency discovery trên classpath, ứng dụng vừa có thể đăng ký bản thân vừa có thể truy vấn các service khác.

### 4.1. Dependency

Thêm starter vào ứng dụng Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
~~~

Quản lý phiên bản bằng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án. Không tự ghim một phiên bản Curator khác với dependency management của Spring Cloud nếu chưa kiểm tra tương thích.

### 4.2. Cấu hình kết nối và registration

Nếu ứng dụng chạy trực tiếp trên host:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: localhost:2181
      connection-timeout: 3000
      session-timeout: 10000
      discovery:
        enabled: true
        register: true
        root: /services
~~~

Nếu ứng dụng chạy trong container cùng network với ZooKeeper, dùng hostname service:

~~~yaml
spring:
  cloud:
    zookeeper:
      connect-string: zookeeper:2181
~~~

`session-timeout` được tính bằng milliseconds. Giá trị 10.000 ms trong ví dụ nằm trong khoảng mặc định thường gặp của server khi `tickTime=2000`. Server vẫn có quyền thương lượng giá trị trong giới hạn cấu hình của nó.

Không nhầm `connection-timeout` với `session-timeout`:

- Connection timeout giới hạn thời gian thiết lập kết nối.
- Session timeout xác định khoảng thời gian server cho phép không nhận heartbeat/request trước khi hết hạn session.

### 4.3. Kiểm tra service registration

Khởi động ứng dụng và mở ZooKeeper CLI:

~~~text
ls /services
ls /services/inventory-service
~~~

Spring Cloud Zookeeper sử dụng root `/services` theo cấu hình mặc định. Dưới service name sẽ có thông tin instance do discovery extension quản lý. Các node đăng ký instance được gắn với vòng đời session; không sửa hoặc xóa thủ công các node do ứng dụng đang quản lý.

Consumer có thể truy vấn bằng abstraction chung của Spring Cloud:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Khi thử nghiệm, ghi lại số instance trả về trước khi gây mất kết nối, trong lúc session hết hạn và sau khi registration được khôi phục.

## 5. Tạo Curator session probe độc lập

Để quan sát trạng thái session trực tiếp, có thể chạy một Java probe độc lập. Probe này tạo một ephemeral node, in trạng thái kết nối và tự đăng ký lại khi Curator báo `LOST` rồi kết nối lại.

### 5.1. Dependency Curator

Nếu tạo một chương trình Java độc lập không dùng Spring Cloud starter, thêm `curator-framework`:

~~~xml
<dependency>
    <groupId>org.apache.curator</groupId>
    <artifactId>curator-framework</artifactId>
    <version>5.9.0</version>
</dependency>
~~~

Curator 5.9.0 là bản phát hành hiện hành của Apache Curator tại thời điểm viết bài. Nếu probe chạy bên trong ứng dụng Spring Cloud, hãy ưu tiên phiên bản Curator được BOM của ứng dụng quản lý.

### 5.2. Code quan sát session và ephemeral node

~~~java
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.CuratorFrameworkFactory;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.retry.ExponentialBackoffRetry;
import org.apache.zookeeper.CreateMode;

public class SessionProbe {

    private static final String PATH = "/lab/sessions/probe-1";

    private static final byte[] DATA =
            "service=inventory-probe;port=8080"
                    .getBytes(StandardCharsets.UTF_8);

    public static void main(String[] args) throws Exception {
        String connectString =
                System.getProperty("zk", "localhost:2181");

        CuratorFramework client = CuratorFrameworkFactory.builder()
                .connectString(connectString)
                .sessionTimeoutMs(10_000)
                .connectionTimeoutMs(3_000)
                .retryPolicy(new ExponentialBackoffRetry(500, 5))
                .build();

        AtomicBoolean sessionWasLost = new AtomicBoolean(false);
        ExecutorService recoveryExecutor =
                Executors.newSingleThreadExecutor();

        client.getConnectionStateListenable().addListener((ignored, state) -> {
            System.out.println(Instant.now() + " state=" + state);

            if (state == ConnectionState.SUSPENDED) {
                System.out.println(
                        "Connection lost; pause work that requires coordination");
            }

            if (state == ConnectionState.LOST) {
                System.out.println(
                        "Session expired; old ephemeral nodes are no longer valid");
                sessionWasLost.set(true);
            }

            if (state == ConnectionState.RECONNECTED
                    && sessionWasLost.compareAndSet(true, false)) {
                recoveryExecutor.submit(() -> register(client));
            }

            if (state == ConnectionState.READ_ONLY) {
                System.out.println(
                        "Read-only connection; do not assume writes are available");
            }
        });

        client.start();

        if (!client.blockUntilConnected(15, TimeUnit.SECONDS)) {
            client.close();
            throw new IllegalStateException("Cannot connect to ZooKeeper");
        }

        register(client);

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            recoveryExecutor.shutdown();
            client.close();
        }));

        new CountDownLatch(1).await();
    }

    private static void register(CuratorFramework client) {
        try {
            String createdPath = client.create()
                    .creatingParentsIfNeeded()
                    .withMode(CreateMode.EPHEMERAL)
                    .forPath(PATH, DATA);

            System.out.println(
                    Instant.now() + " registered ephemeral node " + createdPath);
        } catch (Exception ex) {
            System.err.println(
                    Instant.now() + " registration failed: " + ex.getMessage());
        }
    }
}
~~~

Một số điểm cần chú ý:

- Listener được đăng ký trước `client.start()` để không bỏ lỡ trạng thái ban đầu.
- `SUSPENDED` chỉ ghi nhận mất kết nối; probe không tạo lại node ngay vì session cũ có thể vẫn còn hiệu lực.
- Chỉ khi đã nhận `LOST`, cờ `sessionWasLost` mới được bật.
- Sau `RECONNECTED`, nếu trước đó đã `LOST`, probe chạy đăng ký lại trên executor riêng.
- Không thực hiện thao tác ZooKeeper đồng bộ kéo dài ngay trong callback listener.
- Nếu gặp `NodeExistsException`, cần điều tra xung đột instance ID/session. Không xóa node một cách mù quáng.

Đối với ứng dụng thực tế, ephemeral registration, lock và leader election cần được phục hồi theo đúng abstraction mà ứng dụng dùng. Ví dụ này chỉ minh họa một node độc lập; Spring Cloud Zookeeper Discovery tự quản lý registration của service thông qua discovery extension. Hãy kiểm tra hành vi phục hồi của phiên bản thư viện thực tế thay vì tạo thêm znode thủ công dưới `/services`.

## 6. Quan sát session bằng hai client

Cần hai client độc lập:

- **Owner client:** chạy `SessionProbe`, tạo `/lab/sessions/probe-1`.
- **Observer client:** một ZooKeeper CLI khác dùng để kiểm tra node có còn tồn tại không.

Lệnh `docker network disconnect` ở các bước sau chỉ áp dụng khi Owner client đang chạy trong một container đã tham gia network `zk-discovery-lab`. Ví dụ, sau khi đóng gói probe thành image:

~~~bash
docker run -d --name zk-probe --network zk-discovery-lab -e JAVA_TOOL_OPTIONS="-Dzk=zookeeper:2181" <probe-image>
docker logs -f zk-probe
~~~

Thay `<probe-image>` bằng image ứng dụng chứa lớp `SessionProbe`. Nếu chạy probe trực tiếp trên host, hãy chuyển probe vào container lab hoặc dùng một cơ chế firewall cô lập riêng; lệnh disconnect network không tác động lên process chạy ngoài Docker.

Giữ Owner client chạy liên tục. Trong Observer CLI:

~~~text
ls /lab/sessions
stat /lab/sessions/probe-1
~~~

Ghi lại `ephemeralOwner` và thời điểm node xuất hiện. Khi Owner mất mạng, Observer vẫn kết nối với ZooKeeper và có thể quan sát thời điểm server xóa node.

Không đóng Owner client trong lúc thử. `client.close()` hoặc thoát chương trình sẽ kết thúc session có chủ đích và xóa ephemeral node ngay; thao tác đó không mô phỏng một network partition.

## 7. Thử nghiệm A: mất kết nối ngắn hơn session timeout

Giả sử probe yêu cầu session timeout 10 giây. Dùng client chạy trong một container đã tham gia network `zk-discovery-lab`. Nếu ứng dụng chạy trong container, hãy dùng địa chỉ `zookeeper:2181`.

Xác định container client đang chạy probe. Ngắt riêng container đó khỏi network của ZooKeeper:

~~~bash
docker network disconnect zk-discovery-lab <probe-container>
~~~

Chờ khoảng 3 giây, ngắn hơn đáng kể so với session timeout 10 giây. Sau đó kết nối lại:

~~~bash
docker network connect zk-discovery-lab <probe-container>
~~~

Quan sát log của probe. Kết quả thường thấy:

~~~text
CONNECTED
SUSPENDED
RECONNECTED
~~~

Kiểm tra lại node từ Observer:

~~~text
ls /lab/sessions
stat /lab/sessions/probe-1
~~~

Node vẫn tồn tại vì session cũ chưa hết hạn. `sessionWasLost` không được bật, nên probe không tạo lại node và không gặp xung đột `NodeExists`.

**Kết luận của thử nghiệm A:** mất kết nối TCP không tự động xóa ephemeral node. Khi client quay lại kịp thời, ZooKeeper có thể tiếp tục session cũ.

## 8. Thử nghiệm B: mất kết nối dài hơn session timeout

Đưa probe về trạng thái kết nối ổn định và xác nhận node đang tồn tại. Ngắt container client khỏi network lần nữa:

~~~bash
docker network disconnect zk-discovery-lab <probe-container>
~~~

Giữ gián đoạn lâu hơn timeout đã thương lượng. Với ví dụ 10 giây, chờ khoảng 20 giây để có biên an toàn cho lịch heartbeat, timer và thời gian xử lý.

Trong thời gian owner bị ngắt mạng, dùng Observer CLI kiểm tra:

~~~text
ls /lab/sessions
~~~

Sau khi server hết hạn session, `/lab/sessions/probe-1` sẽ biến mất. Owner vẫn chưa thể nhận notification vì nó đang disconnected.

Khôi phục network:

~~~bash
docker network connect zk-discovery-lab <probe-container>
~~~

Khi Curator kết nối lại, quan sát chuỗi trạng thái:

~~~text
SUSPENDED
LOST
RECONNECTED
registered ephemeral node /lab/sessions/probe-1
~~~

Thứ tự log cụ thể có thể khác theo thời điểm client nhận event và phiên bản Curator. Điều cần xác minh là:

1. Observer thấy ephemeral node cũ biến mất khi server hết hạn session.
2. Owner nhận biết session cũ đã mất sau khi kết nối lại.
3. Curator tạo session mới.
4. Probe đăng ký lại ephemeral node.
5. Observer nhìn thấy node xuất hiện trở lại.

**Kết luận của thử nghiệm B:** session hết hạn là một sự kiện vòng đời session, không chỉ là một lần TCP reconnect. Những ephemeral node của session cũ đã bị xóa và cần được tạo lại bằng session mới.

## 9. Vì sao owner không nhận thông báo hết hạn ngay lập tức?

Khi client bị network partition, ZooKeeper server vẫn hoạt động và tiếp tục quản lý session. Sau khi timeout hết, server xóa ephemeral node và thông báo cho các client khác đang kết nối/watch node.

Owner client đang disconnected nên không thể nhận event tại thời điểm đó. Khi network được khôi phục và client thử nối lại, server báo session cũ đã hết hạn. Lúc đó client mới nhận trạng thái expired/Curator `LOST`.

Vì vậy, có thể quan sát hai thời điểm khác nhau:

- **Thời điểm registry thay đổi:** ephemeral node đã bị server xóa; observer thấy service instance biến mất.
- **Thời điểm owner nhận biết:** client nối lại và được thông báo session đã hết hạn.

Đây là lý do consumer có thể ngừng nhìn thấy instance trước khi provider tự log ra `LOST`.

## 10. Theo dõi server bằng stat và mntr

Trong lab, dùng lệnh Four Letter Words đã bật trong allowlist:

~~~bash
docker compose exec zookeeper zkServer.sh status
~~~

Hoặc gửi `ruok`, `stat`, `mntr` qua client TCP hỗ trợ netcat:

~~~bash
printf ruok | nc 127.0.0.1 2181
printf stat | nc 127.0.0.1 2181
printf mntr | nc 127.0.0.1 2181
~~~

Một số trường trong `mntr` hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `zk_server_state` | Vai trò/state như standalone, leader hoặc follower |
| `zk_num_alive_connections` | Số client connection đang hoạt động |
| `zk_znode_count` | Số znode |
| `zk_watch_count` | Số watch |
| `zk_outstanding_requests` | Số request đang chờ xử lý |
| `zk_avg_latency` | Độ trễ trung bình xử lý request |
| `zk_max_latency` | Độ trễ xử lý lớn nhất theo thống kê server |

Trong thử nghiệm session expiration, quan sát connection count và znode count cùng thời điểm. Znode count có thể giảm khi ephemeral node bị xóa. Trong môi trường có nhiều ứng dụng, cần lọc theo path/service thay vì suy luận từ tổng znode count.

`ruok` trả `imok` chỉ cho biết server process đang hoạt động và client port được bind; nó không xác nhận quorum. Trong ensemble, hãy kiểm tra trạng thái leader/follower và số follower đã đồng bộ.

## 11. Liên hệ với Spring Cloud Zookeeper Discovery

Spring Cloud Zookeeper sử dụng Curator service-discovery extension để quản lý registration. Khi provider đăng ký, instance metadata được lưu trong cây `/services`. Registration gắn với session nên có thể bị xóa khi session hết hạn.

Khi chạy ứng dụng provider và consumer, ghi lại ba góc nhìn:

| Góc nhìn | Cách quan sát | Câu hỏi |
|---|---|---|
| ZooKeeper tree | `ls /services/inventory-service` | Registration znode còn tồn tại không? |
| Provider client | Curator connection state log | Client đang SUSPENDED, LOST hay RECONNECTED? |
| Consumer | `DiscoveryClient.getInstances()` | Consumer còn nhìn thấy instance không? |

Thử nghiệm kỳ vọng:

- Mất kết nối ngắn: provider có thể `SUSPENDED` rồi `RECONNECTED`; session cũ vẫn giữ registration.
- Mất kết nối vượt timeout: session cũ hết hạn và ephemeral registration biến mất; consumer không còn thấy instance sau khi cập nhật discovery view.
- Provider kết nối lại: discovery extension phải phục hồi registration theo lifecycle của phiên bản đang dùng; consumer sẽ thấy instance trở lại sau khi registry/discovery cache hội tụ.

Không kết luận consumer đã cập nhật chỉ dựa vào việc provider log `RECONNECTED`. Hãy truy vấn lại `DiscoveryClient` từ consumer hoặc kiểm tra znode trên ZooKeeper.

### 11.1. Phân biệt session timeout và discovery cache

Có thể có độ trễ giữa các mốc:

1. ZooKeeper server hết hạn session.
2. Ephemeral znode bị xóa.
3. Watcher/Curator nhận event.
4. Spring Cloud discovery extension cập nhật trạng thái.
5. Consumer refresh discovery result hoặc cache.

Nếu consumer vẫn thấy instance sau khi znode biến mất, kiểm tra discovery client cache và thời điểm truy vấn. Không kéo dài session timeout chỉ để che một cache chưa refresh.

### 11.2. Không dùng registration znode như nguồn authorization

Việc một service xuất hiện trong `/services` chỉ chứng minh registration tồn tại theo cơ chế discovery. Nó không thay thế xác thực danh tính hoặc authorization khi consumer gọi API. Endpoint nghiệp vụ vẫn cần TLS, authentication và policy quyền truy cập phù hợp.

## 12. Kiểm tra phục hồi an toàn sau LOST

Khi Curator báo `LOST`, ứng dụng nên xem mọi trạng thái gắn với session cũ là không còn đáng tin:

- Ephemeral registration phải được tạo lại.
- Distributed lock phải được lấy lại bằng thao tác acquire mới.
- Leader election phải tham gia lại.
- Watcher cần được thiết lập lại theo recipe/lifecycle tương ứng.
- Không tiếp tục ghi dựa trên giả định rằng instance vẫn giữ lock hoặc quyền leader cũ.

Không phải mọi thao tác đều cần tạo lại thủ công. Curator recipes và Spring Cloud Zookeeper discovery extension có cơ chế lifecycle riêng. Tuy nhiên, logic nghiệp vụ do ứng dụng tự quản lý vẫn phải nhận biết session loss và phục hồi state tương ứng.

Nếu dùng lock để bảo vệ tài nguyên bên ngoài ZooKeeper, cần fencing token hoặc cơ chế tương đương ở tài nguyên được bảo vệ. Session expiration không thể tự ngăn một process cũ tiếp tục chạy nếu process đó chưa nhận được thông báo do network partition.

## 13. Điều chỉnh session timeout và retry policy

Session timeout là thỏa hiệp giữa tốc độ phát hiện client mất kết nối và khả năng chịu network jitter:

- Timeout ngắn: ephemeral registration được dọn nhanh, nhưng client khỏe có thể bị expire khi mạng chập chờn.
- Timeout dài: giảm nguy cơ expire do gián đoạn ngắn, nhưng registration stale tồn tại lâu hơn và failover chậm hơn.

Không giảm timeout chỉ để thấy `LOST` nhanh trong lab rồi mang nguyên cấu hình đó lên production. Đo thời gian reconnect, heartbeat, network latency và thời gian xử lý của ensemble trước khi chọn giá trị.

Curator retry policy điều khiển cách retry thao tác lỗi. Nó không biến session đã hết hạn thành session cũ còn hợp lệ. Sau `LOST`, ứng dụng cần dùng session mới và phục hồi ephemeral state.

Với ensemble, client connection string nên có nhiều server để client có thể kết nối sang node còn hoạt động. Nếu chỉ khai báo một server, sự cố tại server đó sẽ làm client không có endpoint thay thế dù quorum còn tồn tại.

## 14. Mở rộng từ standalone lên ensemble

Compose ở bài này chỉ chạy một server để quan sát lifecycle. Nó không cung cấp tính sẵn sàng cao: khi node duy nhất ngừng hoạt động, không còn quorum để phục vụ request.

Trong production, ZooKeeper thường được triển khai với số voting member lẻ, phổ biến là 3 hoặc 5:

- Ensemble 3 node chịu được mất 1 node vì còn quorum 2.
- Ensemble 5 node chịu được mất 2 node vì còn quorum 3.
- Mất quá nửa số voting member khiến ensemble không còn quorum để tiếp tục xử lý ghi.

Khi một node hỏng nhưng quorum còn, client có thể reconnect tới node khác và tiếp tục session cũ nếu session chưa hết hạn. Khi client bị cô lập khỏi toàn bộ ensemble quá lâu, session có thể hết hạn dù các server còn lại vẫn hoạt động.

Không dùng một node ZooKeeper cục bộ để mô phỏng mọi tình huống quorum. Bài thực hành này kiểm tra session lifecycle và ephemeral registration; kiểm thử leader election, quorum loss và failover cần một ensemble nhiều node.

## 15. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Không thấy `CONNECTED` | Sai connect string, server chưa sẵn sàng hoặc TCP bị chặn | Kiểm tra port, logs, `zkServer.sh status` |
| Có `SUSPENDED` rồi `RECONNECTED`, node vẫn còn | Kết nối phục hồi trước session expiry | Kiểm tra `ephemeralOwner` và node path |
| Có `LOST`, node biến mất | Session đã hết hạn hoặc Curator xem session không còn dùng được | Observer kiểm tra znode và server log |
| Không có `LOST` sau khi chờ | Mạng chưa bị chặn hoàn toàn hoặc timeout thương lượng lớn hơn dự kiến | Kiểm tra container network, session timeout và server min/max |
| Node không biến mất | Owner vẫn heartbeat qua đường mạng khác hoặc chưa vượt timeout | Kiểm tra toàn bộ địa chỉ trong connect string và observer |
| Node không được tạo lại | Recovery listener không chạy, Curator chưa reconnect hoặc create bị lỗi | Kiểm tra `RECONNECTED`, exception và quyền ACL |
| `NodeExistsException` khi đăng ký lại | Một registration khác đang dùng cùng path hoặc owner cũ chưa hết hạn | Kiểm tra `ephemeralOwner`; không xóa node mù quáng |
| Consumer vẫn thấy instance cũ | Discovery cache chưa refresh hoặc query diễn ra trước khi cập nhật | Kiểm tra znode, discovery client và cache timestamp |
| `ruok` trả `imok` nhưng không ghi được | Server process sống nhưng không có quorum hoặc đang read-only | Dùng `stat`, `mntr` và server logs |
| Chỉ một app không reconnect | Container không được gắn lại network hoặc connect string sai | Kiểm tra network attachments và DNS |

## 16. Checklist hoàn thành lab

- [ ] ZooKeeper container chạy và client port 2181 truy cập được.
- [ ] CLI tạo được persistent parent và ephemeral child.
- [ ] Curator probe kết nối và log `CONNECTED`.
- [ ] Observer nhìn thấy ephemeral node và đọc được `ephemeralOwner`.
- [ ] Ngắt mạng ngắn hơn timeout tạo `SUSPENDED` rồi `RECONNECTED`.
- [ ] Sau gián đoạn ngắn, ephemeral node vẫn tồn tại.
- [ ] Ngắt mạng lâu hơn timeout làm server xóa ephemeral node.
- [ ] Owner nhận `LOST` khi kết nối lại.
- [ ] Curator thiết lập session mới và probe tạo lại ephemeral node.
- [ ] Consumer Spring Cloud Zookeeper được kiểm tra lại bằng `DiscoveryClient`.
- [ ] Đã phân biệt connection timeout, session timeout và cache refresh.
- [ ] Đã hiểu giới hạn của một node standalone so với ensemble production.

## 17. Ghi nhớ

- Session là danh tính lâu dài hơn TCP connection; mất TCP không đồng nghĩa session hết hạn.
- `SUSPENDED` biểu thị mất kết nối; `RECONNECTED` có thể tiếp tục session cũ.
- `LOST` có nghĩa ứng dụng phải xem session cũ là không còn hợp lệ.
- ZooKeeper server quyết định session expiration và xóa ephemeral node thuộc session đó.
- Owner client đang disconnected thường chỉ nhận thông báo expiration khi reconnect.
- Curator retry policy không cứu được session đã hết hạn.
- Sau `LOST`, cần tạo lại ephemeral registration và lấy lại coordination state.
- `ruok` chỉ xác nhận process/client port; kiểm tra quorum bằng `stat` hoặc metrics.
- Spring Cloud Zookeeper dùng Curator service-discovery extension; kiểm tra cả provider, znode và consumer.
- Timeout phải được chọn theo network jitter và yêu cầu failover; không chọn chỉ để test nhanh.
- Một ZooKeeper node phù hợp cho lab; production cần ensemble và quorum.

Thực hành này cho thấy service discovery phụ thuộc trực tiếp vào vòng đời session của ZooKeeper. Khi hiểu rõ ranh giới giữa reconnect và session expiration, đội phát triển có thể dự đoán thời điểm instance biến mất khỏi registry, thiết kế recovery đúng cách và tránh tiếp tục sử dụng registration hoặc lock đã thuộc về một session cũ.

## Tài liệu tham khảo

- [Apache ZooKeeper — Programmer's Guide](https://zookeeper.apache.org/doc/current/zookeeperProgrammers.html)
- [Apache ZooKeeper — Administrator's Guide](https://zookeeper.apache.org/doc/current/zookeeperAdmin.html)
- [Apache ZooKeeper — Releases](https://zookeeper.apache.org/releases/)
- [Docker Official Image — ZooKeeper](https://hub.docker.com/_/zookeeper)
- [Apache Curator — Error Handling and Connection States](https://curator.apache.org/docs/errors/)
- [Apache Curator — Tech Note 12: Connection Semantics](https://curator.apache.org/docs/tech-note-12/)
- [Apache Curator — Tech Note 14: Session Timeout](https://curator.apache.org/docs/tech-note-14/)
- [Apache Curator — Releases](https://curator.apache.org/download/)
- [Spring Cloud Zookeeper — Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html)
- [Spring Cloud Zookeeper — Configuration Properties](https://docs.spring.io/spring-cloud-zookeeper/reference/appendix.html)
