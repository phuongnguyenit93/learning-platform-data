# Phối hợp persistence với replication và failover trong Spring Data Redis

## 1. Mục tiêu: Redis có bản sao và tự failover chưa chắc đã bền dữ liệu

Giả sử ứng dụng Spring Boot ghi một yêu cầu quan trọng vào Redis:

```text
T0  Spring Boot -> Redis primary: SET reservation:42 CONFIRMED
T1  Redis primary trả OK
T2  Redis primary gặp sự cố
T3  Một replica được promote thành primary mới
T4  Spring Boot GET reservation:42 -> không có key
```

Tại sao có thể xảy ra, dù hệ thống đã có replication và failover? Vì Redis replication thông thường **bất đồng bộ**: primary có thể phản hồi `OK` trước khi replica được chọn nhận write. Nếu primary chết hoặc mất khả năng phục hồi đúng trong cửa sổ đó, master mới có thể thiếu dữ liệu vừa ghi.

Thêm persistence (RDB hoặc AOF) vào các node giúp tăng khả năng khôi phục dữ liệu **từ đĩa của từng node**, nhưng không tự biến replication thành đồng bộ, không buộc failover chọn node có mọi write đã ACK, và không bảo đảm không mất dữ liệu trong mọi tình huống.

Ba trục phải được thiết kế cùng nhau:

1. **Persistence:** dữ liệu của một Redis process có thể khôi phục như thế nào sau restart hoặc crash?
2. **Replication:** dữ liệu từ primary đã đi tới các replicas ở mức nào?
3. **Failover:** khi primary mất, node nào được chọn thay thế, và node đó có trạng thái nào?

Trong Spring Data Redis, còn trục thứ tư: **client behavior**. Client phải tìm lại primary, xử lý lỗi kết nối và retry mà không tạo tác dụng phụ trùng.

> **Nguyên tắc:** Persistence bảo vệ bản sao cục bộ; replication tạo bản sao trên node khác; failover chuyển trách nhiệm xử lý. Độ bền dữ liệu end-to-end phụ thuộc cả ba cùng chính sách của ứng dụng, filesystem, network và khôi phục sự cố.

## 2. Sơ đồ tổng thể

Một triển khai Redis master–replicas có Sentinel:

```text
                            Spring Boot
                           RedisTemplate
                                |
                          Redis client
                                |
                     +----------+----------+
                     |                     |
                     v                     v
              Sentinel quorum       Redis primary A
              (discovery/HA)          |
                                      | SET key=value
                                      | -> OK có thể đến trước khi
                                      |    replica nhận write
                                      |
                          +-----------+-----------+
                          |                       |
                          v                       v
                    Replica B                Replica C
                          |                       |
                      local RDB/AOF            local RDB/AOF
                          |
                 failover có thể promote
                          v
                    New primary B
```

Ở đây:

- Sentinel hỗ trợ xác định node mới là master.
- Redis primary và từng replica có **thiết lập persistence riêng**.
- Replication đưa thay đổi giữa các node theo cơ chế riêng.
- File RDB/AOF của node A **không phải** một ổ đĩa chia sẻ mà node B lập tức sử dụng khi được promote.
- Khi failover hoàn tất, ứng dụng cần ghi vào node được promote, không thể tiếp tục gửi write vào node cũ.

Redis Cluster cũng có cơ chế replication/failover, nhưng được tổ chức theo **từng shard/hash slot**, không dùng Sentinel để tự điều phối failover của mỗi cluster shard.

## 3. Phân biệt durability, availability, consistency và recovery

Bốn thuật ngữ rất dễ bị dùng lẫn:

| Thuộc tính | Câu hỏi | Cơ chế liên quan |
| --- | --- | --- |
| Durability | Dữ liệu đã ghi có sống sót sau crash hay không? | RDB, AOF, fsync, storage, backup |
| Availability | Khi một node lỗi, service có thể tiếp tục phục vụ không? | Replication, Sentinel/Cluster failover |
| Consistency | Những client khác nhau thấy cùng trạng thái khi nào? | Replication lag, primary/replica reads, versioning |
| Recoverability | Khi nhiều node hỏng hoặc dữ liệu bị xóa sai, khôi phục từ đâu? | Backup, PITR nếu có hệ hỗ trợ, restore runbook |

Ví dụ:

- Một Redis server có AOF tốt nhưng **không có replica**: có khả năng khởi động lại với dữ liệu đã lưu nhưng có thể downtime lâu khi máy chết.
- Một primary có hai replicas nhưng **persistence tắt hoàn toàn**: có nhiều bản sao trong RAM, có khả năng HA nếu một node lỗi, nhưng mất đồng thời hoặc restart sai thứ tự có thể gây mất dữ liệu.
- Một Redis Cluster có nhiều shards và replicas: có phân mảnh, khả năng failover; nhưng vẫn có nguy cơ write loss vì asynchronous replication.
- Một database transaction ghi dữ liệu chuẩn và Redis chỉ làm cache: Redis mất dữ liệu có thể gây cache miss, không nhất thiết mất trạng thái nghiệp vụ.

Trước khi chỉnh `appendfsync` hay số replica, phải biết **Redis là cache có thể tái tạo hay là nguồn dữ liệu có thẩm quyền**.

## 4. Persistence là gì?

Persistence là cơ chế đưa trạng thái Redis từ bộ nhớ sang phương tiện lưu trữ để Redis có khả năng khôi phục sau restart.

Redis hỗ trợ các lựa chọn chính:

- **RDB snapshots:** chụp trạng thái dữ liệu tại một thời điểm, lưu file snapshot.
- **AOF (Append Only File):** ghi lại các thao tác làm thay đổi dữ liệu để có thể tái dựng trạng thái khi khởi động.
- **Kết hợp RDB và AOF:** một deployment có thể bật cả hai.
- **Không persistence:** dữ liệu chỉ tồn tại trong bộ nhớ; thích hợp với một số cache hoàn toàn có thể tái tạo, nhưng phải hiểu rủi ro khi kết hợp replication/failover.

Không có lựa chọn nào tự bảo đảm tuyệt đối trước mọi loại lỗi: lỗi storage, cấu hình sai, xóa dữ liệu bởi người vận hành, replication of bad data và toàn bộ failure domain bị mất vẫn cần kế hoạch riêng.

## 5. RDB: snapshot theo thời điểm

RDB lưu một bản chụp dữ liệu Redis, thường thông qua cơ chế background save.

Ví dụ cấu hình `redis.conf`:

```conf
save 900 1
save 300 10
save 60 10000

dbfilename dump.rdb
dir /var/lib/redis
stop-writes-on-bgsave-error yes
```

Các dòng `save` mô tả ngưỡng thời gian và số lần thay đổi dữ liệu để Redis thực hiện snapshot tự động, không có nghĩa cứ chính xác 900 giây là đã có một snapshot mới.

Dạng khái niệm:

```text
10:00   Redis có dataset version A
10:01   RDB snapshot ghi version A
10:03   Thêm write B, C, D trong RAM
10:04   Redis process/host crash
10:05   Restart và load RDB gần nhất -> có thể chỉ có version A
```

Nếu chưa có bản snapshot mới, những write sau snapshot có thể mất khi node khởi động lại từ RDB.

### Ưu điểm RDB

- File snapshot gọn, thuận tiện cho một số quy trình backup/restore.
- Có thể hỗ trợ khởi động lại dataset lớn hiệu quả theo điều kiện hệ thống.
- Là một bản chụp nhất quán ở thời điểm snapshot thành công theo cơ chế Redis.
- Hữu ích cho chiến lược lưu trữ nhiều phiên bản backup.

### Giới hạn RDB

- **Cửa sổ mất dữ liệu** có thể bằng khoảng thời gian từ snapshot thành công gần nhất đến sự cố.
- Background save tạo áp lực CPU, I/O, bộ nhớ, copy-on-write.
- Nếu disk đầy hoặc permission sai, snapshot có thể lỗi.
- Có file `dump.rdb` không có nghĩa nó mới nhất, hợp lệ hoặc đã được copy ra khỏi failure domain.
- Snapshot không ngăn application ghi sai hay xóa nhầm dữ liệu; bản chụp mới cũng có thể chứa dữ liệu sai.

