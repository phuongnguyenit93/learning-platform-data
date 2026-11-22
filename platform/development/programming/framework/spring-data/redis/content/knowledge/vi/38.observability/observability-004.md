# Quan sát độ trễ sao chép và thay đổi vai trò máy chủ trong Spring Data Redis

## 1. Tại sao cần quan sát replication và role change?

Redis hỗ trợ replication giữa primary và replicas, và có thể tự động chuyển đổi vai trò khi dùng Sentinel hoặc Redis Cluster. Nhưng một ứng dụng Spring Boot nhận được phản hồi `OK` từ Redis primary **không có nghĩa mọi replica đều đã áp dụng write**, và việc có một primary mới **không có nghĩa dữ liệu trên primary mới hoàn toàn giống primary cũ tại thời điểm sự cố**.

Ví dụ:

```text
                          Spring Boot
                         RedisTemplate
                              |
                              v
                        Redis primary A
                     offset = 1,000,000
                        /          \
                       v            v
                 Replica B      Replica C
                 998,000        999,900
```

Tại một thời điểm, primary ghi nhận Replica B kém 2.000 đơn vị offset, Replica C kém 100. Sau đó primary A lỗi; Replica C được promote thành primary mới.

Các câu hỏi vận hành:

- Replica nào đang chậm và chậm theo đơn vị gì?
- Những replica nào kết nối được nhưng đang full synchronization?
- Primary hiện tại có đúng là primary mà Sentinel/Cluster đã công bố không?
- Những write đã được ACK trên A có còn trên C không?
- Ứng dụng còn lỗi `READONLY`, `MOVED`, timeout hay kết nối cũ không?
- Từ lúc primary hỏng đến lúc Spring ghi lại thành công mất bao lâu?
- Sau failover, các replica còn lại đã bắt kịp primary mới chưa?

Bài này đi từ cách đọc các metric Redis, phát hiện đổi vai trò cho đến thiết kế dashboard/alert, ví dụ Spring Data Redis và các bài kiểm thử sự cố.

> **Thông điệp chính:** Theo dõi replication lag và role changes giúp đánh giá khả năng phục hồi và rủi ro stale reads/write loss. Nó không tự biến replication bất đồng bộ thành durable transaction hoặc cam kết zero downtime.

## 2. Những khái niệm nền tảng

| Khái niệm | Ý nghĩa |
| --- | --- |
| Primary/master | Redis node phục vụ ghi cho dữ liệu nó quản lý |
| Replica | Bản sao của primary, đồng bộ qua replication stream |
| Replication offset | Tiến độ trong replication stream, theo byte |
| Replication lag | Một khoảng trễ cần định nghĩa rõ phương pháp đo |
| ACK age | Thời gian tính từ acknowledgment replication gần nhất theo một metric cụ thể |
| Full synchronization | Replica nhận lại dataset từ primary |
| Partial resynchronization | Replica đuổi theo từ offset bằng backlog nếu đủ điều kiện |
| Role change | Node chuyển giữa vai trò primary/replica |
| Promotion | Replica được nâng thành primary |
| Failover | Thay primary lỗi bằng node khác để phục hồi phục vụ |
| Sentinel | Giám sát và điều phối failover cho nhóm primary–replica |
| Redis Cluster | Sharding theo hash slots, replication và failover theo từng shard |
| RPO | Mục tiêu lượng dữ liệu có thể mất khi phục hồi |
| RTO | Mục tiêu thời gian khôi phục dịch vụ |

Trong output Redis, tên trường `role:slave` và `connected_slaves` vẫn thường xuất hiện dù trong tài liệu người ta gọi là **replica**. Dashboard có thể dùng nhãn `primary/replica`, nhưng khi đọc protocol phải hiểu những tên field thực tế.

## 3. “Replication lag” có ít nhất ba nghĩa khác nhau

### 3.1. Chênh lệch offset theo byte

Giả sử cùng replication history, gần cùng thời điểm:

```text
primary master_repl_offset   = 1,500,000
replica acknowledged offset  = 1,494,000

offset gap = 6,000 bytes
```

Đó là **độ lệch tiến độ replication stream**, không phải “6.000 mili giây”.

### 3.2. Tuổi của ACK từ replica

Trên primary, dòng như:

```text
slave0:ip=10.20.0.12,port=6379,state=online,offset=1494000,lag=0
```

phản ánh thông tin primary có về replica. `lag` ở đây có liên quan thời gian kể từ acknowledgment gần nhất mà primary nhận từ replica, **không trực tiếp đo tuổi của mỗi bản ghi nghiệp vụ**.

Một replica có thể ACK gần đây nhưng vẫn còn dữ liệu chưa theo kịp khi workload đang ghi mạnh.

### 3.3. Độ cũ của dữ liệu đọc ở replica

Đây là điều người dùng quan tâm:

```text
Primary: product:42:price = 120000
Replica: product:42:price = 100000

Đọc replica bao lâu mới thấy 120000?
```

Để quan sát, có thể ghi heartbeat/sequence ở primary rồi đọc cụ thể ở replica. Kết quả gọi là **application-visible staleness**, khác với raw offset gap và ACK age.

Một dashboard nên tách:

```text
replication_offset_gap_bytes
replication_ack_age_seconds
replica_observed_staleness_seconds
```

Tên trên là gợi ý đặt tên nội bộ, không phải mọi exporter đều cung cấp đúng tên.

## 4. Replication bất đồng bộ tạo ra cửa sổ mất write

Luồng tiêu biểu:

```text
Spring app              Primary A                 Replica B
    |                       |                         |
    | SET key v2            |                         |
    |---------------------->|                         |
    |                       | apply v2                |
    |<----------------------| OK                      |
    |                       |                         |
    |                       | replication stream      |
    |                       |------------------------>|
    |                       |                         | apply v2
```

Redis replication thông thường là bất đồng bộ, nên primary có thể phản hồi trước khi replica nhận write.

Kịch bản lỗi:

```text
T0: A và B có key=v1
T1: Spring -> A: SET key v2
T2: A trả OK
T3: A chết trước khi B nhận v2
T4: B được promote thành primary
T5: Spring đọc B -> v1
```

Một metric offset gap lớn có thể là cảnh báo rủi ro. Nhưng offset gap bằng 0 ở lần scrape trước đó **không bảo đảm những write phát sinh sau lần scrape đều sống sót**.

Đồng thời, `OK` từ Redis không đồng nghĩa write đã được fsync lên đĩa của mọi node. Cần phân biệt replication, persistence và failover.

## 5. Quan sát theo nhiều lớp, không chỉ PING

Một hệ thống monitoring nên nhìn:

```text
                      Spring Boot service
                       |            |
                  latency/errors   Redis client reconnect
                       |            |
                       v            v
                    Redis primary/replicas
                          |      |
                    INFO replication
                    ROLE / persistence
                          |
               Sentinel hoặc Cluster
                 master, slots, roles
                          |
                          v
                  Prometheus / Grafana
                     Alerts / Logs
```

Các lớp:

1. **Redis data nodes:** role, offsets, upstream link, full sync.
2. **Replication group hoặc shard:** primary hiện tại, replicas đủ khỏe, offset gap.
3. **Control plane:** Sentinel hoặc Redis Cluster thấy topology thế nào.
4. **Spring Data Redis client:** command latency, connection failures, timeout, redirects.
5. **Persistence/recovery:** AOF/RDB errors và thời điểm backup.
6. **Nghiệp vụ:** stale reads, yêu cầu retry, công việc quá hạn.

`PING` thành công chỉ là một tín hiệu kết nối, không xác nhận replica bắt kịp hoặc application đã tìm đúng master mới.

## 6. INFO replication trên primary

Lệnh Redis:

```bash
redis-cli -h redis-primary.internal -p 6379 INFO replication
```

Ví dụ output (minh họa):

```text
# Replication
role:master
connected_slaves:2
slave0:ip=10.20.0.12,port=6379,state=online,offset=1950200,lag=0
slave1:ip=10.20.0.13,port=6379,state=online,offset=1948600,lag=1
master_replid:2a1...
master_repl_offset:1951000
repl_backlog_active:1
repl_backlog_size:1048576
```

| Trường | Ý nghĩa |
| --- | --- |
| `role` | Vai trò node hiện tại |
| `connected_slaves` | Số replica kết nối theo primary |
| `slaveN.ip`/`port` | Endpoint của replica |
| `slaveN.state` | Trạng thái online/sync của replica theo primary |
| `slaveN.offset` | Tiến độ replica mà primary ghi nhận |
| `slaveN.lag` | Tuổi của ACK theo primary, không phải độ cũ dữ liệu tuyệt đối |
| `master_replid` | Nhận dạng replication history |
| `master_repl_offset` | Offset hiện tại của primary |
| `repl_backlog_active` | Trạng thái replication backlog |
| `repl_backlog_size` | Dung lượng backlog; không phải lag hiện tại |

Tập trường có thể khác theo Redis version. Không viết parser cứng phụ thuộc mọi phiên bản đều trả cùng danh sách hoặc thứ tự `slave0`, `slave1`.

## 7. INFO replication trên replica

Lệnh:

```bash
redis-cli -h redis-replica.internal -p 6379 INFO replication
```

Ví dụ:

```text
# Replication
role:slave
master_host:10.20.0.11
master_port:6379
master_link_status:up
master_last_io_seconds_ago:1
master_sync_in_progress:0
slave_read_repl_offset:1950200
slave_repl_offset:1950200
slave_priority:100
slave_read_only:1
```

Những trường cần chú ý:

- `master_host`, `master_port`: upstream hiện tại. Nếu vừa failover, địa chỉ này có thể thay đổi.
- `master_link_status`: trạng thái đường replication hiện tại.
- `master_last_io_seconds_ago`: thời gian từ I/O gần nhất với master, **không đồng nghĩa dữ liệu stale đúng từng ấy giây**.
- `master_sync_in_progress`: đang đồng bộ đầy đủ hay không.
- `slave_repl_offset`: tiến độ replica theo trường Redis version cung cấp.
- `slave_read_repl_offset`: có thể có trên những phiên bản hỗ trợ, giúp quan sát thêm tiến độ đọc stream.
- `slave_priority`: tham số ảnh hưởng lựa chọn replica trong một số cơ chế failover.

Nếu replica đang full resync, offset gap chưa thể diễn giải đơn giản như trạng thái bắt kịp bình thường; cần nhìn cả snapshot/sync progress và link.

## 8. Tính offset gap một cách có ý nghĩa

Từ primary:

```text
master_repl_offset = 1,951,000
slave0.offset      = 1,950,200
slave1.offset      = 1,948,600
```

Ta có:

```text
slave0 gap = 800 bytes
slave1 gap = 2,400 bytes
```

Công thức cho một quan sát hợp lệ:

```text
offset_gap_bytes =
    max(0, master_repl_offset - replica_ack_offset)
```

Điều kiện:

1. Cùng primary/replication history.
2. Gần cùng thời điểm lấy số liệu.
3. Replica không trong trạng thái mà phép đo chưa có ý nghĩa, như initial full sync.
4. Không lấy offset của primary trước failover để trừ với offset của primary mới không cùng history.
5. Không trộn offsets từ hai Redis Cluster shards khác nhau.

Nên gắn metric với `node_id`, `replication_group`, `master_replid` hoặc thông tin generation phù hợp, và thời điểm scrape.

**Một gap âm hoặc biến động lớn bất thường** có thể do không cùng thời điểm, thay đổi history, mapping sai node hoặc exporter reset. Đừng chỉ clamp về 0 rồi kết luận khỏe.

## 9. Tại sao offset gap không phải số giây?

Ví dụ:

| Primary workload | Gap 100 KB có thể phản ánh |
| --- | --- |
| Ghi 20 MB mỗi giây | Khoảng rất ngắn trong điều kiện lý tưởng |
| Ghi 1 KB mỗi phút | Có thể tích lũy rất lâu |
| Replication link down | Không tiếp tục cập nhật, dù workload nhỏ |
| Full sync | Có nhiều trạng thái khác ngoài stream gap |
| Không có write mới | Gap 0 nhưng link có thể đã down |

Đơn vị của offset gap là byte, không phải thời gian. Nếu muốn ước lượng độ cũ của dữ liệu nghiệp vụ, hãy dùng một probe có sequence/timestamp được kiểm soát.

Không quy đổi bằng phép chia cho throughput trung bình nếu mục tiêu là một SLA cứng; throughput có thể thay đổi rất lớn theo thời gian.

## 10. Link up chưa đủ chứng minh replica bắt kịp

Một replica có thể hiển thị:

```text
master_link_status:up
master_sync_in_progress:0
```

nhưng offset gap vẫn lớn trong lúc primary ghi liên tục.

Ngược lại, một replica có:

```text
master_link_status:down
```

và gap cuối cùng bằng 0 vì không có write mới vẫn là replica cần cảnh báo mất đường đồng bộ.

Cần kết hợp:

```text
link status
sync status
offset gap
ACK age
last I/O age
replica eligibility
server health
```

Một trạng thái sức khỏe đơn giản:

```text
link down                -> unhealthy
full sync đang chạy      -> syncing
offset gap tăng kéo dài  -> lagging
các tín hiệu ổn định     -> currently healthy
```

Đây là phân loại vận hành, không phải một công thức quyết định failover chính thức của Redis.

## 11. ROLE: kiểm tra vai trò thực tế của node

Lệnh:

```bash
redis-cli -h redis-node.internal -p 6379 ROLE
```

Đầu ra primary thường bắt đầu:

```text
1) "master"
2) (integer) <replication-offset>
3) ...
```

Replica thường bắt đầu:

```text
1) "slave"
2) "<upstream-host>"
3) (integer) <upstream-port>
4) "connected"
5) (integer) <replication-offset>
```

Hình dạng phần còn lại phụ thuộc Redis role/version; không parse mọi role bằng cùng chỉ số mảng.

`ROLE` giúp xác minh node bạn **thực sự kết nối** đang là primary hay replica. `INFO replication` cung cấp tập trường rộng hơn cho time-series monitoring.

