# Transactional outbox và xử lý lặp lại như phương án phối hợp dữ liệu

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích lỗi dual-write khi một nghiệp vụ vừa cập nhật database vừa gửi JMS Message.
- Thiết kế transactional outbox để lưu thay đổi nghiệp vụ và sự kiện trong cùng một database transaction.
- Tổ chức relay đọc outbox, gửi Message tới JMS rồi đánh dấu sự kiện đã phát.
- Hiểu vì sao outbox thường cung cấp at-least-once publication và có thể tạo duplicate.
- Thiết kế idempotent consumer bằng inbox/deduplication record được commit cùng side effect nghiệp vụ.
- Phân biệt JMS local transaction với database transaction và hiểu cửa sổ lỗi giữa hai lần commit.
- Xử lý retry, poison event, dead-letter, ordering, concurrency và retention.
- Biết khi nào nên dùng polling relay, CDC hoặc XA/JTA.
- Triển khai ví dụ Java 17 với Spring JMS, Spring JDBC, H2 và ActiveMQ Classic.

## 1. Bài toán dual-write giữa database và JMS

Một service thường thực hiện hai hành động trong cùng một nghiệp vụ:

1. Cập nhật dữ liệu nghiệp vụ vào database.
2. Gửi một event qua JMS để các service khác phản ứng.

Ví dụ khi tạo đơn hàng, ứng dụng lưu đơn hàng rồi phát event order.created tới Queue hoặc Topic.

Nếu hai hành động này dùng hai resource độc lập, một transaction thông thường không thể tự động bảo đảm cả hai cùng thành công hoặc cùng thất bại.

~~~mermaid
flowchart LR
    A["Tạo đơn hàng"]
    B["Database commit"]
    C["JMS send"]
    D["Service downstream"]

    A --> B --> C --> D
~~~

Hai thứ tự thực hiện đều có cửa sổ lỗi:

- **Database trước, JMS sau:** database commit thành công, nhưng ứng dụng dừng hoặc broker lỗi trước khi gửi Message. Đơn hàng tồn tại nhưng downstream không nhận được event.
- **JMS trước, database sau:** broker nhận Message, nhưng database transaction rollback. Downstream xử lý một event cho thay đổi nghiệp vụ chưa được commit.

Đây là lỗi dual-write. Việc gọi database trong một transaction rồi gọi JmsTemplate ngay sau đó không làm hai resource trở thành một transaction nguyên tử.

Một broker hỗ trợ persistent delivery cũng không tự giải quyết dual-write. Persistent delivery giúp broker lưu Message sau khi nhận; nó không phối hợp commit với database của service phát event.

## 2. Transactional outbox giải quyết vấn đề như thế nào?

Transactional outbox lưu event cần phát vào một bảng outbox trong chính database đang lưu dữ liệu nghiệp vụ. Thay đổi nghiệp vụ và bản ghi outbox được ghi trong cùng một local database transaction.

Một tiến trình relay riêng đọc các bản ghi outbox đã commit, gửi event tới JMS rồi đánh dấu bản ghi đã phát.

~~~mermaid
flowchart TB
    A["Application service"]
    B["Một database transaction"]
    C["Bảng nghiệp vụ"]
    D["Bảng outbox"]
    E["Outbox relay"]
    F["JMS broker"]
    G["Consumer"]
    A --> B
    B --> C
    B --> D
    D --> E --> F --> G
~~~

Quy tắc quan trọng:

- Nếu transaction nghiệp vụ rollback, cả dữ liệu nghiệp vụ và outbox event đều rollback.
- Nếu transaction commit, cả dữ liệu nghiệp vụ và outbox event đều tồn tại.
- Relay chỉ đọc những event đã được commit, sau đó thử gửi chúng tới broker.
- Nếu broker tạm thời không sẵn sàng, event vẫn còn trong outbox để relay thử lại.

Outbox biến việc phát event thành một công việc có thể phục hồi sau khi database commit. Ứng dụng không còn phụ thuộc vào việc một lời gọi gửi JMS phải thành công ngay trong cùng thời điểm với transaction nghiệp vụ.

## 3. Cấu trúc bảng outbox

Một bảng outbox thực tế thường lưu các trường sau:

| Trường | Mục đích |
|---|---|
| event_id | ID duy nhất, ổn định của event |
| aggregate_type | Loại aggregate, ví dụ Order |
| aggregate_id | ID đơn hàng hoặc entity nguồn |
| aggregate_version | Phiên bản/sequence để kiểm soát thứ tự |
| event_type | Loại event, ví dụ order.created |
| destination | Queue hoặc Topic cần phát |
| payload | Nội dung event đã được chụp tại thời điểm phát sinh |
| status | Trạng thái NEW, IN_PROGRESS, PUBLISHED hoặc FAILED |
| attempts | Số lần relay thử gửi |
| created_at | Thời điểm tạo event |
| published_at | Thời điểm relay đánh dấu đã phát |
| last_error | Lỗi gần nhất khi gửi thất bại |

Ví dụ DDL rút gọn:

~~~sql
CREATE TABLE outbox (
    event_id VARCHAR(64) PRIMARY KEY,
    aggregate_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    destination VARCHAR(255) NOT NULL,
    payload CLOB NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL,
    last_error VARCHAR(2000) NULL
);

CREATE INDEX idx_outbox_pending
    ON outbox(status, created_at);
~~~

event_id phải duy nhất và không thay đổi khi relay retry. Consumer dùng ID này để nhận diện một event đã xử lý trước đó.

