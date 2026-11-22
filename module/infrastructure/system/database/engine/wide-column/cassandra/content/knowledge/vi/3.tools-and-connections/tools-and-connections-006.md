# Seed node và vai trò khởi tạo thông tin thành viên

## 1. Seed node giải quyết vấn đề gì?

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**, không có máy chủ trung tâm điều phối mọi thao tác đọc/ghi. Mỗi node cần biết những node nào cùng cluster, node nào đang hoạt động, topology datacenter/rack và các thông tin token để xác định replica của một partition. Khi một node **mới khởi động và chưa biết thành viên cluster**, nó cần một hoặc vài địa chỉ liên lạc ban đầu để tìm các node khác.

**Seed node** là node được chỉ định trong danh sách **seed/contact points cho giao thức gossip nội bộ cluster**. Node đang gia nhập sẽ tìm seed còn hoạt động để bắt đầu trao đổi thông tin thành viên. Sau khi học topology, nó tiếp tục gossip với nhiều node khác; seed không giữ vai trò độc quyền trong toàn bộ vòng đời cluster.

Với chương **Công cụ và kết nối** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, cần hiểu seed trong mối liên hệ với **gossip, bootstrap, replication, partition key, consistency, repair** và các kết nối tới Cassandra từ Java.

**Sau bài này, bạn có thể:**

1. Phân biệt seed node với coordinator, replica, seed của Java Driver và node quản trị.
2. Mô tả cách node mới khám phá thành viên qua seed và gossip, sau đó bootstrap dữ liệu.
3. Cấu hình `seed_provider` cùng địa chỉ/cổng internode phù hợp cho lab và cluster nhiều node.
4. Chọn seed dự phòng theo datacenter/rack, nhận biết sai lầm khi chỉ dùng `localhost` hay một seed.
5. Kiểm tra lỗi kết nối seed, gossip, topology và tiến trình bootstrap bằng công cụ Cassandra.

## 2. Seed không phải “master”

| Vai trò | Nhiệm vụ chính | Có đặc quyền giữ toàn bộ dữ liệu không? |
| --- | --- | --- |
| **Seed node** | Điểm liên lạc ban đầu để node khác học thông tin thành viên qua gossip; cũng tham gia gossip thông thường. | **Không**. Dữ liệu vẫn phân phối theo token và replication. |
| **Coordinator** | Node nhận một request CQL cụ thể và trao đổi với replica cần thiết. | **Không**. Bất kỳ node phù hợp nào đều có thể làm coordinator cho request. |
| **Replica** | Node lưu một bản sao dữ liệu của token range/partition theo replication strategy. | Lưu các partition mà nó chịu trách nhiệm; không phụ thuộc việc có là seed. |
| **Contact point của Java Driver** | Endpoint ứng dụng dùng để bắt đầu kết nối và khám phá cluster qua **native protocol**. | **Không**. Không cần trùng với seed của gossip. |
| **Seed của cluster mới** | Node ban đầu cho phép cluster khởi tạo rồi đón các node khác. | Không trở thành node chủ sau khi cluster hình thành. |

Cassandra không dùng seed như **leader/master** để phê duyệt mọi truy vấn. Khi Java Driver gửi `SELECT` tới một node bất kỳ, node đó có thể làm coordinator mà không cần hỏi seed. Partition key của câu truy vấn và cấu hình replication mới quyết định những replica nào được tham gia.

Seed có thể được liên lạc thường xuyên hơn trong cơ chế gossip, nên chọn những node **ổn định, có mạng tốt**. Nhưng không vì vậy mà đặt toàn bộ seed lên một máy/availability zone duy nhất.

## 3. Gossip khởi tạo và lan truyền trạng thái thành viên

### 3.1. Gossip là gì?

**Gossip** là cơ chế trao đổi trạng thái phi tập trung giữa các node Cassandra. Theo kiến trúc Cassandra, mỗi node định kỳ cập nhật heartbeat của mình và trao đổi thông tin với những peer đã biết, có thể ưu tiên thêm một seed trong những vòng trao đổi nhất định. Dữ liệu lan dần trong cluster thay vì phụ thuộc vào bảng thành viên tập trung ở một node.

