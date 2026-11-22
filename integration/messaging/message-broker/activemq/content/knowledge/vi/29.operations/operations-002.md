# Quản lý volume, quyền truy cập và yêu cầu của bộ lưu trữ

> **Chương:** Vận hành  
> **Module:** `INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ` — Apache ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ với queue, topic, routing và JMS; vận hành producer/consumer, persistence, acknowledgment, transaction, redelivery, DLQ và bảo mật.  
> **Phạm vi:** Thiết kế dung lượng/I/O, bố trí volume, quyền filesystem của broker process, giới hạn dung lượng và backup/restore. Ví dụ gồm **ActiveMQ Classic/KahaDB** và **ActiveMQ Artemis/file journal**.

## 1. Storage quyết định độ tin cậy của message

Khi persistence bật, broker phải ghi message và trạng thái liên quan vào storage. Với message persistent, transaction commit và acknowledgment, chất lượng đường ghi bền vững ảnh hưởng trực tiếp đến khả năng phục hồi sau crash. Broker có thể nhận kết nối bình thường nhưng vẫn ngừng phục vụ khi volume đầy, filesystem chuyển read-only hoặc process mất quyền ghi journal.

Ba nhóm yêu cầu phải được quản lý cùng nhau:

1. **Capacity:** đủ dung lượng cho backlog, message lớn, paging, DLQ, transaction/recovery, log và phần dự phòng.
2. **Storage behavior:** độ trễ ghi/flush, IOPS, filesystem, write cache, mount và khả năng phục hồi sau lỗi.
3. **Access control:** đúng service account có quyền cần thiết lên data directories; process/người dùng khác không thể tùy ý sửa hoặc xóa journal.

~~~mermaid
flowchart TD
    P["Producer gửi persistent message"] --> B["Broker nhận và kiểm tra policy"]
    B --> J["Persistence journal / message store"]
    J --> C["Commit được xác nhận"]
    C --> W["Consumer nhận và xử lý"]
    W --> A["Broker ghi ACK / reclaim"]
    V["Volume: dung lượng, quyền, I/O, mount"] -.-> J
    X["Paging / large messages / temp / logs"] -.-> V
    R["Backup + restore"] -.-> V
~~~

Storage không chỉ chứa body. Broker còn cần index/bindings, metadata, transaction state, acknowledgment records, duplicate-detection state, page files và large-message payload. Chỉ cộng kích thước JSON trong queue browser sẽ đánh giá thiếu dung lượng.
## 2. Những vùng dữ liệu của Classic và Artemis

### 2.1. ActiveMQ Classic: KahaDB

KahaDB là persistence adapter dạng file và là lựa chọn mặc định của ActiveMQ Classic hiện đại. Thư mục KahaDB chứa message journal/store và index. Đường dẫn mặc định có thể phụ thuộc biến cấu hình `activemq.data`; vận hành production cần biết **đường dẫn tuyệt đối thực tế** mà broker mở.

Ví dụ bố trí:

~~~text
/etc/activemq/                  cấu hình, root quản lý
/var/log/activemq/              log broker
/srv/activemq/kahadb/           KahaDB persistence
/srv/activemq/tmp/              temporary data nếu được cấu hình
/srv/activemq/archive/          journal archive nếu bật
~~~

Mảnh cấu hình Classic 5.x trong `conf/activemq.xml`:

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="orders-classic"
        persistent="true"
        schedulePeriodForDiskUsageCheck="60000">
    <persistenceAdapter>
        <kahaDB directory="/srv/activemq/kahadb"
                journalMaxFileLength="32mb"/>
    </persistenceAdapter>
</broker>
~~~

- `directory` là nơi KahaDB tạo journal/index; service account cần quyền đọc, ghi và truy cập thư mục.
- `journalMaxFileLength` điều khiển kích thước từng journal data log; không phải quota tổng và không thay `storeUsage.limit`.
- `schedulePeriodForDiskUsageCheck="60000"` yêu cầu Classic kiểm tra lại store/temp disk limits mỗi 60 giây. Tính năng periodic check có từ Classic 5.12; mặc định không chạy nếu không cấu hình.
- Không đặt `persistent="false"` trên broker có yêu cầu durability.
- Các tùy chọn như `indexDirectory`, `directoryArchive` và compaction chỉ nên tách/điều chỉnh sau khi hiểu cách backup và recovery. Không di chuyển riêng một vài file journal/index khi broker đang chạy.

### 2.2. Artemis: bindings, journal, paging và large messages

Artemis file journal thường sử dụng bốn thư mục dữ liệu:

| Thư mục | Chứa gì? | Khi nào tăng? |
|---|---|---|
| `bindings-directory` | Queue/address bindings, destination attributes, ID counters | Tạo/xóa queue, thay đổi binding |
| `journal-directory` | Message journal, ACK, transaction và record persistence | Persistent sends, ACK/commit, transaction |
| `paging-directory` | Page files khi address chuyển message ra disk | Backlog lớn hoặc paging được kích hoạt |
| `large-messages-directory` | Payload large message lưu ngoài journal | Message vượt ngưỡng large-message |

Đường dẫn mặc định thường tương đối dưới instance `data/`. Trong production cần biết volume nào đang chứa từng thư mục. Body lớn có thể nằm ngoài journal, trong khi page files lưu message theo address; vì thế chỉ giám sát journal là chưa đủ.

Mảnh cấu hình Artemis 2.x trong `ARTEMIS_INSTANCE/etc/broker.xml`:

~~~xml
<configuration xmlns="urn:activemq">
    <core xmlns="urn:activemq:core">
        <persistence-enabled>true</persistence-enabled>
        <bindings-directory>/srv/artemis/bindings</bindings-directory>
        <journal-directory>/mnt/mq-journal/journal</journal-directory>
        <paging-directory>/mnt/mq-paging/pages</paging-directory>
        <large-messages-directory>/mnt/mq-large/large-messages</large-messages-directory>
        <journal-type>NIO</journal-type>
        <journal-sync-transactional>true</journal-sync-transactional>
        <journal-sync-non-transactional>true</journal-sync-non-transactional>
        <journal-file-size>10485760</journal-file-size>
        <journal-min-files>4</journal-min-files>
    </core>
</configuration>
~~~

Đây là fragment bên trong cấu hình hiện có. Không thay nguyên file `broker.xml` hoặc tạo thêm phần tử `<core>`. Nếu đổi đường dẫn sau khi broker đã có dữ liệu, hãy dừng broker sạch và migration/restore toàn bộ data set; start với một journal directory trống có thể khiến broker nhìn như không còn queue/message cũ.

Các điểm cần nhớ:

- `journal-type=NIO` là baseline portable dùng Java NIO. Artemis cũng hỗ trợ `ASYNCIO` trên Linux khi có libaio phù hợp và `MAPPED` trong các phiên bản hỗ trợ. Nếu ASYNCIO không khả dụng, broker có thể fallback sang NIO; xem log startup để biết loại thực tế.
- `journal-sync-transactional=true` và `journal-sync-non-transactional=true` giữ flush theo các ranh giới tương ứng. Không tắt hai setting này để tăng benchmark nếu yêu cầu nghiệp vụ vẫn cần durability.
- `journal-file-size` là kích thước từng journal file, không phải giới hạn tổng dung lượng.
- `journal-min-files` điều khiển số file được tạo sẵn; tăng quá mức sẽ tiêu thụ dung lượng ngay khi khởi động.
- Mỗi Artemis node trong cluster phải có bindings/journal/paging/large-messages data riêng. Không copy journal của node này sang node khác để “tạo cluster”.

### 2.3. Khi dùng JDBC persistence

Nếu Classic hoặc Artemis dùng JDBC store, message data nằm trong database thay vì local file journal. Vận hành storage cần tính thêm data tables, indexes, large-message/BLOB tables, transaction log/WAL/redo log, temporary space, vacuum/compaction, quyền DB user, backup/PITR, connection pool, lock waits và replication lag.

JDBC không xóa nhu cầu storage local: broker vẫn có log, cấu hình, temporary files và các thành phần phụ trợ. “Broker host còn đĩa” không đồng nghĩa “database message store còn đủ dung lượng”.
## 3. Bố trí volume và yêu cầu I/O

### 3.1. Tách các workload có đặc tính khác nhau

Journal là đường ghi quan trọng, thường có nhiều append/flush. Paging và large-message có thể tạo luồng đọc/ghi lớn; log hệ điều hành và log ứng dụng có thể tăng đột biến. Nếu tất cả cùng volume, chúng tranh IOPS và băng thông.

Một bố trí tham khảo:

~~~text
/etc/activemq/              cấu hình, read-only với broker
/var/log/activemq/          log và log rotation
/mnt/mq-journal/            journal/KahaDB persistence
/mnt/mq-paging/             Artemis paging
/mnt/mq-large/              large-message payload
/mnt/mq-backup/             backup export nếu phù hợp
~~~

Với Artemis, tài liệu khuyến nghị đặt message journal trên physical volume riêng để giảm tranh chấp I/O; large-message directory cũng nên tách khỏi journal hoặc paging khi tải large message đáng kể. Tách volume chỉ hữu ích khi chúng thực sự là storage performance domain độc lập. Nhiều mount trên cùng một disk vật lý không tự tạo thêm IOPS.

Với Classic KahaDB, volume riêng cho store giúp giới hạn dung lượng và tách khỏi log/temp. Nếu dùng archive, tránh để archive tăng không giới hạn trên cùng volume live journal.

### 3.2. Chất lượng thiết bị và filesystem

Đường persistence nên có độ trễ ghi bền vững thấp và ổn định, IOPS/throughput phù hợp send/ACK/compaction/paging, write cache có bảo vệ mất điện hoặc được cấu hình theo khuyến nghị nhà cung cấp, filesystem/driver hỗ trợ locking/fsync/recovery, đủ block space và inode, cùng giám sát device errors, latency, queue depth, filesystem read-only và mount state.

SSD/NVMe hoặc block storage hiệu năng cao thường phù hợp journal hơn volume chậm với workload ngẫu nhiên. Nhưng tên loại thiết bị không bảo đảm durability; cần kiểm tra write cache, flush semantics, provisioned IOPS và giới hạn cloud volume.

**Không đặt journal vào thư mục tạm, container writable layer hoặc filesystem bị xóa khi pod/container thay thế.** Persistent volume phải mount đúng vào mọi data directory và tồn tại qua vòng đời process.

### 3.3. Network filesystem và shared storage

Network filesystem không tự động an toàn cho mọi journal. Shared-store HA có thể yêu cầu filesystem và locking semantics được hỗ trợ cụ thể; đó là thiết kế riêng với fencing/lock, không phải lý do để mount cùng journal vào nhiều broker độc lập.

Nếu dùng SAN/NFS/cloud file service, thử trên đúng storage class và mount options: hai process tranh file lock có tạo đúng một owner không; lock có được giải phóng khi host crash/mất mạng không; fsync/flush có bảo đảm dữ liệu commit được ghi bền vững không; broker dừng/fence thế nào khi storage mất kết nối; snapshot/restore có tạo tập journal/index nhất quán không.

Không dùng NFS/SMB/object storage như “thư mục chung” cho journal nếu tài liệu phiên bản và nhà cung cấp không xác nhận semantics phù hợp.

## 4. Ước lượng dung lượng theo backlog và outage

### 4.1. Công thức ban đầu

