# Phân biệt bất biến của vỏ thông điệp và khả năng thay đổi của payload

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Message trong Spring Messaging gồm payload và headers.
- Phân biệt tính bất biến của envelope với trạng thái bên trong object payload.
- Hiểu vì sao tạo Message mới từ Message cũ không đồng nghĩa với sao chép payload.
- Nhận diện rủi ro khi nhiều handler hoặc thread cùng tham chiếu một payload mutable.
- Tạo snapshot độc lập bằng immutable DTO hoặc defensive copy.
- Phân biệt việc sao chép map headers với việc sao chép sâu các giá trị header.
- Chọn cách truyền dữ liệu an toàn khi dùng channel đồng bộ, executor hoặc broker.

## 1. Một Message có hai phần khác nhau

Trong Spring Messaging, một Message<T> đóng gói hai thành phần:

- **Payload:** dữ liệu chính mà producer muốn truyền, có kiểu tổng quát T. Payload có thể là String, DTO, record, byte array, collection hoặc một object bất kỳ phù hợp với ứng dụng.
- **Headers:** metadata mô tả thông điệp, chẳng hạn ID, timestamp, content type, correlation ID, destination hoặc thông tin do ứng dụng tự định nghĩa.

Có thể hình dung cấu trúc như sau:

~~~mermaid
flowchart TB
    M["Message<T>"]
    H["MessageHeaders<br/>Metadata của thông điệp"]
    P["Payload T<br/>Object dữ liệu"]
    M --> H
    M --> P
    H --> H1["ID, timestamp, content type"]
    H --> H2["Correlation ID, destination"]
    P --> P1["String / DTO / record"]
    P --> P2["List / Map / byte[] / object mutable"]
~~~

Spring thiết kế Message như một envelope bất biến. Các implementation thông dụng như GenericMessage giữ payload và headers của message sau khi được tạo. MessageHeaders cũng cung cấp một map headers bất biến.

Tuy nhiên, bất biến của envelope không đồng nghĩa với bất biến sâu của mọi object mà envelope đang tham chiếu tới. Nếu payload là một object có thể thay đổi, object đó vẫn có thể bị thay đổi sau khi Message được tạo.

Đây là điểm quan trọng nhất của bài học:

**Message có thể bất biến trong khi payload bên trong nó vẫn mutable.**

## 2. Bất biến của envelope có nghĩa là gì?

Envelope là lớp vỏ chứa tham chiếu tới payload và metadata. Tính bất biến của nó có nghĩa là sau khi Message được tạo, ứng dụng không dùng Message đó như một cấu trúc để thay payload hoặc sửa trực tiếp map headers.

Ví dụ:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-56")
        .setHeader("eventType", "order.created")
        .build();
~~~

Sau khi tạo, có thể đọc:

~~~java
String orderId = message.getPayload();
Object eventType = message.getHeaders().get("eventType");
~~~

Nhưng không thể dùng map headers của Message để thay đổi trực tiếp:

~~~java
message.getHeaders().put("traceId", "trace-56");
~~~

MessageHeaders là immutable map; thao tác sửa trực tiếp như put sẽ bị từ chối bằng UnsupportedOperationException.

Nếu cần thêm hoặc thay header, hãy tạo một Message mới qua MessageBuilder:

~~~java
Message<String> tracedMessage = MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", "trace-56")
        .build();
~~~

Kết quả là một envelope mới có metadata mới. Cách làm này giữ cho Message đã tạo không bị sửa tại chỗ và giúp người đọc nhận ra thời điểm dữ liệu được đóng gói.

## 3. Payload có thể mutable dù Message bất biến

Payload là một object Java bình thường. Spring không tự động deep clone hoặc đóng băng trạng thái nội bộ của object đó khi tạo Message.

Các ví dụ payload thường gặp:

| Kiểu payload | Khả năng thay đổi | Lưu ý |
|---|---|---|
| String | Bất biến | Có thể chia sẻ an toàn theo trạng thái của chính String |
| Integer, Long, Boolean | Bất biến | Là các wrapper cho giá trị nguyên thủy |
| Java record | Bất biến nông | Component có thể vẫn là object mutable |
| DTO có setter | Thường mutable | Có thể bị thay đổi sau khi gửi |
| ArrayList hoặc HashMap | Mutable | Có thể thêm, xóa hoặc thay phần tử |
| byte[] | Mutable | Có thể sửa từng phần tử |
| Date | Mutable | Có các API thay đổi thời gian |
| Object tự định nghĩa | Tùy thiết kế | Cần xem các field và object lồng bên trong |

Ví dụ, nếu payload là một DTO có setter:

~~~java
final class OrderPayload {
    private final String orderId;
    private String status;

    OrderPayload(String orderId, String status) {
        this.orderId = orderId;
        this.status = status;
    }

    String getOrderId() {
        return orderId;
    }

    String getStatus() {
        return status;
    }

    void setStatus(String status) {
        this.status = status;
    }
}
~~~

Tạo Message không làm cho phương thức setStatus() biến mất. Bất kỳ thành phần nào còn giữ tham chiếu tới OrderPayload đều có thể thay đổi status.

Vì vậy, không nên suy luận rằng “đã bọc vào Message thì dữ liệu đã được bảo vệ khỏi thay đổi”. Message bảo vệ cấu trúc envelope theo thiết kế của nó; trách nhiệm bảo vệ trạng thái payload vẫn thuộc về ứng dụng.

## 4. Tạo Message mới không đồng nghĩa với sao chép payload

Một lỗi dễ gặp là nghĩ rằng MessageBuilder.fromMessage(existing) sẽ tạo một bản sao độc lập của toàn bộ object graph.

Thông thường, thao tác này tạo một Message mới dựa trên Message cũ và giữ lại tham chiếu payload hiện có, trừ khi ứng dụng chủ động cung cấp payload khác.

Ví dụ:

~~~java
Message<MutableOrder> original = MessageBuilder
        .withPayload(order)
        .setHeader("eventType", "order.created")
        .build();

Message<MutableOrder> withTrace = MessageBuilder
        .fromMessage(original)
        .setHeader("traceId", "trace-56")
        .build();
~~~

Hai Message có thể là hai envelope khác nhau nhưng cùng trỏ tới một object payload:

~~~text
original -----------+
                    +----> cùng một MutableOrder
withTrace ----------+
~~~

Do đó:

- Thay header khi tạo withTrace không sửa map headers của original.
- Thay đổi object order vẫn được quan sát qua payload của cả hai Message.
- Nếu hai consumer xử lý trên các thread khác nhau, việc cùng truy cập object mutable có thể gây race condition.

Phải phân biệt **sao chép envelope** với **sao chép dữ liệu payload**. Đây là hai thao tác riêng.

## 5. Header map bất biến cũng không bảo đảm mọi giá trị header bất biến

MessageHeaders bảo vệ cấu trúc map: ứng dụng không thể thêm, xóa hoặc thay mapping trực tiếp qua map đã đóng gói. Nhưng giá trị được lưu trong map vẫn có thể là object mutable.

Ví dụ:

~~~java
List<String> tags = new ArrayList<>();
tags.add("new");

Message<String> message = MessageBuilder
        .withPayload("ORD-56")
        .setHeader("tags", tags)
        .build();

tags.add("priority");
~~~

Map headers không bị sửa bằng thao tác put/remove, nhưng object List được tham chiếu từ header đã thay đổi. Khi đọc message.getHeaders().get("tags"), ứng dụng có thể nhìn thấy cả hai phần tử.

Điều này cũng là bất biến nông (shallow immutability). Nếu cần metadata an toàn, hãy ưu tiên giá trị bất biến như String, số, enum hoặc object metadata bất biến. Nếu phải lưu collection, hãy tạo bản sao và cân nhắc cả tính bất biến của từng phần tử.