Thông tin gossip thường gồm:

- **Trạng thái endpoint:** node nào được thấy là đang hoạt động hoặc không liên lạc được.
- **Heartbeat/generation/version:** giúp so sánh trạng thái mới với thông tin cũ.
- **Thông tin token/topology:** phục vụ nhận diện trách nhiệm token range, định tuyến và di chuyển dữ liệu.
- **Thông tin schema phiên bản phù hợp:** hỗ trợ các node biết khi cần đồng bộ metadata schema (chi tiết phụ thuộc phiên bản).

**Gossip và failure detection có liên quan nhưng không giống nhau.** Gossip phân phối thông tin trạng thái; mỗi node sử dụng tín hiệu và cơ chế failure detector của nó để quyết định peer có đang phản hồi hay không. Node có thể thấy peer xuống mạng mà không cần seed tuyên bố “node này đã chết”.

### 3.2. Một node mới học cluster như thế nào?

~~~mermaid
sequenceDiagram
    participant N as Node mới D
    participant S as Seed A
    participant B as Node B
    participant C as Node C
    N->>S: Kết nối internode, bắt đầu gossip
    S-->>N: Trạng thái thành viên/topology đã biết
    N->>B: Gossip trực tiếp với peer vừa khám phá
    B-->>N: Bổ sung/cập nhật thông tin thành viên
    N->>C: Gossip và xác nhận trạng thái
    Note over N,C: Nếu gia nhập như node mới: xác định token và bootstrap/streaming dữ liệu
    N->>B: Trao đổi dữ liệu internode với replica nguồn khi bootstrap
    B-->>N: Truyền dữ liệu của token range liên quan
    Note over N: Khi hoàn tất các bước cần thiết, node chuyển sang trạng thái phục vụ bình thường
~~~

Sơ đồ minh họa luồng logic. Không phải tất cả dữ liệu đều được gửi từ Seed A; **dữ liệu bootstrap được stream từ các node giữ phần dữ liệu liên quan**, dựa trên token/replication. Trình tự chính xác, điều kiện trạng thái node và cơ chế quản lý metadata có thể khác theo phiên bản Cassandra.

Quá trình có thể nhìn theo các bước:

1. Node tải cấu hình cluster, địa chỉ internode, snitch/datacenter và danh sách seed.
2. Node liên hệ seed đang sẵn sàng qua **kết nối internode** để khởi tạo trao đổi gossip.
3. Node biết thêm các endpoint và tiếp tục lan truyền trạng thái với các peer.
4. Khi gia nhập cluster đã có dữ liệu, node mới nhận token range cần phụ trách và **bootstrap/stream** dữ liệu tương ứng từ các replica hiện có.
5. Khi hoàn tất và đạt điều kiện vận hành, node được thấy là thành viên bình thường; các node tiếp tục gossip về topology.

**Khám phá thành viên ≠ sao chép dữ liệu.** Seed giúp thực hiện bước khám phá; bootstrap/streaming thuộc cơ chế dịch chuyển dữ liệu và có thể dùng các peer không phải seed.

### 3.3. Vì sao seed vẫn được dùng khi cluster đã ổn định?

Theo mô tả thuật toán gossip của Cassandra, các vòng gossip lựa chọn peer ngẫu nhiên và còn có bước liên hệ seed khi thích hợp. Seed vì thế có thể là **điểm gossip thường được chạm tới**, giúp trạng thái lan truyền trong cluster. Tuy nhiên mỗi node vẫn gossip độc lập, không có “máy chủ gossip” duy nhất.

Hệ quả:

- Mất một seed không làm toàn bộ cluster có sẵn dữ liệu lập tức ngừng đọc/ghi.
- Nếu **mọi seed mà node mới biết đều không truy cập được**, node mới có thể không khởi tạo được quá trình gia nhập.
- Nếu một seed trở nên quá tải hoặc bị cô lập mạng, khám phá/lan truyền trạng thái có thể chậm hơn, đặc biệt lúc mở rộng hay phục hồi cluster.
- Không nên nhầm việc mất seed với việc mất đúng replica cần cho một truy vấn ở consistency level đang dùng.

## 4. Cấu hình seed_provider trong cassandra.yaml

Cassandra khai báo seed bằng `seed_provider` trong `cassandra.yaml`. Với `SimpleSeedProvider`, danh sách là chuỗi các endpoint seed phân tách bằng dấu phẩy. Ví dụ cú pháp theo tài liệu Cassandra hiện hành:

~~~yaml
# Trích đoạn cassandra.yaml (minh họa, chưa phải cấu hình đầy đủ).
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "192.0.2.11:7000,192.0.2.12:7000"
~~~

Các IP `192.0.2.x` thuộc dải **dùng trong tài liệu**, phải thay bằng địa chỉ internode thực của cluster. Ở ví dụ này, Node A và B làm seed contact points, còn 7000 là **storage/internode port**, không phải cổng CQL 9042.

Một số lưu ý khi áp dụng:

- `SimpleSeedProvider` là triển khai seed provider thông dụng; một hệ thống quản lý cluster có thể sử dụng cách cấp seed khác. Cần đối chiếu cú pháp của **phiên bản Cassandra và công cụ triển khai**.
- Với các phiên bản/cấu hình hỗ trợ `host:port`, dùng **cổng internode thực**, không mặc định port là 7000 nếu đã thay `storage_port`.
- Seed có thể được khai báo bằng IP hoặc tên host được phân giải ổn định theo cơ chế được hỗ trợ. DNS không chính xác hoặc đổi IP không kiểm soát làm node không liên lạc được.
- Danh sách seed **không phải danh sách toàn bộ replica**, không quyết định replication factor, không tự phân bổ token hoặc cân bằng dữ liệu.
- Mỗi node phải có danh sách seed hữu dụng; các node **không bắt buộc phải có danh sách giống hệt nhau**, nhưng cách quản lý danh sách nhất quán giúp dễ vận hành và tránh cấu hình lệch.

### 4.1. Cổng và địa chỉ của seed thuộc mạng nào?

| Tham số/cổng | Mục đích | Dùng với seed không? |
| --- | --- | --- |
| `listen_address`, `broadcast_address` | Địa chỉ internode mà peer Cassandra sử dụng. | **Có**: seed phải tiếp cận được bằng địa chỉ mạng internode. |
| `storage_port`, mặc định `7000/TCP` | Giao tiếp node–node, gossip và các thông điệp liên quan. | **Có**: endpoint seed thường dùng cổng này. |
| `ssl_storage_port`, thường `7001/TCP` | Cổng internode TLS kiểu cũ, tùy phiên bản/cấu hình. | Chỉ khi deployment thực sự sử dụng; nhiều bản mới có thể TLS trên 7000. |
| `rpc_address`, `broadcast_rpc_address` | Địa chỉ native client mà Java Driver/cqlsh có thể kết nối. | **Không** dùng làm endpoint internode seed, trừ khi địa chỉ thực tình cờ trùng nhau và cổng vẫn đúng. |
| `native_transport_port`, mặc định `9042/TCP` | Native CQL client–node. | **Không**: đây là cổng client, không phải cổng gossip. |
| `7199/TCP` | JMX cho `nodetool` (thường gặp). | **Không**: dùng cho quản trị, không phải seed discovery. |

Với server dùng hai card mạng, địa chỉ seed phải là **internode broadcast endpoint** mà các node trong cluster truy cập được. Địa chỉ mà Java Driver sử dụng có thể khác hoàn toàn.

Ví dụ trên Node A:

~~~yaml
# Cặp địa chỉ internode cho Node A.
listen_address: 192.0.2.11
broadcast_address: 192.0.2.11
storage_port: 7000

