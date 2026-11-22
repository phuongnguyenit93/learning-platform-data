# Resource limit, JVM heap và dung lượng dự phòng trên đĩa

> **Chương:** Vận hành  
> **Phạm vi:** Apache ActiveMQ Classic và Artemis; giới hạn tài nguyên broker, JVM heap, bộ nhớ native/direct, persistent store, paging/temp store và dung lượng trống cần thiết để broker tiếp tục nhận, lưu và giao message an toàn.  
> **Mục tiêu:** Thiết kế ngân sách RAM/disk có thể kiểm chứng; cấu hình backpressure khi queue tăng; dự báo thời gian đầy đĩa; xây cảnh báo và runbook xử lý trước khi broker bị OOM, hết dung lượng hoặc dừng ghi journal.

## 1. Khi queue tăng, broker có thể cạn RAM hoặc đĩa theo hai đường khác nhau

Một hệ thống nhận 4.000 message/giây nhưng consumer chỉ xử lý 3.000 message/giây đang tích lũy backlog. Nếu mỗi message chiếm khoảng 2 KiB trong store, phần chênh lệch 1.000 message/giây làm dữ liệu tăng gần 2 MiB/giây. Một volume còn 30 GiB headroom có thể hết chỗ sau khoảng 4,4 giờ.

Trong cùng thời gian đó, broker có thể bắt đầu paging hoặc block producer khi ngưỡng memory đạt giới hạn. Nếu chỉ theo dõi JVM heap, đội vận hành có thể bỏ lỡ việc journal/page store đang đầy. Nếu chỉ theo dõi dung lượng filesystem, đội vận hành có thể bỏ lỡ direct memory/native memory tăng tới giới hạn container.

Cần quản lý **nhiều ngân sách độc lập nhưng liên quan**:

1. **JVM heap:** object, metadata, connection/session, queue cursor và cấu trúc runtime.
2. **Broker message memory:** phần bộ nhớ broker cho phép địa chỉ/queue sử dụng trước khi paging hoặc flow control.
3. **Native/direct memory:** network buffers, direct byte buffers, thread stacks, metaspace, JIT và thư viện native.
4. **Disk store:** persistent journal, index/bindings, paging, large messages, temp data và log.
5. **Disk headroom:** khoảng trống còn lại cho backlog, journal compaction/recovery, page files, log, heap dump và thao tác vận hành.

**Giới hạn bộ nhớ của broker không phải hard limit của toàn JVM; giới hạn store không phải dung lượng đĩa có thể dùng hết.** Cấu hình phải để lại phần dự phòng cho các thành phần ngoài con số message payload.

## 2. Phân biệt các lớp bộ nhớ và lưu trữ

| Thành phần | Chứa gì | Giới hạn/quan sát |
| --- | --- | --- |
| JVM heap | Java objects, broker metadata, queue structures, client/session state | -Xmx, heap used/committed, GC |
| Broker-managed message memory | Message/body/properties đang được broker giữ trong memory working set | Artemis global-max-size/max-size-bytes; Classic memoryUsage/memoryLimit |
| Native/direct memory | Netty/direct buffers, TLS, JNI, metaspace, thread stacks | RSS, Native Memory Tracking, cgroup memory |
| OS page cache | File pages của journal, paging, KahaDB | Host/cgroup memory accounting, cache pressure |
| Persistent store | Message journal, bindings/index và transaction records | Artemis journal; Classic KahaDB; broker store usage |
| Paging/temp/large message | Nội dung được page ra disk, temporary payload hoặc large message data | Artemis paging/large-messages; Classic temp store/cursor files |
| Logs/heap dumps/snapshots | Chẩn đoán và phục hồi | Filesystem riêng hoặc quota riêng; log rotation |

### 2.1. JVM heap và broker message budget không phải cùng một số

Ví dụ Artemis có -Xmx4G. Mặc định global-max-size được tính bằng khoảng **50% giá trị -Xmx**, tức khoảng 2 GiB cho tổng message memory của các address. Có thể đặt rõ bằng global-max-size để cấu hình ổn định giữa môi trường.

global-max-size=2G **không có nghĩa** toàn bộ JVM chỉ dùng tối đa 2 GiB. Heap còn chứa object và metadata ngoài message memory; process còn cần direct/native memory và OS resources.

Tương tự, Classic memoryUsage theo dõi broker-managed memory usage để điều tiết producer. Nó không phải bộ giới hạn thay thế -Xmx, và không bao gồm mọi allocation trong JVM.

### 2.2. Heap còn trống không chứng minh direct memory còn đủ

Một broker có thể có heap tương đối thấp nhưng process RSS/cgroup memory cao do direct buffers, TLS, native memory hoặc page cache. Khi container chạm memory.max, kernel có thể OOM-kill process dù dashboard heap chưa chạm -Xmx.

Ngược lại, heap có thể cao vì cache/object allocation trong khi disk vẫn còn nhiều. Phải quan sát đồng thời:
- JVM heap used/max và GC pause.
- Process RSS và container/cgroup memory.
- Direct buffer pool, metaspace và thread count.
- Filesystem usage, inode và disk I/O latency.
- Broker message memory, store/paging usage và queue backlog.

## 3. Cơ chế backpressure: điều gì xảy ra khi đạt resource limit?

Broker cần có hành vi rõ ràng khi consumer chậm và producer tiếp tục gửi.

