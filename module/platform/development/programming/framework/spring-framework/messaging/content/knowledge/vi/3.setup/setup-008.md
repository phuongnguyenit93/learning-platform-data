# Dựng ví dụ nhỏ để quan sát đường đi của một thông điệp

Cách dễ hiểu Spring Messaging là theo dõi một thông điệp từ lúc được tạo, đi qua channel, đến khi một handler nhận và xử lý nó. Bài này dựng một chương trình Java nhỏ dùng Spring Integration để quan sát luồng đó. Chương trình tạo một Message có payload và headers, gửi vào DirectChannel, rồi in dữ liệu ở phía nhận.

Ví dụ chạy trong một tiến trình, không cần broker, cơ sở dữ liệu hay máy chủ. Nhờ vậy, ta có thể tập trung vào các thành phần cơ bản và hiểu rõ thao tác gửi thực hiện điều gì.

## 1. Mục tiêu và luồng xử lý

Sau khi hoàn thành, bạn sẽ nhận biết được vai trò của:

- **Producer:** thành phần tạo và gửi thông điệp.
- **Message:** gói dữ liệu gồm payload và headers.
- **MessageChannel:** điểm gửi thông điệp tới một hoặc nhiều handler theo cách triển khai của channel.
- **MessageHandler:** thành phần nhận và xử lý thông điệp.
- **DirectChannel:** channel của Spring Integration thực hiện việc chuyển thông điệp trực tiếp tới một subscriber trong cùng luồng gọi.

Luồng của chương trình:

~~~text
MessageFlowDemo (Producer)
        |
        | MessageBuilder.withPayload(...)
        | setHeader(...)
        v
   Message<String>
        |
        | DirectChannel.send(message)
        v
    DirectChannel
        |
        | gọi MessageHandler
        v
   MessageHandler (Consumer)
        |
        | đọc payload và headers
        v
   In ra console
        |
        v
   send() trả về true
~~~

Ví dụ này sử dụng DirectChannel, vì vậy handler được gọi đồng bộ trên luồng đang gửi. Khi đọc output, bạn sẽ thấy log của consumer xuất hiện trước log xác nhận kết quả gửi của producer.

## 2. Chuẩn bị môi trường

Cần có:

- JDK 17 trở lên.
- Apache Maven 3.8 trở lên.
- Một IDE Java bất kỳ hoặc terminal.
- Kết nối Internet ở lần đầu Maven tải dependency.

Ví dụ sử dụng Spring Integration 6.4.6. Module spring-integration-core cung cấp DirectChannel và phụ thuộc vào Spring Messaging, vì vậy dự án có thể dùng Message, MessageBuilder và MessageHandler mà không cần khai báo riêng một dependency spring-messaging.

Kiểm tra môi trường:

~~~shell
java -version
mvn -version
~~~

Cả hai lệnh cần hiển thị phiên bản Java/Maven hợp lệ. Nếu máy có nhiều JDK, hãy kiểm tra JAVA_HOME và cấu hình Maven đang dùng đúng JDK 17 trở lên.

## 3. Tạo cấu trúc dự án

Tạo một thư mục tên message-flow-demo với cấu trúc:

~~~text
message-flow-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MessageFlowDemo.java
~~~

pom.xml khai báo dependency Spring Integration Core và các plugin để biên dịch, chạy chương trình bằng Maven.

## 4. Khai báo dependency trong pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>message-flow-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.4.6</version>
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

Các điểm cần chú ý:

- spring-integration-core cung cấp implementation DirectChannel.
- Spring Messaging cung cấp các abstraction Message, MessageChannel, MessageHandler và MessageBuilder.
- maven.compiler.release đặt mức Java API mục tiêu là 17.
- exec-maven-plugin cho phép chạy class có hàm main trực tiếp từ Maven.

Nếu dự án đã dùng Spring Boot, hãy ưu tiên để Spring Boot dependency management quản lý phiên bản Spring Integration tương thích thay vì tự ghim phiên bản từng module.

## 5. Viết chương trình MessageFlowDemo.java

