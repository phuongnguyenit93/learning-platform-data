# Thu hồi journal, page và dữ liệu thông điệp không còn tham chiếu

> **Chương:** Lưu trữ Artemis  
> **Học phần:** INTEGRATION_MESSAGING_MESSAGE_BROKER_ACTIVEMQ — tìm hiểu ActiveMQ Classic và Artemis trong giao tiếp bất đồng bộ bằng queue/topic, routing và JMS; producer/consumer Java, acknowledgment, transaction, redelivery, DLQ, bảo mật và vận hành broker đáng tin cậy.  
> **Phạm vi:** Apache ActiveMQ **Artemis**, cụ thể là vòng đời của record journal, page files và large-message files sau khi thông điệp không còn tham chiếu. Ví dụ dùng Artemis 2.x, Java 17 và Jakarta JMS. Các cơ chế và tham số của ActiveMQ Classic KahaDB **không** được dùng thay cho Artemis.

## 1. Queue đã rỗng nhưng ổ đĩa vẫn lớn: đây có phải rò rỉ?

Một broker Artemis vận hành queue **orders.work**. Trong giờ cao điểm, hàng triệu message persistent đến nhanh hơn consumer; address chuyển sang paging và dung lượng lưu trữ tăng. Sau khi các consumer xử lý xong, queue message count giảm về 0 nhưng thư mục journal còn nhiều file và thư mục paging có thể chưa giảm ngay.

Ba kết luận sai thường gặp:

1. **ACK là xóa file ngay lập tức.** Thực tế ACK/commit giải phóng trách nhiệm giao lại của broker ở **tầng logic**. Không có ánh xạ một message thành một file độc lập phải bị xóa tức thời.
2. **Một queue rỗng nghĩa là message không còn tham chiếu.** Với multicast hoặc nhiều subscription, message có thể còn được một queue khác tham chiếu; DLQ và expiry queue cũng có thể lưu message.
3. **Có thể xóa journal/page files cũ để giảm dung lượng.** Các file này liên quan đến record recovery, transaction, cursor và tham chiếu; xóa thủ công có thể gây mất message hoặc không khôi phục được broker.

~~~mermaid
flowchart TD
    P["Persistent send"] --> R["Address routing"]
    R --> Q["Một hoặc nhiều queue reference"]
    Q --> A{"Tất cả reference đã kết thúc hợp lệ?"}
    A -->|Chưa| K["Phải giữ message/metadata cần thiết"]
    A -->|Rồi| L["Message logic không còn sống"]
    L --> J["Journal: reclaim, reuse hoặc compact"]
    L --> G["Paging: page cursor cleanup"]
    L --> M["Large-message: body cleanup"]
    J --> D["Dung lượng file vật lý có thể vẫn được giữ"]
    G --> D
    M --> D
~~~

**Luận điểm chính:** cần phân biệt ba mốc: **message hết tham chiếu**, **dữ liệu đủ điều kiện thu hồi/tái sử dụng**, và **block đĩa thực sự được trả cho filesystem**. Những mốc này không nhất thiết xảy ra cùng một thời điểm.

## 2. Artemis lưu những loại dữ liệu nào?

Các thư mục thường thuộc broker instance và được định nghĩa trong cấu hình broker.xml; đường dẫn thực có thể khác trên Docker, Kubernetes, Linux hoặc Windows.

| Khu vực | Thành phần cấu hình Artemis | Vai trò | Hành vi thu hồi |
|---|---|---|---|
| **Message journal** | journal-directory | Record message persistent, reference, ACK, transaction và metadata thông điệp | Record hết hiệu lực; file được reclaim, compact hoặc tái dùng |
| **Bindings journal** | bindings-directory | Queue, binding và metadata topology | Không biến mất chỉ vì message count bằng 0 |
| **Paging store** | paging-directory | Page files theo address khi broker paging | Cleanup page khi các subscription/cursor không còn cần message trên page |
| **Large message store** | large-messages-directory | Nội dung large message được lưu riêng | Xử lý theo vòng đời tham chiếu/message và cleanup |
| **Các nơi khác** | log, snapshot, backup, PVC, volume | Dữ liệu ngoài vòng đời ACK message | Cần chính sách retention/volume riêng |

