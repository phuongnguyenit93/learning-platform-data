# Mã tương quan và liên kết yêu cầu với phản hồi

Trong hệ thống messaging, một yêu cầu có thể đi qua nhiều thành phần trước khi có kết quả trả về. Khi nhiều yêu cầu được xử lý đồng thời, bên gửi cần biết phản hồi nào thuộc về yêu cầu nào. Mã tương quan (correlation ID) giải quyết bài toán đó bằng cách gắn một định danh chung vào các thông điệp thuộc cùng một lượt trao đổi.

Spring Messaging biểu diễn metadata bằng headers của Message. Spring Integration bổ sung các cơ chế định tuyến và request/reply để các thành phần có thể gửi yêu cầu, chuyển phản hồi về đúng nơi nhận và ghép cặp các thông điệp liên quan. Bài này giải thích vai trò của correlation ID, reply channel và cách dựng một ví dụ nhỏ để quan sát toàn bộ đường đi.

## 1. Bài toán liên kết yêu cầu với phản hồi

Hãy xét một ứng dụng đặt hàng. Client gửi yêu cầu tạo đơn hàng tới OrderService. Service có thể xử lý ngay hoặc chuyển công việc sang một thành phần khác rồi mới trả kết quả.

Khi chỉ có một yêu cầu tại một thời điểm, ta có thể dễ dàng nhìn thấy yêu cầu nào dẫn tới phản hồi nào. Nhưng trong hệ thống thực tế, nhiều yêu cầu thường chạy đồng thời:

~~~text
Client
  |-- Request A -------------------->
  |-- Request B -------------------->
  |-- Request C -------------------->

Service xử lý theo lịch riêng:
  |<-- Reply B ----------------------
  |<-- Reply A ----------------------
  |<-- Reply C ----------------------
~~~

Thứ tự phản hồi có thể khác thứ tự gửi. Nếu client chỉ dựa vào thứ tự nhận, nó có thể ghép nhầm kết quả với yêu cầu. Điều này đặc biệt nguy hiểm khi mỗi yêu cầu đại diện cho một giao dịch nghiệp vụ khác nhau.

Một hệ thống request/reply cần giải quyết hai việc:

1. **Định tuyến phản hồi:** biết phải gửi reply về channel hoặc endpoint nào.
2. **Tương quan phản hồi:** biết reply thuộc về request hoặc lượt trao đổi nào.

Đây là hai khái niệm liên quan nhưng khác nhau. Reply channel xác định nơi chuyển phản hồi; correlation ID xác định mối quan hệ logic giữa request và reply.

## 2. Correlation ID là gì?

Correlation ID là một giá trị định danh được gắn vào các thông điệp thuộc cùng một luồng xử lý hoặc một lượt trao đổi. Producer tạo ID khi bắt đầu yêu cầu, đặt nó vào header và các thành phần liên quan tiếp tục truyền giá trị đó qua những thông điệp phát sinh từ yêu cầu ban đầu.

Ví dụ:

~~~text
Request:
  payload: CreateOrder(orderId=1024)
  headers:
    correlationId: corr-req-001

Reply:
  payload: OrderAccepted(orderId=1024)
  headers:
    correlationId: corr-req-001
~~~

Khi client nhận reply, nó đọc correlationId và xác định phản hồi thuộc về yêu cầu nào.

Correlation ID thường được tạo bằng UUID hoặc một định danh đủ duy nhất trong phạm vi hệ thống. Với ứng dụng phân tán, cần chọn phạm vi duy nhất phù hợp, tránh tạo ID có khả năng trùng giữa các request đang hoạt động.

### Correlation ID khác Message ID

Hai ID này có mục đích khác nhau:

| Định danh | Ý nghĩa | Ví dụ |
|---|---|---|
| Message ID | Nhận diện một Message cụ thể | ID do MessageBuilder tạo |
| Correlation ID | Liên kết nhiều Message trong cùng một lượt trao đổi | corr-req-001 |
| Business ID | Nhận diện thực thể nghiệp vụ | orderId=1024 |
| Trace ID | Liên kết các span trong một distributed trace | trace ID theo tracing system |