| Hành vi | Broker xử lý khi đạt ngưỡng | Ảnh hưởng producer | Phù hợp khi |
| --- | --- | --- | --- |
| **PAGE** | Ghi thêm message ra paging store | Producer có thể tiếp tục gửi cho đến ngưỡng disk/page limit | Chấp nhận backlog bền vững trong giới hạn disk đã dự trù |
| **BLOCK** | Không nhận thêm cho tới khi tài nguyên được giải phóng | send/flow control bị chặn hoặc client chịu backpressure | Không muốn âm thầm bỏ message; producer có thể chờ/retry có giới hạn |
| **FAIL** | Từ chối message mới | Producer nhận lỗi và phải xử lý retry/quarantine | Muốn lỗi tường minh khi vượt ngân sách |
| **DROP** | Bỏ message mới theo policy | Có thể không có lỗi cho producer | Chỉ dùng khi contract cho phép mất dữ liệu, ví dụ telemetry best-effort |

**PAGE không phải “disk vô hạn”.** Nó chuyển áp lực từ memory sang disk. Nếu consumer tiếp tục chậm, page files vẫn tăng và cần page-limit/disk guard.

**BLOCK không phải lỗi broker.** Producer bị chặn có thể là backpressure hoạt động đúng. Ứng dụng phải có timeout, deadline và metric để phân biệt broker đang flow-control với thread bị treo vì nguyên nhân khác.

**DROP có nguy cơ mất dữ liệu nghiệp vụ.** Không dùng cho payment/order/audit chỉ để giữ dashboard xanh.

## 4. Artemis: giới hạn memory toàn broker và theo từng address

Artemis có hai phạm vi cần cấu hình:

- global-max-size: tổng memory budget cho message trên toàn broker.
- max-size-bytes/max-size-messages: ngưỡng theo từng address. Khi address đạt ngưỡng, address-full-policy quyết định PAGE/BLOCK/FAIL/DROP.

Nếu chỉ đặt max-size-bytes cho từng address, tổng nhiều address vẫn có thể vượt ngân sách tổng. Nếu chỉ đặt global limit, một address backlog lớn có thể chiếm phần lớn budget chung. Production thường cần cả hai.

### 4.1. Ví dụ broker.xml cho Artemis

Đoạn dưới là fragment trong core của broker.xml, không phải file cấu hình hoàn chỉnh:

```xml
<core>
    <!-- Tổng message-memory budget cho toàn broker.
         Giá trị này độc lập với -Xmx và native/direct memory. -->
    <global-max-size>2G</global-max-size>

    <!-- Dừng nhận thêm trước khi filesystem thực sự đầy.
         Đây là tỷ lệ dung lượng disk đã sử dụng. -->
    <max-disk-usage>85</max-disk-usage>

    <address-settings>
        <address-setting match="orders.#">
            <!-- Ngưỡng memory của address orders.* -->
            <max-size-bytes>512M</max-size-bytes>
            <page-size-bytes>10M</page-size-bytes>

            <!-- Vượt memory threshold: page ra disk. -->
            <address-full-policy>PAGE</address-full-policy>

            <!-- Không cho riêng address này chiếm paging vô hạn. -->
            <page-limit-bytes>20G</page-limit-bytes>
            <page-full-policy>FAIL</page-full-policy>

            <!-- Khi disk đạt ngưỡng, backpressure producer. -->
            <disk-full-policy>BLOCK</disk-full-policy>
        </address-setting>
    </address-settings>
</core>
```

Ý nghĩa và giới hạn:

- global-max-size tính tổng message bytes theo cách broker quản lý; mặc định tài liệu Artemis mô tả khoảng 50% JVM -Xmx nếu không đặt tường minh.
- max-size-bytes áp dụng **theo address**, không phải tổng mọi address.
- address-full-policy=PAGE cho phép message tiếp tục được ghi ra paging store khi address memory đạt ngưỡng.
- page-limit-bytes giới hạn lượng dữ liệu paging cho address. Tính năng page limit có từ Artemis 2.28.0.
- page-full-policy=FAIL khiến producer nhận lỗi khi page limit bị vượt, thay vì âm thầm drop message.
- max-disk-usage=85 là ngưỡng phần trăm disk đã dùng; broker thực hiện disk monitoring và áp dụng disk-full policy.
- disk-full-policy=BLOCK yêu cầu backpressure khi disk đầy/ngưỡng disk policy bị chạm. Các lựa chọn được hỗ trợ gồm BLOCK, FAIL và DROP.

page-limit-bytes không phải quota toàn filesystem. Nhiều address, journal, large messages, log và dữ liệu ngoài broker vẫn dùng chung volume. Phải tính tổng ngân sách của tất cả thành phần.

### 4.2. max-disk-usage và min-disk-free

Artemis hỗ trợ hai cách đặt ngưỡng disk:

- max-disk-usage: phần trăm disk được sử dụng tối đa trước khi policy kích hoạt.
- min-disk-free: lượng dung lượng trống tối thiểu cần giữ.

Nếu cả hai được cấu hình, min-disk-free được ưu tiên. Ví dụ, trên volume 500 GiB, đặt min-disk-free=100GiB có nghĩa broker bắt đầu áp dụng disk policy khi free space xuống dưới 100 GiB, tương đương khoảng 400 GiB đã dùng.

Nếu dùng min-disk-free, đặt ở core theo configuration reference của phiên bản broker:

```xml
<core>
    <min-disk-free>100G</min-disk-free>
</core>
```