Không suy dung lượng broker chỉ từ một folder. **Bindings**, **journal**, **paging** và **large messages** có trách nhiệm khác nhau.

### 2.1. Tham chiếu tồn tại ở đâu?

Một message được route tới một hoặc nhiều queue. Với address **MULTICAST**, hai queue có thể cùng cần message M1:

~~~text
                Address invoice.events
                        |
           +------------+------------+
           |                         |
     Queue accounting          Queue analytics
        reference M1              reference M1
           |                         |
      ACK thành công        consumer offline, chưa ACK
           |                         |
       hết reference        reference M1 vẫn còn
           +------------+------------+
                        |
             M1 chưa thể coi là
             hoàn toàn không còn dùng
~~~

Nếu consumer accounting xử lý xong mà consumer analytics chưa xử lý, broker không được làm mất payload cần giao cho analytics.

Đây là lý do bài toán thu hồi phải kiểm tra **toàn bộ queue/subscription được bind tới address**, không chỉ queue mà đội ứng dụng hay nhìn trên dashboard.

### 2.2. Những trường hợp chưa thể giải phóng

- **Message được dispatch nhưng chưa ACK**: consumer có thể chết, broker phải có khả năng redelivery.
- **JMS transaction chưa commit**: ACK chưa trở thành kết quả cuối cùng; rollback có thể khiến message được giao lại.
- **Prepared XA transaction**: broker có trách nhiệm recovery, không thể dọn tùy tiện record liên quan.
- **Durable subscription offline**: message vẫn có thể chờ subscriber quay lại.
- **Message bị chuyển sang DLQ/expiry queue**: message có thể đã rời queue gốc nhưng vẫn còn reference ở queue đích.
- **Scheduled delivery hoặc state đặc biệt**: message chưa tới thời điểm giao vẫn có thể phải được giữ.
- **Các page subscription/cursor**: broker vẫn cần page để phục vụ queue chưa đi hết dữ liệu.

Đặc biệt, **received** không phải **acknowledged**. Một log consumer cho thấy message đã nhận chưa chứng minh journal/page đủ điều kiện thu hồi.

## 3. Thu hồi journal: record logic chết nhưng file không nhất thiết mất

### 3.1. Journal không lưu một file cho mỗi message

Artemis journal là dạng ghi record tuần tự. Các bản ghi mô tả thêm message, thêm reference, xác nhận, transaction và trạng thái cần recovery. Khi ACK đến, broker không bắt buộc cắt ngay bytes của message bên trong file journal.

Ví dụ khái niệm:

~~~text
File J1:
  ADD message M1
  ADD reference M1 -> queue A
  ADD reference M1 -> queue B
  ADD message M2
  ACK M1 on queue A
  ACK M2 on queue A
  ... các record tiếp theo ...

Tại thời điểm này:
  - Reference M1 -> queue B vẫn còn sống.
  - Nhiều record khác đã hết vai trò logic.
  - File J1 vẫn là một file vật lý hợp lệ.
~~~

Artemis có thể dùng các record để tái dựng state sau broker restart. **Xóa một file vì thấy nó có nhiều record cũ có thể làm hỏng recovery**.

### 3.2. Reclaim, reuse và compaction là ba điều khác nhau

| Cơ chế | Ý nghĩa | Hệ quả quan sát |
|---|---|---|
| **Reclaim journal file** | File không còn record sống cần giữ nên có thể trở lại tập file khả dụng | Không đòi xóa file ngay |
| **Reuse / journal file pool** | File được giữ để ghi mới, giảm tạo/xóa file liên tục | Số byte trong journal directory có thể ổn định sau khi queue rỗng |
| **Compaction** | Tổ chức lại record sống từ các file thưa record để các file khác có thể được giải phóng/tái dùng | Có thể tốn I/O và không chạy sau từng ACK |
| **Filesystem release** | File được xóa/truncate hoặc block được OS/volume trả lại | Không theo tỷ lệ 1:1 với message ACK |

**Dấu hiệu có thể lành mạnh:** sau một đợt load, journal directory còn lớn nhưng ổn định trong nhiều chu kỳ gửi/nhận tiếp theo. Broker có thể **tái sử dụng dung lượng** thay vì trả toàn bộ cho OS.

