# Thử khởi động lại, mất một nút và đối chiếu dữ liệu

## 1. Mục tiêu và giới hạn thí nghiệm

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**: một **partition key** được ánh xạ tới token, và keyspace replication strategy xác định các **replica** sẽ giữ dữ liệu. Mỗi yêu cầu đọc/ghi gửi tới một **coordinator**; **consistency level (CL)** quy định số replica phải phản hồi trước khi client nhận kết quả. Vì thế, một node tắt đi không nhất thiết làm cả cluster dừng, nhưng không phải mọi mức nhất quán đều tiếp tục hoạt động.

Bài này đưa người học từ môi trường đã biết sử dụng CQL sang **quan sát có kiểm soát**: ghi dữ liệu khi ba node khỏe, lần lượt dừng/khởi động lại một node, ghi thêm khi một replica vắng mặt, đối chiếu kết quả sau khi node quay lại và tìm hiểu vai trò của **hints, read repair, anti-entropy repair**.

Kết thúc bài, bạn có thể:

1. Dựng cluster thử nghiệm **3 node, một datacenter, RF=3**, dùng Docker network và volume **riêng cho từng node**.
2. Kiểm tra cùng một ring từ ba góc nhìn bằng `nodetool status` và `system.local/system.peers_v2`.
3. Lập dữ liệu baseline rồi so sánh đọc/ghi với `LOCAL_ONE`, `LOCAL_QUORUM` và `ALL` khi **một node tạm dừng**.
4. Phân biệt **dừng bình thường** và **crash mô phỏng**, nhận biết `UN`, `DN`, native transport và khả năng phục vụ CQL.
5. Phân tích vì sao câu lệnh báo timeout/thất bại **không luôn đồng nghĩa không có replica nào đã nhận write**.
6. Xem bằng chứng hints/streaming/repair; biết vì sao một câu SELECT từ node vừa trở lại **chưa chứng minh** dữ liệu đã được lưu tại replica cục bộ đó.
7. Khôi phục cả ba node, đối chiếu bảng mẫu, ghi biên bản và dọn container **mà không xóa nhầm dữ liệu**.

> **An toàn:** chỉ thực hiện trên **lab cô lập, không có dữ liệu thật**. Không chạy các lệnh dừng/kill/repair dưới đây trên production, cluster dùng chung hoặc node đang phục vụ người khác. Ba container trong cùng một laptop là ba process Cassandra nhưng **không phải ba máy/failure domain độc lập**.

## 2. Mô hình cần hiểu trước khi thực hành

### 2.1. Ba node, một datacenter và ba bản sao

```text
                      Client (cqlsh / Java Driver)
                         ┌────────────┐
                         │ Coordinator│
                         └─────┬──────┘
                               │
     Network: pe010-net        │            Cluster: pe010-lab
                ┌──────────────┼─────────────┐
                │              │             │
         pe010-n1         pe010-n2       pe010-n3
         dc1/rack1        dc1/rack2      dc1/rack3
         volume_n1        volume_n2      volume_n3
                │              │             │
         Replica 1        Replica 2      Replica 3
                └────────── RF=3 ────────────┘

Local datacenter = dc1; LOCAL_QUORUM = floor(3/2)+1 = 2.
```

Trong lab này, mỗi partition của keyspace `pe010_lab` có **ba replica** ở ba node (sau khi cả ba hoàn thành bootstrap). Bảng dùng **partition key `device_id`**, vì vậy một query có `WHERE device_id = ...` có thể được coordinator định tuyến tới đúng replica.

**Rack1/rack2/rack3 chỉ là nhãn logic.** Vì tất cả chạy trên một Docker host, mất host/ổ đĩa/vùng điện chung sẽ làm mất cả ba node. Không dùng kết quả lab này làm chứng nhận disaster recovery hoặc HA production.

### 2.2. RF khác với consistency level

| CL trong `dc1` có RF=3 | Số replica cần phản hồi | Khi cả ba khỏe | Khi n3 down, n1/n2 khỏe |
|---|---:|---|---|
| `LOCAL_ONE` | 1 | Có thể thành công | **Có thể thành công** |
| `LOCAL_QUORUM` | 2 | Có thể thành công | **Có thể thành công** |
| `ALL` | 3 | Có thể thành công | **Không đủ 3 replica**, thường báo unavailable hoặc timeout |

Với **read và write ở `LOCAL_QUORUM`**, hai tập replica phản hồi trong cùng DC với RF=3 phải giao nhau về mặt tập hợp vì **2 + 2 > 3**. Điều đó hỗ trợ quan sát dữ liệu sau ghi dưới các điều kiện thông thường. Tuy nhiên Cassandra dùng **mutation timestamp** để giải quyết xung đột; clock skew, client-supplied timestamp, tombstone, timeout và lỗi thực tế vẫn phải được xét riêng. CL không phải giao dịch SQL tuần tự tuyệt đối và cũng không thay thế repair.

`LOCAL_ONE` ít yêu cầu phản hồi hơn nên có thể trả một bản sao **chưa kịp nhận mutation**. `ALL` chờ cả ba và hy sinh tính sẵn sàng khi một replica vắng mặt. `ANY` chỉ dành cho **write** và có thể nhận một hint thay cho ack của replica; vì không đáp ứng mục tiêu kiểm thử dữ liệu trực tiếp, bài này **không dùng `ANY`**.

### 2.3. Các cấp độ kiểm chứng khác nhau