Đây là **một phương án thay thế** cho ngưỡng phần trăm trong ví dụ trước. Chọn một chính sách dễ giải thích với dung lượng volume thực tế; đừng sao chép cả hai mà không hiểu ưu tiên cấu hình.

### 4.3. Chọn policy theo loại message

| Destination | Ví dụ policy | Lý do |
| --- | --- | --- |
| orders.# | PAGE + page limit + FAIL khi page full | Có thể hấp thụ backlog có giới hạn, sau đó báo lỗi rõ |
| telemetry.# best-effort | Có thể DROP nếu business contract chấp nhận | Tránh telemetry làm cạn broker, nhưng phải ghi nhận số bị drop |
| commands.# cần phản hồi nhanh | BLOCK hoặc FAIL theo SLA | Backpressure sớm, không kéo dài backlog vô hạn |
| audit.# | PAGE + giới hạn disk và cảnh báo nghiêm ngặt | Không drop; cần retention, archive và quy trình xử lý khi gần đầy |

Không có một policy tối ưu cho mọi address. Chọn theo **mức độ mất dữ liệu được phép**, latency budget và khả năng producer chịu backpressure.

### 4.4. Paging vẫn cần giới hạn và giám sát

Một address có thể giữ page files trong thời gian consumer chậm. Khi consumer bắt đầu xử lý, broker đọc lại dữ liệu từ paging store; hiệu năng phụ thuộc disk read, page size, số queue/subscription và cách consumer request message.

Theo dõi:
- Address message count và size.
- Paging state/page files và page store size.
- Consumer count, delivering count và dequeue rate.
- Disk free, IOPS, read/write latency.
- Số producer bị block hoặc nhận exception.

Không kết luận broker “còn nhiều RAM nên an toàn” khi paging volume đã gần đầy.

## 5. ActiveMQ Classic: SystemUsage và Producer Flow Control

Classic dùng SystemUsage để quản lý ba nhóm tài nguyên chính:

| Cấu hình | Ý nghĩa |
| --- | --- |
| memoryUsage | Ngân sách memory broker dùng cho message, bao gồm giới hạn theo broker |
| storeUsage | Dung lượng persistent message store, ví dụ KahaDB |
| tempUsage | Dung lượng temporary store, bao gồm dữ liệu tạm/cursor theo cấu hình |

Khi usage đạt giới hạn, **Producer Flow Control** có thể làm chậm/chặn producer hoặc trả JMSException/ResourceAllocationException tùy cấu hình. Hành vi mặc định thường được hiểu nhầm là producer “treo”, trong khi nó đang đợi tài nguyên được giải phóng.

### 5.1. Ví dụ activemq.xml

Các fragment dưới đây thuộc cấu hình ActiveMQ Classic 5.x:

```xml
<broker xmlns="http://activemq.apache.org/schema/core"
        brokerName="classic-ops"
        persistent="true">

    <persistenceAdapter>
        <kahaDB directory="${activemq.data}/kahadb"/>
    </persistenceAdapter>

    <systemUsage>
        <systemUsage>
            <memoryUsage>
                <!-- 50% JVM max heap dành làm broker memory budget. -->
                <memoryUsage percentOfJvmHeap="50"/>
            </memoryUsage>
            <storeUsage>
                <!-- Persistent store limit; thấp hơn dung lượng volume thực. -->
                <storeUsage limit="70 gb"/>
            </storeUsage>
            <tempUsage>
                <!-- Ngân sách cho temporary store. -->
                <tempUsage limit="10 gb"/>
            </tempUsage>
        </systemUsage>
    </systemUsage>

    <destinationPolicy>
        <policyMap>
            <policyEntries>
                <policyEntry queue=">"
                             producerFlowControl="true"
                             memoryLimit="128 mb"
                             storeUsageHighWaterMark="85"/>
            </policyEntries>
        </policyMap>
    </destinationPolicy>
</broker>
```

Các giá trị 50%, 70 GiB, 10 GiB và 128 MiB chỉ là **ví dụ khởi điểm cho lab**, phải thay bằng ngân sách đã tính từ heap, disk và workload.

- memoryUsage percentOfJvmHeap="50" đặt broker memory budget theo tỷ lệ max heap.
- storeUsage limit="70 gb" đặt giới hạn persistent store usage. Nó không có nghĩa broker được phép chiếm hết 70 GiB nếu volume còn ít hơn.
- tempUsage limit="10 gb" tách ngân sách temporary store.
- producerFlowControl="true" bật flow control cho queue được policy match.
- memoryLimit="128 mb" đặt giới hạn memory cho mỗi destination queue theo policy.
- storeUsageHighWaterMark="85" làm producer flow-control theo ngưỡng phần trăm của storeUsage limit đối với policy này.

Nếu producerFlowControl=false, broker có thể tiếp tục ghi message vào store để tránh cạn memory nhanh, nhưng **store limit vẫn tồn tại** và producer cuối cùng vẫn có thể bị throttle khi store đầy. Tắt flow control không làm tăng dung lượng đĩa.

### 5.2. Vì sao phải nhìn đồng thời memoryUsage, storeUsage, tempUsage?

Ví dụ:
- memoryUsage 90%: consumer chậm, message working set/cursor chiếm memory.
- storeUsage 95%: persistent backlog hoặc dữ liệu KahaDB tăng gần giới hạn.
- tempUsage 20%: temporary store còn nhiều, nhưng điều đó không giúp persistent store có thêm dung lượng.

