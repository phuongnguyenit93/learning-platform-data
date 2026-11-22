# Artemis federation, mirror và khác biệt với HA replication

## 1. Ba cơ chế cùng nối broker nhưng phục vụ ba mục tiêu khác nhau

Giả sử doanh nghiệp có **broker A** ở trung tâm dữ liệu miền Bắc và **broker B** ở miền Nam. Dịch vụ Inventory ở B cần nhận công việc được gửi vào A; nhóm vận hành đồng thời muốn giữ một bản dữ liệu ở vùng thứ hai để khôi phục thảm họa. Hai nhu cầu đó **không phải** một bài toán duy nhất.

Trong Apache ActiveMQ Artemis, cần tách ba khái niệm:

- **Federation**: kết nối các broker **độc lập** để chuyển tiếp message theo **nhu cầu (demand)** và **policy**. Queue federation tập trung san sẻ công việc giữa queue; address federation tập trung đưa message tới các subscription có nhu cầu trên broker khác.
- **AMQP Mirror**: kết nối broker độc lập để **phản chiếu một số sự kiện về tài nguyên và thông điệp** qua liên kết AMQP, ví dụ tạo queue, gửi message và ACK, theo tính năng/cấu hình cụ thể. Mirror thường phục vụ nhân bản dữ liệu broker, di chuyển tải hoặc các phương án disaster recovery có kiểm soát.
- **HA Replication**: **primary** chuyển trạng thái lưu trữ cần thiết cho **backup** thuộc cùng một mô hình high availability, để backup có thể **kích hoạt tiếp quản** khi primary không còn phục vụ. Đây không phải hai broker hoạt động độc lập cùng xử lý một queue.

~~~mermaid
flowchart TB
    subgraph FED["Federation: broker độc lập, route theo demand"]
      FP["Producer"] --> FB["Broker B: queue orders.work"]
      FB -. "Federated consumer / demand" .-> FA["Broker A: queue orders.work"]
      FA --> FC["Inventory consumer tại A"]
    end
    subgraph MIR["AMQP Mirror: phản chiếu operation"]
      MP["Producer"] --> MA["Broker A"]
      MA == "Mirror events qua AMQP" ==> MB["Broker B"]
      MA --> MCA["Local clients A"]
      MB --> MCB["Remote clients / DR"]
    end
    subgraph HA["HA replication: primary + standby"]
      HP["Clients"] --> HPR["Primary (active)"]
      HPR == "Replicated broker state" ==> HB["Backup (passive)"]
      HB -. "Chỉ active sau failover" .-> HP
    end
~~~

Sơ đồ chỉ biểu diễn **vai trò**, không hứa routing, độ trễ hoặc chuyển đổi tự động giống nhau ở mọi cấu hình. Ở federation, chiều “upstream” cần đọc theo **nơi đặt cấu hình và nơi phát sinh demand**, không chỉ theo hướng mũi tên trên sơ đồ.

Bài thuộc chương **Kết nối nhiều broker** của module **INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ**. Phạm vi là cơ chế chuyển tiếp queue/topic, routing, consistency, acknowledgement, failover, vận hành broker đáng tin cậy và cách kiểm chứng bằng Java JMS. **Không dùng từ “replication” chung chung** để kết luận ba cơ chế có cùng semantics.

## 2. Bảng quyết định nhanh: demand, bản sao và chủ sở hữu dữ liệu

| Tiêu chí | Artemis Federation | AMQP Mirror | HA Replication |
| --- | --- | --- | --- |
| Mục tiêu | Mở rộng kết nối/tiêu thụ giữa broker | Đồng bộ/nhân bản hoạt động broker theo mirror link | Tính sẵn sàng cho một dịch vụ broker logic |
| Mô hình | Nhiều broker **độc lập**, có policy | Các broker **độc lập**, có link AMQP | Một **primary active** và backup nhận bản sao trạng thái |
| Điều kiện chuyển message | **Demand và include/exclude policy** | **Sự kiện nguồn + mirror config** | Thay đổi trạng thái broker phục vụ replication |
| Queue work kiểu ANYCAST | Có thể chuyển công việc đến consumer ở broker khác | Có thể tạo trạng thái message tương ứng bên đích; không mặc định là cân tải | Backup **không tiêu thụ đồng thời** queue của primary |
| Topic/MULTICAST | Address federation theo nhu cầu subscriber | Phản chiếu dữ liệu/operation theo policy, phải hiểu ACK | Backup giữ trạng thái để tiếp quản |
| ACK | ACK của consumer liên quan message được forward | Có thể phản chiếu acknowledgements khi bật | Trạng thái ACK/journal cần nhất quán theo HA protocol |
| Broker đích có được dùng độc lập? | Có | Có, với chính sách vận hành nhất quán | Backup thường **passive** trước failover |
| Đường nối đứt | Demand remote không được phục vụ, backlog tùy nơi nhận | Mirror lag/backlog hoặc mất kết nối tùy policy/durability | Kích hoạt backup theo HA/quorum/fencing |
| Auto failover cho JMS client? | **Không tự có** chỉ vì federation | **Không tự có** chỉ vì mirror | Có thể kết hợp client failover khi HA được cấu hình đúng |
| Bảo đảm exactly-once nghiệp vụ? | Không | Không | Không; vẫn cần idempotency cho retry/UNKNOWN commit |

**Federation không phải mirror:** forward một message từ queue B đến consumer ở A không nhất thiết tạo **hai bản công việc độc lập**. **Mirror không phải HA replication:** giữ một bản sự kiện ở broker B không khiến B mặc nhiên được bầu làm primary thay A, cũng không tạo một giao dịch commit nguyên tử giữa hai broker. **HA replication không phải cân tải active-active** trên cùng queue.

### Ba câu hỏi trước khi chọn

1. **Cần người tiêu thụ ở vùng khác lấy việc từ broker gốc?** Ưu tiên đánh giá **queue federation**.
2. **Cần subscription topic ở vùng khác nhận message khi có demand?** Đánh giá **address federation**.
3. **Cần broker dự phòng giữ state để có thể tiếp quản một primary khi sự cố?** Đánh giá **HA replication**; nếu cần thêm bản lưu độc lập ở vùng DR, xem xét **AMQP Mirror** nhưng phải thiết kế cutover/reconciliation.

Một kiến trúc lớn có thể dùng nhiều cơ chế ở các lớp khác nhau, nhưng **không nên bật federation + mirror cho cùng luồng địa chỉ mà chưa phân tích duplicate, ACK, loops và ownership**.

## 3. Federation: broker nào mở kết nối, nơi nào có demand?

Federation của Artemis gồm các **federation upstream/downstream definitions** và **address/queue policies**. Ở ví dụ dễ hiểu nhất, broker **A** có consumer local và muốn lấy message từ broker **B**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Inventory consumer tại A
    participant A as Broker A (downstream consumer side)
    participant B as Broker B (upstream source)
    participant P as Producer gửi tới B

    C->>A: Consume orders.work
    A->>B: Federation link + demand theo policy
    P->>B: Send OrderPaid E1 tới orders.work
    B-->>A: Chuyển E1 qua federated consumer/link
    A-->>C: Dispatch E1
    C-->>A: Commit JMS ACK
    A-->>B: Hoàn tất chuyển tiếp theo protocol
~~~

Cần hiểu **consumer ở A** là nguyên nhân tạo nhu cầu; A mở một upstream federation tới B. Khi consumer A dừng, demand có thể được thu hồi, làm giảm luồng message chuyển từ B. Không đồng nghĩa queue B bị xóa hoặc mọi message cũ phải copy sang A.

### Queue federation khác address federation ở đâu?

