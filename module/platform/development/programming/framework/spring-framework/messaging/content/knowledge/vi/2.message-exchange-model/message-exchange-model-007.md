# Liên kết về thời gian, địa chỉ và cấu trúc dữ liệu trong Spring Messaging

Một thông điệp trong ứng dụng Spring thường mang nhiều thông tin hơn phần dữ liệu nghiệp vụ. Khi một service gửi thông điệp cho thành phần khác, hệ thống cần biết **thông điệp được tạo khi nào, được chuyển đến đâu, và payload có cấu trúc hoặc cách biểu diễn nào**. Spring Messaging tách các mối quan tâm này thành payload và headers để các thành phần có thể phối hợp mà không phải nhồi toàn bộ metadata vào dữ liệu nghiệp vụ.

Ba khía cạnh thời gian, địa chỉ và cấu trúc dữ liệu liên hệ với nhau nhưng có ý nghĩa riêng:

- **Thời gian** giúp xác định thời điểm tạo, phát sinh hoặc tiếp nhận một thông điệp.
- **Địa chỉ** xác định kênh, endpoint, queue, topic hoặc đích xử lý.
- **Cấu trúc dữ liệu** mô tả payload gồm những trường nào và cần được chuyển đổi/diễn giải ra sao.

Hiểu rõ sự phân tách này giúp thiết kế message contract ổn định, định tuyến đúng và xử lý được thông điệp khi đi qua nhiều thành phần hoặc nhiều hệ thống.

## 1. Mô hình Message: payload và headers

Trong Spring Messaging, một thông điệp được biểu diễn bởi interface **Message<T>**:

- **Payload** là dữ liệu chính mà consumer cần xử lý. Kiểu T có thể là một Java object, record, chuỗi, byte array hoặc kiểu dữ liệu khác.
- **Headers** là tập metadata dạng key/value đi kèm payload. Header có thể mô tả định danh, thời gian, content type, kênh phản hồi, kênh lỗi hoặc metadata do ứng dụng định nghĩa.

Có thể hình dung:

~~~text
Message<T>
    |
    +-- payload: T
    |      Dữ liệu nghiệp vụ cần truyền
    |
    +-- headers: MessageHeaders
           id, timestamp, contentType, ...
           metadata phục vụ định tuyến và xử lý
~~~

Ví dụ, một thông điệp thông báo đơn hàng được tạo có thể chứa:

- Payload: mã đơn hàng, tổng tiền, thời điểm nghiệp vụ phát sinh.
- Headers: message ID, thời điểm Spring tạo message, content type, nhãn đích logic, correlation ID và phiên bản schema.

Payload và headers cùng đi theo một message, nhưng không nên thay thế vai trò của nhau. Mã đơn hàng và tổng tiền là dữ liệu nghiệp vụ nên thuộc payload. ID kỹ thuật, thông tin định tuyến hoặc content type thường thuộc headers.

### MessageHeaders và MessageBuilder

**MessageHeaders** là cấu trúc headers mà consumer đọc được. Các header phổ biến của Spring Messaging gồm:

| Header | Ý nghĩa |
|---|---|
| **id** | Định danh của message do Spring tạo nếu chưa được cung cấp. |
| **timestamp** | Thời điểm tạo message theo đồng hồ hệ thống, tính bằng milliseconds kể từ Unix epoch. |
| **contentType** | MIME type mô tả cách diễn giải payload, ví dụ **application/json**. |
| **replyChannel** | Thông tin kênh phản hồi trong những luồng request/reply có sử dụng nó. |
| **errorChannel** | Thông tin kênh xử lý lỗi trong những luồng có hỗ trợ cơ chế này. |

**MessageBuilder** là cách thuận tiện để tạo message và gắn headers:

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order created")
        .setHeader("app.destination", "orders.created")
        .build();
~~~

Khi build, Spring tạo **Message** với payload và headers. ID và timestamp thường được tạo tự động nếu chưa có giá trị tương ứng và cơ chế tạo mặc định vẫn được bật.

**MessageHeaders** được thiết kế theo hướng bất biến sau khi message được tạo. Nếu cần thay đổi metadata, hãy tạo message mới bằng **MessageBuilder** hoặc dùng **MessageHeaderAccessor** trong những luồng cần kiểm soát trạng thái mutable. Không nên coi headers của message đã phát đi như một map tùy ý có thể sửa ở bất kỳ nơi nào.