~~~text
backlogBytes ≈ max(0, ingressRate - ackDrainRate)
               × outageSeconds
               × avgStoredBytesPerMessage
~~~

Trong đó ingressRate là số message persistent broker nhận mỗi giây; ackDrainRate là số message được xử lý/ACK và giải phóng persistence mỗi giây; outageSeconds là thời gian consumer/downstream ngừng xử lý; avgStoredBytesPerMessage là dung lượng trung bình đo trong store cho một message, gồm body/header/metadata overhead chứ không chỉ kích thước JSON.

Nếu toàn bộ consumer ngừng, ackDrainRate bằng 0. Nếu chỉ một nhóm consumer chậm, tính backlog theo destination và retention cần thiết.

Cộng thêm:

~~~text
requiredCapacity =
    steadyStateStore
  + outageBacklog
  + DLQAndExpiredRetention
  + largeMessageAndPaging
  + journalCompactionOrRecoveryHeadroom
  + logsAndTemporaryData
  + operationalReserve
~~~

Không dùng một tỷ lệ overhead duy nhất cho mọi broker. Đo dung lượng thực tế trước/sau một lô message đại diện, theo dõi journal/page/large-message directories và xác nhận sau ACK/compaction.

### 4.2. Ví dụ outage một giờ

Giả sử ingress 2.000 message/giây, consumer ngừng hoàn toàn trong một giờ, dung lượng lưu trữ đo được trung bình là 4 KiB/message:

~~~text
2.000 × 4.096 bytes = 8.192.000 bytes/s
8.192.000 × 3.600 s = 29.491.200.000 bytes
                           ≈ 27,47 GiB
~~~

Đây là estimate ban đầu. Nếu cộng 35% headroom cho metadata/index, journal cleanup/compaction và dao động kích thước:

~~~text
27,47 GiB × 1,35 ≈ 37,08 GiB
~~~

Cần cộng thêm steady-state backlog, DLQ, large messages, paging, logs/temp và phần reserve không được phép sử dụng. Vì vậy không kết luận volume 40 GiB là đủ chỉ từ phép tính này. Payload nặng, durable topic subscriptions chậm hoặc DLQ retention dài có thể làm dung lượng tăng đáng kể.

### 4.3. Các thành phần thường bị bỏ quên

Message chưa ACK/in-flight; durable topic subscription chậm; DLQ/expiry queues; large messages; Artemis page files; journal files pre-created; index/bindings; transaction/ACK records; compaction headroom; temporary/scheduled messages; broker/audit logs; crash/heap dumps; filesystem metadata/inodes; reserved blocks/quota; backup/snapshot nếu đặt cùng filesystem với live store.

**Queue depth không phải phép đo dung lượng chính xác.** Cùng 100.000 message nhưng 1 KiB/message và 1 MiB/message tạo yêu cầu storage rất khác nhau.
## 5. Quyền filesystem: broker ghi bằng service account

### 5.1. Tách quyền cấu hình và quyền dữ liệu

Một triển khai Linux điển hình dùng user riêng, ví dụ `activemq`:

| Đường dẫn | Owner/group gợi ý | Quyền gợi ý | Mục đích |
|---|---|---:|---|
| `/etc/activemq/` | `root:activemq` | Directory 0750, file 0640 | Broker đọc cấu hình, operator quản lý |
| `/srv/activemq/kahadb/` | `activemq:activemq` | Directory 0750 | Broker ghi KahaDB |
| `/var/log/activemq/` | `activemq:activemq` | Directory 0750 | Broker ghi log |
| `/mnt/mq-journal/` | `artemis:artemis` | Directory 0750 | Artemis journal |
| `/mnt/mq-paging/` | `artemis:artemis` | Directory 0750 | Artemis paging |
| `/mnt/mq-large/` | `artemis:artemis` | Directory 0750 | Artemis large messages |

Chỉ broker process và nhóm quản trị được cấp quyền cần thiết lên persistence data. User chạy broker không cần quyền root. Broker cần read/write trên file dữ liệu và read/write/execute trên thư mục để tạo, đổi tên, xóa và duyệt file. Mọi thư mục cha trên đường dẫn phải có execute permission. File cấu hình thường không cần broker ghi; để root/operator quản lý giúp giảm nguy cơ broker/plugin sửa config ngoài ý muốn.

Không dùng `chmod -R 777` cho data directory để chữa lỗi permission.

### 5.2. Tạo thư mục và cấp quyền

~~~bash
sudo install -d -o activemq -g activemq -m 0750 /srv/activemq/kahadb
sudo -u activemq test -r /srv/activemq/kahadb
sudo -u activemq test -w /srv/activemq/kahadb
sudo -u activemq test -x /srv/activemq/kahadb
~~~

Tạo các thư mục Artemis:

~~~bash
sudo install -d -o artemis -g artemis -m 0750 /srv/artemis/bindings
sudo install -d -o artemis -g artemis -m 0750 /mnt/mq-journal/journal
sudo install -d -o artemis -g artemis -m 0750 /mnt/mq-paging/pages
sudo install -d -o artemis -g artemis -m 0750 /mnt/mq-large/large-messages
~~~

Nếu broker đã có dữ liệu, dừng broker sạch trước khi thay ownership trên cây dữ liệu. Chỉ chạy `chown -R` trên đúng data directory đã xác minh; không đổi owner cả thư mục cài đặt, binary, script quản trị hoặc file cấu hình một cách tùy tiện.

Kiểm tra quyền thư mục cha:

~~~bash
namei -l /mnt/mq-journal/journal
stat -c '%U:%G %a %n' /mnt/mq-journal/journal
sudo -u artemis test -r /mnt/mq-journal/journal
sudo -u artemis test -w /mnt/mq-journal/journal
sudo -u artemis test -x /mnt/mq-journal/journal
~~~

