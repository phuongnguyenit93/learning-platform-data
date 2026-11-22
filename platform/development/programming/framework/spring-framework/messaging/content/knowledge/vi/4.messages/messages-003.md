# GenericMessage và cách tạo thông điệp thông thường trong Spring Framework

## 1. GenericMessage nằm ở đâu trong mô hình Messaging?

Spring Messaging chuẩn hóa dữ liệu được trao đổi thành một thông điệp. Thay vì chỉ truyền một object payload, ứng dụng có thể gói payload cùng metadata để các thành phần xử lý thống nhất.

Mô hình cốt lõi gồm ba phần:

- **Message<T>:** interface đại diện cho một thông điệp có payload kiểu T và bộ headers.
- **GenericMessage<T>:** implementation phổ biến của Message<T>, dùng cho payload thông thường.
- **MessageHeaders:** tập hợp metadata dạng key-value gắn với thông điệp.

Một message có thể hình dung như sau:

~~~text
Message<OrderCreated>
├── payload
│   └── OrderCreated(orderId = "ORD-1001")
└── headers
    ├── id
    ├── timestamp
    ├── correlationId = "corr-1001"
    └── source = "checkout"
~~~

Payload mô tả **dữ liệu chính cần xử lý**. Headers mô tả **ngữ cảnh đi kèm** như định danh, thời điểm tạo, correlation ID, content type, reply channel hoặc metadata nghiệp vụ phụ trợ.

Interface Message<T> chỉ có hai phương thức quan trọng:

- getPayload(): trả về payload kiểu T.
- getHeaders(): trả về MessageHeaders; kết quả không null, nhưng có thể không chứa header tùy chỉnh nào.

GenericMessage<T> nằm trong package org.springframework.messaging.support. Đây là một implementation cụ thể để tạo message mà không cần tự viết class triển khai Message.

Cần phân biệt ba khái niệm:

- **Payload:** object nghiệp vụ, ví dụ OrderCreated, String, byte[] hoặc DTO.
- **Message:** wrapper chuẩn hóa payload và headers.
- **Channel/transport:** cơ chế nhận, gửi hoặc vận chuyển Message. GenericMessage tự nó không phải queue, broker, socket hay cơ chế gửi dữ liệu.

## 2. GenericMessage<T> là gì?

GenericMessage<T> triển khai Message<T> và Serializable. Sau khi được tạo, message là immutable: không có API để thay payload hoặc thay cấu trúc headers của chính message đó.

Class cung cấp ba constructor thông dụng:

~~~java
new GenericMessage<>(payload);
new GenericMessage<>(payload, headersMap);
new GenericMessage<>(payload, messageHeaders);
~~~

Trong đó:

1. **GenericMessage(T payload):** tạo message với payload và bộ headers mặc định.
2. **GenericMessage(T payload, Map<String, Object> headers):** tạo message với các header được truyền vào. Nội dung của Map được sao chép khi khởi tạo.
3. **GenericMessage(T payload, MessageHeaders headers):** sử dụng trực tiếp instance MessageHeaders đã truyền vào, không sao chép instance đó.

Payload không được null. Nếu nghiệp vụ cần biểu diễn trạng thái “không có dữ liệu”, hãy thiết kế payload rõ nghĩa như một record/event riêng hoặc một kiểu wrapper phù hợp, thay vì truyền null vào GenericMessage.

### 2.1. Tạo message chỉ với payload

Cách ngắn nhất là truyền object vào constructor:

~~~java
OrderCreated event = new OrderCreated("ORD-1001");

Message<OrderCreated> message = new GenericMessage<>(event);
~~~

Spring tự tạo MessageHeaders. Theo mặc định, headers có ID và timestamp do framework quản lý. Ứng dụng có thể đọc payload và headers thông qua interface Message:

~~~java
OrderCreated body = message.getPayload();

String messageId = message.getHeaders().getId().toString();
Long createdAt = message.getHeaders().getTimestamp();
~~~

ID của message giúp nhận diện một message instance. Nếu cần liên kết nhiều message trong cùng một luồng nghiệp vụ, nên dùng custom header như correlationId hoặc business key. Khi tạo message mới từ message cũ, ID có thể được tạo lại; không dùng ID mặc định như mã giao dịch xuyên suốt nếu nghiệp vụ cần định danh ổn định.

### 2.2. Tạo message với Map headers

Khi cần thêm metadata, truyền một Map<String, Object> vào constructor:

~~~java
Map<String, Object> headers = new HashMap<>();
headers.put("correlationId", "corr-1001");
headers.put("source", "checkout");
headers.put("attempt", 1);

Message<OrderCreated> message =
    new GenericMessage<>(event, headers);
~~~

Header name là String, còn giá trị có thể là Object. Nên thống nhất tên header, kiểu dữ liệu và ý nghĩa của chúng giữa producer và consumer.

Có thể đọc giá trị header theo kiểu mong muốn:

~~~java
String correlationId =
    message.getHeaders().get("correlationId", String.class);

Integer attempt =
    message.getHeaders().get("attempt", Integer.class);
~~~

MessageHeaders hỗ trợ truy cập kiểu bằng get(key, Class<T>). Nếu dùng get(Object) thông thường, kết quả có kiểu Object và ứng dụng phải tự kiểm tra/chuyển kiểu.

**Lưu ý về việc sao chép Map:** GenericMessage(payload, Map) sao chép các cặp key-value vào bộ headers khi tạo message. Vì vậy, việc thay đổi Map gốc sau đó không thay đổi cấu trúc headers của message:

~~~java
Map<String, Object> headers = new HashMap<>();
headers.put("source", "checkout");

Message<String> message = new GenericMessage<>("created", headers);

headers.put("source", "admin");

System.out.println(message.getHeaders().get("source"));
~~~

Kết quả vẫn là checkout. Đây là sao chép cấu trúc Map, không phải deep copy mọi object được lưu làm giá trị. Nếu header chứa một object mutable, object đó vẫn có thể bị thay đổi thông qua tham chiếu khác. Nên ưu tiên giá trị header đơn giản, bất biến và dễ serialize.

### 2.3. Tạo message với MessageHeaders có sẵn

Constructor nhận MessageHeaders dùng trực tiếp instance được truyền vào:

~~~java
MessageHeaders messageHeaders = new MessageHeaders(headers);

Message<String> message =
    new GenericMessage<>("created", messageHeaders);
~~~

Cách này phù hợp khi đã có MessageHeaders được tạo từ một luồng xử lý khác. MessageHeaders là immutable nên dùng chung instance không cho phép consumer sửa trực tiếp cấu trúc header.

Trong ứng dụng thông thường, constructor nhận Map hoặc MessageBuilder thường dễ đọc hơn. Chỉ dùng overload MessageHeaders khi thực sự cần tái sử dụng một bộ headers đã được tạo sẵn và hiểu rõ rằng instance đó không bị sao chép.

## 3. MessageHeaders và các header quan trọng

MessageHeaders triển khai Map<String, Object>, nhưng đây là Map chỉ đọc. Những thao tác thay đổi như put, putAll, remove hoặc clear sẽ ném UnsupportedOperationException.

Không viết cách sau:

~~~java
message.getHeaders().put("correlationId", "corr-2001");
~~~

Muốn thay đổi metadata, hãy tạo một message mới với header mới bằng MessageBuilder hoặc một MessageHeaderAccessor phù hợp.

Một số header chuẩn của Spring:

| Header | Ý nghĩa |
|---|---|
| id | Định danh message instance do Spring quản lý |
| timestamp | Thời điểm tạo message theo cơ chế mặc định |
| contentType | Mô tả kiểu nội dung, thường liên quan tới quá trình convert payload |
| replyChannel | Kênh dùng cho đường phản hồi trong một số mô hình request-reply |
| errorChannel | Kênh dùng cho xử lý lỗi trong một số mô hình messaging |

Có thể dùng các hằng số của MessageHeaders để tránh viết sai tên header, ví dụ MessageHeaders.ID, MessageHeaders.TIMESTAMP và MessageHeaders.CONTENT_TYPE.

Ngoài header chuẩn, ứng dụng có thể thêm header riêng:

- correlationId: liên kết message với một request hoặc luồng nghiệp vụ.
- tenantId: xác định tenant trong hệ thống multi-tenant.
- source: thành phần phát message.
- eventType hoặc schemaVersion: mô tả loại/số phiên bản dữ liệu khi có quy ước rõ ràng.
- traceId: liên kết log và distributed trace nếu hệ thống đã chuẩn hóa cách truyền trace context.

Không nên đưa toàn bộ dữ liệu nghiệp vụ vào headers. Payload là nơi chứa nội dung chính; headers chỉ nên chứa metadata phục vụ định tuyến, theo dõi, chuyển đổi hoặc xử lý xuyên suốt pipeline.

