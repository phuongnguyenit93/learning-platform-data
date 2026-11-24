# Cấu hình adapter bằng XML namespace

## 1. Mục tiêu và vị trí của XML namespace trong Spring Integration

Trong chương **Tạo integration flow** của module **SPRING_INTEGRATION_ADAPTERS**, một flow có thể được cấu hình bằng Java DSL, annotation hoặc XML. **XML namespace** là cách khai báo các thành phần tích hợp bằng thẻ XML chuyên dụng: channel, inbound/outbound adapter, gateway, poller, transformer và service activator. Spring đọc cấu hình đó khi tạo application context, rồi đăng ký các bean và endpoint tương ứng.

Phạm vi module là kết nối hệ thống ngoài qua **inbound/outbound adapter, gateway, poller và `MessageChannel`**, thực hành với **file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu**, đồng thời hiểu **hợp đồng message, lỗi và vòng đời kết nối**. XML namespace hữu ích khi ứng dụng đã có cấu hình XML hoặc cần thể hiện topology tích hợp tập trung trong một tệp cấu hình.

Sau bài này, người học có thể:

- Đọc và khai báo `xmlns:int` cùng các namespace của adapter như `int-file`, `int-sftp`, `int-http` hoặc `int-jms`.
- Viết một flow file inbound hoàn chỉnh bằng XML: **file source → poller → channel → service activator**.
- Hiểu bean ID, channel name, schema location, dependency và cơ chế import XML vào Spring Boot.
- Cấu hình outbound adapter, phân biệt adapter một chiều với gateway request–reply.
- Tìm và xử lý những lỗi thường gặp: channel không có consumer, poller thiếu, tên bean sai, duplicate, timeout, tài nguyên kết nối.
- Kiểm thử cả wiring XML lẫn hành vi thật của nguồn và hệ thống đích.

**Điều cần nhớ:** XML chỉ là **cách biểu diễn cấu hình**. Khi ứng dụng chạy, cơ chế xử lý vẫn dựa trên các đối tượng Spring Integration như `Message<?>`, `MessageChannel`, `MessageSource`, `MessageHandler` và endpoint.

## 2. Sơ đồ cấu trúc của một XML integration flow

~~~mermaid
flowchart LR
    A["Nguồn ngoài<br/>file / SFTP / DB"]
    B["Inbound adapter"]
    P["Poller"]
    C["MessageChannel"]
    T["Transformer / Filter / Router"]
    D["MessageChannel"]
    E["Service activator<br/>hoặc outbound adapter"]
    F["Hệ thống đích"]
    P -. "kích hoạt receive()" .-> B
    A --> B --> C --> T --> D --> E --> F
~~~

| Thành phần XML | Vai trò | Ví dụ |
| --- | --- | --- |
| `<int:channel>` | Tạo channel nối producer và consumer. | `<int:channel id="files.input"/>`. |
| `<int-file:inbound-channel-adapter>` | Đọc file từ thư mục và phát `Message<File>`. | Poll thư mục `./inbox`. |
| `<int:poller>` | Đặt lịch và giới hạn số message lấy mỗi lượt. | `fixed-delay="5000"`. |
| `<int:transformer>` | Chuyển đổi payload của message. | `File` thành đường dẫn hoặc DTO. |
| `<int:filter>` | Chỉ cho message phù hợp đi tiếp. | Loại message không đủ điều kiện. |
| `<int:service-activator>` | Gọi method Java khi nhận message. | Gọi service đọc CSV. |
| `<int-file:outbound-channel-adapter>` | Ghi message thành file ở đích. | Gửi file đến thư mục xuất. |
| Gateway trong namespace | Kết nối một bên request–reply với flow. | Messaging gateway hoặc HTTP gateway. |

Một adapter **inbound** đưa dữ liệu từ bên ngoài vào channel. Adapter **outbound** nhận message trong channel để gửi dữ liệu ra ngoài. Một **gateway** thường có hợp đồng phản hồi; một **poller** áp dụng cho endpoint chủ động lấy dữ liệu, không phải mọi endpoint đều cần poller.

Ví dụ một HTTP inbound gateway thường được kích hoạt bởi HTTP request, còn file inbound adapter phải quét thư mục theo lịch.

## 3. Khai báo namespace, schema và dependency

### 3.1. XML namespace giải quyết điều gì?

Thay vì tự khai báo từng bean factory, listener và polling endpoint, ta dùng các tag tên miền:

~~~xml
<int:channel id="files.input"/>

<int-file:inbound-channel-adapter
        id="csvInbound"
        channel="files.input"
        directory="${adapter.inbox}"
        filename-pattern="*.csv">
    <int:poller fixed-delay="5000" max-messages-per-poll="5"/>
</int-file:inbound-channel-adapter>
~~~

Spring Integration xử lý tag `int-file:inbound-channel-adapter` để đăng ký **message source và endpoint polling**. Namespace `int` tạo channel và poller. Tên `files.input` là tên bean channel dùng để nối các thành phần, trong khi `csvInbound` nhận diện endpoint adapter để quản lý và quan sát.