Nếu chỉ tăng memoryUsage, persistent store vẫn có thể đầy. Nếu chỉ tăng storeUsage, JVM có thể OOM trước khi chạm store limit. Ngân sách phải được đặt đồng bộ với nhau và với filesystem.

### 5.3. Phạm vi per-destination

Policy queue=">" áp dụng cho tất cả queue match pattern. Nếu có queue đặc biệt như audit hoặc telemetry, nên tạo policy riêng và kiểm tra thứ tự match theo cấu hình broker. Không để queue telemetry có memoryLimit quá lớn làm các queue nghiệp vụ thiếu ngân sách.

Classic có storeUsageHighWaterMark và producerFlowControl cho việc điều tiết. Theo dõi cả destination memory usage và broker-wide store/temp usage; một queue đơn lẻ có thể gây áp lực toàn broker.

## 6. Chọn JVM heap trong giới hạn container hoặc VM

### 6.1. Tính từ tổng RAM khả dụng, không lấy toàn bộ cho -Xmx

Ví dụ một container có memory limit 8 GiB:

| Thành phần | Ngân sách ví dụ |
| --- | ---: |
| JVM heap -Xmx | 4 GiB |
| Direct/native buffers, TLS, metaspace, JIT, thread stacks | 1,5 GiB |
| OS/page cache và agent/metrics (tùy cgroup accounting) | 1 GiB |
| Dự phòng cho spike, GC và native allocation | 1,5 GiB |
| **Tổng** | **8 GiB** |

Đây là phép phân bổ minh họa, không phải tỷ lệ bắt buộc. Đo RSS, direct buffer, cgroup usage và heap thực tế dưới tải trước khi chốt.

**Không đặt -Xmx bằng 100% container memory.** JVM cần native memory ngoài heap; broker còn cần network buffers, thread stacks và file cache cho journal/page store. Cgroup OOM-kill có thể xảy ra trước khi JVM phát sinh OutOfMemoryError: Java heap space.

### 6.2. Ví dụ JVM flags cho Java 17

Ví dụ service wrapper có thể truyền các flags sau:

```text
-Xms4g
-Xmx4g
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/var/lib/broker-diagnostics/heap
-Xlog:gc*:file=/var/log/broker/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
```

- -Xms4g -Xmx4g: heap cố định theo ngân sách 4 GiB của ví dụ, tránh heap tự tăng tới sát container limit.
- HeapDumpOnOutOfMemoryError: tạo heap dump khi JVM OOM.
- HeapDumpPath: đặt ở filesystem chẩn đoán có quota riêng, không đặt trên volume journal gần đầy.
- -Xlog:gc*: bật GC log theo cú pháp unified logging của Java 17, có rotation giới hạn file.

Không ép MaxDirectMemorySize theo một giá trị tùy ý. Chỉ đặt khi đã đo nhu cầu direct buffers và hiểu client/broker version. Nếu đặt quá thấp, lỗi direct buffer có thể xuất hiện dù heap còn trống.

### 6.3. Heap dump cũng chiếm đĩa

Heap dump có thể gần bằng dung lượng heap đang dùng và cần thêm khoảng trống khi ghi. Nếu dump nằm trên volume chứa journal:
- Disk usage tăng đột ngột đúng lúc broker đang thiếu dung lượng.
- Journal/page write có thể thất bại.
- Heap dump bị ghi dở nếu volume đầy.

Dùng volume chẩn đoán riêng, giới hạn số dump, có quy trình upload/archive và xóa theo retention. Không xóa journal/page files để lấy chỗ cho heap dump.

### 6.4. Các chỉ số JVM phải quan sát

- Heap used, committed, max và old-generation occupancy.
- GC pause p95/p99, tổng thời gian GC và allocation rate.
- Direct buffer pool usage, metaspace, thread count.
- Process RSS, container memory.current/memory.max (cgroup v2).
- OOM kill count và restart count.
- Số connection/session/consumer và queue count.

Nếu bật Native Memory Tracking, có thể dùng jcmd <pid> VM.native_memory summary; NMT cần được bật từ lúc JVM start bằng -XX:NativeMemoryTracking=summary và có overhead. Không giả định có thể bật NMT đầy đủ sau khi process đã chạy.

## 7. Tính disk headroom và thời gian tới ngưỡng đầy

### 7.1. Ước lượng theo net backlog growth

Gọi:
- λᵢ: tốc độ message vào, message/s.
- λₒ: tốc độ message được xử lý/ACK, message/s.
- S: dung lượng lưu trữ trung bình trên mỗi message, byte/message.
- G: tốc độ tăng store ròng, byte/s.

Với một loại message và kích thước trung bình ổn định:

\[
G \approx \max(0, \lambda_i-\lambda_o)\times S
\]

Nếu có nhiều loại message/kích thước khác nhau, tính tổng byte ingress trừ byte egress thay vì chỉ lấy số message.

Thời gian tới ngưỡng:

\[
T_{\text{full}} =
\frac{\text{usable disk headroom}}{\text{net disk growth rate}}
\]

Không dùng payload bytes thuần làm S nếu chưa đo overhead của journal, index, properties, page files, large-message data và store implementation.

### 7.2. Ví dụ dự báo

Giả sử:
- Ingress 4.000 message/s.
- Consumer hoàn tất 3.000 message/s.
- Dung lượng lưu trữ đo được trung bình 2 KiB/message.
- Headroom thực sự dành cho backlog là 30 GiB.

Net backlog:

\[
(4.000-3.000)\times 2.048
=2.048.000\ \text{byte/s}
\]