ID và timestamp là các header do Spring quản lý. MessageBuilder không cho phép ghi đè chúng thông qua các thao tác copy header thông thường. Đừng dùng chúng làm chỗ lưu mã đơn hàng hoặc mã correlation của nghiệp vụ.

## 4. Tạo message bằng MessageBuilder

Trong code ứng dụng, MessageBuilder thường là cách linh hoạt và dễ đọc để tạo message. Builder giúp thiết lập payload và headers theo từng bước, sau đó build() trả về một Message.

Ví dụ:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1002"))
    .setHeader("correlationId", "corr-1002")
    .setHeader("source", "order-service")
    .setHeaderIfAbsent("attempt", 1)
    .build();
~~~

MessageBuilder tạo GenericMessage thông thường; nếu payload là Throwable, builder tạo ErrorMessage phù hợp với nội dung lỗi.

Các phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| withPayload(payload) | Bắt đầu builder với payload |
| setHeader(name, value) | Thêm hoặc thay header; giá trị null sẽ loại bỏ header đó |
| setHeaderIfAbsent(name, value) | Chỉ đặt header nếu header chưa có |
| copyHeaders(map) | Sao chép các header từ Map; giá trị custom hiện có có thể bị ghi đè |
| copyHeadersIfAbsent(map) | Chỉ thêm header chưa có |
| removeHeader(name) | Xóa một header |
| removeHeaders(patterns...) | Xóa header theo pattern tên |
| build() | Tạo Message mới từ payload và headers đã cấu hình |

### 4.1. setHeader và setHeaderIfAbsent

Dùng setHeader khi giá trị cần được thiết lập rõ ràng:

~~~java
Message<String> message = MessageBuilder
    .withPayload("payment-completed")
    .setHeader("source", "payment-service")
    .setHeader("attempt", 2)
    .build();
~~~

Dùng setHeaderIfAbsent khi muốn giữ giá trị đã có:

~~~java
Message<String> message = MessageBuilder
    .withPayload("payment-completed")
    .setHeaderIfAbsent("source", "default-service")
    .build();
~~~

Nếu source đã tồn tại trong builder, setHeaderIfAbsent không ghi đè. Nếu giá trị truyền cho setHeader là null, builder loại bỏ header tương ứng.

### 4.2. copyHeaders và copyHeadersIfAbsent

Khi metadata đã nằm trong Map, có thể sao chép nhiều header cùng lúc:

~~~java
Map<String, Object> metadata = Map.of(
    "correlationId", "corr-3001",
    "source", "checkout",
    "tenantId", "tenant-a"
);

Message<String> message = MessageBuilder
    .withPayload("order-created")
    .copyHeaders(metadata)
    .build();
~~~

copyHeaders có thể ghi đè giá trị header custom đã được thiết lập trước đó. copyHeadersIfAbsent chỉ điền các header chưa tồn tại. ID và timestamp là các header read-only theo quy tắc của Spring, không được ghi đè bằng thao tác copy thông thường.

### 4.3. Tạo message mới từ message có sẵn

MessageBuilder.fromMessage(existingMessage) tạo builder mới với payload và headers được lấy từ message ban đầu. Đây là cách phù hợp để bổ sung metadata trong một pipeline:

~~~java
Message<OrderCreated> enriched = MessageBuilder
    .fromMessage(originalMessage)
    .setHeader("processedBy", "inventory-service")
    .setHeader("attempt", 2)
    .build();
~~~

Message mới được tạo; message ban đầu không bị sửa. Payload được dùng lại từ message cũ, nên nếu payload là object mutable thì cả hai message vẫn có thể cùng tham chiếu tới object đó. ID/timestamp là metadata do framework quản lý; không nên giả định message mới giữ nguyên ID của message cũ.

### 4.4. createMessage

MessageBuilder còn có factory method:

~~~java
Message<OrderCreated> message =
    MessageBuilder.createMessage(payload, messageHeaders);
~~~

Factory này tạo Message với payload và MessageHeaders đã cung cấp. MessageHeaders instance được dùng trực tiếp, không sao chép. Cần bảo đảm cả payload và messageHeaders đều khác null.

## 5. Ví dụ Java 17+ chạy độc lập

Ví dụ dưới đây so sánh constructor GenericMessage, builder và việc tạo message mới từ message có sẵn. Chương trình cũng cho thấy Map gốc có thể thay đổi mà không làm thay đổi cấu trúc headers đã được sao chép.