**Dấu hiệu cần điều tra:** queue/backlog được xác nhận đã hết, nhưng journal, paging hoặc large-message directory vẫn tăng không giới hạn qua nhiều chu kỳ tương đương. Khi đó cần tìm reference chưa giải phóng, transaction/cursor bị giữ hoặc lỗi vận hành.

### 3.3. Các cấu hình ảnh hưởng journal

Mảnh XML dưới đây dùng cho **Artemis broker.xml**, trong vị trí hợp lệ của phần tử broker:

~~~xml
<journal-file-size>10485760</journal-file-size>
<journal-min-files>2</journal-min-files>
<journal-compact-min-files>10</journal-compact-min-files>
<journal-compact-percentage>30</journal-compact-percentage>
~~~

Giải thích:

- **journal-file-size**: kích thước file journal; ví dụ 10 MiB. Không dùng việc đổi thông số này như lệnh shrink một journal đang chứa dữ liệu.
- **journal-min-files**: journal giữ số file tối thiểu; vì thế thư mục journal có thể không trở về 0 byte.
- **journal-compact-min-files**: điều kiện về lượng file để xét compact, không có nghĩa cứ đủ N file là chúng bị xóa ngay.
- **journal-compact-percentage**: một tiêu chí compactor dùng khi đánh giá mật độ record còn sống; giá trị 30 không đồng nghĩa đã ACK 30% thì đĩa tự giải phóng 30%.

Các giá trị trên **chỉ minh họa**, không phải khuyến nghị production. Cần xét storage backend, file pool, workload, version và cấu hình thực tế trước khi thay đổi.

### 3.4. Khi nào journal file chưa reclaim được?

Một file có thể chứa **record còn sống**, dù nhiều message trong đó đã ACK. Broker vẫn cần những record đó cho recovery. Trong trường hợp này, việc thu hồi phụ thuộc vào journal lifecycle/compaction, chứ không thể cắt tùy tiện bytes giữa file.

Những tình huống cần kiểm tra:

1. Có queue hoặc durable subscription nào còn giữ reference không?
2. Có message unacked/delivering, scheduled, DLQ, expiry queue không?
3. Có transaction chưa commit hoặc prepared XA không?
4. Journal đang giữ file để **reuse** hay compactor chưa đến ngưỡng?
5. Producers vẫn ghi message mới trong khi bạn đo hay không?

**Không chạy lệnh xóa journal file trực tiếp**, kể cả khi broker đã stop. Cần runbook backup/restore và công cụ chính thức phù hợp phiên bản nếu có yêu cầu bảo trì thực sự.

## 4. Paging: page file tồn tại theo tiến độ của nhiều queue

### 4.1. Khi nào Artemis paging?

Với **address-full-policy = PAGE**, khi address đạt điều kiện đầy theo address settings, Artemis có thể chuyển message sang page files thay vì giữ toàn bộ backlog trong bộ nhớ.

Cấu hình lab ví dụ đặt trong phần **address-settings** hiện hữu:

~~~xml
<address-setting match="lab.storage.jobs">
    <address-full-policy>PAGE</address-full-policy>
    <max-size-bytes>2097152</max-size-bytes>
    <page-size-bytes>1048576</page-size-bytes>
</address-setting>
~~~

Đây là threshold nhỏ để chủ động quan sát paging:

- **max-size-bytes = 2 MiB**: ngưỡng kích thước address theo cơ chế broker; **không phải quota đĩa cố định**.
- **page-size-bytes = 1 MiB**: kích thước mục tiêu cho mỗi page file; kích thước file thực có thể bị ảnh hưởng bởi record và kích thước message.
- **PAGE**: chiến lược khi address đạt điều kiện theo cấu hình.

Nếu address cũng có những policy khác hoặc match rule tổng quát, hãy **hợp nhất cấu hình**, không đặt hai rule trùng rồi đoán rule nào được áp dụng. Đừng copy ngưỡng lab vào production.

### 4.2. Vì sao một page không thể xóa khi chỉ một queue đã ACK?

Page files là dữ liệu theo **address**, còn tiến độ tiêu thụ được theo dõi qua **page subscription/cursor** của các queue.