Tương đương khoảng 1,95 MiB/s hoặc 6,87 GiB/giờ.

\[
T_{\text{full}}\approx \frac{30}{6,87}=4,37\ \text{giờ}
\]

Đội vận hành có khoảng 4,4 giờ trong điều kiện tải và kích thước message của ví dụ. Nếu producer tăng tải hoặc consumer chậm thêm, thời gian sẽ ngắn hơn. Đây là lý do cần đo **growth rate theo thời gian**, không chỉ snapshot dung lượng hiện tại.

### 7.3. Đo storage cost thực tế trên broker

Trong một queue lab cô lập:

1. Ghi lại dung lượng filesystem trước run.
2. Gửi một số lượng message persistent có payload/property giống production.
3. Đợi producer commit và broker flush theo cấu hình.
4. Ghi lại disk usage của các thư mục broker.
5. Trừ phần log/temporary noise nếu đo được; chia delta bytes cho số message còn lưu.
6. Lặp với nhiều payload sizes và body types.
7. Khi consumer drain, quan sát dung lượng có giảm ngay hay còn chờ cleanup/compaction.

Cần tách:
- Payload nhỏ nhiều message (metadata/index overhead trên mỗi message đáng kể).
- Payload lớn/large messages.
- Message có nhiều properties/headers.
- Paging backlog.
- DLQ, expiry và scheduled messages.

**Không dùng payloadBytes × count để dự báo store** nếu chưa đo actual disk growth. Overhead theo message và cách journal/page lưu có thể làm con số chênh đáng kể.

### 7.4. Dự phòng cho recovery và thao tác vận hành

Headroom không nên bằng 0 ngay khi đạt broker threshold. Phải để chỗ cho:
- Journal compaction/rewrite và recovery.
- Page files/large messages trong lúc consumer drain.
- KahaDB index/log cleanup.
- Broker logs, GC logs và diagnostic artifacts.
- Snapshot/backup nếu công cụ tạo snapshot trên cùng volume (tốt hơn đặt ngoài volume).
- File system metadata/inode và hoạt động hệ điều hành.

Ví dụ volume 500 GiB có thể đặt ngưỡng admission broker ở 85%, nhưng phần 15% còn lại **không tự động là toàn bộ reserve an toàn**. Nếu log/backup/heap dump cùng dùng volume, reserve thực sự phải trừ các nhu cầu đó.

## 8. Tách filesystem và quota theo vai trò dữ liệu

Một layout vận hành có thể là:

```text
/var/lib/broker-data/       journal, KahaDB, bindings, paging, large messages
/var/log/broker/            broker log, GC log, audit log
/var/lib/broker-diagnostics/heap/  heap dump, crash artifacts
/var/backups/broker/        backup/snapshot trên volume hoặc hệ thống độc lập
```

Mục đích:
- Log tăng bất thường không lấp journal volume.
- Heap dump không chiếm dung lượng paging.
- Snapshot/backup không cạnh tranh trực tiếp với message I/O nếu có thể tách.
- Có thể đặt quota và alert khác nhau cho data/log/diagnostics.

Nếu không thể tách volume, dùng quota và log rotation, đồng thời cộng tất cả thành phần vào disk budget. **Không đặt backup duy nhất trên cùng filesystem với broker store** rồi coi đó là khả năng khôi phục khi volume hỏng.

## 9. Backpressure và giới hạn disk: cách chọn cho từng broker

| Tiêu chí | ActiveMQ Classic | ActiveMQ Artemis |
| --- | --- | --- |
| Memory budget | SystemUsage.memoryUsage, memoryLimit per destination | global-max-size, max-size-bytes per address |
| Persistent store | SystemUsage.storeUsage | Journal, paging/large-message store và disk policy |
| Temporary data | SystemUsage.tempUsage | Paging/temp/large-message paths theo loại dữ liệu |
| Producer backpressure | Producer Flow Control, producerFlowControl | address-full-policy=BLOCK, disk-full-policy=BLOCK |
| Page/persist overflow | Cursor/store usage và broker policy | address-full-policy=PAGE, page-limit-bytes |
| Reject rõ ràng | Producer có thể nhận JMSException/ResourceAllocationException khi flow control policy áp dụng | FAIL/page-full-policy=FAIL |
| Drop | Có thể cấu hình theo policy/ứng dụng | DROP; phải chấp nhận mất message |

### 9.1. Classic: không tắt flow control chỉ để producer chạy nhanh

Nếu producer bị block khi store đạt ngưỡng, điều đó báo rằng tốc độ ingress đang vượt khả năng drain hoặc disk budget. Tắt producerFlowControl có thể làm backlog tiếp tục được ghi xuống store, nhưng store vẫn hữu hạn. Kết quả là broker có thể tiến gần disk full nhanh hơn và mất khả năng vận hành an toàn.

### 9.2. Artemis: PAGE, BLOCK và disk-full policy xử lý hai ngưỡng khác nhau

- address-full-policy quyết định khi address đạt memory/message limit.
- page-full-policy quyết định khi paging quota của address đạt giới hạn.
- disk-full-policy quyết định khi disk usage guard bị chạm.

Đặt PAGE mà không có page limit và disk headroom là để một queue có thể lấn át volume. Đặt BLOCK nhưng producer không có deadline/circuit breaker có thể khiến thread pool ứng dụng bị giữ hết. Đặt FAIL thì producer cần retry có backoff, giới hạn số lần và phân biệt lỗi tạm thời với lỗi cấu hình/quota.