Một request và reply là hai Message riêng biệt, vì vậy chúng có thể có Message ID khác nhau nhưng cùng correlation ID.

Business ID cũng không nên mặc nhiên dùng làm correlation ID. Một đơn hàng có thể phát sinh nhiều yêu cầu khác nhau trong suốt vòng đời, chẳng hạn tạo đơn, thanh toán, hoàn tiền và hủy đơn. Nếu tất cả dùng chung orderId làm correlation ID, việc phân biệt từng lượt request/reply sẽ khó hơn.

Trace ID có mục tiêu quan sát và truy vết xuyên dịch vụ. Một trace có thể bao gồm nhiều thao tác và nhiều message exchange; do đó trace ID và correlation ID có thể liên quan nhưng không nhất thiết giống nhau. Hãy truyền trace context theo chuẩn tracing đang dùng, đồng thời giữ correlation ID nghiệp vụ nếu ứng dụng cần ghép cặp request/reply.

## 3. Correlation ID trong Spring Messaging

Một Message trong Spring Messaging có cấu trúc gồm payload và MessageHeaders. Correlation ID thường được truyền như một header:

~~~java
Message<String> request = MessageBuilder
        .withPayload("Create order #1024")
        .setHeader("correlationId", "corr-req-001")
        .build();
~~~

Ở đây:

- Payload chứa nội dung yêu cầu.
- Header correlationId chứa mã tương quan.
- MessageBuilder tạo Message mới cùng tập headers.
- MessageHeaders là metadata gắn với Message và không được sửa trực tiếp sau khi Message đã được tạo.

Trong Spring Integration, correlation ID còn được dùng bởi các thành phần như aggregator và resequencer để nhóm hoặc sắp xếp các thông điệp thuộc cùng một nhóm. Khi chỉ làm request/reply đơn giản, ứng dụng có thể tự tạo và truyền correlation ID như ví dụ.

Khi tạo reply, hãy sao chép correlation ID từ request:

~~~java
Message<String> reply = MessageBuilder
        .withPayload("Order accepted")
        .setHeader("correlationId", request.getHeaders().get("correlationId"))
        .build();
~~~

Việc sao chép này phải được thực hiện có chủ đích. MessageBuilder tạo một Message mới, nên Message ID của reply sẽ khác Message ID của request. Correlation ID được giữ lại để hai message vẫn thuộc cùng một lượt trao đổi.

## 4. Reply channel và correlation ID giải quyết hai vấn đề khác nhau

Một request/reply message thường cần metadata cho biết nơi gửi phản hồi. Trong Spring Messaging, header chuẩn replyChannel có thể chứa một MessageChannel hoặc tên channel tùy cơ chế định tuyến và cấu hình.

Ví dụ đặt một channel vào header:

~~~java
QueueChannel replyChannel = new QueueChannel();

Message<String> request = MessageBuilder
        .withPayload("Create order #1024")
        .setHeader("correlationId", "corr-req-001")
        .setHeader("replyChannel", replyChannel)
        .build();
~~~

Service nhận request, lấy replyChannel từ header và gửi kết quả về đó:

~~~java
MessageChannel replyTo =
        (MessageChannel) request.getHeaders().get("replyChannel");

replyTo.send(reply);
~~~

Phân biệt:

- replyChannel: nơi nhận phản hồi.
- correlationId: định danh dùng để ghép phản hồi với yêu cầu.
- messageId: định danh riêng của message hiện tại.

Trong ví dụ đơn giản, mỗi request có một QueueChannel riêng nên reply được gửi về đúng hàng đợi của request đó. Trong hệ thống có nhiều request đồng thời và dùng chung một reply channel, cần một cơ chế correlator hoặc registry để ghép reply theo correlation ID. Không nên chỉ dựa vào thứ tự message trong queue.