### 3.2. Khai báo đầy đủ các namespace cần thiết

Một tệp XML chứa file inbound adapter có dạng khung:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-file="http://www.springframework.org/schema/integration/file"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           http://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd
           http://www.springframework.org/schema/integration/file
           http://www.springframework.org/schema/integration/file/spring-integration-file.xsd">

    <!-- Khai báo channel, adapter, poller và handler tại đây. -->

</beans>
~~~

Các mục trong `xsi:schemaLocation` đi theo **cặp namespace URI và đường dẫn XSD**. Prefix như `int` hoặc `int-file` chỉ là bí danh do người viết chọn; nội dung URI mới xác định namespace thật. Trình đọc XML dùng namespace URI + schema và các bộ parser của Spring để hiểu tag.

Không khai báo `xmlns:int-file` rồi dùng `<int-file:...>` nếu dependency `spring-integration-file` không có trên classpath: parser và implementation tương ứng cần được cung cấp bởi module của adapter. Tương tự, không phải cứ thêm namespace vào XML là đã tạo được connection tới JMS, SFTP hay Kafka.

### 3.3. Các dependency Maven tối thiểu

Với Spring Boot quản lý phiên bản dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-file</artifactId>
</dependency>
~~~

Starter cung cấp phần integration core và cấu hình Boot cần thiết. `spring-integration-file` cung cấp adapter file và XML namespace của module file. Khi dùng SFTP, HTTP, JMS, AMQP, Kafka hoặc JDBC cần dependency Spring Integration tương ứng, có thể cần thêm client driver, connection factory hoặc thư viện giao thức.

**Về phiên bản:** ưu tiên để Spring Boot BOM quản lý phiên bản Spring Integration trong cùng dự án. Không kết hợp tùy ý các module Spring Integration thuộc nhiều dòng phiên bản khác nhau vì namespace parser, API và cách xử lý adapter có thể không tương thích.

## 4. Ví dụ hoàn chỉnh: đọc CSV bằng XML inbound adapter

Bài toán: một ứng dụng theo dõi thư mục `./inbox`, mỗi 5 giây quét các file có đuôi `.csv` và gửi từng `File` vào một service Java. Đây là ví dụ thực hành về **wiring nguồn file**, chưa phải hệ thống nhập dữ liệu CSV an toàn cho production.

### 4.1. Cấu trúc tệp minh họa

~~~text
src/main/java/demo/xmladapter/
    XmlAdapterApplication.java
    CsvFileProcessor.java

src/main/resources/
    adapter.properties
    integration/file-flow.xml
~~~

Thư mục `./inbox` nằm tương đối với **working directory lúc chạy ứng dụng**, không tự đồng nghĩa với `src/main/resources`. Tạo thư mục này trước khi khởi động hoặc thiết kế bước tạo thư mục rõ ràng.

### 4.2. Cấu hình integration/file-flow.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:context="http://www.springframework.org/schema/context"
       xmlns:int="http://www.springframework.org/schema/integration"
       xmlns:int-file="http://www.springframework.org/schema/integration/file"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           http://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/context
           http://www.springframework.org/schema/context/spring-context.xsd
           http://www.springframework.org/schema/integration
           http://www.springframework.org/schema/integration/spring-integration.xsd
           http://www.springframework.org/schema/integration/file
           http://www.springframework.org/schema/integration/file/spring-integration-file.xsd">

    <context:property-placeholder
            location="classpath:adapter.properties"/>

    <!-- 1. Channel nhận message File từ adapter. -->
    <int:channel id="files.input"/>

    <!-- 2. Bean Java xử lý message từ channel. -->
    <bean id="csvFileProcessor"
          class="demo.xmladapter.CsvFileProcessor"/>

    <!-- 3. Inbound adapter chủ động tìm file CSV. -->
    <int-file:inbound-channel-adapter
            id="csvInbound"
            channel="files.input"
            directory="${adapter.inbox}"
            filename-pattern="*.csv">
        <int:poller
                fixed-delay="5000"
                max-messages-per-poll="5"/>
    </int-file:inbound-channel-adapter>

    <!-- 4. Consumer thực hiện thao tác cuối. -->
    <int:service-activator
            id="processCsv"
            input-channel="files.input"
            ref="csvFileProcessor"
            method="process"/>

</beans>
~~~

Tệp `src/main/resources/adapter.properties`:

~~~properties
adapter.inbox=./inbox
~~~

Điểm nối quan trọng là tên channel **`files.input`**: adapter phát message tới channel này, còn service activator đăng ký nhận từ chính channel đó.

### 4.3. Class xử lý file