# Native client, có thể dùng một mạng khác.
start_native_transport: true
rpc_address: 198.51.100.11
broadcast_rpc_address: 198.51.100.11
native_transport_port: 9042
~~~

Cấu hình này là **trích đoạn giải thích**, không đủ để khởi chạy một cluster thật. Cần thêm `cluster_name`, snitch, token/config datacenter, auth/TLS, tài nguyên và các thiết lập tương ứng. Đồng thời, server phải thực sự sở hữu các IP bind; không sao chép IP minh họa vào hệ thống.

## 5. Lab: tạo cluster ba node và chọn seed

Giả sử có ba node A, B, C trong cùng datacenter/rack hoặc các rack khác nhau:

| Node | Địa chỉ internode minh họa | Seed? | Vai trò khi khởi tạo |
| --- | --- | --- | --- |
| A | `192.0.2.11:7000` | Có | Node đầu tiên của cluster mới, đầu mối gossip ban đầu. |
| B | `192.0.2.12:7000` | Có, **sau khi gia nhập đúng cách** | Seed dự phòng cho những node gia nhập về sau. |
| C | `192.0.2.13:7000` | Không | Thành viên thông thường, học topology từ seed. |

~~~mermaid
flowchart TD
    D["Node mới D"] -->|"Khởi tạo gossip / 7000"| A["Seed A"]
    D -.->|"Thử seed dự phòng nếu cần"| B["Seed B"]
    A <-->|"Gossip internode"| B
    B <-->|"Gossip internode"| C["Node C"]
    C <-->|"Gossip internode"| A
    D -->|"Sau khi học topology"| C
~~~

### 5.1. Thứ tự khởi tạo khuyến nghị để hiểu cơ chế

1. **Cluster hoàn toàn mới, chưa có dữ liệu:** chọn Node A là seed ban đầu. Trên A, cấu hình cluster name, internode address và seed list thích hợp để A khởi tạo cluster. Khởi động A, xác nhận nó lên trạng thái bình thường.
2. **Gia nhập Node B:** để B tham gia như node mới thông thường và **bootstrap thành công** từ cluster hiện có. Tránh cấu hình B tự nhận vai trò seed từ trước nếu điều đó khiến B bỏ qua quá trình auto-bootstrap dữ liệu của cluster đang hoạt động.
3. Khi B đã gia nhập đúng cách, có thể chọn B làm **seed dự phòng** bằng cơ chế quản lý cấu hình tương ứng và quy trình thay đổi/khởi động của phiên bản đang dùng.
4. **Gia nhập Node C:** khai báo ít nhất một seed đang sống, ưu tiên có đường dự phòng tới A hoặc B. Cho C bootstrap, theo dõi gossip/streaming và xác nhận node đạt trạng thái normal.

**Điểm cần tránh:** theo tài liệu Cassandra, một node tự xem mình là seed có hành vi bootstrap khác với non-seed. Với **node có dữ liệu đang cần bootstrap từ cluster**, việc tự khai nó thành seed quá sớm có thể bỏ qua bước truyền dữ liệu cần thiết. Seed không phải “nhãn bật thêm cho node bất kỳ ngay trước lần khởi động đầu tiên”. Nếu triển khai cluster đã có dữ liệu, hãy theo quy trình bootstrap/replace của đúng phiên bản.

### 5.2. Theo dõi quá trình gia nhập

Trên một node vận hành có quyền, dùng:

~~~bash
# Trạng thái membership của ring (U=Up, N=Normal, J=Joining).
nodetool status

# Các endpoint và trạng thái gossip từ góc nhìn của node.
nodetool gossipinfo

# Tình trạng truyền dữ liệu khi bootstrap/streaming.
nodetool netstats

# Kiểm tra thông tin cluster và phiên bản schema được thấy.
nodetool describecluster
~~~