| Lớp quan sát | Công cụ | Kết luận được | Không thể kết luận chỉ từ đó |
|---|---|---|---|
| Container/process | `docker ps -a`, `docker inspect` | Process còn chạy hay đã dừng | CQL/ring đã sẵn sàng |
| Gossip/ring | `nodetool status` | Các node được nhìn là `UN`/`DN`, token/rack | Mọi replica chắc chắn có cùng dữ liệu |
| Native transport | `nodetool statusbinary` | Server nhận CQL qua binary protocol | Read/write của keyspace chắc chắn thành công |
| Metadata | `system.local`, `system.peers_v2` | Cluster/DC/rack/host ID, peer được biết | Client từ mạng khác sẽ kết nối được mọi peer |
| CQL | SELECT/INSERT với CL đã chọn | Request thật đã phản hồi hoặc thất bại | Một SELECT từ n3 chắc chắn đọc SSTable **cục bộ** của n3 |
| Hints/repair | `listpendinghints`, log, metrics, `nodetool repair` | Bằng chứng công việc đồng bộ đang diễn ra/đã hoàn tất | Một lần chạy query tự động chứng minh mọi replica hoàn toàn giống nhau |

## 3. Điều kiện thực hành

### 3.1. Tài nguyên, mạng và phiên bản

Ví dụ sử dụng **Cassandra 5.0.9**, Docker Engine/Docker Desktop chạy Linux containers, **ba named volumes** và một Docker user-defined bridge network. Để ba JVM hoạt động dễ dàng, host từ khoảng **24 GiB RAM** là mức **tham khảo thuận tiện cho lab**, mỗi container giới hạn 4 GiB và JVM heap 2 GiB. Nếu dùng host ít RAM hơn, phải cân nhắc giảm tải hoặc cấp tài nguyên phù hợp; **đừng dùng cấu hình thiếu RAM để suy đoán hiệu năng production**.

Trong ví dụ, **không publish cổng CQL ra host**. Các lệnh `cqlsh` và `nodetool` chạy qua `docker exec` **bên trong node**. Điều này tránh nhầm `localhost` của host với IP container, đồng thời không vô ý mở cluster chưa bật authentication/TLS ra mạng ngoài.

Các cổng quan trọng **bên trong network**:

- `7000/TCP`: internode/gossip/streaming (nếu không đổi port/TLS cấu hình).
- `9042/TCP`: native CQL cho `cqlsh` và Java Driver.
- `7199/TCP`: JMX của `nodetool`, không cần publish lên host.

Kiểm tra trước:

```bash
docker version
docker ps -a
docker network ls
docker volume ls
```

Các tên `pe010-net`, `pe010-n1`, `pe010-n2`, `pe010-n3` và ba volume bên dưới chỉ dành cho bài này. Nếu chúng **đã tồn tại**, phải kiểm tra nguồn gốc/dữ liệu, **không xóa hoặc ghi đè** một bài lab khác.

### 3.2. Chuẩn bị network và ba volume độc lập

Chạy trên host có Docker CLI, có thể dùng Bash hoặc PowerShell:

```bash
docker pull cassandra:5.0.9
docker network create pe010-net
docker volume create pe010_data_n1
docker volume create pe010_data_n2
docker volume create pe010_data_n3
```

**Không dùng chung volume**: mỗi node có system tables, host ID, tokens, commit log và SSTables riêng. Cassandra nhân dữ liệu giữa các node **qua internode protocol**, không phải bằng cách nhiều Cassandra process cùng ghi một thư mục.

Volume làm dữ liệu sống qua `docker stop/start` và `docker rm` nếu volume còn tồn tại. Nhưng tái tạo container nhiều node với **IP broadcast khác** có thể đòi hỏi quy trình đổi địa chỉ/thay node; vì vậy bài này dùng **stop/start chính container cũ**, không dùng xóa/tạo lại node có dữ liệu để giả lập lỗi.

## 4. Khởi tạo ba node theo thứ tự

### 4.1. Node n1: seed ban đầu

```bash
docker run -d --name pe010-n1 --network pe010-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=pe010-lab -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack1 -v pe010_data_n1:/var/lib/cassandra cassandra:5.0.9
```

Đợi n1 báo `UN` và CQL mở:

```bash
docker logs --tail 80 pe010-n1
docker exec pe010-n1 nodetool status
docker exec pe010-n1 nodetool statusbinary
docker exec pe010-n1 cqlsh -e "SELECT cluster_name, data_center, rack, release_version FROM system.local;"
```

Kỳ vọng: `pe010-lab`, `dc1/rack1`, `status=UN`, `statusbinary=running`. Docker `Up` **không đủ** để kết luận Cassandra sẵn sàng. Nếu JMX/CQL chưa kết nối được, xem log và chờ theo trạng thái thực.

### 4.2. Node n2: join qua seed n1

Chỉ chạy khi n1 đã sẵn sàng:

```bash
docker run -d --name pe010-n2 --network pe010-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=pe010-lab -e CASSANDRA_SEEDS=pe010-n1 -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack2 -v pe010_data_n2:/var/lib/cassandra cassandra:5.0.9
```

```bash
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
docker logs --tail 80 pe010-n2
```

Kỳ vọng sau khi bootstrap hoàn tất là **hai dòng `UN`** trong các góc nhìn n1 và n2. `CASSANDRA_SEEDS` là cấu hình discovery/gossip ban đầu, **không** khiến n1 thành master/leader.

### 4.3. Node n3: hoàn thành cụm

Chỉ chạy khi n1 và n2 đều `UN`:

```bash
docker run -d --name pe010-n3 --network pe010-net --memory=4g --memory-swap=4g -e MAX_HEAP_SIZE=2G -e CASSANDRA_CLUSTER_NAME=pe010-lab -e CASSANDRA_SEEDS=pe010-n1 -e CASSANDRA_ENDPOINT_SNITCH=GossipingPropertyFileSnitch -e CASSANDRA_DC=dc1 -e CASSANDRA_RACK=rack3 -v pe010_data_n3:/var/lib/cassandra cassandra:5.0.9
```

