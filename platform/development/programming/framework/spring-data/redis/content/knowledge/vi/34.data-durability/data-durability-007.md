# Thiết kế sao lưu, khôi phục và kiểm chứng bản sao trong Spring Data Redis

Redis nổi tiếng vì đọc/ghi dữ liệu trong bộ nhớ, nhưng một hệ thống thực tế vẫn có thể cần **khả năng phục hồi dữ liệu** sau khi máy chủ hỏng, thao tác nhầm, lỗi phần mềm, mất cả vùng triển khai hoặc sự cố vận hành kéo dài. Nếu Redis chỉ lưu cache có thể tái tạo, chấp nhận xóa toàn bộ rồi nạp lại có thể là lựa chọn hợp lý. Nếu Redis giữ session, hàng đợi, thông tin nghiệp vụ hoặc trạng thái chưa được lưu ở nơi khác, mất dữ liệu sẽ có hậu quả khác hẳn.

Trong ứng dụng Spring Data Redis, việc sử dụng `RedisTemplate` hoặc `ReactiveRedisTemplate` không tự bảo đảm backup. **Độ bền dữ liệu là một thiết kế xuyên suốt Redis persistence, lưu trữ bên ngoài, kế hoạch restore, quyền truy cập, kiểm chứng tính toàn vẹn và khả năng vận hành.** Một file `dump.rdb` tồn tại trên đĩa chưa đủ để khẳng định hệ thống có thể khôi phục.

Bài học trình bày cách lựa chọn RDB/AOF, xây lịch sao lưu, kiểm tra bản sao, diễn tập khôi phục Standalone/Sentinel/Cluster, xác định RPO/RTO và kiểm chứng dữ liệu từ Spring Data Redis. Những lệnh can thiệp file, dừng Redis hoặc thay cấu hình chỉ dành cho **môi trường test/restore cách ly hoặc runbook production đã được phê duyệt**.

## 1. Phân biệt persistence, replication, backup và disaster recovery

Đây là bốn khái niệm thường bị gộp làm một:

| Cơ chế | Mục tiêu | Không thay thế được |
|---|---|---|
| **Persistence** | Lưu dữ liệu của một Redis instance xuống disk, thường bằng RDB/AOF | Backup offsite, khôi phục trạng thái trước thao tác xóa nhầm |
| **Replication** | Sao chép trạng thái từ master sang replica để tăng availability | Lịch sử nhiều phiên bản, backup độc lập |
| **Backup** | Giữ các bản sao tại những mốc thời gian xác định, ngoài đường vận hành thường ngày | Tự động failover tức thời |
| **Disaster recovery (DR)** | Quy trình khôi phục dịch vụ sau sự cố lớn, gồm hạ tầng, cấu hình và dữ liệu | Tự sinh ra file backup hợp lệ nếu chưa thiết kế trước |

Ví dụ:

```text
                  Spring application
                          |
                          v
                       Redis M
                       /     \
             replication     persistence
                    /           \
                Redis R        RDB/AOF trên disk
                                  |
                            backup job
                                  |
                            encrypted archive
                                  |
                         offsite/object storage
                                  |
                          restore drill / DR
```

Nếu ứng dụng gửi nhầm `FLUSHALL`, thao tác xóa có thể được **replicate** sang replica, và trạng thái sau khi xóa có thể được ghi vào AOF/snapshot mới. Một replica cùng lỗi logic không phải bản sao độc lập để quay lại ngày hôm trước. Cần **backup có version và retention**.

### 1.1. Ví dụ phân loại dữ liệu trước khi lập kế hoạch

| Dữ liệu Redis | Có thể tái tạo? | Cách tiếp cận |
|---|---|---|
| Cache kết quả truy vấn từ PostgreSQL | Thường có | Có thể chấp nhận không backup, nhưng phải tính chi phí warm-up |
| Session đăng nhập | Có thể phục hồi bằng yêu cầu đăng nhập lại nhưng gây ảnh hưởng người dùng | Xác định RPO và downtime chấp nhận |
| Redis Streams chứa job chưa xử lý | Không nhất thiết | Persistence, backup, retention và recovery consumer group |
| Cache số tồn kho | Có nguồn DB authoritative | Bảo đảm khôi phục từ DB và tránh dùng cache cũ làm sự thật |
| Counter hoặc trạng thái nghiệp vụ chỉ nằm trong Redis | Có thể không | Cần thiết kế độ bền nghiêm ngặt hoặc chuyển nguồn sự thật sang storage phù hợp |
| Rate limiter ngắn hạn | Thường không cần lịch sử | Có thể tái tạo; cân nhắc tác dụng khi reset counter |

**Không mặc định toàn bộ Redis phải có cùng chính sách backup.** Bản chất dữ liệu quyết định tần suất sao lưu và cách kiểm chứng sau restore.

## 2. RPO và RTO: bắt đầu từ yêu cầu nghiệp vụ

Hai chỉ tiêu quan trọng:

- **RPO (Recovery Point Objective):** có thể chấp nhận mất tối đa bao nhiêu dữ liệu theo thời gian.
- **RTO (Recovery Time Objective):** mất tối đa bao lâu để khôi phục được chức năng cần thiết sau sự cố.

```text
                         Sự cố
                            |
       Bản backup cuối      |                Dịch vụ phục hồi
               |            |                         |
---------------+------------+-------------------------+----> thời gian
               <--- RPO --->|<---------- RTO -------->|
```

Ví dụ hệ thống dùng Redis lưu một số sự kiện trung gian:

| Mức dịch vụ (ví dụ) | RPO | RTO | Thiết kế có thể cân nhắc |
|---|---|---|---|
| Cache tái tạo được | Mất toàn bộ cache | 15–60 phút để warm up | Không cần backup cache, có kế hoạch rebuild |
| Session có thể yêu cầu đăng nhập lại | 1 giờ | 30 phút | RDB định kỳ, restore tự động hóa |
| Job stream quan trọng | Vài giây/phút tùy SLA | 15 phút | AOF + RDB + sao lưu ngoài máy, test replay/idempotency |
| Dữ liệu tài chính không chấp nhận mất | Gần 0 theo nghiệp vụ | Khắt khe | Không nên chỉ dựa Redis asynchronous replication; chọn hệ dữ liệu authoritative với cơ chế commit phù hợp |

Đây là **ví dụ thiết kế**, không phải cam kết RPO/RTO thực tế của Redis. RPO chỉ có ý nghĩa khi đo được tuổi của bản backup **đã hoàn tất, đã chuyển ra nơi an toàn và đã kiểm tra**. Một job chạy mỗi 5 phút nhưng 8 giờ liên tiếp upload thất bại không có RPO 5 phút.

### 2.1. Công thức hoạch định lịch sao lưu

Giả sử:

```text
Tần suất snapshot: 15 phút
Thời gian tạo snapshot: 2 phút
Thời gian copy/upload: 3 phút
Thời gian nhận biết job lỗi: 5 phút
```

Không thể đơn giản tuyên bố RPO bằng 15 phút. Cần tính tuổi **recovery point cuối cùng đã được bảo vệ** tại thời điểm sự cố, khoảng trễ backup pipeline và khả năng một lần chạy bị bỏ lỡ. RTO cũng gồm phát hiện sự cố, lấy file, tạo máy, load dữ liệu, xác thực và chuyển traffic.

Hãy kiểm tra các chỉ số trên bằng **restore drill thực tế**, không chỉ dựa vào thời gian dự kiến trên giấy.

## 3. Redis persistence: RDB, AOF, kết hợp hoặc tắt

Redis có các lựa chọn chính:

### 3.1. RDB: snapshot trạng thái tại một thời điểm

Redis ghi một bản chụp nhị phân, thường là `dump.rdb`. Snapshot có thể được cấu hình tạo định kỳ hoặc yêu cầu bằng `BGSAVE`.

Ưu điểm:

- Một file tương đối gọn, dễ lưu nhiều phiên bản theo mốc thời gian.
- Thường nhanh khi khởi động lại với dữ liệu lớn so với replay một AOF dài.
- Phù hợp cho backup offsite và restore staging.

Giới hạn:

- Các thay đổi sau snapshot gần nhất có thể mất khi process/máy chủ hỏng.
- `BGSAVE` cần `fork`/copy-on-write và disk I/O; có thể tăng áp lực RAM, CPU và storage.
- Nếu snapshot mới thất bại, file RDB cũ có thể vẫn tồn tại; **file tồn tại không đồng nghĩa lần backup mới thành công**.

### 3.2. AOF: ghi log những thao tác thay đổi dữ liệu

AOF (Append Only File) ghi lệnh thay đổi state để Redis có thể tái tạo dataset khi khởi động. Chính sách `appendfsync`:

| Giá trị | Nguyên tắc | Đánh đổi |
|---|---|---|
| `always` | Đồng bộ xuống storage thường xuyên cho các batch ghi | An toàn hơn trước crash nhưng có thể tăng latency và giảm throughput |
| `everysec` | Fsync gần theo chu kỳ một giây | Cân bằng hiệu năng và rủi ro mất một khoảng ghi rất gần sự cố |
| `no` | Để OS quyết định việc flush | Có thể mất nhiều dữ liệu hơn khi host hỏng |