Trong dashboard nên chuẩn hóa:

```text
Redis role "master" -> primary
Redis role "slave"  -> replica
```

Nhưng giữ nguyên raw field trong log debug nếu cần đối chiếu với Redis CLI.

## 12. Sentinel: master identity là một phần của quan sát

Redis Sentinel điều phối failover cho một nhóm primary–replicas. Ứng dụng kết nối theo tên logic, ví dụ `mymaster`:

```text
Sentinel A -------\
Sentinel B --------+---- mymaster
Sentinel C -------/
                         |
                         v
                       Primary A
                         |
                         v
                       Replica B
```

Các lệnh:

```bash
redis-cli -h sentinel-a.internal -p 26379 SENTINEL get-master-addr-by-name mymaster
redis-cli -h sentinel-a.internal -p 26379 SENTINEL master mymaster
redis-cli -h sentinel-a.internal -p 26379 SENTINEL replicas mymaster
redis-cli -h sentinel-a.internal -p 26379 SENTINEL sentinels mymaster
```

Điều cần ghi nhận:

- Master endpoint hiện tại của `mymaster`.
- Khi nào địa chỉ thay đổi.
- Các Sentinel có cùng nhận thức về master không.
- Trạng thái down/failover.
- Replica nào được promote.
- Những replica còn lại đã theo master mới chưa.

Tên `mymaster` là **master group name**, không phải hostname. Nó được khai báo tại Sentinel:

```conf
sentinel monitor mymaster 10.20.0.11 6379 2
```

Nếu application lưu master name nhưng không ghi nhận endpoint thực tế, dashboard có thể bỏ lỡ thay đổi node sau failover.

## 13. Sentinel events và giới hạn Pub/Sub

Sentinel có thể phát các events như:

```text
+sdown
-sdown
+odown
+new-epoch
+try-failover
+failover-end
+switch-master
+slave-reconf-sent
+slave-reconf-inprog
+slave-reconf-done
```

Tập events và thứ tự cụ thể phụ thuộc loại lỗi và Redis/Sentinel version.

Có thể quan sát ở môi trường thử nghiệm:

```bash
redis-cli -h sentinel-a.internal -p 26379 PSUBSCRIBE '*'
```

`+switch-master` đặc biệt hữu ích: nó phản ánh Sentinel đã chuyển master mà nó giám sát.

**Nhưng events của Sentinel qua Pub/Sub không phải nhật ký bền vững cho subscriber offline.** Nếu monitor bị ngắt kết nối, có thể không nhận được event đã phát.

Thiết kế đáng tin hơn:

```text
Sentinel Pub/Sub event -> cập nhật nhanh/log
             +
Poll Sentinel master address định kỳ
             +
So sánh topology với snapshot trước
```

Nếu bị lỡ `+switch-master`, vòng poll tiếp theo vẫn có thể phát hiện master endpoint đã khác.

## 14. Timeline Sentinel failover

Ví dụ các mốc thời gian giả định:

```text
10:00:00  A primary; B/C là replicas
10:00:04  A không phản hồi
10:00:07  Sentinel phát hiện SDOWN/ODOWN khi đủ điều kiện
10:00:10  B được promote thành primary
10:00:12  Sentinel công bố mymaster -> B
10:00:13  Lettuce kết nối/khám phá lại
10:00:15  Spring ghi vào B thành công
10:00:25  C đã theo B và catch up
```

Các metric trong timeline:

| Pha | Redis/Sentinel signal | Application signal |
| --- | --- | --- |
| Sự cố | Node unreachable, link down | Timeout/connection errors |
| Phát hiện | SDOWN/ODOWN | Retry/fallback |
| Promotion | Switch-master, node role | Có thể vẫn giữ connection cũ |
| Reconnect | Master address mới | Reconnect, có thể READONLY |
| Phục hồi | Replication ổn định | Successful write/latency bình thường |
| Sau phục hồi | Replica offsets bắt kịp | Đối soát dữ liệu quan trọng |

Không nên chỉ đo thời gian từ phát hiện SDOWN đến `+switch-master` rồi coi đó là **RTO nhìn từ người dùng**. Cần đo lúc request thật trở lại thành công.

## 15. Redis Cluster: replication và role theo từng shard

Redis Cluster phân phối dữ liệu theo **16.384 hash slots**. Mỗi primary quản lý một tập slots và có thể có replica:

```text
                   Redis Cluster
            +-----------+-----------+
            |           |           |
         Primary A   Primary B   Primary C
          slots A     slots B     slots C
            |           |           |
         Replica A1  Replica B1  Replica C1
```

Nếu Primary B lỗi, Replica B1 có thể được promote và tiếp quản **slots B**.

Trong Cluster, phải quan sát:

- Node ID/role.
- Primary của mỗi replica.
- Slot ownership.
- `cluster_state` và slot coverage.
- Replication offset trong **từng shard**.
- Role change và epoch/topology tương ứng.
- Cluster bus/network status.

Không thể lấy offset của Primary A trừ offset của Replica C1 để tính replication lag vì chúng thuộc **hai replication streams khác nhau**.

## 16. Redis Cluster commands phục vụ monitoring

Lệnh:

```bash
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER INFO
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER NODES
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER SHARDS
redis-cli -c -h redis-node-1.internal -p 6379 CLUSTER SLOTS
```

Cần xem:

- `cluster_state` có `ok` hay `fail`.
- Số hash slots được gán và đang được phục vụ.
- Những node nào là master/replica.
- Các node có flags `fail`, `pfail` hoặc trạng thái bất thường.
- Slot ranges thuộc primary nào.
- Replica nào theo primary nào.
- Sau promotion, node ID nào tiếp quản slots cũ.

`CLUSTER SHARDS` có ở các Redis versions hỗ trợ. Nếu môi trường cũ, có thể dùng `CLUSTER NODES`/`CLUSTER SLOTS` theo khả năng.

**Redis Cluster không dùng Sentinel để thực hiện failover các shard.** Không dựa vào `+switch-master` Sentinel để quan sát role changes của Redis Cluster.

## 17. Failover khác resharding

Hai hiện tượng cùng làm topology thay đổi nhưng khác mục đích.

**Failover:**

```text
Primary B lỗi
Replica B1 được promote
B1 giữ slots B
```

**Resharding:**

```text
Thêm Primary D
Di chuyển một số slots từ A/B/C sang D
Key migration và redirects
```

Trong resharding, client có thể nhận `ASK` và `MOVED`. Trong failover, client có thể nhận `READONLY`, `MOVED`, timeout hoặc cluster state error tùy thời điểm.

Đừng suy ra “failover” chỉ vì số slots trên một node thay đổi. Log role changes nên bao gồm:

```text
timestamp
replication_group/shard
old_node_id / new_node_id
old_role / new_role
old_primary / new_primary
owned_slots_before / after
observation_source
```

Một dashboard cần phân biệt planned resharding, rolling restart và failover bất thường để cảnh báo đúng.

## 18. Master endpoint khác master role

Một bẫy của monitoring ứng dụng:

```text
T0: Spring -> Redis A, INFO role=master
T1: Failover A -> B
T2: Spring -> Redis B, INFO role=master
```

