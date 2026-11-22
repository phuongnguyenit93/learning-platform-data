# Tự tạo và tự xóa address, queue theo chính sách

> **Chương:** Định tuyến Artemis  
> **Trọng tâm:** cấu hình **address-settings** trong Apache ActiveMQ Artemis để kiểm soát thời điểm broker tự tạo (auto-create), tự thu hồi (auto-delete) **address** và **queue**; áp dụng cho JMS queue/topic, môi trường phát triển và triển khai production có quản trị.

Một queue xuất hiện ngay sau lần gửi đầu tiên là hành vi tiện lợi khi thử nghiệm. Cùng hành vi đó có thể thành lỗi nghiêm trọng trong production: chỉ một ký tự sai trong tên destination cũng đủ tạo ra hàng đợi không có consumer; hoặc một chính sách dọn tự động quá rộng có thể xóa luồng nhận cần giữ message khi ứng dụng tạm dừng. Artemis cho phép lựa chọn khác nhau **theo mẫu tên address**, nhờ đó một broker có thể vừa hỗ trợ namespace động trong sandbox, vừa yêu cầu khai báo trước các destination nghiệp vụ quan trọng.

Bài học này đi thẳng vào **cơ chế, điều kiện, cấu hình và phép thử** để tránh hai sai lầm: hiểu auto-create như thao tác tạo một đối tượng Java, và hiểu auto-delete như một tác vụ “xóa queue ngay khi consumer ngắt kết nối”.

## 1. Mục tiêu và đối tượng mà chính sách tác động

Sau bài học, bạn có thể:

1. Giải thích độc lập các cờ **auto-create-addresses**, **auto-create-queues**, **auto-delete-addresses**, **auto-delete-queues** và quan hệ giữa chúng.
2. Viết **address-settings** cho hai namespace: một vùng động để thử nghiệm và một vùng production phải provision sẵn.
3. Xác định điều kiện thu hồi queue theo **consumer count, message count, delay**, đồng thời kiểm tra các message đang xử lý hoặc đã lên lịch.
4. Phân biệt queue tự tạo bởi broker, queue được khai báo tĩnh, queue do công cụ quản trị tạo và queue của JMS subscription.
5. Thực hành Java/JMS kích hoạt hành vi auto-create, quan sát vòng đời đối tượng rồi kiểm chứng auto-delete trên broker.
6. Chẩn đoán queue “không chịu biến mất”, queue “bất ngờ biến mất” và producer “gửi thành công nhưng không có consumer”.

### 1.1. Phân biệt address và queue trước khi bật chính sách

Trong Artemis:

- **Address** là đích nhận message và gắn với một hoặc nhiều routing type.
- **Queue** gắn vào address, giữ message để consumer tiêu thụ.
- **ANYCAST** thường dùng để phân phối message đến một queue phù hợp; các consumer trên cùng queue cạnh tranh nhận.
- **MULTICAST** thường dùng để phân phối bản sao đến từng queue/subscription phù hợp.

~~~text
Address: lab.auto.invoice.commands.v1     [ANYCAST]
    └── Queue: lab.auto.invoice.commands.v1
          └── Worker A

Address: orders.lifecycle.events.v1        [MULTICAST]
    ├── Queue: inventory-subscription
    └── Queue: notification-subscription
~~~

Hai cặp “address tồn tại / queue tồn tại” và “address có thể được xóa / queue có thể được xóa” **không tương đương nhau**. Một address có thể còn tồn tại dù chưa có queue nào; ngược lại, queue không thể tồn tại độc lập với address liên kết của nó. Trong JMS, đối tượng **Queue** hay **Topic** được tạo trong mã Java chỉ là tham chiếu logic; việc tạo thành tài nguyên trên server xảy ra theo cách broker xử lý thao tác gửi, nhận hoặc đăng ký subscription và cấu hình hiệu lực.

## 2. Các nhóm cấu hình auto-create và auto-delete

Trong Artemis, các thuộc tính này thường được khai báo dưới **address-settings** trong cấu hình broker. Mỗi **address-setting** có thuộc tính **match** để chỉ phạm vi áp dụng.

| Thuộc tính | Tác động chính | Câu hỏi vận hành |
|---|---|---|
| **auto-create-addresses** | Cho phép Artemis tự tạo address chưa tồn tại khi một thao tác yêu cầu và điều kiện liên quan phù hợp | Gửi tới một tên address mới có được chấp nhận không? |
| **auto-create-queues** | Cho phép tự tạo queue cần thiết khi broker xử lý thao tác phù hợp | Nếu address có rồi nhưng queue chưa có, broker có tự bổ sung queue không? |
| **auto-delete-queues** | Bật cơ chế xét thu hồi những queue thuộc diện tự xóa theo chính sách | Khi queue không còn consumer và đáp ứng điều kiện, nó có được dọn không? |
| **auto-delete-addresses** | Bật cơ chế xét thu hồi những address thuộc diện tự xóa, khi không còn queue phụ thuộc theo điều kiện | Sau khi queue cuối cùng biến mất, address có được thu hồi không? |
| **auto-delete-queues-delay** | Thời gian trì hoãn xét xóa queue sau khi thỏa điều kiện | Có tránh dọn ngay khi consumer chỉ restart ngắn không? |
| **auto-delete-queues-message-count** | Ngưỡng số message để queue đủ điều kiện xét xóa | Queue vẫn còn backlog có được giữ lại không? |
| **auto-delete-addresses-delay** | Thời gian trì hoãn xét xóa address đủ điều kiện | Có đủ khoảng đệm trước khi xóa address trống không? |

