# Cursor memory và giới hạn theo destination trên Classic

> **Chương:** Điều tiết lưu lượng  
> **Phạm vi:** Apache ActiveMQ **Classic** với Java/JMS. Bài giải thích cách broker giữ backlog qua **message cursor**, vì sao giới hạn **memoryLimit** theo queue/topic không đồng nghĩa giới hạn số message, và khi nào producer thực sự bị flow control. Cấu hình bên dưới dùng **Classic activemq.xml**, không phải **Artemis broker.xml**.

Một queue nhận 20.000 message nhưng consumer chỉ xử lý được 300 message/giây. Trên console, **QueueSize** tăng nhanh, trong khi bộ nhớ broker không nhất thiết tăng tương ứng. Lý do là ActiveMQ Classic không bắt buộc giữ toàn bộ backlog dưới dạng Java object trong heap: **message cursor** kiểm soát tập message sẵn sàng dispatch và có thể dựa vào persistent store hoặc temporary storage.

Mặt khác, đặt **memoryLimit="1048576"** cho queue **không** có nghĩa queue ấy chỉ nhận tối đa 1 MiB payload. Đây là **ngân sách bộ nhớ broker** sử dụng để quản lý destination/cursor, chịu ảnh hưởng của cursor policy, prefetch và cách lưu message. Nếu hiểu nó như quota dung lượng hay message-count hard limit, rất dễ cấu hình sai producer flow control, dự trù thiếu đĩa, hoặc cố tình giảm prefetch trong khi nguyên nhân thật là storage đang đầy.

Mục tiêu bài học là **đọc được ba lớp giới hạn, chọn cursor có chủ đích và kiểm chứng bằng backlog thực**.

## 1. Ba lớp phải phân biệt trước khi chỉnh cấu hình

| Lớp | Ví dụ cấu hình / cơ chế | Chi phối điều gì? | Không cam kết điều gì? |
|---|---|---|---|
| **Destination memory budget** | **policyEntry.memoryLimit** | Lượng memory được tính cho một destination/usage hierarchy | Không phải giới hạn tổng byte message đã lưu vào queue |
| **Cursor policy** | **storeCursor**, **vmQueueCursor**, **fileQueueCursor** | Pending message được giữ/truy cập từ bộ nhớ, message store hoặc temporary files thế nào | Không thay thế persistence, ACK hoặc transaction |
| **Broker-wide usage limits** | **systemUsage.memoryUsage**, **storeUsage**, **tempUsage** | Ngân sách bộ nhớ, persistent store, temporary store của broker | Không phải quota cố định dành riêng cho một queue |

Ngoài ba lớp trên còn có **producerFlowControl**, **prefetch**, **consumer speed**, **KahaDB disk I/O** và giới hạn disk thật. Chúng phối hợp nhưng không đồng nghĩa.

### 1.1. Bốn trạng thái của một message

~~~mermaid
flowchart LR
    P["Producer"] --> B["Classic queue"]
    B --> C["Pending message cursor"]
    C --> D["Dispatch tới consumer / prefetch"]
    D --> A["Consumer ACK / commit"]
    C --- M["Broker RAM"]
    C --- S["Persistent message store"]
    C --- T["Temporary store"]
~~~

**Pending**: message chưa được consumer xác nhận, đang đợi dispatch hoặc xử lý theo broker.

**Cursor**: cơ chế mà broker dùng để truy cập, sắp xếp và cung cấp những message chờ dispatch. Nó không nhất thiết chứa toàn bộ message body trong RAM.

**Dispatched/in-flight**: message đã chuyển tới client/buffer, nhưng chưa chắc ứng dụng đã xử lý xong.

**Acknowledged**: broker nhận được tín hiệu hoàn tất phù hợp với JMS ACK/transaction; queue reference được giải phóng theo cơ chế storage.

Không suy từ **QueueSize** hoặc **MemoryPercentUsage** riêng lẻ rằng message đã được xử lý. Cần quan sát đồng thời **Pending/QueueSize, InFlightCount, EnqueueCount, DequeueCount** và phía ứng dụng.

## 2. Cursor memory giải quyết vấn đề gì?

ActiveMQ Classic phải giải quyết hai nhu cầu đối nghịch:

1. Trả nhanh message cho consumer khi có khả năng nhận.
2. Không giữ toàn bộ backlog của một destination trong JVM heap khi producer chạy nhanh hơn consumer.

**PendingMessageCursor** là cơ chế nội bộ chịu trách nhiệm quản lý tập message chưa dispatch/đang chờ được gửi tới consumer. Chọn loại cursor có thể ảnh hưởng mạnh đến lượng memory cần cho backlog và việc broker sử dụng store.

### 2.1. VM cursor: ưu tiên bộ nhớ, giới hạn tính mở rộng backlog

**VM queue cursor** giữ pending messages trong bộ nhớ theo chiến lược cursor tương ứng. Cấu hình minh họa:

~~~xml
<policyEntry queue="LAB.FLOW.VM"
             memoryLimit="1048576"
             producerFlowControl="true">
    <pendingQueuePolicy>
        <vmQueueCursor/>
    </pendingQueuePolicy>
</policyEntry>
~~~

**Ưu điểm:** phù hợp môi trường lab hoặc backlog được kiểm soát chặt, đường truy cập pending messages đơn giản.

**Giới hạn:** nếu producer nhanh hơn consumer và cursor/bộ nhớ đạt ngưỡng, producer có thể gặp flow control, tăng latency hoặc timeout. Không dùng VM cursor làm câu trả lời mặc định cho queue có backlog lớn kéo dài, đặc biệt khi cần giữ nhiều persistent message.

**Cần phân biệt:** VM cursor mô tả cách broker giữ **pending message references/data để dispatch**. Nó không tự biến một message **NON_PERSISTENT** thành durable, và cũng không xóa vai trò của message store cho persistent messages. Hành vi cụ thể còn phụ thuộc broker/client version.

### 2.2. Store cursor: lấy dữ liệu từ message store thay vì giữ hết trong heap

**Store-based queue cursor** dựa vào persistent message store để duyệt message bền vững khi backlog vượt phần được cache. Đây là hướng thường phù hợp cho queue persistent có nhiều message chờ.

~~~xml
<policyEntry queue="LAB.FLOW.STORE"
             memoryLimit="1048576"
             producerFlowControl="true">
    <pendingQueuePolicy>
        <storeCursor/>
    </pendingQueuePolicy>