## 5. Luồng request/reply tổng quát

Một lượt trao đổi có thể diễn ra như sau:

~~~text
Client / Producer
    |
    | Tạo correlationId
    | Tạo replyChannel
    | Gửi request + headers
    v
Request Channel
    |
    v
Service / MessageHandler
    |
    | Đọc payload và correlationId
    | Xử lý nghiệp vụ
    | Tạo reply mới
    | Gắn lại correlationId
    | Gửi reply tới replyChannel
    v
Reply Channel
    |
    v
Client / Requester
    |
    | Đọc reply
    | Đối chiếu correlationId
    v
Hoàn tất lượt trao đổi
~~~

Nếu request được xử lý bất đồng bộ, client có thể tiếp tục công việc khác trong khi chờ reply. Nếu cần chờ trong một khoảng thời gian, client phải đặt timeout và xử lý trường hợp không có phản hồi. Khi reply đến muộn sau timeout, hệ thống cần có chính sách bỏ qua, ghi log hoặc xử lý như một sự kiện đến trễ.

## 6. Ví dụ hoàn chỉnh: request và reply qua hai channel

Ví dụ sau dùng Spring Integration để quan sát request đi vào DirectChannel, handler xử lý và gửi reply qua QueueChannel được gắn trong header. Client nhận reply và kiểm tra correlation ID.

Ví dụ dùng Java 17 và Spring Integration 6.4.6. Chương trình chạy trong một tiến trình, không cần broker hay Spring ApplicationContext.

Cấu trúc dự án:

~~~text
correlation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── CorrelationDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>correlation-demo</artifactId>
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

### src/main/java/demo/CorrelationDemo.java

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

public class CorrelationDemo {