RDB phù hợp khi có thể chấp nhận một khoảng RPO nhất định, hoặc làm lớp snapshot/backup bổ sung khi AOF được bật.

## 6. AOF: ghi lại thay đổi và chính sách fsync

AOF ghi lại các lệnh làm thay đổi dữ liệu theo cơ chế log của Redis. Redis sử dụng log này để tái dựng trạng thái khi khởi động.

Ví dụ:

```conf
appendonly yes
appendfsync everysec
```

Ba chính sách thường gặp:

| `appendfsync` | Ý nghĩa thực tế | Đánh đổi |
| --- | --- | --- |
| `always` | Yêu cầu đồng bộ AOF xuống storage thường xuyên, theo từng write | Tăng chi phí I/O và latency, thường bền hơn |
| `everysec` | Redis chủ động fsync theo chu kỳ xấp xỉ mỗi giây | Cân bằng throughput và rủi ro mất write gần nhất |
| `no` | Để OS quyết định thời điểm flush | Có thể có cửa sổ mất dữ liệu lớn hơn |

**Không diễn giải quá mức:** với `everysec`, người ta thường nói “có thể mất khoảng một giây dữ liệu” trong kịch bản crash thông thường. Đây **không phải cam kết cứng** rằng mọi tình huống, kể cả disk stall, power failure hoặc lỗi filesystem, đều mất tối đa đúng một giây.

Tương tự, `always` làm giảm cửa sổ mất dữ liệu do buffer chưa fsync nhưng không chứng minh tuyệt đối an toàn trước mọi lỗi phần cứng, firmware, storage controller hay cấu hình hạ tầng.

### Timeline AOF everysec

```text
T0       AOF đã được fsync
T0+100ms SET x 1 -> OK
T0+300ms SET y 2 -> OK
T0+500ms host crash trước lượt fsync tiếp theo
```

Một số write đã ACK có thể chưa được lưu đủ để khôi phục từ local AOF, tùy tình trạng OS/storage và file log.

**ACK Redis command không mặc định bằng ACK fsync xuống đĩa.**

## 7. Khi bật cả RDB và AOF

Ví dụ cấu hình kết hợp:

```conf
appendonly yes
appendfsync everysec

save 900 1
save 300 10
save 60 10000

dir /var/lib/redis
dbfilename dump.rdb
appenddirname appendonlydir
aof-use-rdb-preamble yes
```

Khi bật cả RDB và AOF, Redis thường ưu tiên khôi phục từ AOF nếu có dữ liệu AOF phù hợp, bởi AOF được thiết kế có thể mới hơn snapshot RDB.

RDB vẫn có thể phục vụ mục tiêu snapshot hoặc backup. AOF giúp giảm cửa sổ mất dữ liệu so với chỉ chụp snapshot không thường xuyên.

**Nhưng bật cả hai không đơn giản là “RDB + AOF = không mất dữ liệu”**. Cần xét:

- AOF đã fsync đến đâu.
- RDB snapshot cuối cùng thành công khi nào.
- File có nằm trên storage bền vững không.
- Disk còn đủ dung lượng cho AOF rewrite và snapshot không.
- Node khác có các bản sao mới đến đâu.
- Failover có chọn bản sao chứa write vừa ACK không.
- Backup có tồn tại ở nơi độc lập với host hiện tại không.

### AOF rewrite

AOF không thể tăng vô hạn mà không có cơ chế tối ưu. Redis có khả năng rewrite/compact log để giảm kích thước dữ liệu cần replay.

Trong các phiên bản Redis hiện đại, AOF có thể được quản lý dưới dạng nhiều file với manifest, base file và incremental files. Vì vậy, **không nên giả định chỉ cần copy một file `appendonly.aof` đang mở là đã backup an toàn toàn bộ AOF**.

Một kế hoạch backup/restore AOF phải tuân thủ layout và quy trình nhất quán của Redis version đang vận hành.

## 8. Persistence được cấu hình theo từng Redis node

Trong topology primary–replicas, **mỗi Redis process quản lý bộ nhớ, disk và persistence cục bộ của nó**.

```text
Primary A:
  RAM data A
  /var/lib/redis/dump.rdb
  /var/lib/redis/appendonlydir/...

Replica B:
  RAM replica of A
  /var/lib/redis/dump.rdb
  /var/lib/redis/appendonlydir/...
```

Đừng giả định rằng vì Primary A đã bật AOF nên Replica B tự có cùng chính sách fsync. Replication truyền dữ liệu/commands, **không đồng nghĩa mọi cấu hình disk/persistence được đồng bộ giống nhau**.

Khi Replica B được promote:

- B tiếp tục dùng dữ liệu nó đang giữ.
- B có thể tiếp tục áp dụng persistence settings của chính process B.
- Nếu B không có AOF hoặc dùng policy yếu hơn, durability sau failover có thể khác A.
- Khi A trở lại và được cấu hình làm replica của B, quá trình resynchronization có thể thay đổi dataset cục bộ của A theo dữ liệu master mới.

Vì vậy production cần cấu hình persistence nhất quán **trên tất cả các nodes có thể được promote**, trừ khi có thiết kế được tài liệu hóa rõ ràng cho vai trò từng node.

## 9. Replication: bản sao dữ liệu không mặc định đồng bộ

Redis replication thường là bất đồng bộ. Primary gửi thay đổi cho replica qua replication stream; replica áp dụng chúng theo trạng thái kết nối và tốc độ xử lý của mình.

```text
Primary A                         Replica B
---------                         ---------
SET key=v2
apply in memory
reply OK to Spring
   |
   +---------- replication ------> apply key=v2
```

Trong khoảng từ lúc primary ACK đến lúc replica áp dụng write, hai node có thể khác nhau.

**Replication offset** là một trong những chỉ số giúp theo dõi sự tiến bộ của replica, nhưng offset tăng không tự chứng minh mọi write đã được fsync lên disk của replica.

### Partial resynchronization và full resynchronization

Khi kết nối replication bị gián đoạn ngắn, Redis có thể thực hiện partial resync nếu replication backlog và các điều kiện protocol còn cho phép. Nếu không, replica có thể cần full resynchronization.

Trong quá trình full resync:

- Dữ liệu replica có thể cần được thay thế bằng snapshot/trạng thái master.
- Network, CPU, disk và memory có thể chịu thêm tải.
- Replica chưa chắc đã sẵn sàng phục vụ read/failover theo kỳ vọng tại mọi thời điểm.
- Nếu Redis có dữ liệu ghi sai trên master mới, replication có thể đưa trạng thái sai đó tới replicas.

**Replication không phải backup lịch sử.** Một lệnh `DEL` sai trên primary có thể được replicate tới toàn bộ replicas.

## 10. Trường hợp 1: primary ACK nhưng replica chưa nhận write

Timeline:

```text
T0  Primary A và Replica B cùng có state v1
T1  Spring -> A: SET state v2
T2  A trả OK
T3  A crash trước khi B nhận write
T4  Failover promote B
T5  B vẫn có state v1
```

Trong trường hợp này:

- Sharding/replication topology có thể khôi phục khả năng phục vụ.
- Redis data trên primary mới có thể **cũ hơn** dữ liệu mà Spring đã được báo `OK`.
- Nếu A có local AOF chứa v2, file này vẫn không tự quyết định kết quả failover khi B được chọn làm master.
- Khi A tham gia lại với vai trò replica của B, trạng thái A có thể bị đồng bộ theo B.

**Kết luận:** một write đã được ACK không đủ để suy ra “chắc chắn có trên replica sẽ được chọn”.

## 11. Trường hợp 2: primary đã fsync, nhưng replica được promote thiếu write

Giả sử Primary A dùng AOF `appendfsync always` và đã fsync write v2:

```text
A: v2 đã lưu trên disk
B: vẫn v1 vì replication chưa tới

A bị cô lập khỏi cluster
B được promote thành primary
Spring đọc B -> v1
```

AOF của A vẫn có thể chứa v2, nhưng cluster hiện phục vụ từ B với v1. Nếu A quay lại làm replica B, cluster không tự động “merge mọi write mới nhất từ cả hai” theo ý nghĩa nghiệp vụ.

Điều này minh họa **local persistence và failover selection là hai việc khác nhau**.