Payload nên là snapshot bất biến của dữ liệu cần phát. Nếu relay chỉ lưu aggregate_id rồi đọc lại entity ở trạng thái hiện tại, event cũ có thể bị phát với dữ liệu mới hơn và không còn phản ánh đúng thời điểm nghiệp vụ xảy ra.

Trong hệ thống có nhiều loại event, nên lưu schema version hoặc content type. Consumer cần biết cách giải mã payload và xử lý thay đổi schema theo thời gian.

Không nên lưu password, access token hoặc dữ liệu nhạy cảm không cần thiết trong payload. Event có thể đi qua broker, log, trace và nhiều hệ thống downstream.

## 4. Ghi dữ liệu nghiệp vụ và outbox trong cùng transaction

Service nghiệp vụ phải ghi cả aggregate và outbox bằng cùng một transaction manager, cùng một database resource.

Ví dụ:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.insert(order);

    OutboxEvent event = new OutboxEvent(
            UUID.randomUUID().toString(),
            order.getId(),
            "order.created",
            serialize(order)
    );

    outboxRepository.insert(event);
}
~~~

Khi method được gọi qua Spring transaction proxy:

- Spring bắt đầu database transaction.
- Dữ liệu đơn hàng được ghi.
- Event được ghi vào outbox.
- Nếu mọi thao tác hoàn tất, transaction commit.
- Nếu một thao tác ném RuntimeException hoặc Error, mặc định transaction rollback.

Khi transaction commit, database bảo đảm dữ liệu nghiệp vụ và outbox row cùng tồn tại. Nếu insert outbox thất bại, đơn hàng cũng không được commit trong transaction đó.

### 4.1. @Transactional phải được áp dụng thực sự

Trong chế độ proxy mặc định của Spring, @Transactional được kích hoạt khi method được gọi qua Spring proxy. Một method trong cùng class gọi trực tiếp một method khác có @Transactional (self-invocation) thường không đi qua proxy và không mở transaction mới.

Nên đặt ranh giới transaction ở public service method được gọi từ bean khác. Dùng JdbcTemplate hoặc DataSourceUtils để truy cập cùng DataSource mà transaction manager quản lý.

Nếu outbox được ghi sang một database khác với dữ liệu nghiệp vụ, hai thao tác lại trở thành dual-write. Cần đưa outbox vào cùng database transaction với aggregate nguồn.

### 4.2. Không gửi JMS bên trong transaction ghi outbox

Nếu gọi JmsTemplate trong cùng method createOrder, ta lại có hai resource độc lập và quay về bài toán dual-write.

Transactional outbox ghi event trước vào database. Relay gửi JMS sau khi transaction nguồn đã commit. Điều này tách transaction nghiệp vụ khỏi thời điểm broker sẵn sàng.

## 5. Outbox relay: đọc, gửi và đánh dấu

Relay có thể chạy theo lịch, đọc một batch event đang chờ, gửi từng event tới destination rồi cập nhật trạng thái.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant R as Outbox relay
    participant DB as Database
    participant J as JMS broker

    R->>DB: Đọc event NEW
    DB-->>R: Event đã commit
    R->>J: Gửi Message với event_id
    J-->>R: Broker chấp nhận send
    R->>DB: Đánh dấu PUBLISHED
    DB-->>R: Commit trạng thái
~~~

Thứ tự này có chủ ý: chỉ đánh dấu PUBLISHED sau khi thao tác gửi JMS trả về thành công theo hợp đồng của client.

Nếu send thất bại, giữ event ở trạng thái chờ và tăng attempts/last_error. Relay sẽ thử lại theo retry policy.

Tuy nhiên, thứ tự send rồi mark tạo ra một cửa sổ duplicate:

1. Broker đã nhận Message.
2. Ứng dụng relay bị dừng trước khi cập nhật outbox thành PUBLISHED.
3. Khi khởi động lại, relay thấy event vẫn NEW và gửi lại.
4. Broker có thể nhận cùng event_id lần thứ hai.

Đây là hành vi bình thường của outbox relay. Không thể xóa cửa sổ này chỉ bằng cách đổi thứ tự hai thao tác: nếu đánh dấu PUBLISHED trước khi gửi, crash sau khi mark nhưng trước khi send có thể làm mất event.

Vì vậy, outbox thường ưu tiên không mất event và chấp nhận duplicate. Consumer cần idempotent.

## 6. At-least-once và vì sao không nên hứa exactly-once

Outbox relay thường cung cấp mô hình at-least-once publication: event được gửi lại cho tới khi relay ghi nhận đã phát thành công theo chính sách của hệ thống.

Một event có thể xuất hiện nhiều lần vì:

- Relay gửi thành công nhưng crash trước khi mark PUBLISHED.
- Broker hoặc client không trả được kết quả rõ ràng khi kết nối bị ngắt đúng lúc gửi.
- Consumer xử lý xong database nhưng JMS acknowledgement/commit thất bại.
- Broker redelivery sau rollback hoặc mất kết nối.
- Nhà vận hành chủ động replay event.

Do đó, event_id phải ổn định xuyên suốt mọi lần retry. Không tạo UUID mới mỗi lần relay gửi lại, vì consumer sẽ không nhận ra đó là cùng một event.

Exactly-once end-to-end là tuyên bố rất mạnh. Dù broker có deduplication hoặc transaction, side effect bên ngoài broker vẫn có thể lặp nếu ứng dụng crash giữa các ranh giới commit.

Thiết kế thực tế thường là:

- Producer ghi outbox một cách nguyên tử với dữ liệu nghiệp vụ.
- Relay phát at-least-once.
- Consumer deduplicate bằng event_id.
- Side effect của consumer và inbox record được commit cùng một database transaction.
- Các side effect ra hệ thống ngoài dùng idempotency key hoặc một outbox tiếp theo.

## 7. Inbox pattern: lưu dấu event đã xử lý

Consumer cần biết event_id nào đã được xử lý thành công. Có thể tạo bảng inbox:

~~~sql
CREATE TABLE inbox (
    event_id VARCHAR(64) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Khi nhận Message, consumer thực hiện trong một database transaction:

1. Kiểm tra event_id đã có trong inbox chưa.
2. Nếu đã có, bỏ qua side effect và trả về bình thường.
3. Nếu chưa có, ghi event_id vào inbox.
4. Thực hiện side effect nghiệp vụ.
5. Commit cả inbox record và side effect cùng nhau.

Ví dụ:

~~~java
@Transactional
public boolean processEvent(String eventId, OrderCreated event) {
    if (inboxRepository.exists(eventId)) {
        return false; // Duplicate: đã xử lý trước đó
    }

    inboxRepository.insert(eventId);
    orderProjectionRepository.apply(event);

    return true;
}
~~~

Nếu transaction commit, inbox record và side effect cùng tồn tại. Nếu side effect thất bại, transaction rollback cả hai; lần giao lại sau có thể thử xử lý lại.

Nếu database commit thành công nhưng JMS acknowledgement thất bại, broker có thể giao lại Message. Lần tiếp theo consumer tìm thấy event_id trong inbox và bỏ qua side effect.

### 7.1. Unique constraint là hàng rào cuối cùng

Không nên chỉ dựa vào câu lệnh SELECT trước INSERT khi nhiều consumer có thể chạy song song:

- Consumer A kiểm tra event_id chưa tồn tại.
- Consumer B cũng kiểm tra và thấy chưa tồn tại.
- Cả hai cùng cố insert và thực hiện side effect.

Đặt event_id làm primary key/unique constraint. Trong production, nên dùng câu lệnh insert nguyên tử theo dialect database, chẳng hạn INSERT ... ON CONFLICT DO NOTHING trên PostgreSQL, rồi kiểm tra số dòng được insert. Với database khác, dùng cơ chế tương đương.

Nếu insert bị trùng, transaction không được tiếp tục side effect như một lần xử lý mới. Hãy xử lý duplicate theo semantics của database, hoặc để transaction rollback rồi retry và kiểm tra inbox ở lần sau.

Ví dụ chạy bên dưới dùng một consumer thread để giữ luồng kiểm tra tuần tự. Phần hướng dẫn production vẫn yêu cầu unique constraint và insert nguyên tử khi có concurrency.

### 7.2. Inbox và side effect phải cùng database transaction

Nếu inbox record được ghi trong một database nhưng side effect được ghi trong database khác, duplicate window xuất hiện trở lại.

Nếu side effect là gọi HTTP, gửi email hoặc ghi sang hệ thống ngoài, không thể tự động làm nó nguyên tử với inbox database. Hãy truyền event_id như idempotency key nếu hệ thống đích hỗ trợ; nếu không, thiết kế workflow/saga hoặc outbox riêng cho side effect tiếp theo.

## 8. JMS transaction và database transaction là hai ranh giới

Spring JMS cho phép bật local JMS transaction trên listener container:

~~~java
factory.setSessionTransacted(true);
~~~

Mỗi lần listener xử lý Message chạy trong một JMS Session transaction. Nếu listener hoàn tất bình thường, container commit JMS transaction. Nếu listener ném exception, container rollback và broker có thể giao lại Message theo redelivery policy.

Nếu listener gọi một service dùng DataSourceTransactionManager, database transaction đó vẫn là transaction độc lập với JMS local transaction.

Trình tự thường gặp:

~~~mermaid
sequenceDiagram
    participant B as JMS broker
    participant C as Listener container
    participant S as Spring service
    participant D as Database

    B->>C: Giao Message trong JMS transaction
    C->>S: Gọi service
    S->>D: BEGIN database transaction
    S->>D: Ghi inbox và side effect
    D-->>S: COMMIT database
    S-->>C: Method hoàn tất
    C->>B: COMMIT JMS acknowledgement
~~~

Có thể xảy ra tình huống database commit thành công nhưng JMS commit/acknowledgement thất bại. Broker giao lại Message; inbox phát hiện duplicate và ngăn side effect chạy lần nữa.

Nếu database transaction rollback, exception cần được truyền ra khỏi listener để container rollback JMS transaction. Không nuốt exception rồi trả về bình thường, vì khi đó container có thể commit acknowledgement dù nghiệp vụ thất bại.

### 8.1. XA/JTA là lựa chọn khác

Nếu cả database và JMS provider đều có XA resource, JTA transaction coordinator có thể điều phối giao dịch phân tán hai phase commit.

XA có thể cung cấp atomic commit giữa các resource tham gia, nhưng đi kèm yêu cầu cấu hình, recovery log, transaction coordinator, XA-capable connection factory và chi phí vận hành. Nó không thay thế idempotency cho mọi side effect ngoài transaction.

Transactional outbox thường được chọn khi muốn tránh distributed transaction, chấp nhận publication at-least-once và thiết kế consumer idempotent.

## 9. Retry, backoff và dead-letter

Relay cần chính sách retry rõ ràng. Nếu broker đang bảo trì, retry quá nhanh có thể tạo tải không cần thiết và log quá nhiều.

Một chiến lược phổ biến:

- Tăng attempts sau mỗi lần gửi thất bại.
- Dùng exponential backoff có giới hạn và jitter.
- Lưu last_error đủ để chẩn đoán nhưng không ghi bí mật.
- Đặt ngưỡng số lần thử hoặc thời gian chờ.
- Chuyển event không thể xử lý sang trạng thái FAILED/QUARANTINED để operator điều tra.
- Có công cụ replay sau khi nguyên nhân được khắc phục.

Không nên xóa event thất bại ngay. Giữ lại payload, event_id, aggregate_id và lỗi để có thể điều tra hoặc phát lại.

Consumer cũng cần phân biệt:

- **Lỗi tạm thời:** database hoặc dependency đang gián đoạn; có thể rollback để broker redeliver.
- **Lỗi payload/schema:** retry liên tục không giải quyết được; cần dead-letter hoặc quarantine.
- **Lỗi nghiệp vụ không thể khắc phục tự động:** lưu trạng thái và đưa vào quy trình xử lý thủ công.
- **Duplicate:** đây là kết quả đã biết, nên bỏ qua và acknowledge thành công sau khi xác nhận inbox record tồn tại.

Broker thường có maximum redelivery, redelivery delay và dead-letter queue. Cấu hình cụ thể phụ thuộc JMS provider. Outbox relay cũng cần trạng thái lỗi riêng; không đồng nhất relay failure với consumer DLQ.

## 10. Ordering và nhiều relay instance

Ordering cần được thiết kế theo aggregate hoặc partition, không nên chỉ dựa vào ORDER BY created_at.

Nếu hai event của cùng một đơn hàng được phát đồng thời bởi nhiều relay, event version 2 có thể tới broker trước version 1. Nhiều consumer thread cũng có thể hoàn tất xử lý không theo thứ tự gửi.

Các biện pháp thường dùng:

- Lưu aggregate_version hoặc sequence_number trong outbox.
- Chỉ phát event tiếp theo của một aggregate sau khi event trước được xác nhận đã phát.
- Phân vùng relay theo aggregate_id.
- Dùng message group/partition key nếu broker hỗ trợ.
- Consumer kiểm tra version để phát hiện event thiếu hoặc đến sai thứ tự.
- Tăng concurrency chỉ khi nghiệp vụ chấp nhận xử lý song song.

Khi chạy nhiều relay instance, không để tất cả cùng đọc và gửi một row. Có thể claim batch bằng một transaction ngắn với SELECT ... FOR UPDATE SKIP LOCKED nếu database hỗ trợ, hoặc dùng trạng thái claim kèm lease_until và owner_id.

Quy trình claim nên ngắn:

1. Trong database transaction, claim các event NEW và ghi owner/lease.
2. Commit claim transaction.
3. Gửi JMS bên ngoài transaction giữ lock.
4. Đánh dấu PUBLISHED sau khi broker chấp nhận.
5. Nếu worker chết, lease hết hạn để worker khác claim lại.

Không giữ row lock trong khi gọi broker qua mạng. Broker chậm có thể làm transaction và lock kéo dài, gây nghẽn database.

Lease không xóa duplicate window. Worker có thể gửi thành công rồi chết trước khi mark; worker khác sẽ gửi lại sau khi lease hết hạn. Consumer vẫn phải idempotent.

## 11. Polling relay hay CDC?

Có hai cách phổ biến để chuyển outbox event tới broker.

| Cách | Hoạt động | Phù hợp khi |
|---|---|---|
| Polling relay | Ứng dụng định kỳ query outbox và gửi JMS | Muốn ít hạ tầng, logic retry tùy chỉnh, tải vừa phải |
| CDC | Công cụ đọc transaction log của database và phát change event | Lưu lượng cao, muốn giảm polling và có hạ tầng CDC |

Polling dễ triển khai nhưng cần quản lý batch size, claim, retry, ordering và cleanup. Query phải có index theo status/created_at; tránh quét toàn bộ bảng ở mỗi vòng.

CDC đọc log commit của database như WAL/binlog và chỉ thấy thay đổi đã commit. Debezium Outbox Event Router là ví dụ phổ biến để đưa outbox row vào Kafka. Nếu đích cuối là JMS, cần connector/bridge hoặc relay tương thích với hạ tầng JMS; không giả định mọi CDC connector đều xuất trực tiếp sang JMS.

Dù dùng polling hay CDC, consumer vẫn nên xử lý duplicate. CDC connector có thể restart hoặc phát lại record theo offset/recovery semantics.

## 12. @TransactionalEventListener không thay thế outbox bền vững

Spring có @TransactionalEventListener với phase AFTER_COMMIT để xử lý application event sau khi transaction commit.

Cách này hữu ích cho side effect nội bộ khi chấp nhận giới hạn về độ bền. Nhưng nếu process dừng sau database commit và trước khi listener callback gửi JMS, event trong bộ nhớ có thể mất. Không có bản ghi outbox để phục hồi.

Nếu yêu cầu event phải được phát sau khi database commit kể cả khi ứng dụng restart, hãy ghi outbox row trong transaction nguồn. Có thể dùng application event để đánh thức relay sớm hơn, nhưng outbox vẫn là nguồn dữ liệu bền vững để relay quét lại.

## 13. Ví dụ Java 17 chạy được: Spring JDBC, JMS, H2 và ActiveMQ

Ví dụ này minh họa đầy đủ hai phía trong một JVM:

1. OrderService ghi order và outbox row trong cùng H2 transaction.
2. OutboxRelay định kỳ gửi event từ outbox tới ActiveMQ Queue.
3. ConsumerListener nhận JMS Message trong transacted listener session.
4. ConsumerService ghi inbox và projection trong cùng database transaction.
5. Chương trình gửi lại cùng event_id một lần để chứng minh duplicate bị bỏ qua.

Để ví dụ chạy độc lập, producer và consumer dùng chung một H2 database trong JVM. Trong production, mỗi service thường sở hữu database riêng: producer sở hữu order/outbox; consumer sở hữu inbox và projection.

### 13.1. Cấu hình Maven

Tạo file pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transactional-outbox-jms-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jms</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-broker</artifactId>
            <version>6.1.6</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>activemq-client</artifactId>
            <version>6.1.6</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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

### 13.2. Spring configuration và schema

Tạo file src/main/java/demo/OutboxConfiguration.java:

~~~java
package demo;

import javax.sql.DataSource;

import jakarta.jms.ConnectionFactory;

import org.apache.activemq.ActiveMQConnectionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableJms
@EnableScheduling
@EnableTransactionManagement
public class OutboxConfiguration {

    @Bean
    public DataSource dataSource() {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:outboxdemo;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");
        dataSource.setPassword("");
        return dataSource;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public InitializingBean databaseSchema(JdbcTemplate jdbc) {
        return () -> {
            jdbc.execute("""
                    CREATE TABLE orders (
                        order_id VARCHAR(64) PRIMARY KEY,
                        status VARCHAR(32) NOT NULL
                    )
                    """);

            jdbc.execute("""
                    CREATE TABLE outbox (
                        event_id VARCHAR(64) PRIMARY KEY,
                        aggregate_id VARCHAR(64) NOT NULL,
                        event_type VARCHAR(128) NOT NULL,
                        destination VARCHAR(255) NOT NULL,
                        payload VARCHAR(4000) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        published_at TIMESTAMP NULL,
                        last_error VARCHAR(1000) NULL
                    )
                    """);

            jdbc.execute("""
                    CREATE INDEX idx_outbox_pending
                    ON outbox(status, created_at)
                    """);

            jdbc.execute("""
                    CREATE TABLE inbox (
                        event_id VARCHAR(64) PRIMARY KEY,
                        processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """);

            jdbc.execute("""
                    CREATE TABLE order_projection (
                        order_id VARCHAR(64) PRIMARY KEY,
                        status VARCHAR(32) NOT NULL
                    )
                    """);
        };
    }

    @Bean
    public ConnectionFactory connectionFactory() {
        return new ActiveMQConnectionFactory(
                "vm://outbox-demo?create=false"
        );
    }

    @Bean
    public JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDeliveryPersistent(true);
        return template;
    }

    @Bean
    public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        return factory;
    }

    @Bean
    @DependsOn("databaseSchema")
    public OrderService orderService(JdbcTemplate jdbc) {
        return new OrderService(jdbc);
    }

    @Bean
    @DependsOn("databaseSchema")
    public OutboxRelay outboxRelay(
            JdbcTemplate jdbc,
            JmsTemplate jmsTemplate) {
        return new OutboxRelay(jdbc, jmsTemplate);
    }

    @Bean
    @DependsOn("databaseSchema")
    public ConsumerService consumerService(JdbcTemplate jdbc) {
        return new ConsumerService(jdbc);
    }

    @Bean
    @DependsOn("databaseSchema")
    public ConsumerListener consumerListener(
            ConsumerService consumerService) {
        return new ConsumerListener(consumerService);
    }
}
~~~