Không được hiểu `appendfsync everysec` thành “bảo đảm đúng 1 giây trong mọi loại lỗi”. OS, filesystem, storage controller, mất cả volume/zone và replication đều có mô hình lỗi khác nhau.

### 3.3. RDB + AOF

Redis có thể bật cả hai:

```conf
appendonly yes
appendfsync everysec
save 900 1
save 300 10
save 60 10000
```

Những dòng `save` chỉ là **ví dụ chính sách snapshot**, không bắt buộc cho mọi workload. Khi bật cả RDB và AOF, Redis thông thường **ưu tiên AOF để nạp lại dataset lúc khởi động** vì AOF có thể chứa trạng thái mới hơn RDB.

Điều này rất quan trọng trong runbook restore: **chỉ copy một bản `dump.rdb` vào data directory của instance vẫn bật AOF hiện hữu không bảo đảm Redis sẽ tải bản RDB bạn muốn**. Phải xác định rõ artifact nào sẽ được load và chuẩn bị cấu hình tương thích.

### 3.4. Không persistence

Nếu Redis chỉ giữ cache hoàn toàn tái tạo được, có thể chủ động tắt persistence:

```conf
save ""
appendonly no
```

Lựa chọn này có thể phù hợp khi hệ thống có khả năng warm-up hoặc degrade gracefully; nó cũng có nghĩa dữ liệu Redis có thể mất sau restart. Không áp dụng cho Redis Stream/queue quan trọng chỉ vì Redis thường được gọi là cache.

### 3.5. Bảng lựa chọn nhanh

| Tiêu chí | RDB | AOF | RDB + AOF |
|---|---|---|---|
Recovery point | Mốc snapshot | Theo log/fsync | Cả snapshot và log |
Kích thước artifact | Thường gọn | Có thể lớn hơn | Tốn storage cho cả hai |
Copy offsite | Tương đối dễ với RDB hoàn chỉnh | Phải bảo đảm bộ AOF nhất quán | Nên quản lý cả hai loại |
Thời gian load | Thường nhanh hơn | Có thể dài do replay | AOF thường được ưu tiên khi restart |
Rủi ro mất thay đổi gần nhất | Phụ thuộc lịch snapshot | Phụ thuộc fsync/storage | Không bằng 0 |
Khôi phục về mốc quá khứ | Dễ nếu lưu nhiều RDB lịch sử | Cần bộ AOF ở mốc phù hợp hoặc quy trình log | Có thêm lựa chọn |

## 4. Những gì cần lưu ngoài dữ liệu Redis

Một backup **chỉ chứa dataset** thường chưa đủ để tái dựng dịch vụ.

| Thành phần | Ví dụ | Có tự nằm trong RDB/AOF không? |
|---|---|---|
| Redis key/value và TTL | String/Hash/Set/Stream | Có theo định dạng và thời điểm snapshot |
| Thông số Redis | `maxmemory`, `appendonly`, `save`, `dir` | Không nên giả định backup data tự mang đầy đủ `redis.conf` |
| ACL/credentials/TLS | ACL file, certificate, secrets | Phải backup/quản lý riêng an toàn |
| Redis module | Search/JSON/TimeSeries tùy deployment | Cần cài phiên bản tương thích và kiểm tra artifact |
| Hạ tầng và storage | Disk, PVC, hostname, firewall | Thuộc IaC/DR runbook |
| Sentinel topology | Master name, sentinels, auth | Không thể tái dựng chỉ bằng một RDB |
| Cluster topology | Slot ownership, node roles, `nodes.conf` metadata | Cần quy trình tạo lại Cluster và ánh xạ shard đúng |
| Spring configuration | Redis nodes, serializer, namespace, prefix, key mapping | Lưu trong cấu hình ứng dụng/secret manager |
| Manifest backup | Thời điểm, phiên bản, checksum, nguồn | Nên tạo riêng bởi backup pipeline |

Trong Redis Cluster, `nodes.conf` là file topology do Redis tự quản lý; **không sửa tay để “khớp” một bộ RDB bất kỳ**. Restore Cluster cần một quy trình có ý thức về shard, slot, metadata và membership.

## 5. Kiểm tra trạng thái trước khi sao lưu

Trên Redis test hoặc qua tài khoản vận hành được cấp quyền:

```bash
redis-cli -h 127.0.0.1 -p 6379 INFO server
redis-cli -h 127.0.0.1 -p 6379 INFO replication
redis-cli -h 127.0.0.1 -p 6379 INFO persistence
redis-cli -h 127.0.0.1 -p 6379 INFO memory

redis-cli -h 127.0.0.1 -p 6379 CONFIG GET dir
redis-cli -h 127.0.0.1 -p 6379 CONFIG GET dbfilename
redis-cli -h 127.0.0.1 -p 6379 CONFIG GET appendonly
redis-cli -h 127.0.0.1 -p 6379 CONFIG GET appenddirname
```

Các trường thường cần quan sát trong `INFO persistence`:

```text
rdb_bgsave_in_progress
rdb_last_bgsave_status
rdb_last_save_time
rdb_last_bgsave_time_sec
aof_enabled
aof_rewrite_in_progress
aof_last_bgrewrite_status
aof_last_write_status
```

Tên trường và tập trường có thể thay đổi theo Redis version; nên parse đúng phiên bản đang triển khai.

**Không ghi mật khẩu trực tiếp trong command history** nếu có thể tránh. Dùng cơ chế secret manager, ACL, TLS và biến môi trường bảo mật phù hợp; lệnh ví dụ chỉ dùng Redis test không xác thực.

### 5.1. Kiểm tra snapshot đang tạo hay đã hoàn tất

`BGSAVE` được xử lý bất đồng bộ. Việc CLI trả lời rằng yêu cầu được chấp nhận **không có nghĩa snapshot đã ghi xong**.

Chỉ xem một lần snapshot thành công khi:

- Không còn `rdb_bgsave_in_progress`.
- `rdb_last_bgsave_status` báo thành công.
- Mốc `rdb_last_save_time`/`LASTSAVE` đã tăng phù hợp so với trước yêu cầu.
- File đích có tồn tại và có thể sao chép/kiểm tra.

Nếu job bận vì background operation khác, `BGSAVE` có thể không bắt đầu ngay hoặc trả lỗi; backup job phải ghi nhận trạng thái thực tế thay vì mặc định thành công.

### 5.2. Theo dõi disk và memory

RDB/AOF rewrite tạo background process và dùng copy-on-write. Khi Redis có nhiều ghi trong lúc snapshot, lượng RAM phát sinh có thể tăng. Cần theo dõi disk free, latency, memory, trạng thái child process và khả năng upload backup trước khi đặt lịch snapshot quá dày.

Một snapshot hoàn chỉnh không giải quyết được trường hợp ổ đĩa backup đầy, đích offsite không truy cập được hoặc backup job chỉ giữ đúng một phiên bản rồi ghi đè.

## 6. Sao lưu RDB khi Redis vẫn đang chạy

Redis tạo RDB vào **file tạm**, sau đó thay thế file đích khi đã hoàn tất. Bản RDB hoàn chỉnh được giữ bất biến cho đến lần snapshot mới thay thế nó. Vì vậy, copy bản `dump.rdb` hiện có khi Redis đang chạy là cách Redis khuyến nghị để sao lưu, **miễn là xác định chính xác bản snapshot và tuổi dữ liệu cần lấy**.

### 6.1. Quy trình chuẩn

1. Xác định Redis instance và vai trò master/replica.
2. Kiểm tra `CONFIG GET dir`, `dbfilename`, `INFO persistence` và mốc `LASTSAVE`.
3. Nếu muốn snapshot mới, yêu cầu `BGSAVE` bằng tài khoản vận hành; không sử dụng `SAVE` blocking thường xuyên trên production.
4. Đợi `BGSAVE` hoàn tất thành công và mốc snapshot cập nhật.
5. Sao chép RDB hoàn chỉnh vào **đường dẫn staging riêng, không cùng tên với file Redis đang ghi**.
6. Tính checksum SHA-256, ghi manifest và upload tới storage độc lập.
7. Kiểm tra checksum bên đích, chính sách retention, quyền truy cập và cảnh báo.
8. Thực hiện restore drill định kỳ vào một Redis instance cách ly.

Ví dụ Redis CLI:

```bash
# Trước khi snapshot:
redis-cli -h 127.0.0.1 -p 6379 LASTSAVE
redis-cli -h 127.0.0.1 -p 6379 INFO persistence

# Chạy trên hạ tầng test hoặc dưới runbook được kiểm soát:
redis-cli -h 127.0.0.1 -p 6379 BGSAVE

# Kiểm tra cho tới khi hoàn tất:
redis-cli -h 127.0.0.1 -p 6379 INFO persistence
redis-cli -h 127.0.0.1 -p 6379 LASTSAVE
```