Nếu chỉ so sánh chuỗi `master`, monitor ghi “không thay đổi”. Nhưng primary thực tế đã đổi từ A sang B.

Cần theo dõi:

- Sentinel master name và **resolved master endpoint**.
- Redis Cluster **node ID** và slot ownership.
- Replication ID/generation nếu dùng offsets.
- Thời điểm quan sát và dữ liệu từ control plane.

Role chỉ nói “node đang xem là primary”, không nói “có phải cùng node như lần trước”.

## 19. Replication ID và generation sau failover

Redis replication dùng các thông tin như replication ID và offset để mô tả stream/history. Khi topology thay đổi, primary mới có thể có identity/history mới; một số cơ chế hỗ trợ secondary replication ID trong giai đoạn thay đổi.

Sai lầm:

```text
offset của A trước failover = 10,000,000
offset của B sau failover   =  9,990,000

=> mất chính xác 10.000 bytes dữ liệu nghiệp vụ
```

Không được kết luận như vậy chỉ từ hai số, vì:

- Có thể khác replication history.
- Có thể metric scrape khác thời điểm.
- Offset theo byte không tương ứng số nghiệp vụ.
- B được promote và stream identity thay đổi.
- Replica ACK state có thể không tương đương data durability.

Khi master identity/history thay đổi, **rebaseline metric** và ghi lại generation. Đừng vẽ negative offset rate qua failover rồi cảnh báo mất dữ liệu bằng phép trừ đơn giản.

## 20. Quan sát qua Spring Data Redis

Spring Data Redis cung cấp `RedisConnectionFactory`, `RedisTemplate`/`StringRedisTemplate` và APIs server commands.

Một component minh họa cách lấy `INFO replication` từ connection đang được factory cấp:

```java
package com.example.monitoring;

import java.util.Properties;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisReplicationInspector {

    private final StringRedisTemplate template;

    public RedisReplicationInspector(
            StringRedisTemplate template) {
        this.template = template;
    }

    public Properties readInfo() {
        return template.execute(
            (RedisCallback<Properties>) connection ->
                connection.serverCommands().info("replication")
        );
    }
}
```

Ví dụ dùng `RedisServerCommands` ở cấp connection mà phiên bản Spring Data Redis tương ứng hỗ trợ.

**Giới hạn rất quan trọng:** đoạn code đọc từ một connection mà factory chọn. Nó **không tự query mọi replica hoặc mọi Redis Cluster shard**. Với Sentinel hoặc Cluster, factory có thể chuyển node sau failover; nên ứng dụng còn cần control-plane topology monitoring.

Không nên coi đoạn code trên là một fleet-wide Redis exporter.

## 21. Đọc role theo cách phòng thủ

Một service chuẩn hóa tên role:

```java
package com.example.monitoring;

import java.util.Properties;
import org.springframework.stereotype.Service;

@Service
public class RedisRoleInspector {

    private final RedisReplicationInspector inspector;

    public RedisRoleInspector(
            RedisReplicationInspector inspector) {
        this.inspector = inspector;
    }

    public String currentRole() {
        Properties info = inspector.readInfo();

        if (info == null) {
            return "unknown";
        }

        String role = info.getProperty("role", "unknown");

        return switch (role) {
            case "master" -> "primary";
            case "slave", "replica" -> "replica";
            default -> "unknown";
        };
    }
}
```

`switch` expression yêu cầu Java version phù hợp; nếu dự án dùng Java cũ, thay bằng `if/else`.

Không biến một lỗi connection thành `primary`, không tự đoán role theo hostname, và không dùng role-observation code để tự điều phối failover.

## 22. Poll role changes trong Spring

Một ví dụ đơn giản dùng Spring Scheduling:

```java
package com.example.monitoring;

import java.util.concurrent.atomic.AtomicReference;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class RedisRoleObserver {

    private static final Logger log =
        LoggerFactory.getLogger(RedisRoleObserver.class);

    private final RedisRoleInspector roles;
    private final AtomicReference<String> previous =
        new AtomicReference<>("unknown");

    public RedisRoleObserver(RedisRoleInspector roles) {
        this.roles = roles;
    }

    @Scheduled(
        fixedDelay = 10_000,
        initialDelay = 10_000
    )
    public void pollRole() {
        try {
            String role = roles.currentRole();
            String old = previous.getAndSet(role);

            if (!old.equals(role)) {
                log.info(
                    "Observed Redis role: {} -> {}",
                    old, role
                );
            }
        } catch (RuntimeException ex) {
            log.warn("Cannot query Redis role", ex);
        }
    }
}
```

Bật scheduling bằng `@EnableScheduling`:

```java
@Configuration
@EnableScheduling
public class RedisMonitoringConfig { }
```

Cần import hai annotation tương ứng từ Spring.

### Giới hạn của ví dụ

- Polling có thể bỏ lỡ thay đổi xảy ra giữa hai lượt.
- Khi app restart, `unknown -> primary` không chứng minh đã có failover.
- Trong Sentinel, trước/sau failover factory vẫn có thể trả role `master` dù node đã đổi.
- Không có node ID/endpoints trong metric trên.
- Một connection không thu thập toàn Redis Cluster topology.
- Nếu monitor offline khi failover, không có lịch sử role changes đầy đủ từ chính JVM.

Để nhận biết thay primary đáng tin cậy, kết hợp **master identity/endpoint polling** và control-plane events.

## 23. Cấu hình Spring Boot Sentinel và phạm vi quan sát

Spring Boot hiện đại:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      sentinel:
        master: mymaster
        nodes:
          - sentinel-a.internal:26379
          - sentinel-b.internal:26379
          - sentinel-c.internal:26379
      connect-timeout: 3s
      timeout: 3s
```

Client Sentinel-aware khám phá primary. Nhưng cấu hình đó không khiến mọi lệnh tự retry an toàn hoặc loại bỏ khoảng downtime trong failover.

Quan sát cùng lúc:

1. Master endpoint từ Sentinel.
2. Role và replication INFO ở tất cả data nodes.
3. Lettuce command errors, reconnect và latency.
4. Những request nghiệp vụ không được hoàn thành.
5. Thời điểm writes trở lại thành công.

Với Spring Boot cũ, prefix có thể là `spring.redis.*` thay vì `spring.data.redis.*`. Cần dùng property namespace đúng version.

## 24. Cấu hình Spring Boot Redis Cluster

Ví dụ:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-a.internal:6379
          - redis-b.internal:6379
          - redis-c.internal:6379
        max-redirects: 5
      connect-timeout: 3s
      timeout: 3s
```

`cluster.nodes` là seed nodes để khám phá topology; không phải danh sách mặc định mọi replica cần được monitor.

Nếu muốn theo dõi toàn cluster, có thể sử dụng exporter hoặc một collector biết node topology để query **từng Redis data node**.

Spring client error `MOVED`/`ASK` có thể xuất hiện khi topology hoặc slot owner thay đổi. Cần phân biệt cluster redirects với replication lag.

`max-redirects` không phải số retries nghiệp vụ an toàn sau timeout.

## 25. Khi dùng Lettuce đọc từ replica