### 13.3. OrderService ghi order và outbox nguyên tử

Tạo file src/main/java/demo/OrderService.java:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

public class OrderService {

    private final JdbcTemplate jdbc;

    public OrderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(String orderId, String eventId) {
        jdbc.update(
                "INSERT INTO orders(order_id, status) VALUES (?, ?)",
                orderId,
                "CREATED"
        );

        jdbc.update("""
                INSERT INTO outbox(
                    event_id,
                    aggregate_id,
                    event_type,
                    destination,
                    payload,
                    status,
                    attempts
                )
                VALUES (?, ?, ?, ?, ?, 'NEW', 0)
                """,
                eventId,
                orderId,
                "order.created",
                "orders.events",
                orderId
        );
    }
}
~~~

OrderService là một Spring bean được gọi qua proxy từ main. Vì hai câu INSERT chạy trong cùng transaction manager và DataSource, nếu insert outbox thất bại thì insert order cũng rollback.

### 13.4. OutboxRelay gửi event sau commit

Tạo file src/main/java/demo/OutboxRelay.java:

~~~java
package demo;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.scheduling.annotation.Scheduled;

public class OutboxRelay {

    private final JdbcTemplate jdbc;
    private final JmsTemplate jmsTemplate;

    public OutboxRelay(
            JdbcTemplate jdbc,
            JmsTemplate jmsTemplate) {
        this.jdbc = jdbc;
        this.jmsTemplate = jmsTemplate;
    }