</policyEntry>
~~~

Một mô hình đơn giản:

~~~text
Producer → Queue persistent → KahaDB message store
                               |
                   Store-backed pending cursor
                               |
                     bộ đệm/dispatch theo nhu cầu
                               |
                           Consumer
~~~

**Điểm quan trọng nhất:** queue vẫn có thể tăng **QueueSize vượt xa lượng message có body vừa trong 1 MiB RAM**, vì message store giữ phần dữ liệu bền vững. **memoryLimit không trở thành giới hạn số byte của toàn bộ backlog**.

Không phải mọi message đều có thể suy luận nằm “chỉ trong KahaDB”; cách cursor xử lý **NON_PERSISTENT** có thể dùng temporary store/bộ nhớ tùy policy. Store cursor **không có nghĩa** broker sẽ không bao giờ block producer: storeUsage, tempUsage, disk hoặc giới hạn tổng của broker vẫn có thể bị chạm.

### 2.3. File cursor: pending messages có thể dùng temporary files

Classic cũng có cursor dựa trên file, thường quan trọng với những trường hợp **non-persistent pending backlog** và topic subscriptions. Ví dụ một queue lab:

~~~xml
<policyEntry queue="LAB.FLOW.FILE"
             memoryLimit="1048576"
             producerFlowControl="true">
    <pendingQueuePolicy>
        <fileQueueCursor/>
    </pendingQueuePolicy>
</policyEntry>
~~~

File cursor có thể chuyển pending data/references sang **temporary store** khi cần giảm áp lực RAM. Vì thế phải theo dõi **tempUsage**, không chỉ memoryUsage.

**Đừng đồng nhất file cursor với journaling bền vững.** Temporary files phục vụ quản lý backlog; chúng không tạo cam kết sống qua broker restart giống **DeliveryMode.PERSISTENT** và persistent message store.

### 2.4. Bảng so sánh lựa chọn cursor

| Tiêu chí | VM queue cursor | Store queue cursor | File queue cursor |
|---|---|---|---|
| Nơi dựa vào để giữ pending data | Bộ nhớ JVM | Persistent message store, có cache/buffer | Bộ nhớ và temporary file store |
| Backlog tăng lâu | Dễ tạo memory pressure/flow control | Thường phù hợp với persistent queue | Giảm áp lực heap nhưng tăng temp disk I/O |
| Khi nào xét dùng | Lab, backlog nhỏ/được kiểm soát | Queue persistent có backlog có thể lớn | Kịch bản pending non-persistent hoặc cần file-backed cursor |
| Tài nguyên cần theo dõi | Destination/broker memory | Memory + store usage + journal I/O | Memory + temp usage + disk I/O |
| Durable message do cursor quyết định? | **Không** | **Không**, do delivery mode/commit/persistence | **Không** |
| Tự động giải quyết consumer chậm? | **Không** | **Không** | **Không** |

**Không có cursor “tốt nhất” cho mọi workload.** Cần đo với cùng message size, delivery mode, consumer prefetch, số queue và profile backlog. Store-based cursor thường là nền tảng hợp lý hơn cho queue persistent dài hạn, nhưng không làm producer/consumer nhanh hơn bản chất của họ.

## 3. memoryLimit: hạn mức bộ nhớ của destination, không phải quota lưu trữ

Trong **destinationPolicy** của Classic, thuộc tính **memoryLimit** cấu hình bộ nhớ mà một queue hoặc topic được phép sử dụng trong hệ thống usage. Giá trị được tính bằng **byte** khi cung cấp số nguyên.

~~~xml
<policyEntry queue="LAB.FLOW.STORE"
             memoryLimit="1048576"
             producerFlowControl="true"
             cursorMemoryHighWaterMark="70">
    <pendingQueuePolicy>
        <storeCursor/>
    </pendingQueuePolicy>
</policyEntry>
~~~

Ở đây:

- **memoryLimit="1048576"** tương đương khoảng **1 MiB** trong ví dụ.
- **cursorMemoryHighWaterMark="70"** đặt mốc sử dụng bộ nhớ liên quan cursor bằng **70% ngân sách đích** để điều khiển hành vi cache/đẩy ra store theo cursor hỗ trợ. **Nó không phải ngưỡng queue chỉ chứa 0,7 MiB message trên disk**.
- **producerFlowControl="true"** cho phép broker thực thi cơ chế điều tiết producer khi các điều kiện sử dụng tài nguyên yêu cầu.

**Mốc high-water mark không phải một công tắc chính xác đến từng byte.** Accounting của destination, kích thước object, message references, dispatch và version ảnh hưởng số liệu quan sát. Chỉ dùng nó để giải thích **chiến lược quản lý pending cursor memory**, không tính chính xác số message bằng phép chia memoryLimit / payloadSize.

### 3.1. Ví dụ tính toán backlog để thấy giới hạn

Giả sử:

- Producer: **1.000 message/giây**.
- Consumer: **700 message/giây**.
- Mỗi message trung bình **8 KiB** payload, chưa kể broker metadata.
- Thời gian chênh lệch: **120 giây**.

~~~text
Net backlog growth = 1.000 - 700 = 300 messages/giây
Pending tăng ≈ 300 × 120 = 36.000 messages
Payload backlog ≈ 36.000 × 8 KiB ≈ 281,25 MiB
~~~

Một **memoryLimit=4 MiB** không ngăn về mặt nguyên lý queue tích lũy khoảng 281 MiB message nếu persistent store và policy cho phép. Nó giới hạn phần **bộ nhớ đích/cursor** dùng để điều phối pending messages, còn phần bền vững có thể nằm trên disk.

Bởi vậy bài toán capacity phải tính **cả message size, backlog duration, store overhead, retention, DLQ và disk throughput**. Không đặt memoryLimit theo suy nghĩ “queue tối đa 4 MiB dữ liệu”.

### 3.2. Mức giới hạn không được bảo đảm cứng đến một byte

Destination memory accounting là cơ chế quản trị tài nguyên nội bộ, không phải bộ giới hạn cứng của tổng RSS của process:

- Heap còn dùng cho kết nối, threads, transport buffers, management, GC và ứng dụng nhúng khác.
- Message dispatch/prefetch có thể khiến dữ liệu nằm cả trong buffer client, không phản ánh một-một ở queue pending.
- Một message lớn hơn ngưỡng có thể làm usage tạm thời vượt mốc trong khi broker thực thi policy.
- Các giá trị memory usage tính theo tham chiếu và cấu trúc nội bộ, không phải phép đo chính xác OS heap usage.

Cần theo dõi cả **JMX destination MemoryPercentUsage**, **broker MemoryPercentUsage**, **JVM heap/GC**, và **StorePercentUsage/TempPercentUsage**.

## 4. systemUsage toàn broker: memory, store và temp

**systemUsage** quy định những ngưỡng tài nguyên chung của broker Classic. Nó khác với **memoryLimit theo destination**.

~~~xml
<!-- Fragment bên trong <broker> của activemq.xml -->
<systemUsage>
    <systemUsage>
        <memoryUsage>
            <memoryUsage limit="67108864"/>
        </memoryUsage>
        <storeUsage>
            <storeUsage limit="1073741824"/>
        </storeUsage>
        <tempUsage>
            <tempUsage limit="268435456"/>
        </tempUsage>
    </systemUsage>
</systemUsage>
~~~

Các giá trị lab tương ứng:

| Usage | Giới hạn ví dụ | Theo dõi |
|---|---:|---|
| **Broker memoryUsage** | 64 MiB | JVM/usage percent, nhiều destination chia sẻ |
| **Broker storeUsage** | 1 GiB | Persistent store như KahaDB, message bền vững |
| **Broker tempUsage** | 256 MiB | Pending data/file cursor/temp store tùy cấu hình |

Đây là **hạn mức policy**, không có nghĩa broker luôn có sẵn đúng dung lượng disk ấy. Disk thật có thể nhỏ hơn, bị chia sẻ hoặc mất inode. Nếu giới hạn đặt lớn hơn dung lượng volume thì broker vẫn có thể gặp lỗi I/O khi đĩa đầy.

### 4.1. Ba lớp giới hạn tương tác như thế nào?

~~~mermaid
flowchart TD
    P["Producer gửi message"] --> C{"Destination cursor/memory"}
    C -->|Còn ngân sách| D["Cache/dispatch theo cursor policy"]
    C -->|Áp lực memory| E{"Cursor hỗ trợ store/temp?"}
    E -->|Có| F["Dùng persistent/temporary store"]
    E -->|Không đủ| B["Producer flow control / chờ / lỗi"]
    F --> G{"StoreUsage/TempUsage còn dung lượng?"}
    G -->|Có| D
    G -->|Đầy| B
    D --> H["Consumer nhận và ACK"]
~~~

Đây là **mô hình giải thích**, không phải khẳng định các bước nội bộ của mọi Classic version diễn ra theo đúng thứ tự này.

**Thực tế quan trọng:** việc chạm memoryLimit của một queue **không buộc** producer dừng ngay nếu cursor có thể tiếp tục dựa vào store theo policy. Ngược lại, broker có thể chặn producer khi **storeUsage/tempUsage** tới hạn, ngay cả khi JVM heap còn khá trống.

### 4.2. Sum(memoryLimit) không phải lượng RAM được cấp phát trước

Nếu có 100 queue, mỗi queue memoryLimit=10 MiB, không có nghĩa lúc broker startup đã cấp ngay 1.000 MiB heap. Nó là giới hạn theo từng destination khi tài nguyên được sử dụng. Nhưng cũng không được kết luận cấu hình đó an toàn với một broker memoryUsage=128 MiB: nhiều queue đồng thời hoạt động có thể cạnh tranh bộ nhớ, gây memory pressure và flow control.

**Nguyên tắc thiết kế:** giới hạn destination để **cô lập phần nào các queue nóng**, sau đó chọn giới hạn broker-wide theo heap, lưu lượng và số lượng destination. Phải kiểm chứng bằng workload đồng thời, không benchmark một queue rồi nhân tuyến tính kết quả.

## 5. Cấu hình thực hành Classic cho ba queue

Giả sử cần so sánh:

- **LAB.FLOW.STORE:** queue persistent, store-backed cursor.
- **LAB.FLOW.VM:** queue test dùng VM cursor để quan sát memory pressure.
- **LAB.FLOW.FILE:** queue test file cursor/temporary store.

Các phần tử sau là **fragment cho Apache ActiveMQ Classic activemq.xml**. Đặt chúng vào phần **broker** có namespace Classic phù hợp, dùng đúng nơi **destinationPolicy** và **systemUsage**; nếu file đã có các phần tử ấy thì **thêm entry**, không chèn hai cấu trúc trùng nhau.

~~~xml
<destinationPolicy>
    <policyMap>
        <policyEntries>
            <policyEntry queue="LAB.FLOW.STORE"
                         memoryLimit="1048576"
                         cursorMemoryHighWaterMark="70"
                         producerFlowControl="true">
                <pendingQueuePolicy>
                    <storeCursor/>
                </pendingQueuePolicy>
            </policyEntry>

            <policyEntry queue="LAB.FLOW.VM"
                         memoryLimit="1048576"
                         producerFlowControl="true">
                <pendingQueuePolicy>
                    <vmQueueCursor/>
                </pendingQueuePolicy>
            </policyEntry>

            <policyEntry queue="LAB.FLOW.FILE"
                         memoryLimit="1048576"
                         producerFlowControl="true">
                <pendingQueuePolicy>
                    <fileQueueCursor/>
                </pendingQueuePolicy>
            </policyEntry>
        </policyEntries>
    </policyMap>
</destinationPolicy>
~~~

**Phạm vi đúng:** chỉ ba queue có tên cố định được match; tránh dùng **queue=">"** cho toàn production chỉ để làm lab. Dấu **>** trong Classic là wildcard match nhiều đoạn tên destination; không nhầm với **#** của Artemis address-settings.

### 5.1. Cấu hình một broker lab tối thiểu về storage và listener

~~~xml
<!-- Những phần tử minh họa trong broker Classic tương ứng -->
<persistenceAdapter>
    <kahaDB directory="data/kahadb"/>
</persistenceAdapter>

<systemUsage>
    <systemUsage>
        <memoryUsage>
            <memoryUsage limit="67108864"/>
        </memoryUsage>
        <storeUsage>
            <storeUsage limit="1073741824"/>
        </storeUsage>
        <tempUsage>
            <tempUsage limit="268435456"/>
        </tempUsage>
    </systemUsage>