Quyền ghi trên thư mục không bảo đảm mọi file con hiện có đều writable. Kiểm tra owner/mode của file cũ và mount read-only nếu broker vẫn báo permission denied.

### 5.3. umask và systemd

Nếu broker chạy bằng systemd, service unit cần chỉ định đúng user/group và umask. Ví dụ drop-in tham khảo:

~~~ini
[Service]
User=artemis
Group=artemis
UMask=0027
ReadWritePaths=/srv/artemis /mnt/mq-journal /mnt/mq-paging /mnt/mq-large
~~~

- `User`/`Group` bảo đảm broker không chạy bằng root.
- `UMask=0027` thường tạo file không cho người ngoài group truy cập; quyền thực tế còn phụ thuộc mode ứng dụng yêu cầu.
- `ReadWritePaths` chỉ cần khi unit dùng systemd sandbox như `ProtectSystem=...`; không phải cấu hình bắt buộc cho mọi service.
- Nếu dùng `StateDirectory=` hoặc cơ chế quản lý directory của systemd, hiểu rõ đường dẫn được tạo và owner mà systemd gán.

Sau khi thay drop-in, operator cần reload systemd và restart broker theo change procedure. Không sửa unit vendor file nếu hệ thống dùng drop-in override.

### 5.4. SELinux và AppArmor

Một thư mục có Unix mode đúng vẫn có thể bị SELinux/AppArmor từ chối. Khi log báo permission denied:

- Kiểm tra audit log/AVC hoặc kernel log để xác định policy block.
- Xác minh label của mount/path và policy dành cho service.
- Dùng quy trình policy của distribution để gán label đúng; sau đó kiểm tra lại bằng service account.
- Không tắt SELinux/AppArmor toàn hệ thống hoặc chuyển sang permissive chỉ để broker khởi động.

~~~bash
sudo ausearch -m AVC -ts recent
sudo journalctl -k --since "15 minutes ago"
~~~

`restorecon` chỉ khôi phục label đã được policy định nghĩa; nếu custom path chưa có file-context rule, cần tạo rule theo policy đúng của distribution thay vì đoán type.

### 5.5. Container/Kubernetes

Khi chạy broker trong container:

- Mount persistent volume vào **tất cả data directories**; không chỉ mount journal mà quên paging/large messages.
- `runAsUser`/`runAsGroup` phải khớp owner hoặc group của volume.
- `fsGroup` có thể hỗ trợ group access tùy CSI driver/filesystem; không giả định driver nào cũng đổi ownership đệ quy.
- Nếu cần init container chuẩn bị quyền, chỉ thay quyền trên volume của broker; tránh chạy broker chính bằng root.
- Broker data không nên rơi vào ephemeral storage nếu cần tồn tại qua pod replacement.
- Pod reschedule không được tạo broker mới trỏ vào volume của node khác với journal cũ chưa detach/fence.

Ví dụ security context:

~~~yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
~~~

UID/GID là giá trị ví dụ; phải khớp image và storage class triển khai.

## 6. Quyền filesystem khác với quyền JMS/broker

| Lớp | Kiểm soát gì? | Ví dụ |
|---|---|---|
| **OS filesystem permission** | Process nào có thể đọc/ghi/xóa journal, page files, logs | User `artemis` được ghi `/mnt/mq-journal` |
| **Broker authentication/authorization** | JMS client nào được connect/send/consume/create destination | Role `orders-producer` chỉ send vào address orders |

Một JMS user được phép consume queue **không** cần quyền đọc file journal trực tiếp. Ngược lại, user OS có quyền đọc persistence files có thể đọc dữ liệu nhạy cảm ngoài cơ chế JMS authorization.

Không cấp quyền filesystem của broker data cho application developers/client runtime. Bảo vệ backup/snapshot vì chúng chứa message body, properties và metadata. Dùng encryption-at-rest ở tầng volume/database/backup nếu cần; TLS bảo vệ đường truyền nhưng không tự mã hóa journal trên disk. Không dùng chung OS account giữa broker và ứng dụng producer/consumer.
## 7. Giới hạn dung lượng và phản ứng khi disk gần đầy

### 7.1. Classic: storeUsage, tempUsage và producer flow control

~~~xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="orders-classic"
        persistent="true"
        schedulePeriodForDiskUsageCheck="60000">

    <persistenceAdapter>
        <kahaDB directory="/srv/activemq/kahadb"/>
    </persistenceAdapter>

    <systemUsage>
        <systemUsage>
            <memoryUsage>
                <memoryUsage limit="512 mb"/>
            </memoryUsage>
            <storeUsage>
                <storeUsage limit="80 gb"/>
            </storeUsage>
            <tempUsage>
                <tempUsage limit="20 gb"/>
            </tempUsage>
        </systemUsage>
    </systemUsage>
</broker>
~~~

- `memoryUsage` kiểm soát bộ nhớ broker dành cho message cursors/cache.
- `storeUsage` giới hạn dung lượng persistence store trước khi flow control làm chậm/block producer.
- `tempUsage` giới hạn vùng temporary store.

`80 gb` và `20 gb` là ví dụ; phải nhỏ hơn dung lượng volume thực sự dành cho broker và chừa headroom cho metadata, log, recovery/compaction cùng process khác. Nếu KahaDB nằm trên volume 100 GiB nhưng storeUsage cho phép 100 GiB, broker có thể hết filesystem trước khi policy bảo vệ có hiệu lực.

Classic producer flow control thường làm producer `send()` chờ khi usage chạm ngưỡng và có thể tiếp tục khi consumer giải phóng storage. Đây là **backpressure**, không phải tự động xóa message. Không tắt producer flow control để broker ghi cho tới khi volume hết sạch.