~~~text
                       Address A
                     Page P: M1..M100
                          |
               +----------+-----------+
               |                      |
          Queue fast              Queue slow
        đã ACK hết P           còn M60 chưa ACK
               |                      |
            cursor qua P       cursor còn cần P
               +----------+-----------+
                          |
                  Page P vẫn có dữ liệu
                  cần giữ cho Queue slow
~~~

Một page cần đủ điều kiện cleanup theo **mọi cursor/subscription liên quan**, không phải chỉ theo queue fast. Việc xóa page có thể xảy ra theo bước và có độ trễ so với commit ACK cuối.

**Ví dụ đặc biệt:** page chứa 1.000 message, 999 đã ACK nhưng một message vẫn được một durable subscription giữ lại. Page file chưa nhất thiết đủ điều kiện thu hồi; không có chuyện được xóa 99,9% bytes của file theo tỷ lệ số ACK.

### 4.3. Tắt trạng thái paging không có nghĩa page directory rỗng

Cần phân biệt:

- Address **đang page message mới** hay không.
- Có **page files chưa được dọn** hay không.
- Mỗi queue có bao nhiêu message **ready/delivering**.
- Các cursor đã hoàn tất những page nào.
- Có queue giữ message **expired**, **DLQ**, hoặc đang chờ redelivery không.

Một address có thể không còn ở trạng thái paging khi áp lực bộ nhớ giảm nhưng vẫn còn **paged backlog**. Vì vậy dashboard cần cả **address/page metrics và queue metrics**, không chỉ một cờ isPaging.

### 4.4. Vì sao không xóa thủ công page files?

Page files và state của page subscriptions/cursors có quan hệ với các record broker. Xóa file còn được tham chiếu có thể gây lỗi đọc, mất message hoặc lỗi recovery.

Những thao tác như xóa toàn bộ thư mục paging, journal hoặc large messages **không phải cách sửa cleanup**. Khi cần hủy message theo chính sách nghiệp vụ, phải dùng API quản trị broker phù hợp, xác nhận đúng queue/address, backup và impact analysis.

## 5. Large message: body file có vòng đời riêng

Một số message lớn được Artemis xử lý qua **large-message mechanism**, lưu phần body riêng tại **large-messages-directory**; journal giữ các dữ kiện cần thiết để quản lý message/reference. Ngưỡng xác định large message liên quan đến client/protocol/configuration, nên đừng khẳng định mọi message vượt một kích thước cố định đều có cùng đường đi trong mọi môi trường.

~~~text
Message metadata / queue references
            |
            +---- Journal / queue lifecycle
            |
            +---- Large-message body file
                         |
              còn reference cần dữ liệu?
                |                  |
               Có                 Không
                |                  |
            Tiếp tục giữ        Đủ điều kiện cleanup
~~~

Với multicast, hai queue có thể cùng tham chiếu một message. Khi queue A ACK còn queue B offline, broker vẫn cần body để giao cho B. Chỉ khi không còn reference cần giữ và các điều kiện lưu trữ phù hợp đã kết thúc, body mới đủ điều kiện cleanup.

**Tồn tại file lớn không tự động là leak.** Có thể còn message live hoặc công việc cleanup chưa hoàn tất. Ngược lại, khi không thấy file cũng không nên suy rằng mọi metadata/transaction đã ổn nếu chưa xác minh broker state.

### 5.1. So sánh dấu hiệu theo thư mục

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Journal directory không giảm sau ACK | File reuse/pool, record sống còn xen kẽ, compaction threshold |
| Paging directory còn nhiều file | Chưa ACK hết ở mọi queue, durable subscription offline, page cursor chưa giải phóng |
| Large-message directory còn file body | Message/reference còn sống hoặc cleanup chưa hoàn tất |
| Bindings directory còn file | Queue/binding metadata là phần lưu trữ riêng, không gắn 1:1 với message count |
| df báo đầy nhưng du nhỏ | File đã unlink nhưng còn process mở, snapshot/volume accounting hoặc path/volume đo không đúng |

## 6. Lab có thể chạy: tạo paging rồi rút message qua JMS transaction

Mục tiêu lab: **tách thời điểm backlog tăng/ACK kết thúc khỏi thời điểm file được reuse/cleanup**. Dùng broker Artemis đã khởi động; không tạo lại môi trường và không thao tác trên queue production.

