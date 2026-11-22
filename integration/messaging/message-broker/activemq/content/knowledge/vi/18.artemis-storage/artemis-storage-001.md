# Bindings journal, message journal, paging và thư mục large messages

> **Chương:** Lưu trữ Artemis  
> **Phạm vi:** Apache ActiveMQ Artemis trong hệ thống Java/JMS cần queue bền vững, khôi phục sau restart, xử lý backlog lớn và truyền payload lớn. Nội dung tập trung vào bốn vùng lưu trữ vật lý, quan hệ giữa chúng, cấu hình và phép thử kiểm chứng; không áp dụng nguyên xi đường dẫn hoặc XML này cho ActiveMQ Classic.

Khi một message bền vững đã được producer gửi thành công, dữ liệu của nó không nhất thiết nằm trong một file có tên giống queue. Artemis dùng nhiều cơ chế lưu trữ phối hợp: **bindings journal** giữ thông tin về những queue/binding bền vững; **message journal** ghi các bản ghi message và trạng thái giao dịch/xác nhận; **paging** chuyển một phần dữ liệu message đang chờ ra đĩa khi address vượt giới hạn bộ nhớ được cấu hình; còn **large-messages directory** chứa phần nội dung của những message lớn được broker xử lý theo đường large-message.

Nếu chỉ sao lưu thư mục journal mà bỏ quên paging hoặc large-messages, bản khôi phục có thể thiếu dữ liệu. Nếu thấy message journal không giảm kích thước sau khi consumer ACK, không thể kết luận broker bị rò rỉ. Nếu thấy một file lớn dưới data/large-messages, cũng không có nghĩa address đang paging.

**Mục tiêu cuối bài:** nhìn vào cấu hình, trạng thái broker và bốn thư mục để giải thích được **dữ liệu nằm ở đâu, khi nào phát sinh file, điều gì được phục hồi và điều gì không được phép xóa thủ công**.

## 1. Bản đồ bốn vùng lưu trữ

Artemis dùng bốn đường dẫn riêng trong cấu hình broker:

| Thành phần | Tham số broker.xml | Lưu loại thông tin gì? | Không nên hiểu nhầm là |
|---|---|---|---|
| **Bindings journal** | **bindings-directory** | Các bản ghi binding bền vững: quan hệ queue–address và metadata liên quan để dựng lại topology phù hợp khi broker khởi động | Không phải nơi giữ toàn bộ payload message |
| **Message journal** | **journal-directory** | Bản ghi message bền vững, queue references, acknowledgment và transaction/journal state cần cho recovery | Không phải một file JSON hoặc một file riêng cho từng message |
| **Paging store** | **paging-directory** | Các page file chứa message được paging từ những address vượt ngưỡng tài nguyên đã cấu hình | Không phải DLQ, archive hay nơi lưu tất cả message theo mặc định |
| **Large-message store** | **large-messages-directory** | Dữ liệu body của các large message, thường dạng file riêng được liên hệ với metadata/reference do broker quản lý | Không phải thư mục dành riêng cho message đã hết TTL hay message trong DLQ |

Ví dụ cấu trúc quan sát được ở một broker instance:

~~~text
data/
├── bindings/          # Binding journal
├── journal/           # Message journal
├── paging/            # Page files, nhóm theo address
└── large-messages/    # Body của large messages
~~~