### 6.2. Mẫu lưu artifact bên ngoài

Giả sử file RDB hoàn chỉnh có đường dẫn `/var/lib/redis/dump.rdb` trên máy test Linux và backup directory đã được tạo:

```bash
cp /var/lib/redis/dump.rdb \
   /srv/redis-backups/staging/redis-standalone-20261113T030000Z.rdb

sha256sum \
   /srv/redis-backups/staging/redis-standalone-20261113T030000Z.rdb
```

Tên file trong ví dụ chỉ nhằm minh họa UTC timestamp. Nhiệm vụ vận hành phải tự lấy mốc giờ UTC thật, thêm node ID và run ID. Phải chắc chắn `BGSAVE` đã thành công **trước khi copy** nếu runbook yêu cầu snapshot tại lượt hiện tại.

Không xóa bản snapshot cuối còn hợp lệ chỉ vì một snapshot mới lỗi. Chỉ dọn phiên bản cũ sau khi đã xác minh các bản thay thế đạt retention và bảo vệ offsite.

### 6.3. Vì sao cần backup nhiều mốc?

```text
00:00  backup-A (trước khi lỗi ứng dụng)
01:00  backup-B
02:00  ứng dụng vô tình xóa các key quan trọng
03:00  backup-C (đã chứa trạng thái lỗi)
04:00  phát hiện sự cố
```

Nếu chỉ giữ backup-C, phục hồi từ nó **không khôi phục dữ liệu trước thao tác xóa**. Retention nhiều phiên bản giúp chọn backup-A hoặc backup-B, nhưng đồng thời có thể làm mất các ghi hợp lệ sau đó. Khôi phục nhầm toàn bộ dataset có thể gây sai lệch nghiệp vụ, nên phải phân tích **phạm vi restore** và dữ liệu cần replay/bù trừ.

## 7. Sao lưu AOF: đặc biệt chú ý Redis 7 trở lên

Redis 7.0+ dùng **multi-part AOF**: một base AOF (có thể ở định dạng RDB hoặc AOF), nhiều incremental AOF và một manifest mô tả các file hợp lệ.

Ví dụ cấu trúc minh họa:

```text
/var/lib/redis/
  appendonlydir/
    appendonly.aof.manifest
    appendonly.aof.12.base.rdb
    appendonly.aof.12.incr.aof
    appendonly.aof.13.incr.aof
```

Tên file và số thứ tự phụ thuộc server/configuration. **Không được tự suy ra rằng chỉ cần copy một file `appendonly.aof` như ở Redis cũ.** Một manifest mất file base hoặc increment sẽ không còn là bộ backup có thể phục hồi đầy đủ.

### 7.1. Vì sao copy AOF ngay lúc rewrite có thể hỏng?

Trong `BGREWRITEAOF`, Redis tạo base mới và incremental files, sau đó cập nhật manifest. Nếu backup tool copy file này trước rồi copy file khác khi rewrite đang đổi thế hệ, bản sao có thể chứa:

- Manifest của thế hệ mới, nhưng thiếu base hoặc increment được nó tham chiếu.
- Một số file thuộc thế hệ cũ và một số file thuộc thế hệ mới.
- File đã bị Redis dọn trong lúc backup chưa copy xong.

**Không dùng `cp -r appendonlydir` không kiểm soát trong khi rewrite đang diễn ra** rồi tuyên bố đã có backup nhất quán.

### 7.2. Quy trình AOF thông dụng theo tài liệu Redis

Với Redis 7+:

1. Đọc và **ghi nhớ giá trị ban đầu** của `auto-aof-rewrite-percentage`.
2. Tạm tắt auto rewrite bằng `CONFIG SET auto-aof-rewrite-percentage 0`.
3. Không kích hoạt `BGREWRITEAOF` thủ công trong cửa sổ backup.
4. Đợi `INFO persistence` báo `aof_rewrite_in_progress:0`.
5. Copy **toàn bộ các file trong `appenddirname`**, bao gồm manifest và các file base/increment liên quan, sang staging.
6. Bật lại giá trị auto rewrite ban đầu **kể cả khi copy/upload lỗi**, bằng cơ chế cleanup/finally của job.
7. Tính checksum cho từng file, ghi manifest và kiểm thử khôi phục từ bản sao.

Lệnh minh họa:

```bash
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG GET auto-aof-rewrite-percentage

# Chỉ thực thi trong runbook backup có quyền quản trị:
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG SET auto-aof-rewrite-percentage 0

redis-cli -h 127.0.0.1 -p 6379 INFO persistence

# Sau khi hoàn tất copy và không còn cần giữ auto rewrite tắt:
# Khôi phục đúng giá trị đã đọc ở bước đầu.
redis-cli -h 127.0.0.1 -p 6379 \
  CONFIG SET auto-aof-rewrite-percentage 100
```

**Số `100` cuối cùng chỉ là ví dụ**; tuyệt đối không ghi đè tùy tiện giá trị đã cấu hình ban đầu. Một backup automation cần lưu original value và có cleanup handler ngay cả khi tiến trình gặp lỗi.

Nếu thao tác copy kéo dài, hãy cân nhắc snapshot filesystem/hard links theo hướng dẫn phù hợp OS/filesystem để rút ngắn cửa sổ chặn rewrite. Không tự xây quy trình hard-link thiếu kiểm soát vì incremental AOF vẫn có thể đang được append; việc đóng gói và kiểm tra thời điểm copy phải dựa vào contract phiên bản Redis đang dùng.

### 7.3. Không bật AOF khi Redis đang chạy bằng cách sửa file cấu hình rồi restart tùy tiện

Khi chuyển từ RDB sang AOF, phải tuân theo quy trình chuyển đổi **online** được Redis hướng dẫn, theo dõi hoàn tất AOF ban đầu và cập nhật cấu hình bền vững. Chỉ đổi `appendonly no` thành `appendonly yes` trong file rồi restart có thể gây bất ngờ về việc Redis chọn artifact nào để load, thậm chí mất dữ liệu.

Đây là một thay đổi chế độ persistence; không gộp vào script sao lưu thường kỳ nếu chưa có kế hoạch migration và rollback.

## 8. Redis mới: lệnh BACKUP trực tuyến theo phiên bản

Với **Redis Open Source 8.10.0 trở lên**, tài liệu Redis giới thiệu nhóm lệnh `BACKUP` hỗ trợ tạo bộ backup online được đóng dấu và có khả năng restore, tách thời điểm bắt đầu và kết thúc:

```text
BACKUP START
     |
     v
Tạo BASE snapshot
     |
     +--> BACKUP LIST: có thể thấy file đã được pin
     |
     v
BACKUP SEAL
     |
     +--> đóng băng INCR + manifest
     |
     v
Copy các file từ BACKUP LIST ra storage độc lập
     |
     v
BACKUP CLEANUP
```

`BACKUP STATUS` cho biết trạng thái quá trình; `BACKUP ABORT` xử lý backup chưa được seal. Bộ file gồm BASE, INCR và manifest, không chỉ một `dump.rdb`. Khi khôi phục phiên bản có tính năng tương ứng, Redis có startup option `preload-file`, ví dụ chỉ minh họa:

```conf
preload-file aof:/tmp/restore-backup/appendonly.aof.manifest
```

**Không áp dụng nhóm lệnh này cho Redis 6/7/8.0 nếu server chưa hỗ trợ.** Luôn kiểm tra `INFO server`/`redis_version` và tài liệu Redis đúng phiên bản. Đây là lựa chọn mới giúp đơn giản hóa một số bước backup AOF, không thay thế việc kiểm chứng offsite, retention và khôi phục ứng dụng.

## 9. Lưu trữ bản sao: 3-2-1, encryption và kiểm soát quyền

Một kiến trúc backup có thể có:

```text
Redis data nodes
     |
     | snapshot hoàn chỉnh / bộ AOF nhất quán
     v
Backup staging (có checksum)
     |
     +--> Local backup store (khôi phục nhanh)
     |
     +--> Offsite object storage / region B
                |
                +--> Versioning / immutable retention
                +--> Encryption at rest
                +--> Integrity metadata
                +--> Access logs / alerts
```

Nguyên tắc **3-2-1** thường được dùng như hướng thiết kế: giữ nhiều bản sao, trên các dạng/lớp lưu trữ thích hợp, trong đó có bản độc lập ngoài nơi vận hành chính. Chi tiết phải phù hợp RPO, RTO, dữ liệu và ngân sách.

### 9.1. Các nguyên tắc bảo mật

- Encrypt backup trong quá trình truyền và lưu trữ, quản lý key trong hệ thống KMS/secret manager.
- Phân quyền **read backup**, **create backup**, **delete backup**, **restore** tách biệt; không để credential ứng dụng có quyền xóa mọi backup.
- Dùng versioning/object lock hoặc retention không thể sửa khi cần chống ransomware/xóa nhầm.
- Giữ log truy cập và kiểm tra ai đã tải hoặc khôi phục dữ liệu nhạy cảm.
- Không in payload session, token, key nhạy cảm trong backup manifest/log.
- Kiểm tra khả năng lấy khóa giải mã từ nơi dự phòng; backup mã hóa nhưng mất encryption key vẫn không restore được.

