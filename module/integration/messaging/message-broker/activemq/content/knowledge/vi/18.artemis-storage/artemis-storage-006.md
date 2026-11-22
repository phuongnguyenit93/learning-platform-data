# Large message và xử lý body theo luồng trong ActiveMQ Artemis

> **Chương:** Lưu trữ Artemis  
> **Trọng tâm:** Artemis quản lý **large message** như thế nào, body được truyền và ghi ra đĩa theo luồng ra sao, ứng dụng Java cần dùng API nào để tránh giữ cả file trong heap, và cách kiểm chứng tính toàn vẹn, transaction, ACK, tài nguyên đĩa. Các ví dụ Core API dùng client `artemis-core-client`; phần JMS giải thích rõ giới hạn của `BytesMessage`/`TextMessage`. Không áp dụng nguyên xi cho ActiveMQ Classic.

## 1. Bài toán: file 2 GiB không nên trở thành một đối tượng Java 2 GiB

Một dịch vụ nhận ảnh y tế hoặc file báo cáo, sau đó gửi nội dung tới queue `files.in` để một worker lưu trữ và kiểm tra checksum. Giả sử file nặng 2 GiB, trong khi JVM của producer và consumer đều chỉ có heap 512 MiB.

Cách làm nguy hiểm:

~~~java
// Ví dụ SAI với file lớn: đọc toàn bộ body vào một byte[].
byte[] entireFile = java.nio.file.Files.readAllBytes(inputPath);
javax.jms.BytesMessage m = session.createBytesMessage();
m.writeBytes(entireFile);
producer.send(m);
~~~

Đoạn trên có thể vấp `OutOfMemoryError` ngay trước khi JMS provider bắt đầu truyền dữ liệu. Nếu producer dựng một `String` khổng lồ rồi gọi `TextMessage.setText(text)`, vấn đề tương tự có thể xuất hiện ở phía ứng dụng.

Artemis hỗ trợ **large messages** để tránh buộc broker/client giữ toàn bộ body trong heap. Tuy nhiên cần phân biệt rõ:

1. **Cơ chế lưu trữ lớn của broker:** body được chuyển thành các phần và lưu dưới dạng dữ liệu large-message, thay vì nằm trọn trong vùng đệm message thông thường.
2. **Cách Java tạo/đọc body:** code phải dùng API streaming để tránh tự tạo `byte[]` hoặc `String` chứa toàn bộ body trước khi gửi.
3. **Tính bền vững và giao dịch:** stream thành công chưa tương đương send transaction đã commit, và file do consumer ghi ra chưa nằm trong cùng transaction với JMS ACK.

**Mục tiêu:** gửi/nhận file kích thước lớn với bộ nhớ ứng dụng xấp xỉ theo kích thước buffer, không theo kích thước cả file; vẫn kiểm chứng checksum và xử lý redelivery an toàn.

## 2. Artemis large message là gì?

Ở mức khái niệm, Artemis phân biệt message thông thường với **large message** dựa trên cơ chế client/protocol và một ngưỡng kích thước cấu hình. Với **Artemis Core client**, tùy chọn `minLargeMessageSize` quyết định ngưỡng mà client bắt đầu gửi một message theo cơ chế large-message; giá trị mặc định phổ biến của Artemis Core là **100 KiB (102.400 byte)**, nhưng phải kiểm tra phiên bản/client/protocol thực tế.

Khi gửi bằng streaming:

~~~mermaid
flowchart LR
    F["File nguồn"] --> I["InputStream"]
    I --> C["Artemis Core client: gửi các phần body"]
    C --> N["Network / broker acceptor"]
    N --> L[("Large-message body files")]
    N --> J[("Journal: metadata / references")]
    J --> Q["Queue reference"]
    Q --> O["Consumer OutputStream"]
    L --> O
    O --> D["File đích"]
~~~

Mô hình logic:

- **Metadata/định tuyến/queue references** được broker quản lý thông qua journal, bindings và các cấu trúc liên quan.
- **Nội dung lớn (body)** được Artemis quản lý ngoài đường lưu body nhỏ thông thường, sử dụng thư mục large messages trên broker.
- Truyền/nhận body có thể diễn ra theo từng khối; producer/consumer không bắt buộc chứa toàn bộ body trong RAM.
- Một body có thể còn được tham chiếu bởi nhiều queue/subscription. Việc dọn file phụ thuộc vòng đời **tất cả references**, không chỉ một consumer đã ACK.

**Không suy diễn rằng mỗi message luôn tạo đúng một file có tên dự đoán được.** Cách tổ chức file, chunk, reference count và thời điểm dọn dẹp là chi tiết nội bộ có thể thay đổi theo phiên bản.

### 2.1. Large message và paging không phải một thứ

| Khía cạnh | Large message | Paging |
|---|---|---|
| Vấn đề chính | **Một message có body lớn** | **Tổng lượng dữ liệu của address/backlog** vượt ngưỡng quản lý bộ nhớ |
| Điều kiện điển hình | Kích thước message/stream vượt ngưỡng client/protocol | Address đầy theo `max-size-bytes` và `address-full-policy=PAGE` |
| Phạm vi | Body của message lớn | Tình trạng backlog của một address |
| Nơi lưu | Dữ liệu body do large-message subsystem quản lý | Paging store/page files theo address |
| Có phụ thuộc nhau không? | Message lớn vẫn có thể góp vào áp lực backlog/paging | Paging có thể xảy ra cả khi từng message nhỏ |

**Không chỉnh `max-size-bytes` rồi cho rằng đã thay ngưỡng `minLargeMessageSize`.** Hai con số giải quyết hai bài toán khác nhau.

### 2.2. Large message không phải kiểu routing thứ ba

Một large message vẫn được gửi vào một **address**, route đến queue theo **anycast/multicast**, có header, property, delivery mode, TTL và transaction như message khác. Cơ chế large message không tự tạo queue riêng, không thay selector hay thay đổi quyền gửi/nhận.

Nếu address multicast có nhiều queue bền, broker phải giữ body khi còn references chưa hoàn tất. Đừng giả định một consumer đã ACK thì large-message file được xóa ngay.

## 3. Những bộ nhớ nào thật sự cần quan tâm?