**Điểm cốt lõi:** tên cấu hình **auto-delete** không hứa xóa tất cả queue đang trống. Broker còn xét **nguồn gốc và thuộc tính của tài nguyên** (chẳng hạn auto-created hay được tạo có chủ đích), điều kiện đếm, delay và cơ chế quản trị của phiên bản Artemis đang chạy.

Một số phiên bản Artemis còn có thuộc tính **auto-delete-created-queues**, nhằm điều khiển cách tự xóa queue được tạo thông qua những con đường khác với auto-create. Không coi queue tạo bằng management API, khai báo tĩnh và queue sinh từ JMS subscription có cùng vòng đời chỉ vì chúng cùng có tên. Khi dùng thuộc tính mở rộng, phải đối chiếu đúng phiên bản broker và kiểm tra loại queue được đánh dấu trong management view.

### 2.1. Hai cờ tạo có thể đưa đến bốn tổ hợp khác nhau

| Auto-create address | Auto-create queue | Kỳ vọng khi gặp destination chưa provision |
|---|---|---|
| Tắt | Tắt | Đòi hỏi address/queue đã tồn tại; phù hợp kiểm soát production |
| Bật | Bật | Có thể tự bổ sung cả address và queue theo protocol/routing được cấu hình |
| Bật | Tắt | Có thể tạo address nhưng **không tự bảo đảm** có queue nhận message |
| Tắt | Bật | Có thể tạo queue cần thiết **trên address đã tồn tại**, nhưng không tự tạo address mới |

Các câu mô tả là **khả năng theo chính sách**, không phải lời cam kết mọi thao tác sẽ cho kết quả giống nhau. Một lệnh gửi JMS Queue, một kết nối AMQP hoặc một lệnh tạo consumer Core API có thể kích hoạt đường tạo đích khác nhau. **Routing type** và quyền truy cập cũng quyết định thành công hay thất bại. Muốn xác minh, phải đọc **cả address, queue và binding thực tế** sau thao tác.

### 2.2. Mẫu tên address và thứ tự lựa chọn chính sách

Artemis thường dùng dấu chấm để phân đoạn tên, với wildcard:

- **\***: một đoạn.
- **#**: không hoặc nhiều đoạn, theo cú pháp wildcard cấu hình của Artemis.

Ví dụ **match="lab.auto.#"** dùng cho namespace bắt đầu bởi **lab.auto**; **match="payments.#"** dùng cho các address thuộc miền payments. Ký tự wildcard trong **match** chỉ dùng để chọn chính sách; không có nghĩa broker phải tạo một address tên nguyên văn “lab.auto.#”.

Khi có các policy chồng lấn, Artemis chọn address-setting có mức khớp phù hợp theo thuật toán wildcard của phiên bản. Cách an toàn là **đọc lại policy hiệu lực với tên cụ thể** và tránh cấu hình phụ thuộc vào những giả định về độ ưu tiên khó quan sát.

## 3. Cấu hình mẫu: sandbox tạo động, production phải tạo trước

Giả sử một nhóm cần:

- **lab.auto.***: tự tạo destination thử nghiệm, tự dọn sau khi không còn message và consumer.
- **payments.***: queue thanh toán có owner, được khai báo trước, không tự tạo/xóa.
- Một instance Artemis dành cho thực hành, có quyền và persistence phù hợp.

### 3.1. Fragment address-settings

Đặt các phần tử sau trong phần **address-settings** của cấu hình **broker.xml** Artemis:

~~~xml
<address-settings>
    <!-- Namespace động cho sandbox, không dùng cho dữ liệu nghiệp vụ thật -->
    <address-setting match="lab.auto.#">
        <auto-create-addresses>true</auto-create-addresses>
        <auto-create-queues>true</auto-create-queues>

        <default-address-routing-type>ANYCAST</default-address-routing-type>
        <default-queue-routing-type>ANYCAST</default-queue-routing-type>

        <auto-delete-queues>true</auto-delete-queues>
        <auto-delete-queues-delay>60000</auto-delete-queues-delay>
        <auto-delete-queues-message-count>0</auto-delete-queues-message-count>

        <auto-delete-addresses>true</auto-delete-addresses>
        <auto-delete-addresses-delay>120000</auto-delete-addresses-delay>
    </address-setting>

    <!-- Namespace nghiệp vụ yêu cầu provisioning có kiểm soát -->
    <address-setting match="payments.#">
        <auto-create-addresses>false</auto-create-addresses>
        <auto-create-queues>false</auto-create-queues>
        <auto-delete-addresses>false</auto-delete-addresses>
        <auto-delete-queues>false</auto-delete-queues>
    </address-setting>
</address-settings>
~~~

Đây là **mảnh cấu hình** để lồng vào cấu trúc **broker.xml** của một phiên bản Artemis tương thích, không phải toàn bộ file broker. Hai giá trị **60000** và **120000** trong phần delay được biểu diễn bằng **mili giây**. Lịch quét và thời điểm thực thi của broker khiến thao tác xóa không nhất thiết xảy ra đúng tại mili giây thứ 60.000 hoặc 120.000.

**auto-delete-queues-message-count=0** dùng để yêu cầu queue phải đạt ngưỡng **không còn message** khi được xét thu hồi. Khi kiểm chứng, phải xem thêm các message đang **delivering/in-flight**, scheduled delivery và thông tin queue của phiên bản đang dùng. Đừng dựa vào một counter tổng quát nếu chưa hiểu broker có tính message đang giao trong counter đó hay không.

