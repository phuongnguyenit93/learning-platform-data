# Broker phục hồi chậm, journal không thu hồi hoặc paging tăng kéo dài

> **Chương:** Chẩn đoán sự cố  
> **Phạm vi:** Phân tích sự cố lưu trữ và phục hồi của Apache ActiveMQ Artemis và ActiveMQ Classic. Bài tập trung vào ba biểu hiện thường đi cùng nhau: broker khởi động/recovery lâu, dung lượng journal không giảm sau khi consumer đã xử lý message, và dữ liệu paging/store tiếp tục tăng. Mục tiêu là xác định dữ liệu nào còn được broker tham chiếu, vì sao producer tạo backlog nhanh hơn consumer giải phóng, và cách khôi phục an toàn mà không làm mất message.

## 1. Nhận diện đúng triệu chứng trước khi thay cấu hình

Ba biểu hiện sau có thể có chung nguyên nhân là backlog hoặc I/O chậm, nhưng chúng không đồng nghĩa:

| Triệu chứng | Dấu hiệu quan sát | Câu hỏi đầu tiên |
|---|---|---|
| **Recovery chậm** | Broker mất nhiều phút/giờ để mở transport và nhận kết nối sau restart | Thời gian nằm ở journal replay, index rebuild, load destination, filesystem hay JVM? |
| **Journal không thu hồi** | File journal vẫn chiếm dung lượng dù enqueue/dequeue có vẻ cân bằng | Có message/reference/transaction nào vẫn còn sống hoặc file chưa đủ điều kiện reclaim không? |
| **Paging/store tăng kéo dài** | Paging directory, KahaDB store hoặc temp store tăng liên tục | Producer rate có vượt consumer rate, consumer có bị block, hay broker không ghi/đọc disk đủ nhanh? |

Đừng kết luận broker bị rò rỉ disk chỉ vì thư mục journal vẫn còn nhiều file. Journal là log append-only có record sống và record đã hết hiệu lực; broker có thể giữ file để tái sử dụng. Ngược lại, queue depth thấp không chứng minh storage đã rỗng: durable topic subscription, scheduled delivery, message đang in-flight, DLQ, prepared transaction hoặc large message vẫn có thể giữ dữ liệu.

Trước khi can thiệp, ghi lại:

- Broker product/version, node/role hiện tại, thời điểm restart và thời gian từng giai đoạn startup trong log.
- Filesystem, mount, dung lượng trống, inode, latency/IOPS, tốc độ đọc ghi và dung lượng từng thư mục storage.
- Producer/consumer rate, queue/address depth, in-flight/delivering, scheduled, DLQ, durable subscription và transaction đang mở.
- Thay đổi gần nhất: deploy producer/consumer, TTL, retry, selector, persistence adapter, disk, JVM, broker configuration hoặc HA failover.

## 2. Phân biệt các vùng lưu trữ

### 2.1. ActiveMQ Artemis

Với instance mặc định, các vùng dữ liệu thường nằm dưới `$ARTEMIS_INSTANCE/data`; đường dẫn có thể được thay bằng cấu hình instance:

| Thư mục | Vai trò | Vì sao còn dữ liệu? |
|---|---|---|
| `data/journal` | Journal lưu binding/message/ack/transaction records | Message persistent chưa được acknowledge, transaction chưa hoàn tất, hoặc file còn record sống |
| `data/paging` | Page files của address khi vượt ngưỡng paging | Producer tiếp tục gửi nhanh hơn consumer xử lý; message chưa được consume/ack/expire |
| `data/large-messages` | Payload lớn được lưu tách khỏi journal | Message lớn hoặc reference của nó còn tồn tại |
| `data/bindings` | Binding, queue/address metadata | Destination/subscription vẫn tồn tại |

Journal và paging giải quyết hai việc khác nhau. Journal ghi nhận trạng thái bền vững của message và thao tác broker. Paging chuyển message của address sang page files khi address đạt ngưỡng cấu hình. Xóa bớt page files không tự làm journal compact; compact journal cũng không làm mất backlog đang được page.

### 2.2. ActiveMQ Classic với KahaDB

Classic thường dùng KahaDB persistence adapter. Trong thư mục KahaDB:

- `db-*.log` là các journal log segment; một segment có thể chứa record còn sống và record đã obsolete.
- `db.data` là index để tìm record trong journal; nó không phải bản sao đầy đủ của mọi message.
- `db.redo` và các file phụ trợ phục vụ ghi/recovery tùy phiên bản/cấu hình.
- Nếu bật `archiveDataLogs`, segment đã đủ điều kiện cleanup có thể được chuyển vào archive directory; dung lượng archive tăng là hành vi được cấu hình, không nhất thiết là cleanup failure.