## 2. Liên kết về thời gian

Thời gian xuất hiện ở nhiều giai đoạn khác nhau của vòng đời thông điệp. Nếu gộp chúng thành một trường duy nhất, consumer có thể hiểu sai thời điểm nghiệp vụ hoặc đo sai độ trễ.

### Phân biệt thời điểm tạo message và thời điểm nghiệp vụ

Spring Messaging cung cấp header **timestamp**. Đây là thời điểm message được tạo trong ứng dụng theo đồng hồ hệ thống. Nó hữu ích để quan sát vòng đời message, nhưng không nhất thiết là lúc sự kiện nghiệp vụ thực sự xảy ra.

Ví dụ, một đơn hàng có thể được tạo lúc 09:00, nhưng service chỉ phát message lúc 09:00:03 sau khi ghi dữ liệu và hoàn thành một số bước xử lý. Khi đó:

- **timestamp** của message phản ánh thời điểm message được tạo.
- **occurredAt** trong payload phản ánh thời điểm nghiệp vụ tạo đơn hàng.
- **receivedAt** nếu ứng dụng tự ghi nhận phản ánh thời điểm consumer hoặc adapter nhận message.

Ba mốc này trả lời ba câu hỏi khác nhau. Nếu cần phân tích độ trễ, hãy xác định rõ đang đo khoảng thời gian nào, ví dụ từ lúc sự kiện xảy ra đến lúc consumer nhận được.

### ID và timestamp không phải khóa nghiệp vụ

**id** giúp phân biệt một message instance. Nó không mặc nhiên là mã đơn hàng, mã giao dịch hoặc khóa idempotency của nghiệp vụ. Khi một message được tạo lại từ cùng một sự kiện, ID message có thể khác.

Tương tự, timestamp không bảo đảm thứ tự xử lý trên toàn hệ thống. Hai service có thể lệch đồng hồ; message broker có thể phân phối lại; consumer có thể xử lý song song. Nếu cần bảo đảm thứ tự, hãy thiết kế theo partition key, sequence/version nghiệp vụ hoặc cơ chế ordering của broker và consumer.

Một số nguyên tắc hữu ích:

- Dùng **Instant** hoặc định dạng thời gian có múi giờ rõ ràng cho thời điểm nghiệp vụ.
- Dùng message ID để truy vết một lần phát message.
- Dùng business event ID hoặc idempotency key để nhận diện cùng một thao tác nghiệp vụ khi retry.
- Không suy luận thứ tự tuyệt đối chỉ từ timestamp.
- Khi tính latency giữa nhiều máy, cần quan tâm đồng bộ đồng hồ và xác định điểm bắt đầu/kết thúc của phép đo.

### Ví dụ biểu diễn thời gian

~~~java
public record OrderCreated(
        String orderId,
        Instant occurredAt
) {
}
~~~

**occurredAt** thuộc payload vì đây là một phần ý nghĩa của sự kiện OrderCreated. Header **timestamp** thuộc metadata của message vì nó mô tả thời điểm message được tạo trong luồng messaging.

## 3. Liên kết về địa chỉ và định tuyến

Địa chỉ trả lời câu hỏi: **message sẽ đi đến thành phần hoặc hệ thống nào?** Trong Spring, không có một trường **destination** duy nhất áp dụng giống nhau cho mọi loại messaging. Địa chỉ phụ thuộc vào tầng mà ứng dụng đang sử dụng.

### MessageChannel trong Spring Messaging

Ở mức Spring Messaging, **MessageChannel** là abstraction đại diện cho nơi message được gửi đến. Producer gọi **send(message)** trên channel; channel và các thành phần kết nối với nó quyết định message được chuyển tiếp như thế nào.

~~~text
Producer
   |
   | send(message)
   v
MessageChannel
   |
   v
Consumer / MessageHandler
~~~

Tên channel trong cấu hình ứng dụng là địa chỉ nội bộ của luồng xử lý. Nó không tự động trở thành tên queue hoặc topic trên broker. Adapter hoặc binder cụ thể mới chịu trách nhiệm ánh xạ luồng trong ứng dụng sang hạ tầng bên ngoài.

### Địa chỉ ở các tầng khác nhau