Từ Classic 5.12, `schedulePeriodForDiskUsageCheck` cho phép broker kiểm tra lại giới hạn store/temp theo dung lượng còn trống. Điều này hữu ích nếu log hoặc process khác cùng filesystem tăng dung lượng sau khi broker khởi động.

### 7.2. Artemis: global disk guard

Mảnh cấu hình trong `<core>`:

~~~xml
<max-disk-usage>85</max-disk-usage>
<min-disk-free>20GB</min-disk-free>
<disk-scan-period>5000</disk-scan-period>
<disk-full-policy>BLOCK</disk-full-policy>
~~~

- `max-disk-usage` là ngưỡng phần trăm disk đã dùng.
- `min-disk-free` là ngưỡng dung lượng còn trống tuyệt đối.
- Nếu cả hai được đặt, `min-disk-free` ưu tiên/override `max-disk-usage` theo tài liệu Artemis.
- `disk-scan-period` là khoảng kiểm tra disk.
- `disk-full-policy` xác định phản ứng khi chạm ngưỡng: `BLOCK`, `FAIL` hoặc `DROP` theo phiên bản. Mặc định thông dụng là BLOCK.

Với protocol không hỗ trợ flow control theo cách broker cần, client có thể nhận exception hoặc bị ngắt kết nối khi disk guard kích hoạt. Producer phải xử lý lỗi/timeout và backpressure; không retry vô hạn không giới hạn tốc độ.

### 7.3. Address full policy khác disk full policy

~~~xml
<address-settings>
    <address-setting match="orders.#">
        <max-size-bytes>536870912</max-size-bytes>
        <page-size-bytes>10485760</page-size-bytes>
        <address-full-policy>PAGE</address-full-policy>
    </address-setting>
</address-settings>
~~~

- `max-size-bytes` là ngưỡng memory/address size cho address match.
- `address-full-policy=PAGE` yêu cầu broker page message ra disk khi address vượt ngưỡng.
- `BLOCK` chặn producer theo flow control; `FAIL` trả lỗi; `DROP` loại message theo policy.
- PAGE chuyển áp lực từ memory sang disk, không làm message biến mất và không tạo thêm dung lượng volume.

Artemis từ 2.28 hỗ trợ giới hạn lượng paging bằng `page-limit-bytes` hoặc `page-limit-messages` cùng `page-full-policy`:

~~~xml
<address-setting match="orders.#">
    <max-size-bytes>536870912</max-size-bytes>
    <page-size-bytes>10485760</page-size-bytes>
    <page-limit-bytes>21474836480</page-limit-bytes>
    <page-full-policy>FAIL</page-full-policy>
    <address-full-policy>PAGE</address-full-policy>
</address-setting>
~~~

`page-limit-bytes` phải ít nhất bằng `page-size-bytes`; giới hạn paging không thay global disk guard. Chọn `FAIL` khi producer phải biết message không thể được lưu thêm; `DROP` có thể loại message mà producer không nhận được exception trong một số page-limit paths, vì vậy không dùng DROP cho command/event bắt buộc nếu không có business-level audit.

### 7.4. Chọn policy theo contract

| Policy | Hành vi | Phù hợp khi |
|---|---|---|
| **BLOCK** | Làm chậm/chặn producer để đợi dung lượng | Ưu tiên giữ message, producer có timeout/backpressure |
| **FAIL** | Từ chối thao tác gửi khi đạt giới hạn | Producer cần nhận lỗi tường minh và xử lý retry/outbox |
| **DROP** | Bỏ message theo policy | Chỉ với dữ liệu có thể mất và đã được nghiệp vụ cho phép |
| **PAGE** | Ghi message ra paging store khi address memory vượt ngưỡng | Backlog lớn cần giữ message và volume còn đủ capacity |

Artemis `PAGE` thuộc `address-full-policy`; `disk-full-policy` là guard toàn disk và có tập giá trị riêng. Đọc đúng tầng config trước khi quyết định.

## 8. Yêu cầu I/O và durability: không tối ưu bằng cách bỏ flush

Artemis file journal là append-oriented. Khi transaction commit hoặc message/ACK được ghi, broker có thể phải flush dữ liệu theo setting và protocol. Các setting `journal-sync-transactional=true` và `journal-sync-non-transactional=true` mặc định phản ánh yêu cầu durability.

ActiveMQ Classic KahaDB cũng có journal disk-sync behavior. Một số option cũ như `enableJournalDiskSyncs` đã deprecated ở các phiên bản Classic mới; dùng tài liệu đúng version để hiểu setting thay thế.

**Không đặt sync=false chỉ để benchmark nhanh hơn** khi workload yêu cầu message đã commit phải tồn tại sau mất điện. Nếu giảm durability, đó là thay đổi hợp đồng dữ liệu và RPO, cần phê duyệt nghiệp vụ và kiểm thử crash/power-loss tương ứng.

| Artemis journal type | Điều kiện | Ghi chú |
|---|---|---|
| `NIO` | Java NIO, portable | Baseline tốt để kiểm tra cấu hình |
| `ASYNCIO` | Linux và libaio phù hợp | Có thể giảm overhead I/O; thiếu dependency có thể fallback NIO |
| `MAPPED` | Java memory-mapped file, tùy version | Cần benchmark/kiểm tra OS và workload |

Large-message volume cần dung lượng cho payload đang chờ ACK; paging volume cần dung lượng cho backlog trong outage/consumer lag; journal volume cần headroom cho append, reclaim/compaction và recovery. Một durable topic subscriber chậm có thể giữ reference khiến page files chưa được giải phóng dù subscriber khác đã xử lý xong.
## 9. Kiểm tra quyền, mount và capacity

### 9.1. Xác minh mount trước khi start broker