~~~java
package demo.xmladapter;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class CsvFileProcessor {

    private final Set<Path> handledFiles =
            ConcurrentHashMap.newKeySet();

    public void process(File file) throws IOException {
        Path path = file.toPath().toRealPath();
        String contents = Files.readString(path, StandardCharsets.UTF_8);

        // Demo chỉ đọc nội dung và ghi nhận đường dẫn.
        System.out.printf("Nhận CSV: %s (%d ký tự)%n",
                path, contents.length());
        handledFiles.add(path);
    }

    public boolean wasHandled(Path file) throws IOException {
        return handledFiles.contains(file.toRealPath());
    }
}
~~~

Vì `CsvFileProcessor` được khai báo bằng `<bean>` trong XML, không cần đặt thêm `@Component` để tạo **bean thứ hai**. Method `process(File)` được gọi khi message có payload `File` đi vào `files.input`.

Trong ví dụ, `handledFiles` chỉ hỗ trợ kiểm thử và quan sát **trong tiến trình đang chạy**. Nó không phải kho checkpoint bền vững. Nếu handler lỗi sau khi nguồn đã đánh dấu file được nhận, endpoint không tự khôi phục đúng file chỉ vì có một `Set` trong Java.

### 4.4. Import XML vào ứng dụng Spring Boot

~~~java
package demo.xmladapter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ImportResource;

@SpringBootApplication
@ImportResource("classpath:integration/file-flow.xml")
public class XmlAdapterApplication {

    public static void main(String[] args) {
        SpringApplication.run(XmlAdapterApplication.class, args);
    }
}
~~~

`@ImportResource` yêu cầu Spring nạp bean definitions từ XML. Các bean channel, inbound adapter, service activator và processor nằm trong **cùng application context** với các bean Java của Spring Boot.

Có thể sử dụng XML bean context độc lập trong ứng dụng Spring truyền thống; với Boot, `@ImportResource` giúp kết hợp XML với Java configuration và dependency injection. Không cần tạo thủ công cùng channel hoặc adapter bằng `@Bean` lần nữa.

### 4.5. Theo dõi một lượt polling

Giả sử thư mục có ba file:

~~~text
./inbox/
    order-01.csv
    order-02.csv
    note.txt
~~~

Với `filename-pattern="*.csv"`, nguồn file sẽ chọn các file CSV phù hợp. Poller mỗi lượt có thể nhận tối đa năm message theo `max-messages-per-poll="5"`; vì chỉ có hai file CSV nên số message nhận được có thể thấp hơn giới hạn. File `note.txt` bị loại ở tầng lọc nguồn.

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant A as csvInbound
    participant C as files.input
    participant S as CsvFileProcessor
    P->>A: Kích hoạt theo fixed-delay
    A->>A: Tìm file *.csv
    A->>C: Message<File>(order-01.csv)
    C->>S: process(File)
    A->>C: Message<File>(order-02.csv)
    C->>S: process(File)
    P-->>P: Kết thúc lượt, chờ lịch kế
~~~

Việc file có được phát lại sau một lần poll hay sau restart tùy **filter, trạng thái lưu trữ và hành vi nguồn**. Lọc theo tên file không thay thế chiến lược ngăn xử lý trùng. Nếu cần file chỉ xuất hiện một lần xuyên restart, phải dùng chính sách archive/checkpoint hoặc filter có trạng thái bền vững phù hợp.

## 5. Các thuộc tính adapter XML cần hiểu

| Thuộc tính/phần tử | Ý nghĩa | Câu hỏi cần trả lời khi cấu hình |
| --- | --- | --- |
| `id` | Tên endpoint/bean để quản lý và theo dõi. | Có trùng với bean khác không? |
| `channel` | Channel mà inbound adapter gửi message tới. | Có consumer nào nhận không? |
| `directory` | Thư mục nguồn/đích khi dùng file adapter. | Đường dẫn thực tế và quyền truy cập là gì? |
| `filename-pattern` | Quy tắc chọn tên file nguồn. | Có bỏ sót hoặc nhận nhầm file đang ghi dở không? |
| `<int:poller>` | Lịch gọi nguồn. | Poll nhanh hay chậm, xử lý có chặn thread không? |
| `max-messages-per-poll` | Giới hạn message trong **một lượt** poll. | Cần giới hạn tải của nguồn và consumer bao nhiêu? |
| `input-channel` | Channel service activator/transformer nhận từ đó. | Tên channel có khớp với đầu ra của bước trước? |
| `ref` / `method` | Bean và method Java được gọi. | Spring có tạo bean đó không, method nhận payload đúng kiểu không? |

Trong XML, một sai lệch nhỏ như `files.inputs` thay cho `files.input` có thể khiến message đi đến sai channel hoặc không có consumer. Đặt tên nhất quán theo các chặng của luồng và giữ mapping payload rõ ràng giữa các endpoint.

### 5.1. Poller không phải xử lý batch nghiệp vụ

Ví dụ:

~~~xml
<int:poller fixed-delay="2000" max-messages-per-poll="10"/>
~~~