</systemUsage>

<transportConnectors>
    <transportConnector name="openwire"
                        uri="tcp://127.0.0.1:61616"/>
</transportConnectors>
~~~

**Không coi các fragment này là broker.xml của Artemis.** ActiveMQ Classic có mô hình broker, policyEntry, KahaDB và cursor khác. Trong môi trường thực phải bổ sung cấu hình security, broker name, directory và lifecycle theo hệ thống đang triển khai.

Một số cấu hình Classic có sẵn nhiều policyEntry. Khi policy wildcard chồng lấn, phải kiểm tra **effective policy** của destination đang test thay vì chỉ nhìn thứ tự XML. Sau thay đổi, xác nhận broker đã reload/restart và đang dùng đúng file cấu hình.

### 5.2. Có nên dùng memoryLimit để áp hard backlog quota?

Không. Nếu nghiệp vụ yêu cầu **queue không được có quá N pending messages**, hoặc **message age không quá T**, hãy thiết kế policy/giám sát và cơ chế admission/backpressure rõ ràng. **memoryLimit là ngân sách bộ nhớ**, không phải giới hạn message count. Không dùng TTL hoặc DLQ để giả lập giới hạn bộ nhớ vì sẽ gây mất message theo thời gian.

Một queue persistent với store cursor có thể tích backlog lớn hơn memoryLimit rất nhiều, miễn storage capacity cho phép. Đó là **đặc tính có chủ đích** để xử lý consumer chậm, nhưng vẫn cần alert backlog age và disk capacity.

## 6. producerFlowControl: khi producer phải chờ

Khi **producerFlowControl=true**, broker Classic có thể dùng cơ chế điều tiết producer để tránh tiếp tục nhận dữ liệu vượt tài nguyên phù hợp. Quan sát được có thể là:

- **send/commit latency tăng** khi broker bị áp lực.
- Producer **block** chờ tài nguyên được giải phóng.
- Producer thấy **timeout / ResourceAllocationException / lỗi kết nối** tùy client, timeout và tình trạng broker.
- Store/temp gần đầy dẫn tới flow control ngay cả khi destination memory usage không cao.

### 6.1. Flow control không phải một lệnh ACK

Producer **send/commit thành công** nói về kết quả gửi vào broker theo phiên và delivery mode; không có nghĩa consumer đã xử lý và ACK. Ngược lại, producer bị block vì flow control không nhất thiết do queue không có consumer: có thể còn nhiều queue khác cùng tiêu thụ broker store/temp limit.

**Cẩn thận với deadlock ở application:**

~~~text
Thread A:
  producer.send() chờ broker giải phóng memory/store
  → cùng thread chưa chạy tới đoạn consume/ACK
  → áp lực không giảm
~~~

Với workload cần producer và consumer phối hợp, không đặt thiết kế mà **consumer chỉ có cơ hội chạy sau khi producer gửi xong một batch không giới hạn**. Nếu send có thể block, hãy dùng concurrency có kiểm soát, thời gian chờ và shutdown an toàn.

### 6.2. Không tắt flow control như “cách sửa lỗi hiệu năng”

~~~xml
<policyEntry queue="LAB.FLOW.STORE"
             memoryLimit="1048576"
             producerFlowControl="false"/>
~~~

Đoạn trên chỉ minh họa cú pháp **false**, **không phải khuyến nghị production**. Tắt flow control có thể chuyển áp lực sang **memory, temporary store, persistent store hoặc producer-side buffering**, tùy cursor và delivery mode; không làm consumer chậm trở nên nhanh hơn.

Giải pháp đúng thường nằm ở **consumer throughput, prefetch, batching, store capacity, message size, giới hạn số producer, rate limit và loại cursor**. Nếu cố tình thay đổi producerFlowControl, phải đo lại hành vi khi đầy memory/store/temp và kết quả bảo toàn message.

## 7. Prefetch và cursor: hai tầng không thể thay nhau

**Classic prefetch** xác định số message broker có thể dispatch trước cho consumer. **Cursor** xác định cách broker quản lý pending backlog chờ dispatch. Điều chỉnh prefetch có thể giúp consumer chậm không giữ quá nhiều message in-flight, nhưng **không tự giải quyết queue backlog** khi producer > consumer.

~~~text
Persistent queue:
    10.000 pending trong store/cursor
       |
       | dispatch đến consumer theo prefetch=20
       v
    Consumer buffer: tối đa khoảng 20 đang được dispatch trước
       |
       v
    Application xử lý và ACK
~~~

Các giá trị chỉ là **minh họa**; in-flight thực tế còn phụ thuộc ACK, dispatch, network và chính sách provider.

### 7.1. Cấu hình prefetch ở Classic Java client

~~~java
import org.apache.activemq.ActiveMQConnectionFactory;

ActiveMQConnectionFactory factory =
    new ActiveMQConnectionFactory("tcp://127.0.0.1:61616");

// Chỉ ảnh hưởng client/consumer dùng ConnectionFactory này.
factory.getPrefetchPolicy().setQueuePrefetch(20);
~~~

**queuePrefetch=20** không phải memoryLimit 20 message cho broker. Một queue có thể còn hàng triệu pending messages trong store, dù chỉ dispatch từng nhóm nhỏ tới consumer.

Prefetch quá lớn với consumer xử lý chậm có thể tăng số message in-flight và làm phân phối kém cân bằng giữa competing consumers. Prefetch quá nhỏ lại có thể làm throughput giảm vì chờ lượt dispatch/ACK thường xuyên. Cần đo **InFlightCount, consumer rate, ACK latency, fairness** chứ không chọn một con số theo cảm tính.

### 7.2. Topic và subscriptions không đơn giản là queue pending

Đối với **non-durable topic subscribers**, Classic có chính sách pending subscriber cursor riêng, chẳng hạn **pendingSubscriberPolicy**; với **durable subscriber**, cơ chế store-backed cursor và backlog bền vững khác.

Ví dụ hướng cấu hình file-backed pending subscriber cho một topic test:

~~~xml
<policyEntry topic="LAB.EVENTS.>"
             memoryLimit="2097152"
             producerFlowControl="true">
    <pendingSubscriberPolicy>
        <fileCursor/>
    </pendingSubscriberPolicy>
</policyEntry>
~~~