### 6.1. Queue và chính sách paging

Mảnh cấu hình trong **addresses** của Artemis broker.xml:

~~~xml
<address name="lab.storage.jobs">
    <anycast>
        <queue name="lab.storage.jobs" durable="true"/>
    </anycast>
</address>
~~~

Mảnh cấu hình trong **address-settings**:

~~~xml
<address-setting match="lab.storage.jobs">
    <address-full-policy>PAGE</address-full-policy>
    <max-size-bytes>2097152</max-size-bytes>
    <page-size-bytes>1048576</page-size-bytes>
</address-setting>
~~~

Nếu queue hoặc rule đã tồn tại, **không thêm trùng**. Cấu hình cần được nạp theo quy trình broker. User lab phải có quyền send/consume. Đảm bảo trước khi chạy không có consumer khác của queue.

### 6.2. Maven

Dự án:

~~~text
artemis-storage-lab/
├── pom.xml
└── src/main/java/lab/StorageLifecycleLab.java
~~~

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab</groupId>
  <artifactId>artemis-storage-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.apache.activemq</groupId>
      <artifactId>artemis-jakarta-client</artifactId>
      <version>2.40.0</version>
    </dependency>
    <dependency>
      <groupId>jakarta.jms</groupId>
      <artifactId>jakarta.jms-api</artifactId>
      <version>3.1.0</version>
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
        <version>3.5.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### 6.3. Java producer và consumer theo lô

Tạo file **src/main/java/lab/StorageLifecycleLab.java**:

~~~java
package lab;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.DeliveryMode;
import jakarta.jms.JMSConsumer;
import jakarta.jms.JMSContext;
import jakarta.jms.Message;
import jakarta.jms.Queue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class StorageLifecycleLab {
    private static final String QUEUE = "lab.storage.jobs";
    private static final int COUNT = 150;
    private static final int BODY_CHARS = 32 * 1024;

    private StorageLifecycleLab() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 1
                || (!"send".equals(args[0]) && !"drain".equals(args[0]))) {
            throw new IllegalArgumentException("Chạy mode send hoặc drain");
        }

        String url = System.getenv().getOrDefault(
                "BROKER_URL", "tcp://127.0.0.1:61616");
        String user = requiredEnv("BROKER_USER");
        String pass = requiredEnv("BROKER_PASSWORD");
        ConnectionFactory factory = new ActiveMQConnectionFactory(url);

        try (JMSContext context = factory.createContext(
                user, pass, JMSContext.SESSION_TRANSACTED)) {
            Queue queue = context.createQueue(QUEUE);
            if ("send".equals(args[0])) {
                sendBatch(context, queue);
            } else {
                drainQueue(context, queue);
            }
        }
    }

    private static void sendBatch(JMSContext context, Queue queue)
            throws Exception {
        String body = "x".repeat(BODY_CHARS);

        for (int i = 1; i <= COUNT; i++) {
            TextMessage msg = context.createTextMessage(body);
            msg.setIntProperty("labSequence", i);

            context.createProducer()
                    .setDeliveryMode(DeliveryMode.PERSISTENT)
                    .setTimeToLive(0)
                    .send(queue, msg);

            if (i % 10 == 0) {
                context.commit();
                System.out.println("SEND_COMMITTED through=" + i);
            }
        }

        if (COUNT % 10 != 0) {
            context.commit();
        }
    }

    private static void drainQueue(JMSContext context, Queue queue)
            throws Exception {
        JMSConsumer consumer = context.createConsumer(queue);
        int received = 0;

        while (received < COUNT) {
            Message msg = consumer.receive(5000);
            if (msg == null) {
                System.out.println("RECEIVE_TIMEOUT count=" + received);
                break;
            }

            int seq = msg.getIntProperty("labSequence");
            received++;
            if (received % 10 == 0) {
                context.commit();
                System.out.println("ACK_COMMITTED count=" + received
                        + " lastSequence=" + seq);
            }
        }

        if (received % 10 != 0) {
            context.commit();
        }

        System.out.println("DRAIN_FINISHED received=" + received);
    }

    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Thiếu biến " + key);
        }
        return value;
    }
}
~~~