Tạo file src/main/java/demo/MessageFlowDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class MessageFlowDemo {

    public static void main(String[] args) {
        // 1. Tạo channel để producer gửi message.
        DirectChannel ordersChannel = new DirectChannel();

        // 2. Tạo consumer và đăng ký consumer vào channel.
        MessageHandler orderHandler = message -> {
            System.out.println("[consumer] payload = " + message.getPayload());
            System.out.println("[consumer] eventType = "
                    + message.getHeaders().get("eventType"));
            System.out.println("[consumer] correlationId = "
                    + message.getHeaders().get("correlationId"));
        };

        ordersChannel.subscribe(orderHandler);

        // 3. Tạo message gồm payload và headers.
        Message<String> message = MessageBuilder
                .withPayload("Order #1024 created")
                .setHeader("eventType", "order.created")
                .setHeader("correlationId", "corr-001")
                .build();

        // 4. Gửi message qua channel.
        System.out.println("[producer] sending message");
        boolean sent = ordersChannel.send(message);

        // 5. Quan sát kết quả gửi.
        System.out.println("[producer] send result = " + sent);
    }
}
~~~

Chương trình không cần tạo Spring ApplicationContext vì ví dụ khởi tạo trực tiếp implementation DirectChannel và đăng ký handler bằng subscribe().

## 6. Chạy chương trình và quan sát kết quả

Mở terminal tại thư mục message-flow-demo, chạy:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.MessageFlowDemo
~~~

Ở lần chạy đầu tiên, Maven tải các dependency cần thiết. Khi chương trình chạy thành công, output là:

~~~text
[producer] sending message
[consumer] payload = Order #1024 created
[consumer] eventType = order.created
[consumer] correlationId = corr-001
[producer] send result = true
~~~

Thứ tự output cho thấy đường đi của thông điệp:

1. Producer in thông báo chuẩn bị gửi.
2. Producer gọi ordersChannel.send(message).
3. DirectChannel chuyển Message tới handler đã đăng ký.
4. Consumer đọc payload và các header, sau đó in ra console.
5. Handler hoàn tất, thao tác gửi trả về true.
6. Producer in kết quả gửi.

Do DirectChannel xử lý trực tiếp, các dòng của consumer xuất hiện ngay trong lời gọi send(). Chương trình không tạo một hàng đợi để consumer xử lý sau.

## 7. Phân tích từng thành phần

### 7.1. Tạo DirectChannel

~~~java
DirectChannel ordersChannel = new DirectChannel();
~~~

DirectChannel là implementation của SubscribableChannel trong Spring Integration. Nó duy trì danh sách các subscriber và điều phối thông điệp tới một handler phù hợp.

Với một subscriber như ví dụ này, thông điệp được chuyển tới subscriber đó. Nếu có nhiều subscriber, DirectChannel sử dụng cơ chế phân phối của nó để chọn handler xử lý một lần gửi; nó không phát bản sao tới tất cả subscriber.

Đây là mô hình point-to-point. Nếu mục tiêu là phát cùng một thông điệp tới tất cả subscriber, hãy tìm hiểu PublishSubscribeChannel.

### 7.2. Tạo và đăng ký MessageHandler

~~~java
MessageHandler orderHandler = message -> {
    System.out.println(message.getPayload());
};

ordersChannel.subscribe(orderHandler);
~~~

MessageHandler là hợp đồng xử lý một Message<?>. Consumer không cần biết producer đã tạo thông điệp ở đâu; nó chỉ cần đọc dữ liệu theo hợp đồng.

subscribe() đăng ký handler với channel. Sau khi đăng ký, channel có thể chuyển thông điệp tới handler này.

Trong ví dụ, lambda được dùng làm implementation ngắn gọn của MessageHandler. Trong ứng dụng lớn, có thể tách handler thành một class riêng để quản lý nghiệp vụ, logging và kiểm thử.

### 7.3. Tạo Message bằng MessageBuilder

~~~java
Message<String> message = MessageBuilder
        .withPayload("Order #1024 created")
        .setHeader("eventType", "order.created")
        .setHeader("correlationId", "corr-001")
        .build();
~~~

Thông điệp có hai phần:

- Payload là chuỗi Order #1024 created.
- Headers chứa eventType và correlationId.