Ví dụ với KahaDB:

~~~bash
findmnt -T /srv/activemq/kahadb
df -hT /srv/activemq/kahadb
df -i /srv/activemq/kahadb
namei -l /srv/activemq/kahadb
stat -c '%U:%G %a %n' /srv/activemq/kahadb
sudo -u activemq test -r /srv/activemq/kahadb
sudo -u activemq test -w /srv/activemq/kahadb
sudo -u activemq test -x /srv/activemq/kahadb
~~~

Với Artemis, kiểm tra riêng journal, paging và large-message:

~~~bash
findmnt -T /mnt/mq-journal/journal
findmnt -T /mnt/mq-paging/pages
findmnt -T /mnt/mq-large/large-messages
df -hT /mnt/mq-journal/journal
df -hT /mnt/mq-paging/pages
df -hT /mnt/mq-large/large-messages
df -i /mnt/mq-journal/journal
df -i /mnt/mq-paging/pages
df -i /mnt/mq-large/large-messages
~~~

`df -h` cho biết block space; `df -i` cho biết inode. Broker có thể báo lỗi tạo file dù còn nhiều GiB nếu filesystem hết inode hoặc quota. `findmnt` giúp phát hiện mount bị thiếu và path đang rơi vào root filesystem ngoài dự kiến.

### 9.2. Kiểm tra broker có dùng đúng volume

1. Đối chiếu đường dẫn tuyệt đối trong XML với mount thực tế.
2. Xác minh systemd/container chạy bằng UID/GID nào.
3. Kiểm tra log startup cho biết broker mở đúng journal/store directory.
4. Kiểm tra file mới nhất trong data directory có owner/mode đúng.
5. Trong lab, gửi persistent message, commit, restart broker sạch và xác nhận message còn tồn tại.
6. Nếu mount không có, broker không được âm thầm ghi vào directory local khác trên root filesystem. Thiết kế startup dependency/volume check để fail fast khi mount bắt buộc bị thiếu.

Có thể dùng `lsof` để tìm file đã bị unlink nhưng process vẫn mở:

~~~bash
sudo lsof +L1
~~~

Nếu log/journal file bị xóa khi process vẫn giữ file descriptor, `df` có thể cho thấy disk chưa được giải phóng dù `du` không còn thấy file. Khởi động lại service theo runbook để đóng descriptor; không xóa thêm file đang mở.

### 9.3. Đo I/O

Theo dõi p50/p95/p99 write/fsync latency của journal; IOPS, throughput, queue depth; paging read/write throughput; broker commit latency; send blocking time; queue oldest age; disk free/inode free và growth rate.

`iostat -xz 1` hỗ trợ quan sát Linux block devices. Nếu cần chạy fio, dùng volume thử nghiệm riêng và cấu hình đúng workload; không chạy bài ghi ngẫu nhiên/destructive lên live KahaDB/journal.

## 10. Backup, restore và migration data directory

Journal có quan hệ giữa file journal, index/bindings, page files và large-message files. Copy riêng một thư mục khi broker đang hoạt động có thể tạo backup không nhất quán.

Quy trình cơ bản:

1. Ghi nhận broker version, đường dẫn data, cấu hình persistence và volume mapping.
2. Chọn cơ chế backup/snapshot được hỗ trợ cho phiên bản và storage.
3. Nếu file-level copy không có snapshot nhất quán, **dừng broker sạch** trước khi copy.
4. Backup toàn bộ tập dữ liệu cần thiết: KahaDB store hoặc Artemis bindings/journal/paging/large-messages theo cấu hình.
5. Giữ owner, mode, ACL/SELinux labels và encryption keys cần thiết.
6. Khôi phục vào instance có broker/version compatibility; bảo đảm service account có quyền.
7. Start, kiểm tra queue/durable subscriptions/message counts, consume tập test và đối chiếu business event IDs.

Không copy data directory của Artemis node A sang node B để “clone node” trong cluster. Cần quy trình tạo node mới và replication/HA phù hợp; journal chứa identity và trạng thái riêng.

Backup không thay DLQ/expiry/retention. Nếu queue giữ backlog quá lâu, volume vẫn có thể đầy trước backup schedule. Purge DLQ để giải phóng disk có thể xóa bằng chứng và dữ liệu cần replay; cần runbook nghiệp vụ phê duyệt ai được replay/purge và cách ghi audit.

Khi đổi volume, dừng producer/consumer hoặc chuyển traffic theo maintenance plan; dừng broker sạch; đồng bộ đầy đủ data set và quyền/owner; cập nhật XML/systemd/container mount; kiểm tra mount; start, kiểm tra recovery; gửi/nhận test message persistent; chỉ mở traffic đầy đủ sau khi xác minh. Không khởi động broker đồng thời trên cả đường dẫn cũ và mới với cùng một bộ dữ liệu.

## 11. Triệu chứng thường gặp và hướng điều tra

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| Broker start lỗi `Permission denied` | Owner/mode/ACL/SELinux sai | `namei -l`, `stat`, service UID, audit logs |
| `No space left on device` dù `df -h` còn trống | Hết inode, quota, reserved blocks hoặc mount khác | `df -i`, quota, `findmnt`, log filesystem |
| Artemis báo disk full và producer bị block | `max-disk-usage`/`min-disk-free` chạm ngưỡng | Broker disk scan, volume free, disk-full-policy |
| Classic producer send block lâu | `storeUsage`/`tempUsage` chạm limit và flow control hoạt động | JMX SystemUsage, store/temp usage, consumer drain |
| Queue depth thấp nhưng disk vẫn tăng | Large messages, paging, DLQ, durable subscriber hoặc log | Kiểm tra từng data directory và subscription |
| Broker restart mà queue trống | Sai path/volume, persistence tắt, data không được mount | XML effective path, startup logs, `findmnt` |
| Journal open/read/write error | Filesystem read-only, I/O error, disk/controller issue | Kernel logs, `iostat`, mount state |
| Artemis paging không giảm | Consumer chậm, queue refs còn, durable subscriber giữ page | Queue/address counts, subscription backlog |
| Disk `df` không giảm sau khi xóa file log | Process còn giữ deleted file descriptor | `lsof +L1`, restart service theo runbook |
| Permission đúng nhưng broker vẫn bị từ chối | SELinux/AppArmor policy | AVC/kernel audit log |
| Khôi phục snapshot nhưng broker không start | Snapshot không nhất quán hoặc thiếu thư mục đi kèm | Restore toàn bộ data set, version và owner |
| Chỉ một node trong cluster có dữ liệu lạ | Data directory bị copy/chia sẻ sai | Kiểm tra unique journal/node identity và HA config |