Đối với luồng gửi/nhận một file `N` byte, bộ nhớ ứng dụng có thể đến từ:

~~~text
N: dung lượng file/body
B: kích thước byte[] của vòng đọc/ghi (ví dụ 64 KiB)
P: số message cùng xử lý đồng thời
K: client transport buffer, protocol buffer, metadata, compression state...

Mô hình streaming tốt:
  ứng dụng giữ O(P × B + K), không bắt buộc O(P × N).

Mô hình readAllBytes()/setText(giantString):
  ứng dụng có thể giữ O(P × N), thậm chí thêm bản sao khi encode/copy.
~~~

Đây là **mô hình độ phức tạp bộ nhớ**, không phải công thức đo heap chính xác; còn buffer của Artemis và JVM. Quan trọng là không tạo một đối tượng Java chứa toàn bộ body.

### 3.1. Đừng nhầm `readBytes(chunk)` với streaming end-to-end

Một consumer có thể đọc từ `BytesMessage` theo từng khối:

~~~java
byte[] buffer = new byte[64 * 1024];
int n;
while ((n = bytesMessage.readBytes(buffer)) != -1) {
    output.write(buffer, 0, n);
}
~~~

Đoạn này tránh cấp phát một `byte[]` cực lớn trong **vòng đọc application**, nhưng **không tự chứng minh** provider đã stream từ network/disk mà không materialize body trong client trước đó. Tương tự, nhiều lần `BytesMessage.writeBytes(buffer,0,n)` có thể vẫn xây một body message trong buffer phía client.

Muốn streaming ở **toàn bộ đường gửi/nhận** với Artemis Core, dùng API `ClientMessage.setBodyInputStream(InputStream)` và `ClientMessage.saveToOutputStream(OutputStream)` như phần thực hành.

### 3.2. `TextMessage` có thể kích hoạt large-message storage nhưng Java vẫn giữ `String`

Nếu app gọi:

~~~java
String hugeText = loadHugeTextIntoMemory();
TextMessage m = session.createTextMessage(hugeText);
producer.send(m);
~~~

Artemis có thể xử lý body lớn ở tầng transport/store, **nhưng `hugeText` đã có trong heap của producer**. Nhận bằng `getText()` cũng có thể làm xuất hiện String rất lớn.

Với binary/file khổng lồ, nên dùng stream; với dữ liệu văn bản cần schema, có thể mã hóa thành UTF-8 dưới dạng bytes streaming và ghi rõ `contentType`, `schemaVersion` cùng checksum. Không đánh đồng nó với JMS `TextMessage` nếu consumer mong đúng loại body theo API.

## 4. Cấu hình broker: bảo vệ large-messages directory

Trong `etc/broker.xml` của **Artemis**, bên trong phần `<core>`, cần quan tâm những đường dẫn dữ liệu sau:

~~~xml
<!-- Fragment: đặt các phần tử ở vị trí/thứ tự hợp lệ
     theo schema của bản Artemis đang chạy. -->
<persistence-enabled>true</persistence-enabled>
<bindings-directory>data/bindings</bindings-directory>
<journal-directory>data/journal</journal-directory>
<paging-directory>data/paging</paging-directory>
<large-messages-directory>data/large-messages</large-messages-directory>
~~~

Khi chạy trong container, **tất cả các thư mục dữ liệu cần thiết** phải nằm trên storage bền hoặc được quản lý theo chiến lược lưu trữ của môi trường. Không đặt `data/large-messages` trên một volume tạm trong khi journal bền trên volume khác rồi mong message persistent sống qua restart.

Một address và queue anycast dành cho lab:

~~~xml
<addresses>
  <address name="files.in">
    <anycast>
      <queue name="files.in" durable="true"/>
    </anycast>
  </address>
</addresses>
~~~

Đây là cấu hình **đặt trước** queue; consumer Core đọc theo tên queue `files.in`, producer gửi vào address `files.in`. Cần cấp quyền phù hợp cho user test.

### 4.1. Bảo vệ disk

Large-message body sẽ tạo I/O và tiêu thụ dung lượng thực trên disk. Khi thiết kế:

- Giám sát tổng dung lượng thư mục large messages và tốc độ tăng/giảm.
- Giữ headroom cho journal, paging, log, transaction và hoạt động recovery.
- Bật cảnh báo disk free và giới hạn số luồng upload đồng thời.
- Xác định retention/TTL, DLQ và người có quyền xóa/replay message.
- Bảo vệ dữ liệu nhạy cảm bằng ACL, encryption-at-rest và backup policy phù hợp.

**Không xóa trực tiếp file trong large-messages directory để giảm dung lượng.** Broker đang giữ reference trong journal/queue; xóa tay có thể làm message không còn body hoặc gây lỗi recovery. Hãy tìm root cause: backlog, unacked subscriptions, DLQ, expiry hay orphan và dùng quy trình quản trị được phiên bản hỗ trợ.

### 4.2. Address paging là cấu hình độc lập

Ví dụ address chịu nhiều file chờ:

~~~xml
<address-settings>
  <address-setting match="files.in">
    <max-size-bytes>268435456</max-size-bytes>
    <address-full-policy>PAGE</address-full-policy>
    <dead-letter-address>DLQ</dead-letter-address>
  </address-setting>
</address-settings>
~~~

`max-size-bytes=268435456` (256 MiB) là một ngưỡng **quản lý kích thước address theo semantics Artemis**, **không phải** giới hạn file upload bằng 256 MiB, không phải kích thước cho phép tối đa của một message và cũng không phải ngưỡng chuyển sang large-message mode.

Đoạn trên giả định `DLQ` đã được tạo/routing hợp lệ nếu dùng dead-letter. Không sao chép fragment mà thiếu address DLQ trong cấu hình thật.

## 5. Ngưỡng `minLargeMessageSize` là quyết định phía client/protocol

Với Artemis Core client, có thể cấu hình `ServerLocator`:

~~~java
// Fragment: gọi trước khi tạo ClientSessionFactory/session.
ServerLocator locator = ActiveMQClient.createServerLocatorWithoutHA(
        transportConfiguration);
locator.setMinLargeMessageSize(128 * 1024); // 128 KiB
~~~