| Nội dung | Queue federation | Address federation |
| --- | --- | --- |
| Demand | Consumer trên queue local phù hợp policy | Binding/subscription local trên address phù hợp policy |
| Mục tiêu | Phân phối **work queue** qua brokers | Đưa dữ liệu **address/MULTICAST** tới subscriber remote |
| Message | Có tính chất chuyển/giao công việc qua queue, không phát thêm một bản nghiệp vụ cho mỗi vùng theo mặc định | Có thể có nhiều queue subscription nhận bản phân phối tương ứng |
| Policy cần định nghĩa | Queue + address match, consumer priority/hops theo hỗ trợ | Address match, hop control, divert bindings theo hỗ trợ |
| Lưu ý | Không đồng nhất queue federation với queue mirror | Không đồng nhất multicast federation với durable subscription được tạo sau publish |

Một Artemis **address** có routing type **ANYCAST/MULTICAST**; một **queue** là nơi giữ message cho consumer. Policy federation chọn **địa chỉ và queue phù hợp**; nó không biến mọi queue ở mọi broker thành một bản replica đồng bộ.

## 4. Lab queue federation: tiêu thụ ở A, gửi công việc vào B

Giả sử A dùng cổng Artemis Core **61616**, B dùng **61626** trên cùng máy lab; B mở một acceptor Core và A có **connector** trỏ đến B. Cả hai broker đã tạo queue **orders.work** kiểu ANYCAST. Dùng **hai broker instances thực sự khác nhau**, với data directories, ports và node IDs riêng. Không khởi động hai broker cùng trỏ vào một journal folder.

### 4.1. Broker B: queue và acceptor

Các đoạn XML minh họa ghép **đúng vào phần tương ứng của broker.xml** (không phải file hoàn chỉnh):

~~~xml
<!-- B: trong acceptors -->
<acceptor name="core-b">tcp://0.0.0.0:61626?protocols=CORE</acceptor>

<!-- B: trong addresses -->
<address name="orders.work">
  <anycast>
    <queue name="orders.work" durable="true"/>
  </anycast>
</address>
~~~

**B** là upstream source của A. Khi Artemis bật security, user của federation cần được broker B xác thực và ủy quyền các thao tác tiêu thụ/management cần thiết theo cấu hình. Ví dụ để minh họa routing, không được mở broker production không xác thực.

### 4.2. Broker A: queue local, connector tới B và queue policy

~~~xml
<!-- A: trong connectors -->
<connector name="broker-b-core">tcp://broker-b.internal:61626</connector>

<!-- A: trong addresses -->
<address name="orders.work">
  <anycast>
    <queue name="orders.work" durable="true"/>
  </anycast>
</address>

<!-- A: trong federations -->
<federation name="orders-queue-fed">
  <upstream name="from-b">
    <static-connectors>
      <connector-ref>broker-b-core</connector-ref>
    </static-connectors>
    <policy ref="orders-work-policy"/>
  </upstream>

  <queue-policy name="orders-work-policy"
                include-federated="false"
                priority-adjustment="-1">
    <include address-match="orders.work" queue-match="orders.work"/>
  </queue-policy>
</federation>
~~~

**Các khối này nằm trong đúng parent XML**: connector trong **connectors**, address trong **addresses**, federation trong **federations** theo schema của release Artemis. Chúng không thể được dán nối tiếp trực tiếp vào root broker.xml ngoài các phần tử cha. Vì tên và thuộc tính federation có thể thay đổi giữa các phiên bản Artemis, phải kiểm tra schema/khả năng của **release đang triển khai** và thử broker khởi động lại trong lab trước khi vận hành.

Giải thích:

- **connector broker-b-core** là đường từ A tới B. Trong container, hostname phải resolve tới broker B, không tự dùng localhost nếu A/B ở container khác.
- **upstream from-b** biểu thị A kết nối ngược tới nguồn B để lấy message khi có nhu cầu.
- **policy** giới hạn address+queue theo tên đã chọn, không mở rộng tới mọi queue của broker.
- **include-federated=false** ngăn tính demand liên hợp đã được tạo bởi federation như demand nội sinh theo cách policy hỗ trợ; hữu ích giảm vòng chuyển tiếp.
- **priority-adjustment=-1** là điều chỉnh priority của consumer federation so với consumer local theo cơ chế Artemis; giúp tránh việc link chiếm quyền phân phối không mong muốn, **không phải** JMSPriority của message.

**Không bật federation hai chiều với cùng queue mặc định.** Nếu mỗi broker đồng thời kéo từ broker kia mà không quản lý hop/demand/origin, có thể hình thành luồng vòng hoặc tranh chấp distribution, đặc biệt khi bổ sung cluster/bridge/mirror.

### 4.3. Bài thử đúng ý nghĩa queue federation

1. Tạo consumer trên **queue orders.work của broker A** trước, kiểm tra nó đã đăng ký.
2. Chờ Artemis quản lý federation và tạo demand/upstream consumer ở broker B (quan sát broker management; không suy liên kết sẵn sàng chỉ từ TCP open).
3. Gửi **OrderPaid E1** vào **queue orders.work của broker B** bằng JMS.
4. Consumer tại A phải có thể nhận E1 và ACK; kiểm tra queue B/A theo trạng thái message thực tế.
5. Dừng consumer A, gửi E2 vào B; xem E2 được giữ ở queue B như thế nào khi không còn demand phù hợp.
6. Khởi động lại consumer A, xác minh E2 có thể được phân phối sau khi federation khôi phục demand.

**Đừng xem queue B giảm một message và A nhận được message là “mirror đã nhân đôi”**; queue federation phục vụ chuyển tiếp công việc. Và đừng kết luận một message chưa xuất hiện ở A là “mất dữ liệu” nếu demand/subscription chưa được thiết lập hoặc policy chưa match.

### 4.4. Khi nào không nên dùng queue federation?

Nếu cần giữ **một bản đầy đủ, độc lập có thể replay** ở mỗi vùng, queue federation không đáp ứng mục tiêu đó như một chính sách sao lưu. Nếu hai vùng phải xử lý **hai side effects khác nhau** từ cùng một event, dùng topic/multicast subscriptions riêng theo business boundary hoặc address federation với binding cụ thể, thay vì biến queue work thành broadcast bằng một policy không rõ.


## 5. Address federation: phục vụ subscriber ở broker khác

Queue federation có điểm xuất phát là **work queue**. Với thông điệp sự kiện **OrderPaid** cần được các dịch vụ Audit/Notification ở nhiều vùng xử lý độc lập, mô hình **MULTICAST address federation** có mục tiêu khác: mỗi queue/subscription phù hợp giữ một bản phân phối của event, nhưng luồng chuyển giữa brokers được điều khiển bởi **demand và policy**.

Giả sử:

~~~text
Broker B:
  address orders.events (MULTICAST)
    queue b.local.audit

Broker A:
  address orders.events (MULTICAST)
    queue a.notification.events
      ↓ consumer Notification tại A

Federation tại A:
  upstream = B
  address-policy match orders.events
~~~

Producer phát một event tới address/topic ở B. Nếu A đã có binding/subscriber phù hợp và federation đã thiết lập demand, message có thể được đưa qua link để queue subscriber ở A nhận. **Không có demand ở A** hoặc policy exclude address thì không có cam kết broker B sẽ chuyển mọi message lịch sử sang A.

### XML minh họa ở A

~~~xml
<!-- A: trong connectors -->
<connector name="broker-b-core">tcp://broker-b.internal:61626</connector>

<!-- A: trong addresses -->
<address name="orders.events">
  <multicast>
    <queue name="a.notification.events" durable="true"/>
  </multicast>