MessageBuilder giúp tạo message theo cách rõ ràng và hỗ trợ bổ sung metadata. MessageHeaders được thiết kế bất biến sau khi message được tạo; nếu cần thay đổi header, hãy tạo message mới bằng builder.

Trong ứng dụng thực tế, payload thường là DTO hoặc event class có cấu trúc thay vì chuỗi tự do. Header có thể chứa correlation ID, trace context, nguồn phát hoặc metadata định tuyến. Không nên đưa dữ liệu nghiệp vụ lớn vào header.

### 7.4. Gửi thông điệp

~~~java
boolean sent = ordersChannel.send(message);
~~~

send() chuyển thông điệp vào channel. Với DirectChannel, thao tác dispatch tới handler diễn ra trong luồng gọi. Giá trị trả về true cho biết channel đã chuyển thông điệp thành công theo hợp đồng gửi của channel.

Không nên hiểu true là toàn bộ nghiệp vụ đã hoàn tất hoặc dữ liệu đã được lưu bền vững. Ví dụ hiện tại chỉ in nội dung ra console; không có transaction cơ sở dữ liệu, broker hay cơ chế xác nhận nghiệp vụ.

## 8. Thử thay đổi để hiểu rõ đường đi

Sau khi chạy chương trình ban đầu, hãy thử các thay đổi sau để quan sát hành vi.

### Thay đổi payload

Đổi:

~~~java
.withPayload("Order #1024 created")
~~~

thành:

~~~java
.withPayload("Order #2048 created")
~~~

Chạy lại chương trình. Consumer sẽ in payload mới, trong khi các header vẫn giữ nguyên. Điều này cho thấy payload và metadata là hai phần riêng của Message.

### Thêm header

Bổ sung:

~~~java
.setHeader("source", "checkout-service")
~~~

Trong handler, đọc header:

~~~java
System.out.println("[consumer] source = "
        + message.getHeaders().get("source"));
~~~

Kết quả sẽ xuất hiện thêm dòng:

~~~text
[consumer] source = checkout-service
~~~

Producer đã bổ sung metadata mà không cần thay đổi chữ ký của MessageHandler.

### Đăng ký thêm handler

Có thể tạo thêm một handler:

~~~java
MessageHandler auditHandler = message -> {
    System.out.println("[audit] received message id = "
            + message.getHeaders().getId());
};

ordersChannel.subscribe(auditHandler);
~~~

Với DirectChannel, hai handler cùng đăng ký sẽ tham gia cơ chế phân phối point-to-point. Mỗi lần gửi chỉ một handler được chọn để xử lý, tùy load-balancing strategy. Vì vậy, không nên kỳ vọng cả orderHandler và auditHandler đều được gọi cho cùng một message.

Nếu muốn cả hai cùng nhận mọi message, thay channel bằng PublishSubscribeChannel:

~~~java
import org.springframework.integration.channel.PublishSubscribeChannel;

PublishSubscribeChannel ordersChannel = new PublishSubscribeChannel();
~~~

Các handler đã đăng ký với PublishSubscribeChannel sẽ cùng nhận thông điệp được phát. Đây là cách quan sát sự khác nhau giữa point-to-point và publish/subscribe.

### Quan sát hành vi khi không có subscriber

Tạm thời bỏ dòng:

~~~java
ordersChannel.subscribe(orderHandler);
~~~

Sau đó chạy lại. DirectChannel không có handler để chuyển thông điệp tới, nên thao tác gửi không thể được dispatch thành công; kết quả gửi sẽ không còn là true. Tùy cấu hình channel và cơ chế xử lý lỗi, ứng dụng cũng có thể nhận ngoại lệ khi gửi.

Điều này cho thấy producer cần có một channel được cấu hình và có consumer phù hợp trước khi gửi.

## 9. DirectChannel và các lựa chọn khác

Các channel khác nhau thể hiện những chính sách giao tiếp khác nhau:

| Channel | Cách phân phối | Đặc điểm chính |
|---|---|---|
| DirectChannel | Một subscriber được chọn | Gọi handler trực tiếp trong luồng gửi |
| PublishSubscribeChannel | Tất cả subscriber | Phát cùng thông điệp tới nhiều handler |
| ExecutorChannel | Một subscriber được chọn | Chuyển việc xử lý qua Executor, có thể bất đồng bộ |
| QueueChannel | Lưu trong hàng đợi | Consumer chủ động nhận thông điệp |