### 9.3. Producer timeout và transaction outcome

Khi send bị block hoặc commit timeout:
- Đừng retry mù quáng nếu chưa biết transaction trước đã commit chưa.
- Gắn eventId ổn định vào business message.
- Nếu commit trả lỗi do connection reset, kết quả có thể unknown.
- Dùng inbox/idempotency phía consumer để tránh side effect lặp.
- Theo dõi producer blocked duration, timeout count, transaction rollback và redelivery.

Resource limit là một phần của delivery contract. Producer phải biết cách phản ứng khi broker backpressure, thay vì coi mọi exception là lỗi có thể retry vô hạn.

## 10. Theo dõi tài nguyên: dashboard cần nhìn cả broker lẫn host

### 10.1. Artemis metrics

Theo dõi:
- Global/address memory usage, global-max-size, address message count.
- Queue message count, delivering count, consumer count.
- Paging state, page store size, page-limit usage.
- Disk usage, free bytes, max-disk-usage/min-disk-free threshold.
- Journal write/read latency, large-message directory usage.
- Producer blocked/failed, send/commit latency, connection errors.

### 10.2. Classic metrics

Theo dõi:
- Broker memoryUsage, storeUsage, tempUsage và percent usage.
- Queue QueueSize, enqueue/dequeue, dispatch/in-flight, consumer count.
- KahaDB data/index/log size và free space.
- Producer flow-control blocked time/exception.
- Network connector/destination nếu broker forward message qua mạng.
- JMX Broker/Queue MBeans và log usage-limit events.

### 10.3. JVM, OS và container

Linux commands để đối chiếu tại host/container:

```bash
# Filesystem capacity và inode
df -h
df -i

# Kích thước các thư mục trên filesystem; -x tránh đi xuyên mount khác
du -x -h -d 1 /var/lib/broker-data

# Heap summary và native memory (NMT phải bật từ JVM startup)
jcmd <pid> GC.heap_info
jcmd <pid> VM.native_memory summary

# Cgroup v2 memory
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
```

Lệnh du chỉ phản ánh file đang thấy trong filesystem, không thay thế broker usage metrics. File đã unlink nhưng process còn giữ file descriptor có thể làm df cao hơn tổng du. Cần kiểm tra deleted-open files khi dung lượng không khớp.

## 11. Alert thresholds và cách đọc xu hướng

Ngưỡng dưới đây là **ví dụ vận hành** để bắt đầu, cần điều chỉnh theo SLA, tốc độ tăng backlog và thời gian phản ứng:

| Mức | Tín hiệu mẫu | Hành động |
| --- | --- | --- |
| Warning | Disk dùng >70%, heap old-gen tăng dần, address/page backlog tăng liên tục | Xác định producer/consumer rate, dự báo time-to-full |
| Critical | Disk dùng >80%, free space dưới reserve vận hành, GC pause/old-gen kéo dài | Giảm ingress có kiểm soát, tăng consumer nếu downstream khỏe, chuẩn bị mở rộng volume |
| Admission guard | Artemis max-disk-usage=85 hoặc min-disk-free đạt ngưỡng; Classic storeUsage high-watermark | Broker flow-control/reject theo policy; alert phải phát ra trước ngưỡng |
| Emergency | Disk gần 100%, container memory sát limit/OOM, journal/page write lỗi | Dừng hoặc throttle producer theo runbook; bảo vệ store và điều tra |

Không đợi đến 95–100% mới báo động. Thời gian xử lý phải nhỏ hơn time-to-full dự báo. Nếu time-to-full là 45 phút, alert critical sau 30 phút mới có tác dụng là quá muộn.

### 11.1. Alert theo tốc độ, không chỉ theo phần trăm

Một volume dùng 70% nhưng tăng 0,1%/ngày khác hoàn toàn volume dùng 70% và tăng 5%/giờ. Cần:
- Disk usage slope trong 5/15/60 phút.
- Queue backlog growth và consumer drain rate.
- Dự báo time-to-threshold.
- Producer blocked count/time.
- Page store growth và DLQ/expiry growth.

Ví dụ: time_to_full < 2h có thể critical ngay cả khi filesystem mới dùng 60%. Giá trị hai giờ chỉ là ví dụ; chọn ngưỡng dựa trên thời gian gọi người trực, tăng disk và drain backlog.

## 12. Runbook khi memory/disk chạm ngưỡng

### 12.1. Khi producer bị block

1. Xác định broker nào và address/queue nào đang đạt memory/store/page threshold.
2. So sánh ingress rate và ACK/dequeue rate.
3. Kiểm tra consumer count, consumer processing errors, redelivery và downstream DB/API.
4. Nếu consumer khỏe nhưng thiếu capacity, tăng worker có kiểm soát và theo dõi thứ tự/idempotency.
5. Nếu consumer lỗi, xử lý nguyên nhân trước khi tăng concurrency.
6. Giảm ingress hoặc bật admission control ở upstream khi backlog tăng nhanh.
7. Không tắt flow control như một phản xạ; nó có thể chỉ chuyển sự cố từ memory sang disk.

### 12.2. Khi disk gần đầy

