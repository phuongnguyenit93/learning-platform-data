# Memory, store, temp, paging, journal và dung lượng đĩa

> **Chương:** Giám sát  
> **Phạm vi:** Theo dõi và kiểm soát bộ nhớ, persistent store, temporary store, paging, journal và filesystem của **Apache ActiveMQ Classic** và **ActiveMQ Artemis**. Trọng tâm là quan hệ giữa các giới hạn tài nguyên, dấu hiệu bão hòa, cách đo và runbook khi broker gần hết RAM/đĩa. Các snippet là cấu hình minh họa cho lab; cần đối chiếu phiên bản broker, JVM, storage và topology trước khi áp dụng production.

## 1. Vì sao phải nhìn nhiều lớp tài nguyên?

Một broker có thể báo queue gần như trống nhưng JVM vẫn dùng nhiều heap; hoặc heap còn thấp nhưng volume chứa KahaDB sắp đầy. Một broker khác có thể vẫn nhận message nhờ **paging** dù memory pressure cao, nhưng độ trễ tăng mạnh vì đọc/ghi đĩa. Những hiện tượng này phản ánh **các lớp tài nguyên khác nhau**, không nhất thiết mâu thuẫn.

| Lớp | Câu hỏi vận hành | Dấu hiệu |
|---|---|---|
| **JVM heap** | Object Java và message metadata có chiếm quá nhiều heap? | Old-gen tăng, GC pause dài |
| **Native/direct memory và RSS** | JVM/thư viện mạng có vượt giới hạn container/máy? | RSS tăng dù heap used không cao |
| **Broker memory budget** | Broker có đạt giới hạn memory usage/địa chỉ? | Classic `MemoryPercentUsage`; Artemis global/address pressure |
| **Persistent store** | Message bền vững và metadata chiếm bao nhiêu? | Classic `StorePercentUsage`; KahaDB journal lớn |
| **Temporary store** | Dữ liệu non-persistent có phải lưu tạm khi memory/cursor áp lực? | Classic `TempPercentUsage` tăng |
| **Paging** | Artemis đã chuyển message của address sang page files? | Page count/bytes tăng, disk I/O tăng |
| **Journal** | Record bền vững, ACK và transaction được ghi/thu hồi thế nào? | Journal file count, I/O latency |
| **Filesystem** | Volume còn bao nhiêu byte/inode và I/O có đáp ứng? | Disk free thấp, write latency/error |

**Không dùng một phần trăm để đại diện tất cả.** `MemoryPercentUsage` không phải phần trăm RAM máy; `StorePercentUsage` không phải phần trăm disk free; Artemis paging không phải journal; `TempPercentUsage` Classic không phải số lượng JMS `TemporaryQueue`.

```mermaid
flowchart TB
    P["Producer / Consumer"] --> M["Broker memory budget"]
    M -->|Persistent message| S["Persistent store / journal"]
    M -->|Non-persistent overflow (Classic)| T["Temporary store"]
    M -->|Address memory threshold (Artemis)| G["Paging files"]
    S --> D["Filesystem / volume"]
    T --> D
    G --> D
    S --> J["Index, ACK, transaction metadata"]
    M --> H["JVM heap + native/direct + OS RSS"]
```

Mục tiêu giám sát là phát hiện **nguyên nhân và tốc độ cạn tài nguyên** đủ sớm để giảm ingress, tăng năng lực consumer hoặc mở rộng storage. Đừng đợi broker hết đĩa rồi mới xử lý; khi filesystem đầy, broker có thể không ghi được journal, page file, log hoặc metadata cần cho recovery.

## 2. Phân biệt các khái niệm dễ bị gọi chung là disk usage

### 2.1 Memory usage không phải heap usage

**Heap used** là bộ nhớ Java đang được object chiếm dụng. **Broker memory usage** là bộ đếm/giới hạn logic do broker quản lý cho message và cấu trúc liên quan. Broker có thể tính theo kích thước message hoặc ước lượng metadata, nên giá trị này **không nhất thiết bằng** heap used của JVM.

Ngoài heap còn có:

- **Direct/native memory:** buffer mạng, NIO/Netty và thư viện native.
- **Thread stack:** số lượng thread và stack size.
- **Metaspace/code cache:** class metadata và mã JIT.
- **OS page cache:** filesystem cache cho journal/page I/O.
- **Container memory accounting:** RSS/cgroup có thể chạm limit trước khi heap đạt `-Xmx`.

Vì vậy, broker báo memory budget 65% nhưng process RSS gần cgroup limit vẫn có nguy cơ OOMKill. Ngược lại, heap cao không tự chứng minh broker giữ quá nhiều message; cần xem GC, live set, queue/cursor và consumer progress.

### 2.2 Persistent store, temporary store và temporary destination là ba chuyện khác nhau

| Khái niệm | Classic | Artemis |
|---|---|---|
| Persistent message storage | KahaDB/JDBC hoặc persistence adapter đang dùng | Journal và các cấu trúc persistent store |
| Temporary storage khi memory/cursor bị áp lực | `tempUsage`, thường liên quan lưu tạm message non-persistent | Không có một bộ đếm `tempUsage` tương đương 1:1; theo dõi address memory/paging và lifecycle queue |
| JMS temporary destination | `TemporaryQueue`/`TemporaryTopic` có vòng đời theo connection | Temporary queue/address theo semantics và client Artemis |

**`tempUsage` trong Classic không có nghĩa là số TemporaryQueue.** Broker có thể không tạo temporary destination nào nhưng temp store vẫn tăng vì message non-persistent được lưu tạm khi cursor/memory policy cần. Ngược lại, có temporary queue không có nghĩa toàn bộ message của nó nằm trong `tempUsage`.

### 2.3 Journal, paging và large-message store không thay thế nhau