    @Scheduled(fixedDelay = 200)
    public void publishPending() {
        List<OutboxEvent> events = jdbc.query("""
                SELECT event_id, destination, event_type, payload
                FROM outbox
                WHERE status = 'NEW'
                ORDER BY created_at, event_id
                FETCH FIRST 10 ROWS ONLY
                """,
                (rs, rowNum) -> new OutboxEvent(
                        rs.getString("event_id"),
                        rs.getString("destination"),
                        rs.getString("event_type"),
                        rs.getString("payload")
                )
        );

        for (OutboxEvent event : events) {
            try {
                jmsTemplate.convertAndSend(
                        event.destination(),
                        event.payload(),
                        message -> {
                            message.setStringProperty(
                                    "eventId", event.eventId()
                            );
                            message.setStringProperty(
                                    "eventType", event.eventType()
                            );
                            return message;
                        }
                );

                jdbc.update("""
                        UPDATE outbox
                        SET status = 'PUBLISHED',
                            published_at = CURRENT_TIMESTAMP,
                            attempts = attempts + 1,
                            last_error = NULL
                        WHERE event_id = ?
                          AND status = 'NEW'
                        """,
                        event.eventId()
                );
            }
            catch (RuntimeException ex) {
                String error = ex.getClass().getSimpleName()
                        + ": " + ex.getMessage();

                if (error.length() > 900) {
                    error = error.substring(0, 900);
                }

                jdbc.update("""
                        UPDATE outbox
                        SET attempts = attempts + 1,
                            last_error = ?
                        WHERE event_id = ?
                          AND status = 'NEW'
                        """,
                        error,
                        event.eventId()
                );
            }
        }
    }