Backup Redis có thể chứa dữ liệu cá nhân, session token, refresh token hoặc nội dung message trong Streams. Nó phải được bảo vệ tương xứng với dữ liệu production, kể cả khi file nằm ở bucket dùng cho “test”.

### 9.2. Retention theo chu kỳ

Ví dụ:

| Loại backup | Tần suất | Retention minh họa |
|---|---|---|
| RDB gần đây | Mỗi giờ | 48 giờ |
| RDB lịch sử | Mỗi ngày | 30 ngày |
| RDB dài hạn | Mỗi tuần | 12 tuần |
| Backup AOF theo nhu cầu khôi phục gần | Theo chính sách riêng | Căn cứ RPO/storage |

Không coi bảng là luật bắt buộc. Với dữ liệu có nghĩa vụ pháp lý hoặc quyền được xóa, phải xem lại retention/PII và quy trình xóa dữ liệu trong backup theo chính sách doanh nghiệp.

## 10. Manifest: mô tả bản sao để phục hồi có căn cứ

Mỗi backup nên có metadata bên cạnh file:

```yaml
backupId: "redis-prod-20261113T030000Z-run45"
environment: "production"
redisVersion: "8.x-example"
topology: "standalone"
nodeId: "redis-prod-01"
roleAtCapture: "master"
snapshotType: "rdb"
captureRequestedAtUtc: "2026-11-13T03:00:00Z"
snapshotCompletedAtUtc: "2026-11-13T03:01:16Z"
uploadedAtUtc: "2026-11-13T03:02:03Z"
sourcePersistence:
  appendonly: true
  appendfsync: everysec
files:
  - name: "redis-prod-01-20261113T030000Z.rdb"
    bytes: 123456789
    sha256: "<SHA256 tính trên bytes thật>"
verification:
  checksumAtDestination: passed
  restoreDrill: pending
schemaVersion: 1
```

Tất cả các giá trị chỉ minh họa, không mô tả backup thật. Trong Cluster cần bổ sung shard ID, tập slot, owner master/replica, cluster generation/topology snapshot và danh sách artifact **theo node**.

**Checksum giải quyết tính toàn vẹn khi copy, không chứng minh nội dung là bản dữ liệu mong muốn.** Nếu nguồn RDB đã quá cũ nhưng copy chính xác, SHA-256 sẽ trùng mà RPO vẫn không đạt.

### 10.1. Cần kiểm tra checksum hai phía

Ví dụ trên Linux:

```bash
sha256sum /srv/redis-backups/staging/backup.rdb
sha256sum /srv/redis-backups/downloaded/backup.rdb
```

Đối chiếu cả checksum, file size và metadata của artifact. Nếu upload qua object storage, dùng checksum/ETag đúng semantics của dịch vụ: **ETag không luôn là MD5 của toàn file**, đặc biệt với multipart upload hoặc encryption. Tốt nhất là có SHA-256 do backup pipeline chủ động tính và xác minh sau tải.

## 11. Khôi phục RDB trong môi trường cách ly

**Nguyên tắc đầu tiên:** restore drill phải chạy vào một Redis instance **rỗng, độc lập**, với port, data directory, network và credentials riêng. Không copy đè file backup lên production Redis đang chạy.

### 11.1. Các bước chuẩn

1. Chọn backup ID theo RPO và thời điểm trước sự cố.
2. Tải artifact và manifest từ storage độc lập; xác minh checksum.
3. Tạo Redis instance restore có phiên bản tương thích, module phù hợp và data directory riêng.
4. **Dừng Redis restore instance** trước khi thay file nạp dữ liệu.
5. Đặt `dump.rdb` vào directory `dir` với tên `dbfilename` mong đợi.
6. Đảm bảo cấu hình AOF của instance restore **không vô tình ưu tiên AOF cũ**; nếu muốn load RDB bằng đường khởi động truyền thống thì dùng bản test bật RDB và tắt AOF, hoặc dùng cơ chế `preload-file` ở phiên bản hỗ trợ.
7. Khởi động lại Redis restore instance, xem log loading và `INFO persistence`.
8. Kiểm tra key mẫu, kiểu dữ liệu, TTL, Stream group và các chỉ số ứng dụng.
9. Ghi lại thời gian từ lúc bắt đầu tới lúc ứng dụng xác nhận hoạt động.

Ví dụ cấu hình **chỉ dành cho Redis restore test**:

```conf
bind 127.0.0.1
protected-mode yes
port 6385
dir /srv/redis-restore-lab
dbfilename dump.rdb
appendonly no
save ""
```

Sau khi copy RDB vào `/srv/redis-restore-lab/dump.rdb`, có thể khởi động một Redis process riêng bằng file cấu hình trên rồi chạy:

```bash
redis-cli -h 127.0.0.1 -p 6385 PING
redis-cli -h 127.0.0.1 -p 6385 INFO persistence
redis-cli -h 127.0.0.1 -p 6385 DBSIZE
```

`DBSIZE` chỉ cho biết số key hiện tại, **không đủ để xác nhận mọi giá trị đã đúng**. Nó cũng có thể khác số key tại thời điểm chụp vì expiration diễn ra trong thời gian lưu trữ và restore.

### 11.2. Vì sao phải thử trên instance rỗng?

Nếu restore vào một Redis đang chứa key khác, dữ liệu mới và cũ có thể trộn nhau hoặc trạng thái cũ bị ghi đè tùy phương pháp. Khi recovery production, mục tiêu thường là dựng **một dataset có nguồn gốc rõ ràng** chứ không phải tự phát ghép dữ liệu bằng nhiều `RESTORE`/`SET` rải rác không có kế hoạch.

Trong trường hợp chỉ cần khôi phục một số key sau xóa nhầm, nên cân nhắc khôi phục toàn backup vào môi trường cách ly trước, xác minh dữ liệu cần lấy, rồi xây quy trình migration có kiểm soát sang production. Việc chép lại một vài key cần xét TTL, key type, serializer, cập nhật đồng thời và tính nhất quán với hệ thống nguồn.

## 12. Khôi phục AOF và rủi ro thiếu thành phần

Với AOF nhiều phần của Redis 7+:

1. Tải **đầy đủ bộ base, incremental và manifest** mà Redis sẽ dùng.
2. Kiểm tra SHA-256 và kích thước từng file.
3. Đặt các file theo cấu trúc `appenddirname` mà Redis restore instance sẽ đọc.
4. Khởi động với Redis version/cấu hình tương thích, **không trộn một manifest mới với file AOF thế hệ khác**.
5. Quan sát log startup, thời gian replay và trạng thái load.
6. Chạy kiểm chứng dữ liệu nghiệp vụ và expiration.

Nếu AOF bị hỏng, Redis có công cụ `redis-check-aof`, nhưng không được chạy chế độ `--fix` trực tiếp trên **bản backup duy nhất**. Việc sửa có thể cắt bỏ phần log sau vị trí lỗi, gây mất dữ liệu; phải:

- Tạo bản copy bất biến của artifact lỗi.
- Ghi nhận checksum và log lỗi trước khi sửa.
- Thử trên bản sao riêng và tài liệu hóa số dữ liệu bị mất.
- Đối chiếu với backup khác và nguồn dữ liệu authoritative.

Tương tự với RDB, có thể dùng `redis-check-rdb` để kiểm tra cấu trúc file trước khi restore:

```bash
redis-check-rdb /srv/redis-backups/downloaded/dump.rdb
```

Tool có thể cần cài đúng Redis version và quyền đọc file. **Một kết quả parser hợp lệ không chứng minh các key hay dữ liệu nghiệp vụ đúng hoặc bản sao đủ mới**. Restore và integration checks vẫn cần thiết.

### 12.1. Phân biệt AOF file, AOF rewrite và backup point

`BGREWRITEAOF` tối ưu log để khởi động hiệu quả hơn. Nó **không phải lệnh tạo lịch sử backup nhiều phiên bản**; sau rewrite, file cũ có thể bị loại bỏ. Nếu chỉ giữ AOF hiện hành, không thể tùy ý chọn mốc lịch sử trước một lần ghi nhầm.

Vì vậy RDB snapshot nhiều mốc và lưu trữ offsite vẫn hữu ích ngay cả khi bật AOF.

## 13. TTL sau restore: đừng kỳ vọng thời hạn “đóng băng”

Một lỗi rất dễ gây nhầm:

```text
00:00   Ghi session:user-42 với TTL 30 phút
00:05   Chụp RDB
02:00   Restore RDB vào Redis mới
```

Ở thời điểm restore, session cũ có thể **đã hết hạn**, chứ không phải nhận lại 25 phút sử dụng. Redis lưu expiration theo mốc thời gian tuyệt đối trong cơ chế persistence tương ứng; sau khi load, những key quá hạn sẽ bị coi là đã hết hạn.