Classic không dùng `data/paging` theo cơ chế Artemis. Áp lực dung lượng ở Classic thường thể hiện qua KahaDB `StorePercentUsage`, `TempPercentUsage`, cursor của queue/topic, memory usage và producer flow control. Không dùng runbook Artemis paging để xóa file KahaDB.

## 3. Chẩn đoán Artemis: recovery và journal compaction

### 3.1. Xác định broker đã recovery xong hay đang kẹt ở một giai đoạn

Đọc log từ thời điểm process khởi động, tìm các mốc theo thứ tự:

1. Load cấu hình, security realm, acceptor/connector và storage directories.
2. Mở journal, đọc/replay record và khôi phục transaction/message references.
3. Load bindings, address, queue và durable subscription.
4. Khôi phục paging/large message state.
5. Start acceptor và báo broker sẵn sàng.

Tên log message thay đổi theo phiên bản; dùng timestamp và khoảng cách giữa các mốc, không phụ thuộc một chuỗi log cố định. Nếu thời gian chủ yếu nằm trước khi acceptor start, kiểm tra journal recovery, filesystem latency và số file/record. Nếu broker đã mở port nhưng ứng dụng vẫn không consume, kiểm tra queue/address state, consumer registration, security và paging pressure.

Thu thập song song:

```bash
# Linux: filesystem capacity và inode
df -h
df -i

# Dung lượng từng vùng dữ liệu; chạy trên đúng instance path
du -sh "$ARTEMIS_INSTANCE/data/journal"
du -sh "$ARTEMIS_INSTANCE/data/paging"
du -sh "$ARTEMIS_INSTANCE/data/large-messages"
du -sh "$ARTEMIS_INSTANCE/data/bindings"

# Latency/queue depth của thiết bị block (nếu sysstat có sẵn)
iostat -xz 1
```

Đo nhiều mẫu trong thời gian đủ dài; một lần `du` không cho biết tốc độ tăng. Kiểm tra cả filesystem chứa journal và filesystem chứa paging/large messages vì chúng có thể nằm trên mount khác nhau. `df -i` phát hiện hết inode dù dung lượng byte còn trống.

Nếu broker process đang sống nhưng phản hồi chậm, thu thập JVM thread dump và GC log trước khi restart:

```bash
jcmd <broker-pid> Thread.print
jcmd <broker-pid> GC.heap_info
```

Tìm thread bị block ở file I/O, lock contention, transaction/session dài, GC pause hoặc management call chờ. Không kết luận disk chậm chỉ từ CPU thấp; cần đối chiếu `await`, `util`, queue depth thiết bị và latency filesystem.

### 3.2. Vì sao journal chưa thu hồi?

Journal file chỉ đủ điều kiện tái sử dụng/cleanup khi các record trong file không còn được trạng thái broker tham chiếu. Các nguyên nhân phổ biến:

- Message persistent vẫn ready, scheduled hoặc đang delivering/in-flight; consumer chưa ACK/commit.
- Message đã vào DLQ nhưng chưa được xử lý/purge theo retention đã phê duyệt. DLQ vẫn là message đang được lưu.
- Durable subscription của topic còn backlog dù subscriber hiện tại không hoạt động.
- Transaction đang mở hoặc prepared transaction chưa commit/rollback; broker phải giữ record để đảm bảo recovery.
- Large message còn reference từ message/queue; file trong `large-messages` không được giải phóng chỉ vì queue nguồn đã giảm.
- Ack/transaction records chưa làm cho toàn bộ journal file trở thành obsolete; file có thể còn một số record sống dù đa số record đã hết hiệu lực.

Kiểm tra từng lớp:

1. QueueControl: `MessageCount`, `DeliveringCount`, `ScheduledCount`, `ConsumerCount`, `MessagesAdded`, `MessagesAcknowledged`, `MessagesExpired`.
2. AddressControl: address size, số page, số byte/page và message count theo khả năng của version.
3. Transaction: transaction đang active/prepared, thời gian mở và owner/client.
4. DLQ/expiry queues: oldest message age, source address/queue metadata và tốc độ tăng.
5. Durable subscriptions: subscription queue depth, consumer online/offline và selector.

Không dùng một chỉ số `MessageCount` đơn lẻ để kết luận toàn bộ storage đã giải phóng. Ví dụ, queue ready count bằng 0 nhưng `DeliveringCount` còn cao hoặc transaction chưa commit thì dữ liệu vẫn có thể cần cho recovery.

### 3.3. Compaction không phải lệnh xóa journal ngay lập tức

Artemis quản lý journal file theo cơ chế append, đánh dấu record obsolete và compact khi điều kiện phù hợp. Các tham số liên quan trong khối `<core>` của `broker.xml` gồm:

```xml
<core>
    <!-- Các thuộc tính journal cần được benchmark theo workload -->
    <journal-file-size>10M</journal-file-size>
    <journal-min-files>2</journal-min-files>
    <journal-compact-min-files>10</journal-compact-min-files>
    <journal-compact-percentage>30</journal-compact-percentage>
</core>
```