    private record OutboxEvent(
            String eventId,
            String destination,
            String eventType,
            String payload) {
    }
}
~~~

Relay chỉ có một instance trong ví dụ. Nó query batch nhỏ, gửi Message có eventId và eventType properties, sau đó đánh dấu PUBLISHED. Nếu send thất bại, row vẫn NEW và được thử lại ở chu kỳ sau.

Trong production có nhiều relay instance, cần claim/lease row an toàn trước khi gửi. Ví dụ này không triển khai distributed claim để giữ phần minh họa ngắn và chạy với một relay.

### 13.5. ConsumerService dùng inbox cùng transaction với side effect

Tạo file src/main/java/demo/ConsumerService.java:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

public class ConsumerService {

    private final JdbcTemplate jdbc;

    public ConsumerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean process(String eventId, String orderId) {
        Integer existing = jdbc.queryForObject(
                "SELECT COUNT(*) FROM inbox WHERE event_id = ?",
                Integer.class,
                eventId
        );

        if (existing != null && existing > 0) {
            return false;
        }

        jdbc.update(
                "INSERT INTO inbox(event_id) VALUES (?)",
                eventId
        );

        jdbc.update("""
                INSERT INTO order_projection(order_id, status)
                VALUES (?, ?)
                """,
                orderId,
                "PROJECTED"
        );

        return true;
    }
}
~~~

Đây là ví dụ tuần tự với một listener consumer. Trong production, giữ primary key trên inbox.event_id và dùng insert nguyên tử theo dialect database để xử lý race giữa nhiều consumer.

### 13.6. JMS listener nhận event và phân biệt duplicate

Tạo file src/main/java/demo/ConsumerListener.java:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.TextMessage;

import org.springframework.jms.annotation.JmsListener;

public class ConsumerListener {

    private final ConsumerService consumerService;
    private final CountDownLatch firstProcessed = new CountDownLatch(1);
    private final CountDownLatch duplicateSkipped = new CountDownLatch(1);

    public ConsumerListener(ConsumerService consumerService) {
        this.consumerService = consumerService;
    }

    @JmsListener(
            destination = "orders.events",
            containerFactory = "jmsListenerContainerFactory"
    )
    public void receive(Message message) throws JMSException {
        if (!(message instanceof TextMessage textMessage)) {
            throw new IllegalArgumentException(
                    "Expected a TextMessage"
            );
        }

        String eventId = message.getStringProperty("eventId");
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing eventId property"
            );
        }

        boolean firstDelivery = consumerService.process(
                eventId,
                textMessage.getText()
        );

        if (firstDelivery) {
            firstProcessed.countDown();
        }
        else {
            duplicateSkipped.countDown();
        }
    }

    public boolean awaitFirst(long timeout, TimeUnit unit)
            throws InterruptedException {
        return firstProcessed.await(timeout, unit);
    }

    public boolean awaitDuplicate(long timeout, TimeUnit unit)
            throws InterruptedException {
        return duplicateSkipped.await(timeout, unit);
    }
}
~~~

ConsumerService là một bean khác, nên lời gọi process đi qua transaction proxy. Database transaction commit trước khi process trả về cho listener. Listener container dùng sessionTransacted=true; nếu xử lý ném exception, JMS transaction có thể rollback để broker redeliver.

### 13.7. Chạy broker, tạo order và phát lại duplicate

Tạo file src/main/java/demo/TransactionalOutboxDemo.java:

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.apache.activemq.broker.BrokerService;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.core.JmsTemplate;

public class TransactionalOutboxDemo {