Nghĩa là một lượt có thể lấy tối đa **10 message** từ nguồn, chứ không có nghĩa framework tự gom chúng thành một `Message<List<File>>`. Nếu nguồn trả một message chứa danh sách 100 bản ghi, con số 10 vẫn đếm **message**, không đếm từng phần tử của danh sách.

`fixed-delay` mô tả độ trễ giữa các lượt chạy theo kiểu delay; `fixed-rate` nhắm đến chu kỳ đều theo thời gian bắt đầu; `cron` chạy theo lịch biểu. Chọn một kiểu trigger phù hợp và xác định rõ tần suất thực tế khi handler chậm.

### 5.2. Polling và đường lỗi

Khi service activator hoặc outbound handler ném exception trong lúc poller chuyển message qua channel đồng bộ, lỗi xuất hiện tại quá trình poll; cơ chế error handling sẽ phụ thuộc scheduler, endpoint và cấu hình error channel/advice. Nếu xử lý đã chuyển sang một queue/executor/broker, exception có thể diễn ra trên thread khác và không quay lại poller.

Vì vậy cần phân biệt:

1. **Đọc nguồn thất bại:** chưa lấy được file hoặc record; có thể cần thử lại ở source.
2. **Đã nhận message nhưng xử lý thất bại:** kiểm tra trạng thái nguồn, retry và khả năng gửi lại đúng message.
3. **Đã ghi ra hệ thống ngoài nhưng mất phản hồi:** nguy cơ duplicate nếu retry thiếu idempotency.

Việc poller chạy lại đúng lịch **không bảo đảm** message thất bại sẽ tự được thử lại.

## 6. Cấu hình outbound adapter bằng XML namespace

XML namespace cũng dùng để khai báo chiều **đi ra hệ thống ngoài**. Với file outbound adapter, ví dụ một channel dành cho message chứa file cần ghi sang thư mục khác:

~~~xml
<!-- Thêm các khai báo này vào bên trong <beans> có int và int-file. -->
<int:channel id="files.toExport"/>

<int-file:outbound-channel-adapter
        id="csvOutbound"
        channel="files.toExport"
        directory="${adapter.outbox}"/>
~~~

Tệp properties bổ sung:

~~~properties
adapter.outbox=./outbox
~~~

Nếu input của adapter là `Message<File>` phù hợp, endpoint file outbound có thể ghi/copy dữ liệu vào thư mục đích theo quy tắc của file-writing handler. Tên file, hành vi khi file đích đã tồn tại, tạo thư mục, thao tác ghi tạm/rename và quyền truy cập phải được kiểm tra theo cấu hình và phiên bản adapter.

Ví dụ Java gửi message **tới channel outbound**, giả sử đã inject đúng bean channel:

~~~java
Message<File> message = MessageBuilder
        .withPayload(new File("./inbox/order-01.csv"))
        .build();

boolean accepted = filesToExportChannel.send(message);
~~~

`accepted` phản ánh thao tác gửi qua Spring `MessageChannel`. Không dùng nó làm chứng cứ rằng file đã an toàn trên hệ thống đích hoặc đã được bên nhận xử lý. Với `DirectChannel`, handler đồng bộ có thể ném exception ngay tại lời gọi `send`; với channel async/queue, thời điểm xác nhận có thể khác.

**Lưu ý về ví dụ:** snippet outbound là cấu hình độc lập. Nếu dùng đồng thời với ví dụ mục 4, không tự nối thêm một `<int:bridge>` từ `files.input` sang `files.toExport` khi đã có service activator trên `files.input`: mặc định channel dạng point-to-point không nhân bản cùng message cho tất cả consumer. Nếu cần vừa xử lý CSV vừa xuất file, hãy định nghĩa flow, điểm chuyển và semantics fan-out rõ ràng.

## 7. Transformer, filter và service activator bằng XML

Bên cạnh adapter, core namespace cho phép nối các bước xử lý:

~~~xml
<int:channel id="files.raw"/>
<int:channel id="files.paths"/>

<int:transformer
        input-channel="files.raw"
        output-channel="files.paths"
        expression="payload.absolutePath"/>

<bean id="pathHandler" class="demo.xmladapter.PathHandler"/>

<int:service-activator
        input-channel="files.paths"
        ref="pathHandler"
        method="handle"/>
~~~

Đoạn trên là **một flow minh họa riêng**. `<int:transformer>` dùng Spring Expression Language để đổi payload `File` thành `String` chứa đường dẫn tuyệt đối. `PathHandler.handle(String path)` là method ứng dụng cần tự cung cấp; class này không được tạo trong ví dụ chạy được ở mục 4.

Nếu cần lọc message sau khi adapter đã phát ra, có thể dùng core filter:

~~~xml
<int:filter input-channel="events.raw"
            output-channel="events.valid"
            expression="payload != null"/>
~~~