Muốn giảm nguy cơ, phải cân nhắc thêm replication acknowledgments, write policy, thậm chí sử dụng một nguồn dữ liệu chuẩn có bảo đảm giao dịch mạnh hơn cho những dữ liệu không được phép mất.

## 12. Trường hợp 3: replicas giữ dữ liệu nhưng không ai có disk bền vững

```text
Primary A:   persistence off
Replica B:   persistence off
Replica C:   persistence off
```

Khi một node A lỗi, B/C có thể giữ dữ liệu trong RAM và hỗ trợ failover. Nhưng nếu cả topology restart, có thể không có bản lưu bền vững đủ để khôi phục dataset.

Một kịch bản đặc biệt cần tránh là **một master không persistence tự khởi động lại rỗng trong khi hệ thống replication chưa được kiểm soát**. Nếu các replicas đồng bộ theo một master rỗng trong thời điểm sai, kết quả có thể làm mất dữ liệu đang giữ trên replicas.

Với môi trường dùng Redis chỉ làm cache có thể xây lại, persistence off có thể được chọn sau khi chấp nhận điều kiện phục hồi. Với Redis lưu trạng thái nghiệp vụ duy nhất, đây là một quyết định rủi ro cao.

**Không đánh đồng “có nhiều bản sao trong RAM” với “có bản backup an toàn sau mất điện toàn hệ thống”.**

## 13. Trường hợp 4: dữ liệu xóa sai được replicate

```text
T0  Primary A và replicas có dữ liệu hợp lệ
T1  Operator/script gửi DEL orders:all:important
T2  Primary A xóa
T3  Replicas cũng nhận xóa
T4  Failover sang replica
T5  Dữ liệu vẫn đã bị xóa
```

Replication làm các nodes giữ trạng thái tương tự master, kể cả khi trạng thái đó **sai về nghiệp vụ**. Failover không quay về thời điểm trước khi lệnh xóa sai chạy.

Nếu cần phục hồi dữ liệu bị xóa nhầm, phải có **backup độc lập**, chính sách retention, bảo vệ quyền truy cập và runbook restore.

Một backup chưa từng được kiểm tra restore cũng chưa đủ để khẳng định hệ thống có khả năng recovery.

## 14. Khi nào persistence có ý nghĩa nếu đã có replicas?

Có ít nhất bốn lợi ích:

1. **Restart cục bộ:** node có thể nạp dữ liệu từ disk thay vì bắt buộc nhận full sync từ master trong mọi kịch bản.
2. **Sự cố đồng thời:** khi nhiều nodes mất RAM/process, bản lưu disk giúp tăng lựa chọn phục hồi.
3. **Backup/snapshot:** cung cấp dữ liệu đầu vào cho các bản sao độc lập và quy trình DR.
4. **Kiểm soát cửa sổ mất dữ liệu cục bộ:** AOF fsync policy cho phép đánh đổi độ bền và chi phí I/O.

Tuy nhiên persistence vẫn không thay thế:

- Replica để giảm thời gian gián đoạn.
- Failover controller để đổi primary.
- Backup để phục hồi từ lỗi logic/corruption.
- Idempotency để tránh tác dụng phụ trùng khi client không rõ kết quả write.
- Nguồn dữ liệu chuẩn khác khi yêu cầu consistency vượt bảo đảm Redis deployment.

## 15. Sentinel: phát hiện master và phối hợp failover

Ở mô hình Redis primary–replica không sharding, **Redis Sentinel** giám sát master/replicas và phối hợp failover.

Ví dụ:

```text
               Sentinel A
               Sentinel B
               Sentinel C
                    |
                    v
                 Master A
                    |
                   sync
                    v
                 Replica B
```

Nếu Master A lỗi và các điều kiện quorum/authorization phù hợp, Sentinel có thể promote Replica B thành master.

Sau failover:

```text
Spring client hỏi Sentinel -> master mới là Replica B
Spring kết nối dữ liệu -> B
```

Sentinel không phải bản sao của dữ liệu nghiệp vụ; Sentinel không tự lưu mọi write của master. Nó điều phối topology. Độ mới của dữ liệu trên B vẫn phụ thuộc replication trước khi failover.

### Config Sentinel đơn giản

Ví dụ file cấu hình Sentinel:

```conf
port 26379
sentinel monitor mymaster 10.10.0.11 6379 2
sentinel down-after-milliseconds mymaster 10000
sentinel failover-timeout mymaster 60000
sentinel parallel-syncs mymaster 1
```

Các địa chỉ và ngưỡng chỉ là minh họa. Với Sentinel, cần một topology đủ replicas/Sentinels, trải trên các failure domains phù hợp, và client tới được địa chỉ Redis master do Sentinel công bố.

**Số Sentinel và quorum không tự đảm bảo “không mất write”**. Chúng chủ yếu phục vụ failure detection/election.

## 16. Redis Cluster: replication và failover trong từng shard

Redis Cluster phân phối key theo hash slots cho nhiều primary nodes. Mỗi primary có thể có replica riêng.

```text
Redis Cluster
  Primary A (slots A) ----> Replica A1
  Primary B (slots B) ----> Replica B1
  Primary C (slots C) ----> Replica C1
```

Khi Primary B lỗi, Replica B1 có thể được promote để tiếp quản **slots B**. Nó không tự tiếp quản keys của A và C.

Ở đây có ba cơ chế:

- **Sharding:** phân phối 16.384 slots giữa các primaries.
- **Replication:** mỗi replica sao chép dataset của shard tương ứng.
- **Failover:** primary của shard được thay bởi replica.

Mọi lập luận về durability cần thực hiện **theo từng shard và từng replica**, không chỉ xem cluster tổng thể có bao nhiêu nodes.

### Sentinel và Cluster không được dùng thay thế cấu hình cho nhau

Trong Spring Data Redis:

- `RedisSentinelConfiguration` dùng master name và Sentinel addresses.
- `RedisClusterConfiguration` dùng cluster seed nodes và slot topology.

Redis Cluster có cơ chế failover của riêng nó, không cần Sentinel để thực hiện failover của các cluster primaries.

## 17. Mục tiêu RPO và RTO trước khi chọn cấu hình

**RPO (Recovery Point Objective)**: mức mất dữ liệu mà hệ thống chấp nhận khi phục hồi, ví dụ có thể mất tối đa dữ liệu từ một khoảng thời gian trước sự cố theo mục tiêu nghiệp vụ.

**RTO (Recovery Time Objective)**: thời gian mục tiêu để dịch vụ hoạt động lại sau sự cố.

Cần tách:

```text
Durability target:
  RPO: có thể mất bao nhiêu dữ liệu?

Availability target:
  RTO: có thể gián đoạn bao lâu?
```

Ví dụ giả định:

| Loại dữ liệu | RPO mong muốn | RTO mong muốn | Định hướng |
| --- | --- | --- | --- |
| Cache bài viết có thể tái tạo | Có thể mất toàn bộ cache | Ngắn | Replicas/HA tùy latency; fallback DB |
| Cache sản phẩm | Có thể mất bản sao cache | Ngắn | TTL, read-through/cache-aside, HA |
| Session đăng nhập | Giới hạn theo trải nghiệm người dùng | Ngắn | Replicas, persistence, chính sách session |
| Job queue quan trọng | Không bỏ công việc đã chấp nhận | Theo SLA công việc | Durable queue/ledger, idempotency |
| Dữ liệu thanh toán | Rất thấp hoặc gần zero | Theo mục tiêu hệ thống | Nguồn chuẩn transaction mạnh, outbox |

**Không chọn `appendfsync everysec` rồi mặc định đó là “RPO đúng 1 giây”**. RPO cần xét cả failover sang replica chưa nhận write, mất nhiều nodes, storage failures và kịch bản vận hành.

## 18. Chính sách AOF/RDB so với RPO/RTO