```bash
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
docker exec pe010-n3 nodetool status
docker exec pe010-n1 nodetool describecluster
```

Chỉ chuyển sang bước tạo keyspace khi **từng góc nhìn ring đều thấy ba `UN`** cùng datacenter `dc1` và ba rack logic. Kết quả bootstrap xuất hiện **bất đồng bộ**, nên không kết luận thất bại nếu trong vài giây đầu một node còn `UJ` (*Up/Joining*).

Để kiểm tra ba định danh node **không trùng**:

```bash
docker exec pe010-n1 cqlsh -e "SELECT cluster_name, data_center, rack, host_id FROM system.local;"
docker exec pe010-n2 cqlsh -e "SELECT cluster_name, data_center, rack, host_id FROM system.local;"
docker exec pe010-n3 cqlsh -e "SELECT cluster_name, data_center, rack, host_id FROM system.local;"
docker exec pe010-n1 cqlsh -e "SELECT peer, peer_port, data_center, rack, host_id FROM system.peers_v2;"
```

Một node khỏe thường biết **hai peer còn lại** trong `system.peers_v2`. Peer metadata và `nodetool status` là hai nguồn đối chiếu; nếu một node chỉ thấy ring của riêng mình thì **không** tiến hành bài thử mất node.

## 5. Dữ liệu baseline trước khi dừng node

### 5.1. Keyspace RF=3 và bảng theo partition key

Mở `cqlsh` tương tác tại n1:

```bash
docker exec -it pe010-n1 cqlsh
```

Trong `cqlsh>`, chạy:

```sql
SELECT cluster_name, data_center FROM system.local WHERE key = 'local';

CREATE KEYSPACE IF NOT EXISTS pe010_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS pe010_lab.events_by_device (
  device_id text,
  event_id text,
  event_time timestamp,
  payload text,
  PRIMARY KEY ((device_id), event_id)
);

DESCRIBE KEYSPACE pe010_lab;
```

Ở đây `device_id` là **partition key**; `event_id` là **clustering key**. Tất cả event có cùng `device_id` nằm trong cùng logical partition, được ánh xạ tới ba replica của keyspace. Các `event_id` cố định giúp lần sau đối chiếu đúng row, không lẫn với việc tạo UUID mới.

**Chú ý:** `CREATE KEYSPACE IF NOT EXISTS` không sửa RF nếu keyspace đã tồn tại. Sau khi tạo, kiểm tra replication thực tế qua `DESCRIBE KEYSPACE` hoặc:

```sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'pe010_lab';
```

Nếu datacenter thực tế không phải `dc1` hoặc cluster chưa có ba node, không tiếp tục dùng nguyên map ví dụ này. **RF=3 không tạo ra ba replica** khi chưa có ba node thực sự.

### 5.2. Ghi baseline khi cả ba node đang khỏe

Trong `cqlsh` của n1:

```sql
CONSISTENCY ALL;

INSERT INTO pe010_lab.events_by_device
  (device_id, event_id, event_time, payload)
VALUES
  ('device-010', 'a-baseline',
   '2026-11-21T08:00:00Z', 'written-while-all-up');

SELECT device_id, event_id, event_time, payload,
       WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Với RF=3, write ở `ALL` thành công nghĩa là **cả ba replica phải phản hồi** theo CL. Đó là baseline mạnh cho bài thử; nó không có nghĩa đã có backup hoặc dữ liệu được kiểm tra bit-for-bit trên ba đĩa.

Lưu ý: `WRITETIME(payload)` trả mutation timestamp của cell theo **microsecond từ Unix epoch**, khác với cột nghiệp vụ `event_time`. Nếu chạy lại script, thời điểm ghi cell có thể thay đổi; để so sánh các lần chạy, hãy ghi cả `event_id` và `payload`.

### 5.3. Đối chiếu với địa chỉ replica

Trên host:

```bash
docker exec pe010-n1 nodetool getendpoints pe010_lab events_by_device device-010
docker exec pe010-n1 nodetool tablestats pe010_lab
docker exec pe010-n1 nodetool status
```

`nodetool getendpoints` liệt kê những endpoint chịu trách nhiệm cho partition key `device-010`. Với ba node khỏe, RF=3 và cùng DC, kỳ vọng thấy **ba địa chỉ**. Lệnh này cho biết **replica placement**, không đọc từng file SSTable để so hash dữ liệu.

Trên n2, thử đọc cùng partition bằng `cqlsh`:

```bash
docker exec pe010-n2 cqlsh -e "SELECT device_id, event_id, payload FROM pe010_lab.events_by_device WHERE device_id='device-010';"
```

Lệnh một lần `-e` ở đây dùng consistency mặc định của cqlsh; nếu muốn xác minh `ALL` hay `LOCAL_QUORUM`, phải đặt `CONSISTENCY ...` trong **chính phiên cqlsh** đang thực hiện SELECT. Node n2 đóng vai coordinator, không nhất thiết lấy dữ liệu chỉ từ đĩa n2.

## 6. Thí nghiệm A: dừng bình thường một node và tiếp tục đọc/ghi

### 6.1. Dừng n3 bằng Docker (có thời gian shutdown)

Trước khi thao tác, bảo đảm đã có dữ liệu baseline và cả ba node đang `UN`. Đóng hoặc để riêng phiên `cqlsh` của n1, sau đó trên host:

```bash
docker stop --time 120 pe010-n3
docker ps -a --filter name=pe010-n3
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
```

`docker stop` gửi tín hiệu dừng bình thường và cho process một khoảng thời gian trước khi buộc dừng. **Nó không cam kết shutdown sạch trong mọi trường hợp**: nếu process không thoát kịp thời hạn, Docker có thể kết thúc cưỡng bức. Nếu muốn bảo trì có kế hoạch trong Cassandra thật, phải theo quy trình rolling operation và có thể sử dụng `nodetool drain` để ngừng nhận write/flush trước khi dừng; `drain` không phải công cụ kiểm thử “node chết bất ngờ”.

Sau khi failure detector/gossip cập nhật, hai node còn sống thường thấy n3 thành **`DN`** (*Down/Normal*). Ngay lúc vừa dừng, trạng thái có thể chưa cập nhật; **không đoán một mốc thời gian cố định**. `system.peers_v2` vẫn có thể giữ metadata của n3: **DN không có nghĩa peer bị xóa khỏi cluster**.

### 6.2. Kiểm tra read với LOCAL_QUORUM khi n3 down

Ở terminal host, mở `cqlsh` của n1:

```bash
docker exec -it pe010-n1 cqlsh
```

Trong `cqlsh`:

```sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, payload, WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Kỳ vọng còn đọc được row `a-baseline`: hai replica n1/n2 đang khỏe đáp ứng **2/3**. Nếu query thất bại vì timeout, CPU/đĩa, network hoặc các node còn lại không khỏe, phải thu log và số liệu trước khi kết luận Cassandra không hỗ trợ quorum.