Đây là ví dụ minh họa các thuộc tính; không thay các giá trị production trước khi đo journal write rate, file count, compaction I/O và thời gian recovery. Ý nghĩa vận hành:

- `journal-file-size`: kích thước journal file; đổi kích thước có thể làm thay đổi số file và thời gian scan/recovery.
- `journal-min-files`: số file tối thiểu broker giữ lại để tái sử dụng; vì vậy journal không nhất thiết co về 0 byte sau khi drain.
- `journal-compact-min-files`: ngưỡng số file liên quan tới lúc xem xét compaction.
- `journal-compact-percentage`: ngưỡng tỷ lệ record live/obsolete dùng trong quyết định compaction.

Compaction tiêu thụ disk I/O và có thể cạnh tranh với traffic đang chạy. Nếu record còn sống do backlog, durable subscription hoặc transaction, tăng tần suất compact không giải quyết nguyên nhân. Không chỉnh ngưỡng thấp chỉ để ép disk usage giảm; có thể làm compaction chạy thường xuyên, tăng latency và khiến recovery/throughput tệ hơn.

### 3.4. Đo paging theo address, không chỉ nhìn tổng thư mục

Một address Artemis có thể cấu hình như sau:

```xml
<address-settings>
    <address-setting match="orders.#">
        <max-size-bytes>104857600</max-size-bytes>
        <page-size-bytes>10485760</page-size-bytes>
        <address-full-policy>PAGE</address-full-policy>
    </address-setting>
</address-settings>
```

Đây là ví dụ ngưỡng 100 MiB và page 10 MiB để minh họa; phải chọn theo memory budget, disk budget, message size và throughput thực tế. Với `address-full-policy`:

| Policy | Hành vi khi address đạt ngưỡng | Rủi ro cần theo dõi |
|---|---|---|
| `PAGE` | Page message xuống disk và tiếp tục nhận theo khả năng disk | Paging tăng tới khi consumer bắt kịp hoặc filesystem cạn |
| `BLOCK` | Broker back-pressure producer | Send latency/timeouts lan ngược về ứng dụng |
| `FAIL` | Từ chối send khi address đầy | Producer phải xử lý lỗi rõ ràng |
| `DROP` | Loại message theo policy | Có thể mất dữ liệu nghiệp vụ; chỉ dùng khi semantics cho phép |

Nếu paging tăng đều, lấy snapshot theo từng address và so sánh:

- Producer `MessagesAdded` delta và consumer `MessagesAcknowledged` delta trong cùng cửa sổ.
- `MessageCount`, `DeliveringCount`, `ScheduledCount`, consumer count và oldest message age.
- Số page/bytes theo address và dung lượng filesystem paging.
- Consumer processing latency, downstream timeout, retry/redelivery và selector mismatch.

Nếu `MessagesAdded` cao hơn ACK lâu dài, paging tăng là hệ quả của throughput imbalance. Nếu producer rate thấp nhưng paging không giảm, kiểm tra consumer không match selector, queue không có consumer, scheduled messages, transaction, consumer stuck hoặc disk read latency.

**Paging giảm chậm không nhất thiết là lỗi cleanup.** Broker cần đọc page, dispatch, chờ ACK/commit và cập nhật journal. Một page có thể chỉ được giải phóng khi các message/reference trong page đã được xử lý theo semantics của broker.

## 4. Chẩn đoán ActiveMQ Classic: KahaDB cleanup và usage limits

### 4.1. Vì sao KahaDB giữ db-*.log?

KahaDB ghi message/transaction records vào journal log. Index db.data trỏ tới các record cần thiết. Cleanup chỉ có thể xóa hoặc archive một log segment khi broker xác định không còn record sống nào trong segment đó cần cho queue, durable subscription hoặc transaction recovery.

Những nguyên nhân hay gặp:

- Persistent message còn trong queue, DLQ hoặc durable topic subscription.
- Consumer đã nhận message nhưng chưa ACK/commit; message vẫn in-flight.
- Transaction chưa hoàn tất hoặc broker phải giữ state để recover.
- Expired message chưa được xử lý theo expiry policy; DLQ chứa message đã hết retry vẫn là dữ liệu persistent.
- archiveDataLogs=true khiến segment đã cleanup được chuyển vào archive, nên tổng dung lượng thư mục cha có thể không giảm.
- db.data index rebuild hoặc journal replay kéo dài sau shutdown không sạch, disk chậm hoặc số segment lớn.

Không xóa db-*.log bằng tay và không xóa db.data để “ép rebuild” khi chưa có backup và runbook đúng phiên bản. Một segment trông cũ theo timestamp vẫn có thể chứa record live. Index rebuild có thể kéo dài và không khắc phục nguyên nhân nếu journal còn backlog.