Những điều cần hiểu:

1. Đây là **ngưỡng** định tuyến message sang cơ chế large-message của client, không phải giới hạn chặn các message lớn hơn ngưỡng.
2. Giá trị mặc định điển hình là **100 KiB**, nhưng kiểm tra Artemis version, client factory và giao thức trước khi kết luận.
3. Các giao thức khác như AMQP có bộ mã hóa, cách stream/large-message và cấu hình riêng; `setMinLargeMessageSize` trên Core client **không tự cấu hình mọi client AMQP/OpenWire/MQTT**.
4. Giảm threshold làm nhiều message trở thành large-message: có thể bớt áp lực heap nhưng thêm overhead metadata/file/I/O.
5. Tăng threshold có thể khiến body lớn vừa phải nằm trong buffer thông thường lâu hơn. Không tune chỉ theo cảm giác.

### 5.1. Stream API và threshold liên quan nhưng không đồng nhất

Khi gọi `setBodyInputStream(InputStream)`, bạn đang khai báo nguồn body theo luồng cho Core client. Đây là API phục vụ gửi large messages mà không materialize body toàn bộ. Còn threshold mô tả quyết định của client khi message body được tạo theo API thông thường.

**Không giả định đặt threshold là đủ để `Files.readAllBytes()` biến thành streaming.** Bộ nhớ đã bị sử dụng trước lời gọi `send()` thì broker không thể sửa được.

## 6. Core API: gửi file theo luồng từ `InputStream`

Phần thực hành dùng thư viện Maven **`org.apache.activemq:artemis-core-client`** với phiên bản đồng bộ theo Artemis broker/BOM; chọn JDK tương thích. Các chương trình Java sau là ví dụ cho **Artemis Core protocol**, không phải JMS API chuẩn.

Lab cần:

- Broker Artemis trên `127.0.0.1:61616`, acceptor cho Core protocol.
- User `app` với password lab `lab-secret` và quyền send/consume.
- Address/queue `files.in` bền như mục 4.
- File nguồn bất kỳ; nên thử từ 20 KiB rồi 20 MiB và trên 1 GiB nếu đủ disk.
- Data volume broker bền và các metric broker/disk được bật để quan sát.

### 6.1. Tạo kết nối Core có transaction

Trong ví dụ sau, cấu trúc tạo connection sử dụng:

~~~java
Map<String, Object> params = new HashMap<>();
params.put("host", "127.0.0.1");
params.put("port", 61616);

TransportConfiguration connector =
        new TransportConfiguration(
                NettyConnectorFactory.class.getName(), params);

ServerLocator locator =
        ActiveMQClient.createServerLocatorWithoutHA(connector);

locator.setMinLargeMessageSize(128 * 1024);

ClientSessionFactory sessionFactory = locator.createSessionFactory();

// xa=false, autoCommitSends=false, autoCommitAcks=false,
// preAcknowledge=false, ackBatchSize=0.
ClientSession session = sessionFactory.createSession(
        "app", "lab-secret",
        false, false, false, false, 0);
~~~

Với `autoCommitSends=false`, sender phải gọi `session.commit()`. Với `autoCommitAcks=false`, consumer phải gọi `message.acknowledge()` và `session.commit()`. Tên tham số và overload được chọn tương ứng Artemis Core API; nếu dự án dùng phiên bản cũ/mới khác, kiểm tra API và BOM trước khi biên dịch.

### 6.2. Chương trình gửi đầy đủ: `ArtemisLargeSender.java`

Chương trình tính SHA-256 của file bằng **một lượt đọc theo buffer**, sau đó mở `InputStream` thứ hai để truyền body. Cách này đọc file hai lượt nhưng **không giữ toàn bộ file trong heap**.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

import org.apache.activemq.artemis.api.core.TransportConfiguration;
import org.apache.activemq.artemis.api.core.client.ActiveMQClient;
import org.apache.activemq.artemis.api.core.client.ClientMessage;
import org.apache.activemq.artemis.api.core.client.ClientProducer;
import org.apache.activemq.artemis.api.core.client.ClientSession;
import org.apache.activemq.artemis.api.core.client.ClientSessionFactory;
import org.apache.activemq.artemis.api.core.client.ServerLocator;
import org.apache.activemq.artemis.core.remoting.impl.netty.NettyConnectorFactory;

public final class ArtemisLargeSender {
    private static final String ADDRESS = "files.in";

    public static void main(String[] args) throws Exception {
        if (args.length != 2 ||
                !args[1].matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException(
                    "Usage: ArtemisLargeSender <filePath> <blobId>");
        }

        Path source = Paths.get(args[0]);
        String blobId = args[1];
        long size = Files.size(source);
        String digest = sha256Base64(source);

        Map<String, Object> params = new HashMap<>();
        params.put("host", "127.0.0.1");
        params.put("port", 61616);

        TransportConfiguration connector = new TransportConfiguration(
                NettyConnectorFactory.class.getName(), params);
        ServerLocator locator =
                ActiveMQClient.createServerLocatorWithoutHA(connector);

        ClientSessionFactory factory = null;
        ClientSession session = null;
        ClientProducer producer = null;
        try {
            locator.setMinLargeMessageSize(128 * 1024);
            factory = locator.createSessionFactory();
            session = factory.createSession(
                    "app", "lab-secret",
                    false, false, false, false, 0);
            producer = session.createProducer(ADDRESS);

            ClientMessage message = session.createMessage(true); // durable
            message.putStringProperty("blobId", blobId);
            message.putLongProperty("blobSize", size);
            message.putStringProperty("blobSha256", digest);

            // Không gọi readAllBytes(): body chỉ được đọc theo luồng.
            try (InputStream input = Files.newInputStream(source)) {
                message.setBodyInputStream(input);
                producer.send(message);
                session.commit(); // Chỉ xác nhận publish sau commit thành công.
            }

            System.out.println("COMMIT_CONFIRMED blobId=" + blobId
                    + " size=" + size + " sha256=" + digest);
        } finally {
            if (producer != null) producer.close();
            if (session != null) session.close();
            if (factory != null) factory.close();
            locator.close();
        }
    }