**default-address-routing-type / default-queue-routing-type=ANYCAST** hỗ trợ việc tạo tự động có định hướng khi thao tác không chỉ rõ routing type. Dù vậy, cách JMS Topic, AMQP hoặc Core client chỉ định destination vẫn ảnh hưởng routing; không dùng một namespace auto-create ANYCAST mặc định để phát sự kiện cần **MULTICAST** mà không cấu hình và thử riêng.

### 3.2. Khai báo trước queue production

Tương ứng với **payments.#**, khai báo đích vật lý:

~~~xml
<addresses>
    <address name="payments.charge.commands.v1">
        <anycast>
            <queue name="payments.charge.commands.v1"
                   durable="true"/>
        </anycast>
    </address>
</addresses>
~~~

Đến đây có **hai điều kiện độc lập**:

1. Chính sách không cho ứng dụng tự tạo/xóa các đích payments.
2. Queue và address **payments.charge.commands.v1** đã được quản trị viên/provisioner khai báo.

Nếu thiếu điều kiện 2, chỉ tắt auto-create không tạo ra một queue có thể dùng được. Nếu thiếu điều kiện 1, một producer gõ sai thành **payments.charges.commands.v1** có thể khiến broker tạo một đích mới, tùy quyền người dùng và protocol.

### 3.3. Bảo mật vẫn là lớp kiểm soát riêng

Các cờ auto-create/auto-delete **không thay thế ACL**. Một ứng dụng gửi được vào namespace không có nghĩa nó nên có toàn quyền tạo hay xóa queue.

Khi thiết kế quyền Artemis, kiểm tra nhóm permission thích hợp với bản đang dùng, chẳng hạn:

- **send**, **consume** cho producer/consumer;
- **createAddress** và quyền tạo queue như **createDurableQueue**, **createNonDurableQueue** khi cho phép tự tạo/đăng ký;
- các quyền **deleteDurableQueue**, **deleteNonDurableQueue**, **deleteAddress**, **manage** dành cho tác vụ cần chúng, giới hạn theo vai trò.

Không cấp quyền manage cho producer chỉ để “khắc phục lỗi queue không tồn tại”. Với namespace động, nên tách tài khoản sandbox có quota và giới hạn tài nguyên; với production, dùng provisioning account độc lập với tài khoản ứng dụng runtime.

## 4. Chính xác lúc nào tài nguyên tự xuất hiện?

Khả năng tạo tự động không nhất thiết được kích hoạt khi code Java gọi phương thức tạo đối tượng Destination.

~~~mermaid
sequenceDiagram
    participant P as Java JMS Producer
    participant B as Artemis Broker
    participant A as Address Registry
    participant Q as Queue Registry
    P->>P: createQueue("lab.auto.demo.commands.v1")
    Note over P: Tạo handle Destination phía client
    P->>B: send(message)
    B->>B: Kiểm tra protocol, quyền, policy, routing
    alt Được tạo tự động theo cấu hình
        B->>A: Tạo address nếu chưa tồn tại
        B->>Q: Tạo/bind queue nếu cần và được phép
        B->>Q: Enqueue message
        B-->>P: Kết quả send/commit
    else Không thỏa policy hoặc quyền
        B-->>P: Lỗi hoặc kết quả đặc thù của thao tác/protocol
    end
~~~

**Thời điểm tạo thực sự** phụ thuộc đường đi: producer send, consumer attach, JMS durable subscription, Core API/AMQP hoặc management operation. Sơ đồ minh họa tuyến gửi JMS Queue thường gặp, không quy định mọi implementation thực hiện đúng từng lời gọi như một transaction riêng.

### 4.1. Tình huống A: address và queue đều chưa có

Trong namespace **lab.auto.#**:

1. Ứng dụng gửi persistent message đến **lab.auto.demo.commands.v1**.
2. Nếu client, routing và ACL cho phép, broker có thể tạo address ANYCAST và queue tương ứng.
3. Message vào queue; nếu chưa có consumer, message vẫn đang chờ.
4. Đọc console quản trị để xác nhận **tên address, tên queue, routing type, durability và trạng thái auto-created**.

Điểm dễ nhầm: **send thành công** không chứng minh consumer đã tồn tại. Cần kiểm tra queue binding và số message thực tế.

### 4.2. Tình huống B: address có sẵn nhưng thiếu queue

Nếu **auto-create-addresses=false**, **auto-create-queues=true** và address đã tồn tại, một thao tác có khả năng kích hoạt tạo queue vẫn có thể tạo queue cần thiết theo policy. Nếu address chưa tồn tại thì không có cơ sở để giả định thao tác tự hoàn thành.

Đây là lý do phải quan sát **độc lập** cả address và queue, thay vì chỉ nhìn danh sách destination JMS trên dashboard.

### 4.3. Tình huống C: tên đúng nhưng routing type sai

Một address được tạo như **ANYCAST** không tự biến thành publish/subscribe theo kiểu **MULTICAST** chỉ vì ứng dụng xem tên đó là “events”. Nếu producer và consumer dùng protocol hoặc routing hint khác nhau, message có thể đi vào queue ngoài dự kiến hoặc không đến consumer.

Quy tắc kiểm soát:

- Dành namespace và policy riêng cho command queue và event topic.
- Với message quan trọng, **pre-provision routing type** và subscription queue rõ ràng.
- Thử cả đường producer và consumer, đọc queue binding sau khi gửi.
- Không mặc định tên có hậu tố **events** tự khiến Artemis chọn MULTICAST.

## 5. Chính xác lúc nào một queue được tự xóa?

**Tự tạo** và **tự xóa** là hai quyết định tách biệt. Một queue được tạo tự động có thể tồn tại lâu nếu còn consumer hoặc message; một queue được khai báo thủ công có thể không thuộc phạm vi tự xóa dù các cờ trong address-settings đang bật.