| Tầng | Địa chỉ hoặc định danh thường gặp | Vai trò |
|---|---|---|
| Spring Messaging | **MessageChannel** | Kênh gửi message trong ứng dụng. |
| Spring Integration | Channel, router, gateway, adapter | Nối các bước xử lý và định tuyến message giữa endpoint. |
| JMS / AMQP | Queue, exchange, routing key, destination | Định tuyến qua broker theo giao thức tương ứng. |
| Apache Kafka | Topic, partition, key | Xác định luồng lưu trữ và phân vùng record. |
| WebSocket / STOMP | Destination như **/topic/orders** hoặc **/app/orders** | Định tuyến frame/message theo quy ước STOMP và cấu hình broker. |

Các tên gọi này không thể hoán đổi tùy ý. Một **MessageChannel** trong ứng dụng có thể được nối với adapter Kafka, nhưng bản thân channel không phải Kafka topic.

### Header định tuyến và destination

Một số luồng sử dụng headers để mang thông tin định tuyến, ví dụ **replyChannel**, **errorChannel** hoặc header riêng do ứng dụng định nghĩa. Các adapter và framework tích hợp có thể đọc metadata này để quyết định bước tiếp theo.

Tuy nhiên, không nên mặc định header tùy ý tên **destination** sẽ được mọi Spring component hiểu. Nếu ứng dụng cần một nhãn đích logic riêng, hãy định nghĩa quy ước rõ ràng, chẳng hạn **app.destination**, và viết router hoặc adapter đọc đúng header đó.

Nên giữ địa chỉ hạ tầng trong cấu hình hoặc lớp adapter khi có thể. Điều này giúp logic nghiệp vụ không bị phụ thuộc trực tiếp vào tên queue, topic hoặc endpoint của từng môi trường.

## 4. Liên kết về cấu trúc dữ liệu

Cấu trúc dữ liệu mô tả payload được tổ chức thế nào và consumer cần diễn giải nó ra sao. Spring Messaging cho phép payload có kiểu Java cụ thể, nhưng khi message đi qua ranh giới mạng, kiểu Java không tự động trở thành một schema dùng chung cho mọi hệ thống.

### Payload là dữ liệu, contentType là metadata

Payload có thể là:

- Java object hoặc record, phù hợp khi các thành phần cùng chia sẻ kiểu dữ liệu.
- **String**, phù hợp với văn bản hoặc dữ liệu đã được serialize.
- **byte[]**, phù hợp khi ứng dụng làm việc trực tiếp với dữ liệu nhị phân.
- Một kiểu dữ liệu chuyên biệt do thư viện hoặc adapter cung cấp.

Header **contentType** mô tả định dạng của payload, ví dụ:

- **application/json**: JSON.
- **application/xml**: XML.
- **text/plain**: văn bản thuần.
- **application/octet-stream**: dữ liệu nhị phân không gắn một định dạng cụ thể.

Content type hỗ trợ message converter lựa chọn cách chuyển đổi phù hợp. Nó không tự định nghĩa đầy đủ schema nghiệp vụ. Hai payload cùng là JSON vẫn có thể có cấu trúc khác nhau.

### Schema và phiên bản dữ liệu

Khi nhiều service trao đổi message, cần thống nhất contract: tên trường, kiểu dữ liệu, trường bắt buộc, ý nghĩa giá trị và quy tắc tương thích phiên bản.

Có thể đưa schema version vào header hoặc trong envelope của payload. Dù chọn cách nào, producer và consumer cần thống nhất vị trí và cách diễn giải. Ví dụ:

~~~text
payload:
  orderId: "ORD-1001"
  total: 125.50
  occurredAt: "2026-11-07T03:00:00Z"

headers:
  contentType: application/json
  app.schemaVersion: 1
~~~

Một số nguyên tắc thiết kế:

1. Dùng DTO hoặc record làm contract trao đổi, tránh gửi trực tiếp entity gắn chặt với persistence.
2. Dùng kiểu dữ liệu rõ ràng cho tiền, thời gian và định danh; tránh biến mọi giá trị thành chuỗi không có quy ước.
3. Quy định cách xử lý trường thiếu, trường mới và giá trị không hợp lệ.
4. Thay đổi schema theo hướng tương thích khi có thể; kiểm thử cả producer lẫn consumer.
5. Chỉ serialize dữ liệu cần thiết cho consumer; tránh đưa toàn bộ object graph hoặc thông tin nội bộ không cần thiết vào payload.
6. Không xem header content type là sự thay thế cho schema registry hoặc tài liệu contract.

