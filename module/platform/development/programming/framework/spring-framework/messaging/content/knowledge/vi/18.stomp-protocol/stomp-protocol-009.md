# ACK, NACK và transaction frame trong STOMP theo khả năng của broker

STOMP cung cấp các frame ACK, NACK, BEGIN, COMMIT và ABORT để client xác nhận việc xử lý message và nhóm thao tác gửi/acknowledge trong một transaction ở phía message server.

Các frame này chỉ phát huy tác dụng khi broker hỗ trợ chúng. Spring simple broker chỉ triển khai một tập con của STOMP và không hỗ trợ ACK, NACK, RECEIPT cùng các tính năng transaction tương ứng. Khi cần acknowledgement tường minh hoặc transaction frame, Spring application thường phải relay STOMP tới một broker bên ngoài có hỗ trợ các tính năng đó.

Cần phân biệt ba lớp:

- **STOMP protocol:** quy định cú pháp frame và ý nghĩa ACK, NACK, transaction.
- **Broker:** quyết định cách redelivery, requeue, dead-letter, persistence và transaction được thực thi.
- **Ứng dụng:** quyết định khi nào message được xem là xử lý thành công, cách chống trùng và cách phối hợp với database hoặc service khác.

## 1. Luồng nhận message và acknowledgement

Một client STOMP đăng ký destination bằng SUBSCRIBE. Header ack chọn cách server xem message đã được xác nhận.

~~~text
SUBSCRIBE
id:orders-sub
destination:/queue/orders
ack:client-individual

<NUL>
~~~

Các giá trị ack hợp lệ trong STOMP 1.2:

| Giá trị | Hành vi |
| --- | --- |
| auto | Client không cần gửi ACK. Server xem message đã được giao khi gửi MESSAGE cho client. |
| client | Client phải gửi ACK. Một ACK xác nhận message được chỉ định và tất cả message trước đó trên cùng subscription chưa được ACK/NACK. Đây là cumulative acknowledgement. |
| client-individual | Client phải gửi ACK cho từng message. ACK một message không xác nhận các message khác. |

Nếu không chỉ định header ack, giá trị mặc định là auto.

### Vì sao auto có thể làm mất message?

Ở chế độ auto, server không đợi ứng dụng hoàn tất xử lý. Khi server gửi MESSAGE xuống connection, nó xem message đã được giao. Nếu browser hoặc process client dừng trước khi lưu dữ liệu hoặc thực hiện nghiệp vụ, message có thể đã bị xem là đã tiêu thụ.

Ví dụ:

1. Broker gửi MESSAGE cho client.
2. Client nhận frame vào socket.
3. Tab trình duyệt bị đóng trước khi lưu dữ liệu.
4. Broker không có ACK để biết ứng dụng chưa xử lý.

Với công việc cần xác nhận xử lý, hãy dùng client hoặc client-individual nếu broker hỗ trợ.

### MESSAGE frame có ack token

Khi subscription yêu cầu explicit acknowledgement, broker gửi MESSAGE kèm header ack. Ví dụ:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-42
ack:ack-42
destination:/queue/orders
content-type:text/plain

order-42
<NUL>
~~~

Có ba giá trị khác nhau:

- subscription: ID của subscription đã đăng ký.
- message-id: ID của message do server/broker cấp.
- ack: token dùng để xác nhận hoặc từ chối message.

Trong STOMP 1.2, ACK/NACK phải dùng giá trị từ header ack của MESSAGE. Không tự lấy message-id thay cho ack token.

## 2. ACK: xác nhận đã xử lý message

ACK thông báo cho server rằng client đã tiêu thụ message. Với STOMP 1.2, frame ACK có header bắt buộc id:

~~~text
ACK
id:ack-42

<NUL>
~~~

Giá trị id phải khớp với header ack trong MESSAGE tương ứng.

### ACK theo từng chế độ

Với ack:client:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-41
ack:ack-41
destination:/queue/orders

order-41
<NUL>

MESSAGE
subscription:orders-sub
message-id:msg-42
ack:ack-42
destination:/queue/orders