    private static String sha256Base64(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buf = new byte[64 * 1024];
        try (InputStream in = Files.newInputStream(path)) {
            int n;
            while ((n = in.read(buf)) != -1) {
                if (n > 0) md.update(buf, 0, n);
            }
        }
        return Base64.getEncoder().encodeToString(md.digest());
    }
}
~~~

**Phân tích:**

- `session.createMessage(true)` tạo message **durable** của Core API. Kết hợp queue durable, broker persistence và `commit()` để kiểm tra lưu bền theo failure model phù hợp.
- `setBodyInputStream(input)` là điểm phân biệt với cách nạp cả file vào `byte[]`.
- `producer.send(message)` chuyển nội dung theo cơ chế Core large-message; `session.commit()` kết thúc local transaction gửi.
- `blobId` là **định danh nghiệp vụ cố định**. Một lần retry gửi cùng file phải giữ nguyên `blobId` và checksum; không dùng message ID do broker sinh để deduplication.
- Nếu `send/commit` timeout hoặc mất phản hồi, producer không thể khẳng định broker chưa nhận. Retry phải giữ blob ID; consumer phải xử lý trùng an toàn.
- Code không chứa retry/failover hay queue provisioning để không làm lẫn trọng tâm streaming. Production cần error classification, timeout, outbox và vận hành phù hợp.
- Không hard-code credential thật; secret ở đây chỉ phục vụ lab.

**Lưu ý về lỗi file thay đổi trong lúc gửi:** checksum và body được đọc ở hai lượt. Nếu file nguồn bị sửa giữa hai lượt, checksum có thể không còn tương ứng. Production nên gửi từ file snapshot/bất biến hoặc lock/version file trước khi tính hash và upload.

## 7. Core API: nhận body qua `OutputStream` và chỉ ACK sau khi lưu

Artemis Core hỗ trợ `ClientMessage.saveToOutputStream(OutputStream)` để **chép body vào stream đầu ra**. Đây là lời gọi đồng bộ phù hợp cho lab; một số API output-stream bất đồng bộ khác của Artemis cần chờ hoàn tất trước khi ACK.

Mục tiêu của receiver:

1. Nhận message bằng queue `files.in`.
2. Đọc `blobId`, kích thước và SHA-256 từ properties.
3. Ghi body vào file tạm, **không tạo byte[] bằng kích thước file**.
4. Xác minh độ dài và checksum.
5. Đưa file sang tên đích bằng move nguyên tử khi filesystem hỗ trợ.
6. Sau khi file đã sẵn sàng, gọi `acknowledge()` và `session.commit()`.
7. Nếu message được giao lại, kiểm tra file đích đã có đúng hash để **không ghi/áp dụng tác động lần hai**.

### 7.1. Chương trình nhận đầy đủ: `ArtemisLargeReceiver.java`

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.security.DigestOutputStream;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

import org.apache.activemq.artemis.api.core.TransportConfiguration;
import org.apache.activemq.artemis.api.core.client.ActiveMQClient;
import org.apache.activemq.artemis.api.core.client.ClientConsumer;
import org.apache.activemq.artemis.api.core.client.ClientMessage;
import org.apache.activemq.artemis.api.core.client.ClientSession;
import org.apache.activemq.artemis.api.core.client.ClientSessionFactory;
import org.apache.activemq.artemis.api.core.client.ServerLocator;
import org.apache.activemq.artemis.core.remoting.impl.netty.NettyConnectorFactory;

public final class ArtemisLargeReceiver {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ArtemisLargeReceiver <outputDirectory>");
        }
        Path outputDir = Paths.get(args[0]);
        Files.createDirectories(outputDir);

        Map<String, Object> params = new HashMap<>();
        params.put("host", "127.0.0.1");
        params.put("port", 61616);
        TransportConfiguration connector = new TransportConfiguration(
                NettyConnectorFactory.class.getName(), params);
        ServerLocator locator =
                ActiveMQClient.createServerLocatorWithoutHA(connector);

        ClientSessionFactory factory = null;
        ClientSession session = null;
        ClientConsumer consumer = null;
        try {
            locator.setMinLargeMessageSize(128 * 1024);
            factory = locator.createSessionFactory();
            session = factory.createSession(
                    "app", "lab-secret",
                    false, false, false, false, 0);
            consumer = session.createConsumer("files.in");
            session.start();

            ClientMessage message = consumer.receive(15_000L);
            if (message == null) {
                System.out.println("NO_MESSAGE_WITHIN_TIMEOUT");
                return;
            }

            try {
                processLargeBody(message, outputDir);
                message.acknowledge();
                session.commit(); // ACK được xác nhận trong Core transaction.
            } catch (Exception problem) {
                try {
                    session.rollback(); // Cho phép broker redeliver theo policy.
                } catch (Exception rollbackFailure) {
                    problem.addSuppressed(rollbackFailure);
                }
                throw problem;
            }
        } finally {
            if (consumer != null) consumer.close();
            if (session != null) session.close();
            if (factory != null) factory.close();
            locator.close();
        }
    }

    private static void processLargeBody(
            ClientMessage message, Path directory) throws Exception {
        String blobId = message.getStringProperty("blobId");
        long expectedSize = message.getLongProperty("blobSize");
        String expectedHash = message.getStringProperty("blobSha256");

        if (blobId == null || !blobId.matches("[A-Za-z0-9_-]{1,80}")
                || expectedSize < 0 || expectedHash == null) {
            throw new IllegalArgumentException("Invalid blob metadata");
        }

        Path target = directory.resolve(blobId + ".bin");

        // Redelivery sau khi file đích đã tạo, nhưng ACK trước đó bị mất.
        if (Files.exists(target)) {
            if (Files.size(target) != expectedSize
                    || !sha256Base64(target).equals(expectedHash)) {
                throw new IllegalStateException(
                        "Same blobId but different content: " + blobId);
            }
            System.out.println("ALREADY_SAVED blobId=" + blobId);
            return;
        }

        Path temp = Files.createTempFile(
                directory, blobId + "-", ".part");
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");

            try (OutputStream out = new DigestOutputStream(
                    Files.newOutputStream(temp), md)) {
                // Stream tới file, không materialize toàn bộ body.
                message.saveToOutputStream(out);
            }

            String actualHash =
                    Base64.getEncoder().encodeToString(md.digest());

            if (Files.size(temp) != expectedSize
                    || !actualHash.equals(expectedHash)) {
                throw new IllegalStateException(
                        "Size or checksum mismatch for " + blobId);
            }

            // Lab yêu cầu cùng filesystem có atomic move.
            Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE);

            System.out.println("SAVED blobId=" + blobId
                    + " size=" + expectedSize);
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    private static String sha256Base64(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] buf = new byte[64 * 1024];
        try (InputStream in = Files.newInputStream(path)) {
            int n;
            while ((n = in.read(buf)) != -1) {
                if (n > 0) md.update(buf, 0, n);
            }
        }
        return Base64.getEncoder().encodeToString(md.digest());
    }
}
~~~