Có thể hình dung quá trình kiểm tra như sau:

~~~mermaid
flowchart TD
    A["Queue tồn tại"] --> B{"Queue thuộc diện được auto-delete?"}
    B -->|Không| K["Giữ queue"]
    B -->|Có| C{"Còn consumer / chưa thỏa điều kiện?"}
    C -->|Có| K
    C -->|Không| D{"Message count đáp ứng ngưỡng?"}
    D -->|Không| K
    D -->|Có| E["Chờ delay / vòng quét của broker"]
    E --> F{"Kiểm tra lại điều kiện"}
    F -->|Không còn thỏa| K
    F -->|Vẫn thỏa| G["Auto-delete queue"]
    G --> H{"Address thuộc diện auto-delete và không còn queue?"}
    H -->|Không| I["Giữ address"]
    H -->|Có| J["Chờ address delay rồi xét thu hồi"]
~~~

Sơ đồ là mô hình giải thích điều kiện, **không phải mô tả thuật toán nội bộ đầy đủ**. Những điều kiện cụ thể còn phụ thuộc đặc tính queue, phương thức tạo queue và phiên bản broker.

### 5.1. Queue có message nhưng không có consumer

Ví dụ queue **lab.auto.demo.commands.v1** đang chứa 40 message; tất cả consumer tắt. Với chính sách **auto-delete-queues-message-count=0**, queue **chưa đủ điều kiện thu hồi vì còn backlog**.

Đây là một kiểm tra quan trọng khi consumer phải offline vài phút. Cờ auto-delete bật không đồng nghĩa queue bị xóa ngay khi một worker bị restart.

### 5.2. Queue không có message nhưng còn consumer

Một consumer vẫn gắn với queue, dù không xử lý message. Queue thường chưa đủ điều kiện auto-delete nếu điều kiện thu hồi yêu cầu không còn consumer. Đừng lẫn **queue trống** với **queue không còn người đăng ký**.

### 5.3. Queue vừa hết message và consumer vừa đóng

Khi message count đạt ngưỡng và consumer count về 0, broker có thể bắt đầu xét/đợi khoảng **auto-delete-queues-delay**. Nếu worker mới kết nối lại, hoặc message mới xuất hiện trước lúc dọn, điều kiện có thể thay đổi và queue tiếp tục tồn tại.

Thực tế phải kiểm chứng bằng management view: số consumer, message count, trạng thái auto-created, thời điểm tạo và queue binding. Không dùng một lệnh gửi/nhận chạy quá nhanh làm bằng chứng rằng auto-delete “không hoạt động”.

### 5.4. Queue được tạo thủ công hoặc thuộc JMS durable subscription

Phải phân biệt ít nhất các trường hợp sau:

| Nguồn gốc | Diễn giải vòng đời |
|---|---|
| **Queue tự tạo** do auto-create | Thường là đối tượng được policy auto-delete xét thu hồi khi đủ điều kiện |
| **Queue khai báo tĩnh trong broker.xml** | Có chủ đích vận hành lâu dài; không mặc nhiên bị xóa chỉ vì tắt consumer |
| **Queue tạo bằng công cụ quản trị / Core API** | Có thể chịu cờ hoặc thuộc tính auto-delete riêng; cần kiểm tra **auto-delete-created-queues** và metadata của queue |
| **JMS non-durable topic subscription** | Đích nhận gắn với vòng đời subscription/consumer; broker có thể dọn theo cơ chế của subscription |
| **JMS durable topic subscription** | Phải tồn tại qua thời gian subscriber offline theo hợp đồng; không được suy luận sẽ bị xóa như non-durable subscription |

Với **durable subscription**, thao tác **unsubscribe** của JMS khác hoàn toàn với **close consumer**. Closing chỉ ngừng nhận; unsubscribe hủy danh tính subscription khi đủ điều kiện, có thể làm mất backlog của subscriber. Không dùng auto-delete để thay thế quy trình quản lý và thu hồi subscription bền vững.

### 5.5. Address có thể ở lại sau khi queue bị xóa

**auto-delete-addresses** thường xét những address thuộc diện tạo động khi **không còn queue** phụ thuộc, sau delay được cấu hình. Address có queue tĩnh hoặc subscription khác **không trống** chỉ vì một queue vừa bị xóa.

Khi điều tra “queue mất nhưng address vẫn còn”, hãy kiểm tra:

- Address được tạo bằng auto-create hay provision thủ công?
- Còn queue nào khác gắn với address?
- Delay auto-delete-addresses đã tới hạn chưa?
- Có thao tác producer/consumer nào khiến address/queue được tạo lại?
- Có subscription động hoặc cơ chế protocol/cluster nào đang giữ binding?

Đừng cưỡng bức xóa address để “dọn cho sạch” nếu còn subscription hoặc queue đang dùng.

## 6. Bài lab Artemis: tạo động, nhận xong rồi tự thu hồi

### 6.1. Chuẩn bị

Dùng **một Artemis broker dành riêng cho thử nghiệm** với cấu hình **lab.auto.#** ở mục 3 và persistence hoạt động. Chuẩn bị:

- JDK/Maven phù hợp với phiên bản **Artemis JMS client**.
- Thư viện client **org.apache.activemq:artemis-jms-client** dùng API **javax.jms** tương thích với mã mẫu. Nếu dự án dùng Jakarta Messaging, chọn client Jakarta tương ứng và đổi toàn bộ import thành **jakarta.jms**.
- Tài khoản lab được phép connect/send/consume và tạo đích trong **lab.auto.#**; không sử dụng tài khoản quản trị production.
- Biến môi trường **MQ_URL**, **MQ_USER**, **MQ_PASSWORD**; ví dụ URL **tcp://localhost:61616** chỉ đúng khi broker đã mở acceptor tương ứng.
- Console quản trị hoặc management API để tra cứu **addresses, queues, consumerCount, messageCount, routingType và autoCreated** nếu phiên bản cung cấp trường này.

**Không** tự động tạo thử namespace payments hoặc xóa bất kỳ queue ngoài sandbox.

### 6.2. Mã Java producer/consumer dùng một queue định danh ổn định

~~~java
import java.util.UUID;
import javax.jms.ConnectionFactory;
import javax.jms.DeliveryMode;
import javax.jms.JMSConsumer;
import javax.jms.JMSContext;
import javax.jms.Message;
import javax.jms.Queue;
import javax.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class AutoDestinationLab {
    private static final String DEST = "lab.auto.demo.commands.v1";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Use: send | consume");
        }

        String url = required("MQ_URL");
        String user = required("MQ_USER");
        String password = required("MQ_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        try (JMSContext context = factory.createContext(
                 user, password, JMSContext.SESSION_TRANSACTED)) {

            // Đây là một handle JMS; bản thân lời gọi không phải
            // lệnh quản trị tạo queue vật lý trên server.
            Queue queue = context.createQueue(DEST);

            if ("send".equals(args[0])) {
                TextMessage msg = context.createTextMessage(
                    "{\"job\":\"index-document\",\"documentId\":\"doc-42\"}");
                String eventId = UUID.randomUUID().toString();
                msg.setStringProperty("eventId", eventId);

                context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .send(queue, msg);

                context.commit();
                System.out.println("SEND COMMITTED: " + eventId);
            } else if ("consume".equals(args[0])) {
                try (JMSConsumer consumer = context.createConsumer(queue)) {
                    Message msg = consumer.receive(5000);
                    if (msg == null) {
                        System.out.println("No message within 5 seconds");
                        return;
                    }

                    System.out.println("RECEIVED: "
                        + msg.getStringProperty("eventId"));
                    // Lab: giả lập xử lý thành công.
                    // Thực tế phải commit nghiệp vụ idempotent trước JMS ack.
                    context.commit();
                    System.out.println("RECEIVE COMMITTED");
                }
            } else {
                throw new IllegalArgumentException("Use: send | consume");
            }
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing env: " + name);
        }
        return value;
    }
}
~~~

**Tương thích Java:** phương thức **String.isBlank()** yêu cầu Java 11 trở lên. Nếu chạy JDK 8 theo yêu cầu client cũ, thay bằng **value.trim().isEmpty()**. Một số bản client Artemis mới dùng Jakarta Messaging thay vì javax; chọn dependency phù hợp, không trộn namespace.

Chương trình **không triển khai thao tác xóa**; quá trình xóa phải do broker thực hiện theo policy, có quan sát bằng công cụ quản trị.

### 6.3. Kịch bản kiểm chứng từng bước

**Bước 1 — Trạng thái trước gửi.** Dùng console/management view kiểm tra chưa có address và queue **lab.auto.demo.commands.v1**. Nếu chúng đã tồn tại từ lần lab trước, hãy dùng một namespace thử riêng đã được phép hoặc thực hiện quy trình dọn trong sandbox; không kết luận “auto-create” từ tài nguyên đã tồn tại.

**Bước 2 — Gửi một message.** Chạy chương trình với argument **send**. Kiểm tra đã xuất hiện address và queue, cùng routing ANYCAST. Quan sát message count tăng khi không có consumer. Nếu client báo lỗi, kiểm tra **ACL, protocol, hiệu lực của match, auto-create flags và routing**.

**Bước 3 — Ngắt hết consumer, giữ backlog.** Chưa chạy **consume**. Đợi dài hơn thời gian **auto-delete-queues-delay** được cấu hình, rồi đọc lại trạng thái. Với message count lớn hơn ngưỡng 0, queue vẫn phải được giữ theo điều kiện policy của bài lab. Đây là kiểm tra cho tình huống consumer offline.

**Bước 4 — Nhận và commit.** Chạy **consume** một lần. Xác minh message được nhận và transaction JMS commit. Sau khi chương trình thoát, consumer count phải về 0; message count và các message đang giao cần đạt điều kiện phù hợp.

**Bước 5 — Quan sát dọn queue.** Đọc trạng thái định kỳ sau khoảng delay đã đặt. Khi broker đã xét đủ điều kiện, queue auto-created có thể bị xóa. Chỉ sau khi queue cuối cùng trên address biến mất, address auto-created mới có thể được xét xóa sau **auto-delete-addresses-delay**.

**Bước 6 — Gửi trở lại.** Chạy **send** lần nữa sau khi đã xác nhận queue/address cũ biến mất. Nếu auto-create vẫn được phép và không có drift chính sách, broker sẽ tạo tài nguyên trở lại theo nhu cầu. Kiểm tra đây là lần tạo mới chứ không phải message được “khôi phục” từ queue cũ.

### 6.4. Bảng kết quả mong đợi

| Thời điểm | Queue | Message chờ | Consumer | Giải thích |
|---|---|---|---|---|
| Trước lab | Chưa có | Không | Không | Chưa từng có thao tác kích hoạt tạo |
| Sau **send** | Có | 1 | 0 | Tài nguyên có thể được auto-create, message được enqueue |
| Đợi khi chưa nhận | Có | 1 | 0 | Chưa đạt ngưỡng messageCount=0 |
| Sau **consume + commit** | Có trước khi dọn | 0 | 0 | Bắt đầu đủ điều kiện xét xóa |
| Sau delay và lần quét đủ điều kiện | Có thể không còn | 0 | 0 | Tùy lịch quét/phiên bản và nguồn gốc queue |
| Sau address delay, nếu không còn queue | Có thể không còn address | — | — | Chỉ xóa address thuộc diện auto-delete |