Ví dụ chỉ minh họa cú pháp expression; với source Spring Integration thông thường, payload của `Message<?>` phải khác null, nên điều kiện trên gần như không bổ sung validation nghiệp vụ. Khi triển khai, thay bằng quy tắc thực tế (mã giao dịch hợp lệ, ngày cập nhật, nguồn được phép...).

**Khác biệt quan trọng:** filter file ngay ở source quyết định **file nào được phát thành message**; filter trong flow quyết định **message nào được đi tiếp**. Khi một filter trong flow loại message mà phía trên có gateway request–reply chờ kết quả, phải quy định cách trả lỗi hoặc phản hồi từ chối, tránh timeout không rõ nguyên nhân.

## 8. Các namespace adapter thường gặp trong module

Mỗi adapter theo giao thức có namespace và dependency tương ứng. Cách đặt prefix có thể thay đổi, nhưng URI namespace phải đúng và có module hỗ trợ.

| Nhóm | Prefix thường dùng | Endpoint/ý nghĩa | Ghi chú triển khai |
| --- | --- | --- | --- |
| File | `int-file` | File inbound/outbound adapter. | Directory, filter, file đang ghi, ghi tạm và rename. |
| SFTP | `int-sftp` | Đồng bộ/đọc file từ server, gửi file. | Session factory, remote path, reconnect, local cache. |
| HTTP | `int-http` | HTTP inbound/outbound gateway hoặc adapter tương ứng. | URL/path, method, status, timeout và mapping body/header. |
| JMS | `int-jms` | Message-driven inbound, outbound adapter/gateway. | ConnectionFactory, destination, ack, transaction. |
| AMQP | `int-amqp` | Listener và outbound adapter/gateway. | Exchange, routing key, queue, publisher confirm. |
| Kafka | `int-kafka` | Kafka inbound/outbound endpoint theo module hỗ trợ. | Topic/partition, offset commit, serialization và retry. |
| JDBC/database | `int-jdbc` | Poll dữ liệu qua query và gửi tới DB. | DataSource, query, checkpoint, transaction, locking. |

Ví dụ, khi khai báo SFTP XML, thường cần:

~~~xml
xmlns:int-sftp="http://www.springframework.org/schema/integration/sftp"
~~~

Và bổ sung cặp namespace/XSD của SFTP trong `xsi:schemaLocation`, cùng dependency `spring-integration-sftp` và bean session factory. Khi thiếu một trong các phần đó, cấu hình chưa đủ để kết nối thực tế. Không copy một thẻ SFTP rồi kỳ vọng Spring tự biết host, credentials, remote directory và chính sách xác thực server.

**Lưu ý:** mức độ hỗ trợ và thuộc tính XML của từng protocol phụ thuộc phiên bản Spring Integration. Hãy kiểm tra XSD/tài liệu của **phiên bản dependency đang dùng** trước khi mang thuộc tính từ ví dụ đời cũ vào cấu hình hiện tại.

### 8.1. Khi nào inbound cần poller?

- **File, SFTP hoặc JDBC polling**: thường dùng poller vì nguồn được kiểm tra chủ động theo lịch.
- **HTTP inbound gateway**: request đến từ HTTP server, không cần poller chung để nhận request.
- **JMS/AMQP/Kafka message-driven inbound**: listener container/broker kiểm soát quá trình nhận; thường không dùng `<int:poller>` như file inbound.

Đừng đánh đồng việc hệ thống có message queue với việc phải dùng polling adapter. Mỗi giao thức có cơ chế delivery, acknowledgement và transaction khác nhau.

## 9. XML cấu hình gateway khác outbound adapter như thế nào?

Một messaging gateway XML có thể tạo proxy cho interface Java. Ví dụ giao diện đã tồn tại `demo.xmladapter.OrderGateway`:

~~~xml
<int:gateway
        id="orderGateway"
        service-interface="demo.xmladapter.OrderGateway"
        default-request-channel="orders.requests"/>
~~~

Thẻ này diễn đạt **Java method → request message channel**. Nếu method có giá trị trả về, flow phải tạo reply thích hợp.

Ngược lại, HTTP outbound gateway diễn đạt **message trong flow → HTTP request → reply**, còn file outbound adapter chủ yếu diễn đạt **message trong flow → ghi file một chiều**. Không nên dùng gateway chỉ vì tên bài có chữ “adapter”: quyết định đúng dựa trên hợp đồng dữ liệu và yêu cầu phản hồi.

| Tình huống | Thành phần | Đường kết quả |
| --- | --- | --- |
| Java caller muốn gọi flow như service. | `<int:gateway>` hoặc `@MessagingGateway`. | Reply trả về Java method nếu có. |
| Flow nhận một HTTP request từ client ngoài. | HTTP inbound gateway. | HTTP response về client. |
| Flow gọi API đối tác và cần response. | HTTP outbound gateway. | Response trở lại flow. |
| Flow ghi file đích, không cần reply nghiệp vụ. | File outbound adapter. | Thường kết thúc một chiều; kiểm tra lỗi ghi file. |
| Flow đọc thư mục mỗi vài giây. | File inbound adapter + poller. | Phát message khi có file; không có caller chờ reply. |