</address>

<!-- A: trong federations -->
<federation name="orders-address-fed">
  <upstream name="from-b-events">
    <static-connectors>
      <connector-ref>broker-b-core</connector-ref>
    </static-connectors>
    <policy ref="orders-events-policy"/>
  </upstream>
  <address-policy name="orders-events-policy" max-hops="1">
    <include address-match="orders.events"/>
  </address-policy>
</federation>
~~~

Broker B cần có MULTICAST address **orders.events** và acceptor/permissions tương ứng. Nếu queue/subscription cần giữ backlog khi consumer offline, hãy tạo **durable queue/subscription** trước khi producer phát message; một **non-durable subscriber tạo sau publish** không được tự động replay toàn bộ message nhờ federation.

**max-hops** giới hạn mức lan truyền của message đã đi qua address federation để giảm đường vòng trong topology phức tạp. Nó **không phải** TTL của JMS message và **không thể thay thế** việc thiết kế topology có hướng, theo dõi origin và chọn policy. Trong nhiều phiên bản Artemis có các tùy chọn như **enable-divert-bindings**, **auto-delete**; chỉ bật khi hiểu rõ binding/demand và schema cụ thể.

### Không làm bài thử sai mô hình

Nếu producer gửi vào queue ANYCAST **orders.work** nhưng policy là address MULTICAST **orders.events**, không thể trông đợi queue subscriber A nhận. Cần xác nhận **address, routing type, queue binding, policy match và consumer demand** đều đúng, thay vì chỉ nhìn hai broker đã có TCP connection.

**Đặc biệt:** address federation có thể tạo nhiều bản phân phối ở các queue subscriber theo semantics MULTICAST, nhưng đó **không phải bản sao HA journal**. Nó phục vụ tiêu thụ sự kiện, không bảo đảm hoàn toàn tương đương khi failover primary/backup.

## 6. AMQP Mirror: phản chiếu sự kiện giữa các broker độc lập

AMQP Mirror của Artemis dùng **AMQP broker connection**, khác với Core federation. Một broker nguồn ghi nhận những thao tác liên quan message/address/queue, rồi truyền thông tin mirror đến broker đích để cập nhật một phần trạng thái bên đích theo tính năng và policy đang bật.

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Producer
    participant A as Broker A (source)
    participant Q as Local state A
    participant L as AMQP mirror link
    participant B as Broker B (target)

    P->>A: Send E1 vào orders.events
    A->>Q: Lưu/routing message theo local transaction
    A->>L: Mirror record cho operation
    L->>B: AMQP transfer
    B->>B: Áp dụng message/resource operation
    Note over A,B: Không phải một global JMS transaction
    opt Source message ACK được mirror theo policy
        A->>L: Acknowledgement event
        L->>B: Phản chiếu acknowledgement
    end
~~~

**Đừng hiểu là cứ có mirror thì A và B đều giữ mỗi message vô thời hạn.** Nếu cấu hình phản chiếu ACK và việc tiêu thụ ở A làm trạng thái bên B được cập nhật, message có thể không còn là bản backlog tự do replay sau khi ACK. Ngược lại, nếu không phản chiếu ACK, target có thể giữ message lâu hơn nguồn. Mục tiêu DR, audit và phục hồi sẽ quyết định policy nào đúng.

### AMQP Mirror khác queue federation thế nào?

- **Federation** hỏi: “Broker bên kia có demand nào cần phục vụ?”.
- **Mirror** hỏi: “Những operation/state nào phải được phản chiếu sang broker bên kia?”.
- Queue federation có thể **chuyển công việc để một consumer remote xử lý**; mirror có thể **tạo bản trạng thái tương ứng trên broker đích**.
- Mirror là cấu hình **nguồn → đích**; thêm chiều ngược lại cần quy tắc chống loop/duplicate và ownership rõ ràng, không được coi là active-active strong consistency.

### Broker B: AMQP acceptor

Trên broker B, trong phần **acceptors**:

~~~xml
<acceptor name="amqp-for-mirror">tcp://0.0.0.0:5673?protocols=AMQP</acceptor>
~~~

Port **5673** chỉ là port lab để phân biệt với 5672 mặc định. Broker B phải chạy Artemis release hỗ trợ nhận AMQP mirror, chấp nhận connection từ A và có quyền tạo/ghi/xóa tài nguyên theo policy. Trong sản phẩm thật, dùng **TLS/mTLS** hoặc kênh mạng đã được kiểm soát tương ứng, không để một acceptor không bảo vệ mở ra Internet.

### Broker A: AMQP broker connection và mirror

Trong phần **broker-connections** của **broker.xml** A, ví dụ tối thiểu:

~~~xml
<broker-connections>
  <amqp-connection name="mirror-a-to-b"
                   uri="tcp://broker-b.internal:5673">
    <mirror/>
  </amqp-connection>
</broker-connections>
~~~

Đoạn này **phải ghép vào đúng cấu trúc broker.xml**, không tạo thêm một **broker-connections** thứ hai nếu file đã có block tương ứng. Kết nối cần authentication/authorization và TLS theo môi trường. **Tên phần tử và các tùy chọn mirror phải được xác minh theo release Artemis**; broker phải hỗ trợ AMQP Mirror, không chỉ AMQP 1.0 nói chung.

Ở các release hỗ trợ, mirror có các tùy chọn điều khiển loại operation được phản chiếu, ví dụ:

~~~xml
<mirror>
  <message-acknowledgements>true</message-acknowledgements>
  <queue-creation>true</queue-creation>
  <queue-removal>true</queue-removal>
</mirror>
~~~

Đây là **đoạn thay thế phần tử mirror trống**, không chèn cả hai vào cùng connection. Các default và khả năng cấu hình **address creation/removal, sync, filter** có thể khác theo Artemis release; không bật/đoán option mới từ tài liệu phiên bản khác. Quan trọng nhất là quyết định **có phản chiếu ACK và deletion hay không**, vì nó ảnh hưởng trạng thái dữ liệu ở DR.

### Trạng thái mục tiêu không phải backup passive

Broker B của mirror có thể đang phục vụ client riêng theo chính sách vận hành; **nó không tự được bầu làm HA backup** của A. Nếu A hỏng và muốn dùng B làm DR, phải có **quy trình ứng dụng đổi endpoint, dừng/khóa writers cũ, đánh giá mirror lag và reconcile message**. Chỉ đổi DNS khi chưa kiểm tra dữ liệu đã hội tụ có thể tạo **mất hoặc trùng event nghiệp vụ**.

## 7. Consistency và ACK: điều gì xảy ra khi mirror link đứt?

Xét producer gửi E1 vào broker A khi liên kết mirror tới B bị mất:

~~~text
T0  Producer gửi E1 vào A
T1  A commit local message
T2  AMQP mirror link A→B đang down
T3  Producer nhận thành công từ A
T4  B chưa thấy E1
T5  Link hồi phục, mirror có thể chuyển backlog theo state và policy
~~~

Trong **chế độ mirror bất đồng bộ**, ACK local send ở A không chứng minh B đã nhận và persist E1. Trong các chế độ đồng bộ hoặc các tùy chọn chờ mirror confirmation được release hỗ trợ, producer latency/availability có thể phụ thuộc link remote; nhưng **không tự biến hai broker thành một transaction XA**.