Phải kiểm tra version và policy effective của subscriber cụ thể. Đừng áp một **pendingQueuePolicy** cho topic rồi cho rằng mọi non-durable/durable subscriber đều dùng cursor tương tự queue ANYCAST.

Các chính sách pending message limit hoặc slow consumer riêng cho topic có thể ảnh hưởng message có được giữ lại cho subscriber hay không. Chúng không thay thế memoryLimit; đặc biệt không được thử một policy drop message trên topic production chỉ để tránh memory pressure.

## 8. Lab Java/JMS: producer nhanh và consumer chậm

Lab được thiết kế **không giả định gửi nhiều message sẽ luôn bị block**. Thay vào đó, nó cho phép quan sát:

- Backlog tăng nhanh trong queue persistent dùng **storeCursor** mà destination memory usage không tăng tuyến tính cùng tổng payload.
- Cấu hình **vmQueueCursor** có thể tạo áp lực memory/flow control sớm hơn.
- Prefetch ảnh hưởng **InFlightCount** và tốc độ tiêu thụ, không phải giới hạn tổng số pending.
- Broker **storeUsage/tempUsage** vẫn là các điểm nghẽn độc lập.

### 8.1. Chuẩn bị

1. Dùng **ActiveMQ Classic broker lab**, không dùng Artemis. Áp policy ở mục 5; đảm bảo KahaDB, systemUsage và cổng OpenWire thực sự hoạt động.
2. Dùng JDK và thư viện **org.apache.activemq:activemq-client** tương thích API **javax.jms** trong ví dụ. Nếu đang dùng Classic client Jakarta hoặc API phiên bản khác, đổi import/dependency một cách nhất quán.
3. Queue **LAB.FLOW.STORE**, **LAB.FLOW.VM**, **LAB.FLOW.FILE** chỉ chứa dữ liệu test; không có consumer ngoài ý muốn.
4. Set **MQ_URL**, **MQ_USER**, **MQ_PASSWORD** phù hợp môi trường. Ví dụ URL **tcp://127.0.0.1:61616** chỉ đúng khi listener đã mở. Không hardcode production credential.
5. Bật JMX/console và quan sát **QueueSize, MemoryPercentUsage, EnqueueCount, DequeueCount, InFlightCount** cùng broker store/temp percent.
6. Đảm bảo disk còn đủ chỗ; không dùng bài test để cố làm cạn đĩa thực. Bắt đầu với 100–400 message, tăng từng bước.

### 8.2. Chương trình gửi/nhận JMS 1.1 tương thích Classic

Các chế độ: **send STORE 400**, **send VM 400**, **send FILE 400**, hoặc **consume STORE**, **consume VM**, **consume FILE**.

~~~java
import java.util.Arrays;

import javax.jms.BytesMessage;
import javax.jms.Connection;
import javax.jms.DeliveryMode;
import javax.jms.Message;
import javax.jms.MessageConsumer;
import javax.jms.MessageProducer;
import javax.jms.Queue;
import javax.jms.Session;

import org.apache.activemq.ActiveMQConnectionFactory;

public final class ClassicCursorLab {
    private static final int PAYLOAD_BYTES = 16 * 1024;

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: send|consume STORE|VM|FILE");
        }

        String destination = selectQueue(args[1]);
        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String pass = required("MQ_PASSWORD");

        ActiveMQConnectionFactory factory =
            new ActiveMQConnectionFactory(url);

        // Classic-specific client configuration.
        factory.getPrefetchPolicy().setQueuePrefetch(20);

        // Giới hạn thời gian gửi trong lab để tránh chờ vô hạn
        // nếu broker đang flow-control. Kiểm tra API của version dùng.
        factory.setSendTimeout(5000);

        Connection connection = factory.createConnection(user, pass);
        try {
            connection.start();

            Session session = connection.createSession(
                true, Session.SESSION_TRANSACTED);
            try {
                Queue queue = session.createQueue(destination);
                if ("send".equals(args[0])) {
                    sendBatch(session, queue, 400);
                } else if ("consume".equals(args[0])) {
                    consumeSlow(session, queue);
                } else {
                    throw new IllegalArgumentException(
                        "Expected send or consume");
                }
            } finally {
                session.close();
            }
        } finally {
            connection.close();
        }
    }

    private static void sendBatch(
            Session session, Queue queue, int count) throws Exception {

        MessageProducer producer = session.createProducer(queue);
        try {
            producer.setDeliveryMode(DeliveryMode.PERSISTENT);

            byte[] bytes = new byte[PAYLOAD_BYTES];
            Arrays.fill(bytes, (byte) 65);

            for (int i = 0; i < count; i++) {
                BytesMessage message = session.createBytesMessage();
                message.writeBytes(bytes);
                message.setIntProperty("labSequence", i);
                message.setStringProperty(
                    "labRun", "cursor-baseline");

                producer.send(message);

                // Chia batch nhỏ để quan sát commit, QueueSize.
                if ((i + 1) % 20 == 0) {
                    session.commit();
                    System.out.println(
                        "Committed messages=" + (i + 1));
                }
            }
        } catch (Exception error) {
            // Những send chưa commit trong transaction hiện tại
            // được rollback; những batch đã commit trước đó vẫn tồn tại.
            session.rollback();
            throw error;
        } finally {
            producer.close();
        }
    }

    private static void consumeSlow(
            Session session, Queue queue) throws Exception {

        MessageConsumer consumer = session.createConsumer(queue);
        try {
            int count = 0;
            while (true) {
                Message message = consumer.receive(1500);
                if (message == null) {
                    break;
                }

                // Giả lập consumer chậm: không gọi DB thật.
                Thread.sleep(200);
                session.commit();
                count++;

                if (count % 20 == 0) {
                    System.out.println(
                        "Committed receives=" + count);
                }
            }
            System.out.println("Total received=" + count);
        } catch (Exception error) {
            session.rollback();
            throw error;
        } finally {
            consumer.close();
        }
    }

    private static String selectQueue(String name) {
        switch (name) {
            case "STORE": return "LAB.FLOW.STORE";
            case "VM": return "LAB.FLOW.VM";
            case "FILE": return "LAB.FLOW.FILE";
            default:
                throw new IllegalArgumentException(
                    "Use STORE, VM or FILE");
        }
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException(
                "Missing env: " + key);
        }
        return value;
    }
}
~~~

**Các giới hạn của ví dụ:**