Trong `nodetool status`, một node có thể xuất hiện ở trạng thái `UJ` khi đang gia nhập và `UN` khi hoạt động bình thường. Đây là các thông tin hữu ích, nhưng cần xem thêm **streaming, log và các health checks** trước khi coi việc mở rộng đã hoàn tất.

Khi node nhận token range mới, các replica liên quan có thể chuyển dữ liệu sang nó. Quá trình này **không phải seed sao chép toàn bộ dữ liệu**. Nếu dòng dữ liệu lớn, xem `nodetool netstats`, disk usage, latency và các giới hạn vận hành.

## 6. Chọn seed trong môi trường nhiều datacenter

Một danh sách seed tốt ưu tiên **khả dụng và đa dạng vùng lỗi**, phù hợp mạng internode thực tế:

- Có **nhiều hơn một seed** trong production để một seed tạm dừng không chặn gia nhập node mới.
- Với multi-datacenter, thường phân bố seed theo **datacenter**, và trong mỗi datacenter nên chọn các node ở **rack/availability zone khác nhau** nếu có.
- Chọn node ổn định, có mạng/CPU phù hợp; tránh seed tập trung vào một điểm yếu về điện, mạng hoặc lịch bảo trì.
- Không cần khai báo **mọi node là seed**. Seed có thể được liên hệ nhiều hơn trong gossip; danh sách quá lớn không tự làm data availability cao hơn.
- Quản lý danh sách seed trong công cụ triển khai cấu hình để các node có ít nhất một đường khám phá còn sống; tránh chỉnh tay rời rạc làm danh sách lệch giữa môi trường.
- Khi cần thay seed, giữ **seed hiện hữu còn sẵn sàng** trong thời gian chuyển đổi và cập nhật cấu hình từng bước, theo quy trình vận hành của phiên bản Cassandra.

Ví dụ một cluster hai datacenter có seed ở mỗi nơi:

~~~yaml
# Danh sách endpoint internode ví dụ; phải thay địa chỉ thực.
seed_provider:
  - class_name: org.apache.cassandra.locator.SimpleSeedProvider
    parameters:
      - seeds: "192.0.2.11:7000,192.0.2.12:7000,198.51.100.11:7000,198.51.100.12:7000"
~~~

| Datacenter | Seed minh họa | Yêu cầu mạng |
| --- | --- | --- |
| `dc-east` | `192.0.2.11`, `192.0.2.12` | Các node trong và ngoài DC có đường internode được cho phép tới các seed cần thiết. |
| `dc-west` | `198.51.100.11`, `198.51.100.12` | Có đường internode phù hợp cùng chính sách TLS/cluster membership. |

Đây là **sơ đồ vận hành**, không phải khuyến nghị cố định “luôn bốn seed”. Số lượng và thành phần tùy kích thước cluster, topology, bảo trì và độ sẵn sàng mong muốn. Datacenter/rack còn được snitch/metadata xác định; **chỉ thêm IP seed không tạo thêm datacenter** và cũng không đổi replication của keyspace.

### 6.1. Seed và replication factor là hai cấu hình độc lập

Trong CQL, keyspace có thể khai báo số replica theo datacenter, ví dụ:

~~~sql
-- Chỉ áp dụng nếu cluster thật có datacenter mang đúng tên.
CREATE KEYSPACE IF NOT EXISTS readings_prod
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc-east': 3,
  'dc-west': 3
};
~~~

Seed list hỗ trợ **khám phá thành viên**. `NetworkTopologyStrategy` cùng token placement quyết định **replica** của mỗi partition; consistency level (ví dụ `LOCAL_QUORUM`) quyết định số replica trong datacenter được yêu cầu phản hồi khi đọc/ghi. Ba cấu hình này giải quyết các vấn đề khác nhau.

## 7. Seed khác contact point của ứng dụng Java

Hai cấu hình trông giống nhau vì đều là “điểm bắt đầu kết nối”, nhưng dùng **hai lớp giao thức khác nhau**:

~~~text
Node Cassandra mới --> seed internode:7000 --> gossip/topology --> bootstrap