XML và Java DSL có thể phối hợp trong cùng application context: XML khai báo channel và adapter, Java DSL đăng ký flow consumer cho channel đó. Điều quan trọng là **không vô tình tạo lại bean cùng tên, đăng ký consumer cạnh tranh trên DirectChannel hoặc nhân đôi endpoint đọc cùng một nguồn**.

## 10. XML so với Java DSL và annotation

Cùng một sơ đồ tích hợp có thể được mô tả bằng nhiều cách:

| Tiêu chí | XML namespace | Java DSL / annotation |
| --- | --- | --- |
| Nơi biểu đạt cấu hình | Tệp XML, property placeholders, bean references. | Class Java, method `@Bean`, DSL và annotation. |
| Tính hiển thị topology | Có thể đọc toàn bộ bean/channel/endpoint trong một tệp. | Có thể duyệt cấu hình bằng IDE, kiểu Java và refactor. |
| Kiểm tra tên channel | Thường dựa trên ID/ref chuỗi, lỗi khi chạy context. | Vẫn có thể dùng chuỗi; có thêm khả năng dùng bean reference. |
| Tái sử dụng logic nghiệp vụ | Bean Java được tham chiếu bởi `ref`/`method`. | Inject bean trực tiếp vào method DSL/handler. |
| Cấu hình adapter | Namespace và schema của module. | Factory/DSL adapter và handler APIs của module. |
| Migration | Có thể chuyển từng flow, miễn không nhân đôi bean. | Có thể tái sử dụng cùng service và channel đã khai báo. |

Ví dụ XML mục 4 biểu diễn chuỗi:

~~~text
int-file:inbound-channel-adapter
    → int:channel
    → int:service-activator
    → CsvFileProcessor.process(File)
~~~

Trong Java DSL, ý tưởng tương đương là khai báo một `IntegrationFlow` từ file inbound source với poller, sau đó `.handle(...)` gọi processor. Không cần thay đổi hợp đồng `File` nếu cả hai cách vẫn phát message tương thích.

Một ứng dụng vận hành lâu năm có thể tiếp tục dùng XML namespace. Khi thay đổi dần sang DSL, giữ các điểm tương tác ổn định: **channel names, DTO/payload, headers, retry semantics, transaction và endpoint lifecycle**.

## 11. Kiểm soát lỗi và vòng đời kết nối

### 11.1. Các giai đoạn cần quan sát

Một luồng outbound điển hình có thể trải qua:

1. **Đọc thành công:** inbound adapter đã tìm/lấy file hoặc record.
2. **Bàn giao message:** source đã gửi message qua `MessageChannel`.
3. **Xử lý nội bộ thành công:** transformer/handler đã chạy xong.
4. **Bàn giao ra đích:** outbound adapter/client báo đã gửi hoặc nhận ack theo protocol.
5. **Nghiệp vụ đích hoàn tất:** hệ thống đích xác nhận đã xử lý theo hợp đồng.

Đừng suy ra bước 5 từ bước 2 hoặc 3. Nếu file đã bị đánh dấu là “đã đọc” trước khi outbound HTTP lỗi, phải có chiến lược **retry/replay** rõ ràng. Nếu HTTP đã xử lý thành công nhưng response mất, retry thiếu idempotency có thể tạo bản ghi trùng.

### 11.2. Lỗi nào xuất hiện ở đâu?

| Loại lỗi | Ví dụ | Thiết kế xử lý |
| --- | --- | --- |
| Khởi tạo XML | Thiếu namespace parser, sai schema, bean ID không tồn tại. | Kiểm tra startup log, dependency, XSD và tham chiếu bean. |
| Kết nối/nguồn | SFTP session timeout, DB unavailable, file permission. | Retry/backoff ở tầng nguồn, cảnh báo và điều kiện dừng phù hợp. |
| Payload/format | CSV lỗi, JSON sai schema, thiếu trường bắt buộc. | Validation và quarantine; không retry vô hạn cùng dữ liệu sai. |
| Delivery nội bộ | Channel không có consumer, queue đầy hoặc endpoint dừng. | Đo queue/channel, giới hạn tải và khôi phục endpoint. |
| Đích từ chối hoặc timeout | HTTP 429/5xx, broker unavailable. | Retry có giới hạn, backoff, idempotency và DLQ/quarantine. |
| Kết quả không chắc chắn | Đích ghi thành công nhưng mất response. | Đối soát bằng ID nghiệp vụ, tránh phát sinh side effect lần hai. |

Với channel đồng bộ như `DirectChannel`, exception từ handler có thể xuất hiện ngay trong đường gửi message. Với queue/executor/broker, lỗi có thể xuất hiện trên thread khác và cần error channel hoặc cơ chế lỗi của adapter. Poller chạy lại không thay thế thiết kế retry ở đúng tầng.