- **Session transacted** giúp nhóm send được commit và mỗi receive được ACK qua commit. Nó **không** bảo đảm logic nghiệp vụ đúng một lần khi consumer crash. Ở đây chỉ đo cơ chế cursor.
- **setSendTimeout(5000)** là cấu hình riêng Classic client dùng để tránh test kẹt vô thời hạn. Nếu broker tiếp tục bị flow control, chương trình có thể ném exception; đó là **kết quả cần ghi**, không phải bằng chứng policy sai.
- Message **PERSISTENT** với FileCursor/VM cursor vẫn phụ thuộc **persistent store** cho độ bền; tên cursor không sửa delivery mode.
- Tổng payload 400 × 16 KiB ≈ **6,25 MiB**, chưa gồm JMS/broker overhead. Dữ liệu này vượt memoryLimit ví dụ 1 MiB nhưng **store cursor có thể giữ backlog trên disk**.
- Không chạy nhiều producer đồng thời hoặc dùng queue production khi chưa hoàn tất baseline đơn luồng.

### 8.3. Lab A — Quan sát storeCursor

1. Xác nhận **LAB.FLOW.STORE** trống và policy đang dùng **storeCursor**, memoryLimit=1 MiB.
2. Không chạy consumer. Chạy **send STORE** để gửi 400 persistent BytesMessage.
3. Ghi kết quả các lần **commit**, QueueSize, MemoryPercentUsage, StorePercentUsage và kích thước KahaDB.
4. Bắt đầu **consume STORE**; quan sát QueueSize giảm, DequeueCount tăng và in-flight theo prefetch.
5. Đợi broker ổn định; xem memory usage có giảm/reclaim không, nhưng **không kỳ vọng KahaDB file xóa ngay** khi queue rỗng.

**Kỳ vọng:** queue có thể lưu backlog nhiều MiB dù **memoryLimit=1 MiB**, cho thấy **memory budget khác persistent backlog capacity**. Nếu producer bị block, kiểm tra **storeUsage, memoryUsage tổng broker, policy effective, disk** trước khi kết luận store cursor bị lỗi.

### 8.4. Lab B — So với vmQueueCursor

1. Xác nhận **LAB.FLOW.VM** trống, memoryLimit và producerFlowControl giống queue STORE.
2. Không chạy consumer; chạy **send VM**.
3. Đo số batch commit thành công trước khi xuất hiện block/timeout (nếu có), memoryPercentUsage và send latency.
4. Chạy **consume VM** ở tiến trình khác để giải phóng áp lực, theo dõi producer có thể tiếp tục không.
5. So sánh với storeCursor trên cùng broker, payload và số producer.

**Kỳ vọng:** VM cursor nhấn mạnh chi phí giữ pending trong memory, nên có thể xuất hiện memory pressure rõ hơn. **Không hứa chắc 1 MiB sẽ chặn ngay sau đúng 64 message**: metadata, cursor cache, dispatch và usage accounting làm ngưỡng thay đổi.

**An toàn:** Nếu producer timeout, đừng vòng lặp retry vô hạn; dừng, ghi trạng thái và drain queue lab. Một batch đã commit không biến mất khi một batch sau fail.

### 8.5. Lab C — File cursor và temp usage

1. Xác nhận policy **LAB.FLOW.FILE** dùng fileQueueCursor.
2. Gửi backlog tương tự; theo dõi cả **TempPercentUsage** và MemoryPercentUsage.
3. Có thể làm một biến thể dùng **NON_PERSISTENT** trên sandbox để làm rõ temporary store; khi thay delivery mode, nhớ rằng bài test durability không còn tương đương bài persistent.
4. Drain queue và quan sát temp store cleanup theo broker lifecycle.

**Kỳ vọng:** file-backed cursor có thể sử dụng temporary storage khi áp lực RAM tăng. Không suy từ “có temporary file” rằng message sẽ sống qua broker restart.

### 8.6. Bảng ghi kết quả

| Phép thử | Số gửi/commit | QueueSize cực đại | MemoryPercentUsage | StorePercentUsage | TempPercentUsage | Block/timeout | Số ACK |
|---|---:|---:|---:|---:|---:|---|---:|
| Store cursor, persistent | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Có/không | Ghi thực tế |
| VM cursor, persistent | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Có/không | Ghi thực tế |
| File cursor, persistent | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Có/không | Ghi thực tế |
| File cursor, non-persistent | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Ghi thực tế | Có/không | Ghi thực tế |

Không điền số giả định và gọi đó là kết quả benchmark. Trong bài lab, mọi phép so sánh phải giữ **cùng broker/version, storage, payload, prefetch, commit batch size và trạng thái ban đầu**.

## 9. Quan sát JMX: đo destination trước khi chỉnh policy

Classic cung cấp destination và broker metrics qua JMX/console. Ví dụ ObjectName của một queue có thể có dạng:

~~~text
org.apache.activemq:type=Broker,
brokerName=<broker-name>,
destinationType=Queue,
destinationName=LAB.FLOW.STORE
~~~

Tên broker và việc escape ObjectName phụ thuộc cấu hình thực tế. Mở JConsole/Hawtio/Classic web console hoặc công cụ quản trị sẵn có; không hardcode ObjectName từ ví dụ nếu brokerName khác.

### 9.1. Bộ chỉ số đủ để giải thích cursor pressure

| JMX/metric | Câu hỏi cần trả lời | Lỗi diễn giải thường gặp |
|---|---|---|
| **QueueSize** | Có bao nhiêu message còn trong queue ở trạng thái chờ theo metric của broker? | Tưởng là số message đã xử lý thất bại |
| **EnqueueCount / DequeueCount** | Số message vào và ra theo counters | Tưởng difference luôn bằng QueueSize tức thời trong mọi trường hợp |
| **InFlightCount** | Broker đã dispatch bao nhiêu message chưa ACK? | Coi mọi in-flight là ứng dụng đang xử lý CPU |
| **MemoryPercentUsage** của queue | Destination đang dùng bao nhiêu phần trăm budget? | Coi là phần trăm toàn bộ backlog nằm trên RAM |
| **MemoryLimit** của queue | Ngân sách bộ nhớ hiệu lực bao nhiêu? | Coi là quota dung lượng disk của queue |
| **Broker MemoryPercentUsage** | Nhiều destination cùng gây memory pressure không? | Chỉ xem một queue rồi kết luận broker còn khỏe |
| **StorePercentUsage** | Persistent store gần giới hạn policy chưa? | Chỉ nhìn Java heap mà bỏ qua disk |
| **TempPercentUsage** | Temporary store có đang bị tiêu hao không? | Nhầm với durable message journal |
| **ConsumerCount / ProducerCount** | Có đủ consumer và bao nhiêu producer đang tạo tải? | Tưởng consumer tồn tại đồng nghĩa throughput đáp ứng |