Ứng dụng Java -----> native contact point:9042 --> driver discovery --> CQL coordinator
~~~

Trong Java Driver 4.x, contact points chỉ giúp ứng dụng thiết lập session và khám phá các node theo chính sách driver. Chúng **không phải** danh sách `seed_provider` mà node Cassandra sử dụng.

Ví dụ Java, giả định ứng dụng có thể kết nối đến các native endpoint và biết tên datacenter thực tế:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("db-a.example.internal", 9042))
        .addContactPoint(new InetSocketAddress("db-b.example.internal", 9042))
        .withLocalDatacenter("dc-east")
        .build()) {

    var row = session.execute(
        "SELECT cluster_name, data_center FROM system.local").one();
    if (row != null) {
        System.out.println(row.getString("cluster_name"));
    }
}
~~~

`dc-east` là ví dụ; phải thay bằng **datacenter thật**, có thể kiểm tra bằng `SELECT data_center FROM system.local;` từ cqlsh. Java Driver có thể khám phá các native endpoint khác sau khi kết nối contact point. Những endpoint này cần truy cập được từ máy ứng dụng; chúng có thể trùng IP với seed internode nếu node dùng cùng interface, nhưng **cổng và mục đích khác nhau**.

**Nếu tất cả seed tạm thời hỏng:** cluster đang chạy vẫn có thể tiếp tục phục vụ các yêu cầu CQL tùy replica/CL và trạng thái mạng. Ngược lại, nếu contact points trong ứng dụng không tới được, ứng dụng mới có thể không khởi tạo session dù ring bên trong vẫn khỏe. Hai nhóm lỗi cần kiểm tra độc lập.

## 8. Seed, token ring và thao tác dữ liệu: liên hệ qua ví dụ

Xem xét bảng các sự kiện cảm biến, thiết kế theo truy vấn “sự kiện của một thiết bị trong một ngày”:

~~~sql
-- Keyspace cho lab Cassandra đơn node, không dùng làm mẫu RF production.
CREATE KEYSPACE IF NOT EXISTS seed_discovery_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS seed_discovery_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  value double,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

INSERT INTO seed_discovery_lab.events_by_device_day
    (device_id, event_day, event_time, event_id, value)
VALUES ('sensor-01', '2026-11-21', '2026-11-21T01:00:00Z',
        11111111-1111-4111-8111-111111111111, 25.1);

SELECT event_time, value
FROM seed_discovery_lab.events_by_device_day
WHERE device_id = 'sensor-01'
  AND event_day = '2026-11-21';
~~~

Ở đây `(device_id, event_day)` là **composite partition key**. Khi có nhiều node, Cassandra tính token để chọn replica theo **token ring và replication**. Seed chỉ giúp node gia nhập **học thông tin ring**, không quyết định rằng “mọi dữ liệu của sensor-01 sẽ được lưu ở seed”.

Với RF = 1 của lab, không thể thực hành failover/quorum nhiều replica. Để đánh giá `LOCAL_QUORUM` hoặc tác động lỗi internode, cần cluster nhiều node và replication factor thực tế, theo datacenter. Việc tăng số seed **không** tăng số replica.

## 9. Kiểm tra seed khi node không gia nhập cluster

### 9.1. Trước hết, xác định đúng địa chỉ và cổng

Từ **máy của node đang muốn gia nhập**, thử kết nối TCP đến **internode endpoint** của seed:

~~~bash
# IP thuộc dải ví dụ; thay bằng IP seed thực trên cổng storage_port.
nc -vz 192.0.2.11 7000
nc -vz 192.0.2.12 7000
~~~

Trên Windows có PowerShell:

~~~powershell
Test-NetConnection -ComputerName 192.0.2.11 -Port 7000
~~~

Nếu network dùng TLS hoặc port khác, phải kiểm tra đúng cấu hình đó. **TCP mở chỉ chứng minh lớp mạng cơ bản**, không bảo đảm gossip handshake, cluster name, authentication internode hoặc snitch/config đều hợp lệ.