### 4.2. Kiểm tra cấu hình KahaDB

Ví dụ fragment trong activemq.xml:

```xml
<persistenceAdapter>
    <kahaDB
        directory="$ACTIVEMQ_DATA/kahadb"
        journalMaxFileLength="32mb"
        cleanupInterval="30000"
        archiveDataLogs="false"/>
</persistenceAdapter>
```

Các thuộc tính:

- directory: nơi lưu KahaDB journal/index. Xác nhận path thực tế từ process và filesystem; không giả định nó nằm trên cùng mount với broker log.
- journalMaxFileLength: kích thước segment tối đa. Segment lớn hơn giảm số file nhưng có thể tăng lượng dữ liệu phải scan/recover; segment nhỏ hơn tăng số file và metadata operations.
- cleanupInterval: chu kỳ kiểm tra cleanup theo đơn vị cấu hình của phiên bản Classic đang dùng. Thay chu kỳ không thể giải phóng segment còn record live.
- archiveDataLogs: nếu bật, segment được archive thay vì xóa. Kiểm tra archiveDirectory và chính sách retention archive nếu cấu hình này đang dùng.

Không thay journalMaxFileLength trong lúc broker đang chạy rồi kỳ vọng segment cũ được chuyển đổi ngay. Tham số này chủ yếu ảnh hưởng segment được tạo về sau; benchmark với kích thước message, write rate và recovery time đại diện.

### 4.3. Phân biệt Store, Temp và Memory usage

Classic công bố usage qua BrokerView/JMX. Các chỉ số cần đọc cùng nhau:

| Chỉ số | Ý nghĩa | Khi tăng tới giới hạn |
|---|---|---|
| StorePercentUsage | Persistent store usage (thường KahaDB) | Producer persistent có thể bị flow control/block hoặc send fail theo cấu hình |
| TempPercentUsage | Temporary store dùng cho dữ liệu tạm/cursor | Có thể làm producer/dispatch bị chặn dù KahaDB persistent chưa đầy |
| MemoryPercentUsage | Broker memory usage | Cursor có thể spill ra store/temp; producer flow control hoặc dispatch latency tăng |
| Queue QueueSize | Message còn trong queue theo semantics MBean | Backlog tăng nếu enqueue vượt dequeue |
| Queue InFlightCount | Message đã dispatch nhưng chưa ACK | Consumer chậm, transaction kéo dài hoặc client mất kết nối |

Ví dụ cấu hình giới hạn toàn broker:

```xml
<systemUsage>
    <systemUsage>
        <memoryUsage>
            <memoryUsage percentOfJvmHeap="60"/>
        </memoryUsage>
        <storeUsage>
            <storeUsage limit="100 gb"/>
        </storeUsage>
        <tempUsage>
            <tempUsage limit="30 gb"/>
        </tempUsage>
    </systemUsage>
</systemUsage>
```

Các limit trên chỉ là số minh họa. Không đặt store/temp limit cao hơn dung lượng filesystem có thể cấp phát thực tế; phải chừa chỗ cho log, index, archive, journal growth, OS và hoạt động recovery. memoryUsage cũng cần chừa heap cho connection, dispatch, management và application broker internals.

Để quan sát cursor theo destination, kiểm tra policy entry và cursor policy. Ví dụ:

```xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue=">"
                         producerFlowControl="true"
                         memoryLimit="20mb"
                         cursorMemoryHighWaterMark="70"/>
        </policyEntries>
    </policyMap>
</destinationPolicy>
```

cursorMemoryHighWaterMark là ngưỡng phần trăm memory trước khi cursor chuyển nhiều dữ liệu hơn sang storage theo cơ chế destination. memoryLimit ở policy entry là ngân sách memory của destination; nó không thay thế systemUsage toàn broker. Chỉ chỉnh sau khi xác định queue nào tạo backlog và cursor nào đang spill.

### 4.4. Đọc dấu hiệu flow control

Khi Store/Temp/Memory usage tiến gần limit, Classic có thể làm producer chậm lại theo producer flow control. Đây là back-pressure có chủ đích để broker không ghi vượt sức chứa. Dấu hiệu:

- Producer send latency tăng hoặc send block.
- Log broker báo usage limit/producer flow control.
- StorePercentUsage hoặc TempPercentUsage gần 100%.
- Enqueue rate giảm đột ngột dù upstream vẫn có request.
- Consumer dequeue không tăng đủ để giải phóng store.

Nếu flow control bị tắt hoặc giới hạn đặt không hợp lý, broker có thể tiến tới filesystem exhaustion. Không tắt producerFlowControl để “hết block”; trước tiên xác định consumer throughput, disk capacity và lý do cursor/store không được giải phóng.