Lettuce có chính sách `ReadFrom` trong các cấu hình được hỗ trợ:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .build();
```

Đoạn code chỉ tạo client configuration; muốn dùng phải gắn đúng vào connection factory theo Spring Data Redis version.

Với `REPLICA_PREFERRED`, client có thể fallback sang primary khi không có replica phù hợp. Vì vậy một `GET` trả giá trị mới **không chứng minh** replica mà bạn định đo đã bắt kịp; có thể request vừa được gửi tới primary.

Nếu cần staleness probe:

- Đọc từ **replica cụ thể** bằng một monitoring connection riêng.
- Xác nhận node ID/role trước và sau lần đo.
- Không dựa vào đường đọc có fallback.
- Không dùng một probe trên một Redis Cluster slot để đại diện cho mọi shard.

## 26. Staleness probe bằng heartbeat/sequence

Ví dụ application viết một heartbeat riêng:

```text
monitor:replication:shard-b
value = sequence:1024, time:...
```

Luồng:

```text
T0  Write sequence 1024 trên primary B
T1  Read replica B1 -> sequence 1022
T2  Read replica B1 -> sequence 1023
T3  Read replica B1 -> sequence 1024
```

Từ đó có thể quan sát số phiên bản heartbeat mà replica chậm và độ trễ từ lúc primary chấp nhận phiên bản tới lúc replica hiển thị phiên bản đó.

Các điều kiện:

- Sequence phải tăng đơn điệu trong một generation.
- Không ghi trùng key từ nhiều producers thiếu điều phối.
- Đường đọc phải vào đúng replica.
- Nếu dùng timestamp, cần chú ý clock skew; có thể đo thời gian bằng clock của hệ thống monitor và lưu time khi gửi.
- Redis Cluster cần probe từng shard nếu muốn quan sát từng replication stream.
- Key riêng, TTL hợp lý, tần suất thấp để không tăng tải.
- Khi failover, xác định generation mới và reset phép đo phù hợp.

Staleness probe kiểm tra **một đường dữ liệu cụ thể**, không chứng minh mọi key đều hiện đại tương đương.

## 27. Redis exporter và metrics

Một hệ thống monitoring có thể gồm:

```text
Redis primary ----> exporter ------\
Redis replica ----> exporter -------+--> Prometheus --> Grafana
Redis Sentinel ---> control-plane -/
Redis Cluster ----> topology collector
Spring Boot ------> Micrometer/Actuator
```

Các metric nên có về mặt ngữ nghĩa:

| Nhóm | Ví dụ tín hiệu |
| --- | --- |
| Node role | Node ID, role, primary identity |
| Replication link | Up/down, last I/O age |
| Replication progress | Primary/replica offsets, gap |
| ACK | ACK age, replica online state |
| Sync | Full sync in progress, sync failures |
| Topology | Sentinel master, Cluster slot ownership |
| Availability | Redis up, cluster state |
| Persistence | AOF/RDB write status |
| Application | Redis command latency/errors/reconnect |
| Business | Stale reads, overdue work, fallback rate |

Tên Prometheus series thực tế phụ thuộc exporter, Redis version và labeling. Không giả định mọi exporter đã có `redis_replication_lag_seconds` với cùng định nghĩa.

Labels hữu ích:

```text
environment
cluster
replication_group
shard
node_id
role
availability_zone
```

Tránh dùng user ID, token hoặc key riêng làm metric labels vì cardinality sẽ tăng rất lớn.

## 28. Dashboard nên có bốn phần

### Tổng quan topology

```text
Group: mymaster
Primary now: redis-b.internal:6379
Replicas: redis-a, redis-c
Last observed master switch: 10:00:12
Quorum/topology health: available
```

### Replication

| Node | Role | Link | Offset gap | ACK age | Sync |
| --- | --- | --- | ---: | ---: | --- |
| Redis B | Primary | — | — | — | — |
| Redis A | Replica | Up | 800 B | 0 s | No |
| Redis C | Replica | Up | 2.400 B | 1 s | No |

Số liệu minh họa. Trong production, cần time-series và thông tin master identity/generation.

### Application

```text
Redis command p95 / p99 latency
Timeout rate
READONLY / CLUSTERDOWN errors
Reconnect attempts
Redis fallback rate
Request failure rate
```

### Recovery

```text
Role changes in last 24h
Replica full sync duration
AOF/RDB errors
Last successful backup
Last tested restore
Time from failure to successful application write
```

Một dashboard chỉ báo `redis_up=1` nhưng không quan sát replication lag, role changes và application errors vẫn rất thiếu.

## 29. Alert design: tránh một ngưỡng cứng cho mọi workload

| Cảnh báo | Điều kiện tham khảo | Mục đích |
| --- | --- | --- |
| Replica link down | Link down vượt khoảng chịu đựng | Phát hiện mất sao chép |
| Replica quá lag | Offset gap cao kéo dài trong cùng history | Phát hiện bắt kịp không đủ |
| ACK age tăng | ACK không cập nhật đúng ngưỡng | Phát hiện link không ổn |
| Full sync kéo dài | Sync chưa hoàn tất quá lâu | Điều tra disk/network/load |
| Primary đổi | Master endpoint/node ID thay đổi | Ghi nhận role change |
| Replica dự phòng không đủ | Số replica khỏe dưới mục tiêu | Phát hiện giảm HA |
| Cluster fail | Cluster state không còn khả dụng | Ảnh hưởng service |
| Redis errors tăng | Timeout/READONLY/CLUSTERDOWN | Ảnh hưởng ứng dụng |
| Staleness vượt SLA | Probe phiên bản đọc replica quá cũ | Rủi ro dữ liệu không nhất quán |
| Persistence error | AOF/RDB thất bại | Rủi ro durability/recovery |

Không dùng ngưỡng `10 KB` hay `2 giây` như một quy tắc chung. Chọn dựa trên write throughput, baseline, số replicas và RPO/RTO của use case.

Để tránh **alert storm** lúc failover, nhóm cảnh báo theo replication group/shard, dùng inhibition hoặc correlation để phân biệt root cause với các triệu chứng.

## 30. Connected replicas không phải số failover candidates hợp lệ

Output:

```text
connected_slaves:2
```

không chứng minh hai replicas đều có thể được promote ngay.

Còn phải xem:

- Replica đã online và sync xong chưa.
- Lag cao không.
- Network tới các node khác có hoạt động không.
- Election/quorum có đủ điều kiện không.
- Replica priority/eligibility theo cấu hình.
- Placement có độc lập failure domain không.
- Disk, CPU, memory có đủ để xử lý tải primary mới không.

Một replica đang full resync có trạng thái rất khác replica online đã bắt kịp.

Monitoring nên có chỉ số **healthy/eligible replica count** được định nghĩa rõ, không chỉ dùng `connected_slaves`.

## 31. min-replicas-to-write và monitoring

Redis có hai cấu hình:

```conf
min-replicas-to-write 1
min-replicas-max-lag 10
```

Mục đích: primary có thể từ chối write nếu không đủ số replica theo điều kiện lag/ACK do Redis kiểm tra.

Đây là cách giảm nguy cơ primary chấp nhận writes khi không có đường sao chép đủ khỏe, đổi lại availability ghi có thể giảm khi replicas không đạt tiêu chí.

Nhưng nó **không chứng minh write vừa ACK đã tới hoặc đã fsync trên replica**.

Cần theo dõi:

- Số replicas hiện kết nối và đạt tiêu chí.
- Tuổi ACK.
- Tỉ lệ write bị từ chối.
- Tải bất thường và replication link.
- Hệ quả application khi Redis từ chối ghi.

Nếu Redis process vẫn sống nhưng application writes lỗi, kiểm tra `min-replicas-*` và replica health trước khi kết luận Redis server bị down.

## 32. WAIT và WAITAOF giúp đánh giá tiến độ xác nhận

Redis có lệnh `WAIT`:

```redis
SET demo:repl "v2"
WAIT 1 2000
```

`WAIT` chờ một số replicas xác nhận replication offset của các writes trước đó từ **cùng client connection** trong khoảng timeout. Kết quả trả số replicas đáp ứng, có thể thấp hơn số mong muốn.

**Cần nhớ:** `WAIT` không có nghĩa replicas đã fsync và không tạo bảo đảm đồng bộ tuyệt đối trong mọi kịch bản failover.

Ở Redis versions hỗ trợ, `WAITAOF` có thể giúp chờ xác nhận AOF fsync:

```redis
SET demo:aof "v2"
WAITAOF 1 1 2000
```

Cần xác minh Redis version (lệnh được giới thiệu từ Redis 7.2), AOF configuration và ý nghĩa kết quả local/replica ACK mà Redis trả về.

Monitoring các cơ chế này có thể gồm:

- Số lệnh chờ đạt ngưỡng.
- Số lần chờ timeout/không đủ ACK.
- Độ trễ chờ.
- Số local/replica acknowledgments.
- Khác biệt theo replication group/shard.

Nếu `SET` được gửi qua một connection còn `WAIT` qua connection khác mà không kiểm soát context, không thể mặc định đã chờ đúng write đó.

Cả `WAIT` lẫn `WAITAOF` đều không thay thế backup, source of truth hoặc idempotency.

## 33. Persistence là tín hiệu bổ sung

Một replica có thể đã áp dụng write trong RAM nhưng AOF vẫn chưa fsync. Vì vậy quan sát:

```bash
redis-cli -h redis-node.internal -p 6379 INFO persistence
```

Các trường thường quan trọng:

| Trường | Cần hiểu |
| --- | --- |
| `aof_enabled` | Node có bật AOF không |
| `aof_last_write_status` | Trạng thái ghi AOF gần đây |
| `aof_last_bgrewrite_status` | AOF rewrite gần đây thành công không |
| `rdb_last_bgsave_status` | RDB background snapshot gần đây thành công không |
| `rdb_bgsave_in_progress` | Có snapshot đang chạy không |
| `aof_rewrite_in_progress` | Có rewrite đang chạy không |

Đừng suy ra “replica offset gap=0” nghĩa “đã durable đến disk”. Replication ACK và persistence/fsync là hai tín hiệu khác nhau.

Nếu Redis chỉ làm cache, mức persistence có thể được chọn theo nhu cầu warm-up. Nếu Redis giữ trạng thái quan trọng, phải quan sát cả RDB/AOF, backups và khả năng restore.

## 34. RPO và RTO: giám sát đúng đối tượng

**RPO** hỏi “cho phép mất bao nhiêu dữ liệu sau sự cố?”. Nó không bằng một giá trị offset gap đơn lẻ.

**RTO** hỏi “bao lâu sau sự cố dịch vụ phục vụ lại?”. Cần đo từ ứng dụng thay vì chỉ thời điểm Sentinel thông báo promotion.

Timeline:

```text
t0  primary lỗi
t1  Sentinel/Cluster phát hiện
t2  replica được promote
t3  client refresh topology/reconnect
t4  Spring API ghi thành công trở lại
```

Một cách đo RTO vận hành là `t4 - t0`, nhưng mục tiêu cụ thể còn tùy định nghĩa dịch vụ của tổ chức.

RPO quan sát sau sự cố có thể được ước lượng bằng cách ghi **sequence IDs** cho những writes được ứng dụng ACK và đối chiếu với dữ liệu trên primary mới.

Offset gap giúp phát hiện rủi ro, nhưng không thể một mình suy ra số giao dịch mất.

## 35. Chẩn đoán khi replica lag tăng

Quy trình:

1. **Xác định group/shard:** tránh so sánh nhầm hai data streams.
2. **Xem INFO replication:** primary offset, replica offset, ACK age, link, sync.
3. **Xác minh master identity:** có vừa failover hoặc restart không?
4. **Xem tài nguyên:** CPU, memory, network bandwidth/loss, disk I/O/AOF rewrite.
5. **Xem replication sync:** partial/full resync, backlog, snapshot transfer.
6. **Xem application workload:** burst writes, command lớn, Lua script hoặc key nóng.
7. **Xem Sentinel/Cluster events:** SDOWN, ODOWN, role changes, node health.
8. **Xem ảnh hưởng:** stale replica reads, write rejection, API latency/fallback.
9. **Đợi phục hồi có bằng chứng:** link ổn định, sync kết thúc, gap trở về baseline.
10. **Ghi timeline:** phục vụ phân tích RPO/RTO và đánh giá cấu hình.

Một số nguyên nhân phổ biến:

| Nguyên nhân | Dấu hiệu có thể |
| --- | --- |
| Network chậm/mất gói | Link flap, ACK age tăng |
| Replica CPU quá tải | Apply stream chậm, gap tăng |
| Disk I/O cao | Snapshot/AOF rewrite, latency tăng |
| Primary ghi burst lớn | Offset tăng nhanh, replica đuổi theo |
| Full resync | Sync in progress, network/disk tăng |
| Failover mới xảy ra | Master identity đổi, role/offset reset |
| Client đọc nhầm node | Probe stale trái kỳ vọng |
| Monitoring scrape lệch thời điểm | Offset gap bất thường/âm |

Không kết luận nguyên nhân chỉ từ một ô dashboard.

## 36. Chẩn đoán khi role liên tục đổi

Role flapping:

```text
10:00 primary A -> B
10:03 primary B -> A
10:05 primary A -> B
```

Có thể liên quan:

- Network partition, packet loss hoặc latency spikes.
- Cluster/Sentinel quorum instability.
- Redis process restart.
- Host overload, GC pause hoặc disk stall.
- Failover configuration quá nhạy.
- Failure domains không độc lập.
- Client/control-plane observation chưa hội tụ.

Cần đối chiếu logs từ nhiều Sentinel/Cluster nodes và thời điểm application errors. Đừng vội thay master bằng health check của ứng dụng; vai trò phải do control plane điều phối.

Một cảnh báo nhiều role changes trong khoảng ngắn nên phân biệt với planned maintenance.

## 37. Tình huống: ACK age thấp nhưng replica vẫn stale

Giả sử:

```text
Primary A: slave0.lag=0
Primary A: slave0.offset kém master 20,000 bytes
Spring GET qua replica B: giá trị cũ
```

Không có mâu thuẫn: `lag=0` liên quan ACK age, còn offset gap cho biết stream chưa theo kịp ở thời điểm quan sát. Cộng thêm ứng dụng có thể đọc từ node khác dự kiến.

Điều tra:

1. Kiểm tra `slave0.offset` và `master_repl_offset`.
2. Xác nhận `slave0` là đúng replica B.
3. Đọc `INFO replication` từ B.
4. Xác định Spring read routing.
5. Kiểm tra staleness probe trực tiếp.
6. Xem application cache layer ngoài Redis.

Không dùng `slave0.lag=0` làm bằng chứng read-your-writes.

## 38. Tình huống: offset bằng 0 nhưng link đã down

Một node không có write trong vài phút:

```text
master offset = 900000
replica offset = 900000
```

Nếu replication link vừa down, gap vẫn có thể bằng 0 vì không phát sinh write mới.

Do đó:

```text
offset_gap=0  +  master_link_status=down
```

phải được phân loại là **replication unhealthy**, không phải healthy chỉ vì số chênh bằng 0.

Bộ metric cần đo cả tiến độ lẫn khả năng đồng bộ tiếp tục.

## 39. Tình huống: role đổi nhưng metric trông không đổi

Trước failover:

```text
Spring -> Redis A
INFO role = master
```

Sau failover:

```text
Spring -> Redis B
INFO role = master
```

Nếu chỉ có `currentRole()` trả `primary`, không quan sát được đổi node.

Giải pháp:

- Sentinel: poll `SENTINEL get-master-addr-by-name`.
- Cluster: poll `CLUSTER SHARDS`/`CLUSTER NODES`.
- Ghi node identity/endpoint.
- Dùng Sentinel Pub/Sub chỉ như tín hiệu bổ sung.
- So sánh topology snapshots và phát metric role-change.
- Gắn replication history/generation để reset offset gap.

Đây là lý do **role label** và **primary identity** phải là hai phần dữ liệu khác nhau.

## 40. Tình huống: primary được promote nhưng application vẫn lỗi

Các bước:

1. Sentinel/Cluster báo primary mới.
2. Xác nhận primary mới `ROLE` trả master.
3. Kiểm tra Spring container kết nối tới endpoint mới có được không.
4. Kiểm tra Redis ACL/TLS/hostname verification.
5. Kiểm tra driver reconnect và topology refresh.
6. Xem Redis command timeout và `READONLY`.
7. Thực hiện write thử trong môi trường test hoặc namespace giám sát được phép.
8. Đối chiếu time từ failover event tới write thành công.
9. Xem replicas đang theo primary mới chưa.
10. Kiểm tra RPO trên dữ liệu thử với sequence IDs nếu đây là bài fault test.

Sentinel báo switch-master không đồng nghĩa toàn bộ client fleet đã kết nối và ghi thành công.

## 41. Redis Cluster: quan sát theo shard, không cộng offsets toàn cluster

Sai:

```text
max(master_repl_offset của tất cả primaries)
-
min(slave_repl_offset của tất cả replicas)
```

Phép tính vô nghĩa vì các offsets thuộc streams khác nhau.

Đúng hơn:

```text
for each shard:
    identify current primary
    identify its replicas
    verify common replication history
    calculate gap for each replica
    emit per-shard metrics