Nếu queue không bị xóa, **đó là một dữ kiện cần điều tra**, không phải lý do lập tức tăng quyền xóa thủ công. Hãy kiểm tra autoCreated, số message, consumer count, config hiệu lực, thời gian delay và phiên bản Artemis.

## 7. Lab đối chứng: tắt auto-create với destination production

Để chứng minh sự khác nhau giữa **handle JMS** và **tài nguyên broker**, hãy chạy một bài đối chứng trong môi trường test với namespace **payments.#**.

1. Provision sẵn **payments.charge.commands.v1** bằng cấu hình ở mục 3.2.
2. Dùng chương trình Java tương tự nhưng tham chiếu đúng tên đó: send/consume hoạt động khi ACL được cấp phù hợp.
3. Trong sandbox, đổi tên thành **payments.charges.commands.v1**, một destination chưa được provision.
4. Thử send, ghi lại lỗi/behavior của client và broker. **Không mặc định tất cả phiên bản đều trả cùng loại exception hoặc cùng thời điểm trả lỗi**.
5. Kiểm tra management view: không được xuất hiện address/queue mới chỉ vì typo nếu chính sách và quyền đã khóa đúng.
6. Bật lại tên hợp lệ, xác nhận luồng hoạt động, rồi hoàn nguyên mọi thay đổi test.

Nếu test số 4 vẫn làm broker tạo tài nguyên mới, điều tra **address-setting nào thực sự match**, có policy wildcard chồng lấn không, và credential có cho phép thao tác tạo qua đường quản trị/protocol hay không.

### 7.1. Thử thêm hai trạng thái “nửa tự động”

Tạo hai cấu hình test tách biệt, không áp dụng chồng lên production:

- **Address được provision, queue chưa có**, bật **auto-create-queues**, tắt **auto-create-addresses**: xem thao tác JMS Queue hoặc Core consumer có tạo queue trên address cũ hay không.
- **Address chưa có**, bật **auto-create-addresses**, tắt **auto-create-queues**: kiểm tra liệu address xuất hiện nhưng chưa có queue/binding để message tồn tại được hay không.

Ghi lại **loại client, protocol, routing type, username, thao tác kích hoạt và kết quả thực**, vì một kết quả quan sát không đại diện mọi đường đi của broker.

## 8. JMS Topic và durable subscription: chỗ dễ cấu hình sai nhất

Auto-create và auto-delete nguy hiểm nhất khi kết hợp với **MULTICAST** và subscription động. Với topic, address phát sự kiện có thể tồn tại trước, còn **subscription queue** chỉ xuất hiện khi subscriber đăng ký.

~~~text
Address: orders.lifecycle.events.v1     MULTICAST
  ├── Queue của subscription inventory (durable)
  ├── Queue của subscription notification (durable)
  └── Queue tạm của subscriber báo cáo (non-durable)
~~~

### 8.1. Một consumer tắt không đồng nghĩa phải xóa subscription queue

- **Non-durable subscriber** thường gắn với vòng đời consumer/connection; broker có thể thu hồi queue nhận của nó sau khi không còn sử dụng theo quy tắc provider.
- **Durable subscriber** được tạo để giữ message khi consumer offline; việc đóng kết nối **không phải thao tác unsubscribe**.
- **Shared durable subscription** cho nhiều consumer chia sẻ một subscription nếu JMS version/provider hỗ trợ; không suy ra rằng mỗi instance tạo một subscription bền vững mới.
- Nếu tắt auto-create-queues cho topic address, việc một client muốn **tạo durable subscription mới** có thể bị ảnh hưởng. Cần provision hoặc cấp quyền tạo queue subscription đúng cách theo sản phẩm, API và version.

### 8.2. Thực hành nhận biết hai vòng đời

1. Provision address MULTICAST **lab.events.v1** và cấu hình policy sandbox theo mục tiêu lab.
2. Tạo một **non-durable** subscriber, publish message và đóng subscriber.
3. Quan sát queue subscription được tạo/xóa theo cơ chế client và broker.
4. Tạo một **durable** subscriber với **clientID** và **subscription name** ổn định; nhận một message, ngắt kết nối.
5. Publish thêm message khi subscriber offline; kiểm tra backlog của durable subscription.
6. Kết nối lại bằng **cùng danh tính** và đọc backlog.
7. Chỉ dùng **unsubscribe** sau khi đã xác nhận không còn dữ liệu cần giữ trong môi trường lab.

**Tiêu chí đạt:** giải thích được vì sao policy auto-delete dành cho queue động không được dùng làm bằng chứng rằng durable subscription không còn tồn tại, cũng như vì sao đổi subscription name theo pod có thể tạo backlog bị bỏ quên.

## 9. Giải thích ba sự cố thường gặp

### 9.1. Queue tự tạo tràn lan vì tên sai

**Triệu chứng:** trên broker có **lab.auto.order.command.v1**, **lab.auto.orders.command.v1**, **lab.auto.order.commands.v1** dù ứng dụng chỉ có một luồng nghiệp vụ.

**Nguyên nhân có thể:** auto-create được bật trong namespace rộng; producer có quyền tạo đích; tên destination là chuỗi tự do trong code/config; ứng dụng không kiểm tra catalog.