## 5. Runbook phân loại: backlog, journal retention hay disk I/O

### 5.1. Chụp snapshot theo cửa sổ thời gian

Lấy ít nhất hai snapshot cách nhau vài phút, cùng timezone và cùng broker node:

| Nhóm | Snapshot cần lưu | Cách đọc |
|---|---|---|
| Storage | Byte/file count của journal, paging, large-message, KahaDB, temp và archive | Tính tốc độ tăng/giảm, xác định đúng mount |
| Queue | Ready/message count, delivering/in-flight, scheduled, enqueue/dequeue/ACK delta | Phân biệt backlog chưa nhận và message đang xử lý |
| Consumer | Consumer count, processing p95/p99, error, rollback, reconnect | Tìm consumer chậm, selector không match hoặc downstream lỗi |
| Transaction | Active/prepared transaction, age, owner/client | Transaction dài có thể giữ record và message reference |
| Disk | IOPS, await, utilization, free bytes, inode, filesystem errors | Phân biệt throughput imbalance với storage bottleneck |
| JVM | Heap, GC pause, thread dump, CPU | Phân biệt broker bị GC/lock với I/O wait |

Không lấy enqueueCount - dequeueCount từ lúc broker start làm backlog nếu MBean counter có thể reset sau restart. Dùng delta trong cùng một uptime window và đối chiếu queue depth hiện tại.

### 5.2. Ma trận nguyên nhân và hướng xác minh

| Dấu hiệu | Khả năng cao | Xác minh tiếp |
|---|---|---|
| Paging tăng, MessagesAdded > ACK liên tục | Producer nhanh hơn consumer | Đo rate theo address, scale/khôi phục consumer, kiểm tra downstream |
| Paging đứng cao, queue có message nhưng consumer count = 0 | Consumer không kết nối hoặc không có quyền | Client logs, auth/ACL, connector, deployment |
| Queue ready thấp nhưng delivering/in-flight cao | Consumer nhận nhưng xử lý/ACK chậm | Listener latency, transaction age, blocked downstream |
| Queue count gần 0, journal file vẫn còn nhưng ổn định | File pool/minimum files hoặc record live rải rác | Đọc journal policy, durable subs, transaction, large-message refs |
| Queue count thấp, journal tăng sau mỗi giờ | DLQ, scheduled, durable subscription hoặc producer khác | Liệt kê mọi address/queue/subscription, không chỉ queue chính |
| Disk await cao, broker threads chờ I/O | Storage latency/IOPS bottleneck | Volume metrics, noisy neighbor, filesystem, storage controller |
| Recovery lâu sau shutdown không sạch | Journal replay/index recovery | Startup log timing, số journal segment, disk read throughput |
| Classic StorePercentUsage cao, producer block | KahaDB store không được reclaim hoặc capacity thấp | Queue/DLQ/durable refs, transactions, disk free |
| Classic TempPercentUsage cao | Cursor/temp spill hoặc temp message accumulation | Temp directory, cursor policy, non-persistent traffic |
| Classic archive tăng, KahaDB active logs ổn định | archiveDataLogs đang giữ segment | Archive retention và backup policy |

### 5.3. Tìm destination giữ dữ liệu

Lập danh sách mọi destination, không chỉ destination có traffic lớn:

- Queue chính, retry queue, DLQ và expiry queue.
- Durable topic subscription queue, kể cả subscriber đã offline.
- Scheduled/delayed delivery.
- Queue nội bộ cho bridge, cluster redistribution hoặc application retry.
- Transaction đang prepared/in-doubt.
- Large messages và paging files tương ứng.

Một destination ít traffic nhưng giữ một message cũ trong journal segment có thể ngăn segment đó được reclaim. Đây là lý do “queue chính đã drain” không đồng nghĩa toàn bộ journal có thể cleanup.

## 6. Quy trình khôi phục an toàn

### 6.1. Trước khi restart hoặc thay storage

1. Xác định node active/backup và cơ chế HA (replication hay shared store). Chỉ một node được phép sở hữu shared journal tại một thời điểm.
2. Ghi nhận broker version, config hiện hành, JVM options, storage mount và dung lượng từng directory.
3. Thu thập logs, thread dump, GC log, JMX snapshot và queue/subscription/transaction inventory.
4. Nếu còn khả năng, giảm ingress từ producer bằng rate limit hoặc pause có kiểm soát; thông báo retry budget và timeout cho upstream.
5. Xác nhận disk còn đủ chỗ cho recovery/compaction. Nếu filesystem sắp đầy, ưu tiên mở rộng volume hoặc giải phóng log/archive đã được retention policy cho phép.
6. Backup theo hướng dẫn của đúng broker/version khi broker đã dừng sạch hoặc dùng cơ chế snapshot nhất quán. Không copy nóng từng file journal rồi coi đó là backup hợp lệ.