| Câu hỏi | Cần chứng minh trước khi tuyên bố đạt |
| --- | --- |
| Producer nhận JMS commit success ở A, B đã bền vững chưa? | Mirror sync mode, remote acknowledgement/persistence và broker metrics thực tế |
| Link đứt, message mirror giữ ở đâu? | Mirror queue/backlog, journal durability, retention và storage |
| A crash trước khi mirror E1 tới B thì sao? | E1 có trong trạng thái durable mirror backlog hay không |
| E1 đã ACK ở A, trạng thái B ra sao? | Đã bật mirror acknowledgements? ACK operation đến B lúc nào? |
| Queue xóa ở A thì B còn dữ liệu không? | Queue removal policy, retention/DR policy |
| Link khôi phục và operation được gửi lại? | Duplicate handling, idempotency và ordering |
| Mirror B chuyển từ DR sang active? | Cutover/fencing, ownership writes và reconciliation |

**Không lấy độ sâu queue ứng dụng ở B làm thước đo duy nhất của mirror lag.** Message có thể đã được consume/ACK, trong khi operation backlog của mirror vẫn đang đi qua link. Cần số liệu của **AMQP connection, mirror-related resources, journal/disk, message add/ack và eventId đối soát**.

### Bẫy ACK quan trọng

Một số hệ thống vận hành kỳ vọng DR broker là “bản sao còn tất cả message từng gửi”. Nếu mirror phản chiếu ACK, B có thể theo trạng thái đã tiêu thụ của A, nên **không còn các message đã ACK**. Nếu muốn audit/replay toàn bộ sự kiện, dùng **event log/outbox/audit topic hoặc kho lưu trữ dữ liệu nghiệp vụ riêng**, không dựa vào một mirror queue với ACK propagation mà chưa hiểu policy.

### Mirror không thay thế idempotent consumer

Nếu producer thấy commit timeout rồi retry, có thể phát sinh **hai bản gửi nghiệp vụ cùng eventId**. Mirror có thể phản chiếu cả hai; dù broker có duplicate detection hoặc cơ chế loop avoidance, không nên tuyên bố exactly-once cho side effect DB/HTTP. Consumer ở mỗi vùng phải có **eventId ổn định** và unique constraint/inbox nếu kết quả nghiệp vụ không được lặp.

## 8. HA replication: primary, backup, quorum và activation

HA replication của Artemis là thiết kế **một broker primary đang hoạt động và một hoặc nhiều backup theo topology HA**, với trạng thái cần thiết được đồng bộ để backup có thể tiếp quản khi sự cố xảy ra. Backup thông thường **không đồng thời phục vụ consumer cho cùng một queue logic** như một broker active độc lập.

~~~mermaid
sequenceDiagram
    participant C as JMS client
    participant P as Primary active
    participant R as Replication channel
    participant B as Backup standby
    C->>P: send E1 + commit
    P->>R: Replicate broker journal/state
    R->>B: Lưu trạng thái dự phòng
    Note over B: Không hoạt động như broker độc lập để consume cùng queue
    P--xC: Primary mất kết nối
    B->>B: HA/quorum/fencing cho phép activation
    B-->>C: Client reconnect/failover
    C->>B: Tiếp tục dùng broker logic sau takeover
~~~

**Không lấy số máy = 2 suy ra active-active.** Một primary/backup pair hướng tới **availability và state continuity** của broker logic. Để tránh **split-brain** khi network partition, cần quorum/coordination/fencing theo chế độ HA và release, đặc biệt khi triển khai qua nhiều vùng mạng.

### HA replication sao chép loại state nào?

Mục tiêu là giữ state broker cho failover: journal/message persistence, durable queues/ACK và các thành phần storage cần thiết theo HA protocol. Việc **nội dung nào được replicate và khi nào được coi là committed** phụ thuộc chế độ HA, journal synchronization và bản Artemis. Không phát biểu “mọi JMS send trên primary luôn có 100% dữ liệu trên backup” khi chưa kiểm tra policy, thời điểm đồng bộ và tình trạng quorum.

### Minh họa ha-policy theo vai trò

Trong phần **ha-policy** của broker.xml của primary ở những bản Artemis dùng cấu trúc replication primary/backup:

~~~xml
<ha-policy>
  <replication>
    <primary>
      <check-for-active-server>true</check-for-active-server>
    </primary>
  </replication>
</ha-policy>
~~~

Ở broker backup:

~~~xml
<ha-policy>
  <replication>
    <backup>
      <allow-failback>true</allow-failback>
    </backup>
  </replication>
</ha-policy>
~~~

**Hai đoạn này phải ở hai broker khác nhau**, thay vào đúng **ha-policy** hiện hữu, không dán chung. Chúng **không đủ để tạo một cụm HA chạy được**: còn cần **cluster connections/discovery hoặc static connectors, authentication, node identity, quorum/failover policy, journal directories, fencing/lock coordination** và cấu hình phù hợp release. Đừng chạy hai broker cùng dùng chung journal directory chỉ vì đang thử replication.

Tên primary/backup và cấu trúc XML đã thay đổi trong lịch sử Artemis (các bản cũ có tên khác); phải xác nhận **schema phiên bản cụ thể** trước khi áp dụng. Với môi trường không có cơ chế quorum/fencing đúng, backup tự kích hoạt trong partition có thể dẫn tới **split-brain**, nguy hiểm hơn một outage ngắn.

### Backup activation không phải mirror promotion

Khi primary mất, một backup được HA protocol cho phép **activate** và trở thành broker đang phục vụ. Với AMQP Mirror, B là **broker độc lập**; việc chuyển ứng dụng sang B là quyết định **DR cutover** cần orchestration riêng. Tương tự, federation chỉ tạo đường chuyển message khi demand tồn tại, không tự bầu broker nào là primary của broker khác.


## 9. Java/JMS lab: chứng minh queue federation khác mirror

Ta sẽ sử dụng **hai broker độc lập A và B**, **không bật HA replication trong cùng phép thử**, để kiểm chứng hai luồng:

- **queue-federation**: producer gửi message vào **B:orders.work**, consumer nhận ở **A:orders.work** theo demand/policy.
- **mirror**: producer gửi message vào **A:orders.mirror.lab**, consumer nhận ở **B:orders.mirror.lab** sau khi operation được mirror từ A sang B.

Hai queue lab này **tách riêng**, tránh việc bật cùng một routing/mirror policy gây khó xác định message đến từ cơ chế nào. Với mirror, tạo sẵn **queue ANYCAST orders.mirror.lab** ở cả A và B để bài thử tập trung vào message propagation, không phụ thuộc cơ chế tự tạo resource của mirror.

### 9.1. Môi trường và queue

Artemis A listen Core tại **127.0.0.1:61616**, Artemis B tại **127.0.0.1:61626**; nếu chạy Docker, tùy host-port mapping phải thay URL và connector nội bộ như mục 4. Broker B cũng cung cấp **AMQP 5673** cho mirror; JMS Java probe bên dưới dùng **Core** ở 61616/61626.

Queue bổ sung cho phép thử mirror, cấu hình trong phần **addresses** của **cả A và B**:

~~~xml
<address name="orders.mirror.lab">
  <anycast>
    <queue name="orders.mirror.lab" durable="true"/>
  </anycast>
</address>
~~~

**Không áp dụng đồng thời federation policy cho orders.mirror.lab** trong phép thử này. Nếu broker/AMQP Mirror có policy phản chiếu việc tạo queue, việc tạo sẵn queue có thể phát sinh operation quản trị: kiểm tra logs và các lựa chọn queue creation trước khi chạy. Để lab tái lập, khởi tạo resource trước rồi chỉ quan sát việc gửi/nhận message.

### 9.2. Maven