| Chế độ | Điểm mạnh | Rủi ro chính |
| --- | --- | --- |
| RDB theo chu kỳ | Backup snapshot gọn, khôi phục từ snapshot | Có thể mất writes sau snapshot |
| AOF `everysec` | Cân bằng hiệu năng/độ bền cục bộ | Có thể mất phần log chưa fsync, không có giới hạn cứng trong mọi lỗi |
| AOF `always` | Giảm cửa sổ dữ liệu chưa fsync | Chi phí I/O, latency và phụ thuộc chất lượng storage |
| RDB + AOF | Có cả snapshot và log gần nhất | Không loại bỏ async replication/failover loss |
| Persistence off | Giảm I/O persistence | Restart nhiều nodes có thể mất dataset |
| Replicas nhưng không backup | HA khi một số nodes lỗi | Không phục hồi tốt khi xóa nhầm, corruption lan rộng |
| Backup ra storage độc lập | Phục hồi lỗi nhiều nodes hoặc lỗi logic | Restore có độ trễ và cần test |

Không có chế độ chung nào tối ưu cho mọi workload. Với Redis chỉ là cache, độ bền cục bộ có thể ít quan trọng hơn latency. Với Redis làm nguồn chuẩn của dữ liệu đặc biệt quan trọng, cần phân tích sâu khả năng mất write và có thể phải chọn kiến trúc dữ liệu khác.

## 19. Giảm nguy cơ mất write bằng min-replicas-to-write

Redis hỗ trợ các cấu hình:

```conf
min-replicas-to-write 1
min-replicas-max-lag 10
```

Ý tưởng: master có thể từ chối các write khi không có đủ số replicas được đánh giá có replication lag chấp nhận được.

Ví dụ mong muốn ít nhất một replica được kết nối với lag theo chính sách dưới 10 giây.

**Tác dụng:** giảm việc primary tiếp tục chấp nhận writes trong khi hoàn toàn không có replica đủ điều kiện.

**Nhưng không bảo đảm:**

- Write cụ thể vừa ACK đã có trên replica.
- Replica đã fsync write lên disk.
- Failover sẽ chọn đúng replica đã nhận write đó.
- Không mất dữ liệu khi nhiều nodes hỏng.
- Không có lỗi trong khoảng kiểm tra điều kiện và replication thực tế.

Các thiết lập này tăng độ chặt chẽ của chính sách chấp nhận ghi, đổi lại **availability** có thể giảm: Redis từ chối write trong những giai đoạn replica lag/mất kết nối dù primary còn online.

### Vì sao không chọn min-replicas quá cao?

Nếu yêu cầu nhiều replicas đồng thời khỏe nhưng topology thường xuyên có một node bảo trì, ứng dụng có thể bị từ chối ghi không cần thiết so với mục tiêu HA.

Chọn các giá trị dựa trên:

- Số replicas thực sự.
- Network lag và tải.
- RPO mục tiêu.
- Mức sẵn sàng của writes chấp nhận được.
- Thực tế vận hành và monitoring.

## 20. WAIT: chờ xác nhận replication, nhưng không phải transaction đồng bộ

Redis có lệnh:

```redis
WAIT numreplicas timeout
```

Ví dụ một session redis-cli kết nối tới primary:

```redis
SET order:42 CONFIRMED
WAIT 1 2000
```

Ở đây `WAIT 1 2000` cố chờ ít nhất một replica xác nhận đã xử lý replication offset tương ứng với các writes trước đó trên **cùng client connection**; timeout tính bằng milliseconds.

Lệnh có thể trả số replicas đáp ứng yêu cầu, không nhất thiết đúng bằng số được yêu cầu.

Ví dụ:

```text
WAIT trả 1 -> có ít nhất 1 replica xác nhận replication theo điều kiện
WAIT trả 0 -> chưa có replica đủ điều kiện trong thời gian chờ
```

**Điểm cực kỳ quan trọng:**

- `WAIT` không biến replication thành giao thức ghi đồng bộ tuyệt đối.
- ACK replication không đồng nghĩa replica đã fsync vào AOF.
- `WAIT` chỉ quan sát trạng thái replication đã đạt được tại thời điểm nhất định.
- Sau `WAIT`, topology và failures vẫn có thể thay đổi.
- Một replica đã ACK vẫn có thể mất RAM/disk trong sự cố tiếp theo.
- Failover không có hợp đồng với từng client rằng replica được promote chính là replica trả ACK trong `WAIT`.

Do đó, `WAIT` giúp giảm một số cửa sổ rủi ro, **không đảm bảo zero data loss**.

### Vì sao cùng connection quan trọng?

Lệnh `WAIT` được thiết kế để chờ replication offset của các writes trước đó do client thực hiện trên connection. Nếu ứng dụng gửi `SET` và `WAIT` trên những connection khác nhau mà không kiểm soát được context, không thể mặc định `WAIT` đang chờ chính write vừa gửi.

Đây là điểm cần chú ý khi dùng connection pooling hoặc Spring Data Redis abstractions.

## 21. WAIT với Spring Data Redis: giao tiếp mức thấp cần được kiểm soát

Một minh họa quan trọng là **connection boundary**:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.core.RedisTemplate;

public class ReplicatedWriteExample {

    private final RedisTemplate<String, String> redis;

    public ReplicatedWriteExample(
            RedisTemplate<String, String> redis) {
        this.redis = redis;
    }

    public Long writeAndWait(String key, String value) {
        return redis.execute((RedisConnection connection) -> {

            byte[] keyBytes =
                key.getBytes(StandardCharsets.UTF_8);
            byte[] valueBytes =
                value.getBytes(StandardCharsets.UTF_8);

            connection.stringCommands().set(keyBytes, valueBytes);

            // Pseudocode ở tầng connection:
            // Chỉ sau write, gọi WAIT trên *cùng* connection.
            // API low-level/driver để gửi WAIT phụ thuộc phiên bản
            // Spring Data Redis, Lettuce hoặc Jedis.
            //
            // return numberOfReplicasThatAcknowledged;
            return 0L;
        });
    }
}
```

Đoạn trên là **minh họa vị trí cần gắn lệnh WAIT**, không phải triển khai bảo đảm replication: giá trị `0L` là placeholder, không phải kết quả thật từ Redis. Muốn sử dụng thật, cần dùng đúng API `WAIT`/server command được hỗ trợ trong phiên bản Spring Data Redis/driver đang chạy, kiểm tra cùng connection và xử lý giá trị trả về.

Nếu chỉ viết:

```java
redis.opsForValue().set(key, value);
// Một lệnh WAIT gửi tùy tiện qua connection khác
```

thì không nên tuyên bố đã chờ write ở dòng trước được replicate.

Với hệ thống cần bảo đảm mạnh, phải document chính xác transaction/connection boundary và có integration test trên Redis thật.

## 22. WAITAOF và phạm vi áp dụng

Các phiên bản Redis mới hỗ trợ lệnh **`WAITAOF`** (được giới thiệu ở Redis 7.2) để chờ xác nhận mức ghi AOF cho những writes trước đó trong bối cảnh phù hợp.

Ý tưởng:

```redis
SET order:42 CONFIRMED
WAITAOF 1 1 2000
```

Cú pháp khái niệm:

```text
WAITAOF numlocal numreplicas timeout
```

Trong ví dụ, client yêu cầu điều kiện local AOF và một replica theo semantics của lệnh, với timeout 2000 milliseconds.

Cần hiểu rõ:

- Redis server phải hỗ trợ `WAITAOF`.
- AOF phải được cấu hình phù hợp trên các nodes được yêu cầu.
- Cùng như `WAIT`, kết quả phụ thuộc những writes trước đó trên **client connection**.
- Cần kiểm tra kết quả số local/replica acknowledgments mà command trả về; không mặc định gọi thành công nghĩa là đạt mọi ngưỡng.
- Nó giúp chờ một mức AOF durability, nhưng **không thay thế backup, transaction nghiệp vụ, quorum storage hoặc một consensus database**.
- Driver/framework version có thể chưa expose API tiện lợi, phải dùng API command phù hợp và test.

Không dùng `WAITAOF` trên Redis version không hỗ trợ, không coi `WAITAOF` là giải pháp thay thế cho thiết kế persistence/replication/failover tổng thể.

## 23. Spring Boot kết nối Redis Sentinel

Nếu dùng Sentinel, Spring Boot hiện đại có thể cấu hình:

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

`mymaster` phải khớp tên logic mà Sentinel theo dõi, không phải hostname.

Với dependency Spring Data Redis phù hợp, ứng dụng có thể dùng:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisStateService {

    private final StringRedisTemplate redis;

    public RedisStateService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void putStatus(String id, String status) {
        redis.opsForValue().set("state:" + id, status);
    }

    public String getStatus(String id) {
        return redis.opsForValue().get("state:" + id);
    }
}
```