### 6.2. Trong khi broker đang phục hồi

- Không xóa file trong journal, paging, large-messages, bindings, kahadb hoặc temp store.
- Không chạy hai broker cùng mở một shared-store directory.
- Không tạo một instance mới trỏ vào data directory cũ để “thử khởi động”.
- Không kill process liên tục khi recovery đang tiến triển; mỗi lần shutdown không sạch có thể khiến lần sau phải replay lại.
- Theo dõi log progress, disk read, I/O wait và free space theo chu kỳ. Nếu không có tiến triển, thu thập thêm bằng chứng trước khi dừng process.

Nếu broker không thể khởi động do filesystem đầy, xử lý dung lượng theo thứ tự ít rủi ro: mở rộng filesystem, chuyển/xóa log ứng dụng đã hết retention, xử lý archive theo chính sách đã duyệt. Không xóa message store để lấy chỗ trống.

### 6.3. Sau khi broker sẵn sàng

1. Xác nhận broker role/HA ổn định, acceptor/connector hoạt động và client reconnect thành công.
2. Xác minh queue/address, durable subscription, DLQ, expiry và transaction state còn nguyên.
3. Mở ingress theo từng bước, giữ consumer concurrency phù hợp với downstream.
4. Quan sát producer add rate, consumer ACK rate, backlog age, paging/store usage và disk latency.
5. Chỉ replay DLQ sau khi sửa nguyên nhân, giữ event ID logic, rate limit và kiểm tra idempotency.
6. Theo dõi thêm ít nhất một chu kỳ tải đại diện để chắc chắn paging/store không tiếp tục tăng.

## 7. Khôi phục throughput và ngăn paging tăng trở lại

### 7.1. Tính chênh lệch producer/consumer

Trong một cửa sổ thời gian T:

\[
\text{net backlog rate} =
\frac{\Delta \text{messages added} -
\Delta \text{messages acknowledged}}{T}
\]

Nếu kết quả dương kéo dài, backlog tiếp tục tăng. Nếu bằng 0 nhưng paging không giảm, kiểm tra message age, scheduled/in-flight, page cleanup semantics và destination khác. Nếu âm, backlog đang drain; disk usage có thể giảm chậm vì broker vẫn cần giữ file pool và compaction diễn ra theo điều kiện.

Ví dụ: producer thêm 900 msg/s, consumer ACK 650 msg/s trong 20 phút. Backlog tăng xấp xỉ 250 msg/s × 1.200 giây = 300.000 message. Tăng max-size-bytes chỉ cho phép backlog chiếm nhiều memory/disk hơn; nó không sửa mất cân bằng throughput.

### 7.2. Chọn hành động theo bottleneck

| Bottleneck | Hành động |
|---|---|
| Downstream DB/API chậm | Khôi phục dependency, connection pool và timeout; tránh tăng consumer concurrency trước khi downstream chịu được |
| Consumer concurrency thấp | Tăng dần consumers sau khi đo CPU, DB pool, ordering và partition/queue semantics |
| Consumer rollback/retry nhiều | Sửa lỗi payload/dependency, backoff và DLQ; tránh retry storm |
| Selector không match | Kiểm tra property name/type/casing và subscription selector; xử lý version không hỗ trợ |
| Disk throughput thấp | Chuyển storage sang volume có IOPS/latency phù hợp, kiểm tra filesystem và noisy neighbor |
| Message lớn bất thường | Giảm payload, dùng object storage/reference pattern, rà soát large-message threshold |
| Producer burst | Rate limit, batch hợp lý, smoothing và admission control |
| Durable subscription không dùng | Xác nhận owner, drain/retention và unsubscribe theo quy trình; không xóa binding thủ công |

### 7.3. Không dùng tăng giới hạn làm biện pháp chữa mặc định

- Tăng Artemis max-size-bytes có thể đẩy thêm message vào paging và làm cạn disk muộn hơn.
- Đổi address-full-policy từ BLOCK sang PAGE có thể khiến producer không bị back-pressure nhưng paging tiếp tục phình.
- Tăng Classic storeUsage/tempUsage vượt dung lượng volume chỉ dời thời điểm filesystem đầy.
- Tắt producer flow control có thể chuyển một sự cố back-pressure thành disk exhaustion.
- Tăng journal file size hoặc giảm compaction threshold không làm record live biến mất.

Chỉ thay giới hạn sau khi có capacity model: peak ingress, peak outage duration, average/p99 message size, consumer drain rate, replication/backup overhead, disk reserve và thời gian phục hồi.

## 8. Dashboard, cảnh báo và tiêu chí ổn định

### 8.1. Theo dõi dung lượng theo vùng và tốc độ tăng

Dashboard nên có các panel riêng cho:

- Artemis: journal bytes/file count, paging bytes/pages theo address, large-message bytes, binding count, disk free/inode.
- Classic: KahaDB active log bytes/count, archive bytes, StorePercentUsage, TempPercentUsage, MemoryPercentUsage.
- Queue/address: ready count, delivering/in-flight, scheduled, enqueue/add, dequeue/ACK, oldest message age và consumer count.
- Runtime: startup/recovery duration, JVM heap/GC pause, disk read/write latency, IOPS và filesystem errors.

Không cộng metric của cả primary và backup thành một con số nếu cả hai cùng expose management metrics. Gắn node/role, xác định active owner và tính rate trên đúng broker đang phục vụ traffic.

Tên metric Prometheus phụ thuộc exporter/plugin và phiên bản broker. Chuẩn hóa mapping trong dashboard, ví dụ:

| Metric logic | Nguồn | Mục đích |
|---|---|---|
| broker_storage_bytes (area=journal) | Filesystem/exporter | Journal growth |
| broker_storage_bytes (area=paging) | Filesystem + address management | Paging growth |
| broker_address_messages_added_total | Address/queue management | Producer rate |
| broker_queue_messages_acknowledged_total | Queue management | Consumer completion rate |
| broker_queue_delivering | Queue management | In-flight backlog |
| broker_address_pages | Artemis AddressControl | Số page đang dùng |
| broker_store_percent_usage | Classic BrokerView/JMX | Persistent store pressure |
| broker_temp_percent_usage | Classic BrokerView/JMX | Temporary store pressure |

Các tên trên là **schema metric nội bộ minh họa**, không phải cam kết tên metric mặc định của Artemis/Classic exporter. Ánh xạ từ JMX/management API phải được xác minh theo broker version đang triển khai.

### 8.2. Alert theo tốc độ và thời gian kéo dài

Đặt alert theo xu hướng thay vì chỉ theo một ngưỡng snapshot:

| Alert | Điều kiện gợi ý | Mức độ |
|---|---|---|
| Disk reserve thấp | Filesystem free < 20% trong 10 phút; critical < 10% | Warning/Critical |
| Inode gần cạn | Inode free < 15% | Warning |
| Paging tăng liên tục | Paging bytes tăng 10–15 phút và ACK rate thấp hơn add rate | Warning |
| Backlog age vượt SLA | Oldest message age vượt deadline của event type | Critical theo nghiệp vụ |
| Classic store/temp pressure | Store hoặc Temp usage > 85% warning, > 95% critical | Warning/Critical |
| Recovery bất thường | Startup-to-ready vượt baseline nhiều lần liên tiếp | Warning |
| Consumer mất khả năng drain | Consumer count = 0 hoặc ACK rate = 0 trong khi backlog > 0 | Critical |
| Transaction kéo dài | Active/prepared transaction vượt ngưỡng tuổi vận hành | Warning/Critical |

Các ngưỡng 20/10/85/95% là điểm bắt đầu để hiệu chỉnh, không phải giá trị áp dụng cho mọi volume. Alert phải có thời gian duy trì và lưu lượng tối thiểu để tránh cảnh báo do burst ngắn. Khi alert paging tăng, gửi kèm address, producer/ACK rate, oldest age và filesystem còn trống để người trực có thể chọn hành động.

### 8.3. Runbook theo mức độ disk pressure

**Warning (còn nhiều disk reserve):**

1. Xác định address/queue hoặc KahaDB destination tạo tăng trưởng.
2. Kiểm tra producer/ACK rate, consumer health và downstream latency.
3. Giảm burst, khôi phục consumer hoặc xử lý selector mismatch.
4. Theo dõi paging/store slope sau thay đổi.

**Critical (disk reserve thấp hoặc I/O bắt đầu lỗi):**

1. Thực hiện incident response và thông báo owner của producer/consumer.
2. Giới hạn/pause ingress có kiểm soát; ưu tiên giữ broker còn khả năng ghi journal và ACK.
3. Mở rộng volume hoặc thêm capacity đã được phê duyệt.
4. Chỉ dọn log/archive không thuộc message store và đã hết retention.
5. Nếu cần restart, xác nhận HA ownership và backup/recovery plan trước khi thao tác.

Không purge DLQ hoặc queue nghiệp vụ để đạt chỉ tiêu disk nếu chưa có quyết định data owner. Purge có thể làm mất bằng chứng và dữ liệu cần replay; journal sẽ không được thu hồi an toàn chỉ vì thao tác purge thiếu kiểm soát.

## 9. Tình huống thực tế: paging tăng sau khi triển khai consumer mới

Một hệ thống Artemis nhận trung bình 700 msg/s. Sau khi deploy consumer phiên bản mới, dashboard ghi nhận:

| Chỉ số | Trước deploy | Sau deploy |
|---|---:|---:|
| Producer add rate | 700 msg/s | 700 msg/s |
| Consumer ACK rate | 680 msg/s | 420 msg/s |
| Consumer p99 | 180 ms | 950 ms |
| orders.# paging | 2 GiB ổn định | Tăng 4 GiB/giờ |
| Disk free | 42% | 31% và tiếp tục giảm |

Điều tra cho thấy consumer mới gọi thêm một API đồng bộ trong transaction xử lý message; API có p99 cao và timeout retry. Message vẫn được dispatch nhưng transaction commit chậm, DeliveringCount tăng và ACK rate giảm. Journal tăng do message/reference và transaction records còn sống; paging tăng vì producer tiếp tục thêm message.

Thứ tự xử lý:

1. Rate-limit producer ở mức đã thống nhất với business owner để ngăn disk tiến tới critical.
2. Khôi phục consumer về phiên bản trước hoặc bỏ call đồng bộ khỏi critical path sau khi xác nhận semantics.
3. Đưa side effect phụ sang event/async workflow có idempotency; giữ transaction DB/JMS ngắn và có timeout.
4. Mở consumer dần, quan sát p99 và ACK rate; không scale vượt connection pool/downstream capacity.
5. Khi ACK rate vượt add rate, theo dõi paging bytes giảm và backlog age về SLA.
6. Journal vẫn giữ số file pool tối thiểu sau khi drain; xác nhận usage ổn định và không xóa file thủ công.

Nếu cùng sự cố ở Classic, đọc StorePercentUsage/TempPercentUsage, QueueSize, InFlightCount, producer flow control và KahaDB log growth. Không tìm thư mục data/paging của Artemis trong Classic.

## 10. Những thao tác dễ làm sự cố nặng hơn

| Thao tác | Vì sao nguy hiểm | Thay thế |
|---|---|---|
| Xóa file journal/KahaDB khi broker dừng | Có thể xóa record còn live hoặc phá index/recovery | Backup nhất quán, xác định reference và làm theo recovery procedure đúng version |
| Xóa toàn bộ paging directory | Mất message đang được page | Drain/ACK/expire theo policy và xác minh address state |
| Xóa large-messages vì queue count thấp | Reference còn có thể tồn tại ở queue khác/transaction | Tìm message references và xử lý qua broker |
| Restart liên tục khi recovery lâu | Tạo thêm shutdown không sạch và lặp journal replay | Theo dõi progress/I/O, thu thập thread dump rồi quyết định một lần |
| Chạy active và backup cùng shared store | Corrupt/lock contention và split-brain | Xác minh ownership/fencing theo HA design |
| Tăng store/temp limit vượt disk | Chỉ trì hoãn filesystem full | Capacity planning và khôi phục consumer throughput |
| Tắt flow control | Producer có thể lấp đầy disk không giới hạn | Rate limit, back-pressure và admission control |
| Purge DLQ để giải phóng journal | Mất message cần audit/replay; không bảo đảm giải phóng ngay segment | Triage, replay/retention có owner |
| Bật archiveDataLogs mà không retention | Active KahaDB giảm nhưng archive tiếp tục phình | Theo dõi archive riêng và lifecycle backup/retention |

## 11. Checklist hoàn tất incident

- [ ] Đã xác định đúng broker product/version và storage adapter.
- [ ] Đã phân biệt journal, paging, large-message, bindings, KahaDB, temp và archive.
- [ ] Đã chụp ít nhất hai snapshot để tính tốc độ tăng/giảm.
- [ ] Đã xác định destination/subscription/transaction đang giữ message references.
- [ ] Đã so sánh producer add rate, consumer ACK rate, in-flight và oldest message age.
- [ ] Đã kiểm tra disk bytes, inode, IOPS, latency, filesystem errors và JVM GC/thread state.
- [ ] Đã xác nhận HA active owner; không có hai broker cùng dùng shared journal.
- [ ] Đã khôi phục consumer/downstream hoặc giảm ingress để backlog bắt đầu drain.
- [ ] Đã xác minh paging/store slope ổn định hoặc giảm và disk reserve đủ an toàn.
- [ ] Đã xác minh queue, DLQ, durable subscription, transaction và large-message state còn đúng.
- [ ] Đã ghi lại thay đổi cấu hình, backup, audit và kế hoạch retention/replay.

**Kết luận:** recovery chậm, journal không thu hồi và paging tăng là ba tín hiệu cần được phân tích cùng queue references, transaction state, consumer ACK rate và disk I/O. Artemis journal/paging và Classic KahaDB/cursor có cơ chế lưu trữ khác nhau, vì vậy phải dùng đúng metric và runbook cho từng broker. Giữ nguyên message store, khôi phục khả năng drain, kiểm soát ingress và xác minh storage slope sau xử lý là cách đưa broker về trạng thái ổn định mà vẫn bảo toàn dữ liệu.