Hệ quả:

- Số key sau restore có thể **ít hơn** số key từng nằm trong snapshot.
- `DBSIZE` có thể khác ngay cả khi file nguyên vẹn.
- Session/rate-limit/cache không nên được kiểm chứng bằng “số key phải đúng từng chiếc” nếu có TTL.
- Một backup được cất nhiều ngày không phải cách giữ session sống vô hạn.
- Đồng hồ hệ thống trên môi trường restore phải chính xác; lệch clock lớn có thể làm dữ liệu bị expire sai.

### 13.1. Kiểm chứng TTL hợp lý

Ví dụ kiểm tra trên Redis restore:

```redis
TYPE product:100
TTL product:100
PTTL session:user-42
GET product:100
```

Giải thích kết quả `TTL`:

| Kết quả | Ý nghĩa |
|---|---|
| Số nguyên không âm | Thời gian còn lại tính theo giây |
| `-1` | Key còn tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại (có thể đã expire) |

Đối với key không có TTL dự kiến, một giá trị `-1` có thể hợp lệ. Đối với key bắt buộc có TTL, `-1` là dấu hiệu cần điều tra. Nên lưu **kỳ vọng policy** theo namespace thay vì giả định mọi key đều có TTL.

## 14. Sentinel: backup replica không đồng nghĩa dữ liệu đầy đủ nhất

Với Redis Sentinel:

```text
                Sentinel quorum
                      |
            Redis master M1
                 |
        asynchronous replication
                 |
            Redis replica R1
                 |
         tạo/copy RDB từ replica
```

Lấy backup từ replica thường giúp giảm áp lực tạo snapshot lên master. Tuy nhiên, replication bất đồng bộ có nghĩa replica **có thể chưa nhận những ghi gần nhất**.

Khi dùng replica làm nguồn backup:

1. Xác nhận nó đang replicate từ master đúng.
2. Theo dõi `INFO replication`: role, link status, offset/lag phù hợp.
3. Đo độ trễ replica và xác định recovery point thực tế.
4. Chỉ chụp sau khi xác nhận replica đã bắt kịp ngưỡng mà RPO yêu cầu.
5. Đề phòng failover xảy ra giữa lúc chọn node và lúc sao lưu.
6. Ghi node ID, role, master group, thời điểm, replication state vào manifest.

Không coi bản backup từ replica là snapshot tuyến tính hóa với mọi write đã ACK ở master. Nếu lệnh ghi đã trả OK trên master nhưng chưa replicate tới R1, backup của R1 có thể thiếu lệnh đó.

### 14.1. Failover xảy ra giữa backup

Nếu master thay đổi trong lúc chạy backup:

- Node nguồn có thể đổi vai trò master/replica.
- Replication offset và dữ liệu chụp có thể không phản ánh mốc dự định.
- Client Spring Data Redis có thể kết nối tới master mới trong khi backup đang chạy trên node cũ.

Runbook nên ghi lại topology **trước và sau** lần backup. Nếu không chứng minh được tính phù hợp của recovery point, đánh dấu lần chạy là **suspect/quarantine** thay vì cho vào danh sách “backup hợp lệ”.

## 15. Redis Cluster: phải bảo vệ tất cả shard

Redis Cluster chia key thành 16.384 hash slot, do nhiều master cùng quản lý. **Một RDB của master không phải bản sao toàn bộ Cluster**.

```text
                         Redis Cluster
                       16.384 hash slots
                              |
               +--------------+--------------+
               |              |              |
          Master A         Master B        Master C
          slots A          slots B         slots C
               |              |              |
             RDB-A          RDB-B          RDB-C
               |              |              |
               +--------------+--------------+
                              |
                    Backup set + manifest
                              |
                       Offsite storage
```

Để khôi phục toàn bộ logical dataset, phải có snapshot/dataset tương ứng **từng shard**. Nếu Cluster có resharding, failover, replica migration đang chạy, cần quan sát topology ở thời điểm sao lưu và đặt quy tắc phát hiện bộ backup bị thiếu/trùng slot.

### 15.1. Không có global snapshot atomic mặc định

Giả sử:

```text
10:00:00  Backup shard A
10:00:30  Ứng dụng cập nhật A rồi B
10:01:00  Backup shard B
```

Một bản backup ghép A lúc 10:00 với B lúc 10:01 có thể không phản ánh một trạng thái toàn Cluster từng tồn tại đúng tại một mốc thời gian. Nếu nghiệp vụ có thao tác xuyên shard, bản sao đó có thể chứa dữ liệu lệch nhau.

Giải pháp tùy yêu cầu:

- Nếu Redis chỉ là cache: backup mỗi shard độc lập có thể đủ; nạp lại từ nguồn authoritative sau restore.
- Nếu dữ liệu có tương quan chặt: tạo **application-level consistency point**, tạm ngừng ghi có kiểm soát hoặc dùng changelog/outbox để tái đồng bộ.
- Nếu không thể dừng ghi: có thể cần cơ chế snapshot/changelog chuyên dụng và quy tắc replay theo thứ tự nghiệp vụ; không mặc định RDB độc lập tạo global transaction.
- Nếu dùng Redis 8.10+ `BACKUP START/SEAL`, có thể quản lý cửa sổ backup các node hiệu quả hơn nhưng **không mặc nhiên tạo atomic snapshot xuyên nhiều shard**.

### 15.2. Manifest Cluster cần thêm gì?

```yaml
backupId: cluster-20261113T030000Z
topology: cluster
clusterState: ok
expectedSlots: 16384
shards:
  - shardId: "shard-A"
    roleAtCapture: master
    nodeId: "node-a"
    slotRanges: ["0-5460"]
    artifact: "node-a.rdb"
    sha256: "<computed>"
  - shardId: "shard-B"
    roleAtCapture: master
    nodeId: "node-b"
    slotRanges: ["5461-10922"]
    artifact: "node-b.rdb"
    sha256: "<computed>"
  - shardId: "shard-C"
    roleAtCapture: master
    nodeId: "node-c"
    slotRanges: ["10923-16383"]
    artifact: "node-c.rdb"
    sha256: "<computed>"
```

Các slot range chỉ minh họa cách chia ba master. Khi thao tác thật, lấy từ `CLUSTER SHARDS` hoặc `CLUSTER SLOTS` của Cluster đang chạy, không giả định node A/B/C sở hữu các khoảng cố định như ví dụ.

### 15.3. Điều cần kiểm chứng trước khi công nhận một backup set

- Có đủ artifact cho tất cả master/shard cần bảo vệ không?
- Các khoảng slot được gán không thiếu và không overlap bất hợp lý theo mốc được chọn?
- Node tạo backup là master hay replica của shard nào?
- Replication lag có phù hợp RPO không?
- Trong cửa sổ chụp có resharding/failover không?
- Có thể dựng lại Cluster trống phù hợp với topology, sau đó nạp dữ liệu từng shard theo runbook đã thử nghiệm không?

Không tùy tiện copy toàn bộ RDB từ các master vào một Redis Standalone rồi hy vọng Redis tự hợp nhất data và giữ đúng keyspace/slot.

## 16. Khôi phục Cluster: hai đường đi khác nhau

### 16.1. Disaster recovery toàn Cluster

Quy trình tổng quát:

1. Xác định backup set và manifest **đủ shard**.
2. Dựng hạ tầng Redis Cluster mới ở vùng restore: node, network, disk, tài khoản, TLS, phiên bản.
3. Tạo/khôi phục topology và phân bổ slot theo runbook của Redis version đang sử dụng.
4. Nạp artifact tương ứng đúng shard/node hoặc dùng công cụ restore/cluster migration được hỗ trợ.
5. Xác minh `CLUSTER INFO` báo slot coverage đầy đủ và các master/replica được thiết lập.
6. Xác minh dữ liệu theo từng namespace/slot và từ ứng dụng Spring.
7. Chỉ chuyển traffic sau khi read/write smoke test, health và business reconciliation đạt yêu cầu.

Các bước thực tế liên quan địa chỉ node, thông số cluster state và phương pháp import dữ liệu phụ thuộc Redis version, orchestrator và công cụ backup. **Không thể chỉ dùng một lệnh `redis-cli --cluster create` rồi nạp ngẫu nhiên các file RDB vào từng node production** mà không đối chiếu mapping slot.

### 16.2. Khôi phục một nhóm key bị xóa nhầm

Khôi phục toàn Cluster về một mốc cũ có thể làm mất các ghi hợp lệ phát sinh sau đó. Nếu chỉ mất một số key:

1. Restore backup vào môi trường **cách ly**.
2. Xác định key cần lấy bằng nguồn dữ liệu nghiệp vụ, không dùng `KEYS *` trên production lớn.
3. Xác minh kiểu dữ liệu, TTL, giá trị, phụ thuộc index và idempotency.
4. Lên kế hoạch copy/migrate từng key sang production bằng API phù hợp.
5. Bảo vệ dữ liệu mới có thể đã xuất hiện cùng tên key từ thời điểm sự cố.