Dùng **JDK 17+**, Maven và Artemis Jakarta client. POM minh họa:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.messaging</groupId>
  <artifactId>artemis-multi-broker-probe</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.42.0</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Đây là dependency tham chiếu cho ví dụ API, phải chọn bản tương thích với phiên bản Artemis/Java thực tế. Đừng đưa **ActiveMQ Classic javax.jms client** vào cùng source đang import **jakarta.jms**.

### 9.3. Chương trình MultiBrokerProbe.java

Tạo **src/main/java/MultiBrokerProbe.java** trong Maven project lab của người học:

~~~java
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

import java.util.Objects;
import java.util.UUID;

public final class MultiBrokerProbe {
    public static void main(String[] args) throws Exception {
        String mode = System.getenv().getOrDefault(
                "LAB_MODE", "queue-federation");
        String brokerA = System.getenv().getOrDefault(
                "BROKER_A", "tcp://127.0.0.1:61616");
        String brokerB = System.getenv().getOrDefault(
                "BROKER_B", "tcp://127.0.0.1:61626");
        String user = required("BROKER_USER");
        String password = required("BROKER_PASSWORD");
        String runId = UUID.randomUUID().toString();

        String sourceUrl;
        String targetUrl;
        String destination;

        if ("queue-federation".equals(mode)) {
            // A có consumer; federation của A lấy từ B theo demand.
            sourceUrl = brokerB;
            targetUrl = brokerA;
            destination = "orders.work";
        } else if ("mirror".equals(mode)) {
            // Mirror A -> B: send A, nhận message được mirror ở B.
            sourceUrl = brokerA;
            targetUrl = brokerB;
            destination = "orders.mirror.lab";
        } else {
            throw new IllegalArgumentException(
                    "LAB_MODE must be queue-federation or mirror");
        }

        ActiveMQConnectionFactory sourceFactory =
                new ActiveMQConnectionFactory(sourceUrl);
        ActiveMQConnectionFactory targetFactory =
                new ActiveMQConnectionFactory(targetUrl);

        try (JMSContext sender = sourceFactory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED);
             JMSContext receiver = targetFactory.createContext(
                     user, password, JMSContext.SESSION_TRANSACTED)) {

            Queue targetQueue = receiver.createQueue(destination);

            // Tạo local consumer trước khi send để queue federation
            // có cơ hội đăng ký demand với upstream broker.
            JMSConsumer consumer = receiver.createConsumer(targetQueue);

            if ("queue-federation".equals(mode)) {
                System.out.println("Check federation demand on broker B.");
                // Sleep chỉ giúp demo; readiness thực phải theo management.
                Thread.sleep(3_000L);
            }

            String eventId = "lab-" + runId;
            Queue sourceQueue = sender.createQueue(destination);

            TextMessage outbound = sender.createTextMessage(
                    "OrderPaid:" + eventId);
            outbound.setStringProperty("eventId", eventId);
            outbound.setStringProperty("labRun", runId);

            sender.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(0L)
                    .send(sourceQueue, outbound);
            sender.commit();

            Message received = consumer.receive(30_000L);
            if (received == null) {
                throw new IllegalStateException(
                        "No message. Inspect broker connection, policy,"
                        + " demand, mirror lag, queue routing and ACL.");
            }

            String observed = received.getStringProperty("eventId");
            if (!eventId.equals(observed)) {
                throw new IllegalStateException(
                        "Unexpected message eventId=" + observed
                        + "; clean the dedicated lab queue first");
            }

            System.out.printf(
                    "PASS mode=%s source=%s target=%s eventId=%s"
                    + " JMSMessageID=%s%n",
                    mode, sourceUrl, targetUrl,
                    observed, received.getJMSMessageID());

            receiver.commit();
        }
    }

    private static String required(String name) {
        return Objects.requireNonNull(
                System.getenv(name), "Missing env variable: " + name);
    }
}
~~~

**Lưu ý về phép thử:**

- Consumer tạo trước send để kích hoạt **demand** trong queue federation. **Thread.sleep(3 giây)** chỉ phục vụ demo; nếu link handshake hoặc discovery chậm hơn, test vẫn có thể time out. Trong kiểm thử nghiêm túc, chờ **consumer federation thực sự xuất hiện ở B** qua management thay vì chỉ sleep.
- Producer dùng **PERSISTENT** và **SESSION_TRANSACTED**; nó xác nhận send với **broker nguồn**, không phải một transaction chung A+B.
- Consumer **commit JMS** sau khi kiểm tra **eventId**; nếu app crash trước commit, message có thể redeliver theo policy và phải có idempotency ở business handler.
- Demo không cấu hình TLS/mTLS, HA, JMS selector, consumer concurrency hay service DB; nó chỉ chứng minh đường đi qua hai broker theo policy đã đặt.
- **Không chạy cùng lúc hai mode trên cùng địa chỉ** hoặc cùng queue có backlog không kiểm soát. Một message tồn cũ có thể làm test đọc nhầm; dùng queue chuyên dụng, quan sát message count và dọn đúng queue lab.
- Nếu mirror B có logic phản chiếu ACK từ A, đừng tạo thêm consumer A để “so sánh” trong lúc test B; consumption/ACK tại A có thể thay đổi state bên B trước khi bạn nhận.

### 9.4. Chạy theo mode

PowerShell:

~~~powershell
$env:BROKER_A = "tcp://127.0.0.1:61616"
$env:BROKER_B = "tcp://127.0.0.1:61626"
$env:BROKER_USER = "artemis_app"
$env:BROKER_PASSWORD = "<your-jms-password>"

$env:LAB_MODE = "queue-federation"
mvn -q compile exec:java "-Dexec.mainClass=MultiBrokerProbe"

$env:LAB_MODE = "mirror"
mvn -q compile exec:java "-Dexec.mainClass=MultiBrokerProbe"
~~~

**Chỉ chạy mode tương ứng với topology broker đã cấu hình tại thời điểm đó.** Để test mirror, tạm gỡ/đóng policy federation trùng đích và dùng AMQP connection A→B; để test queue federation, không cần mirror. Broker B có thể cần separate credentials cho federation/mirror link, ngoài credentials Java gửi/nhận; cấu hình đúng security manager, không dùng tài khoản admin mặc định trên môi trường thật.

Dòng console kỳ vọng:

~~~text
PASS mode=queue-federation source=tcp://...61626 target=tcp://...61616 eventId=lab-...
PASS mode=mirror source=tcp://...61616 target=tcp://...61626 eventId=lab-...
~~~

Đây là **kỳ vọng kiểm thử, không phải output đã chạy**. Nó chứng minh message ở đúng endpoint theo mode trong lab; muốn đánh giá DR, ordering, ACK propagation và catch-up cần các thí nghiệm riêng ở phần sau.


## 10. ACK, ordering, redelivery và transaction qua ranh giới broker

Mỗi mode có **ranh giới sở hữu message** khác nhau; vì vậy cách đọc ACK hoặc số lượng message phải bám theo luồng dữ liệu.

| Tình huống | Federation | AMQP Mirror | HA Replication |
| --- | --- | --- | --- |
| Producer commit thành công ở broker gốc | Message được broker gốc xác nhận theo JMS | Message được broker nguồn xác nhận; đích có thể còn lag | Primary xác nhận theo HA/journal protocol |
| Consumer ở vùng khác xử lý | Demand/link chuyển message giữa broker; ACK cần hoàn tất theo forwarding protocol | Consumer có thể đọc copy/state ở broker độc lập theo policy | Sau backup activation, client đọc broker đã tiếp quản |
| Consumer rollback | Message có thể redeliver qua federation hoặc từ broker nguồn tùy thời điểm | ACK/operation replication và local delivery riêng cần được đánh giá | Redelivery sau failover theo trạng thái ACK đã bền vững |
| Mất mạng đúng lúc commit ACK | Outcome có thể chưa rõ, cần idempotency | Outcome local và mirror remote có thể lệch tạm thời | Outcome commit ở primary/backup cần xem như UNKNOWN nếu client mất response |
| Thứ tự message | Có thể đổi do nhiều broker/consumers/demand | Link/operation lag và nhiều nguồn viết ảnh hưởng thứ tự | Trạng thái broker phục vụ failover; không hứa business completion order |
| Exactly-once DB/HTTP | Không | Không | Không |