### 11.1. Disk gần đầy: phản ứng theo thứ tự

1. **Ngăn tăng thêm:** kiểm tra producer flow control, disk-full policy và traffic; nếu cần rate-limit producer theo runbook.
2. **Xác định mount đầy:** journal, paging, large-message, KahaDB, temp hay logs.
3. **Tìm nguồn tăng:** backlog/consumer lag, DLQ, large messages, page files, log rotation, backup cùng volume.
4. **Giải phóng có kiểm soát:** chỉ xử lý dữ liệu đã được nghiệp vụ cho phép; không xóa journal/index/page files thủ công.
5. **Khôi phục headroom:** mở rộng volume hoặc giảm ingress/khôi phục consumers; xác nhận broker resume đúng.
6. **Điều tra nguyên nhân:** capacity forecast, alert thresholds, retention, flow control và disk growth rate.

**Không xóa trực tiếp file trong KahaDB journal hoặc Artemis journal/paging để lấy chỗ trống.** Những file đó có thể chứa message chưa ACK, index/transaction state hoặc page data còn được tham chiếu. Thao tác thủ công có thể làm broker mất message hoặc không khởi động được.
## 12. Thực hành lab: cấp quyền, chạm ngưỡng và phục hồi

### 12.1. Chuẩn bị lab Classic

Dùng instance thử riêng, service account `activemq` và volume thử có thể xóa. Tạo directory:

~~~bash
sudo install -d -o activemq -g activemq -m 0750 /srv/activemq-lab/kahadb
sudo -u activemq test -r /srv/activemq-lab/kahadb
sudo -u activemq test -w /srv/activemq-lab/kahadb
sudo -u activemq test -x /srv/activemq-lab/kahadb
~~~

Trong `activemq.xml` của lab, đặt KahaDB directory vào path trên và storeUsage nhỏ:

~~~xml
<persistenceAdapter>
    <kahaDB directory="/srv/activemq-lab/kahadb"/>
</persistenceAdapter>

<systemUsage>
    <systemUsage>
        <storeUsage>
            <storeUsage limit="256 mb"/>
        </storeUsage>
        <tempUsage>
            <tempUsage limit="128 mb"/>
        </tempUsage>
    </systemUsage>
</systemUsage>
~~~

Chỉ chạy trên queue lab. Gửi persistent messages có body kích thước đã biết, không chạy tới khi filesystem thật hết dung lượng. Quan sát producer bị chậm/block khi storeUsage chạm ngưỡng; sau khi consumer ACK và store reclaim, quan sát producer tiếp tục. Đừng dùng DROP hoặc tắt flow control để hoàn thành test nhanh.

### 12.2. Chuẩn bị lab Artemis

Tạo bốn thư mục riêng, cấp owner cho user broker:

~~~bash
sudo install -d -o artemis -g artemis -m 0750 /srv/artemis-lab/bindings
sudo install -d -o artemis -g artemis -m 0750 /srv/artemis-lab/journal
sudo install -d -o artemis -g artemis -m 0750 /srv/artemis-lab/paging
sudo install -d -o artemis -g artemis -m 0750 /srv/artemis-lab/large-messages
~~~

Đặt các đường dẫn trong `broker.xml` của instance lab; cấu hình disk guard:

~~~xml
<max-disk-usage>80</max-disk-usage>
<min-disk-free>2GB</min-disk-free>
<disk-scan-period>5000</disk-scan-period>
<disk-full-policy>BLOCK</disk-full-policy>
~~~

Trong `address-settings` cho queue lab, cấu hình PAGE khi address memory đầy. Tạo tải có kiểm soát, dừng consumer và theo dõi page directory tăng; start consumer lại để kiểm tra page files được reclaim khi message đã ACK. Thử ngưỡng disk nhỏ trên **volume test** để quan sát producer bị block; không cố tình lấp đầy root/system volume.

### 12.3. Tiêu chí PASS của lab

- Broker chạy bằng service account riêng, không phải root.
- Process có quyền read/write/execute đúng data directories; config directory không writable bởi broker nếu không cần.
- Classic KahaDB hoặc Artemis journal được tạo đúng mount/path.
- Message persistent đã commit vẫn còn sau restart sạch.
- Khi chạm giới hạn store/address/disk, broker phản ứng đúng policy; producer không được âm thầm coi send là thành công nếu broker đã FAIL.
- Sau khi consumer ACK/drain backlog, usage giảm theo cơ chế reclaim/compaction; không xóa file persistence thủ công.
- Backup/restore lab thành công trên data directory độc lập.
- Metrics cảnh báo trước khi hết disk và có headroom cho outage dự kiến.

## 13. Checklist vận hành production

### Volume và capacity