### 6.3. Ghi một row **mới** trong khi n3 vắng mặt

Giữ `CONSISTENCY LOCAL_QUORUM` ở phiên n1, rồi chạy:

```sql
INSERT INTO pe010_lab.events_by_device
  (device_id, event_id, event_time, payload)
VALUES
  ('device-010', 'b-while-n3-down',
   '2026-11-21T08:05:00Z', 'accepted-by-quorum');

SELECT event_id, event_time, payload
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Khi n1/n2 là hai replica khỏe, write `LOCAL_QUORUM` có thể thành công mặc dù n3 không nhận mutation trực tiếp lúc đó. Đây là minh họa **tính sẵn sàng theo CL**. Cassandra có thể giữ **hint** dành cho replica down, nhưng hint là **best effort**; không dùng write success để khẳng định hint chắc chắn đã được lưu và phát lại.

Dùng **row có `event_id` riêng** thay vì update row baseline là có chủ đích: nếu một thử nghiệm thất bại, có thể quan sát từng row mà không nhầm lỗi với last-write-wins khi hai mutation cùng cell tranh timestamp.

### 6.4. Kiểm tra ALL khi còn thiếu một replica — chỉ đọc

Trong cùng phiên n1:

```sql
CONSISTENCY ALL;

SELECT event_id, payload
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Khi n3 vẫn down, RF=3 và một replica vắng mặt, **ALL không đủ ba phản hồi**. Kỳ vọng lệnh báo lỗi như `Unavailable` hoặc timeout, tùy failure detector, thời điểm thử và trạng thái các node. Đây **không phải lỗi schema**: nó thể hiện CL yêu cầu cao hơn số replica đang sẵn sàng.

**Vì sao thử SELECT thay vì INSERT ở bước dự kiến thất bại?** Một write bị timeout có thể đã đến **một hoặc nhiều replica** dù client nhận lỗi. Do đó không thể kết luận “write thất bại nên dữ liệu chắc chắn chưa tồn tại”, rồi lặp một thao tác không idempotent mà không kiểm tra. Trong hệ thống thật, retry cần có key ổn định/idempotency và ứng dụng phải hiểu hệ quả của CL/timeout.

Trước khi tiếp tục hoặc quay lại thử CQL khác, đặt lại CL:

```sql
CONSISTENCY LOCAL_QUORUM;
```

## 7. Thí nghiệm B: khởi động lại n3 và đối chiếu dữ liệu

### 7.1. Khôi phục đúng container cũ và đúng volume

Trên host:

```bash
docker start pe010-n3
docker ps --filter name=pe010-n3
docker logs --tail 100 pe010-n3
docker exec pe010-n3 nodetool status
docker exec pe010-n3 nodetool statusbinary
```

Sau restart, node cần đọc lại dữ liệu trên volume `pe010_data_n3`, khởi động dịch vụ và tham gia ring. `docker start` thành công **chưa có nghĩa** node đã `UN` hoặc nhận CQL. Đợi tới khi n1, n2 và n3 đều thấy **ba dòng `UN`**:

```bash
docker exec pe010-n1 nodetool status
docker exec pe010-n2 nodetool status
docker exec pe010-n3 nodetool status
docker exec pe010-n3 cqlsh -e "SELECT host_id, cluster_name, data_center FROM system.local;"
```

Nếu n3 vẫn `UJ` hoặc `DN`, đọc `docker logs`, `nodetool netstats` từ node sống và kiểm tra CPU/đĩa trước khi tiếp tục.

### 7.2. Đối chiếu hai row từ các coordinator khác nhau

Trên n1 mở `cqlsh`, chọn `LOCAL_QUORUM`:

```bash
docker exec -it pe010-n1 cqlsh
```

```sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, event_time, payload, WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Đọc tương tự từ n3 (mở một phiên `cqlsh` **khác**):

```bash
docker exec -it pe010-n3 cqlsh
```

```sql
CONSISTENCY LOCAL_QUORUM;

SELECT event_id, event_time, payload, WRITETIME(payload)
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Kỳ vọng hai truy vấn đều nhìn thấy:

| `event_id` | Thời điểm nghiệp vụ | `payload` | Giai đoạn ghi |
|---|---|---|---|
| `a-baseline` | 2026-11-21 08:00 UTC | `written-while-all-up` | Trước khi dừng n3, CL=ALL |
| `b-while-n3-down` | 2026-11-21 08:05 UTC | `accepted-by-quorum` | Khi n3 down, CL=LOCAL_QUORUM |