**Giới hạn của ví dụ:**

- Đây là một receiver đơn luồng cho lab. Trong production có nhiều receiver cùng ghi một `blobId`, cần **conditional create/unique constraint/lock phân tán**; không chỉ kiểm tra `Files.exists()` trước khi move.
- `ATOMIC_MOVE` có thể không được hỗ trợ ở filesystem hoặc object storage đang dùng; nếu thất bại, ví dụ báo lỗi thay vì âm thầm dùng move không nguyên tử. Production cần quy trình ghi tạm và publish file phù hợp storage.
- Close/output stream và move nguyên tử **không mặc nhiên bảo đảm chống mất điện ở filesystem**; nếu đòi durability của file đích, cần cơ chế fsync/đảm bảo lưu bền tương ứng và kiểm tra với thiết bị thật.
- Nếu app crash sau move nhưng trước `session.commit()`, broker có thể giao lại message; nhánh `ALREADY_SAVED` dùng cùng `blobId` + SHA-256 để ACK mà không ghi lại.
- Nếu `session.commit()` ném lỗi do mất phản hồi, gọi rollback phía client **không thể chứng minh ACK/commit chưa có hiệu lực trên broker**.
- File `.part` có thể còn sau crash đột ngột (bỏ qua `finally`); cần job cleanup file tạm đủ tuổi và quan sát retry, không tự xóa file đích đã xác minh.
- Nếu metadata sai/corrupt liên tục, cần redelivery limit và DLQ; không retry nóng mãi.
- SHA-256 trong ví dụ là kiểm tra **toàn vẹn dữ liệu**, không phải xác thực người gửi. Dùng TLS/auth/authorization và cơ chế chữ ký nếu có yêu cầu tin cậy nguồn.

## 8. Chạy lab: xác minh có stream thật và message còn sau restart

Sau khi project có dependency Core client đúng phiên bản và classpath đầy đủ:

~~~text
ArtemisLargeSender <sourceFile> blob-001
ArtemisLargeReceiver <outputDirectory>
~~~

Đây là **đối số chương trình**, không phải lệnh shell có sẵn. Có thể chạy qua IDE, Maven Exec hoặc `java -cp ... ArtemisLargeSender` sau khi biên dịch.

Lượt thử đề xuất:

1. Tạo file test **trên 128 KiB** với nội dung có thể kiểm checksum; ghi kích thước và SHA-256 ở producer.
2. Khởi động broker Artemis lab có `files.in` và large-messages directory hợp lệ.
3. Chạy sender; đợi dòng `COMMIT_CONFIRMED`.
4. Quan sát queue có message pending và disk usage của large-messages directory.
5. **Chưa chạy receiver**; restart broker dùng lại toàn bộ data directory (journal, bindings, paging, large messages), không reset volume.
6. Chạy receiver; đối chiếu kích thước và SHA-256, kiểm tra file đích `blob-001.bin`.
7. Chạy receiver lần nữa khi queue đã ACK; có thể thấy `NO_MESSAGE_WITHIN_TIMEOUT`, trừ khi có message khác.
8. Ghi tốc độ upload/download, heap, disk, queue pending/delivering và sự thay đổi file storage.

**Kết luận hợp lệ:** File lớn đã được stream và nhận nguyên vẹn qua restart trong failure model thử. **Không kết luận:** Hệ thống đã có HA, không thể mất file khi disk hỏng, hay tất cả broker/protocol đều hỗ trợ cùng API.

### 8.1. Test heap để bác bỏ thiết kế `readAllBytes()`

Giữ JVM heap đủ nhỏ so với file test (ví dụ 256 MiB heap và file 1 GiB, nếu máy thử có đủ disk). So sánh:

- Thiết kế `readAllBytes()`: dễ OOM ở producer.
- Thiết kế Core `setBodyInputStream()`: kỳ vọng có thể upload mà không tạo mảng byte 1 GiB.
- Thiết kế Core `saveToOutputStream()`: kỳ vọng ghi file theo stream, không tạo mảng 1 GiB ở receiver.

Đừng tuyên bố heap **không tăng**: client vẫn có buffer, metadata, compression và thread state. Đo `heap used`, GC pause và memory peak thực tế bằng các công cụ theo JDK của dự án.

## 9. So sánh JMS BytesMessage với Artemis Core streaming

| Cách viết | Bộ nhớ ứng dụng | Hợp đồng/giới hạn |
|---|---|---|
| `TextMessage.setText(giantString)` | Có String lớn trong heap | Không phải streaming từ file dù broker xử lý large message |
| `BytesMessage.writeBytes(entireByteArray)` | Cần `byte[]` toàn file | Dễ OOM với file rất lớn |
| Lặp `BytesMessage.writeBytes(buffer)` | App chỉ dùng buffer nhỏ ở vòng đọc file | Provider có thể giữ/tích lũy toàn bộ message body; **không bảo đảm end-to-end streaming** |
| `BytesMessage.readBytes(buffer)` | App đọc thành khối | Có lợi ở code xử lý, nhưng phải xác minh client có materialize body trước đó không |
| **Core `setBodyInputStream()`** | Nguồn body qua stream | API chuyên dụng cho large-message streaming phía gửi Artemis |
| **Core `saveToOutputStream()`** | Body được ghi vào stream đích | API chuyên dụng phía nhận, phù hợp file lớn |