- **Journal:** ghi bền các thay đổi như enqueue, ACK, transaction và metadata broker.
- **Paging (Artemis):** lưu message của address ra page files khi memory threshold/policy kích hoạt; broker vẫn quản lý message như message đang chờ, không phải xóa message.
- **Large-message storage (Artemis):** lưu payload lớn theo cơ chế riêng khi message vượt ngưỡng large-message; không đồng nghĩa address đang paging.
- **KahaDB journal (Classic):** các segment `db-N.log` chứa record append-only; ACK làm record hết hiệu lực về logic nhưng không xóa từng byte ngay.

Một message có thể liên quan tới nhiều cấu trúc store; **đừng cộng dung lượng các thư mục như thể mỗi message chỉ nằm trong một file**. Dung lượng journal cũng không phải backlog queue chính xác.

## 3. ActiveMQ Classic: memory, store và temp usage

### 3.1 Ba Usage Manager quan trọng

Classic dùng `SystemUsage` để giới hạn tài nguyên broker. Cấu hình minh họa trong `activemq.xml`:

```xml
<!-- Snippet trong cấu hình <broker> Classic hiện hữu. -->
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
```

Các giới hạn trên chỉ là **giá trị ví dụ**, không phải sizing khuyến nghị. Chúng cần phù hợp với heap, dung lượng volume, số broker, loại message, tốc độ ingress và khả năng xử lý consumer.

| Thành phần | Giám sát điều gì? | Khi gần giới hạn |
|---|---|---|
| `memoryUsage` | Bộ nhớ logic broker dùng cho message/cursor và cấu trúc liên quan | Producer flow control có thể chặn gửi; broker chịu áp lực heap |
| `storeUsage` | Dung lượng persistent store mà broker quản lý | Persistent producer có thể bị block/reject tùy flow control và cấu hình |
| `tempUsage` | Dung lượng temporary store | Non-persistent message có thể bị block/reject khi temp usage cạn |

`limit` là **ngưỡng kiểm soát của broker**, không phải quota filesystem được hệ điều hành cưỡng chế. Ví dụ `storeUsage limit="80 gb"` không bảo đảm volume 80 GB đủ dùng: journal/index/log/backup và overhead có thể làm volume đầy sớm hơn.

### 3.2 Persistent message vẫn tiêu thụ memory

`DeliveryMode.PERSISTENT` yêu cầu broker lưu message theo persistence policy, nhưng broker vẫn cần metadata, cursor/reference và buffer để dispatch. Vì vậy:

- Persistent message có thể làm **store usage tăng** và đồng thời góp phần vào memory usage.
- Khi consumer chậm, message pending tích lũy; store tăng theo dữ liệu persistent, memory/cursor chịu áp lực tùy cursor strategy.
- ACK không đồng nghĩa journal segment được xóa tức thì; KahaDB cleanup phụ thuộc việc record trong segment không còn reference.
- Nếu producer gửi nhanh hơn consumer trong thời gian dài, chỉ tăng `storeUsage` limit sẽ **trì hoãn** lúc đầy, không khắc phục throughput gap.

### 3.3 Non-persistent message và `tempUsage`

Non-persistent message thường được giữ trong memory/cursor theo policy; khi broker cần chuyển dữ liệu ra temporary store, `tempUsage` là giới hạn cần theo dõi. Hành vi thực tế còn phụ thuộc destination cursor, policy, consumer, broker version và message size. Không giả định mọi non-persistent message đều ghi xuống temp store ngay khi send.

Hai kiểu rủi ro thường gặp:

1. **Memory cao, temp thấp:** broker còn giữ nhiều message/reference trong memory hoặc cursor chưa cần spill.
2. **Temp cao:** non-persistent message đang được giữ tạm trên disk, consumer không theo kịp hoặc temp store không được giải phóng đủ nhanh.

Non-persistent không có cùng bảo đảm sau restart như persistent. Nếu broker dừng bất thường, dữ liệu non-persistent có thể mất; **temp store không biến non-persistent thành durable**.

### 3.4 Producer flow control và destination memory limit

Classic có thể áp policy theo destination:

```xml
<!-- Ví dụ policy entry cho queue lab; ghép vào destinationPolicy hiện có. -->
<policyEntry queue="lab.monitor.>"
             producerFlowControl="true"
             memoryLimit="64 mb"/>
```

`producerFlowControl` giúp broker điều tiết producer khi resource usage vượt ngưỡng; `memoryLimit` là giới hạn memory cho destination theo policy. Trong môi trường thực, kiểm tra policy match queue và broker-wide `SystemUsage`. Không thêm entry trùng pattern vào policy map hiện hữu mà chưa hiểu cách lựa chọn policy.

Khi flow control kích hoạt, producer có thể **bị block trong send**, khiến thread ứng dụng chờ lâu. Nếu ứng dụng không đặt timeout hoặc không có backpressure ở tầng HTTP/API, thread pool upstream có thể cạn. Theo dõi:

- Thời gian `send()` và số lần send bị block/timeout.
- Queue pending/in-flight, tốc độ enqueue/dequeue.
- Memory/store/temp usage theo broker và destination.
- Thread pool/request latency ở service gửi.

Không tắt producer flow control để “hết block” nếu store/disk không có capacity; điều đó có thể biến cảnh báo sớm thành disk full hoặc OOM.

### 3.5 KahaDB journal và dung lượng disk

Với Classic dùng KahaDB, thư mục thường có file journal segment như `db-*.log` cùng index/metadata. Các thao tác persistent message/ACK/transaction được ghi theo journal; một segment chỉ đủ điều kiện thu hồi khi không còn dữ liệu cần giữ. Vì vậy:

- `StorePercentUsage` có thể giảm chậm hơn queue depth sau khi consumer drain.
- Journal file count có thể còn ổn định dù queue chính trống vì segment hiện hành, destination khác hoặc ACK/transaction/subscription còn tham chiếu.
- `du` trên thư mục KahaDB và `StorePercentUsage` không nhất thiết bằng nhau.
- Không xóa thủ công `db-N.log` hoặc index để ép broker giảm dung lượng.

Một cấu hình KahaDB tham khảo:

```xml
<!-- Chỉ dùng nếu broker đang dùng KahaDB; không áp cho Artemis. -->
<persistenceAdapter>
    <kahaDB directory="/var/lib/activemq/data/kahadb"
            journalMaxFileLength="32mb"
            checkpointInterval="5000"
            cleanupInterval="30000"/>
</persistenceAdapter>
```

`journalMaxFileLength` điều khiển kích thước mục tiêu segment mới; `checkpointInterval` và `cleanupInterval` ảnh hưởng lịch checkpoint/cleanup theo phiên bản. Chúng **không phải** công tắc giới hạn tổng dung lượng store. Khi disk tăng, tìm backlog, in-flight, durable subscription, DLQ và transaction chưa giải quyết.

## 4. ActiveMQ Artemis: global memory, address size và paging

### 4.1 Hai cấp memory pressure

Artemis có thể kiểm soát memory theo:

- **Broker-wide global max size:** giới hạn tổng memory message broker quản lý.
- **Address-level max size:** giới hạn theo address để một luồng traffic không chiếm hết tài nguyên chung.

Ví dụ đoạn trong `<core>` của `broker.xml`:

```xml
<core>
    <!-- Giới hạn tổng memory cho message của broker: ví dụ 512 MiB. -->
    <global-max-size>536870912</global-max-size>

    <address-settings>
        <address-setting match="lab.#">
            <max-size-bytes>67108864</max-size-bytes>
            <page-size-bytes>10485760</page-size-bytes>
            <address-full-policy>PAGE</address-full-policy>
        </address-setting>
    </address-settings>
</core>
```

`global-max-size` và `max-size-bytes` là ngưỡng quản lý memory/địa chỉ, **không phải** giới hạn dung lượng filesystem. `page-size-bytes` quy định kích thước page file theo cấu hình address; cần chọn phù hợp message size và storage throughput. Ví dụ trên có 64 MiB cho address và page size 10 MiB chỉ để minh họa; sizing thực tế phải benchmark.

### 4.2 Address full policy quyết định cách broker phản ứng

| `address-full-policy` | Hành vi | Phù hợp khi | Rủi ro |
|---|---|---|---|
| `PAGE` | Chuyển message sang paging store khi address đạt ngưỡng memory | Muốn tiếp tục nhận message và có disk capacity | Disk I/O tăng; backlog kéo dài có thể làm volume đầy |
| `BLOCK` | Block producer gửi vào address khi vượt ngưỡng cho tới khi có capacity | Muốn backpressure thay vì tăng backlog vô hạn | Thread producer có thể chờ; upstream pool cạn nếu timeout kém |
| `FAIL` | Từ chối thao tác gửi khi address đầy | Muốn lỗi rõ để ứng dụng retry/điều tiết | Producer phải xử lý exception và retry có kiểm soát |
| `DROP` | Bỏ message mới theo policy khi address đầy | Chỉ khi loss được chấp nhận rõ ràng | Mất message; không dùng cho luồng nghiệp vụ cần đủ dữ liệu |

**PAGE không phải “lưu vô hạn”.** Nó chuyển áp lực từ memory sang disk; nếu producer tiếp tục nhanh hơn consumer, paging store vẫn tăng tới khi disk hoặc policy khác đạt ngưỡng. **BLOCK không tự giảm backlog**; nó dừng ingress để consumer có thời gian xử lý. **FAIL** cho phép ứng dụng nhìn thấy lỗi; **DROP** có thể mất dữ liệu và cần phê duyệt nghiệp vụ riêng.

### 4.3 Paging khác journal

Artemis thường có các thư mục dữ liệu tách theo chức năng, tùy cấu hình instance:

| Thư mục | Nội dung chính | Cần theo dõi |
|---|---|---|
| `journal` | Journal records cho persistent messages, transaction và trạng thái broker | File count, kích thước, I/O latency, recovery/compaction |
| `bindings` | Metadata address/queue/binding | Số lượng destination và metadata growth |
| `paging` | Page files chứa message của address đang paging | Page count/bytes, oldest page, tốc độ depage |
| `large-messages` | Payload lớn được lưu theo cơ chế large message | File count/size và cleanup sau ACK |

Một message đang paging **vẫn là message cần xử lý**, không phải journal đã được thu hồi. Khi consumer tiến triển và broker depage, page files có thể được giải phóng sau khi không còn cần. Nếu một address có backlog lớn, số page có thể tăng dù queue count không quá lớn.

### 4.4 Large message không phải paging

Message payload lớn có thể được lưu riêng trong large-message store theo cấu hình/ngưỡng của Artemis. Khi điều tra disk growth:

- Đo riêng thư mục `large-messages` và paging.
- Kiểm tra consumer ACK/transaction và message còn tham chiếu.
- Không giả định xóa queue là file payload biến mất tức thì; broker phải hoàn tất cleanup đúng lifecycle.
- Giới hạn message size và payload ở producer/API; không dùng broker disk như kho file đính kèm không giới hạn.

### 4.5 Temporary queue trên Artemis không có `tempUsage` tương đương Classic

Artemis không dùng bộ ba Usage Manager Classic theo đúng tên/semantics. Message của temporary queue vẫn chịu ảnh hưởng memory, address policy, paging và lifecycle queue/address. Khi một ứng dụng tạo nhiều temporary reply queues:

- Theo dõi số queue/address, consumer và subscription tồn tại.
- Theo dõi address size/page count và disk.
- Đóng consumer/destination theo lifecycle và tránh leak temporary destinations.
- Phân biệt resource metadata tăng do quá nhiều queue với payload message đang paging.

Đừng map `TempPercentUsage` Classic thành một metric Artemis giả định. Dùng metric Artemis tương ứng cho address, queue, paging và filesystem.

## 5. Metric nào cần thu thập?

### 5.1 JVM và hệ điều hành

| Metric | Tại sao cần | Dấu hiệu bất thường |
|---|---|---|
| Heap used/committed/max | Theo dõi Java object và GC | Old-gen tăng liên tục sau mỗi đợt drain |
| GC pause/time/count | Xác định broker chậm vì garbage collection | Pause dài, nhiều Full GC |
| Process RSS | Tổng resident memory thực tế | Gần cgroup/host limit dù heap còn |
| Direct/native memory | Buffer mạng, allocator, native libs | Tăng không tương ứng heap |
| Thread count | Consumer, transport, scheduler, management | Thread tăng liên tục hoặc blocked nhiều |
| CPU usage/load | Xác định broker bị giới hạn CPU | CPU cao, GC hoặc journal/crypto tốn CPU |
| Disk free bytes + percent | Phát hiện volume gần đầy | Free giảm liên tục |
| Inode/file count | Phát hiện nhiều page/log nhỏ | Inode cạn dù còn byte |
| Disk latency/IOPS/queue depth | Chất lượng journal/page I/O | Latency tăng, write queue dài |
| Filesystem errors | Read-only, permission, I/O failure | Broker không ghi journal/page/log được |

Trong container, lấy memory limit và usage từ **cgroup/container runtime**, không chỉ `free -m` của host. Một JVM có `-Xmx` 4 GiB vẫn có thể bị OOMKill nếu RSS cộng native memory vượt memory limit container.

### 5.2 ActiveMQ Classic: JMX BrokerView và DestinationView

Nếu JMX được bật và bảo vệ đúng cách, BrokerView Classic thường cung cấp:

| Thuộc tính broker | Ý nghĩa |
|---|---|
| `MemoryPercentUsage` | Phần trăm memory usage manager đã dùng |
| `StorePercentUsage` | Phần trăm persistent store usage manager đã dùng |
| `TempPercentUsage` | Phần trăm temporary usage manager đã dùng |
| `CurrentConnectionsCount` | Số kết nối hiện tại |
| `TotalMessageCount` | Tổng message theo broker view; cần hiểu semantics phiên bản |

Destination/Queue MBean có các số như `QueueSize`, `EnqueueCount`, `DequeueCount` và `InFlightCount`. Đọc đồng thời:

- Broker-level memory/store/temp percent.
- Destination-level pending/in-flight/enqueue/dequeue.
- KahaDB folder size, segment count và disk free.
- Producer send latency và consumer processing/ACK rate.

`MemoryPercentUsage` **không phải heap percentage**. Nếu usage manager tăng nhưng heap ổn, xem backlog/cursor; nếu heap/RSS tăng mà usage manager không tăng, kiểm tra thread, cache, buffer, leak hoặc phần mềm ngoài broker.

JMX có thể chứa quyền quản trị và dữ liệu vận hành nhạy cảm. Chỉ expose trên management network, bật authentication/authorization/TLS phù hợp và không bind cổng JMX công khai.

### 5.3 Artemis: address/queue management và paging

Artemis cung cấp management API/JMX/console và metrics plugin tùy phiên bản. Các số thường cần theo dõi:

| Đối tượng | Metric/attribute cần xem |
|---|---|
| Broker | Global memory limit/usage, active connections, HA/disk state |
| Address | Address size, số message, số page, bytes/page |
| Queue | Message count, delivering count, consumer count, messages added/acknowledged |
| Paging | Page count/bytes, depage progress và address đang paging |
| Journal | File count/size, I/O latency, recovery/compaction events |
| Large message | Số file/bytes còn giữ, tốc độ cleanup |

Tên attribute/metric exporter thay đổi theo version và cách expose management. Khi viết dashboard, **định danh rõ nguồn metric và đơn vị** (bytes, count, percent); không dùng một metric tự đặt tên `disk_usage` cho cả address memory và filesystem.

### 5.4 Metric phải có chiều thời gian

Một snapshot `StorePercentUsage=75%` không đủ để dự báo. Hãy tính tốc độ tăng:

```text
growth_rate = (usage_now - usage_before) / elapsed_seconds
time_to_limit = (configured_limit - usage_now) / growth_rate
filesystem_time_to_full = free_bytes / positive_disk_growth_rate
```

Chỉ dùng công thức khi growth rate dương và đo trong cửa sổ đại diện; nếu traffic có chu kỳ, so sánh cùng khung giờ và dùng percentile/trend. Dự báo còn phải trừ **safety reserve** cho journal rotation, broker restart, compaction, backup và biến động traffic. Nếu growth rate bằng 0 hoặc âm, không báo “vô hạn” như cam kết.

## 6. Diễn giải dấu hiệu và mối quan hệ giữa metric