**Không kết luận “n3 đã có dữ liệu trên đĩa” chỉ vì kết nối cqlsh đến n3 và SELECT thành công.** Node n3 đóng vai coordinator; `LOCAL_QUORUM` có thể nhận phản hồi từ **n1 và n2**, nơi row được ghi trong lúc n3 down. Một lần đọc ở CL=ALL có thể kích hoạt cơ chế xử lý/đồng bộ bản sao; vì vậy đọc thành công sau restart cũng **không riêng lẻ chứng minh hints đã phát lại**.

Nếu có sai khác về `WRITETIME` giữa các lần chạy lại script, nhớ rằng mỗi INSERT có thể tạo mutation timestamp mới. Giữ khóa `event_id` và payload cố định để phân biệt **nội dung nghiệp vụ** với **thời điểm ghi cell**.

### 7.3. Khi nào đọc ở ALL để xác nhận cả ba?

Khi cả ba node đã `UN`, trong một phiên n1:

```sql
CONSISTENCY ALL;

SELECT event_id, payload
FROM pe010_lab.events_by_device
WHERE device_id = 'device-010';
```

Kết quả thành công ở `ALL` yêu cầu ba replica đáp ứng truy vấn theo semantics của Cassandra, có thể bao gồm quá trình read repair. Nó là phép kiểm **mạnh hơn về khả năng phục vụ read với CL=ALL**, nhưng **không phải công cụ kiểm toán toàn bộ SSTable** hoặc bảo đảm các token range khác đều đồng bộ.

Nếu vẫn thất bại mặc dù tất cả node `UN`, thu log/metrics, `nodetool tpstats`, `nodetool netstats`, latency và ổ đĩa; có thể còn timeout, inconsistency/repair backlog hoặc lỗi hệ thống khác.

## 8. Hints, read repair và anti-entropy repair: đối chiếu đúng bằng chứng

### 8.1. Hinted handoff sau một node bị dừng

Khi coordinator xử lý write hướng tới một replica tạm vắng mặt, nó **có thể** ghi một **hint** vào thư mục `hints/` của **coordinator**, giữ mutation và timestamp ban đầu, rồi phát lại khi replica quay lại. Hints được bật mặc định theo cấu hình phổ biến, nhưng bị giới hạn bởi thời gian node vắng mặt (`max_hint_window`, mặc định khoảng **3 giờ**), nguồn lực và điều kiện giao nhận.

**Hints là best effort, không thay thế repair.** Bài này không thay đổi cửa sổ hints, không tắt repair và không ép phát lại để “làm đẹp” kết quả.

Trước/sau restart, có thể quan sát trên node còn sống:

```bash
docker exec pe010-n1 nodetool statushandoff
docker exec pe010-n1 nodetool listpendinghints
docker exec pe010-n2 nodetool listpendinghints
docker exec pe010-n1 sh -c "ls -la /var/lib/cassandra/hints"
docker logs --tail 100 pe010-n1
```

- `statushandoff` cho biết trạng thái cơ chế handoff trên **node đang hỏi**, **không** đếm chính xác các hints.
- `listpendinghints` cho biết hints đang chờ; kết quả có thể **rỗng**, vì hint chưa flush, đã phát lại, không được tạo trong điều kiện thử hoặc request đi qua coordinator khác.
- Dữ liệu hint nằm trên **node giữ hint**, không mặc nhiên trên replica bị down.
- Nếu test chỉ ghi một vài mutation, không nhất thiết nhìn thấy file hint lớn. Muốn kiểm chứng hinted handoff cần kết hợp **metrics, log, thời gian handoff và công cụ quan sát thực tế**, không chỉ `ls hints/`.

Không dùng `nodetool truncatehints` khi cần đồng bộ lại replica: lệnh đó **có thể vứt bỏ mutation đang chờ**. Không đổi `max_hint_window` hay throttle trên môi trường khác chỉ để sao chép đúng kết quả lab.

### 8.2. Vì sao repair vẫn cần thiết?

Replica down có thể **bỏ lỡ write**, hints hết thời hạn, mất trong lúc lỗi, hoặc không được tạo. Cassandra dùng **anti-entropy repair** để so sánh dữ liệu giữa các replica cùng token range (ví dụ bằng Merkle trees) và streaming phần thiếu/sai khác. Repair cũng cần được lên lịch trong production, đặc biệt liên quan tombstone/`gc_grace_seconds` và xóa dữ liệu.

Đừng coi một lần SELECT từ n3 thành công là bằng chứng repair đã chạy. **Read repair** có thể hỗ trợ một số tình huống đọc, nhưng không duyệt toàn bộ partition/token range chưa được đọc. **Full/incremental repair** là công việc quản trị riêng, có chi phí CPU/đĩa/network.

Nếu muốn làm **bài mở rộng và chỉ khi cả ba node đã `UN`**, có thể thử **full repair giới hạn một keyspace/bảng của lab**:

```bash
docker exec pe010-n1 nodetool repair --full pe010_lab events_by_device
```

Lệnh này có thể tiêu thụ I/O/CPU và cần đĩa trống; nó **không được dùng thường xuyên như một readiness check**. Repair trên một node xử lý **token ranges của node đó** theo tùy chọn hiện hành, không mặc nhiên tương đương một chiến dịch full-cluster repair đã lên kế hoạch. Để sửa toàn cluster, tài liệu Apache hướng dẫn thực hiện repair các **primary ranges** (`-pr`) trên từng node/datacenter thích hợp theo quy trình.

Theo dõi:

```bash
docker exec pe010-n1 nodetool netstats
docker exec pe010-n1 nodetool tpstats
docker exec pe010-n1 nodetool compactionstats
docker logs --tail 100 pe010-n1
```

Kết quả `repair` thành công trên dữ liệu mẫu là **bằng chứng thao tác repair của lab hoạt động**, không chứng minh cluster production đã có lịch repair, backup, hoặc toàn bộ dữ liệu giữa mọi node không còn sai khác.

### 8.3. Bảng diễn giải sau một lần mất node

| Quan sát | Kết luận được | Không nên kết luận |
|---|---|---|
| n3 chuyển `DN` khi dừng | Gossip/failure detector của n1/n2 nhận thấy node down | Dữ liệu của n3 đã bị xóa |
| `LOCAL_QUORUM` write thành công khi n3 down | Đủ hai replica phản hồi theo CL | n3 chắc chắn đã nhận mutation hoặc hint chắc chắn được lưu |
| `ALL` read thất bại khi n3 down | Không đủ ba replica cho yêu cầu read | Bảng bị hỏng hoặc keyspace sai |
| n3 restart và chuyển `UN` | Node hoạt động/đã tham gia ring | Mọi row cục bộ của n3 giống hệt n1/n2 |
| SELECT qua n3 thấy row mới | Client truy vấn được thông qua coordinator n3 | Row mới chắc chắn đã nằm trong SSTable cục bộ n3 |
| `listpendinghints` trống | Tại thời điểm hỏi không có hints đang chờ được liệt kê | Hints chưa từng có, hoặc mọi replica đã được sửa hết |
| `nodetool repair` hoàn tất | Repair đã hoàn thành phạm vi thao tác đó | Snapshot/backup và mọi token range toàn cluster đều đạt yêu cầu |

## 9. Thí nghiệm C (tùy chọn): crash process và khôi phục

**Chỉ thực hiện sau khi thí nghiệm A/B hoàn thành, cả ba node đã `UN` và bạn chấp nhận có thể phải dựng lại lab.** Mục đích là phân biệt **dừng bình thường** với **process bị kết thúc đột ngột**; không thử bằng cách cố gây lỗi ổ đĩa thật.

### 9.1. Mô phỏng một process bị kill

Khi cả ba node khỏe, có thể ghi thêm một row với `LOCAL_QUORUM` trên n1:

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO pe010_lab.events_by_device
  (device_id, event_id, event_time, payload)
VALUES
  ('device-010', 'c-before-kill',
   '2026-11-21T08:10:00Z', 'pre-crash-write');