1. Xác định filesystem chứa journal/KahaDB/paging/large messages và free bytes thực tế.
2. Xem directory nào tăng nhanh; phân biệt message store, page store, large messages, logs, heap dump và backup.
3. Tính lại time-to-full từ tốc độ tăng gần nhất.
4. Throttle producer hoặc dừng nguồn phát không thiết yếu theo thứ tự ưu tiên.
5. Tăng dung lượng volume hoặc chuyển dữ liệu theo quy trình broker/platform được hỗ trợ.
6. Drain consumer nếu downstream khỏe; theo dõi dequeue và page cleanup.
7. Kiểm tra DLQ/expiry; xử lý message theo retention/replay policy, không xóa mù quáng.
8. Chỉ resume ingress khi free-space reserve và broker health đã ổn định.

**Không xóa trực tiếp journal, KahaDB data/index, Artemis paging hoặc large-message files khi broker đang chạy.** Việc xóa file có thể làm mất message hoặc làm store không phục hồi được. Dọn dữ liệu phải qua broker management/API hoặc quy trình offline được hỗ trợ, sau khi đã backup và xác minh.

### 12.3. Khi JVM/container gần OOM

1. Phân biệt heap OOM với container OOM-kill.
2. Kiểm tra heap/GC, direct buffer, metaspace, thread count và process RSS.
3. Xem queue/message memory có tăng cùng heap hay chỉ native/direct tăng.
4. Thu thread dump/heap dump theo quy trình; đảm bảo diagnostics volume còn chỗ.
5. Giảm connection/thread churn hoặc payload concurrency nếu đó là nguyên nhân.
6. Không tăng -Xmx vượt container memory limit.
7. Sau khi xử lý, kiểm tra broker journal và pending messages trước khi mở lại tải.

## 13. Kiểm thử resource limits trước production

Dùng broker lab và queue riêng. Không cố tình làm đầy volume production để kiểm tra disk policy.

| Test | Cách tạo điều kiện | Kỳ vọng |
| --- | --- | --- |
| R1 | Artemis address vượt max-size-bytes, PAGE | Message page ra disk, address memory không tăng vô hạn |
| R2 | Artemis vượt page-limit-bytes với page-full-policy=FAIL | Producer nhận lỗi tường minh, không âm thầm drop |
| R3 | Artemis chạm disk guard với disk-full-policy=BLOCK | Producer chịu backpressure theo protocol hỗ trợ |
| R4 | Classic queue vượt memoryLimit | Producer flow-control hoạt động |
| R5 | Classic persistent store đạt high-watermark | Producer bị throttle/block theo storeUsage |
| R6 | Consumer drain sau khi producer bị block | Producer có thể tiếp tục khi usage giảm dưới ngưỡng |
| R7 | Producer commit timeout/connection reset | Unknown outcome được phân loại, eventId dedup |
| R8 | Tăng payload size/large messages | Đo disk growth thực tế, không chỉ payload estimate |
| R9 | DLQ/expiry tích lũy | Disk usage vẫn được tính; retention/cleanup có kiểm soát |
| R10 | Container memory pressure | OOM/GC/native metrics cảnh báo trước khi process bị kill |
| R11 | Log/heap dump tăng | Không lấp broker data volume |
| R12 | Restart sau paging/store pressure | Broker recover và queue state được kiểm chứng |

### 13.1. Tiêu chí nghiệm thu

- Broker không vượt container memory limit trong workload mục tiêu.
- Heap, direct/native và GC có headroom trong peak load.
- Resource guard kích hoạt **trước** khi filesystem cạn.
- Producer có hành vi đã biết khi BLOCK/FAIL: timeout, retry/backoff hoặc admission control.
- Message persistent không bị DROP ngoài contract.
- Khi consumer drain, broker giải phóng memory/page/store usage theo đúng cơ chế.
- Time-to-full được tính từ disk growth thực tế và còn lớn hơn thời gian phản ứng vận hành.
- Queue, DLQ, paging, large messages và log đều có retention/quota rõ.
- Có bằng chứng broker phục hồi sau khi đạt limit trong lab, không cần xóa file store.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Sửa thế nào |
| --- | --- | --- |
| Đặt -Xmx gần bằng container limit | OOM-kill do native/direct/page cache | Chừa ngân sách ngoài heap |
| Chỉ đặt global memory limit | Một address có thể chiếm phần lớn budget | Đặt per-address/per-destination limit |
| Artemis PAGE nhưng không page limit/disk guard | Paging có thể chiếm hết volume | Đặt page-limit-bytes, disk policy và alert |
| Classic storeUsage bằng toàn dung lượng volume | Log/heap dump/OS cần chỗ nhưng store đã dùng hết | Đặt store limit thấp hơn disk capacity và giữ reserve |
| Tắt producer flow control | Chuyển áp lực sang disk/store | Giữ backpressure và điều tiết ingress |
| Chọn DROP để tránh block | Mất message mà producer có thể không biết | Dùng BLOCK/FAIL cho business event |
| Chỉ xem heap dashboard | Bỏ lỡ direct/native hoặc disk pressure | Quan sát RSS/cgroup/disk và broker metrics |
| Không đo page/KahaDB growth | Ước lượng time-to-full sai | Đo disk delta trên workload tương tự |
| Để heap dump trên journal volume | OOM event làm volume đầy nhanh hơn | Tách diagnostics volume |
| Xóa file store để giải phóng disk | Journal/index/page corruption hoặc mất dữ liệu | Dọn qua broker-supported operation/runbook |

## 15. Checklist review trước khi phát hành cấu hình