order-42
<NUL>

ACK
id:ack-42

<NUL>
~~~

ACK cho ack-42 đồng thời xác nhận message ack-41 đã được gửi trước đó trên cùng subscription nếu nó chưa được ACK/NACK. Đây là hành vi cumulative.

Với ack:client-individual, ACK ack-42 chỉ xác nhận message thứ hai. Message ack-41 vẫn chưa được xác nhận và có thể được redeliver nếu connection bị mất.

### ACK sau khi nào?

Client nên gửi ACK sau khi hoàn tất bước xử lý mà ứng dụng xem là thành công. Ví dụ, nếu xử lý gồm lưu đơn hàng vào database, hãy commit database trước khi ACK để tránh xác nhận message rồi mất dữ liệu khi database thất bại.

Tuy nhiên, nếu database đã commit mà connection bị mất trước khi broker nhận ACK, message có thể được giao lại. Vì vậy consumer cần idempotency hoặc duplicate detection. ACK một lần không tạo ra exactly-once processing cho toàn bộ nghiệp vụ.

### STOMP 1.1 và STOMP 1.2 khác nhau ở header ACK

| Phiên bản | Header ACK |
| --- | --- |
| STOMP 1.1 | Dùng message-id và subscription |
| STOMP 1.2 | Dùng id, giá trị lấy từ header ack của MESSAGE |

Client và broker có thể thương lượng version qua CONNECT/STOMP và CONNECTED. Khi hỗ trợ nhiều version, hãy để STOMP client library xử lý khác biệt wire format; không tự gửi header của version khác.

## 3. NACK: từ chối hoặc báo không xử lý được message

NACK là negative acknowledgement. Client gửi NACK khi không thể xử lý message:

~~~text
NACK
id:ack-43

<NUL>
~~~

Trong STOMP 1.2, header id phải khớp với ack token trên MESSAGE. NACK cũng có thể mang transaction header.

NACK cho broker biết message chưa được tiêu thụ thành công. Tuy nhiên, STOMP không bắt buộc một chính sách redelivery duy nhất. Broker có thể:

- Đưa message trở lại queue để giao lại.
- Giao message cho consumer khác.
- Loại bỏ message.
- Chuyển message vào dead-letter queue.
- Áp dụng retry delay, delivery limit hoặc chính sách riêng.

Hành vi chính xác phụ thuộc broker, destination và cấu hình subscription.

### NACK với client và client-individual

Trong ack:client, NACK có hiệu lực cumulative đối với message được chỉ định và các message trước đó trên cùng subscription chưa được ACK/NACK.

Trong ack:client-individual, NACK chỉ áp dụng cho message được chỉ định. Các message khác giữ trạng thái acknowledgement riêng.

Vì vậy, nếu consumer xử lý song song nhiều message và một message lỗi, client-individual thường dễ kiểm soát hơn. Với cumulative mode, ACK/NACK một message có thể ảnh hưởng các message đứng trước nó.

### Không dùng NACK như một vòng retry vô hạn

Nếu lỗi là tạm thời, NACK và redelivery có thể phù hợp. Nếu message sai dữ liệu hoặc vi phạm schema, gửi NACK liên tục có thể tạo vòng lặp nóng.

Một chính sách xử lý lỗi nên xác định:

- Số lần thử tối đa.
- Khoảng nghỉ giữa các lần thử.
- Điều kiện phân biệt lỗi tạm thời và lỗi dữ liệu.
- Dead-letter destination.
- Cách ghi nhận message ID, correlation ID và delivery count.
- Cách vận hành để xem xét và phát lại message từ DLQ.

Một số broker có header riêng thể hiện số lần giao lại hoặc lý do dead-letter. Đây không phải header chuẩn dùng chung cho mọi STOMP server.

## 4. BEGIN, COMMIT và ABORT: transaction ở phía broker

STOMP 1.2 định nghĩa transaction frame để nhóm các thao tác gửi và acknowledge. Transaction được tạo trong một STOMP connection và được nhận diện bằng transaction ID.