**Cách xử lý:**

1. Tìm producer hoặc consumer nào tham chiếu từng tên, dừng việc tạo thêm lỗi.
2. Xác định queue nào đang có backlog, message in-flight hoặc DLQ liên quan; tuyệt đối không xóa tất cả chỉ vì tên “lạ”.
3. Chuẩn hóa tên bằng catalog/constant và validation trong CI.
4. Với production, pre-provision và hạn chế auto-create; với sandbox, giới hạn namespace, quota và auto-delete đủ chặt.
5. Dọn queue rác **sau khi** có quyết định xử lý mọi message tồn đọng.

### 9.2. Queue “không chịu tự xóa”

**Triệu chứng:** đã đặt **auto-delete-queues=true**, consumer rời đi từ lâu, nhưng queue vẫn hiện.

**Lộ trình kiểm tra:**

~~~text
Queue có đúng namespace / address-setting match không?
    ↓
Có được đánh dấu auto-created hoặc thuộc diện auto-delete không?
    ↓
Consumer count có thực sự bằng 0 không?
    ↓
Message count có đáp ứng auto-delete-queues-message-count không?
    ↓
Còn delivering / scheduled / redelivery hoặc subscription đặc biệt không?
    ↓
Đã qua auto-delete-queues-delay và vòng quét chưa?
    ↓
Có client nào reconnect hoặc tự tạo lại queue không?
    ↓
Nếu vẫn chưa rõ: kiểm tra broker log, management metadata và
hành vi của đúng phiên bản Artemis.
~~~

Không nên khắc phục bằng cách đổi ngưỡng message count lên quá cao. Cho phép xóa queue còn backlog có thể phá hủy message nghiệp vụ; chỉ thực hiện trong một bài test cô lập có dữ liệu được phép bỏ.

### 9.3. Queue “bị mất” sau khi worker restart

**Triệu chứng:** worker ngắt rồi chạy lại thì thấy queue không còn, hoặc producer phải đợi queue được tạo lại.

Khả năng cần xác minh: queue thuộc diện auto-delete, đã hết message, consumer count về 0 và delay quá ngắn; hoặc queue bị quản trị viên xóa; hoặc app đang kết nối sang một broker/environment khác.

**Cải thiện:**

- Queue nghiệp vụ cần giữ bền vững: provision tĩnh, khóa auto-delete, cấu hình durable và storage.
- Queue động phục vụ kết nối ngắn hạn: dùng delay hợp lý để tránh tạo/xóa liên tục khi rolling deploy.
- Mọi loại queue: log tên đích, address, broker endpoint, queue ID khi có và nguyên nhân lifecycle.
- Không xem **persistence** như cơ chế chống xóa queue theo policy: khi queue bị xóa hợp lệ, việc lưu bền vững của message trước đó không có nghĩa queue tự sống lại kèm backlog.

## 10. Quan sát và giới hạn tài nguyên đối với auto-create

Khi cho phép runtime tạo queue động, rủi ro không chỉ là số message; **số lượng address và queue** cũng ảnh hưởng metadata, memory, storage và khả năng vận hành.

| Chỉ số / dấu hiệu | Mục tiêu |
|---|---|
| Tổng số address/queue theo namespace | Phát hiện destination explosion |
| Số queue auto-created nhưng không có owner | Tìm queue do typo hoặc ứng dụng bỏ quên |
| Queue count, consumer count, message count | Kiểm tra điều kiện auto-delete |
| Delivering/in-flight, scheduled, redelivery | Tránh kết luận queue trống khi còn công việc |
| Tuổi message lớn nhất và backlog | Phát hiện queue không có consumer hữu ích |
| Journal/paging/disk usage | Kiểm tra chi phí của destination/message |
| Số lần tạo/xóa theo phút | Phát hiện churn do restart hoặc delay quá ngắn |
| Auth/authorization failures | Phát hiện client cố tạo destination không được phép |

Trong production, hữu ích khi so sánh **destination catalog** với trạng thái broker thực tế, nhưng phải cho phép các queue nội bộ và subscription được provider tạo hợp lệ. Đừng xây công cụ xóa tự động mọi queue “không có trong catalog”.

**Cảnh báo khuyến nghị cho sandbox:** số queue mới vượt tốc độ dự kiến, message age tăng khi consumer count bằng 0, hoặc một producer tạo nhiều tên khác nhau trong cùng phút. Cảnh báo nên dựa trên baseline và quota riêng của môi trường.

## 11. Kế hoạch triển khai chính sách an toàn

Không nên thay đồng loạt auto-create và auto-delete trên broker đang có backlog. Một quy trình triển khai có kiểm chứng:

1. **Kiểm kê:** xuất danh sách address, queue, routing type, auto-created flag, consumer count, message count và chủ sở hữu của namespace sắp thay đổi.
2. **Phân loại:** queue nghiệp vụ bền vững, JMS durable subscription, non-durable subscription, temporary/dynamic queue và queue hệ thống (DLQ/expiry).
3. **Thiết kế:** đặt policy riêng cho namespace động và namespace cần provision; tránh wildcard quá rộng ảnh hưởng destination hiện hữu.
4. **Kiểm thử:** thực hiện lab send/consume, consumer offline, restart, message backlog, typo, tạo lại và subscriber durable.
5. **Provision trước:** tạo thủ công những address/queue production mà app vẫn phải truy cập khi auto-create bị tắt.
6. **Triển khai cấu hình:** sử dụng quy trình cập nhật cấu hình của phiên bản Artemis, xác minh cấu hình thực sự có hiệu lực; đừng giả định thay file trên đĩa là broker đã áp dụng.
7. **Readback:** so khớp tên và policy hiệu lực; thử producer/consumer có credential quyền tối thiểu.
8. **Theo dõi:** số destination mới, broker logs, backlog, DLQ, ứng dụng báo lỗi và khả năng reconnect.
9. **Thu hồi có kiểm soát:** nếu cần xóa queue cũ, xác nhận ngừng nguồn gửi, pending/in-flight/scheduled/redo đã được xử lý trước khi gọi lệnh xóa rõ đích.