Driver được cấu hình Sentinel sẽ tìm master hiện tại theo discovery, nhưng **không tự đảm bảo write durability chỉ vì đang dùng Sentinel**.

### Không đưa persistence settings vào YAML Spring mà tưởng Redis đã bật AOF

Các setting như:

```conf
appendonly yes
appendfsync everysec
save 300 10
```

là **cấu hình Redis server/process**, không phải thuộc tính Spring Boot dùng để bật AOF trên mọi node. Spring `application.yml` chủ yếu xác định **cách client kết nối Redis**.

Nếu team vận hành Redis bằng Terraform/Helm/Redis Operator, các Redis server settings phải được quản lý ở đúng lớp hạ tầng.

## 24. Spring Boot kết nối Redis Cluster

Với Redis Cluster, cấu hình khác Sentinel:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      cluster:
        nodes:
          - redis-node-1.internal:6379
          - redis-node-2.internal:6379
          - redis-node-3.internal:6379
        max-redirects: 5
      connect-timeout: 3s
      timeout: 3s
```

Các node này là cluster seeds; client khám phá hash slots và các nodes.

Điều cần nhớ:

- Mỗi shard có persistence settings trên primary và replicas tương ứng.
- Nếu một shard mất primary, replica của **shard đó** có thể được promote.
- Nếu cả primary và replicas của một shard đều lỗi, không có bản sao sẵn sàng của slots đó.
- Cluster resharding không phải replication và cũng không phải backup.
- Khi write liên quan nhiều keys khác slots, Redis Cluster không tự tạo một distributed transaction.

### Spring Data Redis Java configuration

Nếu không dùng auto-configuration:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ClusterConnectionConfig {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {

        RedisClusterConfiguration cluster =
            new RedisClusterConfiguration(
                List.of(
                    "redis-node-1.internal:6379",
                    "redis-node-2.internal:6379",
                    "redis-node-3.internal:6379"
                )
            );

        cluster.setMaxRedirects(5);
        return new LettuceConnectionFactory(cluster);
    }
}
```

Khi tự tạo factory, phải tự cấu hình thêm auth/TLS/timeout/topology refresh theo yêu cầu. Không nên tạo một custom factory rồi mặc định mọi `spring.data.redis.*` property còn được Spring Boot gắn vào bean đó.

## 25. Lựa chọn Lettuce/Jedis và xử lý topology

Spring Data Redis có thể dùng Lettuce hoặc Jedis tùy dependency/phiên bản.

Lettuce hỗ trợ Redis Cluster và Sentinel theo các configuration tương ứng; client có cơ chế reconnect và topology discovery/refresh.

Nhưng reconnect thành công không đồng nghĩa:

- Command trước khi mất connection chắc chắn đã fail.
- Command trước khi mất connection chắc chắn thành công.
- Replica mới chắc chắn có write vừa được ACK.
- Các lệnh non-idempotent có thể tự retry vô điều kiện.

Các trường hợp như `MOVED`, `ASK`, `READONLY`, connection reset, timeout trong failover cần được xử lý theo driver và nghiệp vụ. Application nên có metrics, retry policy và idempotency key cho những write có tác dụng phụ.

### Đọc replica và tính nhất quán

Một số ứng dụng cấu hình Lettuce để đọc replicas cho workload có thể chấp nhận stale data:

```java
import io.lettuce.core.ReadFrom;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .readFrom(ReadFrom.REPLICA_PREFERRED)
        .build();
```

Khi dùng tùy chọn này, replica có thể trả giá trị cũ do replication lag. Đối với nghiệp vụ yêu cầu read-your-writes, phải xác định đường đọc có thẩm quyền; không bật replica reads chỉ vì tăng throughput.

## 26. Xử lý write timeout: không biết lệnh đã thực hiện hay chưa

Một lỗi quan trọng hơn mất kết nối đơn thuần là **kết quả mơ hồ**.

```text
Spring -> Redis primary: INCR billing:counter
Redis thực hiện INCR
Redis chưa kịp trả response
Connection bị ngắt
Spring nhận timeout
```

Client không biết counter đã tăng hay chưa. Nếu tự retry `INCR`, có thể tăng hai lần. Nếu bỏ qua, cũng có thể bỏ sót.

Các thao tác và cách nhìn retry:

| Thao tác | Retry không điều kiện? | Vấn đề |
| --- | --- | --- |
| `GET key` | Thường có thể, theo consistency policy | Dữ liệu có thể đổi giữa hai lần |
| `SET key fixedValue` | Thường idempotent nếu không có điều kiện bổ sung | TTL và side effects cần xét |
| `INCR key` | Không | Có thể tăng hai lần |
| `LPUSH list value` | Không | Có thể thêm item trùng |
| `SET key token NX PX ...` | Phải xem token/owner | Lock có thể đã được tạo |
| Lua reserve/payment | Cần idempotency | Script có thể đã chạy trước timeout |
| `XADD` với ID tự động | Không mặc định | Retry có thể tạo entry mới |

Failover làm tăng khả năng gặp ambiguous outcomes, nhưng đây là vấn đề phân tán tồn tại ngay cả khi không failover.

### Giải pháp thường dùng

1. Cấp **requestId/idempotency key ổn định** ở tầng nghiệp vụ.
2. Ghi nhận kết quả request trong cùng đơn vị nguyên tử nơi phù hợp.
3. Retry bằng **cùng requestId**, không tự sinh ID mới.
4. Khi không rõ kết quả, tra cứu state có thẩm quyền trước khi quyết định.
5. Không coi một timeout là bằng chứng Redis chưa thực thi lệnh.

Nếu Redis có thể mất write sau failover, idempotency state chỉ lưu trên cùng Redis cũng có rủi ro mất; dữ liệu nghiệp vụ quan trọng cần một nguồn chuẩn đủ mạnh.

## 27. Redis là cache hay nguồn dữ liệu chuẩn?

Hai tình huống dẫn tới quyết định durability khác nhau.

### Redis chỉ là cache

```text
PostgreSQL (source of truth)
          |
          v
Redis Cache
          |
          v
Spring API
```

Nếu Redis crash và mất cache:

- API có thể cache miss.
- Application đọc lại PostgreSQL.
- Cache được tái tạo nếu nguồn chuẩn còn.
- Persistence Redis có thể giúp khởi động nhanh hơn, nhưng không phải điều kiện cần để không mất nghiệp vụ.

Trong trường hợp này, **availability và khả năng fallback** có thể đáng ưu tiên hơn việc fsync mỗi Redis write.

### Redis giữ trạng thái nghiệp vụ duy nhất

```text
Spring -> Redis
          |
          +-- chỉ tại đây có reservation / quota / trạng thái công việc
```

Nếu write mất do failover, không có database khác để tái tạo. Cần mục tiêu RPO/RTO nghiêm túc, replication/persistence/backup và có thể chuyển một số dữ liệu sang database có bảo đảm mạnh hơn.

**Không nên chọn cơ chế Redis dựa duy nhất trên tốc độ**, đặc biệt với số dư, thanh toán, đơn hàng hoặc dữ liệu bắt buộc kiểm toán.

## 28. Transactional outbox khi Redis là bản sao hoặc hệ thống xử lý phụ trợ

Một giải pháp thường dùng khi database là source of truth:

```text
Spring transaction
   |
   +-- UPDATE business record
   |
   +-- INSERT outbox_event
   |
   v
COMMIT database
   |
   v
Outbox worker đọc sự kiện
   |
   v
Update Redis cache/stream/derived view
   |
   v
Mark processed hoặc retry
```

Nếu Redis failover ngay khi worker ghi cache:

- Database record vẫn là dữ liệu chuẩn.
- Outbox event vẫn có thể được retry.
- Worker phải idempotent và kiểm tra version/ordering khi cần.
- Redis có thể mất cache entry mà không làm mất giao dịch nghiệp vụ.

Outbox không biến Redis và database thành một transaction phân tán duy nhất, nhưng giải quyết cửa sổ “database commit thành công mà ứng dụng crash trước khi ghi Redis” bằng một cơ chế có thể phục hồi.