Bắt đầu transaction:

~~~text
BEGIN
transaction:tx-1

<NUL>
~~~

Các thao tác gửi và ACK/NACK có thể tham gia transaction bằng header transaction:

~~~text
SEND
destination:/queue/audit
transaction:tx-1
content-type:text/plain

processed:order-42
<NUL>

ACK
id:ack-42
transaction:tx-1

<NUL>
~~~

Hoàn tất transaction:

~~~text
COMMIT
transaction:tx-1

<NUL>
~~~

Nếu muốn hủy transaction:

~~~text
ABORT
transaction:tx-1

<NUL>
~~~

### Transaction nhóm những gì?

Theo STOMP 1.2, transaction áp dụng cho việc gửi message và acknowledge message. Ví dụ một consumer có thể:

1. Nhận message với explicit ack.
2. Bắt đầu transaction tx-1.
3. Gửi một event sang destination audit, gắn transaction tx-1.
4. ACK message vừa nhận, cũng gắn tx-1.
5. COMMIT tx-1.

Nếu broker hỗ trợ transaction đúng theo đặc tả, thao tác gửi event và ACK được xử lý nguyên tử trong phạm vi transaction broker.

| Kết quả | Ý nghĩa ở phía broker |
| --- | --- |
| COMMIT thành công | Các SEND và ACK/NACK đã gắn transaction được áp dụng theo transaction |
| ABORT | Các thao tác đã đưa vào transaction bị hủy theo semantics broker |
| Connection đóng khi transaction chưa commit | STOMP 1.2 yêu cầu transaction chưa commit được abort ngầm |
| Broker lỗi giữa commit | Kết quả client quan sát được phụ thuộc broker, connection recovery và receipt; cần kiểm tra trạng thái trước khi retry |

Transaction ID phải được chỉ định trong BEGIN, COMMIT và ABORT. ID dùng trong các frame SEND, ACK và NACK phải trỏ tới transaction đã mở trên cùng connection. Trong cùng connection, các transaction ID phải khác nhau.

Một transaction STOMP không phải transaction toàn hệ thống. Nó không tự bao gồm database, HTTP request, file hoặc một broker khác.

## 5. Ghép ACK và SEND trong cùng transaction

Một use case phổ biến là consume một message rồi publish kết quả. Nếu chỉ ACK trước rồi SEND sau, có thể xảy ra:

1. Broker nhận ACK và loại message khỏi queue.
2. Ứng dụng mất kết nối trước khi SEND kết quả.
3. Message gốc đã được xác nhận nhưng event kết quả chưa được phát.

Nếu chỉ SEND trước rồi ACK sau, có thể xảy ra:

1. Broker nhận SEND kết quả.
2. Ứng dụng mất kết nối trước khi ACK message gốc.
3. Message gốc được redeliver và ứng dụng có thể gửi kết quả lần nữa.

STOMP transaction cho phép gắn cả SEND và ACK vào cùng transaction:

~~~text
MESSAGE
subscription:orders-sub
message-id:msg-42
ack:ack-42
destination:/queue/orders

order-42
<NUL>

BEGIN
transaction:tx-42

SEND
destination:/queue/processed
transaction:tx-42
content-type:text/plain

processed:order-42
<NUL>

ACK
id:ack-42
transaction:tx-42

COMMIT
transaction:tx-42

<NUL>
~~~

Nếu broker hỗ trợ đầy đủ semantics transaction, broker áp dụng cả hai thao tác khi commit. Nếu transaction bị abort, broker hủy SEND và không áp dụng ACK; message gốc có thể được giao lại theo delivery policy.

Điều này chỉ bảo vệ các thao tác broker tham gia transaction. Nếu xử lý còn ghi database, database không tự động nằm trong STOMP transaction.

## 6. RECEIPT xác nhận điều gì?

Client có thể yêu cầu receipt bằng header receipt trên frame. Ví dụ:

~~~text
COMMIT
transaction:tx-42
receipt:commit-42

<NUL>
~~~

Broker phản hồi:

~~~text
RECEIPT
receipt-id:commit-42