| Quan sát kết hợp | Nguyên nhân có thể | Việc kiểm tra tiếp |
|---|---|---|
| Heap cao + memory usage cao + queue pending tăng | Consumer chậm, message lớn, prefetch/in-flight nhiều | Consumer rate, handler latency, GC, queue cursor |
| Heap thấp + RSS cao | Direct/native memory, thread stack, page cache hoặc cgroup accounting | Native memory tracking, thread count, container limit |
| Classic StorePercentUsage cao + KahaDB lớn | Persistent backlog, DLQ/durable subscription, transaction/reference còn sống | Queue/topic pending, in-flight, DLQ, KahaDB growth |
| Classic TempPercentUsage cao | Non-persistent message đang dùng temporary store | Cursor policy, consumer lag, temp volume |
| Artemis address paging tăng + disk I/O cao | Producer nhanh hơn consumer, address đạt max-size-bytes | Page count/bytes, depage rate, consumer count |
| Artemis journal lớn nhưng paging thấp | Persistent records/ACK/transaction hoặc segment chưa GC | Journal cleanup/compaction, transaction, other addresses |
| Disk free giảm nhưng broker usage thấp | Log, archive, backup, snapshot hoặc volume khác chiếm disk | Đo đúng mount, folder-level usage, inode |
| Producer send latency tăng cùng usage gần limit | Flow control/BLOCK hoặc disk I/O bottleneck | Send timeout, broker logs, consumer progress |
| QueueSize giảm nhưng journal không giảm | Segment chứa record khác hoặc chưa đủ điều kiện GC | Destination khác, durable subscription, transaction |
| OOMKill khi store usage thấp | JVM/native/container memory không đủ | Heap/RSS/cgroup/GC/direct memory |

**Một biểu đồ không có context có thể dẫn đến tuning sai.** Ví dụ giảm `memoryUsage` Classic có thể làm flow control xảy ra sớm hơn nhưng không giải quyết store full; tăng `global-max-size` Artemis có thể làm paging bắt đầu muộn hơn nhưng giảm RAM dự phòng cho OS và tăng nguy cơ OOM.

### 6.1 Backlog growth quan trọng hơn một queue depth đơn lẻ

Ghi tốc độ:

```text
ingress_rate = messages_enqueued / second
egress_rate  = messages_acknowledged / second
backlog_growth = ingress_rate - egress_rate
```

Nếu `backlog_growth` dương liên tục, queue/store/page sẽ tăng. Tăng disk limit chỉ tăng thời gian trước khi hết chỗ. Cần xử lý nguyên nhân: consumer capacity, downstream DB latency, poison message/redelivery loop, message size, producer burst hoặc thiếu rate limit.

### 6.2 Dùng bytes cùng với message count

10.000 message kích thước 1 KiB khác hoàn toàn 10.000 message 1 MiB. Dashboard nên có:

- Message count và bytes/estimated address size.
- Percentile payload size, large-message count/bytes.
- Pending/in-flight và age của message cũ nhất.
- Enqueue/dequeue/ACK rate và redelivery/DLQ rate.
- Memory/store/temp/page/journal/filesystem usage.

Khi payload phình do schema hoặc attachment, message count có thể giữ nguyên trong khi disk growth tăng nhanh. Cần giới hạn body size và cân nhắc lưu file lớn ở object storage, message chỉ chứa reference đã được authorization.

## 7. Cảnh báo và ngưỡng vận hành

### 7.1 Thiết kế cảnh báo theo nhiều chiều

| Cấp | Ví dụ điều kiện | Phản ứng |
|---|---|---|
| **Info** | Usage tăng theo giờ cao điểm nhưng backlog ổn định | Ghi baseline và trend |
| **Warning** | Một usage manager/address vượt ngưỡng cảnh báo trong thời gian duy trì; disk growth dương | Kiểm consumer lag, dự báo time-to-limit |
| **Critical** | Usage gần limit, filesystem free thấp hoặc time-to-full ngắn hơn thời gian xử lý sự cố | Giảm ingress, tăng capacity/consumer có kiểm soát |
| **Emergency** | Disk read-only/full, broker write failures, OOMKill hoặc HA/store error | Kích hoạt incident runbook, bảo toàn store và tránh restart lặp |

Không có ngưỡng 70/85/95% phù hợp mọi broker. Chọn ngưỡng theo **safety reserve**, tốc độ tăng cao nhất, thời gian cấp thêm disk và thời gian consumer cần để drain. Có thể dùng percent làm một tín hiệu nhưng luôn kèm **absolute free bytes** và **time-to-exhaustion**.

### 7.2 Hysteresis và thời gian duy trì

Không cảnh báo critical chỉ vì usage nhảy qua ngưỡng trong một lần scrape. Ví dụ: warning khi vượt ngưỡng liên tục 5 phút; critical khi vượt ngưỡng cao hơn 2 phút hoặc time-to-full thấp hơn thời gian phản ứng. Khi clear alert, dùng ngưỡng thấp hơn ngưỡng kích hoạt để tránh flapping.

Ví dụ logic:

```text
WARNING:
  store_percent > warning_threshold for 5m
  OR disk_free_bytes < warning_free_bytes for 5m

CRITICAL:
  store_percent > critical_threshold for 2m
  OR filesystem_time_to_full < response_time
  OR filesystem_free_bytes < emergency_reserve
```

Các ngưỡng và khoảng thời gian cần được xác định từ workload, volume và SLA. Cảnh báo memory broker phải đi kèm heap/RSS/GC để phân biệt broker usage pressure với JVM/container pressure.

### 7.3 Dashboard theo broker, address và filesystem

**Broker overview:** heap/RSS/GC, memory/store/temp hoặc global memory, connections, send latency, disk free, journal/paging trend.

**Destination/address:** queue count, message count/bytes, in-flight/delivering, consumer count, oldest message age, page count, enqueue/dequeue/ACK.

**Storage:** mount path, journal/bindings/paging/large-message directories, free bytes/inodes, I/O latency, errors và growth rate.

Không gộp tất cả broker trong cluster thành một số trung bình. Một node hoặc address có thể sắp cạn tài nguyên trong khi trung bình toàn cluster còn thấp.

## 8. Runbook khi memory hoặc disk gần đầy