Ví dụ List.copyOf(tags) tạo một list không thể thêm/xóa phần tử qua API List, nhưng đây vẫn là bản sao nông: các object nằm trong list không tự động được clone sâu.

## 6. Ví dụ Java chạy được: envelope mới, payload dùng chung

Ví dụ hoàn chỉnh sau minh họa bốn điều:

1. Tạo Message chứa một payload mutable.
2. Dùng MessageBuilder.fromMessage() để tạo envelope mới với header bổ sung.
3. Thay đổi payload và quan sát cả hai Message cùng thấy trạng thái mới.
4. Tạo defensive copy của payload để có snapshot độc lập.

### 6.1. Cấu hình Maven

Ví dụ dùng Java 17 và Spring Framework 6.2.8. Dùng Spring Framework BOM để quản lý phiên bản dependency:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>message-payload-mutability</artifactId>
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
                <version>6.2.8</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
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

### 6.2. Chương trình hoàn chỉnh

Tạo file src/main/java/demo/MessagePayloadMutabilityDemo.java:

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessagePayloadMutabilityDemo {

    static final class MutableOrder {
        private final String orderId;
        private String status;

        MutableOrder(String orderId, String status) {
            this.orderId = orderId;
            this.status = status;
        }

        String getOrderId() {
            return orderId;
        }

        String getStatus() {
            return status;
        }

        void setStatus(String status) {
            this.status = status;
        }

        MutableOrder copy() {
            return new MutableOrder(orderId, status);
        }
    }

    public static void main(String[] args) {
        MutableOrder order = new MutableOrder("ORD-56", "CREATED");

        Message<MutableOrder> original = MessageBuilder
                .withPayload(order)
                .setHeader("eventType", "order.created")
                .build();

        Message<MutableOrder> newEnvelope = MessageBuilder
                .fromMessage(original)
                .setHeader("traceId", "trace-56")
                .build();

        System.out.println("sameMessage=" + (original == newEnvelope));
        System.out.println(
                "samePayload="
                        + (original.getPayload() == newEnvelope.getPayload())
        );

        // Cả hai Message vẫn tham chiếu tới cùng object order.
        order.setStatus("PAID");

        System.out.println(
                "original.status=" + original.getPayload().getStatus()
        );
        System.out.println(
                "newEnvelope.status=" + newEnvelope.getPayload().getStatus()
        );

        // Tạo payload độc lập và giữ lại các metadata cần thiết.
        Message<MutableOrder> snapshot = MessageBuilder
                .withPayload(original.getPayload().copy())
                .setHeader(
                        "eventType",
                        original.getHeaders().get("eventType")
                )
                .setHeader(
                        "traceId",
                        newEnvelope.getHeaders().get("traceId")
                )
                .build();

        // MessageHeaders không cho sửa trực tiếp map.
        try {
            original.getHeaders().put("extra", "value");
            System.out.println("headersMutable=true");
        }
        catch (UnsupportedOperationException ex) {
            System.out.println("headersMutable=false");
        }

        // Thay đổi object gốc lần nữa.
        order.setStatus("SHIPPED");

        System.out.println(
                "original.status.afterSecondMutation="
                        + original.getPayload().getStatus()
        );
        System.out.println(
                "newEnvelope.status.afterSecondMutation="
                        + newEnvelope.getPayload().getStatus()
        );
        System.out.println(
                "snapshot.status.afterSecondMutation="
                        + snapshot.getPayload().getStatus()
        );
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessagePayloadMutabilityDemo
~~~

Stdout:

~~~text
sameMessage=false
samePayload=true
original.status=PAID
newEnvelope.status=PAID
headersMutable=false
original.status.afterSecondMutation=SHIPPED
newEnvelope.status.afterSecondMutation=SHIPPED
snapshot.status.afterSecondMutation=PAID
~~~

### 6.3. Phân tích kết quả

sameMessage=false cho biết original và newEnvelope là hai envelope khác nhau. Header traceId được bổ sung trên envelope mới.

samePayload=true cho biết hai Message cùng tham chiếu tới một object MutableOrder. Khi gọi order.setStatus("PAID"), cả hai đều đọc được trạng thái PAID.

Sau đó chương trình tạo snapshot bằng cách gọi copy() trên payload. Snapshot giữ trạng thái PAID tại thời điểm sao chép. Khi object gốc chuyển sang SHIPPED, payload của snapshot vẫn giữ PAID.

headersMutable=false xác nhận map MessageHeaders không cho phép thay đổi trực tiếp bằng put.

Ví dụ này chứng minh rằng tạo một Message mới và tạo một bản sao payload là hai thao tác khác nhau. Nếu muốn thông điệp giữ nguyên dữ liệu tại thời điểm phát sinh, producer phải dùng payload bất biến hoặc chủ động tạo bản sao độc lập.

## 7. Cách tạo payload an toàn hơn

Có nhiều cách giảm rủi ro chia sẻ trạng thái mutable. Chọn cách phù hợp với kích thước dữ liệu, hiệu năng và ranh giới giao tiếp.

### 7.1. Ưu tiên DTO bất biến

Một DTO bất biến không cung cấp setter và chỉ giữ các giá trị bất biến:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        long totalAmount
) {}
~~~

Với các component là String và kiểu nguyên thủy, record này phù hợp để làm payload bất biến. Producer có thể chia sẻ nó mà không lo một consumer thay đổi field.

Tuy nhiên, record chỉ bảo đảm bất biến nông. Nếu component là List<MutableItem>, list hoặc từng MutableItem vẫn có thể thay đổi. Hãy tạo bản sao phòng vệ và dùng phần tử bất biến khi cần snapshot sâu.

### 7.2. Dùng defensive copy khi nhận hoặc gửi

Nếu nghiệp vụ cần giữ một snapshot, hãy tạo object mới thay vì truyền tham chiếu tới object đang được nhiều nơi sử dụng.

~~~java
MutableOrder payloadSnapshot = order.copy();

Message<MutableOrder> message = MessageBuilder
        .withPayload(payloadSnapshot)
        .setHeader("eventType", "order.created")
        .build();
~~~

Với collection, cần hiểu độ sâu của bản sao:

- new ArrayList<>(source) tạo list mới nhưng giữ nguyên tham chiếu phần tử.
- List.copyOf(source) tạo list không sửa được qua API List nhưng không clone sâu các phần tử.
- Deep copy phải tạo bản sao cho cả các object mutable lồng bên trong, hoặc chuyển dữ liệu sang một cấu trúc bất biến phù hợp.

Không phải lúc nào cũng cần deep copy. Nếu payload đã bất biến hoặc quyền sở hữu dữ liệu được chuyển giao rõ ràng, sao chép toàn bộ object graph có thể tốn tài nguyên mà không tăng an toàn.

### 7.3. Không để producer tiếp tục sửa object đã gửi

Một quy ước hữu ích là sau khi gửi Message, producer không tiếp tục thay đổi payload đã bàn giao. Quy ước này dễ thực hiện khi payload bất biến hoặc được xem là dữ liệu chỉ đọc.

Nếu producer vẫn cần dùng dữ liệu để cập nhật trạng thái, hãy tạo payload riêng cho thông điệp. Đừng dựa vào việc consumer sẽ đọc xong trước khi producer sửa object, vì thời điểm xử lý có thể thay đổi khi channel chuyển từ đồng bộ sang bất đồng bộ.

### 7.4. Dùng kiểu dữ liệu phù hợp cho header

Headers nên mang metadata nhỏ, có ý nghĩa rõ ràng và dễ chia sẻ:

- String cho correlation ID, event type hoặc destination.
- Enum hoặc giá trị số cho loại và mức ưu tiên.
- Thời điểm hoặc content type theo quy ước của ứng dụng.

Hạn chế đưa DTO nghiệp vụ mutable, collection mutable hoặc object có vòng đời phức tạp vào headers. Nếu header value là object mutable, map bất biến không bảo vệ trạng thái bên trong object đó.

## 8. Rủi ro khi xử lý trên nhiều thread

Khi Message được gửi qua channel đồng bộ, handler có thể chạy ngay trong thread producer. Khi channel dispatch qua executor, handler có thể chạy trên worker thread. Sự thay đổi về thread không tự tạo bản sao payload.

Nếu producer và consumer cùng tham chiếu payload mutable, có thể xảy ra:

- **Race condition:** producer sửa field đúng lúc consumer đọc field.
- **Inconsistent snapshot:** consumer đọc một số field trước khi producer cập nhật và một số field sau khi cập nhật.
- **Thay đổi ngoài dự kiến:** consumer thứ nhất sửa object, consumer thứ hai nhận thấy dữ liệu đã bị thay đổi.
- **Lỗi khó tái hiện:** chương trình chạy đúng khi handler nhanh nhưng sai khi executor bận hoặc hệ thống có tải cao.

Executor tiêu chuẩn có quy tắc truyền đạt bộ nhớ khi submit task, giúp các thao tác xảy ra trước khi submit được nhìn thấy khi task bắt đầu. Điều đó không làm object trở thành immutable và cũng không bảo vệ khỏi các lần sửa đồng thời sau khi submit.

Vì vậy, cách an toàn thường là:

1. Hoàn tất dữ liệu payload trước khi gửi.
2. Dùng immutable DTO hoặc snapshot riêng.
3. Không chia sẻ collection hoặc array mutable giữa các consumer.
4. Nếu bắt buộc chia sẻ trạng thái, dùng cơ chế đồng bộ phù hợp và xác định rõ quyền sở hữu.
5. Kiểm tra lại khi chuyển từ channel đồng bộ sang executor hoặc broker vì thời điểm xử lý thay đổi.

## 9. Khi thông điệp đi qua broker hoặc ranh giới tiến trình

Một số adapter serialize payload thành byte trước khi gửi qua transport. Consumer ở tiến trình khác thường nhận object được deserialize từ dữ liệu truyền đi, nên object đó không phải cùng reference Java với object phía producer.

Tuy nhiên, điều này không có nghĩa serialization tự động giải quyết mọi vấn đề:

- Payload có thể bị producer thay đổi trước hoặc trong lúc serialize.
- Thời điểm serialize phụ thuộc adapter và cấu hình.
- Custom serializer có thể bỏ qua field, biến đổi kiểu hoặc không hỗ trợ một số object.
- Header có thể được ánh xạ sang metadata riêng của giao thức; không phải mọi object header đều truyền qua wire được.
- Nếu dùng in-memory channel, không có ranh giới serialize/deserialize nên payload có thể vẫn là cùng reference.

Vì thế, hãy thiết kế payload như một event hoặc DTO có schema rõ ràng, chứa dữ liệu cần thiết tại thời điểm phát sinh. Đừng dựa vào việc broker sẽ luôn tạo ra snapshot đúng cách nếu chưa kiểm tra serializer và adapter thực tế.

## 10. Phân biệt các thao tác thường gặp

| Thao tác | Envelope | Payload | Headers |
|---|---|---|---|
| Tạo Message bằng withPayload(existingObject) | Tạo Message mới | Giữ reference được truyền vào | Tạo metadata cho Message |
| Tạo Message bằng fromMessage(existing) rồi setHeader | Tạo Message mới | Thường giữ cùng payload reference | Tạo bộ headers cho Message mới |
| Gọi getHeaders().put(...) | Không tạo Message mới | Không đổi | Bị từ chối vì MessageHeaders bất biến |
| Tạo Message mới với payload.copy() | Tạo Message mới | Dùng object payload mới do ứng dụng sao chép | Chỉ giữ metadata được ứng dụng chọn |
| Dùng immutable DTO | Tạo Message mới | Trạng thái payload không thể thay đổi qua API công khai của DTO | Độc lập với tính bất biến payload |

Cụm từ “copy Message” cần được dùng cẩn thận. Nó có thể chỉ việc tạo envelope mới, copy map headers hoặc deep copy payload. Hãy nói rõ loại copy đang thực hiện.

## 11. Lỗi thường gặp

1. **Cho rằng Message bất biến nên payload cũng bất biến:** envelope và object payload là hai lớp khác nhau.
2. **Cho rằng fromMessage() deep clone payload:** builder tạo Message mới nhưng không tự sao chép object graph của payload.
3. **Sửa object sau khi gửi:** consumer có thể nhìn thấy trạng thái mới nếu vẫn dùng chung reference.
4. **Cho rằng headers immutable đồng nghĩa header value immutable:** map không cho sửa mapping, nhưng value có thể là object mutable.
5. **Dùng record rồi mặc định mọi thứ bất biến:** record chỉ bất biến nông; collection và object component vẫn có thể mutable.
6. **Dùng List.copyOf() như deep copy:** list mới không cho sửa cấu trúc nhưng phần tử mutable vẫn được chia sẻ.
7. **Chia sẻ byte[] giữa các handler:** mảng byte có thể bị thay đổi sau khi gửi.
8. **Chuyển channel sang executor mà không xem lại payload:** xử lý chuyển sang thread khác làm lộ race condition vốn khó thấy ở luồng đồng bộ.
9. **Dựa vào broker để tạo snapshot:** phải xác định adapter serialize lúc nào và dữ liệu nào thực sự được truyền.
10. **Copy toàn bộ object graph không cần thiết:** deep copy có chi phí; chỉ tạo snapshot ở ranh giới cần bảo đảm tính độc lập.

## 12. Câu hỏi tự kiểm tra

1. Một Message<T> gồm những thành phần nào?
2. Vì sao Message có thể bất biến nhưng payload vẫn thay đổi?
3. MessageBuilder.fromMessage() tạo envelope mới hay deep clone payload?
4. Hai Message có thể khác nhau nhưng cùng tham chiếu tới một payload không?
5. Vì sao MessageHeaders bất biến không bảo vệ một List được lưu làm header value?
6. Record Java bảo đảm loại bất biến nào? Khi nào cần defensive copy?
7. Khác biệt giữa new ArrayList<>(source) và deep copy là gì?
8. Tại sao thay đổi payload sau khi send nguy hiểm hơn khi dùng executor?
9. Serialization qua broker có luôn bảo đảm snapshot đúng thời điểm không?
10. Khi nào nên dùng immutable DTO, defensive copy hoặc cơ chế đồng bộ?

## 13. Kết luận

Spring Messaging cung cấp một envelope Message với payload và headers. MessageHeaders bảo vệ cấu trúc metadata, còn các Message implementation thông dụng được thiết kế để không bị sửa trực tiếp sau khi tạo. Nhưng payload và giá trị bên trong headers vẫn có thể là object mutable.

Tạo Message mới bằng MessageBuilder.fromMessage() giúp thay đổi envelope, chẳng hạn thêm correlation ID, mà không mặc định tạo bản sao độc lập cho payload. Nếu producer và consumer cùng tham chiếu tới object mutable, thay đổi từ một phía có thể xuất hiện ở phía còn lại và gây lỗi khi xử lý đồng thời.

Để giữ dữ liệu đúng tại thời điểm phát sinh, hãy ưu tiên payload bất biến hoặc tạo defensive copy phù hợp. Đồng thời, kiểm tra cả object lồng bên trong payload và header value; tính bất biến nông của map hoặc record không thay thế được thiết kế quyền sở hữu dữ liệu.

## Tài liệu tham khảo chính thức

- Spring Framework Messaging API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/package-summary.html
- Message API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html
- MessageHeaders API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html
- GenericMessage API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/GenericMessage.html
- MessageBuilder API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- MessageHeaderAccessor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html