<NUL>
~~~

RECEIPT cho biết server đã xử lý frame tương ứng. Với COMMIT, receipt hữu ích để biết broker đã xử lý yêu cầu commit.

Tuy nhiên, receipt không phải xác nhận rằng consumer phía sau đã xử lý business event, database đã cập nhật hoặc một dịch vụ downstream đã hoàn thành. Nó cũng không tự thay thế cơ chế recovery nếu connection mất trước khi client nhận receipt.

Nếu client gửi COMMIT rồi mất connection trước khi nhận RECEIPT, client có thể không biết commit đã được broker áp dụng hay chưa. Khi retry, cần thiết kế operation idempotent hoặc kiểm tra trạng thái transaction/message theo khả năng broker.

## 7. Giới hạn của Spring simple broker

Spring simple broker được bật bằng:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Simple broker lưu subscription trong bộ nhớ của application instance và phát message tới các subscriber đang kết nối. Nó phù hợp cho nhu cầu pub/sub đơn giản.

Simple broker chỉ hỗ trợ một tập con STOMP. Nó không hỗ trợ ACK, NACK, RECEIPT và các tính năng broker nâng cao tương ứng. Do đó, không nên bật ack:client hoặc gửi BEGIN/COMMIT/ABORT rồi kỳ vọng simple broker cung cấp transactional acknowledgement.

Việc STOMP decoder nhận biết command ACK hoặc BEGIN không có nghĩa broker handler thực thi semantics của command đó. Parsing frame và hỗ trợ broker là hai việc khác nhau.

Khi cần acknowledgement tường minh, redelivery, transaction, durable subscription hoặc dead-letter queue, hãy dùng broker ngoài và Spring STOMP broker relay.

## 8. Dùng STOMP broker relay với broker ngoài

Cấu hình relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");

    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.internal")
            .setRelayPort(61613)
            .setClientLogin("web-client")
            .setClientPasscode("external-secret")
            .setSystemLogin("spring-system")
            .setSystemPasscode("system-secret");
}
~~~

Spring relay chuyển tiếp STOMP frame giữa WebSocket client và broker qua TCP. Broker ngoài mới là nơi quyết định ACK/NACK, transaction, redelivery, persistence và dead-letter semantics.

Trước khi triển khai, cần kiểm tra tài liệu broker cụ thể:

- Broker hỗ trợ STOMP 1.2 hay version nào?
- Có hỗ trợ ack:auto, client và client-individual không?
- ACK/NACK dùng header nào theo version đã thương lượng?
- NACK có requeue, drop hay chuyển DLQ?
- Có hỗ trợ BEGIN/COMMIT/ABORT không?
- Transaction có nhóm cả SEND và ACK/NACK không?
- Transaction ID có giới hạn hoặc timeout không?
- Có giới hạn số message unacknowledged, prefetch hoặc inflight không?
- Có delivery count, retry delay và dead-letter policy không?
- Có hỗ trợ receipt cho COMMIT không?

Không suy ra khả năng của broker chỉ từ việc nó mở STOMP port hoặc Spring relay khởi động thành công. Relay chuyển tiếp giao thức; nó không tự bổ sung tính năng broker còn thiếu.

### Phân biệt destination application và broker

Trong cấu hình Spring thường có hai nhóm destination:

- /app/** được định tuyến tới method @MessageMapping của ứng dụng.
- /topic/** và /queue/** được chuyển tới broker.

STOMP transaction frame của client áp dụng cho thao tác broker mà client gửi trực tiếp và broker hỗ trợ. Message đi qua controller /app/** là luồng xử lý ứng dụng. Không giả định transaction ID do client gửi tự động bao bọc method controller, database transaction hoặc message mà server gửi qua system connection của relay.

## 9. Phân biệt STOMP transaction với Spring @Transactional và JMS transaction

Các cơ chế này có mục tiêu và phạm vi khác nhau:

| Cơ chế | Phạm vi | Ai điều khiển |
| --- | --- | --- |
| STOMP BEGIN/COMMIT/ABORT | Các SEND và ACK/NACK tham gia transaction trên STOMP connection | STOMP client và broker |
| Spring @Transactional | Transaction do Spring transaction manager quản lý cho method/service | Spring application |
| JMS local transaction | Các thao tác trên một JMS Session transacted | JMS client/container |
| JTA/XA | Nhiều resource XA được enlist trong một distributed transaction | Transaction coordinator |

STOMP là protocol wire-level. Nó không mặc nhiên gọi Spring PlatformTransactionManager. Ngược lại, method @Transactional trong controller cũng không tự biến ACK frame của STOMP thành một thao tác nằm trong cùng transaction broker.

Nếu hệ thống dùng STOMP broker relay tới một JMS broker, transaction của STOMP client còn phụ thuộc adapter STOMP của broker và cách broker ánh xạ thao tác sang resource nội bộ. Không coi STOMP transaction và JMS Session transaction là cùng một API.

## 10. Thiết kế consumer an toàn khi ACK/NACK

### Xác nhận sau khi xử lý thành công

Với ack mode explicit, thứ tự xử lý phổ biến là:

1. Nhận MESSAGE.
2. Validate payload và quyền truy cập.
3. Thực hiện nghiệp vụ.
4. Lưu trạng thái hoặc kết quả bền vững.
5. Gửi ACK.

Nếu nghiệp vụ thất bại tạm thời, gửi NACK hoặc để connection đóng tùy semantics broker. Nếu lỗi không thể phục hồi, đưa message vào DLQ hoặc đánh dấu lỗi theo quy trình broker.

### Idempotency và duplicate detection

Broker có thể redeliver message khi client mất connection, ACK chưa tới broker hoặc transaction bị abort. Vì vậy, consumer nên dùng message ID, business key hoặc idempotency key để nhận biết message đã được xử lý.

Ví dụ, khi xử lý payment command, database có thể lưu unique request ID. Nếu message được giao lại, consumer kiểm tra ID đã hoàn tất và không thực hiện charge lần nữa.

### ACK cumulative cần cẩn thận khi xử lý song song

Với ack:client, ACK một message xác nhận cả các message trước đó trên cùng subscription. Nếu ứng dụng xử lý song song và message sau hoàn thành trước message trước, ACK message sau có thể xác nhận nhầm một message trước vẫn đang xử lý.

Với xử lý song song, hãy cân nhắc client-individual nếu broker hỗ trợ. Nếu dùng cumulative mode, cần giữ thứ tự xử lý/ack hoặc thiết kế lại concurrency.

### Prefetch và unacknowledged limit

Một số broker gửi trước nhiều message cho client trước khi nhận ACK. Số lượng message đang inflight có thể được điều khiển bằng prefetch hoặc giới hạn tương tự của broker.

Nếu client xử lý chậm, inflight quá lớn có thể làm tăng memory, thời gian redelivery và số message bị giữ trên connection. Hãy cấu hình giới hạn theo năng lực xử lý và latency mục tiêu. Tên cấu hình và semantics là riêng của broker.

## 11. Ví dụ Java 17+: parse ACK/NACK và transaction frame bằng Spring StompDecoder

Ví dụ sau dùng StompDecoder để đọc các frame STOMP 1.2. Nó giúp quan sát command, destination, subscription, ack token, id và transaction header.

Chương trình chỉ parse frame; nó không kết nối broker và không thực thi ACK hoặc COMMIT.

Tạo file src/main/java/example/StompAckTransactionFrameDemo.java:

~~~java
package example;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompDecoder;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class StompAckTransactionFrameDemo {

    private static void decode(String label, String frame) {
        StompDecoder decoder = new StompDecoder();
        List<Message<byte[]>> messages = decoder.decode(ByteBuffer.wrap(
                frame.getBytes(StandardCharsets.UTF_8)));

        if (messages.size() != 1) {
            throw new IllegalStateException(label + ": expected one frame, got "
                    + messages.size());
        }

        StompHeaderAccessor headers =
                StompHeaderAccessor.wrap(messages.get(0));

        System.out.println(label + ".command=" + headers.getCommand());
        System.out.println(label + ".destination=" + headers.getDestination());
        System.out.println(label + ".subscription="
                + headers.getSubscriptionId());
        System.out.println(label + ".ackToken=" + headers.getAck());
        System.out.println(label + ".id="
                + headers.getFirstNativeHeader("id"));
        System.out.println(label + ".transaction="
                + headers.getFirstNativeHeader("transaction"));
    }

    public static void main(String[] args) {
        decode("subscribe", "SUBSCRIBE\nid:orders-sub\n"
                + "destination:/queue/orders\nack:client-individual\n\n\u0000");

        decode("message", "MESSAGE\nsubscription:orders-sub\n"
                + "message-id:msg-42\nack:ack-42\n"
                + "destination:/queue/orders\ncontent-type:text/plain\n\n"
                + "order-42\u0000");

        decode("begin", "BEGIN\ntransaction:tx-1\n\n\u0000");

        decode("send", "SEND\ndestination:/queue/audit\n"
                + "transaction:tx-1\ncontent-type:text/plain\n\n"
                + "processed:order-42\u0000");

        decode("ack", "ACK\nid:ack-42\ntransaction:tx-1\n\n\u0000");

        decode("commit", "COMMIT\ntransaction:tx-1\n\n\u0000");

        decode("nack", "NACK\nid:ack-43\n\n\u0000");

        decode("abort", "ABORT\ntransaction:tx-2\n\n\u0000");
    }
}
~~~

Tạo pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>stomp-ack-transaction-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>7.0.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.StompAckTransactionFrameDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java
~~~

Kết quả stdout:

~~~text
subscribe.command=SUBSCRIBE
subscribe.destination=/queue/orders
subscribe.subscription=orders-sub
subscribe.ackToken=client-individual
subscribe.id=orders-sub
subscribe.transaction=null
message.command=MESSAGE
message.destination=/queue/orders
message.subscription=orders-sub
message.ackToken=ack-42
message.id=null
message.transaction=null
begin.command=BEGIN
begin.destination=null
begin.subscription=null
begin.ackToken=null
begin.id=null
begin.transaction=tx-1
send.command=SEND
send.destination=/queue/audit
send.subscription=null
send.ackToken=null
send.id=null
send.transaction=tx-1
ack.command=ACK
ack.destination=null
ack.subscription=null
ack.ackToken=null
ack.id=ack-42
ack.transaction=tx-1
commit.command=COMMIT
commit.destination=null
commit.subscription=null
commit.ackToken=null
commit.id=null
commit.transaction=tx-1
nack.command=NACK
nack.destination=null
nack.subscription=null
nack.ackToken=null
nack.id=ack-43
nack.transaction=null
abort.command=ABORT
abort.destination=null
abort.subscription=null
abort.ackToken=null
abort.id=null
abort.transaction=tx-2
~~~

Output cho thấy MESSAGE chứa ack token ack-42, trong khi ACK sử dụng native header id với cùng giá trị. Transaction ID được đọc từ header transaction của BEGIN, SEND, ACK, COMMIT và ABORT.

## 12. Kiểm thử integration với broker thật

StompDecoder chỉ kiểm tra cú pháp và cách Spring parse header. Muốn xác nhận broker hỗ trợ acknowledgement hoặc transaction, cần integration test với đúng broker/version/configuration của môi trường chạy.

Một kịch bản kiểm thử nên bao gồm:

1. Mở STOMP connection và thương lượng version.
2. SUBSCRIBE với ack:client-individual.
3. Gửi message tới destination.
4. Xác nhận MESSAGE có header ack.
5. ACK message và xác nhận broker không giao lại.
6. Gửi message khác rồi NACK; xác minh requeue, redelivery hoặc DLQ theo policy.
7. BEGIN transaction, SEND message audit và ACK message gốc cùng transaction.
8. COMMIT rồi xác minh cả hai thao tác đã áp dụng.
9. Lặp lại với ABORT; xác minh SEND bị hủy và message gốc chưa được acknowledge.
10. Ngắt connection khi transaction chưa commit; xác minh broker abort transaction theo STOMP 1.2.
11. Thử mất connection trước/sau COMMIT để kiểm tra trường hợp client không nhận được RECEIPT.
12. Kiểm tra giới hạn inflight/prefetch, retry count và DLQ.

Nên chạy cả happy path và lỗi mạng. Kết quả cần kiểm tra trên broker hoặc consumer thật, không chỉ dựa vào log client.

## 13. Lỗi thường gặp

1. **Dùng ACK với ack:auto.** Subscription auto không yêu cầu ACK; server đã xem message được giao khi gửi MESSAGE.
2. **Dùng message-id thay cho ack token trong STOMP 1.2.** ACK/NACK phải dùng header id khớp với MESSAGE header ack.
3. **Dùng header ACK của STOMP 1.1 trên connection STOMP 1.2.** 1.1 dùng message-id/subscription; 1.2 dùng id.
4. **Cho rằng NACK luôn redeliver.** Broker có thể requeue, giao cho consumer khác, drop hoặc dead-letter.
5. **Dùng ack:client khi xử lý song song.** ACK cumulative có thể xác nhận cả message trước đang xử lý.
6. **Cho rằng simple broker hỗ trợ ACK/NACK.** Spring simple broker không hỗ trợ explicit ack/receipt.
7. **Gửi BEGIN/COMMIT tới simple broker và mong có transaction.** Decoder nhận biết frame không có nghĩa simple broker thực thi transaction.
8. **Dùng transaction ID trên connection khác.** Transaction thuộc connection đã mở nó.
9. **Quên gắn transaction header vào SEND/ACK/NACK.** Các thao tác đó sẽ không thuộc transaction đang mở.
10. **Cho rằng COMMIT RECEIPT xác nhận business processing.** Receipt xác nhận server đã xử lý frame; nó không chứng minh database hoặc downstream service đã hoàn tất.
11. **Cho rằng STOMP transaction bao gồm database.** Transaction frame chỉ nhóm thao tác messaging broker theo khả năng broker.
12. **Cho rằng @Transactional tự động điều khiển STOMP ACK.** Spring transaction manager và STOMP broker transaction là hai cơ chế riêng.
13. **Không xử lý trường hợp mất connection quanh COMMIT.** Client có thể không biết commit đã được áp dụng; cần idempotency và recovery.
14. **Không giới hạn retry hoặc xử lý poison message.** NACK liên tục có thể tạo vòng lặp và tải lớn.
15. **Không kiểm tra broker version/capability.** Cùng một frame có thể có semantics hoặc giới hạn khác nhau giữa broker.

## 14. Checklist triển khai

- Thương lượng và xác nhận STOMP version.
- Chọn ack:auto, client hoặc client-individual theo yêu cầu xử lý.
- Với STOMP 1.2, lấy ACK/NACK id từ MESSAGE header ack.
- Chỉ gửi ACK sau khi ứng dụng hoàn tất bước xử lý cần bảo vệ.
- Dùng NACK theo retry/DLQ policy đã kiểm chứng của broker.
- Kiểm tra broker hỗ trợ ACK/NACK, receipt và transaction frame.
- Chỉ nhóm SEND và ACK/NACK khi broker hỗ trợ transaction semantics cần thiết.
- Giữ transaction ID trong cùng STOMP connection và không tái sử dụng ID trong connection đó.
- Dùng RECEIPT để biết broker đã xử lý frame, không coi nó là business acknowledgement.
- Dùng idempotency để chịu được redelivery và kết quả COMMIT không rõ do mất connection.
- Kiểm thử broker thật với ACK, NACK, COMMIT, ABORT, reconnect và DLQ.
- Không giả định STOMP transaction tự bao gồm Spring @Transactional, database hoặc JMS Session transaction.

## 15. Tài liệu tham khảo

- [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework 7.0 – External Broker Relay](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework 7.0 – Simple Broker](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework – StompDecoder Javadoc](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)
- [Spring Framework – StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/7.0.10/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