```

Có thể tổng hợp các chỉ số cấp cluster:

- Số shards thiếu replica khỏe.
- Số replicas vượt ngưỡng lag.
- Số role changes trong khoảng thời gian.
- Slot coverage và cluster state.
- Số shards đang full sync.
- Tỉ lệ lỗi ứng dụng theo shard nếu biết route.

Với một hot key trên một shard, mức độ lag có thể khác các shards còn lại rất nhiều. Một số trung bình toàn cluster có thể che giấu shard bị lỗi.

## 42. Bảo mật monitoring

Các lệnh:

```text
INFO replication
INFO persistence
ROLE
CLUSTER SHARDS / NODES
SENTINEL master / replicas
```

có thể yêu cầu Redis ACL hoặc quyền từ managed service.

Nguyên tắc:

- Tách monitoring identity khỏi application write identity nếu hạ tầng hỗ trợ.
- Cấp quyền đọc phù hợp, không cấp quyền failover chỉ để thu thập metrics.
- Sử dụng TLS/CA/hostname verification theo yêu cầu.
- Không ghi password vào logs hoặc metric labels.
- Không expose Actuator/Prometheus endpoint công khai nếu có thông tin hệ thống nhạy cảm.
- Không dùng health check để tự gửi `REPLICAOF NO ONE` hoặc `CLUSTER FAILOVER`.
- Với managed Redis, ưu tiên API/metrics mà provider hỗ trợ nếu `CONFIG`/`INFO` bị hạn chế.

Việc giám sát không được trở thành một đường có quyền vô tình thay đổi topology.

## 43. Bài thực hành A: đọc INFO replication

Cho:

```text
master_repl_offset:7000000
slave0:state=online,offset=6998000,lag=0
slave1:state=online,offset=6980000,lag=2
```

Hãy:

1. Tính gap theo bytes.
2. Giải thích vì sao `lag=0` không có nghĩa data staleness 0 ms.
3. Xác định field cần xem trên replicas.
4. Giải thích tại sao không thể đổi gap thành giây bằng hằng số.
5. Nêu điều kiện để phép so sánh offsets hợp lệ.

## 44. Bài thực hành B: failover Sentinel

Trước:

```text
mymaster -> Redis A
Replica B/C theo A
```

Sau:

```text
mymaster -> Redis B
Redis C theo B
```

Thiết kế giám sát:

1. Poll master address từ nhiều Sentinel.
2. Nhận `+switch-master` làm tín hiệu bổ sung.
3. Đối chiếu `ROLE`/`INFO replication` ở nodes.
4. Ghi timeline application errors/reconnect.
5. Đo thời gian tới successful write trên primary mới.
6. Kiểm tra sequence writes đã ACK trước failover.
7. Giải thích vì sao role string vẫn là master nhưng node đã đổi.

## 45. Bài thực hành C: Redis Cluster

Có ba primaries A/B/C, mỗi primary một replica. Primary B lỗi, B1 được promote.

Hãy:

1. Dùng `CLUSTER SHARDS` xác định slot ownership mới.
2. Theo dõi role/node ID trước và sau.
3. Tính replication gap **trong shard B**.
4. Giải thích vì sao không so sánh offset của A với B1.
5. Quan sát các lỗi ứng dụng `MOVED`, `READONLY`, timeout.
6. Đo RTO theo đường business write.

## 46. Bài thực hành D: heartbeat staleness probe

Thiết kế probe:

1. Mỗi 5 giây ghi một sequence vào key monitoring riêng của shard.
2. Đọc trực tiếp từ replica phù hợp.
3. Ghi nhận sequence được nhìn thấy và độ trễ.
4. Không dùng `REPLICA_PREFERRED` nếu client có thể fallback master.
5. Khi master node/replication generation đổi, rebaseline.
6. Đặt TTL, key namespace và giới hạn tải.
7. Phân tích vì sao probe một key không đại diện cho mọi key.

Khoảng 5 giây chỉ là ví dụ bài tập; workload production cần chọn tần suất khác nếu cần.

## 47. Bài thực hành E: fault test với sequence writes

Một kịch bản thử nghiệm cô lập:

1. Dựng primary + replica đủ điều kiện.
2. Ghi các sequence IDs và lưu kết quả `OK` phía client.
3. Thu thập offsets và link state.
4. Gây lỗi primary có kiểm soát.
5. Quan sát promotion và client reconnect.
6. Xác minh primary mới có các sequence IDs nào.
7. Ghi nhận write loss nếu có và downtime thực tế.
8. Đối chiếu metrics đã scrape trong khoảng sự cố.
9. Thử lại với `WAIT`/policy khác và so sánh có điều kiện.
10. Không kết luận zero-data-loss từ một lần test thành công.

Không chạy fault test hoặc lệnh thay đổi role trên Redis production nếu chưa có quy trình vận hành cho phép.

## 48. Ngộ nhận thường gặp

**“`slaveN.lag=0` nghĩa là replica không chậm một mili giây.”** Không. Đó là tín hiệu ACK age, không phải độ cũ mỗi dữ liệu ứng dụng.

**“Offset gap đo bằng giây.”** Không. Nó là chênh lệch bytes trong replication stream theo điều kiện quan sát.

**“Link up tức là bắt kịp.”** Không. Replica có thể lag hoặc full sync.

**“Gap 0 chứng minh không thể mất write.”** Không. Nó chỉ là snapshot ở một thời điểm.

**“Có 2 replicas connected là có 2 failover candidates khỏe.”** Không mặc định. Phải xét lag, sync, election và failure domains.

**“WAIT 1 nghĩa là data an toàn tuyệt đối.”** Không. Chỉ quan sát ACK replication trong phạm vi lệnh.

**“Spring INFO role=master trước và sau nên không có failover.”** Không. Master endpoint có thể đã chuyển.

**“Sentinel events luôn được monitor nhận.”** Không. Pub/Sub có thể bị bỏ lỡ khi subscriber offline.

**“Cluster có một primary chung nên tính một gap toàn cluster.”** Không. Cluster có nhiều shards và replication streams.

**“Exporter nào cũng dùng một tên lag metric giống nhau.”** Không. Cần xác nhận tên và semantics exporter.

**“PING thành công là hệ thống phục hồi.”** Không. Cần application writes và topology/replication ổn định.

**“Monitoring tự ngăn dữ liệu bị mất.”** Không. Đó là quan sát; cần persistence, backup, lựa chọn source of truth và chính sách client phù hợp.

**“Ứng dụng nên tự promote replica khi thấy ROLE sai.”** Không. Sentinel/Cluster điều phối failover, monitor chỉ quan sát.

## 49. Câu hỏi thường gặp

**Độ trễ sao chép Redis đo thế nào?**

Tối thiểu theo dõi offset gap (bytes), ACK age (seconds), replication link/sync state, và nếu cần độ cũ dữ liệu nghiệp vụ thì dùng heartbeat/version probe.

**Nên dùng `INFO replication` hay `ROLE`?**

Cả hai hữu ích. `ROLE` giúp biết vai trò của node đang kết nối; `INFO replication` có nhiều số liệu link, offsets và sync hơn.

**Có cần query mọi Redis data node không?**

Nếu giám sát topology đầy đủ, có. Một `StringRedisTemplate` thông thường không tự trả thông tin toàn bộ replicas/shards.

**Làm sao phát hiện Sentinel đổi master?**

So sánh địa chỉ do `SENTINEL get-master-addr-by-name` trả ở những lần poll; kết hợp `+switch-master` Pub/Sub event làm tín hiệu nhanh.

**Redis Cluster dùng Sentinel events không?**

Không. Redis Cluster có protocol điều phối vai trò riêng; theo dõi qua Cluster topology/roles.

**Replica đọc thấy giá trị cũ khi offset gap nhỏ có bất thường không?**

Không nhất thiết. Replication bất đồng bộ, thời điểm đo và read routing có thể tạo stale read; kiểm tra đường đọc và probe.

**Có nên dùng ACK age làm SLA stale-read?**

Không trực tiếp. ACK age không đo tuổi của mỗi bản ghi. Dùng probe hoặc một hợp đồng consistency tương ứng.

**Có thể tính RPO từ gap bytes không?**

Không chính xác cho số giao dịch. Cần kết hợp replication history, fault test và sequence writes đã ACK.

**Cần đo RTO từ Sentinel switch-master hay từ ứng dụng?**

Để đánh giá trải nghiệm người dùng, cần đo từ lỗi đến lúc ứng dụng thực hiện được request/write thành công; Sentinel event chỉ là một mốc.

**`WAITAOF` thay thế replication metrics không?**

Không. Nó phục vụ xác nhận fsync ở phạm vi lệnh và version phù hợp; vẫn cần quan sát nodes, link, offsets, topology và các lỗi.

**Có cần giám sát AOF/RDB không nếu đã có replica?**

Có nếu mục tiêu durability/recovery yêu cầu. ACK replication không đồng nghĩa fsync và replication không thay backup.

## 50. Tổng kết

Để quan sát độ trễ sao chép và thay đổi vai trò máy chủ trong Spring Data Redis, cần:

1. **Phân biệt ba loại lag:** offset gap, ACK age và application-visible staleness.
2. **Thu thập từ từng data node:** `INFO replication`, `ROLE`, link, sync và offsets.
3. **Theo dõi master identity:** Sentinel master endpoint hoặc Redis Cluster node ID/slot owner, không chỉ role string.
4. **Reset/rebaseline sau failover:** không so sánh offsets khác replication history như một dòng thời gian liên tục.
5. **Quan sát ở tầng Spring:** timeout, `READONLY`, redirects, reconnect, latency và thời điểm writes phục hồi.
6. **Tạo alert có ngữ cảnh:** lag cao, mất link, thiếu replica, role flapping và ảnh hưởng API phải được phân biệt.
7. **Không đánh đồng monitoring với durability:** replication bất đồng bộ và failover vẫn có thể gây stale read hoặc mất write dù lần scrape trước có gap thấp.
8. **Kiểm thử sự cố:** dùng sequence writes, topology thật và đối chiếu application-visible RPO/RTO trong môi trường cô lập.

Khi theo dõi được cả replication progress, control-plane role changes và trải nghiệm thực của Spring client, nhóm phát triển có thể phát hiện lỗi sớm, giải thích sự cố chính xác hơn và thiết kế chính sách khôi phục phù hợp.

## Tài liệu tham khảo

- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – INFO](https://redis.io/docs/latest/commands/info/)
- [Redis – ROLE](https://redis.io/docs/latest/commands/role/)
- [Redis – Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis – SENTINEL commands](https://redis.io/docs/latest/commands/sentinel/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – CLUSTER NODES](https://redis.io/docs/latest/commands/cluster-nodes/)
- [Redis – CLUSTER SHARDS](https://redis.io/docs/latest/commands/cluster-shards/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis – Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Spring Data Redis – Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