Redis `DUMP`/`RESTORE` có thể hỗ trợ di chuyển biểu diễn một key, nhưng việc sử dụng trực tiếp cần xét encoding version, expiration, key tồn tại và lựa chọn replace. Không biến một script khôi phục dữ liệu cũ thành cách ghi đè production vô điều kiện.

## 17. Kiểm chứng bản sao theo ba tầng

Một chính sách backup đáng tin nên có **ba mức xác thực**, không thay thế lẫn nhau:

### Mức 1 — File và đường truyền

Kiểm tra:

- Có đủ file/artifact và manifest.
- File size khớp, SHA-256 khớp nguồn và đích.
- Storage trả về đúng phiên bản object/backup ID.
- Không có lỗi upload multipart hoặc file thiếu.
- Backup không bị xóa theo lifecycle policy sớm hơn dự kiến.

### Mức 2 — Redis có thể đọc file

Kiểm tra:

- `redis-check-rdb` hoặc công cụ AOF phù hợp version không báo lỗi cấu trúc.
- Redis test instance khởi động và nạp dữ liệu thành công.
- Startup log không báo checksum error, invalid AOF hoặc thiếu module.
- Thời gian load nằm trong giới hạn RTO dự kiến.
- `INFO persistence` cho biết trạng thái bình thường sau restore.

### Mức 3 — Dữ liệu đúng theo nghiệp vụ

Kiểm tra:

- Các key/cấu trúc quan trọng còn truy cập được.
- Kiểu Redis (String, Hash, Stream, ZSet...) phù hợp.
- Những key có TTL được restore theo đúng quy tắc expiration.
- Schema/serializer của Spring Data Redis đọc được dữ liệu.
- Consumer groups/Stream recovery và các index phụ trợ hoạt động.
- Số liệu nghiệp vụ có thể đối chiếu với nguồn authoritative hoặc consistency marker.

**Một backup SHA-256 khớp nhưng không load được Redis là thất bại. Một backup load được nhưng chứa trạng thái lỗi nghiệp vụ cũng chưa đủ để phục hồi.**

## 18. Thiết kế canary và integrity marker

Để kiểm chứng một recovery point, có thể tạo **marker kiểm thử** với key riêng, không trùng dữ liệu khách hàng. Ví dụ khi job backup chuẩn bị chụp RDB:

```redis
HSET backup:canary:run45 id run45 expectedValue "ok" createdAt "2026-11-13T03:00:00Z"
```

Chỉ tính marker này vào kỳ vọng snapshot nếu đã xác nhận ghi hoàn tất **trước thời điểm Redis thực sự chụp dữ liệu**. Một lệnh marker được gửi sau khi `BGSAVE` đã fork **không nhất thiết có trong snapshot đang tạo**.

Sau restore:

```redis
HGETALL backup:canary:run45
TYPE backup:canary:run45
```

Một marker tồn tại là bằng chứng tốt cho một mốc dữ liệu, nhưng chưa chứng minh toàn bộ dataset đúng. Nên kết hợp:

- Một số key có giá trị định trước ở các namespace quan trọng.
- Key chứa Hash/ZSet/Stream với field và thành viên kiểm chứng cụ thể.
- Tổng số record theo hệ thống nguồn.
- Checksum/digest theo những tập dữ liệu đã chốt ở mốc nhất quán.

### 18.1. Tránh kiểm chứng bằng quét toàn bộ keyset trong lúc production đang ghi

Trên Redis đang chạy, `SCAN` không tạo snapshot atomic của toàn keyspace. Nếu key thay đổi trong lúc quét, không thể coi bộ kết quả là danh sách nhất quán ở đúng một timestamp.

Trong Redis Cluster, `SCAN` trên **một node** chỉ phản ánh key mà node đó phục vụ; muốn kiểm kê toàn Cluster phải duyệt các master/slot phù hợp. Với dataset lớn, checksum toàn bộ key/value nên thực hiện trên **restore instance cách ly** hoặc dùng metadata ứng dụng có mốc snapshot riêng.

## 19. Kiểm chứng từ ứng dụng Spring Data Redis

Sau khi Redis restore instance đã được khởi động, Spring Boot test có thể kết nối tới môi trường này bằng endpoint và credentials riêng. Không để một instance thử nghiệm vô tình dùng connection factory của production.

Ví dụ cấu hình test profile:

```yaml
spring:
  data:
    redis:
      host: 127.0.0.1
      port: 6385
      timeout: 3s
```

### 19.1. Dùng StringRedisTemplate kiểm tra một số invariant

Giả sử backup dự kiến chứa:

```text
backup:canary:run45 (Hash)
catalog:version      (String, không TTL)
session:test-42      (String, có TTL; có thể đã hết hạn nếu restore muộn)
```

Một service xác minh:

```java
import java.util.Map;
import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisRestoreVerifier {

    private final StringRedisTemplate redis;

    public RedisRestoreVerifier(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void verifyCanary(String backupRunId) {
        String key = "backup:canary:" + backupRunId;

        DataType type = redis.type(key);
        if (type != DataType.HASH) {
            throw new IllegalStateException(
                    "Canary key missing or wrong type: " + type);
        }

        Map<Object, Object> fields =
                redis.opsForHash().entries(key);

        if (!backupRunId.equals(fields.get("id"))) {
            throw new IllegalStateException(
                    "Canary backup run ID does not match");
        }

        if (!"ok".equals(fields.get("expectedValue"))) {
            throw new IllegalStateException(
                    "Canary payload is invalid");
        }
    }
}
```

Đây là kiểm chứng **read-only** đối với một canary đã được ghi trước snapshot. Nó không tạo marker mới vào bản restore, nhờ đó không che khuất lỗi backup. Trong ứng dụng dùng serializer JSON/JDK khác, phải dùng đúng `RedisTemplate`/`RedisSerializationContext`, không tùy tiện đọc mọi value như String.

### 19.2. Kiểm tra TTL bằng Spring Data Redis

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public void checkExpiringKey(
        StringRedisTemplate redis,
        String key) {

    Duration ttl = redis.getExpire(key);

    if (ttl == null) {
        throw new IllegalStateException(
                "Cannot determine TTL of " + key);
    }

    // Spring có thể biểu diễn Redis -1/-2 dưới dạng Duration âm.
    // Chỉ sử dụng so sánh có hiểu biết về policy của key.
    if (!ttl.isNegative() && ttl.isZero()) {
        // Key sắp hoặc đã hết thời hạn; không mặc định lỗi backup.
    }
}
```

Với key TTL, kết quả phụ thuộc thời điểm restore. Kiểm chứng nên mô tả: “key có thể đã expire vì backup cũ” hoặc “key này theo policy không được phép có TTL”, thay vì ép mọi key có TTL đúng bằng số giây lúc capture.

### 19.3. Kiểm chứng Redis Stream

Nếu Redis Streams giữ công việc quan trọng, kiểm tra thêm:

```redis
TYPE orders:events
XLEN orders:events
XINFO STREAM orders:events
XINFO GROUPS orders:events
XPENDING orders:events billing-workers
```

Phải đối chiếu:

- Message ID/cursor có còn đúng không?
- Consumer group và trạng thái pending có khớp recovery point không?
- Những message chưa `XACK` có cần reprocess không?
- Đã có idempotency để tránh side effect hai lần sau restore không?
- Những message mới hơn backup nhưng đã được xử lý ở nơi khác có cần reconciliation không?

Khôi phục Streams không tự rollback tác dụng phụ đã xảy ra ngoài Redis, và không bảo đảm consumer group chạy lại từ vị trí phù hợp nếu logic ứng dụng bỏ qua PEL.

## 20. RPO/RTO cho Spring Cache, Repository và Streams không giống nhau

Spring Data Redis có nhiều cách sử dụng Redis, nên kế hoạch restore phải phân biệt:

### 20.1. Spring Cache

Một cache có `@Cacheable` thường có thể nạp lại từ database. Khôi phục cache **quá cũ** có thể nguy hiểm hơn khởi động với cache rỗng, vì key cũ vẫn tồn tại và có TTL dài hoặc không TTL.

Ví dụ:

```java
@Cacheable(cacheNames = "productDetails", key = "#id")
public ProductView getProduct(String id) {
    return repository.load(id);
}
```

Sau restore, hãy cân nhắc:

- Flush/xóa có chọn lọc những cache được xác định có thể tái tạo.
- Dùng namespace version như `app:v2:...` khi schema cache thay đổi.
- Warm up có kiểm soát để tránh cache stampede gây tải lên database.
- Không khôi phục cache giá/tồn kho cũ rồi dùng nó làm nguồn quyết định giao dịch.

### 20.2. Redis Repository

Với `@RedisHash` và các key phụ trợ cho entity/index:

- Không chỉ kiểm tra key entity tồn tại; còn phải xét index, set ID, TTL và schema/serializer.
- Index có thể không phù hợp sau khi rollback dữ liệu hoặc thay đổi application version.
- Không đưa toàn bộ entity vào một backup mới mà bỏ qua cấu trúc phụ trợ Spring tạo ra.

Sau restore staging, chạy các truy vấn Repository mà ứng dụng thật dùng, không chỉ `GET` raw bytes.

### 20.3. Redis Streams

Streams có thể chứa tiến độ xử lý và pending. Nếu restore về mốc cũ:

- Một event đã được ACK sau mốc backup có thể lại xuất hiện như chưa ACK.
- Một event được ghi sau backup có thể không còn trong dataset restore.
- Tác dụng phụ ở SQL/API bên ngoài vẫn có thể còn.

Vì vậy, **idempotency và reconciliation** là một phần bắt buộc của DR plan cho message processing.

## 21. Diễn tập khôi phục định kỳ: phải đo bằng đồng hồ

Một lần diễn tập có thể có runbook:

```text
T0  Nhận tín hiệu "môi trường Redis chính không khả dụng"
 |
 +-- Xác định tình trạng và chọn backup ID
 |
 +-- Tải manifest + artifact về môi trường restore
 |
 +-- Kiểm tra SHA-256 và tính đầy đủ
 |
 +-- Tạo hạ tầng Redis version phù hợp
 |
 +-- Nạp RDB/AOF và chờ Redis ready
 |
 +-- Kiểm tra CLI + business canary
 |
 +-- Khởi chạy Spring app bằng restore profile
 |
 +-- Smoke test các luồng đọc/ghi và reconciliation
 |
 +-- Ghi nhận kết quả và thời gian thực tế
 v