**Đọc đúng ví dụ:**

- Mỗi message khoảng **32 KiB body ASCII**, tổng 150 message khoảng **4,7 MiB body**, cộng overhead. Ngưỡng address 2 MiB dùng để tăng khả năng thấy paging; số page file thực tế phụ thuộc cách broker vận hành.
- Producer gửi **persistent** và commit JMS mỗi 10 message. Send trong transaction chưa đủ cho tới khi commit.
- Consumer dùng **SESSION_TRANSACTED** và commit ACK mỗi 10 message. Nếu process chết giữa lô, message chưa commit có thể redeliver.
- Code **không** xử lý database nghiệp vụ; log ACK chỉ phản ánh transaction JMS.
- Một lần chạy **drain** chỉ xử lý tối đa 150 message. Không chạy **send** nhiều lần rồi mong một lần drain xóa hết dữ liệu đã seed.
- Payload có thể được nén/serialize theo cách client/provider; hãy xác nhận paging bằng **metrics và page files** thay vì chỉ tính kích thước body.

### 6.4. Các pha nghiệm thu

Đặt biến môi trường PowerShell phù hợp broker lab:

~~~powershell
$env:BROKER_URL = "tcp://127.0.0.1:61616"
$env:BROKER_USER = "lab"
$env:BROKER_PASSWORD = "mat-khau-lab"
mvn -q -DskipTests package
~~~

**Pha A — trước gửi:** đảm bảo queue lab rỗng, không có consumer khác; ghi lại queue message count, delivering count, address size, trạng thái paging, page count, và dung lượng các vùng lưu trữ.

**Pha B — tạo backlog:**

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.StorageLifecycleLab" "-Dexec.args=send"
~~~

Xác minh producer in **SEND_COMMITTED** theo lô, queue backlog tăng. Với policy PAGE được áp dụng, broker có thể tạo page files khi address vượt ngưỡng lab.

**Pha C — rút và ACK:**

~~~powershell
mvn -q exec:java "-Dexec.mainClass=lab.StorageLifecycleLab" "-Dexec.args=drain"
~~~

Kỳ vọng có dòng **ACK_COMMITTED count=150**, sau đó **DRAIN_FINISHED received=150** nếu toàn bộ message còn chờ và không bị client khác lấy. Queue count có thể về 0.

**Pha D — đo lại:** so sánh page count, journal directory, paging directory, large-message directory, và filesystem space ở nhiều thời điểm. Không kỳ vọng journal folder sẽ biến thành 0 byte. Nếu page cleanup chưa xảy ra ngay, kiểm tra các queue/cursor liên quan và chờ thời điểm xử lý cleanup hợp lệ, không xóa file bằng tay.

**Pha E — nhận chưa commit:** trong môi trường lab riêng, mô phỏng consumer chết trước một lần commit; kiểm tra redelivery và dữ liệu chưa ACK vẫn cần được broker giữ.

### 6.5. Lệnh đo chỉ đọc ở môi trường Docker

Nếu image lab thực sự dùng data path **/var/lib/artemis-instance/data**, có thể chạy trên host:

~~~powershell
docker exec amq-lab sh -c 'du -sh /var/lib/artemis-instance/data/journal /var/lib/artemis-instance/data/paging /var/lib/artemis-instance/data/largemessages /var/lib/artemis-instance/data/bindings'
~~~

**Phải lấy đường dẫn thực từ broker.xml/runtime configuration**, vì image, volume và instance có thể khác. Lệnh trên chỉ quan sát dung lượng folder; không đo đầy đủ block của PVC hoặc backup/snapshot. Kết hợp file count, queue/management metrics và timestamp để hiểu xu hướng.

**Tuyệt đối không** chạy lệnh xóa trực tiếp file journal/page/large-message, dù file có ngày sửa cũ hoặc queue count đã về 0.

## 7. Ba lớp số liệu phải theo dõi riêng

### 7.1. Message và queue state

- Message count của **từng queue**, delivering/in-flight và consumer count.
- Address size, page state, page count, page subscriptions/cursor state khi management API hỗ trợ.
- Durable subscription offline, DLQ và expiry queue.
- Transaction chưa commit/rollback, prepared XA và scheduled message.
- Enqueue/dequeue/ACK counters: phân biệt **counter lịch sử** với message chờ hiện tại.