```

Trên host **chỉ trong lab**:

```bash
docker kill --signal=KILL pe010-n2
docker exec pe010-n1 nodetool status
docker ps -a --filter name=pe010-n2
```

Khác với `docker stop`, `docker kill --signal=KILL` kết thúc process đột ngột, không cho nó hoàn tất shutdown. Cassandra có **commit log** nhằm hỗ trợ replay mutation chưa flush **trên chính node đó** khi khởi động lại, với các điều kiện durability và fsync thực tế. Nó **không** đồng nghĩa mọi acknowledged write đã được fsync ngay (đặc biệt tùy `commitlog_sync` và phần cứng), cũng không thay thế replication/backup.

Khởi động lại đúng container/volume:

```bash
docker start pe010-n2
docker logs --tail 100 pe010-n2
docker exec pe010-n2 nodetool status
docker exec pe010-n1 nodetool status
```

Đợi ba node `UN` rồi đối chiếu ba row bằng `LOCAL_QUORUM` từ n1/n2. Khi review log, xem có thông tin recovery/commitlog replay hay không, nhưng **không buộc** log phải xuất hiện dòng replay cụ thể: một write đã được flush hoặc đồng bộ theo đường khác có thể không tạo ra bằng chứng replay dễ thấy. Đừng suy “test crash pass” chỉ từ việc container chạy lại.

### 9.2. Khi nào không nên làm bài C?

Không làm nếu máy thiếu RAM/đĩa, cluster còn `UJ/DN`, dữ liệu có giá trị cần giữ, hoặc người học chưa biết cách khôi phục node. Thử nghiệm này chỉ mô phỏng **process crash trên một Docker host**; không đánh giá hỏng SSD, mất VM, network partition, rack outage, hoặc consistency trong mọi kịch bản.

## 10. Đối chiếu bằng Java Driver

Khi một node tạm down, Java Driver có thể kết nối tới node khác và điều phối query, miễn là **contact point, địa chỉ peer, local datacenter, authentication/TLS và network** được cấu hình phù hợp. Trong Docker Desktop, địa chỉ IP nội bộ mà Cassandra quảng bá thường không định tuyến được từ host; do đó ví dụ này giả định **Java app chạy trong container thuộc cùng Docker network `pe010-net`**.

Với Java 17, Apache Cassandra Java Driver 4.x (ví dụ dependency `org.apache.cassandra:java-driver-core:4.19.4`), mã minh họa:

```java
import java.net.InetSocketAddress;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public class CassandraFailoverRead {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("pe010-n1", 9042))
                .addContactPoint(new InetSocketAddress("pe010-n2", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            SimpleStatement stmt = SimpleStatement.builder(
                    "SELECT event_id, payload FROM pe010_lab.events_by_device " +
                    "WHERE device_id = 'device-010'")
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                    .build();

            for (Row row : session.execute(stmt)) {
                System.out.println(
                        row.getString("event_id") + " => " +
                        row.getString("payload"));
            }
        }
    }
}
```

Một kết nối chạy được khi n3 down minh họa đường client → coordinator → replicas còn sống, **không** tự chứng minh failover của cả ứng dụng đã hoạt động trong mọi tình huống. Để kiểm thử ứng dụng thật, cần dùng lại `CqlSession`, đo timeout/retry/backoff, không retry vô hạn các write không idempotent, ghi nhận CL của statement, và kiểm tra địa chỉ peer quảng bá có thể route từ ứng dụng.

**Đặc biệt:** CL được đặt ở **request Java/cqlsh**, không phải cấu hình một cổng 9042 hay một file `cassandra.yaml` chung cho mọi client. RF nằm ở **keyspace CQL**; sửa CL không tăng số replica lưu dữ liệu.

## 11. Lỗi thường gặp khi thử dừng/khởi động node

| Triệu chứng | Giả thuyết cần kiểm tra | Công cụ và hướng xử lý |
|---|---|---|
| n2/n3 không join n1 từ đầu | Seed sai, Docker DNS/network khác, cổng internode không thông, cấu hình cluster/DC sai | `docker network inspect pe010-net`, `docker logs` từng node, `nodetool status` từ nhiều góc nhìn |
| Node `UJ` rất lâu | Bootstrap, streaming hoặc I/O chậm, thiếu RAM/đĩa | `nodetool netstats`, `docker stats`, `docker logs`; không tạo keyspace RF3 khi chưa đủ ba `UN` |
| `docker stop` xong n3 chưa `DN` ngay | Failure detector chưa cập nhật hoặc góc nhìn node khác | Theo dõi `nodetool status` trên n1/n2; không giả định chuyển trạng thái tức thì |
| `LOCAL_QUORUM` thất bại khi chỉ n3 down | Một trong hai replica còn lại bị lỗi, timeout, schema chưa ổn định, RF/DC không đúng | `nodetool status`, `DESCRIBE KEYSPACE`, log, `tpstats`, latency |
| `ALL` thất bại khi n3 down | Không đủ ba replica theo yêu cầu | Đây là **kết quả mong đợi**, không phải lý do xóa dữ liệu |
| n3 restart nhưng `cqlsh` chưa connect | Native transport chưa mở, JVM/commitlog recovery còn chạy | `nodetool statusbinary`, `docker logs pe010-n3`, đợi readiness |
| SELECT qua n3 thấy row, nhưng không biết dữ liệu cục bộ | n3 chỉ là coordinator; có thể đọc từ n1/n2 hoặc được read-repair | Đối chiếu hints, logs, repair/metrics; không suy local persistence từ một SELECT |
| Hints trống dù có write lúc node down | Hints best effort, write đi qua coordinator khác, hint chưa flush/đã phát, thời gian ngắn | Kiểm tra `listpendinghints` ở các coordinator có thể có, log/metrics và hint window |
| Ghi timeout nhưng retry tạo dữ liệu lặp | Request có thể đã được áp dụng một phần, retry không idempotent | Dùng PK và event ID cố định trong lab; trong ứng dụng thiết kế idempotency |
| n3 restart thành `UN` nhưng sau đó timeout/repair chậm | Hints backlog, compaction/IO, network, disk đầy | `nodetool netstats`, `compactionstats`, `df -h`, logs |
| Tạo lại container với volume cũ rồi peer sai IP | Docker cấp IP mới, Cassandra system metadata/broadcast address đã ghi từ lần trước | Giữ container cũ để stop/start; nếu thay node thật dùng quy trình replace/change address |
| Java app trên host không kết nối được các peer | Broadcast RPC là container IP không route qua Docker Desktop/NAT | Cho app vào cùng network hoặc thiết kế endpoint/address translation hợp lệ |
| `nodetool repair` lỗi hay quá chậm | Node chưa `UN`, disk/network/CPU thiếu, phiên repair khác xung đột | Đảm bảo đủ node, quan sát logs/metrics; không ép repair trên production để vượt deadline lab |

Thứ tự kiểm tra hữu ích: **process → logs → gossip/ring → native transport → keyspace RF/DC → client CL → dữ liệu theo partition key → hints/repair/IO → Java connectivity**. Không tự sửa system tables, đổi token, `assassinate` node hay xóa volume để buộc node hiện `UN`.

## 12. Bảng tổng hợp kết quả và các câu hỏi phân tích

### 12.1. Biên bản thí nghiệm

Ghi thời điểm thực tế của các bước, không sao chép số liệu mẫu:

| Mốc | n1 | n2 | n3 | CL và thao tác | Kết quả/dẫn chứng |
|---|---|---|---|---|---|
| T0 — Sau bootstrap | `UN` | `UN` | `UN` | Ghi `a-baseline` ở `ALL` | Ba replica phản hồi theo CL; `getendpoints` có ba node |
| T1 — Dừng n3 | `UN` | `UN` | `DN` sau khi phát hiện | SELECT ở `LOCAL_QUORUM` | Kỳ vọng đọc baseline |
| T2 — n3 vẫn down | `UN` | `UN` | `DN` | Ghi `b-while-n3-down` ở `LOCAL_QUORUM` | Kỳ vọng write thành công nếu hai replica khỏe |
| T3 — n3 vẫn down | `UN` | `UN` | `DN` | SELECT ở `ALL` | Kỳ vọng unavailable hoặc timeout |
| T4 — Khởi động n3 | `UN` | `UN` | `UN` | SELECT n1/n3 ở `LOCAL_QUORUM` | Kỳ vọng thấy cả baseline và row ghi lúc node down |
| T5 — Cả ba khỏe | `UN` | `UN` | `UN` | SELECT ở `ALL`; xem hints/repair nếu cần | Đối chiếu dữ liệu và hoạt động đồng bộ |
| T6 — Bài crash tùy chọn | `UN` | restart n2 | `UN` | Ghi row `c-before-kill`, kill/restart n2 | Quan sát startup/recovery, dữ liệu qua CL đã chọn |

**Những gì cần lưu trong nhật ký:** phiên bản Cassandra và JDK, tên cluster/datacenter, host ID của ba node, RF của keyspace, chính xác CL của mỗi request, output/lỗi, thời điểm dừng/khởi động node, biến động hints, log quan trọng và đĩa còn trống.

### 12.2. Câu hỏi tự kiểm tra

1. Với `RF=3` và ba node khỏe, `LOCAL_QUORUM` cần mấy replica phản hồi? Khi n3 down, tại sao `LOCAL_QUORUM` có thể thành công mà `ALL` không?
2. Một SELECT từ `cqlsh` kết nối trực tiếp n3 trả row `b-while-n3-down`. Vì sao chưa thể khẳng định row đã nằm trong SSTable cục bộ n3?
3. Một write ở CL `ALL` báo timeout. Có thể kết luận không replica nào đã ghi dữ liệu không? Khi retry, cần cơ chế bảo vệ gì?
4. Hints nằm trên replica down hay trên coordinator giữ hint? Vì sao hints không thể thay thế lịch anti-entropy repair?
5. `WRITETIME(payload)` và `event_time` khác nhau ra sao? Clock skew có thể làm sai kỳ vọng last-write-wins như thế nào?
6. Khi làm bài này, vì sao cần ba volume riêng? Việc xóa/tạo lại container với IP mới khác gì `docker stop/start`?
7. Nếu thay `RF=3` thành `RF=1`, dừng node đang giữ partition sẽ ảnh hưởng đọc/ghi thế nào? Thêm ba node nhưng giữ RF=1 có tự tạo ba bản sao không?
8. `nodetool status` hiển thị ba `UN` có chứng minh không còn tombstone, hint backlog, pending compaction hoặc dữ liệu phân kỳ không?
9. Khác nhau ở đâu giữa `docker stop --time 120` và `docker kill --signal=KILL`? Commit log có thể hỗ trợ gì sau crash, và giới hạn của nó là gì?
10. Tại sao phải thử Java Driver từ đúng network mà ứng dụng chạy, không chỉ kiểm tra bằng `docker exec ... cqlsh`?
11. Khi nào một lệnh `nodetool repair --full pe010_lab events_by_device` là bài mở rộng hợp lý, và tại sao nó không phải health check thường xuyên?
12. Ba container trong một laptop có thể xác minh mất một process, nhưng còn thiếu những điều gì để khẳng định hệ thống chịu được hỏng rack/datacenter thật?

### 12.3. Điều kiện đạt

Người học hoàn thành khi đã: khởi tạo ba node độc lập cùng cluster/DC; thấy ba `UN` và ba host ID; ghi baseline CL=ALL; dừng n3, thử `LOCAL_QUORUM` read/write thành công và quan sát `ALL` không đủ replica; khởi động lại n3, thấy ba `UN`, đối chiếu các row từ n1/n3; phân biệt được dữ liệu coordinator đọc với dữ liệu replica cục bộ; ghi nhận hints/repair và giới hạn của phép thử. Đó là nền tảng cho các bài học sâu hơn về **replication, consistency, repair, compaction, xử lý lỗi và ứng dụng Java**.

## 13. Dừng lab và giữ lại dữ liệu

**Chỉ dọn sau khi cả ba node đã được khôi phục**, các phiên cqlsh đã đóng và không còn Java app nào dùng cluster. Nếu vừa thực hiện bài crash, đợi n2 khỏe trước khi tắt.

```bash
docker stop --time 120 pe010-n3
docker stop --time 120 pe010-n2
docker stop --time 120 pe010-n1
docker rm pe010-n3 pe010-n2 pe010-n1
docker network rm pe010-net
docker volume ls
```

Các lệnh này xóa container/network nhưng **không xóa named volumes** `pe010_data_n1`, `pe010_data_n2`, `pe010_data_n3`. **Không dùng `docker volume rm` hoặc `docker volume prune`** khi cần giữ dữ liệu. Nếu muốn khởi tạo **một cluster mới hoàn toàn**, dùng ba volume mới; không tự gắn bộ dữ liệu cũ với IP/cluster identity khác như thể nó là bootstrap sạch.

Lưu ý: **volume trên cùng host không phải backup độc lập**. Nếu cần dữ liệu bền vững, phải có backup/restore thử nghiệm và những failure domain riêng biệt cho replica.

## 14. Tài liệu tham khảo chính thức

- [Apache Cassandra — Dynamo architecture and consistency levels](https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html): cách tính quorum, read/write replica và hinted handoff.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/hints.html): điều kiện tạo hints, `max_hint_window` và giới hạn best effort.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/repair.html): anti-entropy, full/incremental repair, primary ranges và tác động I/O.
- [Apache Cassandra — nodetool status](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/status.html): trạng thái ring `UN`, `DN`, `UJ`.
- [Apache Cassandra — nodetool getendpoints](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/getendpoints.html): xác định replica endpoints theo partition key.
- [Apache Cassandra — nodetool listpendinghints](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/listpendinghints.html): quan sát hints đang chờ trên một node.
- [Apache Cassandra — nodetool drain](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/drain.html): dừng nhận write và flush khi bảo trì.
- [Apache Cassandra — nodetool repair](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/repair.html): cú pháp repair và tùy chọn `--full`, `-pr`.
- [Docker Hub — Cassandra Official Image](https://hub.docker.com/_/cassandra): multi-node Docker, `CASSANDRA_SEEDS` và volume.
- [Docker Docs — docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/): tín hiệu shutdown và thời hạn chờ.
- [Apache Cassandra Java Driver](https://github.com/apache/cassandra-java-driver): `CqlSession`, contact points và request consistency.