### 10.1. EventId là khóa nghiệp vụ, JMSMessageID là dấu vết transport

Một ứng dụng phát **OrderPaid** với **eventId=payment-ORD-812-v1**. Nếu producer timeout sau commit và retry, hai JMS messages có thể có **JMSMessageID khác nhau** nhưng cùng eventId. Khi đi qua federation hoặc mirror, việc chỉ deduplicate theo JMSMessageID có thể bỏ sót trùng nghiệp vụ.

Ví dụ schema inbox ở consumer PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong **cùng DB transaction**: insert inbox marker nếu mới, thực hiện side effect, commit; sau đó ACK/commit JMS. Nếu message được giao lại nhưng marker đã tồn tại, không làm side effect lần nữa. Tách **consumer_name** để Inventory và Audit đều có thể xử lý cùng event độc lập.

### 10.2. Queue federation không đồng nghĩa two-phase commit

Một federated consumer nhận message từ broker B rồi đưa đến A phải xử lý các trường hợp connection lỗi, ACK thất lạc hoặc remote/local transaction không cùng một phạm vi. **Không tự suy** local JMS Session.commit ở A có nghĩa một giao dịch phân tán hai broker và DB đã commit nguyên tử. Kiểm tra tính bền vững và cách protocol quản lý redelivery trên release đang dùng.

Nếu yêu cầu ràng buộc ngân hàng kiểu “một giao dịch phải commit đồng thời ở DB và hai broker”, federation hoặc mirror không tự đáp ứng XA/2PC. Xem xét outbox/inbox hoặc transaction coordinator được hỗ trợ, cùng reconciliation.

### 10.3. Thứ tự và message grouping

Với nhiều broker, nhiều consumers và các link có độ trễ khác nhau, **thứ tự enqueue ở nguồn không nhất thiết là thứ tự hoàn tất nghiệp vụ** ở tất cả vùng. **JMSXGroupID** có thể giúp giữ một chuỗi công việc trên một consumer trong phạm vi broker/grouping policy, nhưng không phải bảo đảm thứ tự toàn cầu khi message đi qua federation/mirror hoặc khi failover.

Dùng **aggregateId + sequenceVersion**:

~~~json
{
  "eventId": "payment-ORD-812-v3",
  "aggregateId": "ORD-812",
  "sequence": 3,
  "eventType": "OrderPaid"
}
~~~

Consumer so version trong DB, xử lý trùng/đến muộn một cách có chủ đích. Đặc biệt, đừng tăng số worker sau sự cố rồi mặc định “cùng queue bảo đảm mọi OrderPaid luôn xử lý tuần tự” khi không có quy tắc grouping/state.

## 11. Mirror DR cutover khác HA failover: RPO, RTO và fencing

Các thuật ngữ:

- **RPO**: lượng dữ liệu tối đa có thể mất/chưa hội tụ tại thời điểm chuyển đổi, tính theo thời gian hoặc số event được chấp nhận.
- **RTO**: thời gian tối đa để dịch vụ hoạt động trở lại sau sự cố.
- **Fencing**: cơ chế ngăn broker/writer cũ tiếp tục ghi sau khi điểm đích trở thành nguồn sự thật, tránh hai phía cùng nhận dữ liệu trái nhau.
- **Catch-up**: mirror link xử lý backlog operation/message còn chờ, đưa trạng thái target tiến gần source theo policy.

### Mirror DR: cần một quy trình rõ

~~~mermaid
flowchart TD
    DETECT["Phát hiện broker A không thể phục vụ"] --> STOP["Ngăn writers cũ hoặc fence A"]
    STOP --> CHECK["Đối soát B: mirror lag, event IDs, queue/resource state"]
    CHECK --> DEC{"B đủ điều kiện activate cho ứng dụng?"}
    DEC -->|Chưa| FIX["Khôi phục mirror/reconcile/backup theo RPO"]
    DEC -->|Đủ| SWITCH["Đổi JMS endpoints / discovery đến B"]
    SWITCH --> VERIFY["Canary send/consume, ACK, authorization"]
    VERIFY --> OPERATE["B trở thành nguồn phục vụ theo runbook"]
    OPERATE --> REVERSE["Kế hoạch tái đồng bộ và failback có kiểm soát"]
~~~

Nếu **A không truy cập được do partition**, rất có thể A vẫn đang nhận writes ở phía mạng khác. Chỉ đổi DNS hoặc restart A/B mà không fencing có thể làm **hai broker cùng nhận writes**, gây diverging state. Mirror được cấu hình hai chiều không tự giải quyết conflict như một cơ sở dữ liệu multi-master mạnh.

Một DR runbook tối thiểu:

1. Khóa nguồn ghi cũ hoặc xác nhận fencing qua cơ chế quản lý hạ tầng.
2. Đánh giá **mirror link last-seen, backlog/lag, journal health** và sự hội tụ của các event quan trọng.
3. Nếu RPO không đạt, cân nhắc chờ source phục hồi hoặc dùng outbox/replay có kiểm soát để bù thiếu.
4. Chuyển JMS ConnectionFactory endpoint của ứng dụng theo chiến lược đã thử; tạo connection/session mới an toàn với commit outcomes UNKNOWN.
5. Thử send/consume bằng eventId mới, kiểm tra destination permissions và idempotent consumers.
6. Khi A phục hồi, **không cho A tự nhận writes như cũ** trước khi có chiến lược reconcile và mirror direction rõ.
7. Chỉ failback sau khi đã đối soát, đưa dữ liệu về trạng thái hội tụ và gỡ writer fencing đúng thứ tự.

### HA replication: activation do HA protocol quyết định

Trong một HA pair được cấu hình đúng, broker backup có thể được protocol cho phép **activate** khi primary mất. Client có thể reconnect/failover theo topology/connector phù hợp. Tuy nhiên, **HA không thay thế ứng dụng xử lý commit outcome UNKNOWN**, và RPO/RTO thực tế còn phụ thuộc journal sync, quorum, detection timeout, fencing, client retry và hạ tầng.

**Hai máy không tự tạo quorum an toàn.** Nếu primary và backup không nhìn thấy nhau do partition, cả hai có thể cho rằng phía kia chết nếu cấu hình sai. Đánh giá voting nodes, distributed lock manager hoặc cơ chế chống split-brain phù hợp **chế độ replication/phiên bản Artemis** đang dùng.

### Queue federation không phải DR cutover

Với federation, A và B độc lập ngay từ đầu; việc consumer A kéo việc từ B là một **routing decision**. Khi B chết, federation không tự biến A thành bản sao hoàn chỉnh của mọi queue/trạng thái đã có ở B. Nếu yêu cầu khôi phục backlog chưa chuyển, phải có persistence/DR source khác. Mỗi queue chỉ chứa những message được route theo demand và các lần commit thành công.

## 12. Bảo mật và vận hành nhiều liên kết broker

### 12.1. Bảo vệ từng link, không chỉ JMS client