T1  Restore accepted / drill completed
```

Thời gian **T1 − T0** là số liệu thực tế phục vụ RTO, nhưng phải mô tả rõ phạm vi: “Redis sẵn sàng” khác “ứng dụng đã phục vụ khách hàng bình thường”.

### 21.1. Những lần diễn tập nên có

| Kịch bản | Mục tiêu |
|---|---|
| Restore RDB mới nhất | Xác nhận artifact hợp lệ và quy trình nhanh nhất |
| Restore RDB cũ hơn 24 giờ | Xác nhận retention, khả năng chọn phiên bản và TTL |
| Restore bộ AOF nhiều phần | Xác nhận đủ base/increment/manifest và thời gian replay |
| Mô phỏng mất một artifact | Hệ thống có phát hiện lỗi và từ chối backup set không? |
| Restore khi thiếu module hoặc serializer cũ | Đánh giá khả năng tương thích và runbook migration |
| Restore Redis Streams | Xác nhận consumer group, pending, idempotency |
| Restore Sentinel topology | Kiểm tra cấu hình master discovery, ACL/TLS |
| Restore Redis Cluster | Xác minh đủ shard/slot và consistency giữa các phần |
| Khôi phục khi bucket chính unavailable | Đánh giá bản sao offsite thứ hai |

Một pipeline chỉ báo `backup_success=1` do upload thành công mà chưa từng restore là **chưa được chứng minh có thể khôi phục**.

## 22. Quy trình kiểm chứng bản sao tự động

Một backup pipeline có thể gồm:

```text
TRIGGER
   |
   v
Xác định topology và capture policy
   |
   v
Tạo snapshot / sealed AOF set
   |
   v
Chờ lệnh hoàn tất + kiểm tra trạng thái Redis
   |
   v
Copy artifact sang staging + tính SHA-256
   |
   v
Upload offsite + xác minh checksum đích
   |
   v
Ghi manifest và đánh dấu VERIFIED_TRANSFER
   |
   v
Restore drill (theo lịch lấy mẫu)
   |
   v
Kiểm chứng Redis load + app business checks
   |
   v