    public static void main(String[] args) throws Exception {
        BrokerService broker = new BrokerService();
        broker.setBrokerName("outbox-demo");
        broker.setPersistent(false);
        broker.setUseJmx(false);

        broker.start();
        broker.waitUntilStarted();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             OutboxConfiguration.class
                     )) {

            OrderService orderService =
                    context.getBean(OrderService.class);
            ConsumerListener listener =
                    context.getBean(ConsumerListener.class);
            JmsTemplate jmsTemplate =
                    context.getBean(JmsTemplate.class);
            JdbcTemplate jdbc =
                    context.getBean(JdbcTemplate.class);

            String orderId = "ORD-183";
            String eventId = "evt-183-001";

            orderService.createOrder(orderId, eventId);

            if (!listener.awaitFirst(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Outbox event was not consumed"
                );
            }

            if (!awaitPublished(jdbc, eventId, 10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Outbox row was not marked PUBLISHED"
                );
            }

            // Mô phỏng broker redelivery hoặc relay gửi lại cùng event.
            jmsTemplate.convertAndSend(
                    "orders.events",
                    orderId,
                    message -> {
                        message.setStringProperty("eventId", eventId);
                        message.setStringProperty(
                                "eventType", "order.created"
                        );
                        return message;
                    }
            );

            if (!listener.awaitDuplicate(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Duplicate was not detected"
                );
            }

            Integer publishedRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox "
                            + "WHERE event_id = ? AND status = 'PUBLISHED'",
                    Integer.class,
                    eventId
            );

            Integer inboxRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM inbox WHERE event_id = ?",
                    Integer.class,
                    eventId
            );

            Integer projectionRows = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM order_projection WHERE order_id = ?",
                    Integer.class,
                    orderId
            );

            System.out.println("outbox.publishedRows=" + publishedRows);
            System.out.println("consumer.inboxRows=" + inboxRows);
            System.out.println("consumer.projectionRows=" + projectionRows);
            System.out.println("consumer.duplicateSkipped=1");
        }
        finally {
            broker.stop();
            broker.waitUntilStopped();
        }
    }

    private static boolean awaitPublished(
            JdbcTemplate jdbc,
            String eventId,
            long timeout,
            TimeUnit unit) throws InterruptedException {

        long deadline = System.nanoTime() + unit.toNanos(timeout);

        while (System.nanoTime() < deadline) {
            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox "
                            + "WHERE event_id = ? AND status = 'PUBLISHED'",
                    Integer.class,
                    eventId
            );

            if (count != null && count > 0) {
                return true;
            }

            Thread.sleep(25);
        }

        return false;
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.TransactionalOutboxDemo
~~~

Stdout của chương trình:

~~~text
outbox.publishedRows=1
consumer.inboxRows=1
consumer.projectionRows=1
consumer.duplicateSkipped=1
~~~

### 13.8. Phân tích kết quả

OrderService ghi order ORD-183 và outbox event evt-183-001 trong cùng database transaction. Nếu một trong hai câu INSERT thất bại, transaction rollback và không có order được commit riêng lẻ.

OutboxRelay chạy định kỳ, đọc event NEW và gửi TextMessage tới Queue orders.events. eventId được gắn thành JMS property để consumer dùng làm khóa deduplication. Sau khi send trả về thành công, relay đánh dấu outbox row PUBLISHED.

ConsumerListener nhận Message. ConsumerService kiểm tra inbox, ghi event_id và cập nhật order_projection trong cùng transaction. Lần đầu, cả inbox row và projection row được commit.

Chương trình sau đó gửi lại cùng event_id để mô phỏng duplicate. ConsumerService tìm thấy inbox row và trả về false, vì vậy projection không được insert lần thứ hai. Kết quả cho thấy có một inbox row, một projection row và một duplicate đã bị bỏ qua.

Ví dụ dùng một relay instance, một consumer và broker không persistent để tập trung vào transaction/outbox/idempotency. Nó không chứng minh khả năng HA hoặc durability của broker. Trong production, dùng broker được cấu hình persistent, relay claim an toàn và consumer idempotent.

## 14. Vận hành và quan sát

Transactional outbox cần metric và quy trình vận hành, không chỉ cần bảng database.

Nên theo dõi:

- Số lượng event NEW hoặc IN_PROGRESS.
- Tuổi của event NEW lâu nhất.
- Số lần gửi thất bại theo destination.
- Thời gian từ created_at đến published_at.
- Số event chuyển sang FAILED/quarantine.
- Tỷ lệ duplicate mà consumer bỏ qua.
- Số JMS redelivery và dead-letter.
- Độ trễ xử lý từ lúc event được tạo tới lúc side effect hoàn tất.

Nếu outbox backlog tăng liên tục, relay hoặc broker không theo kịp tốc độ ghi event. Cần xem batch size, số relay worker, giới hạn broker, network, payload size và tốc độ consumer.

Có thể partition hoặc archive outbox đã PUBLISHED theo thời gian. Không xóa event đang NEW/IN_PROGRESS. Inbox cũng cần retention; chỉ xóa record sau khi thời gian replay tối đa của hệ thống đã qua và bảo đảm không còn nguồn có thể phát lại event cũ.

Nếu xóa inbox quá sớm, một event cũ được replay có thể chạy side effect lần nữa. Retention của inbox phải dài hơn khoảng thời gian broker, backup, operator hoặc CDC có thể phát lại event.

## 15. Lỗi thường gặp