JMS là API chuẩn cho interoperability, còn Core API là API riêng Artemis. Nếu bắt buộc tiếp tục dùng JMS, hãy kiểm tra **streaming extension của đúng Artemis JMS client/version** hoặc thiết kế đưa **URI + checksum + metadata** vào JMS message, còn file thật nằm ở object storage chuyên dụng.

**Không trộn `javax.jms` và `jakarta.jms` một cách ngẫu nhiên.** Bản Artemis/client và framework có thể dùng namespace khác nhau, trong khi Core API ở ví dụ này không dùng JMS message interfaces.

### 9.1. Vì sao “message chứa URI đến object storage” cũng là lựa chọn hợp lý?

Với file hàng GiB, nghiệp vụ có thể chọn:

~~~json
{
  "eventId": "file-2026-001",
  "objectUri": "s3://private-bucket/files/2026/001",
  "sizeBytes": 2147483648,
  "sha256": "<base64-digest>",
  "contentType": "application/octet-stream"
}
~~~

Ở đây event JMS chỉ mang metadata nhỏ; worker tải file trực tiếp từ object store theo quyền của mình. Cách này giảm áp lực disk/replication của broker, nhưng mang yêu cầu **retention, xác thực URL, tính bất biến file, checksum, xóa rác và consistency giữa object store với message**. URI không nên chứa token truy cập vĩnh viễn.

Đây là **lựa chọn kiến trúc**, không có nghĩa Artemis large messages không phù hợp: nếu muốn broker quản lý cả body và vòng đời queue/ACK, Core large-message streaming là một giải pháp hợp lệ.

## 10. Vòng đời large-message file và thời điểm dọn dẹp

Một message lớn trải qua các giai đoạn:

~~~mermaid
stateDiagram-v2
    [*] --> Uploading: Producer truyền body
    Uploading --> Queued: send/commit hợp lệ
    Uploading --> Aborted: upload/transaction thất bại
    Queued --> Delivering: Consumer nhận
    Delivering --> Queued: rollback/reconnect
    Delivering --> Completed: ACK/commit
    Queued --> Expired: TTL hết hạn
    Queued --> DeadLettered: chính sách DLQ
    Completed --> CleanupEligible: Không còn reference
    Expired --> CleanupEligible: Nếu không được giữ ở expiry queue
    DeadLettered --> CleanupEligible: Sau khi DLQ không còn giữ reference
    CleanupEligible --> [*]: Broker dọn dữ liệu body
    Aborted --> [*]: Broker xử lý dữ liệu upload bỏ dở
~~~

Đây là **mô hình khái niệm**, không phải tên state nội bộ Artemis hoặc cam kết về thời điểm garbage collection.

Các sự kiện ảnh hưởng việc giữ body:

- Message vẫn còn pending ở một queue.
- Message đã dispatch nhưng chưa ACK.
- Transaction nhận chưa commit, có thể rollback.
- Multicast tạo nhiều queue references.
- Message được chuyển đến DLQ/expiry queue theo policy.
- Snapshot/backup đang cần dữ liệu nhất quán.
- Broker cleanup diễn ra không đồng bộ với thao tác ứng dụng.

**Không lấy số file còn trong thư mục large messages ngay sau ACK làm bằng chứng memory leak.** Quan sát đủ thời gian, số queue references và metric broker trước khi kết luận. Ngược lại, file tăng mãi cùng backlog tăng là dấu hiệu capacity cần xử lý.

## 11. Transaction, ACK và redelivery với body lớn

Large message **không có một mô hình transaction hoàn toàn mới**: send/receive vẫn theo ranh giới Core/JMS của provider.

### 11.1. Producer commit không có nghĩa consumer đã lưu file

~~~text
SENDER:
  InputStream -> producer.send()
  -> session.commit()
  -> message được broker xác nhận

RECEIVER:
  receive()
  -> saveToOutputStream(temp)
  -> checksum/size PASS
  -> publish file đích bền theo storage contract
  -> message.acknowledge()
  -> session.commit()
~~~

Nếu producer mất response `commit()` nhưng broker đã ghi nhận, lần gửi lại có thể tạo hai large messages cùng `blobId`. Với Artemis, duplicate detection ID như `_AMQ_DUPL_ID` có thể hỗ trợ lọc trùng trong phạm vi cache, **nhưng consumer vẫn cần idempotency**.

### 11.2. Crash sau ghi file trước ACK

~~~text
Receiver nhận blob-001
-> file blob-001.bin đã tạo và checksum đúng
-> process crash trước ACK/commit
-> broker redeliver cùng message
-> receiver thấy blob-001.bin và checksum khớp
-> ACK/commit mà không ghi lại file
~~~

Đây là lý do receiver dùng `blobId` + checksum và kiểm tra file đích khi redelivery. Nếu chỉ dùng `JMSMessageID`/Core message ID, một producer retry bằng message mới có thể làm idempotency thất bại.

### 11.3. Crash trong lúc ghi file

Nếu receiver chết giữa `saveToOutputStream()`:

- File `.part` có thể chứa body chưa hoàn chỉnh.
- Message chưa ACK nên broker có thể redeliver theo policy.
- Receiver lần sau tạo một file tạm mới, kiểm checksum trước khi publish.
- Job cleanup chỉ xóa **file tạm** đủ tuổi sau khi xác định không còn lượt ghi hoạt động.

**Không ACK trước khi stream hoàn tất và dữ liệu đầu ra được ghi thành công.** Với một API output-stream **bất đồng bộ**, phải chờ tín hiệu hoàn tất được provider hỗ trợ; nếu không, ACK có thể tới broker trong khi file đích chưa có body đầy đủ.

### 11.4. Nguồn dữ liệu ngoài transaction

Việc `session.commit()` ở broker không tự gom transaction của local filesystem/S3/SQL. Nếu yêu cầu bảo đảm “một blob được publish đúng một lần”, phải thiết kế contract ở layer storage và business: temporary object, checksum, atomic publish/conditional PUT, inbox/unique key và retry cùng ID.

## 12. Hiệu năng, backpressure và giới hạn tài nguyên

Streaming giảm áp lực **heap theo kích thước message**, nhưng không biến body lớn thành “miễn phí”:

| Tài nguyên | Vấn đề khi truyền large message | Cách kiểm soát |
|---|---|---|
| Disk broker | Body files lớn; queue backlog giữ reference | Capacity/headroom, retention/TTL phù hợp, xử lý backlog |
| Network | Upload/download lâu, cạnh tranh băng thông | Rate limit, giới hạn concurrent transfers, timeout có ngân sách |
| CPU | Compression, checksum, mã hóa TLS | Đo CPU, hạn chế số luồng nếu CPU bão hòa |
| Heap client | Buffers, số transfer cùng lúc | Streaming API, giới hạn concurrency, không materialize body |
| Journal/paging | Metadata, queue references, backlog | Theo dõi journal/paging, không nhầm paging với threshold |
| Consumer latency | Một file lớn chiếm worker lâu | Pool phù hợp, tách luồng file lớn/nhỏ nếu cần |
| Retry | Upload lại tốn băng thông, có thể tạo duplicate | event/blob ID ổn định, backoff, idempotency |
| Storage recovery | Backup thiếu large-message body | Snapshot nhất quán, restore drill, đối soát checksum |

### 12.1. Ước lượng capacity đơn giản

Giả sử mỗi message body trung bình **500 MiB**, có 300 message pending; chỉ tính raw body:

\[
300 \times 500\ \mathrm{MiB} = 150{,}000\ \mathrm{MiB} \approx 146.5\ \mathrm{GiB}.
\]

Đây **chưa** bao gồm journal, paging, metadata, replication, bản sao backup, file tạm, DLQ hay overhead của filesystem. Khi thiết kế, dự trữ dung lượng thêm và đo dung lượng thực tế.

Nếu throughput đầu vào lớn hơn khả năng consumer giải phóng references, disk usage có thể tăng liên tục dù heap broker ổn. Đừng coi việc “không OOM” là dấu hiệu hệ thống đã chịu tải bền vững.

### 12.2. Tuning threshold và compression

Một quy trình tuning:

1. Lấy histogram kích thước message (p50/p95/p99, max).
2. Đo heap/GC của producer/consumer với kích thước body lớn nhất thực.
3. Chọn ngưỡng large message hợp lý theo client và giao thức.
4. Kiểm tra overhead file/I/O khi hạ ngưỡng.
5. Nếu bật compression large messages trên client/provider hỗ trợ, đo CPU, network và thời gian end-to-end; không giả định compression luôn có lợi với JPEG/ZIP hoặc dữ liệu đã nén.
6. Đo disk free, paging, journal và latency khi tăng đồng thời số upload.
7. Thử lỗi broker/client trong lúc stream, không chỉ đo khi không có sự cố.

**Một con số threshold đúng cho file 20 MiB chưa chắc đúng cho hàng triệu message 150 KiB mỗi giây.** Cần cân bằng số file/metadata với áp lực heap và đường truyền.

## 13. Fault injection và bài kiểm chứng

### Thử A — File lớn hơn heap

- Dùng file 1 GiB, heap producer nhỏ hơn file (ví dụ 256 MiB) trong môi trường lab đủ disk.
- Sender dùng `setBodyInputStream()`; receiver dùng `saveToOutputStream()`.
- Ghi heap peak, GC, duration, SHA-256.
- Không khẳng định “không có allocation”, chỉ kiểm chứng **không cần 1 GiB byte[]**.

### Thử B — Kill producer giữa upload

- Cho upload large message qua mạng chậm trong môi trường test.
- Kill producer trước commit.
- Kiểm tra broker **không deliver một body thiếu byte như message hợp lệ**.
- Quan sát file tạm/orphan và hành vi cleanup; không tự xóa file nội bộ.
- Retry cùng `blobId` sau khi broker/client ổn định.

### Thử C — Restart broker sau commit trước consume

- Gửi và nhận dòng `COMMIT_CONFIRMED`.
- Không cho consumer ACK.
- Restart broker dùng **cùng journal, bindings và large-messages directory**.
- Receive, xác minh kích thước và checksum.

Thử này chứng minh tính bền theo kịch bản process restart, **không** chứng minh disk failure hoặc HA.

### Thử D — Kill receiver lúc đang stream ra file

- Dùng file đủ lớn để nhận mất vài giây.
- Kill receiver, kiểm tra `.part` có thể tồn tại và message chưa ACK.
- Khởi động receiver mới; xác minh file hoàn chỉnh rồi ACK.
- Đối soát không có file đích hỏng được coi là thành công.

### Thử E — Kill receiver sau publish file trước commit JMS

- Chèn điểm fault injection sau `Files.move`, trước `session.commit()`.
- Broker có thể giao lại.
- Lần nhận sau nhận ra `blobId`/checksum đã lưu, không ghi body hoặc tác động nghiệp vụ lần hai, và ACK.

### Thử F — Hai queue cùng tham chiếu large message

- Gửi large message qua một address multicast có hai queue durable.
- Consumer A ACK, consumer B chưa ACK.
- Không kết luận body phải biến mất ngay khỏi large-messages directory; **B vẫn cần dữ liệu**.
- Sau khi B hoàn tất, theo dõi reference và cleanup theo broker version.

### Thử G — Disk broker gần đầy

- Chỉ thử trong broker lab; giới hạn dung lượng volume test, bật monitoring.
- Upload đủ để gây backpressure/I/O warnings.
- Đo producer latency, errors, queue backlog, disk free, paging và khả năng recover.
- Không để full disk ở production hoặc can thiệp bằng cách xóa file large-message thủ công.

## 14. Những hiểu lầm và cách sửa