### MessageConverter và chuyển đổi payload

Trong các luồng Spring hỗ trợ conversion, message converter chuyển payload từ một dạng biểu diễn sang dạng khác. Ví dụ, object Java có thể được chuyển thành JSON khi gửi đi và JSON được chuyển thành DTO khi nhận vào, tùy cấu hình converter và content type.

Khi conversion thất bại, hãy kiểm tra:

- Content type có đúng với bytes thực tế không?
- Producer và consumer có thống nhất schema không?
- Kiểu Java đích có thể nhận các trường và kiểu dữ liệu hiện tại không?
- Converter có được cấu hình và đăng ký trong đúng luồng không?

Không nên dựa vào tên lớp Java ở một service để giả định service khác có thể deserialize chính xác cùng object. Ranh giới giữa các tiến trình cần một định dạng trao đổi và contract được thống nhất.

## 5. Ví dụ hoàn chỉnh: tạo message có thời gian, địa chỉ logic và schema

Ví dụ sau dùng Spring Messaging trực tiếp, không cần khởi tạo Spring Boot application context. Message mang một payload có kiểu **OrderCreated**; headers chứa content type, địa chỉ logic, schema version và correlation ID. Spring tạo ID và timestamp của message.

### Cấu hình Maven

Tạo file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>message-metadata-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.1.8</version>
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
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### Mã Java

Tạo file **src/main/java/com/example/messaging/MessageMetadataExample.java**:

~~~java
package com.example.messaging;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

public class MessageMetadataExample {

    public record OrderCreated(
            String orderId,
            BigDecimal total,
            Instant occurredAt
    ) {
    }

    public static void main(String[] args) {
        OrderCreated event = new OrderCreated(
                "ORD-1001",
                new BigDecimal("125.50"),
                Instant.parse("2026-11-07T03:00:00Z")
        );

        Message<OrderCreated> message = MessageBuilder
                .withPayload(event)
                .setHeader(
                        MessageHeaders.CONTENT_TYPE,
                        MimeTypeUtils.APPLICATION_JSON
                )
                .setHeader("app.destination", "orders.created")
                .setHeader("app.schemaVersion", 1)
                .setHeader("app.correlationId", "checkout-2026-001")
                .build();

        System.out.println("orderId=" + message.getPayload().orderId());
        System.out.println("occurredAt=" + message.getPayload().occurredAt());
        System.out.println("contentType="
                + message.getHeaders().get(MessageHeaders.CONTENT_TYPE));
        System.out.println("destination="
                + message.getHeaders().get("app.destination"));
        System.out.println("schemaVersion="
                + message.getHeaders().get("app.schemaVersion"));
        System.out.println("messageIdPresent="
                + (message.getHeaders().get(MessageHeaders.ID) != null));
        System.out.println("timestampPresent="
                + (message.getHeaders().get(MessageHeaders.TIMESTAMP) != null));
    }
}
~~~

Chạy từ thư mục chứa **pom.xml**:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.messaging.MessageMetadataExample
~~~

Output:

~~~text
orderId=ORD-1001
occurredAt=2026-11-07T03:00:00Z
contentType=application/json
destination=orders.created
schemaVersion=1
messageIdPresent=true
timestampPresent=true
~~~

Ví dụ cho thấy ba khía cạnh được đặt ở vị trí phù hợp:

- **occurredAt** thuộc payload vì nó mô tả thời điểm sự kiện nghiệp vụ xảy ra.
- **timestamp** thuộc headers vì nó mô tả thời điểm message được tạo.
- **app.destination** là nhãn đích logic do ứng dụng quy ước. Nó chỉ có ý nghĩa định tuyến khi có channel, router hoặc adapter được cấu hình để đọc nó.
- **contentType** mô tả cách diễn giải payload; **app.schemaVersion** mô tả phiên bản contract mà ứng dụng quy ước.

Mã ví dụ tạo message trong bộ nhớ. Nó chưa gửi message đến queue, topic hoặc network endpoint; để truyền thực tế cần có **MessageChannel**, handler hoặc adapter tương ứng.

## 6. Kết hợp ba khía cạnh trong một luồng messaging

Một luồng trao đổi hoàn chỉnh thường cần đồng thời ba nhóm thông tin:

~~~text
Producer
   |
   | Tạo payload theo schema đã thống nhất
   | Gắn event time / correlation metadata
   v
Message<T>
   |
   | Headers: id, timestamp, contentType, ...
   | Payload: dữ liệu nghiệp vụ
   v
Channel / Router / Adapter
   |
   | Chọn đích: channel, queue, topic hoặc endpoint
   v
Consumer
   |
   | Kiểm tra contract và content type
   | Xử lý idempotency, thời gian và nghiệp vụ
   v
Kết quả / Reply / Error handling
~~~

Ví dụ với sự kiện đơn hàng:

1. Service đơn hàng tạo payload **OrderCreated** với mã đơn hàng, tổng tiền và thời điểm phát sinh.
2. Spring tạo message, gắn ID và timestamp; ứng dụng bổ sung content type, correlation ID và schema version.
3. Producer gửi message đến channel đã chọn.
4. Adapter chuyển message sang queue hoặc topic nếu kiến trúc dùng broker.
5. Consumer nhận message, kiểm tra định dạng và schema, sau đó xử lý nghiệp vụ.
6. Nếu cần phản hồi, luồng request/reply có thể dùng reply channel hoặc cơ chế reply của giao thức. Nếu xử lý lỗi, ứng dụng định nghĩa error handling phù hợp với channel và adapter đang dùng.

Mỗi tầng chịu trách nhiệm một phần. Việc phân tách rõ giúp thay đổi broker hoặc endpoint mà không phải thay đổi cấu trúc dữ liệu nghiệp vụ trong mọi trường hợp.

## 7. Lỗi thiết kế thường gặp

- **Dùng message timestamp làm thời điểm nghiệp vụ:** hai thời điểm có thể khác nhau. Hãy lưu event time rõ ràng trong payload hoặc metadata nghiệp vụ có quy ước.
- **Dùng message ID làm idempotency key:** message retry hoặc phát lại có thể có ID khác. Hãy dùng event ID hoặc business key ổn định để chống xử lý trùng.
- **Cho rằng mọi message đều có header destination:** địa chỉ phụ thuộc channel, adapter và giao thức. Chỉ dùng header định tuyến khi có thành phần thực sự đọc nó.
- **Đưa tên queue/topic trực tiếp vào logic nghiệp vụ:** điều này làm code phụ thuộc môi trường. Hãy cấu hình địa chỉ ở lớp tích hợp hoặc adapter.
- **Nhồi dữ liệu nghiệp vụ vào headers:** headers phù hợp với metadata ngắn, có ý nghĩa điều khiển hoặc mô tả. Payload nên chứa dữ liệu mà consumer cần xử lý.
- **Cho rằng content type đủ mô tả schema:** content type chỉ nói về định dạng tổng quát. Cần version và contract để mô tả cấu trúc cụ thể.
- **Gửi Java entity trực tiếp giữa các hệ thống:** entity có thể chứa quan hệ lazy, trường nội bộ hoặc phụ thuộc persistence. Dùng DTO/event contract có chủ đích.
- **Dùng timestamp để bảo đảm thứ tự:** timestamp không thay thế ordering của broker, sequence number hoặc version nghiệp vụ.
- **Đưa thông tin nhạy cảm vào headers:** headers có thể bị log, copy hoặc chuyển tiếp qua adapter. Chỉ truyền metadata cần thiết và kiểm soát việc ghi log.

## 8. Ghi nhớ

- **Message<T>** gồm payload và headers; payload chứa dữ liệu chính, headers chứa metadata.
- **id** nhận diện message instance; **timestamp** phản ánh thời điểm tạo message theo đồng hồ hệ thống.
- Thời điểm nghiệp vụ như **occurredAt** cần được biểu diễn riêng khi consumer cần biết lúc sự kiện xảy ra.
- Địa chỉ có thể là **MessageChannel**, queue, topic hoặc endpoint; không có một header destination phổ quát cho mọi transport.
- **contentType** mô tả định dạng payload; schema và schema version cần contract riêng.
- Khi thiết kế message, hãy xác định rõ dữ liệu nào thuộc payload, metadata nào thuộc headers, ai chịu trách nhiệm định tuyến và cách các consumer tương thích schema.

Một message tốt giúp consumer hiểu đúng dữ liệu, thời điểm và ngữ cảnh xử lý mà không phụ thuộc quá mức vào chi tiết nội bộ của producer.