- [ ] Mỗi broker có danh sách tuyệt đối các data directories và mount tương ứng.
- [ ] Journal/store dùng volume có latency/fsync/IOPS đã benchmark.
- [ ] Paging, large-message, temp, log và backup được tính vào capacity plan.
- [ ] Có dự báo backlog theo ingress, ACK drain rate và thời gian outage.
- [ ] Có headroom cho compaction/recovery, DLQ, durable subscriptions và disk reserve.
- [ ] Theo dõi cả block space lẫn inode/quota.

### Quyền truy cập

- [ ] Broker chạy bằng non-root service account.
- [ ] Owner/group/mode đúng trên data dirs và mọi parent directories.
- [ ] Config được operator quản lý, broker chỉ đọc nếu không cần ghi.
- [ ] umask/systemd/container UID/GID được xác minh.
- [ ] SELinux/AppArmor policy đúng, không bị tắt để né lỗi.
- [ ] OS filesystem permission được tách khỏi JMS role/authorization.
- [ ] Backup và volume encryption được bảo vệ như dữ liệu message.

### Durability và recovery

- [ ] Persistence bật; journal sync không bị tắt trái với yêu cầu RPO.
- [ ] Disk guard/producer flow control có policy rõ ràng.
- [ ] Artemis address paging policy không bị nhầm với global disk policy.
- [ ] Không xóa journal/page/index file thủ công khi broker đang chạy.
- [ ] Backup nhất quán và restore drill được thực hiện định kỳ.
- [ ] Với HA/cluster, mỗi node có đúng storage topology và fencing; không chia sẻ/copy data directories tùy tiện.
- [ ] Có runbook cho disk full, read-only filesystem, I/O error và permission denied.

## 14. Câu hỏi tự kiểm tra

1. Tại sao `journal-directory` và `paging-directory` cần được theo dõi riêng?
2. Vì sao KahaDB directory và hai thư mục cùng tên trên hai local disks không phải shared store?
3. Broker process cần quyền nào trên thư mục dữ liệu để tạo và xóa file?
4. `df -h` còn dung lượng nhưng broker không tạo được file; cần kiểm tra gì tiếp?
5. `storeUsage.limit` của Classic có tương đương `max-disk-usage` của Artemis không? **Không**: một cái là broker store usage/flow control, một cái là disk-level threshold.
6. Artemis `address-full-policy=PAGE` có nghĩa dữ liệu không còn tiêu thụ disk không? **Không**, message được page ra disk.
7. Nếu cả `max-disk-usage` và `min-disk-free` được cấu hình, setting nào ưu tiên? **min-disk-free**.
8. Vì sao không nên tắt `journal-sync-transactional` chỉ để tăng throughput?
9. Vì sao backup bằng cách copy một vài file journal trong lúc broker đang chạy có thể không nhất quán?
10. Vì sao một JMS role có quyền consume không nên được cấp OS read permission trên persistence directories?
11. Một durable subscription chậm có thể làm paging files tồn tại dù các subscriber khác đã xử lý xong không? **Có**, message references chưa được giải phóng hết.
12. Tại sao không được copy nguyên thư mục `journal` từ node Artemis này sang node khác để tạo cluster node mới?

**Định hướng trả lời:** (1) journal và page có workload/retention khác; (2) không có cùng backing storage/lock; (3) read/write/execute; (4) inode/quota/mount/ACL/SELinux; (5) khác tầng giới hạn; (6) PAGE chuyển memory pressure thành disk use; (7) min-disk-free; (8) thay durability/RPO; (9) thiếu consistency giữa journal/index/bindings/pages; (10) OS permission bypasses broker authorization; (11) có; (12) journal chứa identity và state riêng của node.

## 15. Tài liệu chính thức

- [ActiveMQ Classic — KahaDB](https://activemq.apache.org/components/classic/documentation/kahadb): KahaDB directory, journal/index, archive và compaction.
- [ActiveMQ Classic — Producer Flow Control](https://activemq.apache.org/components/classic/documentation/producer-flow-control): `systemUsage`, `storeUsage`, `tempUsage` và backpressure.
- [ActiveMQ Classic — Periodically Checking Disk Limits](https://activemq.apache.org/components/classic/documentation/periodically-checking-disk-limits): `schedulePeriodForDiskUsageCheck` từ 5.12.
- [ActiveMQ Classic — XML Configuration](https://activemq.apache.org/components/classic/documentation/xml-configuration): XBean broker config và persistence adapter.
- [Apache ActiveMQ Artemis 2.57 — Persistence](https://artemis.apache.org/components/artemis/documentation/latest/persistence): journal files, journal type, sync và dung lượng file.
- [Apache ActiveMQ Artemis — Paging](https://artemis.apache.org/components/artemis/documentation/latest/paging): page files, disk usage, min-disk-free, max-disk-usage và page limits.
- [Apache ActiveMQ Artemis — Large Messages](https://artemis.apache.org/components/artemis/documentation/latest/large-messages): large-message directory, sync và tách volume.
- [Apache ActiveMQ Artemis — Configuration Reference](https://artemis.apache.org/components/artemis/documentation/latest/configuration-index.html): bindings/journal/paging/large-message paths, disk settings và defaults.
- [Apache ActiveMQ Artemis — Clusters](https://artemis.apache.org/components/artemis/documentation/latest/clusters.html): dữ liệu journal/bindings/paging/large-messages riêng của từng node.

**Kết luận:** Storage của broker phải được thiết kế như một phần của durability contract. Xác định đúng **đường dẫn persistence, volume, I/O, dung lượng và owner**; giữ journal sync theo yêu cầu; tách rõ **Classic storeUsage** với **Artemis disk guard/address paging policy**; cấp quyền cho service account tối thiểu; và kiểm chứng backup/restore bằng dữ liệu thực. Khi volume đầy hoặc permission sai, backpressure và cảnh báo phải xuất hiện trước khi broker mất khả năng ghi an toàn.