Đánh dấu VERIFIED_RESTORE / ALERT nếu không đạt
```

### 22.1. Phân biệt trạng thái backup

| Trạng thái | Ý nghĩa |
|---|---|
| `CAPTURING` | Redis đang tạo bản sao |
| `CAPTURED` | Artifact có mặt tại staging, chưa xác minh upload |
| `TRANSFERRED` | Artifact đã lên storage bên ngoài |
| `VERIFIED_TRANSFER` | Checksum, file count và metadata đích hợp lệ |
| `VERIFIED_RESTORE` | Đã restore thử và đạt smoke/integrity checks |
| `FAILED` | Có lỗi; không dùng làm recovery point mặc định |
| `SUSPECT` | Tính nhất quán/tuổi dữ liệu không chứng minh được |

Không xóa thông tin lỗi của backup cũ khi retry. Mỗi run nên có `runId` riêng để truy vết.

### 22.2. Không làm backup job trở thành nguồn mất dữ liệu

Một công cụ backup cần **ít quyền nhất có thể**:

- Không cần quyền `FLUSHALL`/`FLUSHDB`.
- Không được tùy tiện sửa Redis config mà không có cleanup.
- Không ghi đè dữ liệu Redis production trong quá trình “thử restore”.
- Không lưu credential plaintext trong log.
- Tài khoản upload backup không nhất thiết có quyền xóa tất cả lịch sử.

Khi backup thất bại, hệ thống nên **báo động và giữ bản tốt cuối cùng**, không cố “sửa” live AOF/RDB hoặc xóa file đang được Redis dùng.

## 23. Giám sát và cảnh báo

| Metric hoặc cảnh báo | Ý nghĩa |
|---|---|
| Tuổi của **backup offsite cuối đã xác minh** | Đo khả năng đáp ứng RPO |
| `rdb_last_bgsave_status` | Lỗi snapshot |
| `rdb_last_save_time` | Mốc RDB được chụp |
| `aof_last_write_status` | Trạng thái ghi AOF |
| `aof_rewrite_in_progress` và duration | Rewrite kéo dài hoặc mắc kẹt |
| Disk available và I/O latency | Rủi ro đầy đĩa hoặc snapshot chậm |
| Upload failure / checksum mismatch | Bản sao đích hỏng hoặc thiếu |
| Replica lag / role change | Rủi ro backup từ replica cũ |
| Cluster slots covered | Phát hiện backup set thiếu shard/topology lỗi |
| Restore drill elapsed time | Đo RTO thực tế |
| Business verification failures | Bản sao load được nhưng dữ liệu không đúng |
| Encryption/key access failures | Backup không thể giải mã khi cần |

Tên metric có thể do pipeline backup hoặc hệ thống monitoring tự định nghĩa. Redis `INFO` chỉ phản ánh trạng thái server hiện tại; nó không biết bản backup đã được mã hóa/upload thành công lên bucket hay chưa.

### 23.1. Một điều kiện cảnh báo RPO có ý nghĩa

Ví dụ:

```text
RPO mục tiêu: 30 phút
Now: 04:00 UTC
Latest VERIFIED_TRANSFER snapshot completed: 02:45 UTC
Age: 75 phút
=> RPO mục tiêu không được bảo vệ ở thời điểm này
```

Nếu snapshot lúc 03:50 mới chỉ nằm trên cùng ổ đĩa với Redis, chưa upload offsite, nó **không thể** được dùng để chứng minh phục hồi sau khi máy/ổ đĩa đó mất hẳn.

## 24. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Có `dump.rdb` nhưng thiếu dữ liệu mới | Snapshot cũ, `BGSAVE` thất bại | Kiểm tra `LASTSAVE` và `INFO persistence` |
| Backup job báo OK ngay khi gọi `BGSAVE` | Không đợi background snapshot xong | Chỉ công nhận sau status/time xác nhận |
| RDB checksum khớp nhưng Redis không load | File format/module/version không tương thích | Dùng restore test và log startup |
| Restore RDB nhưng dữ liệu không đổi | Redis khởi động từ AOF đang bật | Tách clean restore instance, kiểm tra cấu hình ưu tiên load |
| Restore session bị thiếu hàng loạt | TTL hết hạn trong thời gian cất backup | Kiểm tra expiration absolute và thiết kế session |
| Redis 7+ AOF backup thiếu file | Chỉ copy một `.aof` hoặc thiếu manifest | Copy cả bộ base/increment/manifest đúng thế hệ |
| AOF backup không nhất quán | Copy giữa `BGREWRITEAOF` | Ngăn rewrite trong cửa sổ copy hoặc dùng cơ chế BACKUP hỗ trợ |
| File đã upload nhưng không download được | ACL/bucket/KMS/lifecycle lỗi | Restore drill trên account/site dự phòng |
| Tất cả replica đã mất dữ liệu | Xóa nhầm được replicate | Dùng backup lịch sử độc lập |
| Backup từ replica có số record ít hơn master | Replication lag | Ghi role/offset/lag, kiểm tra RPO |
| Cluster restore thiếu nhiều key | Chỉ backup một shard hoặc slot map sai | Manifest đầy đủ mỗi master/shard và restore test Cluster |
| Cross-shard dataset không nhất quán | Snapshot từng node ở thời điểm khác nhau | Quiescence/app reconciliation hoặc cơ chế snapshot đồng bộ |
| Spring không deserialize được value | Serializer/schema/class/module thay đổi | Dùng build/schema tương thích hoặc migration |
| Redis Streams chạy lại task đã xử lý | Backup cũ chứa pending/cursor cũ | Idempotency, outbox/reconciliation |
| `DBSIZE` không khớp | Expiration hoặc thời điểm snapshot khác | So sánh key sample và TTL policy, không chỉ số lượng |
| Restore lâu hơn SLA | AOF replay quá dài/dataset lớn/disk chậm | Diễn tập, cân nhắc RDB + AOF và tối ưu hạ tầng |
| Backup bị xóa ngay sau khi tạo | Lifecycle policy hoặc quyền xóa quá rộng | Versioning/immutability và giám sát retention |

## 25. Bài thực hành tích hợp

Những bài sau cần Redis test, data directory riêng và không được gây gián đoạn production.

### Bài 1 — Chụp và khôi phục RDB

1. Khởi động Redis test có persistence RDB.
2. Ghi một String, một Hash, một Set và một key có TTL.
3. Ghi canary `backup:canary:lab1`.
4. Chạy `BGSAVE`, đợi `rdb_last_bgsave_status:ok` và `LASTSAVE` thay đổi.
5. Copy `dump.rdb` sang thư mục staging, tính SHA-256.
6. Dựng Redis instance khác trên port riêng và load RDB.
7. Đối chiếu key/value/type/TTL/canary và thời gian restore.

### Bài 2 — Bảo đảm backup AOF Redis 7+

1. Bật AOF trên Redis test và bảo đảm data directory riêng.
2. Xem `CONFIG GET appenddirname` và `INFO persistence`.
3. Xác định base/increment/manifest đang dùng.
4. Tạm tắt auto rewrite theo quy trình, đợi rewrite idle.
5. Sao lưu **toàn bộ bộ file AOF** và khôi phục config.
6. Restore trên instance test bằng đúng bộ AOF, kiểm tra lệnh load và dữ liệu.
7. Thử bỏ một file được manifest tham chiếu **trong bản sao lab**, xác nhận pipeline phát hiện bất hợp lệ thay vì chấp nhận.

### Bài 3 — TTL sau backup cũ

1. `SET lab:ttl value EX 10`.
2. Chụp RDB ngay sau khi ghi.
3. Đợi hơn 10 giây.
4. Restore RDB vào instance cách ly.
5. Chạy `GET lab:ttl` và `TTL lab:ttl`; giải thích lý do key có thể không còn dù snapshot nguyên vẹn.

### Bài 4 — Redis Streams và idempotency

1. Tạo một Stream và consumer group test.
2. Đọc một message để nó vào PEL, không ACK.
3. Chụp RDB rồi xử lý và ACK message trong instance gốc.
4. Restore bản chụp vào test instance.
5. Kiểm tra PEL và thảo luận vì sao side effect ở database ngoài Redis có thể đã hoàn tất.
6. Thiết kế `eventId`/idempotency để xử lý redelivery an toàn.

### Bài 5 — Backup set Redis Cluster

1. Trên Cluster test có nhiều master, gọi `CLUSTER SHARDS`.
2. Ghi vài key có hash tag thuộc những slot do master khác nhau sở hữu.
3. Lập danh sách artifact riêng theo từng shard.
4. Ghi manifest các range slot, node, role, timestamp và checksum.
5. Kiểm tra bộ backup có đủ 16.384 slot theo topology mốc thu thập không.
6. Diễn tập restore theo quy trình Cluster mà môi trường hỗ trợ, kiểm tra key từ tất cả master.

### Bài 6 — Đo RTO

1. Bắt đầu timer từ lúc báo sự cố giả lập.
2. Chọn backup, tải file, tạo restore instance, load data.
3. Chạy Spring Boot với restore profile.
4. Kiểm tra health, canary, các thao tác Redis cơ bản và luồng nghiệp vụ mẫu.
5. Ghi thời gian từng bước, bước chậm nhất và tổng RTO thực tế.

### Bài 7 — Phát hiện dữ liệu sai dù checksum đúng

1. Tạo backup snapshot **sau khi** cố ý thay một giá trị test từ đúng thành sai.
2. Copy và xác minh SHA-256: bản sao hợp lệ về mặt truyền file.
3. Restore và chạy business verifier: phải phát hiện giá trị sai.
4. Giải thích vì sao checksum không thay thế application-level validation.

## 26. Checklist runbook trước khi triển khai

**Kiến trúc dữ liệu**

1. Đã phân loại Redis key nào là cache tái tạo, key nào là dữ liệu authoritative?
2. Có RPO/RTO được business chấp nhận cho từng nhóm dữ liệu?
3. Đã chọn RDB/AOF và chính sách fsync/save dựa trên mô hình lỗi?
4. Nếu Redis giữ Stream, đã có idempotency và recovery consumer group?

**Backup pipeline**

5. Backup RDB có chờ `BGSAVE` hoàn tất và kiểm tra `LASTSAVE`?
6. Redis 7+ AOF có backup đầy đủ base/increment/manifest và tránh rewrite race?
7. Có manifest và SHA-256 cho mọi file, từng shard?
8. Backup được mã hóa, upload offsite và giữ nhiều phiên bản?
9. Có cảnh báo khi bản backup offsite cuối được xác minh quá cũ?
10. Có kiểm soát permission và backup deletion?

**Restore**

11. Có instance staging riêng để restore, không ghi đè production?
12. Có xác định RDB/AOF nào được Redis load theo configuration?
13. Có chuẩn bị Redis version, module, ACL/TLS, serializer và application version tương thích?
14. Có kiểm tra TTL, key type, canary, Stream group và dữ liệu nghiệp vụ?
15. Với Sentinel/Cluster, có runbook tái tạo topology và backup đủ shard?
16. Có thực hành failover, mất file, backup cũ và lỗi checksum?
17. Đã đo RTO thực tế tới mốc **ứng dụng usable**, không chỉ Redis `PING`?
18. Có owner, lịch diễn tập và lưu lại bằng chứng hoàn thành?

## 27. Kết luận

Một thiết kế sao lưu Redis hiệu quả không dừng ở việc bật `save` hoặc `appendonly yes`. **Persistence** giúp Redis khởi động lại sau một số lỗi cục bộ; **replication** hỗ trợ availability; **backup nhiều phiên bản ngoài hệ thống vận hành** giúp khôi phục khi dữ liệu bị xóa nhầm, hỏng hoặc mất cả hạ tầng; **restore drill** mới chứng minh bộ backup thực sự sử dụng được.

Với RDB, hãy kiểm tra snapshot hoàn tất trước khi copy, lưu timestamp/checksum và giữ các mốc lịch sử. Với AOF, đặc biệt từ Redis 7 trở lên, cần quản lý **toàn bộ bộ base/increment/manifest** nhất quán và tránh race với rewrite. Redis 8.10+ cung cấp thêm nhóm lệnh `BACKUP`, nhưng tính năng phải được xác nhận theo server version. Với Sentinel, kiểm tra replication lag và thay đổi vai trò; với Cluster, sao lưu **từng shard** và không tự giả định có global atomic snapshot.

Cuối cùng, **checksum chỉ chứng minh tính toàn vẹn của bytes**, còn một lần restore thành công cộng với kiểm chứng nghiệp vụ mới chứng minh khả năng phục hồi. Hãy thiết kế RPO/RTO, bảo vệ offsite, kiểm tra TTL/Streams/serializer và diễn tập khôi phục từ một bản backup cũ bất kỳ trước khi khẳng định hệ thống có phương án disaster recovery.

## Tài liệu tham khảo

- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/): RDB/AOF, multi-part AOF Redis 7+, quy trình backup, restore và lệnh BACKUP Redis mới.
- [Redis — BGSAVE](https://redis.io/docs/latest/commands/bgsave/): snapshot bất đồng bộ và trạng thái khi có background operation.
- [Redis — LASTSAVE](https://redis.io/docs/latest/commands/lastsave/): xác định thời điểm snapshot RDB hoàn tất.
- [Redis — INFO](https://redis.io/docs/latest/commands/info/): persistence/replication/role và các chỉ số vận hành.
- [Redis — CONFIG GET](https://redis.io/docs/latest/commands/config-get/): đọc cấu hình server hiện tại.
- [Redis — AOF rewrite](https://redis.io/docs/latest/commands/bgrewriteaof/): quá trình ghi lại AOF.
- [Redis — Backup START](https://redis.io/docs/latest/commands/backup-start/): quy trình backup trực tuyến mới theo version.
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/): replication bất đồng bộ và những giới hạn.
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/): failover, master discovery và topology.
- [Redis — Cluster scaling](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/): shard, slot, failover và các bước vận hành Cluster.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): các trạng thái expiration của key.
- [Redis — Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/): cấu trúc Streams và consumer groups.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): truy cập và kiểm chứng dữ liệu bằng Spring Data Redis.
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): mapping/index/TTL khi dùng Repository.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Stream operations và trạng thái consumer group.