Các implementation này thuộc Spring Integration. Spring Messaging cung cấp abstraction MessageChannel và các hợp đồng liên quan; Spring Integration bổ sung các channel cụ thể và nhiều thành phần tích hợp.

Việc chọn channel cần dựa trên yêu cầu:

- Cần xử lý ngay trong cùng luồng: DirectChannel.
- Cần phát sự kiện cho nhiều thành phần: PublishSubscribeChannel.
- Cần tách thời gian xử lý bằng executor: ExecutorChannel.
- Cần lưu thông điệp tạm thời để consumer lấy sau: QueueChannel.

Các channel trong bộ nhớ không tự cung cấp độ bền dữ liệu khi ứng dụng tắt. Nếu cần giao tiếp bền vững giữa các tiến trình hoặc máy chủ, hãy tích hợp broker phù hợp như RabbitMQ, ActiveMQ hoặc một hệ thống hỗ trợ messaging tương ứng.

## 10. Lỗi thường gặp khi dựng ví dụ

**Thiếu dependency Spring Integration Core:** nếu chỉ thêm một module không chứa DirectChannel, compiler sẽ báo không tìm thấy package org.springframework.integration.channel. Hãy kiểm tra dependency spring-integration-core.

**Import sai Message:** sử dụng org.springframework.messaging.Message, không nhầm với class khác có tên tương tự.

**Quên đăng ký handler:** tạo channel và gọi send mà chưa có subscriber thì không có consumer xử lý message.

**Đọc sai header:** tên header phải khớp chính xác với key đã truyền vào setHeader(). Nếu key không tồn tại, get() trả về null.

**Nhầm DirectChannel với queue:** DirectChannel chuyển trực tiếp tới handler. Nó không lưu message để xử lý sau.

**Nhầm kết quả send với kết quả nghiệp vụ:** send() thành công chỉ phản ánh việc gửi theo hợp đồng channel. Nếu handler ghi database hoặc gọi API, cần thiết kế transaction và xử lý lỗi riêng.

**Cho rằng nhiều subscriber luôn nhận cùng một message:** DirectChannel phân phối point-to-point. Dùng PublishSubscribeChannel khi cần broadcast.

## 11. Mở rộng ví dụ trong ứng dụng thực tế

Khi đã hiểu đường đi cơ bản, có thể mở rộng theo từng nhu cầu:

- Thay payload String bằng một event class như OrderCreated.
- Tách producer và consumer thành các class riêng.
- Thêm correlation ID để liên kết log của các bước xử lý.
- Dùng PublishSubscribeChannel khi nhiều thành phần cùng quan tâm một sự kiện.
- Dùng ExecutorChannel khi muốn handler chạy qua executor.
- Dùng QueueChannel khi cần mô hình producer gửi và consumer chủ động lấy.
- Kết nối adapter với broker khi cần giao tiếp giữa các tiến trình.
- Bổ sung validation, xử lý exception, retry và quan sát độ trễ khi đưa vào môi trường thật.

Ví dụ tối thiểu nên được giữ đơn giản trong giai đoạn học. Khi thêm broker, transaction hoặc nhiều consumer, hãy thay đổi từng phần và quan sát tác động của nó lên đường đi của message.

## 12. Ghi nhớ

- Message gồm payload và headers; MessageBuilder giúp tạo thông điệp có cấu trúc.
- Producer tạo message và gửi qua MessageChannel.
- MessageHandler nhận message và thực hiện xử lý.
- DirectChannel của Spring Integration chuyển message tới một subscriber theo mô hình point-to-point và xử lý đồng bộ trong luồng gửi.
- PublishSubscribeChannel phát message tới tất cả subscriber đã đăng ký.
- Kết quả send() phản ánh việc gửi theo hợp đồng của channel, không đồng nghĩa nghiệp vụ đã hoàn tất hoặc dữ liệu đã được lưu bền vững.
- Ví dụ trong bài chạy trong cùng tiến trình và không sử dụng broker; muốn giao tiếp bền vững qua mạng cần tích hợp hạ tầng messaging phù hợp.