**Cấu trúc dự án**

~~~text
generic-message-demo/
  pom.xml
  src/
    main/
      java/
        demo/
          GenericMessageDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>generic-message-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>6.2.0</version>
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

**src/main/java/demo/GenericMessageDemo.java**

~~~java
package demo;

import java.util.HashMap;
import java.util.Map;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;
import org.springframework.messaging.support.MessageBuilder;

public class GenericMessageDemo {

    public record OrderCreated(String orderId) {}

    public static void main(String[] args) {
        OrderCreated payload = new OrderCreated("ORD-1001");

        // 1. Tạo message trực tiếp bằng GenericMessage và Map headers.
        Map<String, Object> initialHeaders = new HashMap<>();
        initialHeaders.put("correlationId", "corr-1001");
        initialHeaders.put("source", "checkout");

        Message<OrderCreated> directMessage =
            new GenericMessage<>(payload, initialHeaders);

        // Map gốc thay đổi, headers của message vẫn giữ giá trị đã copy.
        initialHeaders.put("source", "changed-outside");

        System.out.println("directPayload=" + directMessage.getPayload());
        System.out.println(
            "directSource=" + directMessage.getHeaders().get("source")
        );
        System.out.println(
            "directCorrelationId=" +
            directMessage.getHeaders().get("correlationId")
        );

        // 2. Tạo message bằng MessageBuilder.
        Message<OrderCreated> builtMessage = MessageBuilder
            .withPayload(payload)
            .setHeader("correlationId", "corr-1002")
            .setHeaderIfAbsent("source", "order-service")
            .build();

        // 3. Tạo message mới từ message đã có.
        Message<OrderCreated> enrichedMessage = MessageBuilder
            .fromMessage(builtMessage)
            .setHeader("attempt", 2)
            .build();

        System.out.println(
            "builtCorrelationId=" +
            builtMessage.getHeaders().get("correlationId")
        );
        System.out.println(
            "builtSource=" + builtMessage.getHeaders().get("source")
        );
        System.out.println(
            "enrichedAttempt=" + enrichedMessage.getHeaders().get("attempt")
        );
        System.out.println(
            "enrichedSource=" + enrichedMessage.getHeaders().get("source")
        );
        System.out.println(
            "payloadSameReference=" +
            (directMessage.getPayload() == enrichedMessage.getPayload())
        );
    }
}
~~~

Chạy từ thư mục generic-message-demo:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.GenericMessageDemo
~~~

**stdout**

~~~text
directPayload=OrderCreated[orderId=ORD-1001]
directSource=checkout
directCorrelationId=corr-1001
builtCorrelationId=corr-1002
builtSource=order-service
enrichedAttempt=2
enrichedSource=order-service
payloadSameReference=true
~~~

Kết quả cho thấy:

- GenericMessage lưu payload và bản sao cấu trúc Map headers tại thời điểm tạo.
- MessageBuilder tạo message mới từ payload và metadata được thiết lập.
- fromMessage cho phép bổ sung header mà không sửa message ban đầu.
- Payload của message mới có thể vẫn là cùng object với payload của message cũ; immutable message không đồng nghĩa payload luôn immutable.

## 6. Đưa GenericMessage vào luồng xử lý

GenericMessage thường được gửi qua MessageChannel hoặc được framework tạo ra khi một thành phần chuyển dữ liệu thành Message. Ví dụ gửi vào một channel:

~~~java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1003"))
    .setHeader("correlationId", "corr-1003")
    .build();

boolean accepted = channel.send(message);
~~~

MessageChannel là abstraction gửi message. Việc message được xử lý đồng bộ, bất đồng bộ, trong bộ nhớ hay qua adapter phụ thuộc implementation của channel và cấu hình hệ thống. Việc tạo GenericMessage không tự động gửi message đi đâu cả.

Khi cần chuyển đổi payload, Spring Messaging có hệ thống MessageConverter. Converter chịu trách nhiệm chuyển đổi giữa payload và kiểu dữ liệu phù hợp với một protocol hoặc endpoint. GenericMessage vẫn là object message trong ứng dụng; để đi qua mạng, tầng tích hợp phải biết cách serialize/convert payload và ánh xạ headers sang định dạng của transport.