### Event tới sai thứ tự

Nếu hai versions của một entity được publish:

```text
version 7 -> price=110
version 8 -> price=120
```

một worker xử lý chậm version 7 sau version 8 có thể ghi cache về giá cũ. Có thể invalidate cache thay vì put snapshot cũ, hoặc kiểm tra version atomically khi ghi Redis theo contract nghiệp vụ.

Persistence và replication không giải quyết vấn đề ordering đó.

## 29. Redis replication không thay thế backup

Replication giúp một node khác có bản sao dữ liệu hiện tại. Nhưng nếu có lệnh sai:

```redis
FLUSHDB
```

hoặc một ứng dụng ghi dữ liệu corrupt, thay đổi cũng có thể lan tới replicas.

**Backup** phải là bản sao có thể phục hồi độc lập với cluster đang chạy và có chính sách retention.

Một chiến lược backup có thể gồm:

- RDB snapshots ở các thời điểm xác định.
- Copy tới object storage hoặc hệ thống backup **khác failure domain**.
- Kiểm tra integrity/checksum.
- Mã hóa và phân quyền bản backup.
- Lưu nhiều phiên bản để phục hồi trước lỗi logic.
- Diễn tập restore định kỳ.
- Chính sách retention phù hợp yêu cầu compliance.

### Không copy AOF đang hoạt động một cách tùy tiện

Với Redis 7+ có multi-part AOF và manifest, copy một file bất kỳ trong khi Redis đang ghi có thể không tạo được bản backup nhất quán. Dùng cơ chế snapshot/backup được Redis và platform hỗ trợ, hoặc tạo backup trong trạng thái/quy trình nhất quán theo version.

Nếu chỉ có RDB backup, phải chấp nhận RPO theo thời điểm snapshot. Nếu muốn khôi phục tới thời điểm gần hơn, cần kiến trúc hỗ trợ và quy trình riêng; Redis OSS không tự cung cấp point-in-time restore đầy đủ như một số database chuyên dụng.

## 30. Backup và restore trong hệ thống Cluster

Redis Cluster phân phối dữ liệu trên nhiều primaries. Vì vậy sao lưu một node **không đồng nghĩa sao lưu toàn bộ cluster dataset**.

Ví dụ:

```text
Primary A: keys slots A -> backup A
Primary B: keys slots B -> backup B
Primary C: keys slots C -> backup C
```

Kế hoạch backup phải bao phủ toàn bộ shards và có metadata/topology đủ để khôi phục. Nếu chụp nhiều shards ở những thời điểm khác nhau, dữ liệu xuyên shards có thể không tương ứng một thời điểm toàn cục nhất quán.

Những điều cần xác định:

1. Snapshot nào thuộc shard/primary nào?
2. Cluster slots đã được reshard giữa các lần backup chưa?
3. Có backup đầy đủ mọi shard tại thời điểm mục tiêu không?
4. Khôi phục lên cluster mới hay node cũ?
5. Có đang giữ cluster metadata/configuration tương thích với bản restore?
6. Làm sao tách môi trường restore khỏi production để tránh ghi đè nhầm?
7. Làm sao xác minh dữ liệu và route đúng slots sau restore?

**Không đơn giản copy `nodes.conf` hoặc AOF từ một cluster đang chạy sang cluster khác** rồi mặc định topology sẽ tự đồng bộ đúng. Redis Cluster lưu metadata node identity và slot ownership; restore phải theo quy trình công cụ/platform phù hợp.

## 31. Các tình huống cần kế hoạch khôi phục riêng

| Sự cố | Có thể dùng gì? | Điều phải kiểm tra |
| --- | --- | --- |
| Redis process crash, disk còn | AOF/RDB local | File hợp lệ, fsync và recovery |
| Host hỏng, replica còn | Failover | Replica có đủ dữ liệu không, khả năng ghi sau promote |
| Replica lag cao | Replication + monitoring | RPO, không giả định read-your-writes |
| Toàn bộ nodes mất RAM | Persistence/backup | Storage còn, restore order, dữ liệu tại thời điểm nào |
| Disk primary hỏng | Replica + backup | Failover và backup còn độc lập |
| Xóa nhầm/FLUSHDB | Backup phiên bản cũ | Replication đã lan lệnh xóa |
| Resharding lỗi | Cluster metadata/backup | Slot mapping và dữ liệu từng shard |
| Network partition | Election/cluster policies | Majority, split brain, write loss |
| Redis provider outage | DR cross-zone/region | Network, credentials, restore time |
| Application retry sau timeout | Idempotency ledger | Tác dụng phụ đã thực hiện hay chưa |

Không có một thao tác “bật replication” nào thay thế được toàn bộ bảng này.

## 32. Cấu hình Redis server trên primary và replicas

Ví dụ một Redis node được quản lý theo hướng có cả AOF và RDB:

```conf
port 6379
dir /var/lib/redis

appendonly yes
appendfsync everysec
aof-use-rdb-preamble yes

save 900 1
save 300 10
save 60 10000
stop-writes-on-bgsave-error yes

min-replicas-to-write 1
min-replicas-max-lag 10
```

**Không copy y nguyên lên mọi node mà không xét role và mục tiêu.** Hai dòng `min-replicas-*` đặc biệt áp dụng chính sách chấp nhận ghi của primary; trong topology có ít/không có replica phù hợp, cấu hình này có thể khiến write bị từ chối. Hãy chọn theo topology thật.

Persistence/backup config trên mỗi node cần thống nhất với vai trò, storage layout và Redis version.

### Replica configuration

Replica có thể dùng:

```conf
replicaof 10.10.0.11 6379
```

Khi dùng Redis Sentinel hoặc Cluster, cấu hình topology thực tế còn do cơ chế failover thay đổi. Không quản lý replica theo cách một script cấu hình cứ ép nó theo master cũ sau mỗi restart, bỏ qua master mới được chọn.

Nếu dùng ACL, cần cấu hình xác thực replication và client connection phù hợp.

## 33. Lưu trữ disk và áp lực background save

Persistence không miễn phí. Khi Redis tạo RDB snapshot hoặc AOF rewrite, process có thể fork child/background task và dùng cơ chế copy-on-write.

Các yếu tố vận hành:

- RAM đủ cho copy-on-write khi dataset thay đổi mạnh trong quá trình snapshot.
- Disk đủ chỗ cho snapshot mới, AOF rewrite và file cũ chưa dọn.
- Filesystem có latency và durability phù hợp.
- Không để cùng một volume quá nhỏ khiến AOF rewrite hoặc RDB save fail.
- Không đặt persistence file trong ephemeral container filesystem khi yêu cầu sống sót qua pod replacement.
- Theo dõi độ trễ command khi I/O hệ thống tăng.
- Kiểm tra permission và owner của thư mục lưu file.
- Kiểm tra cách process shutdown có thể chờ persistence hoặc xử lý tín hiệu.

Trong Kubernetes, persistence yêu cầu PersistentVolume hoặc một storage mechanism phù hợp. Nhưng **có PVC không tự chứng minh dữ liệu đã fsync thành công, replicated sang zone khác hoặc được backup**.

### maxmemory và eviction

Nếu Redis dùng làm cache, `maxmemory-policy` có thể chủ động evict keys. Eviction là behavior dữ liệu, không phải sự cố persistence; một key có thể biến mất đúng theo policy dù AOF/RDB hoạt động.

Nếu Redis giữ dữ liệu không được phép mất do eviction, cần thiết kế maxmemory policy thích hợp, thường phải tránh các chính sách tự động loại key quan trọng.

## 34. Kiểm tra Redis persistence bằng lệnh vận hành

Trên từng Redis data node:

```bash
redis-cli -h redis-node.internal -p 6379 INFO persistence
redis-cli -h redis-node.internal -p 6379 INFO replication
redis-cli -h redis-node.internal -p 6379 ROLE
redis-cli -h redis-node.internal -p 6379 LASTSAVE
```

Kiểm tra cấu hình:

```bash
redis-cli -h redis-node.internal -p 6379 CONFIG GET appendonly
redis-cli -h redis-node.internal -p 6379 CONFIG GET appendfsync
redis-cli -h redis-node.internal -p 6379 CONFIG GET save
redis-cli -h redis-node.internal -p 6379 CONFIG GET min-replicas-to-write
redis-cli -h redis-node.internal -p 6379 CONFIG GET min-replicas-max-lag
```