| Đường kết nối | Điều phải bảo vệ |
| --- | --- |
| Java producer/consumer → broker A/B | TLS/mTLS khi phù hợp, CA/SAN, role send/consume, credential rotation |
| Federation A ↔ B | Authentication/authorization của federated consumer, TLS và tên broker thật |
| AMQP Mirror A → B | AMQP broker connection authentication, TLS server identity, quyền tạo/ghi/ACK resource cần thiết |
| HA replication/cluster link | TLS/cluster authentication, node identity, quorum/lock, network isolation |
| Broker management API/JMX | RBAC, mTLS, không mở public, audit thao tác purge/delete/activate |

Một mTLS handshake hợp lệ trên link broker **không tự cấp quyền JMS** để tạo/xóa queue. Trên Artemis, phân quyền security settings cần cho phép chính xác các operation mirror/federation được sử dụng, không cấp quyền quản trị toàn broker chỉ để “sửa lỗi kết nối”.

### 12.2. Những metric phải xem theo từng cơ chế

| Cơ chế | Chỉ số hữu ích | Đừng suy từ |
| --- | --- | --- |
| Queue federation | Upstream link status, remote consumer/demand, message add/ACK từng queue, backlog age | TCP connected nghĩa là đã có demand |
| Address federation | Local bindings/subscriptions, included addresses, forwarded count/hops nếu expose, delivery lag | Queue topic ở nguồn còn message nghĩa subscriber remote được copy đầy đủ |
| AMQP Mirror | Broker connection state, operation lag/backlog, mirror-related queue/storage, send/ACK/resource operations | Một queue ở B có depth=0 nghĩa mirror đã đồng bộ |
| HA replication | Backup sync/activation state, journal replication health, quorum/fencing, client reconnection time | Backup process sống nghĩa backup đủ dữ liệu và có thể activate an toàn |
| Mọi cơ chế | eventId trace, message age, DLQ, disk/paging, network TLS, retry rate | Producer commit thành công nghĩa mọi consumer đã xử lý |

Có thể dùng broker console, Artemis management/JMX và exporter tùy release để lấy thông tin queue/message/connection. **Tên metric không đồng nhất giữa các phiên bản**, và một số chỉ số mirror/federation được hiển thị qua connection-specific management. Thiết kế dashboard dựa trên metric thực tế được phiên bản broker expose, không tạo tên metric tưởng tượng.

### 12.3. Capacity và failure domain

Mirror có thể thêm **I/O và network** cho mỗi send/ACK/queue operation; federation thêm **remote consumers và forwarding traffic** khi có demand; HA replication cần **băng thông và latency** đủ để duy trì trạng thái backup. Đừng dùng một link WAN chậm rồi mặc định throughput broker local giữ nguyên.

Cần dự trù:

- **Network bandwidth** theo byte payload, số queue fan-out, compression/TLS và resend.
- **Journal/disk** cho mirror backlog, paging, replication và retention.
- **Quorum/witness independence** để network partition không gây split-brain.
- **Resource ACL** cho queue create/remove và operation mirror.
- **SLO** cho thời gian replay/failover, backlog age, DLQ và độ trễ từ producer đến consumer cuối.
- **Operational ownership**: đội nào cấp chứng chỉ, rotate credentials, phục hồi mirror link và phê duyệt DR cutover.

### 12.4. Phân biệt bridge, cluster connection và federation

Artemis cũng có **Core bridge** và **cluster connections**:

- **Core bridge** chuyển message từ queue nguồn sang forwarding address đích theo cấu hình; không mặc nhiên là demand-driven federation.
- **Cluster connection** giúp một cụm Artemis nhận biết node/routing/distribution theo cấu hình; không đồng nghĩa primary/backup HA.
- **Federation** tạo routing liên-broker dựa trên policy/demand và có thể nối các broker/cụm độc lập.
- **AMQP Mirror** phản chiếu operation/state, phù hợp bài toán nhân bản có kiểm soát hơn là chia sẻ consumer demand.
- **HA replication** bảo vệ state broker cho activation của backup; không phải một rule định tuyến nghiệp vụ.

Đừng chọn một cơ chế chỉ vì nó “có thể nối hai máy”. Chọn theo **ownership, desired queue semantics, RPO/RTO và failure mode**.


## 13. Bộ thí nghiệm fault injection phải phân biệt ba cơ chế

Các bài sau chỉ chạy trên **hai hoặc nhiều broker lab riêng**, có backups và khả năng reset dữ liệu thử nghiệm. Gắn **eventId** cho mỗi message, ghi timestamp, broker ingress/egress và ACK status. Khi cố cắt mạng, chỉ dùng firewall/proxy trong lab đã được kiểm soát; không tắt kết nối thật của production.

### Thí nghiệm A — Queue federation mất consumer demand

**Chuẩn bị:** A có queue policy kéo **orders.work** từ B; consumer A được tạo trước để demand xuất hiện.

1. Gửi E1 vào B, xác minh consumer A nhận và ACK.
2. Đóng consumer A, chờ federation thu hồi demand, gửi E2 vào B.
3. Quan sát E2 ở queue nguồn B; đừng kỳ vọng A có bản sao vô điều kiện.
4. Khởi động lại consumer A; kiểm tra link/demand và E2 được nhận.
5. Đối soát eventId E1/E2, số ACK và DLQ.

**Đạt:** federation hỗ trợ work sharing khi có demand; không tự biến queue A thành một bản sao bền vững toàn bộ message của B.

### Thí nghiệm B — Address federation với hai subscribers

**Chuẩn bị:** B có address MULTICAST **orders.events**; A có queue durable **a.notification.events** và local consumer; B có local audit queue.

1. Đợi address federation policy/demand ở A được thiết lập.
2. Publish E3 tại B.
3. Xác minh local Audit B và Notification A đều có đường nhận theo queue binding phù hợp.
4. Dừng subscription A và kiểm tra lifecycle/retention của queue A; thử publish E4.
5. Tạo mới **non-durable subscription** sau E4 và xác minh không được hứa replay khi trước đó không có binding.

**Đạt:** hiểu quan hệ giữa demand, MULTICAST và queue subscription; không nhầm address federation với replication journal.

### Thí nghiệm C — AMQP mirror link đứt

**Chuẩn bị:** mirror A→B đã kết nối, message persistent trên **orders.mirror.lab**; có metric operation lag/backlog.

1. Gửi E5 khi mirror link hoạt động; xác minh B nhận sau propagation.
2. Ngắt **chỉ mirror link** A→B; giữ broker A và B vẫn chạy.
3. Gửi E6 tại A. Quan sát A local send/commit outcome và B tạm thời chưa có E6.
4. Khôi phục link. Đợi mirror reconnect/catch-up, xác minh trạng thái B bằng eventId.
5. Lặp với broker A crash ở các điểm trước/sau khi operation mirror được lưu bền; ghi lại trường hợp không hội tụ và giới hạn RPO của cấu hình đã chọn.

**Đạt:** chỉ kết luận về độ bền/catch-up sau khi kiểm tra mode mirror, mirror queue journal và tình trạng ACK; không suy một JMS success ở A = B đã bền vững.

### Thí nghiệm D — Mirror ACK propagation

**Chuẩn bị:** mirror A→B có policy **message-acknowledgements** đã được kiểm tra đúng trên phiên bản broker.

1. Tạo E7, xác minh đã xuất hiện ở broker B.
2. Consume và ACK E7 tại A bằng consumer riêng theo topology lab phù hợp.
3. Quan sát trạng thái E7 tại B sau khi ACK operation truyền qua link.
4. Thay chính sách ACK trong một phép thử riêng đã reset dữ liệu.
5. So sánh khả năng replay ở B. Không dùng queue message count đơn lẻ để kết luận; ghi eventId và operation timeline.