### 11.3. Vòng đời và nhiều instance

Khi Spring context khởi động, các endpoint có thể tự start theo lifecycle. Khi shutdown cần xử lý vấn đề: ngừng poll mới, cho message đang xử lý hoàn tất, giải phóng SFTP/JMS/DB session, đóng thread pool và lưu checkpoint an toàn.

Nếu hai instance cùng poll thư mục hoặc bảng dữ liệu, cả hai có thể thấy cùng một item. Một filter chỉ nhớ file trong RAM của từng instance không đủ ngăn duplicate giữa các tiến trình. Dùng locking/partition/claim record hoặc persistent metadata store theo đặc tính nguồn.

Các metric hữu ích: số message nhận, số file đã xử lý, thời gian poll, latency handler, lỗi mỗi adapter, độ sâu queue, retry, dead-letter và lần kết nối lại.

## 12. Kiểm thử cấu hình XML một cách có mục tiêu

Có ba lớp kiểm thử nên phân biệt:

- **Context wiring:** XML parse được, bean/channel/endpoint tồn tại, method Java được resolve.
- **Message flow:** gửi message vào channel, transformer/handler nhận payload đúng kiểu và headers cần thiết.
- **External behavior:** file thật được phát/ghi, SFTP reconnect, HTTP timeout, JMS ack, DB transaction và duplicate sau restart.

### 12.1. Test wiring XML mà không đợi poller

Với `CsvFileProcessor` ở mục 4, kiểm tra channel gọi service activator trên cùng Spring context. Tạo tệp `src/test/java/demo/xmladapter/XmlAdapterWiringTest.java`:

~~~java
package demo.xmladapter;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest
class XmlAdapterWiringTest {

    @Autowired
    @Qualifier("files.input")
    MessageChannel input;

    @Autowired
    CsvFileProcessor processor;

    @Test
    void xmlServiceActivatorReceivesFilePayload() throws Exception {
        Path csv = Files.createTempFile("xml-adapter-", ".csv");
        try {
            Files.writeString(csv,
                    "orderId,amount\nORD-1001,250000\n",
                    StandardCharsets.UTF_8);

            boolean sent = input.send(
                    MessageBuilder.withPayload(csv.toFile()).build());

            assertTrue(sent);
            assertTrue(processor.wasHandled(csv));
        } finally {
            Files.deleteIfExists(csv);
        }
    }
}
~~~

Khai báo dependency test:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Test này chứng minh **XML channel → service activator → bean Java** được kết nối và xử lý đồng bộ. Nó **chưa chứng minh poller đã phát hiện file** vì test gửi message trực tiếp. Trong môi trường test, bảo đảm thư mục `./inbox` đã tồn tại hoặc cấu hình một thư mục test riêng để endpoint inbound khởi động ổn định.

### 12.2. Test inbound polling thực sự

Để kiểm tra file inbound adapter:

1. Dùng thư mục tạm riêng cho test, gán giá trị `adapter.inbox` tương ứng **trước khi context được tạo**.
2. Ghi một file `.csv` và một file `.txt`, với nội dung và tên khác nhau.
3. Dùng latch hoặc điều kiện chờ có timeout để quan sát processor nhận đúng file CSV. Không khẳng định chính xác thứ tự file nếu adapter không quy định thứ tự.
4. Xác nhận file `.txt` không đi qua handler, kiểm tra hành vi khi file bị ghi dở.
5. Khởi động lại context để kiểm tra duplicate, vì trạng thái trong RAM có thể bị mất.

Với outbound adapter, kiểm tra file thực sự được tạo đúng nơi, nội dung và tên phù hợp; sau đó kiểm tra trường hợp file đích đã tồn tại, quyền ghi bị từ chối và lỗi giữa chừng.

## 13. Những lỗi cấu hình thường gặp

| Hiện tượng | Khả năng gây ra | Cách kiểm tra |
| --- | --- | --- |
| Startup báo không hiểu thẻ `int-file:...`. | Thiếu namespace, sai schema hoặc thiếu module `spring-integration-file`. | Kiểm tra `xmlns`, `xsi:schemaLocation` và dependency. |
| Spring không resolve được `${adapter.inbox}`. | Chưa nạp properties hoặc sai tên key. | Kiểm tra `<context:property-placeholder>`, classpath và profile. |
| Poller chạy nhưng không có message. | Thư mục rỗng, sai đường dẫn, sai pattern hoặc file đã bị filter. | Xác nhận working directory, nguồn và quy tắc filter. |
| Message gửi vào channel nhưng không xử lý. | Sai `input-channel` hoặc thiếu consumer. | So khớp ID channel và xem endpoint đã start. |
| Flow xử lý chậm dù poller nhanh. | `DirectChannel` và handler đang block. | Đo thời gian xử lý, timeouts và giới hạn mỗi poll. |
| Cùng file bị xử lý hai lần sau restart. | Trạng thái dedup không bền vững. | Dùng persistent state, archive và idempotency. |
| Gửi outbound bị lỗi file tồn tại. | Quy tắc tên file hoặc chính sách file-exists chưa phù hợp. | Xác định chiến lược tên duy nhất/replace/fail và kiểm thử. |
| Có hai consumer nhưng chỉ một consumer chạy. | `DirectChannel` không mặc định broadcast. | Chọn `PublishSubscribeChannel` khi thực sự cần fan-out. |
| Gateway chờ reply không có hồi đáp. | Adapter one-way hoặc filter loại message. | Phân biệt request–reply và one-way, thiết kế đường reply. |
| Nâng phiên bản rồi XML không hợp lệ. | Thuộc tính cũ hoặc schema parser đã thay đổi. | Kiểm tra XSD của đúng phiên bản Spring Integration. |