Nếu một API hoặc listener nhận Message<T>, có thể truyền GenericMessage<T> trực tiếp vì GenericMessage triển khai Message<T>. Nếu chỉ nhận payload, framework có thể giải quyết payload từ message tùy vào loại handler/argument resolver được sử dụng.

## 7. Khi nào dùng GenericMessage và khi nào dùng MessageBuilder?

| Tình huống | Cách phù hợp |
|---|---|
| Chỉ cần gói payload thành message | new GenericMessage<>(payload) |
| Có sẵn Map header và muốn tạo nhanh | new GenericMessage<>(payload, headers) |
| Cần thiết lập nhiều header từng bước | MessageBuilder.withPayload(...) |
| Cần mặc định header nếu chưa có | setHeaderIfAbsent(...) |
| Cần hợp nhất metadata từ Map | copyHeaders(...) hoặc copyHeadersIfAbsent(...) |
| Cần bổ sung header cho message hiện tại | MessageBuilder.fromMessage(...) |
| Đã có MessageHeaders và muốn tái sử dụng instance | GenericMessage hoặc MessageBuilder.createMessage(...) |
| Cần thao tác header nâng cao hoặc quản lý header theo protocol | Xem MessageHeaderAccessor và các subclass |

Trong code nghiệp vụ thông thường, ưu tiên MessageBuilder khi cần nhiều header hoặc cần tạo message từ message có sẵn. Constructor GenericMessage phù hợp khi cấu trúc đơn giản, rõ ràng và đã có payload/Map. Cả hai cách đều tạo ra một Message bất biến theo cấu trúc.

## 8. Lỗi thường gặp và lưu ý

1. **Nhầm GenericMessage với queue hoặc broker:** GenericMessage chỉ là object biểu diễn message. Nó không lưu hàng đợi, không tự gửi qua mạng và không tự tạo consumer.
2. **Cố sửa MessageHeaders sau khi build:** MessageHeaders chỉ đọc. Muốn thay đổi metadata, hãy build message mới.
3. **Cho rằng immutable message làm payload immutable:** GenericMessage không thay payload reference, nhưng object bên trong payload có thể vẫn mutable.
4. **Cho rằng Map headers được deep copy:** constructor nhận Map sao chép cấu trúc key-value, không clone sâu từng value.
5. **Truyền payload null:** GenericMessage yêu cầu payload khác null. Hãy mô hình hóa trường hợp không có dữ liệu bằng kiểu payload có ý nghĩa.
6. **Dùng header thay cho payload:** dữ liệu nghiệp vụ chính nên nằm trong payload; headers dành cho metadata.
7. **Dùng ID mặc định như correlation ID:** ID nhận diện message instance. Hãy tạo correlationId hoặc business key riêng cho luồng nghiệp vụ.
8. **Đặt kiểu header không nhất quán:** producer và consumer cần thống nhất kiểu dữ liệu. Ví dụ attempt nên luôn là Integer, correlationId nên luôn là String.
9. **Cho rằng Serializable đồng nghĩa mọi payload đều truyền được:** GenericMessage triển khai Serializable, nhưng payload và header values cũng phải tương thích với cơ chế serialization đang dùng. JSON converter còn có quy tắc riêng.
10. **Dùng header tùy ý mà không kiểm soát:** chỉ truyền metadata cần thiết; tránh đưa secret, token hoặc dữ liệu nhạy cảm vào message headers vì chúng có thể xuất hiện trong log hoặc bị chuyển tiếp qua adapter.

## 9. Kết luận

GenericMessage<T> là implementation phổ biến của Message<T> trong Spring Messaging. Nó đóng gói một payload không null cùng MessageHeaders và cung cấp một message bất biến sau khi được tạo. Có thể tạo message bằng constructor trực tiếp, truyền Map headers hoặc sử dụng MessageBuilder để thiết lập, sao chép và loại bỏ header theo cách rõ ràng.

Chọn constructor khi message đơn giản; chọn MessageBuilder khi cần nhiều thao tác metadata hoặc muốn tạo message mới từ message hiện có. Luôn giữ payload cho dữ liệu chính, headers cho metadata, và nhớ rằng GenericMessage không tự cung cấp channel, queue, broker hay cơ chế truyền tải.

## 10. Tài liệu tham khảo

- [Message<T> — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/Message.html)
- [GenericMessage<T> — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/GenericMessage.html)
- [MessageBuilder<T> — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [MessageHeaders — Spring Framework 6.2 Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/MessageHeaders.html)