Tên thư mục dưới **data/** là quy ước triển khai phổ biến, **không phải đường dẫn bắt buộc**. Vị trí thực tế do broker.xml, thư mục làm việc khi khởi động broker, cấu hình instance/container và các tùy chọn triển khai quyết định.

### 1.1. Bốn đường đi của dữ liệu, không phải bốn loại message

~~~mermaid
flowchart TD
    A["Client Java/JMS"] --> B["Artemis address / routing"]
    B --> C{"Loại thao tác và trạng thái"}
    C -->|Tạo durable queue/binding| BJ["Bindings journal"]
    C -->|Durable normal message / ACK / TX| MJ["Message journal"]
    C -->|Address vượt ngưỡng và policy PAGE| PG["Paging store"]
    C -->|Payload đạt ngưỡng large message| LG["Large-messages directory"]
    LG --- MJ
    PG --- MJ
    MJ --> Q["Queue / delivery / recovery"]
    BJ --> Q
~~~

Sơ đồ biểu diễn **vai trò**, không khẳng định broker luôn ghi theo trình tự đường mũi tên. Một message có thể liên quan **nhiều** vùng: large-message body nằm trong store riêng nhưng trạng thái/reference của nó gắn với journal; message bị paging có nội dung trong page file và trạng thái tiêu thụ/cursor được broker theo dõi để khôi phục.

**Câu hỏi phân loại đúng:**

- “Queue này còn tồn tại sau restart không?” → kiểm tra **binding** và chính sách queue.
- “Message durable chưa ACK còn sau restart không?” → kiểm tra **message journal/paging/large-message data** liên quan và commit.
- “Tại sao broker chuyển backlog ra disk?” → kiểm tra **paging policy và address memory**.
- “Tại sao payload 20 MiB nằm trong file riêng?” → kiểm tra **large-message threshold và client protocol**.

## 2. Bindings journal: khôi phục cấu trúc queue/binding

Bindings journal lưu các thông tin bền vững mà broker cần để dựng lại topology quản lý message, đặc biệt là **queue binding** và mối liên hệ giữa queue với address. Đây là metadata về **nơi message được định tuyến/giữ**, không phải bản sao dữ liệu body của từng message.

Ví dụ có address ANYCAST và durable queue:

~~~xml
<addresses>
    <address name="orders.charge.commands.v1">
        <anycast>
            <queue name="orders.charge.commands.v1"
                   durable="true"/>
        </anycast>
    </address>
</addresses>
~~~

Khi broker khởi động, cấu hình tĩnh và trạng thái binding bền vững phối hợp để xác định queue nào có hiệu lực. Một queue đã được tạo qua giao diện quản trị hoặc qua cơ chế tạo động có thể có vòng đời khác queue khai báo tĩnh; việc có được bảo toàn qua restart còn phụ thuộc **durability, nguồn gốc queue và chính sách auto-delete**.

### 2.1. Bindings journal trả lời được và không trả lời được điều gì?

| Thắc mắc | Bindings journal có liên quan? | Cần xem thêm |
|---|---|---|
| Vì sao durable queue xuất hiện lại sau restart? | **Có** | broker.xml, queue metadata và policy tạo/xóa |
| Một queue gắn với address nào? | **Có** | Routing type, filter và management metadata |
| Message cụ thể có body gì? | **Không phải nguồn chính** | Message journal, paging hoặc large-message store |
| Queue đang có bao nhiêu pending/delivering? | Không thể chỉ đọc bindings files để kết luận | Management counters và message state |
| Xóa queue có làm dữ liệu của queue tồn tại mãi trong journal? | Không thể suy luận như vậy | Thao tác xóa queue, reference và cơ chế reclaim/compaction |

**Điểm vận hành:** một queue tên sai do auto-create không nhất thiết mất sau khi application ngắt kết nối. Nếu broker duy trì binding đó, nó vẫn xuất hiện trong management console hoặc sau restart theo trạng thái/policy tương ứng. Muốn dọn cần **quy trình quản lý destination**, không xóa file trong bindings/.

### 2.2. Thí nghiệm kiểm tra binding

1. Trên **broker lab**, ghi nhận danh sách queue và address ban đầu.
2. Provision một durable queue **lab.storage.bindings.v1** bằng broker.xml hoặc bằng công cụ quản trị được phép.
3. Kiểm tra queue có tồn tại và routing ANYCAST đúng; không cần gửi message.
4. Restart broker có kiểm soát và xác nhận queue vẫn được nhận diện.
5. Xóa queue qua API/console được phép, sau khi bảo đảm queue không chứa message cần giữ.
6. Restart lại rồi xác nhận kết quả theo chính sách auto-create/provision hiện hành.

**Không chỉnh sửa nội dung file bindings journal bằng text editor** và không xóa trực tiếp file để thay thao tác quản trị. Bản ghi metadata là một phần của trạng thái recovery và có liên hệ với message references.

## 3. Message journal: durable message, ACK và transaction

Message journal của Artemis là cơ chế ghi bền vững dựa trên **journal records**, thay vì tạo một file riêng cho mỗi message thông thường. Nó chứa những bản ghi cần thiết cho message persistence, references, acknowledgments và trạng thái giao dịch liên quan.

Hình dung vòng đời một message persistent với một durable queue:

~~~mermaid
sequenceDiagram
    participant P as JMS Producer
    participant B as Artemis Broker
    participant J as Message journal
    participant C as JMS Consumer
    P->>B: send PERSISTENT message
    B->>J: Ghi records message / reference
    P->>B: commit transaction (nếu transacted)
    B->>J: Commit records theo journal policy
    B-->>P: Kết quả send / commit
    B->>C: Deliver message
    C->>B: ACK hoặc commit receive
    B->>J: Ghi nhận hoàn tất / ACK
    B->>B: Reclaim/reuse journal records khi đủ điều kiện
~~~

**Không đồng nhất “lệnh send trả về” với “ACK của consumer”.** Send/commit phản ánh kết quả của phía producer và transaction gửi; consumer phải nhận rồi xác nhận độc lập. Sau ACK, broker không nhất thiết thu nhỏ file journal ngay lập tức: journal có thể tái sử dụng file, giữ pool và thực hiện compact ở những thời điểm khác.

### 3.1. Những gì có thể phục hồi

Trong điều kiện **persistence-enabled=true**, queue/destination bền vững, message **DeliveryMode.PERSISTENT** và transaction gửi đã commit theo cấu hình durability:

- Message chưa hoàn tất tiêu thụ có thể được khôi phục sau **restart** của broker nếu các file lưu trữ liên quan nhất quán và còn nguyên vẹn.
- Nếu message đã được consumer ACK/commit hợp lệ, message đó không trở lại chỉ vì broker khởi động lại.
- Nếu producer hoặc consumer gặp **commit in doubt** ngay lúc mất kết nối, ứng dụng có thể không biết giao dịch đã thành công ở broker hay chưa; cần **idempotency** để xử lý retry.
- **NON_PERSISTENT** không nhận cùng lời hứa bền vững, kể cả có lúc payload/metadata xuất hiện trong cơ chế lưu tạm hoặc paging.
- Dữ liệu persistent **không tự bảo vệ khỏi mất đĩa, filesystem corruption, sai cấu hình sync hoặc xóa queue có chủ đích**.

### 3.2. ACK làm gì với message journal?

ACK/commit giúp broker biết reference đã được xử lý; broker có thể giải phóng các records không còn cần đến. Không có quan hệ 1–1 đơn giản giữa **một ACK** và **một file journal bị xóa**.

~~~text
Trước consume:
  Journal records: [M1] [M2] [M3] [reference data...]

Sau consumer ACK M1, M2:
  Journal có thông tin hoàn tất / reference lifecycle.
  File vật lý có thể vẫn còn để tái sử dụng hoặc compact.

Sau khi tất cả message được ACK:
  Queue count = 0 không đồng nghĩa thư mục journal = 0 byte.
~~~

Với transaction, journal có thể ghi các record **prepare/commit/rollback** tùy chế độ và API. Không xóa file journal để “tăng tốc giải phóng đĩa” khi đang phục vụ: dễ phá hủy trạng thái phục hồi và dẫn đến mất dữ liệu.

### 3.3. NIO và ASYNCIO

Artemis có các cách ghi journal khác nhau. **NIO** sử dụng Java NIO, thuận tiện cho nhiều môi trường. **ASYNCIO** tận dụng native asynchronous I/O khi nền tảng và native dependency hỗ trợ, thường liên quan Linux/libaio.

~~~xml
<!-- Mảnh cấu hình core, minh họa journal portability trong lab -->
<journal-type>NIO</journal-type>
<journal-file-size>10485760</journal-file-size>
<journal-min-files>2</journal-min-files>
~~~

- **journal-type** chọn cơ chế I/O, không thay đổi ý nghĩa ACK/JMS transaction.
- **journal-file-size** là kích thước file journal tính bằng byte trong cấu hình minh họa, không phải kích thước tối đa của mọi JMS message.
- **journal-min-files** quản lý số file journal tối thiểu để giảm overhead cấp phát; không nên diễn giải là số message được lưu.
- Tùy chọn **journal-sync-transactional** và **journal-sync-non-transactional** ảnh hưởng trade-off độ bền/latency; không tắt sync trong production chỉ để đạt throughput cao mà chưa đánh giá mất điện/crash và cam kết durability.

Khi benchmark, đo **send/commit latency, throughput, tốc độ ACK và I/O latency của volume**. Message journal chậm có thể do storage, chứ không phải do Java consumer chậm.

## 4. Paging: khi backlog vượt ngưỡng bộ nhớ theo address

**Paging** là cơ chế kiểm soát việc giữ message trong bộ nhớ. Khi một address đạt giới hạn tài nguyên được cấu hình và policy là **PAGE**, broker ghi những message liên quan ra **page files** trên đĩa để tránh phải giữ toàn bộ backlog trong RAM.

**Paging không đồng nghĩa message đã thành DLQ, hết hạn hoặc không còn consumer.** Nó là chiến lược lưu trữ khi backlog tăng.

### 4.1. Ví dụ cơ chế

~~~text
Address: lab.storage.page.v1
  max-size-bytes: 1 MiB
  page-size-bytes: 512 KiB
  address-full-policy: PAGE

Khi producer gửi nhanh hơn consumer:
  Message trong bộ nhớ tăng
  → vượt ngưỡng address
  → broker chuyển sang paging
  → một phần message nằm trong các page file trên đĩa
  → consumer tiếp tục đọc message theo cơ chế paging cursor
  → page file được dọn khi không còn cần cho subscription/queue
~~~

Điểm nhấn:

- **Ngưỡng kích hoạt** thuộc **address**, không đơn giản là “mỗi queue một giới hạn 1 MiB”. Với multicast, nhiều subscription/queue gắn vào address có thể ảnh hưởng cách quản lý thông tin tiêu thụ.
- **page-size-bytes** định hướng kích thước page file, **không** phải giới hạn tổng disk usage của paging.
- Paging không có nghĩa broker đã hết RAM vật lý; đó là cơ chế dựa trên **address size/policy**. Các counter và cách tính size phụ thuộc phiên bản/cấu hình.
- Khi consumer bắt kịp backlog, broker có thể thoát trạng thái paging và dọn các page file không còn cần. Không phải mỗi ACK đều làm biến mất ngay một page file.
- Nếu disk tiếp tục đầy, paging không thể thay thế capacity planning. Trên đĩa đầy, producer hoặc broker có thể lỗi/ngừng tiến triển tùy cơ chế xử lý.

### 4.2. Cấu hình address-settings

~~~xml
<!-- Mảnh cấu hình Artemis broker.xml -->
<address-settings>
    <address-setting match="lab.storage.page.v1">
        <address-full-policy>PAGE</address-full-policy>
        <max-size-bytes>1048576</max-size-bytes>
        <page-size-bytes>524288</page-size-bytes>
    </address-setting>
</address-settings>
~~~

Giá trị này chỉ dành cho **lab**: address được cho phép giữ ngưỡng 1 MiB và page file khoảng 512 KiB. Trong production, chọn giới hạn theo memory, throughput, kích thước message, số subscription và khả năng chịu disk I/O. Nếu triển khai có **max-size-bytes-reject-threshold** hoặc limit khác, cần đọc lại cấu hình hiệu lực để không suy luận policy PAGE tự động cho phép sử dụng vô hạn tài nguyên.

### 4.3. Paging gắn với nhiều queue như thế nào?

Một address **MULTICAST** có nhiều subscription queues. Payload được xử lý trong paging store gắn với **address**, trong khi tiến độ tiêu thụ của từng subscription/queue cần được broker theo dõi. Vì vậy:

~~~text
Address: orders.events.v1 (MULTICAST; đang paging)
  ├── inventory-subscription     đã bắt kịp gần hết
  └── audit-subscription         chậm 2 giờ

Page file có thể vẫn cần thiết vì audit-subscription chưa tiêu thụ.
~~~

Không được dọn page file chỉ vì **một consumer/queue** đã ACK toàn bộ message của mình. Tùy khả năng cursor/cleanup của broker, một subscription chậm có thể khiến page files tồn tại lâu hơn mong đợi.

### 4.4. Paging khác các chính sách address-full-policy khác

| Policy | Ý tưởng | Hành vi cần kiểm chứng |
|---|---|---|
| **PAGE** | Chuyển message ra page files khi address đạt ngưỡng | Tăng disk I/O/dung lượng, backlog có thể lớn |
| **BLOCK** | Áp backpressure, chặn producer khi đầy | Producer latency tăng hoặc timeout; không tự ghi vô hạn |
| **FAIL** | Từ chối khi giới hạn bị chạm | Producer nhận lỗi theo client/protocol |
| **DROP** | Loại message theo policy khi quá giới hạn | Chỉ dùng khi chấp nhận mất message |

Không nhầm **PAGE** với “bảo đảm persistence”. Một message **NON_PERSISTENT** có thể được paging để kiểm soát RAM nhưng vẫn không có hợp đồng khôi phục tương tự một message persistent đã commit.

## 5. Large messages: body được lưu riêng, không phải vì address paging

Artemis có đường xử lý **large message** để tránh buộc client/broker giữ toàn bộ một payload lớn trong bộ nhớ. Với các client/protocol được hỗ trợ và threshold thích hợp, broker lưu **body** large message trong **large-messages-directory**, còn metadata/reference liên quan được quản lý qua journal và queue state.

~~~mermaid
flowchart LR
    C["JMS client<br/>payload lớn"] --> N["Artemis large-message protocol / streaming"]
    N --> L["large-messages/<message-body-file>"]
    N --> J["Message journal: metadata / references"]
    J --> Q["Queue binding và delivery"]
    L --> Q
~~~

**Phân biệt hai chiều độc lập:**

- **Large-message path**: kích thước/cách truyền **một message** vượt ngưỡng được client/broker xử lý.
- **Paging path**: tổng backlog/size của **một address** vượt ngưỡng đã cấu hình.

Vì thế có thể gặp:

| Trường hợp | Large message? | Paging? |
|---|---|---|
| 100 message nhỏ, không backlog | Thường không | Thường không |
| Hàng nghìn message 16 KiB, consumer tắt | Tùy threshold, giả sử không | **Có thể** |
| Một message 2 MiB, address không bị áp lực bộ nhớ | **Có thể** | Không nhất thiết |
| Nhiều large message, consumer rất chậm | **Có thể** | **Cũng có thể** |

Không khẳng định chỉ cần payload “lớn hơn 100 KiB” thì mọi giao thức luôn dùng cùng large-message path. Ngưỡng **minLargeMessageSize**, cách encode body và client protocol/version có ảnh hưởng thực tế. Đặc biệt khi đổi **Core JMS → AMQP/STOMP/bridge**, cần kiểm tra cách broker xử lý payload.

### 5.1. Large-message file sống bao lâu?

File body tồn tại khi broker còn cần message đó (hoặc references của nó). Sau ACK/expiry/delete đủ điều kiện, Artemis có cơ chế thu hồi file. Tuy nhiên, cleanup có thể không diễn ra đúng tại thời điểm vừa có ACK, do trạng thái in-flight, transaction, paging, nhiều queue references hoặc công việc dọn nội bộ.

Nếu thấy một file large message còn sau khi một consumer ACK:

1. Kiểm tra message còn reference ở queue/subscription khác không.
2. Kiểm tra in-flight, transaction, scheduled delivery, paging và expiry.
3. Xác minh broker đang hoạt động và cleanup có bị lỗi không.
4. So sánh sau một khoảng ổn định bằng management metrics và dung lượng directory.
5. Không xóa thủ công file chỉ vì nhìn thấy queue count của **một queue** đã về 0.

### 5.2. Với client Java/JMS

Artemis JMS client có thể sử dụng threshold large-message; ví dụ client URL Core Netty trong lab:

~~~text
tcp://localhost:61616?minLargeMessageSize=131072
~~~

URI chỉ minh họa với **Artemis JMS client hỗ trợ tùy chọn đó**. Nếu phiên bản client/protocol đang dùng không nhận tham số hoặc có cách cấu hình khác, hãy cấu hình bằng API/connection factory phù hợp và **kiểm chứng file thực**. Để trigger rõ trong bài test, gửi message body **2 MiB**, vượt xa threshold 128 KiB.

Với payload rất lớn trong ứng dụng thật, cân nhắc phương thức **streaming** do client Artemis hỗ trợ thay vì cấp phát mảng byte khổng lồ; ví dụ bên dưới cố ý dùng mảng nhỏ theo tiêu chuẩn lab, không phải mẫu tối ưu cho gigabyte payload.

## 6. Cấu hình broker.xml: tách đường dẫn và policy

Đây là **các fragment Artemis** ghép vào những phần tử tương ứng của broker.xml hiện có, **không phải file XML hoàn chỉnh**. Các giá trị dưới **/srv/mq/artemis/data** dùng để giải thích vị trí lưu trữ của một instance lab chạy Linux; trên Windows/container hãy chọn đường dẫn được mount phù hợp.