### 7.2. Storage file state

- Dung lượng journal và số file dùng/tái dùng.
- Page files theo address, page cleanup sau khi cursor đi qua.
- Large message files và loại payload đang giữ reference.
- Storage errors, journal errors, paging cleanup warnings.
- IO latency, disk pressure, phần trăm volume trống.

### 7.3. Filesystem/volume state

- **du** thường phản ánh dung lượng của các file hiện thấy dưới đường dẫn.
- **df** phản ánh lượng block của toàn filesystem; có thể khác du do file còn descriptor mở, snapshot, reserved blocks, overlay filesystem hoặc path đang ở volume khác.
- PVC/disk quota và dữ liệu backup/log có thể chiếm chỗ ngoài thư mục broker data.

Ví dụ: queue về 0 và page directory giảm, nhưng df vẫn gần đầy vì journal pool, snapshot hoặc log tăng. Đó không phải bằng chứng page cleanup thất bại.

## 8. Runbook chẩn đoán khi dung lượng không giảm

### Bước 1 — xác định đúng storage path

Kiểm tra config runtime cho **journal-directory**, **bindings-directory**, **paging-directory**, **large-messages-directory**; trong Docker/Kubernetes xác định mount/PVC đúng. Không so sánh dữ liệu trên host với một thư mục khác trong container.

### Bước 2 — chứng minh backlog thực sự đã hết

Xem **mọi queue bind cùng address**, cả durable subscription không online; kiểm tra delivering, scheduled, redelivery, DLQ/expiry và transaction chưa commit. Không lấy một queue count bằng 0 làm nguồn sự thật toàn address.

### Bước 3 — xác định *vùng* đang chiếm đĩa

| Vùng tăng | Điều tra ưu tiên |
|---|---|
| **Journal** | Live records, min-files/pool, compaction threshold, prepared transaction, tốc độ ghi mới |
| **Paging** | Slow subscription, paged backlog, cursor chưa đi qua page, page cleanup error |
| **Large messages** | Large-message references, body file cleanup, message tồn trên queue khác |
| **Bindings** | Queue/topology metadata, journal file reuse; không liên hệ trực tiếp mỗi ACK |
| **Ngoài broker data** | Snapshot, log, heap dump, filesystem block accounting |

### Bước 4 — lấy số liệu nhiều thời điểm

Một lần nhìn thấy journal 20 file khi queue rỗng không đủ chứng minh leak. Chạy vài chu kỳ thử tương đương, đo byte của từng directory. Nếu dung lượng **ổn định** và tái dùng, có thể là trạng thái bình thường; nếu tăng liên tục dù không còn reference, cần thu thập logs/metrics để điều tra.

### Bước 5 — chỉ thay cấu hình khi biết nguyên nhân

Chỉnh threshold compaction, page size hay address limit có thể ảnh hưởng I/O/latency và recovery. Thay đổi trong broker lab, chạy test có fault injection, ghi nhận SLO, backup và lộ trình triển khai. Đừng giảm journal-min-files quá mức chỉ để làm đẹp con số du.

### Bước 6 — sử dụng API quản trị chính thức nếu phải xóa dữ liệu

Purge/delete queue hoặc expiry có thể hợp lệ theo yêu cầu retention, nhưng là **thao tác làm mất dữ liệu**. Phải có scope, phê duyệt và backup; kiểm tra tác động tới những queue/subscription khác. Không thay bằng xóa file thuộc data directory.

### Bước 7 — nghiệm thu

Sau can thiệp, xác nhận đồng thời: queue count, delivering, DLQ/expiry, page metrics, journal file stability, dung lượng volume và thử send/consume persistent + broker restart (nếu nằm trong kế hoạch kiểm thử). Mục tiêu là **recovery đúng và không mất message**, không chỉ giảm dung lượng đĩa.

## 9. Năm tình huống thường gây hiểu nhầm

**Tình huống A — queue fast rỗng nhưng page file còn.**  
Một address MULTICAST có queue fast và queue slow. Fast đã ACK hết, slow còn message. Page file có thể vẫn cần cho slow. Đo riêng fast không đủ.