Trong thực tế Redis ACL hoặc managed Redis có thể hạn chế một số lệnh `CONFIG`; dùng công cụ quản trị nhà cung cấp khi cần.

### Đọc INFO persistence

Các tín hiệu thường quan trọng:

| Trường/nhóm | Ý nghĩa cần theo dõi |
| --- | --- |
| `rdb_last_bgsave_status` | Snapshot trước đó có thành công không |
| `rdb_last_save_time` | Thời điểm RDB save gần nhất |
| `rdb_bgsave_in_progress` | Có background save đang chạy không |
| `aof_enabled` | AOF có bật không |
| `aof_last_write_status` | AOF write gần đây có lỗi không |
| `aof_last_bgrewrite_status` | Rewrite AOF gần đây có thành công không |
| `aof_rewrite_in_progress` | AOF rewrite đang chạy không |
| AOF size fields | Theo dõi tăng trưởng file và rewrite |

Tên/availability một số trường có thể khác theo Redis version. Không suy luận chỉ vì `aof_enabled=1` thì disk không có lỗi hoặc fsync đã kịp với tất cả writes.

### Đọc INFO replication

Theo dõi:

- `role`: master hay slave/replica theo trường Redis version.
- `connected_slaves` hoặc số replica đã kết nối.
- Replication offset master và replica.
- `master_link_status` trên replica.
- Những trạng thái synchronization/full resync.

Số replica đang connected chưa đồng nghĩa tất cả replicas có đủ dữ liệu và AOF đã fsync.

## 35. Kiểm tra failover với Sentinel

Trên Sentinel:

```bash
redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL get-master-addr-by-name mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL master mymaster

redis-cli -h sentinel-a.internal -p 26379 \
  SENTINEL replicas mymaster
```

Trên node dữ liệu được báo là master:

```bash
redis-cli -h redis-primary.internal -p 6379 INFO replication
```

Các lệnh giúp xác định:

- Sentinel đang tin node nào là master.
- Replicas nào còn được theo dõi.
- Role thực tế của data node.
- Có lệch topology hoặc replication lag không.

**Lưu ý:** khi failover đang diễn ra, các Sentinel có thể tạm thời quan sát trạng thái khác nhau. Cần xem logs/events và các node liên quan, không kết luận từ một lần hỏi duy nhất.

## 36. Kiểm tra Redis Cluster khi có failover

Trên Redis Cluster node:

```bash
redis-cli -c -h redis-node.internal -p 6379 CLUSTER INFO
redis-cli -c -h redis-node.internal -p 6379 CLUSTER NODES
redis-cli -c -h redis-node.internal -p 6379 CLUSTER SHARDS
```

Đọc các thông tin:

- `cluster_state`.
- Các hash slots đang được phục vụ.
- Danh sách primaries/replicas.
- Node nào sở hữu slot sau failover.
- Có replica đủ điều kiện cho từng shard không.
- Client có thể cập nhật topology qua seeds/redirects không.

Khi Redis Cluster reshard hoặc failover, client có thể gặp `MOVED`, `ASK`, `READONLY` hoặc timeout tùy thời điểm và trạng thái topology. Đó không mặc định là lỗi persistence; cần phân biệt **slot routing**, **role change** và **local disk recovery**.

## 37. Bảng kiểm thử theo lớp lỗi

Một kế hoạch thử nghiệm tốt cần tách **mất process**, **mất host**, **mất replication link** và **failover**.

| Bài test | Tác động | Điều cần đo |
| --- | --- | --- |
| Restart process an toàn | Redis dừng/khởi động có kiểm soát | Load AOF/RDB, latency, key còn |
| Crash process đột ngột | Process mất mà không shutdown sạch | Writes nào còn, fsync gap |
| Mất primary, replica còn | Failover | RTO, write loss window |
| Mất network primary–replica | Replication lag/disconnect | min-replicas policy, stale data |
| Replica offline rồi trở lại | PSYNC/full sync | Bandwidth, sync time |
| AOF rewrite dưới tải | Disk/CPU/COW | Latency, free space, errors |
| Disk đầy | AOF/RDB có thể lỗi | Application error handling, alerts |
| Mất cả primary và replicas | Không còn RAM live | Backup/restore RTO |
| Xóa key sai | Replication chuyển xóa | Backup historical recovery |
| Client write timeout | Ambiguous result | Idempotency, duplicate effects |

Tất cả bài test gây lỗi đều phải thực hiện trong môi trường **cô lập**, không đụng dữ liệu production.

## 38. Bài thực hành A: so sánh RDB và AOF sau crash

Dựng hai Redis instances test:

**Instance A:** RDB only.

```conf
appendonly no
save 60 10
```

**Instance B:** AOF everysec.

```conf
appendonly yes
appendfsync everysec
```

Thực hiện:

1. Ghi một chuỗi giá trị có ID thứ tự và timestamp.
2. Quan sát lần RDB save cuối, tình trạng AOF.
3. Dùng môi trường test để mô phỏng process crash ở các thời điểm.
4. Restart và thống kê ID nào còn lại.
5. So sánh độ trễ write và khoảng dữ liệu có thể mất.
6. Lặp lại với tải I/O khác nhau và ghi rõ số lần thử.

**Không dùng kết quả một lần thử để khẳng định giới hạn mất dữ liệu cứng.** Crash simulation của một process không tương đương mất điện toàn bộ host/storage, vì OS filesystem cache có thể còn.

## 39. Bài thực hành B: failover khi replication lag

Dùng Sentinel test hoặc Redis Cluster test có ít nhất một primary và replica đủ điều kiện.

Timeline mong muốn:

```text
1. Ghi key và theo dõi sequence number.
2. Tạo replication lag có kiểm soát trong môi trường test.
3. Ghi một số writes mới.
4. Gây sự cố primary.
5. Quan sát replica được promote.
6. So sánh sequence numbers trước/sau.
```

Cần ghi nhận:

- Primary có ACK đến sequence nào.
- Replica có dữ liệu đến sequence nào.
- Redis node nào được promote.
- RPO thực tế quan sát trong lần thử.
- Client mất bao lâu để gửi write thành công trở lại.
- Retry có tạo duplicates không.

Nếu chạy thử với topology được chọn không thể failover vì thiếu quorum/majority, đó cũng là kết quả cần phân biệt với sự cố persistence.

## 40. Bài thực hành C: WAIT và WAITAOF

Trong Redis test có AOF và replicas phù hợp, trên **cùng redis-cli session**:

```redis
SET demo:durability:1 "v1"
WAIT 1 2000
```

Ghi lại số replicas được báo xác nhận.

Nếu Redis hỗ trợ `WAITAOF` và đã bật AOF phù hợp, thử:

```redis
SET demo:durability:2 "v2"
WAITAOF 1 1 2000
```

Ghi nhận kết quả acknowledgement theo lệnh.

Câu hỏi:

- Lệnh `WAIT` xác nhận điều gì và **không xác nhận** điều gì?
- Kết quả `WAITAOF` cần bao nhiêu local/replica acknowledgments?
- Chuyện gì xảy ra nếu timeout?
- Liệu lệnh trước đó đã thực hiện nhưng client chưa nhận đủ ACK không?
- Nếu failover promote một replica khác replica vừa ACK, kết quả ra sao?
- Nếu storage gặp sự cố độc lập sau ACK, có thể suy ra điều gì?

Không kết luận “đã có transaction đồng bộ tuyệt đối” chỉ từ việc các lệnh chờ trả đủ số.

## 41. Bài thực hành D: restore backup

Trong môi trường test:

1. Lưu dữ liệu mẫu đủ xác định version, ID và checksum.
2. Tạo snapshot/backup nhất quán theo công cụ Redis/version.
3. Copy backup ra nơi độc lập với container Redis đang chạy.
4. Xóa hoàn toàn môi trường test.
5. Tạo Redis instance/cluster khôi phục mới.
6. Restore theo runbook phù hợp.
7. Kiểm tra dữ liệu, TTL, key types và application behavior.
8. Đo thời gian hoàn thành restore.
9. Ghi nhận những writes không nằm trong backup theo RPO thực tế.