### 6.1. Core storage directories

~~~xml
<!-- Các phần tử thuộc cấu hình core của Artemis -->
<persistence-enabled>true</persistence-enabled>

<bindings-directory>/srv/mq/artemis/data/bindings</bindings-directory>
<journal-directory>/srv/mq/artemis/data/journal</journal-directory>
<paging-directory>/srv/mq/artemis/data/paging</paging-directory>
<large-messages-directory>/srv/mq/artemis/data/large-messages</large-messages-directory>

<!-- NIO để ví dụ không phụ thuộc native ASYNCIO -->
<journal-type>NIO</journal-type>
<journal-file-size>10485760</journal-file-size>
<journal-min-files>2</journal-min-files>
~~~

Các directory phải được cấp quyền đọc/ghi cho process broker và có disk capacity đủ cho backlog, logs và file tạm. Một số deployment dùng relative paths **data/**; khi đó phải xác định đường dẫn tuyệt đối theo môi trường thực tế, không tự suy từ đường dẫn repository.

**Không đặt journal, paging và large-messages trên một volume nhỏ rồi tưởng chia thành ba directory sẽ tách biệt giới hạn tài nguyên.** Tách volume vật lý/virtual có thể giúp cô lập dung lượng hoặc I/O, nhưng ảnh hưởng tới tính nhất quán của snapshot và khả năng khôi phục; phải thiết kế đồng bộ.

### 6.2. Queue lab và policy paging riêng

~~~xml
<!-- Fragment trong <addresses> -->
<addresses>
    <address name="lab.storage.page.v1">
        <anycast>
            <queue name="lab.storage.page.v1" durable="true"/>
        </anycast>
    </address>
    <address name="lab.storage.large.v1">
        <anycast>
            <queue name="lab.storage.large.v1" durable="true"/>
        </anycast>
    </address>
</addresses>
~~~

~~~xml
<!-- Fragment trong <address-settings> -->
<address-settings>
    <address-setting match="lab.storage.page.v1">
        <address-full-policy>PAGE</address-full-policy>
        <max-size-bytes>1048576</max-size-bytes>
        <page-size-bytes>524288</page-size-bytes>
    </address-setting>
</address-settings>
~~~

Chỉ **lab.storage.page.v1** được đặt ngưỡng paging nhỏ trong ví dụ. **lab.storage.large.v1** dùng để cô lập bài thử large message, tránh nhầm file page với large-message file.

Nếu broker đã có phần tử **addresses** hoặc **address-settings**, hãy **chèn các entry mới vào đúng phần tử hiện hữu**, không tạo hai phần tử gốc trùng nhau trong broker.xml. Sau thay đổi cấu hình, sử dụng quy trình reload/restart được phiên bản hỗ trợ và **xác minh hiệu lực** thay vì giả định sửa file trên disk là broker đã áp dụng.

## 7. Lab Java/JMS: kích hoạt paging và large-message độc lập

Bài lab này cố ý dùng **hai queue test** để phân biệt cơ chế. Không chạy trên DLQ hoặc queue nghiệp vụ thật.

**Điều kiện:**

- Artemis broker đang chạy với persistence và thư mục ở mục 6; đã provision hai ANYCAST queue.
- Client **org.apache.activemq:artemis-jms-client** tương thích với **javax.jms** (JMS 2.x) và phiên bản broker. Nếu dự án dùng **jakarta.jms**, thay dependency/import đồng bộ.
- Environment: **MQ_URL**, **MQ_USER**, **MQ_PASSWORD**. Ví dụ MQ_URL là URI Core client có **minLargeMessageSize=131072**, đảm bảo message 16 KiB ở dưới threshold còn message 2 MiB ở trên.
- Không có consumer khác trên hai queue trong lúc quan sát sự tăng backlog.
- Chỉ làm bài test trên storage volume có đủ dung lượng; không intentionally fill disk tới mức ảnh hưởng broker khác.

### 7.1. Một chương trình với ba chế độ

~~~java
import java.util.Arrays;
import javax.jms.BytesMessage;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.JMSProducer;
import javax.jms.Message;
import javax.jms.Queue;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class ArtemisStorageProbe {
    private static final String PAGE = "lab.storage.page.v1";
    private static final String LARGE = "lab.storage.large.v1";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Use: flood-page | send-large | drain-page | drain-large");
        }

        ConnectionFactory factory = new ActiveMQConnectionFactory(
            required("MQ_URL"));

        try (JMSContext ctx = factory.createContext(
                required("MQ_USER"),
                required("MQ_PASSWORD"),
                JMSContext.SESSION_TRANSACTED)) {

            switch (args[0]) {
                case "flood-page":
                    floodPage(ctx);
                    break;
                case "send-large":
                    sendLarge(ctx);
                    break;
                case "drain-page":
                    drain(ctx, PAGE);
                    break;
                case "drain-large":
                    drain(ctx, LARGE);
                    break;
                default:
                    throw new IllegalArgumentException("Unknown mode");
            }
        }
    }

    private static void floodPage(JMSContext ctx) throws Exception {
        Queue queue = ctx.createQueue(PAGE);
        JMSProducer producer = ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT);

        // Message nhỏ hơn ngưỡng large-message 128 KiB.
        byte[] payload = new byte[16 * 1024];
        Arrays.fill(payload, (byte) 65);

        for (int i = 0; i < 400; i++) {
            BytesMessage message = ctx.createBytesMessage();
            message.writeBytes(payload);
            message.setIntProperty("labSequence", i);
            producer.send(queue, message);

            // Commit theo nhóm để thấy backlog tăng dần.
            if ((i + 1) % 16 == 0) {
                ctx.commit();
                System.out.println("Committed " + (i + 1));
            }
        }
    }

    private static void sendLarge(JMSContext ctx) throws Exception {
        Queue queue = ctx.createQueue(LARGE);
        byte[] payload = new byte[2 * 1024 * 1024];
        Arrays.fill(payload, (byte) 66);

        BytesMessage message = ctx.createBytesMessage();
        message.writeBytes(payload);
        message.setStringProperty("labKind", "large");

        ctx.createProducer()
            .setDeliveryMode(DeliveryMode.PERSISTENT)
            .send(queue, message);
        ctx.commit();

        System.out.println("Committed large message, JMSMessageID="
            + message.getJMSMessageID());
    }

    private static void drain(JMSContext ctx, String name)
            throws Exception {
        Queue queue = ctx.createQueue(name);
        JMSConsumer consumer = ctx.createConsumer(queue);

        int consumed = 0;
        try {
            for (;;) {
                Message message = consumer.receive(1000);
                if (message == null) {
                    break;
                }
                // Lab chỉ xác nhận và giải phóng message.
                // Hệ thống thật phải xử lý nghiệp vụ trước commit.
                ctx.commit();
                consumed++;
            }
        } finally {
            consumer.close();
        }

        System.out.println("Committed receives=" + consumed);
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.trim().isEmpty()) {
            throw new IllegalArgumentException("Missing env: " + key);
        }
        return value;
    }
}
~~~

**Không coi một commit đã trả về là bằng chứng an toàn trước mọi loại mất điện.** Kết quả còn phụ thuộc cấu hình journal sync, storage durability và tình trạng thiết bị. Bài lab chủ yếu kiểm tra **đường lưu trữ và vòng đời file**.

### 7.2. Bài thử A — bindings journal

1. Provision hai queue nhưng **chưa gửi message**.
2. Quan sát qua management console: có address, queue name, durable flag và binding phù hợp.
3. Ghi baseline kích thước bốn directory.
4. Restart broker lab theo quy trình bình thường; đọc lại danh sách queue.
5. Diễn giải vì sao queue bền vững có thể tồn tại khi queue chưa có message.

**Kỳ vọng:** topology được tái dựng/áp dụng đúng; **không cần có payload message trong journal để queue tồn tại**. Không cố suy ra từng record cụ thể bằng cách mở file journal nhị phân.

### 7.3. Bài thử B — message journal, chưa paging

1. Giữ **lab.storage.large.v1** trống.
2. Có thể gửi một **persistent TextMessage nhỏ** riêng dưới ngưỡng large-message bằng JMS để kiểm tra normal message path; tránh dùng payload 2 MiB của phần sau.
3. Đọc queue pending, journal disk usage và record/metrics phù hợp.
4. Restart broker lab; xác minh message chưa ACK vẫn có thể nhận.
5. Commit receive; đợi broker ổn định rồi ghi nhận queue count và kích thước journal.
6. Không kỳ vọng file journal lập tức biến mất khi queue count về 0.

**Kỳ vọng:** durable message chưa ACK sống qua restart bình thường, nhưng file journal có thể vẫn tồn tại do file reuse và compaction policy.

### 7.4. Bài thử C — kích hoạt paging bằng nhiều message nhỏ

1. Không chạy consumer trên **lab.storage.page.v1**.
2. Chạy **flood-page**, gửi **400 × 16 KiB ≈ 6,25 MiB** payload cùng overhead, vượt đáng kể ngưỡng lab **1 MiB**.
3. Trong lúc gửi, kiểm tra trạng thái **paging** của address bằng console/management.
4. Quan sát files dưới **paging-directory** và số message còn chờ.
5. Restart broker lab khi đã commit toàn bộ batch, rồi xác nhận pending message còn được phục hồi.
6. Chạy **drain-page**; chờ dọn các page file không còn được tham chiếu.
7. Ghi lại số lượng file, số message consume và trạng thái paging cuối.

**Kỳ vọng:** address có thể đi vào paging, sinh page files và giải phóng chúng sau khi backlog được tiêu thụ. Việc nhìn thấy hoặc không thấy một file ngay tại một thời điểm phụ thuộc trạng thái cursor, transaction và cleanup; **đọc cả management state lẫn directory**, không chỉ dùng lệnh list file.

### 7.5. Bài thử D — một large message không cần backlog lớn

1. Giữ **lab.storage.large.v1** trống, không đặt max-size-bytes nhỏ như queue paging.
2. Cấu hình Artemis client threshold **minLargeMessageSize=131072** theo cách được version hỗ trợ.
3. Chạy **send-large**, gửi payload **2 MiB** và commit.
4. Quan sát file body mới trong **large-messages-directory**; đọc queue count và message size bằng management view.
5. Restart broker; chạy **drain-large** và xác nhận message có thể được nhận rồi ACK/commit.
6. Đợi broker dọn large-message body khi không còn references; kiểm tra directory.
7. Lặp khi cố tình giữ consumer offline để xác định file tồn tại lâu hơn.

**Kỳ vọng:** large-message body được lưu qua cơ chế large-message dù queue không cần paging. Sau ACK và cleanup, file không còn được dùng có thể biến mất. Không xóa thủ công nếu file vẫn được broker quản lý.

### 7.6. Bảng kết quả cần nộp

| Thử nghiệm | Bindings | Journal | Paging | Large messages | Bằng chứng quan trọng |
|---|---|---|---|---|---|
| Provision queue rỗng | Có binding/topology | Không cần body | Không | Không | Queue tồn tại sau restart |
| Gửi small persistent | Không đổi topology đáng kể | Message/ref/ACK | Không nếu chưa đầy | Không | Receive sau restart, ACK |
| Flood 400 small messages | Không đổi topology đáng kể | Có trạng thái liên quan | **Có thể có page files** | Không nếu dưới threshold | Paging state, drain và cleanup |
| Gửi one large payload 2 MiB | Không đổi topology đáng kể | Metadata/reference liên quan | Không bắt buộc | **Có thể có body file** | File/body lifecycle, threshold |
| ACK hết backlog | Binding vẫn còn | Reclaim/reuse records | Dọn khi không còn references | Dọn khi không còn references | Queue count và disk không nhất thiết về 0 |

## 8. Nhìn file trên disk: quan sát nhưng không can thiệp

Trên một Artemis instance Linux dùng đường dẫn minh họa ở mục 6, có thể quan sát **chỉ đọc**:

~~~bash
du -sh /srv/mq/artemis/data/bindings
du -sh /srv/mq/artemis/data/journal
du -sh /srv/mq/artemis/data/paging
du -sh /srv/mq/artemis/data/large-messages

find /srv/mq/artemis/data/paging -type f -name '*.page' -print
find /srv/mq/artemis/data/large-messages -type f -print
~~~

Kết quả chỉ là **snapshot tức thời của filesystem**:

- Journal có thể giữ file preallocated hoặc file đã có thể reuse.
- Page files có thể đang được tạo/xóa khi consumer chạy.
- Large-message files có thể đang được ghi khi producer stream payload.
- Queue/message counts ở management view có thể lệch thời điểm với lệnh đo disk.

**Không sửa/rename/delete bất kỳ file nào trong bốn directory khi broker đang chạy.** Các file có quan hệ logic với nhau qua journal references và recovery metadata; xóa một file nhìn có vẻ “cũ” có thể làm mất message hoặc khiến broker không phục hồi được.

### 8.1. Kích thước disk thay đổi không đồng nghĩa message bị mất

Ví dụ queue pending từ 10.000 xuống 0 nhưng **journal-directory** còn 2 GiB. Điều này có thể do journal files được reuse hoặc compaction chưa chạy. Cần xem:

1. Queue pending và delivering đã về trạng thái mong đợi chưa?
2. Có durable message khác trên broker, DLQ, scheduled delivery hoặc subscription chậm không?
3. Journal file pool/min-files, compaction và log có đang bình thường không?
4. Paging và large-message directory có còn references?
5. Disk usage có **tiếp tục tăng không giới hạn** hay dao động quanh một mức ổn định?

Không dùng **rm -rf data/journal** như biện pháp reclaim space.

## 9. Crash recovery và backup: phải giữ tính nhất quán giữa bốn vùng

Đối với broker persistent, **một bản backup chỉ có journal-directory thường không phải backup đầy đủ**. Nếu message bị paging, nội dung có thể nằm trong paging-directory; nếu là large message, body có thể nằm trong large-messages-directory; bindings journal cần để khôi phục topology phù hợp.

### 9.1. Ma trận rủi ro khi thiếu một phần storage

| Thành phần bị thiếu khi restore | Rủi ro |
|---|---|
| **bindings-directory** | Không khôi phục đúng binding/queue metadata; journal message có thể không còn nơi tham chiếu đúng |
| **journal-directory** | Thiếu durable message/ACK/transaction state; không thể chỉ dùng queue bindings để dựng lại backlog |
| **paging-directory** | Những message hoặc trạng thái paging đang cần có thể không hoàn chỉnh |
| **large-messages-directory** | Body của large message đang được tham chiếu có thể bị thiếu |
| **broker.xml và security/config** | Routing, policy và quyền có thể thay đổi sau restore dù file data còn |

**Không trộn snapshot của bốn thư mục ở các thời điểm khác nhau.** Một page file tạo lúc 14:03 có thể được journal/cursor reference cùng một trạng thái; nếu journal lấy từ 14:05 còn paging lấy từ 14:00, bản restore có thể không nhất quán.

### 9.2. Cách backup an toàn

Ưu tiên một trong những cách được sản phẩm/triển khai hỗ trợ:

1. **Offline backup:** dừng broker sạch, xác nhận không còn process ghi, sau đó backup **đồng bộ toàn bộ storage và cấu hình cần thiết**.
2. **Storage snapshot nhất quán:** dùng cơ chế quiesce/snapshot phù hợp để lấy một tập dữ liệu nhất quán qua tất cả volume liên quan; nếu bốn directory trên nhiều volume, phải có cách snapshot nhất quán **cùng một thời điểm logic**.
3. **HA/replication phù hợp:** kiểm chứng vai trò backup/replica, journal/paging/large-message state và quy trình failover; **replication không mặc nhiên thay backup lịch sử** trước thao tác xóa nhầm.

Không dựa vào **copy từng file đang mở** bằng công cụ không phối hợp với broker như một cam kết khôi phục. Có thể thu được file bị ghi dở và trạng thái cross-directory không nhất quán.

### 9.3. Bài thử restore cần chứng minh gì?

Trên broker test phục hồi từ bản backup:

- Durable queue có đúng address, routing type và metadata cần thiết.
- Số pending message được giải thích theo **snapshot point**, không chỉ so tổng byte trên disk.
- Message nhỏ persistent chưa ACK được consume/commit.
- Large-message body còn đọc được đầy đủ, không chỉ có record metadata.
- Message nằm trong paging vẫn có thể được drain, không báo missing page/file.
- ACL và policy tương ứng với bản backup.
- Sau drain, journal/paging/large-message lifecycle không báo lỗi.
- Application **không** kết nối nhầm vào broker phục hồi khi dữ liệu đó chỉ dành cho thử nghiệm; tránh phát message/side effect hai lần.

**Phân biệt restart và crash:** một lần stop/start sạch cho thấy persistence cơ bản, nhưng không mô phỏng mất điện giữa journal write/commit hoặc failover. Với mục tiêu durability quan trọng, cần thêm kiểm thử fault injection ở đúng môi trường được phép và đối soát producer/consumer ID.

## 10. Sự cố thường gặp và cách phân loại đúng

### 10.1. Disk paging tăng nhanh, heap không tăng tương ứng

**Triệu chứng:** số page file tăng, queue pending tăng, memory broker chưa chạm giới hạn máy.

**Khả năng:** address đã vào chế độ paging vì max-size-bytes/address-full-policy, producer nhanh hơn consumer hoặc subscriber chậm.

**Điều tra:** đo per-address paging state, backlog, oldest message age, consumer count/rate và disk usage. Nếu cần, giảm tốc producer bằng backpressure, tăng năng lực consumer hoặc xử lý subscription đang chậm. **Không xóa page files để giải phóng disk.**

### 10.2. Journal directory lớn dù queue trống

**Khả năng:** file pool được giữ để reuse, compaction/reclaim chưa diễn ra, hoặc broker còn message/reference ở nơi khác.

**Điều tra:** kiểm tra queue/ACK metrics, journal configuration, log, tốc độ disk growth và các address còn backlog. Không suy từ du -sh rằng toàn bộ byte đó là message chưa xử lý.

### 10.3. Large-messages directory đầy

**Khả năng:** nhiều payload lớn, message bị giữ bởi consumer chậm, một subscription chưa ACK, broker cleanup lỗi hoặc file đang được ghi.

**Điều tra:** message/queue references, consumer progress, size và age của large messages, streaming client, TTL/expiry, broker log. Nếu file thực sự orphaned, quy trình xử lý phải theo công cụ và hướng dẫn của đúng phiên bản Artemis, **không tự xóa file dựa trên timestamp**.

### 10.4. Restart xong queue còn nhưng message mất

**Các giả thiết cần kiểm tra:**

- Queue tồn tại do binding, nhưng message gửi **NON_PERSISTENT**, chưa commit hoặc producer không chắc send thành công.
- Broker đã ACK/expire/delete message trước restart.
- Persistence tắt hoặc journal/data path trỏ tới **volume mới/rỗng** khi restart container.
- Paging/large-message directory bị mất hoặc không nằm trong backup.
- Ứng dụng đang đọc **broker instance hoặc queue khác**.
- Có disk corruption hoặc thao tác quản trị đã xóa queue/message.

Đừng kết luận “bindings journal còn nên message phải còn”. Hai chức năng là khác nhau.

### 10.5. Broker báo lỗi missing page hoặc large-message file

**Không tự tạo file rỗng cùng tên** để broker vượt qua bước khởi động. Cần cô lập instance, lưu logs/snapshot để điều tra, xác minh tính nhất quán của backup/HA, và khôi phục theo quy trình sản phẩm có kiểm chứng. Một file giả có thể làm tình trạng dữ liệu khó đối soát hơn.

### 10.6. I/O saturation làm send/commit tăng latency

**Khả năng:** message journal phải flush nhiều, paging tăng tải đĩa, large messages được ghi cùng volume, hoặc storage backend chậm.

**Điều tra theo thứ tự:** producer/consumer throughput → broker paging state → journal sync metrics/log → filesystem I/O latency → disk space/inode → network storage latency → cấu hình journal-type và file pool. Tối ưu hóa I/O cần đo, không tắt durability flags trước khi biết nguyên nhân.

## 11. Quyết định vận hành: đặt dữ liệu và theo dõi chỉ số

### 11.1. Gợi ý thiết kế volume

- **Bindings + journal:** ưu tiên tính bền vững và latency ghi ổn định; backup/restore nhất quán.
- **Paging:** cần capacity cho backlog tăng bất thường, có alert theo tốc độ sử dụng; có thể tách volume để cô lập áp lực nhưng vẫn phải snapshot nhất quán.
- **Large messages:** dự trù kích thước payload, concurrent inflight và khoảng thời gian ACK; tránh để file lớn lấp đầy volume chứa journal.
- **Container/Kubernetes:** mount persistent volume phù hợp, xác minh broker instance thực sự dùng đúng mount path sau redeploy. Không chỉ mount journal rồi bỏ paging/large messages ở ephemeral filesystem.
- **HA:** kiểm tra chính sách shared store hoặc replication có bao phủ cả bốn phần hay không trong topology cụ thể.

Tách directory **không đồng nghĩa** có replication, quota hoặc bảo vệ mất dữ liệu. Storage reliability đến từ cấu hình, thiết bị, snapshot, broker recovery và quy trình vận hành phối hợp.

### 11.2. Monitoring tối thiểu

| Chỉ số | Vì sao cần |
|---|---|
| **Queue messageCount / deliveringCount / consumerCount** | Thấy backlog và quá trình tiêu thụ |
| **Address paging state, page count, page disk usage** | Phân biệt nghẽn RAM/address với nghẽn queue |
| **Message journal disk usage, write/commit latency** | Tìm áp lực I/O và biểu hiện chưa reclaim |
| **Large-message file count / bytes / age** | Phát hiện payload lớn bị giữ lâu bất thường |
| **Persistent vs non-persistent send rates** | Giải thích khả năng phục hồi sau restart |
| **Disk free bytes, inode, I/O latency trên mọi volume** | Paging và large messages có thể ăn hết disk |
| **Message age / throughput / DLQ rate** | Biết backlog có đang được giải quyết không |
| **Broker restart, recovery errors, missing file logs** | Phát hiện mất nhất quán storage |
| **Backup timestamp và kết quả restore drill** | Chứng minh khả năng khôi phục, không chỉ có file backup |

Không chỉ cảnh báo **“disk 90%”**. Với paging đang tăng nhanh, cần tính **time-to-full** theo tốc độ ghi và khả năng consume hiện tại. Khi gần đầy đĩa, hành động an toàn thường là **giảm tốc hoặc chặn producer có kiểm soát**, mở rộng storage theo runbook, phục hồi consumer; không xóa page/journal records để kéo dài thời gian.

## 12. Câu hỏi kiểm tra và bài tập cuối

### Tình huống A — Queue còn sau restart nhưng rỗng

Một queue ANYCAST bền vững vẫn hiện trong console sau restart, nhưng 1.000 message trước đó không còn.

**Yêu cầu:** nêu ít nhất bốn giả thuyết; phân biệt **bindings journal** với **message journal**; kiểm tra persistent delivery mode, commit/ACK, broker path và paging/large-message storage trước khi kết luận mất dữ liệu.

**Mấu chốt:** sự tồn tại của queue **không phải bằng chứng** message chưa ACK vẫn được bảo toàn.

### Tình huống B — Backlog 15 GiB nhưng memory của broker vẫn ổn định

Có 2 triệu message nhỏ đang chờ trên một address được cấu hình **PAGE**; disk usage thư mục paging tăng.

**Yêu cầu:** giải thích cơ chế theo address, vai trò page-size-bytes, vì sao subscriber chậm có thể giữ page files, và ba biện pháp vận hành **không xóa file thủ công**.

**Mấu chốt:** paging là kiểm soát backlog bằng disk, không phải giải pháp khi disk capacity không đủ.

### Tình huống C — File large-message còn dù queue consumer đã ACK

Một message body 20 MiB có file dưới large-messages/. Consumer queue A đã ACK, nhưng file chưa biến mất.

**Yêu cầu:** kiểm tra references ở queue/subscription khác, in-flight, transaction/cleanup và paging; giải thích vì sao không được xóa file theo timestamp.

**Mấu chốt:** body file do broker quản lý và có thể còn được nhiều references cần dùng.

### Tình huống D — Backup chỉ có thư mục journal

Bản backup từ production chỉ lưu **data/journal**, không có **data/bindings**, **data/paging**, **data/large-messages**. Broker phục hồi có lỗi khi đọc large message.

**Yêu cầu:** chỉ ra thành phần bị thiếu, viết lại backup plan có consistency point và các test restore bắt buộc.

**Mấu chốt:** các vùng lưu trữ **liên kết với nhau**, không thể coi journal-directory là bản sao mọi nội dung.

### Tình huống E — Phân biệt large-message và paging

Một message 2 MiB và 400 message 16 KiB được gửi vào hai address khác nhau. Address thứ nhất không paging, address thứ hai có paging.

**Yêu cầu:** giải thích vì sao hai kết quả không mâu thuẫn; chỉ ra điều kiện kích hoạt của từng cơ chế và phép thử bằng directory/management.

**Mấu chốt:** **kích thước một message** khác **tổng áp lực backlog của address**.

### Checklist nghiệm thu

- [ ] Xác định được bốn tham số **bindings-directory**, **journal-directory**, **paging-directory**, **large-messages-directory** trong Artemis broker.xml.
- [ ] Giải thích được vai trò riêng của bindings journal và message journal.
- [ ] Phân biệt durable queue binding với persistent message và transaction đã commit.
- [ ] Hiểu vì sao ACK không kéo theo việc file journal lập tức co về 0.
- [ ] Cấu hình được **address-full-policy=PAGE**, **max-size-bytes**, **page-size-bytes** trong address-settings.
- [ ] Quan sát được paging khi backlog vượt ngưỡng và page cleanup sau drain.
- [ ] Nhận biết large-message body file và ngưỡng client/protocol, không nhầm với paging.
- [ ] Chạy được Java/JMS test với message nhỏ và payload lớn trên các queue test riêng.
- [ ] Biết rằng **persistence-enabled** và **PERSISTENT delivery** quan trọng nhưng không thay thế backup/HA.
- [ ] Không chỉnh sửa/xóa trực tiếp journal, page hoặc large-message files khi broker đang chạy.
- [ ] Backup và restore có xét **cả bốn vùng** và broker configuration đồng nhất.
- [ ] Có phương án giám sát disk/I/O/paging/large messages cùng chiến lược xử lý khi gần đầy.
- [ ] Kiểm chứng được recovery bằng restart, ACK, drain và restore drill trong sandbox.

**Kết luận:** Trong Artemis, **bindings journal** giúp phục hồi topology bền vững; **message journal** ghi message và trạng thái xác nhận/giao dịch; **paging** xử lý backlog vượt ngưỡng bộ nhớ theo address; còn **large-messages directory** lưu body của message lớn theo cơ chế chuyên biệt. Một message hoặc một queue có thể liên quan nhiều vùng cùng lúc, vì vậy vận hành đáng tin cậy phải **quan sát bằng management metrics, cấu hình đúng đường dẫn, bảo vệ toàn bộ storage set và kiểm chứng restore**, không đoán trạng thái dữ liệu bằng một thư mục đơn lẻ.