### 9.2. Kiểm tra trên seed và node mới

~~~bash
# Chạy trên các node có quyền quản trị Cassandra.
nodetool status
nodetool gossipinfo
nodetool describecluster
nodetool netstats
~~~

Đối chiếu các điểm:

1. Seed được khai báo trong `seed_provider` đúng IP/DNS và **storage_port**, không phải `9042`.
2. Seed thực sự đang hoạt động và bind/listen trên địa chỉ internode có thể truy cập.
3. `cluster_name` và cấu hình datacenter/rack/snitch phù hợp để gia nhập cluster dự kiến.
4. `listen_address`/`broadcast_address` của node mới và seed đều đúng; nếu có NAT, đường mạng hai chiều phải được thiết kế có chủ đích.
5. Firewall/security group cho phép kết nối internode cần thiết, TLS server-to-server thống nhất.
6. Các bản Cassandra đang dùng có cấu hình tương thích cho giai đoạn rolling upgrade; kiểm tra log nếu gossip hoặc streaming bị từ chối.
7. Nếu gossip đã thấy node nhưng bootstrap chưa hoàn tất, tập trung xem **streaming, disk, token và log**, không chỉ tiếp tục đổi seed.

`nodetool status` là quan sát ring từ góc nhìn node được hỏi, không phải phép đo đầy đủ mọi đường mạng. `nodetool gossipinfo` hỗ trợ xem trạng thái endpoint trong gossip; `nodetool netstats` giúp thấy tiến độ streaming. Log của node mới và seed thường cung cấp chi tiết nguyên nhân hơn một dòng trạng thái.

### 9.3. Các lỗi phổ biến

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Cluster nhiều node vẫn để `seeds: "127.0.0.1:7000"` ở mọi node | Mỗi node chỉ liên hệ loopback của chính nó. | Cấu hình endpoint internode thực, có ít nhất một seed còn sống và có tuyến mạng. |
| Node mới không tới được seed nào | Seed down, DNS sai, firewall, port/TLS sai hoặc route thiếu. | Thử kết nối từ **chính node mới** tới từng seed và đối chiếu cấu hình. |
| TCP 7000 được nhưng gossip không học peer | Cluster name/snitch/TLS internode không khớp, lỗi handshake hoặc bản Cassandra không tương thích. | Kiểm tra log, `nodetool gossipinfo` và cấu hình tương ứng. |
| Node mới tự khai là seed, bootstrap không như dự kiến | Sai quy trình thêm seed trước khi node nhận token/data. | Làm theo quy trình thêm node thông thường, xác nhận bootstrap rồi mới cân nhắc thay seed list. |
| Một seed ngừng hoạt động nhưng truy vấn CQL vẫn chạy | Seed không phải coordinator bắt buộc hoặc master. | Kiểm tra replica/consistency và khôi phục dự phòng seed theo kế hoạch. |
| Seed bị hỏng khiến không thêm được node mới | Không còn seed nào mà node mới liên hệ được. | Khôi phục seed hoặc cấu hình seed contact points đang sống theo quy trình cluster. |
| Java Driver kết nối lỗi `9042` dù seed `7000` thông | Native transport/rpc address, TLS client hoặc auth không đúng. | Kiểm tra `native_transport_port`, `broadcast_rpc_address`, driver contact points. |
| `nodetool status` hiển thị `UJ` lâu | Node đã khám phá cluster nhưng bootstrap/streaming chậm hoặc lỗi. | Xem `nodetool netstats`, logs, disk, mạng internode và các replica nguồn. |
| Một datacenter không nhìn thấy node DC khác | Mạng xuyên DC, firewall, seed topology hoặc gossip/sự cố phiên bản. | Kiểm tra internode endpoints giữa DC, cấu hình snitch/datacenter và logs. |

### 9.4. Khi thay hoặc loại bỏ seed

Không dừng tất cả seed cùng lúc để “làm sạch danh sách”. Với hệ thống đang hoạt động:

1. Chọn seed dự phòng **đã là thành viên bình thường** của cluster, ở vùng lỗi phù hợp.
2. Cập nhật danh sách seed có chủ đích bằng công cụ quản lý cấu hình và phương thức áp dụng thay đổi phù hợp phiên bản.
3. Duy trì những seed cũ còn hoạt động trong giai đoạn chuyển đổi; kiểm tra khả năng node mới liên hệ ít nhất một seed tốt.
4. Chỉ đưa seed cũ khỏi cấu hình và quy trình bảo trì khi các node đã nhận thay đổi và topology ổn định.

Nếu cần **thay hẳn node** đang mang vai trò seed, còn phải xử lý dữ liệu/token và ring membership theo quy trình **replace/decommission/bootstrap**. Việc xóa IP seed khỏi YAML không xóa node khỏi ring; việc thay node lưu dữ liệu cũng không chỉ là đổi danh sách seed.

## 10. Bài tự thực hành

1. Phác họa đường đi **Node D mới → Seed A → các peer B/C → bootstrap data**. Giải thích vì sao dữ liệu bootstrap không nhất thiết được truyền từ seed.
2. Trong cluster ba node, hãy chọn hai seed có mạng ổn định và viết trích đoạn `seed_provider`. Chỉ rõ cổng nào là internode và cổng nào dành cho `cqlsh`/Java Driver.
3. Giả sử một node đặt seed là `127.0.0.1` nhưng chạy trên máy khác với seed thật. Dự đoán vấn đề và đề xuất cấu hình sửa.
4. Giả sử Seed A ngừng hoạt động nhưng Node B là seed dự phòng và đang sống. Phân biệt tác động đối với (a) truy vấn CQL của client đã kết nối, (b) một node mới chuẩn bị gia nhập.
5. Chạy `nodetool status`, `nodetool gossipinfo` và `nodetool netstats` trong lab phù hợp. Chỉ ra những thông tin giúp xác định trạng thái thành viên và bootstrap.
6. Mô tả vì sao không nên tự chỉ định node mới là seed trước khi nó bootstrap vào cluster đã có dữ liệu.
7. Với hai datacenter, đề xuất cách phân bổ seed theo rack/DC để tránh một điểm lỗi chung. Giải thích vì sao không cần biến toàn bộ node thành seed.
8. Dùng Java Driver kết nối native contact point `9042` và giải thích vì sao contact point của Java không bắt buộc là seed `7000`.
9. Với RF = 3 trong một datacenter, tính số replica tối thiểu để đạt `LOCAL_QUORUM`. Giải thích tại sao đổi danh sách seed không thay đổi đáp án.

**Tiêu chí hoàn thành:** phân biệt được seed, coordinator và replica; mô tả được gossip và bootstrap; viết được seed configuration đúng mạng internode; nhận diện được lỗi seed không tới được; và giải thích chính xác vai trò độc lập của seed list so với replication/consistency và Java client.

## Tài liệu tham khảo

- [Apache Cassandra — Dynamo architecture: Gossip, Seeds and Ring Membership](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): thuật toán gossip và vai trò seed trong khám phá thành viên.
- [Apache Cassandra — cassandra.yaml configuration](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html): `seed_provider`, `SimpleSeedProvider`, `listen_address`, `broadcast_address` và cổng internode.
- [Apache Cassandra — Frequently Asked Questions](https://cassandra.apache.org/doc/stable/cassandra/overview/faq/index.html): seed, vai trò khi khởi động và khả năng hoạt động khi một seed hỏng.
- [Apache Cassandra — Adding, replacing, moving and removing nodes](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/topo_changes.html): bootstrap, token allocation và quan sát streaming.
- [Apache Cassandra — Glossary: Seed](https://cassandra.apache.org/_/glossary.html): định nghĩa ngắn gọn về seed node.
- [Apache Cassandra Java Driver 4.x](https://docs.datastax.com/en/developer/java-driver/4.17/): native client contact points và cách khởi tạo `CqlSession`.