## 14. Bài thực hành mở rộng

**Tình huống:** hệ thống nhận file thanh toán từ một thư mục và gửi dữ liệu sang dịch vụ đối tác. Hãy xây cấu hình XML với yêu cầu:

1. Tạo `<int-file:inbound-channel-adapter>` quét `./inbox` mỗi 3 giây; chỉ nhận file `payment-*.csv` và giới hạn tối đa 4 message mỗi poll.
2. Khai báo channel `payments.files` và service activator Java đọc file CSV, chuyển mỗi dòng thành một `PaymentCommand` hợp lệ.
3. Phân tách flow nhận file và flow xử lý từng lệnh, có quy ước metadata `sourceFile`, `correlationId` và `idempotencyKey`.
4. Gửi message sang một outbound endpoint (file hoặc service/client giả lập) và ghi lại trạng thái thành công theo ID.
5. File sai schema phải được chuyển tới khu vực kiểm duyệt, có thông tin lỗi để sửa và chạy lại.
6. Mô phỏng đích timeout sau khi đã nhận lệnh; chứng minh retry không tạo bản ghi trùng.
7. Thay source local file bằng SFTP, thêm bean session factory, filter file từ xa, quy tắc đồng bộ về local và chính sách reconnect.
8. Chạy hai instance cùng quét nguồn và giải thích cần cơ chế nào để tránh xử lý trùng.

**Tiêu chí đạt:** XML khởi tạo được trong Spring context; tên channel khớp; poller giới hạn đúng số message; message contract có payload/header rõ ràng; có test lỗi, retry, restart và duplicate. Nếu cùng giải pháp viết bằng Java DSL, hãy chỉ ra các bean/endpoint tương ứng giữa hai cách cấu hình.

## 15. Câu hỏi tự kiểm tra

1. `xmlns:int` và `xmlns:int-file` có nhiệm vụ khác nhau như thế nào?
2. Vì sao phải có cả namespace/XSD và dependency đúng module?
3. `id="csvInbound"` khác `channel="files.input"` ra sao?
4. Tại sao file inbound adapter cần `<int:poller>` mà HTTP inbound gateway thông thường không cần?
5. `max-messages-per-poll="5"` đếm message hay dòng dữ liệu bên trong một file?
6. Trong `<int:service-activator>`, `ref` và `method` tham chiếu đến đâu?
7. Nếu XML khai báo hai consumer trên cùng `DirectChannel`, chúng có cùng nhận một message không?
8. Vì sao `MessageChannel.send()` thành công chưa chứng minh đối tác đã hoàn thành giao dịch?
9. Điều gì xảy ra khi trạng thái chống đọc trùng chỉ lưu trong bộ nhớ rồi ứng dụng restart?
10. Có thể dùng XML và Java DSL trong cùng ứng dụng không? Cần tránh loại xung đột nào?

**Gợi ý trả lời:** namespace ánh xạ cú pháp XML vào parser/bean Spring Integration; channel ID kết nối các endpoint; poller điều khiển quá trình source chủ động nhận message; service activator gọi logic Java; độ bền và xác nhận nghiệp vụ là vấn đề riêng của nguồn/đích và trạng thái tích hợp.

## 16. Ghi nhớ

Cấu hình adapter bằng **XML namespace** cho phép mô tả nguồn vào, channel, poller, bước xử lý và đích ngoài hệ thống một cách tường minh. Ví dụ `int-file:inbound-channel-adapter` cùng `int:poller`, `int:channel` và `int:service-activator` tạo thành một flow nhận file đến handler Java mà không cần viết toàn bộ phần wiring bằng Java DSL.

Khi đổi sang SFTP, HTTP, JMS, AMQP, Kafka hoặc database, phần **hợp đồng message** và các khái niệm channel, adapter, gateway vẫn có thể giữ nguyên; phần namespace, connection factory/session, acknowledgement, timeout và retry phải được cấu hình theo đúng giao thức. Chất lượng hệ thống phụ thuộc vào xác minh flow đã đăng ký đúng, dữ liệu có thể khôi phục sau lỗi và side effect outbound không bị thực hiện trùng.