Nếu dùng Redis Cluster, phải xác định backup từng shard, mapping slots và quy trình khôi phục topology. Chỉ test một key trên một node chưa chứng minh cả cluster đã được backup đầy đủ.

## 42. Những ngộ nhận thường gặp

### “Có replication thì không cần AOF/RDB”

Sai. Replicas có thể cùng mất RAM/process hoặc nhận lệnh xóa sai; persistence và backup phục vụ các loại lỗi khác nhau.

### “Có AOF trên primary thì failover chắc chắn không mất write”

Sai. Replica được promote có thể chưa nhận write mà primary đã ACK/fsync.

### “Dùng appendfsync everysec là chắc chắn mất tối đa đúng một giây”

Không phải bảo đảm cứng trong mọi trường hợp, đặc biệt khi storage stalls và các kịch bản lỗi khác. Cũng phải xét lag khi failover.

### “appendfsync always chắc chắn không bao giờ mất dữ liệu”

Không thể khẳng định tuyệt đối trước mọi lỗi storage/hardware/topology; cũng không làm replication đồng bộ.

### “WAIT 1 có nghĩa write đã an toàn tuyệt đối”

Không. WAIT chờ replica ACK replication offsets, không đồng nghĩa fsync hay đảm bảo được chọn làm master mới.

### “WAITAOF là consensus commit nên không cần backup”

Không. Lệnh tăng bảo đảm ở phạm vi fsync acknowledgments được hỗ trợ, không thay thế hệ thống backup/DR.

### “Sentinel lưu bản sao dữ liệu của master”

Không. Sentinel giám sát và điều phối failover, không phải data replica.

### “Redis Cluster bảo vệ mọi shard dù thiếu replicas”

Không. Một shard mất primary và mọi replicas có thể mất khả năng phục vụ/khôi phục.

### “Một backup RDB trên một node là đủ cho Redis Cluster”

Không. Dữ liệu được chia trên nhiều shards, phải backup toàn bộ relevant primaries và topology.

### “Redis persistence được điều khiển bằng spring.data.redis.*”

Không. Spring properties chủ yếu cấu hình client; AOF/RDB là server settings trên Redis nodes.

### “Timeout nghĩa là Redis không thực hiện write”

Sai. Response có thể bị mất sau khi Redis đã ghi. Retry non-idempotent cần guard.

### “Replica reads luôn thấy dữ liệu mới nhất”

Sai. Replication bất đồng bộ dẫn tới stale reads.

### “Replication tự cứu khi xóa nhầm toàn bộ key”

Không. Lệnh xóa có thể lan tới mọi replicas; cần backup lịch sử.

### “Backup tồn tại nghĩa là restore chắc chắn thành công”

Không. Cần test restore, xác minh đầy đủ shards, integrity, key types và thời gian phục hồi.

## 43. Câu hỏi thường gặp

**Redis chỉ làm cache thì nên bật AOF không?**

Không có một đáp án chung. Nếu có nguồn dữ liệu chuẩn và có thể tái tạo cache, AOF có thể không cần thiết; quyết định dựa trên warm-up cost, tải database, RTO và yêu cầu vận hành. Replica/failover có thể vẫn hữu ích cho availability.

**Có thể bật RDB và AOF cùng lúc không?**

Có. Mỗi cơ chế giải quyết một phần mục tiêu; AOF thường là nguồn nạp dữ liệu được ưu tiên khi bật, còn RDB có thể dùng để snapshot/backup.

**Redis có ghi AOF trước khi trả OK không?**

Điều đó phụ thuộc chính sách AOF và cơ chế xử lý. Không mặc định `OK` đồng nghĩa `fsync` đã hoàn tất trong mọi chế độ, nhất là `everysec` và `no`.

**Replication bất đồng bộ có nghĩa replica luôn chậm không?**

Không phải lúc nào cũng có độ trễ đáng kể, nhưng có thể xuất hiện lag và không có bảo đảm mọi read sau write từ replica luôn là trạng thái mới nhất.

**Failover có thể chọn replica chưa nhận write vừa ACK không?**

Có thể, tùy replication lag, lỗi và election. Đây là một nguồn write loss trong Redis HA.

**Có cách nào giảm write loss không?**

AOF với fsync phù hợp, nhiều replicas, chính sách `min-replicas-*`, `WAIT` hoặc `WAITAOF` ở phiên bản hỗ trợ, persistence/backup và điều kiện vận hành đúng có thể giảm rủi ro; không nên xem chúng bảo đảm zero loss end-to-end.

**Sentinel và Redis Cluster có failover giống nhau không?**

Cùng có ý tưởng promote replica, nhưng Sentinel điều phối HA cho nhóm master–replicas không sharding theo slots; Redis Cluster có giao thức topology/election cho từng shard.

**Nếu cả Redis data nodes mất, có thể phục hồi từ Sentinel không?**

Không. Sentinel không lưu dữ liệu nghiệp vụ. Cần persistence files hoặc backup hợp lệ từ Redis data nodes.

**WAIT nên gửi ở connection khác sau RedisTemplate.set không?**

Không nên mặc định như vậy. WAIT chờ replication offsets của writes trước đó trong client connection, cần bảo đảm cùng connection và dùng API driver phù hợp.

**WAITAOF có thay thế transaction database không?**

Không. Nó phục vụ mức fsync acknowledgment của Redis, không tạo business transaction hay điều phối commit với hệ thống ngoài.

**Khi Redis timeout lúc INCR, có nên retry ngay không?**

Không retry mù quáng; cần xác minh outcome hoặc dùng idempotency key, vì lệnh có thể đã thực thi.

**Muốn backup Redis Cluster phải làm gì?**

Có chiến lược bao phủ mọi shard, lưu snapshot nhất quán theo quy trình Redis/version, bảo vệ topology metadata và test restore trong môi trường cô lập.

**`INFO persistence` báo AOF enabled là đã đủ chưa?**

Chưa. Cần xem status, errors, fsync/rewrite, disk, replica state, backup và RPO thực tế.

## 44. Tổng kết: phối hợp ba cơ chế theo đúng phạm vi

Một thiết kế Redis có độ bền và khả năng phục hồi cần biết:

- **Persistence (RDB/AOF)** giúp node khôi phục trạng thái từ storage, nhưng có cửa sổ mất dữ liệu và phụ thuộc disk/fsync.
- **Replication** đưa thay đổi sang các nodes khác, thường bất đồng bộ nên có replication lag và dữ liệu khác nhau tạm thời.
- **Failover** promote replica phù hợp khi primary mất; nó khôi phục availability nhưng không tự đảm bảo replica chứa tất cả writes đã ACK.
- **Sentinel và Redis Cluster** quản lý failover theo các topology khác nhau; cấu hình Spring Data Redis xác định client discovery, không thay thế Redis server persistence settings.
- **WAIT/WAITAOF và min-replicas-to-write** có thể giảm một số rủi ro, nhưng phải đọc đúng mức ACK và không coi chúng là consensus database.
- **Backup độc lập và thử restore** là bắt buộc nếu phải phục hồi xóa nhầm, lỗi nhiều nodes hoặc mất toàn bộ failure domain.
- **Client retry và idempotency** bảo vệ trước kết quả write mơ hồ do timeout/reconnect.
- **RPO/RTO và vai trò source of truth** phải quyết định cấu hình, không chỉ mong muốn “Redis chạy nhanh”.

Khi kết hợp các cơ chế theo đúng mục tiêu, ứng dụng Spring Boot có thể tận dụng Redis HA mà vẫn hiểu rõ những loại lỗi còn xảy ra, mất dữ liệu nào còn khả thi và kế hoạch phục hồi nào thực sự đã được chuẩn bị.

## Tài liệu tham khảo chính thức

- [Redis – Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis – Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis – High Availability with Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)
- [Redis – Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis – WAIT](https://redis.io/docs/latest/commands/wait/)
- [Redis – WAITAOF](https://redis.io/docs/latest/commands/waitaof/)
- [Redis – INFO](https://redis.io/docs/latest/commands/info/)
- [Spring Data Redis – Connection Modes](https://docs.spring.io/spring-data/redis/reference/redis/connection-modes.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Boot – Redis Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis)