**Đạt:** biết bản mirror là **trạng thái đang thay đổi**, không phải kho lưu trữ sự kiện bất biến nếu ACK được phản chiếu.

### Thí nghiệm E — HA primary mất, backup activate

**Chuẩn bị:** HA replication pair với quorum/fencing và client failover đã thiết lập/kiểm tra riêng.

1. Gửi E8 persistent và xác nhận JMS commit.
2. Xác minh backup được HA protocol báo **đã đồng bộ đủ và sẵn sàng** theo metric của release.
3. Làm primary ngừng hoạt động có kiểm soát, không xóa journal.
4. Quan sát backup **activate**, client reconnect và consume E8 theo trạng thái ACK.
5. Xác minh không có hai brokers cùng quảng bá là primary cho cùng broker logic.
6. Đưa primary cũ trở lại chỉ theo **failback policy có kiểm soát**, kiểm tra journal/node identities.

**Đạt:** failover đúng và không split-brain; không chỉ chứng minh backup JVM vẫn đang chạy.

### Thí nghiệm F — Network partition và commit outcome UNKNOWN

**Chuẩn bị:** eventId ổn định và bảng inbox cho mỗi business consumer. Tạo điểm chặn mạng sát commit response trên JMS client hoặc proxy.

1. Producer gửi eventId E9 với persistent delivery.
2. Tiêm lỗi sát bước commit; ghi producer outcome **CONFIRMED hoặc UNKNOWN**.
3. Nếu UNKNOWN, thử lại **cùng eventId** bằng JMS session mới và outbox.
4. Consumer ở A/B ghi inbox và side effect trong cùng DB transaction.
5. Xác minh side effect của từng consumerName chỉ có **một row**, dù JMS message có thể được giao nhiều lần.

**Đạt:** correctness của nghiệp vụ **không phụ thuộc** việc broker có lọc trùng hoặc link tự phục hồi hoàn hảo. Một TCP cut ngẫu nhiên không chứng minh broker thực sự đã commit trước mất response; cần trace/đối soát và thử cả nhánh committed lẫn not-committed.

### Bảng tóm tắt lỗi

| Lỗi tiêm vào | Federation | AMQP Mirror | HA Replication |
| --- | --- | --- | --- |
| Mất link giữa brokers | Không phục vụ demand remote, pending tùy queue nguồn | Operation propagation trễ/dừng, lag tăng | HA protocol đánh giá lỗi/quorum; backup activation theo policy |
| Broker nguồn down | Message nguồn chưa chuyển có thể unavailable | Target chỉ có state đã phản chiếu, phải đối soát | Backup có thể tiếp quản nếu đồng bộ/fencing đúng |
| Consumer remote dừng | Demand có thể bị rút | Mirror vẫn có thể propagate message theo config | Không đổi vai trò primary/backup |
| Target disk đầy | Link/forwarding thất bại hoặc chậm | Mirror backlog/remote apply thất bại, nguy cơ RPO | Replication availability chịu ảnh hưởng; cần HA response phù hợp |
| DNS/TLS trust lỗi | Không tạo được upstream link | AMQP broker connection thất bại | Cluster/replication/client reconnect có thể lỗi |
| Duplicate send từ producer | Consumer phải idempotent | Mirror có thể phản chiếu bản trùng | HA failover không triệt tiêu duplicate nghiệp vụ |

## 14. Checklist chọn kiến trúc và điều kiện nghiệm thu

### Chọn đúng mô hình

| Nhu cầu cụ thể | Ưu tiên đánh giá | Câu hỏi vẫn phải trả lời |
| --- | --- | --- |
| Worker ở broker A xử lý việc backlog ở broker B | **Queue federation** | Có demand, policy match, fair distribution và ack safety không? |
| Notifications/Audit ở nhiều vùng cần event MULTICAST | **Address federation** | Queue subscriber có tồn tại trước publish và bền vững không? |
| Muốn dữ liệu/operation broker B theo broker A để làm DR | **AMQP Mirror** | ACK/resource replication, mirror lag, RPO và cutover/fencing? |
| Muốn một broker logic tiếp tục khi primary mất | **HA replication** | Backup đã sync, quorum, lock/fencing và client failover? |
| Muốn chuyển một queue theo pipeline định sẵn | **Core bridge** | Có cần demand động không, hay fixed forwarding đủ? |
| Muốn cân tải trong một cụm Artemis | **Cluster connection/distribution** | Node topology và routing policy có đáp ứng? |
| Muốn audit/replay bất biến mọi event | **Event log/outbox/audit store riêng** | Retention, replay keys, privacy và schema evolution? |

### Điều kiện tối thiểu trước production

| Câu hỏi | Bằng chứng bắt buộc |
| --- | --- |
| Mỗi broker có state/journal/node identity riêng? | Không chung data path giữa hai instance độc lập |
| Federation có đúng chiều upstream? | Remote demand/consumer và message delivery được đo |
| Queue vs address federation được phân biệt? | ANYCAST work queue hoặc MULTICAST subscriptions đúng topology |
| Policy giới hạn phạm vi? | Include/exclude/hops và origin controls đã thử, không mở toàn bộ broker tùy tiện |
| Mirror có đúng ACK/resource semantics? | Test message send/ACK/queue create/delete và kiểm tra version options |
| Mirror lag được giám sát? | Có RPO, operation backlog và eventId reconciliation |
| HA có dự phòng thật? | Backup sync/activation/quorum/fencing được kiểm chứng |
| HA không bị hiểu là active-active? | Trước failover, backup không nhận consumer bình thường như primary |
| Có xử lý commit outcome UNKNOWN? | Outbox, stable eventId, inbox/idempotency |
| Có kiểm tra failover URI/TLS? | Đúng Artemis client, CA/SAN cho từng endpoint, không copy Classic failover URI |
| Khi link đứt/disk đầy thì sao? | Backpressure, retries, alerts, storage headroom |
| Khi DR cutover có hai writers? | Fencing và runbook điều phối quyền ghi |
| Kiểm chứng sau phục hồi? | Canary send/consume, backlog age, DLQ và side effect đối soát |
| Được phép xóa/rotate resource? | ACL, audit, resource ownership rõ giữa broker A/B |
| Có biết giới hạn của lab? | Runtime chưa chạy trong bài viết; phải xác minh broker release/schema trước deploy |

### Ba phản ví dụ cần ghi nhớ

- **“Có federation nên broker B là backup của A”**: sai. Federation phục vụ **routing theo demand**, không bảo đảm giữ nguyên đầy đủ journal/state của A.
- **“Có mirror nên A hỏng thì B tự thành primary”**: sai. Mirror không thay HA election; DR cutover cần **writer fencing, RPO assessment và client switch**.
- **“HA replication sao lưu hai queue để consumer ở A và B cùng đọc”**: sai. Backup thuộc một broker logic, chủ yếu sẵn sàng **tiếp quản**, không hoạt động như một broker independent active để cân tải.

**Kết luận:** Với Artemis, **federation** giải quyết đường chuyển message giữa các broker độc lập dựa trên **demand/policy**; **AMQP Mirror** giải quyết việc phản chiếu **message/resource/ACK operations** theo cấu hình, với độ trễ, ownership và rủi ro divergence cần quản lý; còn **HA replication** đồng bộ trạng thái cho **primary–backup failover** theo HA protocol/quorum. Không cơ chế nào tự bảo đảm side effect nghiệp vụ exactly-once. Khi chọn topology, hãy vẽ rõ **message ownership, nơi ACK có hiệu lực, failure domain, RPO/RTO và quyền quyết định primary/writer**, rồi chứng minh bằng fault injection và eventId reconciliation trước khi đưa vào hệ thống thật.