**Tình huống B — DLQ tăng sau retry.**  
Message đã rời queue gốc nhưng vẫn ở DLQ. Đây là **di chuyển trách nhiệm lưu trữ**, không nhất thiết là giải phóng payload khỏi storage.

**Tình huống C — queue rỗng nhưng journal directory còn cố định.**  
Journal có file pool/min-files và có thể giữ record/file để tái sử dụng. Cần xem xu hướng, không đòi thư mục 0 byte.

**Tình huống D — đã receive nhưng transaction chưa commit.**  
Consumer nhận message, crash trước JMS commit. Broker có thể redeliver; dữ liệu vẫn cần được giữ.

**Tình huống E — không paging nữa nhưng vẫn có page files.**  
Address giảm áp lực và ngừng ghi page mới, nhưng queue/page cursor chưa tiêu thụ hết page cũ. Không xóa page theo cờ isPaging đơn lẻ.

## 10. Bài tập tự kiểm tra

1. **Journal lifecycle:** Vì sao sau khi ACK 150 message, file journal vẫn còn? Hãy phân biệt record live/dead, min-files, reuse và compaction.
2. **Nhiều queue:** Một message được route đến hai subscription. Một subscription ACK, subscription kia offline. Có thể coi message không còn tham chiếu không? Hãy vẽ các reference còn lại.
3. **Paging:** Trong page có 1.000 message, 999 đã ACK. Vì sao page file vẫn có thể được giữ?
4. **Transaction:** Consumer đã nhận 20 message nhưng chưa commit. Điều gì xảy ra nếu broker/consumer crash?
5. **Large message:** File body lớn còn trên đĩa sau khi queue A rỗng. Cần xem những queue/transaction nào trước khi nghi cleanup lỗi?
6. **Sự khác biệt du/df:** Nếu page file biến mất nhưng filesystem vẫn đầy, có thể là những nguyên nhân nào ngoài message live?
7. **An toàn thao tác:** Vì sao không nên tự xóa tệp journal/page ngay cả khi broker đang stop?
8. **Đo thực tế:** Chạy một chu kỳ send/drain và đo 3 lần sau khi ACK. Điều gì là bằng chứng của file reuse ổn định, điều gì đáng nghi là tăng trưởng không giới hạn?

## 11. Checklist vận hành

- [ ] Đã xác định đúng data directory và volume của instance Artemis.
- [ ] Đã hiểu khác biệt giữa ACK logic và physical file cleanup.
- [ ] Đã kiểm tra mọi queue/subscription của address, kể cả durable subscription offline.
- [ ] Đã kiểm tra delivering, scheduled, transaction/rollback, prepared XA nếu có.
- [ ] Đã kiểm tra DLQ và expiry queue; không coi chúng là dữ liệu đã biến mất.
- [ ] Đã kiểm tra journal min-files/pool/compaction threshold.
- [ ] Đã kiểm tra page subscriptions/cursors và các page còn reference.
- [ ] Đã phân biệt large-message files với journal và page files.
- [ ] Đã đối chiếu du, df, snapshot và PVC quota.
- [ ] Đã thử send/drain trên queue lab với persistent/transaction.
- [ ] Không xóa file journal/page/large-message trực tiếp để giảm disk.
- [ ] Có cảnh báo disk headroom, backlog tuổi cao, page growth và lỗi storage.

## 12. Kết luận

**Thu hồi dữ liệu trong Artemis được quyết định trước hết bởi các tham chiếu và trạng thái commit, không phải bởi một lần nhìn thấy ACK rồi lập tức xóa file.** Journal có thể tái sử dụng file và compaction theo điều kiện; paging chỉ cleanup page khi các queue/cursor liên quan không còn cần dữ liệu; body large message có vòng đời riêng.

Khi queue đã rỗng mà ổ đĩa vẫn lớn, hãy phân biệt **reference còn sống, file pool được giữ hợp lệ, page cursor chưa hoàn tất và filesystem accounting**. Độ tin cậy không nằm ở việc ép thư mục dữ liệu rỗng, mà ở chỗ **message cần giữ không bị mất, dữ liệu hết vai trò được thu hồi hoặc tái sử dụng an toàn, và dung lượng không tăng vượt kiểm soát**.