- [ ] Đã có RAM budget gồm heap, direct/native, metaspace, thread stacks, OS/cache và reserve.
- [ ] -Xmx nhỏ hơn container/VM memory limit đủ nhiều để chừa native headroom.
- [ ] Artemis global-max-size hoặc Classic memoryUsage được đặt theo workload, không lấy toàn bộ heap.
- [ ] Có limit theo address/destination cho các queue quan trọng.
- [ ] Đã chọn PAGE/BLOCK/FAIL/DROP theo contract dữ liệu.
- [ ] Nếu PAGE, đã đặt page quota và policy khi page limit đạt ngưỡng.
- [ ] Artemis có max-disk-usage hoặc min-disk-free và disk-full-policy rõ ràng.
- [ ] Classic có storeUsage/tempUsage thấp hơn dung lượng volume thực và producerFlowControl được quyết định rõ.
- [ ] Đã đo bytes stored/message thực tế cho các payload size quan trọng.
- [ ] Có dự báo time-to-full từ ingress, egress và disk growth.
- [ ] Có reserve cho journal compaction/recovery, paging, large messages và diagnostics.
- [ ] Log, heap dump, backup được quota/rotation hoặc đặt ở volume riêng.
- [ ] Dashboard có heap, GC, RSS/cgroup, direct memory, disk free, store/page usage và queue backlog.
- [ ] Alert dựa trên cả percentage lẫn growth rate/time-to-full.
- [ ] Producer xử lý BLOCK/FAIL/timeout và unknown commit outcome bằng eventId/idempotency.
- [ ] Đã test đạt limit rồi drain để chứng minh broker phục hồi.
- [ ] Không có quy trình xóa file journal/KahaDB/page thủ công khi broker đang chạy.

## 16. Câu hỏi tự kiểm tra

1. Vì sao -Xmx4G không có nghĩa broker process chỉ dùng tối đa 4 GiB RAM?
2. Artemis global-max-size khác max-size-bytes theo address như thế nào?
3. address-full-policy=PAGE có ngăn disk đầy không?
4. page-limit-bytes và disk-full-policy bảo vệ hai phạm vi nào?
5. Vì sao min-disk-free được ưu tiên khi cấu hình cùng max-disk-usage?
6. Classic memoryUsage, storeUsage và tempUsage đại diện cho những ngân sách gì?
7. producerFlowControl=false có loại bỏ giới hạn store không?
8. Khi producer bị BLOCK, vì sao không nên kết luận broker bị treo ngay?
9. Vì sao heap dump cần filesystem/quota riêng?
10. Tại sao phải dùng disk growth đo thực tế thay vì chỉ nhân payload size với message count?
11. Nếu ingress 4.000 msg/s, egress 3.000 msg/s, stored size 2 KiB/msg, disk growth khoảng bao nhiêu?
12. Khi commit timeout, vì sao phải giữ trạng thái unknown và dedup bằng eventId?
13. Tại sao DROP nguy hiểm cho order/payment/audit?
14. Những metric nào giúp phân biệt heap pressure, native memory pressure và disk pressure?

**Gợi ý:** (1) còn direct/native/metaspace/thread page cache; (2) global toàn broker vs per address; (3) không, PAGE chuyển backlog sang disk; (4) quota paging theo address vs disk toàn broker; (5) free bytes là ngưỡng cụ thể và được ưu tiên; (6) broker memory, persistent store, temporary store; (7) không; (8) đó là backpressure có chủ đích; (9) tránh heap dump lấp journal; (10) còn journal/index/properties/page overhead; (11) khoảng 1,95 MiB/s; (12) broker có thể đã commit nhưng response mất; (13) có thể mất message âm thầm; (14) heap/GC, RSS/direct/cgroup, filesystem/store/page metrics.

## 17. Tài liệu tham khảo

- [Apache ActiveMQ Artemis — Paging](https://artemis.apache.org/components/artemis/documentation/latest/paging.html): global-max-size, per-address max-size-bytes, PAGE/BLOCK/FAIL/DROP, page limits và disk monitoring.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html): address-full-policy, disk-full-policy, redelivery và page limits.
- [Apache ActiveMQ Artemis — Configuration Reference](https://artemis.apache.org/components/artemis/documentation/latest/configuration-index.html): global-max-size, max-disk-usage, min-disk-free, disk-scan-period.
- [Apache ActiveMQ Classic — Producer Flow Control](https://activemq.apache.org/components/classic/documentation/producer-flow-control): SystemUsage, producer block/exception và memory/store/temp limits.
- [Apache ActiveMQ Classic — Per Destination Policies](https://activemq.apache.org/components/classic/documentation/per-destination-policies): producerFlowControl, memoryLimit, storeUsageHighWaterMark.
- [Apache ActiveMQ Classic — KahaDB](https://activemq.apache.org/components/classic/documentation/kahadb): persistent store và cấu hình KahaDB.
- [OpenJDK Java 17 — java launcher options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): -Xms, -Xmx, GC logging và JVM options.
- [OpenJDK Java 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): heap/native diagnostics và Native Memory Tracking.

> **Ghi nhớ:** Quản lý tài nguyên broker cần ba lớp guard cùng lúc: **JVM/container memory budget**, **broker message-memory/backpressure**, và **disk headroom**. Artemis PAGE và Classic store/cursor chỉ giúp hấp thụ backlog trong ngân sách đã định; chúng không tạo dung lượng vô hạn. Hãy đo tốc độ tăng store, dự báo time-to-full, đặt ngưỡng admission trước khi volume cạn, giữ producer flow control và kiểm thử khả năng drain/recovery.