    public static void main(String[] args) {
        DirectChannel requestChannel = new DirectChannel();

        MessageHandler orderService = request -> {
            Object correlationValue =
                    request.getHeaders().get("correlationId");
            Object replyChannelValue =
                    request.getHeaders().get("replyChannel");

            if (!(correlationValue instanceof String correlationId)) {
                throw new IllegalArgumentException(
                        "Missing correlationId header");
            }

            if (!(replyChannelValue instanceof MessageChannel replyTo)) {
                throw new IllegalArgumentException(
                        "Missing or invalid replyChannel header");
            }

            System.out.println("[service] received: " + request.getPayload());
            System.out.println("[service] correlationId = " + correlationId);

            Message<String> reply = MessageBuilder
                    .withPayload("Accepted: " + request.getPayload())
                    .setHeader("correlationId", correlationId)
                    .build();

            if (!replyTo.send(reply)) {
                throw new IllegalStateException(
                        "Reply channel rejected the message");
            }
        };

        requestChannel.subscribe(orderService);

        String correlationId = "corr-req-001";
        QueueChannel replyChannel = new QueueChannel();

        Message<String> request = MessageBuilder
                .withPayload("Create order #1024")
                .setHeader("correlationId", correlationId)
                .setHeader("replyChannel", replyChannel)
                .build();

        System.out.println("[client] request correlationId = "
                + correlationId);

        if (!requestChannel.send(request)) {
            throw new IllegalStateException(
                    "Request channel rejected the message");
        }

        Message<?> reply = replyChannel.receive(1000);

        if (reply == null) {
            throw new IllegalStateException("Timed out waiting for reply");
        }

        System.out.println("[client] reply payload = " + reply.getPayload());
        System.out.println("[client] reply correlationId = "
                + reply.getHeaders().get("correlationId"));
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~shell
mvn -q compile exec:java -Dexec.mainClass=demo.CorrelationDemo
~~~

Output:

~~~text
[client] request correlationId = corr-req-001
[service] received: Create order #1024
[service] correlationId = corr-req-001
[client] reply payload = Accepted: Create order #1024
[client] reply correlationId = corr-req-001
~~~

### Phân tích đường đi của request và reply

**Bước 1 — Tạo request channel:** DirectChannel đóng vai trò điểm nhận request. Service được đăng ký làm subscriber bằng subscribe(orderService).

**Bước 2 — Tạo reply channel:** client tạo một QueueChannel riêng cho lượt trao đổi này. QueueChannel là PollableChannel, vì vậy client có thể lấy reply bằng receive(timeout).

**Bước 3 — Tạo correlation ID:** ví dụ dùng giá trị cố định corr-req-001 để output dễ đối chiếu. Trong ứng dụng thực tế, nên tạo ID duy nhất, chẳng hạn bằng UUID.

**Bước 4 — Gắn metadata:** request chứa cả correlationId và replyChannel. Hai header phục vụ hai mục đích riêng: nhận diện lượt trao đổi và chỉ đường cho phản hồi.

**Bước 5 — Service nhận request:** handler kiểm tra kiểu và sự tồn tại của hai header trước khi xử lý. Nếu thiếu correlation ID hoặc reply channel, ví dụ phát sinh lỗi rõ ràng thay vì âm thầm tạo một phản hồi không thể ghép cặp.

**Bước 6 — Tạo reply:** service tạo Message mới, đặt payload kết quả và sao chép correlation ID từ request.

**Bước 7 — Gửi reply:** service lấy MessageChannel từ header replyChannel rồi gửi reply vào QueueChannel của client.

**Bước 8 — Client nhận và đối chiếu:** client gọi receive(1000), tức chờ tối đa 1.000 mili giây. Sau khi nhận reply, nó đọc correlationId và xác nhận giá trị khớp với request đã gửi.

DirectChannel gọi handler đồng bộ, nên trong ví dụ này reply đã được đưa vào QueueChannel trước khi lời gọi requestChannel.send(request) trả về. Client vẫn dùng receive để thể hiện cách một bên nhận reply từ PollableChannel. Trong hệ thống bất đồng bộ, request và reply có thể đến ở các thời điểm khác nhau.

## 7. Xử lý nhiều request đồng thời

Khi có nhiều request cùng lúc, mỗi lượt trao đổi cần có correlation ID riêng. Ví dụ:

| Request | Correlation ID | Reply |
|---|---|---|
| Tạo đơn 1024 | corr-A | Order 1024 accepted |
| Tạo đơn 1025 | corr-B | Order 1025 accepted |
| Tạo đơn 1026 | corr-C | Order 1026 accepted |

Nếu reply về theo thứ tự C, A, B, client vẫn ghép đúng bằng correlation ID.

Có hai cách tổ chức phổ biến:

**Mỗi request có reply channel riêng:** client tạo một QueueChannel hoặc cơ chế nhận riêng cho từng request, rồi gắn channel vào header replyChannel. Cách này đơn giản để minh họa và tránh các request cạnh tranh lấy reply của nhau. Tuy nhiên, cần quản lý vòng đời channel, timeout và giải phóng tài nguyên khi request hoàn tất.

**Nhiều request dùng chung reply channel:** các reply được gửi về một channel chung. Một thành phần correlator đọc reply, lấy correlationId và tìm request đang chờ tương ứng trong registry. Cần xử lý trường hợp không tìm thấy request, reply đến trễ, trùng lặp hoặc registry đã hết hạn.

Không nên để một QueueChannel dùng chung được nhiều request thread cùng gọi receive mà không có cơ chế ghép cặp. Một thread có thể lấy mất reply vốn dành cho thread khác.

Trong Spring Integration, các gateway và thành phần request/reply có thể quản lý việc tạo reply channel tạm thời và tương quan cho người gọi. Khi dùng gateway, hãy ưu tiên cơ chế chuẩn của framework thay vì tự xây một registry nếu nhu cầu đã được gateway đáp ứng.

## 8. Correlation ID và các header liên quan

| Header hoặc dữ liệu | Mục đích | Lưu ý |
|---|---|---|
| correlationId | Ghép các message thuộc cùng lượt trao đổi | Phải được truyền tiếp hoặc sao chép có chủ đích |
| replyChannel | Chỉ định nơi gửi reply | Có thể là channel object hoặc tên channel tùy cấu hình |
| errorChannel | Định tuyến thông điệp lỗi trong các luồng hỗ trợ cơ chế này | Cần cấu hình và hiểu rõ error flow |
| id | Nhận diện một Message cụ thể | Request và reply thường có ID khác nhau |
| timestamp | Thời điểm Message được tạo | Không dùng thay correlation ID |
| trace context | Liên kết thao tác trong distributed tracing | Theo chuẩn tracing của hệ thống |

Một số lưu ý:

- Không dùng timestamp làm correlation ID vì nhiều request có thể được tạo trong cùng một đơn vị thời gian.
- Không dùng Message ID của request làm correlation ID nếu reply là Message mới và cần một ID chung cho cả lượt trao đổi.
- Không đặt thông tin cá nhân hoặc bí mật vào correlation ID.
- Không xem correlation ID là bằng chứng xác thực. Một client có thể gửi giá trị tùy ý; quyền truy cập vẫn phải được kiểm tra độc lập.
- Khi truyền qua broker hoặc serialization, hãy bảo đảm header được adapter hỗ trợ và được chuyển đổi đúng kiểu dữ liệu.

## 9. Timeout, reply đến trễ và lỗi

Request/reply luôn cần chính sách cho trường hợp không có phản hồi.

### Timeout

Client nên đặt thời gian chờ dựa trên SLA của thao tác. Trong ví dụ, receive(1000) chờ tối đa một giây. Nếu không có reply, kết quả là null, và code phát sinh IllegalStateException.

Trong ứng dụng thật, nên phân biệt timeout với lỗi nghiệp vụ. Timeout chỉ cho biết client chưa nhận được phản hồi trong thời hạn; nó không chứng minh service chưa xử lý request. Service có thể đã tạo đơn hàng nhưng reply bị chậm hoặc thất lạc.

### Reply đến sau timeout

Nếu client đã hết thời gian chờ nhưng reply vẫn đến, cần có chính sách xử lý:

- Bỏ qua reply nếu kết quả không còn cần thiết.
- Ghi log hoặc metric để phát hiện độ trễ bất thường.
- Lưu kết quả nếu nghiệp vụ cần truy xuất sau.
- Hủy hoặc hết hạn correlation entry để tránh rò rỉ bộ nhớ.

### Retry và xử lý trùng

Nếu client retry sau timeout, request mới có thể tạo thêm một thao tác nghiệp vụ. Với lệnh tạo đơn hoặc thanh toán, điều này có thể gây trùng dữ liệu hoặc trừ tiền nhiều lần.

Hãy phân biệt:

- **Correlation ID:** liên kết request/reply của một lượt trao đổi.
- **Idempotency key:** bảo vệ một thao tác nghiệp vụ khỏi bị thực hiện lặp ngoài ý muốn.

Hai giá trị có thể liên quan nhưng không nên mặc định là một. Khi retry cùng một thao tác nghiệp vụ, ứng dụng thường cần giữ idempotency key phù hợp, trong khi mỗi lần gửi lại có thể có correlation ID mới để truy vết từng lượt trao đổi.

### Lỗi kỹ thuật và lỗi nghiệp vụ

Nếu service không xử lý được request, nó có thể phát thông điệp lỗi qua error channel hoặc một reply mang trạng thái lỗi theo hợp đồng ứng dụng. Cần xác định rõ client sẽ nhận exception, error message hay business rejection.

Ví dụ:

- OrderRejected là kết quả nghiệp vụ hợp lệ: đơn hàng không được chấp nhận do hết hàng.
- DatabaseUnavailable là lỗi kỹ thuật: service không thể truy cập cơ sở dữ liệu.
- Timeout là tình trạng client không nhận phản hồi đúng hạn.

Không nên gộp tất cả các tình huống thành một chuỗi lỗi chung vì client sẽ khó quyết định có nên retry hay thông báo cho người dùng.

## 10. Thực hành tốt khi thiết kế correlation

1. **Tạo ID đủ duy nhất:** dùng UUID hoặc ID từ hệ thống định danh đã được chuẩn hóa.
2. **Đặt ID ngay khi bắt đầu lượt trao đổi:** mọi thông điệp phát sinh từ request nên mang cùng correlation ID khi còn thuộc cùng luồng xử lý.
3. **Giữ ID khi tạo reply:** reply là Message mới nhưng cần mang lại correlation ID của request.
4. **Tách ID khỏi dữ liệu nghiệp vụ:** orderId, paymentId và correlationId có vai trò khác nhau.
5. **Dùng reply channel đúng vòng đời:** không giữ channel tạm thời sau khi request đã hoàn tất.
6. **Đặt timeout:** tránh request chờ vô hạn và registry tích tụ không giới hạn.
7. **Xử lý reply trễ và trùng:** quy định rõ cách bỏ qua, ghi nhận hoặc xử lý lại.
8. **Bảo vệ dữ liệu:** correlation ID không chứa PII, token hay bí mật.
9. **Kết hợp tracing:** dùng trace context để truy vết xuyên dịch vụ và correlation ID để ghép lượt trao đổi theo nghiệp vụ.
10. **Kiểm tra kiểu header:** xác thực correlationId và replyChannel trước khi dùng, đặc biệt khi nhận message từ nguồn bên ngoài.

## 11. Những nhầm lẫn phổ biến

**Correlation ID giống Message ID:** sai. Mỗi Message có ID riêng; nhiều Message thuộc cùng một lượt trao đổi có thể dùng chung correlation ID.

**Correlation ID chính là reply channel:** sai. Một giá trị nhận diện lượt trao đổi không thể tự chỉ ra nơi chuyển reply. Cần metadata định tuyến riêng.

**Chỉ cần giữ thứ tự gửi là ghép được reply:** sai. Các consumer xử lý song song có thể trả lời theo thứ tự khác nhau. Dùng correlation ID để ghép cặp.

**Dùng orderId cho mọi correlation:** dễ gây nhầm nếu một đơn hàng có nhiều lượt request/reply độc lập. Hãy tách định danh thực thể và định danh lượt trao đổi.

**Timeout có nghĩa là request thất bại:** sai. Client chỉ biết chưa nhận được reply đúng hạn. Nghiệp vụ phía service có thể đã hoàn tất.

**Retry luôn an toàn:** sai. Retry có thể tạo tác động lặp. Cần idempotency key hoặc cơ chế chống xử lý trùng phù hợp.

**Header tự động được giữ qua mọi broker:** không nên giả định như vậy. Adapter, serializer và broker có thể chuyển đổi hoặc giới hạn header; cần kiểm tra cấu hình thực tế.

## 12. Ghi nhớ

- Correlation ID liên kết request và reply thuộc cùng một lượt trao đổi.
- Message ID nhận diện từng Message riêng biệt; request và reply thường có Message ID khác nhau.
- replyChannel xác định nơi gửi phản hồi, còn correlationId xác định phản hồi thuộc về request nào.
- Spring Messaging truyền metadata qua MessageHeaders; MessageBuilder dùng để tạo Message và gắn header.
- Spring Integration hỗ trợ các luồng request/reply, channel và gateway để định tuyến, nhận phản hồi.
- Khi có nhiều request đồng thời, cần ID riêng và cơ chế ghép reply; không dựa vào thứ tự message.
- Timeout không chứng minh nghiệp vụ chưa thực hiện; retry cần được thiết kế cùng idempotency.
- Correlation ID hỗ trợ truy vết và đối chiếu, nhưng không thay thế xác thực, phân quyền hoặc trace context.