1. **Ghi order rồi gửi JMS ngay trong cùng method và nghĩ @Transactional bao phủ cả hai:** DataSourceTransactionManager không tự quản lý JMS resource.
2. **Ghi outbox sau khi commit bằng callback trong bộ nhớ:** process crash có thể làm mất event trước khi ghi outbox.
3. **Đánh dấu PUBLISHED trước khi gửi:** crash giữa hai thao tác có thể làm mất event.
4. **Tạo event_id mới khi retry:** consumer không nhận diện được duplicate.
5. **Giả định relay chỉ gửi đúng một lần:** crash sau send trước mark có thể tạo duplicate.
6. **Không có unique constraint trên inbox.event_id:** nhiều consumer có thể xử lý cùng event đồng thời.
7. **Ghi inbox và side effect ở hai transaction khác nhau:** có thể đánh dấu đã xử lý dù side effect rollback, hoặc ngược lại.
8. **Nuốt exception trong JMS listener:** container có thể commit acknowledgement dù nghiệp vụ chưa thành công.
9. **Dùng AUTO_ACKNOWLEDGE khi cần redelivery đáng tin cậy:** cấu hình listener transaction phù hợp, ví dụ sessionTransacted=true.
10. **Cho rằng JMS local transaction tự bao gồm database:** hai local resource transaction độc lập trừ khi dùng XA/JTA.
11. **Không kiểm soát relay concurrency:** nhiều relay có thể gửi cùng một row; cần claim/lease hoặc CDC.
12. **Giữ database lock khi gọi broker:** network chậm có thể giữ transaction và lock quá lâu.
13. **Không quản lý ordering:** nhiều worker có thể phát hoặc xử lý event cùng aggregate sai thứ tự.
14. **Retry vô hạn poison event:** cần giới hạn, quarantine và dead-letter policy.
15. **Xóa inbox quá sớm:** replay cũ có thể tạo side effect trùng.
16. **Dùng inbox để chống mọi side effect ngoài database:** email hoặc HTTP cần idempotency key hoặc workflow riêng.
17. **Dùng @TransactionalEventListener(AFTER_COMMIT) như outbox bền vững:** callback trong process không lưu event để phục hồi sau crash.
18. **Hứa exactly-once chỉ vì dùng persistent JMS message:** broker persistence không làm database và JMS commit thành một giao dịch nguyên tử.

## 16. Checklist thiết kế

Trước khi đưa outbox vào production, xác nhận:

- Order/aggregate và outbox row dùng cùng database transaction.
- event_id ổn định, duy nhất và được gửi trong Message.
- Payload là snapshot có schema version rõ ràng.
- Relay chỉ đánh dấu PUBLISHED sau khi send được chấp nhận.
- Retry có backoff, giới hạn và lưu last_error.
- Nhiều relay instance dùng claim/lease hoặc cơ chế CDC phù hợp.
- Ordering được định nghĩa theo aggregate nếu nghiệp vụ cần.
- Consumer có unique inbox event_id.
- Inbox và side effect database cùng transaction.
- JMS listener transaction rollback khi xử lý thất bại.
- Duplicate được acknowledge sau khi xác nhận đã xử lý trước đó.
- Side effect ngoài database có idempotency key hoặc workflow riêng.
- Outbox/inbox có retention, archive và replay policy.
- Có dashboard cho backlog, oldest event age, failure, redelivery và duplicate.

## 17. Câu hỏi tự kiểm tra

1. Dual-write xảy ra khi một nghiệp vụ vừa commit database vừa gửi JMS như thế nào?
2. Vì sao outbox row phải được ghi cùng transaction với aggregate?
3. Relay nên đánh dấu PUBLISHED trước hay sau khi gửi JMS?
4. Crash sau khi broker nhận Message nhưng trước khi mark tạo ra điều gì?
5. Vì sao transactional outbox thường là at-least-once?
6. event_id phải có đặc tính gì để consumer nhận diện duplicate?
7. Inbox record và side effect phải nằm trong cùng transaction vì sao?
8. Unique constraint giúp giải quyết race giữa nhiều consumer như thế nào?
9. sessionTransacted=true tác động tới JMS acknowledgement/rollback ra sao?
10. Vì sao JMS local transaction và database transaction vẫn có cửa sổ duplicate?
11. Khi nào cần XA/JTA thay cho outbox?
12. Vì sao @TransactionalEventListener(AFTER_COMMIT) không tương đương outbox bền vững?
13. Làm thế nào để nhiều relay instance không claim cùng một event?
14. Cần làm gì để giữ ordering theo aggregate?
15. Vì sao inbox retention phải dài hơn cửa sổ replay?
16. Khi side effect là gọi HTTP, làm sao chống thực hiện trùng?

## 18. Kết luận

Transactional outbox phối hợp thay đổi database và event publication bằng cách ghi aggregate cùng event vào một local transaction. Relay gửi event đã commit tới JMS và đánh dấu trạng thái sau khi broker chấp nhận. Cách này tránh mất event do crash giữa database commit và lần gửi JMS đầu tiên.

Relay vẫn có thể gửi duplicate nếu crash sau khi broker nhận Message nhưng trước khi đánh dấu PUBLISHED. Vì vậy, consumer cần inbox/deduplication record với event_id duy nhất và ghi record đó cùng side effect trong một database transaction. JMS local transaction giúp rollback acknowledgement khi listener lỗi, nhưng không tự biến JMS và database thành một transaction nguyên tử.

Thiết kế production cần thêm claim/lease hoặc CDC, retry/backoff, dead-letter, ordering, idempotency cho side effect ngoài database, retention và metric. Mục tiêu là không mất event đã commit và bảo đảm việc giao lại không làm nghiệp vụ bị thực hiện lặp.

## Tài liệu tham khảo chính thức

- Spring Framework — Receiving a Message, Processing Messages Within Transactions: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Framework — Using @Transactional: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — JDBC Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- AWS Prescriptive Guidance — Transactional outbox pattern: https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html
- Debezium — Outbox Event Router: https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- Jakarta Messaging specification: https://jakarta.ee/specifications/messaging/
- Apache ActiveMQ Classic: https://activemq.apache.org/components/classic/