### 11.1. Ma trận chọn chính sách theo loại workload

| Loại workload | Auto-create | Auto-delete | Lý do |
|---|---|---|---|
| **Queue thanh toán, đặt hàng, giao vận quan trọng** | Thường tắt; provision trước | Thường tắt | Backlog phải tồn tại khi consumer offline/restart |
| **Queue công việc thử nghiệm sandbox** | Có thể bật trong prefix riêng | Có thể bật với messageCount=0 và delay | Đỡ công tạo đích nhưng tránh tích rác vô hạn |
| **JMS durable subscription** | Thiết kế theo API/provision/ACL | Không suy từ policy queue động; quản lý unsubscribe | Cần giữ trạng thái offline |
| **Non-durable topic subscriber** | Theo cơ chế subscription của client | Thường theo vòng đời subscription | Không phải nơi giữ backlog offline |
| **Temporary reply queue** | Theo API temporary destination | Theo vòng đời connection/destination | Không dùng thay queue nghiệp vụ |
| **DLQ hoặc expiry queue** | Ưu tiên tạo trước, có owner | Tránh tự xóa tùy tiện | Chứa dữ liệu lỗi cần điều tra, replay |

Bảng là **định hướng thiết kế**, không phải bộ default của mọi Artemis version.

## 12. Bài tập tình huống cuối bài

Một hệ thống xử lý đơn hàng dùng Artemis. Developer bật toàn bộ auto-create/auto-delete theo wildcard rộng. Trong đêm, dịch vụ thanh toán tắt 15 phút để nâng cấp; một producer typo tên queue, một consumer xử lý lỗi lặp nhiều lần và hệ thống có durable subscription nhận sự kiện kho.

Hãy thiết kế các thay đổi sau:

- Tên queue thanh toán **payments.charge.commands.v1** được provision và không thể tự biến mất khi consumer ngắt kết nối.
- Namespace **lab.auto.#** vẫn cho phép tạo động, nhưng sau khi queue thật sự trống và không có consumer sẽ dọn với delay phù hợp.
- Typo **payments.charges.commands.v1** không tạo queue production mới.
- DLQ và expiry queue được giữ có quản trị; policy auto-delete không vô tình thu hồi chúng.
- Durable subscription kho không bị hủy chỉ vì pod restart, và không đổi danh tính khi deploy.
- Có chỉ số để phân biệt **chưa route**, **đã enqueue**, **đang in-flight**, **đã ack**, **đã chuyển DLQ** và **đã xóa queue**.

**Bài nộp yêu cầu:**

1. Hai đoạn **address-settings** theo namespace và một đoạn khai báo **addresses** production.
2. Bảng phân loại từng queue: nguồn gốc, owner, có đủ điều kiện auto-delete hay không, dữ liệu còn chờ.
3. Kết quả lab trước/sau send, consume, hết delay và auto-create lại, kèm quan sát management.
4. Giải thích vì sao **messageCount=0** và **consumerCount=0** chưa đủ để kết luận có thể xóa mọi queue.
5. Kế hoạch rollout, rollback và giám sát để thay policy trên broker có dữ liệu thật.

### Tự kiểm tra nhanh

- **Có thể bật auto-delete-addresses mà tắt auto-delete-queues không?** Có, các cờ độc lập. Nhưng address còn queue sẽ không tự mất chỉ vì auto-delete-addresses bật.
- **Tắt auto-create-queues có khiến queue đã provision dừng nhận?** Không. Cờ chi phối việc tạo **queue mới**; queue tồn tại vẫn có thể nhận nếu routing/ACL và broker hoạt động đúng.
- **AUTO_ACKNOWLEDGE có liên quan auto-delete-queues không?** Gián tiếp: ack làm message hoàn tất, có thể giúp message count đạt ngưỡng; không phải tín hiệu “xóa queue ngay”.
- **Bật auto-delete-queues-message-count=0 thì message chưa ack có được bảo toàn tuyệt đối?** Không nên khẳng định tuyệt đối từ một thuộc tính; cần hiểu metric, loại queue, cấu hình, transaction và behavior của phiên bản.
- **JMS createQueue có chắc tạo queue trong Artemis?** Không. Nó tạo handle ở client; việc có queue vật lý còn phụ thuộc thao tác, protocol, policy và quyền.
- **Artemis có cấu hình giống hệt ActiveMQ Classic không?** Không. Những thuộc tính **address-settings** trong bài là của **Artemis**; Classic có mô hình quản trị destination khác và không thể sao chép các XML này.

**Kết luận:** Auto-create giúp broker tiếp nhận destination động thuận tiện; auto-delete giúp dọn **những tài nguyên đủ điều kiện**, nhưng cả hai chỉ an toàn khi được ràng buộc theo **namespace, nguồn gốc queue, trạng thái consumer/message, delay, routing type và quyền**. Với luồng JMS quan trọng, hãy provision address/queue trước, xác minh cấu hình thực tế và quản lý durable subscription có chủ đích. Mọi điều chỉnh dọn tự động đều cần bài thử chứng minh **message cần giữ không bị mất khi consumer tạm ngừng**.