### 8.1 Bước 1 — xác định lớp tài nguyên thực sự bão hòa

Ghi lại:

1. Broker product/version, node, JVM options, container memory limit.
2. Heap used/max, GC pause, process RSS, direct/native memory nếu có.
3. Classic memory/store/temp usage hoặc Artemis global/address/page metrics.
4. Queue/address pending, in-flight/delivering, consumer count, oldest message age.
5. Filesystem mount đúng với journal, paging, temp và large-message paths; free bytes/inodes và I/O latency.
6. Broker logs, producer send latency, consumer ACK rate, DLQ và transaction state.

Không kết luận “disk full” chỉ từ store usage 100%; cũng không kết luận “heap leak” chỉ từ process RSS tăng.

### 8.2 Bước 2 — làm chậm ingress có kiểm soát

- Dùng rate limit/backpressure ở producer hoặc upstream API.
- Giảm burst, ưu tiên traffic theo business criticality nếu thiết kế cho phép.
- Với Classic, giữ producer flow control nếu store/temp đang cạn; xử lý producer block bằng timeout và upstream backpressure.
- Với Artemis `BLOCK`, bảo đảm producer có timeout và không chiếm hết thread pool; với `PAGE`, theo dõi disk tăng; với `FAIL`, retry có backoff; không dùng `DROP` nếu chưa được business chấp thuận mất message.

Không đồng thời tăng tất cả giới hạn memory/store/temp để “broker chạy tiếp”. Điều đó có thể chuyển vấn đề thành OOM hoặc filesystem full khó phục hồi hơn.

### 8.3 Bước 3 — khôi phục năng lực tiêu thụ

Kiểm tra consumer:

- Downstream DB/API có chậm hoặc timeout không?
- Có poison message gây rollback/redelivery loop?
- Consumer có bị mất kết nối hoặc thiếu concurrency?
- Prefetch quá lớn khiến nhiều message in-flight nhưng handler chưa xử lý?
- Có queue/topic/durable subscription không còn owner?
- Có DLQ hoặc expiry destination tích lũy?

Scale consumer chỉ khi downstream có capacity và xử lý idempotent. Tăng consumer trong khi DB đã quá tải có thể làm tình hình xấu hơn. Với thứ tự theo key, không tăng concurrency một cách phá vỡ ordering contract.

### 8.4 Bước 4 — xử lý storage an toàn

Nếu filesystem gần đầy:

1. Xác minh volume và folder nào chiếm disk; phân biệt journal, paging, large messages, archive, logs và backup.
2. Cấp thêm volume hoặc mở rộng filesystem theo quy trình hạ tầng nếu cần.
3. Giải phóng backlog bằng consumer/retention/DLQ workflow đã được phê duyệt.
4. Chờ broker cleanup/depage/large-message cleanup theo lifecycle.
5. Đo lại disk free và store/page metrics qua nhiều chu kỳ.

**Không xóa thủ công** KahaDB `db-N.log`, Artemis journal, paging files, bindings hoặc large-message files khi broker đang dùng chúng. Không xóa index để “rebuild nhanh”. Nếu cần di trú store, dùng quy trình dừng broker an toàn, backup nhất quán và kiểm tra restore.

### 8.5 Bước 5 — xác nhận đã phục hồi

- Usage không tiếp tục tăng mất kiểm soát.
- Producer send latency và consumer ACK rate trở lại vùng mục tiêu.
- Queue/address backlog giảm hoặc ổn định theo SLA.
- Không tăng DLQ/expired/duplicate ngoài dự kiến.
- Filesystem free/inodes có safety reserve.
- Broker không còn write error, OOM hoặc journal recovery warning.
- Nếu HA, backup/replica và node khác vẫn khỏe; không để việc chữa disk làm mất khả năng failover.

## 9. Lab Classic: tạo persistent/non-persistent backlog và quan sát usage

Lab sử dụng **ActiveMQ Classic 5.x, Java 17, Gradle 8.x và `javax.jms`**. Chạy trên broker lab riêng, với queue `lab.monitor.resources` đã được tạo hoặc cho phép auto-create. Không dùng production, không tạo backlog lớn trên volume dùng chung.

### 9.1 Cấu hình resource limits cho broker lab

Trong `activemq.xml` Classic, hợp nhất các đoạn sau với cấu hình hiện hữu:

```xml
<systemUsage>
    <systemUsage>
        <memoryUsage>
            <memoryUsage limit="64 mb"/>
        </memoryUsage>
        <storeUsage>
            <storeUsage limit="2 gb"/>
        </storeUsage>
        <tempUsage>
            <tempUsage limit="1 gb"/>
        </tempUsage>
    </systemUsage>
</systemUsage>

<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue="lab.monitor.>"
                         producerFlowControl="true"
                         memoryLimit="16 mb"/>
        </policyEntries>
    </policyMap>
</destinationPolicy>
```

Đây là **một policy map minh họa**. Nếu broker đã có `destinationPolicy`, chỉ ghép entry vào map phù hợp; không tạo phần tử trùng. Giới hạn nhỏ giúp lab quan sát pressure sớm nhưng vẫn phải bảo đảm đủ RAM/disk. Để đo `tempUsage`, cần workload non-persistent và cursor/storage behavior thực tế; vài message nhỏ có thể không làm temp store tăng.

### 9.2 Gradle project

`settings.gradle`:

```groovy
rootProject.name = 'classic-resource-probe'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.activemq:activemq-client:5.18.3'
    runtimeOnly 'org.slf4j:slf4j-simple:1.7.36'
}

application {
    mainClass = 'lab.ResourceProbe'
}
```

Dependency là mốc minh họa API, không phải xác nhận version mới nhất hoặc đã được duyệt production. Classic client này dùng `javax.jms`; không thay trực tiếp bằng Artemis Jakarta client mà không đổi dependency/import và test protocol.