| Hiểu lầm | Phân tích chính xác |
|---|---|
| “File 2 GiB chỉ cần `BytesMessage.writeBytes(readAllBytes(...))`.” | Đã cấp phát 2 GiB phía Java trước khi Artemis giúp streaming |
| “Bật `minLargeMessageSize` biến mọi code thành stream.” | Threshold không sửa `String`/`byte[]` mà app đã tạo |
| “Large message là paging.” | Large-message xử lý **body riêng lẻ**; paging xử lý **backlog theo address** |
| “`max-size-bytes` là dung lượng tối đa một file.” | Đây là chính sách quản lý address, không phải file-size limit |
| “Một queue ACK là file body phải xóa tức thì.” | Có thể còn references, DLQ/subscription hoặc cleanup chưa chạy |
| “TextMessage của Artemis không bao giờ tốn nhiều heap.” | App có thể dựng/đọc giant String dù broker stream bên dưới |
| “Chỉ copy journal là backup đủ.” | Large-message files, bindings, paging và state liên quan cũng cần bảo vệ nhất quán |
| “Core `saveToOutputStream()` xong là file bền sau mất điện.” | Output stream close không tự đảm bảo fsync/storage durability |
| “Stream thành công nghĩa là đã ACK JMS.” | ACK/commit là bước độc lập sau khi lưu và xác minh |
| “Producer retry cùng file thì không thể bị duplicate.” | Commit response có thể thất lạc; dùng blobId + idempotency |
| “Có thể xóa file broker large messages để giảm disk.” | Có thể phá references đang được broker quản lý |
| “Artemis Core API và JMS BytesMessage có cùng streaming contract.” | JMS API chuẩn không cam kết cơ chế streaming I/O nội bộ tương tự extension Core |
| “Message lớn thì nên dùng ngay lập tức.” | Có chi phí disk/transfer/recovery; file cực lớn đôi khi hợp hơn với object store + metadata message |

## 15. Bài tập tình huống có lời giải

### A — Threshold 128 KiB, producer đã `readAllBytes()`

Producer đọc file 600 MiB thành byte array rồi tạo JMS BytesMessage. Client đặt large-message threshold 128 KiB.

**Đáp án:** Ngưỡng có thể khiến provider gửi bằng cơ chế large message, nhưng **không xóa được byte array 600 MiB** mà producer đã tạo. Cần API streaming ngay từ bước đọc file.

### B — Gửi thành công, receiver crash trước ACK

Receiver đã ghi file và checksum PASS, nhưng crash trước `session.commit()`. Sau restart cùng blob được deliver lại.

**Đáp án:** Đây là redelivery hợp lệ. Dùng blob ID cố định và kiểm tra file đã được publish với đúng checksum; nếu khớp, ACK mà không thực hiện side effect trùng.

### C — Broker còn journal nhưng mất thư mục large messages

Broker persistent journal được giữ trên volume A; large-messages directory trên volume B tạm bị xóa khi deploy.

**Đáp án:** Journal/queue reference có thể còn nhưng body bị thiếu. Thiết kế lưu trữ/backup sai. Cần bảo vệ **tập dữ liệu broker nhất quán**; không suy từ “journal còn” rằng message body lớn còn.

### D — Upload 200 file, mỗi file 500 MiB

Chỉ tính raw bodies, cần bao nhiêu dung lượng?

**Đáp án:** `200 × 500 MiB = 100.000 MiB ≈ 97,7 GiB`. Phải dự trữ thêm journal, paging, filesystem overhead, replication, backup và tăng trưởng backlog.

### E — Multicast hai queue, một queue chưa ACK

Một large message được route tới queue Billing và Archive. Billing ACK; Archive offline.

**Đáp án:** Message body còn cần cho Archive, do đó **không yêu cầu xóa file ngay**. Khi không còn references và broker cleanup, dữ liệu mới đủ điều kiện dọn.

### F — Core và JMS: chọn API nào?

Ứng dụng cần chuyển file 4 GiB từ disk sang broker và ngược lại với heap 512 MiB, không cần interoperability với provider JMS khác.

**Đáp án:** Core `ClientMessage.setBodyInputStream()` và `saveToOutputStream()` là lựa chọn hợp lý để tránh giữ toàn body trong heap. Nếu phải dùng JMS, cần xác minh extension streaming trên client cụ thể hoặc chọn object store + JMS metadata.

## 16. Checklist trước khi dùng Artemis large messages

- [ ] Đã phân biệt **kích thước body**, **kích thước backlog** và **threshold client**?
- [ ] Input stream đọc file trực tiếp, không `readAllBytes()` hay `getText()` khổng lồ?
- [ ] Output stream lưu file tạm, có checksum/size trước khi publish?
- [ ] Message có `blobId`/event ID bền vững qua retry và consumer xử lý idempotent?
- [ ] Gửi durable + commit và ACK/commit sau khi receiver xử lý phù hợp?
- [ ] Có giới hạn concurrent upload/download, timeout, rate limit và backpressure?
- [ ] Broker large-messages directory nằm trên volume bền cùng với trạng thái journal/bindings/paging liên quan?
- [ ] Không có script xóa file large-message đang được broker tham chiếu?
- [ ] Có metric disk free, backlog, transfer duration, heap/GC, DLQ/expiry và checksum errors?
- [ ] Đã thử producer crash, consumer crash trước ACK, broker restart và disk pressure?
- [ ] Đã chọn threshold theo **protocol/client version**, không copy cấu hình Classic?
- [ ] Có chiến lược backup/restore nhất quán và thử restore?
- [ ] Đã cân nhắc object storage + metadata message nếu kích thước file và retention vượt mục tiêu broker?
- [ ] Khi lưu file đích, đã hiểu `ATOMIC_MOVE`/fsync và khác biệt giữa filesystem với JMS transaction?

## 17. Kết luận

Artemis large messages giải quyết bài toán **truyền và lưu body lớn mà không nhất thiết giữ toàn bộ body trong heap của client/broker**. Với Artemis Core API, `setBodyInputStream()` giúp producer đọc file theo luồng, còn `saveToOutputStream()` giúp consumer ghi ra file theo luồng. Nhưng ngưỡng `minLargeMessageSize`, directory lưu body, paging và thời điểm cleanup là **những khái niệm riêng**.

Một thiết kế thực tế phải đi xa hơn việc tránh OOM: có **commit gửi rõ ràng, checksum/size, file tạm + publish an toàn, ACK sau khi xử lý, idempotency với blob ID**, capacity disk và backup nhất quán. Khi payload quá lớn hoặc cần lifecycle linh hoạt ngoài broker, mô hình **object storage + JMS metadata** cũng đáng cân nhắc. Tính đúng đắn nằm ở **toàn bộ đường truyền, lưu trữ và phục hồi**, không chỉ ở một cờ “large message”.