Các tên attribute cụ thể có thể khác theo MBean, Classic version và loại destination. Quan sát **giá trị theo thời gian**, không chỉ snapshot đơn lẻ.

### 9.2. Dấu hiệu điển hình

**QueueSize tăng, MemoryPercentUsage thấp/ổn định, StorePercentUsage tăng:** store cursor đang giúp broker giữ backlog bền vững ngoài phần memory cache. Đây có thể là hành vi bình thường, nhưng disk capacity và message age đang trở thành rủi ro.

**QueueSize tăng, MemoryPercentUsage gần ngưỡng, send latency tăng:** kiểm tra VM cursor/high watermark, producer flow control và số consumer có ACK kịp không.

**Broker TempPercentUsage cao nhưng storeUsage chưa cao:** kiểm tra pending file cursor và non-persistent backlog hoặc những hoạt động dùng temporary store.

**QueueSize thấp nhưng InFlightCount cao và consumer chậm:** có thể message đã được prefetch/dispatch nhưng chưa ACK; giảm queue memoryLimit không trực tiếp giải quyết client giữ message quá lâu.

**Journal/KahaDB vẫn lớn sau drain:** file pool/reuse và journal cleanup có chu kỳ riêng. Không xóa file store trực tiếp để làm đẹp chỉ số.

## 10. Phân tích lỗi thực tế theo nguyên nhân, không theo triệu chứng

### 10.1. Producer send bị treo trong giờ cao điểm

**Cần phân biệt:**

1. MemoryPercentUsage của queue đạt ngưỡng?
2. MemoryPercentUsage toàn broker gần hạn?
3. StorePercentUsage hoặc TempPercentUsage có tới hạn?
4. Disk đầy hoặc I/O latency tăng?
5. Consumer stopped, ACK chậm hoặc prefetch quá cao?
6. Có batch transaction quá lớn, một thread vừa send vừa đợi consumer?

**Khắc phục:** nếu nguyên nhân là consumer chậm, tăng khả năng xử lý hoặc giảm rate producer; nếu do store/temp đầy, xử lý capacity/backlog; nếu VM cursor gây memory pressure, cân nhắc store/file cursor phù hợp. **Không tắt producerFlowControl trước khi có cơ chế giới hạn khác.**

### 10.2. Heap broker tăng nhưng QueueSize ít thay đổi

Có thể do:

- Prefetched/in-flight messages lớn.
- Nhiều destination hoặc kết nối cùng hoạt động.
- Producer/client batching, message body lớn hoặc temporary objects.
- Memory accounting và JVM GC; không hoàn toàn cùng thước đo.
- Một topic subscriber chậm hoặc cursor policy khác queue đang quan sát.

**Điều tra:** heap/GC, InFlightCount, number of destinations, per-destination memory, client prefetch và thread dumps có kiểm soát. Không đổ lỗi toàn bộ cho cursor của queue được thấy đầu tiên.

### 10.3. Store cursor khiến disk tăng nhanh

Store cursor giúp broker không phải giữ toàn bộ backlog persistent trong heap, nhưng **không xóa chi phí lưu trữ**. Nếu producer lâu dài nhanh hơn consumer, backlog vẫn tăng và KahaDB có thể tới giới hạn storeUsage/disk.

**Điều tra:** enqueue rate − dequeue rate, queue age, oldest message age, store I/O, disk free, journal cleanup và quy trình retention. Có thể cần rate limiting, thêm consumer được thiết kế đúng, hoặc xử lý payload/dung lượng theo nghiệp vụ.

### 10.4. Non-persistent message qua file cursor bị mất sau restart

Không phải bug tự động: **NON_PERSISTENT** không được hứa giữ qua broker restart như **PERSISTENT**. File cursor/temporary store không tự tạo durability.

Nếu workload cần giữ message khi broker restart, phải xét **PERSISTENT delivery, storage bền vững, ACK/transaction và broker HA/backup**, không chỉ thay cursor policy.

### 10.5. Thay memoryLimit nhưng không thấy tác dụng

Kiểm tra:

- Broker có thực sự dùng file activemq.xml đã sửa?
- Destination **match đúng policyEntry** hay bị wildcard/policy khác phủ?
- Thay đổi có được reload/restart theo phiên bản hỗ trợ?
- Queue đang dùng cursor nào; backlog nằm trong KahaDB hay memory?
- Broker bị chặn bởi **storeUsage/tempUsage** chứ không phải memoryLimit?
- Prefetch của client vẫn quá lớn?
- JMX đang nhìn đúng broker và đúng queue, không nhầm namespace môi trường?

Không kết luận policy sai chỉ từ việc queue vẫn nhận trên 1 MiB message sau khi đặt memoryLimit=1 MiB.

## 11. Điều chỉnh có kiểm soát khi đưa vào production

Một quy trình thay đổi hợp lý:

1. **Đo baseline:** queue name, cursor policy hiện có, memoryLimit, broker systemUsage, backlog, peak producer rate, consumer ACK rate, p95/p99 send latency và disk capacity.
2. **Phân loại workload:** persistent/non-persistent, queue/topic, durable subscriber, payload size, tolerated latency, retention/backlog.
3. **Chọn cursor:** store-backed cho persistent queue backlog lớn; cân nhắc VM khi backlog nhỏ; file-backed cho trường hợp pending temp data phù hợp. Không thay tất cả queue bằng cùng một policy.
4. **Đặt memoryLimit theo ngân sách thực:** heap và số destination đồng thời, chứ không dựa trên mong muốn hạn chế message count.
5. **Chọn producerFlowControl:** bật bảo vệ nếu cần; định nghĩa client timeout, retry/backoff và hành vi khi broker không nhận thêm.
6. **Kiểm tra usage limits:** memoryUsage, storeUsage, tempUsage, disk free và độ trễ storage.
7. **Thử canary:** áp policy cho namespace cụ thể trước, dùng một queue test hoặc subset workload; đo send latency, ACK/consumer behavior và queue age.
8. **Thử failure modes:** consumer dừng, broker restart, disk gần giới hạn trong lab, producer timeout, batch rollback và reconnect.
9. **Rollout + monitor:** kiểm tra policy effective, memoryPercentUsage, queue age, store/temp growth, producer timeouts và DLQ.
10. **Rollback có chủ đích:** khôi phục policy cũ qua quy trình broker phù hợp; không xóa backlog hoặc message store để “trở về trạng thái trước”.