### 9.3 Mã Java gửi và drain message

Tạo `src/main/java/lab/ResourceProbe.java`:

```java
package lab;

import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.JMSException;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;
import javax.jms.TextMessage;
import org.apache.activemq.ActiveMQConnectionFactory;

public final class ResourceProbe {
    private static final String QUEUE = "lab.monitor.resources";

    private ResourceProbe() { }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            usage();
            return;
        }
        String mode = args[0];
        int count = Integer.parseInt(args[1]);
        if (count < 1 || count > 2000) {
            throw new IllegalArgumentException("count must be 1..2000");
        }
        if (!"persistent".equals(mode)
                && !"nonpersistent".equals(mode)
                && !"drain".equals(mode)) {
            usage();
            return;
        }

        String url = env("BROKER_URL", "tcp://127.0.0.1:61616");
        String user = System.getenv("BROKER_USER");
        String password = System.getenv("BROKER_PASSWORD");
        ActiveMQConnectionFactory factory =
                new ActiveMQConnectionFactory(url);
        Connection connection = user == null || user.isBlank()
                ? factory.createConnection()
                : factory.createConnection(user, password);

        try {
            connection.start();
            Session session = connection.createSession(
                    true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue(QUEUE);
                if ("drain".equals(mode)) {
                    drain(session, queue, count);
                } else {
                    send(session, queue, count,
                            "persistent".equals(mode)
                            ? DeliveryMode.PERSISTENT
                            : DeliveryMode.NON_PERSISTENT);
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static void send(
            Session session, Queue queue, int count, int deliveryMode)
            throws JMSException {
        MessageProducer producer = session.createProducer(queue);
        try {
            producer.setDeliveryMode(deliveryMode);
            String body = "x".repeat(8 * 1024);
            for (int i = 1; i <= count; i++) {
                TextMessage message = session.createTextMessage(body);
                message.setIntProperty("labSequence", i);
                producer.send(message);
                if (i % 100 == 0) {
                    session.commit();
                    System.out.println("COMMITTED batch through " + i);
                }
            }
            // Commit cả batch cuối nếu count không chia hết cho 100.
            session.commit();
            System.out.println("SEND COMPLETE count=" + count
                    + " mode=" + deliveryMode);
        } finally {
            producer.close();
        }
    }

    private static void drain(Session session, Queue queue, int maxCount)
            throws JMSException {
        MessageConsumer consumer = session.createConsumer(queue);
        int received = 0;
        try {
            while (received < maxCount) {
                Message message = consumer.receive(1500);
                if (message == null) {
                    break;
                }
                session.commit();
                received++;
                if (received % 100 == 0) {
                    System.out.println("ACKED " + received);
                }
            }
            System.out.println("DRAIN COMPLETE count=" + received);
        } finally {
            consumer.close();
        }
    }

    private static String env(String key, String fallback) {
        String value = System.getenv(key);
        return value == null || value.isBlank() ? fallback : value;
    }

    private static void usage() {
        System.out.println("Usage: persistent|nonpersistent|drain <count>");
    }
}
```

Giới hạn 2.000 message × payload 8 KiB để lab không tạo backlog tùy ý. Khi chạy drain, tham số là số message tối đa được nhận. Mã commit theo batch gửi và theo từng message nhận; đây là ví dụ đo resource, không phải throughput benchmark.

### 9.4 Trình tự thử nghiệm

```bash
# Persistent backlog; không bật consumer trong lúc gửi.
gradle run --args="persistent 500"

# Quan sát Classic JMX: MemoryPercentUsage, StorePercentUsage,
# TempPercentUsage; QueueSize, InFlightCount.

# Drain một phần, rồi quan sát các metric thay đổi.
gradle run --args="drain 200"

# Sau khi queue lab trống, gửi non-persistent backlog trên queue test.
gradle run --args="nonpersistent 500"
```

**Không kỳ vọng `TempPercentUsage` chắc chắn tăng** chỉ vì gửi 500 non-persistent message. Kết quả phụ thuộc memory limit, cursor policy, tốc độ consumer và implementation. Để quan sát spill, cần lab có memory/cursor threshold đủ nhỏ, producer nhanh hơn consumer và disk theo dõi được; tuyệt đối không cố tình làm đầy volume.

Trong khi test, ghi:

| Thời điểm | QueueSize | InFlight | Memory% | Store% | Temp% | KahaDB bytes | Disk free |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | … | … | … | … | … | … | … |
| Sau persistent send | … | … | … | … | … | … | … |
| Sau drain một phần | … | … | … | … | … | … | … |
| Sau drain hết | … | … | … | … | … | … | … |
| Sau non-persistent send | … | … | … | … | … | … | … |

## 10. Lab Artemis: quan sát paging theo address

### 10.1 Cấu hình address policy

Trong `broker.xml` của Artemis lab, cấu hình address riêng:

```xml
<address-settings>
    <address-setting match="lab.monitor.#">
        <max-size-bytes>16777216</max-size-bytes>
        <page-size-bytes>1048576</page-size-bytes>
        <address-full-policy>PAGE</address-full-policy>
    </address-setting>
</address-settings>
```

Ví dụ đặt ngưỡng address 16 MiB và page size 1 MiB. Phải hợp nhất vào `<address-settings>` hiện có, kiểm address thật mà JMS destination ánh xạ tới, và bảo đảm paging directory có disk capacity. Có thể thêm `global-max-size` theo capacity broker, nhưng **không tăng tùy tiện** để trì hoãn paging mà làm JVM thiếu headroom.

### 10.2 Quan sát PAGE, BLOCK và FAIL

Trên queue lab riêng, thử lần lượt:

1. `PAGE`: không có consumer hoặc consumer chậm; theo dõi page count/bytes và disk growth.
2. `BLOCK`: đặt threshold nhỏ, chạy producer với timeout; quan sát send latency/block và xác nhận producer dừng khi broker đạt ngưỡng.
3. `FAIL`: quan sát exception ở producer khi address đầy và kiểm retry/backoff của ứng dụng.
4. `DROP`: chỉ chạy trên queue thử nghiệm với message không có giá trị; xác nhận message bị bỏ theo policy và không dùng kết quả này cho workload cần bảo toàn dữ liệu.

Sau mỗi ca, bật consumer và drain queue; quan sát depage progress, address size, paging file count và disk free. **Không chạy DROP trên queue nghiệp vụ** chỉ để kiểm tra dashboard.

### 10.3 Kết quả cần ghi

| Policy | Producer send latency | Address/page bytes | Queue count | Disk free | Kết quả nghiệp vụ |
|---|---:|---:|---:|---:|---|
| PAGE | … | … | … | … | Message được giữ, paging tăng |
| BLOCK | … | … | … | … | Producer bị backpressure |
| FAIL | … | … | … | … | Producer nhận lỗi rõ |
| DROP | … | … | … | … | Message có thể bị mất theo thiết kế |

Lab chỉ thành công nếu bạn phân biệt được **memory threshold** với **disk capacity** và giải thích được policy đã chọn ảnh hưởng producer ra sao.

## 11. Checklist vận hành và các lỗi chẩn đoán thường gặp

### 11.1 Checklist theo dõi hằng ngày

- [ ] Heap, RSS, direct/native memory, GC pause và cgroup limit.
- [ ] Classic memory/store/temp percent hoặc Artemis global/address/page metrics.
- [ ] Queue/address message count, bytes, in-flight/delivering, consumer count và oldest age.
- [ ] Enqueue/dequeue/ACK rate, redelivery, expired và DLQ.
- [ ] Journal, paging, large-message và temp directories theo đúng mount.
- [ ] Disk free bytes, percent, inode, latency và filesystem errors.
- [ ] Producer send latency/block/exception và consumer processing latency.
- [ ] Time-to-limit và growth trend, không chỉ snapshot.
- [ ] Backup/HA nodes còn đủ storage và khả năng recovery.

### 11.2 Những kết luận sai cần tránh

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “MemoryPercentUsage 80% nghĩa là JVM heap dùng 80%.” | Đây là broker usage manager, xem heap/RSS/GC riêng. |
| “StorePercentUsage 100% nghĩa volume đã đầy.” | Đây là usage theo store limit; filesystem có thể còn hoặc đã đầy vì file khác. |
| “TempUsage là số TemporaryQueue.” | Classic tempUsage là temporary storage usage, không phải destination count. |
| “Non-persistent không thể dùng disk.” | Classic có thể dùng temp store tùy cursor/memory policy. |
| “Persistent message không dùng memory.” | Broker vẫn cần metadata/cursor/buffer để quản lý và dispatch. |
| “Artemis PAGE giải quyết disk pressure.” | PAGE chuyển áp lực sang disk; backlog vẫn có thể làm đầy volume. |
| “Artemis journal và paging là một thư mục logic.” | Chúng có lifecycle và vai trò khác nhau. |
| “Queue trống thì journal phải nhỏ ngay.” | Segment còn record khác, reference, transaction hoặc cleanup chưa tới. |
| “Tăng limit luôn chữa được broker chậm.” | Tăng limit chỉ trì hoãn saturation nếu ingress vẫn vượt egress. |
| “DROP là một cách backpressure an toàn.” | DROP có thể làm mất message; chỉ dùng khi business chấp nhận. |

### 11.3 Câu hỏi tự đánh giá

1. Vì sao broker memory usage manager có thể thấp hơn hoặc cao hơn tỷ lệ heap used?
2. Khi persistent backlog tăng, những metric nào có thể tăng đồng thời trong Classic?
3. Phân biệt `storeUsage` và `tempUsage`. Tại sao non-persistent message vẫn có thể tiêu thụ disk?
4. Vì sao `StorePercentUsage` giảm chậm sau khi queue đã drain?
5. Với Artemis, `global-max-size` khác `max-size-bytes` của một address ở điểm nào?
6. Nếu address policy là `PAGE`, vì sao disk free vẫn có thể giảm liên tục?
7. Khi nào chọn `BLOCK` thay vì `PAGE`? Điều gì có thể xảy ra ở thread pool producer?
8. Vì sao `browse`/temporary queue count không đủ để đo paging bytes?
9. Một JVM bị OOMKill dù heap used mới 55%. Bạn cần xem metric nào?
10. Làm thế nào dự báo time-to-full từ growth rate và safety reserve?
11. Vì sao không xóa thủ công journal/page files khi broker đang chạy?
12. Một queue có 100.000 message 1 KiB và một queue có 100 message 1 MiB: metric nào giúp so sánh áp lực storage đúng hơn?

**Kết luận:** **Memory**, **store**, **temp**, **paging**, **journal** và **filesystem** là các lớp tài nguyên liên quan nhưng không thể dùng thay nhau. Classic cần đọc cùng `memoryUsage`, `storeUsage`, `tempUsage`, producer flow control và KahaDB journal; Artemis cần phân biệt global/address memory, `address-full-policy`, paging, journal và large-message store. Một dashboard hữu ích phải kết hợp **bytes + message count + tốc độ ingress/egress + in-flight + disk free/I/O**, có xu hướng theo thời gian và time-to-exhaustion. Khi gần đầy, giảm ingress có kiểm soát, khôi phục năng lực consumer và mở rộng storage theo runbook; **không xóa thủ công journal hoặc page files** để giải phóng dung lượng.