### 11.1. Ma trận quyết định rút gọn

| Workload | Hướng cấu hình cần kiểm chứng | Không nên làm |
|---|---|---|
| Persistent queue, consumer có thể offline hàng giờ | Store cursor + memory budget hữu hạn + store capacity/monitoring | Coi memoryLimit là giới hạn backlog |
| Non-persistent backlog tạm, chấp nhận mất khi restart | File cursor hoặc policy phù hợp + temp capacity | Gọi temp store là durable |
| Queue lab backlog nhỏ | VM cursor để so hành vi memory pressure | Suy từ lab đó ra toàn bộ production |
| Topic có subscriber chậm | Chính sách pending subscriber phù hợp + đánh giá durable/non-durable | Dùng pendingQueuePolicy cho mọi subscription |
| Producer có yêu cầu latency chặt | Timeout/backoff, limit rate, SLO về flow control | Tắt flow control rồi đẩy OOM sang broker |
| Nhiều queue đồng thời | memoryLimit theo destination + broker memoryUsage + full workload test | Cộng memoryLimit như bộ nhớ đã được cấp phát trước |

## 12. Bài tập cuối bài

### Bài A — Giải thích queue vượt memoryLimit

Một queue persistent đặt memoryLimit=2 MiB, storeCursor, nhưng dashboard báo **QueueSize=100.000 messages**, payload trung bình 4 KiB.

**Yêu cầu:** giải thích tại sao không mâu thuẫn; tìm tài nguyên nào có nguy cơ cạn trước; đề xuất metric phải xem. **Đáp án mấu chốt:** memoryLimit là budget memory, store có thể giữ backlog bền vững; theo dõi storeUsage, disk, queue age và consumer rate.

### Bài B — Producer block nhưng heap còn rảnh

Broker có MemoryPercentUsage=40%, StorePercentUsage=100%, producer send đang chờ.

**Yêu cầu:** lý giải có thể là **storeUsage limit**, không phải queue memoryLimit. Đề xuất biện pháp xử lý backlog/capacity mà không tắt producerFlowControl tùy tiện.

### Bài C — VM cursor và store cursor trong cùng broker

Chạy hai queue **LAB.FLOW.VM** và **LAB.FLOW.STORE** với cùng payload, memoryLimit, delivery mode; ghi số commit, memory usage, send latency và QueueSize.

**Yêu cầu:** giải thích khác biệt bằng **pending cursor policy**, không suy ra kết quả chính xác chỉ từ cấu hình. Đưa ra nhận xét dựa trên số đo thực tế.

### Bài D — Consumer prefetch quá lớn

Hai competing consumers: worker A rất chậm, worker B nhanh. Prefetch cao khiến A giữ nhiều message đã dispatch.

**Yêu cầu:** thử giảm queuePrefetch từ 100 xuống 20 trong lab; ghi InFlightCount và throughput của hai worker. Phân biệt prefetch với pending cursor memory và chỉ ra trade-off throughput/fairness.

### Bài E — Topic non-durable subscriber chậm

Một non-durable topic subscriber có backlog lớn; broker memory/temp usage tăng.

**Yêu cầu:** xác định vì sao phải kiểm tra **pendingSubscriberPolicy** thay vì chỉ **pendingQueuePolicy**, và vì sao không tự động chuyển message sang persistent store để biến non-durable thành durable.

### Bài F — Chọn memoryLimit cho nhiều queue

Có 80 queue, mỗi queue có memoryLimit=8 MiB nhưng broker systemUsage.memoryUsage chỉ 128 MiB. Trong peak, 30 queue cùng nhận backlog.

**Yêu cầu:** giải thích đây là giới hạn **khi sử dụng**, không phải reservation; benchmark workload đồng thời, tìm queue nóng và kiểm tra tổng memory usage, store/temp capacity.

### Checklist cuối cùng

- [ ] Phân biệt **destination memoryLimit**, **cursor policy**, **broker systemUsage**.
- [ ] Giải thích vì sao memoryLimit **không phải** giới hạn message count hoặc tổng backlog bytes.
- [ ] Biết tác dụng và giới hạn của **vmQueueCursor**, **storeCursor**, **fileQueueCursor**.
- [ ] Hiểu **cursorMemoryHighWaterMark** là mốc quản lý cursor memory, không phải disk quota.
- [ ] Phân biệt **persistent store** với **temporary store** và **DeliveryMode.PERSISTENT**.
- [ ] Biết producerFlowControl có thể tác động khi **memory/store/temp** bị áp lực.
- [ ] Biết **prefetch** điều tiết số message dispatch trước, không thay pending cursor.
- [ ] Cấu hình được policyEntry theo tên queue cụ thể trong **Classic activemq.xml**.
- [ ] Theo dõi được **QueueSize, EnqueueCount, DequeueCount, InFlightCount, MemoryPercentUsage, StorePercentUsage, TempPercentUsage**.
- [ ] Có phép thử consumer chậm, producer nhanh, timeout và drain queue được kiểm soát.
- [ ] Không tắt flow control hoặc xóa KahaDB/temp files để chữa một triệu chứng chưa phân tích.
- [ ] Nhớ rằng **Artemis có address paging/consumer window và mô hình broker.xml khác**, không sao chép các policy Classic sang Artemis.

**Kết luận:** Với **ActiveMQ Classic**, **cursor** quyết định cách broker quản lý pending messages để dispatch mà không buộc toàn bộ backlog nằm trong heap. **memoryLimit theo destination** giới hạn ngân sách bộ nhớ, **systemUsage** giới hạn tài nguyên chung của broker, còn **producerFlowControl** phản ứng với áp lực theo policy. Tối ưu đúng không phải giảm mỗi memoryLimit, mà là **chọn cursor theo persistence/backlog, đo cả memory–store–temp, hiểu prefetch và kiểm chứng producer timeout/consumer ACK dưới tải thực**.
